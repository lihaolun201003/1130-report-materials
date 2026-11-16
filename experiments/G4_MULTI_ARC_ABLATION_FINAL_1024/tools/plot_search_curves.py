# -*- coding: utf-8 -*-
"""Search-progress figures and matched-cost interpolation tables.

Three cost axes are *not* interchangeable, so every curve is produced on all
three and the paper figure keeps them separate:

1. ``d56_candidate_evals``  -- the frozen candidate-evaluation budget (primary)
2. ``route_3d_checks``      -- exact true-3D route evaluations (normalisation)
3. ``wall_seconds``         -- elapsed search time

For each run the crossings-vs-cost curve is built from
``strategy_stats.json['extra']['history_records']`` (one record per attempted
operator, carrying the cumulative ledger counters).  Because the search only
ever accepts strictly improving transactions, the current total is monotone, so
the curve is also the best-so-far curve.

Outputs
-------
``figures/fig_search_curves.png``      3 panels, per-seed thin + mean bold
``figures/fig_search_curves_norm.png`` crossings vs d56 and vs r3d, seeded bands
``tables/search_curve_matched.csv``    interpolated crossings on a common grid
``tables/search_curve_final.csv``      final point of every run on all 3 axes

Usage::

    python experiments/G4_MULTI_ARC_ABLATION_FINAL_1024/tools/plot_search_curves.py \
        --runs-root experiments/G4_MULTI_ARC_ABLATION_FINAL_1024/runs \
        --tag-prefix c1
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
ROOT = EXP.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib                      # noqa: E402
matplotlib.use('Agg')
import matplotlib.pyplot as plt        # noqa: E402
import numpy as np                     # noqa: E402

AXES = [('d56', 'candidate evaluations  d56_candidate_evals', 1.0),
        ('r3d', 'true-3D route evaluations  route_3d_checks', 1.0),
        ('wall', 'search wall clock  (s)', 1.0)]
COLORS = {'on': 'tab:blue', 'off': 'tab:red'}
LABELS = {'on': 'MultiArc-ON', 'off': 'MultiArc-OFF'}
LABELS_BY_KEY = {'d56': 'candidate evaluations  d56_candidate_evals',
                 'r3d': 'true-3D route evaluations  route_3d_checks',
                 'wall': 'search wall clock  (s)'}
START = 3967


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8-sig'))


def curve_of(run_dir):
    stats = read_json(Path(run_dir) / 'strategy_stats.json', {}) or {}
    extra = stats.get('extra') or {}
    records = extra.get('history_records') or []
    start = int(extra.get('start_crossings') or START)
    points = dict(d56=[0.0], r3d=[0.0], wall=[0.0], total=[float(start)])
    for record in records:
        points['d56'].append(float(record.get('d56') or 0))
        points['r3d'].append(float(record.get('r3d') or 0))
        points['wall'].append(float(record.get('wall') or 0))
        points['total'].append(float(record.get('total') or start))
    return {key: np.asarray(value, dtype=float) for key, value in points.items()}


def step_value(x, y, grid):
    """Right-continuous step interpolation of a monotone decreasing staircase."""
    idx = np.searchsorted(x, grid, side='right') - 1
    idx = np.clip(idx, 0, len(y) - 1)
    return y[idx]


def collect(runs_root, tag_prefix):
    runs = defaultdict(dict)
    for arm_dir in sorted(p for p in Path(runs_root).iterdir() if p.is_dir()):
        arm = arm_dir.name
        for run_dir in sorted(p for p in arm_dir.iterdir() if p.is_dir()):
            if tag_prefix and not run_dir.name.startswith(tag_prefix):
                continue
            meta = read_json(run_dir / 'run_meta.json', {}) or {}
            summary = read_json(run_dir / 'summary.json', {}) or {}
            ledger = read_json(run_dir / 'budget_ledger.json', {}) or {}
            if not summary:
                continue
            runs[arm][int(meta.get('seed') or 0)] = dict(
                dir=str(run_dir), seed=int(meta.get('seed') or 0),
                curve=curve_of(run_dir),
                final=int(summary.get('crossings') or summary.get('crossings', 0)
                          or 0),
                d56=float(ledger.get('d56_candidate_evals') or 0),
                r3d=float(ledger.get('route_3d_checks') or 0),
                wall=float(ledger.get('wall_seconds') or 0))
    return runs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs-root', default=str(EXP / 'runs'))
    parser.add_argument('--tag-prefix', default='c1')
    parser.add_argument('--figures', default=str(EXP / 'figures'))
    parser.add_argument('--tables', default=str(EXP / 'tables'))
    parser.add_argument('--title', default='')
    parser.add_argument('--stem', default='fig_search_curves')
    args = parser.parse_args(argv)

    runs = collect(args.runs_root, args.tag_prefix)
    if not runs:
        print('no runs found under %s' % args.runs_root)
        return 1
    figures = Path(args.figures)
    tables = Path(args.tables)
    figures.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)

    # ---------------- common grids ----------------
    grids = {}
    for key, _label, _scale in AXES:
        top = max(float(np.max(run['curve'][key])) for arm in runs
                  for run in runs[arm].values() if len(run['curve'][key]))
        grids[key] = np.linspace(0.0, top, 241)

    matched = []
    for key, label, _scale in AXES:
        grid = grids[key]
        for arm in sorted(runs):
            seed_curves = [step_value(run['curve'][key], run['curve']['total'], grid)
                           for run in runs[arm].values()]
            if not seed_curves:
                continue
            stack = np.vstack(seed_curves)
            mean = stack.mean(axis=0)
            for index, value in enumerate(grid):
                matched.append(dict(
                    axis=key, arm=arm, x=round(float(value), 3),
                    crossings_mean=round(float(mean[index]), 4),
                    crossings_min=round(float(stack[:, index].min()), 4),
                    crossings_max=round(float(stack[:, index].max()), 4),
                    n_seeds=int(stack.shape[0])))
    with (tables / 'search_curve_matched.csv').open('w', encoding='utf-8',
                                                    newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(matched[0].keys()))
        writer.writeheader()
        writer.writerows(matched)

    final_rows = []
    for arm in sorted(runs):
        for seed in sorted(runs[arm]):
            run = runs[arm][seed]
            final_rows.append(dict(arm=arm, seed=seed, final_crossings=run['final'],
                                   d56_candidate_evals=run['d56'],
                                   route_3d_checks=run['r3d'],
                                   wall_seconds=run['wall'],
                                   run_dir=run['dir']))
    with (tables / 'search_curve_final.csv').open('w', encoding='utf-8',
                                                  newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(final_rows[0].keys()))
        writer.writeheader()
        writer.writerows(final_rows)

    # ---------------- figure 1: three axes ----------------
    fig, axes = plt.subplots(1, 3, figsize=(16.5, 4.9))
    for panel, (key, label, _scale) in enumerate(AXES):
        axis = axes[panel]
        grid = grids[key]
        for arm in ('on', 'off'):
            if arm not in runs:
                continue
            for seed in sorted(runs[arm]):
                curve = runs[arm][seed]['curve']
                axis.step(curve[key], curve['total'], where='post',
                          color=COLORS[arm], alpha=0.30, linewidth=1.0)
            stack = np.vstack([step_value(runs[arm][seed]['curve'][key],
                                          runs[arm][seed]['curve']['total'], grid)
                               for seed in sorted(runs[arm])])
            axis.plot(grid, stack.mean(axis=0), color=COLORS[arm], linewidth=2.4,
                      label='%s (n=%d seeds, bold = mean)' % (LABELS[arm],
                                                              stack.shape[0]))
            axis.fill_between(grid, stack.min(axis=0), stack.max(axis=0),
                              color=COLORS[arm], alpha=0.10, step='post')
        axis.axhline(START, color='0.35', linestyle='--', linewidth=1.2,
                     label='common start = %d' % START)
        axis.set_xlabel(label)
        axis.set_ylabel('same-plane crossing events')
        axis.grid(alpha=0.25)
        axis.set_ylim(1200, 4100)
    axes[0].legend(loc='upper right', fontsize=8)
    title = args.title or ('Strict common start (3967) -- equal counted budget'
                           ' (d56=24000)')
    fig.suptitle(title, fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    out1 = figures / ('%s.png' % args.stem)
    fig.savefig(out1, dpi=170)
    plt.close(fig)

    # ---------------- figure 2: normalised comparison ----------------
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.8))
    for panel, key in enumerate(('d56', 'r3d')):
        axis = axes[panel]
        grid = grids[key]
        for arm in ('on', 'off'):
            if arm not in runs:
                continue
            stack = np.vstack([step_value(runs[arm][seed]['curve'][key],
                                          runs[arm][seed]['curve']['total'], grid)
                               for seed in sorted(runs[arm])])
            axis.plot(grid, stack.mean(axis=0), color=COLORS[arm], linewidth=2.2,
                      label=LABELS[arm])
            axis.fill_between(grid, stack.min(axis=0), stack.max(axis=0),
                              color=COLORS[arm], alpha=0.12, step='post')
        axis.axhline(START, color='0.35', linestyle='--', linewidth=1.1)
        axis.set_xlabel(LABELS_BY_KEY[key])
        axis.set_ylabel('same-plane crossing events')
        axis.grid(alpha=0.25)
        axis.legend(loc='upper right')
    fig.suptitle('Cost-normalised search progress: crossings vs candidate '
                 'evaluations (left) and vs true-3D route evaluations (right)',
                 fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    out2 = figures / ('%s_norm.png' % args.stem)
    fig.savefig(out2, dpi=170)
    plt.close(fig)
    print('wrote %s and %s' % (out1, out2))
    print('matched grid rows: %d' % len(matched))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
