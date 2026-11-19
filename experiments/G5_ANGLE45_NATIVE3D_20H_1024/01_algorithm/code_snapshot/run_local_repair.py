# -*- coding: utf-8 -*-
"""G5 step 9.2 -- single-route / single-pair local repair experiment.

For every one of the 304 sub-45 deg crossings of the frozen G4 solution we ask
the cheapest possible question:

    can ONE of the two routes be reshaped (corridor shift / re-height /
    native-3D over-pass) so that this route ends up with ZERO sub-45 deg
    crossings while every other hard constraint stays satisfied?

The answer bounds what the global search has to do.  Nothing is mutated here:
each candidate is evaluated against the untouched frozen world.
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
OUT = ROOT / 'experiments' / 'G5_ANGLE45_NATIVE3D_20H_1024' / '02_search_runs' / 'local_repair'


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--max-candidates', type=int, default=140)
    parser.add_argument('--out', default=str(OUT))
    parser.add_argument('--seed', type=int, default=20261104)
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    payload = json.loads((RUN / 'routes_l3d.json').read_text(encoding='utf-8'))
    routes = payload['routes']
    started = time.time()
    state = S.State(routes)
    print('[state] %s (%.1fs)' % (state.summary(), time.time() - started),
          flush=True)

    violations = sorted(state.violations, key=lambda e: e['angle_deg'])
    if args.limit:
        violations = violations[:args.limit]
    records = []
    stat = Counter()
    tried = Counter()
    for order, event in enumerate(violations):
        ra, rb = event['route_a'], event['route_b']
        # which route has fewer violations -> try it first
        order_routes = sorted((ra, rb), key=lambda r: state.per_route[r])
        point = (event['x'], event['y'])
        fixed = False
        detail = None
        for rid in order_routes:
            hint = S.route_hint(state, rid, event)
            pool = S.candidate_pool(state, rid,
                                    limit=args.max_candidates,
                                    seed=args.seed + order,
                                    hint=hint,
                                    planes=G5.all_heights())
            for label, new_route in pool:
                tried[label.split(':')[0]] += 1
                evaluation = state.evaluate(rid, new_route)
                if not evaluation['ok']:
                    stat['reject_hard'] += 1
                    continue
                if evaluation['violations']:
                    stat['reject_violations'] += 1
                    continue
                fixed = True
                detail = dict(route=rid, move=label)
                stat['fixed_by_' + label.split(':')[0]] += 1
                break
            if fixed:
                break
        stat['fixed' if fixed else 'unfixed'] += 1
        records.append(dict(order=order, route_a=ra, route_b=rb,
                            z=event['z'], x=event['x'], y=event['y'],
                            angle_deg=event['angle_deg'],
                            fixed=bool(fixed), detail=detail))
        if (order + 1) % 20 == 0:
            print('[%d/%d] fixed=%d unfixed=%d (%.0fs)'
                  % (order + 1, len(violations), stat['fixed'],
                     stat['unfixed'], time.time() - started), flush=True)
    summary = dict(schema='g5_local_repair_v1', events=len(violations),
                   fixed=stat['fixed'], unfixed=stat['unfixed'],
                   fixed_by={k[9:]: v for k, v in stat.items()
                             if k.startswith('fixed_by_')},
                   evaluated={k: v for k, v in tried.items()},
                   reject_hard=stat['reject_hard'],
                   reject_violations=stat['reject_violations'],
                   seconds=round(time.time() - started, 1))
    (out / 'local_repair_summary.json').write_text(
        json.dumps(summary, indent=1, ensure_ascii=False), encoding='utf-8')
    (out / 'local_repair_events.json').write_text(
        json.dumps(records, indent=1, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
