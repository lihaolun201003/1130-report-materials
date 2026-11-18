# L6 物理高度组合圆弧 ON/OFF 中文对比图（专利版）

本目录只包含 **L6 物理高度（plane 6，z = −0.125 mm）** 的中文对比图，不改动原有英文图。

## 数据来源（原始实验，未重跑优化）

| 面板 | 实验组 | 运行目录 | 全层交叉 |
|---|---|---|---:|
| 左：启用组合圆弧 | ON，seed 20261116 | `runs/on/c1_on_20261116/best_valid` | 2093 |
| 右：禁用组合圆弧 | OFF，seed 20261130 | `runs/off/c1_off_20261130/best_valid` | 4052 |

L6 本层交叉（从各自 `crossing_stats.json` 读取并由 `plots21.compute_all_plane_crossings`
独立复算核对，见 `data_check.json`）：

* 启用组合圆弧：**108 次交叉 / 99 对交叉线路 / 41 条本层布线**
* 禁用组合圆弧：**399 次交叉 / 276 对交叉线路 / 44 条本层布线**
* 差值：**+291 次**

## 文件

* `L6_combo_arc_ON_vs_OFF_zh.png` — 300 dpi
* `L6_combo_arc_ON_vs_OFF_zh.svg` — 文字已转为路径，避免字体缺失
* `data_check.json` — 源状态 SHA256、L6 计数、数据核对结果、图内标注清单
* `README.md` — 本文件

## 复现命令

```powershell
cd "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D"
.venv\Scripts\python.exe experiments\20H_G4_MULTI_ARC_ABLATION_1024\tools\plots_ablation_zh.py
```

脚本是独立中文入口，不改变 `plots_ablation.py` 的英文图生成逻辑；只读取真实
`routes_l3d.json` / `crossing_stats.json`，不运行优化、不改实验数据、验证器或其他图件。

## 图中中文标注

* 图题：20 层 1024 通道组合圆弧消融：物理高度 L6 布线对比
* 左右标题：启用组合圆弧 / 禁用组合圆弧
* 面板副标题：物理高度 L6、z 值、本层布线条数、交叉次数/对数
* 坐标轴：x 坐标 (mm)、y 坐标 (mm)（单位保留）
* 图例：人工 U 组、Z1 其余对侧线路、Z2 其余相邻侧线路、接口直连本体（本层布线）、
  冻结接口引出线（其他线路）、端口及内向刻度、交叉点（真实几何）
* 底部说明：同板面、同坐标范围与比例，红色 × 为真实交叉点，数值来源说明

两面板使用相同的 0–150 mm 坐标范围、`equal` 纵横比与相同绘图尺度。
