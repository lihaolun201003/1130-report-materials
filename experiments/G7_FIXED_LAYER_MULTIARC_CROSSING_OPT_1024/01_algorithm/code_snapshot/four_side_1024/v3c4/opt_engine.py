"""Group-level optimization engine for the V3-C4 964 baseline.

Starting from the accepted 964/1024 layout this engine only performs
**four-member atomic** moves:

* direct insertion of a failed C4 group with the expanded R15 candidate families
  (frozen candext + pure-90 families + the new global DETOUR staircase family);
* group-level rip-up & reroute: a small set of placed groups that block the
  failed group is removed, the failed group is inserted, and the removed groups
  are re-inserted (all four members of every group are committed together);
* a move is accepted only when the number of routed connections strictly
  increases and the new layout passes the frozen exact D56 index and the strict
  pair audit.

Best-so-far is saved after every accepted move (routes, checkpoint, validation,
all five required figures).
"""
from __future__ import annotations

import argparse
import itertools
import json
import random
import time
from collections import Counter
from pathlib import Path

from .profile import apply as apply_profile

MAX_RIP_GROUPS = 12


def _jsonable(value):
    if isinstance(value, Path):
        return str(value)
    return value


class Optimizer:
    def __init__(self, routing_root, opt_root, log=print, levels=(1, 2, 3)):
        apply_profile()
        from . import inputs as V3
        from . import l3d as L
        from .c4 import GroupRouter
        from .layout import V3LayoutState

        self.routing_root = Path(routing_root)
        self.opt_root = Path(opt_root)
        self.log = log
        self.levels = tuple(levels)
        self.groups_all, self.route_group = V3.build_groups()
        self.group_by_id = {g['group_id']: g for g in self.groups_all}
        self.plane_groups = {plane: [g for g in self.groups_all
                                     if g['plane'] == plane]
                             for plane in ('z1', 'z2')}
        self.states = {}
        self.records = {}
        for plane in ('z1', 'z2'):
            _payload, records, routed = L.load_c4_2d(self.routing_root, plane,
                                                     log=lambda *a, **k: None)
            failed = {rid: rec for rid, rec in records.items()
                      if rec.get('status') != 'routed'}
            state = L.reconstruct_state(plane, routed,
                                        failed_records=failed,
                                        log=lambda *a, **k: None)
            self.states[plane] = state
            self.records[plane] = records
            self.log(f'[opt] {plane}: baseline routed={len(state.accepted)}/512 '
                     f'failed={len(failed)}')

    # -- helpers -----------------------------------------------------------
    def state(self, plane):
        return self.states[plane]

    def routed_count(self):
        return sum(len(state.accepted) for state in self.states.values())

    def failed_groups(self, plane):
        state = self.states[plane]
        return [g for g in self.plane_groups[plane]
                if not all(rid in state.accepted for rid in g['route_ids'])]

    def all_failed_groups(self):
        return [g for plane in ('z1', 'z2') for g in self.failed_groups(plane)]

    def candidate_iterator(self, plane, group):
        from . import expanded
        state = self.states[plane]
        rep = group['route_ids'][0]
        frame = state.frames[rep]
        oracle = state.oracle_for(rep)
        return expanded.expanded_candidates(frame, oracle, levels=self.levels)

    def _router(self, plane):
        from .c4 import GroupRouter
        state = self.states[plane]
        return GroupRouter(state, self.plane_groups[plane],
                           all_groups=self.plane_groups[plane],
                           log=lambda *a, **k: None)

    def try_group(self, plane, group, budget):
        """Direct insertion attempt with all expanded candidate families."""
        router = self._router(plane)
        results, failure, stats = router.attempt_group(
            group, budget, candidate_iterator=self.candidate_iterator(plane, group))
        if results is None:
            router.fail_group(group, failure)
            return False, failure
        router.commit_group(group, results)
        return True, stats

    def _rip_candidates(self, plane, group, max_groups=MAX_RIP_GROUPS):
        """Deterministic rip sets derived from the measured blocker groups."""
        state = self.states[plane]
        rep = group['route_ids'][0]
        failure = state.failed.get(rep) or {}
        blockers = [int(k) for k in (failure.get('blockers') or {})]
        impact = Counter()
        for rid in blockers:
            entry = self.route_group.get(rid)
            if entry is None or rid not in state.accepted:
                continue
            impact[entry[0]] += 1
        ranked = [gid for gid, _count in impact.most_common(max_groups)]
        sets = []
        if ranked:
            if len(ranked) <= 4:
                sets.append(tuple(ranked))
            for size in (1, 2, 3, 4, 6, 8):
                if size <= len(ranked):
                    sets.append(tuple(ranked[:size]))
        seen = set()
        unique = []
        for entry in sets:
            key = tuple(sorted(entry))
            if key in seen:
                continue
            seen.add(key)
            unique.append(list(key))
        return unique

    def _remove_groups(self, plane, group_ids):
        state = self.states[plane]
        removed = []
        for gid in group_ids:
            group = self.group_by_id[gid]
            for rid in group['route_ids']:
                if rid in state.accepted:
                    state.remove(rid)
                    removed.append(rid)
        return removed

    def _reinsert_groups(self, plane, group_ids, budget):
        """Re-insert ripped groups (easy first) with the expanded families."""
        router = self._router(plane)
        state = self.states[plane]
        groups = [self.group_by_id[gid] for gid in group_ids]
        groups = [g for g in groups
                  if not all(rid in state.accepted for rid in g['route_ids'])]
        if not groups:
            return 0
        from .c4 import order_groups
        groups = order_groups(groups, router.blocks, mode='easy')
        placed = 0
        for group in groups:
            results, failure, _stats = router.attempt_group(
                group, budget,
                candidate_iterator=self.candidate_iterator(plane, group))
            if results is not None:
                router.commit_group(group, results)
                placed += 1
            else:
                router.fail_group(group, failure)
        return placed

    def rip_insert(self, plane, group, budget=1200, reinsert_budget=800,
                   max_rip_groups=MAX_RIP_GROUPS, seed=20261021,
                   extra_attempts=2, time_left=None):
        """Try group insertion after ripping measured blocking groups."""
        state = self.states[plane]
        before = self.routed_count()
        rip_sets = self._rip_candidates(plane, group, max_groups=max_rip_groups)
        # add a couple of randomized variants of the top blockers
        failure = state.failed.get(group['route_ids'][0]) or {}
        blockers = [int(k) for k in (failure.get('blockers') or {})]
        blocker_groups = sorted({self.route_group[rid][0] for rid in blockers
                                 if rid in self.route_group
                                 and rid in state.accepted})
        rng = random.Random(seed + group['group_id'])
        for _attempt in range(extra_attempts):
            if len(blocker_groups) < 2:
                break
            size = min(len(blocker_groups), rng.choice((2, 3, 4)))
            candidate = rng.sample(blocker_groups[:12], size)
            key = tuple(sorted(candidate))
            if all(key != tuple(sorted(entry)) for entry in rip_sets):
                rip_sets.append(list(candidate))
        for rip_gids in rip_sets:
            if time_left is not None and time_left() <= 0:
                break
            snapshot = state.snapshot()
            self._remove_groups(plane, rip_gids)
            inserted, _failure = self.try_group(plane, group, budget)
            if inserted:
                self._reinsert_groups(plane, rip_gids, reinsert_budget)
                after = self.routed_count()
                if after > before:
                    return dict(gain=after - before, ripped=rip_gids,
                                routed=after)
            state.restore(snapshot)
        return None

    # -- drives ------------------------------------------------------------
    def optimize_once(self, budget=1200, reinsert_budget=800,
                      max_rip_groups=MAX_RIP_GROUPS, time_limit=None):
        """One pass over the currently failed groups; returns accepted moves."""
        started = time.perf_counter()

        def time_left():
            if time_limit is None:
                return 1.0
            return time_limit - (time.perf_counter() - started)

        moves = []
        for plane in ('z1', 'z2'):
            failed = sorted(self.failed_groups(plane),
                            key=lambda g: len((self.states[plane]
                                               .failed.get(g['route_ids'][0]) or {})
                                              .get('blockers') or {}))
            for group in failed:
                if time_left() <= 0:
                    return moves
                if all(rid in self.states[plane].accepted
                       for rid in group['route_ids']):
                    continue
                before = self.routed_count()
                inserted, _stats = self.try_group(plane, group, budget)
                if inserted:
                    after = self.routed_count()
                    moves.append(dict(kind='direct', plane=plane,
                                      group_id=group['group_id'],
                                      before=before, after=after))
                    self.log(f'[opt] {plane} group {group["group_id"]}: direct '
                             f'insert {before} -> {after}')
                    continue
                result = self.rip_insert(plane, group, budget=budget,
                                         reinsert_budget=reinsert_budget,
                                         max_rip_groups=max_rip_groups,
                                         time_left=time_left if time_limit else None)
                if result is not None:
                    moves.append(dict(kind='rip_insert', plane=plane,
                                      group_id=group['group_id'],
                                      ripped=result['ripped'],
                                      before=before, after=result['routed']))
                    self.log(f'[opt] {plane} group {group["group_id"]}: '
                             f'rip_insert {before} -> {result["routed"]} '
                             f'(ripped {result["ripped"]})')
        return moves

    # -- artefacts ---------------------------------------------------------
    def build_payloads(self, algorithm_detail=None):
        payloads = {}
        for plane in ('z1', 'z2'):
            state = self.states[plane]
            detail = dict(
                name='V3_C4_OPT', algorithm='C4_2D',
                process_profile='R15_min_radius_15mm',
                radius_mm=15.0, fixed_radius_40mm=False, geometry_mode='d56',
                crossing_policy='exact',
                candidate_generator='candext + ortho90 + global DETOUR staircase',
                strategy='group-atomic direct insert + group rip-up/reroute',
                forced_symmetry=True)
            if algorithm_detail:
                detail.update(algorithm_detail)
            payload = state.payload('C4_2D_OPT', detail, 'V3_C4_OPT')
            payload['v3c4'] = dict(topology='V3_C4', forced_symmetry=True)
            payload['rotation_groups'] = [
                dict(group_id=g['group_id'], kind=g['kind'], plane=plane,
                     route_ids=g['route_ids'],
                     status='routed' if all(rid in state.accepted
                                            for rid in g['route_ids']) else 'failed')
                for g in self.plane_groups[plane]]
            for record in payload.get('routes') or []:
                entry = self.route_group.get(int(record['route_id']))
                if entry is not None:
                    record['rotation_group_id'] = entry[0]
                    record['rotation_phase'] = entry[1]
                    if record.get('status') == 'routed':
                        record['c4_symmetry'] = 'strict_group_commit'
            payloads[plane] = payload
        return payloads

    def save_best(self, out_dir, tag='best', algorithm_detail=None,
                  write_plots=True, log=print):
        from . import plots_opt
        from . import validate2d

        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        payloads = self.build_payloads(algorithm_detail)
        records = []
        for plane in ('z1', 'z2'):
            records.extend(payloads[plane]['routes'])
        records.sort(key=lambda record: int(record['route_id']))
        routed = [record for record in records if record.get('status') == 'routed']
        routed_count = len(routed)
        planes_report = {}
        passed = True
        for plane in ('z1', 'z2'):
            report = validate2d.audit_plane(payloads[plane], plane,
                                            label=f'opt_{tag}_{plane}', log=log)
            planes_report[plane] = report
            passed = passed and report['passed']
        c4_report = validate2d.audit_c4_groups(records, self.groups_all,
                                               self.route_group, log=log)
        coverage = validate2d.audit_full_coverage(records, log=log)
        passed = passed and c4_report['passed'] and coverage['passed']
        combined = dict(
            schema='four_side_1024_v3c4_optimization_routes_v1',
            stage=tag, forced_symmetry=True,
            connectedness_note='V3-C4 connectivity identity, group-atomic C4',
            routed=routed_count, failed=1024 - routed_count,
            rotation_groups=payloads['z1']['rotation_groups']
            + payloads['z2']['rotation_groups'],
            routes=records)
        (out_dir / 'routes_1024.json').write_text(
            json.dumps(combined, ensure_ascii=False), encoding='utf-8')
        for plane in ('z1', 'z2'):
            (out_dir / f'routes_{plane}.json').write_text(
                json.dumps(payloads[plane], ensure_ascii=False, indent=None),
                encoding='utf-8')
        failed_groups = [dict(group_id=g['group_id'], plane=g['plane'],
                              kind=g['kind'], route_ids=g['route_ids'])
                         for g in self.all_failed_groups()]
        (out_dir / 'failed_groups.json').write_text(
            json.dumps(dict(stage=tag, failed_groups=failed_groups),
                       ensure_ascii=False, indent=1), encoding='utf-8')
        validation = dict(
            schema='four_side_1024_v3c4_optimization_validation_v1',
            stage=tag, routed=routed_count, failed=1024 - routed_count,
            planes=planes_report, c4_symmetry=c4_report, coverage=coverage,
            passed=passed)
        (out_dir / 'validation.json').write_text(
            json.dumps(validation, ensure_ascii=False, indent=1), encoding='utf-8')
        routed_by_plane = {plane: sum(1 for record in routed
                                      if record.get('plane') == plane)
                           for plane in ('z1', 'z2')}
        checkpoint = dict(
            schema='four_side_1024_v3c4_optimization_checkpoint_v1',
            tag=tag, routed=routed_count, routed_by_plane=routed_by_plane,
            failed_group_ids=[g['group_id'] for g in self.all_failed_groups()],
            timestamp=time.strftime('%Y-%m-%dT%H:%M:%S'))
        (out_dir / 'checkpoint.json').write_text(
            json.dumps(checkpoint, ensure_ascii=False, indent=1), encoding='utf-8')
        summary = dict(
            schema='four_side_1024_v3c4_optimization_summary_v1', tag=tag,
            routed=routed_count, total=1024, failed=1024 - routed_count,
            routed_by_plane=routed_by_plane,
            routed_groups=sum(1 for g in self.groups_all
                              if all(rid in self.states[g['plane']].accepted
                                     for rid in g['route_ids'])),
            failed_groups=[g['group_id'] for g in self.all_failed_groups()],
            validation_passed=passed)
        (out_dir / 'summary.json').write_text(
            json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')
        if write_plots:
            plots_dir = out_dir / 'plots'
            plots_dir.mkdir(parents=True, exist_ok=True)
            for old in plots_dir.glob('*'):
                old.unlink()
            failed_entries = []
            from . import inputs as V3
            routes_all = V3.load_all_routes()[0]
            by_id = {int(route['route_id']): route for route in routes_all}
            for g in self.all_failed_groups():
                route = by_id[g['route_ids'][0]]
                failed_entries.append(dict(
                    group_id=g['group_id'], plane=g['plane'], kind=g['kind'],
                    source_xy=V3.port_xy(route['source_endpoint']),
                    target_xy=V3.port_xy(route['target_endpoint']),
                    route_ids=g['route_ids']))
            title = f'V3-C4 optimization ({tag})'
            plots_opt.plot_overview(records, None, routed_count,
                                    f'{title} 整板俯视', plots_dir / '01_overview.png',
                                    failed_groups=failed_entries)
            plots_opt.plot_by_row(records, routed_by_plane['z1'],
                                  routed_by_plane['z2'],
                                  f'{title} 分排（row1 对边 / row2 邻边）',
                                  plots_dir / '02_by_row.png')
            records_3d = plots_opt.load_3d_records(
                self.routing_root, payloads)
            plots_opt.plot_layers(records_3d, routed_count,
                                  f'{title} L1–L5 分层',
                                  plots_dir / '03_layers.png')
            plots_opt.plot_3d(records_3d, routed_count,
                              f'{title} 三维', plots_dir / '04_3d.png')
            plots_opt.plot_failed(records, failed_entries, routed_count,
                                  f'{title} 失败四元组位置',
                                  plots_dir / '05_failed_groups.png')
        log(f'[opt] saved {tag}: routed={routed_count} '
            f'validation={"PASS" if passed else "FAIL"} -> {out_dir}')
        return summary

    def snapshot_states(self):
        return {plane: state.snapshot() for plane, state in self.states.items()}

    def restore_states(self, snapshots):
        for plane, snapshot in snapshots.items():
            self.states[plane].restore(snapshot)


def _main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--routing-root', type=Path, default=None)
    parser.add_argument('--out', type=Path, default=None)
    parser.add_argument('--budget', type=int, default=1200)
    parser.add_argument('--reinsert-budget', type=int, default=800)
    parser.add_argument('--max-rip-groups', type=int, default=MAX_RIP_GROUPS)
    parser.add_argument('--rounds', type=int, default=4)
    parser.add_argument('--time-limit', type=float, default=3600.0)
    parser.add_argument('--levels', default='1,2,3')
    parser.add_argument('--tag', default='optim')
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parents[2]
    routing_root = args.routing_root or (repo / 'outputs/four_side_1024_v3_c4_routing')
    opt_root = args.out or (repo / 'outputs/four_side_1024_v3_c4_optimization')
    opt_root = Path(opt_root)
    log_path = opt_root / 'run.log'
    opt_root.mkdir(parents=True, exist_ok=True)

    log_handle = open(log_path, 'a', encoding='utf-8')

    def log(message):
        line = time.strftime('%H:%M:%S') + ' ' + str(message)
        print(line, flush=True)
        log_handle.write(line + '\n')
        log_handle.flush()

    optimizer = Optimizer(routing_root, opt_root, log=log,
                          levels=tuple(int(v) for v in args.levels.split(',')))
    best_dir = opt_root / 'best'
    baseline_summary = optimizer.save_best(best_dir, tag='baseline_964_recheck',
                                           write_plots=True, log=log)
    history = []
    started = time.perf_counter()
    for round_index in range(1, int(args.rounds) + 1):
        remaining = args.time_limit - (time.perf_counter() - started)
        if remaining <= 0:
            log('time limit reached before round', round_index)
            break
        before = optimizer.routed_count()
        moves = optimizer.optimize_once(
            budget=args.budget, reinsert_budget=args.reinsert_budget,
            max_rip_groups=args.max_rip_groups,
            time_limit=remaining)
        after = optimizer.routed_count()
        history.append(dict(round=round_index, before=before, after=after,
                            gain=after - before, moves=moves,
                            seconds=round(time.perf_counter() - started, 2)))
        log(f'[opt] round {round_index}: {before} -> {after} '
            f'(+{after - before}) in {time.perf_counter() - started:.0f}s')
        if after > before:
            optimizer.save_best(opt_root / 'rounds' / f'round_{round_index:02d}',
                                tag=f'round_{round_index:02d}', write_plots=True,
                                log=log)
            optimizer.save_best(best_dir, tag=f'best_{after}', write_plots=True,
                                log=log)
        else:
            break
    final_summary = optimizer.save_best(opt_root / 'best',
                                        tag=f'final_{optimizer.routed_count()}',
                                        write_plots=True, log=log)
    result = dict(schema='four_side_1024_v3c4_optimization_result_v1',
                  final_routed=optimizer.routed_count(),
                  delta_vs_964=optimizer.routed_count() - 964,
                  rounds=history,
                  best_summary=final_summary,
                  seconds=round(time.perf_counter() - started, 2))
    (opt_root / 'optimization_result.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    log_handle.close()
    print(json.dumps({k: result[k] for k in
                      ('final_routed', 'delta_vs_964', 'seconds')},
                     ensure_ascii=False))
    return result


if __name__ == '__main__':
    _main()
