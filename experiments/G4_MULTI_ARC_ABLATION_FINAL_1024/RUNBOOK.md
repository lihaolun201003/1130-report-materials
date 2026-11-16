# RUNBOOK — G4 平面多圆弧消融（严格共同起点版，1024 通道）

> 本文件记录**实际执行过的命令、种子、预算、代码状态与哈希**，使
> `experiments/G4_MULTI_ARC_ABLATION_FINAL_1024/` 的全部产物可被独立复现。
> 与历史目录 `G4_MULTI_ARC_ABLATION_1024/`（只读）并列存在，不修改其任何文件。

---

## 0. 一句话复现

```powershell
cd "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D"
# 主实验：等候选评价预算（d56 = 24000），2 臂 × 3 种子，串行
foreach ($seed in 20261104, 20261116, 20261130) {
  foreach ($arm in 'on','off') {
    powershell -NoProfile -ExecutionPolicy Bypass -File `
      experiments\G4_MULTI_ARC_ABLATION_FINAL_1024\tools\run_arm.ps1 `
      -Arm $arm -Tag "c1_${arm}_$seed" -Seed $seed `
      -CountedD56 24000 -CountedChecks 9000 -Seconds 5400
  }
}
# 辅助实验：等墙钟（900 s）
foreach ($seed in 20261104, 20261116, 20261130) {
  foreach ($arm in 'on','off') {
    powershell -NoProfile -ExecutionPolicy Bypass -File `
      experiments\G4_MULTI_ARC_ABLATION_FINAL_1024\tools\run_arm.ps1 `
      -Arm $arm -Tag "a1_${arm}_$seed" -Seed $seed -Seconds 900
  }
}
```

---

## 1. 环境

| 项 | 值 |
|---|---|
| OS | Windows 11 (10.0.26100) |
| CPU | Intel Core i9-13900HX（24C/32T），**单进程串行**运行 |
| Python | 3.10.11（`C:\Users\lihao\AppData\Local\Programs\Python\Python310\python.exe`） |
| 工作目录 | `C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D` |
| 结果目录 | `<工作目录>\experiments\G4_MULTI_ARC_ABLATION_FINAL_1024\` |

> 所有正式运行在**同一台机器、同一套源码、同一天**内串行完成。
> 每次运行的环境、种子、预算、起止时间写在 `<run>/run_meta.json`。

---

## 2. 数据来源（全部只读）

| 角色 | 路径 | SHA256 |
|---|---|---|
| **共同起点**（无多圆弧、3967 交叉） | `work/1130-report-materials/G4_MULTI_ARC_ABLATION_1024/no_multi_arc/01_convert/` | routes `1707e189…`，assignment `ec6e394c…` |
| G3 合法最优解（1322，仅实验二审计用） | `outputs/manual_c4_new_connectivity/XYZ_JOINT_G123_1024/best_valid/` | routes `711cf910…` |
| 历史 G4 归档解（1185，只读参照） | `work/11.9-second-report-all-work/g4_xyz_joint_1024/03_best_valid/` | routes `b74ae511…` |
| 历史 ON 重跑（1202）/ OFF（3484） | `G4_MULTI_ARC_ABLATION_1024/baseline_rerun|no_multi_arc/03_G4d/best_valid` | 见归档 MANIFEST |
| 身份/端口权威基线 | `outputs/.../XYZ_JOINT_G123_1024/baseline_authoritative/` | — |

> 新实验**不执行 Stage-0 转换**：共同起点本身已经是无多圆弧状态。

---

## 3. 代码状态（唯一变量之外全部冻结）

### 3.1 唯一变量

`enable_multi_arc = True / False`（环境变量 `G4_ENABLE_MULTI_ARC=1/0`），
注入点 `four_side_1024/fanout1024/layer2d.py` 的 `_LayerRouter._iter_candidates`。
该策略代码与历史 G4 实验**字节相同**：

| 文件 | SHA256 |
|---|---|
| `four_side_1024/fanout1024/layer2d.py` | `712ebc5472e3…`（等于历史归档 `code_changes/layer2d.py.after`） |
| `four_side_1024/fanout1024/xyzrouter/local_reroute.py` | `808206248ccc…`（等于历史归档 `local_reroute.py.after`） |

### 3.2 本实验新增的最小修改（**不影响候选几何**，只影响预算调度与记账）

| 文件 | 修改 | 目的 |
|---|---|---|
| `g4/alns.py` | `run(..., counted_d56, counted_checks_guard)`、`counted_used()`、`_counted_exhausted()`；sweep/stage 按**计数份额**停止；`history_records` 增加 `d56/r3d/xy` 累计列；`extra_payload` 增加 `counted_budget`；`start_total` 元数据 | 等候选评价预算公平对照 + 三轴曲线 |
| `g4/run_g4c.py` / `run_g4d.py` / `run_g4_engine.py` | 新增 `--counted-d56-budget` / `--counted-checks-guard` | 命令行注入冻结预算 |
| `g4/arm_base.py` / `g4/artifacts.py` | `state.start_total` 取代硬编码 `GP.START_CROSSINGS` | 起点为 3967 时 `delta_vs_start` 不写错 |

补丁：`code_changes/g4_equal_budget.patch`（6 文件，+176 / −13 行）；
原始/修改后快照：`code_changes/*.orig` / `*.after`。

**验证**：本地 `four_side_1024/fanout1024/xyzrouter/g4/` 的 25 个文件中，
只有上述 6 个与归档快照 `work/11.9-second-report-all-work/g4_xyz_joint_1024/08_code/SHA256.json`
不同，其余 19 个逐字节一致；`layer2d.py` / `local_reroute.py` 与历史消融归档逐字节一致。
冻结记录见 `config/FROZEN_CONFIG.json`（452 个源文件哈希）。

---

## 4. 预算与计数口径

### 4.1 计数位置（精确）

| 计数器 | 代码位置 | 语义 |
|---|---|---|
| `d56_candidate_evals` | `joint_world.py:356`, `:445`；`make_way.py:101`；`group_replan.py:405` | 每次 `xy_candidates()` 调用 +`d56_top`（该 operator 的常量），代表被预筛的候选槽位 |
| `route_3d_checks` | `joint_world.py:388`, `:400`, `:468`；`make_way.py:103`, `:171`；`group_replan.py:419` | 每条被构建并进入真 3D World 检查的 route +1 |
| `xy_candidates_generated` | 同上 | `xy_candidates()` 实际返回 body 数 |
| `valid_candidates` / `rejected_3d` | 同上 | 完整几何检查通过 / 被拒 |
| `accepted_changes` / `gain` | `world_adapter.commit` 等 | 接受替换数 / 交叉下降 |

### 4.2 冻结预算

| | 主实验（等候选评价） | 辅助实验（等墙钟） |
|---|---|---|
| `--counted-d56-budget` | **24000** | 0（关闭计数模式） |
| `--counted-checks-guard` | **9000** | 0 |
| `--seconds` | 5400（安全网，设计为不触发） | **900**（实际停止条件） |
| sweep 份额 | 0.18（计数） | 0.18（墙钟） |
| stage | 8/16/32/64，0.22/0.24/0.26/0.28 | 同 |

---

## 5. 正式运行清单

| tag | 臂 | seed | 预算 |
|---|---|---|---|
| `c1_on_20261104` | on | 20261104 | d56 = 24000 |
| `c1_off_20261104` | off | 20261104 | d56 = 24000 |
| `c1_on_20261116` | on | 20261116 | d56 = 24000 |
| `c1_off_20261116` | off | 20261116 | d56 = 24000 |
| `c1_on_20261130` | on | 20261130 | d56 = 24000 |
| `c1_off_20261130` | off | 20261130 | d56 = 24000 |
| `a1_on_20261104` … `a1_off_20261130` | on/off | 3 seeds | wall = 900 s |

每次运行由 `tools/run_arm.ps1` 完成：设置环境变量 → 调 `run_g4_engine --arm G4c_free`
→ 引擎内嵌 Validator → **再起一个全新进程跑一次 Validator** 到 `<run>/validation_final/`
→ 写 `run_meta.json`。

---

## 6. 分析与出图命令

```powershell
$EXP = 'experiments\G4_MULTI_ARC_ABLATION_FINAL_1024'
python $EXP\tools\audit_state.py --run-dir <dir> --label <name> --out $EXP\audit\<name>.json
python $EXP\tools\collect_results.py --runs-root $EXP\runs --out $EXP\tables --with-audit
python $EXP\tools\summarize.py --runs-json $EXP\tables\runs.json --prefix c1 --label "Primary"
python $EXP\tools\summarize.py --runs-json $EXP\tables\runs.json --prefix a1 --label "Auxiliary"
python $EXP\tools\plot_search_curves.py --runs-root $EXP\runs --tag-prefix c1
python $EXP\tools\analyze_stage0.py
python $EXP\tools\analyze_gap.py --seed 20261104
python $EXP\tools\param_2r.py --suffix _travel90
python $EXP\tools\param_2r.py --travel 55 --suffix _travel55
python $EXP\tools\plot_2r.py
python $EXP\tools\plot_layers.py --state start=<01_convert> --state on=<ON final> --state off=<OFF final>
python $EXP\tools\route_cases.py --on <ON final> --off <OFF final>
python $EXP\tools\build_manifest.py
```

---

## 7. 复现性说明

1. **预算以计数为主**：主实验在 `d56_candidate_evals` 达到 24000 时停止，
   超调上界是一个 operator 调用的成本（每个 run 的 `strategy_stats.json` →
   `extra.counted_budget` 与 `budget_ledger.json` 给出真实值）。
2. **两组事务序列不可逐位复现**：候选集合不同（OFF 少若干 family），
   同一随机种子会产生不同的接受轨迹；因此**不假设随机序列一致**，
   配对比较只用相同种子这一层对应关系。
3. **墙钟不是主实验的停止条件**，只作为安全网记录；辅助实验才是等墙钟对照。
4. 所有硬性门槛（1024/1024、R15、D56、3D 净空、Validator 0 violations、
   OFF 多圆弧区域 = 0）在 `tables/summary_*.md` 中逐 run 列出。
5. 历史归档（1185 / 1202 / 3484）保持不变，仅作参照；新结果若更优，
   只登记为"新最优"，不替换历史基线。
