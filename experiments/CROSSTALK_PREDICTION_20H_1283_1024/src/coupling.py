"""E3 - two-waveguide coupling coefficients.

Two independent numerical routes are implemented and cross-validated:

1. **Supermode splitting** - for two identical parallel cores the even and odd
   supermodes are obtained from two symmetry-reduced 2-D scalar eigenproblems
   (Neumann / Dirichlet on the mirror plane).  This is numerically exact for the
   scalar model because both solves share the identical operator except for one
   boundary row, so the splitting is not limited by the ~1e-7 relative accuracy
   of an absolute eigenvalue.

       Delta n_eff = |n_even - n_odd|,      kappa = pi * Delta n_eff / lambda.

2. **Overlap (perturbation) integral** - valid for large separations where the
   supermode splitting falls below the eigensolver noise floor:

       kappa = k0^2/(2 beta) * int (n2^2 - n_clad^2) psi1 psi2 dA / int psi1^2 dA.

At separations where both are trustworthy they must agree; the deviation is
reported as part of the model validation.

All kappa are returned in mm^-1 (lambda in mm), all distances in um.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import eigsh

from .config import CONFIG
from .modes import ModeSolution, index_grid, solve_modes


# --------------------------------------------------------------- 2-D operators
def _laplacian_stretched(nx: int, ny: int, h: float):
    """5-point Laplacian, row-major indexing (iy*nx + ix)."""
    N = nx * ny
    main = -4.0 * np.ones(N)
    offx = np.ones(N)
    offx[np.arange(1, ny) * nx - 1] = 0.0
    offx[-1] = 0.0
    offy = np.ones(N)
    offy[-nx:] = 0.0
    return sp.diags(
        [main / h ** 2, offx[:-1] / h ** 2, offx[:-1] / h ** 2,
         offy[:-nx] / h ** 2, offy[:-nx] / h ** 2],
        [0, 1, -1, nx, -nx], format="csr",
    )


# ---------------------------------------------------------------- overlap kappa
def kappa_overlap(optics: dict, sol, d_um: float,
                  dz_um: float = 0.0, mode: int = 0) -> float:
    """Perturbation overlap integral for two identical guides (mm^-1)."""
    x, y = sol.x, sol.y
    f1 = sol.fields[mode]
    interp = sol.interpolator(mode)
    X, Y = np.meshgrid(x, y)
    n2 = index_grid(x - d_um, y - dz_um, optics)
    n0 = float(optics["n_clad"])
    delta = n2 ** 2 - n0 ** 2
    f2 = interp(X - d_um, Y - dz_um)
    dA = sol.dA
    num = float(np.sum(delta * f1 * f2 * dA))
    den = float(np.sum(f1 ** 2 * dA))
    beta = float(sol.beta[mode])
    kappa_per_um = sol.k0 ** 2 / (2.0 * beta) * num / den
    return float(kappa_per_um * 1e3)          # 1/um -> 1/mm


# ------------------------------------------------------------- supermode kappa
def supermode_kappa(optics: dict, d_um: float, axis: str = "x",
                    grid_um: float | None = None,
                    n_modes: int = 2) -> dict:
    """Even/odd supermode splitting for two parallel identical cores.

    ``axis='x'``: cores at x = +-d/2 (horizontal, same height).
    ``axis='y'``: cores at y = +-d/2 (vertical offset, same lateral position).
    Only the half domain is discretised; the mirror plane boundary condition
    selects the even (Neumann) or odd (Dirichlet) supermode.
    """
    grid_um = float(grid_um if grid_um is not None else CONFIG["mode_solver"]["grid_um"])
    w = float(optics["core_width_um"])
    hgt = float(optics["core_height_um"])
    lam_um = float(optics["wavelength_nm"]) * 1e-3
    k0 = 2.0 * math.pi / lam_um
    n0 = float(optics["n_clad"])
    dn = float(optics["delta_n"])
    nc = n0 + dn
    profile = optics.get("profile", "step")

    if axis == "x":
        Lx = d_um / 2.0 + 14.0
        Ly = max(14.0, hgt)
        nxa = int(round(Lx / grid_um)) + 1
        nya = int(round(2 * Ly / grid_um)) + 1
        xa = np.arange(nxa) * grid_um          # 0 .. Lx, mirror plane at x=0
        ya = (np.arange(nya) - (nya - 1) / 2.0) * grid_um
        X, Y = np.meshgrid(xa, ya)
        # core centred at (d/2, 0); the mirror core is implied by the BC
        if profile == "step":
            n2 = np.where((np.abs(X - d_um / 2.0) <= w / 2.0) & (np.abs(Y) <= hgt / 2.0),
                          nc ** 2, n0 ** 2)
        else:
            r2 = (2 * (X - d_um / 2.0) / w) ** 2 + (2 * Y / hgt) ** 2
            n2 = (n0 + dn * np.exp(-math.log(2.0) * r2)) ** 2
        # x-boundary: Dirichlet at Lx; mirror plane handled separately
        n2[:, -1] = n0 ** 2
        n2[0, :] = n2[-1, :] = n0 ** 2
    elif axis == "y":
        Ly = d_um / 2.0 + 14.0
        Lx = max(14.0, w)
        nxa = int(round(2 * Lx / grid_um)) + 1
        nya = int(round(Ly / grid_um)) + 1
        xa = (np.arange(nxa) - (nxa - 1) / 2.0) * grid_um
        ya = np.arange(nya) * grid_um
        X, Y = np.meshgrid(xa, ya)
        if profile == "step":
            n2 = np.where((np.abs(X) <= w / 2.0) & (np.abs(Y - d_um / 2.0) <= hgt / 2.0),
                          nc ** 2, n0 ** 2)
        else:
            r2 = (2 * X / w) ** 2 + (2 * (Y - d_um / 2.0) / hgt) ** 2
            n2 = (n0 + dn * np.exp(-math.log(2.0) * r2)) ** 2
        n2[-1, :] = n0 ** 2
        n2[:, 0] = n2[:, -1] = n0 ** 2
    else:
        raise ValueError(axis)

    ny, nx = n2.shape
    sigma = (k0 * nc) ** 2 * (1.0 - 1e-6)
    results = {}
    for bc in ("even", "odd"):
        # Mirror plane is the x=0 column for axis='x' and the y=0 row for
        # axis='y'.  For the even supermode the mirror node is kept and the
        # ghost node doubles the coupling to the first interior neighbour.
        if axis == "x":
            iy0, iy1 = 1, ny - 1
            ix0, ix1 = (0, nx - 1) if bc == "even" else (1, nx - 1)
        else:
            iy0, iy1 = (0, ny - 1) if bc == "even" else (1, ny - 1)
            ix0, ix1 = 1, nx - 1
        sub = n2[iy0:iy1, ix0:ix1]
        sny, snx = sub.shape
        L = _laplacian_stretched(snx, sny, grid_um)
        A = (L + sp.diags(k0 ** 2 * sub.ravel())).tocsc()
        if bc == "even":
            A = A.tolil()
            if axis == "x":
                for j in range(sny):
                    r = j * snx
                    A[r, r + 1] = 2.0 / grid_um ** 2
            else:
                for i in range(snx):
                    A[i, i + snx] = 2.0 / grid_um ** 2
            A = A.tocsc()
        vals, vecs = eigsh(A, k=n_modes, sigma=sigma, which="LM",
                           tol=1e-12, maxiter=40000)
        order = np.argsort(vals)[::-1]
        vals = vals[order]
        results[bc] = np.sqrt(np.clip(vals[0], 0.0, None)) / k0
    dn_eff = abs(results["even"] - results["odd"])
    lam_mm = float(optics["wavelength_nm"]) * 1e-6
    kappa = math.pi * dn_eff / lam_mm
    return {
        "n_eff_even": float(results["even"]),
        "n_eff_odd": float(results["odd"]),
        "delta_n_eff": float(dn_eff),
        "kappa_mm_inv": float(kappa),
        "d_um": float(d_um),
        "axis": axis,
        "grid_um": grid_um,
    }



# --------------------------------------------------------------- coupling model
@dataclass
class CouplingModel:
    """kappa(d) for two identical guides, with an explicit validity range.

    * ``d_lo .. d_hi``  : supermode splitting, numerically resolved.
    * ``d > d_hi``      : exponential extrapolation with the fitted decay
                          constant gamma (the mode tail is evanescent and
                          isotropic in a homogeneous cladding, so the same
                          gamma applies to lateral and vertical offsets).
    * ``d < d_lo``      : clamped (cores overlap; the two-mode picture is not
                          valid there and crossings are handled by the local
                          FDFD solver instead).
    """
    optics: dict
    label: str
    d_um: np.ndarray
    kappa_mm_inv: np.ndarray
    gamma_per_um: float
    d_lo: float
    d_hi: float
    kappa_floor: float
    kappa_ceiling: float
    overlap_rows: list[dict]

    def __post_init__(self):
        self._logk = np.log(np.clip(self.kappa_mm_inv, self.kappa_floor, None))
        self._d = np.asarray(self.d_um, float)
        self.kappa_at_hi = float(np.exp(self._logk[-1]))

    def kappa(self, d_um):
        d_arr = np.asarray(d_um, dtype=float)
        shape = d_arr.shape
        d = np.atleast_1d(d_arr).reshape(-1)
        out = np.empty_like(d)
        inside = (d >= self.d_lo) & (d <= self.d_hi)
        out[inside] = np.exp(np.interp(d[inside], self._d, self._logk))
        high = d > self.d_hi
        out[high] = self.kappa_at_hi * np.exp(-self.gamma_per_um * (d[high] - self.d_hi))
        low = d < self.d_lo
        out[low] = float(np.exp(self._logk[0]))       # clamped validity limit
        out = np.clip(out, self.kappa_floor, self.kappa_ceiling)
        return float(out[0]) if shape == () else out.reshape(shape)

    def gamma_db_per_um(self) -> float:
        return float(10.0 * np.log10(np.e) * self.gamma_per_um)


def build_coupling_model(optics: dict, label: str, d_max_um: float = 24.0,
                         step_um: float = 0.8, validate_overlap: bool = True,
                         half_um: float = 70.0) -> tuple[CouplingModel, list[dict]]:
    from .modes import solve_modes_graded

    cfg = CONFIG["coupling"]
    w = float(optics["core_width_um"])
    d_lo = 1.2 * w
    ds = np.arange(d_lo, d_max_um + 1e-9, step_um)
    sol = solve_modes_graded(optics, half_um=half_um) if validate_overlap else None
    rows: list[dict] = []
    ks: list[float] = []
    for d in ds:
        sm = supermode_kappa(optics, float(d), "x")
        ko = kappa_overlap(optics, sol, float(d)) if sol is not None else float("nan")
        row = {
            "parameter_set": label,
            "wavelength_nm": optics["wavelength_nm"],
            "delta_n": optics["delta_n"],
            "core_width_um": w,
            "core_height_um": optics["core_height_um"],
            "profile": optics["profile"],
            "separation_um": float(d),
            "kappa_supermode_mm_inv": sm["kappa_mm_inv"],
            "kappa_overlap_mm_inv": float(ko),
            "n_eff_even": sm["n_eff_even"],
            "n_eff_odd": sm["n_eff_odd"],
            "delta_n_eff": sm["delta_n_eff"],
            "method": "supermode",
            "validity": "computed",
            "extrapolated": 0,
        }
        if np.isfinite(ko) and ko > 1e-9:
            row["relative_difference"] = abs(sm["kappa_mm_inv"] - ko) / max(ko, 1e-30)
        else:
            row["relative_difference"] = float("nan")
        rows.append(row)
        ks.append(float(sm["kappa_mm_inv"]))

    # decay constant from the clean far-tail range
    fit_lo = max(float(ds[0]), 14.0)
    fit = (ds >= fit_lo)
    if fit.sum() >= 3 and np.all(np.asarray(ks)[fit] > 0):
        A = np.vstack([ds[fit], np.ones(fit.sum())]).T
        slope, _ = np.linalg.lstsq(A, np.log(np.asarray(ks)[fit]), rcond=None)[0]
        gamma = float(-slope)
    else:  # pragma: no cover
        gamma = 0.45
    model = CouplingModel(
        optics=optics, label=label, d_um=np.asarray(ds, float),
        kappa_mm_inv=np.asarray(ks, float), gamma_per_um=gamma,
        d_lo=float(d_lo), d_hi=float(ds[-1]),
        kappa_floor=float(cfg["kappa_floor_mm_inv"]),
        kappa_ceiling=float(cfg["kappa_ceiling_mm_inv"]),
        overlap_rows=rows,
    )
    # append the extrapolated part of the reusable database
    for d in np.concatenate([np.arange(d_max_um + 2.0, 60.0 + 1e-9, 2.0),
                             np.arange(62.0, 121.0, 4.0)]):
        rows.append({
            "parameter_set": label,
            "wavelength_nm": optics["wavelength_nm"],
            "delta_n": optics["delta_n"],
            "core_width_um": w,
            "core_height_um": optics["core_height_um"],
            "profile": optics["profile"],
            "separation_um": float(d),
            "kappa_supermode_mm_inv": float(model.kappa(d)),
            "kappa_overlap_mm_inv": float("nan"),
            "n_eff_even": float("nan"), "n_eff_odd": float("nan"),
            "delta_n_eff": float("nan"),
            "method": "exponential_extrapolation",
            "validity": "extrapolated",
            "extrapolated": 1,
            "relative_difference": float("nan"),
        })
    return model, rows


def reference_separations() -> list[float]:
    return [0.0, 5.0, 9.0, 12.0, 15.0, 20.0, 30.0, 40.0, 50.0, 60.0,
            75.0, 100.0]
