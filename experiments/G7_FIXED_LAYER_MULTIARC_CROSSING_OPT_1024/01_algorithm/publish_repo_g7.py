# -*- coding: utf-8 -*-
"""Publish the G7 experiment into the 1130-report-materials repository."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
EXP_NAME = 'G7_FIXED_LAYER_MULTIARC_CROSSING_OPT_1024'
SRC = os.path.join(PROJECT, 'experiments', EXP_NAME)
REPO = os.path.abspath(os.path.join(PROJECT, '..', 'work',
                                    '1130-report-materials'))
DST = os.path.join(REPO, 'experiments', EXP_NAME)

SKIP_DIRS = {'__pycache__', 'checkpoints', '_probe_tmp'}
SKIP_NAMES = {'latest_routes.json', 'latest_state.json', 'run_meta.json'}
MAX_BYTES = 40 * 1024 * 1024
KEEP_PAYLOAD_PREFIX = (
    '00_frozen_g6/',
    '03_best_valid/',
    '04_validation/',
    '02_sa_runs/selected_best/',
)


def keep(relative, size):
    parts = set(relative.replace('\\', '/').split('/'))
    if parts & SKIP_DIRS:
        return False
    name = os.path.basename(relative)
    if name in SKIP_NAMES or size > MAX_BYTES:
        return False
    if name in ('best_routes.json', 'routes_l3d.json'):
        return any(relative.startswith(prefix)
                   for prefix in KEEP_PAYLOAD_PREFIX)
    if name == 'frozen_manifest.json':
        return (relative.startswith('00_frozen_g6/')
                or relative.startswith('03_best_valid/'))
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', action='store_true')
    parser.add_argument('--push', action='store_true')
    parser.add_argument('--message', default=None)
    args = parser.parse_args(argv)
    if not os.path.isdir(REPO):
        raise SystemExit('repo not found: %s' % REPO)
    if os.path.isdir(DST):
        shutil.rmtree(DST)
    os.makedirs(DST)
    copied = total = 0
    for base, dirs, files in os.walk(SRC):
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS]
        for name in files:
            source = os.path.join(base, name)
            relative = os.path.relpath(source, SRC).replace('\\', '/')
            if not keep(relative, os.path.getsize(source)):
                continue
            target = os.path.join(DST, relative)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(source, target)
            copied += 1
            total += os.path.getsize(source)
    print('[publish] %d files, %.1f MB -> %s'
          % (copied, total / 1e6, DST))
    if not args.commit:
        return 0
    message = args.message or (
        'G7: fixed-layer MultiArc crossing minimization on the G6 solution\n\n'
        '- frozen G6 45-degree solution (1024/1024, 20 heights, 4578 crossings) '
        'with real per-route heights / R15 transitions extracted from '
        'routes_l3d.json (not from the stale assignment CSV)\n'
        '- authoritative crossing/angle/D56 bookkeeping with the same '
        'fslw strict-D56 pair audit as the frozen project validator\n'
        '- fixed-layer MultiArc SA (E = N_cross) with N1 single-route, N2 pair, '
        'N3 group and N5 layer-hotspot neighbourhoods\n'
        '- deterministic fixed-layer polish + frozen-structure verifier\n'
        '- dual acceptance: validator A + independent validator B + frozen '
        'structure PASS\n')
    for command in (['git', 'add', 'experiments/' + EXP_NAME],
                    ['git', 'commit', '-m', message]):
        result = subprocess.run(command, cwd=REPO, capture_output=True,
                                text=True)
        print('$ %s\n%s%s' % (' '.join(command), result.stdout[-3000:],
                              result.stderr[-2000:]))
        if result.returncode != 0 and command[1] != 'commit':
            raise SystemExit(result.returncode)
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=REPO,
                          capture_output=True, text=True)
    print('[publish] HEAD = %s' % head.stdout.strip())
    if args.push:
        result = subprocess.run(['git', 'push', 'origin', 'HEAD'], cwd=REPO,
                                capture_output=True, text=True)
        print('$ git push\n%s%s' % (result.stdout[-2000:],
                                    result.stderr[-2000:]))
        print('[publish] push exit=%s' % result.returncode)
    return 0


def _unused():
    return time.strftime('%Y-%m-%dT%H:%M:%S')


if __name__ == '__main__':
    raise SystemExit(main())
