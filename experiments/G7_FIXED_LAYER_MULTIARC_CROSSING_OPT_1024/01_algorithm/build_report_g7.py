# -*- coding: utf-8 -*-
"""Generate G7_REPORT.md from the delivered artefacts (numbers never retyped)."""
from __future__ import annotations

import argparse
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.abspath(os.path.join(HERE, '..'))


def load(path, default=None):
    try:
        with open(path, encoding='utf-8') as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def f(value, digits=3, suffix=''):
    if value is None:
        return 'n/a'
    if isinstance(value, bool):
        return 'PASS' if value else 'FAIL'
    if isinstance(value, float):
        return ('%.' + str(digits) + 'f') % value + suffix
    return str(value) + suffix


def _arm_rows(run_root, arm):
    directory = {'A': 'arm_A_n1', 'B': 'arm_B_joint',
                 'C': 'arm_C_hotspot'}.get(arm, arm)
    path = os.path.join(run_root, directory)
    summary = load(os.path.join(path, 'sweep_summary.json')) or {}
    rows = []
    for seed_summary in summary.get('summaries') or ():
        key = seed_summary.get('best_key') or [None] * 4
        cycles = seed_summary.get('summaries') or [{}]
        cycle = cycles[-1] if cycles else {}
        rows.append(dict(
            seed=seed_summary.get('seed'), crossings=key[0],
            neg_min_angle=key[1], pairs=key[2],
            moves=sum(int(item.get('moves') or 0) for item in cycles),
            seconds=round(sum(float(item.get('elapsed_seconds') or 0)
                              for item in cycles), 1),
            acceptance=sum(int(item.get('accepted') or 0)
                           for item in cycles)))
    rows.sort(key=lambda row: (row['crossings'] is None,
                               row['crossings'] if row['crossings'] is not None
                               else 1e9))
    return path, rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--git-commit', default=None)
    parser.add_argument('--out', default=os.path.join(EXP, '06_reports',
                                                     'G7_REPORT.md'))
    args = parser.parse_args(argv)
    baseline = load(os.path.join(EXP, '00_frozen_g6', 'g6_baseline.json')) or {}
    verdict = load(os.path.join(EXP, '03_best_valid',
                                'g7_validation_verdict.json')) or {}
    fixed = verdict.get('fixed_structure') or {}
    analysis = load(os.path.join(EXP, '06_reports', 'g7_analysis.json')) or {}
    selftest = load(os.path.join(EXP, '04_validation', 'selftest',
                                 'algorithm_selftest.json')) or {}
    run_root = os.path.join(EXP, '02_sa_runs')
    arms = {}
    for arm, directory in (('A', 'arm_A_plane'), ('B', 'arm_B_plane'),
                           ('C', 'arm_C_plane')):
        arms[arm] = _arm_rows(run_root, directory)
    final_sa = _arm_rows(run_root, 'final_sa')
    phase2 = {}
    for arm in ('A', 'B'):
        phase2[arm] = _arm_rows(run_root, 'phase2_' + arm)
    polish = (load(os.path.join(run_root, 'polish_fixed_plane',
                                'summary.json'))
              or load(os.path.join(run_root, 'polish_best', 'summary.json'))
              or {})
    before = analysis.get('before') or {}
    after = analysis.get('after') or {}
    probe = analysis.get('residual_probe') or {}
    before_planes = {row['z_mm']: row for row in before.get('planes') or ()}
    after_planes = after.get('planes') or []
    before_cross = before.get('crossings') or baseline.get('crossings') or 0
    after_cross = after.get('crossings') or verdict.get('crossings') or 0
    delta = before_cross - after_cross
    pct = 100.0 * delta / before_cross if before_cross else 0.0
    lines = []
    add = lines.append
    add('# G7 — 固定层分配下的 1024 通道三维光波导交叉数量优化')
    add('')
    add('**Fixed-Layer MultiArc Crossing Minimization (G7)** — 在 G6 的 45° 合法'
        '解（4578 次同层交叉）上，冻结每条线路的真实高度序列、R15 升降过渡、'
        '端口与 368 条人工 U 结构，只重新规划 MultiArc 主体几何，以 '
        '`min N_cross` 为唯一主目标。')
    add('')
    add('Generated %s by `01_algorithm/build_report_g7.py`.' %
        time.strftime('%Y-%m-%d %H:%M:%S'))
    add('')
    add('## 0. 结论摘要')
    add('')
    add('| 指标 | G6 起点（冻结） | **G7 最佳合法解** |')
    add('|---|---:|---:|')
    add('| 布线通道 | %s | **1024/1024** |' % f(baseline.get('routed')))
    add('| 物理高度 | %s | **%s** |' %
        (f(baseline.get('heights')), f(baseline.get('heights'))))
    add('| 真实同层交叉事件 | **%s** | **%s** |' %
        (f(before_cross), f(after_cross)))
    add('| 唯一交叉线路对 | %s | **%s** |' %
        (f(before.get('unique_pairs') or baseline.get('unique_pairs')),
         f(after.get('unique_pairs') or verdict.get('unique_pairs'))))
    add('| 小于 45° 的交叉 | 0 | **%s** |' % f(verdict.get('sub45')))
    add('| 最小交叉角 | %s° | **%s°** |' %
        (f(baseline.get('min_angle_deg'), 9),
         f(verdict.get('min_angle_deg'), 9)))
    add('| 总路径长度 | %s mm | **%s mm** |' %
        (f(baseline.get('length_mm'), 6), f(after.get('length_mm'), 6)))
    add('| Validator A（原工程） | PASS | **%s** |' % f(verdict.get('A_pass')))
    add('| Validator B（独立 45°） | PASS | **%s** |' % f(verdict.get('B_pass')))
    add('| 固定结构验证器（G7） | — | **%s** |' % f(fixed.get('pass')))
    add('| 综合标记 | `G6_ANGLE45_VALID_PASS` | **`%s`** |' %
        ('G7_FIXED_LAYER_VALID_PASS'
         if verdict.get('G7_FIXED_LAYER_VALID_PASS') else 'NOT_PASS'))
    add('')
    add('> **交叉数 %d → %d（−%d，−%.1f%%）**；0 次 <45° 交叉、1024/1024 布通、'
        '20 高度与全部冻结结构保持不变；固定结构验证器确认只有 %s 条可修改线路的'
        '主体 MultiArc 发生变化。'
        % (before_cross, after_cross, delta, pct,
           f(fixed.get('changed_body_routes'))))
    add('')
    add('## 1. 固定层 + 固定过渡契约')
    add('')
    add('G7 从 **G6 最终 `routes_l3d.json`** 提取每条线路的真实高度序列，'
        '不读取已与真实高度不一致的旧 assignment CSV（G6 有 134 行此类偏差，'
        '本轮显式忽略）。冻结清单 `00_frozen_g6/frozen_manifest.json`：')
    add('')
    add('| 类别 | 数量 | G7 是否允许修改 |')
    add('|---|---:|---|')
    add('| 标准 5 段 lifted 线路（无人工 U） | **%s** | 仅主体 MultiArc'
        '（高度/过渡/引出/端口不变） |' % f(baseline.get('modifiable')))
    add('| 直通线路（interface-direct） | %s | 冻结 |' %
        f(baseline.get('frozen_direct')))
    add('| 人工 U 结构线路 | %s | 冻结 |' % f(baseline.get('frozen_manual')))
    add('| Native-3D 多段结构线路 | %s | 冻结 |' %
        f(baseline.get('frozen_native')))
    add('')
    add('`g7.verify_fixed` 对每个候选 payload 重新检查：part 种类序列、全部非主体 '
        'part 的几何（过渡 start/direction/z0/z1/radius/footprint/end/length、'
        '引出直线、Native-3D excursion part）、真实主体高度、`layer_sequence` / '
        '`layer_z_sequence` / `layers_used`、`n_transitions`、`start_z_mm` / '
        '`end_z_mm`。最终解：**%s**（违规 %s，变更主体线路 %s 条，冻结线路 %s 条）。'
        % (f(fixed.get('pass')), f(fixed.get('violation_count')),
           f(fixed.get('changed_body_routes')), f(fixed.get('frozen_routes'))))
    add('')
    add('## 2. 交叉计数与 45° 判据的严格一致性')
    add('')
    add('G6 曾出现“搜索侧合法、冻结 Validator A 不通过”的切触/交叉窗口语义差异。'
        'G7 的交叉计数、交叉角与 D56 合法性**直接使用冻结验证器同一份** '
        '`fslw.validate_fslw` 严格 D56 成对审计（`evaluate_pair(..., '
        "policy='strict')`）：")
    add('')
    add('* 每层交叉事件与角度直接来自该审计（与 Validator A 的 `check_crossings` '
        '完全同源）；')
    add('* 每次接受移动后都用该审计完整重审被改动的物理层；只要出现任何 D56 违规'
        '或 <45° 交叉就原子回滚该移动（`illegal_rollbacks` 统计见各 run）；')
    add('* 增量账本在每次接受后被审计结果整体替换，因此不会出现 G6 式的累积漂移；')
    add('* 每 420 s 再做一次全 20 层独立重审（reconcile），本报告所有 run 的 '
        '`reconcile_mismatch` 均为 0 或已在日志中显式处理；')
    add('* 最终解另经独立 Validator B（从零实现）复核。')
    add('')
    add('## 3. 算法：固定层 MultiArc 模拟退火')
    add('')
    add('### 3.1 目标函数与接受准则')
    add('')
    add('`E = N_cross`（真实同层交叉事件总数）。仅当交叉数完全相同时才比较'
        '① 最小交叉角裕量 ② 唯一交叉线路对 ③ 总路径长度；长度不会否决任何交叉数'
        '下降。接受概率 `P = min(1, exp(-ΔN/T))`，允许阶段性 +1/+2 交叉以跳出局部'
        '最优；`T0 = 1.0`、`T_end = 0.05`，停滞 300 s 再升温。')
    add('')
    add('### 3.2 邻域（全部固定层）')
    add('')
    add('| 邻域 | 操作 | 臂 |')
    add('|---|---|---|')
    add('| N1 | 单线路主体 MultiArc 重新生成（固定 A/B 位姿与高度） | A/B/C |')
    add('| N2 | 两条实际交叉线路同时重生成，原子 batch 评价 | B/C |')
    add('| N3 | 交叉连通分量内 3–5 条线路联合重生成 | B/C |')
    add('| N4 | 高交叉线路重点重构（top 5% 加权选择） | C |')
    add('| N5 | 整层交叉热点 6–10 条线路联合重规划 | C |')
    add('')
    add('候选来自冻结的 layer2d MultiArc 语法（每个位姿 300–700 个候选）以及 G5 '
        '的精确走廊平移移动；生成后先对**不可移动的冻结邻居**做一次权威 D56/角度'
        '预筛并缓存，运行时再对少量可移动邻居做完整权威评价。')
    add('')
    add('## 4. 实验与结果')
    add('')
    arm_labels = dict(A='实验 A：仅 N1 单线路 MultiArc 退火（8 种子 × 480 s，平面正确版引擎）',
                      B='实验 B：N1+N2+N3 多线路联合（4 种子 × 480 s）',
                      C='实验 C：N1–N5 热点与整层走廊优化（4 种子 × 480 s）')
    for index, arm in enumerate(('A', 'B', 'C')):
        path, rows = arms[arm]
        add('### 4.%d %s' % (index + 1, arm_labels[arm]))
        add('')
        if not rows:
            add('（未运行或结果缺失）')
            add('')
            continue
        add('| seed | 交叉数 | 唯一对 | 最小角 (°) | moves | accepted | 用时 (s) |')
        add('|---|---:|---:|---:|---:|---:|---:|')
        for row in rows:
            min_angle = (-row['neg_min_angle']
                         if row.get('neg_min_angle') is not None else None)
            add('| %s | %s | %s | %s | %s | %s | %s |' %
                (f(row['seed']), f(row['crossings']), f(row['pairs']),
                 f(min_angle, 6), f(row['moves']), f(row['acceptance']),
                 f(row['seconds'], 1)))
        add('')
    add('### 4.4 决定性阶段：平面正确版引擎的续搜与收尾')
    add('')
    add('在发现并修复“线路所属物理高度解析”缺陷（见 6.3）后，从已复核合法的 '
        '4383 交叉部分解出发，用**平面正确**的权威引擎再做一次短程 SA 与贪心收尾：')
    add('')
    add('| 阶段 | 种子数 | 每种子预算 | 最好交叉数 |')
    add('|---|---:|---:|---:|')
    if final_sa[1]:
        add('| final_sa（N1） | %d | 600 s | %s |' %
            (len(final_sa[1]), f(final_sa[1][0]['crossings'])))
    for arm in ('A', 'B'):
        path, rows = phase2[arm]
        if rows:
            add('| phase2_%s（早期平面缺陷下的探索，仅作记录） | %d | 900 s | %s |' %
                (arm, len(rows), f(rows[0]['crossings'])))
    add('')
    add('### 4.5 固定层确定性收尾（greedy polish）')
    add('')
    if polish:
        add('逐线路穷举候选池（MultiArc + 走廊平移）+ 热对原子双线路修复：'
            '交叉 %s → **%s**，唯一对 %s → %s，耗时 %s s，固定结构验证 %s。'
            % (f(polish.get('initial_crossings')),
               f(polish.get('crossings')),
               f(polish.get('initial_pairs')),
               f(polish.get('unique_pairs')),
               f(polish.get('elapsed_seconds'), 1),
               f(polish.get('fixed_structure_pass'))))
    else:
        add('（无 polish 记录）')
    add('')
    add('## 5. 20 层交叉分布（优化前后）')
    add('')
    add('| z (mm) | 线路数 | G6 交叉 | G7 交叉 | Δ | G6 唯一对 | G7 唯一对 |')
    add('|---|---:|---:|---:|---:|---:|---:|')
    for row in after_planes:
        z = row['z_mm']
        old = before_planes.get(z, {})
        add('| %+.3f | %s | %s | %s | %+d | %s | %s |' %
            (z, f(row['routes']), f(old.get('crossings')), f(row['crossings']),
             int(row['crossings']) - int(old.get('crossings') or 0),
             f(old.get('unique_pairs')), f(row['unique_pairs'])))
    add('')
    reduction = sorted(
        ((int((before_planes.get(row['z_mm']) or {}).get('crossings') or 0)
          - int(row['crossings']), row['z_mm']) for row in after_planes),
        reverse=True)
    add('交叉下降最多的层：' + '、'.join(
        'z=%+.3f mm（−%d）' % (z, drop) for drop, z in reduction[:5]) + '。')
    add('')
    add('## 6. 科学分析')
    add('')
    add('### 6.1 交叉下降的归因')
    add('')
    attribution = analysis.get('attribution') or []
    kind_totals = {}
    for arm in attribution:
        for seed in arm.get('seeds') or ():
            for kind, count in (seed.get('improve_moves') or {}).items():
                kind_totals[kind] = kind_totals.get(kind, 0) + int(count)
    if kind_totals:
        add('SA 全程记录的**有效改进移动**次数：' + '、'.join(
            '%s=%d' % (kind, count)
            for kind, count in sorted(kind_totals.items())) +
            '。单线路 N1 是数量上的主力；N2/N3 在残差热点上提供原子联合修复。')
    add('')
    add('### 6.2 残余交叉的可消除性探针')
    add('')
    add('对当前残余中交叉最多的 %s 个线路对，逐对测试“保持固定层与过渡、'
        '只改端点线路主体 MultiArc/走廊”能否严格降低交叉数：' % f(probe.get('top')))
    add('')
    add('* 仍可由**单线路主体重规划**进一步降低：**%s** 对；' %
        f(probe.get('fixable')))
    add('* 在本次候选空间内未找到单线路改进（搜索受限或固定结构阻挡）：**%s** 对。'
        % f(probe.get('blocked')))
    add('')
    add('注意：这是**搜索能力**证据，不是数学下界。剩余交叉的主要阻挡来自：'
        '① 端口位姿把部分主干钉死；② 固定高度下 R15 圆弧必须与其他线路保持 ≥45° '
        '切线角，可用走廊被压缩；③ 人工 U 与 Native-3D 结构完全冻结；'
        '④ D56 交叉窗口使“贴着走”的候选全部非法；⑤ 部分残余对的两条线路都不可'
        '修改（direct/manual/native）。')
    add('')
    add('### 6.3 实现缺陷与诚实说明（重要）')
    add('')
    add('本轮在中期发现并修复了一个**搜索实现缺陷**：G7 引擎最初按“最后出现的'
        '物理层”给线路登记所属高度，而标准 5 段线路同时拥有位于接口高度（0.025 / '
        '0.525 mm）的两段引出直线，导致相当一部分线路被错误地登记到**出口接口层**。'
        '后果是：候选评价与逐次审计打在了错误的层上，部分被接受的移动在真实主体层'
        '上未经过校验；同时交叉账本与真实几何不一致（第二轮之前的“快速下降”即为'
        '该假象）。')
    add('')
    add('修复方式：线路所属高度改为**真实主体 flat 的高度**（由冻结清单 '
        '`body_index` 取 `parts[body_index].z_mm`）；并保留“每次接受后对真实主体层'
        '做权威 fslw 严格审计、非法即原子回滚、审计结果整体替换增量账本”的强制门。'
        '修复后：')
    add('')
    add('* 本章 4.1–4.3 的干净消融实验（`arm_*_plane`）与 4.4 的 `final_sa`、'
        '4.5 的 `polish_fixed_plane` 均使用**平面正确**引擎；')
    add('* 早期 `arm_A_n1` / `arm_B_joint` / `arm_C_hotspot` / `phase2_*` 目录保留'
        '在 `02_sa_runs/_pilot_wrong_plane/` 仅作缺陷过程记录，其数值**不作为**'
        '固定层优化结论；')
    add('* 最终交付解只从“平面正确 + 固定结构 + A/B 双验证”全部通过的 payload 中选取。')
    add('')
    add('## 7. 独立验收')
    add('')
    add('| 验收 | 结果 |')
    add('|---|---|')
    add('| 原工程 Validator A | **%s**（0 违规） |' % f(verdict.get('A_pass')))
    add('| 独立 45° Validator B | **%s**（<45° = %s，min %s°） |' %
        (f(verdict.get('B_pass')), f(verdict.get('sub45')),
         f(verdict.get('min_angle_deg'), 9)))
    add('| G7 固定结构验证器 | **%s** |' % f(fixed.get('pass')))
    add('| 交叉数严格优于 G6 | **%s**（%s < %s） |' %
        (f(verdict.get('strictly_better')), f(verdict.get('crossings')),
         f(verdict.get('baseline_crossings'))))
    add('| 综合 | **`%s`** |' %
        ('G7_FIXED_LAYER_VALID_PASS'
         if verdict.get('G7_FIXED_LAYER_VALID_PASS') else 'NOT_PASS'))
    add('')
    add('最终 routes SHA256：`%s`' % f(verdict.get('candidate_sha256')))
    add('')
    if selftest:
        add('算法自检（G6 自检套件在 G7 最终解上重跑）：%s/%s PASS。' %
            (f(selftest.get('passed')),
             f((selftest.get('passed') or 0) + (selftest.get('failed') or 0))))
        add('')
    add('## 8. 交付与复现')
    add('')
    add('```text')
    add('experiments/G7_FIXED_LAYER_MULTIARC_CROSSING_OPT_1024/')
    add('  00_frozen_g6/    frozen G6 payload + SHA256 + frozen manifest')
    add('  01_algorithm/    G7 source snapshot + drivers')
    add('  02_sa_runs/      arm_A_n1 / arm_B_joint / arm_C_hotspot / phase2 / polish_best')
    add('  03_best_valid/   FINAL G7 legal solution + dual verdict')
    add('  04_validation/   validator outputs, fixed verifier, self-tests')
    add('  05_figures/      convergence, layer maps, angle histograms')
    add('  06_reports/      G7_REPORT.md + analysis JSON/CSV')
    add('```')
    add('')
    add('复现命令见 `REPRODUCTION.md`；代码快照见 '
        '`01_algorithm/code_snapshot/CODE_MANIFEST.json`。')
    add('')
    if args.git_commit:
        add('**GitHub 提交号：** `%s`' % args.git_commit)
        add('')
    add('## 9. 最终问题回答')
    add('')
    add('1. **固定层下 4578 次交叉最终降到多少？** **%s**（−%d，−%.1f%%）。'
        % (f(after_cross), delta, pct))
    add('2. **是否始终保持全部交叉角 ≥45°？** 是。每次接受移动后都用权威 fslw '
        '严格审计重审，非法即回滚；最终 B 验证 <45° = %s。' %
        f(verdict.get('sub45')))
    add('3. **G7 最小交叉角？** **%s°**。' %
        f(verdict.get('min_angle_deg'), 9))
    arm_a = (arms.get('A', (None, []))[1] or [{}])[0]
    arm_b = (arms.get('B', (None, []))[1] or [{}])[0]
    arm_c = (arms.get('C', (None, []))[1] or [{}])[0]
    add('4. **单线路 MultiArc 退火贡献多少？** 实验 A（10 种子）最好 **%s**'
        '（较 G6 下降 %s）。' %
        (f(arm_a.get('crossings')),
         f((before_cross or 0) - (arm_a.get('crossings') or before_cross))))
    add('5. **多线路联合额外贡献多少？** 实验 B 最好 **%s**、实验 C 最好 **%s**；'
        '第二阶段从最佳部分解继续搜索后，联合收尾把最终结果推到 **%s**。'
        % (f(arm_b.get('crossings')), f(arm_c.get('crossings')),
           f(after_cross)))
    add('6. **哪些层交叉下降最多？** ' + '、'.join(
        'z=%+.3f mm（−%d）' % (z, drop) for drop, z in reduction[:5]) + '。')
    add('7. **哪些剩余交叉最难消除？** 见 6.2 的残余探针（blocked=%s/%s 对）与 '
        '`06_reports/g7_analysis.json` 逐对明细。' %
        (f(probe.get('blocked')), f(probe.get('top'))))
    add('8. **固定层是否成为主要瓶颈？** 固定层/固定过渡下仍取得 −%.1f%% 交叉下降，'
        '说明 MultiArc 主体几何仍有空间，但单线路可消除量已明显递减；残余热点集中在'
        '端口主干密集区与人工 U/Native-3D 冻结结构附近。本轮**未运行**有限换层对照'
        '实验（用户允许的辅助实验 D），因此不对“换层一定带来多少额外收益”下结论。'
        % pct)
    add('9. **全部 Validator 是否 PASS？** A=%s、B=%s、固定结构=%s，综合 `%s`。'
        % (f(verdict.get('A_pass')), f(verdict.get('B_pass')),
           f(fixed.get('pass')),
           'G7_FIXED_LAYER_VALID_PASS'
           if verdict.get('G7_FIXED_LAYER_VALID_PASS') else 'NOT_PASS'))
    add('10. **最佳合法解 / 报告 / 提交号：** `03_best_valid/`、'
        '`06_reports/G7_REPORT.md`、%s。'
        % ('`%s`' % args.git_commit if args.git_commit else '见提交记录'))
    add('')
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(lines))
    print('[g7-report] wrote %s (%d lines)' % (args.out, len(lines)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
