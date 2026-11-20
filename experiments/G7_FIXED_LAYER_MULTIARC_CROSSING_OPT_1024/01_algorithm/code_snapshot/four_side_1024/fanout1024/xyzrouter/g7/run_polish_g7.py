# -*- coding: utf-8 -*-
"""G7 deterministic fixed-layer polish (greedy best-improvement).

Runs after the SA arms: for every modifiable route (ordered by current crossing
count) enumerate its pre-filtered candidate pool, evaluate every candidate with
the same authoritative strict-D56 rule, and commit the best strictly improving
body replacement.  Repeats passes until no route improves (or a time budget is
hit), then optionally tries atomic two-route combinations on the remaining
hottest crossing pairs.

Usage::

    python -m ...g7.run_polish_g7 \
        --start <sa best_routes.json> --reference <G6 routes_l3d.json> \
        --out <dir> --seconds 1200
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import random
import sys
import time

from . import frozen as FR
from . import engine as EN
from . import sa as SA


def _load(path):
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', required=True)
    parser.add_argument('--reference', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--seconds', type=float, default=1200.0)
    parser.add_argument('--passes', type=int, default=6)
    parser.add_argument('--pool-size', type=int, default=24)
    parser.add_argument('--pool-build', type=int, default=160)
    parser.add_argument('--pair-hotspots', type=int, default=40)
    parser.add_argument('--seed', type=int, default=7701)
    args = parser.parse_args(argv)
    root = os.path.abspath(__file__)
    for _ in range(5):
        root = os.path.dirname(root)
    if root not in sys.path:
        sys.path.insert(0, root)
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(os.path.join(args.out, 'logs'), exist_ok=True)
    log_handle = open(os.path.join(args.out, 'logs', 'polish.log'), 'w',
                      encoding='utf-8')

    def log(message):
        line = '[%s] %s' % (time.strftime('%H:%M:%S'), message)
        print(line, flush=True)
        log_handle.write(line + '\n')
        log_handle.flush()

    doc = _load(args.start)
    reference = _load(args.reference)
    manifest = FR.build_manifest(reference['routes'])
    if not FR.verify_payload(doc['routes'], manifest)['pass']:
        raise SystemExit('start payload is not fixed-layer clean')
    cfg = dict(SA.DEFAULT_CFG)
    cfg.update(pool_size=args.pool_size, pool_build=args.pool_build)
    rng = random.Random(args.seed)
    state = SA.G7SA(doc, manifest, args.out, cfg=cfg, log=log)
    start_time = time.time()
    deadline = start_time + float(args.seconds)
    history = []
    initial = dict(crossings=int(state.pw.total_crossings),
                   unique_pairs=int(state.pw.unique_pairs),
                   min_angle_deg=round(state.pw.min_angle() or 0.0, 9),
                   length_mm=round(state._length(), 6))
    log('polish start: crossings=%d pairs=%d min=%.9f'
        % (state.pw.total_crossings, state.pw.unique_pairs,
           state.pw.min_angle() or 0.0))
    for attempt_pass in range(int(args.passes)):
        improved = False
        order = sorted(state.movable,
                       key=lambda rid: -state.pw.route_crossings.get(rid, 0))
        for rid in order:
            if time.time() > deadline:
                log('time budget reached')
                break
            result = state._best_candidate(rid, int(args.pool_size), top_only=True)
            if result is None or result['delta'] >= 0:
                continue
            move = dict(kind='N1', ids=[rid],
                        replacements={rid: result['candidate']['prims']},
                        routes={rid: result['candidate']['route']},
                        crossings={rid: result['crossings']},
                        delta=result['delta'])
            if not state._commit(move):
                continue
            state._sync()
            history.append(dict(kind='single', route_id=rid,
                                delta=result['delta'],
                                crossings=state.pw.total_crossings))
            log('single route %d: %+d -> crossings=%d'
                % (rid, result['delta'], state.pw.total_crossings))
            improved = True
        if improved:
            state._write_best(force=True)
        if not improved:
            log('pass %d: no single-route improvement' % (attempt_pass + 1))
            break
    # atomic pair polish on the hottest residual crossings
    if time.time() < deadline:
        pairs = sorted(state.pw.pair_counts.items(),
                       key=lambda item: -item[1])[:int(args.pair_hotspots)]
        for _pair, _count in pairs:
            if time.time() > deadline:
                break
            ids = [rid for rid in _pair if rid in state.movable_set]
            if len(ids) < 2:
                continue
            cands = {}
            for rid in ids:
                pool = state.pool.candidates(rid, int(args.pool_size))
                cands[rid] = pool
            if len(cands) < 2:
                continue
            best = None
            combos = [(a, b) for a in cands[ids[0]] for b in cands[ids[1]]]
            rng.shuffle(combos)
            for cand_a, cand_b in combos[:12]:
                replacements = {ids[0]: cand_a['prims'],
                                ids[1]: cand_b['prims']}
                result = state.pw.evaluate_batch(replacements)
                if not result['ok'] or result['delta'] >= 0:
                    continue
                angles = [event['angle_deg']
                          for event in result['new_events'].values()]
                if angles and min(angles) < SA.THETA:
                    continue
                ok3d = all(not state.pw.body_3d_issues(rid, route)
                           for rid, route in ((ids[0], cand_a['route']),
                                              (ids[1], cand_b['route'])))
                if not ok3d:
                    continue
                if best is None or result['delta'] < best['delta']:
                    best = dict(delta=result['delta'],
                                replacements=replacements,
                                new_events=result['new_events'])
            if best is None:
                continue
            move = dict(kind='N2', ids=list(ids),
                        replacements=best['replacements'],
                        routes={}, batch_events=best['new_events'],
                        delta=best['delta'])
            if not state._commit(move):
                continue
            state._sync()
            history.append(dict(kind='pair', routes=list(ids),
                                delta=best['delta'],
                                crossings=state.pw.total_crossings))
            log('pair %s: %+d -> crossings=%d'
                % (ids, best['delta'], state.pw.total_crossings))
            state._write_best(force=True)
    state._write_best(force=True)
    verify = FR.verify_payload([state.pw.routes[rid]
                                for rid in sorted(state.pw.routes)], manifest)
    reaudit = state.pw.full_reaudit()
    report = dict(schema='g7_polish_v1',
                  initial=initial,
                  initial_crossings=initial['crossings'],
                  initial_pairs=initial['unique_pairs'],
                  initial_min_angle_deg=initial['min_angle_deg'],
                  initial_length_mm=initial['length_mm'],
                  start=os.path.abspath(args.start),
                  reference=os.path.abspath(args.reference),
                  crossings=int(state.pw.total_crossings),
                  unique_pairs=int(state.pw.unique_pairs),
                  min_angle_deg=round(state.pw.min_angle() or 0.0, 9),
                  length_mm=round(state._length(), 6),
                  moves=len(history), history=history,
                  fixed_structure_pass=verify['pass'],
                  fixed_violation_count=verify['violation_count'],
                  full_reaudit=reaudit,
                  fixed_manifest_entries=len(manifest['entries']),
                  elapsed_seconds=round(time.time() - start_time, 2),
                  generated_at=time.strftime('%Y-%m-%dT%H:%M:%S'))
    with open(os.path.join(args.out, 'summary.json'), 'w',
              encoding='utf-8') as handle:
        json.dump(report, handle, indent=1, ensure_ascii=False)
    log('polish done: crossings=%d pairs=%d fixed_pass=%s reaudit_match=%s'
        % (report['crossings'], report['unique_pairs'],
           report['fixed_structure_pass'], reaudit['matches']))
    log_handle.close()
    state.close()
    return 0 if report['fixed_structure_pass'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
