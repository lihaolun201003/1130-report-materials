# 20 层 G4 平面多段组合圆弧消融实验（原始设计迁移版，1024 通道）

**实验目录：** `experiments/20H_G4_MULTI_ARC_ABLATION_1024/`
**模型：** 20 层物理高度（18 body + 2 interface，z = −0.325 … +0.625 mm，50 µm 间距）
**唯一算法变量：** `G4_ENABLE_MULTI_ARC = 1 / 0`
**状态：** 完成；两组最终解均通过独立 20H Validator（`native3d.validate_native3d`，1024/1024，0 violations）

---

## 0. 结论速览

| 指标 | ON 组（多圆弧开启） | OFF 组（多圆弧关闭） | 差值 |
|---|---:|---:|---:|
| 起点 | 20H G3 合法最优 1395 | Stage-0 转换后 4548 | — |
| 搜索 | G4c-free 1800 s + G4d 1200 s，seed 20261104 | 同 | 同 |
| **最终交叉事件** | **1305** | **3980** | **+2675（×3.05）** |
| 唯一交叉线路对 | 1234 | 3107 | +1873 |
| 最大单线路交叉 | 17 | 46 | +29 |
| 有交叉线路数 | 657 | 932 | +275 |
| 总长度 (mm) | 156603.60 | 164867.72 | +8264.13（+5.01 %） |
| 平面多圆弧区域 / 线路 | 210 / 208 | **0 / 0** | — |
| 独立 Validator | PASS，0 violations | PASS，0 violations | — |

**直接回答：** 同一 20 层框架、同一 1024 连接、同一 R15/D56/三维净空、同一 G4 引擎与预算下，
关闭平面多圆弧后最终交叉从 **1305 升到 3980（×3.05）**；其中 **+3153 发生在几何重表达阶段
（effect A）**，随后的同一 ALNS 收回 478（effect B），最终净差 +2675。

与 21 层历史实验（`G4_MULTI_ARC_ABLATION_1024`：ON 1202 / OFF 3484，×2.90；A=+2645）
方向、量级与机制一致；20 层的转换代价更大（+3153），因为 20 层最终解含多圆弧的线路从
197 条增加到 **213 条**，且少一个 body 高度使替代绕行更贵。

---

## 1. 实验设计与唯一变量

| 项 | ON 组 | OFF 组 |
|---|---|---|
| 起点 | `COLD_START_20_HEIGHT_1024/07_g123/run_xyz_joint_1024_20h/best_valid`（1395） | `01_common_start/`（4548，0 多圆弧） |
| `G4_ENABLE_MULTI_ARC` | 1 | 0 |
| G4c-free | 1800 s，seed 20261104 | 1800 s，同 seed |
| G4d | 1200 s，从 G4c-free 的 `best_valid` 继续 | 1200 s，同 |
| 1024 连接 / 端口 | 不变 | 不变 |
| R15 / 严格 D56 / 3D ≥0.05 mm / 20 高度 / 玻璃 | 不变 | 不变 |
| 交叉口径 | 冻结 strict-D56 独立复算 | 同 |
| Validator | 独立 20H 进程 `validate_xyz` | 同 |

关闭机制与 21H 完全相同：`layer2d._LayerRouter._iter_candidates` 先按 `('S', shift)` 过滤
候选规格，再对每个构建候选做几何硬门（切点连续 + 转向相反 + 圆心不同 → 丢弃）。

---

## 2. Stage-0 几何审查与 OFF 合法化（含 route 456）

### 2.1 20H G3 起点的多圆弧审查（`00_audit/`）

| 项 | 值 |
|---|---:|
| 多圆弧线路 / 局部区域 | **213 / 215** |
| 七种专利构型实例（独立分类器） | 6a 108、6b 56、6c 4、6d 1、7a 16、7b 23、7c 5（合计 213） |
| 其中 2 条线路各含 2 个独立 S 区域（route 149、967），仍各计 1 个组合实例 | — |

### 2.2 OFF 转换（`01_common_start/`）

- 对 **213 条**含平面多圆弧的线路，用**与 G4 完全相同的 planner**（`JointWorld.plan_candidates`，
  `mode='clean'`）重规划；冻结配置无候选时执行确定性扩展搜索（最多 20 个高度、6 组 lead、
  d56_top=64、max_return=8），仍无候选才记 residual。
- 结果：**converted 213 / residual 0**；交叉 **1395 → 4548（A = +3153）**；
  独立 Validator PASS；平面多圆弧区域 **0**。
- **route 456 修复：** 冻结的 3 高度搜索在 20 层表中找不到 OFF 合法体；扩展搜索在
  plane 3（z = −0.275 mm）找到合法 OFF 体，逐条精确交叉增量 **−11**。该调整只扩大搜索范围，
  不改变候选语法/约束/Validator。转换报告记录 `escalated_route_ids: [456]`。
- 非目标线路逐字节不变（`non_target_changed = 0`），1024 端口身份不变。

### 2.3 转换代价的几何成因：2R = 30 mm 阈值

| 继承线路的横向错位 \|bx\| | 线路数 | Σ 交叉增量 | 平均 |
|---|---:|---:|---:|
| **< 2R (30 mm)** | **149** | **+3138** | **+21.06** |
| ≥ 2R (30 mm) | 64 | +15 | +0.23 |

与 21H 的 +2646 / −1 断崖完全同型：多圆弧是亚 2R 横向错位的紧凑表达；取消后这类线路只能走
≥4R 的绕行环路。图：`05_figures/offset_2r/offset_2r_threshold.png`。
逐层转换代价见 `02_experiment1/tables/conversion_summary.md`（L6/L7/L20/Z1/L8 最重）。

---

## 3. 结果与分解

### 3.1 五个状态（独立复算）

| 状态 | 交叉 | 唯一对 | 最大/线 | 总长度 mm | 多圆弧区域/线路 |
|---|---:|---:|---:|---:|---:|
| G3 起点 | 1395 | 1325 | 20 | 156735.57 | 215 / 213 |
| OFF 共同起点 | 4548 | 3378 | 58 | 164949.03 | 0 / 0 |
| ON G4c-free | 1305 | 1234 | 17 | 156603.60 | 210 / 208 |
| **ON 最终（G4d）** | **1305** | **1234** | **17** | **156603.60** | **210 / 208** |
| OFF G4c-free | 4018 | 3108 | 45 | 164929.97 | 0 / 0 |
| **OFF 最终（G4d）** | **3980** | **3107** | **46** | **164867.72** | **0 / 0** |

### 3.2 交叉变化的完整分解

```
G3 起点                                1395
  + Stage-0 OFF 转换（213 条）          +3153  →  4548      ← effect A
  + G4c-free（1800 s，OFF）              −530  →  4018
  + G4d（1200 s，OFF）                    −38  →  3980      ← OFF 交付值（搜索共 −568）

ON 对照（同一引擎、同一预算）
G3 起点                                1395
  + G4c-free（1800 s，ON）               −90  →  1305
  + G4d（1200 s，ON）                      0  →  1305      ← ON 交付值
```

**最终差 2675 = A 3153 − (OFF 搜索 568 − ON 搜索 90)。**
OFF 组搜索收益（−568）大于 ON 组（−90），说明搜索机制没有变差；差的是几何表达力。
G4d 在 ON 组从 1305 未再下降（事务均无净交叉改善），在 OFF 组继续下降 38。

### 3.3 最终 ON/OFF 的全局对照

| 指标 | ON | OFF | 说明 |
|---|---:|---:|---|
| 交叉 | 1305 | 3980 | ×3.05 |
| 唯一对 | 1234 | 3107 | +1873 |
| 最大单线交叉 | 17 | 46 | ON 尾部更短 |
| 有交叉线路 | 657 | 932 | +275 |
| 总长度 | 156603.60 | 164867.72 | ON **短 8264.13 mm（−5.01 %）** |
| flat 弧 / 直线 | 1840 / 4271 | 1944 / 4657 | ON 弧更少、直线更少 |
| transition / mid | 1948 / 86 | 1932 / 50 | 接近 |
| min 3D 净空 | 0.062213 | 0.062213 | 均远高于 0.05 |
| min 非交叉中心线 | 0.086853 | 0.094709 | 均 ≥0.08 |
| Validator | PASS / 0 | PASS / 0 | 独立新进程 |

ON 不仅交叉少，**路径也更短 5.0 %**，因此“多圆弧靠更长绕路换交叉”的解释被否证。

### 3.4 逐层影响

`02_experiment1/tables/exp1_per_height.csv` 给出 20 个高度的交叉事件/对/线路数。
转换代价集中在 L6/L7/L20/Z1/L8（见 §2.3 表）；OFF 最终解把这些绕行分散到更多高度。
图：`05_figures/layer_stats/layer_stats_bars.png`、`05_figures/compare_layers/`。

---

## 4. 图件与数据

| 交付 | 路径 |
|---|---|
| 20 层 ON 逐层布线/交叉图 | `05_figures/layers_*/per_height_{plain,crossings}/` |
| ON vs OFF 逐层左右对照（20 张 + 总览） | `05_figures/compare_layers/` |
| 三维全局布线对照 | `05_figures/global3d/` |
| 典型线路局部几何对照 | `05_figures/route_cases/` |
| 2R 阈值分析 | `05_figures/offset_2r/` |
| 搜索曲线（三轴） | `05_figures/curves/` |
| 核心表 | `02_experiment1/tables/exp1_states.csv`、`exp1_decomposition.json`、`conversion_summary.{md,csv}` |
| 独立验证 | 各 `validation_final/validation.json`（`validate_xyz`，20 planes，0 violations） |

---

## 5. 复现

```powershell
cd "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D"
$PY = ".venv\Scripts\python.exe"
& $PY experiments\20H_G4_MULTI_ARC_ABLATION_1024\tools\run_exp1.py audit
& $PY experiments\20H_G4_MULTI_ARC_ABLATION_1024\tools\run_exp1.py convert
& $PY experiments\20H_G4_MULTI_ARC_ABLATION_1024\tools\run_exp1.py on
& $PY experiments\20H_G4_MULTI_ARC_ABLATION_1024\tools\run_exp1.py off
& $PY experiments\20H_G4_MULTI_ARC_ABLATION_1024\tools\run_exp1.py validate
& $PY experiments\20H_G4_MULTI_ARC_ABLATION_1024\tools\run_exp1.py collect
```

实际命令、日志、SHA256 见 `logs/`、各状态 `SHA256.json`、`02_experiment1/tables/exp1_metrics.json`。

---

## 6. 因果性与限制（必须与 §0 一起读）

1. **两组起点几何不同**：OFF 组为了真正取消多圆弧，必须先做一次 213 条线路的投影
   （1395 → 4548）；ON 组保留原几何。因此 1305 与 3980 的差异包含一次性转换代价 A。
   本报告把 A（+3153）与搜索能力 B（−478 净）分开，不把 A 记作“优化质量”。
2. **消融语义**：关闭多圆弧等价于把候选几何集合收缩；投影代价是这次消融的核心测量值，
   不应与搜索收益相加成单一“多圆弧价值”。
3. **20H vs 21H 不是同一物理模型**：20H 少一个 body 高度，G3 起点 1395（21H 1322）。
   本实验只回答“20 层下 ON/OFF 的差异”，跨层比较仅作参照。
4. **ON 组 G4d 无净收益**（1305→1305），说明 ON 侧在 G4c-free 后已接近该邻域局部最优；
   这不影响对照，但应如实记录。
5. **单种子**（20261104）用于本实验（与 21H 原始消融一致）；三随机种子的严格版本见
   `20H_G4_MULTI_ARC_ABLATION_FINAL_1024/`。
6. 全部数值来自真实运行产物与独立复算，无估算；Validator、R15、D56、三维净空、玻璃、
   1024 连接、端口身份均未放松。
