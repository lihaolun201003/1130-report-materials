# -*- coding: utf-8 -*-
"""Bootstrap-first driver for Native-3D **Phase 2 (experiments D/E/F)** on the 20-height model.

The frozen Phase-2 chain (``native3d`` D/E/F) must never be started with
``python -m four_side_1024.fanout1024.native3d.run_*`` under the 20-height
experiment: without a prior ``coldstart20.bootstrap`` import every pipeline
module binds the **21-height** model (``reheight21.model``) and the run would be
silently mixed.  This driver imports the bootstrap first, asserts the profile,
and then drives the real stage chain in the audited order:

=====================  ======================================================
stage                  module / command
=====================  ======================================================
``intervals``          ``native3d.crossing_intervals --baseline-dir <E5> --out-dir <DEF>``
``blockers``           ``native3d.blocker_analysis --baseline-dir <E5> --native-dir <ABC> --out-dir <DEF>``
``d``                  ``native3d.run_d --screen 80 --repairs 30 --max-joint 3 --time-budget 260 --max-accept 12``
``e``                  ``native3d.run_e --routes 16 --time-budget 300 --max-accept 15``
``f``                  ``native3d.run_f --sweeps 2 --time-budget 560 --joint-per-sweep 10``
``fplus_1``            ``native3d.run_f_plus --time-budget 210``
``fplus_2``            ``native3d.run_f_plus --time-budget 210``
``nearmiss_1``         ``native3d.run_f_nearmiss --routes 250 --time-budget 300 --max-accept 25``
``nearmiss_2``         ``native3d.run_f_nearmiss --routes 250 --time-budget 300 --max-accept 25``
``finalize``           ``native3d.finalize_phase2`` (20H validator = ``reheight21.validate21``)
=====================  ======================================================

Optional stages that are *not* part of ``all``: ``arc-analysis`` (independent
E0 arc-crossing analysis, audit §2.8) and ``validate`` (independent
``coldstart20.run_validate`` on ``best_valid``).

Every stage writes below ``COLDSTART20_NATIVE3D_DEF_RUN``
(= ``experiments/COLD_START_20_HEIGHT_1024/06_native3d_def/run_native3d_phase2``).
The candidate pool produced by ``intervals`` is regenerated for the 20H
pre-native baseline and is read from ``<DEF>/analysis/crossing_intervals.json``
(the patched ``native3d.common.crossing_intervals_path``).

Usage
-----
::

    # cheap: import every module, resolve dirs, print the plan, execute nothing
    .venv\\Scripts\\python.exe -m four_side_1024.fanout1024.coldstart20.run_native3d_phase2 --dry-run
    .venv\\Scripts\\python.exe -m four_side_1024.fanout1024.coldstart20.run_native3d_phase2 plan

    # the real chain (needs the accepted 20H Phase-1 layout + the 20H E5 analog)
    .venv\\Scripts\\python.exe -m four_side_1024.fanout1024.coldstart20.run_native3d_phase2 all

    # resume after a failure / run one stage
    .venv\\Scripts\\python.exe -m four_side_1024.fanout1024.coldstart20.run_native3d_phase2 d
    ... run_native3d_phase2 fplus_2
    ... run_native3d_phase2 arc-analysis
    ... run_native3d_phase2 validate

Safety rules baked in
---------------------
* ``coldstart20.bootstrap`` is imported before **any** pipeline module;
  :func:`bootstrap.assert_20_height_profile` is called immediately.
* the 21-height ``validate_native3d.E5_EXPECT`` regression block is never
  enabled: ``finalize`` uses the frozen independent ``reheight21.validate21``
  under the installed 20-height model (``coldstart20.run_validate`` equivalent).
* no geometric rule / threshold is changed by this driver; it only selects
  directories, modules and CLI arguments.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
from pathlib import Path

# ---- 20-height profile FIRST (installs on import) --------------------------
from . import bootstrap as B          # noqa: E402  installs the 20-height profile
from . import model20 as M            # noqa: E402
from . import paths20 as P20          # noqa: E402
from . import profile_env as PE       # noqa: E402

B.install()
B.assert_20_height_profile('run_native3d_phase2')

#: 20-height movable planes (derived from the installed model; regression-checked
#: by 00_audit/patch_native3d_def.py --verify)
MOVABLE_20H = (6, 7, 20, 1001, 8, 9, 14, 15, 16, 1002, 17, 18)

#: stage order of the real Phase-2 chain (audit 00_audit/native3d_def.md §1.2)
CHAIN = ('intervals', 'blockers', 'd', 'e', 'f', 'fplus_1', 'fplus_2',
         'nearmiss_1', 'nearmiss_2', 'finalize')
#: stages available from the CLI but not executed by ``all``
OPTIONAL = ('arc_analysis', 'validate')

PIPELINE = 'four_side_1024.fanout1024.native3d'
DRIVER = 'four_side_1024.fanout1024.coldstart20.run_native3d_phase2'

STAGE_CHOICES = CHAIN + OPTIONAL


# ===========================================================================
# logging / json helpers
# ===========================================================================
def _now():
    return time.strftime('%Y-%m-%dT%H:%M:%S')


def _def_run():
    return Path(P20.NATIVE3D_DEF_RUN)


def _log(message, log_file=None):
    line = time.strftime('%H:%M:%S') + ' [native3d-def] ' + str(message)
    print(line, flush=True)
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with Path(log_file).open('a', encoding='utf-8') as handle:
            handle.write(line + '\n')


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False,
                               default=str) + '\n', encoding='utf-8')
    return path


# ===========================================================================
# context
# ===========================================================================
def resolve_context():
    """Validate the bootstrap-published directories and build the run context."""
    if not PE.is_20h():
        raise SystemExit(
            'the 20-height profile is not active; import coldstart20.bootstrap '
            'before the pipeline (this driver does that on import -- check the '
            'import order / the bootstrap install log)')
    ctx = dict(
        def_run=Path(P20.NATIVE3D_DEF_RUN),
        abc_run=Path(P20.NATIVE3D_ABC_RUN),
        e5_dir=Path(P20.E5_DIR),
        init_run=Path(P20.INIT_RUN),
        nonc4_root=Path(P20.NONC4_ROOT),
        experiment_root=Path(P20.EXP_ROOT),
        profile=B.profile_payload(),
        started=_now(),
    )
    # the bootstrap publishes COLDSTART20_<NAME> for every path; they must be
    # exactly the paths20 values or the frozen path modules write somewhere else
    mismatched = []
    for name, value in P20.ENV_PATHS.items():
        env_key = PE.PREFIX + name
        actual = os.environ.get(env_key)
        if actual is None or Path(actual) != Path(value):
            mismatched.append('%s=%r (expected %s)' % (env_key, actual, value))
    if mismatched:
        raise SystemExit('profile environment mismatch: ' + '; '.join(mismatched))
    return ctx


def inherited_baseline(ctx):
    """(crossing total, source path) of the accepted 20H Phase-1 layout."""
    for path in (ctx['abc_run'] / 'crossing_stats.json',
                 ctx['abc_run'] / 'experiment_C' / 'crossing_stats.json'):
        try:
            payload = json.loads(Path(path).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        value = (payload.get('totals') or {}).get('crossings')
        if value is not None:
            return int(value), Path(path)
    return None, None


def _ensure_dry_run_baseline(ctx):
    """Let ``--dry-run`` import ``phase2`` before Phase 1 has been validated.

    ``phase2.BASELINE_CROSSINGS`` deliberately fails loudly when the accepted
    Phase-1 layout is absent, so a 20H Phase 2 can never inherit a wrong
    baseline.  A dry run has no Phase-1 input yet, therefore it sets the
    documented ``COLDSTART20_PHASE1_CROSSINGS`` override to a placeholder for
    *this process only*; a real run never sets it.
    """
    if PE.int_env('PHASE1_CROSSINGS') is not None:
        return False
    value, _path = inherited_baseline(ctx)
    if value is None:
        os.environ[PE.PREFIX + 'PHASE1_CROSSINGS'] = '0'
        return True
    return False


# ===========================================================================
# stage table
# ===========================================================================
def stage_specs(ctx):
    """Ordered stage table: module, argv, inputs, outputs, estimate."""
    e5 = ctx['e5_dir']
    abc = ctx['abc_run']
    out = ctx['def_run']
    phase1 = abc / 'experiment_C'
    specs = {}

    specs['intervals'] = dict(
        title='crossing-interval analysis of the 20H pre-native baseline '
              '(candidate pool consumed by D and blocker_analysis)',
        module=PIPELINE + '.crossing_intervals',
        argv=['--baseline-dir', str(e5), '--out-dir', str(out)],
        inputs=[e5 / 'routes_l3d.json', e5 / 'crossing_stats.json'],
        outputs=[out / 'analysis' / 'crossing_intervals.json',
                 out / 'analysis' / 'crossing_intervals_report.md'],
        must_exist=[out / 'analysis' / 'crossing_intervals.json'],
        estimate='~2-5 min (19.9 MB payload, validate-top 150)',
    )
    specs['blockers'] = dict(
        title='D0/E0 blocker analysis (true-3D rejection reasons of the 20H pool)',
        module=PIPELINE + '.blocker_analysis',
        argv=['--baseline-dir', str(e5), '--native-dir', str(abc),
              '--out-dir', str(out), '--min-net', '3',
              '--extra-route', '129', '--extra-net', '16',
              '--validation-limit', '60'],
        inputs=[e5 / 'routes_l3d.json', e5 / 'assignment_1024.csv',
                phase1 / 'routes_l3d.json',
                out / 'analysis' / 'crossing_intervals.json'],
        outputs=[out / 'analysis' / 'blocker_analysis.json',
                 out / 'analysis' / 'blocker_analysis_report.md',
                 out / 'analysis' / 'plots'],
        must_exist=[out / 'analysis' / 'blocker_analysis.json'],
        estimate='~145 s for 5 387 candidates (20H pool size differs)',
    )
    specs['d'] = dict(
        title='D: multi-route joint make-way reroute of the screened candidates',
        module=PIPELINE + '.run_d',
        argv=['--screen', '80', '--repairs', '30', '--max-joint', '3',
              '--time-budget', '260', '--max-accept', '12'],
        inputs=[phase1 / 'routes_l3d.json', e5 / 'assignment_1024.csv',
                out / 'analysis' / 'crossing_intervals.json',
                [abc / 'crossing_stats.json',
                 phase1 / 'crossing_stats.json']],
        outputs=[out / 'experiment_D' / 'routes_l3d.json',
                 out / 'experiment_D' / 'blocker_map.json',
                 out / 'experiment_D' / 'summary.json',
                 out / 'logs' / 'experiment_D.log'],
        must_exist=[out / 'experiment_D' / 'summary.json'],
        estimate='~258 s historically (D0 blocker screen dominates)',
    )
    specs['e'] = dict(
        title='E: arc-region local 3D rebuild (E_A / E_B / E_C)',
        module=PIPELINE + '.run_e',
        argv=['--routes', '16', '--time-budget', '300',
              '--max-accept', '15'],
        inputs=[phase1 / 'routes_l3d.json', e5 / 'assignment_1024.csv',
                [abc / 'crossing_stats.json',
                 phase1 / 'crossing_stats.json'],
                [out / 'experiment_D' / 'routes_l3d.json',
                 out / 'best_valid' / 'routes_l3d.json']],
        outputs=[out / 'experiment_E' / 'routes_l3d.json',
                 out / 'experiment_E' / 'summary.json',
                 out / 'logs' / 'experiment_E.log'],
        must_exist=[out / 'experiment_E' / 'summary.json'],
        estimate='~29 s historically (36 attempts)',
    )
    specs['f'] = dict(
        title='F: global joint crossing optimisation (plain / arc_span / joint sweeps)',
        module=PIPELINE + '.run_f',
        argv=['--sweeps', '2', '--time-budget', '560',
              '--joint-per-sweep', '10'],
        inputs=[phase1 / 'routes_l3d.json', e5 / 'assignment_1024.csv',
                out / 'analysis' / 'crossing_intervals.json',
                [abc / 'crossing_stats.json',
                 phase1 / 'crossing_stats.json']],
        outputs=[out / 'experiment_F' / 'routes_l3d.json',
                 out / 'experiment_F' / 'summary.json',
                 out / 'optimization_history.csv',
                 out / 'transition_stats.json',
                 out / 'logs' / 'experiment_F.log'],
        must_exist=[out / 'experiment_F' / 'summary.json'],
        estimate='~133 s historically (2 sweeps over ~656 movable routes)',
    )
    for index in (1, 2):
        key = 'fplus_%d' % index
        specs[key] = dict(
            title='F+ sweep %d: multi-excursion plain-batch engine on best_valid'
                  % index,
            module=PIPELINE + '.run_f_plus',
            argv=['--time-budget', '210'],
            inputs=[out / 'best_valid' / 'routes_l3d.json',
                    e5 / 'assignment_1024.csv'],
            outputs=[out / 'experiment_F' / 'validation_extra.json',
                     out / 'experiment_F' / 'extra_sweep.json',
                     out / 'best_valid' / 'routes_l3d.json'],
            must_exist=[out / 'best_valid' / 'routes_l3d.json'],
            estimate='~132 s / ~215 s historically (1 sweep each; writes only '
                     'on improvement)',
        )
    for index in (1, 2):
        key = 'nearmiss_%d' % index
        specs[key] = dict(
            title='near-miss refinement pass %d on best_valid (D0 near-miss pool)'
                  % index,
            module=PIPELINE + '.run_f_nearmiss',
            argv=['--routes', '250', '--time-budget', '300',
                  '--max-accept', '25'],
            inputs=[out / 'best_valid' / 'routes_l3d.json',
                    out / 'analysis' / 'blocker_analysis.json',
                    e5 / 'assignment_1024.csv'],
            outputs=[out / 'experiment_F' / 'near_miss_results.json',
                     out / 'experiment_F' / 'validation_near_miss.json'],
            must_exist=[out / 'experiment_F' / 'near_miss_results.json'],
            estimate='~5 min / ~4 min historically (1 700+ / 768 attempts)',
        )
    specs['finalize'] = dict(
        title='finalise Phase 2: independent 20H validation, plots, reports, '
              'MANIFEST, archive',
        module=PIPELINE + '.finalize_phase2',
        argv=None,   # finalize_phase2.main() takes no argv
        inputs=[phase1 / 'routes_l3d.json',
                [abc / 'crossing_stats.json',
                 phase1 / 'crossing_stats.json'],
                [out / 'experiment_F' / 'routes_l3d.json',
                 out / 'best_valid' / 'routes_l3d.json']],
        outputs=[out / 'routes_l3d.json', out / 'crossing_stats.json',
                 out / 'validation.json', out / 'summary.json',
                 out / 'MANIFEST.json',
                 out / 'validation' / 'final' / 'validation.json'],
        must_exist=[out / 'summary.json', out / 'MANIFEST.json'],
        estimate='~30-90 s (validate21 + plots + reports + manifest + archive)',
    )
    # ---- optional (not in ``all``) -------------------------------------
    specs['arc_analysis'] = dict(
        title='[optional E0] independent arc-crossing analysis of the accepted '
              'Phase-1 layout',
        module=PIPELINE + '.arc_crossing_analysis',
        argv=['--baseline', str(phase1), '--out-dir', str(out)],
        inputs=[phase1 / 'routes_l3d.json', phase1 / 'crossing_stats.json'],
        outputs=[out / 'analysis' / 'arc_crossing_analysis.json',
                 out / 'analysis' / 'arc_crossing_report.md'],
        must_exist=[out / 'analysis' / 'arc_crossing_analysis.json'],
        estimate='~1-3 min (2 440-event payload in the 21H run)',
        optional=True,
    )
    specs['validate'] = dict(
        title='[optional] independent 20H validator (reheight21.validate21) on '
              'best_valid, via coldstart20.run_validate',
        module='four_side_1024.fanout1024.coldstart20.run_validate',
        argv=['--run-dir', str(out / 'best_valid'),
              '--out-dir', str(out / 'validation' / 'independent_20h')],
        inputs=[out / 'best_valid' / 'routes_l3d.json'],
        outputs=[out / 'validation' / 'independent_20h' / 'validation.json'],
        must_exist=[],
        estimate='~20-60 s (independent geometry + strict D56 + clearance)',
        optional=True,
    )
    return specs


# ===========================================================================
# input / profile checks
# ===========================================================================
class StageFailure(RuntimeError):
    """A stage failed hard; ``all`` stops here with this message."""


def _missing_inputs(spec):
    missing = []
    for entry in spec.get('inputs') or ():
        alternatives = entry if isinstance(entry, (list, tuple)) else [entry]
        if not any(Path(path).is_file() for path in alternatives):
            missing.append(' | '.join(str(path) for path in alternatives))
    return missing


def _check_inputs(spec):
    missing = _missing_inputs(spec)
    if not missing:
        return
    raise StageFailure(
        'missing input(s) for this stage:\n  - ' + '\n  - '.join(missing) +
        '\nrun the preceding stage(s) first (see ``plan``); a 20H run needs '
        'the accepted Phase-1 layout (stage 05) and the 20H E5 analog (stage 04)')


def _check_profile_bindings():
    """Assert the imported pipeline modules really bind the 20H profile."""
    from ..native3d import common as N
    from ..native3d import phase2 as P2

    problems = []
    if len(N.PLANE_Z) != 20:
        problems.append('native3d.common.PLANE_Z has %d heights (expected 20)'
                        % len(N.PLANE_Z))
    if 19 in N.PLANE_Z:
        problems.append('deleted plane identity 19 is still bound')
    if tuple(N.MOVABLE_PLANES) != MOVABLE_20H:
        problems.append('native3d.common.MOVABLE_PLANES=%r (expected %r)'
                        % (tuple(N.MOVABLE_PLANES), MOVABLE_20H))
    if Path(P2.PHASE1_DIR) != Path(P20.NATIVE3D_ABC_RUN):
        problems.append('phase2.PHASE1_DIR=%s (expected %s)'
                        % (P2.PHASE1_DIR, P20.NATIVE3D_ABC_RUN))
    if Path(P2.RUN2) != _def_run():
        problems.append('phase2.RUN2=%s (expected %s)'
                        % (P2.RUN2, _def_run()))
    if problems:
        raise StageFailure('20-height profile binding is wrong: '
                           + '; '.join(problems))
    return N, P2


def _check_phase1_layout(ctx):
    """Fail early (before burning compute) when the 20H Phase-1 input is absent."""
    problems = []
    phase1 = ctx['abc_run'] / 'experiment_C'
    required = [phase1 / 'routes_l3d.json',
                ctx['e5_dir'] / 'routes_l3d.json',
                ctx['e5_dir'] / 'crossing_stats.json',
                ctx['e5_dir'] / 'assignment_1024.csv']
    for path in required:
        if not Path(path).is_file():
            problems.append(str(path))
    value, _source = inherited_baseline(ctx)
    if value is None:
        problems.append('%s/crossing_stats.json (or %s/experiment_C/'
                        'crossing_stats.json)'
                        % (ctx['abc_run'], ctx['abc_run']))
    if problems:
        raise StageFailure(
            'the 20-height Phase-2 chain cannot start: missing Phase-1/E5 '
            'input(s):\n  - ' + '\n  - '.join(problems) +
            '\nRun stage 04 (run_nonc4) and the 20H Native-3D Phase 1 first.')
    # model payloads, when present, must be 20-height (21H copies are a trap)
    for path in (ctx['abc_run'] / 'layer_planes.json',
                 phase1 / 'layer_planes.json',
                 ctx['e5_dir'] / 'layer_planes.json'):
        if not Path(path).is_file():
            continue
        try:
            payload = json.loads(Path(path).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        count = payload.get('plane_count')
        if count is not None and int(count) != 20:
            raise StageFailure(
                '%s declares %s routing planes; this is not a 20-height layout '
                '(a 21H model copy must not be used by the 20H Phase 2)'
                % (path, count))
    return value


# ===========================================================================
# execution
# ===========================================================================
def _import_stage(spec):
    try:
        return importlib.import_module(spec['module'])
    except Exception as error:  # noqa: BLE001 - reported as a stage failure
        raise StageFailure('cannot import %s: %s: %s'
                           % (spec['module'], type(error).__name__, error))


def run_stage(ctx, key, log_file=None):
    specs = stage_specs(ctx)
    spec = specs[key]
    _check_inputs(spec)
    module = _import_stage(spec)
    command = 'python -m %s' % spec['module']
    if spec.get('argv'):
        command += ' ' + ' '.join(spec['argv'])
    started = time.time()
    _log('stage %s: %s' % (key, spec['title']), log_file)
    _log('  cmd: %s' % command, log_file)
    try:
        if spec.get('argv') is None:
            _result = module.main()
        else:
            _result = module.main(list(spec['argv']))
    except SystemExit as exc:
        code = exc.code
        if code not in (0, None):
            raise StageFailure('stage %r exited with code %r' % (key, code))
    except Exception as error:  # noqa: BLE001 - stop the chain with context
        raise StageFailure('stage %r failed: %s: %s'
                           % (key, type(error).__name__, error))
    seconds = round(time.time() - started, 1)
    missing = [str(path) for path in spec.get('must_exist') or ()
               if not Path(path).is_file()]
    if missing:
        raise StageFailure(
            'stage %r finished but its expected output is missing:\n  - %s'
            % (key, '\n  - '.join(missing)))
    _log('stage %s done in %.1f s' % (key, seconds), log_file)
    return dict(stage=key, status='ok', seconds=seconds,
                module=spec['module'], command=command)


def _write_chain_status(ctx, entries, ok):
    path = ctx['def_run'] / 'logs' / 'phase2_chain_status.json'
    _write_json(path, dict(
        schema='coldstart20_native3d_def_chain_status_v1',
        profile=M.PROFILE,
        driver=DRIVER,
        started=ctx['started'],
        finished=_now(),
        passed=bool(ok),
        chain=list(CHAIN),
        stages=entries,
        definitions={key: dict(module=spec['module'], argv=spec['argv'])
                     for key, spec in stage_specs(ctx).items()},
        paths=dict(def_run=str(ctx['def_run']),
                   abc_run=str(ctx['abc_run']),
                   e5_dir=str(ctx['e5_dir'])),
    ))
    return path


def run_all(ctx):
    specs = stage_specs(ctx)
    _log('preflight: accepted Phase-1 layout + 20H E5 analog')
    try:
        baseline = _check_phase1_layout(ctx)
        _check_profile_bindings()
    except StageFailure as error:
        print('\n[STOP] Native-3D Phase 2 preflight failed:', flush=True)
        print(str(error), flush=True)
        try:
            ctx['def_run'].mkdir(parents=True, exist_ok=True)
            _write_chain_status(
                ctx, [dict(stage='preflight', status='failed',
                           error=str(error))], ok=False)
        except OSError:
            pass
        return 1
    _log('inherited Phase-1 crossing total: %d' % baseline)
    ctx['def_run'].mkdir(parents=True, exist_ok=True)
    log_file = ctx['def_run'] / 'logs' / 'phase2_chain.log'
    _write_json(ctx['def_run'] / 'logs' / 'phase2_profile.json',
                ctx['profile'])
    _log('driver start: 20-height Native-3D Phase 2 (D/E/F)', log_file)
    _log('def run: %s' % ctx['def_run'], log_file)
    entries = []
    ok = True
    failed_stage = None
    for key in CHAIN:
        try:
            entry = run_stage(ctx, key, log_file=log_file)
        except StageFailure as error:
            ok = False
            failed_stage = key
            entry = dict(stage=key, status='failed', error=str(error))
            print('\n[STOP] Native-3D Phase 2 chain stopped at stage %r:' % key,
                  flush=True)
            print(str(error), flush=True)
            print('       fix the input/condition above and resume with: '
                  'run_native3d_phase2 %s' % key, flush=True)
            entries.append(entry)
            break
        entries.append(entry)
    status_path = _write_chain_status(ctx, entries, ok)
    if ok:
        _log('ALL STAGES DONE -- outputs under %s' % ctx['def_run'], log_file)
        _log('chain status: %s' % status_path, log_file)
        return 0
    _log('FAILED at stage %r -- see the message above; status: %s'
         % (failed_stage, status_path), log_file)
    return 1


# ===========================================================================
# plan / dry-run
# ===========================================================================
def _format_state(entries):
    """'n/m input group(s) present' (a group may be an OR-list of paths)."""
    total = 0
    present = 0
    missing = []
    for entry in entries:
        alternatives = entry if isinstance(entry, (list, tuple)) else [entry]
        total += 1
        if any(Path(path).is_file() for path in alternatives):
            present += 1
        else:
            missing.append(' | '.join(str(path) for path in alternatives))
    text = '%d/%d input group(s) present' % (present, total)
    if missing:
        text += '; missing: ' + '; '.join(missing[:3])
        if len(missing) > 3:
            text += ' ...'
    return text


def plan_pages(ctx, only=None):
    specs = stage_specs(ctx)
    keys = list(CHAIN) + [key for key in OPTIONAL if only is None]
    if only is not None:
        keys = [only]
    placeholder = _ensure_dry_run_baseline(ctx)
    print('=' * 78)
    print('Native-3D Phase 2 (experiments D/E/F) -- 20-height driver plan')
    print('=' * 78)
    profile = ctx['profile']
    print('profile          : %s (%d heights: %d body + 2 interface)'
          % (profile['profile'], profile['plane_count'],
             profile['body_plane_count']))
    print('plane ids        : %s' % profile['plane_ids'])
    print('interfaces (mm)  : %s' % profile['interfaces'])
    print('min pitch / 3D   : %.6f / %.6f mm (rules unchanged)'
          % (profile['measured_min_pitch_mm'], profile['min_3d_clearance_mm']))
    print('phase-1 crossing : ', end='')
    baseline, source = inherited_baseline(ctx)
    if baseline is None:
        if placeholder:
            print('MISSING (dry-run placeholder COLDSTART20_PHASE1_CROSSINGS=0; '
                  'a real run requires the validated Phase-1 layout)')
        else:
            print('MISSING (real run would stop: validate Phase 1 first)')
    else:
        print('%d (from %s)' % (baseline, source))
    print()
    print('directories')
    print('  DEF run (all stage output) : %s' % ctx['def_run'])
    print('  Phase-1 accepted layout    : %s/experiment_C'
          % ctx['abc_run'])
    print('  20H E5 analog (pre-native): %s' % ctx['e5_dir'])
    print('  candidate pool             : %s'
          % (ctx['def_run'] / 'analysis' / 'crossing_intervals.json'))
    print()
    # import every stage module exactly as a dry run is expected to do
    modules = {}
    import_errors = []
    for key in STAGE_CHOICES:
        try:
            modules[key] = importlib.import_module(specs[key]['module'])
        except Exception as error:  # noqa: BLE001
            import_errors.append('%s -> %s: %s'
                                 % (key, specs[key]['module'], error))
    if import_errors:
        raise StageFailure('stage module import failed:\n  - '
                           + '\n  - '.join(import_errors))
    N, P2 = _check_profile_bindings()
    print('imports           : %d stage modules imported under the 20H '
          'bootstrap (%d unique modules)'
          % (len(modules), len({spec['module'] for spec in specs.values()})))
    print('model binding     : native3d.common.PLANE_Z=%d heights, '
          'MOVABLE_PLANES=%s'
          % (len(N.PLANE_Z), tuple(int(pid) for pid in N.MOVABLE_PLANES)))
    print('phase2 binding    : PHASE1_DIR=%s, RUN2=%s, BASELINE_CROSSINGS=%d'
          % (P2.PHASE1_DIR, P2.RUN2, P2.BASELINE_CROSSINGS))
    print('profile guard     : %s'
          % ('20H installed + asserted' if B.is_installed() else 'NOT INSTALLED'))
    e5_validator_loaded = (
        'four_side_1024.fanout1024.native3d.validate_native3d' in sys.modules)
    print('21H safety        : validate_native3d %s; E5_EXPECT never enabled; '
          'finalize validates with reheight21.validate21'
          % ('LOADED (unexpected!)' if e5_validator_loaded else 'not imported'))
    print()
    print('stages (executed in this order by ``all``)')
    for index, key in enumerate(keys, 1):
        spec = specs[key]
        print('%2d. %-11s %s' % (index, key, spec['title']))
        command = 'python -m %s' % spec['module']
        if spec.get('argv'):
            command += ' ' + ' '.join(spec['argv'])
        print('    cmd     : %s' % command)
        print('    inputs  : %s' % _format_state(spec.get('inputs') or ()))
        print('    outputs : %s' % ', '.join(str(path)
                                             for path in spec['outputs']))
        print('    estimate: %s' % spec['estimate'])
        if spec.get('optional'):
            print('    note    : optional stage, NOT part of ``all``')
    print()
    print('DRY-RUN: no stage was executed and no stage output was written.')
    print('         bootstrap installation created the empty experiment '
          'directories only.')
    print('         regression check: patch_native3d_def.py --verify')
    print('=' * 78)
    return 0


# ===========================================================================
# CLI
# ===========================================================================
def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--dry-run', action='store_true',
                        default=argparse.SUPPRESS,
                        help='import modules, resolve dirs, print the plan, '
                             'execute nothing')
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dry-run', action='store_true',
                        help='import modules, resolve dirs, print the plan, '
                             'execute nothing')
    sub = parser.add_subparsers(dest='command')
    sub.add_parser('plan', parents=[common],
                   help='print the full chain plan (same as --dry-run)')
    sub.add_parser('all', parents=[common],
                   help='run the full D/E/F chain in audited order')
    for key in STAGE_CHOICES:
        sub.add_parser(key, parents=[common],
                       help='run only this stage (resume after a failure)')
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    ctx = resolve_context()
    dry_run = bool(getattr(args, 'dry_run', False))
    command = args.command
    if command is None:
        if dry_run:
            command = 'plan'
        else:
            parser.print_help()
            return 2
    if dry_run or command == 'plan':
        only = None if command in ('plan', 'all') else command
        return plan_pages(ctx, only=only)
    if command == 'all':
        return run_all(ctx)
    if command in STAGE_CHOICES:
        try:
            _check_phase1_layout(ctx) if command in CHAIN else None
            entry = run_stage(ctx, command)
        except StageFailure as error:
            print('\n[STOP] stage %r failed:' % command, flush=True)
            print(str(error), flush=True)
            return 1
        print(json.dumps(entry, indent=1, ensure_ascii=False))
        return 0
    raise SystemExit('unknown command %r' % command)


if __name__ == '__main__':
    raise SystemExit(main())
