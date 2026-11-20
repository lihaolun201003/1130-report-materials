# -*- coding: utf-8 -*-
"""G5 search state, incremental scoring and violation-driven repair moves."""
from __future__ import annotations

import json
import math
import random
import time
from collections import Counter, defaultdict

from four_side_1024.fanout1024.xyzrouter.g5 import model as G5
from four_side_1024.fanout1024.xyzrouter.g5 import candidates as C

THETA = G5.THETA_MIN_DEG


def violation_key(event):
    return (event['route_a'], event['route_b'], round(event['z'], 6),
            round(event['x'], 6), round(event['y'], 6))


class State:
    """A mutable G5 world with exact violation bookkeeping."""

    def __init__(self, routes, min_angle_deg=THETA, log=print):
        self.world = G5.World(routes, min_angle_deg=min_angle_deg)
        self.min_angle_deg = float(min_angle_deg)
        self.log = log
        self.hard_issues = []
        self.violations = []          # list of crossing dicts with angle < min
        self.crossings = []           # every genuine crossing
        self.per_route = Counter()    # rid -> number of violations
        self.per_route_deficit = defaultdict(float)
        self.per_route_crossings = Counter()
        self.length = 0.0
        self.moves = []
        self._reindex()
        self.length = sum(chain.length_mm for chain in self.world.chains.values())

    # ------------------------------------------------------------------ index
    def _reindex(self):
        result = self.world.audit_all(min_angle_deg=self.min_angle_deg)
        self.crossings = result['crossings']
        self.violations = result['violations']
        self.hard_issues = result['issues']
        self._counters()

    def _counters(self):
        self.per_route = Counter()
        self.per_route_deficit = defaultdict(float)
        self.per_route_crossings = Counter()
        for event in self.violations:
            self.per_route[event['route_a']] += 1
            self.per_route[event['route_b']] += 1
            deficit = max(0.0, self.min_angle_deg - event['angle_deg'])
            self.per_route_deficit[event['route_a']] += deficit
            self.per_route_deficit[event['route_b']] += deficit
        for event in self.crossings:
            self.per_route_crossings[event['route_a']] += 1
            self.per_route_crossings[event['route_b']] += 1

    def refresh(self):
        self._reindex()

    # ------------------------------------------------------------------ stats
    @property
    def n_violations(self):
        return len(self.violations)

    def deficit(self):
        return sum(max(0.0, self.min_angle_deg - event['angle_deg'])
                   for event in self.violations)

    def max_deficit(self):
        if not self.violations:
            return 0.0
        return max(self.min_angle_deg - event['angle_deg']
                   for event in self.violations)

    def summary(self):
        angles = [event['angle_deg'] for event in self.crossings]
        return dict(
            violations=len(self.violations),
            deficit=round(self.deficit(), 6),
            max_deficit=round(self.max_deficit(), 6),
            crossings=len(self.crossings),
            pairs=len({(event['route_a'], event['route_b'])
                       for event in self.crossings}),
            min_angle=(round(min(angles), 6) if angles else None),
            routes_with_violations=len(self.per_route),
            length_mm=round(self.length, 6),
            hard_issues=len(self.hard_issues))

    # -------------------------------------------------------------- evaluation
    def evaluate(self, rid, new_route, three_d='auto', window_check=False):
        """Return ``dict(ok, issues, crossings, violations, hard)`` for a move."""
        structure = G5.structure_issues(new_route)
        if structure:
            return dict(ok=False, structure=structure, issues=[], crossings=[],
                        violations=[], hard=structure, score=None)
        if three_d == 'auto':
            old_heights = set(self.world.chains[int(rid)].z_order)
            new_heights = set(G5.RouteChain(new_route).z_order)
            old_trans = len(self.world.chains[int(rid)].transitions)
            new_trans = len(G5.RouteChain(new_route).transitions)
            three_d = ('all' if (old_heights != new_heights
                                 or old_trans != new_trans) else 'own_flats')
        result = self.world.route_issues(int(rid), route=new_route,
                                         min_angle_deg=self.min_angle_deg,
                                         include_3d=(three_d != 'none'),
                                         window_check=window_check)
        violations = [event for event in result['crossings']
                      if event['angle_deg'] < self.min_angle_deg]
        if three_d == 'own_flats':
            result['issues'] = [issue for issue in result['issues']
                                if issue['kind'] != '3d_transition_flat'
                                and issue['kind'] != '3d_transition_transition']
        return dict(ok=not result['issues'], structure=[], issues=result['issues'],
                    crossings=result['crossings'], violations=violations,
                    hard=result['issues'])

    def pair_violations(self, rid_a, rid_b):
        return [event for event in self.violations
                if {event['route_a'], event['route_b']} == {rid_a, rid_b}]

    def route_violations(self, rid):
        return [event for event in self.violations
                if rid in (event['route_a'], event['route_b'])]

    # ------------------------------------------------------- batch helpers
    def violations_touching(self, ids):
        ids = set(int(rid) for rid in ids)
        return [event for event in self.violations
                if int(event['route_a']) in ids or int(event['route_b']) in ids]

    def crossings_touching(self, ids):
        ids = set(int(rid) for rid in ids)
        return [event for event in self.crossings
                if int(event['route_a']) in ids or int(event['route_b']) in ids]

    def pair_deficit(self, ids):
        return float(sum(max(0.0, self.min_angle_deg - event['angle_deg'])
                         for event in self.violations_touching(ids)))

    def count_route_pair_violations(self, ids):
        return len(self.violations_touching(ids))

    # ------------------------------------------------------------------ commit
    def apply(self, rid, new_route):
        rid = int(rid)
        old_chain = self.world.chains[rid]
        old_length = old_chain.length_mm
        moved = [event for event in self.violations
                 if rid in (event['route_a'], event['route_b'])]
        self.world.set_route(rid, new_route)
        new_chain = self.world.chains[rid]
        # exact re-evaluation of every pair the route takes part in
        result = self.world.route_issues(rid, min_angle_deg=self.min_angle_deg,
                                        window_check=True, include_3d=True)
        # ---- crossings bookkeeping
        kept = [event for event in self.crossings
                if rid not in (event['route_a'], event['route_b'])]
        self.crossings = kept + result['crossings']
        # ---- violations bookkeeping
        kept_v = [event for event in self.violations
                  if rid not in (event['route_a'], event['route_b'])]
        new_v = [event for event in result['crossings']
                 if event['angle_deg'] < self.min_angle_deg]
        self.violations = kept_v + new_v
        self._counters()
        self.hard_issues = [issue for issue in self.hard_issues
                            if rid not in (issue.get('route_a'),
                                           issue.get('route_b'),
                                           issue.get('rid'),
                                           issue.get('other'))]
        for issue in result['issues']:
            lowered = dict(issue)
            lowered.setdefault('route_a', rid)
            self.hard_issues.append(lowered)
        self.length += new_chain.length_mm - old_length
        return dict(removed=moved, added=new_v, issues=result['issues'],
                    crossings=result['crossings'])


# ===========================================================================
# candidate generation for one violation
# ===========================================================================
CORRIDOR_DELTAS = (-30.0, -24.0, -19.0, -15.0, -12.0, -9.0, -7.0, -5.0, -4.0,
                   -3.0, -2.0, 2.0, 3.0, 4.0, 5.0, 7.0, 9.0, 12.0, 15.0, 19.0,
                   24.0, 30.0)


def excursion_candidates(route, part_index, point, planes, min_margin=1.30,
                         middle_min=1.0):
    """Over/under-pass candidates for a crossing at ``point`` on a straight run."""
    span = C.line_span(route, part_index, point)
    if span is None:
        return
    z_from = float(route['parts'][part_index]['z_mm'])
    planes = sorted(planes, key=lambda z: (abs(z - z_from), z))
    for z_to in planes:
        if abs(z_to - z_from) < 1e-9:
            continue
        if G5.plane_of_z(z_to) in (1001, 1002):
            continue                  # interface heights are lead-only
        footprint = C.T.transition_footprint(z_from - z_to)
        need = 2.0 * footprint + middle_min
        half = max(need / 2.0, min_margin + footprint)
        for extra in (0.0, 1.5, 3.0, 6.0):
            s0 = span['s'] - half - extra
            s1 = span['s'] + half + extra
            if s0 < span['s_start'] + 0.05 or s1 > span['s_end'] - 0.05:
                continue
            new_route = C.excursion_on_line(route, part_index, s0, s1, z_to)
            if new_route is None:
                continue
            yield ('excursion:p%d:z%.3f:%+.2f' % (part_index, z_to, extra),
                   new_route)


def multi_excursion_candidates(route, part_index, spans, planes,
                               margin=1.35, middle_min=1.0, max_middle=120.0):
    """One excursion window that covers several crossings on the same run."""
    if not spans:
        return
    z_from = float(route['parts'][part_index]['z_mm'])
    s_lo = min(span['s'] for span in spans)
    s_hi = max(span['s'] for span in spans)
    run_start = min(span['s_start'] for span in spans)
    run_end = max(span['s_end'] for span in spans)
    for z_to in sorted(planes, key=lambda z: (abs(z - z_from), z)):
        if abs(z_to - z_from) < 1e-9:
            continue
        if G5.plane_of_z(z_to) in (1001, 1002):
            continue                  # interface heights are lead-only
        footprint = C.T.transition_footprint(z_from - z_to)
        need = 2.0 * footprint + middle_min
        for extra in (0.0, 2.0, 5.0, 9.0, 15.0, 24.0, 36.0, 55.0, 85.0,
                      130.0):
            s0 = s_lo - margin - footprint - extra
            s1 = s_hi + margin + footprint + extra
            if s1 - s0 < need:
                s0 = s_lo - need / 2.0
                s1 = s_hi + need / 2.0
            if s0 < run_start + 0.05 or s1 > run_end - 0.05:
                continue
            if (s1 - s0) - 2.0 * footprint > max_middle:
                continue
            new_route = C.excursion_on_line(route, part_index, s0, s1, z_to)
            if new_route is None:
                continue
            yield ('excursion_multi:p%d:z%.3f:%+.1f'
                   % (part_index, z_to, extra), new_route)


def candidates_for_route(state, rid, hint=None, planes=None, heavy=True):
    """Every candidate move we are willing to try on one route."""
    route = state.world.routes[int(rid)]
    if heavy:
        for label, new_route in C.corridor_variants(route, CORRIDOR_DELTAS):
            yield ('corridor:' + label, new_route)
        if planes:
            for label, new_route in C.reheight_variants(route, planes):
                yield label, new_route
    if hint is not None:
        part_index, point = hint
        plane_list = planes or G5.all_heights()
        for label, new_route in excursion_candidates(route, part_index, point,
                                                     plane_list):
            yield label, new_route


def candidate_pool(state, rid, limit=120, seed=0, planes=None, heavy=True,
                   hint=None, corridor_share=0.34):
    """Ordered pool: re-height (most effective) -> excursion -> corridor shifts."""
    route = state.world.routes[int(rid)]
    pool = []
    if planes:
        pool.extend(C.reheight_variants(route, planes))
    allow_excursion = not (route.get('excursions') or [])
    if hint is not None and allow_excursion:
        pool.extend(excursion_candidates(route, hint[0], hint[1],
                                         planes or G5.all_heights()))
    if hint is not None and allow_excursion and len(hint) > 2 and hint[2]:
        pool.extend(multi_excursion_candidates(route, hint[0], hint[2],
                                               planes or G5.all_heights()))
    if heavy:
        corridor = list(C.corridor_variants(route, CORRIDOR_DELTAS))
        rng = random.Random(seed)
        rng.shuffle(corridor)
        budget = max(0, int(limit * corridor_share))
        pool.extend(corridor[:budget])
    return pool[:limit]


def route_hint(state, rid, target_event=None):
    """Excursion hint for one route: (body part, target point, spans).

    ``spans`` are the arc-length windows of *every* sub-45 deg crossing of that
    route that lies on a straight run of the same body part, so a single
    over/under-pass can cover several crossings at once.
    """
    route = state.world.routes[int(rid)]
    events = state.route_violations(int(rid))
    if target_event is not None:
        events = [target_event] + [e for e in events if e is not target_event]
    per_part = defaultdict(list)
    for event in events:
        point = (event['x'], event['y'])
        part = C.part_at_point(route, point)
        if part is None:
            continue
        span = C.line_span(route, part, point)
        if span is None:
            continue
        per_part[part].append(span)
    if not per_part:
        return None
    target_part = None
    if target_event is not None:
        target_part = C.part_at_point(route,
                                     (target_event['x'], target_event['y']))
    if target_part is not None and target_part in per_part:
        part = target_part
    else:
        part = max(per_part, key=lambda key: len(per_part[key]))
    spans = per_part[part]
    point = (spans[0]['s'],)
    target = None
    if target_event is not None:
        target = (target_event['x'], target_event['y'])
    else:
        target = None
    return (part, target or _span_point(route, part, spans[0]['s']),
            spans if len(spans) > 1 else None)


def _span_point(route, part_index, s):
    prims = route['parts'][part_index]['primitives']
    cursor = 0.0
    for prim in prims:
        length = C._prim_length(prim)
        if s <= cursor + length + 1e-9:
            if prim['kind'] == 'line':
                p0, p1 = prim['p0'], prim['p1']
                t = 0.0 if length <= 0 else (s - cursor) / length
                return (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)
            angle = prim['start_angle'] + prim['sweep'] * (
                0.0 if length <= 0 else (s - cursor) / length)
            return (prim['center'][0] + prim['radius'] * math.cos(angle),
                    prim['center'][1] + prim['radius'] * math.sin(angle))
        cursor += length
    return None


# ===========================================================================
# scoring / acceptance
# ===========================================================================
def score(state):
    """Lexicographic objective as one comparable tuple."""
    return (len(state.violations), round(state.max_deficit(), 9),
            round(state.deficit(), 6), len(state.crossings),
            round(state.length, 6))


def delta_score(before, after):
    for index, (a, b) in enumerate(zip(before, after)):
        if a != b:
            return (b - a) if index < 3 else (b - a)
    return 0.0


def improvement(before, after):
    """Positive when ``after`` is lexicographically better than ``before``."""
    for a, b in zip(before, after):
        if a != b:
            return a - b
    return 0.0
