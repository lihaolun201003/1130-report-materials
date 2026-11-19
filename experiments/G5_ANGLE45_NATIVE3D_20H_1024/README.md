# G5_ANGLE45_NATIVE3D_20H_1024

**G5 — Angle-Constrained Native 3D Waveguide Routing**
`theta_min = 45 deg` as a new hard geometric constraint on top of the frozen G4
solution (1024 channels, 20 physical heights, R15, strict D56, 50 um true-3D
clearance, 150x150x1 mm glass).

Frozen input (read only, sha256 verified):
`experiments/COLD_START_20_HEIGHT_1024/10_best_valid/`
`routes_l3d.json` = `35d7ebed00339bee21fe0ca47075c9b34008120522a47933a099efacf0b90753`.

## Headline

| | G4 start | G5 (this round) |
|---|---:|---:|
| routes | 1024 | see `07_reports/G5_REPORT.md` |
| physical heights | 20 | 20 |
| same-height crossings | 1283 | see report |
| crossings below 45 deg | **304** | see report |
| min crossing angle | 5.153763 deg | see report |
| frozen validator (A) | PASS | see `04_validation/` |
| independent 45 deg validator (B) | FAIL (304) | see `04_validation/` |

Everything numeric lives in `07_reports/G5_REPORT.md` and `MANIFEST.json`; this
file only explains the layout.

## Layout

| dir | content |
|---|---|
| `00_baseline_audit/` | G4 crossing-angle audit: `baseline_crossing_angles.csv` (every crossing, exact tangents/angle), `baseline_angle_violations.json` (304 sub-45 deg events, histograms, worst routes), `angle_conflict_graph.json` (G_bad), `baseline_layer_statistics.csv`, `baseline_angle_report.md`, plus the **independent from-scratch validator** output in `independent_angle_validator/` |
| `01_algorithm/` | the runnable pipeline: `run_baseline_audit.py`, `run_local_repair.py`, `run_local_repair_deep.py`, `run_g5.py`, `run_finalise.py`, `run_validation.py`, `make_figures.py`, `build_report.py`, and `constraint_audit/` (which module is the authoritative D56/angle gate, and the verified validator runbook) |
| `02_search_runs/` | per-seed search runs: `run.log`, `g5_search_history.csv`, `g5_candidate_statistics.csv`, `checkpoint_*` |
| `03_best_feasible/` | the frozen G5 deliverable **only if fully legal** (0 crossings below 45 deg and 0 validator violations) |
| `03_best_partial/` | the best legal-under-the-old-contract state when the 45 deg goal is not fully reached (never labelled feasible) |
| `04_validation/` | A = frozen project validator, B = independent 45 deg validator, merged verdict `g5_validation_verdict.json` |
| `05_ctp2_comparison/` | CTP-2.0 crosstalk re-prediction on the G5 geometry, `g5_ctp2_comparison.md` |
| `06_figures/` | all report figures (angle histograms, hotspots, conflict graph, per-layer maps, search curves, 3D, before/after zoom, CTP) |
| `07_reports/` | `G5_REPORT.md` |
| `logs/`, `checkpoints/` | raw logs and search checkpoints |
| `MANIFEST.json` | every delivered file with sha256 + bytes |

## Reproduction

See section 10 of `07_reports/G5_REPORT.md`. Short version:

```powershell
$env:PYTHONPATH="<repo root>"; cd "<repo root>"
python experiments\G5_ANGLE45_NATIVE3D_20H_1024\01_algorithm\run_baseline_audit.py
python experiments\G5_ANGLE45_NATIVE3D_20H_1024\01_algorithm\run_g5.py --seed 20261116 --profile free
python experiments\G5_ANGLE45_NATIVE3D_20H_1024\01_algorithm\run_finalise.py --routes <run>\g5_best_routes.json --out <out>
python experiments\G5_ANGLE45_NATIVE3D_20H_1024\01_algorithm\run_validation.py --source <out>
```

## Code

The new routing module is `four_side_1024/fanout1024/xyzrouter/g5/`:

* `model.py` — exact route model: per-height chains, strict D56 + 45 deg rule,
  3-D clearance, structural checks, and the incremental route evaluator;
* `candidates.py` — the three exact, endpoint-preserving move families
  (corridor shift / re-height / native-3D excursion) and metadata rebuild;
* `search.py` — state, exact violation bookkeeping, candidate pools, scoring;
* `engine.py` — the two-phase violation-driven ALNS with checkpoints;
* `validate_g5_angle.py` — the independent from-scratch 45 deg validator
  (standard library only, no project imports);
* `audit.py` — reserved for the audit helpers.

A read-only copy of the module and of every driver is in `01_algorithm/`
(`code_snapshot/`).
