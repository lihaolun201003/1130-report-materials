# -*- coding: utf-8 -*-
"""G7 driver: fixed-layer MultiArc crossing minimization.

Examples
--------
Warm start from the frozen G6 solution, single seed::

    python -m four_side_1024.fanout1024.xyzrouter.g7.run_g7 \
        --start experiments/G6_ANGLE45_MULTIARC_SA_20H_1024/03_best_feasible/routes_l3d.json \
        --out experiments/G7_FIXED_LAYER_MULTIARC_CROSSING_OPT_1024/02_sa_runs/A \
        --profile A --seed 7001 --seconds 2400

Multi-seed sweep::

    ... --seeds 7001,7002,7003 --workers 3 --seconds 2400 --cycles 4
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

from . import frozen as FR
from . import sa as SA


def _project_root():
    path = os.path.abspath(__file__)
    for _ in range(5):        # file -> g7 -> xyzrouter -> fanout1024 -> four_side_1024
        path = os.path.dirname(path)
    return path


def load_doc(path):
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description='G7 fixed-layer MultiArc SA')
    parser.add_argument('--start', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--manifest', default=None,
                        help='optional frozen manifest JSON (built from start)')
    parser.add_argument('--seed', type=int, default=7001)
    parser.add_argument('--seeds', default='')
    parser.add_argument('--workers', type=int, default=0)
    parser.add_argument('--profile', default='A', choices=['A', 'B', 'C'])
    parser.add_argument('--seconds', type=float, default=2400.0)
    parser.add_argument('--max-moves', type=int, default=0)
    parser.add_argument('--cycles', type=int, default=1)
    parser.add_argument('--cycle-seconds', type=float, default=0.0)
    parser.add_argument('--T0', type=float, default=1.2)
    parser.add_argument('--T-end', dest='T_end', type=float, default=0.05)
    parser.add_argument('--pool-size', type=int, default=16)
    parser.add_argument('--pool-build', type=int, default=140)
    parser.add_argument('--n1-sample', type=int, default=4)
    parser.add_argument('--log-seconds', type=float, default=60.0)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--tag', default='')
    parser.add_argument('--quiet', action='store_true')
    return parser.parse_args(argv)


def _cfg(args, seed):
    return dict(seed=seed, profile=args.profile,
                T0=args.T0, T_end=args.T_end,
                pool_size=args.pool_size, pool_build=args.pool_build,
                n1_sample=args.n1_sample, log_seconds=args.log_seconds)


def run_single(args, seed, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    cycles = max(1, int(args.cycles))
    cycle_seconds = (args.cycle_seconds if args.cycle_seconds > 0
                     else args.seconds / cycles)
    starts = [args.start]
    cycle_summaries = []
    best = None
    manifest = None
    for cycle in range(cycles):
        start_path = starts[-1] if cycle else args.start
        if cycle and best is not None:
            start_path = os.path.join(best[1], 'best_routes.json')
        cycle_dir = (out_dir if cycles == 1
                     else os.path.join(out_dir, 'cycle_%02d' % cycle))
        doc = load_doc(start_path)
        if manifest is None:
            if args.manifest and os.path.exists(args.manifest):
                manifest = FR.load_manifest(args.manifest)
            else:
                manifest = FR.build_manifest(doc['routes'])
                FR.write_manifest(os.path.join(out_dir,
                                               'frozen_manifest.json'),
                                  manifest)
                verify = FR.verify_payload(doc['routes'], manifest)
                if not verify['pass']:
                    raise SystemExit('start payload violates the frozen '
                                     'manifest: %s'
                                     % verify['violations'][:5])
        runner = SA.G7SA(doc, manifest, cycle_dir, cfg=_cfg(args, seed),
                         log=(lambda message: None) if args.quiet else None,
                         resume_dir=(cycle_dir if args.resume and cycle == 0
                                     else None))
        summary = runner.run(seconds=cycle_seconds,
                             max_moves=(args.max_moves or None))
        runner.close()
        cycle_summaries.append(summary)
        key = (summary['crossings'],
               -round(summary['min_angle_deg'], 6),
               summary['unique_pairs'],
               round(summary['length_mm'], 3))
        if best is None or key < best[0]:
            best = (key, cycle_dir, summary)
        if args.seconds and cycle + 1 == cycles and _stopped(summary):
            break
    aggregate = dict(schema='g7_run_v1', seed=seed, profile=args.profile,
                     cycles=cycles, cycle_seconds=cycle_seconds,
                     start=os.path.abspath(args.start),
                     best_cycle=best[1] if best else None,
                     best_key=list(best[0]) if best else None,
                     cycles_run=len(cycle_summaries),
                     started=time.strftime('%Y-%m-%dT%H:%M:%S'),
                     summaries=cycle_summaries)
    with open(os.path.join(out_dir, 'summary.json'), 'w',
              encoding='utf-8') as handle:
        json.dump(aggregate, handle, indent=1, ensure_ascii=False)
    if best is not None and cycles > 1:
        import shutil
        for name in ('best_routes.json', 'best_meta.json'):
            source = os.path.join(best[1], name)
            if os.path.exists(source):
                shutil.copyfile(source, os.path.join(out_dir, name))
    return aggregate


def _stopped(summary):
    return True


def _spawn(args, seeds):
    os.makedirs(args.out, exist_ok=True)
    pending = list(seeds)
    running = []
    worker_cap = args.workers or len(seeds)
    summary_paths = []
    root = _project_root()
    while pending or running:
        while pending and len(running) < worker_cap:
            seed = pending.pop(0)
            out_dir = os.path.join(args.out, 'seed_%d' % seed)
            os.makedirs(out_dir, exist_ok=True)
            log_path = os.path.join(out_dir, 'logs', 'console.log')
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            command = [sys.executable, '-m',
                       'four_side_1024.fanout1024.xyzrouter.g7.run_g7',
                       '--start', os.path.abspath(args.start),
                       '--out', os.path.abspath(out_dir),
                       '--seed', str(seed), '--profile', args.profile,
                       '--seconds', str(args.seconds),
                       '--cycles', str(args.cycles),
                       '--cycle-seconds', str(args.cycle_seconds),
                       '--T0', str(args.T0), '--T-end', str(args.T_end),
                       '--pool-size', str(args.pool_size),
                       '--pool-build', str(args.pool_build),
                       '--n1-sample', str(args.n1_sample),
                       '--log-seconds', str(args.log_seconds),
                       '--tag', args.tag]
            if args.max_moves:
                command += ['--max-moves', str(args.max_moves)]
            if args.resume:
                command += ['--resume']
            handle = open(log_path, 'a', encoding='utf-8')
            env = dict(os.environ)
            env['PYTHONPATH'] = root
            proc = subprocess.Popen(command, stdout=handle,
                                    stderr=subprocess.STDOUT, env=env,
                                    cwd=root)
            running.append((seed, proc, handle, out_dir))
            print('[g7] started seed %d -> %s' % (seed, out_dir), flush=True)
        time.sleep(5)
        still = []
        for seed, proc, handle, out_dir in running:
            code = proc.poll()
            if code is None:
                still.append((seed, proc, handle, out_dir))
                continue
            handle.close()
            print('[g7] seed %d finished exit=%s' % (seed, code), flush=True)
            summary = os.path.join(out_dir, 'summary.json')
            if os.path.exists(summary):
                summary_paths.append(summary)
        running = still
    return summary_paths


def main(argv=None):
    args = _parse_args(argv)
    if args.seeds:
        seeds = [int(value) for value in args.seeds.split(',') if value.strip()]
        started = time.time()
        paths = _spawn(args, seeds)
        aggregate = dict(schema='g7_sweep_v1', profile=args.profile,
                         seeds=seeds, seconds=args.seconds,
                         wall_seconds=round(time.time() - started, 3),
                         summaries=[])
        for path in paths:
            with open(path, encoding='utf-8') as handle:
                aggregate['summaries'].append(json.load(handle))
        best = None
        for item in aggregate['summaries']:
            key = item.get('best_key')
            if key is None:
                continue
            if best is None or tuple(key) < best[0]:
                best = (tuple(key), item)
        if best:
            aggregate['best_seed'] = best[1]['seed']
            aggregate['best_key'] = list(best[0])
            aggregate['best_cycle'] = best[1].get('best_cycle')
        os.makedirs(args.out, exist_ok=True)
        with open(os.path.join(args.out, 'sweep_summary.json'), 'w',
                  encoding='utf-8') as handle:
            json.dump(aggregate, handle, indent=1, ensure_ascii=False)
        print(json.dumps({key: aggregate.get(key) for key in
                          ('profile', 'seeds', 'wall_seconds', 'best_seed',
                           'best_key')}, ensure_ascii=False))
        return 0
    summary = run_single(args, args.seed, args.out)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
