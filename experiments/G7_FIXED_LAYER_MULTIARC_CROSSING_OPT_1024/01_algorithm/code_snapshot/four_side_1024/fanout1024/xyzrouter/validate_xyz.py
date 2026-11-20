# -*- coding: utf-8 -*-
"""G1/G2/G3 manual-policy validation wrapper for the XYZ joint-router project.

Owner: validator-dev (DESIGN.md 4.11).

This module is a thin, *additive* wrapper around the frozen independent
validator ``four_side_1024.fanout1024.native3d.validate_native3d.validate_run``:

* the full geometric checks always run (structure / native metadata / R15 /
  glass / true-3D 50 um clearance / ports / strict same-plane D56 crossings /
  synthetic consistency suite) -- this wrapper never skips or weakens them;
* the 368 manual-U routes (non-empty ``manual_group`` in
  ``assignment_1024.csv``) are validated against one of three contracts:

  - ``frozen`` (G1, default): json-identical ``parts`` / ``length_mm`` / z
    fields to the baseline (historical ``check_manual_frozen`` behaviour);
  - ``height_only`` (G2): route identity (source/target endpoint, plane,
    source/target sides and rows) and the XY geometry of every body flat are
    identical to the baseline (same body flat count, same primitive
    kinds/count/order, coordinates within 1e-6 mm); body flat z, number of
    transitions, lead lengths, transition geometry and layer ids may change;
  - ``fully_optimizable`` (G3): route identity / ports / connection fixed,
    the whole 3D geometry is free (still subject to every hard constraint).

Public API
----------
``validate_xyz(run_dir, baseline_dir, out_dir, manual_policy='frozen',
skip_min_clearance=False, log=print, regression=False,
skip_synthetic=False) -> dict``
    Calls ``validate_run(..., manual_policy=...)``, asserts/normalises the
    ``policy_report``, writes ``<out_dir>/validation.json`` with the added
    top-level ``manual_policy`` and ``policy_report`` blocks and returns the
    full report.

``summarize_report(report) -> dict``
    Stable one-line summary for experiment runners (validation_pass,
    violations, routed, failed, crossings, crossing_pairs, mid_transitions,
    min_3d_clearance, total_length, policy, policy_violations).

``load_validation_report(path) -> dict``
    Load a written ``validation.json`` (accepts a directory or a file).

CLI::

    python -m four_side_1024.fanout1024.xyzrouter.validate_xyz \
        --run-dir <dir> --baseline-dir <frozen baseline dir> \
        --out-dir <dir> --manual-policy frozen \
        [--skip-min-clearance] [--regression] [--skip-synthetic]

Exit codes: 0 = pass, 1 = violations, 2 = input/regression failure.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024.native3d import validate_native3d as V

VALIDATOR_ID = 'four_side_1024.fanout1024.xyzrouter.validate_xyz'
POLICY_REPORT_SCHEMA = 'xyz_manual_policy_report_v1'
POLICY_SUMMARY_KEYS = (
    'identity_mismatch_count', 'identity_mismatched_route_ids',
    'body_flat_count_mismatch_count', 'body_flat_count_mismatch_route_ids',
    'body_primitive_kind_mismatch_count',
    'body_primitive_count_mismatch_count', 'body_xy_mismatch_count',
    'body_xy_mismatch_route_ids',
    'body_z_changed_count', 'body_z_changed_route_ids',
    'transition_count_changed_count', 'transition_count_changed_route_ids',
    'lead_length_changed_count', 'lead_length_changed_route_ids',
    'body_flats_checked', 'body_flat_xy_tolerance_mm', 'identity_fields')

__all__ = ['VALIDATOR_ID', 'POLICY_REPORT_SCHEMA', 'validate_xyz',
           'summarize_report', 'load_validation_report', 'build_policy_report',
           'main']


# ===========================================================================
# small helpers
# ===========================================================================
def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=1, default=str)
    path.write_text(text + '\n', encoding='utf-8')
    return path


def _constraints():
    """Hard constraints this validator certifies (echoed into the report)."""
    return dict(
        r15_mm=V.R15_MM,
        min_3d_clearance_mm=V.MIN_3D_CLEARANCE_MM,
        min_layer_pitch_mm=V.MIN_LAYER_PITCH_MM,
        d56_crossing_rule='strict same-plane (unchanged)',
        crossing_grouping='per physical z',
        model_height_count=len(V.M.planes()),
    )


def _manual_block(report):
    checks = (report or {}).get('checks') or {}
    block = checks.get('manual_frozen') or {}
    return block if isinstance(block, dict) else {}


# ===========================================================================
# policy report
# ===========================================================================
def build_policy_report(report, manual_policy=None):
    """Build/normalise the top-level ``policy_report`` from a report.

    The block is derived from the authoritative
    ``checks['manual_frozen']`` details written by the extended validator, so a
    report can be normalised even when it was produced by an older writer.
    """
    report = report or {}
    block = _manual_block(report)
    provided = report.get('policy_report')
    provided = provided if isinstance(provided, dict) else {}
    policy = str(manual_policy or report.get('manual_policy')
                 or provided.get('policy') or block.get('policy') or 'frozen')
    if policy not in V.MANUAL_POLICIES:
        raise ValueError('unknown manual policy %r (expected one of %r)'
                         % (policy, V.MANUAL_POLICIES))
    violation_count = int(block.get('violations') or 0)
    policy_report = dict(provided)
    policy_report.update(
        schema=POLICY_REPORT_SCHEMA,
        policy=policy,
        check='manual_frozen',
        contract=block.get('contract'),
        rule=block.get('rule'),
        passed=violation_count == 0,
        violation_count=violation_count,
        violation_kinds=block.get('violation_kinds') or {},
        offending_route_ids=block.get('offending_route_ids') or [],
        offending_route_count=int(block.get('offending_route_count') or 0),
        manual_route_count=block.get('manual_route_count'),
        checked=block.get('checked'),
        matched=block.get('matched'),
        mismatch_count=block.get('mismatch_count'),
        mismatch_route_ids=block.get('mismatch_route_ids') or [],
        changed_manual_route_ids=block.get('changed_manual_route_ids') or [],
        geometry_checks_run=list(V.GEOMETRY_CHECKS),
        constraints=_constraints(),
    )
    for key in POLICY_SUMMARY_KEYS:
        if key in block:
            policy_report[key] = block[key]
    return policy_report


def _normalize_report(report, manual_policy, log=print):
    """Assert/normalise ``manual_policy`` + ``policy_report`` on a report.

    Guarantees the wrapper invariants used by the experiment runners:

    * ``report['manual_policy']`` equals the requested policy;
    * ``report['policy_report']`` is present, self-consistent and derived from
      ``checks['manual_frozen']``;
    * a manual-contract violation can never be reported as an overall PASS.
    """
    policy = str(manual_policy or report.get('manual_policy') or 'frozen')
    if policy not in V.MANUAL_POLICIES:
        raise ValueError('unknown manual policy %r (expected one of %r)'
                         % (policy, V.MANUAL_POLICIES))
    if report.get('manual_policy') not in (None, policy):
        log('[xyz] WARNING: report manual_policy=%r differs from requested '
            '%r; normalising to the requested policy'
            % (report.get('manual_policy'), policy))
    report['manual_policy'] = policy
    policy_report = build_policy_report(report, policy)
    report['policy_report'] = policy_report
    violations = int(policy_report.get('violation_count') or 0)
    if violations > 0 and report.get('validation_pass'):
        log('[xyz] WARNING: manual-policy contract has %d violations but the '
            'report says PASS; normalising validation_pass=False' % violations)
        report['validation_pass'] = False
        report['contract_pass'] = False
        if report.get('exit_code') == 0:
            report['exit_code'] = 1
    if report.get('validation_pass') is None:
        report['validation_pass'] = bool(report.get('geometry_pass')) \
            and bool(report.get('contract_pass'))
        report['exit_code'] = 0 if report['validation_pass'] else 1
    return policy_report


def _write_validation(out_dir, report):
    """Merge-write ``<out_dir>/validation.json`` (additive fields only)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / 'validation.json'
    payload = _read_json(path)
    if not isinstance(payload, dict):
        payload = {}
    payload.update(report)
    payload['manual_policy'] = report['manual_policy']
    payload['policy_report'] = report['policy_report']
    payload['xyz_validator'] = VALIDATOR_ID
    payload['validation_file'] = str(path)
    _write_json(path, payload)
    report['validation_file'] = str(path)
    report['xyz_validator'] = VALIDATOR_ID
    return path


# ===========================================================================
# public API
# ===========================================================================
def validate_xyz(run_dir, baseline_dir, out_dir, manual_policy='frozen',
                 skip_min_clearance=False, log=print, regression=False,
                 skip_synthetic=False):
    """Validate one 1024-route run under a G1/G2/G3 manual policy.

    Parameters
    ----------
    run_dir : path-like
        Run directory holding ``routes_l3d.json`` (required),
        ``assignment_1024.csv`` (needed to locate the 368 manual-group routes;
        falls back to ``baseline_dir``) and ``layer_planes.json``.
    baseline_dir : path-like
        Frozen authoritative baseline directory (read-only); supplies the
        baseline ``routes_l3d.json`` used by the manual contract and coverage
        checks.
    out_dir : path-like
        Output directory for ``validation.json`` (and the validator's
        ``validator_consistency_tests.json``).
    manual_policy : {'frozen', 'height_only', 'fully_optimizable'}
        Manual-group contract (default ``'frozen'`` = historical behaviour).
    skip_min_clearance : bool
        Skip the independent minimum-3D-clearance scan (the fresh-World
        clearance audit always runs).
    log : callable
        Progress sink (default ``print``).
    regression : bool
        Also enforce the frozen E5 acceptance numbers (only meaningful for the
        ``frozen`` baseline regression).
    skip_synthetic : bool
        Skip the in-memory synthetic consistency suite (the geometric checks
        themselves always run).

    Returns
    -------
    dict
        The full validation report; also written to
        ``<out_dir>/validation.json`` with the added top-level
        ``manual_policy`` and ``policy_report`` blocks.
    """
    policy = str(manual_policy or 'frozen')
    if policy not in V.MANUAL_POLICIES:
        raise ValueError('unknown manual policy %r (expected one of %r)'
                         % (policy, V.MANUAL_POLICIES))
    log('=' * 78)
    log('[xyz] G1/G2/G3 independent validation: manual_policy=%s' % policy)
    report = V.validate_run(
        run_dir=run_dir,
        baseline_dir=baseline_dir,
        out_dir=out_dir,
        skip_min_clearance=skip_min_clearance,
        log=log,
        regression=regression,
        skip_synthetic=skip_synthetic,
        manual_policy=policy,
    )
    policy_report = _normalize_report(report, policy, log=log)
    # validate_run computed its own out_dir (the argument may be None)
    actual_out = Path(report.get('out_dir') or out_dir)
    _write_validation(actual_out, report)
    log('')
    log('[xyz] manual_policy=%s contract_violations=%d validation_pass=%s'
        % (policy, policy_report.get('violation_count'),
           report.get('validation_pass')))
    log('[xyz] summary: %s' % json.dumps(summarize_report(report),
                                         ensure_ascii=False, sort_keys=True))
    log('[xyz] wrote %s' % report['validation_file'])
    return report


def summarize_report(report):
    """Stable summary dict used by the experiment runners / comparison tables."""
    report = report or {}
    counts = report.get('counts') or {}
    policy_report = report.get('policy_report')
    if not isinstance(policy_report, dict):
        policy_report = build_policy_report(report, report.get('manual_policy'))
    violation_count = report.get('violation_count')
    if violation_count is None:
        violation_count = len(report.get('violations') or [])
    return dict(
        validation_pass=bool(report.get('validation_pass')),
        violations=int(violation_count),
        routed=counts.get('routed'),
        failed=counts.get('failed'),
        crossings=counts.get('same_plane_crossings'),
        crossing_pairs=counts.get('same_plane_crossing_pairs'),
        mid_transitions=counts.get('mid_transitions'),
        min_3d_clearance=counts.get('min_3d_clearance_mm'),
        total_length=counts.get('total_length_mm'),
        policy=report.get('manual_policy') or policy_report.get('policy'),
        policy_violations=int(policy_report.get('violation_count') or 0),
    )


def load_validation_report(path):
    """Load a written ``validation.json`` (accepts a directory or a file)."""
    path = Path(path)
    if path.is_dir():
        path = path / 'validation.json'
    report = _read_json(path)
    if not isinstance(report, dict):
        raise FileNotFoundError(
            'validation report not found / not a JSON object: %s' % path)
    return report


# ===========================================================================
# CLI
# ===========================================================================
def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Independent XYZ-joint (G1/G2/G3) validation of a '
                    '1024-route native-3D run: full geometric checks plus the '
                    'manual-policy contract.')
    parser.add_argument('--run-dir', required=True,
                        help='run directory with routes_l3d.json')
    parser.add_argument('--baseline-dir', default=None,
                        help='frozen authoritative baseline directory '
                             '(read-only)')
    parser.add_argument('--out-dir', default=None,
                        help='output directory for validation.json')
    parser.add_argument('--manual-policy', default='frozen',
                        choices=list(V.MANUAL_POLICIES),
                        help='manual-group contract: frozen (G1, default) / '
                             'height_only (G2) / fully_optimizable (G3)')
    parser.add_argument('--skip-min-clearance', action='store_true',
                        help='skip the independent minimum-3D-clearance scan')
    parser.add_argument('--regression', action='store_true',
                        help='also enforce the frozen E5 acceptance numbers')
    parser.add_argument('--skip-synthetic', action='store_true',
                        help='skip the in-memory synthetic consistency suite')
    args = parser.parse_args(argv)
    try:
        report = validate_xyz(
            run_dir=args.run_dir,
            baseline_dir=args.baseline_dir,
            out_dir=args.out_dir,
            manual_policy=args.manual_policy,
            skip_min_clearance=args.skip_min_clearance,
            regression=args.regression,
            skip_synthetic=args.skip_synthetic,
            log=lambda message: print(message, flush=True),
        )
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print('[xyz] INPUT ERROR: %s: %s'
              % (type(error).__name__, error), file=sys.stderr)
        return 2
    return int(report.get('exit_code', 1))


if __name__ == '__main__':
    sys.exit(main())
