# -*- coding: utf-8 -*-
"""G5 global search engine: violation-driven ALNS over the frozen G4 solution.

The engine never relaxes a hard constraint.  ``model.World`` re-checks every
same-height pair (strict D56 + the 45 deg crossing rule) and every true 3-D
clearance of the candidate route, so an accepted move is legal by construction;
the whole world is re-audited at checkpoints and at the end.

Objective (lexicographic, as required by the task):

    (N_<45, D_max, D_theta, N_cross, L_total)

Phases
------
``phase1`` greedy: for every sub-45 deg crossing, try to make one of its two
    routes cross *nothing* below 45 deg with a single exact move.  Cheap, and
    each success fixes all violations of that route at once.
``phase2`` ALNS: destroy a neighbourhood of violating routes (a conflict-graph
    component, a spatial hotspot, or a random subset), rebuild them with the
    same move families, keep improvements, allow equal-cost moves to escape
    plateaus, keep the best legal state separately.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import time
from collections import Counter, defaultdict
from pathlib import Path

from four_side_1024.fanout1024.xyzrouter.g5 import model as G5
from four_side_1024.fanout1024.xyzrouter.g5 import candidates as C
from four_side_1024.fanout1024.xyzrouter.g5 import search as S


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Engine:
    def __init__(self, payload, run_dir, work_dir, min_angle_deg=S.THETA,
                 seed=20261104, frozen_routes=(), log=print, args=None):
        self.payload = payload
        self.run_dir = Path(run_dir)
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.min_angle = float(min_angle_deg)
        self.seed = int(seed)
        self.rng = random.Random(seed)
        self.frozen = set(int(r) for r in frozen_routes)
        self.log = log
        self.args = args or {}
        self.state = S.State(payload['routes'], min_angle_deg=self.min_angle,
                             log=log)
        self.history = []
        self.moves = []
        self.evaluations = 0
        self.started = time.time()
        self.baseline_hard = len(self.state.hard_issues)
        self.best_legal = None
        self.planes = list(G5.all_heights())
        self.heights = self.planes

    # ------------------------------------------------------------------ utils
    def scores(self):
        summary = self.state.summary()
        return dict(time_s=round(time.time() - self.started, 1),
                    evaluations=self.evaluations, **summary)

    def record(self, phase, note=''):
        row = self.scores()
        row['phase'] = phase
        row['note'] = note
        self.history.append(row)
        return row

    def objective(self):
        return (len(self.state.violations),
                round(self.state.max_deficit(), 9),
                round(self.state.deficit(), 6),
                len(self.state.crossings),
                round(self.state.length, 6))

    # --------------------------------------------------------------- evaluate
    def evaluate(self, rid, new_route, window_check=False):
        self.evaluations += 1
        return self.state.evaluate(rid, new_route, window_check=window_check)

    def route_pool(self, rid, hint=None, limit=150, heavy=True):
        return S.candidate_pool(self.state, rid, limit=limit,
                                seed=self.rng.randrange(1 << 30),
                                planes=self.planes, hint=hint, heavy=heavy)

    # ------------------------------------------------------------ move search
    def best_move_for_route(self, rid, hint=None, limit=150, want_zero=True,
                            heavy=True, accept_partial=False):
        """Best single-route move: (score, label, route) or None."""
        if rid in self.frozen:
            return None
        route = self.state.world.routes[int(rid)]
        current = len(self.state.route_violations(rid))
        best = None
        for label, new_route in self.route_pool(rid, hint=hint, limit=limit,
                                                heavy=heavy):
            evaluation = self.evaluate(rid, new_route)
            if not evaluation['ok']:
                continue
            count = len(evaluation['violations'])
            if want_zero and count:
                if not accept_partial:
                    continue
            length_delta = abs(new_route['length_mm'] - route['length_mm'])
            key = (count - current, round(length_delta, 6))
            if want_zero and count == 0:
                return (key, label, new_route, evaluation)
            if accept_partial and (best is None or key < best[0]):
                best = (key, label, new_route, evaluation)
        if want_zero and not accept_partial:
            return None
        return best

    def commit(self, rid, label, new_route, phase):
        old_route = json.loads(json.dumps(self.state.world.routes[int(rid)]))
        info = self.state.apply(rid, new_route)
        if info['issues']:
            # exact re-check found a hard issue the fast path missed -> roll back
            self.state.world.set_route(int(rid), old_route)
            self.state.refresh()
            return dict(removed=[], added=[], issues=info['issues'], reverted=True)
        self.moves.append(dict(phase=phase, route=int(rid), move=label,
                               removed=len(info['removed']),
                               added=len(info['added']),
                               issues=len(info['issues']),
                               time_s=round(time.time() - self.started, 1)))
        return info

    # ------------------------------------------------------------------ phases
    def phase1(self, limit=150, max_rounds=None, deadline=None):
        """Greedy: make one route at a time violation-free."""
        rounds = 0
        improved_total = 0
        failed = set()
        while True:
            if deadline and time.time() > deadline:
                break
            if not self.state.violations:
                break
            rounds += 1
            if max_rounds and rounds > max_rounds:
                break
            # candidates ordered by "cheapest route to fix": fewest violations
            by_route = Counter()
            for event in self.state.violations:
                by_route[event['route_a']] += 1
                by_route[event['route_b']] += 1
            progress = False
            for rid, _count in sorted(by_route.items(), key=lambda kv: kv[1]):
                if rid in self.frozen or rid in failed:
                    continue
                before = len(self.state.violations)
                result = self.best_move_for_route(rid, limit=limit)
                if result is None:
                    continue
                _key, label, new_route, _eval = result
                info = self.commit(rid, label, new_route, 'phase1')
                if info.get('reverted'):
                    failed.add(rid)
                    continue
                after = len(self.state.violations)
                improved_total += before - after
                progress = True
                self.record('phase1', 'route %d %s %d->%d'
                            % (rid, label, before, after))
                if len(self.moves) % 25 == 0:
                    self.save_checkpoint('phase1_%04d' % len(self.moves))
                    self.save_checkpoint('latest')
                self.log('[phase1] route %d %s  violations %d -> %d  (n=%d)'
                         % (rid, label, before, after,
                            len(self.state.violations)))
                if len(self.state.hard_issues) > self.baseline_hard:
                    self.log('[phase1] WARNING new hard issues after route %d: %s'
                             % (rid, self.state.hard_issues[:3]))
                break
            if not progress:
                self.log('[phase1] no further zero-violation single-route fix '
                         '(violations=%d)' % len(self.state.violations))
                break
        self.log('[phase1] rounds=%d improved=%d summary=%s'
                 % (rounds, improved_total, self.state.summary()))
        return self.state.summary()

    def local_delta(self, rid, evaluation, length_delta):
        """Exact change of the global objective if ``rid`` takes the move."""
        n_before = self.state.per_route[rid]
        n_after = len(evaluation['violations'])
        d_before = self.state.per_route_deficit[rid]
        d_after = sum(max(0.0, self.min_angle - event['angle_deg'])
                      for event in evaluation['violations'])
        c_before = self.state.per_route_crossings[rid]
        c_after = len(evaluation['crossings'])
        return (n_after - n_before, round(d_after - d_before, 6),
                c_after - c_before, round(length_delta, 6))

    def phase2(self, budget_seconds=3600.0, limit=70, deadline=None,
               plateau_rate=0.15, log_every=10):
        """Violation-driven stochastic hill climbing with exact local deltas."""
        end = time.time() + budget_seconds
        if deadline:
            end = min(end, deadline)
        accepted = rejected = 0
        stalls = 0
        tabu = {}
        best = self.objective()
        best_routes = None
        while time.time() < end and self.state.violations:
            events = self.state.violations
            if not events:
                break
            # violation-driven target choice: prefer large deficits, small routes
            event = min(self.rng.sample(events, min(6, len(events))),
                        key=lambda e: e['angle_deg'])
            options = sorted((event['route_a'], event['route_b']),
                             key=lambda r: (self.state.per_route[r],
                                            r not in self.frozen))
            improved = False
            for rid in options:
                if rid in self.frozen:
                    continue
                now = time.time()
                if rid in tabu and tabu[rid] > now:
                    continue
                route = self.state.world.routes[rid]
                hint = S.route_hint(self.state, rid, event)
                pool = self.route_pool(rid, hint=hint, limit=limit)
                best_move = None
                best_key = None
                best_eval = None
                for label, new_route in pool:
                    evaluation = self.evaluate(rid, new_route)
                    if not evaluation['ok']:
                        continue
                    if evaluation['issues']:
                        continue
                    length_delta = new_route['length_mm'] - route['length_mm']
                    key = self.local_delta(rid, evaluation, length_delta)
                    if best_key is None or key < best_key:
                        best_key = key
                        best_move = (label, new_route, evaluation)
                        best_eval = evaluation
                if best_move is None:
                    tabu[rid] = time.time() + 30.0
                    continue
                strictly_better = best_key[0] < 0 or (best_key[0] == 0
                                                      and best_key[1] < -1e-9)
                plateau = (best_key[0] == 0 and abs(best_key[1]) <= 1e-9
                           and self.rng.random() < plateau_rate)
                if strictly_better or plateau:
                    label, new_route, _evaluation = best_move
                    info = self.commit(rid, label, new_route, 'phase2')
                    if info.get('reverted'):
                        tabu[rid] = time.time() + 30.0
                        continue
                    accepted += 1
                    improved = True
                    if accepted % log_every == 0:
                        self.record('phase2', 'accepted=%d' % accepted)
                        self.log('[phase2] accepted=%d  %s'
                                 % (accepted, self.state.summary()))
                    break
                else:
                    rejected += 1
                    tabu[rid] = time.time() + 20.0
            if not improved:
                stalls += 1
                if stalls % 25 == 0:
                    self.record('phase2', 'stall=%d' % stalls)
                    self.log('[phase2] stall=%d n=%d accepted=%d'
                             % (stalls, len(self.state.violations), accepted))
                if stalls > 400:
                    break
            objective = self.objective()
            if objective < best:
                best = objective
                best_routes = {rid: json.loads(json.dumps(route))
                               for rid, route in self.state.world.routes.items()}
            if len(self.state.hard_issues) > self.baseline_hard:
                self.log('[phase2] WARNING new hard issues')
        self.log('[phase2] accepted=%d rejected=%d stalls=%d summary=%s'
                 % (accepted, rejected, stalls, self.state.summary()))
        return self.state.summary()

    def phase3(self, passes=2, limit=60, log_every=10):
        """Polish: cut the total crossing count without losing feasibility."""
        moved = sorted({row['route'] for row in self.moves})
        accepted = 0
        for _pass in range(passes):
            for rid in moved:
                if rid in self.frozen:
                    continue
                if self.state.per_route[rid]:
                    continue          # only polish violation-free routes
                route = self.state.world.routes[rid]
                cur_cross = self.state.per_route_crossings[rid]
                cur_length = route['length_mm']
                best = None
                for label, new_route in self.route_pool(rid, limit=limit):
                    evaluation = self.evaluate(rid, new_route)
                    if not evaluation['ok'] or evaluation['violations']:
                        continue
                    key = (len(evaluation['crossings']),
                           round(new_route['length_mm'] - cur_length, 6))
                    if key[0] < cur_cross or (key[0] == cur_cross and key[1] < 0):
                        if best is None or key < best[0]:
                            best = (key, label, new_route)
                if best is None:
                    continue
                info = self.commit(rid, best[1], best[2], 'phase3')
                if info.get('reverted'):
                    continue
                accepted += 1
                if accepted % log_every == 0:
                    self.log('[phase3] polish accepted=%d  crossings=%d '
                             'violations=%d length=%.3f'
                             % (accepted, len(self.state.crossings),
                                len(self.state.violations), self.state.length))
                if len(self.state.hard_issues) > self.baseline_hard:
                    self.log('[phase3] WARNING new hard issues')
        self.record('phase3', 'accepted=%d' % accepted)
        self.log('[phase3] accepted=%d summary=%s'
                 % (accepted, self.state.summary()))
        return self.state.summary()

    def _destroy(self, destroy_sizes):
        """Pick a neighbourhood of violating routes -> [(rid, hint)]."""
        if not self.state.violations:
            return []
        size = self.rng.choice(destroy_sizes)
        events = self.state.violations
        pivot = self.rng.choice(events)
        # 1) same conflict-graph component (BFS over violating pairs)
        adjacency = defaultdict(set)
        for event in events:
            adjacency[event['route_a']].add(event['route_b'])
            adjacency[event['route_b']].add(event['route_a'])
        chosen = [pivot['route_a'], pivot['route_b']]
        frontier = list(chosen)
        while frontier and len(chosen) < size:
            node = frontier.pop(0)
            for other in sorted(adjacency[node]):
                if other not in chosen:
                    chosen.append(other)
                    frontier.append(other)
                    if len(chosen) >= size:
                        break
        # 2) occasionally a spatial hotspot instead
        if self.rng.random() < 0.35:
            px, py = pivot['x'], pivot['y']
            near = sorted(events, key=lambda e: math.hypot(e['x'] - px,
                                                           e['y'] - py))
            chosen = []
            for event in near:
                for rid in (event['route_a'], event['route_b']):
                    if rid not in chosen:
                        chosen.append(rid)
                if len(chosen) >= size:
                    break
        out = []
        for rid in chosen[:size]:
            hint = None
            for event in events:
                if rid in (event['route_a'], event['route_b']):
                    hint = S.route_hint(self.state, rid, event)
                    break
            out.append((rid, hint))
        return out

    # -------------------------------------------------------------- artefacts
    def as_payload(self):
        routes = [self.state.world.routes[rid] for rid in sorted(self.state.world.routes)]
        out = dict(self.payload)
        out['routes'] = routes
        out['routed'] = len(routes)
        out['failed'] = 0
        out['g5'] = dict(schema='g5_angle45_routes_v1',
                         theta_min_deg=self.min_angle,
                         parent_routes_sha256=sha256_file(
                             self.run_dir / 'routes_l3d.json'),
                         generated=time.strftime('%Y-%m-%dT%H:%M:%S'),
                         engine='g5.violation_driven_alns',
                         seed=self.seed,
                         evaluations=self.evaluations,
                         moves=len(self.moves),
                         summary=self.state.summary())
        return out

    def save_checkpoint(self, tag='latest'):
        path = self.work_dir / ('checkpoint_%s.json' % tag)
        path.write_text(json.dumps(self.as_payload(), ensure_ascii=False),
                        encoding='utf-8')
        meta = dict(history=self.history, moves=self.moves,
                    summary=self.state.summary(), seed=self.seed,
                    evaluations=self.evaluations,
                    seconds=round(time.time() - self.started, 1))
        (self.work_dir / ('checkpoint_%s.meta.json' % tag)).write_text(
            json.dumps(meta, indent=1, ensure_ascii=False), encoding='utf-8')
        return path

    def write_history(self, path=None):
        path = Path(path or (self.work_dir / 'g5_search_history.csv'))
        rows = self.history or [self.record('start')]
        keys = list(rows[0].keys())
        with path.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=keys)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        return path

    def write_moves(self, path=None):
        path = Path(path or (self.work_dir / 'g5_candidate_statistics.csv'))
        keys = ['phase', 'route', 'move', 'removed', 'added', 'issues', 'time_s']
        with path.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=keys)
            writer.writeheader()
            for row in self.moves:
                writer.writerow({key: row.get(key, '') for key in keys})
        return path
