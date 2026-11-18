# NON_C4_CROSSING_OPT_1024 — deep audit for the 20-height rebuild

Audit date: 2026-11-17 22:29–22:40 (Asia/Shanghai). Read-only audit; only this file was written.
Audited package: `four_side_1024/fanout1024/nonc4/` (all source files last modified 2026-11-03; byte-identical to the archived snapshot `experiments/non_c4_crossing_opt_1024/code/` — same sizes for every `.py`).
Frozen experiment outputs audited: `outputs/manual_c4_new_connectivity/NON_C4_CROSSING_OPT_1024/` (top-level `report.md`,
`README.md`, `_logs/run.log`, `scratch/*_console.log`, each `E*/`, `S_*/`, `analysis/`).
Frozen upstream: `outputs/manual_c4_new_connectivity/FANOUT_FIRST_21_HEIGHT_REBALANCED_1024/`,
`.../FANOUT_FIRST_Z2_MANUAL_VERIFIED_1024/` (= `common.RUN_DIR`).

> **Concurrent upstream work observed during this audit (not part of the audited nonc4 snapshot).**
> At 22:31–22:38 on 2026-11-17 a new package `four_side_1024/fanout1024/coldstart20/` appeared
> (`model20.py`, `bootstrap.py`, `run_initial.py`) and the following frozen modules were edited at the same time:
> `l3d/layers.py` (22:32), `reheight21/model.py` (22:33), `run21.py` (22:33), `validate21.py` (22:33),
> `assign21.py` (22:38). They now carry a **profile mechanism** for the 20-height model and a parameterised
> validator (`SPEC_*`/`CONTRACT_*` read from the active model). The adaptation table in §9 distinguishes
> “already provided upstream as of 22:38” from “still to change in nonc4”.

---

## 0. Verdict / executive summary

1. The 21H programme is fully reconstructible from the archived artifacts, but **only E0/E1/E2 and a generic
   `run`/`validate` are actually packaged in `experiments.py`**. E3, E5, S_A and S_V3 were driven by
   ad-hoc `python -c` scripts that were **never saved inside the package** (only their console/log output
   remains). `README.md:27-34` and `report.md:145` claim `python -m ...experiments e3`, which does not exist
   in `experiments.py` (its `main()` supports only `e0,e1,e2,run,validate`, `experiments.py:132-205`).
2. E1 is an **incomplete/crashed run** (NameError in `_resolve_planes`, fixed later in `run_nc.py:723`); its
   directory has no `routes_l3d.json`, `crossing_stats.json`, `validation.json`. The “E1 = 6495 crossings”
   figure in `report.md:13,130` therefore has **no artifact backing it** in the campaign tree.
3. The accepted 21H result is **E5_joint_repair_final: 1024/1024 routed, 2606 crossings / 2067 pairs,
   validation_pass=True, 0 violations, min true 3D clearance 0.068714895 mm, R15 kept at 15 mm, 368 manual
   U routes bit-identical to the baseline** (`E5_joint_repair_final/validation.json`,
   `manual_frozen_check.json`, `final_stats.json`; thresholds never relaxed).
4. **20H blockers inside nonc4 (must change):**
   * stale frozen-baseline paths (`paths.py:20`) and output root (`paths.py:18`) — re-pointing is mandatory;
   * plane id **19** still appears in `data.py:24`, `assign_nc.py:78`, `assign_opt.py` allocations and in the
     `assign_nc.build_audit` allowed-set logic (fails hard: confirmed `build_rows` raises
     `ValueError: route 669: plane 19 not in model` under the 20H profile + 21H baseline);
   * non-manual plane budget **13 → 12** (`assign_opt.optimise_allocation` default `plane_count=13`,
     `assign_opt.py:222`; E2 CLI default counts sum to 13, `experiments.py:112`);
   * `validate_nc._EMPTY_PLANE_KINDS` uses validator violation names that changed in the new
     `validate21.py` (`planes_audited_count_not_21` → `planes_audited_count_mismatch`,
     `assignment_used_planes_mismatch`) — `validate_nc.py:32-34`;
   * report/log literals in `run_nc.py:308-316` and the whole of `final_report.py` (harmless for geometry but
     wrong provenance/numbers if not recomputed);
   * the manual-U geometry freeze is sourced from the **21H baseline**; it must be re-pointed to a new 20H
     baseline run (or rebuilt — see §7), otherwise the manual bodies sit at the old z.
5. **Chord lower bound worsens for 20H** (21H campaign predicted 1510 — `_logs/run.log:427`). The 20H
   non-manual plane set is Z1 = 5 planes `(6,7,20,1001,8)` and Z2 = **7** planes `(9,14,15,16,1002,17,18)`.
   Cost curves are height-invariant (same ports ⇒ same chords); I re-measured them read-only:
   Z1V/Z1H edges k=1/2/3 = **1568 / 392 / 134**; each Z2 corner family = **1009 / 246 / 80** (k=1/2/3,
   k=4 = 30 from `_logs/run.log:324-327`). Consequently:
   * family-pure (E3-style) with 12 planes: Z1V 2 + Z1H 3 (526) and Z2 `2,2,2,1` groups
     (3·246 + 1009) ⇒ **predicted 2273** — i.e. the 20H C4-free run is expected to land well above the
     21H accepted 2606, unless a different allocation is proven routable;
   * E2-style compatible sharing over 7 Z2 planes (4,3) ⇒ predicted 526 + 30+30+80+80 = **746**, but the
     21H E2 experiment already showed this allocation is not realisable by the R15 axis router
     (8000 actual crossings vs 646 predicted, `report.md:118`);
   * a currently *forbidden* option is to borrow one Z1-side plane for Z2 (Z1V 2 + Z1H 2 = 4 planes, Z2 8
     planes `2,2,2,2`): predicted 392+392+4·246 = **1768**; it requires relaxing `data.ALLOWED_PLANES`
     (`data.py:35-42`) and a feasibility check of 64 direct bodies on `Z1_INTERFACE` (only 42–52 were ever
     routed there in 21H). This is a decision the 02_annealing stage must make explicitly.
6. Upstream 20H profile availability: `coldstart20.model20`-based generation of the 20H baseline
   (`assign21` → `run21` ABCDE) is now code-complete in principle, but **no 20H baseline run dir exists yet**
   (`experiments/COLD_START_20_HEIGHT_1024/03_fanout_and_xy/run_initial_20h/` is absent). The nonc4 campaign
   cannot start before that baseline (manual geometry + frozen manual fanout) exists; see §7.

---

## 1. The experiment programme (what was actually run, in which order)

Run order from `_logs/run.log` timestamps (2026-11-03): **E0 22:51 → E1 22:53 (crash 22:54) → analysis
run_all 23:04–23:08 → E2 23:03:52–23:05:19 → S_A 23:08:15–23:09:00 → S_V3 23:09:41–23:10:26 →
E3 (first attempt 23:11:13–23:13:16 discarded, final 23:14:11–23:16:49) → E5 23:17:42–23:20:00 →
plots/report/MANIFEST/archive 23:25:07–23:25:42; E4 cross-router in parallel 22:48–23:10; topology
analysis until 23:28:39**. Whole programme ≈ 42 min wall clock, ≈ 20 min of pipeline compute.

| exp | what it does | entry command | output dir (under `outputs/manual_c4_new_connectivity/NON_C4_CROSSING_OPT_1024/`) | result |
|---|---|---|---|---|
| **E0** | Reproduce the frozen 21H baseline inside the new run dir (sanity gate for the C4-free driver + frozen manual geometry). Plan = baseline assignment (`experiments.py:47-59`, `plan_baseline` 30-32) | `python -m four_side_1024.fanout1024.nonc4.experiments e0` (console JSON `{"command":"e0"...}`, `scratch/e0_console.log:163`) | `E0_baseline_reproduction/` (complete: assignment/audit/plan/layer_planes/stack/rules/fanout/routes/crossing_stats/final_stats/validation/consistency + experiment_{B,C,D,E}) | 1024/1024, **11890 crossings / 9797 pairs**, validation PASS — matches frozen baseline (`_logs/run.log:1-162`) |
| **E1** | Remove the C4 orbit binding, naive family-pure contiguous blocks (allocation = `assign_nc.default_allocation()`, `experiments.py:62-76`) | `python -m ...experiments e1 --order port` (traceback shows `main()`→`experiment_e1`, `scratch/e1_console.log`) | `E1_family_pure/` (**incomplete** — only A/B artifacts; no routes/crossing/validation) | crashed 22:54:49 with `NameError: name 'World' is not defined` at old `run_nc.py:765`; 2D=652/656 (4 L8 failures) at crash. Report’s 6495 crossings is **unbacked** |
| **E2** | Crossing-conflict-graph, “compatible opposite-corner families co-plane” allocation; SA partition of each family over 4 shared planes per pair | `python -m ...experiments e2 --seed 11` (console JSON `{"command":"e2"}`), default counts Z1V=2, Z1H=3, NE/SW=4, SE/NW=4 (`experiments.py:112`) | `E2_conflict_assignment/` (complete) | 1024/1024, **8000 crossings / 4315 pairs**, validation PASS — rejected as a *failed experiment*: chord-compatible sharing is unrealisable by the axis router (`report.md:118`, `report.md:131`) |
| **S_A** | Screening variant A of the E3 family-pure SA plan (cheap A+B+C path: `search.screen_plan`, `search.py:60-107`); not saved as a driver | ad-hoc `python -c` (tag `[screen]`, `_logs/run.log:415-509`) | `S_A_familypure_sa/` (A+B only; **no `screening.json`** — process died after printing the screen result) | plan identical to E3 (`assignment_sha256=17e65f22…`), predicted 1510, screened routed=1019 failed=5 crossings=2562/2031; 45 s |
| **S_V3** | Same as S_A, script version V3; only variant that wrote `screening.json` | ad-hoc `python -c` (`_logs/run.log:510-599`) | `S_V3_familypure_sa/` (A+B+`screening.json`) | routed=1019 failed=5 (ids 161,222,408,456,483), crossings=2562/2031, `seconds=39.06`; same assignment SHA as E3 |
| **E3** | Conflict-graph + simulated-annealing partition, **family-pure** 13-plane allocation: Z1V 2 (66/62), Z1H 3 (L20/L1001/L8), Z2 each corner 2 (L9/L14, L15/L16, L17/L18, L19/L1002); full A–E pipeline | ad-hoc `[e3]` driver: `assign_opt.plan_structured(rows, allocation=<family-pure 13>)` + `run_nc.run_standard(budgets=(600,1200), max_iters=2)` + `validate_nc` (not in package) | `E3_family_pure_optimized/` (complete; run twice, final run is the kept one) | **1022/1024, 2586 crossings / 2047 pairs**, validation PASS; 2 L8-blocked failures (222, 483); 158 s |
| **E4** | Crossing-aware per-layer 2D router tool (`cross_router.py`), candidate-level D56 crossing cost + transactional rip-up/re-route; negative result on the new family-pure layers, so not used for the accepted solution | packaged option `python -m ...experiments run --name <n> --router cross` (`experiments.py:79-97,159`); verification via `scratch/cross_router/verify_all.py` | **no experiment dir**; archive `scratch/cross_router/{REPORT.md,verify_final.json,verify_all.log}` | baseline-like planes 9106→8020 crossings (−11.93%, 0 D56 violations); family-pure layers: no stable gain (L6 482→510 etc., `report.md:72`); 2.6–15.5 s/layer vs 0.1–0.4 s production |
| **E5** | E3 plan + **manual cross-height reallocation of the 2 failing routes** (222 L8→L20, 483 L8→Z1_INTERFACE) then full re-run incl. fanout/2D/world/E repair (`_logs/run.log:936-1099`, `scratch/e5_console.log`) | ad-hoc `[e5]` driver = E3 driver with the two plan edits (log lines “move route 222: 8 -> 20”, “move route 483: 8 -> 1001”) | `E5_joint_repair_final/` (**accepted solution**, also copied to the campaign root + `experiments/non_c4_crossing_opt_1024/`) | **1024/1024, 2606 crossings / 2067 pairs**, validation PASS, 0 violations, 1852 transitions, 98 direct, total length 157565.774 mm, min 3D 0.068714895 mm, manual frozen True; 138 s |
| **analysis** | Crossing-source analysis: 11890 crossing database, family-pair matrix, conflict graph (656 movable nodes), L9/L15 anomaly, 28 plots | `python analysis/scripts/run_all.py` (5 steps, `analysis/scripts/run_all.py:45-87`) | `analysis/` | reads the frozen 21H baseline only; hardcoded 11890/9797/21 heights (`analysis/scripts/analysis_common.py:15,34,42-48,65-66`) → must be re-run/re-pointed for 20H |
| **finalize** | Plots (21 per-height + 7 summary), `report.md`, `comparison.md`, `MANIFEST.json`, code snapshot, copy to `experiments/non_c4_crossing_opt_1024`, git commit | ad-hoc calls of `final_report.make_plots/write_reports/write_manifest/archive` (`scratch/finalize_console*.log`); code `final_report.py:75,292,590,608` | campaign root + `experiments/non_c4_crossing_opt_1024/` | MANIFEST 396 files; archive path hardcoded at `final_report.py:610`; also writes/commits into `C:\Users\lihao\Desktop\Graduation Project\work\11.9-second-report-all-work` (`final_report.py:642-661`) |
| **validate** | Independent wrapper around the frozen `validate21` + campaign-specific extra checks | `python -m ...experiments validate --name <exp>` (`experiments.py:165-168,199-203`) | writes `validation.json`, `validator_consistency_tests.json`, `validation/crossing_stats_validate21.json` into the experiment dir (`validate_nc.py:184-220`) | used after every complete experiment; E0/E2/E3/E5 all PASS |

Programme facts that matter for the rebuild:

* **Only E0/E1/E2 are packaged**; the winning path (E3→E5) exists only as console output. The 20H rebuild
  must **re-create the E3/E5/S_A/S_V3 drivers as first-class CLI subcommands** (new `experiments.py` code),
  otherwise the rebuilt campaign is not reproducible.
* Only E5 has its own `run.log`; per-experiment logs for E0–E3 live in `_logs/run.log` and
  `scratch/e*_console.log` (`README.md:6` claims every E dir has one — false).
* `E1` must be re-run from the fixed `run_nc.py` (the `World` import now exists at `run_nc.py:723`).
* All experiments use **A: `assign_nc.prepare_experiment`; B: fanout with frozen manual transitions;
  C: per-plane strict-D56 2D bodies; D: 3D assembly + strict 0.05 mm world check; E: repair loop**;
  the only differences are the assignment plan (and, for E4, the 2D router implementation).

---

## 2. `assign_opt.py` — simulated-annealing layer assignment (full detail)

Files/anchors: `assign_opt.py:1-29` (model rationale), `:46-55` (family compatibility),
`:60-93` (chord graph), `:100-107` (intra energy), `:110-178` (SA), `:190-211` (cost curves),
`:222-252` (`optimise_allocation`), `:256-297` (`plan_structured`), `:300-337` (allocations).

### 2.1 Why it exists
Empirical fact from E0/E1: the number of real same-layer crossing events of a height is, to first order,
the number of **port-chord crossing pairs** assigned to that height, because the R15 body router draws a
near-straight connection between its fanout landings. Therefore layer assignment is reduced to:
partition every direction family into as many height groups as it has planes, minimizing intra-group
chord crossings.

### 2.2 Energy / graph (`assign_opt.py:60-107`)
* Chord of a route = segment `(source_x_mm, source_y_mm) → (target_x_mm, target_y_mm)` (`chord_of`, 60-62).
* `chords_cross` = proper segment intersection (`_orient`, 65-79; strict `o1!=o2 and o3!=o4`, no
  collinear/degenerate case). This is exactly the port-order inversion test.
* `crossing_graph(rows)` (82-93): O(n²) adjacency sets; edges = crossing chord pairs.
* **Energy** `intra_edges(adjacency, assignment)` (100-106): number of graph edges whose two endpoints are in
  the same group = number of chord-crossing pairs that will share a physical height. Only this is minimized;
  there is no length/transition/congestion term, and no group-size penalty.

### 2.3 Simulated annealing (`partition_min_intra`, 110-178)
* Inputs: adjacency, `groups=k`, defaults `seed=0, restarts=10, iters=40000, time_budget=60.0`.
* Multiple restarts; per restart the group assignment is initialized `index % k` then `rng.shuffle`
  (125-127; `random.Random(int(seed))`, so deterministic per seed unless a wall-clock cutoff triggers).
* **Descent phase** (128-150): random route order; for each route compute `Counter` of neighbour groups;
  move it to the group with the most negative exact delta (`delta = neighbours_in_group - neighbours_in_old`,
  best if < 0); repeat until no single-route improving move exists.
* **Annealing phase** (151-167):
  * one move type only: pick a random route, pick a **uniformly random different group** (disallow current);
  * exact delta from the adjacency counter; accept if `delta <= 0` else with `exp(-delta/T)`;
  * `T₀ = 1.2`, geometric cooling `T *= 0.99985` **per iteration** (≈ 0.003 after 40000 iterations);
  * fixed `iters = 40000` per restart; wall-clock `time_budget` (60 s default here, 120 s in
    `measure_cost_curves`) aborts the inner loop and the restart loop; also stops early when `intra == 0`.
* Keep the best restart; log `[partition] k=… intra=… sizes=…`; `sizes` are the actual group sizes.
* **Determinism caveat:** results claim to be deterministic for a fixed seed, but the time budget makes the
  number of executed restarts/iterations machine dependent (a faster/slower machine can differ). For the
  rebuild, keep the seed and treat timeouts as a reproducibility hazard (or fix iteration counts exactly).
* No swap/2-opt move, no capacity constraint, no balancing: `plan_structured`’s comment about
  “deterministic size balancing” (`assign_opt.py:276-279`) is **not implemented** — groups are assigned to
  planes in index order as produced by the SA.

### 2.4 Family partition programme (`measure_cost_curves` / `optimise_allocation`)
* `measure_cost_curves(rows, group_counts=(1..6), seed=11, time_budget=120)` (190-211): per family, build the
  chord graph once and run `partition_min_intra` for k = 1..6 → curve `k → min intra edges`.
  **Never used by any archived run** (grep: no caller; no artifact contains its output).
* `optimise_allocation(curves, plane_count=13, min_planes=1, max_planes=6)` (222-252): brute-force over
  `n_v, n_h, n_sw_pair, n_nw_pair ∈ [1,6]` with `n_v+n_h+n_sw+n_nw == plane_count`; cost =
  `cost(Z1V,n_v) + cost(Z1H,n_h) + cost(NE,k_sw) + cost(SW,k_sw) + cost(SE,k_nw) + cost(NW,k_nw)`.
  This model assumes **opposite-corner families share their plane list** (so `k` physical planes give `k`
  groups to *each* of the two compatible families). Returns `{cost, z1v, z1h, ne_sw, se_nw}` — **not** the
  `{family: [plane_ids]}` allocation; **no glue code converts the result into an allocation**
  (a gap for the rebuild: add `allocation_from_counts` call or a converter).
  **Never called in the archived campaign** — the executed plans were explicit allocations.
* **Executed allocations instead:**
  * E1: `assign_nc.default_allocation()` = family-pure 2+3+2+2+2+2 (13 non-manual planes).
  * E2: `allocation_from_counts({Z1V:2, Z1H:3, Z2_NE:4, Z2_SE:4})` ⇒ Z2 pairs share
    `[9,14,15,16]` and `[1002,17,18,19]`.
  * E3/E5/S_A/S_V3: family-pure explicit 13-plane map = E1 map but SA-partitioned
    (`plan_structured` with `allocation=assign_nc.default_allocation()`); predicted 1510 =
    392+134+4·246 (`_logs/run.log:427,516`).
* Family rules (`assign_opt.py:46-55`): `INCOMPATIBLE={('Z1V','Z1H')}` — 100 % of their chords cross;
  `COMPATIBLE={(NE,SW),(SW,NE),(SE,NW),(NW,SE)}` — 0 chord crossings; every other pair ~60–73 % must be
  kept apart. These rules are pure chord geometry (height-count independent).
* Plan reconstruction (`plan_structured`, 256-297): for each family partition into `len(plane_ids)` groups,
  assign group i to `plane_ids[i]`; `plan_with_manual` re-adds the 368 manual routes on their frozen
  baseline planes (`assign_nc.py:140-151`); summary stores per-family planes/sizes/predicted intra and
  `predicted_crossings = Σ intra`. (Full `plan_structured` is exercised; `optimise_allocation` &
  `measure_cost_curves` are not.)

### 2.5 What is 21-height-specific vs height-count-generic

| part | status | 20H action |
|---|---|---|
| chord graph / energy / SA / plan_structured / save/load | generic | none |
| INCOMPATIBLE / COMPATIBLE | generic (chord facts) | none |
| measured cost curves | **generic** (ports unchanged ⇒ curves reusable) | re-measure once for the new allocation study (I verified the values match: Z1V/Z1H 1568/392/134; Z2 1009/246/80/30) |
| `optimise_allocation(plane_count=13)` | **21H-specific** (`assign_opt.py:222`) | `plane_count=12` (20−8 manual) |
| `default_allocation()` docstrings/slices (“Z1: 5 heights → 2+3; Z2: 8 heights → 4+4”, 304-317) | 21H-specific semantics (uses `D.Z1/Z2_OTHER_PLANES`) | after dropping L19 the slices become 2 + 3 for Z1 and 4+3 for the shared Z2 pairs; for the *family-pure* winning programme an explicit allocation must be written (see below) |
| cost-model assumption “opposite corners share planes” | 21H E2 negative result: not realisable | for 20H, either run E2-style screening (predicted 746) or the family-pure variant; do not assume the sharing model |
| `allocation_from_counts` | generic if plane lists updated | new E2 default counts must sum to 12 |

**Minimum for 18 body + 2 interface planes:** (a) `data.Z2_OTHER_PLANES` → `(9,14,15,16,1002,17,18)`;
(b) new family-pure allocation: Z1V `[6,7]`, Z1H `[20,8,1001]` (or `[20,1001]` if the borrow option is
allowed), Z2 7 planes among 4 families e.g. NE `[9,14]`, SE `[15,16]`, NW `[17]`, SW `[18,1002]`
(predicted 2273); (c) `optimise_allocation(plane_count=12)` + converter if the automatic programme is used;
(d) E2 CLI counts e.g. `{Z1V:2, Z1H:3, Z2_NE:4, Z2_SE:3}` (sum 12). The 02_annealing stage must **screen**
these candidates with `search.screen_plan` (~40 s each) before committing.

---

## 3. `assign_nc.py` — C4-free per-route assignment

### 3.1 What it does
Per-route 2D→2D layer assignment: every non-manual `route_id` may be assigned to any plane of its own
family’s allowed set, independent of the other three routes of its original C4 orbit. The whole-C4-orbit
layer binding is removed; `c4_group_id` survives only as provenance (`assign_nc.py:1-18`).
Pieces:
* `default_allocation()` (63-79): family-pure 21H map `Z1V[6,7]`, `Z1H[20,8,1001]`, `Z2_NE[9,14]`,
  `Z2_SE[15,16]`, `Z2_NW[17,18]`, `Z2_SW[19,1002]`.
* `plan_family_allocation(rows, allocation, order)` (113-137) + `distribute_balanced` (82-98) +
  `order_family` (101-110): order = `port` (sort by source-side coordinate, `data.port_sort_key`),
  `route_id`, or `round_robin`; contiguous balanced chunks per plane or round-robin interleave.
* `plan_with_manual(rows, nonmanual_plan)` (140-151): **the 368 manual routes get their baseline
  `target_layer`** — this is the hard freeze point of the manual U groups.
* `build_rows(base_rows, plan)` (176-198): copies the baseline row, keeps all port/identity columns,
  writes `target_layer`, `target_plane_label`, `target_z_mm = M.plane_z(plane)`, and derives
  `needs_transition = |z − base.interface_z_mm| > 1e-9` and `direction = direct/down/up`.
  Note `base["interface_z_mm"]` is the per-row frozen interface height — in 20H it must be 0.025/0.525.
* `build_audit` (226-416): hard invariants — 1024 rows, unique ids, 512 Z1 / 512 Z2; every port/identity
  column identical to the baseline; 368 manual routes keep group + baseline plane; manual group counts
  64/64/64/64 + 16/16/40/40 (`_MANUAL_EXPECTED`, 55-59); non-manual planes inside the family allowed set
  (289-303); target z/direction consistency with `M.plane_z`; min pitch ≥ `M.MIN_LAYER_PITCH_MM`;
  direct routes only on interface planes (336-346); C4-orbit split evidence (347-364); geometry rules report
  (`routing_heights=len(M.PLANE_IDS)`, 400-411).
* `write_model_payloads` (420-440) writes `layer_planes.json` / `physical_layer_stack.json` /
  `process_rules.json` from `M.*_payload()`; `prepare_experiment` (443-466) writes assignment + audit,
  raises if the audit fails, and **calls `paths.use_experiment(exp_dir)`** (re-binds `model` writable paths).

### 3.2 Route families
Direction families from `data.py:26-49`: `Z1V` (N↔S), `Z1H` (E↔W), `Z2_NE` (E→N/N→E), `Z2_SE`, `Z2_NW`,
`Z2_SW`; manual routes are `MANUAL:Z1-U1..Z2-U4` (8 groups, 368 routes, 8 frozen planes 2,3,4,5,10,11,12,13,
`data.py:19-20,276-283`). Family of a row is derived from `plane` + `source_side`/`target_side`
(`data.family_of`, 114-135); Z1 other planes = `(6,7,20,1001,8)`, Z2 other planes =
`(9,14,15,16,1002,17,18,19)` (`data.py:23-24`, z-ordered).

### 3.3 Manual U freeze (end-to-end)
1. `plan_with_manual` keeps the baseline plane (assign_nc.py:140-151);
2. `build_audit` rejects any manual route whose plane differs from the baseline / `_MANUAL_EXPECTED`
   (258-288), any group-count change, and any total ≠ 368;
3. `validate_nc._extra_checks` compares the manual route `parts` JSON bit-identically with the baseline
   `routes_l3d.json` (validate_nc.py:108-126) and sets `manual_routes_frozen_to_baseline`;
4. `run_nc` (see §4) never re-routes manual bodies: fanout transitions come from the baseline
   `fanout_selected.json`, 2D bodies from the baseline `routes_l3d.json`, and both are re-inserted as fixed
   world citizens / frozen D56 blockers in stage B/C/repair; `manual_frozen_check` re-verifies bit identity
   (run_nc.py:928-952).
Manual group **plane ids do not change** in 20H (2,3,4,5,10,11,12,13), only their physical z (−0.325,
−0.275, −0.225, −0.175, +0.175, +0.225, +0.275, +0.325); therefore `_MANUAL_EXPECTED` needs no id change,
but the *freeze source* must be a new 20H baseline (old geometry would be at wrong z).

### 3.4 C4 orbit integrity tracking
* `c4_group_id` is copied unchanged from the baseline (`PORT_COLUMNS`);
* `build_audit` computes, per `common.rotation_groups()` orbit, the set of assigned planes and whether the
  orbit contains manual routes; it reports `nonmanual_orbits`, `…split_across_planes`,
  `…single_plane`, `max_planes_per_orbits` and deliberately permits splitting (`c4_policy`, 347-402);
* `validate_nc._orbit_split_evidence` recomputes the same evidence (validate_nc.py:39-76);
* `_check_assignment_nc` (validate_nc.py:79-93) **drops only the `c4_orbit_not_single_plane` violation**
  from the frozen validator (`_C4_ALLOWED_KINDS`, validate_nc.py:30); manual groups were already split by
  their verified design and are frozen.
Observed 21H: 656 non-manual routes = 164 orbits, **all 164 split**, max 4 planes/orbit
(`E5/assignment_audit.json: c4_policy`). Height-count independent.

### 3.5 Per-plane capacity rules (there is no numeric capacity limit)
Hard rules only:
* family allowed-plane set (Z1 families → Z1_OTHER_PLANES; Z2 families → Z2_OTHER_PLANES) — `build_audit:289-303`;
* direct routes (target height = own interface height) **only on interface planes 1001/1002** (`build_audit:336-346`);
* each manual group on its fixed plane with fixed count; exactly 368 manual rows;
* exactly one target plane per route; distinct heights and ≥ 0.05 mm pitch (`build_audit:326-335`);
* 1024 rows, 512/512 split, unique ids.
For the campaign the frozen validator’s per-plane count / direct-count expectations are **overwritten with
the plan’s actual counts** (`validate_nc.patch_validator`, validate_nc.py:96-105,
`validate_experiment:190-195`), so no numeric capacity is enforced; layer congestion is handled implicitly by
the 2D router (failures) — e.g. L8 failed at ≥39–43 bodies (`E3/experiment_C/summary.json`) while other
planes routed 66. The 20H baseline contract counts are model20’s `CONTRACT_PLANE_COUNTS`
(2..5:+64, 6/7/20/1001:52, 8:48, 9/14/15/16:56, 10/11:16, 12/13:40, 17/18:64, 1002:48;
`coldstart20/model20.py:303-308`), but those apply to the **baseline** run, not to the C4-free campaign.

### 3.6 20H changes for `assign_nc`
1. `data.Z2_OTHER_PLANES` loses 19 (`data.py:24`) — otherwise any route assigned to 19 makes `build_rows`
   raise (confirmed: `ValueError: route 669: plane 19 not in model` at `assign_nc.py:184-185` under the 20H
   profile with the 21H baseline);
2. `assign_nc.default_allocation` (63-79) must be rewritten for the 7 Z2 planes (current `Z2_SW:[19,1002]`
   is invalid) and for whichever family-pure sharing the 02_annealing stage selects;
3. `_MANUAL_EXPECTED` (55-59) unchanged (same ids/counts);
4. all other invariants/pitch/direct logic is `M.PLANE_IDS`/`M.plane_z`-driven and works once the 20H model
   is installed and the 20H baseline assignment (interface_z 0.025/0.525) is used;
5. the `geometry_rules` report block (400-411) already uses `len(M.PLANE_IDS)` → 20 automatically.

---

## 4. `run_nc.py` — pipeline stages A–E and the joint-repair loop

### 4.1 Stage map (nonc4 packaging)
| stage | function (line) | what it does | writes |
|---|---|---|---|
| **A** | `run_standard` 962-987 → `assign_nc.prepare_experiment` 973-975 | plan/assignment + audit + layer model payloads (`assign_nc` §3); emits `[A] experiment=… per_plane=…` | `assignment_1024.csv`, `assignment_audit.json`, `layer_planes.json`, `physical_layer_stack.json`, `process_rules.json`, optional `assignment_plan.json` |
| **B** | `stage_b` 104-137 | `FANOUT.plan_fanout(rows, stack=M.layer_stack(), fixed=load_baseline_manual_fanout())` (107-110): manual transitions inserted as **fixed** world citizens; then `run21.validate_fanout_selected` (121), `run21._fanout_artifacts` (122) | `fanout_selected.json`, `fanout_validation.json`, `layerwise_endpoints/endpoints.json`, `experiment_B/`, `checkpoints/stage_B_fanout.json` |
| **C** | `route_layers` 179-206 | per-height 2D bodies. `build_layer_tasks` (141-162) creates tasks **only for non-manual rows** (manual skipped at 150-151); `initial_routes_for` (165-176) = interface lead blockers + **frozen manual bodies**; `LAYER2D.route_all_layers(budget, ordering_seed, initial_routes)`; normalize/reconcile via `run21` helpers. Optional `CrossAwareRouterShim` (991-1018) = E4 tool | in-memory `routed`; nothing until finalize (`experiment_C`) |
| **D** | `assemble_all` 210-260 + `run21._world_check` (call at 265, 499) | assembles all 1024 routes: manual rows **copied from baseline** `routes_l3d.json` (219-225); non-manual assembled by `ASM.assemble_route(row, source_trans, target_trans, body)`; then `ASM.validate_routes_independent(routes, stack=M.layer_stack())` = strict 0.05 mm true-3D world check (valid/violations) | `experiment_D/` at finalize |
| **E** | `run_pipeline` 477-577 + helpers | iteration loop (budgets, lead repair, best checkpoint) then `repair_failed` (580-638): (1) single-route insertion `_insert_one_route` (641-718) into the frozen accepted world; (2) whole-plane rip-up & re-solve `_resolve_planes` (721-800); refresh fanout artifacts; write routes; `finalize_experiment` (857-925) | `routes_l3d.json`, `failed_routes.json`, `crossing_stats.json`, `final_stats.json`, `layerwise_routes/routes.json`, `manual_frozen_check.json`, `optimization_history.csv`, `experiment_E/`, `validation/*` (validator called by `experiments.py`) |

Iteration budget: `run_standard(budgets=(600,1200), max_iters=2)` (defaults at
`run_nc.py:962-965`; CLI `--budgets 600,1200 --max-iters 2`, `experiments.py:161-163`;
`run_plan` defaults at `experiments.py:79-81`). Per iteration C uses budget `budgets[(i-1) % len]`,
`ordering_seed = i-1`, and iteration > 1 first re-plans the fanout leads of the previous failures via
`run21._replan_leads` (`run_nc.py:490`; 21H original `stage_e` at `reheight21/run21.py:1061`, budgets
`(600,1200,1800,2400)` in `run21.py:33`).
Repair budgets: local insert `LAYER2D.route_layer(..., budget=2400, rr_rounds=0)` (701-702); plane
re-solve `budget=2400, rr_rounds=2`, seeds `range(4)` (747-752); `repair_failed` may launch up to 14 lead
pairs per route (`run21._LEAD_PAIRS`, `run21.py:40-44`) for non-direct failures.
Accepted-solution score = `len(world_valid)` with tie-break on fewer world violations (523-530); checkpoints
`best_solution.json` (825-843).

### 4.2 What “failed routes” means, and how re-allocation is attempted
* A route is failed if it is **not in `best['valid']`**: either the 2D router produced no body
  (`layer2d_failed:*`), the 3D assembly rejected it (`assembly:*`), or the strict world check reported a
  violation for it (432-451, 500-537). Failed routes are carried as real `route_id`s with reasons into
  `failed_routes.json` (285-324, 541-577).
* `repair_failed` attempts, **on the same assigned plane**, (1) single-route insertion with the rest of the
  layout frozen as D56 blockers, (2) whole-plane rip-up and re-solve at the same height.
* **There is no automatic cross-height re-assignment in `run_nc.py`.** The only re-allocation that ever
  happened is E5’s manual plan edit before stage A: route 222 `L8→L20`, route 483 `L8→Z1_INTERFACE`
  (`_logs/run.log:936-937`; verified by diffing the assignments: exactly these two target layers differ
  between E3 and E5). The 20H rebuild therefore needs an explicit **E5-style reallocation driver**
  (move unresolved routes to another plane of the same family, re-run A–E) as part of stage 04.
* Iteration 2 lead repair only changes the S-transition leads of the failures, not the height
  (`run21._replan_leads`, run_nc.py:489-491).

### 4.3 Parts that consume the FROZEN 21H manual geometry (must be re-pointed)
All of these read `P.BASELINE_21H_DIR` (directly or through `data.py`):
`load_baseline_manual_routes` (run_nc.py:63-75 → `D.load_baseline_assignment`, `D.baseline_routes`),
`load_baseline_manual_fanout` (78-88 → `D.baseline_fanout_selected`), `frozen_manual_bodies` (91-100),
`stage_b`’s `fixed=` (107-110), `initial_routes_for` (165-176), `assemble_all` manual copy (210-225),
`repair_failed` (587-596 manual branch 603-609), `_resolve_planes` (725 manual import),
`finalize_experiment`→`manual_frozen_check` (857-952), plus `write_routes_payload` provenance strings
(308-316), and on the validation side `validate_nc._extra_checks` → `D.baseline_routes()` (validate_nc.py:112).
Re-point `paths.BASELINE_21H_DIR` to the new 20H baseline run dir and these all follow (they are the same
frozen-baseline contract, just a different height profile). Nothing else in run_nc is 21H-specific except
report strings (145/170/380/428/806 are `M.PLANE_IDS` loops → generic).

---

## 5. Supporting modules: what they read/write and how to re-point them

| module | reads | writes | frozen dirs / constants | 20H re-point |
|---|---|---|---|---|
| `data.py` | baseline assignment CSV, `routes_l3d.json`, `fanout_selected.json`, `crossing_stats.json` (`data.py:77-80,239-253`); experiment assignment (83-90); model plane tables via `M` (260-273); endpoints via `common` | via `C.write_json` (65-66, used by other modules) | `P.BASELINE_21H_DIR` only | change `paths.py:20` to the 20H baseline dir; update `Z2_OTHER_PLANES` (24) |
| `paths.py` | `common.OUTPUT_ROOT`, `reheight21.model` | creates experiment subdirs; **rebinds** `model` writable constants (`use_experiment`, 37-58: `RUN_DIR`, `NEW_RUN_DIR`, `NEW_ASSIGNMENT`, `…AUDIT`, `…DIFF_JSON/MD`, `LAYER_PLANES_JSON`, `NEW_STACK_JSON`, `NEW_RULES_JSON`, `NEW_EXPERIMENT_A`), resolved **at call time** by run21/run_nc | `EXPERIMENT_ROOT = OUTPUT_ROOT/'NON_C4_CROSSING_OPT_1024'` (18), `BASELINE_21H_DIR = OUTPUT_ROOT/'FANOUT_FIRST_21_HEIGHT_REBALANCED_1024'` (20), `BASELINE_18L_DIR = C.RUN_DIR` (22, **unused everywhere**) | new `EXPERIMENT_ROOT` under `experiments/COLD_START_20_HEIGHT_1024/` (e.g. `M.EXPERIMENT_ROOT/'02_annealing'`), new `BASELINE_20H_DIR = M.EXPERIMENT_ROOT/'03_fanout_and_xy'/'run_initial_20h'`; keep `BASELINE_21H_DIR` only as a read-only comparison constant. Because `use_experiment` rebinds the *module object*, it keeps working unchanged **iff** `coldstart20.bootstrap` replaced `reheight21.model` before any nonc4 module is imported (see §7 wiring) |
| `crossings.py` | `routes_l3d.json` records (passed in), `layer_planes.json` of the experiment or else `M.PLANE_IDS/plane_z/label/kind` (166-185); `C.CLEARANCE_2D_MM` (`D56_CLEARANCE_MM`, 29) | returns report dict / writes by caller (`_write_json` in run_nc finalize) | `D56=0.08`, sagitta 0.0005; `CROSSING_SCHEMA` | no change needed beyond the active model; docstring “must reproduce 11890/9797” (12) is a report constant |
| `search.py` | `D.load_baseline_assignment`; `assign_nc.prepare_experiment`; `run_nc.stage_b/route_layers/assemble_all`; `D.layer_planes(exp_dir)` (60-107) | `screening.json` in the experiment dir, plus the usual A/B payloads | `P.EXPERIMENT_ROOT` for the default root (68) | no change except upstream |
| `validate_nc.py` | experiment dir (`assignment_1024.csv`, `routes_l3d.json`, `layer_planes.json` via `V.validate`), baseline `routes_l3d.json` for the manual freeze (108-126, 112) | `validation.json`, `validator_consistency_tests.json`, `validation/crossing_stats_validate21.json` (196-214) | patches `V.SPEC_EXPECTED_ASSIGNED`, `V.SPEC_DIRECT_BY_PLANE`, `V.SPEC_DIRECT_TOTAL`, `V.check_assignment` (96-105); filters `c4_orbit_not_single_plane` (30) and two “empty plane” kinds (32-34) | update `_EMPTY_PLANE_KINDS` to the new validator kind names (`planes_audited_count_mismatch`, `assignment_used_planes_mismatch`, keep `model_planes_without_flat_geometry`); no path change; relies on the active model’s `SPEC_*` (20H profile via bootstrap) |
| downstream handoff | `E5_DIR` (not in nonc4) | — | `native3d/common.py:19` and `xyzrouter/paths.py:19` point to `NON_C4_CROSSING_OPT_1024/E5_joint_repair_final`; `validate_native3d.DEFAULT_BASELINE` (native3d/validate_native3d.py:128) likewise | after the 20H accepted solution exists, re-point `E5_DIR`/`DEFAULT_BASELINE` to the new accepted dir (05_native3d stage) |

`paths.use_experiment` notes: it re-binds only the writable paths above, at call time. It does **not**
re-bind `validate21.RUN_DIR_21H` (`validate21.py:77`, captured at import) — safe only because
`validate_nc.validate_experiment` passes an explicit `run_dir`/`out_dir` (`validate_nc.py:199-205`).
`BASELINE_18L_DIR` is dead code (grep: definition only).
**Wiring requirement for 20H:** `from four_side_1024.fanout1024.coldstart20 import bootstrap` must be the
first pipeline import, because every nonc4 module does `from ..reheight21 import model as M` at import time
and `use_experiment` mutates that *same module object*; if nonc4 is imported first, its `M` is the 21H module
and the run silently uses 21 planes while `assert_20_height_profile` still passes.

---

## 6. Every hardcoded 21-specific / historical literal (file:line, classification)

Classification: **L** = logic constant (must change / must be re-pointed for 20H); **R** = report/log/provenance
constant (harmless for geometry, wrong text/number if not recomputed, should be updated for honesty);
**D** = dead/unused code or docstring (no runtime effect).
Core geometry thresholds are intentionally unchanged and are **not** listed as defects: glass z
[-0.35, +0.65], 0.05 mm pitch/3D clearance, R15 = 15 mm, strict D56 = 0.08 mm — these must stay.

### `nonc4/`
| file:line | literal | class |
|---|---|---|
| `paths.py:18` | `EXPERIMENT_ROOT = …/'NON_C4_CROSSING_OPT_1024'` | **L** (new output root; otherwise the 21H artifacts are overwritten) |
| `paths.py:20` | `BASELINE_21H_DIR = …/'FANOUT_FIRST_21_HEIGHT_REBALANCED_1024'` | **L** (must point to the 20H baseline; currently the source of manual geometry/fanout and of the assignment, incl. invalid plane 19) |
| `paths.py:22` | `BASELINE_18L_DIR = C.RUN_DIR` | D (never referenced) |
| `paths.py:4-8,19-21` | “frozen 21-height baseline” comments | D |
| `data.py:5,22` | comments “frozen 21-height baseline / 21-height partition” | D/R |
| `data.py:19-20` | `MANUAL_PLANES = M.MANUAL_PLANE_IDS` | L (works through the active model) |
| `data.py:23` | `Z1_OTHER_PLANES = (6,7,20,1001,8)` | **L** but unchanged for 20H (all five survive) |
| `data.py:24` | `Z2_OTHER_PLANES = (9,14,15,16,1002,17,18,19)` | **L** (must drop 19) |
| `data.py:77-80,94,240,248,253` | paths built from `P.BASELINE_21H_DIR` | **L** (follow the re-point) |
| `assign_nc.py:14-17,67-70` | docstrings “21 routing heights / Z1_INTERFACE / Z2_INTERFACE plane” | D/R |
| `assign_nc.py:55-59` | `_MANUAL_EXPECTED` planes 2–5,10–13 + counts 64/64/64/64/16/16/40/40 | L but **valid for 20H** (same ids/counts; keep) |
| `assign_nc.py:63-79` | `default_allocation` floor plan incl. `Z2_SW:[19,1002]` | **L** (19 invalid; rewrite for 7 Z2 planes) |
| `assign_nc.py:230-231,236` | 1024 rows / z1:z2 = 512:512 | L but unchanged (frozen connectivity) |
| `assign_nc.py:278-280` | manual total 368 | L but unchanged |
| `assign_nc.py:390` | “REMOVED for the 368+656 non-manual routes” | R |
| `assign_nc.py:404-411` | `glass_mm=[150,150,1.0]`, `routing_heights=len(M.PLANE_IDS)` | R (length is generic) |
| `assign_opt.py:222` | `optimise_allocation(..., plane_count=13, ...)` | **L** (12 = 20−8 manual) |
| `assign_opt.py:235-241` | `min/max_planes` 1/6 bounds | L (keep; Z2 pair counts 3/4 still inside) |
| `assign_opt.py:300-317` | `all_planes`, `default_allocation`, doc “Z1: 5 physical heights → 2/3; Z2: 8 physical heights → 4/4” | **L** (slices become 2/3 and 4/3 once `D.Z2_OTHER_PLANES` is fixed; doc must change; family-pure plan must be explicit) |
| `assign_opt.py:110,190` | `seed=0/11`, `restarts=10`, `iters=40000`, `time_budget=60/120` | L but unchanged; wall-clock budget is a reproducibility hazard |
| `experiments.py:47-59` | E0 = “reproduce the frozen 21-height baseline” | **L** (E0 must reproduce the **20H** baseline; plan comes from `P.BASELINE_*`) |
| `experiments.py:100-127,151-152` | E2 default `allocation_counts = dict(Z1V=2, Z1H=3, Z2_NE=4, Z2_SE=4)` (sum **13**) | **L** (must sum to 12, e.g. SE=3) |
| `experiments.py:62-76` | E1 default allocation (via `assign_nc.default_allocation`) | L (follows assign_nc) |
| `experiments.py:132-205` | CLI has no `e3`/`e5`/screening subcommands | **L** (programme reproducibility gap; add them) |
| `run_nc.py:4-14` | doc “21-height”, “exact verified 21-height geometry” | D/R |
| `run_nc.py:63-100` | manual-geometry loaders from the frozen baseline | **L** (re-point via `P.BASELINE_21H_DIR`) |
| `run_nc.py:104-137` | `fixed=load_baseline_manual_fanout()` — frozen manual transitions | **L** (source re-point) |
| `run_nc.py:146-151,165-176` | manual rows skipped in 2D, manual bodies frozen blockers | L (design constant of the freeze; only changes if manual geometry is rebuilt) |
| `run_nc.py:219-225` | manual routes copied from baseline records | L (same) |
| `run_nc.py:308` | `parent_experiment='FANOUT_FIRST_21_HEIGHT_REBALANCED_1024'` | R (provenance — must name the 20H baseline) |
| `run_nc.py:310` | `manual_geometry='frozen from FANOUT_FIRST_21_HEIGHT_REBALANCED_1024'` | R |
| `run_nc.py:312` | `layer_model='21 routing heights = 19 body planes + 2 routable interface planes'` | R (should be derived: `len(M.PLANE_IDS)`, `len(M.BODY_PLANES)`) |
| `run_nc.py:350,397,445,458,536` | 1024 / 656 / direct counts in payloads/logs | R (1024 is the frozen connectivity; fine) |
| `run_nc.py:380,428,806` | loops over `M.PLANE_IDS` | generic |
| `crossings.py:12` | “must reproduce the frozen baseline exactly (11890 crossing events / 9797 crossing pairs)” | R |
| `crossings.py:171` | “derive the 21-height model” | D/R |
| `crossings.py:29-30` | `D56_CLEARANCE_MM=0.08`, `SAGITTA_MM=0.0005` | L but unchanged (no rule relaxation) |
| `validate_nc.py:30` | `_C4_ALLOWED_KINDS=('c4_orbit_not_single_plane',)` | L (kind still exists in the new validator, `validate21.py:2020`; keep) |
| `validate_nc.py:32-34` | `_EMPTY_PLANE_KINDS=('model_planes_without_flat_geometry','planes_audited_count_not_21')` | **L** (second name no longer exists; new names are `planes_audited_count_mismatch` (`validate21.py:2713`) and `assignment_used_planes_mismatch` (`validate21.py:2026`); first still exists at `validate21.py:2717`) |
| `validate_nc.py:179` | “a legal C4-free assignment may leave some of the 21 routing heights unpopulated” | R |
| `validate_nc.py:133` | `manual_routes_expected=368` | L but unchanged |
| `search.py:1-13` | “costs ~2 minutes” | R |
| `final_report.py:248` | plot title “1024 waveguides on 21 heights” | R |
| `final_report.py:337-340` | baseline “11890 / 9797” and all deltas computed against 11890 | R (must be recomputed from the 20H baseline `crossing_stats.json`) |
| `final_report.py:350-356` | “368 条…21 高度基线”, hardcoded experiment chain “E0 11890 → E1 6495 (1020/1024) → E2 … → E3 … → E5 …” | R (E1/E3 numbers are historical/hardcoded; E2/E3 crossing values are read from their dirs) |
| `final_report.py:366,377,393-396` | “21 层汇总”, “## 2. 21 个物理高度与层分配” | R |
| `final_report.py:408,414` | “11890 条交叉”, “1848 条接口 lead” | R |
| `final_report.py:424-431` | “21 高度下的最优结构”, hardcoded per-layer cross-router numbers L6 990→922 … L19 1440→1378, “全部 21 层 9106→8020” | R |
| `final_report.py:436-444` | comparison table header “与 21 高度成功基线的对比” + 11890/9797 | R |
| `final_report.py:480-500` | lower-bound narrative “392+134+…=526”, “4×246=984”, “=1510”, “21 高度” | R (narrative must be re-derived for the 12-plane 20H bound) |
| `final_report.py:506-515` | experiment table rows E0 11890, E1 6495 (1020/1024), E2 8000, E3 1022/1024, E5 2606 | R |
| `final_report.py:526-527` | “搜索入口：`python -m …experiments e3`” | **R (and factually wrong — no e3 subcommand)** |
| `final_report.py:541-555` | comparison.md baseline 11890/9797 + E0 “21 高度基线复现” | R |
| `final_report.py:574-578` | “368 条人工 U 线路完整几何冻结…21 高度” + 11890 | R |
| `final_report.py:610,633-634,642-661` | archive target `experiments/non_c4_crossing_opt_1024`, hardcoded `reheight21/SPEC.md`, git repo `C:\…\work\11.9-second-report-all-work` | **L/R** (new campaign needs a new archive root + no accidental git commit to the old repo) |
| `__init__.py:5-17` | doc “368 manual routes frozen on 8 planes”, “FANOUT_FIRST_21_HEIGHT_REBALANCED_1024” | D/R |
| `cross_router.py` | no plane id / height literal; takes `z_mm` per task (`cross_router.py:733-760`), only a fallback `common.layer_z` when `z_mm is None` (792-793); plane-agnostic | generic (E4 tool reusable as-is) |
| analysis scripts (archived copy only) | `analysis/scripts/analysis_common.py:34` baseline dir, `:42-48` REFERENCE_TOTALS 11890/9797/21/13, `:65-66` allowed plane lists incl. 19 | L if the 20H analysis is re-run (re-point + recompute); not part of the runtime package |

### `reheight21/` dependency (now partly generalised upstream)
| file:line (current checkpoint) | literal | class / status |
|---|---|---|
| `reheight21/model.py:103-104` | `Z1_INTERFACE_MM=0.0`, `Z2_INTERFACE_MM=0.5` | default-profile constants; **20H values live in `coldstart20/model20.py:135-136`** (0.025/0.525) |
| `reheight21/model.py:108-114,131-132` | 19 body planes, 21 plane ids incl. 19 | default 21H profile; 20H table in `coldstart20/model20.py:139-145,162-163` |
| `reheight21/model.py:203-220` | `MANUAL_GROUP_SPECS` z = −0.35…+0.30 | default 21H; 20H +0.025 in `model20.py:231-248` |
| `reheight21/model.py:239,243-246` | Z1 5-plane / Z2 8-plane plans incl. 19 | default 21H; 20H plan in `model20.py:267,277-278` (Z2 7 planes) |
| `reheight21/model.py:256-269,318-319` | 21H experiment name/schema/`SPEC_PLANE_COUNT=21` | default profile values; **profile-parameterised** (`PROFILE`, `CONTRACT_*`, `SPEC_*` at 254-319) — model20 overrides them |
| `reheight21/run21.py:196,240-241` | doc “1848 transitions + 200 direct endpoints”, `expected_transitions=2*(len(rows)-100)`, `expected_direct_endpoints=200` | R only (returned fields, never enforced); for 20H use `M.CONTRACT_ENDPOINT_TRANSITIONS` / `M.CONTRACT_DIRECT_ROUTES` |
| `reheight21/run21.py:266` | `layer_model='21 heights (19 body planes + 2 routable interface planes)'` written into `fanout_selected.json` | R |
| `reheight21/run21.py:756-757,810-812,844` | “/52 /48”, experiment name, “21 routing heights…” in run21-only payload/log | R (not used by nonc4) |
| `reheight21/run21.py:368` | `plane = 'z1' if abs(z) < 0.25 else 'z2'` (lead blocker classification) | L but **still correct for 20H** (0.025 < 0.25 < 0.525); brittle, could use interface rows |
| `reheight21/validate21.py:80-82` | schema names `fanout_first_21_height_*` | R (report/schema naming only) |
| `reheight21/validate21.py:99-101` | baseline-18L regression constants (18108 etc.) | baseline-mode only, harmless |
| `reheight21/validate21.py:2103,2272-2286,2877,2965` | `'21_height'` flags, `build_stack('consistency_21h')`, `2048` expected transitions in transcript, `21h` log labels | R (naming only; the numeric contract checks now use `SPEC_PLANE_COUNT`/`SPEC_DIRECT_*` from the active model) |
| `reheight21/validate21.py:2024-2050,2676-2746` | plane-count/direct-count/crossing-audit contract checks | **L but already profile-parameterised** at 22:33 (`SPEC_PLANE_COUNT`, `SPEC_BODY_PLANE_COUNT`, `SPEC_DIRECT_*`; see §9) — a 20H profile passes as verified in-process |
| `l3d/layers.py:32` | `INTERFACE_ROWS = {'z1':0.0,'z2':0.5}` | default remains; **now overridable per stack** (`interface_rows` field 108-110, `build_stack(..., interface_rows=None)` 245-246); 20H passes 0.025/0.525 (`model20.py:589-596`) |
| `l3d/layers.py:122-135` | routing layer ids had to be contiguous from L2 | **already relaxed upstream at 22:32** to “start at 2, unique” so `{2..18,20}` is legal; all clearance/pitch/interface-row checks unchanged |

---

## 7. Artifacts a 20H upstream stage must provide before the nonc4 campaign can start

### 7.1 What the campaign actually consumes from its “frozen baseline”
From `data.py`, `run_nc.py`, `validate_nc.py`, `crossings.py`, `final_report.py`:

1. **`assignment_1024.csv`** (`P.BASELINE_21H_DIR/assignment_1024.csv`, read by
   `data.load_baseline_assignment` and `data.baseline_columns`) — the connectivity/identity source.
   Required columns (27, exactly the frozen schema, `assign_nc.py:37-46`):
   `route_id, plane, relation, manual_group, manual_pattern, layer_role, target_layer,
   target_plane_label, target_z_mm, interface_z_mm, direction, needs_transition, c4_group_id,
   rotation_phase, baseline_old_layer, source_endpoint, target_endpoint, source_side, target_side,
   source_connector, target_connector, source_x_mm, source_y_mm, target_x_mm, target_y_mm,
   source_row, target_row`.
   For 20H: 1024 rows, `target_layer` ∈ the 20 new plane ids (no 19), `target_z_mm` = new heights,
   `interface_z_mm` = **0.025 (z1) / 0.525 (z2)**, 368 manual rows on planes 2,3,4,5,10,11,12,13,
   z1:z2 = 512:512. Port columns must equal the frozen authoritative ports (they are generated from
   `common.endpoints()`; `assign_nc.build_audit` re-checks identity against `base_rows`).
2. **`fanout_selected.json`** (`data.baseline_fanout_selected`, `run_nc.load_baseline_manual_fanout`).
   Schema `fanout_selected_v1` (frozen file) / `reheight21_fanout_selected_v1` (run21-written):
   `{schema, radius_mm: 15.0, clearance_mm: 0.05, route_count: 1024,
     selected: {str(route_id): {source: <transition record>, target: <transition record>}}}`.
   Each transition record fields (observed): `route_id, endpoint_role, endpoint_id, candidate_id,
   lead_mm, start_xy, start_xyz, direction, z0, z1, target_layer, target_z_mm, target_z, end_xy,
   end_xyz, footprint_mm, length_mm, theta_rad, radius_mm, geometry:'two_arc_S', needs_transition,
   transition{kind,start,direction,z0,z1,dz_mm,radius_mm,footprint_mm,theta_rad,end,length_mm},
   reverse_transition{…}, lead_part{kind:'flat', layer_id:1, z_mm, length_mm, primitives:[line]}`.
   For the nonc4 campaign only the **368 manual entries** are consumed (they become `fixed` in stage B);
   `z0` must be 0.025/0.525 and `z1` the manual-plane height.
3. **`routes_l3d.json`** (`data.baseline_routes`, `run_nc.load_baseline_manual_routes`). Frozen schema
   `reheight21_routes_l3d_v1` (or `reheight20_…`): top-level `{schema, topology:'MANUAL_C4',
   algorithm, experiment, process_mode, layer_model, route_count:1024, routed, failed,
   layer_stack, process, joint_repair_history, routes:[…1040 records incl. failures…]}`.
   Route record fields used by nonc4: `route_id, plane, target_layer, target_plane,
   target_plane_label, target_z_mm, needs_transition, n_transitions, length_mm, layer_sequence,
   layer_z_sequence, start_z_mm/end_z_mm, manual_group, source/target endpoint fields, parts:[flat|transition]`.
   Only the **368 manual records** are strictly required (frozen as D56 blockers, copied into the final
   assembly, and compared bit-identically by `validate_nc._extra_checks`/`manual_frozen_check`), but all four
   consumers load the whole file.
4. **Model payloads** (recommended, not strictly read by the campaign): `layer_planes.json`,
   `physical_layer_stack.json`, `process_rules.json` of the 20H baseline (schema from model20; the campaign
   writes its own copies per experiment via `assign_nc.write_model_payloads`).
5. **`crossing_stats.json`** of the 20H baseline (schema `fanout_first_21_height_crossing_stats_v1` in the
   frozen validator, may become `reheight20_…`): used only by `final_report.write_reports`
   (`D.baseline_crossing_stats`) for the comparison numbers — optional for the pipeline core.
6. **Active 20H height profile**: `coldstart20.bootstrap` installed before any nonc4 import
   (`model20.py` + patched `common.INTERFACE_Z/Z1/Z2` + `l3d.INTERFACE_ROWS` + reset stack; verified working
   in-process: 20 planes, 18 body, interfaces 0.025/0.525, stack ids `{2..18,20}`, min pitch 0.05,
   `validate21.SPEC_PLANE_COUNT=20`, `check_model` 0 violations on a synthetic model payload).

The natural upstream producer is the generalised baseline chain
`python -m four_side_1024.fanout1024.coldstart20.run_initial` (`coldstart20/run_initial.py:1-77`:
install profile → `assign21.main()` → `run21.run_stages('ABCDEF')` → writes
`experiments/COLD_START_20_HEIGHT_1024/03_fanout_and_xy/run_initial_20h/` per
`coldstart20/model20.py:92-94`). As of this audit that run dir does **not exist** (coldstart20 has no
`tests_model20.py`/`drivers/` yet either; `coldstart20/__init__.py:18-21` announces them).

### 7.2 Can the campaign rebuild the manual U geometry from authoritative connectivity?
**Connectivity is not sufficient by itself** — the manual U routes are ordinary fanout+2D routing results
whose *design* additionally fixes group→plane and pattern (`MANUAL_GROUP_SPECS`, e.g. `Z1-U1` on L2,
`pattern='NS-first'`; `model20.py:231-248`), where `manual_pattern` is metadata only (grep: `manual_pattern`
is never consumed by `fanout.py`/`layer2d.py`). The geometry is therefore re-computable by running the
normal fanout + per-height 2D routing for the 368 manual rows on their fixed manual planes — exactly what
the 20H baseline chain does. So:
* **Yes, in principle**: given the 20H assignment (planes + ports) one can rebuild the manual U bodies by
  `FANOUT.plan_fanout` + `LAYER2D.route_layer` on the 8 manual planes, deterministically;
* **but the current nonc4 code cannot**: it hard-freezes them and excludes them from C. The code that would
  have to change to rebuild inside the campaign is:
  * `run_nc.stage_b` (`run_nc.py:107-110`) — stop passing `fixed=load_baseline_manual_fanout()` (or pass
    only non-manual fixed records);
  * `run_nc.build_layer_tasks` (`run_nc.py:150-151`) — remove the `if D.is_manual(row): continue` skip so
    manual rows get 2D tasks on their manual planes;
  * `run_nc.initial_routes_for` (`run_nc.py:165-176`) — stop injecting `frozen_manual_bodies()` as initial
    2D routes (keep only the interface lead blockers, which are also regenerated by fanout);
  * `run_nc.assemble_all` (`run_nc.py:219-225`) — drop the “manual record copied from baseline” branch and
    assemble manual routes from the newly routed body + fanout transitions like any other route;
  * `run_nc.repair_failed`/`_insert_one_route`/`_resolve_planes` (`run_nc.py:587-596,603-609,641-718,
    721-800`) — remove the manual “copy baseline record” special case and the frozen manual blockers;
  * `run_nc.load_baseline_manual_routes/load_baseline_manual_fanout/frozen_manual_bodies` (`run_nc.py:63-100`)
    — no longer the geometry source (still useful for a read-only regression comparison);
  * `run_nc.manual_frozen_check` (`run_nc.py:928-952`) and `validate_nc._extra_checks`
    (`validate_nc.py:108-126`) — replace the bit-identical-to-21H-baseline contract by
    “manual routes on their model planes/z/pattern, never moved by the optimiser”;
  * `assign_nc._MANUAL_EXPECTED` can stay (same ids/counts).
  **Recommended instead:** let upstream generate the 20H baseline once (it is needed for E0 and for all
  downstream audits), and keep the campaign’s manual freeze semantics unchanged (re-point only). This keeps
  the “368 manual routes frozen” contract that Native3D/G123/G4 audits rely on
  (`native3d` freezes E5’s manual U geometry; `E5/validation.json:nonc4.manual_routes_frozen_to_baseline`).
  Note the physical z of the manual geometry **must** change (+0.025); only XY is invariant (all transition
  `dz` are unchanged by a uniform shift, so the regenerated XY geometry should equal the 21H XY).

---

## 8. Wall-clock cost (measured from `_logs/run.log`, console logs, file timestamps)

21H machine timings (one machine, same .venv):

| step | wall | breakdown / note |
|---|---|---|
| E0 full (incl. validate) | **107 s** (22:51:16→22:53:03) | B 20.3 s (fanout core 10.1 s + validation/artifacts); C/D iter1 layer2d 4.1 s + assemble/world 15 s; lead repair 10.4 s; iter2 layer2d 3.3 s + assemble 16 s; crossing report 17 s; validate21 20 s |
| E1 (crashed) | **100 s** (22:53:09→22:54:49) | reached “local insert repaired=3 remaining=1”, then NameError; no crossing/validation |
| E2 full | **87 s** (23:03:52→23:05:19) | SA plan/partition ~7 s; B 21.1 s; C layer2d 2.9 s; assemble/world 14 s; crossing 19 s; validate 22 s |
| S_A / S_V3 screening (each) | **~45 s / 39.1 s** | SA plan ~6 s; fanout 24 s; 2D 12–13 s; crossing screen ~1 s (`screening.json: seconds=39.06`) |
| E3 full (final run) | **158 s** (23:14:11→23:16:49) | B 23.3 s; iter1 layer2d 11.2 + assemble 15 s; iter2 lead-repair 11 + layer2d 9.2 + assemble 15 s; repair local 10 + plane re-solve 10 s; crossing 16 s; validate 19 s. (First attempt 23:11:13→23:13:16 = 123 s, discarded after routes written.) |
| E5 full (accepted) | **138 s** (23:17:42→23:20:00) | B 22.4 s; iter1 layer2d 9.3 + assemble 15 s; iter2 lead-repair 10.9 + layer2d 9.2 + assemble 16 s; local insert 5 s; crossing 18 s; validate 22 s |
| E4 cross-aware verification | single-layer runs 2.6–15.5 s vs production 0.1–0.4 s; full 10-plane verification ≈ 77 s compute (`verify_all.log`), whole E4 exploration ≈ 22 min (probes included) |
| analysis `run_all.py` | ≈ 2–4.5 min (file timestamps 23:04→23:08:34; step1 crossing DB written 23:08:25; 11890-event audit is the expensive part) |
| finalize (plots+reports+manifest+archive) | ≈ 35 s (23:25:07→23:25:42) + one failed attempt at 23:25:12 (TypeError at `final_report.py:321`, int not subscriptable — fixed by re-run) |
| hidden startup/import cost | ≈ 3–5 s per process (numpy/matplotlib/frozen modules) |

**20H estimate:** the campaign shape is identical; one body plane fewer (18 vs 19) and one non-manual plane
fewer (12 vs 13) cuts C/D routing by ≈ 5–8 %. Expect: E0 ≈ 100 s; E2 ≈ 85 s; screening ≈ 40 s each;
E3/E5-class full run ≈ 140–160 s; validator 20 s each; if the 02_annealing cost-curve study is run,
+60–120 s; analysis of the 20H baseline ≈ 3–5 min (must be re-done because the Z2 redistribution over
7 planes changes per-plane crossings); finalize ≈ 35 s. **Total rebuild campaign ≈ 25–40 min** of compute,
plus the upstream 20H baseline generation (`coldstart20.run_initial`) which is a full A–F baseline run
(comparable to one E3/E5-class run plus assign21, ≈ 2–4 min).

---

## 9. Concrete adaptation points for the 20-height rebuild

Status at audit checkpoint (2026-11-17 22:38): items marked **[upstream]** are already provided by the
concurrent `coldstart20` work; everything else is nonc4/campaign work still to do. Decision on the campaign
output root (`EXPERIMENT_ROOT`) is the Lead’s; the `COLD_START_20_HEIGHT_1024/NN_*` stage layout suggests
`02_annealing` (SA/screening), `03_fanout_and_xy` (20H baseline generation), `04_initial_3d_and_e5_repair`
(campaign B–E) — verify against the stage plan before coding.

1. **Wire the profile first**: every cold-start nonc4 driver must start with
   `from four_side_1024.fanout1024.coldstart20 import bootstrap` **before** importing any nonc4/pipeline
   module; then `bootstrap.install(run_dir=…)`/`bind_run_dir`. Otherwise nonc4’s `M` is the 21H module and
   the run silently uses 21 heights. **[upstream: coldstart20/bootstrap.py:1-162]**
2. **`nonc4/paths.py`**: `EXPERIMENT_ROOT` → 20H campaign root (new);
   `BASELINE_21H_DIR` → `BASELINE_20H_DIR = COLD_START_ROOT/'03_fanout_and_xy'/'run_initial_20h'`
   (or the accepted 20H baseline dir); keep the 21H constant only for read-only comparisons.
   `BASELINE_18L_DIR` may be deleted (dead).
3. **`nonc4/data.py:24`**: `Z2_OTHER_PLANES = (9,14,15,16,1002,17,18)` (drop 19).
4. **`nonc4/assign_nc.py:63-79`**: rewrite `default_allocation` for 12 non-manual planes / 7 Z2 planes
   (family-pure candidate: `Z1V[6,7]`, `Z1H[20,8,1001]`, `Z2_NE[9,14]`, `Z2_SE[15,16]`, `Z2_NW[17]`,
   `Z2_SW[18,1002]`, predicted 2273; the chosen candidate must be screened — see item 6);
   `_MANUAL_EXPECTED` unchanged.
5. **`nonc4/assign_opt.py:222`**: `plane_count=12`; add the missing glue that turns the
   `optimise_allocation` result into an allocation (e.g. `allocation_from_counts`); update
   `default_allocation` doc/slices; optionally fix `partition_min_intra` wall-clock dependence (fixed
   iterations or recorded seed/version) for reproducibility.
6. **`nonc4/experiments.py`**: E0 = reproduce the **20H** baseline; E2 default counts sum to 12;
   **add first-class `e3`/`e5`/`screen` subcommands** (re-create the archived ad-hoc drivers:
   `assign_opt.plan_structured(rows, allocation=…)` + `run_nc.run_standard(budgets=(600,1200), max_iters=2)`
   + `validate_nc`; E5 = plan edit of the failed routes before the run; screen = `search.screen_plan`).
7. **`nonc4/validate_nc.py:32-34`**: `_EMPTY_PLANE_KINDS` → current validator kinds
   (`planes_audited_count_mismatch`, `assignment_used_planes_mismatch`, keep
   `model_planes_without_flat_geometry`); keep `_C4_ALLOWED_KINDS`.
8. **`nonc4/run_nc.py:308-316`**: replace the frozen provenance strings/layer_model with values derived
   from the active model (`len(M.PLANE_IDS)`, `len(M.BODY_PLANES)`, `M.PROFILE`, `M.EXPERIMENT_NAME`,
   baseline dir name).
9. **`nonc4/final_report.py`**: recompute all baseline numbers from the 20H baseline
   `crossing_stats.json` (currently hard-coded 11890/9797 and the E-chain 6495/8000/2586/2606), fix
   “21 heights” everywhere, drop the `experiments e3` claim unless item 6 is done, and re-point the archive
   target/git repo.
10. **Manual geometry**: keep the freeze, but source it from the 20H baseline (item 2 makes this automatic);
    do **not** inherit the 21H `routes_l3d.json`/`fanout_selected.json` (wrong z, and Z2 manual plan is the
    same ids but new z). If rebuilding inside the campaign is preferred, change the code points listed in
    §7.2.
11. **E5-style cross-height rejoining**: re-create the 2-route reallocation driver (E3→E5 delta) as part of
    stage 04; `run_nc` has no cross-height re-allocation.
12. **Height-profile invariants to assert in every 20H nonc4 run** (no relaxation):
    `len(M.PLANE_IDS)==20`, `len(M.BODY_PLANES)==18`, `19 not in M.PLANE_IDS`,
    `M.Z1_INTERFACE_MM==0.025`, `M.Z2_INTERFACE_MM==0.525`, glass z ∈ [−0.35, +0.65],
    `min_pitch == 0.05` (floating value 0.04999999999999993 passes the 1e-9 tolerance),
    R15 = 15, 3D clearance 0.05, strict D56 0.08; assignment audit `passed=True`, validation
    `validation_pass=True` with 0 violations.
13. **Upstream remains to be produced/verified [upstream gap]:** the 20H baseline run dir (fanout/2D/3D +
    full artifacts + validation) and the `coldstart20` tests/drivers announced in
    `coldstart20/__init__.py:18-21` are still missing at 22:38; nothing else in the nonc4 package can be
    finalised before that run exists.

---

## 10. Open risks / questions for the Lead

1. 20H plane budget: the realistic family-pure chord lower bound is **2273** (vs 1510 at 21H) unless a
   cross-side plane borrow (1768, needs `ALLOWED_PLANES` relaxation) or the E2-style sharing (746, previously
   unrealisable) is proven routable. The 20H C4-free campaign may well end **worse than the 21H 2606**, which
   changes the expected input to 05_native3d/G123/G4 — plan the target numbers accordingly.
2. The campaign’s reproducibility currently depends on ad-hoc drivers that were not archived (E3/E5/S_A/S_V3)
   and on wall-clock-budgeted SA; both must be fixed in the rebuild.
3. Manual-U freeze semantics vs 20H: only z changes, XY should be invariant for a uniform height shift, but
   the Z2 non-manual redistribution in the 20H baseline (`model20.Z2_OTHER_PLAN`, L19’s 52 routes moved to
   other Z2 planes) changes the 20H baseline crossing count and per-plane stats — re-run the analysis and
   re-baseline all comparison numbers.
4. The 20H `INTERFACE_ROWS` change is a **global** `l3d` configuration (0.025/0.525). Any module that
   hard-codes z = 0.0/0.5 (`common.interface_z` users are patched by bootstrap; fanout’s internal
   `_transition_audit` still compares against `common.interface_z`, so it is covered; but the
   frozen 18L/21H experiments must not be imported in the same process *before* bootstrap if they are to be
   re-run) needs auditing in the 01_height_config stage.
5. Downstream handoff: `native3d/common.py:19`, `xyzrouter/paths.py:19`,
   `native3d/validate_native3d.py:128` point at the 21H `E5_joint_repair_final`; the new accepted 20H
   solution path must be injected there when stage 05 starts.
