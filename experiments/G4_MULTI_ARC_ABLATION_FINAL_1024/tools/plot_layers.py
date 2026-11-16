# -*- coding: utf-8 -*-
"""Per-physical-height crossing distribution of several route states.

Produces the layer table and the grouped bar chart used in the report.  The 21
historical layer *images* are NOT regenerated here (they are archived and
unchanged); this figure is the quantitative per-height comparison the new
experiment needs.

Usage::

    python .../tools/plot_layers.py \
        --state start=.../01_convert \
        --state on=runs/on/c1_on_20261104/best_valid \
        --state off=runs/off/c1_off_20261104/best_valid
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
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

from four_side_1024.fanout1024.reheight21 import model as M  # noqa: E402


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8-sig'))


def plane_table(run_dir):
    # ``best_valid/`` holds the routes only; the engine writes the crossing
    # statistics next to it
    stats = read_json(Path(run_dir) / 'crossing_stats.json')
    if stats is None:
        stats = read_json(Path(run_dir).parent / 'crossing_stats.json', {}) or {}
    rows = {}
    for plane in stats.get('planes') or ():
        rows[round(float(plane['z_mm']), 6)] = dict(
            z_mm=round(float(plane['z_mm']), 6),
            label=str(plane.get('label') or ''),
            crossings=int(plane.get('crossings') or 0),
            pairs=int(plane.get('crossing_pairs') or 0),
            routes=int(plane.get('routes') or 0))
    return rows


def label_for(z):
    for plane_id in M.PLANE_IDS:
        if abs(float(M.plane_z(plane_id)) - float(z)) < 1e-9:
            return str(M.plane_label(plane_id))
    return 'z%+.3f' % float(z)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', action='append', default=[],
                        help='name=run_dir')
    parser.add_argument('--figures', default=str(EXP / 'figures'))
    parser.add_argument('--tables', default=str(EXP / 'tables'))
    parser.add_argument('--stem', default='fig_per_layer_crossings')
    args = parser.parse_args(argv)
    states = []
    for item in args.state:
        name, _, path = str(item).partition('=')
        if not path:
            raise SystemExit('bad --state %r (expected name=dir)' % item)
        states.append((name.strip(), path.strip()))
    if not states:
        raise SystemExit('at least one --state is required')

    tables = {name: plane_table(path) for name, path in states}
    heights = sorted(set().union(*[set(table) for table in tables.values()]))
    rows = []
    for z in heights:
        row = dict(z_mm=z, label=label_for(z))
        for name, table in tables.items():
            row[name] = int(table.get(z, {}).get('crossings', 0))
        rows.append(row)

    out_csv = Path(args.tables) / ('%s.csv' % args.stem)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    fig, ax = plt.subplots(figsize=(15.5, 5.4))
    n = len(states)
    width = 0.8 / n
    index = np.arange(len(rows))
    colors = ['#6d4c41', '#1565c0', '#c62828', '#2e7d32', '#6a1b9a']
    for offset, (name, _path) in enumerate(states):
        values = [row[name] for row in rows]
        ax.bar(index + (offset - (n - 1) / 2) * width, values, width,
               label='%s (%d)' % (name, sum(values)),
               color=colors[offset % len(colors)])
    ax.set_xticks(index)
    ax.set_xticklabels(['%s\n%+.2f' % (row['label'], row['z_mm']) for row in rows],
                       fontsize=7.5, rotation=90)
    ax.set_ylabel('same-plane crossing events')
    ax.set_xlabel('physical height (label / z in mm)')
    ax.set_title('Crossings per physical height (19 body + 2 interface heights)')
    ax.legend()
    ax.grid(axis='y', alpha=0.25)
    fig.tight_layout()
    out_png = Path(args.figures) / ('%s.png' % args.stem)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=165)
    plt.close(fig)
    print('wrote %s and %s' % (out_png, out_csv))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
