# -*- coding: utf-8 -*-
"""Mechanism figure of the 2R threshold in the frozen D56 candidate grammar.

Reads ``tables/param_2r_travel90.json`` / ``param_2r_travel55.json`` (written by
``param_2r.py``) and draws

* left   -- lateral occupancy (x span) of the best candidate vs the lateral
            offset d, MultiArc-ON vs OFF, with the 2R = 30 mm threshold
* middle -- path length of the best candidate vs d
* right  -- number of feasible candidates for a transfer shorter than 4R
            (travel = 55 mm), i.e. the feasibility cliff of the ablated grammar

Usage::

    python .../tools/plot_2r.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
R15 = 15.0


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def series(payload, arm, key):
    xs, ys = [], []
    for row in payload['summary']:
        if row['arm'] != arm:
            continue
        # the best *compact* candidate of the grammar = smallest bounding box
        if key == 'greedy_x_span_mm':
            xs.append(row['offset_mm'])
            ys.append(row['greedy_x_span_mm'])
        elif key == 'greedy_length_mm':
            xs.append(row['offset_mm'])
            ys.append(row['greedy_length_mm'])
        elif key == 'n_candidates':
            xs.append(row['offset_mm'])
            ys.append(row['n_candidates'])
        elif key == 'smallest_box':
            xs.append(row['offset_mm'])
            ys.append((row['smallest_box_area_mm2'] or 0) ** 0.5)
    return xs, ys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tables', default=str(EXP / 'tables'))
    parser.add_argument('--figures', default=str(EXP / 'figures'))
    args = parser.parse_args(argv)
    tables = Path(args.tables)
    figures = Path(args.figures)
    figures.mkdir(parents=True, exist_ok=True)

    long90 = load(tables / 'param_2r_travel90.json')
    short55 = load(tables / 'param_2r_travel55.json')

    fig, axes = plt.subplots(1, 3, figsize=(15.5, 4.6))

    ax = axes[0]
    for arm, color, label in (('ON', 'tab:blue', 'MultiArc-ON'),
                              ('OFF', 'tab:red', 'MultiArc-OFF')):
        xs, ys = series(long90, arm, 'greedy_x_span_mm')
        ax.plot(xs, ys, 'o-', color=color, label=label)
    ax.axvline(2 * R15, color='0.3', linestyle='--', linewidth=1.2)
    ax.text(2 * R15 + 0.8, ax.get_ylim()[1] * 0.92, '2R = 30 mm',
            fontsize=9, color='0.25')
    ax.set_xlabel('lateral offset d (mm)')
    ax.set_ylabel('lateral occupancy  x span (mm)')
    ax.set_title('(a) compactness: lateral footprint\n'
                 'canonical opposite transfer, travel 90 mm')
    ax.grid(alpha=0.25)
    ax.legend(fontsize=9)

    ax = axes[1]
    for arm, color, label in (('ON', 'tab:blue', 'MultiArc-ON'),
                              ('OFF', 'tab:red', 'MultiArc-OFF')):
        xs, ys = series(long90, arm, 'greedy_length_mm')
        ax.plot(xs, ys, 'o-', color=color, label=label)
    ax.axvline(2 * R15, color='0.3', linestyle='--', linewidth=1.2)
    ax.set_xlabel('lateral offset d (mm)')
    ax.set_ylabel('path length of the body (mm)')
    ax.set_title('(b) path length of the chosen candidate\n'
                 '(same endpoints, same R15, same travel)')
    ax.grid(alpha=0.25)
    ax.legend(fontsize=9)

    ax = axes[2]
    for arm, color, label in (('ON', 'tab:blue', 'MultiArc-ON'),
                              ('OFF', 'tab:red', 'MultiArc-OFF')):
        xs, ys = series(short55, arm, 'n_candidates')
        ax.plot(xs, ys, 'o-', color=color, label=label)
    ax.axvline(2 * R15, color='0.3', linestyle='--', linewidth=1.2)
    ax.set_xlabel('lateral offset d (mm)')
    ax.set_ylabel('feasible candidates built')
    ax.set_title('(c) feasibility cliff: travel 55 mm < 4R = 60 mm\n'
                 'OFF has *no* legal body for d <= 2R')
    ax.set_ylim(-8, None)
    ax.grid(alpha=0.25)
    ax.legend(fontsize=9)

    fig.suptitle('Planar geometry of the sub-2R shift inside the frozen D56 '
                 'grammar (R = 15 mm, exact R15 arcs only)', fontsize=11.5)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    out = figures / 'fig_2R_mechanism.png'
    fig.savefig(out, dpi=170)
    plt.close(fig)
    print('wrote %s' % out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
