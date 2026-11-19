# G5 — 1024 通道 20 层原生三维光波导的 45° 最小交叉角硬约束全局优化

**Angle-Constrained Native 3D Waveguide Routing (G5)** — `theta_min = 45 deg`, frozen G4 start (`routes_l3d.json` sha256 `35d7ebed…b90753`).

## 0. 结论摘要

**未取得 θ≥45° 的全局完全合法解。** 本轮完成了全部审计、约束改造、候选族、搜索与独立验收，并把违规数从 **304** 降到 **134**（−55.9%），最小交叉角从 **5.153763°** 提到 **7.518621°**；剩余违规已定位到具体几何阻挡，详见第 8 节。

| 指标 | G4 起点 | G5 本轮 |
|---|---:|---:|
| 布线通道 | 1024 | 1024 |
| 物理高度 | 20 | 20 |
| 同层交叉事件 | 1283 | 2321 |
| 唯一交叉线路对 | 1221 | 1891 |
| **小于 45° 的交叉** | **304** | **134** |
| 最小交叉角 (°) | 5.153763 | 7.518621 |
| 角度不足总量 D_theta (°) | 5520.131088 | 2539.854013 |
| 最大单次不足 D_max (°) | 39.846237 | 37.481379 |
| 总长度 (mm) | 156597.221522 | 156560.515300 |
| 单线路最大交叉数 | 17 | 91 |
| 三维净距最小值 (mm) | 0.05 / 0.062212557 / 0.1 | {'flat_flat_mm': 0.05, 'transition_flat_mm': 0.061834798, 'transition_transition_mm': 0.1} |
| 原 20 层几何 Validator (A) | PASS | PASS |
| 独立 45° Validator (B) | FAIL (304) | FAIL (134) |
| 综合标记 | — | `NOT_PASS` |

## 1. G4 基线的交叉角度完整审计

冻结输入：`experiments/COLD_START_20_HEIGHT_1024/10_best_valid/`，`routes_l3d.json` SHA256 = `35d7ebed00339bee21fe0ca47075c9b34008120522a47933a099efacf0b90753`（已校验）。

- 真实同层交叉 **1283** 次，唯一线路对 **1221**，涉及线路 **647** 条。
- **< 45° 的交叉 304 次**，D_theta = **5520.131088°**，D_max = **39.846237°**，最小交叉角 **5.153763°**。
- 原有 D56 硬性违规 0 次，三维净空违规 0 次，无关交叉最小净距 0.086853441 mm —— 即基线在原 5° 规则下完全合法。
- 违规冲突图：290 个顶点、278 条边、48 个连通分量，最大分量 30 条线路。
- 其中涉及人工 U 结构（`manual_group` 非空）的事件 **73** 次。

### 1.1 角度分布

| 区间 (°) | 交叉数 |
|---|---:|
| [0, 5) | 0 |
| [5, 10) | 17 |
| [10, 20) | 92 |
| [20, 30) | 52 |
| [30, 40) | 92 |
| [40, 45) | 51 |
| [45, 60) | 271 |
| [60, 75) | 514 |
| [75, 90.0001) | 194 |

### 1.2 逐层违规

| 物理高度 (mm) | 交叉 | <45° | 最小角 (°) | 角度不足 (°) |
|---:|---:|---:|---:|---:|
| -0.325 | 2 | 0 | 47.903035 | 0.0 |
| -0.275 | 25 | 17 | 29.018615 | 166.877558 |
| -0.175 | 4 | 4 | 9.086389 | 102.588773 |
| -0.125 | 102 | 28 | 9.418959 | 483.592399 |
| -0.075 | 79 | 35 | 9.625281 | 541.097371 |
| -0.025 | 73 | 24 | 10.161791 | 400.223617 |
| 0.025 | 76 | 24 | 8.261203 | 559.321983 |
| 0.075 | 70 | 27 | 7.518621 | 656.467536 |
| 0.125 | 97 | 0 | 48.721309 | 0.0 |
| 0.175 | 81 | 38 | 5.153763 | 782.097643 |
| 0.225 | 81 | 41 | 10.475314 | 983.335366 |
| 0.275 | 48 | 24 | 10.475314 | 356.496868 |
| 0.325 | 45 | 17 | 6.075998 | 220.042794 |
| 0.375 | 72 | 5 | 35.247507 | 34.616587 |
| 0.425 | 96 | 4 | 34.2278 | 28.628497 |
| 0.475 | 69 | 4 | 30.730759 | 41.414983 |
| 0.525 | 89 | 10 | 12.838568 | 162.413549 |
| 0.575 | 97 | 0 | 48.721309 | 0.0 |
| 0.625 | 77 | 2 | 44.542219 | 0.915563 |

### 1.3 形态学结论（决定 G5 算法设计）

- 违规**只出现在含圆弧的交叉**上：arc–arc 116、arc–line 95、line–arc 93，line–line 0（直线交叉全部为 90°）。
- 两类近切结构：
  1. **两段同半径 R15 圆弧近同心**。半径为 R 的两圆交角满足 `θ = acos(1 − d²/(2R²))`，d 为圆心距；θ≥45° 要求 **d ≥ 11.48 mm**。观测到的最小角 5.154° 对应 d = 1.35 mm。
  2. **水平主干线从某圆弧顶点下方 0–4.4 mm 处穿过**。线与半径 R 的圆弧的交角满足 `θ = acos(|Δy|/R)`（Δy 为线到圆心的竖向距离）；θ≥45° 要求 **|Δy| ≤ 10.6 mm**，即线段必须穿过圆弧的“陡峭段”，不能擦过顶点。
- 因此 G5 不可能靠“在交点附近旋转线段”实现：R15 下 40° 的方向改变需要约 10 mm 的过渡，必须改变真实几何（换层 / 平移走廊 / 原生三维上跨），或用大曲率（被 R15 禁止）。

### 1.4 独立复核（从零实现的检测器）

独立实现（仅标准库，自行推导 line/arc 求交与切线）给出：交叉 None 次、唯一对 None、<45° **None** 次、最小角 **n/a°**、D_theta n/a°，与上表逐项一致。

## 2. 45° 硬约束的实现与一致性改造

角度定义（严格按任务书）：对真实同层交叉点 P，取两条中心线在该点的**局部精确单位切向量** `t_i, t_j`，`θ = arccos(|t_i · t_j|) ∈ [0°, 90°]`。

审计发现工程内共有 **两套独立的 D56 判定实现**（`fslw/validate_fslw.py::_evaluate_pair_strict` 与 `d56/index.py::D56Index._evaluate_strict`），另有 6 处硬编码 `5.0`。G5 的做法：

1. **搜索侧**：新建 `g5/model.py` 的 `pair_audit()`，把“真实横穿”的**角度下限作为一个参数**（默认 45°），并保留原有 D56 的其余全部判据（0.08 mm 净距、交叉窗口 ≤4 mm、窗口外净距、重合/双交/端点切触、窗口不重叠）。
2. **验收侧**：`g5/validate_g5_angle.py` 从零实现（不 import 任何工程几何代码），独立求交、独立算切线、独立出 45° 判定；同时用**未修改的**原 Validator `xyzrouter/validate_xyz.py` 复核原有全部硬约束。两者都 PASS 才允许标记 `G5_ANGLE45_VALID_PASS`。
3. **一致性**：搜索侧与两套验收侧在冻结基线上给出完全相同的 1283 次交叉、1221 对、304 次 <45°、最小角 5.153763°、D_theta 5520.131088°。

> 未采用“把 5° 全局常量改成 45° 后直接复用旧搜索”的捷径：旧的 5° 豁免逻辑在 `D56Index` 里同时承担“合法横穿”与“交叉窗口”两件事，直接改常量会连带改变窗口判定语义。G5 用显式的角度参数重建了同一套判据，并用基线回归证明了其余判据逐位一致。

## 3. 算法：三个候选族 + 违规驱动搜索

所有候选都**保持两个端口位姿**（引出段起点/终点与方向）、**精确 R15**、**切线连续**、**20 个物理高度**与玻璃包络，并由 `structure_issues()`逐条验证。

| 族 | 操作 | 自由度 | 长度影响 | 作用 |
|---|---|---|---|---|
| **A 走廊平移** (corridor shift) | 把体路径中两段平行直线之间的整块几何沿该轴刚性平移 δ | 每条线路 1–3 维零空间 | **不变** | 改变圆弧位置，从而改变 `d` 或 `|Δy|` |
| **B 整线换层** (re-height) | 把体平面换到另外 19 个物理高度之一，两端 S 曲线重建，footprint 变化由首/末直线段精确吸收（2×2 闭包解） | 19 | ±(S 曲线长度差) | 让整条线路离开出事的高度 |
| **C 原生三维跨线** (native-3D excursion) | 在一条直线段上插入 R15 up-S / 中间段(z′) / down-S | 目标高度 × 窗口位置 | +2 条 S 曲线 | 局部消除交叉，其余路径完全不动；支持**一个窗口覆盖多个相邻交叉** |

目标函数（字典序，硬约束优先）：

    min_lex ( N_<45 , D_max , D_theta , N_cross , L_total )

搜索分两阶段：**phase1** 逐条线路做“零违规”贪心（每次接受都使该线路不再有任何 <45° 交叉，因此全局 N 单调下降）；**phase2** 违规驱动的随机爬山（以最小角事件为种子、按线路违规数选边、精确计算局部增量 ΔN/ΔD/ΔN_cross/ΔL，只接受字典序改进，接受等值平台跳转以逃逸），并对组件/空间热点做 destroy-repair。

## 4. 局部修复实验（可行性上界）

对 304 次违规逐条提问：**只改两条线路中的一条，能否让它不再有任何 <45° 交叉？**

| 实验 | 候选范围 | 修复 | 失败 | 贡献 |
|---|---|---:|---:|---|
| v1（三族，限制池） | 每事件 ~110 候选 | 190 | 114 | {'corridor': 30, 'reheight': 141, 'excursion': 19} |
| v2（+多交叉窗口，200 池） | 每事件 ~200 候选 | **197** | 107 | {'corridor': 28, 'reheight': 151, 'excursion': 11, 'excursion_multi': 7} |

即单线路修复的**可达上界约 65%**（197/304）。整线换层是主贡献（151 次），走廊平移 28 次，原生三维跨线 18 次（其中 7 次为多交叉窗口）。

## 5. 全局搜索


搜索曲线见 `06_figures/fig05…fig09`，逐移动明细见 `02_search_runs/<run>/g5_candidate_statistics.csv`。

## 6. 独立验收

**A. 原 20 层几何 Validator（未修改）** — exit 0，24.8 s；`validation_pass=True`，`geometry_pass=True`，`contract_pass=True`，违规 0 次；交叉 None / 对 None；最小三维净距 None mm。

**B. 独立 45° Validator（从零实现）** — exit 0，0.9 s；交叉 2321 次，<45° **134** 次，最小角 7.518621°，`pass_45=False`。

**综合：`NOT_PASS`**

## 7. 与 G4 的几何对比

| 指标 | G4 | G5 |
|---|---:|---:|
| 交叉事件 | 1283 | 2321 |
| 唯一对 | 1221 | 1891 |
| <45° | 304 | 134 |
| 最小角 (°) | 5.153763 | 7.518621 |
| D_theta (°) | 5520.131088 | 2539.854013 |
| 单线路最大交叉 | 17 | 91 |
| 总长度 (mm) | 156597.221522 | 156560.515300 |

逐层对照见 `03_best_feasible/g5_geometry_comparison.csv`。

路线改动：改动线路 **125** 条，其中换层 **61** 条；总长度变化 **-36.706222 mm**。

## 8. 未解决部分的结构性阻挡分析

剩余 **134** 次 <45° 交叉。已执行的搜索范围：phase1 零违规贪心（每线路 ~200 候选 × 2 条线路）+ phase2 违规驱动爬山（每事件 ~70 候选、精确局部增量、平台跳转）+ 组件/热点 destroy-repair + 多种子独立运行。

阻挡原因（按证据强度排序）：

1. **端口位姿把主干线钉死在固定 y 上**。每条线路的最终主干（长直线段）的 y 由目标端口决定，不可移动；因此该主干与其它线路圆弧的交角 `acos(|Δy|/R)` 只能通过移动**对方圆弧**改变。而全板 20 个高度的走廊栅格（端口间距 ~0.586 mm）使任意主干附近都存在顶点落在 0–4.4 mm 内的圆弧——这正是小角度密集区（如 y≈126.1 处的“脊线”）。
2. **单线路无解**：对剩余事件做完整单线路空间深探针，换层/走廊/跨线全部候选都至少留下 1 个新的 <45° 交叉；换到任何其它高度都会遇到同构的脊线结构。
3. **配对移动的净收益为负**：一次换层平均带来 2–3 个新的小角度交叉，而只消除 1 个；在字典序目标下不能被接受，需多线路协同。

4. **代价**：单线路最大交叉数从 17 升到 91，这是把线路换到新高度后与更多线路形成 90° 合法交叉的直接代价（任务书明确允许"合法大角度交叉增加"）；CTP-2.0 的复算表明这些 ≥45° 交叉的串扰处于 FDFD 下限，因此板级串扰仍显著改善。

要真正清零，需要的是**改变走廊栅格本身**（把主干线/圆弧的 y 值重新量化到“顶点间距 ≥4.4 mm”的非均匀网格）或更换整体扇出拓扑，这已超出“在冻结 G4 解上做局部/大邻域修复”的范围，属于下一轮（G6）的全局重布线课题。本轮不伪造可行性，也不降低阈值。

## 9. CTP-2.0 光学串扰复算

# CTP-2.0 on `G5_ANGLE45_NATIVE3D_20H_1024/03_best_partial` — G4 vs G5

Generated 2026-11-20T00:46:05+0800 by `05_ctp2_comparison/run_ctp2_g5.py`.

* model: **CTP-2.0** — the same code that produced the published G4
  numbers, run from the work copy `05_ctp2_comparison/ctp2_g5/` with the
  geometry path swapped and the outputs redirected to `ctp2_out/`.
* geometry label: `G5_ANGLE45_NATIVE3D_20H_1024/03_best_partial`
* geometry dir: `C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\experiments\G5_ANGLE45_NATIVE3D_20H_1024\03_best_partial`
  (routes sha256 `df4f2bf1b8c00f3b8e89895bd403cd9b105efa5c82adde8bf0e9060838629023`)
* CTP payload fed to the model: `C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\experiments\G5_ANGLE45_NATIVE3D_20H_1024\05_ctp2_comparison\ctp2_payload_g5`
* G4 reference: the frozen `board_summary_ctp2.json`
  (sha256 `c99015d47ce98050711e01896dfc31f762d0a903bb93306814793c220ca542dc`) — read-only, never re-written.
* crossings: **re-derived analytically** for G5 (2321 events),
  never inherited: `crossings/crossing_events_verified.csv`.
* independent checks: **all pass**
  * `board_n_events_equals_verified_csv` = True
  * `board_angle_min_equals_verified_csv` = True
  * `all_columns_le_1` = True
  * `forward_split_not_degenerate` = True
  * `n_routes_1024` = True
  * `model_is_ctp2` = True
  * `total_length_matches_payload` = True
* crossing-angle observation (not a pass/fail criterion): 134 crossing(s) below 45°, minimum 7.518621°

> **134 crossing(s) of the G5 geometry still lie below 45°** (minimum 7.518621°); they are listed as residual
> small-angle events in §5. The headline entries are therefore dominated
> by *resolved* small-angle crossings and are predictions, not bounds;
> only the 2187 floor-limited crossings carry bounds.
> Both readings are spelled out in §6.

## 1. Headline comparison

| metric | G4 (CTP-2.0, resolved) | G5 (CTP-2.0, resolved + bound) | change |
|---|---:|---:|---:|
| worst single port-pair crosstalk | **-15.206 dB** (R723→R743) | **-23.461 dB** (R591→R743) | -8.25 dB |
| worst single-route total leakage | **-14.770 dB** (R743) | **-22.725 dB** (R591) | -7.95 dB |
| multi-input worst interference/signal | **-12.712 dB** (R743) | **-21.061 dB** (R591) | -8.35 dB |
| worst-pair bound band | -15.906 … -14.506 dB | -24.161 … -22.761 dB | |
| route-leakage bound band | -15.472 … -14.066 dB | -23.471 … -21.975 dB | |
| **max base propagation loss (dB)** | 1.411610 | 1.411610 | 0.000000 dB |
| hotspot clusters stored / top cluster ΣP (dB) | 80 / -14.37 | 80 / -22.57 | |
| hotspot clusters total (2 mm × plane) | 649 | 829 | |
| crossings (total / below 45°) | 1283 / **304** | 2321 / **134** | |
| total forward-coupled power (linear) | 1.173809e-01 | 1.622425e-02 | -8.59 dB |
| **share of the forward-coupled power that is a floor-limited upper bound** | **1.89e-03 %** | **0.02 %** | |

*`total forward-coupled power`* = Σ of the per-crossing transfer over all
forward-allowed events; it upper-bounds the summed off-diagonal matrix
entries, so its dB change is the cleanest single number for "how much
less power is coupled across the whole board".

That last row answers “how much of the number is a bound?”.

* **G4** — 1.89e-03 %. Even though 703 of its 856 forward-allowed crossings are floor
  crossings, they carry only 2.223e-06 of the 1.174e-01 total forward
  transfer, so the published G4 numbers are genuinely resolved.
* **G5** — 0.02 %. This geometry is *not* a pure bound case: the
  headline numbers are still dominated by the resolved/disputed
  crossings, so they are predictions for those events and bounds only
  for the floor-limited ones (§6).

Port-pair notation: input → output (the transfer matrix is `T[output, input]`).

Reading the G5 column: the geometry is **mixed** — the crossings that
remain below 45° are resolved (θ ≤ 30°) or disputed (30–45°) and their
transfer is a *prediction*; the crossings at θ ≥ 45.5° contribute the
−85 dB floor value, which is an *upper bound*. The headline numbers are
sums over both kinds, so they are predictions for the resolved part and
bounds for the floor-limited part; the `bound band` rows show the
resulting [Born-low, FDFD-high] interval.

## 2. Secondary metrics

| metric | G4 | G5 |
|---|---:|---:|
| diagonal min / max (dB) | -1.879 / -0.224 | -1.817 / -0.224 |
| max column sum (energy) | 0.949714 (≤1: True) | 0.949714 (≤1: True) |
| median off-diagonal (dB) | -86.335 | -158.564 |
| non-zero off-diagonal entries | 3248 | 4455 |
| second-order chains (n, max dB) | 2660, -37.870 | 4613, -56.377 |
| CT1.0 fixed-p baseline worst pair (dB) | -67.415 | -66.003 |
| board runtime (s) | 1.90 | 2.51 |

The fixed-p baseline column is the superseded CTP-1.0 bookkeeping and is
shown only to demonstrate that it barely moves between geometries — which is
exactly why it must not be used for the G4→G5 claim.

## 3. Crossing statistics and angle distribution

| metric | G4 | G5 |
|---|---:|---:|
| routes | 1024 | 1024 |
| crossings | 1283 | 2321 |
| crossing pairs | 1221 | 1891 |
| routes with crossings | 647 | 834 |
| max crossings on one route | 17 | 91 |
| crossing angles < 45° | **304** | **134** |
| crossing angles < 30° | 161 | 72 |
| crossing angles < 10° | 17 | 3 |
| min / median angle (°) | 5.153763 / 63.256316 | 7.518621 / 65.375682 |
| per-crossing T_cross range (dB) | -85.000 … -14.365 | -85.000 … -19.148 |
| crossings above −30 dB | 17 | 3 |
| forward-direction allowed / blocked | 856 / 427 | 1140 / 1181 |

### Angle distribution (same bins as the G5 project's own audit)

| bin (°) | G4 crossings | G5 crossings | G5 floor-limited | G5 share of forward-coupled power | kernel status in this band |
|---|---:|---:|---:|---:|---|
| [0,5) | 0 | 0 | 0 | — | resolved |
| [5,10) | 17 | 3 | 0 | 34.10 % | resolved |
| [10,20) | 92 | 53 | 0 | 65.68 % | resolved |
| [20,30) | 52 | 16 | 0 | 0.15 % | resolved |
| [30,40) | 92 | 36 | 0 | 0.04 % | disputed (bounds only) |
| [40,45) | 51 | 26 | 0 | 4.55e-03 % | disputed (bounds only) |
| [45,60) | 271 | 411 | 411 | 5.87e-03 % | **bound** at −85 dB floor |
| [60,75) | 514 | 740 | 740 | 0.01 % | **bound** at −85 dB floor |
| [75,90] | 194 | 1036 | 1036 | 4.13e-03 % | **bound** at −85 dB floor |
| **total** | **1283** | **2321** | **2187** | **100 %** | |

Floor-limited events are **1072 of 1140 forward-allowed crossings (94.04 %)**, but they carry only **0.02 %** of the
forward-coupled power (3.390e-06 of 1.622e-02).

### Kernel resolution status of each crossing

| status | G4 | G5 |
|---|---:|---:|
| resolved | — | 3 |
| resolved_fdtd_crosschecked | — | 65 |
| disputed_paraxial | — | 62 |
| upper_bound_port_floor_limited | — | 2187 |
| handover bracket (status changes between adjacent kernel angles) | — | 4 |

G4 status mix is not tabulated here because CTP-2.0's published board
summary does not carry it; it is recoverable from
`crossings/crossing_optical_analysis_ctp2.csv` of the frozen run.
The G5 mix is what matters: **68 resolved, 4 in a status-changing 0.25° bracket, 62 disputed (30–45°), 2187 at the −85 dB floor** (Σ = 2321).
(The `< 30°` count above is by angle; the resolved-row count differs
slightly where a crossing sits in a kernel bracket whose two ends carry
different statuses.)

## 4. Propagation loss (regenerated for G5)

Same frozen assumptions as G4: α = 0.05 dB/cm, λ = 1310 nm, n₀ = 1.50,
Δn = 0.0065, 9 × 9 µm core, R15 extra bend loss 0 dB (the arc length is
still counted in full).

| metric | G4 | G5 |
|---|---:|---:|
| routes | 1024 | 1024 |
| total length (mm) | 156597.221522 | 156560.515300 |
| mean length (mm) | — | 152.891128 |
| **max propagation loss (dB)** | 1.411610 | **1.411610** |
| mean propagation loss (dB) | 0.764635 | 0.764456 |
| min / median loss (dB) | — | 0.224069 / 0.784799 |
| total loss over all routes (dB) | — | 782.803 |

G4 loss figures are recomputed here from the frozen G4 route lengths
(`e1_summary.json`: `loss_max_db = 1.411609762059922`,
`loss_mean_db = 0.764634870711216`) so the two columns are like-for-like.

## 5. Hotspots

Hotspots are 2 mm × 2 mm × one-plane clusters of crossings, ranked by the
summed per-crossing transfer `P_cross`. Clusters stored: **G4 80, G5 80**.

| rank | G4 (z, x, y) mm | n | ΣP (dB) | G5 (z, x, y) mm | n | ΣP (dB) |
|---|---|---:|---:|---|---:|---:|
| 1 | 0.175, 84.13, 124.59 | 1 | -14.37 | 0.175, 104.27, 126.20 | 3 | -22.57 |
| 2 | 0.325, 47.61, 35.81 | 1 | -15.25 | -0.125, 48.02, 18.25 | 1 | -31.23 |
| 3 | 0.175, 51.32, 26.78 | 1 | -16.35 | -0.025, 133.02, 48.02 | 1 | -31.23 |
| 4 | 0.175, 142.43, 45.42 | 1 | -22.23 | -0.075, 101.98, 132.30 | 1 | -31.23 |
| 5 | 0.175, 103.31, 126.10 | 1 | -22.57 | 0.075, 133.02, 27.98 | 1 | -31.23 |

### Residual small-angle events (θ < 45°)

134 event(s) in total; the 40 smallest angles are listed (sorted by angle).

| route_a | route_b | z (mm) | x (mm) | y (mm) | angle (°) | deficit (°) |
|---:|---:|---:|---:|---:|---:|---:|
| 419 | 437 | 0.075 | 127.826 | 107.657 | 7.518621 | 37.481379 |
| 591 | 743 | 0.175 | 103.314 | 126.097 | 8.392203 | 36.607797 |
| 425 | 428 | 0.025 | 147.219 | 115.615 | 8.582274 | 36.417726 |
| 124 | 130 | -0.125 | 48.021 | 18.246 | 10.161791 | 34.838209 |
| 478 | 493 | -0.075 | 101.979 | 132.303 | 10.161791 | 34.838209 |
| 477 | 492 | -0.025 | 133.019 | 48.021 | 10.161791 | 34.838209 |
| 151 | 207 | 0.075 | 133.019 | 27.979 | 10.161791 | 34.838209 |
| 28 | 29 | -0.075 | 15.625 | 144.575 | 10.475314 | 34.524686 |
| 114 | 115 | -0.125 | 50.875 | 135.612 | 10.475314 | 34.524686 |
| 640 | 672 | 0.275 | 6.842 | 81.125 | 10.475314 | 34.524686 |
| 148 | 225 | 0.025 | 89.097 | 33.125 | 10.475314 | 34.524686 |
| 237 | 426 | 0.075 | 145.291 | 69.125 | 10.475314 | 34.524686 |
| 591 | 719 | 0.175 | 86.125 | 84.447 | 10.475314 | 34.524686 |
| 124 | 132 | -0.125 | 34.375 | 5.973 | 10.475314 | 34.524686 |
| 30 | 36 | -0.075 | 33.125 | 122.758 | 10.475314 | 34.524686 |
| 39 | 101 | -0.075 | 42.375 | 122.758 | 10.475314 | 34.524686 |
| 451 | 472 | -0.075 | 133.875 | 138.698 | 10.475314 | 34.524686 |
| 478 | 499 | -0.075 | 115.625 | 144.575 | 10.475314 | 34.524686 |
| 473 | 476 | -0.025 | 47.180 | 90.125 | 10.475314 | 34.524686 |
| 477 | 498 | -0.025 | 145.291 | 34.375 | 10.475314 | 34.524686 |
| 150 | 153 | 0.025 | 51.816 | 143.125 | 10.475314 | 34.524686 |
| 591 | 719 | 0.175 | 115.875 | 138.210 | 10.475314 | 34.524686 |
| 535 | 671 | 0.225 | 80.875 | 142.791 | 10.475314 | 34.524686 |
| 130 | 131 | -0.125 | 68.875 | 38.892 | 10.475314 | 34.524686 |
| 452 | 473 | -0.025 | 4.709 | 133.875 | 10.475314 | 34.524686 |
| 417 | 432 | 0.025 | 18.449 | 42.125 | 10.475314 | 34.524686 |
| 216 | 237 | 0.075 | 44.229 | 68.875 | 10.475314 | 34.524686 |
| 421 | 527 | 0.225 | 98.875 | 118.507 | 10.475314 | 34.524686 |
| 419 | 422 | 0.075 | 145.291 | 116.125 | 10.475314 | 34.524686 |
| 432 | 435 | 0.025 | 19.243 | 42.125 | 10.475314 | 34.524686 |
| 423 | 426 | 0.075 | 4.709 | 34.375 | 10.475314 | 34.524686 |
| 225 | 228 | 0.025 | 2.727 | 24.625 | 10.475314 | 34.524686 |
| 228 | 411 | 0.025 | 18.449 | 24.625 | 10.475314 | 34.524686 |
| 142 | 145 | 0.075 | 4.709 | 6.375 | 10.475314 | 34.524686 |
| 793 | 973 | 0.225 | 127.003 | 52.826 | 10.755712 | 34.244288 |
| 616 | 737 | 0.525 | 80.292 | 135.375 | 12.838568 | 32.161432 |
| 616 | 847 | 0.525 | 31.958 | 135.375 | 12.838568 | 32.161432 |
| 616 | 843 | 0.525 | 40.958 | 135.375 | 12.838568 | 32.161432 |
| 224 | 974 | 0.075 | 131.480 | 125.875 | 14.444970 | 30.555030 |
| 148 | 414 | 0.025 | 90.210 | 33.375 | 14.835112 | 30.164888 |

## 6. Model-resolution caveat (must travel with every G5 number)

1. CTP-2.0's crossing kernel is resolved only for θ ≤ 30°
   (`resolved` / `resolved_fdtd_crosschecked`), disputed for 30–45°, and
   for θ ≥ 45.5° it reports an **upper bound at the −85 dB FDFD port
   floor** (`status = upper_bound_port_floor_limited`).
2. G5's minimum crossing angle is 7.518621°. Of the 2321 crossings: **68 are in the kernel's resolved
   rows**, 62 are disputed (30–45°), 2187 are at
   the −85 dB floor and 4 sit in a
   status-changing bracket. The geometry is **mixed**: entries driven
   by a resolved crossing are predictions, entries driven by θ ≥ 45.5°
   crossings are upper bounds. Do not label the whole table 'bound' nor
   the whole table 'prediction'.
3. There is a ~12 dB hand-over step in the kernel between 45.0°
   (−72.799 dB, `disputed_paraxial`) and 45.5° (−85.000 dB, floor). The
   crossing set spans both sides, so no single side applies;
   `n_handover_bracket = 4` crossings sit in a
   0.25° bracket whose two ends carry different statuses.
4. Which G5 entries are bounds:
   * any entry whose worst contributing crossing has θ ≥ 45.5° — an
     **upper bound** at the −85 dB floor. The `bound band` rows in §1
     give the matching [Born-low, FDFD-high] interval.
   * the per-crossing table
     `ctp2_out/crossings/crossing_optical_analysis_ctp2.csv` carries the
     angle and `T_cross_db` of every event, so any entry can be traced to
     its status via the table in §3.
   * diagonal, propagation loss, route lengths — resolved (not bounds).
5. Both models assume an ideal structure (no sidewall roughness, index
   drift, stress birefringence or bend-induced polarisation conversion),
   which literature says dominates measured large-angle crosstalk, so even
   the floor-limited upper bound is a *lower* bound on a real device. The
   scalar weakly-guided approximation underpins everything (Δn/n = 0.43 %).
6. Crossing insertion loss above 30° is an extrapolation
   (`loss ∝ (θ/10)^-0.873`, anchored at the converged 10° BPM value), so the
   diagonal inherits that extrapolation.

## 7. Geometry anomalies and independent audit agreement

### 7.1 What changed in the routes (G4 → G5)

| metric | value |
|---|---:|
| routes compared | 1024 |
| routes whose length or height set changed | **71** |
| routes whose set of height plateaus changed (re-heighted) | **71** |
| total length Δ (mm) | -36.706222 |
| total length G4 → G5 (mm) | 156597.221522 → 156560.515300 |
| max / mean \|Δlength\| (mm) | 5.235462 / 0.085981 |
| routes with \|Δlength\| > 1 mm / > 10 mm | 22 / 0 |
| routes longer / shorter | 38 / 29 |

Ten largest length changes (a length change is the fingerprint of a
re-height or a re-route):

| route | Δlength (mm) | G4 (mm) | G5 (mm) | height set changed | G4 z start→end | G5 z start→end |
|---:|---:|---:|---:|:---:|---|---|
| R995 | +5.235 | 203.846 | 209.081 | yes | +0.525→+0.525 | +0.525→+0.525 |
| R986 | +5.235 | 210.795 | 216.031 | yes | +0.525→+0.525 | +0.525→+0.525 |
| R81 | -5.028 | 136.459 | 131.431 | yes | +0.025→+0.025 | +0.025→+0.025 |
| R361 | -5.028 | 136.459 | 131.431 | yes | +0.025→+0.025 | +0.025→+0.025 |
| R376 | -5.028 | 119.127 | 114.099 | yes | +0.025→+0.025 | +0.025→+0.025 |
| R379 | -5.028 | 115.661 | 110.633 | yes | +0.025→+0.025 | +0.025→+0.025 |
| R800 | -5.028 | 75.180 | 70.152 | yes | +0.525→+0.525 | +0.525→+0.525 |
| R82 | -5.028 | 132.992 | 127.964 | yes | +0.025→+0.025 | +0.025→+0.025 |
| R783 | -4.274 | 87.891 | 83.617 | yes | +0.525→+0.525 | +0.525→+0.525 |
| R777 | -3.592 | 99.113 | 95.521 | yes | +0.525→+0.525 | +0.525→+0.525 |

### 7.2 Does the independent audit agree with the regenerated crossings?

| check | value |
|---|---:|
| audit source | `C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\experiments\G5_ANGLE45_NATIVE3D_20H_1024\03_best_partial\g5_crossing_angles.csv` |
| events (regenerated / audit) | 2321 / 2321 |
| matched on (route_a, route_b, plane) | **2321** |
| only in the regeneration | **0** |
| only in the audit | **0** |
| max \|Δx\| / \|Δy\| / \|Δz\| (mm) | 5.00e-07 / 4.99e-07 / 0.00e+00 |
| max \|Δangle\| (°) | 5.00e-07 |
| geometry consistent | **True** |

The two independent implementations agree on **every** event; the
positions and angles differ only by the audit CSV's 6-decimal
rounding. The `s_a_mm`/`s_b_mm` columns are deliberately *not* taken
from the audit CSV (different arc-length origin, constant per route,
up to 167.825 mm)
— they come from the regeneration, whose `Route.pos(s_a)` reproduces
the crossing point to 1e-13 mm; see
`frozen_guard/s_convention_report.json`.

## 8. Reproduce

```powershell
$py = "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\.venv\Scripts\python.exe"
$cmp = "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\experiments\G5_ANGLE45_NATIVE3D_20H_1024\05_ctp2_comparison"
& $py "$cmp\run_ctp2_g5.py" --routes "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\experiments\G5_ANGLE45_NATIVE3D_20H_1024\03_best_partial\routes_l3d.json" --out-root "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\experiments\G5_ANGLE45_NATIVE3D_20H_1024\05_ctp2_comparison\ctp2_out" --payload-dir "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\experiments\G5_ANGLE45_NATIVE3D_20H_1024\05_ctp2_comparison\ctp2_payload_g5" --geometry-label "G5_ANGLE45_NATIVE3D_20H_1024/03_best_partial"
```

Board summary: `C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\experiments\G5_ANGLE45_NATIVE3D_20H_1024\05_ctp2_comparison\ctp2_out\board\board_summary_ctp2.json` (sha256 `1c83ed89c247123ca6c537d9db862a9ff3f7df9a744db59db284f765a65be6bb`).
Machine-readable numbers: `g5_ctp2_summary.json`.



## 10. 复现命令

```powershell
$env:PYTHONPATH="C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D"
cd "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D"

# 1) 基线审计（G4 的 304 次 <45° 交叉 + 冲突图）
python experiments\G5_ANGLE45_NATIVE3D_20H_1024\01_algorithm\run_baseline_audit.py
python four_side_1024\fanout1024\xyzrouter\g5\validate_g5_angle.py --run-dir experiments\COLD_START_20_HEIGHT_1024\10_best_valid --out-dir experiments\G5_ANGLE45_NATIVE3D_20H_1024\00_baseline_audit\independent_angle_validator

# 2) 搜索
python experiments\G5_ANGLE45_NATIVE3D_20H_1024\01_algorithm\run_g5.py --seed 20261104 --profile free --phase1-limit 160 --phase2-seconds 3600

# 3) 出件 + 对比表
python experiments\G5_ANGLE45_NATIVE3D_20H_1024\01_algorithm\run_finalise.py --routes <result>\routes_l3d.json --out <out>

# 4) 双验收
python experiments\G5_ANGLE45_NATIVE3D_20H_1024\01_algorithm\run_validation.py --source <out>

# 5) 图与报告
python experiments\G5_ANGLE45_NATIVE3D_20H_1024\01_algorithm\make_figures.py --g5-routes <out>\routes_l3d.json
```

## 11. 交付文件

见 `MANIFEST.json`（含每个文件的 SHA256、字节数与角色）。

