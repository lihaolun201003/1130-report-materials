# 11 月 30 日汇报材料｜1024 路三维光波导布线

本仓库汇总毕业设计「面向 1024 通道高密度光互连的三维光波导自动布线系统」的应用调研、布线与光学仿真实验，以及专利文稿。课题研究的是如何在给定的玻璃板尺寸、端点和几何约束下，自动完成 1024 条固定光路。

## 为什么做 1024 路

- **CPO 机箱内配线是主要应用线索。** 光引擎移到交换芯片周围后，前面板与光引擎之间需要在机箱内走光纤。一种 51.2T 并行、收发分纤参考设计使用 512 根发送纤和 512 根接收纤，另有 128 根激光供光纤。康宁也公开了从前面板通往中央 CPO 区域的 1024 路平面玻璃波导设计。[应用需求线索](docs/research/32x32_1024_justification/应用需求线索.md) · [研究报告](docs/research/32x32_1024_justification/研究报告.md)
- **电信 OXC 是另一种千路配线场景。** 32 个输入 WSS 组和 32 个输出组之间，每对保留一条固定纤时，共有 1024 根组间纤。如果省去全部 32 条同编号回接支路，保留 992 根。[32×32 连接拓扑](docs/research/32x32_1024_justification/03_为什么是32x32.md)
- **项目用四边板检验这个规模下的布线。** 150 × 150 mm 板上有 64 个双排连接器，2048 个芯位两两配成 1024 条固定路线。当前净表用于检验整板拥塞、深度分配和几何可行性。对接具体机箱时，需要采用设备的芯位表、连接表和装配边界。[四边板连接表核查](docs/research/32x32_1024_justification/05_现有1024连接表适配分析.md)

[调研目录](docs/research/32x32_1024_justification/) · [全文证据矩阵](docs/research/32x32_1024_justification/证据矩阵_全文复核.csv) · [参考文献与引文追踪](docs/research/32x32_1024_justification/参考文献与引文追踪.md)

## 20 层布线实验

下表各阶段均完成 1024 路布线。同层交叉总数和小于 45° 的交叉数是两个指标。G6 首次满足 45° 硬约束，G7 在保持该约束与固定层分配的情况下继续减少交叉。

| 阶段 | 同层交叉次数 | 小于 45° | 说明 |
| --- | ---: | ---: | --- |
| G4 基线 | 1283 | 304 | 20 层从零重建，原几何验证通过。[报告](experiments/COLD_START_20_HEIGHT_1024/12_reports/EXPERIMENT_REPORT.md) · [复现](experiments/COLD_START_20_HEIGHT_1024/12_reports/REPRODUCTION.md) |
| G5 局部优化 | 4136 | 51 | 小角度交叉减少，仍有 51 处未满足角度约束。[报告](experiments/G5_ANGLE45_NATIVE3D_20H_1024/07_reports/G5_REPORT.md) |
| G6 联合退火 | 4578 | 0 | 原几何验证和独立角度验证均通过。[报告](experiments/G6_ANGLE45_MULTIARC_SA_20H_1024/06_reports/G6_REPORT.md) · [复现](experiments/G6_ANGLE45_MULTIARC_SA_20H_1024/REPRODUCTION.md) |
| G7 固定层优化 | 4353 | 0 | 比 G6 减少 225 次交叉，固定结构验证也通过。[报告](experiments/G7_FIXED_LAYER_MULTIARC_CROSSING_OPT_1024/06_reports/G7_REPORT.md) · [复现](experiments/G7_FIXED_LAYER_MULTIARC_CROSSING_OPT_1024/REPRODUCTION.md) |

## 多圆弧消融与串扰仿真

| 材料 | 结果与阅读入口 |
| --- | --- |
| 多圆弧消融 | 在 20 层、共同起点、等候选评价预算和 3 个随机种子的实验里，开启多圆弧后平均交叉事件从 4064.0 降至 2126.3。[20 层正式报告](experiments/20H_G4_MULTI_ARC_ABLATION_FINAL_1024/EXPERIMENT_REPORT.md) · [21 层对照](experiments/G4_MULTI_ARC_ABLATION_FINAL_1024/report.md) · [早期实验归档](G4_MULTI_ARC_ABLATION_1024/report.md) |
| CTP-2.0 串扰重算 | 对 **G4 的 20 层、1283 次交叉解**建模，名义预测最坏单对串扰为 −15.21 dB。结果用于定位小角度交叉风险，数据来源为数值仿真。[CTP-2.0 主报告](experiments/CROSSTALK_PREDICTION_CTP2_20H_1283_1024/reports/CTP2_REPORT.md) · [全波验证](experiments/CROSSTALK_PREDICTION_CTP2_20H_1283_1024/reports/FULLWAVE_VALIDATION.md) · [CTP-1.0 差异审计](experiments/CROSSTALK_PREDICTION_CTP2_20H_1283_1024/audit/ctp1_vs_ctp2.md) |

## 专利材料

- [1024 路三维布线技术交底](专利/1024三维布线技术交底/)
- [交叉冲突图、模拟退火与三维高度分配](专利/交叉冲突图_模拟退火_三维高度分配_正式重写版/)
- [多圆弧光波导优化布线](专利/多圆弧光波导优化布线专利/)
