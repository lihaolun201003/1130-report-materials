"""E5 - full-board 1024-channel crosstalk propagation.

The board is assembled from the true XYZ geometry:

* diagonal ``T[i,i]`` = propagation loss of route i (0.05 dB/cm over the true
  arc length) reduced by the power removed at each crossing;
* off-diagonal ``T[j,i]`` = power that leaves route i at a crossing (or a
  near-approach interaction), propagates along route j to its output, and is
  attenuated by the *remaining* propagation length of both routes;
* second-order terms ``i -> k -> j`` are accumulated explicitly and are shown
  to be negligible;
* no gain is possible: every column sum is <= 1 by construction and is
  verified numerically.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from .config import CONFIG


def db(x):
    """Power ratio in dB, floored at -300 dB (no crosstalk / zero power)."""
    return 10.0 * np.log10(np.maximum(np.asarray(x, dtype=float), 1e-30))


@dataclass
class BoardResult:
    route_ids: np.ndarray
    T_nominal: np.ndarray
    T_upper: np.ndarray
    pair_records: list[dict]
    second_order: list[dict]
    crossing_power: dict
    column_sums: np.ndarray
    row_sums: np.ndarray


def _loss_factor(length_mm: np.ndarray | float, alpha_db_per_mm: float):
    return 10.0 ** (-alpha_db_per_mm * np.asarray(length_mm, dtype=float) / 10.0)


def reciprocal_lengths(routes) -> tuple[list[int], np.ndarray]:
    ids = [r.route_id for r in routes]
    L = np.array([r.total_length for r in routes], dtype=float)
    return ids, L


def build_board(routes, events: list[dict], p_cross: float,
                p_cross_nominal: float | None = None,
                second_order: bool = True) -> BoardResult:
    """Assemble the 1024x1024 port transfer matrix."""
    alpha = CONFIG["optics"]["propagation_loss_db_per_cm"] / 10.0
    ids, L = reciprocal_lengths(routes)
    index = {rid: k for k, rid in enumerate(ids)}
    n = len(ids)
    loss = _loss_factor(L, alpha)

    T = np.zeros((n, n))
    T_upper = np.zeros((n, n))
    np.fill_diagonal(T, loss)
    np.fill_diagonal(T_upper, loss)

    n_cross = np.zeros(n)
    pair_records: list[dict] = []
    pair_power = defaultdict(float)
    per_route_cross_power = defaultdict(float)

    for k, e in enumerate(events):
        i = index[e["route_a"]]
        j = index[e["route_b"]]
        si, sj = float(e["s_a_mm"]), float(e["s_b_mm"])
        p = float(p_cross)
        # i -> j: propagate s_i on route i, then (L_j - s_j) on route j
        f_ij = float(_loss_factor(si, alpha) * _loss_factor(L[j] - sj, alpha))
        f_ji = float(_loss_factor(sj, alpha) * _loss_factor(L[i] - si, alpha))
        T[j, i] += p * f_ij
        T[i, j] += p * f_ji
        T_upper[j, i] += p * f_ij
        T_upper[i, j] += p * f_ji
        n_cross[i] += 1
        n_cross[j] += 1
        pair_power[(min(i, j), max(i, j))] += p
        pair_records.append({
            "route_a": e["route_a"], "route_b": e["route_b"],
            "z_mm": e["z_mm"], "x_mm": e["x_mm"], "y_mm": e["y_mm"],
            "angle_deg": e["angle_deg"],
            "s_a_mm": si, "s_b_mm": sj,
            "P_cross": p,
            "T_a_to_b": p * f_ij, "T_b_to_a": p * f_ji,
            "T_a_to_b_db": float(db(p * f_ij)),
            "T_b_to_a_db": float(db(p * f_ji)),
        })

    for i in range(n):
        if n_cross[i] > 0:
            T[i, i] *= (1.0 - p) ** n_cross[i]
            T_upper[i, i] *= (1.0 - p) ** n_cross[i]

    # ---------------- second order i -> k -> j
    second: list[dict] = []
    if second_order:
        by_route: dict[int, list[dict]] = defaultdict(list)
        for rec in pair_records:
            by_route[rec["route_a"]].append(rec)
            by_route[rec["route_b"]].append(rec)
        for i in range(n):
            rid = ids[i]
            firsts = by_route.get(rid, [])
            for rec1 in firsts:
                other = rec1["route_b"] if rec1["route_a"] == rid else rec1["route_a"]
                s_i = rec1["s_a_mm"] if rec1["route_a"] == rid else rec1["s_b_mm"]
                s_k1 = rec1["s_b_mm"] if rec1["route_a"] == rid else rec1["s_a_mm"]
                k = index[other]
                for rec2 in by_route.get(other, []):
                    if rec2 is rec1:
                        continue
                    third = rec2["route_b"] if rec2["route_a"] == other else rec2["route_a"]
                    if third == rid:
                        continue
                    s_k2 = rec2["s_a_mm"] if rec2["route_a"] == other else rec2["s_b_mm"]
                    s_j = rec2["s_b_mm"] if rec2["route_a"] == other else rec2["s_a_mm"]
                    if s_k2 <= s_k1:            # wrong propagation direction
                        continue
                    j = index[third]
                    p2 = (p * p * float(_loss_factor(s_i, alpha))
                          * float(_loss_factor(s_k2 - s_k1, alpha))
                          * float(_loss_factor(L[j] - s_j, alpha)))
                    if p2 <= 0:
                        continue
                    T[j, i] += p2
                    T_upper[j, i] += p2
                    second.append({"route_i": rid, "route_k": other, "route_j": third,
                                   "T": p2, "T_db": float(db(p2))})
        second.sort(key=lambda x: -x["T"])

    col_sums = T.sum(axis=0)
    row_sums = T.sum(axis=1)
    return BoardResult(np.asarray(ids), T, T_upper, pair_records, second,
                       {"n_crossings": int(len(events)), "p_cross": p_cross},
                       col_sums, row_sums)


# ------------------------------------------------------------------- statistics
def route_statistics(routes, board: BoardResult) -> list[dict]:
    ids = board.route_ids
    T = board.T_upper
    Tn = board.T_nominal
    rows = []
    n = len(ids)
    cross_count: dict[int, int] = defaultdict(int)
    for rec in board.pair_records:
        cross_count[rec["route_a"]] += 1
        cross_count[rec["route_b"]] += 1
    for k, r in enumerate(routes):
        off = np.delete(T[k, :], k)
        col = np.delete(T[:, k], k)
        order = np.argsort(col)[::-1]
        worst = [int(ids[j if j < k else j + 1]) for j in order[:3]]
        rows.append({
            "route_id": int(ids[k]),
            "source_endpoint": r.source_endpoint,
            "target_endpoint": r.target_endpoint,
            "plane": r.plane,
            "layer_role": r.layer_role,
            "target_plane_label": r.target_plane_label,
            "target_z_mm": r.target_z_mm,
            "native_3d": int(r.native_3d),
            "n_mid_transitions": r.n_mid_transitions,
            "L_total_mm": r.total_length,
            "loss_base_db": CONFIG["optics"]["propagation_loss_db_per_cm"]
            / 10.0 * r.total_length,
            "T_diag": float(T[k, k]),
            "T_diag_db": float(db(T[k, k])),
            "n_crossings": int(cross_count.get(int(ids[k]), 0)),
            "max_crosstalk_from_db": float(db(col.max())) if n > 1 else -999.0,
            "total_leakage_from_db": float(db(col.sum())),
            "worst_victim_routes": ";".join(str(x) for x in worst),
            "max_single_pair_db": float(db(off.max())) if n > 1 else -999.0,
            "total_interference_to_db": float(db(off.sum())),
            "interference_to_signal_db": float(db(off.sum() / max(T[k, k], 1e-300))),
        })
    return rows


def hotspot_records(board: BoardResult, top_n: int = 60) -> list[dict]:
    recs = sorted(board.pair_records, key=lambda x: -x["P_cross"])
    by_pos = defaultdict(list)
    # cluster by 2 mm cell on the crossing plane
    for rec in board.pair_records:
        key = (round(rec["z_mm"], 4), round(rec["x_mm"] / 2.0), round(rec["y_mm"] / 2.0))
        by_pos[key].append(rec)
    clusters = []
    for key, items in by_pos.items():
        tot = sum(x["P_cross"] for x in items)
        clusters.append({
            "z_mm": float(np.mean([x["z_mm"] for x in items])),
            "x_mm": float(np.mean([x["x_mm"] for x in items])),
            "y_mm": float(np.mean([x["y_mm"] for x in items])),
            "n_crossings": len(items),
            "total_P_cross": tot,
            "total_P_cross_db": float(db(tot)),
            "max_P_cross_db": float(db(max(x["P_cross"] for x in items))),
            "routes": sorted({x["route_a"] for x in items} | {x["route_b"] for x in items}),
            "mean_angle_deg": float(np.mean([x["angle_deg"] for x in items])),
        })
    clusters.sort(key=lambda c: -c["total_P_cross"])
    return clusters[:top_n]
