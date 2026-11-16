# EXPERIMENT_SPEC — G4 平面多段组合圆弧消融（严格共同起点版，1024 通道）

> 状态：**预冻结（PRE-FROZEN）**。本文件在**正式实验开跑之前**写定。
> 冻结记录：`config/FROZEN_CONFIG.json`（含写入时间、全部参数、源码快照哈希）。
> 正式运行一旦开始，本文件的任何数值都不得再改；若必须改，另开 `V2` 并在报告里说明原因。

---

## 1. 研究问题与假设

**RQ**：在**相同的 1024 通道连接关系、相同几何约束、相同可行初始布线与相同候选评价预算**下，
允许使用平面多段组合圆弧（planar multi-arc）是否带来显著更少的**真实同层交叉**？

预注册假设（可被否证）：

| 编号 | 假设 | 否证条件 |
|---|---|---|
| H1 | 在严格共同起点下，MultiArc-ON 的最终交叉数显著低于 OFF | 两臂多种子均值差 ≤ 0（或方向相反） |
| H2 | 收益不是"更长的绕路换来的" | ON 明显更长（>5%）却交叉不更低 |
| H3 | 收益主要来自亚 2R（<30 mm）横向错位的紧凑表达 | 收益与"被修复线路的横向错位"无关 |
| H4 | 收益在 3 个随机种子上方向一致 | 出现反向种子 |

**注意**：本实验**不**检验"多圆弧在所有可能光滑曲线里最优"。所有几何结论只限定在
**冻结的 D56 候选语法**（轴对齐直线 + R15 四分之一圆弧 + 两切点相连反向 R15 双弧 S）
之内，这是 SPEC_G4 规定的候选族。

---

## 2. 三类效果必须分开报告（不得合并）

| 记号 | 名称 | 定义 | 数据来源 |
|---|---|---|---|
| **A** | 几何转换代价 | 把继承的 197 条多圆弧线路用"无多圆弧"语法重新表达所产生的交叉增量 | 实验二（Stage-0 审计） |
| **B** | 搜索能力差异 | **同一**起点 + **同一**预算 + **同一**代码，仅切换 `enable_multi_arc` 的最终差 | 实验一（本文件主体） |
| **C** | 总体交叉差异 | 历史 ON/OFF 两套最终解之差（含 A 与 B 与预算不等） | 实验二 / comparison.md |

历史结论 "1185 vs 3484" 属于 **C**，其因果强度受 A 与预算不等污染；本文件的实验一只测 **B**。

---

## 3. 共同起点（严格相同）

| 项 | 值 |
|---|---|
| 目录 | `G4_MULTI_ARC_ABLATION_1024/no_multi_arc/01_convert/`（只读引用） |
| `routes_l3d.json` SHA256 | `1707e189c271c94723af2a7ba304a2cd1deb52955216eff7e063851b964eb15f` |
| `assignment_1024.csv` SHA256 | `ec6e394c41eb090160ba6770644505b0438851650d8503e3909cc7218bf8ec6d` |
| 交叉事件 | **3967**（独立复算，`audit/start_common_3967.json`） |
| 唯一交叉对 | 2942 |
| 平面多圆弧区域 | **0** |
| 连接 | 1024/1024，failed 0 |
| Validator | PASS，violations 0（`no_multi_arc/01_convert/validation/validation.json`） |

**两组从同一个 `routes_l3d.json` 读入，不做任何 Stage-0 转换。**

---

## 4. 唯一改变的算法因素

`enable_multi_arc = True / False`，注入点为 `layer2d._LayerRouter._iter_candidates`
（`G4_ENABLE_MULTI_ARC` 环境变量，默认 1）。关闭时：

1. 先按 `('S', shift)` 过滤候选规格；
2. 再对每个已构建候选做几何硬门：任何"切点连续 + 转向相反 + 圆心不同"的圆弧串一律丢弃。

**该策略代码与历史 G4 实验字节相同**（`layer2d.py` SHA256 `712ebc54…`，
`local_reroute.py` SHA256 `80820624…`，与归档 `code_changes/*.after` 一致）。

保持不变：1024 连接与端口身份、150×150×1 mm、21 个物理高度（19 body + 2 interface）、
R15、D56 同层净空（0.05+0.03=0.08 mm，≥5° 合法横穿豁免）、真 3D 净空 0.05 mm、
人工 U 策略、ALNS、联合让路、局部候选评价与接受准则、目标函数、Validator。

---

## 5. 候选评价计数的精确语义（同等预算的基础）

代码位置与语义（`four_side_1024/fanout1024/xyzrouter/g4/`）：

| 计数器 | 精确位置 | 语义 | 单位 |
|---|---|---|---|
| `d56_candidate_evals` | `joint_world.py:356/445`、`group_replan.py:405`、`make_way.py:101` | 每调用一次 `xy_candidates()`（一个"高度选项 × lead 对"组合的候选生成）加 `d56_top`（该 operator 的 cfg 常量） | 候选评价槽位 |
| `route_3d_checks` | `joint_world.py:388/400/468`、`make_way.py:103/171`、`group_replan.py:419` | 每构建并进入真 3D 世界检查一条 route 加 1 | 真实三维几何评价 |
| `xy_candidates_generated` | 同上 | `xy_candidates()` 实际返回的 body 数 | 生成候选数 |
| `valid_candidates` / `rejected_3d` | 同上 | 通过/被拒的完整几何检查 | 候选 |
| `accepted_changes` / `gain` | `world_adapter.commit`、`group_replan` | 接受的单线路替换数 / 交叉下降量 | 变更 |

**主预算轴 = `d56_candidate_evals`**（任务定义的"实际候选评价"）；
**辅助归一化轴 = `route_3d_checks`**（真实三维几何评价次数）。
两者**不视为等价成本**，分别报告（见 §7.3）。

---

## 6. 冻结的预算

### 6.1 主实验（等候选评价预算，PRIMARY）

| 参数 | 冻结值 |
|---|---|
| `counted_d56_budget` | **24000** |
| `counted_checks_guard`（次级安全上限） | **9000** |
| 墙钟安全网 `--seconds` | **5400**（设计为不触发：试点实测 ~20 d56/s ⇒ 24000 ≈ 1200 s） |
| 贪心 sweep 份额 | `counted_sweep_fraction = 0.18`（与历史 `sweep_ratio=0.18` 一致） |
| 邻域 stage | 8/16/32/64，份额 0.22/0.24/0.26/0.28（引擎默认，两臂相同） |
| 停止条件 | `d56_candidate_evals` 达到 24000（或 checks 达到 9000，或墙钟 5400 s） |

预算通过 `alns.G4Search.run(..., counted_d56=24000, counted_checks_guard=9000)` 的
**计数模式**执行：sweep 与 4 个 stage 各拿到冻结份额的**计数**预算，而不是墙钟份额。
超调上界 = 一个 operator 调用的成本（实测 <10%）。

> **为什么是 24000**：试点（seed 20261104，6000 d56）实测 ON 3967→2853、OFF 3967→3709，
> 两臂都仍在下降、都未被墙钟打断。24000 是试点预算的 4 倍，两臂均可在 ~20 min 内正常跑完，
> 且不触及任何真实上限（历史计数上限 30000/120000 从未触顶的问题在此被彻底消除：
> 两个新上限**都会真实触发**）。

### 6.2 辅助实验（等墙钟预算，AUXILIARY）

| 参数 | 冻结值 |
|---|---|
| `--seconds` | **900** |
| 计数上限 | 不设（`counted_d56 = 0`，回到引擎的墙钟调度） |
| 其余 | 与主实验相同 |

两组均按 900 s 正常结束（`run_g4c` 的 stage 循环由墙钟份额驱动），
不允许任何一组人为提前停止。

### 6.3 种子（预先固定）

`20261104`, `20261116`, `20261130`（主实验与辅助实验使用同一组）。
每个种子两臂各一次 ⇒ 主实验 6 次运行，辅助实验 6 次运行，全部串行。

---

## 7. 度量与统计

### 7.1 每次运行必须记录

最终交叉事件、唯一交叉对、有交叉线路数、最大/P95/中位数单线路交叉、总长度、
flat 圆弧数 / 直线数 / transition 数、平面多圆弧区域数与含多圆弧线路数、
`d56_candidate_evals` / `route_3d_checks` / `xy_candidates_generated` /
`valid_candidates` / `rejected_3d` / `accepted_changes` / `gain`、
实际墙钟、Validator 结果、最终 `routes_l3d.json` SHA256。

### 7.2 汇总

对每个配置报告 3 个种子的**均值、样本标准差（ddof=1）、最小/最大、中位数**，
以及**配对差**（同种子 ON−OFF）。3 次重复 ⇒ **探索性统计**，不做显著性检验，
只报告方向一致性与效应量；报告里明确标注这一点。

### 7.3 归一化对照（必须做）

三条搜索进程曲线（交叉数 vs ① `d56_candidate_evals` ② `route_3d_checks` ③ 墙钟），
数据来自 `strategy_stats.json` 的 `history_records`（每次尝试记录累计三轴计数）。
**等三维评价归一化对照**：在两臂共同的 `route_3d_checks = min(两臂最终值)` 处，
用线性插值读取各自的交叉数并相减。该方法在 §7.3 预先声明，不看结果后修改。

---

## 8. 独立验收协议

每次运行结束后：

1. 引擎内嵌 Validator（子进程，`fully_optimizable`）；
2. **再跑一次全新进程的 Validator** 到 `<run>/validation_final/`；
3. 本仓库独立几何复算 `tools/audit_state.py`（不复用引擎的交叉统计）：
   `world_adapter.RouteWorld` 重算交叉 + `layer2d.local_multi_arc_regions` 重算多圆弧；
4. 三者必须一致：`validator.same_plane_crossings == audit.crossings`、
   `audit.routes_sha256 == best_valid/SHA256.json.routes_l3d_json`。

硬性门槛（任一不满足即判该次运行无效，不得因为交叉更低而接受）：

* 1024/1024 布通，0 failed，route_id / 端口身份不变；
* `min_flat_arc_radius_mm ≥ 15.0`、`min_transition_sampled_radius_mm ≥ 15 - 1e-6`；
* `min_3d_clearance_mm ≥ 0.05`；
* `min_non_crossing_centerline_mm ≥ 0.08`；
* `violation_count == 0`、`validation_pass == True`；
* **OFF 臂**：`multi_arc_regions == 0`（几何审计，不是自报）。

---

## 9. 预注册判定规则（A / B / C）

以主实验（等候选评价预算）3 个种子的配对结果为准：

* **判定 A（支持机制优势）**：3/3 个种子 ON < OFF，且配对均值差 ≥ 200 次交叉
  （≈ 起点 3967 的 5%），且 ON 长度增幅 ≤ 5%，且所有硬性门槛通过。
* **判定 C（未复现）**：配对均值差 ≤ 0，或方向不一致（出现 ON > OFF 的种子）。
* **判定 B（证据不足）**：其余情况（方向一致但效应量小，或长度代价超限，或预算/统计限制）。

无论哪个判定，都必须如实报告；**禁止预设实验必须证明多圆弧有优势**。

---

## 10. 明确不做的声明

1. 不研究 Z 向升降曲线损耗、传播损耗、偏振；
2. 不把交叉减少写成"已证明的光学插入损耗下降"；
3. 不把"多圆弧 > 所有光滑曲线"当作结论，只限定在冻结 D56 候选语法内；
4. 不覆盖历史归档（1185 / 1202 / 3484 三套结果只读）；
5. 不重新设计系统（不改 fanout 落点、不改高度分配算法的目标函数）。

---

## 11. 产物

```
experiments/G4_MULTI_ARC_ABLATION_FINAL_1024/
├── EXPERIMENT_SPEC.md          本文件（预冻结）
├── config/FROZEN_CONFIG.json   冻结参数 + 源码快照哈希 + 时间戳
├── runs/{on,off}/<tag>/        每次正式运行的完整产物
├── pilot/                      预算标定试点（不参与正式结论）
├── audit/                      独立几何复算（起点、历史解、每次最终解）
├── tables/                     每次运行 / 每种子 / 汇总统计
├── figures/                    论文图
├── validation/                 独立验收汇总
├── code_changes/               源码快照（.orig/.after）+ 补丁
├── report.md / comparison.md / RUNBOOK.md
├── MANIFEST.json / SHA256SUMS.csv
└── tools/                      审计、跑臂、收集、出图脚本
```
