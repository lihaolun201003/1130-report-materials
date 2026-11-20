# -*- coding: utf-8 -*-
"""Extra F sweep: stronger plain-excursion engine on the current best layout.

Reuses the Phase-1 batch-avoid planner (multi-cluster greedy + exact guards) on
the Phase-2 2436 layout to squeeze the remaining straight-run gains before the
final Phase-2 deliverable is frozen.
"""
from __future__ import annotations

import argparse
import copy
import time
from collections import Counter

from . import batch_avoid as BA
from . import common as N
from . import crossing_cache as CC
from . import guard as G
from . import joint_reroute as J
from . import phase2 as P2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--time-budget', type=float, default=210.0)
    parser.add_argument('--max-sweeps', type=int, default=1)
    args = parser.parse_args(argv)
    P2.ensure_dirs()
    log = lambda message: print(time.strftime('%H:%M:%S') + ' [F+] '
                               + str(message), flush=True)
    best_dir = P2.RUN2 / 'best_valid'
    payload = P2.load_json(best_dir / 'routes_l3d.json')
    routes = {int(route['route_id']): route for route in payload['routes']}
    env, bbox = J.make_env(routes, log=log)
    rows, _ = N.load_assignment()
    manual = {int(row['route_id']) for row in rows
              if str(row.get('manual_group') or '').strip()}
    start_total = int(env.total())
    log('start %d crossings' % start_total)
    deadline = time.time() + float(args.time_budget)
    history = []
    for sweep in range(1, int(args.max_sweeps) + 1):
        if time.time() > deadline:
            break
        events = env.cache.crossing_events()
        counter = Counter()
        for event in events:
            counter[int(event['route_a'])] += 1
            counter[int(event['route_b'])] += 1
        order = sorted([rid for rid in env.routes if rid not in manual
                        and counter.get(rid, 0) > 0],
                       key=lambda rid: -counter.get(rid, 0))
        sweep_start = int(env.total())
        accepted = 0
        for route_id in order:
            if time.time() > deadline:
                break
            before_total = int(env.total())
            try:
                plan = BA.route_plan(env, route_id, events,
                                     strategy='B4_multi_excursion',
                                     max_excursions=2, bbox_cache=bbox)
            except Exception as error:  # noqa: BLE001
                log('plan error route %d: %r' % (route_id, error))
                continue
            if plan.get('new_route') is None or int(
                    plan.get('predicted_delta') or 0) >= 0:
                continue
            previous = copy.deepcopy(env.routes[route_id])
            try:
                env.replace_route(plan['new_route'])
                bbox.update(plan['new_route'])
            except Exception as error:  # noqa: BLE001
                log('replace error route %d: %r' % (route_id, error))
                continue
            after_total = int(env.total())
            if after_total < before_total:
                accepted += 1
                history.append(dict(stage='plain_batch', sweep=sweep,
                                    route_id=int(route_id),
                                    delta=int(after_total - before_total),
                                    total=int(after_total)))
                log('ACCEPT route %d net=%+d total=%d'
                    % (route_id, after_total - before_total, after_total))
            else:
                env.replace_route(previous)
                bbox.update(previous)
        log('sweep %d: %d accepted, total %d -> %d'
            % (sweep, accepted, sweep_start, int(env.total())))
        if int(env.total()) >= sweep_start:
            break
    final_total = int(env.total())
    if final_total < start_total:
        routes_dict = {rid: route for rid, route in env.routes.items()}
        validation = P2.validate(routes_dict, log=log)
        P2.write_json(P2.RUN2 / 'experiment_F' / 'validation_extra.json',
                      validation)
        if validation['validation_pass']:
            P2.save_experiment(env.routes, 'experiment_F', log=log,
                               note='extra plain-batch sweep on top of F')
            P2.save_best_valid(routes_dict, validation, log=log,
                               tag='best_valid')
            P2.write_json(P2.RUN2 / 'experiment_F' / 'extra_sweep.json',
                          dict(start=start_total, final=final_total,
                               history=history, validation=validation))
            log('extra sweep improved %d -> %d' % (start_total, final_total))
    else:
        log('extra sweep: no improvement')
    return final_total


if __name__ == '__main__':
    main()
