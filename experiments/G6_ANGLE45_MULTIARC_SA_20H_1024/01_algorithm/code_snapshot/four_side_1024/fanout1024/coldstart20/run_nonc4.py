# -*- coding: utf-8 -*-
"""Stage 04 -- from-scratch layer assignment + simulated annealing + joint repair.

This is the 20-height equivalent of the frozen C4-free (``nonc4``) campaign that
took the 21-height fanout-first baseline (11890 crossings) down to the accepted
E5 legal solution (2606 crossings).  The historical E3/E5 drivers were ad-hoc
scripts that were never committed, so this module reconstructs that stage from
the frozen, still-present building blocks:

* :func:`nonc4.assign_opt.measure_cost_curves` -- **simulated annealing** on the
  real chord-crossing graph, one independent run per (family, plane count);
* :func:`nonc4.assign_opt.optimise_allocation` -- small integer programme over
  how many heights each direction family gets (family compatibility rules:
  Z1V/Z1H never share a height; the opposite-corner Z2 pairs (NE,SW) and
  (SE,NW) have zero crossing chords and may share every height);
* :func:`nonc4.assign_opt.plan_structured` -- per-family SA grouping (whole
  orbits are NOT required here: this is the C4-free stage);
* :func:`nonc4.run_nc.run_standard` -- fanout -> per-height strict-D56
  multi-arc 2D routing -> 3D assembly -> true-3D world check -> joint repair.

Nothing about the manual 368 routes is discarded: they stay on their 8 physical
planes and their geometry is re-generated from the authoritative 1024-connection
data of the 20-height fanout-first run (``COLDSTART20_INIT_RUN``), never copied
from the 21-height archive.

Experiments
-----------
``E0_baseline_reproduction``  the 20-height initial layout reproduced through
                              the C4-free driver (sanity gate for the harness);
``E1_family_pure``            deterministic family-pure allocation;
``E3_family_pure_sa_seed*``   from-scratch annealing + SA family partition,
                              one run per random seed;
``E5_joint_repair_final``     best legal solution + joint repair (the accepted
                              20-height first legal checkpoint).

Usage
-----
::

    .venv\\Scripts\\python.exe -m four_side_1024.fanout1024.coldstart20.run_nonc4 all
    .venv\\Scripts\\python.exe -m four_side_1024.fanout1024.coldstart20.run_nonc4 screen
    .venv\\Scripts\\python.exe -m four_side_1024.fanout1024.coldstart20.run_nonc4 e3 --seed 11
    .venv\\Scripts\\python.exe -m four_side_1024.fanout1024.coldstart20.run_nonc4 select
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

from . import bootstrap as B          # installs the 20-height profile on import
from . import model20 as M
from . import paths20 as P20


# ===========================================================================
# helpers
# ===========================================================================
def _nonc4():
    from ..nonc4 import assign_nc, assign_opt, data, paths, run_nc, validate_nc
    return dict(assign_nc=assign_nc, assign_opt=assign_opt, data=data,
                paths=paths, run_nc=run_nc, validate_nc=validate_nc)


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False,
                               default=str) + '\n', encoding='utf-8')
    return path


def _sha256(path):
    import hashlib
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _dir_sha(index, root):
    root = Path(root)
    entries = {}
    for path in sorted(root.rglob('*')):
        if path.is_file() and path.name not in ('run.log',):
            entries[str(path.relative_to(root))] = dict(
                bytes=path.stat().st_size, sha256=_sha256(path))
    _write_json(Path(index), dict(root=str(root), files=entries))
    return entries


def _crossings_of(exp_dir):
    payload = json.loads((Path(exp_dir) / 'crossing_stats.json')
                         .read_text(encoding='utf-8'))
    totals = payload.get('totals') or {}
    return dict(crossings=int(totals.get('crossings') or 0),
                crossing_pairs=int(totals.get('crossing_pairs') or 0),
                routed=payload.get('routed'), failed=payload.get('failed'))


def prepare_profile():
    """Install the profile, bind the campaign root and assert the contract."""
    B.install()
    P20.ensure_dirs()
    nonc4 = _nonc4()
    P = nonc4['paths']
    P.EXPERIMENT_ROOT = Path(P20.NONC4_ROOT)
    nonc4['paths'].BASELINE_21H_DIR = Path(P20.INIT_RUN)
    B.assert_20_height_profile('run_nonc4')
    root = Path(P20.NONC4_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    return root, nonc4


# ===========================================================================
# E0 -- harness sanity gate
# ===========================================================================
def experiment_e0(root=None, nonc4=None, run_validate=False):
    root = Path(root or P20.NONC4_ROOT)
    nonc4 = nonc4 or _nonc4()
    run_nc, paths = nonc4['run_nc'], nonc4['paths']
    log = run_nc.make_logger(root / '_logs', tag='20h-nonc4')
    name = 'E0_baseline_reproduction'
    exp_dir = paths.experiment_dir(name)
    log(f'[E0] reproduce the 20-height fanout-first layout with the non-C4 '
        f'driver (input {P20.INIT_RUN})')
    base_rows = nonc4['data'].load_baseline_assignment()
    plan = {int(row['route_id']): int(row['target_layer']) for row in base_rows}
    core = run_nc.run_standard(name, plan=plan, experiment_dir=exp_dir,
                               log=log, budgets=(600, 1200), max_iters=2,
                               notes=['E0: 20-height fanout-first layout '
                                      'reproduced through the C4-free driver '
                                      '(harness sanity gate)'])
    summary = dict(schema='coldstart20_nonc4_e0_v1', profile=M.PROFILE,
                   experiment=name, exp_dir=str(exp_dir),
                   rows=len(core['rows']), routes=len(core['routes']),
                   failed=len(core['failed']),
                   crossing=_crossings_of(exp_dir),
                   baseline_run=str(P20.INIT_RUN))
    _write_json(root / 'E0_summary.json', summary)
    log(f'[E0] done: routed={summary["routes"]} failed={summary["failed"]} '
        f'crossings={summary["crossing"]["crossings"]}')
    return summary


# ===========================================================================
# screening: the annealing that decides how many heights each family gets
# ===========================================================================
def screen(root=None, nonc4=None, seed=11, time_budget=60.0,
           group_counts=(1, 2, 3, 4)):
    root = Path(root or P20.NONC4_ROOT)
    nonc4 = nonc4 or _nonc4()
    assign_opt, data = nonc4['assign_opt'], nonc4['data']
    run_nc = nonc4['run_nc']
    log = run_nc.make_logger(root / '_logs', tag='20h-nonc4')
    base_rows = data.load_baseline_assignment()
    log(f'[screen] measured SA cost curves: families={list(data.FAMILIES)} '
        f'group_counts={tuple(group_counts)} seed={seed} '
        f'time_budget={time_budget}s')
    curves_path = root / 'screening_cost_curves.json'
    cache = None
    if curves_path.exists():
        try:
            cache = json.loads(curves_path.read_text(encoding='utf-8'))
        except ValueError:
            cache = None
    same_cache = (cache is not None
                  and int(cache.get('seed', -1)) == int(seed)
                  and float(cache.get('time_budget_s', -1)) == float(time_budget)
                  and list(cache.get('group_counts') or []) == list(group_counts))
    if same_cache:
        log(f'[screen] reusing measured SA cost curves from {curves_path}')
        curves = {family: dict(value)
                  for family, value in cache['curves'].items()}
    else:
        curves = assign_opt.measure_cost_curves(
            base_rows, group_counts=tuple(group_counts), seed=seed, log=log,
            time_budget=time_budget)
        _write_json(curves_path,
                    dict(schema='coldstart20_nonc4_cost_curves_v1',
                         profile=M.PROFILE, seed=int(seed),
                         time_budget_s=float(time_budget),
                         group_counts=list(group_counts),
                         families=list(data.FAMILIES),
                         curves=curves))
    best = assign_opt.optimise_allocation(
        curves, max_planes=max(int(value) for value in group_counts))
    allocation = None
    if best is not None:
        counts = dict(Z1V=int(best['z1v']), Z1H=int(best['z1h']),
                      Z2_NE=int(best['ne_sw']), Z2_SE=int(best['se_nw']))
        allocation = assign_opt.allocation_from_counts(counts)
        log(f'[screen] optimal family allocation: {counts} '
            f'predicted_crossings={best["cost"]}')
    else:  # pragma: no cover - defensive
        raise RuntimeError('the allocation integer programme found no feasible '
                           'plane split for the active height profile')
    family_pure = nonc4['assign_nc'].default_allocation()
    payload = dict(schema='coldstart20_nonc4_screening_v1', profile=M.PROFILE,
                   seed=int(seed), time_budget_s=float(time_budget),
                   group_counts=list(group_counts),
                   plane_count=len(assign_opt.all_planes()),
                   z1_planes=list(data.Z1_OTHER_PLANES),
                   z2_planes=list(data.Z2_OTHER_PLANES),
                   families=list(data.FAMILIES),
                   family_labels=dict(data.FAMILY_LABELS),
                   curves={family: dict(value) for family, value in curves.items()},
                   optimal=dict(best),
                   allocation={family: [int(pid) for pid in planes]
                               for family, planes in allocation.items()},
                   predicted_crossings=int(best['cost']),
                   allocation_family_pure={
                       family: [int(pid) for pid in planes]
                       for family, planes in family_pure.items()},
                   note=('allocation = chord-crossing-graph optimum '
                         '(opposite-corner families SHARE planes; the 21-height '
                         'campaign measured this prediction as unrealisable by an '
                         'axis-aligned R15 router).  allocation_family_pure = '
                         'each direction family gets its own planes, which is the '
                         'E3 design that actually performed best.'))
    _write_json(root / 'screening_annealing.json', payload)
    log('[screen] wrote screening_annealing.json')
    return payload


# ===========================================================================
# E1 / E3 -- assignment experiments
# ===========================================================================
def experiment_family_pure(root=None, nonc4=None, order='port'):
    root = Path(root or P20.NONC4_ROOT)
    nonc4 = nonc4 or _nonc4()
    paths, run_nc = nonc4['paths'], nonc4['run_nc']
    log = run_nc.make_logger(root / '_logs', tag='20h-nonc4')
    allocation = nonc4['assign_nc'].default_allocation()
    name = 'E1_family_pure'
    exp_dir = paths.experiment_dir(name)
    log(f'[E1] C4-free deterministic family-pure allocation: '
        f'{ {k: list(v) for k, v in allocation.items()} }')
    core = run_nc.run_standard(name, allocation=allocation, order=order,
                               experiment_dir=exp_dir, log=log,
                               budgets=(600, 1200), max_iters=2,
                               notes=['E1: deterministic family-pure 20-height '
                                      'allocation (no annealing)'])
    summary = dict(schema='coldstart20_nonc4_e1_v1', profile=M.PROFILE,
                   experiment=name, order=order,
                   allocation={k: [int(p) for p in v]
                               for k, v in allocation.items()},
                   routes=len(core['routes']), failed=len(core['failed']),
                   crossing=_crossings_of(exp_dir))
    _write_json(root / 'E1_summary.json', summary)
    return summary


def experiment_e3(root=None, nonc4=None, seed=11, order='route_id',
                  counts=None, style='family_pure'):
    root = Path(root or P20.NONC4_ROOT)
    nonc4 = nonc4 or _nonc4()
    assign_opt, paths, run_nc = (nonc4['assign_opt'], nonc4['paths'],
                                 nonc4['run_nc'])
    log = run_nc.make_logger(root / '_logs', tag='20h-nonc4')
    screening_path = root / 'screening_annealing.json'
    if not screening_path.exists():
        raise FileNotFoundError(f'run the screening first: {screening_path}')
    screening = json.loads(screening_path.read_text(encoding='utf-8'))
    if style == 'family_pure':
        allocation = {family: [int(pid) for pid in planes] for family, planes
                      in screening['allocation_family_pure'].items()}
        counts = dict(planes={family: len(planes) for family, planes
                              in allocation.items()})
    else:
        if counts is None:
            counts = screening['optimal']
        allocation = assign_opt.allocation_from_counts(dict(
            Z1V=int(counts['z1v']), Z1H=int(counts['z1h']),
            Z2_NE=int(counts['ne_sw']), Z2_SE=int(counts['se_nw'])))
    base_rows = nonc4['data'].load_baseline_assignment()
    log(f'[E3] from-scratch simulated annealing: seed={seed} '
        f'order={order} counts={counts}')
    plan, summary = assign_opt.plan_structured(
        base_rows, allocation=allocation, seed=seed, order=order, log=log)
    name = (f'E3_family_pure_sa_seed{int(seed)}' if style == 'family_pure'
            else f'E2_conflict_sharing_seed{int(seed)}')
    exp_dir = paths.experiment_dir(name)
    assign_opt.save_plan(exp_dir / 'assignment_plan.json', plan,
                         dict(summary, seed=int(seed), order=order))
    core = run_nc.run_standard(
        name, plan=plan, allocation=allocation, order=order,
        experiment_dir=exp_dir, log=log, budgets=(600, 1200), max_iters=2,
        notes=[f'E3: from-scratch simulated annealing (seed={seed}, '
               f'order={order}, predicted={summary["predicted_crossings"]})'])
    result = dict(schema='coldstart20_nonc4_e3_v1', profile=M.PROFILE,
                  experiment=name, seed=int(seed), order=order,
                  allocation={k: [int(p) for p in v]
                              for k, v in allocation.items()},
                  plan_predicted_crossings=int(summary['predicted_crossings']),
                  plan_families=summary.get('families'),
                  routes=len(core['routes']), failed=len(core['failed']),
                  crossing=_crossings_of(exp_dir),
                  elapsed_s=core.get('elapsed'))
    _write_json(root / (f'E3_summary_seed{int(seed)}.json'
                        if style == 'family_pure'
                        else f'E2_summary_seed{int(seed)}.json'), result)
    log(f'[E3] seed={seed}: routed={result["routes"]} '
        f'failed={result["failed"]} crossings={result["crossing"]["crossings"]}')
    return result


# ===========================================================================
# E5 -- accept the best legal solution (first 20-height legal checkpoint)
# ===========================================================================
EXPECTED_CRITERIA = ('geometry_pass', 'contract_pass', 'validation_pass')


def _validate_dir(nonc4, exp_dir, log):
    report = nonc4['validate_nc'].validate_experiment(Path(exp_dir), log=log)
    return report


def select_best(root=None, nonc4=None, min_routed=1024):
    root = Path(root or P20.NONC4_ROOT)
    nonc4 = nonc4 or _nonc4()
    run_nc = nonc4['run_nc']
    log = run_nc.make_logger(root / '_logs', tag='20h-nonc4')
    candidates = []
    for path in sorted(root.glob('E[123]_*')):
        if not (path / 'crossing_stats.json').exists():
            continue
        try:
            crossing = _crossings_of(path)
        except Exception:
            continue
        candidates.append(dict(name=path.name, exp_dir=str(path),
                               routes=crossing['routed'],
                               failed=crossing['failed'],
                               crossings=crossing['crossings'],
                               crossing_pairs=crossing['crossing_pairs']))
    if not candidates:
        raise RuntimeError(f'no candidate experiment under {root}')
    candidates.sort(key=lambda item: (item['failed'] or 0,
                                      item['crossings'] or 10 ** 9))
    log('[select] candidates: ' + json.dumps(candidates, ensure_ascii=False))
    chosen = None
    for candidate in candidates:
        report = _validate_dir(nonc4, candidate['exp_dir'], log)
        candidate['validation_pass'] = bool(report.get('validation_pass'))
        candidate['geometry_pass'] = bool(report.get('geometry_pass'))
        candidate['contract_pass'] = bool(report.get('contract_pass'))
        log(f"[select] {candidate['name']}: routed={candidate['routes']} "
            f"crossings={candidate['crossings']} "
            f"validation_pass={candidate['validation_pass']}")
        if (candidate['validation_pass']
                and int(candidate['routes'] or 0) >= int(min_routed)
                and not int(candidate['failed'] or 0)):
            chosen = candidate
            break
    payload = dict(schema='coldstart20_nonc4_selection_v1', profile=M.PROFILE,
                   min_routed=int(min_routed), candidates=candidates,
                   chosen=chosen)
    _write_json(root / 'selection.json', payload)
    if chosen is None:
        log('[select] NO fully legal candidate yet -- joint repair required')
        return payload
    # ---- materialise the accepted E5 checkpoint -------------------------
    accepted = Path(P20.E5_DIR)
    if accepted.exists():
        shutil.rmtree(accepted)
    shutil.copytree(chosen['exp_dir'], accepted)
    for name in ('assignment_1024.csv', 'routes_l3d.json', 'layer_planes.json',
                 'physical_layer_stack.json', 'process_rules.json',
                 'crossing_stats.json', 'validation.json',
                 'failed_routes.json', 'final_stats.json'):
        src = accepted / name
        if src.exists():
            _write_json(accepted / f'{name}.sha256.json',
                        dict(file=name, sha256=_sha256(src)))
    _dir_sha(accepted / 'SHA256_INDEX.json', accepted)
    payload['accepted_dir'] = str(accepted)
    payload['accepted_routes_sha256'] = _sha256(accepted / 'routes_l3d.json')
    payload['accepted_crossings'] = chosen['crossings']
    _write_json(root / 'selection.json', payload)
    (accepted / 'ACCEPTED.json').write_text(
        json.dumps(dict(schema='coldstart20_accepted_solution_v1',
                        profile=M.PROFILE,
                        source_experiment=chosen['name'],
                        routes=chosen['routes'], failed=chosen['failed'],
                        crossings=chosen['crossings'],
                        crossing_pairs=chosen['crossing_pairs'],
                        routes_sha256=payload['accepted_routes_sha256'],
                        validated=True), indent=1, ensure_ascii=False) + '\n',
        encoding='utf-8')
    log(f"[select] ACCEPTED {chosen['name']} -> {accepted} "
        f"(crossings={chosen['crossings']})")
    return payload


# ===========================================================================
# report
# ===========================================================================
def stage_summary(root=None):
    root = Path(root or P20.NONC4_ROOT)
    entries = []
    for path in sorted(root.glob('E[0-9]*')):
        stats = path / 'crossing_stats.json'
        if not stats.exists():
            continue
        crossing = _crossings_of(path)
        entries.append(dict(experiment=path.name, **crossing))
    payload = dict(schema='coldstart20_nonc4_stage_summary_v1',
                   profile=M.PROFILE, programme_root=str(root),
                   experiments=entries)
    _write_json(Path(P20.REPORTS) / 'stage04_nonc4_summary.json', payload)
    return payload


# ===========================================================================
# CLI
# ===========================================================================
def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('e0')
    p_screen = sub.add_parser('screen')
    p_screen.add_argument('--seed', type=int, default=11)
    p_screen.add_argument('--time-budget', type=float, default=60.0)
    sub.add_parser('e1')
    p_e3 = sub.add_parser('e3')
    p_e3.add_argument('--seed', type=int, default=11)
    p_e3.add_argument('--order', default='route_id',
                      choices=['port', 'route_id', 'round_robin'])
    p_e3.add_argument('--style', default='family_pure',
                      choices=['family_pure', 'conflict_sharing'])
    p_e2 = sub.add_parser('e2')
    p_e2.add_argument('--seed', type=int, default=11)
    p_e2.add_argument('--order', default='route_id',
                      choices=['port', 'route_id', 'round_robin'])
    sub.add_parser('select')
    sub.add_parser('summary')
    p_all = sub.add_parser('all')
    p_all.add_argument('--seeds', default='11,23,37,51')
    p_all.add_argument('--time-budget', type=float, default=60.0)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    started = time.time()
    root, nonc4 = prepare_profile()
    if args.command == 'e0':
        result = experiment_e0(root, nonc4)
    elif args.command == 'screen':
        result = screen(root, nonc4, seed=args.seed,
                        time_budget=args.time_budget)
    elif args.command == 'e1':
        result = experiment_family_pure(root, nonc4)
    elif args.command == 'e3':
        result = experiment_e3(root, nonc4, seed=args.seed, order=args.order,
                               style=args.style)
    elif args.command == 'e2':
        result = experiment_e3(root, nonc4, seed=args.seed, order=args.order,
                               style='conflict_sharing')
    elif args.command == 'select':
        result = select_best(root, nonc4)
    elif args.command == 'summary':
        result = stage_summary(root)
    elif args.command == 'all':
        experiment_e0(root, nonc4)
        screen(root, nonc4, seed=11, time_budget=args.time_budget)
        experiment_family_pure(root, nonc4)
        experiment_e3_variants = [int(value) for value
                                  in str(args.seeds).split(',')
                                  if str(value).strip()]
        for seed in experiment_e3_variants:
            experiment_e3(root, nonc4, seed=seed, style='family_pure')
        experiment_e3(root, nonc4, seed=11, style='conflict_sharing')
        result = select_best(root, nonc4)
        stage_summary(root)
    else:  # pragma: no cover
        raise SystemExit(f'unknown command {args.command!r}')
    print(json.dumps(dict(command=args.command,
                          elapsed_s=round(time.time() - started, 1),
                          result=result), indent=1, ensure_ascii=False,
                     default=str)[:4000], flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

