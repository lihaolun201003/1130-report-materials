# Multi-arc ON/OFF ablation audit — 21-height → 20-height rebuild

READ-ONLY audit. Written 2026-11-17 ~22:50 local. No file was modified; only
`--help`/import probes and read-only inspection of the ablation archives were used
(no pipeline stage was executed). Ground truth = current source + the three archived
ablation packages (2026-11-16/17).

Audited:

* `four_side_1024/fanout1024/layer2d.py` (switch + geometry policy),
  `four_side_1024/fanout1024/xyzrouter/local_reroute.py` (propagation),
  `four_side_1024/fanout1024/xyzrouter/g4/` (engines used by the arms).
* `experiments/G4_MULTI_ARC_ABLATION_1024/` — historical mixed design
  (RUNBOOK.md, report.md, MANIFEST.json, SHA256SUMS.csv, code_changes/, tools/,
  `baseline_rerun/` (ON rerun), `no_multi_arc/` (Stage-0 conversion + OFF arm)).
* `experiments/G4_MULTI_ARC_ABLATION_FINAL_1024/` — strict common-start design
  (EXPERIMENT_SPEC.md, RUNBOOK.md, README.md, report.md, comparison.md, config/
  FROZEN_CONFIG.json, runs/{on,off}/…, audit/, tables/, validation/, tools/
  `run_arm.ps1`, `run_all_analysis.ps1`, MANIFEST.json, SHA256SUMS.csv).
* `experiments/G4_MULTI_ARC_COLD_START_1024/` — cold-start feasibility attempt
  (`tools/run_cold_start.py`, `_smoke_{on,off}0.log`, `_smoke/{on,off}_seed0/`; all
  formal dirs `multi_arc_on/`, `multi_arc_off/`, `tables/`, `validation/`,
  `algorithm_evolution/`, `logs/`, `figures/`, `code_changes/` are empty).
* 20H seam already in the tree: `four_side_1024/fanout1024/coldstart20/`
  (`model20.py`, `bootstrap.py`, `run_initial.py`) — see §3.

---

## 0. Verdict and the three things that must not be confused

1. **The switch itself is height-agnostic and already correct.** The only changed
   variable is `enable_multi_arc` (`G4_ENABLE_MULTI_ARC` env, default 1), implemented in
   `layer2d.MULTI_ARC_POLICY` and enforced in `_LayerRouter._iter_candidates`; it removes
   exactly one degree of freedom of the frozen planar candidate grammar (two tangent,
   opposite-sweep R15 arcs with no line between them — the `('S', shift)` short-S).
   Nothing about it depends on the number of routing heights (18/19/21) or on the
   +0.025 mm height shift, so for 20H the switch code needs **no change**; only the
   profile/driver/validator plumbing changes (§3).
2. **There are two different experiments and they must stay separate:**
   * *historical package* (`G4_MULTI_ARC_ABLATION_1024`): ON from G3 1322 (contains 197
     multi-arc routes) vs OFF **after Stage-0 conversion** to a 0-multi-arc state
     (1322→3967); wall budgets differ (ON 3119 s vs OFF 1994 s, OFF G4d stopped early).
     Result 1202 vs 3484 (+2282). This measures **A + B + C**.
   * *strict package* (`G4_MULTI_ARC_ABLATION_FINAL_1024`): both arms read the **same
     converted start** (3967, 0 multi-arc regions, SHA `1707e189…`), only the env var
     differs, equal counted budget (d56=24000, checks guard=9000), 3 seeds.
     Result ON 2203 vs OFF 3601 mean (paired −1398). This measures **B only**.
3. **The cold-start package was not a controlled ON/OFF comparison.** It asked whether
   the ablated grammar can build a legal 1024-route layout *from an empty route set*
   (stages A–E). Only smoke runs ever completed: 21H ON = 1024/1024 legal, 11,890
   crossings (216 s); 21H OFF **failed stage C** at plane L20 (41/52 first pass) and
   produced no routes at all. That is a feasibility signal, not an ON/OFF effect size,
   and it is **not reusable as the common start** for the strict 20H ablation (§4).

---

## 1. The exact arm protocol

### 1.1 Single changed variable: where the switch lives in code

| location | role |
|---|---|
| `four_side_1024/fanout1024/layer2d.py:226-241` | `MULTI_ARC_POLICY` reads `G4_ENABLE_MULTI_ARC` (default `'1'`, false for `0/false/no/off`); `multi_arc_enabled(cfg)` — explicit `cfg['enable_multi_arc']` wins over env. Installed *on import*; the **before-import** env requirement is real (see cold-start driver: it sets `os.environ` before importing layer2d) |
| `layer2d.py:244-290` | `local_multi_arc_regions(primitives)`: the exact geometric definition. Scans each flat chain for maximal tangent-continuous arc runs (`p1≈p0`, tangent gap ≤1e-6); a run is a *real* multi-arc region iff length ≥2, **different centres** (same-centre run = `same_circle_split`, not counted) and **both sweep signs** (`kind='multi_arc'`; same-sign-different-centre is kept only as a guard). Returns `first, n_arcs, kind, signs, start, end` |
| `layer2d.py:293-301` | `spec_uses_multi_arc(spec)`: build-free cheap prefilter — any `('S', shift)` move in the spec, else inspect already-built primitives |
| `layer2d.py:1207-1217` | `_LayerRouter.__init__` reads the policy once (`self.enable_multi_arc`) |
| `layer2d.py:1299-1352` | `_iter_candidates`: **(1)** when disabled, drop specs with `('S', shift)` *before* building them (saves build budget); **(2)** after each candidate is built, hard geometric gate `if not self.enable_multi_arc and local_multi_arc_regions(world): reject` (counts `multi_arc_rejected_candidates`, reason `multi_arc_forbidden`) |
| `four_side_1024/fanout1024/xyzrouter/local_reroute.py:112-131` (`xy_candidates`) | `router_cfg['enable_multi_arc'] = L2.multi_arc_enabled(cfg)` — every G4 candidate path (`joint_world.plan_candidates/plan_forced`, `make_way` probes, `group_replan`) goes through this function, so the policy is enforced uniformly for all search arms |
| `g4/alns.py:184` comment | states the FINAL ablation code is identical to the historical ablation code; only the numbers differ (`layer2d.py` SHA `712ebc54…`, `local_reroute.py` SHA `80820624…` in both packages' `code_changes/*.after`) |
| frozen patch | historical `code_changes/g4_multi_arc.patch`: pure increment, 110 lines added / 0 removed; default (env unset) behavior identical to the 2026-11-04 archive |

Explicitly **not** affected by the policy: `Z`/staircase families (arcs at different
corners separated by straight lines), `same_circle_split` (one circle stored as two arc
records, e.g. `middle=0` U-turn), and the **3-D z-lift R15 S-transition** (`kind=
'transition'`, never part of a flat chain).

### 1.2 How the OFF state is produced from an ON start (geometry conversion)

The inherited ON start contains globally optimized geometry that *uses* short-S. A true
OFF system must express the same connections in the ablated grammar. `tools/
convert_multi_arc.py` (historical package) does exactly that — **no hand-editing of arcs,
no polyline replacement**:

1. run with `G4_ENABLE_MULTI_ARC=0` (the tool sets it via `os.environ.setdefault` before
   importing `layer2d`); load the start via `AB.ArmSpec('stage0_convert', start_dir=…)`
   + `AB.ArmContext.load()`;
2. detect target routes = routes whose flat parts have a `local_multi_arc_regions` entry
   (197/1024 on the 21H G3 start; **must be recomputed for 20H, do not assume 197**);
3. for each target route, in the same true-3D world, call
   `jw.plan_candidates(rid, cfg=JW.PLAN_CFG, mode='clean')` (the exact G4 search planner:
   3 free target heights, 2 lead pairs, 160/320 prescreen, `d56_top=16`, 4 candidates);
4. choose the deterministic best (minimum exact crossing delta, then shortest) legal
   candidate; commit via `jw.replace_one(...)`; if there is **no** legal candidate the
   route keeps its old geometry and is reported as **residual** (never silently deleted,
   never force-replaced by a polyline); a defensive check rejects any candidate that still
   contains a local multi-arc region (`policy_leak`);
5. after all targets: assert the output has 0 multi-arc routes; run the frozen
   independent validator; write `conversion_report.json` (per-route records: old/new
   region counts, family, kind, delta, commit delta, layer, z, length, total after,
   seconds; plus `{start_sha256, start_crossings, routes_sha256, converted, residual,
   multi_arc_routes_before/after, policy_leaks, crossings_after,
   crossing_delta_from_start, seconds, ledger, validation}`).

**Cost separation (mandatory):**

| effect | definition | 21H value |
|---|---|---|
| **A** conversion cost | crossing delta when the inherited ON geometry is re-expressed in the OFF grammar, measured with the frozen crossing audit; separately replayed route-by-route in `analyze_stage0.py` / `tables/stage0_audit.json` | 1322 → 3967 = **+2645** (197 routes; 145 routes with lateral offset `<2R=30 mm`: +2646; 52 routes `≥2R`: −1; replacement families OPP_DETOUR 80, OPP_DETOUR_BACK 64, OPP_Z 39, ADJ_L 12, ADJ_UP_LOOP 2) |
| **B** search-ability difference | same start (post-conversion, 0 multi-arc), same code, same candidate-evaluation budget, only `enable_multi_arc` toggled | FINAL: ON 2203 vs OFF 3601 mean (−1398) |
| **C** total historical difference | ON final vs OFF final from the historical mixed package (= A + B + budget inequality + start difference) | 1202 vs 3484 (+2282); archived 1185 vs 3484 (+2299) |

Do **not** attribute C to the geometry; do **not** compare the historical ON start (1322)
with the OFF start (3967) as if it were an ablation of search ability.

### 1.3 Historical (mixed) result summary

| item | ON (`baseline_rerun/`) | OFF (`no_multi_arc/`) |
|---|---|---|
| start | G3 `711cf910…`, 1322, 197 multi-arc routes | Stage-0 converted `1707e189…`, 3967, 0 multi-arc routes |
| search | G4c_free 1800 s + G4d 1200 s, seed 20261104 | same, but G4d stopped early at checkpoint step_00009 (158 s); total 1994 s vs 3119 s |
| final | **1202 / 1143 pairs** (archived 1185/1124 is the 2026-11-04 run) | **3484 / 2707 pairs** (max 41, length 165,059.1 mm = +5.3 %) |
| validator | PASS, 0 violations | PASS, 0 violations, `multi_arc_regions = 0` (geometric audit) |
| multi-arc regions in final | 204 (197 routes) | 0 |
| d56 / route_3d_checks | 66,962 / 8,162 | 40,403 / 4,774 |

Key intermediate decomposition in the historical report: OFF search itself recovered −483
(3967→3484), more than ON recovered (−120, 1322→1202); the difference is the *expression*
cost, not "better optimization". The 2R (30 mm) threshold is the mechanism: two independent
R15 quarter-turns can only shift the path by ≥2R+w; sub-2R lateral offsets become
≥4R detour loops.

### 1.4 Strict (FINAL) result summary (main result to carry forward)

Primary experiment: equal candidate-evaluation budget, `d56_candidate_evals = 24000`
(secondary guard `route_3d_checks = 9000`, wall safety 5400 s), seeds
`20261104 / 20261116 / 20261130`, both arms from the **same** `routes_l3d.json`
(`1707e189…`, 3967 crossings, 2942 pairs, 677 routes with crossings, max 45, 0 multi-arc
regions, 1024/1024 routed, validator PASS).

| metric (mean of 3 seeds) | common start | ON | OFF | paired diff |
|---|---|---|---|---|
| crossings | 3967 | **2203.0** (2203/2197/2209) | **3601.0** (3583/3613/3607) | **−1398.0** |
| unique crossing pairs | 2942 | 1983.3 | 2763.3 | −780.0 |
| routes with crossings | 677 | 779.3 | 847.0 | −67.7 |
| max crossings/route | 45 | 33.0 | 40.7 | −7.7 |
| total length (mm) | 165104 | **157209.0** | 165021.3 | −7812.4 (−4.73 %) |
| multi-arc regions | 0 | 197.0 | **0** | — |
| d56_candidate_evals | — | 24073 | 24064 | +9 (frozen cap 24000; overshoot ≤0.64 %) |
| route_3d_checks | — | 4234.7 | 2998.0 | +1236.7 |
| search wall clock (s) | — | 1226.3 | 1136.8 | +89.5 (records only) |

Auxiliary equal-wall experiment (`--seconds 900`, no counted caps): ON 2125.3 vs OFF
3535.0 (−1409.7). Cost-normalized comparisons: equal d56 (3000/6000/12000/24000) gives
−684/−911/−1037/−1393; equal r3d (500/1000/2000/2943) gives −819/−969/−1080/−1263.
Verdict per pre-registered rules (`EXPERIMENT_SPEC.md` §9): **A — strict control supports
a real advantage of the planar multi-arc freedom** (3/3 seeds same direction, effect
≥200 crossings, length not worse, all hard gates pass). Statistical claim is explicitly
exploratory (3 seeds, no significance test, one machine).

Hard gates per run (any failure invalidates the run even if crossings are lower):
1024/1024, 0 failed, identity/ports unchanged; `min flat R = 15.0 mm`; sampled transition
R ≥ 15 − 1e-6; `min_3d_clearance ≥ 0.05`; `min non-crossing centreline ≥ 0.08`;
`violation_count = 0`, `validation_pass = True`; **OFF arm: multi-arc regions = 0 by
geometric audit**. Independent validation in the FINAL package: engine-embedded validator
+ a fresh-process `validate_xyz --manual-policy fully_optimizable` into
`<run>/validation_final/`, plus `tools/audit_state.py` recomputing crossings and
multi-arc regions independently; `validator.same_plane_crossings == audit.crossings`
and SHAs must agree.

---

## 2. Exact commands, budgets, seeds, validator, artifacts

### 2.1 Historical package (`G4_MULTI_ARC_ABLATION_1024`)

```powershell
# environment / working dir: project root; python = .venv\Scripts\python.exe
# 1) baseline layer figures + multi-arc geometry audit + archived-1185 validator recheck
python -m four_side_1024.fanout1024.xyzrouter.g4.plots_g4 layer-suite `
  --run-dir "…\work\11.9-second-report-all-work\g4_xyz_joint_1024\03_best_valid" `
  --out-dir experiments\G4_MULTI_ARC_ABLATION_1024\layer_figures\G4_baseline `
  --prefix G4_baseline --title "G4 original (1185 crossings)"
python experiments\G4_MULTI_ARC_ABLATION_1024\tools\audit_flat_multi_arc.py `
  outputs\manual_c4_new_connectivity\XYZ_JOINT_G123_1024\best_valid `
  "…\g4_xyz_joint_1024\03_best_valid" `
  --out experiments\G4_MULTI_ARC_ABLATION_1024\baseline_audit `
  --label G3_start_1322,G4_best_1185
python -m four_side_1024.fanout1024.xyzrouter.validate_xyz `
  --run-dir "…\g4_xyz_joint_1024\03_best_valid" `
  --out-dir experiments\G4_MULTI_ARC_ABLATION_1024\validation\baseline_G4_best_1185 `
  --manual-policy fully_optimizable --baseline-dir outputs\...\baseline_authoritative

# 2) policy self-test: every candidate under OFF must have 0 multi-arc regions
python experiments\G4_MULTI_ARC_ABLATION_1024\tools\test_multi_arc_policy.py

# 3) Stage-0 OFF conversion of the ON start
$env:G4_ENABLE_MULTI_ARC = '0'
python experiments\G4_MULTI_ARC_ABLATION_1024\tools\convert_multi_arc.py `
  --start-dir outputs\manual_c4_new_connectivity\XYZ_JOINT_G123_1024\best_valid `
  --out-dir   experiments\G4_MULTI_ARC_ABLATION_1024\no_multi_arc\01_convert

# 4) the two arms (each: G4c_free 1800 s → validate → G4d 1200 s → validate; serial)
powershell -NoProfile -ExecutionPolicy Bypass -File `
  experiments\G4_MULTI_ARC_ABLATION_1024\tools\run_arm_chain.ps1 -Arm on    # start = G3 (1322)
powershell -NoProfile -ExecutionPolicy Bypass -File `
  experiments\G4_MULTI_ARC_ABLATION_1024\tools\run_arm_chain.ps1 -Arm off   # start = 01_convert (3967)

# 5) analysis / figures / manifest
python experiments\G4_MULTI_ARC_ABLATION_1024\tools\analyze_conversion.py
python experiments\G4_MULTI_ARC_ABLATION_1024\tools\make_report_artifacts.py `
  --baseline "…\g4_xyz_joint_1024\03_best_valid" `
  --nomat experiments\G4_MULTI_ARC_ABLATION_1024\no_multi_arc\03_G4d\best_valid `
  --out experiments\G4_MULTI_ARC_ABLATION_1024
python experiments\G4_MULTI_ARC_ABLATION_1024\tools\build_summary.py
python experiments\G4_MULTI_ARC_ABLATION_1024\tools\build_manifest.py
```

Inside `run_arm_chain.ps1`, each arm executes exactly (recorded in
`<arm>/chain_console.log`):

```powershell
python -m four_side_1024.fanout1024.xyzrouter.g4.run_g4_engine `
  --arm G4c_free --seconds 1800 --seed 20261104 `
  --start-dir <start> --out-dir <arm>\02_G4c_free --tag ablation_<arm>
python -m four_side_1024.fanout1024.xyzrouter.validate_xyz `
  --run-dir <arm>\02_G4c_free\best_valid --out-dir <arm>\02_G4c_free\validation `
  --manual-policy fully_optimizable --baseline-dir outputs\...\baseline_authoritative
python -m four_side_1024.fanout1024.xyzrouter.g4.run_g4_engine `
  --arm G4d --seconds 1200 --seed 20261104 `
  --start-dir <arm>\02_G4c_free\best_valid --out-dir <arm>\03_G4d --tag ablation_<arm>
python -m four_side_1024.fanout1024.xyzrouter.validate_xyz `
  --run-dir <arm>\03_G4d\best_valid --out-dir <arm>\03_G4d\validation `
  --manual-policy fully_optimizable --baseline-dir outputs\...\baseline_authoritative
```

Arm budget/seed table: ON `G4_ENABLE_MULTI_ARC=1`, start G3 `711cf910…` (1322), G4c_free
1800 s + G4d 1200 s, seed 20261104; OFF `G4_ENABLE_MULTI_ARC=0`, start `01_convert`
`1707e189…` (3967), same budgets, seed 20261104, **G4d stopped early at step_00009
(158 s)** → OFF total 1994 s vs ON 3119 s (the RUNBOOK explicitly declares this
asymmetry; 3484 is therefore a restricted-grammar **upper bound**, not a converged value).
Per-run artifacts are exactly the G4 arm artifact set (`routes_l3d.json`,
`assignment_1024.csv`, `crossing_stats.json`, `summary.json`, `strategy_stats.json`,
`budget_ledger.json`, `config.json`, `failed_attempts.json`,
`optimization_history.csv`, `best_valid/`, `checkpoints/`, `validation/`, `run.log`)
plus `04_final/` materialized by `tools/materialize_final.py` (routes/assignment byte
copies, engine-computed crossing_stats/summary, copied validation, final SHA256.json).

### 2.2 FINAL package (`G4_MULTI_ARC_ABLATION_FINAL_1024`, strict common start)

Pre-frozen design: `EXPERIMENT_SPEC.md` + `config/FROZEN_CONFIG.json` (452 source-file
hashes; policy code byte-identical to the historical `*.after`: `layer2d.py`
`712ebc54…`, `local_reroute.py` `80820624…`). Only 6 g4 files differ from the 2026-11-04
archive and only for budget scheduling/accounting:
`alns.py` (+`counted_d56`/`counted_checks_guard` schedule, `counted_used`,
`_counted_exhausted`, history `d56/r3d/xy` columns, `extra.counted_budget`),
`run_g4c/run_g4d/run_g4_engine` (new flags), `arm_base/artifacts`
(`state.start_total` replaces hardcoded `GP.START_CROSSINGS`); patch
`code_changes/g4_equal_budget.patch` (+176/−13).

Runbook "one-liner" (actual commands):

```powershell
cd "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D"
# PRIMARY: equal candidate-evaluation budget (d56=24000), 2 arms × 3 seeds, serial
foreach ($seed in 20261104,20261116,20261130) {
  foreach ($arm in 'on','off') {
    powershell -NoProfile -ExecutionPolicy Bypass -File `
      experiments\G4_MULTI_ARC_ABLATION_FINAL_1024\tools\run_arm.ps1 `
      -Arm $arm -Tag "c1_${arm}_$seed" -Seed $seed `
      -CountedD56 24000 -CountedChecks 9000 -Seconds 5400
  }
}
# AUXILIARY: equal wall clock (900 s)
foreach ($seed in 20261104,20261116,20261130) {
  foreach ($arm in 'on','off') {
    powershell -NoProfile -ExecutionPolicy Bypass -File `
      experiments\G4_MULTI_ARC_ABLATION_FINAL_1024\tools\run_arm.ps1 `
      -Arm $arm -Tag "a1_${arm}_$seed" -Seed $seed -Seconds 900
  }
}
# analysis chain (idempotent; never touches runs/)
powershell -NoProfile -ExecutionPolicy Bypass -File `
  experiments\G4_MULTI_ARC_ABLATION_FINAL_1024\tools\run_all_analysis.ps1 `
  -Seeds "20261104,20261116,20261130"
```

`run_arm.ps1` (115 lines) does exactly: set `G4_ENABLE_MULTI_ARC` (1/0; the only changed
variable), start dir = frozen converted start (default
`work/1130-report-materials/G4_MULTI_ARC_ABLATION_1024/no_multi_arc/01_convert`), then

```powershell
python -m four_side_1024.fanout1024.xyzrouter.g4.run_g4_engine `
  --arm G4c_free --seconds $Seconds --seed $Seed `
  --start-dir $StartDir --out-dir <runs>\<arm>\<tag> --tag <tag> `
  [--counted-d56-budget $CountedD56] [--counted-checks-guard $CountedChecks]
```
then a **fresh-process** validator into `<run>/validation_final/`:
`validate_xyz --run-dir <run>/best_valid --out-dir <run>/validation_final
--manual-policy fully_optimizable --baseline-dir outputs\...\baseline_authoritative`,
then writes `run_meta.json` (`arm, tag, seed, g4_enable_multi_arc, start_dir, out_dir,
counted_d56_budget, counted_checks_guard, wall_safety_net, started/finished, engine_exit,
validator_exit, python, host`). Logs are teed to `<run>/console.log`,
`<run>/validation_final.log`, and copied to `logs/`.

`run_all_analysis.ps1` (94 lines) runs, in order: `collect_results.py --with-audit`
→ `summarize.py --prefix c1` and `--prefix a1` → `plot_search_curves.py --tag-prefix c1`
and `a1` → `analyze_stage0.py` → `analyze_repair.py` per seed → `analyze_gap.py --seed
20261104` → `plot_layers.py` (start / ON / OFF) → `plot_2r.py` → `plot_2r_repair.py` →
`route_cases.py` → `make_validation_summary.py`; then `assemble_archive.py` and
`build_manifest.py` for the archive.

Budgets/seeds/validator/artifacts:
* primary counted mode: stop when `d56_candidate_evals` grows by 24000 since search
  start (absolute ledger marks split by frozen shares; sweep 0.18 + stages
  0.22/0.24/0.26/0.28); secondary hard guard `route_3d_checks ≥ 9000`; wall 5400 s is a
  pure safety net (not reached: measured ~1000–1550 s per run);
* auxiliary: `--seconds 900`, no counted caps (engine wall schedule);
* seeds fixed before the run: 20261104, 20261116, 20261130 (same for main and aux);
* validator: engine-embedded + new-process `validation_final/` + independent
  `audit_state.py` recompute; all must agree with the run SHA/stats;
* artifacts per run: `routes_l3d.json`, `assignment_1024.csv`, `crossing_stats.json`,
  `summary.json`, `summary_g4.json`, `strategy_stats.json`(+`_partial`),
  `failed_attempts.json`, `budget_ledger.json`, `config.json`, `optimization_history.csv`,
  `run.log`, `console.log`, `run_meta.json`, `best_valid/`, `checkpoints/`,
  `validation/`, `validation_final/`, `validation_final.log`, `SHA256.json`;
  package-level: `audit/*`, `tables/*` (runs.csv/json, summary_c1/a1.md, stage0_audit,
  param_2r*, repair_*, search curves, gap analysis), `figures/*`, `validation/summary.*`,
  `results/INDEX.*`, `MANIFEST.json`, `SHA256SUMS.csv`.

Historical vs FINAL relationship (from `comparison.md`): historical "1185 vs 3484"
mixes A (+2645) with B and with unequal budgets; FINAL only measures B. The historical
OFF arm's search gain (−483) was larger than ON's (−120), so "multi-arc makes the
optimizer smarter" is not supportable; "multi-arc is the compact expression for sub-2R
lateral offsets" is supported by both the parametric 2R analysis and the per-route repair
analysis (142/197 converted routes re-used multi-arc geometry in ON; 145 sub-2R routes
contributed +2646 of the conversion cost).

---

## 3. What must change for a controlled ON/OFF comparison on a 20H common start

### 3.1 Prerequisites

1. **A legal 20H common start.** Preferred: the 20H G3 best solution produced by the
   20H cold-start + native-3D G1/G2/G3 chain (`07_g123/best_valid`), then its Stage-0
   OFF conversion (§1.2) — exactly the FINAL design transferred to 20H. The 20H stage-A
   assignment already exists (`03_fanout_and_xy/run_initial_20h/assignment_1024.csv`,
   20 planes, 1024 rows, 368 manual, 100 direct, 924 transitions/1848 endpoints; produced
   2026-11-17 22:38), but **no 20H routed state or G3 output exists yet**, so this is
   blocked on the 20H routing chain.
2. Recompute the conversion target set: the number of start routes with planar multi-arc
   regions is a property of the 20H start (21H G3 had 197; 20H will differ). Do not
   hardcode 197.
3. All tools that import `layer2d` / `g4` / `reheight21.model` must install the 20H
   profile first. `model20` + `bootstrap` already exist and were verified read-only:
   `bootstrap.install()` registers `model20` under `reheight21.model`, re-points
   `common.INTERFACE_Z`/`l3d.layers.INTERFACE_ROWS` to z1=+0.025 / z2=+0.525, and resets
   the stack; probe output: `profile=20_height_raised, planes=20, body=18,
   min pitch 0.04999999999999993, stack routing ids (2..18,20)`.

### 3.2 Concrete porting list

| tool / file | change for 20H |
|---|---|
| `layer2d.py` switch (`226-301`, `1215`, `1311`, `1335`) | **no change**; policy is height-agnostic |
| `local_reroute.xy_candidates` (`:126`) | no change (propagates policy) |
| `tools/convert_multi_arc.py` | import `coldstart20.bootstrap` before `layer2d`/g4; profile-aware start loader (`GP` 20H paths / explicit `--start-dir`); keep same planner cfg and deterministic acceptance; keep residual reporting; assert 0 multi-arc for strict OFF; validator = 20H wrapper |
| `tools/audit_flat_multi_arc.py`, `test_multi_arc_policy.py` | same bootstrap requirement; audit uses `layer2d.local_multi_arc_regions` (height-agnostic) and layer tables from the run → works for 20H; recompute counts |
| `tools/run_arm_chain.ps1` / `run_arm.ps1` | parameterize project root + experiment root + start dir (already mostly parameterized in FINAL); 20H start dir; same env-var switch; 20H validator wrapper in the fresh-process validation step |
| `g4/paths.py` | 20H G4 root/start/fingerprint; see `00_audit/g4.md` §3/§8 (shared prerequisite) |
| `g4/artifacts.run_validation` + `tools/make_validation_summary.py` / `audit_state.py` | launch validator under the 20H profile; report `model_height_count=20` |
| `tools/collect_results.py`, `summarize.py`, `plot_search_curves.py`, `analyze_repair.py`, `analyze_gap.py`, `plot_layers.py`, `route_cases.py` | read `<run>/summary*.json`, `strategy_stats.json`, `best_valid` — largely profile-agnostic; check any hardcoded 21/height labels in tables/plots; `plot_layers` should take the 20H height labels from `layer_planes.json`/model |
| `tools/param_2r*.py`, `plot_2r*.py` | mechanism analysis is geometry (2R=30 mm) and height-agnostic; re-run, update labels |
| `EXPERIMENT_SPEC`/`RUNBOOK`/`report`/`comparison` | new 20H pre-frozen copy: start SHA/crossings computed from the 20H converted start; keep the same three-effect A/B/C definitions, budget, seeds, decision rules and hard gates |
| archive/manifest | new `experiments/COLD_START_20_HEIGHT_1024/09_multi_arc_ablation/` with the same layout (`runs/{on,off}/<tag>`, `audit/`, `tables/`, `figures/`, `validation/`, `config/FROZEN_CONFIG.json`, `MANIFEST.json`, `SHA256SUMS.csv`) |

### 3.3 Pre-registration / risk (must be decided before running 20H)

* **Most important risk: OFF may not be reachable.** The 21H cold-start OFF smoke already
  failed to route plane L20 (41/52 first pass, 11 failed) and aborted without a solution;
  20H has one body plane fewer (no L19) and a smaller set of legal escape heights, so the
  Stage-0 conversion may leave `residual > 0` (routes with no single-arc expression in the
  reduced grammar). Because the OFF gate requires `multi_arc_regions == 0`, a nonzero
  residual means **the strict common start does not exist** for 20H. Pre-register the
  handling now: report A per route (conversion cost / residual routes) as the 20H
  grammar-feasibility result; do **not** run a diluted OFF arm (keeping residual ON
  geometry would silently re-introduce the variable). If residual hits 0, proceed with
  the FINAL design unchanged.
* If the 20H G3 state is itself expensive to convert, consider a secondary start (e.g.
  the 20H cold-start ON layout) only for a *feasibility* experiment, not for effect B.
* Budgets: keep the FINAL primary `d56=24000 / checks=9000` (declared before the run),
  wall safety 5400 s; 3 seeds; same validator protocol and hard gates. Because 20H may
  run faster, changing the wall safety net is allowed only if declared before running.
* Keep the same decision rule (A/C/B from `EXPERIMENT_SPEC.md` §9) and the explicit
  "exploratory statistics (3 seeds, no significance test)" caveat.

### 3.4 Expected command template (20H)

```powershell
# 0) prerequisites: 20H G3 best_valid exists; 20H profile installed in every driver
$G3  = "experiments\COLD_START_20_HEIGHT_1024\07_g123\best_valid"
$EXP = "experiments\COLD_START_20_HEIGHT_1024\09_multi_arc_ablation"

# 1) audit the 20H start geometry (multi-arc regions count) + policy self-test
python …\coldstart20\drivers.py --run audit_flat_multi_arc --start-dir $G3 --out $EXP\baseline_audit
python …\coldstart20\drivers.py --run test_multi_arc_policy

# 2) Stage-0 conversion of the 20H ON start to the OFF grammar (measure effect A)
$env:G4_ENABLE_MULTI_ARC = '0'
python …\coldstart20\drivers.py --run convert_multi_arc --start-dir $G3 --out-dir $EXP\common_start_off

# 3) strict ON/OFF arms from the SAME converted start, equal counted budget, 3 seeds
foreach ($seed in 20261104,20261116,20261130) {
  foreach ($arm in 'on','off') {
    powershell -File $EXP\tools\run_arm.ps1 -Arm $arm -Tag "c1_${arm}_$seed" -Seed $seed `
      -StartDir $EXP\common_start_off -CountedD56 24000 -CountedChecks 9000 -Seconds 5400
  }
}
# 4) analysis chain (collect → summarize → curves → repair/gap → layers/2R → validation)
powershell -File $EXP\tools\run_all_analysis.ps1
```

---

## 4. `G4_MULTI_ARC_COLD_START_1024` — what "cold start" meant, what actually ran, reuse

### 4.1 What cold start meant there

`tools/run_cold_start.py` (172 lines) drives the **complete automatic routing pipeline
from an empty route set**, not a re-optimization of an existing solution:

```
A  reheight21.assign21 : connection table -> per-route body plane; manual-U groups fixed
B  R15 3-D fanout      : transition / interface-direct landing poses
C  layer2d per-height 2D routing  <- the ONLY stage the enable_multi_arc switch changes
D  full 3-D assembly + strict 0.05 mm World check
E  joint repair (lead re-plan / whole-plane rip-up & re-solve) until the best fully legal
   1024-route solution is frozen
F  final experiment-D summary
```

Nothing from G3/G4 is loaded; inputs are only the 1024 connections, the manual-U layer
template and the process rules. The driver sets `G4_ENABLE_MULTI_ARC` **before importing
layer2d**, re-binds `reheight21.model` writable paths through
`nonc4.paths.use_experiment(out_dir)`, adds seed plumbing by patching
`run21._route_all_layers` (base offset on the `ordering_seed`; without it the pipeline is
deterministic), calls `run21.run_stages('ABCDE', max_iters=3)`, then `validate21.main`
and writes `cold_start_run.json` (policy, seed, stages, timings, routed/failed, stats,
validation, crossing totals, routes SHA).

Purpose: answer **"can this candidate grammar build a fully legal 1024-route layout from
scratch?"** — i.e. a geometry-expressiveness/feasibility question, not "which grammar
searches better". It was the natural precursor to the strict common-start ablation.

### 4.2 What actually ran (only smoke, seed 0, 21H model, 2026-11-16/17)

Formal output dirs (`multi_arc_on/`, `multi_arc_off/`, `tables/`, `validation/`,
`algorithm_evolution/`, `logs/`, `figures/`, `code_changes/`) are **empty**. Only
`_smoke/on_seed0` and `_smoke/off_seed0` were produced:

| item | ON | OFF |
|---|---|---|
| policy log | `multi_arc=True, source=env:G4_ENABLE_MULTI_ARC` | `False, source=env:G4_ENABLE_MULTI_ARC` |
| stages | A–F, seed 0 | A–F, seed 0 |
| stage A/B | 20 planes? no — 21H model: 1024 rows, 21 planes, 21 distinct heights, min pitch 0.05, 368 manual, 100 direct, 924 transitions | same |
| layer2d (stage C) | all 21 planes routed 1024/1024, 11.7 s | **failed plane L20 (z=−0.05)**: first pass routed 41/52, 11 failed → pipeline stopped, no `routes_l3d.json`, no `cold_start_run.json` |
| stages D/E | assembled 1024/1024, world violations 0, 2 repair iterations | not reached |
| final | 1024/1024, 0 failed, **11,890 crossings / 9,797 pairs**, max 83/route, min non-crossing 0.0807 mm | — |
| validator | PASS, 0 violations (42.6 s) | — |
| time / SHA | pipeline 216.3 s + validation 42.6 s = 258.9 s; routes SHA `b15536d2…` | — |

Interpretation: on the 21H cold start, the multi-arc grammar can build a legal fully
routed layout (though with ~9× more crossings than the optimized G3 1322 — cold start is a
one-pass + repair construction, not the G4 ALNS), while the OFF grammar did not even
finish the 2D layer at L20 with this seed. Therefore "11890 vs (none)" is a feasibility
asymmetry, not an ON/OFF effect; and the OFF failure mode (plane-level unrouted routes) is
the same risk that now threatens the 20H Stage-0 conversion (§3.3).

### 4.3 Reusability for the new 20H cold start — yes for feasibility, no for the strict ablation

* **The 20H cold-start code already exists and is the right vehicle**: `coldstart20.model20`
  (authoritative 20H model, same public API as `reheight21.model`, including `RUN_DIR`,
  `MANUAL_GROUPS`, `CONTRACT_*`, `SPEC_*`), `coldstart20.bootstrap` (installs the profile
  into the frozen pipeline by module-key swap + interface-constant re-pointing, with
  `assert_20_height_profile`), and `coldstart20.run_initial` (the 20H equivalent driver:
  `--stages ABCDEF --max-iters --run-dir --skip-assign`, installs/binds profile, runs
  `assign21.main()` then `run21.run_stages`). The 20H stage-A assignment has already been
  produced through this path (20 planes, 1024 rows).
* **What is still missing for a 20H cold-start ON/OFF pair**:
  1. seed plumbing (`run_initial` has no `--seed`; add the `run21._route_all_layers`
     ordering-seed patch used by the 21H `run_cold_start.py`, or equivalent);
  2. graceful failure capture (the 21H OFF smoke aborted without a record; the 20H
     driver should wrap stages C/D/E and write a `cold_start_run.json` with
     `status=failed, unrouted_ids, failing_plane` rather than raising);
  3. the multi-seed matrix (3 seeds, ON/OFF, stages A–F) that the empty formal dirs
     anticipate, plus validators and the archive/build scripts (`algorithm_evolution/`,
     `tables/`, `validation/`, `figures/` are all still empty);
  4. the profile-aware validator wrapper (`validate21` is already profile-generic via
     `M.SPEC_*`; run it after bootstrap).
* **What it must not be used for**: the strict ON/OFF search ablation's common start.
  Cold start produces a different, much worse start geometry (11,890 vs 1322 on 21H) and
  the two arms cannot even share a start (OFF may not exist). Keep the two experiments
  separate and report their different questions:
  * *cold-start feasibility*: can the grammar build a legal 1024 layout at all
    (ON vs OFF, per plane failure reasons, routed count) — reuse the cold-start driver;
  * *strict search ablation*: effect B on a common converted start — reuse the FINAL
    package, with the 20H G3 start (§3).
* For 20H specifically, the cold-start ON result is still valuable as a **fallback legal
  20H solution** if the 20H G3 chain is delayed/blocked, and as the only current evidence
  on whether the 20H OFF grammar is feasible at all. But it must be labelled
  "cold-start, seed 0, non-optimized" and never mixed into effect A/B/C or the G4
  chain numbers.

---

## 5. Adaptation checklist (multi-arc, condensed)

1. [ ] Produce a legal 20H ON start (preferably 20H G3 `07_g123/best_valid`); record its
   SHA/crossings/profile in `START.json`.
2. [ ] Re-run the multi-arc geometry audit on that start (do not assume 197 routes).
3. [ ] Port `convert_multi_arc.py` to 20H: bootstrap-first, profile-aware start loader,
   deterministic same planner, residual reporting, strict OFF assertion, 20H validator;
   measure effect **A** = crossing delta (and per-route table).
4. [ ] If residual > 0: declare the strict OFF common start infeasible (a scientific
   result; do not run a diluted OFF arm); otherwise freeze the converted start
   (`common_start_off`, SHA) and pre-register it.
5. [ ] Copy the FINAL framework as `09_multi_arc_ablation/`: `EXPERIMENT_SPEC` (20H
   invariants), `config/FROZEN_CONFIG.json`, `tools/run_arm.ps1` (profile wrapper, 20H
   start, counted flags), `run_all_analysis.ps1`, `tools/audit_state.py`,
   `collect/summarize/plot/validation` scripts.
6. [ ] Run primary (d56=24000/checks=9000, 3 seeds) + auxiliary (900 s) ON/OFF; verify
   every run passes the hard gates and OFF `multi_arc_regions == 0`; re-run the frozen
   independent validator and the independent geometry audit; keep 21H results as history
   only.
7. [ ] Keep the cold-start experiment separate: 20H ON/OFF cold start = feasibility
   (routed count, failing planes, legal validator), not effect B.

---

## Appendix — evidence notes

* 21H switch code byte-identical between the historical and FINAL packages
  (`layer2d.py` `712ebc54…`, `local_reroute.py` `80820624…`; historical patch +110/−0).
* FINAL common start SHAs: routes `1707e189c271c94723af2a7ba304a2cd1deb52955216eff7e063851b964eb15f`,
  assignment `ec6e394c41eb090160ba6770644505b0438851650d8503e3909cc7218bf8ec6d`;
  3967 crossings / 2942 pairs / 677 routes with crossings / max 45 / 0 multi-arc regions /
  1024 routed / validator PASS.
* FINAL primary counted stop values: d56 = 24006–24154 per run (overshoot ≤0.64 %);
  ON r3d ≈ 4133–4388, OFF r3d ≈ 2943–3056; wall 1049–1537 s (ON) / 1105–1158 s (OFF).
* Historical conversion report: 197 targets, converted 197, residual 0, policy leaks 0,
  1322 → 3967, conversion 577 s; OFF final 3484/2707 (validator PASS, min 3D 0.068629);
  ON rerun final 1202/1143 (validator PASS).
* Cold-start smoke: ON 1024/1024, 11,890 crossings, 9,797 pairs, `routes_sha256
  b15536d2efdd0d23a284adfa070afc11a88fc6e105ccc8b2a0a2ad37c399ef6e`, 216.3 s + 42.6 s
  validator; OFF aborted at L20 (41/52, 11 failed), no routes.
* 20H seam verified read-only: `model20` = 20 planes (18 body: ids 2..18,20;
  interface 1001 z=+0.025 / 1002 z=+0.525), 50 µm pitch, glass unchanged,
  profile `20_height_raised`; `bootstrap.install()` verified to re-point
  `reheight21.model`/`common.INTERFACE_Z`/`l3d.INTERFACE_ROWS`; `RB.BODY_PLANE_IDS` →
  18 ids, stack routing ids `(2..18,20)`.
