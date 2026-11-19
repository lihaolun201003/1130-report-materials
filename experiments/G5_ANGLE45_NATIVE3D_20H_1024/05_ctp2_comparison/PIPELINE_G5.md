# Running CTP-2.0 on the G5 geometry — copy, redirection, crossing regeneration, faithfulness

Status: **Phase A complete** (copy + redirection + faithfulness proof + driver).
Phase B (the G5 numbers) runs as soon as
`experiments\G5_ANGLE45_NATIVE3D_20H_1024\03_best_feasible\routes_l3d.json`
exists; see §10 for the single command.

Everything in this document is reproducible from the artefacts listed in §12.
No file in either frozen tree was created, modified or deleted; §9 has the
hash evidence.

---

## 0. Summary of what was built

| # | Deliverable | Path |
|---|---|---|
| 1 | full copy of the CTP-2.0 experiment tree | `05_ctp2_comparison\ctp2_g5\` |
| 2 | two-file edit of the copy (geometry + output redirection) | `ctp2_g5\src\ctp2\{params,geometry}.py` |
| 3 | faithfulness proof against the frozen G4 payload | `05_ctp2_comparison\faithfulness\faithfulness_proof.json` |
| 4 | driver: payload builder, crossing regeneration, V5 + board, comparison | `05_ctp2_comparison\run_ctp2_g5.py` |
| 5 | independent crossing detector validation on G4 | `05_ctp2_comparison\frozen_guard\detector_validation_on_g4.json` |
| 6 | frozen-tree guard (hash + mtime snapshot / verify) | `05_ctp2_comparison\tools\frozen_guard.py` |
| 7 | this document | `05_ctp2_comparison\PIPELINE_G5.md` |

A **G4 self-test** of the whole Phase-B path (payload → crossings → audit
cross-check → V5 → board → comparison) was run with the frozen G4 routes into a
throw-away root. It exercised every code path Phase B uses, and its two table
columns agreed exactly (same geometry on both sides), which also cross-checks the
comparison rendering. It produced the reference value for the bound-share row:
**for G4 only 1.89e-03 % of the forward-coupled power comes from floor-limited
crossings** — quantitatively confirming that the published G4 numbers are
resolved values, not bounds. Log: `logs\g4selftest.log` (report artefacts since
removed).

---

## 1. The copy

```
source : work\1130-report-materials\experiments\CROSSTALK_PREDICTION_CTP2_20H_1283_1024
dest   : experiments\G5_ANGLE45_NATIVE3D_20H_1024\05_ctp2_comparison\ctp2_g5
method : robocopy /E /XD __pycache__        (exit 1 = files copied, no errors)
size   : 323 files, 691,544,309 bytes (659.5 MiB) at copy time
```

The copy is **complete**: `src\`, `scripts\`, `config\`, `docs\`, `audit\`,
`reports\`, `tests\`, `benchmarks\`, `logs\`, `outputs\` and `cache\` are all
present.

**Nothing was hardlinked or junctioned.** The task allowed hardlinking `cache\`
(597 MiB) and the optical reference outputs; copying instead is strictly safer,
because a write through a hardlink would have modified the *frozen* inode. So

* `cache\` — **copied** (132 files, 597 MiB): the geometry-independent numerical
  cache (`channel_modes_ref.npz`, `eim_reference.npz`, `cache\audit\*.npz`,
  `cache\fullwave\*`, `cache\lead\*`). The G5 stages do not write it.
* `outputs\` — **copied** (70 files, 61 MiB), including the 44.7 MiB of G4 board
  matrices. It is kept as a *read-only provenance snapshot* of the published
  CTP-2.0 outputs; **nothing writes it at run time** because every `OUT_*`
  constant was redirected to `ctp2_out\` (§3). Verified by mtime: after two full
  pipeline runs, the newest file under `ctp2_g5\outputs\` is still the copy
  itself, and only `src\ctp2\{params,geometry}.py` plus `__pycache__` carry new
  timestamps.

> Naming note: the task referred to `outputs\optical\mode_reference.npz` /
> `crossing_model_database.csv`. CTP-2.0 has no `outputs\optical\`; the mode
> reference is `cache\channel_modes_ref.npz` and the crossing kernel is
> `outputs\crossings\crossing_model_database.csv`. Both are present in the copy.

---

## 2. The exact diff

`tools\diff_copy.py` hashes every file of `src/ scripts/ config/ tests/ docs/` in
the frozen tree and in the copy:

```
[diff] frozen=53 copy=53 changed=2 added=0 removed=0
  CHANGED src/ctp2/geometry.py
  CHANGED src/ctp2/params.py
```

Unified diff: `frozen_guard\params_geometry.diff`.
Machine-readable record: `frozen_guard\copy_diff.json` (stores both sha256 per
changed file).

### 2.1 `src\ctp2\params.py` — the only behavioural edit

| constant | frozen value | copy value |
|---|---|---|
| `BEST_VALID` | `REPO_ROOT/experiments/COLD_START_20_HEIGHT_1024/10_best_valid` | `G5_EXPERIMENT/03_best_feasible` (overridable by `CTP2_BEST_VALID`) |
| `OUT_MODES` … `OUT_FULLWAVE` | `EXPERIMENT/outputs/*` | `OUT_ROOT/*` with `OUT_ROOT = G5_EXPERIMENT/05_ctp2_comparison/ctp2_out` (overridable by `CTP2_OUT_ROOT`) |
| `CACHE` | `EXPERIMENT/cache` | unchanged in meaning: the copy's own `ctp2_g5/cache` |
| `CTP1_DIR` | `REPO_ROOT/experiments/CROSSTALK_PREDICTION_20H_1283_1024` | the routing project's `experiments\CROSSTALK_PREDICTION_20H_1283_1024` (same content; used only by the explicit legacy loader) |
| `TOTAL_LENGTH_MM`, `N_CROSSINGS`, `N_CROSSING_PAIRS`, `N_ROUTES_WITH_CROSSINGS`, `ROUTES_SHA256`, `N_ROUTES` | G4 truths as literals | G4 truths as `G4_REF_*` defaults, each overridable by `CTP2_*` so the driver can hand the model the **G5** payload's own numbers |

The physical constants (`ALPHA_DB_PER_CM = 0.05`, `BEND_EXTRA_LOSS_DB = 0.0`,
`WAVELENGTH_NM = 1310`, `N_CLAD = 1.50`, `DELTA_N = 0.0065`, `CORE_W_UM/H_UM = 9`,
`PLANE_HEIGHTS_MM`, the `Optics` dataclass, the sensitivity presets, the crossing
angles and separation tables) are **byte-identical**. `EXPERIMENT` is derived
from `__file__` so it correctly becomes the copy; `PROJECT_ROOT`,
`G5_EXPERIMENT`, `COMPARISON_DIR` are new literals because the copy no longer
sits at the same depth as the frozen tree.

Every override is resolved **at import time** so modules that do
`from .params import TOTAL_LENGTH_MM, OUT_BOARD, …` see the overridden value.
That is also why the two pipeline stages are launched as subprocesses rather
than imported.

### 2.2 `src\ctp2\geometry.py` — the silent-fallback trap is closed

The frozen `load_crossings()` read `OUT_CROSSINGS\crossing_events_verified.csv`
if it existed and otherwise **silently fell back to CTP-1.0's G4 crossing CSV**
(`_read_legacy_crossings()`). In a G5 run that is the one failure mode that
produces plausible-looking numbers from the wrong geometry. In the copy:

```python
if not csv_path.exists():
    raise RuntimeError("crossing_events_verified.csv is missing ... the G4 legacy
                        fallback is DISABLED in this work copy ...")
```

`_read_legacy_crossings()` still exists (the faithfulness harness calls it
*explicitly* to reproduce the G4 list) but nothing calls it implicitly.

Two cosmetic changes: the module docstring, and `verify_crossings()` no longer
hard-codes `1221`/`647` — it compares against the geometry's own
`crossing_stats.json`. `verify_inputs()` now reports `best_valid_dir`,
`routes_sha256_expected` and the payload's `N_CROSSINGS` instead of a literal
`1283`.

> Encoding note: the frozen `geometry.py` carried a UTF-8 BOM; it was restored in
> the copy so the diff contains content changes only (`tools\check_encoding.py`).

---

## 3. How the outputs are redirected

```
05_ctp2_comparison\
  ctp2_g5\            <- the model (code) ; its own outputs\ is never written
  ctp2_out\           <- ALL run-time outputs
      board\          crosstalk_matrix_ctp2_{linear,lower,upper}.npy, _db.csv,
                      crosstalk_per_route_ctp2.csv, crossing_optical_analysis_ctp2.csv,
                      crosstalk_hotspots_ctp2.json, board_summary_ctp2.json
      crossings\      crossing_events_verified.csv   <- the switch for load_crossings()
                      crossing_model_database.csv    <- seeded, angle-only, reused
                      near_approaches_ctp2.csv, near_approach_summary.json, ...
      coupling\  modes\  figures\  fullwave\
      reference_seed.json, runtimes.json, logs\
  ctp2_out_faithfulness\   <- the G4 reproduction run (separate root, on purpose)
  ctp2_out_detector_check\ <- scratch root used by the G4 detector probes
```

There is therefore **no code path** by which a G5 run can write
`work\1130-report-materials\...\CROSSTALK_PREDICTION_CTP2_20H_1283_1024\outputs\`
or `experiments\COLD_START_20_HEIGHT_1024\10_best_valid\`: the constants are
absolute paths into `05_ctp2_comparison`, and the only reads of the frozen trees
are `open(..., "rb")` / `pd.read_csv` / `json.loads`.

Geometry-independent reference outputs are **seeded** into `ctp2_out\` on every
run (only if absent) and recorded in `ctp2_out\reference_seed.json` with source
path, sha256 and byte count. The list is `SEED_FILES` in the driver: the 201-row
crossing kernel database and its four supporting CSVs, the multimode tables, the
V1 mode tables and the V2 coupling tables. Never seeded: anything under
`board\` and the `near_approach*` / `crossing_events_verified` products.

---

## 4. What is *not* re-run, and why

| stage | runtime (published) | geometry-dependent? | action |
|---|---:|:---:|---|
| V1 modes (`run_v1_modes.py`) | 119.8 s | no | reuse `outputs\modes\*`, `cache\channel_modes_ref.npz` |
| V2 coupling (`run_v2_coupling.py`) | 115.5 s | no | reuse `outputs\coupling\*` |
| V3/V4 crossing kernel, 201 angles (`run_v3_crossings.py`) | 350.2 s | no (angle + cross-section only) | reuse `outputs\crossings\crossing_model_database.csv` |
| V6 multimode (`run_v6_multimode.py`) | 247.4 s | no | reuse `outputs\crossings\multimode_*` |
| sensitivity (`run_sensitivity.py`) | ~60 s | no | reuse `outputs\coupling\sensitivity_*` |
| **V5 near approaches** | **17 s** | **yes** | **re-run** |
| **board (`run_board_ctp2.py`)** | **2.6 s** | **yes** | **re-run** |
| crossing regeneration (this work) | 3.4 s | yes | **new step** |

The kernel database is a function of the crossing angle only (1°–90° in 0.25°
steps); the crossing *count* and *angles* change for G5, but the per-angle
transfer does not. That is what makes a ~25 s G5 rerun legitimate instead of the
full 25 min.

---

## 5. How the crossing list is regenerated

### 5.1 Why it must be regenerated

CTP-2.0 has **no crossing detector**. Its `load_crossings()` is a file reader.
The G5 geometry has different crossings (routes re-heighted, angles forced
≥45°), so reusing any existing list would produce a "G5" board built from G4
events — the trap documented in `investigation\PIPELINE_PARAMETERISATION.md` §0.

### 5.2 Method — an independent analytic detector

`run_ctp2_g5.py :: detect_crossings()` is a direct port of CTP-1.0's exact
geometry engine (`src\interactions.py`: `_line_line`, `_line_circle`,
`_circle_circle`, `_unwrap_arc_angle`, `segment_intersections`,
`detect_crossings`) onto CTP-2.0's analytic primitives. It reads only
`routes_l3d.json`:

1. every flat part's `line`/`arc` primitives are enumerated with their global
   arc length, mirroring `geometry._build_segments` (asserted: the reconstructed
   arclength equals `Route.total_length` to 1e-6 mm for every route);
2. primitives are bucketed by `round(z, 6)` — a same-height crossing needs two
   constant-z primitives at the same z;
3. each pair in a bucket is AABB-rejected, then solved exactly
   (line/line, line/circle, circle/circle) with arc-span unwrapping;
4. the crossing angle is `acos(|t_a · t_b|)` from the analytic tangents;
5. coincident duplicates (same pair, same z, <1 µm apart) are removed with
   CTP-1.0's exact rule, and `transverse = angle_deg >= 1°`.

It costs 1.68 M primitive-pair tests and **3.4 s** for 1024 routes.

### 5.3 Schema — what CTP-2.0 actually consumes, and the mapping

`load_crossings()` returns each CSV row as a **string dict**;
`run_board_ctp2.build_events()` casts exactly eight fields:

| field | used for |
|---|---|
| `route_a`, `route_b` | route lookup, direction rule |
| `s_a_mm`, `s_b_mm` | `A.tangent(s)`, `A.total_length - s` propagation factors |
| `x_mm`, `y_mm`, `z_mm` | hotspot clustering |
| `angle_deg` | log–log interpolation of the crossing kernel |

`part_index_*`, `kind_*`, `z_a_mm`, `z_b_mm`, `transverse` are never read by
CTP-2.0; they are carried because they exist in CTP-1.0's
`crossing_events_detected.csv` and in the G5 audit CSV.

Delivered columns (17):

```
crossing_id, route_a, route_b, z_mm, z_label, x_mm, y_mm, angle_deg,
kind_a, kind_b, s_a_mm, s_b_mm, part_index_a, part_index_b,
z_a_mm, z_b_mm, transverse
```

Mapping from the G5 project's `03_best_feasible\g5_crossing_angles.csv`
(columns `crossing_id, z_mm, z_label, route_a, route_b, x_mm, y_mm, angle_deg,
kind_a, kind_b, s_a_mm, s_b_mm, theta_margin_deg, pass_45`; the older
`00_baseline_audit\baseline_crossing_angles.csv` variant uses
`below_45`/`deficit_deg` instead of the last two — both are accepted):

| delivered column | source |
|---|---|
| `crossing_id` | recomputed, 1-based, rows sorted by `(z_mm, route_a, route_b)` |
| `route_a`, `route_b`, `z_mm`, `x_mm`, `y_mm`, `angle_deg`, `kind_a`, `kind_b` | same name in the audit CSV — **but taken from the detector at full float64 precision** (the audit CSV rounds to 6 dp; agreement is 5.0e-7) |
| `z_label` | `layer_planes.json` (`L2 … L18`, `Z1_INTERFACE`, `Z2_INTERFACE`) — same heights as the audit's `plane_label` |
| **`s_a_mm`, `s_b_mm`** | **detector only.** The audit CSV's arc length uses a different origin — see §5.4 |
| `part_index_a/b`, `z_a_mm`, `z_b_mm`, `transverse` | detector only (absent in the audit CSV); not read by CTP-2.0 |
| `theta_margin_deg`, `pass_45`, `below_45`, `deficit_deg` | not carried; 45° membership is recomputed downstream |

### 5.4 ⚠️ The audit CSV's arc length cannot be used as-is

The G5 project's audit engine reports `s_a_mm`/`s_b_mm` measured from a different
origin than CTP-2.0's `Route.pos()`. Measured on the frozen G4 geometry:
event set identical (1283/1283), `x`/`y`/`angle` identical to **5.0e-7**
(the CSV's own rounding), but the `s` column differs by a **constant per route**
(802 of 807 route entries constant; max |offset| **132.76 mm**).

Feeding those `s` values to CTP-2.0 would evaluate `A.tangent(s_a)` at the wrong
point on the route, which corrupts the propagation-direction rule
(`forward_direction_ok`) and the two propagation-loss factors — silently, with
plausible-looking output. **Therefore `s_a_mm`/`s_b_mm` always come from the
detector**, whose own consistency with CTP-2.0's geometry was verified
independently:

```
max |Route.pos(s_a) - (x, y, z)|        = 1.14e-13 mm
max |Route.pos_a(s_a) - Route.pos_b(s_b)| = 1.17e-13 mm
max |z_a - z_b|                          = 0.0 mm
```

`frozen_guard\s_convention_report.json`, `tools\probe_s_convention.py`.

### 5.5 The detector is validated on G4 before it is trusted on G5

`tools\validate_detector_on_g4.py` runs the detector on the **frozen G4**
geometry, where two independent reference lists exist:

| reference | events | pairs | routes | max position error | max angle error | `s` |
|---|---:|---:|---:|---:|---:|---|
| CTP-1.0 e4 `crossing_events_detected.csv` | 1283 | 1221 | 647 | **1.8e-15 mm** | **4.3e-14 °** | **5.7e-14 mm** |
| G5 project audit engine `baseline_crossing_angles.csv` | 1283 | 1221 | 647 | **5.0e-07 mm** | **5.0e-07 °** | different origin (§5.4) |

and reproduces the published angle histogram of
`00_baseline_audit\baseline_angle_report.md` **exactly**:

```
[0,5) [5,10) [10,20) [20,30) [30,40) [40,45) [45,60) [60,75) [75,90]
    0      17       92       52       92       51      271      514      194
n_below_45 = 304 , min angle = 5.153763 deg
```

`frozen_guard\detector_validation_on_g4.json` — `all_pass = true`.

On G5 the same comparison runs automatically against
`03_best_feasible\g5_crossing_angles.csv`; the driver **aborts** if the event
set differs (any route pair missing on either side) or if positions/angles
disagree beyond 1e-5 mm / 1e-5 ° (`--no-require-audit-agreement` to override).
The comparison is written to
`ctp2_out\crossings\crossing_regeneration_report.json`.

---

## 6. The payload builder

`run_ctp2_g5.py --stages prepare` writes
`05_ctp2_comparison\ctp2_payload_g5\` — a CTP-2.0-loadable dataset:

| file | origin |
|---|---|
| `routes_l3d.json` | copied byte-identically from `--routes` (sha256 re-checked after copy) |
| `assignment_1024.csv`, `layer_planes.json`, `physical_layer_stack.json`, `process_rules.json` | copied from the geometry dir if present, else from the frozen G4 dir; `identical_to_g4_frozen` recorded per file |
| `crossing_stats.json` | **generated** from the regenerated crossing list, in the frozen schema (`totals` / `planes` / `per_route_crossings` / `crossing_events`) |
| `validation.json` | copied from `g5_validation.json` if the geometry dir has one; otherwise an explicit **stub** that says no independent validator report was available. The G4 `validation.json` is deliberately *never* reused — it validates the G4 geometry |
| `BEST_VALID.json` | generated manifest (routes sha256, counts, min angle, the "no inherited crossing list" acceptance rule) |
| `SHA256.json` | **regenerated** over the payload (never hand-edited) |
| `PAYLOAD_PROVENANCE.json` | per-file origin + sha256 + the source paths |

The driver then points the model at this payload via `CTP2_BEST_VALID`.

---

## 7. Faithfulness proof

```
& $py "$CMP\run_ctp2_g5.py" --mode faithfulness
```

What it does: point the **modified copy** at the **frozen G4 payload**, feed it
the frozen G4 crossing list (written via the explicit legacy loader, column-mapped
to the CTP schema), run V5 + board into `ctp2_out_faithfulness\`, and compare the
resulting `board_summary_ctp2.json` with the frozen one.

Results (`faithfulness\faithfulness_proof.json`):

| metric | frozen CTP-2.0 | reproduced by the copy | sig. digits |
|---|---:|---:|---:|
| `max_offdiagonal_db` (R723→R743) | −15.206468704880304 | **−15.206468704880304** | exact |
| `worst_total_leakage_db` (R743) | −14.769540964146534 | **−14.769540964146534** | exact |
| `worst_interference_to_signal_db` (R743) | −12.711747549665644 | **−12.711747549665644** | exact |
| `diagonal_min_db` / `diagonal_max_db` | −1.8789188513758748 / −0.2240693494208043 | identical | exact |
| bounds (pair / leakage, low–high) | −15.906468704880313 … −14.50646870488031 | identical | exact |
| `n_events` / `n_forward_allowed` / `n_forward_blocked` | 1283 / 856 / 427 | identical | exact |
| `angle_min_deg` / `angle_median_deg` | 5.153763467155517 / 63.256316049596855 | identical | exact |
| `T_cross_db_max` | −14.365259750408583 | identical | exact |
| `n_events_above_minus40dB` / `_minus30dB` | 63 / 17 | identical | exact |
| `n_nonzero_offdiagonal` / `max_column_sum` | 3248 / 0.9497144919208746 | identical | exact |
| `second_order.n_terms` / `max_T_db` | 2660 / −37.86998586546566 | identical | exact |
| `baseline_ctp1_fixed_p` pair / leakage | −67.41532751175713 / −60.48486486628533 | identical | exact |
| `frozen_geometry.n_routes` / `n_crossings` / `total_length_mm` | 1024 / 1283 / 156597.22152165722 | identical | exact |

* **36 of 36** checks pass; `headline_all_pass = true`.
* A **full recursive diff** of the reproduced vs frozen `board_summary_ctp2.json`
  finds **exactly one differing leaf**: `runtime_seconds`
  (1.9036781787872314 → 1.9065675735473633). Literally every other number in the
  file is bit-identical.
* The crossing list itself: writing the legacy rows through the CSV path
  reproduces all **10 264** floats with `max |delta| = 0.0` — so the CSV reader
  path and the pandas fallback are numerically the same code path.
* Route/crossing counts: 1024 routes, 1283 events, 1221 pairs, 647 routes with
  crossings, 1 682 399 primitive-pair tests — all identical.
* The detector independently reproduces the same 1283 events (§5.5).

Verdict recorded in the proof: *"FAITHFUL: the copy reproduces the frozen
CTP-2.0 G4 board summary bit-for-bit."*

---

## 8. Runtimes (measured, this machine, `.venv` Python 3.10.11)

| stage | wall time |
|---|---:|
| full tree copy (robocopy, 660 MiB) | 0.5 s |
| crossing regeneration + payload build + seeding (`prepare`) | **3.9 s** |
| of which analytic crossing detection (1 682 399 tests) | 3.4 s |
| V5 near approaches (`run_v5_near_approaches.py`) | **16.9 s** |
| board (`run_board_ctp2.py`) | **2.6 s** |
| **G5 rerun total (`prepare` + V5 + board + compare)** | **≈ 25 s** |
| faithfulness mode (detector + V5 + board + compare) | 24.5 s |
| `frozen_guard snapshot` / `verify` (323 + 11 files, 692 MB) | 4.2 s / 4.0 s |

For comparison, the full published CTP-2.0 pipeline is ≈ 25 min; only ≈ 25 s of
it is geometry-bound.

---

## 9. The frozen trees are untouched

`tools\frozen_guard.py` hashes every file (sha256) and records size + mtime_ns of
both frozen trees before any work, and re-checks them afterwards:

```
[guard] ctp2_model:   before=323 after=323 changed=0 (hash=0) added=0 removed=0
[guard] g4_best_valid: before=11  after=11  changed=0 (hash=0) added=0 removed=0
[guard] CLEAN - frozen trees untouched
  -> frozen_guard\frozen_manifest_before.json
  -> frozen_guard\frozen_verify_after.json
```

Re-run at any time:

```powershell
& $py "$CMP\tools\frozen_guard.py" verify
```

---

## 10. Exact commands to re-run after the geometry is finalised

The finalised geometry may land in **`03_best_feasible\`** (fully legal: zero
sub-45° crossings) or in **`03_best_partial\`** (a partial solution — a residual
sub-45° set that must never be labelled feasible). The driver handles both: with
no `--routes` it takes `03_best_feasible\routes_l3d.json` if that exists, else
`03_best_partial\routes_l3d.json`, and derives the geometry label from the
directory. Both cases produce the same two deliverables
(`g5_ctp2_summary.json`, `g5_ctp2_comparison.md`) with the geometry label and the
residual-event count stated in the report.

```powershell
$PY  = "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\.venv\Scripts\python.exe"
$CMP = "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\experiments\G5_ANGLE45_NATIVE3D_20H_1024\05_ctp2_comparison"

# ---- the whole G5 run (payload -> crossings -> V5 -> board -> comparison)
& $PY "$CMP\run_ctp2_g5.py"

# ---- the same, fully explicit (defaults shown)
& $PY "$CMP\run_ctp2_g5.py" `
    --routes      "...\G5_ANGLE45_NATIVE3D_20H_1024\03_best_partial\routes_l3d.json" `
    --audit-csv   "...\G5_ANGLE45_NATIVE3D_20H_1024\03_best_partial\g5_crossing_angles.csv" `
    --payload-dir "$CMP\ctp2_payload_g5" `
    --out-root    "$CMP\ctp2_out" `
    --geometry-label "G5_ANGLE45_NATIVE3D_20H_1024/03_best_partial"

# ---- partial runs
& $PY "$CMP\run_ctp2_g5.py" --stages prepare,board,compare   # skip V5 (~17 s saved)
& $PY "$CMP\run_ctp2_g5.py" --stages compare                 # re-derive the tables only (0.2 s)

# ---- a different candidate geometry, isolated from the shipped numbers
& $PY "$CMP\run_ctp2_g5.py" `
    --routes "...\03_best_feasible\best_partial\routes_l3d.json" `
    --payload-dir "$CMP\ctp2_payload_partial" --out-root "$CMP\ctp2_out_partial" `
    --geometry-label "G5/best_partial" --report-stem g5_partial

# ---- re-prove the copy is faithful (must stay 36/36, one runtime-only diff)
& $PY "$CMP\run_ctp2_g5.py" --mode faithfulness

# ---- frozen-tree proof and copy diff
& $PY "$CMP\tools\frozen_guard.py" verify
& $PY "$CMP\tools\diff_copy.py"
& $PY "$CMP\tools\validate_detector_on_g4.py"
```

Outputs of the run:

```
ctp2_out\board\board_summary_ctp2.json          raw CTP-2.0 board summary for G5
ctp2_out\board\crossing_optical_analysis_ctp2.csv  per-event angle + T_cross
ctp2_out\crossings\crossing_events_verified.csv the crossings actually used
ctp2_out\crossings\crossing_regeneration_report.json  detection + audit cross-check
ctp2_out\reference_seed.json                    the reused angle-only reference files
g5_ctp2_summary.json                            G5 absolute numbers (+ provenance,
                                                bound fraction, geometry changes)
g5_ctp2_comparison.md                           G4 vs G5 table + anomalies + caveat
logs\g5_<timestamp>.log                         full console log
```

What `g5_ctp2_comparison.md` contains, in order: the headline table (**G4
resolved values and G5 values side by side**, including max base propagation
loss, hotspot count and the crossing total / sub-45° count), the *share of the
forward-coupled power that is a floor-limited upper bound* (G4: 1.89e-03 %, G5:
whatever the run computes — this is the "how much of the number is a bound"
row), secondary metrics, crossing statistics with the full angle-band table and
the kernel-status split, the propagation-loss table, hotspots, the residual
sub-45° event list, the model-resolution caveat, and **§7 geometry anomalies**
(route length/height changes vs G4, and the audit-vs-detector agreement).

---

## 11. The model-resolution caveat (must accompany every G5 number)

CTP-2.0's crossing kernel (`outputs\crossings\crossing_model_database.csv`, 201
angles, 1°–90°) has three validity regions:

| θ | status | trust |
|---|---|---|
| 1–10° | `resolved` (37 rows) | resolved, ±0.7 dB |
| 10–30° | `resolved_fdtd_crosschecked` (44 rows) | resolved, ±2.0 dB |
| 30–45° | `disputed_paraxial` (30 rows) | disputed, bounds only |
| ≥ 45.5° | `upper_bound_port_floor_limited` (90 rows) | **upper bound at the −85 dB FDFD port floor** |

G5 has, by construction, only crossings ≥ 45°. Hence:

* per crossing, `T_cross` is **≤ 3.162e-9 (−85 dB)** — the FDFD numerical floor,
  i.e. an upper bound on the transfer, not a prediction;
* the board-level aggregate metrics are **floor-limited** and must be quoted as
  `≤ x dB`;
* the Born lower bounds (`T_cross_low`) travel with them; the board emits the
  matching `[lower, upper]` matrix pair and the `bounds` block;
* there is a **~12 dB hand-over step** between 45.0° (−72.799 dB,
  `disputed_paraxial`) and 45.5° (−85.000 dB, floor) — a model property, not
  physics. The driver reports `kernel_status.n_handover_bracket` and states which
  side of the step the run sits on;
* both models assume an ideal structure (no sidewall roughness, index drift,
  stress birefringence, bend-induced polarisation conversion), which literature
  says dominates measured large-angle crosstalk — so even the G5 upper bound is a
  *lower* bound on a real device.

`g5_ctp2_comparison.md` §6 states all of this, and marks exactly which table
entries are bounds.

---

## 12. File map

```
05_ctp2_comparison\
  PIPELINE_G5.md                     this document
  run_ctp2_g5.py                     the driver (prepare / v5 / board / compare / faithfulness)
  ctp2_g5\                           full copy of the CTP-2.0 tree (2 files edited)
  ctp2_payload_g5\                   generated payload (created by the first G5 run)
  ctp2_out\                          all G5 run-time outputs
  ctp2_out_faithfulness\             the G4 reproduction run
  g5_ctp2_summary.json               G5 absolute numbers            (Phase B)
  g5_ctp2_comparison.md              G4 vs G5 comparison + caveat   (Phase B)
  faithfulness\
      faithfulness_proof.json        36 checks, full JSON diff
      board_summary_g4_reproduced.json  the reproduced G4 board summary
      v5_g4.log  board_g4.log
  frozen_guard\
      frozen_manifest_before.json    sha256 + mtime of both frozen trees before work
      frozen_verify_after.json       ... and after
      copy_diff.json                 frozen-vs-copy file hashes (2 changed)
      params_geometry.diff           the exact unified diff
      detector_validation_on_g4.json detector vs CTP-1.0 e4 and vs the G5 audit engine
      s_convention_report.json       arc-length-origin finding
  tools\
      frozen_guard.py  diff_copy.py  validate_detector_on_g4.py
      probe_s_convention.py  check_encoding.py
  logs\                              console logs of every run
  investigation\                     the read-only survey that preceded this work
```
