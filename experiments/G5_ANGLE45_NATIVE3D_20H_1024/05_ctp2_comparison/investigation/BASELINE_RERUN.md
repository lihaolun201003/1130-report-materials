# Baseline rerun — E1 geometry parse on the frozen G4 solution

Purpose: prove that the frozen G4 input is readable and that the geometry half of
the pipeline still reproduces its published numbers, *without* touching any
frozen file. Everything below was produced in a sandbox copy.

---

## 1. How it was run (no frozen file modified)

Because `scripts\run_e1.py:33` **rewrites** `config\simulation_config.yaml` and
lines 26-32 write into `outputs\geometry\`, running it in place would violate
the read-only rule. The unmodified script was therefore executed from a
**sandbox mirror** whose `parents[3]` resolves to the mirror root:

```
<investigation>\_e1_work\experiments\CROSSTALK_PREDICTION_20H_1283_1024\   <- copied src/, scripts/, config/, tests/
<investigation>\_e1_work\experiments\COLD_START_20_HEIGHT_1024\10_best_valid\  <- byte copy of the frozen input (4.25 MB)
```

`src\config.py:11` computes `PROJECT_ROOT = parents[3]`, so the mirror's
`BEST_VALID` automatically pointed at the copied input while the **script,
solver and config files were byte-identical to the originals**.
The copy of `10_best_valid` keeps every byte, so the SHA256 chain still verifies.

```powershell
$PY = "...\OpticalWaveguideRouter2D\.venv\Scripts\python.exe"
Push-Location "<investigation>\_e1_work\experiments\CROSSTALK_PREDICTION_20H_1283_1024"
& $PY scripts\run_e1.py
```

Exit code **0**. Console log: `logs\e1_rerun.log`.

### 1.1 The SHA lock, and how it is satisfied without editing the input

`src\dataio.py:150-182` verifies **every** entry of the input's own
`SHA256.json`, then re-checks `routes_l3d.json` against the hard-coded
`ROUTES_SHA256` (`src\dataio.py:15`) and raises `RuntimeError` on mismatch:

```python
if sha_check["routes_l3d.json"]["actual"] != ROUTES_SHA256:
    raise RuntimeError("routes_l3d.json hash does not match the frozen final route hash")
```

It **did not refuse** here, because the byte copy hashes identically:

```
routes_l3d.json   35d7ebed00339bee... ok=True
```

Point it at a *different* geometry and this is the first thing that breaks
(see `PIPELINE_PARAMETERISATION.md` §3.2). Copying the input is the supported
way to keep the frozen tree untouched.

### 1.2 Hash check output (verbatim)

```
[E1] loaded 1024 routes; sha256 index verified
      assignment_1024.csv                      5abb13315f3f31c1... ok=True
      BEST_VALID.json                          becea7753110c54b... ok=False
      crossing_stats.json                      02ee0533bb338d8c... ok=True
      layer_planes.json                        40e3940260aad26a... ok=True
      physical_layer_stack.json                432cf953939b9d5c... ok=True
      process_rules.json                       da223ccd107286d1... ok=True
      routes_l3d.json                          35d7ebed00339bee... ok=True
      validation\validation.json               237a2e15e0d7c278... ok=True
      validation\validator_consistency_tests.json 1f40eef921365a70... ok=True
      validation.json                          b6526b6dc537d2f8... ok=True
```

`BEST_VALID.json ok=False` is the **pre-existing, documented** discrepancy
(`src\dataio.py:154-157`, `outputs\optical\simulation_manifest.json:63-66`):
the source repo appended `validator_report` + `model_payloads_completed` after
`SHA256.json` was generated (1441 → 1751 bytes). It is not in the `critical`
set, so it is recorded and tolerated — exactly as in the original run.

---

## 2. Reproduced numbers

`logs\e1_rerun.log`, `logs\e1_rerun_summary.json`:

| Quantity | Reproduced | Published (`outputs\geometry\e1_summary.json`) | Match |
|---|---:|---:|---|
| `route_count` / `unique_route_ids` | 1024 / 1024 | 1024 / 1024 | ✅ |
| **`total_length_mm`** | **156597.22152165702** | 156597.22152165702 | ✅ |
| `authoritative_total_length_mm` | 156597.221522 | 156597.221522 | ✅ |
| `absolute_error_mm` | −3.429886419326067e−07 | −3.429886419326067e−07 | ✅ |
| `relative_error` | −2.190260073576216e−12 | −2.190260073576216e−12 | ✅ |
| `max_route_decomposition_error_mm` | 4.973514933226397e−10 | 4.973514933226397e−10 | ✅ |
| `total_L_straight_mm` | 111670.22724679044 | 111670.22724679044 | ✅ |
| `total_L_planar_arc_mm` | 38802.04314835739 | 38802.04314835739 | ✅ |
| `total_L_transition_arc_mm` | 6124.951126508513 | 6124.951126508513 | ✅ |
| `length_min / mean / max_mm` | 44.81386988416087 / 152.92697414224318 / 282.3219524119844 | same | ✅ |
| **`loss_max_db`** | **1.411609762059922** | 1.411609762059922 | ✅ |
| `loss_min_db` / `loss_mean_db` | 0.22406934942080436 / 0.764634870711216 | same | ✅ |
| `total_loss_db` | 782.9861076082848 | 782.9861076082848 | ✅ |
| `n_routes_with_mid_transition` / `n_multi_arc_routes` | 36 / 658 | 36 / 658 | ✅ |
| `total_segments / lines / arcs` | 8065 / 4267 / 1848 | 8065 / 4267 / 1848 | ✅ |
| `length_check_passed` / `all_decompositions_exact` | True / True | True / True | ✅ |

**The regenerated `e1_summary.json` is byte-identical to the published one**
(SHA256 `d035ca18ce8a7e7ac15068f5b55fa4dcfbc3940483d373835b90bd2554a9e4a1`,
matching `simulation_manifest.json:149`).

### 2.1 Runtime

| Run | in-script | wall (incl. interpreter start) |
|---|---:|---:|
| `run_e1.py` | **0.59 s** | **0.85 s** |

Interpreter: `OpticalWaveguideRouter2D\.venv\Scripts\python.exe`
(Python 3.10.11, numpy 2.2.6, scipy 1.15.3, per the manifest).

---

## 3. What E1 does **not** produce (important for the acceptance criteria in the task)

The task text expects the e1 rerun to reproduce "1283 crossings, 1221 pairs,
min non-crossing 3-D clearance 0.062212557 mm". **E1 does not compute any of
those.** Reading `scripts\run_e1.py:23-33` and `src\lengths.py:13-110`, E1 emits
only per-route length decomposition + propagation loss + the input hash record.
Crossings and clearances come from **E4** (`src\interactions.py`, 243 s).

Correct attribution of the three numbers:

| Number | Actually produced by | Value | Evidence |
|---|---|---|---|
| 1283 crossing events / 1221 pairs / 647 routes | **E4** | 1283 / 1221 / 647 ✅ | `outputs\geometry\e4_summary.json` |
| min non-crossing 3-D distance | **E4** | **0.05 mm** (50.000 µm) | `e4_summary.json:30-33` (`min_distance_noncrossing_mm = 0.04999999999999993`) |
| 0.062212557 mm | the **G4 routing Validator**, quoted by the CTP-1.0 report | Validator value | `reports\SIMULATION_REPORT.md` §2 table: ``最小非交叉三维净距 | Validator 0.062212557 mm；独立复核 50.000 µm（= 50 µm 规则边界）`` |

So 0.062212557 mm is the **validator's** clearance metric, while the
pipeline's own independent recount is 50.000 µm (the flat/flat different-height
pitch bound). The G5 baseline audit additionally resolves 0.062209286 mm as the
*transition-vs-flat* sub-category (`G5_...\00_baseline_audit\independent_recount\
min_distance_evidence.json:44-60`), which differs from the validator's
0.062212557 mm by 3.3e−6 mm — i.e. the 0.0622… mm figure is **not** the global
minimum, and no single number should be quoted as "the" clearance without naming
its category.

If in-place reproduction of the crossing statistics is required later, run
`run_e4.py` in the same mirror (243 s, `e4_summary.json` `runtime_seconds =
243.02532148361206`); it is the only stage that regenerates the crossing list.

---

## 4. Bonus: E2 is geometry-independent and bit-reproducible

To settle the "can e2/e3 be reused for a new geometry?" question empirically,
E2 was also re-run in the same mirror (`logs\e2_rerun.log`):

| Output | Result |
|---|---|
| `outputs\optical\e2_summary.json` | **byte-identical** to published |
| `mode_convergence.csv`, `mode_sweep.csv`, `single_waveguide_modes.csv` | byte-identical |
| `mode_reference.npz` | SHA256 `329b52cef73a59eb…` — identical to the value recorded in `simulation_manifest.json:125` |
| reference modes | 3 guided, `n_eff = [1.504557, 1.501874, 1.501874]` (identical) |
| runtime | **5.8 s** in-script / 6.50 s wall |

E2 loads **no** route data (`scripts\run_e2.py:13-17` imports only
`CONFIG, EXPERIMENT_ROOT, parameter_sets, reference_optics`), so it is a pure
function of the optical cross-section. Same argument applies to E3
(κ database + crossing-transfer curve, angle-only) and E6 (sensitivity).
**Conclusion: E2/E3/E6 and the CTP-2.0 V1–V4/V6 kernels never need to be re-run
for G5, and re-running them would give byte-identical results anyway.**

---

## 5. Read-only compliance check

* No file under `OpticalWaveguideRouter2D\experiments\CROSSTALK_PREDICTION_20H_1283_1024\`
  was written: the newest mtime there is `2026-11-19 19:22:15`
  (`reports\SIMULATION_REPORT.md`), well before this session (started 23:10).
* No file under `...\COLD_START_20_HEIGHT_1024\10_best_valid\` was written:
  newest mtime `2026-11-18 02:13:12`.
* The frozen `config\simulation_config.yaml` still hashes to
  `2C0C4F0EAD73FF74…` (the pre-session value).
* The sandbox mirror (`_e1_work\`) is disposable and is removed at the end of
  the investigation; only the logs and the three copied artefacts remain:
  `logs\e1_rerun.log`, `logs\e1_rerun_summary.json`,
  `logs\e1_rerun_input_sha256_check.json`, `logs\e1_rerun_route_lengths.csv`,
  `logs\e2_rerun.log`, `logs\e2_rerun_summary.json`.
