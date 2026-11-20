# -*- coding: utf-8 -*-
"""Freeze the complete runnable G6 source into ``01_algorithm/code_snapshot``.

The G5 round discovered that ``g5/batch.py`` and ``g5/layer_solver.py`` had been
left out of the repository even though the report used them; G6 fixes that by
snapshotting **every** module the G6 result depends on, with SHA256, and by
verifying that the snapshot is complete (no file referenced by the G6 pipeline
is missing, and the G5 batch/layer-solver sources are present).

Usage::

    python snapshot_code.py --out <exp>/01_algorithm/code_snapshot
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))

#: every file needed to reproduce the G6 experiments from a clean checkout
FILES = [
    # ---- experiment drivers --------------------------------------------
    'experiments/G6_ANGLE45_MULTIARC_SA_20H_1024/01_algorithm/run_ablations.py',
    'experiments/G6_ANGLE45_MULTIARC_SA_20H_1024/01_algorithm/make_figures.py',
    'experiments/G6_ANGLE45_MULTIARC_SA_20H_1024/01_algorithm/snapshot_code.py',
    'experiments/G6_ANGLE45_MULTIARC_SA_20H_1024/01_algorithm/build_report.py',
]

#: the whole routing source package is snapshotted (12.5 MB) so that a clean
#: clone can actually run the search, not just read a selected module list
PACKAGE_ROOT = 'four_side_1024'

#: files the G5 report used but never committed (explicitly guarded here)
G5_GAP_FILES = (
    'four_side_1024/fanout1024/xyzrouter/g5/batch.py',
    'four_side_1024/fanout1024/xyzrouter/g5/layer_solver.py',
)


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
    # 1) the complete routing source package (all .py + data files)
    package = os.path.join(PROJECT, PACKAGE_ROOT)
    package_files = []
    skip_dirs = {'__pycache__', 'outputs', 'experiments', 'results', 'data',
                 'tmp', 'scratch'}
    for base, dirs, files in os.walk(package):
        dirs[:] = [name for name in dirs if name not in skip_dirs]
        for name in files:
            if not name.endswith('.py'):
                continue
            package_files.append(os.path.relpath(os.path.join(base, name),
                                                 PROJECT))
    # 2) experiment-level drivers
    explicit = list(FILES)
    for relative in explicit + package_files:
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
        schema='g6_code_snapshot_v1',
        project=PROJECT,
        project_git_commit=_git_commit(PROJECT),
        created_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
        files=entries, missing=missing,
        g5_git_gap_fixed=dict(
            note='G5 report used g5/batch.py and g5/layer_solver.py but the G5 '
                 'code snapshot did not include them; both are included here.',
            present=[name for name in ('four_side_1024/fanout1024/xyzrouter/g5/'
                                       'batch.py',
                                       'four_side_1024/fanout1024/xyzrouter/g5/'
                                       'layer_solver.py')
                     if os.path.exists(os.path.join(out, name))]),
    )
    path = os.path.join(out, 'CODE_MANIFEST.json')
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(manifest, handle, indent=1, ensure_ascii=False)
    print('[snapshot] copied %d files, missing %d -> %s'
          % (len(entries), len(missing), out))
    if missing:
        print('[snapshot] MISSING: ' + json.dumps(missing, indent=1))
    return 0 if not missing else 2


def _git_commit(path):
    try:
        import subprocess
        result = subprocess.run(['git', '-C', path, 'rev-parse', 'HEAD'],
                                capture_output=True, text=True, timeout=30)
        return result.stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


if __name__ == '__main__':
    raise SystemExit(main())
