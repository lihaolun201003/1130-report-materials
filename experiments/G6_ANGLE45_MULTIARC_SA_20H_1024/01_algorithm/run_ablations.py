# -*- coding: utf-8 -*-
"""G6 controlled ablation (experiments B/C/D/E) with a fixed move budget.

All arms start from the *same* frozen G5 warm-start payload, use the *same*
random seeds and the *same* annealing parameters; only the enabled
neighbourhood mixture differs:

    B  N1 single-route MultiArc regeneration
    C  B + N2 two-route joint MultiArc regeneration
    D  C + N4/N5 single-route re-height / lead-out joint reconstruction (+ N3/N6
       in the mix where enabled)
    E  full G6: N1..N6 (single, pair, group, multi-route height kick)

Each seed is limited by the number of proposed moves (``--max-moves``), not by
wall time, so the reported evaluation budget is comparable across arms.

Usage::

    python run_ablations.py --start <routes_l3d.json> --out <dir> \
        --arms B,C,D,E --seeds 4001,4002,4003,4004 --max-moves 3000 --workers 12
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

PROJECT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..',
                                       '..'))
BASE = os.path.join(PROJECT, 'experiments',
                    'G6_ANGLE45_MULTIARC_SA_20H_1024')


def run_arm(arm, args):
    out = os.path.join(args.out, f'arm_{arm}')
    os.makedirs(out, exist_ok=True)
    command = [
        sys.executable, '-m',
        'four_side_1024.fanout1024.xyzrouter.g6.run_g6',
        '--start', os.path.abspath(args.start),
        '--out', out,
        '--seeds', args.seeds,
        '--workers', str(args.workers),
        '--profile', arm,
        '--seconds', str(args.seconds),
        '--max-moves', str(args.max_moves),
        '--cycles', '1',
        '--T0', str(args.T0),
        '--log-seconds', str(args.log_seconds),
    ]
    env = dict(os.environ)
    env['PYTHONPATH'] = PROJECT
    log_path = os.path.join(out, 'console.log')
    started = time.time()
    with open(log_path, 'w', encoding='utf-8') as handle:
        process = subprocess.run(command, stdout=handle,
                                 stderr=subprocess.STDOUT, env=env,
                                 cwd=PROJECT)
    return dict(arm=arm, exit_code=process.returncode,
                seconds=round(time.time() - started, 2), out=out,
                log=log_path)


def summarise(arm, out):
    summary_path = os.path.join(out, 'sweep_summary.json')
    result = dict(arm=arm, out=out)
    if os.path.exists(summary_path):
        with open(summary_path, encoding='utf-8') as handle:
            sweep = json.load(handle)
        result['best_key'] = sweep.get('best_key')
        result['best_seed'] = sweep.get('best_seed')
        items = []
        for summary in sweep.get('summaries') or ():
            for cycle in summary.get('summaries') or ():
                items.append(dict(
                    seed=summary.get('seed'),
                    n_bad=cycle.get('n_bad'),
                    deficit=cycle.get('deficit'),
                    crossings=cycle.get('crossings'),
                    length_mm=cycle.get('length_mm'),
                    moves=cycle.get('moves'),
                    accepted=cycle.get('accepted'),
                    acceptance_rate=cycle.get('acceptance_rate'),
                    moves_per_second=cycle.get('moves_per_second'),
                    move_stats=cycle.get('move_stats'),
                ))
        result['runs'] = items
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', required=True)
    parser.add_argument('--out', default=os.path.join(BASE, '02_sa_runs',
                                                      'ablations'))
    parser.add_argument('--arms', default='B,C,D,E')
    parser.add_argument('--seeds', default='4001,4002,4003,4004')
    parser.add_argument('--max-moves', type=int, default=3000)
    parser.add_argument('--seconds', type=float, default=5400.0)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--T0', type=float, default=700.0)
    parser.add_argument('--log-seconds', type=float, default=120.0)
    args = parser.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    results = []
    for arm in [item.strip().upper() for item in args.arms.split(',')
                if item.strip()]:
        print(f'[ablation] starting arm {arm}', flush=True)
        run_info = run_arm(arm, args)
        summary = summarise(arm, run_info['out'])
        summary.update(run_info)
        results.append(summary)
        print(f'[ablation] arm {arm} done in {run_info["seconds"]}s: '
              f'best_key={summary.get("best_key")}', flush=True)
    payload = dict(schema='g6_ablation_v1', start=os.path.abspath(args.start),
                   seeds=args.seeds, max_moves=args.max_moves,
                   T0=args.T0, arms=results,
                   generated_at=time.strftime('%Y-%m-%dT%H:%M:%S'))
    path = os.path.join(args.out, 'ablation_summary.json')
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle, indent=1, ensure_ascii=False)
    print('[ablation] wrote ' + path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
