# CTP-2.0 — Literature-Grounded, Multi-Method Validated Full-Board Crosstalk Prediction

20 层 / 1283 次同层交叉 / 1024 通道三维玻璃光波导，全板光学串扰预测。

* **输入（只读，SHA256 校验）**：`../COLD_START_20_HEIGHT_1024/10_best_valid/`
* **上一版（只读，未修改）**：`../CROSSTALK_PREDICTION_20H_1283_1024/`（CTP-1.0）
* **主报告**：[`reports/CTP2_REPORT.md`](reports/CTP2_REPORT.md)
* **方法对照与适用边界**：[`docs/method_comparison.md`](docs/method_comparison.md)
* **CTP-1.0 源码审计**：[`audit/ctp1_code_audit.md`](audit/ctp1_code_audit.md)、[`audit/ctp1_anomaly_reproduction.md`](audit/ctp1_anomaly_reproduction.md)
* **新旧定量差异**：[`audit/ctp1_vs_ctp2.md`](audit/ctp1_vs_ctp2.md)
* **文献调研**：[`docs/literature_review.md`](docs/literature_review.md)（29 条来源 / 11 篇全文）、[`docs/literature_matrix.csv`](docs/literature_matrix.csv)、[`benchmarks/literature_benchmarks.csv`](benchmarks/literature_benchmarks.csv)（49 行数值基准）

## 头条结果

| 指标 | CTP-1.0 | **CTP-2.0** |
|---|---:|---:|
| 最坏单对端口串扰 | −65.91 dB | **−15.22 dB**（R723 → R743，5.154° 交叉） |
| 最坏单路总泄漏 | −58.38 dB | **−14.79 dB**（R743） |
| 多输入 干扰/信号 最坏 | −57.49 dB | **−12.50 dB** |
| 跨层/平行近邻累积耦合 | 未计算 | **≤ 1.67×10⁻¹⁸**（上界 1.83×10⁻¹⁵） |

风险集中在 **17 次 <10°** 的交叉（单点 −14…−30 dB）；1174 次 ≥20° 的交叉单点 < −63 dB、对全板无贡献。5.154° 的 3.6 % 耦合与文献（silica X 型耦合器 5° 实测 1.9 %）在 3 dB 内一致。

## 目录

```
config/simulation_config.yaml   全部参数、冻结规则、方法有效域
src/ctp2/                       CTP-2.0 求解与装配代码（params/geometry/optics/coupling/crossing/bpm/fdfd2d）
src/fullwave/                   独立时域全波求解器（2-D / 3-D FDTD）
scripts/                        run_v1 ... run_v6 + run_board + make_figures + run_sensitivity
outputs/modes|coupling|crossings|board|figures|fullwave
audit/                          CTP-1.0 审计、异常复现、新旧差异
docs/                           文献综述、方法对照
benchmarks/                     文献数值基准
tests/test_ctp2.py              验收自检（冻结值、物理一致性、交付物）
cache/                          可再生中间结果（不入库）
```

## 复现

```powershell
python scripts\run_v1_modes.py           # V1 单波导模式
python scripts\run_v2_coupling.py        # V2 平行耦合数据库
python scripts\run_v3_crossings.py       # V3/V4 交叉核数据库（含 3-D BPM 缓存）
python scripts\run_v5_near_approaches.py # V5 跨层/非交叉近邻
python scripts\run_v6_multimode.py       # V6 多模 S 矩阵
python scripts\run_sensitivity.py        # 参数敏感性
python scripts\run_board_ctp2.py         # 1024×1024 全板矩阵
python scripts\make_figures.py           # 20 张图
python tests\test_ctp2.py                # 验收自检
```

依赖：Python 3.10+、NumPy、SciPy、pandas、Matplotlib。总计算量在本机（i9-13900HX / 16 GB / RTX 4060）约 25 分钟（不含独立全波子代理的 2-D/3-D FDTD 扫描）。

## 诚实声明

* 10–30° 区间的绝对串扰**没有**收敛到唯一数字；Born 与 BPM-地板相差 1–17 dB，已逐角度给出上下界并标记 `status`。
* 全部结果是**理想结构**（无侧壁粗糙度、无折射率漂移、无应力双折射）的预测；文献表明大角度实测串扰由这些因素主导。
* 全板矩阵是「基模激励 + 基模检测」工况；多模转换只做了 5°/10°/20° 的代表性案例。
* 文献 A（Adikan 2006）与文献 B（Hammer 2017）全文未获取；HCMT 未按原文实现，本文实现并验证的是标准 CMT 重叠积分与任意方向 Born 积分。
