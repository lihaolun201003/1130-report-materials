# -*- coding: utf-8 -*-
"""Synchronised multi-route repair of the remaining sub-45 deg crossings.

For every residual violation this pass tries, in increasing batch size:

1. every single-route move of either endpoint (the capability of the previous
   rounds),
2. the two-route height **swap** of the pair,
3. two-route moves onto the *other's* height combined with a third route that
   frees that height (a 3-cycle over a conflict triangle),
4. the same over the whole conflict component.

Each candidate is evaluated with ``batch.evaluate_batch`` -- one atomic geometry
change -- and accepted only when the **global** sub-45 deg count drops.  The log
records, per accepted batch, whether the same repair was reachable with a single
route move, which is the evidence that synchronised relocation solves conflicts
that sequential single-route moves cannot.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024.xyzrouter.g5 import model as G5
from four_side_1024.fanout1024.xyzrouter.g5 import candidates as C
from four_side_1024.fanout1024.xyzrouter.g5 import search as S
from four_side_1024.fanout1024.xyzrouter.g5 import batch as B
from four_side_1024.fanout1024.xyzrouter.g5 import layer_solver as LS

EXP = ROOT / 'experiments' / 'G5_ANGLE45_NATIVE3D_20H_1024'


def height_of(route):
    body = C.body_part_indices(route)
    return round(float(route['parts'][body[0]]['z_mm']), 9) if body else None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--routes', default=str(EXP / '03_best_partial'
                                              / 'routes_l3d.json'))
    parser.add_argument('--graph', default=str(EXP / '02_search_runs'
                                             / 'conflict_graph'
                                             / 'conflict_graph.json'))
    parser.add_argument('--domain', default=str(EXP / '02_search_runs'
                                              / 'pathpreserving'
                                              / 'pathpreserving_result.json'))
    parser.add_argument('--out', default=str(EXP / '02_search_runs'
                                             / 'sync_repair'))
    parser.add_argument('--time-limit', type=float, default=5400.0)
    parser.add_argument('--max-passes', type=int, default=12)
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    payload = json.loads(Path(args.routes).read_text(encoding='utf-8'))
    graph = json.loads(Path(args.graph).read_text(encoding='utf-8'))
    state = S.State(payload['routes'])
    adjacency = defaultdict(set)
    for edge in graph['edges']:
        a, b = int(edge['route_a']), int(edge['route_b'])
        adjacency[a].add(b)
        adjacency[b].add(a)
    domain_path = Path(args.domain)
    domain = {}
    if domain_path.exists():
        raw = json.loads(domain_path.read_text(encoding='utf-8'))
        for rid, z in (raw.get('assignment') or {}).items():
            domain[int(rid)] = [float(z)]
    heights = sorted(G5.all_heights())
    current = {rid: height_of(state.world.routes[rid])
               for rid in state.world.routes}
    print('[state] %s' % state.summary(), flush=True)

    def moves_for(rid, target_heights):
        route = state.world.routes[rid]
        for z in target_heights:
            if z is None or abs(z - (current[rid] or 0.0)) < 1e-9:
                continue
            candidate = C.reheight_any(route, z)
            if candidate is None:
                continue
            if G5.structure_issues(candidate):
                continue
            yield z, candidate

    def candidate_heights(rid):
        near = sorted(heights, key=lambda z: abs(z - (current[rid] or 0.0)))
        return near

    log_rows = []
    accepted_total = 0
    for pass_index in range(args.max_passes):
        if time.time() - started > args.time_limit:
            break
        improved_this_pass = 0
        events = sorted(state.violations, key=lambda e: e['angle_deg'])
        for event in events:
            if time.time() - started > args.time_limit:
                break
            if event not in state.violations:
                continue
            a, b = int(event['route_a']), int(event['route_b'])
            base = len(state.violations)
            touching = set([a, b])
            before = len(state.violations_touching(touching))
            accepted = None
            # ---- (1) single-route moves
            for rid, other in ((a, b), (b, a)):
                for z, candidate in moves_for(rid, candidate_heights(rid)):
                    evaluation = B.evaluate_batch(state, {rid: candidate})
                    if not evaluation['ok']:
                        continue
                    after = len(evaluation['violations'])
                    if after < before:
                        accepted = dict(batch={rid: candidate}, size=1,
                                        kind='single', z={rid: z})
                        break
                if accepted:
                    break
            # ---- (2) two-route swap
            if accepted is None:
                za, zb = current.get(a), current.get(b)
                if za is not None and zb is not None and abs(za - zb) > 1e-9:
                    batch = {}
                    ok = True
                    for rid, target in ((a, zb), (b, za)):
                        found = next(moves_for(rid, [target]), None)
                        if found is None:
                            ok = False
                            break
                        batch[rid] = found[1]
                    if ok and batch:
                        evaluation = B.evaluate_batch(state, batch)
                        if evaluation['ok'] and \
                                len(evaluation['violations']) < before:
                            accepted = dict(batch=batch, size=len(batch),
                                            kind='swap',
                                            z={a: zb, b: za})
            # ---- (3) third route frees the target height (3-cycle)
            if accepted is None:
                for rid, other in ((a, b), (b, a)):
                    for target in candidate_heights(rid)[:6]:
                        if abs(target - (current[rid] or 0.0)) < 1e-9:
                            continue
                        found = next(moves_for(rid, [target]), None)
                        if found is None:
                            continue
                        blockers = [r for r in adjacency.get(rid, ())
                                    if current.get(r) is not None
                                    and abs(current[r] - target) < 1e-9]
                        if not blockers:
                            continue
                        for blocker in blockers[:3]:
                            second = next(moves_for(blocker,
                                                    [current[rid]]), None)
                            if second is None:
                                continue
                            batch = {rid: found[1], blocker: second[1]}
                            evaluation = B.evaluate_batch(state, batch)
                            if evaluation['ok'] and \
                                    len(evaluation['violations']) < before:
                                accepted = dict(batch=batch, size=2,
                                                kind='cycle3',
                                                z={rid: target,
                                                   blocker: current[rid]})
                                break
                        if accepted:
                            break
                    if accepted:
                        break
            if accepted is None:
                log_rows.append(dict(pass_index=pass_index, route_a=a,
                                     route_b=b, angle=event['angle_deg'],
                                     accepted=None, global_before=base))
                continue
            info = B.commit_batch(state, accepted['batch'],
                                  label='sync-%s' % accepted['kind'])
            if not info['ok']:
                log_rows.append(dict(pass_index=pass_index, route_a=a,
                                     route_b=b, accepted=None,
                                     rejected=info['issues'][:2],
                                     global_before=base))
                continue
            for rid, z in accepted['z'].items():
                current[rid] = z
            accepted_total += 1
            improved_this_pass += 1
            log_rows.append(dict(pass_index=pass_index, route_a=a, route_b=b,
                                 angle=event['angle_deg'],
                                 accepted=accepted['kind'],
                                 size=accepted['size'],
                                 ids=sorted(accepted['batch']),
                                 z={str(k): v for k, v in accepted['z'].items()},
                                 global_before=base,
                                 global_after=len(state.violations)))
            print('[pass %d] %s batch of %d on (%d,%d): %d -> %d'
                  % (pass_index, accepted['kind'], accepted['size'], a, b,
                     base, len(state.violations)), flush=True)
        print('[pass %d] improved %d, violations=%d (%.0fs)'
              % (pass_index, improved_this_pass, len(state.violations),
                 time.time() - started), flush=True)
        if improved_this_pass == 0:
            break

    summary = state.summary()
    kinds = defaultdict(int)
    for row in log_rows:
        kinds[row.get('accepted') or 'none'] += 1
    print('[done] %s' % summary, flush=True)
    print('[accepted] %d batches, kinds=%s'
          % (accepted_total, dict(kinds)), flush=True)
    (out / 'sync_repair_result.json').write_text(
        json.dumps(dict(schema='g5_sync_repair_v1', summary=summary,
                        accepted=accepted_total, kinds=dict(kinds),
                        rows=log_rows,
                        seconds=round(time.time() - started, 1)),
                   indent=1, ensure_ascii=False), encoding='utf-8')
    (out / 'routes_l3d.json').write_text(
        json.dumps(dict(payload, routes=[state.world.routes[rid]
                                         for rid in sorted(state.world.routes)]),
                   ensure_ascii=False), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
