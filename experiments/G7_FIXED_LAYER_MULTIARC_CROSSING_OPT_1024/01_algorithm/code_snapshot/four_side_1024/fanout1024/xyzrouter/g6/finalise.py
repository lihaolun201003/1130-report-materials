# -*- coding: utf-8 -*-
"""G6 finalise + dual independent acceptance.

Takes an SA output payload (``best_routes.json`` or any ``routes_l3d.json``),
copies it with the frozen companion files into a clean payload directory, then
runs the **unchanged** G5 dual-acceptance driver:

* Validator A -- the frozen 20-height project validator
  (``xyzrouter.validate_xyz`` with the 20-height bootstrap, manual policy
  ``fully_optimizable``);
* Validator B -- the from-scratch, standard-library-only 45 deg validator
  (``g5/validate_g5_angle.py``).

Both must pass for ``G6_ANGLE45_VALID_PASS``.  The G5 verdict file is kept
verbatim and mirrored into ``g6_validation_verdict.json`` with the G6 names.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

COMPANIONS = ('assignment_1024.csv', 'layer_planes.json',
              'physical_layer_stack.json', 'process_rules.json')


def _project_root():
    path = os.path.abspath(__file__)
    for _ in range(5):        # file -> g6 -> xyzrouter -> fanout1024 -> four_side_1024
        path = os.path.dirname(path)
    return path


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_payload(routes_path, companions_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    routes_target = os.path.join(out_dir, 'routes_l3d.json')
    shutil.copyfile(os.path.abspath(routes_path), routes_target)
    missing = []
    for name in COMPANIONS:
        source = os.path.join(os.path.abspath(companions_dir), name)
        if os.path.exists(source):
            shutil.copyfile(source, os.path.join(out_dir, name))
        else:
            missing.append(name)
    return routes_target, missing


def run_dual_validation(g5_driver, payload_dir, validation_dir):
    os.makedirs(validation_dir, exist_ok=True)
    log_path = os.path.join(validation_dir, 'logs', 'dual_validation.log')
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    command = [sys.executable, os.path.abspath(g5_driver),
               '--source', os.path.abspath(payload_dir),
               '--out', os.path.abspath(validation_dir)]
    started = time.time()
    with open(log_path, 'w', encoding='utf-8') as handle:
        process = subprocess.run(command, stdout=handle,
                                 stderr=subprocess.STDOUT,
                                 cwd=_project_root(), timeout=3600)
    verdict_path = os.path.join(validation_dir, 'g5_validation_verdict.json')
    verdict = {}
    if os.path.exists(verdict_path):
        with open(verdict_path, encoding='utf-8') as handle:
            verdict = json.load(handle)
    return dict(exit_code=process.returncode,
                seconds=round(time.time() - started, 2),
                log=log_path, verdict=verdict)


def mirror_verdict(verdict, out_dir):
    """Mirror the G5 verdict into the G6 naming without touching its content."""
    result = dict(verdict)
    result['G6_ANGLE45_VALID_PASS'] = bool(
        verdict.get('G5_ANGLE45_VALID_PASS'))
    result['G6_dual_acceptance'] = dict(
        A_frozen_project_validator=verdict.get(
            'A_frozen_project_validator'),
        B_independent_angle_validator=verdict.get(
            'B_independent_angle_validator'))
    path = os.path.join(out_dir, 'g6_validation_verdict.json')
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(result, handle, indent=1, ensure_ascii=False)
    return result, path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--routes', required=True,
                        help='routes payload (best_routes.json / routes_l3d.json)')
    parser.add_argument('--companions', required=True,
                        help='directory with assignment_1024.csv + layer/process '
                             'JSONs (e.g. the frozen G5 best_partial_v5 dir)')
    parser.add_argument('--out', required=True,
                        help='deliverable directory (payload + verdict)')
    parser.add_argument('--g5-driver', default=None,
                        help='path to the G5 run_validation.py driver')
    parser.add_argument('--skip-validation', action='store_true')
    parser.add_argument('--label', default='G6')
    args = parser.parse_args(argv)

    root = _project_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    out_dir = os.path.abspath(args.out)
    payload_dir = out_dir
    routes_path, missing = prepare_payload(args.routes, args.companions,
                                           payload_dir)
    with open(routes_path, encoding='utf-8') as handle:
        doc = json.load(handle)
    meta = dict(
        schema='g6_best_payload_v1', label=args.label,
        routes_file=routes_path, routes_sha256=_sha256(routes_path),
        route_count=len(doc.get('routes') or ()),
        routed=doc.get('routed'), failed=doc.get('failed'),
        source=os.path.abspath(args.routes),
        missing_companions=missing,
        created_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
        g6=doc.get('g6'))
    with open(os.path.join(out_dir, 'BEST_VALID.json'), 'w',
              encoding='utf-8') as handle:
        json.dump(meta, handle, indent=1, ensure_ascii=False)
    with open(os.path.join(out_dir, 'SHA256.json'), 'w',
              encoding='utf-8') as handle:
        json.dump({name: _sha256(os.path.join(payload_dir, name))
                   for name in ('routes_l3d.json',) + COMPANIONS
                   if os.path.exists(os.path.join(payload_dir, name))},
                  handle, indent=1)
    print('[g6-finalise] payload=%s sha256=%s missing=%s'
          % (routes_path, meta['routes_sha256'], missing), flush=True)
    if args.skip_validation:
        return 0
    g5_driver = args.g5_driver or os.path.join(
        root, 'experiments', 'G5_ANGLE45_NATIVE3D_20H_1024', '01_algorithm',
        'run_validation.py')
    validation_dir = os.path.join(out_dir, 'validation')
    result = run_dual_validation(g5_driver, payload_dir, validation_dir)
    verdict, verdict_path = mirror_verdict(result['verdict'], out_dir)
    summary = dict(
        schema='g6_finalise_v1', label=args.label,
        routes_sha256=meta['routes_sha256'],
        validation_exit_code=result['exit_code'],
        validation_seconds=result['seconds'],
        A_frozen_project_validator=verdict.get(
            'A_frozen_project_validator'),
        B_independent_angle_validator=verdict.get(
            'B_independent_angle_validator'),
        A_pass=verdict.get('A_pass'),
        B_pass=verdict.get('B_pass'),
        G6_ANGLE45_VALID_PASS=verdict.get('G6_ANGLE45_VALID_PASS'),
        verdict_file=verdict_path,
    )
    with open(os.path.join(out_dir, 'g6_finalise_summary.json'), 'w',
              encoding='utf-8') as handle:
        json.dump(summary, handle, indent=1, ensure_ascii=False)
    print('[g6-finalise] ' + json.dumps(
        {key: summary[key] for key in ('A_pass', 'B_pass',
                                       'G6_ANGLE45_VALID_PASS')},
        ensure_ascii=False), flush=True)
    return 0 if summary['G6_ANGLE45_VALID_PASS'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
