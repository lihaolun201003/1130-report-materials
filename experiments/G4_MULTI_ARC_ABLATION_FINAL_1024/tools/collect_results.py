# -*- coding: utf-8 -*-
"""Collect every arm run of the FINAL ablation into one metrics table.

For each ``<runs-root>/<arm>/<tag>/`` directory it reads the engine artifacts
(``summary.json``, ``budget_ledger.json``, ``strategy_stats.json``,
``config.json``, ``run_meta.json``), the frozen Validator report
(``validation/validation.json`` and, when present, the second fresh-process run
``validation_final/validation.json``) and -- with ``--with-audit`` -- an
independent geometric re-census of ``best_valid`` (``audit_state.audit_run``).

Outputs ``<out>/runs.json`` and ``<out>/runs.csv``; the audit JSONs are cached
under ``<out>/audit/`` so a re-run does not redo the expensive part.

Usage::

    python experiments/G4_MULTI_ARC_ABLATION_FINAL_1024/tools/collect_results.py \
        --runs-root experiments/G4_MULTI_ARC_ABLATION_FINAL_1024/runs \
        --out experiments/G4_MULTI_ARC_ABLATION_FINAL_1024/tables --with-audit
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import audit_state as AUDIT  # noqa: E402

FIELDS = [
    'arm', 'tag', 'seed', 'multi_arc', 'status',
    'start_crossings', 'final_crossings', 'delta_vs_start', 'crossing_pairs',
    'routes_with_crossings', 'max_route_crossings', 'p95_route_crossings',
    'mean_route_crossings',
    'total_length_mm', 'flat_arcs', 'flat_lines', 'transition_parts',
    'multi_arc_routes', 'multi_arc_regions',
    'accepts', 'transactions', 'valid_candidates', 'rejected_3d',
    'd56_candidate_evals', 'route_3d_checks', 'xy_candidates_generated',
    'counted_d56_target', 'counted_checks_guard', 'sweep_d56',
    'wall_seconds', 'search_seconds', 'search_seconds_stages',
    'sweep_seconds', 'sweep_gain',
    'validator_pass', 'validator_final_pass', 'violations',
    'min_3d_clearance_mm', 'min_flat_arc_radius_mm',
    'min_non_crossing_centerline_mm', 'routed', 'failed',
    'routes_sha256', 'final_routes_sha256',
]


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except ValueError:
        return default


def _num(value, default=None):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def row_for(run_dir, arm, tag, with_audit, audit_dir):
    run_dir = Path(run_dir)
    row = {key: None for key in FIELDS}
    row['arm'] = arm
    row['tag'] = tag
    meta = read_json(run_dir / 'run_meta.json', {}) or {}
    cfg = read_json(run_dir / 'config.json', {}) or {}
    budget = read_json(run_dir / 'budget_ledger.json', {}) or {}
    summary = read_json(run_dir / 'summary.json', {}) or {}
    stats = read_json(run_dir / 'strategy_stats.json', {}) or {}
    extra = stats.get('extra') or {}
    counted = extra.get('counted_budget') or {}
    validation = read_json(run_dir / 'validation' / 'validation.json', {}) or {}
    validation_final = read_json(run_dir / 'validation_final' / 'validation.json',
                                 {}) or {}
    counts = validation.get('counts') or {}

    row['seed'] = meta.get('seed', cfg.get('seed'))
    row['multi_arc'] = meta.get('g4_enable_multi_arc',
                                cfg.get('cfg', {}).get('enable_multi_arc'))
    row['start_crossings'] = extra.get('start_crossings',
                                       cfg.get('start_crossings'))
    row['final_crossings'] = summary.get('crossings',
                                         extra.get('final_crossings'))
    row['delta_vs_start'] = (None if row['final_crossings'] is None
                             or row['start_crossings'] is None
                             else int(row['final_crossings'])
                             - int(row['start_crossings']))
    row['crossing_pairs'] = summary.get('crossing_pairs',
                                        counts.get('same_plane_crossing_pairs'))
    row['routes_with_crossings'] = summary.get('routes_with_crossings')
    row['max_route_crossings'] = summary.get('max_route_crossings')
    dist = counts.get('per_route_crossing_distribution') or {}
    row['p95_route_crossings'] = dist.get('p95')
    row['mean_route_crossings'] = dist.get('mean')
    row['total_length_mm'] = summary.get('total_length_mm',
                                         counts.get('total_length_mm'))
    row['accepts'] = extra.get('accepts', budget.get('accepted_transactions'))
    row['transactions'] = extra.get('transactions', budget.get('transactions'))
    row['valid_candidates'] = budget.get('valid_candidates')
    row['rejected_3d'] = budget.get('rejected_3d')
    row['d56_candidate_evals'] = budget.get('d56_candidate_evals')
    row['route_3d_checks'] = budget.get('route_3d_checks')
    row['xy_candidates_generated'] = budget.get('xy_candidates_generated')
    row['counted_d56_target'] = counted.get('d56_target')
    row['counted_checks_guard'] = counted.get('checks_guard')
    stages = extra.get('stage_stats') or []
    sweep_stage = next((s for s in stages if int(s.get('stage', 0)) == -1), None)
    row['sweep_d56'] = (sweep_stage or {}).get('counted_d56')
    row['wall_seconds'] = budget.get('wall_seconds')
    row['search_seconds'] = summary.get('seconds')
    # the stage-level seconds exclude the trailing graph rebuild + Validator call
    # and are therefore the comparable "search loop" wall clock of one arm
    row['search_seconds_stages'] = (round(sum(
        float(stage.get('seconds_used') or stage.get('seconds') or 0.0)
        for stage in stages), 2) if stages else None)
    row['sweep_seconds'] = (sweep_stage or {}).get('seconds')
    row['sweep_gain'] = (sweep_stage or {}).get('gain')
    row['validator_pass'] = validation.get('validation_pass')
    if validation_final:
        row['validator_final_pass'] = validation_final.get('validation_pass')
    row['violations'] = validation.get('violation_count')
    row['min_3d_clearance_mm'] = counts.get('min_3d_clearance_mm')
    row['min_flat_arc_radius_mm'] = counts.get('min_flat_arc_radius_mm')
    row['min_non_crossing_centerline_mm'] = counts.get(
        'min_non_crossing_centerline_mm')
    row['routed'] = counts.get('routed')
    row['failed'] = counts.get('failed')
    row['routes_sha256'] = (read_json(run_dir / 'SHA256.json', {}) or {}).get(
        'routes_l3d_json')
    row['final_routes_sha256'] = (read_json(
        run_dir / 'best_valid' / 'SHA256.json', {}) or {}).get('routes_l3d_json')

    best = run_dir / 'best_valid'
    finished = ((run_dir / 'summary_g4.json').exists()
                and summary.get('crossings') is not None)
    if best.exists() and (best / 'routes_l3d.json').exists():
        audit_path = Path(audit_dir) / ('%s_%s.json' % (arm, tag))
        audit = None
        if audit_path.exists():
            audit = read_json(audit_path)
        elif with_audit and finished:
            audit = AUDIT.audit_run(best, label='%s/%s' % (arm, tag))
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=1),
                                  encoding='utf-8')
        if audit:
            row['final_crossings'] = audit['crossings']
            row['crossing_pairs'] = audit['crossing_pairs']
            row['routes_with_crossings'] = audit['routes_with_crossings']
            row['max_route_crossings'] = audit['max_route_crossings']
            row['p95_route_crossings'] = audit['p95_route_crossings']
            row['mean_route_crossings'] = audit['mean_route_crossings']
            row['total_length_mm'] = audit['total_length_mm']
            row['flat_arcs'] = audit['flat_arcs']
            row['flat_lines'] = audit['flat_lines']
            row['transition_parts'] = audit['transition_parts']
            row['multi_arc_routes'] = audit['multi_arc']['routes_with_multi_arc']
            row['multi_arc_regions'] = audit['multi_arc']['total_regions']
            row['delta_vs_start'] = (None if row['start_crossings'] is None
                                     else int(audit['crossings'])
                                     - int(row['start_crossings']))
            row['audit_routes_sha256'] = audit['routes_sha256']
        else:
            row['multi_arc_routes'] = None
            row['multi_arc_regions'] = None
    row['status'] = ('complete' if finished and validation.get('validation_pass')
                     else ('complete_unvalidated' if finished else 'incomplete'))

    # consistency check: engine summary vs audit vs validator
    checks = {}
    if row['final_crossings'] is not None and counts.get('same_plane_crossings') is not None:
        checks['validator_equals_audit'] = (
            int(counts['same_plane_crossings']) == int(row['final_crossings']))
    if row.get('audit_routes_sha256') and row.get('final_routes_sha256'):
        checks['audit_sha_equals_best_sha'] = (
            row['audit_routes_sha256'] == row['final_routes_sha256'])
    row['consistency'] = checks
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs-root', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--with-audit', action='store_true')
    parser.add_argument('--label', default='')
    args = parser.parse_args(argv)

    runs_root = Path(args.runs_root)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    audit_dir = out / 'audit'

    rows = []
    for arm_dir in sorted(p for p in runs_root.iterdir() if p.is_dir()):
        arm = arm_dir.name
        for run_dir in sorted(p for p in arm_dir.iterdir() if p.is_dir()):
            row = row_for(run_dir, arm, run_dir.name, args.with_audit, audit_dir)
            rows.append(row)
            print('%-4s %-28s status=%-20s crossings=%s multi_arc_routes=%s '
                  'd56=%s checks=%s wall=%s' % (
                      arm, run_dir.name, row['status'], row['final_crossings'],
                      row['multi_arc_routes'], row['d56_candidate_evals'],
                      row['route_3d_checks'], row['wall_seconds']))

    (out / 'runs.json').write_text(
        json.dumps(dict(label=args.label, runs=rows), ensure_ascii=False,
                   indent=1), encoding='utf-8')
    # CSV: list fields first, then consistency as json string
    import csv
    with (out / 'runs.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS + ['audit_routes_sha256',
                                                             'consistency'],
                                extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            flat = dict(row)
            flat['consistency'] = json.dumps(row.get('consistency') or {},
                                             ensure_ascii=False)
            writer.writerow({key: ('' if flat.get(key) is None else flat.get(key))
                             for key in writer.fieldnames})
    print('\nwrote %s (%d runs)' % (out / 'runs.csv', len(rows)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
