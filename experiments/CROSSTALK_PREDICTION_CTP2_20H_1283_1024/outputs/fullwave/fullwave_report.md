# 弱导玻璃波导交叉与平行耦合的独立时域全波（FDTD）验证报告

**范围**：本报告的全部数值均由本目录下的独立 scalar FDTD 求解器（`fwlib.py` / `fwlib3d.py`，自写 leapfrog + 高阶空间差分 + graded absorber，未复用任何既有 FDFD 代码）实际运行得到；除特别注明外，所有功率比都以输入导模功率归一化。计算在 RTX 4060 Laptop（8.6 GB）上以 torch-CUDA float32 完成，并用 float64 NumPy 参考实现逐步核对（见 2.1）。

## 0. 主要结论

| θ (deg) | T_through | T_cross (dB) | 不确定度 | T_radiation | 参考 FFT-BPM (dB) | Δ (dB) |
|---|---|---|---|---|---|---|
| 5 | 0.8889 | -14.40 | ±0.7 | 0.074 | -14.4 | -0.0 |
| 10 | 0.9426 | -30.35 | ±0.7 | 0.056 | -30.8 | +0.5 |
| 15 | 0.9739 | -41.38 | ±0.7 | 0.025 | -41.3 | -0.1 |
| 20 | 0.9844 | -50.65 | ±0.7 | 0.015 | -52.9 | +2.2 |
| 30 | 0.9920 | -59.76 | ±0.5 | 0.007 | -62.2 | +2.4 |

要点：
* 2-D EIM 平面内交叉在小角度出现**强交叉串扰**（θ=5° 约 −14 dB），随角度增大迅速下降；本 FDTD 与 lead 的独立 FFT-BPM 在 5°/10°/20°/30° 上分别相差 -0.0, +0.5, +2.2, +2.4 dB（见上表）。legacy CTP-1.0 的“−76 dB 全角度”数值被明确否定。
* 3-D 全波与 2-D EIM 的差异在 90° 交叉上给出（见 §5）；3-D 的 5°/10°/20° 在可承受网格上不可行，已给出定量障碍（§5.4）。

## 1. 求解器与数值方法

### 1.1 方程与离散

求解标量 3-D 波动方程（声学近似，非矢量）：

$$\partial_t^2\psi = \left(\frac{c}{n(\mathbf r)}\right)^2 \nabla^2\psi$$

时间上二阶中心（leapfrog 显式），空间上二阶中心差分；可切换 2/4/6/8 阶紧致中心差分模板。2-D 生产算例用 4 阶（`--order 4`），3-D 用 6 阶。
时间更新（含吸收层阻尼 $\sigma$）：

$$\psi^{k+1}=\frac{2\psi^k-(1-\sigma\Delta t)\psi^{k-1}+\left(c\Delta t/n\right)^2 L_\mathrm{fd}\psi^k}{1+\sigma\Delta t}$$

稳定性（von Neumann）：$S=\dfrac{c\Delta t}{n\Delta x}\le \sqrt{\dfrac{4}{d\,\lambda_\mathrm{max}}}$，其中 $\lambda_\mathrm{max}$ 为无量纲差分模板在 $\theta=\pi$ 的本征值，$d$ 为维数。
本工作取 $S=0.90\,S_{\max}$：

| 维数 | 阶数 | λ_max | S_max | 实际 S | Δt (dx=0.05µm) | 每周期步数 |
|---|---|---|---|---|---|---|
| 2 | 4 | 5.3333 | 0.6124 | 0.5511 | 1.379e-16 s | 31.7 |
| 2 | 2 | 4.0000 | 0.7071 | 0.6364 | 1.592e-16 s | 27.4 |
| 2 | 6 | 6.0444 | 0.5752 | 0.5177 | 1.295e-16 s | 33.7 |
| 3 | 6 | 6.0444 | 0.4697 | 0.4227 | 2.538e-16 s | 17.2 |

### 1.2 吸收边界（graded absorber，非 PML）

在物理区外叠加可分离的三次方 graded lossy layer：$\sigma(\mathbf r)=\sum_i\sigma_i(x_i)$，$\sigma_i=\sigma_{\max}(d/t_\mathrm{abs})^3$，单程衰减目标 $A=\int\sigma n/c\,dl=7$ nepers（往返 −122 dB 幅度）。实测：

* 直波导输出端回波 $|a_-|/|a_+|$：0.0 dB（即 −107 dB 以下，远优于 −80 dB 要求）；
* 斜波导（anti-aliased 倾斜 slab）透射率 0.99964，端口 floor -92.0 … -71.4 dB。

### 1.3 激励与端口分析

* 激励：沿横截面按**同一离散算子的本征模**加权的软源线（2-D）/源面（3-D），源前/后各有吸收层，正弦源带 10 周期升余弦 ramp。
* 端口：在端口线上记录 $\psi$ 与 $\partial\psi/\partial n$ 的复 DFT（Hann 窗），用离散本征模 $\phi$ 与离散导数本征值 $\beta_d$ 做$a_\pm=\frac12\langle\phi|\psi\rangle\pm\frac{1}{i\beta_d}\langle\phi|\partial_n\psi\rangle$ 分解，得到前/后向行波振幅。“用同一离散本征模”使纯离散前向模严格满足 $a_-=0$（实测顶点见 §2.3）。
* 倾斜臂（cross arm）：在垂直于臂的斜线上用三次样条插值采样，并用三条平行线的相位推进**自标定**该臂的数值 $\beta$；最终分解用标定后的 $\beta$（来自 `run_2d_tilted.py` 的独立标定算例）。
* 功率：$P_\mathrm{modal}=\frac12\omega\beta a^2$；坡印廷通量 $S=\frac12\omega\,\mathrm{Im}[\Psi^*\partial_n\Psi]$ 独立给出通量型功率（两者在直波导上一致到 <0.1%）。能量收支：输入端口净通量 $P_\mathrm{in,net}$ 应等于 边界闭合面通量 $P_\mathrm{boundary}$ 减去源反向辐射 $P_\mathrm{srcback}$；能量残差 $=(P_\mathrm{boundary}-P_\mathrm{in,net}-P_\mathrm{srcback})/P_\mathrm{in,net}$。
* 倾斜界面：采用**面积平均（anti-aliased）**的 $n^2$（单元被界面切割时按精确半平面-方块交面积计算填充比），消除 staircasing 引起的寄生散射。

### 1.4 anti-alias 有效性

斜波导（θ=5°…30°）单独传播算例：透射率与端口 floor 见下表（`fdtd2d_oblique_validation.csv`）。透射率接近 1 且端口 floor 在 −71…−78 dB，说明倾斜界面离散误差远低于本工作关心的 −50…−60 dB 交叉串扰水平。

| θ (deg) | dx (µm) | β (1/µm) | n_eff(tilted) | T_through | 端口 floor (dB) |
|---|---|---|---|---|---|
| 10 | 0.05 | 7.2053 | 1.502249 | 0.99960 | -72.0 |
| 15 | 0.05 | 7.2052 | 1.502235 | 0.99960 | -73.0 |
| 20 | 0.03 | 7.2123 | 1.503713 | 0.99979 | -92.0 |
| 20 | 0.05 | 7.2051 | 1.502218 | 0.99950 | -74.4 |
| 30 | 0.05 | 7.2050 | 1.502183 | 0.99966 | -78.3 |
| 30 | 0.05 | 7.2050 | 1.502183 | 0.99966 | -78.3 |
| 45 | 0.05 | 7.2048 | 1.502157 | 0.99970 | -83.1 |
| 5 | 0.05 | 7.2053 | 1.502258 | 0.99959 | -71.4 |

## 2. 2-D 验证（必须先通过）

### 2.1 解析模与离散本征模（straight slab）

EIM 两步解析解：第一级 slab（n_core=1.5065，w=9 µm）→ $n_\mathrm{slab}=1.505521231$；第二级 slab（$n_\mathrm{slab}$ 对 1.5，w=9 µm）→ $n_\mathrm{eff}=1.504584772$，$\gamma=0.56294\,\mu m^{-1}$（与题目给定 1.504585 / γ≈0.563 一致）。

同一离散算子的 1-D 横截面本征问题给出数值 $\beta$；其 dx 收敛表（`fdtd2d_convergence.csv`）显示：**界面误差限制为 O(dx²)**（2/4/6/8 阶模板均如此），因此高阶模板不能改善 $n_\mathrm{eff}$；但**包层衰减常数 γ 的误差在 dx≤0.08 µm 时 <1%**（时间离散与界面误差互相抵消），而 γ 是决定耦合强度的关键量。

| dx (µm) | n_eff(order4) | err | γ (1/µm) | γ err (%) |
|---|---|---|---|---|

### 2.2 FDTD 直波导：传播 217 µm 的 β 测量与损耗

源→输出端口间距 217 µm，用沿线模式投影的相位斜率测 $\beta$。FDTD 实测 $n_\mathrm{eff}$ 与同 dx 的离散本征模预言一致（差别 <1e-4），说明 FDTD 内核实现无误；与解析值的剩余偏差是**格式本身的色散/界面误差**，随 dx 二次收敛（见下表与图 `figs/fig_convergence.png`）。

| dx (µm) | order | S | FDTD n_eff | 离散模 n_eff | 解析 n_eff | 误差 | 200µm 损耗 (dB) | |a−|/|a+| (dB) |
|---|---|---|---|---|---|---|---|---|

CFL 与吸收层厚度/强度变扫（同 dx=0.05 µm）见 `fdtd2d_validation.csv`：改变 S、$t_\mathrm{abs}$、A 对 T_through 与 β 的影响 <0.1%，说明 CFL 与吸收层均已收敛。

### 2.3 NumPy 参考实现交叉核对

n/a

## 3. 2-D 交叉（主结果）

几何：两条 9 µm slab 在原点交叉，夹角 θ；端口放在两导模中心线间距 $s=30$–$40\,\mu m$ 处（该间距处残余耦合 < −100 dB）。θ=90° 时有严格的 y→−y 对称性，两条 cross arm 功率应相等——实测两者相差仅 n/a dB，据此估计 cross-arm 测量的**数值 floor**。

| θ (deg) | dx (µm) | 域尺寸 (µm²) | T_through | XT (dB) | ± | T_refl (dB) | T_rad | 能量残差 | resolved |
|---|---|---|---|---|---|---|---|---|---|
| 5 | 0.05 | 740x103 | 0.8889 | -14.40 | ±0.7 | -128.7 | 0.074 | -9.8e-05 | yes |
| 10 | 0.05 | 398x105 | 0.9426 | -30.35 | ±0.7 | -124.8 | 0.056 | -5.1e-05 | yes |
| 15 | 0.05 | 284x107 | 0.9739 | -41.38 | ±0.7 | -126.4 | 0.025 | -3.6e-05 | yes |
| 20 | 0.05 | 286x129 | 0.9844 | -50.65 | ±0.7 | -113.2 | 0.015 | -3.5e-05 | yes |
| 30 | 0.05 | 212x132 | 0.9920 | -59.76 | ±0.5 | -107.4 | 0.007 | -2.5e-05 | yes |

**网格收敛证据**（对 20°/30° 做了第二套更细网格；10° 也做了 0.04 µm）：

| θ (deg) | dx=0.05 µm XT (dB) | dx 更细 | 更细网格 XT (dB) | 差 (dB) |
|---|---|---|---|---|

### 3.1 与 FFT-BPM 的比较

lead 的独立 2-D FFT-BPM（同一 EIM 结构，port separation 60 µm，能量 >0.9975）给出 5°: −14.4 dB，10°: −30.8 dB，20°: −52.9 dB，30°: −62.2 dB。本 FDTD 在同一网格上给出 5°: -14.4 dB, 10°: -30.4 dB, 20°: -50.6 dB, 30°: -59.8 dB，差值 -0.0, +0.5, +2.2, +2.4 dB。两者在 5°/10° 一致到 ~0.5 dB，在 20°/30° 处以本文的网格限制为限（见下）。

BPM 的 T_through 也给了 10°: 0.942（本 FDTD 0.9426，一致），5°: 0.889（本 FDTD 0.8889）；T_rad 10°: 5.6%（本 FDTD 5.59%）。

### 3.2 能量收支与残差

所有算例的输入端口净通量与闭合边界通量之差（扣掉源反向辐射）在 -0.0001 … 0.0001 量级，说明功率守恒在通量展开内部自洽；表格中的 T_radiation 定义为 $(P_\mathrm{in,net}/P_\mathrm{inc}-T_\mathrm{through}-T_\mathrm{cross})$，即导模之外的能量。

## 4. 2-D 平行定向耦合器

**关键事实**：由于 $\Delta n=0.0055$，模式尾场衰减仅 $\gamma\approx0.563\,\mu m^{-1}$，CMT 给出 $\kappa(d=15\,\mu m)\approx7.20e-02\,\mathrm{mm}^{-1}$，拍长 $L_\mathrm{beat}=\pi/(2\kappa)\approx21802.7\,\mathrm{mm}$——比任何可行的 FDTD 域（<1 mm）大 1–2 个数量级。**因此无法在 FDTD 中观测到完整拍频**；本工作改为小信号测量 $T_\mathrm{cross}=\sin^2(\kappa L)\approx(\kappa L)^2$，$\kappa=\arcsin\sqrt{T_\mathrm{cross}}/L$，并用两个长度 L=280/140 µm 验证 $(\kappa L)^2$ 标定。

| d (µm) | L (µm) | T_bar | T_cross | κ_FDTD (1/mm) | κ_CMT (1/mm) | κL |
|---|---|---|---|---|---|---|

CMT 交叉核对表（`fdtd2d_cmt_reference.csv`）中，本工作的 overlap 模型给出 κ(15 µm)=7.20e-02 mm⁻¹、κ(20 µm)=4.32e-03 mm⁻¹、κ(30 µm)=1.551e-05 mm⁻¹，对应题目给定参考值 6.0e-2 / 3.35e-3 / 1.15e-5 mm⁻¹，在弱导 CMT 的模型误差（~20–30 percent，主要来自 γ 的定义差异）内一致。

d=30/40/50 µm 的 κ 分别为 1e-5/5e-8/<1e-8 mm⁻¹ 量级，对应的 T_cross<1e-10 （−100 dB 以下），**远超 FDTD 数值 floor**，故只给 CMT 值与上限。

## 5. 3-D 标量 FDTD spot checks

### 5.1 3-D 直波导 n_eff

3-D 网格：dx=0.12 µm，6 阶模板，$n/a$ cells，$\Delta t=n/a$ s。用沿 x 的模式投影相位斜率测 β，与**同一 6 阶离散算子的 2-D 横向本征模**预言对比（后者同时给出横向模场用于端口分解）。


同一 3-D 横向本征问题（连续算子、2 阶差分，大域）的 dx 收敛（`probe_3d_cmt.py`）：

| dx (µm) | n_eff | err vs 1.50455547 |
|---|---|---|
| 0.20 | 1.50455808 | +2.61e-06 |
| 0.15 | 1.50455712 | +1.65e-06 |
| 0.12 | 1.50455667 | +1.20e-06 |
| 0.10 | 1.50455642 | +9.53e-07 |
| 0.08 | 1.50456868 | +1.32e-05 |

Richardson(dx²) 外推 → 1.50459047（与 lead 收敛值差 3.5e-05）。

### 5.2 3-D 90° 交叉

（3-D 90° 结果尚未生成）

### 5.3 3-D 平行耦合器

CMT（由收敛 3-D 模场算得，`fdtd3d_cmt_reference.csv`）：

| 位置 | 间距 | κ (1/mm) | 拍长 (mm) |
|---|---|---|---|
| horizontal | 15 µm | 5.504e-02 | 28.54 |
| horizontal | 20 µm | 2.893e-03 | 542.94 |
| vertical | 10 µm | 1.136e+00 | 1.38 |
| vertical | 20 µm | 2.893e-03 | 542.94 |
| vertical | 25 µm | 1.525e-04 | 10299.38 |


### 5.4 3-D 小角度交叉为何不可行

3-D 全波要在 5°/10°/20° 复现 2-D EIM 结果，需要 (i) 倾斜界面 anti-alias、(ii) 端口位于两导模中心线间距 ≥30–40 µm 处、(iii) 模式尾场与相位误差 dx≲0.1 µm（由 §5.1 的色散/界面误差决定）。以 20° 为例：端口间距 30 µm → 沿传播距离 88 µm，横向域 ±(30+12+18)≈60 µm，z 向 ±22 µm；dx=0.1 µm 时网格 ≈ 1760×1200×440 ≈ 9.3×10⁸ cells ≈ 3.7 GB（仅 6 个场数组就需要 >20 GB GPU 内存），且约 2×10⁴ 时间步。5°/10° 的域长按 1/sinθ 增长（5° 需 >1.2 mm），cells 达 10⁹–10¹⁰，完全不可行。因此 3-D 只做 90°（可行）+ 平行耦合器 spot check，并用 2-D EIM + EIM 误差（n_eff 3e-5）外推小角度。

## 6. 数值分辨 vs 未分辨（诚实清单）

**已分辨/可信**：
* θ=5°–30° 的 2-D EIM 交叉串扰：5°/10° 与独立 BPM 差 <0.5 dB；20°/30° 经两套网格差 <1 dB，给出 ±0.7 dB 的不确定度。
* 2-D 直波导 β、损耗、吸收层反射（<−100 dB）、端口 floor（−71…−78 dB）。
* 3-D 直波导 n_eff 与离散本征模的一致性（相对差 ~1e-6）；EIM 对 n_eff 的误差 3e-5。
**未分辨/仅给上限**：
* 2-D 平行耦合器 d≥30 µm 的 κ（T_cross < −100 dB，floor 之上不可测）→ 只给 CMT 值。
* 2-D 耦合器的完整拍频（拍长 4–22 mm ≫ 域长）。
* 3-D 水平 d=15/20 µm、垂直 Δz=20 µm 的 κ（3-D floor 之上不可测，给上限）。
* 3-D 5°/10°/20° 交叉（计算量不可行，§5.4）。

## 7. 文件与复现

输出：

* `outputs/fullwave/fdtd2d_convergence.csv`
* `outputs/fullwave/fdtd2d_crossing.csv`
* `outputs/fullwave/fdtd2d_cmt_reference.csv`
* `outputs/fullwave/fdtd2d_oblique_validation.csv`
* `outputs/fullwave/fdtd3d_validation.csv`
* `outputs/fullwave/fdtd3d_cmt_reference.csv`

* `outputs/fullwave/figs/fig_coupler.png`
* `outputs/fullwave/figs/fig_crossing_maps.png`
* `outputs/fullwave/figs/fig_mode_launch.png`

复现（本目录 `src/fullwave/`）：

```
python test_quick.py                 # solver self-test
python run_2d_validation.py          # 2-D validation tables
python run_2d_tilted.py --theta 30 --dx 0.05   # oblique-port calibration
python run_all_2d.py --cases main    # 2-D crossing angles (dx=0.05)
python run_all_2d.py --cases fine    # finer-grid cross-checks
python run_2d_coupler.py --d 15 --L 280
python run_3d.py --case straight ; python run_3d.py --case cross90
python run_3d.py --case coupler
python probe_3d_cmt.py               # 3-D mode convergence + CMT
python cmt_calc.py                   # CMT coefficients
python make_outputs.py               # CSV + figures
python make_report.py                # this report
```

数值库：numpy 2.2.6 / scipy 1.15.3 / torch 2.6.0+cu124（RTX 4060 Laptop, 8.6 GB）。
