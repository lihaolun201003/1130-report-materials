# -*- coding: utf-8 -*-
"""G6 last-mile polish: exhaustive targeted MultiArc repair of the residual set.

The SA kernel is stochastic and plateaus a few violations short of zero.  This
deterministic stage attacks the residual violations one by one with a much
larger candidate budget than the SA proposal loop:

for every remaining sub-45 event ``(a, b)``
  1. enumerate **all** legal MultiArc bodies of ``a`` (the full frozen layer2d
     grammar), plus re-height / lead-out / direct-lift variants;
  2. for every such candidate, quick-evaluate (structure + D56 + exact angle)
     and keep the ones that are legal against the current world;
  3. do the same for ``b``;
  4. evaluate the promising ``(a', b')`` pairs atomically with the G5 batch
     evaluator (the only move class that can fix a pair whose *single* moves are
     individually illegal, exactly the G5 T2/T3 case);
  5. commit the best move that strictly decreases the global violation count.

Every iteration is a real, hard-constraint-checked geometry change; the loop
stops when no event can be improved (and then reports, per event, how many
single/pair candidates were tried and why they were rejected).
"""
from __future__ import annotations

import copy
import json
import math
import os
import random
import time
from collections import Counter

from . import geometry as GEO
from . import neighborhoods as NB

THETA = 45.0


def _quick_key(result):
    return (len(result['violations']), round(result['deficit'], 6))


class Polisher:
    def __init__(self, state, proposer, evaluator, rng, cfg=None, log=print):
        self.state = state
        self.proposer = proposer
        self.evaluator = evaluator
        self.rng = rng
        default_cfg = dict(
            body_build=500,           # full MultiArc enumeration cap
            pose_variants=6,          # extra (height, lead) poses per route
            pose_build=120,
            pair_keep=10,             # per-side shortlist for atomic pairs
            pair_attempts=160,        # atomic batch evaluations per event
            passes=6,
            seconds=1800.0,
        )
        default_cfg.update(cfg or {})
        self.cfg = default_cfg
        self.log = log
        self._cache = {}
        self.stats = Counter()
        self.history = []

    # ------------------------------------------------------------ candidates
    def _assemble_body_candidates(self, rid):
        """All legal body-only MultiArc routes for one route (cached)."""
        key = (int(rid),)
        if key in self._cache:
            return self._cache[key]
        route = self.state.world.routes[int(rid)]
        dissected = self.proposer.dissections.get(int(rid))
        if dissected is None or int(rid) in self.proposer.manual:
            self._cache[key] = []
            return []
        frame, specs, error = GEO.enumerate_specs(dissected, route)
        out = []
        if frame is not None:
            bodies = GEO.build_bodies(frame, specs,
                                      max_build=int(self.cfg['body_build']))
            for family, params, world in bodies:
                if not GEO.L2._self_clearance_ok(world):
                    continue
                if dissected['kind'] == 'direct':
                    new_route = GEO.assemble_direct(route, dissected,
                                                    dissected['z_body'], world)
                else:
                    new_route = GEO.with_body(route, dissected, world)
                if new_route is not None:
                    out.append((f'body:{family}', new_route, 'body'))
        self.stats['body_candidates'] += len(out)
        self._cache[key] = out
        return out

    def _assemble_pose_candidates(self, rid):
        """Re-height / lead-out / lift candidates sampled around one route."""
        key = ('poses', int(rid))
        if key in self._cache:
            return self._cache[key]
        route = self.state.world.routes[int(rid)]
        dissected = self.proposer.dissections.get(int(rid))
        out = []
        if dissected is None or int(rid) in self.proposer.manual:
            self._cache[key] = out
            return out
        heights = [z for z in self.proposer.allowed_heights(int(rid))]
        if not heights:
            self._cache[key] = out
            return out
        plans = []
        if dissected['kind'] == 'direct':
            for z_body in self.rng.sample(heights,
                                          min(len(heights),
                                              int(self.cfg['pose_variants']))):
                for leads in ((0.25, 0.25), (1.0, 2.0)):
                    plans.append(dict(mode='reheight', z_body=z_body,
                                      lead_s=leads[0], lead_t=leads[1]))
        else:
            near = sorted(heights, key=lambda z: abs(z - dissected['z_body']))
            for z_body in near[:int(self.cfg['pose_variants'])]:
                plans.append(dict(mode='reheight', z_body=z_body,
                                  lead_s=dissected['lead_s'],
                                  lead_t=dissected['lead_t']))
            for leads in ((0.25, 1.0), (1.0, 0.25), (2.0, 2.0)):
                plans.append(dict(mode='lead', z_body=dissected['z_body'],
                                  lead_s=leads[0], lead_t=leads[1]))
        seen = set()
        for plan in plans:
            pose = GEO.body_pose(dissected, z_body=plan['z_body'],
                                 lead_s=plan['lead_s'], lead_t=plan['lead_t'])
            frame, specs, error = GEO.enumerate_specs(
                dissected, route, pose=pose)
            if frame is None:
                continue
            bodies = GEO.build_bodies(
                frame, specs, max_build=int(self.cfg['pose_build']),
                rng=self.rng)
            for family, params, world in bodies:
                if not GEO.L2._self_clearance_ok(world):
                    continue
                new_route = GEO.assemble_lifted(
                    route, dissected, plan['z_body'], plan['lead_s'],
                    plan['lead_t'], world, pose=pose)
                if new_route is None:
                    continue
                signature = GEO.body_signature(world)
                if signature in seen:
                    continue
                seen.add(signature)
                out.append((f'{plan["mode"]}:{family}:z={plan["z_body"]:+.3f}',
                            new_route, plan['mode']))
        self.stats['pose_candidates'] += len(out)
        self._cache[key] = out
        return out

    def candidates(self, rid):
        return (self._assemble_body_candidates(rid) +
                self._assemble_pose_candidates(rid))

    # ------------------------------------------------------------ evaluation
    def _quick_legal(self, rid, candidates, event_routes):
        """Quick-evaluate candidates; keep legal ones, sorted by local score."""
        before_bad, before_def = self.evaluator.before_single(rid)
        legal = []
        for label, new_route, mode in candidates:
            quick = self.evaluator.quick(rid, new_route)
            self.stats['quick_evals'] += 1
            if not quick['ok']:
                self.stats['quick_hard_reject'] += 1
                continue
            delta_bad = len(quick['violations']) - before_bad
            delta_def = quick['deficit'] - before_def
            energy = self.evaluator.energy_delta(delta_bad, delta_def)
            legal.append((energy, delta_bad, delta_def, label, new_route,
                          mode))
        legal.sort(key=lambda item: item[0])
        self.stats['quick_legal'] += len(legal)
        return legal

    def _try_single(self, rid):
        """Best single-route repair; returns ``(move, energy, dbad, ddef)``."""
        candidates = self.candidates(rid)
        legal = self._quick_legal(rid, candidates, None)
        for energy, delta_bad, delta_def, label, new_route, mode in legal:
            if delta_bad > 0:
                continue
            full = self.evaluator.full(rid, new_route,
                                       transitions_changed=(mode != 'body'))
            self.stats['full_evals'] += 1
            if not full['ok']:
                self.stats['full_hard_reject'] += 1
                continue
            before_bad, before_def = self.evaluator.before_single(rid)
            dbad = len(full['violations']) - before_bad
            ddef = full['deficit'] - before_def
            if dbad < 0:
                move = NB.Move('polish:single', {int(rid): new_route},
                               label=f'{label}|{mode}',
                               changed_transitions=(mode != 'body'))
                return move, self.evaluator.energy_delta(dbad, ddef), dbad, ddef
        return None

    def _try_pair(self, rid_a, rid_b):
        legal_a = [item for item in self._quick_legal(
            rid_a, self.candidates(rid_a), None) if item[1] <= 0]
        legal_b = [item for item in self._quick_legal(
            rid_b, self.candidates(rid_b), None) if item[1] <= 0]
        if not legal_a or not legal_b:
            return None
        keep = int(self.cfg['pair_keep'])
        short_a = legal_a[:keep]
        short_b = legal_b[:keep]
        before_bad, before_def = self.evaluator.before_batch([rid_a, rid_b])
        best = None
        attempts = 0
        for _ea, _da, _dda, label_a, route_a, mode_a in short_a:
            for _eb, _db, _ddb, label_b, route_b, mode_b in short_b:
                if attempts >= int(self.cfg['pair_attempts']):
                    break
                attempts += 1
                batch = {int(rid_a): route_a, int(rid_b): route_b}
                result = self.evaluator.batch(batch)
                self.stats['batch_evals'] += 1
                if not result['ok']:
                    self.stats['batch_hard_reject'] += 1
                    continue
                if result['delta_bad'] >= 0:
                    continue
                energy = self.evaluator.energy_delta(
                    result['delta_bad'], result['delta_deficit'])
                if best is None or energy < best[1]:
                    best = (NB.Move('polish:pair', batch,
                                    label=f'{label_a}+{label_b}',
                                    changed_transitions=True),
                            energy, result['delta_bad'],
                            result['delta_deficit'])
            if attempts >= int(self.cfg['pair_attempts']):
                break
        return best

    # ------------------------------------------------------------- main loop
    def _apply(self, move):
        if len(move.routes) == 1:
            rid, new_route = next(iter(move.routes.items()))
            old_route = copy.deepcopy(self.state.world.routes[rid])
            info = self.state.apply(rid, new_route)
            if info['issues']:
                self.state.apply(rid, old_route)
                return False
            self.proposer.refresh_route(rid)
            self._cache = {}
            return True
        result = NB.B5.commit_batch(self.state, move.routes)
        if not result.get('ok'):
            return False
        for rid in move.routes:
            self.proposer.refresh_route(rid)
        self._cache = {}
        return True

    def run(self, seconds=None, passes=None):
        deadline = time.time() + float(seconds or self.cfg['seconds'])
        passes = int(passes or self.cfg['passes'])
        events_detail = []
        for _pass in range(passes):
            improved = False
            events = sorted(self.state.violations,
                            key=lambda event: event['angle_deg'])
            if not events:
                break
            for event in events:
                if time.time() > deadline:
                    self.log('[polish] time budget reached')
                    break
                a, b = int(event['route_a']), int(event['route_b'])
                detail = dict(route_a=a, route_b=b,
                              z=round(float(event['z']), 6),
                              x=round(float(event['x']), 6),
                              y=round(float(event['y']), 6),
                              angle_deg=round(float(event['angle_deg']), 6))
                move = self._try_pair(a, b)
                kind = 'pair'
                if move is None:
                    best_single = None
                    for rid in (a, b):
                        if not self.proposer.regenerable(rid):
                            continue
                        candidate = self._try_single(rid)
                        if candidate is not None and (
                                best_single is None or
                                candidate[1] < best_single[1]):
                            best_single = candidate
                    move = best_single
                    kind = 'single'
                if move is None:
                    detail['result'] = 'no_improving_move'
                    events_detail.append(detail)
                    continue
                move_obj, energy, dbad, ddef = move
                if not self._apply(move_obj):
                    detail['result'] = 'commit_rejected'
                    events_detail.append(detail)
                    continue
                detail.update(result='repaired', kind=kind,
                              delta_bad=int(dbad),
                              delta_deficit=round(float(ddef), 6),
                              label=move_obj.label,
                              n_bad_after=int(self.state.n_violations),
                              deficit_after=round(self.state.deficit(), 6))
                events_detail.append(detail)
                self.history.append(detail)
                self.log('[polish] %s %s -> N_bad=%d D=%.3f (%s)'
                         % (kind, detail['label'][:80],
                            self.state.n_violations, self.state.deficit(),
                            detail['result']))
                improved = True
                break
            if not improved:
                self.log('[polish] pass %d: no event could be improved'
                         % (_pass + 1))
                break
        return dict(
            schema='g6_polish_v1',
            n_bad=int(self.state.n_violations),
            deficit=round(float(self.state.deficit()), 6),
            crossings=int(len(self.state.crossings)),
            length_mm=round(float(self.state.length), 6),
            hard_issues=len(self.state.hard_issues),
            events=events_detail, history=self.history,
            stats=dict(self.stats),
            seconds_remaining=round(deadline - time.time(), 3),
        )
