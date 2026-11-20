# -*- coding: utf-8 -*-
"""Global optimisation loop + artifact writing for the XYZ joint router."""
from __future__ import annotations

import copy
import json
import time
from collections import Counter, OrderedDict
from pathlib import Path

from ..native3d import common as N
from ..native3d.crossing_cache import CrossingCache
from ..reheight21 import model as M
from . import local_reroute as LR
from . import paths as P
from . import route_builder as RB
from . import world_adapter as WA

ASSIGNMENT_FIELDS = ['route_id', 'plane', 'relation', 'manual_group',
                     'manual_pattern', 'layer_role', 'target_layer',
                     'target_plane_label', 'target_z_mm', 'interface_z_mm',
                     'direction', 'needs_transition', 'c4_group_id',
                     'rotation_phase', 'baseline_old_layer', 'source_endpoint',
                     'target_endpoint', 'source_side', 'target_side',
                     'source_connector', 'target_connector', 'source_x_mm',
                     'source_y_mm', 'target_x_mm', 'target_y_mm',
                     'source_row', 'target_row']


def log_default(message):
    print(message, flush=True)


class Optimizer:
    def __init__(self, state, baseline, out_dir, cfg=None, log=None,
                 checkpoint_dir=None):
        self.state = state
        self.baseline = baseline
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        #: stage-scoped checkpoint root.  The frozen 21-height campaign wrote
        #: every stage's checkpoints into the single global
        #: ``paths.DIRS['checkpoints']`` directory, so G1 and the concurrent
        #: G3_cold corrupted each other (audit g123.md 2.4).  A checkpoint
        #: must never escape its own stage: default = <out_dir>/checkpoints;
        #: an explicit ``checkpoint_dir`` still wins.
        self.checkpoint_dir = (
            Path(checkpoint_dir) if checkpoint_dir is not None
            else self.out_dir / 'checkpoints')
        self.cfg = dict(LR.DEFAULT_CFG, **(cfg or {}))
        self.log = log or log_default
        self.history = []
        self.round_stats = []
        self.failed = []
        self.started = time.time()
        self.checkpoint_index = 0
        self.baseline_routes = {int(r['route_id']): r
                                for r in baseline['routes']}
        self.per_route = {}
        self._refresh_per_route()
        self.base_total = int(state.total)
        self.best_total = int(state.total)
        self.best_snapshot = None

    # ------------------------------------------------------------- bookkeeping
    def _refresh_per_route(self):
        self.per_route, self.crossing_cache = self.state.per_route_counts()
        return self.per_route

    def route_crossings(self, route_id):
        return int(self.per_route.get(int(route_id), 0))

    def ordered_routes(self, route_ids):
        return sorted(route_ids, key=lambda rid: (-self.route_crossings(rid), int(rid)))

    # ---------------------------------------------------------------- run loop
    def run_round(self, candidate_ids, time_budget_seconds, max_accepts=None,
                  label='round'):
        round_started = time.time()
        stats = Counter()
        accepted = 0
        order = self.ordered_routes(candidate_ids)
        for rid in order:
            elapsed = time.time() - round_started
            if elapsed > time_budget_seconds:
                stats['budget_stop'] += 1
                break
            if max_accepts is not None and accepted >= max_accepts:
                stats['max_accepts'] += 1
                break
            stats['tried'] += 1
            try:
                record = LR.reroute_one(self.state, rid, cfg=self.cfg,
                                        stats=stats)
            except Exception as error:  # noqa: BLE001 - keep the run alive
                stats['exception'] += 1
                self.failed.append(dict(route_id=int(rid),
                                        reason='exception:%s' % error))
                continue
            if record is None:
                stats['no_gain'] += 1
                continue
            accepted += 1
            stats['accepted'] += 1
            stats['gain'] += -int(record['delta'])
            self.history.append(dict(
                round_index=len(self.round_stats) + 1,
                route_id=int(rid),
                old_layer=int(record['old_layer']),
                new_layer=int(record['new_layer']),
                old_z_mm=float(record['old_z']),
                new_z_mm=float(record['new_z']),
                delta=int(record['delta']),
                gain=int(-record['delta']),
                total_after=int(record['total']),
                family=str(record.get('family') or ''),
                lead_source_mm=float(record.get('lead_s') or 0.0),
                lead_target_mm=float(record.get('lead_t') or 0.0),
                xy_crossings=int(record.get('xy_crossings') or 0),
                old_length_mm=round(float(record['old_length']), 6),
                new_length_mm=round(float(record['new_length']), 6),
                seconds=round(float(record.get('seconds') or 0.0), 3),
                wall_seconds=round(time.time() - self.started, 2),
            ))
            if self.state.total < self.best_total:
                self.best_total = int(self.state.total)
            if self.checkpoint_index is None:
                self.checkpoint_index = 0
            self.checkpoint_index += 1
            if self.checkpoint_index % 25 == 0:
                self.save_checkpoint('checkpoint_%04d' % self.checkpoint_index)
                self.log('  [checkpoint] accepted=%d total=%d (%.1f min)' % (
                    self.checkpoint_index, self.state.total,
                    (time.time() - self.started) / 60.0))
        elapsed = time.time() - round_started
        reasons = stats.pop('reasons', None) or Counter()
        self.round_stats.append(dict(
            label=label, seconds=round(elapsed, 2), accepted=accepted,
            candidates_tried=int(stats.get('tried', 0)),
            total_after=int(self.state.total),
            gain=int(stats.get('gain', 0)),
            stats={str(k): int(v) for k, v in stats.items()},
            reasons={str(k): int(v) for k, v in reasons.items()}))
        self.log('[round %s] accepted=%d gain=%d total=%d (%.1f min)' % (
            label, accepted, int(stats.get('gain', 0)), self.state.total,
            elapsed / 60.0))
        self._refresh_per_route()
        return dict(accepted=accepted, stats={str(k): int(v) for k, v in stats.items()},
                    seconds=round(elapsed, 2))

    def run(self, candidate_ids, rounds=1, round_seconds=1200, max_accepts=None,
            label='round'):
        candidate_ids = list(candidate_ids)
        for index in range(int(rounds)):
            self.log('=' * 70)
            self.log('[%s] round %d/%d: %d candidate routes, total=%d' % (
                label, index + 1, rounds, len(candidate_ids), self.state.total))
            result = self.run_round(candidate_ids, round_seconds,
                                    max_accepts=max_accepts,
                                    label='%s_r%d' % (label, index + 1))
            if result['accepted'] == 0:
                self.log('[%s] converged: no accepted change in round %d' % (
                    label, index + 1))
                break
        self._refresh_per_route()
        return dict(rounds=self.round_stats,
                    total=int(self.state.total), base_total=self.base_total)

    # ----------------------------------------------------------------- saving
    def save_checkpoint(self, name):
        # stage-scoped: never the shared ``paths.DIRS['checkpoints']``
        # (defect 2.4 of the frozen campaign); see __init__.
        directory = Path(self.checkpoint_dir) / name
        directory.mkdir(parents=True, exist_ok=True)
        self.save_state(directory, include_reports=False)
        payload = dict(name=name, total=int(self.state.total),
                       history=len(self.history),
                       seconds=round(time.time() - self.started, 2))
        P.write_json(directory / 'checkpoint.json', payload)

    def routes_payload(self, note=''):
        payload = copy.deepcopy(self.baseline['payload'])
        payload['schema'] = P.SCHEMA
        payload['algorithm'] = P.ALGORITHM
        payload['note'] = note or payload.get('note') or ''
        payload['route_count'] = 1024
        payload['routed'] = len(self.state.routes)
        payload['failed'] = 0
        payload['routes'] = [self.state.routes[rid]
                             for rid in sorted(self.state.routes)]
        payload['manual_geometry'] = payload.get('manual_geometry')
        payload['crossing_definition'] = payload.get('crossing_definition') or (
            'fslw strict D56 per physical z; every flat part grouped by physical '
            'height; same rule as the frozen 2409 baseline')
        return payload

    def assignment_rows(self):
        rows = []
        for original in self.baseline['rows']:
            rid = int(original['route_id'])
            row = dict(original)
            planner = self.state.rows[rid]
            layer = int(planner['target_layer'])
            z = float(planner['target_z_mm'])
            row['target_layer'] = str(layer)
            row['target_plane_label'] = str(RB.PLANE_LABEL.get(layer, ''))
            row['target_z_mm'] = ('%.12g' % z)
            row['needs_transition'] = 'True' if planner['needs_transition'] else 'False'
            row['direction'] = str(planner['direction'])
            rows.append(row)
        return rows

    def crossing_stats(self):
        from ..nonc4 import crossings as X
        cache = self.crossing_cache
        events = cache.crossing_events()
        per_route = {}
        for event in events:
            per_route[int(event['route_a'])] = per_route.get(int(event['route_a']), 0) + 1
            per_route[int(event['route_b'])] = per_route.get(int(event['route_b']), 0) + 1
        planes = []
        for z_key in sorted(cache.plane_routes):
            events_count, pairs = cache.plane_counts.get(z_key, (0, 0))
            planes.append(dict(z_mm=float(z_key),
                               label=str(RB.PLANE_LABEL.get(
                                   N.plane_of_z(float(z_key)) or 0, '')),
                               routes=len(cache.plane_routes.get(z_key) or {}),
                               crossings=int(events_count),
                               crossing_pairs=int(pairs)))
        return dict(schema='xyz_joint_crossing_stats_v1',
                    crossing_rule='fslw strict D56 audit per physical z '
                                  '(frozen 2409 counting definition)',
                    totals=dict(crossings=int(cache.total()),
                                crossing_pairs=int(cache.total_pairs()),
                                routes_with_crossings=len(per_route),
                                max_route_crossings=max(per_route.values())
                                if per_route else 0),
                    planes=planes,
                    per_route_crossings={str(k): int(v)
                                         for k, v in sorted(per_route.items())},
                    crossing_events=[dict(route_a=int(e['route_a']),
                                          route_b=int(e['route_b']),
                                          z_mm=float(e['z_mm']),
                                          x_mm=round(float(e['x_mm']), 6),
                                          y_mm=round(float(e['y_mm']), 6),
                                          angle_deg=round(float(e['angle_deg']), 6))
                                     for e in events],
                    algorithm=P.ALGORITHM)

    def geometry_changes(self):
        changes = []
        for rid in sorted(self.state.routes):
            new = self.state.routes[rid]
            old = self.baseline_routes[rid]
            old_sig = RB.route_signature(old)
            new_sig = RB.route_signature(new)
            if old_sig == new_sig:
                continue
            old_row = self.baseline['rows']
            changes.append(dict(
                route_id=int(rid),
                manual_group=str(new.get('manual_group') or ''),
                old_layer=int(old.get('target_layer') or 0),
                new_layer=int(new.get('target_layer') or 0),
                old_z_mm=float(old.get('target_z_mm') or 0.0),
                new_z_mm=float(new.get('target_z_mm') or 0.0),
                old_transitions=int(old.get('n_transitions') or 0),
                new_transitions=int(new.get('n_transitions') or 0),
                old_mid_transitions=int(old.get('n_mid_transitions') or 0),
                new_mid_transitions=int(new.get('n_mid_transitions') or 0),
                old_length_mm=round(float(old.get('length_mm') or 0.0), 6),
                new_length_mm=round(float(new.get('length_mm') or 0.0), 6),
                xy_changed=bool(RB.body_xy_signature(old) != RB.body_xy_signature(new)),
                old_crossings=int(self.baseline_crossings.get(rid, 0)),
                new_crossings=int(self.per_route.get(rid, 0)),
            ))
        return changes

    def manual_changes(self):
        changes = []
        for rid in sorted(self.state.routes):
            new = self.state.routes[rid]
            if not str(new.get('manual_group') or '').strip():
                continue
            old = self.baseline_routes[rid]
            changes.append(dict(
                route_id=int(rid),
                manual_group=str(new.get('manual_group')),
                old_layer=int(old.get('target_layer') or 0),
                new_layer=int(new.get('target_layer') or 0),
                old_z_mm=float(old.get('target_z_mm') or 0.0),
                new_z_mm=float(new.get('target_z_mm') or 0.0),
                geometry_changed=bool(RB.route_signature(old) != RB.route_signature(new)),
            ))
        return changes

    def save_state(self, out_dir, include_reports=True, note=''):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        payload = self.routes_payload(note=note)
        P.write_json(out_dir / 'routes_l3d.json', payload)
        P.write_csv_rows(out_dir / 'assignment_1024.csv',
                         self.assignment_rows(), ASSIGNMENT_FIELDS)
        if include_reports:
            stats = self.crossing_stats()
            P.write_json(out_dir / 'crossing_stats.json', stats)
            P.write_json(out_dir / 'geometry_changes.json',
                         dict(changes=self.geometry_changes()))
            P.write_json(out_dir / 'manual_u_changes.json',
                         dict(changes=self.manual_changes()))
            P.write_json(out_dir / 'strategy_stats.json',
                         dict(rounds=self.round_stats,
                              cfg={k: v for k, v in self.cfg.items()}))
            P.write_json(out_dir / 'failed_attempts.json',
                         dict(attempts=self.failed[:2000],
                              count=len(self.failed)))
            P.write_csv_records(out_dir / 'optimization_history.csv', self.history)
            hashes = dict(
                routes_l3d_json=P.sha256_file(out_dir / 'routes_l3d.json'),
                assignment_1024_csv=P.sha256_file(out_dir / 'assignment_1024.csv'),
                crossing_stats_json=P.sha256_file(out_dir / 'crossing_stats.json'),
                geometry_changes_json=P.sha256_file(out_dir / 'geometry_changes.json'),
            )
            P.write_json(out_dir / 'SHA256.json', hashes)
            config = dict(
                schema='xyz_joint_config_v1',
                algorithm=P.ALGORITHM,
                cfg={k: v for k, v in self.cfg.items()},
                baseline_dir=str(self.baseline['dir']),
                baseline_routes_sha256=self.baseline['routes_sha256'],
                baseline_crossings=int(self.base_total),
                final_crossings=int(self.state.total),
                accepted_changes=len(self.history),
                seed=20261104,
                started_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
                seconds=round(time.time() - self.started, 2),
            )
            P.write_json(out_dir / 'config.json', config)
        return out_dir

    # used by geometry_changes
    baseline_crossings = {}


def baseline_route_crossings(baseline_routes):
    cache = CrossingCache(list(baseline_routes))
    return cache.per_route(), cache
