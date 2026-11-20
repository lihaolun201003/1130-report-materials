# -*- coding: utf-8 -*-
"""G6 figures: search curves, acceptance/temperature, angle distributions.

All figures are produced from the raw run artefacts (``history.jsonl``,
``summary.json``, independent-validator ``g5_crossing_angles.csv``), so they are
reproducible from the delivered data without re-running the search.
"""
from __future__ import annotations

import csv
import json
import math
import os
from collections import Counter, defaultdict

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

BINS = [(0, 5), (5, 10), (10, 20), (20, 30), (30, 40), (40, 45),
        (45, 60), (60, 75), (75, 90.0001)]


# ---------------------------------------------------------------------------
# raw data helpers
# ---------------------------------------------------------------------------
def _read_json(path):
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def _read_history(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def collect_seeds(root):
    """Return ``[(seed, summary_path, seed_dir)]`` sorted by seed."""
    found = []
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        summary = os.path.join(path, 'summary.json')
        if name.startswith('seed_') and os.path.isfile(summary):
            try:
                seed = int(name.split('_', 1)[1])
            except ValueError:
                continue
            found.append((seed, summary, path))
    return found


def seed_histories(seed_dir):
    """Concatenate the cycle histories of one seed with a global move index."""
    points = []
    cycles = sorted(
        [entry for entry in os.listdir(seed_dir)
         if entry.startswith('cycle_') and
         os.path.isdir(os.path.join(seed_dir, entry))])
    move_offset = 0.0
    elapsed_offset = 0.0
    for cycle in cycles:
        history = _read_history(os.path.join(seed_dir, cycle, 'logs',
                                             'history.jsonl'))
        last_move = 0
        last_elapsed = 0.0
        for row in history:
            move = float(row.get('move') or 0) + move_offset
            elapsed = float(row.get('elapsed') or 0.0) + elapsed_offset
            points.append(dict(kind=row.get('event'), move=move,
                               elapsed=elapsed, n_bad=row.get('n_bad'),
                               deficit=row.get('deficit'),
                               T=row.get('T'),
                               accepted=row.get('accepted'),
                               move_kind=row.get('move_kind'),
                               percent=row.get('n_bad')))
            last_move = max(last_move, move_offset + float(row.get('move') or 0))
            last_elapsed = max(last_elapsed,
                               elapsed_offset + float(row.get('elapsed') or 0.0))
        move_offset = last_move
        elapsed_offset = last_elapsed
    return points


# ---------------------------------------------------------------------------
# figures
# ---------------------------------------------------------------------------
def fig_search_curves(root, out_path, title='G6 warm start (MultiArc SA)'):
    seeds = collect_seeds(root)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    best = None
    for seed, summary_path, seed_dir in seeds:
        points = [row for row in seed_histories(seed_dir)
                  if row['n_bad'] is not None]
        if not points:
            continue
        steps = [row['move'] for row in points]
        values = [row['n_bad'] for row in points]
        axes[0].plot(steps, values, lw=0.9, alpha=0.65, label=f'seed {seed}')
        axes[1].plot([row['elapsed'] / 60.0 for row in points], values,
                     lw=0.9, alpha=0.65)
        key = min((int(row['n_bad']), float(row['deficit']), row['move'])
                  for row in points)
        if best is None or key < best[0]:
            best = (key, steps, values)
    if best is not None:
        axes[0].plot(best[1], best[2], color='black', lw=2.2,
                     label='best seed')
        axes[1].plot([point / 1.0 for point in best[1]], best[2],
                     color='black', lw=2.2)
    for axis in axes:
        axis.set_ylabel('N_bad  (<45 deg crossings)')
        axis.grid(alpha=0.3)
        axis.axhline(0, color='green', lw=1, ls='--')
    axes[0].set_xlabel('move attempts')
    axes[1].set_xlabel('wall time (min, sum over cycles)')
    axes[0].set_title('violations vs moves')
    axes[1].set_title('violations vs time')
    axes[0].legend(fontsize=7, ncol=2)
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return out_path


def fig_temperature(root, out_path):
    seeds = collect_seeds(root)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.2))
    for seed, summary_path, seed_dir in seeds[:6]:
        points = [row for row in seed_histories(seed_dir)
                  if row['T'] is not None]
        if not points:
            continue
        axes[0].plot([row['move'] for row in points],
                     [row['T'] for row in points], lw=0.9,
                     label=f'seed {seed}')
        accepted = [(row['move'], row['accepted']) for row in points
                    if row['accepted'] is not None]
        if len(accepted) > 1:
            axes[1].plot([move for move, _ in accepted],
                         [value for _, value in accepted], lw=0.9)
    axes[0].set_xlabel('move attempts')
    axes[0].set_ylabel('temperature T')
    axes[0].set_title('annealing temperature')
    axes[0].grid(alpha=0.3)
    axes[0].legend(fontsize=7)
    axes[1].set_xlabel('move attempts')
    axes[1].set_ylabel('cumulative accepted moves')
    axes[1].set_title('accepted moves (all seeds in the same colour order)')
    axes[1].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return out_path


def _read_crossings(path):
    rows = []
    with open(path, encoding='utf-8', newline='') as handle:
        for row in csv.DictReader(handle):
            try:
                rows.append(dict(z=float(row['z_mm']),
                                 x=float(row['x_mm']),
                                 y=float(row['y_mm']),
                                 angle=float(row['angle_deg']),
                                 route_a=int(row['route_a']),
                                 route_b=int(row['route_b'])))
            except (KeyError, TypeError, ValueError):
                continue
    return rows


def fig_angle_hist(csv_before, csv_after, out_path):
    before = _read_crossings(csv_before)
    after = _read_crossings(csv_after)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.2))
    edges = [0, 5, 10, 20, 30, 40, 45, 60, 75, 90.0001]
    for axis, rows, title in ((axes[0], before, 'before'),
                              (axes[1], after, 'after')):
        angles = [row['angle'] for row in rows]
        counts = [0] * (len(edges) - 1)
        for angle in angles:
            for index in range(len(edges) - 1):
                if edges[index] <= angle < edges[index + 1]:
                    counts[index] += 1
                    break
        axis.bar(range(len(counts)), counts,
                 color=['#c0392b' if edge < 45 else '#2471a3'
                        for edge in edges[:-1]])
        axis.set_xticks(range(len(counts)))
        axis.set_xticklabels([f'{edges[i]}-{edges[i+1]}'
                              for i in range(len(counts))], rotation=40,
                             fontsize=7)
        axis.set_title(f'{title}: {len(angles)} crossings, '
                       f'{sum(1 for a in angles if a < 45)} <45 deg')
        axis.set_ylabel('crossings')
        axis.grid(alpha=0.3)
    fig.suptitle('crossing-angle distribution (same-height crossings)')
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return out_path


def fig_per_layer(csv_path, out_path):
    """20-panel map of the final same-height crossings (colour by pass/fail)."""
    rows = _read_crossings(csv_path)
    levels = sorted({round(row['z'], 6) for row in rows})
    fig, axes = plt.subplots(4, 5, figsize=(16, 13))
    for index, axis in enumerate(axes.ravel()):
        if index >= len(levels):
            axis.axis('off')
            continue
        level = levels[index]
        here = [row for row in rows if round(row['z'], 6) == level]
        bad = [row for row in here if row['angle'] < 45]
        good = [row for row in here if row['angle'] >= 45]
        axis.scatter([row['x'] for row in good], [row['y'] for row in good],
                     s=3, c='#2471a3', alpha=0.45)
        axis.scatter([row['x'] for row in bad], [row['y'] for row in bad],
                     s=16, c='#c0392b', alpha=0.9, marker='x')
        axis.set_xlim(0, 150)
        axis.set_ylim(0, 150)
        axis.set_aspect('equal')
        axis.set_title(f'z={level:+.3f} mm  n={len(here)} bad={len(bad)}',
                       fontsize=8)
        axis.tick_params(labelsize=6)
    handles = [plt.Line2D([], [], marker='o', ls='', color='#2471a3',
                          label='crossing >=45 deg'),
               plt.Line2D([], [], marker='x', ls='', color='#c0392b',
                          label='crossing <45 deg')]
    fig.legend(handles=handles, loc='upper center', ncol=2)
    fig.suptitle('G6 final geometry: same-height crossings per physical layer')
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def _sample_primitive(prim, count=12):
    """Sample one JSON flat primitive to a list of (x, y) points."""
    if prim.get('kind') == 'line':
        return [tuple(prim['p0']), tuple(prim['p1'])]
    center = prim.get('center') or (0.0, 0.0)
    radius = float(prim.get('radius') or 0.0)
    start = float(prim.get('start_angle') or 0.0)
    sweep = float(prim.get('sweep') or 0.0)
    return [(center[0] + radius * math.cos(start + sweep * index / count),
             center[1] + radius * math.sin(start + sweep * index / count))
            for index in range(count + 1)]


def fig_per_layer_geometry(routes_json, out_path):
    """20-panel map of every routed centreline + the crossings on that layer."""
    with open(routes_json, encoding='utf-8') as handle:
        doc = json.load(handle)
    layers = {}
    for route in doc.get('routes') or ():
        for part in route.get('parts') or ():
            if part.get('kind') != 'flat':
                continue
            layer = layers.setdefault(round(float(part['z_mm']), 6), [])
            for prim in part.get('primitives') or ():
                layer.append(_sample_primitive(prim))
    levels = sorted(layers)
    fig, axes = plt.subplots(4, 5, figsize=(17, 14))
    for index, axis in enumerate(axes.ravel()):
        if index >= len(levels):
            axis.axis('off')
            continue
        level = levels[index]
        for polyline in layers[level]:
            axis.plot([point[0] for point in polyline],
                      [point[1] for point in polyline],
                      lw=0.25, color='#5d6d7e', alpha=0.55)
        axis.set_xlim(0, 150)
        axis.set_ylim(0, 150)
        axis.set_aspect('equal')
        axis.set_title(f'z={level:+.3f} mm  routes={len(layers[level])}',
                       fontsize=8)
        axis.tick_params(labelsize=6)
    fig.suptitle('G6 final geometry: all 1024 true-XYZ routes, one panel per '
                 'physical height')
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    return out_path


def fig_neighbourhood(root, out_path):
    seeds = collect_seeds(root)
    totals = defaultdict(Counter)
    for seed, summary_path, seed_dir in seeds:
        summary = _read_json(summary_path)
        for cycle in summary.get('summaries') or ():
            for kind, counter in (cycle.get('move_stats') or {}).items():
                for key, value in (counter or {}).items():
                    totals[kind][key] += int(value or 0)
    kinds = sorted(totals)
    attempted = [totals[kind].get('attempted', 0) for kind in kinds]
    accepted = [totals[kind].get('accepted', 0) for kind in kinds]
    improving = [totals[kind].get('improving', 0) for kind in kinds]
    fig, axis = plt.subplots(figsize=(max(6, 1.1 * len(kinds) + 3), 4.2))
    positions = range(len(kinds))
    axis.bar([pos - 0.27 for pos in positions], attempted, width=0.27,
             label='attempted', color='#7f8c8d')
    axis.bar(list(positions), accepted, width=0.27, label='accepted',
             color='#2471a3')
    axis.bar([pos + 0.27 for pos in positions], improving, width=0.27,
             label='improving (N_bad down)', color='#27ae60')
    axis.set_xticks(list(positions))
    axis.set_xticklabels(kinds, rotation=25, fontsize=8)
    axis.set_ylabel('moves')
    axis.set_title('G6 neighbourhood contribution (all seeds, all cycles)')
    axis.grid(alpha=0.3, axis='y')
    axis.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return out_path


def fig_early_compare(off_stats, on_stats, out_path):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
    labels = ['greedy\n(angle-blind)', 'angle-aware\nMultiArc']
    values = [off_stats['n_bad'], on_stats['n_bad']]
    axes[0].bar(labels, values, color=['#7f8c8d', '#27ae60'])
    for index, value in enumerate(values):
        axes[0].text(index, value, f'{value}', ha='center', va='bottom',
                     fontsize=10)
    axes[0].set_ylabel('N_bad at end of early-start construction')
    axes[0].set_title('early-start construction stage')
    axes[0].grid(alpha=0.3, axis='y')
    axes[1].bar(labels, [off_stats['crossings'], on_stats['crossings']],
                color=['#7f8c8d', '#2471a3'])
    axes[1].set_ylabel('total same-height crossings')
    axes[1].set_title('total crossings (recorded only, not optimised)')
    axes[1].grid(alpha=0.3, axis='y')
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return out_path
