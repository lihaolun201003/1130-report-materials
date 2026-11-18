# -*- coding: utf-8 -*-
"""Local XY+Z rerouting: candidate generation, exact evaluation, transaction."""
from __future__ import annotations

import copy
import math
import time
from collections import Counter

from ...d56.index import prepare as d56_prepare
from .. import common as C
from .. import layer2d as L2
from ..native3d import common as N
from ..reheight21 import model as M
from . import route_builder as RB
from . import world_adapter as WA

DEFAULT_CFG = dict(
    max_target_layers=3,       # candidate target heights besides the current one
    max_lead_pairs=2,          # lead (source,target) pairs tried in the full pass
    prescreen_candidates=220,  # XY candidates built during the cheap pre-screen
    max_candidates=420,        # XY candidates built in the full evaluation pass
    d56_top=24,                # candidates that get the exact D56 evaluation
    bodies_per_pair=2,         # XY bodies kept per (layer, lead pair)
    max_eval=2,                # full 3D evaluations per (layer, lead pair)
    max_combos=2,              # (layer, lead pair) combos fully evaluated
    early_stop_delta=6,        # stop after the first combo when it gained this much
    min_delta=1,               # require at least this much crossing improvement
    allow_direct=True,         # allow converting to an interface-direct body
    allow_xy_only=True,        # allow same-height XY rerouting (fanout kept)
    phase=0.0,
)

#: reduced family ladders used only for the cheap pre-screen pass
PRESCREEN_CFG = dict(
    u_ladder_step=6.0,
    max_u_levels=24,
    opp_ladder_count=10,
    opp_detour_count=5,
    adj_ladder_count=8,
    adj_slot_count=4,
    max_candidates_built=900,
)


def plane_of_layer(layer_id):
    return float(RB.PLANE_Z[int(layer_id)])


# ---------------------------------------------------------------------------
# target layers
# ---------------------------------------------------------------------------
def target_options(state, route_id, cfg=None):
    cfg = dict(DEFAULT_CFG, **(cfg or {}))
    rid = int(route_id)
    row = state.row(rid)
    cur_layer = int(row['target_layer'])
    cur_z = float(row['target_z_mm'])
    interface = float(row['interface_z_mm'])
    direct = not bool(row.get('needs_transition'))
    counts = state.route_counts_by_plane()
    options = []
    ranked = []
    for pid in RB.BODY_PLANE_IDS:
        z = plane_of_layer(pid)
        if abs(z - cur_z) < 1e-9:
            continue
        load = int(counts.get(WA.plane_key(z), 0))
        ranked.append((load, abs(z - cur_z), int(pid), z))
    ranked.sort()
    for load, _dz, pid, z in ranked[:int(cfg['max_target_layers'])]:
        options.append(dict(kind='migrate', layer=int(pid), z=float(z),
                            load=load, priority=0))
    if cfg['allow_direct'] and not direct:
        # converting a lifted route into an interface-direct body is a genuine
        # XY-only alternative at the interface height (no S-curve at all)
        options.append(dict(kind='direct',
                            layer=int(RB.INTERFACE_PLANE[row['plane']]),
                            z=interface, load=0, priority=1))
    if cfg['allow_xy_only'] and not cfg.get('_ripped'):
        if cur_layer not in (1001, 1002):
            options.append(dict(kind='xy_only', layer=cur_layer, z=cur_z,
                                load=0, priority=2))
        else:
            options.append(dict(kind='direct_xy', layer=cur_layer, z=cur_z,
                                load=0, priority=2))
    return options


def _lead_pair_candidates(route, option, cfg):
    """Bounded lead-pair ladder of one option (first entry = baseline leads)."""
    lead_s, lead_t = RB.lead_lengths(route)
    pairs = []
    if option['kind'] in ('xy_only', 'direct_xy'):
        return [(lead_s, lead_t)]
    if lead_s > 0.0 and lead_t > 0.0:
        pairs.append((lead_s, lead_t))
    for lead in RB.LEAD_CANDIDATES:
        pair = (float(lead), float(lead))
        if any(abs(pair[0] - q[0]) < 1e-9 and abs(pair[1] - q[1]) < 1e-9
               for q in pairs):
            continue
        pairs.append(pair)
        if len(pairs) >= int(cfg['max_lead_pairs']):
            break
    return pairs[:max(1, int(cfg['max_lead_pairs']))]


# ---------------------------------------------------------------------------
# XY body candidates on one plane
# ---------------------------------------------------------------------------
def xy_candidates(state, route_id, task, layer_id, z_mm, cfg=None):
    """Cheap pre-ranked XY body candidates of one (route, height, lead pair).

    Phase 1 builds every candidate of the R15 family library and scores it with
    the O(1) geometric crossing pre-rank (``RouteWorld.fast_crossings``).
    Phase 2 runs the frozen strict D56 evaluation only on the cheapest
    ``d56_top`` candidates - the exact rule still decides legality / crossings.
    """
    cfg = dict(DEFAULT_CFG, **(cfg or {}))
    rid = int(route_id)
    z_key = WA.plane_key(z_mm)
    initial = state.plane_routes(z_key, exclude_route=rid)
    obstacles = state.obstacles_for_z(z_key)
    router_cfg = dict(L2.DEFAULT_CFG)
    router_cfg['enable_multi_arc'] = L2.multi_arc_enabled(cfg)
    if cfg.get('disabled_structures') is not None:
        # per-patent-structure ablation switch (layer2d geometric gate)
        router_cfg['disabled_structures'] = cfg['disabled_structures']
    if cfg.get('_prescreen'):
        router_cfg.update(PRESCREEN_CFG)
    router = L2._LayerRouter(int(layer_id), float(z_mm), [task], obstacles,
                             router_cfg, lambda *_a, **_k: None,
                             initial_routes=initial)
    scored = []
    count = 0
    for body, spec, signature in router._iter_candidates(rid, float(cfg['phase'])):
        count += 1
        if count > int(cfg['max_candidates']):
            break
        fast = state.fast_crossings(z_key, body, exclude_route=rid)
        scored.append((int(fast), len(scored), body,
                       str(spec.get('family') or ''),
                       dict(spec.get('params') or {})))
        if scored and scored[-1][0] == 0 and count >= 4 * int(cfg['d56_top']):
            break
    if not scored:
        return []
    scored.sort(key=lambda item: (item[0], item[1]))
    out = []
    for fast, _index, body, family, params in scored[:int(cfg['d56_top'])]:
        evaluation = router.index.evaluate(d56_prepare(body))
        if not evaluation.valid:
            continue
        ok, _blockers = router.obstacles.check(body, rid)
        if not ok:
            continue
        if not L2._self_clearance_ok(body):
            continue
        crossings = len(getattr(evaluation, 'crossings', ()) or ())
        out.append(dict(crossings=crossings, fast=fast, body=body,
                        family=family, params=params))
    out.sort(key=lambda item: (item['crossings'], item['fast'], item['family']))
    return out[:max(1, int(cfg['bodies_per_pair']))]


# ---------------------------------------------------------------------------
# route construction per option
# ---------------------------------------------------------------------------
def make_task_for_option(state, route_id, option, lead_s, lead_t):
    rid = int(route_id)
    row = state.row(rid)
    if option['kind'] in ('direct', 'direct_xy'):
        task = RB.direct_task(row)
        return task, None, None
    task, source, target = RB.body_task(row, int(option['layer']),
                                        float(option['z']), lead_s, lead_t)
    return task, source, target


def build_route_candidate(state, route_id, option, lead_s, lead_t, body):
    rid = int(route_id)
    row = state.row(rid)
    route = state.route(rid)
    kind = option['kind']
    if kind in ('xy_only', 'direct_xy'):
        if kind == 'direct_xy':
            return RB.build_direct(row, body)
        indices = RB.body_part_indices(route)
        if len(indices) == 1:
            return RB.replace_body_keep_fanout(route, row, indices[0], body)
        return RB.build_lifted(row, int(option['layer']), float(option['z']),
                               lead_s, lead_t, body)
    if kind == 'direct':
        return RB.build_direct(row, body)
    return RB.build_lifted(row, int(option['layer']), float(option['z']),
                           float(lead_s), float(lead_t), body)


# ---------------------------------------------------------------------------
# one-route proposal (two-phase: cheap pre-screen, then exact evaluation)
# ---------------------------------------------------------------------------
def propose(state, route_id, cfg=None, stats=None):
    """Return the best exact candidate of one route (not applied)."""
    cfg = dict(DEFAULT_CFG, **(cfg or {}))
    rid = int(route_id)
    stats = stats if isinstance(stats, dict) else {}
    for key in ('targets', 'xy_generated', 'built', 'rejected_3d', 'evaluated',
                'combos_pre', 'combos_eval'):
        stats.setdefault(key, 0)
    reasons = stats.setdefault('reasons', Counter())
    started = time.time()
    old_groups = state.groups(rid)
    override = cfg.get('old_events_override')
    if override is not None:
        old_events = int(override)
    else:
        old_events = sum(state.route_plane_events(rid, z) for z in old_groups)
        if old_events <= 0 or not old_groups:
            reasons['no_current_crossings'] += 1
            return None
    # ---- phase 1: cheap pre-screen of every target option -------------------
    pre_cfg = dict(cfg)
    pre_cfg['max_candidates'] = int(cfg['prescreen_candidates'])
    pre_cfg['bodies_per_pair'] = 2
    pre_cfg['_prescreen'] = True
    pre_cfg['max_lead_pairs'] = 1
    plans = []
    for option in target_options(state, rid, cfg):
        stats['targets'] += 1
        lead_s, lead_t = _lead_pair_candidates(state.route(rid), option, cfg)[0]
        try:
            task, _src, _tgt = make_task_for_option(state, rid, option,
                                                    lead_s, lead_t)
        except (RB.BuilderError, ValueError) as error:
            reasons[getattr(error, 'reason', 'builder_value_error')] += 1
            continue
        bodies = xy_candidates(state, rid, task, int(option['layer']),
                               float(option['z']), pre_cfg)
        stats['xy_generated'] += len(bodies)
        stats['combos_pre'] += 1
        if not bodies:
            reasons['no_xy_candidate'] += 1
            continue
        plans.append(dict(lower_bound=int(bodies[0]['crossings']) - int(old_events),
                          option=option))
    if not plans:
        return None
    plans.sort(key=lambda plan: (plan['lower_bound'], plan['option']['priority']))
    # ---- phase 2: exact evaluation of the best combos ----------------------
    best = None
    evaluated_options = 0
    for plan in plans:
        if best is not None and plan['lower_bound'] >= best['delta']:
            break
        if evaluated_options >= int(cfg['max_combos']):
            break
        option = plan['option']
        evaluated_options += 1
        stats['combos_eval'] += 1
        for lead_s, lead_t in _lead_pair_candidates(state.route(rid), option, cfg):
            try:
                task, _src, _tgt = make_task_for_option(state, rid, option,
                                                        lead_s, lead_t)
            except (RB.BuilderError, ValueError) as error:
                reasons[getattr(error, 'reason', 'builder_value_error')] += 1
                continue
            full_cfg = dict(cfg)
            full_cfg['bodies_per_pair'] = int(cfg['bodies_per_pair'])
            bodies = xy_candidates(state, rid, task, int(option['layer']),
                                   float(option['z']), full_cfg)
            stats['xy_generated'] += len(bodies)
            if not bodies:
                continue
            if best is not None and int(bodies[0]['crossings']) - int(old_events) >= best['delta']:
                continue
            for body_record in bodies[:int(cfg['max_eval'])]:
                try:
                    candidate = build_route_candidate(state, rid, option,
                                                      lead_s, lead_t,
                                                      body_record['body'])
                except (RB.BuilderError, ValueError) as error:
                    reasons[getattr(error, 'reason', 'builder_value_error')] += 1
                    continue
                stats['built'] += 1
                evaluation = state.evaluate_candidate(rid, candidate)
                stats['evaluated'] += 1
                if not evaluation['ok']:
                    stats['rejected_3d'] += 1
                    kinds = evaluation.get('kinds') or []
                    if kinds:
                        reasons[kinds[0]] += 1
                    continue
                record = dict(route=candidate, delta=int(evaluation['delta']),
                              option=dict(option),
                              lead_s=float(lead_s), lead_t=float(lead_t),
                              family=body_record['family'],
                              xy_crossings=int(body_record['crossings']),
                              per_plane=evaluation['per_plane'],
                              seconds=time.time() - started,
                              lower_bound=int(plan['lower_bound']))
                if best is None or (record['delta'], record['route'].get('length_mm', 0.0)) < \
                        (best['delta'], best['route'].get('length_mm', 0.0)):
                    best = record
        if best is not None and -best['delta'] >= int(cfg['early_stop_delta']):
            best['early_stop'] = True
            break
    return best


def apply(state, record):
    """Commit one proposal (transactional single-route replacement)."""
    rid = int(record['route']['route_id'])
    new_row = RB.row_for_target(state.row(rid),
                                int(record['option']['layer']),
                                float(record['option']['z']))
    return state.commit(rid, record['route'], new_row=new_row,
                        note=record.get('family', ''))


def reroute_one(state, route_id, cfg=None, stats=None):
    record = propose(state, route_id, cfg=cfg, stats=stats)
    if record is None:
        return None
    if record['delta'] > -int(dict(DEFAULT_CFG, **(cfg or {}))['min_delta']):
        return None
    applied = apply(state, record)
    applied['family'] = record['family']
    applied['lead_s'] = record['lead_s']
    applied['lead_t'] = record['lead_t']
    applied['xy_crossings'] = record['xy_crossings']
    applied['seconds'] = record.get('seconds', 0.0)
    return applied


# ---------------------------------------------------------------------------
# multi-route joint reroute (transactional)
# ---------------------------------------------------------------------------
def _rip_up(state, rid):
    row = state.rows[rid]
    state.routes[rid] = _empty_route(rid, row)
    state._route_groups[rid] = {}
    for z_key, table in state.plane_chains.items():
        if rid in table:
            state.planes[z_key].remove(rid)
            table.pop(rid, None)
            state.plane_prims[z_key].pop(rid, None)


def _restore(state, rid, route, row):
    _rip_up(state, rid)
    state.rows[rid] = row
    state.commit(rid, route, new_row=row, note='joint_restore')


def reroute_joint(state, route_ids, cfg=None, log=None, min_gain=1):
    """Jointly rip up 2-3 routes, reroute them together, all-or-nothing.

    The ripped routes are re-planned one after another (the later ones see the
    earlier new geometry), each scored against **its own pre-rip crossing
    count** so that the joint objective is the total crossing change of the
    whole set.  The whole transaction is rolled back unless the total improves.
    """
    log = log or (lambda *_a, **_k: None)
    cfg0 = dict(DEFAULT_CFG, **(cfg or {}))
    rids = [int(r) for r in route_ids if int(r) in state.routes]
    if len(rids) < 2:
        return None
    saved = {rid: (copy.deepcopy(state.routes[rid]), dict(state.rows[rid]))
             for rid in rids}
    old_events = {}
    for rid in rids:
        old_events[rid] = sum(state.route_plane_events(rid, z)
                              for z in state.groups(rid))
    old_total = int(state.total)
    old_histories = len(state.history)

    def _sync_after_rip():
        state._recount_planes()
        state.obstacle_samples = state._build_obstacle_samples()
        state.obstacle_cache = {}
        state.prim_grids = {}
        state.world_cache = {}

    try:
        for rid in rids:
            _rip_up(state, rid)
        _sync_after_rip()
        results = []
        for rid in rids:
            cfg = dict(cfg0)
            cfg['old_events_override'] = int(old_events[rid])
            cfg['_ripped'] = True
            record = propose(state, rid, cfg=cfg)
            if record is None:
                raise RuntimeError('joint route %d has no candidate' % rid)
            applied = apply(state, record)
            applied['family'] = record['family']
            applied['lead_s'] = record['lead_s']
            applied['lead_t'] = record['lead_t']
            applied['xy_crossings'] = record['xy_crossings']
            applied['planned_delta'] = int(record['delta'])
            applied['old_events'] = int(old_events[rid])
            results.append(applied)
        gain = int(old_total - state.total)
        if gain < int(min_gain):
            raise RuntimeError('joint reroute gain %d < %d' % (gain, min_gain))
    except Exception as error:  # noqa: BLE001 - transactional rollback
        log('[joint] rollback (%s)' % error)
        for rid in rids:
            _rip_up(state, rid)
        _sync_after_rip()
        for rid in rids:
            route, row = saved[rid]
            state.rows[rid] = row
            state.commit(rid, route, new_row=row, note='joint_rollback')
        state.world_cache = {}
        state.prim_grids = {}
        del state.history[old_histories:]
        return None
    return dict(applied=results, total=int(state.total), old_total=old_total,
                gain=gain, routes=rids)


def _empty_route(route_id, row):
    """Placeholder record of a ripped-up route (never written to disk)."""
    return dict(route_id=int(route_id), plane=row.get('plane'),
                source_endpoint=row.get('source_endpoint'),
                target_endpoint=row.get('target_endpoint'),
                target_layer=int(row.get('target_layer', 0)),
                target_z_mm=float(row.get('target_z_mm', 0.0)),
                manual_group=str(row.get('manual_group') or ''),
                parts=[], length_mm=0.0, n_transitions=0,
                n_mid_transitions=0)
