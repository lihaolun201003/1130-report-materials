# -*- coding: utf-8 -*-
"""G5 third round: atomic multi-route (batch) geometry evaluation.

The single-route loop of the previous rounds is order dependent: a candidate is
rejected because the routes that will move *later* still occupy their old
height, and a later move never revisits that rejection.  This module removes the
order dependence by evaluating a whole set of new routes **simultaneously**:

``evaluate_batch(state, batch)``
    remove every old route of ``batch`` from the world, insert every new route,
    check all constraints that touch the batch (against the untouched routes
    *and* between the batch members), read back the resulting crossings, then
    restore the world exactly.

``commit_batch(state, batch)``
    apply the batch for real, re-check with the exact (window-aware) audit, and
    roll back **all** of it if anything is hard-illegal.

Both are atomic: the world is restored bit-for-bit on failure (the routes are
kept in a snapshot, so even an exception inside the geometry code cannot leave a
half-migrated layout behind).
"""
from __future__ import annotations

import copy
import json
import time

from four_side_1024.fanout1024.xyzrouter.g5 import model as G5
from four_side_1024.fanout1024.xyzrouter.g5 import search as S


def snapshot(routes, ids):
    """Deep-copied snapshot of the given route ids."""
    return {int(rid): copy.deepcopy(routes[int(rid)]) for rid in ids}


def restore(world, snap):
    """Put the snapshot back into the world (indexes rebuilt per route)."""
    for rid, route in snap.items():
        world.set_route(int(rid), copy.deepcopy(route))


def _event_key(event):
    return (min(event['route_a'], event['route_b']),
            max(event['route_a'], event['route_b']),
            round(float(event['z']), 6),
            round(float(event['x']), 6), round(float(event['y']), 6))


def evaluate_batch(state, batch, window_check=False, include_3d=True):
    """Evaluate ``{route_id: new_route}`` as one atomic geometry change.

    Returns ``dict(ok, issues, violations, crossings, per_route, seconds)``:

    * ``issues``  -- hard-constraint violations created by the batch (empty when
      ``ok`` is true); each carries the two route ids involved,
    * ``violations`` / ``crossings`` -- every crossing that touches a batch route
      *after* the change, deduplicated by (pair, z, point),
    * ``per_route`` -- ``{rid: n_violations}`` for the batch routes only.

    The world is restored to the state it had on entry, whatever happens.
    """
    started = time.time()
    world = state.world
    ids = [int(rid) for rid in batch]
    old = snapshot(world.routes, ids)
    try:
        # 1) remove the old geometry of every batch route from the indexes
        for rid in ids:
            world.drop_route(rid)
        # 2) insert every new route, then check the batch as a whole
        for rid in ids:
            world.set_route(rid, copy.deepcopy(batch[rid]))
        issues = []
        crossings = {}
        per_route = {}
        for rid in ids:
            # structural contract first (heights, R15, continuity, glass)
            for issue in G5.structure_issues(batch[rid]):
                structural = dict(issue)
                structural['kind'] = 'structure_' + str(issue.get('kind'))
                structural['route_a'] = rid
                structural['route_b'] = rid
                issues.append(structural)
            result = world.route_issues(rid, min_angle_deg=state.min_angle_deg,
                                        window_check=window_check,
                                        include_3d=include_3d)
            for issue in result['issues']:
                issues.append(dict(issue))
            for event in result['crossings']:
                crossings[_event_key(event)] = event
        for event in crossings.values():
            rid = int(event['route_a'])
            if rid in ids:
                per_route[rid] = per_route.get(rid, 0) + 1
        # a crossing is counted once per batch route it touches
        violations = [event for event in crossings.values()
                      if event['angle_deg'] < state.min_angle_deg]
        per_violation = {}
        for event in violations:
            for rid in (int(event['route_a']), int(event['route_b'])):
                if rid in ids:
                    per_violation[rid] = per_violation.get(rid, 0) + 1
        return dict(ok=not issues, issues=issues,
                    violations=violations, crossings=list(crossings.values()),
                    per_violation=per_violation,
                    seconds=round(time.time() - started, 4))
    finally:
        # 3) restore exactly (even on exception)
        for rid in ids:
            world.drop_route(rid)
        for rid, route in old.items():
            world.set_route(rid, copy.deepcopy(route))


def score_batch(state, batch, evaluation):
    """Global objective change this batch would cause (lower is better)."""
    ids = [int(rid) for rid in batch]
    before_v = sum(state.count_route_pair_violations(ids))
    after_v = len(evaluation['violations'])
    before_d = state.pair_deficit(ids)
    after_d = sum(max(0.0, state.min_angle_deg - event['angle_deg'])
                  for event in evaluation['violations'])
    return (after_v - before_v, round(after_d - before_d, 6))


def commit_batch(state, batch, label='batch'):
    """Apply a batch atomically; roll back everything if it is not legal."""
    world = state.world
    ids = [int(rid) for rid in batch]
    old = snapshot(world.routes, ids)
    lengths = {rid: world.chains[rid].length_mm for rid in ids}
    try:
        for rid in ids:
            world.set_route(rid, copy.deepcopy(batch[rid]))
        issues = []
        crossings = {}
        new_lengths = {}
        for rid in ids:
            for issue in G5.structure_issues(batch[rid]):
                structural = dict(issue)
                structural['kind'] = 'structure_' + str(issue.get('kind'))
                structural['route_a'] = rid
                structural['route_b'] = rid
                issues.append(structural)
            if issues:
                raise _BatchRejected(issues)
            result = world.route_issues(rid, min_angle_deg=state.min_angle_deg,
                                        window_check=True, include_3d=True)
            issues.extend(result['issues'])
            for event in result['crossings']:
                crossings[_event_key(event)] = event
            new_lengths[rid] = world.chains[rid].length_mm
        if issues:
            raise _BatchRejected(issues)
    except _BatchRejected as rejection:
        for rid in ids:
            world.drop_route(rid)
        for rid, route in old.items():
            world.set_route(rid, copy.deepcopy(route))
        return dict(ok=False, issues=list(rejection.issues), reverted=True)
    except Exception as error:  # noqa: BLE001 - roll back on *any* failure
        for rid in ids:
            world.drop_route(rid)
        for rid, route in old.items():
            world.set_route(rid, copy.deepcopy(route))
        return dict(ok=False, issues=[dict(kind='exception', detail=str(error))],
                    reverted=True)
    # --- accepted: update the bookkeeping exactly like State.apply does
    touched = set(ids)
    state.crossings = [event for event in state.crossings
                       if int(event['route_a']) not in touched
                       and int(event['route_b']) not in touched]
    state.crossings.extend(crossings.values())
    state.violations = [event for event in state.violations
                        if int(event['route_a']) not in touched
                        and int(event['route_b']) not in touched]
    state.violations.extend(event for event in crossings.values()
                            if event['angle_deg'] < state.min_angle_deg)
    state._counters()
    state.length += sum(new_lengths[rid] - lengths[rid] for rid in ids)
    state.moves.append(dict(label=label, routes=len(ids), ids=ids))
    return dict(ok=True, issues=[], reverted=False,
                violations=len([e for e in crossings.values()
                                if e['angle_deg'] < state.min_angle_deg]),
                crossings=len(crossings))


class _BatchRejected(Exception):
    def __init__(self, issues):
        super().__init__('batch rejected')
        self.issues = issues


def batch_signature(batch):
    return json.dumps({int(rid): [[round(v, 6) for v in prim.get('p0', [])],
                                  [round(v, 6) for v in prim.get('p1', [])]]
                       for rid, route in sorted(batch.items())
                       for part in route['parts'] if part['kind'] == 'flat'
                       for prim in part['primitives']},
                      sort_keys=True)
