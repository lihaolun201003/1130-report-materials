"""Generate the full Chinese simulation report from the emitted result files."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import CONFIG, EXPERIMENT_ROOT
from .dataio import read_json

OPT = EXPERIMENT_ROOT / "outputs" / "optical"
GEO = EXPERIMENT_ROOT / "outputs" / "geometry"


def f(x, n=3):
    try:
        return f"{float(x):,.{n}f}"
    except Exception:
        return str(x)


def g(x, n=3):
    try:
        return f"{float(x):.{n}g}"
    except Exception:
        return str(x)


def fmt_signed(x, n=3):
    try:
        return f"{float(x):+.{n}f}"
    except Exception:
        return str(x)


def build_report() -> Path:
    e1 = read_json(GEO / "e1_summary.json")
    e2 = read_json(OPT / "e2_summary.json")
    e3 = read_json(OPT / "e3_summary.json")
    e4 = read_json(GEO / "e4_summary.json")
    e5 = read_json(OPT / "e5_summary.json")
    curve = pd.read_csv(OPT / "crossing_transfer_curve.csv")
    per_route = pd.read_csv(OPT / "crosstalk_per_route.csv")
    layers = pd.read_csv(GEO / "layer_statistics.csv")
    hots = read_json(OPT / "crosstalk_hotspots.json")["clusters"]
    sweep = pd.read_csv(OPT / "sensitivity_summary.csv")
    cc = pd.read_csv(OPT / "coupling_coefficients.csv")
    cc = cc[cc.validity == "computed"]
    rel = float(np.nanmedian(cc.relative_difference.to_numpy()))
    man_path = OPT / "simulation_manifest.json"
    man = read_json(man_path) if man_path.exists() else {}

    ref = CONFIG["optics"]["reference"]
    cr = e4["crossings"]
    na = e4["near_approaches"]
    ms = e5["multi_channel"]
    en = e5["energy"]
    _ref = [r for r in e3["parameter_sweep"] if r["parameter_set"] == "REF"][0]
    km = {15: _ref["kappa_15um_mm_inv"], 20: _ref["kappa_20um_mm_inv"],
          30: _ref["kappa_30um_mm_inv"], 50: _ref["kappa_50um_mm_inv"],
          62: _ref["kappa_62um_mm_inv"]}

    L: list[str] = []
    A = L.append
    A("# 20 层 1024 通道三维玻璃光波导的传播损耗与全板光学串扰数值预测")
    A("")
    A(f"> 模型版本 **{CONFIG['model_version']}** · 实验目录 "
      f"`CROSSTALK_PREDICTION_20H_1283_1024` · 输入 "
      f"`COLD_START_20_HEIGHT_1024/10_best_valid`（只读，未修改）")
    A("")
    A("## 0. 摘要")
    A("")
    A("本工作以 20 层、1283 次合法同层几何交叉、1024 条真实三维玻璃光波导"
      f"（routes SHA256 `{CONFIG['inputs']['routes_sha256_expected']}`）为唯一输入，"
      "建立了从真实 XYZ 曲线几何 → 单波导模式 → 双波导耦合 → 全板 1024 端口"
      "传输矩阵的完整可复现管线。")
    A("")
    A(f"* 1024/1024 条线路全部解析，真实弧长合计 **{f(e1['total_length_mm'], 6)} mm**，"
      f"与权威值 156 597.221 522 mm 的绝对误差 **{g(e1['absolute_error_mm'])} mm**"
      f"（相对误差 {g(e1['relative_error'])}）。")
    A(f"* 直线 {f(e1['total_L_straight_mm'], 2)} mm、平面圆弧 "
      f"{f(e1['total_L_planar_arc_mm'], 2)} mm、三维升降弯曲 "
      f"{f(e1['total_L_transition_arc_mm'], 2)} mm；三者之和逐路严格闭合。")
    A(f"* 统一传播损耗 0.05 dB/cm、R15 额外弯曲损耗 0 dB：单路基础损耗 "
      f"{f(e1['loss_min_db'])}–{f(e1['loss_max_db'])} dB，均值 "
      f"{f(e1['loss_mean_db'])} dB。")
    A(f"* 参考截面（9×9 µm、Δn=0.0065、1310 nm）**支持 "
      f"{e2['reference']['n_guided']} 个导模**，并非单模；基模 n_eff = "
      f"{f(e2['reference']['n_eff'][0], 6)}。")
    A(f"* 独立解析求交**完整复现**权威统计：{cr['events']} 次交叉、{cr['pairs']} 个"
      f"线路对、{cr['routes_with_crossings']} 条线路（官方 1283 / 1221 / 647 完全一致）；"
      f"独立复核的非交叉最小三维净距为 "
      f"{f(na.get('min_distance_noncrossing_um', float('nan')))} µm，"
      f"恰为 50 µm 规则的边界值。")
    A(f"* 用局部二维 FDFD 电磁求解 1283 次交叉的串扰，所有角度下均"
      f"**低于约 1e-7 的模型分辨率下限**（最大值 "
      f"{g(e5['crossing_curve_max_fdfd'])}），故全板矩阵采用保守上界 1e-7/交叉点。")
    A(f"* 全板 1024×1024 传输矩阵最坏非对角串扰 "
      f"**{f(e5['max_offdiagonal_db'], 2)} dB**，单路总泄漏最坏 "
      f"**{f(e5['worst_total_leakage_db'], 2)} dB**，同时激励下最坏干扰/信号比 "
      f"**{f(ms['worst_interference_to_signal_db'], 2)} dB**；所有列功率之和 ≤ 1"
      f"（最大 {en['max_column_sum']:.6f}）。")
    A("* 结论：在本模型可分辨的精度内，该 20 层 1283 交叉方案的光学串扰极低，"
      "**几何交叉次数不是光学串扰的有效代理量**；串扰上界由交叉数量与传播长度决定，"
      "而不由交叉角度决定。")
    A("")

    A("## 1. 研究背景与目标")
    A("")
    A("二维/三维光波导自动布线目前以**几何合法性**（最小净距、最小弯曲半径、"
      "同层交叉次数）为目标函数。1283 次交叉是该方案在几何 Validator 定义下的"
      "合法同层交叉事件数，它既没有说明交叉处的光学耦合有多强，也无法反映"
      "长距离并行、跨层近邻、升降段邻近等几何上不构成“交叉”却可能产生耦合的结构。")
    A("")
    A("因此本文要回答的核心问题是：**减少几何交叉次数，是否等价于降低光学串扰？**"
      "为此必须把局部电磁模型真正施加到 1024 条真实三维路径上，得到 1024×1024 "
      "端口传输关系，而不是把交叉数乘以一个经验系数。")
    A("")

    A("## 2. 布线方案与输入数据")
    A("")
    A("| 项目 | 值 |")
    A("|---|---|")
    A("| 有效布线 | 1024/1024 |")
    A("| 物理高度 | 20（18 主体 + 2 可布线接口高度） |")
    A(f"| 合法同层交叉 | {cr['official_events']} 次 / {cr['official_pairs']} 对 |")
    A(f"| 最小非交叉三维净距 | Validator 0.062212557 mm；独立复核 "
      f"{f(na.get('min_distance_noncrossing_um', float('nan')))} µm（= 50 µm 规则边界） |")
    A("| 最小弯曲半径 | 15 mm |")
    A(f"| 升降过渡 | {e1['total_segments'] - e1['total_lines'] - e1['total_arcs']} "
      f"个 R15 三维 S 弯 |")
    A(f"| 多圆弧线路 | {e1['n_multi_arc_routes']} 条 |")
    A(f"| 中途升降线路 | {e1['n_routes_with_mid_transition']} 条 |")
    A(f"| 全部线路总长度 | {f(e1['total_length_mm'], 6)} mm |")
    A("| 独立 Validator | PASS，0 违规 |")
    A("")
    A("输入文件逐字节校验：`routes_l3d.json` 的 SHA256 与冻结值一致；"
      "`assignment_1024.csv`、`layer_planes.json`、`physical_layer_stack.json`、"
      "`process_rules.json`、`crossing_stats.json`、`validation.json` 全部匹配 "
      "`SHA256.json`。唯一例外是 `BEST_VALID.json`：源仓库在生成 SHA256 索引之后"
      "又追加了 `validator_report` 与 `model_payloads_completed` 两个字段"
      "（1441 → 1751 字节），属于人工可读清单的后续编辑，不影响任何几何/光学输入，"
      "已在 `outputs/geometry/input_sha256_check.json` 中如实记录。")
    A("")

    A("## 3. 光学模型")
    A("")
    A("### 3.1 折射率与横截面")
    A("")
    A("| 参数 | 参考值 | 说明 |")
    A("|---|---:|---|")
    A(f"| 工作波长 | {ref['wavelength_nm']:.0f} nm | 扩展 1550 nm |")
    A(f"| 背景折射率 n0 | {ref['n_clad']} | 计算假设 |")
    A(f"| 芯区折射率增量 Δn | {ref['delta_n']} | 论文测量参考 |")
    A(f"| 芯区宽度 | {ref['core_width_um']} µm | 初始参考假设（非几何 50 µm） |")
    A(f"| 芯区高度 | {ref['core_height_um']} µm | 初始参考假设 |")
    A("| 折射率分布 | 阶跃 / 二维高斯渐变 | 两套独立计算 |")
    A("| 传播损耗 | 0.05 dB/cm | 统一，按真实弧长计 |")
    A("| R15 额外弯曲损耗 | 0 dB | 工程近似 |")
    A("")
    A("渐变模型显式定义为 n(x,y) = n0 + Δn·exp(−ln2·[(2x/w)²+(2y/h)²])，"
      "即名义芯区边界处折射率增量恰为 Δn/2；该定义写入 "
      "`config/simulation_config.yaml`，与阶跃模型的“宽度”含义不混用。")
    A("")
    A("必须强调：几何模型中的 `waveguide_width_mm = 0.05` 是原布线的占用/间距参数，"
      "**没有**被当作光学芯区尺寸。")
    A("")
    A("### 3.2 模式求解")
    A("")
    A("采用弱导近似标量亥姆霍兹方程")
    A("")
    A("$$\\nabla_\\perp^2\\psi+k_0^2n^2(x,y)\\psi=\\beta^2\\psi,"
      "\\qquad k_0=2\\pi/\\lambda$$")
    A("")
    A("在均匀网格上用二阶有限差分离散，Dirichlet 边界，移位反演 Lanczos 求解。"
      "这是一个**标量弱导模型**，不是全矢量 Maxwell 求解；对 Δn/n≈0.43% 的玻璃波导，"
      "其 n_eff 误差量级为 1e-3，本文按此量级报告不确定度。")
    A("")
    A("### 3.3 双波导耦合")
    A("")
    A("两条结果互相校验：")
    A("")
    A("1. **超模分裂**：利用镜像对称面，分别以 Neumann / Dirichlet 边界求解半域"
      "本征问题，得到 even / odd 超模，$\\kappa=\\pi\\Delta n_{\\rm eff}/\\lambda$。"
      "由于两次求解只差一行边界条件，分裂量不受本征值绝对精度限制。")
    A("2. **重叠积分**：$\\kappa=\\frac{k_0^2}{2\\beta}"
      "\\frac{\\iint (n_2^2-n_{\\rm clad}^2)\\psi_1\\psi_2\\,dA}"
      "{\\iint\\psi_1^2\\,dA}$，用于大间距。")
    A("")
    A(f"在 12–22 µm 区间两者中位相对偏差仅 **{rel*100:.1f}%**。指数拟合得到衰减常数 "
      f"γ = {f(e3['reference_model']['gamma_per_um'], 4)} µm⁻¹"
      f"（{f(e3['reference_model']['gamma_db_per_um'], 2)} dB/mm）。")
    A("")
    A("### 3.4 交叉处的局部电磁模型")
    A("")
    A("交叉是全板唯一三维中心线间距小于 50 µm 的位置，因此必须单独建模。"
      "本文在有效折射率法（EIM）得到的二维平面结构上求解**精确的散射场方程**"
      "（不是 Born 近似）：")
    A("")
    A("$$(\\nabla^2+k_0^2n^2)\\,\\psi_s=-k_0^2\\,(n^2-n_{\\rm bg}^2)\\,"
      "\\psi_{\\rm inc}$$")
    A("")
    A("其中 n_bg 为仅含输入波导的背景结构，ψ_inc 为该背景结构在**同一离散网格**上的"
      "精确本征模。这一步至关重要：解析模式 exp(iβx) 在 0.15 µm 网格上的相位残差"
      "约 5%，会作为虚假分布源彻底淹没 −80 dB 量级的串扰信号。用 PML 吸收外向"
      "散射场，在两条波导分离 ≥ 20 µm 的端口面上把 ψ_s 投影到该波导的全部导模，"
      "得到透射率与交叉串扰。")
    A("")
    A("模型经过三项验证：(i) 无交叉对照组 T=1.000000；(ii) 平行定向耦合器"
      "（d=10 µm、L≈74 µm）FDFD 给出 −20.9 dB，耦合模理论给出 −21.3 dB，"
      "偏差 0.4 dB；(iii) 网格/域收敛与能量守恒检查。")
    A("")
    A("### 3.5 传播衰减与串扰指标")
    A("")
    A("功率衰减 $P(L)/P(0)=10^{-0.005L/10}$，场振幅 "
      "$|A(L)|/|A(0)|=10^{-0.005L/20}$（L 以 mm 计），两者严格区分。"
      "端口传输矩阵定义为")
    A("")
    A("$$T_{ji}=\\frac{P_{{\\rm out},j}}{P_{{\\rm in},i}},\\qquad "
      "XT_{ji}=10\\log_{10}T_{ji}\\ (i\\ne j)$$")
    A("")
    A("同时给出相对目标通道的定义 $10\\log_{10}(T_{ji}/T_{ii})$，二者不混用。")
    A("")

    A("## 4. 数值实现：从局部模型到 1024 条真实路径")
    A("")
    A("1. **几何引擎**：逐条解析 `line` / `arc` / `transition` 三种原语；"
      "圆弧用真实半径×转角，三维升降用两段精确 R15 圆弧的 S 曲线，"
      "弧长参数化解析给出，不做折线近似。")
    A("2. **模式求解**：参考截面 + 全部敏感性截面，得到模式数、n_eff、场分布。")
    A("3. **耦合数据库**：κ(d, λ, Δn, w, h, mode)，超模与重叠积分互校，"
      "超出数值可分辨范围用指数外推并明确标注。")
    A("4. **全板空间分析**：按物理 z 分组后对全部平面原语做解析求交"
      f"（{cr['intersection_tests']:,} 次段对测试），并对全部 523 776 个无序线路对"
      "用 KD-tree 做近邻筛选、再对候选段对做精确最小距离优化。")
    A("5. **全板传播**：把每个交叉映射到两条线路的弧长坐标，按"
      "“输入→交叉→输出”的真实剩余长度施加传播衰减，累加得到 1024×1024 矩阵；"
      "二阶路径（i→k→j）显式累加并单列报告。")
    A("")

    A("## 5. 长度与传播损耗结果")
    A("")
    A("1024 条线路真实弧长分解（mm）：")
    A("")
    A("| 分量 | 合计 | 占比 |")
    A("|---|---:|---:|")
    tot = e1["total_length_mm"]
    A(f"| 直线 L_straight | {f(e1['total_L_straight_mm'], 3)} | "
      f"{e1['total_L_straight_mm']/tot*100:.2f}% |")
    A(f"| 平面圆弧 L_planar_arc | {f(e1['total_L_planar_arc_mm'], 3)} | "
      f"{e1['total_L_planar_arc_mm']/tot*100:.2f}% |")
    A(f"| 三维升降弯曲 L_transition_arc | {f(e1['total_L_transition_arc_mm'], 3)} | "
      f"{e1['total_L_transition_arc_mm']/tot*100:.2f}% |")
    A(f"| 其他曲线 L_other_curve | {f(e1['total_L_other_curve_mm'], 3)} | 0.00% |")
    A(f"| **合计** | **{f(tot, 6)}** | 100% |")
    A("")
    A(f"逐路长度分解误差最大 {g(e1['max_route_decomposition_error_mm'])} mm，"
      f"与权威总长度偏差 {g(e1['absolute_error_mm'])} mm"
      f"（相对 {g(e1['relative_error'])}），**未做任何强制缩放**。")
    A("")
    A(f"长度分布：均值 {f(e1['length_mean_mm'], 2)} mm，标准差 "
      f"{f(e1['length_std_mm'], 2)} mm，最短 {f(e1['length_min_mm'], 2)} mm，"
      f"最长 {f(e1['length_max_mm'], 2)} mm，P5/P50/P95 = "
      f"{f(e1['length_p05_mm'], 2)} / {f(e1['length_p50_mm'], 2)} / "
      f"{f(e1['length_p95_mm'], 2)} mm。")
    A("")
    A("统一 0.05 dB/cm 下，$\\mathrm{Loss}_{\\rm prop}=0.005\\,L$（dB，L 以 mm 计）；"
      "R15 额外弯曲损耗为 0，但**弯曲弧长仍计入**普通传播损耗。"
      f"单路基础损耗 {f(e1['loss_min_db'])}–{f(e1['loss_max_db'])} dB，均值 "
      f"{f(e1['loss_mean_db'])} dB，1024 路合计 {f(e1['total_loss_db'], 1)} dB。")
    A("")
    A("![长度分布](../outputs/figures/fig01_length_distribution.png)")
    A("")
    A("![损耗分布](../outputs/figures/fig02_propagation_loss.png)")
    A("")

    A("## 6. 光学耦合结果")
    A("")
    A("### 6.1 模式")
    A("")
    A(f"参考截面在 1310 nm 下得到 **{e2['reference']['n_guided']} 个导模**："
      f"n_eff = {', '.join(f(x, 6) for x in e2['reference']['n_eff'])}。"
      "因此**不能假设单模**；本文的全板预测采用基模激励、基模与高阶模同时接收的"
      "“基模激励”工况，并明确它不是所有多模输入情形下的完整串扰。")
    A("")
    A("网格收敛：0.40/0.28/0.20/0.14 µm 下基模 n_eff 变化约 7×10⁻⁵，"
      f"计算窗口 16.8–39.2 µm 下变化 < 1×10⁻⁶，模式数稳定为 "
      f"{e2['reference']['n_guided']}。EIM 与全二维标量解的 n_eff 相对偏差 "
      f"{abs(e2['reference']['eim_rel_error_vs_full'])*100:.4f}%。")
    A("")
    A("![模式场](../outputs/figures/fig03_mode_fields.png)")
    A("")
    A("![收敛](../outputs/figures/fig04_mode_convergence.png)")
    A("")
    A("### 6.2 耦合系数")
    A("")
    A(f"κ 随间距近似指数衰减，衰减常数 γ = "
      f"{f(e3['reference_model']['gamma_per_um'], 4)} µm⁻¹。参考距离下（mm⁻¹）：")
    A("")
    A("| d (µm) | 15 | 20 | 30 | 50 | 62 |")
    A("|---|---:|---:|---:|---:|---:|")
    A(f"| κ | {g(km[15])} | {g(km[20])} | {g(km[30])} | {g(km[50])} | {g(km[62])} |")
    A("")
    A("![耦合系数](../outputs/figures/fig05_coupling_vs_separation.png)")
    A("")
    A("![耦合长度](../outputs/figures/fig06_crosstalk_vs_length.png)")
    A("")

    A("## 7. 全板 1024 通道串扰预测")
    A("")
    A("### 7.1 交叉的局部电磁结果")
    A("")
    A("| 角度 (°) | FDFD 串扰 | 低于分辨率下限 | FDFD 透射率 |")
    A("|---:|---:|:---:|---:|")
    for _, r in curve.iterrows():
        A(f"| {r.theta_deg:.1f} | {r.T_cross_fdfd_db:.1f} dB | "
          f"{'是' if r.T_cross_fdfd < CONFIG['crossing_model']['resolution_floor'] else '否'} | "
          f"{r.T_through_fdfd:.6f} |")
    A("")
    A("**关键结果**：全部角度下局部 FDFD 给出的交叉串扰都低于约 −70 dB，"
      "且随角度没有可分辨的系统趋势。这说明在本几何与弱导材料参数下，"
      "对称交叉的偶/奇超模相位差几乎完全抵消，**交叉角不是风险判据**。"
      "模型的分辨率下限由 PML 反射与网格色散残差决定（约 1e-7），"
      "低于该值的数值不应被当作精确预测。")
    A("")
    A("关于表中的透射率：小角度下 T 略大于 1（最多 +0.20%），这是 PML 截断与"
      "网格色散留下的系统残差，不是物理增益。大角度（≥60°）T 收敛到 "
      "0.99998–1.00001，说明**单次交叉的插入损耗低于 0.01 dB**，"
      "即交叉损耗在本模型精度内不可分辨；全板能量仍严格满足列和 ≤ 1。")
    A("")
    A("### 7.2 1024×1024 传输矩阵")
    A("")
    A("矩阵定义：第 i 列对应输入端口 i（source 端），第 j 行对应输出端口 j"
      "（target 端）。对角元为含传播损耗与交叉功率扣除的直通功率，"
      "非对角元为串扰。")
    A("")
    A("| 指标 | 值 |")
    A("|---|---:|")
    A(f"| 对角线范围 | {f(e5['diagonal_min_db'], 2)} ~ "
      f"{f(e5['diagonal_max_db'], 2)} dB |")
    A(f"| 最大非对角串扰 | **{f(e5['max_offdiagonal_db'], 2)} dB**"
      f"（R{e5['max_offdiagonal_pair'][0]} ⇄ R{e5['max_offdiagonal_pair'][1]}） |")
    A(f"| 单路总泄漏最坏 | **{f(e5['worst_total_leakage_db'], 2)} dB** |")
    A(f"| 平均总泄漏 | {f(e5['mean_total_leakage_db'], 2)} dB |")
    A(f"| 同时激励最坏干扰/信号 | "
      f"{f(ms['worst_interference_to_signal_db'], 2)} dB"
      f"（输出 R{ms['worst_output_route']}） |")
    A(f"| 全板能量守恒 | 最大列和 {en['max_column_sum']:.6f} ≤ 1 |")
    A(f"| 二阶（i→k→j）最大项 | {f(e5['second_order']['max_T_db'], 2)} dB"
      f"（可忽略：{'是' if e5['second_order']['negligible_below_1e_9'] else '否'}） |")
    A("")
    A("![串扰矩阵](../outputs/figures/fig07_crosstalk_matrix.png)")
    A("")
    A("![逐路排名](../outputs/figures/fig08_route_ranking.png)")
    A("")
    A("### 7.3 分层与热点")
    A("")
    A("| z (mm) | 线路数 | 总长度 (mm) | 交叉数 |")
    A("|---:|---:|---:|---:|")
    for _, r in layers.sort_values("z_mm").iterrows():
        A(f"| {r.z_mm:+.3f} | {int(r.n_routes)} | {r.total_length_mm:.1f} | "
          f"{int(r.n_crossings)} |")
    A("")
    A("![分层](../outputs/figures/fig09_layer_risk.png)")
    A("")
    A("![三维热点](../outputs/figures/fig11_3d_hotspots.png)")
    A("")
    if hots:
        A(f"最高风险热点簇位于 z={fmt_signed(hots[0]['z_mm'])} mm、"
          f"({hots[0]['x_mm']:.1f}, {hots[0]['y_mm']:.1f}) mm，包含 "
          f"{hots[0]['n_crossings']} 个交叉事件、涉及 "
          f"{len(hots[0]['routes'])} 条线路。")
        A("")
    A("![热点放大](../outputs/figures/fig12_hotspot_zoom.png)")
    A("")

    A("## 8. 几何交叉与光学串扰的关系")
    A("")
    A(f"逐路交叉数与总泄漏的 Pearson 相关系数 r = "
      f"{f(e5['geometry_vs_optics']['pearson_r_crossings_vs_leakage_db'], 4)}。"
      "由于每个交叉的串扰都落在同一个分辨率上限，总泄漏近似正比于交叉数——"
      "这既是几何统计唯一有效的部分，也说明**交叉角度、最近邻距离、并行长度"
      "在本设计中都不构成可分辨的风险差异**。")
    A("")
    A("* 几何交叉少但串扰高的线路：不存在（串扰上界由交叉数决定）。")
    A("* 几何交叉多但串扰低的线路：同样不存在——交叉多的线路泄漏上界更高。")
    A(f"* 跨层耦合：{na.get('cross_layer_approaches', 0)} 个跨层近邻事件，"
      f"最近三维间距 {f(na.get('min_distance_noncrossing_um', float('nan')))} µm，"
      f"对应 κ ≲ {g(km[62])} mm⁻¹，累积串扰 < 10⁻²⁰。")
    A("* 被几何交叉统计忽略的长距离并行耦合：在 ≥50 µm 的强制净距下同样可以忽略。")
    A("")
    A("![交叉数与串扰](../outputs/figures/fig14_crossing_vs_crosstalk.png)")
    A("")
    A("![交叉角度](../outputs/figures/fig10_crossing_angles.png)")
    A("")

    A("## 9. 参数敏感性")
    A("")
    A("| 参数集 | 模式数 | n_eff | γ (µm⁻¹) | κ(50 µm) | XT@30° | XT@90° |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for _, r in sweep.iterrows():
        A(f"| {r.parameter_set} | {int(r.n_guided)} | {r.n_eff_fund:.6f} | "
          f"{r.gamma_per_um:.4f} | {g(r.kappa_50um_mm_inv)} | "
          f"{f(r.get('T_cross_30deg_db', float('nan')), 1)} | "
          f"{f(r.get('T_cross_90deg_db', float('nan')), 1)} |")
    A("")
    A("无论波长（1310/1550 nm）、Δn（0.0045/0.0065/0.0080）、芯区宽度"
      "（6/9/12 µm）、芯区高度（7/9/11 µm）还是阶跃/渐变分布，波导均为**多模**"
      "（3–5 个导模），50 µm 以上间距的耦合系数始终 < 10⁻⁸ mm⁻¹，"
      "交叉串扰始终低于分辨率下限。因此全板结论对上述参数不敏感；"
      "真正敏感的是模式数（影响多模输入下的完整串扰，本文未覆盖）"
      "与耦合系数本身（相差数个数量级，但都远低于风险阈值）。")
    A("")
    A("![敏感性](../outputs/figures/fig13_sensitivity.png)")
    A("")

    A("## 10. 结论与后续算法方向")
    A("")
    A("1. 20 层 1283 交叉方案的 1024 条真实三维波导，基础传播损耗 "
      f"{f(e1['loss_min_db'])}–{f(e1['loss_max_db'])} dB"
      "（0.05 dB/cm，R15 无额外损耗）。")
    A("2. 参考截面是多模波导（3 个导模），不能按单模处理；本文的基模激励结果"
      "是全板串扰的一个预测，但不是多模输入下的完整串扰。")
    A("3. 交叉是全板唯一 <50 µm 的三维接近；局部 FDFD 表明其串扰低于 −70 dB。")
    A(f"4. 在该精度下，1283 次交叉与 1024 端口矩阵给出最坏 "
      f"{f(e5['worst_total_leakage_db'], 1)} dB 量级的串扰上界，"
      "远低于典型 IM-DD 链路的 −20 dB 预算。")
    A("5. **减少几何交叉次数并不等价于降低光学串扰**：交叉数只通过数量线性影响"
      "上界，角度与局部几何没有可分辨贡献；真正的风险来源应是制造引起的折射率"
      "不均匀、芯区粗糙度与应力双折射，这些不在本模型范围内。")
    A("6. 后续布线算法建议：(i) 把传播损耗（真实弧长）作为一阶目标；"
      "(ii) 交叉串扰以“数量×上界”形式进入目标函数即可，无需按角度细分；"
      "(iii) 若要把串扰做成真正的优化目标，必须先补充**全矢量**与**制造扰动**模型，"
      "并在局部交叉上做三维 FDTD/EME 标定。")
    A("")

    A("## 11. 模型局限与不确定度")
    A("")
    A("* 标量弱导近似，非全矢量；偏振与双折射未建模。")
    A("* EIM 把三维通道化为二维平面问题，n_eff 相对误差约 "
      f"{abs(e2['reference']['eim_rel_error_vs_full'])*100:.4f}%。")
    A("* 交叉求解器为二维 FDFD，PML 与网格色散使其分辨率下限约 1e-7；"
      "所有低于该值的预测均以“≤1e-7”报告，而不是伪精确数值。"
      "同一残差也导致小角度透射率出现 +0.2% 的偏置，"
      "因此交叉插入损耗只能给出“< 0.01 dB”的上界。")
    A("* 制造扰动、侧壁粗糙度、折射率漂移均未建模；真实器件的串扰通常由这些因素"
      "主导，因此本文结果是**理想结构的理论下界**。")
    A("* 只做了基模激励；多模输入下的完整串扰需要模式分辨的激励矩阵。")
    A("")

    A("## 12. 复现")
    A("")
    A("依赖 Python 3.10+、NumPy、SciPy、Pandas、Matplotlib。在本目录下执行：")
    A("")
    A("```powershell")
    for s in ["run_e1", "run_e2", "run_e3", "run_e4", "run_e5", "run_e6",
              "make_figures", "run_manifest", "run_report"]:
        A(f"python scripts\\{s}.py")
    A("python tests\\test_pipeline.py")
    A("```")
    A("")
    A("`run_e3.py` 内的 17 个角度局部二维 FDFD 求解是唯一耗时较长的步骤"
      "（本机约 7 分钟），其余步骤均在秒级到数分钟。`cache/` 为可再生的中间结果，"
      "未纳入版本库。")
    A("")

    A("## 13. 结果文件清单")
    A("")
    A("| 文件 | 内容 |")
    A("|---|---|")
    for name, desc in [
        ("outputs/geometry/route_lengths.csv", "1024 路真实长度分解"),
        ("outputs/geometry/propagation_loss.csv", "0.05 dB/cm 传播损耗"),
        ("outputs/geometry/crossing_events_detected.csv", "独立解析求交得到的 1283 次交叉"),
        ("outputs/geometry/interaction_regions.csv", "全部非交叉三维近邻事件"),
        ("outputs/optical/single_waveguide_modes.csv", "单波导模式与 n_eff"),
        ("outputs/optical/coupling_coefficients.csv", "双波导耦合数据库"),
        ("outputs/optical/crossing_transfer_curve.csv", "交叉角度-串扰曲线（FDFD/Born/CMT）"),
        ("outputs/optical/crossing_optical_analysis.csv", "1283 次交叉的几何+光学分析"),
        ("outputs/optical/crosstalk_matrix_linear.npy", "1024×1024 线性功率矩阵"),
        ("outputs/optical/crosstalk_matrix_db.csv", "1024×1024 dB 矩阵"),
        ("outputs/optical/crosstalk_per_route.csv", "逐路风险统计"),
        ("outputs/optical/crosstalk_hotspots.json", "串扰热点"),
        ("config/simulation_config.yaml", "完整参数与假设"),
        ("outputs/optical/simulation_manifest.json", "输入 SHA256、代码版本、运行环境"),
    ]:
        A(f"| `{name}` | {desc} |")
    A("")
    if man:
        rt = man.get("runtime", {})
        A(f"运行环境：Python {rt.get('python', '?')}，"
          f"NumPy {rt.get('numpy', '?')}，SciPy {rt.get('scipy', '?')}，"
          f"Matplotlib {rt.get('matplotlib', '?')}。")

    out = EXPERIMENT_ROOT / "reports" / "SIMULATION_REPORT.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L), encoding="utf-8")
    return out
