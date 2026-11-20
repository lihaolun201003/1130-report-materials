# -*- coding: utf-8 -*-
"""Nested same-side U-turn geometry and the geometric U-depth ladder (L1-L6).

This module implements the *depth geometry algorithm* of the manual fixed-U
round.  It does not search: the CSV already pairs the two ports of every U and
the routing layer, so the only remaining freedom is **how deep** each U runs
into the board.  The depth is derived geometrically from the nesting relation
of the same-side U intervals:

1. For one ``(logical layer, board side)`` group the U ports are projected onto
   the side (``x`` for ``N``/``S``, ``y`` for ``E``/``W``) and every U becomes an
   interval ``[lo, hi]`` of that side.
2. The U geometry is a ``quarter_pair`` (the R15 family of
   :mod:`four_side_1024.r15.u_geometry`)::

       port -> straight bulge -> 90 deg arc -> middle straight
            -> 90 deg arc -> straight bulge -> port

   with every arc radius exactly ``R = 15 mm`` and the middle straight equal to
   ``separation - 2R``.  The U therefore spans exactly its own interval and
   reaches its deepest point at ``depth = bulge + R``.
3. The intervals of one group are **laminar** (any two are disjoint or one
   contains the other), so they form a containment forest: a larger span is the
   parent, a smaller span its child.  A parent U must run **deeper** than every
   child, otherwise the child's arms cross the parent's bottom run.  The depth
   order is therefore ``depth = R + base_bulge + step * (max_rank - rank)`` where
   ``rank`` is the number of containing intervals: the outermost U gets the
   deepest track and every containment level costs one ``step`` (default
   0.5 mm, i.e. the task's recommended ladder; the hard lower bound of one step
   is 0.08 mm = the centre-line clearance).
4. ``base_bulge`` is geometric as well: L1 is the flat interface layer, so
   ``base_bulge = 0`` geometrically; L2-L6 are lifted routes and their two
   elevation S-curves must be placed on the two port straights by
   :func:`four_side_1024.manual_u640.paths2d.build_lifted_route`.  That needs

       bulge >= port_margin (1.2) + transition footprint + segment_margin (0.25)

   so the geometric minimum is ``1.2 + footprint + 0.25 (+ 0.5 reserve)``.  The
   footprint is read from
   :meth:`four_side_1024.manual_u640.stack.LayerStack.transition_footprint`, so
   the depth is computed for the real physical layer heights of the round.
   **On top of that every manual U respects the unified 12 mm edge-clearance
   floor** :data:`MIN_BASE_BULGE_MM`: the first 90 deg arc of a manual U starts
   at least 12 mm from the board edge, which keeps the ``0..12`` mm edge band
   free for the elevation S-curves of the automatic L7+ routes (those routes
   must climb from z = 0.0 / 0.5 mm to their routing layer inside that band).
   So ``base_bulge = max(geometric minimum, 12.0) + base_bulge_extra``.
5. Every candidate chain is validated with the frozen canonical validator
   (:func:`four_side_1024.manual_u640.paths2d.validate_2d_chain`: axis-aligned
   lines, exact R=15 arcs, tangent continuity, port poses, board bounds) and the
   whole ``(layer, side)`` group is checked with the frozen strict
   :class:`four_side_1024.d56.index.D56Index` (width 0.05, gap 0.03, sagitta
   0.0005, min crossing angle 5 deg, ``crossing_policy='strict'``).  Under the
   strict policy a *transverse* crossing with an angle >= 5 deg is a legal
   crossing, not a conflict; the ladder search additionally minimises those
   crossings (the default ladder achieves zero crossings for this data set).

Nothing here relaxes a constraint: the radius is never shrunk, the depth ladder
only ever gets *deeper*, and an infeasible record is reported as a failure.
"""
from __future__ import annotations

import math
import time

from four_side_1024.d56.index import D56Index, prepare
from four_side_1024.legacy_geometry import transform_primitives
from four_side_1024.r15 import u_geometry as UG

from . import config as C
from . import paths2d as P

__all__ = [
    'RADIUS_MM', 'BOARD_MM', 'WIDTH_MM', 'EDGE_GAP_MM', 'CLEARANCE_MM',
    'FAMILY', 'DEFAULT_DEPTH_STEP_MM', 'DEPTH_STEP_LADDER', 'MIN_DEPTH_STEP_MM',
    'PORT_MARGIN_MM', 'SEGMENT_MARGIN_MM', 'TRANSITION_MARGIN_MM',
    'MIN_BASE_BULGE_MM',
    'SIDES', 'side_axis', 'side_interval', 'canonical_frame',
    'build_quarter_pair', 'audit_chain', 'min_base_bulge', 'resolved_base_bulge',
    'nesting_forest', 'assign_depth_ladder', 'evaluate_same_side',
    'build_layer_u_layer',
]

#: R15 process radius of the round (existing configuration).
RADIUS_MM = float(C.RADIUS_MM)
BOARD_MM = float(C.BOARD_MM)
WIDTH_MM = float(C.WIDTH_MM)
EDGE_GAP_MM = float(C.EDGE_GAP_MM)
CLEARANCE_MM = float(C.CLEARANCE_MM)
MIN_CROSS_ANGLE_DEG = float(C.MIN_CROSS_ANGLE_DEG)
SAGITTA_MM = float(C.SAGITTA_MM)

#: Same-side U family emitted for the CSV pairings (separation 34.25..134.75 mm,
#: i.e. always > 2R = 30 mm, so the quarter pair is the legal family).
FAMILY = 'quarter_pair'
#: Board sides, deterministic order used by the depth tables.
SIDES = 'NSEW'
#: Default depth step of one containment level (task recommendation, mm).
DEFAULT_DEPTH_STEP_MM = 0.5
#: Hard lower bound of the depth step: the centre-line clearance (mm).
MIN_DEPTH_STEP_MM = CLEARANCE_MM
#: Depth-step ladder tried in order until the strict D56 check is clean.
DEPTH_STEP_LADDER = (0.5, 0.75, 1.0, 1.5, 2.0)
#: Flat path kept at a route port before an elevation transition (mm).
#: Mirrors :data:`four_side_1024.l3d.paths.PORT_MARGIN_MM`.
PORT_MARGIN_MM = 1.2
#: Flat path kept inside one straight primitive end by the transition placer (mm).
SEGMENT_MARGIN_MM = 0.25
#: Reserve on top of ``port_margin + footprint + segment_margin`` (mm).
TRANSITION_MARGIN_MM = 0.5
#: Unified minimum bulge of every manual U (mm): the first 90 deg arc of a
#: manual U starts at least this far from the board edge.  This keeps the
#: ``0..12 mm`` edge band (measured inward from the board edge) free for the
#: elevation S-curves of the automatic L7+ routes, which must climb from the
#: interface heights z = 0.0 / 0.5 mm to their routing layer inside that band.
MIN_BASE_BULGE_MM = 12.0
#: Numerical tolerance of the exact geometry audits.
TOL = 1e-9
DIR_TOL = 1e-7
SEP_TOL = 1e-9
COORD_TOL = 1e-6


# ---------------------------------------------------------------------------
# side projection / canonical frame
# ---------------------------------------------------------------------------
def side_axis(side):
    """Board axis (0 = x, 1 = y) the side runs along."""
    if side in 'NS':
        return 0
    if side in 'EW':
        return 1
    raise ValueError(f'unknown board side {side!r}')


def side_interval(record):
    """``(lo, hi)`` interval of one same-side U on its board side (mm)."""
    axis = side_axis(record['source_side'])
    values = (float(record['source_xy'][axis]), float(record['target_xy'][axis]))
    return (min(values), max(values))


def canonical_frame(record, board=None):
    """Canonical U frame of one record (rigid side rotation; public R15 helper).

    In the canonical frame the common board side is ``y = 0``, the inward
    direction is ``+y``, the source port is ``(x0, 0)`` travelling ``+y`` and the
    target port is ``(x0 + d, 0)`` travelling ``-y`` (``d`` signed).
    """
    return UG.u_frame(record['source_xy'], record['target_xy'],
                      P.start_dir(record), P.end_dir(record),
                      board=BOARD_MM if board is None else board)


# ---------------------------------------------------------------------------
# parametric quarter-pair construction (canonical frame -> world)
# ---------------------------------------------------------------------------
def _append_line(primitives, p0, p1):
    from four_side_1024.fslw import geom
    if math.hypot(p1[0] - p0[0], p1[1] - p0[1]) > TOL:
        primitives.append(geom.line(p0, p1))


def _append_arc(primitives, cursor, center, radius, start_angle, sweep):
    from four_side_1024.fslw import geom
    end = (center[0] + radius * math.cos(start_angle + sweep),
           center[1] + radius * math.sin(start_angle + sweep))
    primitives.append(geom.arc(cursor, end, center, radius, start_angle, sweep))
    return end


def _quarter_arc(primitives, cursor, heading, turn, radius):
    """Append one 90 deg arc (``turn`` +1 = left, -1 = right) to the chain."""
    normal = (-heading[1], heading[0])
    center = (cursor[0] + turn * radius * normal[0],
              cursor[1] + turn * radius * normal[1])
    start_angle = math.atan2(cursor[1] - center[1], cursor[0] - center[0])
    sweep = turn * math.pi / 2.0
    end = _append_arc(primitives, cursor, center, radius, start_angle, sweep)
    cos_sweep, sin_sweep = math.cos(sweep), math.sin(sweep)
    new_heading = (heading[0] * cos_sweep - heading[1] * sin_sweep,
                   heading[0] * sin_sweep + heading[1] * cos_sweep)
    return end, new_heading


def quarter_pair_canonical(x0, x1, bulge, radius=RADIUS_MM, middle=None):
    """Canonical quarter_pair chain for a U between ``x0`` and ``x1``.

    ``straight(bulge) + 90 deg arc + straight(middle) + 90 deg arc +
    straight(bulge)``; the chain starts at ``(x0, 0)`` travelling ``+y`` and
    ends at ``(x1, 0)`` travelling ``-y``.  The deepest point is
    ``depth = bulge + radius``.  ``middle`` defaults to ``|x1-x0| - 2R``.
    Returns ``None`` when the port separation cannot hold two R15 arcs.
    """
    x0 = float(x0)
    x1 = float(x1)
    bulge = float(bulge)
    radius = float(radius)
    delta = x1 - x0
    if middle is None:
        middle = abs(delta) - 2.0 * radius
    middle = float(middle)
    if middle < -SEP_TOL:
        return None
    if bulge < -SEP_TOL:
        return None
    turn = -1.0 if delta > 0.0 else 1.0
    primitives = []
    _append_line(primitives, (x0, 0.0), (x0, bulge))
    cursor = (x0, bulge)
    heading = (0.0, 1.0)
    cursor, heading = _quarter_arc(primitives, cursor, heading, turn, radius)
    _append_line(primitives, cursor,
                 (cursor[0] + heading[0] * middle,
                  cursor[1] + heading[1] * middle))
    cursor = (cursor[0] + heading[0] * middle,
              cursor[1] + heading[1] * middle)
    cursor, heading = _quarter_arc(primitives, cursor, heading, turn, radius)
    _append_line(primitives, cursor, (x1, 0.0))
    return primitives


def audit_chain(primitives, record, radius=RADIUS_MM):
    """Exact-radius / axis-alignment / canonical-pose audit of one XY chain."""
    radius = float(radius)
    errors = []
    for index, primitive in enumerate(primitives or []):
        if primitive.get('kind') == 'arc':
            if abs(float(primitive['radius']) - radius) > 1e-9:
                errors.append(f'arc_radius_not_exact:{index}')
        elif primitive.get('kind') == 'line':
            p0, p1 = primitive['p0'], primitive['p1']
            if (abs(p0[0] - p1[0]) > DIR_TOL
                    and abs(p0[1] - p1[1]) > DIR_TOL):
                errors.append(f'non_axis_aligned_line:{index}')
        else:
            errors.append(f'unknown_primitive_kind:{index}')
    ok, canonical_errors = P.validate_2d_chain(primitives, record, radius=radius)
    errors.extend(canonical_errors)
    return (not errors), errors


def build_quarter_pair(record, bulge, radius=RADIUS_MM):
    """World-coordinate quarter_pair U for one record at one depth.

    Returns a dict with ``primitives``, the canonical ``frame``, the port
    ``separation_mm``, the ``middle_mm`` straight, the deepest point
    ``depth_mm = bulge + R`` and the ``valid``/``errors`` audit.
    """
    radius = float(radius)
    result = dict(valid=False, errors=[], primitives=[], bulge_mm=float(bulge),
                  depth_mm=float(bulge) + radius, family=FAMILY,
                  separation_mm=None, middle_mm=None, frame=None)
    frame = canonical_frame(record)
    result['frame'] = frame
    if not frame.get('valid'):
        result['errors'] = list(frame.get('errors') or ['invalid_u_frame'])
        return result
    separation = float(frame['separation_mm'])
    result['separation_mm'] = separation
    middle = separation - 2.0 * radius
    result['middle_mm'] = middle
    if middle < -SEP_TOL:
        result['errors'] = ['below_minimum_separation_no_radius_shrink']
        return result
    if float(bulge) < -SEP_TOL:
        result['errors'] = ['negative_bulge']
        return result
    canonical = quarter_pair_canonical(frame['p_canonical'][0],
                                       frame['q_canonical'][0],
                                       float(bulge), radius=radius,
                                       middle=middle)
    if canonical is None:
        result['errors'] = ['infeasible_quarter_pair']
        return result
    world = transform_primitives(canonical, frame['transform'], inverse=True)
    ok, errors = audit_chain(world, record, radius=radius)
    result['primitives'] = world
    result['errors'] = errors
    result['valid'] = bool(ok)
    return result


def min_base_bulge(layer_id, plane, stack, radius=RADIUS_MM):
    """Smallest bulge that can host the two elevation transitions (mm).

    L1 is the flat interface layer (no transition).  L2-L6 are lifted and need
    ``port_margin + footprint + segment_margin`` of straight on each port arm.
    """
    layer_id = int(layer_id)
    if layer_id == C.INTERFACE_LAYER_ID:
        return 0.0
    footprint = float(stack.transition_footprint(layer_id, plane))
    return float(PORT_MARGIN_MM + footprint + SEGMENT_MARGIN_MM)


def min_base_bulge_payload(layer_id, plane, stack, radius=RADIUS_MM):
    layer_id = int(layer_id)
    if layer_id == C.INTERFACE_LAYER_ID:
        return dict(port_margin_mm=0.0, footprint_mm=0.0,
                    segment_margin_mm=0.0, minimum_bulge_mm=0.0,
                    transition_required=False)
    footprint = float(stack.transition_footprint(layer_id, plane))
    return dict(port_margin_mm=float(PORT_MARGIN_MM),
                footprint_mm=footprint,
                segment_margin_mm=float(SEGMENT_MARGIN_MM),
                minimum_bulge_mm=float(PORT_MARGIN_MM + footprint
                                       + SEGMENT_MARGIN_MM),
                transition_required=True)


def resolved_base_bulge(layer_id, plane, stack, radius=RADIUS_MM, extra=0.0):
    """Bulge base actually used by the depth ladder (mm).

    ``max(geometric_transition_minimum (+ transition reserve), 12 mm) + extra``:
    the geometric term hosts the two elevation S-curves of a lifted route, the
    :data:`MIN_BASE_BULGE_MM` floor keeps the first U arc 12 mm away from the
    board edge so the automatic routes can climb inside the edge band, and
    ``extra`` is the retry increment of ``u_routes``.
    """
    layer_id = int(layer_id)
    geometric = float(min_base_bulge(layer_id, plane, stack, radius=radius))
    if layer_id != C.INTERFACE_LAYER_ID:
        geometric += float(TRANSITION_MARGIN_MM)
    return max(geometric, MIN_BASE_BULGE_MM) + float(extra)


def base_bulge_payload(layer_id, plane, stack, radius=RADIUS_MM, extra=0.0):
    """JSON-ready explanation of the base bulge of one layer/side group."""
    layer_id = int(layer_id)
    geometric = float(min_base_bulge(layer_id, plane, stack, radius=radius))
    with_reserve = geometric
    if layer_id != C.INTERFACE_LAYER_ID:
        with_reserve += float(TRANSITION_MARGIN_MM)
    resolved = resolved_base_bulge(layer_id, plane, stack, radius=radius,
                                   extra=extra)
    return dict(
        layer_id=layer_id,
        plane=plane,
        transition_required=bool(layer_id != C.INTERFACE_LAYER_ID),
        transition_footprint_mm=float(stack.transition_footprint(layer_id, plane))
        if layer_id != C.INTERFACE_LAYER_ID else 0.0,
        geometric_minimum_bulge_mm=float(geometric),
        with_transition_reserve_mm=float(with_reserve),
        unified_edge_clearance_floor_mm=float(MIN_BASE_BULGE_MM),
        base_bulge_extra_mm=float(extra),
        base_bulge_mm=float(resolved),
        first_arc_edge_clearance_mm=float(resolved),
        note=('first 90 deg arc starts base_bulge mm inward from the board edge; '
              'the 12 mm floor keeps the 0..12 mm edge band free for the '
              'automatic L7+ elevation S-curves'),
    )


# ---------------------------------------------------------------------------
# interval nesting forest
# ---------------------------------------------------------------------------
def _contains(outer, inner):
    return (outer['lo'] <= inner['lo'] + TOL
            and outer['hi'] >= inner['hi'] - TOL)


def _disjoint(first, second):
    return (first['hi'] <= second['lo'] + TOL
            or second['hi'] <= first['lo'] + TOL)


def nesting_forest(records):
    """Containment forest of one ``(layer, side)`` U group.

    Returns a list of items ``{uid, record, lo, hi, span, parent, ancestors,
    children, rank, interval_mm}`` sorted by decreasing span (outermost first).
    ``ancestors`` is the number of containing U's (0 = outermost) and
    ``rank = max_ancestors - ancestors`` (0 = innermost, i.e. shallowest).
    A non-laminar group (partial overlap) is reported through
    ``item['overlap_errors']``; it must not be silently routed.
    """
    items = []
    for record in records:
        lo, hi = side_interval(record)
        items.append(dict(uid=record['uid'], record=record, lo=lo, hi=hi,
                          span=hi - lo, parent=None, ancestors=0,
                          children=[], rank=0,
                          interval_mm=[float(lo), float(hi)],
                          overlap_errors=[]))
    items.sort(key=lambda item: (-item['span'], item['lo'], item['uid']))
    # parent = smallest span interval seen so far that contains this item
    for index, item in enumerate(items):
        best = None
        for other in items[:index]:
            if _contains(other, item):
                if best is None or other['span'] < best['span']:
                    best = other
        if best is not None:
            item['parent'] = best['uid']
            item['ancestors'] = best['ancestors'] + 1
            best['children'].append(item['uid'])
    # laminar audit (a partial overlap cannot be routed with nested U's)
    for index, item in enumerate(items):
        for other in items[index + 1:]:
            if _contains(item, other) or _contains(other, item) \
                    or _disjoint(item, other):
                continue
            message = (f'partial_overlap:{item["uid"]}:{other["uid"]}')
            item['overlap_errors'].append(message)
            other['overlap_errors'].append(message)
    max_ancestors = max((item['ancestors'] for item in items), default=0)
    for item in items:
        item['rank'] = int(max_ancestors - item['ancestors'])
        item['max_ancestors'] = int(max_ancestors)
    return items


def assign_depth_ladder(items, base_bulge, step_mm, radius=RADIUS_MM):
    """Assign ``bulge``/``depth`` to every item from the nesting rank.

    ``bulge = base_bulge + step_mm * (max_ancestors - ancestors)``: the
    outermost (largest span) U is the deepest, every containment level moves one
    ``step_mm`` closer to the board side, and ``depth_mm = bulge + R``.
    Returns a list of ``{rank, bulge_mm, depth_mm}`` sorted by rank.
    """
    step_mm = float(step_mm)
    if step_mm < MIN_DEPTH_STEP_MM - TOL:
        raise ValueError(f'depth step {step_mm!r} is below the centre-line '
                         f'clearance {MIN_DEPTH_STEP_MM!r}')
    ladder = []
    by_rank = {}
    for item in items:
        rank = int(item['rank'])
        bulge = float(base_bulge) + step_mm * rank
        entry = by_rank.get(rank)
        if entry is None:
            entry = dict(rank=rank, bulge_mm=bulge,
                         depth_mm=bulge + float(radius), uids=[])
            by_rank[rank] = entry
            ladder.append(entry)
        entry['uids'].append(item['uid'])
    # depth must increase with the span, i.e. decrease with the rank
    ladder.sort(key=lambda entry: entry['rank'])
    return ladder


# ---------------------------------------------------------------------------
# strict same-plane D56 audit
# ---------------------------------------------------------------------------
def _d56_index():
    return D56Index(width=WIDTH_MM, gap=EDGE_GAP_MM, sagitta=SAGITTA_MM,
                    min_cross_angle_deg=MIN_CROSS_ANGLE_DEG,
                    crossing_policy='strict')


def evaluate_same_side(prims_by_uid, uid_order=None):
    """Strict D56 audit of one ``(layer, side)`` group.

    Every chain is ``prepare``d and evaluated against the already indexed chains
    (identical semantics to :mod:`four_side_1024.l3d.world.PlaneWorld`); a
    transverse crossing with angle >= 5 deg is a *legal crossing*, everything
    else (overlap, tangency, clearance below 0.08, crossing window problems) is
    a conflict.  Returns ``{valid, conflicts, crossings, crossing_events,
    min_spacing_mm, checked, route_ids}``.
    """
    index = _d56_index()
    order = list(prims_by_uid) if uid_order is None else list(uid_order)
    uid_to_id = {}
    conflicts = []
    crossings = []
    for position, uid in enumerate(order):
        primitives = prims_by_uid[uid]
        prepared = prepare(primitives)
        route_id = position + 1
        result = index.evaluate(prepared)
        if result is not None and not result.valid:
            conflicts.append(dict(uid=uid, reason=result.reason,
                                  blockers=list(getattr(result, 'blockers', []) or []),
                                  min_spacing_mm=result.min_spacing_mm))
        elif result is not None:
            for crossing in result.crossings or []:
                if not isinstance(crossing, dict):
                    continue
                other = crossing.get('other')
                other_uid = None
                if other is not None and other in uid_to_id:
                    other_uid = uid_to_id[other]
                crossings.append(dict(uid=uid, other=other_uid,
                                      angle_deg=float(crossing.get('angle_deg')
                                                      or 0.0),
                                      x=float(crossing.get('x', 0.0)),
                                      y=float(crossing.get('y', 0.0))))
        index.add(route_id, prepared)
        uid_to_id[route_id] = uid
    return dict(
        valid=not conflicts,
        checked=len(order),
        conflicts=conflicts,
        conflict_count=len(conflicts),
        crossings=crossings,
        crossing_events=len(crossings),
        evaluations=index.evaluations,
    )


# ---------------------------------------------------------------------------
# per (layer, side) layer builder
# ---------------------------------------------------------------------------
def _step_candidates(depth_step, base_bulge, max_rank):
    steps = []
    if depth_step is not None:
        steps.append(float(depth_step))
    for value in DEPTH_STEP_LADDER:
        if all(abs(value - other) > TOL for other in steps):
            steps.append(float(value))
    # the deepest U of the ladder must still stay inside the available board
    # inward space: depth = bulge + R <= board - half width.
    max_bulge = BOARD_MM - float(RADIUS_MM) - WIDTH_MM / 2.0
    usable = max(0.0, max_bulge - float(base_bulge))
    steps = [value for value in steps
             if (value * max(max_rank, 1) <= usable + TOL)]
    return steps or [float(DEFAULT_DEPTH_STEP_MM)]


def build_layer_u_layer(layer_id, side, records, stack, radius=RADIUS_MM,
                        depth_step=None, base_bulge_extra=0.0, log=None):
    """Build and audit all nested U centres of one ``(layer, side)`` group.

    Parameters
    ----------
    layer_id : int
        Logical layer ``L1..L6`` (the CSV ``assigned_layer``).
    side : str
        Common board side of the records (``'N'``, ``'S'``, ``'E'``, ``'W'``).
    records : list of dict
        The ``inputs.InputData.records`` of this layer and side.
    stack : four_side_1024.manual_u640.stack.LayerStack
        Layer stack used to read the real elevation-transition footprint.
    radius : float
        Fixed bend radius (15 mm; never shrunk).
    depth_step, base_bulge_extra :
        Overrides used by ``u_routes`` when a transition cannot be placed and a
        deeper ladder has to be retried (defaults: adaptive 0.5 mm ladder).

    Returns
    -------
    dict
        ``{layer_id, side, routes, failures, depth_ladder, notes, stats}`` with
        one route entry per record::

            {uid, record, primitives, bulge_mm, depth_mm, separation_mm,
             nesting_level, parent_uid, rank, family, interval_mm, valid,
             errors, route=None}
    """
    layer_id = int(layer_id)
    side = str(side)
    started = time.perf_counter()
    notes = []
    failures = []
    records = list(records or [])
    result = dict(layer_id=layer_id, side=side, routes=[], failures=[],
                  depth_ladder=[], notes=notes, stats={})
    if not records:
        notes.append('empty_group')
        result['stats'] = dict(records=0, elapsed_s=0.0)
        return result
    problems = [record['uid'] for record in records
                if record['source_side'] != side
                or record['target_side'] != side
                or record['relation'] != 'same']
    if problems:
        for uid in problems:
            failures.append(dict(uid=uid, reason='not_a_same_side_u_record'))
        result['failures'] = failures
        notes.append('group_contains_non_same_side_records')
        result['stats'] = dict(records=len(records), elapsed_s=0.0)
        return result
    # -- geometric base bulge -------------------------------------------------
    plane = records[0]['dataset']
    base_payload = min_base_bulge_payload(layer_id, plane, stack,
                                          radius=radius)
    base_info = base_bulge_payload(layer_id, plane, stack, radius=radius,
                                   extra=base_bulge_extra)
    base_bulge = float(base_info['base_bulge_mm'])
    # -- nesting forest -------------------------------------------------------
    items = nesting_forest(records)
    overlap_failures = [item['uid'] for item in items if item['overlap_errors']]
    if overlap_failures:
        for item in items:
            for message in item['overlap_errors']:
                failures.append(dict(uid=item['uid'],
                                     reason='same_side_intervals_not_laminar',
                                     detail=message))
        notes.append('non_laminar_group_cannot_be_routed_with_nested_u_turns')
        result['failures'] = failures
        result['stats'] = dict(records=len(records), failed=len(failures),
                               non_laminar=True,
                               elapsed_s=round(time.perf_counter() - started, 6))
        return result
    max_rank = max((item['rank'] for item in items), default=0)
    # -- depth ladder search --------------------------------------------------
    chosen = None
    attempts = []
    for step_mm in _step_candidates(depth_step, base_bulge, max_rank):
        ladder = assign_depth_ladder(items, base_bulge, step_mm, radius=radius)
        prims_by_uid = {}
        build_errors = {}
        for item in items:
            bulge = base_bulge + step_mm * item['rank']
            built = build_quarter_pair(item['record'], bulge, radius=radius)
            if not built['valid']:
                build_errors[item['uid']] = list(built['errors'])
            prims_by_uid[item['uid']] = built['primitives']
            item['bulge_mm'] = float(bulge)
            item['depth_mm'] = float(built['depth_mm'])
            item['separation_mm'] = built['separation_mm']
            item['middle_mm'] = built['middle_mm']
            item['family'] = FAMILY
            item['primitives'] = built['primitives']
        attempt = dict(step_mm=float(step_mm), build_errors=len(build_errors))
        if build_errors:
            attempt['d56'] = None
            attempt['valid'] = False
            attempts.append(attempt)
            continue
        d56 = evaluate_same_side(prims_by_uid)
        attempt['d56'] = dict(valid=d56['valid'],
                              conflict_count=d56['conflict_count'],
                              crossing_events=d56['crossing_events'])
        attempt['valid'] = bool(d56['valid'])
        attempts.append(attempt)
        if d56['valid']:
            chosen = dict(step_mm=float(step_mm), ladder=ladder, d56=d56,
                          prims_by_uid=prims_by_uid,
                          build_errors=build_errors)
            break
    if chosen is None:
        # no depth step of the ladder yields a clean strict-D56 group: report
        # every record of the group as a failure instead of routing a conflict.
        last = attempts[-1] if attempts else None
        for item in items:
            failures.append(dict(uid=item['uid'],
                                 reason='no_conflict_free_depth_ladder',
                                 detail=last))
        result['failures'] = failures
        result['notes'] = notes
        result['stats'] = dict(records=len(records), attempts=attempts,
                               elapsed_s=round(time.perf_counter() - started, 3))
        return result
    # -- route entries --------------------------------------------------------
    routes = []
    for item in items:
        routes.append(dict(
            uid=item['uid'],
            record=item['record'],
            primitives=item['primitives'],
            bulge_mm=float(item['bulge_mm']),
            depth_mm=float(item['depth_mm']),
            separation_mm=float(item['separation_mm']),
            middle_straight_mm=float(item['middle_mm']),
            nesting_level=int(item['ancestors']),
            nesting_parent=item['parent'],
            rank=int(item['rank']),
            parent_uid=item['parent'],
            children=list(item['children']),
            interval_mm=list(item['interval_mm']),
            family=FAMILY,
            valid=True,
            errors=[],
            route=None,
        ))
    min_depth = min(route['depth_mm'] for route in routes)
    max_depth = max(route['depth_mm'] for route in routes)
    result['routes'] = routes
    result['failures'] = failures
    result['depth_ladder'] = chosen['ladder']
    result['depth_step_mm'] = chosen['step_mm']
    result['base_bulge_mm'] = float(base_bulge)
    result['base_bulge'] = dict(base_info)
    result['min_bulge_mm'] = float(base_payload['minimum_bulge_mm'])
    result['d56'] = chosen['d56']
    result['attempts'] = attempts
    result['stats'] = dict(
        records=len(routes),
        routed=sum(1 for route in routes if route['valid']),
        failed=len(failures),
        layer_id=layer_id,
        side=side,
        plane=plane,
        depth_step_mm=chosen['step_mm'],
        base_bulge_mm=float(base_bulge),
        base_bulge_extra_mm=float(base_bulge_extra),
        unified_base_bulge_floor_mm=float(MIN_BASE_BULGE_MM),
        first_arc_edge_clearance_mm=float(base_bulge),
        base_bulge_components=dict(base_info),
        min_bulge_mm=float(base_payload['minimum_bulge_mm']),
        transition_required=bool(base_payload['transition_required']),
        footprint_mm=float(base_payload['footprint_mm']),
        min_depth_mm=float(min_depth),
        max_depth_mm=float(max_depth),
        nesting_levels=int(max_rank + 1),
        max_nesting_level=int(max_rank),
        separation_min_mm=float(min(route['separation_mm'] for route in routes)),
        separation_max_mm=float(max(route['separation_mm'] for route in routes)),
        d56_conflicts=int(chosen['d56']['conflict_count']),
        d56_crossing_events=int(chosen['d56']['crossing_events']),
        d56_evaluations=int(chosen['d56']['evaluations']),
        attempts=attempts,
        elapsed_s=round(time.perf_counter() - started, 6),
    )
    if log is not None:
        log(f'[u_geometry] L{layer_id} {side}: n={len(routes)} '
            f'step={chosen["step_mm"]:.2f} base_bulge={base_bulge:.2f} '
            f'(floor={MIN_BASE_BULGE_MM:.1f}) '
            f'bulge={base_bulge:.2f}..'
            f'{base_bulge + chosen["step_mm"] * max_rank:.2f} '
            f'depth={min_depth:.2f}..{max_depth:.2f} '
            f'nest={max_rank + 1} d56_conflicts={chosen["d56"]["conflict_count"]} '
            f'crossings={chosen["d56"]["crossing_events"]}')
    return result


# ---------------------------------------------------------------------------
# convenience depth table (used by the self-check entry point and reports)
# ---------------------------------------------------------------------------
def depth_table(layer_result):
    """JSON-ready depth table of one layer/side result."""
    rows = []
    for route in layer_result['routes']:
        rows.append(dict(
            uid=route['uid'],
            interval_mm=list(route['interval_mm']),
            span_mm=float(route['interval_mm'][1] - route['interval_mm'][0]),
            separation_mm=float(route['separation_mm']),
            nesting_level=int(route['nesting_level']),
            rank=int(route['rank']),
            parent_uid=route['parent_uid'],
            bulge_mm=float(route['bulge_mm']),
            depth_mm=float(route['depth_mm']),
            family=route['family'],
        ))
    return rows
