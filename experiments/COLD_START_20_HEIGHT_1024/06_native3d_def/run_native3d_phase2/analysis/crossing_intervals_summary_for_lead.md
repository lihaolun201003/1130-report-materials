# 交叉区间分析 → Lead 摘要

输入：冻结 E5（只读）；可移动路由 656；交叉事件 3275；分析对象=本体 flat 弧长（可行性=任务口径几何+shadow，`world_3d_ok` 另用世界模型式 3D 间距复核）。

Top-5 候选（优先 world_3d_ok；route / 本体层 / s 区间 / 目标高度 / removed→added = net）：
1. r14 L7(z=-0.07) s=0.50–8.82 (簇内 3 交叉) → L9(z=0.12) removed=2 added=0 **net=2** middle=1.40mm W=Y
2. r168 L20(z=-0.03) s=0.50–8.93 (簇内 3 交叉) → L10(z=0.17) removed=2 added=0 **net=2** middle=1.51mm W=Y
3. r213 L8(z=0.07) s=0.50–5.95 (簇内 1 交叉) → Z1_INTERFACE(z=0.03) removed=1 added=0 **net=1** middle=1.99mm W=Y
4. r452 L20(z=-0.03) s=0.50–5.95 (簇内 12 交叉) → Z1_INTERFACE(z=0.03) removed=1 added=0 **net=1** middle=1.99mm W=Y
5. r500 L20(z=-0.03) s=0.50–5.95 (簇内 1 交叉) → Z1_INTERFACE(z=0.03) removed=1 added=0 **net=1** middle=1.99mm W=Y

规模：候选 14136 个，可行 11287 个；可行中 net≥1 的 8520 个、≥3 的 6162 个、≥5 的 3379 个。
路线级：至少一个可行候选 net≥1 的路由 506 条；≥3 的 389 条；≥5 的 274 条；≥10 的 75 条。
真 3D 复核：几何可行候选 11287 个中仅 **152** 个 world_3d_ok；world_3d_ok 且 net≥1 的候选 31 个（net≥3 的 0 个），最好 net=2。

一次换层能否移除多个交叉？**几何上能**：几何可行候选中 net≥3 有 6162 个、net≥5 有 3379 个，最好 net=42（removed=42）。
但**实际可用性受 3D 间距限制**：world_3d_ok 的候选只有 152 个，其中最好的 net=2；因此一次换层净减 2–4 个交叉已是现实上限，而且需要完整 3D 校验后才可采纳。
按路由看：506/656 条可移动路由有几何正收益候选（389 条 net≥3）；但 world_3d_ok 且 net≥1 的路由只有 31 条。
精确 strict-D56 抽检：ranking 前 150 候选 estimate==exact 150/150、D56 通过 149/150；各路由最优候选 estimate==exact 506/506、D56 通过 497/506。
交叉位置的 42% 在圆弧段、无法用直线段换层移除（结构性上限）。

主要限制因素：①区间可放置性（shadow 吸附后无法构造候选 no_shadow_clear_placement 96 次、straight_run_too_short 744 次、落点 shadow_target 1193 次）；②圆弧段/端部不可用（396 个簇不生成候选）；③目标高度占用推高 added。

产物：analysis/crossing_intervals.json（656 条可移动路由、逐候选估计）、crossing_intervals_report.md、plots/*.png。建议实验 B 只取 ranking 顶部候选做精确评估，其余保持 2D 基线。
