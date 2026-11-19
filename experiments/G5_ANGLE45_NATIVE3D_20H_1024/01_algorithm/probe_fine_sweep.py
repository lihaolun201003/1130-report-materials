# -*- coding: utf-8 -*-
"""Probe: can a *fine* corridor sweep zero the violations of a residual route?

The residual violations are dominated by arc-vs-line crossings whose offending
line passes the arc centre at |dy| in (10.6, 15) mm -- a displacement of at most
4.4 mm would move it into the legal band.  The previous search only tried a
coarse delta grid (+-2,3,4,5,7,...).  Here we sweep the corridor basis with a
0.25 mm grid over +-16 mm and ask, for each residual route, whether *any* single
exact move leaves it with zero sub-45 deg crossings.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024.xyzrouter.g5 import model as G5
from four_side_1024.fanout1024.xyzrouter.g5 import candidates as C
from four_side_1024.fanout1024.xyzrouter.g5 import search as S

EXP = ROOT / 'experiments' / 'G5_ANGLE45_NATIVE3D_20H_1024'
SOURCE = EXP / '03_best_partial' / 'routes_l3d.json'


def fine_deltas(step=0.25, span=16.0):
    count = int(span / step)
    return [round(i * step, 6) for i in range(-count, count + 1) if i]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--routes', default=str(SOURCE))
    parser.add_argument('--limit', type=int, default=24)
    parser.add_argument('--step', type=float, default=0.25)
    parser.add_argument('--span', type=float, default=16.0)
    parser.add_argument('--out', default=str(EXP / '02_search_runs' / 'fine_sweep_probe'))
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    payload = json.loads(Path(args.routes).read_text(encoding='utf-8'))
    state = S.State(payload['routes'])
    base = state.summary()
    print('[state] %s' % base, flush=True)

    deltas = fine_deltas(args.step, args.span)
    print('[grid] %d deltas per basis direction (+-%.1f mm, %.2f mm step)'
          % (len(deltas), args.span, args.step), flush=True)

    deg = Counter()
    for event in state.violations:
        deg[event['route_a']] += 1
        deg[event['route_b']] += 1
    targets = [rid for rid, _count in deg.most_common()]
    if args.limit:
        targets = targets[:args.limit]

    started = time.time()
    rows = []
    stat = Counter()
    for index, rid in enumerate(targets):
        route = state.world.routes[rid]
        body = C.single_body(route)
        current = len(state.route_violations(rid))
        best = (current, None, None)
        evaluated = 0
        if body is not None:
            for label, new_route in C.corridor_variants(route, deltas,
                                                        limit_per_route=4000,
                                                        min_length=0.6):
                evaluation = state.evaluate(rid, new_route)
                evaluated += 1
                if not evaluation['ok']:
                    stat['reject_hard'] += 1
                    continue
                count = len(evaluation['violations'])
                if count < best[0]:
                    best = (count, label, new_route)
                    if count == 0:
                        break
        rows.append(dict(route_id=rid, violations_before=current,
                         violations_best=best[0], move=best[1],
                         evaluated=evaluated))
        stat['zero' if best[0] == 0 else ('improved' if best[0] < current
                                          else 'stuck')] += 1
        if (index + 1) % 4 == 0:
            print('[%d/%d] zero=%d improved=%d stuck=%d (%.0fs)'
                  % (index + 1, len(targets), stat['zero'], stat['improved'],
                     stat['stuck'], time.time() - started), flush=True)
    summary = dict(schema='g5_fine_sweep_probe_v1', routes=len(targets),
                   zero=stat['zero'], improved=stat['improved'],
                   stuck=stat['stuck'], reject_hard=stat['reject_hard'],
                   base=base, seconds=round(time.time() - started, 1))
    (out / 'fine_sweep_probe.json').write_text(
        json.dumps(dict(summary=summary, rows=rows), indent=1,
                   ensure_ascii=False), encoding='utf-8')
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
