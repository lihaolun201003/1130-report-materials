# -*- coding: utf-8 -*-
"""Did the ON search *re-express* the converted routes with planar multi-arcs?

Both arms start from the identical converted state (3967, zero multi-arc
regions).  This script compares the two final states on the **197 routes that
the historical Stage-0 conversion had to rebuild**, and answers three questions:

1. how many of them got a planar multi-arc region back in the ON final state
   (the OFF gate makes that impossible by construction);
2. how their per-route crossing counts moved (start -> ON / start -> OFF);
3. how the global crossing difference decomposes over those 197 routes versus
   the other 827 routes.

Everything is read from the stored route files with the same frozen helpers used
elsewhere (``audit_state``), so the numbers are independent of the engines that
produced them.

Usage::

    python .../tools/analyze_repair.py --on runs/on/c1_on_X/best_valid \
        --off runs/off/c1_off_X/best_valid --start <01_convert> \
        --out tables/repair_<tag>.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
ROOT = EXP.parents[1]
for path in (str(ROOT), str(HERE)):
    if path not in sys.path:
        sys.path.insert(0, path)

import audit_state as AUDIT  # noqa: E402

OLD_REPO = Path('C:/Users/lihao/Desktop/Graduation Project/work/1130-report-materials/'
                'G4_MULTI_ARC_ABLATION_1024')
CONVERT_DIR = OLD_REPO / 'no_multi_arc' / '01_convert'


def converted_route_ids():
    report = json.loads((CONVERT_DIR / 'conversion_report.json').read_text(
        encoding='utf-8'))
    return sorted(int(record['route_id']) for record in report['records'])


def load_audit(run_dir, label):
    return AUDIT.audit_run(run_dir, label=label)


def summarize(converted, start, on, off):
    ids = set(converted)
    rows = []
    per_start = {int(k): int(v) for k, v in start['per_route_crossings'].items()}
    per_on = {int(k): int(v) for k, v in on['per_route_crossings'].items()}
    per_off = {int(k): int(v) for k, v in off['per_route_crossings'].items()}
    on_multi = {int(k) for k in on['multi_arc']['per_route_with_multi_arc']}
    off_multi = {int(k) for k in off['multi_arc']['per_route_with_multi_arc']}
    start_multi = {int(k) for k in start['multi_arc']['per_route_with_multi_arc']}
    for rid in sorted(set(per_start) | set(per_on) | set(per_off)):
        rid = int(rid)
        rows.append(dict(
            route_id=rid,
            converted_history=rid in ids,
            crossings_start=int(per_start.get(rid, 0)),
            crossings_on=int(per_on.get(rid, 0)),
            crossings_off=int(per_off.get(rid, 0)),
            delta_on=int(per_on.get(rid, 0)) - int(per_start.get(rid, 0)),
            delta_off=int(per_off.get(rid, 0)) - int(per_start.get(rid, 0)),
            multi_arc_start=rid in start_multi,
            multi_arc_on=rid in on_multi,
            multi_arc_off=rid in off_multi,
        ))

    def block(selector):
        subset = [row for row in rows if selector(row)]
        return dict(
            routes=len(subset),
            crossings_start=sum(row['crossings_start'] for row in subset),
            crossings_on=sum(row['crossings_on'] for row in subset),
            crossings_off=sum(row['crossings_off'] for row in subset),
            delta_on=sum(row['delta_on'] for row in subset),
            delta_off=sum(row['delta_off'] for row in subset),
            multi_arc_on=sum(1 for row in subset if row['multi_arc_on']),
            multi_arc_off=sum(1 for row in subset if row['multi_arc_off']),
            routes_improved_on=sum(1 for row in subset if row['delta_on'] < 0),
            routes_worsened_on=sum(1 for row in subset if row['delta_on'] > 0),
            routes_improved_off=sum(1 for row in subset if row['delta_off'] < 0),
            routes_worsened_off=sum(1 for row in subset if row['delta_off'] > 0),
        )

    payload = dict(
        schema='g4_multi_arc_repair_v1',
        converted_block=block(lambda row: row['converted_history']),
        other_block=block(lambda row: not row['converted_history']),
        global_block=block(lambda row: True),
        restored_multi_arc_on=sum(1 for row in rows if row['multi_arc_on']
                                  and row['converted_history']),
        restored_multi_arc_off=sum(1 for row in rows if row['multi_arc_off']
                                   and row['converted_history']),
        converted_with_multi_arc_but_no_gain=sum(
            1 for row in rows
            if row['converted_history'] and row['multi_arc_on']
            and row['delta_on'] >= 0),
        rows=rows,
    )
    # sanity: block sums must reproduce the audited totals
    payload['check'] = dict(
        start_total_from_rows=sum(row['crossings_start'] for row in rows) // 2,
        on_total_from_rows=sum(row['crossings_on'] for row in rows) // 2,
        off_total_from_rows=sum(row['crossings_off'] for row in rows) // 2,
        start_total=start['crossings'], on_total=on['crossings'],
        off_total=off['crossings'])
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--on', required=True)
    parser.add_argument('--off', required=True)
    parser.add_argument('--start', default=str(CONVERT_DIR))
    parser.add_argument('--out', required=True)
    parser.add_argument('--csv', default=None)
    args = parser.parse_args(argv)

    converted = converted_route_ids()
    start = load_audit(args.start, 'start')
    on = load_audit(args.on, 'on')
    off = load_audit(args.off, 'off')
    payload = summarize(converted, start, on, off)
    payload['inputs'] = dict(start=str(args.start), on=str(args.on),
                             off=str(args.off),
                             start_sha256=start['routes_sha256'],
                             on_sha256=on['routes_sha256'],
                             off_sha256=off['routes_sha256'])
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({key: value for key, value in payload.items()
                               if key != 'rows'}, ensure_ascii=False, indent=1),
                   encoding='utf-8')
    if args.csv:
        csv_path = Path(args.csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(payload['rows'][0].keys()))
            writer.writeheader()
            writer.writerows(payload['rows'])
    print(json.dumps({key: value for key, value in payload.items()
                      if key != 'rows'}, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
