# -*- coding: utf-8 -*-
"""Independent 20H validator on every per-structure start state.

Uses ``validate_state_xyz.py`` (``native3d.validate_native3d`` under the 20H
profile), the same validator as the arms -- not ``run_validate`` (which wraps
the 21-height ``validate21`` contract checker).  Runs sequentially to keep
memory bounded; stores ``<state>/validation_state/``.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PY = str(ROOT / '.venv' / 'Scripts' / 'python.exe')
EXP = ROOT / 'experiments' / '20H_G4_MULTI_ARC_ABLATION_1024' \
    / '03_PER_STRUCTURE_CONTRIBUTION'
STATES = EXP / '01_states'
LOGS = EXP / 'logs'
TOOLS = EXP / 'tools'
WORKER = str(TOOLS / 'validate_state_xyz.py')
AUTHORITY = (ROOT / 'experiments' / 'COLD_START_20_HEIGHT_1024' / '07_g123'
             / 'run_xyz_joint_1024_20h' / 'baseline_authoritative')
GROUPS = ('full_on', 'no_multi_arc', 'ablate_6a', 'ablate_6b', 'ablate_6c',
          'ablate_6d', 'ablate_7a', 'ablate_7b', 'ablate_7c')


def main():
    LOGS.mkdir(parents=True, exist_ok=True)
    failures = []
    for key in GROUPS:
        state = STATES / key
        if not (state / 'routes_l3d.json').is_file():
            print('[states] missing', key)
            continue
        out = state / 'validation_state'
        out.mkdir(parents=True, exist_ok=True)
        argv = [PY, WORKER, '--run-dir', str(state),
                '--out-dir', str(out), '--baseline-dir', str(AUTHORITY)]
        print('[states] validate', key, flush=True)
        with (LOGS / ('validate_state_%s.log' % key)).open(
                'a', encoding='utf-8') as handle:
            code = subprocess.run(argv, cwd=str(ROOT), env=dict(os.environ),
                                  stdout=handle,
                                  stderr=subprocess.STDOUT).returncode
        report = {}
        path = out / 'validation.json'
        if path.is_file():
            report = json.loads(path.read_text(encoding='utf-8-sig'))
        passed = bool(report.get('validation_pass')) and int(
            report.get('violation_count') or 0) == 0
        summary = dict(
            schema='g4_structure_state_validation_v1',
            group=key, exit_code=code,
            validation_pass=report.get('validation_pass'),
            violation_count=report.get('violation_count'),
            routed=(report.get('counts') or {}).get('routed'),
            failed=(report.get('counts') or {}).get('failed'),
            crossings=(report.get('counts') or {}).get('same_plane_crossings'),
            path=str(path))
        (out / 'STATE_VALIDATION.json').write_text(
            json.dumps(summary, indent=1, ensure_ascii=False) + '\n',
            encoding='utf-8')
        print('[states]', key, 'exit', code, 'pass', passed, flush=True)
        if not passed:
            failures.append(key)
    print('[states] failures:', failures, flush=True)
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
