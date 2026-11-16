# -*- coding: utf-8 -*-
"""Audit the *real* flat (in-plane) multi-arc usage of a 1024-route L3D solution.

The 3D solution stores, per route, a list of ``parts``:

* ``kind='flat'``  -> an in-plane chain at one physical height ``z_mm`` whose
  ``primitives`` are ``line`` / ``arc`` (R15).  This is the only place where a
  *planar* multi-arc combination can exist.
* ``kind='transition'`` -> the frozen two-arc R15 S transition that changes the
  physical height.  Its two arcs are **3D** geometry and are deliberately *not*
  part of this audit (the ablation must never touch them).

Classification of a maximal run of consecutive tangent-continuous arcs:

``same_circle_split``
    >=2 arcs with the same centre (and therefore the same sign) that only
    store one continuous circular piece in several records.  NOT a geometric
    degree of freedom (explicitly excluded by the task definition).
``s_pair``
    exactly 2 arcs with opposite sweep signs and different centres: the frozen
    ``short-S`` lateral shift.  THIS is the real planar multi-arc primitive.
``multi_arc``
    runs of >=2 arcs with opposite signs (including 2-arc ``s_pair``) -- i.e.
    a local region that combines several arcs to obtain a lateral offset.
``same_sign_multi``
    >=2 arcs, same sign, different centres: cannot happen for equal-radius
    tangent arcs; reported to prove the classifier is exhaustive.

Usage::

    python audit_flat_multi_arc.py <run_dir> [<run_dir> ...] --out <dir>
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

TOL = 1e-7


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _tangent_start(prim):
    if prim['kind'] == 'line':
        dx = prim['p1'][0] - prim['p0'][0]
        dy = prim['p1'][1] - prim['p0'][1]
        norm = math.hypot(dx, dy)
        return (dx / norm, dy / norm)
    sign = 1.0 if float(prim['sweep']) >= 0 else -1.0
    angle = float(prim['start_angle'])
    return (-sign * math.sin(angle), sign * math.cos(angle))


def _tangent_end(prim):
    if prim['kind'] == 'line':
        dx = prim['p1'][0] - prim['p0'][0]
        dy = prim['p1'][1] - prim['p0'][1]
        norm = math.hypot(dx, dy)
        return (dx / norm, dy / norm)
    sign = 1.0 if float(prim['sweep']) >= 0 else -1.0
    angle = float(prim['start_angle']) + float(prim['sweep'])
    return (-sign * math.sin(angle), sign * math.cos(angle))


def _connected(left, right):
    if abs(left['p1'][0] - right['p0'][0]) > 1e-6:
        return False
    if abs(left['p1'][1] - right['p0'][1]) > 1e-6:
        return False
    t0 = _tangent_end(left)
    t1 = _tangent_start(right)
    return abs(t0[0] - t1[0]) <= 1e-6 and abs(t0[1] - t1[1]) <= 1e-6


def _centre(prim):
    return (float(prim['center'][0]), float(prim['center'][1]))


def classify_chain(prims):
    """Return ``(arc_runs, totals)`` of one flat chain."""
    runs = []
    index = 0
    total = len(prims)
    while index < total:
        prim = prims[index]
        if prim['kind'] != 'arc':
            index += 1
            continue
        run = [prim]
        cursor = index
        while cursor + 1 < total and prims[cursor + 1]['kind'] == 'arc':
            if not _connected(prims[cursor], prims[cursor + 1]):
                break
            run.append(prims[cursor + 1])
            cursor += 1
        index = cursor + 1
        signs = [1 if float(p['sweep']) >= 0 else -1 for p in run]
        centres = [_centre(p) for p in run]
        same_centre = all(
            abs(c[0] - centres[0][0]) <= 1e-6 and abs(c[1] - centres[0][1]) <= 1e-6
            for c in centres)
        if len(run) == 1:
            kind = 'single_arc'
        elif same_centre:
            kind = 'same_circle_split'
        elif len(set(signs)) > 1:
            kind = 'multi_arc' if len(run) > 2 else 's_pair'
        else:
            kind = 'same_sign_multi'
        runs.append(dict(kind=kind, n_arcs=len(run), signs=signs,
                         start=list(run[0]['p0']), end=list(run[-1]['p1']),
                         radius=float(run[0]['radius']),
                         sweep_total_rad=sum(abs(float(p['sweep'])) for p in run)))
    totals = dict(flat_arcs=sum(1 for p in prims if p['kind'] == 'arc'),
                  flat_lines=sum(1 for p in prims if p['kind'] == 'line'),
                  runs=len(runs),
                  single_arc=sum(1 for r in runs if r['kind'] == 'single_arc'),
                  s_pair=sum(1 for r in runs if r['kind'] == 's_pair'),
                  multi_arc=sum(1 for r in runs if r['kind'] == 'multi_arc'),
                  same_circle_split=sum(1 for r in runs
                                        if r['kind'] == 'same_circle_split'),
                  same_sign_multi=sum(1 for r in runs
                                      if r['kind'] == 'same_sign_multi'))
    # number of *arcs* that belong to a real planar multi-arc region
    totals['multi_arc_arcs'] = sum(r['n_arcs'] for r in runs
                                   if r['kind'] in ('s_pair', 'multi_arc'))
    return runs, totals


def audit_run(run_dir):
    run_dir = Path(run_dir)
    payload = json.loads((run_dir / 'routes_l3d.json').read_text(encoding='utf-8'))
    routes = payload['routes']
    per_route = {}
    per_height = defaultdict(lambda: Counter())
    per_height_routes = defaultdict(set)
    total = Counter()
    families = Counter()
    transitions = Counter()
    total_length = 0.0
    routed = 0
    for route in routes:
        rid = int(route['route_id'])
        chain_totals = Counter()
        route_runs = []
        for part in route.get('parts') or ():
            if part.get('kind') == 'transition':
                transitions['transition_parts'] += 1
                transitions['transition_length_mm'] += float(part.get('length_mm') or 0.0)
                continue
            if part.get('kind') != 'flat':
                continue
            prims = part.get('primitives') or []
            runs, totals = classify_chain(prims)
            z = round(float(part['z_mm']), 9)
            for key, value in totals.items():
                chain_totals[key] += value
            per_height[z]['flat_arcs'] += totals['flat_arcs']
            per_height[z]['flat_lines'] += totals['flat_lines']
            per_height[z]['s_pair'] += totals['s_pair']
            per_height[z]['multi_arc'] += totals['multi_arc']
            per_height[z]['multi_arc_arcs'] += totals['multi_arc_arcs']
            per_height[z]['same_circle_split'] += totals['same_circle_split']
            if totals['s_pair'] or totals['multi_arc']:
                per_height_routes[z].add(rid)
                per_height[z]['routes_with_multi_arc'] += 0
            for run in runs:
                if run['kind'] in ('s_pair', 'multi_arc'):
                    families[run['kind']] += 1
                    route_runs.append(dict(z_mm=float(part['z_mm']),
                                           kind=run['kind'],
                                           n_arcs=run['n_arcs'],
                                           start=run['start'], end=run['end'],
                                           sweep_total_rad=run['sweep_total_rad']))
        total.update(chain_totals)
        total_length += float(route.get('length_mm') or 0.0)
        if route.get('parts'):
            routed += 1
        per_route[rid] = dict(
            parts=len(route.get('parts') or []),
            n_transitions=int(route.get('n_transitions') or 0),
            flat_arcs=chain_totals['flat_arcs'],
            s_pair=chain_totals['s_pair'],
            multi_arc=chain_totals['multi_arc'],
            multi_arc_arcs=chain_totals['multi_arc_arcs'],
            same_circle_split=chain_totals['same_circle_split'],
            has_flat_multi_arc=bool(chain_totals['s_pair'] or chain_totals['multi_arc']),
            length_mm=float(route.get('length_mm') or 0.0),
            regions=route_runs,
        )
    stats = dict(
        run_dir=str(run_dir),
        routes=len(routes), routed=routed,
        routes_with_flat_multi_arc=sum(1 for r in per_route.values()
                                       if r['has_flat_multi_arc']),
        flat_arcs=total['flat_arcs'],
        flat_lines=total['flat_lines'],
        arc_runs=total['runs'],
        single_arc=total['single_arc'],
        s_pair=total['s_pair'],
        multi_arc=total['multi_arc'],
        multi_arc_arcs=total['multi_arc_arcs'],
        same_circle_split=total['same_circle_split'],
        same_sign_multi=total['same_sign_multi'],
        transition_parts=transitions['transition_parts'],
        transition_length_mm=round(transitions['transition_length_mm'], 6),
        total_length_mm=round(total_length, 6),
        per_route_s_max=max((r['s_pair'] + r['multi_arc']
                             for r in per_route.values()), default=0),
        routes_sha256=_sha256(run_dir / 'routes_l3d.json'),
    )
    heights = []
    for z in sorted(per_height):
        row = dict(per_height[z])
        row['z_mm'] = z
        row['routes_with_multi_arc'] = len(per_height_routes[z])
        heights.append(row)
    return dict(stats=stats, per_route=per_route, per_height=heights,
                families=dict(families))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('run_dirs', nargs='+')
    parser.add_argument('--out', required=True)
    parser.add_argument('--label', default=None)
    args = parser.parse_args(argv)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    labels = (args.label or '').split(',') if args.label else []
    summary = {}
    for index, run_dir in enumerate(args.run_dirs):
        result = audit_run(run_dir)
        label = labels[index] if index < len(labels) and labels[index] else Path(run_dir).name
        summary[label] = result['stats']
        (out_dir / ('flat_multi_arc_%s.json' % label)).write_text(
            json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
        rows = []
        for rid, row in sorted(result['per_route'].items()):
            flat = dict(row)
            regions = flat.pop('regions')
            flat['route_id'] = rid
            flat['n_regions'] = len(regions)
            flat['regions'] = json.dumps(regions, ensure_ascii=False)
            rows.append(flat)
        fieldnames = ['route_id', 'parts', 'n_transitions', 'flat_arcs',
                      's_pair', 'multi_arc', 'multi_arc_arcs',
                      'same_circle_split', 'has_flat_multi_arc', 'n_regions',
                      'length_mm', 'regions']
        with (out_dir / ('flat_multi_arc_per_route_%s.csv' % label)).open(
                'w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames,
                                    extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)
        with (out_dir / ('flat_multi_arc_per_height_%s.csv' % label)).open(
                'w', encoding='utf-8', newline='') as handle:
            fields = ['z_mm', 'routes_with_multi_arc', 'flat_arcs', 's_pair',
                      'multi_arc', 'multi_arc_arcs', 'same_circle_split',
                      'flat_lines']
            writer = csv.DictWriter(handle, fieldnames=fields,
                                    extrasaction='ignore')
            writer.writeheader()
            writer.writerows(result['per_height'])
        print(json.dumps(dict(label=label, **result['stats']),
                         ensure_ascii=False, indent=1))
    (out_dir / 'flat_multi_arc_summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
