# Pipeline parameterisation — what must change to run the same optical model on G5

Read-only survey. Nothing in this document was applied; no existing file was edited.

Target input for the new round (assumed, currently **empty**):
`experiments\G5_ANGLE45_NATIVE3D_20H_1024\03_best_feasible\` containing
`routes_l3d.json` (same schema, 1024 routes / 20 heights / all crossing angles ≥ 45°).

---

## 0. Executive summary

* There is **no env var and no CLI flag anywhere** in either model. I grepped both
  trees for `argparse`, `os.environ`, `getenv`, `sys.argv`: **zero hits**.
  Every path is a module-level Python constant.
* To point a model at a new geometry you must either (a) edit constants in a
  **copy** of the experiment tree, or (b) import the modules and override the
  constants at run time from a small driver script. Neither requires touching
  the frozen G4 experiment.
* The new directory must contain **8 input files**, not just `routes_l3d.json`.
  `load_dataset()` unconditionally reads `SHA256.json`, `assignment_1024.csv`,
  `layer_planes.json`, `physical_layer_stack.json`, `process_rules.json`,
  `crossing_stats.json`, `BEST_VALID.json`, `validation.json`.
  **This is the single biggest hidden blocker for G5.**
* There are **two independent hash locks** on `routes_l3d.json` in CTP-1.0
  (`src/config.py:32` and `src/dataio.py:15`, the latter raising at
  `src/dataio.py:179-182`). CTP-2.0 has the same constant but only reports a
  boolean, it never raises.
* **The most dangerous silent-reuse path** is the crossing list:
  CTP-1.0 `run_e5.py` reads `outputs/geometry/crossing_events_detected.csv`
  produced by `run_e4.py`, and CTP-2.0 `load_crossings()` silently falls back to
  **CTP-1.0's G4 crossing CSV**. If you forget to re-derive crossings, you get
  the G4 geometry's 1283 events inside a "G5" run with no error and no warning.

---

## 1. CTP-1.0 — every place the input geometry is referenced

Root: `OpticalWaveguideRouter2D\experiments\CROSSTALK_PREDICTION_20H_1283_1024\`

### 1.1 Constants that define *where the geometry comes from*

| # | File:line | Constant / argument | Current value | Effect / lock |
|---|---|---|---|---|
| 1 | `src\config.py:11` | `PROJECT_ROOT = Path(__file__).resolve().parents[3]` | `...\OpticalWaveguideRouter2D` | derived; moving the experiment tree changes it |
| 2 | `src\config.py:12` | `EXPERIMENT_ROOT = parents[1]` | this experiment | all outputs go here |
| 3 | **`src\config.py:13-14`** | `BEST_VALID = PROJECT_ROOT/"experiments"/"COLD_START_20_HEIGHT_1024"/"10_best_valid"` | G4 dir | **the input geometry** |
| 4 | `src\config.py:15` | `REPORTS_SRC = .../COLD_START_20_HEIGHT_1024/12_reports` | G4 reports | report cross-links only |
| 5 | `src\config.py:29` | `"best_valid_dir": str(BEST_VALID)` | folded into the emitted YAML | documentation |
| 6 | **`src\config.py:31-32`** | `"routes_sha256_expected": "35d7ebed…b90753"` | G4 hash | written to `input_sha256_check.json`; used by the manifest |
| 7 | `src\config.py:33-38` | `total_length_mm_expected 156597.221522`, `crossing_events_expected 1283`, `crossing_pairs_expected 1221`, `planes_expected 20`, `routes_expected 1024` | G4 truth | `experiment` bookkeeping; `e1`/`e5` assertions |
| 8 | `src\config.py:38` | `"verify_sha256": True` | on | master switch for lock #9 |
| 9 | **`src\dataio.py:15`** | `ROUTES_SHA256 = "35d7ebed…b90753"` | G4 hash | **hard lock** |
| 10 | `src\dataio.py:16-18` | `TOTAL_LENGTH_MM`, `EXPECTED_CROSSINGS`, `EXPECTED_CROSSING_PAIRS` | G4 truth | imported by `src/lengths.py:10`; `e1` asserts the length |
| 11 | **`src\dataio.py:150-182`** | `load_dataset(root, verify_hash)` | — | raises `RuntimeError` if any *critical* payload mismatches `SHA256.json` **or** if `routes_l3d.json` ≠ `ROUTES_SHA256` (lines 175-182) |
| 12 | `src\dataio.py:158-162` | `critical = {routes_l3d.json, assignment_1024.csv, layer_planes.json, physical_layer_stack.json, process_rules.json, crossing_stats.json, validation.json}` | — | the files that must exist and self-match |
| 13 | `src\dataio.py:186-199` | `read_json(root/…)` for routes, layer_planes, physical_layer_stack, process_rules, crossing_stats, BEST_VALID, validation + `assignment_1024.csv` | — | **required payload, beyond routes_l3d.json** |
| 14 | **`scripts\run_e1.py:18`** | `load_dataset(BEST_VALID, verify_hash=CONFIG["inputs"]["verify_sha256"])` | — | the only geometry read in e1 |
| 15 | **`scripts\run_e4.py:20-21`** | same call | — | produces the crossing list |
| 16 | **`scripts\run_e5.py:27`** | same call | — | board assembly |
| 17 | `scripts\run_e5.py:29` | `pd.read_csv(geo/"crossing_events_detected.csv")` | from e4 | **silent G4 reuse if e4 not re-run** |
| 18 | `scripts\run_e5.py:30` | `pd.read_csv(out/"crossing_transfer_curve.csv")` | from e3 | angle-only, geometry-independent |
| 19 | `src\figures.py:19,305,343` | `load_dataset(BEST_VALID, verify_hash=False)` | G4 dir | figure regeneration |
| 20 | `src\report.py:69-70` | hard-coded strings `` `CROSSTALK_PREDICTION_20H_1283_1024` `` and `` `COLD_START_20_HEIGHT_1024/10_best_valid` `` | G4 names | report header text only |
| 21 | `src\report.py:12-13,496` | `OPT/GEO = EXPERIMENT_ROOT/outputs/...`; writes `reports\SIMULATION_REPORT.md` | — | output paths |
| 22 | `tests\test_pipeline.py:15,22,29,36`; `tests\test_geometry.py:12,17` | `from src.config import BEST_VALID` + `load_dataset(BEST_VALID)` | G4 dir | tests fail on a new geometry |
| 23 | `scripts\run_manifest.py:11,17-20` | `best = Path(CONFIG["inputs"]["best_valid_dir"])`; re-hashes every file; rewrites `config/simulation_config.yaml` | — | manifest |
| 24 | `scripts\run_e1.py:33` | `write_yaml(EXPERIMENT_ROOT/"config"/"simulation_config.yaml", CONFIG)` | — | **e1 rewrites the YAML in place** |

Side effects to be aware of even in a read-only spirit:

* `scripts\run_e1.py:26-33` writes `outputs\geometry\{route_lengths,propagation_loss}.csv`,
  `e1_summary.json`, `input_sha256_check.json` **and rewrites `config\simulation_config.yaml`**.
  If `BEST_VALID` is unchanged the YAML is byte-identical (verified, §4 of
  `BASELINE_RERUN.md`); if it is changed, the `best_valid_dir:` line changes.
* `scripts\run_e5.py:68` writes `cache\crosstalk_matrix_linear.npy`.
* `scripts\run_e3.py:73` incrementally writes `cache\crossing_curve_REF.json`
  after every angle (so e3 is resumable but **never re-solves an angle it
  already has**).
* No script creates `cache\` before writing except `run_e3.py:26`
  (`cache.mkdir(parents=True, exist_ok=True)`); `run_e5.py:68` assumes `cache\`
  already exists.

### 1.2 Crossings are a *derived* quantity — do not inherit them

`run_e4.py` is the only stage that computes the 1283 events
(`src\interactions.py::detect_crossings` / `near_approaches`, `run_e4.py:25,56`).
`run_e5.py` never re-derives them, and `src\board.py:73-97` simply iterates the
CSV rows. For G5 the **angle distribution is the whole point of the
experiment**, so re-running e4 is mandatory (243 s, §5).

---

## 2. CTP-2.0 — every place the input geometry is referenced

Root: `work\1130-report-materials\experiments\CROSSTALK_PREDICTION_CTP2_20H_1283_1024\`

### 2.1 Constants

| # | File:line | Constant / argument | Current value | Effect / lock |
|---|---|---|---|---|
| 1 | `src\ctp2\params.py:56-57` | `_HERE`; `EXPERIMENT = _HERE.parents[2]` | this experiment | output roots |
| 2 | `src\ctp2\params.py:58` | `REPO_ROOT = _HERE.parents[4]` | `...\1130-report-materials` | base for the input dir |
| 3 | **`src\ctp2\params.py:61`** | `BEST_VALID = REPO_ROOT/"experiments"/"COLD_START_20_HEIGHT_1024"/"10_best_valid"` | G4 dir | **the input geometry** |
| 4 | **`src\ctp2\params.py:60`** | `CTP1_DIR = REPO_ROOT/"experiments"/"CROSSTALK_PREDICTION_20H_1283_1024"` | CTP-1.0 dir | **crossing-list fallback source** |
| 5 | `src\ctp2\params.py:42` | `ROUTES_SHA256 = "35d7ebed…b90753"` | G4 hash | **report only** — `geometry.py:78` sets `routes_sha256_matches_frozen`; nothing raises |
| 6 | `src\ctp2\params.py:34-41` | `N_ROUTES 1024`, `N_PLANES 20`, `N_CROSSINGS 1283`, `N_CROSSING_PAIRS 1221`, `N_ROUTES_WITH_CROSSINGS 647`, `TOTAL_LENGTH_MM 156597.221522` | G4 truth | used by `tests\test_ctp2.py` and the report, not by the solver |
| 7 | `src\ctp2\params.py:76-85` | `FROZEN_INPUTS = (routes_l3d.json, assignment_1024.csv, layer_planes.json, physical_layer_stack.json, process_rules.json, crossing_stats.json, validation.json, SHA256.json)` | — | the **8-file payload** contract |
| 8 | **`src\ctp2\geometry.py:304-307`** | `load_routes(path: Path \| None = None)`; default `BEST_VALID/"routes_l3d.json"` | — | **only existing path override in either codebase** |
| 9 | **`src\ctp2\geometry.py:373-381`** | `load_crossings()` → `OUT_CROSSINGS/"crossing_events_verified.csv"` if present, else `_read_legacy_crossings()` | — | **no path argument; falls back to CTP-1.0's G4 CSV** |
| 10 | `src\ctp2\geometry.py:384-392` | `_read_legacy_crossings()` → `CTP1_DIR/outputs/geometry/crossing_events_detected.csv` | G4 CSV | the silent-reuse hazard |
| 11 | `src\ctp2\geometry.py:400-402` | `official_crossing_totals()` → `BEST_VALID/"crossing_stats.json"` | G4 json | `verify_crossings()` only |
| 12 | **`scripts\run_board_ctp2.py:238`** | `routes = G.load_routes()` | default path | geometry read |
| 13 | **`scripts\run_board_ctp2.py:241`** | `crossings = G.load_crossings()` | default fallback | geometry read |
| 14 | `scripts\run_board_ctp2.py:63` | `pd.read_csv(OUT_CROSSINGS/"crossing_model_database.csv")` | angle-only DB | **geometry-independent, reusable** |
| 15 | **`scripts\run_v5_near_approaches.py:69-70`** | `G.load_routes()`, `G.load_crossings()` | default | cross-layer near-approach integration |
| 16 | `config\simulation_config.yaml:14-23` | `best_valid_dir`, `routes_sha256_expected`, expected counts, `verify_sha256: true` | G4 | **documentation only** — nothing parses this YAML at run time |
| 17 | `tests\test_ctp2.py:40,52,159` | `verify_inputs()`, `verify_crossings()`, required deliverable list | G4 | acceptance self-check |

**Stages that do NOT touch route geometry (all reusable as-is for G5):**
`run_v1_modes.py` (modes), `run_v2_coupling.py` (κ database),
`run_v3_crossings.py` (local crossing kernel, 1°–90° in 0.25° steps; 201 angles),
`run_v6_multimode.py`, `run_sensitivity.py`, `make_figures.py` (figures read
`outputs/`), `src/fullwave/*`. Only **V5** and **run_board** are geometry-bound.

### 2.2 CTP-2.0 has no hash lock — but it also has no crossing detector

* `verify_inputs()` exists (`geometry.py:36-80`) and is called **only** from
  `tests\test_ctp2.py:40`. It returns a dict of `match` flags; it never raises.
  So CTP-2.0 will happily run on a new `routes_l3d.json` — *and* happily report
  `routes_sha256_matches_frozen: false`, which a reviewer will notice.
* `load_crossings()` has **no** geometry-of-its-own. CTP-2.0 inherits the
  crossing list from CTP-1.0's e4 output. For G5 you therefore still need
  CTP-1.0's `run_e4.py` (or an equivalent analytic crossing engine) on the new
  routes — this is the one place where the two codebases are coupled.

---

## 3. What exactly must change for `03_best_feasible\`

### 3.1 Input payload (blocker #1 — do this first)

`03_best_feasible\` is currently **empty**. It must be built into a
CTP-loadable dataset:

| File | Required by | Note |
|---|---|---|
| `routes_l3d.json` | both | the G5 solution |
| `SHA256.json` | `dataio.py:152`, `geometry.py:39` | must index every payload file with `{sha256, bytes}`; it is the *trust root* |
| `assignment_1024.csv` | `dataio.py:188` | source/target assignment |
| `layer_planes.json` | `dataio.py:195` | 20 heights |
| `physical_layer_stack.json` | `dataio.py:196` | layer stack |
| `process_rules.json` | `dataio.py:197` | D56/R15/clearance rules |
| `crossing_stats.json` | `dataio.py:198`, `geometry.py:401` | must agree with the crossings e4 re-derives |
| `validation.json` | `dataio.py:200` | validator report |
| `BEST_VALID.json` | `dataio.py:199` | human manifest; **not** in the `critical` set, so a stale hash here is tolerated (this is exactly the pre-existing G4 `BEST_VALID.json` mismatch, `dataio.py:154-157`) |
| `validation\validation.json`, `validation\validator_consistency_tests.json` | `dataio.py:163-174` if listed in `SHA256.json` | optional but present in G4 |

Safest construction: **copy the 8–10 G4 payload files, replace only
`routes_l3d.json`, then regenerate `SHA256.json` and `crossing_stats.json`
from the new geometry.** Do *not* hand-edit `SHA256.json` hashes.

### 3.2 Minimal edit set — CTP-1.0 (2 constants + 2 hash truths)

In a **copy** of the experiment tree (never in the G4 tree):

1. `src\config.py:13-14` → point `BEST_VALID` at `03_best_feasible`.
2. `src\config.py:31-32` → new `routes_sha256_expected`.
3. `src\config.py:33-38` → new `total_length_mm_expected`, `crossing_events_expected`,
   `crossing_pairs_expected` (leave `planes_expected 20`, `routes_expected 1024`).
4. `src\dataio.py:15` → new `ROUTES_SHA256` (**this is the raising lock**).
5. `src\dataio.py:16-18` → new `TOTAL_LENGTH_MM`, `EXPECTED_CROSSINGS`,
   `EXPECTED_CROSSING_PAIRS` (else `lengths.py:10` + `run_e1.py:39` assert-fail).
6. `src\report.py:69-70` → cosmetic header text.
7. `tests\*` → will fail by construction; either skip or parametrise.

### 3.3 Minimal edit set — CTP-2.0 (1 constant, or 0 with a driver)

Preferred (no edit at all) — a driver that overrides at run time:

```python
# experiments\G5_...\05_ctp2_comparison\run_board_g5.py   (new file, outside both trees)
import sys, pathlib
EXP = pathlib.Path(r"...\work\1130-report-materials\experiments\CROSSTALK_PREDICTION_CTP2_20H_1283_1024")
sys.path.insert(0, str(EXP / "src"))
from ctp2 import params, geometry as G
G5 = pathlib.Path(r"...\OpticalWaveguideRouter2D\experiments\G5_ANGLE45_NATIVE3D_20H_1024\03_best_feasible")
params.BEST_VALID = G5                     # geometry.py imports the *name*, so also:
G.BEST_VALID = G5
G.OUT_CROSSINGS = pathlib.Path(r"...\05_ctp2_comparison\ctp2_out\crossings")  # keep G4 outputs untouched
# then: routes = G.load_routes(G5 / "routes_l3d.json")   <-- explicit path, the only supported override
```

Caveats that make the driver-only route risky:
* `geometry.py:23-25` does `from .params import BEST_VALID, …`, so patching
  `params.BEST_VALID` alone does **not** rebind `geometry.BEST_VALID`; patch both.
* `OUT_CROSSINGS`/`OUT_BOARD` are imported into the same modules
  (`run_board_ctp2.py:48-49` imports them by value), so an output redirect must
  patch `run_board_ctp2.OUT_BOARD` too, or you will overwrite G4 outputs.
* `load_crossings()` has no path argument — the clean way is to write
  `OUT_CROSSINGS\crossing_events_verified.csv` for G5 (that file is absent in
  the G4 tree, so its **presence is the switch**).

Therefore the **safer** variant is a **full copy** of
`CROSSTALK_PREDICTION_CTP2_20H_1283_1024` into
`05_ctp2_comparison\ctp2_g5\` with exactly one line edited:
`src\ctp2\params.py:61` → the G5 dir. Everything else (params, kernels, DBs)
is copied or symlinked read-only.

### 3.4 Minimal edit set — if you keep CTP-1.0 in the loop

CTP-1.0 is only needed for its **geometry engine** (`run_e4.py`). That still
needs edits 1, 4, 5 above (the hash + expected counts) because
`run_e4.py:20` calls `load_dataset(BEST_VALID, verify_hash=True)`.
Alternative with zero edits: run e4 in a **mirror tree** (§6) whose
`BEST_VALID` is a directory containing the *G5* payload — the mirror is a copy,
so no frozen file is touched.

---

## 4. Cache / intermediate invalidation

### 4.1 CTP-1.0

| Artefact | Path | Depends on geometry? | Action on new geometry |
|---|---|---|---|
| angles → T_cross curve | `cache\crossing_curve_REF.json` | **NO** (angle + cross-section only) | keep / reuse |
| board matrix cache | `cache\crosstalk_matrix_linear.npy` | **YES** | **delete** |
| crossing events | `outputs\geometry\crossing_events_detected.csv` | **YES** | **regenerate (e4)** |
| near approaches | `outputs\geometry\interaction_regions.csv` | **YES** | **regenerate (e4)** |
| per-route lengths / loss | `outputs\geometry\{route_lengths,propagation_loss}.csv` | **YES** | regenerate (e1) |
| layer stats | `outputs\geometry\layer_statistics.csv` | **YES** | regenerate (e5) |
| e1 / e4 summaries | `outputs\geometry\{e1,e4}_summary.json` | **YES** | regenerate |
| input hash record | `outputs\geometry\input_sha256_check.json` | **YES** | regenerate |
| mode DB | `outputs\optical\mode_reference.npz`, `single_waveguide_modes.csv`, `mode_convergence.csv`, `mode_sweep.csv`, `e2_summary.json` | **NO** | **reuse byte-identically** (verified, §`BASELINE_RERUN.md` 4) |
| κ database | `outputs\optical\coupling_coefficients.csv`, `coupling_parameter_sweep.csv`, `coupling_vertical_offsets.csv` | **NO** | reuse |
| crossing curve | `outputs\optical\crossing_transfer_curve.csv`, `e3_summary.json` | **NO** | reuse (covers 5°–90°; G5 needs ≥45° only) |
| sensitivity | `outputs\optical\sensitivity_summary.csv`, `e6_summary.json` | **NO** | reuse |
| per-event optics | `outputs\optical\crossing_optical_analysis.csv` | **YES** | regenerate (e5) |
| matrices / per-route / hotspots | `outputs\optical\{crosstalk_matrix_*, crosstalk_per_route.csv, crosstalk_hotspots.json, e5_summary.json}` | **YES** | **regenerate (e5)** |
| figures | `outputs\figures\*` | mostly YES | regenerate (`make_figures.py`) |
| manifest / report | `outputs\optical\simulation_manifest.json`, `reports\SIMULATION_REPORT.md` | YES | regenerate |
| `config\simulation_config.yaml` | — | rewritten by e1/manifest | check the `best_valid_dir:` line |

⚠️ **Trap:** `run_e5.py` reads `crossing_events_detected.csv` with no staleness
check and no geometry stamp. A G5 run that reuses the G4 CSV produces a
plausible-looking "G5" matrix built from G4 crossings. Delete the file, or
write each round into its own tree.

### 4.2 CTP-2.0

| Artefact | Path | Depends on geometry? | Action |
|---|---|---|---|
| channel modes | `cache\channel_modes_ref.npz`, `cache\eim_reference.npz` | NO | reuse |
| crossing kernels | `cache\audit\*.npz` (~40 files, ~700 MB), `cache\fullwave\*.json` | **NO** (angle/sep only) | reuse — this is 90 % of the 25 min |
| board matrices | `outputs\board\crosstalk_matrix_ctp2_*.npy`, `_db.csv`, `crosstalk_per_route_ctp2.csv` | **YES** | regenerate (1.9 s) |
| board summary | `outputs\board\board_summary_ctp2.json` | **YES** | regenerate |
| per-event optics | `outputs\board\crossing_optical_analysis_ctp2.csv` | **YES** | regenerate |
| hotspots | `outputs\board\crosstalk_hotspots_ctp2.json` | **YES** | regenerate |
| crossing kernel DB | `outputs\crossings\crossing_model_database.csv` (201 angles, 1–90°) | **NO** | **reuse** |
| near approaches | `outputs\crossings\near_approaches_ctp2.csv` (13.7 MB), `near_approach_integrated_coupling.csv`, `near_approach_summary.json` | **YES** | regenerate (21 s) |
| verified crossings | `outputs\crossings\crossing_events_verified.csv` | — | **absent** in the G4 tree; writing it for G5 is the clean switch |
| figures | `outputs\figures\*` | partly | regenerate |

---

## 5. Per-stage runtime (measured, this machine)

### CTP-1.0 (`OpticalWaveguideRouter2D`)

| Stage | Script | Recorded runtime | Source of truth |
|---|---|---:|---|
| E1 geometry + lengths + loss | `run_e1.py` | **0.59 s** (wall 0.85 s) | measured this session, `logs\e1_rerun.log` |
| E2 modes + convergence | `run_e2.py` | **5.8 s** (wall 6.50 s) | measured this session, `logs\e2_rerun.log` |
| E3 κ database + 17-angle FDFD | `run_e3.py` | **437.8 s** ≈ 7.3 min | `outputs\optical\e3_summary.json` `runtime_seconds` |
| E4 crossings + near approaches | `run_e4.py` | **243.0 s** ≈ 4.1 min | `outputs\geometry\e4_summary.json` `runtime_seconds` |
| E5 board 1024×1024 | `run_e5.py` | **1.07 s** | `outputs\optical\e5_summary.json` `runtime_seconds` |
| E6 sensitivity | `run_e6.py` | **364.0 s** ≈ 6.1 min | `outputs\optical\e6_summary.json` `runtime_seconds` |
| figures / manifest / report | `make_figures.py`, `run_manifest.py`, `run_report.py` | seconds | README:27-28 |

Full pipeline ≈ 17.5 min, of which e3 + e6 = 13.4 min are **geometry-independent**.

### CTP-2.0 (`work\1130-report-materials`)

| Stage | Script | Runtime | Source |
|---|---|---:|---|
| V1 modes | `run_v1_modes.py` | 119.8 s | `logs\run_v1_modes.log` |
| V2 coupling | `run_v2_coupling.py` | 115.5 s | `logs\run_v2_coupling.log` |
| V3/V4 crossing kernel DB (201 angles) | `run_v3_crossings.py` | 350.2 s | `outputs\crossings\crossing_database_summary.json` |
| V5 near approaches | `run_v5_near_approaches.py` | 21.1 s | `logs\run_v5_near.log` |
| V6 multimode | `run_v6_multimode.py` | 247.4 s | `logs\run_v6.log` |
| board | `run_board_ctp2.py` | **1.90 s** | `outputs\board\board_summary_ctp2.json` |
| sensitivity | `run_sensitivity.py` | ~1 min | `logs\run_sensitivity.log` |
| figures | `make_figures.py` | ~30 s | `logs\make_figures.log` |
| **total** | | **≈ 25 min** (README:53) | |

**For a G5 rerun only V5 + board must be re-executed against the new geometry:
21 s + 1.9 s ≈ 23 s, plus the CTP-1.0 e4 (243 s) that supplies the crossings.**
Everything expensive (V1–V4, V6) is a function of angle/cross-section only and
is reused unchanged.

---

## 6. Recommended exact command sequence (no frozen file touched)

PowerShell, from the project root
`C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D`.

### Step 0 — sandbox mirrors (copies only)

```powershell
$P   = "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D"
$G5  = "$P\experiments\G5_ANGLE45_NATIVE3D_20H_1024"
$CMP = "$G5\05_ctp2_comparison"
$PY  = "$P\.venv\Scripts\python.exe"

# (a) CTP-1.0 mirror for the geometry engine only (e1 + e4)
$M = "$CMP\ctp1_g5"                       # sandbox; CTP-1.0 read-only source untouched
New-Item -ItemType Directory -Force "$M\experiments" | Out-Null
Copy-Item -Recurse "$P\experiments\CROSSTALK_PREDICTION_20H_1283_1024\src"     "$M\experiments\CROSSTALK_PREDICTION_20H_1283_1024\"
Copy-Item -Recurse "$P\experiments\CROSSTALK_PREDICTION_20H_1283_1024\scripts" "$M\experiments\CROSSTALK_PREDICTION_20H_1283_1024\"
Copy-Item -Recurse "$P\experiments\CROSSTALK_PREDICTION_20H_1283_1024\config"  "$M\experiments\CROSSTALK_PREDICTION_20H_1283_1024\"
#    IMPORTANT: "experiments" must be the 3rd parent of src\config.py, i.e. the
#    mirror root must be $M  ->  $M\experiments\CROSSTALK_PREDICTION_20H_1283_1024\src\config.py
#    then PROJECT_ROOT resolves to $M, not to $P.

# (b) CTP-2.0 mirror (full copy; kernels are reused, nothing is recomputed)
Copy-Item -Recurse "$env:USERPROFILE\Desktop\Graduation Project\work\1130-report-materials\experiments\CROSSTALK_PREDICTION_CTP2_20H_1283_1024" "$CMP\ctp2_g5"
```

### Step 1 — build the G5 payload in `03_best_feasible\`

```powershell
# copy the 8 non-routes payload files from G4, keep only routes_l3d.json of G5
Copy-Item "$P\experiments\COLD_START_20_HEIGHT_1024\10_best_valid\*" "$G5\03_best_feasible\" -Exclude routes_l3d.json
# then drop in the G5 routes_l3d.json and REGENERATE SHA256.json + crossing_stats.json
```

### Step 2 — point the mirrors at the new geometry (the only edits, in copies)

| Mirror file | Line | Change |
|---|---|---|
| `ctp1_g5\...\src\config.py` | 13-14 | `BEST_VALID` → `03_best_feasible` |
| `ctp1_g5\...\src\config.py` | 31-32 | new `routes_sha256_expected` |
| `ctp1_g5\...\src\config.py` | 33-38 | new expected length / crossing counts |
| `ctp1_g5\...\src\dataio.py` | 15 | new `ROUTES_SHA256` (**the raising lock**) |
| `ctp1_g5\...\src\dataio.py` | 16-18 | new `TOTAL_LENGTH_MM`, `EXPECTED_CROSSINGS`, `EXPECTED_CROSSING_PAIRS` |
| `ctp2_g5\src\ctp2\params.py` | 61 | `BEST_VALID` → G5 `03_best_feasible` |
| `ctp2_g5\src\ctp2\params.py` | 58 | `REPO_ROOT` if the copy does not sit at the same depth |
| `ctp2_g5\src\ctp2\params.py` | 60 | `CTP1_DIR` → the **CTP-1.0 G5 mirror** (so crossings come from G5) |

### Step 3 — run

```powershell
# 3a geometry: lengths + loss  (0.6 s)
Push-Location "$M\experiments\CROSSTALK_PREDICTION_20H_1283_1024"; & $PY scripts\run_e1.py; Pop-Location
# 3b crossings + near approaches on G5  (243 s)  <-- the only expensive new step
Push-Location "$M\experiments\CROSSTALK_PREDICTION_20H_1283_1024"; & $PY scripts\run_e4.py; Pop-Location
# 3c CTP-2.0: near-approach coupling on G5 (21 s) then the board (2 s)
Push-Location "$CMP\ctp2_g5"; & $PY scripts\run_v5_near_approaches.py; Pop-Location
Push-Location "$CMP\ctp2_g5"; & $PY scripts\run_board_ctp2.py;          Pop-Location
# 3d G4 reference numbers, for a like-for-like pair, from the *unmodified* G4 outputs
#    -> work\1130-report-materials\...\outputs\board\board_summary_ctp2.json
```

### Step 4 — verify before believing

```powershell
# crossings really are G5: angle_min must be >= 45 deg, not 5.1538
(Get-Content "$CMP\ctp2_g5\outputs\board\board_summary_ctp2.json" | ConvertFrom-Json).crossings
# forward-direction rule must still split 1283-ish events
# and assert: angle_min_deg -ge 45
```

Optional (do **not** do this if CTP-1.0 numbers are needed for continuity only):
the CTP-1.0 board (`run_e5.py`, 1.1 s) can be run in the mirror too, but its
result is a fixed-p bookkeeping baseline, not physics — see `RECOMMENDATION.md`.

### Why a mirror and not an env var

Neither codebase reads the environment; adding one would itself be an edit of a
frozen file. The mirror keeps `git status` clean in
`OpticalWaveguideRouter2D` and in `work\1130-report-materials`, and it makes the
G5 numbers land in a separate directory by construction, so the G4 outputs
cannot be clobbered.
