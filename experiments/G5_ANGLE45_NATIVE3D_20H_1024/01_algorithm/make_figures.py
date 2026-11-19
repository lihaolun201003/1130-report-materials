# -*- coding: utf-8 -*-
"""G5 figures (report grade).  Every figure is generated from the real data files.

Labels are English on purpose: the default matplotlib font stack on this machine
has no CJK glyphs, and a figure full of tofu boxes is worse than English labels.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024.xyzrouter.g5 import model as G5

EXP = ROOT / 'experiments' / 'G5_ANGLE45_NATIVE3D_20H_1024'
BASE = ROOT / 'experiments' / 'COLD_START_20_HEIGHT_1024' / '10_best_valid'
FIG = EXP / '06_figures'
DPI = 150


def prim_points(prim, count=96):
    if prim['kind'] == 'line':
        return ([prim['p0'][0], prim['p1'][0]], [prim['p0'][1], prim['p1'][1]])
    angles = [prim['start_angle'] + prim['sweep'] * k / count
              for k in range(count + 1)]
    return ([prim['center'][0] + prim['radius'] * math.cos(a) for a in angles],
            [prim['center'][1] + prim['radius'] * math.sin(a) for a in angles])


def load(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def save(fig, name):
    FIG.mkdir(parents=True, exist_ok=True)
    path = FIG / name
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    print('  %s' % path.name, flush=True)
    return path


# --------------------------------------------------------------------- 1 / 10
def fig_histogram(base_viol, g5_viol=None):
    bins = [0, 5, 10, 20, 30, 40, 45, 60, 75, 90.001]
    events = base_viol['violations'] if 'violations' in base_viol else []
    base_hist = base_viol['histogram']
    fig, axis = plt.subplots(figsize=(9, 4.6))
    lows = [row['low_deg'] for row in base_hist]
    counts = [row['crossings'] for row in base_hist]
    colours = ['#c0392b' if row['below_45'] else '#2e86c1' for row in base_hist]
    axis.bar([str(row['low_deg']) + '-' + str(int(row['high_deg']))
              for row in base_hist], counts, color=colours)
    for index, value in enumerate(counts):
        axis.text(index, value + max(counts) * 0.01, str(value),
                  ha='center', fontsize=8)
    axis.set_title('G4 baseline crossing-angle distribution '
                   '(red = below 45 deg, %d of %d)'
                   % (base_viol['violations_below_45'], base_viol['crossings']))
    axis.set_xlabel('crossing angle bin (deg)')
    axis.set_ylabel('crossings')
    axis.grid(True, axis='y', alpha=0.3)
    return save(fig, 'fig01_g4_crossing_angle_histogram.png')


def fig_compare_histogram(base_viol, g5_rows):
    bins = [0, 5, 10, 20, 30, 40, 45, 60, 75, 90.001]
    base = [row['crossings'] for row in base_viol['histogram']]
    g5 = [0] * (len(bins) - 1)
    for row in g5_rows:
        angle = float(row['angle_deg'])
        for index in range(len(bins) - 1):
            if bins[index] <= angle < bins[index + 1]:
                g5[index] += 1
                break
    labels = ['%g-%g' % (bins[i], bins[i + 1]) for i in range(len(bins) - 1)]
    x = np.arange(len(labels))
    fig, axis = plt.subplots(figsize=(10, 4.6))
    axis.bar(x - 0.2, base, 0.4, label='G4 (1283 crossings)',
             color='#c0392b', alpha=0.85)
    axis.bar(x + 0.2, g5, 0.4, label='G5', color='#1e8449', alpha=0.85)
    axis.set_xticks(x)
    axis.set_xticklabels(labels, fontsize=8)
    axis.axvline(5.5, color='k', ls='--', lw=1)
    axis.text(5.6, max(base) * 0.9, '45 deg', fontsize=9)
    axis.set_title('G4 vs G5 crossing-angle distribution')
    axis.set_xlabel('crossing angle bin (deg)')
    axis.set_ylabel('crossings')
    axis.legend()
    axis.grid(True, axis='y', alpha=0.3)
    return save(fig, 'fig10_g4_vs_g5_angle_distribution.png')


# ------------------------------------------------------------------------ 2/3
def fig_layer_violations(base_viol, layer_csv):
    layers = base_viol['violations_by_layer']
    names = list(layers)
    values = [layers[name] for name in names]
    fig, axis = plt.subplots(figsize=(10, 4.4))
    axis.bar(names, values, color='#c0392b')
    for index, value in enumerate(values):
        if value:
            axis.text(index, value + 0.3, str(value), ha='center', fontsize=8)
    axis.set_title('G4 sub-45 deg crossings per physical height')
    axis.set_ylabel('violations')
    axis.tick_params(axis='x', rotation=60, labelsize=8)
    axis.grid(True, axis='y', alpha=0.3)
    return save(fig, 'fig02_g4_layer_violation_counts.png')


def fig_hotspots(base_viol):
    events = base_viol['violations']
    xs = [row['x_mm'] for row in events]
    ys = [row['y_mm'] for row in events]
    angles = [row['angle_deg'] for row in events]
    fig, axis = plt.subplots(figsize=(7.4, 6.6))
    scatter = axis.scatter(xs, ys, c=angles, cmap='RdYlGn_r', s=26,
                           vmin=5, vmax=45, edgecolor='k', linewidth=0.2)
    axis.axhline(75, color='0.8', lw=0.5)
    axis.set_xlim(0, 150)
    axis.set_ylim(0, 150)
    axis.set_aspect('equal')
    axis.set_title('G4 sub-45 deg crossing hotspots (board 150x150 mm)')
    axis.set_xlabel('x (mm)')
    axis.set_ylabel('y (mm)')
    fig.colorbar(scatter, ax=axis, label='crossing angle (deg)')
    axis.grid(True, lw=0.2, alpha=0.3)
    return save(fig, 'fig03_g4_violation_hotspots.png')


def fig_conflict_graph(graph):
    """Spring layout written from scratch (no networkx on this machine)."""
    import random
    nodes = sorted(set(graph['vertices']))
    index = {node: i for i, node in enumerate(nodes)}
    rng = random.Random(7)
    pos = np.array([[rng.uniform(-1, 1), rng.uniform(-1, 1)] for _ in nodes])
    edges = [(index[e['route_a']], index[e['route_b']], 45.0 - e['angle_deg'])
             for e in graph['edges']]
    count = len(nodes)
    k = 1.0 / math.sqrt(max(count, 2))
    temperature = 0.12
    for _step in range(260):
        delta = np.zeros_like(pos)
        for i in range(count):
            diff = pos[i] - pos
            dist = np.maximum(np.linalg.norm(diff, axis=1), 1e-3)
            delta[i] += (diff * (k * k / (dist ** 2))[:, None]).sum(axis=0)
            delta[i] -= diff[i] * (k * k / (dist[i] ** 2))
        for a, b, weight in edges:
            diff = pos[a] - pos[b]
            dist = max(float(np.linalg.norm(diff)), 1e-3)
            force = (dist - k) / dist * 0.5 * (1.0 + weight / 40.0)
            delta[a] -= diff * force
            delta[b] += diff * force
        length = np.linalg.norm(delta, axis=1)
        scale = np.minimum(length, temperature) / np.maximum(length, 1e-9)
        pos += delta * scale[:, None]
        temperature *= 0.995
    degree = Counter()
    for a, b, _w in edges:
        degree[a] += 1
        degree[b] += 1
    fig, axis = plt.subplots(figsize=(7.8, 6.6))
    for a, b, weight in edges:
        axis.plot([pos[a][0], pos[b][0]], [pos[a][1], pos[b][1]],
                  color='#7f8c8d', lw=0.6, alpha=0.5, zorder=1)
    values = np.array([degree[i] for i in range(count)], dtype=float)
    scatter = axis.scatter(pos[:, 0], pos[:, 1], s=30 + 18 * values,
                           c=values, cmap='YlOrRd', edgecolors='k',
                           linewidths=0.3, zorder=2)
    fig.colorbar(scatter, ax=axis, label='violating degree')
    axis.set_title('G_bad conflict graph: %d routes, %d sub-45 deg pairs, '
                   '%d components'
                   % (graph['vertex_count'], graph['edge_count'],
                      graph['component_count']))
    axis.set_xticks([])
    axis.set_yticks([])
    return save(fig, 'fig04_angle_conflict_graph.png')


# --------------------------------------------------------------------- 5..9
def fig_search_history(path):
    rows = []
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        parts = line.split(',')
        rows.append(parts)
    if len(rows) < 2:
        return None
    header = rows[0]
    index = {key: i for i, key in enumerate(header)}
    series = defaultdict(list)
    for row in rows[1:]:
        try:
            series['time'].append(float(row[index['time_s']]))
            series['violations'].append(float(row[index['violations']]))
            series['min_angle'].append(float(row[index['min_angle']]))
            series['deficit'].append(float(row[index['deficit']]))
            series['crossings'].append(float(row[index['crossings']]))
            series['length'].append(float(row[index['length_mm']]))
        except (ValueError, KeyError, IndexError):
            continue
    specs = [('violations', 'sub-45 deg crossings', '#c0392b',
              'fig05_search_violations.png'),
             ('min_angle', 'minimum crossing angle (deg)', '#2e86c1',
              'fig06_search_min_angle.png'),
             ('deficit', 'total angle deficit D_theta (deg)', '#8e44ad',
              'fig07_search_deficit.png'),
             ('crossings', 'total crossings', '#e67e22',
              'fig08_search_crossings.png'),
             ('length', 'total waveguide length (mm)', '#16a085',
              'fig09_search_length.png')]
    out = []
    for key, label, colour, name in specs:
        if not series[key]:
            continue
        fig, axis = plt.subplots(figsize=(8.4, 4.2))
        axis.plot(series['time'], series[key], '-', color=colour, lw=1.4)
        axis.set_xlabel('wall-clock time (s)')
        axis.set_ylabel(label)
        axis.set_title(label + ' during the G5 search')
        axis.grid(True, alpha=0.3)
        if key == 'violations':
            axis.axhline(0, color='k', ls=':', lw=0.8)
        out.append(save(fig, name))
    return out


# ------------------------------------------------------------------- 11..13
def fig_layers_compare(base_routes, g5_routes, layer_csv=None, only_bad=False):
    base_payload = {int(r['route_id']): r for r in base_routes}
    g5_payload = {int(r['route_id']): r for r in g5_routes}
    heights = sorted({round(float(part['z_mm']), 6)
                      for route in base_routes for part in route['parts']
                      if part['kind'] == 'flat'})
    made = []
    for z in heights:
        fig, axes = plt.subplots(1, 2, figsize=(17, 8.4))
        for axis, routes, title in ((axes[0], base_routes, 'G4'),
                                    (axes[1], g5_routes, 'G5')):
            for route in routes:
                for part in route['parts']:
                    if part['kind'] != 'flat':
                        continue
                    if abs(float(part['z_mm']) - z) > 1e-9:
                        continue
                    for prim in part['primitives']:
                        xs, ys = prim_points(prim)
                        axis.plot(xs, ys, color='0.75', lw=0.3)
            axis.set_xlim(0, 150)
            axis.set_ylim(0, 150)
            axis.set_aspect('equal')
            axis.set_title('%s  z = %+.3f mm (%s)'
                           % (title, z, G5.plane_label(z)))
            axis.grid(True, lw=0.2, alpha=0.3)
        path = FIG / 'layers' / ('layer_%+.3f.png' % z)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.tight_layout()
        fig.savefig(path, dpi=110)
        plt.close(fig)
        made.append(path)
        print('  layers/layer_%+.3f.png' % z, flush=True)
    return made


def fig_crossing_layers(g5_rows, baseline_rows):
    heights = sorted({round(float(row['z_mm']), 6) for row in baseline_rows}
                     | {round(float(row['z_mm']), 6) for row in g5_rows})
    for z in heights:
        fig, axis = plt.subplots(figsize=(7.6, 6.8))
        for row in baseline_rows:
            if abs(float(row['z_mm']) - z) > 1e-9:
                continue
            bad = float(row['angle_deg']) < 45.0
            axis.plot([row['x_mm']], [row['y_mm']], 'o', ms=5,
                      mfc=('#c0392b' if bad else 'none'),
                      mec=('#c0392b' if bad else '#2e86c1'), mew=1.0)
            if bad:
                axis.annotate('%.1f' % float(row['angle_deg']),
                              (row['x_mm'], row['y_mm']),
                              textcoords='offset points', xytext=(3, 2),
                              fontsize=5.5, color='#c0392b')
        for row in g5_rows:
            if abs(float(row['z_mm']) - z) > 1e-9:
                continue
            axis.plot([row['x_mm']], [row['y_mm']], 'x', ms=5,
                      color='#1e8449', mew=1.1)
        axis.set_xlim(0, 150)
        axis.set_ylim(0, 150)
        axis.set_aspect('equal')
        axis.set_title('crossings at z = %+.3f mm  (red circle = G4 sub-45 deg, '
                       'green x = G5)' % z, fontsize=9)
        axis.grid(True, lw=0.2, alpha=0.3)
        path = FIG / 'crossing_layers' / ('crossings_%+.3f.png' % z)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.tight_layout()
        fig.savefig(path, dpi=110)
        plt.close(fig)
    print('  crossing_layers/ (%d files)' % len(heights), flush=True)


def fig_3d_compare(base_routes, g5_routes):
    fig = plt.figure(figsize=(14, 6.4))
    for index, (routes, title) in enumerate(((base_routes, 'G4'),
                                             (g5_routes, 'G5'))):
        axis = fig.add_subplot(1, 2, index + 1, projection='3d')
        for route in routes:
            xs, ys, zs = [], [], []
            for part in route['parts']:
                if part['kind'] == 'flat':
                    z = float(part['z_mm'])
                    for prim in part['primitives']:
                        px, py = prim_points(prim, 16)
                        xs.extend(px)
                        ys.extend(py)
                        zs.extend([z] * len(px))
            axis.plot(xs, ys, zs, lw=0.15, alpha=0.5)
        axis.set_title('%s: 1024 routes, 20 heights' % title, fontsize=9)
        axis.set_xlabel('x')
        axis.set_ylabel('y')
        axis.set_zlabel('z (mm)')
    return save(fig, 'fig11_g4_vs_g5_3d.png')


# ------------------------------------------------------------------ 17 / 18
def fig_move_contribution(move_csv):
    rows = []
    text = Path(move_csv).read_text(encoding='utf-8').splitlines()
    if len(text) < 2:
        return None
    header = text[0].split(',')
    index = {key: i for i, key in enumerate(header)}
    counts = Counter()
    for line in text[1:]:
        parts = line.split(',')
        if len(parts) <= index['move']:
            continue
        family = parts[index['move']].split(':')[0]
        counts[family] += 1
    if not counts:
        return None
    fig, axis = plt.subplots(figsize=(7.6, 4.2))
    names = list(counts)
    values = [counts[name] for name in names]
    axis.bar(names, values, color=['#1e8449', '#2e86c1', '#e67e22', '#8e44ad',
                                   '#c0392b'][:len(names)])
    for i, value in enumerate(values):
        axis.text(i, value + 0.2, str(value), ha='center', fontsize=9)
    axis.set_title('accepted moves per neighbourhood family')
    axis.set_ylabel('accepted moves')
    axis.grid(True, axis='y', alpha=0.3)
    return save(fig, 'fig17_neighbourhood_contribution.png')


def fig_acceptance(base_viol, g5_rows):
    angles = sorted(float(row['angle_deg']) for row in g5_rows)
    fig, axis = plt.subplots(figsize=(9, 4.6))
    axis.plot(range(1, len(angles) + 1), angles, lw=0.8, color='#1e8449')
    axis.axhline(45.0, color='k', ls='--', lw=1)
    axis.set_ylim(0, 95)
    axis.set_xlabel('crossing index (sorted by angle)')
    axis.set_ylabel('crossing angle (deg)')
    axis.set_title('G5 acceptance: all %d crossings vs the 45 deg hard limit '
                   '(min = %.3f deg)'
                   % (len(angles), min(angles) if angles else float('nan')))
    axis.grid(True, alpha=0.3)
    return save(fig, 'fig18_angle45_acceptance.png')


# ------------------------------------------------------------------ 14 / 15
def fig_repair_zoom(base_routes, g5_routes, events, index=0, pad=14.0):
    base = {int(r['route_id']): r for r in base_routes}
    g5 = {int(r['route_id']): r for r in g5_routes}
    chosen = sorted(events, key=lambda e: e['angle_deg'])[index]
    ra, rb = chosen['route_a'], chosen['route_b']
    px, py = chosen['x_mm'], chosen['y_mm']
    z = chosen['z_mm']
    fig, axes = plt.subplots(1, 2, figsize=(13, 6.2))
    for axis, table, title in ((axes[0], base, 'G4 (before)'),
                               (axes[1], g5, 'G5 (after)')):
        for rid in (ra, rb):
            route = table[rid]
            for part in route['parts']:
                if part['kind'] != 'flat':
                    continue
                if abs(float(part['z_mm']) - z) > 1e-9:
                    continue
                for prim in part['primitives']:
                    xs, ys = prim_points(prim, 200)
                    axis.plot(xs, ys, lw=1.6,
                              color=('#c0392b' if rid == ra else '#2e86c1'))
        axis.plot([px], [py], 'ko', ms=5)
        axis.annotate('$\\theta$ = %.3f deg' % chosen['angle_deg'],
                      (px, py), textcoords='offset points', xytext=(6, 6),
                      fontsize=9)
        axis.set_xlim(px - pad, px + pad)
        axis.set_ylim(py - pad, py + pad)
        axis.set_aspect('equal')
        axis.set_title('%s  R%d (red) vs R%d (blue), z=%+.3f'
                       % (title, ra, rb, z), fontsize=9)
        axis.grid(True, lw=0.2, alpha=0.3)
    return save(fig, 'fig14_repair_zoom_R%d_R%d.png' % (ra, rb))


def fig_route_before_after(base_routes, g5_routes, route_ids, z=None):
    base = {int(r['route_id']): r for r in base_routes}
    g5 = {int(r['route_id']): r for r in g5_routes}
    made = []
    for rid in route_ids[:3]:
        old = base[rid]
        new = g5[rid]
        fig, axes = plt.subplots(1, 2, figsize=(13, 6.0))
        for axis, route, title in ((axes[0], old, 'G4'),
                                   (axes[1], new, 'G5')):
            for part in route['parts']:
                if part['kind'] != 'flat':
                    continue
                for prim in part['primitives']:
                    xs, ys = prim_points(prim, 160)
                    axis.plot(xs, ys, lw=1.0, color='#34495e')
            axis.set_xlim(0, 150)
            axis.set_ylim(0, 150)
            axis.set_aspect('equal')
            axis.set_title('%s  R%d  plane %s  L=%.2f mm'
                           % (title, rid, route.get('target_plane'),
                              float(route['length_mm'])), fontsize=9)
            axis.grid(True, lw=0.2, alpha=0.3)
        made.append(save(fig, 'fig15_route_R%d_before_after.png' % rid))
    return made


def fig_ctp(compare_md=None):
    path = EXP / '05_ctp2_comparison' / 'ctp2_out' / 'board' / 'board_summary_ctp2.json'
    if not path.exists():
        return None
    g5 = load(path, {})
    g4_path = (ROOT.parent / 'work' / '1130-report-materials' / 'experiments'
               / 'CROSSTALK_PREDICTION_CTP2_20H_1283_1024' / 'outputs'
               / 'board' / 'board_summary_ctp2.json')
    g4 = load(g4_path, {}) if g4_path.exists() else {}

    def numbers(summary):
        nominal = (summary.get('board_summary') or summary)
        nominal = nominal.get('nominal_ctp2', nominal)
        multi = (summary.get('multi_input_incoherent')
                 or summary.get('multi_input') or {})
        return dict(
            pair=nominal.get('max_offdiagonal_db'),
            leak=nominal.get('worst_total_leakage_db'),
            isr=(nominal.get('worst_interference_to_signal_db')
                 or multi.get('worst_interference_to_signal_db')))

    base = numbers(g4)
    new = numbers(g5)
    labels = ['worst port pair', 'worst route leakage', 'multi-input I/S']
    keys = ['pair', 'leak', 'isr']
    if any(base[k] is None or new[k] is None for k in keys):
        print('  [fig16] incomplete CTP numbers: %s / %s' % (base, new))
        return None
    x = np.arange(len(labels))
    fig, axis = plt.subplots(figsize=(8.4, 4.4))
    axis.bar(x - 0.2, [base[k] for k in keys], 0.4, label='G4 + CTP-2.0',
             color='#c0392b')
    axis.bar(x + 0.2, [new[k] for k in keys], 0.4, label='G5 + CTP-2.0',
             color='#1e8449')
    for index, key in enumerate(keys):
        axis.text(index - 0.2, base[key] - 0.6, '%.2f' % base[key],
                  ha='center', fontsize=8)
        axis.text(index + 0.2, new[key] - 0.6, '%.2f' % new[key],
                  ha='center', fontsize=8)
    axis.set_xticks(x)
    axis.set_xticklabels(labels, fontsize=9)
    axis.set_ylabel('dB')
    axis.set_title('CTP-2.0 board crosstalk: G4 vs G5 (higher is worse)',
                   fontsize=9)
    axis.legend()
    axis.grid(True, axis='y', alpha=0.3)
    return save(fig, 'fig16_ctp2_g4_vs_g5.png')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--g5-routes', default=str(
        EXP / '03_best_feasible' / 'routes_l3d.json'))
    parser.add_argument('--skip-layers', action='store_true')
    parser.add_argument('--history', default=None)
    args = parser.parse_args(argv)
    FIG.mkdir(parents=True, exist_ok=True)
    base_payload = json.loads((BASE / 'routes_l3d.json').read_text(
        encoding='utf-8'))
    base_routes = base_payload['routes']
    base_viol = load(EXP / '00_baseline_audit'
                     / 'baseline_angle_violations.json')
    graph = load(EXP / '00_baseline_audit' / 'angle_conflict_graph.json')
    base_rows = []
    csv_path = EXP / '00_baseline_audit' / 'baseline_crossing_angles.csv'
    if csv_path.exists():
        lines = csv_path.read_text(encoding='utf-8').splitlines()
        header = lines[0].split(',')
        for line in lines[1:]:
            parts = line.split(',')
            base_rows.append(dict(zip(header, parts)))
    print('[figures] base violations=%d' % base_viol['violations_below_45'])
    fig_histogram(base_viol)
    fig_layer_violations(base_viol, None)
    fig_hotspots(base_viol)
    fig_conflict_graph(graph)

    g5_routes = None
    g5_rows = []
    path = Path(args.g5_routes)
    if path.exists():
        g5_routes = json.loads(path.read_text(encoding='utf-8'))['routes']
        g5_csv = path.parent / 'g5_crossing_angles.csv'
        if g5_csv.exists():
            lines = g5_csv.read_text(encoding='utf-8').splitlines()
            header = lines[0].split(',')
            for line in lines[1:]:
                g5_rows.append(dict(zip(header, line.split(','))))
        print('[figures] G5 routes=%d crossings=%d'
              % (len(g5_routes), len(g5_rows)))
        fig_compare_histogram(base_viol, g5_rows)
        fig_3d_compare(base_routes, g5_routes)
        if not args.skip_layers:
            fig_layers_compare(base_routes, g5_routes)
            fig_crossing_layers(g5_rows, base_rows)
        if g5_rows:
            fig_acceptance(base_viol, g5_rows)
        try:
            fig_repair_zoom(base_routes, g5_routes, base_viol['violations'])
        except Exception as error:  # noqa: BLE001
            print('  zoom failed: %s' % error)
        changed = [int(route['route_id']) for route in g5_routes
                   if json.dumps(route['parts'], sort_keys=True) !=
                   json.dumps({int(r['route_id']): r for r in base_routes}
                              [int(route['route_id'])]['parts'], sort_keys=True)]
        if changed:
            fig_route_before_after(base_routes, g5_routes,
                                   sorted(changed)[:3])
    history = Path(args.history) if args.history else (EXP / '02_search_runs' / 'seed_20261116_free' / 'g5_search_history.csv')
    if history.exists():
        fig_search_history(history)
    moves = (Path(args.history).parent / 'g5_candidate_statistics.csv') if args.history else (EXP / '02_search_runs' / 'seed_20261116_free' / 'g5_candidate_statistics.csv')
    if moves.exists():
        fig_move_contribution(moves)
    fig_ctp()
    print('[figures] done')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
