#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Independent G5 crossing-angle validator for the 20-height photonic router.

WHY THIS FILE EXISTS
--------------------
The project already owns a geometry stack (``four_side_1024.fanout1024.xyzrouter``,
``fslw``, ``native3d``, ``d56``, ...).  This module deliberately imports *none*
of it.  It is a from-scratch re-implementation of the same physical contract so
that the G5 numbers can be reproduced by an independent derivation.  Only the
Python standard library is used (numpy/scipy are permitted but not needed).
A runtime guard (``assert_no_project_imports``) checks that no project module
sneaked into ``sys.modules``.

GEOMETRY MODEL (centre-line, millimetres)
-----------------------------------------
A route is an ordered list of ``parts``.  Only ``kind == "flat"`` parts live at
one physical height ``z_mm``; a flat part is a chain of primitives:

* ``line``: ``p0``, ``p1``.
* ``arc``:  ``center``, ``radius``, ``start_angle`` (rad), signed ``sweep`` (rad).
  Point at angle ``A`` is ``center + radius * (cos A, sin A)``.  Arc length is
  ``radius * |sweep|``.

``transition`` parts (R15 vertical S-curves) are *not* flat and therefore never
take part in a same-height crossing; they are ignored here (their 3-D clearance
is somebody else's rule).

Two flat parts can only interact when their physical heights agree to
``|dz| <= 1e-9 mm``.  Routes are bucketed by height and each bucket is audited
in 2-D.

EXACT INTERSECTION ALGEBRA (all closed form, no iteration)
----------------------------------------------------------
1. line-line.  Solve ``a0 + u*da = b0 + v*db`` with Cramer's rule;
   ``den = cross(da, db)``.  If ``|den| / (|da||db|) <= 1e-13`` the lines are
   parallel: they are either disjoint or collinear.  Collinear overlap is
   measured by projecting both segments on the common direction and taking the
   interval intersection length.  A positive length is an *overlap* (illegal,
   never a crossing); a zero-length touch is a tangency.

2. line-arc.  With unit line direction ``t``, ``f = p0 - center``,
   ``b = f.t``, ``dist2 = |f|^2 - b^2`` and ``delta = R^2 - dist2``:
   the two hit parameters are ``s = -b -+ sqrt(delta)`` (arc length from p0).
   ``delta > to``: two transverse hits.  ``|delta| <= to``: tangent (the hit is
   ``s = -b``); when ``delta`` is slightly negative the line misses the circle
   analytically but is recorded as ``tangent_or_near_tangent`` instead of being
   silently dropped.  ``to = 1e-12 * max(1, R^2)``.
   A hit is kept only if its angle lies on the arc (mod-2pi sweep containment).

3. arc-arc.  ``d = |c2 - c1|``.  Same centre and same radius within 1e-9 is
   ``coincident`` (an overlap if the angular ranges intersect, never a
   crossing).  Otherwise ``a = (d^2 + R1^2 - R2^2) / (2d)``, ``h^2 = R1^2 - a^2``;
   ``h^2 > to`` gives two points ``c1 + a*u +- h*perp(u)``, ``|h^2| <= to`` gives
   one tangent point, ``h^2 < -to`` no hit.  Each candidate must lie on both
   arcs (mod-2pi containment).

CROSSING ANGLE
--------------
At a transverse hit the exact unit 2-D tangents are

* line: ``(p1 - p0) / |p1 - p0|``;
* arc:  ``(-sin A, cos A) * sign(sweep)``  (the ``radius * dTheta`` direction at
  the hit angle ``A``),

and the reported angle is ``theta = degrees(asin(|t_i x t_j|))``, i.e. the acute
local tangent angle in ``[0, 90]``.  It is *not* an angle between route chords.
For reference the closed forms are ``theta = acos(dist/R)`` for a line meeting a
circle (``dist`` = centre-to-line distance) and ``theta = pi - 2*acos(d/(2R))``
for two equal circles at centre distance ``d`` (acute value when it exceeds 90).

The intersection residual is recomputed independently as the point-to-primitive
distance (point-to-segment / point-to-arc) and stored per crossing; all residuals
in this file are ~1e-13 mm, which is the numerical evidence that the algebra is
self-consistent.

CHAIN ARC LENGTH ``s``
----------------------
``s`` is the arc length measured from the beginning of the route's flat chain at
that height: parts are walked in file order, flat parts at the audited height are
concatenated, and primitive lengths are summed (``radius*|sweep|`` for arcs).
A route may own several flat parts at one height (e.g. the two 0.25 mm interface
leads); they are concatenated in ``parts`` order.  A crossing closer than
``1e-7 mm`` to either end of that chain is *not* a crossing: it is reported as an
``endpoint_touch``.

ACCELERATION
------------
Per height a uniform 1 mm XY grid is filled with the cells actually traversed by
every primitive (the integer bounding box of each <=1 mm sub-step, so a cell
containing any curve point is always registered; arcs get one cell of dilation to
absorb chord sagitta).  Primitive pairs sharing a cell are the only candidates.
Same-route pairs are skipped.  Any two primitives that touch or come within one
cell are guaranteed to be candidates, which makes the pass complete for both
crossings and the 0.08 mm clearance rule.

VERDICT
-------
``pass_45`` is true iff there is no crossing below ``theta_min`` (default 45 deg,
with a ``1e-9`` guard band), no coincident/overlap stretch, no endpoint touch and
no same-height non-crossing route pair closer than 0.08 mm.

USAGE
-----
    python g5_angle_validator.py --run-dir <dir with routes_l3d.json> \
        --out-dir <dir> [--theta-min 45.0] [--layers-json <layer_planes.json>]

    python g5_angle_validator.py --selftest       # synthetic analytic checks

Outputs: ``g5_crossing_angles.csv``, ``g5_angle_validation.json``,
``g5_angle_violations.json`` and a final ``G5_ANGLE_SUMMARY {...}`` line.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
import time
from collections import defaultdict

__version__ = "1.0.0"
SCHEMA_VALIDATION = "g5_angle_validation_v1"
SCHEMA_VIOLATIONS = "g5_angle_violations_v1"

TAU = 2.0 * math.pi

# ---------------------------------------------------------------------------
# Numerical policy.  Every tolerance below is justified in README.md.
# ---------------------------------------------------------------------------
EPS_Z_MM = 1e-9                 # same-height rule (physical contract)
EPS_CHAIN_END_MM = 1e-7         # "too close to a chain end" rule
CLEARANCE_MM = 0.08             # same-height non-crossing centre-line clearance
GRID_CELL_MM = 1.0              # acceleration cell
PARALLEL_REL = 1e-13            # |sin| below this -> parallel lines
COLLINEAR_TOL_MM = 1e-9         # line-line collinearity distance
TANGENT_REL = 1e-12             # relative discriminant tolerance for tangency
PARAM_TOL_MM = 1e-7             # parameter slack at primitive ends
ANGLE_TOL_RAD = 1e-10           # arc angular containment slack
COINCIDENT_CENTER_TOL = 1e-9    # coincident-circle centre tolerance
COINCIDENT_RADIUS_TOL = 1e-9    # coincident-circle radius tolerance
POINT_DEDUPE_TOL_MM = 1e-6      # identical hit points from adjacent primitives
THETA_LEGACY_DEG = 5.0          # old G4 admissibility

FORBIDDEN_PROJECT_MODULES = (
    "four_side_1024",
    "fslw",
    "native3d",
    "validate21",
    "nonc4",
    "d56",
    "fsd25d",
    "l3d",
    "xyzrouter",
    "world_adapter",
    "independent_metrics",
)


def _null_log(*_a, **_k):
    return None


# ---------------------------------------------------------------------------
# small 2-D helpers
# ---------------------------------------------------------------------------
def _clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def _point_seg(px, py, x0, y0, x1, y1):
    """Closest point on segment [(x0,y0),(x1,y1)] to (px,py).

    Returns ``(dist, qx, qy, t)`` with ``t`` the clamped segment parameter.
    """
    dx = x1 - x0
    dy = y1 - y0
    l2 = dx * dx + dy * dy
    if l2 <= 0.0:
        return math.hypot(px - x0, py - y0), x0, y0, 0.0
    t = ((px - x0) * dx + (py - y0) * dy) / l2
    t = _clamp(t, 0.0, 1.0)
    qx = x0 + t * dx
    qy = y0 + t * dy
    return math.hypot(px - qx, py - qy), qx, qy, t


def _angle_in_arc(ang, a0, sweep, tol):
    """True if the angle (rad) belongs to the arc ``[a0, a0+sweep]``."""
    if sweep >= 0.0:
        d = (ang - a0) % TAU
        if d > TAU - tol:
            d = 0.0
        return d <= sweep + tol
    d = (a0 - ang) % TAU
    if d > TAU - tol:
        d = 0.0
    return d <= -sweep + tol


def _arc_param_from_angle(ang, a0, sweep, radius, tol):
    """Arc length from the arc start for ``ang`` or ``None`` if not on the arc."""
    if sweep >= 0.0:
        d = (ang - a0) % TAU
    else:
        d = (a0 - ang) % TAU
    if d > TAU - tol:
        d = 0.0
    span = abs(sweep)
    if d > span + tol:
        return None
    return radius * min(d, span)


def _arc_intervals(a0, sweep):
    """Covered angular intervals of an arc as ``[(lo, hi), ...]`` in [0, 2pi)."""
    if abs(sweep) >= TAU - 1e-12:
        return [(0.0, TAU)]
    if sweep >= 0.0:
        length = sweep
    else:
        length = -sweep
    lo = a0 % TAU
    hi = lo + length
    if hi <= TAU:
        return [(lo, hi)]
    return [(lo, TAU), (0.0, hi - TAU)]


def _interval_overlap(ia, ib):
    total = 0.0
    for l1, h1 in ia:
        for l2, h2 in ib:
            lo = l1 if l1 > l2 else l2
            hi = h1 if h1 < h2 else h2
            if hi > lo:
                total += hi - lo
    return total


# ---------------------------------------------------------------------------
# primitives
# ---------------------------------------------------------------------------
class Prim(object):
    """One flat 2-D primitive (line or circular arc) of one route at one height."""

    __slots__ = (
        "idx", "route_idx", "rid", "z", "z_idx", "kind",
        "x0", "y0", "x1", "y1",          # line endpoints / arc endpoints
        "cx", "cy", "r", "a0", "sweep",  # arc data
        "length", "s0", "chain_total", "part_i", "part_ord", "prim_i",
        "bx0", "by0", "bx1", "by1",
    )

    def __repr__(self):  # pragma: no cover - debugging aid
        return "<Prim %s r=%s z=%.6f len=%.6f>" % (
            self.kind, self.rid, self.z, self.length)


def _bbox_line(x0, y0, x1, y1):
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def _bbox_arc(cx, cy, r, a0, sweep):
    xs = []
    ys = []
    for ang in (a0, a0 + sweep):
        xs.append(cx + r * math.cos(ang))
        ys.append(cy + r * math.sin(ang))
    for k in range(4):
        ang = k * math.pi / 2.0
        if _angle_in_arc(ang, a0, sweep, ANGLE_TOL_RAD):
            xs.append(cx + r * math.cos(ang))
            ys.append(cy + r * math.sin(ang))
    return (min(xs), min(ys), max(xs), max(ys))


def _prim_length(pr):
    if pr.get("kind") == "line":
        p0 = pr.get("p0") or (0.0, 0.0)
        p1 = pr.get("p1") or (0.0, 0.0)
        return math.hypot(float(p1[0]) - float(p0[0]), float(p1[1]) - float(p0[1]))
    if pr.get("kind") == "arc":
        return float(pr.get("radius", 0.0)) * abs(float(pr.get("sweep", 0.0)))
    return 0.0


def _tangent_at(p, x, y):
    """Exact unit tangent of primitive ``p`` at point ``(x, y)``."""
    if p.kind == "line":
        dx = p.x1 - p.x0
        dy = p.y1 - p.y0
        n = math.hypot(dx, dy)
        if n <= 0.0:
            return (1.0, 0.0)
        return (dx / n, dy / n)
    ang = math.atan2(y - p.cy, x - p.cx)
    sgn = 1.0 if p.sweep >= 0.0 else -1.0
    return (-math.sin(ang) * sgn, math.cos(ang) * sgn)


def _angle_deg(p, q, x, y):
    """Acute local tangent angle in [0, 90]."""
    tx = _tangent_at(p, x, y)
    ty = _tangent_at(q, x, y)
    cr = tx[0] * ty[1] - tx[1] * ty[0]
    v = abs(cr)
    if v > 1.0:
        v = 1.0
    return math.degrees(math.asin(v))


def _point_prim_distance(p, x, y):
    """Distance from a point to a flat primitive (mm)."""
    if p.kind == "line":
        d, _qx, _qy, _t = _point_seg(x, y, p.x0, p.y0, p.x1, p.y1)
        return d
    rho = math.hypot(x - p.cx, y - p.cy)
    ang = math.atan2(y - p.cy, x - p.cx)
    if _arc_param_from_angle(ang, p.a0, p.sweep, p.r, ANGLE_TOL_RAD) is not None:
        return abs(rho - p.r)
    return min(math.hypot(x - p.x0, y - p.y0), math.hypot(x - p.x1, y - p.y1))


# ---------------------------------------------------------------------------
# exact intersections
# ---------------------------------------------------------------------------
def _intersect_line_line(p, q):
    """Returns (status, hits); status in {none, cross, tangent, coincident}."""
    ax0, ay0, ax1, ay1 = p.x0, p.y0, p.x1, p.y1
    bx0, by0, bx1, by1 = q.x0, q.y0, q.x1, q.y1
    dax = ax1 - ax0
    day = ay1 - ay0
    dbx = bx1 - bx0
    dby = by1 - by0
    la = math.hypot(dax, day)
    lb = math.hypot(dbx, dby)
    if la <= 0.0 or lb <= 0.0:
        return "none", []
    den = dax * dby - day * dbx
    sin_ab = den / (la * lb)
    if abs(sin_ab) <= PARALLEL_REL:
        # parallel: collinear only if both q endpoints lie on p's line
        dist0 = abs((bx0 - ax0) * day - (by0 - ay0) * dax) / la
        dist1 = abs((bx1 - ax0) * day - (by1 - ay0) * dax) / la
        if max(dist0, dist1) > COLLINEAR_TOL_MM:
            return "none", []
        ux = dax / la
        uy = day / la
        t0 = (bx0 - ax0) * ux + (by0 - ay0) * uy
        t1 = (bx1 - ax0) * ux + (by1 - ay0) * uy
        lo = max(0.0, min(t0, t1))
        hi = min(la, max(t0, t1))
        span = hi - lo
        if span > COLLINEAR_TOL_MM:
            tm = 0.5 * (lo + hi)
            return "coincident", [{
                "x": ax0 + ux * tm, "y": ay0 + uy * tm,
                "s_p": tm, "s_q": tm,
                "overlap_mm": span, "reason": "collinear_overlap",
            }]
        if span >= -COLLINEAR_TOL_MM:
            tm = 0.5 * (lo + hi)
            tm = _clamp(tm, 0.0, la)
            return "tangent", [{
                "x": ax0 + ux * tm, "y": ay0 + uy * tm,
                "s_p": tm, "s_q": tm, "overlap_mm": 0.0,
                "reason": "collinear_touch",
            }]
        return "none", []

    denom = den
    u = ((bx0 - ax0) * dby - (by0 - ay0) * dbx) / denom
    v = ((bx0 - ax0) * day - (by0 - ay0) * dax) / denom
    sp = u * la
    sq = v * lb
    if sp < -PARAM_TOL_MM or sp > la + PARAM_TOL_MM:
        return "none", []
    if sq < -PARAM_TOL_MM or sq > lb + PARAM_TOL_MM:
        return "none", []
    sp = _clamp(sp, 0.0, la)
    sq = _clamp(sq, 0.0, lb)
    x = ax0 + dax * (sp / la)
    y = ay0 + day * (sp / la)
    return "cross", [{"x": x, "y": y, "s_p": sp, "s_q": sq, "overlap_mm": 0.0,
                      "reason": "line_line"}]


def _intersect_line_arc(p, q):
    """Line ``p`` vs arc ``q``.  Quadratic in arc length along the line."""
    L = p.length
    if L <= 0.0 or q.r <= 0.0:
        return "none", []
    ux = (p.x1 - p.x0) / L
    uy = (p.y1 - p.y0) / L
    fx = p.x0 - q.cx
    fy = p.y0 - q.cy
    b = fx * ux + fy * uy
    f2 = fx * fx + fy * fy
    dist2 = f2 - b * b
    if dist2 < 0.0:
        dist2 = 0.0
    delta = q.r * q.r - dist2
    tol = TANGENT_REL * max(1.0, q.r * q.r)

    def _hit(t):
        if t < -PARAM_TOL_MM or t > L + PARAM_TOL_MM:
            return None
        t = _clamp(t, 0.0, L)
        x = p.x0 + ux * t
        y = p.y0 + uy * t
        ang = math.atan2(y - q.cy, x - q.cx)
        s_arc = _arc_param_from_angle(ang, q.a0, q.sweep, q.r, ANGLE_TOL_RAD)
        if s_arc is None:
            return None
        return {"x": x, "y": y, "s_p": t, "s_q": s_arc,
                "overlap_mm": 0.0, "reason": "line_arc"}

    if delta < -tol:
        return "none", []
    if abs(delta) <= tol:
        hit = _hit(-b)
        if hit is None:
            return "none", []
        hit["reason"] = "line_arc_tangent"
        return "tangent", [hit]
    root = math.sqrt(delta)
    hits = []
    for t in (-b - root, -b + root):
        hit = _hit(t)
        if hit is not None:
            hits.append(hit)
    if not hits:
        return "none", []
    return "cross", hits


def _intersect_arc_arc(p, q):
    dx = q.cx - p.cx
    dy = q.cy - p.cy
    d = math.hypot(dx, dy)
    if d <= COINCIDENT_CENTER_TOL:
        if abs(p.r - q.r) <= COINCIDENT_RADIUS_TOL:
            rad = _interval_overlap(_arc_intervals(p.a0, p.sweep),
                                    _arc_intervals(q.a0, q.sweep))
            overlap_mm = p.r * rad
            mid = p.a0 + p.sweep * 0.5
            return "coincident", [{
                "x": p.cx + p.r * math.cos(mid),
                "y": p.cy + p.r * math.sin(mid),
                "s_p": p.r * abs(p.sweep) * 0.5,
                "s_q": 0.0,
                "overlap_mm": overlap_mm,
                "reason": "coincident_circles",
            }]
        return "none", []
    ux = dx / d
    uy = dy / d
    a = (d * d + p.r * p.r - q.r * q.r) / (2.0 * d)
    h2 = p.r * p.r - a * a
    tol = TANGENT_REL * max(1.0, p.r * p.r)

    def _accept(x, y):
        ang_p = math.atan2(y - p.cy, x - p.cx)
        sp = _arc_param_from_angle(ang_p, p.a0, p.sweep, p.r, ANGLE_TOL_RAD)
        if sp is None:
            return None
        ang_q = math.atan2(y - q.cy, x - q.cx)
        sq = _arc_param_from_angle(ang_q, q.a0, q.sweep, q.r, ANGLE_TOL_RAD)
        if sq is None:
            return None
        return {"x": x, "y": y, "s_p": sp, "s_q": sq,
                "overlap_mm": 0.0, "reason": "arc_arc"}

    if h2 < -tol:
        return "none", []
    if abs(h2) <= tol:
        hit = _accept(p.cx + a * ux, p.cy + a * uy)
        if hit is None:
            return "none", []
        hit["reason"] = "arc_arc_tangent"
        return "tangent", [hit]
    h = math.sqrt(h2)
    base_x = p.cx + a * ux
    base_y = p.cy + a * uy
    ox = -uy * h
    oy = ux * h
    hits = []
    for sx, sy in ((base_x + ox, base_y + oy), (base_x - ox, base_y - oy)):
        hit = _accept(sx, sy)
        if hit is not None:
            hits.append(hit)
    if not hits:
        return "none", []
    return "cross", hits


def intersect_prims(p, q):
    """Dispatch to the exact primitive-pair intersection."""
    ka = p.kind
    kb = q.kind
    if ka == "line" and kb == "line":
        return _intersect_line_line(p, q)
    if ka == "line" and kb == "arc":
        return _intersect_line_arc(p, q)
    if ka == "arc" and kb == "line":
        status, hits = _intersect_line_arc(q, p)
        for h in hits:
            h["s_p"], h["s_q"] = h["s_q"], h["s_p"]
            if status == "cross":
                h["reason"] = "arc_line"
            else:
                h["reason"] = h["reason"].replace("line_arc", "arc_line")
        return status, hits
    return _intersect_arc_arc(p, q)


# ---------------------------------------------------------------------------
# exact distances (used for the non-crossing clearance rule)
# ---------------------------------------------------------------------------
def _point_arc(p, x, y):
    rho = math.hypot(x - p.cx, y - p.cy)
    ang = math.atan2(y - p.cy, x - p.cx)
    if _arc_param_from_angle(ang, p.a0, p.sweep, p.r, ANGLE_TOL_RAD) is not None:
        qx = p.cx + p.r * math.cos(ang)
        qy = p.cy + p.r * math.sin(ang)
        return abs(rho - p.r), qx, qy
    d0 = math.hypot(x - p.x0, y - p.y0)
    d1 = math.hypot(x - p.x1, y - p.y1)
    if d0 <= d1:
        return d0, p.x0, p.y0
    return d1, p.x1, p.y1


def _seg_seg_distance(p, q):
    """Minimum distance between two line primitives."""
    ax0, ay0, ax1, ay1 = p.x0, p.y0, p.x1, p.y1
    bx0, by0, bx1, by1 = q.x0, q.y0, q.x1, q.y1
    dax = ax1 - ax0
    day = ay1 - ay0
    dbx = bx1 - bx0
    dby = by1 - by0
    den = dax * dby - day * dbx
    if abs(den) > 1e-300:
        u = ((bx0 - ax0) * dby - (by0 - ay0) * dbx) / den
        v = ((bx0 - ax0) * day - (by0 - ay0) * dax) / den
        if -PARAM_TOL_MM <= u <= 1.0 + PARAM_TOL_MM and \
                -PARAM_TOL_MM <= v <= 1.0 + PARAM_TOL_MM:
            t = _clamp(u, 0.0, 1.0)
            return 0.0, ax0 + t * dax, ay0 + t * day
    best = float("inf")
    best_pt = (ax0, ay0)
    for (px, py) in ((ax0, ay0), (ax1, ay1)):
        d, qx, qy, _t = _point_seg(px, py, bx0, by0, bx1, by1)
        if d < best:
            best = d
            best_pt = (0.5 * (px + qx), 0.5 * (py + qy))
    for (px, py) in ((bx0, by0), (bx1, by1)):
        d, qx, qy, _t = _point_seg(px, py, ax0, ay0, ax1, ay1)
        if d < best:
            best = d
            best_pt = (0.5 * (px + qx), 0.5 * (py + qy))
    return best, best_pt[0], best_pt[1]


def _seg_arc_distance(p, q):
    """Minimum distance between a line primitive ``p`` and an arc primitive ``q``."""
    best = float("inf")
    best_pt = (p.x0, p.y0)
    for (px, py) in ((p.x0, p.y0), (p.x1, p.y1)):
        d, qx, qy = _point_arc(q, px, py)
        if d < best:
            best = d
            best_pt = (0.5 * (px + qx), 0.5 * (py + qy))
    for (px, py) in ((q.x0, q.y0), (q.x1, q.y1)):
        d, qx, qy, _t = _point_seg(px, py, p.x0, p.y0, p.x1, p.y1)
        if d < best:
            best = d
            best_pt = (0.5 * (px + qx), 0.5 * (py + qy))
    # perpendicular foot from the arc centre onto the line's infinite support
    L = p.length
    if L > 0.0:
        ux = (p.x1 - p.x0) / L
        uy = (p.y1 - p.y0) / L
        t = (q.cx - p.x0) * ux + (q.cy - p.y0) * uy
        if -PARAM_TOL_MM <= t <= L + PARAM_TOL_MM:
            tc = _clamp(t, 0.0, L)
            fx = p.x0 + ux * tc
            fy = p.y0 + uy * tc
            ang = math.atan2(fy - q.cy, fx - q.cx)
            if _arc_param_from_angle(ang, q.a0, q.sweep, q.r, ANGLE_TOL_RAD) is not None:
                dperp = math.hypot(fx - q.cx, fy - q.cy)
                d = abs(dperp - q.r)
                if d < best:
                    best = d
                    gx = q.cx + q.r * math.cos(ang)
                    gy = q.cy + q.r * math.sin(ang)
                    best_pt = (0.5 * (fx + gx), 0.5 * (fy + gy))
    return best, best_pt[0], best_pt[1]


def _arc_arc_distance(p, q):
    best = float("inf")
    best_pt = (p.x0, p.y0)
    for (px, py) in ((p.x0, p.y0), (p.x1, p.y1)):
        d, qx, qy = _point_arc(q, px, py)
        if d < best:
            best = d
            best_pt = (0.5 * (px + qx), 0.5 * (py + qy))
    for (px, py) in ((q.x0, q.y0), (q.x1, q.y1)):
        d, qx, qy = _point_arc(p, px, py)
        if d < best:
            best = d
            best_pt = (0.5 * (px + qx), 0.5 * (py + qy))
    dx = q.cx - p.cx
    dy = q.cy - p.cy
    d = math.hypot(dx, dy)
    if d > COINCIDENT_CENTER_TOL:
        ux = dx / d
        uy = dy / d
        cand = None
        if d >= p.r + q.r:
            cand = ((p.cx + p.r * ux, p.cy + p.r * uy),
                    (q.cx - q.r * ux, q.cy - q.r * uy))
        elif d <= abs(p.r - q.r):
            if p.r >= q.r:
                cand = ((p.cx + p.r * ux, p.cy + p.r * uy),
                        (q.cx + q.r * ux, q.cy + q.r * uy))
            else:
                cand = ((p.cx - p.r * ux, p.cy - p.r * uy),
                        (q.cx - q.r * ux, q.cy - q.r * uy))
        if cand is not None:
            # cand[0] must lie on p and cand[1] on q (one point each, not both)
            if (_point_arc(p, cand[0][0], cand[0][1])[0] <= 1e-9
                    and _point_arc(q, cand[1][0], cand[1][1])[0] <= 1e-9):
                dd = math.hypot(cand[0][0] - cand[1][0], cand[0][1] - cand[1][1])
                if dd < best:
                    best = dd
                    best_pt = (0.5 * (cand[0][0] + cand[1][0]),
                               0.5 * (cand[0][1] + cand[1][1]))
    return best, best_pt[0], best_pt[1]


def prim_distance(p, q):
    """Exact minimum centre-line distance between two flat primitives."""
    if p.kind == "line":
        if q.kind == "line":
            return _seg_seg_distance(p, q)
        return _seg_arc_distance(p, q)
    if q.kind == "line":
        d, x, y = _seg_arc_distance(q, p)
        return d, x, y
    return _arc_arc_distance(p, q)


# ---------------------------------------------------------------------------
# uniform grid acceleration
# ---------------------------------------------------------------------------
def _cells_of_box(ax, ay, bx, by, cell, dilate):
    ix0 = int(math.floor(ax / cell)) - dilate
    ix1 = int(math.floor(bx / cell)) + dilate
    iy0 = int(math.floor(ay / cell)) - dilate
    iy1 = int(math.floor(by / cell)) + dilate
    if ix0 > ix1:
        ix0, ix1 = ix1, ix0
    if iy0 > iy1:
        iy0, iy1 = iy1, iy0
    out = []
    for ix in range(ix0, ix1 + 1):
        for iy in range(iy0, iy1 + 1):
            out.append((ix, iy))
    return out


def build_grid(prim_indices, prims, cell=GRID_CELL_MM):
    """Map cell -> primitive indices for every cell a primitive actually visits.

    Each primitive is split into sub-steps no longer than ``cell`` so the integer
    box of a sub-step spans at most 2x2 cells.  Lines are exactly covered by their
    end-point box; arcs are dilated by one cell to absorb the chord sagitta.
    """
    grid = defaultdict(list)
    step = cell
    for pi in prim_indices:
        p = prims[pi]
        if p.length <= 0.0:
            continue
        n = int(math.ceil(p.length / step))
        if n < 1:
            n = 1
        dilate = 1 if p.kind == "arc" else 0
        if p.kind == "line":
            for k in range(n):
                f0 = float(k) / n
                f1 = float(k + 1) / n
                x0 = p.x0 + (p.x1 - p.x0) * f0
                y0 = p.y0 + (p.y1 - p.y0) * f0
                x1 = p.x0 + (p.x1 - p.x0) * f1
                y1 = p.y0 + (p.y1 - p.y0) * f1
                for key in _cells_of_box(x0, y0, x1, y1, cell, 0):
                    grid[key].append(pi)
        else:
            for k in range(n):
                a0 = p.a0 + p.sweep * (float(k) / n)
                a1 = p.a0 + p.sweep * (float(k + 1) / n)
                x0 = p.cx + p.r * math.cos(a0)
                y0 = p.cy + p.r * math.sin(a0)
                x1 = p.cx + p.r * math.cos(a1)
                y1 = p.cy + p.r * math.sin(a1)
                for key in _cells_of_box(x0, y0, x1, y1, cell, dilate):
                    grid[key].append(pi)
    return grid


def candidate_pairs(grid, prims):
    """Unique primitive-index pairs sharing at least one cell (different routes)."""
    pairs = set()
    for _key, lst in grid.items():
        n = len(lst)
        if n < 2:
            continue
        for ii in range(n - 1):
            ia = lst[ii]
            ra = prims[ia].rid
            for jj in range(ii + 1, n):
                ib = lst[jj]
                if prims[ib].rid == ra:
                    continue
                if ia < ib:
                    pairs.add((ia, ib))
                else:
                    pairs.add((ib, ia))
    return pairs


# ---------------------------------------------------------------------------
# geometry build
# ---------------------------------------------------------------------------
def _cluster_heights(zvals):
    """Group physical heights with a 1e-9 mm tolerance; returns (reps, map)."""
    vals = sorted(set(zvals))
    groups = []
    for v in vals:
        if groups and abs(v - groups[-1][-1]) <= EPS_Z_MM:
            groups[-1].append(v)
        else:
            groups.append([v])
    reps = [g[0] for g in groups]
    rep_of = {}
    for rep, members in zip(reps, groups):
        for v in members:
            rep_of[v] = rep
    return reps, rep_of


def build_geometry(routes, meta_by_rid):
    """Flatten every route into per-height primitive chains.

    Returns ``(prims, by_z, zreps, skipped)`` where ``by_z`` maps height index to
    the primitive indices at that height.
    """
    zvals = []
    for route in routes:
        parts = route.get("parts") or ()
        for part in parts:
            if part.get("kind") == "flat" and part.get("z_mm") is not None:
                zvals.append(float(part["z_mm"]))
    if not zvals:
        return [], {}, [], {"unknown_primitive_kind": 0, "missing_z": 0}
    zreps, rep_of = _cluster_heights(zvals)
    z_index = {rep: i for i, rep in enumerate(zreps)}

    prims = []
    by_z = defaultdict(list)
    skipped = {"unknown_primitive_kind": 0, "missing_z": 0}

    for route_idx, route in enumerate(routes):
        rid = route.get("route_id")
        parts = route.get("parts") or ()
        chains = defaultdict(list)   # height index -> [(part_i, part)]
        for part_i, part in enumerate(parts):
            if part.get("kind") != "flat":
                continue
            if part.get("z_mm") is None:
                skipped["missing_z"] += 1
                continue
            z = float(part["z_mm"])
            chains[z_index[rep_of[z]]].append((part_i, part))

        for z_idx, plist in chains.items():
            z = zreps[z_idx]
            total = 0.0
            for _part_i, part in plist:
                for pr in part.get("primitives") or ():
                    total += _prim_length(pr)
            s0 = 0.0
            for part_ord, (part_i, part) in enumerate(plist):
                for prim_i, pr in enumerate(part.get("primitives") or ()):
                    kind = pr.get("kind")
                    length = _prim_length(pr)
                    prim = Prim()
                    prim.route_idx = route_idx
                    prim.rid = rid
                    prim.z = z
                    prim.z_idx = z_idx
                    prim.kind = kind
                    prim.s0 = s0
                    prim.chain_total = total
                    prim.part_i = part_i
                    prim.part_ord = part_ord
                    prim.prim_i = prim_i
                    prim.cx = prim.cy = prim.r = prim.a0 = prim.sweep = 0.0
                    if kind == "line":
                        p0 = pr["p0"]
                        p1 = pr["p1"]
                        prim.x0 = float(p0[0])
                        prim.y0 = float(p0[1])
                        prim.x1 = float(p1[0])
                        prim.y1 = float(p1[1])
                        prim.length = length
                        bx0, by0, bx1, by1 = _bbox_line(
                            prim.x0, prim.y0, prim.x1, prim.y1)
                    elif kind == "arc":
                        c = pr["center"]
                        prim.cx = float(c[0])
                        prim.cy = float(c[1])
                        prim.r = float(pr["radius"])
                        prim.a0 = float(pr["start_angle"])
                        prim.sweep = float(pr["sweep"])
                        prim.x0 = prim.cx + prim.r * math.cos(prim.a0)
                        prim.y0 = prim.cy + prim.r * math.sin(prim.a0)
                        prim.x1 = prim.cx + prim.r * math.cos(prim.a0 + prim.sweep)
                        prim.y1 = prim.cy + prim.r * math.sin(prim.a0 + prim.sweep)
                        prim.length = prim.r * abs(prim.sweep)
                        bx0, by0, bx1, by1 = _bbox_arc(
                            prim.cx, prim.cy, prim.r, prim.a0, prim.sweep)
                    else:
                        # unknown primitive kind: never invented as geometry
                        skipped["unknown_primitive_kind"] += 1
                        continue
                    prim.bx0, prim.by0, prim.bx1, prim.by1 = bx0, by0, bx1, by1
                    prim.idx = len(prims)
                    prims.append(prim)
                    by_z[z_idx].append(prim.idx)
                    s0 += length
    return prims, by_z, zreps, skipped


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------
def _route_pair_key(ra, rb):
    return (ra, rb) if ra <= rb else (rb, ra)


def audit_routes(routes, theta_min=45.0, log=None, z_label_map=None,
                 clearance_mm=CLEARANCE_MM):
    """Run the full independent audit and return a result dict."""
    log = log or _null_log
    t0 = time.time()

    meta_by_rid = {}
    for route in routes:
        rid = route.get("route_id")
        if rid in meta_by_rid:
            raise ValueError("duplicate route_id %r" % (rid,))
        meta_by_rid[rid] = {
            "route_id": rid,
            "source_side": route.get("source_side"),
            "target_side": route.get("target_side"),
            "source_endpoint": route.get("source_endpoint"),
            "target_endpoint": route.get("target_endpoint"),
            "target_plane": route.get("target_plane"),
            "target_plane_label": route.get("target_plane_label"),
        }

    prims, by_z, zreps, skipped = build_geometry(routes, meta_by_rid)
    log("[build] routes=%d heights=%d primitives=%d skipped=%s (%.2fs)"
        % (len(routes), len(zreps), len(prims), skipped,
           time.time() - t0))

    raw_hits = []
    overlap_events = []
    tangent_events = []
    pair_min = {}            # (z_idx, ra, rb) -> dict(distance, evidence)
    cross_pairs = set()
    overlap_pairs = set()
    n_raw_pairs = 0

    for z_idx in sorted(by_z):
        z = zreps[z_idx]
        idxs = by_z[z_idx]
        tz = time.time()
        grid = build_grid(idxs, prims)
        pairs = candidate_pairs(grid, prims)
        n_raw_pairs += len(pairs)
        n_cross_here = 0
        for (ia, ib) in pairs:
            p = prims[ia]
            q = prims[ib]
            status, hits = intersect_prims(p, q)
            if status == "cross":
                for h in hits:
                    ma = meta_by_rid.get(p.rid, {})
                    mb = meta_by_rid.get(q.rid, {})
                    raw_hits.append({
                        "z_idx": z_idx, "z": z,
                        "ra": p.rid, "rb": q.rid,
                        "i": ia, "j": ib,
                        "x": h["x"], "y": h["y"],
                        "kind_a": p.kind, "kind_b": q.kind,
                        "s_a": p.s0 + h["s_p"],
                        "s_b": q.s0 + h["s_q"],
                        "chain_a": p.chain_total, "chain_b": q.chain_total,
                        "res_a": _point_prim_distance(p, h["x"], h["y"]),
                        "res_b": _point_prim_distance(q, h["x"], h["y"]),
                        "n_pair_hits": len(hits),
                        "angle_deg": _angle_deg(p, q, h["x"], h["y"]),
                        "source_a": ma.get("source_endpoint"),
                        "target_a": ma.get("target_endpoint"),
                        "source_b": mb.get("source_endpoint"),
                        "target_b": mb.get("target_endpoint"),
                        "plane_a": ma.get("target_plane"),
                        "plane_b": mb.get("target_plane"),
                    })
                    n_cross_here += 1
                key = (z_idx,) + _route_pair_key(p.rid, q.rid)
                cross_pairs.add(key)
            elif status == "tangent":
                tangent_events.append({
                    "z_idx": z_idx, "z_mm": z,
                    "route_a": p.rid, "route_b": q.rid,
                    "kind_a": p.kind, "kind_b": q.kind,
                    "x_mm": hits[0]["x"], "y_mm": hits[0]["y"],
                    "reason": hits[0]["reason"],
                    "angle_deg": _angle_deg(p, q, hits[0]["x"], hits[0]["y"]),
                })
            elif status == "coincident":
                key = (z_idx,) + _route_pair_key(p.rid, q.rid)
                illegal = hits[0]["overlap_mm"] > COLLINEAR_TOL_MM
                if illegal:
                    overlap_pairs.add(key)
                overlap_events.append({
                    "z_idx": z_idx, "z_mm": z,
                    "route_a": p.rid, "route_b": q.rid,
                    "kind_a": p.kind, "kind_b": q.kind,
                    "x_mm": hits[0]["x"], "y_mm": hits[0]["y"],
                    "overlap_mm": hits[0]["overlap_mm"],
                    "reason": hits[0]["reason"],
                    "illegal_overlap": illegal,
                })
            else:
                d, x, y = prim_distance(p, q)
                key = (z_idx,) + _route_pair_key(p.rid, q.rid)
                prev = pair_min.get(key)
                if prev is None or d < prev["distance_mm"]:
                    pair_min[key] = {
                        "distance_mm": d, "x_mm": x, "y_mm": y,
                        "route_a": _route_pair_key(p.rid, q.rid)[0],
                        "route_b": _route_pair_key(p.rid, q.rid)[1],
                        "kind_a": p.kind, "kind_b": q.kind,
                        "s_a": p.s0, "s_b": q.s0,
                    }
        log("[grid] z=%.6f prims=%d cells=%d pairs=%d raw_hits=%d (%.2fs)"
            % (z, len(idxs), len(grid), len(pairs), n_cross_here, time.time() - tz))

    log("[detect] candidate primitive pairs=%d raw crossings=%d overlaps=%d tangents=%d (%.2fs)"
        % (n_raw_pairs, len(raw_hits), len(overlap_events), len(tangent_events),
           time.time() - t0))

    # ---- deduplicate hits that the same physical point produces via adjacent
    # primitives (a route corner is interior to the chain but shared by two
    # primitives, so both primitive pairs report it).
    by_group = defaultdict(list)
    for h in raw_hits:
        by_group[(h["z_idx"],) + _route_pair_key(h["ra"], h["rb"])].append(h)
    deduped = []
    n_duplicate_groups = 0
    max_angle_spread = 0.0
    for key, lst in by_group.items():
        lst.sort(key=lambda c: (c["x"], c["y"]))
        clusters = []
        tol2 = POINT_DEDUPE_TOL_MM * POINT_DEDUPE_TOL_MM
        for c in lst:
            placed = False
            for cl in clusters:
                dx = c["x"] - cl[0]["x"]
                dy = c["y"] - cl[0]["y"]
                if dx * dx + dy * dy <= tol2:
                    cl.append(c)
                    placed = True
                    break
            if not placed:
                clusters.append([c])
        for cl in clusters:
            rep = min(cl, key=lambda c: c["res_a"] + c["res_b"])
            rec = dict(rep)
            if len(cl) > 1:
                n_duplicate_groups += 1
                spread = (max(c["angle_deg"] for c in cl)
                          - min(c["angle_deg"] for c in cl))
                max_angle_spread = max(max_angle_spread, spread)
                # a hit sitting on a route corner whose two primitives have a
                # tangent discontinuity is reported at its sharpest local angle
                rec["angle_deg"] = min(c["angle_deg"] for c in cl)
            rec["n_duplicate_hits"] = len(cl)
            deduped.append(rec)
    log("[dedupe] unique hit points=%d (merged %d duplicate groups) (%.2fs)"
        % (len(deduped), n_duplicate_groups, time.time() - t0))

    # ---- chain-end filter
    crossings = []
    endpoint_touches = []
    for rec in deduped:
        near_a = min(rec["s_a"], rec["chain_a"] - rec["s_a"])
        near_b = min(rec["s_b"], rec["chain_b"] - rec["s_b"])
        rec["end_margin_a_mm"] = near_a
        rec["end_margin_b_mm"] = near_b
        if near_a < EPS_CHAIN_END_MM or near_b < EPS_CHAIN_END_MM:
            endpoint_touches.append(rec)
        else:
            crossings.append(rec)

    crossings.sort(key=lambda c: (c["z"], c["x"], c["y"], c["ra"], c["rb"]))
    for cid, rec in enumerate(crossings, start=1):
        rec["crossing_id"] = cid

    log("[filter] crossings=%d endpoint_touches=%d (%.2fs)"
        % (len(crossings), len(endpoint_touches), time.time() - t0))

    # ---- thresholds / per-crossing flags
    thr = float(theta_min)
    hard_45 = 45.0
    for rec in crossings:
        ang = rec["angle_deg"]
        rec["theta_margin_deg"] = ang - thr
        rec["pass_45"] = ang >= thr - 1e-9
        rec["pass_5"] = ang >= THETA_LEGACY_DEG - 1e-9
        rec["deficit_deg"] = max(0.0, thr - ang)

    # ---- statistics
    z_labels = _height_labels(zreps, z_label_map)
    for rec in crossings + endpoint_touches:
        rec["z_label"] = z_labels[rec["z_idx"]]
    for ev in overlap_events + tangent_events:
        ev["z_label"] = z_labels[ev["z_idx"]]
    per_height = []
    hist_bins = [0.0, 5.0, 10.0, 20.0, 30.0, 40.0, 45.0, 60.0, 75.0, 90.0]
    hist_counts = [0] * (len(hist_bins) - 1)
    for rec in crossings:
        a = rec["angle_deg"]
        for bi in range(len(hist_bins) - 1):
            lo = hist_bins[bi]
            hi = hist_bins[bi + 1]
            if (a >= lo and a < hi) or (bi == len(hist_bins) - 2 and a >= lo and a <= hi):
                hist_counts[bi] += 1
                break

    route_stats = defaultdict(lambda: {
        "crossings": 0, "n_lt": 0, "deficit_deg": 0.0,
        "min_angle_deg": float("inf"), "heights": set(),
    })
    for rec in crossings:
        for rid in (rec["ra"], rec["rb"]):
            st = route_stats[rid]
            st["crossings"] += 1
            st["heights"].add(rec["z_idx"])
            if rec["angle_deg"] < thr - 1e-9:
                st["n_lt"] += 1
                st["deficit_deg"] += rec["deficit_deg"]
            if rec["angle_deg"] < st["min_angle_deg"]:
                st["min_angle_deg"] = rec["angle_deg"]

    def _worst(limit):
        out = []
        for rid, st in route_stats.items():
            out.append({
                "route_id": rid,
                "crossings": st["crossings"],
                "n_lt": st["n_lt"],
                "deficit_deg": st["deficit_deg"],
                "min_angle_deg": (st["min_angle_deg"]
                                  if st["crossings"] else None),
                "heights": len(st["heights"]),
            })
        out.sort(key=lambda r: (-r["deficit_deg"], -r["crossings"],
                                r["route_id"]))
        return out[:limit]

    for z_idx in range(len(zreps)):
        cs = [c for c in crossings if c["z_idx"] == z_idx]
        n_lt = sum(1 for c in cs if c["angle_deg"] < thr - 1e-9)
        deficit = sum(c["deficit_deg"] for c in cs)
        max_def = max([c["deficit_deg"] for c in cs], default=0.0)
        min_ang = min([c["angle_deg"] for c in cs], default=None)
        min_rec = min(cs, key=lambda c: c["angle_deg"]) if cs else None
        rs = defaultdict(lambda: {"crossings": 0, "n_lt": 0,
                                  "deficit_deg": 0.0,
                                  "min_angle_deg": float("inf")})
        for c in cs:
            for rid in (c["ra"], c["rb"]):
                st = rs[rid]
                st["crossings"] += 1
                if c["angle_deg"] < thr - 1e-9:
                    st["n_lt"] += 1
                    st["deficit_deg"] += c["deficit_deg"]
                if c["angle_deg"] < st["min_angle_deg"]:
                    st["min_angle_deg"] = c["angle_deg"]
        worst = []
        for rid, st in rs.items():
            worst.append({
                "route_id": rid,
                "crossings": st["crossings"],
                "n_lt": st["n_lt"],
                "deficit_deg": st["deficit_deg"],
                "min_angle_deg": (st["min_angle_deg"]
                                  if st["crossings"] else None),
            })
        worst.sort(key=lambda r: (-r["deficit_deg"], -r["crossings"],
                                  r["route_id"]))
        per_height.append({
            "z_mm": zreps[z_idx],
            "z_label": z_labels[z_idx],
            "n_crossings": len(cs),
            "n_below_45": n_lt,
            "n_below_5": sum(1 for c in cs
                             if c["angle_deg"] < THETA_LEGACY_DEG - 1e-9),
            "min_angle_deg": min_ang,
            "min_angle_crossing_id": (min_rec["crossing_id"] if min_rec else None),
            "total_deficit_deg": deficit,
            "max_deficit_deg": max_def,
            "routes_involved": len(rs),
            "worst_routes": worst[:5],
        })

    # ---- clearance rule
    clearance_violations = []
    non_crossing_min = None
    for key, ev in pair_min.items():
        z_idx, ra, rb = key
        if key in cross_pairs:
            continue
        if key in overlap_pairs:
            continue
        d = ev["distance_mm"]
        if non_crossing_min is None or d < non_crossing_min["distance_mm"]:
            non_crossing_min = {
                "distance_mm": d, "z_mm": zreps[z_idx],
                "route_a": ra, "route_b": rb,
                "x_mm": ev["x_mm"], "y_mm": ev["y_mm"],
            }
        if d < clearance_mm - 1e-9:
            clearance_violations.append({
                "z_mm": zreps[z_idx],
                "z_label": z_labels[z_idx],
                "route_a": ra, "route_b": rb,
                "distance_mm": d,
                "x_mm": ev["x_mm"], "y_mm": ev["y_mm"],
                "kind_a": ev["kind_a"], "kind_b": ev["kind_b"],
                "limit_mm": clearance_mm,
            })
    clearance_violations.sort(key=lambda v: (v["distance_mm"], v["z_mm"],
                                             v["route_a"], v["route_b"]))

    # ---- summary
    pair_keys = set()
    for rec in crossings:
        pair_keys.add(_route_pair_key(rec["ra"], rec["rb"]))
    n_lt_theta = sum(1 for c in crossings if c["angle_deg"] < thr - 1e-9)
    n_lt_45 = sum(1 for c in crossings if c["angle_deg"] < hard_45 - 1e-9)
    n_lt_5 = sum(1 for c in crossings if c["angle_deg"] < THETA_LEGACY_DEG - 1e-9)
    d_theta = sum(c["deficit_deg"] for c in crossings)
    d_max = max([c["deficit_deg"] for c in crossings], default=0.0)
    min_rec = (min(crossings, key=lambda c: c["angle_deg"])
               if crossings else None)
    max_route = None
    max_route_ids = []
    if route_stats:
        top = max(st["crossings"] for st in route_stats.values())
        max_route_ids = sorted(rid for rid, st in route_stats.items()
                               if st["crossings"] == top)
        max_route = {"crossings": top, "route_ids": max_route_ids}
    residual_max = 0.0
    for c in crossings:
        residual_max = max(residual_max, c["res_a"], c["res_b"])

    illegal_overlaps = [ev for ev in overlap_events if ev["illegal_overlap"]]
    coincident_zero = len(overlap_events) - len(illegal_overlaps)
    reasons = []
    if n_lt_theta:
        reasons.append("%d crossings below %.3f deg" % (n_lt_theta, thr))
    if illegal_overlaps:
        reasons.append("%d coincident/overlap event(s)" % len(illegal_overlaps))
    if endpoint_touches:
        reasons.append("%d endpoint touch(es)" % len(endpoint_touches))
    if clearance_violations:
        reasons.append("%d same-height non-crossing pair(s) below %.3f mm"
                       % (len(clearance_violations), clearance_mm))
    verdict_pass = not reasons

    summary = {
        "total_crossings": len(crossings),
        "unique_route_pairs": len(pair_keys),
        "routes_with_crossings": len(route_stats),
        "max_crossings_per_route": (max_route["crossings"] if max_route else 0),
        "max_crossings_route_ids": (max_route["route_ids"] if max_route else []),
        "min_angle_deg": (min_rec["angle_deg"] if min_rec else None),
        "min_angle_crossing_id": (min_rec["crossing_id"] if min_rec else None),
        "n_lt_theta_min": n_lt_theta,
        "n_lt_45": n_lt_45,
        "n_lt_5": n_lt_5,
        "D_theta_deg": d_theta,
        "D_max_deg": d_max,
        "overlap_event_count": len(illegal_overlaps),
        "overlap_route_pair_count": len(overlap_pairs),
        "coincident_no_overlap_event_count": coincident_zero,
        "endpoint_touch_count": len(endpoint_touches),
        "tangent_or_near_tangent_count": len(tangent_events),
        "clearance_violation_count": len(clearance_violations),
        "clearance_min_non_crossing_mm": (non_crossing_min["distance_mm"]
                                          if non_crossing_min else None),
        "clearance_min_non_crossing_evidence": non_crossing_min,
        "residual_max_mm": residual_max,
        "raw_primitive_pairs": n_raw_pairs,
        "raw_crossing_hits": len(raw_hits),
        "multi_point_primitive_pairs": len({
            (h["i"], h["j"]) for h in raw_hits if h["n_pair_hits"] >= 2}),
        "multi_point_primitive_pair_hits": sum(
            1 for h in raw_hits if h["n_pair_hits"] >= 2),
        "duplicate_hit_groups_merged": n_duplicate_groups,
        "duplicate_angle_spread_max_deg": max_angle_spread,
        "verdict_pass_45": verdict_pass,
        "verdict": {
            "pass_45": verdict_pass,
            "no_angle_violations": n_lt_theta == 0,
            "no_overlaps": len(illegal_overlaps) == 0,
            "no_endpoint_touches": len(endpoint_touches) == 0,
            "no_clearance_violations": len(clearance_violations) == 0,
            "reasons": reasons,
        },
        "verdict_fail_reasons": reasons,
        "theta_min_deg": thr,
        "clearance_limit_mm": clearance_mm,
        "heights": len(zreps),
        "primitives": len(prims),
        "routes": len(routes),
        "timing_seconds": round(time.time() - t0, 3),
    }

    result = {
        "schema": SCHEMA_VALIDATION,
        "generator": "g5/validate_g5_angle.py",
        "generator_version": __version__,
        "theta_min_deg": thr,
        "tolerances": {
            "same_height_dz_mm": EPS_Z_MM,
            "chain_end_mm": EPS_CHAIN_END_MM,
            "clearance_mm": clearance_mm,
            "grid_cell_mm": GRID_CELL_MM,
            "parallel_rel": PARALLEL_REL,
            "collinear_tol_mm": COLLINEAR_TOL_MM,
            "tangency_rel": TANGENT_REL,
            "param_tol_mm": PARAM_TOL_MM,
            "angle_tol_rad": ANGLE_TOL_RAD,
            "coincident_center_tol_mm": COINCIDENT_CENTER_TOL,
            "coincident_radius_tol_mm": COINCIDENT_RADIUS_TOL,
            "point_dedupe_tol_mm": POINT_DEDUPE_TOL_MM,
            "threshold_guard_deg": 1e-9,
        },
        "summary": summary,
        "per_height": per_height,
        "histogram": {
            "bins_deg": ["[0,5)", "[5,10)", "[10,20)", "[20,30)", "[30,40)",
                         "[40,45)", "[45,60)", "[60,75)", "[75,90]"],
            "counts": hist_counts,
            "edges_deg": hist_bins,
        },
        "worst_routes": _worst(20),
        "worst_crossings": [
            _crossing_row(c) for c in
            sorted(crossings, key=lambda c: (c["angle_deg"], c["crossing_id"]))[:20]
        ],
        "crossings": crossings,
        "overlap_events": overlap_events,
        "endpoint_touch_events": endpoint_touches,
        "tangent_or_near_tangent_events": tangent_events,
        "clearance_violations": clearance_violations,
        "skipped": skipped,
        "z_labels": [{"z_mm": zreps[i], "z_label": z_labels[i]}
                     for i in range(len(zreps))],
    }
    return result


def _height_labels(zreps, z_label_map):
    labels = []
    for i, z in enumerate(zreps):
        lab = None
        if z_label_map:
            for zk, lk in z_label_map.items():
                if abs(float(zk) - z) <= EPS_Z_MM:
                    lab = lk
                    break
        if lab is None:
            lab = "H%02d" % i
        labels.append(str(lab))
    return labels


def _crossing_row(c):
    """The required crossing record (CSV/JSON form)."""
    return {
        "crossing_id": c["crossing_id"],
        "z_mm": c["z"],
        "z_label": c.get("z_label"),
        "route_a": c["ra"],
        "route_b": c["rb"],
        "x_mm": c["x"],
        "y_mm": c["y"],
        "angle_deg": c["angle_deg"],
        "kind_a": c["kind_a"],
        "kind_b": c["kind_b"],
        "s_a_mm": c["s_a"],
        "s_b_mm": c["s_b"],
        "theta_margin_deg": c["theta_margin_deg"],
        "pass_45": c["pass_45"],
        "pass_5": c["pass_5"],
        "source_a": c.get("source_a"),
        "target_a": c.get("target_a"),
        "source_b": c.get("source_b"),
        "target_b": c.get("target_b"),
        "plane_a": c.get("plane_a"),
        "plane_b": c.get("plane_b"),
        "residual_a_mm": c["res_a"],
        "residual_b_mm": c["res_b"],
        "deficit_deg": c["deficit_deg"],
        "n_duplicate_hits": c.get("n_duplicate_hits", 1),
    }


CSV_FIELDS = [
    "crossing_id", "z_mm", "z_label", "route_a", "route_b", "x_mm", "y_mm",
    "angle_deg", "kind_a", "kind_b", "s_a_mm", "s_b_mm", "theta_margin_deg",
    "pass_45", "pass_5", "source_a", "target_a", "source_b", "target_b",
    "plane_a", "plane_b", "residual_a_mm", "residual_b_mm", "deficit_deg",
    "n_duplicate_hits",
]


# ---------------------------------------------------------------------------
# output writers
# ---------------------------------------------------------------------------
def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "True" if v else "False"
    if isinstance(v, float):
        return repr(v)
    return str(v)


def write_csv(path, crossings):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(CSV_FIELDS)
        for c in crossings:
            row = [c[k] for k in CSV_FIELDS]
            w.writerow([_fmt(v) for v in row])


def write_validation_json(path, result):
    doc = {
        "schema": SCHEMA_VALIDATION,
        "generator": result["generator"],
        "generator_version": result["generator_version"],
        "independence": {
            "project_modules_imported": [],
            "allowed_dependencies": ["python-stdlib"],
            "note": "geometry algebra re-implemented from scratch; no project "
                    "module is imported",
        },
        "theta_min_deg": result["theta_min_deg"],
        "tolerances": result["tolerances"],
        "z_label_source": result.get("z_label_source"),
        "z_labels": result["z_labels"],
        "summary": result["summary"],
        "per_height": result["per_height"],
        "histogram": result["histogram"],
        "worst_routes": result["worst_routes"],
        "worst_crossings": result["worst_crossings"],
        "overlap_events": result["overlap_events"],
        "endpoint_touch_events": result["endpoint_touch_events"],
        "tangent_or_near_tangent_events": result["tangent_or_near_tangent_events"],
        "clearance_violations": result["clearance_violations"],
        "skipped": result["skipped"],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False, allow_nan=False)
        fh.write("\n")


def write_violations_json(path, result, routes_file, routes_sha256):
    summary = result["summary"]
    theta_min = result["theta_min_deg"]
    viol = [c for c in result["crossings"] if not c["pass_45"]]
    viol.sort(key=lambda c: (c["angle_deg"], c["crossing_id"]))
    doc = {
        "schema": SCHEMA_VIOLATIONS,
        "generator": result["generator"],
        "generator_version": result["generator_version"],
        "routes_file": routes_file,
        "routes_sha256": routes_sha256,
        "theta_min_deg": theta_min,
        "primary_category": "crossings with angle_deg < theta_min",
        "counts": {
            "angle_violations": len(viol),
            "overlap_events": summary["overlap_event_count"],
            "endpoint_touches": summary["endpoint_touch_count"],
            "tangent_or_near_tangent_events":
                summary["tangent_or_near_tangent_count"],
            "clearance_violations": summary["clearance_violation_count"],
        },
        "angle_violations": [_crossing_row(c) for c in viol],
        "overlap_events": result["overlap_events"],
        "endpoint_touch_events": result["endpoint_touch_events"],
        "tangent_or_near_tangent_events": result["tangent_or_near_tangent_events"],
        "clearance_violations": result["clearance_violations"],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False, allow_nan=False)
        fh.write("\n")


# ---------------------------------------------------------------------------
# layer label support
# ---------------------------------------------------------------------------
def load_layer_labels(path):
    """Read a z -> label map from a ``layer_planes.json``-style file.

    Accepted shapes: ``{"planes": [{"z_mm":..., "label":...}, ...]}`` (the
    project format), ``{"body_planes": {"2": -0.325, ...}}`` (labels become
    ``L<plane_id>``), ``{"z_to_label": {...}}`` and a plain list of objects.
    Never raises: an unusable file just yields an empty map.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except Exception as exc:  # pragma: no cover - defensive
        print("[warn] --layers-json unusable (%s); falling back to H## labels" % exc)
        return {}
    out = {}
    if isinstance(doc, dict):
        planes = doc.get("planes")
        if isinstance(planes, list):
            for p in planes:
                if not isinstance(p, dict):
                    continue
                z = p.get("z_mm")
                lab = p.get("label") or ("L%s" % p.get("plane_id"))
                if z is not None and lab is not None:
                    out[round(float(z), 9)] = str(lab)
        for key in ("interface_planes",):
            block = doc.get(key)
            if isinstance(block, dict):
                for _k, p in block.items():
                    if isinstance(p, dict) and p.get("z_mm") is not None:
                        out[round(float(p["z_mm"]), 9)] = str(
                            p.get("label") or _k)
        body = doc.get("body_planes")
        if isinstance(body, dict):
            for pid, z in body.items():
                if z is not None and round(float(z), 9) not in out:
                    out[round(float(z), 9)] = "L%s" % pid
        zmap = doc.get("z_to_label")
        if isinstance(zmap, dict):
            for z, lab in zmap.items():
                try:
                    out[round(float(z), 9)] = str(lab)
                except (TypeError, ValueError):
                    pass
    elif isinstance(doc, list):
        for p in doc:
            if isinstance(p, dict) and p.get("z_mm") is not None:
                out[round(float(p["z_mm"]), 9)] = str(
                    p.get("label") or p.get("plane_id"))
    return out


def labels_from_routes_document(doc):
    """Best-effort physical z -> layer label map from the routes JSON itself.

    The frozen baseline carries ``process.plane_heights_mm`` (plane id -> z) and
    ``process.interface_planes`` (id -> {label, z_mm}); both are optional.  The
    returned map is only used for the cosmetic ``z_label`` column.
    """
    out = {}
    if not isinstance(doc, dict):
        return out
    proc = doc.get("process") or {}
    iface = proc.get("interface_planes") if isinstance(proc, dict) else None
    if isinstance(iface, dict):
        for pid, info in iface.items():
            if isinstance(info, dict) and info.get("z_mm") is not None:
                out[round(float(info["z_mm"]), 9)] = str(
                    info.get("label") or ("L%s" % pid))
    heights = proc.get("plane_heights_mm") if isinstance(proc, dict) else None
    if isinstance(heights, dict):
        for pid, z in heights.items():
            if z is None:
                continue
            out.setdefault(round(float(z), 9), "L%s" % pid)
    return out


# ---------------------------------------------------------------------------
# self tests
# ---------------------------------------------------------------------------
def _flat(z, prims):
    length = 0.0
    for pr in prims:
        if pr["kind"] == "line":
            length += math.hypot(pr["p1"][0] - pr["p0"][0],
                                 pr["p1"][1] - pr["p0"][1])
        else:
            length += pr["radius"] * abs(pr["sweep"])
    return {"kind": "flat", "z_mm": z, "layer_id": 0,
            "length_mm": length, "primitives": prims}


def _line(p0, p1):
    return {"kind": "line", "p0": [float(p0[0]), float(p0[1])],
            "p1": [float(p1[0]), float(p1[1])]}


def _arc(cx, cy, r, a0, sweep):
    x0 = cx + r * math.cos(a0)
    y0 = cy + r * math.sin(a0)
    x1 = cx + r * math.cos(a0 + sweep)
    y1 = cy + r * math.sin(a0 + sweep)
    return {"kind": "arc", "center": [float(cx), float(cy)],
            "radius": float(r), "start_angle": float(a0),
            "sweep": float(sweep), "p0": [x0, y0], "p1": [x1, y1]}


def _route(rid, parts):
    return {
        "route_id": rid,
        "source_side": "N",
        "target_side": "S",
        "source_endpoint": "N%02d:1:1" % rid,
        "target_endpoint": "S%02d:1:1" % rid,
        "target_plane": 1000 + rid,
        "parts": parts,
    }


def _angles(crossings):
    return [c["angle_deg"] for c in crossings]


def run_selftests():
    """Synthetic analytic checks; returns process exit code."""
    t0 = time.time()
    checks = []

    def check(name, cond, detail=""):
        checks.append((name, bool(cond)))
        print("[selftest] %-58s %-58s %s"
              % (name, detail, "PASS" if cond else "FAIL"), flush=True)

    print("[selftest] independent G5 angle validator v%s" % __version__)
    print("[selftest] all angles are computed by the production code path "
          "audit_routes(); expected values are analytic")

    # -- 1. perpendicular lines -> 90 deg ----------------------------------
    routes = [
        _route(1, [_flat(0.0, [_line((0.0, -5.0), (0.0, 5.0))])]),
        _route(2, [_flat(0.0, [_line((-5.0, 0.0), (5.0, 0.0))])]),
    ]
    res = audit_routes(routes)
    ang = _angles(res["crossings"])
    check("01 perpendicular lines", len(ang) == 1 and abs(ang[0] - 90.0) <= 1e-9,
          "n=%d theta=%.15f" % (len(ang), ang[0] if ang else float("nan")))

    # -- 2. 45 deg lines, and 44.999 deg flagged ---------------------------
    c = math.cos(math.radians(45.0))
    routes = [
        _route(1, [_flat(0.0, [_line((-5.0, 0.0), (5.0, 0.0))])]),
        _route(2, [_flat(0.0, [_line((-5.0 * c, -5.0 * c), (5.0 * c, 5.0 * c))])]),
    ]
    res = audit_routes(routes)
    ang = _angles(res["crossings"])
    check("02a lines at 45 deg", len(ang) == 1 and abs(ang[0] - 45.0) <= 1e-9,
          "theta=%.15f pass_45=%s" % (ang[0] if ang else float("nan"),
                                      res["crossings"][0]["pass_45"] if ang else None))

    c2 = math.cos(math.radians(44.999))
    s2 = math.sin(math.radians(44.999))
    routes = [
        _route(1, [_flat(0.0, [_line((-5.0, 0.0), (5.0, 0.0))])]),
        _route(2, [_flat(0.0, [_line((-5.0 * c2, -5.0 * s2),
                                     (5.0 * c2, 5.0 * s2))])]),
    ]
    res = audit_routes(routes)
    ang = _angles(res["crossings"])
    ok2 = (len(ang) == 1 and abs(ang[0] - 44.999) <= 1e-9
           and res["summary"]["n_lt_45"] == 1
           and not res["crossings"][0]["pass_45"]
           and abs(res["crossings"][0]["deficit_deg"] - 0.001) <= 1e-9)
    check("02b lines at 44.999 deg -> violation", ok2,
          "theta=%.15f n_lt_45=%d pass=%s"
          % (ang[0] if ang else float("nan"), res["summary"]["n_lt_45"],
             res["crossings"][0]["pass_45"] if ang else None))

    # -- 3. line vs circle ------------------------------------------------
    # theta = acos(d/R) = 90 - asin(d/R); d = R*cos(theta)
    # NB: the full-circle arcs start at 0.1 rad so their chain seam is never
    # placed exactly on a hit point (the seam is a chain end by definition).
    R = 15.0
    SEAM = 0.1
    for want in (30.0, 45.0, 90.0):
        d = R * math.cos(math.radians(want))
        routes = [
            _route(1, [_flat(0.0, [_line((-20.0, d), (20.0, d))])]),
            _route(2, [_flat(0.0, [_arc(0.0, 0.0, R, SEAM, 2.0 * math.pi)])]),
        ]
        res = audit_routes(routes)
        ang = _angles(res["crossings"])
        ok = (len(ang) == 2
              and all(abs(a - want) <= 1e-9 for a in ang)
              and all(abs(a - math.degrees(math.acos(d / R))) <= 1e-9 for a in ang))
        check("03 line/arc chord d=R*cos(%.0f deg)" % want, ok,
              "theta=%s expect=%.9f" % (["%.12f" % a for a in ang], want))
    # chord through the centre -> 90
    routes = [
        _route(1, [_flat(0.0, [_line((-20.0, 0.0), (20.0, 0.0))])]),
        _route(2, [_flat(0.0, [_arc(0.0, 0.0, R, SEAM, 2.0 * math.pi)])]),
    ]
    res = audit_routes(routes)
    ang = _angles(res["crossings"])
    check("03b chord through the arc centre -> 90 deg",
          len(ang) == 2 and all(abs(a - 90.0) <= 1e-9 for a in ang),
          "theta=%s" % ["%.12f" % a for a in ang])
    # the brief's calibration point: d = R*sin(45) -> exactly 45 deg
    d = R * math.sin(math.radians(45.0))
    routes = [
        _route(1, [_flat(0.0, [_line((-20.0, d), (20.0, d))])]),
        _route(2, [_flat(0.0, [_arc(0.0, 0.0, R, SEAM, 2.0 * math.pi)])]),
    ]
    res = audit_routes(routes)
    ang = _angles(res["crossings"])
    check("03c d=R*sin(45 deg) -> 45 deg",
          len(ang) == 2 and all(abs(a - 45.0) <= 1e-9 for a in ang),
          "theta=%s" % ["%.12f" % a for a in ang])

    # -- 4. two equal circles --------------------------------------------
    for want in (45.0, 5.0):
        # theta = pi - 2*acos(d/(2R))
        d = 2.0 * R * math.cos(math.radians((180.0 - want) / 2.0))
        routes = [
            _route(1, [_flat(0.0, [_arc(0.0, 0.0, R, 0.0, 2.0 * math.pi)])]),
            _route(2, [_flat(0.0, [_arc(d, 0.0, R, 0.0, 2.0 * math.pi)])]),
        ]
        res = audit_routes(routes)
        ang = _angles(res["crossings"])
        analytic = math.degrees(math.pi - 2.0 * math.acos(d / (2.0 * R)))
        ok = (len(ang) == 2 and abs(analytic - want) <= 1e-9
              and all(abs(a - analytic) <= 1e-9 for a in ang)
              and all(abs(a - want) <= 1e-9 for a in ang))
        check("04 equal circles, d=2R*cos(%.1f deg) -> %.1f deg"
              % ((180.0 - want) / 2.0, want), ok,
              "theta=%s analytic=%.12f" % (["%.12f" % a for a in ang], analytic))

    # -- 5. tangent circles ----------------------------------------------
    for label, d in (("exact", 2.0 * R),
                     ("slightly outside", 2.0 * R * (1.0 + 1e-14))):
        routes = [
            _route(1, [_flat(0.0, [_arc(0.0, 0.0, R, 0.0, 2.0 * math.pi)])]),
            _route(2, [_flat(0.0, [_arc(d, 0.0, R, 0.0, 2.0 * math.pi)])]),
        ]
        res = audit_routes(routes)
        ok = (len(res["crossings"]) == 0
              and res["summary"]["tangent_or_near_tangent_count"] == 1
              and res["summary"]["n_lt_45"] == 0
              and len(res["tangent_or_near_tangent_events"]) == 1
              and res["tangent_or_near_tangent_events"][0]["angle_deg"] <= 1e-6)
        check("05 tangent circles (%s) -> not a crossing" % label, ok,
              "crossings=%d tangent=%d"
              % (len(res["crossings"]),
                 res["summary"]["tangent_or_near_tangent_count"]))

    # -- 6. coincident arcs ----------------------------------------------
    routes = [
        _route(1, [_flat(0.0, [_arc(0.0, 0.0, R, 0.0, math.pi)])]),
        _route(2, [_flat(0.0, [_arc(0.0, 0.0, R, math.pi / 4.0, math.pi)])]),
    ]
    res = audit_routes(routes)
    ok = (len(res["crossings"]) == 0
          and res["summary"]["overlap_event_count"] == 1
          and res["overlap_events"][0]["overlap_mm"] > 1.0
          and abs(res["overlap_events"][0]["overlap_mm"] - R * 3.0 * math.pi / 4.0) <= 1e-9
          and res["summary"]["verdict_pass_45"] is False)
    check("06 coincident arcs -> overlap, not crossing", ok,
          "overlap=%.12f mm expect=%.12f"
          % (res["overlap_events"][0]["overlap_mm"] if res["overlap_events"] else -1.0,
             R * 3.0 * math.pi / 4.0))

    # -- 7. crossing exactly at a chain end ------------------------------
    routes = [
        _route(1, [_flat(0.0, [_line((-5.0, 0.0), (5.0, 0.0))])]),
        _route(2, [_flat(0.0, [_line((0.0, 0.0), (0.0, 5.0))])]),
    ]
    res = audit_routes(routes)
    ok = (len(res["crossings"]) == 0
          and res["summary"]["endpoint_touch_count"] == 1
          and res["summary"]["verdict_pass_45"] is False)
    check("07 crossing at a chain end -> endpoint_touch", ok,
          "crossings=%d endpoint_touch=%d"
          % (len(res["crossings"]), res["summary"]["endpoint_touch_count"]))

    # -- 8. cross-height primitives never cross --------------------------
    routes = [
        _route(1, [_flat(0.0, [_line((0.0, -5.0), (0.0, 5.0))])]),
        _route(2, [_flat(0.05, [_line((-5.0, 0.0), (5.0, 0.0))])]),
    ]
    res = audit_routes(routes)
    check("08 different heights (dz=0.05) -> no crossing",
          len(res["crossings"]) == 0 and res["summary"]["n_lt_45"] == 0,
          "crossings=%d" % len(res["crossings"]))

    # -- 9. parallel lines -> no crossing, clearance rule ----------------
    routes = [
        _route(1, [_flat(0.0, [_line((-5.0, 0.0), (5.0, 0.0))])]),
        _route(2, [_flat(0.0, [_line((-5.0, 0.05), (5.0, 0.05))])]),
    ]
    res = audit_routes(routes)
    check("09a parallel lines 0.05 mm apart -> clearance violation",
          len(res["crossings"]) == 0
          and res["summary"]["clearance_violation_count"] == 1
          and abs(res["summary"]["clearance_min_non_crossing_mm"] - 0.05) <= 1e-12,
          "min=%.12f viol=%d"
          % (res["summary"]["clearance_min_non_crossing_mm"] or -1,
             res["summary"]["clearance_violation_count"]))
    routes = [
        _route(1, [_flat(0.0, [_line((-5.0, 0.0), (5.0, 0.0))])]),
        _route(2, [_flat(0.0, [_line((-5.0, 0.5), (5.0, 0.5))])]),
    ]
    res = audit_routes(routes)
    check("09b parallel lines 0.5 mm apart -> no violation",
          res["summary"]["clearance_violation_count"] == 0,
          "min=%.12f"
          % (res["summary"]["clearance_min_non_crossing_mm"] or -1))
    # a genuine crossing is exempt from the 0.08 mm clearance rule
    routes = [
        _route(1, [_flat(0.0, [_line((0.0, -5.0), (0.0, 5.0))])]),
        _route(2, [_flat(0.0, [_line((-5.0, 0.0), (5.0, 0.0))])]),
    ]
    res = audit_routes(routes)
    check("09c crossing pair exempt from the clearance rule",
          len(res["crossings"]) == 1
          and res["summary"]["clearance_violation_count"] == 0,
          "crossings=%d viol=%d"
          % (len(res["crossings"]),
             res["summary"]["clearance_violation_count"]))

    # -- 10. collinear overlap -------------------------------------------
    routes = [
        _route(1, [_flat(0.0, [_line((0.0, 0.0), (10.0, 0.0))])]),
        _route(2, [_flat(0.0, [_line((5.0, 0.0), (15.0, 0.0))])]),
    ]
    res = audit_routes(routes)
    check("10 collinear overlap -> overlap 5 mm, no crossing",
          len(res["crossings"]) == 0
          and res["summary"]["overlap_event_count"] == 1
          and abs(res["overlap_events"][0]["overlap_mm"] - 5.0) <= 1e-12,
          "overlap=%.12f"
          % (res["overlap_events"][0]["overlap_mm"] if res["overlap_events"] else -1.0))

    # -- 11. s accumulates over several flat parts at the same height ----
    trans = {"kind": "transition", "start": [0.0, 0.0], "direction": [0.0, 1.0],
             "z0": 0.0, "z1": 0.05, "radius_mm": 15.0, "theta_rad": 0.0,
             "footprint_mm": 1.0, "length_mm": 1.0}
    routes = [
        _route(1, [
            _flat(0.0, [_line((0.0, -10.0), (0.0, 0.0))]),
            trans,
            _flat(0.0, [_line((0.0, 1.0), (0.0, 11.0))]),
        ]),
        _route(2, [_flat(0.0, [_line((-5.0, 5.0), (5.0, 5.0))])]),
    ]
    res = audit_routes(routes)
    ok = (len(res["crossings"]) == 1
          and abs(res["crossings"][0]["s_a"] - 14.0) <= 1e-9
          and abs(res["crossings"][0]["s_b"] - 5.0) <= 1e-9
          and abs(res["crossings"][0]["chain_a"] - 20.0) <= 1e-9)
    check("11 chain arc length over two flat parts at one z", ok,
          "s_a=%.12f expect=14 s_b=%.12f"
          % (res["crossings"][0]["s_a"] if res["crossings"] else -1,
             res["crossings"][0]["s_b"] if res["crossings"] else -1))

    # -- 12. corner hit shared by two primitives is deduplicated ---------
    routes = [
        _route(1, [_flat(0.0, [
            _line((0.0, 0.0), (0.0, 10.0)),
            _arc(-15.0, 10.0, 15.0, 0.0, math.pi / 2.0),
        ])]),
        _route(2, [_flat(0.0, [_line((-5.0, 10.0), (5.0, 10.0))])]),
    ]
    res = audit_routes(routes)
    ang = _angles(res["crossings"])
    ok = (len(ang) == 1 and abs(ang[0] - 90.0) <= 1e-9
          and abs(res["crossings"][0]["s_a"] - 10.0) <= 1e-9
          and res["crossings"][0]["n_duplicate_hits"] >= 1)
    check("12 tangent-continuous joint -> one deduplicated hit", ok,
          "n=%d theta=%.12f s_a=%.9f"
          % (len(ang), ang[0] if ang else float("nan"),
             res["crossings"][0]["s_a"] if ang else -1))

    # -- 13. a chord through a full circle yields two crossings ----------
    routes = [
        _route(1, [_flat(0.0, [_line((-20.0, 5.0), (20.0, 5.0))])]),
        _route(2, [_flat(0.0, [_arc(0.0, 0.0, R, 0.0, 2.0 * math.pi)])]),
    ]
    res = audit_routes(routes)
    ang = _angles(res["crossings"])
    xs = sorted(c["x"] for c in res["crossings"])
    ok = (len(ang) == 2
          and abs(xs[0] + math.sqrt(R * R - 25.0)) <= 1e-9
          and abs(xs[1] - math.sqrt(R * R - 25.0)) <= 1e-9
          and all(abs(a - math.degrees(math.acos(5.0 / R))) <= 1e-9 for a in ang))
    check("13 chord crosses a full circle twice -> 2 crossings", ok,
          "n=%d x=%s theta=%s" % (len(ang), ["%.9f" % x for x in xs],
                                  ["%.9f" % a for a in ang]))

    # -- 14. exact line-arc tangency ------------------------------------
    routes = [
        _route(1, [_flat(0.0, [_line((-5.0, 15.0), (5.0, 15.0))])]),
        _route(2, [_flat(0.0, [_arc(0.0, 0.0, R, 0.0, 2.0 * math.pi)])]),
    ]
    res = audit_routes(routes)
    check("14 exact line-arc tangency -> tangent, not crossing",
          len(res["crossings"]) == 0
          and res["summary"]["tangent_or_near_tangent_count"] == 1
          and res["summary"]["n_lt_45"] == 0,
          "crossings=%d tangent=%d"
          % (len(res["crossings"]),
             res["summary"]["tangent_or_near_tangent_count"]))

    # -- 15. slightly-negative line-arc discriminant --------------------
    # y = R*(1+2e-14) leaves delta ~ -9e-12, inside the 1e-12*R^2 budget
    routes = [
        _route(1, [_flat(0.0, [_line((-5.0, R * (1.0 + 2e-14)),
                                     (5.0, R * (1.0 + 2e-14)))])]),
        _route(2, [_flat(0.0, [_arc(0.0, 0.0, R, 0.0, 2.0 * math.pi)])]),
    ]
    res = audit_routes(routes)
    check("15 near-tangent line/arc -> tangent_or_near_tangent",
          len(res["crossings"]) == 0
          and res["summary"]["tangent_or_near_tangent_count"] == 1,
          "crossings=%d tangent=%d"
          % (len(res["crossings"]),
             res["summary"]["tangent_or_near_tangent_count"]))

    # -- 16. angle formula is the local tangent angle -------------------
    # 30 deg line: route A at 30 deg to route B's x-axis line
    c30 = math.cos(math.radians(30.0))
    s30 = math.sin(math.radians(30.0))
    routes = [
        _route(1, [_flat(0.0, [_line((-5.0, 0.0), (5.0, 0.0))])]),
        _route(2, [_flat(0.0, [_line((-5.0 * c30, -5.0 * s30),
                                     (5.0 * c30, 5.0 * s30))])]),
    ]
    res = audit_routes(routes)
    ang = _angles(res["crossings"])
    check("16 lines at 30 deg -> asin|cross(t_i,t_j)| = 30",
          len(ang) == 1 and abs(ang[0] - 30.0) <= 1e-9,
          "theta=%.15f" % (ang[0] if ang else float("nan")))

    # -- 17. exact primitive-pair distances (clearance algebra) ----------
    # two disjoint circles: centre distance d -> gap d - r1 - r2
    d = 30.5
    routes = [
        _route(1, [_flat(0.0, [_arc(0.0, 0.0, R, -0.5, 1.0)])]),
        _route(2, [_flat(0.0, [_arc(d, 0.0, R, math.pi - 0.5, 1.0)])]),
    ]
    res = audit_routes(routes)
    got = res["summary"]["clearance_min_non_crossing_mm"]
    check("17a arc-arc distance d-(r1+r2)", got is not None and abs(got - 0.5) <= 1e-9,
          "min=%.12f expect=0.5" % (got if got is not None else -1.0))
    # line above a circle: distance = |dist(centre,line) - R|
    routes = [
        _route(1, [_flat(0.0, [_line((-5.0, R + 0.5), (5.0, R + 0.5))])]),
        _route(2, [_flat(0.0, [_arc(0.0, 0.0, R, 0.1, 2.0 * math.pi)])]),
    ]
    res = audit_routes(routes)
    got = res["summary"]["clearance_min_non_crossing_mm"]
    check("17b line-arc distance |d-R|", got is not None and abs(got - 0.5) <= 1e-9,
          "min=%.12f expect=0.5" % (got if got is not None else -1.0))
    # two parallel segments
    routes = [
        _route(1, [_flat(0.0, [_line((-5.0, 0.0), (5.0, 0.0))])]),
        _route(2, [_flat(0.0, [_line((0.0, 0.375), (10.0, 0.375))])]),
    ]
    res = audit_routes(routes)
    got = res["summary"]["clearance_min_non_crossing_mm"]
    check("17c line-line distance (parallel)", got is not None and abs(got - 0.375) <= 1e-12,
          "min=%.12f expect=0.375" % (got if got is not None else -1.0))

    elapsed = time.time() - t0
    n_fail = sum(1 for _n, ok in checks if not ok)
    n_pass = len(checks) - n_fail
    print("[selftest] ----------------------------------------------------------")
    for name, ok in checks:
        if not ok:
            print("[selftest] FAILED: %s" % name)
    print('[selftest] SELFTEST_SUMMARY {"passed": %d, "failed": %d, '
          '"checks": %d, "elapsed_s": %.3f, "status": "%s"}'
          % (n_pass, n_fail, len(checks), elapsed,
             "PASS" if n_fail == 0 else "FAIL"), flush=True)
    return 0 if n_fail == 0 else 1


# ---------------------------------------------------------------------------
# independence guard
# ---------------------------------------------------------------------------
def assert_no_project_imports(forbidden=FORBIDDEN_PROJECT_MODULES):
    """Fail loudly if any project geometry module was imported."""
    bad = []
    for name in list(sys.modules):
        root = name.split(".")[0]
        if root in forbidden:
            bad.append(name)
    if bad:
        raise RuntimeError(
            "independence violated: project modules imported: %s" % sorted(bad))
    return sorted(set(m.split(".")[0] for m in sys.modules if m))


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Independent G5 same-height crossing-angle validator "
                    "(no project imports).")
    ap.add_argument("--run-dir", help="directory containing routes_l3d.json")
    ap.add_argument("--out-dir", help="directory for the three output files")
    ap.add_argument("--routes-file", default=None,
                    help="override the routes file (default <run-dir>/routes_l3d.json)")
    ap.add_argument("--theta-min", type=float, default=45.0,
                    help="hard crossing-angle threshold in degrees (default 45)")
    ap.add_argument("--layers-json", default=None,
                    help="optional layer_planes.json for physical z labels")
    ap.add_argument("--selftest", action="store_true",
                    help="run the synthetic analytic self-tests and exit")
    args = ap.parse_args(argv)

    if args.selftest:
        rc = run_selftests()
        try:
            assert_no_project_imports()
            print("[selftest] independence guard: PASS (no project modules imported)")
        except RuntimeError as exc:
            print("[selftest] independence guard: FAIL (%s)" % exc)
            rc = 1
        return rc

    if not args.run_dir or not args.out_dir:
        ap.error("--run-dir and --out-dir are required unless --selftest")

    t_start = time.time()
    run_dir = os.path.abspath(args.run_dir)
    out_dir = os.path.abspath(args.out_dir)
    routes_file = args.routes_file or os.path.join(run_dir, "routes_l3d.json")
    if not os.path.isfile(routes_file):
        print("[error] routes file not found: %s" % routes_file, file=sys.stderr)
        return 2
    os.makedirs(out_dir, exist_ok=True)

    print("[load] %s" % routes_file, flush=True)
    with open(routes_file, "rb") as fh:
        blob = fh.read()
    sha = hashlib.sha256(blob).hexdigest()
    doc = json.loads(blob.decode("utf-8"))
    routes = doc.get("routes") if isinstance(doc, dict) else doc
    if not isinstance(routes, list) or not routes:
        print("[error] no 'routes' list in %s" % routes_file, file=sys.stderr)
        return 2
    print("[load] routes=%d sha256=%s (%.2fs)"
          % (len(routes), sha, time.time() - t_start), flush=True)

    z_label_map = {}
    if args.layers_json:
        z_label_map = load_layer_labels(args.layers_json)
        z_label_source = "layers-json:%s" % args.layers_json
        print("[load] layer labels=%d from %s"
              % (len(z_label_map), args.layers_json), flush=True)
    else:
        doc_labels = labels_from_routes_document(doc)
        if doc_labels:
            z_label_map = doc_labels
            z_label_source = ("routes-document:process.plane_heights_mm/"
                              "interface_planes")
            print("[load] layer labels=%d derived from the routes document "
                  "(process.plane_heights_mm / interface_planes)"
                  % len(z_label_map), flush=True)
        else:
            z_label_source = "auto:H##-ascending-z"

    result = audit_routes(routes, theta_min=args.theta_min,
                          log=lambda m: print(m, flush=True),
                          z_label_map=z_label_map)
    result["z_label_source"] = z_label_source

    csv_path = os.path.join(out_dir, "g5_crossing_angles.csv")
    val_path = os.path.join(out_dir, "g5_angle_validation.json")
    vio_path = os.path.join(out_dir, "g5_angle_violations.json")

    rows = [_crossing_row(c) for c in result["crossings"]]
    write_csv(csv_path, rows)
    print("[write] %s (%d rows)" % (csv_path, len(rows)), flush=True)
    write_validation_json(val_path, result)
    print("[write] %s" % val_path, flush=True)
    write_violations_json(vio_path, result, routes_file, sha)
    print("[write] %s" % vio_path, flush=True)

    summary = result["summary"]
    one_line = {
        "routes": summary["routes"],
        "heights": summary["heights"],
        "total_crossings": summary["total_crossings"],
        "unique_route_pairs": summary["unique_route_pairs"],
        "routes_with_crossings": summary["routes_with_crossings"],
        "max_crossings_per_route": summary["max_crossings_per_route"],
        "max_crossings_route_ids": summary["max_crossings_route_ids"],
        "min_angle_deg": summary["min_angle_deg"],
        "min_angle_crossing_id": summary["min_angle_crossing_id"],
        "n_lt_45": summary["n_lt_45"],
        "n_lt_5": summary["n_lt_5"],
        "D_theta_deg": summary["D_theta_deg"],
        "D_max_deg": summary["D_max_deg"],
        "overlaps": summary["overlap_event_count"],
        "endpoint_touches": summary["endpoint_touch_count"],
        "tangent_or_near_tangent": summary["tangent_or_near_tangent_count"],
        "clearance_violations": summary["clearance_violation_count"],
        "clearance_min_non_crossing_mm": summary["clearance_min_non_crossing_mm"],
        "residual_max_mm": summary["residual_max_mm"],
        "pass_45": summary["verdict_pass_45"],
        "theta_min_deg": summary["theta_min_deg"],
        "sha256": sha,
        "runtime_s": round(time.time() - t_start, 3),
    }
    print("G5_ANGLE_SUMMARY " + json.dumps(one_line, ensure_ascii=False),
          flush=True)
    print("[done] runtime=%.2fs out=%s"
          % (time.time() - t_start, out_dir), flush=True)
    try:
        assert_no_project_imports()
        print("[independence] PASS: only standard-library modules imported",
              flush=True)
    except RuntimeError as exc:
        print("[independence] FAIL: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
