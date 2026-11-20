# -*- coding: utf-8 -*-
"""Select the best verified fixed-layer state across all G7 arms.

Reads every arm's seed summaries + the saved ``best_routes.json`` payloads,
re-audits each candidate with the authoritative strict-D56 audit (and the frozen
manifest), then copies the best *legal* payload to ``selected_best/``.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
EXP = os.path.abspath(os.path.join(HERE, '..'))
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)

from four_side_1024.fanout1024.xyzrouter.g7 import engine as EN  # noqa: E402
from four_side_1024.fanout1024.xyzrouter.g7 import frozen as FR  # noqa: E402
from four_side_1024.fanout1024.xyzrouter.g7 import sa as SA  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root', default=os.path.join(EXP, '02_sa_runs'))
    parser.add_argument('--reference', default=os.path.join(
        EXP, '00_frozen_g6', 'routes_l3d.json'))
    parser.add_argument('--out', default=os.path.join(EXP, '02_sa_runs',
                                                      'selected_best'))
    parser.add_argument('--include', default=None,
                        help='comma separated extra payload paths to consider')
    args = parser.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    with open(args.reference, encoding='utf-8') as handle:
        reference = json.load(handle)
    manifest = FR.build_manifest(reference['routes'])
    candidates = []
    for arm_dir in sorted(os.listdir(args.run_root)):
        arm_path = os.path.join(args.run_root, arm_dir)
        if not os.path.isdir(arm_path) or not (arm_dir.startswith('arm_')
                                                   or arm_dir.startswith('phase2_')):
            continue
        for name in sorted(os.listdir(arm_path)):
            seed_path = os.path.join(arm_path, name)
            payload = os.path.join(seed_path, 'best_routes.json')
            summary = os.path.join(seed_path, 'summary.json')
            if os.path.exists(payload) and os.path.exists(summary):
                candidates.append(dict(arm=arm_dir, seed=name.strip('seed_'),
                                       path=payload, summary=summary))
    for extra in (args.include or '').split(','):
        extra = extra.strip()
        if extra and os.path.exists(extra):
            candidates.append(dict(arm='extra', seed='0', path=extra,
                                   summary=None))
    rows = []
    for candidate in candidates:
        with open(candidate['path'], encoding='utf-8') as handle:
            payload = json.load(handle)
        fixed = FR.verify_payload(payload['routes'], manifest)
        engine_world = EN.PlaneWorld(payload['routes'], freeze=manifest)
        audit = engine_world.full_reaudit()
        sub45 = 0
        for events in engine_world.plane_events.values():
            for event in events.values():
                if event['angle_deg'] < 45.0:
                    sub45 += 1
        rows.append(dict(**candidate,
                         crossings=engine_world.total_crossings,
                         unique_pairs=engine_world.unique_pairs,
                         min_angle_deg=round(engine_world.min_angle() or 0.0, 9),
                         sub45=sub45,
                         fixed_pass=fixed['pass'],
                         fixed_violations=fixed['violation_count'],
                         audit_violations=audit['violations'],
                         length_mm=round(sum(float(part.get('length_mm') or 0.0) for route in payload['routes'] for part in route.get('parts') or ()), 6),
                         legal=bool(fixed['pass'] and sub45 == 0
                                    and audit['violations'] == 0)))
    legal = [row for row in rows if row['legal']]
    legal.sort(key=lambda row: (row['crossings'],
                                -row['min_angle_deg'], row['unique_pairs'],
                                row['length_mm']))
    payload = dict(schema='g7_selection_v1', generated_at=_stamp(),
                   considered=len(rows), legal=len(legal), rows=rows)
    with open(os.path.join(args.out, 'selection.json'), 'w',
              encoding='utf-8') as handle:
        json.dump(payload, handle, indent=1, ensure_ascii=False)
    if not legal:
        print('[select] NO legal candidate found')
        print(json.dumps(rows, ensure_ascii=False, indent=1)[:4000])
        return 2
    best = legal[0]
    shutil.copyfile(best['path'],
                    os.path.join(args.out, 'sa_best_routes.json'))
    with open(os.path.join(args.out, 'sa_best_meta.json'), 'w',
              encoding='utf-8') as handle:
        json.dump({key: value for key, value in best.items()
                   if key not in ('summary',)}, handle, indent=1,
                  ensure_ascii=False)
    print('[select] best %s/%s crossings=%d pairs=%d min=%.9f legal=%s'
          % (best['arm'], best['seed'], best['crossings'],
             best['unique_pairs'], best['min_angle_deg'], best['legal']))
    return 0


def _stamp():
    import time
    return time.strftime('%Y-%m-%dT%H:%M:%S')


if __name__ == '__main__':
    raise SystemExit(main())
