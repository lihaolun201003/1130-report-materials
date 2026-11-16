# -*- coding: utf-8 -*-
"""Figure / table factory of the G4 multi-arc ablation (1024 channels).

Reuses the archived G4 plotting system (``g4/plots_g4.py``: ``Layout``,
``layer_stats``, ``_draw_layer_board``, ``plot_layer_suite``,
``plot_compare_suite``) and adds only the figures the ablation needs:

* per-physical-height crossing-count bar chart (both arms),
* crossing-hotspot zoom-ins (both arms),
* complete 3D overview of the whole 1024-route layout (both arms),
* typical-route local XY geometry contrast (multi-arc vs single-arc grammar),
* per-height / per-event CSV tables.

Usage::

    python make_report_artifacts.py --baseline <g4 best dir> \
        --nomat <no_multi_arc final dir> --out <experiment root> [--g3 <dir>]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt                       # noqa: E402
import numpy as np                                     # noqa: E402
from matplotlib.collections import LineCollection      # noqa: E402
from matplotlib.lines import Line2D                    # noqa: E402
from matplotlib.patches import Rectangle               # noqa: E402
from mpl_toolkits.mplot3d.art3d import Line3DCollection  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024 import layer2d as L2                     # noqa: E402
from four_side_1024.fanout1024.xyzrouter import visualize as V          # noqa: E402
from four_side_1024.fanout1024.xyzrouter.g4 import paths as GP          # noqa: E402
from four_side_1024.fanout1024.xyzrouter.g4 import plots_g4 as PG       # noqa: E402

DPI = 140
BOARD = 150.0
COLORS = dict(baseline='#1565c0', nomat='#c62828', multi='#ff6f00',
              arc='#00838f', line='#90a4ae', cross='#e53935',
              transition='#6a1b9a', board='#37474f', grid='#eceff1')


def _write_csv(path, rows, fieldnames=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    if not rows:
        path.write_text('', encoding='utf-8')
        return path
    fieldnames = fieldnames or list(rows[0].keys())
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames,
                                extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    return path


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1,
                               default=str), encoding='utf-8')
    return path


def _rel(path):
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except Exception:                                       # noqa: BLE001
        return str(path)


# --------------------------------------------------------------------------- #
# 1. per-height crossing bar chart
# --------------------------------------------------------------------------- #
def per_layer_bar(layouts, out_path, title, dpi=DPI):
    rows = {name: PG.all_layer_stats(layout) for name, layout in layouts.items()}
    keys = PG.HEIGHT_KEYS
    labels = ['%s\n%+.2f' % (PG.HEIGHT_BY_Z[k]['label'],
                             PG.HEIGHT_BY_Z[k]['z_mm']) for k in keys]
    width = 0.8 / max(1, len(layouts))
    fig, axes = plt.subplots(1, 2, figsize=(16.4, 7.2),
                             gridspec_kw=dict(width_ratios=[2.35, 1.0]))
    ax = axes[0]
    positions = np.arange(len(keys))
    palette = [COLORS['baseline'], COLORS['nomat'], '#2e7d32']
    for index, (name, stats) in enumerate(rows.items()):
        values = [row['crossings'] for row in stats]
        offset = (index - (len(rows) - 1) / 2.0) * width
        bars = ax.bar(positions + offset, values, width=width * 0.94,
                      label='%s (%d)' % (name, sum(values)),
                      color=palette[index % len(palette)], alpha=0.88)
        for bar, value in zip(bars, values):
            if value:
                ax.text(bar.get_x() + bar.get_width() / 2.0,
                        bar.get_height() + 0.8, str(int(value)),
                        ha='center', va='bottom', fontsize=5.6,
                        rotation=90)
    ax.set_xticks(positions)
    ax.set_xticklabels(labels, fontsize=6.4, rotation=90)
    ax.set_ylabel('real same-height crossing events')
    ax.set_title('crossing events per physical height (exact z match)',
                 fontsize=10.5)
    ax.legend(fontsize=8.2, framealpha=0.95)
    ax.grid(axis='y', color='#e0e0e0', linewidth=0.5)
    ax.set_axisbelow(True)

    ax2 = axes[1]
    first = list(rows)[0]
    base = [row['crossings'] for row in rows[first]]
    for index, name in enumerate(list(rows)[1:], 1):
        values = [row['crossings'] for row in rows[name]]
        delta = [v - b for v, b in zip(values, base)]
        ax2.barh(positions, delta, height=0.62,
                 color=COLORS['nomat'], alpha=0.85,
                 label='%s - %s' % (name, first))
        for y, value in zip(positions, delta):
            if value:
                ax2.text(value, y, ' %+d' % value, va='center',
                         ha='left' if value > 0 else 'right', fontsize=5.6)
    ax2.axvline(0.0, color='#37474f', linewidth=0.8)
    ax2.set_yticks(positions)
    ax2.set_yticklabels([PG.HEIGHT_BY_Z[k]['label'] for k in keys],
                        fontsize=6.4)
    ax2.invert_yaxis()
    ax2.set_xlabel('crossing delta (events)')
    ax2.set_title('per-height difference', fontsize=10.5)
    ax2.legend(fontsize=8.0)
    ax2.grid(axis='x', color='#e0e0e0', linewidth=0.5)
    ax2.set_axisbelow(True)

    fig.suptitle(title, fontsize=12.5, y=0.99)
    fig.text(0.5, 0.005,
             'counts recomputed from the accepted routes_l3d.json real '
             'primitives and crossing_stats.json events (exact physical z)',
             ha='center', fontsize=6.8, color='#546e7a')
    fig.tight_layout(rect=(0, 0.022, 1, 0.965))
    fig.savefig(out_path, dpi=dpi, facecolor='white')
    plt.close(fig)
    return out_path


# --------------------------------------------------------------------------- #
# 2. crossing-hotspot zoom
# --------------------------------------------------------------------------- #
def _clusters(events, radius=8.0):
    """Greedy spatial clusters of crossing events of one height."""
    points = []
    for event in events:
        x = V._to_float(event.get('x_mm'))
        y = V._to_float(event.get('y_mm'))
        if x is None or y is None:
            continue
        points.append((x, y, event))
    clusters = []
    for x, y, event in points:
        placed = False
        for cluster in clusters:
            cx, cy = cluster['x'], cluster['y']
            if math.hypot(x - cx, y - cy) <= radius:
                cluster['events'].append(event)
                n = len(cluster['events'])
                cluster['x'] = (cluster['x'] * (n - 1) + x) / n
                cluster['y'] = (cluster['y'] * (n - 1) + y) / n
                placed = True
                break
        if not placed:
            clusters.append(dict(x=x, y=y, events=[event]))
    clusters.sort(key=lambda item: (-len(item['events']), item['y'], item['x']))
    return clusters


def hotspot_zoom(layout, out_dir, max_panels=4, top_heights=4, dpi=DPI):
    """Zoom into the densest crossing clusters of the densest heights."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = PG.all_layer_stats(layout)
    ranked = sorted(rows, key=lambda row: -row['crossings'])
    written = []
    for row in ranked[:top_heights]:
        key = round(float(row['z_mm']), 6)
        events = layout.events_by_key.get(key, ())
        clusters = _clusters(events)[:max_panels]
        for rank, cluster in enumerate(clusters, 1):
            cx, cy = cluster['x'], cluster['y']
            half = 22.0
            x0, x1 = max(0.0, cx - half), min(BOARD, cx + half)
            y0, y1 = max(0.0, cy - half), min(BOARD, cy + half)
            fig = plt.figure(figsize=(11.0, 5.4))
            ax = fig.add_axes([0.05, 0.09, 0.62, 0.83])
            info = fig.add_axes([0.70, 0.09, 0.285, 0.83])
            info.axis('off')
            ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=True,
                                   facecolor='#fafafa', edgecolor='none',
                                   zorder=0))
            prims = [entry for entry in layout.layer_prims.get(key, ())
                     if _inside(entry['xy'], x0, x1, y0, y1)]
            for kind, color, lw in (('line', COLORS['line'], 1.1),
                                    ('arc', COLORS['arc'], 2.0)):
                arrays = [entry['xy'] for entry in prims if entry['kind'] == kind]
                if arrays:
                    ax.add_collection(LineCollection(arrays, colors=color,
                                                     linewidths=lw, alpha=0.9,
                                                     zorder=3))
            points = [(V._to_float(e['x_mm']), V._to_float(e['y_mm']))
                      for e in events
                      if V._to_float(e.get('x_mm')) is not None]
            points = [p for p in points if x0 <= p[0] <= x1 and y0 <= p[1] <= y1]
            if points:
                arr = np.asarray(points)
                ax.scatter(arr[:, 0], arr[:, 1], marker='x', s=46,
                           c=COLORS['cross'], linewidths=1.1, zorder=10)
            ax.add_patch(Rectangle((cx - 1.2, cy - 1.2), 2.4, 2.4, fill=False,
                                   edgecolor='#b71c1c', linewidth=0.9,
                                   linestyle=(0, (3, 2)), zorder=11))
            ax.set_xlim(x0, x1)
            ax.set_ylim(y0, y1)
            ax.set_aspect('equal')
            ax.set_xlabel('X (mm)')
            ax.set_ylabel('Y (mm)')
            ax.set_title('%s  z=%+.2f mm  --  hotspot %d @ (%.1f, %.1f), '
                         '%d crossing events'
                         % (PG.HEIGHT_BY_Z[key]['label'],
                            PG.HEIGHT_BY_Z[key]['z_mm'], rank, cx, cy,
                            len(cluster['events'])), fontsize=10.0)
            routes = Counter()
            for event in cluster['events']:
                routes[int(event['route_a'])] += 1
                routes[int(event['route_b'])] += 1
            lines = ['window  %.1f x %.1f mm' % (x1 - x0, y1 - y0),
                     'height  %s  z = %+.2f mm'
                     % (PG.HEIGHT_BY_Z[key]['label'],
                        PG.HEIGHT_BY_Z[key]['z_mm']),
                     'events  %d' % len(cluster['events']),
                     'routes involved  %d' % len(routes), '',
                     'top routes in this hotspot:']
            for rid, count in routes.most_common(10):
                entry = layout.by_id.get(rid) or {}
                lines.append('  route %-4d  %d X' % (rid, count))
            lines.append('')
            lines.append('lines / arcs in window: %d / %d'
                         % (sum(1 for e in prims if e['kind'] == 'line'),
                            sum(1 for e in prims if e['kind'] == 'arc')))
            info.text(0.0, 1.0, '\n'.join(lines), transform=info.transAxes,
                      va='top', ha='left', fontsize=8.0, linespacing=1.45)
            fig.suptitle('%s  --  crossing hotspot zoom (%s)'
                         % (layout.name, _rel(layout.dir)), fontsize=11.5,
                         y=0.985)
            name = 'hotspot_%s_z%+.2f_%02d.png' % (
                PG.HEIGHT_BY_Z[key]['label'], PG.HEIGHT_BY_Z[key]['z_mm'], rank)
            fig.savefig(out_dir / name, dpi=dpi, facecolor='white')
            plt.close(fig)
            written.append(name)
    return written


def _inside(xy, x0, x1, y0, y1):
    arr = np.asarray(xy, dtype=float)
    return bool((arr[:, 0].max() >= x0) and (arr[:, 0].min() <= x1)
                and (arr[:, 1].max() >= y0) and (arr[:, 1].min() <= y1))


# --------------------------------------------------------------------------- #
# 3. complete 3D overview
# --------------------------------------------------------------------------- #
def _route3d_segments(route):
    """True 3-D polyline segments of one route (flat parts + real transitions)."""
    flat, trans = [], []
    for part in V._parts(route):
        if part.get('kind') == 'flat':
            z = V._to_float(part.get('z_mm'))
            if z is None:
                continue
            for prim in part.get('primitives') or ():
                xy = PG._prim_xy(prim)
                if xy is None:
                    continue
                arr = np.asarray(xy, dtype=float)
                for a, b in zip(arr[:-1], arr[1:]):
                    flat.append([(a[0], a[1], z), (b[0], b[1], z)])
        elif part.get('kind') == 'transition':
            xyz = V.sample_transition_xyz(part, 0.35)
            if xyz is None:
                continue
            for a, b in zip(xyz[:-1], xyz[1:]):
                trans.append([(a[0], a[1], a[2]), (b[0], b[1], b[2])])
    return flat, trans


def overview_3d(layouts, out_path, dpi=DPI, elev=26.0, azim=-58.0):
    """Side-by-side isometric 3-D view of every route of every arm."""
    count = max(1, len(layouts))
    fig = plt.figure(figsize=(8.6 * count, 8.2))
    zmin, zmax = -0.35, 0.65
    cmap = plt.get_cmap('viridis')
    for index, (name, layout) in enumerate(layouts.items(), 1):
        ax = fig.add_subplot(1, count, index, projection='3d')
        flat_all, trans_all = [], []
        for rid, route in layout.by_id.items():
            flat, trans = _route3d_segments(route)
            flat_all.extend(flat)
            trans_all.extend(trans)
        if flat_all:
            array = np.asarray(flat_all)
            zs = array[:, 0, 2]
            colors = cmap((zs - zmin) / (zmax - zmin))
            ax.add_collection3d(Line3DCollection(
                array, colors=colors, linewidths=0.30, alpha=0.55))
        if trans_all:
            ax.add_collection3d(Line3DCollection(
                np.asarray(trans_all), colors=COLORS['transition'],
                linewidths=0.22, alpha=0.28))
        ax.set_xlim(0, BOARD)
        ax.set_ylim(0, BOARD)
        ax.set_zlim(-0.45, 0.75)
        ax.set_xlabel('X (mm)', labelpad=2)
        ax.set_ylabel('Y (mm)', labelpad=2)
        ax.set_zlabel('z (mm)', labelpad=2)
        ax.view_init(elev=elev, azim=azim)
        ax.set_box_aspect((1, 1, 0.42))
        ax.tick_params(labelsize=6.0, pad=0)
        ax.set_title('%s\nroutes %d | crossings %d | flat arcs %d'
                     % (name, len(layout.by_id),
                        sum(row['crossings']
                            for row in PG.all_layer_stats(layout)),
                        sum(1 for _ in _iter_flat_arcs(layout))),
                     fontsize=9.5, pad=2)
        ax.text2D(0.02, 0.02,
                  'blue -> yellow = physical z (-0.35 ... +0.65 mm)\n'
                  'purple = real 3-D R15 S-transition',
                  transform=ax.transAxes, fontsize=6.4, color='#37474f')
    fig.suptitle('complete 3-D layout of the 1024-channel solution '
                 '(all routes, true geometry)', fontsize=12.5, y=0.97)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(out_path, dpi=dpi, facecolor='white')
    plt.close(fig)
    return out_path


def _iter_flat_arcs(layout):
    for key, prims in layout.layer_prims.items():
        for entry in prims:
            if entry['kind'] == 'arc':
                yield entry


# --------------------------------------------------------------------------- #
# 4. typical-route local geometry contrast
# --------------------------------------------------------------------------- #
def _local_multi_arc_ids(run_dir):
    payload = json.loads((Path(run_dir) / 'routes_l3d.json').read_text(
        encoding='utf-8'))
    out = {}
    for route in payload['routes']:
        regions = []
        for part in route.get('parts') or ():
            if part.get('kind') != 'flat':
                continue
            for region in L2.local_multi_arc_regions(
                    part.get('primitives') or []):
                regions.append(dict(z_mm=float(part['z_mm']), **region))
        if regions:
            out[int(route['route_id'])] = regions
    return out


def geometry_contrast(before, after, out_dir, picks=None, count=3, half=38.0,
                      dpi=DPI):
    """Local XY geometry of the same route in both grammars."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    before_multi = _local_multi_arc_ids(before.dir)
    after_multi = _local_multi_arc_ids(after.dir)
    candidates = []
    for rid, regions in sorted(before_multi.items()):
        if rid not in after_multi and rid in before.by_id and rid in after.by_id:
            candidates.append((rid, regions))
    if picks:
        candidates = [item for item in candidates if item[0] in set(picks)] or candidates
    written = []
    for rid, regions in candidates[:count]:
        region = regions[0]
        z = round(float(region['z_mm']), 6)
        start = region.get('start') or [0.0, 0.0]
        cx, cy = float(start[0]), float(start[1])
        x0, x1 = max(0.0, cx - half), min(BOARD, cx + half)
        y0, y1 = max(0.0, cy - half), min(BOARD, cy + half)
        fig = plt.figure(figsize=(13.2, 6.6))
        for index, (name, layout, highlight) in enumerate(
                (('G4 original (planar multi-arc)', before, True),
                 ('G4-NoMultiArc (single-arc grammar)', after, False))):
            ax = fig.add_axes([0.04 + index * 0.49, 0.09, 0.44, 0.80])
            ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0,
                                   facecolor='#fafafa', edgecolor='none'))
            prims = [entry for entry in layout.layer_prims.get(z, ())
                     if _inside(entry['xy'], x0, x1, y0, y1)]
            other = [entry['xy'] for entry in prims if entry['route_id'] != rid]
            if other:
                ax.add_collection(LineCollection(other, colors='#cfd8dc',
                                                 linewidths=0.9, alpha=0.95,
                                                 zorder=2))
            mine = [entry for entry in prims if entry['route_id'] == rid]
            for kind, color, lw in (('line', '#0d47a1', 1.8),
                                    ('arc', '#e65100', 2.6)):
                arrays = [entry['xy'] for entry in mine if entry['kind'] == kind]
                if arrays:
                    ax.add_collection(LineCollection(arrays, colors=color,
                                                     linewidths=lw, alpha=1.0,
                                                     zorder=6))
            events = [event for event in layout.events_by_key.get(z, ())
                      if V._to_float(event.get('x_mm')) is not None
                      and x0 <= V._to_float(event.get('x_mm')) <= x1
                      and y0 <= V._to_float(event.get('y_mm')) <= y1]
            if events:
                arr = np.asarray([(V._to_float(e['x_mm']),
                                   V._to_float(e['y_mm'])) for e in events])
                ax.scatter(arr[:, 0], arr[:, 1], marker='x', s=40,
                           c=COLORS['cross'], linewidths=1.0, zorder=10)
            ax.set_xlim(x0, x1)
            ax.set_ylim(y0, y1)
            ax.set_aspect('equal')
            ax.set_xlabel('X (mm)')
            ax.set_ylabel('Y (mm)')
            ax.set_title('%s\nroute %d @ z=%+.2f mm  --  %d R15 arcs, %d line '
                         'primitives in window'
                         % (name, rid, z,
                            sum(1 for entry in mine if entry['kind'] == 'arc'),
                            sum(1 for entry in mine if entry['kind'] == 'line')),
                         fontsize=9.4)
        fig.suptitle('same route, same physical height  --  real XY geometry '
                     'difference caused by the planar multi-arc ban '
                     '(local window %.0f x %.0f mm)'
                     % (x1 - x0, y1 - y0), fontsize=11.6, y=0.985)
        fig.text(0.5, 0.012, 'grey = neighbouring routes on the same height | '
                             'blue = straight lines | orange = exact R15 arcs | '
                             'red x = real crossing events', ha='center',
                 fontsize=7.2, color='#546e7a')
        name = 'geometry_contrast_route%04d_z%+.2f.png' % (rid, z)
        fig.savefig(out_dir / name, dpi=dpi, facecolor='white')
        plt.close(fig)
        written.append(name)
    return written


# --------------------------------------------------------------------------- #
# 5. tables
# --------------------------------------------------------------------------- #
def write_tables(baseline, after, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows_b = PG.all_layer_stats(baseline)
    rows_a = PG.all_layer_stats(after)
    compare = []
    for left, right in zip(rows_b, rows_a):
        compare.append(dict(
            layer_index=left['layer_index'], label=left['label'],
            z_mm=left['z_mm'],
            g4_crossings=left['crossings'], g4_pairs=left['crossing_pairs'],
            g4_routes=left['body_routes'],
            nomat_crossings=right['crossings'],
            nomat_pairs=right['crossing_pairs'],
            nomat_routes=right['body_routes'],
            delta_crossings=right['crossings'] - left['crossings'],
            delta_pairs=right['crossing_pairs'] - left['crossing_pairs']))
    _write_csv(out_dir / 'per_layer_crossings_compare.csv', compare)
    events = []
    for name, layout in (('G4_baseline', baseline), ('G4_NoMultiArc', after)):
        for index, event in enumerate(layout.events):
            events.append(dict(
                arm=name, event_index=index,
                z_mm=V._to_float(event.get('z_mm')),
                label=PG.HEIGHT_BY_Z.get(
                    round(float(event['z_mm']), 6), {}).get('label', ''),
                route_a=int(event['route_a']), route_b=int(event['route_b']),
                x_mm=V._to_float(event.get('x_mm')),
                y_mm=V._to_float(event.get('y_mm')),
                angle_deg=V._to_float(event.get('angle_deg'))))
    _write_csv(out_dir / 'crossing_events.csv', events)
    pairs = defaultdict(set)
    per_pair_count = Counter()
    for name, layout in (('G4_baseline', baseline), ('G4_NoMultiArc', after)):
        for event in layout.events:
            key = (name, round(float(event['z_mm']), 6),
                   tuple(sorted((int(event['route_a']), int(event['route_b'])))))
            pairs[name].add((round(float(event['z_mm']), 6),
                             tuple(sorted((int(event['route_a']),
                                           int(event['route_b']))))))
            per_pair_count[key] += 1
    rows = []
    for name in ('G4_baseline', 'G4_NoMultiArc'):
        for z, pair in sorted(pairs[name]):
            rows.append(dict(arm=name, z_mm=z,
                             label=PG.HEIGHT_BY_Z.get(z, {}).get('label', ''),
                             route_a=pair[0], route_b=pair[1],
                             events=per_pair_count[(name, z, pair)]))
    _write_csv(out_dir / 'unique_crossing_pairs_per_layer.csv', rows)
    return compare, len(events), len(rows)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', required=True,
                        help='archived G4 original best_valid dir')
    parser.add_argument('--nomat', required=True,
                        help='G4-NoMultiArc best_valid dir')
    parser.add_argument('--out', required=True, help='experiment root')
    parser.add_argument('--contrast-after', default=None,
                        help='layout used for the local geometry contrast '
                             '(default: the NoMultiArc final); the stage-0 '
                             'conversion output isolates the pure geometry '
                             'change at the same physical height')
    parser.add_argument('--contrast-picks', default='',
                        help='comma separated route ids for the contrast figure')
    parser.add_argument('--skip-heavy', action='store_true')
    args = parser.parse_args(argv)

    out = Path(args.out)
    figures = out / 'layer_figures'
    comparison = out / 'comparison'
    figures.mkdir(parents=True, exist_ok=True)
    comparison.mkdir(parents=True, exist_ok=True)
    manifest = dict(baseline=_rel(args.baseline), nomat=_rel(args.nomat),
                    written=[])

    before = PG.Layout(args.baseline, name='G4 original (1185)')
    after = PG.Layout(args.nomat, name='G4-NoMultiArc')
    print('[fig] baseline crossings', sum(r['crossings']
                                           for r in PG.all_layer_stats(before)))
    print('[fig] nomat    crossings', sum(r['crossings']
                                          for r in PG.all_layer_stats(after)))

    manifest['written'] += ['layer_figures/G4_baseline_suite',
                            'layer_figures/NoMultiArc_suite']
    PG.plot_layer_suite(args.baseline, figures / 'G4_baseline',
                        prefix='G4_baseline', title='G4 original (1185)')
    PG.plot_layer_suite(args.nomat, figures / 'NoMultiArc',
                        prefix='NoMultiArc', title='G4-NoMultiArc')

    before.name = 'G4 original (1185)'
    after.name = 'G4-NoMultiArc'
    path = per_layer_bar(dict([('G4 original', before),
                               ('G4-NoMultiArc', after)]),
                         figures / 'per_layer_crossings_bar.png',
                         'real same-height crossings per physical height  -- '
                         'G4 original vs G4-NoMultiArc')
    manifest['written'].append(_rel(path))

    hotspot_zoom(before, figures / 'hotspots_G4_baseline')
    hotspot_zoom(after, figures / 'hotspots_NoMultiArc')
    manifest['written'] += ['layer_figures/hotspots_G4_baseline',
                            'layer_figures/hotspots_NoMultiArc']

    PG.plot_compare_suite(args.baseline, args.nomat, comparison / 'per_layer',
                          prefix='compare',
                          before_name='G4 original (1185)',
                          after_name='G4-NoMultiArc')
    manifest['written'].append('comparison/per_layer')

    path = overview_3d(dict([('G4 original (1185)', before),
                             ('G4-NoMultiArc', after)]),
                       comparison / 'overview_3d_both_arms.png')
    manifest['written'].append(_rel(path))

    written = geometry_contrast(
        before,
        PG.Layout(args.contrast_after, name='G4-NoMultiArc (stage-0 conversion)')
        if args.contrast_after else after,
        comparison / 'local_geometry',
        picks=[int(v) for v in str(args.contrast_picks).split(',') if v.strip()])
    manifest['written'] += [_rel(comparison / 'local_geometry' / name)
                            for name in written]

    compare, n_events, n_pairs = write_tables(before, after, comparison)
    manifest['written'] += ['comparison/per_layer_crossings_compare.csv',
                            'comparison/crossing_events.csv',
                            'comparison/unique_crossing_pairs_per_layer.csv']
    manifest['tables'] = dict(rows=len(compare), crossing_events=n_events,
                              unique_pair_rows=n_pairs)
    _write_json(out / 'layer_figures' / 'figure_manifest.json', manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())


