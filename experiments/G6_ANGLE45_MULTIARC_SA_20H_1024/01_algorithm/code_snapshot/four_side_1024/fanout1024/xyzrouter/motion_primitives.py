# -*- coding: utf-8 -*-
"""Exact R15 motion primitives of the XYZ joint router.

Every path produced here is built from **exactly** the frozen process primitives

* straight line ``('L', length)``
* R15 circular arc, quarter turn ``('Q', +1/-1)`` (any sub-arc allowed by split)
* two-arc R15 short-S lateral shift ``('S', shift)``

and is checked for position / tangent continuity and R15 curvature before it is
returned.  ``raise PrimitiveError`` instead of approximating a polyline.
"""
from __future__ import annotations

import math

from ...fsd25d import path3d as P3
from ...v2opt.candext import move_path as _move_path

R15 = 15.0


class PrimitiveError(RuntimeError):
    def __init__(self, reason, detail=None):
        super().__init__(str(reason))
        self.reason = str(reason)
        self.detail = dict(detail or {})


# ---------------------------------------------------------------------------
# primitive factories
# ---------------------------------------------------------------------------
def line(p0, p1):
    p0 = (float(p0[0]), float(p0[1]))
    p1 = (float(p1[0]), float(p1[1]))
    length = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    if length <= 1e-9:
        raise PrimitiveError('zero_length_line')
    return dict(kind='line', p0=list(p0), p1=list(p1))


def arc(start, target_heading, sign=1, radius=R15):
    """Exact R15 quarter arc starting at ``start`` with the caller's heading.

    ``target_heading`` must be the caller's heading rotated by ``sign * 90 deg``;
    the arc centre / start angle are derived exactly (no approximation).
    """
    raise NotImplementedError('use chain(); arcs are produced by the exact solver')


def s_transition(start, direction, z0, z1, radius=R15):
    return P3.make_transition(start, direction, z0, z1, radius=radius)


# ---------------------------------------------------------------------------
# exact chain builder
# ---------------------------------------------------------------------------
def chain(start, heading, moves, radius=R15):
    """Build the exact primitive chain of a move sequence.

    Returns ``dict(primitives, end, heading, length_mm)``.
    """
    if not moves:
        raise PrimitiveError('empty_move_sequence')
    prims, end, end_heading = _move_path(start, heading, moves, radius=radius)
    if prims is None:
        raise PrimitiveError('move_sequence_infeasible')
    validate_chain(prims, start, heading, end, end_heading, radius=radius)
    length = sum(_prim_length(prim) for prim in prims)
    return dict(primitives=prims, end=(float(end[0]), float(end[1])),
                heading=(float(end_heading[0]), float(end_heading[1])),
                length_mm=float(length))


def _prim_length(prim):
    if prim['kind'] == 'line':
        return math.hypot(prim['p1'][0] - prim['p0'][0],
                          prim['p1'][1] - prim['p0'][1])
    return abs(float(prim['radius']) * float(prim['sweep']))


def _tangent(prim, at_end=False):
    if prim['kind'] == 'line':
        dx = prim['p1'][0] - prim['p0'][0]
        dy = prim['p1'][1] - prim['p0'][1]
        norm = math.hypot(dx, dy)
        return (dx / norm, dy / norm)
    angle = float(prim['start_angle']) + (float(prim['sweep']) if at_end else 0.0)
    sign = 1.0 if float(prim['sweep']) >= 0 else -1.0
    return (-sign * math.sin(angle), sign * math.cos(angle))


def validate_chain(prims, start, heading, end, end_heading, radius=R15,
                   tol=1e-6):
    """Position / tangent continuity and R15 legality of one exact chain."""
    if not prims:
        raise PrimitiveError('empty_chain')
    first = prims[0]
    if math.hypot(first['p0'][0] - start[0], first['p0'][1] - start[1]) > tol:
        raise PrimitiveError('chain_start_mismatch')
    t0 = _tangent(first)
    if abs(t0[0] - heading[0]) > 1e-6 or abs(t0[1] - heading[1]) > 1e-6:
        raise PrimitiveError('chain_start_tangent_mismatch')
    for index, prim in enumerate(prims):
        if prim['kind'] not in ('line', 'arc'):
            raise PrimitiveError('unknown_primitive:%s' % prim['kind'])
        if prim['kind'] == 'arc':
            if abs(float(prim['radius']) - float(radius)) > 1e-6:
                raise PrimitiveError('arc_radius_not_r15')
        if index:
            left, right = prims[index - 1], prim
            tangent_left = _tangent(left, at_end=True)
            tangent_right = _tangent(right)
            if (abs(tangent_left[0] - tangent_right[0]) > 1e-6
                    or abs(tangent_left[1] - tangent_right[1]) > 1e-6):
                raise PrimitiveError('tangent_discontinuity:%d' % index)
            if (abs(left['p1'][0] - right['p0'][0]) > tol
                    or abs(left['p1'][1] - right['p0'][1]) > tol):
                raise PrimitiveError('position_discontinuity:%d' % index)
    last = prims[-1]
    if math.hypot(last['p1'][0] - end[0], last['p1'][1] - end[1]) > tol:
        raise PrimitiveError('chain_end_mismatch')
    t1 = _tangent(last, at_end=True)
    if abs(t1[0] - end_heading[0]) > 1e-6 or abs(t1[1] - end_heading[1]) > 1e-6:
        raise PrimitiveError('chain_end_tangent_mismatch')
    return True


def attach_height(primitives, z_mm):
    """A flat chain at one physical height (the route builder's flat part)."""
    prims = [dict(prim) for prim in primitives]
    length = sum(_prim_length(prim) for prim in prims)
    return dict(kind='flat', z_mm=float(z_mm), layer_id=None,
                length_mm=float(length), primitives=prims)


def path_length(primitives):
    return float(sum(_prim_length(prim) for prim in primitives))
