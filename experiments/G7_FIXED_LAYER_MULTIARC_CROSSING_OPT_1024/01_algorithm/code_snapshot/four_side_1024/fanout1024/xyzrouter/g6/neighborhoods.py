# -*- coding: utf-8 -*-
"""G6 move families N1..N6 with exact incremental evaluation.

Every move is a *set* of route replacements ``{route_id: new_route}`` that is
evaluated atomically.  The hard manufacturing constraints (strict D56, R15 /
structure / glass, true 3-D 0.05 mm clearance, self clearance) are never
relaxed: a move whose evaluation reports any hard issue is illegal and is
discarded before the annealing acceptance test.

Move families
-------------
N1 ``single_multiarc``   one route, body MultiArc regenerated at the same
                         height / lead pair (the core G6 move: the frozen
                         layer2d candidate grammar is re-enumerated and a
                         different candidate is chosen).
N2 ``pair_multiarc``     two routes of one residual violation, both bodies
                         regenerated simultaneously (atomic batch).
N3 ``group_multiarc``    2..6 routes of one violation connected component,
                         regenerated jointly.
N4 ``single_reheight``   one route, whole body moved to another physical height
                         (R15 S transitions rebuilt) with a fresh MultiArc body.
N5 ``transition_joint``  port lead-out length / lift of an interface-direct
                         route (transition geometry jointly rebuilt).
N6 ``joint_combined``    multi-route mix of height + MultiArc + transition
                         reconstruction (the full G6 neighbourhood).

All candidate bodies come from :mod:`...g6.geometry`, which wraps the frozen
2-D router's candidate grammar; no new geometric primitive is introduced.
"""
from __future__ import annotations

import copy
import math
import random
from collections import Counter, OrderedDict, defaultdict

from . import geometry as GEO
from ..g5 import model as G5
from ..g5 import candidates as C5
from ..g5 import batch as B5
from ..g5 import search as S5

THETA_MIN_DEG = float(G5.THETA_MIN_DEG)
M_DEFAULT = 1000.0      # energy weight of one sub-45 crossing (dimensionless)
LAMBDA_DEFAULT = 1.0    # energy weight of one degree of angle deficit


# ---------------------------------------------------------------------------
# move record
# ---------------------------------------------------------------------------
class Move:
    __slots__ = ('kind', 'routes', 'label', 'changed_transitions')

    def __init__(self, kind, routes, label, changed_transitions=True):
        self.kind = str(kind)
        self.routes = {int(rid): route for rid, route in routes.items()}
        self.label = str(label)
        self.changed_transitions = bool(changed_transitions)

    @property
    def ids(self):
        return tuple(sorted(self.routes))

    def __repr__(self):  # pragma: no cover - debug only
        return f'Move({self.kind}, {self.ids}, {self.label})'


# ---------------------------------------------------------------------------
# exact / incremental evaluator
# ---------------------------------------------------------------------------
class Evaluator:
    """Hard-constraint + crossing evaluation on top of a ``g5.search.State``."""

    def __init__(self, state, theta=THETA_MIN_DEG):
        self.state = state
        self.theta = float(theta)

    # -- helpers ---------------------------------------------------------
    def _violations(self, crossings):
        return [event for event in crossings
                if event['angle_deg'] < self.theta]

    def _deficit(self, violations):
        return float(sum(max(0.0, self.theta - event['angle_deg'])
                         for event in violations))

    # -- single route ----------------------------------------------------
    def quick(self, rid, new_route):
        """Structure + same-height D56/angle only (no 3-D), for prefiltering."""
        rid = int(rid)
        structure = G5.structure_issues(new_route)
        if structure:
            return dict(ok=False, hard=structure, violations=[], deficit=0.0,
                        crossings=0)
        result = self.state.world.route_issues(
            rid, route=new_route, min_angle_deg=self.theta,
            include_3d=False, window_check=False)
        if result['issues']:
            return dict(ok=False, hard=list(result['issues']), violations=[],
                        deficit=0.0, crossings=0)
        violations = self._violations(result['crossings'])
        return dict(ok=True, hard=[], violations=violations,
                    deficit=self._deficit(violations),
                    crossings=len(result['crossings']))

    def full(self, rid, new_route, transitions_changed=True,
             include_self=False):
        """Structure + D56/angle + true 3-D clearance (+ optional self audit).

        The self-clearance audit (numpy/scipy, ~5-15 ms) is run once on the
        move that is about to be committed, not on every candidate.
        """
        rid = int(rid)
        structure = G5.structure_issues(new_route)
        if structure:
            return dict(ok=False, hard=structure, violations=[], deficit=0.0,
                        crossings=0)
        result = self.state.world.route_issues(
            rid, route=new_route, min_angle_deg=self.theta,
            include_3d=True, window_check=True)
        hard = list(result['issues'])
        if not transitions_changed:
            # the route's own transitions are untouched; only the
            # flat-vs-other-transition rule can change for the new body
            hard = [issue for issue in hard
                    if issue.get('kind') not in (
                        '3d_transition_flat', '3d_transition_transition')]
        if include_self:
            hard.extend(self.self_issues(rid, new_route))
        violations = self._violations(result['crossings'])
        return dict(ok=not hard, hard=hard, violations=violations,
                    deficit=self._deficit(violations),
                    crossings=len(result['crossings']))

    def self_issues(self, rid, new_route):
        """Self-clearance issues of one rebuilt route (commit-time gate)."""
        try:
            return list(G5.self_clearance(G5.RouteChain(new_route), int(rid)))
        except Exception:  # noqa: BLE001 - self audit is a safety net
            return []

    # -- atomic batch ----------------------------------------------------
    def batch(self, routes, include_self=False):
        evaluation = B5.evaluate_batch(self.state, routes, window_check=True,
                                       include_3d=True)
        hard = list(evaluation['issues'])
        violations = self._violations(evaluation['violations'])
        ids = [int(rid) for rid in routes]
        # NOTE: g5.batch.score_batch has a pre-existing ``sum(int)`` bug (never
        # exercised by G5 because it used evaluate_batch only); the delta is
        # computed here from the exact same state counters instead.
        before_bad = len(self.state.violations_touching(ids))
        before_def = self.state.pair_deficit(ids)
        delta_bad = len(violations) - before_bad
        delta_def = self._deficit(violations) - before_def
        return dict(ok=not hard, hard=hard, violations=violations,
                    deficit=self._deficit(violations),
                    delta_bad=delta_bad, delta_deficit=delta_def,
                    crossings=len(evaluation['crossings']))

    # -- global counters -------------------------------------------------
    def before_single(self, rid):
        rid = int(rid)
        touching = self.state.violations_touching([rid])
        return len(touching), self.state.pair_deficit([rid])

    def before_batch(self, ids):
        touching = self.state.violations_touching(ids)
        return len(touching), self.state.pair_deficit(ids)

    def energy_delta(self, delta_bad, delta_deficit, M=M_DEFAULT,
                     lam=LAMBDA_DEFAULT):
        return M * delta_bad + lam * delta_deficit


# ---------------------------------------------------------------------------
# candidate proposer (N1..N6)
# ---------------------------------------------------------------------------
DEFAULT_PROPOSER_CFG = dict(
    pool_size=20,              # assembled candidate routes kept per pose
    pool_build=140,            # layer2d bodies built before sampling
    pool_cache=200,            # LRU cache of assembled candidate pools
    quicks=20,                 # quick evaluations per single move
    fulls=2,                   # full 3-D validations per single move
    pair_quicks=4,             # candidate options per route in a pair move
    pair_attempts=4,           # atomic batch evaluations per pair move
    group_attempts=3,
    group_max=6,
    kick_attempts=2,
    cheap_reheight=0.55,       # share of re-height moves that reuse g5 shapes
    lead_choices=GEO.LEAD_CHOICES,
    heights=None,              # resolved to G5.all_heights()
)


class Proposer:
    """Samples legal move proposals around the current violation set."""

    def __init__(self, state, evaluator, rng, cfg=None, log=None):
        self.state = state
        self.evaluator = evaluator
        self.rng = rng
        self.cfg = dict(DEFAULT_PROPOSER_CFG, **(cfg or {}))
        self.log = log or (lambda *args, **kwargs: None)
        self.heights = list(self.cfg['heights'] or G5.all_heights())
        self.pools = OrderedDict()
        self.dissections = {}
        self.stats = Counter()
        self._heights_by_route = {}
        self._rebuild_route_info()

    # ------------------------------------------------------------ metadata
    def _rebuild_route_info(self):
        self.manual = set()
        self.unsupported = set()
        self.direct = set()
        self.lifted = set()
        for rid, route in self.state.world.routes.items():
            rid = int(rid)
            dissected = GEO.dissect_route(route)
            self.dissections[rid] = dissected
            if (route.get('manual_group') or '').strip():
                self.manual.add(rid)
            if dissected is None:
                self.unsupported.add(rid)
                continue
            if dissected['kind'] == 'direct':
                self.direct.add(rid)
            else:
                self.lifted.add(rid)

    def refresh_route(self, rid):
        rid = int(rid)
        route = self.state.world.routes[rid]
        self.dissections[rid] = GEO.dissect_route(route)
        for key in [key for key in self.pools if key[0] == rid]:
            del self.pools[key]
        # drop every cached pool that mentions the route (pools are per route)
        self._heights_by_route.pop(rid, None)

    def allowed_heights(self, rid):
        rid = int(rid)
        if rid in self._heights_by_route:
            return self._heights_by_route[rid]
        dissected = self.dissections.get(rid)
        if dissected is None:
            out = []
        else:
            forbidden = {round(float(dissected['zs']), 9),
                         round(float(dissected['zt']), 9)}
            out = [z for z in self.heights
                   if round(float(z), 9) not in forbidden]
        self._heights_by_route[rid] = out
        return out

    def regenerable(self, rid):
        return int(rid) not in self.manual and self.dissections.get(int(rid)) is not None

    # --------------------------------------------------------------- pools
    def _pool_key(self, rid, mode, z_body, lead_s, lead_t):
        return (int(rid), str(mode), round(float(z_body), 6),
                round(float(lead_s), 6), round(float(lead_t), 6))

    def pool(self, rid, mode, z_body=None, lead_s=None, lead_t=None,
             size=None):
        rid = int(rid)
        dissected = self.dissections.get(rid)
        if dissected is None:
            return []
        if z_body is None:
            z_body = dissected['z_body']
        if lead_s is None:
            lead_s = dissected['lead_s']
        if lead_t is None:
            lead_t = dissected['lead_t']
        key = self._pool_key(rid, mode, z_body, lead_s, lead_t)
        cached = self.pools.get(key)
        if cached is not None:
            self.pools.move_to_end(key)
            return cached
        size = int(self.cfg['pool_size'] if size is None else size)
        candidates = []
        counts = max(1, int(self.cfg['pool_build']))
        if mode in ('body', 'direct'):
            bodies = self._bodies(rid, dissected, mode, z_body, lead_s,
                                  lead_t, counts)
            for label, route in bodies:
                candidates.append((label, route))
                if len(candidates) >= size:
                    break
        else:
            bodies = self._bodies(rid, dissected, mode, z_body, lead_s,
                                  lead_t, counts)
            for label, route in bodies:
                candidates.append((label, route))
                if len(candidates) >= size:
                    break
        if len(self.pools) >= int(self.cfg['pool_cache']):
            self.pools.popitem(last=False)
        self.pools[key] = candidates
        self.stats['pools_built'] += 1
        self.stats['pool_candidates'] += len(candidates)
        return candidates

    def _bodies(self, rid, dissected, mode, z_body, lead_s, lead_t, build):
        route = self.state.world.routes[rid]
        if mode in ('body', 'direct'):
            sample = int(self.cfg['pool_size'])
            raw = GEO.regenerate(route, dissected, 'body', self.rng,
                                 sample=sample, max_build=build)
        elif mode == 'lead':
            raw = GEO.regenerate(route, dissected, 'lead', self.rng,
                                 leads=(lead_s, lead_t),
                                 sample=int(self.cfg['pool_size']),
                                 max_build=build)
        else:  # reheight / lift
            raw = GEO.regenerate(route, dissected, 'reheight', self.rng,
                                 z_body=z_body, leads=(lead_s, lead_t),
                                 sample=int(self.cfg['pool_size']),
                                 max_build=build)
        return raw

    # -------------------------------------------------- route-level helpers
    def _pick_mode(self, rid, profile):
        """Return ``(mode, z_body, lead_s, lead_t)`` for one route."""
        rng = self.rng
        rid = int(rid)
        dissected = self.dissections.get(rid)
        if dissected is None:
            return None
        direct = dissected['kind'] == 'direct'
        weights = []
        if profile in ('B', 'C'):
            weights = [('body', 1.0)]
        elif profile == 'D':
            weights = [('body', 0.52), ('cheap_reheight', 0.30),
                       ('lead', 0.18)]
        else:  # 'E' full G6
            weights = [('body', 0.42), ('lead', 0.14), ('reheight', 0.28),
                       ('lift', 0.16)]
        if direct:
            weights = [(name, w) for name, w in weights
                       if name in ('body', 'lift', 'reheight')]
        else:
            weights = [(name, w) for name, w in weights if name != 'lift']
        if not weights:
            return None
        total = sum(weight for _name, weight in weights)
        draw = rng.random() * total
        mode = weights[-1][0]
        for name, weight in weights:
            if draw < weight:
                mode = name
                break
            draw -= weight
        if mode == 'body' or (direct and mode not in ('lift', 'reheight')):
            return dict(mode='body', z_body=dissected['z_body'],
                        lead_s=dissected['lead_s'], lead_t=dissected['lead_t'])
        if direct:  # 'lift' / 'reheight' of a direct route
            heights = self.allowed_heights(rid)
            if not heights:
                return None
            z_body = float(rng.choice(heights))
            choices = list(self.cfg['lead_choices'])
            lead_s = float(rng.choice(choices))
            lead_t = float(rng.choice(choices))
            return dict(mode='reheight', z_body=z_body, lead_s=lead_s,
                        lead_t=lead_t)
        if mode == 'lead':
            choices = list(self.cfg['lead_choices'])
            lead_s = float(rng.choice([value for value in choices
                                       if abs(value - dissected['lead_s']) > 1e-9]
                                      or choices))
            lead_t = float(rng.choice(choices))
            return dict(mode='lead', z_body=dissected['z_body'],
                        lead_s=lead_s, lead_t=lead_t)
        heights = self.allowed_heights(rid)
        if not heights:
            return None
        if (not direct and rng.random() < float(self.cfg['cheap_reheight'])):
            return dict(mode='cheap_reheight', z_body=dissected['z_body'],
                        lead_s=dissected['lead_s'], lead_t=dissected['lead_t'])
        z_body = float(rng.choice(heights))
        lead_s, lead_t = dissected['lead_s'], dissected['lead_t']
        if rng.random() < 0.35:
            choices = list(self.cfg['lead_choices'])
            lead_s = float(rng.choice(choices))
            lead_t = float(rng.choice(choices))
        return dict(mode='reheight', z_body=z_body, lead_s=lead_s,
                    lead_t=lead_t)

    def candidate_routes(self, rid, profile='E', sample=None, mode_choice=None):
        """Return ``[(label, new_route, mode_name)]`` candidates for one route."""
        rid = int(rid)
        if not self.regenerable(rid):
            return []
        plan = mode_choice or self._pick_mode(rid, profile)
        if plan is None:
            return []
        if plan['mode'] == 'cheap_reheight':
            return self.cheap_reheight_candidates(
                rid, sample=int(sample or self.cfg['pair_quicks']))
        pool = self.pool(rid, plan['mode'], plan['z_body'], plan['lead_s'],
                         plan['lead_t'])
        if not pool:
            return []
        sample = int(sample or self.cfg['quicks'])
        chosen = self.rng.sample(pool, min(sample, len(pool)))
        return [(label, route, plan['mode']) for label, route in chosen]

    def cheap_reheight_candidates(self, rid, sample=3):
        """Re-height candidates that reuse the g5 exact closure solvers.

        These keep the existing body shape and only rebuild the two R15
        S-transitions (``g5.candidates.reheight_variants``); they cost ~10 ms
        per route instead of ~100 ms for a fresh MultiArc enumeration, which
        makes the multi-route re-height neighbourhood (N4) affordable.
        """
        rid = int(rid)
        route = self.state.world.routes[rid]
        heights = self.allowed_heights(rid)
        if not heights:
            return []
        variants = []
        try:
            for label, new_route in C5.reheight_variants(route,
                                                         heights=heights):
                if new_route is None:
                    continue
                if G5.structure_issues(new_route):
                    continue
                variants.append((str(label), new_route, 'cheap_reheight'))
        except Exception:  # noqa: BLE001 - closure solver may refuse a route
            variants = []
        if not variants:
            z_body = float(self.rng.choice(heights))
            for builder in (C5.reheight_any, C5.reheight_full):
                try:
                    new_route = builder(route, z_body)
                except Exception:  # noqa: BLE001
                    new_route = None
                if new_route is not None and not G5.structure_issues(new_route):
                    variants.append((f'reheight:z={z_body:+.3f}', new_route,
                                     'cheap_reheight'))
                    break
        if len(variants) > sample:
            variants = self.rng.sample(variants, sample)
        self.stats['cheap_reheight'] += len(variants)
        return variants


# ---------------------------------------------------------------------------
# single-route move (N1 / N4 / N5)
# ---------------------------------------------------------------------------
def propose_single(proposer, profile='E'):
    """Best-of-pool single-route move proposal, or ``None``."""
    state = proposer.state
    evaluator = proposer.evaluator
    rng = proposer.rng
    if not state.per_route:
        return None
    rids = [rid for rid in state.per_route
            if proposer.regenerable(rid)]
    if not rids:
        return None
    # weight by angle deficit so the worst events are attacked more often
    weights = [state.per_route_deficit.get(rid, 0.0) + 0.25 for rid in rids]
    rid = int(rng.choices(rids, weights=weights, k=1)[0])
    candidates = proposer.candidate_routes(
        rid, profile=profile, sample=int(proposer.cfg['quicks']))
    if not candidates:
        return None
    before_bad, before_def = evaluator.before_single(rid)
    scored = []
    seen = set()
    for label, new_route, mode in candidates:
        key = _route_key(new_route)
        if key in seen:
            continue
        seen.add(key)
        quick = evaluator.quick(rid, new_route)
        proposer.stats['quick_evals'] += 1
        if not quick['ok']:
            proposer.stats['quick_hard_reject'] += 1
            continue
        delta_bad = len(quick['violations']) - before_bad
        delta_def = quick['deficit'] - before_def
        energy = evaluator.energy_delta(delta_bad, delta_def)
        scored.append((energy, delta_bad, delta_def, label, new_route, mode))
        proposer.stats['quick_ok'] += 1
    if not scored:
        return None
    scored.sort(key=lambda item: item[0])
    # epsilon-greedy: sometimes take a random candidate instead of the best
    if len(scored) > 1 and rng.random() < 0.18:
        pick = rng.randrange(len(scored))
    else:
        pick = 0
    # full validation of the best (and a couple of fallbacks)
    order = [pick] + [index for index in range(len(scored)) if index != pick]
    for index in order[:int(proposer.cfg['fulls'])]:
        energy, delta_bad, delta_def, label, new_route, mode = scored[index]
        transitions = mode != 'body'
        full = evaluator.full(rid, new_route,
                              transitions_changed=transitions)
        proposer.stats['full_evals'] += 1
        if not full['ok']:
            proposer.stats['full_hard_reject'] += 1
            continue
        true_bad = len(full['violations']) - before_bad
        true_def = full['deficit'] - before_def
        return Move('single:' + mode, {rid: new_route},
                    label=f'{label}|{mode}',
                    changed_transitions=transitions), \
            evaluator.energy_delta(true_bad, true_def), true_bad, true_def
    return None


def _route_key(route):
    """Cheap geometry key of a rebuilt route (body primitive signature)."""
    body_index = None
    dissected = GEO.dissect_route(route)
    if dissected is not None:
        body_index = dissected['body_index']
    parts = route.get('parts') or ()
    if body_index is None or body_index >= len(parts):
        return tuple()
    return GEO.body_signature(parts[body_index].get('primitives'))


# ---------------------------------------------------------------------------
# pair move (N2 / N5 joint)
# ---------------------------------------------------------------------------
def propose_pair(proposer, profile='E'):
    state = proposer.state
    evaluator = proposer.evaluator
    rng = proposer.rng
    events = list(state.violations)
    if not events:
        return None
    weights = [max(0.0, 45.0 - event['angle_deg']) + 0.5 for event in events]
    event = rng.choices(events, weights=weights, k=1)[0]
    ids = [int(event['route_a']), int(event['route_b'])]
    pool = {}
    for rid in ids:
        if not proposer.regenerable(rid):
            continue
        routes = proposer.candidate_routes(
            rid, profile='E' if profile == 'E' else profile,
            sample=max(2, int(proposer.cfg['pair_quicks']) * 2))
        legal = []
        for label, route, mode in routes:
            quick = evaluator.quick(rid, route)
            proposer.stats['quick_evals'] += 1
            if quick['ok']:
                legal.append((label, route, mode))
        if legal:
            pool[rid] = legal
    if len(pool) < 2:
        return None
    before_bad, before_def = evaluator.before_batch(ids)
    best = None
    attempts = int(proposer.cfg['pair_attempts'])
    for _attempt in range(attempts):
        batch = {}
        labels = []
        for rid, routes in pool.items():
            label, route, mode = routes[rng.randrange(len(routes))]
            batch[rid] = route
            labels.append(f'{rid}:{mode}:{label}')
        result = evaluator.batch(batch)
        proposer.stats['batch_evals'] += 1
        if not result['ok']:
            proposer.stats['batch_hard_reject'] += 1
            continue
        energy = evaluator.energy_delta(result['delta_bad'],
                                        result['delta_deficit'])
        if best is None or energy < best[0]:
            best = (energy, result['delta_bad'], result['delta_deficit'],
                    batch, '+'.join(labels))
    if best is None:
        return None
    return (Move('pair:joint', best[3], label=best[4],
                 changed_transitions=True),
            best[0], best[1], best[2])


# ---------------------------------------------------------------------------
# group move (N3 / N6)
# ---------------------------------------------------------------------------
def violation_components(state):
    """Connected components of the route graph induced by current violations."""
    adjacency = defaultdict(set)
    for event in state.violations:
        a, b = int(event['route_a']), int(event['route_b'])
        adjacency[a].add(b)
        adjacency[b].add(a)
    seen = set()
    components = []
    for start in adjacency:
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        comp = []
        while stack:
            node = stack.pop()
            comp.append(node)
            for other in adjacency[node]:
                if other not in seen:
                    seen.add(other)
                    stack.append(other)
        components.append(sorted(comp))
    components.sort(key=len, reverse=True)
    return components


def propose_group(proposer, profile='E'):
    state = proposer.state
    evaluator = proposer.evaluator
    rng = proposer.rng
    components = violation_components(state)
    if not components:
        return None
    # prefer the components with the largest deficit / most violations
    weights = []
    for comp in components:
        deficit = sum(state.per_route_deficit.get(rid, 0.0) for rid in comp)
        weights.append(deficit + 1.0)
    comp = rng.choices(components, weights=weights, k=1)[0]
    usable = [rid for rid in comp if proposer.regenerable(rid)]
    if not usable:
        return None
    size = min(len(usable), int(proposer.cfg['group_max']))
    if size > 2 and rng.random() < 0.5:
        size = max(2, rng.randint(2, size))
    ids = rng.sample(usable, min(size, len(usable)))
    if len(ids) < 2:
        return None
    # candidate options for every route in the group
    options = {}
    for rid in ids:
        routes = proposer.candidate_routes(
            rid, profile='E' if profile == 'E' else profile, sample=2)
        if routes:
            options[rid] = routes
    if len(options) < 2:
        return None
    before_bad, before_def = evaluator.before_batch(ids)
    best = None
    for _attempt in range(int(proposer.cfg['group_attempts'])):
        batch = {}
        labels = []
        for rid, routes in options.items():
            label, route, mode = routes[rng.randrange(len(routes))]
            batch[rid] = route
            labels.append(f'{rid}:{mode}')
        result = evaluator.batch(batch)
        proposer.stats['batch_evals'] += 1
        if not result['ok']:
            proposer.stats['batch_hard_reject'] += 1
            continue
        energy = evaluator.energy_delta(result['delta_bad'],
                                        result['delta_deficit'])
        if best is None or energy < best[0]:
            best = (energy, result['delta_bad'], result['delta_deficit'],
                    batch, 'group:' + ','.join(labels))
    if best is None:
        return None
    return (Move('group:joint', best[3], label=best[4],
                 changed_transitions=True),
            best[0], best[1], best[2])


# ---------------------------------------------------------------------------
# height kick (N4: several routes re-heighted at once)
# ---------------------------------------------------------------------------
def propose_kick(proposer, profile='E'):
    """N4: several routes re-heighted *simultaneously* (atomic batch).

    This is the direct answer to G5's measured blocker: the CP-SAT/DSATUR layer
    assignment was abstract because the R15 transitions were never rebuilt.
    Here every route of the batch gets a real, exactly rebuilt transition pair
    (cheap g5 closure candidates) and the whole batch is evaluated atomically.
    """
    state = proposer.state
    evaluator = proposer.evaluator
    rng = proposer.rng
    if not state.per_route:
        return None
    components = violation_components(state)
    comp = components[0] if components else []
    usable = [rid for rid in comp if proposer.regenerable(rid)
              and proposer.dissections[rid]['kind'] == 'lifted']
    if len(usable) < 2:
        usable = [rid for rid in state.per_route
                  if proposer.regenerable(rid)
                  and proposer.dissections[rid]['kind'] == 'lifted']
    if len(usable) < 2:
        return None
    size = min(len(usable), rng.randint(2, 4))
    ids = rng.sample(usable, size)
    before_bad, before_def = evaluator.before_batch(ids)
    best = None
    for _attempt in range(int(proposer.cfg['kick_attempts'])):
        batch = {}
        labels = []
        for rid in ids:
            options = proposer.cheap_reheight_candidates(rid, sample=2)
            if not options:
                options = proposer.candidate_routes(rid, profile='D', sample=1)
            if not options:
                continue
            label, route, mode = options[rng.randrange(len(options))]
            batch[rid] = route
            labels.append(f'{rid}:{mode}:{label}')
        if len(batch) < 2:
            continue
        result = evaluator.batch(batch)
        proposer.stats['batch_evals'] += 1
        if not result['ok']:
            proposer.stats['batch_hard_reject'] += 1
            continue
        energy = evaluator.energy_delta(result['delta_bad'],
                                        result['delta_deficit'])
        if best is None or energy < best[0]:
            best = (energy, result['delta_bad'], result['delta_deficit'],
                    batch, 'kick:' + ','.join(labels))
    if best is None:
        return None
    return (Move('kick:reheight', best[3], label=best[4],
                 changed_transitions=True),
            best[0], best[1], best[2])


def propose(proposer, profile='E', mix=None):
    """Draw one move according to the neighbourhood mix of the profile."""
    rng = proposer.rng
    if mix is None:
        mix = profile_mix(profile)
    draw = rng.random()
    for name, weight in mix:
        if draw < weight:
            kind = name
            break
        draw -= weight
    else:  # pragma: no cover
        kind = mix[-1][0]
    if kind == 'single':
        return propose_single(proposer, profile)
    if kind == 'pair':
        return propose_pair(proposer, profile)
    if kind == 'group':
        return propose_group(proposer, profile)
    return propose_kick(proposer, profile)


def profile_mix(profile):
    """Neighbourhood mixture of the experiment profiles B..E.

    B : N1 (single MultiArc regeneration) only
    C : N1 + N2 (two-route joint MultiArc regeneration)
    D : C + N4/N5 (single-route re-height / lead-out joint reconstruction)
    E : D + N3 (multi-route group) + N6 (multi-route height kick)
    """
    profile = str(profile).upper()
    if profile == 'B':
        return [('single', 1.0)]
    if profile == 'C':
        return [('single', 0.80), ('pair', 0.20)]
    if profile == 'D':
        return [('single', 0.78), ('pair', 0.12), ('kick', 0.10)]
    return [('single', 0.70), ('pair', 0.10), ('group', 0.10),
            ('kick', 0.10)]
