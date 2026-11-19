# -*- coding: utf-8 -*-
"""Probe: combined re-height + corridor reshape as one move.

The single families stall because a re-height alone lands the route on a plane
where its *current* shape grazes other arcs, and a corridor shift alone cannot
leave the danger band without breaking D56 elsewhere.  The combination has
19 x (corridor basis x delta) options per route and is exactly the kind of joint
move the G5 neighbourhood lacked.

For each target route: for every alternative physical height, build the exact
re-heighted route, then sweep a corridor grid on it, and report the best
achievable number of sub-45 deg crossings for that route.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024.xyzrouter.g5 import model as G5
from four_side_1024.fanout1024.xyzrouter.g5 import candidates as C
from four_side_1024.fanout1024.xyzrouter.g5 import search as S

EXP = ROOT / 'experiments' / 'G5_ANGLE45_NATIVE3D_20H_1024'
SOURCE = EXP / '03_best_partial' / 'routes_l3d.json'
COARSE = (-14.0, -11.5, -9.0, -7.0, -5.5, -4.5, -3.5, -2.5, -1.5, 1.5, 2.5,
          3.5, 4.5, 5.5, 7.0, 9.0, 11.5, 14.0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--routes', default=str(SOURCE))
    parser.add_argument('--limit', type=int, default=12)
    parser.add_argument('--out', default=str(EXP / '02_search_runs'
                                             / 'joint_probe'))
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    payload = json.loads(Path(args.routes).read_text(encoding='utf-8'))
    state = S.State(payload['routes'])
    print('[state] %s' % state.summary(), flush=True)

    deg = Counter()
    for event in state.violations:
        deg[event['route_a']] += 1
        deg[event['route_b']] += 1
    heights = G5.all_heights()
    targets = [rid for rid, _n in deg.most_common()][:args.limit]

    started = time.time()
    rows = []
    stat = Counter()
    for index, rid in enumerate(targets):
        route = state.world.routes[rid]
        current = len(state.route_violations(rid))
        best = (current, None, None)
        evaluated = 0
        for z in heights:
            reheighted = C.reheight(route, z)
            if reheighted is None:
                continue
            evaluation = state.evaluate(rid, reheighted)
            evaluated += 1
            if evaluation['ok'] and len(evaluation['violations']) < best[0]:
                best = (len(evaluation['violations']), 'reheight:%.3f' % z,
                        reheighted)
                if best[0] == 0:
                    break
            if not evaluation['ok']:
                continue
            for label, variant in C.corridor_variants(reheighted, COARSE,
                                                      limit_per_route=60):
                evaluation = state.evaluate(rid, variant)
                evaluated += 1
                if not evaluation['ok']:
                    stat['reject_hard'] += 1
                    continue
                count = len(evaluation['violations'])
                if count < best[0]:
                    best = (count, 'reheight:%.3f+%s' % (z, label), variant)
                    if count == 0:
                        break
            if best[0] == 0:
                break
        rows.append(dict(route_id=rid, before=current, best=best[0],
                         move=best[1], evaluated=evaluated))
        stat['zero' if best[0] == 0 else ('improved' if best[0] < current
                                          else 'stuck')] += 1
        print('[%d/%d] route %d  %d -> %d  (%s)  evals=%d  zero=%d improved=%d '
              'stuck=%d  %.0fs'
              % (index + 1, len(targets), rid, current, best[0], best[1],
                 evaluated, stat['zero'], stat['improved'], stat['stuck'],
                 time.time() - started), flush=True)
    summary = dict(schema='g5_joint_probe_v1', routes=len(targets),
                   zero=stat['zero'], improved=stat['improved'],
                   stuck=stat['stuck'], reject_hard=stat['reject_hard'],
                   seconds=round(time.time() - started, 1))
    (out / 'joint_probe.json').write_text(
        json.dumps(dict(summary=summary, rows=rows), indent=1,
                   ensure_ascii=False), encoding='utf-8')
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
