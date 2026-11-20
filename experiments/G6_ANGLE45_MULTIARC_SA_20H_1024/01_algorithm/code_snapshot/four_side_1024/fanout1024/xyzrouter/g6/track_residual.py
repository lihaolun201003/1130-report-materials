# -*- coding: utf-8 -*-
"""Track the original G5 residual violations into the G6 geometry.

The 51 sub-45 crossings of the frozen G5 state are compared with the delivered
G6 geometry on three levels (the task explicitly allows the geometry to change,
so identity is by route pair *and* region, never by crossing id):

1. **pair level**   -- does the same unordered route pair still produce a sub-45
                       crossing on the same physical height?
2. **region level** -- is there any residual sub-45 crossing on the same height
                       within ``radius`` mm of the original crossing point?
3. **route level**  -- does either route still participate in any sub-45
                       crossing anywhere?

Also reports the 40 spatial clusters of the original residual set: a cluster is
``cleared`` iff no residual violation sits on the same height within ``radius``
of the cluster centre.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from collections import defaultdict


def load_events(path):
    rows = []
    with open(path, encoding='utf-8', newline='') as handle:
        for row in csv.DictReader(handle):
            if str(row.get('pass_45', 'True')).strip().lower() in \
                    ('false', '0', 'no'):
                try:
                    rows.append(dict(
                        z=float(row['z_mm']), x=float(row['x_mm']),
                        y=float(row['y_mm']),
                        angle=float(row['angle_deg']),
                        route_a=int(row['route_a']),
                        route_b=int(row['route_b']),
                        kind=f"{row.get('kind_a')}-{row.get('kind_b')}"))
                except (KeyError, TypeError, ValueError):
                    continue
    return rows


def load_all_events(path):
    rows = []
    with open(path, encoding='utf-8', newline='') as handle:
        for row in csv.DictReader(handle):
            try:
                rows.append(dict(
                    z=float(row['z_mm']), x=float(row['x_mm']),
                    y=float(row['y_mm']),
                    angle=float(row['angle_deg']),
                    route_a=int(row['route_a']),
                    route_b=int(row['route_b'])))
            except (KeyError, TypeError, ValueError):
                continue
    return rows


def clusters(events, cell=5.0):
    """Group residual events into <=cell mm spatial clusters per height."""
    buckets = defaultdict(list)
    for event in events:
        key = (round(event['z'], 6), int(event['x'] // cell),
               int(event['y'] // cell))
        buckets[key].append(event)
    merged = []
    keys = list(buckets)
    used = set()
    for index, key in enumerate(keys):
        if key in used:
            continue
        group = list(buckets[key])
        used.add(key)
        group_keys = {key}
        changed = True
        while changed:
            changed = False
            for other in keys:
                if other in used or other[0] != key[0]:
                    continue
                if any(abs(other[1] - member[1]) <= 1 and
                       abs(other[2] - member[2]) <= 1 for member in group_keys):
                    group.extend(buckets[other])
                    used.add(other)
                    group_keys.add(other)
                    changed = True
        merged.append(group)
    out = []
    for group in merged:
        xs = [event['x'] for event in group]
        ys = [event['y'] for event in group]
        routes = sorted({event['route_a'] for event in group} |
                        {event['route_b'] for event in group})
        out.append(dict(z=round(group[0]['z'], 6),
                        centre_x=round(sum(xs) / len(xs), 6),
                        centre_y=round(sum(ys) / len(ys), 6),
                        n=len(group), events=group, routes=routes))
    out.sort(key=lambda item: (item['z'], item['centre_x']))
    return out


def track(before_path, after_path, radius=20.0):
    before = load_events(before_path)
    after = load_all_events(after_path)
    after_bad = [event for event in after if event['angle'] < 45.0]
    after_pairs = defaultdict(list)
    for event in after:
        after_pairs[(min(event['route_a'], event['route_b']),
                     max(event['route_a'], event['route_b']),
                     round(event['z'], 6))].append(event)

    def near(event, candidates, limit):
        return [other for other in candidates
                if abs(other['z'] - event['z']) <= 1e-6 and
                math.hypot(other['x'] - event['x'],
                           other['y'] - event['y']) <= limit]

    pair_still = 0
    pair_cleared = 0
    region_still = 0
    region_cleared = 0
    details = []
    routes_before = set()
    for event in before:
        pair = (min(event['route_a'], event['route_b']),
                max(event['route_a'], event['route_b']),
                round(event['z'], 6))
        other = after_pairs.get(pair, [])
        worst = min((item['angle'] for item in other), default=None)
        pair_bad = worst is not None and worst < 45.0
        region = near(event, after_bad, radius)
        if pair_bad:
            pair_still += 1
        else:
            pair_cleared += 1
        if region:
            region_still += 1
        else:
            region_cleared += 1
        routes_before.add(event['route_a'])
        routes_before.add(event['route_b'])
        details.append(dict(
            route_a=event['route_a'], route_b=event['route_b'],
            z=event['z'], x=event['x'], y=event['y'], angle=event['angle'],
            kind=event['kind'], pair_still_bad=pair_bad,
            pair_min_angle_after=worst,
            region_still_bad=bool(region),
            region_hits=[dict(z=item['z'], x=item['x'], y=item['y'],
                              angle=round(item['angle'], 6))
                         for item in region[:3]]))
    before_clusters = clusters(before)
    cleared_clusters = 0
    cluster_details = []
    for cluster in before_clusters:
        hits = []
        for item in after_bad:
            if abs(item['z'] - cluster['z']) > 1e-6:
                continue
            if math.hypot(item['x'] - cluster['centre_x'],
                          item['y'] - cluster['centre_y']) <= radius:
                hits.append(item)
        cleared = not hits
        cleared_clusters += int(cleared)
        cluster_details.append(dict(
            z=cluster['z'], centre_x=cluster['centre_x'],
            centre_y=cluster['centre_y'], n=cluster['n'],
            routes=cluster['routes'], cleared=cleared,
            residual=len(hits)))
    routes_after_bad = set()
    for event in after_bad:
        routes_after_bad.add(event['route_a'])
        routes_after_bad.add(event['route_b'])
    still_routes = sorted(routes_before & routes_after_bad)
    return dict(
        schema='g6_residual_tracking_v1', radius_mm=radius,
        before_events=len(before), after_events=len(after),
        after_bad=len(after_bad),
        pair_level=dict(still_bad=pair_still, cleared=pair_cleared),
        region_level=dict(still_bad=region_still, cleared=region_cleared),
        before_routes=len(routes_before),
        after_bad_routes=len(routes_after_bad),
        routes_still_bad=len(still_routes), still_bad_route_ids=still_routes,
        clusters=dict(total=len(before_clusters),
                      cleared=cleared_clusters,
                      residual=len(before_clusters) - cleared_clusters,
                      details=cluster_details),
        before_clusters=cluster_details,
        events=details,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', required=True,
                        help='independent validator crossing CSV of G5 v5')
    parser.add_argument('--after', required=True,
                        help='independent validator crossing CSV of G6')
    parser.add_argument('--out', required=True)
    parser.add_argument('--radius', type=float, default=20.0)
    args = parser.parse_args(argv)
    report = track(args.before, args.after, radius=args.radius)
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, 'residual_tracking.json')
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(report, handle, indent=1, ensure_ascii=False)
    print(json.dumps({key: report[key] for key in
                      ('before_events', 'after_bad', 'pair_level',
                       'region_level', 'routes_still_bad', 'clusters')},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
