# -*- coding: utf-8 -*-
"""Audit one 1024-channel XYZ route state (geometry + planar multi-arc census).

Read-only: loads ``routes_l3d.json`` / ``assignment_1024.csv`` of one run dir,
recomputes the exact strict-D56 crossing count from scratch with the frozen
engine (``world_adapter.RouteWorld``), and counts the *planar multi-arc
regions* (tangent-continuous runs of >=2 opposite-sign R15 arcs with distinct
centres) per route / per physical height with the frozen policy helper
``layer2d.local_multi_arc_regions``.

Usage::

    python experiments/G4_MULTI_ARC_ABLATION_FINAL_1024/tools/audit_state.py \
        --run-dir <dir> --label start_3967 --out <dir>/audit_start_3967.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024 import layer2d as L2          # noqa: E402
from four_side_1024.fanout1024.nonc4 import crossings as X   # noqa: E402
from four_side_1024.fanout1024.xyzrouter import route_builder as RB  # noqa: E402
from four_side_1024.fanout1024.xyzrouter import world_adapter as WA  # noqa: E402
from four_side_1024.fanout1024.reheight21 import model as M  # noqa: E402


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def read_rows(path):
    with Path(path).open('r', encoding='utf-8-sig', newline='') as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def frozen_crossings(state):
    """Per-route crossing counts from the **frozen** same-plane audit.

    ``world_adapter.RouteWorld.per_route_counts`` goes through
    ``native3d.crossing_cache.CrossingCache``; that helper is what the search
    uses to seed its conflict graph, and on some states it does not agree with
    the frozen objective ``nonc4.crossings.audit_flat_group`` that the engine
    optimises and the Validator certifies.  The audit therefore re-derives the
    per-route counts from ``audit_flat_group`` itself -- the exact rule quoted in
    ``crossing_stats.json`` (``fslw strict D56 audit per physical z``).
    """
    per_route = Counter()
    events = []
    pairs = set()
    for z_key in sorted(state.plane_prims):
        prims = {rid: list(chain) for rid, chain in
                 state.plane_prims[z_key].items()}
        if not prims:
            continue
        result = X.audit_flat_group(prims)
        for event in result.get('crossings') or ():
            route_a = int(event['route_a'])
            route_b = int(event['route_b'])
            per_route[route_a] += 1
            per_route[route_b] += 1
            pairs.add((min(route_a, route_b), max(route_a, route_b)))
            events.append(dict(route_a=route_a, route_b=route_b,
                               z=float(z_key),
                               x=float(event.get('x') or event.get('x_mm') or 0.0),
                               y=float(event.get('y') or event.get('y_mm') or 0.0),
                               angle_deg=event.get('angle_deg')))
    return per_route, events, pairs


def multi_arc_census(state):
    """Per-route planar multi-arc regions (frozen policy definition)."""
    per_route = OrderedDict()
    per_height = Counter()
    routes_with = 0
    total_regions = 0
    total_arcs_in_regions = 0
    kinds = Counter()
    for rid in sorted(state.routes):
        groups = WA.route_flat_groups(state.routes[rid])
        regions = []
        for z_key in sorted(groups):
            for chain in groups[z_key]:
                for region in L2.local_multi_arc_regions(chain):
                    region = dict(region)
                    region['z'] = float(z_key)
                    regions.append(region)
                    per_height[round(float(z_key), 9)] += 1
                    kinds[str(region.get('kind'))] += 1
        if regions:
            routes_with += 1
            total_regions += len(regions)
            total_arcs_in_regions += sum(int(r['n_arcs']) for r in regions)
            per_route[int(rid)] = regions
    return dict(routes_with_multi_arc=int(routes_with),
                total_regions=int(total_regions),
                arcs_in_regions=int(total_arcs_in_regions),
                kinds=dict(kinds),
                per_height={('%.6f' % z): int(n)
                            for z, n in sorted(per_height.items())},
                per_route_with_multi_arc={str(rid): regions
                                          for rid, regions in per_route.items()})


def audit_run(run_dir, label='', per_route_csv=None, include_events=False):
    """Full census of one route state.  Returns a JSON-able summary dict."""
    run_dir = Path(run_dir)
    routes_path = run_dir / 'routes_l3d.json'
    rows_path = run_dir / 'assignment_1024.csv'
    payload = read_json(routes_path)
    rows = read_rows(rows_path)
    routes = payload['routes']

    messages = []
    state = WA.RouteWorld(routes, RB.normalized_rows(rows, stack=M.layer_stack()),
                          log=messages.append)
    per_route, events, pairs = frozen_crossings(state)
    crossings_total = len(events)
    census = multi_arc_census(state)

    kind_counts = Counter()
    flat_parts = 0
    trans_parts = 0
    families = Counter()
    for rid in state.routes:
        for part in state.routes[rid].get('parts') or ():
            if part.get('kind') == 'flat':
                flat_parts += 1
                for prim in part.get('primitives') or ():
                    kind_counts[str(prim.get('kind'))] += 1
                if part.get('tag') == 'body':
                    families[str(part.get('family') or '?')] += 1
            elif part.get('kind') == 'transition':
                trans_parts += 1

    counts = sorted(int(per_route.get(int(rid), 0)) for rid in state.routes)
    n = len(counts)
    p95 = counts[min(n - 1, int(round(0.95 * (n - 1))))] if n else 0

    plane_counts = {}
    for z, value in sorted(state.plane_counts.items()):
        plane_counts['%.6f' % float(z)] = dict(
            events=int(value[0]), pairs=int(value[1]),
            routes=len(state.plane_prims.get(z, {})))

    summary = dict(
        label=str(label), run_dir=str(run_dir),
        routes_sha256=sha256(routes_path),
        assignment_sha256=sha256(rows_path),
        schema=payload.get('schema'),
        algorithm=payload.get('algorithm'),
        note=str(payload.get('note') or '')[:200],
        route_count_declared=payload.get('route_count'),
        routed_declared=payload.get('routed'),
        failed_declared=payload.get('failed'),
        routes_loaded=len(state.routes),
        rows=len(rows),
        crossings=int(crossings_total),
        crossing_pairs=int(len(pairs)),
        state_total=int(state.total),
        state_total_matches_audit=bool(int(state.total) == crossings_total),
        routes_with_crossings=int(sum(1 for value in per_route.values() if value > 0)),
        max_route_crossings=int(max(per_route.values()) if per_route else 0),
        p95_route_crossings=int(p95),
        mean_route_crossings=round(float(sum(counts)) / max(1, n), 6),
        total_length_mm=round(float(state.total_length()), 6),
        mid_transitions=int(state.mid_transition_count()),
        flat_parts=int(flat_parts),
        transition_parts=int(trans_parts),
        flat_arcs=int(kind_counts.get('arc', 0)),
        flat_lines=int(kind_counts.get('line', 0)),
        multi_arc=census,
        plane_counts=plane_counts,
        per_route_crossings={str(rid): int(count)
                             for rid, count in sorted(per_route.items())},
        crossing_events=events if include_events else [],
    )

    if per_route_csv:
        out = Path(per_route_csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(['route_id', 'crossings', 'n_multi_arc_regions',
                             'n_multi_arc_arcs', 'length_mm', 'n_transitions',
                             'target_z_mm', 'body_heights'])
            for rid in sorted(state.routes):
                route = state.routes[rid]
                regions = census['per_route_with_multi_arc'].get(str(int(rid))) or []
                writer.writerow([
                    rid, int(per_route.get(rid, 0)), len(regions),
                    sum(int(r['n_arcs']) for r in regions),
                    '%.6f' % float(route.get('length_mm') or 0.0),
                    int(route.get('n_transitions') or 0),
                    '%.6f' % float(route.get('target_z_mm') or 0.0),
                    json.dumps(route.get('body_heights') or [])])
        summary['per_route_csv'] = str(out)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description='audit one route state')
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--label', default='')
    parser.add_argument('--out', default=None)
    parser.add_argument('--per-route-csv', default=None)
    args = parser.parse_args(argv)

    summary = audit_run(args.run_dir, label=args.label,
                        per_route_csv=args.per_route_csv)
    text = json.dumps(summary, ensure_ascii=False, indent=1)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding='utf-8')
    print(text[:4000])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
