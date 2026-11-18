# Native-3D Phase-1 (experiments A / B / C) — audit for the 20-height rebuild

Audit snapshot: 2026-11-17 (~22:40 local). Read-only: no file was modified except this one.
No pipeline stage was executed; only `--help`-class import checks were used.

Audited tree: `four_side_1024/fanout1024/native3d/` (current source, 28 files) and
`outputs/manual_c4_new_connectivity/NATIVE_3D_CROSSING_OPT_1024/` (archived artifacts).
The archived code snapshot `experiments/native_3d_crossing_opt_1024/code/` is
**older** than the current source for `validate_native3d.py` (109 394 B vs 135 646 B),
`visualize.py` (140 887 B vs 141 432 B) and `crossing_intervals.py`; `run_a.py`,
`run_b.py`, `global_optimizer.py`, `batch_avoid.py`, `common.py`, `guard.py`,
`route_model.py`, `single_route.py`, `transition.py` are byte-identical to the current
source. All line references below are to the current source.

Parallel work already present in the tree (aligned with, not duplicated):
`experiments/COLD_START_20_HEIGHT_1024/00_audit/patch_profile_generic.py` (21H tables ->
profile constants for `reheight21/{model,assign21,run21,validate21}.py`),
`four_side_1024/fanout1024/coldstart20/{model20.py,bootstrap.py}`, and the
`l3d/layers.py` patch (per-stack `interface_rows`, non-contiguous routing ids; mtime 22:32).
The 20H stack itself already builds: 20 planes, ids `(2..18, 20)`, interface rows
`+0.025/+0.525`, measured pitch 0.05 mm.

---

## 0. TL;DR — concrete 20H adaptation points (file : constant : new source of truth)

| # | file:line | constant / behaviour | class | required for 20H |
|---|---|---|---|---|
| 1 | `native3d/common.py:13` | `from ..reheight21 import model as M` | model binding | must be resolved to `coldstart20.model20`; requires `from four_side_1024.fanout1024.coldstart20 import bootstrap` **before any native3d import** (`bootstrap.py:64-70`, `148-162`); all `PLANE_*` tables then follow automatically |
| 2 | `native3d/common.py:19` | `E5_DIR = .../NON_C4_CROSSING_OPT_1024/E5_joint_repair_final` | **input source (search data)** | re-point to the 20H accepted legal baseline (analog of E5, produced by stage 04); `load_e5_payload/load_routes/load_assignment` (`:93-111`) read everything from it |
| 3 | `native3d/common.py:23` | `RUN_DIR = .../NATIVE_3D_CROSSING_OPT_1024` | **all writes** | re-point to `experiments/COLD_START_20_HEIGHT_1024/05_native3d_abc/<run>` |
| 4 | `native3d/common.py:38` | `MOVABLE_PLANES = (6,7,20,1001,8,9,14,15,16,1002,17,18,19)` | **search logic** | plane 19 no longer exists; derive `tuple(int(p) for p in M.PLANE_IDS if int(p) not in M.MANUAL_PLANE_IDS)` → 12 ids `(6,7,20,1001,8,9,14,15,16,1002,17,18)`; otherwise `sorted_by_abs_dz`/`shadow_report` raise `KeyError: 19` |
| 5 | `native3d/common.py:21` | `BASELINE_21H_DIR` | dead constant | unused anywhere (grep); delete or leave, no effect |
| 6 | `native3d/route_model.py:221` | `interface_heights = (0.0, 0.5)` | **structure check** | read the model: `(M.Z1_INTERFACE_MM, M.Z2_INTERFACE_MM)` = `(0.025, 0.525)` (or `N.PLANE_Z[1001/1002]`); use in the `is_lead` test |
| 7 | `native3d/run_a.py:309` | `baseline_crossings=2606` | report-only JSON field | write `int(env.accepted_crossings)` captured before A2 (or the 20H baseline `crossing_stats.totals.crossings`) |
| 8 | `native3d/run_b.py:153,197,204` | `baseline_total=2606`, `baseline_crossings=2606` | report-only JSON/log | same as #7 (search uses exact `env.total()` recounts) |
| 9 | `native3d/global_optimizer.py:372,395` | `start_total=2606` | report-only JSON/log | same as #7; `baseline_length_mm` (`:381-382`) already derives from `load_e5_payload()` |
| 10 | `native3d/phase2.py:25` | `BASELINE_CROSSINGS = 2440` | **search gate** | read from the 20H Phase-1 final (`experiment_C/summary.json` `final_crossings` or `crossing_stats.totals.crossings`); gates `run_d.py:239` and `run_e.py:416` (`save_best_valid` only when `total < BASELINE_CROSSINGS`) |
| 11 | `native3d/phase2.py:22-23,27,66-72` | `PHASE1_DIR/PHASE1_RUN_DIR/RUN2`, model-file copy fallbacks | **input/output paths** | 20H Phase-1 run dir + 20H Phase-2 root; model files must be the 20H ones (`layer_planes.json` etc.) |
| 12 | `native3d/validate_native3d.py:127-128` | `RUN_ROOT`, `DEFAULT_BASELINE` | config | 20H run root / 20H accepted legal baseline |
| 13 | `native3d/validate_native3d.py:145-163` | `E5_EXPECT` (2606 crossings / 2067 pairs / 21 audited heights / 1852 transitions / direct 98 / clearance 0.068714895 / length 157565.774) | **config expectation (regression mode only)** | replace by a 20H `BASELINE_EXPECT` frozen from the 20H accepted legal baseline; `audited_heights` 21→**20**; all tolerances unchanged |
| 14 | `native3d/validate_native3d.py:735,760-765` | `routed_count_not_1024`, `plane_z1/z2_count_not_512` | contract expectation | re-freeze from the 20H assignment (100 direct = 52 z1 + 48 z2 in both profiles, so 512/512 likely stays; verify, never hardcode blindly) |
| 15 | `native3d/validate_native3d.py:1690-1702` | baseline crossing totals from `<baseline>/crossing_stats.json` | config input | 20H baseline dir must contain the 20H `crossing_stats.json` (stage 04 output) |
| 16 | `native3d/validate_native3d.py:1706-1713` + manual contract | 368 manual-U routes json-identical to baseline | contract | re-point `--baseline-dir` to the 20H accepted baseline (manual route z shifts +0.025; keeping the 21H baseline would flag all 368) |
| 17 | `run_a.py:343-347`, `run_b.py:181-185`, `global_optimizer.py:390-394` | copy `layer_planes.json/process_rules.json/physical_layer_stack.json/assignment_1024.csv` from `N.E5_DIR` | **input (validator model)** | will become 20H automatically once #2 is re-pointed; the 20H input dir must carry the `coldstart20.model20` payloads |
| 18 | `native3d/final_deliverables.py:16-17` + literals 2606 (`:145,181,187,229,234,242,276,370,379,397`) | `RUN`,`E5` paths / crossing numbers | report-only | re-point paths; derive crossing numbers from artifacts (never literal) |
| 19 | `native3d/finalize_phase2.py` `or 2440` fallbacks (`:189,254-255,590,619,621,639`) and table texts (`:266-272,292-294,359-361,448-471`) | inherited baseline number | report-only | read the 20H Phase-1 `start_total` from its summary; paths `finalize_phase2.py:19-21` follow #11 |
| 20 | `native3d/arc_crossing_analysis.py:84` `events=2606` (inside `PREVIOUS_CLAIM`), `:99` `PLAUSIBLE_PLANE_IDS = N.MOVABLE_PLANES`, `:2721` required `--baseline` | analysis constant | **analysis** (feeds candidate enumeration, not search) | `events` is quoted text only; `PLAUSIBLE_PLANE_IDS` follows #4; `--baseline` points to the 20H Phase-1 accepted layout |
| 21 | `native3d/crossing_intervals.py:2356,2358` | default `--baseline-dir=N.E5_DIR`, `--out-dir=N.RUN_DIR` | analysis | follows #2/#3 (already generic otherwise: 21 → "all model planes") |
| 22 | `native3d/blocker_analysis.py:72-73` | `DEFAULT_BASELINE=N.E5_DIR`, `DEFAULT_NATIVE_DIR=N.RUN_DIR` | analysis | follows #2/#3 |
| 23 | `native3d/validate_native3d.py:114-115`, `guard.py:13-14` | import `reheight21.model/validate21` at module level | import order | import `coldstart20.bootstrap` first, plus an explicit assert (`len(M.PLANE_IDS)==20 and 19 not in M.PLANE_IDS`); consider `bootstrap.assert_20_height_profile()` in every driver |
| 24 | (cross-cutting prerequisite) `four_side_1024/fslw/config.py:50` | `PLANE_Z_MM = {1: 0.0, 2: 0.5}` (port row physical z, via `v3c4.inputs:41-56`, `fanout1024/common.py:169-183`) | **input/model** | `coldstart20.bootstrap` patches `common.INTERFACE_Z` and `l3d.layers.INTERFACE_ROWS` but **not** `fslw.config.PLANE_Z_MM`; if ports stay 0.0/0.5 while the model interface is 0.025/0.525, `validate_native3d._check_port_poses` (`:874-880,904-910`) will flag all 1024 leads. Resolve with the Lead in `01_height_config` before running A/B/C |
| 25 | `native3d/final_deliverables.py:363-397` (README template) and `visualize.py:32,1648,1990,3111,3238` | doc/log strings "21 heights / 21 per-height" | cosmetic | update wording; figure logic is already model-driven (20 panels) |

Not to be touched (must stay bit-identical, already asserted by the 20H profile):
`native3d/common.py:26-34` (`R15=15.0`, `MIN_3D_CLEARANCE=0.05`,
`SHADOW_MM=sqrt(2·R15·0.05)=1.2247448…`, `MIN_MIDDLE_MM=1.0`, `MAX_MIDDLE_MM=120.0`),
`validate_native3d.py:130-139` (R15, 0.05 3D clearance, 0.05 pitch, all `TOL_*`,
`LEGACY_INTERFACE_LAYER_ID=1`), `transition.py:15-32` (footprint/theta formulas),
`route_model.py:204-288` (structure checks), `guard.py` gates,
`crossing_cache.py` (per-physical-z D56 audit), `joint_reroute.py:41-42` (5 routes / 8 rounds).

---

## 1. Entry points, commands, stage order, checkpoints

### 1.1 How A / B / C are launched

All three are plain `python -m` modules with `main(argv=None)` + `if __name__ == '__main__'`
(no console-script entry points; no wrapper scripts exist for A/B/C in the repo):

| stage | module | CLI (argparse) | `__main__` |
|---|---|---|---|
| A | `four_side_1024.fanout1024.native3d.run_a` | `--top-routes` (default 20), `--time-budget` 420 s, `--max-apply` 1, `--skip-a1` (`run_a.py:364-370`) | `run_a.py:402-403` |
| B | `...native3d.run_b` | `--sample` 40, `--batch` 120, `--time-budget` 200 s, `--max-excursions` 3, `--skip-strategies` (`run_b.py:81-86`) | `run_b.py:212-213` |
| C | `...native3d.global_optimizer` | `--strategy` `B4_multi_excursion`, `--max-excursions` 2, `--time-budget` 420 s **per stage** (`global_optimizer.py:286-291`) | `global_optimizer.py:404-405` |
| validator | `...native3d.validate_native3d` | `--run-dir`, `--baseline-dir`, `--out-dir`, `--skip-min-clearance`, `--regression`, `--skip-synthetic`, `--manual-policy {frozen,height_only,fully_optimizable}` (`validate_native3d.py:2801-2824`) | `validate_native3d.py:2847-2848` (exit 0/1/2) |
| figures | `...native3d.visualize` | `--run-dir --baseline-dir --out-dir --demo-baseline --all-experiments --only --quiet` (`visualize.py:3222-3247`) | `visualize.py:3308-3309` |
| interval analysis | `...native3d.crossing_intervals` | `--baseline-dir --out-dir --cluster-gap-mm --shadow-mm --min-middle-mm --max-middle-mm --end-margin-mm --target-planes --validate-top --no-plots --quiet` (`crossing_intervals.py:2353-2382`) | `crossing_intervals.py:2397-2398` |
| arc analysis | `...native3d.arc_crossing_analysis` | `--baseline`/`--out-dir` **required**, `--plot-dir --top-routes --line-merge-mm --quiet` (`arc_crossing_analysis.py:2719-2733`) | idem |

**There are no config files.** `outputs/.../NATIVE_3D_CROSSING_OPT_1024/configs/` exists but
contains **0 files**; no module in `native3d/` loads a config/JSON for parameters (grep for
`add_argument`/`config` shows argparse only). Configuration = module-level constants +
CLI flags. Phase 2 creates a `configs/` dir (`phase2.py:31-35`) but nothing writes into it.
The payloads that look like config (`layer_planes.json`, `process_rules.json`,
`physical_layer_stack.json`) are *copied validator inputs*, not consumed by A/B/C.

### 1.2 Stage order and dependency reality

Logical order is A → B → C → validator (README `README.md:13-22`, `report.md`), but the
archived data proves **A, B, C are independent branches, not a chain**:

* A reads E5 only (`run_a.py:386-389`: `N.load_routes()` → `CC.NativeRouteSet`);
* B reads E5 only (`run_b.py:22-25` `make_env` → `N.load_routes()`);
* C reads E5 only (`global_optimizer.py:34-37` `make_env` → `N.load_routes()`);
* B does **not** start from A's `experiment_A/routes_l3d.json`; C does not start from B's
  either. Each branch re-derives its own accepted layout from the frozen baseline.
* Therefore the "2606 → 2440" headline is C alone; A (2601) and B (2559) are separate
  demonstrators (`report.md:12-13,25,47`).

Exact command sequence (21H, from README + archived run evidence):

```bat
cd C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D
.venv\Scripts\python.exe -m four_side_1024.fanout1024.native3d.run_a --top-routes 12
.venv\Scripts\python.exe -m four_side_1024.fanout1024.native3d.run_b --sample 30 --batch 80
.venv\Scripts\python.exe -m four_side_1024.fanout1024.native3d.global_optimizer
.venv\Scripts\python.exe -m four_side_1024.fanout1024.native3d.validate_native3d --run-dir outputs\manual_c4_new_connectivity\NATIVE_3D_CROSSING_OPT_1024
.venv\Scripts\python.exe -m four_side_1024.fanout1024.native3d.validate_native3d --run-dir outputs\manual_c4_new_connectivity\NATIVE_3D_CROSSING_OPT_1024\experiment_A --out-dir outputs\manual_c4_new_connectivity\NATIVE_3D_CROSSING_OPT_1024\validation\experiment_A
.venv\Scripts\python.exe -m four_side_1024.fanout1024.native3d.validate_native3d --run-dir outputs\manual_c4_new_connectivity\NATIVE_3D_CROSSING_OPT_1024\experiment_B --out-dir outputs\manual_c4_new_connectivity\NATIVE_3D_CROSSING_OPT_1024\validation\experiment_B
.venv\Scripts\python.exe -m four_side_1024.fanout1024.native3d.validate_native3d --run-dir outputs\manual_c4_new_connectivity\NATIVE_3D_CROSSING_OPT_1024\experiment_C --out-dir outputs\manual_c4_new_connectivity\NATIVE_3D_CROSSING_OPT_1024\validation\experiment_C
@rem optional, not part of A/B/C:
.venv\Scripts\python.exe -m four_side_1024.fanout1024.native3d.crossing_intervals
.venv\Scripts\python.exe -m four_side_1024.fanout1024.native3d.visualize --run-dir outputs\...\NATIVE_3D_CROSSING_OPT_1024 --baseline-dir outputs\...\E5_joint_repair_final
```

Discrepancies between README and the archived run:
* README (`README.md:17`) omits `--top-routes`, but `experiment_A/a1_scan.json`
  has `routes_scanned = 12` attempts 142 → the archived A run used `--top-routes 12`
  (`run_a.py:184-196`; `report.md:14,51-64` lists 12 routes).
* B was invoked 6 times (log spans 23:58:38→00:10:14, including two runs whose final
  `full_validate` failed: 00:01:47 `valid=101 violations=923`, 00:03:41 `valid=656
  violations=368`). The archived artifacts correspond to the last successful invocation
  (00:08:52→00:10:14, `sample=30`, batch 80 routes) whose strategy comparison is
  `B1_adjacent net=-14` (`experiment_B/strategy_comparison.json`), batch net −47.
* C ended with `NameError: name 'C' is not defined` at `C.write_csv(...)` in the then-current
  `global_optimizer.py` (see `logs/experiment_C_console.log`); the current source imports
  `common as C` (`global_optimizer.py:22`) so a re-run does not crash. `summary_C.json`
  documents that summary/history were reconstructed from the per-sweep checkpoints.

### 1.3 Checkpoints / resume

* **No resume mechanism exists.** Grep across `native3d/*.py` for
  `--resume/--checkpoint/--from-checkpoint` returns nothing.
* C writes one route payload per sweep — `checkpoints/c{1,2,3}_{stage}_sweep_NN_routes_l3d.json`
  (`global_optimizer.py:263-281`; archived: `c1_top10_sweep_01`, `c2_top50_sweep_01`,
  `c3_all_sweep_01`, `c3_all_sweep_02`) — but never reads them; they are audit artifacts
  only. A/B write no checkpoints. The root `.../checkpoints/` dir is empty.
* Practical consequence for 20H: "resume" means re-running the stage with the same flags;
  to snapshot a legal state, copy `experiment_C/routes_l3d.json` (or use Phase-2
  `save_best_valid`, `phase2.py:127-149`).
* A cheap 20H smoke sequence: A0 is a pure in-memory test (`run_a.py:69-180`, 11 tests),
  and `global_optimizer` C1 only processes 10 routes / 40 s — run those before the full C.

---

## 2. Module-by-module (inputs → outputs → callees)

| module | what it does | inputs | outputs | calls |
|---|---|---|---|---|
| `run_a.py` (403 L) | A0 geometry unit tests; A1 scan of the highest-crossing movable routes; A2 applies the single best excursion and recounts exactly; saves experiment A | A0 in-memory; A1/A2 load E5 routes via `N.load_routes()` (`:386`) / `N.load_assignment`; model from `reheight21.model` | `experiment_A/a0_geometry_tests.json` (schema `native3d_experiment_a0_v1`, 11 tests), `a1_scan.json` (`..._a1_scan_v1`, routes_scanned/attempts/per_route_best/reasons), `a2_single_route_result.json` (`..._a2_v1`, accepted[] + changes[][before/after route]), `experiment_A/routes_l3d.json` (`native3d_routes_l3d_v1`), `summary.json`, copies of assignment/layer_planes/process_rules/physical_layer_stack | `single_route`, `route_model`, `transition`, `crossing_cache`, `common`, `l3d.world.World`, `fsd25d.path3d` |
| `run_b.py` (213 L) | B0 strategy comparison on a sample (4 strategies), then a batch run with the winning strategy, exact recount per accepted change, final full validate + min clearance | E5 routes (`:22-25`); strategy list `batch_avoid.STRATEGIES` | `experiment_B/strategy_{B1..B4}.json`, `strategy_comparison.json`, `batch_result.json`, `candidates.json`, `failed_attempts.json`, `excursion_statistics.json`, `routes_l3d.json`, `crossing_stats.json`, `summary.json`, model copies | `batch_avoid`, `guard`, `single_route`, `crossing_cache`, `nonc4.crossings` |
| `global_optimizer.py` (405 L) | C: from E5, 3 stages C1_top10 (1 sweep) / C2_top50 (1) / C3_all (≤3 sweeps, 577 routes), greedy per-route excursion plans, accept only exact global decrease, re-validate each new best, snapshot best legal layout | E5 routes (`:34-37`); stage table `:309-313` | `experiment_C/routes_l3d.json`, `crossing_stats.json`, `transition_stats.json`, `failed_attempts.json` (reasons per sweep), `optimization_history.csv`, `summary.json`, checkpoints, model copies; root copies by `final_deliverables` | `batch_avoid.route_plan`, `guard`, `single_route`, `crossing_cache`, `nonc4.crossings` |
| `phase2.py` (293 L) | Phase-2 (D/E/F) shared plumbing: paths, baseline loading, payload builder (schema `native3d_phase2_routes_l3d_v1`), `save_experiment`/`save_best_valid`, crossing report, transition stats, **`derive_excursions`/`reconcile_route`** (rebuild `excursions` bookkeeping from the real parts chain) | Phase-1 accepted layout: `PHASE1_RUN_DIR/routes_l3d.json` (`:55-58`), model files in `PHASE1_RUN_DIR`/`PHASE1_DIR`/`N.E5_DIR` (`:61-72`) | Phase-2 dir tree (`RUN2`), `experiment_X/routes_l3d.json`, `crossing_stats.json`, `best_valid/{routes,validation,config}.json`, `transition_stats.json` (`native3d_phase2_transition_stats_v1`) | `common`, `guard`, `nonc4.crossings`, `crossing_cache` |
| `single_route.py` (349 L) | core candidate machinery: body-chain selection, crossing→arc-length projection, clustering (10 mm), `(s0,s1)` candidate generation, shadow-window screening, 3D world helpers, `evaluate_candidate` (structure→metadata→fast D56 delta→exact 3D world), `scan_route` enumeration | route set/events (`crossing_cache`), model tables via `common` | no files; returns candidate dicts (`s0,s1,footprint_mm,middle_mm,delta,feasible,reasons,cluster_*,route`) | `route_model` (`duck_out`), `transition` (`transition_footprint`, `same_straight_run`), `crossing_cache`, `l3d.world` |
| `route_model.py` (320 L) | route construction & checks: `make_flat`, `tag_parts` (lead/fanout/body/mid), `duck_out` (insert one excursion), `build_multi_excursion`, `structure_errors`, `route_metadata_errors`, `world_parts_consistent` | route records + primitives; model heights via `common` | no files; new route records with `parts`/`excursions`/rebuilt metadata | `transition`, `common`, `l3d.world.World.check_structure`, `fsd25d.path3d` |
| `transition.py` (169 L) | exact mid-body geometry: footprint/theta, `make_s_curve` (delegates to `fsd25d.path3d.make_transition`), path helpers, `same_straight_run`, `split_chain`, `build_excursion` (up/middle/down + prefix/suffix) | flat-body primitive list + `(s0,s1,z0,z1)` | part dicts for the excursion | `fsd25d.path3d`, `common` |
| `batch_avoid.py` (350 L) | strategies B1–B4, target-plane enumeration (adjacent vs all), cluster merging, fast per-plane D56 delta, ranked guarded options, greedy multi-excursion `route_plan`, per-route batch loop, excursion statistics | route set + crossing events + `single_route` primitives | plan dict (`new_route`, `excursions`, `predicted_delta`) or `None`; B strategy comparison | `single_route`, `guard.candidate_guard`, `crossing_cache`, `route_model`, `transition` |
| `guard.py` (186 L) | legality gates: bbox cache, local true-3D check against nearby routes, full-plane strict D56 check, cross-plane pitch check, `candidate_guard` pipeline, whole-layout `full_validate`, independent `measure_min_clearance` (reuses `validate21`), `route_radius_audit` | route records / route sets | gate dicts / violation lists / clearance payloads | `route_model`, `common`, `l3d.world`, `reheight21.validate21` (`V21.check_radius`, `measure_min_3d_clearance`) |
| `joint_reroute.py` (335 L) | Phase-2 experiment D engine: iterative blocker discovery for a target excursion candidate, manual-blocker rejection, per-blocker make-way excursion (`excursion2.insert_excursion_general`), transactional re-validation against all other routes, exact global recount acceptance | current layout (`NativeRouteSet`), bbox cache, target candidate, manual set | report dict (`blockers`, `joint_routes`, `before/after_total`, `net`, `accepted`, changed `routes`) | `excursion2`, `guard`, `single_route`, `crossing_cache`, `l3d.world` |

Supporting modules used by the above: `common.py` (tables/loaders/part helpers/metadata
rebuild), `crossing_cache.py` (`CrossingCache`, `PlaneIndexCache`, `NativeRouteSet`),
`excursion2.py` (arc-spanning excursions + staircases, used by D/E/F), `crossing_intervals.py`,
`blocker_analysis.py`, `visualize.py`, `validate_native3d.py`,
`final_deliverables.py`, `finalize_phase2.py`, `arc_crossing_analysis.py`.

---

## 3. Generic vs hardcoded-21H

### 3.1 Model-derived (generic, follows `M` automatically once the 20H model is installed)

* `native3d/common.py:41-43` `PLANE_Z/Z_PLANE/PLANE_LABEL` ← `M.PLANE_IDS`/`M.plane_z`/
  `M.plane_label`; `:39` `MANUAL_PLANES` ← `M.MANUAL_PLANE_IDS`; `:61-73` `movable_heights`,
  `all_heights`, `sorted_by_abs_dz`; `:186-252` `rebuild_route_metadata` (uses `plane_of_z`);
  `:46-54` `plane_of_z` (only the error strings say "21").
* `transition.py` (whole file), `route_model.py:45-53/57-181` (only `:50` message and `:221`
  interface tuple are 21H-specific), `excursion2.py` (only messages), `crossing_cache.py`,
  `single_route.py:186-201` (iterates `N.MOVABLE_PLANES`; the `0.05` at `:198` is the pitch,
  unchanged), `guard.py` (model stack via `M.layer_stack()`), `batch_avoid.py:41-48`
  (adjacency via `abs(dz)-0.05`, unchanged), `joint_reroute.py` (all target heights via
  `N.sorted_by_abs_dz`), `visualize.py:106-134` (height table from `N.PLANE_Z`),
  `tests_native3d/synthetic_native3d.py:31-35` (heights from `V._model_planes()`),
  `validate_native3d.py:340-426` (model helpers, transition formula).

### 3.2 21H-hardcoded — per requested constant, with classification

| constant | where | feeds search? | 20H action |
|---|---|---|---|
| `PLANE_Z`, `MANUAL_PLANES` | `common.py:39-43` | yes (derived) | nothing — follows model20 |
| `MOVABLE_PLANES` | `common.py:38` | **yes** — target-plane enumeration (`single_route.py:294`), shadow planes (`:186`), D/E target order (`joint_reroute.py:182-184`), arc analysis (`arc_crossing_analysis.py:99`) | drop 19 / derive from model (table row #4) |
| `RUN_DIR` | `common.py:23` | write root for A/B/C (not the search itself) | re-point (row #3) |
| `BASELINE_21H_DIR` | `common.py:21` | no (nothing reads it) | irrelevant |
| `E5_DIR` | `common.py:19` | **yes** — it is the route set every search starts from (`load_routes`), plus traceability strings `parent_experiment` (`run_a.py:331`) | re-point to the 20H accepted legal baseline (row #2) |
| `phase2.BASELINE_CROSSINGS = 2440` | `phase2.py:25` | **yes, gate**: `run_d.py:239`, `run_e.py:416` only save `best_valid` when `total < 2440`; also `summary.start_crossings` (`run_e.py:408`) and D summary (`run_d.py:226`) | read the 20H Phase-1 final total at runtime (row #10) |
| `run_a.py:309 baseline_crossings=2606` | A2 payload | **no** — exact delta is `after_total - before_total` (`run_a.py:296-298`) | derive from `env.accepted_crossings` captured before A2 |
| `run_b.py:153 baseline_total=2606`, `:197 baseline_crossings=2606` | B comparison/summary JSON | **no** — `exact_delta` from env recounts (`batch_avoid.py:304-313`) | derive from the initial `env.total()` |
| `global_optimizer.py:372 start_total=2606` | C summary JSON | **no** — acceptance uses `after_total < before_total` (`global_optimizer.py:221-235`) | derive from initial `env.total()` |
| `finalize_phase2.py` `or 2440` (lines 189,254-255,590,619,621,639) + prose | report/summary builders | **no** — only report/summary numbers; the `or` fallbacks fire when Phase-1 summary keys are absent | read `start_total` from the 20H Phase-1 summary (or crossing_stats) |
| `final_deliverables.py` 2606 literals (145,181,187,229,234,242,276,370,379,397) | report/comparison/README templates + `_max_route_crossing` | **no** — pure reporting (writes `report.md`, `comparison.md`, `README.md`, `MANIFEST.json`, archives code) | derive numbers from artifacts; re-point `RUN`/`E5` (`:16-17`) |
| `arc_crossing_analysis.py` `events=2606` (`:84`) | `PREVIOUS_CLAIM` quoted-claim dict | **no** — the analysis recomputes events from the baseline it is given (`--baseline` required, `:2721`) | update/delete quoted claim; `PLAUSIBLE_PLANE_IDS` follows `MOVABLE_PLANES` |
| `validate_native3d.E5_EXPECT` (`:145-163`) | regression block only | **no** (regression is a post-hoc assertion, not a gate on the run; exit code 2 if mismatched) | replace with 20H expectation block (row #13) |

**Bottom line for question 3:** of the numbers you listed, only `phase2.BASELINE_CROSSINGS`
and `MOVABLE_PLANES` actually feed decision logic; `2606` in run_a/run_b/global_optimizer is
reply-only bookkeeping; `finalize_phase2`/`final_deliverables`/`arc_crossing_analysis`
literals are report/analysis only. `MAX_MIDDLE_MM = 120` (`common.py:34`) is **advisory
only** — `route_model.duck_out(..., max_middle=None)` (`route_model.py:57-58,75-76`) never
passes it; only `crossing_intervals.py` (its own `DEFAULT_MAX_MIDDLE_MM`, `:78`) reports it.

---

## 4. `validate_native3d.py` — checks and hardcoded expectations

### 4.1 Checks (independent of the builder; re-derives everything from `parts`)

Docstring contract `:36-63`; pipeline `validate_run` `:2459-2795`:

0. **model** (`:2546-2548`): `check_model` → `V21.check_model` against the frozen SPEC
   tables (`validate21.py:88-94` now read `M.SPEC_*` after the profile patch); plane ids,
   heights, pitch, interface rows.
1. **coverage / identity** (`check_coverage`, `:702-799`): route id set vs baseline,
   duplicates, `route_count`, routed==expected, no failed, identity fields
   `(source_endpoint,target_endpoint,plane,source_row,target_row)` (`:692-693`), plane
   counts, assignment rows identity.
2. **structure** (`check_structure`, `:956-1122`): alternating `flat/transition` chain,
   leaf flat/transition checks via `V21._check_flat_part`/`_check_transition`, junction
   position/z/tangent continuity, lead flats at interface z + layer id accepted
   `{1, 1001/1002}`, fanout transitions start/end at the interface z, direct-route checks,
   port poses/headings (`:845-913`), tag convention `lead/body/fanout/mid` (`:916-953`),
   `World.check_structure`.
3. **native metadata** (`check_native_metadata`, `:1172-1509`): every flat z must be one of
   the model heights (`:1181-1189`), 50 µm min pitch within a route (`:1191-1200`),
   `n_transitions`, `layer_sequence`, `layer_z_sequence`, `layers_used`, `length_mm`,
   `xy_length_mm`, primary `target_layer`, `target_plane`, `target_z_mm`, `body_heights`,
   `mid_transitions`, excursions pairing (up/flat/down z-consistency, `:500-538`),
   `start_z_mm`/`end_z_mm` vs interface z, `lifted`.
4. **R15** (`check_radius`, `:1542-1575`, mostly `V21.check_radius`): every flat arc exactly
   15 mm; transition true-3D curvature radius sampled ≥ 15−1e-6; also transitions counted.
5. **glass** (`check_glass`, `:1577-1617` via `V21.check_glass`): x,y ∈ [0,150], z ∈
   [−0.35, 0.65], edge margin report.
6. **true-3D clearance** (`check_clearance`, `:1619-1665`): fresh `World(model stack, 0.05)`,
   routes added in id order with `check_route(check_self=True)`, plus independent minimum
   clearance scan (`V21.measure_min_3d_clearance`, lower bound 0.05).
7. **ports** (`check_ports`, `:1667-1676`, `V21.check_ports`).
8. **crossings** (`check_crossings`, `:1678-1688`): strict same-physical-z D56 audit over
   all flat parts (interface leads included), totals/pairs/per-plane/per-route; the
   `audited_heights` field comes from here (one entry per physical z with parts).
9. **manual contract** (`check_manual_contract`, `:1706-2153`): default `frozen` = the 368
   manual-U routes must be json-identical to the baseline (`MANUAL_FROZEN_FIELDS`
   `:1708-1713`; alternatives `height_only`/`fully_optimizable`, `:2116-2153`).
10. **synthetic consistency suite** (`tests_native3d/synthetic_native3d.py`): duck-out
    accepted; 49 µm offset, R=14, 1e-3 break, flat overlap rejected; boundary cases.
11. **E5 regression block** (`_regression_block`, `:2170-2238`) only with `--regression`;
    exit code 2 on mismatch.

Geometry vs contract split: `GEOMETRY_CHECKS = ('structure','native_metadata','radius',
'glass','clearance','crossings')` and `CONTRACT_CHECKS = ('coverage','ports','manual_frozen',
'model','synthetic')` (`:2334-2337`); `validation_pass = geometry_pass and contract_pass`
(`:2680-2688`).

### 4.2 Every hardcoded expectation, classified

**(a) Configuration values that must be re-pointed for 20H:**

| line | value | note |
|---|---|---|
| `:127` | `RUN_ROOT = OUTPUT_ROOT/'NATIVE_3D_CROSSING_OPT_1024'` | 20H Phase-1 run root |
| `:128` | `DEFAULT_BASELINE = .../E5_joint_repair_final` | 20H accepted legal baseline |
| `:145-163` | `E5_EXPECT`: `routed=1024`, `failed=0`, `direct_routes=98`, `non_direct_routes=926`, `transitions=1852`, `flat_arc_count=1596`, `same_plane_crossings=2606`, `same_plane_crossing_pairs=2067`, `same_plane_crossing_violations=0`, **`audited_heights=21`**, `manual_routes=368`, `manual_geometry_mismatch_count=0`, `min_3d_clearance_mm=0.068714895`, `min_3d_clearance_tol=1e-6`, `total_length_mm=157565.774342258`, `total_length_tol=1e-3`, `violation_total=0` | regression mode only. For 20H, `audited_heights` must be 20 and the counts must be frozen from the 20H accepted baseline (20H contract predicts direct 100 / non-direct 924 / endpoint transitions 1848 — see `coldstart20/model20.py:312-314`; E5's 98/926/1852 is the legacy 18-layer assignment and must never be copied). `min_3d_clearance`/`total_length` are measurements of the actual 20H baseline, tolerance constants stay. |
| `:735,760-765` | `routed_count_not_1024`, `plane_z1/z2_count_not_512` | contract expectations vs the baseline route set; 1024 connections are unchanged, and direct routes are 52+48 in both profiles, so these likely remain 1024/512/512 — but they must be re-verified against the 20H `assignment_1024.csv` rather than assumed |
| `:140` | `INTERFACE_PLANE_BY_NAME = {'z1': 1001, 'z2': 1002}` | plane ids unchanged; heights are read from the run's `layer_planes.json` (`_load_model`, `:629-660`) — no numeric change needed |
| `:1690-1702` | `_baseline_crossing_totals` reads `<baseline>/crossing_stats.json` | 20H baseline dir must carry the 20H crossing stats |
| `:1706-1713` + baseline arg | manual-U frozen contract (368 routes) | re-point `--baseline-dir`; with 20H the manual routes' z are +0.025, so a 21H baseline would produce 368 mismatch violations |
| `:2260-2274` | default `out_dir` under `RUN_ROOT` | follows `:127` |
| `:2801-2824` | CLI defaults (`run_dir`=RUN_ROOT, `baseline_dir`=DEFAULT_BASELINE) | follows the above |

**(b) Geometry/threshold values that must remain bit-identical (no change, no relaxation):**

`:130 R15_MM=15.0`; `:131 MIN_3D_CLEARANCE_MM=0.05`; `:132 MIN_LAYER_PITCH_MM=0.05`;
`:133-138` `TOL_POS_MM=1e-6`, `TOL_Z_MM=1e-6`, `TOL_TANGENT=1e-6`, `TOL_RADIUS_MM=1e-6`,
`TOL_LEN_MM=1e-5`, `TOL_MODEL_Z_MM=1e-9`; `:139 LEGACY_INTERFACE_LAYER_ID=1`;
`:407-426` S-curve formula `length=2R·θ`, `footprint=2R·sinθ`, `θ=acos(1−dz/2R)`;
`:141-142` JSON truncation limits; `:122-124` validator id/schema strings (cosmetic).
Also the *semantics* of checks 2–10 must stay identical; 20H only changes the plane table
and the two interface heights that the checks read from the model / baseline.

**(c) 20H prerequisites outside this file (verified in the tree):**
`coldstart20.bootstrap` must be imported before `validate_native3d` (its module-level
`from ..reheight21 import model as M` / `validate21 as V21`, `:114-115`); `check_clearance`
builds the world stack through `V21.build_model_stack` (`validate21.py:407-413`), which after
the profile patch uses `M` and the patched `l3d.layers.INTERFACE_ROWS`; `l3d/layers.py:245-278`
now accepts per-stack `interface_rows` and `:122-159` no longer requires contiguous routing
ids, so a 20H stack validates. Port physical z is the remaining cross-cutting question
(row #24: `fslw/config.py:50`).

---

## 5. `visualize.py` — figures, per-height count, height-table source

* Height table is **model-driven, not hardcoded**: `HEIGHT_ROWS = tuple(sorted((
  pid, z, N.PLANE_LABEL[pid], H.plane_kind(pid)) for pid, z in N.PLANE_Z.items()),
  key=(z, pid))` (`:129-134`); `Z_MIN/Z_MAX` from `N.PLANE_Z` (`:106-107`);
  `INTERFACE_Z` from `H.interface_z('z1'/'z2')` (`:123`). `H` is `reheight21.model`
  (`:82`) → with model20 installed these are the 20 heights, sorted physically
  (L2 −0.325 … L18 +0.625, Z1 +0.025, Z2 +0.525).
* `plot_height_panels` (`:1646-1725`) iterates `HEIGHT_ROWS` → **one figure per plane**,
  `height_%02d_<label>.png` (order = physical z, so removing L19 renumbers the last
  panels; `L18` becomes `height_20`, no `L19` panel). Archived 21H dashboard:
  `plots_manifest.json` `figure_count=29` = 21 height panels + 8 fixed figures.
* Fixed figures of the C dashboard (`plot_experiment_c_dashboard`, `:2422-2487`):
  `3d_overview_1024.png`, `crossing_curve.png`, `per_layer_before_after.png`,
  `top10_routes_before_after.png`, `mid_transition_counts.png`,
  `extra_length_distribution.png`, `crossing_hotspot.png`,
  `route_height_profile_examples.png`.
* Other APIs: `plot_route_3d`, `plot_route_2d_projections` (one XY panel per height the
  route occupies, `:916-1021`), `plot_transition_zoom`, `plot_crossing_profile`,
  `plot_experiment_b_summary`, `plot_experiment_a_dashboard`,
  `plot_experiment_b_dashboard`, `plot_baseline_demo` (also 20 panels once model20 is
  installed), `plot_all_experiments`; CLI `:3222-3305`.
* Hardcoded 21H content is cosmetic only: docstrings/log text "21 heights" (`:32,1648`,
  "all 21 real routing heights" `:1990`, `:3111`, `:3238`). Defaults `--baseline-dir` =
  `N.E5_DIR` (`:3233,3257`) and `--run-dir` = `N.RUN_DIR` (`:3269`) follow the re-pointed
  constants. `3d_overview_1024.png` filename stays (route count 1024 unchanged).
  Also `plot_experiment_c_dashboard` reads `crossing_stats.json` + `optimization_history.csv`
  + `checkpoints/best_routes_l3d.json` (optional) (`:2433-2460`) — all still produced.

---

## 6. Mid-body excursion mechanism (changes for 20H: only the plane table)

**Insertion function:** `route_model.duck_out(route, body_part_index, s0, s1, z_to, radius=15,
max_middle=None)` (`route_model.py:57-109`); multi-excursion variant
`build_multi_excursion` (`:113-181`); Phase-2 arc-spanning variant
`excursion2.insert_excursion_general` (`excursion2.py:116-162`).

**Geometry path:** `duck_out` → `transition.build_excursion` (`transition.py:101-160`) →
`fsd25d.path3d.make_transition` (`path3d.py:174-189`), i.e. an exact pair of R=15 mm circular
arcs (double-arc S) with tangent continuity at both ends and exact landing on the original
straight path. Part chain inserted: `prefix(flat,z0) | up(transition,z0→z1) |
middle(flat,z1) | down(transition,z1→z0) | suffix(flat,z0)`; tags `body / mid / body / mid /
body`; then `rebuild_route_metadata` + `tag_parts` (`route_model.py:80-109`).

**R15 footprint formula** (`transition.py:15-24`; identical in `path3d`/validator):
`θ = acos(1 − |dz|/(2R))`, horizontal footprint `= 2R·sinθ`, S length `= 2R·θ`.
Pitch-limited cases: dz = 0.05 → footprint **1.731329 mm**, length 1.732233 mm;
dz = 0.10 → 2.449490 mm; dz = 0.15 → 2.996247 mm (the archived A2 route 496, `report.md:12`).
Footprint depends **only** on dz and R, so 20H keeps the 50 µm-pitch numbers identical.

**Legality window rules:**

1. `SHADOW_MM = sqrt(2·R15·MIN_3D_CLEARANCE) = sqrt(2·15·0.05) = 1.2247449 mm`
   (`common.py:26-30`): horizontal distance over which the S-curve is still within 50 µm of
   the plane it leaves/lands on. `single_route.shadow_report` (`:165-215`) requires **zero**
   same-plane D56 crossings of other routes under the footprint on: source plane, target
   plane, every routing height strictly between them, and the planes exactly one 50 µm pitch
   beyond each end (`:186-201`; the `0.05` at `:198` is the pitch and stays).
2. `MIN_MIDDLE_MM = 1.0 mm` (`common.py:32`) minimum flat length at the travel height:
   `middle = (s1−s0) − 2·footprint ≥ 1.0` (`transition.py:124-128`); enforced in
   `build_excursion`, `build_multi_excursion` (≥0.5 mm separation) and candidates
   (`single_route.interval_candidates`, `:109-162`).
3. `MAX_MIDDLE_MM = 120.0 mm` (`common.py:34`) is **advisory only** — `duck_out` passes
   `max_middle=None` (`route_model.py:58,76`), so the search never enforces it;
   `crossing_intervals.py` has its own `DEFAULT_MAX_MIDDLE_MM=120` for ranking.
4. Candidate window construction (`single_route.interval_candidates:118-136`):
   `extra = footprint + SHADOW_MM + 0.5` (end margin) around the crossing cluster, plus
   variants +1.5/+3.0/+6.0 mm, symmetric growth when the cluster is shorter than
   `2·footprint+middle`, and `0.5 mm < s0 < s1 < body_length−0.5`; the whole interval must
   lie in **one straight primitive** (`transition.same_straight_run`, `:67-75`).
5. Final gate before acceptance: `guard.candidate_guard` (`guard.py:115-134`) =
   structure → metadata → cross-plane layer pitch (`forbidden_cross_plane`, `:104-112`) →
   full-plane strict D56 (`ensure_flat_d56`, `:91-101`) → local true-3D World vs nearby
   routes (`local_world_check`, `:69-88`); then the caller re-counts exactly.

**What changes for 20H:** only the plane table used for the "which heights may be targeted /
which heights lie between / which planes are one pitch beyond" logic — i.e.
`M.PLANE_IDS` − manual planes (`MOVABLE_PLANES`, table row #4), `all_heights()` (shadow
`up_beyond` planes, `single_route.py:193-201`), and interface heights for the lead ends
(`route_model.py:221`, `model20` 0.025/0.525). `SHADOW_MM`, `MIN_MIDDLE_MM`, `R15`, the
0.05 pitch, the footprint/theta formulas and the 0.5 mm margins are **unchanged**.
Sanity: adjacent-dz footprint stays 1.731329 mm; max reachable |dz| in 20H is 0.95 mm
(L2 ↔ L18), still far below 2R = 30 mm.

---

## 7. Downstream artifact contracts that must be preserved

### 7.1 `routes_l3d.json` (written by A/B/C, read by Phase-2 D/E/F, G123, G4, validators)

Payload schema (actual archived C payload):
`schema='native3d_routes_l3d_v1'`, `experiment`, `parent_experiment`,
`native_3d{model,routes_with_mid_transitions,mid_transitions,geometry,note,total_crossings}`,
`route_count=1024`, `routed=1024`, `failed=0`, `routes[]`,
`crossing_definition`, plus the inherited baseline payload keys
(`algorithm, c4_binding, layer_model, layer_stack, manual_geometry, process, process_mode,
topology, joint_repair_history`). Phase 2 re-wraps it as
`native3d_phase2_routes_l3d_v1` (`phase2.py:76-104`).

Per-route fields that downstream code actually consumes:

* identity/contract: `route_id`, `plane`, `source_endpoint`, `target_endpoint`,
  `source_row`, `target_row`, `manual_group`, `relation`, `direct`, `needs_transition`;
* geometry/structure: `parts` (see 7.2), `n_transitions`, `start_z_mm`, `end_z_mm`,
  `length_mm`, `xy_length_mm`, `z_span_mm`, `lifted`;
* native bookkeeping: `native_3d`, `n_mid_transitions`, `mid_transitions[{part_index,
  from_z,to_z,tag}]`, `body_heights`, `excursions[]` (7.3), `layer_sequence`,
  `layer_z_sequence`, `layers_used`, `target_layer`, `target_plane`,
  `target_plane_label`, `target_z_mm`, `layer_role`.

Who reads what:
* Phase 2: `payload['routes']` + per-route parts/metadata (`phase2.py:55-58`), excursions
  rebuilt from parts (`derive_excursions`, `:209-266`), payload base copied (`:76-104`).
* G123: `xyzrouter/paths.py:122-131` `load_baseline` uses `payload['routes']` + the
  `assignment_1024.csv` rows (identity fields, sha256 for fingerprinting).
* G4: `xyzrouter/g4/paths.py:139-152` `load_start` = same payload + assignment
  (but with a frozen `routes_sha256` and `START_CROSSINGS=1322`, `:27-29` — must be
  re-fingerprinted for 20H).
* Validators: everything is re-derived from `parts`/tags; coverage/identity compares to
  the baseline payload.

### 7.2 `parts[]` contract

* `flat`: `{kind:'flat', tag:'lead'|'body', z_mm, layer_id, length_mm,
  primitives:[{kind:'line',p0,p1} | {kind:'arc',center,radius,sweep,...}]}` —
  interface lead flats are at the model interface z with `layer_id` 1 (or 1001/1002).
* `transition`: `{kind:'transition', tag:'fanout'|'mid', start[2], end[2], direction[2],
  z0, z1, dz_mm, radius_mm=15, footprint_mm, theta_rad, length_mm}`.
* Tag convention is **load-bearing**: first/last flat = `lead`, other flats = `body`;
  first/last transition = `fanout`, inner transitions = `mid` (`route_model.tag_parts
  :15-42`; validator `_check_part_tags` `validate_native3d.py:916-953`).
  `phase2.derive_excursions` recognizes excursions *only* as consecutive
  `flat/transition(mid)/flat/transition(mid)/flat` with matching z (`phase2.py:220-266`);
  `global_optimizer.transition_stats` and the validator's `recompute_route` rely on the
  same tags.

### 7.3 `excursions[]` records

Fields written by `duck_out` (`route_model.py:92-102`):
`s_start_mm, s_end_mm, from_z, to_z, from_plane, to_plane, up_part_index,
middle_part_index, down_part_index, prefix_part_index, suffix_part_index, footprint_mm,
middle_mm, direction[2], body_part_index`; Phase-2 variants add
`contains_arc, kind('excursion'|'arc_span'|'staircase'), n_steps, step_mm`
(`excursion2.py:142-154,318-334`; `phase2.py:239-261`).
`report.md` §8.2 notes `s_start_mm/s_end_mm` are **not** strictly validated (frame
ambiguity) — geometry is re-derived from parts; still, keep the fields because
`transition_stats` (7.4) and `phase2.derive_excursions` copy them.

### 7.4 `transition_stats.json` (root + experiment_C; also Phase-2 root)

Schema `native3d_transition_stats_v1` (`global_optimizer.py:94-121`; Phase-2:
`native3d_phase2_transition_stats_v1`, `phase2.py:181-205`):
`routes_with_mid_transitions, mid_transitions, excursions, by_from_height{'%+.3f': count},
total_footprint_mm, per_route{rid:[{from_z,to_z,footprint_mm,middle_mm,s_start_mm,
s_end_mm(,kind)}]}`. Consumers: reports/figures and the G-stage report tooling; no search
gate depends on it (it is derived from the final routes).

### 7.5 `crossing_stats.json` and other required companions

`crossing_stats.json` (schema `nonc4_crossing_stats_v1`) produced by
`nonc4.crossings.crossing_report`: `totals{crossings,crossing_pairs,violations,
audited_heights,planes_with_crossings,per_route_distribution,min_non_crossing_centerline_mm}`,
`planes[]`, `per_route_crossings`, `crossing_events[]` with
`{route_a,route_b,plane_id,plane_label,z_mm,x_mm,y_mm,angle_deg,manual_a,manual_b,
direct_a,direct_b}`. Consumers: validator baseline-delta (`validate_native3d.py:1690-1702`),
visualize (`:2433-2460`), Phase-2 best_valid copy, reports.

Also required next to `routes_l3d.json` in every run/baseline dir:
`assignment_1024.csv` (identity/contract + G123/G4 fingerprints; columns used:
`route_id, plane, source_endpoint, target_endpoint, source_row, target_row,
manual_group, target_layer`), and the model files
`layer_planes.json` (validator model source, `validate_native3d._load_model:629-660`),
`process_rules.json`, `physical_layer_stack.json` — A/B/C copy all four from `N.E5_DIR`
(`run_a.py:343-347`, `run_b.py:181-185`, `global_optimizer.py:390-394`).

**Schema fields that must be preserved for the 20H rebuild:** the whole set above, in
particular `parts` kinds/tags/fields, `n_transitions`/`n_mid_transitions`/`mid_transitions`,
`body_heights`, `excursions` indices + z fields, `layer_sequence/layer_z_sequence/
layers_used`, `target_layer/target_plane/target_z_mm`, `length_mm/xy_length_mm/z_span_mm`,
identity fields, and the per-height crossing event schema. Only *values* (heights, plane
ids, counts) change; names/shapes must not.

---

## 8. Wall-clock cost of A / B / C (from archived logs)

| stage | measured wall clock | composition |
|---|---|---|
| A | **≈22 s** (23:55:50.8 → 23:56:12.5) | cache build 1.5 s; A0 11 tests <1 s; A1 12 routes / 142 attempts ≈21 s; A2 1 change ≈1 s; save ≈1 s |
| B | **≈82 s** for the archived accepted invocation (00:08:52 → 00:10:14) | 4 strategies × 30 routes ≈31 s (7.2–8.1 s each); batch of 80 routes with 14 accepted ≈21 s; full validation 15.3 s; min-clearance scan 2.3 s; model copies/reads/JSON ≈4 s. The `experiment_B.log` file spans 11 min 36 s (23:58:38→00:10:14) because B was invoked 6 times (triage runs, two validation-failed attempts, aborted runs) |
| C | **≈449 s (7 m 29 s)** (00:10:49 → 00:18:18) | cache 1.5 s; C1 6.2 s + per-new-best validation ≈16 s; C2 11.7 s + ≈16 s; C3 sweeps 165.5 + 96.4 + 87.2 s + 3 validations ≈16 s each; final full validation 15.9 s; min-clearance 2.5 s; JSON/CSV writes and snapshots ≈5 s. The run then crashed on the history CSV write (old code); recording/validation ~30–60 s extra |
| validator | 18.5–22.3 s per run (`validation.json: runtime_seconds`: A 18.74, B 18.54, C 22.10, root 19.06/22.34) | full 1024-route fresh world + min-clearance scan |
| crossing-interval analysis | ≈60 s (deterministic, `report.md:151`) | 2606 events → 5212 associations → 1154 clusters → 14 480 candidates |

20H estimate: same order of magnitude. One fewer plane slightly reduces per-plane work;
C's cost is dominated by `D56` per-plane evaluations and the exact 3D guard, so budget
A ≈25 s, B ≈1.5 min, C ≈8–10 min, validator ≈20 s per run. Total Phase-1 (A+B+C+4 validators)
≈12–15 min single-process on this machine — cheap enough to iterate after the first smoke
test.

---

## 9. Ordered adaptation checklist for the 20H Phase-1 run

1. **Prereq / ordering:** every 20H driver must execute
   `from four_side_1024.fanout1024.coldstart20 import bootstrap` (installs on import,
   `bootstrap.py:148-162`) **before** importing any `native3d`, `reheight21`,
   `l3d` or `xyzrouter` module; then assert
   `bootstrap.assert_20_height_profile('native3d')`. `python -m ...native3d.run_a` cannot be
   used unchanged for this reason — add a tiny `coldstart20/run_native3d_phase1.py` launcher
   (import bootstrap, import native3d modules, call `main()`), or have the drivers import it
   first.
2. **Resolve the port-z question first** (row #24): decide whether the physical port rows
   move to +0.025/+0.525 (`fslw/config.py:50 PLANE_Z_MM`); otherwise the 20H validator's
   port-height checks (`validate_native3d.py:874-880,904-910`) and any port-identity audit
   will fail regardless of the routing code.
3. **Patch `native3d/common.py`** (rows #2–#4): `E5_DIR` → 20H accepted legal baseline
   (stage 04), `RUN_DIR` → `.../05_native3d_abc/<run>`, `MOVABLE_PLANES` derived from the
   model minus `M.MANUAL_PLANE_IDS`; keep every geometry constant unchanged. Optionally add
   env-var overrides (`NATIVE3D_INPUT_DIR` / `NATIVE3D_RUN_DIR`) so no source edit is needed
   per run, and an assert that the loaded model is the 20H profile.
4. **Patch `native3d/route_model.py:221`** interface heights to the model values.
5. **De-hardcode the report numbers** (rows #7–#9) to the initial exact total; no search
   logic depends on them, but the archived payloads/report would otherwise claim 2606.
6. **Fix the known candidate-rollback bug before reusing B/C:** `batch_avoid.run_strategy`
   calls `env.replace_route(env.routes[route_id])` as the "revert" (`batch_avoid.py:306-310`),
   which is a no-op because `replace_route` already updated `env.routes[route_id]`; the
   correct pattern is the `previous = copy.deepcopy(...)` revert used in
   `global_optimizer.run_stage` (`:208,233-235`). Also `global_optimizer.sweep()`
   (`:125-166`) is dead code (never called) with an odd `if False` line (`:159`).
7. **Validator for 20H:** re-point `RUN_ROOT`/`DEFAULT_BASELINE`; replace `E5_EXPECT` with a
   freshly frozen 20H `BASELINE_EXPECT` (audited_heights=20, counts/clearance/length from
   the 20H accepted baseline); re-point `--baseline-dir` (manual contract + identity);
   ensure the 20H baseline dir contains `crossing_stats.json`; keep all R15/0.05/pitch/tags
   constant. `--regression` must be used only against that new expectation block (the 21H
   2606 reproduction is meaningless in the 20H process).
8. **Smoke, then full run:** A0 (in-memory, 11 tests) → A `--skip-a1` → A full
   (`--top-routes 20` or 12 for comparability) → B `--sample 30 --batch 80` → C
   (C1 only first if desired) → validators for A/B/C/root → visualize/interval analysis.
   Expected smoke invariants: `PLANE_Z` has 20 entries and no plane 19;
   `crossing_stats.totals.audited_heights == 20`; 1024/1024 routed; 0 geometry violations;
   all transition radii exactly 15; min 3D clearance ≥ 0.05.
9. **Downstream (later phases, not this run):** `phase2.py` paths + `BASELINE_CROSSINGS`
   from the 20H Phase-1 summary (row #10/#11); `finalize_phase2.py` /
   `final_deliverables.py` derived numbers; G123 `xyzrouter/paths.py:16-23,114-131` and G4
   `xyzrouter/g4/paths.py:26-32,139-161` need new baseline dirs, new route SHA fingerprints
   and new start crossing counts; preserve the payload schema from §7.
10. **Do not touch (bit-identical):** `R15=15`, true-3D clearance 0.05, 50 µm pitch,
    strict D56, legal-crossing ≥5°, 150×150×1 mm glass, 1024 connections, 368 manual-U
    membership/plane ids, S-curve formulas, tolerances, all tag conventions.

### Appendix — quick evidence index

* README reproduction: `outputs/.../NATIVE_3D_CROSSING_OPT_1024/README.md:13-22`.
* Critical summaries: `report.md` (A: route 496 −5; B: 14 excursions −47; C: 118 mid
  transitions, 2440/2036, min clearance 0.06730354; §8 validator table), `summary_C.json`,
  `comparison.md`, `MANIFEST.json` (128 files), `transition_stats.json`,
  `experiment_B/excursion_statistics.json`, `experiment_B/strategy_comparison.json`.
* Archived per-experiment validator results: `validation/experiment_{A,B,C}/validation.json`
  (all `validation_pass=True, violations=0`; crossings 2601/2559/2440).
* Logs: `logs/experiment_A.log`, `experiment_B.log`, `experiment_B_console.log`,
  `experiment_C.log`, `experiment_C_console.log` (the B console shows the two failed
  validation attempts; the C console shows the post-run `C` NameError).
* 20H foundation present in the tree: `coldstart20/model20.py` (20 planes, interface
  +0.025/+0.525, contract tables, `layer_stack()` with per-stack rows),
  `coldstart20/bootstrap.py` (model swap + interface-height repoint + run-dir binding),
  `00_audit/patch_profile_generic.py` (21H tables → profile constants for
  assign21/run21/validate21/model), patched `l3d/layers.py` (`interface_rows`,
  non-contiguous routing ids).
