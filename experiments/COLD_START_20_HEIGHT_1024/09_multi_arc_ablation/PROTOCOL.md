# PROTOCOL — 20-height strict planar multi-arc ON/OFF ablation (1024 routes)

> **Status: PRE-REGISTERED before any formal run.** This file is written before
> the 20H common start exists and must not be edited after the first formal arm
> run starts. Any change requires a `V2` file and an explanation in the report.
> The SHA256 of this file is recorded in `START.json` when the common start is
> verified, so a silent post-hoc edit is detectable.

This is the plain-Python, bootstrap-first port of the strict FINAL design of
`experiments/G4_MULTI_ARC_ABLATION_FINAL_1024` (read-only evidence) to the
20-height physical model installed by
`four_side_1024/fanout1024/coldstart20/bootstrap.py`.

Driver: `four_side_1024/fanout1024/coldstart20/run_multiarc.py`
Stage-0 converter: `four_side_1024/fanout1024/coldstart20/convert_multiarc20.py`
Experiment root: `experiments/COLD_START_20_HEIGHT_1024/09_multi_arc_ablation/`

---

## 1. Research question

Under the **same 1024 connections**, the **same geometry constraints**, the
**same feasible start state** and the **same counted candidate-evaluation
budget**, does allowing planar multi-arc combinations (two tangent,
opposite-sweep R15 arcs with no straight line between them) yield
significantly fewer **real same-plane crossings**?

The answer is restricted to the frozen D56 candidate grammar (axis-aligned
lines + R15 quarter arcs + tangent opposite-sweep R15 double-arc S). This
protocol does **not** claim "multi-arc is better than all smooth curves", and
it does **not** translate crossings into optical insertion loss.

---

## 2. Design: one common start, one changed variable

Both arms read the **same converted common start**
(`.../common_start_off/routes_l3d.json`, `multi_arc = 0`, SHA frozen in
`OFF_FEASIBILITY.json`). The **only** algorithm factor that differs is

```
G4_ENABLE_MULTI_ARC = 1   (arm "on")
G4_ENABLE_MULTI_ARC = 0   (arm "off")
```

injected in `four_side_1024/fanout1024/layer2d.py`:

| role | location (verified by `start --dry-run`, see §11) |
|---|---|
| policy definition, **default ON** | `layer2d.py:229` `MULTI_ARC_POLICY = dict(enabled=..., source=...)` (env unset ⇒ `enabled=True`, `source='default:enabled'`) |
| explicit-cfg override helper | `layer2d.py:237` `multi_arc_enabled(cfg=None)` — `cfg['enable_multi_arc']` wins over the env |
| read once by the router | `layer2d.py:1215` `self.enable_multi_arc = ...` in `_LayerRouter.__init__` |
| injection point | `layer2d.py:1299` `_LayerRouter._iter_candidates`: (1) drop `('S', shift)` candidate specs before building, (2) hard geometric gate `local_multi_arc_regions(...) → multi_arc_forbidden` after building |
| propagation to every G4 candidate path | `xyzrouter/local_reroute.py:126` `router_cfg['enable_multi_arc'] = L2.multi_arc_enabled(cfg)` |

Because the policy is read at **import time**, the arm driver sets the env var
before **any** pipeline import and then runs the frozen engine in that process.
This includes a subtle trap that is handled explicitly: importing
`four_side_1024.fanout1024.xyzrouter.paths` executes
`xyzrouter/__init__.py`, which imports `local_reroute`, which imports
`layer2d`. The driver therefore sets `G4_ENABLE_MULTI_ARC` as the first
statement of the `convert` / `arm-*` commands (it is not set for `--dry-run`,
where the default policy must be observable). The switch is height-table
agnostic: no change to it is needed or made for the 20-height model.

Everything else is identical in both arms: 1024 connections and port
identities, 150×150×1 mm glass, the 20 routing heights (18 body + 2
interface; plane id 19 deleted, every surviving height +0.025 mm), R15,
strict-D56 same-layer clearance (0.08 mm centreline; ≥5° legal crossings),
true-3D clearance 0.05 mm, manual-U policy, ALNS, joint make-way, local
candidate evaluation and acceptance, objective function, validator, seed set
and counted budget.

---

## 3. Prerequisites (hard blockers)

1. **20H G3 best_valid** produced by the 20H cold-start chain:
   `experiments/COLD_START_20_HEIGHT_1024/07_g123/run_xyz_joint_1024_20h/best_valid/`
   with `routes_l3d.json` (schema `xyz_joint_g123_routes_v1`, 1024 routed,
   0 failed) and `assignment_1024.csv`. **It does not exist yet**; the whole
   ablation is blocked on the 20H routing chain.
2. **Identity/port/manual authority** for the validator, resolved in this
   order: (a) `XYZ_RUN/baseline_authoritative` (20H; must contain a 20H
   `layer_planes.json`), (b) the 20H stage-03 legal layout
   `03_fanout_and_xy/run_initial_20h` (same 1024 connections/ports, 20H model
   table). The frozen 21H authority is **not** used: its `layer_planes.json`
   would make the validator report 21 heights.
3. The 20-height profile must be installed in **every** process
   (`coldstart20.bootstrap`, executed on import) before any pipeline/validator
   module; `bootstrap.assert_20_height_profile()` fails loudly otherwise.

---

## 4. Common start verification (`start`)

`run_multiarc.py start` writes `START.json` after these checks (each is
recorded in `START.json`); `ok = true` only when every check and the validator
pass. On a failure the problems are recorded in `START.json` (`ok = false`,
non-zero exit) and `convert`/`chain`/`all` refuse to run — the failure is
reported, not hidden.

* profile is the 20-height model: 20 planes (`2..18,20` + interface
  `1001/1002`), plane id 19 absent, interfaces `z1=+0.025`, `z2=+0.525` mm;
* `routes_l3d.json` / `assignment_1024.csv` exist; 1024 routes, routed 1024,
  failed 0; SHA256 of both files recorded;
* every flat height used by the routes is a 20H model height (no deleted
  L19 / no 21H-table remnants); every assignment `target_layer` is a 20H
  model plane, `target_z_mm` equals the model z (1e-9), `interface_z_mm` is
  `{0.025, 0.525}`; manual-route count equals the 20H contract (368);
* the exact strict-D56 crossing total is **recomputed independently**
  (`nonc4.crossings.audit_flat_group` per physical height on a fresh
  `RouteWorld`) and must equal the reported `crossing_stats.json` total;
* the planar multi-arc census is computed (number of regions / routes is a
  property of the 20H start: **never hardcode the 21H value 197**);
* the frozen independent validator runs in a **fresh process with the 20H
  bootstrap installed** (`xyzrouter.validate_xyz`, `manual_policy =
  fully_optimizable`, `baseline_dir` = the 20H authority): it must report
  `validation_pass = true`, `violation_count = 0` and **20 model heights**.

`START.json` also stores: profile payload, start SHA/crossings, multi-arc
census, manual/direct counts, the frozen budget contract (§6), the seed list,
the decision rule (§9), the SHA256 of this file and a source snapshot
(`layer2d.py`, `local_reroute.py`, `alns.py`, `run_g4_engine.py`, `run_g4c.py`,
`bootstrap.py`, `model20.py`, the driver and the converter).

---

## 5. Stage-0 OFF conversion (`convert`, effect **A**)

The inherited ON start may contain planar short-S geometry, which the ablated
grammar cannot express. The converter re-plans **exactly the routes that carry
at least one real local multi-arc region** with the frozen G4 planner:

* `joint_world.JointWorld.plan_candidates(rid, cfg=JW.PLAN_CFG, mode='clean')`
  — the same planner configuration the G4 search uses (3 free target heights,
  2 lead pairs, 160/320 pre-screen, `d56_top=16`, 4 candidates per option);
* choice = **deterministic minimum exact crossing delta, then shortest**
  (no randomness, no wall-clock dependence);
* commit via `joint_world.replace_one`; no hand-edited arcs, no polyline
  replacement, no route deletion;
* a route with no legal candidate keeps its old geometry and is reported as
  **residual** (never silently deleted, never force-replaced);
* a defensive `policy_leak` check rejects any candidate that would still
  contain a local multi-arc region;
* invariants asserted after conversion: all non-target routes are
  byte-identical, 1024 routes preserved, **0 remaining local multi-arc
  regions**, and the fresh-process 20H validator passes
  (`validation_pass = true`, 0 violations, 20 model heights); a converted
  `layer_planes.json` (20H model table) is written next to the state so the
  validator reads the same 20 heights.

Cost separation (mandatory):

| effect | definition | source |
|---|---|---|
| **A** | crossing delta when the inherited ON geometry is re-expressed in the OFF grammar, measured with the frozen crossing audit, plus the per-route conversion table | `common_start_off/conversion_report.json`, `tables/stage0_audit.json`, `tables/stage0_per_route.csv` |
| **B** | ON vs OFF final result from the **same** converted start, same code, same counted budget | `tables/summary_c1.*` |
| **C** | historical 21H mixed-package difference (A + B + budget/start differences) | read-only reference loaded from `experiments/G4_MULTI_ARC_ABLATION_FINAL_1024/tables/summary_c1.json` |

**A and B must never be added into a single "value of multi-arc" number, and
the conversion cost must never be attributed to the search gain.** C is
historical 21H evidence only; it is not a 20H result.

### Pre-registered OFF feasibility rule

The OFF arm is only meaningful if the ablated grammar can represent the whole
start. Therefore:

> If conversion leaves **residual multi-arc routes**, a `policy_leak`, a
> non-zero **multi-arc count after conversion**, or an **illegal route**
> (validator not pass), the strict common start **does not exist** for this
> 20H start. The converter records the failure honestly in
> `conversion_report.json` and `OFF_FEASIBILITY.json` (with reasons) and
> `chain`/`all` **stop without running any arm**. A diluted OFF arm that keeps
> residual ON geometry would silently re-introduce the disabled variable and
> is forbidden.
>
> This is a valid scientific outcome: effect A (conversion cost / residual
> routes) becomes the 20H grammar-feasibility result.

---

## 6. Budgets (counted, not wall-clock)

### 6.1 Primary experiment — equal candidate-evaluation budget

| parameter | frozen value |
|---|---|
| engine arm | `G4c_free` |
| `counted_d56_budget` (`d56_candidate_evals`) | **24000** |
| `counted_checks_guard` (secondary hard cap on `route_3d_checks`) | **9000** |
| wall-clock `--seconds` safety net | **5400** (designed never to trigger; 21H FINAL measured ~1050–1550 s) |
| `counted_sweep_fraction` | **0.18** |
| neighbourhood stage sizes | **8 / 16 / 32 / 64** |
| stage fractions | **0.22 / 0.24 / 0.26 / 0.28** |
| stop rule | `d56_candidate_evals ≥ 24000` **or** `route_3d_checks ≥ 9000` **or** wall ≥ 5400 s |

Counter semantics (frozen code): `d56_candidate_evals` is bumped once per
`xy_candidates()` call by the operator constant `d56_top` (the exact
strict-D56 candidate-evaluation slots); `route_3d_checks` is bumped once per
route geometry that enters the true-3D World check. The primary axis is
`d56_candidate_evals`; `route_3d_checks` is a **secondary guard**, not an
equivalent cost. The two are reported separately. Overshoot of the counted
target is bounded by one operator call; the run is accepted while
`(used − 24000)/24000 ≤ 10 %` (21H FINAL measured ≤ 0.64 %), and the actual
value is reported per run.

### 6.2 Auxiliary experiment — equal wall clock (secondary only)

| parameter | frozen value |
|---|---|
| `--seconds` | **900** |
| counted caps | none (`counted_d56_budget = 0`, engine wall-clock schedule) |
| everything else | identical |

The primary verdict is based on §6.1 only; the auxiliary experiment is an
independent cross-check of the budget definition (in the 21H FINAL both gave
consistent answers).

---

## 7. Seeds (pre-registered)

`20261104`, `20261116`, `20261130` — the **same three seeds for both arms**
(primary and auxiliary). Each seed × arm is one run; all runs are serial on one
machine. 3 repetitions ⇒ **exploratory statistics** (mean, sample std ddof=1,
min/max, median, paired ON−OFF); **no significance test**, no p-values.

---

## 8. Validators and hard gates

Per run, three independent layers must agree:

1. **engine-embedded validator** — the frozen `xyzrouter.validate_xyz`
   (`manual_policy = fully_optimizable`, `baseline_dir` = 20H authority),
   launched in a fresh process. The frozen engine hard-codes a 21H child
   process, so the driver re-binds `g4.artifacts.run_validation` **in its own
   process only** to inject the `coldstart20.bootstrap` preamble (no source
   file is modified) and binds `g4.paths.AUTHORITY_DIR` to the resolved 20H
   authority; the result is recorded in `validation/validation.json`.
2. **fresh-process validator** — the same frozen validator launched again by
   the driver after the arm, into `<run>/validation_final/`, under the 20H
   bootstrap (`run_multiarc.run_validator_xyz`).
3. **independent geometry audit** — this repository re-derives:
   * the exact strict-D56 crossing count per physical height with
     `nonc4.crossings.audit_flat_group` on a fresh `RouteWorld`
     (not the engine's cached statistics), and
   * the planar multi-arc census with the frozen policy helper
     `layer2d.local_multi_arc_regions`.

   Written to `<run>/audit_state.json`. The audit crossing total must equal the
   validator's `same_plane_crossings`, and the audited routes SHA256 must equal
   `best_valid/SHA256.json`.

Hard gates (any failure invalidates the run, even if crossings are lower):

* 1024/1024 routed, 0 failed, route ids / ports / identities unchanged;
* `min_flat_arc_radius_mm ≥ 15.0`;
* `min_transition_sampled_radius_mm ≥ 15.0 − 1e-6`;
* `min_3d_clearance_mm ≥ 0.05` (true 3D centreline);
* `min_non_crossing_centerline_mm ≥ 0.08` (strict D56, legal crossings exempt);
* `violation_count == 0`, `validation_pass == true` (both validator layers);
* **OFF arm:** `multi_arc_regions == 0` by the independent geometric audit;
* validator reports **20 model heights** (a 21H fallback is a hard failure);
* counted budget contract: the frozen target was actually reached and the
  overshoot is within §6.1; a run stopped by the secondary guard or the wall
  safety net is reported as such and cannot support the primary verdict.

---

## 9. Pre-registered decision rule (A / B / C)

Based on the **primary** experiment's 3 paired seeds:

* **A — supports a real advantage of the planar multi-arc freedom**:
  3/3 seeds `ON < OFF`, **and** paired mean gap `ON − OFF ≤ −F`, where
  `F = max(200, round(0.05 × common-start crossings))` (the 21H FINAL used
  `F = 200 ≈ 5 %` of its 3967 start; the 20H start crossings are computed from
  the real 20H start, so the 5 % floor is pre-registered as a formula, not a
  post-hoc number), **and** ON total length growth vs OFF `≤ +5 %`, **and** all
  hard gates pass in all runs.
* **C — not reproduced**: paired mean gap `≥ 0` **or** direction inconsistent
  (any seed with `ON > OFF`).
* **B — insufficient evidence**: everything else (consistent direction but
  effect below the floor, or length cost over the limit, or budget/statistics
  limits).

The verdict must be reported honestly whichever it is. It is forbidden to
presuppose that multi-arc must win.

---

## 10. Artifacts

```
experiments/COLD_START_20_HEIGHT_1024/09_multi_arc_ablation/
├── PROTOCOL.md                    this pre-registered file (sha recorded)
├── START.json                     verified 20H common ON start fingerprint
├── OFF_FEASIBILITY.json           pre-registered feasibility verdict (effect A)
├── ABORTED_OFF_INFEASIBLE.json    only when the OFF start does not exist
├── CHAIN.json                     stage log of a chain/all invocation
├── common_start_off/              Stage-0 converted start (the SAME start of both arms)
│   ├── routes_l3d.json / assignment_1024.csv / SHA256.json
│   ├── layer_planes.json          20H model table used by the validator
│   ├── conversion_report.json     effect A: per-route records, residual, delta
│   └── validation_xyz/validation.json   (and validation21/ diagnostic)
├── runs/{on,off}/<tag>/           one run per arm × seed
│   ├── …                          full frozen G4 artifact set (routes, stats, ledger,
│   │                              strategy_stats, checkpoints, best_valid, validation/)
│   ├── validation_final/validation.json   fresh-process 20H validator
│   ├── audit_state.json           independent crossing + multi-arc audit
│   ├── run_meta.json              arm, seed, env, budget, start SHA, gates
│   └── RUN_VERDICT.json           hard-gate verdict of this run
├── tables/                        runs.{json,csv}, summary_c1.{json,md},
│                                  summary_a1.*, stage0_audit.json,
│                                  stage0_per_route.csv, abc.json, effects.json,
│                                  decision.json
├── validation/summary.{json,md}   independent acceptance summary
├── audit/                         start/runs audit copies
├── logs/                          stage logs (chain/all) and convert.log
└── report.md                      generated analysis report
```

Tags: primary `c1_{on,off}_{seed}`, auxiliary `a1_{on,off}_{seed}`.

Read-only evidence that is **never modified**:
`experiments/G4_MULTI_ARC_ABLATION_1024/`,
`experiments/G4_MULTI_ARC_ABLATION_FINAL_1024/`,
`experiments/G4_MULTI_ARC_COLD_START_1024/`, `1130-report-materials/`.

---

## 11. Commands

All commands are plain Python (no PowerShell). Everything is invoked from the
project root with `.venv\Scripts\python.exe`. **Every subcommand supports
`--dry-run`** — it prints the resolved start dir, the arm dirs, the budget
contract and the verified multi-arc switch location, executes nothing and
writes nothing (the `coldstart20.bootstrap` import may create the empty stage
directories under the experiment root; no artifact is written).

```powershell
$PY  = ".venv\Scripts\python.exe"
$MOD = "four_side_1024.fanout1024.coldstart20.run_multiarc"

# 0) dry-run verification of the whole plan (blocked-prerequisite aware)
& $PY -m $MOD chain --dry-run
& $PY -m $MOD start --dry-run

# 1) verify the 20H G3 common start (writes START.json)
& $PY -m $MOD start

# 2) Stage-0 OFF conversion (effect A) + pre-registered feasibility gate
& $PY -m $MOD convert

# 3) single arms (each starts from the SAME converted common start)
& $PY -m $MOD arm-on  --seed 20261104
& $PY -m $MOD arm-off --seed 20261104
#    … other seeds; or run the whole primary matrix:
& $PY -m $MOD chain          # start -> convert -> 6 primary runs -> analyse
& $PY -m $MOD all            # chain + 6 auxiliary (900 s) runs

# 4) analysis only (independent audits + A/B/C + pre-registered verdict)
& $PY -m $MOD analyse        # add --with-aux for the auxiliary arms
```

Useful options: `--start-dir`, `--baseline-dir`, `--seeds`, `--skip-validator`
(debug only), `--refresh-start`, `--refresh-convert`, `--force`,
`--arm-timeout`, `--convert-timeout`, `--analyse-timeout`.

Exit codes: `0` success; `1` failed gate / failed stage; `2` input or
prerequisite error; `4` **OFF common start infeasible** (pre-registered, no
diluted OFF arm).

---

## 12. Evidence for every frozen number in this file

| item | value used | evidence (read-only) |
|---|---|---|
| single changed variable | `enable_multi_arc` (`G4_ENABLE_MULTI_ARC` 1/0), injection in `layer2d._LayerRouter._iter_candidates` | `00_audit/multiarc.md` §0/§1.1; verified live by `--dry-run` (policy default ON, override helper, constructor read, prefilter + hard gate, `local_reroute.py:126`) |
| `counted_d56_budget` | 24000 | `G4_MULTI_ARC_ABLATION_FINAL_1024/EXPERIMENT_SPEC.md` §6.1; `config/FROZEN_CONFIG.json` → `primary.counted_d56_budget`; `RUNBOOK.md` §4.2 |
| `counted_checks_guard` | 9000 | same (`primary.counted_checks_guard`) |
| wall safety net | 5400 s | same (`primary.wall_safety_net_seconds`) |
| sweep fraction / stages | 0.18; 8/16/32/64; 0.22/0.24/0.26/0.28 | `FROZEN_CONFIG.json` → `primary`; `alns.py` (`counted_sweep_fraction=0.18`) |
| auxiliary | 900 s wall, no counted caps | `EXPERIMENT_SPEC.md` §6.2; `FROZEN_CONFIG.json` → `auxiliary` |
| seeds | 20261104 / 20261116 / 20261130 | `EXPERIMENT_SPEC.md` §6.3; `FROZEN_CONFIG.json` → `seeds` |
| decision rule A/C/B, effect floor 200 ≈ 5 % | §9 above | `EXPERIMENT_SPEC.md` §9; `report.md` §11; `FROZEN_CONFIG.json` → `decision_rule` |
| hard gates | 1024/1024, R15, 3D 0.05, D56 0.08, 0 violations, OFF multi-arc 0 | `EXPERIMENT_SPEC.md` §8 |
| validator policy | `fully_optimizable`, fresh process, model must report 20 heights | `EXPERIMENT_SPEC.md` §8; `00_audit/g4.md` §5.4; `00_audit/multiarc.md` §3.2 |
| three-effect separation A/B/C | never merge | `00_audit/multiarc.md` §1.2; `G4_MULTI_ARC_ABLATION_FINAL_1024/report.md` §7.1 |
| pre-registered OFF feasibility | residual ⇒ no diluted OFF arm | `00_audit/multiarc.md` §3.3 |
| 20H model | 20 planes, id 19 removed, +0.025 mm | `coldstart20/model20.py`; `bootstrap.assert_20_height_profile` |
| common start | 20H G3 `best_valid` (recomputed multi-arc count; 197 not assumed) | `paths20.py`; `00_audit/multiarc.md` §3.1/§3.3 |

The historical 21H FINAL numbers (common start 3967; ON 2203 / OFF 3601;
paired −1398; effect A +2645) are **not** transferred into any 20H claim; they
are loaded at analysis time as the read-only effect-C reference.

---

## 13. What is still blocked (dry-run status)

* The **20H G3 `best_valid` does not exist yet** — `start`/`convert`/`chain`/
  `all` report `exists=False` for
  `07_g123/run_xyz_joint_1024_20h/best_valid` and `start` stops with
  `returncode 2`. This is the single blocking prerequisite.
* When the 20H G3 output exists: run `start` (writes `START.json`), `convert`
  (effect A + feasibility), then `chain` (primary 6 runs) and optionally
  `all` (auxiliary 6 runs), then `analyse`.
* Expected cost: 6 primary runs × ~20–30 min (21H FINAL reference
  ~1049–1537 s of search each) + conversion + validation; the auxiliary adds
  6 × 900 s. All runs serial.
