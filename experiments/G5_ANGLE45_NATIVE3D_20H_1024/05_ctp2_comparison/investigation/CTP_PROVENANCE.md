# CTP provenance: which crosstalk model versions actually exist

Investigation date: 2026-11-19. Read-only survey; no existing project file was modified.

---

## 0. Bottom line

| Claim | Verdict | Evidence |
|---|---|---|
| "CTP-1.0 exists locally in `OpticalWaveguideRouter2D`" | **TRUE** | §1.1 |
| "CTP-2.0 exists somewhere" | **TRUE** | §1.2 (local checkout) + §1.3 (upstream `main`) |
| "The local checkout only has CTP-1.0" | **TRUE only for the `OpticalWaveguideRouter2D` experiment folder**; FALSE for the workstation as a whole | §1.2 |
| "The user's −15.21 / −14.77 / −12.71 dB numbers come from CTP-2.0" | **TRUE, exact to 3 decimals** | §2.1 |
| CTP-1.0's corresponding numbers are −65.91 / −58.38 / −57.49 dB | **TRUE** — they are ~50 dB more optimistic and are known to be wrong | §2.2 |

**Consequence for the G4→G5 comparison: the model that must be re-run is CTP-2.0, and it is available locally. CTP-1.0 must not be used to produce the comparison headline (see `RECOMMENDATION.md`).**

---

## 1. Where each version lives

### 1.1 CTP-1.0 (two byte-identical copies)

1. **Primary (the folder the task refers to)**
   `OpticalWaveguideRouter2D\experiments\CROSSTALK_PREDICTION_20H_1283_1024\`
   - `README.md:3` → ``1024 通道三维玻璃光波导全板光学串扰预测（模型版本 **CTP-1.0**）。``
   - `config\simulation_config.yaml:2` → `model_version: CTP-1.0`
   - `src\config.py:19` → `"model_version": "CTP-1.0"`
   - `src\__init__.py:1` → `"""1024-Channel 3D Optical Waveguide Crosstalk Prediction (CTP-1.0)."""`
   - 99 files / 49.2 MB (incl. `outputs\` + `cache\`)

2. **Second copy inside the report repo**
   `work\1130-report-materials\experiments\CROSSTALK_PREDICTION_20H_1283_1024\`
   - 91 files / 40.7 MB; `README.md` SHA256 is identical to copy (1)
     (`792613B84F8650589A295805110C715691B64E6D14BB145702B5E962D13E0B73`).
   - This is the copy CTP-2.0 uses as its upstream reference (`src/ctp2/params.py:60`).

No other CTP-1.0 copy exists. `OpticalWaveguideRouter3D\` and
`OpticalWaveguideRouterNative3D\` contain **no** crosstalk material (the only
`*CTP*`/`*crosstalk*` name matches there are unrelated site-package files:
`lxml\objectpath.pxi`, `win32comext\adsi\demos\objectPicker.py`).

### 1.2 CTP-2.0 — full source, full outputs, present locally

**Path**
```
work\1130-report-materials\experiments\CROSSTALK_PREDICTION_CTP2_20H_1283_1024\
```

Self-identification (quoted):

| File:line | Text |
|---|---|
| `README.md:1` | `# CTP-2.0 — Literature-Grounded, Multi-Method Validated Full-Board Crosstalk Prediction` |
| `reports\CTP2_REPORT.md:1` | `# CTP-2.0：基于文献、多方法交叉验证的 20 层 / 1283 交叉 / 1024 通道全板串扰预测` |
| `reports\CTP2_REPORT.md:3` | `> 模型版本 **CTP-2.0** · 实验目录 CROSSTALK_PREDICTION_CTP2_20H_1283_1024` |
| `reports\CTP2_REPORT.md:6` | `> 旧版本 **CTP-1.0** CROSSTALK_PREDICTION_20H_1283_1024 完整保留、未被改动` |
| `config\simulation_config.yaml:2` | `model_version: CTP-2.0` |
| `config\simulation_config.yaml:4` | `supersedes: CROSSTALK_PREDICTION_20H_1283_1024   # CTP-1.0, kept read-only` |
| `outputs\board\board_summary_ctp2.json:2` | `"model": "CTP-2.0"` |
| `src\ctp2\__init__.py:1` | `"""CTP-2.0: Literature-Grounded, Multi-Method Validated Full-Board Crosstalk Prediction.` |
| `scripts\run_board_ctp2.py:1` | `"""Full-board 1024x1024 port transfer matrix, CTP-2.0.` |

It is a **separate codebase**, not a patched CTP-1.0: `src\ctp2\{params,geometry,optics,coupling,crossing,bpm,fdfd2d}.py`
+ `src\fullwave\` (independent 2-D/3-D FDTD) + 7 stage scripts + a 35.9 kB
`audit\ctp1_code_audit.md` + 55 kB `reports\CTP2_REPORT.md`.

Completeness: all stage outputs are materialised
(`outputs\modes|coupling|crossings|board|figures|fullwave`, 20 figures,
1024×1024 matrices as `.npy` + 8.4 MB `.csv`, 201-row crossing-kernel database).

### 1.3 CTP-2.0 is also on the upstream GitHub repository

The URL given in the task, `https://github.com/lihao201003/1130-report-materials`,
**does not exist** — GitHub API returns `404 Not Found`. The real repository is
`lihaolun201003` (note the `lun`):

- `https://api.github.com/repos/lihaolun201003/1130-report-materials` → **HTTP 200**,
  `"full_name":"lihaolun201003/1130-report-materials"`, `"private":false`,
  `"default_branch":"main"`, `"pushed_at":"2026-11-19T14:26:15Z"` (= 2026-11-19 22:26 +08:00).
- `https://api.github.com/repos/lihaolun201003/1130-report-materials/contents/experiments`
  → **HTTP 200**, listing contains the dir **`CROSSTALK_PREDICTION_CTP2_20H_1283_1024`**
  (git sha `19367de9b621481cb12cd9aa6c46d523000e62ce`) next to
  `CROSSTALK_PREDICTION_20H_1283_1024`.
  Browse URL: <https://github.com/lihaolun201003/1130-report-materials/tree/main/experiments/CROSSTALK_PREDICTION_CTP2_20H_1283_1024>
- Local `git remote -v` → `origin https://github.com/lihaolun201003/1130-report-materials`.
- `git ls-remote origin` returns `c6c1f45ff3fd2ae65e14cf47ce3e4043e858e488 refs/heads/main`
  — **identical to local `HEAD`**, and `main` tracks `origin/main` with a clean tree.
  So the local CTP-2.0 is *not* a stale or partial copy: it **is** upstream `main`.

CTP-2.0 git history (from `git log --oneline`), i.e. the version chain:

```
c6c1f45 CTP-2.0: final independent-FDTD validation section (self-check, convergence, 3-D feasibility)
0a8e99a CTP-2.0: final report number sync
7397211 CTP-2.0: fold in the independent FDTD anchors up to 45 deg and finalise the model
d436985 CTP-2.0: clearer crossing figures (FDTD anchors, calibrated nominal band) + fullwave report
b5953c7 CTP-2.0: literature-grounded, multi-method validated full-board crosstalk re-analysis
a0f9ca8 Add 1024-channel full-board crosstalk prediction (CTP-1.0) for 20H/1283
```

### 1.4 Everything else that was searched (all negative)

| Location | Result |
|---|---|
| `docs\`, `毕业设计\`, `汇报记录\`, `personal work\`, `01_汇报与展示\` | no `*CTP*` / `*crosstalk*` file names, no `CTP-2` in `*.md`/`*.py`/`*.json`/`*.yaml` |
| `90_历史与临时\` (上传与打包/依赖安装/发布验证/整理记录/文献处理/清理保全/缓存) | nothing |
| `02_资料备份\` | only `原始压缩包\自动排布.zip` (614 MB, routing, not crosstalk) |
| `03_工具与构建\` | nothing |
| `OpticalWaveguideRouter3D\`, `OpticalWaveguideRouterNative3D\` | nothing (except unrelated site-packages) |
| `work\11.9-second-report-all-work\` (another git checkout) | nothing |
| archives named `*CTP*`/`*crosstalk*` (`*.zip/7z/rar/tar/gz`) | none |
| `OpticalWaveguideRouter2D\_reference\.git` | not a crosstalk source |

Two harmless artefacts worth knowing about:
- `work\1130-report-materials\experiments\experiments\CROSSTALK_PREDICTION_CTP2_20H_1283_1024\`
  is an **empty directory skeleton** (`cache\`, `outputs\board|coupling|crossings|figures|fullwave|modes\`, no files)
  — a stray side effect of a relative-path bug. It contains no data.
- `work\1130-report-materials\README.md` has corrupted links from a bad
  find/replace, e.g. line 14 contains
  `.../C:\Users\lihao\Desktop\Graduation Project\work\1130-report-materialsrts/CTP2_C:\Users\...RT.md`.
  The document is still readable; only the links are mangled.

---

## 2. Which numbers each model produces for the G4 baseline

### 2.1 CTP-2.0 (this is where the user's numbers come from)

`work\1130-report-materials\experiments\CROSSTALK_PREDICTION_CTP2_20H_1283_1024\outputs\board\board_summary_ctp2.json`

```json
"nominal_ctp2": {
  "max_offdiagonal_db": -15.206468704880304,
  "max_offdiagonal_pair": [743, 723],
  "worst_total_leakage_db": -14.769540964146534,
  "worst_total_leakage_route": 743,
  "diagonal_min_db": -1.8789188513758748,
  "all_columns_le_1": true
},
"multi_input_incoherent": {
  "worst_interference_to_signal_db": -12.711747549665644,
  "worst_output_route": 743
},
"bounds": {
  "max_offdiagonal_lower_db": -15.906468704880313,
  "max_offdiagonal_upper_db": -14.50646870488031,
  "worst_total_leakage_lower_db": -15.472380065904119,
  "worst_total_leakage_upper_db": -14.06573507297268
}
```

| User's quoted number | CTP-2.0 value | Rounded |
|---|---|---|
| worst single port-pair crosstalk ≈ **−15.21 dB** | −15.206468704880304 dB (R723→R743) | −15.21 ✅ |
| worst single-route total leakage ≈ **−14.77 dB** | −14.769540964146534 dB (R743) | −14.77 ✅ |
| worst multi-input interference/signal ≈ **−12.71 dB** | −12.711747549665644 dB (route 743) | −12.71 ✅ |

All three match to the quoted precision, so **the quoted baseline is the CTP-2.0
nominal prediction, not CTP-1.0**.

One nuance: CTP-2.0's own `README.md:17-19` quotes a *slightly different*
triple — `−15.22 / −14.79 / −12.50 dB` — from an earlier revision of the
report. The user's triple matches the **final JSON at HEAD (`c6c1f45`)**, i.e.
the latest, not the README table. Use the JSON (or `reports\CTP2_REPORT.md`
§"B. CTP-2.0 名义" lines 457-459, which does read `−15.21 / −14.77`) as the
authoritative baseline; the README table is stale by ~0.2 dB on the ISR value.

Supporting CTP-2.0 facts for the same geometry:
`n_crossings = 1283`, `n_forward_allowed = 856` / `blocked = 427` (direction
rule), `angle_min = 5.153763°`, `angle_median = 63.2563°`, per-crossing
`T_cross_db` from −85.0 (floor) to **−14.365 dB**, `runtime_seconds = 1.90`.

### 2.2 CTP-1.0 (local, G4)

`OpticalWaveguideRouter2D\experiments\CROSSTALK_PREDICTION_20H_1283_1024\outputs\optical\e5_summary.json`

```json
"p_cross_per_event_used": 1e-07,
"crossing_curve_max_fdfd": 6.913574049288306e-08,
"max_offdiagonal_db": -65.90547984023327,
"max_offdiagonal_pair": [16, 742],
"worst_total_leakage_db": -58.37853297615624,
"mean_total_leakage_db": -66.89055322647425,
"multi_channel": { "worst_interference_to_signal_db": -57.493769362467134, "worst_output_route": 559 },
"diagonal_min_db": -1.4116101963544256, "diagonal_max_db": -0.2240693494208043,
"energy": { "max_column_sum": 0.9497144919208746, "all_columns_le_1": true }
```

| Metric | CTP-1.0 (published, local) | CTP-2.0 (nominal) | Difference |
|---|---:|---:|---:|
| worst single port-pair | **−65.905 dB** (R16⇄R742) | −15.206 dB (R723→R743) | +50.7 dB |
| worst single-route total leakage | **−58.379 dB** | −14.770 dB | +43.6 dB |
| worst multi-input interference/signal | **−57.494 dB** (R559) | −12.712 dB | +44.8 dB |
| per-crossing crosstalk | fixed `p = 1e-7` for **every** angle (−70 dB), measured max 6.91e-8 | −14.37 … −85 dB, angle-dependent | — |

Reproduced elsewhere in the same run:
- `outputs\geometry\e1_summary.json`: total length `156597.22152165702 mm`
  (error `−3.43e-7 mm`), `loss_max_db = 1.411609762059922`, `route_count = 1024`.
- `outputs\geometry\e4_summary.json`: `events = 1283`, `pairs = 1221`,
  `routes_with_crossings = 647`, `min_distance_noncrossing_mm = 0.05`,
  `runtime_seconds = 243.03`.
- `outputs\optical\e2_summary.json`: 3 guided modes, `n_eff = [1.50455743, 1.50187373, 1.50187373]`.
- `outputs\optical\e3_summary.json`: FDFD crossing crosstalk **−71.6 … −79.6 dB at
  all 17 angles** (angle-independent plateau), `runtime_seconds = 437.80`.
- `outputs\optical\e5_summary.json`: `runtime_seconds = 1.07`.
- `outputs\optical\e6_summary.json`: `runtime_seconds = 363.95`.
- `outputs\optical\crosstalk_hotspots.json`: 80 hotspot clusters stored (top-80 of a
  2 mm-cell clustering of the 1283 events); top cluster at `z = +0.025 mm`,
  `(x,y) = (111.65, 33.38) mm`, 6 crossings / 5 routes, `total_P_cross = 6e-7`
  (−62.22 dB).

### 2.3 Why CTP-1.0's numbers are ~50 dB off — the audit trail already exists

CTP-2.0 ships a source-level audit of CTP-1.0 with file:line and numerical
reproduction: `audit\ctp1_code_audit.md` (35.9 kB),
`audit\ctp1_anomaly_reproduction.md` (24.7 kB),
`audit\ctp1_vs_ctp2.md`, `audit\ctp1_vs_ctp2_gap_analysis.md`.
The four headline defects, two of which I re-read in the source myself:

1. **Wrong incident mode in the local FDFD.**
   `CROSSTALK_PREDICTION_20H_1283_1024\src\crossing.py:197`:
   `Ty = Dyn + sp.diags(k0 ** 2 * n2_bg[1:-1, 0] ** 2)`.
   Column `0` is the left Dirichlet boundary column that `_index_grid_2d`
   forces to `n_clad²` (no core), and `n2_bg` already stores **n²**, so the
   expression squares it again (n⁴). The resulting "incident mode" is a
   uniform-media sine with overlap **9.1e-10** against the true guided mode —
   which is exactly why CTP-1.0's FDFD returns an angle-independent
   −71.6…−79.6 dB plateau (`e3_summary.json`).
2. **FDFD gives T > 1.** `T_through_fdfd = 1.0015` at 5° … 1.0019 at 40°
   (`e3_summary.json`) — the spurious scattered amplitude interferes with the
   unit "incident amplitude"; the discrete-flux factor `sin(βh)/h` was not used
   (20 % port-normalisation error at h = 0.15 µm).
3. **Non-symmetric supermode matrix fed to a symmetric eigensolver.**
   `src\coupling.py:149-158` writes only `A[r, r+1]` (or `A[i, i+snx]`) for the
   even mirror image and never the transposed element; `eigsh` then sees a
   matrix with ‖A−Aᵀ‖/‖A‖ = 3.6–4.9 %. Repeated runs give κ(50 µm) anywhere in
   3.4e-7 … 8.7e-5 mm⁻¹ (258× spread), versus a physical ≈1.2–2.0e-10 mm⁻¹.
4. **The board matrix never uses the crossing angle.**
   `run_e5.py:38,65` passes `p_floor = 1e-7`; `build_board` reads only the
   scalar `p_cross` (`src\board.py:77`) — the `p_cross_nominal` argument
   declared at `board.py:54` is accepted and never referenced, and `angle_deg`
   is recorded in `pair_records` (`board.py:90`) but never used. Hence
   `T_upper ≡ T_nominal` and the headline numbers are pure bookkeeping:
   `T_max(p) = p·W_max` with `W_max = 2.5672`.

CTP-2.0 also adds a **propagation-direction rule** that CTP-1.0 lacks
(856 of 1283 crossings can actually deliver power to a target port; 427 only
add insertion loss) — `docs\method_comparison.md:83-91`,
`scripts\run_board_ctp2.py:95-130`.

---

## 3. Model-version strings that must not be confused

| String | Where | Meaning |
|---|---|---|
| `CTP-1.0` | `CROSSTALK_PREDICTION_20H_1283_1024\{README.md:3, config:2, src/config.py:19}` | legacy model, kept read-only |
| `CTP-2.0` | `CROSSTALK_PREDICTION_CTP2_20H_1283_1024\{README.md:1, config/simulation_config.yaml:2, outputs/board/board_summary_ctp2.json:2}` | current model |
| `crosstalk_prediction_config_v1` / `_v2` | the two `config/simulation_config.yaml:1` | schema version, matches CTP-1.0 / CTP-2.0 |
| `crosstalk_prediction_manifest_v1` | CTP-1.0 `outputs/optical/simulation_manifest.json:1` | manifest schema |
| `package_version: 1.0.0` | CTP-1.0 manifest | Python package version (`src/__init__.py`), **not** the model version |

There is **no CTP-1.1, CTP-1.5, CTP-3.0 or "CTP-2" variant** anywhere in the
workspace or on the upstream repo. The version chain is exactly
`CTP-1.0` (commit `a0f9ca8`) → `CTP-2.0` (commits `b5953c7 … c6c1f45`).
