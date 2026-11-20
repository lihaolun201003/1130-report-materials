# -*- coding: utf-8 -*-
"""G7 code snapshot: complete runnable source + SHA256 manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
EXP_NAME = 'G7_FIXED_LAYER_MULTIARC_CROSSING_OPT_1024'
PACKAGE_ROOT = 'four_side_1024'
DRIVERS = [
    'experiments/G7_FIXED_LAYER_MULTIARC_CROSSING_OPT_1024/01_algorithm/'
    'make_figures_g7.py',
    'experiments/G7_FIXED_LAYER_MULTIARC_CROSSING_OPT_1024/01_algorithm/'
    'build_report_g7.py',
    'experiments/G7_FIXED_LAYER_MULTIARC_CROSSING_OPT_1024/01_algorithm/'
    'snapshot_code_g7.py',
    'experiments/G7_FIXED_LAYER_MULTIARC_CROSSING_OPT_1024/01_algorithm/'
    'publish_repo_g7.py',
]


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    entries = []
    missing = []
    skip_dirs = {'__pycache__', 'outputs', 'experiments', 'results', 'data',
                 'tmp', 'scratch'}
    package_files = []
    for base, dirs, files in os.walk(os.path.join(PROJECT, PACKAGE_ROOT)):
        dirs[:] = [name for name in dirs if name not in skip_dirs]
        for name in files:
            if name.endswith('.py'):
                package_files.append(
                    os.path.relpath(os.path.join(base, name), PROJECT))
    for relative in DRIVERS + package_files:
        source = os.path.join(PROJECT, relative)
        if not os.path.exists(source):
            missing.append(relative)
            continue
        target = os.path.join(out, relative)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(source, target)
        entries.append(dict(path=relative, bytes=os.path.getsize(target),
                            sha256=sha256(target)))
    manifest = dict(
        schema='g7_code_snapshot_v1', project=PROJECT,
        project_git_commit=_git_commit(PROJECT),
        created_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
        files=entries, missing=missing,
        g5_git_gap_fixed=dict(
            present=[name for name in (
                'four_side_1024/fanout1024/xyzrouter/g5/batch.py',
                'four_side_1024/fanout1024/xyzrouter/g5/layer_solver.py')
                if os.path.exists(os.path.join(out, name))]),
        note='G6 + G7 sources are snapshotted together: the G7 fixed-layer engine '
             'reuses the G6 MultiArc geometry generator, the G5 exact model and '
             'the frozen fslw strict-D56 audit.')
    with open(os.path.join(out, 'CODE_MANIFEST.json'), 'w',
              encoding='utf-8') as handle:
        json.dump(manifest, handle, indent=1, ensure_ascii=False)
    print('[snapshot] %d files, missing %d -> %s'
          % (len(entries), len(missing), out))
    if missing:
        print('[snapshot] MISSING ' + json.dumps(missing))
    return 0 if not missing else 2


def _git_commit(path):
    try:
        result = subprocess.run(['git', '-C', path, 'rev-parse', 'HEAD'],
                                capture_output=True, text=True, timeout=30)
        return result.stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


if __name__ == '__main__':
    raise SystemExit(main())
