# -*- coding: utf-8 -*-
"""Aggregate the independent Validator evidence of every run into ``validation/``.

For each run the engine already wrote one frozen-Validator report
(``validation/validation.json``) and ``run_arm.ps1`` ran a second, fresh process
into ``validation_final/validation.json``.  This script

* copies the *decision-relevant* fields of both into one compact record per run,
* evaluates the hard gates explicitly (1024/1024, identity, R >= 15, 3-D
  clearance >= 0.05 mm, D56 non-crossing centreline >= 0.08 mm, 0 violations),
* writes ``validation/summary.json`` and ``validation/summary.md``.

Usage::

    python .../tools/make_validation_summary.py --runs-root .../runs --out .../validation
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except ValueError:
        return default


def compact(report):
    if not report:
        return None
    counts = report.get('counts') or {}
    checks = report.get('checks') or {}
    coverage = checks.get('coverage') or {}
    radius = checks.get('radius') or {}
    manual = checks.get('manual_frozen') or {}
    synthetic = checks.get('synthetic') or {}
    return dict(
        validation_pass=report.get('validation_pass'),
        violation_count=report.get('violation_count'),
        violation_kinds=report.get('violation_kinds'),
        manual_policy=report.get('manual_policy'),
        routes_file_sha256=report.get('routes_file_sha256'),
        counts=dict(
            records=counts.get('records'), routed=counts.get('routed'),
            failed=counts.get('failed'),
            unique_route_ids=coverage.get('unique_route_ids'),
            expected_route_ids=coverage.get('expected_route_ids'),
            same_plane_crossings=counts.get('same_plane_crossings'),
            same_plane_crossing_pairs=counts.get('same_plane_crossing_pairs'),
            same_plane_crossing_violations=counts.get(
                'same_plane_crossing_violations'),
            min_flat_arc_radius_mm=counts.get('min_flat_arc_radius_mm'),
            min_transition_sampled_radius_mm=counts.get(
                'min_transition_sampled_radius_mm'),
            min_3d_clearance_mm=counts.get('min_3d_clearance_mm'),
            min_non_crossing_centerline_mm=counts.get(
                'min_non_crossing_centerline_mm'),
            total_length_mm=counts.get('total_length_mm'),
            transitions=counts.get('transitions'),
            flat_arc_count=counts.get('flat_arc_count'),
            mid_transitions=counts.get('mid_transitions'),
            manual_route_count=counts.get('manual_route_count'),
            manual_geometry_mismatch_count=counts.get(
                'manual_geometry_mismatch_count'),
            min_edge_glass_margin_mm=counts.get('min_edge_glass_margin_mm'),
            per_route_crossing_distribution=counts.get(
                'per_route_crossing_distribution')),
        checks=dict(
            structure=bool(checks.get('structure')),
            radius=bool(radius), glass=bool(checks.get('glass')),
            clearance=bool(checks.get('clearance')),
            ports=bool(checks.get('ports')),
            crossings=bool(checks.get('crossings')),
            manual_ok=(manual.get('mismatch_count') == 0),
            synthetic_tests=synthetic.get('tests'),
            synthetic_passed=synthetic.get('passed'),
            synthetic_failed=synthetic.get('failed')),
        runtime_seconds=report.get('runtime_seconds'),
        validator=report.get('validator'),
        validated_at=report.get('validated_at'))


def gates(record):
    if not record:
        return dict(available=False)
    counts = record['counts']
    return dict(
        available=True,
        validation_pass=bool(record['validation_pass']),
        zero_violations=(record['violation_count'] == 0),
        routed_1024=(counts['routed'] == 1024 and counts['failed'] == 0),
        coverage_1024=(counts['unique_route_ids'] == 1024
                       and counts['expected_route_ids'] == 1024),
        radius_r15=(counts['min_flat_arc_radius_mm'] is not None
                    and counts['min_flat_arc_radius_mm'] >= 15.0 - 1e-6
                    and counts['min_transition_sampled_radius_mm']
                    >= 15.0 - 1e-6),
        clearance_3d=(counts['min_3d_clearance_mm'] is not None
                      and counts['min_3d_clearance_mm'] >= 0.05),
        d56_clearance=(counts['min_non_crossing_centerline_mm'] is not None
                       and counts['min_non_crossing_centerline_mm'] >= 0.08 - 1e-9),
        crossing_rule_clean=(counts['same_plane_crossing_violations'] == 0),
        manual_identity=(counts['manual_geometry_mismatch_count'] == 0),
        all_pass=None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs-root', default=str(EXP / 'runs'))
    parser.add_argument('--out', default=str(EXP / 'validation'))
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    records = []
    for arm_dir in sorted(p for p in Path(args.runs_root).iterdir() if p.is_dir()):
        for run_dir in sorted(p for p in arm_dir.iterdir() if p.is_dir()):
            engine = compact(read_json(run_dir / 'validation' / 'validation.json'))
            final = compact(read_json(run_dir / 'validation_final' / 'validation.json'))
            if engine is None and final is None:
                continue
            gate_engine = gates(engine)
            gate_final = gates(final)
            for gate in (gate_engine, gate_final):
                if not gate.get('available'):
                    continue
                accumulator = True
                for key, value in gate.items():
                    if key in ('available', 'all_pass'):
                        continue
                    if isinstance(value, bool):
                        accumulator = accumulator and value
                gate['all_pass'] = bool(accumulator)
            entry = dict(arm=arm_dir.name, tag=run_dir.name,
                         engine_validator=engine, final_validator=final,
                         gates_engine=gate_engine, gates_final=gate_final,
                         both_pass=bool((engine or {}).get('validation_pass')
                                        and (final or {}).get('validation_pass')))
            records.append(entry)
            (out / ('%s_%s.json' % (arm_dir.name, run_dir.name))).write_text(
                json.dumps(entry, ensure_ascii=False, indent=1), encoding='utf-8')
            print('%-22s engine=%s final=%s all_gates=%s' % (
                run_dir.name, (engine or {}).get('validation_pass'),
                (final or {}).get('validation_pass'),
                (gate_final or {}).get('all_pass')))

    payload = dict(schema='g4_multi_arc_final_validation_summary_v1',
                   runs=records,
                   all_pass=bool(all(record['both_pass'] for record in records)),
                   n_runs=len(records))
    (out / 'summary.json').write_text(json.dumps(payload, ensure_ascii=False,
                                                 indent=1), encoding='utf-8')

    lines = ['# 独立验收汇总', '',
             '每个 run 有两个**独立进程**的冻结 Validator 报告：'
             '`validation/`（引擎结束时调用）与 `validation_final/`（跑臂脚本再调用一次）。',
             '', '| run | engine PASS | final PASS | violations | crossings | 1024/1024 |'
             ' min R (mm) | min 3D (mm) | D56 (mm) | gates |',
             '|---|---|---|---:|---:|---|---:|---:|---:|---|']
    for entry in records:
        final = entry['final_validator'] or entry['engine_validator'] or {}
        counts = final.get('counts') or {}
        lines.append('| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
            entry['tag'], (entry['engine_validator'] or {}).get('validation_pass'),
            (entry['final_validator'] or {}).get('validation_pass'),
            final.get('violation_count'), counts.get('same_plane_crossings'),
            counts.get('routed'), counts.get('min_flat_arc_radius_mm'),
            counts.get('min_3d_clearance_mm'),
            counts.get('min_non_crossing_centerline_mm'),
            (entry['gates_final'] or {}).get('all_pass')))
    lines.append('')
    lines.append('全部门槛通过：**%s**' % payload['all_pass'])
    (out / 'summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\nwrote %s (all_pass=%s)' % (out / 'summary.md', payload['all_pass']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
