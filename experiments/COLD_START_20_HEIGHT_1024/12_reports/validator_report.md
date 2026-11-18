# Independent validator report -- 20-height experiment

Every accepted layout in this experiment was judged by a **frozen** independent validator, in a fresh process, under the installed 20-height profile.  No threshold, tolerance, clearance rule or crossing definition was modified.

## Final accepted layout (`10_best_valid/`)

| field | value |
|---|---|
| source | 08_G4_chain_link4 |
| routes SHA256 | `35d7ebed00339bee21fe0ca47075c9b34008120522a47933a099efacf0b90753` |
| routed / failed | 1024 / 0 |
| same-plane crossing events | **1283** |
| crossing pairs | 1221 |
| crossing violations | 0 |
| min non-crossing centre-line (mm) | 0.086853441 |
| min true-3D clearance (mm) | 0.062212557 (required >= 0.05) |
| min flat-arc radius (mm) | 15.0 (required 15) |
| min sampled transition radius (mm) | 14.99999998 |
| transitions | 1950 |
| native (mid-body) routes / mid transitions | 36 / 86 |
| manual frozen routes / mismatches | 368 / 0 |
| audited heights | 20 |
| total length (mm) | 156597.221522 |
| **validation_pass** | **True** |
| geometry_pass / contract_pass | True / True |
| violation_count | **0** |
| validator | `four_side_1024.fanout1024.native3d.validate_native3d` |

Per-check violation counts on the final layout: `{}`

## Validator consistency (positive and negative controls)

7/7 consistency tests passed; the negative controls confirm the rules are still enforced (a 49 um plane separation is rejected, an R14 arc is rejected, a 1e-3 position discontinuity is rejected and a flat overlap is rejected).

## Every stage's independent validation

| stage | layout dir | validator | validation_pass | violations |
|---|---|---|---:|---:|
| 03 initial cold start | `03_fanout_and_xy\run_initial_20h` | four_side_1024.fanout1024.reheight21.validate21 | True | 0 |
| 04 E5 joint repair | `04_initial_3d_and_e5_repair\nonc4_programme\E5_joint_repair_final` | four_side_1024.fanout1024.reheight21.validate21 | True | 0 |
| 05 Native 3D Phase 1 | `05_native3d_abc\run_native3d_phase1` | four_side_1024.fanout1024.native3d.validate_native3d | True | 0 |
| 06 Native 3D Phase 2 | `06_native3d_def\run_native3d_phase2` | four_side_1024.fanout1024.native3d.validate_native3d | True | 0 |
| 07 G1/G2/G3 best | `07_g123\run_xyz_joint_1024_20h\best_valid` | four_side_1024.fanout1024.native3d.validate_native3d | True | 0 |
| 08 G4c-free | `08_g4\05_arm_G4c_free` | four_side_1024.fanout1024.native3d.validate_native3d | True | 0 |
| 08 G4 chain link 2 | `08_g4\08_progressive_chain\02_link_G4c` | four_side_1024.fanout1024.native3d.validate_native3d | True | 0 |
| 08 G4 chain link 4 | `08_g4\08_progressive_chain\03_link_G4d` | four_side_1024.fanout1024.native3d.validate_native3d | True | 0 |
| FINAL best (10_best_valid) | `10_best_valid` | four_side_1024.fanout1024.native3d.validate_native3d | True | 0 |

Note on validators: the **planar-assembly** stages (03/04) are judged by `reheight21.validate21`, whose contract is the pre-Native-3D five-part route structure.  Every Native-3D / XYZ / G4 layout (05 onwards) is judged by the frozen `native3d.validate_native3d` (wrapped by `validate_xyz`), which understands mid-body R15 excursions and enforces every geometric rule plus the 368-route manual contract.  Applying `validate21` to a Native-3D layout would report a *contract* mismatch (its part-count assumption), not a geometry violation; those audits are archived for the record and are not acceptance gates.
