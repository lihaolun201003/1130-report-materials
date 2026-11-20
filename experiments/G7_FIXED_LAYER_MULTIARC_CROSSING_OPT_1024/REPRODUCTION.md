# G7 复现说明（Reproduction）

本目录包含从冻结 G6 合法解出发、在**固定层分配 + 固定 R15 过渡**下优化交叉数量的全部可复现材料。

## 0. 环境

| 项 | 值 |
|---|---|
| OS | Windows 10/11 | 
| Python | 3.10.11（`$ROOT\.venv\Scripts\python.exe`） |
| 依赖 | numpy、scipy、matplotlib（G7 主流程）；G5 验证器为纯标准库 |
| 机器 | 32 logical CPUs / 15.7 GB RAM |

```powershell
$ROOT = "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D"
$PY   = "$ROOT\.venv\Scripts\python.exe"
$EXP  = "$ROOT\experiments\G7_FIXED_LAYER_MULTIARC_CROSSING_OPT_1024"
$env:PYTHONPATH = $ROOT
Set-Location $ROOT
```

代码快照：`$EXP\01_algorithm\code_snapshot\`（完整 `four_side_1024/` + G5/G6/G7 源码，
`CODE_MANIFEST.json` 记录 SHA256；G5 的 `batch.py`/`layer_solver.py` 也已包含）。

## 1. 冻结 G6 基线

G6 最终合法解 routes SHA256 =
`39a02c9ec9a598d95bb2a6ef6695ab18a849c037fa9ca24c2a76581c55bc57b2`
（`00_frozen_g6/routes_l3d.json`，副本 + `BEST_VALID.json` + G6 双验收 verdict）。

G7 从 **routes_l3d.json 本身**提取每条线路的真实高度序列与全部非主体几何，
生成 `00_frozen_g6/frozen_manifest.json`（1024 条；527 条可修改标准线路，
92 direct / 368 人工 U / 37 native-3D 完全冻结）。**不读取**已与真实高度
不一致的旧 assignment CSV。

```powershell
& $PY -c "import sys; sys.path.insert(0,r'$ROOT'); from four_side_1024.fanout1024.xyzrouter.g7 import frozen as FR; import json; d=json.load(open(r'$EXP\00_frozen_g6\routes_l3d.json',encoding='utf-8')); m=FR.build_manifest(d['routes']); FR.write_manifest(r'$EXP\00_frozen_g6\frozen_manifest.json',m); print(FR.verify_payload(d['routes'],m)['pass'])"
# -> True
```

## 2. 固定层 MultiArc 交叉优化（主实验）

三个实验臂使用同一起点（G6 4578 交叉）、同一 30 分钟预算、同一种子口径；
邻域按臂逐步启用（A=N1；B=+N2+N3；C=+N4+N5）。每次接受都用冻结验证器同一份
`fslw` 严格 D56 成对审计重审被改动的物理层，非法则原子回滚。

```powershell
$START = "$EXP\00_frozen_g6\routes_l3d.json"
# 实验 A：仅 N1
& $PY -m four_side_1024.fanout1024.xyzrouter.g7.run_g7 --start $START `
  --out "$EXP\02_sa_runs\arm_A_n1" `
  --seeds 7101,7102,7103,7104,7105,7106,7107,7108,7109,7110 --workers 10 `
  --profile A --seconds 1800 --cycles 1 --T0 1.0 `
  --pool-size 24 --pool-build 120 --n1-sample 8
# 实验 B：N1+N2+N3
& $PY -m four_side_1024.fanout1024.xyzrouter.g7.run_g7 --start $START `
  --out "$EXP\02_sa_runs\arm_B_joint" --seeds 7201,7202,7203,7204,7205,7206 `
  --workers 6 --profile B --seconds 1800 --cycles 1 --T0 1.0 `
  --pool-size 24 --pool-build 120 --n1-sample 8
# 实验 C：N1–N5（热点/整层）
& $PY -m four_side_1024.fanout1024.xyzrouter.g7.run_g7 --start $START `
  --out "$EXP\02_sa_runs\arm_C_hotspot" --seeds 7301,7302,7303,7304,7305,7306 `
  --workers 6 --profile C --seconds 1800 --cycles 1 --T0 1.0 `
  --pool-size 24 --pool-build 120 --n1-sample 8
```

每个 seed 的 `best_routes.json` 只在交叉数（同数时按最小角裕量/唯一对/长度）
改善且通过固定结构验证时写出；`checkpoints/latest_routes.json` 支持断点恢复
（`--resume`）。

## 3. 固定层确定性收尾

```powershell
& $PY -m four_side_1024.fanout1024.xyzrouter.g7.run_polish_g7 `
  --start "$EXP\02_sa_runs\selected_best\sa_best_routes.json" `
  --reference "$EXP\00_frozen_g6\routes_l3d.json" `
  --out "$EXP\02_sa_runs\polish_best" --seconds 1200 --pool-size 32
```

## 4. 最终验收（A + B + 固定结构）

```powershell
& $PY -m four_side_1024.fanout1024.xyzrouter.g7.finalise_g7 `
  --routes "$EXP\02_sa_runs\polish_best\best_routes.json" `
  --reference "$EXP\00_frozen_g6\routes_l3d.json" `
  --companions "$EXP\00_frozen_g6" `
  --out "$EXP\03_best_valid" --baseline-crossings 4578
# -> A pass, B pass, fixed structure pass, strictly better => G7_FIXED_LAYER_VALID_PASS
```

固定结构验证器也可单独运行：

```powershell
& $PY -m four_side_1024.fanout1024.xyzrouter.g7.verify_fixed `
  --reference "$EXP\00_frozen_g6\routes_l3d.json" `
  --candidate "$EXP\03_best_valid\routes_l3d.json" `
  --out "$EXP\04_validation\fixed_structure"
```

## 5. 分析、图与报告

```powershell
& $PY "$EXP\01_algorithm\run_analysis.py"
& $PY "$EXP\01_algorithm\make_figures_g7.py"
& $PY "$EXP\01_algorithm\build_report_g7.py" --git-commit <commit>
```

## 6. 实际执行记录

| 项目 | 设置 | 结果 |
|---|---|---|
| G6 冻结基线 | 只读 | 4578 交叉 / 3677 对 / min 45.1085° / A+B PASS |
| 实验 A（N1） | 10 seeds × 1800 s | 见 `02_sa_runs/arm_A_n1/sweep_summary.json` |
| 实验 B（N1+N2+N3） | 6 seeds × 1800 s | 见 `arm_B_joint/sweep_summary.json` |
| 实验 C（N1–N5） | 6 seeds × 1800 s | 见 `arm_C_hotspot/sweep_summary.json` |
| 固定层 polish | 确定性 best-improvement | 见 `polish_best/summary.json` |
| 双验收 + 固定结构 | — | `03_best_valid/g7_validation_verdict.json` |

**未运行项会明确标注；不把仅通过搜索侧检查的中间态当作合法解。**
