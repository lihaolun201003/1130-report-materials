# -*- coding: utf-8 -*-
"""Experiment: restrict the CP-SAT layer assignment to *path-preserving* heights.

The co-planarity conflict graph is only valid for a route whose XY path does not
change, i.e. for the exact end-pose closure (``candidates.reheight``).  The
pose-to-pose body rebuild (``reheight_full``) changes the path, so the graph no
longer predicts the crossings it will have.

This script therefore

1. computes ``H_i^pp`` = the path-preserving heights only,
2. solves the minimum-conflict layer assignment on that restricted domain,
3. realises it, evaluates the whole change as one atomic batch, and compares the
   *realised* violation count with the graph prediction.

If the two agree, the assignment is sound and can be committed.
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


def path_preserving_domain(route, heights):
    rid = int(route['route_id'])
    body = C.body_part_indices(route)
    if not body:
        return [round(z, 9) for z in heights]
    current = round(float(route['parts'][body[0]]['z_mm']), 9)
    out = [current]
    for z in heights:
        if abs(z - current) < 1e-9:
            continue
        candidate = C.reheight(route, float(z))
        if candidate is None:
            continue
        if G5.structure_issues(candidate):
            continue
        out.append(round(z, 9))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--routes', default=str(EXP / '03_best_partial'
                                              / 'routes_l3d.json'))
    parser.add_argument('--graph', default=str(EXP / '02_search_runs'
                                             / 'conflict_graph'
                                             / 'conflict_graph.json'))
    parser.add_argument('--cp-time', type=float, default=240.0)
    parser.add_argument('--out', default=str(EXP / '02_search_runs'
                                             / 'pathpreserving'))
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    payload = json.loads(Path(args.routes).read_text(encoding='utf-8'))
    graph = json.loads(Path(args.graph).read_text(encoding='utf-8'))
    adjacency = defaultdict(set)
    for edge in graph['edges']:
        a, b = int(edge['route_a']), int(edge['route_b'])
        adjacency[a].add(b)
        adjacency[b].add(a)
    state = S.State(payload['routes'])
    heights = sorted(G5.all_heights())
    nodes = sorted(state.world.routes)
    domain = {}
    sizes = Counter()
    for rid in nodes:
        domain[rid] = path_preserving_domain(state.world.routes[rid], heights)
        sizes[len(domain[rid])] += 1
    print('[domain] |H_i| histogram: %s' % dict(sorted(sizes.items())),
          flush=True)
    print('[domain] routes with |H_i|=1 (pinned): %d'
          % sizes.get(1, 0), flush=True)
    current = {rid: domain[rid][0] for rid in nodes}
    assignment, status = LS.solve_cpsat(nodes, adjacency, domain, current, [],
                                        time_limit=args.cp_time, soft=True)
    if assignment is None:
        print('[cpsat] no assignment (%s)' % status)
        return 1
    batch, failures = LS.realise(state, assignment)
    print('[realise] %d routes, %d failures' % (len(batch), len(failures)),
          flush=True)
    evaluation = B.evaluate_batch(state, batch, window_check=False)
    before = len(state.violations_touching(batch.keys()))
    after = len(evaluation['violations'])
    global_after = len(state.violations) - before + after
    print('[result] batch routes=%d  hard issues=%d  violations %d -> %d '
          '(global %d -> %d)'
          % (len(batch), len(evaluation['issues']), before, after,
             len(state.violations), global_after), flush=True)
    kinds = Counter(issue['kind'] for issue in evaluation['issues'])
    print('[result] hard kinds: %s' % dict(kinds), flush=True)
    (out / 'pathpreserving_result.json').write_text(
        json.dumps(dict(batch=len(batch), failures=failures[:20],
                        hard_issues=len(evaluation['issues']),
                        kinds=dict(kinds),
                        violations_before=before,
                        violations_after=after,
                        global_before=len(state.violations),
                        global_after=global_after,
                        assignment={str(k): v for k, v in
                                    assignment.items()},
                        seconds=round(time.time() - started, 1)),
                   indent=1, ensure_ascii=False), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
