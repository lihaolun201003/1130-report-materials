# -*- coding: utf-8 -*-
"""Prototype: can a corridor shift fix a shallow arc-arc crossing?

Route 743 (N15 -> W08, body plane z=+0.175) crosses route 723 (N12 -> W07,
same plane) at 5.153763 deg: their second 90-deg R15 arcs are nearly
concentric (centres 1.35 mm apart).

We rebuild route 743's body by lengthening the west run between its two jog
arcs by +11 mm (and shortening the final west run by -11 mm so the target pose
is unchanged), then re-audit route 743 against the frozen world with the same
exact algebra the baseline audit uses.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024.xyzrouter.g4 import independent_metrics as IM

RUN = ROOT / 'experiments' / 'COLD_START_20_HEIGHT_1024' / '10_best_valid'


def shift_downstream(prims, index, delta, direction):
    """Lengthen prim ``index`` by ``delta`` and translate everything after it."""
    out = []
    dx, dy = direction
    for k, prim in enumerate(prims):
        prim = json.loads(json.dumps(prim))
        if k < index:
            out.append(prim)
            continue
        if k == index:
            if prim['kind'] != 'line':
                raise SystemExit('pivot is not a line')
            prim['p1'] = [prim['p1'][0] + dx * delta, prim['p1'][1] + dy * delta]
            out.append(prim)
            continue
        if prim['kind'] == 'line':
            prim['p0'] = [prim['p0'][0] + dx * delta, prim['p0'][1] + dy * delta]
            prim['p1'] = [prim['p1'][0] + dx * delta, prim['p1'][1] + dy * delta]
        else:
            prim['center'] = [prim['center'][0] + dx * delta,
                              prim['center'][1] + dy * delta]
            prim['p0'] = [prim['p0'][0] + dx * delta, prim['p0'][1] + dy * delta]
            prim['p1'] = [prim['p1'][0] + dx * delta, prim['p1'][1] + dy * delta]
        out.append(prim)
    return out


def main():
    payload = json.loads((RUN / 'routes_l3d.json').read_text(encoding='utf-8'))
    routes = payload['routes']
    by_id = {int(r['route_id']): r for r in routes}
    route = json.loads(json.dumps(by_id[743]))
    body = [p for p in route['parts'] if p['kind'] == 'flat'
            and abs(float(p['z_mm']) - 0.175) < 1e-9 and p.get('tag') == 'body'][0]
    prims = body['primitives']
    print('body prims:')
    for k, p in enumerate(prims):
        print(' ', k, p['kind'], p.get('p0'), p.get('p1'),
              None if p['kind'] == 'line' else p.get('center'))
    # +11 mm on prim 2 (west), -11 mm on prim 6 (west)
    prims = shift_downstream(prims, 2, 11.0, (-1.0, 0.0))
    prims = shift_downstream(prims, 6, -11.0, (-1.0, 0.0))
    # re-derive lengths
    for p in prims:
        if p['kind'] == 'line':
            p['length'] = math.dist(p['p0'], p['p1'])
        else:
            p['length'] = abs(p['radius'] * p['sweep'])
    body['primitives'] = prims
    body['length_mm'] = sum(p['length'] for p in prims)
    print('end of body after edit:', prims[-1]['p1'])

    # --- rebuild the world with the new route and audit 743 against everything
    routes_new = [json.loads(json.dumps(r)) for r in routes]
    for r in routes_new:
        if int(r['route_id']) == 743:
            r['parts'] = route['parts']
    curves = IM.build_curves(routes_new)
    first, second, _stats = IM.build_candidate_pairs(curves)
    chains = IM.build_height_chains(routes_new)
    result = IM.same_layer_audit(curves, routes_new, chains, first, second,
                                 log=lambda *_a: None)
    print('same_layer events=%d illegal=%d pairs=%d min_non_cross=%s'
          % (result['event_count'], result['illegal_event_count'],
             result['crossing_pair_count'],
             result['min_non_crossing_centerline_mm']))
    mine = [e for e in result['events'] if 743 in (e['route_a'], e['route_b'])]
    print('crossings involving 743: %d' % len(mine))
    for event in sorted(mine, key=lambda e: e['angle_deg']):
        print('   z=%.3f  %d-%d  angle=%.4f  at (%.4f, %.4f)'
              % (event['height_mm'], event['route_a'], event['route_b'],
                 event['angle_deg'], event['x_mm'], event['y_mm']))
    for event in result['illegal_events']:
        if 743 in (event['route_a'], event['route_b']):
            print('   ILLEGAL', event)
    for key in ('flat_flat_cross_height', 'transition_flat_3d',
                'transition_transition_3d'):
        pass
    ff = IM.flat_flat_3d(curves, first, second)
    print('flat-flat 3d min=%s viol=%d' % (ff['min_distance_mm'],
                                           ff['violation_count']))
    tf = IM.transition_flat_3d(curves, first, second)
    print('transition-flat 3d min=%s viol=%d' % (tf['min_distance_mm'],
                                                 tf['violation_count']))
    tt = IM.transition_transition_3d(curves, first, second)
    print('transition-transition 3d min=%s viol=%d'
          % (tt['min_distance_mm'], tt['violation_count']))
    for v in (ff['violations'] + tf['violations'] + tt['violations']):
        if 743 in (v['route_a'], v['route_b']):
            print('   3D VIOLATION', v)


if __name__ == '__main__':
    main()
