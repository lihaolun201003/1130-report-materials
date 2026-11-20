# -*- coding: utf-8 -*-
"""G5 round 3 driver: global joint layer assignment + atomic batch relocation.

Pipeline
--------
P0  load the current best legal-partial solution and rebuild its conflict graph;
P1  compute every route's *allowed height set* ``H_i`` (heights at which an exact
    legal R15 body can actually be built);
P2  solve the joint layer assignment with CP-SAT (OR-Tools) on the co-planarity
    conflict graph, minimising the number of routes that move;
P3  realise the assignment into real XYZ routes and evaluate the **whole change
    as one atomic batch**; every hard issue the batch reports is turned into a
    *no-good* clause ``((i, h_i), (j, h_j))`` that is fed back to CP-SAT, and the
    loop repeats;
P4  component-wise batch improvement of whatever residual violations remain:
    for each conflict component, enumerate group re-assignments (swaps, cycles,
    Kempe-chain recolourings) and accept the ones that lower the global count;
P5  log every batch (size, ids, old/target heights, violation delta, failure
    reason), checkpoint, and write the resulting routes.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
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


# --------------------------------------------------------------------------
def load_graph(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    adjacency = defaultdict(set)
    edges = []
    for edge in data['edges']:
        a, b = int(edge['route_a']), int(edge['route_b'])
        adjacency[a].add(b)
        adjacency[b].add(a)
        edges.append((a, b, edge['reason']))
    return adjacency, edges, data.get('summary', {})


def height_of(route):
    body = C.body_part_indices(route)
    return round(float(route['parts'][body[0]]['z_mm']), 9) if body else None


solve_cpsat = LS.solve_cpsat


def components(state):
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for event in state.violations:
        union(int(event['route_a']), int(event['route_b']))
    groups = defaultdict(list)
    for node in parent:
        groups[find(node)].append(node)
    return [sorted(value) for value in groups.values()]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--routes', default=str(EXP / '03_best_partial'
                                              / 'routes_l3d.json'))
    parser.add_argument('--graph', default=str(EXP / '02_search_runs'
                                             / 'conflict_graph'
                                             / 'conflict_graph.json'))
    parser.add_argument('--out', default=str(EXP / '02_search_runs'
                                             / 'batch_relayer'))
    parser.add_argument('--cp-time', type=float, default=120.0)
    parser.add_argument('--rounds', type=int, default=6)
    parser.add_argument('--time-limit', type=float, default=7200.0)
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    log_lines = []

    def log(message):
        line = str(message)
        print(line, flush=True)
        log_lines.append(line)

    payload = json.loads(Path(args.routes).read_text(encoding='utf-8'))
    state = S.State(payload['routes'])
    adjacency, edges, graph_summary = load_graph(args.graph)
    nodes = sorted(state.world.routes)
    current = {rid: height_of(state.world.routes[rid]) for rid in nodes}
    log('[start] %s' % state.summary())
    log('[graph] edges=%d nodes=%d' % (len(edges), len(nodes)))

    # ---------------------------------------------------------------- P1
    cache_path = out / 'allowed_heights.json'
    if cache_path.exists():
        raw = json.loads(cache_path.read_text(encoding='utf-8'))
        domain = {int(rid): [float(z) for z in values]
                  for rid, values in raw.items()}
        log('[P1] domains loaded (%d routes)' % len(domain))
    else:
        domain = {}
        for index, rid in enumerate(nodes):
            domain[rid] = LS.allowed_heights(state.world.routes[rid],
                                             cache=domain)
            if (index + 1) % 100 == 0:
                log('[P1] domains %d/%d (%.0fs)' % (index + 1, len(nodes),
                                                    time.time() - started))
        cache_path.write_text(json.dumps({str(rid): values
                                          for rid, values in domain.items()}),
                              encoding='utf-8')
    missing = [rid for rid in nodes if not domain.get(rid)]
    log('[P1] routes with an empty domain: %d %s'
        % (len(missing), missing[:10]))

    # ---------------------------------------------------------------- P2/P3
    no_goods = []
    history = []
    best_state = {rid: json.loads(json.dumps(state.world.routes[rid]))
                  for rid in nodes}
    best_violations = len(state.violations)
    for round_index in range(args.rounds):
        if time.time() - started > args.time_limit:
            log('[stop] time limit')
            break
        log('[P2] solving joint layer assignment (round %d, %d no-goods)'
            % (round_index, len(no_goods)))
        assignment, status = solve_cpsat(
            nodes, adjacency, domain, current, no_goods,
            time_limit=args.cp_time, log=log)
        if assignment is None:
            log('[P2] hard colouring infeasible (%s); retrying in '
                'minimum-conflict mode' % status)
            assignment, status = solve_cpsat(
                nodes, adjacency, domain, current, no_goods,
                time_limit=args.cp_time, log=log, soft=True)
            if assignment is None:
                log('[P2] CP-SAT found no assignment even in soft mode '
                    '(status=%s)' % status)
                break
            log('[P2] soft assignment found (status=%s)' % status)
        moved = {rid: z for rid, z in assignment.items()
                 if current.get(rid) is not None
                 and abs(z - current[rid]) > 1e-9}
        log('[P2] assignment: %d routes change height' % len(moved))
        batch, failures = LS.realise(state, assignment)
        log('[P3] realised %d routes (%d construction failures)'
            % (len(batch), len(failures)))
        if failures:
            for item in failures[:20]:
                domain[item['route_id']] = [z for z in domain[item['route_id']]
                                            if abs(z - item['z']) > 1e-9]
            cache_path.write_text(json.dumps({str(rid): values for rid, values
                                              in domain.items()}),
                                  encoding='utf-8')
            log('[P3] %d heights removed from domains, re-solving'
                % len(failures))
            continue
        evaluation = B.evaluate_batch(state, batch, window_check=False) \
            if batch else dict(ok=True, issues=[], violations=[],
                               crossings=[])
        log('[P3] batch: %d routes, %d hard issues, %d violations'
            % (len(batch), len(evaluation['issues']),
               len(evaluation['violations'])))
        # ---- greedy batch shrinking: drop the offenders, keep the legal core
        shrink_rounds = 0
        while not evaluation['ok'] and batch and shrink_rounds < 12:
            shrink_rounds += 1
            drop = set(LS.offending_routes(evaluation['issues']))
            drop &= set(batch)
            if not drop:
                break
            for rid in drop:
                batch.pop(rid, None)
            log('[P3] shrink %d: dropped %d offenders, %d routes left'
                % (shrink_rounds, len(drop), len(batch)))
            evaluation = B.evaluate_batch(state, batch, window_check=False) \
                if batch else dict(ok=True, issues=[], violations=[],
                                   crossings=[])
        log('[P3] after shrinking: %d routes, hard issues=%d, violations=%d'
            % (len(batch), len(evaluation['issues']),
               len(evaluation['violations'])))
        if not evaluation['ok']:
            kinds = Counter(issue['kind'] for issue in evaluation['issues'])
            log('[P3] hard issue kinds: %s' % dict(kinds))
            offenders = LS.offending_routes(evaluation['issues'])
            log('[P3] offending routes: %s' % offenders[:30])
            for issue in evaluation['issues'][:400]:
                pairs = []
                for key in ('route_a', 'route_b', 'rid', 'other'):
                    value = issue.get(key)
                    if value is not None and int(value) in assignment:
                        pairs.append(int(value))
                if len(pairs) >= 2:
                    a, b = pairs[0], pairs[1]
                    no_goods.append(((a, assignment[a]), (b, assignment[b])))
                elif len(pairs) == 1:
                    a = pairs[0]
                    z_hint = issue.get('z') if issue.get('kind', '').startswith(
                        '3d_') else None
                    other_z = None
                    if z_hint is not None:
                        other_z = round(float(z_hint), 9)
                    if other_z is None or abs(other_z - assignment[a]) < 1e-9:
                        domain[a] = [z for z in domain[a]
                                     if abs(z - assignment[a]) > 1e-9]
            cache_path.write_text(json.dumps({str(rid): values
                                              for rid, values
                                              in domain.items()}),
                                  encoding='utf-8')
            history.append(dict(round=round_index, phase='P3', ok=False,
                                moved=len(batch), issues=len(evaluation['issues']),
                                violations=len(state.violations),
                                kinds=dict(kinds)))
            continue
        committed_ids = set(batch)
        # acceptance guard: the batch must not raise the *global* violation count
        before = len(state.violations_touching(committed_ids))
        after = len(evaluation['violations'])
        global_after = len(state.violations) - before + after
        log('[P3] guard: %d -> %d violations touching the batch, global %d -> %d'
            % (before, after, len(state.violations), global_after))
        if global_after > len(state.violations):
            log('[P3] rejected: the batch would raise the global count')
            history.append(dict(round=round_index, phase='P3-guard',
                                ok=False, moved=len(batch),
                                violations=len(state.violations),
                                would_be=global_after))
            continue
        kept_out = [rid for rid in moved if rid not in committed_ids]
        for rid in kept_out:
            no_goods.append(((rid, assignment[rid]), (rid, assignment[rid])))
        info = B.commit_batch(state, batch, label='P3-round%d' % round_index)
        if not info['ok']:
            log('[P3] commit rejected: %s' % info['issues'][:3])
            history.append(dict(round=round_index, phase='P3-commit', ok=False,
                                moved=0, issues=len(info['issues']),
                                violations=len(state.violations)))
            continue
        for rid, z in moved.items():
            current[rid] = z
        history.append(dict(round=round_index, phase='P3', ok=True,
                            moved=len(batch), issues=0,
                            violations=len(state.violations),
                            crossings=len(state.crossings)))
        log('[P3] committed: %s' % state.summary())
        if len(state.violations) < best_violations:
            best_violations = len(state.violations)
            best_state = {rid: json.loads(json.dumps(state.world.routes[rid]))
                          for rid in nodes}
        (out / 'checkpoint_routes.json').write_text(
            json.dumps(dict(payload, routes=[state.world.routes[rid]
                                             for rid in nodes]),
                       ensure_ascii=False), encoding='utf-8')
        if not state.violations:
            break

    log('[P4] component batch improvement (%d violations)'
        % len(state.violations))
    comps = components(state)
    log('[P4] %d components, sizes %s'
        % (len(comps), sorted((len(c) for c in comps), reverse=True)[:10]))
    accepted = 0
    for comp in comps:
        if time.time() - started > args.time_limit:
            break
        current_v = len(state.violations_touching(comp))
        if not current_v:
            continue
        # candidate group assignments: permutations of the component's heights
        heights_here = [current[rid] for rid in comp if current.get(rid)]
        targets = [z for z in sorted(G5.all_heights())
                   if z not in heights_here][:6]
        proposals = []
        if len(comp) >= 2:
            proposals.append({comp[0]: current[comp[1]],
                              comp[1]: current[comp[0]]})
        for shift in (1, 2):
            rotated = {comp[i]: current[comp[(i + shift) % len(comp)]]
                       for i in range(len(comp))}
            proposals.append(rotated)
        for target in targets:
            proposals.append({comp[0]: target})
        # swap each component route with each of its conflict partners
        for rid in comp:
            partner_heights = {current[other] for other in adjacency.get(rid, ())
                               if current.get(other) is not None}
            for other in adjacency.get(rid, ()):
                if other in comp:
                    continue
                zo = current.get(other)
                if zo is None or abs(zo - (current.get(rid) or 0.0)) < 1e-9:
                    continue
                proposals.append({rid: zo, other: current[rid]})
        best = None
        for proposal in proposals:
            batch = {}
            ok = True
            for rid, z in proposal.items():
                if z is None or abs(z - (current[rid] or 0.0)) < 1e-9:
                    continue
                candidate = C.reheight_any(state.world.routes[rid], z)
                if candidate is None:
                    ok = False
                    break
                batch[rid] = candidate
            if not ok or not batch:
                continue
            evaluation = B.evaluate_batch(state, batch, window_check=False)
            if not evaluation['ok']:
                continue
            key = (len(evaluation['violations']),
                   sum(max(0.0, state.min_angle_deg - e['angle_deg'])
                       for e in evaluation['violations']))
            if key[0] < current_v and (best is None or key < best[0]):
                best = (key, proposal, batch)
        if best is None:
            continue
        info = B.commit_batch(state, best[2], label='P4-comp')
        if not info['ok']:
            continue
        for rid, z in best[1].items():
            current[rid] = z
        accepted += 1
        log('[P4] component %s accepted: %s' % (comp[:6], state.summary()))
        if len(state.violations) < best_violations:
            best_violations = len(state.violations)
            best_state = {rid: json.loads(json.dumps(state.world.routes[rid]))
                          for rid in nodes}
    log('[P4] accepted %d component batches' % accepted)

    final = state.summary()
    log('[done] %s' % final)
    (out / 'batch_relayer_result.json').write_text(
        json.dumps(dict(schema='g5_batch_relayer_v1', summary=final,
                        history=history, best_violations=best_violations,
                        moves=state.moves[-200:],
                        seconds=round(time.time() - started, 1)),
                   indent=1, ensure_ascii=False), encoding='utf-8')
    (out / 'routes_l3d.json').write_text(
        json.dumps(dict(payload, routes=[state.world.routes[rid]
                                         for rid in nodes]),
                   ensure_ascii=False), encoding='utf-8')
    (out / 'run.log').write_text('\n'.join(log_lines), encoding='utf-8')
    log('[write] %s' % out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
