# -*- coding: utf-8 -*-
"""Build the *co-planarity* conflict graph of the 1024 routes.

A route's XY path does not depend on the physical height it is routed at, so for
every pair of routes the question "may these two share one height?" is a single
boolean, independent of which height:

    conflict(i, j)  <=>  the two XY paths, if laid on the same height, would
                         produce a crossing below 45 deg, or an overlap /
                         a sub-0.08 mm approach without a legal crossing.

If that graph is 20-colourable, *any* proper colouring assigns heights such that
no height contains a sub-45 deg crossing, i.e. N_<45 = 0 by construction.  This
script measures the graph and the colouring headroom.
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

EXP = ROOT / 'experiments' / 'G5_ANGLE45_NATIVE3D_20H_1024'


def merged_chain(route):
    """All flat primitives of a route in path order, z ignored."""
    curves = []
    for part in route.get('parts') or ():
        if part.get('kind') != 'flat':
            continue
        for prim in part.get('primitives') or ():
            curve = G5.make_prim(prim)
            curve['length'] = G5.IM.prim_length(curve)
            curve['z'] = 0.0
            curve['route_id'] = int(route['route_id'])
            curves.append(curve)
    offsets = []
    cursor = 0.0
    for curve in curves:
        offsets.append(cursor)
        cursor += curve['length']
    return dict(curves=curves, offsets=offsets, total=cursor)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--routes', default=str(
        EXP / '03_best_partial' / 'routes_l3d.json'))
    parser.add_argument('--theta', type=float, default=45.0)
    parser.add_argument('--out', default=str(EXP / '02_search_runs'
                                             / 'conflict_graph'))
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    payload = json.loads(Path(args.routes).read_text(encoding='utf-8'))
    routes = payload['routes']
    started = time.time()
    chains = {int(r['route_id']): merged_chain(r) for r in routes}
    print('[chains] %d routes, %d curves (%.1fs)'
          % (len(chains), sum(len(c['curves']) for c in chains.values()),
             time.time() - started), flush=True)

    # spatial grid over every curve, z ignored
    grid = defaultdict(list)
    for rid, chain in chains.items():
        for index, curve in enumerate(chain['curves']):
            box = curve['bbox']
            x0 = int((box[0] - G5.GRID_PAD_MM) // G5.GRID_CELL_MM)
            x1 = int((box[2] + G5.GRID_PAD_MM) // G5.GRID_CELL_MM)
            y0 = int((box[1] - G5.GRID_PAD_MM) // G5.GRID_CELL_MM)
            y1 = int((box[3] + G5.GRID_PAD_MM) // G5.GRID_CELL_MM)
            for ix in range(x0, x1 + 1):
                for iy in range(y0, y1 + 1):
                    grid[(ix, iy)].append((rid, index))
    candidates = set()
    for entries in grid.values():
        if len(entries) < 2:
            continue
        ids = sorted({rid for rid, _index in entries})
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                candidates.add((ids[i], ids[j]))
    print('[grid] %d cells, %d candidate route pairs (%.1fs)'
          % (len(grid), len(candidates), time.time() - started), flush=True)

    conflicts = {}
    stats = Counter()
    for (ra, rb) in sorted(candidates):
        result = G5.pair_audit(chains[ra], chains[rb], 0.0, args.theta,
                               crossing_window_check=False)
        shallow = [c for c in result['crossings']
                   if c['angle_deg'] < args.theta]
        hard = result['issues']
        if shallow or hard:
            reason = 'shallow' if shallow else hard[0]['kind']
            conflicts[(ra, rb)] = dict(
                reason=reason,
                count=len(shallow),
                min_angle=(round(min(c['angle_deg'] for c in shallow), 6)
                           if shallow else None),
                hard=[i['kind'] for i in hard])
            stats[reason] += 1
        else:
            stats['compatible'] += 1
    print('[conflicts] %d conflicting pairs out of %d candidates (%.1fs)'
          % (len(conflicts), len(candidates), time.time() - started), flush=True)

    degree = Counter()
    adjacency = defaultdict(set)
    for (ra, rb) in conflicts:
        adjacency[ra].add(rb)
        adjacency[rb].add(ra)
        degree[ra] += 1
        degree[rb] += 1
    values = sorted(degree.values(), reverse=True)
    summary = dict(
        schema='g5_coplanarity_conflict_graph_v1', theta_min_deg=args.theta,
        routes=len(chains), candidate_pairs=len(candidates),
        conflict_pairs=len(conflicts), reasons=dict(stats),
        routes_with_conflicts=len(adjacency),
        max_degree=(values[0] if values else 0),
        degree_histogram=dict(sorted(Counter(degree.values()).items())),
        top_degree=[dict(route_id=rid, degree=deg)
                    for rid, deg in degree.most_common(20)],
        seconds=round(time.time() - started, 1))
    (out / 'conflict_graph.json').write_text(
        json.dumps(dict(summary=summary,
                        edges=[dict(route_a=a, route_b=b, **info)
                               for (a, b), info in sorted(conflicts.items())]),
                   indent=1, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
