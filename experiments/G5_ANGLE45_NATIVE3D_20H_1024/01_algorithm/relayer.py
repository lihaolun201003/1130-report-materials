# -*- coding: utf-8 -*-
"""Re-layer the 1024 routes so that no height carries a sub-45 deg crossing.

Why this can work
-----------------
A route's XY path does not depend on the physical height it is routed at, so
"may routes i and j share one height?" is a single boolean, independent of which
height (``build_conflict_graph.py`` measures it).  That graph turns out to be
19-colourable although 20 heights are available, so a height assignment exists
in which *no* height contains a shallow crossing.

What this solver adds on top of pure graph colouring is the part graph colouring
ignores: the R15 S-curves that lift a route from its interface row to its body
height must still keep 50 um of true 3-D clearance from everything else, and the
body must satisfy strict D56 on its new height.  So the assignment is done in
DSATUR order, and every candidate height is *exactly evaluated* (structure, D56,
3-D) before it is accepted.  Heights are tried nearest-first so the layout stays
close to the G4/G5 geometry (fewer transitions move).

Output: a full payload plus a per-route assignment log; a full audit follows.
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

EXP = ROOT / 'experiments' / 'G5_ANGLE45_NATIVE3D_20H_1024'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--routes', default=str(
        EXP / '03_best_partial' / 'routes_l3d.json'))
    parser.add_argument('--graph', default=str(
        EXP / '02_search_runs' / 'conflict_graph' / 'conflict_graph.json'))
    parser.add_argument('--out', default=str(EXP / '02_search_runs' / 'relayer'))
    parser.add_argument('--seed', type=int, default=20261116)
    parser.add_argument('--time-limit', type=float, default=5400.0)
    parser.add_argument('--keep', action='store_true',
                        help='prefer the current height of every route')
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()

    payload = json.loads(Path(args.routes).read_text(encoding='utf-8'))
    graph = json.loads(Path(args.graph).read_text(encoding='utf-8'))
    conflict = defaultdict(set)
    for edge in graph['edges']:
        conflict[edge['route_a']].add(edge['route_b'])
        conflict[edge['route_b']].add(edge['route_a'])
    state = S.State(payload['routes'])
    routes = {int(r['route_id']): r for r in payload['routes']}
    print('[start] %s' % state.summary(), flush=True)

    heights = sorted(G5.all_heights())
    current = {}
    for rid, route in routes.items():
        body = C.body_part_indices(route)
        current[rid] = (round(float(route['parts'][body[0]]['z_mm']), 9)
                        if body else None)
    degree = {rid: len(conflict[rid]) for rid in routes}
    order = sorted(routes, key=lambda r: (-degree[r], -len(state.route_violations(r)), r))
    assigned = {}
    failures = []
    moves = 0
    log_rows = []

    def height_ok(rid, z, route):
        """Neighbourhood check against the already-assigned routes."""
        for other, other_z in assigned.items():
            if other == rid:
                continue
            if abs(other_z - z) < 1e-9 and other in conflict[rid]:
                return 'graph'
        return None

    for index, rid in enumerate(order):
        if time.time() - started > args.time_limit:
            print('[stop] time limit at %d/%d' % (index, len(order)), flush=True)
            break
        route = state.world.routes[rid]
        need = len(state.route_violations(rid))
        current_violations = need
        preferred = []
        if args.keep and current[rid] is not None:
            preferred.append(current[rid])
        preferred.extend(sorted(heights,
                                key=lambda z: abs(z - (current[rid] or 0.0))))
        chosen = None
        tried = 0
        best = (current_violations, 10 ** 6, abs(z_here := 0.0))
        for z in preferred:
            if height_ok(rid, z, route):
                continue
            new_route = C.reheight_any(route, z) if z != current[rid] else route
            if new_route is None:
                continue
            tried += 1
            evaluation = state.evaluate(rid, new_route)
            if not evaluation['ok']:
                continue
            count = len(evaluation['violations'])
            key = (count, 0 if count == 0 else 1,
                   abs(z - (current[rid] or 0.0)))
            if count == 0:
                chosen = (z, new_route)
                break
            if key < (best[0], best[1], best[2]):
                best = key
                chosen = (z, new_route)
        if chosen is None:
            failures.append(dict(route_id=rid, current=current[rid],
                                 tried=tried, violations=need))
            assigned[rid] = current[rid]
            continue
        z, new_route = chosen
        if abs(z - (current[rid] or 0.0)) > 1e-9:
            state.world.set_route(rid, new_route)
            state.refresh()
            moves += 1
        assigned[rid] = z
        log_rows.append(dict(route_id=rid, old=current[rid], new=z,
                             moved=abs(z - (current[rid] or 0.0)) > 1e-9))
        if (index + 1) % 25 == 0:
            print('[%d/%d] moved=%d failed=%d violations=%d (%.0fs)'
                  % (index + 1, len(order), moves, len(failures),
                     len(state.violations), time.time() - started), flush=True)
            (out / 'checkpoint_routes.json').write_text(
                json.dumps(dict(payload, routes=[state.world.routes[r]
                                                 for r in sorted(routes)]),
                           ensure_ascii=False), encoding='utf-8')

    final = state.summary()
    print('[done] %s' % final, flush=True)
    print('[moves] %d routes changed height, %d failed to place'
          % (moves, len(failures)), flush=True)
    result = dict(schema='g5_relayer_v1', summary=final, moves=moves,
                  failures=failures, assignment=log_rows,
                  seconds=round(time.time() - started, 1),
                  conflicts_edges=len(graph['edges']))
    (out / 'relayer_result.json').write_text(
        json.dumps(result, indent=1, ensure_ascii=False), encoding='utf-8')
    (out / 'routes_l3d.json').write_text(
        json.dumps(dict(payload, routes=[state.world.routes[r]
                                         for r in sorted(routes)]),
                   ensure_ascii=False), encoding='utf-8')
    print('[write] %s/routes_l3d.json' % out, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
