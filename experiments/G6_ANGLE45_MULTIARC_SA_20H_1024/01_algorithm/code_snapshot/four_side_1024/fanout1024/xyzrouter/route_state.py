# -*- coding: utf-8 -*-
"""Heading-aware 3D routing search state of the XYZ joint router.

The router works on explicit geometric primitives; the search state is

``(x, y, z, heading, used_transitions, cost, length, primitives)``

which is what ``xyz_search`` expands / ranks.  The production local reroute
(`local_reroute.py`) enumerates the same state space at the level of
``(target height, lead lengths, XY corridor family)`` and always keeps exact
geometry, so a candidate can be measured with the true 3D world.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

R15 = 15.0
HEADINGS = ((1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0))


def heading_index(heading):
    hx, hy = float(heading[0]), float(heading[1])
    norm = math.hypot(hx, hy)
    if norm <= 0:
        raise ValueError('zero heading')
    hx, hy = hx / norm, hy / norm
    for index, candidate in enumerate(HEADINGS):
        if abs(candidate[0] - hx) < 1e-6 and abs(candidate[1] - hy) < 1e-6:
            return index
    raise ValueError('heading is not axis aligned')


@dataclass
class SearchState:
    x: float
    y: float
    z: float
    heading: tuple
    used_transitions: int = 0
    cost: float = 0.0
    length_mm: float = 0.0
    primitives: list = field(default_factory=list)

    def key(self, z_ticks=1e4):
        return (round(self.x, 3), round(self.y, 3),
                round(self.z * z_ticks), heading_index(self.heading),
                int(self.used_transitions))

    def advance(self, primitives, length_mm, cost, end, heading,
                transitions_used=0):
        return SearchState(x=float(end[0]), y=float(end[1]), z=float(self.z),
                           heading=(float(heading[0]), float(heading[1])),
                           used_transitions=self.used_transitions + int(transitions_used),
                           cost=float(self.cost) + float(cost),
                           length_mm=float(self.length_mm) + float(length_mm),
                           primitives=list(self.primitives) + list(primitives))

    def pose(self):
        return dict(position=(self.x, self.y, self.z),
                    heading=tuple(self.heading))


@dataclass
class GoalPose:
    x: float
    y: float
    z: float
    heading: tuple

    def pose_gap(self, state):
        return dict(position=math.dist((state.x, state.y),
                                       (self.x, self.y)),
                    z=abs(state.z - self.z),
                    heading=math.dist(state.heading, self.heading))


def route_state(stage, route_part_index, route):
    """Search state of one concrete point of an existing route (for probing)."""
    part = route['parts'][route_part_index]
    if part['kind'] == 'flat':
        prim = part['primitives'][0]
        start = prim['p0']
        tangent = (prim['p1'][0] - start[0], prim['p1'][1] - start[1])
        norm = math.hypot(*tangent) or 1.0
        return SearchState(x=float(start[0]), y=float(start[1]),
                           z=float(part['z_mm']),
                           heading=(tangent[0] / norm, tangent[1] / norm))
    return SearchState(x=float(part['start'][0]), y=float(part['start'][1]),
                       z=float(part['z0']), heading=tuple(part['direction']))
