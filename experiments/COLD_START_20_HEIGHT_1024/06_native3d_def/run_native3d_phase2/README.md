# run_native3d_phase2 — Phase 2（D/E/F：多线联合让路 + 圆弧重构 + 全局优化）

继承 Phase-1 Native 3D 的 3103 交叉合法解，研究“联合修改周围线路创造换层空间”与“圆弧区域整体重构”两条路线，并整合为全局优化器。

## 目录

* `experiment_D/` — D0 阻挡分析（blocker_map.json）+ D1/D2 联合 make-way 重布结果
* `experiment_E/` — E0 圆弧交叉分析 + E1/E2 圆弧区域整体重构结果
* `experiment_F/` — 全局联合优化（plain/arc_span/joint 策略，检查点）
* `best_valid/` — 当前最佳合法解（routes + stats + validation + 哈希）
* 根目录交付见 `SPEC.md` 与 `MANIFEST.json`

## 复现

```
cd OpticalWaveguideRouter2D
.venv\Scripts\python.exe -m four_side_1024.fanout1024.coldstart20.run_native3d_phase2 all
```

Phase-1 基线为只读输入：`C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\experiments\COLD_START_20_HEIGHT_1024\05_native3d_abc\run_native3d_phase1\experiment_C`（3103 交叉）。

