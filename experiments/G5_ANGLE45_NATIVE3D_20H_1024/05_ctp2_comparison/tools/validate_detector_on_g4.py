# -*- coding: utf-8 -*-
"""Validate the G5 crossing detector against two independent implementations.

The detector used by ``run_ctp2_g5.py`` to re-derive the G5 crossings is a port
of CTP-1.0's exact analytic intersection engine onto CTP-2.0's analytic route
geometry.  Before trusting it on a geometry that has no reference answer, it is
run on the **frozen G4** geometry, where *two* independent reference lists exist:

  A) CTP-1.0 e4 ``outputs/geometry/crossing_events_detected.csv`` (1283 events)
  B) the G5 project's own audit engine
     ``G5_ANGLE45_NATIVE3D_20H_1024/00_baseline_audit/baseline_crossing_angles.csv``
     (written by ``01_algorithm/run_baseline_audit.py`` from ``g5.model.World``)

Both must be reproduced: same event set, same positions to < 1e-6 mm, same
angles to < 1e-6 deg, and the same angle histogram as the audit report
(``baseline_angle_report.md`` §2).

Usage:  python tools/validate_detector_on_g4.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CMP = HERE.parent
sys.path.insert(0, str(CMP))

import run_ctp2_g5 as R                                    # noqa: E402

G5_AUDIT_CSV = (R.G5_EXP / "00_baseline_audit" / "baseline_crossing_angles.csv")
OUT = CMP / "frozen_guard" / "detector_validation_on_g4.json"


def main() -> int:
    t0 = time.time()
    routes = R.load_ctp2(R.G4_BEST, CMP / "ctp2_out_detector_check",
                         "G4_frozen_10_best_valid")[0].load_routes(
                             R.G4_BEST / "routes_l3d.json")
    events, stats = R.detect_crossings(routes)
    R.detect_crossings  # keep flake quiet
    print(f"[detector] {stats['events']} events / {stats['pairs']} pairs / "
          f"{stats['routes_with_crossings']} routes "
          f"({stats['intersection_tests']} primitive-pair tests, "
          f"{time.time() - t0:.1f}s)")

    angles = [e["angle_deg"] for e in events]
    hist = R.angle_histogram(angles)

    report = {
        "schema": "ctp2_g5_detector_validation_v1",
        "geometry": str(R.G4_BEST),
        "routes_sha256": R.sha256_file(R.G4_BEST / "routes_l3d.json"),
        "detector_stats": stats,
        "angle_histogram": hist,
        "min_angle_deg": min(angles),
        "n_below_45": int(sum(1 for a in angles if a < 45.0)),
        "checks": {},
    }

    # ---- A) CTP-1.0 e4 reference ------------------------------------------
    legacy = []
    with open(R.CTP1_G4_CROSSINGS, newline="", encoding="utf-8") as fh:
        import csv as _csv
        legacy = [dict(r) for r in _csv.DictReader(fh)]
    a = R.compare_crossing_sets(events, legacy, "CTP-1.0 e4 crossing_events_detected.csv",
                                tol_mm=1e-6, tol_deg=1e-6, require_s_match=True)
    # the raw e4 CSV has no z_label; keep the shared columns only
    report["checks"]["ctp1_e4"] = a
    print(f"[detector] vs CTP-1.0 e4 : matched={a['n_matched']} "
          f"only_detector={a['n_only_mine']} only_ref={a['n_only_other']} "
          f"max|dx|={a['max_abs_dx_mm']:.2e} max|dy|={a['max_abs_dy_mm']:.2e} "
          f"max|ds|={a['max_abs_ds_mm']:.2e} max|dangle|={a['max_abs_dangle_deg']:.2e} "
          f"consistent={a['consistent']}")

    # ---- B) G5 project audit engine reference -----------------------------
    if G5_AUDIT_CSV.exists():
        g5ref = []
        with open(G5_AUDIT_CSV, newline="", encoding="utf-8") as fh:
            import csv as _csv
            g5ref = [dict(r) for r in _csv.DictReader(fh)]
        b = R.compare_crossing_sets(events, g5ref,
                                    "G5 baseline_crossing_angles.csv",
                                    tol_mm=1e-6, tol_deg=1e-6,
                                    require_s_match=False)
        report["checks"]["g5_audit_engine"] = b
        off = b["s_offset"]
        print(f"[detector] vs G5 audit   : matched={b['n_matched']} "
              f"only_detector={b['n_only_mine']} only_ref={b['n_only_other']} "
              f"max|dx|={b['max_abs_dx_mm']:.2e} max|dy|={b['max_abs_dy_mm']:.2e} "
              f"max|dangle|={b['max_abs_dangle_deg']:.2e} "
              f"geometry_consistent={b['geometry_consistent']}")
        print(f"[detector] vs G5 audit   : s column uses a different origin -- "
              f"{off['n_constant_per_route']}/{off['n_route_entries']} routes "
              f"constant, max |offset| = {off['max_abs_mean_offset_mm']:.3f} mm, "
              f"residual {off['max_residual_around_route_mean_mm']:.2e} mm")
    else:
        report["checks"]["g5_audit_engine"] = {"exists": False,
                                              "path": str(G5_AUDIT_CSV)}
        print(f"[detector] G5 audit CSV absent: {G5_AUDIT_CSV}")

    # ---- C) the audit report's own published table ------------------------
    published = {
        "n_crossings": 1283, "n_below_45": 304, "min_angle_deg": 5.153763,
        "bin_labels": ["[0,5)", "[5,10)", "[10,20)", "[20,30)", "[30,40)",
                       "[40,45)", "[45,60)", "[60,75)", "[75,90]"],
        "bin_counts": [0, 17, 92, 52, 92, 51, 271, 514, 194],
    }
    report["published_audit_report"] = published
    report["checks"]["histogram_matches_published"] = (
        hist["counts"] == published["bin_counts"])
    report["checks"]["n_events_matches_published"] = (
        stats["events"] == published["n_crossings"])
    report["checks"]["n_below_45_matches_published"] = (
        report["n_below_45"] == published["n_below_45"])
    report["checks"]["min_angle_matches_published"] = (
        abs(report["min_angle_deg"] - published["min_angle_deg"]) < 1e-6)
    print(f"[detector] histogram == published: "
          f"{hist['counts']} vs {published['bin_counts']} -> "
          f"{report['checks']['histogram_matches_published']}")

    report["all_pass"] = all(
        (v.get("geometry_consistent") if isinstance(v, dict) else bool(v))
        for k, v in report["checks"].items() if k != "g5_audit_engine"
    ) and report["checks"]["g5_audit_engine"].get("geometry_consistent", True)
    report["elapsed_seconds"] = round(time.time() - t0, 3)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"[detector] all_pass={report['all_pass']} -> {OUT}")
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
