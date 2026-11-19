# -*- coding: utf-8 -*-
"""Can the *current* XY geometry be re-layered into 20 conflict-free heights?

If a proper 20-colouring of the co-planarity conflict graph existed, then
re-assigning heights alone would give N_<45 = 0.  This measures how far the
graph is from being 20-colourable: greedy colour counts under several orders,
the largest colour class sizes, and the independent-set capacity needed
(1024 / 20 = 52 routes per height).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXP = ROOT / 'experiments' / 'G5_ANGLE45_NATIVE3D_20H_1024'


def greedy(order, adjacency):
    colour = {}
    for node in order:
        used = {colour[other] for other in adjacency[node] if other in colour}
        c = 0
        while c in used:
            c += 1
        colour[node] = c
    return colour


def dsatur(adjacency, nodes):
    colour = {}
    remaining = set(nodes)
    while remaining:
        best = None
        for node in remaining:
            saturation = len({colour[o] for o in adjacency[node] if o in colour})
            key = (saturation, len(adjacency[node]))
            if best is None or key > best[0]:
                best = (key, node)
        node = best[1]
        used = {colour[o] for o in adjacency[node] if o in colour}
        c = 0
        while c in used:
            c += 1
        colour[node] = c
        remaining.discard(node)
    return colour


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graph', default=str(EXP / '02_search_runs'
                                               / 'conflict_graph'
                                               / 'conflict_graph.json'))
    parser.add_argument('--k', type=int, default=20)
    args = parser.parse_args(argv)
    data = json.loads(Path(args.graph).read_text(encoding='utf-8'))
    edges = data['edges']
    nodes = sorted({e['route_a'] for e in edges} | {e['route_b'] for e in edges})
    adjacency = defaultdict(set)
    for edge in edges:
        adjacency[edge['route_a']].add(edge['route_b'])
        adjacency[edge['route_b']].add(edge['route_a'])
    for node in nodes:
        adjacency[node]
    degree = {node: len(adjacency[node]) for node in nodes}

    results = {}
    for name, order in (
            ('degree_desc', sorted(nodes, key=lambda n: -degree[n])),
            ('degree_asc', sorted(nodes, key=lambda n: degree[n])),
            ('route_id', nodes),
            ('degree_desc_rev', sorted(nodes, key=lambda n: -degree[n])[::-1])):
        colour = greedy(order, adjacency)
        counts = Counter(colour.values())
        results[name] = dict(colours=len(counts),
                             largest_class=max(counts.values()),
                             class_sizes=sorted(counts.values(), reverse=True)[:5])
    colour = dsatur(adjacency, nodes)
    counts = Counter(colour.values())
    results['dsatur'] = dict(colours=len(counts),
                             largest_class=max(counts.values()),
                             class_sizes=sorted(counts.values(), reverse=True)[:5])

    # independent-set capacity: how many routes can one height hold at most?
    # greedy independent set from the lowest-degree node gives a lower bound
    remaining = set(nodes)
    independent = []
    while remaining:
        node = min(remaining, key=lambda n: (sum(1 for o in adjacency[n]
                                                if o in remaining), n))
        independent.append(node)
        remaining.discard(node)
        remaining -= adjacency[node]
    summary = dict(
        schema='g5_layer_colouring_test_v1',
        routes=len(nodes), conflict_edges=len(edges),
        average_degree=round(2.0 * len(edges) / max(len(nodes), 1), 3),
        max_degree=max(degree.values()),
        colours_available=args.k, routes_per_height=round(len(nodes) / args.k, 2),
        greedy_independent_set_size=len(independent),
        greedy_independent_set_lower_bound=len(independent),
        colouring=results,
        verdict=('a 20-colouring of the current XY geometry is impossible'
                 if min(r['colours'] for r in results.values()) > args.k
                 else 'possible'))
    out = Path(args.graph).parent / 'colouring_test.json'
    out.write_text(json.dumps(summary, indent=1, ensure_ascii=False),
                   encoding='utf-8')
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
