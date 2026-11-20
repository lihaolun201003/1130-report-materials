# -*- coding: utf-8 -*-
"""Near-miss refinement pass on top of Phase-2 F.

The independent D0 blocker analysis shows that a large set of high-gain
excursion candidates are rejected only by the production guard's sampling /
accept margin (all true 3D distances are already >= 50 um, but < the guard's
conservative accept threshold).  This module re-searches those candidates with
small interval shifts (and adjacent target heights) so that the two R15 S-curves
move away from the near-miss obstacles and the exact conservative guard passes.
Accepted only on a strictly lower exact global crossing count.
"""
from __future__ import annotations

import argparse
import copy
import json
import time

from ...fsd25d import path3d as P
from . import common as N
from . import guard as G
from . import joint_reroute as J
from . import phase2 as P2
from . import route_model as RM
from . import single_route as S


def load_near_miss_candidates():
    path = P2.RUN2 / 'analysis' / 'blocker_analysis.json'
    if not path.is_file():
        return {}
    payload = P2.load_json(path)
    groups = {}
    for entry in payload.get('candidate_results') or ():
        if not entry.get('build_ok') or entry.get('structure_errors'):
            continue
        if entry.get('hard_blockers') or entry.get('manual_blockers'):
            continue
        if int(entry.get('estimated_net') or 0) < 3:
            continue
        if entry.get('route_modified_in_native'):
            continue
        if entry.get('route_direct'):
            continue
        rid = int(entry['route_id'])
        groups.setdefault(rid, []).append(dict(
            route_id=rid, target_z=float(entry['target_z']),
            target_plane=int(entry['target_plane_id']),
            s_start_mm=float(entry['s_start_mm']),
            s_end_mm=float(entry['s_end_mm']),
            estimated_net=int(entry['estimated_net']),
            estimated_removed=int(entry.get('estimated_removed') or 0),
            estimated_added=int(entry.get('estimated_added') or 0),
            near_miss=len(entry.get('near_miss_blockers') or [])))
    for rid in groups:
        groups[rid].sort(key=lambda item: -item['estimated_net'])
        groups[rid] = groups[rid][:4]
    return groups


SHIFTS = (0.0, 0.4, -0.4, 1.0, -1.0, 2.0, -2.0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--routes', type=int, default=250)
    parser.add_argument('--time-budget', type=float, default=300.0)
    parser.add_argument('--max-accept', type=int, default=25)
    args = parser.parse_args(argv)
    P2.ensure_dirs()
    log = lambda message: print(time.strftime('%H:%M:%S') + ' [near] '
                               + str(message), flush=True)
    best_dir = P2.RUN2 / 'best_valid'
    payload = P2.load_json(best_dir / 'routes_l3d.json')
    routes = {int(route['route_id']): route for route in payload['routes']}
    env, bbox = J.make_env(routes, log=log)
    rows, _ = N.load_assignment()
    manual = {int(row['route_id']) for row in rows
              if str(row.get('manual_group') or '').strip()}
    start_total = int(env.total())
    groups = load_near_miss_candidates()
    log('near-miss candidate routes: %d, start total=%d'
        % (len(groups), start_total))
    order = sorted(groups, key=lambda rid: -max(c['estimated_net']
                                                for c in groups[rid]))
    deadline = time.time() + float(args.time_budget)
    improved = []
    attempts = 0
    for route_id in order[:int(args.routes)]:
        if time.time() > deadline or len(improved) >= int(args.max_accept):
            break
        if route_id not in env.routes or route_id in manual:
            continue
        route = env.routes[route_id]
        if int(route.get('n_mid_transitions') or 0) > 0:
            continue
        try:
            body_index, prims = S.route_body_chain(route)
        except Exception:  # noqa: BLE001
            continue
        total_length = float(P.path_length(prims))
        best = None
        for candidate in groups[route_id]:
            target_z = candidate['target_z']
            for shift0 in SHIFTS:
                for shift1 in SHIFTS:
                    if shift0 == 0.0 and shift1 == 0.0:
                        continue
                    s0 = candidate['s_start_mm'] + shift0
                    s1 = candidate['s_end_mm'] + shift1
                    if s0 < 0.5 or s1 > total_length - 0.5 or s1 - s0 < 4.0:
                        continue
                    attempts += 1
                    if attempts % 400 == 0 and time.time() > deadline:
                        break
                    try:
                        built = RM.duck_out(route, body_index, s0, s1,
                                            target_z)
                    except ValueError:
                        continue
                    cand = built['route']
                    if RM.structure_errors(cand):
                        continue
                    fast = env.evaluate_candidate(route_id, cand)
                    if not fast['d56_ok'] or int(fast['delta']) >= 0:
                        continue
                    guard = G.candidate_guard(env, cand, bbox_cache=bbox)
                    if not guard['ok']:
                        continue
                    if best is None or int(fast['delta']) < best['delta']:
                        best = dict(candidate=cand, delta=int(fast['delta']),
                                    target_z=target_z, s0=s0, s1=s1,
                                    predicted=candidate['estimated_net'])
        if best is None:
            continue
        before = int(env.total())
        env.replace_route(best['candidate'])
        bbox.update(best['candidate'])
        after = int(env.total())
        if after < before:
            improved.append(dict(route_id=int(route_id),
                                 target_z=best['target_z'],
                                 net=after - before,
                                 predicted=best['predicted'],
                                 s0=round(best['s0'], 3),
                                 s1=round(best['s1'], 3)))
            log('ACCEPT route %d z=%.3f net=%+d (predicted %+d) total=%d'
                % (route_id, best['target_z'], after - before,
                   best['predicted'], after))
        else:
            env.replace_route(route)
            bbox.update(route)
    final_total = int(env.total())
    log('near-miss refinement: attempts=%d accepted=%d total %d -> %d'
        % (attempts, len(improved), start_total, final_total))
    result = dict(schema='native3d_phase2_near_miss_v1',
                  start_total=start_total, final_total=final_total,
                  attempts=attempts, accepted=len(improved),
                  net=sum(row['net'] for row in improved),
                  improvements=improved)
    P2.write_json(P2.RUN2 / 'experiment_F' / 'near_miss_results.json', result)
    if final_total < start_total:
        routes_dict = {rid: route for rid, route in env.routes.items()}
        validation = P2.validate(routes_dict, log=log)
        P2.write_json(P2.RUN2 / 'experiment_F' / 'validation_near_miss.json',
                      validation)
        if validation['validation_pass']:
            P2.save_experiment(env.routes, 'experiment_F', log=log,
                               note='F + near-miss interval refinement')
            P2.save_best_valid(routes_dict, validation, log=log,
                               tag='best_valid')
            log('saved improved layout: %d -> %d' % (start_total, final_total))
    return result


if __name__ == '__main__':
    main()
