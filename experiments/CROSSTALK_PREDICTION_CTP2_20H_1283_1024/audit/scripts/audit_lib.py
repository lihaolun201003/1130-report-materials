"""Shared utilities for the CTP-1.0 audit.

READ-ONLY w.r.t. the legacy experiment.  Imports the legacy ``src`` package
from its original location (never edits it), and provides an INDEPENDENT
port/flux analyser for 2-D scalar Helmholtz fields.

Conventions
-----------
* time dependence exp(-i w t); a forward wave along +x is psi = a phi(y) exp(+i beta x)
* scalar 2-D field, physical time-averaged power through a line with unit normal n:
      P = (1/(2 w mu0)) Im[ int psi^* d psi/dn dl ]
  For a mode with int phi^2 dl = 1 this is beta |a|^2 / (2 w mu0).
  We work in units 2 w mu0 = 1 exactly (ratios are what matter).
* all lengths in um unless a name says mm
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CTP2 = HERE.parents[1]                       # .../CROSSTALK_PREDICTION_CTP2_20H_1283_1024
LEGACY = CTP2.parent / "CROSSTALK_PREDICTION_20H_1283_1024"
AUDIT = CTP2 / "audit"
CACHE = CTP2 / "cache" / "audit"
CACHE.mkdir(parents=True, exist_ok=True)
AUDIT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- legacy import
if str(LEGACY) not in sys.path:
    sys.path.insert(0, str(LEGACY))

import src  # noqa: E402
_src_file = Path(src.__file__).resolve()
assert _src_file.is_relative_to(LEGACY.resolve()), f"wrong src imported: {_src_file}"

from src.config import CONFIG, reference_optics  # noqa: E402
from src.crossing import (CrossingResult, _domain_for_angle, _index_grid_2d,  # noqa: E402
                          _pml, _stretched_d2, _plain_d2, _bilinear,
                          crossing_born, crossing_cmt, solve_crossing)
from src.modes import (EffectiveIndex2D, effective_index_model, index_grid,  # noqa: E402
                       solve_modes, solve_modes_graded)
from src import coupling as legacy_coupling  # noqa: E402


# --------------------------------------------------------------------- helpers
def jload(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def jdump(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, default=_np_default)


def write_csv(path, rows, fieldnames=None):
    """Write a list of dicts to CSV (union of keys if fieldnames is None)."""
    import csv
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    if fieldnames is None:
        keys = []
        for r in rows:
            for k in r:
                if k not in keys:
                    keys.append(k)
        fieldnames = keys
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _np_default(o):
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, Path):
        return str(o)
    raise TypeError(type(o))


def beam() -> tuple[dict, EffectiveIndex2D]:
    opt = reference_optics()
    eim = effective_index_model(opt)
    return opt, eim


# ------------------------------------------------------- 1-D transverse modes
def transverse_modes(n2_col: np.ndarray, h: float, k0: float, n_modes: int = 6,
                     tol: float = 1e-14, sigma_offset: float = 1e-6):
    """Plain (no PML) Dirichlet transverse eigenproblem, same stencil as legacy.

    Returns (Lambda, phi(n_int, m), beta_disc, beta_plain) where
    beta_disc = arccos(1 - Lambda h^2/2)/h  (exact discrete dispersion,
    the propagation constant for which psi=phi(y) exp(i beta x) solves the
    5-point discrete Helmholtz equation), and beta_plain=sqrt(Lambda).
    """
    import scipy.sparse as sp
    from scipy.sparse.linalg import eigsh
    n = len(n2_col)
    m = n - 2
    main = -2.0 * np.ones(m) / h ** 2
    off = np.ones(m - 1) / h ** 2
    A = sp.diags([main, off, off], [0, 1, -1], format="csc")
    A = (A + sp.diags(k0 ** 2 * n2_col[1:-1])).tocsc()
    sigma = float(np.max(n2_col)) * k0 ** 2 * (1.0 - sigma_offset)
    vals, vecs = eigsh(A, k=n_modes, sigma=sigma, which="LM", tol=tol, maxiter=60000)
    order = np.argsort(vals)[::-1]
    vals, vecs = vals[order], vecs[:, order]
    beta_plain = np.sqrt(np.clip(vals, 0.0, None))
    arg = 1.0 - vals * h * h / 2.0
    ok = (arg > -1.0) & (arg < 1.0)
    beta_disc = np.full_like(vals, np.nan)
    beta_disc[ok] = np.arccos(arg[ok]) / h
    return vals, vecs, beta_disc, beta_plain


def interp_bilinear(field, x, y, xq, yq):
    """Bilinear interpolation of a complex 2-D array field[j,i] on grid (x,y)."""
    hx, hy = x[1] - x[0], y[1] - y[0]
    fx = np.clip((np.asarray(xq) - x[0]) / hx, 0.0, len(x) - 1.000001)
    fy = np.clip((np.asarray(yq) - y[0]) / hy, 0.0, len(y) - 1.000001)
    i0 = np.clip(np.floor(fx).astype(int), 0, len(x) - 2)
    j0 = np.clip(np.floor(fy).astype(int), 0, len(y) - 2)
    tx = fx - i0
    ty = fy - j0
    return (field[j0, i0] * (1 - tx) * (1 - ty) + field[j0, i0 + 1] * tx * (1 - ty)
            + field[j0 + 1, i0] * (1 - tx) * ty + field[j0 + 1, i0 + 1] * tx * ty)


# ---------------------------------------------------------------- port objects
def line_profile(phi_grid: np.ndarray, y_grid: np.ndarray, s: np.ndarray) -> np.ndarray:
    """Mode profile evaluated at transverse offsets s.  phi_grid is real, on y_grid."""
    return np.interp(s, y_grid, phi_grid, left=0.0, right=0.0)


def analyse_port(field_total: np.ndarray, x, y, prof, beta, p0, n_hat, s_arr,
                 phase_sign=+1, bilinear=None) -> dict:
    """Independent modal-flux / amplitude analyser on one transverse cut.

    field_total : complex 2-D total field on grid (x,y)
    prof        : function s -> real mode profile (interp of phi)
    beta        : propagation constant used for the phase reference
    p0          : (x0,y0) point on the guide axis at the cut
    n_hat       : unit normal of the cut (direction of positive power flow)
    s_arr       : sampling offsets along the cut, relative to p0 along the
                  perpendicular direction t_hat = (-n_y, n_x)
    phase_sign  : +1 if exp(+i beta u) is the outgoing wave along n_hat
    Returns modal amplitude/power and the continuum flux through the cut.

    The phase reference is exp(phase_sign * i*beta*u) where u is the coordinate
    ALONG the guide (n_hat), evaluated at the cut: u = p0 . n_hat.  The mode
    amplitude is a = int field * prof ds / int prof^2 ds * exp(-i phase_sign beta u).
    """
    t_hat = np.array([-n_hat[1], n_hat[0]])
    pts = np.asarray(p0)[None, :] + s_arr[:, None] * t_hat[None, :]
    vals = bilinear(field_total, x, y, pts[:, 0], pts[:, 1])
    prof_s = prof(s_arr)
    den = float(np.trapezoid(prof_s ** 2, s_arr))
    a = float(np.trapezoid(vals * prof_s, s_arr) / den)
    u = float(np.asarray(p0)[0] * n_hat[0] + np.asarray(p0)[1] * n_hat[1])
    a_reph = a * np.exp(-1j * phase_sign * beta * u)
    # continuum flux through the cut: P = Im[ int psi^* dpsi/dn ds ]
    # derivative along n_hat by central differences on a fine sampled grid
    ds_f = min(abs(s_arr[1] - s_arr[0]), 0.05)
    s_f = np.arange(s_arr[0], s_arr[-1] + 1e-12, ds_f)
    P_f = np.asarray(p0)[None, :] + s_f[:, None] * t_hat[None, :]
    d = 0.03
    f0 = bilinear(field_total, x, y, P_f[:, 0], P_f[:, 1])
    fp = bilinear(field_total, x, y, P_f[:, 0] + d * n_hat[0], P_f[:, 1] + d * n_hat[1])
    fm = bilinear(field_total, x, y, P_f[:, 0] - d * n_hat[0], P_f[:, 1] - d * n_hat[1])
    dpsi_dn = (fp - fm) / (2 * d)
    flux = float(np.trapezoid(np.imag(np.conj(f0) * dpsi_dn), s_f))
    flux_mode = float(np.imag(np.conj(a_reph) * 0.0))  # placeholder
    # modal flux from the amplitude (analytic): Im[a^* i beta a] int prof^2 = beta|a|^2 den
    flux_mod = phase_sign * beta * abs(a_reph) ** 2 * den
    return {"a": a, "a_reph": a_reph, "power_mod": abs(a_reph) ** 2 * den,
            "flux_cut": flux, "flux_mod": flux_mod, "den": den,
            "n_s": int(s_arr.size), "s_range": (float(s_arr[0]), float(s_arr[-1]))}


# -------------------------------------------------------------- discrete flux
def discrete_flux_x(field: np.ndarray, i_face: int, direction: int = +1) -> float:
    """Exact discrete Poynting flux of the 5-point Laplacian across the face
    between columns i_face and i_face+direction (direction=+1) or
    i_face-1 and i_face (direction=-1).  Unit: Im[psi* dpsi/dx] integrated dy.
    """
    if direction > 0:
        a = field[:, i_face]
        b = field[:, i_face + 1]
    else:
        a = field[:, i_face]
        b = field[:, i_face - 1]
    half = 0.5 * (np.conj(a) + np.conj(b))
    return float(np.sum(np.imag(half * (b - a))))


def discrete_flux_y(field: np.ndarray, j_face: int, direction: int = +1) -> float:
    if direction > 0:
        a = field[j_face, :]
        b = field[j_face + 1, :]
    else:
        a = field[j_face, :]
        b = field[j_face - 1, :]
    half = 0.5 * (np.conj(a) + np.conj(b))
    return float(np.sum(np.imag(half * (b - a))))


# --------------------------------------------------- cached legacy FDFD solves
def crossing_cache_path(theta, grid, d_port, pml, strength, no_cross, tag=""):
    key = f"xsec_t{theta:g}_h{grid:g}_dp{d_port:g}_pml{pml:g}_s{strength:g}_nc{int(no_cross)}{tag}"
    return CACHE / (key + ".npz")


def run_crossing_cached(opt, eim, theta, grid=None, d_port=10.0, pml=5.0,
                        strength=None, no_cross=False, keep_fields=True,
                        max_unknowns=420_000, tag="", force=False):
    """Run the legacy solve_crossing and cache the raw fields (npz)."""
    cfg = CONFIG["crossing_model"]
    grid = float(grid if grid is not None else cfg["grid_um"])
    strength = float(strength if strength is not None else cfg["pml_strength"])
    path = crossing_cache_path(theta, grid, d_port, pml, strength, no_cross, tag)
    if path.exists() and not force:
        d = np.load(path)
        return d, path
    t0 = time.time()
    r = solve_crossing(opt, float(theta), grid_um=grid, d_port_um=float(d_port),
                       eim=eim, pml_um=float(pml), pml_strength=float(strength),
                       max_unknowns=int(max_unknowns), keep_fields=bool(keep_fields),
                       no_cross=bool(no_cross))
    if keep_fields:
        x, y, full, psi_inc, phi = r.fields
    else:
        x = y = full = psi_inc = phi = None
    np.savez_compressed(
        path,
        theta=np.float64(theta), grid=np.float64(r.grid_um),
        T_through=np.float64(r.T_through), T_cross=np.float64(r.T_cross),
        T_loss=np.float64(r.T_loss), energy_error=np.float64(r.energy_error),
        n_slab=np.float64(r.n_slab), n_eff_disc=np.float64(r.n_eff_discrete),
        beta_disc=np.float64(r.beta_discrete), n_guided=np.int64(r.n_guided_modes),
        domain=np.asarray(r.domain_um, float), unknowns=np.int64(r.unknowns),
        x=(x if x is not None else np.zeros(0)),
        y=(y if y is not None else np.zeros(0)),
        full=(full if full is not None else np.zeros(0, complex)),
        psi_inc=(psi_inc if psi_inc is not None else np.zeros(0, complex)),
        phi=(phi if phi is not None else np.zeros(0)),
        runtime=np.float64(time.time() - t0),
    )
    return np.load(path), path


def crossing_eim(opt):
    return effective_index_model(opt)


# ------------------------------------------------------------- misc diagnostics
def db(x):
    return 10.0 * np.log10(max(float(x), 1e-300))


def summarise_legacy_crossing(d) -> dict:
    return {k: (float(d[k]) if np.ndim(d[k]) == 0 else np.asarray(d[k]).tolist())
            for k in d.files if k not in ("x", "y", "full", "psi_inc", "phi")}
