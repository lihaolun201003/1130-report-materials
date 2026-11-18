# `reheight21` audit — frozen 21-height chain → 20-height rebuild

READ-ONLY audit. Written 2026-11-17 ~22:40 (local). No file was modified except this
one; the only commands executed were read-only imports / in-memory probes (no
pipeline stage was run, nothing was written under any `outputs/` or `experiments/`
directory except this file).

Target of the rebuild: 20 routing heights = **18 body planes + 2 routable interface
planes**; delete plane **L19 (id 19, z=+0.65)**; raise every surviving height by
**+0.025 mm**; keep `plane_id` as identity (`L2..L18`, `L20` ids unchanged);
`Z1_INTERFACE = +0.025`, `Z2_INTERFACE = +0.525`; glass z range unchanged
`[-0.35, +0.65]`; R15 / 0.05 mm true-3D clearance / strict D56 are **never**
relaxed.

---

## 0. Snapshot, provenance and method

Two code states exist right now and they must not be confused:

| state | location | how it is used below |
|---|---|---|
| **frozen 21H release** (the chain that produced the accepted 21H artifacts) | `experiments/fanout_first_21_height_rebalanced_1024/code/reheight21/` (mirror: `work/11.9-second-report-all-work/experiments/...`, backup: `work/_backups/OpticalWaveguideRouter2D_20261117_1118/`) | **all `file:line` references for `reheight21/*.py` below are to this snapshot** |
| **live working tree** (being rewritten for 20H while this audit ran) | `OpticalWaveguideRouter2D/four_side_1024/fanout1024/` | only used in §10 (in-flight status) |

Frozen 21H snapshot (sha256 first 16 hex):

| file | bytes | sha256[:16] |
|---|---:|---|
| `model.py` | 31248 | `842ef8d72d18ace4` |
| `assign21.py` | 68627 | `2905e8f5f35982c6` |
| `run21.py` | 59279 | `c2d9931bcb5e598d` |
| `validate21.py` | 151157 | `6d4f43a063030c9a` |
| `plots21.py` | 144146 | `c1e1badebf98f2a5` |
| `report21.py` | 97837 | `eb40634e12f62860` |
| `archive21.py` | 23387 | `ad34a1d66b69ed96` |
| `SPEC.md` | 9234 | `e4c6432d124cbc9b` |

Shared modules: `fanout.py` 96249B `e3156fe22be60beb`, `assemble.py` 13258B
`9f65f06c56a8f696`, `common.py` 13699B `18a08917fdf4ded9`, `run_all.py` 74942B
`c98ca4ac8341bb25` — all byte-identical to the 21H archive.
`layer2d.py` current tree 88963B `712ebc5472e31a7b` vs archived 83671B
`d0de64e35438861e` (post-21H layer2d patches; line refs below are to the current
tree, which is what a rebuild will use). `four_side_1024/l3d/layers.py` frozen
13457B `8add396e6e801d73`; it was changed in-flight (15773B) after this audit's
first read — §7/§9/§10 separate the two versions.

Accepted 21H artifact reference (read-only evidence):
`outputs/manual_c4_new_connectivity/FANOUT_FIRST_21_HEIGHT_REBALANCED_1024/`
— `validation.json`: routed 1024, failed 0, direct 100 (52+48), transitions 1848,
21 planes audited, same-plane crossings 11890 / pairs 9797, min 3D clearance
0.100699741 mm, geometry+contract+consistency PASS, exit 0. `run.log` 737 lines.

**Concurrent-change warning** (§10): during this audit (`22:28`–`22:40`) another
agent was already editing the live tree — `l3d/layers.py`, `reheight21/model.py`,
`assign21.py`, `run21.py`, `validate21.py`, plus a new `coldstart20/` package
(`model20.py`, `bootstrap.py`, `run_initial.py`). Therefore the frozen line numbers
in §1–§8 are stable, while the live-tree line numbers in §10 are timestamped and
may drift.

---

## 1. `model.py` — public API and the 21-specific configuration

### 1.1 Public API inventory

`__all__` is at **model.py:666-698**. Everything an external module can rely on:

* run paths (resolved at call time by drivers): `ROOT` 65, `OUTPUT_ROOT` 66,
  `BASELINE_RUN_NAME` 67, `NEW_RUN_NAME` 68, `RUN_DIR` 71, `BASELINE_RUN_DIR` 73,
  `NEW_RUN_DIR` 76, `OLD_RUN_DIR` 77, `BASE_ASSIGNMENT` 80, `BASE_AUDIT_JSON` 81,
  `BASE_STACK_JSON` 82, `NEW_ASSIGNMENT` 84, `NEW_ASSIGNMENT_AUDIT` 85,
  `NEW_ASSIGNMENT_DIFF_JSON` 86, `NEW_ASSIGNMENT_DIFF_MD` 87,
  `LAYER_PLANES_JSON` 88, `NEW_STACK_JSON` 89, `NEW_RULES_JSON` 90,
  `NEW_EXPERIMENT_A` 91, `BASELINE_ASSIGNMENT_CSV` 92, `NEW_ASSIGNMENT_CSV` 93,
  `NEW_LAYER_PLANES_JSON` 94;
* geometry constants: `GLASS_THICKNESS_MM` 97, `GLASS_Z_MIN_MM` 98,
  `GLASS_Z_MAX_MM` 99, `MIN_LAYER_PITCH_MM` 100, `MIN_3D_CLEARANCE_MM` 101,
  `MIN_BEND_RADIUS_MM` 102, `Z1_INTERFACE_MM` 103, `Z2_INTERFACE_MM` 104;
* plane tables: `BODY_PLANES` 108-114, `BODY_PLANE_Z` 115, `INTERFACE_PLANES`
  118-121, `Z1_INTERFACE_PLANE_ID` 122, `Z2_INTERFACE_PLANE_ID` 123,
  `INTERFACE_PLANE_IDS` 124, `INTERFACE_STACK_ROWS` 127-128, `PLANE_IDS` 131-132,
  `PLANE_ORDER` 133, `PLANE_Z` 135-140, `PLANE_LABEL` 142-148, `PLANE_KIND`
  150-154, `PLANE_SIDE` 157-162, `PLANE_ROLE` 180, `PLANE_ROLE_DETAIL` 164-177,
  `PLANE_LAYER_ROLE` 186-196, `INTERFACE_Z` 198;
* manual groups: `MANUAL_GROUP_SPECS` 203-220, `MANUAL_GROUPS` 223-228,
  `MANUAL_LAYER_TO_GROUP` 229-230, `MANUAL_PLANE_IDS` 231, `MANUAL_ROLES` 232,
  `Z1_GROUP_ORDER` 233, `Z2_GROUP_ORDER` 234;
* allocation plans: `Z1_OTHER_PLAN` 239, `Z2_OTHER_OLD_TO_NEW` 243-246,
  `Z2_OLD_TO_NEW_PLANE` 247, `Z2_LAYER_MAP` 248;
* baseline (read-only) tables: `BASELINE_LAYER_Z` 251, `BASELINE_LAYER_IDS` 252;
* helpers: `all_plane_ids` 275, `planes` 280, `body_plane_ids` 309,
  `is_interface_plane` 315, `is_direct_plane` 319, `plane_z` 324,
  `plane_label` 329, `plane_kind` 334, `plane_side` 339, `plane_role` 344,
  `plane_role_detail` 349, `interface_z` 354, `interface_plane_for` 373
  (alias `interface_plane_id` 391), `needs_transition` 394, `direction_for` 402,
  `layer_z` 414, `manual_group_plane` 417, `min_height_pitch` 422,
  `layer_stack` 432 (alias `stack` 453), `reset_stack` 456, `raw_stack_payload`
  463, `write_json` 469, `layer_planes_payload` 491, `stack_payload` 562 (alias
  `physical_layer_stack_payload` 613), `process_rules_payload` 616.

Downstream production code imports the module under an alias and touches
(verified by AST-style grep across `nonc4/`, `native3d/`, `xyzrouter/` — full list
in §11): `RUN_DIR, NEW_RUN_DIR, NEW_ASSIGNMENT, NEW_ASSIGNMENT_AUDIT,
NEW_ASSIGNMENT_DIFF_JSON/MD, LAYER_PLANES_JSON, NEW_STACK_JSON, NEW_RULES_JSON,
NEW_EXPERIMENT_A, PLANE_IDS, PLANE_LAYER_ROLE, MANUAL_GROUPS,
MANUAL_LAYER_TO_GROUP, MANUAL_PLANE_IDS, GLASS_Z_MIN_MM, GLASS_Z_MAX_MM,
MIN_LAYER_PITCH_MM, Z1_INTERFACE_MM, Z2_INTERFACE_MM, plane_z, plane_label,
plane_kind, planes(), layer_stack(), stack_payload(), layer_planes_payload(),
process_rules_payload(), body_plane_ids(), interface_z(), is_interface_plane()`.

Two structural facts matter for the rebuild:

* `model.py` is the single height seam: every pipeline module does
  `from ..reheight21 import model as M` (or `from . import model as M` in
  `assign21/run21/validate21`), so a **different height table only needs a
  different model module** (this is exactly what the in-flight
  `coldstart20.bootstrap` does — §10).
* module-level derived tables are computed **once at import** (`PLANE_Z`,
  `PLANE_LABEL`, `PLANE_KIND`, `PLANE_SIDE`, `PLANE_LAYER_ROLE`, `MANUAL_GROUPS`,
  `MANUAL_LAYER_TO_GROUP`, `MANUAL_PLANE_IDS`, `PLANE_ORDER`, `BODY_PLANE_Z`,
  `INTERFACE_Z`). Patching e.g. `M.BODY_PLANES[...]` in place after import does
  **not** refresh them; a 20H table must replace the whole module object (or
  reassign every derived name + `reset_stack()`).

### 1.2 Which values are 21-specific literals, which are derived

**Hardcoded (must be re-authored for 20H):**

| item | lines | 21H value | 20H value |
|---|---|---|---|
| `NEW_RUN_NAME` | 68 | `FANOUT_FIRST_21_HEIGHT_REBALANCED_1024` | new name/dir |
| `Z1_INTERFACE_MM` / `Z2_INTERFACE_MM` | 103-104 | `0.0` / `0.5` | `+0.025` / `+0.525` |
| `BODY_PLANES` | 108-114 | 19 heights, incl. `(19, 0.65)` | **18 heights**: delete 19, all `+0.025` |
| `INTERFACE_PLANES` | 118-121 | ids 1001/1002 at z from the two constants | same ids, new z (derived from 103-104) |
| `PLANE_IDS` | 131-132 | tuple of 21 ids incl. 19 | tuple of 20 ids, no 19 (`2..18,20,1001,8,9,...`) |
| `PLANE_SIDE` membership tuple | 157-162 (`(1001, 2,3,4,5,6,7,8, 20)`) | `...8,20` z1-side | drop 19 (19 was z2 anyway; tuple can stay) |
| `PLANE_ROLE_DETAIL` | 164-177 | entry `(19, 'Z2 other adjacent')` | delete the `(19, ...)` entry |
| `_MANUAL_PLANE_IDS_LAYOUT` | 185 | `(2,3,4,5,10,11,12,13)` | unchanged |
| `MANUAL_GROUP_SPECS` z_mm | 203-220 | `-0.35,-0.30,-0.25,-0.20` + `0.15,0.20,0.25,0.30` | all `+0.025` (`-0.325,...` / `0.175,...`) |
| `Z1_OTHER_PLAN` | 239 | `((6,13),(7,13),(20,13),(1001,13),(8,12))` | **unchanged** (all five planes survive) |
| `Z2_OTHER_OLD_TO_NEW` | 243-246 | 8-entry 1:1 map (`8→9, 9→14, ..., 19→1002`) | **impossible**: only 7 non-manual Z2 planes survive → replace with a plan/hook (`(plane, orbits)` or many-to-one) |
| `layer_stack()` implementation | 432-449 | `build_stack('reheight21', heights=BODY_PLANES)` (interface rows frozen by l3d) | must pass the new interface rows and tolerate non-contiguous ids — see §9 |
| payload schema/experiment strings | 524, 567-568, 621, 646, 658-661, 703-607 | `reheight21_*`, "21 heights" notes | profile-specific schema/notes |
| `stack_payload` `route_count` | 593 | 1024 | 1024 (unchanged, it is the route count) |

**Derived (recomputed automatically once the sources above are replaced):**
`BODY_PLANE_Z` 115, `PLANE_Z` 135-140, `PLANE_LABEL` 142-148, `PLANE_KIND`
150-154, `PLANE_LAYER_ROLE` 186-196, `INTERFACE_Z` 198, `MANUAL_GROUPS` 223-228,
`MANUAL_LAYER_TO_GROUP` 229-230, `MANUAL_PLANE_IDS` 231, `INTERFACE_PLANE_IDS`
124, `INTERFACE_STACK_ROWS` 127-128, `BASELINE_LAYER_Z/IDS` 251-252 (18-layer
baseline, read-only — unchanged), and every helper function (all read the tables
at call time).

### 1.3 Exact globals that need rebinding / rewriting for a 20-height table

Rebinding (or replacing the module with a 20H profile) must cover at least:
`BODY_PLANES`, `BODY_PLANE_Z`, `INTERFACE_PLANES`, `INTERFACE_PLANE_IDS`,
`INTERFACE_STACK_ROWS`, `PLANE_IDS`, `PLANE_ORDER`, `PLANE_Z`, `PLANE_LABEL`,
`PLANE_KIND`, `PLANE_SIDE`, `PLANE_ROLE`, `PLANE_ROLE_DETAIL`,
`PLANE_LAYER_ROLE`, `INTERFACE_Z`, `Z1_INTERFACE_MM`, `Z2_INTERFACE_MM`,
`MANUAL_GROUP_SPECS`, `MANUAL_GROUPS`, `MANUAL_LAYER_TO_GROUP`,
`MANUAL_PLANE_IDS`, `MANUAL_ROLES`, `Z1_GROUP_ORDER`, `Z2_GROUP_ORDER`,
`Z1_OTHER_PLAN` (unchanged value but must exist), `Z2_OTHER_OLD_TO_NEW`,
`Z2_OLD_TO_NEW_PLANE`, `Z2_LAYER_MAP`, `_STACK` (via `reset_stack()`),
`RUN_DIR`, `NEW_RUN_DIR`, `NEW_RUN_NAME`, `NEW_ASSIGNMENT`,
`NEW_ASSIGNMENT_AUDIT`, `NEW_ASSIGNMENT_DIFF_JSON/MD`, `LAYER_PLANES_JSON`,
`NEW_STACK_JSON`, `NEW_RULES_JSON`, `NEW_EXPERIMENT_A`,
`NEW_ASSIGNMENT_CSV`, `NEW_LAYER_PLANES_JSON`, plus the payload schema/experiment
strings (or profile constants that feed them). `BASELINE_RUN_DIR` /
`BASELINE_*` stay pointed at the frozen 18-layer baseline (read-only comparison).

The live tree already has the profile seam (`EXPERIMENT_NAME`, `PROFILE`,
`MODEL_NAME`, `SCHEMA_*`, `CONTRACT_*`, `SPEC_*`, `allocate_z2_other`,
`Z2_OTHER_PLAN = None` in `reheight21/model.py:254-350`) and a full 20H replacement
module in `coldstart20/model20.py` — see §10.

---

## 2. `assign21.py` — what it computes, in what order

Entry points: `main()` **assign21.py:1432-1446**; importable counterpart
`build_assignment(force=True)` + `write_all(rows)`; documented CLI
`python -m four_side_1024.fanout1024.reheight21.assign21` (docstring 38-44).

### 2.1 Call order

1. `build_assignment()` **226-345**
   1. `C.routes()` → the true 1024 connections (`common.routes`, never
      regenerated); sorted by `route_id`.
   2. `load_baseline()` **110-144** — reads the frozen 18L
      `BASELINE_RUN_DIR/assignment_1024.csv` **read-only** + sha256; builds
      `by_id`, plane/manual/layer counters; hard guard 1024 rows.
   3. `C.rotation_groups()` → 64 Z1 `opposite` orbits and 100 Z2 `adjacent`
      orbits, both sorted by `group_id` (241-248); hard guard 64/100 (249-252).
   4. `_manual_allocation()` **155-178** — membership from the baseline manual
      rows; requires the baseline manual `target_layer` ==
      `M.MANUAL_GROUP_SPECS[group]['plane_id']` (168-171), so manual plane ids
      are frozen.
   5. `_z1_other_allocation()` **181-198** — consumes whole orbits in plan order
      `M.Z1_OTHER_PLAN`; every orbit's 4 routes to one plane.
   6. `_z2_other_allocation()` **201-223** — 100 whole orbits; the baseline old
      target layer per orbit is looked up and remapped through
      `M.Z2_OTHER_OLD_TO_NEW`; requires the orbit's baseline old layer to be
      unique (209-211) and present in the map (213-215).
   7. build the 1024 rows (263-327): `target_layer`, `target_plane_label`,
      `target_z_mm = M.plane_z`, `interface_z_mm = M.interface_z(plane)`,
      `direction`/`needs_transition` from `M.needs_transition/direction_for`,
      plus the port data + `c4_group_id`/`rotation_phase` from the real route
      table; `baseline_old_layer` = the old target layer (`''` for manual).
   8. `_check_contract()` **644-669** — fail-fast: 1024 unique rows, 512/512
      split, exact `EXPECTED_PLANE_COUNTS`, exact direct count, target z and
      direction consistent with the model.
2. `write_all()` **1336-1370**, in this order:
   `layer_planes.json` (assigned counts), `assignment_1024.csv`,
   `physical_layer_stack.json`, `process_rules.json`, `build_diff()` +
   `diff_markdown()` → `assignment_diff_vs_baseline.json/.md`, `build_audit()`
   (`_invariants` **360-641**), baseline sha256 before/after → `baseline_untouched`,
   `_experiment_a()` → `experiment_A/{summary.json,layer_audit.csv,audit.json,
   validation_status.json}`, then `assignment_audit.json`.
3. `main()` prints `summary_lines()` (1374-1418) and appends 5 lines to `run.log`
   (1421-1429).

### 2.2 What drives the assignment

* Z1 `other` plan: `M.Z1_OTHER_PLAN` (model.py:239) — whole C4 orbits, sorted by
  `group_id`, capacities 13/13/13/13/12 → **52/52/52/52/48** routes on planes
  `6/7/20/1001/8`.
* Z2 `other` mapping: `M.Z2_OTHER_OLD_TO_NEW` (model.py:243-246) — whole C4
  orbits keyed by the **baseline** old target layer (8,9,14,15,16,17,18,19) →
  8 planes (9,14,15,16,17,18,19,1002).
* manual groups: `M.MANUAL_GROUP_SPECS` (model.py:203-220) — fixed planes
  2/3/4/5 (Z1, 64 each) and 10/11/12/13 (Z2, 16/16/40/40), membership from the
  verified baseline.

### 2.3 Per-plane expected counts are hardcoded

Yes, in three places:

* module constants **70-103**: `EXPECTED_PLANE_COUNTS` 70-76,
  `EXPECTED_DIRECT_ROUTES=100` 77, `EXPECTED_DIRECT_Z1=52` 78,
  `EXPECTED_DIRECT_Z2=48` 79, `EXPECTED_TRANSITION_ROUTES` 80,
  `EXPECTED_ENDPOINT_TRANSITIONS=1848` 81, `EXPECTED_MANUAL_COUNTS` 82-85,
  `EXPECTED_MANUAL_TOTAL=368` 86, `EXPECTED_Z1_OTHER_COUNTS` 87-88,
  `EXPECTED_OLD_LAYER_COUNTS` 90-93, `EXPECTED_Z2_OTHER_COUNTS` 95-97,
  `EXPECTED_MANUAL_ORBIT_PLANE_SETS` 101-103;
* enforced in `_check_contract` (654-656) and in `_invariants`
  (`plane_counts_exact` 424-428, `direct_route_count_100` 443-451,
  `transition_routes_924_endpoints_1848` 452-457, manual 383-389,
  z1/z2 other counts 429-442, manual orbit split 559-580);
* the audit/experiment-A payloads (`build_audit` 673-776, `_experiment_a`
  1142-1332) re-use those constants.

### 2.4 Determinism

Fully deterministic: rows iterated in `route_id` order (263), orbits sorted by
`group_id` (241-248), plans consumed in list order, `sorted()` used for every
container, no RNG, no time-dependent values; JSON/CSV writers are plain. A
built-in invariant `deterministic_rebuild` (**636-638**) rebuilds with
`force=True` and requires byte-identical rows; `_ROWS`/`_STATE` caches only avoid
recomputation. Verified empirically (see §9.2): two consecutive builds of the 20H
profile are identical.

### 2.5 What must change for 20 heights

* `EXPECTED_*` 70-103 → read the profile contract (`M.CONTRACT_*` /
  `M.SPEC_*`); the **per-plane counts and direct/transition totals must come from
  the real 20H assignment** produced from the 20H plan, never be relaxed.
* `_z2_other_allocation` 201-223 → the 20H Z2 `other` family has **400 routes =
  100 orbits over 7 non-manual Z2 planes** (`9,14,15,16,17,18,1002`) instead of
  8, so the 1:1 old-layer map cannot exist. Replace with an explicit whole-orbit
  plan (e.g. in-flight `coldstart20/model20.py:277-278`
  `((9,14),(14,14),(15,14),(16,14),(17,16),(18,16),(1002,12))` orbits →
  56/56/56/56/64/64/48 routes) or a many-to-one old-layer map, still consuming
  **whole orbits**. With a plan consumed in ascending `group_id`, the
  old-layer→plane relation is no longer a function: a probe on the in-flight 20H
  profile shows plane 9 = 52 routes from old L16 + 4 from old L17, plane 14 =
  48 from L17 + 8 from L15, etc. (1002 gets old L8's 48 routes). The per-route
  `baseline_old_layer` column keeps the true old layer, so the diff stays
  auditable; the **aggregate audit must report per-plane old-layer composition**,
  not an old→new map. Old-layer totals stay 48/48/48/52/52/52/52/48 (they are
  baseline data), which keeps `baseline_old_layer_counts` valid.
* `build_audit` **684** and **735-736**, `build_diff` **870-898**,
  `_experiment_a` **1265-1267** dereference
  `M.Z2_OTHER_OLD_TO_NEW.items()` unconditionally → these must handle the plan
  form (or `None`) for 20H. `_invariants` **527-558** must replace
  `z2_other_orbits_follow_old_layer_map` with a "z2_other orbits follow the 20H
  plan" check.
* `build_diff` **870-898** and experiment-A Q6 (**1207-1211**,
  `audit['height_count'] == 21`) and the human strings (987, 996, 1243, 1368,
  1373) need the profile values.
* Notes in `build_audit` **750-774** hardcode the 21H z-shift wording.
* `_z1_other_allocation` 181-198 can stay unchanged for 20H (all five Z1-other
  planes survive; only their z changes, which is read from the model).

---

## 3. `run21.py` — stages A–F, budgets, model propagation

CLI: `python -m four_side_1024.fanout1024.reheight21.run21 --stages ABCDE
[--max-iters N]` (**1267-1277**; `_STAGES = 'ABCDE'` 1231). Stage letters are
accepted in any subset; `run_stages()` **1234-1264** dispatches.

| stage | function | consumes | produces |
|---|---|---|---|
| A | `stage_a` **141-189** | `assignment_1024.csv` (calls `assign21.main()` if missing, 143-146), `layer_planes.json` | validates 512/512, per-plane counts, distinct heights, direct count; writes only `layer_planes.json` if missing |
| B | `stage_b` **330-350** | rows + `M.layer_stack()`; `fanout.plan_fanout(rows, stack=...)` 334 | `fanout_selected.json` 266-275, `fanout_validation.json` 276, `layerwise_endpoints/endpoints.json` 277-279, `experiment_B/{summary.json,failed_routes.json}`, `checkpoints/stage_B_fanout.json` 346; independent `validate_fanout_selected` 197-245 (1848 transitions + 200 direct endpoints checked in a fresh `l3d.world.World`) |
| C | `_route_all_layers` 421-449 → `_experiment_c_summary` 729-760 → `_assemble_all` 510-550 → `_world_check` 553-554 → `_experiment_d_summary` 763-780 | fanout selected (in memory); `fanout.landings`/`layer_obstacles` 389-408; interface lead blockers `_interface_lead_blockers` 354-373 → `_initial_routes_for` 411-418 | `experiment_C/summary.json`, `checkpoints/stage_C_2d.json`; then `experiment_D/{summary.json,failed_routes.json}` (first pass) |
| D | `run_stages` 1252-1258 | reruns the C first pass (without interface `initial_routes`) | `experiment_D/*` overwritten |
| E | `stage_e` **1063-1162** | selected transitions + rows | the accepted solution: `routes_l3d.json`, `failed_routes.json`, `experiment_E/*`, `layerwise_routes/routes.json`, `final_stats.json`, `checkpoints/experiment_E_best.json` |
| F | `stage_finalize` **1165-1198** | `routes_l3d.json` + assignment | rewrites `experiment_D/{summary.json,failed_routes.json}` as the final accepted 3D assembly + world check |

Stage E, in detail:
* loop `iteration = 1..max_iters` (**1067**); default `--max-iters 3` (1270).
* iteration > 1 → `_replan_leads` **558-588**: only the failed non-direct routes
  are re-planned; already-fixed transitions are passed as `fixed`, `repair_ids`
  limits scope, lead vector from `_LEAD_REPAIR_VARIANTS` **34-39** indexed by
  iteration.
* `_route_all_layers` with `budget = _LAYER_BUDGETS[(i-1)%4]` **33**
  = `(600, 1200, 1800, 2400)` and `ordering_seed = i-1`; `layer2d.route_all_layers`
  is called with the explicit per-layer `{plane_id: {z_mm, tasks, obstacles}}`
  payload + `initial_routes` (432-437; a `TypeError` fallback drops the kwargs).
* `_assemble_all` (510-550) uses `ASM.assemble_route(row, None, None, body)` for
  direct rows and `(row, source, target, body)` otherwise; failures carry real
  route ids/reasons.
* `_world_check` (553-554) = `ASM.validate_routes_independent(routes,
  stack=M.layer_stack())` — a **fresh 3D world, 0.05 mm clearance**, route-id
  order; only routes that pass count as routed.
* best solution kept by `(score, fewer violations)` 1103-1109; early stop when
  1024 valid (1111-1113).
* after the loop: `_local_insert` **941-1059** (single-route insert into the
  frozen best layout; `_LEAD_PAIRS` **40-44** = 14 lead pairs, budget 2400,
  rr_rounds 0), then `_layer_resolve` **591-725** (whole-plane rip-up & re-solve,
  up to `max_seeds=16` deterministic orderings per failed plane, budget 2400,
  rr_rounds 2), refreshing fanout artifacts on any gain (`_refresh_fanout_for_repairs`
  1201-1227), then the final writers.

**Iteration budget:** the outer budget is `--max-iters` (3 default), each outer
iteration runs one full 21-plane 2D pass + one full assembly/world check; the
in-loop layer2d budgets cycle 600/1200/1800/2400; the repair phases add
14 lead-pair attempts per failed route and 16 seeds per failed plane at budget
2400. The historical run needed a second invocation with `--max-iters 2` to
converge (see §6).

**Does it hardcode 21 / does 20H propagate automatically?**
`run21` is structurally model-driven: it uses `M.PLANE_IDS`, `M.plane_z/label/
kind`, `M.INTERFACE_PLANES`, `M.is_direct_plane`, `M.layer_stack()`,
`M.INTERFACE_Z`-based helpers, and passes explicit `z_mm`/`target_z_mm`/
`layer_id` maps to `fanout`/`layer2d`/`assemble`, so a replaced model module
propagates. Remaining 21-specific literals in the frozen file:

| line(s) | literal | 20H consequence |
|---|---|---|
| 173-177 | `expected_counts = {2:64, 3:64, ..., 19:52}` | hard assertion → must use the 20H contract counts (else stage A fails) |
| 183-184 | `if len(heights) != 21` | fails (20) |
| 185-186 | `if len(direct) != 100` | numerically still true for the planned 20H mapping (52+48), but must be derived |
| 240-243 | `expected_transitions = 2*(len(rows)-100)`, `expected_direct_endpoints = 200` | numerically still true (924 routes → 1848), must be derived |
| 268 | `layer_model='21 heights (...)'` written into `fanout_selected.json` | wrong metadata |
| 755-757 | log `.../52`, `.../48` | cosmetic |
| 810-814 | `layer_model='21 routing heights = ...'` written into `routes_l3d.json` | wrong metadata |
| 1222-1229 | endpoint table (no 21 literal) | OK |

---

## 4. `validate21.py` — every hardcoded 21-height expectation

Frozen file: 3058 lines, sha `6d4f43a063030c9a`. Entry `main()` **3013-3054**;
orchestrator `validate()` **2400-2966**. It loads the model from
`RUN_DIR/layer_planes.json` but **validates it against a frozen in-file SPEC
table**, so the table itself is configuration that must be re-authored.

### 4.1 The 21-specific literals with line numbers

| # | location | hardcoded expectation | 20H configuration value |
|---|---|---|---|
| 1 | `RUN_DIR_21H` **76**; defaults **2407-2408**, **3016-3018**, **3039** | `outputs/.../FANOUT_FIRST_21_HEIGHT_REBALANCED_1024` | new 20H RUN_DIR |
| 2 | `SPEC_BODY_HEIGHTS` **83-88** | 19 body planes at `-0.35 ... 0.65` incl. `(19,0.65)` | 18 entries `(2..18,20)` at `+0.025` |
| 3 | `SPEC_INTERFACE_PLANES` **89-94** | 1001 z=0.0 / 1002 z=0.5, `level=common.Z1/Z2_INTERFACE_MM` (91,93) | 1001 z=+0.025 / 1002 z=+0.525; `level` from the model, not `common` |
| 4 | `SPEC_MANUAL_FIXED` **96-99** | `Z1-U1..U4→2/3/4/5`, `Z2-U1..U4→10/11/12/13` | unchanged (ids fixed) |
| 5 | `SPEC_EXPECTED_ASSIGNED` **101-107** | 21 per-plane counts | **20 entries from the real 20H assignment** (never relaxed) |
| 6 | `SPEC_DIRECT_TOTAL` **108** | 100 | direct routes of the real 20H assignment (planned: 100 = 52+48) |
| 7 | `SPEC_DIRECT_BY_PLANE` **109** | `{1001:52, 1002:48}` | from the real 20H assignment (planned: same 52/48) |
| 8 | `BASELINE_REGRESSION` **111-119** | 18L numbers (routed 1024, transitions 2048, crossings 18108, L6 5610 / L7 5284, min clearance 0.149965866, length 156893.005) | **must stay bit-identical** (18L regression only, `--baseline-model`) |
| 9 | `check_model` **429-508**: `expected_plane_count=(18 if baseline else 21)` **434**, `plane_count != 21` **449-451**, `body_plane_count != 19` **452-454**, `interface_plane_count != 2` **455-457** (keep 2), SPEC z compare **458-489**, unknown ids **486-489**, distinct heights **496-501**, min pitch **490-495** | 21/19/2 | **20/18/2** |
| 10 | `build_model_stack` **420-426** (`build_stack('reheight21_body_stack', heights=...)`, note "21-routing-height") | builds l3d stack | 20H stack (interface rows + non-contiguous ids — §9.1) |
| 11 | `_spec_model` **312-324** / `load_layer_planes` **331-380** + fallback **2438-2444** | SPEC fallback table | same 20H SPEC table |
| 12 | `interface_z` **264-265**, `interface_plane_id` **268-269** | `common.INTERFACE_Z` (0.0/0.5), 1001/1002 | 20H interface z (+0.025/+0.525) — must come from the model (or `common` must be re-pointed) |
| 13 | `check_direct_route` **795-935**: `expected_z = interface_z(plane)` **802-803**; part z **821-824**; layer_id **816-820**; n_transitions 0 **873-876**; z_span 0 **879-884**; `start_z/end_z` **885-895**; `target_plane` **896-900** | interface z 0/0.5, plane 1001/1002 | 20H interface z; same plane ids |
| 14 | `check_crossings` **1683-1851**: unknown-height violation text "not in the 21-height model" **1733-1736**; per-plane row **1798-1819** | every flat height must be a model plane | 20 planes; text update |
| 15 | `check_assignment` **1871-2128**: rows == 1024 **1885-1887** (keep), `len(plane_counts) != 21` **2034-2036**, `SPEC_EXPECTED_ASSIGNED` **2037-2043**, `SPEC_DIRECT_TOTAL` **2044-2047**, `SPEC_DIRECT_BY_PLANE` **2048-2053**, manual counts 64/64/64/64/16/16/40/40 **2054-2060** (keep), direction rule **1969-1984**, interface z checks **1943-1968**, C4 orbit single plane **1999-2032** | 21 planes / 100 direct / 52-48 split | **20 planes**; counts/direct from the real 20H assignment; manual + orbit rules stay |
| 16 | `run_consistency_tests` **2226-2336**: 50 µm accept / 49 µm reject (**2251-2271**), `model_min_pitch_is_50um` **2272-2276**, `build_stack('consistency_21h', ...)` **2281** and `'consistency_21h_bad'` **2295**, D56 50/49 µm **2300-2314**, port poses **2315-2329** | geometry tests | **keep bit-identical**, but the stack-build tests need the 20H-capable `build_stack` (§9.1) |
| 17 | contract block **2680-2746**: transitions == 2×non-direct **2681-2684** (keep), direct count **2685-2697**, expected transitions 2×(1024−direct) **2698-2706**, direct-by-plane **2707-2715**, `audited != 21` **2718-2723**, missing model planes **2724-2727**, interface rows != 2 **2728-2734** (keep), direct bodies merged **2736-2742** (keep), `model plane_count != 21` **2743-2746** | 21 audited heights | **20**; all other rules unchanged |
| 18 | totals block **2884-2885** | `expected_transitions = 2*(1024-expected_direct) else 2048` | 1848 for 20H (same arithmetic), 2048 only for `--baseline-model` |
| 19 | summary/description strings **2-50, 973, 1122, 1684, 2277, 2707, 2973-2975, 3007, 3015** | "21-height" wording | cosmetic, but must be updated for an honest report |
| 20 | CLI `--expect-direct` / `--expect-transitions` **3033-3034** | optional overrides | unchanged mechanism |

### 4.2 Geometry / threshold checks — must stay bit-identical

These are deliberately not configuration and must not be touched (frozen
`validate21.py:121-144`): `TOL_POS_MM=1e-6` 122, `TOL_Z_MM=1e-6` 123,
`TOL_RADIUS_MM=1e-6` 124, `TOL_LEN_FIELD_MM=1e-4` 125, `TOL_TANGENT=1e-6` 126,
`TOL_GLASS_MM=1e-6` 127, `TOL_PLANE_GAP_MM=1e-9` 128, `R15_MM=15.0` 129,
`MIN_R15_SAMPLED_MM=R15-1e-6` 130, `GLASS_XY_MM=150.0` 131,
`GLASS_Z_MIN_MM=-0.35` 132, `GLASS_Z_MAX_MM=0.65` 133,
`WAVEGUIDE_HALF_WIDTH_MM=common.WIDTH_MM/2` 134, `MIN_3D_CLEARANCE_MM=0.05` 135,
`MIN_LAYER_PITCH_MM=0.05` 136, `D56_CLEARANCE_MM=common.CLEARANCE_2D_MM` 137,
`SAGITTA_MM=0.0005` 138, transition/arc/glass sampling steps 140-143,
`CURVATURE_JOIN_MIN_LENGTH_MM` 144. The check implementations that must stay
semantically identical: `_check_primitive_list` 514-601, `_check_flat_part`
611-663, `_check_transition` 666-783, `check_direct_route` 795-935,
`check_non_direct_route` 940-1199, `check_radius` 1219-1294, `check_glass`
1325-1365, `check_true_3d_clearance` 1371-1421, `measure_min_3d_clearance`
1544-1657, `check_crossings` 1683-1851, `check_ports` 2134-2220,
`_plane_pitch_verdict` 2221-2223, `run_consistency_tests` 2226-2336 (50/49 µm,
D56, port pose), and `BASELINE_REGRESSION` 111-119. The 20H model also introduces
new *reported* geometry facts that must be audited, not asserted: every height is
25 µm inside the glass surfaces (lowest L2 `-0.325`, highest L18 `+0.625`), so
min pitch is still 0.05 and the glass margin is positive on both sides (the 21H
model had L2/L19 *on* the surfaces at `-0.35/+0.65`).

---

## 5. `plots21.py`, `report21.py`, `archive21.py`

### 5.1 `plots21.py` (frozen 144146 B)

* Entry: `main()` **3142-3159**, CLI flags `--run-dir` (default
  `OUTPUT_ROOT/FANOUT_FIRST_21_HEIGHT_REBALANCED_1024`, 88-92, 3145),
  `--baseline-dir` 3146, `--out-dir` 3147, `--only NAME...` 3148-3150,
  `--dpi` 3151-3153; orchestrator `generate_plots()` **3040-3139**; figure
  registry `FIGURES` **3009-3018**, aliases **2998-3007**.
* **Figures = 8 groups / 28 PNGs for 21H**: `per_height` produces
  **len(PlaneModel.planes) = 21** images (`figure_per_height` **1807-1874**,
  names `{index:02d}_{label}_z{z:+.3f}.png`, dpi 165, 97), plus 7 comparison
  figures `02_layer_stack_comparison`, `03_z1_other_comparison`,
  `04_crossings_per_plane`, `05_total_crossings`,
  `06_path_length_distribution`, `07_3d_all_routes`,
  `08_interface_direct_zoom`; plus `plots_manifest.json` (schema
  `fanout_first_reheight21_plots_manifest_v1`, 187). The 21H manifest confirms
  28 figures / 0 skipped.
* Inputs (per figure): `layer_planes.json` → planes (`load_planes` **472-502**,
  falls back to `reheight21.model.planes()` then to a hardcoded 21-entry
  `FALLBACK_PLANES` **112-157**); `layerwise_routes/routes.json` and/or
  `routes_l3d.json` → bodies/leads (`load_layerwise_blocks` 747-813,
  `load_routes` 570-590); `assignment_1024.csv` → ports/groups
  (`load_assignment` 611-622); `crossing_stats.json` / `validation.json` →
  crossings (`load_crossing_info` 1377-1421); the **read-only 21H baseline**
  directory (`physical_layer_stack.json`, `routes_l3d.json`, `validation.json`)
  for panels 02-06.
* 20H: per-height count becomes **20** automatically once
  `layer_planes.json`/routes are 20H (the figure loop is model-driven); the
  hardcoded 21 text is cosmetic but should be updated for honest labels (2009,
  2033, 2116, 2173, 2205, 2225, 2293, 2374, 2386, 2490, 2629, 2635) and
  `FALLBACK_PLANES` needs a 20H variant or the JSON/model path must be
  guaranteed. Comparison panels still read the frozen 21H/18L baselines
  read-only.

### 5.2 `report21.py` (frozen 97837 B)

* Entry `main()` **1770-1810**, flags `--run-dir` 1772, `--baseline-dir` 1773,
  `--skip-write` 1774, `--refresh-tests` 1775, `--skip-tests` 1777-1778.
* `MODEL_BODY_HEIGHTS / MODEL_INTERFACE_PLANES / MODEL_MANUAL_FIXED /
  MODEL_EXPECTED_ASSIGNED` come from `validate21.SPEC_*` **54-57**, so report and
  validator share one model table.
* Reads the new RUN_DIR (`load_new_run` **226-313**): `final_stats.json`,
  `final_stats_run_all.json`, `validation.json`, `validator_consistency_tests
  .json`, `crossing_stats.json`, `routes_l3d.json`, `assignment_1024.csv`,
  `layer_planes.json`, `experiment_*`, `plots/plots_manifest.json`,
  `archive_result.json`; plus the frozen 18L baseline (`load_baseline` **314-396**,
  `BASELINE_RUN_DIR = common.RUN_DIR` 48, `BASELINE_EXPECTED` 61-70).
* Writes `report.md`, `comparison.md`, `final_stats.json` (schema
  `reheight21_final_stats_v2`, 911), and with `--refresh-tests` regenerates
  `tests.log` by running the suites (`collect_tests_log` **413-519**:
  tests_data / tests_fanout / tests_layer2d / tests_assign21 / tests_validate21
  + optional tests_plots21 + the 18L baseline regression).
* 20H: the model tables follow `validate21`; the golden numbers are hardcoded 21H
  values (e.g. `golden_numbers` **1060-1070**: heights=21, crossings 11890/9797,
  min clearance 0.100699741, length 157484.192735; baseline 18108/5610/5284) and
  per-height image names/paths are hardcoded 21H (`01_...21_L19_...`, 1326-1327,
  1731-1732); `CAVEATS` 101-118 says "21 个路由高度". These are report
  configuration and must be updated from the real 20H validation, never relaxed.

### 5.3 `archive21.py` (frozen 23387 B)

* Entry `main()` **449-482**, flags `--run-dir` 451, `--clone` 452,
  `--archive-root` 453, `--experiment` 454, `--message` 455, `--dry-run` 456,
  `--no-push` 457, `--force` 458-459, `--skip-patch` 460-461.
* `build_archive()` **157-263**: refuses to overwrite an existing archive
  **163-171** (`--force` only for this experiment); copies the RUN_DIR files +
  a code snapshot (`CODE_REHEIGHT21` **49-52**, `CODE_SHARED` **53-56**) +
  `MANIFEST.json` (schema `reheight21_archive_manifest_v1` 247) + `README.md`;
  `_commit_and_push` **285-325** via `fanout1024/archive.py` GitHub API;
  `verify_remote` **326-354**; `_patch_placeholder` **355-377** replaces
  `<<<GITHUB_COMMIT_URL_21>>>` (44) in the archived report.
* Defaults that **must be re-pointed for 20H**: `NEW_RUN_DIR` **36**,
  `DEFAULT_EXPERIMENT` **41**, `PLACEHOLDER` **43**, `DEFAULT_ARCHIVE_ROOT` 39
  (do not overwrite the frozen `experiments/fanout_first_21_height_rebalanced_1024`),
  `CODE_REHEIGHT21/CODE_SHARED` lists (add the 20H module/package, e.g.
  `coldstart20/*.py`), `REPO` 42 (same remote is fine, new experiment directory).

---

## 6. Historical 21H reproduction commands (evidence)

From `RUN_DIR/run.log` (737 lines), `RUN_DIR/tests.log`, and the module
`__main__`/docstring blocks. Every command was run from the project root
`OpticalWaveguideRouter2D` with the venv interpreter.

Evidence in `run.log`: raw line 3 `21:37:26 [21h] run21 stages=AB max_iters=3`;
line 24 `21:37:46 ... stages=AB`; line 47 `21:38:33 ... stages=CDE
max_iters=3`; line 426 `21:41:52 ... stages=CDE max_iters=2`; line 733
`21:45:29 ... stages=F`; line 45/736 `run21 done in 20.7 s / 126.6 s`. The
`assign21` banner appears at log lines 1, 23 (i.e. `assign21` was run twice,
21:36:21 and 21:37:12). Final accepted line: `21:43:59 [21h] [E] FINAL
routed=1024/1024 failed=0 direct=100 transitions=1848`.

The full historical sequence (the two `assign21` invocations can be collapsed to
one; `run21.stage_a` re-runs `assign21.main()` automatically only when the
assignment file is missing — run21.py:143-146):

```bat
cd "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D"
.venv\Scripts\python.exe -m four_side_1024.fanout1024.reheight21.assign21
.venv\Scripts\python.exe -m four_side_1024.fanout1024.reheight21.run21 --stages AB
.venv\Scripts\python.exe -m four_side_1024.fanout1024.reheight21.run21 --stages CDE --max-iters 3
.venv\Scripts\python.exe -m four_side_1024.fanout1024.reheight21.run21 --stages CDE --max-iters 2
.venv\Scripts\python.exe -m four_side_1024.fanout1024.reheight21.run21 --stages F
.venv\Scripts\python.exe -m four_side_1024.fanout1024.reheight21.validate21
.venv\Scripts\python.exe -m four_side_1024.fanout1024.reheight21.plots21
.venv\Scripts\python.exe -m four_side_1024.fanout1024.reheight21.report21 --refresh-tests
.venv\Scripts\python.exe -m four_side_1024.fanout1024.reheight21.archive21
```

* The first `--stages CDE --max-iters 3` invocation did **not** converge within
  its budget (log line 445: `[E] iteration 1: assembled=728 world_valid=728 ...
  assembly_failures=296`, plus 2 more iterations) → a second invocation with
  `--max-iters 2` was launched (21:41:52) and converged at 21:43:59 (iteration 2:
  `assembled=1024 world_valid=1024 violations=0`). This is the historical
  "iteration budget" evidence: **more than 3 outer iterations may be needed**;
  the E loop is resumable only by restarting the stage (each stage-E run starts
  from a fresh 2D pass, no checkpoint warm start).
* `validate21` / `plots21` were run with defaults (frozen default RUN_DIR_21H).
* `report21 --refresh-tests` regenerated `tests.log` (2026-11-03 22:05) and the
  final `report.md`/`comparison.md`/`final_stats.json` (22:18); `archive21`
  produced `archive_result.json` (22:22).
* Baseline regression command, copied verbatim from `tests.log` (18L, read-only,
  writes to a scratch dir):

```bat
.venv\Scripts\python.exe -m four_side_1024.fanout1024.reheight21.validate21 ^
  --baseline-model ^
  --run-dir "...\outputs\manual_c4_new_connectivity\FANOUT_FIRST_Z2_MANUAL_VERIFIED_1024" ^
  --out-dir "...\scratch\fanout1024_report\reheight21_baseline_final" ^
  --regression-expect-baseline --quiet
```

* Module self-test entry points (docstrings): `assign21` 40-41,
  `tests_assign21.py` 6, `tests_validate21.py` 6-10, `tests_plots21.py` 6,
  `plots21` 35-39, `validate21` 42-47, `report21` 26, `archive21` 13,
  `model.py` 700.

---

## 7. Shared modules: model-aware seams vs the still-live 18-layer authority

### 7.1 `fanout1024/fanout.py` (96249 B, byte-identical to the 21H archive)

Model-aware seams (20H propagates or is trivial to propagate):

* `_target_z_for()` **156-187** — precedence: row `target_z_mm` → supplied
  `stack.z_for_layer()` → `common.layer_z()` fallback (**184**, 18L table); the
  docstring explicitly says the assignment value wins.
* `candidate_transitions()` **228-319** — `z0` from row `interface_z_mm`
  (**263-264**) else `common.interface_z(plane)`; target z from row/`target_z`
  argument.
* `direct_endpoint_record()` **322-369** — `z0` from row `interface_z_mm`
  (**334-336**).
* `normalize_rows()` **514-607** — carries `target_z_mm`, `interface_z_mm` into
  the planner row (583) and honours explicit `needs_transition` (555-565).
* `plan_fanout(rows, stack=None, fixed=None, repair_ids=None, leads=...)`
  **908-1125** — the world is built by `_make_world(stack, clearance)` (657,
  966); no plane count is assumed; `stack` is the model stack passed by
  `run21` (`M.layer_stack()`).
* `landings()` **1154-1181**, `layer_obstacles(selected, layer_id, layer_z=None)`
  **1245-1277** — explicit `layer_z` supported (1253-1262).
* `write_artifacts()` **1966-2060** — writes `fanout_selected.json` /
  `fanout_validation.json` with schema `fanout_selected_v1` /
  `fanout_validation_v1` (this is what the **on-disk 21H artifacts contain**;
  `run21._fanout_artifacts` writes the `reheight21_*` variants — see §8.2).

Still live 18-layer authority (must be re-pointed or patched for 20H):

| location | code | impact |
|---|---|---|
| `normalize_rows` **528-533** | `z0 = common.interface_z(plane)` (ignores the row's own `interface_z_mm` when `plane` is z1/z2) | **wrong transition start height for 20H** (0.0/0.5 instead of +0.025/+0.525) unless `common.INTERFACE_Z` is globally re-pointed (the in-flight bootstrap does this) |
| `_layer_from_z` **609-616** | scans `common.PHYSICAL_LAYERS` | only used when a row has no `target_layer`; 20H rows always have it, but it is a latent 18L authority |
| `_ensure_record` **388** | `z0 = record.get('z0', common.interface_z(row.get('plane')))` | fallback only; records from `candidate_transitions` carry `z0` |
| `_transition_audit` **1319-1435** | expected z from `expected_z`/stack else `common.layer_z` (**1340**); `z0_at_interface` check against `common.interface_z('z1')/('z2')` (**1415-1416**) | the audit would flag every 20H transition unless `common.INTERFACE_Z` is re-pointed; `run21` does not call `validate_selected`, but tests do |
| `plan_fanout` default | `stack = common.layer_stack()` (945) if no stack | keep passing `M.layer_stack()` |

### 7.2 `fanout1024/layer2d.py` (current tree 88963 B; archived 21H 83671 B)

* `route_layer(layer_id, z_mm, tasks, obstacles=None, budget=600, rr_rounds=2,
  rr_ripmax=3, log, ordering_seed=0, cfg=None, initial_routes=None)`
  **1588-1633** — `z_mm` is explicit; only `None` falls back to
  `C.layer_z(int(layer_id))` (**1624-1625**). `initial_routes` = frozen
  same-layer bodies (strict-D56 blockers) — used by the interface planes and by
  stage-E repair.
* `route_all_layers(layer_tasks, out_dir=None, cfg=None, log, ordering_seed,
  budget, rr_rounds, rr_ripmax, initial_routes=None)` **1677-1768** — consumes
  `{layer_id: {'z_mm', 'tasks', 'obstacles'}}` (1711) and returns
  `{'layers': {layer_id: {routed, failed, stats, z_mm}}, 'stats': {...}}`
  (1749-1762); writes nothing when `out_dir=None`; no plane count assumed.
* `_normalize_layer_tasks` **1636-1658** and `_z_for_layer` **1969-1988** fall
  back to `C.layer_z` and raise for ids outside `common.PHYSICAL_LAYERS`
  (1980-1982) — latent 18L authority; `run21` always supplies explicit `z_mm`.
* `synthesize_landings(rows, ..., plane_z=None)` **1910-1960** uses
  `z0 = C.interface_z(plane)` (**1928**) and `target_z_mm` else `plane_z` else
  `C.layer_z` (**1941-1952**) — a test/experiment helper, not used by `run21`
  (which uses `fanout.landings`), but any 20H experiment code calling it needs
  re-pointed `common.INTERFACE_Z` (bootstrap) or an explicit `plane_z`/row value.
* `footprint_mm` 1900-1907, `_LayerRouter` 1208+, `ObstacleIndex` 1033+ are
  geometry-only (z used as the plane height of the layer being routed) → fine.

### 7.3 `fanout1024/assemble.py` (13258 B, identical to 21H archive)

* `assemble_route(row, source_trans, target_trans, body_primitives)` **128-237**
  — direct branch: `interface_z = C.interface_z(plane)` (**134**), rejects if
  `|target_z - interface_z| > TOL` (148-150); non-direct branch rejects unless
  `|src['z0'] - interface_z| <= TOL` (194-195) and `target_layer/target_z`
  match (190-193). **Therefore 20H requires `C.interface_z('z1'/'z2')` to return
  +0.025/+0.525** (bootstrap re-points `common.INTERFACE_Z`), otherwise every
  route fails assembly. `target_z` itself comes from `row['target_z_mm']` (133,
  model-driven).
* `validate_routes_independent(routes, clearance=0.05, stack=None, log)` **245-279**
  — default stack is `C.layer_stack()` (258) but `run21` passes
  `M.layer_stack()` (run21.py:554).
* `_flat_part` 40-45, `check_route_structure` 240-242 wrap `l3d.world.World`.

### 7.4 `fanout1024/run_all.py` (74942 B) — **the 18-layer baseline driver, not used by 21H/20H**

It hardcodes the baseline stack in seven places: `C.layer_stack()` at **179,
223, 538, 654, 767, 986, 1076**, and `C.physical_layer_stack_payload()` at
**1360**; `main()` 1609-1614 with `--stages/--max-iters/--force-a/--limit`.
It must **not** be reused for the 20H run; `run21.py` is the replacement
(its `run_stages` mirrors run_all's A-E semantics with `M.*`).

### 7.5 `four_side_1024/l3d/layers.py` — the stack gate (critical, §9.1)

Frozen version (13457 B, sha `8add396e6e801d73`): `INTERFACE_ROWS = {'z1': 0.0,
'z2': 0.5}` **32**; `LayerStack.validate()` **101-154** requires
(105-108) routing ids contiguous from L2, (109-110) the layer set == L1 + those
ids, (116-117) the interface rows to be **exactly** `INTERFACE_ROWS`,
(130-134) neighbour plane gaps >= `min_layer_pitch_mm`, (136-141) each routing
plane >= that clearance away from both interface rows; `build_stack()` **216-246**
always uses `dict(INTERFACE_ROWS)` for L1 (235) and sets
`min_layer_pitch_mm = 0.05` when more than 4 routing ids (243).
`l3d/world.py` uses the stack only as an object: `World.__init__` **77-82**
stores it, and `check_route` **220-254** uses real part z / `PlaneWorld` /
`ClearanceWorld3D` (grep: the only stack uses are `self.stack = layer_stack` 78
and a comment at 224). So the world tolerates a nominal/synthetic stack, but
`validate21.build_model_stack` and the payloads do need a buildable stack with
the true 20H values.

Current tree (15773 B): `LayerStack.interface_rows` is now a per-stack field with
`_rows()` (85-115), routing ids need only start at L2/uniqueness instead of being
contiguous (121-140), and `build_stack` accepts `interface_rows=`; every
geometric clearance/pitch check is unchanged (comments at 89-99 state the change
is configuration-only). That is exactly what §9.1 requires; the frozen version
does **not** support the 20H table.

---

## 8. Required 20H call sequence and artifact contracts

### 8.1 Sequence (the 20H equivalent of §6)

```python
# process setup (must happen before any pipeline import)
from four_side_1024.fanout1024.coldstart20 import bootstrap as B
B.install()                      # register model20 as reheight21.model,
                                 # re-point common.INTERFACE_Z + l3d.INTERFACE_ROWS,
                                 # reset the cached stack
B.bind_run_dir(run_dir)          # re-point M.RUN_DIR / NEW_* paths (or default)

# A: assignment  (same functions as the 21H chain, model-driven)
from four_side_1024.fanout1024.reheight21 import assign21, run21
rows = assign21.build_assignment(force=True)      # pure, deterministic
result = assign21.write_all(rows)                 # writes all experiment-A files
# (or assign21.main())

# B..F: driver
run21.run_stages('ABCDE', max_iters=3, log=run21.make_logger(tag='20h'))
#   optional: run21.run_stages('F', ...) -> stage_finalize()
# (or coldstart20.run_initial.main(['--stages','ABCDEF','--max-iters','3']))

# independent validation -> validation.json / validator_consistency_tests.json /
# crossing_stats.json  (requires routes_l3d.json + assignment_1024.csv +
# layer_planes.json)
from four_side_1024.fanout1024.reheight21 import validate21
report, *_ = validate21.validate(run_dir=run_dir)

# figures -> plots/per_height/01..20_*.png + 02..08 + plots_manifest.json
from four_side_1024.fanout1024.reheight21 import plots21
plots21.generate_plots(run_dir=run_dir, baseline_dir=frozen_baseline_dir)

# report -> report.md, comparison.md, final_stats.json, tests.log
from four_side_1024.fanout1024.reheight21 import report21
report21.main(['--run-dir', run_dir, '--refresh-tests'])

# archive -> code snapshot + MANIFEST + GitHub push (new experiment dir!)
from four_side_1024.fanout1024.reheight21 import archive21
archive21.run_archive(run_dir=run_dir, archive_root=new_archive_root,
                      experiment='cold_start_20_height_1024')
```

Ordering constraints: `bootstrap` first (or in-process equivalent) → `assign21`
→ `run21` stages in letter order (B writes `fanout_selected.json` that the C/E
artifacts are derived from; E needs the assignment + transitions) →
`validate21` after `routes_l3d.json` exists → `plots21` after `layer_planes.json
+ routes_l3d.json + layerwise_routes/routes.json + assignment_1024.csv +
crossing_stats.json` → `report21` after validation + plots + `archive_result.json`
(if it is to link the commit) → `archive21` last.

### 8.2 Files needed by downstream stages (frozen schemas)

**`assignment_1024.csv`** — 1024 rows, the 27 columns of
`assign21.ASSIGNMENT_COLUMNS` (**assign21.py:59-67**):
`route_id, plane, relation, manual_group, manual_pattern, layer_role,
target_layer, target_plane_label, target_z_mm, interface_z_mm, direction,
needs_transition, c4_group_id, rotation_phase, baseline_old_layer,
source_endpoint, target_endpoint, source_side, target_side, source_connector,
target_connector, source_x_mm, source_y_mm, target_x_mm, target_y_mm,
source_row, target_row`. Consumers: `run21.read_assignment` (100-138),
`validate21.check_assignment`, `plots21.load_assignment`,
`report21`, `native3d/*`, `xyzrouter/*`. `target_layer` is the `plane_id`
identity (may be 20 for L20, 1001/1002 for the interface planes);
`baseline_old_layer` is the baseline old target layer (`''` for manual) and
`needs_transition`/`direction`/`interface_z_mm` must be the model values.

**`fanout_selected.json`** — produced by `run21._fanout_artifacts`
(**run21.py:266-275**), the in-memory object consumed by C/E:
`{schema: 'reheight21_fanout_selected_v1' (profile schema), layer_model,
route_count, direct_routes, transition_routes, transition_count,
selected: {str(route_id): {'source': record, 'target': record}}}`.
Endpoint records are exactly `fanout.candidate_transitions`
(**fanout.py:292-317**) for transitions
(`route_id, endpoint_role, endpoint_id, candidate_id, lead_mm, start_xy,
start_xyz, direction, z0, z1, target_layer, target_z_mm, target_z, end_xy,
end_xyz, footprint_mm, length_mm, theta_rad, radius_mm, geometry='two_arc_S',
needs_transition, transition, reverse_transition, lead_part`) or
`fanout.direct_endpoint_record` (**322-369**, adds `direct=True, port_xy,
n_transitions=0, lead_part=None, transition=None` and
`start_xy=end_xy=port_xy`, `z0=z1=interface_z`). Consumers:
`fanout.landings` 1154-1181 (`end_xy`/`direction` or direct `port_xy`),
`run21._interface_lead_blockers` 354-373 (`lead_part.primitives`, `lead_part.z_mm`),
`ASM.assemble_route` 180-198 (`start_xy`, `end_xy`, `z0`, `target_layer`,
`target_z_mm`, `footprint_mm`, `transition`, `reverse_transition`).
The on-disk 21H run contains the generic `fanout.write_artifacts` variant
(schema `fanout_selected_v1`, keys `clearance_mm/radius_mm/route_count/selected`,
`fanout_validation.json` schema `fanout_validation_v1`); both shapes are readable
by the 21H validator/report and a 20H run must document which one it writes.

**`routes_l3d.json`** — produced by `run21._write_routes_payload`
(**run21.py:808-819**): `{schema: 'reheight21_routes_l3d_v1' (profile schema),
topology: 'MANUAL_C4', algorithm: 'FANOUT_FIRST_THEN_LAYERWISE_2D',
experiment, process_mode: 'corrected_50um', layer_model, route_count: 1024,
routed, failed, layer_stack: M.stack_payload(), process: M.process_rules_payload(),
joint_repair_history, routes: [...]}`. Each route record is the
`ASM.assemble_route` dict (**assemble.py:155-177** direct / **217-236** non-direct:
`route_id, plane, source_endpoint, target_endpoint, source_side, target_side,
relation, manual_group, layer_role, start_z_mm, end_z_mm, source_row,
target_row, target_layer, target_z_mm, target_plane, target_plane_label,
needs_transition, layer_sequence, layer_z_sequence, n_transitions, lifted,
layers_used, length_mm, xy_length_mm, z_span_mm, lead_source_mm, lead_target_mm,
parts`) plus `run21` additions `target_plane, target_plane_label,
needs_transition, direct` (789-795); failed rows get `status='failed'` and the
route-id/plane/endpoint/reason fields (796-807). `parts` are
`flat` parts (`layer_id, z_mm, length_mm, primitives`) and `transition` parts
(`start, end, direction, z0, z1, radius_mm, theta_rad, footprint_mm, length_mm`).
Consumers: `validate21`, `plots21`, `report21`, `native3d/*`, `xyzrouter/*`,
`archive21`.

**Other required artifacts:** `layer_planes.json` (`model.layer_planes_payload`
491-559: `schema, experiment, baseline_run_dir, glass, interfaces,
interface_planes, plane_count, height_count, min_pitch_mm, measured_min_pitch_mm,
min_pitch_check, body_planes, planes[], plane_order, interface_plane_ids,
assigned_total, assigned_by_role, manual_groups, z1_other_plan,
z2_other_old_to_new, min_layer_pitch_mm`); `physical_layer_stack.json`
(`stack_payload` 562-609); `process_rules.json` (`process_rules_payload`
616-663); `assignment_audit.json`; `assignment_diff_vs_baseline.{json,md}`;
`experiment_A/*`; `experiment_B/*`; `experiment_C/summary.json`;
`experiment_D/*`; `experiment_E/*`; `layerwise_endpoints/endpoints.json`;
`layerwise_routes/routes.json` (schema `reheight21_layerwise_routes_v1`,
run21.py:923-932); `final_stats.json` (826-875); `failed_routes.json`;
`checkpoints/*`; `validation.json`; `validator_consistency_tests.json`;
`crossing_stats.json`; `plots/*` + `plots_manifest.json`; `report.md`;
`comparison.md`; `tests.log`; `run.log`; `archive_result.json`.

---

## 9. Empirical blockers and verified findings (probes run during this audit)

### 9.1 The frozen `l3d` stack **cannot** represent the 20H table (hard blocker)

Probe (import + `build_stack`, no writes): a 20H table
`{2:-0.325, 3:-0.275, ..., 20:-0.025, 8:0.075, ..., 18:0.625}` (18 body ids
`2..18, 20`, all +0.025 from the 21H values, L19 deleted) fails twice on the
frozen `l3d/layers.py`:

1. *interface-row clearance*: `L20 = -0.025` is only **0.025 mm** from the frozen
   interface row `z1 = 0.0` (and `L16 = +0.475` is 0.025 mm from `z2 = 0.5`) —
   `validate()` 136-141 raises `ValueError: L20=-0.025 is closer than clearance
   to interface row z1=0`. The 21H table was exactly 0.05 mm away (`L20=-0.05`,
   `L16=0.45`), which is why the +0.025 shift is geometrically fatal for the
   frozen interface rows.
2. *non-contiguous routing ids*: the 20H id set `{2..18, 20}` is not
   `tuple(range(2, 21))`, so `validate()` 105-108 would raise
   "routing layer ids must be contiguous from L2" once (1) is fixed.

A synthetic probe shows a **shifted-frame, relabeled** stack (`2..19`, heights
`model_z - 0.025`) builds fine, and the same table relabeled `2..19` in the real
frame still fails (1). The current in-flight `layers.py` already adds the two
required configuration seams (`interface_rows` per stack, contiguous-ids check
relaxed) while keeping every geometric rule. **Any 20H rebuild must either
support interface rows ≠ {0.0, 0.5} and non-contiguous routing ids, or build a
nominal stack whose heights are not used by the collision world** (the world uses
the real route z, §7.5) — but the payloads/validator still need true values, so
patching the two seams is the correct fix. This is the single most important
adaptation point.

### 9.2 The 20H assignment is producible and deterministic (verified)

Running the in-flight 20H profile in memory
(`coldstart20.bootstrap` + `assign21.build_assignment(force=True)`, **no file
writes**):

* profile `20_height_raised`, 20 planes, 18 body planes;
  `INTERFACE_Z = {'z1': 0.025, 'z2': 0.525}`, min pitch
  `0.04999999999999993` (passes `>= 0.05 - 1e-9`), stack routing ids
  `(2,3,...,18,20)`, stack interface rows `{'z1':0.025,'z2':0.525}`;
* 1024 rows, two consecutive builds identical (**deterministic**);
* direct 100 (z1 52 + z2 48), 924 transition routes → **1848** endpoint
  transitions; 20 planes used / 20 distinct heights;
* per-plane counts:
  `{2:64, 3:64, 4:64, 5:64, 6:52, 7:52, 20:52, 1001:52, 8:48, 9:56, 10:16,
  11:16, 12:40, 13:40, 14:56, 15:56, 16:56, 17:64, 18:64, 1002:48}` (sum 1024);
* the Z2-other plan consumes whole orbits but mixes baseline old layers per
  plane (probe: plane 9 = old L16 52 + L17 4 routes; plane 14 = L17 48 + L15 8;
  plane 15 = L15 44 + L18 12; plane 16 = L14 16 + L18 40; plane 17 = L14 32 +
  L19 32; plane 18 = L9 48 + L19 16; plane 1002 = L8 48). Old-layer totals stay
  `8:48, 9:48, 14:48, 15:52, 16:52, 17:52, 18:52, 19:48`.
  **These counts must come from the real, frozen 20H assignment** in the final
  audit/report — do not copy them into `validate21` by hand without re-deriving.

### 9.3 In-flight patch status in the live tree (timestamped 22:33–22:38)

The live tree has been patched to read the profile contract
(`assign21.EXPECTED_* = M.CONTRACT_*` at current `assign21.py:74-86`,
`run21.stage_a` uses `M.CONTRACT_PLANE_COUNTS`/`M.CONTRACT_DIRECT_ROUTES`,
`validate21.SPEC_* = M.SPEC_*` at current `validate21.py:88-96`). At 22:35 these
unguarded 21H-map call sites still crashed for the 20H profile
(`M.Z2_OTHER_OLD_TO_NEW is None`): `assign21.build_audit` (`z2_by_plane`
comprehension and `z2_other.old_to_new`), `assign21.build_diff` (`z2_mapping`
loop) and `assign21._experiment_a` (`baseline_diff.z2_old_to_new`) — verified by
`AttributeError: 'NoneType' object has no attribute 'items'`. **That was fixed at
22:38** (`assign21.py` grew to 73,001 B); re-running the in-memory probe now
gives:

* `build_assignment` → 1024 deterministic rows (unchanged);
* `build_audit` → **all invariants passed** (`all_invariants_passed=True`);
* `build_diff` → OK, summary `{routes: 1024, changed_plane: 560,
  unchanged_plane: 464, changed_z: 1024, direction_flip_routes: 332,
  direct_routes: 100, manual_unchanged: True}`;
* the audit now reports the mixed old→new relation in the
  `{old_layer: {new_plane: routes}}` form, e.g.
  `8:{1002:48}, 9:{18:48}, 14:{16:16,17:32}, 15:{14:8,15:44}, 16:{9:52},
  17:{9:4,14:48}, 18:{15:12,16:40}, 19:{17:32,18:16}` and
  `z2 routes_per_new_plane = {9:56, 14:56, 15:56, 16:56, 17:64, 18:64,
  1002:48}` (exactly the 20H plan capacities × 4).

Remaining 21-specific items observed in the live tree (configuration/metadata,
no rule relaxation): `run21.py:240-243` (`2*(len(rows)-100)`, 200 — numerically
coincident for the planned 20H mapping but should be derived), `run21.py:266`
and `:812` (`layer_model='21 ...'` written into payloads),
`assign21.py:1208` (`audit['height_count'] == 21`) and the 21H wording in
docstrings/notes. `report21.py`/`plots21.py` remain the frozen 21H modules and,
as standalone CLIs, import the real 21H `reheight21.model`; a 20H run must either
install the profile before importing them (as `coldstart20.run_initial` does) or
make them read the model exclusively from the 20H `layer_planes.json` /
validation artifacts (§5).

`report21.py` and `plots21.py` are still the frozen 21H modules; run as
standalone CLIs they import the **real** `reheight21.model` (21H), so a 20H run
must either pass the new tables in-process (import `coldstart20.bootstrap` before
importing them) or have them read everything from the 20H `layer_planes.json` /
validation artifacts. `plots21.load_planes` prefers `layer_planes.json`
(the 20H file is enough for the plane model), but `report21.MODEL_*` follows
`validate21.SPEC_*` and the image names/golden numbers are hardcoded 21H.

---

## 10. Downstream packages that consume `reheight21` (do not break them)

`reheight21.model` is imported by `nonc4/*`, `native3d/*`, `xyzrouter/*` (and
`xyzrouter/g4/*`). Verified import sites and the API names used (alias → usage):

| module | import | API used |
|---|---|---|
| `nonc4/paths.py` | `from ..reheight21 import model as M` | **rebinds** `RUN_DIR, NEW_RUN_DIR, NEW_ASSIGNMENT, NEW_ASSIGNMENT_AUDIT, NEW_ASSIGNMENT_DIFF_JSON/MD, LAYER_PLANES_JSON, NEW_STACK_JSON, NEW_RULES_JSON, NEW_EXPERIMENT_A` (48-57) — the established path-rebinding precedent |
| `nonc4/assign_nc.py` | `M` | `GLASS_Z_MIN/MAX_MM, MIN_LAYER_PITCH_MM, PLANE_IDS, plane_label, plane_z, is_interface_plane, layer_planes_payload, process_rules_payload, stack_payload` |
| `nonc4/data.py` | `M` + `run21` | `MANUAL_PLANE_IDS, PLANE_IDS, plane_label, plane_z`; `run21.read_assignment` (79, 84) |
| `nonc4/crossings.py` | `M` | `PLANE_IDS, plane_kind, plane_label, plane_z`; imports `validate21.check_crossings` semantics |
| `nonc4/run_nc.py` | `M` + `run21` | `PLANE_IDS, plane_kind, plane_label, plane_z, layer_stack, process_rules_payload, stack_payload, RUN_DIR`; `run21.read_assignment, _body_lookup, _fanout_artifacts, _fanout_failures, _interface_lead_blockers, _normalize_layer_result, _reconcile_layer_failures, _replan_leads, _task_from_pose, _world_check, _LEAD_PAIRS, validate_fanout_selected, _refresh_fanout_for_repairs` |
| `nonc4/search.py`, `nonc4/final_report.py` | `M` | `MANUAL_GROUPS`/`plane_label`/model payloads |
| `nonc4/validate_nc.py` | `validate21 as V` | `V.validate, V.check_assignment, V.SPEC_EXPECTED_ASSIGNED, V.SPEC_DIRECT_TOTAL, V.SPEC_DIRECT_BY_PLANE` |
| `native3d/common.py`, `single_route.py`, `guard.py`, `run_a.py`, `joint_reroute.py`, `excursion2.py`, `transition.py`, `route_model.py` | `M` | `PLANE_IDS, plane_z, layer_stack, plane_label`, "is one of the 21 heights" assertions |
| `native3d/validate_native3d.py` | `M` + `V21` | `Z1_INTERFACE_MM, Z2_INTERFACE_MM, planes(), SPEC_INTERFACE_PLANES`; `V21.load_layer_planes, check_model, check_crossings, check_glass, check_radius, check_ports, check_true_3d_clearance, build_model_stack, build_true_routes, load_payload, split_records, plane_pitch_audit, measure_min_3d_clearance, _check_flat_part, _check_transition, _finite_xy, _parse_float, _parse_int, _part_flat_z, _read_csv, _round, _sha256, _write_json, failure_reason, INTERFACE_LEGACY_LAYER_ID, GLASS_XY_MM, GLASS_Z_MIN/MAX_MM, WAVEGUIDE_HALF_WIDTH_MM` |
| `native3d/visualize.py` | `model as H` | `interface_z, plane_kind` |
| `xyzrouter/experiment.py`, `optimizer.py`, `local_reroute.py`, `route_builder.py`, `world_adapter.py`, `run_g1.py`, `report.py`, `visualize.py` | `M` | `body_plane_ids, interface_z, is_interface_plane, layer_stack, PLANE_IDS, PLANE_LAYER_ROLE, MANUAL_GROUPS, MANUAL_LAYER_TO_GROUP, plane_kind, plane_label, plane_z, planes()` |
| `xyzrouter/g4/*` (`artifacts, contract_audit, group_replan, arm_base, joint_world, metrics_collect, plots_g4, independent_metrics, c0_continue`) | `M` | same core names; **`g4/contract_audit.py:95-101` source-greps `reheight21/model.py` for the literal lines `^BODY_PLANES = `, `^INTERFACE_PLANES = `, `^MIN_3D_CLEARANCE_MM\s*=`, `^MIN_LAYER_PITCH_MM\s*=`** and `validate21.py` for `World(stack, clearance=MIN_3D_CLEARANCE_MM)`, `def measure_min_3d_clearance`, `def check_crossings` — a 20H rebuild that keeps these files must keep those exact source patterns, or update the audit list |
| `xyzrouter/tests_validate_xyz.py` | `M` + `validate21 as V21` | `V21.load_payload` etc. |

Consequence: a 20H model module registered under the same key keeps all of these
working (the in-flight `coldstart20.bootstrap` does exactly that), but the same
contract thresholds used by the g4 audits must remain in the source files.

---

## 11. Recommended acceptance checklist for the 20H run

1. `l3d.layers.build_stack` accepts interface rows +0.025/+0.525 and the id set
   `{2..18,20}`; min pitch still exactly 0.05; a 49 µm pair still rejected.
2. `assign21` produces 1024 deterministic rows; every plane has assigned > 0;
   whole C4 orbits on one plane (164 non-manual orbits); manual membership and
   plane ids unchanged; per-plane counts equal the 20H contract **read back from
   the produced assignment** (not hand-typed); diff vs the frozen 18L baseline
   works with the plan form of the Z2 mapping.
3. `run21 --stages AB` → `fanout_selected.json` with 1848 transition endpoints +
   100 direct records, all passing the fresh 0.05 mm world check.
4. `run21 --stages CDE --max-iters …` until `routed=1024/1024`, `violations=0`;
   if not converged, record the real failed ids/reasons (never relax rules).
5. `validate21` on the new RUN_DIR: model check 20/18/2, per-plane counts,
   100 direct (52+48), 1848 transitions, crossings audited on **20** heights,
   interface planes merged with leads+direct bodies, glass/R15/clearance/D56 all
   pass; `validator_consistency_tests.json` all passed.
6. `plots21`: exactly **20** per-height images + 7 comparison figures + manifest;
   the frozen 21H/18L baselines only read.
7. `report21`: report/comparison/final_stats/tests.log use the 20H model and the
   real 20H numbers; no 21H "golden numbers" leak in.
8. `archive21`: new archive dir/experiment name; the frozen
   `experiments/fanout_first_21_height_rebalanced_1024` and all `outputs/*` 21H
   artifacts untouched (sha256 recorded before/after, as `assign21` already does
   for the 18L baseline).
