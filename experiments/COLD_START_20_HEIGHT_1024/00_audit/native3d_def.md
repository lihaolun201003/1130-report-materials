# Native-3D Phase 2 (D/E/F) — read-only audit for the 20-height rebuild

| | |
|---|---|
| Deliverable | `experiments/COLD_START_20_HEIGHT_1024/00_audit/native3d_def.md` |
| Audited code | `four_side_1024/fanout1024/native3d/` (D/E/F, Phase 2) |
| Audited run | `outputs/manual_c4_new_connectivity/NATIVE_3D_JOINT_OPT_1024/` (2409 crossings) |
| Project root | `C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D` |
| Python | `<root>\.venv\Scripts\python.exe` = Python 3.10.11 |
| Date of audit | 2026-11-17 (code mtimes: Phase-2 files 2026-11-04, `coldstart20` profile 2026-11-17) |
| Mode | READ-ONLY. No project file was modified. Only this Markdown was created. Evidence = file reads, JSON/CSV inspection, and cheap `--help` / import checks (no pipeline run). |

> **Scope note.** The task said “everything must be rebuilt for 20 heights”. During this audit it
> turned out that a 20-height profile **already exists in the working tree**:
> `four_side_1024/fanout1024/coldstart20/{model20.py,bootstrap.py,run_initial.py}` (written
> 2026-11-17 22:32–22:34, i.e. minutes before this audit). Therefore section 4 distinguishes
> *“must be adapted”* from *“already provided by `coldstart20`”*, and section 9 is written against
> the code as it is now, not against the historical 21-height state.

---

## 0. TL;DR (for the 20-height rebuild)

**What Phase 2 is.** Native-3D Phase 2 is a *post-processing optimiser* on top of an already-legal
multi-height Native-3D layout. It never re-routes from scratch; it only:
1. moves a short sub-path of one route from its body height `z_from` to another routing height `z_to`
   through two exact R15 S-curves (plain / arc-span), and
2. when the 3D World rejects that, also gives each movable blocking route its own make-way excursion
   (joint), and
3. accepts a change only if a *fresh exact world/clearance check* passes **and** the exact global
   strict-D56 crossing count strictly decreases; otherwise the whole transaction is rolled back.

**Historical result (2440 → 2409).** D: 14 joint attempts, 0 accepted. E: 36 arc-rebuild attempts,
0 accepted. F core: 2440 → 2436 (−4, `arc_span` route 497). F+ : 2436 → 2424 (7 accepts).
F+2 : 2424 → 2422 (1 accept). near-miss: 2422 → 2409 (1 accept, route 737 → z = +0.20, net −13).
Everything stayed legal: 1024/1024, 0 violations, min true-3D clearance 0.06730354 mm, 138 mid
transitions on 62 routes, independent validator PASS. Source: `summary.json`,
`logs/experiment_D.log:10-14`, `logs/experiment_F*.log`, `logs/experiment_F_nearmiss*.log`.

**The five things that must change for 20 heights**
1. `native3d/common.py:38` `MOVABLE_PLANES` is a **literal tuple that still contains deleted plane
   id 19**. Under the installed 20-height profile this already crashes: `N.sorted_by_abs_dz(0.0)`
   → `KeyError: 19` (reproduced, see Appendix D). It must be derived from the model
   (`tuple(pid for pid in PLANE_Z if pid not in MANUAL_PLANES)` → 12 planes; verified working).
2. `native3d/phase2.py:22-27` hard-codes `PHASE1_DIR / PHASE1_RUN_DIR / BASELINE_CROSSINGS = 2440 /
   RUN2` (all 21-height paths). The 20H run must read the 20H Native-3D Phase-1 accepted layout and
   write under `experiments/COLD_START_20_HEIGHT_1024/06_native3d_def`, with the baseline crossing
   count read from that layout’s `crossing_stats.json` (it will **not** be 2440).
3. The candidate pool feeding D (`run_d.py:41` → `<PHASE1_DIR>/analysis/crossing_intervals.json`)
   does not exist for 20H and must be regenerated against the 20H pre-native baseline
   (`crossing_intervals`). `blocker_analysis` similarly reads
   `<native_dir>/analysis/crossing_intervals.json` (`blocker_analysis.py:884`).
4. `phase2.copy_model_files` (`phase2.py:61-72`) copies **21-height** `layer_planes.json /
   physical_layer_stack.json / process_rules.json` from the Phase-1 dir. For 20H it must emit the
   model20 payloads. Otherwise the independent validator (`_load_model`, `validate_native3d.py:629`)
   silently audits a 21-height model.
5. `finalize_phase2.py` is the most 21-height-bound file (≈40 hard-coded `2440`/`1967`/`21`/archive
   paths in `:19-22, 44-123, 248-524, 528-605`). It must be parameterised before it can finalise a
   20H run.

**Already given for free (do not rebuild):** `coldstart20/model20.py` is a verified drop-in for
`reheight21.model` (API parity check: only `MODEL_NAME` missing; heights exactly the requested
−0.325 … +0.625, L19 deleted, interface z = +0.025/+0.525), `coldstart20/bootstrap.py` aliases it
under the `reheight21.model` module key and patches `common.INTERFACE_Z`,
`common.Z1/Z2_INTERFACE_MM`, `l3d.layers.INTERFACE_ROWS`, plus `assert_20_height_profile()`. The
pipeline must be imported **after** the bootstrap (verified: `native3d.common.PLANE_Z` then has 20
entries and `M.plane_of_z` resolves +0.025→1001, +0.525→1002).

---

## 1. Entry points, commands, stage order, checkpoints, output directories (Q1)

### 1.1 CLIs (argparse, verified with `--help`)

All modules live in `four_side_1024/fanout1024/native3d/`; they use `if __name__ == '__main__': main()`
(no console-scripts). Run from the project root with the venv Python.

| Stage | Command (observed / README) | argparse defaults (`file:line`) | Writes |
|---|---|---|---|
| D0/D1/D2 | `python -m four_side_1024.fanout1024.native3d.run_d --screen 80 --repairs 30` | `--screen 80`, `--repairs 40`, `--max-joint 3`, `--time-budget 260`, `--max-accept 12` (`run_d.py:81-88`) | `NATIVE_3D_JOINT_OPT_1024/experiment_D/` |
| E0/E1/E2 | `python -m ...native3d.run_e --routes 16` | `--routes 14`, `--time-budget 300`, `--max-accept 15` (`run_e.py:217-223`) | `.../experiment_E/` |
| F | `python -m ...native3d.run_f --sweeps 2 --time-budget 560` | `--sweeps 2`, `--time-budget 600`, `--joint-per-sweep 10` (`run_f.py:218-223`) | `.../experiment_F/`, root `optimization_history.csv`, root `transition_stats.json` |
| F+ (extra plain sweep) | `python -m ...native3d.run_f_plus` | `--time-budget 210`, `--max-sweeps 1` (`run_f_plus.py:23-27`) | `experiment_F/{routes,crossing_stats,validation_extra,extra_sweep}.json` + `best_valid/` |
| near-miss | `python -m ...native3d.run_f_nearmiss` | `--routes 250`, `--time-budget 300`, `--max-accept 25` (`run_f_nearmiss.py:64-69`) | `experiment_F/{near_miss_results,validation_near_miss}.json` + `best_valid/` |
| finalise | `python -m ...native3d.finalize_phase2` | none (`finalize_phase2.py:608`) | root deliverables, `report.md/README.md/SPEC.md/comparison.md`, `MANIFEST.json`, `summary.json`, `validation/final/`, `plots/`, archive |
| D0 analysis (independent) | `python -m ...native3d.blocker_analysis --baseline-dir <E5> --native-dir <NATIVE_3D_CROSSING_OPT_1024> --out-dir <NATIVE_3D_JOINT_OPT_1024>` | `--min-net 3`, `--extra-route 129`, `--extra-net 16`, `--validation-limit 60` (`blocker_analysis.py:2172-2198`) | `analysis/blocker_analysis.json` (29 MB), `analysis/blocker_analysis_report.md`, `analysis/plots/` |
| E0 analysis (independent) | `python -m ...native3d.arc_crossing_analysis --baseline <NATIVE_3D_CROSSING_OPT_1024> --out-dir <NATIVE_3D_JOINT_OPT_1024>` | `--baseline`/`--out-dir` required; `--top-routes 10` (`arc_crossing_analysis.py:2718-2733`) | `analysis/arc_crossing_analysis.json` (7.8 MB), `analysis/arc_crossing_report.md`, `plots/arc_crossing_*.png` |
| interval analysis (Phase-1 input) | `python -m ...native3d.crossing_intervals --baseline-dir <E5> --out-dir <NATIVE_3D_CROSSING_OPT_1024>` | `--baseline-dir N.E5_DIR`, `--out-dir N.RUN_DIR`, `--validate-top 150` (`crossing_intervals.py:2353-2398`) | `<out>/analysis/crossing_intervals.json` (19.9 MB) — **consumed by `run_d`** |
| Phase-1 finaliser (legacy) | `python -m ...native3d.final_deliverables` | none (`final_deliverables.py:479`) | writes `N.RUN_DIR` = `NATIVE_3D_CROSSING_OPT_1024` (**not** Phase-2) |

README commands: `NATIVE_3D_JOINT_OPT_1024/README.md:15-21`.
Note two README/code mismatches: README says `run_e --routes 16` (default 14) and
`run_d --repairs 30` (default 40); the actual D log shows `attempts=14` because only
`repair_candidates=7` survived screening ×2 candidates each (`logs/experiment_D.log:10`).

### 1.2 Stage order actually executed (from logs + mtimes)

```
[Phase 1, read-only input]
  crossing_intervals            -> NATIVE_3D_CROSSING_OPT_1024/analysis/crossing_intervals.json
  (Phase-1 A/B/C)               -> NATIVE_3D_CROSSING_OPT_1024/experiment_C   (2440 crossings)
[Phase 2]
  blocker_analysis (D0, indep)  -> analysis/blocker_analysis.json          (145.1 s)
  arc_crossing_analysis (E0)    -> analysis/arc_crossing_analysis.json     (not logged, minutes)
  run_d                         -> experiment_D/ + best_valid/ (only if improved)
  run_e                         -> experiment_E/ + best_valid/
  run_f                         -> experiment_F/ + best_valid/ + root transition_stats.csv
  run_f_plus   (2×: 2436→2424, 2424→2422)      -> experiment_F/{validation_extra,extra_sweep}
  run_f_nearmiss (2×: 2422→2409, 2409→2409)   -> experiment_F/{near_miss_results,validation_near_miss}
  finalize_phase2               -> root deliverables + validation/final + MANIFEST + report
```

Timestamps: first D start `01:37:51`, finalise `02:17:07` (total ≈ 39 min wall;
`outputs/.../NATIVE_3D_JOINT_OPT_1024/logs/*.log`, `MANIFEST.json:3`).

### 1.3 Config JSON under `configs/`

**There are none.** `configs/` is created by `phase2.ensure_dirs()` (`phase2.py:31-35`) but is empty
in the Phase-2 output. Configuration is exclusively argparse defaults + module constants.
The only JSON that looks like a config is an **output** hash manifest:
`best_valid/config.json` = `{created_at, routes_file_sha256, crossings, crossing_pairs,
validation_pass, violations}` written by `phase2.save_best_valid` (`phase2.py:139-145`).

### 1.4 Checkpoint / resume flags

* **No `--resume` / `--checkpoint` flags exist anywhere** in D/E/F (`grep resume|checkpoint` over
  `run_d/run_e/run_f/phase2`: only `run_f.py:13,257,370` docstring/`save_checkpoint`).
* “Checkpointing” = `best_valid/` snapshot (`phase2.py:127-149`), refreshed after each accepted
  change/sweep by `run_f.save_checkpoint` (`run_f.py:257-267`), by `run_e`/`run_d`/`run_f_plus`/
  `run_f_nearmiss` after their batch, and by `finalize_phase2` (validator target = `best_valid/`).
* Resume semantics are implicit: `run_e` starts from `<RUN2>/best_valid` then `experiment_D` then
  Phase-1 (`run_e.py:229-239`); `run_f` picks the **minimum-total** readable candidate among
  `best_valid / experiment_E / experiment_D / PHASE1_RUN_DIR` (`run_f.py:53-78`); F+ and near-miss
  read `best_valid/` only (`run_f_plus.py:31-33`, `run_f_nearmiss.py:73-75`).
* `checkpoints/` is created (`phase2.py:33`) and mentioned in the report (`finalize_phase2.py:443`)
  but is **empty**; only Phase-1 `global_optimizer.py:270-273` ever writes checkpoint files. The
  `--time-budget` deadlines are absolute wall-clock caps, not resumable state.

### 1.5 Output directory of each stage

`<RUN2> = outputs/manual_c4_new_connectivity/NATIVE_3D_JOINT_OPT_1024/`

| Path | Content |
|---|---|
| `experiment_D/` | routes_l3d, crossing_stats, layer_planes, physical_layer_stack, process_rules, assignment_1024.csv, `blocker_map.json`, `joint_search_history.csv`, validation.json, summary.json |
| `experiment_E/` | routes_l3d, crossing_stats, model files, `arc_crossing_analysis.json` (light), `arc_rebuild_results.json`, validation.json, summary.json |
| `experiment_F/` | routes_l3d, crossing_stats, transition_stats, validation, `strategy_stats.json`, summary, `extra_sweep.json`, `near_miss_results.json`, `validation_extra.json`, `validation_near_miss.json` |
| `best_valid/` | routes_l3d, crossing_stats, validation, config.json, model files, **stale** transition_stats.json |
| `analysis/` | blocker_analysis.json + report + plots; arc_crossing_analysis.json + report; (`crossing_intervals.json` lives in the **Phase-1** dir) |
| `logs/` | `experiment_{D,E,F}.log` (UTF-8), `*_console.log` (UTF-16LE), F+/near-miss console logs |
| `validation/final/` | independent-validator `validation.json` + `validator_consistency_tests.json` |
| root | `routes_l3d.json`, `crossing_stats.json`, `validation.json`, `transition_stats.json`, `optimization_history.csv`, `joint_search_history.csv`, `blocker_analysis.json`, `arc_crossing_analysis.json`, `arc_rebuild_results.json`, `failed_attempts.json`, `MANIFEST.json`, `summary.json`, report set, `plots/` |
| `baseline/` | byte copy of Phase-1 `experiment_C` routes/stats/model files (created out-of-band; **no script writes it**) |
| `checkpoints/`, `configs/`, `scratch/` | empty / empty / analyst debug scripts (`scratch/blocker_analyst/scripts/run_blocker_analysis.py` documents the D0 command) |

---

## 2. Module-by-module audit: what it does, inputs, outputs, transaction mechanics (Q2)

### 2.1 `run_d.py` — D: multi-route joint make-way
* **Inputs** (`run_d.py:96-108`): Phase-1 accepted layout `P2.PHASE1_RUN_DIR/routes_l3d.json`
  (= `NATIVE_3D_CROSSING_OPT_1024/experiment_C`, 2440), `N.load_assignment()` (manual group set),
  and the Phase-1 interval analysis `P2.PHASE1_DIR/analysis/crossing_intervals.json`
  (`run_d.py:41`). Candidate selection: `feasible`, `estimated_net >= MIN_NET=3`, best per target z,
  top `per_route=3`, sorted by predicted net, ex-Phase-1-native routes excluded (`run_d.py:40-68,106-107`).
* **D0** (`run_d.py:110-157`): for up to `--screen 80` candidates – build the excursion
  (`build_candidate`, `:71-78`), iteratively collect true-3D blockers
  (`J.collect_blockers`), split manual vs movable, write `experiment_D/blocker_map.json`
  `{screened, clean, histogram, manual_blocked, own_geometry, repair_candidates, rows[]}`.
  Observed: `screened=80 clean=9 manual=48 hist={0:18,1:7,2:12,3:8,4:4,5:8,6:23} repair_candidates=7`.
* **D1/D2** (`run_d.py:159-208`): for each of the ≤7 repair candidates × first 2 candidates,
  `J.joint_try(..., max_joint=3)`; on accept (`report['accepted']`) replaces **every** route in
  `report['joint_routes']` in `env` and `bbox`; appends to `accepted` and breaks.
* **Outputs**: `experiment_D/routes_l3d.json` (`schema=native3d_phase2_routes_l3d_v1`),
  `crossing_stats.json`, model files, `blocker_map.json`, `joint_search_history.csv`
  (header `route_id,target_z,predicted_net,accepted,net,reason,joint_size,joint_routes,after_total`),
  `validation.json` (guard summary), `summary.json` (`native3d_phase2_experiment_d_v1`).
  `best_valid/` only if pass and total < BASELINE (`run_d.py:239`).
* **Rollback**: `joint_try` never mutates `env`; accept path only. Observed: 14 attempts, 0 accepted.

### 2.2 `run_e.py` — E: arc-region rebuild
* **Inputs** (`run_e.py:229-246`): start dir priority `best_valid` → `experiment_D` → Phase-1
  (`:229-239`), assignment manual set, and `events = P2.crossing_report(...).crossing_events`.
* **E0** (`run_e.py:246-265`): per movable route `arc_crossing_hits` (`:98-117`) locate each crossing
  event on an **arc primitive** (`locate_point` distance ≤ 0.25 mm, matching flat z; `:82-96`),
  rank routes by arc-crossing count; writes `experiment_E/arc_crossing_analysis.json`
  (`native3d_phase2_arc_crossing_analysis_v1`, keys `total_crossings, routes_with_arc_crossings,
  top_routes[40], route_arc_counts`). Observed: 555 routes, top (462:23, 459:21, 149:19, 435:18, 5:17…).
* **E1/E2** (`run_e.py:266-389`): per hot route pick the part with most arc hits that has straight
  runs on both sides (`straight_bounds`, `:133-156`); targets = `N.sorted_by_abs_dz(z_from)` minus
  self, sliced per method (`E_A`:4 nearest, `E_B`:4, `E_C`:8 — `:306-308`); intervals from
  `rebuild_intervals` (`:159-192`; pads 0.5/3.0 mm, E_B also full straight runs; S-feet must fit
  `footprint+0.2`); attempt count `attempts`.
* **Apply/rollback** (`run_e.py:340-386`): per route it keeps the **best** (`min delta`) feasible
  candidate, replaces it, then compares exact `env.total()`; if strictly lower → accept and
  recompute events; else `env.replace_route(route)` + `bbox.update(route)` (captured at `:275`) —
  clean single-route rollback.
* **Outputs**: `experiment_E/{routes_l3d,crossing_stats,validation,summary,arc_crossing_analysis,
  arc_rebuild_results}.json`. Observed: 36 attempts, 0 accepted. Note `run_e.py:395-396` contains
  dead code (`… if False else None`) and `:408` hard-sets `start_crossings = P2.BASELINE_CROSSINGS`.
* `try_rebuild` gate (`run_e.py:195-214`): `E2.insert_excursion_general` → `RM.structure_errors` →
  `G.candidate_guard` → `env.evaluate_candidate` (`d56_ok`, delta).

### 2.3 `run_f.py` — F: global joint optimiser
* **Inputs** (`run_f.py:231-255`): best start among 4 candidate dirs; `env = J.make_env(routes)`
  (`crossing_cache.NativeRouteSet` + `guard.BboxCache`); manual set; `events =
  env.cache.crossing_events()`; `joint_pool` from `run_d.load_analysis_candidates(min_net=5,
  per_route=2)` filtered to routes with crossings and sorted by crossing count.
* **Sweeps** (`run_f.py:269-375`): route order = movable routes with crossings, most crossings first.
  Per route: `plain_attempt` → if no/weak result and arc crossings exist `arc_attempt` → if still
  none and joint budget remains `joint_try(max_joint=2)` (max `--joint-per-sweep 10`).
  Apply best; recompute exact `env.total()`; accept only if `after_total < before_total`, update
  `events`/`counter`; else rollback (`:365-369`).
* **Checkpoint** (`run_f.py:257-267`): save `experiment_F/` + full `P2.validate` (1024-route World +
  min-clearance) + `best_valid/` if total ≤ best_valid_total. After each sweep and at the end.
* **Outputs**: `experiment_F/{routes_l3d,crossing_stats,transition_stats,validation,strategy_stats,
  summary}.json`, root `optimization_history.csv` (header `stage,sweep,route_id,delta,total,target_z`),
  root `transition_stats.json`.
  Observed: sweep 1 accepted `arc_span route 497 net=-4 total=2436`; second invocation no accept.
* **Strategy counters** `plain/arc_span/joint` each `{attempts, accepted, net, best}`
  (`run_f.py:244-247`, exported `:395`).

### 2.4 `run_f_plus.py` — extra plain-batch sweep (Phase-1 batch engine)
* **Inputs**: `best_valid/routes_l3d.json` only (`run_f_plus.py:31-33`); `batch_avoid.route_plan(
  strategy='B4_multi_excursion', max_excursions=2)`.
* **Transaction** (`run_f_plus.py:60-87`): plan → `new_route` + `predicted_delta < 0` →
  deep-copy `previous` → replace → exact `env.total()`; accept if lower else restore `previous`.
* **Outputs** (`run_f_plus.py:92-105`): `experiment_F/validation_extra.json`, `extra_sweep.json`
  `{start, final, history[], validation}`, refreshed `experiment_F/{routes_l3d,crossing_stats}` and
  `best_valid/`. Requires `validation_pass`. Observed: 2436→2424 (7 accepts, `plain_batch` net −14),
  2424→2422 (1 accept).

### 2.5 `run_f_nearmiss.py` — near-miss interval refinement
* **Inputs** (`run_f_nearmiss.py:28-58`): `best_valid/` + `analysis/blocker_analysis.json`
  candidate_results with `build_ok`, no structure errors, no hard/manual blockers,
  `estimated_net >= 3`, route not native/direct; ≤4 per route, 256 routes observed
  (`logs/experiment_F_nearmiss_console.log`).
* **Search** (`run_f_nearmiss.py:103-133`): for each candidate × `SHIFTS` on `s0` and `s1`
  (`SHIFTS = (0, ±0.4, ±1.0, ±2.0)`, `:61`), guard `s0≥0.5`, `s1≤len-0.5`, `s1-s0≥4`; build
  `RM.duck_out`; structure → `env.evaluate_candidate` (d56 + delta<0) → `G.candidate_guard`.
* **Transaction** (`run_f_nearmiss.py:136-152`): apply best → exact `env.total()`; accept if lower,
  else restore captured `route`.
* **Outputs** (`run_f_nearmiss.py:153-172`): `experiment_F/near_miss_results.json`
  (`native3d_phase2_near_miss_v1`: `start_total, final_total, attempts, accepted, net,
  improvements[]` — on-disk file additionally has `runs[]` and `note`, which the current source does
  **not** write → artefact/script drift, see §10), `validation_near_miss.json`, refreshed
  `experiment_F/` + `best_valid/` if pass. Observed: 1728 attempts, 1 accept (route 737 → z=+0.20,
  net −13, 2422→2409); second pass 768 attempts, 0 accept.

### 2.6 `joint_reroute.py` — the joint transaction engine (library, no CLI)
Inputs: `env` (`crossing_cache.NativeRouteSet`), `bbox_cache`, target route id, already-built
candidate route, manual id set, `max_joint`. Output: a report dict
`{target_route_id, accepted, blockers, movable_blockers, manual_blockers, joint_routes, reason,
before_total, after_total, net, seconds[, routes, exact_total, exact_pairs, placement_errors]}`.
Mechanics — see §5 for the validator chain. Key facts:
* blocker discovery is iterative (≤ `MAX_BLOCKER_ROUNDS=8`) with a **local** 3D World over
  bbox-overlapping routes (`local_check`, `:62-76`); rejects `manual_blocker`, `too_many_blockers`
  (hard cap `MAX_JOINT_ROUTES=5`, `:41-42`), `own_geometry`, `unattributed_violation` (`:78-125`).
* make-way geometry per blocker (`make_way_candidates`, `:150-172`): exact R15 excursion of
  half-span `footprint+3` mm or `footprint+12` mm to the 3 nearest target heights; accepted by
  `make_way_one` only if `RM.structure_errors` empty **and** `local_check` against the already
  planned changes is clean (`:175-203`).
* the caller’s route dict is never mutated (deep-copied `work`, `:260`); `joint_try` returns
  `routes=work` only when accepted.

### 2.7 `blocker_analysis.py` — independent D0 analysis (2 202 lines)
* Inputs (`:72-74`, `:884`): frozen E5 baseline (`NON_C4_CROSSING_OPT_1024/E5_joint_repair_final`),
  Native Phase-1 root (`NATIVE_3D_CROSSING_OPT_1024`) and its `analysis/crossing_intervals.json`;
  candidates rebuilt **against the E5 world** with `route_model.duck_out`.
* Output: `analysis/blocker_analysis.json` (`native3d_blocker_analysis_v1`) — keys
  `schema, module, inputs, parameters, worlds{E5,native,native_delta}, selection, aggregates,
  route129, validation, native_validation, candidate_results[5387]`; each candidate has ~35 fields
  (`route_id, target_plane_id/label, target_z, estimated_removed/added/net, s_start_mm, s_end_mm,
  footprint_mm, middle_mm, build_ok, structure_errors, layer_pitch, violations[], d56,
  self_clearance, blockers, blockers_hard, near_miss_blockers, movable_blockers, manual_blockers,
  category, world_clean, production_rejected, native_world, …`). Plus report `.md` and 4 plots.
* Observed: 5 387 selected of 14 480 candidates; 397 near-miss, 4 989 rejected, 1 world-clean;
  145.1 s total (66.6 s candidate check), `scratch/blocker_analyst/full_run.log`.

### 2.8 `arc_crossing_analysis.py` — independent E0 analysis (2 752 lines)
* Inputs: frozen Native Phase-1 baseline dir (`--baseline`); reads `routes_l3d.json` +
  `crossing_stats.json` (`:2548-2556`).
* Output `analysis/arc_crossing_analysis.json` (`native3d_arc_crossing_analysis_v1`): keys
  `schema, inputs, parameters, crossings[2440], aggregates{totals, verification, per_plane,
  per_family, per_route, top_routes_by_own_arc, top_routes_by_arc_involved, hotspot, angle},
  top_route_ids[10], top_routes[10], availability, mechanism_notes, plots[7]`; plus report `.md` and
  7 PNGs. Observed totals: events 2440, class_counts `{arc-arc:438, line-arc:1529, line-line:473}`,
  any_arc 1967 (80.61 %), side arc 2405/4880 (49.28 %), routes_with_own_arc 555.
* **Bug**: the finalizer reads `arcs['classes']` (`finalize_phase2.py:261,356-359`) but the payload
  has **no `classes` key** → report.md E0 table prints 0/0/0 while the real data is in
  `aggregates.totals.class_counts` / `crossings[].crossing_class`.

### 2.9 `crossing_intervals.py` — Phase-1 candidate generator (2 402 lines)
* Inputs: frozen E5 baseline (`--baseline-dir`), outputs `out_dir/analysis/crossing_intervals.json`
  (`:2324-2331`).
* Schema `native3d_crossing_intervals_v1`: `schema, baseline_dir, route_count, movable_routes,
  analysis_parameters, routes[656]{route_id, family, manual, body_layer, body_layer_label, body_z,
  body_flat_index, path_length_mm, crossings[], clusters[], candidates[]}, ranking[1000],
  mechanism_notes`. Candidate: `target_z, target_plane_id/label, target_is_manual_plane,
  world_3d_ok/reason, s_start_mm, s_end_mm, footprint_mm, middle_mm, estimated_removed/added/net,
  shadow_ok, target_shadow_ok, feasible, reason, cluster_*, straight_prim_index,
  transition_clearance_violations, min_target_clearance_mm, …`.
* This is the **only** producer of the candidate coordinates D consumes (`run_d.py:41`).
* Height-generic via `N.PLANE_Z / N.MANUAL_PLANES / N.PLANE_LABEL` (`:853-854, 1285-1298`), i.e. it
  follows the installed model; only its default input/output dirs are 21H paths (`:2356-2358`).

### 2.10 `crossing_cache.py` — exact crossing cache + fast candidate evaluation
* `route_flat_groups` (`:28-39`): flat parts grouped by **physical z**.
* `CrossingCache` (`:50-154`): per-z `audit_flat_group` (strict `fslw` D56 via
  `nonc4.crossings`) → exact `total()/total_pairs()`, `crossing_events()` (route_a/b, z, x, y, angle).
* `NativeRouteSet` (`:212-238`): routes dict + cache + `PlaneIndexCache`; `replace_route`
  invalidates only affected z keys.
* `evaluate_candidate` (`:241-262`): exact per-plane strict-D56 delta and `d56_ok` for one route.
* No files written. Height-agnostic (z keys are physical mm; plane ids only used for reporting).

### 2.11 `excursion2.py` — arc-spanning excursion + staircase geometry
* `build_excursion_general` (`:61-113`) = the arc-region engine (§7).
* `staircase_path`/`build_staircase` (`:166-296`): multi-step height change through the real height
  table (`N.all_heights()`), used for large `dz`; exact S-curves between neighbouring heights.
* `insert_excursion_general` (`:116-162`): builds the new parts chain and appends an `excursions`
  record `{s_start_mm,s_end_mm,from_z,to_z,from_plane,to_plane,up/down/middle/prefix/suffix part
  indices,footprint_mm,middle_mm,contains_arc,kind:'arc_span'|'excursion'}`.
* No CLI, no files.

### 2.12 `phase2.py` — shared paths/baseline/bookkeeping
* Paths: `PHASE1_DIR`, `PHASE1_RUN_DIR`, `BASELINE_CROSSINGS=2440`, `RUN2` (`:22-27`).
* `build_payload` (`:76-104`): inherits the Phase-1 payload dict and replaces
  `routes/native_3d/route_count/routed/failed/crossing_definition/note` +
  `schema=native3d_phase2_routes_l3d_v1`.
* `save_experiment` (`:107-124`): reconcile metadata → routes_l3d + model file copies +
  exact `crossing_stats.json` (with `routed/failed/experiment` fields).
* `save_best_valid` (`:127-149`): routes + model files + crossing_stats + `validation.json` +
  `config.json` (SHA/crossings/pairs/pass/violations). **Does not write `transition_stats.json`** →
  the stale 118-mid Phase-1 copy is what G123 later had to override (see §6).
* `crossing_report` (`:153-160`): authoritative `crossing_report(..., planes=None)` →
  per-physical-z grouping with labels from `reheight21.model` (so it follows the installed profile,
  including `audited_heights`).
* `transition_stats` (`:181-205`): `routes_with_mid_transitions, mid_transitions, excursions,
  by_from_height, per_route` from each route’s `excursions[]`.
* `derive_excursions`/`reconcile_route` (`:209-274`): re-derives `excursions[]` from the parts chain
  (`flat, transition(mid), flat, transition(mid), flat`); used on every save, geometry untouched.
* `validate` (`:278-287`): fresh-world `G.full_validate` + `G.measure_min_clearance` →
  `{valid, violations, violation_kinds, examples, seconds, min_3d_clearance{...},
  validation_pass}`.

### 2.13 `finalize_phase2.py` — deliverable for Phase 2
* `collect_state` (`:44-85`): loads D/E/F summaries, strategy, arc analysis, near-miss, baseline and
  final routes/crossing stats; patches F summary totals to the freshest crossing_stats and injects
  `plain_batch`/`near_miss` strategy rows.
* `copy_final_artifacts` (`:88-123`): root `routes_l3d.json`, `crossing_stats.json`, model files from
  Phase-1, `transition_stats.json`, copies D/E artifacts from the first `rglob` match, writes
  `failed_attempts.json` (`native3d_phase2_failed_attempts_v1`).
* `run_validator` (`:127-139`): `validate_native3d.validate_run(target=best_valid|experiment_F,
  baseline_dir=PHASE1_RUN_DIR)` → `validation/final/validation.json` and root `validation.json`.
* `make_plots` (`:143-237`), `write_reports` (`:248-524`, report/README/SPEC/comparison),
  `write_manifest` (`:528-544`, `native3d_phase2_manifest_v1`), `archive` (`:548-605`, copies to
  `experiments/native_3d_joint_opt_1024/` + optional git commit in an external repo),
  `main` (`:608-641`, summary `native3d_phase2_final_summary_v1`).

### 2.14 `final_deliverables.py` — **Phase-1** finaliser (not used by Phase 2)
Writes into `N.RUN_DIR` (`= NATIVE_3D_CROSSING_OPT_1024`) with hard-coded 2606 baseline numbers
(`:16-17, 145, 181-187, 229-242, 370-397, 460-477`). For the 20H rebuild this file is irrelevant
except as the template for `finalize_phase2`; do not point it at a 20H run.

### 2.15 Producers of `strategy_stats` / `failed_attempts`
* `experiment_F/strategy_stats.json` is written **only** by `run_f.py:395`
  (`{strategy:{plain,arc_span,joint}}`); the root copy is made by `finalize_phase2.py:104-110`
  (rglob copy). `plain_batch` / `near_miss` rows are **not** in it — they exist only in the final
  `summary.json` where `finalize_phase2.py:70-84` injects them from `extra_sweep`/`near_miss_results`.
* `failed_attempts.json` is written **only** by `finalize_phase2.py:111-121`
  (`native3d_phase2_failed_attempts_v1` aggregating D attempts/accepted + blocker_screen, E
  attempts/accepted, F strategy).

### 2.16 Joint-transaction / rollback mechanism (summary)
`joint_reroute.joint_try` = the only multi-route transaction. It is a **functional transaction**:
deep-copied `work` dict → plan target + make-way per blocker → validate the changed routes in a fresh
World containing all unchanged routes → rebuild `NativeRouteSet(work)` and recount exact crossings →
accept only if `after_total < before_total`; on *any* failure return `accepted=False` and the caller
applies nothing. `run_d`/`run_f` apply `report['routes']` for all `joint_routes` atomically. See §5.

---

## 3. plain / arc_span / joint: definition, selection, near-miss windows, budgets (Q3)

### 3.1 Strategy definitions
| Strategy | Engine | What it changes | Where |
|---|---|---|---|
| `plain` | `run_f.plain_attempt` + `single_route.interval_candidates` | one mid-body excursion of a single route on **one straight run**: crossing cluster → `[s0,s1]` window (4×4 window extensions) → exact R15 up/middle/down at target height | `run_f.py:101-167`; `single_route.py:109-162` |
| `arc_span` | `run_e.rebuild_intervals` + `RE.try_rebuild` on top of `excursion2.insert_excursion_general` | whole sub-path **containing R15 arcs** moved to another height; S-feet on flanking straight runs; middle arc chain reused verbatim | `run_f.py:170-208`; `run_e.py:159-214` |
| `joint` | `joint_reroute.joint_try` (+ `run_d.load_analysis_candidates`) | target excursion **plus** exact R15 make-way excursion of every movable true-3D blocker (≤ `max_joint`) | `run_f.py:305-332`; `run_d.py:40-68` |
| `near_miss` (post-pass) | `run_f_nearmiss` | same as plain but the D0 near-miss candidates with ±0.4/1/2 mm interval shifts | `run_f_nearmiss.py:61-152` |
| `plain_batch` (post-pass) | `batch_avoid.route_plan(B4_multi_excursion, ≤2)` | up to 2 non-overlapping excursions per route at once | `run_f_plus.py:60-87` |

* `plain` tries **all flat parts** (`run_f.py:108-110`), top-3 crossing clusters (gap 10 mm,
  `run_f.py:115-116`), 4 nearest target heights (`:119-120`), ≤3 interval candidates,
  `max_options=8` soft cap (`:130-135`), prefers the most negative fast delta; stops at the first
  cluster/target that yields a feasible candidate (`:160-166`).
* `arc_span` picks the body part with most arc hits (`Counter.most_common`, `run_f.py:176-179`),
  4 nearest targets (`:182-183`), intervals E_A/E_B/E_C, accepts the best delta over the first
  target height that produces any (`:206-207`).
* `joint` pool = Phase-1 interval candidates with predicted net ≥ 5, ≤2 per route, restricted to
  routes with crossings and ordered by crossing count (`run_f.py:212-214, 249-255`); only routes for
  which plain+arc produced nothing and `joint_tried < --joint-per-sweep` (`:306`); `max_joint=2`
  (`:322-323`).

### 3.2 Selection / comparison logic (`run_f.py:288-351`)
1. `strategy['plain']['attempts'] += 1`; try plain.
2. If `best is None or best.delta >= -2` **and** the route has arc crossings:
   `strategy['arc_span']['attempts'] += 1`; take arc result if better.
3. If still nothing and joint budget remains: `strategy['joint']['attempts'] += 1`; take the first
   accepted joint report with more negative net.
4. Apply the chosen change; recompute exact total; **accept only if `after_total < before_total`**;
   update `strategy[method]['accepted'/'net'/'best']` and `history`.
5. Rollback otherwise (`:365-369`).
Cross-strategy comparison is only by the exact post-change global crossing total (−1 per event);
no weighted cost function. There is no per-strategy reordering/annealing; sweeps stop as soon as a
sweep yields no net improvement (`:373-375`).

### 3.3 Near-miss window adjustment mechanisms
| Mechanism | Parameters | Where |
|---|---|---|
| internal window shift (plain) | `base_extra = footprint + SHADOW_MM + margin(0.5)` then `+1.5/+3/+6 mm` before and after; symmetric grow if too short | `single_route.py:119-135` |
| arc-window padding | E_A 0.5 mm, E_B 3.0 mm (and full flanking straight runs), E_C = E_A; S-feet must fit `footprint+0.2` | `run_e.py:175-192` |
| make-way half-span | `footprint+3 mm` and `footprint+12 mm` around the projected conflict | `joint_reroute.py:156-159` |
| near-miss shifts (post-pass) | `SHIFTS=(0, +0.4, −0.4, +1.0, −1.0, +2.0, −2.0)` on `s0` and `s1` independently; min span 4 mm; 49 combos minus (0,0) | `run_f_nearmiss.py:61, 105-113` |
| transition shadow (3D margin implied by geometry) | `SHADOW_MM = sqrt(2·R15·0.05) = 1.224744871 mm` | `common.py:30`; `single_route.shadow_report` `:165-215` |

### 3.4 Budgets / counters
* CLI budgets: D `--screen/--repairs/--max-joint/--time-budget/--max-accept`; E
  `--routes/--time-budget/--max-accept`; F `--sweeps/--time-budget/--joint-per-sweep`; F+
  `--time-budget/--max-sweeps`; near-miss `--routes/--time-budget/--max-accept`.
* Internal caps: `MAX_JOINT_ROUTES=5`, `MAX_BLOCKER_ROUNDS=8`, blocker conflict-point loop 8
  (`joint_reroute.py:41-42, 249`); plain `target_limit=4, max_options=8, clusters[:3], intervals[:3]`;
  arc `target_limit=4, max_targets=8`; D `MIN_NET=3`; near-miss min net 3 and ≤4 candidates/route.
* Counters: `strategy[method]`, `history[]`, `attempts`, `accepted`, D
  `joint_search_history.csv`, F `optimization_history.csv`, plus logs.
* Observed totals (final `summary.json`): plain 580/0, arc_span 555/0, joint 8/0, plain_batch 7/7
  (−14), near_miss 1728/1 (−13).

---

## 4. Hard-coded 21-height / historical numbers inventory (Q4)

Classification: **S** = search-logic (changes behaviour/results), **R** = report/metadata only,
**P** = path/IO default (changes which data is read/written), **T** = validation expectation
(must not be applied to 20H), **X** = already superseded by the `coldstart20` profile.

| # | File:line | Value | Class | Why it must change for 20H / what to read instead |
|---|---|---|---|---|
| 1 | `native3d/common.py:38` | `MOVABLE_PLANES = (6,7,20,1001,8,9,14,15,16,1002,17,18,19)` | **S (crash)** | literal includes deleted id 19 → `PLANE_Z[19]` KeyError (reproduced). Derive from model: `tuple(pid for pid in PLANE_Z if pid not in MANUAL_PLANES)` → 12 ids `(6,7,20,1001,8,9,14,15,16,1002,17,18)` |
| 2 | `native3d/common.py:39` | `MANUAL_PLANES = M.MANUAL_PLANE_IDS` | X | already model-driven; ids unchanged (2,3,4,5,10,11,12,13) |
| 3 | `native3d/common.py:41-43` | `PLANE_Z / Z_PLANE / PLANE_LABEL` from `M.PLANE_IDS` | X | follows installed profile → 20 entries |
| 4 | `native3d/common.py:213` | error text `is not one of the 21 heights` | R | cosmetic |
| 5 | `native3d/common.py:19` | `E5_DIR = …/E5_joint_repair_final` (21H) | **P** | must point at the 20H pre-native baseline (stage 04 “E5-equivalent”) for `load_e5_payload/load_routes/load_assignment` defaults; used by `crossing_intervals`, `global_optimizer`, `final_deliverables`, `visualize` |
| 6 | `native3d/common.py:21` | `BASELINE_21H_DIR = …/FANOUT_FIRST_21_HEIGHT_REBALANCED_1024` | **P/R** | comparison only; for 20H compare against `FANOUT_FIRST_20_HEIGHT_RAISED_1024` (or the stage-03 run dir) |
| 7 | `native3d/common.py:23` | `RUN_DIR = …/NATIVE_3D_CROSSING_OPT_1024` | **P** | default output dir of Phase-1 tools; 20H must write under `experiments/COLD_START_20_HEIGHT_1024/05_native3d_abc` (not the 21H output tree) |
| 8 | `native3d/transition.py:114` | `21 heights` error msg | R | cosmetic |
| 9 | `native3d/excursion2.py:72,168` | `21 heights` | R | cosmetic |
| 10 | `native3d/excursion2.py:179` | `staircase_path` uses `N.all_heights()` | X | follows model (20 values) |
| 11 | `native3d/route_model.py:50` | `21 heights` | R | cosmetic |
| 12 | `native3d/route_model.py:213` | `heights = {… for z in N.all_heights()}` | X | follows model |
| 13 | `native3d/route_model.py:221` | `interface_heights = (0.0, 0.5)` | **S (low risk)** | lead recognition fallback: with 20H interface rows are (0.025, 0.525); derive from `(N.z_of_plane(1001), N.z_of_plane(1002))` |
| 14 | `native3d/phase2.py:22-23` | `PHASE1_DIR`, `PHASE1_RUN_DIR` = 21H `NATIVE_3D_CROSSING_OPT_1024/experiment_C` | **P/S** | 20H Phase-1 accepted layout (stage `05_native3d_abc`) path |
| 15 | `native3d/phase2.py:25` | `BASELINE_CROSSINGS = 2440` | **S** | used as accept/compare threshold (`run_d.py:226,239`, `run_e.py:396,408,416`, `finalize_phase2.py:619-639`). Read from the 20H Phase-1 `crossing_stats.json` totals (will differ; 20 planes and different geometry) |
| 16 | `native3d/phase2.py:27` | `RUN2 = output dir NATIVE_3D_JOINT_OPT_1024` | **P** | new root e.g. `experiments/COLD_START_20_HEIGHT_1024/06_native3d_def` |
| 17 | `native3d/phase2.py:61-72` | `copy_model_files` copies model files from PHASE1/E5 | **P/S** | must emit 20H payloads (`model20.layer_planes_payload()`, stack/rules payloads) or validator silently uses 21H `layer_planes.json` |
| 18 | `native3d/phase2.py:76-104` | `base_payload` from Phase-1 routes payload; `parent_experiment='…experiment_C (2440 crossings)'` | **P/R** | load 20H Phase-1 payload; regenerate parent text |
| 19 | `native3d/phase2.py:127-149` | `save_best_valid` omits `transition_stats.json` | **S (defect)** | causes the stale 118-mid file; write the recomputed stats |
| 20 | `native3d/run_d.py:41` | reads `PHASE1_DIR/analysis/crossing_intervals.json` | **P** | must exist for 20H: rerun `crossing_intervals` against the 20H pre-native baseline |
| 21 | `native3d/run_d.py:116-123` | `J.collect_blockers` on candidates whose `s0/s1` refer to the E5 body flat | **S (semantics)** | candidate coordinates are baseline-body-relative; keep regenerating intervals from the same 20H pre-native baseline the 20H Phase-1 used |
| 22 | `native3d/run_e.py:229-239` | start-dir priority + Phase-1 fallback | **P** | rename to 20H dirs |
| 23 | `native3d/run_e.py:304` | `N.sorted_by_abs_dz(z_from)` | X after #1 | target enumeration |
| 24 | `native3d/run_e.py:395-408` | dead code + `start_crossings = P2.BASELINE_CROSSINGS` | **S/R** | dynamic baseline |
| 25 | `native3d/run_f.py:53-58` | candidate start dirs incl. Phase-1 | **P** | 20H dirs; `phase1_baseline` label |
| 26 | `native3d/run_f.py:119-120,182-183` | `N.sorted_by_abs_dz` | X after #1 | |
| 27 | `native3d/run_f_plus.py:5,31-33` | docstring “2436 layout”; `best_valid` dir | **R/P** | |
| 28 | `native3d/run_f_nearmiss.py:29,39,73` | `RUN2/analysis/blocker_analysis.json`, min net 3, `RUN2/best_valid` | **P** | 20H analysis dir |
| 29 | `native3d/run_f_nearmiss.py:61` | `SHIFTS` | X | height-independent; window is in mm along the body path |
| 30 | `native3d/joint_reroute.py:72,284` | `World(M.layer_stack(), 0.05)` | X | after bootstrap `M` is model20 → 20H stack; `World` checks pitch from world content, not from stack |
| 31 | `native3d/guard.py:79,141` | `World(M.layer_stack(), 0.05)` | X | same |
| 32 | `native3d/single_route.py:186,193` | `N.MOVABLE_PLANES`, `N.all_heights()` in `shadow_report` | X after #1 | shadow/beyond-plane logic auto-adapts (0.05 pitch unchanged) |
| 33 | `native3d/validate_native3d.py:127` | `RUN_ROOT = …NATIVE_3D_CROSSING_OPT_1024` | **P** | default `run_dir` only when `--run-dir` omitted |
| 34 | `native3d/validate_native3d.py:145-160` | `E5_EXPECT` (1024, 2606, 2067, 21 audited heights, min clearance 0.068714895) | **T** | must not be used for 20H; add a 20H expectation block or run without `--regression` |
| 35 | `native3d/validate_native3d.py:338-351` | `_model_planes()` from `M.planes()`; docstrings “frozen 21-height model helpers” | X | after bootstrap returns the 20H table; run dir `layer_planes.json` takes precedence (`:629-648`) |
| 36 | `native3d/validate_native3d.py:1708-1768` | `check_manual_frozen` = byte-identical `parts/length/z` vs `baseline_dir` | **S/T** | for 20H `--baseline-dir` must be the 20H layout that already contains manual-U at +0.025 z (stage 03/04 output). The old 21H E5 baseline would flag all 368 manual routes (correctly: their z changed) |
| 37 | `native3d/validate_native3d.py:956-1106,1172-1508` | structure/native-metadata recompute uses model | X | auto 20H via model + `layer_planes.json` |
| 38 | `native3d/arc_crossing_analysis.py:84` | `PREVIOUS_CLAIM = dict(… events=2606 …)` | R | historical claim; must not be quoted for 20H |
| 39 | `native3d/arc_crossing_analysis.py:99-100` | `PLAUSIBLE_PLANE_IDS = N.MOVABLE_PLANES`, `ALL_PLANE_IDS = N.PLANE_Z` | X after #1 | 20H target list |
| 40 | `native3d/arc_crossing_analysis.py:1824,1859,2139,2525` | report text “all 2440 crossings”, “accepted 2440-crossing baseline”, help “NATIVE_3D_CROSSING_OPT_1024” | R | regenerate text from data |
| 41 | `native3d/crossing_intervals.py:14` | docstring “2606 events” | R | |
| 42 | `native3d/crossing_intervals.py:2356,2358` | defaults `N.E5_DIR`, `N.RUN_DIR` | **P** | pass explicit `--baseline-dir/--out-dir` for 20H |
| 43 | `native3d/blocker_analysis.py:72-74` | defaults E5 / `NATIVE_3D_CROSSING_OPT_1024` / `NATIVE_3D_JOINT_OPT_1024` | **P** | 20H input/output dirs (CLI flags available) |
| 44 | `native3d/blocker_analysis.py:884` | candidate pool `<native_dir>/analysis/crossing_intervals.json` | **P** | 20H Phase-1 analysis path |
| 45 | `native3d/blocker_analysis.py:1590,1863,2160-2161` | report text / help referencing 2440 & `NATIVE_3D_CROSSING_OPT_1024` | R | |
| 46 | `native3d/finalize_phase2.py:19-22` | `RUN=P2.RUN2`, `BASELINE=P2.PHASE1_RUN_DIR`, `ARCHIVE_NAME='native_3d_joint_opt_1024'` | **P** | new run/baseline/archive names |
| 47 | `native3d/finalize_phase2.py:189,254-255,266-272,286-294,359-361,424,448-464,590-593,619-639` | `2440` (and `1967/80.6 %/49.28 %/2405/4880/36`) in reports/summary/plot defaults | **R** | read from state (D/E/F summaries + crossing_stats + arc aggregates) |
| 48 | `native3d/finalize_phase2.py:498-521` | SPEC “21 个物理高度 … −0.35…+0.65” | **R** | 20-height text (18 body + 2 interface; L19 removed; +0.025) |
| 49 | `native3d/finalize_phase2.py:441` | plot title “21 高度图” | R | 20 |
| 50 | `native3d/finalize_phase2.py:549-605` | archive target `experiments/native_3d_joint_opt_1024` + hard-coded external git repo + code snapshot list (missing `run_f_plus.py`, `run_f_nearmiss.py`) | **P** | 20H archive dir + complete code list; no external git repo for cold start |
| 51 | `native3d/finalize_phase2.py:255,266-272,292-294,424,464` | BASE vs FINAL comparisons against 2440 | **R** | compare against 20H Phase-1 baseline count |
| 52 | `native3d/final_deliverables.py:16-17,145,181-187,229-242,370-397` | Phase-1 finaliser, `2606`, `E5` | R/P | not part of Phase 2; do not reuse |
| 53 | `native3d/run_a.py:309`, `run_b.py:153,197`, `global_optimizer.py:372,389-394` | Phase-1 tools with `2606` / E5 model copies | R/P | 20H Phase-1 (A/B/C) needs the same dir treatment if the 20H run redoes Phase 1 |
| 54 | `native3d/visualize.py:2428,2739,2954,3111,3238` | defaults/`21 height panels` text | **P/R** | auto 20 rows via `N.PLANE_Z` (`:127-135`), but pass explicit dirs and fix text |
| 55 | `native3d/tests_native3d/synthetic_native3d.py:296` | “frozen 21-height layer stack (built from the model table)” | X/T | uses model table; must be re-run under bootstrap to test 20H |
| 56 | `four_side_1024/l3d/layers.py:32,245-251` | `INTERFACE_ROWS = {'z1':0.0,'z2':0.5}`; docstring now mentions “20-height cold-start uses +0.025/+0.525” | X | bootstrap patches `INTERFACE_ROWS` in place; `build_stack(..., interface_rows=…)` supports override |
| 57 | `four_side_1024/fanout1024/reheight21/model.py:106-140,203-220,432-448` | literal 21H plane tables | X | 21H default profile; not modified for 20H runs (bootstrap aliases model20) |
| 58 | `four_side_1024/fanout1024/reheight21/model.py:254-319` | `PROFILE / SCHEMA_* / CONTRACT_*` | X | already profile-parameterised (2026-11-17) |

**Rule of thumb:** S entries (1, 13, 15, 17?, 19, 24, 36) are the ones that can produce a wrong or
illegal result; P entries select the wrong files; R entries only corrupt reports; T entries must be
disabled for 20H.

---

## 5. Per-transaction validators and how rollback is guaranteed (Q5)

### 5.1 Candidate gate used by every single-route strategy (`guard.candidate_guard`, `guard.py:115-134`)
Order (fail-fast):
1. `route_model.structure_errors(candidate)` (`route_model.py:204-288`) — parts chain alternation,
   `World.check_structure`, junction position (1e-6), tangent continuity, flat z ∈ height table,
   flat `layer_id == plane_of_z(z)` (lead flats on layer 1), flat arc radius == 15, transition
   radius == 15 and `footprint == 2R·sin(acos(1−|dz|/2R))`, transition end continuity.
2. `route_model.route_metadata_errors` (`:296-320`) — `body_heights`, `mid_transitions`,
   `n_transitions`, `n_mid_transitions`, `length_mm` consistency.
3. `guard.forbidden_cross_plane` (`guard.py:104-112`) — any two flat parts closer than 50 µm.
4. `guard.ensure_flat_d56` (`:91-101`) — **full-plane strict D56** per flat z against all other
   routes (`crossing_cache.PlaneIndexCache.crossings_of`, `D56Index(crossing_policy='strict')`,
   width 0.05 + edge gap 0.03, legal transverse crossings only).
5. `guard.local_world_check` (`:69-88`) — fresh `l3d.world.World(M.layer_stack(),
   clearance=0.05)` over every route whose XY bbox overlaps the candidate (+0.6 mm):
   same-plane D56, cross-plane true-3D centreline ≥ 0.05 mm, self-clearance, layer pitch.

### 5.2 Joint transaction (`joint_reroute.joint_try`, `:207-309`)
1. `collect_blockers` (`:78-125`): iterative local World (≤8 rounds), excludes target; returns
   `clean / manual_blocker / too_many_blockers / own_geometry / blocker_round_limit`.
2. Per blocker `make_way_one` (`:175-203`): `RM.structure_errors` then `local_check` vs
   (target + already-planned changes) — fresh World at clearance 0.05.
3. **Fresh-world re-validation of the whole changed set** (`:282-299`): World gets every unchanged
   route in id order, then each changed route (target + blockers) is `check_route`d and added;
   any violation → `changed_route_validation_failed` (this covers same-plane D56, cross-plane
   3D clearance, layer pitch, self-clearance for the changed routes).
4. **Exact crossing recount** (`:300-303`): `make_env(work)` rebuilds `CrossingCache` from scratch →
   `after_total`; `accepted = after_total < original_total` (strictly).
5. On any failure the function returns `accepted=False`; `work` is discarded → caller mutates
   nothing. On accept it returns the full `routes` dict; `run_d`/`run_f` then replace all changed
   routes in `env` and `bbox` (atomic in practice, no partial apply).
6. After every accepted batch/sweep the caller runs `P2.validate` = `guard.full_validate` (fresh
   World over all 1024 in id order, `:138-165`) + `guard.measure_min_clearance`
   (`V21.measure_min_3d_clearance`, `:168-179`) and saves `best_valid/` only when
   `violations == 0` (`phase2.py:278-287`).

### 5.3 R15 / port contract
* R15 is enforced structurally on every candidate (flat arcs and transitions, see 5.1.1) and
  re-derived by the independent validator (`validate_native3d.check_radius`, `:1542`;
  `V21.check_radius`).
* Port contract (1024 fixed connections, port poses, interface rows, 368 manual-U frozen) is **not**
  part of the per-transaction gates — by construction `duck_out`/`insert_excursion_general` only
  split a body flat and keep prefix/suffix parts and all lead/fanout parts byte-identical
  (`route_model.py:77-90`, `excursion2.py:128-141`). It is enforced only by the independent
  validator at finalise time (`check_coverage`, `check_ports`, `check_manual_frozen`, `check_glass`,
  `check_crossings`, `check_clearance`, `validate_native3d.py:702-2159, 2459-2800`).
* **Known rollback defect in `run_f.py:333-369`:** the reject branch restores
  `old = routes.get(route_id)` where `routes` is the **start snapshot** captured at `run_f.py:234`,
  never updated during the run. If a route was already modified earlier in the same run (or the
  transaction was `joint`, which changes several routes), a rejection restores the *original start
  geometry* and leaves the other joint routes modified. Today the exact total is pre-checked on a
  copy so this path is rarely taken, but for the 20H rebuild it should restore a per-step
  `previous = deepcopy(env.routes[rid])` (pattern already used correctly in `run_f_plus.py:69-87`
  and `run_e.py:275,380-381`).

---

## 6. What later stages (G123, G4) consume from the Phase-2 output (Q6)

`G123 = outputs/manual_c4_new_connectivity/XYZ_JOINT_G123_1024` (and
`experiments/xyz_joint_g123_1024`), `G4 = experiments/xyz_joint_g4_1024` (and
`four_side_1024/fanout1024/xyzrouter/g4`). Both ran after Phase 2 and treat it as the frozen
2409-crossing baseline.

### 6.1 G123
* Path constants: `four_side_1024/fanout1024/xyzrouter/paths.py:16-17`
  `NATIVE_JOINT_DIR = OUTPUT_ROOT/'NATIVE_3D_JOINT_OPT_1024'`,
  `NATIVE_PHASE1_DIR = …'NATIVE_3D_CROSSING_OPT_1024'`;
  `baseline_dir()` (`:114-119`) prefers `XYZ_JOINT_G123_1024/baseline_authoritative`, else
  `NATIVE_JOINT_DIR/best_valid`.
* `load_baseline()` (`:122-131`) reads exactly:
  `routes_l3d.json` → `payload['routes']` (list of route records) and `assignment_1024.csv`, plus
  SHA256 of both.
* `preflight_audit.py` builds `baseline_authoritative/` from **`NATIVE_3D_JOINT_OPT_1024/best_valid`**
  (`SNAP_DIR` `:89`): copies `routes_l3d.json, assignment_1024.csv, layer_planes.json,
  physical_layer_stack.json, process_rules.json, crossing_stats.json, transition_stats.json,
  validation.json, config.json`, adds `SHA256.json`, `AUTHORITY.json` (`:1624`, `:1669`), and
  **overrides** `transition_stats.json` with the root 138-mid file because
  `best_valid/transition_stats.json` is a stale 118-mid Phase-1 copy (documented in
  `AUTHORITY.json.notes` and `superseded_stale_files`).
* `AUTHORITY.json` pins `authoritative_routes_sha256=36c57ad9…`, crossings 2409, pairs 2010,
  mid_transitions 138, excursions 69, manual_368, manual_geometry_mismatch_0, and the independent
  validator PASS report. `tests_validate_xyz.py:73-78` hard-codes the same BEST_VALID/ARCHIVED_REPORT
  paths and the 36c57… SHA.
* Required route fields (via `load_baseline`/`route_builder.py:63-95,127-128,205-268`):
  `route_id, plane, relation, manual_group, layer_role, source_endpoint, target_endpoint,
  source_side, target_side, source_row, target_row, target_layer, target_z_mm, target_plane,
  target_plane_label, n_transitions, direct, needs_transition, lead_source_mm, lead_target_mm,
  length_mm, parts[]` (`flat{kind,z_mm,layer_id,primitives[],tag}` +
  `transition{start,direction,z0,z1,radius_mm,footprint_mm,theta_rad,end,length_mm,tag}`),
  `body_heights`, `mid_transitions`, `excursions`, `layer_sequence`, `layer_z_sequence`.
  Assignment CSV columns: `route_id, plane, relation, manual_group, manual_pattern, layer_role,
  target_layer, target_plane_label, target_z_mm, interface_z_mm, direction,
  needs_transition, c4_group_id, rotation_phase, baseline_old_layer, source_endpoint,
  target_endpoint, source_side, target_side, source_connector, target_connector,
  source_x_mm, source_y_mm, target_x_mm, target_y_mm, source_row, target_row`
  (`NATIVE_3D_JOINT_OPT_1024/baseline/assignment_1024.csv` header).
* Also consumed: `layer_planes.json` (validator model; 21 planes), `physical_layer_stack.json`,
  `process_rules.json`, `crossing_stats.json` (totals/planes/crossing_events),
  root `transition_stats.json` (authoritative 138/69), root and `validation/final/validation.json`
  (independent validator; `tests_validate_xyz.py:75` ARCHIVED_REPORT).

### 6.2 G4
* `four_side_1024/fanout1024/xyzrouter/g4/paths.py:32-38`:
  `START_DIR = XYZ_JOINT_G123_1024/best_valid` (G3, `START_ROUTES_SHA256=711cf910…`,
  `START_CROSSINGS=1322`); `AUTHORITY_DIR = XYZ_JOINT_G123_1024/baseline_authoritative` — i.e. the
  **Phase-2 2409 snapshot is used only for identity / port / manual-U contract checks**, not as the
  search start (docstring `g4/paths.py:1-14`).
* `g4/contract_audit.py` reads `run_dir/routes_l3d.json`, `run_dir/crossing_stats.json`
  (`check_crossing_stats :156`), `run_dir|baseline_dir/assignment_1024.csv` (`:220`),
  `<out>/baseline_revalidation/validation.json` (`:250`), and the baseline snapshot; writes
  `contract_evidence.json`, `audit_metrics.json`, `six_quantities.json`.
* `g4/independent_metrics.py` recomputes every reported number from `routes_l3d.json` alone
  (own 2-D/3-D algebra; only imports `fanout1024.common` for ports and `reheight21.model` for the
  **height table** — a 20H run must run it under the installed 20H profile).
* G4 per-arm artifacts also re-emit `routes_l3d.json / assignment_1024.csv / crossing_stats.json /
  validation/validation.json / SHA256.json / config.json / summary.json / strategy_stats.json /
  failed_attempts.json` (`g4/artifacts.py:6-8,76-149`).

### 6.3 Minimal schema contract a 20H Phase-2 must keep
`routes_l3d.json`: `schema, route_count, routed, failed, native_3d{routes_with_mid_transitions,
mid_transitions, model, geometry}, routes[]` (fields above; `native_3d`/`n_mid_transitions`/
`mid_transitions`/`body_heights`/`excursions`/`layer_sequence`/`layer_z_sequence`/`length_mm`/
`xy_length_mm`/`z_span_mm`/`target_*`).
`crossing_stats.json`: `schema, crossing_rule, totals{crossings, crossing_pairs, violations,
audited_heights, planes_with_crossings, per_route_distribution,…}, planes[]{plane_id,label,z_mm,
kind,route_count,part_count,crossings,crossing_pairs,violations,min_non_crossing_centerline_mm},
per_route_crossings, crossing_events[]{route_a,route_b,plane_id,plane_label,z_mm,x_mm,y_mm,
angle_deg,manual_a,manual_b,direct_a,direct_b}` (observed 2409 events).
`transition_stats.json`: `schema, routes_with_mid_transitions, mid_transitions, excursions,
by_from_height, per_route`.
`validation.json` (independent): `schema, validator, mode, run_dir, baseline_dir, routes_file,
routes_file_sha256, baseline_routes_file, baseline_routes_file_sha256, assignment_file,
assignment_source, layer_planes_file, model, counts{…}, checks{}, violations, violation_count,
violation_counts_by_check, offending_route_ids, synthetic_consistency, geometry_pass,
contract_pass, validation_pass, exit_code, runtime_seconds`.
`summary.json` (final): `schema=native3d_phase2_final_summary_v1, baseline_crossings,
final_crossings, routes, mid_transitions, routes_with_mid_transitions, validation_pass,
violations, experiment_D/E/F, archive, plots`.
`best_valid/config.json`: `{created_at, routes_file_sha256, crossings, crossing_pairs,
validation_pass, violations}`.

---

## 7. Arc-region reconstruction (Q7)

### 7.1 What “arc region” means
A **flat** part holds a 2-D primitive chain (`line` / exact `arc` R=15 mm) at one physical z.
An arc region is a contiguous span of that chain in which the crossing sits on an `arc` primitive
(E0: crossing located within 0.25 mm of an arc, `run_e.py:98-117,82-96`). Because the old excursion
geometry required the two S-curve feet to lie inside a **single straight run**
(`transition.same_straight_run`), crossings on arcs could not be moved. E’s idea: move the whole
local sub-path (lines *and* arcs) to another height, placing the two S-curves on the straight runs
that flank the arc region.

### 7.2 Construction (`excursion2.build_excursion_general`, `:61-113`)
1. `f = transition_footprint(|dz|) = 2R·sin(acos(1−|dz|/2R))` (`transition.py:15-24`).
2. Require `s0+f` and `s1−f` to lie inside one straight line primitive each
   (`_straight → transition.same_straight_run`); middle length `(s1−f)−(s0+f) ≥ 1 mm`.
3. `up = make_s_curve(point(s0), dir_start, z_from, z_to, R=15, tag='mid')`;
   `middle = _sub_chain(prims, s0+f, s1−f)` — **the original primitives, including arcs, are reused
   verbatim** at `z_to`;
   `down = make_s_curve(point(s1−f), dir_end, z_to, z_from, …)`.
4. Exactness checks: up/down endpoints coincide with the original path within 1e-6 mm.
5. `insert_excursion_general` (`:116-162`) rebuilds parts as
   `flat(prefix) | up | flat(middle @ z_to) | down | flat(suffix)` and records
   `{kind:'arc_span'|'excursion', contains_arc, footprint_mm, middle_mm, s_start/end_mm, from/to z,
   part indices}`; `rebuild_route_metadata` recomputes `body_heights/layer_sequence/n_mid_transitions`
   etc.
6. Height coverage: `transition_footprint` allows any `|dz| < 2R = 30 mm`; a 20H `dz` of 0.05 mm
   gives `f = 1.731329 mm` (computed; `SHADOW_MM = 1.224745 mm`).

### 7.3 Planning variant (E_A/E_B/E_C)
`straight_bounds` (`run_e.py:133-156`) finds the line primitives immediately before/after the hot
arc (skipping consecutive arcs). `rebuild_intervals` (`:159-192`) produces intervals whose S-feet sit
inside those lines: E_A = footprint + 0.5 mm pad, E_B = footprint + 3.0 mm (plus full available
straight runs), E_C = E_A but targets non-adjacent heights (8 targets). Requires
`flanking straight length >= footprint + 0.2` on both sides, else no candidate
(`no_flanking_straight`).

### 7.4 Is it height-table generic?
**Yes for the geometry**, with these height-table touch points:
* target heights are enumerated with `N.sorted_by_abs_dz` / `N.z_of_plane` (`run_e.py:304-305`,
  `run_f.py:119-120,182-183`, `joint_reroute.py:182-184`) → after fixing `MOVABLE_PLANES` (#1) this
  becomes the 12 movable heights of the 20H table;
* `build_excursion_general` validates `z_to` with `N.plane_of_z` (`excursion2.py:72`) → accepts the
  20H table automatically;
* the S-curve math depends only on `z_from, z_to, R=15` (no pitch/plane-count assumption);
* E0 analysis parametrises target planes from `N.PLANE_Z` (`arc_crossing_analysis.py:99-100`,
  `crossing_intervals.py:1285-1298`), so it enumerates 20 planes under the profile.
The only non-generic part is the **interface/lead convention** (`body_flat_indices` assumes the first
and last flats are leads, `common.py:133-149`) and the interface-height fallback in
`route_model.structure_errors:221`. Both are unaffected by the number of heights but the latter must
track the new interface z (+0.025/+0.525).

---

## 8. Wall-clock cost measured from the logs (Q8)

| Stage | Wall clock | Evidence |
|---|---|---|
| D (successful run) | **257.7 s ≈ 4 m 18 s** | `experiment_D/summary.json.seconds=257.7`; log `01:46:39 → 01:50:55` |
| — D0 screen (80 candidates, iterative 3D blocker search) | **≈185 s** (72 %) | `logs/experiment_D.log:8-10` (`01:46:40 → 01:49:45`) |
| — save + exact recount | ≈50 s | `01:49:45 → 01:50:35` |
| — full validation + min-clearance | 16.0 s + 2.4 s | `:[guard] full validation … 16.0s`, `min 3D clearance … 2.4s` |
| — D1/D2 (14 joint attempts) | inside the above; each joint attempt = blocker discovery + make-way + exact 1024 recount | `logs/experiment_D.log:10-11` |
| E (per run) | **≈29 s** (36 attempts, 12.0 s of attempts + save + validation) | `experiment_E/summary.json.seconds=12.0`; log `01:51:05 → 01:51:34` (3 E runs total ≈ 70 s) |
| F core (2 sweeps over 656 movable routes) | **133.1 s** (start log `01:53:46 → 01:56:00`; sweep 1 ≈100 s, saves+validations ≈30 s) | `experiment_F/summary.json.seconds=133.1`; `logs/experiment_F.log` |
| F+ (1 sweep, batch engine) | **≈132 s** | `01:56:25 → 01:58:37` |
| F+2 (2 sweeps) | **≈215 s** | `01:58:46 → 02:02:21` |
| near-miss (250 routes, ≈1 700–1 900 attempts) | **≈325 s / ≈230 s** | `02:06:29 → 02:11:54`, `02:12:01 → 02:15:51` |
| D0 independent `blocker_analysis` | **145.1 s** (66.6 s for 5 387 candidates; two world rebuilds + validation cross-check) | `scratch/blocker_analyst/full_run.log` |
| E0 independent `arc_crossing_analysis` | not logged; 7.8 MB payload, 2 440 events, 10-route interval search + 7 PNGs → order 1–3 min | file size/mtimes only |
| `finalize_phase2` (validator + plots + reports + manifest + archive + git) | ≈30–90 s (validator 19.01 s; MANIFEST hashes 125 files ≈30 MB twice) | `validation.json.runtime_seconds=19.01`; `MANIFEST.json` mtime |
| **Whole Phase-2 session** | **≈39 min** (`01:37:51` first D start → `02:17:07` report) including 3 D runs and 3 E runs | combined logs |

**Long poles for a 20H rerun:** (1) D0 blocker screening / joint make-way (fresh `World` per
candidate/blocker; scales with candidate count × nearby routes), (2) near-miss refinement
(≈1.7 k `duck_out` + strict-D56 + 3D guard evaluations), (3) F plain sweep over 656 routes ×
4 target heights × 16 window variants, (4) repeated full-1024 validation after every save
(16 s each, plus 2.4 s min-clearance), (5) independent validator (19 s) and blocker analysis
(145 s). 20H reduces the target-height fan-out slightly (12 movable heights vs 13) so per-attempt
cost should be ≈unchanged or a few % lower.

---

## 9. Concrete adaptation plan for Native-3D Phase 2 on a 20-height legal solution

**Precondition already satisfied in the tree (verified):** `coldstart20.model20` has 20 heights
`(2,3,4,5,6,7,20,1001,8,9,10,11,12,13,14,15,16,1002,17,18)` with z −0.325 … +0.625 step 0.05,
L19 gone, interface +0.025/+0.525, glass unchanged; `bootstrap.install()` aliases it over
`reheight21.model` and patches `common.INTERFACE_Z`, `common.Z1/Z2_INTERFACE_MM`,
`l3d.layers.INTERFACE_ROWS`; `assert_20_height_profile()` guards import order.

### 9.1 Must-fix code (in order)
1. **`native3d/common.py:38`** — replace the literal with a model-derived tuple:
   `MOVABLE_PLANES = tuple(int(pid) for pid in PLANE_Z if int(pid) not in set(MANUAL_PLANES))`.
   Verified: 12 planes, `sorted_by_abs_dz(0.0)` = `[20,1001,7,8,6,9,14,15,16,1002,17,18]`,
   no `KeyError`. (This single change unblocks run_e/run_f/run_d/joint target enumeration,
   `single_route.shadow_report`, and all E0/intervals tools.)
2. **`native3d/route_model.py:221`** — `interface_heights = (0.0, 0.5)` → derive from
   `(N.z_of_plane(1001), N.z_of_plane(1002))` or `M.INTERFACE_Z.values()`.
3. **`native3d/phase2.py:22-27`** — parameterise paths/baseline. Suggested profile hook:
   `#if model is model20: PHASE1_DIR = experiments/COLD_START_20_HEIGHT_1024/05_native3d_abc;
   PHASE1_RUN_DIR = PHASE1_DIR/'experiment_C'; RUN2 = …/06_native3d_def;
   BASELINE_CROSSINGS = load_json(PHASE1_RUN_DIR/'crossing_stats.json')['totals']['crossings']`
   (or add `--phase1-dir/--run2/--baseline-crossings` args to D/E/F and to finalize).
4. **`native3d/phase2.py:61-72` `copy_model_files`** — emit the 20H model files
   (`model20.layer_planes_payload()`, `stack_payload()`, `process_rules_payload()`, plus the 20H
   `assignment_1024.csv`) instead of copying from `PHASE1_RUN_DIR/E5_DIR`.
5. **`native3d/phase2.py:127-149`** — write `transition_stats.json` in `save_best_valid` (fix the
   stale-stats defect that G123 had to work around).
6. **`native3d/run_d.py:41` / `blocker_analysis.py:884` input** — regenerate the candidate pool for
   20H: run `crossing_intervals` with `--baseline-dir <20H pre-native baseline (stage 04 output)>`
   `--out-dir <20H phase1 dir>` **under the bootstrap**; then point D at
   `<20H phase1 dir>/analysis/crossing_intervals.json`.
7. **`run_e.py:229-239`, `run_f.py:53-58`, `run_f_plus.py:31-33`, `run_f_nearmiss.py:29,73`** —
   point start dirs at the 20H `best_valid/experiment_D/experiment_E` and the 20H analysis dir;
   replace `P2.BASELINE_CROSSINGS` uses with the dynamic 20H baseline.
8. **`finalize_phase2.py`** — parameterise `RUN`, `BASELINE`, `ARCHIVE_NAME`, external git repo and
   every 2440/1967/21 literal listed in §4 rows 46-51; regenerate README/SPEC/report/comparison text
   from state (20 heights; L19 deleted; +0.025 mm shift; new baseline/archive names); add
   `run_f_plus.py` + `run_f_nearmiss.py` to the archived code snapshot; fix the
   `arcs['classes']` bug (use `aggregates.totals.class_counts`).
9. **`native3d/validate_native3d.py`** — add a 20H expectation block (or simply run without
   `--regression`), update docstrings/`RUN_ROOT` default, keep `E5_EXPECT` only for the 21H E5
   regression; pass `--baseline-dir <20H layout that already contains the 368 manual-U at +0.025 z>`
   so `check_manual_frozen` remains a *freeze* check, not a relaxation.
10. **Report-only strings** in `transition.py:114`, `excursion2.py:72,168`, `common.py:213`,
    `route_model.py:50`, `arc_crossing_analysis.py:84,1824,1859,2139,2525`,
    `crossing_intervals.py:14`, `blocker_analysis.py:1590,1863,2160`, `final_deliverables.py`
    → “20 heights” / data-driven text.

### 9.2 Add 20H entry points (no direct `python -m …native3d.run_*`!)
`native3d/__init__.py` does not import submodules, and the package `__init__`s are inert, so a driver
that imports the bootstrap **first** is safe. Add e.g.
`four_side_1024/fanout1024/coldstart20/run_native3d_def.py`:

```python
from . import bootstrap as B          # installs 20H profile on import
B.install()                           # idempotent + assert
from ..native3d import phase2 as P2   # now 20H-derived
P2.configure(phase1_dir=..., run2=... , baseline_crossings=...)
from ..native3d import run_d, run_e, run_f, run_f_plus, run_f_nearmiss
from ..native3d import blocker_analysis, arc_crossing_analysis, crossing_intervals, finalize_phase2
```
Candidate stages: `01_height_config` (model20 profile JSON), `04_...` (pre-native baseline),
`05_native3d_abc` (Phase-1 A/B/C analog producing the input layout), `06_native3d_def`
(this Phase-2 rebuild), `07_g123`, `08_g4`, following the existing empty scaffold under
`experiments/COLD_START_20_HEIGHT_1024/`.
Add `B.assert_20_height_profile('run_native3d_def')` at the top of each `run_*` main (or a shared
`native3d/profile_guard()`), otherwise a direct `python -m …native3d.run_d` silently runs a mixed
21H/20H process.

### 9.3 Keep the “no rule relaxation” guarantees
* Do **not** touch `R15=15`, `MIN_3D_CLEARANCE=0.05`, `SHADOW_MM`, D56 strict policy
  (`fslw/config`, `d56.index(crossing_policy='strict')`), glass or 1024 connectivity.
  `coldstart20/model20.py:124-133` already re-asserts them and `tests_model20` (to be written per
  `coldstart20/__init__.py:17`) is meant to prove a 49 µm pair is still rejected.
* Keep the independent validator PASS gate on every `best_valid/` write and the exact crossing
  recount on every accept; keep `strict D56` and legal-crossing semantics unchanged.
* Beware the legacy 0.08 mm global clearance constant: `fslw/config.CLEARANCE_MM = 0.08` is the
  default of `l3d.world.World` when `clearance=None`; every native3d call site passes 0.05
  explicitly — keep it that way.

### 9.4 Expected behavioural deltas in 20H (sanity targets)
* 20 planes; 12 movable heights; 18 body + 2 interface; interface z +0.025/+0.525; manual U ids
  unchanged; per-plane counts follow `model20.CONTRACT_PLANE_COUNTS` (sum 1024).
* Crossing baseline will differ from 2440 (different z occupancy + a different Z2 “other” allocation
  plan `Z2_OTHER_PLAN = ((9,14),(14,14),(15,14),(16,14),(16,…),(17,…),(18,12))`, 400 routes over 7
  planes): **never compare to 2440**; compare to the 20H Phase-1 accepted count.
* `audited_heights` must be 20; `min_route_layer_pitch` remains 0.05.
* Glass headroom becomes 0.025 mm at both surfaces (old L2/L19 sat on the glass surfaces).
* expect roughly the same acceptance economics as 21H (F-family gains were small: −31 over 2440);
  the D0 blocker analysis held that 60 % of high-gain candidates are blocked by frozen manual U and
  that large-dz S-curves are infeasible — both constraints are unchanged by the height shift.

---

## 10. Defects / inconsistencies found during the audit
1. **`MOVABLE_PLANES` crash under the 20H profile** — reproduced (`KeyError: 19`); §9.1 item 1.
2. **Stale `best_valid/transition_stats.json`** — 118 mid transitions (Phase-1 copy) while routes
   have 138; `save_best_valid` never writes it (`phase2.py:127-149`). G123’s preflight had to record
   and override it (`AUTHORITY.json` → `superseded_stale_files`). Root/experiment_F copies are also
   stale (120/118) per `preflight_audit.py:1123-1162`.
3. **`run_f.py` rollback restores the start snapshot, not the pre-step geometry** (`:367-369`);
   latent for joint/multi-change steps (§5.3).
4. **Report E0 table prints zeros** — `finalize_phase2.py:261,356-359` reads `arcs['classes']`, absent
   from `analysis/arc_crossing_analysis.json`; real numbers are in `aggregates.totals.class_counts`.
5. **`experiment_F/summary.json` and `near_miss_results.json` contain fields the current source does
   not write** (`summary.note="F core sweep (arc_span) + plain-batch sweeps + near-miss interval
   refinement…"`; `near_miss.runs[]/note`) → they were post-edited by a scratch script (none found in
   the tree). Treat archive `experiments/native_3d_joint_opt_1024/` code snapshot as the frozen
   Phase-2 source; it is byte-identical to the live code for the 9 files it contains
   (`CODE_FILES.json`), but it does **not** include `run_f_plus.py`, `run_f_nearmiss.py`,
   `batch_avoid.py`, `guard.py`, `validate_native3d.py`.
6. **`baseline/` and `checkpoints/` of the Phase-2 output are not produced by any Phase-2 script**
   (`baseline/` is a hand copy of Phase-1 `experiment_C`; `checkpoints/` is empty although the report
   mentions it, `finalize_phase2.py:443`).
7. **`run_e.py:395-396` dead code** (`… if False else None`) and hard-set
   `summary['start_crossings'] = P2.BASELINE_CROSSINGS` (`:408`) — hides the real start count when
   E starts from an improved `best_valid`.
8. **README/code argument mismatch** (`run_d --repairs 30` vs default 40; `run_e --routes 16` vs 14;
   `run_f --time-budget 560` vs 600).
9. **`crossing_intervals` candidate pool came from the 21H E5 world** (2606-crossing layout); the
   20H rebuild must regenerate it, otherwise D’s `s0/s1` coordinates refer to the wrong body flats.
10. **Phase-2 write targets are inside the historical output tree**
    (`outputs/manual_c4_new_connectivity/NATIVE_3D_JOINT_OPT_1024`); the 20H experiment must write
    only under `experiments/COLD_START_20_HEIGHT_1024/` per `coldstart20/bootstrap.bind_run_dir`
    and the scaffold (`05_native3d_abc`, `06_native3d_def`, …).

---

## Appendix A — 20-height table (authoritative, from `coldstart20/model20.py`; verified by import)

| plane_id | label | z (mm) | kind | role |
|---:|---|---:|---|---|
| 2 | L2 | −0.325 | body | Z1-U1 (manual, fixed) |
| 3 | L3 | −0.275 | body | Z1-U2 (manual, fixed) |
| 4 | L4 | −0.225 | body | Z1-U3 (manual, fixed) |
| 5 | L5 | −0.175 | body | Z1-U4 (manual, fixed) |
| 6 | L6 | −0.125 | body | Z1 other opposite |
| 7 | L7 | −0.075 | body | Z1 other opposite |
| 20 | L20 | −0.025 | body | Z1 other opposite |
| 1001 | Z1_INTERFACE | +0.025 | interface_body | Z1 other opposite (direct 2D) |
| 8 | L8 | +0.075 | body | Z1 other opposite |
| 9 | L9 | +0.125 | body | Z2 other adjacent |
| 10 | L10 | +0.175 | body | Z2-U1 (manual, fixed) |
| 11 | L11 | +0.225 | body | Z2-U2 (manual, fixed) |
| 12 | L12 | +0.275 | body | Z2-U3 (manual, fixed) |
| 13 | L13 | +0.325 | body | Z2-U4 (manual, fixed) |
| 14 | L14 | +0.375 | body | Z2 other adjacent |
| 15 | L15 | +0.425 | body | Z2 other adjacent |
| 16 | L16 | +0.475 | body | Z2 other adjacent |
| 1002 | Z2_INTERFACE | +0.525 | interface_body | Z2 other adjacent (direct 2D) |
| 17 | L17 | +0.575 | body | Z2 other adjacent |
| 18 | L18 | +0.625 | body | Z2 other adjacent |

* 20 heights (18 body + 2 interface), pitch exactly 0.05 mm, plane 19 (old +0.65) deleted,
  every survivor +0.025 mm, glass [−0.350, +0.650] unchanged → 0.025 mm headroom at both surfaces.
* `MOVABLE_PLANES` under 20H = `(6,7,20,1001,8,9,14,15,16,1002,17,18)` (12);
  `MANUAL_PLANES` = `(2,3,4,5,10,11,12,13)` (8).
* footprints at R=15 mm: dz 0.05 → 1.731329 mm; 0.10 → 2.447448; 0.20 → 3.458323;
  0.30 → 4.232021; 0.60 → 5.969925; 1.00 → 7.681146; `SHADOW_MM = 1.224745`.

## Appendix B — Phase-2 output inventory & schemas
See §1.5 and §6.3. Key sizes: `routes_l3d.json` 3.64 MB (1024 routes), `crossing_stats.json`
686 KB (2409 events), `blocker_analysis.json` 29.2 MB (5 387 candidates), `arc_crossing_analysis.json`
7.8 MB (2 440 events), `transition_stats.json` 16 KB (138 mid / 69 excursions),
`validation.json` 54 KB (independent), `MANIFEST.json` 125 files.

## Appendix C — Commands
**Historical (21H, reproduced in README/report):**
```
cd OpticalWaveguideRouter2D
.venv\Scripts\python.exe -m four_side_1024.fanout1024.native3d.crossing_intervals
.venv\Scripts\python.exe -m four_side_1024.fanout1024.native3d.blocker_analysis
.venv\Scripts\python.exe -m four_side_1024.fanout1024.native3d.arc_crossing_analysis --baseline <NATIVE_3D_CROSSING_OPT_1024> --out-dir <NATIVE_3D_JOINT_OPT_1024>
.venv\Scripts\python.exe -m four_side_1024.fanout1024.native3d.run_d --screen 80 --repairs 30
.venv\Scripts\python.exe -m four_side_1024.fanout1024.native3d.run_e --routes 16
.venv\Scripts\python.exe -m four_side_1024.fanout1024.native3d.run_f --sweeps 2 --time-budget 560
.venv\Scripts\python.exe -m four_side_1024.fanout1024.native3d.run_f_plus --time-budget 210
.venv\Scripts\python.exe -m four_side_1024.fanout1024.native3d.run_f_nearmiss --time-budget 300
.venv\Scripts\python.exe -m four_side_1024.fanout1024.native3d.finalize_phase2
```
**20H target (to be implemented per §9; bootstrap must be imported before any pipeline module):**
```
.venv\Scripts\python.exe -m four_side_1024.fanout1024.coldstart20.run_initial
.venv\Scripts\python.exe -m four_side_1024.fanout1024.coldstart20.run_native3d_def --stage D
... --stage E ... --stage F ... --stage near-miss ... --stage finalize
```

## Appendix D — Verification performed during this audit
* Read: README/report/SPEC/MANIFEST/SUMMARY, all `logs/*` (UTF-16 console logs decoded), all D/E/F
  sources, `guard.py`, `joint_reroute.py`, `phase2.py`, `finalize_phase2.py`, `crossing_cache.py`,
  `excursion2.py`, `route_model.py`, `single_route.py`, `transition.py`, `common.py`,
  `validate_native3d.py` (model/validate_run), `blocker_analysis.py`/`arc_crossing_analysis.py`/
  `crossing_intervals.py` (headers/CLI/writes), `final_deliverables.py`, `nonc4.crossings`,
  `l3d/world.py`, `l3d/layers.py`, `reheight21/model.py`, `reheight21/validate21.py`,
  `xyzrouter/paths.py`, `xyzrouter/g4/paths.py`, `xyzrouter/preflight_audit.py`,
  `xyzrouter/g4/{contract_audit,independent_metrics}.py`, `coldstart20/{__init__,model20,bootstrap,run_initial}.py`.
* Inspected JSON schemas by loading the artifacts (no recomputation of the pipeline).
* `--help` executed for `run_d, run_e, run_f, run_f_plus, run_f_nearmiss, blocker_analysis,
  arc_crossing_analysis, crossing_intervals` (all import cleanly on Python 3.10.11).
* Imported `coldstart20.bootstrap` and `native3d.common` in a throw-away process and reproduced:
  `N.PLANE_Z` = 20 entries, interface z (0.025, 0.525), `N.MOVABLE_PLANES` still 13 with id 19,
  `N.sorted_by_abs_dz(0.0)` → `KeyError: 19`; then (memory-only, **no file edit**) applied the
  proposed derivation `MOVABLE_PLANES = tuple(pid for pid in PLANE_Z if pid not in MANUAL_PLANES)`
  and confirmed `sorted_by_abs_dz(0.0/0.625)` works and matches the 12 movable heights.
* No pipeline stage was executed; no project file was written except this Markdown.
