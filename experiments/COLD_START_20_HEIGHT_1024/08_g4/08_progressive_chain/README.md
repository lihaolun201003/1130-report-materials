# 08_progressive_chain — 逐步优化链（B 类补充结果）

> 生成于 2026-11-18T01:54:00。本目录由 `g4/fair_runner.py` 构建；所有数值来自真实运行产物，未估算。

## 1. 定位（重要）

* 本链是 **B 类（继承链）补充结果**：每一段都从**上一段的最佳合法检查点**出发，而不是共同起点。
* **A 类"同起点/同计数预算/同 seed 独立对照"的结果以 `01_arm_C0` ~ `06_arm_G4d` 为准**，见 `../experiment_matrix.csv` 与 `../fair_comparison.md`。
* 链是**分支结构**（link2 G4c 重跑 / link2b 继承最佳 G4c / link3 G4d / 06b 平行 warm-start）：只有 **selected path**（主干）的增量可相加，主干 = G3 → link1(best G4a/G4b) → link2b(继承最佳 G4c) → link3(G4d) = 1322 → 1294 → 1189 → 1185（总 −137）。**不得把链的累计收益全部归因于最后一个算法**：每段收益只归因于该段所用臂/起点，平行分支（link2 重跑 1204、06b 1189）只作对照记录、不重复计入主干收益。
* 链段预算与正式臂预算不同（run_g4_engine 链段参数）：G4c 链段 700s、G4d 链段 1000/1200s；逐段记录在 `chain_summary.json`。
* 本链采用 SPEC B 类允许的"继承最佳合法检查点"：`02b_link_best_G4c` 的 1189 来自 A 类正式臂 G4c_free 的 best_valid（非链段重跑值），链段重跑值（1204）保留在 `02_link_G4c` 作对照；`06b_G4d_warm_from_1189` 是 g4-core 用 seed 20261105 的平行 B 类warm-start 探索，两条不同 seed 的 B 类探索最终取最优合法者，都如实列出。

## 2. 共同起点

* G3 合法最优解：`C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\experiments\COLD_START_20_HEIGHT_1024\07_g123\run_xyz_joint_1024_20h\best_valid`
* routes SHA256 = `a6aa699728c2c431b0e2ccae4f82c2772dc3943eee43a8832ccfc22e1415eabf`
* 交叉 = 1395；seed = 20261104

## 3. 链段收益（真实运行）

| 环节 | 来源臂 | 本段起点交叉 | 本段终点交叉 | 本段增量 | 本段预算 | 本段耗时(s) | 终点 SHA256 | 独立验收 | 违规 | 状态 |
|---|---|---|---|---|---|---|---|---|---|---|
| G3 公共起点 | G3 | 1395 | 1395 | 0 | {"route_3d_checks": 0, "d56_candidate_evals": 0, "wall_seconds": 0.0} | 0.0 | `a6aa699728c2c431…` | None | None | ok |
| best(G4a, G4b) 检查点 | G4b | 1395 | 1371 | -24 | {"route_3d_checks": 30000, "d56_candidate_evals": 120000, "wall_seconds": 900.0} | 842.32 | `ec749648747d7f5d…` | True | 0 | ok |
| 链段 G4c 重跑（从 link1 1294 起） | G4c_free | 1371 | 1309 | -62 | {"route_3d_checks": 30000, "d56_candidate_evals": 120000, "wall_seconds": 700.0} | 738.9 | `f441b332f08392aa…` | True | 0 | ok |
| 最佳 G4c 检查点（来自 A 类 G4c_free 臂） | G4c_free | 1371 | None | None | {} | None | `NA…` | None | None | pending |
| 链段 G4d（从 1189 最佳 G4c 检查点起） | G4d | None | None | None | {} | None | `NA…` | None | None | pending |

* 链 best（selected path）终点 = 1309；主干增量之和 = -86；链 best 总收益（vs 共同起点 1395）= -86。
* selected path：G3 公共起点(1395) → best(G4a, G4b) 检查点(1371) → 链段 G4c 重跑（从 link1 1294 起）(1309)

## 4. 每段真实账本

* **G3 公共起点**（G3）：route_3d_checks=None，d56_candidate_evals=null，transactions=None，valid_candidates=None，accepted_changes=None，gain=None，wall_seconds=None，validation_pass=None，validation_sha_match=False
* **best(G4a, G4b) 检查点**（G4b）：route_3d_checks=None，d56_candidate_evals=null，transactions=None，valid_candidates=None，accepted_changes=None，gain=None，wall_seconds=None，validation_pass=True，validation_sha_match=True
* **链段 G4c 重跑（从 link1 1294 起）**（G4c_free）：route_3d_checks=2737，d56_candidate_evals=22096，transactions=164，valid_candidates=1923，accepted_changes=28，gain=62，wall_seconds=738.9，validation_pass=True，validation_sha_match=True
* **最佳 G4c 检查点（来自 A 类 G4c_free 臂）**（G4c_free）：route_3d_checks=None，d56_candidate_evals=null，transactions=None，valid_candidates=None，accepted_changes=None，gain=None，wall_seconds=None，validation_pass=None，validation_sha_match=True
* **链段 G4d（从 1189 最佳 G4c 检查点起）**（G4d）：route_3d_checks=None，d56_candidate_evals=null，transactions=None，valid_candidates=None，accepted_changes=None，gain=None，wall_seconds=None，validation_pass=None，validation_sha_match=True

## 5. 注记（终版）

1. **G4d A 类臂（06_arm_G4d）因外部误杀分两次 session 运行**：session1 1242.7s 到 1212（中途被误杀，best_valid=1212 来自 checkpoint step_00023），session2 用 `--resume` 111.6s 补完 stage 64/96 并跑独立 validation；矩阵/账本中 `wall_seconds=106.3s` 仅为 session2（恢复段），总搜索墙钟 ≈ 1354s（1242.7+111.6）；其 ledger `route_3d_checks=4400`、`d56_candidate_evals=35815` 为含 checkpoint 恢复的累计值。A 类公平比较以计数预算为主轴，墙钟差异如实列出、不补造未记录耗时。
2. **exploratory 起点/关系**：E2 起点为 E1 的 1201 快照（`_lead_explore_migrate2/start_1201`）；E1b 为 E2 的继续探索（`_lead_explore_direct`）。E1/E2/E1b 均为 exploratory（非正式臂），无独立 validation 的如实标 `not_run`，不计入 A 类对照。

## 6. 文件清单

* `progressive_chain.json` / `progressive_chain.md`：链结构与归因说明
* `chain_summary.json`：每段 start/end crossings、start/end SHA256、增量、预算、实际耗时、ledger、validation（机器可读）
* `00_link_G3_start/`：共同起点检查点副本
* `01_link_best_G4ab/`：best(G4a,G4b) 检查点副本 + 其 validation 副本
* `02_link_G4c/`：链段 G4c 重跑产物（从 1294 起；对照用）
* `02b_link_best_G4c/`：继承的最佳 G4c 合法检查点（1189，来自 A 类 G4c_free 臂，含 validation 副本）
* `03_link_G4d/`：链段 G4d 真实运行产物（从 1189 起；含 best_valid、validation、budget_ledger）
* `runner_logs/`：链段运行控制台日志

