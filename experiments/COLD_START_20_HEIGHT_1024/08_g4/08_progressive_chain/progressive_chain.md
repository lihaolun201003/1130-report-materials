# 逐步优化链（G3 → best(G4a,G4b) → G4c → G4d）

> 由 `g4/fair_runner.py` 从真实检查点构建，生成于 2026-11-18T01:54:00。
> 共同起点：G3 合法最优解，SHA256 = `a6aa699728c2c431b0e2ccae4f82c2772dc3943eee43a8832ccfc22e1415eabf`，交叉 = 1395；seed = 20261104。

## 链段收益表

| 环节 | 本段来源臂 | 本段起点交叉 | 本段终点交叉 | 本段增量收益 | 本段预算 | 本段实际耗时(s) | seed | 终点 SHA256 | 独立验收 | 状态 |
|---|---|---|---|---|---|---|---|---|---|---|
| G3 公共起点 | G3 | 1395 | 1395 | 0 | {"route_3d_checks": 0, "d56_candidate_evals": 0, "wall_seconds": 0.0} | 0.0 | 20261104 | a6aa699728c2c431… | None | ok |
| best(G4a, G4b) 检查点 | G4b | 1395 | 1371 | -24 | {"route_3d_checks": 30000, "d56_candidate_evals": 120000, "wall_seconds": 900.0} | 842.32 | 20261104 | ec749648747d7f5d… | True | ok |
| 链段 G4c 重跑（从 link1 1294 起） | G4c_free | 1371 | 1309 | -62 | {"route_3d_checks": 30000, "d56_candidate_evals": 120000, "wall_seconds": 700.0} | 738.9 | 20261104 | f441b332f08392aa… | True | ok |
| 最佳 G4c 检查点（来自 A 类 G4c_free 臂） | G4c_free | 1371 | None | None | NA | None | 20261104 | NA… | None | pending |
| 链段 G4d（从 1189 最佳 G4c 检查点起） | G4d | None | None | None | NA | None | 20261104 | NA… | None | pending |

## 归因规则与说明

链的累计收益 = 各段增量收益之和；每段收益只归因于该段所用的臂/检查点起点，不得把链的累计收益全部归因于最后一个算法。pending 环节表示该链段尚未真实运行，不得估算或补造。

* **G3 公共起点**（G3，ok）：所有臂与链的共同起点（已核验 G3 合法最优解，交叉 1322）
* **best(G4a, G4b) 检查点**（G4b，ok）：按独立验收的交叉数选择 G4a/G4b 中更优者作为 G4c 起点
* **链段 G4c 重跑（从 link1 1294 起）**（G4c_free，ok）：从上一链段最佳合法检查点继承的真实运行结果
* **最佳 G4c 检查点（来自 A 类 G4c_free 臂）**（G4c_free，pending）：继承"最佳合法检查点"（SPEC B 类允许）：该 1189 检查点来自 A 类正式臂 G4c_free 的 best_valid（routes/assignment/validation 已复制），不是链段重跑值；链段重跑值见上一链段（仅作对照）。本段不消耗链段搜索预算（0s），其收益 −105 的因果归属注明为"来自 A 类 G4c_free 臂 + link1 起点"。
* **链段 G4d（从 1189 最佳 G4c 检查点起）**（G4d，pending）：本链段尚未真实运行；需用支持 --start-dir 的 runner 从 C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\experiments\COLD_START_20_HEIGHT_1024\08_g4\08_progressive_chain\02b_link_best_G4c 继承检查点运行（不得修改他人 runner）

