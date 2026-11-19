# CROSSTALK_PREDICTION_20H_1283_1024

1024 通道三维玻璃光波导全板光学串扰预测（模型版本 **CTP-1.0**）。

输入是 `experiments/COLD_START_20_HEIGHT_1024/10_best_valid/` 中的冻结最终解
（20 个物理高度、1283 次合法同层交叉、1024 条真实 XYZ 路线，
`routes_l3d.json` SHA256 = `35d7ebed…b90753`）。本目录**只读**该输入，不修改原路由。

## 快速开始

依赖：Python 3.10+、NumPy、SciPy、Pandas、Matplotlib（无需商业电磁软件）。
在本目录下执行：

```powershell
python scripts\run_e1.py        # 几何解析 + 真实长度 + 0.05 dB/cm 传播损耗
python scripts\run_e2.py        # 单波导标量模式 + 收敛
python scripts\run_e3.py        # 双波导耦合数据库 + 交叉角-串扰曲线
python scripts\run_e4.py        # 1024 路三维相互作用（交叉 + 近邻）
python scripts\run_e5.py        # 1024×1024 全板串扰矩阵
python scripts\run_e6.py        # 参数敏感性
python scripts\make_figures.py  # 全部图
python scripts\run_manifest.py  # 哈希 / 运行环境清单
python scripts\run_report.py    # 中文报告
python tests\test_pipeline.py   # 数值一致性检查
```

`run_e3.py` 含 17 个角度的局部二维 FDFD 求解，是唯一耗时较长的步骤（本机约 7 分钟）；
其余步骤均在秒级到数分钟。`cache/` 为可再生的中间结果，未纳入版本库。

## 目录

| 路径 | 内容 |
|---|---|
| `config/simulation_config.yaml` | 全部参数、单位、假设、模型版本 |
| `src/geom3d.py` | line / arc / transition 解析曲线，弧长参数化 |
| `src/modes.py` | 标量弱导模式求解（均匀网格 + 分级大域） |
| `src/coupling.py` | 超模分裂 + 重叠积分 κ(d) |
| `src/crossing.py` | 交叉的二维 FDFD 散射求解 + CMT/Born 对照 |
| `src/interactions.py` | 解析求交 + KD-tree 近邻 + 精确最小距离 |
| `src/board.py` | 1024×1024 传输矩阵组装 |
| `src/lengths.py` | 长度分解与传播损耗 |
| `src/figures.py` | 14 张报告级图 |
| `src/report.py` | 报告生成 |
| `outputs/` | 全部结果、图、清单 |
| `reports/SIMULATION_REPORT.md` | 完整中文报告 |
| `tests/` | 数值/数据一致性检查 |

## 关键约定

* 长度单位 mm，波长 nm，损耗 dB/cm，串扰 dB（10·log10 功率比）。
* `T[j,i]`：第 i 列 = 输入端口 i（source 端），第 j 行 = 输出端口 j（target 端）。
* 传播损耗统一 **0.05 dB/cm**，R15 额外弯曲损耗 **0 dB**，但弯曲弧长计入普通损耗。
* 几何 `waveguide_width_mm = 0.05` **不**作为光学芯区尺寸；光学芯区独立配置。
* 标量弱导近似，不是全矢量 Maxwell 求解；交叉局部模型为 EIM + 二维 FDFD。
* 交叉串扰低于 ~1e-7 的模型分辨率下限时，以“≤1e-7”保守上界报告，不伪造精确值。

## 主要结论（详见报告）

1. 1024 条路线真实弧长合计 156 597.221 522 mm（误差 3.4×10⁻⁷ mm）。
2. 参考截面 9×9 µm / Δn=0.0065 / 1310 nm 支持 **3 个导模**，不是单模。
3. 独立解析求交完整复现 1283 次交叉 / 1221 对 / 647 条线路。
4. 非交叉最小三维净距 62.2 µm；该间距下 κ ≲ 5×10⁻¹⁴ mm⁻¹，并行耦合可忽略。
5. 交叉的局部 FDFD 串扰在所有角度均低于 −70 dB。
6. 全板最坏非对角串扰为 −5x dB 量级，列功率和 ≤ 1。
7. 几何交叉次数不是光学串扰的有效代理量；该方案的串扰预算非常宽裕。
