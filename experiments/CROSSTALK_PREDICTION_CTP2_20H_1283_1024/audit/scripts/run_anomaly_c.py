"""ANOMALY C - the 50 um supermode kappa anomaly.

Reproduces coupling.supermode_kappa(REF, 50, axis='y') = 1.04e-4 mm^-1 and
shows (a) that it is eigennoise / operator-difference artefact, (b) which kappa
is physical.  Implements, side by side:

  * legacy half-domain even/odd construction (including the broken Neumann
    ghost node: diagonal left at -4/h^2 instead of -2/h^2)
  * corrected Neumann ghost node
  * full-domain two-core solve (no symmetry reduction -> both branches share
    one matrix, common-mode errors cancel)
  * shift / tolerance sweeps and eigsh residual estimates
  * converged 1-D EIM overlap kappa(d) and the asymptotic kappa0 exp(-gamma d)

Outputs: supermode_kappa_vs_d.csv, c_full_domain.csv, c_settings_sweep.csv,
         c_summary.json
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
from src.coupling import _laplacian_stretched, kappa_overlap

OUT = AL.AUDIT
CONFIG = AL.CONFIG


# ------------------------------------------------------------------ operators
def _build_half_domain(optics, d_um, axis, grid):
    w = float(optics["core_width_um"])
    hgt = float(optics["core_height_um"])
    lam_um = float(optics["wavelength_nm"]) * 1e-3
    k0 = 2.0 * math.pi / lam_um
    n0 = float(optics["n_clad"])
    dn = float(optics["delta_n"])
    nc = n0 + dn
    if axis == "x":
        Lx = d_um / 2.0 + 14.0
        Ly = max(14.0, hgt)
        nxa = int(round(Lx / grid)) + 1
        nya = int(round(2 * Ly / grid)) + 1
        xa = np.arange(nxa) * grid
        ya = (np.arange(nya) - (nya - 1) / 2.0) * grid
        X, Y = np.meshgrid(xa, ya)
        n2 = np.where((np.abs(X - d_um / 2.0) <= w / 2.0) & (np.abs(Y) <= hgt / 2.0),
                      nc ** 2, n0 ** 2)
        n2[:, -1] = n0 ** 2
        n2[0, :] = n2[-1, :] = n0 ** 2
        mirror_axis = 0
    else:
        Ly = d_um / 2.0 + 14.0
        Lx = max(14.0, w)
        nxa = int(round(2 * Lx / grid)) + 1
        nya = int(round(Ly / grid)) + 1
        xa = (np.arange(nxa) - (nxa - 1) / 2.0) * grid
        ya = np.arange(nya) * grid
        X, Y = np.meshgrid(xa, ya)
        n2 = np.where((np.abs(X) <= w / 2.0) & (np.abs(Y - d_um / 2.0) <= hgt / 2.0),
                      nc ** 2, n0 ** 2)
        n2[-1, :] = n0 ** 2
        n2[:, 0] = n2[:, -1] = n0 ** 2
        mirror_axis = 1
    return dict(n2=n2, xa=xa, ya=ya, grid=grid, k0=k0, nc=nc, n0=n0,
                mirror_axis=mirror_axis, axis=axis)


def _half_matrix(geo, bc, ghost):
    """Half-domain matrix. ghost in {'legacy','correct'}."""
    grid = geo["grid"]
    n2 = geo["n2"]
    ny, nx = n2.shape
    k0 = geo["k0"]
    if geo["axis"] == "x":
        iy0, iy1 = 1, ny - 1
        ix0, ix1 = (0, nx - 1) if bc == "even" else (1, nx - 1)
    else:
        iy0, iy1 = (0, ny - 1) if bc == "even" else (1, ny - 1)
        ix0, ix1 = 1, nx - 1
    sub = n2[iy0:iy1, ix0:ix1]
    sny, snx = sub.shape
    L = _laplacian_stretched(snx, sny, grid)
    A = (L + sp.diags(k0 ** 2 * sub.ravel())).tolil()
    if bc == "even":
        if geo["axis"] == "x":
            for j in range(sny):
                r = j * snx
                A[r, r + 1] = 2.0 / grid ** 2
                if ghost == "correct":
                    A[r, r] += 2.0 / grid ** 2
        else:
            for i in range(snx):
                A[i, i + snx] = 2.0 / grid ** 2
                if ghost == "correct":
                    A[i, i] += 2.0 / grid ** 2
    return A.tocsc(), sub.shape


def solve_half(optics, d_um, axis="x", grid=0.2, ghost="legacy",
               sigma_offset=1e-6, tol=1e-12, n_modes=2, maxiter=40000):
    geo = _build_half_domain(optics, d_um, axis, grid)
    k0, nc = geo["k0"], geo["nc"]
    sigma = (k0 * nc) ** 2 * (1.0 - sigma_offset)
    out = {}
    for bc in ("even", "odd"):
        A, shape = _half_matrix(geo, bc, ghost)
        vals, vecs = eigsh(A, k=n_modes, sigma=sigma, which="LM", tol=tol,
                           maxiter=maxiter)
        order = np.argsort(vals)[::-1]
        vals, vecs = vals[order], vecs[:, order]
        lam = float(vals[0])
        x = vecs[:, 0]
        resid = float(np.linalg.norm(A @ x - lam * x) / max(np.linalg.norm(x), 1e-300))
        out[bc] = {"Lambda": lam, "n_eff": math.sqrt(max(lam, 0.0)) / k0,
                   "residual": resid, "shape": shape, "all_vals": vals,
                   "vec": x}
    out["delta_n_eff"] = abs(out["even"]["n_eff"] - out["odd"]["n_eff"])
    lam_mm = float(optics["wavelength_nm"]) * 1e-6
    out["kappa_mm_inv"] = math.pi * out["delta_n_eff"] / lam_mm
    out["d_um"] = d_um
    out["axis"] = axis
    out["grid"] = grid
    out["ghost"] = ghost
    out["sigma"] = sigma
    return out


def solve_full_domain(optics, d_um, axis="x", grid=0.2, n_modes=4,
                      sigma_offset=1e-6, tol=1e-12):
    """Two-core full-domain solve: both supermodes from ONE matrix."""
    w = float(optics["core_width_um"])
    hgt = float(optics["core_height_um"])
    lam_um = float(optics["wavelength_nm"]) * 1e-3
    k0 = 2.0 * math.pi / lam_um
    n0 = float(optics["n_clad"])
    dn = float(optics["delta_n"])
    nc = n0 + dn
    Lperp = 14.0
    if axis == "x":
        Lx = d_um / 2.0 + Lperp
        Ly = max(14.0, hgt)
        nx = int(round(2 * Lx / grid)) + 1
        ny = int(round(2 * Ly / grid)) + 1
        x = (np.arange(nx) - (nx - 1) / 2.0) * grid
        y = (np.arange(ny) - (ny - 1) / 2.0) * grid
        X, Y = np.meshgrid(x, y)
        inside = ((np.abs(np.abs(X) - d_um / 2.0) <= w / 2.0) & (np.abs(Y) <= hgt / 2.0))
    else:
        Ly = d_um / 2.0 + Lperp
        Lx = max(14.0, w)
        nx = int(round(2 * Lx / grid)) + 1
        ny = int(round(2 * Ly / grid)) + 1
        x = (np.arange(nx) - (nx - 1) / 2.0) * grid
        y = (np.arange(ny) - (ny - 1) / 2.0) * grid
        X, Y = np.meshgrid(x, y)
        inside = ((np.abs(X) <= w / 2.0) & (np.abs(np.abs(Y) - d_um / 2.0) <= hgt / 2.0))
    n2 = np.where(inside, nc ** 2, n0 ** 2)
    n2[0, :] = n2[-1, :] = n2[:, 0] = n2[:, -1] = n0 ** 2
    m = (nx - 2) * (ny - 2)
    L = _laplacian_stretched(nx - 2, ny - 2, grid)
    A = (L + sp.diags(k0 ** 2 * n2[1:-1, 1:-1].ravel())).tocsc()
    sigma = (k0 * nc) ** 2 * (1.0 - sigma_offset)
    vals, vecs = eigsh(A, k=n_modes, sigma=sigma, which="LM", tol=tol,
                       maxiter=80000)
    order = np.argsort(vals)[::-1]
    vals, vecs = vals[order], vecs[:, order]
    # classify by parity about the mirror plane
    info = []
    for k in range(len(vals)):
        f = vecs[:, k].reshape(ny - 2, nx - 2)
        lam = float(vals[k])
        # parity: compare f and its mirror image
        if axis == "x":
            # mirror about x=0: grid is symmetric because nx odd
            fm = f[:, ::-1]
        else:
            fm = f[::-1, :]
        asym = float(np.linalg.norm(f - fm) / max(np.linalg.norm(f), 1e-300))
        resid = float(np.linalg.norm(A @ vecs[:, k] - lam * vecs[:, k])
                      / max(np.linalg.norm(vecs[:, k]), 1e-300))
        info.append({"Lambda": lam, "n_eff": math.sqrt(max(lam, 0.0)) / k0,
                     "asymmetry": asym, "residual": resid})
    # even: most symmetric (asym smallest); odd: most antisymmetric
    i_even = int(np.argmin([r["asymmetry"] for r in info]))
    i_odd = int(np.argmax([r["asymmetry"] for r in info]))
    dn = abs(info[i_even]["n_eff"] - info[i_odd]["n_eff"])
    lam_mm = float(optics["wavelength_nm"]) * 1e-6
    return {"d_um": d_um, "axis": axis, "grid": grid,
            "n_eff_even": info[i_even]["n_eff"],
            "n_eff_odd": info[i_odd]["n_eff"],
            "delta_n_eff": float(dn),
            "kappa_mm_inv": float(math.pi * dn / lam_mm),
            "residual_even": info[i_even]["residual"],
            "residual_odd": info[i_odd]["residual"],
            "asymmetry_even": info[i_even]["asymmetry"],
            "asymmetry_odd": info[i_odd]["asymmetry"],
            "modes": info}


def main():
    opt, eim = AL.beam()
    lam_mm = float(opt["wavelength_nm"]) * 1e-6
    kap1d = PK.load_or_build_kappa(opt)
    print(f"1-D EIM mode: n_eff={kap1d['n_eff']:.9f} beta={kap1d['beta']:.6f}/um "
          f"gamma={kap1d['gamma']:.6f}/um", flush=True)

    # ---------------------------------------------------- 1. reproduce the anomaly
    print("\n== legacy supermode_kappa(REF, 50) ==", flush=True)
    from src.coupling import supermode_kappa
    repro = {}
    for axis in ("y", "x"):
        s = supermode_kappa(opt, 50.0, axis=axis)
        repro[axis] = s
        print(f"  axis={axis}: n_even={s['n_eff_even']:.12f} "
              f"n_odd={s['n_eff_odd']:.12f} dn={s['delta_n_eff']:.4e} "
              f"kappa={s['kappa_mm_inv']:.4e} /mm", flush=True)

    # ------------------------------ 1b. run-to-run reproducibility of legacy code
    print("\n== reproducibility: supermode_kappa(REF,50) repeated 8x ==", flush=True)
    reps = []
    for k in range(8):
        sy = supermode_kappa(opt, 50.0, axis="y")
        sx = supermode_kappa(opt, 50.0, axis="x")
        reps.append({"axis_y_dn": sy["delta_n_eff"], "axis_y_kappa": sy["kappa_mm_inv"],
                     "axis_x_dn": sx["delta_n_eff"], "axis_x_kappa": sx["kappa_mm_inv"]})
        print(f"  run {k}: y dn={sy['delta_n_eff']:.4e} kappa={sy['kappa_mm_inv']:.4e}"
              f" | x dn={sx['delta_n_eff']:.4e} kappa={sx['kappa_mm_inv']:.4e}", flush=True)
    ry = [r["axis_y_kappa"] for r in reps]
    rx = [r["axis_x_kappa"] for r in reps]
    print(f"  axis=y kappa range {min(ry):.4e}..{max(ry):.4e} "
          f"(factor {max(ry)/max(min(ry), 1e-300):.2f})")
    print(f"  axis=x kappa range {min(rx):.4e}..{max(rx):.4e} "
          f"(factor {max(rx)/max(min(rx), 1e-300):.2f})")
    repro["reproducibility_50um"] = reps

    # --------------------------------------------------------- 2. d sweep table
    d_grid = [10.0, 12.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 60.0, 80.0, 100.0]
    rows = []
    kappa_asym_tab = {}
    for axis in ("x", "y"):
        for d in d_grid:
            s = supermode_kappa(opt, d, axis=axis)
            kap_asym, k0fit, gam = PK.kappa_asymptotic(opt, d)
            kappa_asym_tab[(axis, d)] = kap_asym
            # eigsh residual estimate for each branch (legacy construction)
            hl = solve_half(opt, d, axis=axis, grid=0.2, ghost="legacy")
            resid = max(hl["even"]["residual"], hl["odd"]["residual"])
            # kappa_overlap: legacy 2-D graded mode only trusted for d<=20
            if d <= 20.0:
                try:
                    solg = AL.solve_modes_graded(opt, half_um=70.0)
                    ko = kappa_overlap(opt, solg, d)
                except Exception:
                    ko = float("nan")
            else:
                ko = float("nan")
            ko1d = float(np.atleast_1d(PK.kappa_eim(opt, d, kap1d))[0])
            rows.append({
                "d_um": d, "axis": axis,
                "n_eff_even": s["n_eff_even"], "n_eff_odd": s["n_eff_odd"],
                "delta_n_eff": s["delta_n_eff"],
                "kappa_supermode_mm_inv": s["kappa_mm_inv"],
                "kappa_overlap_mm_inv": ko if np.isfinite(ko) else ko1d,
                "kappa_overlap_1d_eim_mm_inv": ko1d,
                "kappa_asymptotic_mm_inv": kap_asym,
                "eig_residual": resid,
                "numerically_resolved": "no",
            })
            print(f"  axis={axis} d={d:6.1f}  dn_super={s['delta_n_eff']:.4e} "
                  f"kappa_super={s['kappa_mm_inv']:.4e} "
                  f"kappa_1d={ko1d:.4e} kappa_asym={kap_asym:.4e} "
                  f"resid={resid:.2e}", flush=True)

    # ------------------------------------------------- 3. solver-settings sweep
    sweep = []
    for d in (20.0, 50.0):
        for axis in ("x", "y"):
            base = solve_half(opt, d, axis=axis, grid=0.2, ghost="legacy")
            for ghost in ("legacy", "correct"):
                for sig_off in (1e-6, 1e-4, 1e-3):
                    for tol in (1e-10, 1e-12, 1e-14):
                        r = solve_half(opt, d, axis=axis, grid=0.2, ghost=ghost,
                                       sigma_offset=sig_off, tol=tol)
                        sweep.append({"d_um": d, "axis": axis, "ghost": ghost,
                                      "sigma_offset": sig_off, "tol": tol,
                                      "n_eff_even": r["even"]["n_eff"],
                                      "n_eff_odd": r["odd"]["n_eff"],
                                      "delta_n_eff": r["delta_n_eff"],
                                      "kappa_mm_inv": r["kappa_mm_inv"],
                                      "resid_even": r["even"]["residual"],
                                      "resid_odd": r["odd"]["residual"]})
            print(f"  settings sweep d={d} axis={axis} done", flush=True)
    # spread of kappa across settings for the same (d,axis,ghost)
    spread = {}
    for rec in sweep:
        key = (rec["d_um"], rec["axis"], rec["ghost"])
        spread.setdefault(key, []).append(rec["kappa_mm_inv"])
    print("\n== kappa spread across solver settings ==", flush=True)
    for key, v in sorted(spread.items()):
        print(f"  {key}: min={min(v):.4e} max={max(v):.4e} spread={max(v)-min(v):.2e}",
              flush=True)

    # ----------------------------------------------- 4. full-domain independent
    full = []
    for d in (15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 60.0, 80.0, 100.0):
        for axis in ("x", "y"):
            try:
                r = solve_full_domain(opt, d, axis=axis, grid=0.2)
                full.append({"d_um": d, "axis": axis,
                             "n_eff_even": r["n_eff_even"],
                             "n_eff_odd": r["n_eff_odd"],
                             "delta_n_eff": r["delta_n_eff"],
                             "kappa_mm_inv": r["kappa_mm_inv"],
                             "residual_even": r["residual_even"],
                             "residual_odd": r["residual_odd"],
                             "asym_even": r["asymmetry_even"],
                             "asym_odd": r["asymmetry_odd"],
                             "kappa_asymptotic": kappa_asym_tab[(axis, d)]})
                print(f"  full-domain axis={axis} d={d:6.1f} "
                      f"dn={r['delta_n_eff']:.4e} kappa={r['kappa_mm_inv']:.4e} "
                      f"resid={max(r['residual_even'], r['residual_odd']):.2e}",
                      flush=True)
            except Exception as exc:
                print(f"  full-domain axis={axis} d={d} FAILED: {exc}", flush=True)

    # ------------------------------- 5. mark numerically resolved (|dn| > 100 x spread)
    for rec in rows:
        key_leg = (rec["d_um"], rec["axis"], "legacy")
        key_cor = (rec["d_um"], rec["axis"], "correct")
        s_leg = spread.get(key_leg, [])
        spread_leg = (max(s_leg) - min(s_leg)) if s_leg else float("nan")
        # compare with the physical/asymptotic value
        phys = rec["kappa_asymptotic_mm_inv"]
        resolved = (np.isfinite(spread_leg) and rec["kappa_supermode_mm_inv"]
                    > 100.0 * max(spread_leg, phys, 1e-300))
        rec["numerically_resolved"] = "yes" if resolved else "no"
        rec["kappa_setting_spread"] = spread_leg
    AL.write_csv(OUT / "supermode_kappa_vs_d.csv", rows)
    AL.write_csv(OUT / "c_settings_sweep.csv", sweep)
    AL.write_csv(OUT / "c_full_domain.csv", full)
    summary = {"reproduction": repro,
               "kappa_spread_across_settings": {"|".join(map(str, k)): [min(v), max(v)]
                                                for k, v in spread.items()},
               "d_sweep": rows,
               "full_domain": full,
               "physical_kappa_50um": {"overlap_1d_eim": float(np.atleast_1d(
                   PK.kappa_eim(opt, 50.0, kap1d))[0]),
                   "asymptotic": float(np.atleast_1d(
                       PK.kappa_asymptotic(opt, 50.0)[0])[0])}}
    AL.jdump(OUT / "c_summary.json", summary)
    print("\n[ANOMALY C] done")


if __name__ == "__main__":
    main()
