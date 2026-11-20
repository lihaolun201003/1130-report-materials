# -*- coding: utf-8 -*-
"""G3 experiment: every original manual-U route is a fully optimisable route.

The 368 manual connections keep their route_id / source / target / true ports but
their geometry (XY corridor, body height, U depth, number and position of the
R15 end transitions) is free and optimised with the same XY+Z joint router as the
non-manual routes.  Validated with ``manual_policy='fully_optimizable'``.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024.xyzrouter import experiment as E  # noqa: E402
from four_side_1024.fanout1024.xyzrouter import paths as P  # noqa: E402


def log(message):
    print(message, flush=True)


def parse_cfg(text):
    cfg = {}
    for chunk in (text or '').split(','):
        chunk = chunk.strip()
        if not chunk:
            continue
        key, _, value = chunk.partition('=')
        cfg[key.strip()] = json.loads(value.strip())
    return cfg


def main(argv=None):
    parser = argparse.ArgumentParser(description='G3 full XYZ joint re-routing')
    parser.add_argument('--start-from', default='')
    parser.add_argument('--out', default=str(P.DIRS['G3']))
    parser.add_argument('--rounds', type=int, default=2)
    parser.add_argument('--round-seconds', type=float, default=1200.0)
    parser.add_argument('--top', type=int, default=None)
    parser.add_argument('--cfg', default='')
    parser.add_argument('--skip-validate', action='store_true')
    args = parser.parse_args(argv)
    P.ensure_dirs()
    started = time.time()
    run_dir = Path(args.out)
    start = None if args.start_from in (None, '', 'baseline', 'auto') \
        else Path(args.start_from)
    baseline, state = E.load_state(start, log=log)
    log('=' * 78)
    log('[g3] start=%s total=%d' % (baseline['dir'], state.total))
    optimizer, result = E.run_all_route_optimizer(
        state, baseline, run_dir, rounds=args.rounds,
        round_seconds=args.round_seconds, cfg=parse_cfg(args.cfg),
        label='g3', log=log)
    summary = dict(experiment='G3_manual_full_xyz',
                   start_dir=baseline['dir'],
                   start_crossings=int(optimizer.base_total),
                   final_crossings=int(state.total),
                   accepted_changes=len(optimizer.history),
                   rounds=result.get('rounds'),
                   elapsed_seconds=round(time.time() - started, 2))
    E.write_summary(run_dir, summary)
    log('[g3] final total=%d (start %d)' % (state.total, optimizer.base_total))
    if not args.skip_validate:
        original = str(P.baseline_dir())
        try:
            report, vs = E.validate_stage(run_dir, original,
                                          run_dir / 'validation',
                                          'fully_optimizable', log=log)
        except Exception as error:  # noqa: BLE001
            log('[g3] validation failed: %s' % error)
    return 0


if __name__ == '__main__':
    sys.exit(main())
