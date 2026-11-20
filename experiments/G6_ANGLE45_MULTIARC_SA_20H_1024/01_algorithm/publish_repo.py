# -*- coding: utf-8 -*-
"""Publish the G6 experiment into the 1130-report-materials repository.

The live experiment directory is ~900 MB because every annealing cycle keeps a
2.4 MB routes payload.  The repository only needs what is required to *reproduce
and audit* the result, so this script copies a curated subset:

* everything in ``00_baseline``, ``01_algorithm``, ``03_best_*``,
  ``04_validation``, ``05_figures``, ``06_reports`` and the top-level docs;
* ``02_sa_runs``: sweep summaries, per-seed summaries/logs, cycle
  ``history.jsonl`` + ``best_meta.json``, the frozen SA snapshots, early-start
  artefacts, polish summaries/logs, ablation summaries/logs;
* it drops cycle ``best_routes.json`` / ``latest_routes.json`` /
  ``checkpoints`` (except the few selected snapshots), re-tuning scratch runs
  (``tune*``, ``smoke*``, ``profile*``, ``debug*``, ``polish_test``) and
  everything named ``__pycache__``.

``--commit`` stages + commits ``experiments/G6_ANGLE45_MULTIARC_SA_20H_1024``;
``--push`` also pushes to origin.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
EXP_NAME = 'G6_ANGLE45_MULTIARC_SA_20H_1024'
SRC = os.path.join(PROJECT, 'experiments', EXP_NAME)
REPO = os.path.abspath(os.path.join(PROJECT, '..', 'work',
                                    '1130-report-materials'))
DST = os.path.join(REPO, 'experiments', EXP_NAME)

SKIP_DIRS = {'__pycache__', 'checkpoints', 'tune1', 'tune2', 'tune3',
             'smoke', 'smoke2', 'smoke3', 'profile', 'profile2', 'debug1',
             'debug_par', 'polish_test', 'early', 'warm_B_v1', 'warm_B_v2',
             'warm_B_v3', 'warm_B_v4_tmp', 'best_snapshots_tmp'}
SKIP_NAMES = {'latest_routes.json', 'checkpoint_latest.json',
              'run_meta.json'}
MAX_BYTES = 40 * 1024 * 1024
#: 2.4 MB payloads worth shipping: the frozen inputs, the two zero solutions,
#: the SA snapshots that the polish stage consumed.
KEEP_PAYLOAD = (
    '00_baseline/',
    '03_best_feasible/',
    '03_best_partial/',
    '04_validation/',
    '02_sa_runs/best_snapshots/',
    '02_sa_runs/early2/early_off/routes_l3d.json',
    '02_sa_runs/early2/early_on/routes_l3d.json',
    '02_sa_runs/early_SA_B/seed_3006/best_routes.json',
    '02_sa_runs/polish_1008/best_routes.json',
    '02_sa_runs/polish_1001c/best_routes.json',
)


def keep(relative, size):
    parts = set(relative.replace('\\', '/').split('/'))
    if parts & SKIP_DIRS:
        return False
    name = os.path.basename(relative)
    if name in SKIP_NAMES:
        return False
    if size > MAX_BYTES:
        return False
    if name in ('best_routes.json', 'routes_l3d.json'):
        return any(relative.startswith(prefix) for prefix in KEEP_PAYLOAD)
    return True


def copy_tree():
    if os.path.isdir(DST):
        shutil.rmtree(DST)
    os.makedirs(DST)
    copied = 0
    total = 0
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
    return copied, total


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', action='store_true')
    parser.add_argument('--push', action='store_true')
    parser.add_argument('--message', default=None)
    args = parser.parse_args(argv)
    if not os.path.isdir(REPO):
        raise SystemExit('repo not found: %s' % REPO)
    copied, total = copy_tree()
    print('[publish] %d files, %.1f MB -> %s' % (copied, total / 1e6, DST))
    if not args.commit:
        return 0
    message = args.message or (
        'G6: angle-aware MultiArc simulated annealing for 1024-channel 20-height '
        'waveguide routing\n\n'
        '- angle-aware MultiArc candidate selection inside the frozen layer2d '
        'generator (1365 -> 1166 sub-45 constructions, -14.6%)\n'
        '- new G6 SA kernel on the complete 1024-route XYZ geometry '
        '(E = M*N_bad + lambda*D_theta, Metropolis, reheating, checkpoints)\n'
        '- neighbourhoods N1..N6 (single/pair/group MultiArc regeneration, '
        'multi-route re-height, port-lead/transition joint reconstruction)\n'
        '- G5 warm start 51 -> SA best 4 -> deterministic exhaustive repair 0\n'
        '- dual acceptance: frozen project validator A PASS + independent '
        '45 deg validator B PASS => G6_ANGLE45_VALID_PASS\n'
        '- G5 batch.py / layer_solver.py are finally under version control '
        '(complete four_side_1024 code snapshot, SHA256 manifest)\n')
    for command in (['git', 'add', 'experiments/' + EXP_NAME],
                    ['git', 'commit', '-m', message]):
        result = subprocess.run(command, cwd=REPO, capture_output=True,
                                text=True)
        print('$ %s\n%s%s' % (' '.join(command), result.stdout[-4000:],
                              result.stderr[-2000:]))
        if result.returncode != 0 and command[1] != 'commit':
            raise SystemExit(result.returncode)
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=REPO,
                          capture_output=True, text=True)
    print('[publish] HEAD = %s' % head.stdout.strip())
    if args.push:
        result = subprocess.run(['git', 'push', 'origin', 'HEAD'],
                                cwd=REPO, capture_output=True, text=True)
        print('$ git push\n%s%s' % (result.stdout[-3000:],
                                    result.stderr[-3000:]))
        print('[publish] push exit=%s' % result.returncode)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
