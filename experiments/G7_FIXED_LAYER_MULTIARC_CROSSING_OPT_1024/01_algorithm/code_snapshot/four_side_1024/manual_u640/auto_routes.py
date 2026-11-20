# -*- coding: utf-8 -*-
"""Automatic routing of the 356 remaining connections from L7 upwards.

Final Lead-integrated implementation (replaces the earlier in-progress version;
the engine adapter ideas and the port-anchored lift come from that round).

Strategy
--------
1. **2D stage (existing engine)**: every automatic connection is routed on its
   assigned plane with the project's existing sequential router
   (:class:`four_side_1024.fslw.search.Router` + the frozen candidate families in
   :mod:`four_side_1024.fslw.candidates` + the exact strict
   :class:`four_side_1024.d56.index.D56Index`).  The 2D stage uses a *tighter*
   centre-line clearance than the physical 0.08 mm requirement
   (``ROUTING_CLEARANCE_MM = 0.10``) because the true-3D clearance world only
   certifies point-sampled distances down to 0.091 mm; this is a tightening, never
   a relaxation.  One routing layer per topology group (NS -> L7, EW -> L8,
   adjacent -> L9); the layer count is the number of groups actually used.
2. **Port-anchored lift**: each 2D chain is lifted from its interface row height
   (z1 = 0.0 mm / z2 = 0.5 mm) to its routing layer with two exact R = 15 mm
   elevation S-curves.  The first S-curve starts a small port margin after the
   port and the second ends a small port margin before the target, so the flat
   part on the interface plane is only a short lead-in and the route really is
   routed on its assigned layer.
3. **Sequential true-3D placement**: routes are lifted into the
   :class:`four_side_1024.l3d.world.World` one by one, with the manual L1-L6
   routes loaded as fixed obstacles.  For each route a small ladder of port
   margins is searched until both S-curves are clear of every obstacle: the port
   margin shifts the height at which an S-curve crosses the lower planes and
   therefore resolves the corner crossings between perpendicular groups.  A route
   with no legal S-curve placement is reported as failed with a structured
   reason; nothing is silently dropped and no clearance, radius, crossing-angle or
   bend constraint is ever relaxed.
"""
from __future__ import annotations

import json
import time
from collections import Counter, OrderedDict
from pathlib import Path

from four_side_1024.r15 import profile_r15

profile_r15.apply()          # R = 15 mm before the engine modules bind constants

from four_side_1024.d56.frames import build_frames
from four_side_1024.fslw import candidates as FSLW_CANDIDATES  # noqa: F401
from four_side_1024.fslw import config as FSLW_CFG
from four_side_1024.fslw import search as FSLW_SEARCH
from four_side_1024.fsd25d import path3d as P3
from four_side_1024.l3d import paths as L3D

from . import config as C
from . import paths2d as P

#: 2D centre-line clearance used by the placement stage. The physical requirement
#: is 0.08 mm; the 3D clearance world certifies segment distances down to
#: 0.081 mm and point-sampled distances down to 0.091 mm, so 0.10 mm is used.
ROUTING_CLEARANCE_MM = 0.10
ROUTING_EDGE_GAP_MM = round(ROUTING_CLEARANCE_MM - C.WIDTH_MM, 6)

#: One routing layer per topology group (automatic layer allocation).
DEFAULT_LAYER_PLAN = OrderedDict([
    ('z1_opposite_NS', 7),
    ('z1_opposite_EW', 8),
    ('z2_adjacent', 9),
])
AUTO_GROUP_ORDER = tuple(DEFAULT_LAYER_PLAN)

#: Port-margin ladder (mm): flat length between each port and its elevation
#: S-curve. The first entry is preferred; the rest resolve 3D conflicts by moving
#: the height at which the S-curve crosses the lower routing planes.
PORT_MARGIN_LADDER = (
    (1.2, 1.2), (0.2, 0.2), (2.0, 2.0), (3.0, 3.0), (4.0, 4.0), (5.0, 5.0),
    (6.0, 6.0), (8.0, 8.0),
    (0.2, 1.2), (1.2, 0.2), (2.0, 1.2), (1.2, 2.0), (3.0, 1.2), (1.2, 3.0),
    (4.0, 1.2), (1.2, 4.0), (5.0, 1.2), (1.2, 5.0), (6.0, 1.2), (1.2, 6.0),
    (8.0, 1.2), (1.2, 8.0), (8.0, 0.2), (0.2, 8.0),
)

SEGMENT_MARGIN_MM = 0.05

#: Layout acceptance policy: the interface-plane lead-in of one end must stay
#: short (a port lead-in, not routing on L1) and the assigned layer must carry the
#: bulk of the route.
MAX_INTERFACE_LEAD_IN_MM = 8.0
MIN_TARGET_LAYER_FRACTION = 0.80


# ---------------------------------------------------------------------------
# engine adapters
# ---------------------------------------------------------------------------
def endpoint_records(records):
    """``{endpoint_id: endpoint}`` for :func:`d56.frames.build_frames`."""
    endpoints = {}
    for record in records:
        for which in ('source', 'target'):
            endpoint = record[f'{which}_endpoint']
            endpoints[record[f'{which}_endpoint_id']] = dict(
                side=endpoint['side'], routing_xy=list(endpoint['xy']),
                inward=list(endpoint['inward']))
    return endpoints


def routing_route(record):
    """Engine-facing route record (unique integer id + endpoint identities)."""
    return dict(route_id=int(record['internal_id']), uid=record['uid'],
                source_endpoint=record['source_endpoint_id'],
                target_endpoint=record['target_endpoint_id'],
                relation=record['relation'],
                pair=f"{record['source_side']}{record['target_side']}")


def engine_config(candidate_budget=None):
    cfg = dict(FSLW_SEARCH.DEFAULT_CFG)
    cfg.update(width=C.WIDTH_MM, gap=ROUTING_EDGE_GAP_MM,
               sagitta=C.SAGITTA_MM, min_radius_mm=C.RADIUS_MM,
               min_cross_angle_deg=C.MIN_CROSS_ANGLE_DEG,
               crossing_policy='strict')
    if candidate_budget:
        cfg['candidate_budget_per_route'] = int(candidate_budget)
    return cfg


class _ClearanceEnvironment:
    """Tighten ``fslw.config`` while the existing engine generates candidates."""

    def __enter__(self):
        self.saved = (FSLW_CFG.CLEARANCE_MM, FSLW_CFG.EDGE_GAP_MM)
        FSLW_CFG.CLEARANCE_MM = float(ROUTING_CLEARANCE_MM)
        FSLW_CFG.EDGE_GAP_MM = float(ROUTING_EDGE_GAP_MM)

    def __exit__(self, *exc_info):
        FSLW_CFG.CLEARANCE_MM, FSLW_CFG.EDGE_GAP_MM = self.saved
        return False


# ---------------------------------------------------------------------------
# 2D stage
# ---------------------------------------------------------------------------
class GroupRouting:
    """2D routing state of one topology group (frames + accepted paths)."""

    def __init__(self, group, records, layer, log=print):
        self.group = str(group)
        self.layer = int(layer)
        self.records = list(records)
        self.by_internal = {int(record['internal_id']): record
                            for record in self.records}
        self.routes = [routing_route(record) for record in self.records]
        self.frames = build_frames(self.routes, endpoint_records(self.records))
        self.cfg = engine_config()
        self.router = FSLW_SEARCH.Router(self.frames, self.routes,
                                         cfg=self.cfg, log=lambda *a: None)
        self.accepted = OrderedDict()
        self.failures = {}
        self.info = {}
        self.log = log


    def _order(self, rids, mode):
        """Deterministic route order for the sequential engine."""
        frames = self.frames

        def chord(rid):
            frame = frames[rid]
            dx = frame.q[0] - frame.p[0]
            dy = frame.q[1] - frame.p[1]
            return (dx * dx + dy * dy) ** 0.5

        keys = {
            'x_desc': lambda rid: (-frames[rid].p[0], rid),
            'x_asc': lambda rid: (frames[rid].p[0], rid),
            'chord_desc': lambda rid: (-chord(rid), rid),
            'chord_asc': lambda rid: (chord(rid), rid),
            'csv': lambda rid: (rid,),
        }
        return sorted(rids, key=keys[mode])

    def route(self):
        started = time.perf_counter()
        with _ClearanceEnvironment():
            for attempt, strategy_name in enumerate(
                    ('x_desc', 'endpoint_order', 'shortest_first', 'y_desc')):
                remaining = [rid for rid in self.frames
                             if rid not in self.router.accepted]
                if not remaining:
                    break
                if attempt:
                    self.router.ripup(max_rounds=2)
                    remaining = [rid for rid in self.frames
                                 if rid not in self.router.accepted]
                order = self._order(remaining, strategy_name)
                for rid in order:
                    self.router._try_place(rid)
            removed = self.router.final_audit()
        self.accepted = OrderedDict(
            (int(rid), dict(primitives=list(result.primitives),
                            family=result.family,
                            prepared=result.prepared))
            for rid, result in self.router.accepted.items())
        self.failures = {int(rid): failure
                         for rid, failure in self.router.failed.items()}
        self.info = dict(
            group=self.group, layer=self.layer, attempted=len(self.routes),
            accepted=len(self.accepted), failed=len(self.failures),
            evaluations=int(self.router.index.evaluations),
            final_audit_removed=len(removed),
            duration_seconds=round(time.perf_counter() - started, 3),
            failure_reasons=dict(Counter(
                failure.get('reason') for failure in self.failures.values())))
        self.log(f'[auto] 2D {self.group} on L{self.layer}: '
                 f'{len(self.accepted)}/{len(self.routes)} accepted in '
                 f'{self.info["duration_seconds"]}s '
                 f'(evals={self.info["evaluations"]})')
        return self


# ---------------------------------------------------------------------------
# lift with independent rise / fall port margins
# ---------------------------------------------------------------------------
def _clean(primitives):
    return [P3.clean_primitive(prim) for prim in primitives]


def straight_windows(primitives, footprint):
    prims = _clean(primitives)
    total = float(P3.path_length(prims))
    windows = L3D._straight_windows(prims, footprint, SEGMENT_MARGIN_MM, total)
    return prims, total, windows


def lift_metrics(primitives, layer, plane):
    """Cheap liftability metrics of one 2D chain."""
    z0 = float(C.PLANE_Z_MM[plane])
    z1 = float(C.layer_z(layer))
    footprint = float(L3D.transition_geometry(z1 - z0, C.RADIUS_MM)['footprint_mm'])
    prims, total, windows = straight_windows(primitives, footprint)
    first = float(P3.path_length([prims[0]])) if prims and prims[0]['kind'] == 'line' else 0.0
    last = float(P3.path_length([prims[-1]])) if prims and prims[-1]['kind'] == 'line' else 0.0
    return dict(footprint_mm=footprint, total_mm=total, windows=windows,
                prims=prims, first_straight_mm=first, last_straight_mm=last)


def _identity(record):
    return dict(
        uid=record['uid'], original_route_id=int(record['original_route_id']),
        dataset=record['dataset'], relation=record['relation'],
        source_side=record['source_side'], target_side=record['target_side'],
        source_port_id=record['source_port_id'],
        target_port_id=record['target_port_id'],
        source_endpoint_id=record['source_endpoint_id'],
        target_endpoint_id=record['target_endpoint_id'],
        source_xy_mm=list(record['source_xy']),
        target_xy_mm=list(record['target_xy']),
        source_z_mm=float(record['source_z_mm']),
        target_z_mm=float(record['target_z_mm']),
        assignment=record['assignment'], manual_group=record['manual_group'],
        manual_group_order=record['manual_group_order'],
        csv_assigned_layer=record['assigned_layer_csv'],
    )


def build_anchored_lift(record, primitives, layer, rise=1.2, fall=1.2):
    """Assemble one ``[L1, Lk, L1]`` route with explicit port margins."""
    plane = record['dataset']
    z0 = float(C.PLANE_Z_MM[plane])
    if int(layer) == C.INTERFACE_LAYER_ID:
        return P.build_flat_route(record, primitives)
    z1 = float(C.layer_z(layer))
    footprint = float(L3D.transition_geometry(z1 - z0, C.RADIUS_MM)['footprint_mm'])
    prims, total, windows = straight_windows(primitives, footprint)
    starts = [float(rise), float(total) - float(fall) - footprint]
    if starts[1] - starts[0] < footprint + 0.05:
        return None
    for start in starts:
        if not any(lo - 1e-9 <= start <= hi + 1e-9 for lo, hi in windows):
            return None
    heights = [z0, z1, z0]
    parts = []
    previous_end = 0.0
    for index, start_s in enumerate(starts):
        end_s = start_s + footprint
        flat = L3D._subchain(prims, previous_end, start_s)
        flat_length = float(P3.path_length(flat))
        if flat_length > 1e-12:
            flat_layer = (C.INTERFACE_LAYER_ID if abs(heights[index] - z0) < 1e-9
                          else int(layer))
            parts.append(dict(kind='flat', layer_id=flat_layer,
                              z_mm=heights[index], length_mm=flat_length,
                              primitives=flat))
        point, direction = P3.path_point_at(prims, start_s)
        transition = dict(P3.make_transition(point, direction, heights[index],
                                            heights[index + 1], C.RADIUS_MM))
        transition['from_layer'] = (C.INTERFACE_LAYER_ID if index == 0
                                    else int(layer))
        transition['to_layer'] = (int(layer) if index == 0
                                  else C.INTERFACE_LAYER_ID)
        parts.append(transition)
        previous_end = end_s
    tail = L3D._subchain(prims, previous_end, total)
    tail_length = float(P3.path_length(tail))
    if tail_length > 1e-12:
        parts.append(dict(kind='flat', layer_id=C.INTERFACE_LAYER_ID,
                          z_mm=heights[-1], length_mm=tail_length,
                          primitives=tail))

    if not parts or parts[0]['kind'] != 'flat' or parts[-1]['kind'] != 'flat':
        return None
    length = float(sum(part['length_mm'] for part in parts))
    route = dict(_identity(record))
    route.update(
        route_id=int(record['internal_id']), plane=plane,
        source_row=int(record['source_row']),
        target_row=int(record['target_row']),
        source_port=dict(xy=list(record['source_xy']), z_mm=z0,
                         layer_id=C.INTERFACE_LAYER_ID),
        target_port=dict(xy=list(record['target_xy']), z_mm=z0,
                         layer_id=C.INTERFACE_LAYER_ID),
        start_z_mm=z0, end_z_mm=z0,
        layer_sequence=[C.INTERFACE_LAYER_ID, int(layer), C.INTERFACE_LAYER_ID],
        layer_z_sequence=[z0, z1, z0], n_transitions=2, lifted=True,
        layers_used=[C.INTERFACE_LAYER_ID, int(layer)], xy_length_mm=total,
        length_mm=length, z_span_mm=z1 - z0, parts=parts,
        primitives_2d=[dict(prim) for prim in prims],
        min_bend_radius_mm=P.min_arc_radius(prims),
        bend_count=P.bend_count(prims), status='routed', failure_reason=None,
        logical_layer=int(layer), target_layer=int(layer),
        port_margin_used=dict(rise=float(rise), fall=float(fall)),
    )
    return route


def route_layout(route):
    """Layout metrics: interface-plane lead-ins and target-layer share."""
    parts = route.get('parts') or []
    if not parts:
        return dict(l1_prefix_mm=0.0, l1_suffix_mm=0.0, l1_flat_mm=0.0,
                    target_layer_flat_mm=0.0, target_layer_fraction=0.0,
                    total_length_mm=0.0, max_interface_lead_in_mm=0.0)
    z0 = float(route.get('start_z_mm') or 0.0)
    target_z = float(route.get('layer_z_sequence')[1])
    prefix = 0.0
    for part in parts:
        if part['kind'] == 'flat' and abs(part['z_mm'] - z0) < 1e-9:
            prefix += float(part['length_mm'])
        else:
            break
    suffix = 0.0
    for part in reversed(parts):
        if part['kind'] == 'flat' and abs(part['z_mm'] - z0) < 1e-9:
            suffix += float(part['length_mm'])
        else:
            break
    total = float(sum(part['length_mm'] for part in parts))
    target_flat = float(sum(part['length_mm'] for part in parts
                            if part['kind'] == 'flat'
                            and abs(part['z_mm'] - target_z) < 1e-9))
    return dict(
        l1_prefix_mm=round(prefix, 6), l1_suffix_mm=round(suffix, 6),
        l1_flat_mm=round(prefix + suffix, 6),
        max_interface_lead_in_mm=round(max(prefix, suffix), 6),
        target_layer_flat_mm=round(target_flat, 6),
        target_layer_fraction=round(target_flat / total, 6) if total else 0.0,
        total_length_mm=round(total, 6))


def layout_satisfies_policy(layout, max_lead_in=MAX_INTERFACE_LEAD_IN_MM,
                            min_fraction=MIN_TARGET_LAYER_FRACTION):
    return (layout['max_interface_lead_in_mm'] <= max_lead_in + 1e-9
            and layout['target_layer_fraction'] >= min_fraction - 1e-9)


# ---------------------------------------------------------------------------
# main entry
# ---------------------------------------------------------------------------
def build_auto_routes(data, stack=None, groups=None, log=print,
                      obstacle_routes=None, layer_plan=None,
                      port_margin_ladder=None, budget=None, repair=True,
                      audit=True, relocate_2d=False, relocate_budget=10):
    """Route the 356 automatic connections from L7 upwards.

    Parameters
    ----------
    data : inputs.InputData
    stack : stack.LayerStack
    groups : iterable of group keys (default: all automatic groups)
    obstacle_routes : list of already built route dicts (the manual L1-L6 routes)
        loaded into the true-3D world as fixed obstacles.
    layer_plan : ``{group: logical_layer}`` override of :data:`DEFAULT_LAYER_PLAN`.
    repair : run the second-chance / 2D-relocation stage.
    relocate_2d : allow re-placing a route's 2D candidate when no port-margin
        placement is legal (the engine's existing candidate list is reused).

    Returns
    -------
    (routes, failures, stats)
    """
    from . import assemble as ASSEMBLE

    if stack is None:
        from . import stack as stack_module
        stack = stack_module.LayerStack(C.MAX_LOGICAL_LAYERS)
    layer_plan = OrderedDict(DEFAULT_LAYER_PLAN if layer_plan is None
                             else layer_plan)
    selected_groups = ([group for group in AUTO_GROUP_ORDER
                        if group in data.auto_groups]
                       if groups is None else list(groups))
    ladder = tuple(port_margin_ladder or PORT_MARGIN_LADDER)
    started = time.perf_counter()

    # ------------------------------------------------------------- 2D stage
    log('[auto] === 2D stage: existing sequential engine '
        f'(routing clearance {ROUTING_CLEARANCE_MM} mm, physical '
        f'{C.CLEARANCE_MM} mm) ===')
    group_states = OrderedDict()
    for group in selected_groups:
        if group not in layer_plan:
            raise KeyError(f'no layer allocated for group {group}')
        state = GroupRouting(group, data.records_for(data.auto_groups[group]),
                             layer_plan[group], log=log).route()
        group_states[group] = state

    # --------------------------------------------------------- 3D placement
    log('[auto] === sequential true-3D placement '
        '(manual L1-L6 routes as fixed obstacles) ===')
    world = ASSEMBLE.build_world(stack)
    obstacles = list(obstacle_routes or [])
    for route in obstacles:
        violations = world.check_route(route)
        if violations:
            raise ValueError(f'obstacle route {route["uid"]} is not legal: '
                             f'{violations[:2]}')
        world.add_route(route)
    log(f'[auto] pre-loaded {len(obstacles)} obstacle route(s) into the 3D world')

    placed = OrderedDict()
    pending = []
    metrics = {}
    for group in selected_groups:
        state = group_states[group]
        layer = state.layer
        order = sorted(state.accepted)
        for rid in order:
            record = state.by_internal[rid]
            primitives = state.accepted[rid]['primitives']
            layout_info = lift_metrics(primitives, layer, record['dataset'])
            metrics[record['uid']] = dict(
                footprint_mm=round(layout_info['footprint_mm'], 6),
                first_straight_mm=round(layout_info['first_straight_mm'], 6),
                last_straight_mm=round(layout_info['last_straight_mm'], 6))
            chosen = _try_lift(record, primitives, layer, ladder, world)
            if chosen is None:
                pending.append((group, rid))
                continue
            _commit(chosen, group, layer, metrics[record['uid']], world, placed)
        log(f'[auto] L{layer} {group}: '
            f'{sum(1 for uid in placed if placed[uid]["auto_group"] == group)}'
            f'/{len(state.accepted)} placed')

    # ------------------------------------- second chance for the pending ones
    leftover = []
    if repair and pending:
        log(f'[auto] second chance for {len(pending)} pending route(s) '
            f'(relocate_2d={relocate_2d})')
        still_pending = []
        for group, rid in pending:
            state = group_states[group]
            record = state.by_internal[rid]
            layer = state.layer
            chosen = None
            if relocate_2d:
                chosen = _relocate_and_lift(state, rid, layer, ladder, world,
                                            budget=relocate_budget, log=log)
            if chosen is None:
                # last attempt with the original chain and the full ladder
                chosen = _try_lift(record, state.accepted[rid]['primitives'],
                                   layer, ladder, world)
            if chosen is None:
                still_pending.append((group, rid))
                continue
            _commit(chosen, group, layer, metrics.get(record['uid']), world,
                    placed)
        pending = still_pending

    # ------------------------- third chance: allocate an extra routing layer
    if repair and pending:
        log(f'[auto] third chance: extra layer allocation for '
            f'{len(pending)} pending route(s)')
        for group, rid in pending:
            state = group_states[group]
            record = state.by_internal[rid]
            primitives = state.accepted[rid]['primitives']
            chosen = None
            for layer in _extra_layer_candidates(state.layer, stack):
                candidate = _try_lift(record, primitives, layer, ladder, world)
                if candidate is None:
                    continue
                candidate['layer_reallocated_from'] = int(state.layer)
                chosen = candidate
                state.layer = layer          # future spills of this group reuse it
                break
            if chosen is None:
                leftover.append((group, rid,
                                 'no_legal_elevation_placement_against_3d_'
                                 'obstacles'))
                continue
            _commit(chosen, group, int(chosen['logical_layer']),
                    metrics.get(record['uid']), world, placed)
    else:
        for group, rid in pending:
            leftover.append((group, rid,
                             'no_legal_elevation_placement_against_3d_obstacles'))

    # ------------------------------------------------------------- failures
    failures = []
    for group, rid, reason in leftover:
        state = group_states[group]
        record = state.by_internal[rid]
        failed = P.failed_record(record, reason, logical_layer=state.layer)
        failed['auto_group'] = group
        state = group_states[group]
        diagnostics = {}
        primitives = state.accepted.get(int(record['internal_id']), {}).get('primitives')
        if primitives:
            for layer in _extra_layer_candidates(state.layer, stack)[:1] + [state.layer]:
                _try_lift(record, primitives, layer, ladder[:10], world,
                          diagnostics=diagnostics)
        failed['failure_detail'] = dict(
            group=group, lift=metrics.get(record['uid']),
            tried_layers=(_extra_layer_candidates(state.layer, stack)[:2]
                          + [state.layer]),
            rejection_counts=diagnostics,
            primitives_2d=[dict(prim) for prim in (primitives or [])],
            note=('the existing engine found a legal 2D path, but no elevation '
                  'S-curve placement is clear of the manual L1-L6 routes and the '
                  'already placed automatic routes'))
        failures.append(failed)
    for group in selected_groups:
        state = group_states[group]
        for rid, failure in state.failures.items():
            record = state.by_internal.get(int(rid))
            if record is None or record['uid'] in placed:
                continue
            failed = P.failed_record(
                record, f'2d_routing_failed:{failure.get("reason")}',
                logical_layer=state.layer)
            failed['auto_group'] = group
            failed['failure_detail'] = dict(
                group=group,
                rejection_counts=failure.get('rejection_counts'),
                blockers=failure.get('blockers'))
            failures.append(failed)

    # ------------------------------------------------------------- statistics
    routes = list(placed.values())
    layouts = [route['layout'] for route in routes]
    stats = dict(
        schema='four_side_1024_manual_u640_auto_routing_stats_v1',
        engine=dict(router='four_side_1024.fslw.search.Router',
                    candidates='four_side_1024.fslw.candidates',
                    index='four_side_1024.d56.index.D56Index',
                    radius_mm=C.RADIUS_MM,
                    routing_clearance_mm=ROUTING_CLEARANCE_MM,
                    physical_clearance_mm=C.CLEARANCE_MM,
                    candidate_budget=(budget or engine_config()[
                        'candidate_budget_per_route'])),
        layer_plan={group: int(layer_plan[group])
                    for group in selected_groups},
        layer_count=len({int(route['logical_layer']) for route in routes}),
        layers_used=sorted({int(route['logical_layer']) for route in routes}),
        groups={group: dict(records=len(data.auto_groups[group]),
                            routed=sum(1 for uid in placed
                                       if placed[uid]['auto_group'] == group),
                            failed=sum(1 for failure in failures
                                       if failure.get('auto_group') == group),
                            layer=int(layer_plan[group]),
                            routing_2d=group_states[group].info)
                for group in selected_groups},
        placed=len(routes), failed=len(failures),
        total=sum(len(data.auto_groups[group]) for group in selected_groups),
        layer_counts=dict(Counter(int(route['logical_layer'])
                                  for route in routes)),
        port_margin_usage={f'{rise:g}/{fall:g}': count for (rise, fall), count
                           in Counter((route['port_margin_used']['rise'],
                                       route['port_margin_used']['fall'])
                                      for route in routes).most_common(20)},
        interface_lead_in=dict(
            max_mm=max((layout['max_interface_lead_in_mm']
                        for layout in layouts), default=0.0),
            mean_mm=round(sum(layout['max_interface_lead_in_mm']
                              for layout in layouts) / len(layouts), 4)
            if layouts else 0.0,
            count_over_5mm=sum(1 for layout in layouts
                               if layout['max_interface_lead_in_mm'] > 5.0 + 1e-9)),
        target_layer_fraction=dict(
            min=min((layout['target_layer_fraction'] for layout in layouts),
                    default=0.0),
            mean=round(sum(layout['target_layer_fraction'] for layout in layouts)
                       / len(layouts), 4) if layouts else 0.0,
            count_below_0_8=sum(1 for layout in layouts
                                if layout['target_layer_fraction'] < 0.8)),
        failures=[dict(uid=failure['uid'], group=failure.get('auto_group'),
                       reason=failure.get('failure_reason'))
                  for failure in failures],
        world_audit=(_audit(routes, stack, obstacles, log=log) if audit else None),
        elapsed_s=round(time.perf_counter() - started, 2),
    )
    log(f'[auto] done: {len(routes)}/{stats["total"]} automatic routes placed, '
        f'{len(failures)} failed, layers {sorted(stats["layer_counts"])}, '
        f'{stats["elapsed_s"]}s')
    return routes, failures, stats


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------
def _try_lift(record, primitives, layer, ladder, world, diagnostics=None):
    diagnostics = diagnostics if diagnostics is not None else {}
    for rise, fall in ladder:
        candidate = build_anchored_lift(record, primitives, layer, rise, fall)
        if candidate is None:
            diagnostics['lift_infeasible'] = diagnostics.get('lift_infeasible', 0) + 1
            continue
        layout = route_layout(candidate)
        if not layout_satisfies_policy(layout):
            diagnostics['layout_policy'] = diagnostics.get('layout_policy', 0) + 1
            continue
        violations = world.check_route(candidate)
        if violations:
            for violation in violations:
                kind = violation.get('kind', 'unknown')
                diagnostics[kind] = diagnostics.get(kind, 0) + 1
            continue
        candidate['layout'] = layout
        return candidate
    return None


def _commit(route, group, layer, lift, world, placed):
    route['logical_layer'] = int(layer)
    route['target_layer'] = int(layer)
    route['auto_group'] = group
    route['layout'] = route.get('layout') or route_layout(route)
    route['lift'] = lift
    world.add_route(route)
    placed[route['uid']] = route


def _relocate_and_lift(state, rid, layer, ladder, world, budget=120, log=print):
    """Re-place one route's 2D chain with another existing-engine candidate.

    The engine's own candidate generator is reused; the candidate must be legal in
    the group's 2D index (the route's current entry is temporarily removed) and
    must admit a legal elevation placement in the true-3D world.
    """
    frame = state.frames.get(rid)
    if frame is None:
        return None
    record = state.by_internal[rid]
    router = state.router
    oracle = router.oracles.oracle_for(frame)
    prepared_old = state.accepted.get(rid, {}).get('prepared')
    router.index.remove(rid)
    router.oracles.remove(rid)
    chosen = None
    evaluated = 0
    liftable = 0
    z0 = float(C.PLANE_Z_MM[record['dataset']])
    footprint = float(L3D.transition_geometry(
        float(C.layer_z(layer)) - z0, C.RADIUS_MM)['footprint_mm'])
    required = footprint + 0.30
    try:
        with _ClearanceEnvironment():
            for deep in (False, True):
                for candidate in FSLW_CANDIDATES.candidates(
                        frame, oracle, router.cfg, deep=deep):
                    if evaluated >= budget:
                        break
                    evaluated += 1
                    primitives = frame.to_world(candidate['primitives'])
                    # cheap pre-filter: the lift needs a long straight at both ends
                    first = primitives[0]
                    last = primitives[-1]
                    if first.get('kind') != 'line' or last.get('kind') != 'line':
                        continue
                    first_len = float(((first['p1'][0] - first['p0'][0]) ** 2
                                       + (first['p1'][1] - first['p0'][1]) ** 2) ** 0.5)
                    last_len = float(((last['p1'][0] - last['p0'][0]) ** 2
                                      + (last['p1'][1] - last['p0'][1]) ** 2) ** 0.5)
                    if min(first_len, last_len) < required:
                        continue
                    liftable += 1
                    prepared = _prepare(primitives)
                    evaluation = router.index.evaluate(prepared)
                    if evaluation is None or not evaluation.valid:
                        continue
                    built = _try_lift(record, primitives, layer, ladder, world)
                    if built is not None:
                        chosen = built
                        chosen['relocated_2d'] = dict(
                            family=candidate['family'],
                            params=candidate['params'], evaluated=evaluated)
                        router.index.add(rid, prepared)
                        router.oracles.add(rid, prepared)
                        break
                if chosen is not None or evaluated >= budget:
                    break
    finally:
        if chosen is None:
            # restore the previous 2D placement so later routes see the same world
            if prepared_old is not None:
                router.index.add(rid, prepared_old)
                router.oracles.add(rid, prepared_old)
    if chosen is not None:
        new_prepared = _prepare(chosen['primitives_2d'])
        router.index.add(rid, new_prepared)
        router.oracles.add(rid, new_prepared)
        selected = state.accepted[rid]
        selected['primitives'] = list(chosen['primitives_2d'])
        selected['prepared'] = new_prepared
        selected['relocated'] = True
    return chosen



def _extra_layer_candidates(base_layer, stack):
    """Alternative routing layers tried when a route has no legal placement.

    Routes are lifted to a *fresh* higher layer (whose plane is still empty), which
    changes the elevation profile and therefore where the S-curves cross the lower
    planes.  This is the automatic layer-extension mechanism: the number of used
    layers grows only when a route cannot be placed on the planned layer.
    """
    base = int(base_layer)
    highest_planned = max(int(layer) for layer in DEFAULT_LAYER_PLAN.values())
    options = [highest_planned + 1, highest_planned + 2, highest_planned + 3,
               highest_planned + 4]
    options += [base + 1, base]
    seen = []
    for layer in options:
        if layer in seen:
            continue
        if not 2 <= layer <= int(getattr(stack, 'max_layer', C.MAX_LOGICAL_LAYERS)):
            continue
        seen.append(int(layer))
    return seen


def _prepare(primitives):
    from four_side_1024.d56.index import prepare
    return prepare(primitives)


def _audit(routes, stack, obstacles, log=print):
    """Re-audit the placed automatic routes in a fresh true-3D world.

    A route cannot be checked inside the world that already contains it, so the
    audit rebuilds the world from the obstacles and re-inserts every automatic
    route one by one, checking it against the routes inserted before it.
    """
    from . import assemble as ASSEMBLE
    world = ASSEMBLE.build_world(stack)
    for route in obstacles:
        world.add_route(route)
    violations = []
    for route in routes:
        found = world.check_route(route)
        if found:
            violations.append(dict(uid=route['uid'], violations=found[:3]))
            continue
        world.add_route(route)
    log(f'[auto] world audit: {len(routes) - len(violations)}/{len(routes)} clean')
    return dict(routes=len(routes), clean=len(routes) - len(violations),
                violation_count=len(violations), violations=violations[:50])


# ---------------------------------------------------------------------------
# CLI (development aid)
# ---------------------------------------------------------------------------
def build_parser():
    import argparse
    parser = argparse.ArgumentParser(description='automatic L7+ routing')
    parser.add_argument('--group', action='append', default=None)
    parser.add_argument('--json', default=None)
    parser.add_argument('--no-repair', action='store_true')
    return parser


def main(argv=None):
    from . import inputs
    args = build_parser().parse_args(argv)
    data = inputs.load_inputs()

    def log(message):
        print(message, flush=True)

    routes, failures, stats = build_auto_routes(
        data, log=log, groups=args.group, repair=not args.no_repair)
    print(json.dumps({key: value for key, value in stats.items()
                      if key != 'groups'}, indent=1, ensure_ascii=False,
                     default=str))
    if args.json:
        path = Path(args.json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict(stats=stats, routes=routes,
                                        failures=failures), ensure_ascii=False,
                                   default=str, indent=1), encoding='utf-8')
        print('written', path)
    return 0 if not failures else 1


if __name__ == '__main__':
    raise SystemExit(main())



