# G4_MULTI_ARC_ABLATION_FINAL_1024 — 严格共同起点多圆弧消融（1024 通道）

本目录是 G4 平面多段组合圆弧消融的**最终实验包**：
在**完全相同**的 1024 通道连接、几何约束、可行初始布线（3967 次交叉、0 个平面多圆弧区域）
与**相同候选评价预算**下，只切换 `enable_multi_arc` 一个变量，比较 ON / OFF 两组。

与历史实验包 `G4_MULTI_ARC_ABLATION_1024/`（只读，未修改）的关系见 `comparison.md`：
历史上的 "1185 vs 3484" 混合了**几何转换代价 A** 与**搜索能力差 B**，
本实验只测 **B**。

## 先读哪个

| 想了解 | 打开 |
|---|---|
| 正式科研报告（结论 / 方法 / 结果 / 局限） | `report.md` |
| 预冻结的实验设计（跑之前就写定） | `EXPERIMENT_SPEC.md` |
| 新旧结论与因果强度对照 | `comparison.md` |
| 逐条命令复现 | `RUNBOOK.md` |
| **结果入口（12 次运行的索引）** | `results/INDEX.md`、`results/INDEX.json` |
| 每个 run 的原始统计 | `runs/<arm>/<tag>/summary*.json`、`budget_ledger.json`、`strategy_stats.json` |
| 汇总表 | `tables/summary_c1.md`（主）、`tables/summary_a1.md`（辅助）、`tables/runs.csv` |
| 独立几何复算 | `audit/*.json`、`tables/stage0_audit.json`、`tables/param_2r*.json` |
| 论文图 | `figures/` |
| 代码改动 | `code_changes/g4_equal_budget.patch` + `*.orig` / `*.after` |

> 命名说明：任务书建议的 `results/` 在本包里以 **`runs/<arm>/<tag>/`** 存放完整运行产物
> （每次运行一个目录），`results/` 作为索引入口（`INDEX.md` / `INDEX.json`），
> 两者共同构成"所有 ON/OFF 结果"。

## 三个数字先记住

1. **3967** — 两组的共同起点（历史 Stage-0 转换后的合法状态，多圆弧区域 = 0）；
2. **输出见 `tables/summary_c1.md`** — ON / OFF 在等候选评价预算下的最终交叉；
3. **2645** — 历史转换那一步本身造成的交叉增量（效果 A，已独立重放验证）。

## 目录

```
EXPERIMENT_SPEC.md   预冻结设计（预算、种子、判定规则）
RUNBOOK.md           实际命令 / 环境 / 计数口径 / 代码状态
report.md            正式报告
comparison.md        新旧对照与因果强度
README.md            本文件
results/             结果入口：12 次运行的索引（INDEX.md / INDEX.json）
config/              冻结配置 + 452 个源文件哈希
runs/{on,off}/       每次正式运行的完整产物（含两个独立 Validator）
pilot/               预算标定试点（不参与正式结论）
audit/               独立几何复算（起点、历史解、每次最终解）
tables/              每 run / 每种子 / 汇总 / Stage-0 / 2R 参数化
figures/             论文图（2R 机制、搜索曲线、逐层、真实线路案例）
validation/          独立验收汇总
code_changes/        源码快照（.orig/.after）+ 补丁
tools/               审计、跑臂、收集、统计、出图脚本
logs/                每个 run 的 console 日志
ARCHIVE_NOTES.json   归档裁剪说明（checkpoints 等）
MANIFEST.json        全量文件 SHA256
SHA256SUMS.csv       扁平哈希表
```

## 硬性门槛（每次运行都逐项检查）

1024/1024 布通、0 failed、端口身份不变、`min R = 15.0 mm`、`min 3D clearance ≥ 0.05 mm`、
`min non-crossing centreline ≥ 0.08 mm`、`violations = 0`、`validation_pass = True`、
**OFF 臂的平面多圆弧区域必须为 0**。逐 run 结果见 `tables/summary_c1.md` / `summary_a1.md`。
