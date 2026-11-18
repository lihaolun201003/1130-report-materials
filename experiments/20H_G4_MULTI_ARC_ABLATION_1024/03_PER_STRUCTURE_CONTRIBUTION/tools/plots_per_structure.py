# -*- coding: utf-8 -*-
"""Figures of the per-patent-structure ablation (reads only real run data).

Inputs:
  tables/per_structure_runs.json  (written by run_per_structure.py collect)
Outputs (PNG + SVG, 160 dpi):
  01_benefit_by_structure       independent benefit C_i (mean +- sd) and
                                geometry-substitution cost A_i
  02_usage_by_structure         routes / instances in the Full-ON final state
  03_transactions_by_structure  accepted transactions and their true gain
  04_search_curves              crossings vs d56_candidate_evals per group
  05_group_6_compare            6a/6b/6c/6d internal comparison
  06_group_7_compare            7a/7b/7c internal comparison
  07_crossing_pairs_length      secondary metrics (pairs, max/route, length)

No value is estimated: every bar comes from a real audit/final route file.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

TYPES = ('6a', '6b', '6c', '6d', '7a', '7b', '7c')
LABELS = {key: 'Fig.%s' % key for key in TYPES}
COLORS = dict(zip(TYPES, ('#1f77b4', '#4c78a8', '#72b7b2', '#54a24b',
                          '#f58518', '#e45756', '#b279a2')))


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _save(fig, out, name):
    out.mkdir(parents=True, exist_ok=True)
    for suffix in ('png', 'svg'):
        fig.savefig(out / ('%s.%s' % (name, suffix)), dpi=160,
                    bbox_inches='tight')
    plt.close(fig)
    print('wrote', out / ('%s.png' % name))


def _values(group, field):
    return [float(seed[field]) for seed in group['seeds'].values()
            if not seed.get('missing') and seed.get(field) is not None]


def _mean_sd(values):
    if not values:
        return 0.0, 0.0
    return statistics.mean(values), (statistics.stdev(values)
                                     if len(values) > 1 else 0.0)


def figure_benefit(data, out):
    full = data['groups']['full_on']
    full_cross = [s['crossings'] for s in full['seeds'].values()
                  if not s.get('missing')]
    full_mean = statistics.mean(full_cross) if full_cross else 0.0
    benefits, costs, labels = [], [], []
    for key in TYPES:
        group = data['groups']['ablate_' + key]
        crossings = [s['crossings'] for s in group['seeds'].values()
                     if not s.get('missing')]
        benefits.append([value - full_mean for value in crossings])
        recon = group.get('start_reconstruction') or {}
        costs.append(float(recon.get('crossing_delta') or 0.0))
        labels.append(key)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    means = [statistics.mean(values) if values else 0.0 for values in benefits]
    errors = [statistics.stdev(values) if len(values) > 1 else 0.0
              for values in benefits]
    axes[0].bar(labels, means, yerr=errors, capsize=4,
                color=[COLORS[key] for key in labels])
    axes[0].axhline(0, color='black', linewidth=0.8)
    axes[0].set_ylabel('final crossings - Full-ON mean')
    axes[0].set_title('(a) independent benefit $C_i$ (positive = disabling hurts)')
    axes[1].bar(labels, costs, color=[COLORS[key] for key in labels])
    axes[1].axhline(0, color='black', linewidth=0.8)
    axes[1].set_ylabel('crossings')
    axes[1].set_title('(b) geometry-substitution cost $A_i$ (1283 -> rebuilt)')
    for axis in axes:
        axis.grid(axis='y', alpha=0.3)
    _save(fig, out, '01_benefit_by_structure')
    return dict(full_on_mean=full_mean,
                benefit={key: _mean_sd(values)
                         for key, values in zip(TYPES, benefits)},
                substitution={key: cost for key, cost in zip(TYPES, costs)})


def figure_usage(data, out):
    census = data['groups']['full_on']['seeds'][
        str(sorted(data['groups']['full_on']['seeds'])[0])]['census']
    routes = [census['types'][key]['routes'] for key in TYPES]
    instances = [census['types'][key]['instances'] for key in TYPES]
    fig, axis = plt.subplots(figsize=(10, 4.2))
    x = range(len(TYPES))
    axis.bar([i - 0.2 for i in x], routes, width=0.4, label='routes',
             color='#1f77b4')
    axis.bar([i + 0.2 for i in x], instances, width=0.4,
             label='instances', color='#ff9f4a')
    axis.set_xticks(list(x))
    axis.set_xticklabels(TYPES)
    axis.set_ylabel('count in the Full-ON final state')
    axis.set_title('Usage of the seven patent structures (real final geometry)')
    axis.legend()
    axis.grid(axis='y', alpha=0.3)
    _save(fig, out, '02_usage_by_structure')
    return dict(routes=dict(zip(TYPES, routes)),
                instances=dict(zip(TYPES, instances)))


def figure_transactions(data, out):
    groups = [data['groups']['ablate_' + key] for key in TYPES]
    accepted, exclusive, involving = [], [], []
    for group in groups:
        a = e = i = 0
        for seed in group['seeds'].values():
            if seed.get('missing'):
                continue
            rows = seed['transaction'][group['disable'][0]]
            a += rows['transactions']
            e += rows['exclusive_gain']
            i += rows['involving_gain']
        accepted.append(a)
        exclusive.append(e)
        involving.append(i)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
    axes[0].bar(TYPES, accepted, color=[COLORS[key] for key in TYPES])
    axes[0].set_title('(a) accepted transactions touching the structure')
    axes[0].set_ylabel('transactions (3 seeds)')
    width = 0.38
    axis = axes[1]
    axis.bar([i - width / 2 for i in range(len(TYPES))], exclusive,
             width=width, label='exclusive gain')
    axis.bar([i + width / 2 for i in range(len(TYPES))], involving,
             width=width, label='involving gain')
    axis.set_xticks(list(range(len(TYPES))))
    axis.set_xticklabels(TYPES)
    axis.axhline(0, color='black', linewidth=0.8)
    axis.set_title('(b) true crossing change of those transactions')
    axis.legend()
    for axis in axes:
        axis.grid(axis='y', alpha=0.3)
    _save(fig, out, '03_transactions_by_structure')
    return dict(accepted=dict(zip(TYPES, accepted)),
                exclusive=dict(zip(TYPES, exclusive)),
                involving=dict(zip(TYPES, involving)))


def _history(run_dir):
    path = Path(run_dir) / 'strategy_stats.json'
    if not path.is_file():
        return []
    stats = load(path)
    return (stats.get('extra') or {}).get('history_records') or []


def figure_curves(data, out):
    fig, axis = plt.subplots(figsize=(10, 4.8))
    for group_key, label in (('full_on', 'Full-ON'),
                             ('no_multi_arc', 'NoMultiArc')):
        group = data['groups'][group_key]
        for seed_key, seed in group['seeds'].items():
            if seed.get('missing'):
                continue
            points = []
            for record in _history(seed['dir']):
                d56 = record.get('d56')
                crossings = record.get('total')
                if d56 is None or crossings is None:
                    continue
                points.append((float(d56), float(crossings)))
            if points:
                points.sort()
                axis.plot([p[0] for p in points], [p[1] for p in points],
                          alpha=0.45, linewidth=1.2,
                          label='%s seed %s' % (label, seed_key))
    for key in TYPES:
        group = data['groups']['ablate_' + key]
        seed = next((value for value in group['seeds'].values()
                     if not value.get('missing')), None)
        if not seed:
            continue
        points = sorted((float(record['d56']),
                         float(record['total']))
                        for record in _history(seed['dir'])
                        if record.get('d56') is not None
                        and record.get('total') is not None)
        if points:
            axis.plot([p[0] for p in points], [p[1] for p in points],
                      label='Ablation-%s' % key, linewidth=1.4,
                      color=COLORS[key])
    axis.set_xlabel('d56_candidate_evals')
    axis.set_ylabel('same-plane crossing events')
    axis.set_title('G4c-free search curves (real counted budget)')
    axis.grid(alpha=0.3)
    axis.legend(ncol=2, fontsize=8)
    _save(fig, out, '04_search_curves')


def figure_secondary(data, out):
    full = data['groups']['full_on']
    full_pairs = [s['crossing_pairs'] for s in full['seeds'].values()
                  if not s.get('missing')]
    full_max = [s['max_route_crossings'] for s in full['seeds'].values()
                if not s.get('missing')]
    full_len = [s['total_length_mm'] for s in full['seeds'].values()
                if not s.get('missing')]
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.0))
    for axis, getter, title in (
            (axes[0], lambda s: s['crossing_pairs'], 'crossing pairs'),
            (axes[1], lambda s: s['max_route_crossings'],
             'max crossings on one route'),
            (axes[2], lambda s: s['total_length_mm'] / 1000.0,
             'total length (m)')):
        base = statistics.mean([getter(s) for s in full['seeds'].values()
                                if not s.get('missing')])
        values = []
        for key in TYPES:
            group = data['groups']['ablate_' + key]
            series = [getter(s) for s in group['seeds'].values()
                      if not s.get('missing')]
            values.append(statistics.mean(series) - base if series else 0.0)
        axis.bar(TYPES, values, color=[COLORS[key] for key in TYPES])
        axis.axhline(0, color='black', linewidth=0.8)
        axis.set_title('%s vs Full-ON' % title)
        axis.grid(axis='y', alpha=0.3)
    _save(fig, out, '07_secondary_metrics')
    return dict(full_on_pairs=full_pairs, full_on_max=full_max,
                full_on_length_mm=full_len)


def figure_group_compare(data, out, keys, title, filename):
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8))
    full = data['groups']['full_on']
    full_cross = statistics.mean([s['crossings']
                                  for s in full['seeds'].values()
                                  if not s.get('missing')])
    benefits = []
    costs = []
    for key in keys:
        group = data['groups']['ablate_' + key]
        crossings = [s['crossings'] for s in group['seeds'].values()
                     if not s.get('missing')]
        benefits.append(statistics.mean(crossings) - full_cross
                        if crossings else 0.0)
        costs.append(float((group.get('start_reconstruction') or {}).get(
            'crossing_delta') or 0.0))
    axes[0].bar(keys, benefits, color=[COLORS[key] for key in keys])
    axes[0].set_title('benefit $C_i$')
    axes[0].axhline(0, color='black', linewidth=0.8)
    axes[1].bar(keys, costs, color=[COLORS[key] for key in keys])
    axes[1].set_title('substitution cost $A_i$')
    for axis in axes:
        axis.grid(axis='y', alpha=0.3)
    fig.suptitle(title)
    _save(fig, out, filename)
    return dict(keys=list(keys), benefits=benefits, costs=costs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', required=True,
                        help='tables/per_structure_runs.json')
    parser.add_argument('--out-dir', required=True)
    args = parser.parse_args()
    data = load(args.runs)
    out = Path(args.out_dir)
    summary = dict(
        benefit=figure_benefit(data, out),
        usage=figure_usage(data, out),
        transactions=figure_transactions(data, out),
        secondary=figure_secondary(data, out),
        group6=figure_group_compare(data, out, ('6a', '6b', '6c', '6d'),
                                    'Patent figure 6 internal comparison',
                                    '05_group_6_compare'),
        group7=figure_group_compare(data, out, ('7a', '7b', '7c'),
                                    'Patent figure 7 internal comparison',
                                    '06_group_7_compare'),
    )
    figure_curves(data, out)
    (out / 'per_structure_figures.json').write_text(
        json.dumps(summary, indent=1, ensure_ascii=False, default=str) + '\n',
        encoding='utf-8')
    print('summary', out / 'per_structure_figures.json')


if __name__ == '__main__':
    main()
