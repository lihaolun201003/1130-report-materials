# -*- coding: utf-8 -*-
"""Model self-check: reproduce the frozen G4 numbers with the G5 engine."""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024.xyzrouter.g5 import model as G5

RUN = ROOT / 'experiments' / 'COLD_START_20_HEIGHT_1024' / '10_best_valid'


def main():
    started = time.time()
    payload = json.loads((RUN / 'routes_l3d.json').read_text(encoding='utf-8'))
    routes = payload['routes']
    world = G5.World(routes, min_angle_deg=G5.THETA_MIN_DEG)
    print('world built in %.2fs  routes=%d' % (time.time() - started,
                                               len(world.routes)))

    mark = time.time()
    result = world.audit_all(min_angle_deg=G5.OLD_MIN_ANGLE_DEG)
    print('[G4 rule 5 deg] crossings=%d issues=%d min_non_crossing=%.9f (%.1fs)'
          % (len(result['crossings']), len(result['issues']),
             result['min_non_crossing'][0], time.time() - mark))
    kinds = {}
    for issue in result['issues']:
        kinds[issue['kind']] = kinds.get(issue['kind'], 0) + 1
    print('   issue kinds:', kinds)

    result45 = world.audit_all(min_angle_deg=G5.THETA_MIN_DEG)
    angles = [event['angle_deg'] for event in result45['crossings']]
    print('[G5 rule 45 deg] crossings=%d issues=%d'
          % (len(result45['crossings']), len(result45['issues'])))
    bad = [a for a in angles if a < 45.0]
    print('   min angle=%.6f  N<45=%d  Dtheta=%.6f  Dmax=%.6f'
          % (min(angles), len(bad), sum(45.0 - a for a in bad),
             max(45.0 - a for a in bad)))
    kinds45 = {}
    for issue in result45['issues']:
        kinds45[issue['kind']] = kinds45.get(issue['kind'], 0) + 1
    print('   issue kinds:', kinds45)
    pairs = {(event['route_a'], event['route_b']) for event in result45['crossings']}
    print('   pairs=%d routes_with_crossings=%d'
          % (len(pairs), len({r for p in pairs for r in p})))

    # per-route local evaluation must agree with the global audit
    mark = time.time()
    global_bad = {}
    for event in result45['crossings']:
        if event['angle_deg'] < 45.0:
            global_bad.setdefault(event['route_a'], []).append(event)
            global_bad.setdefault(event['route_b'], []).append(event)
    mismatches = 0
    hard_issues = 0
    for rid in sorted(world.routes)[:120]:
        local = world.route_issues(rid, min_angle_deg=G5.THETA_MIN_DEG)
        local_bad = [i for i in local['issues']
                     if i['kind'] in ('angle_below_min', 'tangent_touch')]
        hard = [i for i in local['issues']
                if i['kind'] not in ('angle_below_min', 'tangent_touch')]
        if len(local_bad) != len(global_bad.get(rid, [])):
            mismatches += 1
            print('   MISMATCH route %d local=%d global=%d'
                  % (rid, len(local_bad), len(global_bad.get(rid, []))))
        hard_issues += len(hard)
        if hard:
            print('   HARD route %d: %s' % (rid, hard[:3]))
    print('[local check] first 120 routes: mismatches=%d hard_issues=%d (%.1fs)'
          % (mismatches, hard_issues, time.time() - mark))
    print('total %.1fs' % (time.time() - started))


if __name__ == '__main__':
    main()
