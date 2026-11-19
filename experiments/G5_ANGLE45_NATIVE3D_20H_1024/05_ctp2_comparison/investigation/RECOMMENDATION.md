# Recommendation — how to produce a defensible G4-vs-G5 crosstalk comparison

Audience: whoever runs the G5 comparison and writes the claim. Short version:

> **Use CTP-2.0. Call it CTP-2.0 (it exists, locally and upstream). Never use
> CTP-1.0 for the headline. And report the G5 numbers as *bounds*, because every
> G5 crossing sits at or beyond the angle where CTP-2.0 stops being resolved.**

---

## 1. Which model to use, and what to call it

| | Verdict |
|---|---|
| **CTP-2.0** | **Use it.** Full source + outputs at `work\1130-report-materials\experiments\CROSSTALK_PREDICTION_CTP2_20H_1283_1024\`, in sync with upstream `main` (`c6c1f45`, `git ls-remote` verified). It is the model that produced −15.21 / −14.77 / −12.71 dB. |
| **CTP-1.0** | **Do not use for the G4-vs-G5 headline.** Keep its published −65.91 / −58.38 / −57.49 dB only as the "legacy, superseded" column, with the audit reference. |

Naming: the model that computes the comparison is **CTP-2.0**. There is no need
to invent a version. If a reviewer asks why the G4 numbers changed by ~50 dB
between rounds, point at `audit\ctp1_code_audit.md` and
`audit\ctp1_anomaly_reproduction.md`, not at the G5 geometry.

### 1.1 Why CTP-1.0 would actively mislead on G5

CTP-1.0's board matrix uses one constant `p = 1e-7` per crossing
(`run_e5.py:38` sets `p_floor = floor`, `run_e5.py:65` passes it as `p_cross`;
`board.py:53-55` declares the signature, `board.py:77` reads only the scalar)
and **never reads the crossing angle** (`angle_deg` is stored at `board.py:90`
and never used; the `p_cross_nominal` parameter declared at `board.py:54` is
dead). Its headline numbers are therefore
`T_max = p·W_max` with `W_max = 2.5672`, and `leak_max = p·V_max` with
`V_max = 14.526` — pure bookkeeping over the crossing graph.

For G5 that means: even a perfect G5 geometry, with every crossing at 90°, would
still be reported as ≈ **−65.9 dB / −58.4 dB** (only the count/weight terms move,
by a few dB at most). The conclusion would be *"the angle-constrained rerouting
changed nothing"* — which is the opposite of the truth and is precisely the
artifact CTP-2.0 was built to remove. **Do not let a CTP-1.0 run anywhere near the
G5 claim.**

---

## 2. The physical situation CTP-2.0 will report for G5

CTP-2.0's crossing kernel is a function of angle only
(`outputs\crossings\crossing_model_database.csv`, 201 points, 1°–90°,
`theta_deg` 1.0 → 90.0). Its validity regions
(`docs\method_comparison.md:32-35`, `config\simulation_config.yaml:104-108`):

| Angle | Method | Status | Trust |
|---|---|---|---|
| 1–10° | 2-D/3-D BPM (+ FDTD anchors) | `resolved` | resolved, ±0.93 dB 2D-vs-3D |
| 10–30° | BPM, FDTD-cross-checked | `resolved_fdtd_crosschecked` | resolved, ±2.5 dB |
| 30–45° | BPM nominal, Born as bound | `disputed_paraxial` | **disputed, bounds only** |
| **> 45°** | **FDFD-2D upper bound (−85 dB) + Born lower bound** | `upper_bound_port_floor_limited` | **bound only — not a resolved value** |

**G5 has, by construction, only crossings ≥ 45°.** So the G5 board result is
built almost entirely from the `upper_bound_port_floor_limited` rows: the
per-crossing crosstalk is pinned at the FDFD numerical floor
`T_cross = 10^(−85/10) = 3.162e-9`, and the Born lower bound is
−96 … −187 dB. **The G5 prediction is a bound, not a measurement.**

That is not a defect of the comparison — it *is* the result, and it is a strong
one: G5 removes every crossing at which the model is resolved at all.

### 2.1 ⚠️ The 45.0° handover artifact — check G5's minimum angle first

The database has a **12 dB discontinuity at the BPM→FDFD handover**:

| θ | `T_cross_db_nominal` | status |
|---:|---:|---|
| 44.5° | −72.868 | `disputed_paraxial` |
| **45.0°** | **−72.799** | `disputed_paraxial` |
| **45.5°** | **−85.000** | `upper_bound_port_floor_limited` |
| 50° … 90° | −85.000 | `upper_bound_port_floor_limited` |

`run_board_ctp2.py:67-77` interpolates log-log in θ, so a G5 whose minimum
crossing angle is exactly 45.0° will be dominated by the −72.8 dB *disputed*
BPM value, while a G5 at 45.6° jumps to the −85 dB floor. **This is a model
handover, not physics.**

Action: after the board run, read
`board_summary_ctp2.json → crossings.angle_min_deg` and
`→ n_events_above_minus30dB`:
* if `angle_min_deg` is in **[45.0, 45.5)** → quote the *bound pair*
  (`T_cross_low` −101.6 dB … `T_cross_high` −72.8 dB at 45.0°) and say so;
* if `angle_min_deg` ≥ **45.5** → everything is at the −85 dB floor, quote
  "≤ −85 dB per crossing".

(For a clean claim, target a G5 minimum angle ≥ 46°.)

### 2.2 Order of magnitude to expect (floor-limited G5)

With `p = 3.162e-9` per crossing and the same 1024-route/20-height board:

| Metric | G4 (CTP-2.0, actual) | G5 (expected, floor-limited) | Improvement |
|---|---:|---:|---:|
| worst single pair | −15.21 dB | ≈ **−85 dB** (p × loss factors ≤ 1) | ≈ 70 dB |
| worst single-route total leakage | −14.77 dB (R743) | ≈ **−73 dB** (`n_cross × p`, e.g. 17 × 3.16e-9 = 5.4e-8) | ≈ 58 dB |
| multi-input interference/signal | −12.71 dB (R743) | ≈ **−74 dB** (sum over the crossings feeding one output) | ≈ 61 dB |

Note the ordering flips: for G5 the *aggregate* metrics (leakage, ISR) are worse
than the single-pair metric, because they integrate many floor-limited
crossings. Quote them separately; do not quote only the −85 dB pair number.

These are estimates from CTP-2.0's own floor and the G4 crossing-count
statistics. **Run `run_board_ctp2.py` (1.9 s) rather than quoting the estimate.**

---

## 3. The defensible claim

Something in the form:

> Re-running the same optical model (CTP-2.0: BPM/FDFD/FDTD-calibrated local
> crossing kernel, propagation-direction rule, 0.05 dB/cm along the true arc
> length) on the G5 geometry: every crossing angle is ≥ 45°, so **no crossing
> lies in CTP-2.0's resolved range (θ ≤ 30°)**. Per-crossing crosstalk drops from
> −14.37 dB at the G4 minimum angle of 5.154° to **≤ −85 dB** (FDFD upper bound;
> Born lower bound ≤ −96 dB). The board-level worst pair falls from −15.21 dB to
> ≤ −85 dB, and worst single-route leakage from −14.77 dB to ≈ −73 dB.

What makes it defensible:
1. **Same model, same parameters, same optical assumptions** on both geometries
   (cross-section 9×9 µm / Δn 0.0065 / 1310 nm, α = 0.05 dB/cm, `p` from the
   same kernel). Only the geometry changes.
2. **The improvement is not a fitting artifact** — it is the direction the
   kernel predicts monotonically over the resolved range (−14.37 dB @5.15°,
   −30 dB @10°, −60 dB @30°), and the G5 geometry moves entirely outside that
   range.
3. **The G5 number is stated as a bound**, with the floor named.

What would make it indefensible:
* quoting −85 dB as a *predicted* crosstalk value (it is the FDFD noise floor);
* comparing it directly with measured literature (−30…−50 dB) without saying the
  model is an ideal-structure bound;
* using CTP-1.0's −65.9 dB anywhere in the same table without labelling it
  "legacy, erroneous".

---

## 4. Physical-model caveats that must accompany the numbers

1. **Scalar weakly-guided approximation.** `src\ctp2\optics.py` solves
   `∇²ψ + k₀²n²ψ = β²ψ` (`modes.py` in CTP-1.0, eq. documented at
   `config\simulation_config.yaml:49`). No polarisation, no full-vector
   coupling. Valid because Δn/n = 0.43 %; error on n_eff ~1e-5, but
   polarisation-dependent crosstalk is simply absent from the model.
2. **2-D effective-index local crossing model.** The crossing kernel is
   in-plane EIM (`bpm.py`, `crossing.py`, `fdfd2d.py`); 3-D is used only as a
   cross-check at a subset of angles (agreement ≤ 0.93 dB for θ ≤ 10°). The
   vertical (z) dimension enters only through the layer stack and the
   near-approach integration.
3. **Resolution floors — do not over-read low numbers.**
   * CTP-1.0's local FDFD floor is **~1e-7** (−70 dB) by construction
     (`config:128,155`; measured max 6.91e-8). Every CTP-1.0 crossing value is
     *below* its own floor, i.e. CTP-1.0 never resolved a single crossing.
   * CTP-2.0's measured **FDFD floor is 1e-8** (−80 dB) and its conservative
     reporting floor is **−85 dB** (`config:103`, `crossing_model_database.csv`
     `status = upper_bound_port_floor_limited`). Values at −85 dB are
     **upper bounds**, and the Born values below −96 dB are lower bounds.
   * Nothing in either model is meaningful below these floors; report "≤ x dB",
     never "= x dB".
4. **Uncertainty markers exist and should travel with the numbers.**
   `crossing_model_database.csv` carries `uncertainty_db`, `status`, and the
   `[T_cross_low, T_cross_high]` band; the board emits a matching
   `[lower, upper]` matrix pair (`crosstalk_matrix_ctp2_lower/upper.npy`,
   `bounds` block in `board_summary_ctp2.json`). Report the triple
   `(nominal, low, high)` for G4 **and** G5, never the nominal alone.
5. **Ideal structure.** No sidewall roughness, no index drift, no stress
   birefringence, no bend-induced polarisation conversion. Literature says these
   *dominate* measured large-angle crosstalk (−30…−50 dB), so both models are
   **lower bounds on real-device crosstalk**, and the G5 "≤ −85 dB" must be
   framed that way.
6. **Fundamental mode only.** Launch and detection are LP01-like
   (`config:119`); multimode conversion was checked only at 5°/10°/20°
   (`run_v6_multimode.py`). G5 has no small angles, so the multimode question is
   even less constrained there.
7. **Insertion loss above 30° is an extrapolation.** `T_through` above 30° uses a
   literature exponent fitted on three FDTD anchors
   (`run_board_ctp2.py:80-92`, `method_comparison.md:38`), so G5's per-crossing
   insertion loss (≈0.016 dB at 45°, 0.004 dB at 90°) is extrapolated, not solved.
8. **Direction rule.** 856/1283 G4 crossings can reach a target port; 427 only
   add loss (`method_comparison.md:83-91`). The split is recomputed from the
   analytic tangents on the new geometry — verify the G5 split is plausible
   (not 0/1283 or 1283/1283).

---

## 5. Pre-flight checklist before believing a G5 number

- [ ] `03_best_feasible\` contains all 8 payload files (not just `routes_l3d.json`) — §3.1 of `PIPELINE_PARAMETERISATION.md`.
- [ ] `SHA256.json` was **regenerated** for the G5 payload, not hand-edited.
- [ ] `crossing_stats.json` agrees with the crossings re-derived by the analytic engine.
- [ ] Crossings were **re-derived on G5**, and the run did **not** fall back to
      `CTP1_DIR/.../crossing_events_detected.csv` (G4's list). Positive check:
      `angle_min_deg ≥ 45`, and the event count is whatever G5 actually has.
- [ ] `board_summary_ctp2.json` shows `model: "CTP-2.0"`, `n_forward_allowed` of
      the right order (hundreds–thousands, not 0), `all_columns_le_1: true`.
- [ ] G4 reference numbers were **not** regenerated into the same directory
      (compare against the frozen `-15.206468704880304 / -14.769540964146534 /
      -12.711747549665644`).
- [ ] the G5 triple is reported with its `[low, high]` band and the floor named.

---

## 6. One-paragraph summary for the report

> The crosstalk model has one current version, **CTP-2.0** (developed from the
> superseded CTP-1.0 after a source-level audit showed CTP-1.0's local FDFD used
> a non-guided incident field and its board ignored crossing angle entirely).
> On the frozen G4 solution CTP-2.0 gives −15.21 dB worst pair, −14.77 dB worst
> route leakage and −12.71 dB worst multi-input interference/signal, with the
> risk concentrated in 17 crossings below 10°. The G5 solution places every
> crossing at ≥ 45°, i.e. beyond the range in which CTP-2.0's local kernel is
> resolved; the same model therefore returns an upper bound of −85 dB per
> crossing there, and the board-level aggregate metrics become floor-limited
> (≈ −73 dB leakage, ≈ −74 dB ISR) rather than resolved predictions. The
> comparison is between a resolved prediction for G4 and a derived bound for G5,
> and must be stated as such.
