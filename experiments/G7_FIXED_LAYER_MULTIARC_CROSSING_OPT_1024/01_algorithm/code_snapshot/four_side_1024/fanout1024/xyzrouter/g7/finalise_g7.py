# -*- coding: utf-8 -*-
"""G7 dual acceptance: frozen-structure verifier + Validator A + Validator B.

Runs, in order:

1. the G6 dual-acceptance driver (unchanged frozen project Validator A and the
   independent 45 deg Validator B) on the candidate payload;
2. the G7 fixed-structure verifier against the frozen G6 reference;
3. writes ``g7_validation_verdict.json`` with the combined
   ``G7_FIXED_LAYER_VALID_PASS`` flag (A pass AND B pass AND fixed pass AND
   crossing count strictly below the G6 baseline).

Usage::

    python -m ...g7.finalise_g7 \
        --routes <G7 best_routes.json> \
        --reference <G6 routes_l3d.json> \
        --companions <G6 03_best_feasible dir> \
        --out experiments/G7.../03_best_valid
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

from . import frozen as FR
from . import verify_fixed as VF


def _project_root():
    path = os.path.abspath(__file__)
    for _ in range(5):
        path = os.path.dirname(path)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--routes', required=True)
    parser.add_argument('--reference', required=True,
                        help='frozen G6 routes_l3d.json')
    parser.add_argument('--companions', required=True,
                        help='dir with assignment_1024.csv / layer JSONs')
    parser.add_argument('--out', required=True)
    parser.add_argument('--baseline-crossings', type=int, default=4578)
    parser.add_argument('--run-fixed', action='store_true', default=True)
    args = parser.parse_args(argv)
    root = _project_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)

    # 1) copy payload + companions into a clean run dir, then G5 dual validator
    from four_side_1024.fanout1024.xyzrouter.g6 import finalise as G6F
    g5_driver = os.path.join(root, 'experiments',
                             'G5_ANGLE45_NATIVE3D_20H_1024', '01_algorithm',
                             'run_validation.py')
    payload_dir = out
    routes_path, missing = G6F.prepare_payload(args.routes, args.companions,
                                               payload_dir)
    validation_dir = os.path.join(out, 'validation')
    result = G6F.run_dual_validation(g5_driver, payload_dir, validation_dir)
    verdict, verdict_path = G6F.mirror_verdict(result['verdict'], out)

    # 2) fixed-structure verification against the frozen G6 reference
    fixed = dict(passed=False, violation_count=None)
    if args.run_fixed:
        fixed_out = os.path.join(out, 'validation', 'fixed')
        os.makedirs(fixed_out, exist_ok=True)
        manifest_path = os.path.join(out, 'frozen_manifest.json')
        with open(args.reference, encoding='utf-8') as handle:
            reference = json.load(handle)
        manifest = FR.build_manifest(reference['routes'])
        FR.write_manifest(manifest_path, manifest)
        command = [sys.executable, '-m',
                   'four_side_1024.fanout1024.xyzrouter.g7.verify_fixed',
                   '--reference', os.path.abspath(args.reference),
                   '--candidate', routes_path,
                   '--out', fixed_out, '--manifest', manifest_path]
        env = dict(os.environ)
        env['PYTHONPATH'] = root
        log_path = os.path.join(fixed_out, 'verify.log')
        with open(log_path, 'w', encoding='utf-8') as handle:
            process = subprocess.run(command, stdout=handle,
                                     stderr=subprocess.STDOUT, env=env,
                                     cwd=root, timeout=1800)
        report_path = os.path.join(fixed_out,
                                   'fixed_structure_verification.json')
        if os.path.exists(report_path):
            with open(report_path, encoding='utf-8') as handle:
                fixed = json.load(handle)
        fixed['exit_code'] = process.returncode
        fixed['log'] = log_path

    # 3) crossing count from the independent angle validator JSON
    independent = verdict.get('B_independent_angle_validator') or {}
    crossings = independent.get('crossings')
    g6 = load_json(os.path.join(args.companions, 'BEST_VALID.json')) or {}
    combined = dict(
        schema='g7_validation_verdict_v1',
        candidate=os.path.abspath(args.routes),
        reference=os.path.abspath(args.reference),
        candidate_sha256=VF._sha256(routes_path),
        A_pass=verdict.get('A_pass'),
        B_pass=verdict.get('B_pass'),
        fixed_structure_pass=bool(fixed.get('pass')),
        crossings=crossings,
        unique_pairs=independent.get('pairs'),
        min_angle_deg=independent.get('min_angle_deg'),
        sub45=int(independent.get('violations') or 0),
        baseline_crossings=int(args.baseline_crossings),
        strictly_better=bool(crossings is not None and
                             int(crossings) < int(args.baseline_crossings)),
        G6_ANGLE45_VALID_PASS=verdict.get('G6_ANGLE45_VALID_PASS'),
        G6_payload_sha256=g6.get('routes_sha256'),
        fixed_structure=fixed,
        generated_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
    )
    combined['G7_FIXED_LAYER_VALID_PASS'] = bool(
        combined['A_pass'] and combined['B_pass']
        and combined['fixed_structure_pass'] and combined['strictly_better'])
    path = os.path.join(out, 'g7_validation_verdict.json')
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(combined, handle, indent=1, ensure_ascii=False)
    print(json.dumps({key: combined[key] for key in
                      ('A_pass', 'B_pass', 'fixed_structure_pass',
                       'crossings', 'baseline_crossings', 'strictly_better',
                       'G7_FIXED_LAYER_VALID_PASS')}, ensure_ascii=False))
    return 0 if combined['G7_FIXED_LAYER_VALID_PASS'] else 2


def load_json(path):
    try:
        with open(path, encoding='utf-8') as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


if __name__ == '__main__':
    raise SystemExit(main())
