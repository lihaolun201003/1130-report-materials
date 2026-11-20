# G6 复现说明（Reproduction）

本目录是可从干净仓库复现 G6 结果的**全部**输入、代码快照、运行配置与可执行命令。
所有路径相对于工程根目录（`OpticalWaveguideRouter2D/`，下文记作 `$ROOT`）。

## 0. 环境

| 项 | 值 |
|---|---|
| OS | Windows 10/11（本机 Windows 10.0.26200） |
| Python | 3.10.11（`$ROOT\.venv\Scripts\python.exe`） |
| 依赖 | numpy 2.2.6、scipy 1.15.3、matplotlib 3.10.9、pandas 2.3.3 |
| 机器 | 32 logical CPUs / 15.7 GB RAM；本轮全部实验实际耗时约 2.5 小时（12 种子并行） |

所有命令均在 PowerShell 中：

```powershell
$ROOT = "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D"
$PY   = "$ROOT\.venv\Scripts\python.exe"
$EXP  = "$ROOT\experiments\G6_ANGLE45_MULTIARC_SA_20H_1024"
$env:PYTHONPATH = $ROOT
Set-Location $ROOT
```

代码快照（与仓库提交一致）在 `$EXP\01_algorithm\code_snapshot\`。若只想从快照运行，
把 `$env:PYTHONPATH` 指向该目录即可（快照中含完整 `four_side_1024/` 源码，共 496 个
文件，`CODE_MANIFEST.json` 记录每个文件的 SHA256）。

## 1. 冻结基线（只读，仓库已附带）

```powershell
# G5 51 违规解：Validator A + B 复核（约 60 s + 2 s）
& $PY "$ROOT\experiments\G5_ANGLE45_NATIVE3D_20H_1024\01_algorithm\run_validation.py" `
  --source "$EXP\00_baseline\frozen_g5_v5" `
  --out    "$EXP\00_baseline\validation_g5_v5"
# -> A PASS, B FAIL(51), min 6.122694 deg
```

冻结输入的 SHA256 见各目录 `SHA256.json` / `BEST_VALID.json`；G5 v5 的 routes SHA256 =
`95f4d6bf1ca0942cb7e3f836f4c12d9141ca016a279a38d968a05d181a29a485`（与 G5 报告一致）。
G4 冻结解（`00_baseline/frozen_g4_10_best_valid`）与 stage-03 早期起点
（`00_baseline/frozen_stage03_multiarc`）的独立 45° 复算结果分别在
`00_baseline/validation_g4/` 与 `00_baseline/validation_stage03/`
（1283/304 与 12338/1365）。

## 2. 早期起点（研究方案 A）：角度感知 MultiArc 生成

在**逐字节相同的**冻结 stage A/B（层分配 + 端口 R15 扇出）上重跑 C–F：

```powershell
# A0 对照：角度盲（复现冻结的 1365 次 <45 度）
& $PY -m four_side_1024.fanout1024.xyzrouter.g6.run_early `
  --frozen-stage03 "$ROOT\experiments\COLD_START_20_HEIGHT_1024\03_fanout_and_xy\run_initial_20h" `
  --out "$EXP\02_sa_runs\early2\early_off" --angle-aware 0 --stages CDEF --max-iters 3

# A1 G6：角度感知 MultiArc 候选选择（1365 -> 1166，-14.6%）
& $PY -m four_side_1024.fanout1024.xyzrouter.g6.run_early `
  --frozen-stage03 "$ROOT\experiments\COLD_START_20_HEIGHT_1024\03_fanout_and_xy\run_initial_20h" `
  --out "$EXP\02_sa_runs\early2\early_on" --angle-aware 1 --angle-pool 24 `
  --stages CDEF --max-iters 3

# 早期解的工程验收（A PASS / B FAIL 1166，中间状态，非最终解）
& $PY "$ROOT\experiments\G5_ANGLE45_NATIVE3D_20H_1024\01_algorithm\run_validation.py" `
  --source "$EXP\02_sa_runs\early2\early_on" `
  --out "$EXP\02_sa_runs\early2\early_on\validation"

# 同一 G6 退火内核从早期起点继续搜索
& $PY -m four_side_1024.fanout1024.xyzrouter.g6.run_g6 `
  --start "$EXP\02_sa_runs\early2\early_on\routes_l3d.json" `
  --out "$EXP\02_sa_runs\early_SA_B" `
  --seeds 3001,3002,3003,3004,3005,3006 --workers 6 `
  --profile B --seconds 1200 --cycles 4 --cycle-seconds 300 --T0 700 --T0-decay 0.9
```

## 3. Warm Start（研究方案 B）：G5 51 违规解 + MultiArc 退火

```powershell
& $PY -m four_side_1024.fanout1024.xyzrouter.g6.run_g6 `
  --start "$ROOT\experiments\G5_ANGLE45_NATIVE3D_20H_1024\best_partial_v5\routes_l3d.json" `
  --out "$EXP\02_sa_runs\warm_B_v4" `
  --seeds 1001,1002,1003,1004,1005,1006,1007,1008,1009,1010,1011,1012 --workers 12 `
  --profile B --seconds 1920 --cycles 8 --cycle-seconds 240 `
  --T0 700 --T0-decay 0.9 --log-seconds 120
```

每个种子 8 个 cycle、总预算 1920 s；12 个种子并行。结果见
`02_sa_runs/warm_B_v4/sweep_summary.json`（最好 seed 1008：51 → 4）。

## 4. 确定性收尾：残余违规穷举修复

```powershell
& $PY -m four_side_1024.fanout1024.xyzrouter.g6.run_polish `
  --routes "$EXP\02_sa_runs\best_snapshots\seed_1008_sa_best.json" `
  --out "$EXP\02_sa_runs\polish_1008" `
  --seconds 1500 --passes 60 --body-build 700 --pair-keep 14 --pair-attempts 240
# -> N_bad = 0, hard_issues = 0, reaudit_matches = true
```

## 5. 最终双验收（Validator A + B）

```powershell
& $PY -m four_side_1024.fanout1024.xyzrouter.g6.finalise `
  --routes "$EXP\02_sa_runs\polish_1008\best_routes.json" `
  --companions "$EXP\00_baseline\frozen_g5_v5" `
  --out "$EXP\03_best_feasible" --label G6
# -> A pass = true, B pass = true, G6_ANGLE45_VALID_PASS = true
```

输出：`03_best_feasible/routes_l3d.json`（含 SHA256）、`g6_validation_verdict.json`、
`validation/frozen/validation.json`、`validation/independent/g5_angle_validation.json`。

## 6. 算法自检（边界 / 一致 / 回滚 / 重生成）

```powershell
& $PY -m four_side_1024.fanout1024.xyzrouter.g6.selftest `
  --routes "$EXP\03_best_feasible\routes_l3d.json" `
  --out "$EXP\04_validation\selftest_best_feasible"
# -> 7/7 PASS（含独立验证器 28 项解析自检、44.9/44.999/45.0/45.001/90 边界）
```

## 7. 51 次残余追踪 / 图 / 报告

```powershell
& $PY -m four_side_1024.fanout1024.xyzrouter.g6.track_residual `
  --before "$EXP\00_baseline\validation_g5_v5\independent\g5_crossing_angles.csv" `
  --after  "$EXP\03_best_feasible\validation\independent\g5_crossing_angles.csv" `
  --out "$EXP\06_reports" --radius 20

& $PY "$EXP\01_algorithm\make_figures.py"
& $PY "$EXP\01_algorithm\build_report.py" --git-commit <commit>
```

## 8. 邻域消融（B/C/D/E，固定起点/种子/移动预算）

```powershell
& $PY "$EXP\01_algorithm\run_ablations.py" `
  --start "$ROOT\experiments\G5_ANGLE45_NATIVE3D_20H_1024\best_partial_v5\routes_l3d.json" `
  --arms B,C,D,E --seeds 4001,4002,4003,4004 --max-moves 1500 --workers 4
```

## 9. 完整可复现实验清单（实际执行记录）

| 实验 | 目录 | 实际预算 | 结果 |
|---|---|---|---|
| 基线双验收 | `00_baseline/validation_g5_v5` | 60 s + 2 s | A PASS / B 51 |
| 早期构造 A0（greedy） | `02_sa_runs/early2/early_off` | 236 s | 1365 |
| 早期构造 A1（angle-aware） | `02_sa_runs/early2/early_on` | 676 s | 1166 |
| 早期起点 G6 SA | `02_sa_runs/early_SA_B` | 6×4×300 s | 最好 678 |
| Warm Start G6 SA | `02_sa_runs/warm_B_v4` | 12×8×240 s | 最好 4 |
| 确定性收尾 | `02_sa_runs/polish_1008` | 29 s | **0** |
| 最终双验收 | `03_best_feasible` | 63 s | **A+B PASS** |
| 算法自检 | `04_validation/selftest_best_feasible` | 9 s | 7/7 PASS |
| 邻域消融 | `02_sa_runs/ablations` | 4 arms × 4 seeds × 1500 moves | B=9, C=8, D=0, E=0 |
| 第二零解复核 | `04_validation/alternate_zero_seed1001` | 63 s | **A+B PASS** |

**未运行项会明确标注 n/a，绝不把未运行的实验写成已完成。**
