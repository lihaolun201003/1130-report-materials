# 11 月 30 日汇报材料

本仓库汇总毕业设计「面向 1024 通道高密度光互连的三维光波导自动布线系统」的应用调研、G4 多圆弧消融实验和专利材料。

## 材料导航

| 内容 | 阅读入口 | 主要问题 |
| --- | --- | --- |
| 32×32 光互连与 1024 通道选型 | [调研首页](docs/research/32x32_1024_justification/README.md) · [规模论证](docs/research/32x32_1024_justification/03_为什么是32x32.md) | 哪种光交换架构会产生 1024 条固定连接，现有四边板如何与该架构对照 |
| 绪论与答辩 | [论文背景与三版答辩口径](docs/research/32x32_1024_justification/06_本科毕业论文应用背景建议.md) · [参考文献](docs/research/32x32_1024_justification/references.md) · [证据矩阵](docs/research/32x32_1024_justification/evidence_matrix.csv) | 如何说明选型依据，如何区分产品规格、原型和推导 |
| G4 多圆弧消融 | [实验报告](G4_MULTI_ARC_ABLATION_1024/report.md) · [分层与热点图](G4_MULTI_ARC_ABLATION_1024/layer_figures) · [运行说明](G4_MULTI_ARC_ABLATION_1024/RUNBOOK.md) | 在给定模型下，关闭平面组合圆弧后，交叉、长度与几何验收怎样变化 |
| 专利材料 | [三维布线技术交底](专利/1024三维布线技术交底) · [交叉冲突图与高度分配](专利/交叉冲突图_模拟退火_三维高度分配_正式重写版) · [多圆弧光波导布线](专利/多圆弧光波导优化布线专利) | 查阅技术交底、权利要求书、说明书和附图 |
| 20 层从零重建实验（2026-11-18） | [实验报告](experiments/COLD_START_20_HEIGHT_1024/12_reports/EXPERIMENT_REPORT.md) · [最终合法解与校验](experiments/COLD_START_20_HEIGHT_1024/10_best_valid/BEST_VALID.json) · [阶段曲线与图件](experiments/COLD_START_20_HEIGHT_1024/11_figures/final) · [复现命令](experiments/COLD_START_20_HEIGHT_1024/12_reports/REPRODUCTION.md) | 删除 L19、全部高度 +25 µm 后从零重做退火/多圆弧/Native-3D/G4：1024/1024 合法布通，1283 次交叉（21 层 1185 的 +8.3%），多圆弧受控消融 −13.3% |

## 汇报摘要

- **应用规模。** 32-degree ROADM 有公开产品依据。两级 WSS 若为每对输入、输出组各设置一条固定空间光路，完整的 32×32 配置需要 1024 条链路。实际设备的数量取决于端口表和是否允许回送。现有四边板含 1024 条固定端点连接，标准转置 Shuffle 可作为独立基准。[选型分析](docs/research/32x32_1024_justification/03_为什么是32x32.md) · [连接表核查](docs/research/32x32_1024_justification/05_现有1024连接表适配分析.md)
- **实验结果。** G4 消融实验的多圆弧开启组与关闭组均布通 1024 路并通过几何验收。开启组重跑记录 1202 次交叉事件，关闭组记录 3484 次。报告第 4、6 节分解了继承路径转换、后续搜索和提前停止对结果的影响。[消融实验报告](G4_MULTI_ARC_ABLATION_1024/report.md)

[答辩口径](docs/research/32x32_1024_justification/06_本科毕业论文应用背景建议.md) 包含 30 秒、2 分钟和详细三版。
