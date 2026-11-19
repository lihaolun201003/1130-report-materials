"""Extra anomaly-C check: the even-branch matrix is NON-SYMMETRIC.

`supermode_kappa` sets A[r, r+1] = 2/h^2 for the Neumann ghost node but leaves
A[r+1, r] = 1/h^2 and the diagonal at -4/h^2.  eigsh() assumes a symmetric
matrix, so the even-branch eigenvalues are not true eigenvalues of any
symmetric operator -> run-to-run noise and a spurious Delta n_eff.

This script quantifies the asymmetry, the corrected (symmetric Neumann) result,
and the convergence of the physically correct splitting to the overlap value.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import eigsh

import audit_lib as AL
import physical_kappa as PK
import run_anomaly_c as RC
from src.coupling import supermode_kappa

OUT = AL.AUDIT


def asym_metrics(A):
    A = A.tocsr()
    T = A.T.tocsr()
    D = (A - T)
    na = float(np.sqrt(np.sum(np.abs(A.data) ** 2)))
    nd = float(np.sqrt(np.sum(np.abs(D.data) ** 2)))
    return nd, nd / max(na, 1e-300)


def solve_half_symmetric(optics, d_um, axis, grid, ghost="legacy", tol=1e-13):
    """Half-domain solve with the ghost-node matrix used CORRECTLY.

    The legacy ghost-node stencil at the Neumann mirror node is the standard
    second-order one, but its matrix is non-symmetric (A[mirror,next]=2/h^2 vs
    A[next,mirror]=1/h^2).  It is similar to a symmetric matrix through the
    diagonal W = diag(sqrt(2) on the mirror row, 1 elsewhere):
        S = W^-1 A W,   S symmetric, same eigenvalues.
    eigsh() on S gives the valid Neumann eigenvalue; the legacy code instead
    feeds the non-symmetric A to eigsh() (symmetric Lanczos) -> invalid Ritz
    values, residuals 1e-2..1e-4, run-to-run scatter 30-258x.
    """
    geo = RC._build_half_domain(optics, d_um, axis, grid)
    k0, nc = geo["k0"], geo["nc"]
    sigma = (k0 * nc) ** 2 * (1.0 - 1e-6)
    out = {}
    for bc in ("even", "odd"):
        A, shape = RC._half_matrix(geo, bc, ghost)
        A = A.tocsr()
        if bc == "even":
            snx = shape[1]
            N = A.shape[0]
            w = np.ones(N)
            idx = np.arange(0, N, snx) if axis == "x" else np.arange(0, snx)
            w[idx] = math.sqrt(2.0)
            W = sp.diags(w)
            A = (sp.diags(1.0 / w) @ A @ W).tocsr()
        vals, vecs = eigsh(A, k=2, sigma=sigma, which="LM", tol=tol, maxiter=60000)
        order = np.argsort(vals)[::-1]
        vals, vecs = vals[order], vecs[:, order]
        x = vecs[:, 0]
        lam = float(vals[0])
        resid = float(np.linalg.norm(A @ x - lam * x) / max(np.linalg.norm(x), 1e-300))
        out[bc] = {"Lambda": lam, "n_eff": math.sqrt(max(lam, 0.0)) / k0,
                   "residual": resid}
    dn = abs(out["even"]["n_eff"] - out["odd"]["n_eff"])
    lam_mm = float(optics["wavelength_nm"]) * 1e-6
    out["delta_n_eff"] = dn
    out["kappa_mm_inv"] = math.pi * dn / lam_mm
    return out


def main():
    opt, eim = AL.beam()
    kap1d = PK.load_or_build_kappa(opt)
    res = {}
    print("== asymmetry of the legacy even-branch matrix ==", flush=True)
    for d in (15.0, 20.0, 50.0):
        for axis in ("x", "y"):
            geo = RC._build_half_domain(opt, d, axis, 0.2)
            A_leg, shp = RC._half_matrix(geo, "even", "legacy")
            A_cor, shp = RC._half_matrix(geo, "even", "correct")
            A_cor = A_cor.tocsr()
            snx = shp[1]; N = A_cor.shape[0]
            w = np.ones(N)
            w[np.arange(0, N, snx) if axis == "x" else np.arange(0, snx)] = math.sqrt(2.0)
            A_sym = (sp.diags(1.0 / w) @ A_cor @ sp.diags(w)).tocsr()
            nd_l, rel_l = asym_metrics(A_leg)
            nd_c, rel_c = asym_metrics(A_sym)
            print(f"  d={d:5.1f} axis={axis}: ||A-A^T||={nd_l:.4e} "
                  f"(||A||={np.sqrt(np.sum(A_leg.data**2)):.4e}, rel={rel_l:.3e})"
                  f"  | corrected rel={rel_c:.3e}", flush=True)
            res[f"asym_{axis}_{d:g}"] = {"norm_asym_legacy": nd_l,
                                        "rel_asym_legacy": rel_l,
                                        "rel_asym_corrected": rel_c}
    print("\n== legacy vs fully symmetric Neumann ghost ==", flush=True)
    rows = []
    for d in (10.0, 12.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 60.0):
        for axis in ("x", "y"):
            leg = RC.solve_half(opt, d, axis=axis, grid=0.2, ghost="legacy",
                                tol=1e-12)
            cor = solve_half_symmetric(opt, d, axis=axis, grid=0.2)
            kap1 = float(np.atleast_1d(PK.kappa_eim(opt, d, kap1d))[0])
            rows.append({"d_um": d, "axis": axis,
                         "kappa_legacy": leg["kappa_mm_inv"],
                         "kappa_corrected_symmetric": cor["kappa_mm_inv"],
                         "kappa_overlap_1d_eim": kap1,
                         "dn_legacy": leg["delta_n_eff"],
                         "dn_corrected": cor["delta_n_eff"],
                         "resid_legacy_even": leg["even"]["residual"],
                         "resid_legacy_odd": leg["odd"]["residual"],
                         "resid_corrected_even": cor["even"]["residual"],
                         "resid_corrected_odd": cor["odd"]["residual"]})
            print(f"  d={d:5.1f} axis={axis}: kappa legacy={leg['kappa_mm_inv']:.4e}"
                  f" corrected={cor['kappa_mm_inv']:.4e} "
                  f"overlap={kap1:.4e} | resid legacy even="
                  f"{leg['even']['residual']:.2e} corrected even="
                  f"{cor['even']['residual']:.2e}", flush=True)
    AL.write_csv(OUT / "c_extra_asymmetry.csv", rows)
    AL.jdump(OUT / "c_extra_asymmetry.json", res)
    print("[C-extra] done")


if __name__ == "__main__":
    main()
