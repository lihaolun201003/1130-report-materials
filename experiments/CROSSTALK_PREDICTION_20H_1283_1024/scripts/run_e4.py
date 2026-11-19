"""E4: full 1024-route 3-D interaction analysis (crossings + near approaches)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from src.config import BEST_VALID, CONFIG, EXPERIMENT_ROOT
from src.dataio import load_dataset, write_csv, write_json
from src.interactions import detect_crossings, near_approaches


def main() -> int:
    t0 = time.time()
    ds = load_dataset(BEST_VALID,
                      verify_hash=CONFIG["inputs"]["verify_sha256"])
    out = EXPERIMENT_ROOT / "outputs" / "geometry"

    # ---- same-plane crossings (independent analytic re-derivation)
    events, cstats = detect_crossings(ds.routes)
    official = ds.crossing_events
    off_keys = {(min(e["route_a"], e["route_b"]), max(e["route_a"], e["route_b"]),
                 round(e["z_mm"], 6)) for e in official}
    my_keys = {(e["route_a"], e["route_b"], round(e["z_mm"], 6)) for e in events}
    pos_off = {(min(e["route_a"], e["route_b"]), max(e["route_a"], e["route_b"]),
                round(e["z_mm"], 6), round(e["x_mm"], 2), round(e["y_mm"], 2))
               for e in official}
    pos_my = {(e["route_a"], e["route_b"], round(e["z_mm"], 6),
               round(e["x_mm"], 2), round(e["y_mm"], 2)) for e in events}
    cstats.update({
        "official_events": len(official),
        "official_pairs": ds.crossing_stats["totals"]["crossing_pairs"],
        "official_routes_with_crossings":
            ds.crossing_stats["totals"]["routes_with_crossings"],
        "pair_plane_matches_official": len(off_keys & my_keys),
        "pair_plane_official_only": len(off_keys - my_keys),
        "pair_plane_detected_only": len(my_keys - off_keys),
        "position_matches_official": len(pos_off & pos_my),
        "count_matches_official": int(len(events) == len(official)),
        "pairs_match_official": int(cstats["pairs"]
                                    == ds.crossing_stats["totals"]["crossing_pairs"]),
        "crossing_detection_reproduces_official": bool(
            len(events) == len(official)
            and cstats["pairs"] == ds.crossing_stats["totals"]["crossing_pairs"]),
    })
    write_csv(out / "crossing_events_detected.csv", events)
    print(f"[E4] crossings: {cstats}")

    # ---- non-crossing near approaches
    t1 = time.time()
    near, nstats = near_approaches(ds.routes)
    print(f"[E4] near approaches: {nstats} in {time.time() - t1:.1f}s")
    if near:
        near.sort(key=lambda x: x["d_min_mm"])
        write_csv(out / "interaction_regions.csv", near)
        d = np.array([r["d_min_mm"] for r in near])
        cross_pairs = {(min(e["route_a"], e["route_b"]),
                        max(e["route_a"], e["route_b"])) for e in events}
        clean = [r for r in near
                 if (min(r["route_a"], r["route_b"]),
                     max(r["route_a"], r["route_b"])) not in cross_pairs]
        dc = np.array([r["d_min_mm"] for r in clean]) if clean else np.array([np.nan])
        nstats.update({
            "min_distance_mm": float(np.nanmin(d)),
            "min_distance_um": float(np.nanmin(d) * 1000.0),
            "min_distance_noncrossing_mm": float(np.nanmin(dc)),
            "min_distance_noncrossing_um": float(np.nanmin(dc) * 1000.0),
            "records_involving_crossing_pairs": int(len(near) - len(clean)),
            "pairs_within_50um": int((d < 0.05).sum()),
            "pairs_within_62um": int((d < 0.062).sum()),
            "same_plane_approaches": int(sum(r["same_plane"] for r in near)),
            "cross_layer_approaches": int(sum(1 - r["same_plane"] for r in near)),
            "transition_involved": int(sum(r["involves_transition"] for r in near)),
            "exact_intersections_found": int(sum(r["crossing"] for r in near)),
            "median_distance_um": float(np.median(d) * 1000.0),
        })
    else:
        nstats["min_distance_um"] = float("nan")

    write_json(EXPERIMENT_ROOT / "outputs" / "geometry" / "e4_summary.json",
               {"crossings": cstats, "near_approaches": nstats,
                "runtime_seconds": time.time() - t0})
    print(f"[E4] done in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
