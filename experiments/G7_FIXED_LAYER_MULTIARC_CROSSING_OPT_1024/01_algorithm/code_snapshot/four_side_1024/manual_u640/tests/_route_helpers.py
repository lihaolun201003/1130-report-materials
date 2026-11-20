# -*- coding: utf-8 -*-
"""Shared helpers for the manual_u640 verification tests.

Everything here builds *small synthetic inputs* in ``tmp_path`` so that the
tests never depend on ``outputs/`` or on the routers being finished.
"""
from __future__ import annotations

import csv
import math

from four_side_1024.manual_u640 import config as C
from four_side_1024.manual_u640 import inputs as I
from four_side_1024.manual_u640 import paths2d as P
from four_side_1024.manual_u640 import stack as ST

#: the exact CSV header of the authoritative 640-record input
CSV_FIELDS = [
    'input_dataset', 'route_uid', 'route_id',
    'source_side', 'source_connector', 'source_row', 'source_column',
    'source_channel',
    'target_side', 'target_connector', 'target_row', 'target_column',
    'target_channel',
    'relation', 'source_port_id', 'target_port_id',
    'source_x_mm', 'source_y_mm', 'target_x_mm', 'target_y_mm',
    'layer', 'u_pair', 'manual_group', 'manual_group_order',
    'u_logical_layer', 'assigned_layer', 'routing_method', 'routing_status',
    'cross_dataset_same_port_pair',
]


def _row(dataset, route_id, side, source, target, assignment,
         assigned_layer='', manual_group='', relation='same'):
    """One CSV row dict; ``source``/``target`` are ``(connector, column)``."""
    source_port = f'{source[0]}:1:{source[1]}'
    target_port = f'{target[0]}:1:{target[1]}'
    source_xy = I.endpoint_xy(*source)
    target_xy = I.endpoint_xy(*target)
    return dict(
        input_dataset=dataset,
        route_uid=f'{dataset}:{route_id}',
        route_id=route_id,
        source_side=side,
        source_connector=source[0], source_row=1, source_column=source[1],
        source_channel=1,
        target_side=side if relation == 'same' else side,
        target_connector=target[0], target_row=1, target_column=target[1],
        target_channel=1,
        relation=relation,
        source_port_id=source_port, target_port_id=target_port,
        source_x_mm=f'{source_xy[0]:.9f}', source_y_mm=f'{source_xy[1]:.9f}',
        target_x_mm=f'{target_xy[0]:.9f}', target_y_mm=f'{target_xy[1]:.9f}',
        layer=dataset,
        u_pair='', manual_group=manual_group, manual_group_order='',
        u_logical_layer=assigned_layer,
        assigned_layer=assigned_layer,
        routing_method=assignment,
        routing_status='MANUAL_FIXED_U' if assignment == 'manual_fixed_u'
        else 'DEFER_TO_EXISTING_ALGORITHM',
        cross_dataset_same_port_pair='NO',
    )


def write_input_csv(path, rows):
    """Write a tiny CSV with the authoritative header and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def make_input(tmp_path, specs, name='fake_input.csv'):
    """Build an ``InputData`` from ``specs`` (list of ``_row`` keyword dicts).

    Every spec is one ``manual_fixed_u`` L1 record unless it overrides the
    assignment.  The returned object has the same public API as
    ``inputs.load_inputs()`` (records, by_uid, manual_groups, validation, ...).
    """
    rows = []
    for index, spec in enumerate(specs, 1):
        spec = dict(spec)
        spec.setdefault('dataset', 'z1')
        spec.setdefault('side', 'N')
        spec.setdefault('assignment', 'manual_fixed_u')
        spec.setdefault('assigned_layer', 'L1')
        spec.setdefault('manual_group', 'NS-1')
        rows.append(_row(route_id=spec.pop('route_id', index), **spec))
    path = write_input_csv(tmp_path / name, rows)
    return I.load_inputs(path)


def stack_object():
    return ST.LayerStack()


# ---------------------------------------------------------------------------
# synthetic U-turn geometry (only the N side is used by the tests)
# ---------------------------------------------------------------------------
def build_u_primitives(record, depth_offset=0.0, radius=None):
    """Quarter-pair U-turn between two same-side ports.

    Works for every board side: the lateral direction and the turn sense are
    chosen from the two port positions.  ``depth_offset`` is the straight
    port-leg length in front of the U arcs; the centre-line depth of the turn
    is ``radius + depth_offset``.
    """
    radius = float(C.RADIUS_MM if radius is None else radius)
    p = (float(record['source_xy'][0]), float(record['source_xy'][1]))
    q = (float(record['target_xy'][0]), float(record['target_xy'][1]))
    inward = record['source_endpoint']['inward']
    u = (float(inward[0]), float(inward[1]))
    lateral_ccw = (-u[1], u[0])           # CCW rotation of the inward direction
    separation = ((q[0] - p[0]) * lateral_ccw[0]
                  + (q[1] - p[1]) * lateral_ccw[1])
    if abs(separation) <= 2.0 * radius + 1e-9:
        raise ValueError('ports are too close for a quarter-pair U at this R')
    if separation >= 0.0:
        v = lateral_ccw
        sweep = math.pi / 2.0
    else:
        v = (-lateral_ccw[0], -lateral_ccw[1])
        sweep = -math.pi / 2.0
    separation = abs(separation)
    depth = float(depth_offset)

    def add(point, vector, distance):
        return (point[0] + vector[0] * distance, point[1] + vector[1] * distance)

    p1 = add(p, u, depth)
    c1 = add(p1, v, radius)
    angle1 = math.atan2(p1[1] - c1[1], p1[0] - c1[0])
    e1 = (c1[0] + radius * math.cos(angle1 + sweep),
          c1[1] + radius * math.sin(angle1 + sweep))
    mid = add(e1, v, separation - 2.0 * radius)
    q_leg_end = add(q, u, depth)
    turn_normal = ((v[1], -v[0]) if sweep < 0.0 else (-v[1], v[0]))
    c2 = add(mid, turn_normal, radius)
    angle2 = math.atan2(mid[1] - c2[1], mid[0] - c2[0])
    e2 = (c2[0] + radius * math.cos(angle2 + sweep),
          c2[1] + radius * math.sin(angle2 + sweep))

    primitives = []
    if depth > 1e-12:
        primitives.append(dict(kind='line', p0=[p[0], p[1]],
                               p1=[p1[0], p1[1]], layer=0))
    primitives.append(dict(kind='arc', p0=[p1[0], p1[1]], p1=[e1[0], e1[1]],
                           center=[c1[0], c1[1]], radius=radius,
                           start_angle=angle1, sweep=sweep, layer=0))
    if (separation - 2.0 * radius) > 1e-12:
        primitives.append(dict(kind='line', p0=[e1[0], e1[1]],
                               p1=[mid[0], mid[1]], layer=0))
    primitives.append(dict(kind='arc', p0=[mid[0], mid[1]], p1=[e2[0], e2[1]],
                           center=[c2[0], c2[1]], radius=radius,
                           start_angle=angle2, sweep=sweep, layer=0))
    if depth > 1e-12:
        primitives.append(dict(kind='line', p0=[e2[0], e2[1]],
                               p1=[q[0], q[1]], layer=0))
    return primitives


def build_u_route(record, depth_offset=0.0, radius=None):
    primitives = build_u_primitives(record, depth_offset=depth_offset,
                                    radius=radius)
    ok, errors = P.validate_2d_chain(primitives, record, radius=radius)
    if not ok:
        raise AssertionError(f'synthetic U chain is not canonical: {errors}')
    return P.build_flat_route(record, primitives)


def build_u_routes_from_records(records, depth_offsets=None):
    depth_offsets = depth_offsets or {}
    return [build_u_route(record, depth_offset=depth_offsets.get(record['uid'], 0.0))
            for record in records]
