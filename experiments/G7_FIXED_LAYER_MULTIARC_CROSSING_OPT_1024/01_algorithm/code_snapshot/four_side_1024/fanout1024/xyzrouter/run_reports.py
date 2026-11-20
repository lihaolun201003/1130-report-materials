# -*- coding: utf-8 -*-
"""Assemble the final reports, fair/warm comparison, best_valid and archive."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024.xyzrouter import paths as P  # noqa: E402
from four_side_1024.fanout1024.xyzrouter import report as R  # noqa: E402


def log(message):
    print('[reports] ' + str(message), flush=True)


def read_json(path):
    path = Path(path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:  # noqa: BLE001
        return None


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', default=str(R.ARCHIVE_DIR))
    parser.add_argument('--skip-archive', action='store_true')
    args = parser.parse_args(argv)
    P.ensure_dirs()
    reports_dir = P.DIRS['reports']
    reports_dir.mkdir(parents=True, exist_ok=True)

    baseline_run = R.load_run(P.baseline_dir())
    if baseline_run is None:
        log('baseline missing')
        return 2
    order = []
    runs = OrderedDict()
    for name, (relative, _description) in R.EXPERIMENTS.items():
        run = R.load_run(P.XYZ_RUN_DIR / relative)
        if run is None:
            log('skip %s (no routes_l3d.json)' % name)
            continue
        runs[name] = run
        order.append(name)
    metrics = OrderedDict()
    metrics['baseline'] = R.run_metrics(baseline_run, baseline_run)
    for name in order:
        metrics[name] = R.run_metrics(runs[name], baseline_run)
        log('%s: crossings=%s routed=%s changed=%s validator=%s' % (
            name, metrics[name]['crossings'], metrics[name]['routed'],
            metrics[name]['changed_routes'], metrics[name]['validation_pass']))

    # ---- router validation (P0/P1/P2) ------------------------------------
    router_validation = {}
    for case in ('P0', 'P1', 'P2'):
        for filename in ('%s_case.json' % case.lower(), '%s_comparison.json' % case.lower(),
                         '%s_summary.json' % case.lower()):
            payload = read_json(P.DIRS['router_validation'] / case / filename)
            if payload is not None:
                router_validation[case] = dict(summary=payload)
                break
    selfcheck = read_json(P.DIRS['router_validation'] / 'selfcheck' /
                          'router_selfcheck.json')
    if selfcheck:
        router_validation['selfcheck'] = dict(summary=selfcheck)

    # ---- reports ---------------------------------------------------------
    R.write_reports(metrics, order, reports_dir,
                    router_validation=router_validation)
    g1_summary = None
    strategy = read_json(Path(metrics['G1']['dir']) / 'strategy_stats.json')
    if strategy:
        g1_summary = strategy
    R.write_router_report(reports_dir, router_validation=router_validation,
                          g1_summary=g1_summary)

    # ---- fair comparison (cold, same budget) -----------------------------
    fair = OrderedDict()
    fair['baseline'] = metrics['baseline']
    fair['G1'] = metrics['G1']
    if 'G3_cold' in metrics:
        fair['G3_cold'] = metrics['G3_cold']
    P.write_json(P.DIRS['fair'] / 'fair_comparison.json', fair)
    lines = ['# 同预算独立对照（均从 2409 合法基线冷启动）\n',
             '| 实验 | 起点 | 交叉 | 改动线路 | Validator |',
             '|---|---:|---:|---:|---|']
    for name in fair:
        item = fair[name]
        lines.append('| %s | %s | %s | %s | %s |' % (
            name, '2409' if name == 'baseline' else str(
                (R.optimizer_summary(item['dir']).get('accepted') and '') or '2409'),
            item['crossings'], item['changed_routes'],
            'PASS' if item['validation_pass'] else 'UNVERIFIED'))
    lines.append('')
    lines.append('G1 与 G3_cold 使用完全相同的搜索预算与随机种子、同一套引擎、'
                 '同一套独立 Validator；区别仅在于人工 U 的冻结程度。')
    (P.DIRS['fair'] / 'comparison.md').write_text('\n'.join(lines),
                                                  encoding='utf-8')

    # ---- warm start comparison -------------------------------------------
    warm = read_json(P.DIRS['warmstart'] / 'summary.json')
    if warm:
        log('warm chain: %s' % [step['step'] for step in warm.get('steps', [])])

    # ---- best valid solution --------------------------------------------
    candidates = []
    for name in order:
        item = metrics[name]
        if item.get('validation_pass'):
            candidates.append((int(item['crossings']), name))
    if candidates:
        candidates.sort()
        best_name = candidates[0][1]
        best_run = P.XYZ_RUN_DIR / R.EXPERIMENTS[best_name][0]
        target = P.DIRS['best_valid']
        target.mkdir(parents=True, exist_ok=True)
        for path in sorted(Path(best_run).glob('*')):
            if path.is_file():
                shutil.copy2(path, target / path.name)
        validation_dir = Path(best_run) / 'validation'
        if validation_dir.exists():
            nested = target / 'validation'
            nested.mkdir(parents=True, exist_ok=True)
            for path in validation_dir.glob('*'):
                if path.is_file():
                    shutil.copy2(path, nested / path.name)
        P.write_json(target / 'BEST.json', dict(
            experiment=best_name, crossings=int(metrics[best_name]['crossings']),
            baseline_crossings=int(metrics['baseline']['crossings']),
            source_dir=str(best_run),
            validation_pass=bool(metrics[best_name]['validation_pass']),
            selected_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
            metrics=dict(metrics[best_name])))
        log('best_valid = %s (%d crossings)' % (best_name,
                                                metrics[best_name]['crossings']))

    # ---- archive ---------------------------------------------------------
    if not args.skip_archive:
        archive = Path(args.archive)
        archive.mkdir(parents=True, exist_ok=True)
        # code + docs
        code_dir = archive / 'code'
        code_dir.mkdir(parents=True, exist_ok=True)
        package = ROOT / 'four_side_1024' / 'fanout1024' / 'xyzrouter'
        for path in package.glob('*.py'):
            shutil.copy2(path, code_dir / path.name)
        shutil.copy2(package / 'DESIGN.md', archive / 'SPEC.md')
        # reports
        for path in reports_dir.glob('*.md'):
            shutil.copy2(path, archive / path.name)
        # experiment artifacts
        for name in order:
            source = Path(metrics[name]['dir'])
            destination = archive / 'experiments' / name
            destination.mkdir(parents=True, exist_ok=True)
            for filename in ('routes_l3d.json', 'assignment_1024.csv',
                             'crossing_stats.json', 'config.json',
                             'SHA256.json', 'geometry_changes.json',
                             'manual_u_changes.json', 'strategy_stats.json',
                             'failed_attempts.json', 'optimization_history.csv',
                             'summary.json'):
                path = source / filename
                if path.exists():
                    shutil.copy2(path, destination / filename)
            for extra in ('manual_group_reheight.json',
                          'manual_route_reheight.json'):
                path = source / extra
                if path.exists():
                    shutil.copy2(path, destination / extra)
            for validation in (source / 'validation.json',
                               source / 'validation' / 'validation.json'):
                if validation.exists():
                    shutil.copy2(validation, destination / 'validation.json')
                    break
        # baseline + preflight
        for source, destination in (
                (P.DIRS['baseline'], archive / 'baseline_authoritative'),
                (P.DIRS['preflight'], archive / 'preflight_audit'),
                (P.DIRS['router_validation'], archive / 'router_validation'),
                (P.DIRS['plots'], archive / 'plots'),
                (P.DIRS['checkpoints'], archive / 'checkpoints'),
                (P.DIRS['G2a'] / 'group_height_audit.json', archive / 'G2a_manual_group_reheight' / 'group_height_audit.json'),
                (P.DIRS['warmstart'], archive / 'warmstart_comparison'),
                (P.DIRS['fair'], archive / 'fair_comparison')):
            source = Path(source)
            if not source.exists():
                continue
            if source.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                continue
            for path in source.rglob('*'):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in ('.json', '.csv', '.md', '.png'):
                    continue
                relative = path.relative_to(source)
                target = Path(destination) / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        R.write_manifest_tree(archive)
        log('archive written to %s' % archive)
    return 0


if __name__ == '__main__':
    sys.exit(main())
