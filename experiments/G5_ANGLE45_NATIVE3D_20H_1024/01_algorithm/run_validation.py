# -*- coding: utf-8 -*-
"""G5 acceptance: frozen project validator (A) + independent 45 deg validator (B).

A. the frozen 20-height project validator ``xyzrouter.validate_xyz`` is run on the
   G5 payload with the *unchanged* geometric contract (D56, R15, 50 um true 3-D
   clearance, glass, ports, assignment).  It is the same code that produced the
   frozen G4 verdict.
B. the independent, from-scratch ``g5.validate_g5_angle`` recomputes every true
   same-height crossing from the exact primitives and checks theta >= 45 deg.

Both must PASS before a run may be called ``G5_ANGLE45_VALID_PASS``.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXP = ROOT / 'experiments' / 'G5_ANGLE45_NATIVE3D_20H_1024'
BASELINE = (ROOT / 'experiments' / 'COLD_START_20_HEIGHT_1024' / '07_g123'
            / 'run_xyz_joint_1024_20h' / 'baseline_authoritative')
PAYLOAD = ('routes_l3d.json', 'assignment_1024.csv', 'layer_planes.json',
           'physical_layer_stack.json', 'process_rules.json',
           'crossing_stats.json', 'validation.json', 'BEST_VALID.json',
           'SHA256.json')

FROZEN_VALIDATOR = r'''
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


def run(command, log_path, timeout=3600):
    started = time.time()
    with Path(log_path).open('w', encoding='utf-8') as handle:
        process = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT,
                                 cwd=str(ROOT), timeout=timeout)
    return dict(exit_code=process.returncode,
                seconds=round(time.time() - started, 1), log=str(log_path))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True,
                        help='directory holding the G5 payload to validate')
    parser.add_argument('--out', default=str(EXP / '04_validation'))
    parser.add_argument('--skip-frozen', action='store_true')
    args = parser.parse_args(argv)
    source = Path(args.source)
    out = Path(args.out)
    run_dir = out / 'run_dir'
    run_dir.mkdir(parents=True, exist_ok=True)
    for name in PAYLOAD:
        candidate = source / name
        if candidate.exists():
            shutil.copy2(candidate, run_dir / name)
    missing = [name for name in PAYLOAD if not (run_dir / name).exists()]
    print('[payload] copied, missing=%s' % missing, flush=True)

    verdict = dict(schema='g5_acceptance_v1', source=str(source),
                   run_dir=str(run_dir), missing_payload=missing)

    # ---------------------------------------------------------- A: frozen
    required_a = ('routes_l3d.json', 'assignment_1024.csv', 'layer_planes.json')
    frozen = dict(skipped=True)
    if not args.skip_frozen and not [n for n in missing if n in required_a]:
        log_a = out / 'logs' / 'frozen_validator.log'
        log_a.parent.mkdir(parents=True, exist_ok=True)
        frozen = run([python(), '-c', FROZEN_VALIDATOR, str(run_dir),
                      str(out / 'frozen'), str(BASELINE)], log_a)
        report_path = out / 'frozen' / 'validation.json'
        if report_path.exists():
            report = json.loads(report_path.read_text(encoding='utf-8'))
            frozen.update(
                validation_pass=bool(report.get('validation_pass')),
                geometry_pass=bool(report.get('geometry_pass')),
                contract_pass=bool(report.get('contract_pass')),
                violation_count=int(report.get('violation_count') or 0),
                counts=report.get('counts'),
                min_3d_clearance_mm=report.get('min_3d_clearance_mm'),
                violation_counts_by_check=report.get('violation_counts_by_check'))
        else:
            frozen.update(validation_pass=False, violation_count=None,
                          report_missing=str(report_path))
    verdict['A_frozen_project_validator'] = frozen
    print('[A] %s' % json.dumps(frozen, ensure_ascii=False)[:600], flush=True)

    # ------------------------------------------------- B: independent angle
    log_b = out / 'logs' / 'independent_angle_validator.log'
    log_b.parent.mkdir(parents=True, exist_ok=True)
    independent = run([python(),
                       str(ROOT / 'four_side_1024' / 'fanout1024' / 'xyzrouter'
                           / 'g5' / 'validate_g5_angle.py'),
                       '--run-dir', str(run_dir),
                       '--out-dir', str(out / 'independent'),
                       '--theta-min', '45.0'], log_b)
    report_path = out / 'independent' / 'g5_angle_validation.json'
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding='utf-8'))
        summary = report.get('summary') or report
        independent.update(
            pass_45=bool(summary.get('verdict_pass_45',
                                     summary.get('pass_45'))),
            crossings=summary.get('total_crossings'),
            violations=summary.get('n_lt_theta_min'),
            min_angle_deg=summary.get('min_angle_deg'),
            deficit_deg=summary.get('D_theta_deg'),
            pairs=summary.get('unique_route_pairs'),
            clearance_violations=summary.get('clearance_violation_count'),
            min_non_crossing_mm=summary.get('clearance_min_non_crossing_mm'))
    else:
        independent.update(pass_45=False,
                           report_missing=str(report_path))
    verdict['B_independent_angle_validator'] = independent
    print('[B] %s' % json.dumps(independent, ensure_ascii=False)[:600], flush=True)

    ok_a = bool(frozen.get('validation_pass')) and not frozen.get(
        'violation_count')
    ok_b = bool(independent.get('pass_45'))
    verdict['G5_ANGLE45_VALID_PASS'] = bool(ok_a and ok_b)
    verdict['A_pass'] = ok_a
    verdict['B_pass'] = ok_b
    (out / 'g5_validation_verdict.json').write_text(
        json.dumps(verdict, indent=1, ensure_ascii=False), encoding='utf-8')
    print('[verdict] A=%s B=%s => %s' % (ok_a, ok_b,
                                         verdict['G5_ANGLE45_VALID_PASS']))
    return 0 if verdict['G5_ANGLE45_VALID_PASS'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
