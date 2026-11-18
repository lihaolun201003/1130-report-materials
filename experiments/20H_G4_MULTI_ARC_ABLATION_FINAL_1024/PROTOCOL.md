# 20H_G4_MULTI_ARC_ABLATION_FINAL_1024 — 严格共同起点多圆弧消融（20 层）

本目录是 21 层实验 `experiments/G4_MULTI_ARC_ABLATION_FINAL_1024/` 在 **20 层 / 1024 通道**
模型上的完整迁移与重跑。它不是重新设计实验：协议、唯一变量、预算、种子、验证与统计口径
全部沿用原实验，唯一变化是物理高度表（20 层）和因此重新生成的 20 层布线链。

---

## 1. 研究问题

在 **相同的 1024 条连接、相同的 20 层高度表、相同几何约束、相同的合法共同起点** 与
**相同的候选评价预算** 下，允许使用平面多段组合圆弧（planar multi-arc）是否显著减少
真实同层交叉事件？

唯一实验变量：`G4_ENABLE_MULTI_ARC = 1 / 0`。
注入点：`four_side_1024/fanout1024/layer2d.py` 的 `_LayerRouter._iter_candidates`
（spec 预过滤 + 构建后几何硬门），经 `xyzrouter/local_reroute.py:xy_candidates` 传播到
G4 联合重规划。

---

## 2. 共同起点（严格相同）

| 项 | 值 |
|---|---|
| 目录 | `common_start_off/` |
| 生成方式 | 20H G3 合法最优（1395 交叉）的 Stage-0 OFF 转换：213 条含平面多圆弧的线路用 **同一条 planner**（`JointWorld.plan_candidates`，`mode='clean'`）重新表达 |
| 残差处理 | 冻结 `PLAN_CFG` 无候选时，执行确定性扩展搜索（20 个高度 / 6 组 lead / d56_top=64 / max_return=8），仍无候选才记 residual；**0 residual** |
| 平面多圆弧区域 | **0**（独立几何审计） |
| 1024 连接 | 全部合法，failed = 0 |
| Validator | 独立 20H 进程 PASS，0 violations |

转换代价单独记为 **effect A**（`crossings_after_conversion − 1395`），不与搜索能力
（effect B）相加。历史 21H effect A = 3967−1322 = +2645（只读参照）。

> 20 层比 21 层少一个 body 高度。冻结 `PLAN_CFG`（3 个候选高度）对 route 456 找不到
> OFF 合法体；按任务要求扩展原有合法候选搜索并允许重新选择高度后，route 456 在
> plane 3（z = −0.275 mm）找到合法 OFF 体（精确交叉增量 −11），转换因此可行。
> 该调整只扩大**搜索范围**，不改变候选语法、R15、D56、三维净空或 Validator。

---

## 3. 预算与种子（与 21H FINAL 完全一致）

### 3.1 主实验（等候选评价预算，PRIMARY）

| 参数 | 值 |
|---|---|
| 引擎 | 冻结 G4c-free（joint make-way LNS，manual-U free） |
| `counted_d56_budget` | **24000** |
| `counted_checks_guard` | **9000** |
| 墙钟安全网 | 5400 s（设计为不触发） |
| sweep / stage 份额 | 0.18 / 0.22 / 0.24 / 0.26 / 0.28 |
| 停止条件 | 达到 d56 预算或 3D 检查上限 |

### 3.2 辅助实验（等墙钟，AUXILIARY）

`--seconds 900`，不设计数上限，其余相同。

### 3.3 种子

`20261104`、`20261116`、`20261130`（预注册）。
主实验 6 次运行（3 种子 × ON/OFF），辅助实验 6 次运行，全部从**同一个**共同起点出发。

---

## 4. 度量与验收

每次运行记录：交叉事件 / 唯一交叉对 / 有交叉线路 / 最大与 P95 单线交叉 / 总长度 /
flat 弧与直线 / transition / 平面多圆弧区域与线路 / d56 与三维评价计数 / 墙钟 /
`routes_l3d.json` SHA256 / 独立 Validator。

硬性验收：

* 1024/1024 布通，0 failed，端口身份不变；
* `min_flat_arc_radius_mm ≥ 15.0`，transition 采样半径 ≥ 15 − 1e-6；
* `min_3d_clearance_mm ≥ 0.05`，`min_non_crossing_centerline_mm ≥ 0.08`；
* `violation_count == 0`，`validation_pass == true`；
* **OFF 臂最终几何 `multi_arc_regions == 0`**（几何审计，不是自报）。

预注册判定 A/B/C 沿用原实验：3/3 种子 ON<OFF 且配对均值差 ≥ 200（起点 3967 的 5% 在
20H 按本实验起点重新设定为 5% 起点值）、ON 长度增幅 ≤5%、全部门槛通过 ⇒ A；
配对差 ≤0 或方向不一致 ⇒ C；其余 ⇒ B。无论结果如何如实报告。

---

## 5. 目录

```
00_audit/      START 指纹、转换报告、源码快照
common_start_off/  严格共同起点（1024 合法、0 多圆弧）
runs/on/<tag>/      ON 臂（主/辅）
runs/off/<tag>/     OFF 臂（主/辅）
tables/        summary_c1 / summary_a1 / abc / decision / stage0_audit
validation/    独立验收汇总
figures/       图件
logs/          实际命令与日志
tools/         run_final.py（本实验驱动）
```

正式运行命令见 `RUNBOOK.md`；结果见 `report.md`。
