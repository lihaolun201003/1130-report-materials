"""ANOMALY D - the fixed-p (1e-7) full-board model.

Recomputes the 1024x1024 transfer matrix with p = 1e-7, 1e-5, 1e-3 (and a
per-event angle-dependent p for comparison) and shows that every headline
number is pure  p x (geometric/loss weight)  bookkeeping.

Outputs: d_board_scaling.csv, d_pair_weight.csv, d_summary.json
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pandas as pd

import audit_lib as AL
from src.board import build_board, db
from src.dataio import load_dataset

OUT = AL.AUDIT


def board_stats(T, ids):
    n = len(ids)
    off = T.copy()
    np.fill_diagonal(off, 0.0)
    diag = np.diag(T)
    col = T.sum(axis=0)
    offcol = off.sum(axis=0)
    i, j = np.unravel_index(np.argmax(off), off.shape)
    return {
        "matrix_shape": n,
        "max_offdiag_db": float(db(off.max())),
        "max_offdiag_value": float(off.max()),
        "max_offdiag_pair": [int(ids[i]), int(ids[j])],
        "worst_total_leakage_db": float(db(offcol.max())),
        "worst_total_leakage_value": float(offcol.max()),
        "worst_leakage_col_route": int(ids[int(np.argmax(offcol))]),
        "median_offdiag_db": float(db(np.median(off[off > 0]))) if np.any(off > 0) else -300.0,
        "n_nonzero_offdiag": int(np.count_nonzero(off)),
        "diag_min_db": float(db(diag.min())),
        "diag_mean_db": float(db(diag.mean())),
        "diag_max_db": float(db(diag.max())),
        "max_col_sum": float(col.max()),
        "min_col_sum": float(col.min()),
        "all_cols_le_1": bool(col.max() <= 1.0 + 1e-12),
    }


def main():
    opt = AL.reference_optics()
    ds = load_dataset(AL.CONFIG["inputs"]["best_valid_dir"],
                      verify_hash=AL.CONFIG["inputs"]["verify_sha256"])
    events = pd.read_csv(Path(AL.LEGACY) / "outputs" / "geometry"
                         / "crossing_events_detected.csv").to_dict("records")
    print(f"routes={len(ds.routes)} events={len(events)}")
    # the fixed-p path is exactly what run_e5.py does
    p_floor = float(AL.CONFIG["crossing_model"]["resolution_floor"])
    results = {}
    rows = []
    for p in (1e-7, 1e-5, 1e-3, 1e-2):
        b = build_board(ds.routes, events, p)
        st = board_stats(b.T_upper, b.route_ids)
        st["p"] = p
        st["second_order_max_T"] = (b.second_order[0]["T"] if b.second_order else 0.0)
        st["second_order_max_T_db"] = (b.second_order[0]["T_db"] if b.second_order else -300.0)
        results[str(p)] = st
        rows.append(st)
        print(f"p={p:.1e}: max offdiag {st['max_offdiag_db']:.2f} dB  "
              f"worst leakage {st['worst_total_leakage_db']:.2f} dB  "
              f"diag {st['diag_min_db']:.3f}..{st['diag_max_db']:.3f} dB  "
              f"colsum {st['min_col_sum']:.4f}..{st['max_col_sum']:.4f}", flush=True)

    # exact scaling law: T_max(p) = p * W_max ; leakage_max(p) = p * V_max
    st1 = results[str(p_floor)]
    W_max = st1["max_offdiag_value"] / p_floor
    V_max = st1["worst_total_leakage_value"] / p_floor
    print(f"\nscale-invariant weights: W_max={W_max:.6f}  V_max={V_max:.6f}")
    for p in (1e-7, 1e-5, 1e-3, 1e-2):
        pred_pair = db(p * W_max)
        pred_leak = db(p * V_max)
        print(f"  p={p:.1e} predicted pair={pred_pair:.3f} dB (measured "
              f"{results[str(p)]['max_offdiag_db']:.3f}), leakage={pred_leak:.3f} dB "
              f"(measured {results[str(p)]['worst_total_leakage_db']:.3f})")

    # T_upper vs T_nominal identity
    b = build_board(ds.routes, events, p_floor)
    ident = bool(np.array_equal(b.T_upper, b.T_nominal))
    print(f"\nT_upper == T_nominal exactly: {ident}")

    # event-level weights: total weight per ordered pair
    from collections import defaultdict
    w = defaultdict(float)
    for e in events:
        i, j = int(e["route_a"]), int(e["route_b"])
        L = {r.route_id: r.total_length for r in ds.routes}
        alpha = AL.CONFIG["optics"]["propagation_loss_db_per_cm"] / 10.0
        f_ij = 10 ** (-alpha * (float(e["s_a_mm"]) + L[j] - float(e["s_b_mm"])) / 10.0)
        f_ji = 10 ** (-alpha * (float(e["s_b_mm"]) + L[i] - float(e["s_a_mm"])) / 10.0)
        w[(j, i)] += f_ij
        w[(i, j)] += f_ji
    (i_best, j_best), Wb = max(w.items(), key=lambda kv: kv[1])
    print(f"worst ordered pair {i_best}->{j_best}: weight W={Wb:.6f} "
          f"(= sum of {sum(1 for e in events if {int(e['route_a']), int(e['route_b'])} == {i_best, j_best})} events' loss factors)")
    pair_rows = [{"out_route": a, "in_route": b_, "weight_W": v,
                  "T_at_p1e-7": v * 1e-7} for (a, b_), v in
                 sorted(w.items(), key=lambda kv: -kv[1])[:20]]

    # angle dependence completely discarded: P_cross_used per event
    coa = pd.read_csv(Path(AL.LEGACY) / "outputs" / "optical"
                      / "crossing_optical_analysis.csv")
    used = coa["P_cross_used"].to_numpy()
    fdfd = coa["P_cross_fdfd"].to_numpy()
    ang = coa["angle_deg"].to_numpy()
    print(f"\nevents: {len(used)}, unique P_cross_used = {np.unique(used)}, "
          f"at_floor = {int(coa['at_resolution_floor'].sum())}")
    print(f"  correlation(angle, P_cross_used) = {np.corrcoef(ang, used)[0,1]:.3e}")
    print(f"  correlation(angle, P_cross_fdfd) = {np.corrcoef(ang, fdfd)[0,1]:.3f}")
    print(f"  P_cross_fdfd range: {fdfd.min():.3e} .. {fdfd.max():.3e}")
    print(f"  event angle range: {ang.min():.2f} .. {ang.max():.2f} deg; "
          f"mean angle={ang.mean():.2f}")

    # angle-dependent alternative: use the *corrected* FDFD curve (from anomaly A)
    corr_csv = OUT / "a_legacy_vs_corrected.csv"
    sum_csv = OUT / "a_summary.csv"
    angle_rows = []
    if corr_csv.exists() and sum_csv.exists():
        ca = pd.read_csv(corr_csv)
        sa = pd.read_csv(sum_csv)
        th = ca["theta_deg"].to_numpy()
        tc = np.maximum(ca["T_cross"].to_numpy(), 1e-300)
        tcf = np.maximum(ca["T_cross_fund"].to_numpy(), 1e-300)
        pb = np.interp(ang, th, tc)
        pb_f = np.interp(ang, th, tcf)
        leg_th = sa["theta_deg"].to_numpy()
        leg_tc = sa["legacy_T_cross"].to_numpy()
        pf = np.maximum(np.interp(ang, leg_th, leg_tc), 1e-300)
        events_p = []
        for e, p_ev in zip(events, pb):
            e2 = dict(e); e2["p"] = float(p_ev)
            events_p.append(e2)
        # build_board only takes a scalar p, so emulate per-event weight scaling
        b0 = build_board(ds.routes, events, 0.0)        # p=0 -> pure losses
        diag_loss = np.diag(b0.T_nominal).copy()
        idx = {int(rid): k for k, rid in enumerate(b0.route_ids)}
        L = {r.route_id: r.total_length for r in ds.routes}
        alpha = AL.CONFIG["optics"]["propagation_loss_db_per_cm"] / 10.0

        def build_event_matrix(p_ev):
            Tm = np.zeros((len(idx), len(idx)))
            np.fill_diagonal(Tm, diag_loss)
            for e, pe in zip(events, p_ev):
                i, j = idx[int(e["route_a"])], idx[int(e["route_b"])]
                f_ij = 10 ** (-alpha * (float(e["s_a_mm"]) + L[int(e["route_b"])]
                                        - float(e["s_b_mm"])) / 10.0)
                f_ji = 10 ** (-alpha * (float(e["s_b_mm"]) + L[int(e["route_a"])]
                                        - float(e["s_a_mm"])) / 10.0)
                Tm[j, i] += pe * f_ij
                Tm[i, j] += pe * f_ji
            # diagonal throughput reduction
            for rid, k in idx.items():
                pev = [pe for e, pe in zip(events, p_ev)
                       if int(e["route_a"]) == rid or int(e["route_b"]) == rid]
                if pev:
                    Tm[k, k] = diag_loss[k] * float(np.prod([1.0 - x for x in pev]))
            return Tm, idx

        T_ang, _ = build_event_matrix(pb)
        st_ang = board_stats(T_ang, b0.route_ids)
        st_ang["p"] = "angle_dependent_corrected"
        T_angf, _ = build_event_matrix(pb_f)
        st_angf = board_stats(T_angf, b0.route_ids)
        st_angf["p"] = "angle_dependent_corrected_fund"
        angle_rows.append(st_angf)
        angle_rows.append(st_ang)
        print("\nangle-dependent corrected-FDFD board:")
        print(f"  max offdiag {st_ang['max_offdiag_db']:.2f} dB, worst leakage "
              f"{st_ang['worst_total_leakage_db']:.2f} dB, colsum max "
              f"{st_ang['max_col_sum']:.4f}")
        # probability-like model with the *legacy* FDFD curve
        T_leg, _ = build_event_matrix(pf)
        st_leg = board_stats(T_leg, b0.route_ids)
        st_leg["p"] = "angle_dependent_legacy"
        angle_rows.append(st_leg)
        print(f"  [legacy angle curve] max offdiag {st_leg['max_offdiag_db']:.2f} dB, "
              f"worst leakage {st_leg['worst_total_leakage_db']:.2f} dB")

    # energy structure: what p would be needed for column sums to exceed 1
    print("\n== column-sum structure ==")
    b = build_board(ds.routes, events, p_floor)
    T = b.T_upper
    n_cross = np.array([sum(1 for e in events if int(e["route_a"]) == rid
                            or int(e["route_b"]) == rid)
                        for rid in b.route_ids], float)
    loss = np.diag(b.T_nominal)
    # max possible column sum if every off-diagonal loss factor were 1:
    bound = loss * (1 - p_floor) ** n_cross + p_floor * n_cross
    print(f"  n_cross range {n_cross.min():.0f}..{n_cross.max():.0f}; "
          f"diag(loss) range {loss.min():.4f}..{loss.max():.4f}")
    print(f"  column sums {T.sum(axis=0).min():.4f}..{T.sum(axis=0).max():.4f} "
          f"(bound if all f=1: {bound.max():.6f})")
    # with alpha=0 and all f=1 the p=1e-3 board would violate energy:
    n = n_cross.max()
    for p in (1e-3, 1e-2):
        print(f"  hypothetical no-propagation-loss, n_events={int(n):d}, p={p:.0e}: "
              f"(1-p)^n + n p = {(1-p)**n + n*p:.8f}")
    AL.jdump(OUT / "d_summary.json", {
        "scaling": results,
        "W_max": W_max, "V_max": V_max,
        "formula": "max_offdiag(p) = p * W_max ; worst_total_leakage(p) = p * V_max ; "
                   "dB shifts by 10 log10(p2/p1)",
        "T_upper_equals_T_nominal": ident,
        "worst_pair_weight": {"pair": [i_best, j_best], "W": Wb},
        "events_unique_p_used": np.unique(used).tolist(),
        "events_all_at_floor": int(coa["at_resolution_floor"].sum()),
        "corr_angle_p_used": float(np.corrcoef(ang, used)[0, 1]),
        "corr_angle_p_fdfd": float(np.corrcoef(ang, fdfd)[0, 1]),
        "p_fdfd_range": [float(fdfd.min()), float(fdfd.max())],
        "angle_range_deg": [float(ang.min()), float(ang.max())],
        "angle_dependent": angle_rows,
        "column_sum_bound": float(bound.max()),
        "no_loss_column_sum_p1e-3": float((1 - 1e-3) ** n + n * 1e-3),
        "no_loss_column_sum_p1e-2": float((1 - 1e-2) ** n + n * 1e-2),
    })
    AL.write_csv(OUT / "d_board_scaling.csv", rows)
    AL.write_csv(OUT / "d_pair_weight.csv", pair_rows)
    AL.write_csv(OUT / "d_angle_dependent.csv", angle_rows)
    print("\n[ANOMALY D] done")


if __name__ == "__main__":
    main()
