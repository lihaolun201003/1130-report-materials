"""E1: parse the 1024 authoritative XYZ routes and compute true lengths + loss."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import BEST_VALID, CONFIG, EXPERIMENT_ROOT
from src.dataio import load_dataset, runtime_info, write_csv, write_json, write_yaml
from src.lengths import length_table, summary


def main() -> int:
    t0 = time.time()
    ds = load_dataset(BEST_VALID, verify_hash=CONFIG["inputs"]["verify_sha256"])
    print(f"[E1] loaded {len(ds.routes)} routes; sha256 index verified")
    for name, rec in ds.sha_check.items():
        print(f"      {name:40s} {rec['actual'][:16]}... ok={rec['ok']}")

    rows = length_table(ds)
    summ = summary(rows)
    out = EXPERIMENT_ROOT / "outputs" / "geometry"
    write_csv(out / "route_lengths.csv", rows)
    write_csv(out / "propagation_loss.csv", rows)
    write_json(EXPERIMENT_ROOT / "outputs" / "geometry" / "e1_summary.json", summ)
    write_json(EXPERIMENT_ROOT / "outputs" / "geometry" / "input_sha256_check.json",
               {"checked": ds.sha_check,
                "routes_sha256_expected": CONFIG["inputs"]["routes_sha256_expected"],
                "runtime": runtime_info()})
    write_yaml(EXPERIMENT_ROOT / "config" / "simulation_config.yaml", CONFIG)

    print("\n[E1] summary")
    for k, v in summ.items():
        print(f"      {k:44s} {v}")
    print(f"\n[E1] done in {time.time() - t0:.2f}s")
    assert summ["length_check_passed"], "total length does not match the authoritative value"
    assert summ["all_decompositions_exact"], "per-route decomposition mismatch"
    assert summ["route_count"] == 1024 and summ["unique_route_ids"] == 1024
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
