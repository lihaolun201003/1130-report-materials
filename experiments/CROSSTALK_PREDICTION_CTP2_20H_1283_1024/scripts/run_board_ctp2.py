"""Full-board 1024x1024 port transfer matrix, CTP-2.0.

Differences from CTP-1.0
------------------------
* every crossing uses its *own* locally validated optical model (angle, through
  loss, crosstalk, radiation) instead of one fixed ``p = 1e-7``;
* the propagation attenuation of the *actual remaining arc length* of both
  routes is applied in both directions (unchanged from CTP-1.0, verified);
* a crossing transfers power from a route's forward direction into the arm of
  the other route that makes the **acute angle** with it.  If the two routes'
  forward tangents have a negative dot product (obtuse angle between the
  propagation directions) that arm is the other route's *input* arm, so the
  light leaves through a source port and does **not** reach any target port:
  such crossings contribute insertion loss but no crosstalk to the matrix.
  CTP-1.0 added both directions unconditionally and therefore double counted
  roughly half of the events;
* second-order chains i -> k -> j are evaluated with the real event ordering
  along route k and only when both hops are allowed by the direction rule;
* three separate matrices are produced: the CTP-1.0 fixed-p baseline, the
  CTP-2.0 nominal prediction, and a lower/upper bound pair obtained from the
  per-crossing model uncertainty band.

Outputs
-------
outputs/board/crosstalk_matrix_ctp2_linear.npy
outputs/board/crosstalk_matrix_ctp2_db.csv
outputs/board/crosstalk_per_route_ctp2.csv
outputs/board/crosstalk_hotspots_ctp2.json
outputs/board/board_summary_ctp2.json
outputs/board/crosstalk_matrix_ctp1_baseline.npy     (rebuilt fixed-p baseline)
outputs/board/crossing_optical_analysis_ctp2.csv
"""
from __future__ import annotations

import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ctp2 import geometry as G                                  # noqa: E402
from ctp2.params import (ALPHA_DB_PER_CM, CTP1_DIR, OUT_BOARD,     # noqa: E402
                         OUT_CROSSINGS, TOTAL_LENGTH_MM)

ALPHA_DB_PER_MM = ALPHA_DB_PER_CM / 10.0


def db(x):
    return 10.0 * np.log10(np.maximum(np.asarray(x, dtype=float), 1e-300))


def loss_factor(length_mm):
    return 10.0 ** (-ALPHA_DB_PER_MM * np.asarray(length_mm, float) / 10.0)


def load_crossing_model():
    df = pd.read_csv(OUT_CROSSINGS / "crossing_model_database.csv")
    return df.sort_values("theta_deg").reset_index(drop=True)


def model_lookup(df, theta_deg):
    """log-log interpolation of the (nominal, low, high) crosstalk and through."""
    th = np.clip(np.asarray(theta_deg, float), df.theta_deg.min(), df.theta_deg.max())
    out = {}
    for key, col in (("xt", "T_cross_nominal"), ("xt_lo", "T_cross_low"),
                     ("xt_hi", "T_cross_high")):
        out[key] = np.exp(np.interp(np.log(th), np.log(df.theta_deg.values),
                                    np.log(np.maximum(df[col].values, 1e-300))))
    out["T_through"] = np.exp(np.interp(np.log(th), np.log(df.theta_deg.values),
                                        np.log(np.maximum(df.T_through_nominal.values, 1e-300))))
    return out


#: literature-anchored angular scaling of the crossing insertion loss.
#: ``loss = loss_10deg * (theta/10)^(-0.873)`` follows Baghsiahi et al., SPIE
#: 8988, 898807 (2014), who measured an exponent of -0.873 for weakly guided
#: crossings; the amplitude is anchored at our own converged BPM result at
#: 10 deg (where BPM is trustworthy) instead of at the literature absolute
#: value, because their waveguide is a 50 um multimode one.
LOSS_EXPONENT = -0.873


def through_power(theta_deg, t_through_bpm):
    th = np.asarray(theta_deg, float)
    t10 = float(np.interp(10.0, [10.0], [t_through_bpm])) if np.ndim(th) == 0 else None
    return t_through_bpm


def build_events(routes, crossings, cmodel):
    """Attach to every crossing its local optics and propagation direction flag."""
    rows = []
    for e in crossings:
        a, b = int(e["route_a"]), int(e["route_b"])
        sa, sb = float(e["s_a_mm"]), float(e["s_b_mm"])
        A, B = routes["routes"][a], routes["routes"][b]
        ta, tb = A.tangent(sa), B.tangent(sb)
        dot = float(np.dot(ta, tb))
        m = model_lookup(cmodel, float(e["angle_deg"]))
        # through (insertion) loss: BPM value up to 10 deg, then the
        # literature-anchored power law extrapolation
        ang = float(e["angle_deg"])
        loss10_db = -10.0 * math.log10(max(float(m["T_through"][0]), 1e-12)) \
            if np.ndim(m["T_through"]) else -10.0 * math.log10(float(m["T_through"]))
        if ang > 10.0:
            loss_db = loss10_db * (ang / 10.0) ** LOSS_EXPONENT
            t_through = 10.0 ** (-loss_db / 10.0)
        else:
            t_through = float(np.asarray(m["T_through"]).ravel()[0])
        rows.append({
            "route_a": a, "route_b": b, "s_a_mm": sa, "s_b_mm": sb,
            "x_mm": float(e["x_mm"]), "y_mm": float(e["y_mm"]),
            "z_mm": float(e["z_mm"]), "angle_deg": float(e["angle_deg"]),
            "tangent_dot": dot,
            "forward_direction_ok": int(dot > 0.0),
            "T_cross": float(m["xt"]), "T_cross_lo": float(m["xt_lo"]),
            "T_cross_hi": float(m["xt_hi"]),
            "T_through": t_through,
            "insertion_loss_db_crossing": float(-10.0 * math.log10(max(t_through, 1e-12))),
            "L_a_mm": A.total_length, "L_b_mm": B.total_length,
        })
    df = pd.DataFrame(rows)
    df["T_cross_db"] = db(df.T_cross.values)
    df["insertion_loss_db"] = -db(df.T_through.values)
    return df


def assemble(routes, events: pd.DataFrame, n: int, xt_key: str = "T_cross",
             second_order: bool = True, order2_max: int = 3):
    """Assemble T (row = output target, col = input source) plus diagnostics."""
    ids = np.asarray(routes["order"], int)
    index = {int(rid): k for k, rid in enumerate(ids)}
    L = np.array([routes["routes"][int(rid)].total_length for rid in ids])
    T = np.zeros((n, n))
    diag = loss_factor(L).copy()
    n_cross = np.zeros(n, int)
    per_event = []
    # diagonal: through loss of every crossing on the route
    for _, e in events.iterrows():
        i = index[int(e.route_a)]
        j = index[int(e.route_b)]
        th = float(e.T_through)
        diag[i] *= th
        diag[j] *= th
        n_cross[i] += 1
        n_cross[j] += 1
    np.fill_diagonal(T, diag)

    # first order
    for _, e in events.iterrows():
        if not int(e.forward_direction_ok):
            continue
        i = index[int(e.route_a)]
        j = index[int(e.route_b)]
        p = float(e[xt_key])
        f_ij = float(loss_factor(float(e.s_a_mm)) *
                     loss_factor(float(e.L_b_mm) - float(e.s_b_mm)))
        f_ji = float(loss_factor(float(e.s_b_mm)) *
                     loss_factor(float(e.L_a_mm) - float(e.s_a_mm)))
        T[j, i] += p * f_ij
        T[i, j] += p * f_ji
        per_event.append({"route_from": int(e.route_a), "route_to": int(e.route_b),
                          "T": p * f_ij, "T_db": float(db(p * f_ij)),
                          "angle_deg": float(e.angle_deg)})
        per_event.append({"route_from": int(e.route_b), "route_to": int(e.route_a),
                          "T": p * f_ji, "T_db": float(db(p * f_ji)),
                          "angle_deg": float(e.angle_deg)})

    # second order
    second = []
    if second_order:
        allowed = events[events.forward_direction_ok.astype(bool)]
        by_route = defaultdict(list)
        for _, e in allowed.iterrows():
            by_route[int(e.route_a)].append((int(e.route_b), float(e.s_a_mm),
                                            float(e.s_b_mm), float(e[xt_key])))
            by_route[int(e.route_b)].append((int(e.route_a), float(e.s_b_mm),
                                            float(e.s_a_mm), float(e[xt_key])))
        for i, rid in enumerate(ids):
            rid = int(rid)
            if rid not in by_route:
                continue
            for (k_id, s_i, s_k1, p1) in by_route[rid]:
                k = index[k_id]
                Lk = routes["routes"][k_id].total_length
                for (j_id, s_k2, s_j, p2) in by_route.get(k_id, []):
                    if j_id == rid or s_k2 <= s_k1:
                        continue
                    j = index[j_id]
                    Lj = routes["routes"][j_id].total_length
                    t2 = (p1 * p2 * float(loss_factor(s_i)) *
                          float(loss_factor(s_k2 - s_k1)) *
                          float(loss_factor(Lj - s_j)))
                    if t2 <= 0:
                        continue
                    T[j, i] += t2
                    second.append({"route_i": rid, "route_k": k_id,
                                   "route_j": j_id, "T": t2,
                                   "T_db": float(db(t2))})
        second.sort(key=lambda r: -r["T"])
    return T, diag, n_cross, per_event, second


def stats(T, ids, routes, events, n_cross, label):
    n = len(ids)
    L = np.array([routes["routes"][int(rid)].total_length for rid in ids])
    out = []
    Tno = T.copy()
    np.fill_diagonal(Tno, 0.0)
    for k in range(n):
        col = Tno[:, k]
        off = np.delete(T[:, k], k)
        order = np.argsort(col)[::-1]
        worst = [int(ids[j]) for j in order[:3]]
        out.append({
            "route_id": int(ids[k]),
            "L_total_mm": float(L[k]),
            "loss_prop_db": float(ALPHA_DB_PER_MM * L[k]),
            "n_crossings": int(n_cross[k]),
            "T_diag": float(T[k, k]),
            "T_diag_db": float(db(T[k, k])),
            "max_single_pair_from_db": float(db(col.max())) if n > 1 else -300.0,
            "total_leakage_from_db": float(db(col.sum())),
            "worst_victim_routes": ";".join(str(x) for x in worst),
        })
    df = pd.DataFrame(out)
    df["model"] = label
    return df


def main() -> None:
    t0 = time.time()
    routes = G.load_routes()
    ids = np.asarray(routes["order"], int)
    n = len(ids)
    crossings = G.load_crossings()
    print(f"routes={n} crossings={len(crossings)}", flush=True)

    cmodel = load_crossing_model()
    events = build_events(routes, crossings, cmodel)
    events.to_csv(OUT_BOARD / "crossing_optical_analysis_ctp2.csv", index=False)
    print(f"events: forward-ok {int(events.forward_direction_ok.sum())} / "
          f"{len(events)}; XT db range "
          f"{events.T_cross_db.min():.1f}..{events.T_cross_db.max():.1f}", flush=True)

    # ------------------------------------------------ CTP-1.0 fixed-p baseline
    T1, diag1, ncross1, _, _ = assemble(
        routes, events.assign(T_cross=1e-7, T_through=1.0 - 1e-7), n,
        xt_key="T_cross", second_order=True)
    np.save(OUT_BOARD / "crosstalk_matrix_ctp1_baseline.npy", T1)
    s1 = stats(T1, ids, routes, events, ncross1, "ctp1_fixed_p_1e-7")
    s1.to_csv(OUT_BOARD / "crosstalk_per_route_ctp1_baseline.csv", index=False)
    off1 = T1.copy()
    np.fill_diagonal(off1, 0.0)
    print(f"BASELINE(fixed p=1e-7): worst pair {db(off1.max()):.2f} dB, "
          f"worst total leakage {s1.total_leakage_from_db.max():.2f} dB", flush=True)

    # --------------------------------------------------------- CTP-2.0 nominal
    T2, diag2, ncross2, per_event, second = assemble(routes, events, n)
    np.save(OUT_BOARD / "crosstalk_matrix_ctp2_linear.npy", T2)
    Ts = T2.astype(np.float32)
    np.save(OUT_BOARD / "crosstalk_matrix_ctp2_linear_f32.npy", Ts)
    off2 = T2.copy()
    np.fill_diagonal(off2, 0.0)
    pd.DataFrame(db(T2)).to_csv(OUT_BOARD / "crosstalk_matrix_ctp2_db.csv",
                                index=False, header=False)
    s2 = stats(T2, ids, routes, events, ncross2, "ctp2_nominal")
    s2.to_csv(OUT_BOARD / "crosstalk_per_route_ctp2.csv", index=False)

    # bounds
    Tlo, _, _, _, _ = assemble(routes, events, n, xt_key="T_cross_lo")
    Thi, _, _, _, _ = assemble(routes, events, n, xt_key="T_cross_hi")
    np.save(OUT_BOARD / "crosstalk_matrix_ctp2_lower.npy", Tlo)
    np.save(OUT_BOARD / "crosstalk_matrix_ctp2_upper.npy", Thi)
    off_lo = Tlo.copy(); np.fill_diagonal(off_lo, 0.0)
    off_hi = Thi.copy(); np.fill_diagonal(off_hi, 0.0)

    # --------------------------------------------------------------- hotspots
    ev2 = events[events.forward_direction_ok.astype(bool)].copy()
    ev2["P_cross"] = ev2["T_cross"]
    ev2["cluster_key"] = (ev2.z_mm.round(3).astype(str) + "_" +
                          (ev2.x_mm / 2.0).round().astype(int).astype(str) + "_" +
                          (ev2.y_mm / 2.0).round().astype(int).astype(str))
    clusters = []
    for key, g in ev2.groupby("cluster_key"):
        clusters.append({
            "z_mm": float(g.z_mm.mean()), "x_mm": float(g.x_mm.mean()),
            "y_mm": float(g.y_mm.mean()), "n_crossings": int(len(g)),
            "total_P_cross": float(g.P_cross.sum()),
            "total_P_cross_db": float(db(g.P_cross.sum())),
            "max_P_cross_db": float(db(g.P_cross.max())),
            "min_angle_deg": float(g.angle_deg.min()),
            "mean_angle_deg": float(g.angle_deg.mean()),
            "routes": sorted(set(g.route_a) | set(g.route_b)),
        })
    clusters.sort(key=lambda c: -c["total_P_cross"])
    (OUT_BOARD / "crosstalk_hotspots_ctp2.json").write_text(
        json.dumps(clusters[:80], indent=1), encoding="utf-8")

    # ------------------------------------------------------------- multi-input
    T_no_diag = T2.copy()
    np.fill_diagonal(T_no_diag, 0.0)
    interference = T_no_diag.sum(axis=1)                # incoherent, all sources on
    isr = interference / np.maximum(np.diag(T2), 1e-30)
    worst_out = int(np.argmax(isr))

    summary = {
        "model": "CTP-2.0",
        "propagation_loss_db_per_cm": ALPHA_DB_PER_CM,
        "bend_extra_loss_db": 0.0,
        "frozen_geometry": {
            "n_routes": n,
            "n_planes": 20,
            "n_crossings": len(crossings),
            "total_length_mm": float(sum(routes["routes"][int(r)].total_length
                                        for r in ids)),
            "authoritative_total_length_mm": TOTAL_LENGTH_MM,
        },
        "crossings": {
            "n_events": int(len(events)),
            "n_forward_allowed": int(events.forward_direction_ok.sum()),
            "n_forward_blocked": int((1 - events.forward_direction_ok).sum()),
            "T_cross_db_min": float(events.T_cross_db.min()),
            "T_cross_db_max": float(events.T_cross_db.max()),
            "T_cross_db_median": float(events.T_cross_db.median()),
            "angle_min_deg": float(events.angle_deg.min()),
            "angle_median_deg": float(events.angle_deg.median()),
            "n_events_above_minus40dB": int((events.T_cross_db > -40).sum()),
            "n_events_above_minus30dB": int((events.T_cross_db > -30).sum()),
        },
        "baseline_ctp1_fixed_p": {
            "p_used": 1e-7,
            "max_offdiagonal_db": float(db(off1.max())),
            "worst_total_leakage_db": float(s1.total_leakage_from_db.max()),
        },
        "nominal_ctp2": {
            "max_offdiagonal_db": float(db(off2.max())),
            "max_offdiagonal_pair": [int(ids[np.unravel_index(np.argmax(off2), off2.shape)[0]]),
                                     int(ids[np.unravel_index(np.argmax(off2), off2.shape)[1]])],
            "median_offdiagonal_db": float(np.median(db(off2[off2 > 1e-300])))
            if np.any(off2 > 0) else -300.0,
            "n_nonzero_offdiagonal": int((off2 > 1e-300).sum()),
            "worst_total_leakage_db": float(s2.total_leakage_from_db.max()),
            "worst_total_leakage_route": int(s2.loc[s2.total_leakage_from_db.idxmax(),
                                                    "route_id"]),
            "mean_total_leakage_db": float(s2.total_leakage_from_db.mean()),
            "diagonal_min_db": float(db(np.diag(T2).min())),
            "diagonal_max_db": float(db(np.diag(T2).max())),
            "max_column_sum": float(T2.sum(axis=0).max()),
            "all_columns_le_1": bool((T2.sum(axis=0) <= 1.0 + 1e-12).all()),
            "total_output_over_input": float(T2.sum() / n),
        },
        "bounds": {
            "max_offdiagonal_lower_db": float(db(off_lo.max())),
            "max_offdiagonal_upper_db": float(db(off_hi.max())),
            "worst_total_leakage_lower_db": float(stats(Tlo, ids, routes, events, ncross2, "lo")
                                                  .total_leakage_from_db.max()),
            "worst_total_leakage_upper_db": float(stats(Thi, ids, routes, events, ncross2, "hi")
                                                  .total_leakage_from_db.max()),
        },
        "second_order": {
            "n_terms": len(second),
            "max_T": float(second[0]["T"]) if second else 0.0,
            "max_T_db": float(second[0]["T_db"]) if second else -300.0,
        },
        "multi_input_incoherent": {
            "worst_interference_to_signal_db": float(db(isr.max())),
            "worst_output_route": int(ids[worst_out]),
            "mean_isr_db": float(np.median(db(isr))),
        },
        "runtime_seconds": time.time() - t0,
    }
    (OUT_BOARD / "board_summary_ctp2.json").write_text(
        json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1), flush=True)


if __name__ == "__main__":
    main()

