# -*- coding: utf-8 -*-
"""G5 driver: run the angle-constrained global search on the frozen G4 start.

Examples
--------
    python experiments\\G5_ANGLE45_NATIVE3D_20H_1024\\01_algorithm\\run_g5.py `
        --seed 20261104 --profile free --phase1-limit 150 `
        --phase2-seconds 3600 --out <dir>

Writes (into ``--out``): ``routes_l3d.json`` checkpoint, ``g5_search_history.csv``,
``g5_candidate_statistics.csv``, ``g5_summary.json`` and a meta file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024.xyzrouter.g5 import model as G5
from four_side_1024.fanout1024.xyzrouter.g5 import engine as E

FROZEN = ROOT / 'experiments' / 'COLD_START_20_HEIGHT_1024' / '10_best_valid'
EXPECTED_SHA = '35d7ebed00339bee21fe0ca47075c9b34008120522a47933a099efacf0b90753'


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=20261104)
    parser.add_argument('--profile', choices=('free', 'frozen'), default='free',
                        help='frozen = manual-U routes are never moved')
    parser.add_argument('--phase1-limit', type=int, default=150)
    parser.add_argument('--phase2-seconds', type=float, default=1800.0)
    parser.add_argument('--phase1-only', action='store_true')
    parser.add_argument('--polish-passes', type=int, default=2)
    parser.add_argument('--out', default=None)
    parser.add_argument('--checkpoint-every', type=int, default=25)
    parser.add_argument('--resume', default=None,
                        help='checkpoint routes_l3d.json to resume from')
    args = parser.parse_args(argv)

    out = Path(args.out or (ROOT / 'experiments' / 'G5_ANGLE45_NATIVE3D_20H_1024'
                            / '02_search_runs'
                            / ('seed_%d_%s' % (args.seed, args.profile))))
    out.mkdir(parents=True, exist_ok=True)
    log_path = out / 'run.log'

    def log(message):
        line = str(message)
        print(line, flush=True)
        with log_path.open('a', encoding='utf-8') as handle:
            handle.write(line + '\n')

    digest = sha256_file(FROZEN / 'routes_l3d.json')
    if digest != EXPECTED_SHA:
        raise SystemExit('frozen routes sha256 mismatch: %s' % digest)
    payload = json.loads((FROZEN / 'routes_l3d.json').read_text(encoding='utf-8'))
    if args.resume:
        payload = json.loads(Path(args.resume).read_text(encoding='utf-8'))
        log('[resume] %s' % args.resume)

    frozen_routes = ()
    if args.profile == 'frozen':
        frozen_routes = [int(route['route_id']) for route in payload['routes']
                         if str(route.get('manual_group') or '').strip()]
        log('[frozen] %d manual-U routes excluded from moves' % len(frozen_routes))

    engine = E.Engine(payload, FROZEN, out, seed=args.seed,
                      frozen_routes=frozen_routes, log=log, args=vars(args))
    log('[start] %s' % engine.state.summary())
    engine.record('start')

    started = time.time()
    deadline = started + args.phase2_seconds + 3600.0
    engine.phase1(limit=args.phase1_limit, deadline=deadline)
    engine.save_checkpoint('phase1')
    engine.write_history()
    engine.write_moves()
    log('[phase1 done] %s' % engine.state.summary())

    if not args.phase1_only:
        engine.phase2(budget_seconds=args.phase2_seconds, deadline=deadline)
        engine.save_checkpoint('phase2')
        engine.write_history()
        engine.write_moves()
        engine.phase3(passes=args.polish_passes)
        engine.save_checkpoint('phase3')
        engine.write_history()
        engine.write_moves()

    final = engine.state.summary()
    (out / 'g5_summary.json').write_text(
        json.dumps(dict(profile=args.profile, seed=args.seed,
                        args=vars(args), final=final,
                        moves=engine.moves[-40:],
                        seconds=round(time.time() - started, 1)),
                   indent=1, ensure_ascii=False), encoding='utf-8')
    (out / 'g5_best_routes.json').write_text(
        json.dumps(engine.as_payload(), ensure_ascii=False), encoding='utf-8')
    log('[final] %s' % final)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
