# -*- coding: utf-8 -*-
"""Experiment 2 -- independent audit of the Stage-0 multi-arc conversion cost.

The historical ablation had to *re-express* the 197 inherited multi-arc routes in
the ablated grammar before the OFF search could start.  That one-off step is
effect **A** (geometric conversion cost) and must never be mixed with effect
**B** (search ability under an identical start) or effect **C** (total ON/OFF
difference).  This script re-derives A from the archived states themselves.

Definitions used (they matter -- do not mix them):

* ``per_route_events``   -- number of same-plane crossing *events* the route
  participates in.  It is **not additive**: events between two converted routes
  are counted twice, so ``sum(per_route_events_before)`` equals
  ``2 * total_before``.
* ``delta_commit``       -- the change of the **global** crossing total caused by
  replacing that one route while all other routes keep their geometry.  The
  conversion commits the routes one at a time, so ``sum(delta_commit)`` equals
  the global change of the conversion, exactly.
* ``delta_replay``       -- ``delta_commit`` re-executed here from scratch, in the
  recorded order, with the frozen engine.  It is the independent check of the
  archived per-route attribution.

Writes ``tables/stage0_per_route.csv`` and ``tables/stage0_audit.json``.

Usage::

    python experiments/G4_MULTI_ARC_ABLATION_FINAL_1024/tools/analyze_stage0.py
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
ROOT = EXP.parents[1]
for path in (str(ROOT), str(HERE)):
    if path not in sys.path:
        sys.path.insert(0, path)

import audit_state as AUDIT  # noqa: E402

from four_side_1024.fanout1024 import layer2d as L2                      # noqa: E402
from four_side_1024.fanout1024.xyzrouter import route_builder as RB      # noqa: E402
from four_side_1024.fanout1024.xyzrouter import world_adapter as WA      # noqa: E402
from four_side_1024.fanout1024.reheight21 import model as M              # noqa: E402

R15 = 15.0
G3_DIR = ROOT / 'outputs' / 'manual_c4_new_connectivity' / 'XYZ_JOINT_G123_1024' / 'best_valid'
OLD_REPO = Path('C:/Users/lihao/Desktop/Graduation Project/work/1130-report-materials/'
                'G4_MULTI_ARC_ABLATION_1024')
CONVERT_DIR = OLD_REPO / 'no_multi_arc' / '01_convert'


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def canonical_of(state, route_id):
    row = state.row(route_id)
    route = state.routes[route_id]
    layer = int(row['target_layer'])
    z = float(row['target_z_mm'])
    if layer in (1001, 1002):
        task = RB.direct_task(row)
    else:
        task, _s, _t = RB.body_task(row, layer, z, *RB.lead_lengths(route))
    frame, error = L2.canonical_frame(task)
    if error:
        return None, None
    return str(frame['kind']), abs(float(frame['bx']))


def load_state(run_dir):
    payload = read_json(Path(run_dir) / 'routes_l3d.json')
    rows = AUDIT.read_rows(Path(run_dir) / 'assignment_1024.csv')
    rows = RB.normalized_rows(rows, stack=M.layer_stack())
    state = WA.RouteWorld(payload['routes'], rows, log=lambda *_a: None)
    return state, payload, rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default=str(EXP / 'tables'))
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    report = read_json(CONVERT_DIR / 'conversion_report.json')
    before = AUDIT.audit_run(G3_DIR, label='G3_start_1322')
    after = AUDIT.audit_run(CONVERT_DIR, label='stage0_converted')
    per_before = {int(k): int(v) for k, v in before['per_route_crossings'].items()}
    per_after = {int(k): int(v) for k, v in after['per_route_crossings'].items()}

    g3_payload = read_json(G3_DIR / 'routes_l3d.json')
    cv_payload = read_json(CONVERT_DIR / 'routes_l3d.json')
    g3_routes = {int(r['route_id']): r for r in g3_payload['routes']}
    cv_routes = {int(r['route_id']): r for r in cv_payload['routes']}
    cv_rows = {int(r['route_id']): r for r in
               RB.normalized_rows(AUDIT.read_rows(CONVERT_DIR / 'assignment_1024.csv'),
                                  stack=M.layer_stack())}

    state, _payload, _rows = load_state(G3_DIR)
    state.start_crossings = dict(state.per_route_counts()[0])
    # canonical body frame of the *inherited* (G3) geometry: must be taken
    # BEFORE the replay mutates the state
    canon = {}
    for record in report['records']:
        rid = int(record['route_id'])
        canon[rid] = canonical_of(state, rid)

    # --- independent replay of the sequential conversion --------------------
    replay_total = int(state.total)
    replay_deltas = {}
    replay_totals = {}
    order = [int(record['route_id']) for record in report['records']]
    for rid in order:
        new_route = copy.deepcopy(cv_routes[rid])
        new_row = dict(cv_rows[rid])
        record = state.commit(rid, new_route, new_row=new_row,
                              note='stage0 replay')
        replay_deltas[rid] = int(record['delta'])
        replay_total = int(state.total)
        replay_totals[rid] = replay_total
    final_matches = all(
        json.dumps(state.routes[rid], sort_keys=True) ==
        json.dumps(cv_routes[rid], sort_keys=True) for rid in cv_routes)
    replay_crossings = int(state.total)

    rows = []
    for record in report['records']:
        rid = int(record['route_id'])
        kind, offset = canon.get(rid, (None, None))
        g3 = g3_routes.get(rid) or {}
        cv = cv_routes.get(rid) or {}
        rows.append(dict(
            route_id=rid,
            frame_kind=kind or 'direct',
            lateral_offset_mm=(None if offset is None else round(offset, 4)),
            below_2R=(None if offset is None else bool(offset < 2 * R15 - 1e-9)),
            per_route_events_before=int(per_before.get(rid, 0)),
            per_route_events_after=int(per_after.get(rid, 0)),
            per_route_events_diff=int(per_after.get(rid, 0) - per_before.get(rid, 0)),
            delta_commit=int(record.get('delta') or 0),
            delta_replay=int(replay_deltas.get(rid, 0)),
            delta_matches=bool(int(record.get('delta') or 0)
                               == int(replay_deltas.get(rid, 0))),
            total_after_recorded=int(record.get('total_after') or 0),
            total_after_replay=int(replay_totals.get(rid, 0)),
            family=str(record.get('family')),
            chosen_kind=str(record.get('kind')),
            layer=int(record.get('layer') or 0),
            z_mm=record.get('z_mm'),
            old_multi_arc_regions=int(record.get('old_regions') or 0),
            new_multi_arc_regions=int(record.get('new_regions') or 0),
            length_before_mm=round(float(g3.get('length_mm') or 0.0), 6),
            length_after_mm=round(float(cv.get('length_mm') or 0.0), 6),
            length_delta_mm=round(float(cv.get('length_mm') or 0.0)
                                  - float(g3.get('length_mm') or 0.0), 6),
            n_transitions_before=int(g3.get('n_transitions') or 0),
            n_transitions_after=int(cv.get('n_transitions') or 0),
            source_endpoint=str(g3.get('source_endpoint')),
            target_endpoint=str(g3.get('target_endpoint')),
            same_endpoints=bool(
                str(g3.get('source_endpoint')) == str(cv.get('source_endpoint'))
                and str(g3.get('target_endpoint')) == str(cv.get('target_endpoint'))),
        ))
    rows.sort(key=lambda row: row['route_id'])

    with (out / 'stage0_per_route.csv').open('w', encoding='utf-8',
                                             newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    def bucket(predicate, key='delta_commit'):
        values = [row[key] for row in rows if predicate(row)]
        ordered = sorted(values)
        n = len(values)
        return dict(
            routes=n,
            sum_delta=int(sum(values)),
            mean_delta=round(sum(values) / n, 4) if n else None,
            median_delta=(ordered[n // 2] if n % 2
                          else round(0.5 * (ordered[n // 2 - 1]
                                            + ordered[n // 2]), 4)) if n else None,
            min_delta=(ordered[0] if n else None),
            max_delta=(ordered[-1] if n else None),
            share_positive=(round(sum(1 for v in values if v > 0) / n, 4)
                            if n else None),
            share_zero=(round(sum(1 for v in values if v == 0) / n, 4)
                        if n else None),
            share_negative=(round(sum(1 for v in values if v < 0) / n, 4)
                            if n else None))

    converted_ids = set(int(r['route_id']) for r in report['records'])
    summary = dict(
        schema='g4_multi_arc_stage0_audit_v1',
        g3=dict(dir=str(G3_DIR), sha256=before['routes_sha256'],
                crossings=before['crossings'],
                multi_arc_routes=before['multi_arc']['routes_with_multi_arc'],
                multi_arc_regions=before['multi_arc']['total_regions'],
                multi_arc_arcs=before['multi_arc']['arcs_in_regions'],
                routes=before['routes_loaded'],
                flat_arcs=before['flat_arcs'], flat_lines=before['flat_lines'],
                transition_parts=before['transition_parts'],
                total_length_mm=before['total_length_mm'],
                routes_with_crossings=before['routes_with_crossings'],
                max_route_crossings=before['max_route_crossings']),
        converted=dict(dir=str(CONVERT_DIR), sha256=after['routes_sha256'],
                       crossings=after['crossings'],
                       multi_arc_routes=after['multi_arc']['routes_with_multi_arc'],
                       multi_arc_regions=after['multi_arc']['total_regions'],
                       routes=after['routes_loaded'],
                       flat_arcs=after['flat_arcs'], flat_lines=after['flat_lines'],
                       transition_parts=after['transition_parts'],
                       total_length_mm=after['total_length_mm'],
                       routes_with_crossings=after['routes_with_crossings'],
                       max_route_crossings=after['max_route_crossings']),
        delta_total_independent=int(after['crossings'] - before['crossings']),
        delta_total_reported=int(report['crossing_delta_from_start']),
        replay=dict(
            order_recorded=len(order),
            replay_crossings_final=int(replay_crossings),
            replay_equals_converted_state=bool(final_matches),
            all_deltas_match=bool(all(row['delta_matches'] for row in rows)),
            mismatched_route_ids=[row['route_id'] for row in rows
                                  if not row['delta_matches']],
            all_totals_match=bool(all(row['total_after_recorded']
                                      == row['total_after_replay'] for row in rows)),
            sum_replay_delta=int(sum(row['delta_replay'] for row in rows)),
        ),
        targets=int(report['targets']), converted_count=int(report['converted']),
        residual=int(report['residual']),
        records=len(rows),
        sum_commit_delta=int(sum(row['delta_commit'] for row in rows)),
        by_threshold={
            'below_2R': bucket(lambda row: row['below_2R'] is True),
            'at_or_above_2R': bucket(lambda row: row['below_2R'] is False),
        },
        by_threshold_replay={
            'below_2R': bucket(lambda row: row['below_2R'] is True,
                               key='delta_replay'),
            'at_or_above_2R': bucket(lambda row: row['below_2R'] is False,
                                     key='delta_replay'),
        },
        by_family=dict(Counter(row['family'] for row in rows)),
        by_frame_kind=dict(Counter(row['frame_kind'] for row in rows)),
        identity=dict(
            routes_before=len(g3_routes), routes_after=len(cv_routes),
            same_route_id_set=bool(set(g3_routes) == set(cv_routes)),
            endpoints_identical=bool(all(row['same_endpoints'] for row in rows)),
            endpoints_mismatch_ids=[row['route_id'] for row in rows
                                    if not row['same_endpoints']],
        ),
        length=dict(
            g3_total_length_mm=before['total_length_mm'],
            converted_total_length_mm=after['total_length_mm'],
            converted_minus_g3_mm=round(after['total_length_mm']
                                        - before['total_length_mm'], 6),
            converted_routes_length_delta_sum_mm=round(
                sum(row['length_delta_mm'] for row in rows), 6),
        ),
        non_additivity=dict(
            sum_per_route_events_diff=int(sum(row['per_route_events_diff']
                                              for row in rows)),
            global_delta=int(after['crossings'] - before['crossings']),
            note='sum(per-route event diffs) - global delta = number of '
                 'crossing events whose BOTH routes are converted routes '
                 '(each counted twice in the per-route sums)',
            converted_pair_events_implied=int(
                sum(row['per_route_events_diff'] for row in rows)
                - (after['crossings'] - before['crossings'])),
        ),
        planner=report.get('planner'),
        policy=report.get('policy'),
    )
    (out / 'stage0_audit.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=1)[:6000])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
