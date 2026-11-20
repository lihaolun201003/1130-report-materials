# 03_best_feasible — G6 FINAL DELIVERABLE (zero sub-45-degree crossings)

**`G6_ANGLE45_VALID_PASS`**

| item | value |
|---|---|
| routes | 1024 / 1024 routed, 20 physical heights |
| routes SHA256 | `39a02c9ec9a598d95bb2a6ef6695ab18a849c037fa9ca24c2a76581c55bc57b2` |
| same-height crossings | 4578 |
| crossings below 45 deg | **0** |
| minimum crossing angle | **45.10850000520098 deg** |
| total angle deficit D_theta | **0.0 deg** |
| Validator A (frozen 20-height project validator) | **PASS**, 0 violations |
| Validator B (independent from-scratch 45 deg validator) | **PASS**, 0 violations |
| total length | 157162.472389 mm |
| minimum true-3D clearance | 0.062212557 mm |
| R15 flat arcs | 1860, all exactly 15.0 mm |
| R15 transitions | 1954, sampled min curvature radius 14.99999998 mm |
| glass | 150 x 150 x 1 mm, all 20 heights used |
| manual U structures | 368, 0 geometry mismatches |

Files
* `routes_l3d.json` — the delivered true-XYZ route payload (frozen schema).
* `BEST_VALID.json` / `SHA256.json` — payload identity.
* `g6_validation_verdict.json` — merged dual-acceptance verdict.
* `validation/frozen/validation.json` — Validator A full report.
* `validation/independent/g5_angle_validation.json` + `g5_crossing_angles.csv` —
  Validator B full report and the per-crossing angle table.

Provenance (fully traceable, no unstated step):
1. frozen G5 warm start: 51 sub-45 crossings (`00_baseline/frozen_g5_v5/`);
2. G6 MultiArc SA, 12 seeds x 8 cycles, profile B (N1 single-route MultiArc
   regeneration): best state = seed 1008, 4 violations, 4454 crossings
   (`03_best_partial/`, SHA256 `50d34cad2dd67721...`);
3. deterministic exhaustive MultiArc repair of that exact state
   (`02_sa_runs/polish_1008/`, 17.4 s): 4 -> 0;
4. dual acceptance (`finalise.py`): A PASS + B PASS.

Independently archived zero solutions (both also A+B PASS, different SHA256):
* `04_validation/alternate_zero_seed1001/` — seed 1001 chain,
  `0df3cda3fc67f8135c51acdee21324906cdbfbfb45427b1a8401652e37a7ffe9`.
