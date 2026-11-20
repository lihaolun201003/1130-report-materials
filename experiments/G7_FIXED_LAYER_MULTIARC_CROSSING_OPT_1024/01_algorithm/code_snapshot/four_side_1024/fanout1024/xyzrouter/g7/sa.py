# -*- coding: utf-8 -*-
"""G7 fixed-layer MultiArc simulated annealing (E = N_cross).

Only the body MultiArc of 527 modifiable standard routes may change; heights,
R15 transitions, ports, interface/direct geometry and the 368 artificial-U
groups are frozen.  Every accepted state is checked against the frozen manifest
(:mod:`..g7.frozen`) and every accepted move is evaluated with the authoritative
strict-D56 pair audit (:mod:`..g7.engine`), so a crossing count improvement can
never be a search-side pseudo-improvement.
"""
from __future__ import annotations

import copy
import json
import math
import os
import random
import time
from collections import Counter, OrderedDict, defaultdict

from . import frozen as FR
from . import engine as EN
from ..g5 import model as G5
from ..g5 import candidates as C5
from ..g6 import geometry as GEO
from ....fslw import validate_fslw as F

THETA = 45.0

DEFAULT_CFG = dict(
    profile='A',
    seed=0,
    T0=1.2,
    T_end=0.05,
    M=None,                 # G7 energy is the raw crossing count
    pool_build=140,         # layer2d bodies built before sampling
    pool_size=16,           # assembled candidates cached per route pose
    pool_cache=420,         # LRU route pools
    n1_sample=4,            # authoritative candidate evaluations per N1 move
    n1_trials=2,            # 3-D validated candidates per N1 move
    pair_sample=2,          # candidate options per route in an N2 move
    group_size=(3, 5),
    group_sample=2,
    n1_weight=1.0,
    n2_weight=0.0,
    n3_weight=0.0,
    n5_weight=0.0,
    hotspot_share=0.0,      # probability of picking a top-crossing route
    length_tiebreak=1e-4,
    reheat_after_seconds=300.0,
    reconcile_seconds=420.0,
    checkpoint_seconds=180.0,
    best_min_interval=8.0,
    log_seconds=60.0,
)


def _now():
    return time.time()


def _stamp():
    return time.strftime('%Y-%m-%dT%H:%M:%S')


def _route_key(route, freeze_entry):
    """Signature of the current body primitives (pool invalidation key)."""
    prims = EN.body_primitives(route, freeze_entry)
    return GEO.body_signature(prims)


class CandidatePool:
    """Cached body-only MultiArc candidates (fixed pose, fixed height)."""

    def __init__(self, world, freeze, rng, cfg, log=None):
        self.world = world
        self.freeze = freeze
        self.rng = rng
        self.cfg = cfg
        self.log = log or (lambda *args, **kwargs: None)
        self.cache = OrderedDict()
        self.stats = Counter()
        self.movable_set = {int(rid) for rid in world.routes
                              if freeze['entries'][str(rid)]['kind'] == 'modifiable'}

    def entry(self, rid):
        rid = int(rid)
        entries = self.freeze['entries']
        return entries.get(rid) if str(rid) not in entries else \
            entries[str(rid)]

    def candidates(self, rid, sample, top_only=False):
        rid = int(rid)
        entry = self.freeze['entries'][str(rid)]
        route = self.world.routes[rid]
        key = (rid, _route_key(route, entry))
        if key in self.cache:
            self.cache.move_to_end(key)
            pool = self.cache[key]
        else:
            pool = self._build(rid, route)
            self.cache[key] = pool
            while len(self.cache) > int(self.cfg['pool_cache']):
                self.cache.popitem(last=False)
        if len(pool) <= sample:
            return list(pool)
        if top_only:
            return list(pool[:sample])
        half = max(2, sample // 2)
        top = pool[:half]
        rest = pool[half:]
        return top + self.rng.sample(rest, min(len(rest), sample - half))

    def _build(self, rid, route):
        """Build a pre-filtered candidate pool for one route pose.

        Each candidate is checked once against the **frozen** routes of its
        physical height with the authoritative strict-D56 pair rule; candidates
        that conflict with a frozen route (which can never move) or that create a
        sub-45-degree crossing with one are discarded up front.  The remaining
        candidates carry their frozen-route crossing count, which lets the SA
        loop evaluate a move against the (few) movable neighbours only.
        """
        entry = self.freeze['entries'][str(rid)]
        dissected = GEO.dissect_route(route)
        if dissected is None or dissected['kind'] != 'lifted':
            return []
        frame, specs, error = GEO.enumerate_specs(dissected, route)
        if frame is None:
            return []
        bodies = GEO.build_bodies(frame, specs,
                                  max_build=int(self.cfg['pool_build']))
        if not bodies:
            return []
        self.stats['bodies'] += len(bodies)
        z = self.world.route_plane[rid]
        frozen_ids = [other for other in self.world.prepared[z]
                      if other != rid and other not in self.movable_set]
        frozen_prepared = [(other, self.world.prepared[z][other])
                           for other in frozen_ids]
        movable_ids = [other for other in self.world.prepared[z]
                       if other != rid and other in self.movable_set]
        movable_prepared = [(other, self.world.prepared[z][other])
                            for other in movable_ids]
        pool = []

        def frozen_filter(body_prims):
            prepared_new = F.prepare_route(body_prims, route_id=rid)
            frozen_count = 0
            for other, other_prepared in frozen_prepared:
                result = F.evaluate_pair(other_prepared, prepared_new,
                                         EN.CLEARANCE, EN.SAGITTA, 'strict')
                if result is None:
                    continue
                if not result.get('valid'):
                    return None
                for crossing in result.get('crossings') or ():
                    if EN._angle_from_sine(crossing['sine']) < THETA:
                        return None
                    frozen_count += 1
            movable_count = 0
            for other, other_prepared in movable_prepared:
                result = F.evaluate_pair(other_prepared, prepared_new,
                                         EN.CLEARANCE, EN.SAGITTA, 'strict')
                if result is None:
                    continue
                if not result.get('valid'):
                    return None
                movable_count += len(result.get('crossings') or [])
            return frozen_count, movable_count

        def add_candidate(label, body_prims, route_candidate):
            if G5.structure_issues(route_candidate):
                return
            filtered = frozen_filter(body_prims)
            if filtered is None:
                return
            frozen_count, movable_count = filtered
            old_total = self.world.route_crossings.get(int(rid), 0)
            pool.append(dict(label=label, route=route_candidate,
                             prims=[dict(prim) for prim in body_prims],
                             frozen_count=frozen_count,
                             est_delta=frozen_count + movable_count - old_total))

        checked = 0
        for family, params, body_world in bodies:
            if checked >= int(self.cfg['pool_build']):
                break
            checked += 1
            new_route = GEO.with_body(route, dissected, body_world)
            if new_route is not None:
                add_candidate(str(family), body_world, new_route)
        # G5 exact corridor-shift moves: translate one straight corridor while
        # preserving both landing poses (a strictly smaller perturbation than a
        # full MultiArc regeneration, often legal on packed planes)
        try:
            for label, variant in C5.corridor_variants(
                    route, deltas=(-15.0, -9.0, -5.0, -3.0, 3.0, 5.0, 9.0, 15.0),
                    limit_per_route=32, min_length=0.6):
                if variant is None:
                    continue
                prims = EN.body_primitives(variant, entry)
                if prims:
                    add_candidate('corridor:' + str(label), prims, variant)
        except Exception:  # noqa: BLE001 - corridor family is optional
            pass
        pool.sort(key=lambda item: item['est_delta'])
        pool = pool[:max(int(self.cfg['pool_size']),
                         int(self.cfg['pool_size']) * 2)]
        self.stats['pools'] += 1
        self.stats['candidates'] += len(pool)
        return pool


class G7SA:
    def __init__(self, doc, manifest, out_dir, cfg=None, log=None,
                 resume_dir=None):
        self.cfg = dict(DEFAULT_CFG, **(cfg or {}))
        self.doc = doc
        self.manifest = manifest
        self.out_dir = os.path.abspath(out_dir)
        self.seed = int(self.cfg['seed'])
        os.makedirs(self.out_dir, exist_ok=True)
        for name in ('checkpoints', 'logs'):
            os.makedirs(os.path.join(self.out_dir, name), exist_ok=True)
        log_path = os.path.join(self.out_dir, 'logs', 'sa.log')
        self._log_fh = open(log_path, 'a', encoding='utf-8')
        self._hist_fh = open(os.path.join(self.out_dir, 'logs',
                                          'history.jsonl'), 'a', encoding='utf-8')
        self.log = log or self._default_log
        self.rng = random.Random(self.seed)
        routes = doc['routes']
        self.pw = EN.PlaneWorld(routes, freeze=manifest)
        self.pool = CandidatePool(self.pw, manifest, self.rng, self.cfg,
                                  log=self.log)
        self.movable = [rid for rid in self.pw.routes
                        if manifest['entries'][str(rid)]['kind'] == 'modifiable']
        self.movable_set = set(self.movable)
        self.T = float(self.cfg['T0'])
        self.move_count = 0
        self.accepted = 0
        self.rejected = 0
        self.failed_proposals = 0
        self.commit_failures = 0
        self.illegal_rollbacks = 0
        self.reheat_count = 0
        self.reconcile_count = 0
        self.reconcile_mismatch = 0
        self.conditional = Counter()
        self.move_stats = defaultdict(Counter)
        self.start_time = _now()
        self.last_improve = _now()
        self.last_checkpoint = _now()
        self.last_best_write = 0.0
        self.last_log = _now()
        self.last_reconcile = _now()
        self.acc_window = []
        self.crossings = int(self.pw.total_crossings)
        self.unique_pairs = int(self.pw.unique_pairs)
        self.min_angle = self.pw.min_angle() or 45.0
        self.length = self._length()
        self.best_key = self._key()
        self.best_move = 0
        self.best_routes = {rid: copy.deepcopy(route)
                            for rid, route in self.pw.routes.items()}
        self.resumed = False
        if resume_dir:
            self._resume(resume_dir)
        self.log('G7 SA start seed=%d profile=%s crossings=%d pairs=%d '
                 'min_angle=%.9f C=%.6f movable=%d'
                 % (self.seed, self.cfg['profile'], self.pw.total_crossings,
                    self.pw.unique_pairs, self.pw.min_angle() or 0.0,
                    self.length, len(self.movable)))
        os.makedirs(os.path.join(self.out_dir, 'checkpoints'), exist_ok=True)

    # ------------------------------------------------------------------ log
    def _default_log(self, message):
        line = '[%s] %s' % (_stamp(), message)
        print(line, flush=True)
        self._log_fh.write(line + '\n')
        self._log_fh.flush()

    def _hist(self, obj):
        try:
            self._hist_fh.write(json.dumps(obj, ensure_ascii=False) + '\n')
            self._hist_fh.flush()
        except Exception:  # noqa: BLE001
            pass

    def close(self):
        for handle in (self._log_fh, self._hist_fh):
            try:
                handle.close()
            except Exception:  # noqa: BLE001
                pass

    # --------------------------------------------------------------- state
    def _length(self):
        return sum(float(part.get('length_mm') or 0.0)
                   for route in self.pw.routes.values()
                   for part in route.get('parts') or ())

    def _key(self):
        return (int(self.pw.total_crossings),
                -round(float(self.pw.min_angle() or 0.0), 6),
                int(self.pw.unique_pairs),
                round(float(self._length()), 3))

    def _sync(self):
        self.crossings = int(self.pw.total_crossings)
        self.unique_pairs = int(self.pw.unique_pairs)
        self.min_angle = self.pw.min_angle() or 45.0
        self.length = self._length()

    # ------------------------------------------------------------- payload
    def _payload(self, routes):
        payload = {key: value for key, value in self.doc.items()
                   if key != 'routes'}
        payload['routes'] = [routes[rid] for rid in sorted(routes)]
        payload['route_count'] = len(payload['routes'])
        payload['routed'] = len(payload['routes'])
        payload['failed'] = 0
        payload['g7'] = dict(
            schema='g7_fixed_layer_multiarc_crossing_opt_v1',
            seed=self.seed, profile=self.cfg['profile'],
            crossings=self.crossings, unique_pairs=self.unique_pairs,
            min_angle_deg=round(self.min_angle, 9),
            length_mm=round(self.length, 6),
            moves=self.move_count, accepted=self.accepted,
            fixed_layer=True, fixed_transitions=True,
            frozen_manifest='g7_frozen_manifest_v1',
            generated_at=_stamp())
        return payload

    def _write_json(self, path, obj):
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as handle:
            json.dump(obj, handle, ensure_ascii=False)
        os.replace(tmp, path)

    def _write_best(self, force=False):
        if not force and _now() - self.last_best_write < float(
                self.cfg['best_min_interval']):
            return False
        current = self._key()
        if current > self.best_key:
            return False
        verify = FR.verify_payload(
            [self.pw.routes[rid] for rid in sorted(self.pw.routes)],
            self.manifest)
        if not verify['pass']:
            self.log('BEST REJECTED: fixed-manifest violation %s'
                     % verify['violations'][:3])
            return False
        self.best_routes = {rid: copy.deepcopy(route)
                            for rid, route in self.pw.routes.items()}
        self.best_key = self._key()
        self.best_move = self.move_count
        payload = self._payload(self.best_routes)
        self._write_json(os.path.join(self.out_dir, 'best_routes.json'), payload)
        self._write_json(os.path.join(self.out_dir, 'best_meta.json'), dict(
            crossings=self.crossings, unique_pairs=self.unique_pairs,
            min_angle_deg=round(self.min_angle, 9),
            length_mm=round(self.length, 6), move=self.move_count,
            seed=self.seed, profile=self.cfg['profile'], at=_stamp(),
            fixed_verify=dict(passed=verify['pass'],
                              violation_count=verify['violation_count'])))
        self.last_best_write = _now()
        return True

    def _checkpoint(self, force=False):
        if not force and _now() - self.last_checkpoint < float(
                self.cfg['checkpoint_seconds']):
            return
        payload = self._payload(self.pw.routes)
        self._write_json(os.path.join(self.out_dir, 'checkpoints',
                                      'latest_routes.json'), payload)
        meta = dict(seed=self.seed, profile=self.cfg['profile'],
                    move_count=self.move_count, accepted=self.accepted,
                    rejected=self.rejected,
                    failed_proposals=self.failed_proposals,
                    T=self.T, reheat_count=self.reheat_count,
                    crossings=self.crossings,
                    unique_pairs=self.unique_pairs,
                    min_angle_deg=self.min_angle,
                    length_mm=self.length,
                    best_key=list(self._key()), best_move=self.best_move,
                    rng_state=self.rng.getstate(),
                    elapsed=_now() - self.start_time, at=_stamp(),
                    cfg=dict(self.cfg))
        self._write_json(os.path.join(self.out_dir, 'checkpoints',
                                      'latest_state.json'), meta)
        self.last_checkpoint = _now()

    def _resume(self, resume_dir):
        latest = os.path.join(resume_dir, 'checkpoints', 'latest_routes.json')
        meta_path = os.path.join(resume_dir, 'checkpoints', 'latest_state.json')
        if not (os.path.exists(latest) and os.path.exists(meta_path)):
            self.log('resume requested but no checkpoint in %s' % resume_dir)
            return
        with open(latest, encoding='utf-8') as handle:
            payload = json.load(handle)
        self.doc = {key: value for key, value in payload.items()
                    if key != 'routes'}
        routes = payload['routes']
        self.pw = EN.PlaneWorld(routes, freeze=self.manifest)
        self.pool = CandidatePool(self.pw, self.manifest, self.rng, self.cfg,
                                  log=self.log)
        with open(meta_path, encoding='utf-8') as handle:
            meta = json.load(handle)
        try:
            self.rng.setstate(_tuple_rng(meta['rng_state']))
        except Exception:  # noqa: BLE001
            self.rng = random.Random(self.seed + int(meta.get('move_count', 0)))
        self.move_count = int(meta.get('move_count', 0))
        self.accepted = int(meta.get('accepted', 0))
        self.rejected = int(meta.get('rejected', 0))
        self.failed_proposals = int(meta.get('failed_proposals', 0))
        self.T = float(meta.get('T', self.cfg['T0']))
        self.reheat_count = int(meta.get('reheat_count', 0))
        self.best_move = int(meta.get('best_move', 0))
        self.start_time = _now() - float(meta.get('elapsed', 0.0))
        self.resumed = True
        self._sync()
        try:
            with open(os.path.join(resume_dir, 'best_routes.json'),
                      encoding='utf-8') as handle:
                best = json.load(handle)
            self.best_routes = {int(route['route_id']): route
                                for route in best['routes']}
        except Exception:  # noqa: BLE001
            self.best_routes = {rid: copy.deepcopy(route)
                                for rid, route in self.pw.routes.items()}

    # ------------------------------------------------------------- proposals
    def _select_route(self):
        ids = [rid for rid in self.movable]
        weights = [max(1, self.pw.route_crossings.get(rid, 0)) ** 1.5
                   for rid in ids]
        if self.cfg['hotspot_share'] and self.rng.random() < float(
                self.cfg['hotspot_share']):
            ranked = sorted(ids, key=lambda rid: -self.pw.route_crossings.get(rid, 0))
            top = ranked[:max(5, len(ranked) // 20)]
            return int(self.rng.choice(top))
        return int(self.rng.choices(ids, weights=weights, k=1)[0])

    def _best_candidate(self, rid, sample, top_only=False):
        """Best feasible body candidate for one route (frozen prefiltered pool).

        The authoritative strict-D56 pair rule is applied against the *movable*
        neighbours only (the frozen ones were already checked when the pool was
        built).  A pool candidate stores its frozen-neighbour crossing count, so
        the delta is exact.
        """
        pool = self.pool.candidates(rid, sample, top_only=top_only)
        if not pool:
            return None
        z = self.pw.route_plane[rid]
        prepared_plane = self.pw.prepared[z]
        movable_others = [(other, prepared_plane[other])
                          for other in prepared_plane
                          if other != rid and other in self.movable_set]
        old_total = int(self.pw.route_crossings.get(rid, 0))
        route = self.pw.routes[rid]
        scored = []
        for candidate in pool:
            prepared_new = F.prepare_route(candidate['prims'], route_id=rid)
            crossings = []
            bad = False
            for other, other_prepared in movable_others:
                result = F.evaluate_pair(other_prepared, prepared_new,
                                         EN.CLEARANCE, EN.SAGITTA, 'strict')
                if result is None:
                    continue
                if not result.get('valid'):
                    bad = True
                    break
                for crossing in result.get('crossings') or ():
                    angle = EN._angle_from_sine(crossing['sine'])
                    if angle < THETA:
                        bad = True
                        break
                    crossings.append((int(other), angle,
                                      float(crossing['point'][0]),
                                      float(crossing['point'][1])))
                if bad:
                    break
            if bad:
                continue
            delta = int(candidate['frozen_count']) + len(crossings) - old_total
            length_delta = (float(candidate['route'].get('length_mm') or 0.0)
                            - float(route.get('length_mm') or 0.0))
            scored.append(dict(score=(delta, length_delta), candidate=candidate,
                               crossings=crossings, delta=delta))
        if not scored:
            return None
        scored.sort(key=lambda item: item['score'])
        # epsilon-exploration: sometimes pick a random feasible candidate
        if (not top_only) and len(scored) > 1 and self.rng.random() < 0.25:
            pick = self.rng.randrange(len(scored))
        else:
            pick = 0
        for index in [pick] + [i for i in range(len(scored)) if i != pick][:2]:
            best = scored[index]
            issues = self.pw.body_3d_issues(rid, best['candidate']['route'])
            if issues:
                continue
            return dict(score=best['score'], candidate=best['candidate'],
                        route=route, crossings=best['crossings'],
                        delta=best['delta'])
        return None

    def _propose_n1(self):
        rid = self._select_route()
        if rid not in self.movable_set:
            return None
        sample = int(self.cfg['n1_sample'])
        result = self._best_candidate(rid, sample)
        if result is None:
            return None
        return dict(kind='N1', ids=[rid],
                    replacements={rid: result['candidate']['prims']},
                    routes={rid: result['candidate']['route']},
                    crossings={rid: result['crossings']},
                    delta=result['delta'])

    def _propose_n2(self):
        plane_pairs = [(z, key[0]) for z, events in self.pw.plane_events.items()
                       for key in events]
        if not plane_pairs:
            return None
        candidates = [item for item in plane_pairs
                      if item[1][0] in self.movable_set
                      and item[1][1] in self.movable_set]
        if not candidates:
            return None
        z, (rid_a, rid_b) = self.rng.choice(candidates)
        options = {}
        for rid in (rid_a, rid_b):
            pool = self.pool.candidates(rid, int(self.cfg['pair_sample']) * 2)
            if not pool:
                return None
            options[rid] = pool
        best = None
        combos = []
        for cand_a in options[rid_a]:
            for cand_b in options[rid_b]:
                combos.append((cand_a, cand_b))
        if not combos:
            return None
        self.rng.shuffle(combos)
        for cand_a, cand_b in combos[:4]:
            replacements = {rid_a: cand_a['prims'], rid_b: cand_b['prims']}
            result = self.pw.evaluate_batch(replacements)
            if not result['ok']:
                continue
            angles = [event['angle_deg']
                      for event in result['new_events'].values()]
            if angles and min(angles) < THETA:
                continue
            delta = result['delta']
            length_delta = sum(
                float(route.get('length_mm') or 0.0) -
                float(self.pw.routes[rid].get('length_mm') or 0.0)
                for rid, route in ((rid_a, cand_a['route']),
                                   (rid_b, cand_b['route'])))
            if best is None or (delta, length_delta) < best['score']:
                best = dict(score=(delta, length_delta),
                            replacements=replacements,
                            routes={rid_a: cand_a['route'],
                                    rid_b: cand_b['route']},
                            new_events=result['new_events'],
                            delta=delta,
                            ids=[rid_a, rid_b])
        if best is None:
            return None
        # 3-D gate for both new bodies
        for rid, route in best['routes'].items():
            if self.pw.body_3d_issues(rid, route):
                return None
        return dict(kind='N2', ids=best['ids'],
                    replacements=best['replacements'],
                    routes=best['routes'], batch_events=best['new_events'],
                    delta=best['delta'], crossings=None)

    def _propose_n3(self, size_range=None):
        z = self._hot_plane()
        if z is None:
            return None
        ids_here = sorted(rid for rid in self.pw.groups[z]
                          if rid in self.movable_set)
        if len(ids_here) < 3:
            return None
        ranked = sorted(ids_here,
                        key=lambda rid: -self.pw.route_crossings.get(rid, 0))
        size = self.rng.randint(*(size_range or self.cfg['group_size']))
        size = min(size, len(ranked))
        group = ranked[:max(size * 2, size)]
        chosen = self.rng.sample(group, size)
        options = {}
        for rid in chosen:
            pool = self.pool.candidates(rid, int(self.cfg['group_sample']))
            if pool:
                options[rid] = pool
        if len(options) < 3:
            return None
        best = None
        for _attempt in range(2):
            replacements = {}
            routes = {}
            for rid, pool in options.items():
                candidate = pool[self.rng.randrange(len(pool))]
                replacements[rid] = candidate['prims']
                routes[rid] = candidate['route']
            result = self.pw.evaluate_batch(replacements)
            if not result['ok']:
                continue
            angles = [event['angle_deg']
                      for event in result['new_events'].values()]
            if angles and min(angles) < THETA:
                continue
            delta = result['delta']
            if best is None or delta < best['delta']:
                best = dict(delta=delta, replacements=replacements,
                            routes=routes, new_events=result['new_events'],
                            ids=sorted(replacements))
        if best is None:
            return None
        for rid, route in best['routes'].items():
            if self.pw.body_3d_issues(rid, route):
                return None
        return dict(kind='N3', ids=best['ids'],
                    replacements=best['replacements'],
                    routes=best['routes'], batch_events=best['new_events'],
                    delta=best['delta'], crossings=None)

    def _hot_plane(self):
        planes = [(z, len(events)) for z, events in self.pw.plane_events.items()
                  if sum(1 for key in events
                         if key[0][0] in self.movable_set
                         or key[0][1] in self.movable_set) >= 3]
        if not planes:
            return None
        weights = [count ** 1.2 for _z, count in planes]
        total = sum(weights)
        draw = self.rng.random() * total
        for (z, _count), weight in zip(planes, weights):
            if draw < weight:
                return z
            draw -= weight
        return planes[-1][0]

    def _propose(self):
        profile = str(self.cfg['profile']).upper()
        draw = self.rng.random()
        if profile == 'A':
            return self._propose_n1()
        if profile == 'B':
            if draw < 0.68:
                return self._propose_n1()
            if draw < 0.88:
                return self._propose_n2()
            return self._propose_n3()
        # profile C: N1..N5 incl. larger layer-hotspot groups
        if draw < 0.55:
            return self._propose_n1()
        if draw < 0.75:
            return self._propose_n2()
        if draw < 0.90:
            return self._propose_n3()
        return self._propose_n3(size_range=(6, 10))

    # -------------------------------------------------------------- commits
    def _commit(self, move):
        """Apply a move and re-audit its physical plane with the authoritative
        strict-D56 rule; roll the move back if the plane is not completely legal
        (0 violations, every crossing >= 45 deg).  The freshly audited crossing
        set then *replaces* the incremental bookkeeping, so the official crossing
        count can never drift from the frozen-validator semantics."""
        ids = [int(rid) for rid in move['ids']]
        z = self.pw.route_plane[ids[0]]
        snapshot = self.pw.plane_snapshot(z, ids)
        old_routes = {rid: copy.deepcopy(self.pw.routes[rid]) for rid in ids}
        try:
            if move['kind'] == 'N1':
                rid = ids[0]
                applied = self.pw.apply_route(rid, move['routes'][rid],
                                              move['replacements'][rid],
                                              move['crossings'][rid])
            else:
                applied = self.pw.apply_batch(
                    move['replacements'], move.get('batch_events') or {})
        except Exception as error:  # noqa: BLE001
            self.log('commit exception: %r' % (error,))
            applied = False
        if not applied:
            for rid in ids:
                self.pw.routes[rid] = old_routes[rid]
                self.pw.world.set_route(rid, old_routes[rid])
            self.pw.restore_plane(z, snapshot)
            self.commit_failures += 1
            return False
        audit = self.pw.audit_plane(z)
        events = self.pw.events_from_audit(audit)
        bad_angle = any(event['angle_deg'] < THETA
                        for event in events.values())
        if audit.get('violations') or bad_angle:
            # illegal geometry: restore exactly and retry another proposal
            for rid in ids:
                self.pw.routes[rid] = old_routes[rid]
                self.pw.world.set_route(rid, old_routes[rid])
            self.pw.restore_plane(z, snapshot)
            self.illegal_rollbacks += 1
            self.commit_failures += 1
            return False
        self.pw.adopt_plane_events(z, events)
        return True

    def _temperature(self, elapsed, budget):
        if budget and budget > 0:
            frac = min(1.0, max(0.0, elapsed / float(budget)))
            base = float(self.cfg['T0']) * (
                float(self.cfg['T_end']) / float(self.cfg['T0'])) ** frac
        else:
            base = max(float(self.cfg['T_end']), self.T * 0.99995)
        return max(float(self.cfg['T_end']), base)

    def _maybe_reconcile(self):
        if _now() - self.last_reconcile < float(
                self.cfg['reconcile_seconds']):
            return
        self.reconcile_count += 1
        result = self.pw.full_reaudit()
        self.last_reconcile = _now()
        if not result['matches']:
            self.reconcile_mismatch += 1
            self.log('RECONCILE mismatch %s (incremental %d/%d/%.9f)'
                     % ({key: result[key] for key in
                         ('crossings', 'unique_pairs', 'min_angle')},
                        self.pw.total_crossings, self.pw.unique_pairs,
                        self.pw.min_angle() or 0.0))
            self.pw = EN.PlaneWorld(
                [self.pw.routes[rid] for rid in sorted(self.pw.routes)],
                freeze=self.manifest)
        else:
            self.log('reconcile ok crossings=%d pairs=%d min=%.9f (%.1fs)'
                     % (result['crossings'], result['unique_pairs'],
                        result['min_angle'], result['seconds']))
        self._sync()

    # ------------------------------------------------------------------- run
    def run(self, seconds=1800.0, max_moves=None):
        budget = float(seconds)
        started = _now()
        next_log = started + float(self.cfg['log_seconds'])
        while True:
            now = _now()
            elapsed = now - self.start_time
            if now - started >= budget and self.move_count > 0:
                self.log('budget exhausted after %d moves (%.1fs) crossings=%d'
                         % (self.move_count, _now() - started,
                            self.pw.total_crossings))
                break
            if max_moves and self.move_count >= int(max_moves):
                self.log('move budget exhausted crossings=%d'
                         % self.pw.total_crossings)
                break
            self.T = self._temperature(elapsed, budget)
            move = self._propose()
            self.move_count += 1
            if move is None:
                self.failed_proposals += 1
                self.move_stats['none']['rejected'] += 1
                continue
            self.move_stats[move['kind']]['attempted'] += 1
            delta = int(move['delta'])
            accept = delta <= 0
            if not accept:
                ratio = -float(delta) / max(self.T, 1e-9)
                accept = ratio > -50.0 and self.rng.random() < math.exp(ratio)
            if accept and delta == 0:
                # plateau move: accept half of the time (keeps exploring)
                accept = self.rng.random() < 0.5
            if not accept:
                self.rejected += 1
                self.move_stats[move['kind']]['rejected'] += 1
                continue
            if not self._commit(move):
                self.commit_failures += 1
                continue
            self.accepted += 1
            self.move_stats[move['kind']]['accepted'] += 1
            if delta < 0:
                self.move_stats[move['kind']]['improving'] += 1
            self._sync()
            key = self._key()
            if key < self.best_key:
                if self._write_best():
                    self._hist({'event': 'improve', 'move': self.move_count,
                                'crossings': self.crossings,
                                'unique_pairs': self.unique_pairs,
                                'min_angle_deg': round(self.min_angle, 9),
                                'length_mm': round(self.length, 3),
                                'delta': delta, 'T': round(self.T, 4),
                                'move_kind': move['kind'],
                                'elapsed': round(elapsed, 3)})
            window = self.acc_window
            window.append(1 if accept else 0)
            if len(window) > 240:
                del window[0]
            if _now() - self.last_improve > float(
                    self.cfg['reheat_after_seconds']):
                self.reheat_count += 1
                self.T = min(float(self.cfg['T0']) * 2.0, self.T * 3.0)
                self.last_improve = _now()
                self.log('REHEAT #%d T=%.4f crossings=%d'
                         % (self.reheat_count, self.T,
                            self.pw.total_crossings))
            if _now() >= next_log:
                self.log('t=%.0fs moves=%d acc=%.3f crossings=%d pairs=%d '
                         'min=%.9f T=%.4f reheat=%d commit_fail=%d '
                         'failed=%d' % (elapsed, self.move_count,
                                        self.accepted /
                                        max(1, self.move_count),
                                        self.pw.total_crossings,
                                        self.pw.unique_pairs,
                                        self.pw.min_angle() or 0.0, self.T,
                                        self.reheat_count,
                                        self.commit_failures,
                                        self.failed_proposals))
                self._hist({'event': 'stat', 'move': self.move_count,
                            'crossings': self.crossings,
                            'unique_pairs': self.unique_pairs,
                            'min_angle_deg': round(self.min_angle, 9),
                            'length_mm': round(self.length, 3),
                            'T': round(self.T, 4), 'accepted': self.accepted,
                            'rejected': self.rejected,
                            'failed': self.failed_proposals,
                            'elapsed': round(elapsed, 3)})
                next_log = _now() + float(self.cfg['log_seconds'])
            self._maybe_reconcile()
            self._checkpoint()
        self._write_best(force=True)
        self._checkpoint(force=True)
        summary = self.summary()
        self._write_json(os.path.join(self.out_dir, 'summary.json'), summary)
        self.log('STOP %s' % json.dumps(
            {key: summary[key] for key in
             ('crossings', 'unique_pairs', 'min_angle_deg', 'moves',
              'accepted', 'elapsed_seconds')}, ensure_ascii=False))
        return summary

    def summary(self):
        audio = self.pw.summary()
        return dict(schema='g7_sa_summary_v1', seed=self.seed,
                    profile=self.cfg['profile'],
                    crossings=int(self.pw.total_crossings),
                    unique_pairs=int(self.pw.unique_pairs),
                    min_angle_deg=round(self.pw.min_angle() or 0.0, 9),
                    length_mm=round(self._length(), 6),
                    moves=self.move_count, accepted=self.accepted,
                    rejected=self.rejected,
                    failed_proposals=self.failed_proposals,
                    commit_failures=self.commit_failures,
                    illegal_rollbacks=self.illegal_rollbacks,
                    reheat_count=self.reheat_count,
                    reconcile_count=self.reconcile_count,
                    reconcile_mismatch=self.reconcile_mismatch,
                    elapsed_seconds=round(_now() - self.start_time, 3),
                    moves_per_second=round(
                        self.move_count / max(1e-9, _now() - self.start_time), 3),
                    acceptance_rate=round(
                        self.accepted / max(1, self.move_count), 4),
                    per_plane=audio['per_plane'],
                    sub45=audio['sub45'],
                    hard_issues=audio['hard_issues'],
                    move_stats={key: dict(value) for key, value in
                                self.move_stats.items()},
                    pool_stats=dict(self.pool.stats),
                    frozen_routes=len(self.pw.routes) - len(self.movable),
                    modifiable_routes=len(self.movable),
                    best_key=list(self._key()), best_move=self.best_move,
                    cfg=dict(self.cfg), generated_at=_stamp())


def _tuple_rng(state):
    if isinstance(state, (list, tuple)):
        return tuple(_tuple_rng(item) for item in state)
    return state
