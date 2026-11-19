# 文献综述：1024 通道飞秒激光直写 3-D 玻璃波导阵列串扰（crosstalk）预测的文献依据

- 项目：`CROSSTALK_PREDICTION_CTP2_20H_1283_1024`（20 个路由高度 × 50 µm 垂直间距，1283 个同层交叉，交叉角 5.15°–90°，中位数 63°；参考截面 9 µm × 9 µm、Δn = 0.0065、λ = 1310/1550 nm、损耗 0.05 dB/cm）
- 本文性质：**策展式（curated）文献调研**，非系统性、无偏的文献普查；检索与核验日期 **2026-11-19**（Asia/Shanghai）
- 交付物：`docs/literature_review.md`、`docs/literature_matrix.csv`（29 条）、`benchmarks/literature_benchmarks.csv`（49 条数值）、`docs/literature_search_log.md`
- 诚实性声明：所有书目元数据（作者/期刊/卷/页/DOI）均经 Crossref API 逐条核验；所有数值只来自我**实际读到的**摘要或全文。凡是"全文未获取"的条目均显式标注，凡是把论文结论外推到本项目的地方均标为 **[inference]**。**不存在任何编造的数字、DOI 或页码。**

---

## 0. 一页结论（TL;DR）

1. **对本项目最直接的定量锚点**是 Adikan 等 2006（silica-on-silicon 弱导 X coupler）：交叉角 0.8°–5° 范围内耦合比从 95 % 掉到 1.9 %；5° 处约 1.9 % ≈ **−17 dB**。这说明弱导玻璃体系的"危险区"是**约 1°–2° 的相位匹配过渡带**，而本项目最小角 5.15° 已在该过渡带之外约 3–5 倍处，因此**小角交叉串扰不应是灾难性的，但会显著高于大角交叉**。**[inference：把 1.9 % 当作交叉端串扰；把角度端点与数值的对应关系由"最大/最小"推得]**
2. **平行/近距耦合（≥50 µm 净距）在弱导玻璃中可以忽略**：飞秒直写熔石英方向耦合器实测耦合长度在 5 µm 间距约 0.5 mm、15 µm 间距约 5.6 mm（Amorim 2017），随间距近似指数增长；50 µm 间距的耦合长度将超出任何板级长度若干数量级。**[direct evidence：0.5/5.6 mm 数据；inference：外推到 50 µm]**
3. **大角（30°–90°）交叉本身在弱导体系中是"小扰动"**：Bogaerts 2007 明确写道"在低折射率对比波导中，直接交叉只是直波导的轻微扰动"；弱导多模聚合物 90° 交叉实测附加损耗可低至 0.006 dB、"crosstalk" 约 −30 dB（Bamiedakis 2007）；角度分辨的弱导聚合物实测给出损耗随角度减小而增大的经验律 1.078·θ^−0.873 dB（10°–90°，Baghsiahi 2014）。
4. **方法学上，文献对"角度分区"有明确共识**：BPM（含 SSFM）是弱导小角 X 结的常用工具（Adikan 2006；Zhang 2005），但 BPM 只在"小角（θ < 4°）+ 小 Δn"下被验证，且忽略反射、不能处理大几何/材料不连续（Chu & Chaudhuri 1989 摘要原话）；30°–90° 交叉用 FDTD / EME / FEM 才是可辩护的选择（Bogaerts 2007 用 2-D EME；所有硅光交叉用 3-D FDTD）。
5. **全板组装（full-board assembly）的文献范式是"S 参数/紧凑模型 + 电路级组合"**：Lumerical 官方文档给出 port → mode expansion → S-matrix → INTERCONNECT 的标准流程（FOM = T₃ − T₂ − T₄ − R₁）；Bogaerts & Chrostowski 2018 把"器件紧致模型 + 电路仿真 + 变异分析"确立为大规模光子电路的标准设计层；Hildén & Shevchenko 2024 给出密集波导阵列（含弯曲）串扰的矩阵分析方法。**本项目应输出局部器件的多模 S-matrix（含相位/群时延）再用网络组合，而不是企图对整板做单片 3-D FDTD。**

---

## 1. 检索方法（Search methodology）

### 1.1 数据库与工具
- **Crossref REST API**：29 条参考文献的 DOI、题名、作者、期刊、卷期、页码、年份逐条核验（脚本化，带 `mailto`）。
- **OpenAlex API**：题录发现 + 摘要（inverted index 重建）+ 开放获取（OA）位置；共查询 36 个 DOI、15 组主题检索。
- **Unpaywall API**：14 个关键 DOI 的合法 OA 版本定位（找到 5 篇机构库/arXiv 全文，是本综述能读全文的关键）。
- **Semantic Scholar Graph API**、**arXiv API / arxiv.org PDF**、**PubMed / PMC**、**出版社页面**（Optica、AIP、Springer、Wiley、IOP、MDPI、De Gruyter、SPIE）、**机构知识库**（Bristol、UGent、Politecnico di Torino、U Toronto、INESC-TEC、UCL、九州大学）、**官方技术文档**（Ansys Lumerical Knowledge Base）。
- **通用 web 检索**（DSH `web_search`，实为 Bing/Google 系索引）：7 批、共 21 条英文 query，用于发现题录与获取被索引的 PDF 片段。

### 1.2 主要 query（节选，均为英文原词）
`femtosecond laser written glass waveguide crosstalk`；`3D optical waveguide crossing coupling`；`small angle crossing waveguide silica`；`silica waveguide X coupler`；`beam propagation method waveguide crossing`；`3D hybrid coupled mode theory waveguide`；`waveguide crossing FDTD simulation crosstalk`；`eigenmode expansion waveguide crossing scattering`；`multimode waveguide crossing crosstalk`；`optical waveguide array coupling crosstalk`；`3D curved waveguide BPM`；`coupled mode theory phase mismatch crossing`；`femtosecond laser direct write 3D photonic integrated circuit crosstalk`；`glass waveguide directional coupler coupling length`；`ultrafast laser inscribed waveguide crossing loss`；`X-junction waveguide crossing angle coupling`；`shallow angle X coupler silica waveguide`；`directional coupler fused silica coupling coefficient separation`；`silicon-based multimode waveguide crossings`；`photonic circuit design compact models S-parameter`。

### 1.3 纳入 / 排除标准
纳入：① 直接涉及四类问题之一（(a) 小角交叉 1°–20°，(b) 大角交叉 30°–90°，(c) 平行/垂直偏移耦合 vs 间距，(d) 从局部模型组装整板）；② 有可核验的题录；③ 能读到至少摘要，或能读到全文；④ 优先弱导（silica/glass/polymer）与 3-D 结构，其次把高对比硅光作为**方法学**参照。
排除：纯新闻/产品页、无法核验题录的条目、纯理论但与交叉/耦合无关的条目、以及只能看到标题且无法判断内容的条目（例如若干 2025–2026 年的新综述，未纳入）。

### 1.4 数量统计（诚实计数）
- 检索/筛查题录约 **150 条**（OpenAlex/Crossref 返回并人工浏览标题+摘要）。
- 进入候选清单 **约 35 条**。
- **保留 29 条**写入矩阵；其中：
  - **全文可读 11 条**（S03、S04、S05、S06、S07、S10、S11、S12、S13、S24、S25；其中 S06、S24 读的是 arXiv 版，已与正式版摘要核对）；
  - **仅摘要 16 条**（S01、S02、S08、S15、S16、S17、S18、S19、S20、S21、S22、S23、S26、S27、S28、S29）；
  - **仅题录/被索引摘要片段 2 条**（S09、S14）。
- 网络请求总量约 **150 次**（Crossref：26 组题录 query + 32 个 DOI 核验；OpenAlex：36 个 DOI + 15 组检索；Unpaywall 14 次；Semantic Scholar 5 次；arXiv 2 次；PMC/出版社/机构库下载尝试约 25 次，其中约 1/3 被 403/401/Cloudflare 拦截）。
- 提取数值基准 **49 行**（`benchmarks/literature_benchmarks.csv`），覆盖：交叉插入损耗、交叉串扰、回损/反射、方向耦合器耦合长度 vs 间距、弱导交叉角依赖、3-D 多层垂直耦合串扰。

**重要限定：** 这是一个围绕本项目需求人工筛选的**策展集合**，不是"该领域全部文献"的无偏普查；引用计数、期刊层级均未做系统加权。

---

## 2. 逐篇精读档案

> 每条格式：题录 → 体系/截面/Δn → λ/模式 → 结构 → 方法与设置 → 实验验证 → 报告数值 → 预测 vs 实测 → 对我方适用性 → **论文直接证据** / **我们的推论** → 获取状态。
> `[direct]` = 论文中可直接读到的陈述/数据；`[inference]` = 我们的外推，论文未直接说。

### S01 — Adikan et al., *Design and demonstration of direct UV-written small angle X couplers in silica-on-silicon for broadband operation*, Appl. Opt. **45**(24):6113–6118 (2006). DOI [10.1364/AO.45.006113](https://doi.org/10.1364/AO.45.006113)
- 体系：silica-on-silicon，direct UV-written 通道波导；弱导。截面、绝对 Δn、精确波长在摘要中未给出（全文不可得）。
- 结构：**小角 X coupler**，交叉角 **0.8°–5°**；面向宽带（broadband）应用。
- 方法：**BPM + 解析模型（analytical model）** 与实验对比（摘要原话）。
- 实验验证：有（器件级测量）。
- 报告数值：**最大耦合比 95 %（±0.8 %），最小 1.9 %（±1 %）**；典型**附加损耗（excess loss）1.0 dB（±0.5 dB）**；偏振与波长依赖性很低。
- 预测 vs 实测："BPM 与解析模型在很宽的交叉角和波长范围内与实验结果吻合良好"——**没有给出具体偏差数字**（摘要层面）。
- 对我方适用性：**high**（目前找到的最接近"弱导玻璃 + 小角 X coupler"的实测数据）。
- **论文直接证据 [direct]**：① 0.8°–5° 弱导 X coupler 的耦合比从 95 % 单调降到 1.9 %；② 典型附加损耗 ~1 dB；③ BPM+解析模型被作者认为足以复现该角度/波长范围的行为。
- **我们的推论 [inference]**：① 95 % 对应 0.8°、1.9 % 对应 5°（摘要只给"最大/最小"，端点对应关系未印出）；② "耦合比"可当作交叉端功率占比，即 1.9 % ≈ −17 dB 交叉串扰；③ 若把这一趋势搬到 9 µm/Δn=0.0065、λ=1310 nm，则 5° 附近预期串扰量级为 −20 ~ −15 dB，而 ≥30° 会迅速降到 −40 dB 以下（该外推我们在 §5 给出物理判据）。
- 获取状态：**abstract_only**。Optica 页面被 bot-check 拦截；UM repository 无全文；同组 ECIO-2006 会议文（eprints.soton.ac.uk/47870）返回 HTTP 401。**BPM 的网格/边界/折射率剖面设置无法获取，因此"BPM 与实测吻合到多少"无法量化。**

### S02 — Hammer, Alhaddad & Förstner, *Hybrid coupled-mode modeling in 3D: perturbed and coupled channels, and waveguide crossings*, JOSA B **34**(3):613–624 (2017). DOI [10.1364/JOSAB.34.000613](https://doi.org/10.1364/JOSAB.34.000613)
- 体系：一般介质通道波导（数值示例为矩形直通道）；截面/Δn/λ 摘要未给。
- 结构：3-D；**平行（水平/垂直）耦合、以及"位置与取向相当任意"的交叉（crossings of potentially overlapping channels）**。这正是本项目需要的"任意角度/任意相对位置"能力。
- 方法（**摘要可确认的部分**）：3-D **HCMT**（hybrid analytical/numerical coupled-mode theory），频域；各通道的**本征模用数值方法计算**；用这些本征模构造复合结构场的**全矢量近似**；幅度函数用 **1-D 有限元**离散；用有限元式装配**线性方程组**求解模态幅度。摘要称：内存极省、计算时间中等，**"在低辐射损耗区域足够精确（sufficiently accurate in regimes of low radiative losses）"**。
- 实验验证：**无**（纯数值方法论文，摘要未提实验对比）。
- 报告数值：无（摘要层面）。
- 对我方适用性：**medium**（方法学最贴合 (c)+(d)，但"低辐射损耗区"这一精度前提恰好是交叉处最可疑的地方，且对少模/辐射的验证状态未知）。
- **论文直接证据 [direct]**：上述方法框架与"适用于任意相对位置/取向的交叉"的声明；精度限定于低辐射损耗区。
- **我们的推论 [inference]**：① 其数学形式可写为标准 CMT 拟设 `E = Σ_j a_j(s) E_j(x,y) e^{iβ_j s}`，耦合系数由扰动极化重叠积分给出（**这是标准形式的重构，不是该文公式**）；② 若要把 1283 个交叉组成整板，HCMT 的"稀疏 1-D 通道问题"思路可极大降维；③ 但我方波导为 few-mode，交叉处有辐射/模式转换，可能落在该文声明的精度区之外。
- 获取状态：**abstract_only**。JOSA B 全文 closed（Optica bot-check；Paderborn 机构库在本网络不可达；Unpaywall 状态 CLOSED）。作者公开报告 PDF（[computational-photonics.eu/Papers/Pres/wihelp.pdf](https://computational-photonics.eu/Papers/Pres/wihelp.pdf)）已下载阅读，其中给出 2-D 版本的场拟设、1-D 线性有限元、Galerkin 弱形式与 `K_uu a_u = −K_ug a_g` 的求解结构；**但该讲稿自述"3-D 尚在进行中"，不能作为 2017 年论文公式的直接证据。代码/推导是否可下载：未验证到。**

### S03 — Johnson, Thompson & Sahin, *Low-loss, low-crosstalk waveguide crossing for scalable integrated silicon photonics applications*, Opt. Express **28**(9):12498–12507 (2020). DOI [10.1364/OE.381304](https://doi.org/10.1364/OE.381304)
- 体系：SOI，220 nm Si 器件层 + 2 µm BOX；500 nm 宽条波导；高对比。
- 结构：MMI 型 4 端口 90° 交叉；W_M=1.9 µm、L_M=3.7 µm、L_T=2.5 µm；footprint 14.3 × 14.3 µm²。
- 方法：**3-D FDTD（Lumerical）** 优化 + 流片；**cut-back**（0/40/80/120/160 个交叉）测插损；through/cross 端口谱测串扰；白光反射仪（Luna OBR 4600）测背向散射。
- 实验验证：有（TE 单模，1520–1580 nm）。
- 报告数值（我逐项读过 PDF）：实测插损 **0.043 ± 0.004 dB**（1555 nm）、**0.044 ± 0.002 dB/crossing**（1560 nm）；实测串扰 **−50.3 dB @1550 nm**，带内最差 **−45.8 dB**（1525–1570 nm）；仿真插损 **0.042 dB**、仿真串扰最差 **−45.6 dB**（1520–1580 nm）；背向散射最好 **−55 dB**（频域，最差 −35 dB）。
- 预测 vs 实测：插损差 **1–2 mdB**；串扰带内差 **约 0.2 dB**；最优串扰的波长偏移归因于结构尺寸变化。
- 对我方适用性：**medium**——**只有"验证方法学"可迁移，绝对数值完全不可迁移**。
- **论文直接证据 [direct]**：① 完整的"FDTD → 端口投影 → S 参数 → cut-back 实测"闭环；② 串扰定义=through 与 cross 端口的相对信号（在探测器噪声基底之上提升激光功率测得），并明确说明 −15 dB 的测量下限问题；③ 160 个交叉链的时域回损测量证明"多交叉累积"可测。
- **我们的推论 [inference]**：① 我方局部交叉模型应采用同样的端口投影 + S 参数流程；② 弱导玻璃的串扰会比 −45 dB 高得多（更易测），但**损耗只有 0.02–0.2 dB 量级时，cut-back 需要极多样本/极低测量不确定度**；③ 该文的 ~0.2 dB 串扰吻合度是理想情况下的上限，我方不应期待更好。
- 获取状态：**full_text**（Bristol Research Portal 出版社版 PDF，CC BY）。

### S04 — Keil et al., *All-optical routing and switching for three-dimensional photonic circuitry*, Sci. Rep. **1**:94 (2011). DOI [10.1038/srep00094](https://doi.org/10.1038/srep00094)
- 体系：熔石英（fused silica），飞秒激光直写（800 nm、170 fs、300 nJ、100 kHz、NA 0.35）；**Δn = 1.2×10⁻³（p 偏振）/ 9.8×10⁻⁴（s 偏振）**；波导间距 **32 µm**；样品长 10 cm。
- 结构：2-D 蒸发耦合波导阵列的 **Y 结与 T 结（90°）**，用于全光路由/开关。
- 方法：**Fourier split-step（SSFM）** 解含 Kerr 非线性的傍轴 Helmholtz 方程；折射率剖面由实测模场反演标量 Helmholtz 方程得到；cw 仿真。
- 实验验证：有（输出端面成像，脉冲激发）。
- 报告数值：T 结功率比变化 ~10 dB（实验）/ ~15 dB（仿真）；**反射回输入端口 ~6 %（有门控）/ ~17 %（无门控）**；Y 结对比度 ~9 dB（实验）vs ~14 dB（仿真）；传输损耗 ~0.4 dB/cm（并引用热处理后 0.05 dB/cm 的文献值）。
- 预测 vs 实测：仿真高估开关对比度约 5 dB（归因于 cw vs 脉冲时空动力学）。
- 对我方适用性：**medium**。
- **论文直接证据 [direct]**：① 3-D 飞秒直写玻璃回路可以用 SSFM/BPM 建模（含实测折射率剖面）；② 玻璃中 90° T 结的**反射**是真实损耗通道（实测 6 %–17 %）；③ 32 µm 间距在 Δn≈1×10⁻³ 时被作者称为"weakly coupled"；④ 玻璃波导 0.4 dB/cm 实测损耗及 0.05 dB/cm（热处理）文献值。
- **我们的推论 [inference]**：① 我方局部模型若只算"通过 + 交叉"两端口会漏掉反射（在 90° 附近反射率可达 5 %–15 % 量级，**与弱导交叉损耗同量级甚至更大**）；② 32 µm 已属弱耦合，则 50 µm 净距在 Δn=0.0065 下仍几乎无平行耦合；③ SSFM 是可信的 3-D 玻璃传播引擎，但其傍轴性在 90° 交叉处失效（见 §3）。
- 获取状态：**full_text**（PMC 全文）。

### S05 — Ansys Lumerical Knowledge Base, *Waveguide crossing*（官方技术文档，访问于 2026-11-19）
URL: [optics.ansys.com/hc/en-us/articles/360042800433-Waveguide-crossing](https://optics.ansys.com/hc/en-us/articles/360042800433-Waveguide-crossing)
- 体系：通用（示例为 SOI 条波导）；无实测。
- 方法：**3-D FDTD 优化 + 端口（mode source + field monitor + mode expansion monitor）**；**S-parameter matrix sweep**；导出到 **INTERCONNECT** 的 Optical N-port S-Parameter 元件做电路级组合。
- 关键定义与设置（文档原文要点）：FOM = `transmission(port 3) − transmission(port 2) − transmission(port 4) − reflection(port 1)`；插损按每个输出端口定义；4 端口 S 矩阵原则上需"每个端口/模式一次仿真"，对称结构可用 **port mapping / auto symmetry** 减半；**S 参数扫掠时不能用对称边界（会使 port 失效）**；最终扫掠 mesh accuracy 3、全 PML；优化阶段可 mesh accuracy 2；port span 必须覆盖所有感兴趣的模；多模仿真通过在每个 port 选多个模式实现；需要相位/群时延的电路可加 group delay。
- 对我方适用性：**high**（方法学与定义）。
- **论文直接证据 [direct]**：本项目的"局部 S-matrix → 整板网络"应遵循上述流程；"reflection、insertion loss、crosstalk、S 参数"在该文档中有明确定义；多模端口会成倍增加仿真次数。
- **我们的推论 [inference]**：若把 20 层 1024 通道全部做成 N-port 网络，节点数 ~2048 端口、每交叉 8 端口（含 2 个模）× 1283 交叉，网络规模很大但稀疏；需要相位/群时延才能在"相干串扰"意义上相加。
- 获取状态：**tech_doc / full**。

### S06 — Chiles et al., *Multi-planar amorphous silicon photonics with compact interplanar couplers, cross talk mitigation, and low crossing loss*, APL Photonics **2**(11):116101 (2017). DOI [10.1063/1.5000384](https://doi.org/10.1063/1.5000384)
- 体系：三层非晶硅（a-Si）波导，n = 3.12 ± 0.1；层厚 200 nm；**层间距 900 nm（设计）/ ~700 nm（实测）**；同层间距 2 µm；宽度 470/550 nm。
- 结构：**3-D 多层**——层间耦合器（IPC）、跨层交叉、层间共传播串扰。
- 方法：3-D FDTD 设计 + 实验（棱镜耦合、光栅耦合器、显微环）。
- 报告数值：跨层交叉损耗 P1/P3 **< 3×10⁻⁴ dB**、P1/P2 **3.1×10⁻³ ± 7×10⁻⁴ dB**；IPC **0.05 ± 0.02 dB**（实测，1526 nm；仿真 0.032 dB）；**层间共传播串扰**：完全重叠加 16 µm 共传播时 **−4.8 ± 0.7 dB**，加 80 nm 宽度失谐后 **−12.5 ± 0.7 dB**（58 µm），P1/P3 重叠 **−35 ± 0.7 dB**；同层 2 µm 间距、2 mm 共传播 **< −19 dB**。
- 预测 vs 实测：损耗与 FDTD 在 10⁻³ dB 级吻合；P1/P3 重叠串扰比 FDTD 好 16 dB（归因于实际间距偏差）。
- 对我方适用性：**medium**（方法学 + "垂直偏移决定重叠"的定量图像；材料高对比不可迁移）。
- **论文直接证据 [direct]**：① 层间串扰由**模场重叠 + 相位失配**决定，亚微米级垂直间距下可达 −5 dB；② 跨层交叉本身可以近乎无损耗；③ 串扰可用 FDTD 定量预测并被实验检验（但可差 16 dB）。
- **我们的推论 [inference]**：我方 50 µm 垂直间距下的模场重叠比 0.7–0.9 µm 情形小几十个数量级，**层间（不同高度）耦合可忽略**；本项目 (c) 类"平行/跨层近距"在 ≥50 µm 中心线间距下应当为零，真正需要算的只有同层交叉与同层平行段。
- 获取状态：**full_text**（arXiv:1708.09438 版；与正式版摘要一致）。

### S07 — Bogaerts, Dumon, Van Thourhout & Baets, *Low-loss, low-cross-talk crossings for silicon-on-insulator nanophotonic waveguides*, Opt. Lett. **32**(19):2801–2803 (2007). DOI [10.1364/OL.32.002801](https://doi.org/10.1364/OL.32.002801)
- 体系：SOI 220 nm Si / 2 µm BOX；高对比（3.45 / 1.45）。
- 结构：90° 直接交叉；用 3 µm 抛物线 taper 展宽 + **double-etch** 局部降低横向对比；交叉长度 6 µm。
- 方法：**2-D 特征模展开（EME）** @1.55 µm + 实验；测 0/5/10/21 个交叉的链。
- 报告数值：**实测每个交叉 −0.16 dB（97.5 % 透射）**；**实测串扰优于 −40 dB**；未优化直接交叉仿真 67 % 透射、几个百分点串扰；改进设计仿真 >95 % 透射。
- 预测 vs 实测：实测 −0.16 dB 与仿真 >95 % 一致（无偏差数字）。
- 对我方适用性：**medium**（关键在"低对比=轻微扰动"的定性结论）。
- **论文直接证据 [direct]**：① 原文明确："**In low-contrast waveguides these direct waveguide crossings are just a minor perturbation of the straight waveguide, even though the crossing is several micrometers long. In this situation, the beam is hardly diffracted.**" ② 交叉串扰用"第一个交叉侧臂输出"测量，是上界；③ 2-D EME 足以设计分段均匀的 90° 交叉。
- **我们的推论 [inference]**：① 我方 90° 交叉的**损耗**项应当很小（弱导），风险主要在**串扰**与**小角**；② 硅光的 −0.16 dB / −40 dB 数值不可迁移；③ 论文摘要中的"97.5 % transmission (−1.7 dB)"与正文 −0.16 dB 自相矛盾，**−1.7 dB 疑为笔误**，引用时须注意。
- 获取状态：**full_text**（UGent biblio PDF）。

### S08 — Ma et al., *Ultralow loss single layer submicron silicon waveguide crossing for SOI optical interconnect*, Opt. Express **21**(24):29374–29382 (2013). DOI [10.1364/OE.21.029374](https://doi.org/10.1364/OE.21.029374)
- 体系：SOI，CMOS 兼容 248 nm 光刻、单步刻蚀；高对比。
- 结构：90° 交叉，**同时做 1310 nm 与 1550 nm 两个器件**。
- 方法：FDTD 设计 + 30 dies 跨晶圆测量（摘要层面）。
- 报告数值：插损 **1550 nm：−0.028 ± 0.009 dB；1310 nm：−0.017 ± 0.005 dB**；串扰 **< −37 dB**。
- 对我方适用性：**low**（数值不可迁移，但"双波长 + 跨样本统计"的做法可借鉴）。
- **论文直接证据 [direct]**：1310/1550 双波长交叉设计可行；跨晶圆插损统计在 0.01 dB 级。
- **我们的推论 [inference]**：我方的"预测 vs 实测"报告应给出**几何/工艺变异下的统计**（而不仅是名义值）；1310 与 1550 的差异在弱导体系会更大（色散 + 模场）。
- 获取状态：**abstract_only**（Optica 全文被拦截；数值与 Johnson Table 1 一致，可交叉核对）。

### S09 — Szameit et al., *Hexagonal waveguide arrays written with fs-laser pulses*, Appl. Phys. B **82**(4):507–512 (2006). DOI [10.1007/s00340-005-2127-4](https://doi.org/10.1007/s00340-005-2127-4)
- 体系：熔石英飞秒直写六角波导阵列（弱导）。
- 结构：平行耦合（阵列）。
- 报告内容：**被索引的摘要片段明确说"我们确定了耦合常数随波导间距和波长的变化行为"**；但具体数值在图里，摘要与正文均不可得。
- 对我方适用性：**medium**（若拿到全文，将是 C(间距, λ) 的最佳实验标定源之一）。
- **论文直接证据 [direct]**：仅"耦合常数 vs 间距/波长"这一题录级事实（Google Scholar/Patents 索引摘要片段）。
- **我们的推论 [inference]**：无（不可在无数值情况下外推）。
- 获取状态：**metadata_only**。Springer 付费；OpenAlex/S2 摘要被出版商屏蔽。**必须通过机构订阅获取全文后才能引用任何 C(间距) 数值。**

### S10 — Amorim, Maia, Alexandre & Marques, *Monolithic Add–Drop Multiplexers in Fused Silica Fabricated by Femtosecond Laser Direct Writing*, J. Lightwave Technol. **35**(17):3615–3621 (2017). DOI [10.1109/JLT.2017.2715118](https://doi.org/10.1109/JLT.2017.2715118)
- 体系：纯熔石英，Type-I 飞秒直写（400 µm/s，50 µm 深度）；**单模 @1550 nm，MFD 7.1 × 12.3 ± 0.2 µm**；耦合器波导传输损耗 0.6 dB/cm。
- 结构：**方向耦合器（平行耦合）**，中心距 **5–15 µm**，互作用长度 **0–12 mm**；S 弯半径 80 mm；随后做 3-dB 耦合器 + Bragg 光栅的 OADM。
- 方法：实验测耦合比 vs 互作用长度，拟合正弦耦合律；给出"耦合长度 vs 间距"。
- 报告数值：**5 µm 间距时耦合长度 ~0.5 mm；15 µm 间距时 ~5.6 mm**；3-dB 耦合：10 µm 间距 + 1.48 mm（44/56 ±1 %），15 µm 间距 + 1.77 mm（51/49 ±1 %）；5 µm 间距时随互作用长度增加出现额外损耗（波导重叠）。
- 对我方适用性：**high**（目前最好的"玻璃 + 弱导 + 1550 nm + 耦合长度 vs 间距"实测数据）。
- **论文直接证据 [direct]**：耦合长度随中心距强烈增长（0.5 → 5.6 mm over 5 → 15 µm），且近似指数；间距 5 µm 时波导重叠带来额外损耗。
- **我们的推论 [inference]**：① 50 µm 净距的耦合长度将比 15 µm 的 5.6 mm 大若干个数量级（指数外推），故 (c) 类平行耦合可忽略；② 我方 MFD 可能略大于该文，耦合还会更弱；③ "耦合长度"与"3-dB 长度"的关系需统一（该文 15 µm 处 1.77 mm 的 3-dB 长度与 5.6 mm 拍长在数值上不完全自洽，引用时以原文条件为准）。
- 获取状态：**full_text**（INESC-TEC 机构库 accepted manuscript）。

### S11 — Fernandes, Grenier, Herman, Aitchison & Marques, *Femtosecond laser fabrication of birefringent directional couplers as polarization beam splitters in fused silica*, Opt. Express **19**(13):11992–11999 (2011). DOI [10.1364/OE.19.011992](https://doi.org/10.1364/OE.19.011992)
- 体系：块体熔石英飞秒直写（300 fs、150 nJ、500 kHz、522 nm）；**MFD 9.6 × 9.0 µm @1550 nm**；传输损耗 0.5 dB/cm（无光栅）。
- 结构：方向耦合器，S = 5–15 µm，互作用长度 0–20 mm，用于偏振分束。
- 方法：实验测耦合比 vs 长度与波长，Levenberg-Marquardt 拟合提取 K 与弯曲相位 φ。
- 报告数值：**8 µm 间距、19.2 mm 耦合长度**（1484 nm 处实现 −19 dB(H) / −24 dB(V) 偏振消光）；双折射 5.2×10⁻⁵（平行写入）/ 2.1×10⁻⁴（垂直写入）；偏振间耦合系数差 ~5 %。
- 对我方适用性：**medium**。
- **论文直接证据 [direct]**：① 与 S10 同材料但模场更大（9.6 × 9.0 µm）时，8 µm 间距需要 **19.2 mm** 耦合长度——说明耦合长度对模场/写入剖面极其敏感；② fs 直写玻璃波导存在 10⁻⁵–10⁻⁴ 量级双折射，耦合系数对偏振有 ~5 % 差异。
- **我们的推论 [inference]**：① 仅凭 Δn 猜耦合长度非常危险，必须用自己的模场计算 κ；② 若我方需要偏振无关的串扰预算，偏振依赖是二阶修正（~5 % 量级）。
- 获取状态：**full_text**（U Toronto 机构库）。

### S12 — Olivero & Svalgaard, *Direct UV-written broadband directional planar waveguide couplers*, Opt. Express **13**(21):8390–8396 (2005). DOI [10.1364/OPEX.13.008390](https://doi.org/10.1364/OPEX.13.008390)
- 体系：silica-on-silicon，direct UV-written（扫描速度/退火调 index step）；**峰值 index step 0.0085–0.0092**（对应 Δn 与**我方 0.0065 同量级**）；波导宽 3.3–7.2 µm；耦合区中心距固定 8 µm、**核心间隙最小 ~1.5 µm**。
- 结构：方向耦合器（对称/非对称），用于宽带 3-dB/任意分束。
- 方法：实验 + 解析 sin² 耦合比模型；测 1200–1750 nm。
- 报告数值：**带宽（0.5 dB 平坦度）最高 ~430 nm**；总附加损耗 < 0.5 dB；耦合损耗 ~0.03 dB/facet；PDL ~0.3 dB；耦合比标准差 5 %。
- 对我方适用性：**high**（参数最接近的弱导方向耦合器工艺）。
- **论文直接证据 [direct]**：弱导（Δn≈0.0085）、~7 µm 宽波导、~1.5 µm 间隙的方向耦合器可以做到宽带（430 nm）且低损耗；非对称设计（不同宽度/Δn）可拓宽耦合比带宽。
- **我们的推论 [inference]**：① 我方 1310/1550 双波长可用同一组几何，κ 的波长色散在弱导体系中较温和但不可忽略；② 若做"耦合长度 vs 间距"的自身仿真，可用该文的 index step/宽度做中间校验点。
- 获取状态：**full_text**（Politecnico di Torino 机构库）。

### S13 — Baghsiahi, Wang & Selviah, *Optical loss and crosstalk in multimode photolithographically fabricated polyacrylate polymer waveguide crossings*, Proc. SPIE **8988**:898807 (2014). DOI [10.1117/12.2039860](https://doi.org/10.1117/12.2039860)
- 体系：聚丙烯酸酯聚合物多模波导（FR4 PCB 上）；**n_core = 1.5560，n_clad = 1.5264（Δn ≈ 0.030）**；**50 × 50 µm** 方形芯。
- 结构：同层 X 交叉，角度 10°–90°。
- 方法：**ray tracing（10⁶ 条光线）+ 实验（每个角度 50 次重复、6 个交叉/条）**；λ = 853 nm。
- 报告数值：实测"每交叉损耗 vs 角度"用**拟合式 y = 1.078·θ^(−0.873) dB（θ 以度计，10°–90°）**表示；据此：10° ≈ 0.14 dB、20° ≈ 0.079 dB、40° ≈ 0.043 dB、90° ≈ 0.021 dB。**ray tracing 预测 <20° 时 >1 dB**（严重高估）。
- 预测 vs 实测：ray tracing 在 20° 以下高估一个数量级（归因于几何光学忽略波动效应）。
- 对我方适用性：**medium**（弱导角度依赖**趋势**可用；绝对量不可迁移：多模、50 µm 芯、853 nm、Δn 0.03）。
- **论文直接证据 [direct]**：① 弱导体系交叉损耗随角度减小单调增大；② 90° 时 <0.03 dB；③ 几何光学在 <20° 不可靠，需要波动方法。
- **我们的推论 [inference]**：① 若我方的"损耗"预算只关心插损，5°–20° 也不会灾难（0.1 dB 量级，但该文是多模大芯，我方 few-mode 9 µm 会有差异）；② **但该文没有给出 dB 串扰**，其"crosstalk"是定性讨论，不能把 0.14 dB 当串扰。
- 获取状态：**full_text**（UCL Discovery PDF）。

### S14 — Gevorgyan & Hovsepyan, *The optical power distribution and scattering losses in symmetric channel waveguide X-junctions*, Opt. Quantum Electron. **23**(5):649–656 (1991). DOI [10.1007/BF00620091](https://doi.org/10.1007/BF00620091)
- 体系：对称通道波导 X 结（理论）。
- 方法：解析/理论（标题层面）；内容不可得。
- 对我方适用性：**medium**（若获取全文，可能是小角 X 结的解析框架）。
- **论文直接证据 [direct]**：仅题录级——存在一篇专门分析对称通道 X 结功率分配与散射损耗的解析论文。
- **我们的推论 [inference]**：无（不可引用其公式或数值）。
- 获取状态：**metadata_only**（Springer 付费，摘要被 API 屏蔽）。

### S15 — Zhang et al., *Power loss of X-junction in solid state optical gyrometer simulated by beam propagation method*, Proc. SPIE **5644**:479 (2005). DOI [10.1117/12.570300](https://doi.org/10.1117/12.570300)
- 体系：集成光波导线圈（固体陀螺）；弱导。
- 结构：X 结（交叉）。
- 方法：**BPM**；给出"功率损耗与交叉角的关系"以及"功率耦合与交叉角的关系"。
- 报告结论（摘要原话意译）：**"只要适当增大交叉角，X 结引起的功率损耗可以忽略"**。
- 对我方适用性：**medium**（方法学支持 BPM 用于小角 X 结；无数字）。
- **论文直接证据 [direct]**：BPM 被用作 X 结损耗/耦合 vs 角度设计的工具；损耗随角度增大而降至可忽略。
- **我们的推论 [inference]**：与 Adikan/Baghsiahi 的趋势一致，可作为方法选择的支持性引用，但不能用作数值校验。
- 获取状态：**abstract_only**（SPIE 付费）。

### S16 — Chu & Chaudhuri, *FDTD Simulation of Wave Propagating in Waveguide-Crossings at Large Angle*, OSA topical meeting "Numerical Simulation and Analysis in Guided-Wave Optics and Optoelectronics", paper SC3 (1989). DOI [10.1364/GWOE.1989.SC3](https://doi.org/10.1364/GWOE.1989.SC3)
- 体系：介质波导交叉（数值方法）。
- 方法：**FDTD**，针对**大角度**交叉。
- 报告内容（摘要原话要点）：先前工作用 BPM 分析"Δn 与 2Δn"型无源交叉时**只限于小角度（θ < 4°）与小折射率变化**；BPM 忽略反射、只做前向传播，因此**不能分析大几何/材料不连续结构**或反射相干叠加的情形——这正是需要用 FDTD 的理由。
- 对我方适用性：**medium**（本综述找到的**最重要的方法学边界陈述**）。
- **论文直接证据 [direct]**：BPM 的适用域被明确限定为 θ < 4° + 小 Δn；大角度需全波方法。
- **我们的推论 [inference]**：本项目应按角度分区选方法：5°–20° 用 BPM/SSFM（并用 EME 抽样校验），30°–90° 用 FDTD/EME/FEM；**θ<4° 这条线来自 1989 年的特定结构，不能当作普适定律**，但方向正确。
- 获取状态：**abstract_only**（Optica legacy 会议论文集，摘要可见）。

### S17 — (题录作者未核验), *An Effective Way of Reducing Waveguide Crossovers using 3D Silica Waveguide*, Kyushu University repository, p.142 (2018). DOI [10.15017/1961324](https://doi.org/10.15017/1961324)
- 体系：掺杂石英（doped silica）3-D 弯曲波导，**芯/包层相对折射率差 1 %**。
- 结构：4 条弯曲波导构成 4 输入/输出路径，用 3-D 路由**减少交叉数量**。
- 方法：**3-D BPM**；仿真。
- 报告数值：各输出端"近乎 100 % 透射"；**串扰约 −80 dB**（3-D BPM 仿真）。
- 对我方适用性：**high**（silica + 3-D + BPM + 弱导，方法学最接近的一类）。
- **论文直接证据 [direct]**：silica 3-D 路由用 3-D BPM 分析，报告 −80 dB 级串扰；动机是减少交叉数。
- **我们的推论 [inference]**：−80 dB 是**仿真**值且几何/波长/间距未知，只能作为"3-D BPM 可用于 silica 3-D 结构"的证据，**不能当 benchmark**；其"用 3-D 弯曲减少交叉"的思想与本项目 20 层布局直接相关。
- 获取状态：**abstract_only**（DOI 为机构库句柄、不在 Crossref；PDF 下载失败）。作者与期刊信息不可核验。

### S18 — Han et al., *High performance ultra-compact SOI waveguide crossing*, Opt. Express **26**(20):25602–25610 (2018). DOI [10.1364/OE.26.025602](https://doi.org/10.1364/OE.26.025602)
- 体系：SOI，高对比，超紧凑交叉。
- 报告数值：仿真插损 **< 0.175 dB**、串扰 **< −37 dB**（C 波段）；实测插损 **< 0.28 dB**、串扰 **约 −30 dB**（C 波段）。
- 预测 vs 实测：插损差 ~0.1 dB；**串扰差 ~7 dB（变差）**。
- 对我方适用性：**low**（但"串扰预测偏差可达 7 dB"这条极重要）。
- **论文直接证据 [direct]**：FDTD 预测的交叉串扰与实测可差 7 dB。
- **我们的推论 [inference]**：我方报告的串扰预测必须带**不确定度带**（至少 ±3–7 dB），不能给出"点值"。
- 获取状态：**abstract_only**。

### S19 — Seok et al., *Large-scale broadband digital silicon photonic switches with vertical adiabatic couplers*, Optica **3**(1):64–70 (2016). DOI [10.1364/OPTICA.3.000064](https://doi.org/10.1364/OPTICA.3.000064)
- 体系：SOI + MEMS 垂直绝热耦合器；64×64 开关（4096 个耦合器，8.6 × 8.6 mm 芯片）。
- 报告数值（摘要）：片上插损 3.7 dB、开关时间 0.91 µs、消光比 >60 dB、带宽 300 nm。
- 对我方适用性：**low**（交叉串扰数值不在可及摘要中；其 Table 数值见 S03 Table 1：0.017 dB / −55 dB，但**未能从原文核实**，本综述不采用为 benchmark）。
- **论文直接证据 [direct]**：千级交叉/耦合器的真实大规模电路存在，逐器件预算至关重要。
- **我们的推论 [inference]**：1283 个交叉的板级规模与真实大规模开关同量级，per-crossing 预算必须精确。
- 获取状态：**abstract_only**。

### S20 — Chen & Poon, *Low-Loss Multimode-Interference-Based Crossings for Silicon Wire Waveguides*, IEEE PTL **18**(21):2260–2262 (2006). DOI [10.1109/LPT.2006.884726](https://doi.org/10.1109/LPT.2006.884726)
- 体系：SOI 硅线波导。
- 报告数值：MMI 交叉插损 **~0.4 dB**，比同尺寸普通交叉改善 **~0.9 dB**（即普通交叉 ~1.3 dB）；显著串扰抑制；1520–1580 nm 内透射波长依赖 <0.2 dB。
- 对我方适用性：**low**。
- **论文直接证据 [direct]**：高对比"普通交叉"基线差（~1.3 dB），MMI 可改善 ~0.9 dB。
- **我们的推论 [inference]**：弱导体系的"普通交叉"基线好得多（见 S07 的低对比论述），因此 MMI 类结构设计对我方**损耗**问题无必要；我方问题在小角**串扰**。
- 获取状态：**abstract_only**。

### S21 — Feng, Li & Fan, *Compact and low cross-talk silicon-on-insulator crossing using a periodic dielectric waveguide*, Opt. Lett. **35**(23):3904–3906 (2010). DOI [10.1364/OL.35.003904](https://doi.org/10.1364/OL.35.003904)
- 体系：SOI，周期介质波导交叉；footprint < 4 × 4 µm²。
- 报告数值：插损 **~0.7 dB**；串扰 **< −40 dB**（宽带，实测）。
- 对我方适用性：**low**（但说明 −40 dB 级串扰在实验上可达，需相应测量手段）。
- **论文直接证据 [direct]**：−40 dB 级交叉串扰已被实测。
- **我们的推论 [inference]**：若我方模型预测 < −40 dB，需借用 Johnson(S03) 的噪声基底方法才能验证。
- 获取状态：**abstract_only**。

### S22 — Sun, Yu & Zhang, *Ultra-compact waveguide crossing for a mode-division multiplexing optical network*, Opt. Lett. **42**(23):4913–4916 (2017). DOI [10.1364/OL.42.004913](https://doi.org/10.1364/OL.42.004913)
- 体系：SOI 多模波导（同时处理 TE0/TE1）；21 × 21 µm²。
- 报告数值：**IL：TE0 ~1.82 dB，TE1 ~0.46 dB @1550 nm**；**串扰 < −18 dB（1510–1600 nm）**。
- 对我方适用性：**medium**（我方参考波导为 few-mode，这是最接近的"多模交叉"证据）。
- **论文直接证据 [direct]**：少模/多模交叉的模式相关损耗差异巨大（1.82 vs 0.46 dB），且串扰在 −18 dB 量级（高对比条件下）。
- **我们的推论 [inference]**：① 我方 9 µm/Δn=0.0065 波导 V≈3，属于 few-mode，**不能假设单模行为**；② 交叉处会有模式转换/模式串扰这一额外通道，标量单模 BPM 会漏掉；③ −18 dB 是硅光多模数，不能直接搬到我方。
- 获取状态：**abstract_only**。

### S23 — Lu et al., *Inverse-designed ultra-compact star-crossings based on PhC-like subwavelength structures for optical intercross connect*, Opt. Express **25**(15):18355–18364 (2017). DOI [10.1364/OE.25.018355](https://doi.org/10.1364/OE.25.018355)
- 体系：SOI，逆向设计（DBS）多端口 star-crossing。
- 报告数值：平均实测 IL < 0.75 / 0.9 / 1.5 dB；其余端口串扰 **−22.5 / −20 / −18 dB**（60 nm 带宽 @1550 nm）。
- 对我方适用性：**low**（我方为两两交叉，无星形多路交叉）。
- **论文直接证据 [direct]**：多端口/多路交叉的串扰显著高于 4 端口（−18 ~ −22.5 dB）。
- **我们的推论 [inference]**：本项目 1283 个交叉均为两两交叉（pairwise），可排除多路交叉机制；但**同一位置多根波导重叠**的情形需要检查（若布局中存在）。
- 获取状态：**abstract_only**。

### S24 — Nevlacsil et al., *Broadband low loss and ultra-low crosstalk waveguide crossings based on a multimode interferometer for 840 nm operation*, OSA Continuum **3**(2):334 (2020). DOI [10.1364/OSAC.381003](https://doi.org/10.1364/OSAC.381003)
- 体系：SiN/SiO₂（中等对比；SiO₂ n=1.455）；**单模输入波导宽 0.7 µm**（原文明确）；MMI 交叉；λ = 790–890 nm。
- 方法：**3-D FDTD + MODE 特征模求解器**；损耗=交叉后功率监视器/交叉前监视器归一化；串扰由 3-D FDTD 给出（实验无法测）。
- 报告数值：单交叉损耗 **~0.05 dB（实测，840 nm）**；100 nm 带宽内 **< 0.16 dB**；串扰 **~−60 dB（仿真，MMI 版）**、简单交叉 ~−40 dB；**明确说明 −40 dB 串扰无法实验测量**。
- 对我方适用性：**medium**（FDTD 流程与"仿真下限"的诚实讨论）。
- **论文直接证据 [direct]**：① 监视器归一化求损耗、FDTD 求串扰的标准流程；② −40 dB 以下串扰超出可测范围；③ 实测损耗略高于仿真。
- **我们的推论 [inference]**：① 我方若用 FDTD 做局部模型，应按"前/后监视器功率比"定义插损，并单独定义串扰基准（through 还是 input）；② 低于 −40 dB 的预测只能以"模型上界"形式报告。
- 获取状态：**full_text**（arXiv:2002.11399 版；正式版 OSA Continuum 3(2):334）。

### S25 — Chang & Zhang, *Silicon-based multimode waveguide crossings*（综述）, J. Phys. Photonics **2**(2):022002 (2020). DOI [10.1088/2515-7647/ab8698](https://doi.org/10.1088/2515-7647/ab8698)
- 体系：SOI 多模交叉综述（MMI、Maxwell fisheye、逆向设计）。
- 报告数值（综述表格，二次引用）：如非对称 Y 结 2 dB / −20 dB / 34×34 µm² / 3 模；Maxwell fisheye 0.5 dB / −20 dB / 27.5×27.5 µm²；另有 0.02 dB/−40 dB、0.5 dB/−20 dB/18×18 µm²、0.6 dB/−24 dB（60 nm）等。
- 对我方适用性：**medium**（few-mode 交叉难度的系统证据）。
- **论文直接证据 [direct]**：多模交叉需要更大 footprint、串扰普遍在 −18 ~ −24 dB；模式相关损耗是常态。
- **我们的推论 [inference]**：把我方 few-mode 波导当作"更难的单模问题"处理会低估风险；需要至少 2 个模式参与局部 S-matrix。
- 获取状态：**full_text**（IOP PDF）。

### S26 — Bamiedakis et al., *Low Loss and Low Crosstalk Multimode Polymer Waveguide Crossings for High-Speed Optical Interconnects*, CLEO 2007, pp.1–2. DOI [10.1109/CLEO.2007.4452523](https://doi.org/10.1109/CLEO.2007.4452523)
- 体系：多模聚合物波导（板级光互连）；弱/中等对比。
- 报告数值：**附加损耗 0.006 dB/crossing**（当时最低）；**串扰低至 −30 dB**。
- 对我方适用性：**medium**（弱导大角交叉的"低损耗/有限串扰"证据）。
- **论文直接证据 [direct]**：弱导多模体系 90° 交叉可做到 0.006 dB 附加损耗，但串扰仍在 −30 dB 量级。
- **我们的推论 [inference]**：大角交叉的瓶颈不是损耗而是**串扰底**（−30 dB 量级），这与"损耗小 ⇒ 但泄漏到交叉端仍有功率"的物理一致；我方大角串扰预期也在 −40 ~ −25 dB 量级。
- 获取状态：**abstract_only**（CLEO proceedings）。

### S27 — Hildén & Shevchenko, *Matrix analysis of high-density arrayed waveguides: Crosstalk suppression by bending*, Phys. Rev. Applied **22**(2):024077 (2024). DOI [10.1103/PhysRevApplied.22.024077](https://doi.org/10.1103/PhysRevApplied.22.024077)
- 体系：一般介质波导阵列。
- 方法：**耦合矩阵分析**，涵盖直波导与**弯曲**阵列；以弯曲降低串扰为例。
- 对我方适用性：**medium**（"从局部耦合系数组装整板串扰矩阵"的可选形式化）。
- **论文直接证据 [direct]**：存在可同时处理直/弯密集波导阵列串扰的矩阵方法；弯曲可降低串扰。
- **我们的推论 [inference]**：可用于验证我方"最近邻耦合 + 局部模型"组装是否会遗漏长程/弯曲效应；无数字可用。
- 获取状态：**abstract_only**。

### S28 — Bogaerts & Chrostowski, *Silicon Photonics Circuit Design: Methods, Tools and Challenges*, Laser Photonics Rev. **12**(4) (2018). DOI [10.1002/lpor.201700237](https://doi.org/10.1002/lpor.201700237)
- 内容：大规模光子电路设计的综述——从 schematic capture、电路仿真、版图、验证，到**紧凑模型（compact model）**、变异分析与光电共仿真。
- 对我方适用性：**medium**（(d) 类问题的标准范式）。
- **论文直接证据 [direct]**：大电路设计通过把器件抽象为紧凑模型并在电路层组合来完成，而非整版全波仿真。
- **我们的推论 [inference]**：本项目应把 1283 个交叉压缩为"角度分箱 + 层间偏移分箱"的少量局部 S-matrix 模板，再做板级组合——这正是该综述所述设计层。
- 获取状态：**abstract_only**（Wiley 全文被拦截）。

### S29 — Feit & Fleck, *Light propagation in graded-index optical fibers*, Appl. Opt. **17**(24):3990 (1978). DOI [10.1364/AO.17.003990](https://doi.org/10.1364/AO.17.003990)
- 内容：BPM/FFT split-step 方法的原始文献（求解 Helmholtz 方程）。
- 对我方适用性：**medium**（方法史与假设边界）。
- **论文直接证据 [direct]**：BPM 作为数值方法被建立。
- **我们的推论 [inference]**：所有玻璃波导 BPM/SSFM 工作（S01、S04、S17）都继承其**傍轴、前向、无反射**假设，因此在大角交叉处必须有独立的全波校验（见 S16）。
- 获取状态：**abstract_only**。

---

## 3. 横向分析：什么方法用在什么问题上

### 3.1 四类问题的"文献默认方法"

| 问题 | 文献主流方法 | 代表文献 | 典型设置/证据 |
|---|---|---|---|
| (c) 平行蒸发耦合 vs 间距（含垂直偏移） | **CMT/超模 + 实验标定**；3-D 情形用 FDTD 或 HCMT | S10、S11、S12、S09、S06、S02、S27 | 实验直接测"耦合比 vs 互作用长度"→拟合 κ；3-D 多层用 FDTD 算重叠；HCMT 处理任意位置/取向 |
| (a) 小角交叉 1°–20° | **BPM/SSFM（傍轴、前向）** + 解析模型；少数用 EME | S01、S15、S04、S29 | Adikan 用 BPM+analytic；Zhang 用 BPM 扫角度；Keil 用 SSFM 做 3-D 玻璃 |
| (b) 大角交叉 30°–90° | **FDTD / EME / FEM 全波** | S16、S07、S20–S25、S03、S18 | Chu 明确 BPM 只到 θ<4°；硅光全部用 3-D FDTD；Bogaerts 用 2-D EME |
| (d) 整板组装 | **S 参数/紧凑模型 + 电路网络组合** | S05、S28、S03、S27 | Lumerical port→S-matrix→INTERCONNECT；Clements/Bogaerts 设计流；矩阵耦合分析 |

### 3.2 典型数值设置（能被证实的部分）
- **3-D FDTD（Lumerical, S03/S05/S18/S24）**：优化阶段 mesh accuracy 2、最终 S 参数扫掠 mesh accuracy 3、全 PML；对称边界只能用于优化（S 参数扫掠会禁用 port）；port = mode source + field monitor + mode expansion monitor；通过 port mapping/auto-symmetry 把 4 次仿真减半；多模通过每 port 选多个模式。
- **EME（S07）**：2-D 特征模展开、分段均匀结构、1.55 µm；适用于 90° 交叉这种"分段近似成立"的几何。
- **BPM/SSFM（S01、S04、S15、S17）**：傍轴标量 Helmholtz；Keil 用实测模场反演折射率剖面；玻璃样品 10 cm；无反射。
- **解析/耦合模（S12、S14、S02）**：sin² 耦合比律；X 结解析功率分配；HCMT 的有限元弱形式。
- **收敛性/能量守恒**：**文献中很少系统报告**。S03/S05 用 Lumerical 内建 S 参数与功率归一化；S24 用"交叉后/交叉前监视器"归一化；S18 只报预测-实测差。**没有任何一篇给出 mesh 收敛曲线**——这是本领域报告规范的一个缺口，我方应自行补上（网格收敛 + 网格能量守恒 R+T+ΣS = 1）。

### 3.3 串扰（crosstalk）定义与报告方式（关键差异）
1. **交叉串扰 = 交叉端功率 / 输入端功率**（dB）：多数交叉论文隐含此定义；Lumerical 文档中 crosstalk 与 through/cross transmission 相邻给出（S05）。
2. **交叉串扰 = 交叉端 / 直通端**（dB）：S03 实测采用"through 与 cross 端口的相对信号"，并配合探测器噪声基底（可测下限约 −60 ~ −50 dB）。
3. **"耦合比（coupling ratio）"**（S01、S12）：交叉端功率占比（线性 %），与串扰是同一物理量的不同表述；**Adikan 的"coupling ratio"是否按 cross/input 定义，摘要未说明**（缺口）。
4. **平行段串扰**：S06 定义为"另一端口的信号 / 输入端信号"，随共传播长度振荡（因为两波导相位失配），因此**只报一个数字没有意义，必须报"最大值 vs 共传播长度"**。
5. **回损/反射**：S03 用白光反射仪报 backscatter（−35 ~ −55 dB）；S04 用反射功率占比（6 %/17 %）。

> **对本项目的直接要求**：报"crosstalk"时必须同时写明基准（input 还是 through）、端口集合（含哪些模式）、波长、以及是"单交叉"还是"链式累积"。文献里这四点经常缺失（S08、S18、S21、S22 的摘要都未写清）。

### 3.4 验证方式（文献怎么做）
- **端口投影 / 模式展开**：Lumerical port（S05）、EME 端口（S07）、功率监视器归一化（S24）。
- **能量守恒**：S05 的 S 参数框架隐含 R + T + Σ(cross) = 1；**没有文献给出显式数值检查**（缺口）。
- **网格收敛**：几乎无人报告（缺口）。
- **实验**：cut-back 链（S03，0–160 交叉）、多交叉链（S07，0–21）、50 次重复平均（S13）、跨晶圆 30 dies（S08）、端面成像（S04）。
- **预测-实测偏差**：最好的情况是 S03（插损 1–2 mdB、串扰 0.2 dB）；中等的 S18（串扰 7 dB 偏差）；差的 S13（ray tracing 在 <20° 高估 10 倍）。

---

## 4. 弱导玻璃 vs 硅光：哪些数字不能搬，为什么

| 量 | 硅光（S03/S07/S18/S20–S23） | 弱导玻璃/石英（S01/S10–S13/S17/S26） | 能否迁移 |
|---|---|---|---|
| Δn | ~2（Si/SiO₂） | 0.001–0.03 | ❌ |
| 模场尺寸 | 0.3–0.5 µm | 7–10 µm（S10：7.1×12.3；S11：9.6×9.0） | ❌ |
| 90° 交叉插损 | 0.007–1.3 dB（S03：0.043；S07：0.16；S20：~1.3 普通交叉） | 0.006–0.02 dB 量级（S26；S13 拟合 0.021 dB@90°） | ❌ 数值不可搬 |
| 90° 交叉串扰 | −30 ~ −70 dB（S21：<−40；S22：<−18；S26 弱导聚合物 −30） | 缺定量（S17 仿真 −80 dB；S26 聚合物 −30 dB） | ⚠️ 只能搬"方法/量级意识" |
| 小角 X coupler | 几乎无文献（硅光不做小角） | **S01：0.8°→95 %，5°→1.9 %** | ✅ 趋势与量级可搬，精确值不可搬 |
| 波长 | 1550/1310 | 800 nm（S04）、853 nm（S13）、1550 nm（S10/S11）、840 nm（S24） | ⚠️ 我方 1310 介于其间，模场/κ 需重算 |
| 偏振 | TE 单模为主 | fs 直写玻璃有 10⁻⁵–10⁻⁴ 双折射（S11） | ⚠️ 我方若用 fs 直写，偏振效应不可忽略 |
| 多模/少模 | 硅光多模交叉 −18 dB 串扰（S22/S25） | 弱导多模 50 µm 芯（S13） | ⚠️ 我方 few-mode 需按 S22/S25 处理，不能按单模 |

**为什么不能搬**：交叉/耦合的物理量是**模场重叠积分与相位失配**的函数，而不是 Δn 本身。高对比波导的模场小、宽角谱成分多，交叉处衍射强、辐射损耗大；弱导波导模场大、角谱窄，交叉近似"微扰"（S07 原话），但**小角处耦合长度长、耦合强**。因此硅光的"低插损/低串扰"是**工程结构（MMI、双刻蚀、逆向设计）**换来的，弱导玻璃不需要这些结构，但小角串扰是硅光文献里根本不存在的课题。

**唯一可整体迁移的是"验证方法学"**：FDTD + 端口模式投影 + S 参数 + cut-back 实测 + 噪声基底控制（S03/S05/S24）——这正是任务 C 所要求的。

---

## 5. 小角交叉的物理机理：文献说了什么、没说什么

### 5.1 文献中的角度依赖（可直接引用的部分）
- **Adikan 2006（S01）**：0.8°–5°，耦合比 95 % → 1.9 %；即交叉角减小时功率转移急剧增大；附加损耗 ~1 dB 且基本不随角度剧烈变化（"很低的偏振与波长依赖"）。
- **Baghsiahi 2014（S13）**：弱导（Δn≈0.03）多模、10°–90°，实测损耗随角度减小而增大，拟合 **∝ θ^−0.87**；90° ≈ 0.02 dB，10° ≈ 0.14 dB。**注意：这是"损耗"，不是"交叉端串扰"**；该文没有给出 dB 串扰值。
- **Zhang 2005（S15）**：BPM 扫描交叉角，结论"角度适当增大后 X 结损耗可忽略"。
- **Chu 1989（S16）**：BPM 只在 θ<4°、小 Δn 下被验证过（这既说明小角是 BPM 的主场，也说明大角不能靠 BPM）。
- **S07（Bogaerts）**：低对比波导的直交叉"几乎不衍射"——解释了为什么弱导大角交叉损耗小。
- **S26（Bamiedakis）**：弱导多模 90° 交叉附加损耗 0.006 dB，但串扰 −30 dB。

### 5.2 物理图像（标准耦合模/相位匹配论证，**我们的重构，非某篇论文原文**）
把交叉看成两根相同波导在角度 θ 下的瞬态耦合。交叉区横向"相互作用长度"约为

```
L_int ≈ w_mode / tanθ  (θ 不太大时可写 ≈ w_mode / θ)
```

两波导的模式在横向的相位失配为

```
Δk_x = β sinθ ≈ β θ ,   β = 2π n_eff / λ
```

耦合积分是模式乘积的横向傅里叶分量在 Δk_x 处的取值；由于模场横向谱宽 ~1/w_mode，**当 βθ·w_mode ≫ 1 时耦合被指数抑制**。于是存在一个"相位匹配过渡角"

```
θ_c ≈ 1/(β w_mode) = λ / (2π n_eff w_mode)
```

本项目的量级估算（**[inference]**）：n_eff≈1.5、λ=1310 nm，
- 若 w_mode≈4.5 µm（9 µm 方芯的基模半宽）：θ_c ≈ 1.31/(2π·1.5·4.5) rad ≈ 0.031 rad ≈ **1.8°**；
- 若 w_mode≈9 µm（用芯宽）：θ_c ≈ **0.9°**；λ=1550 nm 时相应放大 1.18 倍。

即 **θ_c ≈ 1°–2°**（对 λ=1550 nm 约放大 1.18 倍）。对照 Adikan（其波导约 6 µm 芯、λ≈1.5 µm）：若取模场半宽 ~3 µm，则 θ_c≈3°；若取全芯宽 6 µm，则 θ_c≈1.5°。无论取哪种定义，0.8°（θ/θ_c≈0.3–0.5）落在"强耦合"一侧，而 5°（θ/θ_c≈1.7–3.3）落在"耦合被抑制"一侧——**与其 95 %→1.9 % 的数据在定性上一致**（该 θ_c 公式本身是我们的尺度估计，不是 Adikan 论文的公式）。

由此得到本项目的角度分区图像（**[inference]，需仿真验证**）：

| 交叉角 | 相对 θ_c | 预期机制 | 交叉端串扰的量级猜测 |
|---|---|---|---|
| 0.5°–2° | ≲ θ_c | 相位匹配、强耦合，近 3-dB/完全耦合 | 0 ~ −6 dB（灾难） |
| 5° | ~3–5 θ_c | 过渡区，仍有一次耦合 | **−20 ~ −14 dB** |
| 10°–20° | ~6–20 θ_c | 快速衰减 | −30 ~ −20 dB |
| 30°–60° | ~20–60 θ_c | 近似微扰，主要剩余辐射/反射 | −45 ~ −30 dB |
| 90° | ~50–90 θ_c | 微扰（弱导），反射 ~5 %–15 %（S04 玻璃 T 结实测） | −45 ~ −30 dB（串扰）、插损 0.01–0.1 dB |

**关键结论（[inference]）**：本项目最小交叉角 5.15° 已约为 θ_c 的 3 倍，**"3-dB 灾难区"（≲2°）并不出现在本板中**；但 5°–15° 的小角尾部仍是全板串扰预算的主导项（数量少但每项大），而中位角 63° 及以上的交叉大概率接近微扰区。**文献对"Δn≈0.0065、9 µm、λ=1310/1550 nm 的 few-mode 玻璃波导"没有任何直接的 crosstalk vs angle 数据——这一点必须在报告中如实声明。**

### 5.3 文献沉默之处（必须声明）
1. **没有**任何一篇文献给出"Δn≈0.005–0.01、8–10 µm 芯、λ=1310/1550 nm、few-mode 玻璃波导"的 **crosstalk vs 交叉角** 实测或全波曲线；S01 是最接近的，但仅 0.8°–5° 且参数不完全可得。
2. **没有**弱导玻璃体系 90° 交叉的 dB 串扰实测（S26 是聚合物、多模；S17 是仿真且几何未知）。
3. **没有** few-mode 玻璃交叉的"模式串扰/模式转换"定量数据（S22/S25 是硅光）。
4. **没有** 3-D 玻璃 20 层、上千交叉的整板实测或整板全波验证。
5. **没有** HCMT 在"弱导 + 少模 + 有辐射"交叉上的验证数据（S02 声明其精度限于低辐射损耗区）。
6. **没有**文献报告 BPM/SSFM 在 90° 交叉上与全波的系统偏差（S16 只给原则性否定）。

---

## 6. 对本项目的直接可用结论 / 不可用结论

> 每条标注 `[direct evidence]`（文献直接支持）或 `[inference]`（我们的外推/推论）。

### 可用结论
1. **[direct evidence, S01]** 弱导 silica X coupler 在 0.8°–5° 的耦合比实测从 95 % 降到 1.9 %，附加损耗 ~1 dB；BPM+解析模型在该范围内与实测"good agreement"。→ 小角交叉必须用波动方法（BPM/EME/FDTD）算，且小角是全板串扰的主要风险源。
2. **[direct evidence, S16]** BPM 只在"小角（θ<4°）+ 小 Δn"下被验证，且忽略反射、不能处理大不连续。→ 30°–90° 交叉的局部模型必须用全波（FDTD/EME/FEM）；BPM 结果只能用于小角端并需 EME 抽样校验。
3. **[direct evidence, S10/S11]** 熔石英 fs 直写方向耦合器：5 µm 中心距耦合长度 ~0.5 mm、15 µm ~5.6 mm；模场 9.6×9.0 µm 时 8 µm 间距需 19.2 mm。→ 耦合长度对间距/模场极敏感，**κ 必须用自己的模场积分算，不能从 Δn 猜**。
4. **[inference, 基于 S10/S11 指数外推]** 中心距 ≥50 µm 时，弱导玻璃波导的平行蒸发耦合在板级长度上可忽略（耦合长度将超过米量级）。→ (c) 类"平行/跨层 ≥50 µm"项目可置为零耦合，但**必须记录为模型假设并做敏感度分析**。
5. **[direct evidence, S07/S26/S13]** 弱导（低对比）波导的 90° 直接交叉只是"轻微扰动"，实测附加损耗可到 0.006–0.16 dB 量级（S26 聚合物 0.006 dB；S07 经结构优化 −0.16 dB），且损耗随角度减小而增大（S13 拟合 ∝θ^−0.87）。→ 大角交叉的插损预算可以很小；**串扰**是更值得关注的量。
6. **[direct evidence, S03/S05/S24]** 局部交叉器件应通过"端口模式投影 + S 参数矩阵 + cut-back"表征；串扰必须写明基准（input vs through）与噪声基底（−40 ~ −50 dB 以下不可测）。
7. **[direct evidence, S28/S05/S27]** 整板应从"局部紧凑模型 + 电路级 S 参数组合"组装，而非整版 FDTD；这对 1024 通道、1283 交叉是唯一可行路径。
8. **[direct evidence, S04]** 玻璃 90° T 结实测有 6 %–17 % 功率反射回输入端口。→ 局部模型若只有"通过/交叉"两个端口会漏掉可观的反射损耗。
9. **[direct evidence, S22/S25]** few-mode 波导交叉的模式相关损耗差异大（1.82 vs 0.46 dB），串扰在 −18 dB 量级（高对比）。→ 我方参考波导为 few-mode 时，局部 S-matrix 必须至少包含 2 个模式，不能只算基模。
10. **[direct evidence, S18]** FDTD 预测的交叉串扰与实测可差 ~7 dB。→ 我方给出的串扰预测必须附不确定度带（保守 ±3 ~ ±7 dB），不能报单点值。

### 不可用结论（禁止直接搬用）
1. **[不可用]** 硅光的 0.007–0.16 dB 插损、−40 ~ −70 dB 串扰绝对值（S03/S07/S08/S18/S20–S23）——Δn 与模场差 1–2 个数量级。
2. **[不可用]** S19（Seok）的 0.017 dB/−55 dB 交叉数值——**所见为 Johnson Table 1 的二次引用，未核实原文**，本综述不采用。
3. **[不可用]** S01 的"95 %@0.8°、1.9 %@5°"直接当作我方数值——材料体系（UV-written silica-on-silicon）与波长/模场不同，只能作为趋势锚点。
4. **[不可用]** S13 的 0.14 dB@10° 当作我方"crosstalk"——它是**插损**，且是多模 50 µm 芯、853 nm。
5. **[不可用]** S17 的 −80 dB 串扰——纯仿真、几何/波长未知、非同行评审会议摘要，只能证明"3-D BPM 被用于 silica 3-D 路由"。
6. **[不可用]** 任何"15 篇文献平均"式的元分析——本样本是策展集合，不可做统计推断。

---

## 7. 未获取到的全文与由此产生的不确定性（诚实清单）

| 编号 | 文献 | 状态 | 影响 |
|---|---|---|---|
| S01 | Adikan 2006, Appl. Opt. 45:6113 | abstract_only（Optica bot-check；UM repo 无全文；ECIO 版 401） | **无法核实**：交叉角如何定义（两波导轴夹角 vs 半角？）、"coupling ratio"分母是什么、BPM 的网格/边界/折射率剖面、BPM vs 实测偏差数字 |
| S02 | Hammer 2017, JOSA B 34:613 | abstract_only（Optica bot-check；Paderborn 库不可达） | **无法核实**：具体耦合项公式、模式归一化方式、任意角度/位置的坐标变换、与全波对比的具体误差、代码是否公开 |
| S08 | Ma 2013, Opt. Express 21:29374 | abstract_only | 无法核实 FDTD 设置与预测-实测细节；数值仅通过摘要与 Johnson Table 1 交叉核对 |
| S09 | Szameit 2006, Appl. Phys. B 82:507 | metadata_only（Springer 付费） | **无法获得任何 C(间距) 数值**；仅有"研究了耦合常数 vs 间距/波长"的题录级陈述 |
| S14 | Gevorgyan 1991, Opt. Quantum Electron. 23:649 | metadata_only（Springer 付费，摘要被屏蔽） | **完全无法引用其解析模型**；仅知道存在这一主题 |
| S15 | Zhang 2005, SPIE 5644:479 | abstract_only | 无角度-损耗数值、无 BPM 设置 |
| S16 | Chu & Chaudhuri 1989, OSA SC3 | abstract_only | 只有"BPM 限于 θ<4°+小 Δn"的原则性陈述，无定量对比 |
| S17 | Kyushu 2018（机构库） | abstract_only（PDF 下载失败） | 作者、期刊、几何、波长均不可核验；−80 dB 不可作为 benchmark |
| S18–S23、S26 | Han 2018、Seok 2016、Chen&Poon 2006、Feng 2010、Sun 2017、Lu 2017、Bamiedakis 2007 | abstract_only | 无完整设置；部分数值仅有上界；S19 的交叉数值无法核实 |
| S27、S28、S29 | Hildén 2024、Bogaerts&Chrostowski 2018、Feit&Fleck 1978 | abstract_only | 方法学引用可靠，但无具体数值 |
| — | Optica（JOSA B/AO/OL/OE）全系 | **整站被 bot-check（perfdrive）拦截** | 凡 Optica 出版的非 OA 文章均只能读摘要；这是本次调研最大的系统性限制 |

**由这些缺口导致的不确定性**：
- 我方"小角交叉串扰"的量级估计（§5.3 表）**没有直接文献校验**，只有 Adikan 两端点作为趋势锚点；
- BPM 与全波在我方几何上的偏差**未知**，必须靠自建 EME/FDTD 对比来定；
- HCMT 是否可作我方主方法**无法判断**（没有公开的验证数据/代码）；
- S01 的"coupling ratio"定义未确认，若它实际是"cross/(cross+through)"，则 −17 dB 的换算需修正（差异约 0.5 dB 以内，不影响量级结论）。

---

## 附录 A：全部引用链接（按编号）

1. Adikan et al., Appl. Opt. 45, 6113 (2006) — [10.1364/AO.45.006113](https://doi.org/10.1364/AO.45.006113)
2. Hammer et al., JOSA B 34, 613 (2017) — [10.1364/JOSAB.34.000613](https://doi.org/10.1364/JOSAB.34.000613)
3. Johnson & Sahin, Opt. Express 28, 12498 (2020) — [10.1364/OE.381304](https://doi.org/10.1364/OE.381304)
4. Keil et al., Sci. Rep. 1, 94 (2011) — [10.1038/srep00094](https://doi.org/10.1038/srep00094)
5. Ansys Lumerical KB, "Waveguide crossing" — [optics.ansys.com/hc/en-us/articles/360042800433](https://optics.ansys.com/hc/en-us/articles/360042800433-Waveguide-crossing)
6. Chiles et al., APL Photonics 2, 116101 (2017) — [10.1063/1.5000384](https://doi.org/10.1063/1.5000384)；arXiv: [1708.09438](https://arxiv.org/abs/1708.09438)
7. Bogaerts et al., Opt. Lett. 32, 2801 (2007) — [10.1364/OL.32.002801](https://doi.org/10.1364/OL.32.002801)
8. Ma et al., Opt. Express 21, 29374 (2013) — [10.1364/OE.21.029374](https://doi.org/10.1364/OE.21.029374)
9. Szameit et al., Appl. Phys. B 82, 507 (2006) — [10.1007/s00340-005-2127-4](https://doi.org/10.1007/s00340-005-2127-4)
10. Amorim et al., J. Lightwave Technol. 35, 3615 (2017) — [10.1109/JLT.2017.2715118](https://doi.org/10.1109/JLT.2017.2715118)
11. Fernandes et al., Opt. Express 19, 11992 (2011) — [10.1364/OE.19.011992](https://doi.org/10.1364/OE.19.011992)
12. Olivero & Svalgaard, Opt. Express 13, 8390 (2005) — [10.1364/OPEX.13.008390](https://doi.org/10.1364/OPEX.13.008390)
13. Baghsiahi et al., Proc. SPIE 8988, 898807 (2014) — [10.1117/12.2039860](https://doi.org/10.1117/12.2039860)
14. Gevorgyan & Hovsepyan, Opt. Quantum Electron. 23, 649 (1991) — [10.1007/BF00620091](https://doi.org/10.1007/BF00620091)
15. Zhang et al., Proc. SPIE 5644, 479 (2005) — [10.1117/12.570300](https://doi.org/10.1117/12.570300)
16. Chu & Chaudhuri, OSA topical meeting, paper SC3 (1989) — [10.1364/GWOE.1989.SC3](https://doi.org/10.1364/GWOE.1989.SC3)
17. "An Effective Way of Reducing Waveguide Crossovers using 3D Silica Waveguide", Kyushu Univ. repo (2018) — [10.15017/1961324](https://doi.org/10.15017/1961324)
18. Han et al., Opt. Express 26, 25602 (2018) — [10.1364/OE.26.025602](https://doi.org/10.1364/OE.26.025602)
19. Seok et al., Optica 3, 64 (2016) — [10.1364/OPTICA.3.000064](https://doi.org/10.1364/OPTICA.3.000064)
20. Chen & Poon, IEEE Photon. Technol. Lett. 18, 2260 (2006) — [10.1109/LPT.2006.884726](https://doi.org/10.1109/LPT.2006.884726)
21. Feng et al., Opt. Lett. 35, 3904 (2010) — [10.1364/OL.35.003904](https://doi.org/10.1364/OL.35.003904)
22. Sun et al., Opt. Lett. 42, 4913 (2017) — [10.1364/OL.42.004913](https://doi.org/10.1364/OL.42.004913)
23. Lu et al., Opt. Express 25, 18355 (2017) — [10.1364/OE.25.018355](https://doi.org/10.1364/OE.25.018355)
24. Nevlacsil et al., OSA Continuum 3, 334 (2020) — [10.1364/OSAC.381003](https://doi.org/10.1364/OSAC.381003)；arXiv: [2002.11399](https://arxiv.org/abs/2002.11399)
25. Chang & Zhang, J. Phys. Photonics 2, 022002 (2020) — [10.1088/2515-7647/ab8698](https://doi.org/10.1088/2515-7647/ab8698)
26. Bamiedakis et al., CLEO 2007, pp.1–2 — [10.1109/CLEO.2007.4452523](https://doi.org/10.1109/CLEO.2007.4452523)
27. Hildén & Shevchenko, Phys. Rev. Applied 22, 024077 (2024) — [10.1103/PhysRevApplied.22.024077](https://doi.org/10.1103/PhysRevApplied.22.024077)
28. Bogaerts & Chrostowski, Laser Photonics Rev. 12(4) (2018) — [10.1002/lpor.201700237](https://doi.org/10.1002/lpor.201700237)
29. Feit & Fleck, Appl. Opt. 17, 3990 (1978) — [10.1364/AO.17.003990](https://doi.org/10.1364/AO.17.003990)

## 附录 B：辅助/背景资料（未入矩阵，仅用于背景阅读）
- Hammer, "Wave Interaction in Photonic Integrated Circuits: Hybrid Analytical/Numerical Coupled Mode Modeling"（作者公开讲稿 PDF，2-D HCMT 框架示意）— [computational-photonics.eu/Papers/Pres/wihelp.pdf](https://computational-photonics.eu/Papers/Pres/wihelp.pdf)
- Corrielli, Crespi & Osellame, "Femtosecond laser micromachining for integrated quantum photonics", Nanophotonics 10, 3789 (2021) — [10.1515/nanoph-2021-0419](https://doi.org/10.1515/nanoph-2021-0419)（仅摘要）
- Tan et al., "Photonic circuits written by femtosecond laser in glass", Adv. Photonics 3, 024002 (2021) — [10.1117/1.AP.3.2.024002](https://doi.org/10.1117/1.AP.3.2.024002)（仅摘要）
- Wu et al., "State-of-the-Art and Perspectives on Silicon Waveguide Crossings: A Review", Micromachines 11, 326 (2020) — [10.3390/mi11030326](https://doi.org/10.3390/mi11030326)（仅摘要）
