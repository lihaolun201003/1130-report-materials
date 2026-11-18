# Reproduction: 20-height cold-start rebuild of the 1024-route 3D router

**Experiment:** `COLD_START_20_HEIGHT_1024`
**Project root:** `C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D`
**Interpreter:** `.venv\Scripts\python.exe` (Python 3.10.11, Windows/PowerShell)
**Deliverable root:** `experiments\COLD_START_20_HEIGHT_1024\`
**Measured total:** ≈2.9 h for the A-class stages 03–08 (single-process CPU),
+≈22 min stage 09 (partly overlapped with 08), +≈13 min for progressive-chain
link 2; ≈3.5 h wall including figures/reports on one workstation, no GPU.

This is the **executed** order, not an idealised plan: commands, budgets,
output directories and resume points are taken from the stage logs and driver
CLIs under `four_side_1024\fanout1024\coldstart20\` and from the artifacts of
the delivered run. Every command below is copy-pasteable from the project root.

---

## 0. Prerequisites and execution model

1. Use the bundled venv from the project root (all commands assume `pwd` is the
   project root). PowerShell is the reference shell.
2. **Import-order contract (mandatory).** Every 20H driver imports
   `four_side_1024.fanout1024.coldstart20.bootstrap` before any pipeline
   module; the bootstrap registers `model20` under the
   `four_side_1024.fanout1024.reheight21.model` key. Never start the frozen
   modules with `python -m four_side_1024.fanout1024.native3d.*`,
   `...xyzrouter.*` or `...xyzrouter.g4.*` for the 20H experiment -- `-m` would
   bind the 21H model first. Always go through the
   `python -m four_side_1024.fanout1024.coldstart20.<driver>` entry points.
3. No source file has to be patched to reproduce the run: the audited patches
   are already applied in the working tree. Sanity-check them with the
   read-only verifiers in §11.
4. The 21H trees under `outputs\manual_c4_new_connectivity\` and
   `experiments\xyz_joint_*` are **read-only inputs**; the 20H chain writes only
   under `experiments\COLD_START_20_HEIGHT_1024\`.
5. Set once per shell:

```powershell
cd "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D"
$PY = ".venv\Scripts\python.exe"
$EXP = "experiments\COLD_START_20_HEIGHT_1024"
```

## 1. Environment variables that matter

| variable | default | effect / when to set it |
|---|---|---|
| `G4_ENABLE_MULTI_ARC` | `1` | **the only algorithmic switch.** Read by `layer2d.MULTI_ARC_POLICY` at import; `0` bans the planar short-S multi-arc candidate family. Only the stage-09 OFF arm sets it to `0`; every reported main-experiment solution uses `1`. Reset to `1` (or remove it) afterwards. |
| `COLDSTART20_PROFILE` | set by the bootstrap | `20_height_raised`; the frozen path modules use it to detect the 20H process. Do not set it manually before a driver. |
| `COLDSTART20_*` (paths) | set by `coldstart20.bootstrap` | all writable run directories (`INIT_RUN`, `NONC4_ROOT`, `E5_DIR`, `NATIVE3D_ABC_RUN`, `NATIVE3D_DEF_RUN`, `XYZ_RUN`, `G4_ROOT`, `MULTIARC_ROOT`, ...). The drivers publish them; the frozen path modules fall back to the 21H paths when they are absent. |
| `COLDSTART20_START_SHA` / `COLDSTART20_START_CROSSINGS` | unset | optional override of the G4 common-start fingerprint (bit-reproducible reruns). Not needed here: the fingerprint is computed from the accepted layout (`a6aa6997...` / 1395). |
| `COLDSTART20_PHASE1_CROSSINGS` | unset | optional override of the Phase-2 inherited baseline (3275 for this run); normally read from the Phase-1 `crossing_stats.json`. |

Do not run two stages that write the same directory at the same time. The
driver-level preflight that freezes the G123 authority snapshot is idempotent
(same source SHA => reuse), so the G1 and G3_cold drivers may safely be started
concurrently (that is how the delivered run was produced).

---

## 2. Stage 01 -- height configuration metadata (optional, ~5 s)

Not needed for the optimisation chain, but it produces the stage-01 deliverable
(height table, migration table, model self-check, `profile.json`). It reads the
completed stage-03 run for the observed per-plane counts, so run it **after**
stage 03:

```powershell
$PY "$EXP\01_height_config\build_height_config.py"
```

Outputs (in `$EXP\01_height_config\`): `height_table_20.json`,
`height_table_20.md`, `height_table_21_vs_20.md`, `profile.json`,
`model20_selfcheck.txt`, `SHA256.json`.

---

## 3. Stage 03 -- fanout-first cold start (A–F), validation, figures

Output directory: `$EXP\03_fanout_and_xy\run_initial_20h\` (≈270 s).

```powershell
# A assignment -> B fanout/R15 transitions -> C per-height strict-D56 multi-arc
#   -> D 3D assembly/world check -> E joint repair -> F final summary
$PY -m four_side_1024.fanout1024.coldstart20.run_initial --stages ABCDEF --max-iters 3

# independent frozen validator (reheight21.validate21 under the 20H profile)
$PY -m four_side_1024.fanout1024.coldstart20.run_validate --run-dir "$EXP\03_fanout_and_xy\run_initial_20h"

# 20 plain + 20 crossing-annotated per-height XY figures (frozen plots21 engine)
$PY -m four_side_1024.fanout1024.coldstart20.plot_layers20 `
    --run-dir "$EXP\03_fanout_and_xy\run_initial_20h" `
    --out-dir "$EXP\03_fanout_and_xy\figures" --dpi 165

# crossing summary report for the initial layout (plain script, not a driver;
# run after the figures)
$PY "$EXP\03_fanout_and_xy\build_crossing_summary.py"
```

Outputs: `run_initial_20h\` (`assignment_1024.csv`, `assignment_audit.json`,
`assignment_diff_vs_baseline.*`, `layer_planes.json`,
`physical_layer_stack.json`, `process_rules.json`, `fanout_selected.json`,
`routes_l3d.json`, `crossing_stats.json`, `final_stats.json`, `validation.json`,
`validator_consistency_tests.json`, `experiment_A..F/`); plus
`03_fanout_and_xy\crossing_summary_20h.{json,md}` and
`03_fanout_and_xy\figures\{per_height_plain,per_height_crossings}\`.
Measured: 269.9 s; validation 37.95 s; 1024/1024 routed, 0 failed, **12338
crossings / 10133 pairs**, validator PASS 0 violations.

Resume/repair: `--stages CDE --max-iters 4` reuses the existing assignment;
`--skip-assign` skips stage A.

---

## 4. Stage 04 -- from-scratch C4-free annealing + joint repair (the 20H "E5")

Output root: `$EXP\04_initial_3d_and_e5_repair\nonc4_programme\` (≈590 s).
The delivered run used the stepwise sequence below (no `e0`, no `summary`):

```powershell
$PY -m four_side_1024.fanout1024.coldstart20.run_nonc4 screen --seed 11 --time-budget 60
$PY -m four_side_1024.fanout1024.coldstart20.run_nonc4 e1
$PY -m four_side_1024.fanout1024.coldstart20.run_nonc4 e3 --seed 51
$PY -m four_side_1024.fanout1024.coldstart20.run_nonc4 e3 --seed 23
$PY -m four_side_1024.fanout1024.coldstart20.run_nonc4 e3 --seed 37
$PY -m four_side_1024.fanout1024.coldstart20.run_nonc4 e2 --seed 11
$PY -m four_side_1024.fanout1024.coldstart20.run_nonc4 e3 --seed 11
$PY -m four_side_1024.fanout1024.coldstart20.run_nonc4 select
```

Equivalent single command (also runs the E0 reproduction and the stage summary,
and iterates the seeds in `11,23,37,51` order -- the seed-named output dirs are
identical):

```powershell
$PY -m four_side_1024.fanout1024.coldstart20.run_nonc4 all --seeds 11,23,37,51 --time-budget 60
```

Outputs: `E1_family_pure\`, `E2_conflict_sharing_seed11\`,
`E3_family_pure_sa_seed{11,23,37,51}\`, `selection.json`, and the accepted
checkpoint `E5_joint_repair_final\` (`ACCEPTED.json`,
`routes_l3d.json` SHA256 `9da7924c...`, 1024/1024, **3275 crossings / 2774
pairs**, validator PASS). The accepted source experiment is E3 seed 11.
(`select` re-validates every candidate and copies the first fully legal one.)

Resume: each subcommand is independent and rerunnable; `select` only reads
existing experiment dirs.

---

## 5. Stage 05 -- Native 3D Phase 1 (A/B/C)

Output: `$EXP\05_native3d_abc\run_native3d_phase1\` (≈805 s total). A and B were
launched as two processes; C runs after B. A and B are **independent branches**
from the E5 layout (not a chain); C produces the accepted Phase-1 layout.

```powershell
$PY -m four_side_1024.fanout1024.coldstart20.run_native3d_phase1 a --top-routes 12
$PY -m four_side_1024.fanout1024.coldstart20.run_native3d_phase1 b --sample 30 --batch 80
$PY -m four_side_1024.fanout1024.coldstart20.run_native3d_phase1 c
$PY -m four_side_1024.fanout1024.coldstart20.run_native3d_phase1 materialize
# record-only planar-assembly audit under validate21 (expected exit 1: its
# 5-part route contract cannot judge mid-path layer changes -- NOT the gate)
$PY -m four_side_1024.fanout1024.coldstart20.run_native3d_phase1 validate-planar
# official Native-3D validator (this is the acceptance gate)
$PY -m four_side_1024.fanout1024.coldstart20.run_native3d_phase1 validate
$PY -m four_side_1024.fanout1024.coldstart20.run_native3d_phase1 plots
$PY -m four_side_1024.fanout1024.coldstart20.run_native3d_phase1 summary
```

`a` first runs the A0 geometry gate (11/11 expected); a failed A0 aborts before
the scan. Measured: A re-run 16 s (A1: 0/12 routes feasible), B 217 s
(3275 -> 3240), C 450 s (3275 -> **3103 / 2733 pairs**), materialize 23:07:48,
native3D validation PASS 0 violations. If you run `all`, the driver executes
a -> b -> c -> materialize -> validate -> plots -> summary sequentially in one
process (same artifacts, ≈13 min).

Outputs: `ACCEPTED_PHASE1.json`, `STAGE05_GATE.json`, `routes_l3d.json`,
`crossing_stats.json`, `transition_stats.json`, `summary.json`,
`validation\validation.json` (`native3d.validate_native3d`, PASS),
`validation\planar_contract_validate21_validation.json` (recorded diagnostic,
FAIL 364 -- expected), `experiment_A|B|C\`, `plots\`.

---

## 6. Stage 06 -- Native 3D Phase 2 (D/E/F)

Output: `$EXP\06_native3d_def\run_native3d_phase2\` (2670 s = 44.5 min). One
command runs the whole audited chain in-process:

```powershell
$PY -m four_side_1024.fanout1024.coldstart20.run_native3d_phase2 all
```

Chain and measured sub-stage times (from `logs\phase2_chain_status.json`):

| sub-stage | what | seconds | crossing effect |
|---|---|---:|---|
| `intervals` | crossing-interval candidate pool on the E5 layout | 87.3 | – |
| `blockers` | D0/E0 blocker analysis | 286.1 | – |
| `d` | screened multi-route joint make-way | 301.1 | 3103 -> 3103 (0 accepted) |
| `e` | arc-region local rebuild | 79.5 | 3103 -> 3098 |
| `f` | plain/arc_span/joint sweeps, 2 sweeps | 644.0 | 3098 -> 3087 |
| `fplus_1` / `fplus_2` | multi-excursion batch sweeps | 255.7 / 253.3 | contributes part of 3087 -> 3061 |
| `nearmiss_1` / `nearmiss_2` | near-miss refinement passes | 413.1 / 316.6 | completes the reduction to 3061 |
| `finalize` | independent validation + plots + reports + MANIFEST/archive | 33.3 | 3061 |

Final: `best_valid\` — 1024/1024, **3061 crossings / 2705 pairs**, 68 native
routes / 156 mid-path transitions, min true-3D clearance 0.068629474 mm;
`validation\final\validation.json` `native3d.validate_native3d` PASS 0
violations.

Resume from a failure or re-run one stage (stages build on the prior
`best_valid` and are rerunnable): `run_native3d_phase2 <stage>` with `<stage>`
one of `intervals, blockers, d, e, f, fplus_1, fplus_2, nearmiss_1,
nearmiss_2, finalize`; optional `arc_analysis` and `validate` are **not** part
of `all`. `--dry-run`/`plan` prints the resolved plan without executing.

---

## 7. Stage 07 -- G1 -> G2a -> G2b -> G3 (XYZ joint)

Output root: `$EXP\07_g123\run_xyz_joint_1024_20h\` (≈63 min). The G1 and G3_cold
invocations were started concurrently (the preflight authority snapshot is
idempotent, so this is safe):

```powershell
# terminal A: G1, manual-U frozen (2 rounds x 1200 s wall)
$PY -m four_side_1024.fanout1024.coldstart20.run_g123 g1

# terminal B (in parallel): independent cold control, 1 round x 1200 s
$PY -m four_side_1024.fanout1024.coldstart20.run_g123 g3cold

# after both: G2a (2x300 s) -> G2b (1x240 s) -> G3 (1x500 s) in-process
$PY -m four_side_1024.fanout1024.coldstart20.run_g123 warmstart

# frozen router functional validation P0/P1/P2 under the 20H model
$PY -m four_side_1024.fanout1024.coldstart20.run_g123 validate

# reports + fair/warm comparison + best_valid + archive
$PY -m four_side_1024.fanout1024.coldstart20.run_g123 reports
```

Measured: G1 1448.71 s (3061 -> **1485**), G3_cold 929.09 s (3061 -> 1646),
G2a 416.68 s (-> 1440), G2b 404.82 s (-> 1409), G3 516.19 s (-> **1395 / 1325
pairs**), P0/P1/P2 ≈4.8 min, reports 5 s. `best_valid\` routes SHA256
`a6aa699728c2c431b0e2ccae4f82c2772dc3943eee43a8832ccfc22e1415eabf`; validator
`native3d.validate_native3d`, `manual_policy=fully_optimizable`, PASS 0
violations. The preflight also writes `baseline_authoritative\` (the accepted
Phase-2 3061 start) with `AUTHORITY.json`/`SHA256.json` and its own PASS
validation (`manual_policy=frozen`).

Resume: every subcommand is rerunnable from its own stage dir; checkpoints are
stage-scoped (`<stage out>\checkpoints\checkpoint_%04d\`, every 25 accepts).
`run_g123 preflight` alone refreshes the authority snapshot; `run_g123 all`
runs the whole chain in order.

---

## 8. Stage 08 -- G4 global ALNS arms (+ progressive chain)

Output root: `$EXP\08_g4\` (A-class arms ≈37 min). Start with the common-start
freeze (writes `START.json`, fingerprint `a6aa6997...` / 1395):

```powershell
$PY -m four_side_1024.fanout1024.coldstart20.run_g4 start
```

Then run the six arms (the delivered run launched C0/G4a/G4b concurrently, then
G4c_frozen/G4c_free/G4d concurrently; each arm re-validates its own best in a
fresh 20H process):

```powershell
# first batch (all from the common 1395 start)
$PY -m four_side_1024.fanout1024.coldstart20.run_g4 c0 --seconds 600
$PY -m four_side_1024.fanout1024.coldstart20.run_g4 a  --seconds 900
$PY -m four_side_1024.fanout1024.coldstart20.run_g4 b  --seconds 900

# second batch: equal counted budget (d56 24000 / checks guard 9000), 1800 s wall safety net
$PY -m four_side_1024.fanout1024.coldstart20.run_g4 c-frozen --seconds 1800 --counted
$PY -m four_side_1024.fanout1024.coldstart20.run_g4 c-free   --seconds 1800 --counted
$PY -m four_side_1024.fanout1024.coldstart20.run_g4 d        --seconds 1800 --counted
```

| arm | start | best legal | crossings | search wall | counted effort |
|---|---:|---:|---:|---:|---|
| C0 | 1395 | 1383 | −12 | 604.6 s | not counted |
| G4a | 1395 | 1393 | −2 | 828.6 s | not counted |
| G4b | 1395 | 1371 | −24 | 842.3 s | not counted |
| G4c_frozen | 1395 | 1338 | −57 | 1211.6 s | 24006 d56 / 3347 checks |
| **G4c_free** | 1395 | **1322** | **−73** | 1237.8 s | 24175 d56 / 3327 checks |
| G4d | 1395 | 1337 | −58 | 1159.7 s | 24266 d56 / 3688 checks |

Every arm's `best_valid\` has PASS `validation\validation.json`. The A-class
matrix compares arms at equal **counted** effort for G4c/G4d and equal wall for
C0/G4a/G4b (the START.json `ARM_BUDGETS` defaults are overridden by the
`--seconds` values above; see `00_audit/pipeline_map.md` §10.4).

Progressive chain (delivered run: link 2 only; links 3/4 pending):

```powershell
$PY -m four_side_1024.fanout1024.coldstart20.run_g4 chain --run-chain
# link 2: G4c_free 700 s from 01_link_best_G4ab (1371) -> 1309, validated
# link 3 (02b) is a 0-s SPEC-B inheritance and stays pending in the frozen
# fair_runner, so link 4 is blocked. The delivered run instead launched a manual
# G4d continuation from link 2 (not part of the A-class matrix):
$PY -m four_side_1024.fanout1024.coldstart20.run_g4 d --seconds 1200 --counted `
    --start-dir "$EXP\08_g4\08_progressive_chain\02_link_G4c" `
    --out-dir    "$EXP\08_g4\08_progressive_chain\03_link_G4d"
```

Outputs per arm: `best_valid\`, `validation\`, `budget_ledger.json`,
`config.json`, `summary.json`, `summary_g4.json`, `strategy_stats*.json`,
`failed_attempts.json`, `geometry_changes.json`, `manual_u_changes.json`,
`optimization_history.csv`, `run.log`; plus `START.json`, `00_start_g3\`,
`08_progressive_chain\` (`chain_summary.json`, `progressive_chain.md`,
`run_g4_chain.log`). `07_best_valid\` is empty in the delivered state (see
§12 caveats).

Resume: each arm is `--resume`-capable and keeps its own checkpoints
(`<arm>\checkpoints\step_%05d\`); rerunning an arm from scratch is also safe
(it rewrites only its own directory).

---

## 9. Stage 09 -- multi-arc ON/OFF controlled ablation

Output root: `$EXP\09_multi_arc_ablation\` (≈22 min, can overlap stage 08). The
pre-registered strict common-start design first, then the executed substitute:

```powershell
# (1) verify the ON/common start (accepted G3 optimum, 1395) + record its validation
$PY -m four_side_1024.fanout1024.coldstart20.run_multiarc start

# (2) deterministic Stage-0 ON -> OFF conversion of the G3 start.
#     Expected outcome for 20 heights: exit code 4 (OFF start infeasible:
#     212/213 multi-arc routes converted, residual route 456, 1395 -> 4559,
#     effect A = +3164). It writes OFF_FEASIBILITY.json +
#     ABORTED_OFF_INFEASIBLE.json and the protocol forbids running a diluted
#     OFF arm from this start.
$PY -m four_side_1024.fanout1024.coldstart20.run_multiarc convert

# (3) cold-start controlled OFF arm: identical cold assignment / seeds /
#     budgets / validator, only the multi-arc policy differs.
$env:G4_ENABLE_MULTI_ARC = '0'
$PY -m four_side_1024.fanout1024.coldstart20.run_initial `
    --run-dir "$EXP\09_multi_arc_ablation\cold_start_off"
$PY -m four_side_1024.fanout1024.coldstart20.run_validate `
    --run-dir "$EXP\09_multi_arc_ablation\cold_start_off"
Remove-Item Env:G4_ENABLE_MULTI_ARC   # or set it back to '1'
```

The ON arm is the unchanged stage-03 run (`run_initial_20h`, same
`routes_l3d.json` SHA256 `2eb3a14c...`); do not rerun it for the ablation.

| arm | `enable_multi_arc` | crossings | pairs | mean/route | min 3D (mm) | arc primitives / routes with >=2 arcs | validator |
|---|---|---:|---:|---:|---:|---:|---|
| ON (stage-03) | 1 | **12338** | 10133 | 38.56 | 0.086499 | 1700 / 646 | PASS |
| OFF (`cold_start_off`) | 0 | **14233** | 10637 | 44.48 | 0.100011 | 1960 / 636 | PASS |

Measured: start 01:03:41; conversion 974 s (incl. native3D validation 31 s and
a non-blocking validate21 diagnostic 32 s); OFF arm 262.3 s (1024/1024,
14233 crossings); validation 01:25:10. `run_multiarc analyse` was **not** run in
the delivered state (`audit\`, `tables\`, `runs\` are empty); the analysis text
is `09_multi_arc_ablation\ABLATION_REPORT.md`.

---

## 10. Stage 10/12 -- final figures, selection and reports

Figures were rendered as **test renderings** in the delivered run (on the E5
and stage-05 layouts), not on the final G4c-free layout:

```powershell
$PY -m four_side_1024.fanout1024.coldstart20.plot_final `
    --layout "$EXP\04_initial_3d_and_e5_repair\nonc4_programme\E5_joint_repair_final" `
    --out-dir "$EXP\11_figures\test_on_e5" `
    --label "E5 joint-repaired 20H (3275 crossings)" --dpi 150 --yscale log

$PY -m four_side_1024.fanout1024.coldstart20.plot_final `
    --layout "$EXP\05_native3d_abc\run_native3d_phase1" `
    --out-dir "$EXP\11_figures\test_on_stage05" `
    --label "Native-3D Phase 1 20H (3103 crossings)" --dpi 150 --yscale log

# machine-collected final metrics (reads artifacts only, no geometry)
$PY -m four_side_1024.fanout1024.coldstart20.collect_final
$PY -m four_side_1024.fanout1024.coldstart20.build_final_report

# best-legal scan (WRITE: only if you want the 10_best_valid freeze; see §12)
$PY -m four_side_1024.fanout1024.coldstart20.select_final            # scan only
# $PY -m four_side_1024.fanout1024.coldstart20.select_final --apply  # NOT SAFE yet, see §12
```

To render the **final** figure set from the measured best 1322 layout once the
freeze issue of §12 is resolved:

```powershell
$PY -m four_side_1024.fanout1024.coldstart20.plot_final `
    --layout "$EXP\08_g4\05_arm_G4c_free\best_valid" `
    --out-dir "$EXP\11_figures\final" `
    --label "G4c-free 20H final (1322 crossings)" --dpi 150 --yscale log
```

Outputs: `11_figures\test_on_{e5,stage05}\{01..07_*.png,figure_manifest.json,README.md,render_timings.json}`;
`12_reports\final_metrics.{json,md}`, `12_reports\stage_curve_20h.{json,md}`;
`10_best_valid\selection_scan.json` (and `BEST_VALID.json`/`SHA256.json` only
when `--apply` freezes a winner).

---

## 11. Verification / regression commands (read-only, no pipeline stage)

```powershell
# 21H assignment regression: 0 row mismatches vs the archived assignment; 34/34 invariants
$code = @"
import csv
from four_side_1024.fanout1024.reheight21 import assign21
rows = assign21.build_assignment(force=True)
base = list(csv.DictReader(open(r'outputs\manual_c4_new_connectivity\FANOUT_FIRST_21_HEIGHT_REBALANCED_1024\assignment_1024.csv', newline='', encoding='utf-8-sig')))
bad = sum(1 for r,b in zip(rows,base) if any(str(r.get(k)).strip()!=str(b.get(k)).strip() for k in b))
a = assign21.build_audit(rows, assign21._state()); inv=a['invariants']
print('row_mismatches', bad, 'invariants', sum(1 for x in inv if x['passed']), '/', len(inv))
"@
$code | $PY -

# 21H path/fingerprint resolution: 711cf910... / 1322 / frozen dirs
$PY -c "from four_side_1024.fanout1024.xyzrouter.g4 import paths as GP; print(GP.START_ROUTES_SHA256, GP.START_CROSSINGS, GP.START_DIR)"

# 21H/20H patch verifiers (read-only)
$PY "$EXP\00_audit\patch_native3d_def.py" --verify   # 21h PASS 13 checks / 20h PASS 24 checks
$PY "$EXP\00_audit\patch_g4.py" --check              # already applied 19 / all postconditions present

# 20H profile sanity: 20 planes, no plane 19, interfaces +0.025/+0.525
$PY -c "from four_side_1024.fanout1024.coldstart20 import bootstrap as B; print(len(B.M20.PLANE_IDS), 19 in B.M20.PLANE_IDS, B.M20.Z1_INTERFACE_MM, B.M20.Z2_INTERFACE_MM)"

# inspect a stage's validator identity/result (example: G4c-free final)
$PY -c "import json;d=json.load(open(r'$EXP\08_g4\05_arm_G4c_free\validation\validation.json',encoding='utf-8-sig'));print(d['validator'],d['validation_pass'],d['violation_count'],d['counts']['same_plane_crossings'])"
```

Expected: `row_mismatches 0 invariants 34 / 34`;
`711cf910...4077 1322 .../XYZ_JOINT_G123_1024/best_valid`;
`PASS -- evidence: .../patch_native3d_def_verify.json`;
`already applied 19`; `20 False 0.025 0.525`;
`four_side_1024.fanout1024.native3d.validate_native3d True 0 1322`.

---

## 12. Checkpoints, resumability and known caveats

**Checkpoint / resume points**

| stage | checkpoint | resume command |
|---|---|---|
| 03 | `run_initial_20h\checkpoints\stage_B_fanout.json`, `stage_C_2d.json`, `experiment_E_best.json`; `routes_l3d.json` written per iteration | `run_initial --stages CDE --max-iters N` |
| 04 | one self-contained dir per experiment; `E5_joint_repair_final\` + `SHA256_INDEX.json` | rerun any `run_nonc4 <step>`; `select` re-validates |
| 05 | `experiment_C\checkpoints\c*_routes_l3d.json`; `ACCEPTED_PHASE1.json` after `materialize` | `run_native3d_phase1 c` then `materialize`/`validate` |
| 06 | `checkpoints\` + `best_valid\` rewritten after every accepted transaction; stage log `phase2_chain_status.json` | `run_native3d_phase2 <stage>` |
| 07 | `checkpoints\checkpoint_%04d\` every 25 accepts, stage-scoped; `best_valid\` + `FINAL.json` after `reports` | rerun any `run_g123 <stage>`; preflight is idempotent |
| 08 | per-arm `checkpoints\step_%05d\`, crash-safe `best_valid\`, `budget_ledger.json` | rerun the arm (or add `--resume` where supported) |
| 09 | `common_start_off\` (conversion), `cold_start_off\` (OFF arm); `START.json`/`OFF_FEASIBILITY.json` gate | rerun `run_multiarc convert` / `run_initial --run-dir ...\cold_start_off` |
| chain | `08_progressive_chain\00_link_G3_start\`, `01_link_best_G4ab\`, `02_link_G4c\best_valid\`; `chain_summary.json` | `run_g4 chain --run-chain` (skips non-pending links) |

**Known caveats (must be read together with `00_audit/pipeline_map.md` §10)**

1. `10_best_valid\` is **not** frozen to the measured best layout in the
   delivered state. Its root has only `selection_scan.json` (01:41:07) plus the
   stage-03 checkpoint subdir `00_initial_fanout_first_20h\`; there is no
   `BEST_VALID.json`. `select_final.py` currently mis-resolves the G4-arm
   `best_valid` dirs (it needs `routes_l3d.json` and `crossing_stats.json` in the
   same directory and reads `routed/failed` only from `crossing_stats.json`), so
   its winner is `04_E5` (3275), not the 1322 G4c-free layout. The measured best
   layout is `08_g4\05_arm_G4c_free\best_valid\`; its independent validation
   report is `08_g4\05_arm_G4c_free\validation\validation.json` (PASS). Do
   **not** run `select_final --apply` until that resolution is fixed, or it will
   freeze 3275.
2. The progressive chain's links 3/4 are pending: `run_g4 chain --run-chain`
   stops with `link 4 blocked: previous link 3 status=pending` because link 3 is
   a 0-s SPEC-B inheritance step that the frozen `fair_runner` does not
   materialise. Link 2 did run and reached a validated **1309** crossings (better
   than the A-class 1322) after the main report was written.
3. The delivered figure set is a test rendering (`11_figures\test_on_*`, figure
   06 shows Native-2 = 3087, the value at render time). `11_figures\final\` does
   not exist; render it from the 1322 layout (§10).
4. `12_reports\stage05_native3d_phase1_summary.json` is correct in the final
   state (regenerated 23:39:45): `native3d.validate_native3d`, PASS, 0
   violations, 3103 crossings. The figure README
   (`11_figures\test_on_e5\README.md`) still contains a stale caveat that this
   file reports `validate21`'s 364-violation audit; that caveat predates the
   regeneration and is itself stale. The authoritative stage-05 result is
   `05_native3d_abc\run_native3d_phase1\validation\validation.json` /
   `STAGE05_GATE.json` (`native3d.validate_native3d`, PASS, 0 violations).
5. `12_reports\stage_curve_20h.*` was generated at 23:59:39, before stages 07/08
   finished; its S07/S08 rows say "not run yet". Use
   `12_reports\final_metrics.{json,md}`.
6. The G4 arms' START.json declares the frozen `ARM_BUDGETS`, but the executed
   run overrode the wall budgets (`--seconds 600/900/1800`); compare arms on the
   counted axis for G4c/G4d, and see the per-arm ledger for the real effort.
7. `12_reports\validator_report.md` (referenced by `EXPERIMENT_REPORT.md`) is
   not produced by any script; the per-stage `validation.json` files are the
   evidence of record.
