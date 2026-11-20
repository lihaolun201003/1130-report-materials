# -*- coding: utf-8 -*-
"""Shared paths / IO helpers for the XYZ joint router experiments."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from .. import common as C
from ..coldstart20 import profile_env as PE

ROOT = Path(C.ROOT)
OUTPUT_ROOT = Path(C.OUTPUT_ROOT)

#: previous-round join-optimised native-3D run (READ ONLY)
NATIVE_JOINT_DIR = PE.path_env(
    'NATIVE3D_DEF_RUN', OUTPUT_ROOT / 'NATIVE_3D_JOINT_OPT_1024')
NATIVE_PHASE1_DIR = PE.path_env(
    'NATIVE3D_ABC_RUN', OUTPUT_ROOT / 'NATIVE_3D_CROSSING_OPT_1024')
NON_C4_DIR = PE.path_env('NONC4_ROOT',
                         OUTPUT_ROOT / 'NON_C4_CROSSING_OPT_1024')
E5_DIR = PE.path_env('E5_DIR', NON_C4_DIR / 'E5_joint_repair_final')

#: this round's run directory
XYZ_RUN_DIR = PE.path_env('XYZ_RUN',
                          OUTPUT_ROOT / 'XYZ_JOINT_G123_1024')
BASELINE_AUTHORITY = XYZ_RUN_DIR / 'baseline_authoritative'

DIRS = {
    'preflight': XYZ_RUN_DIR / 'preflight_audit',
    'router_validation': XYZ_RUN_DIR / 'router_validation',
    'G1': XYZ_RUN_DIR / 'G1_manual_frozen',
    'G2a': XYZ_RUN_DIR / 'G2a_manual_group_reheight',
    'G2b': XYZ_RUN_DIR / 'G2b_manual_route_reheight',
    'G3': XYZ_RUN_DIR / 'G3_manual_full_xyz',
    'fair': XYZ_RUN_DIR / 'fair_comparison',
    'warmstart': XYZ_RUN_DIR / 'warmstart_comparison',
    'best_valid': XYZ_RUN_DIR / 'best_valid',
    'checkpoints': XYZ_RUN_DIR / 'checkpoints',
    'plots': XYZ_RUN_DIR / 'plots',
    'reports': XYZ_RUN_DIR / 'reports',
    'baseline': BASELINE_AUTHORITY,
}

SCHEMA = 'xyz_joint_g123_routes_v1'
ALGORITHM = 'XYZ_JOINT_MOTION_PRIMITIVE_SEARCH'


def ensure_dirs():
    for path in DIRS.values():
        Path(path).mkdir(parents=True, exist_ok=True)
    return DIRS


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path, default=None):
    path = Path(path)
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(str(path))
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, payload, indent=1):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=indent),
                    encoding='utf-8')
    return path


def read_csv_rows(path):
    path = Path(path)
    with path.open('r', encoding='utf-8-sig', newline='') as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv_rows(path, rows, fieldnames=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text('', encoding='utf-8')
        return path
    if fieldnames is None:
        fieldnames = list(rows[0].keys())
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, '') for key in fieldnames})
    return path


def write_csv_records(path, records, fieldnames=None):
    """Write records whose values may be dict/list (JSON-encoded)."""
    rows = []
    for record in records:
        row = {}
        for key, value in record.items():
            if isinstance(value, (dict, list, tuple)):
                row[key] = json.dumps(value, ensure_ascii=False)
            elif value is None:
                row[key] = ''
            else:
                row[key] = value
        rows.append(row)
    return write_csv_rows(path, rows, fieldnames)


def baseline_dir():
    """The authoritative 2409 baseline directory (falls back to best_valid)."""
    authority = BASELINE_AUTHORITY
    if (authority / 'routes_l3d.json').exists():
        return authority
    return NATIVE_JOINT_DIR / 'best_valid'


def load_baseline(base_dir=None):
    """Load the authoritative baseline: payload, routes, csv rows, sha."""
    base = Path(base_dir or baseline_dir())
    routes_path = base / 'routes_l3d.json'
    payload = load_json(routes_path)
    routes = payload['routes']
    rows = read_csv_rows(base / 'assignment_1024.csv')
    return dict(dir=str(base), payload=payload, routes=routes, rows=rows,
                routes_sha256=sha256_file(routes_path),
                assignment_sha256=sha256_file(base / 'assignment_1024.csv'))
