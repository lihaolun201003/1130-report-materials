# -*- coding: utf-8 -*-
"""Paths / IO / seeds of the G4 experiment archive.

Single source of truth for every G4 arm.  All formal G4 artifacts live under
``<project root>/experiments/xyz_joint_g4_1024/`` (task requirement 11.6).

The G4 **start** point is always the verified G3 legal optimum
(``outputs/manual_c4_new_connectivity/XYZ_JOINT_G123_1024/best_valid``,
routes SHA256 ``711cf910...``, 1322 crossings); the historical 2409 baseline
(``baseline_authoritative``) is only used for identity / port / manual-contract
checks by the independent validator.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path

from .. import paths as XP
from ... import common as C
from ...coldstart20 import profile_env as PE

ROOT = Path(C.ROOT)
G4_ROOT = PE.path_env('G4_ROOT',
                      ROOT / 'experiments' / 'xyz_joint_g4_1024')

#: verified G3 legal optimum: the mandatory common start point of every G4 arm
START_DIR = XP.XYZ_RUN_DIR / 'best_valid'


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _start_fingerprint(start_dir):
    """Routes SHA256 + crossing total of the G3 legal optimum (no literals).

    The frozen 21-height archive hard-wired ``711cf910...`` / 1322; a different
    height profile must fingerprint its own G3 optimum, so the values are
    computed from ``best_valid``.  ``COLDSTART20_START_SHA`` /
    ``COLDSTART20_START_CROSSINGS`` win for a bit-reproducible rerun.
    """
    sha = os.environ.get('COLDSTART20_START_SHA')
    crossings = PE.int_env('START_CROSSINGS')
    routes = Path(start_dir) / 'routes_l3d.json'
    if sha is None and routes.exists():
        sha = _sha256(routes)
    if crossings is None:
        for name in ('crossing_stats.json', 'summary.json'):
            path = Path(start_dir) / name
            try:
                payload = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            value = ((payload.get('totals') or {}).get('crossings')
                     or payload.get('crossings'))
            if value is not None:
                crossings = int(value)
                break
    if PE.is_20h() and (sha is None or crossings is None):
        raise RuntimeError(
            'the 20-height G4 start point must be a validated G3 legal '
            'optimum with routes_l3d.json + crossing total: %s' % (start_dir,))
    return sha, crossings


START_ROUTES_SHA256, START_CROSSINGS = _start_fingerprint(START_DIR)

#: frozen authoritative baseline (identity + port + manual-U contract only)
def _resolve_authority_dir():
    """Identity/port/manual-U authority directory (read-only, never a start).

    The 20-height G3 run exports its own ``baseline_authoritative/`` under
    the run dir; until that exists the frozen archive copy of the same
    21-height baseline is the shared identity/port authority (the validator
    with ``manual_policy=fully_optimizable`` only uses identity / port /
    connection fields, never the routing heights).  The frozen 21-height
    path is preferred and unchanged.
    """
    candidates = [Path(XP.BASELINE_AUTHORITY)]
    candidates.extend([
        Path(C.ROOT) / 'experiments' / 'xyz_joint_g123_1024' /
        'baseline_authoritative',
        Path(C.OUTPUT_ROOT) / 'manual_c4_new_connectivity' /
        'XYZ_JOINT_G123_1024' / 'baseline_authoritative',
    ])
    for candidate in candidates:
        if (candidate / 'routes_l3d.json').exists():
            return candidate
    return Path(XP.BASELINE_AUTHORITY)


AUTHORITY_DIR = _resolve_authority_dir()

SEED = 20261104

ARM_DIRS = {
    'C0': G4_ROOT / '01_arm_C0',
    'G4a': G4_ROOT / '02_arm_G4a',
    'G4b': G4_ROOT / '03_arm_G4b',
    'G4c_frozen': G4_ROOT / '04_arm_G4c_frozen',
    'G4c_free': G4_ROOT / '05_arm_G4c_free',
    'G4d': G4_ROOT / '06_arm_G4d',
    'best_valid': G4_ROOT / '07_best_valid',
    'chain': G4_ROOT / '08_progressive_chain',
    'plots': G4_ROOT / '09_plots',
    'reports': G4_ROOT / '10_reports',
    'audit': G4_ROOT / '00_baseline_audit',
    'checkpoints': G4_ROOT / 'checkpoints',
    'code': G4_ROOT / 'code',
}

#: candidate-evaluation budget per arm (fair-comparison contract, see SPEC_G4.md)
DEFAULT_BUDGET = dict(
    route_3d_checks=30000,     # route geometries checked in the true 3D World
    d56_candidate_evals=120000,  # exact strict-D56 candidate evaluations
    wall_seconds=1800,         # hard wall-clock cap (search only, no validation)
)

#: smaller budget for the quick arms (G4a/G4b) so that all arms stay comparable
ARM_BUDGETS = {
    'C0': dict(DEFAULT_BUDGET, wall_seconds=1200),
    'G4a': dict(DEFAULT_BUDGET, wall_seconds=1200),
    'G4b': dict(DEFAULT_BUDGET, wall_seconds=1200),
    'G4c_frozen': dict(DEFAULT_BUDGET, wall_seconds=1800),
    'G4c_free': dict(DEFAULT_BUDGET, wall_seconds=1800),
    'G4d': dict(DEFAULT_BUDGET, wall_seconds=3600),
}


def ensure_dirs():
    for path in ARM_DIRS.values():
        Path(path).mkdir(parents=True, exist_ok=True)
    return ARM_DIRS


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(str(path))
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, payload, indent=1):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=indent,
                               default=str), encoding='utf-8')
    return path


def read_csv_rows(path):
    with Path(path).open('r', encoding='utf-8-sig', newline='') as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv_rows(path, rows, fieldnames=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    if not rows:
        path.write_text('', encoding='utf-8')
        return path
    if fieldnames is None:
        fieldnames = list(rows[0].keys())
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames,
                                extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, '') for key in fieldnames})
    return path


def write_csv_records(path, records, fieldnames=None):
    rows = []
    for record in records:
        row = {}
        for key, value in record.items():
            if isinstance(value, (dict, list, tuple)):
                row[key] = json.dumps(value, ensure_ascii=False, default=str)
            elif value is None:
                row[key] = ''
            else:
                row[key] = value
        rows.append(row)
    return write_csv_rows(path, rows, fieldnames)


def _active_model():
    """The height model installed in this process (20H after bootstrap)."""
    from ...reheight21 import model as M
    return M


def _model_file(model):
    try:
        return Path(model.__file__).resolve().relative_to(ROOT).as_posix()
    except (AttributeError, ValueError):
        return None


def start_model_summary():
    """Fingerprint of the ACTIVE height profile (used by the start guard)."""
    model = _active_model()
    return dict(
        profile=getattr(model, 'PROFILE', None),
        model_module=str(getattr(model, '__name__', '')),
        model_file=_model_file(model),
        plane_count=len(model.PLANE_IDS),
        body_plane_count=len(model.BODY_PLANES),
        plane_ids=[int(pid) for pid in model.PLANE_IDS],
        interface_z={key: float(value)
                     for key, value in model.INTERFACE_Z.items()},
        min_3d_clearance_mm=float(model.MIN_3D_CLEARANCE_MM),
        min_layer_pitch_mm=float(model.MIN_LAYER_PITCH_MM),
        min_bend_radius_mm=float(model.MIN_BEND_RADIUS_MM),
    )


def assert_start_profile(start, context='load_start'):
    """HARD validity guard: the start state must belong to the ACTIVE profile.

    This is a *validity* guard, not a relaxation.  Every flat height of
    every route, every ``layer_z_sequence`` entry, every route
    ``target_z_mm``/``target_layer`` and every assignment ``target_layer`` /
    ``target_z_mm`` / ``interface_z_mm`` must be a routing height of the
    model installed in this process; the identity counts (1024 routes, 1024
    assignment rows, 368 manual-U rows) must hold; and under the 20-height
    profile the imported model must really be the 20-plane model with
    identity 19 deleted.

    The frozen 21-height archive loaded a 21-height G3 optimum into a
    20-height process without any error (21 distinct flat heights, 50
    routes on the deleted plane L19).  This guard makes that silent
    21H/20H mix impossible (audit g4.md section 3.3).
    """
    model = _active_model()
    summary = start_model_summary()
    plane_ids = set(int(pid) for pid in model.PLANE_IDS)
    plane_z = {round(float(model.plane_z(pid)), 9): int(pid)
               for pid in model.PLANE_IDS}
    problems = []
    if PE.is_20h():
        if len(plane_ids) != 20 or 19 in plane_ids:
            problems.append(
                'the 20-height profile is active but the imported model has '
                '%d planes (identity 19 present=%s): bootstrap did not '
                'install coldstart20.model20 before g4 was imported'
                % (len(plane_ids), 19 in plane_ids))
    routes = list(start.get('routes') or ())
    rows = list(start.get('rows') or ())
    if len(routes) != 1024:
        problems.append('route payload has %d routes (expected 1024)'
                        % len(routes))
    if len(rows) != 1024:
        problems.append('assignment has %d rows (expected 1024)' % len(rows))
    manual = [row for row in rows
              if str(row.get('manual_group') or '').strip()]
    if len(manual) != 368:
        problems.append('assignment has %d manual-U rows (expected 368)'
                        % len(manual))
    bad_flat = {}
    bad_target_z = {}
    bad_layers = {}
    for route in routes:
        for part in route.get('parts') or ():
            if str(part.get('kind')) != 'flat':
                continue
            z = round(float(part.get('z_mm')), 9)
            if z not in plane_z:
                bad_flat[z] = bad_flat.get(z, 0) + 1
        for z in route.get('layer_z_sequence') or ():
            z = round(float(z), 9)
            if z not in plane_z:
                bad_flat[z] = bad_flat.get(z, 0) + 1
        target_z = route.get('target_z_mm')
        if target_z is not None:
            z = round(float(target_z), 9)
            if z not in plane_z:
                bad_target_z[z] = bad_target_z.get(z, 0) + 1
        target_layer = route.get('target_layer')
        if target_layer is not None and \
                int(float(target_layer)) not in plane_ids:
            bad_layers[int(float(target_layer))] = bad_layers.get(
                int(float(target_layer)), 0) + 1
    if bad_flat:
        problems.append('route flat/layer heights not in the %d-plane model: '
                        '%s' % (len(plane_ids),
                                {float(k): v for k, v
                                 in sorted(bad_flat.items())}))
    if bad_target_z:
        problems.append('route target heights not in the %d-plane model: %s'
                        % (len(plane_ids),
                           {float(k): v for k, v
                            in sorted(bad_target_z.items())}))
    if bad_layers:
        problems.append('route target layers not in the model: %s'
                        % {int(k): v for k, v in sorted(
                            bad_layers.items())})
    bad_row_layers = {}
    bad_row_z = {}
    bad_interface = {}
    for row in rows:
        layer = int(float(row.get('target_layer')))
        z = float(row.get('target_z_mm'))
        if layer not in plane_ids:
            bad_row_layers[layer] = bad_row_layers.get(layer, 0) + 1
        elif abs(z - float(model.plane_z(layer))) > 1e-9:
            bad_row_z[layer] = bad_row_z.get(layer, 0) + 1
        plane = str(row.get('plane') or '').strip()
        if plane in getattr(model, 'INTERFACE_Z', {}):
            interface_z = float(row.get('interface_z_mm'))
            if abs(interface_z - float(model.interface_z(plane))) > 1e-9:
                bad_interface[plane] = bad_interface.get(plane, 0) + 1
    if bad_row_layers:
        problems.append('assignment target_layer not in the model: %s'
                        % bad_row_layers)
    if bad_row_z:
        problems.append('assignment target_z_mm != '
                        'model.plane_z(target_layer) for layers: %s'
                        % bad_row_z)
    if bad_interface:
        problems.append('assignment interface_z_mm != model interface '
                        'height for: %s' % bad_interface)
    if problems:
        raise RuntimeError(
            'G4 start point rejected by the %s-profile validity guard '
            '[%s]: %s (start=%s).  A 21-height G3 optimum must never be '
            'loaded into a 20-height process; run the 20H G3 stage first.'
            % (summary['profile'] or 'unknown', context,
               '; '.join(problems), start.get('dir')))
    return dict(summary, route_count=len(routes),
                assignment_rows=len(rows),
                manual_route_count=len(manual),
                checks=dict(profile_20h=(len(plane_ids) == 20),
                            plane_19_absent=(19 not in plane_ids),
                            flat_heights_in_model=True,
                            target_z_in_model=True,
                            target_layers_in_model=True,
                            assignment_layers_in_model=True,
                            assignment_z_in_model=True,
                            interface_z_in_model=True,
                            route_count_1024=True,
                            manual_route_count_368=True))


def start_crossing_total(start_dir):
    """Exact crossing total recorded by a start directory, or ``None``.

    The start state's *own* count is used (``crossing_stats.json`` /
    ``summary.json`` / a G4 ``START.json``); the global ``START_CROSSINGS``
    constant is never a data source for ``load_start`` (lightweight chain
    checkpoints may carry no statistics, in which case the authoritative
    value is ``state.start_total`` after the arm loaded its state).
    """
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


def load_start(start_dir=None, validate_profile=True):
    """Load a G4 start point (default: the 20H G3 legal optimum).

    Returns the same dict shape as ``xyzrouter.paths.load_baseline`` plus
    the start fingerprint.  ``crossings`` is the start's own recorded total
    (or ``None`` for a lightweight chain checkpoint) and ``profile`` is the
    hard validity-guard result.  ``validate_profile=False`` is only used for
    the read-only identity authority, which may belong to another model.
    """
    start = Path(start_dir or START_DIR)
    payload = read_json(start / 'routes_l3d.json')
    routes = payload['routes']
    rows = read_csv_rows(start / 'assignment_1024.csv')
    loaded = dict(dir=str(start), payload=payload, routes=routes, rows=rows,
                  routes_sha256=sha256_file(start / 'routes_l3d.json'),
                  assignment_sha256=sha256_file(
                      start / 'assignment_1024.csv'),
                  crossings=start_crossing_total(start))
    if validate_profile:
        loaded['profile'] = assert_start_profile(loaded,
                                                 context='load_start')
    return loaded


def load_authority():
    """Load the read-only identity/port/manual-U authority baseline.

    The authority is not a start state and may belong to the 18-layer model
    even when a different routing profile is active, so the start-profile
    validity guard deliberately does not apply here.
    """
    return load_start(AUTHORITY_DIR, validate_profile=False)


def start_fingerprint_ok(start):
    return str(start.get('routes_sha256')) == START_ROUTES_SHA256


def seed_rng(seed=None):
    import random
    rng = random.Random(int(SEED if seed is None else seed))
    return rng
