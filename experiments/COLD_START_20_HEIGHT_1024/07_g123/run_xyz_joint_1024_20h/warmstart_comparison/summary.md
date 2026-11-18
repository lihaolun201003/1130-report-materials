# Warm-start 对比链（G2a → G2b → G3）

| 步骤 | 返回码 | 用时 min | 起点交叉 | 终点交叉 |
|---|---:|---:|---:|---:|
| G2a | 0 | 7.3 | 1485 | 1440 |
| G2b | 0 | 7.1 | 1440 | 1409 |
| G3 | 0 | 9.0 | 1409 | 1395 |

说明：G2a/G2b 使用 `manual_policy=height_only`，G3 使用 `fully_optimizable`；每个阶段都保存了独立的 routes/assignment/crossing_stats/validation 与 SHA256。