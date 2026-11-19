# -*- coding: utf-8 -*-
"""Publish the G5 experiment into the 1130-report-materials repository.

Copies ``experiments/G5_ANGLE45_NATIVE3D_20H_1024`` into
``work/1130-report-materials/experiments/G5_ANGLE45_NATIVE3D_20H_1024`` while

* dropping the 660 MB CTP-2.0 tree copy (only its diff/doc/outputs are shipped),
* dropping the largest search checkpoints (the final routes file is shipped),
* dropping scratch/rehearsal directories,
* stripping ``__pycache__``.

It never touches the frozen G4 / CTP trees.  ``--commit`` stages and commits;
``--push`` also pushes to origin.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / 'experiments' / 'G5_ANGLE45_NATIVE3D_20H_1024'
REPO = ROOT.parent / 'work' / '1130-report-materials'
DST = REPO / 'experiments' / 'G5_ANGLE45_NATIVE3D_20H_1024'

SKIP_DIRS = {'__pycache__', 'ctp2_g5', '_rehearsal', '_rehearsal_validation',
             '_scratch', '_probe', 'ctp2_out'}
SKIP_PREFIX = ('checkpoint_phase1_0', 'checkpoint_phase2', 'checkpoint_phase3',
               '_aborted')
MAX_BYTES = 40 * 1024 * 1024


def keep(path: Path, relative: str) -> bool:
    parts = set(Path(relative).parts)
    if parts & SKIP_DIRS:
        return False
    name = path.name
    if name.startswith(SKIP_PREFIX):
        return False
    if path.is_file() and path.stat().st_size > MAX_BYTES:
        return False
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', action='store_true')
    parser.add_argument('--push', action='store_true')
    parser.add_argument('--message', default=None)
    args = parser.parse_args(argv)
    if not REPO.exists():
        raise SystemExit('repo not found: %s' % REPO)
    if DST.exists():
        shutil.rmtree(DST)
    DST.mkdir(parents=True)
    copied = 0
    total = 0
    for path in sorted(SRC.rglob('*')):
        if not path.is_file():
            continue
        relative = str(path.relative_to(SRC))
        if not keep(path, relative):
            continue
        target = DST / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied += 1
        total += path.stat().st_size
    print('[publish] %d files, %.1f MB -> %s' % (copied, total / 1e6, DST))
    if not args.commit:
        return 0
    message = args.message or (
        'G5: angle-constrained native-3D routing (theta_min = 45 deg)\n\n'
        '- full audit of the frozen G4 crossings: 1283 events, 304 below 45 deg\n'
        '- two independent 45 deg validators + the unchanged frozen validator\n'
        '- exact endpoint-preserving move families (corridor shift / re-height /\n'
        '  native-3D excursion) and a violation-driven ALNS\n'
        '- search runs, checkpoints, per-layer figures and the CTP-2.0 re-run\n')
    for command in (['git', 'add', 'experiments/G5_ANGLE45_NATIVE3D_20H_1024'],
                    ['git', 'commit', '-m', message]):
        result = subprocess.run(command, cwd=str(REPO), capture_output=True,
                                text=True)
        print('$ %s\n%s%s' % (' '.join(command), result.stdout[-4000:],
                              result.stderr[-2000:]))
        if result.returncode != 0 and command[1] != 'commit':
            raise SystemExit(result.returncode)
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=str(REPO),
                          capture_output=True, text=True)
    print('[publish] HEAD = %s' % head.stdout.strip())
    if args.push:
        result = subprocess.run(['git', 'push', 'origin', 'HEAD'],
                                cwd=str(REPO), capture_output=True, text=True)
        print('$ git push\n%s%s' % (result.stdout[-3000:],
                                    result.stderr[-2000:]))
        print('[publish] push exit=%s' % result.returncode)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
