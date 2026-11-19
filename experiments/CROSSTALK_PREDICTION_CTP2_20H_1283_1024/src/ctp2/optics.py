"""Mode solvers and the effective-index model (CTP-2.0).

Three levels are implemented and cross-validated:

``slab_modes``  1-D scalar slab eigensolver (used twice by the EIM)
``build_eim``   effective-index model of the 9x9 um channel: vertical slab ->
                in-plane strip; returns n_slab, the in-plane n_eff and the
                normalised in-plane mode profile used by the 2-D crossing
                kernels (BPM / FDFD)
``solve_channel`` full scalar 3-D cross-section eigensolver: true mode count,
                n_eff and the fields used for the two-waveguide overlap
                integral (kappa)

Accuracy measures implemented here
----------------------------------
* **sub-pixel (cell-averaged) index**: a hard step whose boundary does not fall
  on a grid node gives only first-order accuracy; averaging n^2 over each
  finite-difference cell restores second order.  This matters because the
  legacy CTP-1.0 solver snapped the 9 um step to the 0.2 um grid.
* **Richardson extrapolation** of the slab solves in h^2.
* **tail decay constant** measured from the computed mode field, which is the
  physically correct exponent for evanescent coupling (used by the large-
  separation kappa model instead of an extrapolated numerical splitting).

Conventions
-----------
all lengths in um, ``k0 = 2*pi/lambda_um``; eigenproblem
``(D2x + D2y + k0^2 n^2) psi = beta^2 psi`` (scalar weak guidance).
1-D profiles normalised to ``int |phi|^2 dz = 1``; 2-D fields to
``int |psi|^2 dA = 1`` so that modal power is ``|amplitude|^2``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import eigsh

from .params import Optics


# ------------------------------------------------------------------- grids
def uniform_axis(half_um: float, step_um: float) -> np.ndarray:
    n = int(round(2 * half_um / step_um)) + 1
    if n % 2 == 0:
        n += 1
    return (np.arange(n) - (n - 1) / 2.0) * step_um


def graded_axis(half_um: float, fine_um: float = 0.1,
                fine_half_um: float = 12.0, max_step_um: float = 2.0,
                growth: float = 1.12) -> np.ndarray:
    half_um = float(half_um)
    fine_half = min(float(fine_half_um), half_um)
    core = np.arange(-fine_half, fine_half + 1e-12, fine_um)
    tail = []
    x, step = fine_half, fine_um
    while x < half_um - 1e-12:
        step = min(step * growth, max_step_um)
        x = min(x + step, half_um)
        tail.append(x)
    tail = np.asarray(tail)
    return np.unique(np.concatenate([core, -tail, tail]))


def cell_edges(x: np.ndarray) -> np.ndarray:
    """Node-centred cell edges (length len(x)+1)."""
    e = np.empty(len(x) + 1)
    e[1:-1] = 0.5 * (x[1:] + x[:-1])
    e[0] = x[0] - 0.5 * (x[1] - x[0])
    e[-1] = x[-1] + 0.5 * (x[-1] - x[-2])
    return e


def _d2_nonuniform(x: np.ndarray) -> sp.csr_matrix:
    n = len(x)
    h = np.diff(x)
    hi, hnext = h[:-1], h[1:]
    cmain = -2.0 / (hi * hnext)
    cnext = 2.0 / ((hi + hnext) * hnext)
    cprev = 2.0 / ((hi + hnext) * hi)
    m = n - 2
    return sp.diags([cmain, cnext[:-1], cprev[1:]], [0, 1, -1],
                    shape=(m, m), format="csr")


def _quad_weights(x: np.ndarray) -> np.ndarray:
    w = np.empty_like(x)
    w[1:-1] = 0.5 * (x[2:] - x[:-2])
    w[0] = 0.5 * (x[1] - x[0])
    w[-1] = 0.5 * (x[-1] - x[-2])
    return w


# --------------------------------------------------------------- index models
def _frac_inside(e1: np.ndarray, e2: np.ndarray, half: float):
    """Overlap length of cell [e1,e2] with [-half, half] (vectorised)."""
    lo = np.maximum(e1, -half)
    hi = np.minimum(e2, half)
    return np.clip(hi - lo, 0.0, None)


def index1d_avg(x: np.ndarray, optics: Optics, axis: str = "x") -> np.ndarray:
    """n along one axis, cell-averaged (n^2) for a step profile."""
    half = (optics.core_w_um if axis == "x" else optics.core_h_um) / 2.0
    if optics.profile == "step":
        e = cell_edges(x)
        frac = _frac_inside(e[:-1], e[1:], half) / (e[1:] - e[:-1])
        return np.sqrt(optics.n_clad ** 2 +
                       frac * (optics.n_core ** 2 - optics.n_clad ** 2))
    return optics.n_clad + optics.delta_n * np.exp(
        -math.log(2.0) * (2.0 * x / (2.0 * half)) ** 2)


def index2d_avg(x: np.ndarray, y: np.ndarray, optics: Optics) -> np.ndarray:
    """n(x,y) with cell-averaged n^2 for a step profile."""
    if optics.profile == "step":
        ex, ey = cell_edges(x), cell_edges(y)
        fx = _frac_inside(ex[:-1], ex[1:], optics.core_w_um / 2.0) / (ex[1:] - ex[:-1])
        fy = _frac_inside(ey[:-1], ey[1:], optics.core_h_um / 2.0) / (ey[1:] - ey[:-1])
        f = np.outer(fy, fx)
        return np.sqrt(optics.n_clad ** 2 + f * (optics.n_core ** 2 - optics.n_clad ** 2))
    X, Y = np.meshgrid(x, y)
    r2 = (2.0 * X / optics.core_w_um) ** 2 + (2.0 * Y / optics.core_h_um) ** 2
    return optics.n_clad + optics.delta_n * np.exp(-math.log(2.0) * r2)


# ------------------------------------------------------------- 1-D slab solve
@dataclass
class SlabModes:
    beta: np.ndarray
    n_eff: np.ndarray
    fields: np.ndarray
    z: np.ndarray
    k0: float
    n_clad: float

    @property
    def guided(self) -> np.ndarray:
        return self.n_eff > self.n_clad + 1e-9

    def fundamental(self) -> tuple[float, np.ndarray]:
        m = self.guided
        if not m.any():  # pragma: no cover
            return float(self.n_eff[0]), self.fields[0]
        idx = np.flatnonzero(m)[int(np.argmax(self.n_eff[m]))]
        return float(self.n_eff[idx]), self.fields[idx]


def slab_modes(n2_profile: np.ndarray, z: np.ndarray, k0: float,
               n_modes: int = 4) -> SlabModes:
    """Solve ``(d2/dz2 + k0^2 n(z)^2) phi = beta^2 phi``; Dirichlet ends."""
    n = len(z)
    h = np.diff(z)
    if np.allclose(h, h[0], rtol=1e-12):
        hh = h[0]
        D2 = sp.diags([np.ones(n - 1) / hh ** 2, -2.0 * np.ones(n) / hh ** 2,
                       np.ones(n - 1) / hh ** 2], [-1, 0, 1], format="csr")
    else:
        D2 = _d2_nonuniform(z)
    A = (D2 + sp.diags(k0 ** 2 * n2_profile)).tocsc()
    sigma = float(np.max(k0 ** 2 * n2_profile)) * (1.0 - 1e-9)
    vals, vecs = eigsh(A, k=min(n_modes, n - 2), sigma=sigma, which="LM",
                       tol=1e-13, maxiter=60000)
    order = np.argsort(vals)[::-1]
    vals, vecs = vals[order], vecs[:, order]
    w = _quad_weights(z)
    fields = vecs.T.copy()
    for i in range(fields.shape[0]):
        norm = math.sqrt(max(float(np.sum(fields[i] ** 2 * w)), 1e-300))
        fields[i] /= norm
    beta = np.sqrt(np.clip(vals, 0.0, None))
    return SlabModes(beta=beta, n_eff=beta / k0, fields=fields, z=z, k0=k0,
                     n_clad=float(np.min(n2_profile) ** 0.5))


def slab_neff_richardson(optics: Optics, axis: str = "y",
                         steps=(0.06, 0.03, 0.015),
                         half_um: float = 25.0) -> tuple[float, list]:
    out = []
    for h in steps:
        z = uniform_axis(half_um, h)
        n2 = index1d_avg(z, optics, axis) ** 2
        n2[0] = n2[-1] = optics.n_clad ** 2
        sm = slab_modes(n2, z, optics.k0, n_modes=4)
        out.append(sm.fundamental()[0])
    n_extrap = (4.0 * out[2] - out[1]) / 3.0     # 2nd order in h^2
    return float(n_extrap), out


# ------------------------------------------------------- effective-index model
@dataclass
class EIM:
    n_slab: float
    n_eff: float
    beta: float
    k0: float
    s: np.ndarray
    phi: np.ndarray
    n2_profile: np.ndarray
    core_w_um: float
    n_clad: float
    optics: Optics
    slab_convergence: list = field(default_factory=list)

    @property
    def gamma_um(self) -> float:
        return float(math.sqrt(max(self.beta ** 2 - (self.k0 * self.n_clad) ** 2, 0.0)))

    def index2d_n2(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """In-plane 2-D ``n^2`` grid (tilted/arbitrary structures fill this)."""
        X, Y = np.meshgrid(x, y)
        if self.optics.profile == "step":
            inside = np.abs(X) <= self.core_w_um / 2.0
            return np.where(inside, self.n_slab ** 2, self.n_clad ** 2)
        r2 = (2.0 * X / self.core_w_um) ** 2
        return (self.n_clad + (self.n_slab - self.n_clad) *
                np.exp(-math.log(2.0) * r2)) ** 2


def build_eim(optics: Optics, grid_um: float = 0.005,
              half_um: float = 25.0) -> EIM:
    k0 = optics.k0
    n_slab, conv = slab_neff_richardson(optics, "y")

    s = uniform_axis(half_um, grid_um)
    if optics.profile == "step":
        e = cell_edges(s)
        frac = _frac_inside(e[:-1], e[1:], optics.core_w_um / 2.0) / (e[1:] - e[:-1])
        n2 = optics.n_clad ** 2 + frac * (n_slab ** 2 - optics.n_clad ** 2)
    else:
        n = optics.n_clad + (n_slab - optics.n_clad) * np.exp(
            -math.log(2.0) * (2.0 * s / optics.core_w_um) ** 2)
        n2 = n ** 2
    n2[0] = n2[-1] = optics.n_clad ** 2
    sm = slab_modes(n2, s, k0, n_modes=4)
    guided = sm.guided
    if not guided.any():  # pragma: no cover
        raise RuntimeError("EIM strip has no guided mode")
    idx = int(np.flatnonzero(guided)[int(np.argmax(sm.n_eff[guided]))])
    return EIM(n_slab=float(n_slab), n_eff=float(sm.n_eff[idx]),
               beta=float(sm.beta[idx]), k0=k0, s=s, phi=sm.fields[idx],
               n2_profile=n2, core_w_um=optics.core_w_um,
               n_clad=optics.n_clad, optics=optics, slab_convergence=conv)


# --------------------------------------------------- full 3-D channel eigensolve
@dataclass
class ChannelModes:
    optics: Optics
    x: np.ndarray
    y: np.ndarray
    wx: np.ndarray
    wy: np.ndarray
    n_eff: np.ndarray
    beta: np.ndarray
    fields: np.ndarray
    n_clad: float
    n_core: float
    k0: float
    uniform_step_um: float | None = None

    @property
    def guided(self) -> np.ndarray:
        return (self.n_eff > self.n_clad + 5e-6) & (self.n_eff < self.n_core - 1e-9)

    def ordered(self) -> "ChannelModes":
        idx = np.argsort(-self.n_eff)
        return ChannelModes(self.optics, self.x, self.y, self.wx, self.wy,
                            self.n_eff[idx], self.beta[idx], self.fields[idx],
                            self.n_clad, self.n_core, self.k0,
                            self.uniform_step_um)

    def interpolator(self, i: int):
        f = self.fields[i]
        x, y = self.x, self.y

        def interp(xq, yq):
            xq = np.asarray(xq, float)
            yq = np.asarray(yq, float)
            i0 = np.clip(np.searchsorted(x, xq) - 1, 0, len(x) - 2)
            j0 = np.clip(np.searchsorted(y, yq) - 1, 0, len(y) - 2)
            tx = np.clip((xq - x[i0]) / (x[i0 + 1] - x[i0]), 0, 1)
            ty = np.clip((yq - y[j0]) / (y[j0 + 1] - y[j0]), 0, 1)
            v = (f[j0, i0] * (1 - tx) * (1 - ty) + f[j0, i0 + 1] * tx * (1 - ty)
                 + f[j0 + 1, i0] * (1 - tx) * ty
                 + f[j0 + 1, i0 + 1] * tx * ty)
            inside = (xq >= x[0]) & (xq <= x[-1]) & (yq >= y[0]) & (yq <= y[-1])
            return np.where(inside, v, 0.0)

        return interp

    def confinement(self, i: int) -> float:
        m = self.optics
        X, Y = np.meshgrid(self.x, self.y)
        if m.profile == "step":
            mask = (np.abs(X) <= m.core_w_um / 2) & (np.abs(Y) <= m.core_h_um / 2)
        else:
            mask = ((2 * X / m.core_w_um) ** 2 + (2 * Y / m.core_h_um) ** 2) <= 1
        dA = np.outer(self.wy, self.wx)
        f2 = self.fields[i] ** 2
        return float(np.sum(f2[mask] * dA[mask]) / np.sum(f2 * dA))

    def tail_decay(self, i: int, axis: str = "x",
                   r0_um: float = 6.0, r1_um: float | None = None) -> dict:
        """Fit ``ln|psi|`` versus radius on a principal axis (exterior only).

        Returns the measured decay constant (1/um), the fitted amplitude and the
        R^2 of the log-linear fit.  Only points with |psi| above 1e-12 of the
        peak are used (below that the discrete tail is unreliable).
        """
        f = np.abs(self.fields[i])
        if axis == "x":
            j = int(np.argmin(np.abs(self.y)))
            coord, line = self.x, f[j, :]
        else:
            i0 = int(np.argmin(np.abs(self.x)))
            coord, line = self.y, f[:, i0]
        r1 = r1_um if r1_um is not None else min(coord[-1], coord[0] * -1) * 0.75
        m = (np.abs(coord) >= r0_um) & (np.abs(coord) <= r1) & (line > 0)
        r = np.abs(coord[m])
        y = np.log(line[m])
        A = np.vstack([r, np.ones_like(r)]).T
        slope, intercept = np.linalg.lstsq(A, y, rcond=None)[0]
        pred = A @ np.array([slope, intercept])
        ss_res = float(np.sum((y - pred) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        return {"gamma_per_um": float(-slope), "amplitude": float(np.exp(intercept)),
                "r2": 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan"),
                "r_min_um": float(r.min()), "r_max_um": float(r.max())}


def solve_channel(optics: Optics, half_um: float = 25.0,
                  step_um: float | None = 0.1, n_modes: int = 10,
                  graded: dict | None = None) -> ChannelModes:
    """Scalar 3-D cross-section eigenproblem."""
    k0 = optics.k0
    if step_um is not None:
        x = uniform_axis(half_um, step_um)
        y = x.copy()
    else:  # pragma: no cover - graded variant kept for the convergence study
        g = dict(graded or {})
        x = graded_axis(half_um, **g)
        y = x.copy()
    n = index2d_avg(x, y, optics)
    n[0, :] = n[-1, :] = n[:, 0] = n[:, -1] = optics.n_clad
    wx, wy = _quad_weights(x), _quad_weights(y)
    hx = x[1] - x[0]
    hy = y[1] - y[0]
    D2x = _uniform_d2(len(x), hx) if step_um is not None else _d2_nonuniform(x)
    D2y = _uniform_d2(len(y), hy) if step_um is not None else _d2_nonuniform(y)
    nx_i, ny_i = len(x) - 2, len(y) - 2
    A = (sp.kron(sp.eye(ny_i, format="csr"), D2x, format="csr")
         + sp.kron(D2y, sp.eye(nx_i, format="csr"), format="csr"))
    sub = n[1:-1, 1:-1]
    A = (A + sp.diags(k0 ** 2 * sub.ravel() ** 2)).tocsc()
    sigma = float(k0 ** 2 * optics.n_core ** 2) * (1.0 - 1e-9)
    vals, vecs = eigsh(A, k=min(n_modes, nx_i * ny_i - 2), sigma=sigma,
                       which="LM", tol=1e-13, maxiter=80000)
    order = np.argsort(vals)[::-1]
    vals, vecs = vals[order], vecs[:, order]
    fields = np.zeros((vecs.shape[1], len(y), len(x)))
    dA = np.outer(wy, wx)
    for i in range(vecs.shape[1]):
        f = np.zeros((len(y), len(x)))
        f[1:-1, 1:-1] = vecs[:, i].reshape(ny_i, nx_i)
        fields[i] = f / math.sqrt(max(float(np.sum(f ** 2 * dA)), 1e-300))
    beta = np.sqrt(np.clip(vals, 0.0, None))
    return ChannelModes(optics, x, y, wx, wy, beta / k0, beta, fields,
                        optics.n_clad, optics.n_core, k0,
                        step_um).ordered()


def _uniform_d2(n: int, h: float) -> sp.csr_matrix:
    m = n - 2
    return sp.diags([np.ones(m - 1) / h ** 2, -2.0 * np.ones(m) / h ** 2,
                     np.ones(m - 1) / h ** 2], [-1, 0, 1], shape=(m, m),
                    format="csr")


# ---------------------------------------------------------------- diagnostics
def analytic_slab_neff(optics: Optics, axis: str = "y",
                       n_modes: int = 4) -> list[float]:
    """Analytic symmetric step-index slab n_eff (validation reference)."""
    half = (optics.core_w_um if axis == "x" else optics.core_h_um) / 2.0
    V = optics.k0 * half * optics.na
    out = []
    for m in range(n_modes):
        if V <= m * math.pi / 2.0 + 1e-12:
            break
        even = (m % 2 == 0)
        lo = m * math.pi / 2.0 + 1e-10
        hi = min((m + 1) * math.pi / 2.0 - 1e-10, V - 1e-10)

        def g(u):
            w = math.sqrt(max(V * V - u * u, 0.0))
            if even:
                return u * math.tan(u) - w
            return -u / math.tan(u) - w

        a, b = lo, hi
        fa = g(a)
        for _ in range(200):
            mid = 0.5 * (a + b)
            fm = g(mid)
            if fa * fm <= 0:
                b = mid
            else:
                a, fa = mid, fm
        u = 0.5 * (a + b)
        w = math.sqrt(max(V * V - u * u, 0.0))
        b_norm = (w / V) ** 2 if V > 0 else 0.0
        out.append(float(math.sqrt(optics.n_clad ** 2 + b_norm *
                                   (optics.n_core ** 2 - optics.n_clad ** 2))))
    return out
