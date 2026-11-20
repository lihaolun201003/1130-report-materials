# -*- coding: utf-8 -*-
"""Minimal validation of the corrected-input adapter (no full search, no experiment).

This script does exactly two things, as requested for this round:

1. **Static check** that the two manual files are read correctly: record counts,
   unique ids, relation counts, endpoint coordinates against the project's real
   port model, per-plane port occupancy, and the "layer column says z1 for both
   files" quirk.
2. **One minimal adaptation run**: a handful of records (2 per relation per plane)
   are pushed through the *existing* project code paths to prove the adapter feeds
   them correctly:
   * ``same`` relation   -> existing R=15 U-turn geometry + canonical validator;
   * ``opposite`` / ``adjacent`` -> existing sequential 2D router + elevation lift
     (``l3d.paths.build_route_l3d``) + existing true-3D world check.

It deliberately routes only a few records and never starts a full search.
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter, OrderedDict
from pathlib import Path

from .imports import (C, FSLW_GEOM, L3D_LAYERS, L3D_PATHS, L3D_WORLD,
                      ROUTER_FRAMES, ROUTER_SEARCH, U_GEOMETRY, D56_INDEX)
from .inputs import load_manual_c4_inputs


def _log(message):
    print(message, flush=True)


# ---------------------------------------------------------------------------
# 1. static check
# ---------------------------------------------------------------------------
def static_check(log=_log):
    inputs = load_manual_c4_inputs()
    validation = inputs.validation
    log('[static] files:')
    for plane, info in validation['files'].items():
        log(f'  {plane}: {info["records"]} records  sha256={info["sha256"][:16]}...'
            f'  {Path(info["path"]).name}')
    log(f'[static] relation counts: {validation["relation_counts"]}')
    log(f'[static] plane rules: {validation["plane_rules"]}')
    passed = sum(1 for item in inputs.checks.values() if item['passed'])
    log(f'[static] checks: {passed}/{len(inputs.checks)} passed')
    for name, item in inputs.checks.items():
        if not item['passed']:
            log(f'  FAILED {name}: {item["detail"]}')
    log(f'[static] manual grouping metadata available: '
        f'{validation["manual_group_metadata_available"]}')
    return inputs


# ---------------------------------------------------------------------------
# 2. minimal adaptation run (a few records only)
# ---------------------------------------------------------------------------
def _route_subset_2d(plane, records, log=_log):
    """Run the existing sequential 2D router on a handful of records."""
    routes = [dict(route_id=int(record['internal_id']),
                   uid=record['uid'],
                   source_endpoint=record['source_endpoint_id'],
                   target_endpoint=record['target_endpoint_id'],
                   relation=record['relation'],
                   pair=f"{record['source_side']}{record['target_side']}")
              for record in records]
    endpoints = {}
    for record in records:
        for which in ('source', 'target'):
            endpoints[record[f'{which}_endpoint_id']] = dict(
                side=record[f'{which}_endpoint']['side'],
                routing_xy=list(record[f'{which}_endpoint']['routing_xy']),
                inward=list(record[f'{which}_endpoint']['inward']))
    frames = ROUTER_FRAMES.build_frames(routes, endpoints)
    cfg = dict(ROUTER_SEARCH.DEFAULT_CFG)
    cfg.update(width=C.WIDTH_MM, gap=C.EDGE_GAP_MM, sagitta=C.SAGITTA_MM,
               min_radius_mm=C.RADIUS_MM,
               min_cross_angle_deg=C.MIN_CROSS_ANGLE_DEG,
               crossing_policy='strict')
    router = ROUTER_SEARCH.Router(frames, routes, cfg=cfg, log=lambda *a: None)
    order = sorted(frames, key=lambda rid: -frames[rid].p[0])
    for rid in order:
        router._try_place(rid)
    accepted = {}
    for rid, result in router.accepted.items():
        accepted[int(rid)] = dict(primitives=list(result.primitives),
                                  family=result.family)
    failed = {int(rid): failure.get('reason')
              for rid, failure in router.failed.items()}
    log(f'[minimal] 2D {plane}: {len(accepted)}/{len(routes)} accepted '
        f'(existing engine; evals={router.index.evaluations})')
    if failed:
        log(f'[minimal] 2D {plane} failed: {failed}')
    return accepted, failed


def _lift_and_check(record, primitives, layer, stack, world, log=_log):
    """Lift one 2D chain to ``layer`` with the existing l3d builder and check it."""
    z0 = float(record['source_z_mm'])
    z1 = (z0 if int(layer) == C.INTERFACE_LAYER_ID
          else float(stack.z_for_layer(layer)))
    port_meta = dict(
        source_port=dict(xy=list(record['source_xy']), z_mm=z0, layer_id=1),
        target_port=dict(xy=list(record['target_xy']), z_mm=z0, layer_id=1),
        source_row=int(record['source_row']),
        target_row=int(record['target_row']),
        start_dir=list(record['source_endpoint']['inward']),
        end_dir=[-float(v) for v in record['target_endpoint']['inward']])
    sequence = ([C.INTERFACE_LAYER_ID, int(layer), C.INTERFACE_LAYER_ID]
                if int(layer) != C.INTERFACE_LAYER_ID else [C.INTERFACE_LAYER_ID])
    heights = [z0, z1, z0] if len(sequence) == 3 else [z0]
    route = L3D_PATHS.build_route_l3d(int(record['internal_id']),
                                      record['dataset'], primitives,
                                      sequence, heights, port_meta,
                                      radius=C.RADIUS_MM)
    if route is None:
        return None, 'lift_infeasible'
    violations = world.check_route(route)
    if violations:
        return None, f'world_violation:{violations[0]["kind"]}'
    world.add_route(route)
    summary = dict(uid=record['uid'], layer=int(layer),
                   n_transitions=int(route['n_transitions']),
                   length_mm=round(float(route['length_mm']), 3),
                   flat_parts=sum(1 for part in route['parts']
                                  if part['kind'] == 'flat'))
    return summary, None


def minimal_run(inputs, log=_log):
    """Route a handful of records through the existing code paths."""
    stack = L3D_LAYERS.build_stack('medium_050')
    results = OrderedDict()
    started = time.perf_counter()

    # ---- (a) manual-style same-side U-turns: existing U geometry, L1..L4
    # one sampled U per layer (a distinct layer per sample, because the depth
    # ladder that separates nested U-turns on one plane belongs to the production
    # manual-U path, not to this adapter check)
    z1_same = inputs.records_of_relation('z1', 'same')
    z2_same = inputs.records_of_relation('z2', 'same')
    manual = OrderedDict()
    manual[z1_same[0]['uid']] = (z1_same[0], 2)
    if len(z1_same) > 1:
        manual[z1_same[1]['uid']] = (z1_same[1], 3)
    if z2_same:
        manual[z2_same[0]['uid']] = (z2_same[0], 5)
    log('[minimal] (a) manual same-side U-turns through existing R=15 U geometry')
    for uid, (record, layer) in manual.items():
        start = record['source_endpoint']['inward']
        end = [-float(start[0]), -float(start[1])]
        candidates = U_GEOMETRY.u_candidates(record['source_xy'],
                                             record['target_xy'], start, end,
                                             radius=C.RADIUS_MM)
        if not candidates:
            results[uid] = dict(status='failed',
                                reason='no_legal_u_turn_candidate')
            log(f'  {uid}: NO U-turn candidate')
            continue
        chosen = candidates[0]
        ok, errors = FSLW_GEOM.canonical_validate(
            chosen['primitives'], record['source_xy'], record['target_xy'],
            start, end, radius=C.RADIUS_MM, width=C.WIDTH_MM)
        # each sampled U is checked in its own world: assigning several nested
        # U-turns to one plane is the job of the existing manual-U depth ladder,
        # not of this input adapter
        world = L3D_WORLD.World(stack, clearance=C.CLEARANCE_MM)
        summary, error = _lift_and_check(record, chosen['primitives'], layer,
                                         stack, world)
        plane = record['dataset']
        if error:
            results[uid] = dict(status='failed', reason=error,
                                family=chosen['family'])
            log(f'  {uid} {plane} L{layer}: {error}')
        else:
            summary.update(family=chosen['family'], canonical_valid=bool(ok),
                           canonical_errors=errors[:2])
            results[uid] = dict(status='routed', **summary)
            log(f'  {uid} {plane} L{layer}: family={chosen["family"]} '
                f'len={summary["length_mm"]}mm canonical={ok}')

    # ---- (b) remaining records: existing 2D engine, then existing lift to L5
    world = L3D_WORLD.World(stack, clearance=C.CLEARANCE_MM)
    log('[minimal] (b) opposite/adjacent records through the existing 2D engine '
        'and elevation lift to L5')
    for plane, relation in (('z1', 'opposite'), ('z2', 'adjacent')):
        subset = inputs.records_of_relation(plane, relation)[:2]
        if not subset:
            continue
        accepted, failed = _route_subset_2d(plane, subset, log=log)
        by_internal = {int(record['internal_id']): record for record in subset}
        for rid, record in by_internal.items():
            if rid not in accepted:
                results[record['uid']] = dict(
                    status='failed',
                    reason=f'2d_routing_failed:{failed.get(rid)}')
                continue
            primitives = accepted[rid]['primitives']
            start = record['source_endpoint']['inward']
            end = [-float(v) for v in record['target_endpoint']['inward']]
            canonical_ok, canonical_errors = FSLW_GEOM.canonical_validate(
                primitives, record['source_xy'], record['target_xy'],
                start, end, radius=C.RADIUS_MM, width=C.WIDTH_MM)
            summary, error = _lift_and_check(record, primitives, 5,
                                             stack, world)
            if error:
                results[record['uid']] = dict(
                    status='failed', reason=error,
                    family=accepted[rid]['family'])
                log(f'  {record["uid"]} {plane} L5: {error}')
            else:
                summary.update(family=accepted[rid]['family'],
                               canonical_valid=bool(canonical_ok),
                               canonical_errors=canonical_errors[:2])
                results[record['uid']] = dict(status='routed', **summary)
                log(f'  {record["uid"]} {plane} L5: family={summary["family"]} '
                    f'len={summary["length_mm"]}mm transitions='
                    f'{summary["n_transitions"]}')

    elapsed = round(time.perf_counter() - started, 2)
    routed = sum(1 for item in results.values()
                 if item.get('status') == 'routed')
    log(f'[minimal] done: {routed}/{len(results)} sampled records routed, '
        f'{elapsed}s')
    return dict(schema='four_side_1024_manual_c4_adapt_minimal_run_v1',
                sampled=len(results), routed=routed, elapsed_s=elapsed,
                results=results,
                stack=dict(preset='medium_050',
                           heights={layer: stack.z_for_layer(layer)
                                    for layer in (2, 3, 4, 5)},
                           note='existing four_side_1024.l3d layer stack'),
                note=('deliberately small: 2 same-side records per plane through '
                      'the manual U path and 2 records per relation plane through '
                      'the original 2D engine + lift; no full search was run'))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(
        description='corrected-input adapter: static check + minimal adaptation run')
    parser.add_argument('--json', default=None, help='write the result JSON here')
    parser.add_argument('--static-only', action='store_true')
    args = parser.parse_args(argv)
    inputs = static_check()
    output = dict(validation=inputs.validation)
    if not args.static_only:
        output['minimal_run'] = minimal_run(inputs)
    if args.json:
        path = Path(args.json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(output, ensure_ascii=False, indent=1,
                                   default=str), encoding='utf-8')
        _log(f'written {path}')
    return 0 if output['validation']['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
