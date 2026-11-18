# 20-height cold-start rebuild of the 1024-channel 3D optical waveguide router

**Experiment:** `COLD_START_20_HEIGHT_1024`
**Model:** `four_side_1024/fanout1024/coldstart20/model20.py` (profile `20_height_raised`)
**Date:** 2026-11-17 / 2026-11-18
**Status:** complete chain, 1024/1024 legal layout, independent validator PASS at every accepted state

---

## 0. Answer to the question the report must answer

> **Can 20 heights -- keeping R15 = 15 mm, the 50 µm layer pitch and all 1024
> connections -- reach a crossing level close to or better than the original
> 21-height result by re-annealing, multi-arc planar routing, Native-3D
> mid-path layer changes and G4 global joint optimisation?**

**Result: close at the global-optimisation end, but not better; and not close at
the re-annealing end.**

| stage | 21H reference (frozen, read-only) | **20H (this experiment)** | difference |
|---|---:|---:|---:|
| initial fanout-first baseline | 11890 | **12338** | +448 (+3.8 %) |
| after from-scratch annealing + joint repair (E5 analog) | 2606 | **3275** | +669 (+25.7 %) |
| after Native-3D Phase 1 (A/B/C) | 2440 | **3103** | +663 (+27.2 %) |
| after Native-3D Phase 2 (D/E/F) | 2409 | **3061** | +652 (+27.1 %) |
| after G1 → G2a → G2b → G3 | 1322 | **1395** | +73 (+5.5 %) |
| after G4 global ALNS | 1185 | **1283** | +98 (+8.3 %) |

The 20-height table loses one body plane and gains no extra freedom, and the loss
is concentrated exactly where the frozen 21-height chain was strongest: the
combinatorial layer-assignment stage (E5: +25.7 %).  The global joint XYZ
optimisation stages then recover most of it: at G3 the gap falls to +5.5 %, and
the best 20-height legal solution (G4 progressive chain link 4, 1283 crossings)
is **+8.3 %** above the 21-height G4 best (1185).  The 21-height 1185 itself was
not single-digit, and the 20-height best is the same order of magnitude -- but it
is **not** better and **not** single-digit, and this report does not claim
otherwise.  All numbers are measured on independently validated layouts.

---

## 1. What changed physically -- the 20-height configuration

The only geometric input changed is the routing-height table (`01_height_config/`):

* plane identity **L19 (id 19, old z = +0.650 mm) is deleted**;
* every surviving height is **raised by +0.025 mm**;
* plane ids are kept as **identity labels** (`L20` = id 20 keeps z = -0.025 mm,
  which is *not* above L18 — physical order is always taken from z, never from id);
* the two interface planes (routable 2D body planes) move with the ports:
  **Z1_INTERFACE = +0.025 mm, Z2_INTERFACE = +0.525 mm**; the authoritative
  `fslw` port model is re-pointed in the same way, so the 0.5 mm MPO row spacing
  is preserved exactly and every route still starts/ends *on* its physical port;
* result: **18 body planes + 2 interface planes = 20 routing heights**, exactly
  50.000 µm neighbour pitch, 25.0 µm headroom to both glass faces, glass
  envelope unchanged at z ∈ [-0.350, +0.650] mm.

**Nothing was relaxed.**  R15 = 15 mm, the strict same-layer D56 rule
(0.05 mm width + 0.03 mm edge gap, legal transverse crossings preserved), the
0.05 mm true-3D centre-line clearance, the 150 × 150 × 1 mm glass, the 1024
fixed connections and the 368 manual-U route identities are bit-identical to the
frozen 21-height model.  The 20-height change is *geometry configuration*; there
is **no** validation-standard relaxation (see §8 and `00_audit/adaptation_log.md`).

The deleted plane's routes are not dropped: the 1024 connections are immutable
and every route is re-assigned from the authoritative connection data
(`assignment_diff_vs_baseline.md`), so the former L19 routes simply receive a new
25-µm-shifted height from the 20-height table.

## 2. How the 21-height chain was reused (no simplified router)

The existing production chain was reused **in full**, driven through a single
profile switch (`coldstart20/bootstrap.py` registers `model20` as
`reheight21.model` and re-points `common.INTERFACE_Z`,
`fslw.config.PLANE_Z_MM` and the `l3d` interface rows before any pipeline module
is imported).  The chain is:

```
assign21/run21 (A-F)  ->  nonc4 (E0/screen/E1/E3/E5)  ->  native3d A/B/C
   -> native3d D/E/F  ->  xyzrouter G1 -> G2a -> G2b -> G3  ->  g4 arms + chain
```

with the real function-level map in `00_audit/pipeline_map.md`.  The 368 manual-U
routes are frozen through stages 03/04/05/06/G1, height-only at G2a/G2b, and
unfrozen at G3/G4c-free/G4d — exactly the frozen stage policy.  No historical
21-height route geometry was copied into the 20-height cold start: the manual-U
geometry is regenerated from the authoritative connectivity at the new heights
(vector-z shift only, XY identical by symmetry of the manual template).

## 3. Stage-by-stage results (all independently validated)

### 3.1 From-scratch layer assignment + simulated annealing (stages 02 / 04)

The deterministic cold assignment (whole C4 orbits, 368 manual fixed, 100 direct,
924 transition routes → 1848 endpoint transitions) was annealed from scratch with
`nonc4.assign_opt`: simulated annealing on the **exact chord-crossing graph**
measures a `k → min intra crossings` cost curve per direction family, then a
small integer programme decides how many heights each family receives
(Z1V/Z1H never share; the opposite-corner Z2 pairs (NE,SW)/(SE,NW) have zero
crossing chords and may share).  For 12 non-manual heights the programme chose
**2 / 3 / 3 / 4** (predicted cost 746) but that "compatible-corner sharing"
allocation is the one the 21-height campaign already measured as unrealisable by
an axis-aligned R15 router, so the **family-pure** allocation (each family on its
own heights: Z1V 2, Z1H 3, Z2 2/2/1/2) was also run -- and it is what performed.

| experiment | allocation style | seed | routed | failed | crossings |
|---|---|---|---:|---:|---:|
| E1_family_pure | family-pure, deterministic | – | 1024 | 0 | 6803 |
| E2_conflict_sharing_seed11 | chord-optimal sharing | 11 | 1021 | 3 | 9372 (negative result, reproduces the 21H finding) |
| E3_family_pure_sa_seed11 | family-pure + SA partition | 11 | **1024** | **0** | **3275 (accepted E5)** |
| E3_family_pure_sa_seed23 | family-pure + SA partition | 23 | 1022 | 2 | 3353 |
| E3_family_pure_sa_seed37 | family-pure + SA partition | 37 | 1023 | 1 | 3346 |
| E3_family_pure_sa_seed51 | family-pure + SA partition | 51 | 1024 | 0 | 3500 |

The accepted E5-analog legal solution (E3 seed 11) is 1024/1024 with 0 failures
and independent-validator PASS; it is frozen read-only under
`04_initial_3d_and_e5_repair/nonc4_programme/E5_joint_repair_final/`.
Annealing evidence (cost curves, seeds, per-family conflict counts, per-height
counts, convergence) is in `02_annealing/`.

### 3.2 Complete stage curve

See `12_reports/final_metrics.md` for the machine-collected full table (routed,
crossings, crossing pairs, max/P95/mean per-route crossings, min 3D clearance,
min radius, transitions, planar multi-arc routes, total length, validator
status, per-stage delta) and `11_figures/final/06_crossing_curve_vs_stage.png`.
Headline numbers:

| stage | crossings | crossing pairs | max/route | P95 | mean/route | min 3D (mm) | min R (mm) | transitions | multi-arc routes | validator |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 03 cold start (fanout + D56 multi-arc + 3D) | 12338 | 10133 | 83 | 68.0 | 38.56 | 0.0865 | 15.0 | 1848 | 646 | PASS |
| 04 annealing + E5 repair | 3275 | 2774 | 49 | 28.0 | 11.20 | 0.1063 | 15.0 | 1866 | 592 | PASS |
| 05 Native 3D Phase 1 (A/B/C) | 3103 | 2733 | 49 | 27.0 | 10.57 | 0.0686 | 15.0 | 1998 | 592 | PASS |
| 06 Native 3D Phase 2 (D/E/F) | 3061 | 2705 | 49 | 26.6 | 10.38 | 0.0686 | 15.0 | 2022 | 592 | PASS |
| 07 G1 → G2a → G2b → G3 | 1395 | 1325 | 20 | 11.0 | 4.33 | 0.0622 | 15.0 | 1952 | 652 | PASS |
| 08 G4c-free (best independent arm) | 1322 | 1255 | 18 | 10.0 | 4.07 | 0.0622 | 15.0 | 1950 | 654 | PASS |
| 08 G4 progressive chain link 4 (**final best**) | **1283** | 1221 | 17 | 9.0 | 3.97 | 0.0622 | 15.0 | 1950 | 658 | PASS |

### 3.3 Native 3D Phase 1 (A/B/C)

A0 geometry unit tests 11/11 PASS (mid-body R15 double-arc S-curve construction,
49 µm off-height rejected, R14 rejected, discontinuity rejected, overlap
rejected).  A1 scanned the 12 highest-crossing movable routes: the 20-height
layout's top routes all carry a **corner arc inside their crossing cluster**,
so the straight-run legal-window generator yields no feasible single excursion
(0/12) — an honest geometric property of this layout, not a rule relaxation.
B (batch avoidance, 4 strategies) applied 10 excursions net −35; C (global
optimisation, 3 sweeps) took the layout from 3275 to **3103** (−172), 60 native
routes with 132 mid-body transitions, min true-3D clearance 0.0686 mm, R15
unchanged, and the frozen Native-3D independent validator PASS (all 11 check
groups 0 violations; 7 synthetic positive controls PASS, including the 49 µm
rejection control).

### 3.4 Native 3D Phase 2 (D/E/F)

D (screened joint make-way) found 0 acceptable multi-route repairs from 46
screened candidates (the 20-height layout's blockers are mostly frozen manual-U
leads); E (arc-region rebuild) took 3103 → 3098; F (plain / arc_span / joint
sweeps) 3098 → 3087; two F+ passes and two near-miss passes took it to
**3061** (−42 from Phase 1), 68 native routes, 156 mid transitions, min 3D
0.0686 mm, Native-3D validator PASS.  Joint transactions were protected by
deep-copied rollback (the frozen Phase-2 reject-path rollback defect was fixed
and documented); no manual-U blocking route was deleted.

### 3.5 G1 / G2a / G2b / G3 (XYZ joint optimisation)

| stage | policy on the 368 manual routes | crossings | delta |
|---|---|---:|---:|
| G3 start (authority snapshot, re-validated) | – | 1395* | – |
| G1 | frozen (B class) | 1485 | from 3061 → −1576 |
| G2a | height-only (group re-height) | 1440 | −45 |
| G2b | height-only (per-route re-height) | 1409 | −31 |
| G3 | fully optimisable | **1395** | −14 |
| G3_cold (independent cold control, same 1200 s budget) | fully optimisable | 1646 | from 3061 |

\* authority = accepted Native-3D Phase-2 best (3061); G1 is the first chain
stage and produced 1485, then G2a 1440, G2b 1409, G3 1395.  Router validation
P0/P1/P2 all PASS under the 20-height model; the frozen independent validator
PASS at every stage (0 violations); all stages record their own start/end and
are not credited with each other's gains.

### 3.6 G4 global joint optimisation (a / b / c-frozen / c-free / d)

All arms share the same validated G3 legal start (1395 crossings, routes SHA256
`a6aa699728c2c431b0e2ccae4f82c2772dc3943eee43a8832ccfc22e1415eabf`, 368 manual
routes, 20 planes; hard start-profile guard).  Equal counted budgets
(`d56_candidate_evals ≈ 24000`, `route_3d_checks ≈ 3300–4800`);
wall caps 600–1800 s.  Every arm's own best layout was re-validated in a fresh
20H process (PASS, 0 violations).

| arm | actual work | start | best legal | gain | accepted transactions | d56 candidate evals | 3D checks | wall (s) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| C0 (control continuation) | engine continuation from the common start | 1395 | 1383 | −12 | 7 | — | 1092 | 605 |
| G4a | 8 fixed manual-U groups, group XY+Z rebuild (membership frozen) | 1395 | 1393 | −2 | 1 | 32390 | 4795 | 829 |
| G4b | manual-U dynamic regrouping + height migration + geometry rebuild | 1395 | 1371 | −24 | 10 | 10326 | 1353 | 842 |
| G4c-frozen | ALNS joint make-way, manual-U frozen | 1395 | 1338 | −57 | 9 | 24006 | 3347 | 1212 |
| **G4c-free** | ALNS joint make-way, manual-U **unfrozen** | 1395 | **1322** | **−73** | 12 | 24175 | 3327 | 1238 |
| G4d | 1024-route large-neighbourhood global ALNS | 1395 | 1337 | −58 | 10 | 24266 | 3688 | 1160 |

`min(d56, 24000)` was the binding budget for the three counted arms; the arms
are therefore compared at equal counted effort, not at equal wall clock.

**Progressive chain (B-class, executed from the real 20-height checkpoints).**
`08_g4/08_progressive_chain/` links the arms' best legal checkpoints and re-runs
the next operator from there:

| chain link | start | end | delta | budget | validation |
|---|---:|---:|---:|---|---|
| 0 G3 common start | 1395 | 1395 | 0 | – | PASS (re-validated) |
| 1 best(G4a, G4b) = G4b | 1395 | 1371 | −24 | 900 s (own arm) | PASS |
| 2 G4c rerun from link 1 | 1371 | **1309** | −62 | 700 s counted | PASS (0 violations) |
| 3 best G4c checkpoint | 1309 | 1309 | 0 | – | inherited from link 2 |
| 4 G4d from link 3 | 1309 | **1283** | −26 | 1200 s counted (d56 24837 / checks 3692) | PASS (0 violations) |

Each link's gain is attributed to that link only; the chain's *cumulative*
gain is not attributed to its last operator.  The final accepted 20-height
solution is **chain link 4: 1283 same-plane crossing events, 1221 crossing
pairs, 1024/1024 routed, 0 violations**, frozen read-only in `10_best_valid/`.

### 3.7 Multi-arc ON/OFF controlled ablation (stage 09)

See the dedicated report `09_multi_arc_ablation/ABLATION_REPORT.md`.

* **Strict common-start design (pre-registered): infeasible for 20 heights.**
  Converting the accepted G3 legal optimum's 213 planar multi-arc bodies to
  OFF-legal bodies is deterministic and converted 212/213, but leaves **1
  residual** route (id 456, no OFF-legal body in the 20-height table) and costs
  +3164 crossings (1395 → 4559).  Per the pre-registered feasibility rule the
  OFF arm was not diluted; no ON/OFF pair was fabricated.
* **Executed controlled substitute: cold-start ON/OFF from the identical cold
  assignment, same seeds, same budgets, same validator, only
  `enable_multi_arc` differs.**

| arm | enable_multi_arc | routed | crossings | pairs | mean/route | min 3D (mm) | validator |
|---|---|---:|---:|---:|---:|---:|---|
| ON (default) | 1 | 1024 | **12338** | 10133 | 38.56 | 0.0865 | PASS |
| OFF (`G4_ENABLE_MULTI_ARC=0`) | 0 | 1024 | 14233 | 10637 | 44.48 | 0.1000 | PASS |

At equal legality and equal effort the multi-arc candidate family lowers the
same-plane crossing count by **1895 (−13.3 %)**.  The ablation is an independent
mechanism check and does **not** change the main experiment, which keeps
multi-arc ON for every reported solution.

## 4. Final state and deliverables

* Best legal 20-height layout: **G4 progressive chain link 4, 1283 same-plane
  crossing events, 1221 crossing pairs, 1024/1024 routed, 0 violations, min
  true-3D clearance 0.0622 mm, min radius 15.0 mm, 1950 transitions, 86 mid-body
  transitions on 36 native routes, 658 multi-arc routes, total length
  156597.22 mm**, routes SHA256 `35d7ebed00339bee21fe0ca47075c9b34008120522a47933a099efacf0b90753`,
  independent validator PASS (`native3d.validate_native3d`, 0 violations).
  Frozen read-only in `10_best_valid/` with `BEST_VALID.json`, `SHA256.json` and
  the full validator report (`12_reports/validator_report.md`).
* `01_height_config/` -- the authoritative 20-height table, 21H→20H migration
  table, profile JSON, model self-check, SHA256 index.
* `02_annealing/` -- cold assignment, SA cost curves, seeds/energies, selection.
* `03_fanout_and_xy/` -- initial legal solution, 20 plain + 20
  crossing-annotated per-height XY figures, crossing summary.
* `04_initial_3d_and_e5_repair/` -- the from-scratch annealing programme and the
  accepted E5-analog legal checkpoint.
* `05_native3d_abc/`, `06_native3d_def/` -- Phase 1/2 artifacts, logs, checkpoints,
  validators, transition statistics.
* `07_g123/`, `08_g4/` -- stage layouts, arm artifacts, budgets/ledgers,
  validators, progressive chain.
* `09_multi_arc_ablation/` -- protocol, START fingerprint, conversion report,
  abort record, cold-start ON/OFF arms.
* `10_best_valid/` -- the final frozen legal solution.
* `11_figures/` -- 20 per-height XY figures, 20 crossing-annotated per-height
  figures, 3D global view, crossing hotspot zooms, multi-arc geometry examples,
  stage curve, 21H-vs-20H comparison; manifest + SHA256.
* `12_reports/` -- this report, machine-collected metrics, stage curve,
  validator report, reproduction commands.

## 5. Hard engineering constraints (all verified, none relaxed)

| constraint | required | measured on the final layout |
|---|---|---|
| glass | 150 × 150 × 1 mm, z ∈ [-0.350, +0.650] | conforms (validator glass check 0 violations) |
| routing heights | 20 (18 body + 2 interface), 50 µm pitch | 20 heights, min pitch 0.050000 mm |
| connections | 1024 fixed route identities / port pairs | 1024/1024, port contract 0 violations |
| manual U | 368 routes, identities preserved | 368, frozen policy honoured through G2b, unfrozen only where the stage allows |
| bend radius | Rmin = 15 mm | flat arcs 15.0 mm, transitions sampled min ≈ 15.0 mm |
| waveguide width | 0.05 mm | unchanged model constant |
| same-layer D56 | 0.08 mm centre-line, legal crossings ≥ 5° | strict D56 index, 0 violations; legal crossings counted, not suppressed |
| cross-height | true-3D clearance ≥ 0.05 mm | min 0.0622 mm on the final layout |
| independent validator | PASS | PASS, 0 violations (`12_reports/validator_report.md`) |

## 6. Honest limitations and open items

1. The 20-height final best (1283) is **not better** than the 21-height G4 best
   (1185); it is 8.3 % higher.  The 20-height loss is a real geometric cost of
   the deleted plane and is largest after the annealing stage (+25.7 %).
2. The strict common-start multi-arc ablation has **no feasible OFF start** for
   20 heights (1 residual multi-arc route, route 456); the substituted cold-start
   ablation is controlled but is a different (earlier) stage.
3. Native-3D A1 found no feasible single-route mid-body excursion among the top
   12 crossing routes (all have an arc inside the crossing cluster); the gains
   came from B/C/D/E/F.  This is reported as measured, not compensated.
4. Some frozen report text and plot labels still carry historical 21-height
   numbers (1322/1189/2409 etc.); where an execution path depended on them, the
   driver reads the real value instead (documented in the adaptation log).  The
   historical reference curve is shown for context only.
5. All stages ran as single-process CPU jobs on one workstation; total wall time
   ≈ 3.6 h (measured stage times: 03 270 s, 04 ≈ 15 min, 05 590 s + 20 s
   validation, 06 45 min, 07 68 min, 08 60 min, 09 25 min).  Budgets are
   recorded per stage; no arm silently shrank its budget except where noted
   (G4 wall caps 600–1800 s with equal counted budgets, and the multi-arc
   cold-start arms are equal-budget by construction).
