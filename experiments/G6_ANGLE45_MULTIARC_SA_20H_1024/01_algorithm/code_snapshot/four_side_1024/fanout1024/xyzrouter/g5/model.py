# -*- coding: utf-8 -*-
"""Exact route model for G5: per-height chains, strict D56 + 45 deg crossing rule.

This module is the *search-side* legality engine.  It is deliberately thin on
new geometry algebra: the exact 2-D primitive algebra (line / R15 arc
intersection, distance, tangents) and the analytic R15 S-curve of the vertical
transitions come from the audited ``xyzrouter.g4.independent_metrics`` module
(which reproduces the frozen G4 numbers exactly).  What is new here is

* the **45 deg crossing-angle hard rule** (G5) instead of the G4 5 deg rule,
* per-height chain bookkeeping that survives part splitting (multi-flat routes),
* an incremental, region-limited route evaluator (used by the search),
* the 3-D clearance checks (transition vs flat / flat / transition), and
* exact structural checks (heights, R15, continuity, glass, port identity).

Conventions (identical to the frozen audit):

* a ``flat`` part is at one physical height ``z``; only flats **at the same z**
  can genuinely cross;
* a genuine crossing is a single transverse interior intersection of two
  primitives of different routes, and its angle is
  ``theta = degrees(asin(|t_a x t_b|))`` with exact local tangents;
* around a crossing the pair may come closer than 0.08 mm only inside the
  crossing window; outside it the strict 0.08 mm centre-line clearance holds;
* different heights need a true 3-D centre-line distance >= 0.05 mm.
"""
from __future__ import annotations

import copy
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: install the 20-height profile BEFORE any ``reheight21.model`` import below
from four_side_1024.fanout1024.coldstart20 import bootstrap as _bootstrap
_bootstrap.install()

from four_side_1024.fanout1024.xyzrouter.g4 import independent_metrics as IM
from four_side_1024.fanout1024.xyzrouter.g4.independent_metrics import Transition


def _repair_native3d_tables():
    """Make ``native3d.common`` see the installed 20-height table.

    ``native3d.common`` builds its height tables at *import* time; when it is
    imported before ``coldstart20.bootstrap`` installed the 20-height model its
    tables keep the frozen 21-height values and every ``plane_of_z`` call then
    rejects a legal 20-height plane.  Importing this module always precedes the
    G5 geometry code, so the tables are re-derived from the installed model.
    """
    try:
        from collections import OrderedDict
        from four_side_1024.fanout1024.native3d import common as N3
        from four_side_1024.fanout1024.reheight21 import model as M
    except Exception:  # noqa: BLE001
        return
    N3.PLANE_Z = OrderedDict((int(pid), float(M.plane_z(pid)))
                             for pid in M.PLANE_IDS)
    N3.Z_PLANE = OrderedDict((round(z, 9), int(pid))
                             for pid, z in N3.PLANE_Z.items())
    N3.PLANE_LABEL = OrderedDict((int(pid), M.plane_label(pid))
                                 for pid in M.PLANE_IDS)
    N3.MANUAL_PLANES = tuple(int(pid) for pid in M.MANUAL_PLANE_IDS)
    N3.MOVABLE_PLANES = tuple(int(pid) for pid in M.PLANE_IDS
                              if int(pid) not in set(M.MANUAL_PLANE_IDS))


_repair_native3d_tables()

# --------------------------------------------------------------------- contract
CLEARANCE_2D_MM = 0.08
WIDTH_MM = 0.05
EDGE_GAP_MM = 0.03
MIN_3D_CLEARANCE_MM = 0.05
R15_MM = 15.0
SAGITTA_MM = 0.0005
STRICT_MAX_HALF_WINDOW_MM = 4.0
GLASS_XY_MM = 150.0
GLASS_Z_MIN_MM = -0.35
GLASS_Z_MAX_MM = 0.65
#: G5 hard rule (degrees)
THETA_MIN_DEG = 45.0
#: old G4 rule, only used to classify "tangent touch" as an extra sub-kind
OLD_MIN_ANGLE_DEG = 5.0

LIMIT_2D = CLEARANCE_2D_MM - 1e-7
LIMIT_3D = MIN_3D_CLEARANCE_MM - 1e-9
#: creation margin: the frozen validator flags transition-vs-flat distances of
#: exactly 0.05 mm, so the search keeps 0.5 um of slack when it *accepts* a move
CREATE_MARGIN_3D = 0.011
GRID_CELL_MM = 1.0
GRID_PAD_MM = 0.20


def _model():
    from four_side_1024.fanout1024.reheight21 import model as M
    return M


def all_heights():
    return [float(_model().plane_z(pid)) for pid in _model().PLANE_IDS]


def plane_of_z(z_mm, tol=1e-6):
    for pid in _model().PLANE_IDS:
        if abs(float(_model().plane_z(pid)) - float(z_mm)) <= tol:
            return int(pid)
    return None


def plane_label(z_mm):
    pid = plane_of_z(z_mm)
    if pid is None:
        return '?'
    try:
        return str(_model().plane_label(pid))
    except Exception:  # noqa: BLE001
        return str(pid)


# ===========================================================================
# primitives
# ===========================================================================
def make_prim(prim):
    """Parse one JSON flat primitive into the audit representation (+z later)."""
    return IM._make_flat_prim(prim)


def prim_points(prim, count=64):
    if prim['kind'] == 'line':
        return ([prim['p0'][0], prim['p1'][0]], [prim['p0'][1], prim['p1'][1]])
    angles = [prim['start'] + prim['sweep'] * k / count
              for k in range(count + 1)]
    return ([prim['center'][0] + prim['radius'] * math.cos(a) for a in angles],
            [prim['center'][1] + prim['radius'] * math.sin(a) for a in angles])


def _merge(ivs):
    return IM._merge_intervals(list(ivs))


def _close_regions(chain, offsets, total, partner, limit):
    """Intervals of chain arc length closer than ``limit`` (audited version)."""
    intervals, _min, _point = IM._close_regions_on_chain(
        chain, offsets, total, partner, limit)
    return intervals


def _point_on_chain(chain, offsets, total, s):
    return IM._point_on_chain((chain, offsets, total), s)


def _edge_distance(chain, offsets, total, sa, partner, limit, direction):
    return IM._edge_distance((chain, offsets, total), sa, partner, limit,
                             direction)


# ===========================================================================
# route -> chains
# ===========================================================================
class RouteChain:
    """All flat primitives of one route grouped by physical height."""

    __slots__ = ('route_id', 'z_order', 'by_z', 'flat_parts', 'transitions',
                 'length_mm')

    def __init__(self, route):
        self.route_id = int(route['route_id'])
        by_z = OrderedZ = defaultdict(list)
        self.flat_parts = []
        transitions = []
        length = 0.0
        for part_index, part in enumerate(route.get('parts') or ()):
            kind = part.get('kind')
            if kind == 'flat':
                z = round(float(part['z_mm']), 9)
                curves = []
                for prim in part.get('primitives') or ():
                    curve = make_prim(prim)
                    curve['length'] = IM.prim_length(curve)
                    curve['z'] = float(part['z_mm'])
                    curve['route_id'] = self.route_id
                    curve['part_index'] = part_index
                    curves.append(curve)
                    length += curve['length']
                by_z[z].extend(curves)
                self.flat_parts.append((part_index, float(part['z_mm']), curves))
            elif kind == 'transition':
                tr = Transition(part)
                transitions.append(dict(part_index=part_index, part=part,
                                        transition=tr, z0=tr.z0, z1=tr.z1,
                                        z_min=tr.z_min, z_max=tr.z_max,
                                        length=tr.length,
                                        footprint=tr.footprint))
                length += tr.length
        self.by_z = {}
        for z, curves in by_z.items():
            offsets = []
            cursor = 0.0
            for curve in curves:
                offsets.append(cursor)
                cursor += curve['length']
            self.by_z[z] = dict(curves=curves, offsets=offsets, total=cursor)
        self.z_order = sorted(self.by_z)
        self.transitions = transitions
        self.length_mm = length

    def heights(self):
        return list(self.z_order)

    def curves_at(self, z):
        key = round(float(z), 9)
        item = self.by_z.get(key)
        return item['curves'] if item else []

    def chain_at(self, z):
        return self.by_z.get(round(float(z), 9))

    def bbox(self):
        xs = []
        ys = []
        for _pid, _z, curves in self.flat_parts:
            for curve in curves:
                xs.append(curve['bbox'][0])
                xs.append(curve['bbox'][2])
                ys.append(curve['bbox'][1])
                ys.append(curve['bbox'][3])
        for item in self.transitions:
            tr = item['transition']
            b = tr.start[0], tr.start[1]
            e = (tr.start[0] + tr.direction[0] * tr.footprint,
                 tr.start[1] + tr.direction[1] * tr.footprint)
            xs.extend([b[0], e[0]])
            ys.extend([b[1], e[1]])
        if not xs:
            return (0.0, 0.0, 0.0, 0.0)
        return (min(xs), min(ys), max(xs), max(ys))


# ===========================================================================
# strict same-height pair audit (D56 + 45 deg rule)
# ===========================================================================
def pair_audit(chain_a, chain_b, z, min_angle_deg=THETA_MIN_DEG,
               max_half_window=STRICT_MAX_HALF_WINDOW_MM,
               crossing_window_check=True):
    """Strict same-height audit of one route pair (G5 rule, 45 deg).

    The rule is applied at the **primitive-pair** level, exactly like the frozen
    project validator's D56 index: a primitive pair either (a) intersects once,
    transversally, interior to both primitives -- then it is a legal crossing
    and its angle must be >= ``min_angle_deg``, or (b) does not intersect --
    then its minimum distance must be >= 0.08 mm.  Coincident stretches
    (``overlap``) and multi-point primitive pairs (``double_cross``) are
    illegal.  ``crossing_window_check`` is kept for API compatibility; the
    window bookkeeping is no longer used for legality because the frozen
    validator is equivalent to the stricter pair rule above.
    """
    curves_a = chain_a['curves']
    curves_b = chain_b['curves']
    issues = []
    crossings = []
    overlap = False
    double = False
    records = []
    min_distance = float('inf')
    min_non_crossing = float('inf')
    contacts = 0
    pairs = 0
    for ca in curves_a:
        for cb in curves_b:
            if not _bbox_close(ca['bbox'], cb['bbox'], GRID_PAD_MM):
                continue
            pairs += 1
            points, common = IM.prim_intersections(ca, cb)
            if common:
                overlap = True
                break
            if len(points) > 1:
                double = True
                break
            if len(points) == 1:
                records.append((points[0], ca, cb))
                continue
            distance = IM.prim_prim_distance(ca, cb)
            if distance < min_distance:
                min_distance = distance
            if 1e-6 < distance < min_non_crossing:
                min_non_crossing = distance
            elif distance <= 1e-6:
                contacts += 1
            if 1e-6 < distance < LIMIT_2D:
                issues.append(dict(kind='clearance', z=z,
                                   distance_mm=distance,
                                   kind_a=ca['kind'], kind_b=cb['kind']))
            elif distance <= 1e-6:
                # exact endpoint coincidence: the frozen intersection algebra
                # (and the frozen validator) does not count it; keep it visible
                # as an informational contact, never as a hard failure.
                pass
        if overlap or double:
            break
    if overlap:
        return dict(crossings=[], issues=[dict(kind='overlap', z=z)],
                    min_distance=0.0, min_non_crossing=1e9, contacts=0)
    if double:
        return dict(crossings=[], issues=[dict(kind='double_cross', z=z)],
                    min_distance=0.0, min_non_crossing=1e9, contacts=0)
    if issues:
        return dict(crossings=[], issues=issues, min_distance=min_distance,
                    min_non_crossing=(min_non_crossing
                                      if min_non_crossing < float('inf') else 1e9),
                    contacts=contacts)
    # group coincident intersection points (junction crossings counted once)
    groups = []
    for point, ca, cb in records:
        t_a = IM.param_of_point(ca, point)
        t_b = IM.param_of_point(cb, point)
        tangent_a = IM.prim_tangent(ca, t_a)
        tangent_b = IM.prim_tangent(cb, t_b)
        sine = min(1.0, abs(tangent_a[0] * tangent_b[1]
                            - tangent_a[1] * tangent_b[0]))
        member = dict(point=point, sine=sine, ca=ca, cb=cb,
                      sa=_chain_sa(chain_a, ca, t_a),
                      sb=_chain_sa(chain_b, cb, t_b),
                      local_a=t_a, local_b=t_b)
        for group in groups:
            ref = group[0]
            if (abs(point[0] - ref['point'][0]) < 1e-6
                    and abs(point[1] - ref['point'][1]) < 1e-6):
                group.append(member)
                break
        else:
            groups.append([member])
    for group in groups:
        ref = group[0]
        angle = math.degrees(math.asin(ref['sine']))
        if min(ref['sa'], chain_a['total'] - ref['sa'],
               ref['sb'], chain_b['total'] - ref['sb']) < 1e-7:
            issues.append(dict(kind='endpoint_touch', z=z,
                               x=round(ref['point'][0], 6),
                               y=round(ref['point'][1], 6)))
            continue
        crossings.append(dict(
            z=z, x=ref['point'][0], y=ref['point'][1], angle_deg=angle,
            sine=ref['sine'], sa=ref['sa'], sb=ref['sb'],
            kind_a=ref['ca']['kind'], kind_b=ref['cb']['kind'],
            angle_ok=angle >= min_angle_deg))
    if issues:
        return dict(crossings=[], issues=issues, min_distance=0.0,
                    min_non_crossing=1e9, contacts=contacts)
    return dict(crossings=crossings, issues=[], min_distance=min_distance,
                min_non_crossing=1e9, contacts=contacts)


def _chain_sa(chain, curve, t):
    for index, candidate in enumerate(chain['curves']):
        if candidate is curve:
            return chain['offsets'][index] + t * curve['length']
    return t * curve['length']


def _bbox_close(a, b, pad):
    return not (a[0] - b[2] > pad or b[0] - a[2] > pad
                or a[1] - b[3] > pad or b[1] - a[3] > pad)


# ===========================================================================
# 3-D clearance of transitions
# ===========================================================================
def transition_flat_min(tr, flat_curve):
    """Exact min 3-D distance between one R15 S-curve and one flat primitive."""
    count = max(9, int(math.ceil(tr.length / 0.05)) + 1)
    import numpy as np
    ss = np.linspace(0.0, tr.length, count)
    xs, ys, zs = tr.points(ss)
    d2 = IM.point_prim_dist_array(xs, ys, flat_curve)
    values = np.hypot(d2, zs - flat_curve['z'])
    index = int(np.argmin(values))
    value, point = IM._transition_flat_minimum(
        tr, flat_curve, float(ss[max(0, index - 1)]),
        float(ss[min(len(ss) - 1, index + 1)]))
    return value, point


def transition_transition_min(tra, trb):
    import numpy as np
    na = max(9, int(math.ceil(tra.length / 0.05)) + 1)
    nb = max(9, int(math.ceil(trb.length / 0.05)) + 1)
    sa = np.linspace(0.0, tra.length, na)
    sb = np.linspace(0.0, trb.length, nb)
    xa, ya, za = tra.points(sa)
    xb, yb, zb = trb.points(sb)
    dx = xa[:, None] - xb[None, :]
    dy = ya[:, None] - yb[None, :]
    dz = za[:, None] - zb[None, :]
    values = np.sqrt(dx * dx + dy * dy + dz * dz)
    flat_index = int(np.argmin(values))
    ia, ib = divmod(flat_index, nb)
    step = max(tra.length / (na - 1), trb.length / (nb - 1))
    value, point, _sa, _sb = IM._transition_transition_minimum(
        tra, trb, float(sa[ia]), float(sb[ib]), step)
    return value, point


# ===========================================================================
# world
# ===========================================================================
class World:
    """Immutable-ish world of routes with a per-height spatial grid."""

    def __init__(self, routes, min_angle_deg=THETA_MIN_DEG):
        self.routes = {int(r['route_id']): r for r in routes}
        self.min_angle_deg = float(min_angle_deg)
        self.rebuild()

    # ---------------------------------------------------------------- rebuild
    def rebuild(self):
        self.chains = {}
        for rid, route in self.routes.items():
            self.chains[rid] = RouteChain(route)
        self.by_z = defaultdict(dict)      # z -> rid -> chain
        self.grid = defaultdict(lambda: defaultdict(list))  # z -> cell -> [(rid, idx)]
        self.transitions = []              # [(rid, part_index, Transition, footprint)]
        # transitions indexed by every routing height inside their z span
        # (+- one gap, so that a flat just outside the span is still found)
        self.trans_grid = defaultdict(lambda: defaultdict(list))
        self.heights = sorted(set(round(z, 9) for z in all_heights()))
        for rid, chain in self.chains.items():
            for z, item in chain.by_z.items():
                self.by_z[z][rid] = item
                for index, curve in enumerate(item['curves']):
                    box = curve['bbox']
                    x0 = int(math.floor((box[0] - GRID_PAD_MM) / GRID_CELL_MM))
                    x1 = int(math.floor((box[2] + GRID_PAD_MM) / GRID_CELL_MM))
                    y0 = int(math.floor((box[1] - GRID_PAD_MM) / GRID_CELL_MM))
                    y1 = int(math.floor((box[3] + GRID_PAD_MM) / GRID_CELL_MM))
                    for ix in range(x0, x1 + 1):
                        for iy in range(y0, y1 + 1):
                            self.grid[z][(ix, iy)].append((rid, index))
            for item in chain.transitions:
                entry = (rid, item['part_index'],
                         item['transition'], item['footprint'])
                self.transitions.append(entry)
                self._index_transition(entry)

    def set_route(self, rid, route):
        rid = int(rid)
        self._unindex_route(rid)
        self.routes[rid] = route
        self.chains[rid] = RouteChain(route)
        chain = self.chains[rid]
        for z, item in chain.by_z.items():
            self.by_z[z][rid] = item
            for index, curve in enumerate(item['curves']):
                box = curve['bbox']
                x0 = int(math.floor((box[0] - GRID_PAD_MM) / GRID_CELL_MM))
                x1 = int(math.floor((box[2] + GRID_PAD_MM) / GRID_CELL_MM))
                y0 = int(math.floor((box[1] - GRID_PAD_MM) / GRID_CELL_MM))
                y1 = int(math.floor((box[3] + GRID_PAD_MM) / GRID_CELL_MM))
                for ix in range(x0, x1 + 1):
                    for iy in range(y0, y1 + 1):
                        self.grid[z][(ix, iy)].append((rid, index))
        for item in chain.transitions:
            entry = (rid, item['part_index'], item['transition'],
                     item['footprint'])
            self.transitions.append(entry)
            self._index_transition(entry)

    def drop_route(self, rid):
        """Remove one route from every index (used by the batch evaluator)."""
        rid = int(rid)
        self._unindex_route(rid)
        self.chains.pop(rid, None)

    @staticmethod
    def _chain_cells(chain):
        """Every (height, grid cell) a chain occupies (flats + transitions)."""
        out = []
        for z, item in chain.by_z.items():
            for curve in item['curves']:
                box = curve['bbox']
                x0 = int(math.floor((box[0] - GRID_PAD_MM) / GRID_CELL_MM))
                x1 = int(math.floor((box[2] + GRID_PAD_MM) / GRID_CELL_MM))
                y0 = int(math.floor((box[1] - GRID_PAD_MM) / GRID_CELL_MM))
                y1 = int(math.floor((box[3] + GRID_PAD_MM) / GRID_CELL_MM))
                for ix in range(x0, x1 + 1):
                    for iy in range(y0, y1 + 1):
                        out.append((z, (ix, iy)))
        for item in chain.transitions:
            tr = item['transition']
            box = _transition_bbox(tr, pad=0.25)
            for z in World._plane_heights():
                if not (tr.z_min - 0.05 - 1e-9 <= z <= tr.z_max + 0.05 + 1e-9):
                    continue
                for cell in _cells(box, 0.0):
                    out.append((z, cell))
        return out

    @staticmethod
    def _plane_heights():
        return [float(_model().plane_z(pid)) for pid in _model().PLANE_IDS]

    def _unindex_route(self, rid):
        """Remove one route from the indexes by touching only its own cells."""
        rid = int(rid)
        chain = self.chains.get(rid)
        if chain is None:
            return
        for z, cell in self._chain_cells(chain):
            table = self.grid.get(z)
            if table is not None and cell in table:
                filtered = [e for e in table[cell] if e[0] != rid]
                if filtered:
                    table[cell] = filtered
                else:
                    del table[cell]
            ttable = self.trans_grid.get(z)
            if ttable is not None and cell in ttable:
                filtered = [e for e in ttable[cell] if e[0] != rid]
                if filtered:
                    ttable[cell] = filtered
                else:
                    del ttable[cell]
        for z in list(chain.by_z):
            self.by_z.get(z, {}).pop(rid, None)
        self.transitions = [item for item in self.transitions if item[0] != rid]

    # ------------------------------------------------------- transition index
    def _index_transition(self, entry):
        _rid, _pid, tr, _fp = entry
        box = _transition_bbox(tr, pad=0.25)
        for z in self.heights:
            if tr.z_min - 0.05 - 1e-9 <= z <= tr.z_max + 0.05 + 1e-9:
                x0 = int(math.floor(box[0] / GRID_CELL_MM))
                x1 = int(math.floor(box[2] / GRID_CELL_MM))
                y0 = int(math.floor(box[1] / GRID_CELL_MM))
                y1 = int(math.floor(box[3] / GRID_CELL_MM))
                for ix in range(x0, x1 + 1):
                    for iy in range(y0, y1 + 1):
                        self.trans_grid[z][(ix, iy)].append(entry)

    def transitions_near(self, z, box):
        """Transition entries whose bbox may be near ``box`` at height ``z``."""
        table = self.trans_grid.get(round(float(z), 9))
        if not table:
            return []
        x0 = int(math.floor(box[0] / GRID_CELL_MM))
        x1 = int(math.floor(box[2] / GRID_CELL_MM))
        y0 = int(math.floor(box[1] / GRID_CELL_MM))
        y1 = int(math.floor(box[3] / GRID_CELL_MM))
        out = {}
        for ix in range(x0, x1 + 1):
            for iy in range(y0, y1 + 1):
                for entry in table.get((ix, iy), ()):
                    out[(entry[0], entry[1])] = entry
        return list(out.values())

    # ------------------------------------------------------------ neighbour set
    def neighbours_at_z(self, rid, z, curves, pad=GRID_PAD_MM):
        """Route ids sharing a grid cell with any of ``curves`` at height ``z``."""
        table = self.grid.get(round(float(z), 9))
        if not table:
            return set()
        out = set()
        for curve in curves:
            box = curve['bbox']
            x0 = int(math.floor((box[0] - pad) / GRID_CELL_MM))
            x1 = int(math.floor((box[2] + pad) / GRID_CELL_MM))
            y0 = int(math.floor((box[1] - pad) / GRID_CELL_MM))
            y1 = int(math.floor((box[3] + pad) / GRID_CELL_MM))
            for ix in range(x0, x1 + 1):
                for iy in range(y0, y1 + 1):
                    for other, _index in table.get((ix, iy), ()):
                        if other != rid:
                            out.add(other)
        return out

    # -------------------------------------------------------------- full audit
    def audit_all(self, min_angle_deg=None, log=None, window_check=True):
        """Full-world same-height audit: all crossings, angle violations, issues."""
        min_angle = (self.min_angle_deg if min_angle_deg is None
                     else float(min_angle_deg))
        crossings = []
        violations = []
        issues = []
        min_non_crossing = (float('inf'), None)
        for z in sorted(self.by_z):
            routes_here = self.by_z[z]
            ids = sorted(routes_here)
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    ra, rb = ids[i], ids[j]
                    chain_a = routes_here[ra]
                    chain_b = routes_here[rb]
                    if not _chain_bbox_close(chain_a, chain_b, GRID_PAD_MM):
                        continue
                    result = pair_audit(chain_a, chain_b, z, min_angle,
                                        crossing_window_check=window_check)
                    for event in result['crossings']:
                        event.update(route_a=ra, route_b=rb)
                        crossings.append(event)
                        if not event['angle_ok']:
                            violations.append(event)
                    for issue in result['issues']:
                        issue.update(route_a=ra, route_b=rb)
                        issues.append(issue)
                    if result['min_non_crossing'] < min_non_crossing[0]:
                        min_non_crossing = (result['min_non_crossing'],
                                            dict(z=z, route_a=ra, route_b=rb))
        if log:
            log('[audit] crossings=%d violations=%d issues=%d min_non_crossing=%.9f'
                % (len(crossings), len(violations), len(issues),
                   min_non_crossing[0]))
        return dict(crossings=crossings, violations=violations, issues=issues,
                    min_non_crossing=min_non_crossing)

    # ------------------------------------------------------------- 3-D audit
    def audit_3d(self, log=None):
        """Every true 3-D clearance check of the world (>= 0.05 mm)."""
        issues = []
        minima = {}
        # (1) flat vs flat at different heights: always >= dz >= 0.05
        best = (float('inf'), None)
        zs = sorted(self.by_z)
        for ii in range(len(zs)):
            for jj in range(ii + 1, len(zs)):
                za, zb = zs[ii], zs[jj]
                if abs(za - zb) < 0.05 - 1e-12:
                    continue
                for ra, ca in self.by_z[za].items():
                    for rb, cb in self.by_z[zb].items():
                        if not _chain_bbox_close(ca, cb, 0.2):
                            continue
                        dz = abs(za - zb)
                        if dz * dz >= 0.05 * 0.05 and best[0] <= 0.05:
                            continue
                        for x in ca['curves']:
                            for y in cb['curves']:
                                if not _bbox_close(x['bbox'], y['bbox'], 0.2):
                                    continue
                                value = math.hypot(
                                    IM.prim_prim_distance(x, y), dz)
                                if value < best[0]:
                                    best = (value, dict(za=za, zb=zb,
                                                        route_a=ra, route_b=rb))
                                if value < LIMIT_3D:
                                    issues.append(dict(
                                        kind='3d_flat_flat', z_a=za, z_b=zb,
                                        route_a=ra, route_b=rb,
                                        distance_mm=value))
        minima['flat_flat_mm'] = best[0] if best[0] < float('inf') else None
        # (2) transition vs flat
        best = (float('inf'), None)
        seen = set()
        for rid, pid, tr, fp in self.transitions:
            box = _transition_bbox(tr, pad=0.25)
            for z in self.heights:
                if not (tr.z_min - 0.05 - 1e-9 <= z <= tr.z_max + 0.05 + 1e-9):
                    continue
                table = self.grid.get(z)
                if not table:
                    continue
                for (ix, iy) in _cells(box, 0.0):
                    for other, index in table.get((ix, iy), ()):
                        key = (rid, pid, other, index, z)
                        if other == rid or key in seen:
                            continue
                        seen.add(key)
                        curve = self.by_z[z][other]['curves'][index]
                        if not _bbox_close(box, curve['bbox'], 0.2):
                            continue
                        value, point = transition_flat_min(tr, curve)
                        if value < best[0]:
                            best = (value, dict(route=rid, part=pid,
                                                other=other, z=z))
                        if value < LIMIT_3D:
                            issues.append(dict(kind='3d_transition_flat',
                                               route_a=rid, route_b=other,
                                               z=z, distance_mm=value))
        minima['transition_flat_mm'] = best[0] if best[0] < float('inf') else None
        # (3) transition vs transition
        best = (float('inf'), None)
        for i in range(len(self.transitions)):
            rid, pid, tr, fp = self.transitions[i]
            box = _transition_bbox(tr, pad=0.25)
            for j in range(i + 1, len(self.transitions)):
                rb, pb, trb, fpb = self.transitions[j]
                if rid == rb:
                    continue
                if not _bbox_close(box, _transition_bbox(trb, 0.0), 0.2):
                    continue
                value, point = transition_transition_min(tr, trb)
                if value < best[0]:
                    best = (value, dict(route_a=rid, route_b=rb,
                                        part_a=pid, part_b=pb))
                if value < LIMIT_3D:
                    issues.append(dict(kind='3d_transition_transition',
                                       route_a=rid, route_b=rb,
                                       distance_mm=value))
        minima['transition_transition_mm'] = (best[0]
                                              if best[0] < float('inf') else None)
        if log:
            log('[3d] %s issues=%d' % (minima, len(issues)))
        return dict(issues=issues, minima=minima)

    # --------------------------------------------------- single-route evaluation
    def route_issues(self, rid, route=None, region=None, min_angle_deg=None,
                     include_3d=True, include_self=False, window_check=False):
        """Every legality issue of one route against the rest of the world.

        ``region`` (x0, y0, x1, y1) limits the audit to the primitives inside
        that XY box (plus pad).  Returns a dict with ``issues`` and
        ``crossings`` (the crossings the route participates in, for scoring).
        """
        rid = int(rid)
        route = route if route is not None else self.routes[rid]
        chain = RouteChain(route)
        min_angle = (self.min_angle_deg if min_angle_deg is None
                     else float(min_angle_deg))
        issues = []
        crossings = []
        partners = set()
        if region is None:
            for z in chain.z_order:
                partners |= self.neighbours_at_z(rid, z, chain.curves_at(z))
        else:
            pad_region = (region[0] - GRID_PAD_MM, region[1] - GRID_PAD_MM,
                          region[2] + GRID_PAD_MM, region[3] + GRID_PAD_MM)
            for z in chain.z_order:
                curves = [c for c in chain.curves_at(z)
                          if _bbox_intersects(c['bbox'], pad_region)]
                if curves:
                    partners |= self.neighbours_at_z(rid, z, curves)
        for other in sorted(partners):
            other_chain = self.chains[other]
            shared = [z for z in chain.z_order if z in other_chain.by_z]
            for z in shared:
                if region is not None:
                    own = chain.by_z[z]
                    sub = [c for c in own['curves']
                           if _bbox_intersects(c['bbox'], region)]
                    if not sub:
                        continue
                result = pair_audit(chain.by_z[z], other_chain.by_z[z], z,
                                    min_angle,
                                    crossing_window_check=window_check)
                for event in result['crossings']:
                    event.update(route_a=rid, route_b=other)
                    crossings.append(event)
                for issue in result['issues']:
                    issue.update(route_a=rid, route_b=other)
                    issues.append(issue)
        if include_3d:
            issues.extend(self._route_3d_issues(rid, chain, region))
        if include_self:
            issues.extend(self_clearance(chain, rid))
        return dict(issues=issues, crossings=crossings)

    def _route_3d_issues(self, rid, chain, region):
        issues = []
        rid = int(rid)
        # (a) own transitions vs other routes' flats
        for item in chain.transitions:
            tr = item['transition']
            box = _transition_bbox(tr, pad=0.25)
            seen = set()
            for z in self.heights:
                if z < tr.z_min - 0.05 - 1e-9 or z > tr.z_max + 0.05 + 1e-9:
                    continue
                table = self.grid.get(z)
                if not table:
                    continue
                x0 = int(math.floor(box[0] / GRID_CELL_MM))
                x1 = int(math.floor(box[2] / GRID_CELL_MM))
                y0 = int(math.floor(box[1] / GRID_CELL_MM))
                y1 = int(math.floor(box[3] / GRID_CELL_MM))
                for ix in range(x0, x1 + 1):
                    for iy in range(y0, y1 + 1):
                        for other, index in table.get((ix, iy), ()):
                            if other == rid or (other, z, index) in seen:
                                continue
                            seen.add((other, z, index))
                            curve = self.by_z[z][other]['curves'][index]
                            if not _bbox_close(box, curve['bbox'], 0.2):
                                continue
                            if not (tr.z_min - 0.05 - 1e-9 <= curve['z']
                                    <= tr.z_max + 0.05 + 1e-9):
                                continue
                            value, point = transition_flat_min(tr, curve)
                            if value < LIMIT_3D + CREATE_MARGIN_3D:
                                issues.append(dict(
                                    kind='3d_transition_flat', rid=rid,
                                    other=other, z=curve['z'],
                                    part_index=item['part_index'],
                                    distance_mm=value,
                                    point=[round(p, 6) for p in point]))
        # (b) own flats vs other routes' transitions
        for z in chain.z_order:
            for curve in chain.curves_at(z):
                if region is not None and not _bbox_intersects(curve['bbox'], region):
                    continue
                for entry in self.transitions_near(z, curve['bbox']):
                    other, part_index, tr, _footprint = entry
                    if other == rid:
                        continue
                    if not (tr.z_min - 0.05 - 1e-9 <= curve['z']
                            <= tr.z_max + 0.05 + 1e-9):
                        continue
                    if not _bbox_close(_transition_bbox(tr, 0.25), curve['bbox'], 0.2):
                        continue
                    value, point = transition_flat_min(tr, curve)
                    if value < LIMIT_3D + CREATE_MARGIN_3D:
                        issues.append(dict(
                            kind='3d_flat_transition', rid=rid, other=other,
                            z=z, other_part_index=part_index,
                            distance_mm=value,
                            point=[round(p, 6) for p in point]))
        # (c) own transitions vs other transitions
        for item in chain.transitions:
            tr = item['transition']
            box = _transition_bbox(tr, pad=0.25)
            seen = set()
            for z in self.heights:
                if z < tr.z_min - 0.05 - 1e-9 or z > tr.z_max + 0.05 + 1e-9:
                    continue
                for entry in self.transitions_near(z, box):
                    other, part_index, trb, _fp = entry
                    if other == rid or (other, part_index) in seen:
                        continue
                    seen.add((other, part_index))
                    if tr.z_max < trb.z_min - 0.05 or trb.z_max < tr.z_min - 0.05:
                        continue
                    if not _bbox_close(box, _transition_bbox(trb, 0.0), 0.2):
                        continue
                    value, point = transition_transition_min(tr, trb)
                    if value < LIMIT_3D + CREATE_MARGIN_3D:
                        issues.append(dict(
                            kind='3d_transition_transition', rid=rid,
                            other=other, part_index=item['part_index'],
                            other_part_index=part_index,
                            distance_mm=value,
                            point=[round(p, 6) for p in point]))
        return issues


def _cells(box, pad=0.0):
    x0 = int(math.floor((box[0] - pad) / GRID_CELL_MM))
    x1 = int(math.floor((box[2] + pad) / GRID_CELL_MM))
    y0 = int(math.floor((box[1] - pad) / GRID_CELL_MM))
    y1 = int(math.floor((box[3] + pad) / GRID_CELL_MM))
    return [(ix, iy) for ix in range(x0, x1 + 1) for iy in range(y0, y1 + 1)]


def _transition_bbox(tr, pad=0.0):
    x0, y0 = tr.start
    x1 = x0 + tr.direction[0] * tr.footprint
    y1 = y0 + tr.direction[1] * tr.footprint
    return (min(x0, x1) - pad, min(y0, y1) - pad,
            max(x0, x1) + pad, max(y0, y1) + pad)


def _chain_bbox_close(chain_a, chain_b, pad):
    ba = _chain_bbox(chain_a)
    bb = _chain_bbox(chain_b)
    return _bbox_close(ba, bb, pad)


def _chain_bbox(chain):
    xs = []
    ys = []
    for curve in chain['curves']:
        box = curve['bbox']
        xs.extend([box[0], box[2]])
        ys.extend([box[1], box[3]])
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))


def _bbox_intersects(a, b):
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


# ===========================================================================
# self clearance
# ===========================================================================
def self_clearance(chain, rid=None, step_flat=0.25, step_tr=0.05,
                   min_s_separation=1.0):
    """Route vs itself, excluding |ds| <= 1 mm (same convention as the audit)."""
    import numpy as np
    points = []
    lengths = []
    total = 0.0
    for _pid, z, curves in chain.flat_parts:
        for curve in curves:
            count = max(2, int(math.ceil(curve['length'] / step_flat)) + 1)
            for index in range(count + 1):
                t = index / count
                point = IM.prim_point(curve, t)
                if points:
                    total += math.hypot(point[0] - points[-1][0],
                                        point[1] - points[-1][1])
                points.append((point[0], point[1], z))
                lengths.append(total)
    for item in chain.transitions:
        tr = item['transition']
        count = max(3, int(math.ceil(tr.length / step_tr)) + 1)
        for index in range(count + 1):
            point = tr.point(tr.length * index / count)
            if points:
                total += math.hypot(point[0] - points[-1][0],
                                    point[1] - points[-1][1])
            points.append(point)
            lengths.append(total)
    issues = []
    if len(points) < 2:
        return issues
    import scipy.spatial as spatial
    array = np.asarray(points, dtype=float)
    lengths_array = np.asarray(lengths, dtype=float)
    tree = spatial.cKDTree(array)
    neighbours = tree.query_ball_point(array, r=1.0, workers=-1)
    worst = float('inf')
    for index, items in enumerate(neighbours):
        for other in items:
            if other <= index:
                continue
            if abs(lengths_array[index] - lengths_array[other]) <= min_s_separation:
                continue
            distance = float(np.linalg.norm(array[index] - array[other]))
            if distance < worst:
                worst = distance
            if distance < LIMIT_3D:
                issues.append(dict(kind='self_clearance', rid=rid,
                                   distance_mm=distance,
                                   point=[round(v, 6) for v in array[index]]))
    return issues


# ===========================================================================
# structural checks
# ===========================================================================
def structure_issues(route):
    """Heights / R15 / continuity / glass / metadata of one route."""
    issues = []
    heights = set(round(z, 9) for z in all_heights())
    parts = route.get('parts') or []
    if not parts:
        return [dict(kind='empty_route')]
    for index, part in enumerate(parts):
        if part['kind'] == 'flat':
            z = round(float(part['z_mm']), 9)
            if z not in heights:
                issues.append(dict(kind='flat_height', index=index, z=z))
            for prim in part.get('primitives') or ():
                if prim['kind'] == 'arc':
                    if abs(float(prim['radius']) - R15_MM) > 1e-6:
                        issues.append(dict(kind='arc_radius', index=index,
                                           radius=prim['radius']))
                elif prim['kind'] != 'line':
                    issues.append(dict(kind='prim_kind', index=index,
                                       got=prim['kind']))
        elif part['kind'] == 'transition':
            if abs(float(part.get('radius_mm') or 0.0) - R15_MM) > 1e-6:
                issues.append(dict(kind='transition_radius', index=index))
            if plane_of_z(part['z0']) is None or plane_of_z(part['z1']) is None:
                issues.append(dict(kind='transition_height', index=index))
        else:
            issues.append(dict(kind='part_kind', index=index,
                               got=part.get('kind')))
    # continuity
    for index in range(len(parts) - 1):
        first, second = parts[index], parts[index + 1]
        if first['kind'] == 'flat' and second['kind'] == 'transition':
            prims = first['primitives']
            if not prims:
                issues.append(dict(kind='empty_flat', index=index))
                continue
            end = IM.prim_point(make_prim(prims[-1]), 1.0)
            if math.dist(end, second['start']) > 1e-6:
                issues.append(dict(kind='position_flat_transition', index=index))
            tangent = IM.prim_tangent(make_prim(prims[-1]), 1.0)
            if _direction_error(tangent, second['direction']) > 1e-6:
                issues.append(dict(kind='tangent_flat_transition', index=index))
        elif first['kind'] == 'transition' and second['kind'] == 'flat':
            prims = second['primitives']
            if not prims:
                issues.append(dict(kind='empty_flat', index=index))
                continue
            start = IM.prim_point(make_prim(prims[0]), 0.0)
            if math.dist(start, first['end']) > 1e-6:
                issues.append(dict(kind='position_transition_flat', index=index))
            tangent = IM.prim_tangent(make_prim(prims[0]), 0.0)
            if _direction_error(first['direction'], tangent) > 1e-6:
                issues.append(dict(kind='tangent_transition_flat', index=index))
        elif first['kind'] == 'flat' and second['kind'] == 'flat':
            if math.dist(IM.prim_point(make_prim(first['primitives'][-1]), 1.0),
                         IM.prim_point(make_prim(second['primitives'][0]), 0.0)) > 1e-6:
                issues.append(dict(kind='position_flat_flat', index=index))
    # glass envelope on flat primitives
    for index, part in enumerate(parts):
        if part['kind'] != 'flat':
            continue
        for prim in part.get('primitives') or ():
            box = make_prim(prim)['bbox']
            if (box[0] < -1e-9 or box[1] < -1e-9
                    or box[2] > GLASS_XY_MM + 1e-9 or box[3] > GLASS_XY_MM + 1e-9):
                issues.append(dict(kind='glass_xy', index=index))
        z = float(part['z_mm'])
        if z < GLASS_Z_MIN_MM - 1e-9 or z > GLASS_Z_MAX_MM + 1e-9:
            issues.append(dict(kind='glass_z', index=index, z=z))
    return issues


def _direction_error(first, second):
    dot = float(first[0]) * float(second[0]) + float(first[1]) * float(second[1])
    return abs(1.0 - max(-1.0, min(1.0, dot)))
