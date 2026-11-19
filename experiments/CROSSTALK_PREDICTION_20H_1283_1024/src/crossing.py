"""Local electromagnetic model for a waveguide crossing (E5 optical kernel).

A crossing is the only place on this board where two centre lines come closer
than 50 um, so it dominates the optical coupling budget.  Rather than assigning
an empirical crosstalk number to the 1283 events we solve a **local 2-D scalar
scattering problem** for the canonical crossing geometry and map every event
onto the resulting angle-dependent transfer curve.

Model construction
------------------
1.  Effective-index method (EIM): the vertical slab gives ``n_slab``; the
    in-plane problem is a strip of width ``w`` with core index ``n_slab`` and
    cladding ``n0``.
2.  The **discrete** incident mode is computed on the actual FDFD grid, so that
    it satisfies the discretised background operator to machine precision.
    This is essential: an analytic mode ``exp(i beta x)`` has a ~5 % phase
    residual on a 0.15 um grid, which otherwise acts as a spurious distributed
    source and completely swamps the -80 dB crosstalk signal.
3.  The **exact** scattered-field equation is solved (no Born approximation):

        (lap + k0^2 n^2) psi_s = -k0^2 (n^2 - n_bg^2) psi_inc

    with ``n_bg`` the isolated input-guide structure.
4.  Port amplitudes are obtained by projecting ``psi_s`` onto the discrete mode
    at a plane of each guide where the two guides are >= 20 um apart.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import eigsh, splu

from .config import CONFIG
from .modes import EffectiveIndex2D, effective_index_model


# ------------------------------------------------------------------ utilities
def _stretched_d2(coord: np.ndarray, s: np.ndarray, h: float) -> sp.csr_matrix:
    """d/dx (1/s d/dx) on interior nodes (finite-volume form)."""
    n = len(coord)
    inv_s = 1.0 / s
    diag = -(inv_s[0:n - 2] + inv_s[1:n - 1]) / h ** 2
    off = inv_s[1:n - 2] / h ** 2
    return sp.diags([diag, off, off], [0, 1, -1], shape=(n - 2, n - 2),
                    format="csr")


def _plain_d2(coord: np.ndarray, h: float) -> sp.csr_matrix:
    n = len(coord)
    m = n - 2
    main = -2.0 * np.ones(m) / h ** 2
    off = np.ones(m - 1) / h ** 2
    return sp.diags([main, off, off], [0, 1, -1], shape=(m, m), format="csr")


def _pml(coord: np.ndarray, half: float, thickness_um: float,
         strength: float) -> np.ndarray:
    s = np.ones_like(coord, dtype=complex)
    d = np.abs(coord) - (half - thickness_um)
    m = d > 0
    s[m] = 1.0 + 1j * strength * (d[m] / thickness_um) ** 2
    return s


def _bilinear(field: np.ndarray, x: np.ndarray, y: np.ndarray,
              xq: np.ndarray, yq: np.ndarray) -> np.ndarray:
    hx, hy = x[1] - x[0], y[1] - y[0]
    i0 = np.clip(np.floor((xq - x[0]) / hx).astype(int), 0, len(x) - 2)
    j0 = np.clip(np.floor((yq - y[0]) / hy).astype(int), 0, len(y) - 2)
    tx = np.clip((xq - x[i0]) / hx, 0.0, 1.0)
    ty = np.clip((yq - y[j0]) / hy, 0.0, 1.0)
    return (field[j0, i0] * (1 - tx) * (1 - ty)
            + field[j0, i0 + 1] * tx * (1 - ty)
            + field[j0 + 1, i0] * (1 - tx) * ty
            + field[j0 + 1, i0 + 1] * tx * ty)


# ------------------------------------------------------------------- geometry
def _domain_for_angle(theta_rad: float, w_um: float, d_port_um: float,
                      margin_um: float) -> tuple[float, float]:
    sin_t = max(math.sin(theta_rad), 1e-9)
    cos_t = math.cos(theta_rad)
    u_port = d_port_um / sin_t
    x_port = abs(u_port * cos_t)
    Lx = max(x_port + margin_um, 3.0 * w_um + margin_um)
    Ly = max(d_port_um + margin_um, 2.5 * w_um + margin_um)
    return Lx, Ly


def _index_grid_2d(x: np.ndarray, y: np.ndarray, theta_rad: float,
                   n_slab: float, n0: float,
                   w_um: float) -> tuple[np.ndarray, np.ndarray]:
    X, Y = np.meshgrid(x, y)
    inside_in = np.abs(Y) <= w_um / 2.0
    dist_cross = np.abs(-math.sin(theta_rad) * X + math.cos(theta_rad) * Y)
    inside_cross = dist_cross <= w_um / 2.0
    n2 = np.where(inside_in | inside_cross, n_slab ** 2, n0 ** 2)
    n2_bg = np.where(inside_in, n_slab ** 2, n0 ** 2)
    n2[0, :] = n2[-1, :] = n2[:, 0] = n2[:, -1] = n0 ** 2
    n2_bg[0, :] = n2_bg[-1, :] = n2_bg[:, 0] = n2_bg[:, -1] = n0 ** 2
    return n2, n2_bg


# --------------------------------------------------------------------- result
@dataclass
class CrossingResult:
    theta_deg: float
    wavelength_nm: float
    T_through: float
    T_cross: float
    T_loss: float
    energy_error: float
    grid_um: float
    domain_um: tuple[float, float]
    unknowns: int
    n_slab: float
    n_eff_discrete: float
    beta_discrete: float
    n_guided_modes: int = 1
    status: str = "ok"
    fields: tuple | None = None
    extra: dict = field(default_factory=dict)

    def as_row(self) -> dict:
        return {
            "theta_deg": self.theta_deg,
            "wavelength_nm": self.wavelength_nm,
            "T_through": self.T_through,
            "T_cross": self.T_cross,
            "T_cross_db": 10.0 * math.log10(max(self.T_cross, 1e-300)),
            "T_loss": self.T_loss,
            "loss_db": -10.0 * math.log10(max(self.T_through, 1e-300)),
            "energy_error": self.energy_error,
            "grid_um": self.grid_um,
            "domain_x_um": self.domain_um[0],
            "domain_y_um": self.domain_um[1],
            "unknowns": self.unknowns,
            "n_slab": self.n_slab,
            "n_eff_discrete": self.n_eff_discrete,
            "beta_discrete_per_um": self.beta_discrete,
            "n_guided_modes": self.n_guided_modes,
            "status": self.status,
        }


# --------------------------------------------------------------------- solver
def solve_crossing(optics: dict, theta_deg: float,
                   grid_um: float | None = None,
                   d_port_um: float = 20.0,
                   eim: EffectiveIndex2D | None = None,
                   pml_um: float | None = None,
                   pml_strength: float | None = None,
                   max_unknowns: int = 230_000,
                   keep_fields: bool = False,
                   no_cross: bool = False) -> CrossingResult:
    cfg = CONFIG["crossing_model"]
    grid_um = float(grid_um if grid_um is not None else cfg["grid_um"])
    pml_um = float(pml_um if pml_um is not None else cfg["pml_thickness_um"])
    pml_strength = float(pml_strength if pml_strength is not None
                         else cfg["pml_strength"])
    eim = eim if eim is not None else effective_index_model(optics)
    th = math.radians(theta_deg)
    if theta_deg <= 0.0 or theta_deg > 90.0:
        raise ValueError("crossing angle must be in (0, 90] deg")
    w = float(optics["core_width_um"])
    k0 = 2.0 * math.pi / (float(optics["wavelength_nm"]) * 1e-3)
    n0 = float(optics["n_clad"])
    ns = float(eim.n_slab)
    margin = float(cfg["domain_margin_um"])

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
            raise RuntimeError("crossing domain too large")
    h = grid_um
    x = np.linspace(-Lx, Lx, nx)
    y = np.linspace(-Ly, Ly, ny)
    n2, n2_bg = _index_grid_2d(x, y, th, ns, n0, w)
    if no_cross:
        n2 = n2_bg.copy()

    # ---- discrete incident mode: exact eigenvector of the background operator
    Dyn = _plain_d2(y, h)
    Ty = Dyn + sp.diags(k0 ** 2 * n2_bg[1:-1, 0] ** 2)
    sigma = (k0 * ns) ** 2 * (1.0 - 1e-6)
    n_req = min(8, ny - 2)
    vals, vecs = eigsh(Ty.tocsc(), k=n_req, sigma=sigma, which="LM", tol=1e-13)
    order = np.argsort(vals)[::-1]
    vals, vecs = vals[order], vecs[:, order]
    betas, phis = [], []
    for j in range(len(vals)):
        arg = 1.0 - float(vals[j]) * h ** 2 / 2.0
        if arg <= -1.0 or arg >= 1.0:
            continue
        betas.append(math.acos(arg) / h)
        phis.append(vecs[:, j].ravel())
    # keep guided modes only (n_eff > n_clad)
    keep = [j for j in range(len(betas)) if betas[j] / k0 > n0 + 1e-6]
    betas = [betas[j] for j in keep]
    phis = [phis[j] for j in keep]
    if not betas:
        raise RuntimeError("no guided mode on the crossing grid")
    n_guided = len(betas)
    phi_full = []
    for p in phis:
        p = p / math.sqrt(np.sum(p ** 2) * h)
        f = np.zeros(ny)
        f[1:-1] = p
        phi_full.append(f)
    beta_x = betas[0]
    n_eff_disc = beta_x / k0
    phi = phi_full[0]

    sx = _pml(x, Lx, pml_um, pml_strength)
    sy = _pml(y, Ly, pml_um, pml_strength)
    Dx = _stretched_d2(x, sx, h)
    Dy = _stretched_d2(y, sy, h)
    nxi, nyi = nx - 2, ny - 2
    A = (sp.kron(sp.eye(nyi, format="csr"), Dx, format="csr")
         + sp.kron(Dy, sp.eye(nxi, format="csr"), format="csr"))
    sub = n2[1:-1, 1:-1]
    A = (A + sp.diags(k0 ** 2 * sub.ravel())).tocsc()

    psi_inc = np.exp(1j * beta_x * x)[None, :] * phi[:, None]
    delta = sub - n2_bg[1:-1, 1:-1]
    rhs = (-k0 ** 2 * delta * psi_inc[1:-1, 1:-1]).ravel().astype(complex)

    lu = splu(A)
    psi_s = lu.solve(rhs).reshape(nyi, nxi)
    full = np.zeros((ny, nx), dtype=complex)
    full[1:-1, 1:-1] = psi_s

    # ---- port 1: input guide, just inside the x-PML
    x1 = Lx - pml_um - 3.0 * h
    i1 = int(round((x1 - x[0]) / h))
    col = full[1:-1, i1]
    a1 = np.array([np.sum(col * p[1:-1]) * h for p in phi_full]) \
        * np.exp(-1j * beta_x * x[i1])
    T_through = float(abs(1.0 + a1[0]) ** 2 + np.sum(np.abs(a1[1:]) ** 2))

    # ---- port 2: crossed guide, perpendicular plane at u = u_port
    sin_t, cos_t = math.sin(th), math.cos(th)
    u_port = d_port_um / sin_t
    pc = np.array([u_port * cos_t, u_port * sin_t])
    half_port = min(3.5 * w, 0.45 * min(Lx, Ly))
    s = np.arange(-half_port, half_port + 1e-12, h / 2.0)
    xq = pc[0] - sin_t * s
    yq = pc[1] + cos_t * s
    inside = ((xq > x[0] + 2 * h) & (xq < x[-1] - 2 * h)
              & (yq > y[0] + 2 * h) & (yq < y[-1] - 2 * h))
    s, xq, yq = s[inside], xq[inside], yq[inside]
    vals = _bilinear(full, x, y, xq, yq)
    ds = s[1] - s[0]
    a2 = np.array([np.sum(vals * np.interp(s, y, p, left=0.0, right=0.0)) * ds
                   for p in phi_full])
    T_cross = float(np.sum(np.abs(a2) ** 2))

    T_loss = max(0.0, 1.0 - T_through - T_cross)
    res = CrossingResult(
        theta_deg=float(theta_deg), wavelength_nm=float(optics["wavelength_nm"]),
        T_through=T_through, T_cross=T_cross, T_loss=T_loss,
        energy_error=float(T_through + T_cross - 1.0),
        grid_um=h, domain_um=(2 * Lx, 2 * Ly), unknowns=int(N),
        n_slab=ns, n_eff_discrete=float(n_eff_disc),
        beta_discrete=float(beta_x), n_guided_modes=int(n_guided),
    )
    if keep_fields:
        res.fields = (x, y, full, psi_inc, phi)
    return res


# --------------------------------------------------------------- CMT reference
def crossing_cmt(optics: dict, theta_deg: float, kappa_model,
                 beta_per_um: float, grid_um_res: float = 0.02,
                 s_max_um: float | None = None) -> dict:
    """Coupled-mode reference integral along the crossing.

        A = int kappa(|s| sin t) exp(-i beta (1-cos t) s) ds

    Only meaningful for the quasi-parallel (small-angle) regime; it is used to
    cross-check the FDFD solver there, not as the primary model at large angles.
    """
    th = math.radians(theta_deg)
    if s_max_um is None:
        s_max_um = kappa_model.d_hi / max(math.sin(th), 1e-6)
    s = np.arange(-s_max_um, s_max_um + grid_um_res, grid_um_res)
    d = np.abs(s) * math.sin(th)
    kap = kappa_model.kappa(d)                       # 1/mm
    dbeta = beta_per_um * (1.0 - math.cos(th))       # 1/um
    amp = np.trapezoid(kap * np.exp(-1j * dbeta * s), s) * 1e-3
    return {"theta_deg": float(theta_deg),
            "T_cross_cmt": float(min(abs(amp) ** 2, 1.0)),
            "amplitude_cmt": float(abs(amp))}


# ============================================================================
#  Primary crossing model: first-order (Born / coupled-mode) scattering integral
# ============================================================================
def crossing_born(eim: EffectiveIndex2D, theta_deg: float) -> dict:
    """First-order scattering amplitude for two identical guides crossing at theta.

    Derivation (see the report, section 3.4)
    ----------------------------------------
    Projecting the scattered field of guide 1 onto the mode of guide 2 along the
    common rotated coordinate (u along guide 2, s across it) gives

        a2 = -i k0^2/(2 beta) * int int  dn^2 phi1(y) phi2(s)
                              exp(i beta [u(cos t - 1) - s sin t]) ds du

    Because the integrand factorises after the rotation, the double integral
    collapses to two 1-D Fourier transforms of the same mode profile:

        a2 = -i k0^2/(2 beta) * Phi(q)^2 / sin(t),      q = -beta tan(t/2)

    with Phi(q) = int phi(s) exp(i q s) ds and phi normalised to unit power.
    For t -> 0 this reduces to the standard parallel coupled-mode coefficient
    (a2 = kappa * L with L ~ w/t), and for large t the high-q Fourier tail of
    the mode suppresses the coupling quadratically -- the correct physics that
    a fixed coupling coefficient cannot reproduce.

    The result is unitarised as ``P = sin^2(|a2|)`` so that it saturates in the
    strong-coupling regime instead of diverging.
    """
    th = math.radians(theta_deg)
    beta = float(eim.beta2d)
    k0 = float(eim.k0)
    q = -beta * math.tan(th / 2.0)
    phi = eim.phi
    s = eim.s
    Phi = np.trapezoid(phi * np.exp(1j * q * s), s)
    a2 = (k0 * k0 / (2.0 * beta)) * Phi * Phi / math.sin(th)
    amp = float(abs(a2))
    amp_capped = min(amp, math.pi / 2.0)
    power = float(math.sin(amp_capped) ** 2)
    if amp < 0.1:
        regime, sigma_db = "weak_coupling", 5.0
    elif amp < 0.5:
        regime, sigma_db = "moderate_coupling", 10.0
    else:
        regime, sigma_db = "strong_coupling", 20.0
    return {
        "theta_deg": float(theta_deg),
        "q_per_um": float(q),
        "fourier_phi": float(abs(Phi)),
        "amplitude": amp,
        "amplitude_capped": float(amp_capped),
        "T_cross": power,
        "T_cross_db": 10.0 * math.log10(max(power, 1e-300)),
        "T_cross_born_db": 10.0 * math.log10(max(amp ** 2, 1e-300)),
        "regime": regime,
        "uncertainty_db": sigma_db,
        "model": "born_first_order_unitarised",
    }
