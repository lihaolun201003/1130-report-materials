# -*- coding: utf-8 -*-
"""G7 authoritative fixed-layer engine.

Crossings, angles and same-plane D56 legality are computed with the **same
``four_side_1024.fslw.validate_fslw`` strict-D56 code that the frozen project
validator uses** (``evaluate_pair(..., policy='strict')``): no reimplementation,
no semantic gap.  True-3-D clearance is checked against the G5 world transition
index; structure/R15/glass against the G5 structural contract.

The engine keeps an incremental, per-physical-height crossing bookkeeping:

* ``plane_events[z][(rid_a, rid_b)] = {angle, x, y}`` -- every genuine crossing
  on physical height ``z`` (at most one per route pair per plane, because a
  double crossing is already a hard D56 violation);
* ``route_crossings[rid]`` -- crossings the route participates in (selection
  weight for the N1 neighbour);
* ``total_crossings``, ``unique_pairs``, ``min_angle`` -- global objective and
  tie-break diagnostics.

Only the body flat of a *modifiable* route is ever replaced; transitions, lead
flats, interface geometry, native-3D parts and artificial-U parts are frozen and
verified by :mod:`...g7.frozen`.
"""
from __future__ import annotations

import math
import time
from collections import Counter, OrderedDict

from ..g5 import model as G5
from ....fslw import validate_fslw as F
from . import frozen as FR

CLEARANCE = 0.08
SAGITTA = 0.0005
THETA_MIN_DEG = 45.0
R15 = 15.0


def _pair_key(a, b):
    return (int(a), int(b)) if int(a) <= int(b) else (int(b), int(a))


def _event_key(pair, x, y):
    """One genuine crossing: a route pair may legally cross more than once."""
    return (pair, round(float(x), 6), round(float(y), 6))


def _angle_from_sine(sine):
    return math.degrees(math.asin(max(-1.0, min(1.0, abs(float(sine))))))


class PlaneWorld:
    """Authoritative crossing bookkeeping over all 20 physical heights."""

    def __init__(self, routes, freeze=None, log=None):
        self.log = log or (lambda *args, **kwargs: None)
        self.routes = {int(route['route_id']): route for route in routes}
        self.freeze = freeze
        # group every flat primitive by physical z (exactly like the frozen
        # validator's check_crossings)
        groups = {}
        for rid, route in self.routes.items():
            for part in route.get('parts') or ():
                if part.get('kind') != 'flat':
                    continue
                z = round(float(part['z_mm']), 9)
                prims = part.get('primitives') or []
                if prims:
                    groups.setdefault(z, {}).setdefault(rid, []).extend(
                        dict(prim) for prim in prims)
        self.groups = groups
        self.prepared = {z: {rid: F.prepare_route(prims, route_id=rid)
                             for rid, prims in routes_here.items()}
                         for z, routes_here in groups.items()}
        self.plane_events = {}
        self.plane_min_angle = {}
        self.plane_violations = {}
        self.total_crossings = 0
        self.pair_counts = Counter()
        self.route_crossings = Counter()
        self.route_plane = {}
        self.route_plane_prims = {}
        for z, routes_here in self.groups.items():
            audit = F.audit_route_pairs(list(self.prepared[z].values()),
                                        clearance=CLEARANCE,
                                        sagitta=SAGITTA, policy='strict')
            events = {}
            for crossing in audit.get('crossings') or ():
                pair = _pair_key(crossing['route_a'], crossing['route_b'])
                key = _event_key(pair, crossing['x'], crossing['y'])
                events[key] = dict(angle_deg=float(crossing['angle_deg']),
                                   x=float(crossing['x']),
                                   y=float(crossing['y']))
            self.plane_events[z] = events
            self.plane_min_angle[z] = min(
                (ev['angle_deg'] for ev in events.values()), default=None)
            self.plane_violations[z] = audit.get('violations') or []
            self.total_crossings += len(events)
        for z, routes_here in self.groups.items():
            for rid, prims in routes_here.items():
                self.route_plane_prims[rid] = prims
        # The plane a route *belongs to* is the one carrying its body flat.
        # A standard route also owns lead flats at the interface heights, so a
        # naive "last plane seen" assignment would silently point the search at
        # the exit interface plane instead of the body plane.
        for rid, route in self.routes.items():
            plane = None
            if freeze is not None:
                entry = freeze.get('entries', {}).get(str(rid))
                if entry and entry.get('body_index') is not None:
                    part = route['parts'][int(entry['body_index'])]
                    if part.get('kind') == 'flat':
                        plane = round(float(part['z_mm']), 9)
            if plane is None:
                flats = [part for part in route.get('parts') or ()
                         if part.get('kind') == 'flat']
                if flats:
                    plane = round(float(flats[len(flats) // 2]['z_mm']), 9)
            if plane is not None:
                self.route_plane[int(rid)] = plane
        self._rebuild_pair_counts()
        self._rebuild_route_crossings()
        self.total_crossings = sum(len(events) for events in
                                   self.plane_events.values())
        self.world = G5.World(list(self.routes.values()))
        self._audit_seconds = 0.0

    # ------------------------------------------------------------ statistics
    def min_angle(self):
        values = [value for value in self.plane_min_angle.values()
                  if value is not None]
        return min(values) if values else None

    def summary(self):
        angles = [event['angle_deg'] for events in self.plane_events.values()
                  for event in events.values()]
        return dict(crossings=int(self.total_crossings),
                    unique_pairs=int(self.unique_pairs),
                    min_angle=(round(min(angles), 9) if angles else None),
                    sub45=sum(1 for angle in angles if angle < THETA_MIN_DEG),
                    length_mm=round(_routes_length(self.routes), 6),
                    hard_issues=0 if not any(self.plane_violations.values())
                    else sum(len(v) for v in self.plane_violations.values()),
                    per_plane={z: len(events)
                               for z, events in self.plane_events.items()})

    def crossing_pairs(self):
        return [key for key, count in self.pair_counts.items() if count > 0]

    # --------------------------------------------------------- candidate eval
    def attached_plane(self, rid):
        return self.route_plane[rid]

    def evaluate_candidate(self, rid, new_prims):
        """Authoritative evaluation of a body-only candidate on the frozen plane.

        Returns ``dict(ok, crossings, violations, delta, min_angle)`` where
        ``crossings`` is ``[(other_rid, angle, x, y)]`` and ``delta`` is the
        exact change of the number of crossings involving ``rid`` on its plane.
        """
        z = self.route_plane[rid]
        prepared_new = F.prepare_route(new_prims, route_id=rid)
        crossings = []
        violations = []
        for other, other_prepared in self.prepared[z].items():
            if other == rid:
                continue
            result = F.evaluate_pair(other_prepared, prepared_new,
                                     CLEARANCE, SAGITTA, 'strict')
            if result is None:
                continue
            if not result.get('valid'):
                for detail in result.get('violations') or ():
                    violations.append(dict(detail, other=other))
                continue
            for crossing in result.get('crossings') or ():
                crossings.append((int(other),
                                  _angle_from_sine(crossing['sine']),
                                  float(crossing['point'][0]),
                                  float(crossing['point'][1])))
        old = self.plane_events[z]
        old_count = sum(1 for key in old if rid in key[0])
        if violations:
            return dict(ok=False, crossings=[], violations=violations,
                        delta=None, min_angle=None)
        angles = [item[1] for item in crossings]
        return dict(ok=True, crossings=crossings, violations=[],
                    delta=len(crossings) - old_count,
                    min_angle=(min(angles) if angles else None))

    def evaluate_batch(self, replacements):
        """Atomic authoritative evaluation of several body replacements.

        ``replacements`` is ``{route_id: new_body_prims}`` all on one physical
        height (the crossing-hotspot case).  Returns the exact global crossing
        delta of the whole batch and the new per-route crossing lists.
        """
        ids = sorted(int(rid) for rid in replacements)
        z = {self.route_plane[rid] for rid in ids}
        if len(z) != 1:
            return dict(ok=False, violations=[dict(kind='batch_multiple_planes')],
                        delta=None)
        z = z.pop()
        planes = self.prepared[z]
        new_prepared = {rid: F.prepare_route(replacements[rid], route_id=rid)
                        for rid in ids}
        changed = set(ids)
        old_events = self.plane_events[z]
        old_inside = sum(1 for key in old_events
                         if key[0][0] in changed or key[0][1] in changed)
        new_events = {}
        violations = []
        # (a) new routes vs untouched routes
        for rid in ids:
            for other, other_prepared in planes.items():
                if other in changed:
                    continue
                result = F.evaluate_pair(other_prepared, new_prepared[rid],
                                         CLEARANCE, SAGITTA, 'strict')
                if result is None:
                    continue
                if not result.get('valid'):
                    violations.extend(result.get('violations') or [])
                    continue
                for crossing in result.get('crossings') or ():
                    pair = _pair_key(rid, other)
                    new_events[_event_key(pair, crossing['point'][0],
                                          crossing['point'][1])] = dict(
                        angle_deg=_angle_from_sine(crossing['sine']),
                        x=float(crossing['point'][0]),
                        y=float(crossing['point'][1]))
        # (b) new routes among themselves
        for index, rid in enumerate(ids):
            for other in ids[index + 1:]:
                result = F.evaluate_pair(new_prepared[rid], new_prepared[other],
                                         CLEARANCE, SAGITTA, 'strict')
                if result is None:
                    continue
                if not result.get('valid'):
                    violations.extend(result.get('violations') or [])
                    continue
                for crossing in result.get('crossings') or ():
                    pair = _pair_key(rid, other)
                    new_events[_event_key(pair, crossing['point'][0],
                                          crossing['point'][1])] = dict(
                        angle_deg=_angle_from_sine(crossing['sine']),
                        x=float(crossing['point'][0]),
                        y=float(crossing['point'][1]))
        if violations:
            return dict(ok=False, violations=violations, delta=None)
        return dict(ok=True, violations=[], new_events=new_events,
                    delta=len(new_events) - old_inside)

    # -------------------------------------------------------------- updates
    def apply_route(self, rid, new_route, new_prims, crossings):
        """Commit one accepted body replacement into the authoritative state.

        ``crossings`` is the exact pair list returned by
        :meth:`evaluate_candidate` for this same candidate.
        """
        rid = int(rid)
        z = self.route_plane[rid]
        events = self.plane_events[z]
        for key in [key for key in events if rid in key[0]]:
            events.pop(key)
        self.prepared[z][rid] = F.prepare_route(new_prims, route_id=rid)
        self.groups[z][rid] = [dict(prim) for prim in new_prims]
        for other, angle, x, y in crossings:
            pair = _pair_key(rid, other)
            events[_event_key(pair, x, y)] = dict(angle_deg=float(angle),
                                                  x=float(x), y=float(y))
        self.routes[rid] = new_route
        self.world.set_route(rid, new_route)
        self.route_plane_prims[rid] = self.groups[z][rid]
        self._reindex_plane(z)
        return True

    def audit_plane(self, z):
        """Authoritative strict-D56 audit of one physical plane (current state)."""
        return F.audit_route_pairs(list(self.prepared[z].values()),
                                   clearance=CLEARANCE, sagitta=SAGITTA,
                                   policy='strict')

    def events_from_audit(self, audit):
        events = {}
        for crossing in audit.get('crossings') or ():
            pair = _pair_key(crossing['route_a'], crossing['route_b'])
            key = _event_key(pair, crossing['x'], crossing['y'])
            events[key] = dict(angle_deg=float(crossing['angle_deg']),
                               x=float(crossing['x']),
                               y=float(crossing['y']))
        return events

    def adopt_plane_events(self, z, events):
        """Replace the plane bookkeeping with a freshly audited event set."""
        self.plane_events[z] = events
        self._reindex_plane(z)

    def plane_snapshot(self, z, ids):
        return dict(
            events=dict(self.plane_events[z]),
            prepared=dict(self.prepared[z]),
            groups=dict(self.groups[z]),
            routes={int(rid): self.routes[int(rid)] for rid in ids})

    def restore_plane(self, z, snapshot):
        self.plane_events[z] = snapshot['events']
        self.prepared[z] = snapshot['prepared']
        self.groups[z] = snapshot['groups']
        for rid, route in snapshot['routes'].items():
            self.routes[int(rid)] = route
            self.world.set_route(int(rid), route)
        self._reindex_plane(z)

    def _reindex_plane(self, z):
        events = self.plane_events[z]
        angles = [event['angle_deg'] for event in events.values()]
        self.plane_min_angle[z] = min(angles) if angles else None
        self._rebuild_pair_counts()
        self._rebuild_route_crossings()
        self.total_crossings = sum(len(plane) for plane in
                                   self.plane_events.values())
        self.unique_pairs = sum(1 for value in self.pair_counts.values()
                                if value > 0)

    def apply_batch(self, replacements, new_events):
        """Commit an accepted batch using its pre-computed pair events.

        ``new_events`` comes from :meth:`evaluate_batch` (pairs of batch routes
        with untouched routes plus pairs inside the batch); untouched pairs are
        unchanged by definition, so no full re-audit is needed.
        """
        ids = sorted(int(rid) for rid in replacements)
        id_set = set(ids)
        z = {self.route_plane[rid] for rid in ids}
        z = z.pop()
        kept = {key: event for key, event in self.plane_events[z].items()
                if key[0][0] not in id_set and key[0][1] not in id_set}
        kept.update({key: dict(event) for key, event in new_events.items()})
        self.plane_events[z] = kept
        for rid in ids:
            self.prepared[z][rid] = F.prepare_route(replacements[rid],
                                                    route_id=rid)
            self.groups[z][rid] = [dict(prim) for prim in replacements[rid]]
            self.routes[rid] = _route_with_body(self.routes[rid], rid,
                                                replacements[rid], self.freeze)
            self.world.set_route(rid, self.routes[rid])
            self.route_plane_prims[rid] = self.groups[z][rid]
        self._reindex_plane(z)
        return True

    def _rebuild_pair_counts(self):
        counts = Counter()
        for events in self.plane_events.values():
            for key in events:
                counts[key[0]] += 1
        self.pair_counts = counts
        self.unique_pairs = sum(1 for value in counts.values() if value > 0)

    def _rebuild_route_crossings(self):
        counts = Counter()
        for events in self.plane_events.values():
            for key in events:
                counts[key[0][0]] += 1
                counts[key[0][1]] += 1
        self.route_crossings = counts

    # ---------------------------------------------------------- 3-D clearance
    def body_3d_issues(self, rid, new_route, limit=None):
        """True-3-D clearance of the *new body* against other transitions.

        The route's own transitions and lead flats are frozen and were already
        legal, so only ``flat(new body) - transition(other routes)`` can change
        (different-height flat/flat pairs are >= one 50 um plane pitch apart).
        """
        limit = G5.LIMIT_3D + G5.CREATE_MARGIN_3D if limit is None else limit
        z = self.route_plane[rid]
        chain = G5.RouteChain(new_route)
        item = chain.by_z.get(round(float(z), 9))
        if item is None:
            return [dict(kind='body_plane_missing')]
        issues = []
        for curve in item['curves']:
            for entry in self.world.transitions_near(z, curve['bbox']):
                other, part_index, transition, _footprint = entry
                if int(other) == int(rid):
                    continue
                if not (transition.z_min - 0.05 - 1e-9 <= z
                        <= transition.z_max + 0.05 + 1e-9):
                    continue
                if not G5._bbox_close(G5._transition_bbox(transition, 0.25),
                                      curve['bbox'], 0.2):
                    continue
                value, point = G5.transition_flat_min(transition, curve)
                if value < limit:
                    issues.append(dict(kind='3d_flat_transition',
                                       other=int(other), z=z,
                                       distance_mm=value,
                                       point=[round(v, 6) for v in point]))
        return issues

    def full_reaudit(self):
        """Independent full re-audit (all planes) to detect bookkeeping drift."""
        started = time.time()
        total = 0
        pairs = Counter()
        min_angle = None
        violations = []
        for z, prepared in self.prepared.items():
            audit = F.audit_route_pairs(list(prepared.values()),
                                        clearance=CLEARANCE, sagitta=SAGITTA,
                                        policy='strict')
            events = {}
            for crossing in audit.get('crossings') or ():
                pair = _pair_key(crossing['route_a'], crossing['route_b'])
                key = _event_key(pair, crossing['x'], crossing['y'])
                events[key] = dict(angle_deg=float(crossing['angle_deg']),
                                   x=float(crossing['x']),
                                   y=float(crossing['y']))
            total += len(events)
            for key, event in events.items():
                pairs[key[0]] += 1
                if min_angle is None or event['angle_deg'] < min_angle:
                    min_angle = event['angle_deg']
            violations.extend(audit.get('violations') or [])
        unique = sum(1 for value in pairs.values() if value > 0)
        self._audit_seconds = time.time() - started
        return dict(crossings=total, unique_pairs=unique,
                    min_angle=min_angle, violations=len(violations),
                    seconds=round(self._audit_seconds, 3),
                    matches=(total == self.total_crossings and
                             unique == self.unique_pairs and
                             abs((min_angle or 0.0)
                                 - (self.min_angle() or 0.0)) < 1e-9))


def replacement_ids(ids):
    return set(int(rid) for rid in ids)


def body_primitives(route, freeze_entry):
    index = freeze_entry['body_index']
    return [dict(prim) for prim in route['parts'][index].get('primitives') or []]


def _route_with_body(route, rid, prims, freeze):
    import copy
    entry = freeze['entries'][str(rid)]
    new = copy.deepcopy(route)
    new['parts'][entry['body_index']]['primitives'] = [dict(prim) for prim in prims]
    from ..g5 import candidates as C5
    return C5._finalise(new)


def _routes_length(routes):
    total = 0.0
    for route in routes.values():
        for part in route.get('parts') or ():
            total += float(part.get('length_mm') or 0.0)
    return total
