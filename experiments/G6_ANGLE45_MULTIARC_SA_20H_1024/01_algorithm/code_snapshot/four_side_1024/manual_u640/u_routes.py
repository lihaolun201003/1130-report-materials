# -*- coding: utf-8 -*-
"""L1-L6 manual fixed-U routes (284 records) of the 640-channel round.

The 284 records of the input CSV are grouped by ``assigned_layer`` (L1 = 64,
L2 = 64, L3 = 64, L4 = 64, L5 = 13, L6 = 15) and by board side, and every group
is routed with the geometric U-depth algorithm of
:mod:`four_side_1024.manual_u640.u_geometry`:

* L1 is the flat interface layer: :func:`paths2d.build_flat_route` (z = 0.0 for
  the ``z1`` rows; every L1 record of this CSV is a ``z1`` record).
* L2-L6 are elevated: :func:`paths2d.build_lifted_route` builds the
  ``[L1, Lk, L1]`` route with two R15 elevation S-curves on the two port
  straights.  When the transition placement is infeasible for the current
  bulge the whole ``(layer, side)`` ladder is retried one millimetre deeper
  (never the other way round) - a ``None`` route is never accepted silently.
* every manual U uses the unified 12 mm edge-clearance floor
  (:data:`four_side_1024.manual_u640.u_geometry.MIN_BASE_BULGE_MM`): its first
  90 deg arc starts at least 12 mm inward from the board edge, so the
  ``0..12 mm`` edge band stays free for the elevation S-curves of the
  automatic L7+ routes.  The resolved per-group base bulge is reported in
  ``stats['base_bulge']``.
* every 2D chain passes the frozen canonical validator, and every
  ``(layer, side)`` group passes the frozen strict D56 index; the whole 284-route
  set is then checked in true 3D with :class:`four_side_1024.l3d.world.World`
  (same physical plane strict D56 + cross-plane 0.08 mm 3D clearance), in the
  same deterministic order that the assembly step uses.

Nothing is relocated or re-paired: the port identities and the CSV connection
relations are carried unchanged into every route record.
"""
from __future__ import annotations

import math
import time
from collections import Counter, OrderedDict

from . import config as C
from . import paths2d as P
from . import u_geometry as UG

__all__ = ['build_manual_u_routes', 'self_check_3d', 'self_check_planes',
           'board_bounds', 'route_precheck']

MANUAL_LAYER_IDS = tuple(C.MANUAL_LAYER_IDS)
SIDES = 'NSEW'
TOL = 1e-9


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _plane_key(z_mm):
    return round(float(z_mm), 9)


def _route_min_z(route):
    heights = [_plane_key(part['z_mm']) for part in route.get('parts') or []
               if part['kind'] == 'flat']
    return min(heights) if heights else 99.0


def _assemble_order(routes):
    return sorted(routes, key=lambda route: (_route_min_z(route), route['uid']))


def _join_audit(routes):
    from four_side_1024.l3d import paths as L3D_PATHS
    joins = 0
    bad = []
    for route in routes:
        for join in L3D_PATHS.route_transition_join(route):
            joins += 1
            if not (join['position_ok'] and join['tangent_ok']):
                bad.append(dict(uid=route['uid'], join=join))
    return dict(joins=joins, bad=bad, bad_count=len(bad),
                all_ok=not bad)


def route_precheck(routes, radius=UG.RADIUS_MM):
    """Per-route audits: 2D chain, exact radius, summary, port identity."""
    inward_of = dict(N=(0.0, -1.0), S=(0.0, 1.0),
                     E=(-1.0, 0.0), W=(1.0, 0.0))
    bad_chain = []
    bad_radius = []
    bad_summary = []
    bad_ports = []
    for route in routes:
        primitives = route.get('primitives_2d') or []
        side = route.get('source_side')
        if not primitives or side not in inward_of:
            bad_chain.append(dict(uid=route['uid'],
                                  errors=['empty_chain_or_unknown_side']))
            continue
        inward = inward_of[side]
        # ``inputs`` gives both endpoints the same inward normal; the frozen
        # pose convention is start_dir = inward, end_dir = -inward.
        port_record = dict(
            uid=route['uid'],
            source_xy=list(route['source_xy_mm']),
            target_xy=list(route['target_xy_mm']),
            source_endpoint=dict(inward=list(inward)),
            target_endpoint=dict(inward=list(inward)),
        )
        ok, errors = P.validate_2d_chain(primitives, port_record, radius=radius)
        if not ok:
            bad_chain.append(dict(uid=route['uid'], errors=errors))
        radii = [float(prim['radius']) for prim in primitives
                 if prim.get('kind') == 'arc']
        if not radii or any(abs(value - float(radius)) > 1e-9
                            for value in radii):
            bad_radius.append(dict(uid=route['uid'], radii=radii))
        stored = route.get('min_bend_radius_mm')
        if stored is None or abs(float(stored) - float(radius)) > 1e-9:
            bad_radius.append(dict(uid=route['uid'],
                                   min_bend_radius_mm=stored))
        try:
            summary = P.route_summary(route)
            if not summary or summary['uid'] != route['uid']:
                bad_summary.append(route['uid'])
        except Exception as error:  # noqa: BLE001 - an audit must report, not raise
            bad_summary.append(dict(uid=route['uid'], error=str(error)))
        if (math.dist(primitives[0]['p0'], route['source_xy_mm']) > 1e-6
                or math.dist(primitives[-1]['p1'],
                             route['target_xy_mm']) > 1e-6):
            bad_ports.append(route['uid'])
    return dict(bad_2d_chain=bad_chain, bad_radius=bad_radius,
                bad_summary=bad_summary, bad_port_pose=bad_ports,
                all_ok=not (bad_chain or bad_radius or bad_summary
                            or bad_ports))


def _primitive_bbox(primitive):
    """Exact axis-aligned bbox of one D56 line/arc (arc extrema included)."""
    if primitive.get('kind') == 'line':
        p0, p1 = primitive['p0'], primitive['p1']
        return (min(p0[0], p1[0]), min(p0[1], p1[1]),
                max(p0[0], p1[0]), max(p0[1], p1[1]))
    center = primitive['center']
    radius = float(primitive['radius'])
    start = float(primitive['start_angle'])
    sweep = float(primitive['sweep'])
    xs = [primitive['p0'][0], primitive['p1'][0]]
    ys = [primitive['p0'][1], primitive['p1'][1]]
    for k in range(-4, 13):
        angle = k * math.pi / 2.0
        if _angle_in_arc(angle, start, sweep):
            xs.append(center[0] + radius * math.cos(angle))
            ys.append(center[1] + radius * math.sin(angle))
    return (min(xs), min(ys), max(xs), max(ys))


def board_bounds(routes, board=UG.BOARD_MM, width=UG.WIDTH_MM, tol=1e-6):
    """Board containment audit of the centre lines plus the terminal envelope.

    The 2x16 port table of the frozen input model puts every port centre exactly
    on the board edge, so the centre line of a legal route may touch
    ``0``/``150`` but must never leave the board.  The 0.05 mm waveguide width
    therefore extends at most 0.025 mm outside the board **at the two terminal
    port faces only** (the fixed connector interface, ports may not be moved);
    that inherent overrun is reported separately from a centre-line overrun.
    """
    half_width = float(width) / 2.0
    low = 0.0
    high = float(board)
    min_x = min_y = float('inf')
    max_x = max_y = float('-inf')
    offenders = []
    for route in routes:
        route_offender = None
        for part in route.get('parts') or []:
            if part['kind'] != 'flat':
                continue
            for primitive in part['primitives']:
                bbox = _primitive_bbox(primitive)
                min_x = min(min_x, bbox[0])
                min_y = min(min_y, bbox[1])
                max_x = max(max_x, bbox[2])
                max_y = max(max_y, bbox[3])
                if route_offender is None and (
                        bbox[0] < low - tol or bbox[1] < low - tol
                        or bbox[2] > high + tol or bbox[3] > high + tol):
                    route_offender = dict(
                        uid=route['uid'], kind=primitive['kind'],
                        bbox=[float(value) for value in bbox])
        if route_offender is not None:
            offenders.append(route_offender)
    terminal_overrun = 0.0
    for route in routes:
        for key in ('source_xy_mm', 'target_xy_mm'):
            x, y = (float(value) for value in route[key])
            edge_distance = min(x, y, high - x, high - y)
            overrun = half_width - edge_distance
            if overrun > terminal_overrun:
                terminal_overrun = overrun
    return dict(
        ok=not offenders,
        check='centre-line inside 0..board; waveguide width envelope audited',
        min_coord_mm=[float(min_x), float(min_y)],
        max_coord_mm=[float(max_x), float(max_y)],
        board_mm=float(board),
        allowed_min_mm=float(low), allowed_max_mm=float(high),
        terminal_port_envelope_overrun_mm=round(float(terminal_overrun), 9),
        terminal_port_note=('the frozen 2x16 port model puts the port centres on '
                            'the board edge; the half width outside the board at '
                            'the two terminal port faces is the connector '
                            'interface (ports may not be moved)'),
        offenders=offenders[:20], offender_count=len(offenders))


def _angle_in_arc(angle, start, sweep):
    two_pi = 2.0 * math.pi
    if sweep >= 0.0:
        delta = (angle - start) % two_pi
        return delta <= sweep + 1e-12
    delta = (start - angle) % two_pi
    return delta <= (-sweep) + 1e-12


# ---------------------------------------------------------------------------
# true-3D self check
# ---------------------------------------------------------------------------
def self_check_3d(routes, stack, log=None):
    """Incremental true-3D world check of the produced routes.

    The routes are added in the assembly order (lowest physical plane first,
    then uid) and every route is verified against everything already placed,
    exactly like :func:`four_side_1024.manual_u640.assemble.check_against_world`.
    Returns ``{routes, accepted, violations, plane_counts, elapsed_s}``.
    """
    from four_side_1024.l3d.world import World

    started = time.perf_counter()
    world = World(stack, clearance=C.CLEARANCE_MM)
    violations = []
    accepted = 0
    for route in _assemble_order(routes):
        found = world.check_route(route)
        if found:
            violations.append(dict(uid=route['uid'],
                                   logical_layer=route.get('logical_layer'),
                                   violations=found[:8]))
            continue
        world.add_route(route)
        accepted += 1
        if log is not None and accepted % 128 == 0:
            log(f'[u_routes] 3D self-check {accepted}/{len(routes)} '
                f'violations={len(violations)}')
    payload = dict(routes=len(routes), accepted=int(accepted),
                   violations=violations, violation_count=len(violations),
                   plane_counts={str(key): int(value)
                                 for key, value in world.planes.counts().items()},
                   elapsed_s=round(time.perf_counter() - started, 3),
                   note=('same physical plane: frozen strict D56; different '
                         'physical planes: true 3D 0.08 mm centre-line clearance'))
    if log is not None:
        log(f'[u_routes] 3D self-check: accepted={accepted}/{len(routes)} '
            f'violations={len(violations)} '
            f'planes={list(payload["plane_counts"])} '
            f'elapsed={payload["elapsed_s"]}s')
    return payload


# ---------------------------------------------------------------------------
# same-plane legal-crossing / conflict audit (assemble-compatible semantics)
# ---------------------------------------------------------------------------
def self_check_planes(routes, log=None):
    """Strict D56 audit of every physical plane touched by the manual U routes."""
    from four_side_1024.d56.index import D56Index, prepare

    planes = OrderedDict()

    def entry(key):
        item = planes.get(key)
        if item is None:
            item = dict(
                index=D56Index(width=UG.WIDTH_MM, gap=UG.EDGE_GAP_MM,
                               sagitta=UG.SAGITTA_MM,
                               min_cross_angle_deg=UG.MIN_CROSS_ANGLE_DEG,
                               crossing_policy='strict'),
                routes=set(), parts=0, conflicts=[], crossings=0,
                min_spacing_mm=None)
            planes[key] = item
        return item

    for route in routes:
        for part_index, part in enumerate(route.get('parts') or []):
            if part['kind'] != 'flat':
                continue
            key = _plane_key(part['z_mm'])
            item = entry(key)
            prepared = prepare(part['primitives'])
            result = item['index'].evaluate(prepared)
            item['parts'] += 1
            item['routes'].add(int(route['route_id']))
            if result is not None and not result.valid:
                item['conflicts'].append(dict(
                    uid=route['uid'], reason=getattr(result, 'reason', None),
                    blockers=list(getattr(result, 'blockers', []) or [])[:8],
                    min_spacing_mm=getattr(result, 'min_spacing_mm', None)))
            if result is not None:
                item['crossings'] += len(getattr(result, 'crossings', []) or [])
                spacing = getattr(result, 'min_spacing_mm', None)
                if spacing is not None:
                    item['min_spacing_mm'] = (
                        spacing if item['min_spacing_mm'] is None
                        else min(item['min_spacing_mm'], spacing))
            item['index'].add(int(route['route_id']) * 1000 + part_index,
                              prepared)
    summary = OrderedDict()
    total_conflicts = 0
    total_crossings = 0
    for key, item in planes.items():
        total_conflicts += len(item['conflicts'])
        total_crossings += item['crossings']
        summary[str(key)] = dict(
            z_mm=key,
            routes=len(item['routes']),
            parts=int(item['parts']),
            conflicts=len(item['conflicts']),
            conflict_examples=item['conflicts'][:5],
            crossings=int(item['crossings']),
            min_spacing_mm=item['min_spacing_mm'])
    if log is not None:
        log(f'[u_routes] same-plane audit: conflicts={total_conflicts} '
            f'crossings={total_crossings} planes={list(summary)}')
    return dict(planes=summary, conflict_count=int(total_conflicts),
                crossings=int(total_crossings))


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------
def _failed(data, uid, reason, logical_layer=None, detail=None):
    return P.failed_record(data.record(uid), reason,
                           logical_layer=logical_layer, detail=detail)


def _enrich_route(route, entry, layer_id, group, base_bulge):
    """Attach the U-depth diagnostics to one route record."""
    route['u_side'] = group['side']
    route['u_family'] = entry['family']
    route['u_bulge_mm'] = float(entry['bulge_mm'])
    route['u_depth_mm'] = float(entry['depth_mm'])
    route['u_separation_mm'] = float(entry['separation_mm'])
    route['u_middle_straight_mm'] = float(entry.get('middle_straight_mm')
                                         or 0.0)
    route['u_nesting_level'] = int(entry['nesting_level'])
    route['u_rank'] = int(entry['rank'])
    route['u_parent_uid'] = entry.get('parent_uid')
    route['u_interval_mm'] = list(entry.get('interval_mm') or [])
    route['u_depth_step_mm'] = float(group.get('depth_step_mm')
                                     or UG.DEFAULT_DEPTH_STEP_MM)
    route['u_base_bulge_mm'] = float(base_bulge)
    route['u_layer_plane'] = route.get('dataset')
    route['u_layer_side'] = f'L{layer_id}{route["u_side"]}'
    return route


def build_manual_u_routes(data, stack, radius=UG.RADIUS_MM, log=print):
    """Route the 284 manual fixed-U records of L1-L6.

    Returns
    -------
    (routes, failures, stats)
        ``routes``: 284 ``l3d`` route dicts (L1 flat, L2-L6 lifted), each with
        its U depth diagnostics; ``failures``: ``paths2d.failed_record`` items
        (empty on success); ``stats``: JSON-ready statistics including the
        per-layer/side depth table, the strict D56 audit and the true-3D
        self-check.
    """
    started = time.perf_counter()
    radius = float(UG.RADIUS_MM if radius is None else radius)
    routes = []
    failures = []
    group_results = []
    per_layer_side = OrderedDict()
    per_layer = OrderedDict()
    notes = []

    for layer_id in MANUAL_LAYER_IDS:
        sides = data.manual_sides(layer_id)
        group_name = None
        if data.manual_groups.get(layer_id):
            group_name = data.records_for(
                data.manual_groups[layer_id])[0]['manual_group']
        per_layer[layer_id] = dict(
            layer_id=int(layer_id), group=group_name,
            count=0, routed=0, failed=0, sides=OrderedDict(),
            depth_min_mm=None, depth_max_mm=None, planes=set())
        for side in SIDES:
            uids = sides.get(side) or []
            if not uids:
                continue
            records = data.records_for(uids)
            base_extra = 0.0
            attempt = 0
            group = None
            probe_routes = {}
            while True:
                group = UG.build_layer_u_layer(
                    layer_id, side, records, stack, radius=radius,
                    base_bulge_extra=base_extra, log=log)
                probe_routes = {}
                if group['failures'] or layer_id == C.INTERFACE_LAYER_ID:
                    break
                infeasible = []
                for entry in group['routes']:
                    route = P.build_lifted_route(entry['record'],
                                                 entry['primitives'],
                                                 layer_id)
                    probe_routes[entry['uid']] = route
                    if route is None:
                        infeasible.append(entry['uid'])
                if not infeasible:
                    break
                base_extra += 1.0
                attempt += 1
                notes.append(f'L{layer_id}{side}: transition placement '
                             f'infeasible for {len(infeasible)} U(s) at '
                             f'bulge base {group["base_bulge_mm"]:.2f}; '
                             f'retrying +1.0 mm deeper')
                log(f'[u_routes] L{layer_id}{side}: build_lifted_route '
                    f'returned None for {len(infeasible)} route(s); '
                    f'retrying with base_bulge +{base_extra:.1f} mm')
                if attempt > 4:
                    break
            group['attempt_count'] = attempt
            group['base_bulge_extra_mm'] = float(base_extra)
            group_results.append(group)
            # -- materialise routes -------------------------------------------------
            group_routes = []
            if group['failures']:
                for failure in group['failures']:
                    uid = failure.get('uid')
                    if uid is None or uid not in data.by_uid:
                        continue
                    failures.append(_failed(
                        data, uid,
                        failure.get('reason') or 'u_geometry_failure',
                        logical_layer=layer_id,
                        detail=failure.get('detail')))
            else:
                for entry in group['routes']:
                    uid = entry['uid']
                    record = entry['record']
                    if layer_id == C.INTERFACE_LAYER_ID:
                        route = P.build_flat_route(record, entry['primitives'])
                    else:
                        route = probe_routes.get(uid)
                        if route is None:
                            route = P.build_lifted_route(
                                record, entry['primitives'], layer_id)
                        if route is None:
                            failures.append(_failed(
                                data, uid, 'transition_placement_infeasible',
                                logical_layer=layer_id,
                                detail=dict(bulge_mm=entry['bulge_mm'],
                                            base_bulge_extra_mm=base_extra)))
                            continue
                    _enrich_route(route, entry, layer_id, group,
                                  group['base_bulge_mm'])
                    group_routes.append(route)
            routes.extend(group_routes)
            # -- per layer/side statistics -----------------------------------------
            depths = [float(entry['depth_mm'])
                      for entry in group['routes']] if not group['failures'] else []
            side_stats = dict(
                layer_id=int(layer_id), side=side,
                count=len(records), routed=len(group_routes),
                failed=len(records) - len(group_routes),
                dataset=records[0]['dataset'],
                depth_step_mm=group.get('depth_step_mm'),
                base_bulge_mm=group.get('base_bulge_mm'),
                base_bulge_extra_mm=float(base_extra),
                base_bulge_floor_mm=float(UG.MIN_BASE_BULGE_MM),
                first_arc_edge_clearance_mm=group.get('base_bulge_mm'),
                base_bulge_components=group.get('base_bulge'),
                min_bulge_mm=group.get('min_bulge_mm'),
                transition_required=(layer_id != C.INTERFACE_LAYER_ID),
                footprint_mm=(group.get('stats') or {}).get('footprint_mm'),
                depth_min_mm=(min(depths) if depths else None),
                depth_max_mm=(max(depths) if depths else None),
                nesting_levels=(group.get('stats') or {}).get('nesting_levels'),
                max_nesting_level=(group.get('stats') or {}).get('max_nesting_level'),
                separation_min_mm=(group.get('stats') or {}).get('separation_min_mm'),
                separation_max_mm=(group.get('stats') or {}).get('separation_max_mm'),
                d56_conflicts=(group.get('stats') or {}).get('d56_conflicts'),
                d56_crossing_events=(group.get('stats') or {}).get(
                    'd56_crossing_events'),
                transition_retries=int(attempt),
                depth_ladder=[dict(rank=entry['rank'],
                                   bulge_mm=float(entry['bulge_mm']),
                                   depth_mm=float(entry['depth_mm']),
                                   uids=list(entry['uids']))
                              for entry in group.get('depth_ladder') or []],
                depth_table=UG.depth_table(group) if not group['failures'] else [],
                failure_count=len(group['failures']),
            )
            per_layer_side[f'L{layer_id}{side}'] = side_stats
            per_layer[layer_id]['sides'][side] = side_stats
            per_layer[layer_id]['count'] += len(records)
            per_layer[layer_id]['routed'] += len(group_routes)
            per_layer[layer_id]['failed'] += len(records) - len(group_routes)
            for route in group_routes:
                for part in route.get('parts') or []:
                    if part['kind'] == 'flat':
                        per_layer[layer_id]['planes'].add(
                            _plane_key(part['z_mm']))
            layer_depths = [route['u_depth_mm'] for route in group_routes]
            if layer_depths:
                current_min = per_layer[layer_id]['depth_min_mm']
                current_max = per_layer[layer_id]['depth_max_mm']
                per_layer[layer_id]['depth_min_mm'] = (
                    min(layer_depths) if current_min is None
                    else min(current_min, min(layer_depths)))
                per_layer[layer_id]['depth_max_mm'] = (
                    max(layer_depths) if current_max is None
                    else max(current_max, max(layer_depths)))

    # -- completeness: never drop a record --------------------------------------
    routed_uids = {route['uid'] for route in routes}
    failed_uids = {failed['uid'] for failed in failures}
    for layer_id in MANUAL_LAYER_IDS:
        for uid in data.manual_groups[layer_id]:
            if uid in routed_uids or uid in failed_uids:
                continue
            failures.append(_failed(data, uid, 'no_route_built',
                                    logical_layer=layer_id))
    expected_total = sum(len(data.manual_groups[layer_id])
                         for layer_id in MANUAL_LAYER_IDS)
    duplicates = [uid for uid, count in Counter(
        route['uid'] for route in routes).items() if count > 1]
    if duplicates:
        notes.append(f'duplicate_routes:{duplicates[:5]}')

    # -- audits -----------------------------------------------------------------
    joins = _join_audit(routes)
    precheck = route_precheck(routes, radius=radius)
    bounds = board_bounds(routes)
    planes = self_check_planes(routes, log=log)
    world = self_check_3d(routes, stack, log=log)

    # -- statistics -------------------------------------------------------------
    all_depths = [float(route['u_depth_mm']) for route in routes]
    layer_rows = []
    for layer_id, item in per_layer.items():
        layer_routes = [route for route in routes
                        if int(route['logical_layer']) == int(layer_id)]
        layer_failures = [failed for failed in failures
                          if failed.get('logical_layer') == int(layer_id)]
        layer_rows.append(dict(
            logical_layer=int(layer_id),
            group=item['group'],
            count=int(item['count']),
            routed=int(item['routed']),
            failed=int(len(layer_failures)),
            planes=sorted(item['planes']),
            physical_z_mm=sorted(item['planes']),
            depth_min_mm=item['depth_min_mm'],
            depth_max_mm=item['depth_max_mm'],
            min_bend_radius_mm=(min((route['min_bend_radius_mm']
                                     for route in layer_routes
                                     if route.get('min_bend_radius_mm')),
                                    default=None)),
            total_length_mm=round(sum(float(route['length_mm'])
                                      for route in layer_routes), 6),
            avg_length_mm=(round(sum(float(route['length_mm'])
                                     for route in layer_routes)
                                 / len(layer_routes), 6)
                           if layer_routes else None),
            sides={side: dict(
                count=stats['count'], routed=stats['routed'],
                failed=stats['failed'],
                depth_min_mm=stats['depth_min_mm'],
                depth_max_mm=stats['depth_max_mm'],
                depth_step_mm=stats['depth_step_mm'],
                base_bulge_mm=stats['base_bulge_mm'],
                first_arc_edge_clearance_mm=stats['first_arc_edge_clearance_mm'],
                nesting_levels=stats['nesting_levels'],
                d56_conflicts=stats['d56_conflicts'],
                d56_crossing_events=stats['d56_crossing_events'],
                transition_retries=stats['transition_retries'])
                for side, stats in item['sides'].items()},
        ))
    base_bulge_groups = {key: float(value['base_bulge_mm'])
                         for key, value in per_layer_side.items()}
    base_bulge_per_layer = {}
    for layer_id, item in per_layer.items():
        values = [float(stats['base_bulge_mm'])
                  for stats in item['sides'].values()]
        base_bulge_per_layer[f'L{layer_id}'] = (values[0] if values
                                                and all(abs(value - values[0])
                                                        <= 1e-12
                                                        for value in values)
                                                else values)
    stats = dict(
        schema='four_side_1024_manual_u640_u_routes_stats_v1',
        module='four_side_1024.manual_u640.u_routes',
        radius_mm=float(radius),
        width_mm=float(UG.WIDTH_MM),
        edge_gap_mm=float(UG.EDGE_GAP_MM),
        clearance_mm=float(UG.CLEARANCE_MM),
        family=UG.FAMILY,
        expected_total=int(expected_total),
        routed=int(len(routes)),
        failed=int(len(failures)),
        complete=bool(len(routes) + len(failures) == expected_total),
        duplicate_uid_count=len(duplicates),
        manual_layer_ids=list(MANUAL_LAYER_IDS),
        per_layer=layer_rows,
        groups={key: {field: value for field, value in item.items()
                      if field not in ('depth_table',)}
                for key, item in per_layer_side.items()},
        base_bulge=dict(
            unified_edge_clearance_floor_mm=float(UG.MIN_BASE_BULGE_MM),
            transition_reserve_mm=float(UG.TRANSITION_MARGIN_MM),
            port_margin_mm=float(UG.PORT_MARGIN_MM),
            segment_margin_mm=float(UG.SEGMENT_MARGIN_MM),
            note=('every manual U uses '
                  'base_bulge = max(geometric transition minimum, 12 mm) '
                  '+ transition retry extra; the first 90 deg arc of a manual '
                  'U therefore starts >= 12 mm from the board edge, leaving the '
                  '0..12 mm edge band free for the automatic L7+ elevation '
                  'S-curves'),
            per_group=base_bulge_groups,
            per_layer=base_bulge_per_layer,
            min_mm=(min(base_bulge_groups.values())
                    if base_bulge_groups else None),
            max_mm=(max(base_bulge_groups.values())
                    if base_bulge_groups else None),
            all_at_or_above_floor=bool(base_bulge_groups) and all(
                value >= float(UG.MIN_BASE_BULGE_MM) - 1e-9
                for value in base_bulge_groups.values()),
            components={key: (value.get('base_bulge_components')
                              or value.get('base_bulge'))
                        for key, value in per_layer_side.items()},
        ),
        depth=dict(
            min_mm=(min(all_depths) if all_depths else None),
            max_mm=(max(all_depths) if all_depths else None),
            steps_by_group={key: value['depth_step_mm']
                            for key, value in per_layer_side.items()},
        ),
        nesting=dict(
            groups=len(per_layer_side),
            max_level=max((value['max_nesting_level'] or 0)
                          for value in per_layer_side.values()),
            per_group={key: value['nesting_levels']
                       for key, value in per_layer_side.items()},
        ),
        d56=dict(
            group_conflicts=sum((value['d56_conflicts'] or 0)
                                for value in per_layer_side.values()),
            group_crossing_events=sum((value['d56_crossing_events'] or 0)
                                      for value in per_layer_side.values()),
            plane_conflicts=int(planes['conflict_count']),
            plane_crossing_events=int(planes['crossings']),
            planes=planes['planes'],
        ),
        transition=dict(
            joins=int(joins['joins']),
            bad_joins=int(joins['bad_count']),
            all_position_and_tangent_ok=bool(joins['all_ok']),
            retries=int(sum(value['transition_retries']
                            for value in per_layer_side.values())),
        ),
        route_precheck=dict(
            all_ok=bool(precheck['all_ok']),
            bad_2d_chain=precheck['bad_2d_chain'][:10],
            bad_radius=precheck['bad_radius'][:10],
            bad_summary=precheck['bad_summary'][:10],
            bad_port_pose=precheck['bad_port_pose'][:10],
        ),
        board=bounds,
        world_self_check=world,
        depth_tables={key: value['depth_table']
                      for key, value in per_layer_side.items()},
        notes=notes,
        elapsed_s=round(time.perf_counter() - started, 3),
    )
    # drop the always-None placeholder kept out of the payload
    if log is not None:
        log(f'[u_routes] done: routed={len(routes)}/{expected_total} '
            f'failed={len(failures)} '
            f'depth={min(all_depths) if all_depths else 0:.2f}..'
            f'{max(all_depths) if all_depths else 0:.2f} mm '
            f'base_bulge={stats["base_bulge"]["min_mm"]:.2f}..'
            f'{stats["base_bulge"]["max_mm"]:.2f} mm '
            f'd56_conflicts={stats["d56"]["group_conflicts"]} '
            f'world_violations={world["violation_count"]} '
            f'elapsed={stats["elapsed_s"]}s')
    return routes, failures, stats


# ---------------------------------------------------------------------------
# self-check entry point
# ---------------------------------------------------------------------------
def main(argv=None):
    import argparse

    from . import inputs as I
    from . import stack as S

    parser = argparse.ArgumentParser(
        description='L1-L6 manual fixed-U routing self-check (284 records)')
    parser.add_argument('--csv', default=None, help='input CSV override')
    parser.add_argument('--json', default=None,
                        help='write the statistics JSON to this path')
    parser.add_argument('--quiet', action='store_true')
    args = parser.parse_args(argv)
    log = (lambda message: None) if args.quiet else print

    log('== manual_u640 L1-L6 fixed-U routing self-check ==')
    data = I.load_inputs(args.csv)
    stack = S.LayerStack(C.MAX_LOGICAL_LAYERS)
    log(f'inputs: {len(data.records)} records, '
        f'{sum(len(uids) for uids in data.manual_groups.values())} manual U, '
        f'input validation passed={data.validation["passed"]}')
    routes, failures, stats = build_manual_u_routes(data, stack, log=log)

    # per (layer, side) depth tables
    for key, table in stats['depth_tables'].items():
        summary = stats['groups'][key]
        log(f'== {key}  n={len(table)}  '
            f'step={summary["depth_step_mm"]:.2f} mm  '
            f'depth={summary["depth_min_mm"]:.2f}..'
            f'{summary["depth_max_mm"]:.2f} mm  '
            f'nesting={summary["nesting_levels"]} levels')
        log(f'   {"nest":>4} {"uid":<10} {"interval mm":<26} '
            f'{"span":>8} {"bulge":>7} {"depth":>7}  parent')
        for row in sorted(table, key=lambda item: (-item['depth_mm'],
                                                   item['uid'])):
            lo, hi = row['interval_mm']
            log(f'   {row["nesting_level"]:>4} {row["uid"]:<10} '
                f'[{lo:8.3f},{hi:8.3f}]        {row["span_mm"]:8.3f} '
                f'{row["bulge_mm"]:>7.3f} {row["depth_mm"]:>7.3f}  '
                f'{row["parent_uid"]}')
    log('')
    log('== self-check summary ==')
    log(f'routed                 : {stats["routed"]}/{stats["expected_total"]}')
    log(f'failed                 : {stats["failed"]}')
    log(f'complete               : {stats["complete"]}')
    log(f'U depth range          : {stats["depth"]["min_mm"]:.2f} .. '
        f'{stats["depth"]["max_mm"]:.2f} mm')
    log(f'U base bulge           : {stats["base_bulge"]["min_mm"]:.2f} .. '
        f'{stats["base_bulge"]["max_mm"]:.2f} mm '
        f'(unified edge-clearance floor '
        f'{stats["base_bulge"]["unified_edge_clearance_floor_mm"]:.2f} mm, '
        f'all_above_floor={stats["base_bulge"]["all_at_or_above_floor"]})')
    log(f'max nesting level      : {stats["nesting"]["max_level"]}')
    log(f'same-plane D56         : conflicts='
        f'{stats["d56"]["group_conflicts"]} '
        f'crossings={stats["d56"]["group_crossing_events"]}')
    log(f'plane audit            : conflicts={stats["d56"]["plane_conflicts"]} '
        f'crossings={stats["d56"]["plane_crossing_events"]}')
    log(f'transition joins       : {stats["transition"]["joins"]} joins '
        f'bad={stats["transition"]["bad_joins"]}')
    log(f'route precheck         : {"OK" if stats["route_precheck"]["all_ok"] else "FAIL"}')
    log(f'board bounds           : {"OK" if stats["board"]["ok"] else "FAIL"} '
        f'min={stats["board"]["min_coord_mm"]} '
        f'max={stats["board"]["max_coord_mm"]}')
    log(f'3D world self-check    : accepted='
        f'{stats["world_self_check"]["accepted"]}/'
        f'{stats["world_self_check"]["routes"]} '
        f'violations={stats["world_self_check"]["violation_count"]}')
    log(f'elapsed                : {stats["elapsed_s"]} s')
    if args.json:
        import json
        from pathlib import Path
        path = Path(args.json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(stats, ensure_ascii=False, indent=1,
                                   default=str), encoding='utf-8')
        log(f'statistics written to {path}')
    ok = (stats['complete'] and stats['routed'] == stats['expected_total']
          and stats['failed'] == 0
          and stats['d56']['group_conflicts'] == 0
          and stats['d56']['plane_conflicts'] == 0
          and stats['transition']['bad_joins'] == 0
          and stats['route_precheck']['all_ok']
          and stats['board']['ok']
          and stats['base_bulge']['all_at_or_above_floor']
          and stats['world_self_check']['violation_count'] == 0)
    log(f'SELF-CHECK {"PASS" if ok else "FAIL"}')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
