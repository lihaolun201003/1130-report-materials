# -*- coding: utf-8 -*-
"""G6 simulated-annealing kernel for angle-aware MultiArc routing.

Energy (only the 45 deg rule enters the objective):

    E(S) = M * N_bad(S) + lambda * D_theta(S)

where ``N_bad`` is the number of genuine same-height crossings below 45 deg and
``D_theta`` the summed angle deficit in degrees.  ``M`` (default 1000) makes one
violating crossing dominate any deficit change, so ``N_bad`` is optimised first
and ``lambda`` only steers *how* the violations are removed.

Hard manufacturing constraints (D56, R15, glass, true-3-D clearance, self
clearance, structure) are never part of the energy: a move that violates any of
them is discarded outright (``neighborhoods.Evaluator``).

The acceptance rule is the exact Metropolis rule on ``E``:

    P_accept = min(1, exp(-dE / T))

so a move that temporarily adds a violating crossing *is* accepted with
positive probability, which is exactly the local-minimum escape G5 lacked.
"""
from __future__ import annotations

import copy
import json
import math
import os
import random
import time
from collections import Counter, defaultdict

from . import geometry as GEO
from . import neighborhoods as NB
from ..g5 import model as G5
from ..g5 import batch as B5
from ..g5 import search as S5

DEFAULT_CFG = dict(
    theta=45.0,
    M=1000.0,
    lam=1.0,
    seed=0,
    profile='E',
    # temperature: initial / final (energy units) and adaptive control
    T0=1200.0,
    T_end=45.0,
    reheat_after_seconds=240.0,
    reconcile_seconds=420.0,
    checkpoint_seconds=300.0,
    best_min_interval=15.0,
    log_seconds=20.0,
)


def _now():
    return time.time()


def _stamp():
    return time.strftime('%Y-%m-%dT%H:%M:%S')


class G6SA:
    """Angle-aware MultiArc simulated annealing over the frozen route payload."""

    def __init__(self, doc, out_dir, cfg=None, log=None, resume_dir=None):
        self.cfg = dict(DEFAULT_CFG, **(cfg or {}))
        self.doc = doc
        self.out_dir = os.path.abspath(out_dir)
        self.seed = int(self.cfg['seed'])
        os.makedirs(self.out_dir, exist_ok=True)
        for name in ('checkpoints', 'logs'):
            os.makedirs(os.path.join(self.out_dir, name), exist_ok=True)
        self.log_path = os.path.join(self.out_dir, 'logs', 'sa.log')
        self.history_path = os.path.join(self.out_dir, 'logs', 'history.jsonl')
        self.best_routes_path = os.path.join(self.out_dir, 'best_routes.json')
        self.best_meta_path = os.path.join(self.out_dir, 'best_meta.json')
        self.latest_path = os.path.join(self.out_dir, 'checkpoints',
                                        'latest_routes.json')
        self.state_meta_path = os.path.join(self.out_dir, 'checkpoints',
                                            'latest_state.json')
        self._log_fh = open(self.log_path, 'a', encoding='utf-8')
        self._hist_fh = open(self.history_path, 'a', encoding='utf-8')
        self.log = log or self._default_log
        self.rng = random.Random(self.seed)

        routes = doc['routes']
        started = _now()
        self.state = S5.State(routes, min_angle_deg=float(self.cfg['theta']),
                              log=lambda *args, **kwargs: None)
        self.state_seconds = _now() - started
        self.evaluator = NB.Evaluator(self.state, theta=self.cfg['theta'])
        self.proposer = NB.Proposer(self.state, self.evaluator, self.rng,
                                    cfg=self.cfg.get('proposer'), log=self.log)
        self.T = float(self.cfg['T0'])
        self.T_scale = 1.0
        self.move_count = 0
        self.accepted = 0
        self.accepted_worse = 0
        self.rejected = 0
        self.failed_proposals = 0
        self.commit_failures = 0
        self.reconcile_count = 0
        self.reconcile_mismatch = 0
        self.reheat_count = 0
        self.success = False
        self.n_bad = int(self.state.n_violations)
        self.deficit = float(self.state.deficit())
        self.crossings = int(len(self.state.crossings))
        self.length = float(self.state.length)
        self.move_stats = defaultdict(lambda: Counter())
        self.start_time = _now()
        self.last_improve = _now()
        self.last_checkpoint = _now()
        self.last_best_write = 0.0
        self.last_log = _now()
        self.last_reconcile = _now()
        self.acc_window = []
        self.best_key = self._key()
        self.best_routes = {rid: copy.deepcopy(route) for rid, route in
                            self.state.world.routes.items()}
        self.best_move = 0
        self.best_meta = None
        self.resumed = False
        if resume_dir:
            self._resume(resume_dir)
        self.log(
            'G6 SA start seed=%d profile=%s routes=%d '
            'N_bad=%d D_theta=%.6f crossings=%d hard_issues=%d'
            % (self.seed, self.cfg['profile'], len(self.state.world.routes),
               self.n_bad, self.deficit, self.crossings,
               len(self.state.hard_issues)))
        self._write_json(os.path.join(self.out_dir, 'run_meta.json'), dict(
            schema='g6_run_meta_v1', seed=self.seed, profile=self.cfg['profile'],
            cfg=dict(self.cfg), started=_stamp(), start_n_bad=self.n_bad,
            start_deficit=round(self.deficit, 6),
            start_crossings=self.crossings,
            state_build_seconds=round(self.state_seconds, 3),
            resumed=self.resumed))

    # ------------------------------------------------------------------ log
    def _default_log(self, message):
        line = '[%s] %s' % (_stamp(), message)
        print(line, flush=True)
        self._log_fh.write(line + '\n')
        self._log_fh.flush()

    def close(self):
        for handle in (self._log_fh, self._hist_fh):
            try:
                handle.close()
            except Exception:  # noqa: BLE001
                pass

    # ---------------------------------------------------------------- state
    def _key(self):
        return (int(self.n_bad), round(float(self.deficit), 6),
                int(self.crossings), round(float(self.length), 3))

    def _sync_after_commit(self, before_n, before_def):
        """Read the exact post-commit counters from the state."""
        self.n_bad = int(self.state.n_violations)
        self.deficit = float(self.state.deficit())
        self.crossings = int(len(self.state.crossings))
        self.length = float(self.state.length)
        drift = (self.n_bad - before_n)
        return drift

    # ------------------------------------------------------------- snapshot
    def _payload(self, routes, copy_routes=True):
        payload = {key: value for key, value in self.doc.items()
                   if key not in ('routes',)}
        if copy_routes:
            payload['routes'] = [copy.deepcopy(routes[rid])
                                 for rid in sorted(routes)]
        else:
            payload['routes'] = [routes[rid] for rid in sorted(routes)]
        payload['route_count'] = len(payload['routes'])
        payload['routed'] = len(payload['routes'])
        payload['failed'] = 0
        summary = dict(
            schema='g6_angle45_multiarc_sa_v1',
            theta_min_deg=float(self.cfg['theta']),
            seed=self.seed,
            profile=self.cfg['profile'],
            moves=self.move_count,
            accepted=self.accepted,
            n_bad=self.n_bad,
            deficit=round(self.deficit, 6),
            crossings=self.crossings,
            length_mm=round(self.length, 6),
            M=float(self.cfg['M']),
            lam=float(self.cfg['lam']),
            elapsed_seconds=round(_now() - self.start_time, 3),
            generated_at=_stamp(),
        )
        g6 = dict(payload.get('g6') or {})
        g6.update(summary)
        payload['g6'] = g6
        payload['g5'] = dict(payload.get('g5') or {})
        payload['g5'].update(dict(schema='g6_angle45_routes_v1',
                                  theta_min_deg=float(self.cfg['theta']),
                                  cleaned=True))
        payload['algorithm'] = 'ANGLE_AWARE_MULTIARC_SA_G6'
        return payload

    def _write_json(self, path, obj):
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as handle:
            json.dump(obj, handle, ensure_ascii=False)
        os.replace(tmp, path)

    def _write_best(self, force=False):
        if not force and (_now() - self.last_best_write
                          < float(self.cfg['best_min_interval'])):
            return
        self.best_routes = {rid: copy.deepcopy(route) for rid, route in
                            self.state.world.routes.items()}
        self.best_meta = dict(
            n_bad=self.n_bad, deficit=round(self.deficit, 6),
            crossings=self.crossings, length_mm=round(self.length, 6),
            move=self.move_count, seed=self.seed,
            profile=self.cfg['profile'], at=_stamp())
        payload = self._payload(self.best_routes, copy_routes=False)
        self._write_json(self.best_routes_path, payload)
        self._write_json(self.best_meta_path, self.best_meta)
        self.last_best_write = _now()

    def _checkpoint(self, force=False):
        if not force and (_now() - self.last_checkpoint
                          < float(self.cfg['checkpoint_seconds'])):
            return
        payload = self._payload(self.state.world.routes, copy_routes=False)
        self._write_json(self.latest_path, payload)
        meta = dict(
            seed=self.seed, profile=self.cfg['profile'],
            move_count=self.move_count, accepted=self.accepted,
            rejected=self.rejected, failed_proposals=self.failed_proposals,
            commit_failures=self.commit_failures, T=self.T,
            T_scale=self.T_scale, reheat_count=self.reheat_count,
            n_bad=self.n_bad, deficit=self.deficit,
            crossings=self.crossings, length_mm=self.length,
            best_key=list(self.best_key), best_move=self.best_move,
            rng_state=self.rng.getstate(),
            elapsed=_now() - self.start_time, at=_stamp(),
            cfg=dict(self.cfg),
        )
        self._write_json(self.state_meta_path, meta)
        self.last_checkpoint = _now()

    def _resume(self, resume_dir):
        latest = os.path.join(resume_dir, 'checkpoints', 'latest_routes.json')
        meta_path = os.path.join(resume_dir, 'checkpoints', 'latest_state.json')
        if not (os.path.exists(latest) and os.path.exists(meta_path)):
            self.log('resume requested but no checkpoint found in %s'
                     % resume_dir)
            return
        self.log('resuming from %s' % resume_dir)
        with open(latest, encoding='utf-8') as handle:
            payload = json.load(handle)
        routes = {int(route['route_id']): route
                  for route in payload['routes']}
        self.doc = {key: value for key, value in payload.items()
                    if key != 'routes'}
        with open(meta_path, encoding='utf-8') as handle:
            meta = json.load(handle)
        self.state = S5.State(list(routes.values()),
                              min_angle_deg=float(self.cfg['theta']),
                              log=lambda *args, **kwargs: None)
        self.evaluator = NB.Evaluator(self.state, theta=self.cfg['theta'])
        self.rng = random.Random()
        try:
            self.rng.setstate(_tuple_rng(meta['rng_state']))
        except Exception:  # noqa: BLE001
            self.rng = random.Random(self.seed + int(meta.get('move_count', 0)))
        self.proposer = NB.Proposer(self.state, self.evaluator, self.rng,
                                    cfg=self.cfg.get('proposer'), log=self.log)
        self.move_count = int(meta.get('move_count', 0))
        self.accepted = int(meta.get('accepted', 0))
        self.rejected = int(meta.get('rejected', 0))
        self.failed_proposals = int(meta.get('failed_proposals', 0))
        self.commit_failures = int(meta.get('commit_failures', 0))
        self.T = float(meta.get('T', self.cfg['T0']))
        self.T_scale = float(meta.get('T_scale', 1.0))
        self.reheat_count = int(meta.get('reheat_count', 0))
        best = meta.get('best_key') or []
        self.best_key = tuple(best) if best else self._key()
        self.best_move = int(meta.get('best_move', 0))
        self.start_time = _now() - float(meta.get('elapsed', 0.0))
        self.n_bad = int(self.state.n_violations)
        self.deficit = float(self.state.deficit())
        self.crossings = int(len(self.state.crossings))
        self.length = float(self.state.length)
        self.resumed = True
        # restore the best snapshot if it exists
        try:
            with open(self.best_routes_path, encoding='utf-8') as handle:
                best_payload = json.load(handle)
            self.best_routes = {int(route['route_id']): route
                                for route in best_payload['routes']}
        except Exception:  # noqa: BLE001
            self.best_routes = {rid: copy.deepcopy(route) for rid, route in
                                self.state.world.routes.items()}

    # ------------------------------------------------------------- acceptance
    def _temperature(self, elapsed, budget):
        if budget and budget > 0:
            frac = min(1.0, max(0.0, elapsed / float(budget)))
            base = float(self.cfg['T0']) * (
                float(self.cfg['T_end']) / float(self.cfg['T0'])) ** frac
        else:
            base = max(float(self.cfg['T_end']), self.T * 0.99995)
        return max(float(self.cfg['T_end']),
                   min(float(self.cfg['T0']) * 2.0, base * self.T_scale))

    def _commit(self, move):
        # NOTE: g5.model.self_clearance is NOT a valid gate here: its
        # cumulative-length bookkeeping puts every flat part before every
        # transition, so it reports false self hits at the frozen lead/body
        # junctions (932/1024 frozen routes "fail" it).  The authoritative
        # self-distance check is the frozen project validator (A); the body
        # candidate grammar already carries the layer2d ``_self_clearance_ok``
        # audit.  Only the exact world evaluator is used as the commit gate.
        if len(move.routes) == 1:
            rid, new_route = next(iter(move.routes.items()))
            old_route = copy.deepcopy(self.state.world.routes[rid])
            info = self.state.apply(rid, new_route)
            if info['issues']:
                self.state.apply(rid, old_route)
                self.commit_failures += 1
                return False
            self.proposer.refresh_route(rid)
            return True
        result = B5.commit_batch(self.state, move.routes)
        if not result.get('ok'):
            self.commit_failures += 1
            return False
        for rid in move.routes:
            self.proposer.refresh_route(rid)
        return True

    def _maybe_reconcile(self):
        if _now() - self.last_reconcile < float(self.cfg['reconcile_seconds']):
            return
        tracked = (self.n_bad, round(self.deficit, 6), self.crossings)
        started = _now()
        self.state.refresh()
        self.reconcile_count += 1
        actual = (int(self.state.n_violations),
                  round(float(self.state.deficit()), 6),
                  int(len(self.state.crossings)))
        self.last_reconcile = _now()
        if actual != tracked:
            self.reconcile_mismatch += 1
            self.log('RECONCILE mismatch tracked=%s actual=%s (%.1fs)'
                     % (tracked, actual, _now() - started))
        else:
            self.log('reconcile ok %s (%.1fs)' % (actual, _now() - started))
        self.n_bad, self.deficit, self.crossings = actual
        self.length = float(self.state.length)

    # ------------------------------------------------------------------- run
    def run(self, seconds=3600.0, max_moves=None):
        budget = float(seconds)
        started = _now()
        next_log = started + float(self.cfg['log_seconds'])
        while True:
            now = _now()
            elapsed = now - self.start_time
            if self.n_bad == 0:
                self.success = True
                self.log('SUCCESS: N_bad == 0 reached at move %d (%.1fs)'
                         % (self.move_count, elapsed))
                self._write_best(force=True)
                self._checkpoint(force=True)
                break
            if now - started >= budget and self.move_count > 0:
                self.log('budget exhausted after %d moves (%.1fs); N_bad=%d'
                         % (self.move_count, _now() - started, self.n_bad))
                break
            if max_moves and self.move_count >= int(max_moves):
                self.log('move budget exhausted; N_bad=%d' % self.n_bad)
                break

            self.T = self._temperature(elapsed, budget)
            proposal = NB.propose(self.proposer, self.cfg['profile'])
            self.move_count += 1
            if proposal is None:
                self.failed_proposals += 1
                self._record_move('none', None, False)
                if self.move_count % 200 == 0:
                    self.log('no legal proposal in last window (failed=%d)'
                             % self.failed_proposals)
                continue
            move, energy, delta_bad, delta_def = proposal
            self.move_stats[move.kind]['attempted'] += 1
            accept = energy <= 0.0
            if not accept:
                ratio = -float(energy) / max(self.T, 1e-9)
                accept = ratio > -40.0 and self.rng.random() < math.exp(ratio)
            if accept:
                before_n, before_def = self.n_bad, self.deficit
                if not self._commit(move):
                    self.rejected += 1
                    self._record_move(move.kind, move.label, False)
                    continue
                drift = self._sync_after_commit(before_n, before_def)
                self.accepted += 1
                if energy > 0.0:
                    self.accepted_worse += 1
                if drift != delta_bad:
                    self.log('count drift predicted=%+d actual=%+d (%s)'
                             % (delta_bad, drift, move.label))
                self._record_move(move.kind, move.label, True,
                                  energy=energy, delta_bad=drift,
                                  delta_def=delta_def)
                key = self._key()
                if key < self.best_key:
                    self.best_key = key
                    self.best_move = self.move_count
                    self.last_improve = _now()
                    self._write_best()
                    self._hist({
                        'event': 'improve', 'move': self.move_count,
                        'n_bad': self.n_bad,
                        'deficit': round(self.deficit, 6),
                        'crossings': self.crossings,
                        'length_mm': round(self.length, 3),
                        'energy': round(energy, 3),
                        'T': round(self.T, 3),
                        'move_kind': move.kind, 'label': move.label,
                        'elapsed': round(elapsed, 3)})
            else:
                self.rejected += 1
                self._record_move(move.kind, move.label, False,
                                  energy=energy, delta_bad=delta_bad,
                                  delta_def=delta_def)
            window = self.acc_window
            window.append(1 if accept else 0)
            if len(window) > 240:
                del window[0]
            if len(window) == 240:
                rate = sum(window) / len(window)
                if rate < 0.035 and self.T < float(self.cfg['T0']) * 1.8:
                    self.T_scale = min(8.0, self.T_scale * 1.6)
                    window.clear()
                elif rate > 0.72 and self.T_scale > 0.1:
                    self.T_scale = max(0.1, self.T_scale * 0.7)
                    window.clear()
            if _now() - self.last_improve > float(
                    self.cfg['reheat_after_seconds']):
                self.reheat_count += 1
                old = self.T
                self.T_scale = min(12.0, max(self.T_scale, 1.0) * 2.5)
                self.last_improve = _now()
                self.log('REHEAT #%d: T %.1f -> %.1f (N_bad=%d)'
                         % (self.reheat_count, old, self._temperature(
                             elapsed, budget), self.n_bad))
            if _now() >= next_log:
                self.log('t=%.1fs moves=%d acc=%.3f worse_acc=%d N_bad=%d '
                         'D=%.3f T=%.1f reheat=%d commit_fail=%d '
                         'failed_props=%d'
                         % (elapsed, self.move_count,
                            self.accepted / max(1, self.move_count),
                            self.accepted_worse, self.n_bad, self.deficit,
                            self.T, self.reheat_count,
                            self.commit_failures, self.failed_proposals))
                self._hist({'event': 'stat', 'move': self.move_count,
                            'n_bad': self.n_bad,
                            'deficit': round(self.deficit, 6),
                            'crossings': self.crossings,
                            'length_mm': round(self.length, 3),
                            'T': round(self.T, 3),
                            'accepted': self.accepted,
                            'rejected': self.rejected,
                            'failed': self.failed_proposals,
                            'move_stats': {kind: dict(counter) for kind,
                                           counter in self.move_stats.items()},
                            'elapsed': round(elapsed, 3)})
                next_log = _now() + float(self.cfg['log_seconds'])
            self._maybe_reconcile()
            self._checkpoint()
        self._write_best(force=True)
        self._checkpoint(force=True)
        summary = self.summary()
        self._write_json(os.path.join(self.out_dir, 'summary.json'), summary)
        self.log('STOP %s' % json.dumps(summary, ensure_ascii=False,
                                        sort_keys=True))
        return summary

    # ---------------------------------------------------------------- records
    def _record_move(self, kind, label, accepted, energy=None, delta_bad=None,
                     delta_def=None):
        self.move_stats[kind]['accepted' if accepted else 'rejected'] += 1
        if accepted:
            if delta_bad is not None and delta_bad < 0:
                self.move_stats[kind]['improving'] += 1

    def _hist(self, obj):
        try:
            self._hist_fh.write(json.dumps(obj, ensure_ascii=False) + '\n')
            self._hist_fh.flush()
        except Exception:  # noqa: BLE001
            pass

    def summary(self):
        elapsed = _now() - self.start_time
        move_stats = {kind: dict(counter)
                      for kind, counter in self.move_stats.items()}
        total_attempted = sum(counter.get('attempted', 0)
                              for counter in move_stats.values())
        total_accepted = sum(counter.get('accepted', 0)
                             for counter in move_stats.values())
        return dict(
            schema='g6_sa_summary_v1',
            seed=self.seed, profile=self.cfg['profile'],
            theta_min_deg=float(self.cfg['theta']),
            M=float(self.cfg['M']), lam=float(self.cfg['lam']),
            moves=self.move_count, accepted=self.accepted,
            rejected=self.rejected, accepted_worse=self.accepted_worse,
            failed_proposals=self.failed_proposals,
            commit_failures=self.commit_failures,
            reheat_count=self.reheat_count,
            reconcile_count=self.reconcile_count,
            reconcile_mismatch=self.reconcile_mismatch,
            elapsed_seconds=round(elapsed, 3),
            moves_per_second=round(self.move_count / max(elapsed, 1e-9), 3),
            acceptance_rate=round(self.accepted / max(1, self.move_count), 4),
            n_bad=self.n_bad, deficit=round(self.deficit, 6),
            crossings=self.crossings, length_mm=round(self.length, 6),
            hard_issues=len(self.state.hard_issues),
            best_key=list(self.best_key), best_move=self.best_move,
            success=self.n_bad == 0,
            move_stats=move_stats,
            total_attempted=total_attempted,
            total_accepted=total_accepted,
            state_build_seconds=round(self.state_seconds, 3),
            cfg=dict(self.cfg),
            generated_at=_stamp(),
        )


def _tuple_rng(state):
    """JSON round-trip helper: list -> tuple (nested)."""
    if isinstance(state, (list, tuple)):
        return tuple(_tuple_rng(item) for item in state)
    return state


# ---------------------------------------------------------------------------
# payload / document helpers
# ---------------------------------------------------------------------------
def load_doc(path):
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def write_payload(doc, routes, path):
    payload = {key: value for key, value in doc.items() if key != 'routes'}
    payload['routes'] = [copy.deepcopy(routes[rid]) for rid in sorted(routes)]
    payload['route_count'] = len(payload['routes'])
    payload['routed'] = len(payload['routes'])
    payload['failed'] = 0
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle, ensure_ascii=False)
    return payload
