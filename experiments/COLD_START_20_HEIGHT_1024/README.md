# COLD_START_20_HEIGHT_1024 -- 20-height cold-start rebuild (report materials)

Complete, independently validated rebuild of the 1024-channel 3D optical
waveguide router on a **20-height** physical model, generated from scratch
(no 21-height assignment, geometry or checkpoint was inherited).

## Physical change vs the frozen 21-height model
* plane **L19 (id 19, z = +0.650 mm) deleted**;
* every surviving height **+0.025 mm**; plane ids kept as identity labels;
* interfaces move with the ports: **Z1 = +0.025 mm, Z2 = +0.525 mm**
  (500 um MPO row pitch preserved);
* 18 body planes + 2 routable interface planes = **20 heights**, 50.000 um pitch,
  25.0 um headroom to both glass faces, glass envelope unchanged
  (z in [-0.350, +0.650] mm);
* **no rule relaxed**: R15 = 15 mm, strict D56 same-layer rule, 0.05 mm true-3D
  clearance, 150x150x1 mm glass, 1024 fixed connections, 368 manual-U routes.

## Result
| stage | crossings |
|---|---:|
| 03 cold start (fanout + D56 multi-arc + 3D) | 12338 |
| 04 from-scratch annealing + E5 joint repair | 3275 |
| 05 Native 3D Phase 1 (A/B/C) | 3103 |
| 06 Native 3D Phase 2 (D/E/F) | 3061 |
| 07 G1 -> G2a -> G2b -> G3 | 1395 |
| 08 G4 global ALNS (best arm, G4c-free) | 1322 |
| 08 G4 progressive chain link 4 = **final accepted** | **1283** |

Final accepted solution (`10_best_valid/`): 1024/1024 routed, 0 failed,
**1283 same-plane crossing events / 1221 crossing pairs**, 0 validator
violations, min true-3D clearance 0.0622 mm (>= 0.05), min radius 15.0 mm,
1950 transitions (86 mid-body transitions on 36 native routes), 658 multi-arc
routes, routes SHA256
`35d7ebed00339bee21fe0ca47075c9b34008120522a47933a099efacf0b90753`.
Independent validator: `native3d.validate_native3d` (frozen), PASS.

20H vs the historical 21H reference (11890 / 2606 / 2440 / 2409 / 1322 / 1185):
the 20-height chain ends **+8.3 %** above the 21-height G4 best (1283 vs 1185);
it is close at the global-optimisation end but **not better**, and the loss is
largest after the annealing stage (+25.7 %, one body plane fewer).

## Contents
```
00_audit/                 pipeline map, adaptation log, patch scripts + verify
01_height_config/         authoritative 20-height table, 21H->20H migration
02_annealing/             cold assignment, SA cost curves, seeds/energies
03_fanout_and_xy/         initial legal layout + crossing summary
04_initial_3d_and_e5_repair/  annealing programme + accepted E5 layout
05_native3d_abc/          Native-3D Phase 1 layouts/validators
06_native3d_def/          Native-3D Phase 2 layouts/validators
07_g123/                  G1/G2a/G2b/G3 layouts, reports, router validation
08_g4/                    G4 arm summaries/ledgers/best layouts + chain
09_multi_arc_ablation/    protocol, strict-OFF infeasibility, cold-start ON/OFF
10_best_valid/            FINAL frozen legal solution (routes + validator)
11_figures/final/         3D global, hotspot, multi-arc, stage curve, 21H/20H,
                          per-height plain + crossing-annotated XY figures (PNG)
12_reports/               experiment report, metrics, validator report,
                          reproduction commands
code_snapshot/coldstart20/  the new profile/driver package (python)
```

## Key negative/limiting results (reported honestly)
* The 20H G4 best (1283) is **not better** than the 21H G4 best (1185).
* Strict common-start multi-arc ON/OFF ablation has **no feasible OFF start**
  for 20 heights: 212/213 multi-arc routes convert, route 456 has no OFF-legal
  body, conversion costs +3164 crossings -> pre-registered abort, no diluted arm.
* Controlled substitute (identical cold assignment, only `enable_multi_arc`
  differs): ON 12338 vs OFF 14233 crossings (-13.3 %), both 1024/1024 and valid.
* Native-3D A1 found 0 feasible single-route mid-body excursions among the top
  12 crossing routes (their crossing cluster contains a planar arc); gains came
  from B/C/D/E/F.

## Reproduction
See `12_reports/REPRODUCTION.md` (full ordered command list) and
`12_reports/EXPERIMENT_REPORT.md`.  Source adaptations are documented in
`00_audit/adaptation_log.md`; the 21-height baseline is reproducible unchanged
(assign21: 0 row mismatches, 34/34 invariants).
