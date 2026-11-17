# G4_CODE_RECOVERY_AUDIT — 目录说明

本目录是 **1185 交叉的原始 G4 代码基线的恢复与审计**工作区。
正式报告：**[`G4_CODE_RECOVERY_AUDIT.md`](G4_CODE_RECOVERY_AUDIT.md)**。

> 主工程 `OpticalWaveguideRouter2D` **未被修改**。完整备份在
> `work/_backups/OpticalWaveguideRouter2D_20261117_1118/`（36 783 文件 / 6.617 GB，
> 0 failed，逐文件 SHA256 见 `work/_backups/BACKUP_SHA256_20261117_1118.csv`）。

## 目录

| 路径 | 内容 |
|---|---|
| `G4_CODE_RECOVERY_AUDIT.md` | **正式审计报告**（出处 / 逐文件差异 / 回归判定 / 独立验证 / 恢复工程 / 回退建议） |
| `trusted_08_code/` | 从 `11.9-second-report-all-work @ 833a009b411c` 提取的 `g4_xyz_joint_1024/08_code/`（25 条目，自校验 25/25） |
| `audit_g4/` | `summary.json`、`file_table.csv`、`diffs/*.diff`、`signatures.json`、`settings.json`、`chain_provenance.json` |
| `audit_g3_start.json` | 恢复工程里 G3 起点的独立复算（`711cf910…` / 1322 / 197 条多圆弧） |
| `audit_1185.json` + `audit_1185_per_route.csv` | 1185 归档解的独立几何复算（1185 / 1124 / 202 条线路 / 208 区域） |
| `validation_1185_original_code/` | 用**恢复出来的原始代码**的冻结 Validator 对 1185 的验收（PASS / 0 violations） |
| `recovered_G4_1185/` | **隔离恢复工程**：原始 g4（24 文件）+ 原始 `layer2d.py`（`d0de64e3…`）+ 原始 `local_reroute.py`（`3daa0d8d…`）+ G3 依赖数据 |
| `probe_current_code/` | 同一恢复工程 + **当前主工程**的 8 个文件，用于"新旧代码同条件对撞" |
| `runs/G4b_repro_1200s/` | 复现探针 1（原始代码）：1322 → **1294**，`best_valid` 与归档 `c72b245a…` **逐字节相同** |
| `runs/G4b_current_code_1200s/` | 复现探针 2（当前代码）：见报告 §8.2 |
| `staging/` | 从可信提交提取的 1185 工件、链段文档、`git archive` 中间件 |
| `tools/` | `audit_g4_recovery.py`（逐文件差异）、`extract_chain_provenance.py`（链谱系） |

## 三分钟版本

1. `833a009b` 的 `08_code/g4` 自校验 25/25；当前 g4 与之相比 **18 同 / 6 改 / 0 删 / 0 增**。
2. 6 个改动 = 最新等预算实验，`+176/−13`，**13 行删除全是签名与元数据**，无算法删除。
3. 另外两处改动 = 1130 多圆弧开关（`layer2d.py +112/−0`、`local_reroute.py +1/−0`），**纯增量**；
   其 `.orig` 经归一化后与归档中一份真实提交的 `layer2d.py` **哈希相同**。
4. 全包 452 个 `.py` 中只有这 8 个在 2026-11-04 之后被改动。
5. 1185 = `G3 1322 → G4c_free(1840 s) → 1189 → G4d 链段(1230 s) → 1185`；**G4b 不在祖先里**，
   最后一段 G4d 只贡献 −4。
6. 1185 归档解用原始 Validator + 独立复算双重复核一致：1185 / 1124 / 0 violations。
7. 用原始代码重跑首段 G4b（同起点、同种子、同 1200 s）→ **1294 且 routes 文件与归档逐字节相同**。
8. **结论：没有 G4 回归。** 2203 的差异来自起点（3967 vs 1322）、链路（单段 vs 两段）与预算口径。
