# -*- coding: utf-8 -*-
"""20-height driver for the XYZ joint optimisation chain G1 / G2a / G2b / G3.

The frozen G1/G2/G3 experiment (``four_side_1024/fanout1024/xyzrouter``) reads
its height table from ``reheight21.model`` **at import time**, so it must be
started from a process that imports ``coldstart20.bootstrap`` first (audit
``experiments/COLD_START_20_HEIGHT_1024/00_audit/g123.md`` section 9.1).  This
module is that bootstrap-first entry point.  It installs the 20-height profile,
snapshots the accepted 20-height Native-3D Phase-2 ``best_valid`` as
``baseline_authoritative`` (what ``xyzrouter.paths.BASELINE_AUTHORITY`` means),
and then drives, in order:

0. ``preflight``  -- copy Phase-2 ``best_valid`` -> ``baseline_authoritative``,
   write the authority ``SHA256.json`` / ``AUTHORITY.json``, check the 20H data
   contract (1024 routes / 368 manual records / every flat z is a 20H height /
   no deleted plane 19 / 20-plane ``layer_planes.json``), recompute the start
   crossing total, and run the independent validator with
   ``manual_policy='frozen'``.  The 21-height ``preflight_audit.py`` is NOT used.
1. ``g1``         -- ``run_g1 --rounds 2 --round-seconds 1200 --top 656``
   (manual-U frozen, 656 non-manual routes XY+Z re-routed, validation fatal).
2. ``warmstart``  -- ``run_warmstart_chain``: G2a 2x300 s -> G2b 1x240 s ->
   G3 1x500 s (each stage validates itself; in-process under 20H).
3. ``g3cold``     -- ``run_g3 --start-from baseline --rounds 1
   --round-seconds 1200`` into ``fair_comparison/G3_cold`` (the independent
   same-budget cold control the archived campaign ran).
4. ``validate``   -- ``run_router_validation`` P0/P1/P2 under the 20H model.
5. ``reports``    -- ``run_reports``: reports + fair/warm comparison +
   ``best_valid`` + archive.

Every writable path resolves below ``COLDSTART20_XYZ_RUN``
(``experiments/COLD_START_20_HEIGHT_1024/07_g123/run_xyz_joint_1024_20h``); the
frozen 21-height tree is never written.  The real runs are long (the archived
21-height campaign took ~63 min G1+warm chain, +21 min G3_cold, +7 min P0/P1/P2,
plus the independent validations); this driver does **not** shrink a budget.

Usage (from the project root)::

    # resolve + print the whole plan, assert the 20H wiring, run nothing
    .venv\\Scripts\\python.exe -m four_side_1024.fanout1024.coldstart20.run_g123 --dry-run

    # one stage / the whole chain
    .venv\\Scripts\\python.exe -m four_side_1024.fanout1024.coldstart20.run_g123 preflight
    .venv\\Scripts\\python.exe -m four_side_1024.fanout1024.coldstart20.run_g123 g1
    .venv\\Scripts\\python.exe -m four_side_1024.fanout1024.coldstart20.run_g123 warmstart
    .venv\\Scripts\\python.exe -m four_side_1024.fanout1024.coldstart20.run_g123 g3cold
    .venv\\Scripts\\python.exe -m four_side_1024.fanout1024.coldstart20.run_g123 validate
    .venv\\Scripts\\python.exe -m four_side_1024.fanout1024.coldstart20.run_g123 reports
    .venv\\Scripts\\python.exe -m four_side_1024.fanout1024.coldstart20.run_g123 all

Commands are rerunnable: every stage overwrites its own output directory and
the authority snapshot is rebuilt from the Phase-2 source.  Checkpoints are
stage-scoped (``<stage out_dir>/checkpoints``) so a later/parallel stage can
never corrupt another stage's checkpoints (the frozen campaign defect, audit
section 2.4).
"""
from __future__ import annotations

import argparse
import contextlib
import importlib
import json
import shutil
import sys
import time
import traceback
from pathlib import Path

import matplotlib
matplotlib.use('Agg')  # noqa: E402 - forced before any pyplot import

from . import bootstrap as B          # installs the 20-height profile on import
from . import model20 as M20
from . import paths20 as P20

#: fail loudly if a pipeline module was imported before the bootstrap
B.assert_20_height_profile('run_g123 (bootstrap-first import)')

#: imported only after the profile is installed: these modules freeze the
#: height / plane tables at import time (audit g123.md section 9.1)
from ..reheight21 import model as M                    # noqa: E402
from ..xyzrouter import paths as P                     # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROFILE = M20.PROFILE
MODEL_NAME = M20.MODEL_NAME
EXPERIMENT_ROOT = Path(P20.EXP_ROOT)
G123_ROOT = Path(P20.G123)
RUN_ROOT = Path(P.XYZ_RUN_DIR)
AUTHORITY = Path(P.BASELINE_AUTHORITY)
PREFLIGHT_DIR = Path(P.DIRS['preflight'])
ARCHIVE_DIR = RUN_ROOT / 'archive'
LOG_PATH = RUN_ROOT / 'run_g123.log'
SUMMARY_PATH = RUN_ROOT / 'run_g123_summary.json'
PHASE2_BEST_VALID = Path(P20.NATIVE3D_DEF_RUN) / 'best_valid'

#: authority provenance files copied from the Phase-2 best_valid (audit 9.5)
AUTHORITY_REQUIRED_FILES = ('routes_l3d.json', 'assignment_1024.csv',
                            'layer_planes.json')
MODEL_PROVENANCE_FILES = ('layer_planes.json', 'physical_layer_stack.json',
                          'process_rules.json')

#: fallback sources for the model files the Phase-2 save_best_valid copies from
#: its Phase-1 run (native3d/phase2.copy_model_files); mirrors that chain
FALLBACK_MODEL_SOURCES = (
    Path(P.NATIVE_PHASE1_DIR) / 'experiment_C',
    Path(P.NATIVE_PHASE1_DIR),
    Path(P.E5_DIR),
    Path(P20.INIT_RUN),
)

# ===========================================================================
# budgets / stage contracts (audit g123.md sections 1.1, 2.3 and 9.6)
# ===========================================================================
G1 = dict(rounds=2, round_seconds=1200.0, top=656)
G2A = dict(rounds=2, round_seconds=300.0, delta_budget=80)
G2B = dict(rounds=1, round_seconds=240.0, route_delta_budget=2)
G3 = dict(rounds=1, round_seconds=500.0)
G3_COLD = dict(rounds=1, round_seconds=1200.0)

POLICIES = {
    'G1': 'frozen',
    'G2a': 'height_only',
    'G2b': 'height_only',
    'G3': 'fully_optimizable',
    'G3_cold': 'fully_optimizable',
}

RUN_G1 = 'four_side_1024.fanout1024.xyzrouter.run_g1'
RUN_WARMSTART = 'four_side_1024.fanout1024.xyzrouter.run_warmstart_chain'
RUN_G3 = 'four_side_1024.fanout1024.xyzrouter.run_g3'
RUN_ROUTER_VALIDATION = 'four_side_1024.fanout1024.xyzrouter.run_router_validation'
RUN_REPORTS = 'four_side_1024.fanout1024.xyzrouter.run_reports'

#: command -> stages executed (each command is self-contained and rerunnable)
COMMANDS = {
    'plan': ('preflight', 'g1', 'warmstart', 'g3cold', 'validate', 'reports'),
    'preflight': ('preflight',),
    'g1': ('preflight', 'g1'),
    'warmstart': ('preflight', 'warmstart'),
    'g3cold': ('preflight', 'g3cold'),
    'validate': ('preflight', 'validate'),
    'reports': ('preflight', 'reports'),
    'all': ('preflight', 'g1', 'warmstart', 'g3cold', 'validate', 'reports'),
}


# ===========================================================================
# small helpers
# ===========================================================================
def _log(message=''):
    print(message, flush=True)


def _rel(path):
    """Path relative to the project root when possible (portable reports)."""
    try:
        return str(Path(path).resolve().relative_to(PROJECT_ROOT))
    except (ValueError, OSError):
        return str(path)


def _num(value):
    value = float(value)
    return str(int(value)) if value.is_integer() else ('%g' % value)


def _minutes(seconds):
    seconds = float(seconds or 0.0)
    return '%.1f min' % (seconds / 60.0)


def _read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False,
                               default=str) + '\n', encoding='utf-8')
    return path


def _read_csv_rows(path):
    import csv
    with Path(path).open('r', encoding='utf-8-sig', newline='') as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _sha256(path):
    import hashlib
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)
    return True


def _under(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except (ValueError, OSError):
        return False


def _load_validation(stage_dir):
    """Validation report of a G stage (``validation/validation.json``)."""
    stage_dir = Path(stage_dir)
    for candidate in (stage_dir / 'validation' / 'validation.json',
                      stage_dir / 'validation.json'):
        payload = _read_json(candidate)
        if isinstance(payload, dict):
            return payload
    return None


class _Tee:
    """Duplicate everything printed by the stages into one run log file."""

    encoding = 'utf-8'

    def __init__(self, stream, path):
        self.stream = stream
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open('w', encoding='utf-8')

    def write(self, data):
        self.stream.write(data)
        if not self.handle.closed:
            self.handle.write(data)
        return len(data)

    def flush(self):
        try:
            self.stream.flush()
        finally:
            if not self.handle.closed:
                self.handle.flush()

    def isatty(self):
        return False

    def close(self):
        try:
            self.handle.close()
        except OSError:
            pass


# ===========================================================================
# stage plan
# ===========================================================================
def build_plan(source=None):
    """The complete ordered stage plan (paths resolved from the 20H profile)."""
    source = Path(source) if source else PHASE2_BEST_VALID
    fair_cold = Path(P.DIRS['fair']) / 'G3_cold'
    g1_dir = Path(P.DIRS['G1'])
    stages = [
        dict(
            name='preflight',
            title=('authority snapshot of the accepted 20H Phase-2 best_valid '
                   '(baseline_authoritative) + 20H data contract + independent '
                   'frozen validation'),
            module=None,
            argv=[],
            source=str(source),
            out_dir=str(AUTHORITY),
            validation='frozen (independent validate_xyz)',
            checkpoint_dir=str(PREFLIGHT_DIR / 'checkpoints'),
            budget_seconds=0.0,
        ),
        dict(
            name='g1',
            title='G1 manual-U frozen: 656 non-manual routes XY+Z re-routed',
            module=RUN_G1,
            argv=['--baseline-dir', str(AUTHORITY),
                  '--out', str(g1_dir),
                  '--rounds', str(G1['rounds']),
                  '--round-seconds', _num(G1['round_seconds']),
                  '--top', str(G1['top'])],
            out_dir=str(g1_dir),
            validation=POLICIES['G1'],
            checkpoint_dir=str(g1_dir / 'checkpoints'),
            budget_seconds=G1['rounds'] * G1['round_seconds'],
        ),
        dict(
            name='warmstart',
            title=('warm chain G2a 2x300 s -> G2b 1x240 s -> G3 1x500 s '
                   '(each stage validates itself)'),
            module=RUN_WARMSTART,
            argv=['--g1-dir', str(g1_dir),
                  '--g2a-round-seconds', _num(G2A['round_seconds']),
                  '--g2b-round-seconds', _num(G2B['round_seconds']),
                  '--g3-round-seconds', _num(G3['round_seconds'])],
            out_dir=str(P.DIRS['warmstart']),
            validation=' -> '.join([POLICIES['G2a'], POLICIES['G2b'],
                                    POLICIES['G3']]),
            checkpoint_dir=str(P.DIRS['G2a'] / 'checkpoints')
                           + ' | .../G2b/checkpoints | .../G3/checkpoints',
            budget_seconds=(G2A['rounds'] * G2A['round_seconds']
                            + G2B['rounds'] * G2B['round_seconds']
                            + G3['rounds'] * G3['round_seconds']),
            sub_dirs=[str(P.DIRS['G2a']), str(P.DIRS['G2b']),
                      str(P.DIRS['G3'])],
        ),
        dict(
            name='g3cold',
            title=('G3 cold independent control from the authority '
                   '(same 1200 s budget as the archived campaign)'),
            module=RUN_G3,
            argv=['--start-from', 'baseline',
                  '--out', str(fair_cold),
                  '--rounds', str(G3_COLD['rounds']),
                  '--round-seconds', _num(G3_COLD['round_seconds'])],
            out_dir=str(fair_cold),
            validation=POLICIES['G3_cold'],
            checkpoint_dir=str(fair_cold / 'checkpoints'),
            budget_seconds=G3_COLD['rounds'] * G3_COLD['round_seconds'],
        ),
        dict(
            name='validate',
            title='P0/P1/P2 router functional validation under the 20H model',
            module=RUN_ROUTER_VALIDATION,
            argv=['--phases', 'P0,P1,P2'],
            out_dir=str(P.DIRS['router_validation']),
            validation='frozen (independent validator per case)',
            checkpoint_dir=str(P.DIRS['router_validation'] / 'checkpoints'),
            budget_seconds=0.0,
        ),
        dict(
            name='reports',
            title=('reports + fair/warm comparison + best_valid + archive '
                   '(run_reports)'),
            module=RUN_REPORTS,
            argv=['--archive', str(ARCHIVE_DIR)],
            out_dir=str(P.DIRS['best_valid']),
            validation='best_valid gate (validation_pass only)',
            checkpoint_dir=str(P.DIRS['reports'] / 'checkpoints'),
            budget_seconds=0.0,
        ),
    ]
    for stage in stages:
        if stage['module'] is None:
            stage['command_text'] = ('in-process: coldstart20.run_g123 '
                                     'stage_preflight (bootstrap-first)')
        else:
            stage['command_text'] = ('python -m %s %s'
                                     % (stage['module'],
                                        ' '.join(stage['argv'])))
    return stages


def _stage_map(stages):
    return {stage['name']: stage for stage in stages}


# ===========================================================================
# 20H wiring assertions (used by --dry-run; the real run relies on them too)
# ===========================================================================
def assert_20h_wiring():
    """Assert that every path of the chain resolves into the 20H G123 tree."""
    checks = {}
    B.assert_20_height_profile('run_g123 assert_20h_wiring')
    require(M is M20, 'reheight21.model is not coldstart20.model20 (import order)')
    require(len(M.PLANE_IDS) == 20,
            'expected 20 routing heights, got %d' % len(M.PLANE_IDS))
    require(19 not in M.PLANE_IDS, 'deleted plane identity 19 is still present')
    checks['model20_registered_as_reheight21_model'] = True
    checks['plane_count_20'] = [int(pid) for pid in M.PLANE_IDS]

    require(EXPERIMENT_ROOT.name == 'COLD_START_20_HEIGHT_1024',
            'experiment root is not experiments/COLD_START_20_HEIGHT_1024: %s'
            % EXPERIMENT_ROOT)
    require(G123_ROOT.name == '07_g123',
            'G123 root is not .../07_g123: %s' % G123_ROOT)
    require(G123_ROOT.parent == EXPERIMENT_ROOT,
            'G123 root is not directly under the experiment root: %s'
            % G123_ROOT)
    require(RUN_ROOT.name == 'run_xyz_joint_1024_20h',
            'unexpected 20H XYZ run directory name: %s' % RUN_ROOT)
    require(_under(RUN_ROOT, G123_ROOT),
            'xyzrouter.paths.XYZ_RUN_DIR is NOT under .../07_g123: %s'
            % RUN_ROOT)
    checks['xyz_run_dir'] = _rel(RUN_ROOT)
    checks['xyz_run_dir_under_g123'] = True

    require(AUTHORITY == RUN_ROOT / 'baseline_authoritative',
            'BASELINE_AUTHORITY is not <XYZ_RUN>/baseline_authoritative: %s'
            % AUTHORITY)
    checks['baseline_authority'] = _rel(AUTHORITY)

    env_expectations = {
        'NATIVE_JOINT_DIR': Path(P20.NATIVE3D_DEF_RUN),
        'NATIVE_PHASE1_DIR': Path(P20.NATIVE3D_ABC_RUN),
        'NON_C4_DIR': Path(P20.NONC4_ROOT),
        'E5_DIR': Path(P20.E5_DIR),
    }
    for attribute, expected in env_expectations.items():
        actual = Path(getattr(P, attribute))
        require(actual == expected,
                'xyzrouter.paths.%s=%s != COLDSTART20 value %s'
                % (attribute, actual, expected))
        require(_under(actual, EXPERIMENT_ROOT),
                'xyzrouter.paths.%s is not under the 20H experiment root: %s'
                % (attribute, actual))
        checks['xyzrouter.paths.' + attribute] = _rel(actual)

    expected_stage_dirs = {
        'G1': 'G1_manual_frozen',
        'G2a': 'G2a_manual_group_reheight',
        'G2b': 'G2b_manual_route_reheight',
        'G3': 'G3_manual_full_xyz',
        'warmstart': 'warmstart_comparison',
        'best_valid': 'best_valid',
        'reports': 'reports',
        'router_validation': 'router_validation',
        'preflight': 'preflight_audit',
    }
    for key, name in expected_stage_dirs.items():
        directory = Path(P.DIRS[key])
        require(directory.name == name,
                'xyzrouter.paths.DIRS[%r].name=%r != %r'
                % (key, directory.name, name))
        require(_under(directory, RUN_ROOT),
                'stage dir %r escapes the 20H XYZ run root: %s'
                % (key, directory))
    require(Path(P.DIRS['fair']) == RUN_ROOT / 'fair_comparison',
            'fair_comparison dir moved: %s' % P.DIRS['fair'])
    checks['stage_dirs_under_xyz_run'] = True
    checks['experiment_root'] = _rel(EXPERIMENT_ROOT)
    return checks


# ===========================================================================
# dry run: print the plan + the resolved paths, run nothing
# ===========================================================================
def _status(path):
    path = Path(path)
    if path.is_file():
        return 'file OK'
    if path.is_dir():
        return 'dir OK'
    return 'MISSING'


def print_dry_run(stages, command, source=None):
    source = Path(source) if source else PHASE2_BEST_VALID
    checks = assert_20h_wiring()
    selected = [stage for stage in stages if stage['name'] in COMMANDS[command]]
    _log('=' * 100)
    _log('[g123] 20H XYZ joint optimisation chain G1/G2a/G2b/G3 -- DRY RUN')
    _log('[g123] command          : %s' % command)
    _log('[g123] profile          : %s (%d routing heights: %d body + %d interface)'
         % (PROFILE, len(M.PLANE_IDS), len(M20.BODY_PLANES),
            len(M20.INTERFACE_PLANES)))
    _log('[g123] model            : %s (installed as reheight21.model)'
         % MODEL_NAME)
    _log('[g123] experiment root  : %s' % EXPERIMENT_ROOT)
    _log('[g123] G123 root        : %s' % G123_ROOT)
    _log('[g123] COLDSTART20_XYZ_RUN (xyzrouter.paths.XYZ_RUN_DIR)')
    _log('       = %s' % RUN_ROOT)
    _log('[g123] authority        : %s' % AUTHORITY)
    _log('[g123] phase-2 source   : %s  [%s]'
         % (source, _status(source)))
    _log('')
    _log('[g123] resolved input directories (COLDSTART20_* env bridge):')
    for key in ('INIT_RUN', 'FANOUT_BASELINE_DIR', 'NONC4_ROOT', 'E5_DIR',
                'NATIVE3D_ABC_RUN', 'NATIVE3D_DEF_RUN', 'XYZ_RUN', 'G4_ROOT',
                'MULTIARC_ROOT'):
        value = P20.ENV_PATHS.get(key)
        _log('  %-22s %s' % ('COLDSTART20_' + key, value))
    _log('')
    _log('[g123] 20H wiring assertions: PASS')
    _log('  %-40s %s' % ('xyzrouter.paths.XYZ_RUN_DIR under 07_g123',
                          checks['xyz_run_dir_under_g123']))
    _log('  %-40s %s' % ('BASELINE_AUTHORITY = <XYZ_RUN>/baseline_authoritative',
                          _rel(AUTHORITY)))
    _log('  %-40s %s' % ('reheight21.model.PLANE_IDS entries',
                          len(checks['plane_count_20'])))
    _log('  %-40s %s' % ('deleted plane 19 absent',
                          'PASS' if 19 not in M.PLANE_IDS else 'FAIL'))
    _log('')
    _log('[g123] stage plan (%d stage%s):' % (len(selected),
                                              '' if len(selected) == 1 else 's'))
    for index, stage in enumerate(selected):
        _log('  [%d] %-10s %s' % (index, stage['name'], stage['title']))
        _log('      command   : %s' % stage['command_text'])
        _log('      out dir   : %s  [%s]'
             % (stage['out_dir'], _status(stage['out_dir'])))
        if stage.get('source'):
            _log('      source    : %s  [%s]'
                 % (stage['source'], _status(stage['source'])))
        _log('      validation: %s' % stage['validation'])
        _log('      checkpts  : %s' % stage['checkpoint_dir'])
        budget = float(stage.get('budget_seconds') or 0.0)
        if budget:
            _log('      budget    : search wall-clock <= %s' % _minutes(budget))
        else:
            _log('      budget    : no search budget (snapshot / validation / '
                 'reporting)')
        for sub_dir in stage.get('sub_dirs') or ():
            _log('      sub dir   : %s  [%s]' % (sub_dir, _status(sub_dir)))
    _log('')
    _log('[g123] DRY RUN: nothing was executed and no file was written.')
    _log('=' * 100)
    return 0


# ===========================================================================
# stage 0: authority snapshot + 20H data contract + independent validation
# ===========================================================================
#: (name, expected) hard checks of the accepted 20H Phase-2 solution
def check_authority_layout(layout_dir):
    """20H data-contract checks on an accepted 1024-route layout (audit 9.5)."""
    layout_dir = Path(layout_dir)
    problems = []
    checks = {}

    def record(name, ok, detail):
        checks[name] = dict(ok=bool(ok), detail=detail)
        if not ok:
            problems.append('%s: %s' % (name, detail))

    for name in AUTHORITY_REQUIRED_FILES:
        record('file:' + name, (layout_dir / name).is_file(),
               _rel(layout_dir / name))
    if problems:
        raise RuntimeError('20H authority layout is incomplete in %s:\n  - %s'
                           % (_rel(layout_dir), '\n  - '.join(problems)))

    payload = _read_json(layout_dir / 'routes_l3d.json') or {}
    routes = payload.get('routes') or []
    record('routes_count_1024', len(routes) == 1024, len(routes))
    record('payload_route_count_1024',
           int(payload.get('route_count') or 0) == 1024,
           payload.get('route_count'))
    record('payload_routed_1024', int(payload.get('routed') or 0) == 1024,
           payload.get('routed'))
    record('payload_failed_zero', int(payload.get('failed') or 0) == 0,
           payload.get('failed'))
    route_ids = [int(route.get('route_id')) for route in routes
                 if route.get('route_id') is not None]
    record('route_ids_unique_1024', len(set(route_ids)) == 1024,
           len(set(route_ids)))
    manual_routes = [route for route in routes
                     if str(route.get('manual_group') or '').strip()]
    record('manual_route_records_%d' % M.CONTRACT_MANUAL_TOTAL,
           len(manual_routes) == M.CONTRACT_MANUAL_TOTAL, len(manual_routes))
    expected_groups = set(M.MANUAL_GROUP_SPECS)
    found_groups = {str(route.get('manual_group')).strip()
                    for route in manual_routes}
    record('manual_group_names', found_groups == expected_groups,
           sorted(found_groups))

    allowed_z = {round(float(M.plane_z(pid)), 6) for pid in M.PLANE_IDS}
    checked_z = 0
    bad_z = []
    for route in routes:
        rid = int(route.get('route_id'))
        for key in ('target_z_mm', 'start_z_mm', 'end_z_mm'):
            value = route.get(key)
            if value is None:
                continue
            checked_z += 1
            if round(float(value), 6) not in allowed_z:
                bad_z.append([rid, key, float(value)])
        for part in route.get('parts') or ():
            for key in ('z_mm', 'z0', 'z1'):
                value = part.get(key)
                if value is None:
                    continue
                checked_z += 1
                if round(float(value), 6) not in allowed_z:
                    bad_z.append([rid, '%s.%s' % (part.get('kind'), key),
                                  float(value)])
    record('flat_heights_are_20h_model_heights', not bad_z,
           dict(samples=checked_z, violations=len(bad_z), first=bad_z[:20]))
    record('deleted_plane_19_absent', 19 not in M.PLANE_IDS,
           list(M.PLANE_IDS))

    layer_planes = _read_json(layout_dir / 'layer_planes.json') or {}
    layer_planes_ok = (int(layer_planes.get('plane_count') or 0) == 20
                       and int(layer_planes.get('body_plane_count') or 0) == 18
                       and [int(value) for value in
                            layer_planes.get('plane_order') or []] ==
                       [int(pid) for pid in M.PLANE_IDS])
    record('layer_planes_20_planes_18_body_20h_order', layer_planes_ok,
           dict(plane_count=layer_planes.get('plane_count'),
                body_plane_count=layer_planes.get('body_plane_count')))
    stack_path = layout_dir / 'physical_layer_stack.json'
    if stack_path.is_file():
        stack = _read_json(stack_path) or {}
        count = stack.get('routing_plane_count', stack.get('plane_count'))
        record('physical_stack_20_planes', int(count or 0) == 20, count)
    else:
        record('physical_stack_20_planes', True, 'absent (not required)')

    rows = _read_csv_rows(layout_dir / 'assignment_1024.csv')
    record('assignment_rows_1024', len(rows) == 1024, len(rows))
    row_ids = {int(row['route_id']) for row in rows if row.get('route_id')}
    record('assignment_route_ids_match_routes', row_ids == set(route_ids),
           dict(rows=len(row_ids),
                only_rows=len(row_ids - set(route_ids)),
                only_routes=len(set(route_ids) - row_ids)))
    assignment_manual = [row for row in rows
                         if str(row.get('manual_group') or '').strip()]
    record('assignment_manual_rows_%d' % M.CONTRACT_MANUAL_TOTAL,
           len(assignment_manual) == M.CONTRACT_MANUAL_TOTAL,
           len(assignment_manual))
    assignment_groups = {str(row.get('manual_group')).strip()
                        for row in assignment_manual}
    record('assignment_manual_group_names',
           assignment_groups == expected_groups, sorted(assignment_groups))
    bad_layers = []
    for row in rows:
        value = str(row.get('target_layer') or '').strip()
        if not value:
            continue
        try:
            layer = int(float(value))
        except ValueError:
            bad_layers.append([row.get('route_id'), value])
            continue
        if layer not in M.PLANE_IDS:
            bad_layers.append([row.get('route_id'), layer])
    record('assignment_target_layers_are_20h_planes', not bad_layers,
           dict(violations=len(bad_layers), first=bad_layers[:20]))

    stats = _read_json(layout_dir / 'crossing_stats.json') or {}
    totals = stats.get('totals') or {}
    if totals:
        record('crossing_stats_present', True,
               dict(crossings=totals.get('crossings'),
                    crossing_pairs=totals.get('crossing_pairs')))
    else:
        # not fatal: the exact RouteWorld recomputation below is the authority.
        # (phase2.save_best_valid always writes crossing_stats.json, so this is
        # only a safety net for a manually assembled accepted layout.)
        checks['crossing_stats_present'] = dict(
            ok=True, detail='absent; the recomputed RouteWorld total is the '
                            'authority and is written into AUTHORITY.json')
    source_validation = _read_json(layout_dir / 'validation.json') or {}
    if problems:
        raise RuntimeError('20H authority data contract FAILED in %s:\n  - %s'
                           % (_rel(layout_dir), '\n  - '.join(problems)))
    return dict(
        layout_dir=_rel(layout_dir),
        routes=len(routes),
        manual_records=len(manual_routes),
        assignment_rows=len(rows),
        checks=checks,
        stored_crossings=(None if totals.get('crossings') is None
                          else int(totals['crossings'])),
        stored_crossing_pairs=(None if totals.get('crossing_pairs') is None
                               else int(totals['crossing_pairs'])),
        source_validation_pass=source_validation.get('validation_pass'),
    )


def recompute_authority_layout(layout_dir):
    """Rebuild the exact RouteWorld of the start layout and return its totals."""
    from ..xyzrouter import experiment as E
    baseline, state = E.load_state(Path(layout_dir), log=_log)
    return dict(
        baseline_dir=_rel(baseline['dir']),
        routes_sha256=baseline['routes_sha256'],
        assignment_sha256=baseline['assignment_sha256'],
        routes=len(state.routes),
        crossings=int(state.total),
        crossing_pairs=int(state.pairs),
        build_seconds=round(float(state.build_time), 2),
        per_route_crossings=int(sum(1 for value
                                    in state.per_route_counts()[0].values()
                                    if int(value) > 0)),
    )


def validate_authority_layout(layout_dir, out_dir):
    """Independent validator (``manual_policy='frozen'``) on the authority."""
    from ..xyzrouter import validate_xyz as VX
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    report = VX.validate_xyz(run_dir=Path(layout_dir),
                             baseline_dir=Path(layout_dir),
                             out_dir=out_dir, manual_policy='frozen')
    summary = VX.summarize_report(report)
    counts = report.get('counts') or {}
    policy = report.get('policy_report') or {}
    model = report.get('model') or {}
    synthetic = report.get('synthetic_consistency') or {}
    checks = dict(
        validation_pass=bool(report.get('validation_pass')),
        geometry_pass=bool(report.get('geometry_pass')),
        contract_pass=bool(report.get('contract_pass')),
        violations_zero=int(summary['violations']) == 0,
        routed_1024=int(counts.get('routed') or 0) == 1024,
        failed_zero=int(counts.get('failed') or 0) == 0,
        manual_contract_matched=int(policy.get('matched') or 0)
                              == M.CONTRACT_MANUAL_TOTAL,
        policy_violations_zero=int(summary['policy_violations']) == 0,
        model_plane_count_20=int(model.get('plane_count') or 0) == 20,
        model_plane_ids_20h=[int(pid) for pid in model.get('plane_ids') or []]
                            == [int(pid) for pid in M.PLANE_IDS],
        synthetic_consistency_all_passed=bool(synthetic.get('all_passed')),
    )
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise RuntimeError('independent validation of the 20H authority FAILED '
                           '(%s); report: %s'
                           % (', '.join(failed),
                              _rel(out_dir / 'validation.json')))
    return dict(
        out_dir=_rel(out_dir),
        validation_file=_rel(out_dir / 'validation.json'),
        checks=checks,
        manual_policy=report.get('manual_policy'),
        model_source=model.get('source'),
        plane_count=model.get('plane_count'),
        summary=dict(
            validation_pass=summary['validation_pass'],
            violations=summary['violations'],
            policy_violations=summary['policy_violations'],
            routed=summary['routed'],
            failed=summary['failed'],
            crossings=summary['crossings'],
            crossing_pairs=summary['crossing_pairs'],
            mid_transitions=summary['mid_transitions'],
            min_3d_clearance_mm=summary['min_3d_clearance'],
            total_length_mm=summary['total_length'],
        ),
    )


def _fill_missing_authority_files():
    """Mirror ``native3d.phase2.copy_model_files`` for missing model files.

    ``phase2.save_best_valid`` copies ``assignment_1024.csv`` /
    ``layer_planes.json`` / ``physical_layer_stack.json`` /
    ``process_rules.json`` from its Phase-1 run.  If a Phase-2 ``best_valid``
    was produced without one of them (e.g. a resume), the same fallback chain
    is applied here so the authority snapshot always carries the 20H model
    files the validator needs (audit 9.5 #1).  Provenance is recorded.
    """
    filled = {}
    for name in ('assignment_1024.csv',) + MODEL_PROVENANCE_FILES:
        target = AUTHORITY / name
        if target.is_file():
            continue
        for candidate in FALLBACK_MODEL_SOURCES:
            source = Path(candidate) / name
            if source.is_file():
                shutil.copy2(source, target)
                filled[name] = _rel(source)
                break
    return filled


def stage_preflight(stage, skip_validation=False):
    """Stage 0: snapshot the Phase-2 best_valid as ``baseline_authoritative``."""
    source = Path(stage.get('source') or PHASE2_BEST_VALID)
    routes_source = source / 'routes_l3d.json'
    if not routes_source.is_file():
        raise FileNotFoundError(
            'the accepted 20-height Native-3D Phase-2 solution is missing: %s\n'
            'run stages 05/06 first; this driver never falls back to 21-height '
            'data.' % source)
    if source.resolve() == AUTHORITY.resolve():
        raise RuntimeError('preflight source and authority are the same '
                           'directory: %s' % source)

    # Idempotent snapshot: two independent stages (e.g. G1 and the G3 cold
    # control) may be started concurrently.  Re-snapshotting (rmtree+copytree)
    # under a live reader would corrupt the authority directory, so a completed
    # snapshot of the SAME source is reused instead of rebuilt.
    authority_record = _read_json(AUTHORITY / 'AUTHORITY.json') or {}
    if (not skip_validation
            and authority_record.get('routes_sha256')
            == _sha256(source / 'routes_l3d.json')
            and (AUTHORITY / 'AUTHORITY.json').is_file()
            and (AUTHORITY / 'assignment_1024.csv').is_file()
            and (AUTHORITY / 'layer_planes.json').is_file()):
        _log('[g123] [preflight] reusing the completed authority snapshot of '
             'the same source (idempotent snapshot)')
        return dict(stage='preflight', seconds=0.0, status='reused',
                    authority=str(AUTHORITY), source=str(source))
    _log('[g123] [preflight] Phase-2 best_valid : %s' % source)
    _log('[g123] [preflight] authority snapshot: %s' % AUTHORITY)
    if AUTHORITY.exists():
        shutil.rmtree(AUTHORITY)
    AUTHORITY.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, AUTHORITY)
    for name in sorted(path.name for path in AUTHORITY.iterdir()):
        _log('          copied %s' % name)
    fallback_files = _fill_missing_authority_files()
    if fallback_files:
        _log('[g123] [preflight] filled model files missing from best_valid '
             '(native3d.phase2.copy_model_files fallback chain): %s'
             % json.dumps(fallback_files, ensure_ascii=False))

    contract = check_authority_layout(AUTHORITY)
    _log('[g123] [preflight] 20H data contract: PASS (%d checks, %d routes, '
         '%d manual records, every flat z a 20H height)'
         % (len(contract['checks']), contract['routes'],
            contract['manual_records']))

    recomputed = recompute_authority_layout(AUTHORITY)
    _log('[g123] [preflight] recomputed start layout: crossings=%d pairs=%d '
         '(%.2fs)' % (recomputed['crossings'], recomputed['crossing_pairs'],
                       recomputed['build_seconds']))
    stored = contract['stored_crossings']
    if stored is not None:
        require(recomputed['crossings'] == int(stored),
                'recomputed crossing total %d != stored authority '
                'crossing_stats %d' % (recomputed['crossings'], stored))
    stored_pairs = contract['stored_crossing_pairs']
    if stored_pairs is not None:
        require(recomputed['crossing_pairs'] == int(stored_pairs),
                'recomputed crossing pairs %d != stored authority '
                'crossing_stats %d' % (recomputed['crossing_pairs'],
                                       stored_pairs))

    validation_dir = PREFLIGHT_DIR / 'validation_authoritative'
    if skip_validation:
        validation = dict(skipped=True,
                          reason='--skip-authority-validation (debug only)')
        _log('[g123] [preflight] WARNING: independent authority validation '
             'skipped (debug flag)')
    else:
        _log('[g123] [preflight] independent frozen validation of the '
             'authority (validate_xyz, manual_policy=frozen)')
        validation = validate_authority_layout(AUTHORITY, validation_dir)
        _log('[g123] [preflight] independent validation: PASS '
             '(routed=%s crossings=%s min 3D clearance=%s mm)'
             % (validation['summary']['routed'],
                validation['summary']['crossings'],
                validation['summary']['min_3d_clearance_mm']))

    files = {}
    for path in sorted(AUTHORITY.rglob('*')):
        if not path.is_file():
            continue
        relative = str(path.relative_to(AUTHORITY)).replace('\\', '/')
        files[relative] = dict(bytes=path.stat().st_size,
                               sha256=_sha256(path))
    sha_path = AUTHORITY / 'SHA256.json'
    _write_json(sha_path, dict(
        schema='coldstart20_xyz_authority_sha256_v1',
        algorithm='sha256',
        snapshot_dir=_rel(AUTHORITY),
        source_dir=_rel(source),
        note=('byte copies of the accepted 20H Phase-2 best_valid; the '
              'independent-validator report is stored under '
              'preflight_audit/validation_authoritative/ (not inside this '
              'snapshot)'),
        file_count=len(files),
        files=files,
    ))
    authority = dict(
        schema='coldstart20_xyz_authority_v1',
        profile=PROFILE,
        model=MODEL_NAME,
        generated_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
        generated_by='four_side_1024.fanout1024.coldstart20.run_g123',
        experiment_root=_rel(EXPERIMENT_ROOT),
        snapshot_dir=_rel(AUTHORITY),
        source_best_valid=_rel(source),
        fallback_model_files=fallback_files,
        routes_sha256=_sha256(AUTHORITY / 'routes_l3d.json'),
        assignment_sha256=_sha256(AUTHORITY / 'assignment_1024.csv'),
        layer_planes_sha256=_sha256(AUTHORITY / 'layer_planes.json'),
        stored_crossings=contract['stored_crossings'],
        stored_crossing_pairs=contract['stored_crossing_pairs'],
        recomputed_crossings=recomputed['crossings'],
        recomputed_crossing_pairs=recomputed['crossing_pairs'],
        recomputed_routes=recomputed['routes'],
        contract=contract,
        independent_validation=validation,
        sha256_index=_rel(sha_path),
        sha256_index_sha256=_sha256(sha_path),
        files=files,
        notes=['This directory is xyzrouter.paths.BASELINE_AUTHORITY: G1 and '
               'G3_cold start here; G2a/G2b/G3 are chained through the stage '
               'directories.',
               'The 21-height preflight_audit.py is intentionally NOT used '
               '(it audits the frozen 2409/E5 21H provenance).'],
    )
    authority_path = AUTHORITY / 'AUTHORITY.json'
    _write_json(authority_path, authority)
    report = dict(
        schema='coldstart20_xyz_preflight_v1',
        profile=PROFILE,
        generated_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
        source_best_valid=_rel(source),
        authority_dir=_rel(AUTHORITY),
        authority_json=_rel(authority_path),
        fallback_model_files=fallback_files,
        sha256_json=_rel(sha_path),
        contract=contract,
        recomputed=recomputed,
        independent_validation=validation,
        files=files,
        notes=['20H replacement for xyzrouter.preflight_audit: authority '
               'snapshot + SHA256 + 20H data contract + independent frozen '
               'validation.'],
    )
    report_path = PREFLIGHT_DIR / 'preflight_authority.json'
    _write_json(report_path, report)
    _log('[g123] [preflight] wrote %s' % report_path)
    _log('[g123] [preflight] wrote %s' % sha_path)
    _log('[g123] [preflight] wrote %s' % authority_path)
    return dict(
        source_best_valid=_rel(source),
        authority_dir=_rel(AUTHORITY),
        routes_sha256=authority['routes_sha256'],
        crossing_stats=dict(crossings=contract['stored_crossings'],
                            crossing_pairs=contract['stored_crossing_pairs']),
        recomputed_crossings=recomputed['crossings'],
        recomputed_crossing_pairs=recomputed['crossing_pairs'],
        contract_checks=len(contract['checks']),
        independent_validation=validation,
        sha256_json=_rel(sha_path),
        authority_json=_rel(authority_path),
        preflight_report=_rel(report_path),
    )


# ===========================================================================
# stage verification (a 20H stage is not "done" unless its validator PASSed)
# ===========================================================================
def verify_stage_dir(stage_dir, label, policy):
    """Check one G stage: validator PASS, zero violations, routes SHA, summary."""
    stage_dir = Path(stage_dir)
    require((stage_dir / 'routes_l3d.json').is_file(),
            '%s: routes_l3d.json missing in %s' % (label, _rel(stage_dir)))
    validation = _load_validation(stage_dir)
    require(validation is not None,
            '%s: validation report missing in %s'
            % (label, _rel(stage_dir / 'validation' / 'validation.json')))
    require(validation.get('validation_pass') is True,
            '%s: validator FAILED (pass=%r violations=%r) in %s'
            % (label, validation.get('validation_pass'),
               validation.get('violation_count'), _rel(stage_dir)))
    violations = int(validation.get('violation_count') or 0)
    require(violations == 0, '%s: %d validation violations' % (label, violations))
    manual_policy = validation.get('manual_policy')
    require(manual_policy in (None, policy),
            '%s: manual_policy=%r, expected %r'
            % (label, manual_policy, policy))
    plan = _read_json(stage_dir / 'SHA256.json') or {}
    routes_sha = _sha256(stage_dir / 'routes_l3d.json')
    recorded = plan.get('routes_l3d_json')
    if recorded is not None:
        require(routes_sha == recorded,
                '%s: routes_l3d.json sha does not match SHA256.json' % label)
    summary = _read_json(stage_dir / 'summary.json') or {}
    counts = validation.get('counts') or {}
    return dict(
        stage=label,
        dir=_rel(stage_dir),
        policy=manual_policy or policy,
        validation_pass=True,
        violations=violations,
        routed=counts.get('routed'),
        failed=counts.get('failed'),
        crossings=counts.get('same_plane_crossings'),
        crossing_pairs=counts.get('same_plane_crossing_pairs'),
        min_3d_clearance_mm=counts.get('min_3d_clearance_mm'),
        total_length_mm=counts.get('total_length_mm'),
        routes_sha256=routes_sha,
        summary=dict(
            start_crossings=summary.get('start_crossings',
                                        summary.get('baseline_crossings')),
            final_crossings=summary.get('final_crossings'),
            accepted=(summary.get('accepted_changes')
                      if summary.get('accepted_changes') is not None
                      else summary.get('accepted_nonmanual')),
        ),
    )


def verify_stage(stage):
    name = stage['name']
    out_dir = Path(stage['out_dir'])
    if name == 'g1':
        return dict(name=name, out_dir=_rel(out_dir),
                    **verify_stage_dir(out_dir, 'G1', POLICIES['G1']))
    if name == 'warmstart':
        chain_dir = Path(P.DIRS['warmstart'])
        chain = _read_json(chain_dir / 'summary.json') or {}
        steps = []
        for label, key in (('G2a', 'G2a'), ('G2b', 'G2b'), ('G3', 'G3')):
            steps.append(verify_stage_dir(Path(P.DIRS[key]), label,
                                          POLICIES[label]))
        require(chain.get('steps'), 'warm chain summary missing in %s'
                % _rel(chain_dir / 'summary.json'))
        for step in chain.get('steps') or ():
            require(int(step.get('returncode') or 0) == 0,
                    'warm chain stage %r returned rc=%r'
                    % (step.get('step'), step.get('returncode')))
        return dict(name=name, out_dir=_rel(chain_dir),
                    chain=[step.get('step') for step in
                           chain.get('steps') or ()],
                    stages=steps)
    if name == 'g3cold':
        return dict(name=name, out_dir=_rel(out_dir),
                    **verify_stage_dir(out_dir, 'G3_cold',
                                       POLICIES['G3_cold']))
    if name == 'validate':
        root = Path(P.DIRS['router_validation'])
        strategy = _read_json(root / 'strategy_stats.json') or {}
        validators = strategy.get('validators') or {}
        _log('[g123] [validate] aggregate validators: %s'
             % json.dumps(validators, sort_keys=True))
        require(validators and all(value is True for value in
                                   validators.values()),
                'P0/P1/P2 aggregate validation is not all PASS: %s'
                % json.dumps(validators, sort_keys=True))
        cases = []
        for label, directory in (('P0', root / 'P0'), ('P1', root / 'P1'),
                                 ('P2_z_only', root / 'P2' / 'z_only'),
                                 ('P2_xy_z', root / 'P2' / 'xy_z')):
            summary = _read_json(directory / 'validation_summary.json')
            require(summary is not None,
                    '%s: validation_summary.json missing in %s'
                    % (label, _rel(directory)))
            require(bool(summary.get('hard_requirements_ok')),
                    '%s: validator hard requirements FAILED: %s'
                    % (label, json.dumps(summary.get('hard_requirements'))))
            cases.append(dict(
                case=label, dir=_rel(directory),
                hard_requirements_ok=True,
                validation_pass=bool(summary.get('validation_pass')),
                violations=summary.get('violations'),
                routed=summary.get('routed'),
                crossings=summary.get('crossings'),
                manual=summary.get('manual'),
                validation_file=summary.get('validation_file'),
            ))
        return dict(name=name, out_dir=_rel(root),
                    aggregate_validators=validators, cases=cases)
    if name == 'reports':
        best_dir = Path(P.DIRS['best_valid'])
        best = _read_json(best_dir / 'BEST.json')
        require(best is not None,
                'best_valid/BEST.json missing: %s' % _rel(best_dir))
        require(best.get('validation_pass') is True,
                'best_valid is not validator-PASS: %s'
                % json.dumps(best.get('validation_pass')))
        metrics = _read_json(Path(P.DIRS['reports']) / 'comparison_metrics.json')
        require(metrics is not None,
                'reports/comparison_metrics.json missing')
        require((best_dir / 'routes_l3d.json').is_file(),
                'best_valid/routes_l3d.json missing')
        require((best_dir / 'assignment_1024.csv').is_file(),
                'best_valid/assignment_1024.csv missing')
        return dict(
            name=name,
            out_dir=_rel(Path(P.DIRS['reports'])),
            best_valid_dir=_rel(best_dir),
            best_experiment=best.get('experiment'),
            best_crossings=best.get('crossings'),
            best_baseline_crossings=best.get('baseline_crossings'),
            validation_pass=True,
            report_metrics=list(metrics.keys()),
        )
    raise RuntimeError('unknown stage %r' % name)


# ===========================================================================
# final freeze + run summary
# ===========================================================================
def finalize_run(command, stages, started_at, started_monotonic):
    executed = [stage['name'] for stage in stages]
    final = dict(best_valid=None)
    if 'reports' in executed:
        best_dir = Path(P.DIRS['best_valid'])
        require(best_dir.is_dir(), 'best_valid missing after run_reports')
        copied = []
        for name in MODEL_PROVENANCE_FILES:
            source = AUTHORITY / name
            target = best_dir / name
            if source.is_file() and not target.exists():
                shutil.copy2(source, target)
                copied.append(name)
        if copied:
            _log('[g123] [final] copied 20H model provenance into best_valid: %s'
                 % ', '.join(copied))
        best = _read_json(best_dir / 'BEST.json') or {}
        contract = check_authority_layout(best_dir)
        from ..xyzrouter import experiment as E
        baseline, state = E.load_state(best_dir, log=_log)
        stats = _read_json(best_dir / 'crossing_stats.json') or {}
        stored = (stats.get('totals') or {}).get('crossings')
        if stored is not None:
            require(int(state.total) == int(stored),
                    'best_valid recomputed crossings %d != crossing_stats %d'
                    % (int(state.total), int(stored)))
        routes_sha = _sha256(best_dir / 'routes_l3d.json')
        freeze = dict(
            schema='coldstart20_xyz_final_freeze_v1',
            profile=PROFILE,
            model=MODEL_NAME,
            frozen_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
            selected_experiment=best.get('experiment'),
            source_dir=best.get('source_dir'),
            crossings=int(state.total),
            crossing_pairs=int(state.pairs),
            stored_crossings=stored,
            routes_sha256=routes_sha,
            manual_policy=POLICIES.get(str(best.get('experiment')), 'unknown'),
            validation_pass=best.get('validation_pass'),
            layout_contract_checks=len(contract['checks']),
            copied_model_files=copied,
            notes=['best_valid is the deliverable start point of the G4 stage.',
                   'It was re-loaded and its exact crossing total re-verified '
                   'against crossing_stats.json after run_reports.'],
        )
        _write_json(best_dir / 'FINAL.json', freeze)
        final = dict(
            best_valid_dir=_rel(best_dir),
            best_experiment=freeze['selected_experiment'],
            best_crossings=freeze['crossings'],
            best_crossing_pairs=freeze['crossing_pairs'],
            best_baseline_crossings=best.get('baseline_crossings'),
            best_routes_sha256=routes_sha,
            best_validation_pass=best.get('validation_pass'),
            final_json=_rel(best_dir / 'FINAL.json'),
            archive=_rel(ARCHIVE_DIR) if ARCHIVE_DIR.exists() else None,
        )
        _log('[g123] [final] best_valid = %s (%d crossings, sha %s)'
             % (freeze['selected_experiment'], freeze['crossings'],
                routes_sha[:16]))
    elapsed = time.time() - started_monotonic
    summary = dict(
        schema='coldstart20_xyz_g123_driver_v1',
        profile=PROFILE,
        model=MODEL_NAME,
        command=command,
        generated_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
        started_at=started_at,
        elapsed_s=round(elapsed, 1),
        ok=True,
        error=None,
        project_root=str(PROJECT_ROOT),
        experiment_root=_rel(EXPERIMENT_ROOT),
        run_root=_rel(RUN_ROOT),
        authority_dir=_rel(AUTHORITY),
        log=_rel(LOG_PATH),
        budgets=dict(
            G1='%d rounds x %s s, top %d'
               % (G1['rounds'], _num(G1['round_seconds']), G1['top']),
            G2a='%d rounds x %s s, group delta budget %d'
                % (G2A['rounds'], _num(G2A['round_seconds']),
                   G2A['delta_budget']),
            G2b='%d round x %s s, route delta budget %d'
                % (G2B['rounds'], _num(G2B['round_seconds']),
                   G2B['route_delta_budget']),
            G3='%d round x %s s'
               % (G3['rounds'], _num(G3['round_seconds'])),
            G3_cold='%d round x %s s'
                    % (G3_COLD['rounds'], _num(G3_COLD['round_seconds'])),
        ),
        seeds=dict(engine_seed=20261104,
                   note='the frozen engine seed is written by optimizer.py; '
                        'G1/G2/G3 are deterministic per candidate order'),
        checkpoint_scoping=dict(
            global_dir=_rel(Path(P.DIRS['checkpoints'])),
            per_stage='<stage out_dir>/checkpoints/<checkpoint_%04d>',
            note='patch_g123.py namespaces optimizer checkpoints by stage; '
                 'the frozen campaign defect (G1/G3_cold shared global dir) '
                 'cannot recur'),
        stages=executed,
        completed=executed,
        expected_search_budget_s=sum(float(stage.get('budget_seconds') or 0.0)
                                      for stage in stages),
        records=[dict(name=stage['name'], module=stage['module'],
                      out_dir=_rel(stage['out_dir']),
                      checkpoint_dir=stage['checkpoint_dir'],
                      seconds=round(stage.get('seconds', 0.0), 1),
                      argv=stage['argv'])
                 for stage in stages],
        final=final,
    )
    # stage execution payloads (verification evidence)
    summary['stage_evidence'] = [dict(stage.get('evidence') or {})
                                 for stage in stages]
    _write_json(SUMMARY_PATH, summary)
    _log('[g123] wrote %s' % SUMMARY_PATH)
    _log('[g123] CHAIN %s: %s in %s'
         % (command.upper(), 'PASS', _minutes(elapsed)))
    return summary


def _failure_summary(command, stages, started_at, started_monotonic, exc):
    elapsed = time.time() - started_monotonic
    try:
        text = traceback.format_exc()
    except Exception:  # noqa: BLE001
        text = ''
    summary = dict(
        schema='coldstart20_xyz_g123_driver_v1',
        profile=PROFILE,
        model=MODEL_NAME,
        command=command,
        generated_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
        started_at=started_at,
        elapsed_s=round(elapsed, 1),
        ok=False,
        error='%s: %s' % (type(exc).__name__, exc),
        traceback=text,
        project_root=str(PROJECT_ROOT),
        experiment_root=_rel(EXPERIMENT_ROOT),
        run_root=_rel(RUN_ROOT),
        logs=_rel(LOG_PATH),
        records=[dict(name=stage['name'], module=stage['module'],
                      out_dir=_rel(stage['out_dir']),
                      seconds=round(stage.get('seconds', 0.0), 1))
                 for stage in stages],
        completed=[stage['name'] for stage in stages
                   if stage.get('seconds') is not None],
    )
    try:
        _write_json(SUMMARY_PATH, summary)
    except OSError:
        pass
    return summary


# ===========================================================================
# execution
# ===========================================================================
def _check_prerequisites(stage):
    name = stage['name']
    if name == 'warmstart':
        require((Path(P.DIRS['G1']) / 'routes_l3d.json').is_file(),
                'G1 output missing (%s); run `run_g123 g1` first'
                % _rel(Path(P.DIRS['G1'])))
    if name == 'reports':
        for key in ('G1', 'G2a', 'G2b', 'G3'):
            require((Path(P.DIRS[key]) / 'routes_l3d.json').is_file(),
                    '%s output missing (%s); run the chain up to G3 first'
                    % (key, _rel(Path(P.DIRS[key]))))


def run_chain(command, stages, args):
    #: fail before anything is written if the 20H wiring is wrong (e.g. a
    #: stray COLDSTART20_XYZ_RUN would otherwise create a log outside 07_g123)
    wiring = assert_20h_wiring()
    selected = [stage for stage in stages if stage['name'] in COMMANDS[command]]
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    PREFLIGHT_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    started_at = time.strftime('%Y-%m-%dT%H:%M:%S')
    started = time.time()
    tee = _Tee(sys.stdout, LOG_PATH)
    completed = []
    try:
        with contextlib.redirect_stdout(tee), contextlib.redirect_stderr(tee):
            _log('=' * 100)
            _log('[g123] 20H XYZ joint optimisation chain G1/G2a/G2b/G3')
            _log('[g123] command=%s  profile=%s  model=%s  planes=%d'
                 % (command, PROFILE, MODEL_NAME, len(M.PLANE_IDS)))
            _log('[g123] run root=%s' % RUN_ROOT)
            _log('[g123] authority=%s' % AUTHORITY)
            _log('[g123] started=%s' % started_at)
            _log('[g123] 20H wiring assertions: PASS (%d checks)'
                 % len(wiring))
            for stage in selected:
                _log('-' * 100)
                _log('[g123] [%s] %s' % (stage['name'], stage['title']))
                _log('[g123] [%s] command: %s'
                     % (stage['name'], stage['command_text']))
                _check_prerequisites(stage)
                stage_started = time.time()
                if stage['name'] == 'preflight':
                    evidence = stage_preflight(
                        stage,
                        skip_validation=bool(args.skip_authority_validation))
                else:
                    module = importlib.import_module(stage['module'])
                    returncode = int(module.main(list(stage['argv'])) or 0)
                    require(returncode == 0,
                            '%s returned rc=%d' % (stage['module'],
                                                   returncode))
                    evidence = verify_stage(stage)
                stage['seconds'] = round(time.time() - stage_started, 1)
                stage['evidence'] = dict(evidence)
                completed.append(stage['name'])
                _log('[g123] [%s] OK in %s'
                     % (stage['name'], _minutes(stage['seconds'])))
            summary = finalize_run(command, selected, started_at, started)
            _log('[g123] stages completed: %s' % ', '.join(completed))
            _log('=' * 100)
            return 0, summary
    except Exception as exc:  # noqa: BLE001 - the driver records and fails
        tee.write('\n[g123] FAILED: %s: %s\n'
                  % (type(exc).__name__, exc))
        traceback.print_exc(file=tee)
        tee.flush()
        summary = _failure_summary(command, selected, started_at, started, exc)
        return 1, summary
    finally:
        tee.flush()
        tee.close()


# ===========================================================================
# CLI
# ===========================================================================
def build_parser():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        'command', nargs='?', default='all', choices=sorted(COMMANDS),
        help='stage(s) to run; "plan" or --dry-run only prints the resolved '
             'plan (default: all)')
    parser.add_argument(
        '--dry-run', action='store_true',
        help='resolve every path, assert the 20H wiring, print the plan and '
             'exit without running a stage')
    parser.add_argument(
        '--source', default=None,
        help='accepted 20H Native-3D Phase-2 best_valid directory '
             '(default: COLDSTART20_NATIVE3D_DEF_RUN/best_valid = %s)'
             % PHASE2_BEST_VALID)
    parser.add_argument(
        '--skip-authority-validation', action='store_true',
        help='debug only: skip the independent frozen validation of the '
             'authority snapshot (never for a reported run)')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    B.install()
    B.assert_20_height_profile('run_g123 main')
    stages = build_plan(args.source)
    if args.dry_run or args.command == 'plan':
        return print_dry_run(stages, args.command, source=args.source)
    print('[g123] log file: %s' % LOG_PATH, flush=True)
    returncode, summary = run_chain(args.command, stages, args)
    if returncode != 0:
        print('[g123] FAILED: %s' % summary.get('error'), flush=True)
        print('[g123] summary: %s' % SUMMARY_PATH, flush=True)
    else:
        print('[g123] OK: %s stages, %s'
              % (len(summary.get('completed') or []),
                 _minutes(summary.get('elapsed_s'))), flush=True)
        print('[g123] summary: %s' % SUMMARY_PATH, flush=True)
    return returncode


if __name__ == '__main__':
    sys.exit(main())
