# -*- coding: utf-8 -*-
"""G7 analysis: per-layer statistics, attribution, residual-blocking probe.

Everything is computed with the same authoritative strict-D56 pair audit used by
the frozen validator, so the numbers in the report and the figures are
consistent with the acceptance verdicts.
"""
from __future__ import annotations

import json
import math
import os
import random
from collections import Counter, defaultdict

from ....fslw import validate_fslw as F
from . import frozen as FR


def _angles(payload):
    """Crossing records grouped by physical height (authoritative)."""
    groups = defaultdict(dict)
    for route in payload['routes']:
        for part in route.get('parts') or ():
            if part.get('kind') != 'flat':
                continue
            z = round(float(part['z_mm']), 9)
            prims = part.get('primitives') or []
            if prims:
                groups[z].setdefault(int(route['route_id']), []).extend(
                    dict(prim) for prim in prims)
    planes = {}
    for z, routes_here in groups.items():
        prepared = [F.prepare_route(prims, route_id=rid)
                    for rid, prims in routes_here.items()]
        audit = F.audit_route_pairs(prepared, clearance=0.08, sagitta=0.0005,
                                    policy='strict')
        crossings = []
        for crossing in audit.get('crossings') or ():
            crossings.append(dict(route_a=int(crossing['route_a']),
                                  route_b=int(crossing['route_b']),
                                  angle_deg=float(crossing['angle_deg']),
                                  x=float(crossing['x']), y=float(crossing['y']),
                                  z=z))
        planes[z] = dict(crossings=crossings,
                         violations=audit.get('violations') or [],
                         routes=len(routes_here),
                         parts=sum(len(prims) for prims in routes_here.values()),
                         min_angle=min((c['angle_deg'] for c in crossings),
                                       default=None))
    return planes


def plane_stats(payload, manifest=None):
    """Per-physical-height statistics (routes, crossings, pairs, min angle)."""
    planes = _angles(payload)
    rows = []
    route_entries = (manifest or {}).get('entries') or {}
    for z in sorted(planes):
        data = planes[z]
        crossings = data['crossings']
        pairs = {(min(c['route_a'], c['route_b']),
                  max(c['route_a'], c['route_b'])) for c in crossings}
        route_crossings = Counter()
        for crossing in crossings:
            route_crossings[crossing['route_a']] += 1
            route_crossings[crossing['route_b']] += 1
        top_routes = route_crossings.most_common(5)
        rows.append(dict(
            z_mm=round(z, 9),
            routes=data['routes'],
            crossings=len(crossings),
            unique_pairs=len(pairs),
            min_angle_deg=(round(data['min_angle'], 9)
                           if data['min_angle'] is not None else None),
            max_route_crossings=(top_routes[0][1] if top_routes else 0),
            top_routes=[dict(route_id=rid, crossings=count)
                        for rid, count in top_routes],
            violations=len(data['violations'])))
    return rows


def route_stats(payload, manifest=None):
    planes = _angles(payload)
    counts = Counter()
    for data in planes.values():
        for crossing in data['crossings']:
            counts[crossing['route_a']] += 1
            counts[crossing['route_b']] += 1
    entries = (manifest or {}).get('entries') or {}
    rows = []
    for rid, count in counts.most_common():
        kind = ''
        if str(rid) in entries:
            kind = entries[str(rid)]['kind']
        rows.append(dict(route_id=rid, crossings=count, kind=kind))
    return rows


def _load_json(path, default=None):
    try:
        with open(path, encoding='utf-8') as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def attribution(run_root, arms):
    """Move-kind contribution from the SA improvement histories."""
    summary = []
    for arm, run_dir in arms.items():
        seeds = []
        if not os.path.isdir(run_dir):
            continue
        for name in sorted(os.listdir(run_dir)):
            path = os.path.join(run_dir, name)
            if not name.startswith('seed_'):
                continue
            history_path = os.path.join(path, 'logs', 'history.jsonl')
            moves = Counter()
            deltas = Counter()
            if os.path.exists(history_path):
                with open(history_path, encoding='utf-8') as handle:
                    for line in handle:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if record.get('event') != 'improve':
                            continue
                        kind = str(record.get('move_kind') or '?')
                        moves[kind] += 1
                        deltas[kind] += int(record.get('delta') or 0)
            seeds.append(dict(seed=name, improve_moves=dict(moves),
                              delta=dict(deltas)))
        summary.append(dict(arm=arm, seeds=seeds))
    return summary


def residual_probe(payload, reference_payload, manifest, top_n=30,
                   candidates_per_route=120, seed=20261120):
    """Why do the residual crossings remain? (search-side blocking analysis)

    For the hottest residual crossings, test whether re-generating the body of
    either endpoint route (fixed height, fixed transitions) can remove the
    crossing under the full frozen contract.  A crossing is ``blocked`` when no
    candidate of either endpoint reduces the total crossing count; ``fixable``
    otherwise.  This is evidence about the remaining search head-room, **not** a
    mathematical lower bound.
    """
    from . import engine as EN
    from . import sa as SA

    rng = random.Random(seed)
    state = SA.G7SA(payload, manifest, os.path.join(
        os.path.dirname(os.path.abspath(__file__)), '_probe_tmp'),
        cfg=dict(SA.DEFAULT_CFG), log=lambda *args, **kwargs: None)
    planes = state.pw.plane_events
    # hottest crossings: count per route pair by number of events
    pair_counts = Counter()
    example = {}
    for z, events in planes.items():
        for key, event in events.items():
            pair = key[0]
            pair_counts[pair] += 1
            example.setdefault(pair, dict(z=z, x=event['x'], y=event['y'],
                                          angle=event['angle_deg']))
    results = []
    for (rid_a, rid_b), count in pair_counts.most_common(top_n):
        info = example[(rid_a, rid_b)]
        entry = dict(route_a=rid_a, route_b=rid_b,
                     crossings_in_pair=count, z=info['z'],
                     x=info['x'], y=info['y'], angle_deg=info['angle'],
                     modifiable=[rid for rid in (rid_a, rid_b)
                                 if rid in state.movable_set])
        fixable = []
        for rid in entry['modifiable']:
            pool = state.pool.candidates(rid, int(candidates_per_route))
            best = None
            for candidate in pool:
                result = state.pw.evaluate_candidate(rid, candidate['prims'])
                if not result['ok']:
                    continue
                if (result['min_angle'] is not None
                        and result['min_angle'] < SA.THETA):
                    continue
                delta = result['delta']
                if delta < 0 and (best is None or delta < best):
                    best = delta
            if best is not None:
                fixable.append(dict(route_id=rid, best_delta=best))
        entry['fixable'] = fixable
        entry['blocked'] = not fixable
        results.append(entry)
    state.close()
    return dict(schema='g7_residual_probe_v1',
                top=len(results),
                fixable=sum(1 for row in results if not row['blocked']),
                blocked=sum(1 for row in results if row['blocked']),
                rows=results)


def build_analysis(before_path, after_path, run_root, arms, out_dir,
                   reference_path=None, top_n=30):
    os.makedirs(out_dir, exist_ok=True)
    before = _load_json(before_path)
    after = _load_json(after_path)
    reference = _load_json(reference_path) if reference_path else before
    manifest = FR.build_manifest(reference['routes'])
    before_planes = plane_stats(before, manifest)
    after_planes = plane_stats(after, manifest)
    before_routes = route_stats(before, manifest)
    after_routes = route_stats(after, manifest)
    data = dict(
        schema='g7_analysis_v1',
        before=dict(path=os.path.abspath(before_path),
                    crossings=sum(row['crossings'] for row in before_planes),
                    unique_pairs=len({(min(c['route_a'], c['route_b']),
                                       max(c['route_a'], c['route_b']))
                                      for plane in _angles(before).values()
                                      for c in plane['crossings']}),
                    length_mm=round(sum(float(part.get('length_mm') or 0.0)
                                        for route in before['routes']
                                        for part in route.get('parts') or ()), 6),
                    planes=before_planes, routes=before_routes[:60]),
        after=dict(path=os.path.abspath(after_path),
                   crossings=sum(row['crossings'] for row in after_planes),
                   unique_pairs=len({(min(c['route_a'], c['route_b']),
                                      max(c['route_a'], c['route_b']))
                                     for plane in _angles(after).values()
                                     for c in plane['crossings']}),
                   length_mm=round(sum(float(part.get('length_mm') or 0.0)
                                       for route in after['routes']
                                       for part in route.get('parts') or ()), 6),
                   planes=after_planes, routes=after_routes[:60]),
        attribution=attribution(run_root, arms),
    )
    probe = residual_probe(after, reference, manifest, top_n=top_n)
    data['residual_probe'] = probe
    path = os.path.join(out_dir, 'g7_analysis.json')
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(data, handle, indent=1, ensure_ascii=False)
    # CSV of per-layer comparison
    csv_path = os.path.join(out_dir, 'g7_per_layer.csv')
    with open(csv_path, 'w', encoding='utf-8', newline='') as handle:
        import csv
        writer = csv.writer(handle)
        writer.writerow(['z_mm', 'routes', 'crossings_before',
                         'crossings_after', 'delta', 'pairs_before',
                         'pairs_after', 'min_angle_before', 'min_angle_after'])
        by_z_before = {row['z_mm']: row for row in before_planes}
        for row in after_planes:
            z = row['z_mm']
            old = by_z_before.get(z, {})
            writer.writerow([z, row['routes'],
                             old.get('crossings', 0), row['crossings'],
                             row['crossings'] - old.get('crossings', 0),
                             old.get('unique_pairs', 0), row['unique_pairs'],
                             old.get('min_angle_deg'), row['min_angle_deg']])
    data['per_layer_csv'] = csv_path
    return data
