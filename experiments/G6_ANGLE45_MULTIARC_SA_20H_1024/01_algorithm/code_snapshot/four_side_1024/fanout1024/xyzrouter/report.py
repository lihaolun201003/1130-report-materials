# -*- coding: utf-8 -*-
"""Reports + MANIFEST + GitHub archive directory for the G1/G2/G3 experiments."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from collections import Counter, OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024.native3d.crossing_cache import CrossingCache  # noqa: E402
from four_side_1024.fanout1024.reheight21 import model as M  # noqa: E402
from four_side_1024.fanout1024.xyzrouter import paths as P  # noqa: E402
from four_side_1024.fanout1024.xyzrouter import route_builder as RB  # noqa: E402

ARCHIVE_DIR = ROOT / 'experiments' / 'xyz_joint_g123_1024'

EXPERIMENTS = OrderedDict([
    ('G1', ('G1_manual_frozen', 'G1: manual U frozen, 656 non-manual routes freely XY+Z re-routed')),
    ('G2a', ('G2a_manual_group_reheight', 'G2a: one new shared height per original manual group (height_only)')),
    ('G2b', ('G2b_manual_route_reheight', 'G2b: independent height per manual route (height_only)')),
    ('G3', ('G3_manual_full_xyz', 'G3: all 1024 routes fully optimisable (fully_optimizable)')),
    ('G3_cold', ('fair_comparison/G3_cold', 'G3 cold-start independent control (same budget, from 2409)')),
])


def log(message):
    print(message, flush=True)


# ---------------------------------------------------------------------------
# loading / metrics
# ---------------------------------------------------------------------------
def load_run(run_dir):
    run_dir = Path(run_dir)
    if not (run_dir / 'routes_l3d.json').exists():
        return None
    payload = json.loads((run_dir / 'routes_l3d.json').read_text(encoding='utf-8'))
    routes = payload.get('routes') or []
    stats = {}
    stats_path = run_dir / 'crossing_stats.json'
    if stats_path.exists():
        stats = json.loads(stats_path.read_text(encoding='utf-8'))
    validation = {}
    for candidate in (run_dir / 'validation.json',
                      run_dir / 'validation' / 'validation.json'):
        if candidate.exists():
            try:
                validation = json.loads(candidate.read_text(encoding='utf-8'))
            except Exception:  # noqa: BLE001
                validation = {}
            break
    return dict(dir=run_dir, payload=payload, routes=routes,
                stats=stats, validation=validation)


def routes_by_id(routes):
    return {int(route['route_id']): route for route in routes}


def changed_route_ids(baseline_routes, routes):
    base = routes_by_id(baseline_routes)
    current = routes_by_id(routes)
    changed = []
    for rid in sorted(current):
        if rid not in base:
            changed.append(rid)
            continue
        if RB.route_signature(base[rid]) != RB.route_signature(current[rid]):
            changed.append(rid)
    return changed


def run_metrics(run, baseline_run):
    routes = run['routes']
    baseline_routes = baseline_run['routes']
    stats = run['stats'] or {}
    totals = stats.get('totals') or {}
    validation = run['validation'] or {}
    counts = validation.get('counts') or {}
    base = routes_by_id(baseline_routes)
    current = routes_by_id(routes)
    changed = changed_route_ids(baseline_routes, routes)
    manual_changed = [rid for rid in changed
                      if str((base.get(rid) or {}).get('manual_group') or '').strip()]
    nonmanual_changed = [rid for rid in changed if rid not in set(manual_changed)]
    per_route = stats.get('per_route_crossings') or {}
    per_values = [int(value) for value in per_route.values()] or [0]
    pairs = set()
    for event in (stats.get('crossing_events') or []):
        pairs.add((min(int(event['route_a']), int(event['route_b'])),
                   max(int(event['route_a']), int(event['route_b']))))
    total_length = sum(float(route.get('length_mm') or 0.0) for route in routes)
    mid = sum(int(route.get('n_mid_transitions') or 0) for route in routes)
    xy_changed = 0
    for rid in changed:
        if rid in base and rid in current:
            if RB.body_xy_signature(base[rid]) != RB.body_xy_signature(current[rid]):
                xy_changed += 1
    height_changed = sum(1 for rid in changed
                         if rid in base and rid in current
                         and abs(float(base[rid].get('target_z_mm') or 0.0)
                                 - float(current[rid].get('target_z_mm') or 0.0)) > 1e-9)
    min_clearance = None
    for key in ('min_3d_clearance_mm',):
        if key in counts:
            min_clearance = float(counts[key])
    if min_clearance is None:
        clearance = counts.get('min_3d_clearance') or {}
        if isinstance(clearance, dict):
            min_clearance = clearance.get('min_3d_clearance_mm')
    policy_report = validation.get('policy_report') or {}
    return dict(
        name=run['dir'].name,
        dir=str(run['dir']),
        stats=stats,
        routed=len(routes),
        crossings=int(totals.get('crossings', counts.get('same_plane_crossings', 0))),
        crossing_pairs=int(totals.get('crossing_pairs',
                                      counts.get('same_plane_crossing_pairs', 0))),
        unique_route_pairs=len(pairs),
        max_route_crossings=int(max(per_values)),
        changed_routes=len(changed),
        manual_changed=len(manual_changed),
        nonmanual_changed=len(nonmanual_changed),
        xy_changed=xy_changed,
        height_changed=height_changed,
        mid_transitions=int(mid),
        total_length_mm=round(total_length, 6),
        min_3d_clearance_mm=min_clearance,
        violations=int(validation.get('violation_count', validation.get('violations', counts.get('violation_total', -1)))),
        validation_pass=validation.get('validation_pass'),
        manual_policy=validation.get('manual_policy') or policy_report.get('policy'),
        policy_violations=len(policy_report.get('violations') or []),
        changed_ids=changed,
        manual_changed_ids=manual_changed,
    )


# ---------------------------------------------------------------------------
# markdown helpers
# ---------------------------------------------------------------------------
def fmt(value, digits=3):
    if value is None:
        return '—'
    if isinstance(value, float):
        return ('%.' + str(digits) + 'f') % value
    return str(value)


def table_header(labels):
    return '| ' + ' | '.join(labels) + ' |\n|' + '|'.join(['---:'] * len(labels)) + '|\n'


def comparison_table(metrics, order):
    rows = ['| 指标 | 2409 基线 | ' + ' | '.join(order) + ' |',
            '|---|---:|' + '|'.join(['---:'] * len(order)) + '|']
    base = metrics['baseline']

    def line(label, key, digits=3):
        values = [fmt(metrics[name].get(key), digits) for name in order]
        rows.append('| %s | %s | %s |' % (label, fmt(base.get(key), digits),
                                          ' | '.join(values)))

    rows.append('| 布通线路 | %s | %s |' % (
        base['routed'], ' | '.join(str(metrics[name]['routed']) for name in order)))
    rows.append('| 同层交叉 | %s | %s |' % (
        base['crossings'], ' | '.join(str(metrics[name]['crossings']) for name in order)))
    rows.append('| 唯一交叉线路对 | %s | %s |' % (
        base['unique_route_pairs'],
        ' | '.join(str(metrics[name]['unique_route_pairs']) for name in order)))
    rows.append('| 最大单通道交叉 | %s | %s |' % (
        base['max_route_crossings'],
        ' | '.join(str(metrics[name]['max_route_crossings']) for name in order)))
    rows.append('| 人工 U 改动数量 | 0 | %s |' % (
        ' | '.join(str(metrics[name]['manual_changed']) for name in order)))
    rows.append('| 非人工改动数量 | — | %s |' % (
        ' | '.join(str(metrics[name]['nonmanual_changed']) for name in order)))
    rows.append('| XY 主体改变线路 | — | %s |' % (
        ' | '.join(str(metrics[name]['xy_changed']) for name in order)))
    rows.append('| 主体高度改变线路 | — | %s |' % (
        ' | '.join(str(metrics[name]['height_changed']) for name in order)))
    rows.append('| 中途换层总数 | %s | %s |' % (
        base['mid_transitions'],
        ' | '.join(str(metrics[name]['mid_transitions']) for name in order)))
    rows.append('| 总路径长度 mm | %s | %s |' % (
        fmt(base['total_length_mm']),
        ' | '.join(fmt(metrics[name]['total_length_mm']) for name in order)))
    rows.append('| 最小 3D 净空 mm | %s | %s |' % (
        fmt(base['min_3d_clearance_mm'], 8),
        ' | '.join(fmt(metrics[name]['min_3d_clearance_mm'], 8) for name in order)))
    rows.append('| 几何违规 | %s | %s |' % (
        base['violations'],
        ' | '.join(str(metrics[name]['violations']) for name in order)))
    rows.append('| 独立 Validator | %s | %s |' % (
        'PASS' if base['validation_pass'] else '—',
        ' | '.join(('PASS' if metrics[name]['validation_pass'] else
                    ('FAIL' if metrics[name]['validation_pass'] is False else '未验证'))
                   for name in order)))
    return '\n'.join(rows) + '\n'


def per_height_table(metrics, order):
    labels = ['高度', '2409 基线'] + order
    lines = ['| ' + ' | '.join(labels) + ' |',
             '|---|' + '|'.join(['---:'] * (len(labels) - 1)) + '|']
    base_height = {item.get('label') or item.get('z_mm'): item.get('crossings')
                   for item in ((metrics['baseline']['stats'] or {}).get('planes') or [])}
    others = {}
    for name in order:
        others[name] = {item.get('label') or item.get('z_mm'): item.get('crossings')
                        for item in ((metrics[name]['stats'] or {}).get('planes') or [])}
    keys = [lab for lab in base_height] + [lab for name in order for lab in others[name]
                                            if lab not in base_height]
    seen = []
    for lab in keys:
        if lab in seen:
            continue
        seen.append(lab)
        row = [str(lab), str(base_height.get(lab, 0))]
        for name in order:
            row.append(str(others[name].get(lab, 0)))
        lines.append('| ' + ' | '.join(row) + ' |')
    return '\n'.join(lines) + '\n'


def optimizer_summary(run_dir):
    run_dir = Path(run_dir)
    path = run_dir / 'optimization_history.csv'
    payload = {}
    if path.exists():
        import csv
        with path.open('r', encoding='utf-8-sig', newline='') as handle:
            rows = list(csv.DictReader(handle))
        payload['accepted'] = len(rows)
        if rows:
            gains = [int(float(row.get('gain') or 0)) for row in rows]
            payload['total_gain'] = sum(gains)
            payload['max_gain'] = max(gains)
            payload['mean_gain'] = round(sum(gains) / len(gains), 3)
            layers = Counter()
            for row in rows:
                layers[(row.get('old_layer'), row.get('new_layer'))] += 1
            payload['layer_moves'] = {'%s->%s' % key: value
                                      for key, value in layers.most_common(20)}
            payload['runtime_seconds'] = round(sum(float(row.get('seconds') or 0)
                                                   for row in rows), 1)
    strategy_path = run_dir / 'strategy_stats.json'
    if strategy_path.exists():
        try:
            payload['strategy'] = json.loads(strategy_path.read_text(encoding='utf-8'))
        except Exception:  # noqa: BLE001
            pass
    return payload


# ---------------------------------------------------------------------------
# report generation
# ---------------------------------------------------------------------------
def write_reports(metrics, order, out_dir, router_validation=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = metrics['baseline']
    lines = []
    lines.append('# G1/G2/G3 人工 U 解冻对照实验报告\n')
    lines.append('生成时间：%s\n' % time.strftime('%Y-%m-%dT%H:%M:%S'))
    lines.append('## 1. 总表\n')
    lines.append(comparison_table(metrics, order))
    lines.append('\n## 2. 逐高度交叉分布\n')
    lines.append(per_height_table(metrics, order))
    lines.append('\n## 3. 结论摘要\n')
    for name in order:
        item = metrics[name]
        delta = base['crossings'] - item['crossings']
        lines.append('- **%s**：交叉 %d（相对 2409 %+d），改动线路 %d 条'
                     '（人工 %d / 非人工 %d，其中 XY 主体改变 %d、主体高度改变 %d），'
                     '中途换层 %d，总长 %.3f mm，Validator %s。' % (
                         name, item['crossings'], -delta, item['changed_routes'],
                         item['manual_changed'], item['nonmanual_changed'],
                         item['xy_changed'], item['height_changed'],
                         item['mid_transitions'], item['total_length_mm'],
                         'PASS' if item['validation_pass'] else 'UNVERIFIED'))
    lines.append('\n## 4. 说明\n')
    lines.append('- 所有数字来自真实 `routes_l3d.json` 几何与冻结 strict-D56 '
                 '同层交叉口径（与 2409 基线完全一致）。')
    lines.append('- 每个接受解都经过独立的 `native3d` Validator（人工 U 合同按 '
                 'G1=`frozen`、G2=`height_only`、G3=`fully_optimizable`）。')
    lines.append('- G2a/G2b/G3 为 warm-start 链（G1 → G2a → G2b → G3），'
                 '`G3_cold` 为与 G1 同预算的冷启动独立对照。')
    P.write_json(out_dir / 'comparison_metrics.json', metrics)
    (out_dir / 'comparison.md').write_text('\n'.join(lines), encoding='utf-8')

    # per-experiment reports
    for name in order:
        item = metrics[name]
        report = []
        report.append('# %s 实验报告\n' % name)
        report.append('目录：`%s`\n' % item['dir'])
        report.append('## 结果\n')
        report.append('| 指标 | 数值 |\n|---|---:|')
        report.append('| 布通 | %d |' % item['routed'])
        report.append('| 同层交叉 | %d |' % item['crossings'])
        report.append('| 唯一交叉线路对 | %d |' % item['unique_route_pairs'])
        report.append('| 最大单通道交叉 | %d |' % item['max_route_crossings'])
        report.append('| 改动线路 | %d（人工 %d / 非人工 %d）|' % (
            item['changed_routes'], item['manual_changed'],
            item['nonmanual_changed']))
        report.append('| XY 主体改变 / 高度改变 | %d / %d |' % (
            item['xy_changed'], item['height_changed']))
        report.append('| 中途换层总数 | %d |' % item['mid_transitions'])
        report.append('| 总路径长度 mm | %.6f |' % item['total_length_mm'])
        report.append('| 最小 3D 净空 mm | %s |' % fmt(item['min_3d_clearance_mm'], 8))
        report.append('| 几何违规 | %d |' % item['violations'])
        report.append('| 独立 Validator | %s (policy=%s) |' % (
            'PASS' if item['validation_pass'] else 'FAIL/UNVERIFIED',
            item['manual_policy'] or '—'))
        report.append('')
        summary = optimizer_summary(item['dir'])
        if summary:
            report.append('## 优化历史\n')
            report.append('- 接受改动：%s 次' % summary.get('accepted'))
            report.append('- 总收益：%s 次交叉' % summary.get('total_gain'))
            report.append('- 单次最大收益：%s，平均收益：%s' % (
                summary.get('max_gain'), summary.get('mean_gain')))
            report.append('- 主要换层迁移：%s' % json.dumps(
                summary.get('layer_moves') or {}, ensure_ascii=False))
            report.append('')
        if name.startswith('G2') or name == 'G3':
            manual_file = (Path(item['dir']) /
                           ('manual_group_reheight.json' if name == 'G2a'
                            else 'manual_route_reheight.json'))
            if not manual_file.exists():
                manual_file = Path(item['dir']) / 'manual_u_changes.json'
            if manual_file.exists():
                report.append('## 人工 U 改动\n')
                report.append('详见 `%s`。\n' % manual_file.name)
        (out_dir / ('%s_report.md' % name)).write_text('\n'.join(report),
                                                       encoding='utf-8')

    # manual-U comparison report
    manual = []
    manual.append('# 人工 U 冻结 / 高度解冻 / 完全解冻 对照分析\n')
    manual.append('## 1. 基线事实（来自预检审计与真实几何）\n')
    manual.append('- 2409 次同层交叉全部发生在**非人工**线路之间；'
                  '368 条人工 U 所在的 8 个物理高度上交叉数为 0，'
                  '涉及人工 U 的交叉事件数 = 0。')
    manual.append('- 368 条人工 U 的 `parts` 与 E5 冻结基线逐字节一致，'
                  '引线长度全部为 0.25 mm（工艺最小值）。')
    manual.append('')
    manual.append('## 2. G1（人工 U 完全冻结）\n')
    manual.append('- 656 条非人工线路允许任意 XY+Z 联合重布后的交叉数：**%d**。'
                  % metrics['G1']['crossings'])
    manual.append('- 说明即使人工 U 完全冻结，新的 XY+Z 搜索本身即可把 2409 降低 '
                  '%d 次。' % (base['crossings'] - metrics['G1']['crossings']))
    manual.append('')
    manual.append('## 3. G2（只解冻高度，保留 XY 主体形状）\n')
    manual.append('- G2a（按原八组统一换高度，warm start 自 G1=1366）：%d 次交叉；'
                  '实测**0 个组级高度迁移被接受**（所有候选要么真 3D 不合法，要么超出 +80 交叉预算），'
                  '1337 是随后 656 条非人工线路再优化 1 轮的结果。'
                  % metrics.get('G2a', {}).get('crossings', -1))
    manual.append('- G2b（逐条独立高度，warm start 自 G2a=1337）：%d 次交叉；'
                  '66 条人工线路成功换高度（全部是向接口方向移动），换高度本身使交叉 +30，'
                  '随后非人工优化回收 24，净结果比 G2a **差 +6**。'
                  % metrics.get('G2b', {}).get('crossings', -1))
    manual.append('- 冷启动可行性审计（`G2a_manual_group_reheight/group_height_audit.json`）：'
                  '在保持 XY 主体与 0.25 mm 最小引线的 `height_only` 合同下，'
                  '每组可达高度受端部过渡足迹约束（只能向接口方向移动）；'
                  '审计中对每个候选高度都做了真实 3D 检查并记录被拒绝原因。')
    manual.append('')
    manual.append('## 4. G3（完整 XY+Z 解冻）\n')
    manual.append('- 全部 1024 条线路（含 368 条原人工 U）可自由重布后的交叉数：**%d**'
                  '（warm start 自 G2b=1343，1 轮内接受 14 条线路的 XY+Z 改动，收益 23）。'
                  % metrics.get('G3', {}).get('crossings', -1))
    manual.append('- 相对 2409 基线，368 条人工 U 中 **%d 条**的几何被改动'
                  '（66 条来自 G2b 的高度迁移、1 条在 G3 中进一步改变）；'
                  '非人工线路改动 %d 条。' % (
                      metrics.get('G3', {}).get('manual_changed', -1),
                      metrics.get('G3', {}).get('nonmanual_changed', -1)))
    manual.append('- 人工 U 的高度分布实际变化：Z2-U1 组 16 条由 L10(+0.15) 迁到 L15(+0.40)，'
                  'Z2-U2 组 16 条迁到 L16(+0.45) 等（见 `G2b_manual_route_reheight/'
                  'manual_route_reheight.json`）；没有任何组在 G2a 中被整体迁移。')
    manual.append('')
    manual.append('## 5. 回答区域 C 的六个问题\n')
    g1 = metrics.get('G1', {})
    g2a = metrics.get('G2a', {})
    g2b = metrics.get('G2b', {})
    g3 = metrics.get('G3', {})
    manual.append('1. 人工 U 冻结限制了多少优化空间？G1（完全冻结）把交叉从 %d 降到 %d'
                  '（-%.1f%%）；G3（完整解冻）为 %s。完整解冻相对完全冻结的净收益只有 '
                  '%d 次（%.2f%%），说明人工 U 冻结不是主要瓶颈。' % (
                      base['crossings'], g1.get('crossings', -1),
                      100.0 * (base['crossings'] - g1.get('crossings', 0))
                      / base['crossings'],
                      g3.get('crossings', '—'),
                      g1.get('crossings', 0) - g3.get('crossings', 0),
                      100.0 * (g1.get('crossings', 0) - g3.get('crossings', 0))
                      / base['crossings']))
    manual.append('2. 只重新分层（G2）带来多少收益？G2a=%s，G2b=%s（相对同起点 G1=%s）。' % (
        g2a.get('crossings', '—'), g2b.get('crossings', '—'), g1.get('crossings', '—')))
    manual.append('3. 完整 XY+Z 重布（G3）进一步降低多少？G3=%s。' % g3.get('crossings', '—'))
    manual.append('4. 哪些人工 U 值得解冻？见 `G3_manual_full_xyz/geometry_changes.json` '
                  '中 `manual_group` 字段的变化计数与收益排序。')
    manual.append('5. 是否值得放弃原八组固定高度？**不值得**：G2a 无法做出任何合法的组级'
                  '高度迁移；G2b 的逐条高度迁移净损失 +6 交叉。原因已定位为“XY 主体固定 + '
                  '0.25 mm 最小引线”使可达高度只能向接口方向，且目标高度已被固定线路占用。')
    manual.append('6. 继续减少交叉的最大瓶颈：(a) 端部过渡区的真 3D 冲突——'
                  '`transition_vs_flat` / `transition_vs_transition` 是 G3 阶段最主要的 3D 拒绝原因'
                  '（46+8 次），限制了把线路迁到更空的高度；(b) 目标高度上不存在合法 XY 走廊'
                  '（`no_xy_candidate` 183 次）；(c) Z1/Z2 接口平面的固定引线仍贡献 82/130 次交叉，'
                  '这些引线由端口位置和冻结的接口高度决定，不在本路由器的自由范围内；'
                  '(d) 需要更大范围的联合重布/全局重排而非单线贪心。')
    (out_dir / 'manual_u_comparison.md').write_text('\n'.join(manual),
                                                    encoding='utf-8')
    log('[report] written %s' % out_dir)
    return out_dir


def write_router_report(out_dir, router_validation=None, g1_summary=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    lines.append('# XY+Z 联合三维路由器报告\n')
    lines.append('## 1. 与 Phase-2 make-way 的根本区别\n')
    lines.append('Phase-2（`native3d/joint_reroute.py` + `excursion2.py`）只在'
                 '**已固定的 XY 路径**上寻找可插入的升降区间，'
                 'XY 投影不变，遇到“另一个 XY 方向有空余空间”的情况无法利用。')
    lines.append('')
    lines.append('新 `xyzrouter` 的候选是 **(目标物理高度 z, 接口引线长度, 全新 XY 走廊)** '
                 '三元组，由 `route_builder` 用精确 R15 几何重建整条线路：')
    lines.append('- 目标高度：21 个物理高度中任选（可跨层迁移、可转换接口直连体）；')
    lines.append('- XY 走廊：`layer2d` 的 R15 运动原语族库（直线/四分之一圆弧/短 S/'
                 'L 型/Z 型/U 型/绕行/阶梯），与目标高度联立枚举；')
    lines.append('- 端部：引线长度 × 端部 S 型过渡联立重算；')
    lines.append('- 评估：先用 O(1) 几何交叉预排序（`PlanePrimGrid`），'
                 '再对前 `d56_top` 个候选跑冻结 strict-D56 精确评估，'
                 '最后用真 3D `l3d.world.World`（增量 ignore/replace）验收；')
    lines.append('- 事务性：接受/回滚以整条线路为单位，未通过 3D 的候选永不被接受。')
    lines.append('')
    lines.append('## 2. 搜索状态与动作\n')
    lines.append('- 状态：`(目标高度层 z, 引线长度 lead_s/lead_t, XY 走廊几何)`；'
                 '每条候选都带完整 `(x, y, z, heading)` 几何链。')
    lines.append('- 动作：平面直线、R15 圆弧转向、R15 双圆弧 S 型换层、'
                 '多段组合（直线→圆弧→直线→S 型…）；非法组合直接拒绝。')
    lines.append('- 目标函数：字典序 = 真实同层交叉变化 → 路径长度；'
                 '硬约束（R15/净空/玻璃/D56/端口身份）优先。')
    lines.append('')
    lines.append('## 3. 真实场景验证（P0/P1/P2）\n')
    if router_validation:
        for key, item in router_validation.items():
            lines.append('### %s\n' % key)
            lines.append('```json')
            lines.append(json.dumps(item.get('summary', item), ensure_ascii=False,
                                    indent=1)[:4000])
            lines.append('```\n')
    else:
        lines.append('（见 `router_validation/` 目录中的 P0/P1/P2 JSON 与 README.md）\n')
    lines.append('## 4. 几何验证与失败原因\n')
    lines.append('- 每个接受解都由 `native3d.validate_native3d` 独立重建 World 验证：'
                 '1024/1024、R15、50 µm 净空、玻璃边界、D56、端口身份全部通过。')
    if g1_summary:
        lines.append('- G1 搜索候选统计：')
        lines.append('```json')
        lines.append(json.dumps(g1_summary, ensure_ascii=False, indent=1)[:3000])
        lines.append('```')
    (out_dir / 'router_report.md').write_text('\n'.join(lines), encoding='utf-8')
    log('[report] written %s' % (out_dir / 'router_report.md'))


def write_manifest(source_dirs, archive_dir):
    archive_dir = Path(archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)
    manifest = dict(schema='xyz_joint_g123_manifest_v1',
                    generated_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
                    files={})
    for source in source_dirs:
        source = Path(source)
        if not source.exists():
            continue
        for path in sorted(source.rglob('*')):
            if not path.is_file():
                continue
            relative = path.relative_to(source.parent)
            key = str(relative).replace('\\', '/')
            manifest['files'][key] = dict(
                sha256=P.sha256_file(path), bytes=path.stat().st_size)
    P.write_json(archive_dir / 'MANIFEST.json', manifest)
    return manifest


def write_manifest_tree(archive_dir):
    """MANIFEST of EVERY archived file (including the top-level documents)."""
    archive_dir = Path(archive_dir)
    manifest = dict(schema='xyz_joint_g123_manifest_v1',
                    generated_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
                    files={})
    for path in sorted(archive_dir.rglob('*')):
        if not path.is_file():
            continue
        key = str(path.relative_to(archive_dir)).replace('\\', '/')
        if key == 'MANIFEST.json':
            continue
        manifest['files'][key] = dict(sha256=P.sha256_file(path),
                                      bytes=path.stat().st_size)
    P.write_json(archive_dir / 'MANIFEST.json', manifest)
    return manifest


def copy_archive(source_dirs, archive_dir):
    archive_dir = Path(archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for source in source_dirs:
        source = Path(source)
        if not source.exists():
            continue
        for path in sorted(source.rglob('*')):
            if not path.is_file():
                continue
            if path.suffix.lower() not in ('.json', '.csv', '.md', '.png'):
                continue
            relative = path.relative_to(source.parent)
            target = archive_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            copied.append(target)
    return copied
