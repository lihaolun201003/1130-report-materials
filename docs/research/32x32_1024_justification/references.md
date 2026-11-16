# 参考文献和证据定位

检索与核对日期为 2026-11-16。先检查项目根目录、Native3D、既有调研和保存的原始端口清单。外部参考文献以作者公开稿、期刊、厂家、专利及标准组织的一手材料为主。正文定位优先于摘要，受限全文的结论保留到摘要能支持的精度。矩阵按原始结论记录数据性质，样机、仿真、提案和产品规格可出现在同一资料中。

- **A** 实际器件、测试样品或系统的实测。若仅取到摘要，A 表示摘要报告的证据类型，测试方法、样本及边界仍待核。
- **B** 工程架构、产品规格或原型演示。
- **C** 仿真与模型计算。
- **D** 架构设想、专利实施例或条件推导。
- **全文定位** 指读到支持主张的正文、数据表或图注。需要目视确认的图片已在各条记录标明状态。**unknown** 表示现有来源不足以确定该栏；有“模型”“规格”“推导”前缀的数字只能在对应口径使用。

## 检索与覆盖记录

| 目的 | 典型检索式 | 核查路径 |
|---|---|---|
| 组对固定净表及采用 32 的条件 | “A Three-Phase Modularization Approach” Cheng ROADM OXC pdf 3301057；32 degree ROADM 1x32 WSS optical backplane；32×32 32-degree optical cross connect fiber shuffle 1024 992 | 网页搜索、学术搜索、作者机构和出版社、Crossref 及专利原文 |
| 千路实体波导及直写的最近先例 | “2020ECS6002” Jiang 3D waveguides shuffle；femtosecond laser written glass optical shuffle 512 1024 1000 channel；“420 mm” “255 mm” “1024” Brusberg glass waveguide | IEICE、Kyushu、IEEE、OFC、Fraunhofer IZM 和报告，正向检索确认 ECTC 跨机构出版记录 |
| 数据中心固定重排 | Corning fiber shuffle MPO breakout；“Optical Shuffle Architectures” Castro E4AI；OptoConnect Aggregation Fiber Shuffle Boxes | 读 Corning 和 Molex 官方页面、IEEE 演示 PDF 以及 NVL72 结构化布线案例 |
| 架构反例 | 32x32 MZI optical switch 1024；64x64 MEMS Benes；Jupiter optical circuit switching 136 Apollo | 核对正文的外部端口、开关单元、测试路径与并发条件 |
| 芯片光互连 | HBM3E 1024 HBM4 2048 Micron；Intel OCI eight fiber pairs；“Optically Connected Multi-Stack HBM Modules” | 产品文档与作者论文，分别核对比特位宽、波长、光纤、链路带宽 |

采用公开检索的相关性排序和定向追查，无起始年份限制。网页结果总量及索引覆盖为 unknown。主要追查已收录的早期光纤托盘设计、华为 32 槽背板、IOX 千路玻璃板和当代直写样品。补充检索没有建立同时满足商用 OXC 逐纤表、单板三维飞秒直写 1024 路、完整逐路光学性能的证据链。全文访问不全和厂商净表未公开限制了排除性结论。

**已深入阅读的资料范围**　光交换主干包括 S01、S02、S03、S05–S09、S31–S32。固定重排、制造及部署包括 S10–S11、S16–S18、S25–S26。接口与系统包括 S19–S24、S27。各条目列出实际读取位置。S12、S13、S14、S15、S29、S30 属摘要或书目辅助，独立于全文阅读计数。

**出版状态核对**　2026-11-16。S01 交叉核对 Optica、作者机构和 Crossref，IEEE 落地页受访问限制，Crossref 未返回更新关系。S14 核对 ECTC 官方日程、Fraunhofer IZM 书目和 Crossref，IEEE 落地页受限，出版社状态仍待确认。S13 在 IEICE/J-STAGE 匹配正式版及同 DOI 的提前版，公开页未显示影响所引用摘要的更正。其他期刊或会议条目以各条所链发布页及可取得版本核对，受限或不同版本的内容见各条边界。公开网页观察不足以断言期刊未来或未索引更正的状态。

## 参考条目

### S01 A Three-Phase Modularization Approach of OXC for Large-Scale ROADM

Ziyu Cheng、Tong Ye、Yixiao Zhu、Weisheng Hu。2023。B 级。§II.A–C、Fig. 1–2、Table I、§IV Fig. 10–12。

路径级 1×9/9×1 WSS 模拟网络传输。FULLTEXT_LOCATED。图注和正文核实每组对一纤。独立 Fig. 1 图形获取受限。1024 是代入 N=32，单槽并发 N；没有整机 32×32 光纤 BOM。 适合引用在OXC 架构与并发口径一节。[原始论文或官方资料](https://doi.org/10.1109/JLT.2023.3301057)

### S02 Optical Cross-Connect Technology and Application

ZTE Technologies。2022。B 级。Technical Principles、Main Application Scenarios、Fig. 1–2。

32-degree 设备及工程例；太原枢纽 57 degree。企业正文。16/32 的节点用法是中兴所述工程口径，57 是站点维度。厂商未披露逐纤表和并发，1024T 带宽不作为路数。 适合引用在32 的工程来源一节。[原始论文或官方资料](https://www.zte.com.cn/global/about/magazine/zte-technologies/2022/6-en/special-topic--intelligent-e-otn/5.html)

### S03 Huawei OptiX OSN 9800 P32

Huawei。未署年。B 级。p.2 Optical Layer Architecture；p.3 Technical Specifications。

32 业务板槽，1–32 degree。官方整份规格。规格支持维度；固定路数、并发、量产和具体净表 unknown。 适合引用在产品选型依据一节。[原始论文或官方资料](https://carrier.huawei.com/~/media/CNBGV2/download/products/networks/WDM-OTN/OSN-9800-P32-en.pdf)

### S04 Wavelength Selective Switch (WSS) Modules

Molex。未署年。B 级。产品简介与 Products。

Single 1×2 到 Twin 1×32+ 产品范围。官方完整产品说明。数字表示 WSS 分支；同时切换能力依频谱和产品配置。整 OXC 和波导数量 unknown。 适合引用在1×32 元器件可实现性一节。[原始论文或官方资料](https://www.molex.com/en-us/products/optical-solutions/wavelength-selective-switch--wss--modules)

### S05 32 × 32 silicon photonic MEMS switch with gap-adjustable directional couplers fabricated in commercial CMOS foundry

Sangyoon Han 等。2021。A 级。§2 Fig. 1；§3 Fig. 4–7。

32×32 硅光芯片实测。FULLTEXT_LOCATED 并目视 Fig. 1。共用行列导路；一对一最大 32，实际同时激活量未作为本报告证据。内部有源路由，不是固定玻璃板。 适合引用在32×32 动态端口反例一节。[原始论文或官方资料](https://doi.org/10.1117/1.JOM.1.2.024003)

### S06 Broadband 32 × 32 Strictly-Nonblocking Optical Switch on a Multi-Layer Si3N4-on-SOI Platform

Wei Gao、Xin Li、Liangjun Lu、Chenghan Liu、Jianping Chen、Linjie Zhou。2023。A 级。§2 Fig. 1、Fig. 4；性能章节。

32×32；1984 个 MZI 单元、2048 个层间耦合器。FULLTEXT_LOCATED。结构允许最多 32 路一对一。中间按结构推导 1024 个专用支路对；每条可含多个不同材料层的导波段。交叉数 246016，不可套为玻璃损耗。 适合引用在架构同类、工艺不同的先例一节。[原始论文或官方资料](https://doi.org/10.1002/lpor.202300275)

### S07 Silicon photonic MEMS switches based on split waveguide crossings

Yinpeng Hu、Yi Sun、Ye Lu、Huan Li、Liu Liu、Yaocheng Shi、Daoxin Dai。2025。A 级。Results: 64×64 switch，Fig. 4。

硅光 64×64，352 个 2×2 单元。FULLTEXT_LOCATED。4096 条谱对应路径依次表征；并发一对一上限 64。64×64 不要求 4096 条专用空间纤，不能引采购规模。 适合引用在64×64 替代架构一节。[原始论文或官方资料](https://doi.org/10.1038/s41467-024-55528-9)

### S08 Mission Apollo: Landing Optical Circuit Switching at Datacenter Scale

Ryohei Urata 等。2022。A 级。§3 Fig. 5–9、Table 1。

136×136 Palomar OCS 生产组件及光机表征。FULLTEXT_LOCATED（作者稿）。136 个外部双射配对为理论并发上限。物理外部光纤和设备内部逐段纤留空；镜面转向不产生 N² 固定光纤。 适合引用在生产光交换架构与光路实现一节。[原始论文或官方资料](https://arxiv.org/abs/2208.10041)

### S09 Jupiter Evolving: Transforming Google’s Datacenter Network via Optical Circuit Switches and Software-Defined Networking

Leon Poutievski 等。2022。A 级。§2–3、Fig. 1–3、Appendix F。

Jupiter 生产流量、网络运营经验。FULLTEXT_LOCATED。和 Apollo 是同一部署体系不同层次的材料。端口总量和同时电路数依配置，非 1024 独立波导清单。 适合引用在真实 OCS 部署趋势一节。[原始论文或官方资料](https://doi.org/10.1145/3544216.3544265)

### S10 Data Center Shuffling Solutions

Corning Optical Communications。未署年。B 级。Shuffle Boxes、FAQ: Shuffling Methods。

2×2、4×4 产品说明，箱体 1–6 RU。官方产品正文。2×2/4×4 指 MPO 重排样式；未披露确定千路型号、逐路表、并发或出货量。 适合引用在固定重排的接口和产品形态一节。[原始论文或官方资料](https://www.corning.com/optical-communications/cala/en/home/products/shuffle-solutions.html)

### S11 Optical Shuffle Architectures for Large AI Networks

Jose M. Castro（Panduit）。2026。B 级。p.2–9、p.10–12、p.13–14。

展示玻璃组件；网络规模图为方案推导。PDF 完整并目视 p.13–14。IEEE 讨论稿，p.5–9、12 的网络容量属 D；玻璃实物和损耗定性比较未公开逐路测试。p.14 引用 S12。 适合引用在重排部署、直写候选和柔性电路损耗对照一节。[原始论文或官方资料](https://www.ieee802.org/3/ad_hoc/E4AI/public/26_0224/castro_e4ai_02_260224.pdf)

### S12 Photonic Chip with Embedded Data Center Fabric

Jose Castro、Bulent Kose、Robert Reid、Paul Huang、Brett Lane、Simon Gross、Michael Withford。2025。A 级。OFC W2A.36 摘要。

OFC 摘要报告 400 Gb/s 流量及器件表征。ABSTRACT_READ。Huang 名字在学术库与会议预告拼写不同，按正式论文引用时核其 PDF。论文未取全文，不能据流量速率定并发或路数。与 S11 相关，同一研发线索。 适合引用在三维直写玻璃的直接应用先例一节。[原始论文或官方资料](https://doi.org/10.1364/OFC.2025.W2A.36)

### S13 Concept Demonstration of 3D Waveguides Shuffle Converter for Multi-Core Fiber/Single-Mode Fiber Fan-in Fan-out Configuration Toward Over 1,000 Port Count

Haisong Jiang、Yasuhiro Hinokuma、Sampad Ghosh、Ryota Kuwahata、Kiichi Hamamoto。2021。A 级。IEICE E104.C(1), 34–36；摘要。

原理器件插损 2.1 dB、串扰低于 −54.2 dB（摘要）。ABSTRACT_READ。over 1000 是目标系统端口数，属 D；原型路数、并发、工艺、仿真规模、图号、测量条件 unknown。 适合引用在千端口应用设想及小规模验证边界一节。[原始论文或官方资料](https://doi.org/10.1587/transele.2020ECS6002)

### S14 Large-Scale Glass Waveguide Circuit for Board-Level Optical Interconnects Between Faceplate and Co-Packaged Optical Transceivers

Lars Brusberg、Betsy J. Johnson、Christian Herbst、Jason R. Grenier、Matthew J. Dejneka、Chad C. Terwilliger、Julian Schwietering、Henning Schröder。2025。A 级。ECTC pp.59–63；摘要；合作者出版清单。

报告已制作 420×255×0.7 mm 扇出光路板，传播损耗 0.1 dB/cm。ABSTRACT_READ（论文摘要副本）与机构书目，IEEE 落地页访问受限。低于 0.04 dB/cm 是该摘要提出的改进目标。逐路测试数、并发和量产待核，已公开拓扑为面板至 CPO 扇出。适合引用在千路玻璃实体规模一节。[原始论文](https://doi.org/10.1109/ECTC51687.2025.00016) · [ECTC 议程](https://ectc.net/wp-content/uploads/2025/06/75-ECTCFinal-Web.pdf) · [Fraunhofer IZM 成果清单](https://www.izm.fraunhofer.de/content/dam/izm/de/documents/Publikationen/Jahresberichte/ar-2026/IZM_AR2026_EN_web.pdf)

### S15 Optical Design and Applications for Ion-Exchanged Glass Waveguide Circuits

Lars Brusberg 等。2025。A 级。IEEE TCPMT 摘要。

IOX 优化波导传播损耗 0.034 dB/cm；CPO 实例另述。ABSTRACT_READ。千路样品的测试覆盖 unknown，0.034 dB/cm 仅归到所报告优化波导，未与 S14 同板或独立验证作等同。 适合引用在IOX 工艺方向、相同数量级一节。[原始论文或官方资料](https://doi.org/10.1109/TCPMT.2025.3526500)

### S16 Heterogeneous 2D/3D photonic integrated microsystems

S. J. Ben Yoo、Binbin Guan、Ryan P. Scott。2016。A 级。3D optical phased arrays；Fig. 7(a–c)。

256 通道 ULI 扇出，端面实物照片。FULLTEXT_LOCATED。16×16 是输出端面几何，光学同时激活数量 unknown。最小间距、等长和曲率是设计要求。 适合引用在真实三维直写阵列转换与约束一节。[原始论文或官方资料](https://doi.org/10.1038/micronano.2016.30)

### S17 Ultrafast laser processing of glass waveguide substrates for multi-fiber connectivity in co-packaged optics

Jason R. Grenier 等。2023。A 级。§2–4、Fig. 8–9。

可插拔多纤端面测量及多排直写截面样例。FULLTEXT_LOCATED。IOX、激光制对准槽和飞秒直写是不同工艺步骤。无千路实物或并发证据。 适合引用在连接与加工可制造性一节。[原始论文或官方资料](https://doi.org/10.3389/aot.2023.1244009)

### S18 Next Generation Multi-Fiber Ferrule Using 165 Micron Pitch Optical Fiber

Hirotaka Asada、Darrell Childers、Mike Hughes、Takaaki Ishikawa、Sharon Lutz、Dirk Schoellner、Kansei Shindo、Yasuyuki Wada。2021。A 级。§1.1 Fig. 1、端面几何和温循章节。

165 µm 插芯几何、接触和温循实验。FULLTEXT_LOCATED。1024 纤来自 51.2T 配置假设，属 D。实测对象是插芯。示例中 512 条全双工，不是千路玻璃。 适合引用在千纤需求具体推导与封装边界一节。[原始论文或官方资料](https://doi.org/10.1117/12.2578649)

### S19 HBM3E

Micron。未署年。B 级。High bandwidth 产品规格与 FAQ。

商用规格 1024 I/O，>9.2 Gb/s 每 pin。官方产品页。1024 为电 I/O 数，不用作光通道或端口计数。 适合引用在排除 HBM3E 电位宽误用一节。[原始论文或官方资料](https://www.micron.com/products/memory/hbm/hbm3e)

### S20 HBM4

Micron。未署年。B 级。Bandwidth performance 与 2048-bit interface。

2048 位，>11 Gb/s 每 pin。官方产品页。电接口升级不限定空间光导路。 适合引用在HBM4 口径与代际对比一节。[原始论文或官方资料](https://www.micron.com/products/memory/hbm/hbm4)

### S21 Intel Demonstrates First Fully Integrated Optical I/O Chiplet

Intel。2024。B 级。Newsroom PDF，演示及 BER 段。

CPU 原型 live data，约 4 Tb/s 双向。原型规格 B；单报告有眼图、光谱与 BER 测量。与 HBM 宽度无直接绑定；光纤可并发承载多个波长。 适合引用在串行化与波分复用的实例一节。[原始论文或官方资料](https://download.intel.com/newsroom/archive/2025/en-us-2024-06-26-intel-demonstrates-first-fully-integrated-optical-io-chiplet.pdf)

### S22 Hardware — NVIDIA DGX GB Rack Scale Systems User Guide

NVIDIA。未署年。B 级。Hardware 与 System Components。

NVL72 机架，72-GPU NVLink domain。官方硬件正文。机架内部 NVLink 铜缆；跨机架连接独立，需另查网卡和光预算。 适合引用在区分 GPU–HBM、GPU–GPU、scale-out一节。[原始论文或官方资料](https://docs.nvidia.com/dgx/dgxgb200-user-guide/hardware.html)

### S23 Optically Connected Multi-Stack HBM Modules for Large Language Model Training and Inference

Yanghui Ou、Hengrui Zhang、Austin Rovinski、David Wentzlaff、Christopher Batten。2025。C 级。§II–III、Fig. 2–6。

设计与性能仿真；物理链路未实测。FULLTEXT_LOCATED（Cornell 作者稿）。含 16 Tx、16 Rx、16 供光纤。带宽原文单位以参数复算。设计描述属 D，性能属 C。 适合引用在直接区分 1024 逻辑通道和空间数量一节。[原始论文或官方资料](https://doi.org/10.1109/LCA.2025.3540058)

### S24 Optically connected memory for disaggregated data centers

Jorge Gonzalez 等。2022。C 级。§3–4 Fig. 3；§6。

设备数据推算与系统仿真。FULLTEXT_LOCATED（机构全文）。同时访问能力依模型业务；非本地 GPU–HBM 玻璃样机。2020 预印本数值与正式版不同。 适合引用在光内存池化不直接产生千路光纤一节。[原始论文或官方资料](https://doi.org/10.1016/j.jpdc.2022.01.013)

### S25 OptoConnect Aggregation Fiber Shuffle Boxes

Molex。2023。B 级。p.1 Features and Advantages；p.2 Specifications。

可定制 1–6 RU。官方完整规格（印刷 Rev.6 2023.08）。容量范围不等于指定端口图、同时工作数、实际出货或一块玻璃。 适合引用在真实千纤机箱级规模一节。[原始论文或官方资料](https://www.molex.com/content/dam/molex/molex-dot-com/en_us/pdf/datasheets/987651-1657.pdf?inline=)

### S26 NVIDIA NVL72 GB200/GB300 Systems: InfiniBand and Ethernet Connectivity Solutions

Corning Optical Communications。2025。B 级。LAN-3481-AEN；Fig. 24–31。

每 spine 32 MPO 下联配置；大规模分层物料示例。工程指南相关章节。32 MPO=每 leaf 两个×16 leaf；MPO、trunk、光芯和逻辑链路分别计数。未给 1024 实体玻璃或单盒净表。 适合引用在机架与交换机配置怎样产生 32一节。[原始论文或官方资料](https://www.corning.com/catalog/coc/documents/application-engineering-notes/LAN-3481-AEN.pdf)

### S27 NVIDIA Spectrum-4 SN5000 2U Switch Systems Hardware User Manual

NVIDIA。未署年。B 级。Introduction、Table 1、Specifications。

SN5600 64×800G／128×400G／256×200G；51.2 Tb/s。官方手册。cage 与子端口为不同计数；网络拓扑和逐纤数量需相应光模块规范。 适合引用在反例与 ASIC 端口口径一节。[原始论文或官方资料](https://networking-docs.nvidia.com/sn5000hw/introduction)

### S28 Low-loss and polarization insensitive 32 × 4 optical switch for ROADM applications

Xiaotian Zhu、Xiang Wang、Yanlu Huang 等。2024。A 级。器件设计、Figure 1 与 fiber-to-fiber loss 图。

188 MZI、88 optical vias、618 crossings；制备并测量。FULLTEXT_LOCATED。单播无冲突同时 drop 最多 4，未把 express 计入；不支持 16×32 产品或 1024 玻璃路由。 适合引用在不对称调度有工程场景一节。[原始论文或官方资料](https://doi.org/10.1038/s41377-024-01456-8)

### S29 32×32 Strictly Non-Blocking Si-Wire Optical Switch on Ultra-Small Die of 11×25 mm²

Ken Tanizawa、Keijiro Suzuki 等。2015。B 级。OFC M2B.5 摘要。

1024 个热光 MZI 单元，芯片原型。ABSTRACT_READ。1024 个是可调开关，不是空间光纤。理论并发 32。后续 AIST 全路径结果另属逐路径测试。 适合引用在直接区分 1024 个 MZI一节。[原始论文或官方资料](https://doi.org/10.1364/OFC.2015.M2B.5)

### S30 Large-scale and nonblocking OXC using a hybrid of WSSs and OCSs

Dannan Hong、Tong Ye、Qiang Guo、Bofang Zheng、Zhiwu Chang、Ruishan Chen、Luo Han。2025。D 级。JOCN 17(9), 771–782；摘要。

理论分析与结构方案。ABSTRACT_READ。与 S01 共享研究团队和问题，架构替代证据。具体净表与样机并发 unknown。 适合引用在说明 N² 固定层的适用范围一节。[原始论文或官方资料](https://doi.org/10.1364/JOCN.566633)

### S31 Optical cross connect

Robert Verhagen、Willy Rietveld（Tyco Electronics Nederland BV）。2006。D 级。US7092592B2 Fig. 3、5–11；实施例说明。

Fig. 9 四托盘各四个 8×8 电路；另有 Fig. 3 4096 纤设计。全文及实图。图 9 目视核对四个托盘叠放及引出纤带。全组对固定转置实施例；32×32 条数 4×4×64。专利没有给生产或光学并发测试，介质为预制分段光纤。 适合引用在直接引用 32×32/1024 纤和模块数设计一节。[原始论文或官方资料](https://patents.google.com/patent/US7092592B2/en)

### S32 Connection management method for high degree optical cross-connect cluster node

Hamid Mehrvar（Huawei Technologies）。2026。D 级。US12568543B2 Fig. 1A–B、Fig. 3。

专利中的 32 槽背板与多个机箱连接实施例。全文。992 是单向空间线每有向对一根时的推导，实际从专利不能确认逐纤数量和并发。P32 同厂，未证实同型号。 适合引用在32×31 边界与 32-degree 组数一节。[原始论文或官方资料](https://patents.google.com/patent/US12568543B2/en)

### S33 Photonic Fabric Technology: How Optical Connectivity Enables the Next Generation of AI Infrastructure

Marvell。2026。B 级。Photonic Fabric Memory Module 和 PF-NIC。

厂商的内存池化产品说明给出每模块最多 8 个 DDR5 DIMM、72 GB HBM cache 和 7.2 Tb/s 光 fabric 带宽。官方正文未公开可逐根映射到 1024 路的空间纤、波导或并发光端点数。适合引用在远端共享内存与本地 HBM 的工程差别一节。[Marvell 技术说明](https://www.marvell.com/blogs/photonic-fabric-technology-optical-connectivity-ai-infrastructure.html)

## 关键证据的作用与下一步

| 主张 | 已形成的论证 | 会改变结论的证据 |
|---|---|---|
| 32 度可作为真实规模锚点 | S02 和 S03 是不同厂商应用与规格，S04 补足 WSS 部件口径 | 明确节点站型、业务槽配置和 WSS 型号 |
| 完整两级 WSS 的固定中间层有 1024 条 | S01 给出 N² 连接；S31 给出对应物理纤托盘方案；S32 提供可少对角项的架构例 | 厂商或公开样机的实际逐纤端口表、方向及保护配线 |
| 千路玻璃已有制作实例 | S14 明确报告 1024 波导。S15 与其属于有关联的 IOX 研发线。S11、S12 说明三维直写重排的工程可行性线索 | S14 全文与逐路测试页、三维直写单板的独立千路全测和良率 |
| 现有四边板是千路固定互连 | 本地端点、组对、奇环及验收文件支持 | 目标系统端口表与本地连接器身份的逐项对应。现有路由实验无需重跑 |
| HBM 电 I/O 数不直接确定光波导数 | S19、S20 产品位宽，S21 的 DWDM 原型和 S23 的光 HBM 模型给出分层计数 | 具体产品逐路光净表和明确空间通道数 |
