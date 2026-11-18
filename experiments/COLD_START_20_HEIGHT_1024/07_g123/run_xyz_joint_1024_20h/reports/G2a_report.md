# G2a 实验报告

目录：`C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\experiments\COLD_START_20_HEIGHT_1024\07_g123\run_xyz_joint_1024_20h\G2a_manual_group_reheight`

## 结果

| 指标 | 数值 |
|---|---:|
| 布通 | 1024 |
| 同层交叉 | 1440 |
| 唯一交叉线路对 | 1377 |
| 最大单通道交叉 | 20 |
| 改动线路 | 193（人工 0 / 非人工 193）|
| XY 主体改变 / 高度改变 | 193 / 93 |
| 中途换层总数 | 96 |
| 总路径长度 mm | 156641.083974 |
| 最小 3D 净空 mm | 0.06594987 |
| 几何违规 | 0 |
| 独立 Validator | PASS (policy=height_only) |

## 优化历史

- 接受改动：16 次
- 总收益：45 次交叉
- 单次最大收益：14，平均收益：2.812
- 主要换层迁移：{"6->6": 5, "7->7": 3, "17->10": 2, "20->20": 2, "10->12": 1, "7->10": 1, "1002->16": 1, "12->12": 1}

## 人工 U 改动

详见 `manual_group_reheight.json`。
