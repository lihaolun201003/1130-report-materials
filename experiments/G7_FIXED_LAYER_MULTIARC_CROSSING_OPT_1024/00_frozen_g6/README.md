# 00_frozen_g6 — 冻结的 G6 合法基线（只读）

本目录是 G7 的唯一输入，所有内容均从 G6 实验交付物复制而来，**不得修改**。

| 文件 | 说明 |
|---|---|
| `routes_l3d.json` | G6 最终合法解（20 高度、1024/1024、4578 次同层交叉、0 次 <45°）。SHA256 = `39a02c9ec9a598d95bb2a6ef6695ab18a849c037fa9ca24c2a76581c55bc57b2` |
| `BEST_VALID.json` | G6 交付索引（payload SHA256、验收结论、统计） |
| `SHA256.json` | G6 交付文件哈希清单 |
| `g6_validation_verdict.json` | G6 的 Validator A + Validator B 综合验收结论 |
| `assignment_1024.csv` 等 | G6 的物理层/规则/分配附属文件（仅作验证器输入） |
| `frozen_manifest.json` | **G7 冻结清单**：从 `routes_l3d.json` 逐线路提取的真实高度、part 种类序列、全部非主体几何签名、端口与 `layer_sequence`；1024 条中 527 条可修改（主体 MultiArc），92 direct / 368 人工 U / 37 native-3D 完全冻结 |
| `g6_baseline.json` | 基线统计摘要（含“忽略旧 assignment CSV 中 134 行高度偏差”的说明） |

## 为什么不用 assignment CSV 的高度

G6 的旧 assignment CSV 与最终 `routes_l3d.json` 的真实高度存在 134 行不一致
（G6 polish 阶段改写过部分线路结构）。G7 的固定层契约必须以**实际交付几何**为准，
因此 `frozen_manifest.json` 完全从 `routes_l3d.json` 生成；CSV 只用于让冻结验证器
（Validator A）完成其原有的附属文件检查。

## 固定性验证

```powershell
& $PY -m four_side_1024.fanout1024.xyzrouter.g7.verify_fixed `
  --reference 00_frozen_g6/routes_l3d.json `
  --candidate 03_best_valid/routes_l3d.json `
  --out 04_validation/fixed_structure
```

验证器逐字段比较每条线路：part 种类序列、过渡参数、引出直线、native-3D part、
真实主体高度、layer 序列、`n_transitions`、起点/终点高度。只有 527 条可修改线路的
第 3 个 part（主体 flat）允许不同。
