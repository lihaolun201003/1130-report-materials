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
        parts[index]['tag'] = 'lead' if index in lead else 'body'
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
    # a rebuilt body has no mid transitions: clear the stale native flags
    route['native_3d'] = bool(mid)
    if not mid:
        route.pop('excursions', None)
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
    """Move the body of ``route`` to physical height ``z_new`` (exact).

    The body is translated so that its start follows the rebuilt up-S-curve and
    then two *arbitrary* perpendicular body runs absorb the 2-D end-pose change
    (a 2x2 closure solve).  Requiring the first/last run instead -- as the first
    G5 version did -- excluded every route whose two end directions are
    parallel, which is a large fraction of the layout.
    """
    z_new = float(z_new)
    if G5.plane_of_z(z_new) is None:
        return None
    index = single_body(route)
    if index is None:
        return None
    if int(route.get('n_transitions') or 0) == 0:
        return None                     # a DIRECT route must stay on its interface
    parts = copy.deepcopy(route['parts'])
    if len(parts) != 5:
        return None
    lead_in, up, body, down, lead_out = parts
    if (lead_in['kind'] != 'flat' or up['kind'] != 'transition'
            or body['kind'] != 'flat' or down['kind'] != 'transition'
            or lead_out['kind'] != 'flat'):
        return None
    z_old = float(body['z_mm'])
    if abs(z_old - z_new) < 1e-12:
        return None
    start_dir = (float(up['direction'][0]), float(up['direction'][1]))
    end_dir = (float(down['direction'][0]), float(down['direction'][1]))
    z_in = float(lead_in['z_mm'])
    z_out = float(lead_out['z_mm'])
    if abs(z_new - z_in) < 1e-9 or abs(z_new - z_out) < 1e-9:
        return None                     # zero-height transition
    fp_old = float(up['footprint_mm'])
    fp_new = T.transition_footprint(z_in - z_new)
    fp_out_old = float(down['footprint_mm'])
    fp_out_new = T.transition_footprint(z_out - z_new)
    prims = [dict(prim) for prim in body['primitives']]
    entries = _line_entries(prims)
    if not entries:
        return None
    # end of the old body and the end the rebuilt down-S-curve needs
    end_old = None
    for prim in reversed(prims):
        if prim['kind'] in ('line', 'arc'):
            end_old = (float(prim['p1'][0]), float(prim['p1'][1]))
            break
    if end_old is None:
        return None
    lead_out_start = (float(lead_out['primitives'][0]['p0'][0]),
                      float(lead_out['primitives'][0]['p0'][1]))
    target_end = (lead_out_start[0] - end_dir[0] * fp_out_new,
                  lead_out_start[1] - end_dir[1] * fp_out_new)
    shift = (fp_new - fp_old) * start_dir[0], (fp_new - fp_old) * start_dir[1]
    end_after = (end_old[0] + shift[0], end_old[1] + shift[1])
    rhs = (target_end[0] - end_after[0], target_end[1] - end_after[1])
    # --- parallel end directions: the closure needs one run along that axis ---
    dot = start_dir[0] * end_dir[0] + start_dir[1] * end_dir[1]
    if abs(abs(dot) - 1.0) < 1e-6:
        axis = _axis_of(start_dir)
        prims = _translate(prims, fp_new - fp_old, start_dir)
        end_after = (end_old[0] + (fp_new - fp_old) * start_dir[0],
                     end_old[1] + (fp_new - fp_old) * start_dir[1])
        need = (target_end[0] - end_after[0], target_end[1] - end_after[1])
        if math.hypot(*need) <= 1e-9:
            pass
        else:
            gamma = (need[0] * start_dir[0] + need[1] * start_dir[1])
            residual = (need[0] - gamma * start_dir[0],
                        need[1] - gamma * start_dir[1])
            if math.hypot(*residual) > 1e-9:
                return None
            target_entry = None
            for entry in entries:
                if _axis_of(entry['direction']) != axis:
                    continue
                if entry['length'] + gamma > 0.1:
                    target_entry = entry
                    break
            if target_entry is None:
                return None
            prims = _shift_downstream(prims, target_entry['index'], gamma,
                                      target_entry['direction'])
        body['primitives'] = prims
        body['z_mm'] = z_new
        body['layer_id'] = int(G5.plane_of_z(z_new))
        up_new = T.make_s_curve(tuple(up['start']), start_dir, z_in, z_new,
                                tag='fanout')
        body_end = None
        for prim in reversed(prims):
            if prim['kind'] in ('line', 'arc'):
                body_end = (float(prim['p1'][0]), float(prim['p1'][1]))
                break
        down_new = T.make_s_curve(body_end, end_dir, z_new, z_out,
                                  tag='fanout')
        parts[1] = up_new
        parts[3] = down_new
        new_route = copy.deepcopy(route)
        new_route['parts'] = parts
        return _finalise(new_route)
    # pick any two perpendicular body runs
    pair = None
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            a, b = entries[i], entries[j]
            if abs(a['direction'][0] * b['direction'][0]
                   + a['direction'][1] * b['direction'][1]) > 1e-6:
                continue
            pair = (a, b)
            break
        if pair:
            break
    if pair is None:
        return None
    a, b = pair
    alpha = rhs[0] * a['direction'][0] + rhs[1] * a['direction'][1]
    beta = rhs[0] * b['direction'][0] + rhs[1] * b['direction'][1]
    residual = (rhs[0] - alpha * a['direction'][0] - beta * b['direction'][0],
                rhs[1] - alpha * a['direction'][1] - beta * b['direction'][1])
    if math.hypot(*residual) > 1e-9:
        return None
    if a['length'] + alpha <= 0.1 or b['length'] + beta <= 0.1:
        return None
    prims = _translate(prims, fp_new - fp_old, start_dir)
    for entry, delta in sorted(((a, alpha), (b, beta)),
                               key=lambda item: item[0]['index']):
        if abs(delta) < 1e-12:
            continue
        prims = _shift_downstream(prims, entry['index'], delta,
                                  entry['direction'])
    body['primitives'] = prims
    body['z_mm'] = z_new
    body['layer_id'] = int(G5.plane_of_z(z_new))
    up_new = T.make_s_curve(tuple(up['start']), start_dir, z_in, z_new,
                            tag='fanout')
    body_end = None
    for prim in reversed(prims):
        if prim['kind'] in ('line', 'arc'):
            body_end = (float(prim['p1'][0]), float(prim['p1'][1]))
            break
    down_new = T.make_s_curve(body_end, end_dir, z_new, z_out, tag='fanout')
    parts[1] = up_new
    parts[3] = down_new
    new_route = copy.deepcopy(route)
    new_route['parts'] = parts
    return _finalise(new_route)


def _axis_of(direction):
    return 0 if abs(direction[0]) > 0.5 else 1


def _round_polyline(points):
    """Exact R15 rounding of every interior vertex of an axis-aligned polyline."""
    if len(points) < 2:
        return None
    segments = []
    for i in range(len(points) - 1):
        p0, p1 = points[i], points[i + 1]
        length = math.dist(p0, p1)
        if length <= 1e-9:
            return None
        segments.append(dict(dir=((p1[0] - p0[0]) / length,
                                  (p1[1] - p0[1]) / length),
                             length=length, p0=p0, p1=p1))
    corners = len(segments) - 1
    for i, seg in enumerate(segments):
        need = 0.0
        if i > 0:
            need += R15
        if i < len(segments) - 1:
            need += R15
        if seg['length'] < need + 1e-6:
            return None
    prims = []
    cursor = points[0]
    for i, seg in enumerate(segments):
        if i < len(segments) - 1:
            nxt = segments[i + 1]['dir']
            corner = seg['p1']
            arc_start = (corner[0] - R15 * seg['dir'][0],
                         corner[1] - R15 * seg['dir'][1])
            arc_end = (corner[0] + R15 * nxt[0], corner[1] + R15 * nxt[1])
            if math.dist(cursor, arc_start) > 1e-9:
                prims.append(dict(kind='line', p0=list(cursor),
                                  p1=list(arc_start)))
            centre = (arc_start[0] + R15 * nxt[0], arc_start[1] + R15 * nxt[1])
            a0 = math.atan2(arc_start[1] - centre[1], arc_start[0] - centre[0])
            a1 = math.atan2(arc_end[1] - centre[1], arc_end[0] - centre[0])
            sweep = a1 - a0
            while sweep > math.pi:
                sweep -= 2.0 * math.pi
            while sweep < -math.pi:
                sweep += 2.0 * math.pi
            prims.append(dict(kind='arc', center=[centre[0], centre[1]],
                              radius=R15, start_angle=a0, sweep=sweep,
                              p0=list(arc_start), p1=list(arc_end)))
            cursor = arc_end
        else:
            if math.dist(cursor, seg['p1']) > 1e-9:
                prims.append(dict(kind='line', p0=list(cursor),
                                  p1=list(seg['p1'])))
    return prims


def _short_s_pair(start, travel, shift):
    """Exact R15 two-arc short-S (the project's own ``fslw.geom.short_s``)."""
    from four_side_1024.fslw import geom as FG
    from four_side_1024.fslw import config as FC
    _, _, _ = None, None, None
    prims, end, end_dir = FG.short_s(tuple(start), tuple(travel), float(shift),
                                     radius=R15)
    if prims is None:
        return None
    return [dict(kind='line', p0=list(prim['p0']), p1=list(prim['p1']))
            if prim['kind'] == 'line' else
            dict(kind='arc', center=list(prim['center']),
                 radius=float(prim['radius']),
                 start_angle=float(prim['start_angle']),
                 sweep=float(prim['sweep']),
                 p0=list(prim['p0']), p1=list(prim['p1']))
            for prim in prims], tuple(end), tuple(end_dir)


def _body_between(S, u, E, v, fraction=0.5, m=3):
    """Exact body from pose (S, u) to pose (E, v); no closure solve needed."""
    ua, va = _axis_of(u), _axis_of(v)
    if ua != va:
        if m == 1:
            corner = [0.0, 0.0]
            corner[ua] = S[ua]
            corner[va] = E[va]
            points = [tuple(S), tuple(corner), tuple(E)]
        else:
            # m = 3: two intermediate levels give two free parameters
            span_u = (E[ua] - S[ua])
            span_v = (E[va] - S[va])
            level = S[ua] + fraction * span_u
            xcross = S[va] + fraction * span_v
            points = [tuple(S), (S[0], S[1]), tuple(E)]
            p1 = [0.0, 0.0]
            p1[ua] = level
            p1[va] = S[va]
            p2 = [0.0, 0.0]
            p2[ua] = level
            p2[va] = xcross
            p3 = [0.0, 0.0]
            p3[ua] = E[ua]
            p3[va] = xcross
            points = [tuple(S), tuple(p1), tuple(p2), tuple(p3), tuple(E)]
    else:
        # parallel end directions: a straight run, or a U-jog in the other axis
        perp = 1 - ua
        lateral = E[perp] - S[perp]
        total = (E[ua] - S[ua]) * (1.0 if u[ua] > 0 else -1.0)
        if abs(lateral) <= 1e-6:
            points = [tuple(S), tuple(E)]
        elif abs(lateral) < 30.0:
            # small lateral shift: a two-arc short-S pair, then a straight run.
            # ``short_s`` measures the shift along rot90(travel), so convert.
            perp_dir = (-u[1], u[0])
            shift_signed = (E[0] - S[0] - u[0] * ((E[0] - S[0]) * u[0]
                                                 + (E[1] - S[1]) * u[1])
                            ) * perp_dir[0] + (E[1] - S[1] - u[1] * (
                                (E[0] - S[0]) * u[0] + (E[1] - S[1]) * u[1])
                            ) * perp_dir[1]
            built = _short_s_pair(S, u, shift_signed)
            if built is None:
                return None
            prims, after, heading = built
            remaining = (E[0] - after[0], E[1] - after[1])
            if math.hypot(*remaining) > 1e-9:
                if abs(remaining[0] * u[1] - remaining[1] * u[0]) > 1e-6:
                    return None
                if remaining[0] * u[0] + remaining[1] * u[1] < 1e-9:
                    return None
                prims.append(dict(kind='line', p0=list(after), p1=list(E)))
            return prims
        elif total <= 60.0 + 1e-6:
            return None
        else:
            a = max(15.0 + 1e-6, min(total - 15.0 - 1e-6, fraction * total))
            p1 = [S[0], S[1]]
            p1[ua] = S[ua] + (1.0 if u[ua] > 0 else -1.0) * a
            p1[perp] = S[perp]
            p2 = list(p1)
            p2[perp] = E[perp]
            points = [tuple(S), tuple(p1), tuple(p2), tuple(E)]
            if abs(p2[ua] - E[ua]) < 1e-9:
                return None
    cleaned = [points[0]]
    for point in points[1:]:
        if math.dist(point, cleaned[-1]) > 1e-9:
            cleaned.append(point)
    return _round_polyline(cleaned)


def reheight_full(route, z_new, trials=6):
    """Re-height by rebuilding the body between the *new* transition poses.

    This is the universal fallback: the two R15 S-curves are fixed by the new
    height, and the body is then an exact staircase between their new endpoints,
    so the end-pose closure problem disappears.  Excursion parts are dropped.
    """
    z_new = float(z_new)
    if G5.plane_of_z(z_new) is None:
        return None
    parts = route.get('parts') or []
    fanout = [i for i, part in enumerate(parts)
              if part.get('kind') == 'transition'
              and (part.get('tag') or '') == 'fanout']
    if not fanout:
        fanout = [i for i, part in enumerate(parts)
                  if part.get('kind') == 'transition']
    if len(fanout) < 2:
        return None
    up_index, down_index = fanout[0], fanout[-1]
    if up_index == 0 or down_index == len(parts) - 1:
        return None
    lead_in = parts[up_index - 1]
    lead_out = parts[down_index + 1]
    if lead_in.get('kind') != 'flat' or lead_out.get('kind') != 'flat':
        return None
    z_in = float(lead_in['z_mm'])
    z_out = float(lead_out['z_mm'])
    if abs(z_new - z_in) < 1e-9 or abs(z_new - z_out) < 1e-9:
        return None
    up = parts[up_index]
    down = parts[down_index]
    u = (float(up['direction'][0]), float(up['direction'][1]))
    v = (float(down['direction'][0]), float(down['direction'][1]))
    fp_new = T.transition_footprint(z_in - z_new)
    fp_out_new = T.transition_footprint(z_out - z_new)
    up_new = T.make_s_curve(tuple(up['start']), u, z_in, z_new, tag='fanout')
    S = (float(up_new['end'][0]), float(up_new['end'][1]))
    lead_out_start = (float(lead_out['primitives'][0]['p0'][0]),
                      float(lead_out['primitives'][0]['p0'][1]))
    E = (lead_out_start[0] - v[0] * fp_out_new,
         lead_out_start[1] - v[1] * fp_out_new)
    down_new = T.make_s_curve(E, v, z_new, z_out, tag='fanout')
    if math.dist(tuple(down_new['end']), lead_out_start) > 1e-6:
        return None
    for fraction in (0.5, 0.33, 0.66, 0.2, 0.8, 0.42):
        for m in (3, 1):
            body = _body_between(S, u, E, v, fraction=fraction, m=m)
            if body is None:
                continue
            trial = copy.deepcopy(route)
            new_parts = [copy.deepcopy(lead_in), up_new,
                         dict(kind='flat', layer_id=int(G5.plane_of_z(z_new)),
                              z_mm=float(z_new), tag='body',
                              primitives=body),
                         down_new, copy.deepcopy(lead_out)]
            trial['parts'] = new_parts
            trial.pop('excursions', None)
            out = _finalise(trial)
            if not G5.structure_issues(out):
                return out
            if trials <= 0:
                return None
    return None


def staircase_body(route, levels, xs, end_dir=None):
    """Rebuild the body as an exact R15 staircase with free jog positions.

    For a body whose first run is along ``u`` and last run along ``v`` with
    ``u`` perpendicular to ``v``, the path is

        S -> (u to Y0) -> (v to X1) -> (u to Y1) -> ... -> (u to Ey) -> E

    with ``len(levels) = m`` and ``len(xs) = m``; the free parameters are the
    ``m`` u-levels and the ``m`` v-positions, i.e. ``2m`` degrees of freedom, and
    every corner is a quarter R15 arc.  ``levels``/``xs`` are in path order and
    monotone towards E.  Returns the new body primitives or ``None``.
    """
    body_index = single_body(route)
    if body_index is None:
        return None
    parts = route['parts']
    up, down = parts[1], parts[3]
    if up['kind'] != 'transition' or down['kind'] != 'transition':
        return None
    u = (float(up['direction'][0]), float(up['direction'][1]))
    v = (float(down['direction'][0]), float(down['direction'][1]))
    if abs(u[0] * v[0] + u[1] * v[1]) > 1e-6:
        return None                     # not a perpendicular staircase
    S = (float(up['end'][0]), float(up['end'][1]))
    E = (float(down['start'][0]), float(down['start'][1]))
    m = len(levels)
    if m == 0 or len(xs) != m:
        return None
    # build the waypoint list in (u, v) coordinates
    ua, va = _axis_of(u), _axis_of(v)
    corner_u = []
    corner_v = []
    # first run along u to levels[0]; then alternate v / u ... ending with v to E
    points = [S]
    cursor = list(S)
    order = []
    for index in range(m):
        order.append(('u', levels[index]))
        order.append(('v', xs[index]))
    order.append(('u', E[ua]))
    order.append(('v', E[va]))
    for kind, value in order:
        if kind == 'u':
            cursor[ua] = value
        else:
            cursor[va] = value
        points.append(tuple(cursor))
    # drop duplicate points (zero-length runs are not allowed)
    cleaned = [points[0]]
    for point in points[1:]:
        if math.dist(point, cleaned[-1]) > 1e-9:
            cleaned.append(point)
    # verify the end really is E
    if math.dist(cleaned[-1], E) > 1e-6:
        return None
    prims = []
    cursor = cleaned[0]
    heading = u
    for target in cleaned[1:]:
        delta = (target[0] - cursor[0], target[1] - cursor[1])
        length = math.hypot(*delta)
        if length < 30.0 - 1e-9 and (prims and target is not cleaned[-1]):
            return None                 # two R15 arcs do not fit in this run
        run_dir = (delta[0] / length, delta[1] / length)
        if prims:
            # quarter arc from the previous heading to run_dir
            centre = (cursor[0] + heading[0] * R15 - run_dir[0] * 0.0,
                      cursor[1] + heading[1] * R15)
            # centre = cursor + R15 * (heading rotated towards run_dir)
            # for a quarter turn: centre is at cursor + R15*heading + R15*(run_dir - heading)
            centre = (cursor[0] + R15 * (heading[0] + run_dir[0]),
                      cursor[1] + R15 * (heading[1] + run_dir[1]))
            p0 = (cursor[0], cursor[1])
            p1 = (cursor[0] + R15 * run_dir[0], cursor[1] + R15 * run_dir[1])
            start_angle = math.atan2(p0[1] - centre[1], p0[0] - centre[0])
            end_angle = math.atan2(p1[1] - centre[1], p1[0] - centre[0])
            sweep = end_angle - start_angle
            while sweep > math.pi:
                sweep -= 2.0 * math.pi
            while sweep < -math.pi:
                sweep += 2.0 * math.pi
            prims.append(dict(kind='arc', center=[centre[0], centre[1]],
                              radius=R15, start_angle=start_angle,
                              sweep=sweep, p0=[p0[0], p0[1]], p1=[p1[0], p1[1]]))
            cursor = p1
            delta = (target[0] - cursor[0], target[1] - cursor[1])
            length = math.hypot(*delta)
        if length > 1e-9:
            prims.append(dict(kind='line', p0=[cursor[0], cursor[1]],
                              p1=[target[0], target[1]]))
            cursor = target
        heading = run_dir
    # final heading must match the down transition
    if abs(heading[0] - v[0]) > 1e-6 or abs(heading[1] - v[1]) > 1e-6:
        return None
    return prims


def reheight_any(route, z_new, rebuild=True):
    """Exact re-height, falling back to a body rebuild when the closure fails."""
    new_route = reheight(route, z_new)
    if new_route is not None or not rebuild:
        return new_route
    if int(route.get('n_transitions') or 0) == 0:
        return None
    if single_body(route) is None:
        # multi-body (excursion) route: rebuild the body between the new poses
        return reheight_full(route, z_new)
    body_index = single_body(route)
    prims = route['parts'][body_index]['primitives']
    entries = _line_entries(prims)
    if len(entries) < 2:
        return None
    up, down = route['parts'][1], route['parts'][3]
    u = (float(up['direction'][0]), float(up['direction'][1]))
    v = (float(down['direction'][0]), float(down['direction'][1]))
    if abs(u[0] * v[0] + u[1] * v[1]) > 1e-6:
        return None
    S = (float(up['end'][0]), float(up['end'][1]))
    E = (float(down['start'][0]), float(down['start'][1]))
    ua, va = _axis_of(u), _axis_of(v)
    span_u = (E[ua] - S[ua]) * (1.0 if u[ua] > 0 else -1.0)
    span_v = (E[va] - S[va]) * (1.0 if v[va] > 0 else -1.0)
    if span_u <= 0 or span_v <= 0:
        return None
    # current jog positions as the starting guess
    levels = []
    xs = []
    for entry in entries:
        prim = prims[entry['index']]
        if _axis_of(entry['direction']) != ua:
            continue
        levels.append(round(float(prim['p0'][ua]), 6))
    for entry in entries:
        prim = prims[entry['index']]
        if _axis_of(entry['direction']) != va:
            continue
        xs.append(round(float(prim['p0'][va]), 6))
    candidates = []
    from_route_levels = [value for value in levels]
    from_route_xs = [value for value in xs]
    # a 2-level (4 dof) family derived from the current runs, clamped to range
    def clamp(value, lo, hi):
        return max(lo, min(hi, value))
    if from_route_levels and from_route_xs:
        candidates.append(([from_route_levels[0],
                            S[ua] + 0.5 * (E[ua] - S[ua])],
                           [from_route_xs[0],
                            S[va] + 0.5 * (E[va] - S[va])]))
    for frac in (0.33, 0.5, 0.66):
        levels_f = [S[ua] + frac * (E[ua] - S[ua]),
                    S[ua] + (frac + 0.25) * (E[ua] - S[ua])]
        xs_f = [S[va] + frac * (E[va] - S[va]),
                S[va] + (frac + 0.25) * (E[va] - S[va])]
        candidates.append((levels_f, xs_f))
    for level_values, x_values in candidates:
        levels_ok = sorted(level_values, reverse=(u[ua] < 0)) == list(level_values)
        xs_ok = sorted(x_values, reverse=(v[va] < 0)) == list(x_values)
        if not levels_ok or not xs_ok:
            continue
        prims_new = staircase_body(route, level_values, x_values)
        if prims_new is None:
            continue
        trial = copy.deepcopy(route)
        trial['parts'][body_index]['primitives'] = prims_new
        trial['parts'][body_index]['z_mm'] = float(z_new)
        trial['parts'][body_index]['layer_id'] = int(G5.plane_of_z(z_new))
        z_in = float(route['parts'][0]['z_mm'])
        z_out = float(route['parts'][4]['z_mm'])
        if abs(z_new - z_in) < 1e-9 or abs(z_new - z_out) < 1e-9:
            return None
        fp_new = T.transition_footprint(z_in - z_new)
        fp_out_new = T.transition_footprint(z_out - z_new)
        trial['parts'][1] = T.make_s_curve(tuple(up['start']), u, z_in,
                                           float(z_new), tag='fanout')
        body_end = (float(prims_new[-1]['p1'][0]), float(prims_new[-1]['p1'][1]))
        trial['parts'][3] = T.make_s_curve(body_end, v, float(z_new), z_out,
                                           tag='fanout')
        out = _finalise(trial)
        if not G5.structure_issues(out):
            return out
    return reheight_full(route, z_new)


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
    """Native-3D over/under-pass built by the project's own ``duck_out``.

    Using ``native3d.route_model.duck_out`` guarantees that the declared
    excursion metadata (part indices, from/to planes, footprint, middle length,
    tag placement) is exactly the form the frozen validator rebuilds and checks;
    the geometry itself is the exact R15 S-curve pair.
    """
    from four_side_1024.fanout1024.native3d import route_model as RM
    try:
        result = RM.duck_out(route, part_index, float(s0), float(s1),
                             float(z_to), radius=R15)
    except Exception:  # noqa: BLE001
        return None
    new_route = result['route']
    if not new_route.get('parts'):
        return None
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
