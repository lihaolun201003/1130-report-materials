# -*- coding: utf-8 -*-
"""Quick look at the G4 crossing-angle violations on one physical height."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024.xyzrouter.g4 import independent_metrics as IM

RUN = ROOT / 'experiments' / 'COLD_START_20_HEIGHT_1024' / '10_best_valid'
OUT = ROOT / 'experiments' / 'G5_ANGLE45_NATIVE3D_20H_1024' / '06_figures' / '_scratch'


def prim_points(prim, count=64):
    if prim['kind'] == 'line':
        return ([prim['p0'][0], prim['p1'][0]], [prim['p0'][1], prim['p1'][1]])
    angles = [prim['start'] + prim['sweep'] * k / count for k in range(count + 1)]
    return ([prim['center'][0] + prim['radius'] * math.cos(a) for a in angles],
            [prim['center'][1] + prim['radius'] * math.sin(a) for a in angles])


def main(z_target=0.175, xlim=(40, 150), ylim=(55, 150)):
    payload = json.loads((RUN / 'routes_l3d.json').read_text(encoding='utf-8'))
    routes = payload['routes']
    by_id = {int(r['route_id']): r for r in routes}
    curves = IM.build_curves(routes)
    first, second, _ = IM.build_candidate_pairs(curves)
    chains = IM.build_height_chains(routes)
    result = IM.same_layer_audit(curves, routes, chains, first, second,
                                 log=lambda *_a: None)
    events = result['events']
    bad = [e for e in events if e['angle_deg'] < 45.0
           and abs(e['height_mm'] - z_target) < 1e-6]
    bad_routes = sorted({e['route_a'] for e in bad} | {e['route_b'] for e in bad})
    print('plane %.3f: %d crossings, %d bad, %d routes'
          % (z_target, sum(1 for e in events
                           if abs(e['height_mm'] - z_target) < 1e-6),
             len(bad), len(bad_routes)))
    OUT.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(1, 2, figsize=(22, 11))
    for ax, highlight in ((axes[0], False), (axes[1], True)):
        for curve in curves:
            if curve['curve_kind'] != 'flat' or abs(curve['z'] - z_target) > 1e-9:
                continue
            xs, ys = prim_points(curve)
            if highlight and curve['route_id'] in bad_routes:
                continue
            ax.plot(xs, ys, color='0.82', lw=0.35, zorder=1)
        if highlight:
            colours = plt.cm.tab20.colors
            for k, rid in enumerate(bad_routes):
                for curve in curves:
                    if curve['curve_kind'] != 'flat' or abs(curve['z'] - z_target) > 1e-9:
                        continue
                    if curve['route_id'] != rid:
                        continue
                    xs, ys = prim_points(curve)
                    ax.plot(xs, ys, color=colours[k % 20], lw=1.1, zorder=3)
            for e in bad:
                ax.plot([e['x_mm']], [e['y_mm']], 'o', ms=5, mfc='none',
                        mec='red', mew=1.0, zorder=4)
                ax.annotate('%.1f' % e['angle_deg'], (e['x_mm'], e['y_mm']),
                            textcoords='offset points', xytext=(3, 3),
                            fontsize=6, color='red', zorder=5)
        ax.set_xlim(*xlim)
        ax.set_ylim(*ylim)
        ax.set_aspect('equal')
        ax.set_title('z = %.3f mm  %s' % (z_target,
                                        'violating routes' if highlight else 'all'))
        ax.grid(True, lw=0.2, alpha=0.3)
    fig.tight_layout()
    path = OUT / ('plane_%+.3f.png' % z_target)
    fig.savefig(path, dpi=150)
    print('wrote', path)


if __name__ == '__main__':
    main(*(float(a) if a.replace('.', '').replace('-', '').isdigit() else a
           for a in sys.argv[1:]))
