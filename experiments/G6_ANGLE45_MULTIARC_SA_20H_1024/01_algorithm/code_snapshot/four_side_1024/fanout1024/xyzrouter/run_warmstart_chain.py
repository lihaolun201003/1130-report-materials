# -*- coding: utf-8 -*-
"""Warm-start chain G1 -> G2a -> G2b -> G3 (second comparison category).

Runs, in order and each with its own validation:
  G2a: manual groups re-heighted jointly with the non-manual XY+Z re-routing
  G2b: per-route manual height, again jointly optimised
  G3 : all 1024 routes fully optimisable
and writes warmstart_comparison/summary.json + summary.md.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024.xyzrouter import paths as P

PY = str(ROOT / '.venv' / 'Scripts' / 'python.exe')


def log(message):
    print('[chain] ' + str(message), flush=True)


def run_module(module, args):
    """Run one chain stage, bootstrap-first under the 20-height profile.

    ``python -m <stage>`` imports the frozen 21-height model before
    ``coldstart20.bootstrap`` can install the 20-height one, so under the
    active 20-height profile the stage module is imported and called
    in-process.  The frozen 21-height subprocess behaviour is unchanged.
    """
    from four_side_1024.fanout1024.coldstart20 import profile_env as PE
    started = time.time()
    if PE.is_20h():
        import importlib
        argv = [str(value) for value in args]
        log('IN-PROCESS %s %s' % (module, ' '.join(argv)))
        stage = importlib.import_module(module)
        returncode = int(stage.main(argv) or 0)
        seconds = time.time() - started
        log('DONE %s rc=%s (%.1f min)'
            % (module, returncode, seconds / 60.0))
        return returncode, seconds
    command = [PY, '-m', module] + list(args)
    log('RUN ' + ' '.join(command))
    result = subprocess.run(command, cwd=str(ROOT))
    seconds = time.time() - started
    log('DONE %s rc=%s (%.1f min)' % (module, result.returncode, seconds / 60.0))
    return result.returncode, seconds


def load_summary(path):
    path = Path(path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:  # noqa: BLE001
        return None


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--g1-dir', default=str(P.DIRS['G1']))
    parser.add_argument('--g2a-round-seconds', type=float, default=300.0)
    parser.add_argument('--g2b-round-seconds', type=float, default=240.0)
    parser.add_argument('--g3-round-seconds', type=float, default=500.0)
    parser.add_argument('--skip-g3', action='store_true')
    args = parser.parse_args(argv)
    g1_dir = Path(args.g1_dir)
    if not (g1_dir / 'routes_l3d.json').exists():
        log('G1 dir not ready: %s' % g1_dir)
        return 2
    out = P.DIRS['warmstart']
    out.mkdir(parents=True, exist_ok=True)
    steps = []

    rc, seconds = run_module(
        'four_side_1024.fanout1024.xyzrouter.run_g2',
        ['--phase', 'a', '--start-from', str(g1_dir),
         '--out-a', str(P.DIRS['G2a']), '--rounds', '2',
         '--round-seconds', str(args.g2a_round_seconds),
         '--delta-budget', '80'])
    steps.append(dict(step='G2a', returncode=rc, seconds=seconds,
                      summary=load_summary(P.DIRS['G2a'] / 'summary.json')))
    if rc != 0:
        log('G2a failed, stopping chain')
        write_summary(out, steps)
        return rc

    rc, seconds = run_module(
        'four_side_1024.fanout1024.xyzrouter.run_g2',
        ['--phase', 'b', '--start-from', str(P.DIRS['G2a']),
         '--out-b', str(P.DIRS['G2b']), '--rounds', '1',
         '--round-seconds', str(args.g2b_round_seconds),
         '--route-delta-budget', '2'])
    steps.append(dict(step='G2b', returncode=rc, seconds=seconds,
                      summary=load_summary(P.DIRS['G2b'] / 'summary.json')))
    if rc != 0:
        log('G2b failed, stopping chain')
        write_summary(out, steps)
        return rc

    if not args.skip_g3:
        rc, seconds = run_module(
            'four_side_1024.fanout1024.xyzrouter.run_g3',
            ['--start-from', str(P.DIRS['G2b']),
             '--out', str(P.DIRS['G3']), '--rounds', '1',
             '--round-seconds', str(args.g3_round_seconds)])
        steps.append(dict(step='G3', returncode=rc, seconds=seconds,
                          summary=load_summary(P.DIRS['G3'] / 'summary.json')))
    write_summary(out, steps)
    return 0


def write_summary(out, steps):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    payload = dict(chain=[step['step'] for step in steps],
                   steps=steps,
                   generated_at=time.strftime('%Y-%m-%dT%H:%M:%S'))
    P.write_json(out / 'summary.json', payload)
    lines = ['# Warm-start 对比链（G2a → G2b → G3）\n',
             '| 步骤 | 返回码 | 用时 min | 起点交叉 | 终点交叉 |',
             '|---|---:|---:|---:|---:|']
    for step in steps:
        summary = step.get('summary') or {}
        lines.append('| %s | %s | %.1f | %s | %s |' % (
            step['step'], step['returncode'], step['seconds'] / 60.0,
            summary.get('start_crossings', '—'),
            summary.get('final_crossings', '—')))
    lines.append('')
    lines.append('说明：G2a/G2b 使用 `manual_policy=height_only`，'
                 'G3 使用 `fully_optimizable`；每个阶段都保存了独立的 '
                 'routes/assignment/crossing_stats/validation 与 SHA256。')
    (out / 'summary.md').write_text('\n'.join(lines), encoding='utf-8')
    log('written %s' % (out / 'summary.json'))


if __name__ == '__main__':
    sys.exit(main())
