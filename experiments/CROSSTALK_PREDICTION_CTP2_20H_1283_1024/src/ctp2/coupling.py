"""Two-waveguide coupling: kappa(d) for parallel guides, with validation.

Two independent numerical routes plus a validated asymptotic model:

1. **Overlap (perturbation) integral** with the *exact* scalar mode of the
   isolated guide::

       kappa = k0^2 / (2 beta) * int int_D2 (n2^2 - n_clad^2) psi1 psi2 dA
                                    / int int psi1^2 dA

   where ``D2`` is the core of guide 2 only, ``psi2`` is ``psi1`` translated by
   the guide separation.  This is the standard CMT coupling coefficient for
   weak guidance; it is exact to first order in the index perturbation.

2. **Symmetry-reduced supermode splitting** of the *two-guide* cross-section.
   For two identical guides the even/odd supermodes split by
   ``2 kappa = Delta beta``, i.e. ``kappa = pi * Delta n_eff / lambda``
   (in mm^-1 with lambda in mm).  This is only numerically meaningful while
   Delta n_eff is above the eigensolver noise; we measure that noise explicitly
   (repeat with a random perturbation / different shift / different grid
   alignment) instead of trusting the value.

3. **Asymptotic model** for the large-separation tail that neither numerical
   route can resolve: ``kappa(d) = kappa(d_ref) * exp(-gamma * (d - d_ref))``
   with ``gamma = sqrt(beta^2 - (k0 n_clad)^2)`` taken from the mode's own
   eigenvalue (an exact property of the homogeneous cladding, not a fit).

Every returned value carries ``method``, ``validity`` and an uncertainty.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import eigsh

from .optics import (
    ChannelModes, EIM, _frac_inside, _uniform_d2, cell_edges, graded_axis,
    index2d_avg, solve_channel, uniform_axis,
)
from .params import Optics


# ------------------------------------------------------- overlap-integral kappa
def kappa_overlap(modes: ChannelModes, d_um: float, dz_um: float = 0.0,
                  mode: int = 0, order: int = 2) -> dict:
    """CMT overlap integral for two identical parallel guides.

    ``d_um``  : lateral (x) separation of the guide centres
    ``dz_um`` : vertical (y) offset of the guide centres (0 = same plane)

    Returns kappa in mm^-1 plus the integral diagnostics.
    """
    x, y = modes.x, modes.y
    psi = modes.fields[mode]
    k0 = modes.k0
    beta = float(modes.beta[mode])
    n_clad = modes.n_clad
    o = modes.optics

    # guide 2 core mask evaluated on the *same* grid, shifted by (-d, -dz)
    # integral over guide-2 core of (n_core^2-n_clad^2) psi1(r) psi1(r - shift)
    X, Y = np.meshgrid(x, y)
    Xs = X - d_um
    Ys = Y - dz_um
    if o.profile == "step":
        inside = (np.abs(Xs) <= o.core_w_um / 2.0) & (np.abs(Ys) <= o.core_h_um / 2.0)
        dn2 = o.n_core ** 2 - n_clad ** 2
        wgt = np.where(inside, dn2, 0.0)
    else:  # graded: perturbation is the profile itself
        r2 = (2.0 * Xs / o.core_w_um) ** 2 + (2.0 * Ys / o.core_h_um) ** 2
        nc2 = (n_clad + o.delta_n * np.exp(-math.log(2.0) * r2)) ** 2
        wgt = nc2 - n_clad ** 2
    # interpolate psi1 onto the shifted points
    interp = modes.interpolator(mode)
    psi_shift = interp(Xs, Ys)
    dA = np.outer(modes.wy, modes.wx)
    num = float(np.sum(wgt * psi * psi_shift * dA))
    den = float(np.sum(psi ** 2 * dA))
    kappa_per_um = (k0 ** 2 / (2.0 * beta)) * num / den
    # second-order (non-orthogonality / power-correction) estimate
    s_self = float(np.sum(np.where(
        (np.abs(Xs) <= o.core_w_um / 2.0) & (np.abs(Ys) <= o.core_h_um / 2.0), 1, 0)
        * (o.n_core ** 2 - n_clad ** 2) * psi_shift * psi_shift * dA)) / den
    corr = (k0 ** 2 / (2.0 * beta)) * s_self
    return {
        "d_um": float(d_um), "dz_um": float(dz_um), "mode": int(mode),
        "kappa_mm_inv": float(kappa_per_um * 1e3),
        "overlap_integral_per_um2": num,
        "self_overlap_correction_per_um": corr,
        "beta_per_um": beta,
        "gamma_um": float(math.sqrt(max(beta ** 2 - (k0 * n_clad) ** 2, 0.0))),
        "method": "overlap_integral",
    }


# -------------------------------------------------- two-guide supermode kappa
def _half_domain_d2x(nx: int, h: float, mirror: str):
    """Second-derivative matrix on the half domain x = 0, h, ..., (nx-2)h.

    ``mirror='even'`` : unknowns are the nodes x=0..(nx-2)h, Neumann ghost at 0
    ``mirror='odd'``  : unknowns are the nodes x=h..(nx-2)h, Dirichlet at 0
    The outer node x=(nx-1)h is a Dirichlet boundary and is excluded.
    """
    if mirror == "even":
        m = nx - 1
        D = sp.lil_matrix((m, m))
        D[0, 0] = -2.0 / h ** 2
        D[0, 1] = 2.0 / h ** 2
        for j in range(1, m - 1):
            D[j, j - 1] = 1.0 / h ** 2
            D[j, j] = -2.0 / h ** 2
            D[j, j + 1] = 1.0 / h ** 2
        D[m - 1, m - 2] = 1.0 / h ** 2
        D[m - 1, m - 1] = -2.0 / h ** 2
        return D.tocsr()
    m = nx - 2
    D = sp.lil_matrix((m, m))
    for j in range(m):
        D[j, j] = -2.0 / h ** 2
        if j + 1 < m:
            D[j, j + 1] = 1.0 / h ** 2
        if j - 1 >= 0:
            D[j, j - 1] = 1.0 / h ** 2
    return D.tocsr()


def supermode_kappa_3d(optics: Optics, d_um: float, dz_um: float = 0.0,
                       half_pad_um: float = 22.0, step_um: float = 0.1,
                       n_modes: int = 2, align: float = 0.0) -> dict:
    """Even/odd supermode splitting of the *two-guide* 3-D cross-section.

    The two guide centres are at (x,y) = (+-d/2, +-dz/2).  Only the half domain
    x >= 0 is discretised; the mirror plane x=0 carries a Neumann (even) or a
    Dirichlet (odd) condition.  Both branches use the *same* physical grid and
    the *same* outer boundary, so the discretisation error largely cancels in
    Delta n_eff.  ``align`` shifts the whole layout by a sub-grid amount to test
    whether the splitting is a numerical artefact (it must be invariant).
    """
    k0 = optics.k0
    o = optics
    dx_half = d_um / 2.0 + align
    half_x = dx_half + half_pad_um
    nx = int(round(half_x / step_um)) + 1
    half_y = abs(dz_um) / 2.0 + half_pad_um
    ny = int(round(2 * half_y / step_um)) + 1
    x = np.arange(nx) * step_um
    y = (np.arange(ny) - (ny - 1) / 2.0) * step_um
    X, Y = np.meshgrid(x, y)

    ex, ey = cell_edges(x), cell_edges(y)

    def frac_core(xc, yc):
        """Area fraction of each cell inside a rectangle centred at (xc,yc)."""
        fx = _frac_inside(ex[:-1] - xc, ex[1:] - xc, o.core_w_um / 2.0) / (ex[1:] - ex[:-1])
        fy = _frac_inside(ey[:-1] - yc, ey[1:] - yc, o.core_h_um / 2.0) / (ey[1:] - ey[:-1])
        return np.outer(fy, fx)

    def make_n2(shift_x, shift_y):
        if o.profile == "step":
            f = frac_core(shift_x, shift_y) + frac_core(-shift_x, -shift_y)
            f = np.clip(f, 0.0, 1.0)
            return o.n_clad ** 2 + f * (o.n_core ** 2 - o.n_clad ** 2)
        Xc = X - shift_x
        Yc = Y - shift_y
        r2 = (2 * Xc / o.core_w_um) ** 2 + (2 * Yc / o.core_h_um) ** 2
        return (o.n_clad + o.delta_n * np.exp(-math.log(2.0) * r2)) ** 2

    n2_single = make_n2(dx_half, dz_um / 2.0)
    out = {}
    grid_cache = {}
    for mirror in ("even", "odd"):
        D2x = _half_domain_d2x(nx, step_um, mirror)
        m = D2x.shape[0]
        # for the odd branch the unknown column j corresponds to node x=(j+1)h
        j0 = 0 if mirror == "even" else 1
        n2h = n2_single[1:-1, j0:j0 + m].copy()
        # the two symmetrised cores: guide at +centre and its mirror at -centre
        D2y = _uniform_d2(ny, step_um)
        A = (sp.kron(D2y, sp.eye(m, format="csr"), format="csr")
             + sp.kron(sp.eye(ny - 2, format="csr"), D2x, format="csr"))
        A = (A + sp.diags(k0 ** 2 * n2h.ravel())).tocsc()
        sigma = float(k0 ** 2 * o.n_core ** 2) * (1.0 - 1e-9)
        vals, vecs = eigsh(A, k=min(n_modes, A.shape[0] - 2), sigma=sigma,
                           which="LM", tol=1e-13, maxiter=80000)
        out[mirror] = float(np.max(np.sqrt(np.clip(vals, 0.0, None)))) / k0

    dn_eff = out["even"] - out["odd"]
    kappa = math.pi * abs(dn_eff) / (o.wavelength_nm * 1e-6)
    return {
        "d_um": float(d_um), "dz_um": float(dz_um),
        "n_eff_even": out["even"], "n_eff_odd": out["odd"],
        "delta_n_eff": float(abs(dn_eff)), "kappa_mm_inv": float(kappa),
        "grid_um": step_um, "half_x_um": half_x, "align_um": float(align),
        "method": "supermode_3d",
    }

# ------------------------------------------------------------ asymptotic model
@dataclass
class KappaModel:
    """Validated kappa(d, dz) for two identical parallel guides.

    ``d`` is the 3-D centre-to-centre distance.  For ``d <= d_switch`` the value
    comes from the overlap integral on a graded-grid mode (resolved); beyond it
    the exact cladding decay constant is used::

        kappa(d) = kappa(d_switch) * exp(-gamma_eff * (d - d_switch))
    """

    optics: Optics
    d_ref_um: float
    kappa_ref_mm_inv: float
    gamma_um: float
    d_switch_um: float = 30.0
    beta_um: float = 0.0
    table: list = field(default_factory=list)
    gamma_measured_um: float = float("nan")
    gamma_r2: float = float("nan")

    def kappa(self, d_um):
        d = np.atleast_1d(np.asarray(d_um, float))
        out = np.empty_like(d)
        lo = d <= self.d_switch_um
        if lo.any():
            out[lo] = np.exp(np.interp(d[lo], self._d, self._logk))
            # below the smallest tabulated d the two-mode picture is invalid;
            # clamp to the first value (callers must treat it as a validity edge)
            out[lo & (d < self._d[0])] = self._kappa[0]
        hi = ~lo
        out[hi] = self.kappa_ref_mm_inv * np.exp(-self.gamma_um * (d[hi] - self.d_ref_um))
        return float(out[0]) if np.ndim(d_um) == 0 else out

    def __post_init__(self):
        d = np.array([r["d_um"] for r in self.table], float)
        k = np.array([r["kappa_mm_inv"] for r in self.table], float)
        order = np.argsort(d)
        self._d = d[order]
        self._kappa = k[order]
        self._logk = np.log(np.maximum(self._kappa, 1e-300))

    @property
    def d_range_um(self) -> tuple[float, float]:
        return float(self._d[0]), float(self._d[-1])

    def integrated_coupling(self, d_of_s, s_um, theta_rad: float = 0.0) -> dict:
        """Amplitude ``a = int kappa(d(s)) exp(-i*dbeta*s) ds`` along a path.

        ``d_of_s`` is the centre-to-centre distance as a function of the path
        coordinate ``s`` (um); ``dbeta`` = beta*(1-cos theta) is the phase
        mismatch of the *crossed* guide when the two guides are not parallel.
        """
        d = np.asarray(d_of_s, float)
        s = np.asarray(s_um, float)
        k = self.kappa(d) * 1e-3                 # 1/mm -> 1/um
        db = self.beta_per_um * (1.0 - math.cos(theta_rad))
        integrand = k * np.exp(-1j * db * s)
        amp = np.trapezoid(integrand, s)
        return {"amplitude": float(abs(amp)), "power": float(abs(amp) ** 2),
                "d_min_um": float(d.min()), "d_max_um": float(d.max())}

    @property
    def beta_per_um(self) -> float:
        return float(self.beta_um)


# --------------------------------------------------------------- model builder
def build_kappa_model(optics: Optics, separations=(9., 10., 11., 12., 13., 14.,
                                                  15., 16., 17., 18., 19., 20.,
                                                  22., 24.),
                      half_um: float = 30.0, step_um: float = 0.1,
                      n_modes: int = 6) -> tuple[KappaModel, list[dict]]:
    """Build the validated kappa(d) database for one optics preset.

    The isolated-guide mode is solved on a **uniform** grid (no graded-grid
    artefact in the evanescent tail) and the overlap integral is evaluated only
    for separations where guide 2 still lies inside that domain
    (``d <= half_um - core_half - 1 um``).  Beyond that the exact cladding
    decay constant ``gamma = sqrt(beta^2-(k0 n_clad)^2)`` is used, which is a
    *lower bound* on the true decay rate of the field along the guide axis and
    therefore makes the extrapolated kappa an upper bound.
    """
    modes_u = solve_channel(optics, half_um=half_um, step_um=step_um,
                            n_modes=n_modes)
    mode0 = int(np.argmax(modes_u.n_eff))
    beta = float(modes_u.beta[mode0])
    gamma = float(math.sqrt(max(beta ** 2 - (optics.k0 * optics.n_clad) ** 2, 0.0)))
    tail = modes_u.tail_decay(mode0, "x", r0_um=6.0)

    d_max_resolved = half_um - max(optics.core_w_um, optics.core_h_um) / 2.0 - 1.0
    rows = []
    for d in separations:
        if d > d_max_resolved:
            continue
        r = kappa_overlap(modes_u, float(d), 0.0, mode=mode0)
        r["optics_label"] = optics.label
        r["validity"] = "resolved"
        r["gamma_from_eigenvalue"] = gamma
        rows.append(r)

    # exponential fit on the resolved tail (20-30 um) with the *exact* gamma
    sel = [r for r in rows if r["d_um"] >= max(rows[-1]["d_um"] - 8.0, 12.0)]
    d_ref = float(rows[-1]["d_um"])
    kappa_ref = float(np.exp(np.mean([math.log(r["kappa_mm_inv"]) +
                                     gamma * (r["d_um"] - d_ref) for r in sel])))
    model = KappaModel(optics=optics, d_ref_um=d_ref, kappa_ref_mm_inv=kappa_ref,
                       gamma_um=gamma, d_switch_um=d_ref, beta_um=beta, table=rows,
                       gamma_measured_um=tail["gamma_per_um"], gamma_r2=tail["r2"])
    return model, rows






