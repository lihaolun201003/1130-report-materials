# G4 CODE RECOVERY AUDIT

**1185 交叉的原始 G4 算法基线的代码审计、历史版本恢复与复现性检查**

| | |
|---|---|
| 审计对象 | `OpticalWaveguideRouter2D`（主工程，**未修改**） |
| 可信归档 | `11.9-second-report-all-work` @ **`833a009b411c`** → `g4_xyz_joint_1024/08_code/g4/` |
| 历史消融归档 | `1130-report-materials/G4_MULTI_ARC_ABLATION_1024`（只读） |
| 最新严格消融归档 | `1130-report-materials/experiments/G4_MULTI_ARC_ABLATION_FINAL_1024`（只读） |
| 审计目录 | `work/G4_CODE_RECOVERY_AUDIT/` |
| 完整备份 | `work/_backups/OpticalWaveguideRouter2D_20261117_1118/`（36 783 文件 / 6.617 GB，0 失败） |
| 隔离恢复工程 | `work/G4_CODE_RECOVERY_AUDIT/recovered_G4_1185/` |
| 日期 | 2026-11-17 |

---

## 0. 结论摘要

1. **原始 G4 代码（1185 的代码版本）已从 `833a009b411c` 完整恢复**：25 个快照条目自校验
   **25/25 通过**（24 个 `g4/*.py` + `SPEC_G4.md`，清单 `g4_xyz_joint_1024/08_code/SHA256.json`
   生成于 2026-11-04 20:10:14，自述 `all_match_source: true`）。
2. **当前主工程与历史代码的差异只有 8 个文件、两类改动**，全部可追溯：
   * **6 个 g4 文件** ← 最新等预算实验（`+176 / −13` 行，纯增量，默认不启用）；
   * **2 个几何/搜索文件** ← 1130 历史多圆弧开关（`layer2d.py +112 / −0`、`local_reroute.py +1 / −0`，纯增量，默认 ON 时行为不变）。
   其余 **444 个 .py 文件**的 mtime 早于可信快照生成时间，未被 1130 任一轮触碰。
3. **没有发现任何被删除或被削弱的算法功能**：6 个修改文件的 13 行删除逐条可列举，
   全部是"签名加默认参数""调用点透传""`START_CROSSINGS` 元数据改写""history 切片长度"，
   没有一行属于搜索逻辑、接受准则、候选生成或预算判定。
4. **不存在真正的 G4 回归错误**。1130 与 FINAL 得不到 1185 的原因是**起点、链路与预算口径**，
   不是代码退化（§5、§6）。最强证据：用**当前代码**在同一条件（G3 起点、seed 20261104、
   1200 s）重跑首段 G4b，产出与 2026-11-04 归档**逐字节相同**的检查点（`c72b245a…`，1294）。
5. **历史 1185 归档解独立验证通过**：用**恢复出来的原始代码**的冻结 Validator 跑出
   `PASS / 0 violations / 1185 crossings / 1124 pairs / 1024 routed`，
   `min 3D clearance = 0.060877 mm`，`total length = 156735.562 mm`；独立几何复算给出
   完全相同的数字，并确认 202 条线路 / 208 个多圆弧区域。
6. **1185 的准确出处不是"一次 G4d 运行"**：它是
   `G3(1322) → G4c_free(1840 s) → 1189 → G4d 链段(1230 s) → 1185`。
   G4b（1294）只进入了一条**未被采用**的旁支（链段 G4c 重跑 → 1204）。
7. **发现两处归档自身的哈希不一致**（不是代码问题，是归档物化问题）：
   `07_chain` 的链段声明哈希、链表的 `end_sha256`、以及发布件 `03_best_valid` 的
   routes 哈希三者互不相同，但 assignment 与 crossing_stats 哈希一致，
   说明是**同一解的不同序列化**。详情见 §2.4，建议以 `b74ae511…` 为唯一权威标识。

---

## 1. 完整备份（第 1 项要求）

| 项 | 值 |
|---|---|
| 源 | `C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D` |
| 目标 | `work\_backups\OpticalWaveguideRouter2D_20261117_1118\` |
| 方法 | `robocopy /E /COPY:DAT /R:1 /W:1 /MT:8`（**未使用任何 git 破坏性命令**；主工程本就不是 git 工作树） |
| 结果 | Dirs 4 338 / Files **36 783** / Bytes **6.617 GB**，Copied = 全部，**FAILED = 0，Mismatch = 0** |
| 用时 | 15 s（456 MB/s） |
| 校验 | `BACKUP_SHA256_20261117_1118.csv`：逐文件 SHA256，**36 783 / 36 783 行均有有效 64 位哈希**；随机抽 3 个（含 `.venv` 深层路径）用 Python 独立复算，全部一致 |
| 指针 | `work\_backups\CURRENT_BACKUP.txt` |
| **审计结束后复核** | `robocopy <主工程> <备份> /E /L`（只列不拷）：**Files 0 / Dirs 0 / Bytes 0** —— 主工程与备份逐字节一致，**审计全程未写入主工程** |

备份覆盖：全部源码、`outputs/`（3.9 GB 结果）、`experiments/`（1.27 GB，含两轮消融）、
`.venv/`、`data/`、`scratch*`、未提交修改与运行配置。**主工程此后全程只读**，
所有写入都发生在 `work/G4_CODE_RECOVERY_AUDIT/`。

> 注：备份中 `outputs/`、`experiments/` 的 2026-11-16 内容即包含两轮消融的全部产物；
> 备份完成后主工程未再被本任务写入任何字节（审计用到的脚本均放在 `work/` 下）。

---

## 2. 原始 1185 实验的准确出处

### 2.1 可信代码快照

| 项 | 值 |
|---|---|
| 仓库 / 提交 | `lihaolun201003/11.9-second-report-all-work` @ **`833a009b411c`**（"G4 实验归档：…（1024）"，即 origin/main 尖端） |
| 路径 | `g4_xyz_joint_1024/08_code/g4/`（24 个 `.py`）+ 同级 `SHA256.json` + `SPEC_G4.md` |
| 清单生成时间 | `2026-11-04 20:10:14`，`all_match_source: true`，`file_count: 25`（24 个 `.py` + `SPEC_G4.md`），`total_bytes: 949 763` |
| 自校验 | **25/25 OK**（`audit_g4/summary.json → snapshot_self_check`） |
| 注意 | 该仓库 `core.autocrlf=true`，用 `git archive` 直接取会得到 CRLF 变体（25 文件全部哈希不符）；必须 `git -c core.autocrlf=false archive` 或取 blob。本次已按后者处理，并在报告中标明 |

快照内 `SHA256.json` 的 `source_package` 字段为 `four_side_1024\fanout1024\xyzrouter\g4`，
且每条记录同时给出 `sha256`（快照）与 `source_sha256`（当时的主工程文件），两者逐条相同 ——
这说明**该快照就是产出 1185 的那一版 g4 代码**，而不是事后另抄的副本。

### 2.2 1185 解的权威标识

| 项 | 值 |
|---|---|
| 文件 | `g4_xyz_joint_1024/03_best_valid/routes_l3d.json` |
| SHA256 | **`b74ae51185edcef43419c3157d07e24237bf05f10e50321310b554f487e9e77a`**（3 700 364 字节） |
| 交叉 / 唯一对 | **1185 / 1124** |
| 有交叉线路 / 最大单线路 | 593 / 19 |
| 总长度 | 156 735.562 044 mm |
| `selected_from` | `chain_link3_G4d` |
| 起点 | G3 合法最优解 `711cf910…`，1322 |
| 独立验收 | `validation_pass: true`（归档时），本次再用原始代码复验通过（§7） |

### 2.3 真实链路（**不是单次 G4d**）

归档 `07_chain/progressive_chain.json` + 各臂 `config/ledger/summary` 给出的实际谱系：

| 环节 | 来源臂 | 起点 | 终点 | 本段收益 | 预算 | 实际耗时 | 终点 routes SHA |
|---|---|---|---:|---:|---:|---|---:|---|
| G3 公共起点 | G3 | 1322 | 1322 | 0 | — | 0 s | `711cf910…` |
| best(G4a,G4b) 检查点 | **G4b** | 1322 | **1294** | −28 | 1200 s | 1099.82 s | `c72b245a…` |
| 链段 G4c 重跑（从 1294） | G4c_free | 1294 | **1204** | −90 | 700 s | 740.52 s | `252bbfd2…`（表）/ `eca59790…`（链段 SHA 文件） |
| best G4c 检查点（A 类 G4c_free 臂） | **G4c_free** | 1322 | **1189** | −133 | 1800 s | 1840.36 s | `ce7ca9a9…` |
| **链段 G4d（从 1189）** | **G4d** | 1189 | **1185** | **−4** | 1200 s | 1229.96 s | `a0bf4c70…`（表）/ `22b0c5fe…`（链段 SHA 文件） |
| G4d warm-start（06b，seed 20261105） | G4d | 1189 | 1189 | 0 | — | 1061.44 s | `ce7ca9a9…`（未改变） |

**实际谱系（决定 1185 的那条）只有两段**：

```
G3 1322 ──[G4c_free, 1800 s, 6851 r3d / 63433 d56]──► 1189
        ──[G4d 链段, 1200 s, 从 1189 起]────────────► 1185
```

* **G4b 不在 1185 的祖先里**。G4b 的 1294 只喂给"链段 G4c 重跑"，产出 1204，**未被采用**；
  真正被采用的 1189 来自**从 G3 直接出发**的 A 类 G4c_free 臂（config 明确写着
  `start_dir = G3 best_valid`、`start_crossings = 1322`）。
* **最后一次 G4d 只贡献 −4**。1185 的绝大部分（1322 → 1189，−133）来自 G4c_free。
* 因此"只跑一个 G4d"无论从哪个起点都不可能复现 1185（从 G3 直接跑的 G4d 臂是 **1212**）。

各孤立臂（全部从 G3 起，seed 20261104）：

| 臂 | 预算 | 实际耗时 | r3d | d56 | 接受事务 | 收益 | 终点 |
|---|---:|---:|---:|---:|---:|---:|---:|
| C0（沿 G3 引擎续跑） | 1200 s | 1208.76 s | 2 324 | —（旧引擎不计） | 31 | −63 | 1259 |
| G4a（组主高度/组内 XY） | 1200 s | 1018.74 s | 6 208 | 43 004 | 1 | −2 | 1320 |
| G4b（人工 U 动态重分组） | 1200 s | 1099.82 s | 1 538 | 11 552 | 11 | −28 | 1294 |
| G4c_frozen | 1800 s | 1847.02 s | 7 106 | 64 342 | 21 | −100 | 1222 |
| **G4c_free** | 1800 s | 1840.36 s | 6 851 | 63 433 | 33 | **−133** | **1189** |
| G4d（从 G3） | 1200 s | 106.3 s¹ | 4 400 | 35 815 | 23 | −110 | 1212 |
| G4d warm（06b，从 1189） | — | 1061.44 s | 4 003 | 29 196 | 0 | 0 | 1189 |

¹ G4d 臂的 `budget_ledger.wall_seconds = 106.3 s` 是"最后一次 resume 会话"的耗时，
不是总耗时（历史 RUNBOOK 记载该臂中断后 `--resume` 续跑）。**这是原始代码的一处记账陷阱**，
复现时若按它设置预算会严重欠跑。

² 所有臂的 `config.json` 里 `start_crossings = 1322`、`start_routes_sha256 = 711cf910…`
都是**硬编码常量**，不是真实起点（见 §6 末尾）。判断起点请只看 `start_dir`。

### 2.4 归档内部的三处哈希不一致（必须知道，但不影响解的正确性）

"链段 G4d"的输出在归档里出现了三个不同的 routes 哈希：

| 记录位置 | routes SHA256 | assignment SHA256 | crossing_stats SHA256 |
|---|---|---|---|
| `07_chain/03_link_G4d/SHA256.json` | `22b0c5fe…` | `2d7363ec…` | `c526abda…` |
| `07_chain/progressive_chain.json` 的 `end_sha256` | `a0bf4c70…` | — | — |
| 发布件 `03_best_valid/`（本文权威） | **`b74ae511…`** | `2d7363ec…` | `c526abda…` |

三者 assignment 与 crossing_stats **完全相同**，说明是**同一个解**；
差异只能来自 `routes_l3d.json` 的**序列化**（发布件的 `note` 字段写着
"G4 best legal solution (selected from chain_link3_G4d); …"，是归档脚本重写过的文本）。
同理，链段 G4c 也有 `252bbfd2…`（表）与 `eca59790…`（链段 SHA 文件）两个值。

**建议**：把 `b74ae511…` 作为 1185 的唯一权威标识；`07_chain` 里的哈希只应视为
"物化时刻的字节指纹"，不能当身份键。仅凭归档无法把这两组字节找回并比对
（`07_chain/*/` 只保留了 `SHA256.json` 与 `validation/`，没有 routes 文件本体）。

---

## 3. 逐文件差异（第 3、4 项要求）

审计脚本：`tools/audit_g4_recovery.py`；产物：`audit_g4/file_table.csv`、
`audit_g4/diffs/*.diff`、`audit_g4/signatures.json`、`audit_g4/settings.json`、`audit_g4/summary.json`。

### 3.1 总表

| 状态 | 文件数 |
|---|---:|
| 完全一致 | **18** |
| 修改 | **6** |
| 当前缺失（快照有、现在没有） | **0** |
| 当前新增（快照没有、现在有） | **0** |

| 文件 | 状态 | 快照字节 | 当前字节 | +行 | −行 | 来源 |
|---|---|---:|---:|---:|---:|---|
| `__init__.py` | 一致 | 606 | 606 | | | |
| `archive_g4.py` | 一致 | 27 409 | 27 409 | | | |
| `artifacts.py` | **修改** | 8 969 | 9 159 | 6 | 3 | 等预算实验 |
| `arm_base.py` | **修改** | 8 797 | 9 203 | 9 | 2 | 等预算实验 |
| `alns.py` | **修改** | 45 963 | 53 397 | 146 | 13 | 等预算实验 |
| `c0_continue.py` | 一致 | 43 334 | 43 334 | | | |
| `contract_audit.py` | 一致 | 39 946 | 39 946 | | | |
| `failure_analysis.py` | 一致 | 45 321 | 45 321 | | | |
| `fair_runner.py` | 一致 | 60 269 | 60 269 | | | |
| `group_replan.py` | 一致 | 50 970 | 50 970 | | | |
| `independent_metrics.py` | 一致 | 98 242 | 98 242 | | | |
| `joint_world.py` | 一致 | 32 701 | 32 701 | | | |
| `ledger.py` | 一致 | 4 465 | 4 465 | | | |
| `make_way.py` | 一致 | 27 954 | 27 954 | | | |
| `metrics_collect.py` | 一致 | 90 718 | 90 718 | | | |
| `neighborhood.py` | 一致 | 19 464 | 19 464 | | | |
| `paths.py` | 一致 | 5 614 | 5 614 | | | |
| `plots_g4.py` | 一致 | 79 456 | 79 456 | | | |
| `report_g4.py` | 一致 | 154 295 | 154 295 | | | |
| `run_g4_engine.py` | **修改** | 3 542 | 3 934 | 6 | 0 | 等预算实验 |
| `run_g4a.py` | 一致 | 34 077 | 34 077 | | | |
| `run_g4b.py` | 一致 | 43 003 | 43 003 | | | |
| `run_g4c.py` | **修改** | 6 847 | 7 753 | 15 | 1 | 等预算实验 |
| `run_g4d.py` | **修改** | 6 669 | 6 948 | 5 | 1 | 等预算实验 |

**没有"无法追溯的其他改动"**：6 个修改文件与 FINAL 实验归档里的
`code_changes/<file>.after` **逐字节相同**，且 `audit_g4/g4_equal_budget.patch`
可从快照重建当前文件。

### 3.2 函数签名变化

只有 `alns.py` 有签名变化（`signatures.json`）：

| 函数 | 变化 |
|---|---|
| `G4Search.run` | 新增 `counted_d56=None, counted_checks_guard=None`（默认 None） |
| `G4Search._run_sweep` | 新增 `counted_end=None` |
| `G4Search._run_stage` | 新增 `counted_end=None` |
| `G4Search.counted_used` | **新增方法** |
| `G4Search._counted_exhausted` | **新增方法** |

其余 5 个文件的签名零变化。

### 3.3 13 行删除的全部内容（证明无功能删除）

| 文件 | 删除行 | 性质 |
|---|---|---|
| `alns.py` | `def _run_sweep(self, seconds, budget):` | 签名加默认参数 |
| | `def _run_stage(self, stage_index, size, seconds, budget):` | 同上 |
| | `skip_sweep=False):` | `run()` 签名续行 |
| | `stage = self._run_sweep(sweep_seconds, budget)` | 调用点透传 `counted_end` |
| | `self._run_stage(stage_index, int(size), stage_seconds, budget)` | 同上 |
| | `time.time() - started < float(seconds) * 0.7:` | quality pass 增加"计数未耗尽"条件 |
| | `self.log('[stage %d] neighbourhood size=…')` + 续行 | 日志加 `counted_end/used` 字段 |
| | `start_crossings=int(GP.START_CROSSINGS),` ×2 | → `getattr(state,'start_total',…)`（元数据） |
| | `delta_vs_start=int(self.state.total) - int(GP.START_CROSSINGS),` ×2 | 同上 |
| | `history_records=self.history_records[-800:],` | → `[-cfg.cap:]`（只影响写盘条数） |
| `arm_base.py` | `start_crossings=dict(GP.START_CROSSINGS),` / `delta=… - int(GP.START_CROSSINGS),` | 元数据 |
| `artifacts.py` | `payload['g4_start_crossings'] = int(GP.START_CROSSINGS)` / `start_crossings=…` / `delta_vs_start=… - int(GP.START_CROSSINGS),` | 元数据 |
| `run_g4c.py` / `run_g4d.py` | `skip_sweep=skip_sweep)` | 调用点透传两个新参数 |

**没有任何一行属于**：候选几何生成、R15/D56/3D 净空判定、接受准则（`min_gain`）、
算子权重、邻域构造、图刷新、事务回滚、Validator 调用。

### 3.4 预算与调度常量（逐值比对，全部未变）

| 常量 | 文件 | 快照 | 当前 |
|---|---|---|---|
| `SEED` | `paths.py` | 20261104 | 20261104 |
| `START_CROSSINGS` | `paths.py` | 1322 | 1322 |
| `STAGE_SIZES`（G4c） | `run_g4c.py` | `[8, 16, 32, 64]` | 同 |
| `STAGE_FRACTIONS`（G4c） | `run_g4c.py` | `[0.22, 0.24, 0.26, 0.28]` | 同 |
| `STAGE_SIZES`（G4d） | `run_g4d.py` | `[16, 32, 64, 96]` | 同 |
| `STAGE_FRACTIONS`（G4d） | `run_g4d.py` | `[0.2, 0.24, 0.26, 0.3]` | 同 |
| `DEFAULT_CFG`（全部 operator 参数） | `alns.py` | 原样 | 原样 **+2 个新键**（`counted_sweep_fraction=0.18`、`history_records_cap=4000`） |
| `PLAN_CFG` / `PROBE_CFG` / `SWEEP_CFG` / `SWEEP_QUALITY_CFG` | `joint_world.py` / `make_way.py` | 原样 | 原样（**逐字节一致，文件未改**） |
| `DEFAULT_BUDGET` / `ARM_BUDGETS` | `paths.py` | 30 000 / 120 000 / 1200–3600 s | 同（文件未改） |

---

## 4. 1130 两轮消融是否改变了候选几何或生产行为（第 4 项要求）

### 4.1 历史多圆弧开关（1130 第一轮）

| 文件 | 改动 | 证明 |
|---|---|---|
| `fanout1024/layer2d.py` | `+112 / −0` 行（纯增量：`MULTI_ARC_POLICY`、`multi_arc_enabled()`、`local_multi_arc_regions()`、`spec_uses_multi_arc()`，`__init__` 读开关，`_iter_candidates` 两处门） | `difflib` 复算：added=112, **removed=0** |
| `fanout1024/xyzrouter/local_reroute.py` | `+1 / −0` 行（`router_cfg['enable_multi_arc'] = L2.multi_arc_enabled(cfg)`） | added=1, **removed=0** |

**`.orig` 的独立来源验证**：把 `layer2d.py.orig` 归一化换行后，
SHA256 = `d0de64e35438861e393cd33e70367bbd9d84bfead065ba8646cbfde78a68e099`，
与可信归档中 `experiments/fanout_first_21_height_rebalanced_1024/code/layer2d.py`
的 **git blob 完全一致**。也就是说，1130 声称的"消融前原始文件"确实等于归档里
一个更早提交的真实快照，不是凭空反推的。
（`.orig` 与本地文件只差 CRLF/LF；本地包全部为 LF。）

`local_reroute.py.orig` 在可信归档中**没有对应快照**，无法做同样的哈希互证；
但它只差 1 行，且该行是给 `cfg` 塞一个键。

**行为等价性**：开关默认 `G4_ENABLE_MULTI_ARC=1`，两处门都是
`if not self.enable_multi_arc and …: continue`，短路后不可达；
新增计数器只写不读。**因此在 ON 状态下候选集合与 2026-11-04 完全一致。**

### 4.2 最新等预算实验（1130 第二轮）

见 §3：6 个 g4 文件，纯增量，默认关闭（只有在命令行显式给 `--counted-d56-budget` 时才进入计数调度），
其余 18 个 g4 文件与 444 个包内其它 .py 文件**一字未动**。

### 4.3 全包 mtime 调查（交叉验证）

`four_side_1024/` 下 452 个 `.py` 文件中，**只有 8 个**的修改时间晚于可信快照生成时间
（2026-11-04 20:10:14）：

| 文件 | mtime | 归属 |
|---|---|---|
| `fanout1024/xyzrouter/local_reroute.py` | 2026-11-16 18:04 | 1130 多圆弧开关 |
| `fanout1024/layer2d.py` | 2026-11-16 19:55 | 1130 多圆弧开关 |
| `xyzrouter/g4/alns.py` | 2026-11-16 23:48 | 等预算实验 |
| `xyzrouter/g4/arm_base.py` | 2026-11-16 23:48 | 等预算实验 |
| `xyzrouter/g4/artifacts.py` | 2026-11-16 23:48 | 等预算实验 |
| `xyzrouter/g4/run_g4c.py` | 2026-11-16 23:49 | 等预算实验 |
| `xyzrouter/g4/run_g4d.py` | 2026-11-16 23:49 | 等预算实验 |
| `xyzrouter/g4/run_g4_engine.py` | 2026-11-16 23:49 | 等预算实验 |

其余 444 个 `.py` 与全部非 `.py` 配置文件（除 `__pycache__`）均早于该时刻。
1130 归档里的 `code_changes/` 也只列了 `layer2d.py` 与 `local_reroute.py` 两个文件，
两者互相印证：**1130 没有偷偷改过别的生产代码**。

---

## 5. 1130/FINAL 新实验为什么得到约 2203（第 5 项要求）

先把问题拆干净：`2203` 是 **FINAL 严格消融 ON 臂**的 3 种子均值（2203/2197/2209）。
它与 1185 的差 **1018** 来自四个可分离的因素，**不是同一个实验的两种结果**。

| 因素 | 1185 的产出条件 | FINAL ON 臂 | 影响 |
|---|---|---|---|
| **起点** | G3 1322（`711cf910…`） | Stage-0 转换后 **3967**（`1707e189…`，多圆弧区域 0） | 决定性 |
| **链路** | G4c_free(1800 s) **+ G4d(1200 s)** 两段 | **单段** `G4c_free` | 大 |
| **预算口径** | 墙钟 1800 + 1200 s（G4c 实际 1840 s） | 计数 **d56 = 24000**（≈900–1500 s） | 中 |
| **代码** | 原始 g4 | 原始 g4 + 纯增量补丁（默认不启用） | **0** |
| 种子 / 约束 / Validator | 20261104 / 同 | 20261104·16·30 / 同 | 0 |

### 5.1 起点是主因：同一预算下 OFF 臂的天花板就是 3601

FINAL 实验里 **OFF 臂**（禁多圆弧）与 ON 臂**同起点、同预算**，它只到 **3601**。
也就是说，从 3967 出发，即使把 24000 次候选评价全部用掉、并且允许搜索完全自由地改高度，
这一版引擎的可达区间仍在 2200–3600，而 1185 是"1322 盆地"里的解。
`3967 → 2203` 本身已经是 −1764（−44.5%），比 1185 那条链的 −137（1322→1185）大一个数量级。

### 5.2 剩余 881 的逐条分解（FINAL 报告 §7.4 的结论，此处复核）

数据：`experiments/G4_MULTI_ARC_ABLATION_FINAL_1024/tables/gap_analysis.json`
与 `tables/repair_c1_20261104_per_route.csv`。`2203 − 1322 = +881`（事件数），可精确拆成：

| 分块 | 残余 | 说明 |
|---|---:|---|
| 197 条被 Stage-0 重表达的线路 | **+515** | 其中 142 条已重新用上多圆弧；但只有 13 条与 G3 逐图元相同，**99 条的目标高度被 Stage-0 改过** |
| 其余 665 条线路 | **+366** | 其中 567 条根本没被动过，是被"修复后的 197 条"的新交叉关系拖高的 |

按高度分桶：高度未变的 98 条平均残余 **+3.18**；高度被改的 99 条平均 **+7.25**（占残余 70%）。
→ **多圆弧自由度被用回来了（142/197），但"几何复原"不等于"排布复原"**。

### 5.3 链路差异：即使给 FINAL 臂更多预算，它也不是 1185 的那条链

1185 的最后一段 G4d 只贡献 **−4**；真正干活的是 G4c_free（−133）。
FINAL 的 ON 臂只跑了 G4c_free 一段（而且是从 3967 起）。
因此 "FINAL ON 没到 1185" 不能读作 "G4 退化了"，只能读作
**"FINAL 实验测的是效果 B（同起点同预算下多圆弧是否更好），不是 1185 的复现"**。

### 5.4 预算：FINAL 的 ON 臂在计数上限处仍在下降

`d56 18000 → 24000` 时 ON 均值 2343 → 2208（−135，约 −22 次/1000 d56）。
按该斜率外推还需 ~45–50k d56 才能再降 1000，且 ALNS 收益次线性 —— 这只是"未跑满"的次要因素，
**不能**据此声称"再跑就能到 1185"。

---

## 6. 是否存在真正的 G4 回归错误（第 6 项要求）

**没有。** 逐项排除：

| 可能的回归 | 检查 | 结论 |
|---|---|---|
| 搜索逻辑被删/改 | 6 文件 diff 的 13 行删除逐条列举（§3.3） | 无逻辑删除 |
| 接受准则放松/收紧 | `min_gain`、`finish()` 接受条件在 18 个未改文件中；`alns.py` 对应行未出现在 diff 删除里 | 未变 |
| 候选几何被改 | `layer2d.py` 只有多圆弧门（默认 ON 时短路）；`joint_world.py`/`make_way.py` 未改 | 未变 |
| 预算/调度被改 | `STAGE_SIZES/FRACTIONS/SEED/START_CROSSINGS` 逐值相同（§3.4） | 未变 |
| 交叉口径被改 | `nonc4/`、`native3d/validate_native3d.py` 未在任何补丁里出现；Validator 输出与 2026-11-04 归档一致（§7） | 未变 |
| 依赖/环境漂移 | §8.2 的两个探针：原始代码与当前代码在 G3 起点、同种子、1200 s 下，**都产出与归档逐字节相同的 `c72b245a…`（1294）** | 无漂移影响 |

**判定：当前代码 = 1185 的算法 + 两组默认不改变行为的纯增量补丁。没有回归。**
（唯一能观察到的差异是记账字段，见下。）

唯一"行为可能不同"的地方是**元数据**：原代码的 `ArmSpec.as_dict()` 把
`start_crossings` 与 `start_routes_sha256` 都写成**常量**（1322 / `711cf910…`），
与实际起点无关。铁证：`06b_G4d_warm_from_1189` 的 `start_dir` 明明是
`05_arm_G4c_free/best_valid`（实际起点 `ce7ca9a9…` / 1189），
但它的 `config.json` 仍写 `start_routes_sha256 = 711cf910…`、`start_crossings = 1322`，
`summary.json.delta_vs_start` 也因此写成 −133（真实收益是 0，`ledger.gain = 0`）。
**这是记账缺陷，不是算法回归**；FINAL 实验的补丁正是修它（改为 `state.start_total`，
但只修了 `extra_payload`/`artifacts`，`summary_g4.json` 与 `config.json` 仍有残留，见 §9 第 5 条）。
→ **复现链式实验时，判断"某臂从哪起跑"只能看 `start_dir`，判断"收益多少"只能看
`budget_ledger.gain`；`config.start_crossings` / `summary.delta_vs_start` 一律不可信。**

---

## 7. 历史 1185 归档的独立验证结果（第 7 项要求）

用 **`recovered_G4_1185/`（原始代码）** 的冻结 Validator，对 `03_best_valid` 的
`routes_l3d.json`（`b74ae511…`）+ `assignment_1024.csv`（`2d7363ec…`）重新验收：

| 检查 | 结果 |
|---|---|
| `validation_pass` | **True** |
| `violations` / `violation_count` | **0 / 0** |
| 覆盖 | routed **1024**，failed 0，identity_mismatches 0 |
| 结构 | routes 1024，junctions 3 848，max_position_gap 4.95e-10，max_tangent_gap 1.01e-15，violations 0 |
| 原生元数据 | native 29 / mid 70 / excursions 35，violations 0 |
| R15 | flat_arcs 1 798，transitions 1 924，`min_sampled = 14.99999998`，violations 0 |
| 玻璃 | samples 1 073 098，min_margin −0.0，violations 0 |
| 真 3D 净空 | `min_3d = 0.060877381`，violations 0 |
| 交叉（冻结 strict D56） | **crossings 1185 / pairs 1124**（与归档一致） |
| 人工 U 契约（`fully_optimizable`） | violations 0 |
| 合成长度 / 交叉 | `total_length = 156735.562044 mm` |
| 输出 | `validation_1185_original_code/validation.json`（20.7 s，exit 0） |

再用**与代码无关**的独立几何复算（`audit_state.py`，只读 routes）交叉核对：

| 指标 | 数值 |
|---|---:|
| routes SHA256 | `b74ae51185edcef43419c3157d07e24237bf05f10e50321310b554f487e9e77a` |
| 交叉 / 唯一对 | **1185 / 1124** |
| 有交叉线路 / 最大 / P95 | 593 / 19 / 8 |
| 总长度 | 156 735.562 044 mm |
| flat 弧 / 直线 / transition | 1 798 / 4 210 / 1 924 |
| 平面多圆弧 | **202 条线路 / 208 个区域 / 553 条弧** |
| `state.total` 与事件列表一致 | True |

三方（归档 summary、原始 Validator、独立复算）**完全一致**。

**因此：不需要重跑整条链来确认"1185 是真的"。**
重跑只在需要"逐位复现"时才有意义，而原实验的预算是墙钟，
逐位复现本来就不成立（历史 RUNBOOK 已记载同代码重跑得到 1202，+1.4%）。

---

## 8. 隔离恢复工程（第 6 项要求的位置与状态）

### 8.1 位置与构成

```
work/G4_CODE_RECOVERY_AUDIT/
├── G4_CODE_RECOVERY_AUDIT.md      ← 本报告
├── README.md                      ← 目录说明（三分钟版本）
├── recovered_G4_1185/             ← 隔离恢复工程 A（原始代码，可独立运行）
│   ├── four_side_1024/             恢复的包：原始 g4/ + 原始 layer2d.py + 原始 local_reroute.py
│   ├── outputs/manual_c4_new_connectivity/XYZ_JOINT_G123_1024/{best_valid,baseline_authoritative,…}
│   ├── outputs/manual_c4_new_connectivity/NEW_MANUAL_CSV_1024_FULL_CAMPAIGN/phase2_2d_selected/（Validator 的 parent 引用）
│   └── data/  requirements.txt  README.md
├── probe_current_code/            ← 隔离工程 B（同一份工程 + 当前主工程 8 个文件）用于对撞探针
├── trusted_08_code/g4_xyz_joint_1024/08_code/   ← 833a009b 的原始快照（25 条目自校验通过）
├── audit_g4/                     逐文件差异（diffs/）、签名、常量、chain_provenance.json、summary.json
├── audit_g3_start.json           起点复算（1322 / 711cf910 / 197 条多圆弧）
├── audit_1185.json               1185 的独立复算（+ 逐条 CSV）
├── validation_1185_original_code/  原始代码 Validator 对 1185 的验收
├── runs/G4b_repro_1200s/         探针 1（原始代码）→ c72b245a
├── runs/G4b_current_code_1200s/  探针 2（当前代码）→ c72b245a
├── staging/                      从可信提交提取的 1185 工件 / 链段文档 / archive 中间件
└── tools/                        audit_g4_recovery.py / extract_chain_provenance.py
```

恢复进 `recovered_G4_1185/` 的代码版本：

| 文件 | SHA256 | 来源 |
|---|---|---|
| `xyzrouter/g4/*.py`（24 个） | 逐条等于 `08_code/SHA256.json` | `833a009b` 快照 |
| `fanout1024/layer2d.py` | `d0de64e3…`（LF，83 671 B） | `833a009b` 中 `fanout_first_21_height_rebalanced_1024/code/layer2d.py` 的 blob（= 1130 `.orig` 归一化后） |
| `xyzrouter/local_reroute.py` | `3daa0d8d…`（CRLF，18 995 B） | 1130 归档 `code_changes/local_reroute.py.orig` |

隔离性验证：

* `common.ROOT` 解析到 `recovered_G4_1185`（`ROOT = Path(__file__).parents[2]`，天然隔离）；
* 该副本里 `G4Search.run` **没有** `counted_d56` 参数（等预算补丁不存在）；
* 该副本的 `layer2d.py` 中 `MULTI_ARC_POLICY`/`enable_multi_arc` 出现次数 = **0**；
* 起点复算：`711cf910…` / **1322** / 1253 对 / 197 条多圆弧线路（与 G3 档案一致）。

### 8.2 复现探针（首段 G4b，原代码 vs 当前代码）

**探针 1：恢复出来的原始代码**

```
cd recovered_G4_1185
python -m four_side_1024.fanout1024.xyzrouter.g4.run_g4b --budget-seconds 1200 --seed 20261104 \
       --out-dir ..\runs\G4b_repro_1200s
```

| 指标 | 归档 G4b（2026-11-04） | 本次探针（2026-11-17，原代码） |
|---|---:|---:|
| 起点 | `711cf910…` / 1322 | 同 |
| 预算 | 1200 s 墙钟 | 同 |
| seed | 20261104 | 同 |
| **终点交叉** | **1294** | **1294** |
| 收益 | −28 | −28 |
| 接受事务 | 11 | 11 |
| 搜索实际耗时 | 1099.82 s | 1079.33 s（1110 s 收尾） |
| ledger `route_3d_checks` | 1 538 | 1 112 |
| ledger `d56_candidate_evals` | 11 552 | 8 380 |
| ledger `transactions` | 320 | 237 |
| Validator | PASS / 0 | PASS / 0（1024 routed，min 3D 0.063596，长度 156 953.815828） |
| **`best_valid/routes_l3d.json` SHA256** | **`c72b245a240fce27…`** | **`c72b245a240fce27…`（逐字节相同）** |
| 逐条线路比对 | — | **1024/1024 完全相同** |

**用 2026-11-04 的原始代码、同样的起点、同样的种子、同样的墙钟预算，
复现出与归档逐字节相同的检查点**（含全部 1024 条线路的几何）。
计数器（r3d/d56/attempts）不同是墙钟调度下"多跑了几次失败尝试"的结果，不影响终点。

**探针 2：当前主工程代码（含 1130 多圆弧开关 + FINAL 等预算补丁）**

把 `recovered_G4_1185` 复制为 `probe_current_code/`，用主工程的 8 个文件覆盖，
其余完全相同，跑同一条命令（`G4_ENABLE_MULTI_ARC` 不设 = 默认 ON）：

| 指标 | 归档 2026-11-04 | 探针 1（原始代码） | **探针 2（当前代码）** |
|---|---:|---:|---:|
| 起点 / 种子 / 预算 | `711cf910…` / 20261104 / 1200 s | 同 | 同 |
| 终点交叉 | 1294 | 1294 | **1294** |
| 收益 / 接受事务 | −28 / 11 | −28 / 11 | **−28 / 11** |
| `routes_l3d.json` SHA256 | `c72b245a…` | `c72b245a…` | **`c72b245a…`** |
| 逐条线路比对 | — | 1024/1024 相同 | **1024/1024 相同** |
| Validator | PASS / 0 | PASS / 0 | **PASS / 0** |
| 长度 / min 3D | 156 953.815828 / — | 156 953.815828 / 0.063596 | **156 953.815828 / 0.063596** |
| ledger r3d / d56 | 1 538 / 11 552 | 1 112 / 8 380 | 1 269 / 9 468 |
| 搜索耗时 | 1099.82 s | 1110 s | 1161 s |

**三次运行产出同一个字节相同的文件**。计数器不同只说明"墙钟预算下多跑了几次失败尝试"，
终点完全一致。这直接回答了第 9 条要求：**新旧代码在相同条件下不产生不同结果**，
因此 2203 不可能是"代码退化"造成的。

### 8.3 若要做"完整链"复现，正确做法（未执行，等确认）

```powershell
cd work\G4_CODE_RECOVERY_AUDIT\recovered_G4_1185
# 1) G4c_free：从 G3 1322 起，1800 s，seed 20261104 → 期望 ~1189
python -m four_side_1024.fanout1024.xyzrouter.g4.run_g4_engine --arm G4c_free `
  --seconds 1800 --seed 20261104 --out-dir ..\runs\chain_G4c_free
# 2) G4d：从第 1 步的 best_valid 起，1200 s → 期望 ~1185
python -m four_side_1024.fanout1024.xyzrouter.g4.run_g4_engine --arm G4d `
  --seconds 1200 --seed 20261104 --start-dir ..\runs\chain_G4c_free\best_valid `
  --out-dir ..\runs\chain_G4d
```

注意：
* **不要**只跑 G4d。从 G3 直接跑的 G4d 臂是 1212，不是 1185。
* 原代码 `--seconds` 是墙钟预算，两次运行都不可能逐位复现；
  历史同代码重跑得到 1202（+1.4%），应以此为预期区间。
* 原代码的 `summary.json.delta_vs_start` 对"从检查点起跑"的臂是错的（硬编码 1322），
  比较时请用 `budget_ledger.gain`，不要用 `delta_vs_start`。

---

## 9. 建议保留与回退的修改清单（第 9 项要求）

| # | 修改 | 位置 | 建议 | 理由 |
|---|---|---|---|---|
| 1 | 平面多圆弧开关（`MULTI_ARC_POLICY` 等） | `fanout1024/layer2d.py`、`xyzrouter/local_reroute.py` | **保留** | 纯增量；默认 ON 行为与 1185 版一致；关掉即 OFF 消融臂。若要生产环境完全回到 1185 代码，把 `G4_ENABLE_MULTI_ARC=1` 固定即可（已是默认） |
| 2 | 等预算调度（`counted_d56` 等） | `g4/alns.py`、`run_g4c.py`、`run_g4d.py`、`run_g4_engine.py` | **保留**（默认关闭） | 只有显式 `--counted-d56-budget` 才生效；是 FINAL 实验可复现的前提 |
| 3 | 起点元数据修正（`state.start_total`） | `g4/arm_base.py`、`g4/artifacts.py`、`g4/alns.py` | **保留** | 修的是记账缺陷（从检查点起跑时 `delta_vs_start` 错）。**若回退，链式复现的统计会再次失真** |
| 4 | `history_records` 增加 `d56/r3d/xy` 与切片上限 | `g4/alns.py` | **保留** | 只影响写盘内容；是搜索曲线图的数据源 |
| 5 | （建议新增，未做）`ArmSpec.as_dict()` 里仍硬编码 `start_routes_sha256 = GP.START_ROUTES_SHA256`、`start_crossings = GP.START_CROSSINGS` | `g4/arm_base.py:52-53` → `config.json` | **建议修**（本次未改，属生产文件） | 现在 `summary_g4.json` / `extra_payload` / `arm_base.summary()` 都已用 `state.start_total`（已修），**只剩 `config.json` 还是常量**。任何从检查点起跑的臂，其 `config.json` 仍会把起点写成 711cf910/1322 —— 这正是 06b 那类误记的来源 |

**回退方案（若确需回到 1185 版代码）**：
`code_changes` 里的 `g4_equal_budget.patch` 可用 `git apply -R` 逆向撤销；
`layer2d.py`/`local_reroute.py` 回退到 1130 `.orig`（等于 `833a009b` 里的 layer2d 快照）。
**但本任务不执行任何回退**——按第 10 条要求，先由你确认。

---

## 10. 与既有结论的更正

| 出处 | 原表述 | 本次更正 |
|---|---|---|
| FINAL 报告 §7.3/§7.4 | "1185 是**从 1322 出发**、用 3119 s 的**两段式链**得到的解" | 链路正确，但**不含 G4b**：实际祖先为 `G4c_free(1840 s) → 1189 → G4d 链段(1230 s) → 1185`，合计 ≈3070 s。G4b 的 1294 只进入未采用的旁支 |
| FINAL 报告 §7.4 | "…需要跨过 Stage-0 造成的高度重排" | 该结论不变，且本次补上了量化：99/197 条高度被改，占残余 70% |
| 1130 历史 RUNBOOK §7.3 | 1202 vs 1185 的 +17 归因于墙钟/重启/贪心差异 | 本次给出更直接的归因：**1185 使用了两段链（G4c_free + G4d），而 1130 的 ON 对照也是两段** —— 但 1130 的 ON 臂从 1322 起跑且 G4c 只跑 1800 s 墙钟，与归档 G4c_free 同预算，最终 1204/1202，与归档 1189/1185 相差 15/17（≈1.4%）。差异同源于墙钟不可逐位复现 + 归档 G4c 曾 `--resume` |

---

## 11. 复现本审计

```powershell
$AUD = 'work\G4_CODE_RECOVERY_AUDIT'
# 1) 备份（若需重做）
robocopy <project> work\_backups\OpticalWaveguideRouter2D_<stamp> /E /COPY:DAT /R:1 /W:1 /MT:8
# 2) 提取可信快照（必须关闭 autocrlf）
git -C work\11.9-second-report-all-work -c core.autocrlf=false archive -o $AUD\staging\08_code.tar 833a009b411c g4_xyz_joint_1024/08_code
tar -xf $AUD\staging\08_code.tar -C $AUD\trusted_08_code
# 3) 逐文件差异
python $AUD\tools\audit_g4_recovery.py --trusted $AUD\trusted_08_code\g4_xyz_joint_1024\08_code `
  --current <project>\four_side_1024\fanout1024\xyzrouter\g4 `
  --ablation work\1130-report-materials\G4_MULTI_ARC_ABLATION_1024\code_changes --out $AUD\audit_g4
# 4) 链谱系
python $AUD\tools\extract_chain_provenance.py --repo work\11.9-second-report-all-work --out $AUD\audit_g4
# 5) 1185 独立验收（在恢复工程里）
cd $AUD\recovered_G4_1185
python -m four_side_1024.fanout1024.xyzrouter.validate_xyz --run-dir $AUD\staging\archived_1185 `
  --out-dir $AUD\validation_1185_original_code --manual-policy fully_optimizable `
  --baseline-dir $AUD\recovered_G4_1185\outputs\manual_c4_new_connectivity\XYZ_JOINT_G123_1024\baseline_authoritative
```

---

## 12. 未做 / 待确认

* **未修改主工程任何文件**；未回退任何补丁；未改动 Validator；未做新的冷启动消融。
* **未跑完整链**（G4c_free 1800 s + G4d 1200 s，约 55 min）：§7 已证明 1185 归档解本身成立，
  是否要做逐位复现请你确认（§8.3 给了命令）。
* `07_chain` 里两组"物化哈希"无法找回对应文件（归档未存 routes 本体），
  只能证明 assignment/crossing_stats 一致（§2.4）。若需要严格哈希链，
  需要从原 `OpticalWaveguideRouter2D/experiments/xyz_joint_g4_1024/` 工作目录遗址里找，
  但那目录已不存在于当前工程（`experiments/` 下只有 1130 两轮的内容）。

---

## 13. 发布记录

本审计的**完整证据包**已发布到 1130 归档仓库：

```
1130-report-materials/
└── experiments/G4_CODE_RECOVERY_AUDIT/
    ├── G4_CODE_RECOVERY_AUDIT.md      ← 本报告
    ├── README.md
    ├── audit_g4/                      file_table.csv / diffs/ / signatures.json /
    │                                  settings.json / summary.json / chain_provenance.json
    ├── audit_g3_start.json            起点复算
    ├── audit_1185.json (+ _per_route.csv)
    ├── validation_1185_original_code/ 原始代码 Validator 的 1185 验收
    ├── trusted_08_code/               833a009b 的 08_code 快照（可离线复核哈希）
    ├── runs/G4b_repro_1200s/          探针 1（原始代码），含 best_valid/routes_l3d.json = c72b245a
    ├── runs/G4b_current_code_1200s/   探针 2（当前代码），同上
    ├── tools/                         audit_g4_recovery.py / extract_chain_provenance.py /
    │                                  build_manifest.py / publish_to_1130.ps1
    ├── MANIFEST.json / SHA256SUMS.csv
    └── .gitattributes                 `* -text`（字节精确）
```

未发布（可复现，故不入库）：`recovered_G4_1185/` 与 `probe_current_code/`（各 ~74 MB 的
隔离工程副本）、`staging/`（中间 tar 与提取件）。它们由 §8.1 与 §11 的步骤可重建。

发布脚本：`tools/publish_to_1130.ps1`（可重复执行；`-Commit` / `-Push` 可选）。
