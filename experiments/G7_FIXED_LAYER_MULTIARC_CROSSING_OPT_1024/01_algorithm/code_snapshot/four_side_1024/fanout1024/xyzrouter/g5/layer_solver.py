# -*- coding: utf-8 -*-
"""G5 third round: global joint layer assignment with atomic batch moves.

The solver has three layers of increasing fidelity:

1. **abstract colouring** of the co-planarity conflict graph (DSATUR, then Kempe
   chain swaps) over each route's *allowed height set* ``H_i`` -- the heights at
   which an exact R15 body can actually be built for that route;
2. **realisation + atomic batch evaluation**: the whole colouring is built into
   real XYZ routes and evaluated as *one* ``evaluate_batch`` call, so routes that
   are temporarily illegal on their own are judged only in the presence of their
   group;
3. **conflict-driven repair**: every hard issue the batch reports names the two
   routes involved and the constraint kind; those routes are pinned to their
   current height (or get the failing height removed from ``H_i``) and the
   colouring is re-solved.  This loop is what turns "19-colourable" into
   "geometrically realisable".
"""
from __future__ import annotations

import json
import math
import random
import time
from collections import Counter, defaultdict
from pathlib import Path

from four_side_1024.fanout1024.xyzrouter.g5 import model as G5
from four_side_1024.fanout1024.xyzrouter.g5 import candidates as C
from four_side_1024.fanout1024.xyzrouter.g5 import batch as B


# --------------------------------------------------------------------------
# allowed height sets
# --------------------------------------------------------------------------
def allowed_heights(route, heights=None, cache=None):
    """Heights at which an exact legal body can be built for ``route``."""
    rid = int(route['route_id'])
    if cache is not None and rid in cache:
        return cache[rid]
    heights = heights or G5.all_heights()
    body = C.body_part_indices(route)
    current = round(float(route['parts'][body[0]]['z_mm']), 9) if body else None
    out = []
    for z in heights:
        if current is not None and abs(z - current) < 1e-9:
            out.append(round(z, 9))
            continue
        candidate = C.reheight_any(route, z)
        if candidate is None:
            continue
        if G5.structure_issues(candidate):
            continue
        out.append(round(z, 9))
    if cache is not None:
        cache[rid] = out
    return out


# --------------------------------------------------------------------------
# colouring
# --------------------------------------------------------------------------
def dsatur_colour(nodes, adjacency, domain):
    """DSATUR over per-node domains; returns {node: colour} or None."""
    colour = {}
    remaining = set(nodes)
    while remaining:
        best = None
        for node in remaining:
            used = {colour[o] for o in adjacency[node] if o in colour}
            key = (len(used), len(adjacency[node]))
            if best is None or key > best[0]:
                best = (key, node)
        node = best[1]
        used = {colour[o] for o in adjacency[node] if o in colour}
        options = [c for c in domain[node] if c not in used]
        if not options:
            return None
        # prefer the colour closest to the node's current height
        options.sort(key=lambda c: abs(c - domain[node][0]))
        colour[node] = options[0]
        remaining.discard(node)
    return colour


def kempe_improve(colour, adjacency, domain, iterations=2000, rng=None):
    """Kempe-chain swaps that never break properness; returns best colouring."""
    rng = rng or random.Random(0)
    best = dict(colour)
    best_cost = len({c for c in colour.values()})
    for _ in range(iterations):
        nodes = list(colour)
        a = rng.choice(nodes)
        ca = colour[a]
        cb = rng.choice([c for c in set(colour.values()) if c != ca]
                        or [ca])
        if cb == ca:
            break
        # the two-colour subgraph component containing a
        component = []
        stack = [a]
        seen = {a}
        while stack:
            node = stack.pop()
            component.append(node)
            for other in adjacency[node]:
                if other in colour and other not in seen and \
                        colour[other] in (ca, cb):
                    seen.add(other)
                    stack.append(other)
        trial = dict(colour)
        for node in component:
            trial[node] = cb if colour[node] == ca else ca
        if any(trial[node] not in domain[node] for node in component):
            continue
        if all(trial[o] != trial[node] for node in component
               for o in adjacency[node]):
            colour = trial
            cost = len(set(colour.values()))
            if cost <= best_cost:
                best_cost = cost
                best = dict(colour)
    return best


# --------------------------------------------------------------------------
# realisation
# --------------------------------------------------------------------------
def realise(state, assignment, current_heights=None):
    """Build every route at its assigned height; return (batch, failures)."""
    batch = {}
    failures = []
    for rid, z in assignment.items():
        route = state.world.routes[int(rid)]
        body = C.body_part_indices(route)
        current = round(float(route['parts'][body[0]]['z_mm']), 9) if body else None
        if current is not None and abs(z - current) < 1e-9:
            continue
        new_route = C.reheight_any(route, float(z))
        if new_route is None:
            failures.append(dict(route_id=int(rid), z=float(z),
                                 reason='construction_failed'))
            continue
        batch[int(rid)] = new_route
    return batch, failures


def apply_assignment(state, assignment, log=print, label='layer-assignment'):
    """Realise an assignment and commit it as one atomic batch."""
    batch, failures = realise(state, assignment)
    if failures:
        log('[assign] %d routes could not be built: %s'
            % (len(failures), failures[:5]))
    if not batch:
        return dict(ok=True, moved=0, failures=failures, violations=len(
            state.violations))
    evaluation = B.evaluate_batch(state, batch, window_check=False)
    hard = evaluation['issues']
    log('[assign] %d routes, %d hard issues, %d violations touching the batch'
        % (len(batch), len(hard), len(evaluation['violations'])))
    if hard:
        return dict(ok=False, moved=0, failures=failures, issues=hard[:50],
                    violations=len(state.violations))
    info = B.commit_batch(state, batch, label=label)
    return dict(ok=bool(info['ok']), moved=len(batch) if info['ok'] else 0,
                failures=failures, issues=info.get('issues', [])[:50],
                violations=len(state.violations))


def offending_routes(issues):
    out = set()
    for issue in issues:
        for key in ('route_a', 'route_b', 'rid', 'other'):
            value = issue.get(key)
            if value is not None:
                out.add(int(value))
    return sorted(out)


# --------------------------------------------------------------------------
# batch move generation (graph-level prefilter, then exact evaluation)
# --------------------------------------------------------------------------
def occupants_by_height(state, height_of):
    out = defaultdict(set)
    for rid in state.world.routes:
        z = height_of(state.world.routes[rid])
        if z is not None:
            out[z].add(int(rid))
    return out


def swap_candidates(state, adjacency, height_of, limit=None):
    """Pairs (a, b) whose two-route height swap can only remove conflicts.

    Graph condition: apart from each other, ``a`` has no conflict with the
    occupants of ``b``'s height and vice versa.  Such a swap is *individually*
    illegal (each lands next to a route it conflicts with) but may be *jointly*
    legal -- exactly the case the single-route relayer could never accept.
    """
    occupants = occupants_by_height(state, height_of)
    pairs = []
    for a in sorted(state.world.routes):
        za = height_of(state.world.routes[a])
        if za is None:
            continue
        for b in adjacency.get(a, ()):
            zb = height_of(state.world.routes[b])
            if zb is None or abs(za - zb) < 1e-9:
                continue
            if (adjacency[a] & occupants[zb]) - {b}:
                continue
            if (adjacency[b] & occupants[za]) - {a}:
                continue
            pairs.append((a, b, za, zb))
            if limit and len(pairs) >= limit:
                return pairs
    return pairs


def cycle_candidates(state, adjacency, height_of, limit=40, max_triangles=200000):
    """Triples (a, b, c) whose cyclic height rotation is conflict-free."""
    occupants = occupants_by_height(state, height_of)
    out = []
    seen = set()
    for a in sorted(state.world.routes):
        za = height_of(state.world.routes[a])
        if za is None:
            continue
        for b in adjacency.get(a, ()):
            zb = height_of(state.world.routes[b])
            if zb is None or abs(za - zb) < 1e-9:
                continue
            if (adjacency[a] & occupants[zb]) - {b}:
                continue
            for c in adjacency.get(b, ()):
                key = (a, b, c)
                if key in seen or c == a or c not in adjacency.get(a, ()):
                    continue
                seen.add(key)
                zc = height_of(state.world.routes[c])
                if zc is None or len({za, zb, zc}) != 3:
                    continue
                if (adjacency[b] & occupants[zc]) - {c}:
                    continue
                if (adjacency[c] & occupants[za]) - {a}:
                    continue
                out.append((a, b, c, za, zb, zc))
                if len(out) >= limit:
                    return out
                if len(seen) > max_triangles:
                    return out
    return out


# --------------------------------------------------------------------------
# CP-SAT joint layer assignment
# --------------------------------------------------------------------------
def solve_cpsat(nodes, adjacency, domain, current, no_goods, time_limit=120.0,
                log=print, soft=False):
    """CP-SAT layer assignment.

    ``soft=False`` posts a hard disequality for every conflict edge (a proper
    colouring); ``soft=True`` instead charges a large penalty for every violated
    edge, which turns the model into a *minimum-conflict* assignment -- the right
    formulation once the realisable height sets make a perfect colouring
    impossible.

    ``no_goods`` is the geometry feedback: a list of ``((route, height),
    (route, height))`` clauses meaning "these two assignments must not both
    hold".
    """
    from ortools.sat.python import cp_model
    heights = sorted({z for values in domain.values() for z in values})
    model = cp_model.CpModel()
    var = {}
    for node in nodes:
        values = domain.get(node) or list(heights)
        var[node] = model.NewIntVar(0, len(values) - 1, 'z_%d' % node)
    index = {node: {z: i for i, z in enumerate(domain.get(node) or heights)}
             for node in nodes}
    edges = set()
    for a in nodes:
        for b in adjacency.get(a, ()):
            if a == b or b not in var:
                continue
            edges.add((min(a, b), max(a, b)))
    soft_terms = []
    posted = 0
    for (a, b) in edges:
        if not (set(index[a]) & set(index[b])):
            continue
        posted += 1
        if not soft:
            model.Add(var[a] != var[b])
            continue
        same = model.NewBoolVar('')
        model.Add(var[a] == var[b]).OnlyEnforceIf(same)
        model.Add(var[a] != var[b]).OnlyEnforceIf(same.Not())
        soft_terms.append(same)
    for (a, ha), (b, hb) in no_goods:
        if a not in var or b not in var:
            continue
        clauses = []
        if ha in index.get(a, {}):
            flag = model.NewBoolVar('')
            model.Add(var[a] != index[a][ha]).OnlyEnforceIf(flag)
            clauses.append(flag)
        if hb in index.get(b, {}):
            flag = model.NewBoolVar('')
            model.Add(var[b] != index[b][hb]).OnlyEnforceIf(flag)
            clauses.append(flag)
        if clauses:
            model.AddBoolOr(clauses)
    # displacement objective: how many height steps a route moves, in units of
    # the 0.05 mm layer pitch.  Minimising the *distance* (instead of the number
    # of moved routes) keeps the rebuilt S-curves short, which is what makes the
    # 3-D transition checks survivable.
    moves = []
    for node in nodes:
        current_z = current.get(node)
        values = domain.get(node) or heights
        if current_z is None or current_z not in index.get(node, {}):
            continue
        base = index[node][current_z]
        dist = model.NewIntVar(0, len(values) - 1, '')
        delta = model.NewIntVar(-len(values), len(values), '')
        model.Add(delta == var[node] - base)
        model.AddAbsEquality(dist, delta)
        moves.append(dist)
    objective = []
    if soft_terms:
        objective.append(sum(soft_terms) * 10000)
    if moves:
        objective.append(sum(moves))
    if objective:
        model.Minimize(sum(objective))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_search_workers = 8
    log('[cpsat] nodes=%d edges=%d soft=%s no_goods=%d'
        % (len(nodes), posted, soft, len(no_goods)))
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, status
    assignment = {}
    for node in nodes:
        values = domain.get(node) or heights
        assignment[node] = values[solver.Value(var[node])]
    if soft_terms:
        violated = sum(1 for term in soft_terms if solver.Value(term))
        moved = sum(solver.Value(term) for term in moves)
        log('[cpsat] soft objective: %d violated edges, total displacement '
            '%d layer steps, status=%s' % (violated, moved, status))
    return assignment, status
