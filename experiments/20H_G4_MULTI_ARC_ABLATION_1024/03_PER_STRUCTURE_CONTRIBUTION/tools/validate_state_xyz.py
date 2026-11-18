# -*- coding: utf-8 -*-
"""Fresh-process 20H independent validator (``native3d.validate_native3d``).

The frozen G4 states are validated by ``xyzrouter.validate_xyz`` -- the same
validator the engine and the archived 20H chain use -- **not** by
``run_validate`` (which wraps the 21-height ``validate21`` contract checker and
therefore reports z-span/structure mismatches on a 20-height XYZ state).

The 20-height profile is installed *before* the validator module is imported,
so it sees the 20H plane table, while every geometric / D56 / clearance / port
check stays the frozen one.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024.coldstart20 import bootstrap as B  # noqa: E402
B.install()
B.assert_20_height_profile('validate_state_xyz')

from four_side_1024.fanout1024.xyzrouter import validate_xyz as VX  # noqa: E402


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    run_dir = None
    out_dir = None
    baseline = None
    manual = 'fully_optimizable'
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == '--run-dir':
            run_dir = argv[index + 1]
            index += 2
        elif token == '--out-dir':
            out_dir = argv[index + 1]
            index += 2
        elif token == '--baseline-dir':
            baseline = argv[index + 1]
            index += 2
        elif token == '--manual-policy':
            manual = argv[index + 1]
            index += 2
        else:
            index += 1
    if not run_dir:
        print('usage: validate_state_xyz.py --run-dir DIR --out-dir DIR '
              '[--baseline-dir DIR] [--manual-policy NAME]', file=sys.stderr)
        return 2
    out_dir = out_dir or run_dir
    report = VX.validate_xyz(
        run_dir=Path(run_dir),
        baseline_dir=(Path(baseline) if baseline else None),
        out_dir=Path(out_dir),
        manual_policy=manual, log=print)
    summary = dict(
        schema='coldstart20_validate_state_xyz_v1',
        run_dir=str(run_dir), out_dir=str(out_dir),
        validation_pass=report.get('validation_pass'),
        geometry_pass=report.get('geometry_pass'),
        contract_pass=report.get('contract_pass'),
        violation_count=report.get('violation_count'),
        plane_count=(report.get('model') or {}).get('plane_count'),
        counts=report.get('counts'),
        manual_policy=manual,
    )
    (Path(out_dir) / 'VALIDATE_STATE.json').write_text(
        json.dumps(summary, indent=1, ensure_ascii=False, default=str) + '\n',
        encoding='utf-8')
    print(json.dumps(summary, indent=1, ensure_ascii=False, default=str))
    return 0 if (report.get('validation_pass') is True
                 and int(report.get('violation_count') or 0) == 0) else 1


if __name__ == '__main__':
    raise SystemExit(main())
