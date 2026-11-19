# -*- coding: utf-8 -*-
"""Make the G5 result satisfy the *frozen* project validator again.

The G5 search only accepts moves that its own exact re-check declares legal, but
the frozen validator's D56 index is a second, independent implementation with a
few stricter corners (transition-vs-flat clearance margin, native excursion
metadata bookkeeping after a second excursion on the same route, interface-plane
excursions).  Rather than argue with it, this script reverts the offending routes
to their frozen geometry and re-validates until the frozen validator passes.

Reversion is monotone in the original contract: the frozen geometry is legal, so
reverting a route can only remove violations of the *old* constraints.  The G5
angle objective is re-counted afterwards, so the price paid is reported exactly.
"""
from __future__ import annotations

import argparse
import copy
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024.xyzrouter.g5 import model as G5

EXP = ROOT / 'experiments' / 'G5_ANGLE45_NATIVE3D_20H_1024'
FROZEN = ROOT / 'experiments' / 'COLD_START_20_HEIGHT_1024' / '10_best_valid'
BASELINE_DIR = (ROOT / 'experiments' / 'COLD_START_20_HEIGHT_1024' / '07_g123'
                / 'run_xyz_joint_1024_20h' / 'baseline_authoritative')
PAYLOAD = ('assignment_1024.csv', 'layer_planes.json',
           'physical_layer_stack.json', 'process_rules.json')
VALIDATOR = r'''
import json, sys
from four_side_1024.fanout1024.coldstart20 import bootstrap as B
B.assert_20_height_profile('g5')
from four_side_1024.fanout1024.xyzrouter import validate_xyz as V
sys.exit(V.main(['--run-dir', sys.argv[1], '--out-dir', sys.argv[2],
                 '--baseline-dir', sys.argv[3],
                 '--manual-policy', 'fully_optimizable']))
'''


def python():
    return str(ROOT / '.venv' / 'Scripts' / 'python.exe')


def write_payload(directory, routes, base):
    directory.mkdir(parents=True, exist_ok=True)
    for name in PAYLOAD:
        source = FROZEN / name
        if source.exists():
            shutil.copy2(source, directory / name)
    payload = copy.deepcopy(base)
    payload['routes'] = routes
    payload['routed'] = len(routes)
    payload['failed'] = 0
    (directory / 'routes_l3d.json').write_text(
        json.dumps(payload, ensure_ascii=False), encoding='utf-8')


def validate(directory, out_dir):
    log = out_dir.parent / 'logs' / ('cleanup_%s.log' % directory.name)
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    with log.open('w', encoding='utf-8') as handle:
        process = subprocess.run([python(), '-c', VALIDATOR, str(directory),
                                  str(out_dir), str(BASELINE_DIR)],
                                 stdout=handle, stderr=subprocess.STDOUT,
                                 cwd=str(ROOT))
    report_path = out_dir / 'validation.json'
    report = {}
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding='utf-8'))
    return dict(exit_code=process.returncode,
                seconds=round(time.time() - started, 1),
                violation_count=int(report.get('violation_count') or 0),
                validation_pass=bool(report.get('validation_pass')),
                geometry_pass=bool(report.get('geometry_pass')),
                contract_pass=bool(report.get('contract_pass')),
                kinds=report.get('violation_counts_by_check'),
                offending=sorted(set(int(x) for x in
                                     (report.get('offending_route_ids') or []))
                                 | {int(v['route_id']) for v in
                                    (report.get('violations') or [])
                                    if v.get('route_id') is not None}
                                 | {int(v['other_route']) for v in
                                    (report.get('violations') or [])
                                    if v.get('other_route') is not None}),
                report=str(report_path))


def audit(routes, log=print):
    world = G5.World(routes, min_angle_deg=45.0)
    result = world.audit_all(min_angle_deg=45.0)
    violations = result['violations']
    summary = dict(crossings=len(result['crossings']),
                   violations=len(violations),
                   min_angle_deg=(round(min(e['angle_deg']
                                            for e in result['crossings']), 6)
                                  if result['crossings'] else None),
                   deficit_deg=round(sum(45.0 - e['angle_deg']
                                         for e in violations), 6),
                   max_deficit_deg=round(max([45.0 - e['angle_deg']
                                              for e in violations] or [0.0]), 6),
                   hard_issues=len(result['issues']))
    log('[audit] %s' % summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True,
                        help='G5 result dir (routes_l3d.json) to clean')
    parser.add_argument('--out', default=str(EXP / '03_best_partial'))
    parser.add_argument('--rounds', type=int, default=5)
    args = parser.parse_args(argv)
    out = Path(args.out)
    work = Path(str(out) + '_cleanup')
    work.mkdir(parents=True, exist_ok=True)

    base_payload = json.loads((FROZEN / 'routes_l3d.json').read_text(
        encoding='utf-8'))
    frozen_routes = {int(r['route_id']): r for r in base_payload['routes']}
    source_file = Path(args.source)
    if source_file.is_dir():
        source_file = source_file / 'routes_l3d.json'
    g5_payload = json.loads(source_file.read_text(encoding='utf-8'))
    routes = {int(r['route_id']): r for r in g5_payload['routes']}
    log_lines = []

    def log(message):
        print(message, flush=True)
        log_lines.append(str(message))

    reverted = set()
    history = []
    for round_index in range(args.rounds):
        candidate = [routes[rid] for rid in sorted(routes)]
        directory = work / ('round_%d' % round_index)
        write_payload(directory, candidate, base_payload)
        verdict = validate(directory, work / ('validation_%d' % round_index))
        summary = audit(candidate, log)
        history.append(dict(round=round_index, validator=verdict,
                            audit=summary, reverted_total=len(reverted)))
        log('[round %d] validator passes=%s violations=%d kinds=%s '
            'offending=%d | audit %s'
            % (round_index, verdict['validation_pass'],
               verdict['violation_count'], verdict['kinds'],
               len(verdict['offending']), summary))
        if verdict['validation_pass']:
            break
        new = [rid for rid in verdict['offending'] if rid not in reverted]
        if not new:
            log('[round %d] no further offending route to revert' % round_index)
            break
        for rid in new:
            routes[rid] = copy.deepcopy(frozen_routes[rid])
            reverted.add(rid)
        log('[round %d] reverted %d routes to the frozen geometry: %s'
            % (round_index, len(new), new[:20]))

    final_routes = [routes[rid] for rid in sorted(routes)]
    out.mkdir(parents=True, exist_ok=True)
    payload = copy.deepcopy(base_payload)
    payload['routes'] = final_routes
    payload['g5'] = dict(schema='g5_angle45_routes_v1', theta_min_deg=45.0,
                         cleaned=True, reverted_routes=sorted(reverted),
                         cleanup_rounds=len(history))
    (out / 'routes_l3d.json').write_text(
        json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    for name in PAYLOAD:
        if (FROZEN / name).exists():
            shutil.copy2(FROZEN / name, out / name)
    (out / 'cleanup_report.json').write_text(
        json.dumps(dict(history=history, reverted_routes=sorted(reverted),
                        final_audit=history[-1]['audit'] if history else None),
                   indent=1, ensure_ascii=False), encoding='utf-8')
    (out / 'cleanup.log').write_text('\n'.join(log_lines), encoding='utf-8')
    log('[done] %s' % out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
