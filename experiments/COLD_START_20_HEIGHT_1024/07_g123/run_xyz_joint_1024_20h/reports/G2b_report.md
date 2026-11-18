# G2b 实验报告

目录：`C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\experiments\COLD_START_20_HEIGHT_1024\07_g123\run_xyz_joint_1024_20h\G2b_manual_route_reheight`

## 结果

| 指标 | 数值 |
|---|---:|
| 布通 | 1024 |
| 同层交叉 | 1409 |
| 唯一交叉线路对 | 1328 |
| 最大单通道交叉 | 20 |
| 改动线路 | 245（人工 49 / 非人工 196）|
| XY 主体改变 / 高度改变 | 196 / 145 |
| 中途换层总数 | 96 |
| 总路径长度 mm | 156721.115887 |
| 最小 3D 净空 mm | 0.06221256 |
| 几何违规 | 0 |
| 独立 Validator | PASS (policy=height_only) |

## 优化历史

- 接受改动：6 次
- 总收益：19 次交叉
- 单次最大收益：5，平均收益：3.167
- 主要换层迁移：{"6->2": 2, "6->6": 2, "17->10": 1, "1002->10": 1}

## 人工 U 改动

详见 `manual_route_reheight.json`。
