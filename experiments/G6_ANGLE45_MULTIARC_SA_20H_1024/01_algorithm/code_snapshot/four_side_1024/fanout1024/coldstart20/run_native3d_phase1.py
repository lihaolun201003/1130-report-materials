# -*- coding: utf-8 -*-
"""Stage 05 -- Native 3D Phase 1 (experiments A / B / C) on the 20-height model.

Allows the waveguide body to change height *mid-path* through a real R15
double-arc S-curve (:func:`native3d.transition.build_excursion` ->
``fsd25d.path3d.make_transition``), never a vertical polyline or an instant jump.

Frozen stage semantics (unchanged, re-used in full)
--------------------------------------------------
A  single-route mid-body excursion: legal windows + R15 geometry verification
   (``native3d.run_a``  -- A0 geometry tests, A1 real 1024-channel scan,
   A2 single-route result);
B  batch avoidance and multi-strategy candidate comparison (``native3d.run_b``);
C  global layer-change / crossing optimisation (``native3d.global_optimizer``).

Start point: the 20-height accepted joint-repair legal solution
``COLDSTART20_E5_DIR`` (stage 04); no 21-height Phase-1 route is ever loaded.
The stage output is ``COLDSTART20_NATIVE3D_ABC_RUN`` (= stage 05 run dir).

Usage
-----
::

    .venv\\Scripts\\python.exe -m four_side_1024.fanout1024.coldstart20.run_native3d_phase1 all
    .venv\\Scripts\\python.exe -m four_side_1024.fanout1024.coldstart20.run_native3d_phase1 a --top-routes 12
    .venv\\Scripts\\python.exe -m four_side_1024.fanout1024.coldstart20.run_native3d_phase1 materialize
    .venv\\Scripts\\python.exe -m four_side_1024.fanout1024.coldstart20.run_native3d_phase1 validate
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


def _sha256(path):
    import hashlib
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False,
                               default=str) + '\n', encoding='utf-8')
    return path


def prepare():
    """Install the profile, ensure the stage dirs and assert the contract."""
    B.install()
    P20.ensure_dirs()
    run_dir = Path(P20.NATIVE3D_ABC_RUN)
    for sub in ('', 'logs', 'experiment_A', 'experiment_B', 'experiment_C',
                'checkpoints', 'configs', 'plots', 'validation', 'analysis'):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)
    e5 = Path(P20.E5_DIR)
    if not (e5 / 'routes_l3d.json').is_file():
        raise FileNotFoundError(
            f'the stage-04 accepted legal solution is missing: {e5}. '
            'Run coldstart20.run_nonc4 all first.')
    if not (e5 / 'assignment_1024.csv').is_file():
        raise FileNotFoundError(f'assignment missing in {e5}')
    B.assert_20_height_profile('run_native3d_phase1')
    return run_dir, e5


def _native3d():
    from ..native3d import common as N
    return N


def stage_a(top_routes=12, time_budget=420.0, max_apply=1, log=print):
    run_dir, e5 = prepare()
    from ..native3d import run_a
    log(f'[A] start={run_dir} input={e5} top_routes={top_routes}')
    argv = ['--top-routes', str(int(top_routes)),
            '--time-budget', str(float(time_budget)),
            '--max-apply', str(int(max_apply))]
    result = run_a.main(argv)
    # A0 is the geometry unit gate: a failure means the R15 mid-body excursion
    # model itself is broken, so the rest of phase 1 must not run.
    a0_path = run_dir / 'experiment_A' / 'a0_geometry_tests.json'
    if a0_path.is_file():
        a0 = json.loads(a0_path.read_text(encoding='utf-8'))
        if not a0.get('passed'):
            failed = [item.get('test') for item in a0.get('tests') or []
                      if not item.get('passed')]
            raise RuntimeError(
                'Native-3D A0 geometry gate FAILED (%s); not continuing phase 1'
                % ', '.join(str(name) for name in failed))
        log('[A] A0 geometry gate passed')
    return result


def stage_b(sample=30, batch=80, time_budget=200.0, max_excursions=3,
            log=print):
    run_dir, e5 = prepare()
    from ..native3d import run_b
    log(f'[B] sample={sample} batch={batch} budget={time_budget}')
    argv = ['--sample', str(int(sample)), '--batch', str(int(batch)),
            '--time-budget', str(float(time_budget)),
            '--max-excursions', str(int(max_excursions))]
    return run_b.main(argv)


def stage_c(strategy='B4_multi_excursion', max_excursions=2,
            time_budget=420.0, log=print):
    run_dir, e5 = prepare()
    from ..native3d import global_optimizer
    log(f'[C] strategy={strategy} budget={time_budget}')
    argv = ['--strategy', str(strategy),
            '--max-excursions', str(int(max_excursions)),
            '--time-budget', str(float(time_budget))]
    return global_optimizer.main(argv)


#: experiment_C artifacts that the frozen Phase-2 code reads from the run root
ROOT_ARTIFACTS = ('routes_l3d.json', 'crossing_stats.json',
                  'transition_stats.json', 'failed_attempts.json',
                  'summary.json', 'optimization_history.csv')
MODEL_FILES = ('assignment_1024.csv', 'layer_planes.json',
               'process_rules.json', 'physical_layer_stack.json')


def materialize(log=print):
    """Publish experiment_C as the accepted Phase-1 layout at the run root."""
    run_dir, e5 = prepare()
    exp_c = run_dir / 'experiment_C'
    if not (exp_c / 'routes_l3d.json').is_file():
        raise FileNotFoundError(f'experiment C output missing: {exp_c}')
    copied = []
    for name in ROOT_ARTIFACTS:
        source = exp_c / name
        if source.is_file():
            shutil.copy2(source, run_dir / name)
            copied.append(name)
    for name in MODEL_FILES:
        source = e5 / name
        if not source.is_file():
            source = exp_c / name
        if source.is_file():
            target = run_dir / name
            if not target.is_file() or _sha256(target) != _sha256(source):
                shutil.copy2(source, target)
                copied.append(name)
    payload = dict(schema='coldstart20_native3d_phase1_accepted_v1',
                   profile=M.PROFILE, run_dir=str(run_dir),
                   source_experiment='experiment_C',
                   input_legal_solution=str(e5),
                   copied=copied,
                   routes_sha256=_sha256(run_dir / 'routes_l3d.json'),
                   plane_count=len(M.PLANE_IDS),
                   body_plane_count=len(M.BODY_PLANES),
                   interfaces=dict(M.INTERFACE_Z),
                   note='mid-body R15 S-curve layer changes (Native 3D Phase 1)')
    _write_json(run_dir / 'ACCEPTED_PHASE1.json', payload)
    log(f'[materialize] published {len(copied)} artifacts: {copied}')
    log(f"[materialize] routes sha256 = {payload['routes_sha256']}")
    return payload


def validate(log=print):
    """Independent **Native-3D** validator on the accepted Phase-1 layout.

    The frozen independent validator for every Native-3D stage is
    ``native3d.validate_native3d`` (it understands mid-body R15 excursions and
    checks: full route structure incl. mid transitions, per-physical-height
    strict D56, true-3D >= 0.05 mm clearance, R15, glass envelope, port contract,
    the 368 frozen manual routes against the accepted baseline layout, and the
    exact crossing recount).  It is the validator the 21-height Phase-1 used.

    ``reheight21.validate21`` is the *planar-assembly* validator: its contract
    assumes the pre-Native-3D 5-part structure (lead / S-transition / body /
    S-transition / lead) and therefore cannot be applied to a layout whose
    bodies contain mid-path layer changes -- that is a contract mismatch, not a
    relaxation.  Its output is kept for the record as
    ``validation/planar_contract_validate21.json``.
    """
    run_dir, e5 = prepare()
    from ..native3d import validate_native3d
    out_dir = run_dir / 'validation'
    out_dir.mkdir(parents=True, exist_ok=True)
    log(f'[validate] native-3D independent validator: run={run_dir} '
        f'baseline={e5}')
    code = validate_native3d.main([
        '--run-dir', str(run_dir),
        '--baseline-dir', str(e5),
        '--out-dir', str(out_dir),
    ])
    log(f'[validate] validate_native3d exit_code={code}')
    return code


def validate_planar(log=print):
    """Planar-assembly contract audit (frozen validate21) -- record only."""
    from . import run_validate
    run_dir, _e5 = prepare()
    record = run_dir / 'validation' / 'planar_contract_validate21'
    record.mkdir(parents=True, exist_ok=True)
    code = run_validate.main(['--run-dir', str(run_dir),
                              '--out-dir', str(record)])
    log(f'[validate-planar] validate21 exit_code={code} '
        f'(recorded, not the Native-3D acceptance gate)')
    return code


def plots(log=print):
    run_dir, _e5 = prepare()
    from ..native3d import visualize
    return visualize.main(['--run-dir', str(run_dir),
                           '--out-dir', str(run_dir / 'plots')])


def stage_summary(log=print):
    run_dir, e5 = prepare()
    stats_path = run_dir / 'crossing_stats.json'
    payload = dict(schema='coldstart20_native3d_phase1_summary_v1',
                   profile=M.PROFILE, run_dir=str(run_dir),
                   input=str(e5), crossings=None, pairs=None,
                   routed=None, failed=None,
                   validation=None)
    if stats_path.is_file():
        stats = json.loads(stats_path.read_text(encoding='utf-8'))
        totals = stats.get('totals') or {}
        payload.update(crossings=totals.get('crossings'),
                       pairs=totals.get('crossing_pairs'),
                       routed=stats.get('routed'), failed=stats.get('failed'))
    validation_path = run_dir / 'validation.json'
    if validation_path.is_file():
        validation = json.loads(validation_path.read_text(encoding='utf-8'))
        payload['validation'] = dict(
            validation_pass=validation.get('validation_pass'),
            geometry_pass=validation.get('geometry_pass'),
            contract_pass=validation.get('contract_pass'),
            violations=validation.get('violation_count'))
    _write_json(Path(P20.REPORTS) / 'stage05_native3d_phase1_summary.json',
                payload)
    log('[summary] ' + json.dumps(payload, ensure_ascii=False))
    return payload


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p_a = sub.add_parser('a')
    p_a.add_argument('--top-routes', type=int, default=12)
    p_a.add_argument('--time-budget', type=float, default=420.0)
    p_a.add_argument('--max-apply', type=int, default=1)
    p_b = sub.add_parser('b')
    p_b.add_argument('--sample', type=int, default=30)
    p_b.add_argument('--batch', type=int, default=80)
    p_b.add_argument('--time-budget', type=float, default=200.0)
    p_b.add_argument('--max-excursions', type=int, default=3)
    p_c = sub.add_parser('c')
    p_c.add_argument('--strategy', default='B4_multi_excursion')
    p_c.add_argument('--max-excursions', type=int, default=2)
    p_c.add_argument('--time-budget', type=float, default=420.0)
    sub.add_parser('materialize')
    sub.add_parser('validate')
    sub.add_parser('validate-planar')
    sub.add_parser('plots')
    sub.add_parser('summary')
    p_all = sub.add_parser('all')
    p_all.add_argument('--top-routes', type=int, default=12)
    p_all.add_argument('--sample', type=int, default=30)
    p_all.add_argument('--batch', type=int, default=80)
    p_all.add_argument('--c-budget', type=float, default=420.0)
    p_all.add_argument('--skip-plots', action='store_true')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    started = time.time()
    prepare()
    if args.command == 'a':
        result = stage_a(args.top_routes, args.time_budget, args.max_apply,
                         log=print)
    elif args.command == 'b':
        result = stage_b(args.sample, args.batch, args.time_budget,
                         args.max_excursions, log=print)
    elif args.command == 'c':
        result = stage_c(args.strategy, args.max_excursions,
                         args.time_budget, log=print)
    elif args.command == 'materialize':
        result = materialize(log=print)
    elif args.command == 'validate':
        result = dict(exit_code=validate(log=print))
    elif args.command == 'validate-planar':
        result = dict(exit_code=validate_planar(log=print))
    elif args.command == 'plots':
        result = dict(exit_code=plots(log=print))
    elif args.command == 'summary':
        result = stage_summary(log=print)
    elif args.command == 'all':
        stage_a(args.top_routes, log=print)
        stage_b(args.sample, args.batch, log=print)
        stage_c(time_budget=args.c_budget, log=print)
        materialize(log=print)
        validate(log=print)
        if not args.skip_plots:
            try:
                plots(log=print)
            except Exception as error:  # noqa: BLE001 - figures are optional
                print(f'[plots] skipped: {type(error).__name__}: {error}',
                      flush=True)
        result = stage_summary(log=print)
    else:  # pragma: no cover
        raise SystemExit(f'unknown command {args.command!r}')
    print(json.dumps(dict(command=args.command,
                          elapsed_s=round(time.time() - started, 1)),
                     ensure_ascii=False), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())


