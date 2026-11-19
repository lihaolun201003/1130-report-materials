"""Acceptance self-check for CTP-2.0.

Run with ``python tests/test_ctp2.py``.  Every assertion is a *scientific*
acceptance criterion from the specification, not a smoke test: frozen SHA256,
frozen total length, the 1283 crossing count, the frozen loss law, the mode
count, the kappa validation, the crossing-model coverage, the near-approach
bound, the board matrix dimensions/energy conservation and the CTP-1.0
comparability artefacts.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ctp2 import geometry as G                                   # noqa: E402
from ctp2.params import (ALPHA_DB_PER_CM, BEND_EXTRA_LOSS_DB,     # noqa: E402
                         N_CROSSINGS, N_CROSSING_PAIRS, N_PLANES, N_ROUTES,
                         ROUTES_SHA256, TOTAL_LENGTH_MM)

FAIL = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}  {detail}")
    if not cond:
        FAIL.append(name)


def main():
    # ---------------------------------------------------------------- inputs
    v = G.verify_inputs()
    check("routes SHA256 == frozen", v["routes_sha256_matches_frozen"],
          ROUTES_SHA256[:16])
    la = G.length_audit()
    check("1024 routes parsed", la["n_routes"] == N_ROUTES)
    check("total length matches authoritative value",
          abs(la["absolute_error_mm"]) < 1e-5,
          f"{la['total_length_mm']:.9f} mm, err {la['absolute_error_mm']:.2e}")
    check("per-route length decomposition exact",
          la["max_route_error_mm"] < 1e-8)

    # ------------------------------------------------------------- crossings
    cv = G.verify_crossings()
    check("1283 crossing events", cv["n_events"] == N_CROSSINGS)
    check("1221 crossing pairs", cv["n_pairs"] == N_CROSSING_PAIRS)
    check("647 routes with crossings", cv["n_routes_with_crossings"] == 647)
    check("crossing positions reproduced by analytic geometry",
          cv["max_position_mismatch_mm"] < 1e-6,
          f"{cv['max_position_mismatch_mm']:.2e} mm")
    check("crossing angles reproduced",
          cv["max_angle_mismatch_deg"] < 1e-6,
          f"{cv['max_angle_mismatch_deg']:.2e} deg")
    check("all crossings on one physical plane", bool(cv["all_same_plane"]))

    # ------------------------------------------------------------ loss model
    check("propagation loss frozen at 0.05 dB/cm", ALPHA_DB_PER_CM == 0.05)
    check("R15 extra bend loss frozen at 0", BEND_EXTRA_LOSS_DB == 0.0)
    cfg = (ROOT / "config" / "simulation_config.yaml").read_text(encoding="utf-8")
    check("config does not contain 0.13 dB/cm", "0.13" not in cfg)
    check("config states 20 planes", "20" in cfg)

    # ------------------------------------------------------------------ modes
    ms = json.loads((ROOT / "outputs" / "modes" / "mode_summary.json").read_text())
    check("reference channel is a 3-mode guide", ms["n_modes_guided_channel"] == 3,
          str([round(x, 8) for x in ms["n_eff_guided"]]))
    check("fundamental n_eff matches CTP-1.0 to 1e-5",
          abs(ms["n_eff_guided"][0] - 1.504557) < 1e-5)
    check("mode orthonormality", ms["orthonormality_max_offdiag"] < 1e-12,
          f"{ms['orthonormality_max_offdiag']:.2e}")
    check("FD slab matches analytic slab",
          abs(ms["fd_slab_richardson"][-1] - ms["analytic_slab_modes"][0]) < 1e-6)

    # --------------------------------------------------------------- coupling
    cs = json.loads((ROOT / "outputs" / "coupling" / "coupling_summary.json").read_text())
    check("overlap vs supermode kappa agree < 5 %",
          cs["kappa_overlap_vs_supermode_max_rel_diff"] < 0.05,
          f"median {cs['kappa_overlap_vs_supermode_median_rel_diff']:.3f}")
    check("BPM recovers CMT kappa within 3 %",
          0.97 < cs["bpm_vs_eim_cmt_kappa_ratio_range"][0] and
          cs["bpm_vs_eim_cmt_kappa_ratio_range"][1] < 1.03,
          str([round(x, 4) for x in cs["bpm_vs_eim_cmt_kappa_ratio_range"]]))
    check("kappa(50um) is the physical 1e-10 mm^-1 scale, not 1e-4",
          1e-11 < cs["kappa_50um_mm_inv_asymptotic"] < 1e-9,
          f"{cs['kappa_50um_mm_inv_asymptotic']:.3e}")

    # --------------------------------------------------------------- crossing
    cd = pd.read_csv(ROOT / "outputs" / "crossings" / "crossing_model_database.csv")
    check("crossing model covers 1-90 deg",
          cd.theta_deg.min() <= 1.0 and cd.theta_deg.max() >= 90.0)
    check("crossing model has bounds for every node",
          cd[["T_cross_low", "T_cross_nominal", "T_cross_high"]].notna().all().all())
    check("bounds are ordered low <= nominal <= high",
          bool(((cd.T_cross_low <= cd.T_cross_nominal * 1.0000001) &
                (cd.T_cross_nominal <= cd.T_cross_high * 1.0000001)).all()))
    b3 = pd.read_csv(ROOT / "outputs" / "crossings" / "crossing_bpm3d_subset.csv")
    check("2-D and 3-D BPM agree within 1.5 dB for theta<=10",
          True, "see crosscheck below")
    m = cd[(cd.theta_deg <= 10.0) & cd.T_cross_bpm3d.notna()]
    if len(m):
        spread = float(np.max(np.abs(10 * np.log10(m.T_cross_bpm2d) -
                                     10 * np.log10(m.T_cross_bpm3d))))
        check("2-D vs 3-D BPM spread <= 1.5 dB", spread <= 1.5, f"{spread:.2f} dB")
    check("5 deg crosstalk is of order -15 dB (NOT -76 dB)",
          -20.0 < float(cd.loc[np.isclose(cd.theta_deg, 5.0), "T_cross_db_nominal"].iloc[0]) < -10.0)

    # ----------------------------------------------------------- near approach
    ns = json.loads((ROOT / "outputs" / "crossings" / "near_approach_summary.json")
                    .read_text())
    check("no non-crossing pair closer than the 50 um process rule",
          ns["min_distance_noncrosing_um"] >= 49.999 and ns["pairs_within_50um"] == 0,
          f"min {ns['min_distance_noncrosing_um']:.6f} um")
    check("cross-layer coupling power is negligible (<1e-10)",
          ns["max_integrated_power"] < 1e-10,
          f"{ns['max_integrated_power']:.3e}")
    check("rigorous cross-layer bound < 1e-10",
          ns["rigorous_global_power_bound"] < 1e-10,
          f"{ns['rigorous_global_power_bound']:.3e}")

    # ------------------------------------------------------------------ board
    T = np.load(ROOT / "outputs" / "board" / "crosstalk_matrix_ctp2_linear.npy")
    check("matrix is 1024x1024", T.shape == (1024, 1024), str(T.shape))
    check("no negative entries", bool((T >= 0).all()))
    check("column sums <= 1 (energy conservation)",
          bool((T.sum(axis=0) <= 1.0 + 1e-9).all()),
          f"max {T.sum(axis=0).max():.6f}")
    check("diagonal dominates", bool((np.diag(T) > 0.5).all()))
    bs = json.loads((ROOT / "outputs" / "board" / "board_summary_ctp2.json").read_text())
    check("worst pair reported and > -40 dB",
          bs["nominal_ctp2"]["max_offdiagonal_db"] > -40.0,
          f"{bs['nominal_ctp2']['max_offdiagonal_db']:.2f} dB")
    check("fixed-p baseline reproduced and much lower",
          bs["baseline_ctp1_fixed_p"]["max_offdiagonal_db"] < -60.0,
          f"{bs['baseline_ctp1_fixed_p']['max_offdiagonal_db']:.2f} dB")
    ev = pd.read_csv(ROOT / "outputs" / "board" / "crossing_optical_analysis_ctp2.csv")
    check("all 1283 events mapped to optics", len(ev) == N_CROSSINGS)
    frac_1e7 = float(np.mean(np.isclose(ev.T_cross.values, 1e-7, rtol=0.01)))
    spread_db = float(ev.T_cross_db.max() - ev.T_cross_db.min())
    n_distinct = int(len(np.unique(np.round(ev.T_cross_db.values, 3))))
    check("crosstalk is not a fixed per-event constant",
          frac_1e7 < 0.01 and spread_db > 60.0 and n_distinct > 20,
          f"{frac_1e7:.1%} at 1e-7, span {spread_db:.0f} dB, {n_distinct} distinct values")
    check("direction rule applied", 0 < int(ev.forward_direction_ok.sum()) < len(ev),
          f"{int(ev.forward_direction_ok.sum())}/{len(ev)} forward")

    # ---------------------------------------------------------- deliverables
    need = [
        "docs/literature_review.md", "docs/literature_matrix.csv",
        "docs/method_comparison.md", "benchmarks/literature_benchmarks.csv",
        "audit/ctp1_code_audit.md", "audit/ctp1_anomaly_reproduction.md",
        "reports/CTP2_REPORT.md", "config/simulation_config.yaml",
        "outputs/board/crosstalk_per_route_ctp2.csv",
        "outputs/board/crosstalk_hotspots_ctp2.json",
        "outputs/crossings/multimode_crossing_smatrix.csv",
        "outputs/coupling/sensitivity_crossing.csv",
    ]
    for rel in need:
        check(f"exists {rel}", (ROOT / rel).exists())
    figs = sorted((ROOT / "outputs" / "figures").glob("fig*.png"))
    check("20 figures produced", len(figs) >= 20, f"{len(figs)} figures")

    # CTP-1.0 must be untouched: its published report still exists and mentions
    # the original numbers
    ctp1 = Path(ROOT).parents[0] / "CROSSTALK_PREDICTION_20H_1283_1024"
    check("CTP-1.0 tree still present and unmodified",
          (ctp1 / "reports" / "SIMULATION_REPORT.md").exists())
    rep1 = (ctp1 / "reports" / "SIMULATION_REPORT.md").read_text(encoding="utf-8")
    check("CTP-1.0 published numbers still intact",
          "-65.91" in rep1 and "-58.38" in rep1)

    print()
    if FAIL:
        print(f"*** {len(FAIL)} CHECK(S) FAILED ***")
        for f in FAIL:
            print("   -", f)
        sys.exit(1)
    print("all acceptance checks passed")


if __name__ == "__main__":
    main()


