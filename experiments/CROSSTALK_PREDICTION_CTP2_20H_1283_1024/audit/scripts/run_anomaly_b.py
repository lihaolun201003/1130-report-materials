"""ANOMALY B - T_through > 1 and the honest FDFD numerical floor.

1. legacy T_through-1 decomposed as 2 Re(a1)+|a1|^2 with a1 = projection of the
   legacy scattered field onto the legacy "mode" (reproduced exactly).
2. legacy no_cross control: proved to be a *null* control (rhs == 0).
3. corrected solver: grid / PML strength / PML thickness / domain-margin sweeps
   at theta = 90 deg, where the physical crosstalk is ~1e-11 (verified in A),
   so any measured T_cross is the numerical floor.
4. corrected solver: linearity (empty-domain) control with a scaled crossing-guide
   index perturbation (T_cross must scale as scale^2).
Outputs: b_legacy_terms.csv, b_floor_sweep.csv, b_linearity.csv, b_summary.json
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import audit_lib as AL
import ctp2_corrected as CC

OUT = AL.AUDIT
CACHE = AL.CACHE


def legacy_a1_terms(opt, theta, leg):
    """Reproduce the legacy port-1 projection a1[0] and decompose T_through-1."""
    h = float(leg["grid"])
    beta = float(leg["beta_disc"])
    x = np.asarray(leg["x"])
    full = np.asarray(leg["full"])
    phi = np.asarray(leg["phi"])
    Lx = float(np.asarray(leg["domain"])[0]) / 2.0
    pml = 5.0
    x1 = Lx - pml - 3.0 * h
    i1 = int(round((x1 - x[0]) / h))
    col = full[1:-1, i1]
    a1_0 = np.sum(col * phi[1:-1]) * h * np.exp(-1j * beta * x[i1])
    # higher "modes" are not stored; report only the fundamental term
    T_leg = float(leg["T_through"])
    return {"theta_deg": theta, "a1_real": float(a1_0.real),
            "a1_imag": float(a1_0.imag), "a1_abs": float(abs(a1_0)),
            "T_through_reported": T_leg,
            "T_through_minus_1": T_leg - 1.0,
            "2Re_a1": 2.0 * float(a1_0.real),
            "abs_a1_sq": float(abs(a1_0) ** 2),
            "residual": T_leg - 1.0 - 2.0 * float(a1_0.real) - float(abs(a1_0) ** 2),
            "x1_um": float(x1), "grid": h}


def run_corrected(opt, th, grid, pml, strength, bounds=None, tag="", scale=1.0):
    p = CC.corrected_cache_path(th, grid, 10.0, pml, strength,
                                f"_b{tag}_sc{scale:g}")
    if p.exists():
        d = np.load(p)
        return {k: (d[k] if d[k].ndim else float(d[k])) for k in d.files}
    r = CC.solve_crossing_corrected(opt, th, grid_um=grid, d_port_um=10.0,
                                    pml_um=pml, pml_strength=strength,
                                    max_unknowns=1_200_000, bounds=bounds,
                                    cross_scale=scale)
    np.savez_compressed(
        p, theta=np.float64(r["theta"]), grid=np.float64(r["grid"]),
        pml=np.float64(r["pml"]), strength=np.float64(r["strength"]),
        Lx=np.float64(r["Lx"]), Ly=np.float64(r["Ly"]),
        bounds=np.asarray(r["bounds"], float), unknowns=np.int64(r["unknowns"]),
        n_eff_disc=np.float64(r["n_eff_disc"]), n_eff=np.float64(r["n_eff"]),
        beta_disc=np.float64(r["beta_disc"]), n_slab=np.float64(r["n_slab"]),
        P_src=np.float64(r["P_src"]), flux_inc=np.float64(r["flux_inc"]),
        runtime=np.float64(r["runtime"]), x=r["x"], y=r["y"],
        psi_s=r["psi_s"], psi_inc=r["psi_inc"], phi=r["phi"])
    d = np.load(p)
    return {k: (d[k] if d[k].ndim else float(d[k])) for k in d.files}


def metrics(opt, th, d):
    dd = dict(x=np.asarray(d["x"]), y=np.asarray(d["y"]),
              psi_s=np.asarray(d["psi_s"]), psi_inc=np.asarray(d["psi_inc"]),
              phi=np.asarray(d["phi"]), beta_disc=float(d["beta_disc"]),
              grid=float(d["grid"]), pml=float(d["pml"]),
              Lx=float(d["Lx"]), Ly=float(d["Ly"]), P_src=float(d["P_src"]),
              theta=th, bounds=d.get("bounds"), n_slab=float(d["n_slab"]))
    pa = CC.port_analysis2(dd, opt, theta_deg=th)
    return pa


def main():
    opt, eim = AL.beam()
    summary = {"legacy_terms": [], "floor_sweep": [], "linearity": []}
    # ---------------------------------------------------------------- legacy terms
    print("== legacy T_through-1 decomposition ==", flush=True)
    for th in (5.0, 10.0, 15.0, 20.0, 30.0, 45.0, 60.0, 90.0):
        p = AL.crossing_cache_path(th, 0.15, 10.0, 5.0, 3.0, False)
        leg = np.load(p)
        r = legacy_a1_terms(opt, th, leg)
        summary["legacy_terms"].append(r)
        print(f"  theta={th:5.1f}  T-1={r['T_through_minus_1']:+.6e}  "
              f"2Re a1={r['2Re_a1']:+.6e}  |a1|^2={r['abs_a1_sq']:.3e}  "
              f"resid={r['residual']:+.2e}", flush=True)
    # legacy no_cross control
    print("== legacy no_cross control (theta=45) ==", flush=True)
    rn = AL.run_crossing_cached(opt, eim, 45.0, grid=0.15, d_port=10.0, pml=5.0,
                                strength=3.0, no_cross=True, tag="_nocross")
    d = rn[0]
    print(f"  legacy no_cross: T_through={float(d['T_through']):.12f} "
          f"T_cross={float(d['T_cross']):.3e} "
          f"max|psi_s|={np.abs(d['full']).max():.3e}  (rhs is identically 0)")
    summary["legacy_nocross"] = {"T_through": float(d["T_through"]),
                                 "T_cross": float(d["T_cross"]),
                                 "max_abs_psi_s": float(np.abs(d["full"]).max())}

    # ------------------------------------------------------------ corrected sweeps
    th = 90.0
    configs = []
    for g in (0.20, 0.15, 0.12, 0.10):
        configs.append(dict(tag=f"grid{g:g}", grid=g, pml=5.0, strength=3.0,
                            bounds=None))
    for s in (1.0, 6.0):
        configs.append(dict(tag=f"pml_str{s:g}", grid=0.15, pml=5.0, strength=s,
                            bounds=None))
    for pm in (3.0, 4.0, 6.0):
        configs.append(dict(tag=f"pml_th{pm:g}", grid=0.15, pml=pm, strength=3.0,
                            bounds=None))
    for yh in (25.0, 34.5, 45.0):
        configs.append(dict(tag=f"margin{yh:g}", grid=0.15, pml=5.0, strength=3.0,
                            bounds=dict(x_min=-39.0, x_max=39.0,
                                        y_min=-yh, y_max=yh)))
    print("== corrected 90 deg floor sweep ==", flush=True)
    for c in configs:
        r = run_corrected(opt, th, c["grid"], c["pml"], c["strength"],
                          bounds=c["bounds"], tag=c["tag"])
        pa = metrics(opt, th, r)
        row = {"config": c["tag"], "theta_deg": th, "grid": float(r["grid"]),
               "pml": float(r["pml"]), "strength": float(r["strength"]),
               "N": int(r["unknowns"]), "n_eff_disc": float(r["n_eff_disc"]),
               "T_through": pa["T_through"], "one_minus_T": 1 - pa["T_through"],
               "R": pa["R"], "T_cross_plus": pa["T_cross_plus"],
               "T_cross_minus": pa["T_cross_minus"], "T_cross": pa["T_cross"],
               "T_cross_db": AL.db(pa["T_cross"]), "radiation": pa["radiation"],
               "T_through_fund": pa["T_through_fund"],
               "T_through_higher": pa["T_through_higher"],
               "T_cross_fund": pa["T_cross_fund"],
               "T_cross_higher": pa["T_cross_higher"],
               "separation_at_port_um": pa["separation_at_port_um"],
               "P_src_norm": pa["P_src_norm"],
               "extinction_minus_Psrc": pa["extinction_minus_Psrc"],
               "sflux_minus_src": pa["sflux_minus_src"],
               "energy_1_minus_sum": pa["energy_1_minus_sum"],
               "arm_plateau_spread": float(np.std([x["power"] for x in pa["arms"]["cross_plus"]])
                                           / max(np.mean([x["power"] for x in pa["arms"]["cross_plus"]]), 1e-300))}
        summary["floor_sweep"].append(row)
        print(f"  {c['tag']:12s} grid={row['grid']:.3f} N={row['N']:6d} "
              f"T={row['T_through']:.9f} Tcross={row['T_cross']:.3e} "
              f"({row['T_cross_db']:.1f} dB) R={row['R']:.2e} "
              f"Psrc={row['P_src_norm']:.2e} ext-Psrc={row['extinction_minus_Psrc']:+.1e}",
              flush=True)

    # ------------------------------------------- linearity / empty-domain control
    print("== corrected theta=10 linearity control (crossing guide scaled) ==",
          flush=True)
    for sc in (1.0, 0.3, 0.1, 0.03):
        r = run_corrected(opt, 10.0, 0.15, 5.0, 3.0, tag="lin", scale=sc)
        pa = metrics(opt, 10.0, r)
        row = {"cross_scale": sc, "T_cross": pa["T_cross"],
               "T_cross_db": AL.db(pa["T_cross"]),
               "T_cross_over_scale2": pa["T_cross"] / sc ** 2,
               "R": pa["R"], "R_over_scale2": pa["R"] / sc ** 2,
               "P_src_norm": pa["P_src_norm"],
               "P_src_over_scale2": pa["P_src_norm"] / sc ** 2,
               "T_through": pa["T_through"]}
        summary["linearity"].append(row)
        print(f"  scale={sc:6.3f} T_cross={row['T_cross']:.4e} "
              f"T_cross/scale^2={row['T_cross_over_scale2']:.4e} "
              f"R/scale^2={row['R_over_scale2']:.3e} "
              f"Psrc/scale^2={row['P_src_over_scale2']:.4e}", flush=True)

    # ---------------- grid convergence at a *signal* angle (10 deg, coarse grids)
    print("== corrected theta=10 grid convergence ==", flush=True)
    grid_rows = []
    for g in (0.20, 0.15):
        r = run_corrected(opt, 10.0, g, 5.0, 3.0, tag="g10")
        pa = metrics(opt, 10.0, r)
        grid_rows.append({"theta_deg": 10.0, "grid": float(r["grid"]),
                          "N": int(r["unknowns"]),
                          "n_eff_disc": float(r["n_eff_disc"]),
                          "T_cross": pa["T_cross"], "T_cross_db": AL.db(pa["T_cross"]),
                          "T_through": pa["T_through"], "R": pa["R"],
                          "radiation": pa["radiation"], "P_src_norm": pa["P_src_norm"]})
        print(f"  theta=10 grid={grid_rows[-1]['grid']:.3f} "
              f"T_cross={pa['T_cross']:.4e} ({AL.db(pa['T_cross']):.2f} dB) "
              f"T_through={pa['T_through']:.6f} rad={pa['radiation']:.3e}", flush=True)
    summary["grid10"] = grid_rows
    AL.jdump(OUT / "b_summary.json", summary)
    AL.write_csv(OUT / "b_legacy_terms.csv", summary["legacy_terms"])
    AL.write_csv(OUT / "b_floor_sweep.csv", summary["floor_sweep"])
    AL.write_csv(OUT / "b_linearity.csv", summary["linearity"])
    AL.write_csv(OUT / "b_grid10.csv", grid_rows)
    print("[ANOMALY B] done")


if __name__ == "__main__":
    main()
