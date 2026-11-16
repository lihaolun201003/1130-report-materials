# -*- coding: utf-8 -*-
"""Build the core comparison table of the G4 multi-arc ablation.

Reads only real run products:

* ``<arm>/02_G4c_free/budget_ledger.json`` / ``03_G4d/budget_ledger.json``
* the final ``best_valid/routes_l3d.json`` + ``crossing_stats.json``
* the independent ``validation/validation.json`` of that final state
* ``no_multi_arc/01_convert/conversion_report.json`` for the ablated start

and writes ``comparison/core_table.json`` + ``comparison/core_table.md``.
Nothing is estimated: every number is read from a produced artifact.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024 import layer2d as L2   # noqa: E402

EXP = Path(__file__).resolve().parents[1]
ARCHIVED = Path('C:/Users/lihao/Desktop/Graduation Project/work/'
                '11.9-second-report-all-work/g4_xyz_joint_1024/03_best_valid')


def _load(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8-sig'))


def _recount(run_dir):
    """Recount crossings with the frozen audit (used when no stats file exists).

    ``best_valid/`` of an arm only stores routes + assignment, so a stage that
    was stopped before ``save_final`` has no ``crossing_stats.json``.  This
    rebuilds the per-height D56 state with the *same* frozen audit the engine
    uses and returns ``(events, pairs, per_route_max, per_route)``.
    """
    from four_side_1024.fanout1024.xyzrouter import route_builder as RB
    from four_side_1024.fanout1024.xyzrouter import world_adapter as WA
    from four_side_1024.fanout1024.reheight21 import model as M
    from four_side_1024.fanout1024.xyzrouter.g4 import paths as GP
    payload = _load(Path(run_dir) / 'routes_l3d.json', {})
    rows = GP.read_csv_rows(Path(run_dir) / 'assignment_1024.csv')
    normalized = RB.normalized_rows(rows, stack=M.layer_stack())
    state = WA.RouteWorld(payload.get('routes') or [], normalized,
                          log=lambda *_a: None)
    per_route, _cache = state.per_route_counts()
    values = [int(v) for v in per_route.values()]
    return int(state.total), int(state.pairs), max(values) if values else 0, \
        {str(k): int(v) for k, v in per_route.items()}


def _float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def route_stats(run_dir):
    run_dir = Path(run_dir)
    payload = _load(run_dir / 'routes_l3d.json', {})
    routes = payload.get('routes') or []
    stats = _load(run_dir / 'crossing_stats.json')
    if stats is None:
        stats = _load(run_dir.parent / 'crossing_stats.json')
    if stats is None:
        events, pairs, per_route_max, per_route = _recount(run_dir)
        totals = dict(crossings=events, crossing_pairs=pairs,
                      routes_with_crossings=len(per_route),
                      max_route_crossings=per_route_max)
        stats_source = 'recounted with the frozen audit'
    else:
        totals = stats.get('totals') or {}
        per_route = stats.get('per_route_crossings') or {}
        stats_source = str((run_dir / 'crossing_stats.json'
                            if (run_dir / 'crossing_stats.json').exists()
                            else run_dir.parent / 'crossing_stats.json'))
    flat_arcs = 0
    transitions = 0
    multi_arc_regions = 0
    multi_arc_routes = 0
    total_length = 0.0
    for route in routes:
        regions = 0
        for part in route.get('parts') or ():
            if part.get('kind') == 'transition':
                transitions += 1
                continue
            if part.get('kind') != 'flat':
                continue
            prims = part.get('primitives') or []
            flat_arcs += sum(1 for p in prims if p.get('kind') == 'arc')
            found = L2.local_multi_arc_regions(prims)
            regions += len(found)
        multi_arc_regions += regions
        if regions:
            multi_arc_routes += 1
        total_length += _float(route.get('length_mm'), 0.0)
    values = [int(v) for v in (per_route or {}).values()]
    return dict(
        run_dir=str(run_dir),
        stats_source=stats_source,
        routes=len(routes),
        routed=int(payload.get('routed') or len(routes)),
        failed=int(payload.get('failed') or 0),
        crossings=int(totals.get('crossings') or 0),
        crossing_pairs=int(totals.get('crossing_pairs') or 0),
        routes_with_crossings=int(totals.get('routes_with_crossings') or 0),
        max_route_crossings=int(totals.get('max_route_crossings') or 0),
        per_route_max=max(values) if values else 0,
        total_length_mm=round(total_length, 6),
        flat_arcs=flat_arcs,
        transitions=transitions,
        multi_arc_regions=multi_arc_regions,
        multi_arc_routes=multi_arc_routes,
    )


def validation_of(run_dir):
    run_dir = Path(run_dir)
    candidates = [run_dir / 'validation' / 'validation.json',
                  run_dir.parent / 'validation' / 'validation.json']
    path = next((item for item in candidates if item.exists()), candidates[0])
    payload = _load(path, {}) or {}
    summary = payload.get('summary') or {}
    counts = payload.get('counts') or {}
    checks = payload.get('checks') or {}
    clearance = checks.get('clearance') or {}
    violations = payload.get('violation_count',
                             payload.get('violations', summary.get('violations')))
    if isinstance(violations, (list, tuple, dict)):
        violations = len(violations)
    policy = payload.get('policy_report') or {}

    def _pick(*values):
        for value in values:
            if value is not None:
                return value
        return None

    return dict(
        path=str(path),
        validation_pass=payload.get('validation_pass'),
        violations=violations,
        crossing_events=_pick(counts.get('same_plane_crossings'),
                              summary.get('crossings')),
        crossing_pairs=_pick(counts.get('same_plane_crossing_pairs'),
                             summary.get('crossing_pairs')),
        min_3d_clearance=_pick(clearance.get('min_3d_clearance_mm'),
                               summary.get('min_3d_clearance')),
        routed=_pick(counts.get('routed'), summary.get('routed')),
        failed=_pick(counts.get('failed'), summary.get('failed')),
        total_length=_pick(counts.get('total_length_mm'),
                           summary.get('total_length')),
        flat_arcs=counts.get('flat_arcs'),
        transitions=counts.get('transitions'),
        policy=_pick(payload.get('manual_policy'), summary.get('policy')),
        policy_violations=_pick(policy.get('violation_count'),
                                summary.get('policy_violations')),
    )


def ledger_of(stage_dirs):
    totals = {}
    for stage_dir in stage_dirs:
        stage_dir = Path(stage_dir)
        payload = _load(stage_dir / 'budget_ledger.json')
        if not payload:
            checkpoints = sorted((stage_dir / 'checkpoints').glob('step_*')) \
                if (stage_dir / 'checkpoints').exists() else []
            if checkpoints:
                payload = _load(checkpoints[-1] / 'budget_ledger.json')
        if not payload:
            continue
        data = payload.get('data') if isinstance(payload, dict) and 'data' in payload else payload
        for key, value in (data or {}).items():
            if isinstance(value, (int, float)):
                totals[key] = totals.get(key, 0) + value
    return totals


def frame_kind_histogram(run_dir):
    from four_side_1024.fanout1024.xyzrouter import route_builder as RB
    from four_side_1024.fanout1024.xyzrouter import world_adapter as WA
    from four_side_1024.fanout1024.reheight21 import model as M
    from four_side_1024.fanout1024.xyzrouter.g4 import paths as GP
    payload = _load(Path(run_dir) / 'routes_l3d.json', {})
    rows = GP.read_csv_rows(Path(run_dir) / 'assignment_1024.csv')
    normalized = RB.normalized_rows(rows, stack=M.layer_stack())
    state = WA.RouteWorld(payload.get('routes') or [], normalized,
                          log=lambda *_a: None)
    counts = {}
    for rid in sorted(state.routes):
        row = state.row(rid)
        route = state.routes[rid]
        layer = int(row['target_layer'])
        try:
            if layer in (1001, 1002):
                task = RB.direct_task(row)
            else:
                task, _s, _t = RB.body_task(row, layer,
                                            float(row['target_z_mm']),
                                            *RB.lead_lengths(route))
        except Exception:                                  # noqa: BLE001
            counts['unknown'] = counts.get('unknown', 0) + 1
            continue
        frame, error = L2.canonical_frame(task)
        key = frame['kind'] if frame else ('error:' + str(error))
        counts[key] = counts.get(key, 0) + 1
    return counts


def main():
    out_dir = EXP / 'comparison'
    out_dir.mkdir(parents=True, exist_ok=True)
    conversion = _load(EXP / 'no_multi_arc' / '01_convert' / 'conversion_report.json', {}) or {}
    on_final = _load(EXP / 'baseline_rerun' / 'chain_run.json', {}) or {}
    off_final = _load(EXP / 'no_multi_arc' / 'chain_run.json', {}) or {}

    arms = {}
    # archived reference (read-only historical product)
    arms['G4_original_archived'] = dict(
        stats=route_stats(ARCHIVED), validation=validation_of(ARCHIVED),
        ledger={}, search_seconds=None,
        note='archived G4 final legal solution (read-only reference)')
    for name, chain in (('G4_rerun_multi_arc', on_final),
                        ('G4_NoMultiArc', off_final)):
        final = chain.get('final_dir')
        stages = [stage['out_dir'] for stage in chain.get('stages') or []]
        if not final:
            arms[name] = dict(stats=None, validation=None, ledger={},
                              search_seconds=None, note='run missing')
            continue
        run_dir = Path(final)
        arms[name] = dict(
            stats=route_stats(run_dir),
            validation=validation_of(run_dir),
            ledger=ledger_of(stages),
            search_seconds=round(sum(float(stage.get('search_seconds') or 0)
                                     for stage in chain.get('stages') or []), 2),
            stages=[dict(stage=stage['stage'], out_dir=stage['out_dir'],
                         search_seconds=stage.get('search_seconds'),
                         validation_seconds=stage.get('validation_seconds'))
                    for stage in chain.get('stages') or []],
            note='re-run with the same code / seed / budget as the ablation arm')

    if conversion:
        arms['G4_NoMultiArc_stage0'] = dict(
            stats=dict(routes=1024, routed=1024, failed=0,
                       crossings=conversion.get('crossings_after'),
                       crossing_pairs=None,
                       total_length_mm=conversion.get('total_length_mm'),
                       flat_arcs=None, transitions=None,
                       multi_arc_regions=conversion.get('multi_arc_routes_after'),
                       multi_arc_routes=conversion.get('multi_arc_routes_after')),
            validation=conversion.get('validation') or {},
            ledger=conversion.get('ledger') or {},
            search_seconds=conversion.get('seconds'),
            note='stage-0 conversion of the 197 inherited multi-arc routes')

    payload = dict(schema='g4_multi_arc_ablation_core_table_v1',
                   arms=arms,
                   conversion=dict(
                       routes=int(conversion.get('multi_arc_routes_before') or 0),
                       converted=int(conversion.get('converted') or 0),
                       residual=int(conversion.get('residual') or 0),
                       crossings_before=int(conversion.get('start_crossings') or 0),
                       crossings_after=int(conversion.get('crossings_after') or 0),
                       delta=int(conversion.get('crossing_delta_from_start') or 0),
                   ))
    (out_dir / 'core_table.json').write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')

    base = arms.get('G4_original_archived_placeholder')
    order = [('原始组 G4（归档）', 'G4_original_archived'),
             ('对照组 G4-NoMultiArc', 'G4_NoMultiArc'),
             ('同代码对照 G4 重跑', 'G4_rerun_multi_arc')]
    lines = ['| 指标 | G4 原始方案（归档 1185） | G4-NoMultiArc | G4 重跑（on 对照） |',
             '|---|---|---|---|']
    keys = [('布通数量', 'routed'), ('交叉事件', 'crossings'),
            ('唯一交叉对', 'crossing_pairs'), ('最大单线交叉', 'max_route_crossings'),
            ('总长度 (mm)', 'total_length_mm'), ('flat 圆弧数', 'flat_arcs'),
            ('transition 数', 'transitions'),
            ('残留平面多圆弧区域', 'multi_arc_regions')]
    for label, key in keys:
        cells = []
        for _title, arm_key in order:
            stats = (arms.get(arm_key) or {}).get('stats') or {}
            value = stats.get(key)
            if isinstance(value, float):
                value = '%.3f' % value
            cells.append('—' if value is None else str(value))
        lines.append('| %s | %s |' % (label, ' | '.join(cells)))
    for label, key in (('Validator', 'validation_pass'),
                       ('几何违规', 'violations')):
        cells = []
        for _title, arm_key in order:
            value = ((arms.get(arm_key) or {}).get('validation') or {}).get(key)
            cells.append('—' if value is None else str(value))
        lines.append('| %s | %s |' % (label, ' | '.join(cells)))
    cells = []
    for _title, arm_key in order:
        value = (arms.get(arm_key) or {}).get('search_seconds')
        cells.append('—' if value is None else '%.1f' % float(value))
    lines.append('| 搜索墙钟 (s) | %s |' % ' | '.join(cells))
    for counter in ('route_3d_checks', 'd56_candidate_evals', 'transactions',
                    'accepted_changes', 'valid_candidates'):
        cells = []
        for _title, arm_key in order:
            value = ((arms.get(arm_key) or {}).get('ledger') or {}).get(counter)
            cells.append('—' if value is None else str(int(value)))
        lines.append('| %s | %s |' % (counter, ' | '.join(cells)))
    (out_dir / 'core_table.md').write_text('\n'.join(lines) + '\n',
                                           encoding='utf-8')
    print('\n'.join(lines))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
