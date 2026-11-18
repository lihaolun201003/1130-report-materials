# Adaptation log — 20-height rebuild, file-by-file and chronological

Deliverable of the 20-height rebuild (1024-route 3D optical-waveguide router) in
`C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D`.

This is the chronological record of **every source change made for the 20-height
(20H) rebuild**, with the reason for each change and the evidence that the frozen
21-height (21H) behaviour is preserved. It complements `pipeline_map.md` (what runs
and where) and the six audit reports in this directory (why the frozen chain behaves
as it does).

Method / constraints:

* the project is **not a git repository** (`git status` reports `fatal: not a git
  repository`), so the change set was reconstructed from: file mtimes, the four
  audited patch scripts in this directory, the pre-change archive
  `_source_backup/four_side_1024_src_20261117_223317.zip`, the audit reports' frozen
  hash/size tables (`reheight21.md` section 0), and read-only source inspection;
* no source file was modified while writing this log; no pipeline stage was run to
  produce it (the 20H run itself was produced by the concurrent rebuild workstream);
* all line numbers are to the **current** working tree; "frozen 21H" line numbers
  are quoted from the audit reports where they differ.

Evidence tags: **[V]** = verified in this pass (probe/hash/read), **[A]** = audit
report evidence, **[R]** = wall-clock from an archived log.

---

## 1. Chronological timeline (2026-11-17, local time)

| time | file / event | what happened | legacy-safety note |
|---|---|---|---|
| 22:28:20 | `experiments/COLD_START_20_HEIGHT_1024/01..12_*` | deliverable directory scaffold created (empty stage dirs) | no code change |
| 22:31-22:32 | `four_side_1024/fanout1024/coldstart20/model20.py`, `bootstrap.py` created (first versions) | new 20H model/profile package | new files only |
| 22:32:07 | `four_side_1024/l3d/layers.py` (13,457 -> 15,773 B) | per-stack `interface_rows`; non-contiguous routing ids allowed; docstring documents 20H use | legacy defaults unchanged (3.1) |
| 22:32:07 | `coldstart20/__init__.py` | package docstring/API contract | new file |
| 22:33:17 | `_source_backup/four_side_1024_src_20261117_223317.zip` | pre-patch snapshot of the whole source tree (provenance/rollback) | read-only artifact |
| 22:33:20 | `reheight21/model.py` (31,248 -> 37,190 B) | `patch_profile_generic.py` applied: `PROFILE`/`MODEL_NAME`/`SCHEMA_*`/`CONTRACT_*`/`SPEC_*`/`Z2_OTHER_PLAN` hook/`allocate_z2_other` seam; 21H tables become the default profile values | 21H defaults equivalent (4.2) |
| 22:33:21 | `reheight21/run21.py` (59,279 -> 59,278 B) | stage-A expected counts from `M.CONTRACT_*`, height-count log derived | numerically identical on the 21H profile (4.2) |
| 22:33:55 | `coldstart20/run_initial.py` | 20H stage-03 driver (assignment + `run21.run_stages('ABCDEF')`, bootstrap-first) | new file; writes only the 20H tree |
| 22:38:00 | `reheight21/assign21.py` (68,627 -> 73,001 B) | three audited patches applied: `patch_profile_generic.py` (contract tables, Z2 allocation hook, invariant renames), `patch_assign21_reporting.py` (Z2 whole-orbit summary, audit/diff/experiment-A payloads), `patch_assign21_literals.py` (remaining "21"/"19"/z literals in logs/notes) | 21H assignment unchanged — verified 0 row mismatches, 34/34 invariants (5.1) |
| 22:38:01 | **stage-03 run starts** (`run_initial_20h/run.log` line 1 = `assign21: === COLD_START_20_HEIGHT_1024 ...`) | live 20H baseline generation | 20H tree only |
| 22:40:42 | `coldstart20/profile_env.py`, `coldstart20/paths20.py` | environment-variable path bridge + per-stage directory map (written before the path modules were patched) | new files; zero effect unless `COLDSTART20_*` set |
| 22:42:30 | stage-03 run completes | 1024/1024, 0 failed, 100 direct, 1848 transitions, 20 planes, 269.9 s | 20H tree only |
| 22:43:10 | `coldstart20/model20.py` (final, 40,124 B) | authoritative 20H model finalised (tables, contract, payloads, stack) | new file |
| 22:43:43 | `native3d/common.py` (10,391 B), `native3d/route_model.py` (15,331 B), `native3d/phase2.py` (13,715 B), `xyzrouter/paths.py` (4,671 B), `nonc4/paths.py` (2,661 B) | `patch_paths_profile.py` applied: run-dir env overrides, model-derived `MOVABLE_PLANES`, interface heights from the model, Phase-2 inherited crossing total, XYZ/nonc4 path re-pointing | all defaults are the frozen paths/values (3.6-3.8) |
| 22:43:49 | `xyzrouter/g4/paths.py` (7,491 B) | `patch_paths_profile.py`: `G4_ROOT` env override, start fingerprint computed from `best_valid` (no more literal SHA/crossings), hard failure for 20H if the start is missing | on 21H the computed values equal the frozen literals (5.2) |
| 22:44:28 | `reheight21/validate21.py` (151,157 -> 154,420 B), `coldstart20/bootstrap.py` (11,539 B final) | `patch_profile_generic.py` plus re-point of validator SPEC tables to `M.SPEC_*`/`SPEC_PLANE_COUNT`; bootstrap finalised (fslw port-row z re-point with row-pitch assertion) | 21H validator behaviour unchanged; 20H checks strict (3.5, 5.4) |
| 22:45:17 | `run_initial_20h/validation.json` | independent frozen validation of the 20H stage-03 run: all PASS, 0 violations, 37.95 s | no validation standard relaxed (5.4) |
| 22:45:53 | `nonc4/assign_nc.py` (20,610 -> 21,925 B) | 20H family-pure allocation branch (5 Z1 + 7 Z2 planes) guarded by `M.Z2_OTHER_PLAN`; 21H fallback preserved | **no audited patch script** - see section 6 |
| 22:46:27 | `coldstart20/run_validate.py` | 20H validator wrapper (bootstrap-first, frozen `validate21` in full, summary JSON) | new file; does not relax checks |
| 22:46:38 | `nonc4/data.py` (9,050 -> 9,651 B) | profile-driven allowed plane sets: `Z1_OTHER_PLANES`/`Z2_OTHER_PLANES` derived from the active model, literal 21H tuple kept only as fallback | **no audited patch script** - see section 6 |
| 22:46:42 | **stage-04 run starts** (`nonc4_programme/_logs/run.log`) | live C4-free programme (`run_nonc4 screen`; SA cost curves) | 20H tree only |
| 22:47:01 | `nonc4/assign_opt.py` (14,216 -> 14,885 B), `coldstart20/run_nonc4.py` (20,821 B) | assign_opt family/plane slices from the active model; new stage-04 driver (E0/screen/E1/E3/select/summary) | assign_opt fallback keeps 21H behaviour; driver is new |

Files modified **before** this rebuild window but part of the current code state
(not 20H changes, listed so the diff is not mis-attributed): `xyzrouter/local_reroute.py`
(2026-11-16 18:04, multi-arc policy propagation), `layer2d.py` (2026-11-16 19:55,
multi-arc policy), and six `xyzrouter/g4/*.py` files (2026-11-16 23:48-23:49,
equal-counted-budget patch). Frozen 21H files untouched during the rebuild:
`reheight21/plots21.py`, `report21.py`, `archive21.py`, `fanout.py`, `assemble.py`,
`run_all.py`, all `native3d/run_*`, `global_optimizer`, `finalize_phase2`,
`validator*`, all `xyzrouter/*` except the two path modules, all `g4/*` except
`paths.py`.

---

## 2. Why the change is a configuration swap, not an algorithm rewrite

Every frozen pipeline module imports the height table through
`from ..reheight21 import model as M` at import time. The rebuild therefore does
**one structural thing**: it registers a different module under that key before any
pipeline import (`coldstart20/bootstrap.py:66-72`), and re-points the handful of
legacy constants/paths that are not read through `model` (interface heights in
`common`/`l3d`/`fslw`, writable directories, inherited crossing totals, start
fingerprints). No search operator, cost function, acceptance rule, threshold or
validator geometry check was edited.

Consequence: every change below is either (a) a new file, (b) a seam that is inert
unless the 20H profile/env is active, or (c) the replacement of a hardcoded
expectation by a value read from the **active** profile (which equals the old literal
on the 21H profile).

---

## 3. File-by-file log

### 3.1 `four_side_1024/l3d/layers.py` - stack gate (13,457 -> 15,773 B)

* **What changed:**
  * `interface_rows` became a per-stack field (`LayerStack.interface_rows`,
    `layers.py:62,108-110`) with a `_rows()` accessor (`:85-115`); default is the
    frozen `INTERFACE_ROWS = {'z1': 0.0, 'z2': 0.5}` (`:32`);
  * the routing-id validation no longer requires ids to be *contiguous* from L2 -
    they must start at L2 and be unique (`:127-143`), so the 20H id set
    `{2..18, 20}` is legal;
  * `build_stack()` accepts `interface_rows=` (`:245-251`); docstring records the 20H
    +0.025/+0.525 use (`:89-99,250-251`);
  * every geometric check is untouched: interface-row clearance, neighbour pitch,
    glass, min pitch, L1+ids set (`:116-160`).
* **Why:** the frozen stack could not represent the 20H table at all - a probe showed
  two hard failures: `L20 = -0.025` is only 0.025 mm from the frozen interface row
  `z1 = 0.0` (clearance check), and the id set is non-contiguous
  (`reheight21.md` section 9.1). Both are configuration, not geometry.
* **Legacy preservation:** with default arguments (`interface_rows=None`) the stack
  is exactly the frozen one: `INTERFACE_ROWS` default factory, same pitch/clearance
  checks, contiguous 21H ids still pass the relaxed rule. Evidence: the 21H stack and
  consistency tests still pass; the 20H run's `validator_consistency_tests.json`
  exercises both `world_accepts_50um_plane_separation` and
  `world_rejects_49um_plane_separation` with all passed [V]; the 20H stack is built
  only through `model20.layer_stack()` (`model20.py:581-600`) [V].

### 3.2 `reheight21/model.py` - 21H table -> profile constants (31,248 -> 37,190 B)

* **What changed:** the 21H height table no longer lives only as literals; the module
  now exposes the *profile contract* that a replacement model must provide:
  `MODEL_NAME` (`:92`), payload schema constants (`:264-269`),
  `CONTRACT_*` (`:273-302`), `SPEC_*` (`:304-322`), the `Z2_OTHER_PLAN` hook
  (`:252,322`), `PROFILE='21_height_rebalanced'`, and the `allocate_z2_other`
  compatible seam. The 21H values themselves are unchanged:
  `Z1_INTERFACE_MM = 0.0` / `Z2_INTERFACE_MM = 0.5` (`:103-104`), 19 body planes incl.
  `(19, 0.65)` (`:108-114`), 21 plane ids (`:131-132`), 8-entry
  `Z2_OTHER_OLD_TO_NEW` (`:243-246`), manual z table (`:203-220`).
* **Why:** `assign21`/`run21`/`validate21` had the 21H expectations hardcoded; they
  now read `M.CONTRACT_*`/`M.SPEC_*`, so a different model supplies a different
  contract without touching the consumers.
* **Legacy preservation:** in a plain process (no bootstrap) the module is the 21H
  module and every `CONTRACT_*`/`SPEC_*` value equals the old literal. Strongest
  evidence: the frozen 21H `assign21.build_assignment()` still reproduces the
  archived `assignment_1024.csv` exactly and all invariants pass (5.1) [V]. The
  frozen 21H snapshot's public API is preserved (the audit's section 1.1 inventory is
  a subset of the current module).

### 3.3 `reheight21/run21.py` - stages A-F (59,279 -> 59,278 B)

* **What changed:** stage A reads `expected_counts = dict(M.CONTRACT_PLANE_COUNTS)`
  (`:173`), asserts `len(direct) == M.CONTRACT_DIRECT_ROUTES['total']` (`:182-184`),
  checks `len(heights) != len(M.PLANE_IDS)` and logs the derived height count
  (`:178-186`).
* **Why:** the frozen stage A fail-fast contained a 21-entry literal count table and
  `!= 21` / `!= 100` height/direct assertions; a 20H run would otherwise abort.
* **Legacy preservation:** identical values on the 21H profile (the contract constants
  are the frozen numbers). Remaining 21H literals in this file are report-only and
  were left untouched (listed in `pipeline_map.md` section 5: `layer_model='21
  heights'` `:266`, `expected_transitions=2*(len(rows)-100)` `:240-241`).

### 3.4 `reheight21/assign21.py` - assignment + audit/diff/reporting (68,627 -> 73,001 B)

Applied in this order (all exact-match, occurrence-count asserted - a half-applied
patch is impossible):

1. **`patch_profile_generic.py`** (`PATCHES` list, lines 27-222 of the script):
   * expected values now come from the active contract:
     `EXPECTED_PLANE_COUNTS = M.CONTRACT_PLANE_COUNTS`,
     `EXPECTED_DIRECT_ROUTES = int(M.CONTRACT_DIRECT_ROUTES['total'])`, ..., manual
     orbit sets `dict(M.CONTRACT_MANUAL_ORBIT_PLANE_SETS)` (current `:74-86`);
   * `_z2_other_allocation()` delegates to `M.allocate_z2_other(z2_orbits,
     baseline['by_id'])` (current `:184`; 20H implementation
     `model20.py:540-577`), which keeps whole C4 orbits on one plane but may mix
     baseline old layers per plane;
   * invariants: `all_21_planes_used` -> `all_model_planes_used`,
     `height_count_21_distinct` -> `height_count_distinct`,
     `z2_other_counts_48_...` -> `z2_other_counts_match_contract`,
     `z2_other_orbits_follow_old_layer_map` -> `..._follow_profile_plan` plus a new
     exhaustiveness check; `_check_contract` keeps the same arithmetic;
   * payload schema/experiment/model names read from the profile (`model.py:264-269`,
     `M.MODEL_NAME`).
2. **`patch_assign21_reporting.py`** (lines 24-186 of the script): only payload/report
   code, no search logic:
   * new `_z2_orbit_summary()` (current `assign21.py:328`) derives
     `{old_layer: {new_planes: routes}}` from the real whole-orbit plan;
   * `build_audit` per-plane Z2 counts iterate `M.CONTRACT_Z2_OTHER_COUNTS`; the
     `z2_other.old_to_new` block handles the plan form (and emits `plan=None` for
     21H); `build_diff` Z2 mapping handles `new_planes`/multi-plane rows;
   * notes/report lines become profile-derived (manual z list, Z1 plan capacities,
     experiment name).
3. **`patch_assign21_literals.py`** (whole file): remaining "21"/"19"/interface-z
   literals in questions/notes/log headers/markdown headers replaced by
   `len(M.PLANE_IDS)` / `M.plane_z(1001/1002)` / `M.EXPERIMENT_NAME`
   (e.g. Q6 `answer=(audit['height_count'] == len(M.PLANE_IDS))`, Q7 orbit evidence
   computed from the real groups).

* **Why:** the assignment audit/diff/reporting unconditionally dereferenced
  `M.Z2_OTHER_OLD_TO_NEW.items()` (None for 20H -> `AttributeError`) and compared
  against 21H counts; the 20H plan needs a whole-orbit allocation that mixes baseline
  old layers across the 7 surviving Z2 planes.
* **Legacy preservation:** on the 21H profile the plan form is not used
  (`Z2_OTHER_PLAN = None`, `Z2_OTHER_OLD_TO_NEW` is the 8-entry map), so the payloads
  are structurally the same; the assignment is bit-identical - **0 row mismatches vs
  the archived `assignment_1024.csv` and 34/34 invariants pass (5.1)** [V].
  The 20H audit additionally reports the mixed old->new relation explicitly (probe
  recorded in `reheight21.md` section 9.2, e.g. `8:{1002:48}, 9:{18:48},
  14:{16:16,17:32}, ...`, and per-new-plane 9:56, 14:56, 15:56, 16:56, 17:64, 18:64,
  1002:48).

### 3.5 `reheight21/validate21.py` - frozen independent validator (151,157 -> 154,420 B)

* **What changed (`patch_profile_generic.py` lines 253-348):**
  * imports the active model: `from . import model as M` (`:68`);
  * `RUN_DIR_21H` default follows `M.RUN_DIR` if the profile defines it
    (`:77-78`, keeps the frozen 21H default otherwise);
  * `SPEC_BODY_HEIGHTS`, `SPEC_INTERFACE_PLANES`, `SPEC_INTERFACE_IDS`,
    `SPEC_MANUAL_FIXED`, `SPEC_EXPECTED_ASSIGNED`, `SPEC_DIRECT_TOTAL`,
    `SPEC_DIRECT_BY_PLANE`, `SPEC_BODY_PLANE_COUNT`, `SPEC_PLANE_COUNT` = the active
    model's tables (current `:88-96`);
  * the checks that hardcoded 21/19/2/computed plane counts now compare against
    `SPEC_PLANE_COUNT` / `SPEC_BODY_PLANE_COUNT` with renamed violation kinds
    (`plane_count_mismatch`, `body_plane_count_mismatch`,
    `assignment_used_planes_mismatch`, `planes_audited_count_mismatch`,
    `model_plane_count_mismatch`; current `:437-447,2024-2033,2711-2746`);
  * **nothing else**: all geometry/threshold constants and check functions are the
    frozen ones (R15, 0.05 clearance, D56, glass, ports, crossings, consistency
    suite) - the audit's complete list in `reheight21.md` section 4.2 is untouched.
* **Why:** the validator deliberately validates against a frozen in-file SPEC table;
  for 20H that table must be the 20H configuration (20/18/2 planes, new z), while
  every acceptance rule stays identical.
* **Legacy preservation:** with no bootstrap, `M` is the 21H model, so every SPEC
  value equals the frozen literal and validator behaviour is unchanged. The 21H
  `BASELINE_REGRESSION` (`:98-106`, 18L numbers) is untouched and only used in
  `--baseline-model` mode. For 20H, the validator was run in full and passed
  (5.4) [V].

### 3.6 `native3d/common.py` (10,391 B), `native3d/route_model.py` (15,331 B), `native3d/phase2.py` (13,715 B)

Applied by `patch_paths_profile.py` lines 23-126:

* `native3d/common.py`
  * imports `profile_env` (`:14`);
  * `E5_DIR`, `BASELINE_21H_DIR`, `RUN_DIR` read `COLDSTART20_E5_DIR`,
    `COLDSTART20_FANOUT_BASELINE_DIR`, `COLDSTART20_NATIVE3D_ABC_RUN` with the
    frozen 21H defaults (`:19-30`);
  * `MOVABLE_PLANES` is now model-derived: every model plane that is not a manual
    plane (`:48-50`) - 13 ids incl. 19 on the 21H profile, 12 ids (no 19) on 20H;
    `MANUAL_PLANES` was already `M.MANUAL_PLANE_IDS` (`:48`).
* `native3d/route_model.py`: the interface-heights tuple in `structure_errors()` is
  read from the model (`:221-226`) instead of `(0.0, 0.5)`.
* `native3d/phase2.py`
  * imports `profile_env` (`:18`); `RUN2` from `COLDSTART20_NATIVE3D_DEF_RUN`
    (`:27-28`);
  * `PHASE1_DIR = N.RUN_DIR` (so it follows the active profile run dir, `:24-25`);
  * `BASELINE_CROSSINGS` is no longer the literal 2440: `_inherited_crossings()`
    (`:31-57`) reads `COLDSTART20_PHASE1_CROSSINGS` or the accepted Phase-1
    `crossing_stats.json`; the 2440 value survives only as the 21H fallback, and a
    20H process raises if the accepted layout has no crossing stats
    (`:52-56`).
* **Why:** `MOVABLE_PLANES` with id 19 crashes under the 20H profile
  (`KeyError: 19` in `sorted_by_abs_dz`, reproduced in `native3d_def.md` section 0);
  the Phase-2 accept gate must inherit the 20H Phase-1 crossing total; the interface
  tuple must be the 20H rows.
* **Legacy preservation:** every new value defaults to the frozen 21H
  path/value when `COLDSTART20_*` is unset. Verified probe in a plain process:
  `MOVABLE_PLANES = (6,7,20,1001,8,9,14,15,16,1002,17,18,19)`,
  `E5_DIR = outputs/.../NON_C4_CROSSING_OPT_1024/E5_joint_repair_final`,
  `RUN_DIR = outputs/.../NATIVE_3D_CROSSING_OPT_1024` [V]. On the 20H profile the
  same tuple derives to 12 ids and the inherited count is read from the 20H Phase-1
  artifact.

### 3.7 `xyzrouter/paths.py` (4,671 B) and `xyzrouter/g4/paths.py` (7,491 B)

* `xyzrouter/paths.py`: imports `profile_env` (`:11`) and resolves
  `NATIVE_JOINT_DIR`, `NATIVE_PHASE1_DIR`, `NON_C4_DIR`, `E5_DIR`, `XYZ_RUN_DIR` from
  `COLDSTART20_NATIVE3D_DEF_RUN` / `_NATIVE3D_ABC_RUN` / `_NONC4_ROOT` / `_E5_DIR` /
  `_XYZ_RUN` (`:16-27`); `DIRS` (`:30-44`) unchanged in shape; the frozen
  `best_valid`/`baseline_authoritative` sub-paths follow the new run root.
* `xyzrouter/g4/paths.py`:
  * `G4_ROOT = PE.path_env('G4_ROOT', ROOT/'experiments'/'xyz_joint_g4_1024')`
    (`:26-27`), so 20H writes to `experiments/COLD_START_20_HEIGHT_1024/08_g4`;
  * **the start fingerprint is computed, not hardcoded**: `_start_fingerprint()`
    (`:41-73`) hashes `best_valid/routes_l3d.json` and reads
    `crossing_stats.json`/`summary.json` totals; `COLDSTART20_START_SHA` /
    `COLDSTART20_START_CROSSINGS` override for bit-reproducible reruns; a 20H
    process raises if the start point is not a validated G3 optimum (`:66-69`).
* **Why:** all `xyzrouter`/`g4` modules import `model`/`route_builder` tables at
  import time; the run directories were frozen 21H literals, and the G4 start was a
  literal SHA+count that is meaningless for a different height profile (and was
  already wrong for 21H chain links - it reported 1322 for a 1294-crossing link,
  `g4.md` section 3.4).
* **Legacy preservation:** unset env -> frozen paths. Verified probe in a plain
  process: `XYZ_RUN_DIR = outputs/manual_c4_new_connectivity/XYZ_JOINT_G123_1024`,
  `START_DIR = .../XYZ_JOINT_G123_1024/best_valid`,
  `START_ROUTES_SHA256 = 711cf910d5c75ea788be877ef88b588fe3d59a90a2ae2d3636bb5b5896834077`,
  `START_CROSSINGS = 1322`, `G4_ROOT = experiments/xyz_joint_g4_1024` [V]. The SHA
  was independently recomputed from the frozen file and matches (5.2) [V].

### 3.8 `nonc4/paths.py` (2,661 B)

* **What changed (`patch_paths_profile.py` lines 158-183):** `EXPERIMENT_ROOT` =
  `COLDSTART20_NONC4_ROOT` (default frozen `NON_C4_CROSSING_OPT_1024`);
  `BASELINE_21H_DIR` = `COLDSTART20_FANOUT_BASELINE_DIR` (default frozen 21H run) -
  this is the **368-manual-U geometry source**; `BASELINE_18L_DIR` unchanged
  (`:19-28`). `use_experiment()` re-binding (`:43-60`) untouched.
* **Why:** the C4-free campaign reads its identity rows and manual-U geometry from the
  "frozen baseline"; for 20H that must be the stage-03 20H run (`run_nonc4.py:111`
  sets it explicitly as well).
* **Legacy preservation:** unset env -> the frozen 21H baseline path; the 21H
  campaign archive stays readable/rerunnable. `run_nonc4` overrides the constant at
  runtime (no source edit per run).

### 3.9 `nonc4/data.py`, `nonc4/assign_nc.py`, `nonc4/assign_opt.py` (unaudited, 22:45-22:47)

* **`data.py`** (9,050 -> 9,651 B): allowed plane sets are now profile-driven -
  `Z1_OTHER_PLANES = tuple(pid for pid,_orbits in M.Z1_OTHER_PLAN)` (`:24`);
  `Z2_OTHER_PLANES` from `M.Z2_OTHER_PLAN` when present (`:25-26`), else the frozen
  21H literal `(9,14,15,16,1002,17,18,19)` (`:27-28`).
* **`assign_nc.py`** (20,610 -> 21,925 B): `default_allocation()` gained a 20H branch
  guarded by `getattr(M, 'Z2_OTHER_PLAN', None)` (`:72-86`): family-pure 5 Z1 + 7 Z2
  planes (Z1V 6,7; Z1H 20,1001,8; Z2_NE 9,14; Z2_SE 15,16; Z2_NW 17; Z2_SW 18,1002),
  with a hard check that 5+7 planes are present; the 21H plan incl. `[19, 1002]`
  remains the fallback (`:87-94`). `_MANUAL_EXPECTED` unchanged (`:55-59`).
* **`assign_opt.py`** (14,216 -> 14,885 B): family `default_allocation()` slices now
  read the profile-driven `D.Z1_OTHER_PLANES`/`D.Z2_OTHER_PLANES` (`:307,317-322`)
  and accept explicit `z1_planes`/`z2_planes` (`:328-329`), so the 12-plane 20H
  family plan is expressed without an `optimise_allocation` glue change.
* **Why:** `data.Z2_OTHER_PLANES` containing plane 19 makes `assign_nc.build_rows`
  raise `ValueError: route ...: plane 19 not in model` under the 20H profile; and the
  13-plane `default_allocation` would assign routes to the deleted plane.
* **Legacy preservation:** all three keep the 21H literal/branch as the fallback and
  are only reached through the 20H driver with the profile installed. The 21H
  campaign's archived artifacts are untouched; re-running the 21H nonc4 CLI in a
  plain process follows the old code path.
* **Audit gap:** these three edits were made between the audit snapshot (22:40) and
  the stage-04 driver (22:47) and have **no exact-match patch script in `00_audit/`**
  (the four scripts there do not reference nonc4/data/assign_nc/assign_opt). They
  are reconstructed here from content+mtime; a retro-audited script
  (`patch_nonc4_profile.py`) should be added so the change set is fully
  reproducible/verifiable (`pipeline_map.md` section 7.7).

### 3.10 New package `four_side_1024/fanout1024/coldstart20/`

| file | size | role | key API / safety |
|---|---|---|---|
| `__init__.py` | 1,455 B | package docstring; declares the 20H rebuild as a profile swap | lists planned `tests_model20`/`drivers` modules (not yet present) |
| `model20.py` | 40,124 B | **authoritative 20H model**, drop-in for `reheight21.model` | 20 planes/18 body, L19 deleted, +0.025 mm; thresholds bit-identical (`:128-136`); contract/spec tables (`:306-346`); `allocate_z2_other` (`:540`); `layer_stack` (`:581`); payload builders (`:642-819`) |
| `bootstrap.py` | 11,539 B | import-time installer (module-key swap + interface constants + port row z + stack reset + run-dir binding) | installs on import (`:187`); `assert_20_height_profile()` (`:146-163`) makes a silent 21H run impossible; fslw row-pitch assertion (`:99-111`) |
| `paths20.py` | 3,247 B | all writable 20H directories + `COLDSTART20_*` mapping | `ENV_PATHS` (`:51-61`); frozen defaults untouched |
| `profile_env.py` | 2,706 B | env-var bridge used by the patched frozen path modules | `path_env/int_env` with frozen defaults; `is_20h()` (`:36-38`) |
| `run_initial.py` | 2,663 B | stage-03 driver: assignment + stages A-F | bootstrap-first (`:35`); `assign21.main()` (`:63`); `run21.run_stages` (`:71`) |
| `run_validate.py` | 3,292 B | 20H validator wrapper | frozen `validate21.validate` in full (`:43-46`); `--regression` never used |
| `run_nonc4.py` | 20,821 B | stage-04 driver (E0/screen/E1/E3/select/summary/all) | bootstrap-first (`:53`); re-points nonc4 paths to the 20H baseline (`:110-111`); never copies manual geometry from 21H |

The package is imported by name (`from four_side_1024.fanout1024.coldstart20 import
bootstrap`) **before** any pipeline import; a new stage driver must copy that
pattern (do not use `python -m` on the frozen native3d/xyzrouter/g4 modules).

---

## 4. Changed vs not changed

### 4.1 Geometry configuration that changed

See `pipeline_map.md` section 6.1 for the full table: plane table (21 -> 20; L19
deleted; every surviving height +0.025 mm), interface heights (0.0/0.5 ->
+0.025/+0.525), Z2-other whole-orbit allocation over 7 planes, derived per-plane
contract counts, model payload schema names (`reheight20_*`), writable run
directories, inherited crossing totals (Phase 2), G4 start fingerprint, Native-3D
movable-plane tuple.

### 4.2 Rules that were NOT changed (no relaxation anywhere)

R15 = 15.0 mm; 0.05 mm true-3D clearance; 0.05 mm minimum layer pitch; strict
same-layer D56 (width 0.05 + edge gap 0.03 mm, legal transverse crossings); glass
150x150x1 mm, z in [-0.35, +0.65] mm; 1024 connections / 512 z1 + 512 z2; 368 manual
U routes on plane ids 2,3,4,5,10,11,12,13 with counts 64/64/64/64/16/16/40/40;
interface-direct count 100 = 52 + 48; transition total 1848 endpoints; all validator
tolerances and the independent-crossing definition; port geometry (column/row/connector
pitches) - only the two port row z values follow the interface heights, with the
0.5 mm row pitch asserted unchanged.

### 4.3 Explicit statement

The 20H rebuild changed **geometry configuration** (plane table and derived
allocation/contract). It did **not** relax any **validation standard**: the validators
are the frozen `validate21` / `validate_native3d` / `validate_xyz` code with the 20H
configuration tables; no check was skipped, no threshold widened, no tolerance
loosened, and the 21H number-lock regression mode is never used for 20H. Evidence in
section 5.4.

---

## 5. Legacy 21-height preservation evidence

### 5.1 21H assignment reproduces the archived artifact bit-for-bit

Verification (read-only, in-memory; `assign21.build_assignment()` only, no writes) in
a plain process without the bootstrap, i.e. the 21H profile:

```text
built_rows 1024   archived_rows 1024
row_mismatches 0  field_mismatches 0        # all 27 columns, compared as strings
all_invariants_passed True
invariants_total 34   passed 34   failed []
```

(The first comparison pass reported 1024 "mismatches" only because the archived CSV
begins with a UTF-8 BOM that renamed the first header field; re-reading with
`utf-8-sig` gives 0/0 as above.) Archived file:
`outputs/manual_c4_new_connectivity/FANOUT_FIRST_21_HEIGHT_REBALANCED_1024/assignment_1024.csv`
(126,652 B, 2026-11-03 21:37:40). This proves the profile-generic rewrite of
`model.py`/`assign21.py` is a **behaviour-preserving refactor** on the 21H profile:
same 1024 rows, same values, same 34 invariants.

### 5.2 21H path modules still resolve to the frozen paths and G4 start values

Plain process (no `COLDSTART20_*` variables), probe output:

```text
XYZ_RUN_DIR     .../outputs/manual_c4_new_connectivity/XYZ_JOINT_G123_1024
START_DIR       .../outputs/manual_c4_new_connectivity/XYZ_JOINT_G123_1024/best_valid
START_SHA       711cf910d5c75ea788be877ef88b588fe3d59a90a2ae2d3636bb5b5896834077
START_CROSSINGS 1322
G4_ROOT         .../experiments/xyz_joint_g4_1024
NONC4_ROOT      .../outputs/manual_c4_new_connectivity/NON_C4_CROSSING_OPT_1024
NONC4_BASELINE  .../outputs/manual_c4_new_connectivity/FANOUT_FIRST_21_HEIGHT_REBALANCED_1024
E5_DIR          .../outputs/manual_c4_new_connectivity/NON_C4_CROSSING_OPT_1024/E5_joint_repair_final
NATIVE3D_RUN    .../outputs/manual_c4_new_connectivity/NATIVE_3D_CROSSING_OPT_1024
MOVABLE_PLANES  (6, 7, 20, 1001, 8, 9, 14, 15, 16, 1002, 17, 18, 19)
21H_PROFILE_PLANES 21
```

Independent SHA check of the frozen start file:
`outputs/manual_c4_new_connectivity/XYZ_JOINT_G123_1024/best_valid/routes_l3d.json`
(3,693,355 B, 2026-11-04 13:45:28) -> SHA-256
`711cf910d5c75ea788be877ef88b588fe3d59a90a2ae2d3636bb5b5896834077`, exactly the
archived value; the computed `START_CROSSINGS` is 1322 (read from the start's
`crossing_stats.json`), exactly the archived constant. So the new computed
fingerprint reproduces the frozen literal values on the frozen data.

### 5.3 Env-default / profile-guard design

* every patched path module uses `profile_env.path_env(name, frozen_default)` /
  `int_env(name, default)` - with the variable absent the frozen 21H value is
  returned (`profile_env.py:41-52`); `paths20.ENV_PATHS` is published only by
  `bootstrap.install()` (`bootstrap.py:174-180`);
* `bootstrap.assert_20_height_profile()` (`:146-163`) fails if the model key was not
  swapped, if plane 19 is present, or if the interface constants were not
  re-pointed, so a 20H driver cannot silently run the 21H table; conversely, a plain
  process never installs the 20H model;
* `_inherited_crossings()` (`native3d/phase2.py:52-57`) and
  `_start_fingerprint()` (`g4/paths.py:66-69`) **raise** for 20H rather than fall
  back to the 21H numbers (2440/1322), preventing silent mixed-profile metadata;
* `is_20h()` is driven only by `COLDSTART20_PROFILE == '20_height_raised'`
  (`profile_env.py:36-38`).

### 5.4 The 20H run passes the frozen validators (no relaxed standard)

Stage-03 `run_initial_20h/validation.json` (`runtime_seconds=37.95`, `baseline_model=false`):

```text
route_count 1024, routed 1024, failed 0, route_count_declared 1024
min_3d_clearance_mm 0.086498778   (lower bound 0.05, unchanged)
geometry_pass true, contract_pass true, validation_pass true, exit_code 0
validator_consistency_passed true
counts: direct_routes 100 (52 z1 / 48 z2), transitions 1848,
        same_plane_crossings 12338 / pairs 10133, same_plane_crossing_violations 0,
        min_non_crossing_centerline_mm 0.080748117, planes_audited 20,
        flat_arc_count 1700, min_flat_arc_radius_mm 15.0,
        min_transition_sampled_radius_mm 14.99999998, violation_total 0
```

`validator_consistency_tests.json`: `plane_count=20`, `all_passed=true`, including
`model_min_pitch_is_50um`, `world_rejects_49um_plane_separation`,
`validator_rejects_49um_plane_separation`, `invalid_49um_stack_rejected`,
`d56_same_plane_49um_xy_is_illegal`, `true_port_table_poses_consistent` - i.e. the
strict rules still reject sub-clearance geometry under the 20H profile. The 20H
run's `assignment_audit.json` reports `all_invariants_passed=true`.

---

## 6. Residual risks / unlogged-change reconciliation

1. **Unaudited nonc4 edits** (section 3.9): `nonc4/data.py`, `assign_nc.py`,
   `assign_opt.py` changed 22:45-22:47 without a patch script in `00_audit/`.
   Recommend adding an exact-match script now (the files still contain the old code
   as fallback branches, so the patch can be written and re-applied against the
   22:33 snapshot zip).
2. **Provenance strings** in the completed 20H run still carry 21H schema/experiment
   names (`routes_l3d.json` `layer_model`/`experiment`, `final_stats.json`,
   `crossing_stats.json`, `validation.json`) - configuration/report metadata only;
   must be fixed before the final report (`pipeline_map.md` section 7.6).
3. **`validate_nc._EMPTY_PLANE_KINDS`** filter name is stale for stage 04
   (`nonc4/validate_nc.py:33-34`); it does not weaken geometry, but the empty-plane
   filter needs re-pointing.
4. **Stage 04 is running while this log is written**, and the concurrent workstream
   kept adding 20H drivers after this log's file-by-file snapshot (taken 22:47): by
   22:55 it had added `coldstart20/run_native3d_phase1.py` (22:48:24),
   `coldstart20/plot_layers20.py` (22:51:57), `coldstart20/run_nonc4.py` update
   (22:51:29), `coldstart20/convert_multiarc20.py` (22:54:06),
   `coldstart20/run_g123.py` (22:54:27), plus `00_audit/patch_g123.py`
   (22:51:38, **applied 22:54:43-22:55:00** to `xyzrouter/optimizer.py`,
   `run_g1.py`, `run_warmstart_chain.py`, `run_router_validation.py`: stage-scoped
   checkpoint root, profile-env import, start-total read from the start layout,
   20H validation failure fatal, 2409 gates replaced by the authoritative start
   total) and stage-03/04 outputs/analysis
   (`03_fanout_and_xy/crossing_summary_20h.*`, `build_crossing_summary.py` 22:54:01,
   stage-04 E2/E3 runs). Those additions are **not covered by this log's
   file-by-file sections** and must be logged as they land, with the same
   "bootstrap-first + frozen defaults + no threshold change" argument; their
   existence is recorded here (time-stamped) so the change set stays auditable.
5. **The 21H archives are not byte-identical to the current code** for
   `layer2d.py`/`local_reroute.py` (multi-arc policy added 2026-11-16) and six
   `g4/*.py` files (equal-budget patch 2026-11-16). Those changes pre-date the 20H
   rebuild and are not part of this log; a 20H archive must snapshot the current
   sources, not the archived code directories.
6. The full source tree before the rebuild is preserved at
   `experiments/COLD_START_20_HEIGHT_1024/_source_backup/four_side_1024_src_20261117_223317.zip`
   (8,210,719 B) for diffing/rollback.

---

## 7. Read-only re-verification commands (no pipeline stage)

```powershell
cd "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D"
# 1) 21H assignment regression (in-memory; prints row_mismatches 0 / invariants 34/34)
$code = @"
import csv
from four_side_1024.fanout1024.reheight21 import assign21
rows = assign21.build_assignment(force=True)
base = list(csv.DictReader(open(r'outputs\manual_c4_new_connectivity\FANOUT_FIRST_21_HEIGHT_REBALANCED_1024\assignment_1024.csv', newline='', encoding='utf-8-sig')))
bad = sum(1 for r,b in zip(rows,base) if any(str(r.get(k)).strip()!=str(b.get(k)).strip() for k in b))
a = assign21.build_audit(rows, assign21._state()); inv=a['invariants']
print('row_mismatches', bad, 'invariants', sum(1 for x in inv if x['passed']), '/', len(inv))
"@
$code | .venv\Scripts\python.exe -
# 2) frozen path/fingerprint resolution
.venv\Scripts\python.exe -c "from four_side_1024.fanout1024.xyzrouter.g4 import paths as GP; print(GP.START_ROUTES_SHA256, GP.START_CROSSINGS, GP.START_DIR)"
# 3) frozen start hash
(Get-FileHash "outputs\manual_c4_new_connectivity\XYZ_JOINT_G123_1024\best_valid\routes_l3d.json" -Algorithm SHA256).Hash
# 4) 20H profile sanity (separate process; installs the profile)
.venv\Scripts\python.exe -c "from four_side_1024.fanout1024.coldstart20 import bootstrap as B; print(len(B.M20.PLANE_IDS), 19 in B.M20.PLANE_IDS, B.M20.Z1_INTERFACE_MM, B.M20.Z2_INTERFACE_MM)"
```

Expected: `row_mismatches 0 invariants 34 / 34`;
`711cf910... 1322 .../XYZ_JOINT_G123_1024/best_valid`; the same hash;
`20 False 0.025 0.525`.

---

## Late-session changes (2026-11-17 22:55 -> 2026-11-18 02:30)

Sections 1-7 stop at the 22:55 snapshot. This section records **every source
and driver change made after 22:55**, plus the late in-session execution
patches and the resulting verification state. It was reconstructed read-only on
2026-11-18 02:00-02:30 from: file mtimes (local time, UTC+8) under
`four_side_1024/fanout1024/`, the audited patch scripts (their `--check` /
`--verify` modes were re-run; no patch was applied), the stage logs under
`experiments/COLD_START_20_HEIGHT_1024/`, and the final artifacts in
`12_reports/`. **No source file was modified while writing this section.**

Late file changes fall into three classes: (i) new `coldstart20/` drivers,
(ii) applied patch scripts for the frozen `native3d/`, `xyzrouter/`, `xyzrouter/g4/`
modules, (iii) late corrections to already-written patches. The four "not yet
documented" late patches named in the hand-over are items 11, 12, 13 and 15
below (item 11's implementation file is `build_final_report.py`, not
`collect_final.py` -- see the evidence column).

### 8.1 Chronological file-by-file table

| # | time (local) | file | change | why | 21H behaviour preserved | evidence |
|---|---|---|---|---|---|---|
| 1 | 22:54:40 | `coldstart20/plot_layers20.py` (new) | per-height figure driver: 20 plain + 20 crossing-annotated XY figures; imports the frozen `reheight21/plots21.py` read-only | the 20H deliverable needs per-height evidence; no frozen plot driver can bind the 20H model | new file only; writes under `03_fanout_and_xy/figures` | `03_fanout_and_xy/figures/{per_height_plain,per_height_crossings}/`, `figure_manifest.json` 22:55:10 (generated 22:55:10); README records the run |
| 2 | 22:54:43-22:55:51 | `00_audit/patch_g123.py` applied to `xyzrouter/{optimizer.py, run_g1.py, run_warmstart_chain.py, run_router_validation.py}` | stage-scoped checkpoint root (`<stage out>/checkpoints`); G1/P2 start total read from the start layout (`crossing_stats.json`) instead of the 2409 literal; 20H validation failure fatal; warm chain runs **in-process** under 20H; P2 `total_before/removed` from the real start | frozen `python -m` subprocesses would bind the 21H model; G1 and G3_cold shared one global checkpoint dir and overwrote it; 2409 != the 3061 20H start | profile-conditional: plain 21H process keeps log-only failure, its start total is 2409, and subprocess behaviour is unchanged | source markers: `optimizer.py:41-48,171-173` (stage-scoped root), `run_warmstart_chain.py:37-44` (`IN-PROCESS ...` branch), `run_g1.py:52-78` (authority crossing_stats); G1 + G3_cold ran concurrently 23:59->00:23 without checkpoint collision |
| 3 | 22:58:04-22:58:08 | `00_audit/patch_g4.py` applied to `xyzrouter/g4/{contract_audit.py, independent_metrics.py, run_g4b.py, paths.py, arm_base.py, artifacts.py}` | audit citations from the active model; port z from `M.interface_z`; `SCAN_CFG.max_target_layers = len(M.BODY_PLANES)` (18 at 20H); `assert_start_profile()` hard guard on `load_start()`; authority resolver with frozen-archive fallback; arm records the start's **own** crossing total (no more 1322 constant for other starts); validator subprocess is bootstrap-first; 20H snapshots write a real 20-plane `layer_planes.json` | a historical 21H G3 optimum must fail loudly in a 20H process; G4 `summary()/config.json` must not report 1322 for a different start; arms need a 20H `layer_planes.json` for validation | profile-conditional / inert on the 21H profile | `patch_g4.py --check` re-run 2026-11-18 02:00: `patches applied 0 / already applied 19 / files changed {} / all postconditions present`; `08_g4/START.json` records start `a6aa6997...`/1395; every arm's `validation/validation.json` PASS 0 violations |
| 4 | 22:58:21-22:59:20 | `00_audit/patch_native3d_def.py` **first application** to `native3d/{route_model.py, common.py, blocker_analysis.py, phase2.py, run_d.py, run_e.py, run_f.py, finalize_phase2.py}` | 20H interface-height tuple in `structure_errors()`; profile-aware candidate-pool path; 20H payload copies; fresh `best_valid/transition_stats.json`; data-driven baseline count; `run_f.py` reject-branch rollback restores the **pre-step** geometry (frozen defect #3) | Phase 2 cannot read the 21H pool/paths under 20H; the rollback defect can corrupt a layout | profile-conditional; defaults frozen; the rollback fix only differs when a rejected mutation follows an earlier mutation | mtimes `route_model.py` 22:58:21, `common/phase2/run_d/run_e/run_f` 22:59:20; A0 geometry gate failed 0/2 at 22:56:36 before the `route_model` fix and passed 11/11 at 22:58:27 after (stage-05 log); Phase-2 chain all stages `status=ok` |
| 5 | 23:00:24 | `coldstart20/run_native3d_phase2.py` (new) | bootstrap-first Phase-2 driver; runs `intervals -> blockers -> d -> e -> f -> fplus_1 -> fplus_2 -> nearmiss_1 -> nearmiss_2 -> finalize` **in-process** (`module.main(argv)`), asserts profile bindings, writes `phase2_chain_status.json` | frozen `python -m native3d.run_*` binds the 21H model first | new file; writes only `06_native3d_def/` | `06_native3d_def/run_native3d_phase2/logs/phase2_chain.log` 23:10:00->23:54:30, all stages ok; `phase2_chain_status.json` |
| 6 | 23:05:48 | `coldstart20/convert_multiarc20.py` (new) | 20H port of the archived Stage-0 ON->OFF conversion: re-plans exactly the routes with a real planar multi-arc body with the frozen G4 planner (`plan_candidates(mode='clean')`), deterministic, reports residual routes | strict common-start ablation needs the G3 optimum re-expressed in the OFF grammar | new file; archived 21H tool untouched | `09_multi_arc_ablation/common_start_off/` 01:18:50-01:19:59; `conversion_report.json` converted 212 / residual 1 / 1395->4559 |
| 7 | 23:08:08 | `coldstart20/run_multiarc.py` (new) | strict ON/OFF protocol driver (`start/convert/arm-on/arm-off/chain/all/analyse`), counted budget 24000 d56 / 9000 checks / 5400 s wall safety net, pre-registered feasibility rule: residual>0 => write `OFF_FEASIBILITY.json` + `ABORTED_OFF_INFEASIBLE.json`, do not run a diluted OFF arm | the 21H strict protocol tools are PowerShell and import-order unsafe; 20H must not fabricate an ON/OFF pair | new file; writes under `09_multi_arc_ablation/` | `START.json` 01:03:41; `logs/convert.log` 01:03:45->01:19:59; `ABORTED_OFF_INFEASIBLE.json` 01:19:59 (residual route 456) |
| 8 | 23:09:31 | `coldstart20/run_native3d_phase1.py` (new) | Phase-1 driver `a / b / c / materialize / validate / validate-planar / plots / summary / all`; A0 geometry gate is fatal | Phase 1 needs a bootstrap-first launcher; `reheight21.validate21` cannot judge mid-body layer changes (see item 10) | new file; writes only `05_native3d_abc/` | `05_native3d_abc/run_native3d_phase1/`: A 11/11 gate, C 3275->3103, `STAGE05_GATE.json`, `ACCEPTED_PHASE1.json` |
| 9 | 23:19:24 | `coldstart20/select_final.py` (new) | scans every stage's legal layout, ranks by (fully legal, then crossings) and can freeze the winner into `10_best_valid` with `BEST_VALID.json` + `SHA256.json` | final deliverable selection | new file; 20H tree only | `10_best_valid/selection_scan.json` 01:41:07; **current limitation recorded in §8.4 item 2** |
| 10 | 23:24:13-23:24:21 | `00_audit/patch_native3d_def.py` **corrected** and re-applied to `native3d/finalize_phase2.py`; `00_audit/patch_native3d_def_verify.json` regenerated | **validator-selection correction**: the accepted Native-3D layout must be judged by `native3d.validate_native3d`, not by the planar-assembly contract validator `reheight21.validate21`; the `E5_EXPECT`/`--regression` number lock is never enabled; archive/plots stay below the 20H run | the first version wrongly told 20H finalisation to use `validate21`; `validate21`'s route contract is the pre-Native-3D 5-part lead/transition/body structure and **cannot** judge bodies with mid-path layer changes -- measured 364 violations on the Phase-1 layout and 577 on the converted OFF start, i.e. a contract mismatch, not a geometry violation | 21H branch unchanged (its archives were also validated with `validate_native3d`; `validate21` remains the planar-stage validator only) | `patch_native3d_def.py --verify` 2026-11-18 02:00: `21h: PASS (13 checks, 0 failed)` / `20h: PASS (24 checks, 0 failed)`; `native3d/finalize_phase2.py:144-157` (comment + `from . import validate_native3d as V`), mtime 23:24:13; `06_.../validation/final/validation.json` validator `native3d.validate_native3d`, PASS, 0 violations |
| 11 | 01:41:32 | `coldstart20/build_final_report.py` (new, then **late artifact-resolution fix**) | final-metrics collector. Fixes: `_full_validation()` now searches `validation.json`, **`validation/validation.json`**, the stage/arm parent root and `validation/final/validation.json` and prefers the first payload that carries the full measurement block; `_crossing_stats()` walks layout dir, parent and grandparent (**arm-root `crossing_stats.json`**); a payload without `totals.crossings` falls back to the validator counts' **`same_plane_crossings`**; `min_3d_clearance_mm` prefers the **independent-validator measurement** over the router's `final_stats` acceptance bound | G4 arm `best_valid/` directories contain only `routes/assignment/layer_planes/SHA256`; their full validator report is `<arm>/validation/validation.json` and their crossing stats are `<arm>/crossing_stats.json`; without the fix all G4 arms read as "not measured" and `final_stats` would report the 0.05 mm bound instead of the measured clearance | new file; 20H tree only | `build_final_report.py:59-90` (validation/stats resolution), `:154-186` (`same_plane_crossings` fallback, validator-wins min 3D); `12_reports/final_metrics.json` 01:41:33 (S06 min 3D `0.068629474` = validator value, not `0.05`; every G4 arm has real 3D/counts) |
| 12 | 00:34:01 | `coldstart20/run_g123.py` (new, then **late idempotent-preflight fix**) | G123 driver: preflight snapshots the accepted Phase-2 `best_valid` as `baseline_authoritative` (`AUTHORITY.json` + `SHA256.json`), asserts the 20H data contract, recomputes the start total, runs the independent validator with `manual_policy='frozen'`; stage-scoped checkpoints. **Late fix:** if `AUTHORITY.json.routes_sha256` equals the source `routes_l3d.json` SHA and the snapshot files exist, preflight **reuses** the completed snapshot instead of `rmtree`+`copytree` | G1 and the G3 cold control were started **concurrently** (23:59) and both ran preflight; the raw `rmtree`+`copytree` race corrupted `baseline_authoritative` | 20H-only; the frozen 21H chain is untouched | `run_g123.py:783-797` (comment + idempotent branch), `:798-803` (rebuild only when needed); `run_g123.log` line `[preflight] reusing the completed authority snapshot of the same source (idempotent snapshot)` -- 0.0 s; `baseline_authoritative` still carries the 3061-crossing Phase-2 start (validated `manual_policy=frozen`, PASS) |
| 13 | 01:02:57 | `coldstart20/run_g4.py` (new, then **late `getattr` fix**) | G4 driver with `ARM_SPECS/ARM_ORDER` (`c0,a,b,c-frozen,c-free,d`), profile-first child launcher (`run_g4 _run --module`), `start`, `chain`, `validate`, `all`. **Late fix:** equal-counted flags are read with `getattr(args, 'counted'/'counted_d56_budget'/'counted_checks_guard', ...)` because only the counted arm subcommands define them | `c0/a/b` subcommands have no `--counted*` flags; direct `args.counted` raised `AttributeError` when the counted path was evaluated for them | 20H-only driver | `run_g4.py:876-887` (`_arm_inner_argv`), `:934-935`, `:1214-1218` (`getattr` use); all six arms completed (01:03:01-01:39:35) |
| 14 | 01:03:06 | `coldstart20/collect_final.py` (new) | stage-curve collector -> `12_reports/stage_curve_20h.{json,md}` | stage-vs-stage curve | new file; 20H tree only | `12_reports/stage_curve_20h.json` 23:59:39 (generated **before** stages 07/08 finished, so its `S07_G123`/`S08_G4` entries are `available:false`; `final_metrics.json` is the later, complete collector) |
| 15 | 01:20:18-01:25:10 | `09_multi_arc_ablation/cold_start_off/` (data; **late in-session execution**) | **multi-arc cold-start OFF arm** run through `coldstart20.run_initial --run-dir ...\09_multi_arc_ablation\cold_start_off` with `G4_ENABLE_MULTI_ARC=0`, then `coldstart20.run_validate --run-dir ...\cold_start_off` | Part A's strict common-start OFF start is infeasible (1 residual multi-arc route), so Part B is executed as a controlled cold-start ON/OFF pair from the identical 20H assignment (the ON arm **is** the unchanged stage-03 run, same `routes_l3d.json` SHA256 `2eb3a14c...`) | 20H tree only; no algorithm/rule change; only the policy environment variable differs | `cold_start_off/run.log` 01:20:18->01:24:40 (`done in 262.3s`), 1024/1024 routed, 0 failed, **14233** crossings; `cold_start_off/validation.json` 01:25:10 (`reheight21.validate21`, PASS, 0 violations); OFF ledger: 1960 arc primitives, 636 routes with >=2 planar arcs; `final_metrics.json` `multi_arc_ablation.cold_start_off` |
| 16 | 01:41:14-01:54:00 | `08_g4/08_progressive_chain/` (data; late execution) | `run_g4 chain --run-chain` built links 0/1 and ran link 2 (G4c_free, 700 s from the G4b 1371 checkpoint) -> **1309** crossings, validated 01:53:54; link 3 (02b, adopt the best validated G4c_free **arm** checkpoint, 0 s SPEC-B inheritance) and link 4 (G4d from link 3) remain **pending/blocked** (see `pipeline_map.md` §10.4). A manual G4d continuation from link 2 was launched at 01:54:25 and was still running when this log was finalised (02:04; interim 1283, no final validation yet) | the frozen fair_runner chain contract, applied to 20H | 20H tree only | `08_progressive_chain/run_g4_chain.log` 01:41:14->01:54:00; `chain_summary.json` `chain_best_crossings=1309`, `selected_path_total_delta=-86`; `02_link_G4c/validation/validation.json` 01:53:54 PASS; `03_link_G4d/run.log` 02:04 |

### 8.2 Late driver/artefact work not covered by the table

* the **final verification probes** were re-run read-only on 2026-11-18 02:00
  (`assign21` regression, path/fingerprint resolution, frozen-hash check,
  `patch_native3d_def.py --verify`, `patch_g4.py --check`); results in §8.3;
* the **progressive-chain link 3/4 handling and the final-freeze state** are
  recorded in `pipeline_map.md` §10.4-§10.5; they are artifact/scheduling
  drifts, not source changes;
* `run_native3d_phase2.py` (docstring and dry-run text), the
  `patch_native3d_def.py` docstring/patch label (`finalize_phase2.py: 20H
  independent validator is validate21`) and one report line in
  `native3d/finalize_phase2.py:480-481` still **name `validate21` for 20H**.
  Those are stale descriptive strings only: the executable path in
  `finalize_phase2.run_validator()` imports `validate_native3d`, and the
  `--verify` marker `finalize_20h_validator` passes. They are left unchanged
  (reporting hygiene item, not a behaviour change).

### 8.3 Current verification state (2026-11-18 02:00-02:30, read-only probes)

#### 8.3.1 Legacy 21-height regression evidence (unchanged by this rebuild)

| check | command / artifact | result |
|---|---|---|
| 21H assignment reproduces the archived assignment | in-memory `reheight21.assign21.build_assignment(force=True)` compared column-by-column (strings) with `outputs/manual_c4_new_connectivity/FANOUT_FIRST_21_HEIGHT_REBALANCED_1024/assignment_1024.csv`; then `build_audit` invariants | **0 row mismatches**, 1024/1024 rows, **34/34 invariants passed** |
| 21H path modules resolve to the frozen paths | plain process (no bootstrap, no `COLDSTART20_*`): `g4.paths`, `nonc4.paths`, `native3d.common`, `xyzrouter.paths` | `START_ROUTES_SHA256=711cf910...4077`, `START_CROSSINGS=1322`, `START_DIR=.../XYZ_JOINT_G123_1024/best_valid`, `G4_ROOT=.../experiments/xyz_joint_g4_1024`, `NONC4_ROOT=.../NON_C4_CROSSING_OPT_1024`, `NONC4_BASELINE=.../FANOUT_FIRST_21_HEIGHT_REBALANCED_1024`, `E5_DIR=.../E5_joint_repair_final`, `NATIVE3D_RUN=.../NATIVE_3D_CROSSING_OPT_1024`, `MOVABLE_PLANES=(6,7,20,1001,8,9,14,15,16,1002,17,18,19)` |
| frozen G4 start fingerprint reproduces the archived literal | `(Get-FileHash outputs\...\XYZ_JOINT_G123_1024\best_valid\routes_l3d.json -Algorithm SHA256).Hash` | `711CF910D5C75EA788BE877EF88B588FE3D59A90A2AE2D3636BB5B5896834077`, exactly the computed `START_ROUTES_SHA256`; computed crossings 1322 |
| Native-3D Phase-2 patch is behaviour-preserving on 21H and active on 20H | `patch_native3d_def.py --verify` (fresh subprocesses) | `21h: PASS (13 checks, 0 failed)`; `20h: PASS (24 checks, 0 failed)`; evidence file `00_audit/patch_native3d_def_verify.json` |
| G4 patch set is fully applied | `patch_g4.py --check` | `patches applied 0`, `already applied 19`, `files changed {}`, `all postconditions present` |
| 20H profile installs correctly | `-c "from ...coldstart20 import bootstrap as B; ..."` | `20 False 0.025 0.525` (20 planes, no plane 19, interfaces +0.025/+0.525) |

#### 8.3.2 20-height execution evidence (independent validator PASS at every accepted state)

| stage | layout | crossings (start -> end) | validator actually used | result |
|---|---|---|---|---|
| 03 cold start (fanout + D56 multi-arc + 3D) | `03_fanout_and_xy/run_initial_20h` | assignment -> **12338** | `reheight21.validate21` | PASS, 0 violations, 37.95 s |
| 04 annealing + E5 analog | `04_.../E5_joint_repair_final` (E3 seed 11) | 12338 -> **3275** | `reheight21.validate21` | PASS, 0 violations |
| 05 Native-3D Phase 1 | `05_native3d_abc/run_native3d_phase1` | 3275 -> **3103** | **`native3d.validate_native3d`** (mode `native3d`); planar `validate21` recorded as a non-blocking diagnostic: FAIL, 364 violations | PASS, 0 violations; `STAGE05_GATE.json` |
| 06 Native-3D Phase 2 | `06_native3d_def/.../best_valid` | 3103 -> **3061** | **`native3d.validate_native3d`** (`validation/final/validation.json`) | PASS, 0 violations |
| 07 G1 -> G2a -> G2b -> G3 | `07_g123/.../best_valid` | 3061 -> 1485 -> 1440 -> 1409 -> **1395** (G3_cold: 3061 -> 1646) | **`native3d.validate_native3d`**, `manual_policy=fully_optimizable`; preflight authority validated with `manual_policy=frozen` | PASS, 0 violations at every stage |
| 08 G4 arms (all from 1395) | per-arm `best_valid` | C0 1383 / G4a 1393 / G4b 1371 / G4c_frozen 1338 / **G4c_free 1322** / G4d 1337 | `xyzrouter.validate_xyz` -> **`native3d.validate_native3d`** | PASS, 0 violations, each arm re-validated in a fresh 20H process |
| 09 multi-arc ON/OFF | ON = stage-03 layout; OFF = `09.../cold_start_off` | ON **12338** vs OFF **14233** (equal cold assignment/budget) | `reheight21.validate21` (both) | PASS, 0 violations, both arms |
| 09 strict common-start conversion | `09.../common_start_off` | 1395 -> **4559** (+3164, conversion effect A) | `native3d.validate_native3d` PASS on the converted start; `validate21` diagnostic FAIL 577 (expected contract mismatch) | conversion infeasible: 212/213 converted, 1 residual route (456) -> OFF arm not run |
| 08 chain link 2 (B-class) | `08_g4/08_progressive_chain/02_link_G4c` | 1371 -> **1309** | `xyzrouter.validate_xyz` -> `native3d.validate_native3d` | PASS, 0 violations (finished 01:53:54, after the main report cutoff) |

**Stage-by-stage crossing curve (main A-class chain):**
`12338 -> 3275 -> 3103 -> 3061 -> 1395 -> 1322`
(03 -> 04 -> 05 -> 06 -> 07 -> 08 G4c-free; deltas -9063, -172, -42, -1666, -73).

The matching evidence files are `12_reports/final_metrics.{json,md}`,
`12_reports/stage_curve_20h.{json,md}` (pre-07/08 snapshot), the per-stage
`validation.json` files listed above, and `12_reports/EXPERIMENT_REPORT.md`.

### 8.4 Residual risks and reconciliation of the late change set

1. **Stale "validate21 for 20H" text** remains in three descriptive places
   (`patch_native3d_def.py` docstring + patch label,
   `run_native3d_phase2.py` docstring/dry-run output, and one report line in
   `native3d/finalize_phase2.py:480-481`). The executable validator selection
   and the `--verify` marker are correct (§8.1 item 10); this is a
   reporting-hygiene item only.
2. **`10_best_valid` is not frozen to the measured best layout** in the state
   delivered at 02:00: its root holds only `selection_scan.json` (01:41:07,
   winner `04_E5` because per-arm G4 `best_valid` dirs are mis-resolved by
   `select_final.py` -- `routes_l3d.json` and `crossing_stats.json` are not in
   the same directory and `routed/failed` are read only from
   `crossing_stats.json`), plus the stage-03 checkpoint subdir
   `00_initial_fanout_first_20h/` (frozen 22:49:11, 12338 crossings). There is
   **no `BEST_VALID.json`** at the root. The measured best 1322 layout lives in
   `08_g4/05_arm_G4c_free/best_valid/`; the arm's independent validation report
   is `08_g4/05_arm_G4c_free/validation/validation.json` (PASS, 0 violations).
   This is a deliverable-integrity gap recorded in `pipeline_map.md` §10.4.
3. **Chain link 3/4 are pending** and `08_progressive_chain/progressive_chain.md`
   / `chain_summary.json` labels still carry 21H prose values (1322 for the G3
   start, "1294"/"1189" link descriptions) while the table columns contain the
   real 20H values (1395 / 1371 / 1309). Link 2's 1309 is **better** than the
   A-class 1322 and was validated at 01:53:54, i.e. after `final_metrics.json`
   (01:41:33) and `EXPERIMENT_REPORT.md` (01:42:11) were written.
4. **`12_reports/stage05_native3d_phase1_summary.json` is correct in the final
   state (regenerated 23:39:45):** it records
   `native3d.validate_native3d`, `validation_pass=true`, 0 violations,
   3103 crossings / 2733 pairs. The caveat in
   `11_figures/test_on_e5/README.md` ("reports validation_pass=False / 364
   violations") was written at 23:31:57, before that regeneration, and is
   itself stale; the earlier version of the summary reflected the non-blocking
   planar `validate21` diagnostic. No artifact action is needed, but the figure
   README sentence should not be quoted as current state.
5. The **final figure set is a test rendering, not the final layout**: at
   23:31:33-23:31:57 `plot_final.py` was rendered on the E5 (3275) and stage-05
   (3103) layouts into `11_figures/test_on_e5/` and
   `11_figures/test_on_stage05/`; its figure 06 still shows Native-2 as 3087
   (the value at render time). No `11_figures/final/` exists, and
   `EXPERIMENT_REPORT.md` refers to one. Re-render from the 1322 layout after
   the freeze is fixed (§8.4 item 2).
6. **The `_source_backup` snapshot and the change set**: the 22:33:17 source zip
   remains the pre-rebuild provenance artifact. No rollback was exercised; no
   source file has been modified since 23:24:13 (`native3d/finalize_phase2.py`)
   and the `coldstart20` drivers listed above.
