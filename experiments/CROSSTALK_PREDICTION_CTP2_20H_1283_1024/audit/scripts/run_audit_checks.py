"""TARGETED VERIFICATION of the claims in the CTP-1.0 source and report.

Every number below is measured, not assumed.  Output: audit/checks_summary.json
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pandas as pd

import audit_lib as AL
import physical_kappa as PK
from src.board import build_board, db
from src.config import CONFIG
from src.crossing import crossing_born, crossing_cmt
from src.coupling import CouplingModel, build_coupling_model, supermode_kappa
from src.dataio import load_dataset
from src.modes import effective_index_model, solve_modes

OUT = AL.AUDIT


def main():
    opt = AL.reference_optics()
    res = {}
    print("== 1. mode solver: the '3 guided modes' claim ==")
    sol = solve_modes(opt)
    n_eff = sol.n_eff
    guided = sol.guided_mask
    print(f"  n_modes returned={len(n_eff)}  n_guided={int(guided.sum())}")
    print(f"  n_eff = {np.round(n_eff, 9)}")
    print(f"  n_clad={sol.n_clad} n_core={sol.n_core}")
    res["modes"] = {"n_eff": n_eff.tolist(), "guided": guided.tolist(),
                    "n_guided": int(guided.sum()),
                    "confinement": [float(sol.confinement(i)) for i in range(len(n_eff))]}
    print("  confinement(core) =", np.round(
        [sol.confinement(i) for i in range(len(n_eff))], 6))
    # beta convention: sqrt(Lambda) vs discrete propagation constant
    lam_um = float(opt["wavelength_nm"]) * 1e-3
    k0 = 2 * math.pi / lam_um
    for h in (0.2, 0.15, 0.1):
        Lam = float(sol.beta[0] ** 2)
        arg = 1.0 - Lam * h * h / 2.0
        beta_disc = math.acos(arg) / h if -1 < arg < 1 else float("nan")
        print(f"  h={h:.2f}: beta(physical sqrt Lam)={sol.beta[0]:.6f}/um  "
              f"beta_disc(acos)={beta_disc:.6f}/um  "
              f"inflation={(beta_disc/sol.beta[0]-1)*100:+.3f}%  "
              f"n_eff_disc={beta_disc/k0:.6f}")
        res[f"beta_convention_h{h}"] = {"beta_plain": float(sol.beta[0]),
                                        "beta_disc_acos": float(beta_disc),
                                        "inflation_pct": float((beta_disc / sol.beta[0] - 1) * 100)}
    print("\n== 2. EIM vs full 2-D scalar consistency ==")
    eim = effective_index_model(opt)
    rel = abs(eim.n_eff - sol.n_eff[0]) / sol.n_eff[0]
    print(f"  EIM n_slab={eim.n_slab:.9f}  n_eff(2D-EIM)={eim.n_eff:.9f}  "
          f"full-2D={sol.n_eff[0]:.9f}  rel diff={rel:.3e}")
    res["eim"] = {"n_slab": eim.n_slab, "n_eff_eim": eim.n_eff,
                  "n_eff_full2d": float(sol.n_eff[0]), "rel_diff": float(rel)}

    print("\n== 3. crossing_cmt: how much of -30 dB @5deg is the d_lo clamp? ==")
    cc = pd.read_csv(Path(AL.LEGACY) / "outputs" / "optical"
                     / "coupling_coefficients.csv")
    comp = cc[cc["method"] == "supermode"].sort_values("separation_um")
    d = comp["separation_um"].to_numpy()
    k = comp["kappa_supermode_mm_inv"].to_numpy()
    gamma = 0.5974196830329641
    model = CouplingModel(optics=opt, label="REF", d_um=d, kappa_mm_inv=k,
                          gamma_per_um=gamma, d_lo=float(d[0]), d_hi=float(d[-1]),
                          kappa_floor=1e-14, kappa_ceiling=100.0, overlap_rows=[])
    res["cmt_reproduction"] = {}
    for a in (5.0, 10.0, 15.0):
        c = crossing_cmt(opt, a, model, eim.beta2d)
        # variant: replace the d_lo plateau by a physical log-linear extrapolation
        th = math.radians(a)
        s = np.arange(-model.d_hi / math.sin(th), model.d_hi / math.sin(th) + 1e-9, 0.02)
        dsep = np.abs(s) * math.sin(th)
        kk = np.asarray(model.kappa(dsep))
        # no-clamp: for d<d_lo extrapolate kappa(d_lo)*exp(-gamma*(d_lo-d))
        low = dsep < model.d_lo
        kk_nc = kk.copy()
        kk_nc[low] = model.kappa(model.d_lo) * np.exp(-gamma * (model.d_lo - dsep[low]))
        dbeta = eim.beta2d * (1 - math.cos(th))
        amp = np.trapezoid(kk * np.exp(-1j * dbeta * s), s) * 1e-3
        amp_nc = np.trapezoid(kk_nc * np.exp(-1j * dbeta * s), s) * 1e-3
        frac_low = float(np.trapz(np.abs(kk[low]), s[low]) / np.trapz(np.abs(kk), s))
        res["cmt_reproduction"][a] = {
            "legacy_T_cross": c["T_cross_cmt"], "legacy_amp": c["amplitude_cmt"],
            "no_clamp_T_cross": float(abs(amp_nc) ** 2),
            "no_clamp_amp": float(abs(amp_nc)),
            "fraction_of_integral_in_clamped_region": frac_low,
            "s_max_um": float(model.d_hi / math.sin(th)),
            "clamp_region_half_width_um": float(model.d_lo / math.sin(th))}
        print(f"  theta={a:4.1f}: legacy CMT T={c['T_cross_cmt']:.4e} "
              f"(amp {c['amplitude_cmt']:.5f}) | no-clamp T={abs(amp_nc)**2:.4e} "
              f"(amp {abs(amp_nc):.5f}) | clamped-region weight={frac_low*100:.1f}%")
    print("  physical kappa CMT (independent 1-D EIM):")
    kap1d = PK.load_or_build_kappa(opt)
    for a in (5.0, 10.0, 15.0, 20.0):
        cp = PK.cmt_crossing(kap1d, kap1d["beta"], a, optics=opt)
        print(f"    theta={a:4.1f}: |A|={cp['amplitude']:.4f} T={cp['T_cross']:.4e} "
              f"({cp['T_cross_db']:.2f} dB) weak={cp['valid_weak_coupling']}")
        res.setdefault("cmt_physical", {})[a] = cp

    print("\n== 4. crossing_born sanity ==")
    res["born"] = {}
    for a in (5.0, 10.0, 15.0, 90.0):
        b = crossing_born(eim, a)
        res["born"][a] = b
        print(f"  theta={a:4.1f}: q={b['q_per_um']:.4f}/um |Phi|={b['fourier_phi']:.4e} "
              f"amp={b['amplitude']:.4e} T={b['T_cross']:.4e} regime={b['regime']}")
    # Fourier transform of the mode profile at q = beta (90 deg case)
    q = eim.beta2d
    s = eim.s
    Phi = np.trapezoid(eim.phi * np.exp(1j * q * s), s)
    print(f"  Phi(q=beta={q:.3f}) = {abs(Phi):.3e} -> |A_90|~"
          f"{eim.k0**2/(2*eim.beta2d)*abs(Phi)**2:.3e}")
    res["phi_q_beta"] = float(abs(Phi))

    print("\n== 5. board: fixed-p scaling and column-sum structure ==")
    ds = load_dataset(CONFIG["inputs"]["best_valid_dir"],
                      verify_hash=CONFIG["inputs"]["verify_sha256"])
    bad = {k: v for k, v in ds.sha_check.items() if not v["ok"]}
    print(f"  sha256: {len(ds.sha_check)} files checked, {len(bad)} mismatches: "
          f"{[(k, v['critical']) for k, v in bad.items()]}")
    res["sha_check"] = {k: {"ok": v["ok"], "critical": v["critical"],
                            "size_ok": v["size_ok"]} for k, v in ds.sha_check.items()}
    events = pd.read_csv(Path(AL.LEGACY) / "outputs" / "geometry"
                         / "crossing_events_detected.csv").to_dict("records")
    b1 = build_board(ds.routes, events, 1e-7)
    b2 = build_board(ds.routes, events, 1e-5)
    b3 = build_board(ds.routes, events, 1e-3)
    off = lambda b: b.T_upper.copy() - np.diag(np.diag(b.T_upper))
    for bb, p in ((b1, 1e-7), (b2, 1e-5), (b3, 1e-3)):
        o = off(bb)
        print(f"  p={p:.0e}: max offdiag={db(o.max()):.3f} dB, "
              f"worst leakage={db(o.sum(axis=0).max()):.3f} dB")
        res[f"board_p{p:g}"] = {"max_offdiag_db": float(db(o.max())),
                                "worst_leakage_db": float(db(o.sum(axis=0).max())),
                                "max_col_sum": float(bb.T_upper.sum(axis=0).max())}
    print(f"  T_upper == T_nominal: {bool(np.array_equal(b1.T_upper, b1.T_nominal))}")
    res["T_upper_equals_nominal"] = bool(np.array_equal(b1.T_upper, b1.T_nominal))
    # energy: column sum with propagation loss artificially set to 0
    alpha_save = CONFIG["optics"]["propagation_loss_db_per_cm"]
    CONFIG["optics"]["propagation_loss_db_per_cm"] = 0.0
    bn = build_board(ds.routes, events, 1e-3)
    bn2 = build_board(ds.routes, events, 1e-2)
    CONFIG["optics"]["propagation_loss_db_per_cm"] = alpha_save
    print(f"  with alpha=0: p=1e-3 max col sum={bn.T_upper.sum(axis=0).max():.8f}; "
          f"p=1e-2 max col sum={bn2.T_upper.sum(axis=0).max():.8f} "
          f"(>1 breaks the 'no gain by construction' claim)")
    res["alpha0_colsum"] = {"p1e-3": float(bn.T_upper.sum(axis=0).max()),
                            "p1e-2": float(bn2.T_upper.sum(axis=0).max())}
    print(f"  second order max T: p=1e-7 -> {b1.second_order[0]['T']:.3e}, "
          f"p=1e-3 -> {b3.second_order[0]['T']:.3e} (ratio {b3.second_order[0]['T']/b1.second_order[0]['T']:.3e}, "
          f"p^2 ratio {(1e-3/1e-7)**2:.3e})")

    print("\n== 6. dataio / units ==")
    print(f"  total length measured={sum(r.total_length for r in ds.routes):.6f} mm")
    print(f"  routes={len(ds.routes)} events={len(events)} "
          f"(expected {CONFIG['inputs']['crossing_events_expected']})")
    print(f"  assignment rows={len(ds.assignment)}")
    res["dataset"] = {"n_routes": len(ds.routes),
                      "total_length_mm": float(sum(r.total_length for r in ds.routes)),
                      "n_events": len(events)}
    AL.jdump(OUT / "checks_summary.json", res)


if __name__ == "__main__":
    main()
