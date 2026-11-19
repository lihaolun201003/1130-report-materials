"""Corrected 2-D scalar FDFD crossing solver (audit implementation, NOT legacy).

Why a corrected solver is needed
--------------------------------
The legacy ``crossing.solve_crossing`` builds its "discrete incident mode" from

    Ty = plain_d2(y) + diag(k0^2 * n2_bg[1:-1, 0] ** 2)

Two independent bugs:
 (1) ``n2_bg[:, 0]`` is the left *Dirichlet boundary* column of ``_index_grid_2d``
     which is overwritten with n_clad^2 -> the transverse profile contains NO core;
 (2) ``n2_bg`` already stores n^2, and the code squares it again -> it uses n^4.
The resulting "mode" is a high-order box sine of a fictitious uniform n^4 medium
(n_eff=1.63), i.e. the incident field is not a guided mode of the input guide.

This module keeps the legacy grid / domain / EIM / PML machinery bit-identical
(so the comparison is apples-to-apples) but constructs the incident field from
the correct background transverse operator, and provides a fully independent
port/flux analyser.
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import eigsh, splu

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_lib as AL

from src.config import CONFIG          # noqa: E402
from src.crossing import (_domain_for_angle, _index_grid_2d, _pml,  # noqa: E402
                          _plain_d2, _stretched_d2)


def _build_geometry(optics, theta_deg, grid_um, d_port_um, pml_um, max_unknowns,
                    bounds=None):
    """Replicate the legacy domain-size loop *exactly* (same grid coarsening).

    bounds : optional dict(x_min,x_max,y_min,y_max) to override the legacy
             symmetric domain (used only for the domain-truncation study).
    """
    cfg = CONFIG["crossing_model"]
    th = math.radians(theta_deg)
    w = float(optics["core_width_um"])
    k0 = 2.0 * math.pi / (float(optics["wavelength_nm"]) * 1e-3)
    n0 = float(optics["n_clad"])
    eim = AL.crossing_eim(optics)
    ns = float(eim.n_slab)
    margin = float(cfg["domain_margin_um"])
    if bounds is None:
        while True:
            Lx, Ly = _domain_for_angle(th, w, d_port_um, margin)
            nx = int(round(2 * Lx / grid_um)) + 1
            ny = int(round(2 * Ly / grid_um)) + 1
            if nx % 2 == 0:
                nx += 1
            if ny % 2 == 0:
                ny += 1
            N = (nx - 2) * (ny - 2)
            if N <= max_unknowns and (Lx > pml_um + 1.5 * w) and (Ly > pml_um + 1.5 * w):
                break
            grid_um *= 1.1
            if grid_um > 0.6:
                raise RuntimeError("domain too large")
        h = grid_um
        x = np.linspace(-Lx, Lx, nx)
        y = np.linspace(-Ly, Ly, ny)
        Lx, Ly = float(Lx), float(Ly)
        x_min, x_max, y_min, y_max = -Lx, Lx, -Ly, Ly
    else:
        h = float(grid_um)
        x_min = float(bounds["x_min"]); x_max = float(bounds["x_max"])
        y_min = float(bounds["y_min"]); y_max = float(bounds["y_max"])
        nx = int(round((x_max - x_min) / h)) + 1
        ny = int(round((y_max - y_min) / h)) + 1
        if nx % 2 == 0:
            nx += 1
        if ny % 2 == 0:
            ny += 1
        x = np.linspace(x_min, x_max, nx)
        y = np.linspace(y_min, y_max, ny)
        N = (nx - 2) * (ny - 2)
        Lx = 0.5 * (x_max - x_min); Ly = 0.5 * (y_max - y_min)
    n2, n2_bg = _index_grid_2d(x, y, th, ns, n0, w)
    return dict(th=th, w=w, k0=k0, n0=n0, eim=eim, ns=ns, h=h, x=x, y=y,
                Lx=Lx, Ly=Ly, nx=nx, ny=ny, N=N, n2=n2, n2_bg=n2_bg,
                pml_um=pml_um,
                bounds=(x_min, x_max, y_min, y_max))


def _pml_asym(coord, lo, hi, thickness_um, strength):
    """Complex stretching factor for a (possibly asymmetric) 1-D extent."""
    s = np.ones_like(coord, dtype=complex)
    d = np.maximum.reduce([np.zeros_like(coord),
                           (lo + thickness_um) - coord,
                           coord - (hi - thickness_um)])
    m = d > 0
    s[m] = 1.0 + 1j * strength * (d[m] / thickness_um) ** 2
    return s


def correct_incident_mode(geo, n_bg_col=None, n_keep_guided=1, verbose=False):
    """Fundamental guided mode of the *actual* background transverse profile.

    n_bg_col : 1-D array of n^2 across y (default: centre column of n2_bg).
    Returns dict with phi (full ny vector, int phi^2 dy = 1), Lambda, beta_disc,
    beta_plain, n_eff, n_guided_detected.
    """
    h, k0, n0 = geo["h"], geo["k0"], geo["n0"]
    if n_bg_col is None:
        n_bg_col = geo["n2_bg"][1:-1, geo["nx"] // 2]
    Ty = _plain_d2(geo["y"], h) + sp.diags(k0 ** 2 * n_bg_col)
    sigma = (k0 * geo["ns"]) ** 2 * (1.0 - 1e-6)
    n_req = min(8, geo["ny"] - 2)
    vals, vecs = eigsh(Ty.tocsc(), k=n_req, sigma=sigma, which="LM", tol=1e-14,
                       maxiter=80000)
    order = np.argsort(vals)[::-1]
    vals, vecs = vals[order], vecs[:, order]
    beta_plain = np.sqrt(np.clip(vals, 0.0, None))
    arg = 1.0 - vals * h * h / 2.0
    beta_disc = np.full_like(vals, np.nan)
    ok = (arg > -1.0) & (arg < 1.0)
    beta_disc[ok] = np.arccos(arg[ok]) / h
    # the TRUE guided criterion is sqrt(Lambda)/k0 > n0 (not the acos-mapped beta)
    guided = (beta_plain / k0 > n0 + 1e-6) & (beta_plain / k0 < geo["ns"] + 1e-6)
    if verbose:
        print("   corrected Ty: Lambda", np.round(vals, 6))
        print("   beta_disc/k0", np.round(beta_disc / k0, 6))
        print("   n_guided_detected", int(guided.sum()), "of", n_req)
    if guided.sum() < 1:
        raise RuntimeError("no guided transverse mode found")
    i = int(np.where(guided)[0][0])
    phi_full = np.zeros(geo["ny"])
    p = vecs[:, i]
    phi_full[1:-1] = p / math.sqrt(float(np.sum(p ** 2)) * h)
    return {"phi": phi_full, "Lambda": float(vals[i]),
            "beta_disc": float(beta_disc[i]), "beta_plain": float(beta_plain[i]),
            "n_eff": float(beta_plain[i] / k0), "n_eff_disc": float(beta_disc[i] / k0),
            "n_guided_detected": int(guided.sum()), "all_vals": vals}


def solve_crossing_corrected(optics, theta_deg, grid_um=None, d_port_um=10.0,
                             pml_um=5.0, pml_strength=None, max_unknowns=420_000,
                             keep_fields=True, verbose=False, bounds=None,
                             cross_scale=1.0):
    """Full 2-D scattered-field FDFD with a *correct* discrete incident mode.

    cross_scale : scales the crossing-guide index perturbation (n^2 - n_bg^2)
                  linearly; used for linearity / numerical-floor controls.
    """
    t0 = time.time()
    cfg = CONFIG["crossing_model"]
    grid_um = float(grid_um if grid_um is not None else cfg["grid_um"])
    pml_strength = float(pml_strength if pml_strength is not None
                         else cfg["pml_strength"])
    geo = _build_geometry(optics, theta_deg, grid_um, d_port_um, pml_um,
                          max_unknowns, bounds=bounds)
    h, x, y, nx, ny = geo["h"], geo["x"], geo["y"], geo["nx"], geo["ny"]
    x_min, x_max, y_min, y_max = geo["bounds"]
    Lx, Ly = geo["Lx"], geo["Ly"]
    k0, n2, n2_bg, n0 = geo["k0"], geo["n2"], geo["n2_bg"], geo["n0"]
    if cross_scale != 1.0:
        n2 = n2_bg + float(cross_scale) * (n2 - n2_bg)
        geo["n2"] = n2

    im = correct_incident_mode(geo, verbose=verbose)
    phi, beta = im["phi"], im["beta_disc"]
    psi_inc = np.exp(1j * beta * x)[None, :] * phi[:, None]

    sx = _pml_asym(x, x_min, x_max, pml_um, pml_strength)
    sy = _pml_asym(y, y_min, y_max, pml_um, pml_strength)
    Dx = _stretched_d2(x, sx, h)
    Dy = _stretched_d2(y, sy, h)
    nxi, nyi = nx - 2, ny - 2
    A = (sp.kron(sp.eye(nyi, format="csr"), Dx, format="csr")
         + sp.kron(Dy, sp.eye(nxi, format="csr"), format="csr"))
    sub = n2[1:-1, 1:-1]
    A = (A + sp.diags(k0 ** 2 * sub.ravel())).tocsc()
    delta = sub - n2_bg[1:-1, 1:-1]
    rhs = (-k0 ** 2 * delta * psi_inc[1:-1, 1:-1]).ravel().astype(complex)
    lu = splu(A)
    psi_s = lu.solve(rhs).reshape(nyi, nxi)
    full_s = np.zeros((ny, nx), dtype=complex)
    full_s[1:-1, 1:-1] = psi_s
    psi_tot = psi_inc + full_s

    # exact discrete power injected by the source  P_src = Im[sum psi_s^* rhs] h^2
    P_src = float(np.imag(np.vdot(psi_s.ravel(), rhs)) * h * h)
    # exact discrete outgoing flux of the incident mode (per unit |a|^2)
    flux_inc = math.sin(beta * h) / h

    out = dict(theta=float(theta_deg), grid=h, d_port=float(d_port_um),
               pml=float(pml_um), strength=float(pml_strength),
               domain=(float(nx), float(ny)), domain_um=(float(2 * Lx), float(2 * Ly)),
               Lx=float(Lx), Ly=float(Ly), unknowns=int((nx - 2) * (ny - 2)),
               n_eff_disc=im["n_eff_disc"], n_eff=im["n_eff"],
               beta_disc=beta, n_slab=geo["ns"],
               n_guided_detected=im["n_guided_detected"],
               P_src=P_src, flux_inc=flux_inc,
               P_src_norm=P_src / flux_inc, runtime=time.time() - t0,
               x=x, y=y, psi_s=full_s, psi_inc=psi_inc, phi=phi,
               bounds=geo["bounds"])
    return out


# --------------------------------------------------------------------- caching
def corrected_cache_path(theta, grid, d_port, pml, strength, extra=""):
    return AL.CACHE / (f"corr_t{theta:g}_h{grid:g}_dp{d_port:g}_pml{pml:g}"
                       f"_s{strength:g}{extra}.npz")


def solve_corrected_cached(optics, theta, grid=0.15, d_port=10.0, pml=5.0,
                           strength=3.0, max_unknowns=420_000, tag="", force=False):
    p = corrected_cache_path(theta, grid, d_port, pml, strength, tag)
    if p.exists() and not force:
        d = np.load(p)
        return {k: (d[k] if d[k].ndim else float(d[k])) for k in d.files}, p
    r = solve_crossing_corrected(optics, theta, grid_um=grid, d_port_um=d_port,
                                 pml_um=pml, pml_strength=strength,
                                 max_unknowns=max_unknowns)
    np.savez_compressed(
        p,
        theta=np.float64(r["theta"]), grid=np.float64(r["grid"]),
        d_port=np.float64(r["d_port"]), pml=np.float64(r["pml"]),
        strength=np.float64(r["strength"]),
        domain=np.asarray(r["domain"], float), domain_um=np.asarray(r["domain_um"]),
        Lx=np.float64(r["Lx"]), Ly=np.float64(r["Ly"]),
        bounds=np.asarray(r["bounds"], float),
        unknowns=np.int64(r["unknowns"]), n_eff_disc=np.float64(r["n_eff_disc"]),
        n_eff=np.float64(r["n_eff"]), beta_disc=np.float64(r["beta_disc"]),
        n_slab=np.float64(r["n_slab"]),
        n_guided_detected=np.int64(r["n_guided_detected"]),
        P_src=np.float64(r["P_src"]), flux_inc=np.float64(r["flux_inc"]),
        P_src_norm=np.float64(r["P_src_norm"]),
        runtime=np.float64(np.float64(r["runtime"])),
        x=r["x"], y=r["y"], psi_s=r["psi_s"], psi_inc=r["psi_inc"], phi=r["phi"])
    d = np.load(p)
    return {k: (d[k] if d[k].ndim else float(d[k])) for k in d.files}, p


def local_guided_modes(x, y, h, k0, ns, n0, w, max_modes=4):
    """All guided transverse modes of the EIM 2-level background structure.

    The EIM slab (core index n_slab, width w) supports floor(2V/pi)+1 guided
    modes; at the reference optics V=2.78 -> 2 (even fundamental + odd TE1).
    Returns list of dicts {phi, beta, Lambda, n_eff, nodes} sorted by Lambda desc.
    """
    from scipy.sparse.linalg import eigsh
    y = np.asarray(y)
    ny = y.size
    n2c = np.where(np.abs(y[1:-1]) <= w / 2.0, ns ** 2, n0 ** 2)
    Ty = _plain_d2(y, h) + sp.diags(k0 ** 2 * n2c)
    sigma = (k0 * ns) ** 2 * (1.0 - 1e-6)
    vals, vecs = eigsh(Ty.tocsc(), k=min(max_modes + 2, ny - 2), sigma=sigma,
                       which="LM", tol=1e-14, maxiter=80000)
    order = np.argsort(vals)[::-1]
    out = []
    light = (k0 * n0) ** 2
    for j in order:
        lam = float(vals[j])
        if lam <= light + 1e-9:
            continue
        p = vecs[:, j]
        phi = np.zeros(ny)
        phi[1:-1] = p / math.sqrt(float(np.sum(p ** 2)) * h)
        arg = 1.0 - lam * h * h / 2.0
        if not (-1.0 < arg < 1.0):
            continue
        out.append({"phi": phi, "Lambda": lam,
                    "beta": float(math.acos(arg) / h),
                    "n_eff": float(math.sqrt(lam) / k0),
                    "nodes": int(np.sum(np.sign(phi[1:-1]) != np.sign(phi[2:])))}
                   )
    return out


# ------------------------------------------------------- independent port analysis
def _transverse_projection(field, col, y, phi, h):
    """V(x) = <field(:,col), phi> = sum_j field_j phi_j h  (discrete inner product)."""
    return np.sum(field[1:-1, col] * phi[1:-1]) * h


def _two_plane_amplitudes(Vs, xs, beta):
    """Fit V(x) = a+ exp(i beta x) + a- exp(-i beta x) by linear least squares."""
    E = np.column_stack([np.exp(1j * beta * xs), np.exp(-1j * beta * xs)])
    sol, *_ = np.linalg.lstsq(E, np.asarray(Vs, complex), rcond=None)
    return complex(sol[0]), complex(sol[1])


def exact_discrete_flux_x(field, i_from, i_to):
    """h * sum_j Im[ psi*_{i+1/2} (psi_{i+1}-psi_i) ] over the face between
    columns i_from and i_to (must be adjacent).  Uses the 5-point FV flux."""
    a = field[1:-1, i_from]
    b = field[1:-1, i_to]
    half = 0.5 * (np.conj(a) + np.conj(b))
    return float(np.sum(np.imag(half * (b - a))))


def exact_discrete_flux_y(field, j_from, j_to):
    a = field[j_from, 1:-1]
    b = field[j_to, 1:-1]
    half = 0.5 * (np.conj(a) + np.conj(b))
    return float(np.sum(np.imag(half * (b - a))))


def port_analysis(d, optics, theta_deg=None, pml=None, u_list=None,
                  half_width_um=14.0, ds=0.04, verbose=False):
    """Fully independent 4-arm port analysis of a solved crossing.

    Power convention: the incident mode (amplitude 1) carries the exact discrete
    flux  F_inc = h * sum_j Im[psi*_{i+1/2}(psi_{i+1}-psi_i)] = sin(beta h)
    across a grid face.  All guided powers are reported as |a|^2 (ratio to the
    incident modal power; for one and the same mode this equals P/P_inc exactly
    because both carry the same beta).  Radiation/total scattered power is
    obtained from the exact source-power identity  P_src = Im[<psi_s, rhs>] h^2.
    """
    th = math.radians(float(d["theta"] if theta_deg is None else theta_deg))
    x, y = np.asarray(d["x"]), np.asarray(d["y"])
    psi_s, psi_inc = np.asarray(d["psi_s"]), np.asarray(d["psi_inc"])
    phi = np.asarray(d["phi"])
    beta = float(d["beta_disc"])
    h = float(d["grid"])
    Lx, Ly = float(d["Lx"]), float(d["Ly"])
    if "bounds" in d:
        b = d["bounds"]
        x_min, x_max, y_min, y_max = (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
    else:
        x_min, x_max, y_min, y_max = -Lx, Lx, -Ly, Ly
    pml = float(d["pml"] if pml is None else pml)
    w = float(optics["core_width_um"])
    cos_t, sin_t = math.cos(th), math.sin(th)
    u_hat = np.array([cos_t, sin_t])
    n_hat1 = np.array([1.0, 0.0])

    phi2 = float(np.sum(phi ** 2) * h)          # == 1 by construction
    psi_tot = psi_inc + psi_s

    # ---------------- through arm: exact discrete flux + 2-plane modal amplitudes
    x_hi = x_max - pml - 3.0 * h
    x_lo = x_min + pml + 3.0 * h
    i_hi = int(round((x_hi - x[0]) / h))
    i_lo = int(round((x_lo - x[0]) / h))
    flux_right = exact_discrete_flux_x(psi_tot, i_hi, i_hi + 1)   # outward +x
    flux_left = -exact_discrete_flux_x(psi_tot, i_lo, i_lo + 1)   # outward -x
    flux_left_inc = -exact_discrete_flux_x(psi_inc, i_lo, i_lo + 1)
    # exact discrete flux of psi_s through the four faces just inside the PML
    j_lo = int(round((y_min + pml + 2.0 * h - y[0]) / h))
    j_hi = int(round((y_max - pml - 2.0 * h - y[0]) / h))
    i_lo2 = int(round((x_min + pml + 2.0 * h - x[0]) / h))
    i_hi2 = int(round((x_max - pml - 2.0 * h - x[0]) / h))
    sflux = {
        "right": exact_discrete_flux_x(psi_s, i_hi2, i_hi2 + 1),
        "left": -exact_discrete_flux_x(psi_s, i_lo2, i_lo2 + 1),
        "top": exact_discrete_flux_y(psi_s, j_hi, j_hi + 1),
        "bottom": -exact_discrete_flux_y(psi_s, j_lo, j_lo + 1),
    }
    F_inc = float(np.sin(beta * h) / h)          # flux of unit-amplitude mode (Sigma J units)

    # two-plane (actually 4-plane) LSQ decomposition at the right port
    dx_probe = [1, 3, 5, 7]                      # in cells, inward from i_hi
    xs_p = np.array([x[i_hi - k] for k in dx_probe])
    Vs_p = np.array([_transverse_projection(psi_tot, i_hi - k, y, phi, h) for k in dx_probe])
    a_fwd, a_bwd = _two_plane_amplitudes(Vs_p, xs_p, beta)
    R = float(abs(a_bwd) ** 2)
    # left port: only reflected/backward wave (psi_s)
    xs_l = np.array([x[i_lo + k] for k in dx_probe])
    Vs_l = np.array([_transverse_projection(psi_s, i_lo + k, y, phi, h) for k in dx_probe])
    al_fwd, al_bwd = _two_plane_amplitudes(Vs_l, xs_l, beta)
    R_left = float(abs(al_bwd) ** 2)
    R_right = R
    R_tot = 0.5 * (R_left + R_right)

    # ---------------- crossed-guide arms: independent cut, mode projection
    # A valid port cut must lie (i) inside the physical box and (ii) outside the
    # merged coupling region: guide separation d = u*sin(theta) > 1.2 w.
    if u_list is None:
        m_bnd = pml + 3.0 * h
        hw = float(half_width_um)
        cand = []
        if cos_t > 1e-9:
            cand.append((x_max - m_bnd - hw * abs(sin_t)) / cos_t)
        if sin_t > 1e-9:
            cand.append((y_max - m_bnd - hw * abs(cos_t)) / sin_t)
        u_geo = float(min(cand)) if cand else float("nan")
        d_min = 1.15 * w                       # outside the core-overlap region
        u_min = d_min / max(sin_t, 1e-9)
        u_max = u_geo
        if not np.isfinite(u_max) or u_max <= 1.1 * u_min:
            u_max = max(u_min * 1.1, 0.9 * u_geo if np.isfinite(u_geo) else 4 * w)
        u_list = [u_min + f * (u_max - u_min) for f in (0.5, 0.75, 1.0)]
        u_list = [float(min(u, u_max)) for u in u_list]
    tt = np.array([-u_hat[1], u_hat[0]])
    s = np.arange(-half_width_um, half_width_um + 1e-12, ds)

    def cut_amp(field, p0, nh, sgn):
        tt_ = np.array([-nh[1], nh[0]])
        pts = np.asarray(p0, float)[None, :] + s[:, None] * tt_[None, :]
        ok = ((pts[:, 0] > x[0] + 2 * h) & (pts[:, 0] < x[-1] - 2 * h)
              & (pts[:, 1] > y[0] + 2 * h) & (pts[:, 1] < y[-1] - 2 * h))
        ss, pp = s[ok], pts[ok]
        if ss.size < 8:
            return None
        vals = AL.interp_bilinear(field, x, y, pp[:, 0], pp[:, 1])
        pr = np.interp(ss, y, phi, left=0.0, right=0.0)
        den = float(np.trapezoid(pr ** 2, ss))
        a_raw = complex(np.trapezoid(vals * pr, ss))
        u = float(np.asarray(p0, float) @ nh)
        a = a_raw / den * np.exp(-1j * sgn * beta * u)
        return {"a": a, "amp": abs(a), "power": abs(a) ** 2, "den": den,
                "s_min": float(ss[0]), "s_max": float(ss[-1]), "n": int(ss.size)}

    arms = {}
    for lbl, uu, nh in (("cross_plus", +1.0, u_hat), ("cross_minus", -1.0, -u_hat)):
        rows = []
        for up in u_list:
            p0 = uu * up * u_hat
            r = cut_amp(psi_s, p0, nh, +1)
            if r is not None:
                r["u"] = float(up)
                rows.append(r)
        arms[lbl] = rows
    # very first cut is nearest the junction (most contaminated by radiation);
    # the LAST cut is the port we quote
    def last_pow(rows):
        return rows[-1]["power"] if rows else float("nan")
    T_cp, T_cm = last_pow(arms["cross_plus"]), last_pow(arms["cross_minus"])
    T_cross = T_cp + T_cm
    T_through = float(abs(a_fwd) ** 2)
    P_src_norm = float(d["P_src"]) / F_inc
    d_fwd = complex(a_fwd) - 1.0
    ext = 1.0 - T_through + abs(d_fwd) ** 2          # extinction = -2 Re(d) - ...
    rad = 1.0 - T_through - R_tot - T_cross
    rad2 = P_src_norm - abs(d_fwd) ** 2 - R_tot - T_cross
    return {
        "theta_deg": float(d["theta"]), "beta": beta, "h": h,
        "F_inc": F_inc, "flux_right": flux_right, "flux_left": flux_left,
        "flux_left_inc": flux_left_inc, "P_src": float(d["P_src"]),
        "P_src_norm": P_src_norm,
        "a_fwd": a_fwd, "a_bwd": a_bwd, "d_fwd": d_fwd,
        "T_through": T_through, "R": R_tot, "R_left": R_left, "R_right": R_right,
        "T_cross_plus": T_cp, "T_cross_minus": T_cm, "T_cross": T_cross,
        "radiation": rad, "radiation_alt": rad2,
        "extinction": ext, "extinction_minus_Psrc": ext - P_src_norm,
        "energy_1_minus_sum": 1.0 - (T_through + R_tot + T_cross + rad),
        "flux_balance": (flux_left + flux_right) / F_inc,
        "flux_minus_src": (flux_left + flux_right) / F_inc - P_src_norm,
        "sflux": sflux,
        "sflux_sum_norm": sum(sflux.values()) / F_inc,
        "sflux_minus_src": sum(sflux.values()) / F_inc - P_src_norm,
        "arms": arms,
        "phi2": phi2,
        "u_list": [float(u) for u in u_list],
        "separation_at_port_um": float(u_list[-1] * math.sin(th)),
        "check_fluxright": flux_right / F_inc,
    }



def port_analysis2(d, optics, theta_deg=None, pml=None, u_list=None,
                   half_width_um=14.0, ds=0.04, modes=None, verbose=False):
    """Independent multi-mode (all guided EIM modes) 4-arm port analyser.

    Power convention: incident fundamental amplitude 1 carries the exact discrete
    flux F_inc = sin(beta_1 h)/h; guided powers are ratios to that flux, i.e.
    P/P_inc = (sin(beta_j h)/sin(beta_1 h)) |a_j|^2.
    Outputs per-arm/per-mode powers, through/reflection decomposition, exact
    source power P_src and the closed energy balance
        1 = T_through + R + T_cross + radiation.
    """
    th = math.radians(float(d["theta"] if theta_deg is None else theta_deg))
    x, y = np.asarray(d["x"]), np.asarray(d["y"])
    psi_s, psi_inc = np.asarray(d["psi_s"]), np.asarray(d["psi_inc"])
    h = float(d["grid"])
    k0 = 2.0 * math.pi / (float(optics["wavelength_nm"]) * 1e-3)
    n0 = float(optics["n_clad"])
    w = float(optics["core_width_um"])
    ns = float(d["n_slab"])
    Lx, Ly = float(d["Lx"]), float(d["Ly"])
    if "bounds" in d:
        b = d["bounds"]
        x_min, x_max, y_min, y_max = (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
    else:
        x_min, x_max, y_min, y_max = -Lx, Lx, -Ly, Ly
    pml = float(d["pml"] if pml is None else pml)
    if modes is None:
        modes = local_guided_modes(x, y, h, k0, ns, n0, w)
    if not modes:
        raise RuntimeError("no guided transverse mode")
    beta1 = modes[0]["beta"]
    wts = [math.sin(m["beta"] * h) / math.sin(beta1 * h) for m in modes]
    psi_tot = psi_s + psi_inc
    F_inc = math.sin(beta1 * h) / h
    cos_t, sin_t = math.cos(th), math.sin(th)
    u_hat = np.array([cos_t, sin_t])

    # ---------------------------------------------------------- through port
    x_hi = x_max - pml - 3.0 * h
    x_lo = x_min + pml + 3.0 * h
    i_hi = int(round((x_hi - x[0]) / h))
    i_lo = int(round((x_lo - x[0]) / h))
    dx_probe = [1, 3, 5, 7, 9, 11]
    xs_p = np.array([x[i_hi - k] for k in dx_probe])
    xs_l = np.array([x[i_lo + k] for k in dx_probe])
    T_fwd_modes, R_modes, a_fwd_modes = [], [], []
    for m, wt in zip(modes, wts):
        Vs = np.array([_transverse_projection(psi_tot, i_hi - k, y, m["phi"], h)
                       for k in dx_probe])
        ap, am = _two_plane_amplitudes(Vs, xs_p, m["beta"])
        a_fwd_modes.append(ap)
        T_fwd_modes.append(wt * abs(ap) ** 2)
        Vs_l = np.array([_transverse_projection(psi_s, i_lo + k, y, m["phi"], h)
                         for k in dx_probe])
        alp, alm = _two_plane_amplitudes(Vs_l, xs_l, m["beta"])
        R_modes.append(wt * abs(alm) ** 2)
    T_through = float(sum(T_fwd_modes))
    T_through_fund = float(T_fwd_modes[0])
    T_through_higher = float(T_through - T_through_fund)
    R = float(sum(R_modes))
    d_fwd = complex(a_fwd_modes[0]) - 1.0

    # exact discrete flux diagnostics
    j_lo = int(round((y_min + pml + 2.0 * h - y[0]) / h))
    j_hi = int(round((y_max - pml - 2.0 * h - y[0]) / h))
    i_lo2 = int(round((x_min + pml + 2.0 * h - x[0]) / h))
    i_hi2 = int(round((x_max - pml - 2.0 * h - x[0]) / h))
    sflux = {
        "right": exact_discrete_flux_x(psi_s, i_hi2, i_hi2 + 1),
        "left": -exact_discrete_flux_x(psi_s, i_lo2, i_lo2 + 1),
        "top": exact_discrete_flux_y(psi_s, j_hi, j_hi + 1),
        "bottom": -exact_discrete_flux_y(psi_s, j_lo, j_lo + 1),
    }
    flux_right = exact_discrete_flux_x(psi_tot, i_hi, i_hi + 1)
    flux_left = -exact_discrete_flux_x(psi_tot, i_lo, i_lo + 1)

    # ------------------------------------------------------- crossed-guide arms
    if u_list is None:
        m_bnd = pml + 3.0 * h
        hw = float(half_width_um)
        cand = []
        if cos_t > 1e-9:
            cand.append((x_max - m_bnd - hw * abs(sin_t)) / cos_t)
        if sin_t > 1e-9:
            cand.append((y_max - m_bnd - hw * abs(cos_t)) / sin_t)
        u_geo = float(min(cand)) if cand else float("nan")
        u_min = 1.15 * w / max(sin_t, 1e-9)
        u_max = u_geo
        if not np.isfinite(u_max) or u_max <= 1.1 * u_min:
            u_max = max(u_min * 1.1, 0.9 * u_geo if np.isfinite(u_geo) else 4 * w)
        u_list = [float(min(u_min + f * (u_max - u_min), u_max))
                  for f in (0.5, 0.75, 1.0)]
    s = np.arange(-half_width_um, half_width_um + 1e-12, ds)

    def cut_amps(field, p0, nh):
        tt_ = np.array([-nh[1], nh[0]])
        pts = np.asarray(p0, float)[None, :] + s[:, None] * tt_[None, :]
        ok = ((pts[:, 0] > x[0] + 2 * h) & (pts[:, 0] < x[-1] - 2 * h)
              & (pts[:, 1] > y[0] + 2 * h) & (pts[:, 1] < y[-1] - 2 * h))
        ss, pp = s[ok], pts[ok]
        if ss.size < 8:
            return None
        vals = AL.interp_bilinear(field, x, y, pp[:, 0], pp[:, 1])
        u = float(np.asarray(p0, float) @ nh)
        out = []
        for m in modes:
            pr = np.interp(ss, y, m["phi"], left=0.0, right=0.0)
            den = float(np.trapezoid(pr ** 2, ss))
            a_raw = complex(np.trapezoid(vals * pr, ss))
            out.append(a_raw / den * np.exp(-1j * m["beta"] * u))
        return out

    arms = {}
    for lbl, uu, nh in (("cross_plus", +1.0, u_hat),
                        ("cross_minus", -1.0, -u_hat)):
        rows = []
        for up in u_list:
            p0 = uu * up * u_hat
            amps = cut_amps(psi_s, p0, nh)
            if amps is None:
                continue
            powers = [wt * abs(a) ** 2 for wt, a in zip(wts, amps)]
            rows.append({"u": float(up), "amps": amps, "powers": powers,
                         "power": float(sum(powers)),
                         "power_fund": float(powers[0]),
                         "amp": abs(amps[0])})
        arms[lbl] = rows
    cp = arms["cross_plus"][-1] if arms["cross_plus"] else None
    cm = arms["cross_minus"][-1] if arms["cross_minus"] else None
    T_cross = float((cp["power"] if cp else 0.0) + (cm["power"] if cm else 0.0))
    T_cross_fund = float((cp["power_fund"] if cp else 0.0)
                         + (cm["power_fund"] if cm else 0.0))
    T_cross_higher = float(T_cross - T_cross_fund)
    P_src_norm = float(d["P_src"]) / F_inc
    radiation = 1.0 - T_through - R - T_cross
    ext = 1.0 - T_through + abs(d_fwd) ** 2
    out = {
        "theta_deg": float(d["theta"]), "h": h, "beta": beta1, "F_inc": F_inc,
        "modes": [{"n_eff": m["n_eff"], "beta": m["beta"], "nodes": m["nodes"],
                   "weight": wt} for m, wt in zip(modes, wts)],
        "T_through": T_through, "T_through_fund": T_through_fund,
        "T_through_higher": T_through_higher,
        "R": R, "R_modes": R_modes, "T_fwd_modes": T_fwd_modes,
        "a_fwd": complex(a_fwd_modes[0]), "d_fwd": d_fwd,
        "T_cross": T_cross, "T_cross_fund": T_cross_fund,
        "T_cross_higher": T_cross_higher,
        "T_cross_plus": float(cp["power"] if cp else 0.0),
        "T_cross_minus": float(cm["power"] if cm else 0.0),
        "T_cross_plus_fund": float(cp["power_fund"] if cp else 0.0),
        "T_cross_minus_fund": float(cm["power_fund"] if cm else 0.0),
        "radiation": radiation, "P_src": float(d["P_src"]),
        "P_src_norm": P_src_norm,
        "extinction": ext, "extinction_minus_Psrc": ext - P_src_norm,
        "energy_1_minus_sum": 1.0 - (T_through + R + T_cross + radiation),
        "sflux": sflux,
        "sflux_sum_norm": sum(sflux.values()) / F_inc,
        "sflux_minus_src": sum(sflux.values()) / F_inc - P_src_norm,
        "flux_right": flux_right, "flux_left": flux_left,
        "flux_left_div_Finc": flux_left / F_inc,
        "flux_right_div_Finc": flux_right / F_inc,
        "arms": arms,
        "u_list": [float(u) for u in u_list],
        "separation_at_port_um": float(u_list[-1] * math.sin(th)),
        "half_width_um": float(half_width_um),
    }
    return out


def discrete_box_flux(field, x, y, h, i0, i1, j0, j1):
    """Net outward discrete flux of `field` through the rectangle
    [i0,i1]x[j0,j1] (interior node indices on the (ny,nx) grid)."""
    tot = 0.0
    # x-faces
    for i, dirn in ((i1, +1), (i0, -1)):
        a = field[:, i]
        b = field[:, i + dirn]
        half = 0.5 * (np.conj(a) + np.conj(b))
        tot += dirn * float(np.sum(np.imag(half * (b - a)))) / h * h
    for j, dirn in ((j1, +1), (j0, -1)):
        a = field[j, :]
        b = field[j + dirn, :]
        half = 0.5 * (np.conj(a) + np.conj(b))
        tot += dirn * float(np.sum(np.imag(half * (b - a)))) / h * h
    return tot
