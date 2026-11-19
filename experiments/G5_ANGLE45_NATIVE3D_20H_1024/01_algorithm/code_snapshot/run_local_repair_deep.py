# -*- coding: utf-8 -*-
"""Deep probe of the violations that single-route repair could not fix.

For every event that ``run_local_repair`` marked ``unfixed`` we now try the
*complete* single-route move space of both routes:

* every one of the 19 alternative physical heights (re-height),
* every corridor shift of every parallel run pair with a dense delta grid,
* every native-3D over/under-pass plane on every straight run that contains the
  crossing point.

Nothing is committed.  The result is the true single-route ceiling.
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

RUN = ROOT / 'experiments' / 'COLD_START_20_HEIGHT_1024' / '10_best_valid'
EXP = ROOT / 'experiments' / 'G5_ANGLE45_NATIVE3D_20H_1024'

DELTAS = (-40.0, -34.0, -28.0, -23.0, -19.0, -16.0, -13.0, -11.0, -9.5, -8.0,
          -6.5, -5.0, -4.0, -3.0, -2.0, -1.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.5,
          8.0, 9.5, 11.0, 13.0, 16.0, 19.0, 23.0, 28.0, 34.0, 40.0)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--events', default=str(
        EXP / '02_search_runs' / 'local_repair' / 'local_repair_events.json'))
    parser.add_argument('--out', default=str(
        EXP / '02_search_runs' / 'local_repair_deep'))
    parser.add_argument('--limit', type=int, default=0)
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    events = json.loads(Path(args.events).read_text(encoding='utf-8'))
    todo = [event for event in events if not event['fixed']]
    if args.limit:
        todo = todo[:args.limit]
    payload = json.loads((RUN / 'routes_l3d.json').read_text(encoding='utf-8'))
    state = S.State(payload['routes'])
    print('[state] %s' % state.summary(), flush=True)
    planes = G5.all_heights()
    started = time.time()
    rows = []
    stat = Counter()
    for index, event in enumerate(todo):
        point = (event['x'], event['y'])
        fixed = False
        detail = None
        for rid in (event['route_a'], event['route_b']):
            route = state.world.routes[rid]
            moves = []
            moves.extend(C.reheight_variants(route, planes))
            moves.extend(C.corridor_variants(route, DELTAS))
            body = C.single_body(route)
            if body is not None:
                moves.extend(S.excursion_candidates(route, body, point, planes))
            for label, new_route in moves:
                evaluation = state.evaluate(rid, new_route)
                stat['evaluated'] += 1
                if not evaluation['ok']:
                    stat['reject_hard'] += 1
                    continue
                if evaluation['violations']:
                    stat['reject_violations'] += 1
                    continue
                fixed = True
                detail = dict(route=rid, move=label)
                stat['fixed_' + label.split(':')[0]] += 1
                break
            if fixed:
                break
        stat['fixed' if fixed else 'unfixed'] += 1
        rows.append(dict(**event, deep_fixed=bool(fixed), deep_detail=detail))
        if (index + 1) % 10 == 0:
            print('[%d/%d] fixed=%d unfixed=%d (%.0fs)'
                  % (index + 1, len(todo), stat['fixed'], stat['unfixed'],
                     time.time() - started), flush=True)
    summary = dict(schema='g5_local_repair_deep_v1', events=len(todo),
                   fixed=stat['fixed'], unfixed=stat['unfixed'],
                   fixed_by={k[6:]: v for k, v in stat.items()
                             if k.startswith('fixed_')},
                   evaluated=stat['evaluated'],
                   reject_hard=stat['reject_hard'],
                   reject_violations=stat['reject_violations'],
                   seconds=round(time.time() - started, 1))
    (out / 'deep_probe_summary.json').write_text(
        json.dumps(summary, indent=1, ensure_ascii=False), encoding='utf-8')
    (out / 'deep_probe_events.json').write_text(
        json.dumps(rows, indent=1, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
