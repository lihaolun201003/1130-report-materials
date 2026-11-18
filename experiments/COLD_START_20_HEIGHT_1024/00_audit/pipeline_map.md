# 20-height pipeline map — authoritative algorithm-execution chain

Scope: the full 1024-route 3D optical-waveguide optimisation chain, rebuilt for the
**20-height** physical model, in project root
`C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D`.

This document is the single map of **what runs, in which order, with which module,
command, functions, inputs, outputs, budget and degrees of freedom**. It was written
read-only (2026-11-17 ~22:40–23:00 local) from:

* the six audit reports in this directory (`reheight21.md`, `nonc4.md`,
  `native3d_abc.md`, `native3d_def.md`, `g123.md`, `g4.md`, `multiarc.md`);
* the real source under `four_side_1024/fanout1024/` (line numbers below are the
  **current** working-tree lines, verified by reading/grepping the files);
* the four applied patch scripts in this directory
  (`patch_profile_generic.py`, `patch_assign21_reporting.py`,
  `patch_assign21_literals.py`, `patch_paths_profile.py`);
* the new package `four_side_1024/fanout1024/coldstart20/`;
* the archived 21-height run logs/artifacts and the live 20-height run artifacts
  under `experiments/COLD_START_20_HEIGHT_1024/`.

No source file was modified to produce this map. The 20-height run is **live**:
stage 03 finished at 22:42:30 and stage 04 was running while this file was written
(see §2.4). Line numbers/sizes are as of the read time.

Legend for evidence tags: **[V]** = verified during this pass by reading the file /
hash / probe; **[A]** = taken from an audit report (file:line evidence is inside the
report); **[R]** = measured wall-clock from an archived log.

---

## 0. Directory convention and the two code states

The deliverable tree `experiments/COLD_START_20_HEIGHT_1024/` is pre-scaffolded
(created 22:28:20): `01_height_config`, `02_annealing`, `03_fanout_and_xy`,
`04_initial_3d_and_e5_repair`, `05_native3d_abc`, `06_native3d_def`, `07_g123`,
`08_g4`, `09_multi_arc_ablation`, `10_best_valid`, `11_figures`, `12_reports`
[V]. All writable run directories of the frozen pipeline are re-pointed into this
tree by `coldstart20/paths20.py` (ENV mapping, see §1.2); the historical 21-height
`outputs/manual_c4_new_connectivity/*` trees stay **read-only**.

Two code states matter and must not be mixed:

| state | what it is | how 20H uses it |
|---|---|---|
| **frozen 21H chain** | `reheight21/{model,assign21,run21,validate21,plots21,report21,archive21}.py`, `nonc4/`, `native3d/`, `xyzrouter/`, `xyzrouter/g4/` — all originally written for 21 heights | driven **unchanged**; the height table is replaced at process start by `coldstart20.bootstrap` |
| **20H profile** | `coldstart20/model20.py` (authoritative 20-height model) + `bootstrap.py` (import-time installer) + `paths20.py`/`profile_env.py` (path seam) + per-stage `run_*` drivers | installed first in every 20H process; emits only below `experiments/COLD_START_20_HEIGHT_1024/` |

The whole 20H rebuild is therefore an **input/configuration swap**, not an algorithm
rewrite: no search operator, threshold or acceptance rule changed (see §6).

---

## 1. Top-level execution chain (real stage order and entry points)

```
                               1024 fixed connections  (common.routes(); never regenerated)
                                            |
                                            v
 (00_audit)   six read-only audit reports + four applied patch scripts        [this dir]
                                            |
 (01_height_config)  model20.py authoritative 20-height table; bootstrap installs it
                                            |
 (02_annealing)      scaffold only — NOT used by the executed chain (the C4-free
                     simulated annealing lives inside stage 04, see note in §2.4)
                                            |
                                            v
=== stage 03: fanout-first cold-start baseline ==========================================
 driver:  four_side_1024/fanout1024/coldstart20/run_initial.py
 command: python -m four_side_1024.fanout1024.coldstart20.run_initial --stages ABCDEF --max-iters 3
 internals: reheight21.assign21.main()  ->  reheight21.run21.run_stages('ABCDEF')
 stages: A assignment | B fanout/R15 transitions | C per-height strict-D56 multi-arc
         2D routing | D 3D assembly + 0.05 mm world check | E joint repair loop |
         F final experiment-D summary
 output:  experiments/COLD_START_20_HEIGHT_1024/03_fanout_and_xy/run_initial_20h/
          -> assignment_1024.csv, layer_planes/stack/rules, fanout_selected.json,
             routes_l3d.json, routes/world stats  (the 20H "pre-native baseline")
          -> DONE 2026-11-17 22:42:30, 1024/1024, 0 failed, 1848 transitions,
             100 direct, min true-3D clearance 0.086498778 mm  [V]
                                            |
                                            v
=== stage 04: C4-free annealing + joint repair (21H name: NON_C4_CROSSING_OPT_1024) ====
 driver:  coldstart20/run_nonc4.py   (LIVE at 22:47)
 command: python -m four_side_1024.fanout1024.coldstart20.run_nonc4 {e0|screen|e1|e3 --seed N|select|summary|all}
 internals: nonc4.assign_opt (SA on chord-crossing graph) -> nonc4.assign_nc/run_nc
            (fanout -> per-height 2D -> 3D assembly -> world check -> repair)
 output:  04_initial_3d_and_e5_repair/nonc4_programme/{E0_*,E1_*,E3_*,E5_joint_repair_final/}
          the accepted legal 20H solution consumed as "E5" by stages 05/06
                                            |
                                            v
=== stage 05: Native-3D Phase 1 (A/B/C) ================================================
 modules: native3d/run_a.py, native3d/run_b.py, native3d/global_optimizer.py
 commands (21H form): run_a --top-routes 12 ; run_b --sample 30 --batch 80 ;
                      global_optimizer ; validate_native3d --run-dir <dir>
 output: 05_native3d_abc/run_native3d_phase1/{experiment_A,experiment_B,experiment_C}/
         A/B/C are INDEPENDENT branches from the accepted stage-04 solution (not a chain)
                                            |
                                            v
=== stage 06: Native-3D Phase 2 (D/E/F) ===============================================
 modules: native3d/crossing_intervals.py, blocker_analysis.py, arc_crossing_analysis.py,
          run_d.py, run_e.py, run_f.py, run_f_plus.py, run_f_nearmiss.py, finalize_phase2.py
 commands (21H form): crossing_intervals -> blocker_analysis -> arc_crossing_analysis ->
                      run_d --screen 80 --repairs 30 -> run_e --routes 16 ->
                      run_f --sweeps 2 -> run_f_plus (x2) -> run_f_nearmiss (x2) ->
                      finalize_phase2
 output: 06_native3d_def/run_native3d_phase2/{experiment_D,experiment_E,experiment_F,best_valid,analysis}/
         (21H: 2440 -> 2409 crossings, all legal; 20H baseline crossings are dynamic)
                                            |
                                            v
=== stage 07: G1 -> G2a -> G2b -> G3 (XYZ joint router) ================================
 modules: xyzrouter/{run_g1,run_g2,run_g3,run_warmstart_chain,run_reports}.py
 commands: run_g1 --rounds 2 --round-seconds 1200 --top 656
           run_warmstart_chain     (G2a --rounds 2 --round-seconds 300;
                                    G2b --rounds 1 --round-seconds 240;
                                    G3  --rounds 1 --round-seconds 500)
           [optional] run_g3 --start-from baseline (G3_cold, 1200 s)
           [optional] run_router_validation (P0/P1/P2)
           run_reports  -> 07_g123/run_xyz_joint_1024_20h/best_valid
 output: G1_manual_frozen, G2a_manual_group_reheight, G2b_manual_route_reheight,
         G3_manual_full_xyz, best_valid, reports
                                            |
                                            v
=== stage 08: G4 global ALNS chain ====================================================
 modules: xyzrouter/g4/{run_g4_engine,run_g4a,run_g4b,c0_continue,fair_runner}.py
 commands: run_g4_engine --arm {C0|G4a|G4b|G4c_frozen|G4c_free|G4d} --seconds S
             --seed 20261104 --start-dir <G3 best_valid> --out-dir 08_g4/<arm>
           validate_xyz --run-dir <arm>/best_valid --manual-policy fully_optimizable
           fair_runner --chain --run-chain ...   (progressive chain links)
 output: 08_g4/{01_arm_C0,02_arm_G4a,03_arm_G4b,04_arm_G4c_frozen,05_arm_G4c_free,
         06_arm_G4d,07_best_valid,08_progressive_chain}
                                            |
                                            v
=== stage 09: multi-arc ON/OFF ablation ==============================================
 modules/tools: layer2d.MULTI_ARC_POLICY (switch) + g4 engines + ablation tools
 commands (FINAL 21H design): tools/convert_multi_arc.py (Stage-0 OFF conversion);
           run_arm.ps1 -Arm on|off -Seed S -CountedD56 24000 -CountedChecks 9000
           (internally run_g4_engine --arm G4c_free, then validate_xyz);
           run_all_analysis.ps1
 output: 09_multi_arc_ablation/{common_start_off,runs/{on,off}/...,tables,figures,validation}
                                            |
                                            v
 (10_best_valid) frozen best legal solution -> (11_figures) plots -> (12_reports) report
```

Which of these are **implemented today** for 20H: stage 03 ✔ (`run_initial.py`),
stage 04 ✔ (`run_nonc4.py`, running). At the read time of this map (22:47) stages
05–09 had **no 20H driver yet**; between 22:48 and 22:55 the concurrent rebuild
workstream added `coldstart20/run_native3d_phase1.py` (22:48:24),
`coldstart20/run_g123.py` (22:54:27), `coldstart20/convert_multiarc20.py`
(22:54:06), `coldstart20/plot_layers20.py` (22:51:57) and `00_audit/patch_g123.py`
(22:51:38). Those files appeared **after** this map's source verification pass and
are not described stage-by-stage here; verify them against §3.3–§3.7 before use.
Still missing at read time: a Native-3D Phase-2 driver (`run_native3d_def.py`), a G4
driver (`run_g4.py`), the strict multi-arc ON/OFF `run_arm` port, and the
`tests_model20`/`drivers` modules announced by `coldstart20/__init__.py:18-21`.

> **Update 2026-11-18 02:30:** this "implemented today" paragraph is superseded
> by the final section *"Executed 20-height chain: measured results and drifts"*
> at the end of this file. All stages 03–09 now have bootstrap-first 20H drivers
> and were executed; the Phase-2 driver is `run_native3d_phase2.py` (not
> `run_native3d_def.py`), and multi-arc uses `run_multiarc.py` +
> `convert_multiarc20.py`.

---

## 2. The profile seam (common to every 20H stage)

### 2.1 `coldstart20.model20` — authoritative 20-height model

`four_side_1024/fanout1024/coldstart20/model20.py` (892 lines) exposes exactly the
public API of `reheight21.model`:

* identity: `PROFILE='20_height_raised'`, `EXPERIMENT_NAME='COLD_START_20_HEIGHT_1024'`,
  `MODEL_NAME='coldstart20.model20'` (`:88-92`);
* 20 routing heights = 18 body planes `{2..18, 20}` at −0.325…+0.625 mm step 0.05,
  and the two routable interface planes 1001 (z=+0.025) / 1002 (z=+0.525);
  plane identity **19 is deleted** (`:138-166`); all surviving heights are the 21H
  heights **+0.025 mm**;
* unchanged thresholds: glass 1.000 mm / z ∈ [−0.35, +0.65] mm, 0.05 mm minimum pitch,
  0.05 mm true-3D clearance, R15 = 15.0 mm (`:128-136`);
* manual groups: **same 8 groups, same plane ids, same counts** 64/64/64/64 +
  16/16/40/40 = 368; only z shifts +0.025 (`:234-251`, `:318-322`);
* allocations: `Z1_OTHER_PLAN` unchanged `((6,13),(7,13),(20,13),(1001,13),(8,12))`
  (`:270`); `Z2_OTHER_PLAN` replaces the 21H 1:1 old-layer map with a whole-C4-orbit
  plan over the **7** surviving Z2-other planes
  `((9,14),(14,14),(15,14),(16,14),(17,16),(18,16),(1002,12))` = 100 orbits /
  400 routes (`:280-281`); `Z2_OTHER_OLD_TO_NEW = None` (`:286`);
  `allocate_z2_other()` implements it (`:540-577`);
* contract: `CONTRACT_PLANE_COUNTS` (`:306-311`, sums to 1024),
  `CONTRACT_Z2_OTHER_COUNTS` (`:312-314`), direct 100 = 52+48, transitions 924 →
  1848 endpoints (`:315-317`), manual 368 (`:318-322`);
* validator contract tables `SPEC_*` (`:328-346`) at 20/18/2 planes;
* stack: `layer_stack()` builds an `l3d` stack with interface rows +0.025/+0.525 and
  routing ids `{2..18,20}` (`:581-600`);
* payloads: `layer_planes_payload()` (`:642-703`), `stack_payload()` (`:706-755`),
  `process_rules_payload()` (`:762-819`) with schema names `reheight20_*`
  (`:296-301`).

### 2.2 `coldstart20.bootstrap` — import-time installer (mandatory first import)

`coldstart20/bootstrap.py`:

* registers `model20` **under the module key** `four_side_1024.fanout1024.reheight21.model`
  and as the `model` attribute of the `reheight21` package (`:66-72`). Every pipeline
  module does `from ..reheight21 import model as M` at import time, so this single
  swap re-points the whole chain;
* re-points the legacy interface constants in place:
  `common.INTERFACE_Z`, `common.Z1_INTERFACE_MM`, `common.Z2_INTERFACE_MM`,
  `l3d.layers.INTERFACE_ROWS` (`:78-93`), plus `fslw.config.PLANE_Z_MM`
  **without changing the 0.5 mm port row pitch** (asserts it, `:94-112`);
* drops the cached `l3d` stack and re-points the writable `model` paths via
  `bind_run_dir()` (`:118-136`);
* guard `assert_20_height_profile()` fails loudly if a pipeline module was imported
  before the bootstrap, if plane 19 still exists, or if the interface constants were
  not re-pointed (`:146-163`); `install()` runs on import (`:187`).

**Import-order contract:** every 20H driver must do
`from four_side_1024.fanout1024.coldstart20 import bootstrap` **before** importing
`reheight21`, `nonc4`, `native3d`, `l3d` or `xyzrouter` modules. All existing 20H
drivers satisfy this (`run_initial.py:35`, `run_validate.py:22`, `run_nonc4.py:53`).
The frozen `python -m ...native3d.run_a` / `...xyzrouter.run_g1` forms must **not**
be used for 20H (the `-m` import binds the 21H model first).

### 2.3 `coldstart20.paths20` + `profile_env` — run-directory seam

`paths20.py` resolves every writable directory (`:14-48`) and publishes them as
`COLDSTART20_*` environment variables (`:51-61`). The frozen path modules read them
through `profile_env.path_env(name, frozen_default)`; with no variable set the
historical 21H default is returned, so a plain process is bit-identical to the frozen
chain.

| path | 20H value (paths20.py:42-48) | frozen path variable |
|---|---|---|
| stage-03 run | `03_fanout_and_xy/run_initial_20h` | `COLDSTART20_INIT_RUN`, `COLDSTART20_FANOUT_BASELINE_DIR` |
| stage-04 root | `04_initial_3d_and_e5_repair/nonc4_programme` | `COLDSTART20_NONC4_ROOT` |
| accepted legal solution ("E5") | `<nonc4_root>/E5_joint_repair_final` | `COLDSTART20_E5_DIR` |
| Native-3D Phase 1 | `05_native3d_abc/run_native3d_phase1` | `COLDSTART20_NATIVE3D_ABC_RUN` |
| Native-3D Phase 2 | `06_native3d_def/run_native3d_phase2` | `COLDSTART20_NATIVE3D_DEF_RUN` |
| G1/G2/G3 | `07_g123/run_xyz_joint_1024_20h` | `COLDSTART20_XYZ_RUN` |
| G4 archive root | `08_g4` | `COLDSTART20_G4_ROOT` |
| multi-arc ablation | `09_multi_arc_ablation` | `COLDSTART20_MULTIARC_ROOT` |

`profile_env.py` also defines `is_20h()` (reads `COLDSTART20_PROFILE ==
'20_height_raised'`, `:36-38`) and `int_env()` for numeric overrides
(e.g. `COLDSTART20_START_CROSSINGS`, `COLDSTART20_PHASE1_CROSSINGS`).

### 2.4 Live status at write time

* stage 03 completed **2026-11-17 22:38:01 → 22:42:30 = 269.9 s** (`run_initial_20h/run.log`
  last line; banner line 1 = `assign21: === COLD_START_20_HEIGHT_1024 ...`);
* independent validation of the stage-03 output completed at 22:45:17
  (`validation.json`, `runtime_seconds=37.95`): 1024/1024 routed, 0 failed,
  100 direct (52 z1 + 48 z2), 1848 transitions, 20 planes audited,
  same-plane crossings **12338 / 10133 pairs**, 0 crossing violations,
  min true-3D clearance **0.086498778 mm**, `geometry_pass=true`,
  `contract_pass=true`, `validation_pass=true`, `exit_code=0`;
  `validator_consistency_tests.json` `all_passed=true` (including 50 µm accepted /
  49 µm rejected for plane gap and D56) [V];
* stage 04 began at 22:46:42 (`04_initial_3d_and_e5_repair/nonc4_programme/_logs/run.log`:
  `[20h-nonc4] [screen] measured SA cost curves ...`), i.e. it is running while this
  document is written. No 20H result exists yet for stages 05–09.

---

## 3. Stage-by-stage map

Notation: each stage lists **module(s) → entry command (as executed/planned) →
implementing functions with `file:line` → inputs → outputs + JSON schema → measured
runtime (21H evidence, `[R]`) → frozen vs movable planes/routes**.

### 3.1 Stage 03 — 20H fanout-first cold-start baseline (A–F)

**Modules:** `coldstart20/run_initial.py` (driver) driving the frozen
`reheight21/assign21.py` + `reheight21/run21.py`; shared engines
`fanout.py`, `layer2d.py`, `assemble.py`, `l3d/world.py`.

**Entry command** (as used; `run.log` line 1–2 identifiers match the banner):
```bat
.venv\Scripts\python.exe -m four_side_1024.fanout1024.coldstart20.run_initial ^
  --stages ABCDEF --max-iters 3
```
Driver: `main()` `run_initial.py:49-73` — `B.install()`/`bind_run_dir` (`:51-56`),
`assign21.main()` (`:63`), `run21.make_logger(tag='20h')` (`:67`),
`run21.run_stages('ABCDEF', max_iters=3)` (`:71`).
CLI args: `--stages` (default `ABCDEF`), `--max-iters` (3), `--run-dir`,
`--skip-assign` (`:39-46`).

**Stage A — assignment** (`assign21.py`):
`main()` `:1482`, `build_assignment()` `:198`, `write_all()` `:1386`,
`_invariants()` `:355`, `_check_contract()` `:658`, `build_audit()` `:687`,
`build_diff()` `:818`, `_z2_other_allocation()` `:184` → profile
`M.allocate_z2_other` (`model20.py:540`), `EXPECTED_* = M.CONTRACT_*` (`:74-86`).
Inputs: frozen 18L baseline `outputs/manual_c4_new_connectivity/FANOUT_FIRST_Z2_MANUAL_VERIFIED_1024/assignment_1024.csv`
(read-only; sha256 recorded); `common.routes()` / `rotation_groups()`.
Outputs (all under stage-03 run dir): `assignment_1024.csv` (27 columns,
`assign21.py:59`), `assignment_audit.json` (`schema=reheight20_assignment_audit_v1`),
`assignment_diff_vs_baseline.{json,md}`, `layer_planes.json`
(`reheight20_layer_planes_v1`), `physical_layer_stack.json`
(`reheight20_layer_stack_v1`), `process_rules.json`
(`reheight20_process_rules_v1`), `experiment_A/{summary,audit,layer_audit.csv,
validation_status}.json` [V: schemas read from the 20H artifacts].
20H result [V]: 1024 rows, 20 planes / 20 distinct heights, z1 512 / z2 512,
direct 100, transitions 924 (1848 endpoints), manual 368, min pitch 0.050 mm,
assignment audit `all_invariants_passed=true`.

**Stage B — fanout / R15 transitions** (`run21.py`):
`stage_b()` `:328` → `fanout.plan_fanout(rows, stack=M.layer_stack())` (`:334`),
independent `validate_fanout_selected()` `:195`, `_fanout_artifacts()` `:246`.
Outputs: `fanout_selected.json` (`schema=reheight21_fanout_selected_v1` in the 20H
run — profile schema string not yet updated), `fanout_validation.json`,
`layerwise_endpoints/endpoints.json`, `experiment_B/{summary,failed_routes}.json`,
`checkpoints/stage_B_fanout.json`; 20H: 1024 routes / 2048 endpoints OK,
failures 0, 1848 transitions + 200 direct endpoints (log [V]).
Runtime 20H: **40.3 s** (`run.log` `[B] seconds=40.3`).

**Stage C — per-height strict-D56 multi-arc 2D routing**:
`_route_all_layers()` `:419` → `layer2d.route_all_layers()` (`layer2d.py:1677`);
`_interface_lead_blockers()` `:352`, `_initial_routes_for()` `:409`,
`_experiment_c_summary()` `:727`. Inputs are the in-memory fanout selection.
Outputs: `experiment_C/summary.json`, `checkpoints/stage_C_2d.json`;
20H: all 20 planes routed 1024/1024, 12.4 s [V].
**This is the only stage whose output the multi-arc ON/OFF switch changes**
(§4.3): the planar candidate generator is `layer2d._LayerRouter._iter_candidates`
(`layer2d.py:1299`).

**Stage D/E/F — 3D assembly, world check, joint repair, finalisation**:
`_assemble_all()` `:508` (via `assemble.assemble_route`), `_world_check()` `:551`
(`assemble.validate_routes_independent(routes, stack=M.layer_stack())` = strict
0.05 mm true-3D world), `_local_insert()` `:939`, `_layer_resolve()` `:589`,
`stage_e()` `:1061` (loop `_LAYER_BUDGETS` = 600/1200/1800/2400 s at `:33`,
`--max-iters` outer iterations), `_write_routes_payload()` `:781`,
`_write_final_stats()` `:824`, `_write_experiment_e()` `:876`,
`stage_finalize()` `:1163`; dispatcher `run_stages()` `:1232`, `_STAGES='ABCDE'`
`:1229` (+F explicitly).
Outputs: `routes_l3d.json` (`schema=reheight21_routes_l3d_v1`), `failed_routes.json`,
`final_stats.json`, `layerwise_routes/routes.json`, `experiment_D`, `experiment_E`,
`checkpoints/experiment_E_best.json`, `crossing_stats.json` (written by the
validator/wrapper), `validation.json`, `validator_consistency_tests.json`, plots/report.
20H result [V]: iteration 2 `assembled=1024 world_valid=1024 violations=0
assembly_failures=0`; final `routed=1024/1024 failed=0 direct=100 transitions=1848`;
`final_stats.json` `total_length_mm=157368.795`, `min_3d_clearance_mm=0.05`,
`max_route_length_mm=282.322`, 20 per-plane counts equal to
`CONTRACT_PLANE_COUNTS` [V]. Total 269.9 s.

**Frozen vs movable at stage 03:** body heights are assigned by stage A from the
contract; all 1024 routes get fresh XY/fanout/S-transitions; planar multi-arc
candidates are enabled by default; the 368 manual-U routes are here *generated* (they
are not inherited from the 21H archive) and fixed to planes 2,3,4,5,10,11,12,13.

**Independent validation of stage 03** (packaged wrapper):
`coldstart20/run_validate.py` — `main()` `:35-69`, calls
`validate21.validate(run_dir, out_dir, skip_min_clearance, skip_crossings)` (`:43-46`)
and writes `coldstart20_validation_summary.json` (`:64`). The frozen validator
`validate21.validate()` `:2394` / `main()` `:3008` is used **in full** (all geometry /
D56 / R15 / glass / port / contract checks), with only the configuration tables from
`model20` (§5).

### 3.2 Stage 04 — C4-free annealing + joint repair (20H "E5" legal solution)

**Module:** `coldstart20/run_nonc4.py` (435 lines) driving the frozen
`nonc4/` package: `assign_opt.py` (simulated annealing on the chord-crossing graph),
`assign_nc.py` (per-route C4-free assignment), `run_nc.py` (fanout→2D→3D→repair),
`validate_nc.py` (frozen-validator wrapper), `data.py`/`paths.py` (I/O).

**Entry command** (`run_nonc4.py:40-43`, CLI `:379-396`, `main()` `:399-431`):
```bat
.venv\Scripts\python.exe -m four_side_1024.fanout1024.coldstart20.run_nonc4 all
  # or individual steps:
  #   e0 | screen --seed 11 --time-budget 60 | e1 | e3 --seed 11 --order route_id
  #   select | summary
```
`prepare_profile()` `:104-115` installs bootstrap, binds
`nonc4.paths.EXPERIMENT_ROOT = paths20.NONC4_ROOT` and
`nonc4.paths.BASELINE_21H_DIR = paths20.INIT_RUN` (so the 368 manual-U geometry is
regenerated from the **20H** stage-03 run, never copied from the 21H archive).

**Sub-experiments (functions):**
| step | function | what it does | outputs |
|---|---|---|---|
| `e0` | `experiment_e0()` `:121-146` | reproduce the 20H fanout-first layout through the C4-free driver (harness sanity gate; plan = the stage-03 assignment `route_id → target_layer`) | `E0_baseline_reproduction/`, `E0_summary.json` (`schema=coldstart20_nonc4_e0_v1`) |
| `screen` | `screen()` `:152-193` | SA cost curves per family (`assign_opt.measure_cost_curves`) + allocation integer program (`assign_opt.optimise_allocation`) → the family→plane-count plan | `screening_annealing.json` (`coldstart20_nonc4_screening_v1`: curves, optimal, allocation, predicted crossings) |
| `e1` | `experiment_family_pure()` `:199-221` | deterministic family-pure allocation (`assign_nc.default_allocation()`, 20H branch `assign_nc.py:72-86`) | `E1_family_pure/`, `E1_summary.json` |
| `e3` | `experiment_e3()` `:224-266` | from-scratch SA partition (`assign_opt.plan_structured`) then full A–E (`run_nc.run_standard(budgets=(600,1200), max_iters=2)`) | `E3_family_pure_sa_seed<N>/`, `E3_summary_seed<N>.json`, `assignment_plan.json` |
| `select` | `select_best()` `:280-354` | re-validate every candidate with `validate_nc.validate_experiment`; accept the best fully legal one and materialise `E5_joint_repair_final/` | `selection.json` (`coldstart20_nonc4_selection_v1`, accepted SHA/crossings), `E5_joint_repair_final/ACCEPTED.json` (`coldstart20_accepted_solution_v1`) + `.sha256.json` per file + `SHA256_INDEX.json` |
| `summary` | `stage_summary()` `:360-373` | compact campaign table | `12_reports/stage04_nonc4_summary.json` |

Core nonc4 functions (frozen, profile-aware): `assign_opt.partition_min_intra()`
`:110` (SA, seed default 11, restarts 10, 40000 iters, 60 s/120 s wall budgets),
`optimise_allocation()` `:222`, `plan_structured()` `:256`;
`assign_nc.default_allocation()` `:63`, `plan_with_manual()` `:140`
(**manual freeze point**), `build_rows()` `:176`, `build_audit()` `:226`;
`run_nc.stage_b()` `:104`, `route_layers()` `:179`, `assemble_all()` `:210`,
`run_pipeline()` `:477`, `repair_failed()` `:580`, `finalize_experiment()` `:857`;
`validate_nc.validate_experiment()` `:184`.

**Runtime** (21H campaign [R]; 20H only the screen has run so far): E0 107 s,
E2 87 s, S_A/S_V3 screen 39–45 s each, E3 158 s, E5 138 s, validate 20–22 s.
20H live: cost-curve screening at 22:46:42–22:47:30 (per-family 60 s/15 s SA
budgets), consistent with the 21H curve values (`Z1V/Z1H 1568/392/134/52`,
`Z2 1009/246/80/30`) which are port-geometry invariants.

**Frozen vs movable at stage 04:** all non-manual routes may be **re-assigned to any
plane of their own family's allowed set** and re-routed (fanout + 2D + 3D); whole C4
orbit binding is removed (C4 orbits may split); the **368 manual-U routes stay on
their 8 fixed planes and are never re-routed** — their transitions/bodies are imported
from the stage-03 run as fixed world citizens / D56 blockers and re-checked
bit-identically (`manual_frozen_check`). No search inside stage 04 moves the manual
geometry; only its z values are the new 20H values because it was regenerated in
stage 03.

### 3.3 Stage 05 — Native-3D Phase 1 (experiments A / B / C)

**Modules:** `native3d/run_a.py`, `native3d/run_b.py`, `native3d/global_optimizer.py`,
plus `validate_native3d.py` (independent validator) and `visualize.py`.

**Entry commands (21H form; 20H must use a bootstrap-first driver, see §7):**
```bat
.venv\Scripts\python.exe -m four_side_1024.fanout1024.native3d.run_a --top-routes 12
.venv\Scripts\python.exe -m four_side_1024.fanout1024.native3d.run_b --sample 30 --batch 80
.venv\Scripts\python.exe -m four_side_1024.fanout1024.native3d.global_optimizer
.venv\Scripts\python.exe -m four_side_1024.fanout1024.native3d.validate_native3d --run-dir <dir>
```
CLIs: `run_a.py:364-370` (`--top-routes` 20, `--time-budget` 420, `--max-apply` 1,
`--skip-a1`); `run_b.py:81-86` (`--sample` 40, `--batch` 120, `--time-budget` 200,
`--max-excursions` 3); `global_optimizer.py:286-291` (`--strategy B4_multi_excursion`,
`--max-excursions` 2, `--time-budget` 420 s per stage);
`validate_native3d.py:2801-2824`.

**Semantics:** each branch starts from the accepted stage-04 solution
(`N.load_routes()` reads `N.E5_DIR`), inserts R15 mid-body excursions that move a
short sub-path of one route from its body height to another routing height, recounts
crossings exactly, and accepts only a strict decrease with a legal fresh 3D world.
A/B/C are **independent branches, not a chain** (A = 1 route, B = batch strategies,
C = greedy 3-stage sweep). C is the one that produces the Phase-1 accepted layout.
**Frozen:** the 368 manual-U routes are not in the candidate set (the search operates
on the 656 non-manual routes; the manual set is loaded from the accepted layout's
assignment and their records are fixed world citizens). Mid-body excursions of
non-manual routes are the only degree of freedom; fanout is untouched.

**Outputs:** `experiment_A/{a0_geometry_tests,a1_scan,a2_single_route_result,routes_l3d,summary}`,
`experiment_B/{strategy_*,strategy_comparison,batch_result,candidates,failed_attempts,
excursion_statistics,routes_l3d,crossing_stats,summary}`,
`experiment_C/{routes_l3d,crossing_stats,transition_stats,failed_attempts,
optimization_history.csv,summary,checkpoints}`. Schemas: `native3d_routes_l3d_v1`
(for A/B/C), `native3d_experiment_a0_v1`, `..._a1_scan_v1`, `..._a2_v1`,
`native3d_transition_stats_v1`; the accepted C layout is the Phase-2 input.
`validate_native3d` writes `validation.json` against a `--baseline-dir`; the manual-U
freeze is a contract check (`check_manual_frozen`) — the baseline must be the 20H
stage-04 layout, otherwise all 368 are flagged.

**Runtime (21H [R]):** A ≈22 s (12 routes/142 attempts), B ≈82 s (accepted
invocation), C ≈449 s (7.5 min), validator 18.5–22.3 s per run. Budget flags are
wall-clock caps per stage.

### 3.4 Stage 06 — Native-3D Phase 2 (D / E / F)

**Modules:** `native3d/crossing_intervals.py` (candidate pool),
`blocker_analysis.py` (D0 independent analysis), `arc_crossing_analysis.py` (E0
independent analysis), `run_d.py` / `run_e.py` / `run_f.py` / `run_f_plus.py` /
`run_f_nearmiss.py` (search), `joint_reroute.py` + `excursion2.py` (joint transaction
engine), `phase2.py` (paths/baseline/bookkeeping), `finalize_phase2.py` (deliverable).

**Entry commands (21H form):**
```bat
python -m ...native3d.crossing_intervals --baseline-dir <stage04 E5> --out-dir <05 phase1 dir>
python -m ...native3d.blocker_analysis --baseline-dir <E5> --native-dir <05 phase1>
python -m ...native3d.arc_crossing_analysis --baseline <05 phase1>
python -m ...native3d.run_d --screen 80 --repairs 30
python -m ...native3d.run_e --routes 16
python -m ...native3d.run_f --sweeps 2 --time-budget 560
python -m ...native3d.run_f_plus
python -m ...native3d.run_f_nearmiss
python -m ...native3d.finalize_phase2
```
(argparse defaults: `run_d.py:81-88`, `run_e.py:217-223`, `run_f.py:218-223`,
`run_f_plus.py:23-27`, `run_f_nearmiss.py:64-69`; `crossing_intervals.py:2353-2382`;
`finalize_phase2.py:608`.)

**Semantics:** a post-processing optimiser on the accepted Phase-1 layout. It moves
short sub-paths between routing heights through two exact R15 S-curves
(plain / arc-span / staircase), optionally gives each 3D-blocking route its own
make-way excursion (joint transaction), and accepts a change only if a **fresh exact
3D world check** passes **and** the exact global strict-D56 crossing count strictly
decreases; otherwise the transaction is rolled back (`joint_reroute.joint_try`,
`joint_reroute.py:207-309`; candidate gate `guard.candidate_guard`,
`guard.py:115-134`). `phase2._inherited_crossings()` (`phase2.py:31-57`) reads the
inherited baseline count from the accepted Phase-1 `crossing_stats.json`
(`COLDSTART20_PHASE1_CROSSINGS` overrides); for 20H it raises instead of using the
historical `2440` if that file is missing.

**Frozen vs movable:** the 368 manual-U routes stay frozen (entry/exit geometry,
heights, bodies) throughout Phase 2; only non-manual routes and their mid-body
excursions are movable. Fanout/landings are not re-planned.

**Outputs:** `experiment_D/` (`routes_l3d.json` schema
`native3d_phase2_routes_l3d_v1`, `crossing_stats.json`, `blocker_map.json`,
`joint_search_history.csv`, `validation.json`, `summary.json`,
`native3d_phase2_experiment_d_v1`); `experiment_E/` (`arc_crossing_analysis.json`,
`arc_rebuild_results.json`, routes/stats/validation/summary);
`experiment_F/` (`strategy_stats.json`, `extra_sweep.json`, `near_miss_results.json`,
`validation_extra.json`, `validation_near_miss.json`, routes/stats/summary);
`best_valid/{routes_l3d.json,crossing_stats.json,validation.json,config.json,model files}`;
`analysis/{blocker_analysis.json,arc_crossing_analysis.json,crossing_intervals.json}`;
root deliverables + `MANIFEST.json` + `validation/final/`.
Known defects to preserve/fix: `save_best_valid` does not write
`transition_stats.json` (stale Phase-1 copy); `finalize_phase2` has a
`arcs['classes']` key bug; `near_miss_results.json` has on-disk keys the current
source does not write (artifact/script drift) — see §7.

**Runtime (21H [R]):** D 257.7 s (D0 screen ≈185 s), E ≈29 s per run, F 133.1 s,
F+ 132 s / 215 s, near-miss ≈325 s / ≈230 s, D0 blocker analysis 145.1 s,
finalize ≈30–90 s; whole session ≈39 min.

### 3.5 Stage 07 — G1 → G2a → G2b → G3 (XYZ joint router)

**Modules:** `xyzrouter/optimizer.py` (engine wrapper), `local_reroute.py` (production
candidate engine), `world_adapter.py` (incremental exact world), `route_builder.py`,
`manual_reheight.py` (G2 Z-only), `run_g1.py`, `run_g2.py`, `run_g3.py`,
`run_warmstart_chain.py`, `run_reports.py`, `validate_xyz.py`,
`run_router_validation.py` (P0/P1/P2 functional validation), `paths.py`.

**Entry commands (21H, from archive evidence):**
```powershell
python -m four_side_1024.fanout1024.xyzrouter.run_g1 --rounds 2 --round-seconds 1200 --top 656
python -m four_side_1024.fanout1024.xyzrouter.run_warmstart_chain
python -m four_side_1024.fanout1024.xyzrouter.run_g3 --start-from baseline `
    --out .../G3_cold --rounds 1 --round-seconds 1200          # optional cold control
python -m four_side_1024.fanout1024.xyzrouter.run_router_validation   # optional P0/P1/P2
python -m four_side_1024.fanout1024.xyzrouter.run_reports             # best_valid + reports
```

**Semantics / functions:** one production engine: greedy per-route
`local_reroute.reroute_one()` `:318` (propose `:200`, `xy_candidates` `:112`,
target options `:53-87`, lead ladder `:90-106`, acceptance `:318-330`) on top of
`world_adapter.RouteWorld`; driver loop `optimizer.Optimizer.run_round()`
`optimizer.py:67-139`, `Optimizer.run()` `:141-157`; per-stage wrappers
`run_g1.main()` `:79-132`, `run_g2.main()` `:201-263` (`--phase a|b`, `:175-199`),
`run_g3.main()` `:40-79`, chain `run_warmstart_chain.main()` `:51-127`
(G2a `--rounds 2 --round-seconds 300`, G2b `--rounds 1 --round-seconds 240`,
G3 `--rounds 1 --round-seconds 500`). Each stage ends with an in-process independent
validator (`experiment.validate_stage()` `experiment.py:91-102`).

**What each stage may move** (this is the manual-U unfreeze ladder):

| stage | 368 manual-U routes | 656 non-manual routes |
|---|---|---|
| **G1** | **completely frozen** (excluded from candidate list, `run_g1.py:60-76`) | full XY + Z re-route |
| **G2a** | each of the 8 groups may move to **one shared new body height**, XY body primitives kept byte-identical (`manual_reheight.feasible_heights` `:58-83`, `shift_height_keep_xy` `route_builder.py:223-256`) | full XY + Z re-route |
| **G2b** | each of the 368 routes may pick its **own** body height, XY kept (`manual_reheight.reheight_one_route` `:217-239`) | full XY + Z re-route |
| **G3** | **fully optimisable** — same engine/freedom as non-manual (`run_g3.py:58-61`; `manual_policy='fully_optimizable'`) | full XY + Z re-route |

Strictly: the 368 manual-U routes are **frozen through stage 04 / 05 / 06 / G1**;
G2a/G2b unfreeze **height only** (XY body frozen); G3 unfreezes them completely. The
per-route engine also rebuilds planar XY from the `layer2d` R15 family library
(including the multi-arc short-S override, §4.3).

**Inputs:** the start directory `routes_l3d.json` + `assignment_1024.csv`
(`paths.load_baseline()` `paths.py:122-131`), and the frozen 18L authority for
identity/port/manual-contract checks. **Outputs:** per stage a standard set
(`routes_l3d.json`, `assignment_1024.csv`, `crossing_stats.json`,
`geometry_changes.json`, `manual_u_changes.json`, `strategy_stats.json`,
`failed_attempts.json`, `optimization_history.csv`, `SHA256.json`, `config.json`,
`summary.json`, `validation/`) plus `manual_group_reheight.json` (G2a),
`manual_route_reheight.json` (G2b); `best_valid/` (routes/assignment/stats) is what
G4 consumes. Schemas: `xyz_joint_g123_routes_v1` (`paths.py:46`). Checkpoints:
`checkpoints/checkpoint_%04d/` every 25 accepts (`optimizer.py:117-124,160-167`).

**Runtime (21H [R]):** G1 2033.3 s (2×1200 s cap) + 38.2 s validation;
G2a 551.9 s; G2b 607.6 s; G3 546.9 s; whole warm chain 1706.4 s; G3_cold ≈1239 s;
P0/P1/P2 393.9 s. Budgets are wall-clock caps.

### 3.6 Stage 08 — G4 global ALNS chain (C0/G4a/G4b/G4c_frozen/G4c_free/G4d)

**Modules:** `xyzrouter/g4/`: `run_g4_engine.py` (dispatcher `:84`),
`run_g4a.py` (`main` `:435`), `run_g4b.py` (`:710`), `run_g4c.py` (`:117`),
`run_g4d.py` (`:97`), `c0_continue.py` (`:480`), `alns.py` (`G4Search`),
`joint_world.py` (`JointWorld`, `Transaction`), `make_way.py`, `neighborhood.py`,
`group_replan.py`, `arm_base.py`, `artifacts.py`, `ledger.py`, `paths.py`,
`fair_runner.py` (`:1226`), `contract_audit.py`, `independent_metrics.py`,
`metrics_collect.py`, `report_g4.py`, `plots_g4.py`, `archive_g4.py`.

**Entry commands (21H, as executed):**
```powershell
# common start fingerprint: G3 best_valid (routes SHA + crossings)
python -m ...g4.run_g4_engine --arm C0 --seconds 1200 --seed 20261104 --start-dir <g3 best_valid> --out-dir 08_g4/01_arm_C0
python -m ...g4.run_g4a --budget-seconds 1200 --seed 20261104 --out-dir 08_g4/02_arm_G4a
python -m ...g4.run_g4b --budget-seconds 1200 --seed 20261104 --out-dir 08_g4/03_arm_G4b
python -m ...g4.run_g4_engine --arm G4c_frozen --seconds 1800 --seed 20261104 --start-dir <g3> --out-dir 08_g4/04_arm_G4c_frozen
python -m ...g4.run_g4_engine --arm G4c_free  --seconds 1800 --seed 20261104 --start-dir <g3> --out-dir 08_g4/05_arm_G4c_free
python -m ...g4.run_g4_engine --arm G4d       --seconds 2400 --seed 20261104 --start-dir <g3> --out-dir 08_g4/06_arm_G4d
# independent validator per arm / chain link:
python -m ...xyzrouter.validate_xyz --run-dir <arm>/best_valid --out-dir <arm>/validation `
    --manual-policy fully_optimizable --baseline-dir <frozen 18L authority>
# progressive chain:
python -m ...g4.fair_runner --chain --run-chain --budget-seconds 1200 --seed 20261104 `
    --chain-g4c-arm G4c_free --chain-seconds-g4c 800 --chain-seconds-g4d 1200 ...
```

**Arm contracts (what each may move):**

| arm | movable set | height freedom | XY freedom | mechanism |
|---|---|---|---|---|
| C0 | all 1024 | single-route migration | single-route corridor rebuild | legacy G3 `Optimizer` continues, no new DOF |
| G4a | 368 manual-U only | one shared height per fixed 8-group | whole group rebuilt | group transaction + height enumeration |
| G4b | 368 manual-U only | single migration / swaps / split / reorg | full rebuild | dynamic grouping transactions |
| G4c_frozen | 656 non-manual; 368 manual **completely frozen** | non-manual free | full rebuild | joint make-way ALNS + greedy sweep |
| G4c_free | all 1024 | all | full rebuild | same engine, manual geometry may move, label kept |
| G4d | all 1024 | all | full rebuild | global LNS/ruin-recreate |

Key functions: `joint_world.JointWorld.plan_candidates()` `:326`,
`plan_forced()` `:425`, `replace_one()` `:464`, `Transaction.finish()/abort()`
`:644/677`; `alns.G4Search.run()` / `_run_sweep()`; `arm_base.ArmContext.load()`
`:73-106`; start loader `g4/paths.py` `load_start()` `:183` (20H: fingerprint
computed, §5/§7). Budget counters: `g4/ledger.py::Ledger` keys
`route_3d_checks`, `d56_candidate_evals`, `transactions`, `accepted_*`, `gain`,
`wall_seconds`; contract `DEFAULT_BUDGET = dict(route_3d_checks=30000,
d56_candidate_evals=120000, wall_seconds=1800)` and `ARM_BUDGETS =
{C0:1200, G4a:1200, G4b:1200, G4c_frozen:1800, G4c_free:1800, G4d:3600}`
(`g4/paths.py`); equal-counted mode via `--counted-d56-budget/--counted-checks-guard`.

**Frozen vs movable:** manual-U routes are frozen in G4c_frozen; fully movable in
G4b (group granularity) and G4c_free/G4d (route granularity); G4a moves fixed manual
groups. Checkpoints every 50 accepts / 10 min, exact rollback; `best_valid` only
written when the exact total strictly decreases after a committed, verified
transaction.

**Outputs:** per arm the standard set + `budget_ledger.json`, `config.json`,
`summary.json`, `summary_g4.json`, `strategy_stats*.json`, `failed_attempts.json`,
`optimization_history.csv`, `best_valid/`, `checkpoints/`, `validation/`; archive
root `LAST`/`BEST.json`, `experiment_matrix.csv`, `budget_ledger.csv`, `metrics.csv`,
`fair_comparison.md`, `report.md`, `comparison.md`, `MANIFEST.json`, `code/` snapshot,
`08_progressive_chain/progressive_chain.json|md`.

**Runtime (21H [R]):** C0 1208.76 s; G4a 1018.74 s; G4b 1099.82 s;
G4c_frozen 1847.02 s; G4c_free 1840.36 s; G4d ≈1354 s (2 sessions);
chain links 740.52 s / 1229.96 s; warm 06b 1061.44 s; validator 19–27 s per run.
Budget utilisation: wall, not counted caps, was binding on 21H; equal-counted mode
is recommended for 20H cross-arm fairness.

### 3.7 Stage 09 — multi-arc ON/OFF ablation

**Switch (height-agnostic):** `layer2d.MULTI_ARC_POLICY` `layer2d.py:229-241`
(env `G4_ENABLE_MULTI_ARC`, default `'1'`); `multi_arc_enabled(cfg)`
`layer2d.py:237-241`; geometric detector `local_multi_arc_regions(primitives)`
`layer2d.py:244-290`; cheap prefilter `spec_uses_multi_arc()` `:293-301`;
enforcement in `_LayerRouter.__init__` `:1214-1217` and
`_iter_candidates()` `:1299-1352` (drop `('S', shift)` specs before building
`:1311`; hard geometric reject after build `:1335-1340`); propagation through
`xyzrouter/local_reroute.xy_candidates()` `local_reroute.py:112` →
`router_cfg['enable_multi_arc'] = L2.multi_arc_enabled(cfg)` `:126`, which is the
single candidate path of the G4 engines.

**Arms (21H FINAL strict design):**
```powershell
# Stage-0: convert an ON start into the OFF grammar (only the ON start; measure effect A)
$env:G4_ENABLE_MULTI_ARC = '0'
python -m ...tools.convert_multi_arc --start-dir <G3 best_valid> --out-dir <exp>/common_start_off
# Primary: equal candidate-evaluation budget, 2 arms x 3 seeds
powershell -File experiments\G4_MULTI_ARC_ABLATION_FINAL_1024\tools\run_arm.ps1 `
  -Arm on|off -Tag c1_<arm>_<seed> -Seed <seed> -CountedD56 24000 -CountedChecks 9000 -Seconds 5400
# (run_arm.ps1 -> run_g4_engine --arm G4c_free ..., then a fresh validate_xyz;
#  then run_all_analysis.ps1: collect -> summarize -> curves -> stage0/repair/gap ->
#  layers/2R -> make_validation_summary -> assemble_archive -> manifest)
```
21H results to carry as **scale only** (never as 20H numbers): strict ON 2203 vs
OFF 3601 mean crossings (paired −1398, 3 seeds); historical mixed-package
1202 vs 3484; conversion effect A 1322→3967 (+2645, 197 multi-arc routes);
cold-start smoke ON 1024/1024 legal at 11890 crossings, OFF failed stage C on plane
L20 (41/52) — a feasibility asymmetry, not an ON/OFF effect.

**Frozen vs movable:** the only changed variable is the boolean
`enable_multi_arc`; both arms start from the same converted 0-multi-arc state,
same seed policy, same counted budget, and only the G4c_free/G4d search degrees of
freedom (height + XY rebuild of routes) apply.

**20H status:** blocked on a 20H G3 `best_valid`; `paths20.MULTIARC`
(`09_multi_arc_ablation`) and `COLDSTART20_MULTIARC_ROOT` are published but not yet
consumed by any code; the ablation tools live only in the historical experiment
packages and need a bootstrap-first port (see §7).

> **Update 2026-11-18 02:30:** executed. The 20H port is
> `coldstart20/run_multiarc.py` + `coldstart20/convert_multiarc20.py`; the strict
> common-start OFF start is infeasible (1 residual multi-arc route 456,
> 1395 -> 4559, +3164 crossings, conversion exit 4 -> `ABORTED_OFF_INFEASIBLE.json`),
> and the executed substitute is the cold-start ON/OFF pair (ON 12338 / OFF
> 14233, both validated). See the final section.

### 3.8 Stage 10–12 — best_valid / figures / reports (planned)

`10_best_valid` is the frozen best legal 20H solution (selected from the G4 chain /
stage 07), `11_figures` the plots, `12_reports` the report. The frozen generators are
`reheight21/plots21.py` (main `:3142`, `generate_plots()` `:3040`,
`figure_per_height()` `:1807`, 21-entry `FALLBACK_PLANES` `:112`) and
`reheight21/report21.py` (main `:1770`, `golden_numbers` `:1062-1065`),
`archive21.py` (main `:449`). They are **not yet 20H-safe** (hardcoded 21H golden
numbers/fallback tables), see §5 and §7. Stage 04 already writes
`12_reports/stage04_nonc4_summary.json`.

---

## 4. What Stage X can modify

### 4.1 Degrees of freedom per stage

| stage | main body height | XY geometry | fanout / transition leads | planar multi-arc candidates |
|---|---|---|---|---|
| 03 A (assignment) | **assigns** `target_layer` for all 1024 (whole C4 orbits for Z1-other / Z2-other; manual planes fixed) | no | no | no (no planar routing yet) |
| 03 B (fanout) | fixed by A | no | **builds** the R15 S-transitions / interface-direct leads; lead placement per row | no |
| 03 C (layer2d) | fixed by A | **full per-height 2D corridor** inside the 150×150 mm plate (strict D56) | no | **chooses** among the R15 family incl. short-S multi-arc candidates (switch default ON) |
| 03 D/E/F | fixed by A; repair re-plans leads only | rebuilds failed planes / inserts single routes | lead repair (`_replan_leads`, `_LEAD_PAIRS`) | inherits C output |
| 04 nonc4 | **re-assigns** non-manual routes within family allowed planes (C4 binding removed); manual fixed | full | full (fanout re-planned) | ON (layer2d default) |
| 05 Native-3D P1 | inserts **mid-body excursions** to other heights (short sub-path), body flat mostly unchanged | no (body corridor fixed) | no | not applicable (no new planar routing) |
| 06 Native-3D P2 | same excursion mechanism (plain/arc-span/staircase), joint make-way | no | no | not applicable |
| 07 G1/G2/G3 | **G1**: non-manual target height free; **G2a/G2b**: manual height only (XY body frozen); **G3**: all heights free | G1/G3 full rebuild; G2 XY body kept byte-identical | lead lengths rebuilt (`route_builder.LEAD_CANDIDATES`, `shift_height_keep_xy`) | **yes** — G1/G3 candidate engine is `local_reroute.xy_candidates` → `layer2d._iter_candidates` (multi-arc switch respected) |
| 08 G4 | **all arms** migrate heights (C0 single-route; G4a whole manual group; G4b dynamic manual grouping; G4c* joint make-way; G4d LNS) | full rebuild of moved routes | rebuilt per transaction | **yes**, via the cached `xy_candidates` path (`local_reroute.py:126`), switch default ON |
| 09 multi-arc ablation | unchanged (search degrees same as G4c_free/G4d) | unchanged | unchanged | **the single controlled variable**: ON vs OFF (two-arc short-S allowed vs forbidden) |

### 4.2 The 368 manual-U routes — freeze matrix

`assign21` fixes them to planes 2,3,4,5 (Z1, 64 each) and 10,11,12,13 (Z2,
16/16/40/40), membership from the frozen 18L baseline; their plane ids never change
in any stage, only their physical z (+0.025 mm in 20H) and — after unfreezing — their
geometry.

**Frozen through:** stage 03 generation (they are created there and then fixed),
stage 04 (`plan_with_manual`, `assign_nc.py:140-151`; frozen fanout/bodies as D56
blockers and fixed world citizens; `manual_frozen_check` re-verifies bit-identity),
stage 05 (`native3d` candidate list = non-manual only), stage 06 (same), and **G1**
(completely frozen).
**Unfrozen at:** G2a/G2b **height only** (XY body byte-identical; G2a one shared
height per group, G2b per-route height); **G3** (fully optimisable, same freedom as
non-manual); **G4b** (dynamic regroup + height/XY rebuild); **G4c_free**, **G4d**
(full geometry freedom). G4a additionally relaxes them at fixed-group granularity.

### 4.3 Where the planar multi-arc generator actually lives

There is exactly **one** production generator of planar XY candidates — the R15
family library inside the frozen 2D layer router:

1. **`four_side_1024/fanout1024/layer2d.py` — `_LayerRouter._iter_candidates()`
   (`layer2d.py:1299-1352`).** It streams line / quarter-arc / short-S / L / Z / U /
   detour / staircase candidates; the multi-arc short-S (`('S', shift)`, two tangent
   opposite-sweep R15 arcs with no line between them) is the part controlled by the
   policy. When disabled: specs with `('S', shift)` are dropped before building
   (`:1311`) and any candidate that still contains a `local_multi_arc_regions()` entry
   is rejected (`:1335-1340`, counts `multi_arc_rejected_candidates`).
2. **`four_side_1024/fanout1024/xyzrouter/local_reroute.py` — `xy_candidates()`
   (`:112-161`)** builds one `_LayerRouter` per target plane and forwards the policy:
   `router_cfg['enable_multi_arc'] = L2.multi_arc_enabled(cfg)` (`:126`). Every G123
   and G4 candidate (joint_world plan/probe, make_way, group_replan) goes through
   this function, so the switch applies uniformly to all search arms.
3. **The switch:** `layer2d.MULTI_ARC_POLICY` (`layer2d.py:229-241`) reads
   `G4_ENABLE_MULTI_ARC` **at import time** (default enabled); `enable_multi_arc` is
   also a per-router config key that overrides the env (`multi_arc_enabled()`
   `:237-241`). The switch is **height-count agnostic** (nothing in it depends on
   18/19/20/21 heights); a 20H controlled ablation therefore only needs profile,
   path and validator plumbing, not a code change to the generator.

`layer2d._iter_candidates` is also the only generator used by stage 03 C
(`layer2d.route_all_layers` → `_LayerRouter`), so "planar multi-arc candidates" are
present from the very first layout; the ON/OFF ablation isolates their effect by
re-expressing them in the ablated grammar (Stage-0 conversion) and comparing search
under equal budget.

---

## 5. Hard-coded 21-height assumptions found

Classification: **G** = geometry configuration (plane table / interface heights /
allocation); **S** = search gate or invariant that changes decisions/results;
**R** = report/log/provenance text (wrong numbers/text if not recomputed);
**V** = validation expectation (must not be applied to 20H). "20H behaviour" column
gives the real replacement in `coldstart20.model20` / the applied patches / the 20H
drivers.

| # | file:line (current tree) | literal / behaviour | role | what the 20H profile does instead |
|---|---|---|---|---|
| 1 | `reheight21/model.py:103-104` | `Z1_INTERFACE_MM = 0.0`, `Z2_INTERFACE_MM = 0.5` | **G** | `model20.py:138-139` → +0.025 / +0.525; module swapped by `bootstrap.py:66-72`; `common.INTERFACE_Z`/`l3d.INTERFACE_ROWS` re-pointed (`bootstrap.py:78-93`) |
| 2 | `reheight21/model.py:108-114` | `BODY_PLANES` = 19 body planes incl. `(19, 0.65)` | **G** | `model20.py:142-148`: 18 body planes, no id 19, all +0.025 |
| 3 | `reheight21/model.py:131-132` | `PLANE_IDS` = 21 ids incl. 19 | **G** | `model20.py:165-166`: `(2,3,4,5,6,7,20,1001,8,9,10,11,12,13,14,15,16,1002,17,18)` |
| 4 | `reheight21/model.py:243-246` + `:288,340-343,658-659` | `Z2_OTHER_OLD_TO_NEW` 8-entry 1:1 old-layer→plane map, dereferenced as `.items()` in audit/diff payloads | **G/S** | `model20.py:280-281` whole-orbit plan `((9,14),(14,14),(15,14),(16,14),(17,16),(18,16),(1002,12))`; `model20.py:286` sets `None`; `model20.allocate_z2_other` (`model20.py:540-577`, called from `assign21._z2_other_allocation`) + `_z2_orbit_summary` (`assign21.py:328`) handle the plan form (patch scripts 1–2) |
| 5 | `reheight21/model.py:264-269` | schema strings `reheight21_*` | **R** | `model20.py:296-301` `reheight20_*` for model payloads |
| 6 | `reheight21/assign21.py:74-86` (after patch) | expected counts were module literals; now `M.CONTRACT_*` | **S** | `model20.py:306-346` (20H contract; sums to 1024, direct 100 = 52+48, transitions 924/1848, manual 368) |
| 7 | `reheight21/assign21.py:465` | `height_count_distinct` compares to `len(M.PLANE_IDS)` (patched) | **S** | 20 automatically; verified 20H assignment audit `all_invariants_passed=true` |
| 8 | `reheight21/run21.py:240-241` | `expected_transitions=2*(len(rows)-100)`, `expected_direct_endpoints=200` | **R** | numerically correct for 20H (924→1848 / 200) but should read `M.CONTRACT_ENDPOINT_TRANSITIONS`; audit-repair item |
| 9 | `reheight21/run21.py:266`, `:812` | `layer_model='21 heights (19 body planes + 2 routable interface planes)'` written into `fanout_selected.json` / `routes_l3d.json` | **R** | 20H run still writes this string (observed in both 20H artifacts) → must be derived from the model |
| 10 | `reheight21/run21.py:9` (docstring) | "layer-wise 2D routing on all 21 heights" | **R** | 20 heights |
| 11 | `reheight21/validate21.py:77-78` | default `RUN_DIR_21H = FANOUT_FIRST_21_HEIGHT_REBALANCED_1024` | **G/paths** | captured at import, cannot be re-pointed by bootstrap; 20H always passes an explicit `run_dir` (`run_validate.py:43-46`, `run_nonc4`/`validate_nc`) |
| 12 | `reheight21/validate21.py:80-82` | schemas `fanout_first_21_height_validation_v1` / `..._consistency_v1` / `..._crossing_stats_v1` | **R** | 20H `validation.json` still carries the 21H schema name (observed) → provenance cleanup required |
| 13 | `reheight21/validate21.py:88-96` | `SPEC_*` were 21H literals; now `M.SPEC_*` | **S/V** | `model20.py:328-346`: 20/18/2 planes, new z table, same manual ids/direct totals; all frozen checks unchanged (49 µm rejection verified) |
| 14 | `reheight21/validate21.py:2106` | flag/transcript string `'21_height'` | **R** | cosmetic; should read the profile |
| 15 | `reheight21/plots21.py:88,112` | `RUN_NAME` + 21-entry `FALLBACK_PLANES` | **G/R** | 20H must supply 20-entry fallback or always rely on `layer_planes.json` (present in run dir) |
| 16 | `reheight21/plots21.py:2205` | axis label "21 heights" | **R** | 20 |
| 17 | `reheight21/report21.py:47,1062-1065` | `NEW_RUN_DIR` 21H; `golden_numbers` heights=21, crossings 11890/9797, min clearance 0.100699741, length 157484.192735 | **R/V** | must be recomputed from the real 20H run (validation: 20 planes, 12338/10133, min 0.086498778, length 157368.795) — not yet ported |
| 18 | `reheight21/archive21.py:36,39,41,43-44,49-56` | default run dir, archive root, experiment name, placeholder, code-snapshot lists | **G/paths/R** | new 20H archive root/experiment name; snapshot must include `coldstart20/*.py` |
| 19 | `nonc4/data.py:27-28` | fallback `Z2_OTHER_PLANES = (9,14,15,16,1002,17,18,19)` | **S** | guarded by `M.Z2_OTHER_PLAN`: 20H branch derives from `model20.Z2_OTHER_PLAN` (`:24-26`); the 21H literal only remains on the legacy branch |
| 20 | `nonc4/experiments.py:112` | E2 default `dict(Z1V=2, Z1H=3, Z2_NE=4, Z2_SE=4)` (sum 13) | **S** | 20H has 12 non-manual planes; `run_nonc4.screen` obtains the plan from SA curves/integer programme and never uses this default |
| 21 | `nonc4/validate_nc.py:33-34` | `_EMPTY_PLANE_KINDS` includes the old violation kind `'planes_audited_count_not_21'` | **S/R** | the current validator emits `planes_audited_count_mismatch` / `assignment_used_planes_mismatch`; filter list not yet re-pointed (gap, §7) |
| 22 | `nonc4/assign_opt.py:222` | `optimise_allocation(..., plane_count=13, ...)` default | **S** | 20H has 12 non-manual planes; `run_nonc4.screen` passes `max_planes` from the requested group counts, so the default is not used in the 20H path |
| 23 | `native3d/common.py:48-50` (formerly literal `:38`) | `MOVABLE_PLANES` literal formerly contained 19 | **S** | derived from the active model: 20H → 12 ids `(6,7,20,1001,8,9,14,15,16,1002,17,18)`; a plain (21H) process still resolves the frozen 13-id tuple (verified) |
| 24 | `native3d/route_model.py:221` | interface-heights tuple `(0.0, 0.5)` (now model-derived) | **S** | `(M.Z1_INTERFACE_MM, M.Z2_INTERFACE_MM)` = (0.025, 0.525) — patched at 22:43 |
| 25 | `native3d/phase2.py:25` (historical) / `:31-57` (now) | `BASELINE_CROSSINGS = 2440` | **S** | `_inherited_crossings()` reads the accepted Phase-1 `crossing_stats.json`; fallback `2440` only on the 21H branch, 20H raises if missing (`:52-57`) |
| 26 | `native3d/run_a.py:309`; `run_b.py:153,197,204`; `global_optimizer.py:372` | `baseline_crossings=2606` / `start_total=2606` payload/log fields | **R** | report-only; 20H must derive from the start layout count |
| 27 | `native3d/finalize_phase2.py:189,254-255,266-272,590,619-639` | `2440` and `1967/80.6 %/49.28 %/21 ...` report/summary/plot text | **R** | read from the 20H D/E/F summaries + `crossing_stats`; must not be copied |
| 28 | `native3d/validate_native3d.py:145-163` | `E5_EXPECT` (1024, 2606/2067, audited_heights=21, min 0.068714895, length 157565.774) | **V** | regression mode only; must be replaced by a 20H expectation block or `--regression` must stay off; `--baseline-dir` must point at the 20H manual-U layout. **Correction (23:24):** the 20H Native-3D acceptance validator is `native3d.validate_native3d` itself (it PASSes stages 05/06 with 0 violations); `reheight21.validate21` is the planar-assembly contract validator and cannot judge a mid-path layer-change layout (measured 364 / 577 contract violations on such layouts) -- see the final section |
| 29 | `xyzrouter/run_g1.py:55-56` (before 22:55) | warning `baseline crossings != 2409` | **S** | **patched at 22:54:43 by `patch_g123.py`**: the start total is now read from the start layout (`run_g1.py:49-53` helper, `:78` log), no 2409 literal left in the file |
| 30 | `xyzrouter/run_router_validation.py:598-600` (before 22:55) | hard `RuntimeError` if `baseline_crossings != 2409` | **S** | **patched at 22:54:44 by `patch_g123.py`**: the gate and the P2 totals use the authoritative start total; remaining `2409` occurrences are report text (`:610,723,1877,1954-1956,2248`) |
| 30a | `xyzrouter/optimizer.py:194,232` | "same rule as the frozen 2409 baseline" / "frozen 2409 counting definition" strings | **R** | report text only; `patch_g123.py` also made the checkpoint root stage-scoped (22:54:43) |
| 31 | `xyzrouter/report.py:22,162,210,281,350`; `run_reports.py:96-110` | archive dir `experiments/xyz_joint_g123_1024`, `2409` table headers | **R/paths** | new 20H G123 run/archive root + real numbers |
| 32 | `xyzrouter/visualize.py:172` | `BASELINE_REFERENCE = 2409.0` | **R** | 20H baseline crossing reference |
| 33 | `xyzrouter/g4/contract_audit.py:56`; `independent_metrics.py:88` | duplicated `EXPECTED_ROUTES_SHA256 = '711cf910…'` | **S/V** | `g4/paths.py:41-79` now computes the fingerprint from `best_valid`; the duplicated constants must be re-pointed/removed for a 20H start |
| 34 | `xyzrouter/g4/run_g4b.py:49` | `SCAN_CFG = dict(max_target_layers=19, ...)` | **S** | 18 body heights in 20H → `len(RB.BODY_PLANE_IDS)` |
| 35 | `xyzrouter/g4/report_g4.py:1244,1870,1882,1959`; `archive_g4.py:380-381,408-412` | `1322` start / `1185` final narrative | **R** | read start/final values from `state.start_total` / `START.json` |
| 36 | `xyzrouter/g4/paths.py:26-27` (patched `:26-27,41-79`) | `G4_ROOT = experiments/xyz_joint_g4_1024`; `START_CROSSINGS`/`START_ROUTES_SHA256` were constants | **G/S** | `PE.path_env('G4_ROOT', ...)`, computed `_start_fingerprint()`; unknown start raises for 20H; `G4_ROOT` → `08_g4` via `paths20` |
| 37 | `four_side_1024/l3d/layers.py:32` | `INTERFACE_ROWS = {'z1': 0.0, 'z2': 0.5}` (frozen default) | **G** | per-stack `interface_rows` field (`:108-110`), `build_stack(..., interface_rows=...)` (`:245-251`); `model20.layer_stack()` passes 0.025/0.525 (`model20.py:589-596`); legacy default unchanged |
| 38 | `four_side_1024/fslw/config.py:50` | `PLANE_Z_MM = {1: 0.0, 2: 0.5}` (port row z) | **G** | `bootstrap.py:99-111` re-points the two row heights to +0.025/+0.525 and asserts the 0.5 mm row pitch is unchanged |
| 39 | `four_side_1024/fanout1024/layer2d.py:229-241` | `G4_ENABLE_MULTI_ARC` default `'1'` | not 21H-specific | height-agnostic switch; no 20H change needed (§4.3) |

Not listed as defects (must stay bit-identical, see §6): `R15=15.0`, 0.05 mm
true-3D clearance, 0.05 mm pitch, strict D56 (width 0.05 / edge gap 0.03 / 2D
clearance 0.08), 150×150×1 mm glass, 1024 connections, 368 manual-U membership,
all validator tolerances.

---

## 6. 20-height configuration adaptation

### 6.1 What was changed (configuration only)

| item | 21H | 20H | source |
|---|---|---|---|
| routing heights | 21 (19 body + 2 interface) | **20 (18 body + 2 interface)**; id 19 deleted | `model20.py:142-166` |
| body heights | −0.350 … +0.650 step 0.05 | **every surviving height +0.025** → −0.325 … +0.625 | `model20.py:142-148` |
| interface heights | z1 = 0.0, z2 = 0.5 | **z1 = +0.025, z2 = +0.525** | `model20.py:138-139` |
| Z1-other allocation | 5 planes, 13/13/13/13/12 orbits | **unchanged** (all five planes survive) | `model20.py:270` |
| Z2-other allocation | 1:1 old-layer→new-plane map over 8 planes | **whole-orbit plan over 7 planes** `9:14, 14:14, 15:14, 16:14, 17:16, 18:16, 1002:12` orbits (400 routes) | `model20.py:280-281,540-577` |
| per-plane assigned counts | `{2..5:64, 6/7/20/1001:52, 8:48, 9:52, 10/11:16, 12/13:40, 14/15/16:52, 17/18/19:52, 1002:48}` | `{2..5:64, 6/7/20/1001:52, 8:48, 9/14/15/16:56, 10/11:16, 12/13:40, 17/18:64, 1002:48}` | `model20.py:306-314`; verified in 20H run [V] |
| direct routes | 100 (52 z1 + 48 z2) | **unchanged** 100 (52+48) | `model20.py:315` |
| transitions | 924 routes → 1848 endpoints | **unchanged** | `model20.py:316-317` |
| manual routes | 368 (8 groups, planes 2,3,4,5,10,11,12,13) | **unchanged ids/counts**, z +0.025 | `model20.py:234-251,318-322` |
| model payload schemas | `reheight21_*` | `reheight20_*` for layer_planes / stack / rules / assignment audit / diff / experiment-A | `model20.py:296-301` |
| l3d stack | `INTERFACE_ROWS {0.0,0.5}`, contiguous ids 2..20 | per-stack `interface_rows {0.025,0.525}`, ids `{2..18,20}` legal | `l3d/layers.py:108-143,245-251`; `model20.py:581-600` |
| writable directories | `outputs/manual_c4_new_connectivity/*`, `experiments/xyz_joint_*` | `experiments/COLD_START_20_HEIGHT_1024/NN_*/...` via `COLDSTART20_*` env | `paths20.py:42-61`; patch `patch_paths_profile.py` |
| G4 start fingerprint | literal `711cf910…` / `1322` | computed from the 20H G3 `best_valid` (+ optional `COLDSTART20_START_SHA/START_CROSSINGS`); hard-fails if the start is missing | `g4/paths.py:41-79` |
| Native-3D inherited crossing total | literal 2440 | read from the accepted Phase-1 `crossing_stats.json` | `native3d/phase2.py:31-57` |
| Native-3D movable planes | literal 13-tuple incl. 19 | model-derived: 12 heights for 20H | `native3d/common.py:48-50` |
| fanout / port row heights | `common.INTERFACE_Z` 0.0/0.5 | +0.025/+0.525 with the **0.5 mm port row pitch unchanged** | `bootstrap.py:78-112` |

### 6.2 What was **not** changed (bit-identical by construction)

| rule / constant | value | where re-asserted in 20H |
|---|---|---|
| minimum bend radius R15 | **15.0 mm** (sampled ≥ 15 − 1e-6) | `model20.py:133`; validator thresholds unchanged (`validate21.py` frozen constants); 20H run min transition sampled radius 14.99999998 mm [V] |
| true-3D centre-line clearance | **0.05 mm** | `model20.py:132`; 20H validation `min_3d_clearance_mm = 0.086498778` ≥ 0.05 and the 50 µm/49 µm consistency tests pass [V] |
| minimum layer pitch | **0.05 mm** (measured 0.04999999999999993, accepted by the `>= 0.05 − 1e-9` rule — same floating behaviour as the frozen validator) | `model20.py:131`; `validator_consistency_tests.json`: `model_min_pitch_is_50um`, `world_rejects_49um_plane_separation`, `invalid_49um_stack_rejected` all passed [V] |
| strict same-layer D56 | width 0.05 + edge gap 0.03 mm ⇒ 0.08 mm same-layer centre-line; legal transverse crossings; ≥ 5° crossing angle | `model20.py:134-136` (`WIDTH_MM`, `EDGE_GAP_MM`, `CLEARANCE_2D_MM`); 20H validation `same_plane_crossing_violations=0`, `min_non_crossing_centerline_mm=0.080748117` [V]; 49 µm D56 synthetic case still rejected [V] |
| glass envelope | 150 × 150 × 1 mm, z ∈ [−0.35, +0.65] mm | `model20.py:128-130`; 20H validation `geometry_pass=true`, `check_glass` unchanged [V] |
| connections | **1024** fixed (512 z1 / 512 z2), 368 manual, 100 direct | `model20.py:315-322`; 20H validation counts 1024/512/512/368/100 [V] |
| manual-U membership / plane ids | 8 groups, planes 2,3,4,5,10,11,12,13, counts 64/64/64/64/16/16/40/40 | `model20.py:234-251,318-322`; 20H `assignment_audit` invariant `manual_unchanged`/`manual_counts` passed [V] |
| port geometry | 0.25 mm column pitch, 0.5 mm row pitch, 9 mm connector pitch | `bootstrap.py:99-111` only changes the two row z values and asserts the row pitch is unchanged [V] |
| validator geometry checks / tolerances | R15, clearance, glass, D56, structure, ports, crossings, consistency suite | `validate21.py` frozen code; 20H `validation.json`: `geometry_pass=true`, `contract_pass=true`, `validation_pass=true`, `violation_count=0`, `exit_code=0`, `validator_consistency_passed=true` [V] |

### 6.3 Explicit separation: geometry configuration vs validation standard

* **Geometry configuration changed:** the 20 plane height table (L19 deleted,
  +0.025 mm shift), the two interface heights, the Z2-other allocation plan and the
  derived per-plane assignment counts, the model payload schema names, and the
  writable run directories. These are *inputs*; changing them does not touch any
  acceptance rule.
* **Validation standard relaxed: NONE.** No threshold, tolerance, D56 rule, R15
  check, clearance check, glass check, port check, crossing definition, contract
  count, or manual-freeze rule was weakened. The 20H validators are the **frozen**
  `validate21.validate()` / `validate_native3d.validate_run()` / `validate_xyz.py`
  operating with the 20H configuration tables; only the *expected configuration*
  (plane count 20, body count 18, interface z 0.025/0.525, per-plane counts from the
  20H plan) is different, and those expectations come from `model20` exactly as the
  frozen code reads them from `reheight21.model` for 21H. Evidence: the 20H stage-03
  validation passes all geometry + contract checks with 0 violations and the
  consistency suite still rejects 49 µm separations; the regression/`E5_EXPECT`
  number-lock mode is **never** enabled for 20H (`--regression` is a frozen-21H
  assertion, not a 20H gate).

  **Correction (2026-11-17 23:24):** the sentence above names
  `validate21.validate()` among the validators for 20H layouts. That is only
  true for the **planar-assembly** stages 03/04. The Native-3D stages 05/06 and
  every Native-3D-derived G4 layout are accepted by
  `native3d.validate_native3d` only (it understands mid-body R15 excursions);
  `reheight21.validate21` applies the pre-Native-3D 5-part route contract and
  reports a contract mismatch (364 violations on the Phase-1 layout, 577 on the
  converted OFF start) rather than a geometric violation. This was corrected in
  `patch_native3d_def.py`; its `--verify` reports 21H PASS (13 checks) / 20H PASS
  (24 checks). See the final section *"Executed 20-height chain..."*.

---

## 7. Known gaps / non-reusable code (what must be reconstructed)

1. **Stage-04 driver archaeology.** The historical 21H nonc4 campaign's winning path
   (E3/E5) and the screening variants S_A/S_V3 were driven by **ad-hoc `python -c`
   scripts that were never committed**; only console/log output remains in the 21H
   campaign tree. `run_nonc4.py` re-creates E0/E1/E3/select from the frozen building
   blocks, but:
   * there is **no E5-style cross-height repair** (the 21H E5 = E3 plan + 2 manual
     route moves L8→L20 and L8→Z1_INTERFACE, then full re-run); `select_best()` only
     *accepts* a fully legal candidate and logs "joint repair required" when none
     exists — that repair loop is still to be written;
   * S_A/S_V3 were `search.screen_plan` runs with a saved `screening.json`; the 20H
     `screen` command here is the SA cost-curve/allocation study, not that plan
     screening;
   * the E3 seeds/order matrix is new (the 21H campaign used a single E3/E5 driver).
2. **No 20H drivers yet for stages 05–09 at this map's verification time.**
   `coldstart20/__init__.py:18-21` announces a `drivers` module and `tests_model20`;
   neither existed at 22:47 (the concurrent workstream then added
   `run_native3d_phase1.py` 22:48, `run_g123.py` 22:54, `convert_multiarc20.py`
   22:54 — verify before relying). The frozen
   `python -m ...native3d.run_a`, `...native3d.run_d`, `...xyzrouter.run_g1`,
   `...g4.run_g4_engine` CLIs **cannot** be used for 20H (import-order seam); every
   one needs a bootstrap-first launcher (names: `run_native3d_phase1.py`,
   `run_native3d_def.py`, `run_g123.py`, `run_g4.py`, `run_multiarc.py`). The
   `run_validate.py` wrapper is the model for how it must be done.
3. **21H G4/Phase-2 archives contain post-edited/altered artifacts** — do not trust
   them as code state:
   * the G4 archive `code/g4/*.py` is the 2026-11-04 snapshot; the current tree has
     the equal-counted-budget patch on 6 files (`alns.py`, `arm_base.py`,
     `artifacts.py`, `run_g4c.py`, `run_g4d.py`, `run_g4_engine.py`, +176/−13); the
     other 18 files are byte-identical. A 20H archive must snapshot the **current**
     g4 package (and record the multi-arc policy SHAs);
   * Phase-2 `near_miss_results.json` on disk has `runs[]`/`note` keys the current
     `run_f_nearmiss.py` does not write (artifact/script drift);
   * `finalize_phase2.py` reads `arcs['classes']`, which the
     `arc_crossing_analysis.json` payload does not contain → the report's E0 table
     prints 0/0/0 (real values are in `aggregates.totals.class_counts`);
   * `save_best_valid()` does not write `transition_stats.json` → the Phase-1
     `118 mid-transitions` copy is stale and G123 had to override it;
   * the Phase-2 `baseline/` directory is a byte copy of Phase-1 created
     out-of-band; no script writes it;
   * the G4 chain-start metadata bug (`load_start` reported the constant `1322` even
     for a 1294-crossing link) is only fixed by the computed fingerprint in
     `patch_paths_profile.py` — the report/`metrics_collect` literals remain.
4. **`preflight_audit.py` / `l7_geometry_audit.py` are 21H provenance.** They encode
   the frozen 21H authority (E5, 2409, `TARGET_Z=-0.10`, baseline SHA 711cf910…,
   copies of 21H artifacts). `xyzrouter/BASELINE_AUTHORITY =
   XYZ_RUN_DIR/'baseline_authoritative'` has no 20H producer yet, yet G1/G4 identity
   and manual-contract checks need it. A 20H authority-snapshot writer (profile
   payload + manually-frozen route file + independent validation + `START.json`) must
   be reconstructed; `l7_geometry_audit` needs `TARGET_Z = −0.075` (L7 at −0.075 mm)
   and the 20H `best_valid`.
5. **Report/figure stack not yet ported.** `plots21.py` (21-entry `FALLBACK_PLANES`,
   "21 heights" labels), `report21.py` (21H `golden_numbers` 11890/9797/0.100699741/
   157484.192735), `archive21.py` (21H run dir/experiment/archive root/placeholder).
   `report21.MODEL_*` follows `validate21.SPEC_*` (so it follows the profile) but its
   golden numbers and image names are literal 21H. The 20H run also still carries
   mixed provenance strings (see below).
6. **Mixed provenance strings in the completed stage-03 run** (must be fixed before
   the final report; no geometry impact): `routes_l3d.json` schema
   `reheight21_routes_l3d_v1`, `layer_model: "21 routing heights = 19 body planes +
   2 routable interface planes"`, an embedded `experiment: "FANOUT_FIRST_21_HEIGHT_
   REBALANCED_1024"`; `fanout_selected.json` schema `reheight21_fanout_selected_v1`;
   `final_stats.json` schema `reheight21_final_stats_v1` and experiment
   `FANOUT_FIRST_21_HEIGHT_REBALANCED_1024`; `crossing_stats.json` schema
   `fanout_first_21_height_crossing_stats_v1`; `validation.json` schema
   `fanout_first_21_height_validation_v1`. Also `coldstart20_validation_summary.json`
   is absent from the run dir, i.e. the validator was invoked through
   `validate21`/`run_validate` without keeping the wrapper summary — provenance gap.
7. **`nonc4` adaptation has no audited patch script.** `nonc4/assign_nc.py`
   (22:45:53), `nonc4/data.py` (22:46:38) and `nonc4/assign_opt.py` (22:47:01) were
   changed after the audit snapshot and before `run_nonc4.py`; the four scripts in
   `00_audit/` do not cover them (see `adaptation_log.md` §6). They must be
   retro-documented as exact-match patches (or a new audited script) so the change
   set stays reproducible.
8. **`nonc4/validate_nc.py:33-34` filter names are stale** (`planes_audited_count_
   not_21` no longer exists in the current validator; new names are
   `planes_audited_count_mismatch` / `assignment_used_planes_mismatch`). The stage-04
   validator wrapper therefore needs a re-point before its reports are trusted for
   empty-plane filtering (it does not weaken geometry).
9. **Multi-arc ablation is 20H-blocked and its tools are archived outside the code
   tree.** No 20H G3 `best_valid` exists yet; `09_multi_arc_ablation` and
   `COLDSTART20_MULTIARC_ROOT` are empty/unconsumed; `convert_multi_arc.py`,
   `run_arm.ps1`, `run_all_analysis.ps1`, `audit_state.py`, etc. only live under
   `experiments/G4_MULTI_ARC_ABLATION_2024/…/FINAL_1024` packages and must be ported
   bootstrap-first. The 21H cold-start OFF smoke **failed to route plane L20**
   (41/52 first pass), so 20H OFF-grammar feasibility is an open risk: report
   residual routes as a scientific result, never dilute the OFF arm.
10. **`02_annealing` is a scaffold, not a used stage.** The layer assignment actually
    happens in stage 03 A (`assign21`); the C4-free SA happens in stage 04. Do not
    look for a separate 02-stage driver; the numeric stage order above is the real
    one. `01_height_config` is likewise metadata only (`model20` is the configuration).
11. **The 20H step-3 `final_stats.json` min 3D clearance** prints exactly `0.05`
    while the validator measures 0.086498778; `final_stats` is generated by `run21`
    from the world check's route-wise minimum, the validator scan is the authoritative
    number. Use the validator value in reports.
12. **G4 equal-budget mode**: 21H showed wall clock, not counted caps, was binding
    (85–107 % budget). For a claimable 20H ON/OFF or cross-arm comparison use the
    equal-counted mode (`--counted-d56-budget 24000 --counted-checks-guard 9000`)
    exactly as the strict FINAL ablation did; do not silently shorten budgets.

---

## 8. Reproduction commands for the 20-height chain

All commands run from the project root with the venv interpreter
`.venv\Scripts\python.exe` (Python 3.10.11). Process rule: every 20H driver imports
`coldstart20.bootstrap` **first** (the packaged drivers already do).

```bat
:: 0) sanity: profile installs and the 20H model is the one the pipeline sees
.venv\Scripts\python.exe -c "from four_side_1024.fanout1024.coldstart20 import bootstrap as B; import json; print(json.dumps(B.profile_payload(), indent=1)[:800])"

:: 1) STAGE 03 — 20H fanout-first baseline (A assignment -> B..F)
.venv\Scripts\python.exe -m four_side_1024.fanout1024.coldstart20.run_initial --stages ABCDEF --max-iters 3
::    resume/repair variant:  --stages CDE --max-iters N   (reuses the existing assignment)
::    independent frozen validation of the run dir:
.venv\Scripts\python.exe -m four_side_1024.fanout1024.coldstart20.run_validate --run-dir experiments\COLD_START_20_HEIGHT_1024\03_fanout_and_xy\run_initial_20h

:: 2) STAGE 04 — C4-free SA + joint repair ("E5" accepted legal solution)
.venv\Scripts\python.exe -m four_side_1024.fanout1024.coldstart20.run_nonc4 all
::    stepwise:  e0  ->  screen --seed 11 --time-budget 60  ->  e1  ->
::               e3 --seed 11 --order route_id  ->  select  ->  summary
::    outputs: experiments\COLD_START_20_HEIGHT_1024\04_initial_3d_and_e5_repair\nonc4_programme\

:: 3) STAGE 05 — Native-3D Phase 1 (A/B/C)   [driver appeared 22:48:24: coldstart20/run_native3d_phase1.py; verify before use]
.venv\Scripts\python.exe -m four_side_1024.fanout1024.coldstart20.run_native3d_phase1 --help
:: 4) STAGE 06 — Native-3D Phase 2 (D/E/F)   [driver NOT YET PRESENT: coldstart20/run_native3d_def.py]
::    prerequisite: crossing_intervals on the stage-04 accepted layout; then D -> E -> F/F+/near-miss -> finalize
:: 5) STAGE 07 — G1 -> G2a -> G2b -> G3      [driver appeared 22:54:27: coldstart20/run_g123.py; verify before use]
.venv\Scripts\python.exe -m four_side_1024.fanout1024.coldstart20.run_g123 --help
:: 6) STAGE 08 — G4 arms + chain             [driver NOT YET PRESENT: coldstart20/run_g4.py]
::    per arm: run_g4_engine.main(['--arm',A,'--seconds',S,'--seed',20261104,
::             '--start-dir',<07 best_valid>,'--out-dir',<08/arm>])
::    each arm: validate_xyz.main([...]) in a fresh bootstrap-first process
:: 7) STAGE 09 — multi-arc ON/OFF           [partially ported 22:54:06: coldstart20/convert_multiarc20.py; run_arm port NOT YET PRESENT]
::    convert_multi_arc (G4_ENABLE_MULTI_ARC=0) -> run_arm.ps1 on|off (3 seeds,
::    counted d56=24000 / checks=9000) -> run_all_analysis.ps1
```

Notes:
* stages 05–09 commands are the **planned** bootstrap-first equivalents of the
  archived 21H commands quoted in §3; do not run the `python -m ...native3d.*` /
  `...xyzrouter.*` / `...g4.*` forms directly for 20H (21H/20H model mix — see §7.1
  of `g4.md` for the measured silent-mix evidence: 50 routes at deleted z = +0.65).
* the legacy 21H chain remains reproducible unchanged in a process that does **not**
  import the bootstrap (no `COLDSTART20_*` environment variables set).
* a 20H run writes only under `experiments/COLD_START_20_HEIGHT_1024/`; the 21H
  `outputs/manual_c4_new_connectivity/*` trees and `experiments/xyz_joint_*` archives
  are read-only.

---

## 9. Evidence index

* Stage order / commands / run dirs: `run_initial_20h/run.log` (22:38:01–22:42:30),
  `04_.../nonc4_programme/_logs/run.log` (22:46:42+), stage `README.md` files under
  `outputs/manual_c4_new_connectivity/*`, `experiments/xyz_joint_{g123,g4}_1024/`.
* 20H model/config: `coldstart20/model20.py` (all citations above),
  `coldstart20/bootstrap.py`, `coldstart20/paths20.py`, `coldstart20/profile_env.py`.
* 20H stage-03 outputs: `03_fanout_and_xy/run_initial_20h/` (`validation.json`,
  `crossing_stats.json`, `final_stats.json`, `assignment_audit.json`,
  `validator_consistency_tests.json`, all schemas/values quoted in §2.4/§3.1).
* Hard-coded literals: current-tree grep of the files listed in §5 plus the
  classification tables of `reheight21.md` §1.2/§4.1, `nonc4.md` §6,
  `native3d_abc.md` §3.2, `native3d_def.md` §4, `g123.md` §4, `g4.md` §4,
  `multiarc.md` §1.1.
* Frozen 21H reference numbers (scale only, never 20H results): `reheight21.md` §0;
  `nonc4.md` §8; `native3d_abc.md` §8; `native3d_def.md` §8; `g123.md` §8;
  `g4.md` §7; `multiarc.md` §1.3–1.4.

---

## Executed 20-height chain: measured results and drifts

This section supersedes every "live status", "planned" and "driver not yet
present" statement of §1, §2.4, §3.3–§3.7 and §7. It records **what was actually
executed** from 2026-11-17 22:38:01 to 2026-11-18 02:00 (local, UTC+8), with the
measured wall times and the real validator used at each stage. Sources: the
per-stage `run.log` / `*_status.json` / `*_chain.log` under
`experiments/COLD_START_20_HEIGHT_1024/`, the per-stage `summary.json`
`elapsed_seconds`/`seconds` fields, file mtimes where a stage writes no clock,
`12_reports/final_metrics.json` (01:41:33) and `12_reports/EXPERIMENT_REPORT.md`
(01:42:11). Late in-session execution that finished after the report cutoff is
flagged `[after 01:42]`.

### 10.1 Executed command sequence per stage

All commands run from the project root with `.venv\Scripts\python.exe`
(Python 3.10.11), i.e. `python -m four_side_1024.fanout1024.coldstart20.<driver>`.
Every driver installs `coldstart20.bootstrap` **before** any pipeline import;
the frozen `python -m ...native3d.* / ...xyzrouter.* / ...g4.*` forms were
**never** used (see §2.2).

| stage | command(s) actually run | outputs |
|---|---|---|
| 01 (metadata) | `python experiments\COLD_START_20_HEIGHT_1024\01_height_config\build_height_config.py` (run at 22:54:44, after stage 03) | `height_table_20.{json,md}`, `height_table_21_vs_20.md`, `profile.json`, `model20_selfcheck.txt`, `SHA256.json` |
| 03 | `python -m ...coldstart20.run_initial --stages ABCDEF --max-iters 3` (22:38:01–22:42:30); then `python -m ...coldstart20.run_validate --run-dir experiments\COLD_START_20_HEIGHT_1024\03_fanout_and_xy\run_initial_20h` (→ validation 22:45:17); then `python -m ...coldstart20.plot_layers20 --run-dir experiments\...\03_fanout_and_xy\run_initial_20h --out-dir experiments\...\03_fanout_and_xy\figures --dpi 165` (figures 22:55:10); then `python experiments\COLD_START_20_HEIGHT_1024\03_fanout_and_xy\build_crossing_summary.py` (22:55:41) | `run_initial_20h/` (assignment, fanout, per-height routes, `routes_l3d.json`, `validation.json`), `crossing_summary_20h.{json,md}`, `figures/{per_height_plain,per_height_crossings}/` |
| 04 | stepwise (no `e0`, no `summary`): `run_nonc4 screen --seed 11 --time-budget 60`; `run_nonc4 e1`; `run_nonc4 e3 --seed 51`; `run_nonc4 e3 --seed 23`; `run_nonc4 e3 --seed 37`; `run_nonc4 e2 --seed 11`; `run_nonc4 e3 --seed 11`; `run_nonc4 select` (22:46:42–22:56:28; order of the E3 seeds inferred from dir mtimes/log order) | `nonc4_programme/{E1_family_pure,E2_conflict_sharing_seed11,E3_family_pure_sa_seed{11,23,37,51}}/`, `selection.json`, `E5_joint_repair_final/` (`ACCEPTED.json`, SHA256 index) |
| 05 | `run_native3d_phase1 a --top-routes 12` (first attempt 22:56:36 failed the A0 geometry gate 0/2; re-run 22:58:27 after the `patch_native3d_def.py` route-model fix → 11/11), `run_native3d_phase1 b --sample 30 --batch 80` (concurrent with A, 22:56:37–23:00:14), `run_native3d_phase1 c` (23:00:17–23:07:47), `materialize` (23:07:48), `validate-planar` (23:08:09, recorded diagnostic), `validate` (native3D validator PASS, 23:09:53), `plots`, `summary` | `05_native3d_abc/run_native3d_phase1/` (`ACCEPTED_PHASE1.json`, `STAGE05_GATE.json`, `validation.json`, `validation/validation.json`, `validation/planar_contract_validate21_validation.json`) |
| 06 | `run_native3d_phase2 all` (23:10:00–23:54:30), which runs `intervals → blockers → d → e → f → fplus_1 → fplus_2 → nearmiss_1 → nearmiss_2 → finalize` **in-process** | `06_native3d_def/run_native3d_phase2/{analysis,experiment_D,experiment_E,experiment_F,best_valid,validation/final}` + `logs/phase2_chain_status.json` |
| 07 | two concurrent invocations at 23:59: `run_g123 g1` (G1 done 00:23:41) and `run_g123 g3cold` (G3_cold done 00:14:47); then `run_g123 warmstart` (00:34:01–00:57:02); then `run_g123 validate` (router P0/P1/P2, 00:57:2x–01:02:09); then `run_g123 reports` (01:02:10–01:02:17) | `07_g123/run_xyz_joint_1024_20h/{baseline_authoritative,G1_manual_frozen,G2a_manual_group_reheight,G2b_manual_route_reheight,G3_manual_full_xyz,fair_comparison/G3_cold,router_validation/{P0,P1,P2/{xy_z,z_only}},reports,best_valid,archive}` |
| 08 | `run_g4 start` (01:02:22, freezes the G3 `best_valid` as the common start); arms: `run_g4 c0 --seconds 600`, `run_g4 a --seconds 900`, `run_g4 b --seconds 900` (all 01:03:01–01:17:28, each running its own independent validator); then `run_g4 c-frozen --seconds 1800 --counted`, `run_g4 c-free --seconds 1800 --counted`, `run_g4 d --seconds 1800 --counted` (01:18:57–01:39:35) | `08_g4/{00_start_g3,01_arm_C0,…,06_arm_G4d}/` with per-arm `best_valid/`, `validation/validation.json`, `budget_ledger.json`, `summary.json`; `08_g4/07_best_valid/` is empty |
| 08 chain | `run_g4 chain --run-chain` (01:41:14): links 0/1 ok; link 2 (`G4c_free`, 700 s, start `01_link_best_G4ab`) ran 01:41:14–01:53:33 and was validated 01:53:54 `[after 01:42]`; link 3 (`02b_link_best_G4c`, 0-s SPEC-B inheritance) and link 4 (G4d from it) stayed pending/blocked. A manual continuation `run_g4 d --start-dir ...\02_link_G4c --seconds 1200 --counted --out-dir ...\03_link_G4d` was launched 01:54:25 `[after 01:42]` and was still running when this map was finalised (02:04; interim total 1283, not yet final/validated) | `08_g4/08_progressive_chain/{00_link_G3_start,01_link_best_G4ab,02_link_G4c,03_link_G4d}/`, `chain_summary.json`, `progressive_chain.md`, `run_g4_chain.log` |
| 09 | `run_multiarc start` (validates the ON/start layout, 01:03:41); `run_multiarc convert` (01:03:45–01:19:59, exit 4 = OFF start infeasible); cold-start OFF arm: `$env:G4_ENABLE_MULTI_ARC='0'; run_initial --run-dir experiments\...\09_multi_arc_ablation\cold_start_off` (01:20:18–01:24:40), then `run_validate --run-dir ...\cold_start_off` (01:25:10). ON arm = the unchanged stage-03 run. `analyse` was **not** run (`audit/`, `tables/`, `runs/` are empty) | `09_multi_arc_ablation/{START.json,PROTOCOL.md,ABORTED_OFF_INFEASIBLE.json,OFF_FEASIBILITY.json,validation/start,common_start_off/,cold_start_off/,logs/convert.log,ABLATION_REPORT.md}` |
| 10–12 | `select_final` scan only (no `--apply`) → `10_best_valid/selection_scan.json` 01:41:07; `build_final_report` → `12_reports/final_metrics.{json,md}` 01:41:33; `plot_final --layout <E5> --out-dir ...\11_figures\test_on_e5 --label ...` and `--layout <stage05 run> --out-dir ...\test_on_stage05` (23:31:33–23:31:57) | `10_best_valid/selection_scan.json` + `00_initial_fanout_first_20h/`; `11_figures/test_on_{e5,stage05}/` (7 PNGs + manifest + README each); `12_reports/` |

### 10.2 Measured wall times (clock evidence per stage)

| stage | window (local) | measured wall | source of the clock |
|---|---|---:|---|
| 03 | 22:38:01 → 22:42:30 | **269.9 s** | `run_initial_20h/run.log` last line (`done in 269.9s`); sub-stage B 40.3 s, C 12.4 s |
| 03 validation | 22:44:39 → 22:45:17 | **37.95 s** | `03_fanout_and_xy/run_initial_20h/validation.json` `runtime_seconds` |
| 04 | 22:46:42 → 22:56:28 | **586 s** (9.8 min) | `nonc4_programme/_logs/run.log` first/last timestamps (the report's "≈15 min" is not reproducible from this log) |
| 05 | 22:56:35 → 23:10:00 | **805 s** (13.4 min) | run-dir mtimes / stage logs: A re-run 16 s, B 217 s, C 450 s (C summary 452.5 s), materialize + validate-planar 20.3 s + native3D validate + gate |
| 06 | 23:10:00 → 23:54:30 | **2670.0 s** (44.5 min) | `phase2_chain_status.json`: intervals 87.3, blockers 286.1, d 301.1, e 79.5, f 644.0, fplus_1 255.7, fplus_2 253.3, nearmiss_1 413.1, nearmiss_2 316.6, finalize 33.3 |
| 07 | 23:59:18 → 01:02:17 | **3779 s** (63.0 min) | per-stage `summary.json`: G1 `elapsed_seconds=1448.71`, G3_cold `929.09`, G2a `416.68`, G2b `404.82`, G3 `516.19`; router P0/P1/P2 driver ≈00:57:2x–01:02:09 (≈4.8 min, outputs P0 00:58:59 / P1 01:00:13 / P2 01:01:49+01:02:09), reports 5 s; 10.3-min gap 00:23:41→00:34:01 between G1 and warmstart, no artifacts |
| 08 (A-class arms) | 01:02:22 → 01:39:35 | **2233 s** (37.2 min) | arm `run.log`/ledger: C0 process 656.5 s (search 604.6), G4a 854.1 s (search 828.6), G4b 867.2 s (search 842.3), G4c_frozen 1211.6 s, G4c_free 1237.8 s, G4d 1159.7 s; validators 21–27 s each |
| 08 chain link 2 `[after 01:42]` | 01:41:14 → 01:53:54 | **738.9 s** search + 21 s validation | `run_g4_chain.log` + `02_link_G4c/budget_ledger.json` |
| 09 | 01:03:41 → 01:25:10 | **1289 s** (21.5 min) | START.json 01:03:41; convert 01:03:45→01:19:59 (974 s incl. native3D validation 31 s + validate21 diagnostic 32 s); OFF arm 262.3 s (`cold_start_off/run.log`); validate 01:25:10 |
| 10–12 | 01:41:07 → 01:42:11 | ≈64 s | `selection_scan.json` (01:41:07), `final_metrics.json` (01:41:33), `EXPERIMENT_REPORT.md` (01:42:11); figures rendered earlier at 23:31 |

Total measured chain (03 + 04 + 05 + 06 + 07 + 08 A-class arms + 09) ≈
11 670 s ≈ 3.2 h of single-process CPU time; adding chain link 2 (≈760 s with
its validation) and the figures/selection/report steps brings the delivered run
to ≈3.5 h, consistent with the report's "≈3.6 h" once the concurrent stages are
counted.

### 10.3 Per-stage start/end crossing counts and the validator actually used

| stage | start crossings | end crossings | delta | accepted validator (module) | evidence |
|---|---:|---:|---:|---|---|
| 03 | (cold assignment) | **12338** (10133 pairs) | – | `reheight21.validate21` PASS 0 viol. | `03.../validation.json` 22:45:17 |
| 04 | 12338 | **3275** (2774 pairs) | −9063 | `reheight21.validate21` PASS 0 viol. | `E5_joint_repair_final/validation.json` |
| 05 | 3275 | **3103** (2733 pairs) | −172 | **`native3d.validate_native3d`** PASS 0 viol. (`mode=native3d`); planar `validate21` = recorded NON-blocking diagnostic, FAIL 364 violations | `05.../validation/validation.json`, `STAGE05_GATE.json` 23:10:00 |
| 06 | 3103 | **3061** (2705 pairs) | −42 | **`native3d.validate_native3d`** PASS 0 viol. | `06.../validation/final/validation.json` |
| 07 G1 | 3061 | 1485 | −1576 | `native3d.validate_native3d` (`fully_optimizable`) | `G1_manual_frozen/summary.json` + validation PASS |
| 07 G2a | 1485 | 1440 | −45 | idem | `G2a_manual_group_reheight/summary.json` |
| 07 G2b | 1440 | 1409 | −31 | idem | `G2b_manual_route_reheight/summary.json` |
| 07 G3 | 1409 | **1395** (1325 pairs) | −14 | idem; authority preflight also PASS with `manual_policy=frozen` on the 3061 Phase-2 start | `G3_manual_full_xyz/summary.json`; `best_valid/validation/validation.json` |
| 07 G3_cold (control) | 3061 | 1646 | −1415 | idem | `fair_comparison/G3_cold/summary.json` |
| 08 C0 | 1395 | 1383 | −12 | `xyzrouter.validate_xyz` → `native3d.validate_native3d` PASS | `01_arm_C0/validation/validation.json` |
| 08 G4a | 1395 | 1393 | −2 | idem | `02_arm_G4a/validation/validation.json` |
| 08 G4b | 1395 | 1371 | −24 | idem | `03_arm_G4b/validation/validation.json` |
| 08 G4c_frozen | 1395 | 1338 | −57 | idem | `04_arm_G4c_frozen/validation/validation.json` |
| 08 G4c_free | 1395 | **1322** (1255 pairs) | −73 | idem | `05_arm_G4c_free/validation/validation.json` |
| 08 G4d | 1395 | 1337 | −58 | idem | `06_arm_G4d/validation/validation.json` |
| 08 chain link 2 `[after 01:42]` | 1371 (G4b checkpoint) | **1309** (1240 pairs) | −62 | idem | `02_link_G4c/validation/validation.json` 01:53:54 |
| 09 ON (cold start) | (cold assignment) | 12338 | – | `reheight21.validate21` PASS | stage-03 run |
| 09 OFF (cold start) | same cold assignment | 14233 (10637 pairs) | +1895 vs ON (OFF is +15.4 % over ON; the ON arm is 13.3 % below OFF) | `reheight21.validate21` PASS 0 viol. | `09.../cold_start_off/validation.json` 01:25:10 |
| 09 strict common-start conversion | 1395 | 4559 | +3164 (effect A) | `native3d.validate_native3d` PASS on converted start; `validate21` diagnostic FAIL 577 (expected contract mismatch) | `common_start_off/validation_xyz/validation.json`, `OFF_FEASIBILITY.json` |

Main A-class curve: **12338 → 3275 → 3103 → 3061 → 1395 → 1322**
(03 → 04 → 05 → 06 → 07 → 08 G4c-free). The B-class chain link 2 `[after 01:42]`
reached 1309 from the G4b 1371 checkpoint with a 700 s wall budget; it was
independently validated but is **not** part of the A-class arm matrix.

### 10.4 Known deviations from the frozen 21H design (as executed)

1. **G4 budgets: wall caps 600–1800 s with equal counted budgets for the three
   counted arms.** `C0` ran with 600 s; `G4a`/`G4b` with 900 s; `G4c_frozen`/
   `G4c_free`/`G4d` with a 1800 s wall *safety net* plus equal counted budgets
   (`d56_candidate_evals = 24000`, `route_3d_checks` guard = 9000). The counted
   arms actually spent d56 24006 / 24175 / 24266 and route_3d_checks
   3347 / 3327 / 3688, i.e. the counted axis, not the wall clock, was binding
   (see `budget_ledger.json` per arm and `final_metrics.json.g4_arms`). The
   START.json declares the frozen `ARM_BUDGETS` (C0/G4a/G4b 1200 s, G4c 1800 s,
   G4d 3600 s); the executed values above override them, so compare arms only
   on the counted axis.
2. **Native-3D A1 has zero feasible windows.** A0 passed 11/11 but A1 scanned
   the 12 highest-crossing movable routes and found **0/12** feasible single
   mid-body excursions (all carry a corner arc inside the crossing cluster).
   B (independent branch from E5 3275) made 10 excursions for a net **−35**
   (3275 → 3240). The accepted Phase-1 layout comes from branch **C**
   (3275 → 3103, −172), then Phase 2 D/E/F brings 3103 → 3061. This is a
   measured geometric property of the 20H layout, not a rule relaxation.
3. **Multi-arc strict common-start OFF start is infeasible for 20H.** Converting
   the G3 optimum (1395, 213 routes with a real planar multi-arc body) to the
   OFF grammar (deterministic, frozen `plan_candidates(mode='clean')`) converted
   **212/213** routes and left **1 residual route (id 456)** with no OFF-legal
   body in the 20H table; the conversion costs **+3164 crossings (1395 → 4559)**
   and exits 4. Per the pre-registered rule `ABORTED_OFF_INFEASIBLE.json` was
   written and **no OFF search arm was run from that start**. The substituted
   controlled experiment is the **cold-start ON/OFF pair** (identical
   assignment, seeds, budgets, validator; only `G4_ENABLE_MULTI_ARC` differs):
   ON 12338 vs OFF 14233 crossings (−1895 / −13.3 % for multi-arc ON), both
   legal, both `validate21` PASS. The OFF arm is a separate cold-start run, not
   a continuation of the ON chain.
4. **G4 progressive chain links 3/4 handling.** The chain record is:
   link 0 = G3 start 1395 (ok); link 1 = best validated G4a/G4b checkpoint 1371
   (G4b, ok); link 2 = G4c_free rerun from link 1, 700 s → 1309 (ok,
   `[after 01:42]`); **link 3 = `02b_link_best_G4c`, the 0-second SPEC-B
   inheritance of the best *arm* G4c-free checkpoint**, and link 4 = G4d from
   link 3. `fair_runner.build_chain` leaves link 3 `pending` (its source is an
   A-class arm checkpoint, not a chain run), so `run_g4 chain --run-chain`
   stopped at `link 4 blocked: previous link 3 status=pending` (01:54:00). The
   executed workaround was a **manual G4d continuation** from link 2's 1309
   checkpoint (`[after 01:42]`, see §10.1). In addition,
   `08_progressive_chain/progressive_chain.md` and `chain_summary.json` labels
   still carry the 21H prose values ("1322" G3 start, "1294"/"1189" link
   descriptions) while their numeric columns hold the real 20H values.
5. **Artifact/report boundary mismatches (deliverable integrity).**
   (a) `10_best_valid/` was **not frozen** to the measured best: the root holds
   only `selection_scan.json` (01:41:07) plus the stage-03 checkpoint subdir
   `00_initial_fanout_first_20h/` (frozen 22:49:11, 12338 crossings); there is
   no `BEST_VALID.json`/`SHA256.json` at the root, and the scan's winner is
   `04_E5` (3275) because `select_final.py` requires `routes_l3d.json` and
   `crossing_stats.json` in the *same* directory and reads `routed/failed`
   only from `crossing_stats.json` — every G4 arm therefore reads as
   `legal:false`. The measured best 1322 lives at
   `08_g4/05_arm_G4c_free/best_valid/`; the arm's independent validation report is
   `08_g4/05_arm_G4c_free/validation/validation.json` (PASS, 0 violations).
   `08_g4/07_best_valid/` is empty. So `EXPERIMENT_REPORT.md` §4 (frozen
   1322 in `10_best_valid` with `BEST_VALID.json`) is **not backed by the disk
   state** at 02:00.
   (b) `final_metrics.json` (01:41:33) still marks `S08_G4_chain` and
   `S08_G4_best` `available:false`; the experiment report (01:42:11) says the
   chain links "are reported separately in `final_metrics.json`", which is not
   the case. Chain link 2 (1309) finished after both files.
   (c) the figure suite is a **test rendering**: `11_figures/test_on_e5/` and
   `test_on_stage05/` were rendered 23:31 from the E5 (3275) and Phase-1
   (3103) layouts; figure 06 therefore shows Native-2 as 3087, and the
   report's `11_figures/final/06_crossing_curve_vs_stage.png` does not exist.
   (d) `12_reports/stage_curve_20h.json` (23:59:39) predates stages 07/08 and
   reports them as unavailable; use `final_metrics.json` instead.
   (e) `12_reports/validator_report.md`, referenced by the experiment report,
   does not exist; the authoritative validator payloads are the per-stage
   `validation.json` files.
   (f) in `final_metrics.json` the `validator.path` field is the literal string
   `"None"` for S07/S08 because `build_final_report._first_in_chain()` looks for
   `<dir>/validation.json` and `<parent>/validation.json`, while those reports
   live at `<dir>/validation/validation.json` / `<arm>/validation/validation.json`.
   The metric payload itself is the correct full report (counts, crossings,
   min-3D), so only the diagnostic path string is wrong. Note also that the
   artifact-resolution hardening described in the hand-over lives in
   `build_final_report.py` (final-metrics collector), **not** in
   `collect_final.py` (stage-curve collector, which still emits S07/S08 as
   "not run yet").
6. **Wall-time differences vs the report's §6.5 prose.** Measured: 03 270 s
   (report 270 s), 04 586 s (report ≈15 min), 05 805 s (report 590 s + 20 s),
   06 2670 s (report 45 min), 07 3779 s (report 68 min), 08 A-class arms
   2233 s (report 60 min), 09 1289 s (report 25 min). The report's stage table
   is a rounded narrative; the numbers above come from logs/status files.

### 10.5 Corrections to statements in the older text

| older statement (section) | corrected fact (evidence) |
|---|---|
| §1: "at 22:47 stages 05–09 had no 20H driver yet" / §7.2 "the frozen CLIs cannot be used ... every one needs a bootstrap-first launcher (`run_native3d_def.py`, `run_g4.py`, `run_multiarc.py`)" | all launchers now exist and ran: `run_native3d_phase1.py`, `run_native3d_phase2.py` (**not** `run_native3d_def.py`), `run_g123.py`, `run_g4.py`, `run_multiarc.py`, `convert_multiarc20.py`, `plot_layers20.py`, `plot_final.py`, `select_final.py`, `collect_final.py`, `build_final_report.py`; only `tests_model20`/`drivers` announced by `__init__.py` were never written |
| §3.4 / §5 row 28 / §6.3 / §7: "the 20H validators are the frozen `validate21.validate()` / `validate_native3d.validate_run()` / `validate_xyz.py` operating with the 20H tables" (implying `validate21` judges Native-3D layouts) | **wrong for Native-3D layouts.** Stage 05/06 (and every Native-3D-derived G4 layout) are accepted by `native3d.validate_native3d` only; `reheight21.validate21` is the planar-assembly contract validator (5-part lead/transition/body structure) and its audit on a mid-path layer-change layout is a contract mismatch: measured **364 violations** on the Phase-1 layout, **577** on the converted OFF start, while `validate_native3d` returns PASS 0 violations. `patch_native3d_def.py` was corrected at 23:24 to select `validate_native3d`; its `--verify` reports 21H PASS (13 checks) / 20H PASS (24 checks) |
| §3.4: "the Phase-2 `finalize_phase2` validator ... `reheight21.validate21`" (and `run_native3d_phase2.py` docstring/dry-run text) | same correction as above; the executed `finalize_phase2.run_validator()` imports `validate_native3d`. Residual stale strings are text-only (§8.1 of the adaptation log, item 10) |
| §3.3/§3.5/§3.6 "commands (21H form)" and §3.6 budget defaults (C0 1200 s, G4a/G4b 1200 s, G4d 3600 s) | executed as §10.1/§10.4: `run_g4 c0 --seconds 600`, `a/b --seconds 900`, `c-frozen/c-free/d --seconds 1800 --counted`; subcommands are `c0,a,b,c-frozen,c-free,d` |
| §3.7: "20H status: blocked on a 20H G3 best_valid ... tools need a bootstrap-first port" | executed: `run_multiarc start`, `convert` (exit 4, residual 1), cold-start OFF arm `run_initial` with `G4_ENABLE_MULTI_ARC=0`, `run_validate`; `analyse` not run |
| §7.4: "`xyzrouter/BASELINE_AUTHORITY = .../baseline_authoritative` has no 20H producer yet ... must be reconstructed" | implemented: `run_g123` preflight writes `07_g123/run_xyz_joint_1024_20h/baseline_authoritative/` + `AUTHORITY.json`/`SHA256.json`, 20H data contract PASS, independent validation PASS (`manual_policy=frozen`, crossings 3061) |
| §7.1: "there is no E5-style cross-height repair ... that repair loop is still to be written" | the accepted E5 analog (E3 seed 11, 3275) was already fully legal, so `select` materialised it without an extra repair loop; no repair code was added and none was needed for the reported chain |
| §2.4 live status (stage 04 running, no 20H results for 05–09) | superseded by §10.1–§10.3 |
| adaptation_log §3.10: `__init__.py` "lists planned `tests_model20`/`drivers` modules (not yet present)" | still absent; not required by the executed chain |
