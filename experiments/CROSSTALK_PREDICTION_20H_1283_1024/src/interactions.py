"""E4 - true 3-D interaction analysis over all 1024 routes.

Two complementary products:

* ``detect_crossings``  - independent analytic re-derivation of every same-plane
  centre-line intersection (expected: 1283 events / 1221 route pairs), with the
  local tangents, crossing angle and the arclength position on both routes.
* ``near_approaches``   - all non-crossing 3-D close approaches, found with a
  spatial index (KD-tree over route samples) and refined to the true minimum
  centre-line distance.  Cross-layer, transition and multi-arc cases are kept
  and classified, never assumed to be zero.

All distances are mm unless the column name says ``_um``.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
from scipy.spatial import cKDTree

from .config import CONFIG
from .geom3d import Route, Segment


# --------------------------------------------------------------- intersections
def _line_line(p1, d1, p2, d2):
    den = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(den) < 1e-14:
        return None
    dp = p2 - p1
    t = (dp[0] * d2[1] - dp[1] * d2[0]) / den
    u = (dp[0] * d1[1] - dp[1] * d1[0]) / den
    return t, u


def _line_circle(p, d, c, r):
    """Intersections of p + t d with |x-c|=r; returns list of t."""
    a = float(d @ d)
    b = 2.0 * float(d @ (p - c))
    cc = float((p - c) @ (p - c)) - r * r
    disc = b * b - 4 * a * cc
    if disc < 0:
        return []
    sq = math.sqrt(disc)
    return [(-b - sq) / (2 * a), (-b + sq) / (2 * a)]


def _circle_circle(c1, r1, c2, r2):
    d = float(np.linalg.norm(c2 - c1))
    if d < 1e-14 or d > r1 + r2 or d < abs(r1 - r2):
        return []
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h2 = r1 * r1 - a * a
    if h2 < 0:
        return []
    h = math.sqrt(h2)
    base = c1 + a * (c2 - c1) / d
    perp = np.array([-(c2[1] - c1[1]), c2[0] - c1[0]]) / d
    return [base + h * perp, base - h * perp]


def _unwrap_arc_angle(seg: Segment, ang: float, tol: float = 1e-9):
    """Return the branch of ``ang`` inside the arc's angular span, else None."""
    a0, a1 = seg.start_angle, seg.start_angle + seg.sweep
    lo, hi = min(a0, a1), max(a0, a1)
    k0 = math.floor((lo - ang) / (2 * math.pi)) - 1
    k1 = math.ceil((hi - ang) / (2 * math.pi)) + 1
    for kk in range(k0, k1 + 1):
        a = ang + kk * 2 * math.pi
        if lo - tol <= a <= hi + tol:
            return a
    return None


def _arc_angle_ok(seg: Segment, ang: float, tol: float = 1e-9) -> bool:
    return _unwrap_arc_angle(seg, ang, tol) is not None


def segment_intersections(a: Segment, b: Segment) -> list[tuple]:
    """Return (point2d, u_a, u_b) for every centre-line intersection."""
    out: list[tuple] = []
    tol = 1e-9
    if a.kind == "line" and b.kind == "line":
        d1 = a.p1 - a.p0
        d2 = b.p1 - b.p0
        r = _line_line(a.p0, d1, b.p0, d2)
        if r is None:
            return []
        ta, tb = r                      # already normalised to [0, 1]
        if -tol <= ta <= 1 + tol and -tol <= tb <= 1 + tol:
            p = a.p0 + ta * d1
            out.append((p, float(np.clip(ta, 0, 1)), float(np.clip(tb, 0, 1))))
    elif a.kind == "arc" and b.kind == "line":
        d = b.p1 - b.p0
        for t in _line_circle(b.p0, d, a.center, a.radius):
            if not (-tol <= t <= 1 + tol):
                continue
            p = b.p0 + t * d
            au = _unwrap_arc_angle(a, math.atan2(p[1] - a.center[1],
                                                 p[0] - a.center[0]))
            if au is None:
                continue
            ua = (au - a.start_angle) / a.sweep
            out.append((p, float(np.clip(ua, 0, 1)), float(np.clip(t, 0, 1))))
    elif a.kind == "line" and b.kind == "arc":
        d = a.p1 - a.p0
        for t in _line_circle(a.p0, d, b.center, b.radius):
            if not (-tol <= t <= 1 + tol):
                continue
            p = a.p0 + t * d
            bu = _unwrap_arc_angle(b, math.atan2(p[1] - b.center[1],
                                                 p[0] - b.center[0]))
            if bu is None:
                continue
            ub = (bu - b.start_angle) / b.sweep
            out.append((p, float(np.clip(t, 0, 1)), float(np.clip(ub, 0, 1))))
    elif a.kind == "arc" and b.kind == "arc":
        for p in _circle_circle(a.center, a.radius, b.center, b.radius):
            au = _unwrap_arc_angle(a, math.atan2(p[1] - a.center[1],
                                                 p[0] - a.center[0]))
            bu = _unwrap_arc_angle(b, math.atan2(p[1] - b.center[1],
                                                 p[0] - b.center[0]))
            if au is None or bu is None:
                continue
            ua = (au - a.start_angle) / a.sweep
            ub = (bu - b.start_angle) / b.sweep
            out.append((p, float(np.clip(ua, 0, 1)), float(np.clip(ub, 0, 1))))
    return out

def detect_crossings(routes: list[Route]) -> tuple[list[dict], dict]:
    """Analytic same-z centre-line intersections between all route pairs."""
    by_z: dict[float, list[tuple[int, Segment]]] = defaultdict(list)
    for r in routes:
        for g in r.segments:
            if g.kind == "transition":
                continue
            by_z[round(g.z0, 6)].append((r.route_id, g))

    route_by_id = {r.route_id: r for r in routes}
    events: list[dict] = []
    n_tested = 0
    for z, items in sorted(by_z.items()):
        n = len(items)
        for i in range(n):
            ria, ga = items[i]
            for j in range(i + 1, n):
                rib, gb = items[j]
                if ria == rib:
                    continue
                n_tested += 1
                # quick AABB reject
                la, ha = ga.aabb()
                lb, hb = gb.aabb()
                if (la[0] > hb[0] or lb[0] > ha[0] or la[1] > hb[1]
                        or lb[1] > ha[1]):
                    continue
                for (p, ua, ub) in segment_intersections(ga, gb):
                    ta = ga.tangent(ua)
                    tb = gb.tangent(ub)
                    c = float(np.clip(abs(ta @ tb), 0.0, 1.0))
                    ang = math.degrees(math.acos(c))
                    sa = ga.s0 + ua * ga.length
                    sb = gb.s0 + ub * gb.length
                    events.append({
                        "route_a": int(min(ria, rib)),
                        "route_b": int(max(ria, rib)),
                        "z_mm": float(z),
                        "x_mm": float(p[0]),
                        "y_mm": float(p[1]),
                        "angle_deg": float(ang),
                        "s_a_mm": float(sa if ria <= rib else sb),
                        "s_b_mm": float(sb if ria <= rib else sa),
                        "kind_a": ga.kind,
                        "kind_b": gb.kind,
                        "part_index_a": ga.part_index,
                        "part_index_b": gb.part_index,
                        "z_a_mm": float(ga.z0),
                        "z_b_mm": float(gb.z0),
                    })
    stats = {
        "intersection_tests": int(n_tested),
        "raw_events": len(events),
    }
    # de-duplicate coincident intersections (same pair, same plane, < 1 um apart)
    events.sort(key=lambda e: (e["route_a"], e["route_b"], e["z_mm"],
                               -e["angle_deg"], e["x_mm"], e["y_mm"]))
    dedup: list[dict] = []
    for e in events:
        dup = False
        for prev in reversed(dedup[-8:]):
            if (prev["route_a"] == e["route_a"] and prev["route_b"] == e["route_b"]
                    and abs(prev["z_mm"] - e["z_mm"]) < 1e-9
                    and abs(prev["x_mm"] - e["x_mm"]) < 1e-3
                    and abs(prev["y_mm"] - e["y_mm"]) < 1e-3):
                dup = True
                break
        if not dup:
            dedup.append(e)
    for e in dedup:
        e["transverse"] = int(e["angle_deg"] >= 1.0)
    stats.update({
        "events": len(dedup),
        "events_transverse": int(sum(e["transverse"] for e in dedup)),
        "events_tangential": int(sum(1 - e["transverse"] for e in dedup)),
        "pairs": len({(e["route_a"], e["route_b"]) for e in dedup}),
        "routes_with_crossings": len({e["route_a"] for e in dedup}
                                     | {e["route_b"] for e in dedup}),
        "planes": len(by_z),
    })
    return dedup, stats


# --------------------------------------------------------------- near approach
@dataclass
class NearApproach:
    route_a: int
    route_b: int
    d_min_mm: float
    point_a: np.ndarray
    point_b: np.ndarray
    s_a_mm: float
    s_b_mm: float
    z_a_mm: float
    z_b_mm: float
    angle_deg: float
    kind_a: str
    kind_b: str
    dz_mm: float = 0.0
    relation: str = ""


def _sample_segment(g: Segment, step: float, max_pts: int = 4000) -> tuple[np.ndarray, np.ndarray]:
    n = int(min(max(2, math.ceil(g.length / step) + 1), max_pts))
    u = np.linspace(0.0, 1.0, n)
    return u, g.point(u)


def min_distance_between(a: Segment, b: Segment,
                         coarse_step: float = 0.02) -> tuple[float, float, float]:
    """Minimum 3-D distance between two analytic segments (multi-start)."""
    ua, pa = _sample_segment(a, coarse_step)
    ub, pb = _sample_segment(b, coarse_step)
    tree = cKDTree(pb)
    d, idx = tree.query(pa)
    order = np.argsort(d)[:4]
    dmin, u_best, v_best = float("inf"), 0.0, 0.0
    for k in order:
        d0 = float(d[k])
        u0, v0 = float(ua[k]), float(ub[idx[k]])
        span = max(2.0 / max(len(ua) - 1, 1), 2.0 / max(len(ub) - 1, 1)) * 3.0
        lo_u, hi_u = max(0.0, u0 - span), min(1.0, u0 + span)
        lo_v, hi_v = max(0.0, v0 - span), min(1.0, v0 + span)
        for _ in range(45):
            us = np.linspace(lo_u, hi_u, 9)
            vs = np.linspace(lo_v, hi_v, 9)
            P = a.point(us)
            Q = b.point(vs)
            D = np.linalg.norm(P[:, None, :] - Q[None, :, :], axis=2)
            i, j = np.unravel_index(np.argmin(D), D.shape)
            if D[i, j] < dmin:
                dmin = float(D[i, j])
                u_best, v_best = float(us[i]), float(vs[j])
            if D[i, j] < d0:
                d0 = float(D[i, j])
                u0, v0 = float(us[i]), float(vs[j])
            du = (hi_u - lo_u) / 8.0
            dv = (hi_v - lo_v) / 8.0
            lo_u, hi_u = max(0.0, u0 - du), min(1.0, u0 + du)
            lo_v, hi_v = max(0.0, v0 - dv), min(1.0, v0 + dv)
            if du < 1e-8 and dv < 1e-8:
                break
    return dmin, u_best, v_best


def near_approaches(routes: list[Route], cutoff_mm: float | None = None,
                    sample_step_mm: float = 0.1,
                    coarse_step_mm: float = 0.02) -> tuple[list[dict], dict]:
    cfg = CONFIG["interactions"]
    cutoff = float(cutoff_mm if cutoff_mm is not None
                   else cfg["spatial_cutoff_um"] / 1000.0)
    # route samples -> candidate route pairs
    pts = []
    rid = []
    for r in routes:
        P = r.sample(sample_step_mm)
        pts.append(P)
        rid.append(np.full(len(P), r.route_id, dtype=np.int32))
    P = np.vstack(pts)
    RID = np.concatenate(rid)
    tree = cKDTree(P)
    pair_set: set[tuple[int, int]] = set()
    for i, j in tree.query_pairs(r=cutoff, output_type="ndarray"):
        a, b = int(RID[i]), int(RID[j])
        if a != b:
            pair_set.add((min(a, b), max(a, b)))
    n_route_pairs = len(pair_set)

    routes_by_id = {r.route_id: r for r in routes}
    # segment-level candidate filtering
    results: list[dict] = []
    n_seg_pairs = 0
    for (ra, rb) in sorted(pair_set):
        A = routes_by_id[ra]
        B = routes_by_id[rb]
        for ga in A.segments:
            la, ha = ga.aabb()
            for gb in B.segments:
                lb, hb = gb.aabb()
                if (la[0] - cutoff > hb[0] or lb[0] - cutoff > ha[0]
                        or la[1] - cutoff > hb[1] or lb[1] - cutoff > ha[1]
                        or la[2] - cutoff > hb[2] or lb[2] - cutoff > ha[2]):
                    continue
                n_seg_pairs += 1
                # a same-plane transverse intersection is a crossing, not a
                # near approach: record it at d = 0 without numerical search
                is_cross = False
                ua = ub = 0.0
                if (ga.kind != "transition" and gb.kind != "transition"
                        and abs(ga.z0 - gb.z0) < 1e-9):
                    hits = segment_intersections(ga, gb)
                    if hits:
                        is_cross = True
                        _, ua, ub = hits[0]
                        d = 0.0
                if not is_cross:
                    d, ua, ub = min_distance_between(ga, gb, coarse_step_mm)
                    if d > cutoff:
                        continue
                pa = ga.point(ua)
                pb = gb.point(ub)
                ta = ga.tangent(ua)
                tb = gb.tangent(ub)
                ang = math.degrees(math.acos(float(np.clip(abs(ta @ tb), 0, 1))))
                same_plane = abs(ga.z0 - gb.z0) < 1e-9 and ga.kind != "transition" \
                    and gb.kind != "transition"
                results.append({
                    "route_a": ra, "route_b": rb,
                    "d_min_mm": float(d), "d_min_um": float(d * 1000.0),
                    "x_a_mm": float(pa[0]), "y_a_mm": float(pa[1]), "z_a_mm": float(pa[2]),
                    "x_b_mm": float(pb[0]), "y_b_mm": float(pb[1]), "z_b_mm": float(pb[2]),
                    "s_a_mm": float(ga.s0 + ua * ga.length),
                    "s_b_mm": float(gb.s0 + ub * gb.length),
                    "dz_mm": float(pb[2] - pa[2]),
                    "dz_um": float((pb[2] - pa[2]) * 1000.0),
                    "angle_deg": float(ang),
                    "kind_a": ga.kind, "kind_b": gb.kind,
                    "part_kind_a": ga.part_kind, "part_kind_b": gb.part_kind,
                    "z_plane_a_mm": float(ga.z0), "z_plane_b_mm": float(gb.z0),
                    "same_plane": int(same_plane),
                    "crossing": int(d < 1e-6 and same_plane),
                    "involves_transition": int(ga.kind == "transition" or gb.kind == "transition"),
                })
    stats = {
        "cutoff_um": cutoff * 1000.0,
        "total_route_pairs": len(routes) * (len(routes) - 1) // 2,
        "candidate_route_pairs": int(n_route_pairs),
        "segment_pairs_checked": int(n_seg_pairs),
        "raw_approach_records": len(results),
    }
    return results, stats
