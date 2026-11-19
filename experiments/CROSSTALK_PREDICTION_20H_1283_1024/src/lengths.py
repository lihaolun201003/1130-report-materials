"""E1 - 1024 route parsing, true length decomposition and propagation loss."""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from .config import CONFIG
from .dataio import TOTAL_LENGTH_MM, Dataset


def length_table(ds: Dataset) -> list[dict]:
    alpha = CONFIG["optics"]["propagation_loss_db_per_cm"]     # dB/cm
    alpha_per_mm = alpha / 10.0                                # dB/mm
    rows: list[dict] = []
    for r in ds.routes:
        L_straight = sum(g.length for g in r.segments if g.kind == "line")
        L_arc = sum(g.length for g in r.segments if g.kind == "arc")
        L_trans = sum(g.length for g in r.segments if g.kind == "transition")
        L_other = sum(g.length for g in r.segments
                      if g.kind not in ("line", "arc", "transition"))
        L_tot = L_straight + L_arc + L_trans + L_other
        # per-tag decomposition (lead / fanout / body / mid)
        by_tag = defaultdict(float)
        for g in r.segments:
            by_tag[g.tag or "untagged"] += g.length
        loss_prop = alpha_per_mm * L_tot
        loss_bend = CONFIG["optics"]["bend_extra_loss_db"] * 1.0
        rows.append({
            "route_id": r.route_id,
            "source_endpoint": r.source_endpoint,
            "target_endpoint": r.target_endpoint,
            "source_side": r.source_side,
            "target_side": r.target_side,
            "plane": r.plane,
            "layer_role": r.layer_role,
            "target_plane": r.target_plane,
            "target_plane_label": r.target_plane_label,
            "target_z_mm": r.target_z_mm,
            "start_z_mm": r.start_z_mm,
            "n_transitions": r.n_transitions,
            "n_mid_transitions": r.n_mid_transitions,
            "native_3d": int(r.native_3d),
            "direct": int(r.direct),
            "n_segments": len(r.segments),
            "n_line": sum(1 for g in r.segments if g.kind == "line"),
            "n_arc": sum(1 for g in r.segments if g.kind == "arc"),
            "L_straight_mm": L_straight,
            "L_planar_arc_mm": L_arc,
            "L_transition_arc_mm": L_trans,
            "L_other_curve_mm": L_other,
            "L_total_mm": L_tot,
            "L_declared_mm": r.declared_length,
            "L_decomposition_error_mm": L_tot - r.declared_length,
            "L_lead_mm": by_tag.get("lead", 0.0),
            "L_fanout_mm": by_tag.get("fanout", 0.0),
            "L_body_mm": by_tag.get("body", 0.0),
            "L_mid_mm": by_tag.get("mid", 0.0),
            "L_xy_plan_mm": r.xy_length,
            "alpha_db_per_cm": alpha,
            "loss_prop_db": loss_prop,
            "loss_bend_extra_db": loss_bend,
            "loss_base_db": loss_prop + loss_bend,
            "power_transmission_diag": 10.0 ** (-(loss_prop + loss_bend) / 10.0),
            "amplitude_transmission_diag": 10.0 ** (-(loss_prop + loss_bend) / 20.0),
        })
    rows.sort(key=lambda x: x["route_id"])
    return rows


def summary(rows: list[dict]) -> dict:
    L = np.array([r["L_total_mm"] for r in rows])
    tot = float(L.sum())
    abs_err = tot - TOTAL_LENGTH_MM
    rel_err = abs_err / TOTAL_LENGTH_MM
    dec_err = np.array([r["L_decomposition_error_mm"] for r in rows])
    return {
        "route_count": len(rows),
        "unique_route_ids": len({r["route_id"] for r in rows}),
        "total_length_mm": tot,
        "authoritative_total_length_mm": TOTAL_LENGTH_MM,
        "absolute_error_mm": abs_err,
        "relative_error": rel_err,
        "max_route_decomposition_error_mm": float(np.abs(dec_err).max()),
        "total_L_straight_mm": float(sum(r["L_straight_mm"] for r in rows)),
        "total_L_planar_arc_mm": float(sum(r["L_planar_arc_mm"] for r in rows)),
        "total_L_transition_arc_mm": float(sum(r["L_transition_arc_mm"] for r in rows)),
        "total_L_other_curve_mm": float(sum(r["L_other_curve_mm"] for r in rows)),
        "length_mean_mm": float(L.mean()),
        "length_std_mm": float(L.std(ddof=1)),
        "length_min_mm": float(L.min()),
        "length_max_mm": float(L.max()),
        "length_p05_mm": float(np.percentile(L, 5)),
        "length_p50_mm": float(np.percentile(L, 50)),
        "length_p95_mm": float(np.percentile(L, 95)),
        "total_loss_db": float(sum(r["loss_base_db"] for r in rows)),
        "loss_mean_db": float(np.mean([r["loss_base_db"] for r in rows])),
        "loss_min_db": float(np.min([r["loss_base_db"] for r in rows])),
        "loss_max_db": float(np.max([r["loss_base_db"] for r in rows])),
        "n_routes_with_mid_transition": int(sum(1 for r in rows if r["n_mid_transitions"] > 0)),
        "n_multi_arc_routes": int(sum(1 for r in rows if r["n_arc"] >= 2)),
        "total_segments": int(sum(r["n_segments"] for r in rows)),
        "total_lines": int(sum(r["n_line"] for r in rows)),
        "total_arcs": int(sum(r["n_arc"] for r in rows)),
        "length_check_passed": abs(abs_err) < 1e-4,
        "all_decompositions_exact": bool(np.abs(dec_err).max() < 1e-9),
        "alpha_db_per_cm": CONFIG["optics"]["propagation_loss_db_per_cm"],
        "bend_extra_loss_db": CONFIG["optics"]["bend_extra_loss_db"],
    }
