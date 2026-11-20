# -*- coding: utf-8 -*-
"""Incremental exact world for the XYZ joint router.

The state keeps

* the 1024 route records (native multi-height part chains),
* one strict D56 index per **physical height** (exact same counting rule as the
  frozen ``crossing_cache`` / ``nonc4.crossings`` audit),
* a lazily rebuilt true-3D ``l3d.world.World`` used to accept a replacement,

and supports transactional replacement of one route: ``evaluate_candidate``
returns the exact crossing delta + the real 3D violations; ``commit`` applies it;
``rollback`` restores the previous route.
"""
from __future__ import annotations

import copy
import math
import time
from collections import Counter, OrderedDict

from ...d56.index import D56Index
from ...d56.index import prepare as d56_prepare
from ...fsd25d import path3d as P3
from ...l3d.world import World
from .. import common as C
from ..native3d import common as N
from ..reheight21 import model as M
from . import route_builder as RB

CLEARANCE_MM = 0.05
OBSTACLE_WINDOW_MM = 0.12


def plane_key(z_mm):
    return round(float(z_mm), 9)


def new_index():
    return D56Index(width=float(C.WIDTH_MM), gap=float(C.EDGE_GAP_MM),
                    sagitta=0.0005, min_cross_angle_deg=5.0,
                    crossing_policy='strict')


def _compile_xy(prim):
    from ...conflicts import _make_primitive
    clean = {key: value for key, value in prim.items()
             if key not in ('layer', 'z')}
    return _make_primitive(clean)


class PlanePrimGrid:
    """Coarse grid over the flat primitives of ONE physical height.

    Used only as a **cheap crossing pre-rank** for XY candidate bodies: the
    exact D56 strict evaluation still decides validity / crossing counts.  The
    pre-rank cuts the number of expensive D56 evaluations by ~20x.
    """

    CELL_MM = 2.0

    def __init__(self, prims_by_route):
        from ...conflicts import _bbox_distance  # noqa: F401 (API parity)
        self.entries = []
        self.grid = {}
        cell = self.CELL_MM
        for rid, prims in prims_by_route.items():
            for prim in prims:
                try:
                    compiled = _compile_xy(prim)
                except Exception:  # noqa: BLE001 - degenerate primitive
                    continue
                bounds = compiled.bounds
                key = len(self.entries)
                self.entries.append((int(rid), compiled, bounds))
                x0 = int(math.floor(bounds[0] / cell))
                x1 = int(math.floor(bounds[2] / cell))
                y0 = int(math.floor(bounds[1] / cell))
                y1 = int(math.floor(bounds[3] / cell))
                for ix in range(x0, x1 + 1):
                    for iy in range(y0, y1 + 1):
                        self.grid.setdefault((ix, iy), []).append(key)

    def crossings(self, prims, exclude_route=None):
        from ...conflicts import _intersections
        from ...conflicts import _bbox_distance
        total = 0
        exclude = None if exclude_route is None else int(exclude_route)
        cell = self.CELL_MM
        entries = self.entries
        seen = set()
        for prim in prims:
            try:
                compiled = _compile_xy(prim)
            except Exception:  # noqa: BLE001
                continue
            bounds = compiled.bounds
            x0 = int(math.floor(bounds[0] / cell))
            x1 = int(math.floor(bounds[2] / cell))
            y0 = int(math.floor(bounds[1] / cell))
            y1 = int(math.floor(bounds[3] / cell))
            for ix in range(x0, x1 + 1):
                for iy in range(y0, y1 + 1):
                    for key in self.grid.get((ix, iy), ()):
                        if key in seen:
                            continue
                        seen.add(key)
                        rid, other, other_bounds = entries[key]
                        if exclude is not None and rid == exclude:
                            continue
                        if _bbox_distance(bounds, other_bounds) > 1e-9:
                            continue
                        points, overlap = _intersections(compiled, other)
                        total += len(points)
                        if overlap:
                            total += 8
        return int(total)


def route_flat_groups(route):
    """``{z_key: [chain, ...]}`` of one route (flat parts only, real prims)."""
    groups = OrderedDict()
    for part in route.get('parts') or ():
        if part.get('kind') != 'flat':
            continue
        prims = [dict(prim) for prim in (part.get('primitives') or ())]
        if not prims:
            continue
        groups.setdefault(plane_key(part['z_mm']), []).append(prims)
    return groups


def _merged(groups, z_key):
    merged = []
    for chain in groups.get(z_key) or ():
        merged.extend(chain)
    return merged


class RouteWorld:
    """The 1024-route 3D world with exact incremental crossing bookkeeping."""

    def __init__(self, routes, rows, log=None, clearance=CLEARANCE_MM):
        self.log = log or (lambda *_a, **_k: None)
        self.clearance = float(clearance)
        self.routes = OrderedDict()
        for route in routes:
            self.routes[int(route['route_id'])] = copy.deepcopy(route)
        self.rows = OrderedDict()
        for row in rows:
            self.rows[int(row['route_id'])] = dict(row)
        self.planes = {}          # z_key -> D56Index
        self.plane_prims = {}     # z_key -> {rid: [prims merged]}
        self.plane_chains = {}    # z_key -> {rid: prepared}
        self.plane_counts = {}    # z_key -> (events, pairs)
        self.obstacle_samples = []  # [(x, y, z, rid)]
        self.obstacle_cache = {}    # z_key -> [dict]
        self.prim_grids = {}        # z_key -> PlanePrimGrid
        self.world_cache = {}       # 'all' -> World
        self.total = 0
        self.pairs = 0
        self._route_groups = {}
        self.history = []
        self.last_reason = None
        self.build_time = 0.0
        self._build()

    # ------------------------------------------------------------------ build
    def _build(self):
        started = time.time()
        self.planes = {}
        self.plane_prims = {}
        self.plane_chains = {}
        self._route_groups = {}
        for rid, route in self.routes.items():
            groups = route_flat_groups(route)
            self._route_groups[rid] = groups
            for z_key, chains in groups.items():
                merged = []
                for chain in chains:
                    merged.extend(chain)
                self.plane_prims.setdefault(z_key, {})[rid] = merged
                prepared = d56_prepare(merged)
                self.plane_chains.setdefault(z_key, {})[rid] = prepared
                index = self.planes.get(z_key)
                if index is None:
                    index = new_index()
                    self.planes[z_key] = index
                index.add(rid, prepared)
        self._recount_planes()
        self.obstacle_samples = self._build_obstacle_samples()
        self.obstacle_cache = {}
        self.prim_grids = {}
        self.build_time = time.time() - started

    def _recount_planes(self):
        from ..nonc4 import crossings as X
        self.plane_counts = {}
        self.total = 0
        self.pairs = 0
        for z_key in sorted(self.planes):
            prims = {rid: list(chain) for rid, chain in
                     self.plane_prims.get(z_key, {}).items()}
            if not prims:
                continue
            result = X.audit_flat_group(prims)
            events = int(result.get('crossing_count') or 0)
            pairs = int(result.get('crossing_pair_count') or 0)
            self.plane_counts[z_key] = (events, pairs)
            self.total += events
            self.pairs += pairs

    def _build_obstacle_samples(self):
        samples = []
        for rid, route in self.routes.items():
            for part in route.get('parts') or ():
                if part.get('kind') != 'transition':
                    continue
                for sample in P3.transition_samples(part, step=0.1):
                    samples.append((float(sample[0]), float(sample[1]),
                                    float(sample[2]), int(rid)))
        return samples

    # ---------------------------------------------------------------- queries
    def route(self, route_id):
        return self.routes[int(route_id)]

    def row(self, route_id):
        return self.rows[int(route_id)]

    def groups(self, route_id):
        return self._route_groups[int(route_id)]

    def plane_index(self, z_key):
        return self.planes.get(plane_key(z_key))

    def route_plane_events(self, route_id, z_key):
        """Exact crossing events of one route in one physical plane."""
        rid = int(route_id)
        z_key = plane_key(z_key)
        index = self.planes.get(z_key)
        chains = self._route_groups.get(rid, {}).get(z_key) or []
        if index is None or not chains:
            return 0
        present = rid in self.plane_chains.get(z_key, {})
        if present:
            index.remove(rid)
        events = 0
        try:
            for chain in chains:
                evaluation = index.evaluate(d56_prepare([dict(p) for p in chain]))
                events += len(getattr(evaluation, 'crossings', ()) or ())
        finally:
            if present:
                index.add(rid, self.plane_chains[z_key][rid])
        return events

    def crossing_delta(self, route_id, new_route):
        """Exact (new_total - old_total) of replacing one route's flat chains."""
        rid = int(route_id)
        old_groups = self._route_groups.get(rid) or {}
        new_groups = route_flat_groups(new_route)
        affected = sorted(set(old_groups) | set(new_groups))
        delta = 0
        per_plane = {}
        for z_key in affected:
            old_events = self.route_plane_events(rid, z_key)
            index = self.planes.get(z_key)
            new_events = 0
            if index is not None:
                present = rid in self.plane_chains.get(z_key, {})
                if present:
                    index.remove(rid)
                try:
                    for chain in new_groups.get(z_key) or ():
                        evaluation = index.evaluate(
                            d56_prepare([dict(p) for p in chain]))
                        new_events += len(getattr(evaluation, 'crossings', ()) or ())
                finally:
                    if present:
                        index.add(rid, self.plane_chains[z_key][rid])
            delta += new_events - old_events
            per_plane[z_key] = dict(old=old_events, new=new_events)
        return delta, per_plane

    def plane_routes(self, z_key, exclude_route=None):
        """``{rid: prims}`` of the given physical plane (layer2d initial routes)."""
        z_key = plane_key(z_key)
        exclude_route = None if exclude_route is None else int(exclude_route)
        out = {}
        for rid, prims in (self.plane_prims.get(z_key) or {}).items():
            if exclude_route is not None and int(rid) == exclude_route:
                continue
            out[int(rid)] = [dict(prim) for prim in prims]
        return out

    def obstacles_for_z(self, z_mm):
        z_key = plane_key(z_mm)
        cached = self.obstacle_cache.get(z_key)
        if cached is not None:
            return cached
        z = float(z_key)
        samples = [dict(x=x, y=y, z=sample_z, route_id=rid)
                   for (x, y, sample_z, rid) in self.obstacle_samples
                   if abs(z - sample_z) < OBSTACLE_WINDOW_MM]
        self.obstacle_cache[z_key] = samples
        return samples

    def route_counts_by_plane(self):
        return {z_key: len(prims) for z_key, prims in self.plane_prims.items()}

    # ------------------------------------------------- cheap crossing pre-rank
    def prim_grid(self, z_key):
        z_key = plane_key(z_key)
        grid = self.prim_grids.get(z_key)
        if grid is None:
            grid = PlanePrimGrid(self.plane_prims.get(z_key) or {})
            self.prim_grids[z_key] = grid
        return grid

    def fast_crossings(self, z_key, prims, exclude_route=None):
        return self.prim_grid(z_key).crossings(prims, exclude_route=exclude_route)

    def assigned_counts(self):
        counts = Counter()
        for rid, row in self.rows.items():
            counts[int(row.get('target_layer', 0))] += 1
        return counts

    # ----------------------------------------------------------- 3D checking
    def _world_all(self):
        world = self.world_cache.get('all')
        if world is None:
            world = World(M.layer_stack(), clearance=self.clearance)
            for rid in sorted(self.routes):
                world.add_route(self.routes[rid])
            self.world_cache = {'all': world}
        return world

    def world_without(self, route_id):
        """True-3D world that hides exactly one route (slow ground truth)."""
        rid = int(route_id)
        world = World(M.layer_stack(), clearance=self.clearance)
        for other_id, route in self.routes.items():
            if other_id == rid:
                continue
            world.add_route(route)
        return world

    def check_3d(self, route_id, new_route):
        world = self._world_all()
        rid = int(route_id)
        world.ignore_route(rid)
        try:
            violations = world.check_route(new_route, check_self=True)
        except Exception as error:  # noqa: BLE001 - defensive
            violations = [dict(kind='exception', detail=str(error))]
        finally:
            world.restore_route(rid)
        return violations

    def validate_all(self, log=None):
        """Fresh true-3D world: add every route in id order, report violations."""
        log = log or (lambda *_a, **_k: None)
        started = time.time()
        world = World(M.layer_stack(), clearance=self.clearance)
        violations = []
        valid = 0
        for rid in sorted(self.routes):
            route = self.routes[rid]
            structural = World.check_structure(route)
            if structural:
                violations.append(dict(route_id=rid, kind='structure',
                                       detail=structural[:6]))
                continue
            found = world.check_route(route)
            if found:
                for record in found:
                    record = dict(record)
                    record.setdefault('route_id', rid)
                    violations.append(record)
                continue
            world.add_route(route)
            valid += 1
        kinds = Counter(record.get('kind') for record in violations)
        return dict(valid=valid, violations=violations,
                    violation_kinds=dict(kinds),
                    seconds=round(time.time() - started, 3))

    # ------------------------------------------------------------ transaction
    def evaluate_candidate(self, route_id, new_route, check_3d=True):
        rid = int(route_id)
        started = time.time()
        violations = self.check_3d(rid, new_route) if check_3d else []
        if violations:
            return dict(ok=False, delta=None, violations=violations,
                        kinds=[v.get('kind') for v in violations[:6]],
                        seconds=time.time() - started)
        delta, per_plane = self.crossing_delta(rid, new_route)
        return dict(ok=True, delta=int(delta), per_plane=per_plane,
                    violations=[], kinds=[], seconds=time.time() - started)

    def commit(self, route_id, new_route, new_row=None, note=''):
        """Apply a replacement (transactional: caller must have checked it)."""
        rid = int(route_id)
        old_route = self.routes[rid]
        old_row = self.rows[rid]
        old_groups = self._route_groups.get(rid) or {}
        new_groups = route_flat_groups(new_route)
        old_plane_events = {z: self.route_plane_events(rid, z) for z in
                            set(old_groups) | set(new_groups)}
        delta, per_plane = self.crossing_delta(rid, new_route)
        # remove old chains
        for z_key in old_groups:
            index = self.planes.get(z_key)
            if index is not None and rid in self.plane_chains.get(z_key, {}):
                index.remove(rid)
                self.plane_chains[z_key].pop(rid, None)
                self.plane_prims.get(z_key, {}).pop(rid, None)
        # add new chains
        for z_key, chains in new_groups.items():
            merged = []
            for chain in chains:
                merged.extend(chain)
            prepared = d56_prepare(merged)
            self.plane_prims.setdefault(z_key, {})[rid] = merged
            self.plane_chains.setdefault(z_key, {})[rid] = prepared
            index = self.planes.get(z_key)
            if index is None:
                index = new_index()
                self.planes[z_key] = index
            index.add(rid, prepared)
        self.routes[rid] = copy.deepcopy(new_route)
        if new_row is not None:
            self.rows[rid] = dict(new_row)
        self._route_groups[rid] = new_groups
        self.total += int(delta)
        self._recount_planes()
        # incremental caches: keep the true 3D world in sync, refresh obstacles
        world = self.world_cache.get('all')
        if world is not None:
            world.replace_route(rid, self.routes[rid])
        self.obstacle_samples = self._build_obstacle_samples()
        self.obstacle_cache = {}
        self.prim_grids = {}
        record = dict(route_id=rid, delta=int(delta), total=int(self.total),
                      old_layer=int(old_row.get('target_layer', 0)),
                      new_layer=int((new_row or {}).get('target_layer', 0)),
                      old_z=float(old_row.get('target_z_mm', 0.0)),
                      new_z=float((new_row or {}).get('target_z_mm', 0.0)),
                      note=str(note),
                      per_plane={str(k): v for k, v in per_plane.items()},
                      old_length=float(old_route.get('length_mm') or 0.0),
                      new_length=float(new_route.get('length_mm') or 0.0),
                      old_plan=dict(old_plane_events))
        self.history.append(record)
        return record

    # --------------------------------------------------------- batch replace
    def batch_evaluate(self, replacements, log=None):
        """3D validity of replacing several routes at once (transactional check).

        ``replacements`` is ``{route_id: new_route}``.  Returns
        ``dict(ok, violations, checked)``; the state is NOT modified.
        """
        rids = sorted(int(rid) for rid in replacements)
        world = self._world_all()
        for rid in rids:
            world.ignore_route(rid)
        violations = []
        added = []
        try:
            for rid in rids:
                new_route = replacements[rid]
                structural = World.check_structure(new_route)
                if structural:
                    violations.append(dict(route_id=rid, kind='structure',
                                           detail=structural[:6]))
                    continue
                found = world.check_route(new_route)
                if found:
                    for record in found:
                        record = dict(record)
                        record.setdefault('route_id', rid)
                        violations.append(record)
                    continue
                world.add_route(new_route)
                added.append(rid)
        finally:
            for rid in rids:
                world.restore_route(rid)
        if added:
            # temporary additions polluted the shared world: drop and rebuild
            self.world_cache = {}
        return dict(ok=not violations, violations=violations,
                    checked=len(rids), added=added)

    def batch_commit(self, replacements, new_rows=None, note=''):
        """Apply several replacements with one exact crossing recount."""
        new_rows = new_rows or {}
        rids = sorted(int(rid) for rid in replacements)
        affected = set()
        for rid in rids:
            affected.update(self._route_groups.get(rid) or {})
            affected.update(route_flat_groups(replacements[rid]))
        old_total = int(self.total)
        old_plane_counts = {z: self.plane_counts.get(z, (0, 0)) for z in affected}
        for rid in rids:
            old_groups = self._route_groups.get(rid) or {}
            for z_key in old_groups:
                index = self.planes.get(z_key)
                if index is not None and rid in self.plane_chains.get(z_key, {}):
                    index.remove(rid)
                    self.plane_chains[z_key].pop(rid, None)
                    self.plane_prims.get(z_key, {}).pop(rid, None)
        for rid in rids:
            new_route = replacements[rid]
            new_groups = route_flat_groups(new_route)
            for z_key, chains in new_groups.items():
                merged = []
                for chain in chains:
                    merged.extend(chain)
                prepared = d56_prepare(merged)
                self.plane_prims.setdefault(z_key, {})[rid] = merged
                self.plane_chains.setdefault(z_key, {})[rid] = prepared
                index = self.planes.get(z_key)
                if index is None:
                    index = new_index()
                    self.planes[z_key] = index
                index.add(rid, prepared)
            self.routes[rid] = copy.deepcopy(new_route)
            if rid in new_rows:
                self.rows[rid] = dict(new_rows[rid])
            self._route_groups[rid] = new_groups
        self._recount_planes()
        self.obstacle_samples = self._build_obstacle_samples()
        self.obstacle_cache = {}
        self.prim_grids = {}
        self.world_cache = {}
        record = dict(kind='batch', routes=rids,
                      old_total=old_total, total=int(self.total),
                      delta=int(self.total) - old_total, note=str(note),
                      old_planes={str(z): v for z, v in old_plane_counts.items()})
        self.history.append(record)
        return record

    def batch_crossing_delta(self, replacements):
        """Exact crossing delta of replacing several routes (no state change)."""
        from ..nonc4 import crossings as X
        rids = sorted(int(rid) for rid in replacements)
        affected = set()
        for rid in rids:
            affected.update(self._route_groups.get(rid) or {})
            affected.update(route_flat_groups(replacements[rid]))
        before = 0
        after = 0
        for z_key in sorted(affected):
            before += int(self.plane_counts.get(z_key, (0, 0))[0])
            prims = {}
            for rid, merged in (self.plane_prims.get(z_key) or {}).items():
                if rid in replacements:
                    continue
                prims[int(rid)] = list(merged)
            for rid in rids:
                groups = route_flat_groups(replacements[rid])
                merged = []
                for chain in groups.get(z_key) or ():
                    merged.extend(chain)
                if merged:
                    prims[int(rid)] = merged
            if not prims:
                continue
            result = X.audit_flat_group(prims)
            after += int(result.get('crossing_count') or 0)
        return int(after - before), dict(before=before, after=after,
                                          planes=sorted(affected))

    # -------------------------------------------------------------- reporting
    def per_route_counts(self):
        from ..native3d.crossing_cache import CrossingCache
        cache = CrossingCache(list(self.routes.values()))
        return cache.per_route(), cache

    def total_length(self):
        return float(sum(float(route.get('length_mm') or 0.0)
                         for route in self.routes.values()))

    def mid_transition_count(self):
        return int(sum(int(route.get('n_mid_transitions') or 0)
                       for route in self.routes.values()))

    def summary(self):
        return dict(total_crossings=int(self.total),
                    total_pairs=int(self.pairs),
                    routes=len(self.routes),
                    total_length_mm=round(self.total_length(), 6),
                    mid_transitions=self.mid_transition_count(),
                    plane_counts={str(z): dict(events=v[0], pairs=v[1],
                                               routes=len(self.plane_prims.get(z, {})))
                                  for z, v in sorted(self.plane_counts.items())},
                    build_seconds=round(self.build_time, 3))
