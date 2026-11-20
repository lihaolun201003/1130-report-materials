# -*- coding: utf-8 -*-
"""Joint XY+Z search over the XYZ router's state space.

The search space of one route is

    (target physical height z,  lead lengths (lead_s, lead_t),  XY corridor)

where the XY corridor is an exact R15 motion-primitive chain (line / quarter arc
/ short-S) from the source landing ``A`` with heading ``dA`` to the target landing
``B`` with arrival heading ``-dB``.  ``plan_combos`` enumerates that space with a
cheap crossing pre-rank, and ``beam_search`` keeps the best ``beam`` combos per
target height (beam search over heights), which is what the production
``local_reroute.propose`` evaluates exactly.

Multi-height bodies (several legal S-transitions in the middle of a route) are
supported through ``height_plan_options`` + ``route_builder.insert_height_plan``.
"""
from __future__ import annotations

import itertools

from . import local_reroute as LR
from . import route_builder as RB
from . import corridor_search as CS
from . import route_state as RS
from . import world_adapter as WA

INF = float('inf')


def height_plan_options(current_z, target_z, max_hops=1):
    """Physical-height sequences: direct, or via one intermediate height."""
    plans = [[float(target_z)]]
    if max_hops >= 2 and abs(float(target_z) - float(current_z)) > 1e-9:
        for plane_id in RB.BODY_PLANE_IDS:
            z = RB.plane_z(plane_id)
            if abs(z - float(current_z)) < 1e-9 or abs(z - float(target_z)) < 1e-9:
                continue
            plans.append([float(z), float(target_z)])
    return plans


def plan_combos(state, route_id, cfg=None):
    """Cheap pre-screen of every (target height, lead pair) combo.

    Returns ``[{'option', 'lead_s', 'lead_t', 'lower_bound', 'bodies'}]`` sorted
    by the exact crossing lower bound (no 3D evaluation yet).
    """
    cfg = dict(LR.DEFAULT_CFG, **(cfg or {}))
    rid = int(route_id)
    old_events = sum(state.route_plane_events(rid, z) for z in state.groups(rid))
    pre_cfg = dict(cfg)
    pre_cfg['max_candidates'] = int(cfg['prescreen_candidates'])
    pre_cfg['bodies_per_pair'] = int(cfg['bodies_per_pair']) + 1
    pre_cfg['_prescreen'] = True
    pre_cfg['max_lead_pairs'] = 1
    combos = []
    for option in LR.target_options(state, rid, cfg):
        lead_s, lead_t = LR._lead_pair_candidates(state.route(rid), option, cfg)[0]
        try:
            task, _src, _tgt = LR.make_task_for_option(state, rid, option,
                                                       lead_s, lead_t)
        except (RB.BuilderError, ValueError):
            continue
        bodies = LR.xy_candidates(state, rid, task, int(option['layer']),
                                  float(option['z']), pre_cfg)
        if not bodies:
            continue
        combos.append(dict(option=dict(option), lead_s=float(lead_s),
                           lead_t=float(lead_t),
                           lower_bound=int(bodies[0]['crossings']) - int(old_events),
                           bodies=bodies))
    combos.sort(key=lambda item: (item['lower_bound'], item['option']['priority']))
    return combos


def beam_search(state, route_id, beam=2, cfg=None):
    """Beam search over target heights; returns the exact-evaluated best record.

    This is the exploratory version of ``local_reroute.propose`` (same geometry,
    same exact D56 + true-3D acceptance) with an explicit beam over heights and a
    corridor-cost re-ranking of the XY candidates (``corridor_search``).
    """
    cfg = dict(LR.DEFAULT_CFG, **(cfg or {}))
    cfg['max_combos'] = int(beam)
    rid = int(route_id)
    combos = plan_combos(state, rid, cfg)
    best = None
    for combo in combos[:int(beam)]:
        option = combo['option']
        z_key = WA.plane_key(option['z'])
        grid = CS.occupancy_grid(state.plane_routes(z_key, exclude_route=rid))
        ranked = CS.select_corridors(combo['bodies'], grid,
                                     keep=max(1, int(cfg['max_eval'])))
        for body_record in ranked:
            try:
                candidate = LR.build_route_candidate(state, rid, option,
                                                     combo['lead_s'],
                                                     combo['lead_t'],
                                                     body_record['body'])
            except (RB.BuilderError, ValueError):
                continue
            evaluation = state.evaluate_candidate(rid, candidate)
            if not evaluation['ok']:
                continue
            record = dict(route=candidate, delta=int(evaluation['delta']),
                          option=dict(option), lead_s=combo['lead_s'],
                          lead_t=combo['lead_t'],
                          family=body_record.get('family'),
                          corridor_cost=body_record.get('corridor_cost'),
                          xy_crossings=int(body_record.get('crossings') or 0))
            if best is None or record['delta'] < best['delta']:
                best = record
    return best


def search_space_summary():
    return dict(
        state='(x, y, z, heading, used_transitions, cost, length)',
        actions=['plane line', 'R15 quarter arc', 'R15 two-arc S height change',
                 'multi-segment chains / multi-hop height plans'],
        xy_sources=['layer2d R15 family library (L/Z/U/S/detour/staircase)',
                    'corridor_search A* coarse corridor re-ranking'],
        height_sources=['19 body planes + 2 interface-direct options',
                        'mid-body arc-spanning excursions (multi-height bodies)'],
        acceptance=['exact strict-D56 per physical height',
                    'true 3D l3d.world.World clearance/R15/glass',
                    'exact crossing delta (frozen 2409 counting rule)'],
    )
