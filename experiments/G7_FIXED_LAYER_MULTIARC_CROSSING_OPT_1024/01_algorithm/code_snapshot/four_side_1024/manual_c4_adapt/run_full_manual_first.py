# -*- coding: utf-8 -*-
"""FULL manual-first 1024-channel pipeline (one bounded run).

1. 256 validated manual U's (L1-L4) are fixed 3D routes.
2. The other 736 frozen 2D routes are kept; the 276 routes that physically
   conflict with the manual U's (38 on z1, 238 on z2) are re-routed on their own
   plane with all other geometry (manual U's + non-conflicting frozen routes)
   kept fixed, using the existing candidate generators / D56 index.
3. The original crossing-lift (L5-L15) then assigns the 3D layers of the 768
   non-manual routes while the 256 manual routes stay fixed.
4. Full frozen validator, global crossing statistics, plots, comparison table.

Output: outputs/manual_c4_new_connectivity/MANUAL_GROUP_15L_MANUAL_FIRST_FULL/
"""
from __future__ import annotations

import json
import math
import sys
import time
from collections import Counter, OrderedDict
from pathlib import Path

ROOT = Path(r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D')
sys.path.insert(0, str(ROOT))

import numpy as np
from scipy.spatial import cKDTree

from four_side_1024.manual_c4_adapt import compare_15L as M
from four_side_1024.manual_c4_adapt import manual_u_geometry as UGEOM
from four_side_1024.manual_c4 import connectivity as CONN
from four_side_1024.manual_c4 import state as STATE
from four_side_1024.manual_c4.router import (BULGE_LADDER, INWARD,
                                            ManualGroupRouter,
                                            order_groups as ORDER_GROUPS)
from four_side_1024.v2opt import search as SEARCH
from four_side_1024.d56.index import prepare
from four_side_1024.d56.search import RouteResult
from four_side_1024.legacy_geometry import transform_primitives
from four_side_1024.l3d.world import World
from four_side_1024.v3c4 import lift_cross as LIFT
from four_side_1024.v3c4 import lift_cross_run as LIFT_RUN
from four_side_1024.r15 import u_geometry as UG
from four_side_1024.fslw import config as C
from four_side_1024.l3d import layers as LL

NEW_DIR = (ROOT / 'outputs/manual_c4_new_connectivity'
           / 'MANUAL_GROUP_15L_MANUAL_FIRST_FULL')
MANUAL_JSON = (ROOT / 'outputs/manual_c4_new_connectivity'
               / 'MANUAL_GROUP_15L_COMPARISON_FIXED/manual_first'
               / 'manual_isolated.json')
BUDGET = 600
CROSSING_LIFT_BUDGET_S = 480.0
MAX_GROUPS = 300


def log(message):
    print(message, flush=True)


def write_json(path, payload, indent=1):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=indent,
                                     default=str), encoding='utf-8')


# ---------------------------------------------------------------------------
# 1. fixed manual U's + frozen layout
# ---------------------------------------------------------------------------
def load_manual_routes():
    rows = json.loads(MANUAL_JSON.read_text(encoding='utf-8'))['results']
    connections = M.load_manual_connections()
    routes = OrderedDict()
    primitives = {}
    plans = {}
    for rid_text, row in rows.items():
        rid = int(rid_text)
        if row.get('failed'):
            continue
        connection = connections[rid]
        prims = row['primitives']
        layer = int(row['layer'])
        layer_z = 0.0 if layer == 1 else 0.65 + 0.15 * (layer - 2)
        if layer == 1:
            route = LIFT.flat_route(rid, 'z1', prims, row=1)
        else:
            plan = row['transition']
            route = LIFT.lift_route(connection['record'], 1, layer, layer_z,
                                    plan['rise_start'], plan['fall_start'],
                                    prims)
        if route is None:
            raise SystemExit(f'manual route {rid} could not be rebuilt')
        routes[rid] = route
        primitives[rid] = prims
        plans[rid] = row.get('transition')
    return routes, primitives, plans, connections


def load_frozen_layout():
    layout = json.loads((M.V4_ROOT / 'routes_1024.json')
                        .read_text(encoding='utf-8'))
    records = {int(record['route_id']): record for record in layout['routes']}
    primitives = {rid: [dict(primitive) for primitive in record['primitives']]
                  for rid, record in records.items()
                  if record.get('status') == 'routed'
                  and record.get('primitives')}
    return records, primitives


def manual_only_world(lifter, manual_routes):
    world = World(lifter.stack)
    for rid, route in manual_routes.items():
        world.add_route(route)
    return world


def find_conflicts(lifter, records, frozen, manual_routes):
    """Frozen routes that physically conflict with the fixed manual U's."""
    world = manual_only_world(lifter, manual_routes)
    conflicts = {'z1': [], 'z2': []}
    for rid in sorted(frozen):
        if rid in manual_routes:
            continue
        record = records[rid]
        base = LIFT.flat_route(rid, record['plane'], frozen[rid],
                               row=lifter.row.get(rid, 1))
        violations = world.check_route(base, check_self=False)
        if violations:
            conflicts[record['plane']].append(dict(
                route_id=rid, kind=violations[0].get('kind'),
                other_route=violations[0].get('other_route')))
    return conflicts


# ---------------------------------------------------------------------------
# 2. re-route the conflicting frozen routes with everything else fixed
# ---------------------------------------------------------------------------
def sample_prepared(prepared, step_mm=0.5):
    points = []
    for prim in prepared.prims:
        if prim.kind == 'line':
            p0 = np.asarray(prim.p0, dtype=float)
            p1 = np.asarray(prim.p1, dtype=float)
            length = float(np.linalg.norm(p1 - p0))
            count = max(2, int(length / step_mm) + 1)
            for index in range(count):
                points.append(p0 + (p1 - p0) * (index / (count - 1)))
        else:
            center = np.asarray(prim.center, dtype=float)
            radius = float(prim.radius)
            sweep = float(prim.sweep)
            p0 = np.asarray(prim.p0, dtype=float)
            start = math.atan2(p0[1] - center[1], p0[0] - center[0])
            count = max(2, int(abs(sweep) * radius / step_mm) + 1)
            for index in range(count):
                angle = start + sweep * index / (count - 1)
                points.append(center + radius * np.asarray([math.cos(angle),
                                                            math.sin(angle)]))
    return np.asarray(points, dtype=float)


def make_guard(original_evaluate, guard_points, clearance=0.08):
    tree = cKDTree(guard_points[:, :2]) if len(guard_points) else None

    def guarded(prepared, exclude=(), stop_on_invalid=True):
        result = original_evaluate(prepared, exclude=exclude,
                                   stop_on_invalid=stop_on_invalid)
        if not result.valid:
            return result
        if tree is not None:
            points = sample_prepared(prepared)
            if len(points) and float(tree.query(points)[0].min()) < clearance:
                result.valid = False
                result.reason = 'manual_transition_keepout'
                return result
        return result

    return guarded


def conn_to_campaign_map(state, plane, records):
    """CONN route id -> campaign layout route id (same endpoint pair, same plane)."""
    campaign_by_key = {}
    for rid, record in records.items():
        if record.get('plane') != plane:
            continue
        key = frozenset((record.get('source_endpoint'),
                         record.get('target_endpoint')))
        campaign_by_key[key] = int(rid)
    mapping = {}
    for rid, record in state.route_by_id.items():
        key = frozenset((record.get('source_endpoint'),
                         record.get('target_endpoint')))
        campaign_id = campaign_by_key.get(key)
        if campaign_id is not None:
            mapping[int(rid)] = campaign_id
    return mapping


def manual_z0_obstacles(manual_routes):
    """Manual U geometry that physically sits on the z1 interface plane."""
    obstacles = {}
    for rid, route in manual_routes.items():
        for index, part in enumerate(route['parts']):
            if part['kind'] != 'flat' or abs(float(part['z_mm'])) > 1e-9:
                continue
            obstacle_id = rid if index == 0 else rid * 1000 + index
            obstacles[obstacle_id] = [dict(primitive)
                                      for primitive in part['primitives']]
    return obstacles


def route_z1_fresh(records, frozen, manual_routes, manual_ids, guard_points,
                   budget=BUDGET):
    """Rebuild all 256 non-manual z1 (opposite) connections with manual fixed."""
    state = STATE.state_for('z1', log=log)
    obstacles = manual_z0_obstacles(manual_routes)
    for obstacle_id, prims in obstacles.items():
        try:
            state.index.add(int(obstacle_id), prepare(prims))
        except Exception:  # noqa: BLE001
            continue
    log(f'[z1] manual z=0 obstacle parts: {len(obstacles)}')
    if len(guard_points):
        state.index.evaluate = make_guard(state.index.evaluate, guard_points)
        log(f'[z1] transition keep-out guard: {len(guard_points)} points')
    id_map = conn_to_campaign_map(state, 'z1', records)
    ids = [rid for rid, record in sorted(state.route_by_id.items())
           if record.get('relation') != 'same' and rid in id_map]
    log(f'[z1] routing {len(ids)} non-manual connections from scratch')
    routed = {}
    failures = []
    started = time.perf_counter()
    for index, rid in enumerate(ids, 1):
        result, failure, stats = SEARCH.attempt_route(state, rid,
                                                      budget=budget)
        if result is None:
            failures.append(dict(route_id=id_map.get(int(rid), int(rid)),
                                 plane='z1',
                                 relation=state.route_by_id[rid].get('relation'),
                                 evaluator=(failure or {}).get('reason'),
                                 evaluated=stats.get('evaluated')))
            log(f'[z1] route {rid} FAILED after {stats.get("evaluated")} '
                f'candidates ({failure.get("reason") if failure else ""})')
        else:
            state.add(result)
            routed[id_map[int(rid)]] = [dict(primitive)
                                        for primitive in result.primitives]
        if index % 32 == 0:
            log(f'[z1] progress {index}/{len(ids)} ok={len(routed)} '
                f'fail={len(failures)} ({time.perf_counter() - started:.1f}s)')
    log(f'[z1] routed {len(routed)}/{len(ids)} '
        f'({time.perf_counter() - started:.1f}s, {len(failures)} failed)')
    return dict(routed=routed, failures=failures, plane='z1')


def route_z2_fresh(guard_points, budget=1600, retry_passes=3, rr_rounds=2):
    """Rebuild all 512 z2 connections with the unchanged strict-C4 engine."""
    state = STATE.state_for('z2', log=log)
    if len(guard_points):
        state.index.evaluate = make_guard(state.index.evaluate, guard_points)
        log(f'[z2] transition keep-out guard: {len(guard_points)} points')
    groups = CONN.groups_for_plane('z2')
    router = ManualGroupRouter(state, groups, log=log)
    cache = router.prime_same_candidates()
    order = ORDER_GROUPS(groups, router, mode='easy')
    started = time.perf_counter()
    details, summary = router.route_all(order, budget,
                                        same_candidates_cache=cache)
    router.reconcile()
    log(f'[z2] first pass: routed_routes={len(state.accepted)} '
        f'failed_groups={len(router.failed_groups)} '
        f'({time.perf_counter() - started:.1f}s)')
    retry_history = []
    for pass_index in range(1, int(retry_passes) + 1):
        router.reconcile()
        pending = [g for g in groups
                   if g['group_id'] in router.failed_groups]
        if not pending:
            break
        pending_order = ORDER_GROUPS(pending, router, mode='easy')
        router.route_all(pending_order, budget,
                         same_candidates_cache=cache)
        router.reconcile()
        retry_history.append(dict(pass_index=pass_index,
                                  attempted=len(pending_order),
                                  routed_routes=len(state.accepted),
                                  failed_groups=len(router.failed_groups),
                                  seconds=round(time.perf_counter() - started,
                                                1)))
        log(f'[z2] retry pass {pass_index}: routed_routes={len(state.accepted)} '
            f'failed_groups={len(router.failed_groups)} '
            f'({time.perf_counter() - started:.1f}s)')
        if rr_rounds > 0 and router.failed_groups:
            router.rr_groups(budget=budget, max_rounds=rr_rounds)
            router.reconcile()
            log(f'[z2] rr after pass {pass_index}: '
                f'routed_routes={len(state.accepted)} '
                f'failed_groups={len(router.failed_groups)}')
    id_map = conn_to_campaign_map(state, 'z2', records)
    routed = {id_map.get(int(rid), int(rid)):
              [dict(primitive) for primitive in result.primitives]
              for rid, result in state.accepted.items()}
    failed_conn_ids = set()
    for group in groups:
        if group['group_id'] in router.failed_groups:
            failed_conn_ids.update(int(rid) for rid in group['route_ids'])
    failures = [dict(route_id=id_map.get(rid, rid), plane='z2',
                     reason='group_failed')
                for rid in sorted(failed_conn_ids)]
    log(f'[z2] routed {len(routed)} routes, failed routes={len(failed_ids)} '
        f'({time.perf_counter() - started:.1f}s)')
    return dict(routed=routed, failures=failures, plane='z2',
                retry_history=retry_history,
                failed_groups=len(router.failed_groups))


def build_3d_layout(lifter, manual_routes, manual_prims, records, final_2d,
                    manual_ids):
    missing = [rid for rid in list(lifter.routed)
               if rid not in manual_ids and rid not in final_2d]
    for rid in missing:
        lifter.routed.pop(int(rid), None)
    if missing:
        log(f'[full] {len(missing)} auto routes not routed -> marked failed')
    groups = []
    for group in lifter.groups:
        ids = [int(rid) for rid in group['route_ids']]
        if any(rid not in lifter.routed for rid in ids):
            continue
        groups.append(group)
    lifter.groups = groups
    lifter.group_by_id = {int(g['group_id']): g for g in groups}
    lifter.route_group = {}
    for group in groups:
        for phase, rid in enumerate(group['route_ids']):
            lifter.route_group[int(rid)] = (int(group['group_id']), phase)
    lifter.world.rebuild({})
    lifter.lifted = {}
    lifter.primitives = {}
    lifter.base_routes = {}
    for rid, route in manual_routes.items():
        lifter.world.add_route(route)
        lifter.lifted[rid] = route
        lifter.primitives[rid] = [dict(primitive)
                                  for primitive in manual_prims[rid]]
        lifter.base_routes[rid] = LIFT.flat_route(rid, 'z1',
                                                  lifter.primitives[rid], row=1)
    plane_of = {}
    for rid, prims in final_2d.items():
        if rid in manual_routes:
            continue
        record = records[rid]
        plane = record['plane']
        row = 1 if plane == 'z1' else 2
        flat = LIFT.flat_route(rid, plane, prims, row=row)
        lifter.world.add_route(flat)
        lifter.primitives[rid] = [dict(primitive) for primitive in prims]
        lifter.base_routes[rid] = flat
        plane_of[rid] = plane
    log(f'[full] world rebuilt: manual={len(manual_routes)}, auto={len(plane_of)}, '
        f'total={len(lifter.world.plan)}')
    return plane_of


def manual_first_full():
    started = time.perf_counter()
    NEW_DIR.mkdir(parents=True, exist_ok=True)
    M.install_extended_stack_builder()
    LIFT.LAYER_IDS = tuple(range(2, 16))

    manual_routes, manual_prims, manual_plans, connections = load_manual_routes()
    manual_ids = set(manual_routes)
    log(f'[full] fixed manual routes: {len(manual_routes)}')
    records, frozen = load_frozen_layout()
    log(f'[full] frozen layout routed records: {len(frozen)}')

    lifter = LIFT.CrossingLifter(v4_root=M.V4_ROOT, out_dir=NEW_DIR,
                                 heights=M.HEIGHTS, log=log)
    # transition guard points for each plane
    transition_points = []
    for rid, route in manual_routes.items():
        for part in route['parts']:
            if part['kind'] != 'transition':
                continue
            samples = LIFT_RUN._part_samples(part)
            if samples is not None and len(samples):
                transition_points.append(np.asarray(samples, dtype=float))
    transition_points = (np.vstack(transition_points) if transition_points
                         else np.zeros((0, 3)))
    z1_guard = transition_points[transition_points[:, 2] < 0.09]
    z2_guard = transition_points[np.abs(transition_points[:, 2] - 0.5) < 0.09]
    log(f'[full] transition keep-out points: z1={len(z1_guard)}, '
        f'z2={len(z2_guard)}')

    reroute = {
        'z1': route_z1_fresh(records, frozen, manual_routes, manual_ids,
                             z1_guard),
        'z2': route_z2_fresh(z2_guard),
    }
    write_json(NEW_DIR / 'reroute_2d.json', reroute, indent=1)

    # merge final 2D primitives: manual + re-routed + unchanged frozen
    final_2d = {}
    failures_2d = []
    for plane in ('z1', 'z2'):
        final_2d.update(reroute[plane]['routed'])
        failures_2d.extend(reroute[plane]['failures'])
    for rid in manual_ids:
        final_2d.pop(rid, None)
    log(f'[full] 2D layout: {len(final_2d)} auto routes + {len(manual_ids)} manual '
        f'= {len(final_2d) + len(manual_ids)}')

    plane_of = build_3d_layout(lifter, manual_routes, manual_prims, records,
                               final_2d, manual_ids)
    manual_groups = set()
    for rid in manual_ids:
        entry = lifter.route_group.get(int(rid))
        if entry is not None:
            manual_groups.add(int(entry[0]))
    for gid in manual_groups:
        lifter.group_plans[gid] = dict(group_id=int(gid),
                                       status='manual_fixed_group',
                                       note='manual U L1-L4 fixed')
    log(f'[full] frozen manual C4 groups: {len(manual_groups)}')

    entries = lifter.final_flat_entries()
    crossings, reports, pairs = LIFT.analyze_planes(
        entries, log=log, compute_positions=True,
        primitives_by_id=lifter.primitives)
    lifter.crossings = crossings
    lifter.pair_set = set()
    for plane_pairs in pairs.values():
        lifter.pair_set |= plane_pairs
    lifter.high_pairs = lifter._added_pairs({})
    lifter._finalize_analysis()
    log(f'[full] after manual-first 2D: pairs={len(lifter.pair_set)} '
        f'points={len(lifter.crossings)} ({time.perf_counter() - started:.1f}s)')

    LIFT.LAYER_IDS = tuple(range(5, 16))
    log(f'[full] crossing-lift L5-L15 (budget {CROSSING_LIFT_BUDGET_S:.0f}s, '
        f'max {MAX_GROUPS} groups)')
    history = lifter.optimize(max_groups=MAX_GROUPS,
                              time_limit=CROSSING_LIFT_BUDGET_S, log=log)
    log(f'[full] optimizer lifted {len(history)} groups '
        f'({time.perf_counter() - started:.1f}s)')

    payload = lifter.build_payload()
    LIFT._write_json(NEW_DIR / 'routes_l3d.json', payload)
    LIFT._write_json(NEW_DIR / 'layer_stack.json', lifter.stack.to_dict())
    validation = LIFT.validate_payload_v4(payload, lifter.v4_root, log=log)
    repair_rounds = 0
    while not validation.get('exploratory_pass') and repair_rounds < 40:
        violations = validation.get('violations') or []
        offending = set()
        for item in violations:
            if item.get('category') != 'clearance_violations':
                continue
            for key in ('route_id', 'other_route'):
                value = item.get(key)
                if value is None:
                    continue
                entry = lifter.route_group.get(int(value))
                if entry is None:
                    continue
                gid = int(entry[0])
                if gid not in manual_groups:
                    offending.add(gid)
        if not offending:
            break
        lifter.revert_groups(offending, log=log)
        repair_rounds += 1
        payload = lifter.build_payload()
        LIFT._write_json(NEW_DIR / 'routes_l3d.json', payload)
        validation = LIFT.validate_payload_v4(payload, lifter.v4_root, log=log)
    log(f'[full] validation status={validation.get("status")} '
        f'repair_rounds={repair_rounds}')

    entries = lifter.final_flat_entries()
    after_crossings, after_reports, after_pairs = LIFT.analyze_planes(
        entries, log=log, compute_positions=False)
    unique_pairs = set()
    for plane_pairs in after_pairs.values():
        unique_pairs |= plane_pairs
    after_records = [dict(z=float(value[0]), route_a=int(value[1]),
                          route_b=int(value[2]), x=float(value[3]),
                          y=float(value[4]), angle_deg=float(value[7]))
                     for value in after_crossings]
    LIFT._write_json(NEW_DIR / 'crossings_after.json', dict(
        count=len(after_records), unique_pair_count=len(unique_pairs),
        pair_count_by_height={str(key): value['crossing_pair_count']
                              for key, value in after_reports.items()},
        point_count_by_height={str(key): value['crossing_count']
                               for key, value in after_reports.items()},
        remaining_pairs=sorted(unique_pairs), crossings=after_records),
        indent=None)

    summary = lifter.summary(validation=validation,
                             after_reports=after_reports,
                             after_pairs_by_plane=after_pairs)
    routed_by_plane = Counter()
    for rid in lifter.routed:
        routed_by_plane[lifter.routed[rid]['plane']] += 1
    summary.update(
        schema='manual_first_full_1024_v1',
        layer_heights_mm={str(int(layer.layer_id)):
                          float(layer.physical_z_mm)
                          for layer in lifter.stack.routing_layers},
        remaining_unique_crossing_pairs=len(unique_pairs),
        crossing_pairs_after_by_plane={
            str(key): value['crossing_pair_count']
            for key, value in after_reports.items()},
        crossing_points_after_by_plane={
            str(key): value['crossing_count']
            for key, value in after_reports.items()},
        manual_fixed=dict(routes=len(manual_routes),
                          groups=len(manual_groups),
                          all_kept=True),
        reroute=dict(z1_routed=len(reroute['z1']['routed']),
                     z1_failed=len(reroute['z1']['failures']),
                     z2_routed=len(reroute['z2']['routed']),
                     z2_failed=len(reroute['z2']['failures']),
                     failures=failures_2d),
        routed_by_plane=dict(routed_by_plane),
        repair_rounds=repair_rounds,
        elapsed_seconds=round(time.perf_counter() - started, 1))
    LIFT._write_json(NEW_DIR / 'summary.json', summary, indent=1)
    LIFT._write_json(NEW_DIR / 'validation.json', validation, indent=1)
    LIFT._write_json(NEW_DIR / 'lift_plans.json', dict(
        lifted=[plan for plan in lifter.group_plans.values()
                if plan.get('status') == 'lifted'],
        rejected=[plan for plan in lifter.group_plans.values()
                  if plan.get('status') == 'rejected'],
        reverted=[plan for plan in lifter.group_plans.values()
                  if plan.get('status') == 'reverted'],
        manual=[plan for plan in lifter.group_plans.values()
                if plan.get('status') == 'manual_fixed_group'],
        history=history), indent=1)
    try:
        figures = LIFT_RUN.plot_all(lifter, payload, summary,
                                    NEW_DIR / 'plots', log=log)
    except Exception as error:  # noqa: BLE001
        log(f'[full] plot_all skipped: {error}')
    return dict(lifter=lifter, unique_pairs=unique_pairs,
                after_records=after_records, history=history,
                summary=summary, validation=validation,
                reroute=reroute, failures_2d=failures_2d,
                manual_routes=manual_routes,
                total_routes=len(lifter.world.plan))


def main():
    result = manual_first_full()
    # comparison with the old baseline (992/1024, 75,794, 0 violations)
    baseline = M.baseline_metrics()
    comparison, md = M.compare(baseline, result)
    log('')
    log(md)
    log(f'[full] artifacts: {NEW_DIR}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
