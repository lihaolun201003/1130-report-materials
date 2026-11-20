# -*- coding: utf-8 -*-
"""G6 early-start arm: angle-aware MultiArc generation inside the cold-start.

This driver re-runs the *construction* stage of the frozen 20-height cold start
(stages C-F: per-height strict-D56 MultiArc 2-D body routing -> 3-D assembly ->
repair -> finalize) on top of the *identical* frozen stage-A/B artefacts
(layer assignment + endpoint fan-out transitions).  The only changed variable is

    ``G6_ANGLE_AWARE=1``  ->  ``layer2d._attempt`` scores a pool of legal
                               MultiArc candidates by the number of real
                               crossings below 45 deg (then angle deficit, then
                               body length) instead of committing the first
                               feasible candidate.

With ``--angle-aware 0`` the same driver reproduces the frozen greedy geometry
(control arm).  Everything downstream (G6 SA) then starts from this genuinely
reproducible early state -- no assumed ``routes_l3d.json``.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time


def _project_root():
    path = os.path.abspath(__file__)
    for _ in range(5):        # file -> g6 -> xyzrouter -> fanout1024 -> four_side_1024
        path = os.path.dirname(path)
    return path


def _copy_tree(source, target):
    if os.path.isdir(target):
        shutil.rmtree(target)
    shutil.copytree(source, target)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frozen-stage03', required=True,
                        help='frozen COLD_START 03_fanout_and_xy/run_initial_20h')
    parser.add_argument('--out', required=True,
                        help='fresh run directory for the early-start arm')
    parser.add_argument('--angle-aware', type=int, default=1, choices=(0, 1))
    parser.add_argument('--angle-theta', type=float, default=45.0)
    parser.add_argument('--angle-pool', type=int, default=24)
    parser.add_argument('--max-iters', type=int, default=3)
    parser.add_argument('--stages', default='CDEF')
    args = parser.parse_args(argv)

    root = _project_root()
    if root not in sys.path:
        sys.path.insert(0, root)

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    # stage A/B artefacts are copied verbatim: the layer assignment and the R15
    # endpoint transitions are NOT modified by this arm.
    _copy_tree(os.path.abspath(args.frozen_stage03), out)
    for stale in ('routes_l3d.json', 'failed_routes.json', 'validation.json',
                  'final_stats.json', 'crossing_stats.json'):
        path = os.path.join(out, stale)
        if os.path.exists(path):
            os.remove(path)

    os.environ['G6_ANGLE_AWARE'] = str(int(args.angle_aware))
    os.environ['G6_ANGLE_MIN_DEG'] = str(float(args.angle_theta))
    os.environ['G6_ANGLE_POOL'] = str(int(args.angle_pool))

    # ``layer2d`` may already be imported by the package import chain (which
    # happens before this module body with ``python -m``), so the env-based
    # policy snapshot can be stale: force the effective policy explicitly.
    from four_side_1024.fanout1024 import layer2d as _L2
    _L2.ANGLE_AWARE_POLICY['enabled'] = bool(args.angle_aware)
    _L2.ANGLE_AWARE_POLICY['theta_deg'] = float(args.angle_theta)
    _L2.ANGLE_AWARE_POLICY['pool'] = int(args.angle_pool)
    _L2.ANGLE_AWARE_POLICY['source'] = 'cli:run_early'

    from four_side_1024.fanout1024.coldstart20 import run_initial

    started = time.time()
    run_initial.main(['--stages', args.stages,
                      '--max-iters', str(args.max_iters),
                      '--run-dir', out, '--skip-assign'])
    elapsed = time.time() - started

    # independent audit of the produced geometry (G5 exact model, 45 deg rule)
    routes_path = os.path.join(out, 'routes_l3d.json')
    summary = dict(schema='g6_early_start_v1', out=out,
                   angle_aware=int(args.angle_aware),
                   angle_theta=float(args.angle_theta),
                   angle_pool=int(args.angle_pool),
                   stages=args.stages, elapsed_seconds=round(elapsed, 3),
                   generated_at=time.strftime('%Y-%m-%dT%H:%M:%S'))
    if os.path.exists(routes_path):
        from four_side_1024.fanout1024.xyzrouter.g5 import model as G5
        from four_side_1024.fanout1024.xyzrouter.g5 import search as S5
        with open(routes_path, encoding='utf-8') as handle:
            doc = json.load(handle)
        state = S5.State(doc['routes'], min_angle_deg=45.0,
                         log=lambda *a, **k: None)
        angles = [event['angle_deg'] for event in state.crossings]
        summary.update(dict(
            routes=len(state.world.routes), routed=doc.get('routed'),
            crossings=len(state.crossings),
            n_bad=len(state.violations),
            deficit=round(state.deficit(), 6),
            min_angle=(round(min(angles), 6) if angles else None),
            hard_issues=len(state.hard_issues),
            length_mm=round(state.length, 6),
            routes_with_violations=len(state.per_route)))
        with open(os.path.join(out, 'early_stats.json'), 'w',
                  encoding='utf-8') as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2)
    try:
        from four_side_1024.fanout1024 import layer2d as _L2
        summary['angle_aware_policy'] = dict(_L2.ANGLE_AWARE_POLICY)
        summary['angle_aware_counters'] = _L2.angle_aware_counters_snapshot()
        with open(os.path.join(out, 'early_stats.json'), 'w',
                  encoding='utf-8') as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2)
    except Exception:  # noqa: BLE001
        pass
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)
