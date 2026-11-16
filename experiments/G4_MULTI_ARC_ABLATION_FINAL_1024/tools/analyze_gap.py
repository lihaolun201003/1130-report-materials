# -*- coding: utf-8 -*-
"""Why does the strict ON arm stop at ~2200 instead of the historical 1185?

This script answers that question with measurements, not with a story.  It
compares four states that all share the same 1024 connections:

* ``G3_start_1322``      -- the historical best state (1322 crossings)
* ``start_common_3967``  -- the same state after the Stage-0 multi-arc ablation
* ``ON final``           -- the strict common-start arm with multi-arc allowed
* ``OFF final``          -- the strict common-start arm with multi-arc banned

and decomposes the crossing burden into the **197 routes that Stage-0 had to
rebuild** and the **other 827 routes**, then checks how much of the
G3 configuration the ON search actually reconstructed.

Outputs ``tables/gap_analysis.json`` + a console table.

Usage::

    python .../tools/analyze_gap.py --tag c1_20261104
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics as st
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
R15 = 15.0


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def read_csv(path):
    with Path(path).open('r', encoding='utf-8') as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def per_route(audit):
    return {int(k): int(v) for k, v in audit['per_route_crossings'].items()}


def block(counts, ids):
    values = [counts.get(rid, 0) for rid in ids]
    return dict(routes=len(ids), sum=int(sum(values)),
                mean=round(float(st.mean(values)), 4) if values else None,
                median=(round(float(st.median(values)), 4) if values else None),
                max=(int(max(values)) if values else None),
                with_crossings=int(sum(1 for v in values if v > 0)))


def route_geometry(route):
    """Comparable geometry fingerprint: (target_z, [primitive signature...])."""
    parts = []
    for part in route.get('parts') or ():
        if part.get('kind') == 'flat':
            for prim in part.get('primitives') or ():
                if prim.get('kind') == 'line':
                    parts.append(('L', round(float(prim['p0'][0]), 4),
                                  round(float(prim['p0'][1]), 4),
                                  round(float(prim['p1'][0]), 4),
                                  round(float(prim['p1'][1]), 4)))
                else:
                    parts.append(('A', round(float(prim['center'][0]), 4),
                                  round(float(prim['center'][1]), 4),
                                  round(float(prim['start_angle']), 6),
                                  round(float(prim['sweep']), 6)))
        elif part.get('kind') == 'transition':
            parts.append(('T', round(float(part.get('z0') or 0), 4),
                          round(float(part.get('z1') or 0), 4)))
    return (round(float(route.get('target_z_mm') or 0.0), 6), tuple(parts))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tables', default=str(EXP / 'tables'))
    parser.add_argument('--audit', default=str(EXP / 'audit'))
    parser.add_argument('--runs', default=str(EXP / 'runs'))
    parser.add_argument('--seed', default='20261104')
    args = parser.parse_args(argv)
    tables = Path(args.tables)
    audit = Path(args.audit)
    runs = Path(args.runs)
    on_tag = 'c1_on_%s' % args.seed
    off_tag = 'c1_off_%s' % args.seed

    g3 = read_json(audit / 'G3_start_1322.json')
    start = read_json(audit / 'start_common_3967.json')
    on = read_json(tables / 'audit' / ('on_%s.json' % on_tag))
    off = read_json(tables / 'audit' / ('off_%s.json' % off_tag))
    converted = sorted(int(row['route_id'])
                       for row in read_csv(tables / 'stage0_per_route.csv'))
    cset = set(converted)

    g3p, sp, onp, offp = (per_route(x) for x in (g3, start, on, off))
    all_ids = sorted(set(g3p) | set(sp) | set(onp) | set(offp))
    others = [rid for rid in all_ids if rid not in cset]

    # ---------------- block decomposition ----------------
    blocks = {}
    for name, counts in (('G3_start_1322', g3p), ('start_common_3967', sp),
                         ('ON_final', onp), ('OFF_final', offp)):
        blocks[name] = dict(
            total_events=(g3 if name == 'G3_start_1322' else
                          start if name == 'start_common_3967' else
                          on if name == 'ON_final' else off)['crossings'],
            converted_block=block(counts, converted),
            other_block=block(counts, others))

    # ---------------- how much of G3 did the ON arm rebuild? ----------------
    deltas_converted = [onp.get(rid, 0) - g3p.get(rid, 0) for rid in converted]
    deltas_others = [onp.get(rid, 0) - g3p.get(rid, 0) for rid in others]
    at_or_below_g3 = sum(1 for value in deltas_converted if value <= 0)
    restored = [int(row['route_id']) for row in read_csv(
        tables / ('repair_c1_%s_per_route.csv' % args.seed))
        if row['multi_arc_on'] == 'True' and row['converted_history'] == 'True']

    # ---------------- geometry: how much was rebuilt verbatim? --------------
    g3_payload = read_json(Path(
        'C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter2D/outputs/'
        'manual_c4_new_connectivity/XYZ_JOINT_G123_1024/best_valid/routes_l3d.json'))
    on_payload = read_json(Path(runs) / ('on/%s/best_valid/routes_l3d.json' % on_tag))
    off_payload = read_json(Path(runs) / ('off/%s/best_valid/routes_l3d.json' % off_tag))
    start_payload = read_json(Path(
        'C:/Users/lihao/Desktop/Graduation Project/work/1130-report-materials/'
        'G4_MULTI_ARC_ABLATION_1024/no_multi_arc/01_convert/routes_l3d.json'))
    g3r = {int(r['route_id']): r for r in g3_payload['routes']}
    onr = {int(r['route_id']): r for r in on_payload['routes']}
    offr = {int(r['route_id']): r for r in off_payload['routes']}
    spr = {int(r['route_id']): r for r in start_payload['routes']}

    def identical(a, b, ids):
        return sum(1 for rid in ids if route_geometry(a[rid]) == route_geometry(b[rid]))

    def height_changed(a, b, ids):
        return sum(1 for rid in ids
                   if abs(float(a[rid].get('target_z_mm') or 0)
                          - float(b[rid].get('target_z_mm') or 0)) > 1e-9)

    geometry = dict(
        converted=dict(
            on_identical_to_G3=identical(onr, g3r, converted),
            on_identical_to_start=identical(onr, spr, converted),
            off_identical_to_G3=identical(offr, g3r, converted),
            off_identical_to_start=identical(offr, spr, converted),
            on_height_differs_from_G3=height_changed(onr, g3r, converted),
            n=len(converted)),
        others=dict(
            on_identical_to_G3=identical(onr, g3r, others),
            on_identical_to_start=identical(onr, spr, others),
            off_identical_to_G3=identical(offr, g3r, others),
            off_identical_to_start=identical(offr, spr, others),
            n=len(others)),
    )

    # ---------------- residual split by "height changed by Stage-0" ----------
    repaired = {int(row['route_id']): row['multi_arc_on'] == 'True'
                for row in read_csv(tables / ('repair_c1_%s_per_route.csv' % args.seed))}
    buckets = {'height_unchanged': [], 'height_changed': []}
    for rid in converted:
        same_height = abs(float(g3r[rid].get('target_z_mm') or 0.0)
                          - float(onr[rid].get('target_z_mm') or 0.0)) <= 1e-9
        buckets['height_unchanged' if same_height else 'height_changed'].append(
            (rid, onp.get(rid, 0) - g3p.get(rid, 0),
             bool(repaired.get(rid, False))))
    height_split = {}
    for name, items in buckets.items():
        values = [item[1] for item in items]
        height_split[name] = dict(
            routes=len(items),
            mean_residual=round(float(st.mean(values)), 4) if values else None,
            median_residual=(round(float(st.median(values)), 4) if values else None),
            sum_residual=int(sum(values)),
            restored_multi_arc=int(sum(1 for item in items if item[2])))
    height_split['note'] = ('residual = per-route crossing count in the ON final '
                            'minus the G3 value; the two groups sum to the '
                            'converted-block residual reported in g3_rebuild')
    height_split['converted_block_residual'] = int(sum(
        onp.get(rid, 0) - g3p.get(rid, 0) for rid in converted))

    payload = dict(
        schema='g4_multi_arc_gap_analysis_v1', seed=args.seed,
        blocks=blocks,
        g3_rebuild=dict(
            converted_routes=len(converted),
            converted_routes_at_or_below_G3_level=at_or_below_g3,
            converted_routes_with_multi_arc_restored=len(restored),
            converted_mean_delta_vs_G3=round(float(st.mean(deltas_converted)), 4),
            converted_median_delta_vs_G3=round(float(st.median(deltas_converted)), 4),
            others_mean_delta_vs_G3=round(float(st.mean(deltas_others)), 4),
            others_improved_vs_G3=int(sum(1 for v in deltas_others if v < 0)),
            others_at_or_worse_vs_G3=int(sum(1 for v in deltas_others if v >= 0))),
        height_split=height_split,
        geometry=geometry)
    (tables / 'gap_analysis.json').write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')

    print('%-20s %10s %10s' % ('state', 'total', 'per-route sum'))
    for name, entry in blocks.items():
        print('%-20s %10d %10d (converted %d + others %d)'
              % (name, entry['total_events'],
                 2 * entry['total_events'], entry['converted_block']['sum'],
                 entry['other_block']['sum']))
    print()
    print(json.dumps({key: value for key, value in payload.items()
                      if key != 'blocks'}, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
