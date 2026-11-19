"""E5: full-board 1024-channel crosstalk prediction."""
from __future__ import annotations

import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from src.board import BoardResult, build_board, db, hotspot_records, route_statistics
from src.config import CONFIG, EXPERIMENT_ROOT
from src.coupling import build_coupling_model
from src.dataio import (load_dataset, runtime_info, write_csv, write_json,
                        write_yaml)
from src.config import BEST_VALID


def main() -> int:
    t0 = time.time()
    out = EXPERIMENT_ROOT / "outputs" / "optical"
    geo = EXPERIMENT_ROOT / "outputs" / "geometry"
    ds = load_dataset(BEST_VALID, verify_hash=CONFIG["inputs"]["verify_sha256"])

    events = pd.read_csv(geo / "crossing_events_detected.csv").to_dict("records")
    curve = pd.read_csv(out / "crossing_transfer_curve.csv")
    theta = curve["theta_deg"].to_numpy(float)
    tcross = curve["T_cross_fdfd"].to_numpy(float)
    order = np.argsort(theta)
    theta, tcross = theta[order], tcross[order]
    floor = float(CONFIG["crossing_model"]["resolution_floor"])
    p_cross_curve = np.maximum(tcross, floor)

    p_floor = floor
    print(f"[E5] crossing curve: {len(theta)} angles, "
          f"FDFD max={tcross.max():.3e}, floor={floor:.1e}")

    # per-event optical analysis
    cross_rows = []
    for e in events:
        a = float(e["angle_deg"])
        p_fdfd = float(np.interp(a, theta, tcross))
        p_used = float(np.interp(a, theta, p_cross_curve))
        cross_rows.append({
            "route_a": int(e["route_a"]), "route_b": int(e["route_b"]),
            "z_mm": float(e["z_mm"]), "x_mm": float(e["x_mm"]),
            "y_mm": float(e["y_mm"]), "angle_deg": a,
            "s_a_mm": float(e["s_a_mm"]), "s_b_mm": float(e["s_b_mm"]),
            "kind_a": e["kind_a"], "kind_b": e["kind_b"],
            "P_cross_fdfd": p_fdfd,
            "P_cross_fdfd_db": float(db(p_fdfd)),
            "P_cross_used": p_used,
            "P_cross_used_db": float(db(p_used)),
            "at_resolution_floor": int(p_fdfd < floor),
            "model": "local_fdfd_2d_eim",
            "model_status": ("below_resolution" if p_fdfd < floor
                             else "resolved"),
        })
    write_csv(out / "crossing_optical_analysis.csv", cross_rows)

    board = build_board(ds.routes, events, p_floor)
    T = board.T_upper
    np.save(out / "crosstalk_matrix_linear.npy", T.astype(np.float64))
    np.save(EXPERIMENT_ROOT / "cache" / "crosstalk_matrix_linear.npy",
            T.astype(np.float64))

    # dB matrix (with an explicit definition string in the manifest)
    T_db = np.where(T > 0, 10.0 * np.log10(np.maximum(T, 1e-300)), -300.0)
    np.fill_diagonal(T_db, 10.0 * np.log10(np.maximum(np.diag(T), 1e-300)))
    df = pd.DataFrame(T_db, index=board.route_ids, columns=board.route_ids)
    df.index.name = "out_route_id"
    df.to_csv(out / "crosstalk_matrix_db.csv", float_format="%.4f")

    stats = route_statistics(ds.routes, board)
    write_csv(out / "crosstalk_per_route.csv", stats)

    hotspots = hotspot_records(board, top_n=80)
    write_json(out / "crosstalk_hotspots.json", {
        "definition": "total coupled power per 2x2 mm cell on the crossing plane",
        "clusters": hotspots,
    })

    # ---------------- board-level statistics
    n = len(board.route_ids)
    off = T.copy()
    np.fill_diagonal(off, 0.0)
    diag = np.diag(T)
    col_sums = T.sum(axis=0)
    stats_out = {
        "matrix_shape": [int(n), int(n)],
        "route_ids_unique": int(len(set(board.route_ids.tolist()))),
        "definition": ("T[j,i] = P_out(target of j) / P_in(source of i); "
                       "row index = output route, column index = input route"),
        "p_cross_per_event_used": p_floor,
        "crossing_curve_max_fdfd": float(tcross.max()),
        "resolution_floor": p_floor,
        "diagonal_min_db": float(db(diag.min())),
        "diagonal_max_db": float(db(diag.max())),
        "diagonal_mean_db": float(db(diag.mean())),
        "max_offdiagonal_db": float(db(off.max())),
        "max_offdiagonal_pair": [
            int(board.route_ids[np.unravel_index(np.argmax(off), off.shape)[0]]),
            int(board.route_ids[np.unravel_index(np.argmax(off), off.shape)[1]]),
        ],
        "max_offdiagonal_value": float(off.max()),
        "median_offdiagonal_db": float(db(np.median(off[off > 0])))
        if np.any(off > 0) else -300.0,
        "n_nonzero_offdiagonal": int(np.count_nonzero(off)),
        "worst_total_leakage_db": float(db(off.sum(axis=0).max())),
        "mean_total_leakage_db": float(db(off.sum(axis=0).mean())),
        "median_total_leakage_db": float(db(np.median(off.sum(axis=0)))),
        "max_interference_to_signal_db": float(
            np.max(off.sum(axis=0) / np.maximum(diag, 1e-300))),
        "energy": {
            "max_column_sum": float(col_sums.max()),
            "min_column_sum": float(col_sums.min()),
            "max_row_sum": float(board.row_sums.max()),
            "all_columns_le_1": bool(col_sums.max() <= 1.0 + 1e-12),
            "total_output_over_total_input": float(col_sums.mean()),
        },
        "second_order": {
            "n_terms": len(board.second_order),
            "max_T": float(board.second_order[0]["T"]) if board.second_order else 0.0,
            "max_T_db": float(board.second_order[0]["T_db"]) if board.second_order else -300.0,
            "negligible_below_1e_9": bool(
                (not board.second_order) or board.second_order[0]["T"] < 1e-9),
        },
        "n_crossing_events": len(events),
        "n_route_pairs_with_crosstalk": int(
            len({(min(r["route_a"], r["route_b"]), max(r["route_a"], r["route_b"]))
                 for r in board.pair_records})),
        "runtime_seconds": time.time() - t0,
    }

    # ---------------- multi-channel (all 1024 on, incoherent)
    sig = diag
    interf = off.sum(axis=0)
    stats_out["multi_channel"] = {
        "assumption": "all 1024 sources on, independent (random) optical phases",
        "worst_interference_to_signal_db": float(db((interf / np.maximum(sig, 1e-300)).max())),
        "mean_interference_to_signal_db": float(db((interf / np.maximum(sig, 1e-300)).mean())),
        "worst_output_route": int(board.route_ids[np.argmax(interf / np.maximum(sig, 1e-300))]),
    }

    # ---------------- per-layer statistics
    planes = defaultdict(lambda: {"routes": 0, "crossings": 0, "length_mm": 0.0,
                                  "leakage_db_sum": 0.0})
    for r, st in zip(ds.routes, stats):
        key = round(r.target_z_mm, 6)
        planes[key]["routes"] += 1
        planes[key]["length_mm"] += r.total_length
    for e in events:
        planes[round(float(e["z_mm"]), 6)]["crossings"] += 1
    layer_rows = []
    for z in sorted(planes):
        d = planes[z]
        layer_rows.append({"z_mm": z, "n_routes": d["routes"],
                           "total_length_mm": d["length_mm"],
                           "n_crossings": d["crossings"]})
    write_csv(geo / "layer_statistics.csv", layer_rows)

    # ---------------- crossing-count vs crosstalk correlation
    ncross = np.array([s["n_crossings"] for s in stats], float)
    leak = np.array([s["total_leakage_from_db"] for s in stats], float)
    corr = float(np.corrcoef(ncross, leak)[0, 1]) if ncross.std() > 0 else float("nan")
    stats_out["geometry_vs_optics"] = {
        "pearson_r_crossings_vs_leakage_db": corr,
        "note": ("leakage is proportional to the crossing count when every "
                 "crossing contributes the same resolution-limited power"),
        "max_route_crossings": int(ncross.max()),
        "routes_with_zero_crossings": int((ncross == 0).sum()),
    }
    write_json(out / "e5_summary.json", stats_out)
    print(f"[E5] max off-diagonal {stats_out['max_offdiagonal_db']:.2f} dB, "
          f"worst leakage {stats_out['worst_total_leakage_db']:.2f} dB")
    print(f"[E5] energy: {stats_out['energy']}")
    print(f"[E5] done in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
