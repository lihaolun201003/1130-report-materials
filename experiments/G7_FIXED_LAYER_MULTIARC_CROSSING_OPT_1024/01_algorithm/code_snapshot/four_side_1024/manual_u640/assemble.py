# -*- coding: utf-8 -*-
"""Assembly + whole-board geometric integration of the 640 routes.

Responsibilities
----------------
* merge the manual fixed-U routes (L1–L6) and the automatic routes (L7+) into the
  single 640-record result set; every input record must be represented exactly
  once, as a routed record or as a failed record with a reason;
* build the true-3D collision world (:class:`four_side_1024.l3d.world.World`),
  which checks **same physical plane** conflicts with the frozen strict D56 index
  and **cross-plane** clearance in 3D;
* count the legal crossings per physical plane (they are *not* violations), for
  the loss/statistics tables;
* produce the per-layer / per-plane statistics used by the report and export.

Nothing in this module relaxes a constraint: a route the world rejects stays
rejected and is reported with its blockers.
"""
from __future__ import annotations

import math
import time
from collections import Counter, OrderedDict

from . import config as C
from . import paths2d as P


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------
def merge_routes(data, manual_result, auto_result, log=print):
    """Merge the two router outputs into one ordered 640-record list.

    ``manual_result`` / ``auto_result`` may be ``(routes, failures, stats)``
    tuples (the router contract) or plain lists of routes.
    """
    def _split(result):
        if result is None:
            return [], [], {}
        if isinstance(result, tuple):
            routes = list(result[0] or [])
            failures = list(result[1] or [])
            stats = dict(result[2] or {}) if len(result) > 2 else {}
            return routes, failures, stats
        return list(result), [], {}

    manual_routes, manual_failed, manual_stats = _split(manual_result)
    auto_routes, auto_failed, auto_stats = _split(auto_result)

    merged = OrderedDict()
    for route in manual_routes + auto_routes:
        uid = route['uid']
        if uid in merged:
            raise ValueError(f'duplicate routed record {uid}')
        merged[uid] = route
    failures = OrderedDict()
    for failed in manual_failed + auto_failed:
        uid = failed['uid']
        if uid in merged or uid in failures:
            raise ValueError(f'record {uid} reported both routed and failed')
        failures[uid] = failed

    missing = [record['uid'] for record in data.records
               if record['uid'] not in merged and record['uid'] not in failures]
    if missing:
        for uid in missing:
            failures[uid] = P.failed_record(
                data.record(uid), 'router_returned_no_route_for_record',
                logical_layer=data.record(uid)['assigned_layer'])
    extra = [uid for uid in list(merged) + list(failures)
             if uid not in data.by_uid]
    if extra:
        raise ValueError(f'unknown records in router output: {extra[:5]}')

    order = [record['uid'] for record in data.records]
    routes = [merged[uid] for uid in order if uid in merged]
    failed = [failures[uid] for uid in order if uid in failures]
    log(f'[assemble] routed={len(routes)} failed={len(failed)} '
        f'(manual={len(manual_routes)}/{len(manual_failed)} '
        f'auto={len(auto_routes)}/{len(auto_failed)})')
    return routes, failed, dict(manual=manual_stats, auto=auto_stats)


# ---------------------------------------------------------------------------
# physical plane helpers
# ---------------------------------------------------------------------------
def plane_key(z_mm):
    return round(float(z_mm), 9)


def logical_layer_of_z(stack, z_mm):
    """Best logical layer label of one physical height (L1 rows included)."""
    z = plane_key(z_mm)
    if abs(z - C.Z1_MM) <= 1e-9:
        return C.INTERFACE_LAYER_ID
    if abs(z - C.Z2_MM) <= 1e-9:
        return C.INTERFACE_LAYER_ID
    for layer_id in stack.routing_layer_ids:
        if abs(z - C.layer_z(layer_id)) <= 1e-9:
            return layer_id
    return None


def used_logical_layers(routes):
    layers = set()
    for route in routes:
        if route.get('logical_layer') is not None:
            layers.add(int(route['logical_layer']))
        for part in route.get('parts') or []:
            if part['kind'] == 'flat':
                layer_id = logical_layer_of_z_key(part['z_mm'])
                if layer_id is not None:
                    layers.add(int(layer_id))
    return sorted(layers)


def used_physical_planes(routes):
    planes = set()
    for route in routes:
        for part in route.get('parts') or []:
            if part['kind'] == 'flat':
                planes.add(plane_key(part['z_mm']))
    return sorted(planes)


# ---------------------------------------------------------------------------
# world checks + crossing statistics
# ---------------------------------------------------------------------------
def build_world(stack, clearance=None):
    from four_side_1024.l3d.world import World
    return World(stack, clearance=C.CLEARANCE_MM if clearance is None else clearance)


def check_against_world(routes, world, log=print):
    """Incremental world check; returns ``(violations, accepted, elapsed_s)``.

    The world is populated in a deterministic order (interface planes first, then
    ascending physical height).  A route is only added when the world does not
    reject it, so a violation never silently disappears.
    """
    def order_key(route):
        # manual L1-L6 routes are the fixed reference set: they are inserted
        # first so that the automatic routes are the ones checked against them.
        manual = 0 if route.get('assignment') == 'manual_fixed_u' else 1
        heights = [plane_key(part['z_mm']) for part in route.get('parts') or []
                   if part['kind'] == 'flat']
        return (manual, min(heights) if heights else 99.0, route['uid'])

    violations = []
    accepted = []
    started = time.perf_counter()
    for index, route in enumerate(sorted(routes, key=order_key), 1):
        found = world.check_route(route)
        if found:
            violations.append(dict(uid=route['uid'],
                                   logical_layer=route.get('logical_layer'),
                                   violations=found[:8]))
            continue
        world.add_route(route)
        accepted.append(route)
        if index % 128 == 0:
            log(f'[assemble] world check {index}/{len(routes)} '
                f'accepted={len(accepted)} violations={len(violations)} '
                f'elapsed={time.perf_counter() - started:.1f}s')
    return violations, accepted, time.perf_counter() - started


def plane_crossings(routes, log=print):
    """Legal-crossing count per physical plane using the frozen strict index.

    One route may contribute several flat sub-chains to the same physical plane
    (the two arms of a lifted U are both at the port height), so every part is
    indexed under ``route_id * 1000 + part_index`` exactly like
    :class:`four_side_1024.l3d.world.PlaneWorld`.
    """
    from four_side_1024.d56.index import D56Index, prepare

    per_plane = OrderedDict()

    def entry_for(key):
        entry = per_plane.get(key)
        if entry is None:
            entry = dict(
                index=D56Index(width=C.WIDTH_MM, gap=C.EDGE_GAP_MM,
                               sagitta=C.SAGITTA_MM,
                               min_cross_angle_deg=C.MIN_CROSS_ANGLE_DEG,
                               crossing_policy='strict'),
                routes=set(), part_count=0, conflicts=[], crossing_events=0,
                pairs=set())
            per_plane[key] = entry
        return entry

    for route in routes:
        for part_index, part in enumerate(route.get('parts') or []):
            if part['kind'] != 'flat':
                continue
            key = plane_key(part['z_mm'])
            entry = entry_for(key)
            prepared = prepare(part['primitives'])
            result = entry['index'].evaluate(prepared)
            entry['part_count'] += 1
            entry['routes'].add(int(route['route_id']))
            if result is not None and not result.valid:
                entry['conflicts'].append(dict(
                    uid=route['uid'], z_mm=key,
                    reason=getattr(result, 'reason', None),
                    blockers=list(getattr(result, 'blockers', []) or [])[:8]))
            if result is not None:
                for crossing in getattr(result, 'crossings', []) or []:
                    if not isinstance(crossing, dict):
                        continue
                    entry['crossing_events'] += 1
                    other_part = crossing.get('other')
                    if other_part is not None:
                        entry['pairs'].add(tuple(sorted(
                            (int(route['route_id']), int(other_part) // 1000))))
            entry['index'].add(route['route_id'] * 1000 + part_index, prepared)

    summary = OrderedDict()
    for key, entry in per_plane.items():
        summary[str(key)] = dict(
            z_mm=key, logical_layer=logical_layer_of_z_key(key),
            routes=len(entry['routes']),
            parts=entry['part_count'],
            conflicts=len(entry['conflicts']),
            conflict_examples=entry['conflicts'][:5],
            crossing_events=entry['crossing_events'],
            crossing_pairs=len(entry['pairs']),
        )
    overall = sum(item['crossing_events'] for item in summary.values())
    log(f'[assemble] legal crossings per plane: '
        f'{ {key: item["crossing_events"] for key, item in summary.items()} } '
        f'total={overall}')
    return summary, overall


def logical_layer_of_z_key(z_mm):
    z = plane_key(z_mm)
    if abs(z - C.Z1_MM) <= 1e-9 or abs(z - C.Z2_MM) <= 1e-9:
        return C.INTERFACE_LAYER_ID
    for layer_id in range(2, C.MAX_LOGICAL_LAYERS + 1):
        if abs(z - C.layer_z(layer_id)) <= 1e-9:
            return layer_id
    return None


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------
def per_layer_statistics(data, routes, failures):
    """Routing counts per logical layer (manual L1–L6 and automatic L7+)."""
    by_layer = OrderedDict()
    assigned = {}
    for route in routes:
        layer_id = int(route['logical_layer'])
        by_layer.setdefault(layer_id, []).append(route)
        assigned[route['uid']] = layer_id
    for failed in failures:
        layer_id = failed.get('logical_layer')
        if layer_id is None:
            layer_id = 'unassigned'
        by_layer.setdefault(layer_id, [])
        assigned[failed['uid']] = layer_id

    rows = []
    for layer_id in sorted(by_layer, key=lambda value: (isinstance(value, str),
                                                        value if isinstance(value, str)
                                                        else int(value))):
        layer_routes = [item for item in by_layer[layer_id]
                        if isinstance(item, dict)]
        uids = [route['uid'] for route in layer_routes]
        failed_layer = [failed for failed in failures
                        if assigned.get(failed['uid']) == layer_id]
        total_length = sum(float(route['length_mm']) for route in layer_routes)
        uids_manual = [uid for uid in uids
                       if data.record(uid)['assignment'] == 'manual_fixed_u']
        z_values = sorted({plane_key(part['z_mm'])
                           for route in layer_routes
                           for part in route.get('parts') or []
                           if part['kind'] == 'flat'})
        # the layer's own routing height (L1 keeps the interface row heights)
        if isinstance(layer_id, str):
            layer_z = None
        elif layer_id == C.INTERFACE_LAYER_ID:
            layer_z = sorted({float(route['source_z_mm']) for route in layer_routes})
        else:
            layer_z = float(C.layer_z(layer_id))
        rows.append(dict(
            logical_layer=int(layer_id) if not isinstance(layer_id, str) else None,
            layer_label=f'L{layer_id}' if not isinstance(layer_id, str) else layer_id,
            layer_type=('interface' if layer_id == C.INTERFACE_LAYER_ID else
                        ('routing' if not isinstance(layer_id, str) else 'unassigned')),
            physical_z_mm=z_values,
            layer_physical_z_mm=layer_z,
            routes=len(layer_routes),
            manual_routes=len(uids_manual),
            automatic_routes=len(layer_routes) - len(uids_manual),
            failed=len(failed_layer),
            total_length_mm=round(total_length, 6),
            propagation_loss_db=round(total_length / 10.0
                                      * C.PROPAGATION_LOSS_DB_PER_CM, 9),
        ))
    return rows


def loss_summary(routes):
    """Propagation-only loss (the only calibrated term of the existing model)."""
    total_length = sum(float(route['length_mm']) for route in routes)
    propagation = total_length / 10.0 * C.PROPAGATION_LOSS_DB_PER_CM
    return dict(
        model='existing fslw loss record',
        propagation_loss_db_per_cm=C.PROPAGATION_LOSS_DB_PER_CM,
        propagation_loss_db=round(propagation, 6),
        total_length_mm=round(total_length, 6),
        bend_loss=dict(status='pending',
                       reason=('four_side_1024/fslw/config.py declares the bend-loss '
                               'function unknown_uncalibrated for this glass '
                               'process; no number is invented here')),
        crossing_loss=dict(status='pending',
                           reason=('four_side_1024/fslw/config.py declares the '
                                   'crossing-loss function unknown_uncalibrated; the '
                                   'crossing count is reported as a geometric metric')),
    )


def assemble(data, stack, manual_result, auto_result, log=print):
    """Full integration: merge, world-check, crossing audit, statistics."""
    started = time.perf_counter()
    routes, failures, router_stats = merge_routes(data, manual_result, auto_result,
                                                  log=log)
    log('[assemble] building 3D collision world ...')
    world = build_world(stack)
    violations, world_accepted, world_elapsed = check_against_world(routes, world,
                                                                   log=log)
    log('[assemble] auditing legal crossings per physical plane ...')
    crossings, crossing_total = plane_crossings(routes, log=log)
    layers = used_logical_layers(routes)
    planes = used_physical_planes(routes)
    per_layer = per_layer_statistics(data, routes, failures)
    result = dict(
        routes=routes,
        failures=failures,
        router_stats=router_stats,
        world=world,
        world_violations=violations,
        world_accepted=len(world_accepted),
        world_elapsed_s=round(world_elapsed, 3),
        plane_crossings=crossings,
        crossing_events_total=crossing_total,
        used_logical_layers=layers,
        used_physical_planes=planes,
        logical_layer_count=len(layers),
        physical_plane_count=len(planes),
        per_layer=per_layer,
        loss=loss_summary(routes),
        elapsed_s=round(time.perf_counter() - started, 3),
    )
    log(f'[assemble] done: routed={len(routes)} failed={len(failures)} '
        f'world_violations={len(violations)} layers={layers} '
        f'physical_planes={planes}')
    return result
