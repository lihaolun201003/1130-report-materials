# -*- coding: utf-8 -*-
"""G7 figures (reproducible from the delivered artefacts)."""
from __future__ import annotations

import json
import os
from collections import Counter

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def _load(path, default=None):
    try:
        with open(path, encoding='utf-8') as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def collect_seed_summaries(run_dir):
    rows = []
    if not os.path.isdir(run_dir):
        return rows
    for name in sorted(os.listdir(run_dir)):
        path = os.path.join(run_dir, name)
        summary = os.path.join(path, 'summary.json')
        if name.startswith('seed_') and os.path.exists(summary):
            data = _load(summary) or {}
            rows.append(dict(seed=int(name.split('_', 1)[1]), data=data))
    return rows


def fig_convergence(arms, out_path):
    """Crossing count vs move attempts: one panel per arm, all seeds."""
    fig, axes = plt.subplots(1, len(arms), figsize=(6 * len(arms), 4.4),
                             squeeze=False)
    for axis, (arm, run_dir) in zip(axes[0], arms.items()):
        best = None
        for row in collect_seed_summaries(run_dir):
            history_path = os.path.join(run_dir, 'seed_%d' % row['seed'],
                                        'logs', 'history.jsonl')
            points = []
            if not os.path.exists(history_path):
                continue
            with open(history_path, encoding='utf-8') as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if record.get('event') not in ('improve', 'stat'):
                        continue
                    if record.get('crossings') is None:
                        continue
                    points.append((float(record.get('move') or 0),
                                   int(record['crossings']),
                                   float(record.get('elapsed') or 0.0)))
            if not points:
                continue
            points.sort()
            axis.step([p[0] for p in points], [p[1] for p in points],
                      where='post', lw=0.9, alpha=0.65)
            candidate = min(points, key=lambda item: (item[1], item[0]))
            if best is None or (candidate[1], candidate[0]) < (best[1],
                                                               best[0]):
                best = candidate
        if best is not None:
            axis.axhline(best[1], color='black', lw=1.4, ls='--',
                         label='best %d' % best[1])
            axis.legend(fontsize=8)
        axis.axhline(4578, color='#c0392b', lw=1.0, ls=':',
                     label='G6 start 4578')
        axis.set_title(arm, fontsize=10)
        axis.set_xlabel('move attempts')
        axis.set_ylabel('same-height crossings')
        axis.grid(alpha=0.3)
    fig.suptitle('G7 fixed-layer MultiArc SA: crossing-count convergence')
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return out_path


def fig_arm_compare(arm_best, out_path):
    arms = list(arm_best)
    values = [arm_best[arm] for arm in arms]
    fig, axis = plt.subplots(figsize=(6.4, 4.0))
    bars = axis.bar(arms, values, color=['#5d6d7e', '#2471a3', '#27ae60',
                                         '#8e44ad'][:len(arms)])
    for bar, value in zip(bars, values):
        axis.text(bar.get_x() + bar.get_width() / 2, value, str(value),
                  ha='center', va='bottom', fontsize=10)
    axis.axhline(4578, color='#c0392b', ls=':', label='G6 start 4578')
    axis.set_ylabel('best crossing count')
    axis.set_title('G7 arm comparison (fixed layer + fixed transitions)')
    axis.grid(alpha=0.3, axis='y')
    axis.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return out_path


def fig_per_layer_compare(analysis, out_path):
    before = {row['z_mm']: row for row in analysis['before']['planes']}
    after = analysis['after']['planes']
    levels = [row['z_mm'] for row in after]
    old = [before.get(z, {}).get('crossings', 0) for z in levels]
    new = [row['crossings'] for row in after]
    fig, axis = plt.subplots(figsize=(13, 4.4))
    positions = range(len(levels))
    axis.bar([p - 0.2 for p in positions], old, width=0.4,
             label='G6 before', color='#7f8c8d')
    axis.bar([p + 0.2 for p in positions], new, width=0.4,
             label='G7 after', color='#2471a3')
    axis.set_xticks(list(positions))
    axis.set_xticklabels(['%+.3f' % z for z in levels], rotation=75,
                         fontsize=7)
    axis.set_ylabel('same-height crossings')
    axis.set_title('G7 per-physical-height crossing count before/after')
    axis.grid(alpha=0.3, axis='y')
    axis.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return out_path


def fig_route_distribution(analysis, out_path):
    before = Counter({int(row['route_id']): row['crossings']
                      for row in analysis['before']['routes']})
    after = Counter({int(row['route_id']): row['crossings']
                     for row in analysis['after']['routes']})
    fig, axis = plt.subplots(figsize=(8, 4.2))
    bins = [0, 1, 2, 3, 5, 8, 12, 20, 30, 50, 80, 120, 200]
    for label, counts, color in (('G6 before', before, '#7f8c8d'),
                                 ('G7 after', after, '#2471a3')):
        hist = [0] * (len(bins) - 1)
        for value in counts.values():
            for index in range(len(bins) - 1):
                if bins[index] <= value < bins[index + 1]:
                    hist[index] += 1
                    break
            else:
                if value >= bins[-1]:
                    hist[-1] += 1
        axis.plot(range(len(hist)), hist, marker='o', label=label,
                  color=color)
    axis.set_xticks(range(len(bins) - 1))
    axis.set_xticklabels(['%d-%d' % (bins[i], bins[i + 1])
                          for i in range(len(bins) - 1)], rotation=40,
                         fontsize=7)
    axis.set_ylabel('number of routes')
    axis.set_title('per-route crossing count distribution')
    axis.grid(alpha=0.3)
    axis.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return out_path


def fig_attribution(analysis, out_path):
    totals = Counter()
    for arm in analysis.get('attribution') or ():
        for seed in arm.get('seeds') or ():
            for kind, count in (seed.get('improve_moves') or {}).items():
                totals[kind] += int(count)
    kinds = sorted(totals)
    values = [totals[kind] for kind in kinds]
    fig, axis = plt.subplots(figsize=(max(6, 1.2 * len(kinds) + 3), 4.0))
    axis.bar(kinds, values, color='#27ae60')
    for index, value in enumerate(values):
        axis.text(index, value, str(value), ha='center', va='bottom',
                  fontsize=9)
    axis.set_ylabel('improving moves')
    axis.set_title('G7 improving-move attribution by neighbourhood')
    axis.grid(alpha=0.3, axis='y')
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return out_path


def fig_hotspots(before_csv, after_csv, out_path):
    import sys
    import csv
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, '..', '..', '..', '..'))
    if root not in sys.path:
        sys.path.insert(0, root)
    from four_side_1024.fanout1024.xyzrouter.g6 import plots as G6P
    return G6P.fig_angle_hist(before_csv, after_csv, out_path)


def fig_per_layer_crossings(csv_path, out_path):
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, '..', '..', '..', '..'))
    if root not in sys.path:
        sys.path.insert(0, root)
    from four_side_1024.fanout1024.xyzrouter.g6 import plots as G6P
    return G6P.fig_per_layer(csv_path, out_path)


def fig_per_layer_geometry(routes_path, out_path):
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, '..', '..', '..', '..'))
    if root not in sys.path:
        sys.path.insert(0, root)
    from four_side_1024.fanout1024.xyzrouter.g6 import plots as G6P
    return G6P.fig_per_layer_geometry(routes_path, out_path)
