# 文献检索日志（literature search log）

- 任务：为 `CROSSTALK_PREDICTION_CTP2_20H_1283_1024` 的串扰预测寻找可核验的文献依据
- 执行者：research-librarian 子代理（litreview）
- 日期：**2026-11-19**（Asia/Shanghai）
- 工具：DSH `web_search` / `web_fetch`；Crossref REST API；OpenAlex API；Unpaywall API；Semantic Scholar Graph API；arXiv API；PMC；出版社与机构库页面；本地 PDF 下载 + `pdftotext`/`pypdf` 文本提取
- 重要环境限制：
  - `opg.optica.org` 全站被 bot-check（perfdrive）拦截 → 所有 Optica 非 OA 文章只能拿摘要；
  - `ris.uni-paderborn.de`、`r.jina.ai`、`mdpi.com` PDF、`pubs.aip.org`、`onlinelibrary.wiley.com`、`degruyter.com`、`eprints.soton.ac.uk`、`core.ac.uk` 在本网络被 401/403/Cloudflare 拦截；
  - `web_fetch` 不支持 `application/pdf` → 改用 `Invoke-WebRequest` 下载 + `pdftotext` 本地转换（11 篇成功）。

## 1. 检索批次与命中（web_search）

| 批次 | 主要 query | 命中/用途 |
|---|---|---|
| 1 | `Design and demonstration of direct UV-written small angle X couplers ...`；`Hybrid coupled-mode modeling in 3D ...` | 定位 S01/S02；拿到 S01 摘要（Google Patents 片段）与 S02 摘要（Google Patents 片段） |
| 2 | `Low-loss, low-crosstalk waveguide crossing for scalable integrated silicon photonics applications (2020 DOI)`；`All-optical routing and switching for three-dimensional photonic circuitry (DOI)` | 定位 S03（Opt. Express 28:12498, DOI 10.1364/OE.381304）与 S04（Sci. Rep. 1:94, DOI 10.1038/srep00094） |
| 3 | `Hammer Alhaddad Förstner "hybrid coupled-mode" 3D ... pdf`；`Johnson Thompson Sahin ... crosstalk -50 dB` | 发现 Hammer 讲稿 PDF、Bristol 机构库 PDF、Paderborn 库（不可达） |
| 4 | `Adikan Gawith ... silica-on-silicon beam propagation method coupling ratio`；`"X coupler" silica waveguide 0.8 degrees 5 degrees coupling ratio` | 发现 Soton ECIO-2006 会议文（401，未取得）与 UM repository 记录 |
| 5 | `femtosecond laser written glass waveguide directional coupler coupling length ...`；`Szameit femtosecond laser written waveguide arrays coupling constant separation fused silica` | 定位 S09（Appl. Phys. B 82:507）与 S10/S11 线索 |
| 6 | `Chiles "Multi-planar amorphous silicon photonics" ...`；`Bogaerts "Low-loss, low-cross-talk crossings ..."`；`Szameit "Hexagonal waveguide arrays ..."`；`silica-on-silicon waveguide crossing crosstalk X junction weak index contrast` | 定位 S06/S07/S09；发现 S13/S26 线索 |
| 7 | `femtosecond laser written glass waveguide crossing insertion loss crosstalk 3D`；`multimode waveguide crossing crosstalk ...`；`coupled mode theory waveguide crossing angle dependence`；`Osellame Cerullo review ...` | 发现 S22/S24/S25 与 S16 线索；确认"3-D 玻璃交叉"几乎无实测文献 |

## 2. API/数据库请求（关键批处理）

1. **Crossref 主题探测**（26 条题录 query，每条 rows=2~4）：核验了 S01–S29 中 28 条的题名/作者/期刊/卷期/页码/年份；S17 为机构库 DOI，不在 Crossref（HTTP 404）。
2. **Crossref 逐 DOI 核验**（32 个 DOI）：见 `crossref_verify_out.txt`（本地临时文件）；最终矩阵只保留核验通过的条目。
3. **OpenAlex 摘要/题录**（42 个 DOI + 15 组主题 search）：拿到 16 条摘要（含 S01、S02、S08、S18–S23、S26–S29 等）；并从 OA 位置找到 S06（arXiv）、S10/S11/S12（机构库）、S24（arXiv）、S25（IOP）的全文。
4. **Unpaywall**（14 个 DOI）：确认 S01/S02/S09/S14 等为 closed；确认 S06/S10/S11/S12/S24/S25 的合法 OA 副本。
5. **Semantic Scholar**（4 次）：仅作辅助（摘要被出版商 elide 的条目拿不到内容）。
6. **arXiv API**（"hybrid coupled-mode"）：0 命中 → 确认 Hammer HCMT 无 arXiv 版本。
7. **PDF 下载与本地提取**（11 篇成功）：S03、S04（PMC HTML）、S05（HTML）、S06、S07、S10、S11、S12、S13、S24、S25；另有 Hammer 讲稿（辅助材料）。
8. **失败尝试记录**：S01（Optica + UM repo + ECIO 401）、S02（Optica + Paderborn 不可达）、S06 出版社版（AIP 403，改用 arXiv 版）、S08/S09/S14（付费墙）、S17（PDF 0 字节）、S19/S21 等（Optica bot-check）。

## 3. 筛查统计

- 浏览题录约 **150 条**（OpenAlex/Crossref 返回）。
- 进入候选 **~35 条**；最终保留 **29 条**写入 `docs/literature_matrix.csv`。
- 全文可读 **11 条**；仅摘要 **16 条**；仅题录 **2 条**（S09、S14）。
- 提取数值 **49 行**写入 `benchmarks/literature_benchmarks.csv`。
- 本集合是**策展样本**，不可当作该领域全部文献的无偏普查；引用计数未加权。

## 4. 数据质量规则（本次执行）

- 书目字段只填 Crossref 核验值；`page` 缺失时留空，不猜测。
- 数值只从**实际读到的**摘要/全文抄录；二次引用（如 S19 的交叉数值来自 S03 的 Table 1）**不写入 benchmark**，只在正文注明"未核实"。
- 从图中读不出的数值一律不填；用论文给出的拟合式计算的数值标 `value_kind=fitted` 并在 `conditions_notes` 说明。
- 所有"论文没说、我们外推"的内容在综述中显式标 `[inference]`；所有"论文原话/原数"标 `[direct evidence]`。
- 对 S07 摘要与正文自相矛盾处（97.5 % transmission 对应 −1.7 dB vs 正文 −0.16 dB）已在矩阵 notes 中标明为论文笔误。

## 5. 待办（若后续可访问付费全文）

1. S01 Adikan 2006 全文：确认"crossing angle"定义与"coupling ratio"分母、BPM 设置与偏差数字。
2. S02 Hammer 2017 全文：确认 HCMT 的耦合项公式、任意角度/位置处理方式、与全波对比误差、代码可得性。
3. S09 Szameit 2006 全文：抽取 C(间距, λ) 数据点，补入 benchmark（当前 `benchmarks` 只在 S10/S11 有玻璃耦合长度数据）。
4. S14 Gevorgyan 1991 全文：获取 X 结解析公式（小角理论）。
5. S17 Kyushu 2018 全文：确认作者/期刊/几何，决定是否保留。
6. S19 Seok 2016 原文：核实 0.017 dB / −55 dB 交叉数值后再决定是否入 benchmark。

## 6. 产出文件

- `docs/literature_review.md`（中文综述，7 节 + 附录，含逐篇精读档案）
- `docs/literature_matrix.csv`（29 行 × 24 列）
- `benchmarks/literature_benchmarks.csv`（49 行 × 17 列）
- `docs/literature_search_log.md`（本文件）
