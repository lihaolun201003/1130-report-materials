# 32×32 光互连拓扑与 1024 通道选型

**[应用需求线索：为什么做 1024 路](应用需求线索.md)** · 从 CPO 机箱的光纤托盘和商用 OXC 背板出发，列出可追的设备、配线部件，以及与现有四边玻璃布线模型的关系。

**2026-11-23 全文复核** · [中文研究报告](研究报告.md) · [证据矩阵](证据矩阵_全文复核.csv) · [参考文献与双向引文追踪](参考文献与引文追踪.md)。本次复核定位了中兴的 992／1024 两种工程计数，以及康宁期刊原文中 48 路 Shuffle、1024 路 CPO 扇出和附加测试结构。以下保留 2026-11-16 初步调研入口，证据状态和数量以新报告为准。

**32×32 是有工程依据的基准规模，具体设备是否需要 1024 条固定光路取决于内部架构。** 华为 OptiX OSN 9800 P32 产品资料列出 1–32 degree ROADM 和 32 个业务板槽位。中兴公开描述了 32-degree OXC、电信网络应用和光背板，并指出不同节点采用的方向数有别。这里的 32 首先是设备的线路侧维度。厂商公开规格没有给出对应机型的背板逐纤表。[华为规格][S03] · [中兴技术说明][S02]

**1024 来自每一对输入、输出 WSS 组之间各预布一条链路。** Cheng 等人的标准 route-and-select OXC 在两个 WSS 级之间设置固定重排。若有 32 个 1×32 输入侧 WSS 和 32 个 32×1 输出侧 WSS，来自输入组 i 的第 j 个分支接入输出组 j 的第 i 个分支。计入全部组对时，中间有 1024 条物理链路，玻璃板两侧各有 1024 个空间端点。Tyco 的专利曾给出四托盘各四个 8×8 电路的 1024 纤设计。若同一编号的入口和出口对应同一网络方向，工程上排除该方向回送且无其他端口补齐，则只剩 992 条。单个波长切片最多有 32 路无争用连接。[Cheng 等，§II、Fig. 1 图注及 Table I][S01] · [Tyco 的四托盘设计][S31]

**最接近的应用是板内固定光重排。** OXC 背板给出连接逻辑，AI 网络的光纤 Shuffle 和三维直写玻璃 Shuffle 给出形态与工艺先例。Corning 与 Fraunhofer IZM 的 ECTC 论文公开摘要报告了从机箱面板到 CPO 区域的 1024 路玻璃扇出板，说明千路玻璃互连已有制备先例。该板采用面板级扇出；目前查得的证据尚未把商用 32-degree OXC、逐纤 32×32 全组合、单板飞秒直写 1024 路以及逐路光学验收连接成同一产品证据链。[Castro 技术报告][S11] · [Brusberg 等，ECTC][S14]

**现有毕设板有 1024 条固定路由任务。** 两份连接表按路线 ID 核对一致，包含四边 64 个双排连接器和 2048 个互不重复的空间端点。1024 路分布在 712 种连接器对上，且连接器图存在三角形。现有布局应称为“四边双排 1024 通道固定互连”，可另定义标准 32×32 转置 Shuffle 作为同规模对照。HBM3E 的 1024 是电 I/O 位宽，现有芯片光互连资料不足以把它作为 1024 条物理波导的需求依据。[本地连接表审计](05_现有1024连接表适配分析.md) · [Micron HBM3E][S19] · [Intel OCI][S21]

**后续最值得核查的是目标机型的背板端口表和装配边界。** 先确认线路、上下路、保护和回送如何计入 32 个组，再把固定净表和端面几何独立定义出来。针对候选工艺测量短样的端面耦合、传播与弯曲损耗、长并行段串扰，才能判断哪类固定光纤重排适合迁移到玻璃板。

- [光交换与 WSS](01_光交换与WSS基础.md)
- [Fiber Shuffle 与玻璃波导](02_Fiber_Shuffle与三维玻璃波导.md)
- [32×32 选型及规模对照](03_为什么是32x32.md)
- [HBM、GPU 与 CPU 评估](04_HBM_GPU_CPU应用评估.md)
- [现有连接表审计](05_现有1024连接表适配分析.md)
- [绪论与 30 秒、2 分钟、详细答辩口径](06_本科毕业论文应用背景建议.md)
- [参考文献与可定位证据](references.md) · [证据矩阵](evidence_matrix.csv)

[S01]: https://doi.org/10.1109/JLT.2023.3301057
[S02]: https://www.zte.com.cn/global/about/magazine/zte-technologies/2022/6-en/special-topic--intelligent-e-otn/5.html
[S03]: https://carrier.huawei.com/~/media/CNBGV2/download/products/networks/WDM-OTN/OSN-9800-P32-en.pdf
[S11]: https://www.ieee802.org/3/ad_hoc/E4AI/public/26_0224/castro_e4ai_02_260224.pdf
[S14]: https://doi.org/10.1109/ECTC51687.2025.00016
[S19]: https://www.micron.com/products/memory/hbm/hbm3e
[S21]: https://download.intel.com/newsroom/archive/2025/en-us-2024-06-26-intel-demonstrates-first-fully-integrated-optical-io-chiplet.pdf
[S31]: https://patents.google.com/patent/US7092592B2/en
