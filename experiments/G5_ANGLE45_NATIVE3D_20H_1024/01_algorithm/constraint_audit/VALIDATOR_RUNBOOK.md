# VALIDATOR RUNBOOK — run the frozen 20-height validator on an arbitrary run dir

**Project root** `C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D`
**Interpreter** `.venv\Scripts\python.exe` (CPython 3.10.11, numpy 2.2.6, scipy 1.15.3)
**Verified on** a byte-copy of `experiments\COLD_START_20_HEIGHT_1024\10_best_valid`
(`routes_l3d.json` sha256 `35d7ebed00339bee21fe0ca47075c9b34008120522a47933a099efacf0b90753`)
**Result** exit code **0**, `violation_count = 0`, `validation_pass = True` — reproduces the frozen
verdict of record exactly.
**Date** 2026-11-19

---

## 1. TL;DR — the command

There is **no** standalone `python -m ...validate_native3d --run-dir X` that is correct for the
20-height profile: the validator resolves its expected height table from
`four_side_1024.fanout1024.reheight21.model`, and only `coldstart20.bootstrap` re-points that module
to the 20-height `model20`. **The bootstrap must be imported in the same process before the validator
runs.** Any wrapper that does this (the official one is `coldstart20.run_g4 … validate`, which spawns
`python -m four_side_1024.fanout1024.xyzrouter.validate_xyz`) is fine.

### 1.1 Canonical command (produces the same artefact shape as the frozen `validation.json`)

```powershell
$env:PYTHONPATH="C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D"
& "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\.venv\Scripts\python.exe" -c @"
import sys
from four_side_1024.fanout1024.coldstart20 import bootstrap as B   # installs the 20H profile
B.assert_20_height_profile('runbook')
from four_side_1024.fanout1024.xyzrouter import validate_xyz as X  # G4 chain entry point
sys.exit(X.main([
    '--run-dir',      r'<RUN_DIR>',
    '--out-dir',      r'<OUT_DIR>',
    '--baseline-dir', r'<PROJECT>\experiments\COLD_START_20_HEIGHT_1024\07_g123\run_xyz_joint_1024_20h\baseline_authoritative',
    '--manual-policy', 'fully_optimizable',
]))
"@
```

*Use `<OUT_DIR> = <RUN_DIR>` to write the verdict next to the routes; use a separate directory to
leave the run dir untouched (both verified, §3).*

### 1.2 Equivalent minimal command (one layer less; same verdict, slightly smaller report)

```powershell
& $py -c @"
import sys
from four_side_1024.fanout1024.coldstart20 import bootstrap as B
B.assert_20_height_profile('runbook')
from four_side_1024.fanout1024.native3d import validate_native3d as V
sys.exit(V.main(['--run-dir', r'<RUN_DIR>', '--out-dir', r'<OUT_DIR>',
                 '--baseline-dir', r'<PROJECT>\experiments\COLD_START_20_HEIGHT_1024\07_g123\run_xyz_joint_1024_20h\baseline_authoritative',
                 '--manual-policy', 'fully_optimizable']))
"@
```

`validate_xyz` only wraps `validate_native3d.validate_run()`, normalises `manual_policy` /
`policy_report`, merge-writes `validation.json` and stamps
`"xyz_validator": "four_side_1024.fanout1024.xyzrouter.validate_xyz"` — which is exactly what the
frozen report contains. Use §1.2 when you want the pure `native3d_validation_v1` report.

---

## 2. What the validator is, and what it is not

```
validate_native3d  (report of record: schema native3d_validation_v1, 11 checks)
   ├─ model / coverage / structure / native_metadata / radius / glass / clearance / ports
   ├─ crossings  -> reheight21.validate21.check_crossings
   │                   -> fslw.validate_fslw.audit_route_pairs(..., policy='strict')   [strict D56]
   ├─ manual_frozen -> 368 manual-group route identities vs the baseline
   └─ synthetic   -> 7 in-memory consistency tests
```

**Do not use `python -m four_side_1024.fanout1024.coldstart20.run_validate` as *the* validator for
G4/G5 outputs.** That module runs `reheight21.validate21` — the *planar-assembly* contract validator.
It re-uses the very same strict-D56 pair audit (so its **crossing numbers are identical**), but its
structure/assignment contract assumes the pre-Native-3D 5-part shape
(`lead / S-transition / body / S-transition / lead`). G4/G5 routes contain mid-body layer changes and
re-assigned heights, so:

* the crossing verdict is right,
* the overall verdict is wrong (exit 1, 580 "violations" on the frozen solution that the official
  validator passes with 0).

This is stated by the project itself in `four_side_1024/fanout1024/coldstart20/run_native3d_phase1.py:183-188`:
*"`reheight21.validate21` is the planar-assembly validator: its contract assumes the pre-Native-3D
5-part structure … therefore cannot be applied to a layout whose bodies contain mid-path layer
changes — that is a contract mismatch, not a relaxation."* `run_validate` output is kept as
`validation/planar_contract_validate21.json` for the record only.

---

## 3. Observed runs (all on the same scratch copy)

Scratch copy: `experiments\G5_ANGLE45_NATIVE3D_20H_1024\01_algorithm\_probe\frozen_20h_copy\`
(5 input files copied from `10_best_valid`; `routes_l3d.json` sha256 re-verified as
`35d7ebed…b90753`). Deliverable copy: `…\01_algorithm\constraint_audit\probe\run_dir\`.

| run | command | exit | wall | report `runtime` | `validation.json` | violations | crossings / pairs | min 3D | files added to run dir |
|---|---|---:|---:|---:|---:|---:|---|---:|---|
| **A (canonical, `validate_xyz`)** | §1.1, out-dir = separate | **0** | **38.4 s** | 38.0 s | 56 899 B | **0** | 1283 / 1221 | 0.062212557 | **0** |
| B (`validate_native3d` only) | §1.2, out-dir = run dir | **0** | 40.6 s | 40.19 s | 56 127 B | **0** | 1283 / 1221 | 0.062212557 | 2 |
| C (default baseline, separate out-dir) | §1.2 without `--baseline-dir` | 0 | 40.8 s | 40.4 s | 62 203 B | 0 | 1283 / 1221 | 0.062212557 | 0 |
| D (`run_validate` = validate21) | `python -m …coldstart20.run_validate --run-dir … --out-dir …` | **1** | 36.9 s | 36.5 s | 112 024 B | **580** (structure 307, assignment 268, totals 5) | 1283 / 1221 | 0.062212557 | 4 |
| E (`validate_native3d`, default `--manual-policy frozen`) | §1.2 without `--manual-policy` | **1** | 34.9 s | 34.5 s | — | **368** (`manual_frozen`) | 1283 / 1221 | 0.062212557 | — |
| *frozen artefact of record* | — | 0 | — | 20.27 s | 56 993 B | 0 | 1283 / 1221 | 0.062212557 | — |

**A vs the frozen file:** schema `native3d_validation_v1`, `validator =
four_side_1024.fanout1024.native3d.validate_native3d`, `xyz_validator =
four_side_1024.fanout1024.xyzrouter.validate_xyz`, `manual_policy = fully_optimizable`,
`exit_code = 0`, `validation_pass/geometry_pass/contract_pass = True`, `violation_count = 0`,
`counts.same_plane_crossings = 1283`, `counts.same_plane_crossing_pairs = 1221`,
`counts.same_plane_crossing_violations = 0`, `counts.min_non_crossing_centerline_mm = 0.086853441`,
`counts.min_3d_clearance_mm = 0.062212557`, `counts.audited_heights = 20`,
`checks.crossings.totals = {crossings: 1283, crossing_pairs: 1221, violations: 0}`.
The only differences from the frozen file are the absolute paths and the timings (the frozen run took
20.27 s; a warm/cold machine varies 34–41 s here).

**Why run D fails (diagnostic detail, not a rule failure):** the 580 violations are
`structure / z_span_mismatch` (e.g. `route 2: 0.0 != 0.1` — the G4 records keep
`start_z_mm == end_z_mm == interface z` while the body flats sit at re-assigned heights) and
`assignment` contract mismatches; `checks.crossings.violations = 0` in run D as well. Use run D only
as the planar-contract record.

---

## 4. Files it writes

| file | when | bytes (run A) |
|---|---|---|
| `<OUT_DIR>\validation.json` | always | 56 899 |
| `<OUT_DIR>\validator_consistency_tests.json` | always (7 synthetic tests) | 3 671 |
| — | **nothing else** | — |

* With `--out-dir = <RUN_DIR>` (run B): exactly those **2** files are added to the run dir; the
  input files are not touched (verified by a recursive file-count/size listing before and after:
  5 → 7 files; `routes_l3d.json` sha256 unchanged).
* With `--out-dir` pointing elsewhere (runs A and C): the run dir is **completely untouched**
  (file count 7 → 7, all hashes unchanged).
* The validator does **not** write `crossing_stats.json` (that file in `10_best_valid` was produced by
  the G4 run's `xyzrouter/optimizer.py::crossing_stats()` → `native3d/crossing_cache.py`, i.e. by the
  search pipeline, not by the validator).
* `run_validate` (validate21, run D) additionally writes `<OUT_DIR>\crossing_stats.json` and
  `<RUN_DIR>\coldstart20_validation_summary.json` — another reason not to use it for acceptance.

---

## 5. Inputs, dependencies, environment assumptions

**Required in the run dir**

| file | required? | note |
|---|---|---|
| `routes_l3d.json` | **yes** | `FileNotFoundError` → exit 2 if missing |
| `assignment_1024.csv` | yes (falls back to `<baseline-dir>\assignment_1024.csv` with a log line) | used for the 368 manual routes and the assignment contract |
| `layer_planes.json` | recommended (falls back to `<baseline-dir>\layer_planes.json`, then to `reheight21.model`) | if missing *and* no baseline copy, the expected table comes from the (21H) model and `check_model` fails |

**Required side inputs (project-internal, no network)**

| input | required? | note |
|---|---|---|
| `--baseline-dir` = a frozen baseline with `routes_l3d.json` + `assignment_1024.csv` | **effectively yes** — `validate_native3d` raises `FileNotFoundError` if `<baseline-dir>\routes_l3d.json` is absent | default is the **21-height** `outputs\manual_c4_new_connectivity\NON_C4_CROSSING_OPT_1024\E5_joint_repair_final` (exists in this checkout; run C passed with it, but its "vs E5 baseline" numbers differ: 2606→1283 instead of 3061→1283). For G5 use the 20H baseline `experiments\COLD_START_20_HEIGHT_1024\07_g123\run_xyz_joint_1024_20h\baseline_authoritative` |
| `<baseline-dir>\crossing_stats.json` | optional | only for the "vs baseline" delta block |

**Process / environment**

* `PYTHONPATH` must contain the project root (the modules are imported as `four_side_1024.*`).
  Run from the project root for consistency; nothing in the validator depends on the CWD (all paths
  are resolved from `__file__` and the CLI arguments).
* **The 20H profile must be installed in-process** (`coldstart20.bootstrap`) — otherwise
  `reheight21.model` stays 21H and `check_model` reports `plane_count_mismatch`,
  `model_body_plane_missing`, `model_unknown_plane_id`, … → exit 1.
* Packages: `numpy` (imported at module level) and `scipy` (imported inside
  `validate21.measure_min_3d_clearance` → `scipy.spatial.cKDTree`). **No matplotlib, no fonts, no
  display, no network.**
* Wall clock ≈ 35–41 s for 1024 routes on this machine; ~0.5 s of that is the D56 pair audit
  (`checks.crossings.runtime_seconds`), the rest is the fresh-World `check_route` pass and the
  min-3D-clearance KD-tree scan. A run with **both** `--skip-min-clearance` and `--skip-synthetic`
  still took 34.5 s (vs 40.2 s full) — the world pass dominates, so the flags buy almost nothing and
  **must never be used for an acceptance verdict.**

---

## 6. Exit codes and how to read them

| exit | meaning |
|---:|---|
| 0 | `validation_pass = True` (geometry + contract + consistency) |
| 1 | violations (`violation_count > 0`) — read `validation.json` → `violation_counts_by_check` |
| 2 | input error (missing `routes_l3d.json`, missing baseline routes, unknown `--manual-policy`) |

Check-list for a G5 acceptance run:

```powershell
$v = Get-Content "$out\validation.json" -Raw | ConvertFrom-Json
$v.exit_code -eq 0
$v.violation_count -eq 0
$v.counts.same_plane_crossing_violations -eq 0
# G5 extra assertion: no crossing below 45 deg
($v.checks.crossings.planes | Measure-Object -Property crossings -Sum).Sum   # per-plane counts
# and inspect the per-event angles written by the search pipeline, not by the validator:
#   crossing_stats.json -> crossing_events[].angle_deg  (min must be >= 45)
```

---

## 7. Copy-paste PowerShell (parameterised, run from the project root)

```powershell
# ---------------------------------------------------------------- parameters
$PROJECT = "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D"
$PY      = Join-Path $PROJECT ".venv\Scripts\python.exe"
$RUN     = "<absolute path to the run dir with routes_l3d.json>"
$OUT     = $RUN                      # or e.g. "$RUN\validation"
$BASE    = Join-Path $PROJECT "experiments\COLD_START_20_HEIGHT_1024\07_g123\run_xyz_joint_1024_20h\baseline_authoritative"

$env:PYTHONPATH = $PROJECT
Push-Location $PROJECT

# ------------------------------------------------- optional: snapshot run dir
$before = Get-ChildItem $RUN -Recurse -File |
          ForEach-Object { "{0}`t{1}`t{2}" -f $_.FullName.Substring($RUN.Length+1), $_.Length,
                                                (Get-FileHash $_.FullName -Algorithm SHA256).Hash }
Set-Content "$RUN\..\listing_before.txt" $before

# ---------------------------------------------------------------- validate
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$code = @"
import sys
from four_side_1024.fanout1024.coldstart20 import bootstrap as B
B.assert_20_height_profile('g5-runbook')
from four_side_1024.fanout1024.xyzrouter import validate_xyz as X
sys.exit(X.main(['--run-dir', r'$RUN', '--out-dir', r'$OUT',
                 '--baseline-dir', r'$BASE',
                 '--manual-policy', 'fully_optimizable']))
"@
$code | & $PY -
$exit = $LASTEXITCODE
$sw.Stop()
Pop-Location

# ---------------------------------------------------------------- report
"exit=$exit wall=$([math]::Round($sw.Elapsed.TotalSeconds,1))s"
$v = Get-Content (Join-Path $OUT "validation.json") -Raw | ConvertFrom-Json
$v | Select-Object schema, validator, xyz_validator, exit_code, validation_pass,
                     geometry_pass, contract_pass, violation_count, runtime_seconds
$v.counts | Select-Object routed, failed, same_plane_crossings, same_plane_crossing_pairs,
                            same_plane_crossing_violations, min_non_crossing_centerline_mm,
                            min_3d_clearance_mm, audited_heights
$v.violation_counts_by_check

# ---------------------------------------------------------------- evidence
$after = Get-ChildItem $RUN -Recurse -File |
         ForEach-Object { "{0}`t{1}`t{2}" -f $_.FullName.Substring($RUN.Length+1), $_.Length,
                                               (Get-FileHash $_.FullName -Algorithm SHA256).Hash }
Compare-Object $before $after      # empty  => the validator did not modify the run dir
```

---

## 8. Verified evidence in this deliverable

| path | content |
|---|---|
| `probe\run_dir\` | scratch copy of the frozen 5 input files + the **canonical** `validation.json` (56 899 B) and `validator_consistency_tests.json` (3 671 B) |
| `probe\run_dir_listing_before.txt` / `run_dir_listing_after_native3d.txt` | the before/after listings proving only 2 files are added |
| `probe\validate_xyz_run.log` | full stdout of run A (38.4 s, exit 0) |
| `probe\validate_native3d_run.log` | full stdout of run B (40.6 s, exit 0) |
| `probe\validate_native3d_only\` | run B's two output files (the pure `native3d_validation_v1` report) |
| `probe\validate_native3d_default_baseline.log` | run C (default 21H E5 baseline, separate out-dir, run dir untouched) |
| `probe\validate21_attempt_negative\` | run D (`coldstart20.run_validate` / validate21): `validation.json`, `crossing_stats.json`, `validator_consistency_tests.json`, `coldstart20_validation_summary.json`, log — 580 violations, exit 1 |
| `probe\angle_window_probe.py` / `.json` | the 5/10/30/45/90 deg strict-D56 admissibility + window probe used by `CROSSING_RULE_AUDIT.md` |

All probe artefacts were produced without modifying any existing project file; the frozen
`10_best_valid` directory was only read (its `routes_l3d.json` still hashes to
`35d7ebed00339bee21fe0ca47075c9b34008120522a47933a099efacf0b90753`).
