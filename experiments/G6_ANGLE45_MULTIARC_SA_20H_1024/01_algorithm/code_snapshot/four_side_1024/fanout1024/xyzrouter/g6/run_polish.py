# -*- coding: utf-8 -*-
"""G6 deterministic last-mile polish driver.

Loads an SA output payload, rebuilds the exact G5 world and runs the exhaustive
targeted repair loop of :mod:`...g6.polish` until no residual sub-45 crossing
can be improved.  Writes the resulting payload, a detailed per-event report and
the usual run artefacts (best_routes.json / summary.json).

Usage::

    python -m ...g6.run_polish \
        --routes <sa best_routes.json> --out <polish dir> --seconds 1800
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time

from . import sa as SA
from . import neighborhoods as NB
from . import geometry as GEO
from .polish import Polisher


def _project_root():
    path = os.path.abspath(__file__)
    for _ in range(5):
        path = os.path.dirname(path)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--routes', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--seconds', type=float, default=1800.0)
    parser.add_argument('--passes', type=int, default=8)
    parser.add_argument('--seed', type=int, default=20261120)
    parser.add_argument('--body-build', type=int, default=500)
    parser.add_argument('--pose-variants', type=int, default=6)
    parser.add_argument('--pair-keep', type=int, default=10)
    parser.add_argument('--pair-attempts', type=int, default=160)
    args = parser.parse_args(argv)

    root = _project_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    os.makedirs(args.out, exist_ok=True)
    doc = SA.load_doc(args.routes)
    log_path = os.path.join(args.out, 'logs', 'polish.log')
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    log_handle = open(log_path, 'w', encoding='utf-8')

    def log(message):
        line = '[%s] %s' % (time.strftime('%H:%M:%S'), message)
        print(line, flush=True)
        log_handle.write(line + '\n')
        log_handle.flush()

    started = time.time()
    from four_side_1024.fanout1024.xyzrouter.g5 import search as S5
    state = S5.State(doc['routes'], min_angle_deg=45.0,
                     log=lambda *a, **k: None)
    evaluator = NB.Evaluator(state)
    rng = random.Random(args.seed)
    proposer = NB.Proposer(state, evaluator, rng)
    start_snapshot = dict(n_bad=int(state.n_violations),
                          deficit=round(float(state.deficit()), 6),
                          crossings=int(len(state.crossings)),
                          length_mm=round(float(state.length), 6),
                          hard_issues=len(state.hard_issues))
    log('polish start: N_bad=%d deficit=%.6f crossings=%d'
        % (state.n_violations, state.deficit(), len(state.crossings)))
    polisher = Polisher(state, proposer, evaluator, rng,
                        cfg=dict(body_build=args.body_build,
                                 pose_variants=args.pose_variants,
                                 pair_keep=args.pair_keep,
                                 pair_attempts=args.pair_attempts),
                        log=log)
    report = polisher.run(seconds=args.seconds, passes=args.passes)
    report['start'] = start_snapshot
    report['started_at'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    report['elapsed_seconds'] = round(time.time() - started, 2)
    report['source'] = os.path.abspath(args.routes)
    report['seed'] = args.seed

    # exact re-audit with a fresh State (must agree with the incremental one)
    fresh = S5.State(list(state.world.routes.values()), min_angle_deg=45.0,
                     log=lambda *a, **k: None)
    report['reaudit'] = dict(n_bad=fresh.n_violations,
                             deficit=round(fresh.deficit(), 6),
                             crossings=len(fresh.crossings),
                             length_mm=round(fresh.length, 6),
                             hard_issues=len(fresh.hard_issues))
    report['reaudit_matches'] = bool(
        fresh.n_violations == state.n_violations and
        abs(fresh.deficit() - state.deficit()) < 1e-6)

    routes = {int(route['route_id']): route
              for route in state.world.routes.values()}
    payload = SA.write_payload(doc, routes,
                               os.path.join(args.out, 'best_routes.json'))
    with open(os.path.join(args.out, 'summary.json'), 'w',
              encoding='utf-8') as handle:
        json.dump(report, handle, indent=1, ensure_ascii=False)
    log('polish done: N_bad=%d deficit=%.6f hard_issues=%d elapsed=%.1fs'
        % (report['n_bad'], report['deficit'], report['hard_issues'],
           report['elapsed_seconds']))
    log_handle.close()
    return 0 if report['n_bad'] == 0 else 2


if __name__ == '__main__':
    raise SystemExit(main())
