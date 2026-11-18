# -*- coding: utf-8 -*-
"""Stage-0 conversion accounting for experiment 1 (no state load required).

Reads the frozen ``conversion_report.json`` and writes:

* ``tables/conversion_by_layer.csv``  -- per inherited physical height: routes,
  crossing delta, mean delta, old/new bit counts;
* ``tables/conversion_2r.csv``        -- below/at-or-above the 2R = 30 mm
  bucket (the |bx| values are the ones computed by ``plots_ablation.py
  offset-2r`` from the real assignment/route geometry);
* ``tables/conversion_summary.json``  -- global totals + sha256 + validator.

Usage::

    python .../analyze_conversion.py --report <conversion_report.json> \
        --offset-csv <05_figures/offset_2r/offset_2r_per_route.csv> --out-dir tables
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True)
    parser.add_argument('--offset-csv', default=None)
    parser.add_argument('--out-dir', required=True)
    args = parser.parse_args()
    report = read_json(args.report)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    records = [rec for rec in report.get('records') or ()
               if rec.get('status') == 'converted']
    by_layer = {}
    for rec in records:
        layer = int(rec.get('old_layer') or 0)
        entry = by_layer.setdefault(layer, dict(
            old_layer=layer, z_mm=rec.get('old_z_mm'), routes=0,
            delta_sum=0, delta_min=0, delta_max=0, new_routes=0))
        entry['routes'] += 1
        delta = int(rec.get('commit_delta') or rec.get('delta') or 0)
        entry['delta_sum'] += delta
        entry['delta_min'] = min(entry['delta_min'], delta)
        entry['delta_max'] = max(entry['delta_max'], delta)
    rows = []
    for layer in sorted(by_layer):
        entry = by_layer[layer]
        entry['delta_mean'] = round(entry['delta_sum'] / entry['routes'], 3)
        rows.append(entry)
    with (out / 'conversion_by_layer.csv').open(
            'w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = dict(
        source=args.report,
        feasible=report.get('feasible'),
        start_crossings=report.get('start_crossings'),
        crossings_after=report.get('crossings_after'),
        crossing_delta=report.get('crossing_delta_from_start'),
        targets=report.get('targets'),
        converted=report.get('converted'),
        residual=report.get('residual'),
        escalated_route_ids=report.get('escalated_route_ids'),
        routes_sha256=report.get('routes_sha256'),
        validation_pass=report.get('validation_pass'),
        validation=report.get('validation'),
        by_layer=rows,
    )
    # ---- 2R buckets (from the independently recomputed offset CSV) -------
    buckets = []
    if args.offset_csv and Path(args.offset_csv).is_file():
        with Path(args.offset_csv).open('r', encoding='utf-8-sig',
                                        newline='') as handle:
            offset_rows = [dict(row) for row in csv.DictReader(handle)]
        key = 'bx_old_mm' if 'bx_old_mm' in (offset_rows[0] if offset_rows
                                             else {}) else 'bx_mm'
        for label, predicate in (
                ('below_2R', lambda v: v < 30.0 - 1e-9),
                ('at_or_above_2R', lambda v: v >= 30.0 - 1e-9)):
            selected = [row for row in offset_rows
                        if predicate(abs(float(row[key])))]
            deltas = [float(row.get('delta_commit')
                            or row.get('delta') or 0.0)
                      for row in selected]
            buckets.append(dict(
                bucket=label, routes=len(selected),
                delta_sum=round(sum(deltas), 3),
                delta_mean=round(sum(deltas) / len(deltas), 3) if deltas else 0,
                delta_min=(min(deltas) if deltas else 0),
                delta_max=(max(deltas) if deltas else 0)))
        with (out / 'conversion_2r.csv').open(
                'w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(buckets[0]))
            writer.writeheader()
            writer.writerows(buckets)
        summary['buckets'] = buckets
    (out / 'conversion_summary.json').write_text(
        json.dumps(summary, indent=1, ensure_ascii=False) + '\n',
        encoding='utf-8')
    lines = ['# Stage-0 OFF conversion accounting (20H, exp-1)',
             '',
             '| layer | z (mm) | routes | delta sum | delta mean | min | max |',
             '|---:|---:|---:|---:|---:|---:|---:|']
    for row in rows:
        lines.append('| L%s | %.3f | %d | %+d | %+.2f | %+d | %+d |' % (
            row['old_layer'], float(row['z_mm']), row['routes'],
            row['delta_sum'], row['delta_mean'], row['delta_min'],
            row['delta_max']))
    if buckets:
        lines += ['', '| bucket | routes | delta sum | delta mean |',
                  '|---|---:|---:|---:|']
        for row in buckets:
            lines.append('| %s | %d | %+d | %+.2f |' % (
                row['bucket'], row['routes'], row['delta_sum'],
                row['delta_mean']))
    (out / 'conversion_summary.md').write_text('\n'.join(lines) + '\n',
                                               encoding='utf-8')
    print(json.dumps(dict(converted=summary['converted'],
                          residual=summary['residual'],
                          start=summary['start_crossings'],
                          after=summary['crossings_after'],
                          delta=summary['crossing_delta'],
                          buckets=buckets), ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
