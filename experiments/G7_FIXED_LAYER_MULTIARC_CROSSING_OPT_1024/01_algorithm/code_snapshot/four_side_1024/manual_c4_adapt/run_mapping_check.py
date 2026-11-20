# -*- coding: utf-8 -*-
"""Static mapping check + one small-sample execution check (no full search).

What this script proves, and nothing more
-----------------------------------------
* static : the manual grouping metadata is mapped onto the *authoritative*
  topology exactly (z1 direct 1:1, z2 128 base connections via C4 four-fold
  expansion -> the authoritative 512), and the manual / old-algorithm partition
  follows the round rules (L1-L4 manual, L5+ old algorithm, explicit marks only);
* sample : 5 records are executed through the **existing** project code to show the
  manual grouping really changes the *layer assignment and the physical path*,
  not just the routing order:
    - 2 explicitly marked L1-L4 records  -> executed as manual on L1 / L3;
    - 1 control: the same L1 record under the old-algorithm layer policy (L5);
    - 1 explicitly marked L5+ record     -> old algorithm (its CSV layer L6 is
      deliberately **not** executed, proving the L5+ rule overrides the mark);
    - 1 unmarked record                  -> old algorithm, layer L5.
"""
from __future__ import annotations

import json
import sys
import time
from collections import OrderedDict
from pathlib import Path

from .imports import (C, FSLW_GEOM, L3D_LAYERS, L3D_PATHS, L3D_WORLD,
                      ROUTER_FRAMES, ROUTER_SEARCH, U_GEOMETRY)
from .inputs import load_manual_c4_inputs
from .mapping import (MANUAL_LAYER_RANGE, OLD_ALGORITHM_START_LAYER,
                      build_mapping, load_metadata, load_topology)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_JSON = PROJECT_ROOT / 'outputs' / 'manual_c4_adapt' / 'mapping_check.json'


def _log(message):
    print(message, flush=True)


# ---------------------------------------------------------------------------
# small helpers around the existing code
# ---------------------------------------------------------------------------
def _port_meta(record):
    from .imports import C  # local import keeps the module import order explicit
    z0 = float(record['source_z_mm'])
    return dict(
        source_port=dict(xy=list(record['source_xy']), z_mm=z0,
                         layer_id=C.INTERFACE_LAYER_ID),
        target_port=dict(xy=list(record['target_xy']), z_mm=z0,
                         layer_id=C.INTERFACE_LAYER_ID),
        source_row=int(record['source_row']),
        target_row=int(record['target_row']),
        start_dir=list(record['source_endpoint']['inward']),
        end_dir=[-float(v) for v in record['target_endpoint']['inward']])


def _lift(record, primitives, layer, stack, log=_log):
    """Lift one 2D chain to ``layer`` with the existing l3d builder + 3D check."""
    z0 = float(record['source_z_mm'])
    z1 = (z0 if int(layer) == C.INTERFACE_LAYER_ID
          else float(stack.z_for_layer(layer)))
    sequence = ([C.INTERFACE_LAYER_ID] if int(layer) == C.INTERFACE_LAYER_ID
                else [C.INTERFACE_LAYER_ID, int(layer), C.INTERFACE_LAYER_ID])
    heights = [z0] if len(sequence) == 1 else [z0, z1, z0]
    route = L3D_PATHS.build_route_l3d(int(record['internal_id']),
                                      record['dataset'], primitives, sequence,
                                      heights, _port_meta(record),
                                      radius=C.RADIUS_MM)
    if route is None:
        return None, 'lift_infeasible', None
    world = L3D_WORLD.World(stack, clearance=C.CLEARANCE_MM)
    violations = world.check_route(route)
    if violations:
        return None, f'world_violation:{violations[0]["kind"]}', route
    flat_heights = [round(float(part['z_mm']), 6) for part in route['parts']
                    if part['kind'] == 'flat']
    flat_layers = [int(part['layer_id']) for part in route['parts']
                   if part['kind'] == 'flat']
    summary = dict(
        target_layer=int(layer),
        layer_z_mm=round(z1, 6),
        flat_heights_mm=flat_heights,
        flat_layers=flat_layers,
        n_transitions=int(route['n_transitions']),
        length_mm=round(float(route['length_mm']), 3),
    )
    return summary, None, route


def _u_path(record, log=_log):
    """Existing R=15 same-side U-turn geometry + frozen canonical validation."""
    start = record['source_endpoint']['inward']
    end = [-float(v) for v in record['target_endpoint']['inward']]
    candidates = U_GEOMETRY.u_candidates(record['source_xy'],
                                         record['target_xy'], start, end,
                                         radius=C.RADIUS_MM)
    if not candidates:
        return None, 'no_u_turn_candidate', None
    chosen = candidates[0]
    ok, errors = FSLW_GEOM.canonical_validate(
        chosen['primitives'], record['source_xy'], record['target_xy'],
        start, end, radius=C.RADIUS_MM, width=C.WIDTH_MM)
    if not ok:
        return None, f'canonical_invalid:{errors[:2]}', None
    return chosen, None, dict(family=chosen['family'],
                              length_mm=round(float(chosen['length_mm']), 3),
                              bulge_mm=chosen['params']['bulge_mm'],
                              canonical_valid=True)


def _engine_path(record, log=_log):
    """Existing sequential 2D engine (for a non-manual opposite/adjacent record)."""
    routes = [dict(route_id=int(record['internal_id']), uid=record['uid'],
                   source_endpoint=record['source_endpoint_id'],
                   target_endpoint=record['target_endpoint_id'],
                   relation=record['relation'],
                   pair=f"{record['source_side']}{record['target_side']}")]
    endpoints = {}
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
    rid = int(record['internal_id'])
    router._try_place(rid)
    if rid not in router.accepted:
        return None, f'2d_failed:{router.failed.get(rid, {}).get("reason")}', None
    result = router.accepted[rid]
    start = record['source_endpoint']['inward']
    end = [-float(v) for v in record['target_endpoint']['inward']]
    ok, errors = FSLW_GEOM.canonical_validate(
        result.primitives, record['source_xy'], record['target_xy'],
        start, end, radius=C.RADIUS_MM, width=C.WIDTH_MM)
    if not ok:
        return None, f'canonical_invalid:{errors[:2]}', None
    return list(result.primitives), None, dict(family=result.family,
                                               length_mm=round(float(result.length_mm), 3),
                                               canonical_valid=True)


# ---------------------------------------------------------------------------
# static check
# ---------------------------------------------------------------------------
def static_check(log=_log):
    payload = build_mapping()
    coverage = payload['coverage']
    log('[static] manual grouping metadata <-> authoritative topology')
    log(f'  authoritative topology : {coverage["authoritative_topology"]}')
    log(f'  metadata file          : {coverage["metadata_file"]}')
    log(f'  metadata vs topology   : {coverage["metadata_vs_topology"]}')
    log(f'  manual marks (metadata): {coverage["manual_metadata_marks"]}')
    log(f'  manual executed L1-L4  : {coverage["manual_execute_L1_L4"]}')
    log(f'  old algorithm          : {coverage["old_algorithm"]}')
    hard = [name for name, item in payload['checks'].items()
            if not item['passed']]
    log(f'[static] checks: {len(payload["checks"]) - len(hard)}/'
        f'{len(payload["checks"])} passed; failed={hard}')
    return payload


# ---------------------------------------------------------------------------
# small-sample execution
# ---------------------------------------------------------------------------
def _metadata_records():
    metadata, _sha = load_metadata()
    by_layer = OrderedDict()
    for record in metadata:
        by_layer.setdefault((record['dataset'], record['assigned_layer'],
                             record['routing_method']), []).append(record)
    return metadata, by_layer


def _authoritative_record(record, topology):
    """Authoritative topology entry + route_id for one metadata pair."""
    for entry in topology[record['dataset']]:
        if entry['pair'] == record['pair']:
            return entry
    return None


def sample_execution(adapter_inputs, log=_log):
    from .mapping import load_topology, pair_key  # local import (small scope)
    stack = L3D_LAYERS.build_stack('medium_050')
    metadata, by_layer = _metadata_records()
    topology, _sha = load_topology()
    records = adapter_inputs.records_by_plane
    by_pair = {(plane, pair_key(record['source_port_id'],
                                record['target_port_id'])): record
               for plane, plane_records in records.items()
               for record in plane_records}

    samples = OrderedDict()

    def add(key, record, policy, layer, path_kind, extra=None):
        item = dict(uid=record['uid'], dataset=record['dataset'],
                    relation=record['relation'],
                    metadata_marks=dict(routing_method=record['routing_method'],
                                        manual_group=record['manual_group'],
                                        assigned_layer_csv=record['assigned_layer_csv']),
                    policy=policy, policy_layer=int(layer),
                    path_kind=path_kind)
        if extra:
            item.update(extra)
        samples[key] = item

    # ---- 1/2: explicitly marked L1-L4 records -> manual execution
    for assigned_layer, tag in ((1, 'manual_L1'), (3, 'manual_L3')):
        record_meta = next(record for record in metadata
                           if record['routing_method'] == 'manual_fixed_u'
                           and record['assigned_layer'] == assigned_layer
                           and record['dataset'] == 'z1')
        adapter = by_pair[('z1', record_meta['pair'])]
        authoritative = _authoritative_record(record_meta, topology)
        chosen, error, path_info = _u_path(adapter)
        if error:
            add(tag, record_meta, 'manual', assigned_layer, 'u_geometry',
                dict(error=error))
            log(f'[sample] {tag}: {record_meta["uid"]} -> {error}')
            continue
        summary, lift_error, _route = _lift(adapter, chosen['primitives'],
                                            assigned_layer, stack)
        entry = dict(manual_group=record_meta['manual_group'],
                     authoritative_route_id=authoritative['route_id']
                     if authoritative else None,
                     path=path_info)
        if lift_error:
            entry['error'] = lift_error
        else:
            entry.update(summary)
            entry['layer_from_metadata'] = assigned_layer
            entry['layer_executed'] = summary['target_layer']
            entry['layer_matches_metadata'] = (
                summary['target_layer'] == assigned_layer)
        add(tag, record_meta, 'manual', assigned_layer, 'u_geometry', entry)
        log(f'[sample] {tag}: {record_meta["uid"]} group={record_meta["manual_group"]} '
            f'-> layer L{summary["target_layer"]} z={summary["layer_z_mm"]}mm '
            f'len={summary["length_mm"]}mm (authoritative route_id '
            f'{entry["authoritative_route_id"]})')

    # ---- 3: control - the same L1 record under the old-algorithm layer policy
    record_meta = next(record for record in metadata
                       if record['routing_method'] == 'manual_fixed_u'
                       and record['assigned_layer'] == 1
                       and record['dataset'] == 'z1')
    adapter = by_pair[('z1', record_meta['pair'])]
    chosen, error, path_info = _u_path(adapter)
    summary, lift_error, _route = _lift(adapter, chosen['primitives'],
                                        OLD_ALGORITHM_START_LAYER, stack)
    entry = dict(path=path_info, note=('same connection executed under the '
                                       'old-algorithm layer policy'))
    if lift_error:
        entry['error'] = lift_error
    else:
        entry.update(summary)
        entry['layer_executed'] = summary['target_layer']
        entry['layer_from_metadata'] = 1
        entry['layer_matches_metadata'] = False
    add('control_manual_L1_under_old_policy', record_meta, 'old_algorithm_control',
        OLD_ALGORITHM_START_LAYER, 'u_geometry', entry)
    log(f'[sample] control: same {record_meta["uid"]} under old-algorithm policy '
        f'-> L{summary["target_layer"]} z={summary["layer_z_mm"]}mm '
        f'(metadata layer was L1)')

    # ---- 4: explicitly marked L5+ record -> old algorithm (CSV layer NOT executed)
    record_meta = next(record for record in metadata
                       if record['routing_method'] == 'manual_fixed_u'
                       and record['dataset'] == 'z2'
                       and (record['assigned_layer'] or 0) >= 5)
    adapter = by_pair[('z2', record_meta['pair'])]
    chosen, error, path_info = _u_path(adapter)
    summary, lift_error, _route = _lift(adapter, chosen['primitives'],
                                        OLD_ALGORITHM_START_LAYER, stack)
    entry = dict(path=path_info,
                 note=('explicitly marked but assigned L5+ -> old algorithm; the '
                       'CSV layer is deliberately not executed'))
    if lift_error:
        entry['error'] = lift_error
    else:
        entry.update(summary)
        entry['layer_executed'] = summary['target_layer']
        entry['layer_from_metadata'] = record_meta['assigned_layer']
        entry['layer_matches_metadata'] = (
            summary['target_layer'] == record_meta['assigned_layer'])
    add('marked_L5plus_old_algorithm', record_meta, 'old_algorithm',
        OLD_ALGORITHM_START_LAYER, 'u_geometry', entry)
    log(f'[sample] marked L5+: {record_meta["uid"]} csv_layer='
        f'{record_meta["assigned_layer_csv"]} -> executed L'
        f'{summary["target_layer"]} (CSV layer not executed)')

    # ---- 5: unmarked record -> old algorithm, layer L5
    record_meta = next(record for record in metadata
                       if record['routing_method'] == 'existing_algorithm'
                       and record['dataset'] == 'z1')
    adapter = by_pair[('z1', record_meta['pair'])]
    primitives, error, path_info = _engine_path(adapter)
    if error:
        add('unmarked_old_algorithm', record_meta, 'old_algorithm',
            OLD_ALGORITHM_START_LAYER, 'engine_2d', dict(error=error))
        log(f'[sample] unmarked: {record_meta["uid"]} -> {error}')
    else:
        summary, lift_error, _route = _lift(adapter, primitives,
                                            OLD_ALGORITHM_START_LAYER, stack)
        entry = dict(path=path_info)
        if lift_error:
            entry['error'] = lift_error
        else:
            entry.update(summary)
            entry['layer_executed'] = summary['target_layer']
            entry['layer_from_metadata'] = None
            entry['layer_matches_metadata'] = None
        add('unmarked_old_algorithm', record_meta, 'old_algorithm',
            OLD_ALGORITHM_START_LAYER, 'engine_2d', entry)
        log(f'[sample] unmarked: {record_meta["uid"]} (existing_algorithm) -> '
            f'L{summary["target_layer"]} z={summary["layer_z_mm"]}mm '
            f'len={summary["length_mm"]}mm')

    # ---- layer/path effect summary (rule 5 evidence)
    manual_ok = [item for key, item in samples.items()
                 if item['policy'] == 'manual' and 'error' not in item]
    control = samples['control_manual_L1_under_old_policy']
    effect = dict(
        manual_records_executed=len(manual_ok),
        manual_layers=dict(sorted(
            (item['layer_executed'], item.get('length_mm')) for item in manual_ok))
        if manual_ok else {},
        manual_layer_equals_metadata=all(item.get('layer_matches_metadata')
                                         for item in manual_ok),
        control_layer=control.get('layer_executed'),
        control_layer_z_mm=control.get('layer_z_mm'),
        control_path_length_mm=control.get('length_mm'),
        manual_same_record=dict(
            layer=manual_ok[0].get('layer_executed') if manual_ok else None,
            layer_z_mm=manual_ok[0].get('layer_z_mm') if manual_ok else None,
            path_length_mm=manual_ok[0].get('length_mm') if manual_ok else None),
        note=('the manual grouping changes the physical layer (and therefore the '
              '3D path height and total length), not just the routing order'),
    )
    return dict(schema='four_side_1024_manual_c4_adapt_sample_v1',
                layer_stack=dict(
                    preset='medium_050',
                    interface_rows={'z1': 0.0, 'z2': 0.5},
                    heights={layer: stack.z_for_layer(layer)
                             for layer in (2, 3, 4, 5)},
                    note='existing four_side_1024.l3d stack'),
                policy=dict(manual_layers=list(MANUAL_LAYER_RANGE),
                            old_algorithm_start_layer=OLD_ALGORITHM_START_LAYER),
                samples=samples,
                layer_path_effect=effect)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(
        description='manual grouping -> authoritative topology mapping check '
                    '(static + one small sample)')
    parser.add_argument('--json', default=str(OUTPUT_JSON))
    parser.add_argument('--static-only', action='store_true')
    args = parser.parse_args(argv)
    started = time.perf_counter()
    static = static_check()
    adapter_inputs = load_manual_c4_inputs()
    payload = dict(validation=adapter_inputs.validation, mapping=static)
    if not args.static_only:
        payload['sample'] = sample_execution(adapter_inputs)
        effect = payload['sample']['layer_path_effect']
        _log(f'[sample] layer/path effect: manual layers='
             f'{effect["manual_layers"]} control L{effect["control_layer"]} '
             f'(z={effect["control_layer_z_mm"]} mm)')
    payload['elapsed_s'] = round(time.perf_counter() - started, 2)
    path = Path(args.json)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1,
                               default=str), encoding='utf-8')
    _log(f'written {path}')
    return 0 if static['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
