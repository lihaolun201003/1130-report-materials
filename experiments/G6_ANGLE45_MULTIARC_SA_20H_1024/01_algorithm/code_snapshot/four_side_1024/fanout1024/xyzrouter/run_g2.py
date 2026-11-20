# -*- coding: utf-8 -*-
"""G2 experiment: manual U may change physical height (XY body shape kept).

G2a : one new shared body height per original manual group.
G2b : independent body height per manual route.

The height assignment is optimised **jointly** with the non-manual routing
(DESIGN 3.2 / task section 8.3): the loop alternates between

1. trying each manual group's / route's candidate heights and taking the best
   one under a small crossing-delta budget, then
2. re-optimising the 656 non-manual routes with the full XY+Z joint router.

Everything is validated with ``manual_policy='height_only'``: identity / ports
fixed, XY body geometry identical, body height + R15 end transitions may change.

Usage::

    python -m four_side_1024.fanout1024.xyzrouter.run_g2 \
        --phase a --start-from <G1 dir> --out <G2a dir> --rounds 2
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024.xyzrouter import experiment as E  # noqa: E402
from four_side_1024.fanout1024.xyzrouter import manual_reheight as MR  # noqa: E402
from four_side_1024.fanout1024.xyzrouter import paths as P  # noqa: E402


def log(message):
    print(message, flush=True)


def parse_cfg(text):
    cfg = {}
    for chunk in (text or '').split(','):
        chunk = chunk.strip()
        if not chunk:
            continue
        key, _, value = chunk.partition('=')
        cfg[key.strip()] = json.loads(value.strip())
    return cfg


def start_dir(value):
    if value in (None, '', 'baseline', 'auto'):
        return None
    return Path(value)


def choose_group_height(state, group, delta_budget, log=log):
    """Best group height under a crossing-delta budget, jointly with routing."""
    candidates = MR.group_shared_heights(state, group)
    z_current = MR.current_height(state, group[0])
    best_row = None
    audit = []
    for layer_id, z in candidates:
        if abs(float(z) - z_current) < 1e-9:
            audit.append(dict(layer=int(layer_id), z=float(z), delta=0,
                              crowding=MR.crowding_score(state),
                              unchanged=True))
            if best_row is None:
                best_row = dict(layer=int(layer_id), z=float(z), delta=0,
                                crowding=MR.crowding_score(state),
                                unchanged=True, replacements=None)
            continue
        replacements, failures = MR.plan_group_shift(state, group, layer_id, z)
        if len(replacements) != len(group):
            audit.append(dict(layer=int(layer_id), z=float(z), delta=None,
                              skipped='incomplete', failures=failures[:5]))
            continue
        evaluation = MR.evaluate_shift(state, replacements)
        if not evaluation['ok']:
            audit.append(dict(layer=int(layer_id), z=float(z), delta=None,
                              skipped='3d', kinds=evaluation.get('kinds')))
            continue
        row = dict(layer=int(layer_id), z=float(z),
                   delta=int(evaluation['delta']),
                   crowding=MR.crowding_score(state, replacements),
                   replacements=replacements, unchanged=False)
        audit.append({key: value for key, value in row.items()
                      if key != 'replacements'})
        if best_row is None or (row['delta'], row['crowding']) < \
                (best_row['delta'], best_row['crowding']):
            best_row = row
    if best_row is None or best_row.get('unchanged'):
        return best_row, audit
    if best_row['delta'] > int(delta_budget):
        log('    best move delta=%+d exceeds budget %+d -> keep current height'
            % (best_row['delta'], int(delta_budget)))
        return None, audit
    return best_row, audit


def g2a_joint(state, rounds=2, delta_budget=80, log=log):
    groups = MR.manual_groups(state)
    history = []
    for round_index in range(int(rounds)):
        moves = 0
        for group_name, group in groups.items():
            best, audit = choose_group_height(state, group, delta_budget)
            if best is None or best.get('unchanged'):
                history.append(dict(round=round_index + 1, group=group_name,
                                    action='keep', audit=audit))
                continue
            state.batch_commit(best['replacements'],
                               note='g2a_%s_L%d' % (group_name, best['layer']))
            moves += 1
            history.append(dict(round=round_index + 1, group=group_name,
                                action='moved', chosen=best, audit=audit))
            log('[g2a] %s -> L%s z=%+0.3f delta=%+d total=%d' % (
                group_name, best['layer'], best['z'], best['delta'],
                state.total))
        if moves == 0:
            break
    return history


def g2b_joint(state, rounds=1, delta_budget=2, log=log):
    history = []
    for round_index in range(int(rounds)):
        moved = 0
        for rid in MR.manual_route_ids(state):
            record = MR.reheight_one_route(state, rid)
            if record is None:
                continue
            if record['delta'] > int(delta_budget):
                continue
            applied = MR.apply_route_reheight(state, rid, record)
            history.append(dict(round=round_index + 1, route_id=int(rid),
                                delta=int(record['delta']),
                                old_layer=int(applied['old_layer']),
                                new_layer=int(applied['new_layer']),
                                old_z=applied['old_z'], new_z=applied['new_z'],
                                total_after=int(state.total)))
            moved += 1
        state.prim_grids = {}
        log('[g2b] round %d: %d manual routes re-heighted, total=%d' % (
            round_index + 1, moved, state.total))
        if moved == 0:
            break
    return history


def main(argv=None):
    parser = argparse.ArgumentParser(description='G2 manual-U height-only experiments')
    parser.add_argument('--phase', choices=['a', 'b', 'audit-a', 'audit-b'],
                        default='a')
    parser.add_argument('--start-from', default='')
    parser.add_argument('--out-a', default=str(P.DIRS['G2a']))
    parser.add_argument('--out-b', default=str(P.DIRS['G2b']))
    parser.add_argument('--rounds', type=int, default=2,
                        help='joint rounds (reheight + non-manual re-routing)')
    parser.add_argument('--round-seconds', type=float, default=700.0)
    parser.add_argument('--delta-budget', type=int, default=80,
                        help='G2a: allowed immediate crossing increase per group')
    parser.add_argument('--route-delta-budget', type=int, default=2,
                        help='G2b: allowed immediate crossing increase per route')
    parser.add_argument('--top', type=int, default=None)
    parser.add_argument('--cfg', default='')
    parser.add_argument('--skip-validate', action='store_true')
    args = parser.parse_args(argv)
    P.ensure_dirs()
    started = time.time()

    if args.phase in ('audit-a', 'audit-b'):
        baseline, state = E.load_state(start_dir(args.start_from), log=log)
        if args.phase == 'audit-a':
            groups = MR.manual_groups(state)
            audit = []
            for name, group in groups.items():
                best, rows = choose_group_height(state, group, 10 ** 6, log=log)
                audit.append(dict(group=name, members=len(group),
                                  chosen=best, candidates=rows))
            target = Path(args.out_a) / 'group_height_audit.json'
            P.write_json(target, dict(audit=audit))
            log('[g2a-audit] written %s' % target)
        else:
            rows = []
            for rid in MR.manual_route_ids(state):
                record = MR.reheight_one_route(state, rid)
                rows.append(dict(route_id=int(rid),
                                 best=(None if record is None else
                                       dict(delta=int(record['delta']),
                                            layer=int(record['layer']),
                                            z=float(record['z'])))))
            target = Path(args.out_b) / 'route_height_audit.json'
            P.write_json(target, dict(audit=rows))
            log('[g2b-audit] written %s' % target)
        return 0

    if args.phase == 'a':
        baseline, state = E.load_state(start_dir(args.start_from), log=log)
        run_a = Path(args.out_a)
        log('=' * 78)
        log('[g2a] start=%s total=%d' % (baseline['dir'], state.total))
        history = g2a_joint(state, rounds=args.rounds,
                            delta_budget=args.delta_budget, log=log)
        P.write_json(run_a / 'manual_group_reheight.json',
                     dict(history=history))
        E.save_stage(state, baseline, run_a,
                     note='G2a manual groups re-heighted (height_only)', log=log)
        optimizer, result = E.run_nonmanual_optimizer(
            state, baseline, run_a, rounds=1,
            round_seconds=args.round_seconds, cfg=parse_cfg(args.cfg),
            top=args.top, label='g2a', log=log)
        summary = dict(experiment='G2a_manual_group_reheight',
                       start_dir=baseline['dir'],
                       start_crossings=int(optimizer.base_total),
                       final_crossings=int(state.total),
                       reheight_history=history,
                       accepted_nonmanual=len(optimizer.history),
                       elapsed_seconds=round(time.time() - started, 2))
        E.write_summary(run_a, summary)
        log('[g2a] final total=%d (start %d)' % (state.total,
                                                 optimizer.base_total))
        if not args.skip_validate:
            try:
                E.validate_stage(run_a, str(P.baseline_dir()),
                                 run_a / 'validation', 'height_only', log=log)
            except Exception as error:  # noqa: BLE001
                log('[g2a] validation failed: %s' % error)
        return 0

    # phase b
    baseline, state = E.load_state(start_dir(args.start_from), log=log)
    run_b = Path(args.out_b)
    log('=' * 78)
    log('[g2b] start=%s total=%d' % (baseline['dir'], state.total))
    start_total = int(state.total)
    history = g2b_joint(state, rounds=args.rounds,
                        delta_budget=args.route_delta_budget, log=log)
    P.write_json(run_b / 'manual_route_reheight.json', dict(history=history))
    E.save_stage(state, baseline, run_b,
                 note='G2b per-route manual height (height_only)', log=log)
    optimizer, result = E.run_nonmanual_optimizer(
        state, baseline, run_b, rounds=1, round_seconds=args.round_seconds,
        cfg=parse_cfg(args.cfg), top=args.top, label='g2b', log=log)
    summary = dict(experiment='G2b_manual_route_reheight',
                   start_dir=baseline['dir'],
                   start_crossings=start_total,
                   final_crossings=int(state.total),
                   reheight_history=history,
                   accepted_nonmanual=len(optimizer.history),
                   elapsed_seconds=round(time.time() - started, 2))
    E.write_summary(run_b, summary)
    log('[g2b] final total=%d' % state.total)
    if not args.skip_validate:
        try:
            E.validate_stage(run_b, str(P.baseline_dir()), run_b / 'validation',
                             'height_only', log=log)
        except Exception as error:  # noqa: BLE001
            log('[g2b] validation failed: %s' % error)
    return 0


if __name__ == '__main__':
    sys.exit(main())
