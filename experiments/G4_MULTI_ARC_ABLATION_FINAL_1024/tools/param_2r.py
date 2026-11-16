# -*- coding: utf-8 -*-
"""Parametric local-geometry study around the 2R = 30 mm threshold.

For a *canonical opposite-side transfer* of fixed travel ``by = 90 mm`` and a
lateral offset ``d`` in {5, 10, 15, 20, 25, 29, 30, 31, 35, 40, 50} mm, this
script enumerates the **actual candidate set of the frozen D56 grammar** with
``enable_multi_arc = True`` and ``False`` (the single ablation variable) and
measures every built candidate:

* family name and move sequence class
* total path length (mm) and arc-only length
* lateral occupancy ``x_span`` and longitudinal occupancy ``y_span``
* lateral excursion outside the [0, d] corridor
* extra longitudinal footprint beyond the 90 mm travel
* bounding-box area, arc count, line count
* number of planar multi-arc regions (frozen policy helper)

Nothing here is a hand-drawn curve: every candidate comes from
``layer2d._LayerRouter._iter_candidates`` exactly as the router builds it.

Usage::

    python experiments/G4_MULTI_ARC_ABLATION_FINAL_1024/tools/param_2r.py \
        --out experiments/G4_MULTI_ARC_ABLATION_FINAL_1024/tables
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
ROOT = EXP.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024 import layer2d as L2  # noqa: E402

R15 = float(L2.R15)
OFFSETS = [5, 10, 15, 20, 25, 29, 30, 31, 35, 40, 50]
A = (75.0, 20.0)          # canonical start pose (heading +y)
TRAVEL = 90.0             # canonical travel (by), overridable by --travel
N_SAMPLES = 64            # arc sampling for the occupancy metrics


def metric_of(primitives):
    """Geometric metrics of one built candidate, in the canonical frame."""
    points = []
    length = 0.0
    arc_length = 0.0
    n_arcs = 0
    n_lines = 0
    min_radius = None
    for prim in primitives:
        if prim.get('kind') == 'line':
            x0, y0 = prim['p0']
            x1, y1 = prim['p1']
            length += math.hypot(x1 - x0, y1 - y0)
            n_lines += 1
            points.extend([(x0, y0), (x1, y1)])
            continue
        if prim.get('kind') != 'arc':
            continue
        n_arcs += 1
        radius = float(prim['radius'])
        sweep = abs(float(prim['sweep']))
        arc_length += radius * sweep
        length += radius * sweep
        min_radius = radius if min_radius is None else min(min_radius, radius)
        cx, cy = prim['center']
        a0 = float(prim['start_angle'])
        a1 = a0 + float(prim['sweep'])
        for index in range(N_SAMPLES + 1):
            angle = a0 + (a1 - a0) * index / N_SAMPLES
            points.append((cx + radius * math.cos(angle),
                           cy + radius * math.sin(angle)))
    xs = [point[0] - A[0] for point in points]
    ys = [point[1] - A[1] for point in points]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    return dict(length_mm=round(length, 6), arc_length_mm=round(arc_length, 6),
                x_span_mm=round(x_max - x_min, 6),
                y_span_mm=round(y_max - y_min, 6),
                x_min_mm=round(x_min, 6), x_max_mm=round(x_max, 6),
                y_min_mm=round(y_min, 6), y_max_mm=round(y_max, 6),
                bbox_area_mm2=round((x_max - x_min) * (y_max - y_min), 3),
                n_arcs=int(n_arcs), n_lines=int(n_lines),
                min_radius_mm=min_radius,
                n_multi_arc_regions=len(L2.local_multi_arc_regions(primitives)))


def build_task(offset, travel=None):
    travel = TRAVEL if travel is None else float(travel)
    return dict(route_id=1,
                A=A, dA=(0.0, 1.0),
                B=(A[0] + offset, A[1] + travel), dB=(0.0, -1.0),
                relation='opposite', manual_group='',
                source_side='S', target_side='N')


def enumerate_candidates(offset, enable_multi_arc, cfg_extra=None, travel=None):
    cfg = dict(L2.DEFAULT_CFG)
    cfg.update(enable_multi_arc=bool(enable_multi_arc))
    if cfg_extra:
        cfg.update(cfg_extra)
    router = L2._LayerRouter(0, 0.0, [build_task(offset, travel)], None, cfg,
                             lambda *_a, **_k: None)
    frame = router.frames.get(1)
    rows = []
    for world, spec, _signature in router._iter_candidates(1, 0.0):
        row = dict(family=spec['family'],
                   moves=' '.join('%s%g' % (op, float(arg))
                                  for op, arg in (spec.get('moves') or [])))
        row.update(metric_of(world))
        rows.append(row)
    return rows, dict(kind=(frame or {}).get('kind'),
                      bx=(frame or {}).get('bx'), by=(frame or {}).get('by'),
                      multi_arc_skipped=router.stats.get('multi_arc_skipped_specs'),
                      multi_arc_rejected=router.stats.get(
                          'multi_arc_rejected_candidates'))


def pick(rows, key, reverse=False):
    if not rows:
        return None
    return sorted(rows, key=key, reverse=reverse)[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default=str(EXP / 'tables'))
    parser.add_argument('--figure', default=str(EXP / 'figures'))
    parser.add_argument('--travel', type=float, default=TRAVEL,
                        help='canonical longitudinal travel by (mm)')
    parser.add_argument('--suffix', default='',
                        help='suffix of the output files (e.g. _travel55)')
    args = parser.parse_args(argv)

    travel = float(args.travel)
    suffix = str(args.suffix)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    all_rows = []
    summary = []
    for offset in OFFSETS:
        for label, enabled in (('ON', True), ('OFF', False)):
            rows, info = enumerate_candidates(offset, enabled, travel=travel)
            for row in rows:
                row.update(offset_mm=offset, arm=label,
                           relation_2R=('below' if offset < 2 * R15
                                        else 'at_or_above'))
            all_rows.extend(rows)
            greedy = rows[0] if rows else None
            shortest = pick(rows, key=lambda r: (r['length_mm'], r['bbox_area_mm2']))
            smallest_box = pick(rows, key=lambda r: (r['bbox_area_mm2'],
                                                     r['length_mm']))
            families = sorted({row['family'] for row in rows})
            summary.append(dict(
                offset_mm=offset, arm=label, n_candidates=len(rows),
                families=families, frame=info,
                greedy_family=(greedy or {}).get('family'),
                greedy_length_mm=(greedy or {}).get('length_mm'),
                greedy_x_span_mm=(greedy or {}).get('x_span_mm'),
                greedy_y_span_mm=(greedy or {}).get('y_span_mm'),
                greedy_bbox_area_mm2=(greedy or {}).get('bbox_area_mm2'),
                greedy_arcs=(greedy or {}).get('n_arcs'),
                greedy_bends=(greedy or {}).get('n_arcs'),
                greedy_multi_arc_regions=(greedy or {}).get('n_multi_arc_regions'),
                shortest_length_mm=(shortest or {}).get('length_mm'),
                shortest_family=(shortest or {}).get('family'),
                shortest_y_span_mm=(shortest or {}).get('y_span_mm'),
                shortest_bbox_area_mm2=(shortest or {}).get('bbox_area_mm2'),
                smallest_box_area_mm2=(smallest_box or {}).get('bbox_area_mm2'),
                smallest_box_family=(smallest_box or {}).get('family'),
                smallest_box_length_mm=(smallest_box or {}).get('length_mm'),
            ))
            print('d=%2d %-3s n=%3d families=%s greedy=%s len=%s y_span=%s '
                  'bbox=%s arcs=%s' % (
                      offset, label, len(rows), ','.join(families),
                      (greedy or {}).get('family'),
                      (greedy or {}).get('length_mm'),
                      (greedy or {}).get('y_span_mm'),
                      (greedy or {}).get('bbox_area_mm2'),
                      (greedy or {}).get('n_arcs')))

    # analytic grammar relations (frozen move algebra, layer2d._opposite_specs)
    analytic = []
    for offset in OFFSETS:
        d = float(offset)
        row = dict(offset_mm=offset, two_R_mm=2 * R15)
        if d < 2 * R15 - 1e-9:
            theta = math.acos(1.0 - d / (2.0 * R15))
            row['short_s_possible'] = True
            row['short_s_theta_rad'] = round(theta, 9)
            row['short_s_advance_mm'] = round(2 * R15 * math.sin(theta), 6)
            row['short_s_length_mm'] = round(2 * R15 * theta, 6)
            row['z_block_min_shift_mm'] = 2 * R15
        else:
            row['short_s_possible'] = False
            row['short_s_theta_rad'] = None
            row['short_s_advance_mm'] = None
            row['short_s_length_mm'] = None
            row['z_block_min_shift_mm'] = 2 * R15
        row['z_block_w_mm'] = round(max(0.0, d - 2 * R15), 6)
        row['detour_extra_advance_mm'] = 4 * R15
        analytic.append(row)

    with (out / ('param_2r_candidates%s.csv' % suffix)).open('w', encoding='utf-8',
                                                newline='') as handle:
        fields = ['arm', 'offset_mm', 'relation_2R', 'family', 'moves',
                  'length_mm', 'arc_length_mm', 'x_span_mm', 'y_span_mm',
                  'bbox_area_mm2', 'n_arcs', 'n_lines', 'min_radius_mm',
                  'n_multi_arc_regions', 'x_min_mm', 'x_max_mm']
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for row in all_rows:
            writer.writerow(row)
    with (out / ('param_2r_summary%s.csv' % suffix)).open('w', encoding='utf-8',
                                             newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0].keys()),
                                extrasaction='ignore')
        writer.writeheader()
        for row in summary:
            flat = dict(row)
            flat['families'] = '|'.join(row['families'])
            flat['frame'] = json.dumps(row['frame'], ensure_ascii=False)
            writer.writerow(flat)
    with (out / ('param_2r_analytic%s.csv' % suffix)).open('w', encoding='utf-8',
                                              newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(analytic[0].keys()))
        writer.writeheader()
        for row in analytic:
            writer.writerow(row)
    (out / ('param_2r%s.json' % suffix)).write_text(json.dumps(
        dict(schema='g4_multi_arc_param_2r_v1', r15_mm=R15,
             two_r_mm=2 * R15, travel_mm=TRAVEL, start_pose=list(A),
             offsets_mm=OFFSETS, summary=summary, analytic=analytic,
             n_candidates_total=len(all_rows)), ensure_ascii=False, indent=1),
        encoding='utf-8')
    print('\nwrote %s' % (out / ('param_2r%s.json' % suffix)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
