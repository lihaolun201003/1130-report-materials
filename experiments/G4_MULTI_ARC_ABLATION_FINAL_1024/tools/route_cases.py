# -*- coding: utf-8 -*-
"""Representative real-route geometry cases (experiment 3.2).

Two families of cases are rendered, each from the *stored* geometry of the
states involved (never a redrawn sketch):

A. **Stage-0 conversion cases** -- the inherited G3 route (with its tangent
   two-arc short-S) versus the route the ablated grammar had to build instead,
   drawn on the same physical height with the same XY window.
B. **Strict common-start cases** -- the *same* route in the common 3967 start,
   in the ON final solution and in the OFF final solution, i.e. what the two
   grammars actually converged to from an identical starting geometry.

Route ids are resolved from the new results, not inherited from the old report:
the script always re-reads the per-route tables and picks the routes with the
largest measured effect (plus the requested named routes when they are still in
the converted set).

Usage::

    python .../tools/route_cases.py --on runs/on/c1_on_20261104/best_valid \
        --off runs/off/c1_off_20261104/best_valid
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
for path in (str(ROOT), str(HERE)):
    if path not in sys.path:
        sys.path.insert(0, path)

import matplotlib                      # noqa: E402
matplotlib.use('Agg')
import matplotlib.pyplot as plt        # noqa: E402
import numpy as np                     # noqa: E402

import geo_plots as G                  # noqa: E402

G3_DIR = ROOT / 'outputs' / 'manual_c4_new_connectivity' / 'XYZ_JOINT_G123_1024' / 'best_valid'
OLD_REPO = Path('C:/Users/lihao/Desktop/Graduation Project/work/1130-report-materials/'
                'G4_MULTI_ARC_ABLATION_1024')
CONVERT_DIR = OLD_REPO / 'no_multi_arc' / '01_convert'


def read_csv(path):
    with Path(path).open('r', encoding='utf-8') as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def body_z(run, rid):
    """Physical height of the largest body flat of one route (m metres -> mm)."""
    route = run['routes'][int(rid)]
    best = None
    for z_mm, prims in G.flat_chains(route):
        length = G.chain_length(prims)
        if best is None or length > best[1]:
            best = (z_mm, length)
    return None if best is None else round(float(best[0]), 6)


def panel(ax, run, rid, z_mm, x0, x1, y0, y1, color, title,
          highlight_color=None):
    rid = int(rid)
    info = G.route_summary(run['routes'][rid], z_mm)
    events = G.events_for_route(run, rid)
    in_window = [event for event in events
                 if abs(float(event.get('z_mm') or 0.0) - z_mm) <= 1e-9
                 and x0 <= float(event.get('x_mm') or -1) <= x1
                 and y0 <= float(event.get('y_mm') or -1) <= y1]
    G.draw_window(ax, run, z_mm, x0, x1, y0, y1,
                  highlight={rid: highlight_color or color})
    ax.set_title('%s\nroute %d @ z=%+.2f mm  --  %d arcs, %d lines, '
                 '%.1f mm, %d crossings in window'
                 % (title, rid, z_mm, info['n_arcs'], info['n_lines'],
                    info['length_mm'], len(in_window)), fontsize=9.5)
    ax.set_xlabel('X (mm)')
    ax.set_ylabel('Y (mm)')
    return info, len(in_window)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--on', default=None, help='ON best_valid dir')
    parser.add_argument('--off', default=None, help='OFF best_valid dir')
    parser.add_argument('--start', default=str(CONVERT_DIR),
                        help='common start dir (3967)')
    parser.add_argument('--tables', default=str(EXP / 'tables'))
    parser.add_argument('--figures', default=str(EXP / 'figures'))
    parser.add_argument('--named', default='25,36,115')
    args = parser.parse_args(argv)

    figures = Path(args.figures)
    figures.mkdir(parents=True, exist_ok=True)
    rows = read_csv(Path(args.tables) / 'stage0_per_route.csv')
    by_id = {int(row['route_id']): row for row in rows}

    named = [int(part) for part in str(args.named).split(',') if part.strip()]
    sub = [row for row in rows if row['below_2R'] == 'True']
    ge = [row for row in rows if row['below_2R'] == 'False']
    worst = max(sub, key=lambda row: int(row['delta_commit']))
    control = min(ge, key=lambda row: abs(int(row['delta_commit'])))
    picks = []
    for rid in named:
        if rid in by_id and rid not in [p[0] for p in picks]:
            picks.append((rid, 'named sub-2R case'))
    if int(worst['route_id']) not in [p[0] for p in picks]:
        picks.append((int(worst['route_id']), 'largest measured Stage-0 cost'))
    picks.append((int(control['route_id']), '>=2R control (no cost)'))

    g3 = G.load_run(G3_DIR)
    converted = G.load_run(CONVERT_DIR)
    manifest = []
    for rid, note in picks:
        row = by_id[rid]
        za, zb = body_z(g3, rid), body_z(converted, rid)
        bounds = []
        for run, z in ((g3, za), (converted, zb)):
            box = G.route_bounds(run['routes'][rid], z)
            if box:
                bounds.append(box)
        if not bounds:
            continue
        x0 = min(b[0] for b in bounds)
        x1 = max(b[1] for b in bounds)
        y0 = min(b[2] for b in bounds)
        y1 = max(b[3] for b in bounds)
        # keep a readable aspect ratio
        width = max(12.0, x1 - x0)
        height = max(12.0, y1 - y0)
        side = max(width, height)
        cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
        x0, x1 = max(0.0, cx - side / 2), min(G.BOARD, cx + side / 2)
        y0, y1 = max(0.0, cy - side / 2), min(G.BOARD, cy + side / 2)

        fig, axes = plt.subplots(1, 2, figsize=(12.4, 6.0))
        info_a, n_a = panel(axes[0], g3, rid, za, x0, x1, y0, y1,
                            G.COLOR_HL_ON,
                            'G3 inherited: planar multi-arc allowed')
        info_b, n_b = panel(axes[1], converted, rid, zb, x0, x1, y0, y1,
                            G.COLOR_HL_OFF,
                            'Stage-0: multi-arc removed (%s)' % row['family'])
        fig.suptitle(
            'route %d  %s  |  lateral offset |bx| = %s mm (%s 2R)  |  '
            'length %.1f -> %.1f mm  |  per-route crossings %s -> %s  |  '
            'commit delta %s  |  z %+.2f -> %+.2f mm'
            % (rid, note, row['lateral_offset_mm'],
               'below' if row['below_2R'] == 'True' else 'above',
               float(row['length_before_mm']), float(row['length_after_mm']),
               row['per_route_events_before'], row['per_route_events_after'],
               row['delta_commit'], za, zb), fontsize=10)
        fig.tight_layout(rect=(0, 0, 1, 0.92))
        out = figures / ('fig_case_stage0_route%04d.png' % rid)
        fig.savefig(out, dpi=150)
        plt.close(fig)
        manifest.append(dict(kind='stage0', route_id=rid, note=note,
                             file=out.name, z_before=za, z_after=zb,
                             crossings_in_window=[n_a, n_b],
                             length_before=float(row['length_before_mm']),
                             length_after=float(row['length_after_mm']),
                             delta_commit=int(row['delta_commit']),
                             lateral_offset_mm=float(row['lateral_offset_mm']),
                             below_2R=row['below_2R'] == 'True',
                             family=row['family']))
        print('wrote %s' % out)

    # ---------------- strict common-start cases ----------------
    if args.on and args.off:
        on = G.load_run(args.on)
        off = G.load_run(args.off)
        start = G.load_run(args.start)
        # rank routes by the crossing difference between the OFF and ON finals
        def per_route(run):
            return dict(run.get('per_route') or {})
        c_on, c_off, c_start = per_route(on), per_route(off), per_route(start)
        ranked = sorted(c_on, key=lambda rid: (c_off.get(rid, 0) - c_on.get(rid, 0)),
                        reverse=True)
        chosen = [rid for rid in ranked
                  if c_start.get(rid, 0) >= 10 and c_off.get(rid, 0) >= 10][:2]
        for rid in chosen:
            za, zb = body_z(on, rid), body_z(off, rid)
            zs = body_z(start, rid)
            bounds = []
            for run, z in ((start, zs), (on, za), (off, zb)):
                box = G.route_bounds(run['routes'][rid], z)
                if box:
                    bounds.append(box)
            if not bounds:
                continue
            x0 = min(b[0] for b in bounds)
            x1 = max(b[1] for b in bounds)
            y0 = min(b[2] for b in bounds)
            y1 = max(b[3] for b in bounds)
            side = max(14.0, x1 - x0, y1 - y0)
            cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
            x0, x1 = max(0.0, cx - side / 2), min(G.BOARD, cx + side / 2)
            y0, y1 = max(0.0, cy - side / 2), min(G.BOARD, cy + side / 2)
            fig, axes = plt.subplots(1, 3, figsize=(17.8, 6.0))
            panel(axes[0], start, rid, zs, x0, x1, y0, y1, '#6d4c41',
                  'common start (3967): inherited ablated geometry')
            panel(axes[1], on, rid, za, x0, x1, y0, y1, G.COLOR_HL_ON,
                  'MultiArc-ON final')
            panel(axes[2], off, rid, zb, x0, x1, y0, y1, G.COLOR_HL_OFF,
                  'MultiArc-OFF final')
            fig.suptitle(
                'route %d  |  per-route crossings  start %d -> ON %d -> OFF %d  |'
                '  z  start %+.2f  ON %+.2f  OFF %+.2f mm'
                % (rid, c_start.get(rid, 0), c_on.get(rid, 0), c_off.get(rid, 0),
                   zs, za, zb), fontsize=10)
            fig.tight_layout(rect=(0, 0, 1, 0.92))
            out = figures / ('fig_case_common_start_route%04d.png' % rid)
            fig.savefig(out, dpi=150)
            plt.close(fig)
            manifest.append(dict(kind='common_start', route_id=rid,
                                 file=out.name,
                                 crossings=dict(start=c_start.get(rid, 0),
                                                on=c_on.get(rid, 0),
                                                off=c_off.get(rid, 0)),
                                 z=dict(start=zs, on=za, off=zb)))
            print('wrote %s' % out)

    (figures / 'cases_manifest.json').write_text(
        json.dumps(dict(schema='g4_multi_arc_cases_v1', cases=manifest),
                   ensure_ascii=False, indent=1), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
