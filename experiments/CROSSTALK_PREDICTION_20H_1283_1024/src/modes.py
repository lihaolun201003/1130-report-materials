"""E2 - scalar weak-guidance mode solver for the glass waveguide cross-section.

Equation solved (documented approximation, *not* a full-vector Maxwell solve):

    d2psi/dx2 + d2psi/dy2 + k0^2 n^2(x, y) psi = beta^2 psi          (1)

with ``k0 = 2*pi/lambda``, Dirichlet boundaries on a square computational
window and a second-order finite-difference Laplacian.  This is the standard
scalar (weakly-guiding) approximation; for Delta n / n = 0.43 % its error on
n_eff is of order 1e-3, and it is reported as such.

The eigenproblem is solved with a shift-invert sparse Lanczos iteration around
``(k0 n_core)^2``.  Guided modes are those with ``n_clad < n_eff < n_core``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import eigsh

from .config import CONFIG


# --------------------------------------------------------------------- profiles
def index_grid(x: np.ndarray, y: np.ndarray, optics: dict) -> np.ndarray:
    """Refractive index n(x, y) for the configured cross-section model."""
    X, Y = np.meshgrid(x, y)                     # shape (ny, nx)
    n0 = float(optics["n_clad"])
    dn = float(optics["delta_n"])
    w = float(optics["core_width_um"])
    h = float(optics["core_height_um"])
    profile = optics.get("profile", "step")
    if profile == "step":
        inside = (np.abs(X) <= w / 2.0) & (np.abs(Y) <= h / 2.0)
        n = np.full_like(X, n0)
        n[inside] = n0 + dn
        return n
    if profile == "graded":
        # separable 2-D Gaussian: n = n0 + dn * exp(-ln2 * [(2x/w)^2 + (2y/h)^2])
        # so the index increment is exactly dn/2 on the nominal core boundary.
        r2 = (2.0 * X / w) ** 2 + (2.0 * Y / h) ** 2
        return n0 + dn * np.exp(-math.log(2.0) * r2)
    raise ValueError(f"unknown profile {profile}")


def core_mask(x: np.ndarray, y: np.ndarray, optics: dict) -> np.ndarray:
    X, Y = np.meshgrid(x, y)
    w = float(optics["core_width_um"])
    h = float(optics["core_height_um"])
    if optics.get("profile", "step") == "step":
        return (np.abs(X) <= w / 2.0) & (np.abs(Y) <= h / 2.0)
    r2 = (2.0 * X / w) ** 2 + (2.0 * Y / h) ** 2
    return r2 <= 1.0


# ------------------------------------------------------------------- operator
def _laplacian_2d(nx: int, ny: int, h: float) -> sp.csr_matrix:
    """5-point Laplacian on an nx-by-ny grid, row-major (iy*nx+ix)."""
    N = nx * ny
    main = -4.0 * np.ones(N)
    offx = np.ones(N)
    offx[np.arange(1, ny) * nx - 1] = 0.0      # no wrap between rows
    offx[-1] = 0.0
    offy = np.ones(N)
    offy[-nx:] = 0.0
    data = [main / h ** 2, offx[:-1] / h ** 2, offx[:-1] / h ** 2,
            offy[:-nx] / h ** 2, offy[:-nx] / h ** 2]
    return sp.diags(data, [0, 1, -1, nx, -nx], format="csr")


def _solve_system(n2: np.ndarray, h: float, k0: float, n_modes: int,
                  sigma: float | None, tol: float) -> tuple[np.ndarray, np.ndarray]:
    ny, nx = n2.shape
    N = nx * ny
    L = _laplacian_2d(nx, ny, h)
    A = L + sp.diags(k0 ** 2 * n2.ravel())
    if sigma is None:
        sigma = float(np.max(A.diagonal())) * (1.0 - 1e-6)
    vals, vecs = eigsh(A, k=n_modes, sigma=sigma, which="LM",
                       tol=tol, maxiter=CONFIG["mode_solver"]["max_iter"])
    order = np.argsort(vals)[::-1]
    return vals[order], vecs[:, order]


# ---------------------------------------------------------------------- result
@dataclass
class ModeSolution:
    optics: dict
    domain_um: float
    grid_um: float
    x: np.ndarray
    y: np.ndarray
    n_eff: np.ndarray
    beta: np.ndarray
    fields: np.ndarray        # (n_found, ny, nx)
    n_clad: float
    n_core: float
    k0: float

    @property
    def guided_mask(self) -> np.ndarray:
        return (self.n_eff > self.n_clad + 1e-7) & (self.n_eff < self.n_core - 1e-9)

    @property
    def n_guided(self) -> int:
        return int(self.guided_mask.sum())

    def guided(self) -> "ModeSolution":
        m = self.guided_mask
        return ModeSolution(self.optics, self.domain_um, self.grid_um, self.x, self.y,
                            self.n_eff[m], self.beta[m], self.fields[m],
                            self.n_clad, self.n_core, self.k0)

    def confinement(self, i: int) -> float:
        mask = core_mask(self.x, self.y, self.optics)
        f = self.fields[i]
        tot = float(np.sum(np.abs(f) ** 2))
        return float(np.sum(np.abs(f)[mask] ** 2) / tot) if tot > 0 else 0.0

    @property
    def wx(self) -> np.ndarray:
        h = self.grid_um
        return np.full(len(self.x), h)

    @property
    def wy(self) -> np.ndarray:
        return self.wx

    @property
    def dA(self) -> np.ndarray:
        return np.outer(self.wy, self.wx)

    def interpolator(self, i: int):
        """Bilinear interpolator of the (real) mode field, zero outside."""
        f = self.fields[i]
        x, y = self.x, self.y
        dx, dy = x[1] - x[0], y[1] - y[0]

        def interp(xq: np.ndarray, yq: np.ndarray) -> np.ndarray:
            fx = (np.asarray(xq) - x[0]) / dx
            fy = (np.asarray(yq) - y[0]) / dy
            i0 = np.clip(np.floor(fx).astype(int), 0, len(x) - 2)
            j0 = np.clip(np.floor(fy).astype(int), 0, len(y) - 2)
            tx = np.clip(fx - i0, 0.0, 1.0)
            ty = np.clip(fy - j0, 0.0, 1.0)
            v = (f[j0, i0] * (1 - tx) * (1 - ty) + f[j0, i0 + 1] * tx * (1 - ty)
                 + f[j0 + 1, i0] * (1 - tx) * ty + f[j0 + 1, i0 + 1] * tx * ty)
            inside = ((xq >= x[0]) & (xq <= x[-1]) & (yq >= y[0]) & (yq <= y[-1]))
            return np.where(inside, v, 0.0)

        return interp


def solve_modes(optics: dict, domain_um: float | None = None,
                grid_um: float | None = None, n_modes: int | None = None,
                tol: float | None = None) -> ModeSolution:
    cfg = CONFIG["mode_solver"]
    domain_um = float(domain_um if domain_um is not None else cfg["domain_um"])
    grid_um = float(grid_um if grid_um is not None else cfg["grid_um"])
    n_modes = int(n_modes if n_modes is not None else cfg["n_modes"])
    tol = float(tol if tol is not None else cfg["eig_tol"])
    lam_um = float(optics["wavelength_nm"]) * 1e-3
    k0 = 2.0 * math.pi / lam_um
    n0 = float(optics["n_clad"])
    nc = n0 + float(optics["delta_n"])

    nx = int(round(domain_um / grid_um)) + 1
    if nx % 2 == 0:
        nx += 1
    half = (nx - 1) / 2.0
    x = (np.arange(nx) - half) * grid_um
    y = x.copy()
    n = index_grid(x, y, optics)
    # Dirichlet window: force the outermost ring to the cladding index and rely
    # on the field being ~exp(-(D/2 - w/2)/decay) << 1 there (checked in E2).
    n[0, :] = n[-1, :] = n[:, 0] = n[:, -1] = n0
    n2 = n ** 2
    interior = n2[1:-1, 1:-1]
    sigma = (k0 * nc) ** 2 * (1.0 - 1e-6)
    vals, vecs = _solve_system(interior, grid_um, k0, n_modes, sigma, tol)
    fields = np.zeros((vecs.shape[1], nx, nx))
    for i in range(vecs.shape[1]):
        f = np.zeros((nx, nx))
        f[1:-1, 1:-1] = vecs[:, i].reshape(nx - 2, nx - 2)
        # normalise to unit modal power: integral |psi|^2 dA = 1
        norm = math.sqrt(float(np.sum(np.abs(f) ** 2)) * grid_um ** 2)
        fields[i] = f / norm
    beta = np.sqrt(np.clip(vals, 0.0, None))
    n_eff = beta / k0
    return ModeSolution(optics, domain_um, grid_um, x, y, n_eff, beta, fields,
                        n0, nc, k0)


# ------------------------------------------------------------ EIM (for crossing)
@dataclass
class EffectiveIndex2D:
    """Effective-index model of the channel: in-plane slab index + mode."""
    n_slab: float
    n_eff: float
    slab_neff: np.ndarray
    s: np.ndarray          # transverse coordinate (um)
    phi: np.ndarray        # normalised in-plane mode profile
    beta2d: float
    k0: float
    width_um: float
    optics: dict


def _slab_solve(n_profile: np.ndarray, z: np.ndarray, k0: float,
                n_guess: float) -> tuple[float, np.ndarray]:
    """1-D scalar slab eigenmode (Dirichlet), returns (n_eff, field)."""
    h = z[1] - z[0]
    N = len(z)
    main = -2.0 / h ** 2 + k0 ** 2 * n_profile ** 2
    off = np.ones(N - 1) / h ** 2
    A = sp.diags([main, off, off], [0, 1, -1], format="csc")
    sigma = (k0 * n_guess) ** 2 * (1.0 - 1e-6)
    vals, vecs = eigsh(A, k=1, sigma=sigma, which="LM", tol=1e-10)
    beta = math.sqrt(max(float(vals[0]), 0.0))
    f = vecs[:, 0]
    f = f / math.sqrt(float(np.sum(f ** 2)) * h)
    return beta / k0, f


def effective_index_model(optics: dict, slab_um: float = 44.0,
                          slab_grid_um: float = 0.05) -> EffectiveIndex2D:
    """Standard effective-index method (EIM) for the channel waveguide.

    Step 1: vertical slab of height ``h`` -> n_slab(x).
    Step 2: horizontal slab of width ``w`` with core index n_slab.
    The in-plane 2-D scalar problem used for the crossing FDFD then has the
    two-level index profile ``n_slab`` inside the core strip and ``n_clad``
    outside.  This preserves the vertical confinement physics at the level of
    n_eff (validated against the full 2-D scalar solve in E2).
    """
    n0 = float(optics["n_clad"])
    dn = float(optics["delta_n"])
    w = float(optics["core_width_um"])
    hgt = float(optics["core_height_um"])
    lam_um = float(optics["wavelength_nm"]) * 1e-3
    k0 = 2.0 * math.pi / lam_um
    profile = optics.get("profile", "step")

    nz = int(round(slab_um / slab_grid_um))
    z = (np.arange(nz) - (nz - 1) / 2.0) * slab_grid_um
    if profile == "step":
        nz_profile = np.where(np.abs(z) <= hgt / 2.0, n0 + dn, n0)
    else:
        nz_profile = n0 + dn * np.exp(-math.log(2.0) * (2.0 * z / hgt) ** 2)
    n_slab, _ = _slab_solve(nz_profile, z, k0, n0 + dn)

    # horizontal slab
    ns = int(round(slab_um / slab_grid_um))
    s = (np.arange(ns) - (ns - 1) / 2.0) * slab_grid_um
    if profile == "step":
        nxy = np.where(np.abs(s) <= w / 2.0, n_slab, n0)
    else:
        nxy = n0 + (n_slab - n0) * np.exp(-math.log(2.0) * (2.0 * s / w) ** 2)
    n_eff, phi = _slab_solve(nxy, s, k0, n_slab)

    return EffectiveIndex2D(n_slab=float(n_slab), n_eff=float(n_eff),
                            slab_neff=nxy, s=s, phi=phi,
                            beta2d=float(k0 * n_eff), k0=k0,
                            width_um=w, optics=optics)


# ------------------------------------------------------------------ reporting
def mode_rows(sol: ModeSolution, label: str) -> list[dict]:
    rows = []
    for i in range(len(sol.n_eff)):
        guided = bool(sol.n_eff[i] > sol.n_clad + 1e-7)
        rows.append({
            "parameter_set": label,
            "mode_index": i,
            "n_eff": float(sol.n_eff[i]),
            "beta_per_um": float(sol.beta[i]),
            "guided": int(guided),
            "confinement_core": sol.confinement(i) if guided else float("nan"),
            "wavelength_nm": sol.optics["wavelength_nm"],
            "delta_n": sol.optics["delta_n"],
            "core_width_um": sol.optics["core_width_um"],
            "core_height_um": sol.optics["core_height_um"],
            "profile": sol.optics["profile"],
            "domain_um": sol.domain_um,
            "grid_um": sol.grid_um,
        })
    return rows


def convergence_rows(optics: dict, label: str) -> list[dict]:
    cfg = CONFIG["mode_solver"]
    rows = []
    for grid in cfg["convergence_grids_um"]:
        sol = solve_modes(optics, domain_um=cfg["domain_um"], grid_um=grid)
        g = sol.guided()
        rows.append({
            "parameter_set": label,
            "study": "grid",
            "grid_um": grid,
            "domain_um": cfg["domain_um"],
            "n_guided": g.n_guided,
            "n_eff_fund": float(g.n_eff[0]) if len(g.n_eff) else float("nan"),
            "n_eff_2": float(g.n_eff[1]) if len(g.n_eff) > 1 else float("nan"),
            "beta_fund_per_um": float(g.beta[0]) if len(g.beta) else float("nan"),
        })
    ref = rows[-1]["n_eff_fund"]
    for r in rows:
        r["n_eff_error_vs_finest"] = float(r["n_eff_fund"] - ref)
    for dom in cfg["convergence_domains_um"]:
        sol = solve_modes(optics, domain_um=dom, grid_um=cfg["grid_um"])
        g = sol.guided()
        rows.append({
            "parameter_set": label,
            "study": "domain",
            "grid_um": cfg["grid_um"],
            "domain_um": dom,
            "n_guided": g.n_guided,
            "n_eff_fund": float(g.n_eff[0]) if len(g.n_eff) else float("nan"),
            "n_eff_2": float(g.n_eff[1]) if len(g.n_eff) > 1 else float("nan"),
            "beta_fund_per_um": float(g.beta[0]) if len(g.beta) else float("nan"),
            "n_eff_error_vs_finest": float("nan"),
        })
    return rows


# ------------------------------------------------------- graded (large domain)
def graded_axis(half_um: float, fine_um: float = 0.2,
                fine_half_um: float = 14.0, max_step_um: float = 1.2,
                growth: float = 1.22) -> np.ndarray:
    """Symmetric 1-D grid: uniform fine core region, geometric tail growth."""
    half_um = float(half_um)
    fine_half_um = min(float(fine_half_um), half_um)
    xs = [np.arange(-fine_half_um, fine_half_um + 1e-9, fine_um)]
    for sgn in (-1.0, 1.0):
        x = sgn * fine_half_um
        step = fine_um
        tail = []
        while abs(x) < half_um:
            step = min(step * growth, max_step_um)
            x = x + sgn * step
            if abs(x) > half_um:
                x = sgn * half_um
            tail.append(x)
        xs.append(np.asarray(tail))
    g = np.unique(np.concatenate(xs))
    g = np.clip(g, -half_um, half_um)
    return g


def _d2_interior(x: np.ndarray) -> sp.csr_matrix:
    """Non-uniform 3-point second derivative for interior nodes only."""
    n = len(x)
    h = np.diff(x)
    hi, hi1 = h[:-1], h[1:]                 # h_i, h_{i+1} for i = 1..n-2
    cprev = 2.0 / ((hi + hi1) * hi)
    cmain = -2.0 / (hi * hi1)
    cnext = 2.0 / ((hi + hi1) * hi1)
    m = n - 2
    return sp.diags([cmain, cnext[:-1], cprev[1:]], [0, 1, -1],
                    shape=(m, m), format="csr")


@dataclass
class GradedModeSolution:
    optics: dict
    x: np.ndarray
    y: np.ndarray
    n_eff: np.ndarray
    beta: np.ndarray
    fields: np.ndarray
    wx: np.ndarray
    wy: np.ndarray
    n_clad: float
    n_core: float
    k0: float

    @property
    def guided_mask(self) -> np.ndarray:
        return (self.n_eff > self.n_clad + 1e-7) & (self.n_eff < self.n_core - 1e-9)

    @property
    def n_guided(self) -> int:
        return int(self.guided_mask.sum())

    def guided(self) -> "GradedModeSolution":
        m = self.guided_mask
        return GradedModeSolution(self.optics, self.x, self.y, self.n_eff[m],
                                  self.beta[m], self.fields[m], self.wx, self.wy,
                                  self.n_clad, self.n_core, self.k0)

    @property
    def dA(self) -> np.ndarray:
        return np.outer(self.wy, self.wx)

    def confinement(self, i: int) -> float:
        mask = core_mask(self.x, self.y, self.optics)
        f = self.fields[i]
        tot = float(np.sum(np.abs(f) ** 2 * self.dA))
        return float(np.sum(np.abs(f)[mask] ** 2 * self.dA[mask]) / tot) if tot > 0 else 0.0

    def interpolator(self, i: int):
        f = self.fields[i]
        x, y = self.x, self.y

        def interp(xq, yq):
            xq = np.asarray(xq, dtype=float)
            yq = np.asarray(yq, dtype=float)
            i0 = np.clip(np.searchsorted(x, xq) - 1, 0, len(x) - 2)
            j0 = np.clip(np.searchsorted(y, yq) - 1, 0, len(y) - 2)
            dx = x[i0 + 1] - x[i0]
            dy = y[j0 + 1] - y[j0]
            tx = np.clip((xq - x[i0]) / dx, 0.0, 1.0)
            ty = np.clip((yq - y[j0]) / dy, 0.0, 1.0)
            v = (f[j0, i0] * (1 - tx) * (1 - ty) + f[j0, i0 + 1] * tx * (1 - ty)
                 + f[j0 + 1, i0] * (1 - tx) * ty + f[j0 + 1, i0 + 1] * tx * ty)
            inside = ((xq >= x[0]) & (xq <= x[-1]) & (yq >= y[0]) & (yq <= y[-1]))
            return np.where(inside, v, 0.0)

        return interp


def solve_modes_graded(optics: dict, half_um: float = 70.0,
                       fine_um: float = 0.2, n_modes: int | None = None,
                       max_step_um: float = 1.2) -> GradedModeSolution:
    """Scalar mode solve on a large graded grid (accurate evanescent tails)."""
    n_modes = int(n_modes if n_modes is not None else CONFIG["mode_solver"]["n_modes"])
    lam_um = float(optics["wavelength_nm"]) * 1e-3
    k0 = 2.0 * math.pi / lam_um
    n0 = float(optics["n_clad"])
    nc = n0 + float(optics["delta_n"])
    w = float(optics["core_width_um"])
    hgt = float(optics["core_height_um"])
    fine_half = max(1.5 * max(w, hgt), 12.0)

    x = graded_axis(half_um, fine_um, fine_half, max_step_um)
    y = graded_axis(half_um, fine_um, fine_half, max_step_um)
    n = index_grid(x, y, optics)
    n[0, :] = n[-1, :] = n[:, 0] = n[:, -1] = n0

    D2x = _d2_interior(x)
    D2y = _d2_interior(y)
    nx_i, ny_i = len(x) - 2, len(y) - 2
    A = (sp.kron(sp.eye(ny_i, format="csr"), D2x, format="csr")
         + sp.kron(D2y, sp.eye(nx_i, format="csr"), format="csr"))
    sub = n[1:-1, 1:-1]
    A = (A + sp.diags(k0 ** 2 * sub.ravel() ** 2)).tocsc()
    sigma = (k0 * nc) ** 2 * (1.0 - 1e-6)
    vals, vecs = eigsh(A, k=n_modes, sigma=sigma, which="LM", tol=1e-11,
                       maxiter=CONFIG["mode_solver"]["max_iter"])
    order = np.argsort(vals)[::-1]
    vals, vecs = vals[order], vecs[:, order]

    wx = np.empty_like(x)
    wx[1:-1] = 0.5 * (x[2:] - x[:-2])
    wx[0] = 0.5 * (x[1] - x[0])
    wx[-1] = 0.5 * (x[-1] - x[-2])
    wy = np.empty_like(y)
    wy[1:-1] = 0.5 * (y[2:] - y[:-2])
    wy[0] = 0.5 * (y[1] - y[0])
    wy[-1] = 0.5 * (y[-1] - y[-2])

    fields = np.zeros((vecs.shape[1], len(y), len(x)))
    dA = np.outer(wy, wx)
    for i in range(vecs.shape[1]):
        f = np.zeros((len(y), len(x)))
        f[1:-1, 1:-1] = vecs[:, i].reshape(ny_i, nx_i)
        norm = math.sqrt(max(float(np.sum(f ** 2 * dA)), 1e-300))
        fields[i] = f / norm
    beta = np.sqrt(np.clip(vals, 0.0, None))
    return GradedModeSolution(optics, x, y, beta / k0, beta, fields, wx, wy,
                              n0, nc, k0)
