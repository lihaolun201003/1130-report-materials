# -*- coding: utf-8 -*-
"""G6 driver: angle-aware MultiArc simulated annealing on a 1024-route payload.

Examples
--------
Single seed, warm start from the G5 51-violation solution::

    python -m four_side_1024.fanout1024.xyzrouter.g6.run_g6 \
        --start experiments/G5_ANGLE45_NATIVE3D_20H_1024/best_partial_v5/routes_l3d.json \
        --out experiments/G6_ANGLE45_MULTIARC_SA_20H_1024/02_sa_runs/warm_E \
        --seed 20261120 --profile E --seconds 3600

Multi-seed sweep (spawns one process per seed)::

    python -m ...g6.run_g6 ... --seeds 1,2,3,4 --workers 4 --seconds 3600
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

from . import sa as SA


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description='G6 angle-aware MultiArc SA')
    parser.add_argument('--start', required=True,
                        help='input routes_l3d.json (frozen payload)')
    parser.add_argument('--out', required=True,
                        help='output directory for this run / sweep')
    parser.add_argument('--seed', type=int, default=20261120)
    parser.add_argument('--seeds', default='',
                        help='comma separated seeds (spawns workers)')
    parser.add_argument('--workers', type=int, default=0,
                        help='max parallel workers for --seeds (0 = all)')
    parser.add_argument('--profile', default='E', choices=list('BCDE'))
    parser.add_argument('--seconds', type=float, default=3600.0)
    parser.add_argument('--max-moves', type=int, default=0)
    parser.add_argument('--M', type=float, default=1000.0)
    parser.add_argument('--lam', type=float, default=1.0)
    parser.add_argument('--T0', type=float, default=1200.0)
    parser.add_argument('--T-end', dest='T_end', type=float, default=45.0)
    parser.add_argument('--theta', type=float, default=45.0)
    parser.add_argument('--resume', action='store_true',
                        help='resume from <out>/seed_<seed>/checkpoints')
    parser.add_argument('--proposer-pool-size', type=int, default=28)
    parser.add_argument('--proposer-pool-build', type=int, default=800)
    parser.add_argument('--log-seconds', type=float, default=20.0)
    parser.add_argument('--cycles', type=int, default=1,
                        help='iterated-SA cycles; each restarts from the '
                             'previous best with a cooler temperature')
    parser.add_argument('--cycle-seconds', type=float, default=0.0,
                        help='seconds per cycle (0 -> --seconds / --cycles)')
    parser.add_argument('--T0-decay', dest='T0_decay', type=float, default=0.75)
    parser.add_argument('--tag', default='')
    parser.add_argument('--quiet', action='store_true')
    return parser.parse_args(argv)


def _cfg_from_args(args, seed):
    return dict(
        theta=args.theta, M=args.M, lam=args.lam, seed=seed,
        profile=args.profile, T0=args.T0, T_end=args.T_end,
        log_seconds=args.log_seconds,
        proposer=dict(pool_size=args.proposer_pool_size,
                      pool_build=args.proposer_pool_build),
    )


def run_single(args, seed, out_dir, resume=False):
    """Run one seed (possibly several iterated-SA cycles) and return summary."""
    os.makedirs(out_dir, exist_ok=True)
    cycles = max(1, int(args.cycles))
    cycle_seconds = (args.cycle_seconds if args.cycle_seconds > 0
                     else args.seconds / cycles)
    starts = [args.start]
    cycle_summaries = []
    best = None            # (key, cycle_dir, summary)
    for cycle in range(cycles):
        if cycle and best is not None:
            starts.append(os.path.join(best[1], 'best_routes.json'))
        start_path = starts[-1]
        cycle_dir = (out_dir if cycles == 1
                     else os.path.join(out_dir, 'cycle_%02d' % cycle))
        doc = SA.load_doc(start_path)
        cfg = _cfg_from_args(args, seed)
        cfg['T0'] = float(args.T0) * (float(args.T0_decay) ** cycle)
        runner = SA.G6SA(doc, cycle_dir, cfg=cfg,
                         log=(lambda message: None) if args.quiet else None,
                         resume_dir=(cycle_dir if resume and cycle == 0 else None))
        summary = runner.run(seconds=cycle_seconds,
                             max_moves=(args.max_moves or None))
        cycle_summaries.append(summary)
        key = (summary['n_bad'], round(summary['deficit'], 6),
               summary['crossings'], round(summary['length_mm'], 3))
        if best is None or key < best[0]:
            best = (key, cycle_dir, summary)
        if summary['n_bad'] == 0:
            break
    aggregate = dict(
        schema='g6_run_v1', seed=seed, profile=args.profile,
        cycles=cycles, cycle_seconds=cycle_seconds,
        T0=args.T0, T0_decay=args.T0_decay,
        start=os.path.abspath(args.start),
        best_cycle=best[1] if best else None,
        best_key=list(best[0]) if best else None,
        started=time.strftime('%Y-%m-%dT%H:%M:%S'),
        cycles_run=len(cycle_summaries), summaries=cycle_summaries,
    )
    with open(os.path.join(out_dir, 'summary.json'), 'w',
              encoding='utf-8') as handle:
        json.dump(aggregate, handle, ensure_ascii=False, indent=2)
    # expose the best cycle payload at the run root
    if best is not None and cycles > 1:
        import shutil
        for name in ('best_routes.json', 'best_meta.json'):
            source = os.path.join(best[1], name)
            if os.path.exists(source):
                shutil.copyfile(source, os.path.join(out_dir, name))
    return aggregate


def _spawn(args, seeds):
    os.makedirs(args.out, exist_ok=True)
    procs = []
    worker_cap = args.workers or len(seeds)
    pending = list(seeds)
    running = []
    summary_paths = []
    while pending or running:
        while pending and len(running) < worker_cap:
            seed = pending.pop(0)
            out_dir = os.path.join(args.out, 'seed_%d' % seed)
            os.makedirs(out_dir, exist_ok=True)
            log_path = os.path.join(out_dir, 'logs', 'console.log')
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            command = [sys.executable, '-m',
                       'four_side_1024.fanout1024.xyzrouter.g6.run_g6',
                       '--start', os.path.abspath(args.start),
                       '--out', os.path.abspath(out_dir),
                       '--seed', str(seed), '--profile', args.profile,
                       '--seconds', str(args.seconds),
                       '--M', str(args.M), '--lam', str(args.lam),
                       '--T0', str(args.T0), '--T-end', str(args.T_end),
                       '--theta', str(args.theta),
                       '--proposer-pool-size', str(args.proposer_pool_size),
                       '--proposer-pool-build', str(args.proposer_pool_build),
                       '--log-seconds', str(args.log_seconds),
                       '--cycles', str(args.cycles),
                       '--T0-decay', str(args.T0_decay),
                       '--tag', args.tag]
            if args.cycle_seconds:
                command += ['--cycle-seconds', str(args.cycle_seconds)]
            if args.max_moves:
                command += ['--max-moves', str(args.max_moves)]
            if args.resume:
                command += ['--resume']
            handle = open(log_path, 'a', encoding='utf-8')
            env = dict(os.environ)
            env['PYTHONPATH'] = _project_root()
            proc = subprocess.Popen(command, stdout=handle,
                                    stderr=subprocess.STDOUT, env=env,
                                    cwd=_project_root())
            running.append((seed, proc, handle, out_dir))
            print('[g6] started seed %d -> %s' % (seed, out_dir), flush=True)
        time.sleep(5)
        still = []
        for seed, proc, handle, out_dir in running:
            code = proc.poll()
            if code is None:
                still.append((seed, proc, handle, out_dir))
                continue
            handle.close()
            print('[g6] seed %d finished exit=%s' % (seed, code), flush=True)
            summary = os.path.join(out_dir, 'summary.json')
            if os.path.exists(summary):
                summary_paths.append(summary)
        running = still
    return summary_paths


def _project_root():
    path = os.path.abspath(__file__)
    for _ in range(5):        # file -> g6 -> xyzrouter -> fanout1024 -> four_side_1024
        path = os.path.dirname(path)
    return path


def main(argv=None):
    args = _parse_args(argv)
    if args.seeds:
        seeds = [int(value) for value in args.seeds.split(',') if value.strip()]
        started = time.time()
        paths = _spawn(args, seeds)
        aggregate = dict(
            schema='g6_sweep_v1', profile=args.profile, seeds=seeds,
            seconds=args.seconds, started=time.strftime('%Y-%m-%dT%H:%M:%S'),
            wall_seconds=round(time.time() - started, 3), summaries=[])
        for path in paths:
            with open(path, encoding='utf-8') as handle:
                aggregate['summaries'].append(json.load(handle))
        best = None
        for item in aggregate['summaries']:
            key = item.get('best_key')
            if not key:
                continue
            key = tuple(key)
            if best is None or key < best[0]:
                best = (key, item)
        if best:
            aggregate['best_seed'] = best[1]['seed']
            aggregate['best_key'] = list(best[0])
            aggregate['best_cycle'] = best[1].get('best_cycle')
        os.makedirs(args.out, exist_ok=True)
        with open(os.path.join(args.out, 'sweep_summary.json'), 'w',
                  encoding='utf-8') as handle:
            json.dump(aggregate, handle, ensure_ascii=False, indent=2)
        print(json.dumps({key: aggregate.get(key) for key in
                          ('profile', 'seeds', 'wall_seconds', 'best_seed',
                           'best_key')}, ensure_ascii=False))
        return 0
    summary = run_single(args, args.seed, args.out, resume=args.resume)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
