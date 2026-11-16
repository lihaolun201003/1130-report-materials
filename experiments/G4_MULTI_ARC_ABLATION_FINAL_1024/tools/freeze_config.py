# -*- coding: utf-8 -*-
"""Freeze the experiment configuration *before* any formal run.

Writes ``config/FROZEN_CONFIG.json`` with

* the frozen budget/seed/stage parameters of the two formal experiments,
* the SHA256 of every Python source file of the ``four_side_1024`` package that
  the router actually imports (so the exact code state is auditable),
* the SHA256 of the two data files of the common start state,
* a timestamp and the host/python identification.

The file is written once; re-running the script refuses to overwrite an
existing frozen config unless ``--force`` is given (and then records the
previous content under ``history``).

Usage::

    python experiments/G4_MULTI_ARC_ABLATION_FINAL_1024/tools/freeze_config.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
ROOT = EXP.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

START_DIR = Path('C:/Users/lihao/Desktop/Graduation Project/work/1130-report-materials/'
                 'G4_MULTI_ARC_ABLATION_1024/no_multi_arc/01_convert')

FROZEN = dict(
    schema='g4_multi_arc_final_config_v1',
    common_start=dict(
        dir=str(START_DIR),
        routes_l3d_json_sha256='1707e189c271c94723af2a7ba304a2cd1deb52955216eff7e063851b964eb15f',
        assignment_1024_csv_sha256='ec6e394c40eb090160ba6770644505b0438851650d8503e3909cc7218bf8ec6d',
        crossings=3967,
        multi_arc_regions=0,
    ),
    single_variable=dict(
        name='enable_multi_arc',
        on='G4_ENABLE_MULTI_ARC=1',
        off='G4_ENABLE_MULTI_ARC=0',
        injection='four_side_1024/fanout1024/layer2d.py:_LayerRouter._iter_candidates',
    ),
    seeds=[20261104, 20261116, 20261130],
    arms=[
        dict(arm='on', multi_arc=1, tag_prefix='c1_on'),
        dict(arm='off', multi_arc=0, tag_prefix='c1_off'),
    ],
    primary=dict(  # equal candidate-evaluation budget
        engine_arm='G4c_free',
        counted_d56_budget=24000,
        counted_checks_guard=9000,
        wall_safety_net_seconds=5400,
        counted_sweep_fraction=0.18,
        stage_sizes=[8, 16, 32, 64],
        stage_fractions=[0.22, 0.24, 0.26, 0.28],
        sweep_ratio=0.18,
        stop_rule='d56_candidate_evals >= 24000 (or route_3d_checks >= 9000, '
                  'or wall >= 5400 s)',
    ),
    auxiliary=dict(  # equal wall-clock budget
        engine_arm='G4c_free',
        counted_d56_budget=0,
        wall_seconds=900,
        counted_sweep_fraction=0.18,
        stage_sizes=[8, 16, 32, 64],
        stage_fractions=[0.22, 0.24, 0.26, 0.28],
        sweep_ratio=0.18,
        stop_rule='wall_seconds >= 900 (engine stage schedule by wall fractions)',
    ),
    constraints=dict(
        routes=1024, board_mm=[150.0, 150.0, 1.0], heights=21,
        r15_mm=15.0, d56_clearance_mm=0.08, min_3d_clearance_mm=0.05,
        validator_policy='fully_optimizable',
        crossing_rule='frozen strict same-plane D56 (>=5 deg legal crossing)',
    ),
    decision_rule=dict(
        A='3/3 seeds ON<OFF and paired mean gap >= 200 crossings and ON length '
          'increase <= 5% and all hard gates pass',
        C='paired mean gap <= 0 or direction inconsistent',
        B='otherwise',
    ),
    non_claims=[
        'no optical insertion-loss claim',
        'no claim about all smooth curves, only the frozen D56 candidate grammar',
        'historical 1185/1202/3484 archive stays read-only',
    ],
)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def source_snapshot():
    package = ROOT / 'four_side_1024'
    files = {}
    for path in sorted(package.rglob('*.py')):
        rel = path.relative_to(ROOT).as_posix()
        files[rel] = sha256_file(path)
    return dict(package='four_side_1024', file_count=len(files), files=files)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args(argv)

    out = EXP / 'config' / 'FROZEN_CONFIG.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(FROZEN)
    payload['frozen_at'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    payload['host'] = platform.node()
    payload['python'] = sys.version.split()[0]
    payload['executable'] = sys.executable
    payload['source_snapshot'] = source_snapshot()
    payload['start_files'] = dict(
        routes_l3d_json=sha256_file(START_DIR / 'routes_l3d.json'),
        assignment_1024_csv=sha256_file(START_DIR / 'assignment_1024.csv'))
    text = json.dumps(payload, ensure_ascii=False, indent=1)
    if out.exists() and not args.force:
        print('REFUSING to overwrite existing frozen config: %s' % out)
        print('(use --force only if no formal run has started yet)')
        return 1
    if out.exists():
        history = EXP / 'config' / ('FROZEN_CONFIG.%s.json'
                                    % time.strftime('%Y%m%dT%H%M%S'))
        history.write_text(out.read_text(encoding='utf-8'), encoding='utf-8')
        print('previous config archived to %s' % history)
    out.write_text(text, encoding='utf-8')
    print('frozen config written: %s' % out)
    print('source files hashed   : %d' % payload['source_snapshot']['file_count'])
    print('start routes sha256   : %s' % payload['start_files']['routes_l3d_json'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
