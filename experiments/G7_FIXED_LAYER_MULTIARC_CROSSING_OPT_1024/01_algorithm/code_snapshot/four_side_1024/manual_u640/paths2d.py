# -*- coding: utf-8 -*-
"""2D-chain / 3D-route assembly helpers shared by the U and automatic routers.

A *route* produced here is the existing ``l3d`` schema used by
``four_side_1024.l3d.world.World`` and the plotting code::

    {route_id, plane, source_row, target_row, source_port, target_port,
     start_z_mm, end_z_mm, layer_sequence, layer_z_sequence, n_transitions,
     lifted, layers_used, xy_length_mm, length_mm, z_span_mm, parts}

plus this round's identity fields (``uid``, ``original_route_id``, ``dataset``,
``assignment``, ``logical_layer`` ...).  ``parts`` is a list of

* ``dict(kind='flat', layer_id, z_mm, length_mm, primitives=[...])``
* ``dict(kind='transition', start, end, z0, z1, ...)``

The XY path is a chain of the existing D56 primitives
(``kind`` = ``line``/``arc``, axis-aligned lines, exact-radius arcs).  A route is
always built from the same XY chain: the flat parts are sub-chains of it and the
transitions are the elevation S-curves placed on its straight segments by
:func:`four_side_1024.l3d.paths.build_route_l3d`.
"""
from __future__ import annotations

import math

from four_side_1024.fsd25d import path3d as P3
from four_side_1024.l3d import paths as L3D_PATHS

from . import config as C
from . import inputs as I


# ---------------------------------------------------------------------------
# port poses
# ---------------------------------------------------------------------------
def start_dir(record):
    """Travel direction at the source port (always the inward board normal)."""
    return list(record['source_endpoint']['inward'])


def end_dir(record):
    """Travel direction at the target port (outward: minus the inward normal)."""
    inward = record['target_endpoint']['inward']
    return [-float(inward[0]), -float(inward[1])]


def port_meta(record, start=None, end=None):
    """``port_meta`` dict required by ``l3d.paths.build_route_l3d``."""
    source = record['source_endpoint']
    target = record['target_endpoint']
    return dict(
        source_port=dict(xy=list(source['xy']), z_mm=float(source['z_mm']),
                         layer_id=C.INTERFACE_LAYER_ID),
        target_port=dict(xy=list(target['xy']), z_mm=float(target['z_mm']),
                         layer_id=C.INTERFACE_LAYER_ID),
        source_row=int(source['row']),
        target_row=int(target['row']),
        start_dir=list(start_dir(record) if start is None else start),
        end_dir=list(end_dir(record) if end is None else end),
    )


# ---------------------------------------------------------------------------
# 2D chain validation
# ---------------------------------------------------------------------------
def validate_2d_chain(primitives, record, radius=None):
    """Frozen canonical D56 validation of one XY chain against its two ports."""
    from four_side_1024.fslw import geom
    radius = float(C.RADIUS_MM if radius is None else radius)
    return geom.canonical_validate(
        primitives, record['source_xy'], record['target_xy'],
        start_dir(record), end_dir(record),
        radius=radius, width=C.WIDTH_MM)


def chain_length(primitives):
    return float(P3.path_length(primitives))


def min_arc_radius(primitives):
    radii = [float(prim['radius']) for prim in primitives
             if prim.get('kind') == 'arc']
    return min(radii) if radii else None


def bend_count(primitives):
    return sum(1 for prim in primitives if prim.get('kind') == 'arc')


def chain_start(primitives):
    return tuple(primitives[0]['p0'])


def chain_end(primitives):
    return tuple(primitives[-1]['p1'])


# ---------------------------------------------------------------------------
# route assembly
# ---------------------------------------------------------------------------
def _identity(record):
    """Identity/metadata fields carried on every produced route."""
    return dict(
        uid=record['uid'],
        original_route_id=int(record['original_route_id']),
        dataset=record['dataset'],
        plane=record['dataset'],
        relation=record['relation'],
        source_side=record['source_side'],
        target_side=record['target_side'],
        source_port_id=record['source_port_id'],
        target_port_id=record['target_port_id'],
        source_endpoint_id=record['source_endpoint_id'],
        target_endpoint_id=record['target_endpoint_id'],
        source_xy_mm=list(record['source_xy']),
        target_xy_mm=list(record['target_xy']),
        source_z_mm=float(record['source_z_mm']),
        target_z_mm=float(record['target_z_mm']),
        csv_source_row=int(record['csv_source_row']),
        csv_target_row=int(record['csv_target_row']),
        physical_source_row=int(record['source_row']),
        physical_target_row=int(record['target_row']),
        assignment=record['assignment'],
        manual_group=record['manual_group'],
        manual_group_order=record['manual_group_order'],
        u_pair=record['u_pair'],
        csv_layer_tag=record['csv_layer_tag'],
        csv_assigned_layer=record['assigned_layer_csv'],
        cross_dataset_same_port_pair=record['cross_dataset_same_port_pair'],
    )


def _base_route(record, primitives, layer_sequence, layer_z_sequence,
                target_layer, variant=0):
    """Build one ``l3d`` route with the existing builder; attach identity."""
    if not primitives:
        raise ValueError(f'{record["uid"]}: empty 2D chain')
    route = L3D_PATHS.build_route_l3d(
        record['internal_id'], record['dataset'], primitives,
        layer_sequence, layer_z_sequence, port_meta(record),
        radius=float(C.RADIUS_MM), variant=int(variant))
    if route is None:
        return None
    out = dict(route)
    out.update(_identity(record))
    out['assignment'] = record['assignment']
    out['logical_layer'] = int(target_layer)
    out['target_layer'] = int(target_layer)
    out['primitives_2d'] = [dict(prim) for prim in primitives]
    out['xy_chain_length_mm'] = chain_length(primitives)
    out['min_bend_radius_mm'] = min_arc_radius(primitives)
    out['bend_count'] = bend_count(primitives)
    out['status'] = 'routed'
    out['failure_reason'] = None
    return out


def build_flat_route(record, primitives):
    """Flat L1 route (interface layer at the data-source physical height)."""
    z = float(record['source_z_mm'])
    return _base_route(record, primitives, [C.INTERFACE_LAYER_ID], [z],
                       C.INTERFACE_LAYER_ID)


def build_lifted_route(record, primitives, target_layer, variant=0):
    """Route whose flat run sits on ``target_layer`` (L2..Lmax).

    ``target_layer == 1`` degenerates to :func:`build_flat_route`.
    """
    target_layer = int(target_layer)
    if target_layer == C.INTERFACE_LAYER_ID:
        return build_flat_route(record, primitives)
    z0 = float(record['source_z_mm'])
    z1 = float(C.layer_z(target_layer))
    sequence = [C.INTERFACE_LAYER_ID, target_layer, C.INTERFACE_LAYER_ID]
    return _base_route(record, primitives, sequence, [z0, z1, z0],
                       target_layer, variant=variant)


# ---------------------------------------------------------------------------
# derived geometry / metrics
# ---------------------------------------------------------------------------
def transition_length(route):
    return float(sum(part['length_mm'] for part in route['parts']
                     if part['kind'] == 'transition'))


def flat_length(route):
    return float(sum(part['length_mm'] for part in route['parts']
                     if part['kind'] == 'flat'))


def xy_projection(route):
    """XY chain of the route (transition XY chords make it continuous)."""
    chain = []
    for part in route['parts']:
        if part['kind'] == 'flat':
            chain.extend(dict(prim) for prim in part['primitives'])
        else:
            chain.append(dict(kind='line', p0=list(part['start']),
                              p1=list(part['end'])))
    return chain


def flat_chain(route, layer_id=None):
    """Concatenated XY chain of every flat part (optionally of one layer)."""
    chain = []
    for part in route['parts']:
        if part['kind'] != 'flat':
            continue
        if layer_id is not None and int(part['layer_id']) != int(layer_id):
            continue
        chain.extend(dict(prim) for prim in part['primitives'])
    return chain


def z_span(route):
    heights = []
    for part in route['parts']:
        if part['kind'] == 'flat':
            heights.append(float(part['z_mm']))
        else:
            heights.extend([float(part['z0']), float(part['z1'])])
    return (min(heights), max(heights))


def route_summary(route):
    """JSON/CSV-ready numeric summary of one routed record."""
    return dict(
        uid=route['uid'],
        internal_id=int(route['route_id']),
        original_route_id=int(route['original_route_id']),
        dataset=route['dataset'],
        relation=route['relation'],
        source_side=route['source_side'],
        target_side=route['target_side'],
        source_port_id=route['source_port_id'],
        target_port_id=route['target_port_id'],
        assignment=route['assignment'],
        manual_group=route.get('manual_group'),
        logical_layer=int(route['logical_layer']),
        target_layer=int(route['target_layer']),
        layer_sequence=list(route['layer_sequence']),
        layer_z_sequence=list(route['layer_z_sequence']),
        n_transitions=int(route['n_transitions']),
        xy_length_mm=float(route['xy_length_mm']),
        length_mm=float(route['length_mm']),
        flat_length_mm=flat_length(route),
        transition_length_mm=transition_length(route),
        min_bend_radius_mm=route.get('min_bend_radius_mm'),
        bend_count=int(route.get('bend_count') or 0),
        min_z_mm=z_span(route)[0],
        max_z_mm=z_span(route)[1],
        status=route.get('status', 'routed'),
        failure_reason=route.get('failure_reason'),
    )


def failed_record(record, reason, logical_layer=None, detail=None):
    """Uniform failed-route record (kept in the output, never dropped)."""
    item = _identity(record)
    item.update(
        route_id=record['internal_id'],
        logical_layer=(None if logical_layer is None else int(logical_layer)),
        target_layer=(None if logical_layer is None else int(logical_layer)),
        start_z_mm=float(record['source_z_mm']),
        end_z_mm=float(record['target_z_mm']),
        layer_sequence=[],
        layer_z_sequence=[],
        n_transitions=0,
        lifted=False,
        layers_used=[],
        xy_length_mm=None,
        length_mm=None,
        z_span_mm=None,
        parts=[],
        primitives_2d=[],
        min_bend_radius_mm=None,
        bend_count=0,
        status='failed',
        failure_reason=str(reason),
        failure_detail=detail,
    )
    if logical_layer is None:
        item['logical_layer'] = None
    return item
