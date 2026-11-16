# -*- coding: utf-8 -*-
"""Per-seed / per-arm statistics and the pre-registered A/B/C judgement.

Consumes ``tables/runs.json`` (written by ``collect_results.py``) and produces

* ``tables/summary_<prefix>.json``  -- machine readable
* ``tables/summary_<prefix>.md``    -- markdown tables for the report

Statistics with n = 3 seeds are **exploratory**: mean, sample standard deviation
(ddof = 1), min / max / range, median, and the paired ON - OFF difference per
seed.  No significance test is claimed.

Usage::

    python .../tools/summarize.py --runs-json tables/runs.json --prefix c1 \
        --label "Primary (equal candidate-evaluation budget)"
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent


def stats(values):
    values = [float(v) for v in values if v is not None]
    n = len(values)
    if not n:
        return dict(n=0)
    mean = sum(values) / n
    if n > 1:
        var = sum((v - mean) ** 2 for v in values) / (n - 1)
        std = math.sqrt(var)
    else:
        std = None
    ordered = sorted(values)
    median = (ordered[n // 2] if n % 2 else
              0.5 * (ordered[n // 2 - 1] + ordered[n // 2]))
    return dict(n=n, mean=round(mean, 4),
                std=round(std, 4) if std is not None else None,
                min=round(ordered[0], 4), max=round(ordered[-1], 4),
                range=round(ordered[-1] - ordered[0], 4),
                median=round(median, 4),
                values=[round(v, 4) for v in values])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs-json', default=str(EXP / 'tables' / 'runs.json'))
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--label', default='')
    parser.add_argument('--start', type=int, default=3967)
    parser.add_argument('--out', default=str(EXP / 'tables'))
    args = parser.parse_args(argv)

    payload = json.loads(Path(args.runs_json).read_text(encoding='utf-8'))
    rows = [row for row in payload['runs']
            if str(row['tag']).startswith(args.prefix)
            and row.get('status') != 'incomplete']
    if not rows:
        print('no runs with prefix %r' % args.prefix)
        return 1
    arms = {}
    for row in rows:
        arms.setdefault(str(row['arm']), {})[int(row['seed'])] = row
    seeds = sorted(set.intersection(*[set(v) for v in arms.values()])) \
        if arms else []

    metrics = ['final_crossings', 'delta_vs_start', 'crossing_pairs',
               'routes_with_crossings', 'max_route_crossings',
               'total_length_mm', 'flat_arcs', 'multi_arc_routes',
               'multi_arc_regions', 'd56_candidate_evals', 'route_3d_checks',
               'xy_candidates_generated', 'valid_candidates', 'rejected_3d',
               'accepts', 'wall_seconds', 'min_3d_clearance_mm']

    summary = dict(schema='g4_multi_arc_final_summary_v1',
                   label=args.label, prefix=args.prefix,
                   start_crossings=args.start, seeds=seeds,
                   n_seeds=len(seeds), by_arm={}, paired={}, gates={},
                   decision={}, runs=rows)
    for arm, per_seed in sorted(arms.items()):
        summary['by_arm'][arm] = {}
        for metric in metrics:
            summary['by_arm'][arm][metric] = stats(
                [per_seed[seed].get(metric) for seed in seeds])
        summary['by_arm'][arm]['multi_arc_flag'] = sorted(
            {per_seed[seed].get('multi_arc') for seed in seeds})

    for metric in metrics:
        on = [arms.get('on', {}).get(seed, {}).get(metric) for seed in seeds]
        off = [arms.get('off', {}).get(seed, {}).get(metric) for seed in seeds]
        if any(v is None for v in on) or any(v is None for v in off):
            continue
        diffs = [float(a) - float(b) for a, b in zip(on, off)]
        summary['paired'][metric] = dict(
            on=[round(float(v), 4) for v in on],
            off=[round(float(v), 4) for v in off],
            diff_on_minus_off=[round(v, 4) for v in diffs],
            diff_stats=stats(diffs),
            n_on_better=int(sum(1 for v in diffs if v < 0)),
            n_off_better=int(sum(1 for v in diffs if v > 0)),
            n_tie=int(sum(1 for v in diffs if v == 0)))
    # relative length change of ON w.r.t. OFF (positive = ON longer)
    length = summary['paired'].get('total_length_mm')
    if length:
        rel = [(a - b) / b for a, b in zip(length['on'], length['off'])]
        summary['paired']['total_length_mm']['relative_on_vs_off'] = [
            round(v, 6) for v in rel]
        summary['paired']['total_length_mm']['relative_mean'] = round(
            sum(rel) / len(rel), 6)

    # ---------------- hard gates ----------------
    gates = {}
    for row in rows:
        tag = '%s/%s' % (row['arm'], row['tag'])
        gates[tag] = dict(
            routed_1024=(row.get('routed') == 1024 and row.get('failed') == 0),
            validator_pass=bool(row.get('validator_pass')),
            validator_final_pass=(row.get('validator_final_pass')
                                  if row.get('validator_final_pass') is not None
                                  else 'not_run'),
            violations_zero=(row.get('violations') == 0),
            radius_ok=(row.get('min_flat_arc_radius_mm') is None
                       or row['min_flat_arc_radius_mm'] >= 15.0 - 1e-6),
            clearance_ok=(row.get('min_3d_clearance_mm') is None
                          or row['min_3d_clearance_mm'] >= 0.05),
            d56_ok=(row.get('min_non_crossing_centerline_mm') is None
                    or row['min_non_crossing_centerline_mm'] >= 0.08 - 1e-9),
            multi_arc_absent_for_off=(row['arm'] != 'off'
                                      or row.get('multi_arc_regions') == 0),
            consistency=row.get('consistency') or {},
        )
        gates[tag]['all_ok'] = all([
            gates[tag]['routed_1024'], gates[tag]['validator_pass'],
            gates[tag]['violations_zero'], gates[tag]['radius_ok'],
            gates[tag]['clearance_ok'], gates[tag]['d56_ok'],
            gates[tag]['multi_arc_absent_for_off']])
    summary['gates'] = gates

    # ---------------- pre-registered decision ----------------
    crossings = summary['paired'].get('final_crossings')
    length_rel = summary['paired'].get('total_length_mm', {}).get('relative_mean')
    all_gates = all(entry['all_ok'] for entry in gates.values())
    decision = dict(rule=('A: 3/3 seeds ON<OFF and paired mean gap >= 200 '
                          'crossings and ON length increase <= 5% and all hard '
                          'gates pass; C: mean gap <= 0 or direction '
                          'inconsistent; B: otherwise'))
    if crossings:
        mean_diff = crossings['diff_stats']['mean']
        n_on_better = crossings['n_on_better']
        crit_a = (n_on_better == len(seeds) and mean_diff <= -200
                  and (length_rel is None or length_rel <= 0.05) and all_gates)
        crit_c = (mean_diff >= 0 or
                  (0 < n_on_better < len(seeds) and
                   crossings['n_off_better'] > 0))
        decision.update(
            mean_paired_gap=mean_diff,
            seeds_on_better=n_on_better,
            seeds_off_better=crossings['n_off_better'],
            relative_length_change=length_rel,
            all_hard_gates_pass=bool(all_gates),
            verdict=('A' if crit_a else ('C' if crit_c else 'B')))
    else:
        decision['verdict'] = 'B'
    summary['decision'] = decision

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / ('summary_%s.json' % args.prefix)).write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')

    # ---------------- markdown ----------------
    lines = []
    lines.append('### %s' % (args.label or args.prefix))
    lines.append('')
    lines.append('Common start = %d crossings; seeds = %s; n = %d '
                 '(exploratory statistics).' % (args.start,
                                                ', '.join(str(s) for s in seeds),
                                                len(seeds)))
    lines.append('')
    header = ('| metric | ON mean | ON std | ON min..max | OFF mean | OFF std | '
              'OFF min..max | paired mean ON-OFF | ON better / OFF better |')
    lines.append(header)
    lines.append('|---|---:|---:|---|---:|---:|---|---:|---:|')
    for metric in metrics:
        on = summary['by_arm'].get('on', {}).get(metric) or {}
        off = summary['by_arm'].get('off', {}).get(metric) or {}
        pair = summary['paired'].get(metric) or {}
        if not on.get('n') or not off.get('n'):
            continue
        diff = pair.get('diff_stats') or {}
        lines.append('| %s | %s | %s | %s..%s | %s | %s | %s..%s | %s | %s / %s |'
                     % (metric, on.get('mean'), on.get('std'), on.get('min'),
                        on.get('max'), off.get('mean'), off.get('std'),
                        off.get('min'), off.get('max'), diff.get('mean'),
                        pair.get('n_on_better'), pair.get('n_off_better')))
    lines.append('')
    lines.append('**Paired per seed (crossings)**: ON %s vs OFF %s -> diff %s'
                 % (crossings['on'] if crossings else '-',
                    crossings['off'] if crossings else '-',
                    crossings['diff_on_minus_off'] if crossings else '-'))
    lines.append('')
    lines.append('**Judgement**: %s' % decision.get('verdict'))
    lines.append('')
    lines.append('| gate | value |')
    lines.append('|---|---|')
    for key in ('mean_paired_gap', 'seeds_on_better', 'seeds_off_better',
                'relative_length_change', 'all_hard_gates_pass', 'rule'):
        lines.append('| %s | %s |' % (key, decision.get(key)))
    lines.append('')
    lines.append('| run | all gates | validator | violations | min 3D clr | '
                 'min radius | D56 clr | multi-arc regions |')
    lines.append('|---|---|---|---:|---:|---:|---:|---:|')
    for row in rows:
        tag = '%s/%s' % (row['arm'], row['tag'])
        gate = gates[tag]
        lines.append('| %s | %s | %s | %s | %s | %s | %s | %s |' % (
            tag, gate['all_ok'], gate['validator_pass'], row.get('violations'),
            row.get('min_3d_clearance_mm'), row.get('min_flat_arc_radius_mm'),
            row.get('min_non_crossing_centerline_mm'),
            row.get('multi_arc_regions')))
    text = '\n'.join(lines) + '\n'
    (out / ('summary_%s.md' % args.prefix)).write_text(text, encoding='utf-8')
    print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
