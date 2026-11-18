# -*- coding: utf-8 -*-
"""Run the frozen independent validator on a 20-height run directory.

The validator is :mod:`four_side_1024.fanout1024.reheight21.validate21` **in
full** -- every geometric / D56 / R15 / clearance / port / contract check is
unchanged.  Only the *configuration* expectations (the plane height table,
per-plane assigned route counts, direct/transition totals, plane counts) come
from the installed 20-height model (``coldstart20.model20``), exactly as the
frozen code reads them from ``reheight21.model`` for the 21-height experiment.

Nothing is relaxed: ``R15``, the 50 um true-3D clearance, the strict D56 index,
the glass envelope and the independent crossing definition are all the frozen
ones, and ``--regression`` (the 21-height number lock) is never enabled here.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from . import bootstrap as B          # installs the 20-height profile on import
from . import model20 as M


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', default=None)
    parser.add_argument('--out-dir', default=None)
    parser.add_argument('--skip-min-clearance', action='store_true')
    parser.add_argument('--skip-crossings', action='store_true')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    B.install()
    run_dir = Path(args.run_dir or M.RUN_DIR)
    B.assert_20_height_profile('run_validate')
    from ..reheight21 import validate21

    started = time.time()
    report, validation_path, crossing_path, consistency_path = \
        validate21.validate(
            run_dir=run_dir,
            out_dir=Path(args.out_dir) if args.out_dir else run_dir,
            skip_min_clearance=args.skip_min_clearance,
            skip_crossings=args.skip_crossings, verbose=True)
    summary = dict(
        schema='coldstart20_validation_runner_v1',
        profile=M.PROFILE,
        run_dir=str(run_dir),
        elapsed_s=round(time.time() - started, 1),
        exit_code=int(report.get('exit_code')),
        validation_pass=bool(report.get('validation_pass')),
        geometry_pass=bool(report.get('geometry_pass')),
        contract_pass=bool(report.get('contract_pass')),
        validator_consistency_passed=bool(
            report.get('validator_consistency_passed')),
        counts={key: report.get(key) for key in
                ('routed', 'failed', 'direct_routes', 'transitions',
                 'min_3d_clearance_mm') if key in report},
        crossing_totals=(report.get('counts') or {}),
        violations_total=int(report.get('violation_count') or 0),
        violation_counts_by_check=report.get('violation_counts_by_check'),
        report_path=str(run_dir / 'validation.json'),
        crossing_stats_path=str(run_dir / 'crossing_stats.json'),
    )
    path = run_dir / 'coldstart20_validation_summary.json'
    path.write_text(json.dumps(summary, indent=1, ensure_ascii=False,
                               default=str) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=1, ensure_ascii=False, default=str),
          flush=True)
    return int(report.get('exit_code') or 0)


if __name__ == '__main__':
    raise SystemExit(main())
