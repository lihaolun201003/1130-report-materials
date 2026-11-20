# -*- coding: utf-8 -*-
"""Exact route (re)construction for the XYZ joint router.

Every candidate route is assembled from **exact** R15 geometry only:

* interface lead  : straight flat at the interface height;
* fanout          : two-arc R15 S-curve (``fsd25d.path3d.make_transition``);
* body            : one or more flat parts (line/R15-arc primitives) that may
                    sit on different physical heights, connected by more
                    two-arc R15 S-curves.

No polyline approximation is ever produced: a candidate that cannot be built
with exact primitives raises :class:`BuilderError`.
"""
from __future__ import annotations

import copy
import math

from .. import assemble as A
from .. import common as C
from .. import fanout as F
from ..native3d import common as N
from ..native3d import excursion2 as EX
from ..native3d import route_model as RM
from ..reheight21 import model as M

R15 = float(C.MIN_BEND_RADIUS_MM)
MIN_LEAD_MM = float(F.MIN_LEAD_MM)
LEAD_CANDIDATES = tuple(float(v) for v in F.LEAD_CANDIDATES)
INTERFACE_PLANE = {'z1': 1001, 'z2': 1002}
BODY_PLANE_IDS = tuple(int(pid) for pid in M.body_plane_ids())
PLANE_IDS = tuple(int(pid) for pid in M.PLANE_IDS)
PLANE_Z = {int(pid): float(M.plane_z(pid)) for pid in M.PLANE_IDS}
PLANE_LABEL = {int(pid): str(M.plane_label(pid)) for pid in M.PLANE_IDS}


class BuilderError(RuntimeError):
    def __init__(self, route_id, reason, detail=None):
        super().__init__('route %s: %s' % (route_id, reason))
        self.route_id = int(route_id)
        self.reason = str(reason)
        self.detail = dict(detail or {})


def interface_z(plane):
    return float(M.interface_z(plane))


def plane_z(plane_id):
    return float(PLANE_Z[int(plane_id)])


def normalized_rows(assignment_rows, stack=None):
    """Numeric planner rows from the assignment CSV rows."""
    return F.normalize_rows(assignment_rows, stack=stack or M.layer_stack())


def row_for_target(row, layer_id, z_mm):
    """Copy of a planner row retargeted at ``(layer_id, z_mm)``."""
    out = dict(row)
    out['target_layer'] = int(layer_id)
    out['target_z_mm'] = float(z_mm)
    z0 = float(row['interface_z_mm'])
    out['needs_transition'] = abs(float(z_mm) - z0) > 1e-12
    if not out['needs_transition']:
        out['direction'] = 'direct'
        out['target_z_mm'] = z0
    else:
        out['direction'] = 'down' if float(z_mm) < z0 else 'up'
    return out


def _finalize(route, row):
    """Recompute every derived field from the real parts and tag the route."""
    plane = str(row.get('plane'))
    route = N.rebuild_route_metadata(route, interface_z=interface_z(plane))
    route.pop('excursions', None)
    route['manual_group'] = str(row.get('manual_group') or '')
    route['relation'] = str(row.get('relation') or row.get('relation_geom') or '')
    route['layer_role'] = str(row.get('layer_role') or '')
    route['source_endpoint'] = str(row.get('source_endpoint'))
    route['target_endpoint'] = str(row.get('target_endpoint'))
    route['source_side'] = row.get('source_side')
    route['target_side'] = row.get('target_side')
    # ``assemble_route`` already resolved the true endpoint rows; only override
    # when the planner row carries an explicit value.
    if row.get('source_row') not in (None, ''):
        route['source_row'] = row.get('source_row')
    if row.get('target_row') not in (None, ''):
        route['target_row'] = row.get('target_row')
    route['plane'] = plane
    route['direct'] = int(route.get('n_transitions') or 0) == 0
    route['needs_transition'] = not bool(route['direct'])
    route['target_plane'] = int(route['target_layer'])
    route['target_plane_label'] = str(PLANE_LABEL.get(int(route['target_layer']),
                                                      ''))
    route = RM.tag_parts(route)
    structural = RM.structure_errors(route)
    if structural:
        raise BuilderError(route['route_id'], 'structure', dict(errors=structural[:6]))
    return route


def transition_record(row, role, layer_id, z_mm, lead):
    records = F.candidate_transitions(row, role, int(layer_id), leads=(float(lead),),
                                      target_z=float(z_mm))
    if not records:
        raise BuilderError(row['route_id'], 'no_transition_record',
                           dict(role=role, lead=lead))
    return records[0]


def build_lifted(row, layer_id, z_mm, lead_s, lead_t, body_primitives):
    """Full route: lead + S-curve + new body + S-curve + lead at ``(layer, z)``."""
    row2 = row_for_target(row, layer_id, z_mm)
    if not row2['needs_transition']:
        raise BuilderError(row['route_id'], 'lifted_route_without_height_change')
    source = transition_record(row2, 'source', layer_id, z_mm, lead_s)
    target = transition_record(row2, 'target', layer_id, z_mm, lead_t)
    try:
        route = A.assemble_route(row2, source, target,
                                 [dict(prim) for prim in body_primitives])
    except A.AssemblyError as error:
        raise BuilderError(row['route_id'], error.reason, error.detail)
    route = _finalize(route, row2)
    route['lead_source_mm'] = float(lead_s)
    route['lead_target_mm'] = float(lead_t)
    return route


def build_direct(row, body_primitives):
    """Interface-direct route: one flat body at the interface height."""
    plane = str(row.get('plane'))
    layer_id = int(INTERFACE_PLANE[plane])
    z0 = interface_z(plane)
    row2 = row_for_target(row, layer_id, z0)
    try:
        route = A.assemble_route(row2, None, None,
                                 [dict(prim) for prim in body_primitives])
    except A.AssemblyError as error:
        raise BuilderError(row['route_id'], error.reason, error.detail)
    route = _finalize(route, row2)
    route['lead_source_mm'] = 0.0
    route['lead_target_mm'] = 0.0
    return route


def body_task(row, layer_id, z_mm, lead_s, lead_t):
    """Landing task ``{A, dA, B, dB, ...}`` of a lifted body at ``(layer, z)``."""
    row2 = row_for_target(row, layer_id, z_mm)
    source = transition_record(row2, 'source', layer_id, z_mm, lead_s)
    target = transition_record(row2, 'target', layer_id, z_mm, lead_t)
    A_xy = (float(source['end_xy'][0]), float(source['end_xy'][1]))
    B_xy = (float(target['end_xy'][0]), float(target['end_xy'][1]))
    dA = (float(source['direction'][0]), float(source['direction'][1]))
    dB = (float(target['direction'][0]), float(target['direction'][1]))
    task = dict(route_id=int(row['route_id']),
                A=A_xy, dA=dA, B=B_xy, dB=dB,
                relation=str(row.get('relation') or ''),
                manual_group=str(row.get('manual_group') or ''),
                source_side=row.get('source_side'),
                target_side=row.get('target_side'))
    return task, source, target


def direct_task(row):
    """Landing task of an interface-direct body (starts/ends exactly at ports)."""
    A_xy = (float(row['source_xy'][0]), float(row['source_xy'][1]))
    B_xy = (float(row['target_xy'][0]), float(row['target_xy'][1]))
    dA = (float(row['source_inward'][0]), float(row['source_inward'][1]))
    dB = (float(row['target_inward'][0]), float(row['target_inward'][1]))
    return dict(route_id=int(row['route_id']),
                A=A_xy, dA=dA, B=B_xy, dB=dB,
                relation=str(row.get('relation') or ''),
                manual_group=str(row.get('manual_group') or ''),
                source_side=row.get('source_side'),
                target_side=row.get('target_side'))


# ------------------------------------------------------------------ fanout keep
def body_part_indices(route):
    return list(N.body_flat_indices(route))


def lead_lengths(route):
    if int(route.get('n_transitions') or 0) == 0:
        return 0.0, 0.0
    parts = route.get('parts') or []
    lead_s = float(parts[0]['length_mm']) if parts and parts[0]['kind'] == 'flat' else 0.0
    lead_t = float(parts[-1]['length_mm']) if parts and parts[-1]['kind'] == 'flat' else 0.0
    return lead_s, lead_t


def transition_footprints(route):
    parts = route.get('parts') or []
    values = [float(part.get('footprint_mm') or 0.0) for part in parts
              if part.get('kind') == 'transition']
    return values


def replace_body_keep_fanout(route, row, body_index, new_primitives):
    """Keep both fanout transitions and both leads, replace one body flat."""
    route = copy.deepcopy(route)
    parts = route['parts']
    body = parts[body_index]
    if body['kind'] != 'flat':
        raise BuilderError(route['route_id'], 'replace_body_not_flat')
    prims = [dict(prim) for prim in new_primitives]
    layer_id = int(route['target_layer'])
    z_mm = float(route['target_z_mm'])
    new_body = RM.make_flat(z_mm, prims, tag='body', layer_id=layer_id)
    parts[body_index] = new_body
    route['parts'] = parts
    # structural checks (pose continuity) are done by _finalize
    route = _finalize(route, row)
    lead_s, lead_t = lead_lengths(route)
    route['lead_source_mm'] = lead_s
    route['lead_target_mm'] = lead_t
    return route


def shift_height_keep_xy(route, row, layer_id, z_mm):
    """G2 contract: identical XY body, new physical height, rebuilt fanout.

    The interface leads absorb the footprint change so that both body landing
    points (and therefore every XY body primitive) stay exactly where they were.
    """
    route = copy.deepcopy(route)
    z_new = float(z_mm)
    z_old = float(route['target_z_mm'])
    if abs(z_new - z_old) <= 1e-12:
        raise BuilderError(route['route_id'], 'same_height')
    body_indices = body_part_indices(route)
    if len(body_indices) != 1:
        raise BuilderError(route['route_id'], 'multi_body_route_not_supported')
    body = route['parts'][body_indices[0]]
    if abs(float(body['z_mm']) - z_old) > 1e-9:
        raise BuilderError(route['route_id'], 'body_height_mismatch')
    prims = [dict(prim) for prim in body['primitives']]
    lead_s, lead_t = lead_lengths(route)
    footprints = transition_footprints(route)
    if len(footprints) != 2:
        raise BuilderError(route['route_id'], 'unexpected_transition_count')
    z0 = interface_z(row.get('plane'))
    f_old = float(footprints[0])
    f_new = abs(z_new - z0)
    from ..native3d import transition as T
    f_new = T.transition_footprint(z_new - z0, radius=R15)
    lead_s_new = lead_s + f_old - f_new
    lead_t_new = lead_t + f_old - f_new
    if lead_s_new < MIN_LEAD_MM - 1e-12 or lead_t_new < MIN_LEAD_MM - 1e-12:
        raise BuilderError(route['route_id'], 'lead_below_minimum',
                           dict(lead_source=lead_s_new, lead_target=lead_t_new,
                                f_old=f_old, f_new=f_new))
    return build_lifted(row, layer_id, z_new, lead_s_new, lead_t_new, prims)


def insert_height_plan(route, row, body_index, s0, s1, z_to):
    """Insert one exact arc-spanning excursion into the route body."""
    route = copy.deepcopy(route)
    plane = str(row.get('plane'))
    built = EX.insert_excursion_general(route, int(body_index), float(s0),
                                        float(s1), float(z_to),
                                        interface_z=interface_z(plane))
    new_route = built['route']
    new_route['manual_group'] = str(row.get('manual_group') or '')
    new_route['relation'] = str(row.get('relation') or '')
    new_route['layer_role'] = str(row.get('layer_role') or '')
    new_route['target_plane'] = int(new_route['target_layer'])
    new_route['target_plane_label'] = str(PLANE_LABEL.get(
        int(new_route['target_layer']), ''))
    new_route['direct'] = False
    structural = RM.structure_errors(new_route)
    if structural:
        raise BuilderError(route['route_id'], 'structure',
                           dict(errors=structural[:6]))
    return new_route, built['excursion']


# ------------------------------------------------------------------ signatures
def prim_signature(prim):
    if prim.get('kind') == 'line':
        return ('line', tuple(round(float(v), 6) for v in prim['p0']),
                tuple(round(float(v), 6) for v in prim['p1']))
    return ('arc', tuple(round(float(v), 6) for v in prim['p0']),
            tuple(round(float(v), 6) for v in prim['p1']),
            tuple(round(float(v), 6) for v in prim['center']),
            round(float(prim['radius']), 6), round(float(prim['start_angle']), 9),
            round(float(prim['sweep']), 9))


def route_signature(route):
    out = []
    for part in route.get('parts') or ():
        if part['kind'] == 'flat':
            out.append(('flat', round(float(part['z_mm']), 9),
                        tuple(prim_signature(prim) for prim in part['primitives'])))
        else:
            out.append(('transition', tuple(round(float(v), 6) for v in part['start']),
                        tuple(round(float(v), 6) for v in part['direction']),
                        round(float(part['z0']), 9), round(float(part['z1']), 9)))
    return tuple(out)


def body_xy_signature(route):
    """XY primitives of the body flat(s) in traversal order (G2 contract)."""
    out = []
    for index in body_part_indices(route):
        part = route['parts'][index]
        for prim in part['primitives']:
            out.append(prim_signature(prim))
    return tuple(out)


def path_total(primitives):
    from ..fsd25d import path3d as P3
    return float(P3.path_length(primitives))
