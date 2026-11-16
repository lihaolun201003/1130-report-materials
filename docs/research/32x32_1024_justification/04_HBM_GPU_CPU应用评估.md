# HBM、GPU 与 CPU 应用评估

目前未找到能够直接证明该需求的证据。这里的“该需求”指计算芯片或 HBM 必须通过同一块三维玻璃板上的 1024 条独立物理波导相连。数据中心网络和 CPO 仍可给高密度固定互连提供应用背景，相关链路的位置、粒度及数量必须单独确定。

## 同样的数值在不同接口统计什么

| 对象 | 可核实的实现与数量 | 证据性质 | 与毕业设计的关系 |
|---|---|---|---|
| HBM3E | Micron 给出每栈 1024 个 I/O、超过 9.2 Gb/s 每引脚、超过 1.2 TB/s 总带宽。乘积 1024×9.2/8≈1178 GB/s，量级对应带宽口径 | 产品规格 B | 1024 是电数据总线宽度。HBM3 家族以并行电 PHY 和微凸点接入处理器封装 |
| HBM4 | Micron 给出 2048 位总线、每引脚大于 11 Gb/s、每栈带宽超过 2.8 TB/s | 产品规格 B | 接口世代升级会改变电位宽。并行电位宽不能直接指定光空间通路数 |
| GB200／GB300 NVL72 | GB200 的 72 个 GPU 使用 NVLink Switch 系统，机架内使用无源铜缆背板。对外 scale-out 仍有网络接口和光连接部署场景 | NVIDIA 整机规格与硬件说明 B | GPU–HBM、本机架 GPU–GPU、跨机架网络是三个不同接口 |
| Intel OCI | CPU 共封装原型在 OFC 运行数据。每方向 64×32 Gb/s，8 对光纤，每根信号纤 8 个 DWDM 波长，即 8 根 Tx 和 8 根 Rx，每方向 2.048 Tb/s，厂家约记双向 4 Tb/s | 原型演示 B，BER／眼图示例 A | 64 是每方向波长承载通道总数，物理信号纤每方向为 8 |
| Ou 等，多栈光连 HBM | Fig. 2–4 的设计中每 EIC/PIC 对有 16 个光通道，每通道 3 根纤，分为 Tx、Rx、未调制梳状供光，合计 48 根。每根信号纤 64 个波长，故每方向有 1024 个波长承载实例 | 方案 D、系统性能模型 C | 直接对照同一系统里的 1024 个波长实例与 48 根空间纤。论文的系统模型不能作为实测模块证明 |
| 分离式主存 OCM | Gonzalez 等讨论由串并转换和微环 WDM 承载的 DDR 内存访问。原文报告四个 DDR4 通道由两根纤连接的模型，给出能耗和性能估计 | 架构 D、建模 C | 池化是远端内存访问机制。介质数量由实现的 PHY、光预算和拓扑算出 |

[Micron HBM3E][S19] · [Micron HBM4][S20] · [NVIDIA 机架硬件][S22] · [Intel OCI][S21] · [Ou 等 §II–III][S23] · [OCM §3–4、§6][S24]

Ou 等的作者稿 §II 段落有一处写单信号纤约 1 Tb/s，图 3 显示配对单元约 2 TB/s。按参数 (64×16) Gb/s = 1.024 Tb/s/信号纤，16 根信号纤是约 16.384 Tb/s = 2.048 TB/s·方向⁻¹。报告引用明确的物理纤和波长数，区分计算换算与原文单位。六个独立 EIC/PIC 对若都采用同样净表，推导为 288 根纤段（含供光）；实际器件状态属提案。[Ou 等，Fig. 2–4][S23]

## 数量推导应该从带宽与空间接口同时开始

单方向的有效带宽为 B，每空间路径承载 W 个波长，每波长线速为 R，有效载荷比例为 η。在均匀、无冗余的模型中，空间路径下界为 ⌈B/(W×R×η)⌉。独立的 Tx、Rx、光源、保护和监测光路应按系统平面分别相加。功耗、延迟、BER、频谱间隔、每波长激光预算、同频路由争用和纤端可用位置可能提高实际数量。

Marvell 的 Photonic Fabric Memory Module 把共享 DDR5、72 GB HBM 缓存和每模块 7.2 Tb/s 光 fabric 集成在产品方案中，另以支持 CXL 3.1 与 PCIe 6 的 PF-NIC 接入共享内存。厂商公开说明可支持“光接口连接内存池”的工程方向，物理介质类型、空间通道数和逐路净表未公开到足以换算成 1024 条波导。[Marvell 光内存方案][S33]

## 有哪些不同的千路案例

Asada 等在 51.2 Tb/s、radix 512、100G 每纤的收发分纤示例下，给出 1024 根实体纤的封装压力，讨论 16 个 3.2T 或 8 个 6.4T 光 tile。Fig. 1 是架构分解。论文的实测对象是窄间距插芯的接触、几何和温循，千路不等于整套设备已经量产。Corning/Fraunhofer 的 ECTC 论文则在另一项 CPO 系统背景下报告了 1024 路玻璃扇出板的制备。这两项是“千条物理光路有工程来源”的证据，均属于交换 ASIC 到面板的光 I/O 或封装连接，不能归因于 HBM 电总线。[Asada §1.1、Fig. 1][S18] · [Brusberg 等 ECTC][S14]

可用于绪论的主线是短距固定空间重排与机箱内部光纤管理。CPU/GPU 光 I/O、远端内存和跨机架交换适合说明系统的带宽与封装趋势。与 HBM 直接连接的主张留待出现明确的光端口分配、独立净线和实物测量。

[S14]: https://doi.org/10.1109/ECTC51687.2025.00016
[S18]: https://doi.org/10.1117/12.2578649
[S19]: https://www.micron.com/products/memory/hbm/hbm3e
[S20]: https://www.micron.com/products/memory/hbm/hbm4
[S21]: https://download.intel.com/newsroom/archive/2025/en-us-2024-06-26-intel-demonstrates-first-fully-integrated-optical-io-chiplet.pdf
[S22]: https://docs.nvidia.com/dgx/dgxgb200-user-guide/hardware.html
[S23]: https://doi.org/10.1109/LCA.2025.3540058
[S24]: https://doi.org/10.1016/j.jpdc.2022.01.013

[S33]: https://www.marvell.com/blogs/photonic-fabric-technology-optical-connectivity-ai-infrastructure.html
