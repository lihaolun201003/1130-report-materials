# CTP-1.0 源码级审计报告

**审计对象**：`experiments/CROSSTALK_PREDICTION_20H_1283_1024/`（`src/*.py`、`scripts/*.py`、`config/simulation_config.yaml`、`reports/SIMULATION_REPORT.md`）
**审计方式**：只读导入 legacy 包（未修改任何文件），另写独立实现复核（`audit/scripts/`）；每一条数值结论都来自实际运行，证据文件见 `audit/*.json|csv` 与 `audit/logs_*.txt`。
**约定**：`文件:行号` 指 legacy 源文件行号；“实测”指本审计运行结果。

---

## 0. 摘要：致命缺陷与影响

| # | 级别 | 位置 | 缺陷 | 后果（实测） |
|---|---|---|---|---|
| 1 | **致命** | `crossing.py:197` | 离散入射模用 `n2_bg[1:-1,0]**2`：取到被覆写为 n_clad² 的 Dirichlet 边界列，且把 n² 再平方成 n⁴ | 入射场是虚假均匀介质的高阶 box sine（n_eff=1.63，460 个极值）；与真导模重叠²=9.1e-10。整个 E5 交叉矩阵因此无效 |
| 2 | **致命** | `coupling.py:149-158` | Neumann ghost node 只改 `A[r,r+1]`，未改 `A[r+1,r]` → 非对称矩阵喂给 `eigsh` | 本征对残差 1e-2…1e-4；同一调用 κ(50 µm) 重复 8 次差 **258 倍**；1.04e-4 mm⁻¹ 为噪声（物理值 ~1e-10） |
| 3 | **致命** | `board.py:53-55,77` + `run_e5.py:38,65` | 全板 1283 个交点统一用常数 p=1e-7，角度/位置信息不进矩阵；`p_cross_nominal` 形参未使用 | 所有 headline 数字严格 = p×几何权重；`T_upper≡T_nominal`；−65.91/−58.38 dB 是概率记账 |
| 4 | 严重 | `crossing.py:210-213` | 导模判据用 acos 映射后的 β 而非 √Λ | 8 个 box 模式全被判为“导模”；报告写“支持 3 个导模”（对 2-D 方芯成立）但交叉求解器用 8 个 |
| 5 | 严重 | `crossing.py:255-269` | 只分析 +u 一个交叉臂；端口在 5°–20° 仍位于芯区重叠区 | 交叉串扰被系统性低估；`T_cross` 与角度无关 |
| 6 | 严重 | `crossing.py:41-48` | PML 用 ∂(1/s∂)，缺外层 1/s 与 s_x s_y 质量项（非标量 Helmholtz 的一致 PML） | 数值反射偏大；实测底 1e-8（修正实现可到 1e-9） |
| 7 | 严重 | `crossing.py:312-366` | `crossing_born` 声称旋转后积分可因子化为 Φ(q)²/sinθ；对旋转条带该分解不成立（漏了 β sinθ 的横向 Fourier 因子与正确的 1/sinθ 结构） | 5°: 振幅=71.6（T 饱和为 1），10°: T=0.94，与修正 FDFD 差 40 倍；模型未进入任何最终结果 |
| 8 | 严重 | `coupling.py:209-221` + `crossing.py:286-306` | κ(d<d_lo) 被钳位到 κ(10.8 µm)=0.72 mm⁻¹；CMT 积分 86.5% 来自该平台 | legacy CMT −30 dB @5° 是钳位伪值；物理外推给 −27.5 dB，物理 κ 的 CMT 在 5° 已强耦合失效 |
| 9 | 严重 | `run_e3.py:63-64` | 实际用 d_port=10 µm / pml=5 µm / max_unknowns=420k，与配置文件 d_port=20/pml=4/230k 不符；网格按 1.1× 粗化（5°: 0.2196，7.5°: 0.1815） | 角度扫描混入网格变化；5° 离散 β 膨胀 15.6% |
| 10 | 中 | `board.py:11-13` | “column sum ≤1 by construction” 数学上不成立 | α=0 时最大列和 1.000143（p=1e-3）、1.0137（p=1e-2） |
| 11 | 中 | `report.py:209-213` + `SIMULATION_REPORT.md:85` | 报告的三项验证 (ii) 平行耦合器 −20.9/−21.3 dB 在代码中**不存在**（字符串硬编码，且重复两次）；(i) no-cross 是恒零对照；(iii) 交叉求解器没有网格/域收敛研究 | 无法作为模型验证 |
| 12 | 中 | `modes.py:437` | graded 网格细区只 ±13.5 µm，d>20 µm 的重叠积分在粗网格上采样 | κ_overlap 在 d=23.6 处偏差 275%，却进入验证/拟合区间 |
| 13 | 中 | `modes.py:192`/`coupling.py:164`/`crossing.py:302` vs `crossing.py:205-208` | β 约定不统一：一部分用 √Λ（物理），交叉 FDFD 用 acos 修正（离散） | 同一 pipeline 内 β 差 5.7%（h=0.15） |
| 14 | 低 | `dataio.py:163-167` | SHA256 清单中的文件缺失时抛未捕获 FileNotFoundError | 输入不完整时崩溃而非报错退出 |
| 15 | 低 | `interactions.py:278-363` + `run_e5.py` | 61691 条近邻记录无光学模型且从未进入 board | 死数据；`interactions.optical_cutoff_um=60` 从未使用 |
| 16 | 低 | `lengths.py:29` | `bend_extra_loss_db=0` 常数；`min_bend_radius_mm` 未参与任何损耗模型 | 弯曲损耗未建模（但弯曲弧长计入传播损耗） |

---

## 1. `src/config.py`

**声称**：中央配置，所有物理常数与单位；`units.length=mm/wavelength=nm/propagation_loss=dB/cm`（L21-27）。

**实际**：
* 单位命名基本自洽：`_um`/`_mm` 后缀明确；`propagation_loss_db_per_cm=0.05`（L52）在 `lengths.py:15` 与 `board.py:57` 都以 `/10` 转为 dB/mm（正确）。
* `crossing_model`（L114-133）中的 `grid_um=0.15`、`pml_cells=12`、`pml_thickness_um=4.0`、`domain_margin_um=12`、`max_unknowns=230000` 与 **实际产生结果的运行参数不一致**：`run_e3.py:63-64` 用 `d_port_um=10.0, max_unknowns=420000, pml_um=5.0`，`run_e6.py:50` 同样如此；`pml_cells` 在整个代码库中**从未被读取**（`_pml()` 用物理厚度而非 cell 数：`crossing.py:59-65`）。
* L128-132 的 `resolution_floor=1e-7` 及其注释（“local FDFD resolves crossing crosstalk down to ~1e-7”）是本项目最关键的**未经验证声明**：实测（本审计 B 节）legacy 的 1e-8 是错误入射模的伪值，修正实现的数值底 ≈1e-8（θ=90°）但在小角度处耦合信号远高于此；该 floor 被 `run_e5.py:35-38` 直接用作全板 p，构成因果链的核心。
* L12-15 `BEST_VALID` 指向外部工程 `OpticalWaveguideRouter2D/...`；该路径在本机存在。

**缺陷**：F1（配置与实际运行参数不符）、F2（resolution_floor 无依据）。

---

## 2. `src/modes.py`（2-D 标量弱导模求解）

**声称**（L1-14）：标量 Helmholtz `∇²ψ + k0²n²ψ = β²ψ`，二阶差分、Dirichlet、移位反演 Lanczos；导模判据 `n_clad<n_eff<n_core`；归一化 `∫|ψ|²dA=1`（µm 单位）；报告“3 个导模 n_eff(fund)=1.504557”。

**实际计算逐项审计**：

1. **离散格式正确**：`_laplacian_2d`（L61-72）为标准 5 点 Laplacian，`offx[np.arange(1,ny)*nx-1]=0`（L66）避免了行间 wrap；`main=-4/h²`、off=1/h²（L70）。`solve_modes` 中 `n2=n**2`（L181）后 `A=L+diag(k0²n2)`（L80），**没有**重复平方（与 `crossing.py:197` 形成对比）。
2. **边界条件**：L180 把最外圈折射率设为 n_clad，但真正起作用的是 L182 `interior=n2[1:-1,1:-1]` + L188 把边界 ψ 置零 = **Dirichlet**，与 L7 声称一致。边界 n_clad 覆写是多余但无害的。
3. **移位反演**：L183 `sigma=(k0*nc)²(1−1e-6)`；`_solve_system` L83 `eigsh(A,k=12,sigma=sigma,which="LM",tol=1e-10)`。`_solve_system:82` 的 fallback `sigma=max(A.diagonal())*(1−1e-6)` 是**死代码**且其值约为 `k0²n_core²−4/h²<0`（错误的 shift），只因为 `solve_modes` 总显式传入 sigma 才没触发。
4. **β=√λ**：L192 `beta=sqrt(clip(vals))`。对“沿 x 不变”的横截面本征问题，√Λ 是连续算子 β 的离散近似，**没有** sin 修正——这对模式求解本身可以接受（O(h²) 误差，实测 n_eff 网格收敛 7e-5），但它与 `crossing.py` 的传播约定不一致：交叉 FDFD 必须用 `acos(1−Λh²/2)/h`（`crossing.py:205-208`，正确实现），两者在 h=0.15 时差 **5.67%**（实测：√Λ=7.2163 vs acos=7.6253 /µm）。`crossing_cmt`（`crossing.py:302`）仍用未修正的 `eim.beta2d`，`crossing_born` 亦然。**这是 pipeline 级的一致性问题**（F13）。
5. **归一化**：L190 `norm=sqrt(Σ|f|² h²)` → `∫|ψ|²dA=1`（µm⁻² 的 ψ）。`ModeSolution.wx/wy=grid`（L124-131）、`dA=outer(wy,wx)`（L134-135）正确。
6. **模式计数**：L106 `guided_mask=(n_eff>n_clad+1e-7)&(n_eff<n_core−1e-9)`；eigsh 取 shift 附近 12 个本征值。实测（`run_audit_checks.py`）：返回 12 个，guided=**3**，n_eff=[1.504557, 1.501874, 1.501874, 1.499469, …]；后 9 个 n_eff<n_clad 被正确过滤。**“3 个导模”成立**（后两个是方芯的 x/y 简并模，数值上完全简并是网格对称性的结果）。
7. **收敛性**：`mode_convergence.csv` 实测：grid 0.40→0.10 时 n_eff_fund 变化 7e-5；domain 16.8→39.2 µm 变化 <1e-6；mode 数稳定为 3。与报告 L131 一致 ✓。
8. **EIM 构造**（L199-268）：
   * `_slab_solve`（L213-226）一维 Dirichlet 本征解，返回 `sqrt(vals[0])/k0`；
   * `effective_index_model`：先竖向 slab（高 9 µm，芯 n0+Δn）得 `n_slab=1.505521303`（L254），再用 `n_slab` 作芯做横向 slab（宽 9 µm）得 `n_eff=1.504584836`（L263）。
   * **一致性**：与完整 2-D 标量解 `n_eff=1.504557429` 的相对偏差 **1.82e-5（0.0018%）**（实测，与报告 L131 一致 ✓）。EIM 的 `n_slab`（1.505521）与 2-D `n_eff`（1.504585）物理上自洽。
   * **但** `crossing.py` 使用的是“2-level EIM 条带”结构（`_index_grid_2d`：n_slab 在 |y|<w/2 的条带内，n0 在外），其横向导模在离散结构下有 **2 个**（V=2.78>π/2；实测 `local_guided_modes`：n_eff=1.504607/1.502084，分别为 even 基模与 odd TE1），而 `crossing.solve_crossing` 的伪模构造完全不反映这一点。
9. **graded 版本**（L330-475）：`_d2_interior`（L354-364）非均匀三点系数经复核**正确**；`solve_modes_graded` L450 `k0²*sub²` 其中 `sub` 是折射率（`index_grid` 返回 n）→ 正确；L471-472 用 `dA` 归一化 ✓。
   * **缺陷 F12**：L437 `fine_half = max(1.5*max(w,hgt),12)=13.5 µm`，此后网格按 1.22 增长到 1.2 µm；`coupling.kappa_overlap` 需要在平移 d 后对第二个芯积分，d>~20 µm 时芯落在 0.24–1.2 µm 的粗网格上（实测 d=22.8→23.6 时 κ 从 4.81e-4 跳到 1.13e-4，与超模相对偏差 275%），却被 `build_coupling_model` 当作“验证数据”。
10. **interpolator**（L137-155）：bilinear，clamp 参数（L148-149）使域外返回 0（L152-153）✓。

**该文件结论**：模式求解器本身基本正确（3 个导模、n_eff、收敛性经核实），主要问题在 β 约定不一致（F13）与 graded 网格对重叠积分的污染（F12）。

---

## 3. `src/coupling.py`（双波导耦合）

**声称**（L1-23）：两条独立路线——(1) 对称性半域超模分裂，κ=πΔn_eff/λ（λ in mm → mm⁻¹）；(2) 扰动重叠积分 κ=k0²/(2β)·∫(n₂²−n_clad²)ψ₁ψ₂dA/∫ψ₁²dA；两者在可信区应一致。

**实际计算与缺陷**：

1. **`_laplacian_stretched`（L38-51）**：与 `modes._laplacian_2d` 逐位相同，**没有任何 stretching**——函数名误导；不影响数值。
2. **`supermode_kappa`（L75-175）**：
   * 半域构造：axis='x' 时 `Lx=d/2+14`、`xa=arange(nxa)*h`（镜面在 x=0，芯在 x=d/2）；axis='y' 类似（L96-128）。
   * **Neumann ghost node（L149-158）——本项目的头号数值缺陷**：
     ```python
     A[r, r + 1] = 2.0 / grid_um ** 2      # 只改上三角
     ```
     对角元保持 −4/h²（对 2-D ghost 模板而言 −4/h² **本身是对的**：x 向 −2/h²+2/h²、y 向 −2/h²+1/h²），但对称位置 `A[r+1,r]` 仍是 1/h² ⇒ **矩阵非对称**（实测 ‖A−Aᵀ‖/‖A‖=3.6%–4.9%，`c_extra_asymmetry.json`）。`eigsh`（L159）是**对称** Lanczos 求解器，喂非对称矩阵 ⇒ 返回的 Ritz 对不是任何对称算子的本征值。
     实测后果（d=50 µm）：本征对残差 1e-2…1e-4（对称化后 3.5e-14）；**同一调用重复 8 次 κ 在 3.4e-7…8.7e-5 mm⁻¹ 间跳动（258×）**；axis='x' 与 axis='y'（物理上应相等）结果可差 4 倍。e3 记录的 1.0387e-4 只是其中一次随机抽样。
   * `vals[0]` 选取（L163）：`order=argsort(vals)[::-1]; results[bc]=sqrt(vals[0])/k0`——假设最大本征值是基模。对一个被非对称性污染的谱，这个假设无保证。
   * `κ=πΔn/λ`（L164-166）：**量纲正确**（Δn 无量纲、λ in mm → mm⁻¹）。
   * docstring L8-10 的“两次求解只差一行边界条件，分裂量不受本征值绝对精度限制”是**错误论断**：两个分支的矩阵维度不同（even 含镜面节点/odd 不含）、域网格不同、且非对称化后求解器本身失效；实测残差与重复性都否证该说法。
3. **`kappa_overlap`（L55-71）**：公式与量纲正确（实测与 1-D EIM 重叠积分在 d=10–20 µm 一致到 3–26%）；`delta=index_grid(...)**2−n0**²`（L62-64）中 `index_grid` 返回 n，所以是 n²−n₀² ✓；分母 `∫f1²dA=1` ✓。**缺陷**：所用 `solve_modes_graded` 的细区限制（见 F12），大 d 不可信。
4. **`build_coupling_model`（L227-303）**：
   * `d_lo=1.2w=10.8`（L234）——d<d_lo 时模型的 κ 被**钳位**为该处的值（L218-219 `out[low]=exp(self._logk[0])`）；
   * L240 只用**超模** κ 建模型（`ks.append(sm[...])`），重叠积分仅作验证列（L241）；因此 L267-272 的 γ 拟合被 d≥23 µm 的超模噪声污染（实测 κ_super 在 22.8→23.6 µm 从 4.07e-4 升到 4.23e-4，非单调）；
   * L283-302 指数外推；e3_summary 的 `kappa_50um_mm_inv=1.23e-10` 即 `κ(20.8µm)·e^{−γ(50−20.8)}`，γ=0.5724 被噪声抬高（物理 γ=0.5634）；
   * 模型数值上碰巧与物理值同量级（1.23e-10 vs 1.98e-10），但方法不可靠。
5. **`CouplingModel.kappa`（L209-221）**：对数线性插值 + d>d_hi 指数外推 + d<d_lo 钳位 + [1e-14,100] 截断。钳位是 `crossing_cmt` 在 5° 出现 −30 dB 的直接原因（见 `crossing.py` 审计）。

**该文件结论**：重叠积分公式可用（小 d），超模路线因非对称矩阵而**整体失效**（F2 级缺陷），模型构建用了错误的数据源。

---

## 4. `src/crossing.py`（交叉局部电磁模型）——重点

### 4.1 声称（L1-26）

1. EIM：竖向 slab → n_slab；平面内用 n_slab 条带；
2. **“离散入射模”**：在真实 FDFD 网格上求背景结构本征模，以满足离散背景算子到机器精度（因为解析 `exp(iβx)` 在 0.15 µm 网格上有 ~5% 相位残差）；
3. **精确散射场方程**（非 Born）：`(∇²+k0²n²)ψ_s = −k0²(n²−n_bg²)ψ_inc`；
4. 端口：在两条波导分离 ≥20 µm 的平面上把 ψ_s 投影到该波导的全部导模。

### 4.2 实际计算

| 环节 | 代码 | 实际 |
|---|---|---|
| 域尺寸 | `_domain_for_angle` L82-90 | `u_port=d_port/sinθ`；`x_port=|u_port cosθ|`；`Lx=max(x_port+margin,3w+margin)`；`Ly=max(d_port+margin,2.5w+margin)`。d_port=10（run_e3）时 Ly=34.5 µm；5° 时 Lx=126.3 µm。域的内存循环 L174-187 以 1.1× 粗化网格直到 N≤max_unknowns——**这不是收敛研究，而是被迫粗化** |
| 折射率 | `_index_grid_2d` L93-104 | 返回 **n²**（命名 n2 正确），但 L103 把最外圈（含 `[:,0]`）覆写为 n0² |
| 入射模 | L195-225 | **见 4.3，致命缺陷** |
| 散射方程 | L227-244 | `A=Dx⊗I+I⊗Dy+diag(k0²n²)`（PML 复数 s）；`rhs=−k0²Δn²ψ_inc`（L239）。代数上式子正确，**但前提 `A_bgψ_inc=0` 因入射模错误而不成立**；且 PML 区缺少 `(A_bg,PML−A_bg,plain)ψ_inc` 源项 |
| 端口 1 | L246-253 | 在 x₁=Lx−pml−3h 取列，`a1=Σψ_sφ h e^{−iβx}`，`T=|1+a1₀|²+Σ|a1_j|²` |
| 端口 2 | L255-269 | 在 `pc=u_port(cosθ,sinθ)` 处取**垂直于交叉波导**的线，双线性插值，`a2=Σψ_sφ(s)ds`（**未去相位参考**——只取 |a2|² 时无害），`T_cross=Σ|a2_j|²`；**只分析 +u 一臂** |
| 结果 | L271-279 | `T_loss=max(0,1−T_through−T_cross)`（把负损耗抹平）；`energy_error=T_through+T_cross−1` 存了但未使用 |

### 4.3 致命缺陷：离散入射模（`crossing.py:196-225`）

```python
Dyn = _plain_d2(y, h)
Ty = Dyn + sp.diags(k0 ** 2 * n2_bg[1:-1, 0] ** 2)        # line 197
```

两处独立错误：
1. `_index_grid_2d` 的 L103 已把 `n2_bg[:,0]` 覆写为 n0² ⇒ 该“横向剖面”**没有芯**，是纯 cladding；
2. `n2_bg` 已是 n²，再 `**2` 变成 **n⁴**。

于是 `Ty` 是“虚假均匀 n⁴ 介质”的一维 Dirichlet 算子，其近 shift 的 8 个本征值是**高阶 box sine**。实测（`audit/a_diagnostics.json`）：

| θ | n_eff_disc | φ 局部极值数 | 与真导模重叠² |
|---|---:|---:|---:|
| 5° | 1.766197 | 314 | 5.2e-34 |
| 10°–90° | 1.630556 | 460 | 9.1e-10 |

（正确构造应取 `n2_bg[1:-1, nx//2]`，即经过芯的列，且**不再平方**；修正后 h=0.15 时 n_eff_disc=1.5899，对应真导模。）随后：
* L204-209 的 `acos(1−Λh²/2)/h` 离散色散公式**本身正确**（用于把横截面本征值 Λ 换算成网格传播常数），但作用在错误的 Λ 上；
* L210-213 的导模过滤用 `beta/k0 > n0`（acos 映射后的 β）而不是 `sqrt(Λ)/k0 > n0` ⇒ 8 个 box 模式全被保留（e3 表 `n_guided_modes=8` 由此而来）；
* L237 `psi_inc=e^{iβx}φ` 因此不是输入波导的导模，整个求解的是“虚假平面波入射到斜条带”的散射问题；
* L238-239 的散射场方程缺少 `A_bgψ_inc≠0` 的补偿源（在 PML 区尤其明显），使计算出的 ψ_s 也不满足总场方程（实测：θ=10° 时总场在物理区内的离散残差 max|Aψ_tot|=6.9e-3，而 θ=30° 时 1.5e-12）。

### 4.4 端口功率归一化（任务重点）：错在哪、没错在哪

**没问题的部分**：对纯 2-D 标量场，若模态剖面满足 `∫|φ|²dℓ=1`，则时间平均功率 `P=(1/2ωμ₀)Im∫ψ*∂ψ/∂n dℓ` 对同频所有模都正比于同一个 β（β≈k0n_eff），因此功率比可用 |a|²，**不需要额外的 cosθ 或群速因子**（同频、同一介质、同一波导截面，β 相同）。在斜端口上“用旋转后的同一剖面 φ(s) 投影”在结构旋转不变的前提下**也是对的**；未去相位参考 `e^{−iβu}` 只影响相位、不影响 |a|²。因此**任务书怀疑的“缺少 cosθ / 群速因子”并不是该实现的主要错误**（只有在比较不同 β 的模式或不同端口法向通量时才会出现这些因子；本审计的独立分析实现了完整通量积分并确认 |a|² 与通量比一致到 1% 量级）。

**真正错的地方**：
1. **用错模**：投影用的 φ（L220-225）是上述虚假 box 模式（与真导模重叠² 9e-10），所以“投影”没有意义；
2. **导模集合错**（L210-213）：8 个非导模被当作导模；
3. **只取 +u 一臂**（L257）：−u 臂从未计算；对 90° 两臂对称，实测两臂功率同量级（本审计 A 节：cross_plus/cross_minus 均 ~1e-12/1e-9 量级）；
4. **端口位置**：`u_port=d_port/sinθ`，5°–20° 时 u_port 处的“两波导间距”只有 10 µm，而两波导的芯区在 5° 时于 |u|<103 µm 内**仍重叠**；端口平面切过合并区，不是“分离 ≥20 µm 的自由端口”；
5. **PML 不一致**：入射场不满足含 PML 的背景算子，因此“散射场=总场−入射场”的分解在 PML 区不成立；
6. **`T_through=|1+a1|²`**：`a1` 是 ψ_s 在虚假 φ 上的投影；实测 T−1 中 2Re(a1)=+1.5e-3…+1.7e-3 占绝对主导（见 B 节），故 T_through>1 是投影伪干涉，不是物理增益。

**结论**：legacy `T_cross`（1.1e-8…6.9e-8）和 `T_through`（1.0015…）都不是“带端口归一化误差的物理结果”，而是**错误入射场 + 错误模投影**的产物；独立多模端口分析在本审计的修正求解器上给出 5°/10°/15° 的 T_cross（总导模）−49.7/−25.3/−44.8 dB（基模→基模 −52.9/−40.8/−54.9 dB），比 legacy 大 2–5 个量级且强烈依赖角度；且 5°–15° 尚未网格/域收敛（见异常报告 A.5）。

### 4.5 `crossing_cmt`（L286-306）

```
A = ∫ κ(|s|sinθ) e^{−i β(1−cosθ)s} ds        # L303
s_max = κ_model.d_hi / sinθ                    # L297-298
T_cross = min(|A|², 1)                         # L305
```
* 公式结构（相位匹配项 β(1−cosθ)、只取相位匹配的 +s 臂）**基本正确**；
* **但 κ 模型在 d<d_lo=10.8 µm 被钳位为常数 κ(10.8)=0.72 mm⁻¹**（`coupling.py:218-219`）⇒ 5° 时 |s|<124 µm 的整个平台区（占 |κ| 积分的 **86.5%**，实测）用的是任意常数，CMT 积分由钳位而非物理 κ 决定；s_max=23.6/sinθ 又截断了积分；
* β 用 `eim.beta2d=√Λ`（未做离散色散修正），与同文件 FDFD 的 acos β 差 5.7%；
* L305 的 `min(|A|²,1)` 是功率硬截断（非幺正化），|A|>1 时结果完全失真（物理 κ 的 CMT 在 5° 给出 |A|=1.29）。

实测复核（`audit/logs_checks.txt`）：legacy CMT 数值精确复现（5/10/15° = −30.0/−41.1/−50.5 dB ✓ 与任务书一致），但 86.5% 的积分落在钳位区；把钳位换成物理外推得 −27.5/−39.0/−48.6 dB；用独立 1-D EIM κ 的 CMT 得 5°: |A|=1.29（弱耦合失效）、10°: −27.8 dB、15°: −54.0 dB。

### 4.6 `crossing_born`（L312-366）

* 声称（L320-330）：`a2 = −i k0²/(2β)·∫∫Δn²φ1(y)φ2(s)exp(iβ[u(cos t−1)−s sin t])ds du`，并“因为旋转后积分因子化”得 `a2 = −i k0²/(2β)·Φ(q)²/sin(t)`，`q=−β tan(t/2)`，`Φ(q)=∫φ(s)e^{iqs}ds`。
* **代数错误**：在 (u,s) 旋转坐标下，`ψ1=φ(y)=φ(u sinθ+s cosθ)`、`ψ2=φ(s)`、相位 `Δk·r=−βu(1−cosθ)−βs sinθ`。u 积分给出 `(1/sinθ)·Φ(β(1−cosθ)/sinθ)=Φ(β tan(θ/2))/sinθ`，而 s 积分给出的是 `∫φ(s)φ(s)e^{−iβs sinθ}ds` 形式（含横向剖面自身的 Fourier 因子），**不是** 同一个 `Φ(q)` 再平方；旋转后积分的“因子化”只对 θ=0（平行）成立。代码把两个不同的 Fourier 变换替换成同一个 Φ(q)²，量纲/系数也不自洽（L326-330 的推导跳步）。
* **数值荒谬**（实测）：5°：`|Φ|=1.98`，amp=71.6 → `sin²(min(amp,π/2))=1`（T=0 dB）；10°：amp=1.33 → T=0.94；15°：T=1.3e-3；90°：T=1.6e-14。与修正 FDFD 相比 5°/10° 差 3–10 个量级。
* L334-336 “unitarised as P=sin²(|a2|)” 是任意启发式；L348-353 的 `regime/uncertainty_db=5/10/20 dB` 无依据。该模型未进入 board，只作为报告中的“校验”出现。

### 4.7 `run_e3.py` 的运行参数（F9）

`run_e3.py:63-64`：`solve_crossing(opt, a, eim=eim, d_port_um=10.0, max_unknowns=420_000, pml_um=5.0)` ⇒ 与 `config/simulation_config.yaml:crossing_model` 的 d_port=20/pml=4/max_unknowns=230k 不一致；且 5°/7.5° 时网格被 L174-187 的循环粗化到 0.2196/0.1815 µm，导致角度扫描的离散色散逐点不同（5° 时 β 膨胀 15.6%）。

---

## 5. `src/board.py`（全板 1024×1024 传输矩阵）

**声称**（L1-13）：由真实 XYZ 几何组装；对角=传播损耗−交叉扣除；非对角=交叉点泄漏 + 剩余传播损耗；二阶项显式累加且可忽略；“no gain is possible: every column sum is <= 1 by construction and is verified numerically”。

**实际**：
1. **固定 p**（F3）：
   * 签名 L53-55 接受 `p_cross` 与 `p_cross_nominal`，但 **函数体内从未使用 `p_cross_nominal`**（全文件 grep 只有签名出现）；
   * L73-97 对每个事件 `p=float(p_cross)`，`angle_deg` 只写进 `pair_records`（L93），不进矩阵；
   * L81-84 `T[j,i]+=p·f_ij` 与 `T_upper[j,i]+=p·f_ij` **完全相同** ⇒ 实测 `np.array_equal(T_upper,T_nominal)=True`（`checks_summary.json`）；
   * `run_e5.py:38,65` 传 `p_floor=1e-7` 常数 ⇒ 角度、位置、模式、FDTD 曲线全部不进入矩阵；实测 1283 个事件的 `P_cross_used` 唯一值 =1e-7，与角度相关系数 =0。
2. **对角** L99-102：`T[i,i]*=(1−p)^{n_cross[i]}`；与 L81 的注入共用同一 p，这是列和接近守恒的原因，但该“守恒”依赖 p 为常数与传播损耗>0（见缺陷 10）。
3. **二阶** L104-139：`p2=p·p·loss...`；实测 max T 在 p=1e-7 时 9.851e-15、p=1e-3 时 9.851e-7，严格 ∝p²；方向判断 `s_k2<=s_k1`（L127）跳过反向。
4. **列和** L141-145 与 docstring L11-13：数学上不成立——列和 = loss·(1−p)^n + Σp·f ≤ (1−p)^n + n·p = 1 + n(n−1)p²/2 > 1。实测（α 置零）：p=1e-3 最大列和 1.000143，p=1e-2 时 1.0137。e5_summary 中 0.72–0.95 的列和来自传播损耗（对角 0.72–0.95），不是构造保证。
5. `db()` L26-28 把功率下截到 1e-30（−300 dB）——只在显示层面，尚可。
6. `route_statistics` L149-187：`T=board.T_upper`（与 T_nominal 相同，故“上界”无意义）；`worst=argsort(col)`（L162）按列取，`worst_victim_routes` 逻辑用 `j if j<k else j+1` 把自身索引排除——正确。
7. `hotspot_records` L190-211：按 (z, x/2, y/2) 聚类，`P_cross` 全部为常数 p ⇒ 热点排序等价于“每 2 mm 单元内的交点数”。

**结论**：headline 数字（−65.91 dB 最坏对、−58.38 dB 最坏总泄漏）精确等于 `p × 几何/损耗权重`（W_max=2.5672、V_max=14.526；p 变化 100 倍 → dB 恰好平移 +40 dB），是**概率记账模型**，不是光学模型。

---

## 6. `src/interactions.py`（交叉检测 + 近邻分析）

**声称**（L1-11）：独立解析重推所有同层中心线交点（期望 1283 事件/1221 对），并用 KD-tree 找出所有非交叉 3-D 近邻，保留跨层/过渡/多弧情况。

**实际**：
* `detect_crossings`（L133-213）**工作正常**：实测 events=**1283**、pairs=**1221**、routes_with_crossings=647、planes=20，与官方 crossing_stats 完全一致；位置四舍五入到 0.01 mm 后 1258/1283 匹配（25 个来自弧-弧交点的位置量化差异）——**该结果可复用**（几何可靠）。
  * 去重逻辑 L187-201 只与 `dedup[-8:]` 比较，理论上可能漏掉更早的重复，但实测 raw 1298→1283 与官方一致，无实际影响。
* `near_approaches`（L278-363）：先 0.1 mm 采样 + KD-tree 150 µm 筛选（L288-299），再做段 AABB 过滤（L308-315），最后 `min_distance_between`（L241-275，KD-tree 初值 + 45 轮 9×9 局部网格细化）。实测 61691 条记录、min 非交叉距离 49.999999999999936 µm（**恰好 50 µm，是布局 50 µm 节距的量化产物，不是物理最小值**）、median 72.03 µm、跨层 60318 条、含 crossing 对 1342 条。
* **但**：
  * 近邻记录**没有任何光学模型**（无 κ(d)、无耦合功率、无模式），只是几何距离；
  * `run_e5.py` 只读 `crossing_events_detected.csv`，**从不读 `interaction_regions.csv`** ⇒ 61691 条记录是死数据；
  * `config.interactions.optical_cutoff_um=60`（`config.py:95`）从未被使用，`min_parallel_length_um=0.5` 亦未使用；
  * “近邻是否排除交叉区”：代码把 `is_cross` 的记录以 d=0 保留（L320-327），但 board 不用这些记录，所以问题不存在于最终模型（因为最终模型完全没用它）。

**结论**：交叉检测可用；近邻分析是**半成品**：几何上合理，但没有物理模型，也未接入最终矩阵。

---

## 7. `src/geom3d.py`（三维中心线几何）

**声称**（L1-18）：line/arc/transition 三种解析原语；transition 是“两段等半径精确圆弧的 G1 S 曲线”，弧长解析、无折线近似。

**实际（复核正确）**：
* `_transition_xy_z`（L80-99）：第一段 `xy1=p0+R sinφ d`、`z1=z0+sgn R(1−cosφ)`，φ=2θu（u≤0.5）；第二段以 `c2_xy=p1`、`c2_z=z0+sgnR(1−cosθ)−sgnR cosθ` 为中心，`xy2=p1−R sin(θ−ψ)d`、`z2=c2_z+sgnR cos(θ−ψ)`。在 u=0.5 与 u=1 处与第一段/终点逐点连续（本审计逐行推导确认）；`theta=acos(1−|dz|/(2R))`（L274）保证总高差 2R(1−cosθ)=|dz| ✓（L276 `p1=p0+2R sinθ d` 保证横向位移）；
* `length=2Rθ`（L280）为真实弧长 ✓；
* 切线 `tangent`（L101-124）在 u=0.5 连续（G1），曲率在 u=0.5 变号（G1 非 G2，与 docstring 一致）；
* `aabb`（L135-153）：line/transition 用端点 min/max（transition 的 xy 沿 d 单调、z 单调 ⇒ 精确）；arc 补 π/2 倍数点 ✓；
* `recompute`（L232-240）正确；`Route.point_at_s/tangent_at_s/curvature_at_s` 用 `searchsorted(s_breaks)` ✓。
* **实测验证**：1024 条线路总长 156597.221522 mm 与权威值误差 −3.4e-7 mm（相对 −2.2e-12），逐路分解最大误差 4.97e-10 mm；1024 条全部吻合。**该模块可靠，可复用**。
* 唯一问题：`bend_extra_loss_db=0` 使 transition/arc 的曲率不产生额外损耗（属 `lengths.py` 的模型选择，不是几何错误）。

---

## 8. `src/lengths.py`（长度与传播损耗）

**实际**：
* L14-15：`alpha=0.05 dB/cm`；`alpha_per_mm=alpha/10=0.005 dB/mm` ✓；
* L18-23：按 line/arc/transition 分类累加真实弧长；L24-27 按 tag（lead/fanout/body/mid）分解；
* L29：`loss_bend=CONFIG[...]*1.0` = **常数 0**（配置里就是 0）——`min_bend_radius_mm=15` 不参与任何计算，弯曲额外损耗未建模（只把弧长计入 0.005 dB/mm 的传播损耗）；
* L55 `L_decomposition_error = L_tot − declared`；实测全部 1024 条 <5e-10 mm ✓；
* L106 `length_check_passed = |abs_err|<1e-4`（实测 −3.4e-7 ✓）。
* 单位一致，无缺陷；**输出可复用**（长度/基础损耗是 safe 的）。

---

## 9. `src/dataio.py`（输入校验/序列化）

**声称**：SHA256 校验、数据集加载、JSON/CSV/YAML 写出。

**实际与缺陷**：
* `sha256_file` L21-29 分块读取 ✓；
* `load_dataset` L150-183：对 `SHA256.json` 列出的每个文件计算哈希；`critical` 集合（L158-162）不匹配才 raise（L175-178）；非 critical 不匹配仅记录（L169-174）。实测：10 个文件，1 个不匹配 `BEST_VALID.json`（非 critical；代码注释 L154-157 已说明它被重写过），routes 哈希双保险（L179-182）✓。**行为符合注释**。
* **缺陷 F14**：清单中的文件缺失时 `sha256_file` 直接 `FileNotFoundError`（L163-167 无 try），不是清晰报错。
* 没有利用 `CONFIG["inputs"]` 里的 `total_length_mm_expected`/`crossing_events_expected` 做一致性断言（这些在 run_e1/e4 里另行检查）。
* `write_csv` L55-66：`fieldnames` 取第一行键 + `extrasaction="ignore"` ⇒ 后续行多出的键会被**静默丢弃**（run_e3 的若干行结构相同，暂无实际数据丢失，但是脆弱设计）。
* `dump_yaml` L70-121：实现正确（nan→`.nan`、特殊字符加引号）；`repr(float)` 可能与运行时一致。
* 单位约定：mm/nm 清晰；`TOTAL_LENGTH_MM=156597.221522` 与实测一致 ✓。

---

## 10. `src/report.py` 与 `reports/SIMULATION_REPORT.md`：声称 vs 实测

| # | 报告声明（行号） | 实测/审计结论 |
|---|---|---|
| R1 | L12/L129 “支持 3 个导模，n_eff=1.504557, 1.501874, 1.501874” | **成立**（实测 n_guided=3；后两个为方芯简并模） |
| R2 | L72 “两次求解只差一行边界条件，分裂量不受本征值绝对精度限制” | **错误**：矩阵非对称（3.6–4.9%）、残差 1e-2…1e-4、重复 8 次 κ(50) 差 258× |
| R3 | L75 “12–22 µm 中位相对偏差 1.6%，γ=0.5974 µm⁻¹” | 中位偏差 ~1.6% **成立**（实测中位 1.62%），但区间恰好止于噪声开始处（23.6 µm 处偏差 275%）；γ 被噪声抬高（物理 0.5634） |
| R4 | L83 “解析模式在 0.15 µm 网格相位残差约 5%” | **成立**（实测 5.67%） |
| R5(i) | L85 “无交叉对照组 T=1.000000” | **成立但平凡**：`rhs≡0` ⇒ ψ_s≡0，测不到任何数值底 |
| R5(ii) | L85 “平行定向耦合器 −20.9 dB vs CMT −21.3 dB” | **无代码**：字符串只硬编码在 `report.py:209-213`（生成文本中还重复两次），`src/scripts/tests` 中无对应计算 |
| R5(iii) | L85 “网格/域收敛与能量守恒检查” | **未实现**：交叉求解器没有收敛研究（域循环只粗化网格）；T_through>1 被接受、T_loss 被 max(0,·) 抹平，没有能量检查 |
| R6 | L14/L173 “全角度 −70 dB 以下、无角度趋势、交叉角不是风险判据” | **错误**：值是伪入射场/伪投影的产物；修正后 T_cross 从 1e-5（5°）跨到 1e-9（90°），强角度依赖 |
| R7 | L175 “小角度 T 略大于 1 是 PML 截断与网格色散残差” | **错误**：实测 T−1 = 2Re(a1)+|a1|²，2Re(a1)=+1.5e-3 主导，a1 是投影到非导模 box 模式的伪振幅 |
| R8 | L175 “单次交叉插入损耗低于 0.01 dB” | **错误**：修正模型 90° 已 0.0126 dB，10–15° 为 0.24 dB，5° 达 0.79 dB（粗网格） |
| R9 | L184-189 “−65.91 / −58.38 dB / 最大列和 0.949714” | **数值精确复现**，但它们是 p×几何权重的概率记账（见 D），不是光学量 |
| R10 | L131 “网格收敛 7e-5、EIM 与 2-D 偏差 0.0018%” | **成立**（实测 7e-5、1.82e-5） |
| R11 | L143 κ(50 µm)=1.23e-10 mm⁻¹ | 数值上恰与物理值同量级（1-D EIM 1.98e-10），但来自被噪声污染的超模数据的指数外推；κ(62)=1.28e-13 与 γ 拟合不可靠 |
| R12 | 报告 L85 段落重复 | `report.py:209-213` 的 `A(...)` 调用重复，生成文本出现两次（排版缺陷） |

---

## 11. 缺陷分级与影响面

| 影响面 | 是否可复用 | 说明 |
|---|---|---|
| **几何（e1/e4）**：1024 条线路长度、弧长分解、1283 交叉/1221 对/647 路/20 平面 | **可复用（已验证）** | 总长误差 −2.2e-12 相对；交叉事件与官方完全一致 |
| **传播损耗**：0.05 dB/cm × 真实弧长 | **可复用**（若弯曲损耗保持 0 的假设成立） | 但 `bend_extra_loss_db=0` 是工程假设，不是计算结果 |
| **模式求解**：3 导模、n_eff=1.504557、EIM 一致性 | **可复用（已验证）** | 需在报告中明确“3 模”与“单模激励”假设 |
| **超模 κ** | **不可复用**（F2） | 非对称矩阵 + eigsh 误用；重复性 258× |
| **重叠积分 κ** | 小 d（≲20 µm）可用，大 d 不可用（F12） | 建议改为大域 1-D EIM 或解析尾场 |
| **交叉 FDFD（T_cross/T_through/T_loss）** | **不可复用**（F1） | 入射模错误；端口/导模集合错误；需重写 |
| **crossing_cmt** | **不可复用**（F8：d_lo 钳位、s_max、β 约定） | 公式骨架可保留 |
| **crossing_born** | **不可复用**（F7：旋转积分代数错误） | 仅 θ→0 极限正确 |
| **全板 1024×1024 矩阵** | **不可复用**（F3） | 固定 p=1e-7 的概率记账；角度/位置不入矩阵；近邻记录未用 |
| **近邻分析** | 几何可用，物理模型**缺失** | 需补 κ(d)/功率模型并接入 board |

## 12. 数值证据索引

| 结论 | 证据文件 |
|---|---|
| legacy 交叉曲线逐字复现 + 入射模 bug | `audit/logs_a1.txt`, `audit/a_diagnostics.json`, `audit/a1_baseline_runs.json` |
| 修正 FDFD + 独立端口分析 A | `audit/logs_a2.txt`, `audit/a_summary.csv`, `audit/a_legacy_vs_corrected.csv`, `audit/a_energy_balance.csv` |
| 5° 域截断 | `audit/logs_a3.txt`, `audit/logs_a3b.txt`, `audit/a3_domain_test_5deg.json`, `audit/a3b_domain_symmetric_test.json` |
| T_through>1 分解 / 噪声底 / 线性对照 | `audit/logs_b.txt`, `audit/b_legacy_terms.csv`, `audit/b_floor_sweep.csv`, `audit/b_linearity.csv`, `audit/b_summary.json` |
| 超模 κ 异常 + 非对称矩阵 | `audit/logs_c*.txt`, `audit/supermode_kappa_vs_d.csv`, `audit/c_settings_sweep.csv`, `audit/c_extra_asymmetry.csv/json`, `audit/c_full_domain.csv` |
| 固定 p 全板 | `audit/logs_d.txt`, `audit/d_board_scaling.csv`, `audit/d_angle_dependent.csv`, `audit/d_pair_weight.csv`, `audit/d_summary.json` |
| 模式/β/CMT/board/sha256 校验 | `audit/logs_checks.txt`, `audit/checks_summary.json` |
| 能量通量校验 | `audit/a_energy_flux_check.csv` |
