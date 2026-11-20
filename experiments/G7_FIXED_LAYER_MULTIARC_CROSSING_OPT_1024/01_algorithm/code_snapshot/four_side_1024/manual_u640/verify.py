# -*- coding: utf-8 -*-
"""Independent geometric verification of the 640-channel manual_u640 routing.

This module is deliberately **not** a wrapper around the router's own checks.  It
re-derives every verdict from the saved route geometry:

* record / port / layer identity is compared against the CSV input model
  (:mod:`four_side_1024.manual_u640.inputs`) — a record is never merged or
  re-paired, and the two interface rows (z1 = 0.0 mm, z2 = 0.5 mm) stay separate;
* the single-route geometry (axis-aligned D56 lines, exact-R arcs, position and
  tangent continuity, fixed ports, stroked board bounds, part/structure
  consistency) is re-read primitive by primitive here;
* same-physical-plane conflicts use the frozen strict D56 index **and** are
  cross-checked pair by pair with the independent authoritative validator
  :func:`four_side_1024.d56.validate_d56.evaluate_pair` (``policy='strict'``);
  legal crossings are counted separately and are never reported as violations;
* cross-plane clearance re-samples the elevation S-curves and computes true 3D
  centre-line distances against every flat primitive / transition of the other
  routes (the intermediate layers a lifted route passes through are covered);
* self clearance, U-turn depth/nesting, failure authenticity, per-plane and
  per-layer statistics are computed here.

The only reused low-level primitives are the frozen D56 geometry/index code, the
independent ``validate_d56`` pair predicate, and the shared layer/process
configuration.  No routing, plotting or export module is imported.

Public API
----------
``verify_all(routes, data, stack, radius=15.0, clearance=0.08, log=print) -> dict``

The returned dict is JSON ready and contains at least: ``summary``, ``checks``,
``violations``, ``per_plane``, ``per_layer``, ``min_clearance_mm``,
``min_radius_mm``, ``min_cross_angle_deg``, ``u_depth_table``, ``crossings``,
``failed_routes``.

Command line
------------
``python -m four_side_1024.manual_u640.verify \
    --routes outputs/manual_u640/routes.json \
    --out outputs/manual_u640/validation.json [--json]``
"""
from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

import numpy as np

from . import config as C

SCHEMA = 'four_side_1024_manual_u640_verification_v1'

# ---------------------------------------------------------------------------
# tolerances (task statement / CONTRACT.md)
# ---------------------------------------------------------------------------
TOL_COORD = 1e-9          # record identity coordinate tolerance (task §1)
TOL_XY = 1e-9             # adjacent primitive endpoint coincidence (task §4)
TOL_POS_CSV = 1e-7        # route endpoint vs CSV port coordinate (route pose)
TOL_ANGLE_DEG = 1e-6      # tangent continuity angle tolerance (task §4)
TOL_RADIUS_MM = 1e-6      # an arc may not be smaller than R inside this band
TOL_Z = 1e-9              # flat/transition height joins
TOL_STRUCT_REL = 1e-6     # relative structural consistency (lengths etc.)
TOL_BOARD = 1e-6
HALF_WIDTH = float(C.WIDTH_MM) / 2.0
BOARD = float(C.BOARD_MM)

STATUS_ROUTED = {'routed', 'success', 'succeeded', 'ok', 'routed_ok'}
STATUS_FAILED = {'failed', 'failure', 'fail', 'blocked', 'rejected'}

#: transition placement margins of the shared builder (l3d.paths); imported
#: lazily with a local fallback so that verification works even if that module
#: changes its constant names.
PORT_MARGIN_MM = 1.2
SEGMENT_MARGIN_MM = 0.25
try:  # pragma: no cover - constant import only
    from four_side_1024.l3d import paths as _L3D_PATHS
    PORT_MARGIN_MM = float(getattr(_L3D_PATHS, 'PORT_MARGIN_MM', PORT_MARGIN_MM))
    SEGMENT_MARGIN_MM = float(getattr(_L3D_PATHS, 'SEGMENT_MARGIN_MM',
                                      SEGMENT_MARGIN_MM))
except Exception:  # pragma: no cover
    pass


# ---------------------------------------------------------------------------
# generic helpers
# ---------------------------------------------------------------------------
def _json_safe(value):
    """Recursively make a value strictly JSON serialisable."""
    if isinstance(value, (np.floating, np.integer)):
        value = value.item()
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


def _f(value, default=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def _dist2(a, b):
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def _unit2(vector):
    length = math.hypot(float(vector[0]), float(vector[1]))
    if length <= 1e-15:
        return None
    return (float(vector[0]) / length, float(vector[1]) / length)


def _angle_deg(first, second):
    """Angle between two 2D/3D vectors in degrees (``None`` on degenerate input)."""
    a = np.asarray(first, dtype=float)
    b = np.asarray(second, dtype=float)
    norm = float(np.linalg.norm(a) * np.linalg.norm(b))
    if norm <= 1e-15:
        return None
    cosine = float(np.dot(a, b) / norm)
    cosine = max(-1.0, min(1.0, cosine))
    return math.degrees(math.acos(cosine))


def _status(route):
    text = route.get('status')
    if text is None:
        return 'routed' if route.get('parts') else 'failed'
    text = str(text).strip().lower()
    if text in STATUS_FAILED:
        return 'failed'
    if text in STATUS_ROUTED:
        return 'routed'
    return text or 'routed'


def _is_failed(route):
    return _status(route) == 'failed'


# ---------------------------------------------------------------------------
# primitive geometry (independent re-implementation)
# ---------------------------------------------------------------------------
_TAU = 2.0 * math.pi


def _prim_kind(prim):
    if not isinstance(prim, dict):
        return None
    kind = prim.get('kind')
    return kind if kind in ('line', 'arc') else None


def _angle_in_sweep(angle, start, sweep, tol=1e-12):
    """Is ``angle`` on the oriented arc ``[start, start+sweep]``?"""
    if abs(sweep) >= _TAU - tol:
        return True
    if sweep >= 0.0:
        delta = (angle - start) % _TAU
        return delta <= sweep + tol or delta >= _TAU - tol
    delta = (start - angle) % _TAU
    return delta <= -sweep + tol or delta >= _TAU - tol


def _prim_endpoints(prim):
    """``(p0, p1)`` as float tuples."""
    p0 = prim.get('p0')
    p1 = prim.get('p1')
    return (float(p0[0]), float(p0[1])), (float(p1[0]), float(p1[1]))


def _prim_length(prim):
    kind = _prim_kind(prim)
    p0, p1 = _prim_endpoints(prim)
    if kind == 'line':
        return _dist2(p0, p1)
    if kind == 'arc':
        return abs(float(prim['radius'])) * abs(float(prim['sweep']))
    return 0.0


def _prim_tangent(prim, at_end):
    kind = _prim_kind(prim)
    p0, p1 = _prim_endpoints(prim)
    if kind == 'line':
        return _unit2((p1[0] - p0[0], p1[1] - p0[1]))
    if kind == 'arc':
        angle = float(prim['start_angle']) + (float(prim['sweep']) if at_end else 0.0)
        sign = 1.0 if float(prim['sweep']) >= 0.0 else -1.0
        return (-sign * math.sin(angle), sign * math.cos(angle))
    return None


def _prim_center_extents(prim):
    """Exact axis-aligned extents of the *centerline* primitive."""
    kind = _prim_kind(prim)
    p0, p1 = _prim_endpoints(prim)
    if kind == 'line':
        return (min(p0[0], p1[0]), min(p0[1], p1[1]),
                max(p0[0], p1[0]), max(p0[1], p1[1]))
    if kind == 'arc':
        center = (float(prim['center'][0]), float(prim['center'][1]))
        radius = float(prim['radius'])
        start = float(prim['start_angle'])
        sweep = float(prim['sweep'])
        xs = [p0[0], p1[0]]
        ys = [p0[1], p1[1]]
        for quadrant in range(-4, 13):
            angle = quadrant * math.pi / 2.0
            if _angle_in_sweep(angle, start, sweep):
                xs.append(center[0] + radius * math.cos(angle))
                ys.append(center[1] + radius * math.sin(angle))
        return (min(xs), min(ys), max(xs), max(ys))
    return (p0[0], p0[1], max(p0[0], p1[0]), max(p0[1], p1[1]))


def _prim_stroked_extents(prim, half_width):
    """Exact stroked extents with the ``geometry.bounds`` flat-port-face convention."""
    kind = _prim_kind(prim)
    p0, p1 = _prim_endpoints(prim)
    if kind == 'line':
        tangent = _prim_tangent(prim, False) or (1.0, 0.0)
        normal = (-tangent[1] * half_width, tangent[0] * half_width)
        xs = [p0[0] + normal[0], p0[0] - normal[0],
              p1[0] + normal[0], p1[0] - normal[0]]
        ys = [p0[1] + normal[1], p0[1] - normal[1],
              p1[1] + normal[1], p1[1] - normal[1]]
        return (min(xs), min(ys), max(xs), max(ys))
    if kind == 'arc':
        center = (float(prim['center'][0]), float(prim['center'][1]))
        radius = float(prim['radius'])
        start = float(prim['start_angle'])
        sweep = float(prim['sweep'])
        angles = [start, start + sweep]
        for quadrant in range(-4, 13):
            angle = quadrant * math.pi / 2.0
            if _angle_in_sweep(angle, start, sweep):
                angles.append(angle)
        xs = [center[0] + (radius + sign * half_width) * math.cos(angle)
              for sign in (-1, 1) for angle in angles]
        ys = [center[1] + (radius + sign * half_width) * math.sin(angle)
              for sign in (-1, 1) for angle in angles]
        return (min(xs), min(ys), max(xs), max(ys))
    return _prim_center_extents(prim)


def _extent_along(bbox, vector):
    """``(min, max)`` of ``dot(point, vector)`` over the corners of ``bbox``."""
    xs = (bbox[0], bbox[2])
    ys = (bbox[1], bbox[3])
    values = [vector[0] * x + vector[1] * y for x in xs for y in ys]
    return min(values), max(values)


# ---------------------------------------------------------------------------
# route structure helpers
# ---------------------------------------------------------------------------
def _parts(route):
    parts = route.get('parts')
    return parts if isinstance(parts, list) else []


def _flat_parts(route):
    return [part for part in _parts(route)
            if isinstance(part, dict) and part.get('kind') == 'flat']


def _transition_parts(route):
    return [part for part in _parts(route)
            if isinstance(part, dict) and part.get('kind') == 'transition']


def _route_xy_chain(route):
    """Full 2D chain of one route and its provenance.

    ``primitives_2d`` is authoritative when present; otherwise the chain is
    rebuilt from the parts (flat sub-chains plus the straight XY chord of every
    elevation transition, which is exactly the geometry the transition replaces).
    """
    primitives = route.get('primitives_2d')
    if isinstance(primitives, list) and primitives:
        chain = []
        for prim in primitives:
            if isinstance(prim, dict):
                chain.append(dict(prim))
        if chain:
            return chain, 'primitives_2d'
    chain = []
    for part in _parts(route):
        if not isinstance(part, dict):
            continue
        if part.get('kind') == 'flat':
            for prim in part.get('primitives') or []:
                if isinstance(prim, dict):
                    chain.append(dict(prim))
        elif part.get('kind') == 'transition':
            start = part.get('start')
            end = part.get('end')
            if isinstance(start, (list, tuple)) and isinstance(end, (list, tuple)):
                chain.append(dict(kind='line', p0=[float(start[0]), float(start[1])],
                                  p1=[float(end[0]), float(end[1])]))
    return chain, 'reconstructed_from_parts'


def _chain_length(prims):
    return float(sum(_prim_length(prim) for prim in prims))


def _expected_z(layer_id, plane):
    layer_id = int(layer_id)
    if layer_id == int(C.INTERFACE_LAYER_ID):
        return float(C.PLANE_Z_MM[plane])
    return float(C.layer_z(layer_id))


def _logical_layer_of_z(z_mm, stack=None):
    z = round(float(z_mm), 9)
    if abs(z - float(C.Z1_MM)) <= 1e-9 or abs(z - float(C.Z2_MM)) <= 1e-9:
        return int(C.INTERFACE_LAYER_ID)
    max_layer = int(getattr(stack, 'max_layer', C.MAX_LOGICAL_LAYERS))
    for layer_id in range(2, max_layer + 1):
        if abs(z - float(C.layer_z(layer_id))) <= 1e-9:
            return layer_id
    return None


# ---------------------------------------------------------------------------
# elevation S-curve helpers (independent analytic parameterisation)
# ---------------------------------------------------------------------------
def _transition_geometry(part):
    """``(radius, z0, z1, footprint, theta, start_xy, direction)`` of a transition."""
    radius = _f(part.get('radius_mm'))
    z0 = _f(part.get('z0'))
    z1 = _f(part.get('z1'))
    start = part.get('start')
    end = part.get('end')
    if radius is None or z0 is None or z1 is None or start is None or end is None:
        return None
    start = (float(start[0]), float(start[1]))
    end = (float(end[0]), float(end[1]))
    dz = abs(z1 - z0)
    if radius <= 0.0 or dz > 2.0 * radius + 1e-9:
        return None
    theta = math.acos(max(-1.0, min(1.0, 1.0 - dz / (2.0 * radius))))
    footprint = 2.0 * radius * math.sin(theta)
    direction = _unit2((end[0] - start[0], end[1] - start[1]))
    if direction is None:
        return None
    return radius, z0, z1, footprint, theta, start, direction


def _transition_points(part, us):
    """3D points of the elevation S-curve at arc-length parameters ``us`` (mm)."""
    geometry = _transition_geometry(part)
    if geometry is None:
        return None
    radius, z0, z1, footprint, theta, start, direction = geometry
    sign = 1.0 if z1 >= z0 else -1.0
    dz = abs(z1 - z0)
    mid_u = radius * math.sin(theta)
    points = []
    for u in us:
        u = max(0.0, min(footprint, float(u)))
        if u <= mid_u + 1e-15:
            phi = math.asin(max(-1.0, min(1.0, u / radius)))
            z = z0 + sign * radius * (1.0 - math.cos(phi))
        else:
            mirror = footprint - u
            phi = math.asin(max(-1.0, min(1.0, mirror / radius)))
            z = z1 - sign * radius * (1.0 - math.cos(phi))
        points.append((start[0] + direction[0] * u,
                       start[1] + direction[1] * u,
                       z))
    return np.asarray(points, dtype=float)


def _point_segment_distance_3d(points, a, b):
    """Vectorised distance from ``(n,3)`` points to the 3D segment ``a-b``."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    direction = b - a
    denominator = float(np.dot(direction, direction))
    if denominator <= 1e-30:
        return np.linalg.norm(points - a, axis=1)
    t = (points - a) @ direction / denominator
    t = np.clip(t, 0.0, 1.0)
    closest = a[None, :] + t[:, None] * direction[None, :]
    return np.linalg.norm(points - closest, axis=1)


def _angle_in_sweep_array(angles, start, sweep):
    """Vectorised :func:`_angle_in_sweep`."""
    angles = np.asarray(angles, dtype=float)
    if abs(sweep) >= _TAU - 1e-12:
        return np.ones(angles.shape, dtype=bool)
    if sweep >= 0.0:
        delta = np.mod(angles - start, _TAU)
        return (delta <= sweep + 1e-12) | (delta >= _TAU - 1e-12)
    delta = np.mod(start - angles, _TAU)
    return (delta <= -sweep + 1e-12) | (delta >= _TAU - 1e-12)


def _point_flat_primitive_distances_3d(points, prim, z_mm):
    """Distance from ``(n,3)`` points to one *flat* primitive at height ``z_mm``.

    The flat part of a route may contain arcs (a planar U-turn bends on its own
    layer), so an arc is treated as its exact circle segment, never as a chord.
    """
    kind = _prim_kind(prim)
    p0, p1 = _prim_endpoints(prim)
    if kind == 'line':
        return _point_segment_distance_3d(points,
                                          (p0[0], p0[1], z_mm),
                                          (p1[0], p1[1], z_mm))
    if kind == 'arc':
        center = (float(prim['center'][0]), float(prim['center'][1]))
        radius = float(prim['radius'])
        sweep = float(prim['sweep'])
        start_angle = float(prim['start_angle'])
        relative = points[:, :2] - np.asarray(center, dtype=float)[None, :]
        radial = np.linalg.norm(relative, axis=1)
        angle = np.arctan2(relative[:, 1], relative[:, 0])
        on_arc = _angle_in_sweep_array(angle, start_angle, sweep)
        endpoint_distance = np.minimum(
            np.linalg.norm(points[:, :2] - np.asarray(p0)[None, :], axis=1),
            np.linalg.norm(points[:, :2] - np.asarray(p1)[None, :], axis=1))
        distance_2d = np.where(on_arc, np.abs(radial - radius), endpoint_distance)
        return np.hypot(distance_2d, points[:, 2] - float(z_mm))
    return np.full(len(points), np.inf)


def _transition_to_primitive_min(part, prim, z_mm, rounds=5):
    """Minimum 3D distance between one S-curve and one flat primitive.

    Coarse sampling followed by a shrinking local window makes the result
    accurate to well below 1e-3 mm without assuming anything about the router.
    """
    geometry = _transition_geometry(part)
    if geometry is None:
        return None
    footprint = geometry[3]
    count = 64
    us = np.linspace(0.0, footprint, count + 1)
    points = _transition_points(part, us)
    if points is None:
        return None
    distances = _point_flat_primitive_distances_3d(points, prim, z_mm)
    index = int(np.argmin(distances))
    best = float(distances[index])
    width = footprint / count
    centre = float(us[index])
    for _ in range(rounds):
        low = max(0.0, centre - 2.0 * width)
        high = min(footprint, centre + 2.0 * width)
        us = np.linspace(low, high, 65)
        points = _transition_points(part, us)
        distances = _point_flat_primitive_distances_3d(points, prim, z_mm)
        index = int(np.argmin(distances))
        best = float(distances[index])
        centre = float(us[index])
        width = (high - low) / 64.0
    return best


def _transition_to_segment_min(part, a, b, rounds=5):
    """Minimum 3D distance between one S-curve and the flat 3D segment ``a-b``."""
    geometry = _transition_geometry(part)
    if geometry is None:
        return None
    footprint = geometry[3]
    count = 64
    us = np.linspace(0.0, footprint, count + 1)
    points = _transition_points(part, us)
    if points is None:
        return None
    distances = _point_segment_distance_3d(points, a, b)
    index = int(np.argmin(distances))
    best = float(distances[index])
    width = footprint / count
    centre = float(us[index])
    for _ in range(rounds):
        low = max(0.0, centre - 2.0 * width)
        high = min(footprint, centre + 2.0 * width)
        us = np.linspace(low, high, 65)
        points = _transition_points(part, us)
        distances = _point_segment_distance_3d(points, a, b)
        index = int(np.argmin(distances))
        best = float(distances[index])
        centre = float(us[index])
        width = (high - low) / 64.0
    return best


def _transition_pair_min(part_a, part_b, rounds=5):
    """Minimum 3D distance between two S-curves (coarse + local refinement)."""
    geometry_a = _transition_geometry(part_a)
    geometry_b = _transition_geometry(part_b)
    if geometry_a is None or geometry_b is None:
        return None
    footprint_a, footprint_b = geometry_a[3], geometry_b[3]
    count = 32
    us_a = np.linspace(0.0, footprint_a, count + 1)
    us_b = np.linspace(0.0, footprint_b, count + 1)
    points_a = _transition_points(part_a, us_a)
    points_b = _transition_points(part_b, us_b)
    if points_a is None or points_b is None:
        return None
    matrix = np.linalg.norm(points_a[:, None, :] - points_b[None, :, :], axis=2)
    flat_index = int(np.argmin(matrix))
    index_a, index_b = divmod(flat_index, matrix.shape[1])
    best = float(matrix[index_a, index_b])
    width_a = footprint_a / count
    width_b = footprint_b / count
    centre_a = float(us_a[index_a])
    centre_b = float(us_b[index_b])
    for _ in range(rounds):
        low_a = max(0.0, centre_a - 2.0 * width_a)
        high_a = min(footprint_a, centre_a + 2.0 * width_a)
        low_b = max(0.0, centre_b - 2.0 * width_b)
        high_b = min(footprint_b, centre_b + 2.0 * width_b)
        us_a = np.linspace(low_a, high_a, 25)
        us_b = np.linspace(low_b, high_b, 25)
        points_a = _transition_points(part_a, us_a)
        points_b = _transition_points(part_b, us_b)
        matrix = np.linalg.norm(points_a[:, None, :] - points_b[None, :, :],
                                axis=2)
        flat_index = int(np.argmin(matrix))
        index_a, index_b = divmod(flat_index, matrix.shape[1])
        best = float(matrix[index_a, index_b])
        centre_a = float(us_a[index_a])
        centre_b = float(us_b[index_b])
        width_a = (high_a - low_a) / 24.0
        width_b = (high_b - low_b) / 24.0
    return best


def _flat_segment_3d(prim):
    """``((x0,y0,z), (x1,y1,z))`` placeholder: z is filled in by the caller."""
    p0, p1 = _prim_endpoints(prim)
    return (p0[0], p0[1], 0.0), (p1[0], p1[1], 0.0)


# ---------------------------------------------------------------------------
# pair distance for same-plane flat primitives (exact low-level primitive)
# ---------------------------------------------------------------------------
def _primitive_pair_distance_2d(first, second):
    """Exact centre-line distance of two D56 primitives (shared frozen math)."""
    try:
        from four_side_1024.conflicts import _make_primitive, _exact_distance
        return float(_exact_distance(_make_primitive(first), _make_primitive(second)))
    except Exception:  # pragma: no cover - numerical fallback
        points = _path_polyline([first, second], step=0.01)
        best = float('inf')
        for index in range(len(points) - 1):
            for jndex in range(index + 1, len(points) - 1):
                best = min(best, _dist2(points[index], points[jndex]))
        return best


def _path_polyline(prims, step=0.1):
    points = []
    for prim in prims:
        length = _prim_length(prim)
        count = max(1, int(math.ceil(length / step)))
        for index in range(count + 1):
            fraction = index / count
            if prim.get('kind') == 'line':
                p0, p1 = _prim_endpoints(prim)
                points.append((p0[0] + (p1[0] - p0[0]) * fraction,
                               p0[1] + (p1[1] - p0[1]) * fraction))
            else:
                center = prim['center']
                angle = (float(prim['start_angle'])
                         + float(prim['sweep']) * fraction)
                radius = float(prim['radius'])
                points.append((float(center[0]) + radius * math.cos(angle),
                               float(center[1]) + radius * math.sin(angle)))
    return points


# ---------------------------------------------------------------------------
# verification context
# ---------------------------------------------------------------------------
class _Context:
    def __init__(self, radius, clearance, log):
        self.radius = float(radius)
        self.clearance = float(clearance)
        self.log = log
        self.checks = OrderedDict()
        self.violations = []
        self.counts = Counter()
        self.routes = []
        self.by_uid = {}
        self.data = None
        self.stack = None
        self.records = []
        self.min_radius = None
        self.min_cross_angle = None
        self.min_clearance = None
        self.per_plane = OrderedDict()
        self.per_layer = OrderedDict()
        self.route_metrics = OrderedDict()
        self.crossings = OrderedDict(
            total=0, per_plane=OrderedDict(), per_layer=OrderedDict(),
            per_route=OrderedDict(), min_angle_deg=None, items=[])
        self.plane_conflict_pairs = []       # dicts route_a/route_b/z/kinds
        self.manual_u_uids = set()
        self.u_depth_table = []
        self.failed_routes = []
        self.discrepancies = []
        self.arc_count = 0
        self.primitive_count = 0
        self.radius_off_count = 0

    # -- bookkeeping -------------------------------------------------------
    def check(self, name, passed, detail=None):
        self.checks[str(name)] = dict(passed=bool(passed),
                                      detail=_json_safe(detail))
        return bool(passed)

    def violation(self, kind, **fields):
        item = dict(kind=str(kind))
        for key, value in fields.items():
            if value is not None:
                item[key] = value
        item = _json_safe(item)
        self.violations.append(item)
        self.counts[item['kind']] += 1
        return item

    def note_clearance(self, value):
        value = _f(value)
        if value is None:
            return
        if self.min_clearance is None or value < self.min_clearance:
            self.min_clearance = value

    def fail_count(self, kind):
        return self.counts.get(kind, 0)


# ---------------------------------------------------------------------------
# 1) record conservation / identity
# ---------------------------------------------------------------------------
_IDENTITY_FIELDS = (
    ('route_id', 'internal_id'),
    ('original_route_id', 'original_route_id'),
    ('dataset', 'dataset'),
    ('relation', 'relation'),
    ('source_side', 'source_side'),
    ('target_side', 'target_side'),
    ('source_port_id', 'source_port_id'),
    ('target_port_id', 'target_port_id'),
    ('source_endpoint_id', 'source_endpoint_id'),
    ('target_endpoint_id', 'target_endpoint_id'),
    ('assignment', 'assignment'),
)
_IDENTITY_COORDS = (
    ('source_xy_mm', 'source_xy'),
    ('target_xy_mm', 'target_xy'),
)
_IDENTITY_Z = (
    ('source_z_mm', 'source_z_mm'),
    ('target_z_mm', 'target_z_mm'),
)


def _check_records(ctx, routes, data):
    records = list(getattr(data, 'records', []) or [])
    ctx.records = records
    expected_uids = [record['uid'] for record in records]
    route_uids = [route.get('uid') for route in routes]
    uid_counter = Counter(route_uids)
    data_counter = Counter(expected_uids)

    duplicates = sorted([uid for uid, count in uid_counter.items() if count > 1],
                        key=str)
    missing = sorted((uid for uid in data_counter if uid not in uid_counter),
                     key=str)
    extra = sorted((uid for uid in uid_counter
                    if uid not in data_counter and uid is not None), key=str)

    expected_total = 640
    count_ok = (len(records) == expected_total
                and len(routes) == expected_total
                and len(set(route_uids)) == expected_total)
    ctx.check('record_count_640', count_ok, dict(
        expected=expected_total, records=len(records), routes=len(routes),
        unique_route_uids=len(set(route_uids))))

    ctx.check('record_conservation',
              len(routes) == len(records) and not duplicates
              and not missing and not extra and not any(uid is None for uid in route_uids),
              dict(expected_records=len(records), routes=len(routes),
                   duplicate_uids=duplicates[:10], missing_uids=missing[:10],
                   extra_uids=extra[:10]))

    # input model itself must be the validated 640-record model
    validation = getattr(data, 'validation', {}) or {}
    ctx.check('input_model_valid',
              bool(validation.get('passed', False)),
              dict(failed_checks=validation.get('failed_checks'),
                   total_records=validation.get('total_records'),
                   sha256=getattr(data, 'sha256', None)))

    by_uid = {}
    for route in routes:
        uid = route.get('uid')
        if uid is not None and uid not in by_uid:
            by_uid[uid] = route
    ctx.by_uid = by_uid

    # -- per-record identity ----------------------------------------------
    errors = []
    for record in records:
        uid = record['uid']
        route = by_uid.get(uid)
        if route is None:
            errors.append(dict(uid=uid, field='route', reason='missing_route'))
            continue
        for field, record_key in _IDENTITY_FIELDS:
            actual = route.get(field)
            expected = record.get(record_key)
            if actual is None:
                errors.append(dict(uid=uid, field=field, reason='missing'))
            elif actual != expected:
                errors.append(dict(uid=uid, field=field, reason='mismatch',
                                   actual=actual, expected=expected))
        for field, record_key in _IDENTITY_COORDS:
            actual = route.get(field)
            if actual is None:
                source = route.get('source_port' if field.startswith('source') else 'target_port')
                if isinstance(source, dict):
                    actual = source.get('xy')
            expected = record.get(record_key)
            if actual is None or expected is None:
                errors.append(dict(uid=uid, field=field, reason='missing'))
                continue
            if (abs(float(actual[0]) - float(expected[0])) > TOL_COORD
                    or abs(float(actual[1]) - float(expected[1])) > TOL_COORD):
                errors.append(dict(uid=uid, field=field, reason='mismatch',
                                   actual=[float(actual[0]), float(actual[1])],
                                   expected=[float(expected[0]),
                                             float(expected[1])]))
        for field, record_key in _IDENTITY_Z:
            actual = _f(route.get(field))
            expected = _f(record.get(record_key))
            if actual is None or expected is None:
                errors.append(dict(uid=uid, field=field, reason='missing'))
            elif abs(actual - expected) > TOL_COORD:
                errors.append(dict(uid=uid, field=field, reason='mismatch',
                                   actual=actual, expected=expected))
        for field, record_key in (('csv_source_row', 'csv_source_row'),
                                  ('csv_target_row', 'csv_target_row'),
                                  ('physical_source_row', 'source_row'),
                                  ('physical_target_row', 'target_row')):
            if field in route:
                actual = route.get(field)
                expected = record.get(record_key)
                if expected is not None and actual != expected:
                    errors.append(dict(uid=uid, field=field, reason='mismatch',
                                       actual=actual, expected=expected))
    for item in errors:
        ctx.violation('record_identity_mismatch', **item)
    ctx.check('record_identity', not errors, dict(
        records=len(records), checked_fields=[name for name, _ in _IDENTITY_FIELDS],
        errors=len(errors), examples=errors[:10]))

    # relation / side must not be rewritten (already covered by identity, but the
    # task asks for an explicit check)
    relation_errors = []
    for record in records:
        route = by_uid.get(record['uid'])
        if route is None:
            continue
        sides = {record['source_side'], record['target_side']}
        relation = record['relation']
        if relation == 'same':
            ok = record['source_side'] == record['target_side']
        elif relation == 'opposite':
            ok = sides in ({'N', 'S'}, {'E', 'W'})
        elif relation == 'adjacent':
            ok = len(sides) == 2 and sides not in ({'N', 'S'}, {'E', 'W'})
        else:
            ok = False
        if (not ok or route.get('relation') != relation
                or route.get('source_side') != record['source_side']
                or route.get('target_side') != record['target_side']):
            relation_errors.append(record['uid'])
    ctx.check('relation_sides_unchanged', not relation_errors,
              dict(errors=len(relation_errors), examples=relation_errors[:10]))


# ---------------------------------------------------------------------------
# 2) port occupancy
# ---------------------------------------------------------------------------
def _endpoint_id(record, which):
    return record.get(f'{which}_endpoint_id')


def _check_ports(ctx, routes, data):
    records = ctx.records
    datasets = sorted({record['dataset'] for record in records})
    expected = OrderedDict()
    for dataset in datasets:
        ports = []
        for record in records:
            if record['dataset'] != dataset:
                continue
            ports.extend([_endpoint_id(record, 'source'),
                          _endpoint_id(record, 'target')])
        expected[dataset] = ports

    checks_passed = True
    detail = OrderedDict()
    for dataset in datasets:
        expected_ports = expected[dataset]
        expected_set = set(expected_ports)
        used = []
        used_map = defaultdict(list)
        for route in routes:
            if route.get('dataset') != dataset:
                continue
            for which in ('source', 'target'):
                endpoint = route.get(f'{which}_endpoint_id')
                if endpoint is None:
                    port = route.get(f'{which}_port')
                    endpoint = port.get('endpoint_id') if isinstance(port, dict) else None
                if endpoint is None:
                    continue
                used.append(endpoint)
                used_map[endpoint].append(route.get('uid'))
        duplicates = {port: uids for port, uids in used_map.items()
                      if len(uids) > 1}
        missing = sorted(expected_set - set(used))
        extra = sorted(set(used) - expected_set)
        expected_count = len(expected_ports)
        physical_rows = sorted({int(record['source_row']) for record in records
                                if record['dataset'] == dataset})
        physical_z = sorted({float(record['source_z_mm']) for record in records
                             if record['dataset'] == dataset})
        passed = (not duplicates and not missing and not extra
                  and len(used) == expected_count and len(used_set := set(used)) == expected_count)
        checks_passed = checks_passed and passed
        if not passed:
            for port, uids in list(duplicates.items())[:20]:
                ctx.violation('port_used_more_than_once', dataset=dataset,
                              endpoint_id=port, uids=uids)
            for port in missing[:20]:
                ctx.violation('port_unused', dataset=dataset, endpoint_id=port)
            for port in extra[:20]:
                ctx.violation('unknown_port_used', dataset=dataset,
                              endpoint_id=port)
        detail[dataset] = dict(
            expected_ports=expected_count, used_ports=len(used),
            unique_used_ports=len(set(used)), duplicates=len(duplicates),
            missing=len(missing), extra=len(extra),
            physical_rows=physical_rows, physical_z_mm=physical_z,
            duplicate_examples={port: uids[:4]
                                for port, uids in list(duplicates.items())[:5]},
            missing_examples=missing[:5], extra_examples=extra[:5])
        ctx.check(f'port_occupancy_{dataset}', passed, detail[dataset])
    # the task's fixed port budgets
    ctx.check('port_occupancy_1024_256',
              detail.get('z1', {}).get('expected_ports') == 1024
              and detail.get('z2', {}).get('expected_ports') == 256,
              {key: value.get('expected_ports') for key, value in detail.items()})
    ctx.check('port_occupancy', checks_passed, detail)

    # -- cross dataset identical XY port pairs (never merged!) -------------
    # The CSV marks 24 records (12 z1 + 12 z2): the SAME two physical ports in
    # the two interface rows, connected in opposite directions.  They are
    # physically distinct ports (z = 0.0 mm vs 0.5 mm) and must not be merged.
    flagged = [record for record in records
               if str(record.get('cross_dataset_same_port_pair', '')).strip().upper()
               in ('YES', 'TRUE', '1')]
    groups = OrderedDict()
    for record in flagged:
        key = tuple(sorted([
            (tuple(round(float(v), 9) for v in record['source_xy']),
             record['source_port_id']),
            (tuple(round(float(v), 9) for v in record['target_xy']),
             record['target_port_id']),
        ]))
        groups.setdefault(key, []).append(record)
    pairs = []
    consistent = len(flagged) == 24 and len(groups) == 12
    for key, items in groups.items():
        datasets = sorted(item['dataset'] for item in items)
        heights = [float(item['source_z_mm']) for item in items]
        z_ok = all(abs(height - (0.0 if dataset == 'z1' else 0.5)) <= 1e-9
                   for dataset, height in zip(datasets, heights))
        pair_ok = datasets == ['z1', 'z2'] and z_ok
        consistent = consistent and pair_ok
        pairs.append(dict(
            endpoint_ids=[key[0][1], key[1][1]],
            endpoint_xy=[list(key[0][0]), list(key[1][0])],
            ports=[dict(uid=item['uid'], dataset=item['dataset'],
                        source_port_id=item['source_port_id'],
                        target_port_id=item['target_port_id'],
                        source_z_mm=float(item['source_z_mm']),
                        target_z_mm=float(item['target_z_mm']))
                   for item in items],
            physical_planes_distinct=z_ok,
            conflict=False,
            note=('the same two physical port columns are used in interface row '
                  '1 (z=0.0 mm) and row 2 (z=0.5 mm); the ports are physically '
                  'distinct, the records are never merged, and this is not a '
                  'conflict')))
    ctx.check('cross_dataset_same_port_pairs', consistent, dict(
        flagged_records=len(flagged), xy_pairs=len(groups),
        expected_flagged=24, expected_pairs=12,
        z1_records=sum(1 for item in flagged if item['dataset'] == 'z1'),
        z2_records=sum(1 for item in flagged if item['dataset'] == 'z2'),
        physical_note='z1 rows at z=0.0 mm, z2 rows at z=0.5 mm; identical XY '
                      'columns are distinct ports and are never merged',
        pairs=pairs))


# ---------------------------------------------------------------------------
# 3) layer assignment
# ---------------------------------------------------------------------------
_MANUAL_LAYER_COUNTS = {1: 64, 2: 64, 3: 64, 4: 64, 5: 13, 6: 15}
_AUTO_TOTAL = 356


def _check_layers(ctx, routes, data, stack):
    by_uid = ctx.by_uid
    max_layer = int(getattr(stack, 'max_layer', C.MAX_LOGICAL_LAYERS))
    manual_groups = getattr(data, 'manual_groups', {}) or {}
    auto_groups = getattr(data, 'auto_groups', {}) or {}

    # -- input group counts -------------------------------------------------
    manual_counts = OrderedDict((int(layer), len(manual_groups.get(layer, [])))
                                for layer in C.MANUAL_LAYER_IDS)
    expected_manual = OrderedDict((layer, _MANUAL_LAYER_COUNTS[layer])
                                  for layer in C.MANUAL_LAYER_IDS)
    ctx.check('manual_layer_counts', manual_counts == expected_manual,
              dict(expected=dict(expected_manual), actual=dict(manual_counts)))
    auto_counts = OrderedDict((str(key), len(value))
                              for key, value in auto_groups.items())
    ctx.check('auto_group_counts',
              auto_counts.get('z1_opposite_NS') == 128
              and auto_counts.get('z1_opposite_EW') == 128
              and auto_counts.get('z2_adjacent') == 100
              and sum(auto_counts.values()) == _AUTO_TOTAL,
              dict(actual=dict(auto_counts), expected=_AUTO_TOTAL))
    ctx.check('manual_total_284',
              sum(manual_counts.values()) == 284, sum(manual_counts.values()))
    ctx.check('record_partition',
              sum(manual_counts.values()) + sum(auto_counts.values())
              == len(ctx.records),
              dict(manual=sum(manual_counts.values()),
                   automatic=sum(auto_counts.values()),
                   records=len(ctx.records)))

    # -- manual L1..L6 assignment ------------------------------------------
    manual_violations = []
    manual_failures = []
    layer_detail = OrderedDict()
    for layer_id in sorted(int(layer) for layer in manual_groups):
        uids = manual_groups.get(layer_id, [])
        found = 0
        routed = 0
        for uid in uids:
            route = by_uid.get(uid)
            record = next((item for item in ctx.records if item['uid'] == uid),
                          None)
            expected_layer = (record or {}).get('assigned_layer')
            if route is None:
                manual_violations.append(dict(uid=uid, reason='missing_route',
                                              expected_layer=layer_id))
                continue
            found += 1
            actual_layer = route.get('logical_layer')
            failed_route = _is_failed(route)
            if expected_layer is not None and actual_layer is not None \
                    and actual_layer != int(expected_layer):
                manual_violations.append(dict(
                    uid=uid, reason='logical_layer_mismatch',
                    logical_layer=actual_layer, expected_layer=int(expected_layer)))
            if actual_layer is None and not failed_route:
                manual_violations.append(dict(
                    uid=uid, reason='missing_logical_layer',
                    expected_layer=int(layer_id)))
            if actual_layer is not None and int(layer_id) in _MANUAL_LAYER_COUNTS \
                    and actual_layer != int(layer_id):
                manual_violations.append(dict(
                    uid=uid, reason='layer_not_from_csv_assignment',
                    logical_layer=actual_layer, expected_layer=int(layer_id)))
            if failed_route:
                manual_failures.append(dict(
                    uid=uid, logical_layer=actual_layer,
                    failure_reason=route.get('failure_reason')))
            else:
                routed += 1
        layer_detail[int(layer_id)] = dict(
            expected=_MANUAL_LAYER_COUNTS.get(int(layer_id)),
            records=len(uids), found=found, routed=routed,
            failed=len(uids) - routed)
    for item in manual_violations:
        ctx.violation('manual_layer_mismatch', **item)
    for item in manual_failures:
        ctx.violation('manual_route_failed', **item)
    ctx.check('manual_layer_assignment', not manual_violations,
              dict(errors=len(manual_violations),
                   examples=manual_violations[:10], layers=dict(layer_detail)))
    ctx.check('manual_all_routed', not manual_failures,
              dict(failed=len(manual_failures), examples=manual_failures[:10]))

    # -- automatic L7+ assignment ------------------------------------------
    auto_violations = []
    auto_failures = []
    auto_total = 0
    for key, uids in auto_groups.items():
        for uid in uids:
            auto_total += 1
            route = by_uid.get(uid)
            if route is None:
                auto_violations.append(dict(uid=uid, reason='missing_route'))
                continue
            layer = route.get('logical_layer')
            failed_route = _is_failed(route)
            if layer is None:
                # a failed record legitimately has no assigned layer; the
                # failure itself is reported by the auto_route_failed check
                if not failed_route:
                    auto_violations.append(dict(uid=uid,
                                                reason='missing_logical_layer'))
            elif not (int(C.FIRST_AUTO_LAYER_ID) <= int(layer) <= max_layer):
                auto_violations.append(dict(uid=uid, reason='layer_below_L7',
                                            logical_layer=layer))
            if failed_route:
                auto_failures.append(dict(
                    uid=uid, logical_layer=layer,
                    failure_reason=route.get('failure_reason')))
    for item in auto_violations:
        ctx.violation('auto_layer_mismatch', **item)
    for item in auto_failures:
        ctx.violation('auto_route_failed', **item)
    ctx.check('auto_layer_assignment', not auto_violations,
              dict(records=auto_total, errors=len(auto_violations),
                   examples=auto_violations[:10],
                   first_auto_layer=int(C.FIRST_AUTO_LAYER_ID)))
    ctx.check('auto_all_routed', not auto_failures,
              dict(records=auto_total, failed=len(auto_failures),
                   examples=auto_failures[:10]))

    # -- every record accounted for ----------------------------------------
    covered = [route.get('uid') for route in routes]
    ctx.check('every_record_has_route', len(set(covered)) == len(ctx.records),
              dict(records=len(ctx.records), unique_routes=len(set(covered))))


# ---------------------------------------------------------------------------
# 4) single-route geometry / structure
# ---------------------------------------------------------------------------
def _check_chain(ctx, uid, chain, source):
    """Primitive-level checks of one XY chain; returns per-chain statistics."""
    stats = dict(min_radius=None, arcs=0, prims=len(chain), chain_length=0.0,
                 errors=0)
    if not chain:
        ctx.violation('missing_xy_chain', uid=uid, source=source)
        stats['errors'] += 1
        return stats
    tangents = []
    lengths = []
    for index, prim in enumerate(chain):
        kind = _prim_kind(prim)
        ctx.primitive_count += 1
        if kind is None:
            ctx.violation('invalid_primitive', uid=uid, index=index,
                          reason='kind_must_be_line_or_arc',
                          kind=prim.get('kind') if isinstance(prim, dict) else None)
            stats['errors'] += 1
            tangents.append(None)
            lengths.append(0.0)
            continue
        try:
            p0, p1 = _prim_endpoints(prim)
            for value in (*p0, *p1):
                if not math.isfinite(value):
                    raise ValueError('non-finite endpoint')
        except (TypeError, ValueError, IndexError):
            ctx.violation('invalid_primitive', uid=uid, index=index,
                          reason='non_finite_or_missing_endpoint')
            stats['errors'] += 1
            tangents.append(None)
            lengths.append(0.0)
            continue
        length = 0.0
        try:
            length = _prim_length(prim)
        except (TypeError, ValueError, KeyError):
            ctx.violation('invalid_primitive', uid=uid, index=index,
                          reason='non_finite_length')
            stats['errors'] += 1
        if kind == 'line':
            dx = abs(p1[0] - p0[0])
            dy = abs(p1[1] - p0[1])
            if min(dx, dy) > TOL_XY:
                ctx.violation('diagonal_line', uid=uid, index=index,
                              p0=list(p0), p1=list(p1),
                              reason='D56 lines must be axis aligned')
                stats['errors'] += 1
            if length <= 1e-12:
                ctx.violation('zero_length_line', uid=uid, index=index)
                stats['errors'] += 1
        else:
            stats['arcs'] += 1
            ctx.arc_count += 1
            radius = _f(prim.get('radius'))
            sweep = _f(prim.get('sweep'))
            center = prim.get('center')
            start_angle = _f(prim.get('start_angle'))
            if radius is None or sweep is None or center is None \
                    or start_angle is None:
                ctx.violation('invalid_arc', uid=uid, index=index,
                              reason='missing_or_non_finite_parameters')
                stats['errors'] += 1
            else:
                if stats['min_radius'] is None or radius < stats['min_radius']:
                    stats['min_radius'] = radius
                if ctx.min_radius is None or radius < ctx.min_radius:
                    ctx.min_radius = radius
                if radius < ctx.radius - TOL_RADIUS_MM:
                    ctx.violation('arc_radius_below_min', uid=uid, index=index,
                                  radius_mm=radius,
                                  required_radius_mm=ctx.radius)
                    stats['errors'] += 1
                if abs(radius - ctx.radius) > 1e-6 * max(1.0, ctx.radius):
                    ctx.radius_off_count += 1
                if sweep == 0.0 or abs(sweep) > _TAU + 1e-6:
                    ctx.violation('invalid_arc', uid=uid, index=index,
                                  reason='sweep_out_of_range', sweep=sweep)
                    stats['errors'] += 1
                cx, cy = float(center[0]), float(center[1])
                for point, angle in ((p0, start_angle),
                                     (p1, start_angle + sweep)):
                    expected = (cx + radius * math.cos(angle),
                                cy + radius * math.sin(angle))
                    if _dist2(point, expected) > 1e-6:
                        ctx.violation('inconsistent_arc', uid=uid, index=index,
                                      endpoint=list(point),
                                      reconstructed=list(expected))
                        stats['errors'] += 1
        # board bounds including half the waveguide width
        try:
            box = _prim_stroked_extents(prim, HALF_WIDTH)
            if (box[0] < -TOL_BOARD or box[1] < -TOL_BOARD
                    or box[2] > BOARD + TOL_BOARD or box[3] > BOARD + TOL_BOARD):
                ctx.violation('board_out_of_bounds', uid=uid, index=index,
                              stroked_bounds=[round(value, 9) for value in box],
                              board=[BOARD, BOARD])
                stats['errors'] += 1
        except (TypeError, ValueError, KeyError):
            ctx.violation('board_bounds_undefined', uid=uid, index=index)
            stats['errors'] += 1
        tangents.append(_prim_tangent(prim, False))
        lengths.append(length)

    stats['chain_length'] = float(sum(lengths))
    # position / tangent continuity
    for index in range(1, len(chain)):
        try:
            prev_p0, prev_p1 = _prim_endpoints(chain[index - 1])
            cur_p0, _cur_p1 = _prim_endpoints(chain[index])
        except (TypeError, ValueError, IndexError):
            continue
        gap = _dist2(prev_p1, cur_p0)
        if gap > TOL_XY:
            ctx.violation('position_discontinuity', uid=uid, index=index,
                          gap_mm=gap, tolerance_mm=TOL_XY)
            stats['errors'] += 1
        start_tangent = _prim_tangent(chain[index - 1], True)
        end_tangent = _prim_tangent(chain[index], False)
        if start_tangent is not None and end_tangent is not None:
            angle = _angle_deg(start_tangent, end_tangent)
            if angle is not None and angle > TOL_ANGLE_DEG:
                ctx.violation('tangent_discontinuity', uid=uid, index=index,
                              angle_error_deg=angle,
                              tolerance_deg=TOL_ANGLE_DEG)
                stats['errors'] += 1
    return stats


def _check_route_pose(ctx, uid, route, record):
    plane = record['dataset']
    try:
        chain, chain_source = _route_xy_chain(route)
    except (TypeError, ValueError, KeyError) as error:  # pragma: no cover
        ctx.violation('invalid_xy_chain', uid=uid, reason=str(error))
        return None
    chain_stats = _check_chain(ctx, uid, chain, chain_source)

    # fixed ports (never moved) and in/out directions
    try:
        chain_start = (float(chain[0]['p0'][0]), float(chain[0]['p0'][1]))
        chain_end = (float(chain[-1]['p1'][0]), float(chain[-1]['p1'][1]))
    except (KeyError, TypeError, ValueError, IndexError):
        chain_start = chain_end = None
    source_xy = record['source_xy']
    target_xy = record['target_xy']
    if chain_start is None or chain_end is None:
        ctx.violation('route_endpoint_missing', uid=uid)
    else:
        start_error = _dist2(chain_start, source_xy)
        end_error = _dist2(chain_end, target_xy)
        if start_error > TOL_POS_CSV:
            ctx.violation('route_endpoint_mismatch', uid=uid, which='source',
                          xy=list(chain_start), csv_xy=list(source_xy),
                          error_mm=start_error)
        if end_error > TOL_POS_CSV:
            ctx.violation('route_endpoint_mismatch', uid=uid, which='target',
                          xy=list(chain_end), csv_xy=list(target_xy),
                          error_mm=end_error)
        start_tangent = _prim_tangent(chain[0], False)
        end_tangent = _prim_tangent(chain[-1], True)
        inward = record['source_endpoint']['inward']
        target_inward = record['target_endpoint']['inward']
        expected_start = (float(inward[0]), float(inward[1]))
        expected_end = (-float(target_inward[0]), -float(target_inward[1]))
        for label, actual, expected in (('start', start_tangent, expected_start),
                                        ('end', end_tangent, expected_end)):
            if actual is None:
                continue
            angle = _angle_deg(actual, expected)
            if angle is not None and angle > 1e-3:
                ctx.violation('route_port_direction_error', uid=uid,
                              which=label, angle_error_deg=angle,
                              expected=list(expected), actual=list(actual))
    return chain, chain_stats


def _check_route_structure(ctx, uid, route, record, chain, chain_stats):
    plane = record['dataset']
    parts = _parts(route)
    logical_layer = route.get('logical_layer')
    errors = 0
    if not parts:
        ctx.violation('missing_parts', uid=uid)
        return
    for index, part in enumerate(parts):
        if not isinstance(part, dict):
            ctx.violation('invalid_part', uid=uid, index=index,
                          reason='not_a_dict')
            errors += 1
            continue
        kind = part.get('kind')
        if kind not in ('flat', 'transition'):
            ctx.violation('invalid_part', uid=uid, index=index,
                          reason='unknown_kind', kind=kind)
            errors += 1
    kinds = [part.get('kind') if isinstance(part, dict) else None
             for part in parts]
    if kinds and kinds[0] != 'flat':
        ctx.violation('route_structure', uid=uid,
                      reason='route_must_start_with_flat', kinds=kinds[:8])
        errors += 1
    if kinds and kinds[-1] != 'flat':
        ctx.violation('route_structure', uid=uid,
                      reason='route_must_end_with_flat', kinds=kinds[:8])
        errors += 1
    for index in range(1, len(kinds)):
        if kinds[index] == kinds[index - 1]:
            ctx.violation('route_structure', uid=uid,
                          reason='flat_and_transition_must_alternate',
                          index=index, kinds=kinds[:8])
            errors += 1

    # -- flat parts --------------------------------------------------------
    flat_layers = []
    flat_heights = []
    flat_length_total = 0.0
    for index, part in enumerate(parts):
        if not isinstance(part, dict) or part.get('kind') != 'flat':
            continue
        primitives = part.get('primitives') or []
        if not primitives:
            ctx.violation('empty_flat_part', uid=uid, index=index)
            errors += 1
            continue
        layer_id = part.get('layer_id')
        z_mm = _f(part.get('z_mm'))
        try:
            layer_id = int(layer_id)
        except (TypeError, ValueError):
            ctx.violation('flat_part_layer_invalid', uid=uid, index=index,
                          layer_id=layer_id)
            errors += 1
            continue
        if not (1 <= layer_id <= int(getattr(ctx.stack, 'max_layer',
                                             C.MAX_LOGICAL_LAYERS))):
            ctx.violation('flat_part_layer_out_of_stack', uid=uid, index=index,
                          layer_id=layer_id)
            errors += 1
            continue
        if z_mm is None:
            ctx.violation('flat_part_height_invalid', uid=uid, index=index)
            errors += 1
            continue
        expected_z = _expected_z(layer_id, plane)
        if abs(z_mm - expected_z) > TOL_Z:
            ctx.violation('flat_part_height_mismatch', uid=uid, index=index,
                          layer_id=layer_id, z_mm=z_mm,
                          expected_z_mm=expected_z)
            errors += 1
        if logical_layer is not None:
            allowed = {int(C.INTERFACE_LAYER_ID), int(logical_layer)}
            if layer_id not in allowed:
                ctx.violation('flat_layer_not_in_route_layers', uid=uid,
                              index=index, layer_id=layer_id,
                              logical_layer=logical_layer)
                errors += 1
        part_length = _f(part.get('length_mm'))
        actual_length = _chain_length([dict(prim) for prim in primitives
                                       if isinstance(prim, dict)])
        flat_length_total += actual_length
        if part_length is None or abs(part_length - actual_length) > TOL_STRUCT_REL \
                * max(1.0, actual_length):
            ctx.violation('flat_part_length_mismatch', uid=uid, index=index,
                          recorded_mm=part_length, computed_mm=actual_length)
            errors += 1
        flat_layers.append(layer_id)
        flat_heights.append(z_mm)

    # -- transitions -------------------------------------------------------
    transition_count = 0
    previous_flat = None
    transition_geometry_total = 0.0
    for index, part in enumerate(parts):
        if not isinstance(part, dict):
            continue
        if part.get('kind') == 'flat':
            previous_flat = part
            continue
        if part.get('kind') != 'transition':
            continue
        transition_count += 1
        geometry = _transition_geometry(part)
        if geometry is None:
            ctx.violation('invalid_transition', uid=uid, index=index,
                          reason='missing_or_non_finite_parameters')
            errors += 1
            previous_flat = None
            continue
        radius, z0, z1, footprint, theta, start, direction = geometry
        transition_geometry_total += footprint
        if radius < ctx.radius - TOL_RADIUS_MM:
            ctx.violation('transition_radius_below_min', uid=uid, index=index,
                          radius_mm=radius)
            errors += 1
        recorded_radius = _f(part.get('radius_mm'))
        if recorded_radius is None or abs(recorded_radius - radius) > TOL_STRUCT_REL:
            ctx.violation('transition_radius_inconsistent', uid=uid, index=index,
                          recorded_mm=recorded_radius, computed_mm=radius)
            errors += 1
        recorded_footprint = _f(part.get('footprint_mm'))
        if recorded_footprint is None or abs(recorded_footprint - footprint) > 1e-6:
            ctx.violation('transition_footprint_inconsistent', uid=uid,
                          index=index, recorded_mm=recorded_footprint,
                          computed_mm=footprint)
            errors += 1
        recorded_theta = _f(part.get('theta_rad'))
        if recorded_theta is None or abs(recorded_theta - theta) > 1e-9:
            ctx.violation('transition_theta_inconsistent', uid=uid, index=index,
                          recorded=recorded_theta, computed=theta)
            errors += 1
        recorded_length = _f(part.get('length_mm'))
        computed_length = 2.0 * radius * theta
        if recorded_length is None or abs(recorded_length - computed_length) \
                > TOL_STRUCT_REL * max(1.0, computed_length):
            ctx.violation('transition_length_inconsistent', uid=uid, index=index,
                          recorded_mm=recorded_length,
                          computed_mm=computed_length)
            errors += 1
        if abs(z1 - z0) <= TOL_Z:
            ctx.violation('transition_with_zero_height_change', uid=uid,
                          index=index, z0=z0, z1=z1)
            errors += 1
        # join with the previous flat
        if previous_flat is not None:
            previous_z = _f(previous_flat.get('z_mm'))
            if previous_z is not None and abs(previous_z - z0) > TOL_Z:
                ctx.violation('transition_join_height_mismatch', uid=uid,
                              index=index, side='start', flat_z_mm=previous_z,
                              transition_z_mm=z0)
                errors += 1
            previous_primitives = previous_flat.get('primitives') or []
            if previous_primitives:
                try:
                    flat_end = previous_primitives[-1]['p1']
                    if _dist2(flat_end, start) > TOL_XY:
                        ctx.violation('transition_join_position_mismatch',
                                      uid=uid, index=index, side='start',
                                      gap_mm=_dist2(flat_end, start))
                        errors += 1
                except (KeyError, TypeError, ValueError):
                    pass
        else:
            ctx.violation('route_structure', uid=uid,
                          reason='transition_not_after_flat', index=index)
            errors += 1
        # join with the next flat
        next_flat = None
        for following in parts[index + 1:]:
            if isinstance(following, dict) and following.get('kind') == 'flat':
                next_flat = following
                break
            if isinstance(following, dict) and following.get('kind') == 'transition':
                break
        if next_flat is None:
            ctx.violation('route_structure', uid=uid,
                          reason='transition_not_followed_by_flat', index=index)
            errors += 1
        else:
            next_z = _f(next_flat.get('z_mm'))
            if next_z is not None and abs(next_z - z1) > TOL_Z:
                ctx.violation('transition_join_height_mismatch', uid=uid,
                              index=index, side='end', flat_z_mm=next_z,
                              transition_z_mm=z1)
                errors += 1
            next_primitives = next_flat.get('primitives') or []
            if next_primitives:
                try:
                    flat_start = next_primitives[0]['p0']
                    end = part.get('end')
                    if _dist2(flat_start, end) > TOL_XY:
                        ctx.violation('transition_join_position_mismatch',
                                      uid=uid, index=index, side='end',
                                      gap_mm=_dist2(flat_start, end))
                        errors += 1
                except (KeyError, TypeError, ValueError):
                    pass
        previous_flat = None

    # -- route level structural consistency -------------------------------
    layer_sequence = route.get('layer_sequence')
    layer_z_sequence = route.get('layer_z_sequence')
    if not isinstance(layer_sequence, list):
        ctx.violation('route_structure', uid=uid,
                      reason='layer_sequence_missing')
        errors += 1
    else:
        if [int(value) for value in layer_sequence] != flat_layers:
            ctx.violation('route_structure', uid=uid,
                          reason='layer_sequence_vs_flat_parts',
                          layer_sequence=list(layer_sequence),
                          flat_layers=flat_layers)
            errors += 1
        if isinstance(layer_z_sequence, list) and len(layer_z_sequence) == len(flat_heights):
            for index, (recorded_z, flat_z) in enumerate(
                    zip(layer_z_sequence, flat_heights)):
                recorded_z = _f(recorded_z)
                if recorded_z is None or abs(recorded_z - flat_z) > TOL_Z:
                    ctx.violation('route_structure', uid=uid,
                                  reason='layer_z_sequence_vs_flat_parts',
                                  index=index, recorded_z=recorded_z,
                                  flat_z=flat_z)
                    errors += 1
        elif layer_z_sequence is not None:
            ctx.violation('route_structure', uid=uid,
                          reason='layer_z_sequence_length',
                          layer_z_sequence=layer_z_sequence,
                          flat_heights=flat_heights)
            errors += 1
        recorded_sequence = [int(value) for value in layer_sequence]
        if recorded_sequence:
            if recorded_sequence[0] != int(C.INTERFACE_LAYER_ID) \
                    or recorded_sequence[-1] != int(C.INTERFACE_LAYER_ID):
                ctx.violation('route_structure', uid=uid,
                              reason='route_must_start_end_on_L1',
                              layer_sequence=recorded_sequence)
                errors += 1
    recorded_n = route.get('n_transitions')
    if recorded_n is not None and int(recorded_n) != transition_count:
        ctx.violation('route_structure', uid=uid,
                      reason='n_transitions_mismatch',
                      recorded=int(recorded_n), computed=transition_count)
        errors += 1
    recorded_lifted = route.get('lifted')
    if recorded_lifted is not None and bool(recorded_lifted) != bool(
            len(flat_layers) > 1):
        ctx.violation('route_structure', uid=uid, reason='lifted_flag_mismatch',
                      recorded=bool(recorded_lifted),
                      computed=len(flat_layers) > 1)
        errors += 1

    # lengths / heights
    recorded_length = _f(route.get('length_mm'))
    computed_length = sum(_f(part.get('length_mm')) or 0.0
                          for part in parts if isinstance(part, dict))
    if recorded_length is None:
        ctx.violation('route_structure', uid=uid, reason='length_missing')
        errors += 1
    elif abs(recorded_length - computed_length) > TOL_STRUCT_REL \
            * max(1.0, computed_length):
        ctx.violation('route_structure', uid=uid, reason='length_mismatch',
                      recorded_mm=recorded_length, computed_mm=computed_length)
        errors += 1
    recorded_xy_length = _f(route.get('xy_length_mm'))
    computed_xy_length = flat_length_total + transition_geometry_total
    if recorded_xy_length is None:
        ctx.violation('route_structure', uid=uid, reason='xy_length_missing')
        errors += 1
    elif chain is not None:
        chain_length = chain_stats['chain_length'] if chain_stats else None
        reference = chain_length if chain_length else computed_xy_length
        if abs(recorded_xy_length - reference) > 1e-6 * max(1.0, reference):
            ctx.violation('route_structure', uid=uid,
                          reason='xy_length_vs_chain_length',
                          recorded_mm=recorded_xy_length,
                          chain_mm=chain_length,
                          parts_mm=computed_xy_length)
            errors += 1
    source_z = _f(record.get('source_z_mm'))
    target_z = _f(record.get('target_z_mm'))
    if flat_heights:
        if source_z is not None and abs(flat_heights[0] - source_z) > TOL_Z:
            ctx.violation('route_structure', uid=uid,
                          reason='start_z_vs_source_port',
                          start_flat_z=flat_heights[0], source_z_mm=source_z)
            errors += 1
        if target_z is not None and abs(flat_heights[-1] - target_z) > TOL_Z:
            ctx.violation('route_structure', uid=uid,
                          reason='end_z_vs_target_port',
                          end_flat_z=flat_heights[-1], target_z_mm=target_z)
            errors += 1
        span = _f(route.get('z_span_mm'))
        if span is not None and abs(span - (max(flat_heights) - min(flat_heights))) \
                > TOL_STRUCT_REL * max(1.0, span):
            ctx.violation('route_structure', uid=uid,
                          reason='z_span_mismatch', recorded_mm=span,
                          flat_mm=max(flat_heights) - min(flat_heights))
            errors += 1
    start_z = _f(route.get('start_z_mm'))
    end_z = _f(route.get('end_z_mm'))
    if start_z is None or abs(start_z - (source_z if source_z is not None else 0.0)) > TOL_Z:
        ctx.violation('route_structure', uid=uid, reason='start_z_mismatch',
                      recorded=start_z, expected=source_z)
        errors += 1
    if end_z is None or abs(end_z - (target_z if target_z is not None else 0.0)) > TOL_Z:
        ctx.violation('route_structure', uid=uid, reason='end_z_mismatch',
                      recorded=end_z, expected=target_z)
        errors += 1
    if route.get('plane') is not None and route.get('plane') != plane:
        ctx.violation('route_structure', uid=uid, reason='plane_mismatch',
                      recorded=route.get('plane'), expected=plane)
        errors += 1
    if route.get('source_row') is not None \
            and int(route['source_row']) != int(record['source_row']):
        ctx.violation('route_structure', uid=uid, reason='source_row_mismatch',
                      recorded=route.get('source_row'),
                      expected=int(record['source_row']))
        errors += 1
    if route.get('target_row') is not None \
            and int(route['target_row']) != int(record['target_row']):
        ctx.violation('route_structure', uid=uid, reason='target_row_mismatch',
                      recorded=route.get('target_row'),
                      expected=int(record['target_row']))
        errors += 1
    # bend metrics recorded by the builder must agree with the geometry
    if chain_stats is not None:
        recorded_min = _f(route.get('min_bend_radius_mm'))
        if recorded_min is not None and chain_stats['min_radius'] is not None:
            if abs(recorded_min - chain_stats['min_radius']) > 1e-6:
                ctx.violation('route_structure', uid=uid,
                              reason='min_bend_radius_mismatch',
                              recorded=recorded_min,
                              computed=chain_stats['min_radius'])
                errors += 1
        recorded_bends = route.get('bend_count')
        if recorded_bends is not None and int(recorded_bends) != chain_stats['arcs']:
            ctx.violation('route_structure', uid=uid,
                          reason='bend_count_mismatch',
                          recorded=int(recorded_bends),
                          computed=chain_stats['arcs'])
            errors += 1
    return errors


def _check_geometry(ctx, routes, data):
    records = {record['uid']: record for record in ctx.records}
    checked = 0
    failed = 0
    errors_total = 0
    for route in routes:
        uid = route.get('uid')
        record = records.get(uid)
        if record is None:
            continue
        if _is_failed(route):
            failed += 1
            continue
        checked += 1
        try:
            pose = _check_route_pose(ctx, uid, route, record)
        except Exception as error:  # pragma: no cover - defensive
            ctx.violation('route_check_error', uid=uid, reason=str(error))
            errors_total += 1
            continue
        if pose is None:
            continue
        chain, chain_stats = pose
        try:
            errors_total += _check_route_structure(
                ctx, uid, route, record, chain, chain_stats)
        except Exception as error:  # pragma: no cover - defensive
            ctx.violation('route_check_error', uid=uid, reason=str(error))
            errors_total += 1
    ctx.check('single_route_geometry', errors_total == 0,
              dict(routed_routes=checked, failed_routes=failed,
                   violations=errors_total))
    geometry_kinds = (
        'invalid_primitive', 'diagonal_line', 'zero_length_line', 'invalid_arc',
        'inconsistent_arc', 'arc_radius_below_min', 'position_discontinuity',
        'tangent_discontinuity', 'board_out_of_bounds', 'board_bounds_undefined',
        'route_endpoint_mismatch', 'route_endpoint_missing',
        'route_port_direction_error', 'missing_xy_chain',
        'flat_part_height_mismatch', 'flat_part_height_invalid',
        'flat_part_layer_invalid', 'flat_part_layer_out_of_stack',
        'flat_part_length_mismatch', 'flat_layer_not_in_route_layers',
        'empty_flat_part', 'invalid_transition', 'invalid_part', 'missing_parts',
        'route_structure', 'transition_radius_below_min',
        'transition_radius_inconsistent', 'transition_footprint_inconsistent',
        'transition_theta_inconsistent', 'transition_length_inconsistent',
        'transition_with_zero_height_change', 'transition_join_height_mismatch',
        'transition_join_position_mismatch', 'route_check_error',
    )
    ctx.check('single_route_checks', all(ctx.counts.get(kind, 0) == 0
                                         for kind in geometry_kinds),
              {kind: ctx.counts.get(kind, 0) for kind in geometry_kinds
               if ctx.counts.get(kind, 0)})
    ctx.check('arc_radius_exactly_15',
              ctx.radius_off_count == 0 and ctx.arc_count > 0,
              dict(arcs=ctx.arc_count,
                   arcs_not_exactly_radius=ctx.radius_off_count,
                   radius_mm=ctx.radius,
                   min_radius_mm=ctx.min_radius))
    if ctx.arc_count == 0:
        ctx.check('arc_min_radius', False, dict(reason='no_arcs_found'))
    else:
        ctx.check('arc_min_radius', (ctx.min_radius or 0.0) >=
                  ctx.radius - TOL_RADIUS_MM,
                  dict(min_radius_mm=ctx.min_radius, required_radius_mm=ctx.radius))


# ---------------------------------------------------------------------------
# 5) same physical plane conflicts + legal crossings (D56 strict + independent)
# ---------------------------------------------------------------------------
def _flat_plane_groups(routes):
    """``{rounded z: OrderedDict(route_key -> {uid, prims, parts})}``."""
    groups = OrderedDict()
    fallback = 0
    for route in routes:
        if _is_failed(route):
            continue
        uid = route.get('uid')
        route_key = route.get('route_id')
        if route_key is None:
            fallback += 1
            route_key = 900000000 + fallback
        per_plane = OrderedDict()
        for part in _flat_parts(route):
            primitives = part.get('primitives') or []
            z_mm = _f(part.get('z_mm'))
            if z_mm is None or not primitives:
                continue
            key = round(z_mm, 9)
            per_plane.setdefault(key, []).extend(
                dict(prim) for prim in primitives if isinstance(prim, dict))
        for key, prims in per_plane.items():
            entry = groups.setdefault(key, OrderedDict())
            entry[int(route_key)] = dict(uid=uid, prims=prims,
                                         route=route)
    return groups


def _candidate_pairs(prepared, pad):
    """Broad phase: route pairs whose exact bounding boxes are within ``pad``."""
    if len(prepared) < 2:
        return []
    boxes = np.asarray([[*route.bbox] for route in prepared], dtype=float)
    pairs = []
    for index in range(len(prepared) - 1):
        x0, y0, x1, y1 = boxes[index]
        rest = boxes[index + 1:]
        dx = np.maximum(rest[:, 0] - x1, x0 - rest[:, 2])
        np.maximum(dx, 0.0, out=dx)
        dy = np.maximum(rest[:, 1] - y1, y0 - rest[:, 3])
        np.maximum(dy, 0.0, out=dy)
        near = np.flatnonzero(np.hypot(dx, dy) <= pad)
        pairs.extend((index, index + 1 + int(offset)) for offset in near)
    return pairs


def _run_independent_pair_audit(ctx, prepared, route_ids, route_uids, z_mm):
    """Authoritative pair-by-pair D56 strict audit; returns aggregate data."""
    from four_side_1024.d56 import validate_d56 as V

    kind_map = {
        'overlap': 'same_plane_overlap',
        'touch': 'same_plane_touch',
        'tangent_touch': 'same_plane_tangent_touch',
        'endpoint_touch': 'same_plane_endpoint_touch',
        'spacing': 'same_plane_spacing',
        'double_cross': 'same_plane_double_cross',
        'crossing_window_overlap': 'same_plane_crossing_window_overlap',
        'crossing_window_excessive': 'same_plane_crossing_window_excessive',
    }
    sagitta = float(C.SAGITTA_MM)
    pairs = _candidate_pairs(prepared, ctx.clearance + 2.0 * sagitta)
    result = dict(
        candidate_pairs=len(pairs), violations=[], violations_by_pair={},
        crossings=[], crossing_pairs=0, pair_min_distances=[],
        invalid_route_ids=set(), error=None)
    for index_a, index_b in pairs:
        first = prepared[index_a]
        second = prepared[index_b]
        try:
            pair = V.evaluate_pair(first, second, clearance=ctx.clearance,
                                   sagitta=sagitta, policy='strict')
        except Exception as error:  # pragma: no cover - defensive
            result['error_detail'] = f'pair_audit_error: {error}'
            result['violations'].append(dict(
                route_a=route_uids[index_a], route_b=route_uids[index_b],
                kind='same_plane_pair_audit_error', detail_kind=None,
                distance_mm=None, x=None, y=None))
            result['invalid_route_ids'].update(
                (route_ids[index_a], route_ids[index_b]))
            continue
        if pair is None:
            continue
        uid_a = route_uids[index_a]
        uid_b = route_uids[index_b]
        pair_key = tuple(sorted((uid_a, uid_b)))
        if pair.get('valid'):
            if pair.get('crossings'):
                result['crossing_pairs'] += 1
                for crossing in pair['crossings']:
                    angle = math.degrees(math.asin(
                        max(-1.0, min(1.0, float(crossing.get('sine', 0.0))))))
                    point = crossing.get('point') or (None, None)
                    result['crossings'].append(dict(
                        route_a=uid_a, route_b=uid_b, z_mm=z_mm,
                        x=float(point[0]) if point[0] is not None else None,
                        y=float(point[1]) if point[1] is not None else None,
                        angle_deg=float(angle)))
            else:
                distance = pair.get('min_distance')
                if distance is not None:
                    result['pair_min_distances'].append(
                        (uid_a, uid_b, float(distance)))
        else:
            raw_kinds = []
            if pair.get('overlap'):
                raw_kinds.append('overlap')
            if pair.get('touch'):
                touch_kind = 'touch'
                for detail in pair.get('violations') or []:
                    if detail.get('kind') in ('tangent_touch', 'endpoint_touch'):
                        touch_kind = detail['kind']
                        break
                raw_kinds.append(touch_kind)
            if pair.get('double_cross'):
                raw_kinds.append('double_cross')
            if pair.get('crossing_zone_overlap'):
                raw_kinds.append('crossing_window_overlap')
            if pair.get('crossing_window_excessive'):
                raw_kinds.append('crossing_window_excessive')
            if pair.get('spacing'):
                raw_kinds.append('spacing')
            details = pair.get('violations') or [
                dict(kind=kind, distance_mm=None, x=None, y=None)
                for kind in raw_kinds]
            for detail in details:
                raw_kind = detail.get('kind') or 'spacing'
                item = dict(
                    route_a=uid_a, route_b=uid_b, z_mm=z_mm,
                    kind=kind_map.get(raw_kind, f'same_plane_{raw_kind}'),
                    detail_kind=raw_kind,
                    distance_mm=detail.get('distance_mm'),
                    x=detail.get('x'), y=detail.get('y'),
                    kinds=[kind_map.get(value, f'same_plane_{value}')
                           for value in raw_kinds])
                result['violations'].append(item)
                result['violations_by_pair'].setdefault(pair_key, []).append(item)
                result['invalid_route_ids'].add(route_ids[index_a])
                result['invalid_route_ids'].add(route_ids[index_b])
    return result


def _check_same_plane(ctx, routes, data):
    from four_side_1024.d56.index import D56Index, prepare
    from four_side_1024.d56 import validate_d56 as V

    groups = _flat_plane_groups(routes)
    ctx.log(f'[verify] same-plane conflict audit on {len(groups)} physical planes')
    violation_pairs = []
    all_crossing_items = []
    for z_mm in sorted(groups):
        entries = groups[z_mm]
        route_ids = list(entries.keys())
        route_uids = [entries[rid]['uid'] for rid in route_ids]
        logical_layer = _logical_layer_of_z(z_mm, ctx.stack)
        plane_parts = 0
        for rid in route_ids:
            for part in _flat_parts(entries[rid]['route']):
                part_z = _f(part.get('z_mm'))
                if part_z is not None and abs(part_z - z_mm) < 1e-9:
                    plane_parts += 1
        plane_stat = dict(
            z_mm=round(float(z_mm), 9), logical_layer=logical_layer,
            layer_label=f'L{logical_layer}' if logical_layer else 'unmapped',
            routes=len(entries), parts=plane_parts,
            conflicts=0, conflict_routes=0, conflict_pairs=0,
            crossing_events=0, crossing_pairs=0, min_clearance_mm=None,
            d56_route_conflicts=0, independent_violations=0)
        # ---- frozen strict D56 index (required by the task) --------------
        index = D56Index(width=float(C.WIDTH_MM), gap=float(C.EDGE_GAP_MM),
                         sagitta=float(C.SAGITTA_MM),
                         min_cross_angle_deg=float(C.MIN_CROSS_ANGLE_DEG),
                         crossing_policy='strict')
        prepared_map = {}
        for rid in route_ids:
            prepared = prepare(entries[rid]['prims'])
            prepared_map[rid] = prepared
            index.add(rid, prepared)
        d56_conflicts = OrderedDict()
        d56_crossings = 0
        for rid in route_ids:
            # enumerate every blocker route: the strict verdict stops at the
            # first blocker, so repeat with the found blockers excluded until
            # the route is accepted (bounded to stay finite on broken inputs).
            excluded = {rid}
            blockers = []
            reason = None
            for _ in range(512):
                evaluation = index.evaluate(prepared_map[rid], exclude=excluded)
                if evaluation is None:
                    break
                d56_crossings += len(getattr(evaluation, 'crossings', []) or [])
                if evaluation.valid:
                    break
                reason = getattr(evaluation, 'reason', None)
                found = [int(blocker) for blocker in
                         (getattr(evaluation, 'blockers', []) or [])]
                new_blockers = [blocker for blocker in found
                                if blocker not in excluded]
                if not new_blockers:
                    break
                blockers.extend(new_blockers)
                excluded.update(new_blockers)
            if blockers:
                d56_conflicts[rid] = dict(reason=reason,
                                          blockers=sorted(set(blockers)))
        plane_stat['d56_route_conflicts'] = len(d56_conflicts)

        # ---- independent authoritative pair audit ------------------------
        prepared = [V.prepare_route(entries[rid]['prims'], route_id=rid)
                    for rid in route_ids]
        audit = _run_independent_pair_audit(ctx, prepared, route_ids, route_uids,
                                            z_mm)
        if audit.get('error_detail'):
            ctx.violation('pair_audit_error', z_mm=z_mm,
                          reason=audit['error_detail'])
        plane_stat['independent_violations'] = len(audit['violations'])
        plane_stat['candidate_pairs'] = audit['candidate_pairs']
        plane_stat['crossing_events'] = len(audit['crossings'])
        plane_stat['crossing_pairs'] = audit['crossing_pairs']

        # map independent violation route ids back to uids
        rid_to_uid = dict(zip(route_ids, route_uids))
        independent_pairs = set()
        independent_invalid = set()
        for item in audit['violations']:
            pair = tuple(sorted((item['route_a'], item['route_b'])))
            independent_pairs.add(pair)
            independent_invalid.update(pair)
            ctx.violation(item['kind'], uid=item['route_a'], uid_b=item['route_b'],
                          z_mm=round(float(z_mm), 9),
                          logical_layer=logical_layer,
                          detail_kind=item.get('detail_kind'),
                          distance_mm=item.get('distance_mm'),
                          x=item.get('x'), y=item.get('y'),
                          kinds=item.get('kinds'))
            violation_pairs.append(dict(
                uid_a=item['route_a'], uid_b=item['route_b'],
                z_mm=round(float(z_mm), 9), kind=item['kind'],
                detail_kind=item.get('detail_kind'),
                distance_mm=item.get('distance_mm')))
        # D56 index pairs, mapped back to record uids
        d56_pairs = set()
        d56_invalid = set()
        for rid, info in d56_conflicts.items():
            d56_invalid.add(rid_to_uid[rid])
            for blocker in info['blockers']:
                if blocker in rid_to_uid:
                    d56_pairs.add(tuple(sorted((rid_to_uid[rid],
                                                rid_to_uid[blocker]))))
        router_only = d56_pairs - independent_pairs
        for uid_a, uid_b in sorted(router_only):
            reason = None
            for rid, info in d56_conflicts.items():
                if rid_to_uid[rid] in (uid_a, uid_b):
                    reason = info.get('reason')
                    break
            ctx.violation('same_plane_d56index_conflict',
                          uid=uid_a, uid_b=uid_b, z_mm=round(float(z_mm), 9),
                          logical_layer=logical_layer,
                          reason=reason)
            violation_pairs.append(dict(uid_a=uid_a, uid_b=uid_b,
                                        z_mm=round(float(z_mm), 9),
                                        kind='same_plane_d56index_conflict'))
            independent_invalid.update((uid_a, uid_b))
        independent_only = independent_pairs - d56_pairs
        missing_route = d56_invalid - independent_invalid
        if independent_only or router_only or missing_route:
            ctx.discrepancies.append(dict(
                z_mm=round(float(z_mm), 9),
                d56_index_only_pairs=len(router_only),
                independent_only_pairs=len(independent_only),
                d56_route_conflicts=len(d56_conflicts),
                independent_conflict_routes=len(independent_invalid),
                route_set_mismatch=len(missing_route | (independent_invalid
                                                        - d56_invalid)),
                examples=dict(
                    d56_index_only=[list(pair) for pair in sorted(router_only)[:5]],
                    independent_only=[list(pair) for pair in
                                      sorted(independent_only)[:5]],
                    route_set_mismatch=sorted(missing_route
                                              | (independent_invalid - d56_invalid))[:10])))
        plane_stat['conflict_pairs'] = len(independent_pairs | router_only)
        plane_stat['conflict_routes'] = len(independent_invalid)
        plane_stat['conflicts'] = plane_stat['conflict_pairs']
        plane_stat['independent_conflict_routes'] = len(independent_invalid)
        plane_stat['d56_conflict_routes'] = len(d56_invalid)

        # min clearance for this plane
        min_clearance = None
        for _uid_a, _uid_b, distance in audit['pair_min_distances']:
            if min_clearance is None or distance < min_clearance:
                min_clearance = distance
        for item in audit['violations']:
            distance = item.get('distance_mm')
            if distance is not None:
                if min_clearance is None or distance < min_clearance:
                    min_clearance = distance
        plane_stat['min_clearance_mm'] = min_clearance
        if min_clearance is not None:
            ctx.note_clearance(min_clearance)

        # crossings (legal; distinguished from violations)
        crossing_stat = dict(events=len(audit['crossings']),
                             pairs=audit['crossing_pairs'],
                             min_angle_deg=None)
        for crossing in audit['crossings']:
            angle = crossing['angle_deg']
            if crossing_stat['min_angle_deg'] is None \
                    or angle < crossing_stat['min_angle_deg']:
                crossing_stat['min_angle_deg'] = angle
            if ctx.min_cross_angle is None or angle < ctx.min_cross_angle:
                ctx.min_cross_angle = angle
            all_crossing_items.append(dict(
                z_mm=round(float(z_mm), 9), logical_layer=logical_layer,
                uid_a=crossing['route_a'], uid_b=crossing['route_b'],
                x=crossing.get('x'), y=crossing.get('y'),
                angle_deg=round(float(angle), 9)))
        plane_stat['crossings'] = crossing_stat

        # per-route metrics on this plane
        for index, uid in enumerate(route_uids):
            metric = ctx.route_metrics.setdefault(uid, dict(
                min_clearance_mm=None, crossing_count=0, planes=[],
                conflicts=0))
            metric['planes'].append(round(float(z_mm), 9))
            for uid_a, uid_b, distance in audit['pair_min_distances']:
                if uid in (uid_a, uid_b):
                    current = metric['min_clearance_mm']
                    if current is None or distance < current:
                        metric['min_clearance_mm'] = distance
            for crossing in audit['crossings']:
                if uid in (crossing['route_a'], crossing['route_b']):
                    metric['crossing_count'] += 1
            if uid in independent_invalid:
                metric['conflicts'] += 1
        ctx.per_plane[str(round(float(z_mm), 9))] = plane_stat

    # record crossing tables (legal crossings, never violations)
    per_plane_cross = OrderedDict()
    per_layer_cross = OrderedDict()
    per_route_cross = OrderedDict()
    plane_crossing_pairs = defaultdict(set)
    layer_crossing_pairs = defaultdict(set)
    for item in all_crossing_items:
        z_key = str(item['z_mm'])
        layer_key = str(item['logical_layer'])
        pair = tuple(sorted((item['uid_a'], item['uid_b'])))
        for key, table in ((z_key, per_plane_cross), (layer_key, per_layer_cross)):
            entry = table.setdefault(key, dict(events=0, pairs=0,
                                               min_angle_deg=None))
            entry['events'] += 1
            if entry['min_angle_deg'] is None \
                    or item['angle_deg'] < entry['min_angle_deg']:
                entry['min_angle_deg'] = item['angle_deg']
        plane_crossing_pairs[z_key].add(pair)
        layer_crossing_pairs[layer_key].add(pair)
        for uid in (item['uid_a'], item['uid_b']):
            per_route_cross[uid] = per_route_cross.get(uid, 0) + 1
    for key, pairs_set in plane_crossing_pairs.items():
        per_plane_cross.setdefault(key, dict(events=0, pairs=0,
                                             min_angle_deg=None))['pairs'] = \
            len(pairs_set)
    for key, pairs_set in layer_crossing_pairs.items():
        per_layer_cross.setdefault(key, dict(events=0, pairs=0,
                                             min_angle_deg=None))['pairs'] = \
            len(pairs_set)
    ctx.crossings['total'] = len(all_crossing_items)
    ctx.crossings['per_plane'] = per_plane_cross
    ctx.crossings['per_layer'] = per_layer_cross
    ctx.crossings['per_route'] = per_route_cross
    ctx.crossings['min_angle_deg'] = ctx.min_cross_angle
    ctx.crossings['items'] = all_crossing_items[:20000]
    ctx.crossings['items_total'] = len(all_crossing_items)
    ctx.plane_conflict_pairs = violation_pairs

    d56_ok = all(plane['d56_route_conflicts'] == 0
                 for plane in ctx.per_plane.values())
    independent_ok = all(plane['independent_violations'] == 0
                         for plane in ctx.per_plane.values())
    ctx.check('same_plane_conflicts_d56_strict', d56_ok,
              dict(planes={key: value['d56_route_conflicts']
                           for key, value in ctx.per_plane.items()}))
    ctx.check('same_plane_conflicts_independent', independent_ok,
              dict(planes={key: value['independent_violations']
                           for key, value in ctx.per_plane.items()},
                   candidate_pairs={key: value.get('candidate_pairs')
                                    for key, value in ctx.per_plane.items()}))
    ctx.check('same_plane_crosscheck', not ctx.discrepancies,
              dict(discrepancies=ctx.discrepancies))
    ctx.check('crossings_legal_angle_ge_5deg',
              ctx.min_cross_angle is None
              or ctx.min_cross_angle >= float(C.MIN_CROSS_ANGLE_DEG) - 1e-9,
              dict(min_cross_angle_deg=ctx.min_cross_angle,
                   required_deg=float(C.MIN_CROSS_ANGLE_DEG),
                   crossings=len(all_crossing_items)))


# ---------------------------------------------------------------------------
# 6) cross-plane true 3D clearance (flats / transitions / transitions)
# ---------------------------------------------------------------------------
def _transition_records(routes):
    records = []
    for route in routes:
        if _is_failed(route):
            continue
        uid = route.get('uid')
        for part in _transition_parts(route):
            geometry = _transition_geometry(part)
            if geometry is None:
                continue
            radius, z0, z1, footprint, theta, start, direction = geometry
            end = (start[0] + direction[0] * footprint,
                   start[1] + direction[1] * footprint)
            records.append(dict(
                uid=uid, route_id=route.get('route_id'), part=part,
                z0=min(z0, z1), z1=max(z0, z1), start=start, end=end,
                bbox=(min(start[0], end[0]), min(start[1], end[1]),
                      max(start[0], end[0]), max(start[1], end[1]))))
    return records


def _flat_primitive_records(routes):
    records = []
    for route in routes:
        if _is_failed(route):
            continue
        uid = route.get('uid')
        for part in _flat_parts(route):
            z_mm = _f(part.get('z_mm'))
            if z_mm is None:
                continue
            for prim in part.get('primitives') or []:
                if not isinstance(prim, dict):
                    continue
                box = _prim_center_extents(prim)
                records.append(dict(uid=uid, z_mm=z_mm, prim=dict(prim),
                                    bbox=box))
    return records


def _flat_cell_key(x, y, cell):
    return int(math.floor(x / cell)), int(math.floor(y / cell))


def _insert_flat_grid(grid, record, cell):
    bbox = record['bbox']
    x0 = int(math.floor((bbox[0] - cell) / cell))
    x1 = int(math.floor((bbox[2] + cell) / cell))
    y0 = int(math.floor((bbox[1] - cell) / cell))
    y1 = int(math.floor((bbox[3] + cell) / cell))
    for ix in range(x0, x1 + 1):
        for iy in range(y0, y1 + 1):
            grid.setdefault((ix, iy), []).append(record)


def _query_flat_grid(grid, bbox, cell):
    x0 = int(math.floor((bbox[0] - cell) / cell))
    x1 = int(math.floor((bbox[2] + cell) / cell))
    y0 = int(math.floor((bbox[1] - cell) / cell))
    y1 = int(math.floor((bbox[3] + cell) / cell))
    found = []
    seen = set()
    for ix in range(x0, x1 + 1):
        for iy in range(y0, y1 + 1):
            for record in grid.get((ix, iy), ()):
                identifier = id(record)
                if identifier in seen:
                    continue
                seen.add(identifier)
                found.append(record)
    return found


def _bbox_distance_2d(first, second):
    dx = max(first[0] - second[2], second[0] - first[2], 0.0)
    dy = max(first[1] - second[3], second[1] - first[3], 0.0)
    return math.hypot(dx, dy)


def _check_cross_plane_3d(ctx, routes, data):
    flat_records = _flat_primitive_records(routes)
    transition_records = _transition_records(routes)
    ctx.log(f'[verify] 3D cross-plane clearance: {len(flat_records)} flat '
            f'primitives, {len(transition_records)} elevation transitions')
    cell = 2.0
    search_radius = 2.0
    grid = {}
    for record in flat_records:
        _insert_flat_grid(grid, record, cell)

    min_distance = None
    min_detail = None
    violations = []

    def note(distance, detail):
        nonlocal min_distance, min_detail
        if distance is None:
            return
        if min_distance is None or distance < min_distance:
            min_distance = distance
            min_detail = detail

    # -- flat vs flat on different physical planes: vertical separation -----
    heights = sorted({round(record['z_mm'], 9) for record in flat_records})
    min_vertical_gap = None
    for first, second in zip(heights, heights[1:]):
        gap = second - first
        if min_vertical_gap is None or gap < min_vertical_gap:
            min_vertical_gap = gap
    cross_plane_pairs_exist = len(heights) >= 2 or bool(transition_records)
    vertical_ok = (not cross_plane_pairs_exist) or (
        min_vertical_gap is not None
        and min_vertical_gap >= ctx.clearance - 1e-9)
    if min_vertical_gap is not None and not vertical_ok:
        ctx.violation('cross_plane_flat_vertical_gap',
                      distance_mm=min_vertical_gap,
                      required_mm=ctx.clearance,
                      heights=list(heights))
    if min_vertical_gap is not None:
        note(min_vertical_gap, dict(kind='flat_flat_vertical', z_mm=heights[:2]))

    # -- transition vs flat of another route -------------------------------
    flat_pair_checked = 0
    for trans in transition_records:
        probe = (trans['bbox'][0] - search_radius, trans['bbox'][1] - search_radius,
                 trans['bbox'][2] + search_radius, trans['bbox'][3] + search_radius)
        candidates = _query_flat_grid(grid, probe, cell)
        for flat in candidates:
            if flat['uid'] == trans['uid']:
                continue
            if _bbox_distance_2d(flat['bbox'], trans['bbox']) > search_radius:
                continue
            z_flat = flat['z_mm']
            if z_flat < trans['z0'] - search_radius \
                    or z_flat > trans['z1'] + search_radius:
                continue
            flat_pair_checked += 1
            distance = _transition_to_primitive_min(trans['part'],
                                                    flat['prim'], z_flat)
            if distance is None:
                continue
            point = _transition_closest_point_guess(trans, flat['prim'], z_flat)
            note(distance, dict(kind='transition_vs_flat', uid=trans['uid'],
                                other=flat['uid'], z_mm=round(z_flat, 9),
                                point=point))
            if distance < ctx.clearance - 1e-3:
                violations.append(dict(
                    kind='transition_vs_flat_3d', uid=trans['uid'],
                    uid_b=flat['uid'], z_mm=round(z_flat, 9),
                    distance_mm=distance, required_mm=ctx.clearance,
                    point=point))
                ctx.violation('transition_vs_flat_3d', uid=trans['uid'],
                              uid_b=flat['uid'], z_mm=round(z_flat, 9),
                              distance_mm=distance, point=point)

    # -- transition vs transition of another route ------------------------
    count = len(transition_records)
    trans_pair_checked = 0
    if count > 1:
        boxes = np.asarray([[*record['bbox']] for record in transition_records],
                           dtype=float)
        z_low = np.asarray([record['z0'] for record in transition_records])
        z_high = np.asarray([record['z1'] for record in transition_records])
        uid_array = np.asarray([record['uid'] for record in transition_records],
                               dtype=object)
        for index in range(count):
            x0, y0, x1, y1 = boxes[index]
            rest = boxes[index + 1:]
            dx = np.maximum(rest[:, 0] - x1, x0 - rest[:, 2])
            np.maximum(dx, 0.0, out=dx)
            dy = np.maximum(rest[:, 1] - y1, y0 - rest[:, 3])
            np.maximum(dy, 0.0, out=dy)
            near = np.flatnonzero(np.hypot(dx, dy) <= search_radius)
            for offset in near:
                jndex = index + 1 + int(offset)
                if uid_array[jndex] == uid_array[index]:
                    continue
                z_gap = max(z_low[index] - z_high[jndex],
                            z_low[jndex] - z_high[index], 0.0)
                if z_gap > search_radius:
                    continue
                trans_pair_checked += 1
                distance = _transition_pair_min(transition_records[index]['part'],
                                                transition_records[jndex]['part'])
                if distance is None:
                    continue
                note(distance, dict(kind='transition_vs_transition',
                                    uid=uid_array[index],
                                    other=uid_array[jndex],
                                    z_mm=round(0.5 * (z_low[index] + z_high[index]), 9)))
                if distance < ctx.clearance - 1e-3:
                    ctx.violation('transition_vs_transition_3d',
                                  uid=uid_array[index], uid_b=uid_array[jndex],
                                  distance_mm=distance,
                                  required_mm=ctx.clearance,
                                  z_range_mm=[float(z_low[index]),
                                              float(z_high[index])])
                    violations.append(dict(
                        kind='transition_vs_transition_3d',
                        uid=uid_array[index], uid_b=uid_array[jndex],
                        distance_mm=distance))

    ctx.check('cross_plane_flat_vertical_separation', vertical_ok,
              dict(min_vertical_gap_mm=min_vertical_gap,
                   required_mm=ctx.clearance, physical_heights=list(heights)))
    ctx.check('cross_plane_3d_clearance', not violations,
              dict(flat_vs_transition_pairs=flat_pair_checked,
                   transition_vs_transition_pairs=trans_pair_checked,
                   violations=len(violations),
                   min_3d_clearance_mm=min_distance,
                   min_detail=min_detail,
                   required_mm=ctx.clearance,
                   method=('true 3D centre-line distance: analytic elevation '
                           'S-curve sampling + local refinement, exact '
                           'flat-segment distance')))
    if min_distance is not None and min_distance < ctx.clearance - 1e-3:
        pass  # already a violation above
    ctx.check('cross_plane_3d_min_clearance',
              min_distance is None or min_distance >= ctx.clearance - 1e-3,
              dict(min_3d_clearance_mm=min_distance,
                   required_mm=ctx.clearance))
    ctx.check('cross_plane_3d_measured',
              min_distance is not None or not cross_plane_pairs_exist,
              dict(measured=min_distance is not None,
                   cross_plane_pairs_exist=cross_plane_pairs_exist,
                   note=('all transition/flat pairs are farther apart than the '
                         'search radius when no value is measured; a single '
                         'physical plane without transitions has no cross-plane '
                         'pair to measure')))


def _transition_closest_point_guess(trans, prim, z_mm):
    """Rough (x, y, z) of the closest sample; reporting only (no verdict)."""
    try:
        geometry = _transition_geometry(trans['part'])
        if geometry is None:
            return None
        footprint = geometry[3]
        us = np.linspace(0.0, footprint, 33)
        points = _transition_points(trans['part'], us)
        distances = _point_flat_primitive_distances_3d(points, prim, z_mm)
        index = int(np.argmin(distances))
        point = points[index]
        return [round(float(point[0]), 6), round(float(point[1]), 6),
                round(float(point[2]), 6)]
    except Exception:  # pragma: no cover
        return None


# ---------------------------------------------------------------------------
# 7) self clearance / self intersection
# ---------------------------------------------------------------------------
def _part_z_range(part):
    if isinstance(part, dict) and part.get('kind') == 'flat':
        z = _f(part.get('z_mm'))
        return (z, z) if z is not None else None
    if isinstance(part, dict) and part.get('kind') == 'transition':
        z0 = _f(part.get('z0'))
        z1 = _f(part.get('z1'))
        if z0 is None or z1 is None:
            return None
        return (min(z0, z1), max(z0, z1))
    return None


def _part_bbox_2d(part):
    if isinstance(part, dict) and part.get('kind') == 'flat':
        prims = part.get('primitives') or []
        boxes = [_prim_center_extents(prim) for prim in prims
                 if isinstance(prim, dict)]
        if not boxes:
            return None
        return (min(box[0] for box in boxes), min(box[1] for box in boxes),
                max(box[2] for box in boxes), max(box[3] for box in boxes))
    if isinstance(part, dict) and part.get('kind') == 'transition':
        start = part.get('start')
        end = part.get('end')
        if not isinstance(start, (list, tuple)) or not isinstance(end, (list, tuple)):
            return None
        return (min(float(start[0]), float(end[0])),
                min(float(start[1]), float(end[1])),
                max(float(start[0]), float(end[0])),
                max(float(start[1]), float(end[1])))
    return None


def _flat_part_min_distance_2d(first, second, first_z, second_z):
    """Exact minimum 2D distance between the primitives of two flat parts."""
    if abs(first_z - second_z) > 1e-12:
        return abs(first_z - second_z)
    best = None
    for prim_a in first.get('primitives') or []:
        if not isinstance(prim_a, dict):
            continue
        for prim_b in second.get('primitives') or []:
            if not isinstance(prim_b, dict):
                continue
            distance = _primitive_pair_distance_2d(prim_a, prim_b)
            if best is None or distance < best:
                best = distance
    return best


def _check_self_clearance(ctx, routes):
    violations = 0
    checked_pairs = 0
    for route in routes:
        if _is_failed(route):
            continue
        uid = route.get('uid')
        parts = [part for part in _parts(route) if isinstance(part, dict)]
        # (a) non-adjacent parts (adjacent parts only share their join)
        for index in range(len(parts)):
            for jndex in range(index + 2, len(parts)):
                first, second = parts[index], parts[jndex]
                z_first = _part_z_range(first)
                z_second = _part_z_range(second)
                if z_first is None or z_second is None:
                    continue
                box_first = _part_bbox_2d(first)
                box_second = _part_bbox_2d(second)
                if box_first is None or box_second is None:
                    continue
                gap = _bbox_distance_2d(box_first, box_second)
                z_gap = max(z_first[0] - z_second[1],
                            z_second[0] - z_first[1], 0.0)
                if math.hypot(gap, z_gap) > ctx.clearance + 1.0:
                    continue
                checked_pairs += 1
                kind_a, kind_b = first.get('kind'), second.get('kind')
                distance = None
                point = None
                if kind_a == 'flat' and kind_b == 'flat':
                    distance = _flat_part_min_distance_2d(
                        first, second, z_first[0], z_second[0])
                    point = [round(0.5 * (box_first[0] + box_second[0]), 6),
                             round(0.5 * (box_first[1] + box_second[1]), 6)]
                elif kind_a == 'flat' or kind_b == 'flat':
                    flat = first if kind_a == 'flat' else second
                    trans = second if kind_a == 'flat' else first
                    flat_z = _f(flat.get('z_mm'))
                    distances = []
                    if flat_z is not None:
                        for prim in flat.get('primitives') or []:
                            if not isinstance(prim, dict):
                                continue
                            value = _transition_to_primitive_min(trans, prim,
                                                                 flat_z)
                            if value is not None:
                                distances.append(value)
                    distance = min(distances) if distances else None
                    point = None
                else:
                    distance = _transition_pair_min(first, second)
                if distance is None:
                    continue
                if distance < ctx.clearance - 1e-3:
                    kind = 'self_intersection' if distance < 1e-6 else 'self_clearance'
                    ctx.violation(kind, uid=uid,
                                  part_indices=[index, jndex],
                                  distance_mm=distance,
                                  required_mm=ctx.clearance,
                                  point=point)
                    violations += 1
        # (b) non-adjacent primitives inside one flat part (path-distance aware)
        for part in parts:
            if part.get('kind') != 'flat':
                continue
            prims = [prim for prim in part.get('primitives') or []
                     if isinstance(prim, dict)]
            if len(prims) < 3:
                continue
            offsets = []
            running = 0.0
            lengths = []
            for prim in prims:
                offsets.append(running)
                length = _prim_length(prim)
                lengths.append(length)
                running += length
            for index in range(len(prims)):
                for jndex in range(index + 2, len(prims)):
                    separation = offsets[jndex] - (offsets[index] + lengths[index])
                    if separation <= 1.0:
                        continue
                    distance = _primitive_pair_distance_2d(prims[index],
                                                           prims[jndex])
                    checked_pairs += 1
                    if distance < ctx.clearance - 1e-3:
                        kind = ('self_intersection' if distance < 1e-6
                                else 'self_clearance')
                        ctx.violation(kind, uid=uid,
                                      part_indices=None,
                                      primitives=[index, jndex],
                                      distance_mm=distance,
                                      required_mm=ctx.clearance)
                        violations += 1
    ctx.check('self_clearance', violations == 0,
              dict(routed_pairs_checked=checked_pairs,
                   violations=violations, required_mm=ctx.clearance))


# ---------------------------------------------------------------------------
# 8) U-turn depth / nesting audit (284 manual fixed-U records)
# ---------------------------------------------------------------------------
def _u_extent_data(route, record):
    chain, _source = _route_xy_chain(route)
    inward = record['source_endpoint']['inward']
    inward = (float(inward[0]), float(inward[1]))
    lateral = (-inward[1], inward[0])
    along_min = along_max = inward_min = inward_max = None
    total_length = 0.0
    for prim in chain:
        if not isinstance(prim, dict):
            continue
        box = _prim_center_extents(prim)
        a_lo, a_hi = _extent_along(box, lateral)
        i_lo, i_hi = _extent_along(box, inward)
        along_min = a_lo if along_min is None else min(along_min, a_lo)
        along_max = a_hi if along_max is None else max(along_max, a_hi)
        inward_min = i_lo if inward_min is None else min(inward_min, i_lo)
        inward_max = i_hi if inward_max is None else max(inward_max, i_hi)
        total_length += _prim_length(prim)
    # ports: edge coordinate is the inward projection of the source port
    edge_coordinate = inward[0] * float(record['source_xy'][0]) \
        + inward[1] * float(record['source_xy'][1])
    depth = None if inward_max is None else inward_max - edge_coordinate
    span = None
    if along_min is not None and along_max is not None:
        span = along_max - along_min
    source_along = lateral[0] * float(record['source_xy'][0]) \
        + lateral[1] * float(record['source_xy'][1])
    target_along = lateral[0] * float(record['target_xy'][0]) \
        + lateral[1] * float(record['target_xy'][1])
    port_separation = abs(source_along - target_along)
    return dict(along_min=along_min, along_max=along_max, span_mm=span,
                depth_mm=depth, port_separation_mm=port_separation,
                chain_length_mm=total_length)


def _check_u_depth(ctx, routes, data, stack):
    by_uid = ctx.by_uid
    records_by_uid = {record['uid']: record for record in ctx.records}
    manual_uids = []
    manual_groups = getattr(data, 'manual_groups', {}) or {}
    for layer_id in sorted(int(layer) for layer in manual_groups):
        manual_uids.extend(manual_groups[layer_id])
    ctx.manual_u_uids = set(manual_uids)
    max_bulge = BOARD - float(ctx.radius) - HALF_WIDTH

    # conflicts between manual U routes on the same physical plane
    u_conflicts = defaultdict(set)
    u_conflict_examples = []
    for pair in ctx.plane_conflict_pairs:
        uid_a, uid_b = pair.get('uid_a'), pair.get('uid_b')
        if uid_a in ctx.manual_u_uids and uid_b in ctx.manual_u_uids:
            u_conflicts[uid_a].add(uid_b)
            u_conflicts[uid_b].add(uid_a)
            if len(u_conflict_examples) < 10:
                u_conflict_examples.append(dict(
                    uid_a=uid_a, uid_b=uid_b, z_mm=pair.get('z_mm'),
                    kind=pair.get('kind')))
    ctx.check('manual_u_same_plane_pairs', not u_conflict_examples,
              dict(violation_pairs=len(u_conflict_examples),
                   examples=u_conflict_examples,
                   note='same-layer manual U-turn pairs are independently '
                        'checked by the strict D56 pair audit'))

    table = []
    depth_report_errors = []
    for uid in manual_uids:
        record = records_by_uid.get(uid)
        route = by_uid.get(uid)
        entry = OrderedDict(
            uid=uid,
            logical_layer=(route.get('logical_layer') if route else None),
            assigned_layer=(record or {}).get('assigned_layer'),
            dataset=(record or {}).get('dataset'),
            side=(record or {}).get('source_side'),
            status=(_status(route) if route else 'missing'),
            depth_mm=None, bulge_mm=None, span_mm=None,
            port_separation_mm=None,
            separation_excess_over_2R_mm=None,
            physical_z_mm=None, transition_required=False,
            transition_footprint_mm=0.0, bulge_host_ok=None,
            target_layer_flat_length_mm=None, nesting_parent=None,
            nesting_level=0, nesting_children=0, conflicts_with_u=[],
            router_reported_depth_mm=None,
            failure_reason=(route.get('failure_reason') if route else None))
        if record is None or route is None:
            entry['status'] = 'missing'
            table.append(entry)
            continue
        if _is_failed(route):
            table.append(entry)
            continue
        try:
            extent = _u_extent_data(route, record)
        except Exception as error:  # pragma: no cover
            entry['status'] = 'geometry_error'
            entry['failure_reason'] = str(error)
            table.append(entry)
            continue
        layer = route.get('logical_layer')
        plane = record['dataset']
        entry['depth_mm'] = extent['depth_mm']
        entry['span_mm'] = extent['span_mm']
        entry['port_separation_mm'] = extent['port_separation_mm']
        if extent['depth_mm'] is not None:
            entry['bulge_mm'] = float(extent['depth_mm']) - float(ctx.radius)
        # independent cross-check of the router's own depth diagnostics
        reported_depth = _f(route.get('u_depth_mm'))
        entry['router_reported_depth_mm'] = reported_depth
        if reported_depth is not None and extent['depth_mm'] is not None:
            if abs(reported_depth - extent['depth_mm']) > 1e-6:
                depth_report_errors.append(dict(
                    uid=uid, router_reported_mm=reported_depth,
                    independently_measured_mm=extent['depth_mm']))
                ctx.violation('u_depth_router_report_mismatch', uid=uid,
                              router_reported_mm=reported_depth,
                              measured_depth_mm=extent['depth_mm'])
        if extent['port_separation_mm'] is not None:
            entry['separation_excess_over_2R_mm'] = (
                extent['port_separation_mm'] - 2.0 * ctx.radius)
        entry['physical_z_mm'] = (_expected_z(int(layer), plane)
                                 if layer is not None else None)
        # transition footprint compatibility
        if layer is not None and int(layer) != int(C.INTERFACE_LAYER_ID):
            entry['transition_required'] = True
            footprint = float(stack.transition_footprint(int(layer), plane))
            entry['transition_footprint_mm'] = footprint
            required_depth = footprint + PORT_MARGIN_MM + SEGMENT_MARGIN_MM
            depth = extent['depth_mm']
            entry['bulge_host_ok'] = (depth is not None
                                      and depth >= required_depth - 1e-6)
            entry['bulge_required_depth_mm'] = required_depth
            if not entry['bulge_host_ok']:
                ctx.violation('u_bulge_too_shallow_for_transition',
                              uid=uid, logical_layer=int(layer),
                              depth_mm=depth, required_depth_mm=required_depth,
                              transition_footprint_mm=footprint)
            target_length = 0.0
            for part in _flat_parts(route):
                try:
                    part_layer = int(part.get('layer_id'))
                except (TypeError, ValueError):
                    continue
                if part_layer == int(layer):
                    target_length += _f(part.get('length_mm')) or 0.0
            entry['target_layer_flat_length_mm'] = target_length
        # depth within the board's available inward space
        if extent['depth_mm'] is not None and extent['depth_mm'] > max_bulge + 1e-6:
            ctx.violation('u_depth_exceeds_board_space', uid=uid,
                          depth_mm=extent['depth_mm'],
                          max_available_mm=max_bulge)
        entry['conflicts_with_u'] = sorted(u_conflicts.get(uid, set()))
        table.append(entry)

    # -- nesting (same physical plane + same side) ------------------------
    groups = OrderedDict()
    for entry in table:
        if entry['status'] != 'routed':
            continue
        if entry['depth_mm'] is None or entry['physical_z_mm'] is None:
            continue
        key = (round(float(entry['physical_z_mm']), 9), entry['side'])
        groups.setdefault(key, []).append(entry)
    nesting_errors = []
    depth_errors = []
    for key, entries in groups.items():
        for entry in entries:
            entry['nesting_parent'] = None
            intervals = {}
            for item in entries:
                record = records_by_uid[item['uid']]
                extent = _u_extent_data(by_uid[item['uid']], record)
                intervals[item['uid']] = (extent['along_min'], extent['along_max'])
            candidates = []
            for parent in entries:
                if parent is entry:
                    continue
                low_parent, high_parent = intervals[parent['uid']]
                low_child, high_child = intervals[entry['uid']]
                if low_parent is None or low_child is None:
                    continue
                if (low_parent <= low_child + 1e-6
                        and high_parent >= high_child - 1e-6
                        and (high_parent - low_parent)
                        > (high_child - low_child) + 1e-6):
                    candidates.append(parent)
            if candidates:
                parent = min(candidates,
                             key=lambda item: item['span_mm'] if item['span_mm']
                             is not None else float('inf'))
                entry['nesting_parent'] = parent['uid']
                parent['nesting_children'] = parent.get('nesting_children', 0) + 1
                parent_depth = parent['depth_mm']
                child_depth = entry['depth_mm']
                if parent_depth is None or child_depth is None:
                    continue
                if parent_depth <= child_depth + 1e-9:
                    nesting_errors.append(dict(
                        uid_parent=parent['uid'], uid_child=entry['uid'],
                        parent_depth_mm=parent_depth,
                        child_depth_mm=child_depth,
                        reason='parent_U_must_be_deeper_than_child'))
                    ctx.violation('u_nesting_depth_order',
                                  uid=entry['uid'], uid_parent=parent['uid'],
                                  parent_depth_mm=parent_depth,
                                  child_depth_mm=child_depth)
                gap = parent_depth - child_depth
                if gap < ctx.clearance - 1e-9:
                    depth_errors.append(dict(
                        uid_parent=parent['uid'], uid_child=entry['uid'],
                        depth_gap_mm=gap, required_mm=ctx.clearance))
                    ctx.violation('u_nesting_depth_gap_too_small',
                                  uid=entry['uid'], uid_parent=parent['uid'],
                                  depth_gap_mm=gap,
                                  required_mm=ctx.clearance)
    # nesting levels (parent chains)
    entry_by_uid = {entry['uid']: entry for entry in table}
    for entry in table:
        level = 0
        cursor = entry
        seen = set()
        while cursor.get('nesting_parent'):
            parent_uid = cursor['nesting_parent']
            if parent_uid in seen or parent_uid not in entry_by_uid:
                break
            seen.add(parent_uid)
            level += 1
            cursor = entry_by_uid[parent_uid]
        entry['nesting_level'] = level

    # independent cross-check of the router's nesting diagnostics
    parent_mismatches = []
    for entry in table:
        if entry['status'] != 'routed':
            continue
        route = by_uid.get(entry['uid']) or {}
        if 'u_parent_uid' not in route:
            continue
        reported_parent = route.get('u_parent_uid')
        if reported_parent != entry['nesting_parent']:
            parent_mismatches.append(dict(
                uid=entry['uid'], router_reported_parent=reported_parent,
                independently_computed_parent=entry['nesting_parent']))
    ctx.check('u_nesting_router_crosscheck', not parent_mismatches,
              dict(checked=sum(1 for entry in table
                               if entry['status'] == 'routed'),
                   mismatches=len(parent_mismatches),
                   examples=parent_mismatches[:10]))
    ctx.check('u_depth_router_report_consistent', not depth_report_errors,
              dict(mismatches=len(depth_report_errors),
                   examples=depth_report_errors[:10]))

    ctx.check('u_nesting_depth_order', not nesting_errors,
              dict(errors=len(nesting_errors), examples=nesting_errors[:10],
                   note='nested U-turns on one plane/side: the wider U must run '
                        'deeper so its legs enclose the narrower U'))
    ctx.check('u_nesting_depth_gap', not depth_errors,
              dict(errors=len(depth_errors), examples=depth_errors[:10],
                   required_mm=ctx.clearance))
    depth_values = [entry['depth_mm'] for entry in table
                    if entry['depth_mm'] is not None]
    ctx.check('u_depth_within_board',
              all(depth <= max_bulge + 1e-6 for depth in depth_values),
              dict(max_depth_mm=max(depth_values) if depth_values else None,
                   max_available_mm=max_bulge))
    host_checks = [entry['bulge_host_ok'] for entry in table
                   if entry['bulge_host_ok'] is not None]
    ctx.check('u_bulge_hosts_transition', all(host_checks),
              dict(checked=len(host_checks),
                   failed=sum(1 for value in host_checks if not value),
                   note='for lifted U routes the inward bulge must host the two '
                        'elevation S-curves'))
    ctx.check('manual_u_count_284', len(table) == 284
              and len({entry['uid'] for entry in table}) == len(table),
              dict(entries=len(table), unique=len({entry['uid'] for entry in table})))
    ctx.u_depth_table = table


# ---------------------------------------------------------------------------
# 9) failure authenticity
# ---------------------------------------------------------------------------
def _check_failures(ctx, routes, data):
    records = {record['uid']: record for record in ctx.records}
    failed = []
    problems = []
    for route in routes:
        uid = route.get('uid')
        status = _status(route)
        if status == 'failed':
            reason = route.get('failure_reason')
            if reason is None or not str(reason).strip():
                problems.append(dict(uid=uid, reason='failed_route_without_reason'))
                ctx.violation('failed_route_without_reason', uid=uid)
            failed.append(dict(
                uid=uid,
                failure_reason=reason,
                failure_detail=route.get('failure_detail'),
                logical_layer=route.get('logical_layer'),
                dataset=(records.get(uid) or {}).get('dataset'),
                assignment=(records.get(uid) or {}).get('assignment')))
            if _parts(route):
                problems.append(dict(uid=uid,
                                     reason='failed_route_keeps_geometry'))
                ctx.violation('failed_route_keeps_geometry', uid=uid)
        else:
            parts = _parts(route)
            if not parts:
                problems.append(dict(uid=uid, reason='routed_route_without_parts'))
                ctx.violation('routed_route_without_parts', uid=uid)
            else:
                for index, part in enumerate(parts):
                    if part is None:
                        problems.append(dict(uid=uid, reason='none_part',
                                             index=index))
                        ctx.violation('none_part_in_routed_route', uid=uid,
                                      index=index)
                        break
            length = _f(route.get('length_mm'))
            if length is None:
                problems.append(dict(uid=uid, reason='missing_length'))
                ctx.violation('routed_route_without_length', uid=uid)
    ctx.failed_routes = failed
    ctx.check('failure_authenticity', not problems,
              dict(failed=len(failed), problems=problems[:20]))
    ctx.check('failed_routes_reported', True,
              dict(count=len(failed),
                   uids=[item['uid'] for item in failed][:50]))


# ---------------------------------------------------------------------------
# statistics: per plane / per layer
# ---------------------------------------------------------------------------
def _build_per_layer(ctx, routes, data):
    records = {record['uid']: record for record in ctx.records}
    max_layer = int(getattr(ctx.stack, 'max_layer', C.MAX_LOGICAL_LAYERS))
    layers = OrderedDict()
    for layer_id in range(1, max_layer + 1):
        layers[layer_id] = dict(
            logical_layer=layer_id, layer_label=f'L{layer_id}',
            layer_type=('interface' if layer_id == int(C.INTERFACE_LAYER_ID)
                        else 'routing'),
            physical_z_mm=([float(C.PLANE_Z_MM['z1']), float(C.PLANE_Z_MM['z2'])]
                           if layer_id == int(C.INTERFACE_LAYER_ID)
                           else [float(C.layer_z(layer_id))]),
            routes=0, routed=0, failed=0, manual=0, automatic=0,
            total_length_mm=0.0, min_bend_radius_mm=None,
            conflicts=0, crossing_events=0, crossing_pairs=0,
            min_clearance_mm=None)
    unassigned = dict(logical_layer=None, layer_label='unassigned',
                      layer_type='unassigned', physical_z_mm=[],
                      routes=0, routed=0, failed=0, manual=0, automatic=0,
                      total_length_mm=0.0, min_bend_radius_mm=None,
                      conflicts=0, crossing_events=0, crossing_pairs=0,
                      min_clearance_mm=None)
    for route in routes:
        uid = route.get('uid')
        record = records.get(uid) or {}
        layer = route.get('logical_layer')
        if layer is None:
            row = unassigned
        else:
            try:
                layer = int(layer)
            except (TypeError, ValueError):
                row = unassigned
            else:
                row = layers.get(layer, unassigned)
        row['routes'] += 1
        if record.get('assignment') == 'manual_fixed_u':
            row['manual'] += 1
        elif record.get('assignment') == 'existing_algorithm':
            row['automatic'] += 1
        if _is_failed(route):
            row['failed'] += 1
            continue
        row['routed'] += 1
        length = _f(route.get('length_mm'))
        if length is not None:
            row['total_length_mm'] += length
        radius = _f(route.get('min_bend_radius_mm'))
        if radius is not None and (row['min_bend_radius_mm'] is None
                                   or radius < row['min_bend_radius_mm']):
            row['min_bend_radius_mm'] = radius
        metric = ctx.route_metrics.get(uid) or {}
        clearance = metric.get('min_clearance_mm')
        if clearance is not None and (row['min_clearance_mm'] is None
                                      or clearance < row['min_clearance_mm']):
            row['min_clearance_mm'] = clearance
    # conflicts of one logical layer = violating route pairs on its physical
    # plane (an L1 pair on z=0.0 and a pair on z=0.5 are counted separately)
    layer_conflict_pairs = Counter()
    layer_conflict_routes = defaultdict(set)
    for pair in ctx.plane_conflict_pairs:
        layer = _logical_layer_of_z(pair.get('z_mm'), ctx.stack)
        key = str(layer) if layer is not None else 'unassigned'
        layer_conflict_pairs[key] += 1
        layer_conflict_routes[key].update((pair.get('uid_a'), pair.get('uid_b')))
    for key in list(layer_conflict_pairs):
        target = layers.get(int(key)) if key.isdigit() else None
        if target is None:
            if key == 'unassigned':
                target = unassigned
            else:
                continue
        target['conflicts'] = int(layer_conflict_pairs[key])
        target['conflict_routes'] = len(layer_conflict_routes[key])
    for layer_key, crossing in (ctx.crossings.get('per_layer') or {}).items():
        try:
            layer = int(layer_key)
        except (TypeError, ValueError):
            continue
        row = layers.get(layer)
        if row is None:
            continue
        row['crossing_events'] = crossing.get('events', 0)
        row['crossing_pairs'] = crossing.get('pairs', 0)
    per_layer = OrderedDict()
    for layer_id, row in layers.items():
        row.setdefault('conflict_routes', 0)
        per_layer[str(layer_id)] = row
    if unassigned['routes']:
        unassigned.setdefault('conflict_routes', 0)
        per_layer['unassigned'] = unassigned
    return per_layer


def _build_summary(ctx, routes, data, elapsed):
    records = ctx.records
    routed = [route for route in routes if not _is_failed(route)]
    failed = [route for route in routes if _is_failed(route)]
    used_layers = sorted({int(route['logical_layer']) for route in routed
                          if route.get('logical_layer') is not None})
    used_planes = sorted({round(float(part['z_mm']), 9)
                          for route in routed for part in _flat_parts(route)
                          if _f(part.get('z_mm')) is not None})
    manual_total = len(ctx.manual_u_uids)
    manual_failed = len([uid for uid in ctx.manual_u_uids
                         if uid in ctx.by_uid and _is_failed(ctx.by_uid[uid])])
    auto_total = len(records) - manual_total
    auto_failed = len(failed) - manual_failed
    checks_failed = [name for name, item in ctx.checks.items()
                     if not item['passed']]
    passed = not checks_failed and not ctx.violations
    summary = OrderedDict(
        passed=bool(passed),
        schema=SCHEMA,
        records=len(routes),
        input_records=len(records),
        routed=len(routed),
        failed=len(failed),
        manual_records=manual_total,
        manual_routed=manual_total - manual_failed,
        manual_failed=manual_failed,
        automatic_records=auto_total,
        automatic_routed=auto_total - auto_failed,
        automatic_failed=auto_failed,
        logical_layer_count=len(used_layers),
        logical_layers=used_layers,
        physical_plane_count=len(used_planes),
        physical_planes=used_planes,
        checks_total=len(ctx.checks),
        checks_passed=len(ctx.checks) - len(checks_failed),
        checks_failed=checks_failed,
        violations=len(ctx.violations),
        violations_by_kind=dict(sorted(ctx.counts.items())),
        min_clearance_mm=ctx.min_clearance,
        min_radius_mm=ctx.min_radius,
        min_cross_angle_deg=ctx.min_cross_angle,
        crossing_events=ctx.crossings.get('total', 0),
        arcs=ctx.arc_count,
        primitives=ctx.primitive_count,
        runtime_s=round(float(elapsed), 3),
    )
    return summary


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------
def verify_all(routes, data, stack, radius=15.0, clearance=0.08, log=print):
    """Independently verify the complete 640-record routing result.

    Parameters
    ----------
    routes:
        List of route dicts (the CONTRACT §2 ``l3d`` schema).  It must contain
        one record per input record (``status='failed'`` records included);
        routed-only lists are tolerated but then the conservation check fails.
    data:
        ``four_side_1024.manual_u640.inputs.InputData`` of the 640-record CSV.
    stack:
        ``four_side_1024.manual_u640.stack.LayerStack``.
    radius, clearance:
        process values to verify against (R = 15 mm, 0.08 mm).

    Returns
    -------
    dict
        JSON-ready verification report (see the module docstring).
    """
    started = time.perf_counter()
    log = log or (lambda message: None)
    log('[verify] independent verification: %d route records' % len(routes))
    ctx = _Context(radius, clearance, log)
    ctx.data = data
    ctx.stack = stack
    routes = [route for route in routes if isinstance(route, dict)]
    ctx.routes = routes

    _check_records(ctx, routes, data)
    log('[verify] 1/9 record conservation + identity done '
        f'({len(ctx.checks)} checks)')

    _check_ports(ctx, routes, data)
    log('[verify] 2/9 port occupancy done')

    _check_layers(ctx, routes, data, stack)
    log('[verify] 3/9 layer assignment done')

    _check_geometry(ctx, routes, data)
    log('[verify] 4/9 single-route geometry done '
        f'(min radius {ctx.min_radius} mm, {ctx.arc_count} arcs)')

    _check_same_plane(ctx, routes, data)
    log('[verify] 5/9 same-plane conflicts + crossings done '
        f'({ctx.crossings.get("total", 0)} legal crossings)')

    _check_cross_plane_3d(ctx, routes, data)
    log('[verify] 6/9 cross-plane 3D clearance done')

    _check_self_clearance(ctx, routes)
    log('[verify] 7/9 self clearance done')

    _check_u_depth(ctx, routes, data, stack)
    log('[verify] 8/9 U depth / nesting audit done '
        f'({len(ctx.u_depth_table)} manual U records)')

    _check_failures(ctx, routes, data)
    log('[verify] 9/9 failure authenticity done')

    ctx.per_layer = _build_per_layer(ctx, routes, data)
    elapsed = time.perf_counter() - started
    summary = _build_summary(ctx, routes, data, elapsed)

    result = OrderedDict(
        schema=SCHEMA,
        generated_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
        inputs=dict(
            csv=getattr(data, 'path', None),
            sha256=getattr(data, 'sha256', None),
            validation_passed=(getattr(data, 'validation', {}) or {}).get('passed'),
            records=len(ctx.records)),
        parameters=dict(
            radius_mm=float(ctx.radius), clearance_mm=float(ctx.clearance),
            width_mm=float(C.WIDTH_MM), edge_gap_mm=float(C.EDGE_GAP_MM),
            board_mm=[BOARD, BOARD], min_cross_angle_deg=float(C.MIN_CROSS_ANGLE_DEG),
            layer_pitch_mm=float(C.LAYER_PITCH_MM),
            z1_mm=float(C.Z1_MM), z2_mm=float(C.Z2_MM),
            max_layer=int(getattr(stack, 'max_layer', C.MAX_LOGICAL_LAYERS))),
        summary=summary,
        checks=ctx.checks,
        violations=ctx.violations,
        discrepancies=ctx.discrepancies,
        per_plane=ctx.per_plane,
        per_layer=ctx.per_layer,
        route_metrics=ctx.route_metrics,
        crossings=ctx.crossings,
        min_clearance_mm=ctx.min_clearance,
        min_radius_mm=ctx.min_radius,
        min_cross_angle_deg=ctx.min_cross_angle,
        u_depth_table=ctx.u_depth_table,
        failed_routes=ctx.failed_routes,
        runtime_s=round(elapsed, 3),
    )
    result = _json_safe(result)
    summary = result['summary']
    log('[verify] ============================================================')
    log(f'[verify] records={summary["records"]} routed={summary["routed"]} '
        f'failed={summary["failed"]}')
    log(f'[verify] checks {summary["checks_passed"]}/{summary["checks_total"]} '
        f'passed; violations={summary["violations"]}')
    if summary['checks_failed']:
        log(f'[verify] failed checks: {summary["checks_failed"]}')
    log(f'[verify] min clearance={summary["min_clearance_mm"]} mm, '
        f'min radius={summary["min_radius_mm"]} mm, '
        f'min crossing angle={summary["min_cross_angle_deg"]} deg')
    log(f'[verify] logical layers={summary["logical_layer_count"]} '
        f'{summary["logical_layers"]}')
    log(f'[verify] physical planes={summary["physical_plane_count"]} '
        f'{summary["physical_planes"]}')
    log(f'[verify] overall passed={summary["passed"]} '
        f'({elapsed:.1f}s)')
    return result


# ---------------------------------------------------------------------------
# command line entry point
# ---------------------------------------------------------------------------
def load_routes_file(path):
    """Load a ``routes.json`` payload (list or ``{'routes': [...]}``)."""
    path = Path(path)
    payload = json.loads(path.read_text(encoding='utf-8'))
    if isinstance(payload, dict):
        for key in ('routes', 'records', 'results'):
            value = payload.get(key)
            if isinstance(value, list):
                return value, payload
        raise ValueError(f'{path}: no route list found in the JSON payload')
    if isinstance(payload, list):
        return payload, None
    raise ValueError(f'{path}: unsupported JSON payload type '
                     f'{type(payload).__name__}')


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Independent geometric verification of the manual_u640 '
                    '640-channel 3D routing result.')
    parser.add_argument('--routes', default=None,
                        help='routes.json (default: <project>/outputs/manual_u640/routes.json)')
    parser.add_argument('--out', default=None,
                        help='validation JSON output (default: '
                             '<project>/outputs/manual_u640/validation.json)')
    parser.add_argument('--input', default=None,
                        help='manual grouping CSV (default: the project input)')
    parser.add_argument('--max-layer', type=int, default=C.MAX_LOGICAL_LAYERS)
    parser.add_argument('--json', action='store_true',
                        help='print the full JSON report to stdout')
    args = parser.parse_args(argv)

    from . import inputs as I
    from . import stack as stack_module

    routes_path = (Path(args.routes) if args.routes is not None
                   else Path(C.OUTPUT_ROOT) / 'routes.json')
    out_path = (Path(args.out) if args.out is not None
                else Path(C.OUTPUT_ROOT) / 'validation.json')
    routes, payload = load_routes_file(routes_path)
    data = I.load_inputs(args.input)
    stack = stack_module.LayerStack(int(args.max_layer))
    result = verify_all(routes, data, stack, radius=float(C.RADIUS_MM),
                       clearance=float(C.CLEARANCE_MM))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n',
                        encoding='utf-8')
    print(f'[verify] report written to {out_path}')
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0
    summary = result['summary']
    print('-' * 72)
    print(f'records      : {summary["records"]} '
          f'(input {summary["input_records"]})')
    print(f'routed       : {summary["routed"]}  failed: {summary["failed"]}')
    print(f'manual L1-L6 : {summary["manual_routed"]}/{summary["manual_records"]} '
          f'(failed {summary["manual_failed"]})')
    print(f'automatic L7+ : {summary["automatic_routed"]}/'
          f'{summary["automatic_records"]} (failed {summary["automatic_failed"]})')
    print(f'logical layers: {summary["logical_layer_count"]} '
          f'{summary["logical_layers"]}')
    print(f'physical planes: {summary["physical_plane_count"]} '
          f'{summary["physical_planes"]}')
    print(f'checks       : {summary["checks_passed"]}/{summary["checks_total"]} '
          f'passed')
    if summary['checks_failed']:
        print(f'failed checks: {summary["checks_failed"]}')
    print(f'violations   : {summary["violations"]} '
          f'{summary["violations_by_kind"]}')
    print(f'min clearance: {summary["min_clearance_mm"]} mm')
    print(f'min radius   : {summary["min_radius_mm"]} mm')
    print(f'min cross deg: {summary["min_cross_angle_deg"]}')
    print(f'crossings    : {summary["crossing_events"]}')
    print(f'passed       : {summary["passed"]}')
    print('-' * 72)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
