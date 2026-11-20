# -*- coding: utf-8 -*-
"""G2 manual-U height policies (height_only contract).

G2a : every original manual group may pick ONE new body height (members share it)
G2b : every manual route may pick its own body height

Both respect the ``height_only`` contract: the XY body geometry is identical to
the baseline, only the physical height / the R15 end transitions change.  The
implementation keeps the two body landing points fixed by absorbing the
transition footprint change in the interface lead length, so the body path is
re-used verbatim and every candidate is exact.
"""
from __future__ import annotations

import math
import time
from collections import Counter, OrderedDict

from ..native3d import transition as T
from . import route_builder as RB
from . import world_adapter as WA

GROUP_ORDER = ('Z1-U1', 'Z1-U2', 'Z1-U3', 'Z1-U4',
               'Z2-U1', 'Z2-U2', 'Z2-U3', 'Z2-U4')


def manual_groups(state):
    groups = OrderedDict()
    for rid in sorted(state.rows):
        row = state.rows[rid]
        group = str(row.get('manual_group') or '').strip()
        if not group:
            continue
        groups.setdefault(group, []).append(int(rid))
    return OrderedDict((g, groups[g]) for g in GROUP_ORDER if g in groups)


def manual_route_ids(state):
    out = []
    for rid in sorted(state.rows):
        if str(state.rows[rid].get('manual_group') or '').strip():
            out.append(int(rid))
    return out


def non_manual_route_ids(state):
    out = []
    for rid in sorted(state.rows):
        if not str(state.rows[rid].get('manual_group') or '').strip():
            out.append(int(rid))
    return out


def current_height(state, rid):
    return float(state.routes[int(rid)]['target_z_mm'])


def feasible_heights(state, rid):
    """``[(layer_id, z_mm, lead_mm)]`` reachable under the height_only contract.

    The footprint change is absorbed by the interface lead, which must stay at
    or above the 0.25 mm process minimum, so the reachable set is bounded.
    """
    rid = int(rid)
    row = state.rows[rid]
    route = state.routes[rid]
    z0 = float(row['interface_z_mm'])
    lead_s, lead_t = RB.lead_lengths(route)
    lead = min(lead_s, lead_t)
    z_cur = float(route['target_z_mm'])
    f_old = T.transition_footprint(z_cur - z0, radius=RB.R15)
    out = []
    for pid in RB.BODY_PLANE_IDS:
        z = RB.plane_z(pid)
        if abs(z - z_cur) < 1e-9:
            out.append((int(pid), z, lead))
            continue
        f_new = T.transition_footprint(z - z0, radius=RB.R15)
        lead_new = lead + f_old - f_new
        if lead_new < RB.MIN_LEAD_MM - 1e-12:
            continue
        out.append((int(pid), z, lead_new))
    return out


def build_shift(state, rid, layer_id, z_mm):
    return RB.shift_height_keep_xy(state.routes[int(rid)], state.rows[int(rid)],
                                   int(layer_id), float(z_mm))


def plan_group_shift(state, group, layer_id, z_mm):
    """Build the shifted routes of one group at one height (partial on failure)."""
    replacements = {}
    failures = []
    for rid in group:
        try:
            replacements[int(rid)] = build_shift(state, rid, layer_id, z_mm)
        except RB.BuilderError as error:
            failures.append(dict(route_id=int(rid), reason=error.reason,
                                 detail=error.detail))
    return replacements, failures


def group_shared_heights(state, group):
    """Heights reachable by EVERY member of the group (strict G2a contract)."""
    sets = []
    for rid in group:
        sets.append({(int(pid), round(float(z), 9)) for pid, z, _lead
                     in feasible_heights(state, rid)})
    if not sets:
        return []
    common = set.intersection(*sets)
    return sorted(common, key=lambda item: (abs(item[1] - current_height(state, group[0])),
                                            item[1]))


def evaluate_shift(state, replacements, log=None):
    """3D validity + exact crossing delta of a batch of shifted routes."""
    if not replacements:
        return dict(ok=False, violations=[], delta=None, kind='empty')
    check = state.batch_evaluate(replacements)
    if not check['ok']:
        kinds = Counter(v.get('kind') for v in check['violations'])
        return dict(ok=False, violations=check['violations'][:20],
                    kinds=dict(kinds), delta=None, kind='3d')
    delta, detail = state.batch_crossing_delta(replacements)
    return dict(ok=True, violations=[], delta=int(delta), detail=detail,
                kind='ok')


def crowding_score(state, replacements=None, extra_counts=None):
    """Layer-crowding potential: sum over heights of n^2 (lower is better)."""
    counts = Counter()
    for z_key, prims in state.plane_prims.items():
        counts[z_key] += len(prims)
    if replacements:
        for rid, route in replacements.items():
            old = state.groups(rid)
            for z_key in old:
                counts[z_key] = max(0, counts[z_key] - 1)
            for z_key in WA.route_flat_groups(route):
                counts[z_key] = counts[z_key] + 1
    return int(sum(value * value for value in counts.values()))


def reheight_group(state, group, heights=None, log=None):
    """Choose the best ONE height for an original manual group (G2a)."""
    log = log or (lambda *_a, **_k: None)
    cand = heights if heights is not None else group_shared_heights(state, group)
    z_current = current_height(state, group[0])
    results = []
    for layer_id, z in cand:
        if abs(float(z) - z_current) < 1e-9:
            results.append(dict(layer=int(layer_id), z=float(z), delta=0,
                                crowding=crowding_score(state),
                                unchanged=True, failures=[]))
            continue
        replacements, failures = plan_group_shift(state, group, layer_id, z)
        if len(replacements) != len(group):
            results.append(dict(layer=int(layer_id), z=float(z), delta=None,
                                skipped='requires %d members, built %d'
                                        % (len(group), len(replacements)),
                                failures=failures[:8]))
            continue
        evaluation = evaluate_shift(state, replacements)
        if not evaluation['ok']:
            results.append(dict(layer=int(layer_id), z=float(z), delta=None,
                                skipped='3d', kinds=evaluation.get('kinds'),
                                failures=[]))
            continue
        results.append(dict(layer=int(layer_id), z=float(z),
                            delta=int(evaluation['delta']),
                            crowding=crowding_score(state, replacements),
                            replacements=replacements, failures=failures))
    valid = [item for item in results if item.get('delta') is not None]
    if not valid:
        return None, results
    # lexicographic: (crossing delta, crowding potential) - a reheight must pay
    # for itself in crossings when possible, otherwise the least crowded layout
    # is preferred because it is what unlocks the non-manual re-routing.
    valid.sort(key=lambda item: (item['delta'], item['crowding']))
    best = valid[0]
    if best.get('unchanged'):
        return best, results
    state.batch_commit(best['replacements'], note='g2a_%s_L%d'
                       % (group[0], best['layer']))
    return best, results


def reheight_all_groups(state, log=None, rounds=1):
    """Greedy G2a search over the eight original manual groups."""
    log = log or (lambda *_a, **_k: None)
    history = []
    groups = manual_groups(state)
    for _round in range(int(rounds)):
        changed = 0
        for group_name, group in groups.items():
            best, results = reheight_group(state, group, log=log)
            if best is None:
                log('[g2a] %s: no valid height, kept as is' % group_name)
                continue
            history.append(dict(round=_round + 1, group=group_name,
                                members=len(group), chosen=best,
                                candidates=[{k: v for k, v in item.items()
                                             if k != 'replacements'}
                                            for item in results]))
            if not best.get('unchanged'):
                changed += 1
            log('[g2a] %s -> L%s z=%+0.2f delta=%s crowding=%s' % (
                group_name, best.get('layer'), best.get('z'),
                best.get('delta'), best.get('crowding')))
        if changed == 0:
            break
    return history


def reheight_one_route(state, rid, heights=None, log=None):
    """G2b: pick one manual route's own best height (exact crossing delta)."""
    rid = int(rid)
    z_current = current_height(state, rid)
    candidates = heights if heights is not None else feasible_heights(state, rid)
    best = None
    tried = 0
    for layer_id, z, _lead in candidates:
        if abs(float(z) - z_current) < 1e-9:
            continue
        try:
            candidate = build_shift(state, rid, layer_id, z)
        except RB.BuilderError:
            continue
        tried += 1
        evaluation = state.evaluate_candidate(rid, candidate)
        if not evaluation['ok']:
            continue
        delta = int(evaluation['delta'])
        if best is None or delta < best['delta']:
            best = dict(route=candidate, delta=delta, layer=int(layer_id),
                        z=float(z), tried=tried)
    return best


def apply_route_reheight(state, rid, record):
    rid = int(rid)
    new_row = RB.row_for_target(state.rows[rid], int(record['layer']),
                                float(record['z']))
    return state.commit(rid, record['route'], new_row=new_row,
                        note='g2b_manual_height')


def reheight_routes(state, route_ids=None, log=None, min_delta=1,
                    rounds=1):
    """G2b: per-route manual height search (exact crossing delta)."""
    log = log or (lambda *_a, **_k: None)
    route_ids = route_ids if route_ids is not None else manual_route_ids(state)
    history = []
    for _round in range(int(rounds)):
        changed = 0
        for rid in route_ids:
            record = reheight_one_route(state, rid)
            if record is None or record['delta'] > -int(min_delta):
                continue
            applied = apply_route_reheight(state, rid, record)
            history.append(dict(round=_round + 1, route_id=int(rid),
                                delta=int(record['delta']),
                                old_layer=int(applied['old_layer']),
                                new_layer=int(applied['new_layer']),
                                old_z=applied['old_z'], new_z=applied['new_z'],
                                total_after=int(state.total)))
            changed += 1
        state.per_route = None
        log('[g2b] round %d: %d manual routes re-heighted, total=%d' % (
            _round + 1, changed, state.total))
        if changed == 0:
            break
    return history
