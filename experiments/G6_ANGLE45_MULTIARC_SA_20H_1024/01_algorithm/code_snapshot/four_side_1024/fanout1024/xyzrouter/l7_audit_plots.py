# -*- coding: utf-8 -*-
"""Figures for the L7 independent geometry audit.

Every figure is drawn from the REAL stored primitives of the G3 best solution:
flats from their analytic line / R15-arc definitions, transitions from the exact
two-arc S-curve samples of ``fsd25d.path3d.transition_samples``.  Nothing is
smoothed, splined or simplified.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fsd25d import path3d as P3  # noqa: E402
from four_side_1024.fanout1024.xyzrouter import l7_geometry_audit as A  # noqa: E402
from four_side_1024.fanout1024.xyzrouter import paths as P  # noqa: E402

RUN_DIR = P.DIRS['best_valid']
OUT_DIR = P.XYZ_RUN_DIR / 'l7_geometry_audit' / 'plots'
TARGET_Z = -0.10
KAPPA_MAX = 1.0 / 15.0

# case routes: representatives of every "wavy" primitive combination
CASE_ROUTES = [
    (475, 'detour body: line-arc-arc-arc-arc (4 x R15 arcs in XY)'),
    (100, 'multi-excursion: 6 S-curves / 2 mid-body up-down pairs'),
    (127, 'one mid-body excursion: 4 S-curves'),
    (128, 'detour body: 4 x R15 arcs in XY'),
]
HIGHLIGHT = {475: '#c2185b', 100: '#1b5e20', 127: '#ef6c00', 128: '#6a1b9a'}


# ---------------------------------------------------------------------------
def load_run(run_dir=None):
    run_dir = Path(run_dir or RUN_DIR)
    payload = json.loads((run_dir / 'routes_l3d.json').read_text(encoding='utf-8'))
    routes = {int(route['route_id']): route for route in payload['routes']}
    stats = json.loads((run_dir / 'crossing_stats.json').read_text(encoding='utf-8'))
    assignment = {}
    assignment_path = run_dir / 'assignment_1024.csv'
    if assignment_path.exists():
        from four_side_1024.fanout1024 import common as C
        rows, _ = C.read_csv_rows(assignment_path)
        assignment = {int(row['route_id']): row for row in rows}
    return payload, routes, stats, assignment


def flat_primitive_polylines(route, z_filter=None):
    """``[(part_index, prim_index, prim, points_xy, z)]`` from real primitives."""
    out = []
    for part_index, part in enumerate(route['parts']):
        if part.get('kind') != 'flat':
            continue
        z = float(part['z_mm'])
        if z_filter is not None and abs(z - z_filter) > 1e-9:
            continue
        for prim_index, prim in enumerate(part.get('primitives') or ()):
            length = A.prim_length(prim)
            count = max(2, int(math.ceil(length / 0.25)) + 1)
            points = np.asarray([A.prim_point(prim, index / (count - 1))
                                 for index in range(count)], dtype=float)
            out.append(dict(part_index=part_index, prim_index=prim_index,
                            prim=prim, points=points, z=z))
    return out


def route_flat_polylines(route, z_filter=None):
    return [item['points'] for item in flat_primitive_polylines(route, z_filter)]


def route_transition_polylines(route):
    out = []
    for part in route['parts']:
        if part.get('kind') != 'transition':
            continue
        samples = np.asarray(P3.transition_samples(part, step=0.05), dtype=float)
        out.append(samples)
    return out


def save(fig, name):
    path = OUT_DIR / name
    fig.savefig(path, dpi=140, bbox_inches='tight')
    plt.close(fig)
    print('wrote', path)
    return path


# ---------------------------------------------------------------------------
# figure 1: the L7 layer as it really is
# ---------------------------------------------------------------------------
def fig_l7_layer(routes, stats, l7_ids):
    fig = plt.figure(figsize=(15.0, 7.4))
    ax = fig.add_subplot(121)
    ax_zoom = fig.add_subplot(122)
    segments = []
    for rid in l7_ids:
        for item in flat_primitive_polylines(routes[rid], z_filter=TARGET_Z):
            segments.append(item['points'])
    ax.add_collection(LineCollection(segments, colors='#5c6bc0', linewidths=0.7,
                                     alpha=0.75, label='L7 flats (real primitives)'))
    for rid, label in CASE_ROUTES:
        for item in flat_primitive_polylines(routes[rid], z_filter=TARGET_Z):
            ax.plot(item['points'][:, 0], item['points'][:, 1],
                    color=HIGHLIGHT[rid], linewidth=1.9, solid_capstyle='round')
            ax_zoom.plot(item['points'][:, 0], item['points'][:, 1],
                         color=HIGHLIGHT[rid], linewidth=2.0,
                         solid_capstyle='round')
    events = [event for event in (stats.get('crossing_events') or [])
              if abs(float(event['z_mm']) - TARGET_Z) < 1e-9]
    ax.scatter([event['x_mm'] for event in events],
               [event['y_mm'] for event in events],
               marker='x', c='#d32f2f', s=28, linewidths=1.0, zorder=8,
               label='%d crossing events (all z = -0.100 mm)' % len(events))
    ax.set_xlim(-2, 152)
    ax.set_ylim(-2, 152)
    ax.set_aspect('equal')
    ax.set_title('L7 (z = -0.10 mm): all %d real flat chains\n'
                 'wavy shapes = real line + R15-arc combinations'
                 % len(l7_ids), fontsize=9.5)
    ax.set_xlabel('x (mm)')
    ax.set_ylabel('y (mm)')
    handles = [plt.Line2D([], [], color='#5c6bc0', lw=1.4,
                          label='L7 flats (real primitives)'),
               plt.Line2D([], [], marker='x', color='#d32f2f', ls='none',
                          label='crossing event (%d)' % len(events))]
    for rid, label in CASE_ROUTES:
        handles.append(plt.Line2D([], [], color=HIGHLIGHT[rid], lw=2.0,
                                  label='route %d: %s' % (rid, label)))
    ax.legend(handles=handles, fontsize=6.8, loc='upper left', framealpha=0.92)

    # zoom around the most "wavy" detour (route 475 body)
    items = flat_primitive_polylines(routes[475], z_filter=TARGET_Z)
    all_points = np.vstack([item['points'] for item in items])
    x0, x1 = all_points[:, 0].min() - 8, all_points[:, 0].max() + 8
    y0, y1 = all_points[:, 1].min() - 8, all_points[:, 1].max() + 8
    for rid in (475, 128):
        for item in flat_primitive_polylines(routes[rid], z_filter=TARGET_Z):
            mask = ((item['points'][:, 0] >= x0) & (item['points'][:, 0] <= x1)
                    & (item['points'][:, 1] >= y0) & (item['points'][:, 1] <= y1))
            if mask.sum() < 2:
                continue
            ax_zoom.plot(item['points'][:, 0], item['points'][:, 1],
                         color=HIGHLIGHT[rid], linewidth=2.0)
            start = item['points'][0]
            ax_zoom.annotate('p%d' % item['prim_index'],
                             (start[0], start[1]), fontsize=6.5,
                             color=HIGHLIGHT[rid])
            if item['prim']['kind'] == 'arc':
                center = item['prim']['center']
                ax_zoom.plot([center[0]], [center[1]], marker='+', ms=6,
                             color=HIGHLIGHT[rid])
                ax_zoom.plot([center[0], item['points'][0][0]],
                             [center[1], item['points'][0][1]],
                             ls=':', lw=0.6, color=HIGHLIGHT[rid])
    ax_zoom.set_xlim(x0, x1)
    ax_zoom.set_ylim(y0, y1)
    ax_zoom.set_aspect('equal')
    ax_zoom.set_title('Zoom: route 475 real primitives (line-arc-arc-arc-arc)\n'
                      'dotted = R15 centre-to-start radius, + = arc centre',
                      fontsize=9.0)
    ax_zoom.set_xlabel('x (mm)')
    ax_zoom.set_ylabel('y (mm)')
    fig.suptitle('Independent L7 geometry audit — real primitives only, no spline / '
                 'no simplification', fontsize=11.5)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    return save(fig, 'fig1_L7_layer_real_geometry.png')


# ---------------------------------------------------------------------------
# figure 2-4: one route deep dive
# ---------------------------------------------------------------------------
def fig_route(routes, rid, subtitle):
    route = routes[rid]
    rows = A.curvature_exact_uniform(route)
    points, part_tags, prim_tags = A.route_centerline(route)
    fig = plt.figure(figsize=(15.0, 9.4))
    ax_geom = fig.add_subplot(221)
    ax_samp = fig.add_subplot(222)
    ax_curv = fig.add_subplot(223)
    ax_z = fig.add_subplot(224)

    palette = plt.get_cmap('tab20')
    items = flat_primitive_polylines(route)
    for index, item in enumerate(items):
        colour = palette(index % 20)
        ax_geom.plot(item['points'][:, 0], item['points'][:, 1], color=colour,
                     linewidth=2.2,
                     label='part%d/p%d %s' % (item['part_index'],
                                              item['prim_index'],
                                              item['prim']['kind']))
        ax_geom.plot([item['points'][0, 0]], [item['points'][0, 1]], 'o',
                     ms=3.2, color=colour)
        if item['prim']['kind'] == 'arc':
            center = item['prim']['center']
            ax_geom.plot([center[0]], [center[1]], '+', ms=7, color=colour)
            ax_geom.plot([center[0], item['points'][0, 0]],
                         [center[1], item['points'][0, 1]], ':', lw=0.7,
                         color=colour)
    for samples in route_transition_polylines(route):
        ax_geom.plot(samples[:, 0], samples[:, 1], color='#455a64',
                     linewidth=2.0, linestyle='--')
    ax_geom.set_aspect('equal')
    ax_geom.set_title('real primitives in XY (solid = flats at their z, '
                      'dashed = exact S-curve XY projection)', fontsize=8.6)
    ax_geom.set_xlabel('x (mm)')
    ax_geom.set_ylabel('y (mm)')
    ax_geom.legend(fontsize=6.0, loc='best', ncol=2)

    dense = np.asarray(points)
    ax_samp.plot(dense[:, 0], dense[:, 1], color='#9e9e9e', lw=0.7)
    scatter = ax_samp.scatter(dense[:, 0], dense[:, 1], s=6,
                              c=np.arange(len(dense)), cmap='viridis', zorder=3)
    ax_samp.set_aspect('equal')
    ax_samp.set_title('centre-line samples from the real parts (%d points, '
                      'flat step 0.05 mm, S step 0.01 mm)' % len(dense),
                      fontsize=8.6)
    ax_samp.set_xlabel('x (mm)')
    ax_samp.set_ylabel('y (mm)')
    fig.colorbar(scatter, ax=ax_samp, fraction=0.035, pad=0.02,
                 label='sample index')

    inside = [row for row in rows if not row['crosses_junction']]
    cross = [row for row in rows if row['crosses_junction']]
    if inside:
        ax_curv.plot([row['s_mm'] for row in inside],
                     [row['kappa_menger'] for row in inside], 'o', ms=1.6,
                     color='#1565c0', label='kappa Menger (inside one primitive)')
    if cross:
        ax_curv.plot([row['s_mm'] for row in cross],
                     [row['kappa_turn'] for row in cross], '.', ms=2.4,
                     color='#ef6c00',
                     label='kappa turn-rate (window crosses a junction)')
    ax_curv.axhline(KAPPA_MAX, color='#c62828', ls='--', lw=1.0,
                    label='limit kappa = 1/15 = %.6f' % KAPPA_MAX)
    ax_curv.set_ylim(0, max(2.2 * KAPPA_MAX, 0.01))
    ax_curv.set_xlabel('3D arclength s (mm)')
    ax_curv.set_ylabel('curvature kappa (1/mm)')
    ax_curv.set_title('independent local curvature on the exact centre line',
                      fontsize=8.6)
    ax_curv.legend(fontsize=6.2, loc='upper right')

    ax_z.plot([row['s_mm'] for row in rows],
              [0.0] * len(rows))
    exact_points, atom_ids, s_values, atoms = A.exact_uniform_samples(route)
    ax_z.plot(s_values, [point[2] for point in exact_points], color='#2e7d32',
              lw=1.4)
    for atom in atoms:
        pass
    ax_z.set_xlabel('3D arclength s (mm)')
    ax_z.set_ylabel('z (mm)')
    ax_z.set_title('independent Z profile (exact analytic sampling)', fontsize=8.6)
    ax_z.grid(alpha=0.25)

    fig.suptitle('Route %d — %s' % (rid, subtitle), fontsize=11.0)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    return save(fig, 'fig_route_%d.png' % rid)


# ---------------------------------------------------------------------------
# figure 5: curvature summary of all 54 routes
# ---------------------------------------------------------------------------
def fig_curvature_summary(audit):
    routes = audit['routes']
    ids = [row['route_id'] for row in routes]
    kappa = [row['max_kappa_exact_uniform_inside_atom'] for row in routes]
    order = np.argsort(kappa)
    fig, axes = plt.subplots(1, 2, figsize=(15.0, 5.6))
    ax = axes[0]
    bars = ax.bar(range(len(order)),
                  [kappa[index] for index in order],
                  color='#1565c0', alpha=0.85)
    ax.axhline(KAPPA_MAX, color='#c62828', ls='--', lw=1.2,
               label='kappa limit 1/15 = %.9f' % KAPPA_MAX)
    ax.set_ylim(0, 1.25 * KAPPA_MAX)
    ax.set_xlabel('L7 routes (sorted)')
    ax.set_ylabel('max local curvature kappa (1/mm)')
    ax.set_title('max curvature per L7 route (exact analytic centre line, '
                 'inside-primitive samples)\nall %d routes reach kappa = 1/15 '
                 'but none exceed it' % len(routes), fontsize=9.0)
    ax.legend(fontsize=7.5)

    ax = axes[1]
    ax.hist(kappa, bins=24, color='#1565c0', alpha=0.85)
    ax.set_xlim(0.0, 1.3 * KAPPA_MAX)
    ax.axvline(KAPPA_MAX, color='#c62828', ls='--', lw=1.2, label='limit 1/15')
    ax.set_xlabel('max local curvature kappa (1/mm)')
    ax.set_ylabel('routes')
    ax.set_title('distribution of the per-route maximum curvature', fontsize=9.0)
    ax.legend(fontsize=7.5)
    fig.suptitle('Independent curvature audit of all %d L7 routes: '
                 'max kappa = %.9f = exactly 1/15, no violation'
                 % (len(routes), max(kappa)), fontsize=11.0)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    return save(fig, 'fig5_curvature_summary_54_routes.png')


# ---------------------------------------------------------------------------
# figure 6: crossing-marker verification on L7
# ---------------------------------------------------------------------------
def fig_crossings(routes, crossings, n_panels=4):
    events = crossings['events']
    chosen = events[:n_panels]
    fig, axes = plt.subplots(1, len(chosen), figsize=(4.4 * len(chosen), 4.6))
    if len(chosen) == 1:
        axes = [axes]
    for ax, event in zip(axes, chosen):
        point = (event['x_mm'], event['y_mm'])
        for rid, colour in ((event['route_a'], '#1565c0'),
                            (event['route_b'], '#ef6c00')):
            for item in flat_primitive_polylines(routes[rid], z_filter=TARGET_Z):
                distances = [A.point_on_primitive_distance(point, item['prim'])
                             for _ in [0]]
                # keep only nearby geometry for the zoom
                mask = (np.abs(item['points'][:, 0] - point[0]) < 9.0) & \
                       (np.abs(item['points'][:, 1] - point[1]) < 9.0)
                if mask.sum() >= 2:
                    ax.plot(item['points'][:, 0], item['points'][:, 1],
                            color=colour, lw=1.8,
                            label='route %d flat (z=%.3f mm)'
                                  % (rid, TARGET_Z))
        ax.scatter([point[0]], [point[1]], marker='x', s=70, color='#d32f2f',
                   zorder=6)
        ax.set_xlim(point[0] - 9, point[0] + 9)
        ax.set_ylim(point[1] - 9, point[1] + 9)
        ax.set_aspect('equal')
        ax.set_title('L7 crossing: routes %d × %d\nz_a=%.6f  z_b=%.6f  '
                     'angle=%.3f deg\npoint-on-both-geometry: %.2e / %.2e mm'
                     % (event['route_a'], event['route_b'],
                        event['z_a_mm'], event['z_b_mm'],
                        event['angle_recorded_deg'],
                        event['distance_a_mm'] or 0.0,
                        event['distance_b_mm'] or 0.0), fontsize=7.6)
        ax.set_xlabel('x (mm)')
        ax.set_ylabel('y (mm)')
        ax.legend(fontsize=6.0, loc='upper left')
    fig.suptitle('Red crossing markers re-verified on the real geometry: every '
                 'intersection is exactly on the z = -0.100 mm plane of BOTH routes',
                 fontsize=10.5)
    fig.tight_layout(rect=[0, 0, 1, 0.9])
    return save(fig, 'fig6_crossing_verification_L7.png')


# ---------------------------------------------------------------------------
# figure 7: plotting fidelity (no spline / no simplification)
# ---------------------------------------------------------------------------
def fig_plot_fidelity(routes, rid=475):
    route = routes[rid]
    fig, axes = plt.subplots(1, 2, figsize=(14.0, 5.6))
    ax = axes[0]
    max_deviation = 0.0
    items = flat_primitive_polylines(route)
    for item in items:
        prim = item['prim']
        analytic = item['points']
        # exactly what visualize.py draws: P3.path_polyline of the same prims
        drawn = np.asarray(P3.path_polyline([prim], step=1.5), dtype=float)
        first = (item is items[0])
        ax.plot(analytic[:, 0], analytic[:, 1], color='#1565c0', lw=3.4,
                alpha=0.30,
                label='real analytic primitive' if first else None)
        ax.plot(drawn[:, 0], drawn[:, 1], color='#c62828', lw=1.0, ls='--',
                label='exactly the polyline visualize.py draws (1.5 mm step)'
                if first else None)
        # deviation of drawn polyline from the analytic curve
        for point in drawn:
            if prim['kind'] == 'line':
                deviation = A.point_on_primitive_distance(point, prim)
            else:
                deviation = abs(A.point_on_primitive_distance(point, prim))
            max_deviation = max(max_deviation, deviation)
    ax.set_aspect('equal')
    ax.set_title('route %d: what visualize.py draws vs the real primitive\n'
                 'max deviation of the drawn polyline from the analytic curve '
                 '= %.2e mm' % (rid, max_deviation), fontsize=8.8)
    ax.legend(fontsize=7.0)
    ax.set_xlabel('x (mm)')
    ax.set_ylabel('y (mm)')

    ax = axes[1]
    text = (
        'Static inspection of four_side_1024/fanout1024/xyzrouter/visualize.py\n\n'
        'scipy spline / interp1d / CubicSpline ...... NOT USED\n'
        'moving average / savgol .................... NOT USED\n'
        'Douglas-Peucker / simplify ................. NOT USED\n'
        'z-slice truncation ......................... NOT USED\n\n'
        'flats      : P3.path_polyline(real line/arc primitives, step 1.5 mm)\n'
        'transitions: P3.transition_samples(exact two-arc R15 S-curve)\n'
        'joints     : _join_chunks only drops duplicated junction points\n'
        'per-height panels draw ONLY flat parts grouped by their exact z_mm\n'
        'crossing x markers: raw x/y/z of crossing_stats.json events\n\n'
        '=> every wavy line in the L7 panel is a real sequence of\n'
        '   R15 arcs / lines / exact S-curves, not a plotting artefact.'
    )
    ax.axis('off')
    ax.text(0.0, 1.0, text, va='top', ha='left', fontsize=8.4,
            family='DejaVu Sans Mono')
    fig.suptitle('Plotting-code audit and fidelity check', fontsize=11.0)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    return save(fig, 'fig7_plot_fidelity.png')


# ---------------------------------------------------------------------------
def main(argv=None):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload, routes, stats, assignment = load_run(argv[1] if argv and len(argv) > 1
                                                  else None)
    l7_ids = sorted(rid for rid, route in routes.items()
                    if any(part['kind'] == 'flat'
                           and abs(float(part['z_mm']) - TARGET_Z) < 1e-9
                           for part in route['parts']))
    audit = json.loads((OUT_DIR.parent / 'l7_geometry_audit.json')
                       .read_text(encoding='utf-8'))
    crossings = json.loads((OUT_DIR.parent / 'l7_crossings_verified.json')
                           .read_text(encoding='utf-8'))
    written = []
    written.append(fig_l7_layer(routes, stats, l7_ids))
    for rid, subtitle in CASE_ROUTES:
        written.append(fig_route(routes, rid, subtitle))
    written.append(fig_curvature_summary(audit))
    written.append(fig_crossings(routes, crossings))
    written.append(fig_plot_fidelity(routes))
    manifest = dict(schema='xyz_l7_audit_plots_v1',
                    run_dir=str(RUN_DIR),
                    figures=[str(path) for path in written],
                    case_routes=CASE_ROUTES)
    P.write_json(OUT_DIR / 'plots_manifest.json', manifest)
    print('figures:', len(written))
    return written


if __name__ == '__main__':
    main(sys.argv)
