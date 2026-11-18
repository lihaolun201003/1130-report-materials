# 03_PER_STRUCTURE_CONTRIBUTION — 七种专利组合圆弧构型独立收益实验（预注册协议）

> 状态：**预注册（PRE-REGISTERED）**。本文件在正式消融运行开始之前写定。
> 实验对象：20 层、1024 通道、R15、D56、0.05 mm 真三维净空不变。
> 唯一实验变量：**被禁用的专利组合圆弧构型集合**（`G4_DISABLED_STRUCTURES`）。
> 参考起点：`experiments/COLD_START_20_HEIGHT_1024/10_best_valid/`
> （1283 次同层交叉事件、1221 对交叉线路、1024/1024 合法、独立 Validator PASS）。

---

## 1. 研究问题

专利图 6(a)–(d)、图 7(a)–(c) 给出七种平面组合圆弧构型：

| 编号 | 专利名称 | 几何定义（本实验实际使用） |
|---|---|---|
| 6a | 单组短S | 一个双弧 short-S：两段切点相连、转向相反的 R15 圆弧，中间无直线 |
| 6b | 双组短S | 两组 short-S（可直接相切，或夹直线） |
| 6c | 短S在Z型块之前 | 一个 short-S 之后接一个 Z 型块（两个反向四分之一弧夹直线） |
| 6d | 短S在Z型块之后 | Z 型块之后接一个 short-S |
| 7a | 横移后转向 | 一个 short-S 之后接一个四分之一转向弧（可夹直线） |
| 7b | 转向后横移 | 一个四分之一转向弧之后接一个 short-S（可夹直线） |
| 7c | 两次横移后转向 | 两组 short-S 之后接一个四分之一转向弧 |

**RQ1**：从同一个 1024 条全合法、1283 次交叉的初始状态出发，单独禁用上述每一种构型，最终交叉数增加多少？
**RQ2**：哪些构型的收益最大、哪些作用有限、哪些主要靠与其他构型组合才有效？

必须区分三类量，禁止混算：

| 记号 | 定义 | 数据来源 |
|---|---|---|
| **A_i** | 几何替换代价：1283 → 禁用构型 i 并合法重构后的交叉数 | `01_states/<group>/reconstruction_report.json` |
| **B_i** | 搜索改善量：重构后 → 同预算 G4 优化后的交叉数 | `02_runs/<group>/seed_*/summary_g4.json` |
| **C_i** | 消融收益：`Crossings(Ablation-i) − Crossings(Full-ON)`（同种子配对，负值表示禁用后更差） | 表 `tables/per_structure_table.*` |

**七项 C_i 不能相加**当作“多圆弧整体收益”：构型之间存在替代与协同（见 §7）。

---

## 2. 统一参考起点与重构

### 2.1 统一参考起点

所有 9 个实验组从 **同一个** `10_best_valid/` 状态独立复制（`01_states/<group>/`），
互不继承优化结果。Full-ON 组直接使用该状态；其余组先做一次确定性几何重构。

### 2.2 重构（只对使用被禁构型的线路）

1. 用独立几何分类器 `four_side_1024/fanout1024/patent_structures.py` 扫描每条线路的真实
   flat body primitives，找出使用被禁构型的线路（**不是按候选家族名猜**）。
2. 在 `G4_DISABLED_STRUCTURES=<被禁构型>` 生效的进程中，用与 G4 完全相同的 planner
   （`JointWorld.plan_candidates`，`mode='clean'`）重规划这些线路：
   * 第一级：冻结 `PLAN_CFG`（3 个自由高度、2 组 lead、d56_top=16）；
   * 第二级：扩展搜索（最多 20 个高度、6 组 lead、d56_top=64、max_return=8）；
   * 第三级：对**每一个** 20H body 高度做 forced 搜索，取精确交叉增量最小者。
3. 每个候选在提交前再用分类器做一次几何复核；仍含被禁构型的一律丢弃。
4. 候选按 `(exact crossing delta, layer)` 确定性排序；没有合法替代的线路保持原样并记为
   residual（不删除、不强行替换）。若出现 residual，该组如实报告为“不可完全消融”。

禁止：删除线路、放宽 R15/D56/净空、改端口或连接、改高度表。

### 2.3 逐步计账

```
10_best_valid 1283
  + A_i（禁用 i 的合法几何重构）      -> crossings_after_reconstruction
  + B_i（同预算 G4c-free 优化）        -> final(group, seed)
C_i = final(group, seed) - final(Full-ON, seed)   (同种子配对)
```

---

## 3. 实验组

| 组 | `G4_ENABLE_MULTI_ARC` | `G4_DISABLED_STRUCTURES` | 说明 |
|---|---|---|---|
| Full-ON | 1 | （空） | 对照；与 10_best_valid 同状态 |
| NoMultiArc | 0 | （空） | 关闭全部平面多圆弧；重构所有 213 条多圆弧线路 |
| Ablation-6a | 1 | `6a` | 只禁 6a |
| Ablation-6b | 1 | `6b` | 只禁 6b |
| Ablation-6c | 1 | `6c` | 只禁 6c |
| Ablation-6d | 1 | `6d` | 只禁 6d |
| Ablation-7a | 1 | `7a` | 只禁 7a |
| Ablation-7b | 1 | `7b` | 只禁 7b |
| Ablation-7c | 1 | `7c` | 只禁 7c |

`G4_DISABLED_STRUCTURES` 的实现点：`layer2d._LayerRouter._iter_candidates` 在候选
**构建后**调用 `patent_structures.route_types(world)`，与禁用集合有交集则丢弃；
`local_reroute.xy_candidates` 把 cfg 透传给同一开关。默认未设置时行为与历史完全一致
（已用逐层路由 digest 回归验证，见 `code_changes/`）。

---

## 4. 冻结的搜索预算与种子

| 参数 | 值 |
|---|---|
| 引擎 | 冻结 G4c-free（joint make-way LNS，manual-U free） |
| 主预算 | `d56_candidate_evals = 24000`，`route_3d_checks` 上限 `9000` |
| 墙钟安全网 | `5400 s`（设计为不触发；计数预算先到） |
| 种子 | `20261104`, `20261116`, `20261130` |
| 每组 | 3 次独立运行（从该组自己的重构状态出发） |
| 总计 | 9 组 × 3 种子 = 27 次正式运行 |

所有组使用相同引擎、相同操作符顺序、相同接受准则、相同 Validator。

---

## 5. 必须记录的指标

每次运行：

* 最终交叉事件、唯一交叉对、有交叉线路数、最大/P95/单线交叉、总长度；
* flat 弧数/直线数/transition 数；平面多圆弧区域数与线路数；
* `d56_candidate_evals` / `route_3d_checks` / `xy_candidates_generated` /
  `valid_candidates` / `rejected_3d` / accepted transactions / gain；
* 实际墙钟、`routes_l3d.json` SHA256、独立 Validator 结果；
* 逐构型：实例数、使用线路数、物理高度分布、候选生成次数、D56 几何合法次数、
  最终接受事务次数及其真实交叉下降。

定义：

* **使用线路数**：最终 1024 条线路中，几何上包含该构型实例的线路数（一条线路可含多个实例；
  同一构型在一条线路上出现两次按 2 个实例、1 条线路计）。
* **最终接受次数**：该组 G4 运行中，被接受且改变了“最终使用该构型”的线路的事务次数；
  由 `strategy_stats.json` 的 `transaction_history` + 最终几何分类联合统计。
* **事务交叉下降**：事务的真实 `delta`。一个事务若同时涉及多个构型，同时记入
  `involving_gain`，只有单一构型时记入 `exclusive_gain`；禁止把同一次下降重复加总。

---

## 6. 硬性验收

每次运行必须：

* 1024/1024 布通，0 failed，端口/连接身份不变；
* `min_flat_arc_radius_mm ≥ 15.0`，transition 采样半径 ≥ 15 − 1e-6；
* `min_3d_clearance_mm ≥ 0.05`，`min_non_crossing_centerline_mm ≥ 0.08`；
* `violation_count == 0`，`validation_pass == true`（独立新进程验证）；
* 被禁构型组：最终几何中该构型实例数必须为 **0**（几何审计，不是自报）；
* NoMultiArc：`multi_arc_regions == 0`。

任何一条不满足，该次运行判无效，不得因为交叉更低而接受。

---

## 7. 预注册的解释规则

1. 主结论以 3 个种子的均值与样本标准差（ddof=1）报告；探索性统计，不做显著性检验。
2. `C_i > 0` 表示禁用构型 i 使最终交叉增加（该构型有正收益）；`C_i ≤ 0` 如实记录为
   “无正收益/作用有限”。
3. **禁止把七个 C_i 相加**当作多圆弧整体收益：禁用 6a 会同时移除“独立 6a”以及
   与其他构型组合中的 6a 实例（若分类器把组合实例标为组合型，则只移除独立实例），
   构型之间存在替代与协同。
4. 若某构型在 10_best_valid 中出现次数为 0，则其消融组退化为 Full-ON 对照，
   `C_i` 只反映随机搜索差异；必须明确标注“该构型在本布局中未被使用，无法测量独立收益”。
5. 重构 residual > 0 的组必须标注“部分消融”，不得把 residual 线路算作已禁用。

---

## 8. 产物

```
03_PER_STRUCTURE_CONTRIBUTION/
├── PROTOCOL.md                     本文件
├── 01_states/<group>/              统一参考起点的独立副本 + 重构报告
├── 02_runs/<group>/seed_<seed>/    27 次正式运行（routes/checkpoints/validation/审计）
├── tables/                         per_structure_table.{csv,md}、per_structure_runs.json、usage、seed 统计
├── 03_figures/                     七构型收益柱状图、使用频率图、典型线路图、6/7 内部对照
├── validation/                     独立 Validator 汇总
├── logs/                           全部命令与日志
├── tools/                          reconstruct.py / run_per_structure.py / 分类器测试
└── REPORT.md                       最终报告
```
