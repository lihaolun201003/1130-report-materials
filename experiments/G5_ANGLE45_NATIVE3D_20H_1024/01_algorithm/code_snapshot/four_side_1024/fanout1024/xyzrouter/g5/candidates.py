# -*- coding: utf-8 -*-
"""G5 candidate moves: exact, endpoint-preserving route reshaping.

All three families keep the two port poses (lead start/end + directions), exact
R15 arcs, tangent continuity, the 20 physical heights and the glass envelope.

A. ``corridor_variants``  -- re-parameterise the body's rectilinear runs.  The
   body is a chain of axis-aligned runs and R15 arcs; moving ``delta`` mm of
   length from one run to the next *parallel* run of the same body translates
   the whole block in between along that axis.  The end pose is invariant by
   construction and the total length is unchanged.
B. ``reheight_variants``  -- move the body to another physical height.  Direct
   routes (no transition) only change ``z``; transitioned routes rebuild both
   R15 S-curves and absorb the footprint change in the first/last body runs with
   an exact 2x2 closure solve.
C. ``excursion_variants`` -- an R15 native-3D over/under-pass on one straight
   run: prefix (z) | up S | middle (z') | down S | suffix (z).  This removes a
   same-height crossing locally without touching the rest of the route.
"""
from __future__ import annotations

import copy
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024.xyzrouter.g5 import model as G5
from four_side_1024.fanout1024.native3d import transition as T

R15 = 15.0


# ===========================================================================
# body discovery / metadata
# ===========================================================================
def body_part_indices(route):
    """Indices of the body flat parts (lead flats at the interface excluded)."""
    flats = [i for i, part in enumerate(route.get('parts') or ())
             if part.get('kind') == 'flat']
    if int(route.get('n_transitions') or 0) == 0:
        return list(flats)
    if not flats:
        return []
    return list(flats[1:-1])


def single_body(route):
    indices = body_part_indices(route)
    return indices[0] if len(indices) == 1 else None


def body_parts(route):
    return list(body_part_indices(route))


def part_at_point(route, point):
    """Body flat part index whose chain passes through ``point`` (or None)."""
    for index in body_parts(route):
        if line_span(route, index, point) is not None:
            return index
    return None


def tag_parts(route):
    parts = route['parts']
    flats = [i for i, part in enumerate(parts) if part['kind'] == 'flat']
    transitions = [i for i, part in enumerate(parts)
                   if part['kind'] == 'transition']
    if not transitions:
        for index in flats:
            parts[index].setdefault('tag', 'body')
        return route
    lead = set()
    if parts[0]['kind'] == 'flat':
        lead.add(0)
    if parts[-1]['kind'] == 'flat':
        lead.add(len(parts) - 1)
    for index in flats:
        parts[index].setdefault('tag', 'lead' if index in lead else 'body')
    parts[min(transitions)]['tag'] = (parts[min(transitions)].get('tag')
                                      or 'fanout')
    parts[max(transitions)]['tag'] = (parts[max(transitions)].get('tag')
                                      or 'fanout')
    for index in transitions[1:-1]:
        parts[index]['tag'] = parts[index].get('tag') or 'mid'
    return route


def _prim_length(prim):
    if prim['kind'] == 'line':
        return math.dist(tuple(prim['p0']), tuple(prim['p1']))
    return abs(float(prim['radius']) * float(prim['sweep']))


def rebuild_metadata(route):
    """Recompute the derived route fields with the G5 20-height table."""
    route = copy.deepcopy(route)
    parts = route['parts']
    body_indices = body_part_indices(route)
    body_heights = [float(parts[i]['z_mm']) for i in body_indices]
    transitions = [(i, part) for i, part in enumerate(parts)
                   if part['kind'] == 'transition']
    n_transitions = len(transitions)
    mid = [dict(part_index=i, from_z=float(part['z0']),
                to_z=float(part['z1']), tag=part.get('tag') or '')
           for i, part in transitions if (part.get('tag') or '') == 'mid']
    plane_ids = [int(G5.plane_of_z(z)) for z in body_heights]
    longest = (max(body_indices, key=lambda i: parts[i].get('length_mm') or 0.0)
               if body_indices else None)
    primary_z = (float(parts[longest]['z_mm']) if longest is not None
                 else (body_heights[0] if body_heights else 0.0))
    target_layer = int(G5.plane_of_z(primary_z))
    route['target_layer'] = target_layer
    route['target_plane'] = target_layer
    route['target_plane_label'] = G5.plane_label(primary_z)
    route['target_z_mm'] = primary_z
    interface_z = float(route.get('start_z_mm') or 0.0)
    if n_transitions == 0:
        route['layer_sequence'] = [target_layer]
        route['layer_z_sequence'] = [primary_z]
        route['layers_used'] = [target_layer]
        route['start_z_mm'] = primary_z
        route['end_z_mm'] = primary_z
        route['lifted'] = False
    else:
        route['layer_sequence'] = [1] + plane_ids + [1]
        route['layer_z_sequence'] = [interface_z] + body_heights + [interface_z]
        route['layers_used'] = [1] + sorted(set(plane_ids))
        route['start_z_mm'] = interface_z
        route['end_z_mm'] = interface_z
        route['lifted'] = True
    route['n_transitions'] = n_transitions
    route['n_mid_transitions'] = len(mid)
    route['native_3d'] = bool(mid) or bool(route.get('native_3d'))
    route['body_heights'] = body_heights
    route['mid_transitions'] = mid
    for part in parts:
        if part['kind'] == 'flat':
            part['length_mm'] = sum(_prim_length(prim)
                                    for prim in part['primitives'])
    total = sum(float(part.get('length_mm') or 0.0) for part in parts)
    route['length_mm'] = round(total, 9)
    xy = 0.0
    for part in parts:
        if part['kind'] == 'flat':
            xy += sum(_prim_length(prim) for prim in part['primitives'])
        else:
            xy += float(part.get('footprint_mm') or 0.0)
    route['xy_length_mm'] = round(xy, 9)
    if body_heights:
        route['z_span_mm'] = round(max(body_heights) - min(body_heights), 9)
    if n_transitions == 0:
        route['z_span_mm'] = 0.0
    return route


def _finalise(route):
    return tag_parts(rebuild_metadata(route))


# ===========================================================================
# primitive editing
# ===========================================================================
def _line_entries(prims):
    out = []
    for index, prim in enumerate(prims):
        if prim['kind'] != 'line':
            continue
        length = math.dist(tuple(prim['p0']), tuple(prim['p1']))
        if length <= 1e-9:
            continue
        direction = ((prim['p1'][0] - prim['p0'][0]) / length,
                     (prim['p1'][1] - prim['p0'][1]) / length)
        axis = 0 if abs(direction[0]) > 0.5 else 1
        out.append(dict(index=index, length=length, direction=direction,
                        axis=axis, sign=direction[axis]))
    return out


def _move(prim, dx, dy):
    prim = copy.deepcopy(prim)
    if prim['kind'] == 'line':
        prim['p0'] = [prim['p0'][0] + dx, prim['p0'][1] + dy]
        prim['p1'] = [prim['p1'][0] + dx, prim['p1'][1] + dy]
    else:
        prim['center'] = [prim['center'][0] + dx, prim['center'][1] + dy]
        prim['p0'] = [prim['p0'][0] + dx, prim['p0'][1] + dy]
        prim['p1'] = [prim['p1'][0] + dx, prim['p1'][1] + dy]
    return prim


def _translate(prims, delta, direction):
    return [_move(prim, direction[0] * delta, direction[1] * delta)
            for prim in prims]


def _translate_middle(prims, first, last, delta, direction):
    """Translate prims strictly between ``first`` and ``last`` (not the ends)."""
    dx = direction[0] * delta
    dy = direction[1] * delta
    out = []
    for index, prim in enumerate(prims):
        if first < index < last:
            out.append(_move(prim, dx, dy))
        else:
            out.append(copy.deepcopy(prim))
    return out


def _shift_downstream(prims, index, alpha, direction):
    """Lengthen ``prims[index]`` by ``alpha`` and translate all later prims."""
    dx = direction[0] * alpha
    dy = direction[1] * alpha
    out = []
    for i, prim in enumerate(prims):
        prim = copy.deepcopy(prim)
        if i == index:
            prim['p1'] = [prim['p1'][0] + dx, prim['p1'][1] + dy]
        elif i > index:
            prim = _move(prim, dx, dy)
        out.append(prim)
    return out


def _open_block(prims, first, last, delta, direction):
    """Shift the block (first,last) by ``delta``; keep both outer ends fixed."""
    dx = direction[0] * delta
    dy = direction[1] * delta
    out = []
    for index, prim in enumerate(prims):
        prim = copy.deepcopy(prim)
        if index == last:
            if prim['kind'] == 'line':
                prim['p0'] = [prim['p0'][0] + dx, prim['p0'][1] + dy]
            out.append(prim)
            continue
        if first < index < last:
            prim = _move(prim, dx, dy)
        out.append(prim)
    first_prim = out[first]
    first_prim['p1'] = [first_prim['p1'][0] + dx, first_prim['p1'][1] + dy]
    return out


# ===========================================================================
# A. corridor shift
# ===========================================================================
def corridor_shift(route, first_line, second_line, delta):
    index = single_body(route)
    if index is None:
        return None
    parts = copy.deepcopy(route['parts'])
    prims = parts[index]['primitives']
    entries = {entry['index']: entry for entry in _line_entries(prims)}
    if first_line not in entries or second_line not in entries:
        return None
    a = entries[first_line]
    b = entries[second_line]
    if a['axis'] != b['axis'] or first_line >= second_line:
        return None
    if a['sign'] * b['sign'] < 0:
        return None
    # signed bound checks: +delta lengthens `a`, shortens `b`
    if a['length'] + delta <= 0.05 or b['length'] - delta <= 0.05:
        return None
    prims = _open_block(prims, first_line, second_line, delta, a['direction'])
    parts[index]['primitives'] = prims
    new_route = copy.deepcopy(route)
    new_route['parts'] = parts
    return _finalise(new_route)


def corridor_variants(route, deltas, limit_per_route=60, min_length=0.6):
    index = single_body(route)
    if index is None:
        return
    prims = route['parts'][index]['primitives']
    entries = _line_entries(prims)
    produced = 0
    for pos in range(len(entries) - 1):
        a = entries[pos]
        for later in range(pos + 1, len(entries)):
            b = entries[later]
            if a['axis'] != b['axis'] or a['sign'] * b['sign'] < 0:
                continue
            for delta in deltas:
                if produced >= limit_per_route:
                    return
                if a['length'] + delta < min_length:
                    continue
                if b['length'] - delta < min_length:
                    continue
                new_route = corridor_shift(route, a['index'], b['index'], delta)
                if new_route is None:
                    continue
                produced += 1
                yield ('corridor:%d-%d:%+g' % (a['index'], b['index'], delta),
                       new_route)


# ===========================================================================
# B. re-height
# ===========================================================================
def reheight(route, z_new):
    z_new = float(z_new)
    if G5.plane_of_z(z_new) is None:
        return None
    index = single_body(route)
    if index is None:
        return None
    parts = copy.deepcopy(route['parts'])
    body = parts[index]
    z_old = float(body['z_mm'])
    if abs(z_old - z_new) < 1e-12:
        return None
    if int(route.get('n_transitions') or 0) == 0:
        # a DIRECT route lives at its interface height by contract: it has no
        # S-curve, so its body must stay on the interface plane.
        return None
    if len(parts) != 5:
        return None
    lead_in, up, _body, down, lead_out = parts
    if (lead_in['kind'] != 'flat' or up['kind'] != 'transition'
            or down['kind'] != 'transition' or lead_out['kind'] != 'flat'):
        return None
    start_dir = (float(up['direction'][0]), float(up['direction'][1]))
    end_dir = (float(down['direction'][0]), float(down['direction'][1]))
    z_in = float(lead_in['z_mm'])
    z_out = float(lead_out['z_mm'])
    fp_old = float(up['footprint_mm'])
    fp_new = T.transition_footprint(z_in - z_new)
    fp_out_old = float(down['footprint_mm'])
    fp_out_new = T.transition_footprint(z_out - z_new)
    prims = [dict(prim) for prim in body['primitives']]
    entries = _line_entries(prims)
    if len(entries) < 2:
        return None
    first = entries[0]
    last = entries[-1]
    if first['index'] == last['index']:
        return None
    # the whole body is translated so that its start follows the new S-curve
    delta_start = (fp_new - fp_old)
    shift = (start_dir[0] * delta_start, start_dir[1] * delta_start)
    prims = _translate(prims, delta_start, start_dir)
    # 2x2 closure on the two end runs
    rhs = (-end_dir[0] * (fp_out_new - fp_out_old) - shift[0],
           -end_dir[1] * (fp_out_new - fp_out_old) - shift[1])
    alpha = rhs[0] * first['direction'][0] + rhs[1] * first['direction'][1]
    beta = rhs[0] * last['direction'][0] + rhs[1] * last['direction'][1]
    residual = (rhs[0] - alpha * first['direction'][0]
                - beta * last['direction'][0],
                rhs[1] - alpha * first['direction'][1]
                - beta * last['direction'][1])
    if math.hypot(*residual) > 1e-9:
        return None
    if first['length'] + alpha <= 0.1:
        return None
    if last['index'] <= first['index']:
        return None
    prims = _shift_downstream(prims, first['index'], alpha, first['direction'])
    if last['length'] + beta <= 0.1:
        return None
    last_prim = prims[last['index']]
    last_prim['p1'] = [last_prim['p1'][0] + last['direction'][0] * beta,
                       last_prim['p1'][1] + last['direction'][1] * beta]
    body['primitives'] = prims
    body['z_mm'] = z_new
    body['layer_id'] = int(G5.plane_of_z(z_new))
    up_new = T.make_s_curve(tuple(up['start']), start_dir, z_in, z_new,
                            tag='fanout')
    body_end = None
    for prim in reversed(prims):
        if prim['kind'] in ('line', 'arc'):
            body_end = tuple(prim['p1'])
            break
    if body_end is None:
        return None
    down_new = T.make_s_curve(body_end, end_dir, z_new, z_out, tag='fanout')
    parts[1] = up_new
    parts[3] = down_new
    new_route = copy.deepcopy(route)
    new_route['parts'] = parts
    return _finalise(new_route)


def reheight_variants(route, heights=None):
    heights = heights if heights is not None else G5.all_heights()
    index = single_body(route)
    if index is not None:
        z_now = float(route['parts'][index]['z_mm'])
        heights = sorted(heights, key=lambda z: (abs(z - z_now), z))
    for z in heights:
        new_route = reheight(route, z)
        if new_route is None:
            continue
        yield ('reheight:%.6f' % z, new_route)


# ===========================================================================
# C. native-3D excursion on one straight run
# ===========================================================================
def excursion_on_line(route, part_index, s0, s1, z_to):
    parts = copy.deepcopy(route['parts'])
    body = parts[part_index]
    if body['kind'] != 'flat':
        return None
    prims = [dict(prim) for prim in body['primitives']]
    z_from = float(body['z_mm'])
    try:
        exc = T.build_excursion(prims, s0, s1, z_from, float(z_to))
    except Exception:  # noqa: BLE001
        return None
    new_parts = [copy.deepcopy(part) for part in parts[:part_index]]
    prefix = dict(kind='flat', layer_id=int(G5.plane_of_z(z_from)),
                  z_mm=z_from, tag='body', primitives=exc['prefix'])
    new_parts.append(prefix)
    up = dict(exc['up'])
    up['tag'] = 'mid'
    new_parts.append(up)
    middle = dict(kind='flat', layer_id=int(G5.plane_of_z(float(z_to))),
                  z_mm=float(z_to), tag='body',
                  primitives=[dict(exc['middle'])])
    new_parts.append(middle)
    down = dict(exc['down'])
    down['tag'] = 'mid'
    new_parts.append(down)
    suffix = dict(kind='flat', layer_id=int(G5.plane_of_z(z_from)),
                  z_mm=z_from, tag='body', primitives=exc['suffix'])
    new_parts.append(suffix)
    new_parts.extend(copy.deepcopy(part) for part in parts[part_index + 1:])
    new_route = copy.deepcopy(route)
    new_route['parts'] = new_parts
    record = dict(s_start_mm=float(s0), s_end_mm=float(s1),
                  from_z=z_from, to_z=float(z_to),
                  from_plane=int(G5.plane_of_z(z_from)),
                  to_plane=int(G5.plane_of_z(float(z_to))),
                  footprint_mm=float(exc['footprint_mm']),
                  middle_mm=float(exc['middle_mm']),
                  body_part_index=int(part_index))
    new_route = _finalise(new_route)
    new_route['excursions'] = list(new_route.get('excursions') or []) + [record]
    new_route['native_3d'] = True
    return new_route


def line_span(route, part_index, point, tol=1e-5):
    """The straight run of ``part_index`` that contains ``point`` (or None)."""
    prims = route['parts'][part_index]['primitives']
    cursor = 0.0
    for prim in prims:
        length = _prim_length(prim)
        if prim['kind'] == 'line':
            p0 = prim['p0']
            p1 = prim['p1']
            direction = ((p1[0] - p0[0]) / length, (p1[1] - p0[1]) / length)
            along = ((point[0] - p0[0]) * direction[0]
                     + (point[1] - p0[1]) * direction[1])
            perp = abs(-(point[0] - p0[0]) * direction[1]
                       + (point[1] - p0[1]) * direction[0])
            if -tol <= along <= length + tol and perp <= 1e-4:
                return dict(s_start=cursor, s_end=cursor + length,
                            s=cursor + min(max(along, 0.0), length),
                            direction=direction, length=length,
                            local=min(max(along, 0.0), length))
        cursor += length
    return None
