# -*- coding: utf-8 -*-
"""Experiment 2 driver -- strict common-start 20H multi-arc ablation.

Implements the pre-registered FINAL protocol on the 20-height model:
both arms read the **same converted common start** (1024 routes, 0 planar
multi-arc regions); the only variable is ``G4_ENABLE_MULTI_ARC``; primary runs
are counted (24000 d56 / 9000 3-D checks, 5400 s wall safety net only); the
auxiliary runs are equal wall clock (900 s); three pre-registered seeds
(20261104 / 20261116 / 20261130); independent validator + independent audit for
every run.

The actual arm implementation is the frozen port
``four_side_1024.fanout1024.coldstart20.run_multiarc`` (START / CONVERT /
arm-on / arm-off / analyse), driven here with a per-experiment root
(``COLDSTART20_MULTIARC_ROOT``) and parallel arm processes.

Usage (repository root)::

    .venv\\Scripts\\python.exe experiments\\20H_G4_MULTI_ARC_ABLATION_FINAL_1024\\tools\\run_final.py start
    ... run_final.py convert
    ... run_final.py primary
    ... run_final.py auxiliary
    ... run_final.py analyse
    ... run_final.py status
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PY = str(ROOT / '.venv' / 'Scripts' / 'python.exe')
EXP = ROOT / 'experiments' / '20H_G4_MULTI_ARC_ABLATION_FINAL_1024'
LOGS = EXP / 'logs'
MODULE = 'four_side_1024.fanout1024.coldstart20.run_multiarc'
SEEDS = (20261104, 20261116, 20261130)
MAX_PARALLEL = 2


def log(message):
    line = '[%s] %s' % (time.strftime('%Y-%m-%dT%H:%M:%S'), message)
    print(line, flush=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    with (LOGS / 'run_final.log').open('a', encoding='utf-8') as handle:
        handle.write(line + '\n')


def env():
    values = dict(os.environ)
    values['COLDSTART20_MULTIARC_ROOT'] = str(EXP)
    return values


def spawn(argv, log_name):
    LOGS.mkdir(parents=True, exist_ok=True)
    handle = (LOGS / log_name).open('a', encoding='utf-8')
    handle.write('\n===== %s =====\n' % time.strftime('%Y-%m-%dT%H:%M:%S'))
    handle.flush()
    log('spawn %s -> %s' % (' '.join(argv), log_name))
    return subprocess.Popen(argv, cwd=str(ROOT), env=env(),
                            stdout=handle, stderr=subprocess.STDOUT), handle


def wait_all(jobs):
    failed = []
    for name, process, handle in jobs:
        code = process.wait()
        handle.close()
        log('finish %s exit=%s' % (name, code))
        if code != 0:
            failed.append((name, code))
    return failed


def run_sync(argv, log_name, timeout=None):
    log('run %s' % ' '.join(argv))
    LOGS.mkdir(parents=True, exist_ok=True)
    with (LOGS / log_name).open('a', encoding='utf-8') as handle:
        handle.write('\n===== %s =====\n' % time.strftime('%Y-%m-%dT%H:%M:%S'))
        handle.flush()
        completed = subprocess.run(argv, cwd=str(ROOT), env=env(),
                                   stdout=handle, stderr=subprocess.STDOUT,
                                   timeout=timeout)
    log('done exit=%s' % completed.returncode)
    return int(completed.returncode)


def stage_start(force=False):
    argv = [PY, '-m', MODULE, 'start']
    if force:
        argv.append('--force')
    return run_sync(argv, 'start.log')


def stage_convert(force=False):
    argv = [PY, '-m', MODULE, 'convert']
    if force:
        argv.append('--force')
    return run_sync(argv, 'convert.log', timeout=7200)


def _arm_done(arm, kind, seed):
    tag = {'primary': 'c1', 'auxiliary': 'a1'}[kind] + '_%s_%d' % (arm, seed)
    out = EXP / 'runs' / arm / tag
    return (out / 'RUN_VERDICT.json').is_file() or (
        (out / 'best_valid' / 'routes_l3d.json').is_file()
        and (out / 'audit_state.json').is_file())


def _pending_arms(kind):
    pending = []
    for seed in SEEDS:
        for arm in ('on', 'off'):
            if _arm_done(arm, kind, seed):
                log('%s %s %s already done -- skip' % (kind, arm, seed))
                continue
            pending.append((arm, seed))
    return pending


def _launch_arm(kind, arm, seed):
    log_name = '%s_%s_%s.log' % (kind, arm, seed)
    argv = [PY, '-m', MODULE, 'arm-' + arm, '--seed', str(seed),
            '--kind', kind]
    process, handle = spawn(argv, log_name)
    return ('%s_%s_%d' % (kind, arm, seed), process, handle)


def stage_arms(kind, parallel=MAX_PARALLEL):
    pending = _pending_arms(kind)
    failures = []
    while pending:
        batch, pending = pending[:parallel], pending[parallel:]
        log('%s: launching %d, %d queued' % (kind, len(batch), len(pending)))
        jobs = [_launch_arm(kind, arm, seed) for arm, seed in batch]
        failures.extend(wait_all(jobs))
    return failures


def stage_analyse():
    return run_sync([PY, '-m', MODULE, 'analyse', '--with-aux'],
                    'analyse.log', timeout=7200)


def _read(path):
    path = Path(path)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except Exception:                                        # noqa: BLE001
        return None


def status():
    for kind in ('primary', 'auxiliary'):
        for seed in SEEDS:
            for arm in ('on', 'off'):
                tag = {'primary': 'c1', 'auxiliary': 'a1'}[kind] + \
                    '_%s_%d' % (arm, seed)
                out = EXP / 'runs' / arm / tag
                verdict = _read(out / 'RUN_VERDICT.json') or {}
                summary = _read(out / 'summary_g4.json') or {}
                print('%-9s %-3s %d done=%-5s crossings=%-5s dir=%s' % (
                    kind, arm, seed, bool(verdict or summary),
                    summary.get('final_crossings'), out))
    result = _read(EXP / 'tables' / 'summary_c1.json')
    if result:
        print('\nprimary summary:', json.dumps(result, ensure_ascii=False)[:800])


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    command = argv[0] if argv else 'all'
    EXP.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    if command == 'status':
        status()
        return 0
    if command in ('start', 'all'):
        code = stage_start(force='--force' in argv)
        if code:
            return code
    if command in ('convert', 'all'):
        code = stage_convert(force='--force' in argv)
        if code:
            return code
    failed = []
    if command in ('primary', 'all'):
        failed.extend(stage_arms('primary'))
    if command in ('auxiliary', 'all'):
        failed.extend(stage_arms('auxiliary'))
    if failed:
        log('arm failures: %s' % failed)
        return 1
    if command in ('analyse', 'all'):
        code = stage_analyse()
        if code:
            return code
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
