# 20-height experiment: stage curve (independently validated)

Every number below is read from the stage artifacts written in this experiment; nothing is interpolated and no stage is credited with an earlier stage's gain.

| stage | routed | failed | crossings | crossing pairs | unique-pair | max/route | P95 | mean | min 3D (mm) | R min (mm) | transitions | total length (mm) | validator | delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| S03_initial_cold_start | 1024 | 0 | **12338** | 10133 | 10133 | 83 | 68.0 | 38.55625 | 0.05 | 15.0 | 1848 | 157368.795 | PASS | n/a |
| S04_E5_joint_repair | 1024 | 0 | **3275** | 2774 | 2774 | 49 | 28.0 | 11.196581 | 0.106265934 | 15.0 | 1866 | 157448.209 | PASS | -9063 |
| S05_native3d_phase1 | 1024 | 0 | **3103** | 2733 | 2733 | 49 | 27.0 | 10.572402 | 0.068629474 | 15.0 | 1998 | 157448.425026 | PASS | -172 |
| S06_native3d_phase2 | 1024 | 0 | **3061** | 2705 | 2705 | 49 | 26.55 | 10.376271 | 0.068629474 | 15.0 | 2022 | 157448.464291 | PASS | -42 |
| S07_G123 | 1024 | 0 | **1395** | 1325 | 1325 | 0 | 0.0 | 0.0 | None | None | 1952 | None | n/a | -1666 |
| S08_G4_arms_best | - | - | not run yet | - | - | - | - | - | - | - | - | - | - | - |
| S08_G4_chain | 1024 | 0 | **1283** | 1221 | 1221 | 0 | 0.0 | 0.0 | None | None | 1950 | None | n/a | n/a |
| S10_final_best | 1024 | 0 | **1283** | 1221 | 1221 | 0 | 0.0 | 0.0 | 0.062212557 | 15.0 | 1950 | 156597.221522 | PASS | +0 |

## 21-height historical reference (frozen, read-only)

These are the historical 21-height numbers.  They are a reference curve only -- **not** a target and not directly attributable to the 20-height stages.

| historical stage | crossings |
|---|---:|
| 21H initial fanout-first baseline | 11890 |
| 21H E5 joint repair | 2606 |
| 21H Native 3D Phase 1 | 2440 |
| 21H Native 3D Phase 2 | 2409 |
| 21H G3 | 1322 |
| 21H G4 best legal | 1185 |

