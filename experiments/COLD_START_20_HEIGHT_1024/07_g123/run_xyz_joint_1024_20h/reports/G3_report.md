# G3 实验报告

目录：`C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\experiments\COLD_START_20_HEIGHT_1024\07_g123\run_xyz_joint_1024_20h\G3_manual_full_xyz`

## 结果

| 指标 | 数值 |
|---|---:|
| 布通 | 1024 |
| 同层交叉 | 1395 |
| 唯一交叉线路对 | 1325 |
| 最大单通道交叉 | 20 |
| 改动线路 | 248（人工 49 / 非人工 199）|
| XY 主体改变 / 高度改变 | 202 / 145 |
| 中途换层总数 | 90 |
| 总路径长度 mm | 156735.565905 |
| 最小 3D 净空 mm | 0.06221256 |
| 几何违规 | 0 |
| 独立 Validator | PASS (policy=fully_optimizable) |

## 优化历史

- 接受改动：7 次
- 总收益：14 次交叉
- 单次最大收益：3，平均收益：2.0
- 主要换层迁移：{"16->11": 2, "15->1002": 1, "8->2": 1, "7->2": 1, "1001->1001": 1, "7->7": 1}

## 人工 U 改动

详见 `manual_u_changes.json`。
