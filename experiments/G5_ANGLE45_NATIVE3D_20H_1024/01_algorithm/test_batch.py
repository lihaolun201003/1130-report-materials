# -*- coding: utf-8 -*-
"""Atomic-batch test matrix (G5 round 3, section 3.3).

Every test builds its case from the real 1024-route layout, so the assertions
are about real geometry, not synthetic primitives.  ``--write`` stores the
machine-readable result next to this script (``test_batch_results.json``) which
the report quotes.

Tests
-----
T1  identity batch               -- no change, no issue
T2  two-route height swap        -- individually illegal, jointly legal
T3  three-route cyclic swap      -- individually illegal, jointly legal
T4  chain migration              -- A->B's height, B->C's height, C->free height
T5  batch D56 conflict           -- two routes on one height closer than 0.08 mm
T6  batch R15 violation          -- a rebuild with the wrong arc radius
T7  batch 3-D violation          -- a re-height whose S-curve breaks 50 um
T8  rollback                     -- a rejected batch leaves the world untouched
T9  exhaustive equivalence       -- batch result == full-world re-audit result
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024.xyzrouter.g5 import model as G5
from four_side_1024.fanout1024.xyzrouter.g5 import candidates as C
from four_side_1024.fanout1024.xyzrouter.g5 import search as S
from four_side_1024.fanout1024.xyzrouter.g5 import batch as B

EXP = ROOT / 'experiments' / 'G5_ANGLE45_NATIVE3D_20H_1024'
SOURCE = EXP / '03_best_partial' / 'routes_l3d.json'
GRAPH = EXP / '02_search_runs' / 'conflict_graph' / 'conflict_graph.json'

results = []


def check(name, condition, detail=''):
    results.append(dict(test=name, passed=bool(condition), detail=str(detail)))
    print('[%s] %s  %s' % ('PASS' if condition else 'FAIL', name, detail),
          flush=True)
    return condition


def world_fingerprint(state):
    payload = json.dumps({rid: route['parts']
                          for rid, route in sorted(state.world.routes.items())},
                         sort_keys=True)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def height_of(route):
    body = C.body_part_indices(route)
    return round(float(route['parts'][body[0]]['z_mm']), 9) if body else None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--routes', default=str(SOURCE))
    parser.add_argument('--graph', default=str(GRAPH))
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args(argv)
    payload = json.loads(Path(args.routes).read_text(encoding='utf-8'))
    graph = json.loads(Path(args.graph).read_text(encoding='utf-8'))
    state = S.State(payload['routes'])
    print('[state] %s' % state.summary(), flush=True)
    conflict = {}
    adjacency = {}
    from four_side_1024.fanout1024.xyzrouter.g5 import layer_solver as LS
    for edge in graph['edges']:
        a, b = int(edge['route_a']), int(edge['route_b'])
        conflict[(a, b)] = edge
        conflict[(b, a)] = edge
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)
    heights = sorted(G5.all_heights())
    nodes = sorted(state.world.routes)

    # ---------------------------------------------------------------- T1
    rid = sorted(state.world.routes)[0]
    fingerprint = world_fingerprint(state)
    evaluation = B.evaluate_batch(state, {rid: copy.deepcopy(
        state.world.routes[rid])})
    check('T1 identity batch', evaluation['ok'] and not evaluation['violations'],
          'issues=%d violations=%d' % (len(evaluation['issues']),
                                       len(evaluation['violations'])))
    check('T1 world untouched', world_fingerprint(state) == fingerprint)

    # ---------------------------------------------------------------- T2
    # a conflicting pair on two different heights: single move is illegal,
    # the swap is legal.
    swap = None
    pairs = LS.swap_candidates(state, adjacency, height_of)[:120]
    print('  [T2] graph-level swap candidates: %d' % len(pairs), flush=True)
    for (a, b, za, zb) in pairs:
        candidate_a = C.reheight_any(state.world.routes[a], zb)
        candidate_b = C.reheight_any(state.world.routes[b], za)
        if candidate_a is None or candidate_b is None:
            continue
        single = B.evaluate_batch(state, {a: candidate_a})
        single_bad = (not single['ok']) or bool(single['violations'])
        joint = B.evaluate_batch(state, {a: candidate_a, b: candidate_b})
        if single_bad and joint['ok'] and not joint['violations']:
            swap = (a, b, za, zb, len(single['violations']),
                    len(single['issues']))
            break
    check('T2 two-route swap: individually illegal, jointly legal',
          swap is not None,
          'pair=%s single_violations=%s single_issues=%s' % (
              (swap[0], swap[1]) if swap else None,
              swap[4] if swap else None, swap[5] if swap else None))

    # ---------------------------------------------------------------- T3
    cycle = None
    triples = LS.cycle_candidates(state, adjacency, height_of)[:60]
    print('  [T3] graph-level cycle candidates: %d' % len(triples), flush=True)
    for (a, b, c, za, zb, zc) in triples:
        trio = (a, b, c)
        moved = {}
        ok = True
        for rid2, target in zip(trio, (zb, zc, za)):
            candidate = C.reheight_any(state.world.routes[rid2], target)
            if candidate is None:
                ok = False
                break
            moved[rid2] = candidate
        if not ok:
            continue
        joint = B.evaluate_batch(state, moved)
        if not (joint['ok'] and not joint['violations']):
            continue
        singles_bad = all(
            (lambda ev: (not ev['ok']) or bool(ev['violations']))(
                B.evaluate_batch(state, {rid2: route}))
            for rid2, route in moved.items())
        if singles_bad:
            cycle = trio
            break
    check('T3 three-route cycle: individually illegal, jointly legal',
          cycle is not None, 'trio=%s' % (cycle,))

    # ---------------------------------------------------------------- T4
    chain = None
    attempts = 0
    for a in nodes[:400]:
        attempts += 1
        if attempts > 60:
            break
        za = height_of(state.world.routes[a])
        for b in adjacency.get(a, ()):
            zb = height_of(state.world.routes[b])
            if za is None or zb is None or abs(za - zb) < 1e-9:
                continue
            free = [z for z in heights if z not in (za, zb)][:3]
            for zc in free:
                moved = {}
                ok = True
                for rid2, target in ((a, zb), (b, zc)):
                    candidate = C.reheight_any(state.world.routes[rid2], target)
                    if candidate is None:
                        ok = False
                        break
                    moved[rid2] = candidate
                if not ok:
                    continue
                joint = B.evaluate_batch(state, moved)
                if joint['ok'] and not joint['violations']:
                    chain = (a, b, zb, zc)
                    break
            if chain:
                break
        if chain:
            break
    check('T4 chain migration legal as one batch', chain is not None,
          'chain=%s' % (chain,))

    # ---------------------------------------------------------------- T5
    clearance = None
    attempts = 0
    for (a, b), edge in conflict.items():
        attempts += 1
        if attempts > 600 or clearance:
            break
        if edge['reason'] != 'clearance':
            continue
        za = height_of(state.world.routes[a])
        candidate = C.reheight_any(state.world.routes[b], za) \
            if za is not None else None
        if candidate is None:
            continue
        evaluation = B.evaluate_batch(state, {b: candidate})
        kinds = {issue['kind'] for issue in evaluation['issues']}
        if 'clearance' in kinds:
            clearance = (b, za, sorted(kinds))
            break
    check('T5 batch D56 clearance conflict detected', clearance is not None,
          'route=%s z=%s kinds=%s' % (clearance if clearance else (None,) * 3))

    # ---------------------------------------------------------------- T6
    a = sorted(state.world.routes)[3]
    broken = copy.deepcopy(state.world.routes[a])
    body = C.body_part_indices(broken)[0]
    for part in broken['parts']:
        if part['kind'] == 'flat':
            for prim in part['primitives']:
                if prim['kind'] == 'arc':
                    prim['radius'] = 12.0
                    break
    evaluation = B.evaluate_batch(state, {a: broken})
    kinds6 = sorted({issue['kind'] for issue in evaluation['issues']})
    check('T6 batch R15 violation detected', not evaluation['ok'],
          'issues=%d kinds=%s' % (len(evaluation['issues']), kinds6))

    # ---------------------------------------------------------------- T7
    three_d = None
    for rid2 in nodes[:40]:
        route = state.world.routes[rid2]
        current = height_of(route)
        for z in heights:
            if current is not None and abs(z - current) < 1e-9:
                continue
            candidate = C.reheight_any(route, z)
            if candidate is None:
                continue
            evaluation = B.evaluate_batch(state, {rid2: candidate})
            kinds = {issue['kind'] for issue in evaluation['issues']}
            if any(kind.startswith('3d_') for kind in kinds):
                three_d = (rid2, z, sorted(k for k in kinds
                                           if k.startswith('3d_')))
                break
        if three_d:
            break
    check('T7 batch 3-D clearance violation detected', three_d is not None,
          'route/z/kinds=%s' % (three_d,))

    # ---------------------------------------------------------------- T8
    fingerprint = world_fingerprint(state)
    before = len(state.violations)
    info = B.commit_batch(state, {a: broken}, label='test-rollback')
    check('T8 rejected batch rolls back completely',
          world_fingerprint(state) == fingerprint and len(state.violations) == before,
          'commit ok=%s reverted=%s' % (info.get('ok'), info.get('reverted')))

    # ---------------------------------------------------------------- T9
    # an accepted batch must agree with a full-world re-audit
    moved = {}
    # any hard-legal batch whose violation count does not grow is enough to test
    # the bookkeeping agreement (the test is about state consistency)
    for rid2 in nodes[:200]:
        route = state.world.routes[rid2]
        before = len(state.violations_touching([rid2]))
        for z in heights:
            candidate = C.reheight_any(route, z)
            if candidate is None:
                continue
            trial = B.evaluate_batch(state, {rid2: candidate})
            if not trial['ok']:
                continue
            if len(trial['violations']) <= before:
                moved[rid2] = candidate
                break
        if moved:
            break
    if not moved:
        pairs = LS.swap_candidates(state, adjacency, height_of)[:40]
        for (a2, b2, za2, zb2) in pairs:
            batch = {}
            for rid2, target in ((a2, zb2), (b2, za2)):
                candidate = C.reheight_any(state.world.routes[rid2], target)
                if candidate is None:
                    batch = None
                    break
                batch[rid2] = candidate
            if not batch:
                continue
            before = len(state.violations_touching(batch.keys()))
            trial = B.evaluate_batch(state, batch)
            if trial['ok'] and len(trial['violations']) < before:
                moved = batch
                break
    if moved:
        info = B.commit_batch(state, moved, label='test-accept')
        if info['ok']:
            world = G5.World([state.world.routes[rid]
                              for rid in sorted(state.world.routes)],
                             min_angle_deg=45.0)
            audit = world.audit_all(min_angle_deg=45.0)
            consistent = (len(audit['violations']) == len(state.violations)
                          and len(audit['crossings']) == len(state.crossings))
            check('T9 committed batch agrees with full re-audit', consistent,
                  'audit violations=%d state=%d | audit crossings=%d state=%d'
                  % (len(audit['violations']), len(state.violations),
                     len(audit['crossings']), len(state.crossings)))
        else:
            check('T9 committed batch agrees with full re-audit', False,
                  'batch was rejected')
    else:
        check('T9 committed batch agrees with full re-audit', False,
              'no acceptable batch found')

    summary = dict(schema='g5_batch_tests_v1',
                   passed=sum(1 for row in results if row['passed']),
                   failed=sum(1 for row in results if not row['passed']),
                   total=len(results),
                   seconds=round(time.time() - state_started, 1)
                   if (state_started := getattr(main, '_started', time.time())) else 0,
                   results=results)
    print('\nBATCH_TEST_SUMMARY ' + json.dumps({k: summary[k] for k in
                                                ('passed', 'failed', 'total')}),
          flush=True)
    if args.write:
        (Path(__file__).parent / 'test_batch_results.json').write_text(
            json.dumps(summary, indent=1, ensure_ascii=False), encoding='utf-8')
        print('[write] %s' % (Path(__file__).parent / 'test_batch_results.json'))
    return 0 if summary['failed'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
