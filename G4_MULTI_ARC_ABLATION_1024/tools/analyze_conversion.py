# -*- coding: utf-8 -*-
"""Mechanism analysis of the stage-0 planar multi-arc conversion.

For every converted route it recovers the *canonical* body geometry of the G3
start solution (frame kind + lateral offset ``|bx|``) and pairs it with the
exact crossing delta the ablated grammar needed for that route.  This makes the
geometric threshold of the frozen D56 grammar visible:

* 2 independent R15 quarter arcs can only realise a lateral offset ``>= 2R``
  (30 mm) -- below that the only *compact* planar solution is the two-arc
  short-S that the ablation removes;
* therefore all converted routes with ``|bx| < 2R`` are forced into a >= 4R
  detour, which is what the crossing delta measures.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt                       # noqa: E402
import numpy as np                                     # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024 import layer2d as L2                      # noqa: E402
from four_side_1024.fanout1024.xyzrouter import route_builder as RB      # noqa: E402
from four_side_1024.fanout1024.xyzrouter import world_adapter as WA      # noqa: E402
from four_side_1024.fanout1024.xyzrouter.g4 import paths as GP           # noqa: E402
from four_side_1024.fanout1024.reheight21 import model as M              # noqa: E402

R15 = 15.0


def canonical_of(state, rid):
    row = state.row(rid)
    route = state.routes[rid]
    layer = int(row['target_layer'])
    z = float(row['target_z_mm'])
    if layer in (1001, 1002):
        task = RB.direct_task(row)
    else:
        task, _s, _t = RB.body_task(row, layer, z, *RB.lead_lengths(route))
    frame, error = L2.canonical_frame(task)
    if error:
        return None, None
    return frame['kind'], abs(float(frame['bx']))


def main(argv=None):
    exp = Path(__file__).resolve().parents[1]
    report_path = exp / 'no_multi_arc' / '01_convert' / 'conversion_report.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    start = GP.load_start()
    rows = RB.normalized_rows(start['rows'], stack=M.layer_stack())
    state = WA.RouteWorld(start['routes'], rows, log=lambda *_a: None)

    out_rows = []
    for record in report['records']:
        if record.get('status') != 'converted':
            continue
        rid = int(record['route_id'])
        kind, u = canonical_of(state, rid)
        out_rows.append(dict(
            route_id=rid, kind=kind or 'direct/unknown',
            lateral_offset_mm=None if u is None else round(u, 4),
            below_2R=None if u is None else bool(u < 2 * R15 - 1e-9),
            delta_crossings=int(record['delta']),
            old_regions=int(record['old_regions']),
            new_regions=int(record['new_regions']),
            family=record.get('family'), chosen_kind=record.get('kind'),
            layer=int(record.get('layer') or 0),
            z_mm=record.get('z_mm'),
            length_after_mm=record.get('length_mm')))
    out_dir = exp / 'baseline_audit'
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / 'conversion_geometry_vs_delta.csv').open(
            'w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(out_rows[0].keys()))
        writer.writeheader()
        writer.writerows(out_rows)

    buckets = defaultdict(list)
    for row in out_rows:
        key = ('|bx| < 2R (sub-30 mm offset)' if row['below_2R']
               else '|bx| >= 2R')
        buckets[key].append(row['delta_crossings'])
    summary = {}
    for key, values in buckets.items():
        values.sort()
        summary[key] = dict(
            routes=len(values), mean_delta=round(float(np.mean(values)), 3),
            median_delta=float(np.median(values)), max_delta=int(values[-1]),
            min_delta=int(values[0]),
            sum_delta=int(sum(values)),
            share_positive=round(float(np.mean([1 if v > 0 else 0
                                                for v in values])), 4))
    families = Counter(row['family'] for row in out_rows)
    kkinds = Counter(row['kind'] for row in out_rows)
    payload = dict(schema='g4_multi_arc_conversion_mechanism_v1',
                   converted=len(out_rows),
                   total_delta=int(sum(row['delta_crossings']
                                       for row in out_rows)),
                   by_offset_threshold=summary,
                   by_family=dict(families),
                   by_frame_kind=dict(kkinds),
                   delta_positive=int(sum(1 for row in out_rows
                                          if row['delta_crossings'] > 0)),
                   delta_zero=int(sum(1 for row in out_rows
                                      if row['delta_crossings'] == 0)),
                   delta_negative=int(sum(1 for row in out_rows
                                          if row['delta_crossings'] < 0)))
    (out_dir / 'conversion_mechanism.json').write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')

    # ---- scatter: lateral offset vs crossing delta -------------------------
    fig, ax = plt.subplots(figsize=(11.4, 6.6))
    palette = {'opposite': '#1565c0', 'adjacent': '#2e7d32',
               'direct/unknown': '#6a1b9a'}
    for kind, color in palette.items():
        xs = [row['lateral_offset_mm'] for row in out_rows
              if row['kind'] == kind and row['lateral_offset_mm'] is not None]
        ys = [row['delta_crossings'] for row in out_rows
              if row['kind'] == kind and row['lateral_offset_mm'] is not None]
        if xs:
            ax.scatter(xs, ys, s=34, alpha=0.80, c=color, edgecolors='white',
                       linewidths=0.5, label='%s (%d routes)' % (kind, len(xs)))
    ax.axvline(2 * R15, color='#c62828', linewidth=1.4, linestyle='--')
    ax.text(2 * R15 + 1.0, ax.get_ylim()[1] * 0.92,
            '2R = 30 mm\nhard resolution limit of two\nindependent R15 quarters',
            fontsize=8.2, color='#c62828')
    ax.axhline(0.0, color='#37474f', linewidth=0.8)
    ax.set_xlabel('lateral offset |bx| between the two landings of the route (mm)')
    ax.set_ylabel('exact crossing delta of the converted route (events)')
    ax.set_title('stage-0 conversion: the ablated grammar needs a >= 4R detour '
                 'for every sub-2R lateral offset\n(%d converted routes, total '
                 '%+d crossing events)'
                 % (len(out_rows), payload['total_delta']), fontsize=10.6)
    ax.grid(color='#eceff1', linewidth=0.6)
    ax.set_axisbelow(True)
    ax.legend(fontsize=8.4)
    fig.tight_layout()
    fig.savefig(out_dir / 'conversion_offset_vs_delta.png', dpi=140,
                facecolor='white')
    plt.close(fig)
    print(json.dumps(payload, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
