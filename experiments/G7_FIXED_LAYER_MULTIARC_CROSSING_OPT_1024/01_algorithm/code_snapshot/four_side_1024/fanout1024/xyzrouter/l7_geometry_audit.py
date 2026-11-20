# -*- coding: utf-8 -*-
"""Independent forensic audit of the L7 (z = -0.10 mm) routes of the G3 best
solution.

Nothing trusts the stored Validator PASS or the declared R15 radius:

* every route is re-read from ``routes_l3d.json``;
* every arc radius is re-derived from its centre / endpoints / sweep and from a
  three-point circumradius on the real arc;
* the full 3D centre line is re-sampled straight from the stored primitives
  (analytic line/arc samples + exact two-arc S-curve samples) with a per-sample
  primitive tag, and THREE independent curvature estimators are computed:
    - ``curv_menger_same_primitive``: Menger curvature of sample triples that
      stay inside one primitive (the only place a pure local curvature is
      well defined when the curvature vector jumps between primitives);
    - ``curv_menger_all``: Menger curvature of every triple (including the
      junction-spanning triples, which are known to overshoot when the
      curvature *vector* rotates between two G1-continuous primitives);
    - ``curv_turn_rate``: chord-turn-rate >= angle/ds, which for a G1 curve is
      bounded by the maximum of the adjacent true curvatures, so it is a
      junction-safe upper estimator;
  and each is compared with kappa <= 1/15 mm^-1;
* every junction (inside a flat chain and between parts) is checked for exact
  position + tangent continuity;
* every crossing event drawn on the L7 layer panel is re-verified against the
  real geometry of both routes at z = -0.10 mm (point-on-both-geometries and
  recomputed crossing angle);
* the plotting code path is inspected for spline / simplification / z-slicing
  artefacts.

Outputs ``outputs/manual_c4_new_connectivity/XYZ_JOINT_G123_1024/l7_geometry_audit/``.
"""
from __future__ import annotations

import json
import math
import sys
import time
from collections import Counter, OrderedDict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fsd25d import path3d as P3  # noqa: E402
from four_side_1024.fanout1024.xyzrouter import paths as P  # noqa: E402

RUN_DIR = P.DIRS['best_valid']
OUT_DIR = P.XYZ_RUN_DIR / 'l7_geometry_audit'
TARGET_Z = -0.10
R15 = 15.0
KAPPA_MAX = 1.0 / R15
TOL_RADIUS = 1e-6
TOL_TANGENT = 1e-6
TOL_POS = 1e-6

FLAT_STEP = 0.05
TRANS_STEP = 0.01


# ---------------------------------------------------------------------------
# geometry helpers (independent of the router)
# ---------------------------------------------------------------------------
def _dist3(a, b):
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def _dist2(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _sub3(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross3(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _norm3(v):
    n = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    return (v[0] / n, v[1] / n, v[2] / n) if n > 0 else (0.0, 0.0, 0.0)


def _angle3(a, b):
    na = math.sqrt(sum(v * v for v in a))
    nb = math.sqrt(sum(v * v for v in b))
    if na <= 0 or nb <= 0:
        return math.pi
    dot = sum(x * y for x, y in zip(a, b)) / (na * nb)
    return math.acos(max(-1.0, min(1.0, dot)))


def _menger(p0, p1, p2):
    a = _dist3(p1, p2)
    b = _dist3(p0, p2)
    c = _dist3(p0, p1)
    if a * b * c <= 1e-18:
        return 0.0
    area2 = _cross3(_sub3(p1, p0), _sub3(p2, p0))
    area = 0.5 * math.sqrt(sum(v * v for v in area2))
    return 4.0 * area / (a * b * c)


# ---------------------------------------------------------------------------
# primitive diagnostics
# ---------------------------------------------------------------------------
def prim_length(prim):
    if prim['kind'] == 'line':
        return _dist2(prim['p0'], prim['p1'])
    return abs(float(prim['radius']) * float(prim['sweep']))


def prim_start(prim):
    return (float(prim['p0'][0]), float(prim['p0'][1]))


def prim_end(prim):
    return (float(prim['p1'][0]), float(prim['p1'][1]))


def prim_tangent(prim, at_end=False):
    if prim['kind'] == 'line':
        dx = prim['p1'][0] - prim['p0'][0]
        dy = prim['p1'][1] - prim['p0'][1]
        n = math.hypot(dx, dy)
        return (dx / n, dy / n) if n > 0 else (0.0, 0.0)
    sign = 1.0 if float(prim['sweep']) >= 0 else -1.0
    angle = float(prim['start_angle']) + (float(prim['sweep']) if at_end else 0.0)
    return (-sign * math.sin(angle), sign * math.cos(angle))


def prim_point(prim, t):
    if prim['kind'] == 'line':
        p0, p1 = prim['p0'], prim['p1']
        return (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)
    angle = float(prim['start_angle']) + float(prim['sweep']) * t
    radius = float(prim['radius'])
    cx, cy = prim['center']
    return (cx + radius * math.cos(angle), cy + radius * math.sin(angle))


def audit_arc(prim):
    """Re-derive the real radius of one arc from its stored fields."""
    r = float(prim['radius'])
    cx, cy = float(prim['center'][0]), float(prim['center'][1])
    p0 = (float(prim['p0'][0]), float(prim['p0'][1]))
    p1 = (float(prim['p1'][0]), float(prim['p1'][1]))
    start = float(prim['start_angle'])
    sweep = float(prim['sweep'])
    radius_p0 = math.hypot(p0[0] - cx, p0[1] - cy)
    radius_p1 = math.hypot(p1[0] - cx, p1[1] - cy)
    expected_p0 = (cx + r * math.cos(start), cy + r * math.sin(start))
    expected_p1 = (cx + r * math.cos(start + sweep),
                   cy + r * math.sin(start + sweep))
    chord = _dist2(p0, p1)
    expected_chord = 2.0 * r * math.sin(abs(sweep) / 2.0)
    # circumradius of 7 equally spaced real arc points (robust)
    samples = [prim_point(prim, index / 6.0) for index in range(7)]
    circum_values = []
    for index in range(1, 6):
        a = _dist2(samples[index - 1], samples[index])
        b = _dist2(samples[index], samples[index + 1])
        c = _dist2(samples[index - 1], samples[index + 1])
        area = 0.5 * abs((samples[index][0] - samples[index - 1][0])
                         * (samples[index + 1][1] - samples[index - 1][1])
                         - (samples[index + 1][0] - samples[index - 1][0])
                         * (samples[index][1] - samples[index - 1][1]))
        if area > 1e-12:
            circum_values.append((a * b * c) / (4.0 * area))
    circum = max(circum_values) if circum_values else float('inf')
    return dict(
        declared_radius_mm=r,
        centre_to_p0_mm=radius_p0,
        centre_to_p1_mm=radius_p1,
        expected_p0_mm=list(expected_p0),
        expected_p1_mm=list(expected_p1),
        p0_error_mm=_dist2(p0, expected_p0),
        p1_error_mm=_dist2(p1, expected_p1),
        chord_mm=chord,
        expected_chord_mm=expected_chord,
        chord_error_mm=abs(chord - expected_chord),
        circumradius_mm=circum,
        circumradius_min_mm=min(circum_values) if circum_values else None,
        circumradius_max_mm=max(circum_values) if circum_values else None,
        radius_error_mm=max(abs(radius_p0 - r), abs(radius_p1 - r),
                            max(abs(v - r) for v in circum_values)
                            if circum_values else 0.0),
        kappa_declared=1.0 / r if r > 0 else float('inf'),
        sweep_deg=math.degrees(sweep),
        arc_length_mm=prim_length(prim),
        start_angle_rad=start,
    )


# ---------------------------------------------------------------------------
# route -> exact 3D centre line with per-sample primitive tags
# ---------------------------------------------------------------------------
def sample_part(part):
    """``[(x, y, z)]`` exact samples of one part + ``[(part, prim)]`` tags."""
    points = []
    tags = []
    if part.get('kind') == 'flat':
        z = float(part['z_mm'])
        for prim_index, prim in enumerate(part.get('primitives') or ()):
            length = prim_length(prim)
            if length <= 1e-12:
                continue
            count = max(2, int(math.ceil(length / FLAT_STEP)) + 1)
            for index in range(count):
                t = index / (count - 1)
                x, y = prim_point(prim, t)
                point = (float(x), float(y), z)
                if points and _dist3(points[-1], point) < 1e-9:
                    continue
                points.append(point)
                tags.append(prim_index)
    else:
        for sample in P3.transition_samples(part, step=TRANS_STEP):
            point = (float(sample[0]), float(sample[1]), float(sample[2]))
            if points and _dist3(points[-1], point) < 1e-12:
                continue
            points.append(point)
            tags.append(0)
    return points, tags


def route_centerline(route):
    """Exact 3D centre line + per-sample (part_index, primitive_index) tags."""
    points = []
    part_tags = []
    prim_tags = []
    for part_index, part in enumerate(route.get('parts') or ()):
        chunk, tags = sample_part(part)
        for point, prim_index in zip(chunk, tags):
            if points and _dist3(points[-1], point) < 1e-6:
                continue
            points.append(point)
            part_tags.append(part_index)
            prim_tags.append(prim_index)
    return points, part_tags, prim_tags


def curvature_profile(points, part_tags, prim_tags):
    """Three estimators + junction classification for every interior sample."""
    rows = []
    if len(points) < 3:
        return rows, Counter()
    lengths = [0.0]
    for index in range(1, len(points)):
        lengths.append(lengths[-1] + _dist3(points[index - 1], points[index]))
    kinds = Counter()
    for index in range(1, len(points) - 1):
        p0, p1, p2 = points[index - 1], points[index], points[index + 1]
        same_part = (part_tags[index - 1] == part_tags[index]
                     == part_tags[index + 1])
        same_prim = same_part and (prim_tags[index - 1] == prim_tags[index]
                                   == prim_tags[index + 1])
        kappa_menger = _menger(p0, p1, p2)
        ds1 = _dist3(p0, p1)
        ds2 = _dist3(p1, p2)
        turn = _angle3(_sub3(p1, p0), _sub3(p2, p1))
        mean_ds = 0.5 * (ds1 + ds2)
        kappa_turn = (2.0 * math.sin(0.5 * turn) / mean_ds) if mean_ds > 0 else 0.0
        kinds['same_primitive' if same_prim else
              ('same_part_junction' if same_part else 'part_junction')] += 1
        rows.append(dict(index=index, s_mm=lengths[index],
                         kappa_menger=kappa_menger,
                         kappa_turn_rate=kappa_turn,
                         ds_mm=ds1 + ds2,
                         same_primitive=bool(same_prim),
                         part_index=int(part_tags[index]),
                         primitive_index=int(prim_tags[index]),
                         point=[round(v, 6) for v in p1]))
    return rows, kinds


# ---------------------------------------------------------------------------
# exact analytic arclength parameterisation (no polyline interpolation)
# ---------------------------------------------------------------------------
def build_atoms(route):
    """Split the route into exact arclength atoms.

    flat lines / arcs are stored analytically; each transition is stored as its
    exact two-arc S-curve (radius, theta, direction, z0/z1) so any arclength can
    be evaluated without interpolating a sampled polyline.
    """
    atoms = []
    for part_index, part in enumerate(route.get('parts') or ()):
        if part.get('kind') == 'flat':
            z = float(part['z_mm'])
            for prim_index, prim in enumerate(part.get('primitives') or ()):
                length = prim_length(prim)
                if length <= 1e-12:
                    continue
                atoms.append(dict(kind='flat_' + prim['kind'],
                                  part_index=part_index,
                                  primitive_index=prim_index,
                                  length=length, z=z, prim=prim))
        else:
            radius = float(part['radius_mm'])
            theta = float(part['theta_rad'])
            atoms.append(dict(kind='transition', part_index=part_index,
                              primitive_index=0,
                              length=2.0 * radius * theta,
                              radius=radius, theta=theta,
                              start=(float(part['start'][0]),
                                     float(part['start'][1])),
                              direction=(float(part['direction'][0]),
                                         float(part['direction'][1])),
                              z0=float(part['z0']), z1=float(part['z1']),
                              part=part))
    return atoms


def atom_point(atom, local_s):
    """Exact 3D point at arclength ``local_s`` inside one atom."""
    if atom['kind'] == 'flat_line':
        prim = atom['prim']
        p0 = (float(prim['p0'][0]), float(prim['p0'][1]))
        p1 = (float(prim['p1'][0]), float(prim['p1'][1]))
        length = atom['length']
        ratio = 0.0 if length <= 0 else min(1.0, max(0.0, local_s / length))
        return (p0[0] + (p1[0] - p0[0]) * ratio,
                p0[1] + (p1[1] - p0[1]) * ratio, atom['z'])
    if atom['kind'] == 'flat_arc':
        prim = atom['prim']
        radius = float(prim['radius'])
        start = float(prim['start_angle'])
        sweep = float(prim['sweep'])
        ratio = 0.0 if atom['length'] <= 0 else min(1.0, max(0.0, local_s / atom['length']))
        angle = start + sweep * ratio
        cx, cy = float(prim['center'][0]), float(prim['center'][1])
        return (cx + radius * math.cos(angle), cy + radius * math.sin(angle),
                atom['z'])
    # exact two-arc S-curve
    radius, theta = atom['radius'], atom['theta']
    s = max(0.0, min(local_s, atom['length']))
    if s <= radius * theta:
        phi = s / radius
        u = radius * math.sin(phi)
        w = atom['z0'] + math.copysign(radius * (1.0 - math.cos(phi)),
                                       atom['z1'] - atom['z0'])
    else:
        phi = (2.0 * radius * theta - s) / radius
        dz_signed = atom['z1'] - atom['z0']
        dz_abs = abs(dz_signed)
        u = 2.0 * radius * math.sin(theta) - radius * math.sin(phi)
        w = atom['z0'] + math.copysign(
            dz_abs - radius * (1.0 - math.cos(phi)), dz_signed)
    sx, sy = atom['start']
    dx, dy = atom['direction']
    return (sx + dx * u, sy + dy * u, w)


def exact_uniform_samples(route, step=0.02):
    """(points, atom_index, s) sampled EXACTLY on the analytic geometry."""
    atoms = build_atoms(route)
    total = sum(atom['length'] for atom in atoms)
    if total <= 0:
        return [], [], [], atoms
    count = max(3, int(math.ceil(total / step)) + 1)
    points, atom_ids, s_values = [], [], []
    cursor_atom = 0
    atom_start = 0.0
    for index in range(count):
        target = total * index / (count - 1)
        while (cursor_atom + 1 < len(atoms)
               and atom_start + atoms[cursor_atom]['length'] < target - 1e-12):
            atom_start += atoms[cursor_atom]['length']
            cursor_atom += 1
        local = min(target - atom_start, atoms[cursor_atom]['length'])
        points.append(atom_point(atoms[cursor_atom], local))
        atom_ids.append(cursor_atom)
        s_values.append(target)
    return points, atom_ids, s_values, atoms


def parameterisation_crosscheck(route, samples=64):
    """Max distance between the analytic arclength point and the router's own
    ``transition_samples`` (independent of my formula, produced by path3d)."""
    atoms = build_atoms(route)
    worst = 0.0
    checked = 0
    for atom in atoms:
        if atom['kind'] != 'transition':
            continue
        reference = P3.transition_samples(atom['part'], step=0.002)
        # reference is the same exact S-curve; compare at its own arclength grid
        reference_length = 2.0 * atom['radius'] * atom['theta']
        for index in range(1, samples):
            local = reference_length * index / samples
            target = atom_point(atom, local)
            # find nearest reference point
            best = min(_dist3(target, tuple(sample)) for sample in reference)
            worst = max(worst, best)
            checked += 1
    return worst, checked


def curvature_exact_uniform(route, window=0.05, step=0.02):
    """Curvature of the exact centre line at uniform 3D arclength.

    Points are evaluated analytically (no polyline interpolation).  A sample is
    marked ``crosses_junction`` when its symmetric window spans two atoms; only
    samples inside one atom are used for the strict local-curvature verdict
    (at a junction the curvature *vector* may rotate between two G1 primitives,
    which is legal and not representable by a single local circle).
    """
    points, atom_ids, s_values, atoms = exact_uniform_samples(route, step=step)
    rows = []
    if len(points) < 3:
        return rows
    count = len(points)
    for index in range(1, count - 1):
        # window points by index (uniform grid)
        span = s_values[index + 1] - s_values[index - 1]
        p0, p1, p2 = points[index - 1], points[index], points[index + 1]
        kappa_menger = _menger(p0, p1, p2)
        turn = _angle3(_sub3(p1, p0), _sub3(p2, p1))
        kappa_turn = (2.0 * math.sin(0.5 * turn) / span) if span > 0 else 0.0
        rows.append(dict(index=index, s_mm=s_values[index], span_mm=span,
                         atom_id=int(atom_ids[index]),
                         crosses_junction=bool(atom_ids[index - 1]
                                               != atom_ids[index]
                                               or atom_ids[index] != atom_ids[index + 1]),
                         kappa_menger=kappa_menger,
                         kappa_turn=kappa_turn))
    return rows


# ---------------------------------------------------------------------------
# uniform-arclength curvature (junction-safe independent estimator)
# ---------------------------------------------------------------------------
def uniform_resample(points, step=0.02):
    """Resample the exact polyline at uniform 3D arclength spacing."""
    if len(points) < 2:
        return [], 0.0
    lengths = [0.0]
    for index in range(1, len(points)):
        lengths.append(lengths[-1] + _dist3(points[index - 1], points[index]))
    total = lengths[-1]
    count = max(3, int(math.ceil(total / step)) + 1)
    out = []
    cursor = 0
    for index in range(count):
        target = total * index / (count - 1)
        while cursor < len(lengths) - 2 and lengths[cursor + 1] < target:
            cursor += 1
        span = lengths[cursor + 1] - lengths[cursor]
        ratio = 0.0 if span <= 1e-15 else (target - lengths[cursor]) / span
        p0, p1 = points[cursor], points[cursor + 1]
        out.append((p0[0] + (p1[0] - p0[0]) * ratio,
                    p0[1] + (p1[1] - p0[1]) * ratio,
                    p0[2] + (p1[2] - p0[2]) * ratio))
    return out, total / (count - 1)


def curvature_uniform(points, window=0.05):
    """kappa <= 1/15 check on a uniform-arclength curve.

    ``kappa_turn`` = chord turn angle over the symmetric window / window length.
    For a G1 curve whose curvature magnitude never exceeds 1/15 this estimator
    is mathematically bounded by 1/15 (it averages |curvature| over the window).
    ``kappa_menger`` at the same point is also reported; near a curvature-vector
    rotation (flat R15 arc -> vertical R15 S-curve) Menger may overshoot locally
    by O(h/R) because the three-point circle mixes the two curvature directions.
    """
    rows = []
    if len(points) < 5:
        return rows
    lengths = [0.0]
    for index in range(1, len(points)):
        lengths.append(lengths[-1] + _dist3(points[index - 1], points[index]))
    total = lengths[-1]
    import bisect
    for index in range(2, len(points) - 2):
        s = lengths[index]
        if s - window < lengths[0] or s + window > total:
            continue
        before = bisect.bisect_left(lengths, s - window)
        after = bisect.bisect_right(lengths, s + window) - 1
        before = max(0, min(before, index - 1))
        after = min(len(points) - 1, max(after, index + 1))
        p_before, p_here, p_after = points[before], points[index], points[after]
        t_in = _sub3(p_here, p_before)
        t_out = _sub3(p_after, p_here)
        turn = _angle3(t_in, t_out)
        span = lengths[after] - lengths[before]
        kappa_turn = (2.0 * math.sin(0.5 * turn) / span) if span > 0 else 0.0
        kappa_menger = _menger(p_before, p_here, p_after)
        rows.append(dict(index=index, s_mm=s, span_mm=span,
                         kappa_turn=kappa_turn, kappa_menger=kappa_menger))
    return rows


# ---------------------------------------------------------------------------
# junction continuity
# ---------------------------------------------------------------------------
def tangent3(prim, at_end=False):
    tx, ty = prim_tangent(prim, at_end=at_end)
    return (tx, ty, 0.0)


def audit_junctions(route):
    issues = []
    parts = route.get('parts') or []
    for part_index, part in enumerate(parts):
        if part.get('kind') != 'flat':
            continue
        prims = part.get('primitives') or ()
        for index in range(len(prims) - 1):
            first, second = prims[index], prims[index + 1]
            gap = _dist2(prim_end(first), prim_start(second))
            angle = _angle3(tangent3(first, True), tangent3(second, False))
            if gap > TOL_POS or angle > TOL_TANGENT:
                issues.append(dict(kind='primitive_junction',
                                   part_index=part_index,
                                   primitive_index=index, gap_mm=gap,
                                   tangent_angle_rad=angle))
    for index in range(len(parts) - 1):
        first, second = parts[index], parts[index + 1]
        if first['kind'] == 'flat' and second['kind'] == 'transition':
            gap = _dist2(prim_end(first['primitives'][-1]),
                         (float(second['start'][0]), float(second['start'][1])))
            angle = _angle3(tangent3(first['primitives'][-1], True),
                            (float(second['direction'][0]),
                             float(second['direction'][1]), 0.0))
            if gap > TOL_POS or angle > TOL_TANGENT:
                issues.append(dict(kind='flat_to_transition',
                                   part_index=index, gap_mm=gap,
                                   tangent_angle_rad=angle))
        elif first['kind'] == 'transition' and second['kind'] == 'flat':
            gap = _dist2((float(first['end'][0]), float(first['end'][1])),
                         prim_start(second['primitives'][0]))
            angle = _angle3((float(first['direction'][0]),
                             float(first['direction'][1]), 0.0),
                            tangent3(second['primitives'][0], False))
            if gap > TOL_POS or angle > TOL_TANGENT:
                issues.append(dict(kind='transition_to_flat',
                                   part_index=index, gap_mm=gap,
                                   tangent_angle_rad=angle))
        elif first['kind'] == 'transition' and second['kind'] == 'transition':
            gap = _dist2((float(first['end'][0]), float(first['end'][1])),
                         (float(second['start'][0]),
                          float(second['start'][1])))
            angle = _angle3((float(first['direction'][0]),
                             float(first['direction'][1]), 0.0),
                            (float(second['direction'][0]),
                             float(second['direction'][1]), 0.0))
            if gap > TOL_POS or angle > TOL_TANGENT:
                issues.append(dict(kind='transition_to_transition',
                                   part_index=index, gap_mm=gap,
                                   tangent_angle_rad=angle))
    return issues


# ---------------------------------------------------------------------------
# crossing re-verification on the target layer
# ---------------------------------------------------------------------------
def point_on_primitive_distance(point, prim):
    if prim['kind'] == 'line':
        p0 = np.asarray(prim['p0'], float)
        p1 = np.asarray(prim['p1'], float)
        target = np.asarray(point, float)
        seg = p1 - p0
        length2 = float(seg @ seg)
        if length2 <= 0:
            return float(np.linalg.norm(target - p0))
        t = float(np.clip((target - p0) @ seg / length2, 0.0, 1.0))
        return float(np.linalg.norm(target - (p0 + t * seg)))
    cx, cy = float(prim['center'][0]), float(prim['center'][1])
    radius = float(prim['radius'])
    target = np.asarray(point, float)
    start = float(prim['start_angle'])
    sweep = float(prim['sweep'])
    angle = math.atan2(target[1] - cy, target[0] - cx)
    if sweep >= 0:
        inside = (angle - start) % (2 * math.pi) <= sweep + 1e-9
    else:
        inside = (start - angle) % (2 * math.pi) <= -sweep + 1e-9
    radial = abs(math.hypot(target[0] - cx, target[1] - cy) - radius)
    if inside:
        return radial
    d0 = math.hypot(target[0] - prim['p0'][0], target[1] - prim['p0'][1])
    d1 = math.hypot(target[0] - prim['p1'][0], target[1] - prim['p1'][1])
    return min(d0, d1)


def route_closest_on_height(route, point, z_value):
    best = None
    for part in route.get('parts') or ():
        if part.get('kind') != 'flat':
            continue
        if abs(float(part['z_mm']) - z_value) > 1e-9:
            continue
        for prim in part.get('primitives') or ():
            distance = point_on_primitive_distance(point, prim)
            if best is None or distance < best[0]:
                best = (distance, part, prim)
    return best


def _tangent_at(prim, point):
    if prim['kind'] == 'line':
        dx = prim['p1'][0] - prim['p0'][0]
        dy = prim['p1'][1] - prim['p0'][1]
        return _norm3((dx, dy, 0.0))
    cx, cy = float(prim['center'][0]), float(prim['center'][1])
    angle = math.atan2(point[1] - cy, point[0] - cx)
    sign = 1.0 if float(prim['sweep']) >= 0 else -1.0
    return _norm3((-sign * math.sin(angle), sign * math.cos(angle), 0.0))


def verify_crossings(routes_by_id, stats, z_value):
    events = [event for event in (stats.get('crossing_events') or [])
              if abs(float(event['z_mm']) - z_value) < 1e-9]
    results = []
    for event in events:
        rid_a = int(event['route_a'])
        rid_b = int(event['route_b'])
        point = (float(event['x_mm']), float(event['y_mm']))
        route_a = routes_by_id.get(rid_a)
        route_b = routes_by_id.get(rid_b)
        match_a = route_closest_on_height(route_a, point, z_value) if route_a else None
        match_b = route_closest_on_height(route_b, point, z_value) if route_b else None
        z_a = float(match_a[1]['z_mm']) if match_a else None
        z_b = float(match_b[1]['z_mm']) if match_b else None
        angle_recomputed = None
        if match_a and match_b:
            t0 = _tangent_at(match_a[2], point)
            t1 = _tangent_at(match_b[2], point)
            angle_recomputed = math.degrees(_angle3(t0, t1))
            angle_recomputed = min(angle_recomputed, 180.0 - angle_recomputed)
        results.append(dict(
            route_a=rid_a, route_b=rid_b,
            event_z_mm=float(event['z_mm']),
            z_a_mm=z_a, z_b_mm=z_b,
            same_height=bool(z_a is not None and z_b is not None
                             and abs(z_a - z_b) < 1e-9
                             and abs(z_a - z_value) < 1e-9),
            x_mm=point[0], y_mm=point[1],
            distance_a_mm=(match_a[0] if match_a else None),
            distance_b_mm=(match_b[0] if match_b else None),
            point_on_both_geometries=bool(match_a and match_b
                                          and match_a[0] <= 1e-6
                                          and match_b[0] <= 1e-6),
            angle_recorded_deg=float(event.get('angle_deg') or 0.0),
            angle_recomputed_deg=angle_recomputed,
        ))
    return results


# ---------------------------------------------------------------------------
# plotting-code inspection
# ---------------------------------------------------------------------------
def inspect_plot_code():
    path = Path(__file__).resolve().parent / 'visualize.py'
    text = path.read_text(encoding='utf-8')
    lines = text.splitlines()
    findings = OrderedDict(source=str(path))
    findings['scipy_spline_or_interp'] = any(
        token in text for token in ('scipy.interpolate', 'splprep', 'splrep',
                                    'make_interp_spline', 'CubicSpline',
                                    'interp1d', 'UnivariateSpline'))
    findings['moving_average_or_savgol'] = any(
        token in text for token in ('savgol_filter', 'gaussian_filter',
                                    'uniform_filter', 'moving_average'))
    findings['douglas_peucker_or_simplify'] = any(
        token in text for token in ('Douglas', 'Peucker', 'simplify',
                                    'approximate_polygon'))
    findings['flat_sampler'] = 'P3.path_polyline' in text
    findings['transition_sampler'] = 'P3.transition_samples' in text
    findings['join_dedupe'] = '_join_chunks' in text
    findings['crossing_markers_from_stats_events'] = (
        'def _events_by_height' in text and 'def _scatter_crossings' in text
        and "_to_float(event.get('z_mm'))" in text)
    findings['z_slice_truncation'] = any(
        token in text for token in ('z_slice', 'slice_z', 'z_threshold'))
    for index, line in enumerate(lines):
        for name in ('def sample_flat_xy', 'def sample_transition_xyz',
                     'def _join_chunks', 'def _fig_height_panels',
                     'def route_s_z', 'def _events_by_height',
                     'def _scatter_crossings', 'def _decimate'):
            if line.startswith(name):
                findings[name[4:] + '_line'] = index + 1
    return findings


# ---------------------------------------------------------------------------
# main audit
# ---------------------------------------------------------------------------
def classify_route(route):
    transitions = sum(1 for part in route['parts'] if part['kind'] == 'transition')
    mid = int(route.get('n_mid_transitions') or 0)
    arcs = sum(1 for part in route['parts'] if part['kind'] == 'flat'
               for prim in part.get('primitives') or ()
               if prim['kind'] == 'arc')
    if mid >= 4:
        return 'multi_excursion (>=2 mid-body S-curve pairs)'
    if mid >= 2:
        return 'mid_body_excursion (1 pair)'
    if arcs >= 4:
        return 'detour_body (>=4 R15 arcs)'
    if arcs >= 2:
        return 'detour_body (2 R15 arcs)'
    return 'basic_lifted (straight body)'


def main(argv=None):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_dir = Path(argv[1]) if argv and len(argv) > 1 else RUN_DIR
    payload = json.loads((Path(run_dir) / 'routes_l3d.json').read_text(encoding='utf-8'))
    routes = payload['routes']
    routes_by_id = {int(route['route_id']): route for route in routes}
    stats = json.loads((Path(run_dir) / 'crossing_stats.json').read_text(encoding='utf-8'))

    l7_ids = sorted(rid for rid, route in routes_by_id.items()
                    if any(part['kind'] == 'flat'
                           and abs(float(part['z_mm']) - TARGET_Z) < 1e-9
                           for part in route['parts']))
    print('L7 routes:', len(l7_ids))
    report = dict(schema='xyz_l7_geometry_audit_v2',
                  generated_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
                  run_dir=str(run_dir),
                  routes_file_sha256=P.sha256_file(Path(run_dir) / 'routes_l3d.json'),
                  target_height_mm=TARGET_Z,
                  route_count=len(l7_ids),
                  tolerances=dict(radius_mm=TOL_RADIUS,
                                  tangent_rad=TOL_TANGENT,
                                  position_mm=TOL_POS,
                                  kappa_limit_per_mm=KAPPA_MAX,
                                  flat_sample_step_mm=FLAT_STEP,
                                  transition_sample_step_mm=TRANS_STEP),
                  plotting=inspect_plot_code(),
                  routes=[])
    arc_issues, junction_issues = [], []
    curvature_issues = []
    kind_counter = Counter()
    totals = Counter()
    worst = []

    for rid in l7_ids:
        route = routes_by_id[rid]
        points, part_tags, prim_tags = route_centerline(route)
        profile, triple_kinds = curvature_profile(points, part_tags, prim_tags)
        arc_rows = []
        analytic_kappa = []
        for part_index, part in enumerate(route['parts']):
            if part.get('kind') != 'flat':
                continue
            for prim_index, prim in enumerate(part.get('primitives') or ()):
                totals['primitives'] += 1
                if prim['kind'] == 'arc':
                    totals['arcs'] += 1
                    row = audit_arc(prim)
                    row.update(part_index=part_index,
                               primitive_index=prim_index,
                               z_mm=float(part['z_mm']),
                               kappa_analytic=1.0 / row['circumradius_mm'])
                    analytic_kappa.append(row['kappa_analytic'])
                    arc_rows.append(row)
                    if (row['radius_error_mm'] > TOL_RADIUS
                            or abs(row['declared_radius_mm'] - R15) > TOL_RADIUS):
                        arc_issues.append(dict(route_id=rid, **row))
                        totals['arc_radius_issues'] += 1
                else:
                    totals['lines'] += 1
                    analytic_kappa.append(0.0)
        for part in route['parts']:
            if part['kind'] == 'transition':
                totals['transitions'] += 1
                analytic_kappa.append(1.0 / float(part['radius_mm']))
        issues = audit_junctions(route)
        if issues:
            junction_issues.extend(dict(route_id=rid, **issue) for issue in issues)
            totals['junction_issues'] += len(issues)
        same_prim = [row for row in profile if row['same_primitive']]
        exact_rows = curvature_exact_uniform(route)
        exact_inside = [row for row in exact_rows if not row['crosses_junction']]
        exact_cross = [row for row in exact_rows if row['crosses_junction']]
        max_exact_inside = max((row['kappa_menger'] for row in exact_inside),
                               default=0.0)
        max_exact_inside_turn = max((row['kappa_turn'] for row in exact_inside),
                                    default=0.0)
        max_exact_cross = max((row['kappa_menger'] for row in exact_cross),
                              default=0.0)
        max_exact_cross_turn = max((row['kappa_turn'] for row in exact_cross),
                                   default=0.0)
        uniform_points, uniform_step = uniform_resample(points)
        uniform_rows = curvature_uniform(uniform_points)
        max_uniform_turn = max((row['kappa_turn'] for row in uniform_rows), default=0.0)
        max_uniform_menger = max((row['kappa_menger'] for row in uniform_rows), default=0.0)
        min_uniform_radius = (1.0 / max_uniform_turn) if max_uniform_turn > 0 else None
        # arclength positions of the part boundaries: at a flat<->transition
        # junction the curvature *vector* rotates (horizontal R15 arc ->
        # vertical R15 S-curve), which makes the 3-point Menger estimator
        # overshoot locally; the turn-rate estimator is bounded and the exact
        # per-primitive curvature is 1/15 there, so classify the samples.
        dense_s = [0.0]
        for index in range(1, len(points)):
            dense_s.append(dense_s[-1] + _dist3(points[index - 1], points[index]))
        boundaries = [dense_s[index] for index in range(len(part_tags) - 1)
                      if part_tags[index] != part_tags[index + 1]]
        band = 0.25
        away = [row for row in uniform_rows
                if all(abs(row['s_mm'] - value) > band for value in boundaries)]
        near = [row for row in uniform_rows
                if any(abs(row['s_mm'] - value) <= band for value in boundaries)]
        max_uniform_menger_away = max((row['kappa_menger'] for row in away),
                                      default=0.0)
        max_uniform_menger_near = max((row['kappa_menger'] for row in near),
                                      default=0.0)
        overshoot_rows = [row for row in uniform_rows
                          if row['kappa_menger'] > KAPPA_MAX * (1 + 1e-6)]
        max_menger_same = max((row['kappa_menger'] for row in same_prim), default=0.0)
        max_menger_all = max((row['kappa_menger'] for row in profile), default=0.0)
        max_turn = max((row['kappa_turn_rate'] for row in profile), default=0.0)
        max_analytic = max(analytic_kappa, default=0.0)
        true_ok = max(max_menger_same, max_turn, max_analytic,
                      max_uniform_turn) <= KAPPA_MAX * (1 + 1e-6)
        overshoot = None
        if max_menger_all > KAPPA_MAX * (1 + 1e-6):
            worst_row = max(profile, key=lambda row: row['kappa_menger'])
            overshoot = dict(kappa_menger_all=round(max_menger_all, 9),
                             min_radius_mm=round(1.0 / max_menger_all, 6),
                             at_s_mm=round(worst_row['s_mm'], 6),
                             same_primitive=bool(worst_row['same_primitive']),
                             part_index=worst_row['part_index'],
                             primitive_index=worst_row['primitive_index'],
                             kappa_turn_rate_here=round(
                                 worst_row['kappa_turn_rate'], 9))
            if not worst_row['same_primitive']:
                totals['menger_junction_overshoots'] += 1
        totals['uniform_menger_overshoot_rows'] += len(overshoot_rows)
        if not true_ok:
            curvature_issues.append(dict(route_id=rid,
                                         max_kappa_same_primitive=max_menger_same,
                                         max_kappa_turn_rate=max_turn,
                                         max_kappa_analytic=max_analytic))
            totals['curvature_issues'] += 1
        route_kind = classify_route(route)
        kind_counter[route_kind] += 1
        totals['mid_transitions'] += int(route.get('n_mid_transitions') or 0)
        route_row = dict(
            route_id=rid,
            manual_group=str(route.get('manual_group') or ''),
            target_layer=int(route.get('target_layer') or 0),
            target_z_mm=float(route.get('target_z_mm') or 0.0),
            length_mm=float(route.get('length_mm') or 0.0),
            classification=route_kind,
            n_parts=len(route['parts']),
            n_flats=sum(1 for part in route['parts'] if part['kind'] == 'flat'),
            n_transitions=sum(1 for part in route['parts']
                              if part['kind'] == 'transition'),
            n_mid_transitions=int(route.get('n_mid_transitions') or 0),
            n_primitives=sum(len(part.get('primitives') or ())
                             for part in route['parts'] if part['kind'] == 'flat'),
            n_arcs=len(arc_rows),
            n_arcs_on_L7=sum(1 for row in arc_rows
                             if abs(row['z_mm'] - TARGET_Z) < 1e-9),
            heights_visited=sorted({round(float(part['z_mm']), 6)
                                    for part in route['parts']
                                    if part['kind'] == 'flat'}),
            transition_z_pairs=[[float(part['z0']), float(part['z1'])]
                                for part in route['parts']
                                if part['kind'] == 'transition'],
            samples=len(points),
            triple_kinds=dict(triple_kinds),
            max_kappa_same_primitive=round(max_menger_same, 9),
            max_kappa_turn_rate=round(max_turn, 9),
            max_kappa_analytic=round(max_analytic, 9),
            max_kappa_menger_all=round(max_menger_all, 9),
            max_kappa_uniform_turn=round(max_uniform_turn, 9),
            max_kappa_uniform_menger=round(max_uniform_menger, 9),
            parameterisation_crosscheck_mm=round(
                parameterisation_crosscheck(route)[0], 12),
            max_kappa_exact_uniform_inside_atom=round(max_exact_inside, 9),
            max_kappa_exact_uniform_inside_atom_turn=round(max_exact_inside_turn, 9),
            max_kappa_exact_uniform_crossing_junction=round(max_exact_cross, 9),
            max_kappa_exact_uniform_crossing_junction_turn=round(
                max_exact_cross_turn, 9),
            min_radius_exact_uniform_inside_atom_mm=(
                round(1.0 / max_exact_inside, 6) if max_exact_inside > 0 else None),
            max_kappa_uniform_menger_away_from_junctions=round(
                max_uniform_menger_away, 9),
            max_kappa_uniform_menger_near_junctions=round(
                max_uniform_menger_near, 9),
            n_part_boundaries=len(boundaries),
            uniform_menger_overshoots=int(len(overshoot_rows)),
            uniform_menger_overshoot_max_radius_mm=(
                round(1.0 / max(row['kappa_menger'] for row in overshoot_rows), 6)
                if overshoot_rows else None),
            min_radius_uniform_mm=(round(min_uniform_radius, 6)
                                   if min_uniform_radius else None),
            uniform_sample_step_mm=(round(uniform_step, 9)
                                    if uniform_step else None),
            min_radius_same_primitive_mm=(round(1.0 / max_menger_same, 6)
                                          if max_menger_same > 0 else None),
            curvature_ok=bool(true_ok),
            menger_junction_overshoot=overshoot,
            junction_issues=len(issues),
            arc_radius_issues=sum(1 for row in arc_rows
                                  if row['radius_error_mm'] > TOL_RADIUS),
            arcs=[{key: (round(row[key], 12) if isinstance(row[key], float)
                         else row[key]) for key in
                   ('part_index', 'primitive_index', 'z_mm',
                    'declared_radius_mm', 'circumradius_mm',
                    'circumradius_min_mm', 'circumradius_max_mm',
                    'radius_error_mm', 'chord_error_mm', 'sweep_deg',
                    'arc_length_mm', 'start_angle_rad', 'kappa_analytic')}
                  for row in arc_rows],
            curvature_profile=[{key: (round(value, 9) if isinstance(value, float)
                                      else value) for key, value in row.items()}
                               for row in profile[::max(1, len(profile) // 300)]],
        )
        report['routes'].append(route_row)
        worst.append((max(max_menger_same, max_turn), rid, route_row))

    crossings = verify_crossings(routes_by_id, stats, TARGET_Z)
    report['crossings'] = dict(
        count=len(crossings),
        all_same_height=all(item['same_height'] for item in crossings),
        all_points_on_both_geometries=all(item['point_on_both_geometries']
                                          for item in crossings),
        max_distance_a_mm=max((item['distance_a_mm'] or 0.0 for item in crossings),
                              default=None),
        max_distance_b_mm=max((item['distance_b_mm'] or 0.0 for item in crossings),
                              default=None),
        max_angle_difference_deg=max(
            (abs((item['angle_recorded_deg'] or 0.0)
                 - (item['angle_recomputed_deg'] or 0.0))
             for item in crossings if item['angle_recomputed_deg'] is not None),
            default=None),
        events=crossings)

    by_kind = Counter(row['classification'] for row in report['routes'])
    report['summary'] = dict(
        routes=len(l7_ids),
        route_classification=dict(by_kind),
        primitives=int(totals['primitives']),
        lines=int(totals['lines']),
        arcs=int(totals['arcs']),
        transitions=int(totals['transitions']),
        mid_transitions=int(totals['mid_transitions']),
        arc_radius_issues=int(totals['arc_radius_issues']),
        junction_issues=int(totals['junction_issues']),
        curvature_issues=int(totals['curvature_issues']),
        menger_junction_overshoots=int(totals['menger_junction_overshoots']),
        max_kappa_uniform_menger_away_from_junctions=round(max(
            (row['max_kappa_uniform_menger_away_from_junctions']
             for row in report['routes']), default=0.0), 9),
        max_kappa_uniform_menger_near_junctions=round(max(
            (row['max_kappa_uniform_menger_near_junctions']
             for row in report['routes']), default=0.0), 9),
        uniform_menger_overshoot_rows=int(sum(
            row['uniform_menger_overshoots'] for row in report['routes'])),
        uniform_menger_overshoot_max_radius_mm=min(
            (row['uniform_menger_overshoot_max_radius_mm']
             for row in report['routes']
             if row.get('uniform_menger_overshoot_max_radius_mm')),
            default=None),
        max_kappa_same_primitive=round(max(
            (row['max_kappa_same_primitive'] for row in report['routes']),
            default=0.0), 9),
        max_kappa_turn_rate=round(max(
            (row['max_kappa_turn_rate'] for row in report['routes']),
            default=0.0), 9),
        max_kappa_uniform_turn=round(max(
            (row['max_kappa_uniform_turn'] for row in report['routes']),
            default=0.0), 9),
        parameterisation_crosscheck_mm=max(
            (row['parameterisation_crosscheck_mm'] for row in report['routes']),
            default=0.0),
        max_kappa_exact_uniform_inside_atom=round(max(
            (row['max_kappa_exact_uniform_inside_atom']
             for row in report['routes']), default=0.0), 9),
        max_kappa_exact_uniform_inside_atom_turn=round(max(
            (row['max_kappa_exact_uniform_inside_atom_turn']
             for row in report['routes']), default=0.0), 9),
        max_kappa_exact_uniform_crossing_junction=round(max(
            (row['max_kappa_exact_uniform_crossing_junction']
             for row in report['routes']), default=0.0), 9),
        min_radius_exact_uniform_inside_atom_mm=min(
            (row['min_radius_exact_uniform_inside_atom_mm']
             for row in report['routes']
             if row.get('min_radius_exact_uniform_inside_atom_mm')),
            default=None),
        max_kappa_uniform_menger=round(max(
            (row['max_kappa_uniform_menger'] for row in report['routes']),
            default=0.0), 9),
        max_kappa_analytic=round(max(
            (row['max_kappa_analytic'] for row in report['routes']),
            default=0.0), 9),
        kappa_limit_per_mm=round(KAPPA_MAX, 9),
        arc_radius_min_mm=min((arc['circumradius_min_mm']
                               for row in report['routes'] for arc in row['arcs']),
                              default=None),
        arc_radius_max_mm=max((arc['circumradius_max_mm']
                               for row in report['routes'] for arc in row['arcs']),
                              default=None),
        arc_radius_error_max_mm=max((arc['radius_error_mm']
                                     for row in report['routes']
                                     for arc in row['arcs']), default=None),
        tangent_angle_max_rad=max((issue['tangent_angle_rad']
                                   for issue in junction_issues), default=0.0),
        position_gap_max_mm=max((issue['gap_mm']
                                 for issue in junction_issues), default=0.0),
    )
    report['worst_routes'] = [
        dict(route_id=rid, max_kappa=round(kappa, 9),
             min_radius_mm=(round(1.0 / kappa, 6) if kappa > 0 else None),
             classification=row['classification'],
             n_primitives=row['n_primitives'], n_arcs=row['n_arcs'],
             n_transitions=row['n_transitions'],
             n_mid_transitions=row['n_mid_transitions'])
        for kappa, rid, row in sorted(worst, reverse=True)[:10]]

    P.write_json(OUT_DIR / 'l7_geometry_audit.json', report)

    # ---- primitive listing (deliverable 1) ----
    listing = []
    for rid in l7_ids:
        route = routes_by_id[rid]
        for part_index, part in enumerate(route['parts']):
            if part['kind'] == 'flat':
                for prim_index, prim in enumerate(part.get('primitives') or ()):
                    row = dict(route_id=rid, part_index=part_index,
                               part_kind='flat', primitive_index=prim_index,
                               primitive_kind=prim['kind'],
                               z_mm=part['z_mm'],
                               length_mm=round(prim_length(prim), 6),
                               p0=str([round(float(v), 6) for v in prim['p0']]),
                               p1=str([round(float(v), 6) for v in prim['p1']]))
                    if prim['kind'] == 'arc':
                        arc = audit_arc(prim)
                        row.update(
                            center=str([round(float(v), 6) for v in prim['center']]),
                            radius_declared=round(float(prim['radius']), 9),
                            radius_measured=round(arc['circumradius_mm'], 9),
                            radius_error_mm=round(arc['radius_error_mm'], 12),
                            sweep_deg=round(math.degrees(float(prim['sweep'])), 6),
                            start_angle_deg=round(math.degrees(
                                float(prim['start_angle'])), 6),
                            chord_mm=round(arc['chord_mm'], 6))
                    listing.append(row)
            else:
                listing.append(dict(
                    route_id=rid, part_index=part_index,
                    part_kind='transition', primitive_index=0,
                    primitive_kind='S_curve_two_R15_arcs',
                    z_mm=round(float(part['z0']), 6),
                    length_mm=round(float(part.get('length_mm') or 0.0), 6),
                    p0=str([round(float(v), 6) for v in part['start']]),
                    p1=str([round(float(v), 6) for v in part['end']]),
                    z0=round(float(part['z0']), 9),
                    z1=round(float(part['z1']), 9),
                    radius_declared=round(float(part['radius_mm']), 9),
                    footprint_mm=round(float(part['footprint_mm']), 6),
                    direction=str([round(float(v), 9) for v in part['direction']]),
                    theta_deg=round(math.degrees(float(part['theta_rad'])), 6)))
    primitive_fields = sorted({key for row in listing for key in row})
    P.write_csv_records(OUT_DIR / 'l7_primitives.csv', listing,
                        primitive_fields)
    route_rows = [{key: value for key, value in row.items()
                   if key not in ('arcs', 'curvature_profile', 'triple_kinds')}
                  for row in report['routes']]
    route_fields = sorted({key for row in route_rows for key in row})
    P.write_csv_records(OUT_DIR / 'l7_route_summary.csv', route_rows,
                        route_fields)
    P.write_json(OUT_DIR / 'l7_crossings_verified.json', report['crossings'])
    print('summary:', json.dumps(report['summary'], indent=1))
    return report


if __name__ == '__main__':
    main(sys.argv)
