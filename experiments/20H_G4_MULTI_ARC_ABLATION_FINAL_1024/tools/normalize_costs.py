# -*- coding: utf-8 -*-
"""Three cost normalisations of the FINAL primary runs (real history only).

Reads each run's ``strategy_stats.json`` ``extra.history_records`` (cumulative
``d56`` / ``r3d`` / ``wall`` counters and the current crossing total) and the
auxiliary equal-wall runs, then reports:

1. equal counted candidate evaluations (the primary endpoint, d56 = 24000);
2. equal true-3-D route evaluations at the OFF endpoint (linear interpolation);
3. equal wall clock (the 900 s auxiliary runs).

Writes ``tables/normalized_costs.{json,md}``.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXP = ROOT / 'experiments' / '20H_G4_MULTI_ARC_ABLATION_FINAL_1024'
SEEDS = (20261104, 20261116, 20261130)


def read(path):
    path = Path(path)
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding='utf-8-sig'))


def history(run_dir):
    stats = read(Path(run_dir) / 'strategy_stats.json')
    records = (stats.get('extra') or {}).get('history_records') or []
    start = (read(Path(run_dir) / 'summary_g4.json').get('start_crossings')
             or 4548)
    points = [(0.0, 0.0, 0.0, float(start))]
    for record in records:
        points.append((float(record.get('d56') or 0.0),
                       float(record.get('r3d') or 0.0),
                       float(record.get('wall') or 0.0),
                       float(record.get('total'))))
    return points


def at(points, axis, target):
    """Step interpolation: crossings of the last record at/below target."""
    value = points[0][3]
    for point in points:
        if point[axis] <= target + 1e-9:
            value = point[3]
        else:
            break
    return value


def mean(values):
    return statistics.mean(values) if values else None


def main():
    table = {}
    for kind, prefix in (('primary', 'c1'), ('auxiliary', 'a1')):
        for arm in ('on', 'off'):
            finals, checks, d56s, walls = [], [], [], []
            curves = []
            for seed in SEEDS:
                run = EXP / 'runs' / arm / ('%s_%s_%d' % (prefix, arm, seed))
                summary = read(run / 'summary_g4.json')
                if not summary:
                    continue
                finals.append(float(summary.get('final_crossings')))
                stats = read(run / 'strategy_stats.json')
                ledger = stats.get('ledger') or {}
                d56s.append(float(ledger.get('d56_candidate_evals') or 0.0))
                checks.append(float(ledger.get('route_3d_checks') or 0.0))
                walls.append(float(ledger.get('wall_seconds') or 0.0))
                curves.append(history(run))
            table['%s_%s' % (kind, arm)] = dict(
                finals=finals, mean_final=mean(finals),
                d56=d56s, mean_d56=mean(d56s),
                checks=checks, mean_checks=mean(checks),
                wall=walls, mean_wall=mean(walls),
                curves=curves)
    primary_on = table['primary_on']
    primary_off = table['primary_off']
    target_checks = min(primary_on['mean_checks'], primary_off['mean_checks'])
    on_at_checks = [at(curve, 1, target_checks) for curve in primary_on['curves']]
    off_at_checks = [at(curve, 1, target_checks) for curve in primary_off['curves']]
    payload = dict(
        schema='coldstart20_multiarc_normalized_costs_v1',
        equal_d56=dict(
            target=24000,
            on=primary_on['finals'], on_mean=primary_on['mean_final'],
            off=primary_off['finals'], off_mean=primary_off['mean_final'],
            gap=(primary_off['mean_final'] - primary_on['mean_final'])),
        equal_3d_checks=dict(
            target=target_checks,
            on=on_at_checks, on_mean=mean(on_at_checks),
            off=off_at_checks, off_mean=mean(off_at_checks),
            gap=(mean(off_at_checks) - mean(on_at_checks))),
        equal_wall_900s=dict(
            target=900.0,
            on=table.get('auxiliary_on', {}).get('finals'),
            on_mean=table.get('auxiliary_on', {}).get('mean_final'),
            off=table.get('auxiliary_off', {}).get('finals'),
            off_mean=table.get('auxiliary_off', {}).get('mean_final'),
            gap=((table.get('auxiliary_off', {}).get('mean_final') or 0.0)
                 - (table.get('auxiliary_on', {}).get('mean_final') or 0.0))),
        counters=dict(
            on_d56=primary_on['d56'], on_checks=primary_on['checks'],
            off_d56=primary_off['d56'], off_checks=primary_off['checks']),
    )
    (EXP / 'tables').mkdir(parents=True, exist_ok=True)
    (EXP / 'tables' / 'normalized_costs.json').write_text(
        json.dumps(payload, indent=1, ensure_ascii=False) + '\n',
        encoding='utf-8')
    lines = ['# FINAL 三种成本归一化（真实运行）', '',
             '| 归一化 | ON | OFF | 差(OFF-ON) |', '|---|---:|---:|---:|']
    lines.append('| 等候选评价 d56=24000 | %.1f | %.1f | %.1f |' % (
        payload['equal_d56']['on_mean'], payload['equal_d56']['off_mean'],
        payload['equal_d56']['gap']))
    lines.append('| 等真实三维评价 r3d=%d | %.1f | %.1f | %.1f |' % (
        payload['equal_3d_checks']['target'],
        payload['equal_3d_checks']['on_mean'],
        payload['equal_3d_checks']['off_mean'],
        payload['equal_3d_checks']['gap']))
    if payload['equal_wall_900s']['on_mean'] is not None:
        lines.append('| 等墙钟 900 s（辅助） | %.1f | %.1f | %.1f |' % (
            payload['equal_wall_900s']['on_mean'],
            payload['equal_wall_900s']['off_mean'],
            payload['equal_wall_900s']['gap']))
    (EXP / 'tables' / 'normalized_costs.md').write_text(
        '\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
