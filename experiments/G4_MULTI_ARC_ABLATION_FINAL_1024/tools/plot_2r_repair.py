# -*- coding: utf-8 -*-
"""Per-route crossing change of the 197 converted routes vs their 2R offset.

Reads ``tables/stage0_per_route.csv`` (lateral offset ``|bx|`` of the inherited
geometry and the Stage-0 commit delta) and
``tables/repair_<tag>_per_route.csv`` (per-route crossings in the common start,
the ON final and the OFF final).

The figure is the *real-route* counterpart of the parametric 2R study: it shows
that the ON advantage is concentrated exactly where the ablated grammar has no
compact candidate, i.e. ``|bx| <= 2R``.

Usage::

    python .../tools/plot_2r_repair.py --tag c1_20261104
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np               # noqa: E402

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
R15 = 15.0


def read_csv(path):
    with Path(path).open('r', encoding='utf-8') as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tables', default=str(EXP / 'tables'))
    parser.add_argument('--figures', default=str(EXP / 'figures'))
    parser.add_argument('--tag', default='c1_20261104')
    args = parser.parse_args(argv)
    tables = Path(args.tables)
    figures = Path(args.figures)
    figures.mkdir(parents=True, exist_ok=True)

    stage0 = {int(row['route_id']): row for row in
              read_csv(tables / 'stage0_per_route.csv')}
    repair = {int(row['route_id']): row for row in
              read_csv(tables / ('repair_%s_per_route.csv' % args.tag))}
    rows = []
    for rid, base in stage0.items():
        rep = repair.get(rid)
        if rep is None:
            continue
        offset = base.get('lateral_offset_mm')
        if not offset:
            continue
        rows.append(dict(route_id=rid, offset=float(offset),
                          delta_on=int(rep['delta_on']),
                          delta_off=int(rep['delta_off']),
                          multi_on=rep['multi_arc_on'] == 'True'))
    if not rows:
        raise SystemExit('no overlapping rows; run analyze_stage0 and analyze_repair first')

    offsets = np.array([row['offset'] for row in rows])
    d_on = np.array([row['delta_on'] for row in rows])
    d_off = np.array([row['delta_off'] for row in rows])
    below = offsets < 2 * R15 - 1e-9

    fig, axes = plt.subplots(1, 2, figsize=(13.2, 4.8))
    ax = axes[0]
    rng = np.random.default_rng(7)
    jitter = rng.uniform(-0.35, 0.35, size=len(offsets))
    ax.scatter(offsets + jitter, d_off, s=26, c='tab:red', alpha=0.55,
               label='MultiArc-OFF', marker='o')
    ax.scatter(offsets + jitter, d_on, s=26, c='tab:blue', alpha=0.55,
               label='MultiArc-ON', marker='^')
    ax.axhline(0.0, color='0.4', linewidth=1.0)
    ax.axvline(2 * R15, color='0.25', linestyle='--', linewidth=1.2)
    ax.set_xlim(0.0, 62.0)
    ax.text(2 * R15 + 0.6, ax.get_ylim()[0] * 0.85, '2R = 30 mm', fontsize=9,
            color='0.25')
    outside = int((offsets > 62.0).sum())
    if outside:
        ax.text(0.99, 0.97, '%d route(s) with |bx| > 62 mm omitted '
                '(adjacent-frame cases)' % outside,
                transform=ax.transAxes, ha='right', va='top', fontsize=7.5,
                color='0.35')
    ax.set_xlabel('lateral offset |bx| of the inherited geometry (mm)')
    ax.set_ylabel('per-route crossing change vs common start')
    ax.set_title('(a) 197 converted routes: crossing change per route\n'
                 '(negative = fewer crossings than the common start)')
    ax.grid(alpha=0.25)
    ax.legend(fontsize=9, loc='lower right')

    ax = axes[1]
    bins = [(0, 10), (10, 20), (20, 30), (30, 45), (45, 60)]
    labels = ['0-10', '10-20', '20-30', '30-45', '45-60']
    width = 0.38
    index = np.arange(len(bins))
    on_means, off_means, counts = [], [], []
    for low, high in bins:
        mask = (offsets >= low) & (offsets < high)
        counts.append(int(mask.sum()))
        on_means.append(float(d_on[mask].mean()) if mask.any() else 0.0)
        off_means.append(float(d_off[mask].mean()) if mask.any() else 0.0)
    ax.bar(index - width / 2, on_means, width, color='tab:blue', label='ON')
    ax.bar(index + width / 2, off_means, width, color='tab:red', label='OFF')
    span = max(1.0, max(abs(value) for value in on_means + off_means))
    for position, count in enumerate(counts):
        ax.text(position, 0.6, 'n=%d' % count, ha='center', va='bottom',
                fontsize=7.5, color='0.3')
    ax.set_ylim(-span * 1.05, span * 0.18)
    ax.axhline(0.0, color='0.4', linewidth=1.0)
    ax.set_xticks(index)
    ax.set_xticklabels(labels)
    ax.set_xlabel('lateral offset |bx| bin (mm)')
    ax.set_ylabel('mean per-route crossing change')
    ax.set_title('(b) mean change by offset bin (n annotated under each bar)')
    ax.grid(axis='y', alpha=0.25)
    ax.legend(fontsize=9)

    summary = dict(
        tag=args.tag, routes=len(rows),
        below_2R=dict(
            routes=int(below.sum()),
            mean_delta_on=round(float(d_on[below].mean()), 4),
            sum_delta_on=int(d_on[below].sum()),
            mean_delta_off=round(float(d_off[below].mean()), 4),
            sum_delta_off=int(d_off[below].sum()),
            restored_multi_arc=int(sum(1 for row, b in zip(rows, below)
                                       if b and row['multi_on']))),
        at_or_above_2R=dict(
            routes=int((~below).sum()),
            mean_delta_on=round(float(d_on[~below].mean()), 4),
            sum_delta_on=int(d_on[~below].sum()),
            mean_delta_off=round(float(d_off[~below].mean()), 4),
            sum_delta_off=int(d_off[~below].sum()),
            restored_multi_arc=int(sum(1 for row, b in zip(rows, below)
                                       if not b and row['multi_on']))),
        bins=[dict(low=low, high=high, n=counts[i],
                   mean_on=round(on_means[i], 4),
                   mean_off=round(off_means[i], 4))
              for i, (low, high) in enumerate(bins)])
    (figures / 'fig_2R_repair.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')
    fig.suptitle('Where the ON advantage comes from: the 197 converted routes, '
                 'per-route crossing change vs the inherited 2R offset',
                 fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    out = figures / 'fig_2R_repair.png'
    fig.savefig(out, dpi=165)
    plt.close(fig)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print('wrote %s' % out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
