# -*- coding: utf-8 -*-
"""Bootstrap-first driver for every **G4 global ALNS arm** on the 20-height model.

The frozen G4 package (``four_side_1024/fanout1024/xyzrouter/g4``) is written for
the 21-height pipeline: each arm module does ``from ...reheight21 import model as
M`` at import time and reads the plane table / interface heights / run dirs from
that single seam.  This driver installs :mod:`coldstart20.bootstrap` (which
registers ``model20`` as ``reheight21.model``) **before** any G4 module is
imported, then wraps the unmodified arm entry points:

===================================  ==========================================
sub-command                          real entry point
===================================  ==========================================
``start``                            verify/copy the 20H G3 ``best_valid`` as
                                     the common G4 start + write ``START.json``
``c0``                               ``g4.c0_continue`` (legacy G3 optimizer)
``a``                                ``g4.run_g4a`` (fixed manual-U groups)
``b``                                ``g4.run_g4b`` (dynamic regrouping)
``c-frozen``                         ``g4.run_g4_engine --arm G4c_frozen``
``c-free``                           ``g4.run_g4_engine --arm G4c_free``
``d``                                ``g4.run_g4_engine --arm G4d``
``chain``                            ``g4.fair_runner.build_chain`` +
                                     owner runners for the pending links
``validate``                         ``xyzrouter.validate_xyz`` (frozen
                                     independent validator, 20H profile)
``all``                              ``start`` + every arm + ``chain``
``_run``                             internal: profile-first module launcher
===================================  ==========================================

Safety model
------------
* Every command (including every arm subprocess) starts from this module, whose
  first two imports are ``coldstart20.bootstrap`` (installs the profile) and
  ``coldstart20.model20``; ``B.assert_20_height_profile()`` is re-asserted before
  every dispatch.  A silent 21-height run is impossible.
* ``start`` is mandatory before any arm: it hard-verifies the 20H G3
  ``best_valid`` (profile guard, 1024 routes / 368 manual-U, exact crossing
  recount in the true ``RouteWorld``, ``layer_planes.json`` table, validator
  report) and writes the archive fingerprint ``08_g4/START.json``.
* Arm subprocesses are launched as
  ``python -m ...coldstart20.run_g4 _run --module <arm module> -- <arm argv>``,
  i.e. the profile is installed in a fresh process exactly as with the frozen
  ``fair_runner`` (same start, same seed, same declared budget contract).
* ``--dry-run`` (available on every sub-command) only *plans*: it prints the
  exact argv, the start point, the out dir and the declared budget, and never
  imports an arm module or writes anything.  This is why the plan can be
  produced before the 20H G3 output exists.

Declared budget contract (frozen SPEC_G4 §3.2, unchanged by the 20H port)
--------------------------------------------------------------------------
``route_3d_checks = 30000``, ``d56_candidate_evals = 120000`` per arm; wall
clock: C0 / G4a / G4b 1200 s, G4c_frozen / G4c_free 1800 s, G4d 3600 s; every
arm uses seed ``20261104`` and the same 20H G3 start.  Optional equal-counted
mode (``--counted-d56-budget 24000 --counted-checks-guard 9000``, as used by the
frozen strict-multi-arc ablation) is forwarded to G4c/G4d.  Budgets are never
silently shortened: an explicit ``--seconds`` is recorded in the launch record.

Usage
-----
::

    .venv\\Scripts\\python.exe -m four_side_1024.fanout1024.coldstart20.run_g4 start
    .venv\\Scripts\\python.exe -m ...coldstart20.run_g4 c0   --dry-run
    .venv\\Scripts\\python.exe -m ...coldstart20.run_g4 c-free
    .venv\\Scripts\\python.exe -m ...coldstart20.run_g4 d --seconds 3600 --tag formal
    .venv\\Scripts\\python.exe -m ...coldstart20.run_g4 validate --arm c-free
    .venv\\Scripts\\python.exe -m ...coldstart20.run_g4 chain --run-chain
    .venv\\Scripts\\python.exe -m ...coldstart20.run_g4 all --dry-run
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import bootstrap as B          # installs the 20-height profile on import
from . import model20 as M
from . import paths20 as P20

ROOT = Path(M.ROOT)
G4_ROOT = Path(P20.G4_ROOT)

DRIVER_MODULE = 'four_side_1024.fanout1024.coldstart20.run_g4'
VALIDATOR_MODULE = 'four_side_1024.fanout1024.xyzrouter.validate_xyz'
DEFAULT_SEED = 20261104
DEFAULT_TAG = ''
START_COPY_NAME = '00_start_g3'
DRIVER_STATE_DIR = '_driver'

#: frozen SPEC_G4 §3.2 budget contract (identical to g4.paths)
DEFAULT_BUDGET = dict(route_3d_checks=30000, d56_candidate_evals=120000,
                      wall_seconds=1800)
ARM_BUDGETS = {
    'C0': dict(DEFAULT_BUDGET, wall_seconds=1200),
    'G4a': dict(DEFAULT_BUDGET, wall_seconds=1200),
    'G4b': dict(DEFAULT_BUDGET, wall_seconds=1200),
    'G4c_frozen': dict(DEFAULT_BUDGET, wall_seconds=1800),
    'G4c_free': dict(DEFAULT_BUDGET, wall_seconds=1800),
    'G4d': dict(DEFAULT_BUDGET, wall_seconds=3600),
}
#: equal-counted mode caps (frozen strict-multi-arc ablation used 24000 / 9000)
COUNTED_D56_BUDGET = 24000
COUNTED_CHECKS_GUARD = 9000

#: mirror of ``g4.paths.ARM_DIRS`` relative to ``P20.G4_ROOT``; only used when
#: the real ``g4.paths`` module cannot be imported yet (20H G3 start absent, i.e.
#: dry-run planning).  ``selfcheck`` compares both tables when it can.
ARM_DIR_NAMES = {
    'C0': '01_arm_C0',
    'G4a': '02_arm_G4a',
    'G4b': '03_arm_G4b',
    'G4c_frozen': '04_arm_G4c_frozen',
    'G4c_free': '05_arm_G4c_free',
    'G4d': '06_arm_G4d',
    'best_valid': '07_best_valid',
    'chain': '08_progressive_chain',
    'plots': '09_plots',
    'reports': '10_reports',
    'audit': '00_baseline_audit',
    'checkpoints': 'checkpoints',
    'code': 'code',
}

#: sub-command -> arm entry point / CLI flags it must receive
ARM_SPECS = {
    'c0': dict(
        command='c0', arm='C0', dir_key='C0', arm_flag=None,
        module='four_side_1024.fanout1024.xyzrouter.g4.c0_continue',
        time_flag='--seconds', out_flag='--out', start_flag='--start-dir',
        counted=False, resume_flag=False, tag_flag=False,
        description='C0 control: legacy G3 optimizer continues, no new DOF'),
    'a': dict(
        command='a', arm='G4a', dir_key='G4a', arm_flag=None,
        module='four_side_1024.fanout1024.xyzrouter.g4.run_g4a',
        time_flag='--budget-seconds', out_flag='--out-dir', start_flag=None,
        counted=False, resume_flag=True, tag_flag=True,
        description='G4a: 8 fixed manual-U groups, whole-group XY+Z redesign'),
    'b': dict(
        command='b', arm='G4b', dir_key='G4b', arm_flag=None,
        module='four_side_1024.fanout1024.xyzrouter.g4.run_g4b',
        time_flag='--budget-seconds', out_flag='--out-dir', start_flag=None,
        counted=False, resume_flag=True, tag_flag=True,
        description='G4b: dynamic manual-U regrouping + full XY+Z replanning'),
    'c-frozen': dict(
        command='c-frozen', arm='G4c_frozen', dir_key='G4c_frozen',
        arm_flag='G4c_frozen',
        module='four_side_1024.fanout1024.xyzrouter.g4.run_g4_engine',
        time_flag='--seconds', out_flag='--out-dir', start_flag='--start-dir',
        counted=True, resume_flag=True, tag_flag=True,
        description='G4c-frozen: joint make-way LNS, 368 manual-U frozen'),
    'c-free': dict(
        command='c-free', arm='G4c_free', dir_key='G4c_free',
        arm_flag='G4c_free',
        module='four_side_1024.fanout1024.xyzrouter.g4.run_g4_engine',
        time_flag='--seconds', out_flag='--out-dir', start_flag='--start-dir',
        counted=True, resume_flag=True, tag_flag=True,
        description='G4c-free: joint make-way LNS, manual-U free'),
    'd': dict(
        command='d', arm='G4d', dir_key='G4d', arm_flag='G4d',
        module='four_side_1024.fanout1024.xyzrouter.g4.run_g4_engine',
        time_flag='--seconds', out_flag='--out-dir', start_flag='--start-dir',
        counted=True, resume_flag=True, tag_flag=True,
        description='G4d: global large-neighbourhood ALNS over all 1024 routes'),
}
ARM_ORDER = ('c0', 'a', 'b', 'c-frozen', 'c-free', 'd')

#: files copied from the G3 ``best_valid`` into the frozen common-start copy
START_FILES = ('routes_l3d.json', 'assignment_1024.csv',
               'crossing_stats.json', 'layer_planes.json', 'SHA256.json',
               'BEST.json', 'summary.json', 'config.json')

_GP_STATE = {'tried': False, 'module': None, 'error': None}


# ===========================================================================
# small helpers
# ===========================================================================
def _log(message):
    print('[run_g4] %s' % str(message), flush=True)


def _warn(message):
    print('[run_g4] WARNING: %s' % str(message), flush=True)


def _now():
    return time.strftime('%Y-%m-%dT%H:%M:%S')


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


_MISSING = object()


def _read_json(path, default=_MISSING):
    path = Path(path)
    if not path.exists():
        if default is not _MISSING:
            return default
        raise FileNotFoundError(str(path))
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        if default is not _MISSING:
            return default
        raise


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False,
                               default=str) + '\n', encoding='utf-8')
    return path


def _read_csv(path):
    with Path(path).open('r', encoding='utf-8-sig', newline='') as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _rel(path):
    """Project-relative POSIX path when possible (stable archive text)."""
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except (ValueError, OSError):
        return str(path)


def _python():
    return sys.executable


def _split_extra(text):
    if not text:
        return []
    return [part for part in str(text).split() if part]


def _num(value):
    value = float(value)
    return str(int(value)) if value.is_integer() else str(value)


def _blocked(message, code=2):
    print('[run_g4] BLOCKED: %s' % str(message), file=sys.stderr, flush=True)
    return code


# ===========================================================================
# g4.paths / arm dirs / budgets (with a planning mirror before the start exists)
# ===========================================================================
def _clear_g4_paths_cache():
    _GP_STATE.update(tried=False, module=None, error=None)


def g4_paths(required=False):
    """The patched ``g4.paths`` module, or ``None`` when it cannot import yet.

    ``g4.paths`` computes the G3 start fingerprint at import time and raises
    under the 20H profile while the G3 ``best_valid`` does not exist.  The driver
    treats that as "plan mode" (dry-run): the arm dirs / budgets are then taken
    from the mirror tables above.  Any real run passes ``required=True`` and is
    blocked with the original error message instead of guessing.
    """
    if not _GP_STATE['tried']:
        _GP_STATE['tried'] = True
        try:
            from ..xyzrouter.g4 import paths as GP
            _GP_STATE['module'] = GP
        except RuntimeError as error:  # 20H profile + missing G3 start
            _GP_STATE['error'] = error
    module = _GP_STATE['module']
    if module is None and required:
        print('[run_g4] BLOCKED: the 20H G3 start point is not ready: %s'
              % _GP_STATE['error'], file=sys.stderr, flush=True)
        raise SystemExit(2)
    return module


def _arm_dir(dir_key, out_dir=None):
    if out_dir:
        return Path(out_dir)
    GP = g4_paths()
    if GP is not None:
        return Path(GP.ARM_DIRS[dir_key])
    return G4_ROOT / ARM_DIR_NAMES[dir_key]


def _start_dir_default():
    GP = g4_paths()
    if GP is not None:
        return Path(GP.START_DIR)
    return Path(P20.XYZ_RUN) / 'best_valid'      # == xyzrouter.paths.DIRS['best_valid']


def _arm_budget(budget_key):
    """Frozen per-arm budget; cross-checked against ``g4.paths`` when possible."""
    mirror = dict(ARM_BUDGETS[budget_key])
    GP = g4_paths()
    if GP is not None:
        reference = dict(GP.ARM_BUDGETS[budget_key])
        if reference != mirror:
            _warn('budget contract drift: g4.paths=%s driver mirror=%s '
                  '(using g4.paths)' % (reference, mirror))
        return reference
    return mirror


def _budget_lines():
    return [
        'route_3d_checks=%d  d56_candidate_evals=%d' % (
            int(DEFAULT_BUDGET['route_3d_checks']),
            int(DEFAULT_BUDGET['d56_candidate_evals'])),
        'wall seconds: C0=%d G4a=%d G4b=%d G4c_frozen=%d G4c_free=%d G4d=%d' % (
            ARM_BUDGETS['C0']['wall_seconds'],
            ARM_BUDGETS['G4a']['wall_seconds'],
            ARM_BUDGETS['G4b']['wall_seconds'],
            ARM_BUDGETS['G4c_frozen']['wall_seconds'],
            ARM_BUDGETS['G4c_free']['wall_seconds'],
            ARM_BUDGETS['G4d']['wall_seconds']),
        'seed=%d  equal-counted mode: --counted-d56-budget %d '
        '--counted-checks-guard %d' % (
            DEFAULT_SEED, COUNTED_D56_BUDGET, COUNTED_CHECKS_GUARD),
    ]


def _profile_lines():
    return [
        'profile=%s installed=%s' % (M.PROFILE, B.is_installed()),
        'routing heights=%d (body=%d)  interfaces=%s' % (
            len(M.PLANE_IDS), len(M.BODY_PLANES),
            {key: float(value) for key, value in M.INTERFACE_Z.items()}),
    ]


# ===========================================================================
# start point verification / fingerprint
# ===========================================================================
def _state_fingerprint(source):
    """Read a candidate start state (raises when a required artefact is absent)."""
    source = Path(source)
    routes_path = source / 'routes_l3d.json'
    assignment_path = source / 'assignment_1024.csv'
    missing = [str(path) for path in (routes_path, assignment_path)
               if not path.exists()]
    if missing:
        raise SystemExit(_blocked(
            'G3 best_valid is not ready: missing %s\n'
            '         run the 20H G1/G2/G3 stage (07_g123) first: %s'
            % (', '.join(missing), source)))
    payload = _read_json(routes_path)
    routes = list(payload.get('routes') or [])
    rows = _read_csv(assignment_path)
    manual = [row for row in rows
              if str(row.get('manual_group') or '').strip()]
    crossings = _artifact_crossings(source)
    return dict(
        dir=str(source), payload=payload, routes=routes, rows=rows,
        routes_sha256=_sha256(routes_path),
        assignment_sha256=_sha256(assignment_path),
        crossings=crossings,
        route_count=len(routes),
        assignment_rows=len(rows),
        manual_route_count=len(manual),
        payload_routed=int(payload.get('routed') or len(routes)),
        payload_failed=int(payload.get('failed') or 0),
        layer_planes_path=(source / 'layer_planes.json'),
    )


def _artifact_crossings(start_dir):
    """Crossing total from the start artefacts (``None`` when not recorded)."""
    for name in ('crossing_stats.json', 'summary.json', 'START.json'):
        path = Path(start_dir) / name
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        totals = payload.get('totals') or payload
        value = totals.get('crossings')
        if value is None:
            value = payload.get('crossings')
        if value is not None:
            return int(value)
    return None


def _layer_planes_table(path):
    """Read + check a ``layer_planes.json`` table against the 20H model."""
    payload = _read_json(path)
    planes = payload.get('planes') or []
    plane_ids = [int(plane.get('plane_id')) for plane in planes]
    z_values = [round(float(plane.get('z_mm')), 9) for plane in planes]
    model_ids = [int(pid) for pid in M.PLANE_IDS]
    model_z = [round(float(M.plane_z(pid)), 9) for pid in M.PLANE_IDS]
    return dict(
        path=str(path),
        plane_count=int(payload.get('plane_count') or len(planes)),
        height_count=int(payload.get('height_count') or len(set(z_values))),
        profile=payload.get('profile'),
        plane_ids_match=(sorted(plane_ids) == sorted(model_ids)),
        heights_match=(sorted(z_values) == sorted(model_z)),
        plane_ids=plane_ids,
    )


def _recount_state(fingerprint, log=None):
    """Build the true ``RouteWorld`` of the start state (exact crossing recount)."""
    from ..xyzrouter import route_builder as RB
    from ..xyzrouter import world_adapter as WA
    rows = RB.normalized_rows(fingerprint['rows'], stack=M.layer_stack())
    state = WA.RouteWorld(fingerprint['routes'], rows, log=log)
    return state


def _read_validation(start_dir, routes_sha256):
    start_dir = Path(start_dir)
    for candidate in (start_dir / 'validation' / 'validation.json',
                      start_dir / 'validation.json'):
        if not candidate.exists():
            continue
        payload = _read_json(candidate)
        counts = payload.get('counts') or {}
        routes_file_sha = payload.get('routes_file_sha256')
        return dict(
            path=str(candidate),
            validation_pass=payload.get('validation_pass'),
            violation_count=int(payload.get('violation_count') or 0),
            routes_file_sha256=routes_file_sha,
            matches_start=(routes_file_sha == routes_sha256),
            manual_route_count=counts.get('manual_route_count'),
            routed=counts.get('routed'),
            failed=counts.get('failed'),
            crossings=counts.get('same_plane_crossings'),
        )
    return None


def _bind_paths_to_start(source, fingerprint):
    """Import ``g4.paths``, declaring a custom start when the default is absent."""
    default = _start_dir_default()
    try:
        return g4_paths(required=True)
    except SystemExit:
        if Path(source).resolve() == Path(default).resolve():
            raise
        if fingerprint['crossings'] is None:
            raise SystemExit(_blocked(
                'custom --start-dir %s has no crossing_stats.json; the 20H G4 '
                'start fingerprint cannot be declared' % source))
        _warn('the configured 20H G3 start is absent; declaring the custom '
              'start %s as the common start for this process' % source)
        os.environ['COLDSTART20_START_SHA'] = str(fingerprint['routes_sha256'])
        os.environ['COLDSTART20_START_CROSSINGS'] = str(int(
            fingerprint['crossings']))
        _clear_g4_paths_cache()
        return g4_paths(required=True)


def _copy_start(source, dest, fingerprint, log=_log):
    """Freeze the verified start into ``08_g4/00_start_g3/`` (idempotent)."""
    source = Path(source)
    dest = Path(dest)
    if dest.resolve() == source.resolve():
        raise SystemExit(_blocked('start copy destination equals source: %s'
                                  % dest))
    if dest.exists():
        existing = dest / 'routes_l3d.json'
        if existing.exists() and _sha256(existing) == fingerprint['routes_sha256']:
            log('start copy already up to date: %s' % _rel(dest))
        else:
            if dest.parent.resolve() != G4_ROOT.resolve():
                raise SystemExit(_blocked(
                    'refusing to delete an unexpected directory: %s' % dest))
            log('refreshing stale start copy %s' % _rel(dest))
            shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    copied = {}
    for name in START_FILES:
        src = source / name
        if not src.exists():
            continue
        target = dest / name
        shutil.copy2(src, target)
        copied[name] = _sha256(target)
    validation_dir = source / 'validation'
    if validation_dir.is_dir():
        shutil.copytree(validation_dir, dest / 'validation', dirs_exist_ok=True)
        copied['validation/validation.json'] = _sha256(
            dest / 'validation' / 'validation.json')
    layer_planes = dest / 'layer_planes.json'
    generated = False
    if not layer_planes.exists():
        assigned = {}
        for row in fingerprint['rows']:
            layer = int(float(row['target_layer']))
            assigned[layer] = assigned.get(layer, 0) + 1
        _write_json(layer_planes, M.layer_planes_payload(assigned=assigned))
        copied['layer_planes.json'] = _sha256(layer_planes)
        generated = True
        log('generated 20H layer_planes.json in the start copy (source had none)')
    _write_json(dest / 'COPY.json', dict(
        schema='coldstart20_g4_start_copy_v1',
        profile=M.PROFILE,
        source_dir=str(source),
        source_dir_rel=_rel(source),
        routes_sha256=fingerprint['routes_sha256'],
        assignment_sha256=fingerprint['assignment_sha256'],
        copied_at=_now(),
        files=copied,
        layer_planes_generated=generated))
    return dict(dir=str(dest), dir_rel=_rel(dest), files=copied,
                layer_planes_generated=generated)


def _start_payload(source, fingerprint, state, profile_checks,
                   layer_planes, validation, copy_info, authority):
    claimed = fingerprint['crossings']
    return dict(
        schema='coldstart20_g4_start_v1',
        generated_at=_now(),
        profile=M.PROFILE,
        experiment=M.EXPERIMENT_NAME,
        model=M.MODEL_NAME,
        model_module='four_side_1024.fanout1024.coldstart20.model20',
        start_profile=profile_checks,
        g4_root=_rel(G4_ROOT),
        start_dir=_rel(_start_dir_default()),
        source_dir=_rel(source),
        source_dir_abs=str(source),
        copied_dir=(copy_info or {}).get('dir_rel'),
        routes_sha256=fingerprint['routes_sha256'],
        assignment_sha256=fingerprint['assignment_sha256'],
        crossings=int(state.total) if state is not None else claimed,
        crossing_pairs=(int(state.pairs) if state is not None else None),
        crossings_source=('recounted_true_3d_route_world'
                          if state is not None else 'start_artefact'),
        artefact_crossings=claimed,
        plane_count=len(M.PLANE_IDS),
        body_plane_count=len(M.BODY_PLANES),
        plane_ids=[int(pid) for pid in M.PLANE_IDS],
        interface_z_mm={key: float(value)
                        for key, value in M.INTERFACE_Z.items()},
        removed_plane_ids=[19],
        route_count=fingerprint['route_count'],
        assignment_rows=fingerprint['assignment_rows'],
        manual_route_count=fingerprint['manual_route_count'],
        payload_routed=fingerprint['payload_routed'],
        payload_failed=fingerprint['payload_failed'],
        layer_planes=layer_planes,
        validation=validation,
        authority=authority,
        seed=DEFAULT_SEED,
        budget_contract=dict(
            default=dict(DEFAULT_BUDGET),
            arms={arm: dict(budget) for arm, budget in ARM_BUDGETS.items()},
            counted_mode=dict(d56_candidate_evals=COUNTED_D56_BUDGET,
                              route_3d_checks_guard=COUNTED_CHECKS_GUARD,
                              applies_to=['G4c_frozen', 'G4c_free', 'G4d'])),
        copy=(copy_info or {}),
        checks=dict(
            profile_20h=(len(M.PLANE_IDS) == 20),
            plane_19_absent=(19 not in set(int(pid) for pid in M.PLANE_IDS)),
            route_count_1024=(fingerprint['route_count'] == 1024),
            assignment_rows_1024=(fingerprint['assignment_rows'] == 1024),
            manual_route_count_368=(fingerprint['manual_route_count'] == 368),
            zero_failed=(fingerprint['payload_failed'] == 0),
            start_profile_guard=True,
            recount_matches_artefact=(state is None or claimed is None
                                      or int(state.total) == int(claimed)),
            layer_planes_is_20h=(layer_planes is None
                                 or (layer_planes['plane_ids_match']
                                     and layer_planes['heights_match'])),
            validation_pass=(validation is None
                             or bool(validation.get('validation_pass'))
                             and bool(validation.get('matches_start'))),
        ),
    )


# ===========================================================================
# authority / preflight
# ===========================================================================
def _resolve_authority(explicit=None):
    """Identity/port/manual-U authority used by the frozen validator."""
    GP = g4_paths()
    candidates = []
    if explicit:
        candidates.append((Path(explicit), 'explicit --baseline-dir'))
    if GP is not None:
        candidates.append((Path(GP.AUTHORITY_DIR), 'g4.paths.AUTHORITY_DIR'))
    candidates.extend([
        (Path(P20.XYZ_RUN) / 'baseline_authoritative',
         '20H G3 run baseline_authoritative'),
        (ROOT / 'experiments' / 'xyz_joint_g123_1024' /
         'baseline_authoritative',
         'frozen archive baseline_authoritative (18-layer authority copy)'),
        (ROOT / 'outputs' / 'manual_c4_new_connectivity' /
         'XYZ_JOINT_G123_1024' / 'baseline_authoritative',
         'frozen run baseline_authoritative'),
    ])
    for path, source in candidates:
        if (path / 'routes_l3d.json').exists():
            return path, source
    return (Path(explicit) if explicit else None), 'missing'


def _preflight(context, require_start=True):
    """Hard prerequisites for a real (non dry-run) arm / chain execution."""
    B.assert_20_height_profile(context)
    GP = g4_paths(required=True)
    start_payload = _read_json(G4_ROOT / 'START.json', default=None)
    if require_start:
        if not isinstance(start_payload, dict):
            raise SystemExit(_blocked(
                'no 20H G4 start fingerprint: run\n'
                '         python -m %s start\n'
                '         first (writes %s)' % (DRIVER_MODULE,
                                            _rel(G4_ROOT / 'START.json'))))
        if start_payload.get('profile') != M.PROFILE:
            raise SystemExit(_blocked(
                'START.json profile=%r does not match the installed profile %r'
                % (start_payload.get('profile'), M.PROFILE)))
        if int(start_payload.get('plane_count') or 0) != len(M.PLANE_IDS):
            raise SystemExit(_blocked(
                'START.json plane_count=%r does not match the %d-plane model'
                % (start_payload.get('plane_count'), len(M.PLANE_IDS))))
        current_sha = GP.START_ROUTES_SHA256
        if current_sha and current_sha != start_payload.get('routes_sha256'):
            raise SystemExit(_blocked(
                'START.json fingerprint is stale: the 20H G3 best_valid now has '
                'routes sha256=%s but START.json records %s\n'
                '         rerun `%s start`' % (
                    current_sha, start_payload.get('routes_sha256'),
                    DRIVER_MODULE)))
        if GP.START_CROSSINGS is not None and \
                int(GP.START_CROSSINGS) != int(start_payload.get('crossings')):
            raise SystemExit(_blocked(
                'START.json crossings=%r != current G3 crossing total %r; '
                'rerun `%s start`' % (
                    start_payload.get('crossings'), GP.START_CROSSINGS,
                    DRIVER_MODULE)))
    authority, authority_source = _resolve_authority(None)
    if authority is None:
        raise SystemExit(_blocked(
            'no identity/port authority baseline found (validator needs it). '
            'Expected the 20H run baseline_authoritative or the frozen archive '
            'copy; pass --baseline-dir explicitly where supported.'))
    return dict(gp=GP, start=start_payload, authority=str(authority),
                authority_source=authority_source,
                start_dir=str(GP.START_DIR))


def _launch_record_path(key):
    return G4_ROOT / DRIVER_STATE_DIR / ('launch_%s.json' % key)


def _run_subprocess(argv, meta):
    """Run one arm subprocess with inherited stdio; persist the launch record."""
    record_path = _launch_record_path(meta['key'])
    _write_json(record_path, dict(meta, state='launched', argv=argv,
                                  started_at=_now()))
    _log('launch %s: %s' % (meta['key'], ' '.join(argv)))
    started = time.time()
    completed = subprocess.run(argv, cwd=str(ROOT))
    elapsed = round(time.time() - started, 2)
    record = dict(meta, state='finished', argv=argv, exit_code=int(
        completed.returncode), elapsed_seconds=elapsed,
        finished_at=_now(), best_valid=None)
    best = Path(meta['out_dir']) / 'best_valid' / 'routes_l3d.json'
    if best.exists():
        record['best_valid'] = dict(
            path=_rel(best), sha256=_sha256(best),
            artifacts=sorted(path.name for path in best.parent.iterdir()
                             if path.is_file()))
    _write_json(record_path, record)
    _log('done %s exit=%s elapsed=%.1fs record=%s' % (
        meta['key'], completed.returncode, elapsed, _rel(record_path)))
    if best.exists():
        _log('%s best_valid sha256=%s' % (meta['key'],
                                          record['best_valid']['sha256']))
    else:
        _warn('%s produced no best_valid/routes_l3d.json' % meta['key'])
    return int(completed.returncode)


def _validate_arm(arm_key, extra_args='', dry_run=False):
    """Fresh 20H-profile independent validation of one arm's best_valid."""
    spec = ARM_SPECS[arm_key]
    arm_dir = _arm_dir(spec['dir_key'])
    best_dir = arm_dir / 'best_valid'
    run_dir = best_dir if (best_dir / 'routes_l3d.json').exists() else arm_dir
    out_dir = arm_dir / 'validation'
    argv = [_python(), '-m', DRIVER_MODULE, 'validate',
            '--run-dir', str(run_dir), '--out-dir', str(out_dir),
            '--manual-policy', 'fully_optimizable']
    if extra_args:
        argv.extend(_split_extra(extra_args))
    _log('validate %s: %s' % (spec['arm'], ' '.join(argv)))
    if dry_run:
        return 0
    return int(subprocess.run(argv, cwd=str(ROOT)).returncode)


# ===========================================================================
# sub-command: start
# ===========================================================================
def command_start(args):
    source = Path(args.start_dir) if args.start_dir else _start_dir_default()
    copy_dir = G4_ROOT / START_COPY_NAME
    _log('start: profile=%s installed=%s' % (M.PROFILE, B.is_installed()))
    for line in _profile_lines():
        _log('  ' + line)
    _log('start source: %s' % _rel(source))
    _log('start copy  : %s' % _rel(copy_dir))
    _log('fingerprint : %s' % _rel(G4_ROOT / 'START.json'))
    if args.dry_run:
        _log('dry-run: would verify -> copy -> write START.json; nothing done')
        _log('  verify: 1024 routes / 368 manual-U / 0 failed, routes+assignment '
             'sha256, crossing_stats total, true-3D recount, 20H profile guard '
             '(all flat heights + assignment layers in the 20H model), '
             'layer_planes.json 20-plane table, validator report')
        return 0
    B.assert_20_height_profile('start')
    fingerprint = _state_fingerprint(source)
    _log('source: routes=%d assignment_rows=%d manual=%d failed=%d '
         'crossings(artefact)=%s' % (
             fingerprint['route_count'], fingerprint['assignment_rows'],
             fingerprint['manual_route_count'], fingerprint['payload_failed'],
             fingerprint['crossings']))
    problems = []
    if fingerprint['route_count'] != 1024:
        problems.append('route payload has %d routes (expected 1024)'
                        % fingerprint['route_count'])
    if fingerprint['assignment_rows'] != 1024:
        problems.append('assignment has %d rows (expected 1024)'
                        % fingerprint['assignment_rows'])
    if fingerprint['manual_route_count'] != 368:
        problems.append('assignment has %d manual-U rows (expected 368)'
                        % fingerprint['manual_route_count'])
    if fingerprint['payload_failed']:
        problems.append('route payload reports %d failed routes'
                        % fingerprint['payload_failed'])
    if fingerprint['crossings'] is None:
        problems.append('no crossing total in crossing_stats.json/summary.json')
    if problems:
        return _blocked('G3 best_valid failed verification: ' + '; '.join(
            problems))
    GP = _bind_paths_to_start(source, fingerprint)
    baseline = GP.load_start(source)      # 20H profile validity guard (hard)
    _log('20H start profile guard passed: %s' % json.dumps(
        {key: baseline['profile'][key] for key in
         ('profile', 'plane_count', 'body_plane_count', 'route_count',
          'manual_route_count')}, ensure_ascii=False))
    state = None
    if not args.no_recount:
        _log('recounting the start state in the true 3D RouteWorld (exact '
             'crossing total) ...')
        state = _recount_state(fingerprint, log=lambda message: None)
        _log('recount: routes=%d crossings=%d pairs=%d (%.2fs)' % (
            len(state.routes), state.total, state.pairs, state.build_time))
        if int(state.total) != int(fingerprint['crossings']):
            return _blocked(
                'crossing recount mismatch: crossing_stats=%d but the loaded '
                'state has %d (the G3 artefact is stale or not the same state)'
                % (fingerprint['crossings'], int(state.total)))
    else:
        _warn('--no-recount: the crossing total is the artefact value, not the '
              'true-3D recount')
    layer_planes = None
    if fingerprint['layer_planes_path'].exists():
        layer_planes = _layer_planes_table(fingerprint['layer_planes_path'])
        if not (layer_planes['plane_ids_match']
                and layer_planes['heights_match']):
            return _blocked(
                'G3 layer_planes.json is not the 20H model table: profile=%r '
                'plane_count=%r planes_match=%r heights_match=%r'
                % (layer_planes.get('profile'), layer_planes['plane_count'],
                   layer_planes['plane_ids_match'],
                   layer_planes['heights_match']))
    else:
        _warn('G3 best_valid has no layer_planes.json; the start copy gets a '
              'generated 20H table')
    validation = _read_validation(source, fingerprint['routes_sha256'])
    if validation is None:
        if args.require_validation:
            return _blocked('G3 best_valid has no independent validator report '
                            'and --require-validation was given')
        _warn('G3 best_valid has no independent validator report')
    else:
        if not validation.get('validation_pass'):
            return _blocked('G3 best_valid validator report says '
                            'validation_pass=%r' % validation.get(
                                'validation_pass'))
        if not validation.get('matches_start'):
            return _blocked(
                'G3 best_valid validator report belongs to another state '
                '(validation routes sha256=%r != %r)'
                % (validation.get('routes_file_sha256'),
                   fingerprint['routes_sha256']))
    authority, authority_source = _resolve_authority(None)
    if authority is None:
        _warn('no identity/port authority baseline found; arm validation will '
              'need one')
    copy_info = None
    if not args.no_copy:
        copy_info = _copy_start(source, copy_dir, fingerprint)
    payload = _start_payload(
        source, fingerprint, state, baseline['profile'],
        layer_planes, validation, copy_info,
        dict(dir=(str(authority) if authority else None),
             dir_rel=(_rel(authority) if authority else None),
             resolved_by=authority_source,
             present=bool(authority and (authority / 'routes_l3d.json').exists())))
    _write_json(G4_ROOT / 'START.json', payload)
    _write_json(G4_ROOT / ARM_DIR_NAMES['audit'] / 'profile.json',
                B.profile_payload())
    _clear_g4_paths_cache()
    _log('wrote %s' % _rel(G4_ROOT / 'START.json'))
    _log('fingerprint: profile=%s routes_sha256=%s crossings=%d '
         'assignment_sha256=%s plane_count=%d manual_route_count=%d' % (
             payload['profile'], payload['routes_sha256'],
             int(payload['crossings']), payload['assignment_sha256'],
             payload['plane_count'], payload['manual_route_count']))
    return 0


# ===========================================================================
# sub-command: one arm
# ===========================================================================
def _arm_inner_argv(key, args):
    spec = ARM_SPECS[key]
    seconds = float(args.seconds) if args.seconds is not None else \
        float(_arm_budget(spec['dir_key'])['wall_seconds'])
    arm_dir = _arm_dir(spec['dir_key'], args.out_dir)
    start_override = getattr(args, 'start_dir', None)
    inner = []
    if spec['arm_flag']:
        inner.extend(['--arm', spec['arm']])
    inner.extend([spec['time_flag'], _num(seconds)])
    inner.extend(['--seed', str(int(args.seed))])
    # C0's legacy runner has no --resume/--tag flags (it always resumes from its
    # own crash-safe best_valid; --no-resume goes through --extra-args)
    if args.resume and spec.get('resume_flag', True):
        inner.append('--resume')
    start = Path(start_override) if start_override else _start_dir_default()
    if spec['start_flag']:
        inner.extend([spec['start_flag'], str(start)])
    elif start_override and Path(start_override).resolve() != \
            Path(_start_dir_default()).resolve():
        raise SystemExit(_blocked(
            'the %s runner has no --start-dir flag: it always starts from the '
            'configured G3 optimum (%s).  Chain-style starts are not supported '
            'for this arm (same contract as the frozen fair_runner).'
            % (spec['arm'], _start_dir_default())))
    inner.extend([spec['out_flag'], str(arm_dir)])
    if args.tag and spec.get('tag_flag', True):
        inner.extend(['--tag', str(args.tag)])
    if spec['counted']:
        _counted = bool(getattr(args, 'counted', False))
        _d56 = getattr(args, 'counted_d56_budget', None)
        _guard = getattr(args, 'counted_checks_guard', None)
        d56 = (_d56 if _d56 is not None
               else (COUNTED_D56_BUDGET if _counted else None))
        guard = (_guard if _guard is not None
                 else (COUNTED_CHECKS_GUARD if _counted else None))
        if d56 is not None:
            inner.extend(['--counted-d56-budget', str(int(d56))])
        if guard is not None:
            inner.extend(['--counted-checks-guard', str(int(guard))])
    inner.extend(_split_extra(args.extra_args))
    return spec, inner, arm_dir, seconds


def command_arm(key, args):
    spec = ARM_SPECS[key]
    if args.dry_run:
        if g4_paths() is None:
            _warn('g4.paths cannot import yet (the 20H G3 best_valid is '
                  'missing): using the driver plan mirror of ARM_DIRS / '
                  'budgets; a real run will be blocked until G3 exists')
        spec, inner, arm_dir, seconds = _arm_inner_argv(key, args)
        start = Path(args.start_dir) if getattr(args, 'start_dir', None) \
            else _start_dir_default()
        _log('arm=%s  %s' % (spec['arm'], spec['description']))
        _log('  out-dir : %s' % _rel(arm_dir))
        _log('  start   : %s' % _rel(start))
        _log('  budget  : route_3d_checks=%d d56_candidate_evals=%d '
             'wall_seconds=%s seed=%d' % (
                 int(DEFAULT_BUDGET['route_3d_checks']),
                 int(DEFAULT_BUDGET['d56_candidate_evals']),
                 _num(seconds), int(args.seed)))
        bare = [_python(), '-m', spec['module']] + inner
        _log('  bare argv (NOT profile-safe, shown for reference): %s'
             % ' '.join(bare))
        wrapped = [_python(), '-m', DRIVER_MODULE, '_run', '--module',
                   spec['module'], '--'] + inner
        _log('  driver argv: %s' % ' '.join(wrapped))
        _log('  dry-run: nothing executed')
        return 0
    preflight = _preflight('arm:%s' % key)
    spec, inner, arm_dir, seconds = _arm_inner_argv(key, args)
    arm_dir.mkdir(parents=True, exist_ok=True)
    argv = [_python(), '-m', DRIVER_MODULE, '_run', '--module',
            spec['module'], '--'] + inner
    meta = dict(
        schema='coldstart20_g4_launch_v1', key=key, arm=spec['arm'],
        profile=M.PROFILE, g4_root=_rel(G4_ROOT),
        start_dir=str(preflight['start_dir']),
        start_routes_sha256=preflight['start'].get('routes_sha256'),
        start_crossings=preflight['start'].get('crossings'),
        authority_dir=preflight['authority'],
        authority_source=preflight['authority_source'],
        out_dir=str(arm_dir), seconds=seconds, seed=int(args.seed),
        declared_budget=dict(DEFAULT_BUDGET),
        arm_budget=dict(_arm_budget(spec['dir_key'])),
        counted_d56_budget=getattr(args, 'counted_d56_budget', None),
        counted_checks_guard=getattr(args, 'counted_checks_guard', None),
        tag=args.tag, resume=bool(args.resume), extra_args=args.extra_args)
    return _run_subprocess(argv, meta)


# ===========================================================================
# sub-command: validate
# ===========================================================================
def command_validate(args):
    B.assert_20_height_profile('validate')
    if args.arm:
        key = str(args.arm)
        if key not in ARM_SPECS:
            return _blocked('unknown --arm %r (choose from %s)'
                            % (key, ', '.join(ARM_SPECS)))
        spec = ARM_SPECS[key]
        arm_dir = _arm_dir(spec['dir_key'])
        run_dir = Path(args.run_dir) if args.run_dir else (
            arm_dir / 'best_valid')
        out_dir = Path(args.out_dir) if args.out_dir else (
            arm_dir / 'validation')
    else:
        if not args.run_dir:
            return _blocked('validate needs --run-dir or --arm')
        run_dir = Path(args.run_dir)
        out_dir = Path(args.out_dir) if args.out_dir else (
            run_dir / 'validation')
    if not (run_dir / 'routes_l3d.json').exists():
        if not args.dry_run:
            return _blocked('no routes_l3d.json in %s' % run_dir)
        _warn('run dir not present yet (dry-run plan only): %s' % run_dir)
    authority, authority_source = _resolve_authority(args.baseline_dir)
    if authority is None:
        if not args.dry_run:
            return _blocked('no identity/port authority baseline found; pass '
                            '--baseline-dir')
        _warn('no identity/port authority baseline found yet; a real '
              'validation would need one')
        authority = Path('<authority baseline>')
    elif args.baseline_dir is None:
        _log('authority: %s (%s)' % (_rel(authority), authority_source))
        if '20H G3 run' not in authority_source:
            _warn('using a frozen fallback authority: %s' % authority_source)
    stage_note = None
    validator_run_dir = run_dir
    if (run_dir / 'routes_l3d.json').exists() and \
            not (run_dir / 'layer_planes.json').exists():
        stage = Path(out_dir) / '_staged_run_with_model'
        stage.mkdir(parents=True, exist_ok=True)
        for name in ('routes_l3d.json', 'assignment_1024.csv',
                     'crossing_stats.json'):
            if (run_dir / name).exists():
                shutil.copy2(run_dir / name, stage / name)
        rows = _read_csv(run_dir / 'assignment_1024.csv')
        assigned = {}
        for row in rows:
            layer = int(float(row['target_layer']))
            assigned[layer] = assigned.get(layer, 0) + 1
        _write_json(stage / 'layer_planes.json',
                    M.layer_planes_payload(assigned=assigned))
        validator_run_dir = stage
        stage_note = _rel(stage)
        _warn('run dir has no layer_planes.json: validating a staged copy with '
              'the generated 20H table (%s)' % stage_note)
    argv = ['--run-dir', str(validator_run_dir),
            '--out-dir', str(out_dir),
            '--manual-policy', str(args.manual_policy),
            '--baseline-dir', str(authority)]
    for flag in _split_extra(args.extra_args):
        if flag in ('--run-dir', '--out-dir', '--manual-policy',
                    '--baseline-dir'):
            continue
        argv.append(flag)
    _log('validator argv: python -m %s %s' % (VALIDATOR_MODULE,
                                              ' '.join(argv)))
    if args.dry_run:
        _log('dry-run: nothing executed')
        return 0
    from ..xyzrouter import validate_xyz as VX
    code = int(VX.main(argv) or 0)
    report_path = Path(out_dir) / 'validation.json'
    report = _read_json(report_path, default=None)
    if isinstance(report, dict):
        counts = report.get('counts') or {}
        _log('validation: pass=%s violations=%s routed=%s failed=%s '
             'manual=%s crossings=%s sha=%s' % (
                 report.get('validation_pass'),
                 report.get('violation_count'), counts.get('routed'),
                 counts.get('failed'), counts.get('manual_route_count'),
                 counts.get('same_plane_crossings'),
                 str(report.get('routes_file_sha256'))[:16]))
    return code


# ===========================================================================
# sub-command: chain
# ===========================================================================
def _chain_plan(args):
    """Human-readable plan of the 20H progressive chain (no imports needed)."""
    chain_root = G4_ROOT / ARM_DIR_NAMES['chain']
    lines = [
        'link 0  00_link_G3_start      copy of the verified 20H G3 best_valid',
        'link 1  01_link_best_G4ab     adopt best independently-validated '
        'G4a / G4b best_valid (requires both arms validated)',
        'link 2  02_link_G4c           run %s from 01_link_best_G4ab '
        '(budget %ss)' % (args.chain_g4c_arm, _num(args.chain_seconds_g4c)),
        'link 2b 02b_link_best_G4c     adopt the best validated %s '
        'best_valid (0 s search)' % args.chain_g4c_arm,
        'link 4  03_link_G4d           run G4d from 02b_link_best_G4c '
        '(budget %ss)' % _num(args.chain_seconds_g4d),
    ]
    commands = []
    for index, arm, seconds in ((2, args.chain_g4c_arm,
                                 args.chain_seconds_g4c),
                                (4, 'G4d', args.chain_seconds_g4d)):
        link_dir = chain_root / {2: '02_link_G4c',
                                 4: '03_link_G4d'}[index]
        inner = ['--arm', arm, '--seconds', _num(seconds),
                 '--seed', str(int(args.seed)),
                 '--start-dir', '<previous link checkpoint>',
                 '--out-dir', str(link_dir), '--tag', 'chain']
        commands.append(' '.join([_python(), '-m', DRIVER_MODULE, '_run',
                                  '--module',
                                  'four_side_1024.fanout1024.xyzrouter.g4.'
                                  'run_g4_engine', '--'] + inner))
    return lines, commands, chain_root


def command_chain(args):
    lines, commands, chain_root = _chain_plan(args)
    _log('progressive chain root: %s' % _rel(chain_root))
    for line in lines:
        _log('  ' + line)
    for command in commands:
        _log('  run: %s' % command)
    if args.dry_run:
        _log('dry-run: would build the chain records with '
             'g4.fair_runner.build_chain and (with --run-chain) execute the '
             'pending links above; nothing executed')
        return 0
    _preflight('chain')
    from ..xyzrouter.g4 import fair_runner as FR
    fr_args = FR.parse_args([])
    fr_args.seed = int(args.seed)
    fr_args.start_dir = str(Path(args.start_dir) if args.start_dir
                            else _start_dir_default())
    fr_args.python = _python()
    fr_args.chain_g4c_arm = args.chain_g4c_arm
    fr_args.chain_seconds_g4c = float(args.chain_seconds_g4c)
    fr_args.chain_seconds_g4d = float(args.chain_seconds_g4d)
    fr_args.extra_args = ''
    fr_args.timeout_slack = 900.0
    chain_root.mkdir(parents=True, exist_ok=True)
    log_path = chain_root / 'run_g4_chain.log'
    log_handle = log_path.open('a', encoding='utf-8', buffering=1)

    def log(message):
        line = '[%s] %s' % (_now(), message)
        print(line, flush=True)
        log_handle.write(line + '\n')

    try:
        payload = FR.build_chain(fr_args, log=log)
        links = payload['links']
        log('[chain] built %d links: %s' % (
            len(links), [(link['index'], link['status']) for link in links]))
        if not args.run_chain:
            log('[chain] --run-chain not given: chain records only (pending '
                'links were not executed)')
            return 0
        runnable = ((2, args.chain_g4c_arm, args.chain_seconds_g4c),
                    (4, 'G4d', args.chain_seconds_g4d))
        for index, arm, seconds in runnable:
            if index >= len(links):
                log('[chain] link %d missing from the chain record; stop'
                    % index)
                return 1
            link = links[index]
            if link.get('status') != 'pending':
                log('[chain] link %d already %s, skip'
                    % (index, link.get('status')))
                continue
            previous = links[index - 1]
            if previous.get('status') not in ('ok', 'unvalidated') or \
                    previous.get('end_crossings') is None:
                log('[chain] link %d blocked: previous link %d status=%s'
                    % (index, index - 1, previous.get('status')))
                return 1
            start_dir = FR._chain_checkpoint_dir(previous)
            if start_dir is None:
                log('[chain] link %d blocked: previous checkpoint has no '
                    'routes_l3d.json' % index)
                return 1
            link_dir = Path(link['checkpoint_dir'])
            inner = ['--arm', arm, '--seconds', _num(seconds),
                     '--seed', str(int(args.seed)),
                     '--start-dir', str(start_dir),
                     '--out-dir', str(link_dir), '--tag', 'chain']
            argv = [_python(), '-m', DRIVER_MODULE, '_run', '--module',
                    'four_side_1024.fanout1024.xyzrouter.g4.run_g4_engine',
                    '--'] + inner
            log('[chain] link %d arm=%s start=%s out=%s seconds=%s' % (
                index, arm, start_dir, link_dir, _num(seconds)))
            log('[chain] link %d argv=%s' % (index, ' '.join(argv)))
            code = int(subprocess.run(argv, cwd=str(ROOT)).returncode)
            log('[chain] link %d exit=%s' % (index, code))
            if code != 0:
                log('[chain] link %d failed; chain stopped' % index)
                FR.build_chain(fr_args, log=log)
                return code
            checkpoint = None
            for candidate in (link_dir / 'best_valid', link_dir):
                if (candidate / 'routes_l3d.json').exists():
                    checkpoint = candidate
                    break
            if checkpoint is None:
                log('[chain] link %d produced no routes_l3d.json; chain stopped'
                    % index)
                FR.build_chain(fr_args, log=log)
                return 1
            log('[chain] link %d validating %s' % (index, checkpoint))
            code = int(subprocess.run(
                [_python(), '-m', DRIVER_MODULE, 'validate',
                 '--run-dir', str(checkpoint),
                 '--out-dir', str(link_dir / 'validation'),
                 '--manual-policy', 'fully_optimizable'],
                cwd=str(ROOT)).returncode)
            log('[chain] link %d validation exit=%s' % (index, code))
            payload = FR.build_chain(fr_args, log=log)
            links = payload['links']
        log('[chain] done: %s' % json.dumps(
            {link['index']: link.get('status') for link in links},
            ensure_ascii=False))
        return 0
    finally:
        log_handle.close()


# ===========================================================================
# sub-command: all
# ===========================================================================
def _default_attrs():
    return dict(
        dry_run=False, seconds=None, counted=False, seed=DEFAULT_SEED,
        out_dir=None, start_dir=None, tag=DEFAULT_TAG, resume=False,
        extra_args='', counted_d56_budget=None, counted_checks_guard=None,
        arm=None, run_dir=None, manual_policy='fully_optimizable',
        baseline_dir=None, require_validation=False, no_copy=False,
        no_recount=False, chain_g4c_arm='G4c_free',
        chain_seconds_g4c=700.0, chain_seconds_g4d=1200.0,
        run_chain=False, skip_start=False, skip_chain=False,
        arms=','.join(ARM_ORDER))


def _ns(**overrides):
    namespace = argparse.Namespace(**_default_attrs())
    for key, value in overrides.items():
        setattr(namespace, key, value)
    return namespace


def command_all(args):
    arms = [name.strip() for name in str(args.arms).split(',')
            if name.strip()]
    unknown = [name for name in arms if name not in ARM_SPECS]
    if unknown:
        return _blocked('unknown arm(s) %s (choose from %s)'
                        % (unknown, ', '.join(ARM_ORDER)))
    steps = []
    if not args.skip_start:
        steps.append(('start', _ns(dry_run=args.dry_run,
                                   start_dir=args.start_dir,
                                   require_validation=args.require_validation,
                                   no_copy=args.no_copy,
                                   no_recount=args.no_recount)))
    for key in arms:
        steps.append((key, _ns(
            dry_run=args.dry_run,
            seconds=(args.seconds if key == 'c0' else None),
            counted=bool(getattr(args, 'counted', False)),
            seed=args.seed, out_dir=None, start_dir=args.start_dir,
            tag=args.tag, resume=args.resume, extra_args=args.extra_args,
            counted_d56_budget=getattr(args, 'counted_d56_budget', None),
            counted_checks_guard=getattr(args, 'counted_checks_guard',
                                         None))))
    if not args.skip_chain:
        steps.append(('chain', _ns(
            dry_run=args.dry_run, seed=args.seed,
            start_dir=args.start_dir, run_chain=args.run_chain,
            chain_g4c_arm=args.chain_g4c_arm,
            chain_seconds_g4c=args.chain_seconds_g4c,
            chain_seconds_g4d=args.chain_seconds_g4d)))
    total_wall = sum(
        int(ARM_BUDGETS[ARM_SPECS[key]['dir_key']]['wall_seconds'])
        for key in arms)
    if not args.skip_chain:
        total_wall += int(args.chain_seconds_g4c) + int(
            args.chain_seconds_g4d)
    _log('all: arms=%s chain=%s total declared search wall=%ds (plus '
         'validator runs)' % (arms, not args.skip_chain, total_wall))
    for index, (key, step_args) in enumerate(steps, 1):
        _log('=' * 74)
        _log('[%d/%d] %s' % (index, len(steps), key))
        if key == 'start':
            code = command_start(step_args)
        elif key == 'chain':
            code = command_chain(step_args)
        else:
            code = command_arm(key, step_args)
            if not args.dry_run and code == 0:
                code = _validate_arm(key, extra_args='')
        if code != 0:
            _log('all: step %r failed with exit=%s; stopping' % (key, code))
            return int(code)
    _log('all: finished %d steps' % len(steps))
    return 0


# ===========================================================================
# internal: profile-first module launcher
# ===========================================================================
def command_run(args):
    """Import ``--module`` after the profile is installed and call ``main``."""
    B.assert_20_height_profile('run_g4._run')
    rest = [token for token in list(args.rest or []) if token != '--']
    _log('_run: profile=%s plane_count=%d module=%s' % (
        M.PROFILE, len(M.PLANE_IDS), args.module))
    module = importlib.import_module(str(args.module))
    main = getattr(module, 'main', None)
    if main is None:
        return _blocked('module %r has no main(argv)' % args.module)
    result = main(rest)
    return int(result) if isinstance(result, int) else 0


# ===========================================================================
# CLI
# ===========================================================================
def build_parser():
    parser = argparse.ArgumentParser(
        description='Bootstrap-first driver for the G4 arms on the 20-height '
                    'model (profile is installed on import; every arm runs in '
                    'a fresh profile-first process).')
    sub = parser.add_subparsers(dest='command', required=True)

    def add_dry(target):
        target.add_argument('--dry-run', action='store_true',
                            help='print the exact plan/argv; never execute')

    p_start = sub.add_parser('start', help='verify/copy the 20H G3 best_valid '
                                          'and write START.json')
    p_start.add_argument('--start-dir', default=None,
                         help='override the G3 best_valid source')
    p_start.add_argument('--no-copy', action='store_true',
                         help='do not freeze a copy under 08_g4/00_start_g3')
    p_start.add_argument('--no-recount', action='store_true',
                         help='skip the exact true-3D crossing recount')
    p_start.add_argument('--require-validation', action='store_true',
                         help='fail when the G3 best_valid has no validator '
                              'report')
    add_dry(p_start)

    for key in ARM_ORDER:
        spec = ARM_SPECS[key]
        p_arm = sub.add_parser(key, help=spec['description'])
        common = p_arm.add_argument_group('fair-comparison contract')
        common.add_argument('--seconds', type=float, default=None,
                            help='wall-clock search budget (default: declared '
                                 '%ss)' % ARM_BUDGETS[spec['dir_key']][
                                     'wall_seconds'])
        common.add_argument('--seed', type=int, default=DEFAULT_SEED)
        common.add_argument('--out-dir', default=None)
        common.add_argument('--start-dir', default=None,
                            help='start point override; only the runners that '
                                 'expose a start flag can honour it (G4a/G4b '
                                 'always start from the configured G3 optimum)')
        common.add_argument('--tag', default=DEFAULT_TAG)
        common.add_argument('--resume', action='store_true')
        common.add_argument('--extra-args', default='',
                            help='extra argv forwarded verbatim to the arm '
                                 'runner (e.g. "--quick --no-validate")')
        if spec['counted']:
            p_arm.add_argument('--counted', action='store_true',
                               help='equal-counted mode (%d d56 / %d checks)'
                                    % (COUNTED_D56_BUDGET,
                                       COUNTED_CHECKS_GUARD))
            p_arm.add_argument('--counted-d56-budget', type=int, default=None)
            p_arm.add_argument('--counted-checks-guard', type=int,
                               default=None)
        add_dry(p_arm)

    p_validate = sub.add_parser('validate', help='frozen independent validator '
                                                'under the 20H profile')
    p_validate.add_argument('--arm', default=None, choices=list(ARM_SPECS))
    p_validate.add_argument('--run-dir', default=None)
    p_validate.add_argument('--out-dir', default=None)
    p_validate.add_argument('--manual-policy', default='fully_optimizable',
                            choices=['frozen', 'height_only',
                                     'fully_optimizable'])
    p_validate.add_argument('--baseline-dir', default=None)
    p_validate.add_argument('--extra-args', default='',
                            help='extra validate_xyz flags (e.g. '
                                 '"--skip-synthetic")')
    add_dry(p_validate)

    p_chain = sub.add_parser('chain', help='20H progressive chain '
                                           '(fair_runner.build_chain + link '
                                           'runs)')
    p_chain.add_argument('--seed', type=int, default=DEFAULT_SEED)
    p_chain.add_argument('--start-dir', default=None)
    p_chain.add_argument('--chain-g4c-arm', default='G4c_free',
                         choices=['G4c_free', 'G4c_frozen'])
    p_chain.add_argument('--chain-seconds-g4c', type=float, default=700.0)
    p_chain.add_argument('--chain-seconds-g4d', type=float, default=1200.0)
    p_chain.add_argument('--run-chain', action='store_true',
                         help='actually execute the pending chain links')
    add_dry(p_chain)
    p_all = sub.add_parser('all', help='start + every arm + validation + chain')
    p_all.add_argument('--arms', default=','.join(ARM_ORDER))
    p_all.add_argument('--seconds', type=float, default=None,
                       help='C0 wall-clock override (other arms use declared)')
    p_all.add_argument('--seed', type=int, default=DEFAULT_SEED)
    p_all.add_argument('--start-dir', default=None)
    p_all.add_argument('--tag', default=DEFAULT_TAG)
    p_all.add_argument('--resume', action='store_true')
    p_all.add_argument('--extra-args', default='')
    p_all.add_argument('--counted', action='store_true')
    p_all.add_argument('--counted-d56-budget', type=int, default=None)
    p_all.add_argument('--counted-checks-guard', type=int, default=None)
    p_all.add_argument('--skip-start', action='store_true')
    p_all.add_argument('--skip-chain', action='store_true')
    p_all.add_argument('--run-chain', action='store_true')
    p_all.add_argument('--chain-g4c-arm', default='G4c_free',
                       choices=['G4c_free', 'G4c_frozen'])
    p_all.add_argument('--chain-seconds-g4c', type=float, default=700.0)
    p_all.add_argument('--chain-seconds-g4d', type=float, default=1200.0)
    p_all.add_argument('--no-copy', action='store_true')
    p_all.add_argument('--no-recount', action='store_true')
    p_all.add_argument('--require-validation', action='store_true')
    add_dry(p_all)
    return parser


def _parse_internal(tokens):
    """Parse ``_run --module <module> -- <module argv...>`` (hidden command)."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--module', required=True)
    namespace, rest = parser.parse_known_args(list(tokens))
    return namespace.module, [token for token in rest if token != '--']


def main(argv=None):
    tokens = list(sys.argv[1:] if argv is None else argv)
    if tokens and tokens[0] == '_run':
        module, rest = _parse_internal(tokens[1:])
        return command_run(argparse.Namespace(module=module, rest=rest))
    parser = build_parser()
    args = parser.parse_args(tokens)
    _log(' '.join(_profile_lines()))
    if args.command == 'start':
        return command_start(args)
    if args.command in ARM_SPECS:
        return command_arm(args.command, args)
    if args.command == 'validate':
        return command_validate(args)
    if args.command == 'chain':
        return command_chain(args)
    if args.command == 'all':
        return command_all(args)
    return _blocked('unknown command %r' % args.command)


if __name__ == '__main__':
    raise SystemExit(main())
