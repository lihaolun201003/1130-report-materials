# RUNBOOK — G4 多圆弧消融实验（可复现命令 / 种子 / 参数 / SHA256 / 代码修改）

本文件给出**实际执行过的每一条命令**、随机种子、预算参数、输入输出 SHA256 与代码修改，
使 `experiments/G4_MULTI_ARC_ABLATION_1024/` 的全部产物可被独立复现。

---

## 1. 环境

| 项 | 值 |
|---|---|
| OS | Windows 11 (10.0.26100) |
| CPU | Intel Core i9-13900HX（24C/32T），单进程串行运行，避免墙钟预算被争抢 |
| Python | 3.10.11 (`C:\Users\lihao\AppData\Local\Programs\Python\Python310\python.exe`) |
| numpy | 2.2.6 |
| matplotlib | 3.10.9 |
| 工作目录 | `C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D` |

> 归档 G4 运行于 2026-11-04（当时 numpy/matplotlib 版本可能不同）。本实验的所有对照
> 都在**同一台机器、同一套当前代码、同一环境**下重跑，故组间可比；与历史归档值的
> 差异单独报告（见 §7）。

## 2. 数据与代码来源

| 角色 | 路径 | SHA256 |
|---|---|---|
| 公共起点（G3 合法最优解） | `outputs/manual_c4_new_connectivity/XYZ_JOINT_G123_1024/best_valid/routes_l3d.json` | `711cf910d5c75ea788be877ef88b588fe3d59a90a2ae2d3636bb5b5896834077` |
| G4 原始最终解（只读） | `work/11.9-second-report-all-work/g4_xyz_joint_1024/03_best_valid/routes_l3d.json` | `b74ae51185edcef43419c3157d07e24237bf05f10e50321310b554f487e9e77a` |
| G4 原始 crossing_stats（只读） | 同目录 `crossing_stats.json` | `c526abdaabe2296a797f0c443340bb74a0ba5e114334d6306b4fbd6649f73e97` |
| 身份/端口权威基线（只读） | `outputs/manual_c4_new_connectivity/XYZ_JOINT_G123_1024/baseline_authoritative/` | — |

**源码版本控制状态**

* `OpticalWaveguideRouter2D/` **不是 git 工作树**（无 `.git`）。
* 归档仓库 `work/11.9-second-report-all-work` 是 git 仓库，HEAD = `0e927d891b9dadb8193dc5c3d9e0d6d0c9fbb562`（2026-11-04）。
* 因此本实验用 **反向补丁** 记录代码修改：`code_changes/g4_multi_arc.patch`（110 行新增，
  0 行删除，纯增量），原始文件重建件 `code_changes/*.orig` 与修改后快照 `code_changes/*.after` 一并归档。
* 本目录自身在交付时建立独立 git 仓库并提交，commit 记录见 `GIT_COMMIT.txt`。

### 2.1 代码修改（唯一一处语义变更）

`four_side_1024/fanout1024/layer2d.py`

1. 新增 `MULTI_ARC_POLICY / multi_arc_enabled(cfg) / local_multi_arc_regions(prims) / spec_uses_multi_arc(spec)`；
2. `_LayerRouter.__init__` 读取开关；
3. `_LayerRouter._iter_candidates`：
   * 关闭时先按 `('S', shift)` move 过滤候选规格（保存 build 预算）；
   * 再对每个已构建候选做**几何硬门**：任何"同一切点连续、方向相反的圆弧串"一律丢弃。
4. env 变量 `G4_ENABLE_MULTI_ARC`（默认 `1`），也可由 `cfg['enable_multi_arc']` 覆盖。

`four_side_1024/fanout1024/xyzrouter/local_reroute.py`

5. `xy_candidates()` 把策略写入 `router_cfg`，使 G4 的全部候选生成路径统一受控。

**默认行为不变**：不设 `G4_ENABLE_MULTI_ARC=0` 时，代码路径与归档完全一致（纯增量补丁）。

## 3. 判定口径（消融的"多圆弧"到底指什么）

只取消**同一局部平面转弯/避让区域内的多段组合圆弧**，即两个切点相连、转向相反的 R15 圆弧对
（frozen D56 `('S', shift)` short-S）。明确**不**取消：

| 类别 | 处理 |
|---|---|
| `Z` / 阶梯家族（两段四分之一圆弧**中间夹直线**） | 保留（不同转角处的独立圆弧） |
| `same_circle_split`（同一圆被拆成两条 arc 记录，如 `middle=0` 的 180° U 弯） | 保留（仅存储/数值拆分） |
| 三维 `z` 升降的 R15 双弧 S transition（`kind='transition'`） | 保留（不属于平面 flat 链） |

统计口径由 `local_multi_arc_regions()` 实现：对每条 flat 链求"切点连续的最大圆弧串"，
只有长度 ≥2 且**圆心不同**（排除同圆拆分）且**转向相反**的串才算多圆弧区域。

## 4. 实验流程（实际命令）

以下命令均在工作目录 `OpticalWaveguideRouter2D` 下执行。

### 4.1 基线审查（任务一 + 任务二第 2 步）

```powershell
# 21 张分层图 + 拼图 + 逐层统计（复用 g4/plots_g4.py 的 plot_layer_suite）
python -m four_side_1024.fanout1024.xyzrouter.g4.plots_g4 layer-suite `
  --run-dir "C:\Users\lihao\Desktop\Graduation Project\work\11.9-second-report-all-work\g4_xyz_joint_1024\03_best_valid" `
  --out-dir experiments\G4_MULTI_ARC_ABLATION_1024\layer_figures\G4_baseline `
  --prefix G4_baseline --title "G4 original (1185 crossings)"

# 平面多圆弧几何审计（G3 起点 / G4 最终 / NoMultiArc 转换后）
python experiments\G4_MULTI_ARC_ABLATION_1024\tools\audit_flat_multi_arc.py `
  outputs\manual_c4_new_connectivity\XYZ_JOINT_G123_1024\best_valid `
  "C:\Users\lihao\Desktop\Graduation Project\work\11.9-second-report-all-work\g4_xyz_joint_1024\03_best_valid" `
  --out experiments\G4_MULTI_ARC_ABLATION_1024\baseline_audit `
  --label G3_start_1322,G4_best_1185

# 归档 G4 最终解的独立 Validator 复核
python -m four_side_1024.fanout1024.xyzrouter.validate_xyz `
  --run-dir "C:\...\g4_xyz_joint_1024\03_best_valid" `
  --out-dir experiments\G4_MULTI_ARC_ABLATION_1024\validation\baseline_G4_best_1185 `
  --manual-policy fully_optimizable `
  --baseline-dir outputs\manual_c4_new_connectivity\XYZ_JOINT_G123_1024\baseline_authoritative
```

### 4.2 候选生成器策略自检

```powershell
python experiments\G4_MULTI_ARC_ABLATION_1024\tools\test_multi_arc_policy.py
```
输出 `baseline_audit/multi_arc_policy_smoke_test.json`：策略关闭时**每个**已构建候选的
多圆弧区域数必须为 0（脚本内断言）。

### 4.3 对照组 Stage-0：把继承的多圆弧几何重造为单圆弧

```powershell
$env:G4_ENABLE_MULTI_ARC = '0'
python experiments\G4_MULTI_ARC_ABLATION_1024\tools\convert_multi_arc.py `
  --start-dir outputs\manual_c4_new_connectivity\XYZ_JOINT_G123_1024\best_valid `
  --out-dir   experiments\G4_MULTI_ARC_ABLATION_1024\no_multi_arc\01_convert
```
* 目标集合 = 起点解中**含平面多圆弧区域的 197 条**线路（确定性、由几何判定，不依赖随机数）。
* 每条线路用**与 G4 搜索完全相同的 planner**（`joint_world.PLAN_CFG`：3 个自由目标高度、
  2 组 lead、预筛 160/320、`d56_top=16`、每组 4 候选）在同一三维 World 内重规划；
  接受**精确交叉增量最小**的合法候选；高度、lead 可动（与搜索同权）。
* 无合法候选的线路保留原几何并记为 residual（本次 = 0）。

### 4.4 两个臂（唯一差别 = 环境变量）

```powershell
# 原始组同代码对照（multi-arc ON）
powershell -NoProfile -ExecutionPolicy Bypass -File `
  experiments\G4_MULTI_ARC_ABLATION_1024\tools\run_arm_chain.ps1 -Arm on

# 对照组（multi-arc OFF）
powershell -NoProfile -ExecutionPolicy Bypass -File `
  experiments\G4_MULTI_ARC_ABLATION_1024\tools\run_arm_chain.ps1 -Arm off
```

每个臂内部执行（脚本逐条记录到 `<arm>/chain_console.log`）：

```powershell
python -m four_side_1024.fanout1024.xyzrouter.g4.run_g4_engine `
  --arm G4c_free --seconds 1800 --seed 20261104 `
  --start-dir <start> --out-dir <arm>\02_G4c_free --tag ablation_<arm>
python -m four_side_1024.fanout1024.xyzrouter.validate_xyz `
  --run-dir <arm>\02_G4c_free\best_valid --out-dir <arm>\02_G4c_free\validation `
  --manual-policy fully_optimizable --baseline-dir outputs\...\baseline_authoritative
python -m four_side_1024.fanout1024.xyzrouter.g4.run_g4_engine `
  --arm G4d --seconds 1200 --seed 20261104 `
  --start-dir <arm>\02_G4c_free\best_valid --out-dir <arm>\03_G4d --tag ablation_<arm>
python -m four_side_1024.fanout1024.xyzrouter.validate_xyz `
  --run-dir <arm>\03_G4d\best_valid --out-dir <arm>\03_G4d\validation `
  --manual-policy fully_optimizable --baseline-dir outputs\...\baseline_authoritative
```

| 臂 | start | G4_ENABLE_MULTI_ARC | G4c_free | G4d | seed |
|---|---|---|---|---|---|
| `baseline_rerun`（on） | G3 `711cf910…`（1322） | `1` | 1800 s | 1200 s | 20261104 |
| `no_multi_arc`（off） | `01_convert`（转换后起点 `1707e189…`，3967） | `0` | 1800 s | **158 s（提前停在安全检查点）** | 20261104 |

> **off 臂 G4d 提前停止说明**：`G4d` 在 `checkpoints/step_00009`（total=3484，已完整写出
> routes/assignment/ledger/checkpoint.json）后由操作者主动停止，未跑满 1200 s，
> 因此 off 臂搜索墙钟为 1994.1 s（G4c 1836.2 + G4d 157.9），比 on 臂 3119.3 s 少约 36%。
> 交付值为该安全检查点的 `best_valid`，停止后用冻结独立 Validator 重新验收（PASS / 0 violations）。
> 该状态由 `tools/materialize_final.py` 物化为 `04_final/`（routes/assignment 逐字节复制，
> SHA256 不变，另写入由同一引擎计算的 `crossing_stats.json`/`summary.json` 并复制 validation）。

`stage sizes / fractions`：G4c_free `8/16/32/64 → 0.22/0.24/0.26/0.28`，sweep ratio 0.18（默认）；
G4d `16/32/64/96 → 0.20/0.24/0.26/0.30`，sweep ratio 0.12（默认）。其余全部使用引擎默认参数。

### 4.5 图表、表格、汇总

```powershell
python experiments\G4_MULTI_ARC_ABLATION_1024\tools\analyze_conversion.py
python experiments\G4_MULTI_ARC_ABLATION_1024\tools\make_report_artifacts.py `
  --baseline "C:\...\g4_xyz_joint_1024\03_best_valid" `
  --nomat experiments\G4_MULTI_ARC_ABLATION_1024\no_multi_arc\03_G4d\best_valid `
  --out experiments\G4_MULTI_ARC_ABLATION_1024
python experiments\G4_MULTI_ARC_ABLATION_1024\tools\build_summary.py
python experiments\G4_MULTI_ARC_ABLATION_1024\tools\build_manifest.py
```

## 5. 关键参数（与归档 G4 完全一致，未做任何放宽）

| 约束 | 值 |
|---|---|
| 玻璃 | 150 × 150 × 1 mm，z ∈ [−0.35, +0.65] |
| 物理高度 | 21（19 body + 2 interface） |
| Rmin | 15 mm（所有圆弧恰为 R15，未降低） |
| 同层规则 | frozen strict D56（0.05 波导 + 0.03 边距 = 0.08 mm 中心线，≥5° 合法横穿豁免） |
| 跨高度净空 | 真 3D 中心线 ≥ 0.05 mm |
| 连接数 | 1024（未删减） |
| 交叉口径 | frozen `nonc4.crossings.audit_flat_group`（与 G4/Validator 完全同源） |
| Validator | `--manual-policy fully_optimizable`，冻结独立进程 |

## 6. 产物 SHA256

见 `MANIFEST.json`（全量）与 `SHA256SUMS.csv`（扁表）。关键件：

| 文件 | 说明 |
|---|---|
| `no_multi_arc/01_convert/conversion_report.json` | 197 条线路逐条转换记录 + 校验（转换后 `routes` SHA256 `1707e189…`，3967） |
| `no_multi_arc/03_G4d/best_valid/routes_l3d.json` | 对照组最终解 SHA256 `7e3674c5…`，**3484 / 2707** |
| `no_multi_arc/03_G4d/validation/validation.json` | 对照组最终独立验收（PASS，violations 0，min 3D 0.068629） |
| `no_multi_arc/02_G4c_free/best_valid` | 对照臂第一里程碑（3520），已独立验收 PASS |
| `baseline_rerun/03_G4d/best_valid/routes_l3d.json` | on 对照最终解 SHA256 `9db061d6…`，**1202 / 1143** |
| `baseline_rerun/03_G4d/validation/validation.json` | on 对照最终独立验收（PASS） |
| `validation/baseline_G4_best_1185/validation.json` | 归档 G4 原始解（`b74ae511…`，1185 / 1124）的独立复核 |
| `comparison/core_table.json` / `.md` | 核心对照表（含 Validator 自报的交叉数、净空、配对数） |

## 7. 复现性说明与局限（必读）

1. **搜索预算以墙钟为主**：G4 各阶段的 `route_3d_checks / d56_candidate_evals` 上限
   (30000 / 120000) 从未触顶（历史利用率 5–24%），因此实际生效的是 1800 s / 1200 s 墙钟预算，
   同机串行执行使两臂条件一致，但**逐位不可复现**（机器负载会改变事务次数）。
2. **与历史归档的差异**：本次 ON 对照重跑 1322 → **1202**，历史归档 G4c_free+G4d 为 1322 → **1185**，
   差 **+17 (+1.4%)**。原因：(a) 墙钟预算下的随机事务序列不同；(b) 当前代码的贪心 sweep 实现
   与归档日志（`sweep round` vs `sweep pass`）已不同，同预算下多接受了若干次迁移；
   (c) 归档 G4c_free 曾中断后 `--resume` 续跑。因此**因果结论以"同代码 ON 对照 vs OFF"为主**，
   以归档 1185 为历史参照。
3. **Stage-0 转换是"把继承几何用消融语法重新表达"的必要步骤**，其代价单独计入并单独报告，
   不与搜索收益混为一谈。
4. 本实验只改变平面候选语法，**未**改变：Validator、交叉口径、D56 规则、R15、玻璃尺寸、
   高度集合、1024 连接、目标函数、ALNS/联合让路/人工 U 策略。
5. 未在"从零重新设计布线系统"的意义上做联合优化（例如重新选择 fanout 落点使
   横向错位 ≥2R）；本实验固定同一框架与同一起点，只隔离该几何自由度。
6. **off 臂 G4d 提前停止**（158 s / 1200 s，total=3484）：两组搜索墙钟不等（1994 s vs 3119 s），
   因此 3484 应读作"受限语法下的上界"，不是收敛值；报告的因果分解（§report.md §4.2、§6）
   已把这一不对称计入。
7. **两臂起点几何不同**（1322 vs 3967）：这是"取消该几何自由度"的必要投影，不是配置差异；
   投影代价 +2645 单独计量，不得与"搜索收益"混算。
