# CTP-2.0 on `G5_ANGLE45_NATIVE3D_20H_1024/03_best_partial` — G4 vs G5

Generated 2026-11-20T00:47:29+0800 by `05_ctp2_comparison/run_ctp2_g5.py`.

* model: **CTP-2.0** — the same code that produced the published G4
  numbers, run from the work copy `05_ctp2_comparison/ctp2_g5/` with the
  geometry path swapped and the outputs redirected to `ctp2_out/`.
* geometry label: `G5_ANGLE45_NATIVE3D_20H_1024/03_best_partial`
* geometry dir: `C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\experiments\G5_ANGLE45_NATIVE3D_20H_1024\03_best_partial`
  (routes sha256 `df4f2bf1b8c00f3b8e89895bd403cd9b105efa5c82adde8bf0e9060838629023`)
* CTP payload fed to the model: `C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\experiments\G5_ANGLE45_NATIVE3D_20H_1024\05_ctp2_comparison\ctp2_payload_g5`
* G4 reference: the frozen `board_summary_ctp2.json`
  (sha256 `c99015d47ce98050711e01896dfc31f762d0a903bb93306814793c220ca542dc`) — read-only, never re-written.
* crossings: **re-derived analytically** for G5 (2321 events),
  never inherited: `crossings/crossing_events_verified.csv`.
* independent checks: **all pass**
  * `board_n_events_equals_verified_csv` = True
  * `board_angle_min_equals_verified_csv` = True
  * `all_columns_le_1` = True
  * `forward_split_not_degenerate` = True
  * `n_routes_1024` = True
  * `model_is_ctp2` = True
  * `total_length_matches_payload` = True
* crossing-angle observation (not a pass/fail criterion): 134 crossing(s) below 45°, minimum 7.518621°

> **134 crossing(s) of the G5 geometry still lie below 45°** (minimum 7.518621°); they are listed as residual
> small-angle events in §5. The headline entries are therefore dominated
> by *resolved* small-angle crossings and are predictions, not bounds;
> only the 2187 floor-limited crossings carry bounds.
> Both readings are spelled out in §6.

## 1. Headline comparison

| metric | G4 (CTP-2.0, resolved) | G5 (CTP-2.0, resolved + bound) | change |
|---|---:|---:|---:|
| worst single port-pair crosstalk | **-15.206 dB** (R723→R743) | **-23.461 dB** (R591→R743) | -8.25 dB |
| worst single-route total leakage | **-14.770 dB** (R743) | **-22.725 dB** (R591) | -7.95 dB |
| multi-input worst interference/signal | **-12.712 dB** (R743) | **-21.061 dB** (R591) | -8.35 dB |
| worst-pair bound band | -15.906 … -14.506 dB | -24.161 … -22.761 dB | |
| route-leakage bound band | -15.472 … -14.066 dB | -23.471 … -21.975 dB | |
| **max base propagation loss (dB)** | 1.411610 | 1.411610 | 0.000000 dB |
| hotspot clusters stored / top cluster ΣP (dB) | 80 / -14.37 | 80 / -22.57 | |
| hotspot clusters total (2 mm × plane) | 649 | 829 | |
| crossings (total / below 45°) | 1283 / **304** | 2321 / **134** | |
| total forward-coupled power (linear) | 1.173809e-01 | 1.622425e-02 | -8.59 dB |
| **share of the forward-coupled power that is a floor-limited upper bound** | **0.0019 %** | **0.0209 %** | |

*`total forward-coupled power`* = Σ of the per-crossing transfer over all
forward-allowed events; it upper-bounds the summed off-diagonal matrix
entries, so its dB change is the cleanest single number for "how much
less power is coupled across the whole board".

That last row answers “how much of the number is a bound?”.

* **G4** — 0.0019 %. Even though 703 of its 856 forward-allowed crossings are floor
  crossings, they carry only 2.223e-06 of the 1.174e-01 total forward
  transfer, so the published G4 numbers are genuinely resolved.
* **G5** — 0.0209 %. This geometry is *not* a pure bound case: the
  headline numbers are still dominated by the resolved/disputed
  crossings, so they are predictions for those events and bounds only
  for the floor-limited ones (§6).

### 1.1 How much of the G5 improvement is a real model result?

**All of it, to within the model's own uncertainty — with one large
caveat.** The floor of the crossing kernel carries
0.0209 % of the forward-coupled power, so replacing the whole
floor with zero would move the aggregate numbers by less than
0.001 dB. The improvement therefore does **not** come from the
−85 dB floor; it comes from the geometry change itself:

* the minimum crossing angle rose **5.153763° → 7.518621°**;
* the crossings below 10° fell **17 → 3**, and below 30° **161 → 72**;
* the total forward-coupled power fell **-8.59 dB**.

The model uncertainty in the band that dominates (θ ≤ 30°) is
±0.7 dB below 10° and ±2.5 dB below 30°, i.e. an order of magnitude
smaller than the improvement — so the ~8 dB is a genuine resolved
result, not an artefact.

**The caveat:** that ~8 dB exists *only because* 134 crossings still sit below 45°. Those residual
events are the entire physical content of the number. Had the G5
round reached its goal (zero sub-45° crossings), every crossing
would be at the −85 dB floor and the board would return a *bound*
in the −60 … −85 dB region rather than a resolved prediction. So the
defensible statement is "the residual small-angle crossings were cut
from 304 to 134, and that bought 8.25 dB of resolved crosstalk" —
not "G5 is 8 dB better than G4" without the residual count next to
it, and certainly not "G5 is 60 dB better" (which would be a
floor artefact).

The 62 crossings in the
30–45° `disputed_paraxial` band carry
0.0407 %
of the forward-coupled power, so the ±18 dB uncertainty of that band
does not propagate into the headline numbers.

Port-pair notation: input → output (the transfer matrix is `T[output, input]`).

Reading the G5 column: the geometry is **mixed** — the crossings that
remain below 45° are resolved (θ ≤ 30°) or disputed (30–45°) and their
transfer is a *prediction*; the crossings at θ ≥ 45.5° contribute the
−85 dB floor value, which is an *upper bound*. The headline numbers are
sums over both kinds, so they are predictions for the resolved part and
bounds for the floor-limited part; the `bound band` rows show the
resulting [Born-low, FDFD-high] interval.

## 2. Secondary metrics

| metric | G4 | G5 |
|---|---:|---:|
| diagonal min / max (dB) | -1.879 / -0.224 | -1.817 / -0.224 |
| max column sum (energy) | 0.949714 (≤1: True) | 0.949714 (≤1: True) |
| median off-diagonal (dB) | -86.335 | -158.564 |
| non-zero off-diagonal entries | 3248 | 4455 |
| second-order chains (n, max dB) | 2660, -37.870 | 4613, -56.377 |
| CT1.0 fixed-p baseline worst pair (dB) | -67.415 | -66.003 |
| board runtime (s) | 1.90 | 1.97 |

The fixed-p baseline column is the superseded CTP-1.0 bookkeeping and is
shown only to demonstrate that it barely moves between geometries — which is
exactly why it must not be used for the G4→G5 claim.

## 3. Crossing statistics and angle distribution

| metric | G4 | G5 |
|---|---:|---:|
| routes | 1024 | 1024 |
| crossings | 1283 | 2321 |
| crossing pairs | 1221 | 1891 |
| routes with crossings | 647 | 834 |
| max crossings on one route | 17 | 91 |
| crossing angles < 45° | **304** | **134** |
| crossing angles < 30° | 161 | 72 |
| crossing angles < 10° | 17 | 3 |
| min / median angle (°) | 5.153763 / 63.256316 | 7.518621 / 65.375682 |
| per-crossing T_cross range (dB) | -85.000 … -14.365 | -85.000 … -19.148 |
| crossings above −30 dB | 17 | 3 |
| forward-direction allowed / blocked | 856 / 427 | 1140 / 1181 |

### Angle distribution (same bins as the G5 project's own audit)

| bin (°) | G4 crossings | G5 crossings | G5 floor-limited | G5 share of forward-coupled power | kernel status in this band |
|---|---:|---:|---:|---:|---|
| [0,5) | 0 | 0 | 0 | — | resolved |
| [5,10) | 17 | 3 | 0 | 34.10 % | resolved |
| [10,20) | 92 | 53 | 0 | 65.68 % | resolved |
| [20,30) | 52 | 16 | 0 | 0.1507 % | resolved |
| [30,40) | 92 | 36 | 0 | 0.0362 % | disputed (bounds only) |
| [40,45) | 51 | 26 | 0 | 0.0045 % | disputed (bounds only) |
| [45,60) | 271 | 411 | 411 | 0.0059 % | **bound** at −85 dB floor |
| [60,75) | 514 | 740 | 740 | 0.0109 % | **bound** at −85 dB floor |
| [75,90] | 194 | 1036 | 1036 | 0.0041 % | **bound** at −85 dB floor |
| **total** | **1283** | **2321** | **2187** | **100 %** | |

Floor-limited events are **1072 of 1140 forward-allowed crossings (94.04 %)**, but they carry only **0.0209 %** of the
forward-coupled power (3.390e-06 of 1.622e-02).

### Kernel resolution status of each crossing

| status | G4 | G5 |
|---|---:|---:|
| resolved | — | 3 |
| resolved_fdtd_crosschecked | — | 65 |
| disputed_paraxial | — | 62 |
| upper_bound_port_floor_limited | — | 2187 |
| handover bracket (status changes between adjacent kernel angles) | — | 4 |

G4 status mix is not tabulated here because CTP-2.0's published board
summary does not carry it; it is recoverable from
`crossings/crossing_optical_analysis_ctp2.csv` of the frozen run.
The G5 mix is what matters: **68 resolved, 4 in a status-changing 0.25° bracket, 62 disputed (30–45°), 2187 at the −85 dB floor** (Σ = 2321).
(The `< 30°` count above is by angle; the resolved-row count differs
slightly where a crossing sits in a kernel bracket whose two ends carry
different statuses.)

## 4. Propagation loss (regenerated for G5)

Same frozen assumptions as G4: α = 0.05 dB/cm, λ = 1310 nm, n₀ = 1.50,
Δn = 0.0065, 9 × 9 µm core, R15 extra bend loss 0 dB (the arc length is
still counted in full).

| metric | G4 | G5 |
|---|---:|---:|
| routes | 1024 | 1024 |
| total length (mm) | 156597.221522 | 156560.515300 |
| mean length (mm) | — | 152.891128 |
| **max propagation loss (dB)** | 1.411610 | **1.411610** |
| mean propagation loss (dB) | 0.764635 | 0.764456 |
| min / median loss (dB) | — | 0.224069 / 0.784799 |
| total loss over all routes (dB) | — | 782.803 |

G4 loss figures are recomputed here from the frozen G4 route lengths
(`e1_summary.json`: `loss_max_db = 1.411609762059922`,
`loss_mean_db = 0.764634870711216`) so the two columns are like-for-like.

## 5. Hotspots

Hotspots are 2 mm × 2 mm × one-plane clusters of crossings, ranked by the
summed per-crossing transfer `P_cross`. Clusters stored: **G4 80, G5 80**.

| rank | G4 (z, x, y) mm | n | ΣP (dB) | G5 (z, x, y) mm | n | ΣP (dB) |
|---|---|---:|---:|---|---:|---:|
| 1 | 0.175, 84.13, 124.59 | 1 | -14.37 | 0.175, 104.27, 126.20 | 3 | -22.57 |
| 2 | 0.325, 47.61, 35.81 | 1 | -15.25 | -0.125, 48.02, 18.25 | 1 | -31.23 |
| 3 | 0.175, 51.32, 26.78 | 1 | -16.35 | -0.025, 133.02, 48.02 | 1 | -31.23 |
| 4 | 0.175, 142.43, 45.42 | 1 | -22.23 | -0.075, 101.98, 132.30 | 1 | -31.23 |
| 5 | 0.175, 103.31, 126.10 | 1 | -22.57 | 0.075, 133.02, 27.98 | 1 | -31.23 |

### Residual small-angle events (θ < 45°)

134 event(s) in total; the 40 smallest angles are listed (sorted by angle).

| route_a | route_b | z (mm) | x (mm) | y (mm) | angle (°) | deficit (°) |
|---:|---:|---:|---:|---:|---:|---:|
| 419 | 437 | 0.075 | 127.826 | 107.657 | 7.518621 | 37.481379 |
| 591 | 743 | 0.175 | 103.314 | 126.097 | 8.392203 | 36.607797 |
| 425 | 428 | 0.025 | 147.219 | 115.615 | 8.582274 | 36.417726 |
| 124 | 130 | -0.125 | 48.021 | 18.246 | 10.161791 | 34.838209 |
| 478 | 493 | -0.075 | 101.979 | 132.303 | 10.161791 | 34.838209 |
| 477 | 492 | -0.025 | 133.019 | 48.021 | 10.161791 | 34.838209 |
| 151 | 207 | 0.075 | 133.019 | 27.979 | 10.161791 | 34.838209 |
| 28 | 29 | -0.075 | 15.625 | 144.575 | 10.475314 | 34.524686 |
| 114 | 115 | -0.125 | 50.875 | 135.612 | 10.475314 | 34.524686 |
| 640 | 672 | 0.275 | 6.842 | 81.125 | 10.475314 | 34.524686 |
| 148 | 225 | 0.025 | 89.097 | 33.125 | 10.475314 | 34.524686 |
| 237 | 426 | 0.075 | 145.291 | 69.125 | 10.475314 | 34.524686 |
| 591 | 719 | 0.175 | 86.125 | 84.447 | 10.475314 | 34.524686 |
| 124 | 132 | -0.125 | 34.375 | 5.973 | 10.475314 | 34.524686 |
| 30 | 36 | -0.075 | 33.125 | 122.758 | 10.475314 | 34.524686 |
| 39 | 101 | -0.075 | 42.375 | 122.758 | 10.475314 | 34.524686 |
| 451 | 472 | -0.075 | 133.875 | 138.698 | 10.475314 | 34.524686 |
| 478 | 499 | -0.075 | 115.625 | 144.575 | 10.475314 | 34.524686 |
| 473 | 476 | -0.025 | 47.180 | 90.125 | 10.475314 | 34.524686 |
| 477 | 498 | -0.025 | 145.291 | 34.375 | 10.475314 | 34.524686 |
| 150 | 153 | 0.025 | 51.816 | 143.125 | 10.475314 | 34.524686 |
| 591 | 719 | 0.175 | 115.875 | 138.210 | 10.475314 | 34.524686 |
| 535 | 671 | 0.225 | 80.875 | 142.791 | 10.475314 | 34.524686 |
| 130 | 131 | -0.125 | 68.875 | 38.892 | 10.475314 | 34.524686 |
| 452 | 473 | -0.025 | 4.709 | 133.875 | 10.475314 | 34.524686 |
| 417 | 432 | 0.025 | 18.449 | 42.125 | 10.475314 | 34.524686 |
| 216 | 237 | 0.075 | 44.229 | 68.875 | 10.475314 | 34.524686 |
| 421 | 527 | 0.225 | 98.875 | 118.507 | 10.475314 | 34.524686 |
| 419 | 422 | 0.075 | 145.291 | 116.125 | 10.475314 | 34.524686 |
| 432 | 435 | 0.025 | 19.243 | 42.125 | 10.475314 | 34.524686 |
| 423 | 426 | 0.075 | 4.709 | 34.375 | 10.475314 | 34.524686 |
| 225 | 228 | 0.025 | 2.727 | 24.625 | 10.475314 | 34.524686 |
| 228 | 411 | 0.025 | 18.449 | 24.625 | 10.475314 | 34.524686 |
| 142 | 145 | 0.075 | 4.709 | 6.375 | 10.475314 | 34.524686 |
| 793 | 973 | 0.225 | 127.003 | 52.826 | 10.755712 | 34.244288 |
| 616 | 737 | 0.525 | 80.292 | 135.375 | 12.838568 | 32.161432 |
| 616 | 847 | 0.525 | 31.958 | 135.375 | 12.838568 | 32.161432 |
| 616 | 843 | 0.525 | 40.958 | 135.375 | 12.838568 | 32.161432 |
| 224 | 974 | 0.075 | 131.480 | 125.875 | 14.444970 | 30.555030 |
| 148 | 414 | 0.025 | 90.210 | 33.375 | 14.835112 | 30.164888 |

## 6. Model-resolution caveat (must travel with every G5 number)

1. CTP-2.0's crossing kernel is resolved only for θ ≤ 30°
   (`resolved` / `resolved_fdtd_crosschecked`), disputed for 30–45°, and
   for θ ≥ 45.5° it reports an **upper bound at the −85 dB FDFD port
   floor** (`status = upper_bound_port_floor_limited`).
2. G5's minimum crossing angle is 7.518621°. Of the 2321 crossings: **68 are in the kernel's resolved
   rows**, 62 are disputed (30–45°), 2187 are at
   the −85 dB floor and 4 sit in a
   status-changing bracket. The geometry is **mixed**: entries driven
   by a resolved crossing are predictions, entries driven by θ ≥ 45.5°
   crossings are upper bounds. Do not label the whole table 'bound' nor
   the whole table 'prediction'.
3. There is a ~12 dB hand-over step in the kernel between 45.0°
   (−72.799 dB, `disputed_paraxial`) and 45.5° (−85.000 dB, floor). The
   crossing set spans both sides, so no single side applies;
   `n_handover_bracket = 4` crossings sit in a
   0.25° bracket whose two ends carry different statuses.
4. Which G5 entries are bounds:
   * any entry whose worst contributing crossing has θ ≥ 45.5° — an
     **upper bound** at the −85 dB floor. The `bound band` rows in §1
     give the matching [Born-low, FDFD-high] interval.
   * the per-crossing table
     `ctp2_out/crossings/crossing_optical_analysis_ctp2.csv` carries the
     angle and `T_cross_db` of every event, so any entry can be traced to
     its status via the table in §3.
   * diagonal, propagation loss, route lengths — resolved (not bounds).
5. Both models assume an ideal structure (no sidewall roughness, index
   drift, stress birefringence or bend-induced polarisation conversion),
   which literature says dominates measured large-angle crosstalk, so even
   the floor-limited upper bound is a *lower* bound on a real device. The
   scalar weakly-guided approximation underpins everything (Δn/n = 0.43 %).
6. Crossing insertion loss above 30° is an extrapolation
   (`loss ∝ (θ/10)^-0.873`, anchored at the converged 10° BPM value), so the
   diagonal inherits that extrapolation.

## 7. Geometry anomalies and independent audit agreement

### 7.1 What changed in the routes (G4 → G5)

| metric | value |
|---|---:|
| routes compared | 1024 |
| routes whose length or height set changed | **71** |
| routes whose set of height plateaus changed (re-heighted) | **71** |
| total length Δ (mm) | -36.706222 |
| total length G4 → G5 (mm) | 156597.221522 → 156560.515300 |
| max / mean \|Δlength\| (mm) | 5.235462 / 0.085981 |
| routes with \|Δlength\| > 1 mm / > 10 mm | 22 / 0 |
| routes longer / shorter | 38 / 29 |

Ten largest length changes (a length change is the fingerprint of a
re-height or a re-route):

| route | Δlength (mm) | G4 (mm) | G5 (mm) | height set changed | G4 z start→end | G5 z start→end |
|---:|---:|---:|---:|:---:|---|---|
| R995 | +5.235 | 203.846 | 209.081 | yes | +0.525→+0.525 | +0.525→+0.525 |
| R986 | +5.235 | 210.795 | 216.031 | yes | +0.525→+0.525 | +0.525→+0.525 |
| R81 | -5.028 | 136.459 | 131.431 | yes | +0.025→+0.025 | +0.025→+0.025 |
| R361 | -5.028 | 136.459 | 131.431 | yes | +0.025→+0.025 | +0.025→+0.025 |
| R376 | -5.028 | 119.127 | 114.099 | yes | +0.025→+0.025 | +0.025→+0.025 |
| R379 | -5.028 | 115.661 | 110.633 | yes | +0.025→+0.025 | +0.025→+0.025 |
| R800 | -5.028 | 75.180 | 70.152 | yes | +0.525→+0.525 | +0.525→+0.525 |
| R82 | -5.028 | 132.992 | 127.964 | yes | +0.025→+0.025 | +0.025→+0.025 |
| R783 | -4.274 | 87.891 | 83.617 | yes | +0.525→+0.525 | +0.525→+0.525 |
| R777 | -3.592 | 99.113 | 95.521 | yes | +0.525→+0.525 | +0.525→+0.525 |

### 7.2 Does the independent audit agree with the regenerated crossings?

| check | value |
|---|---:|
| audit source | `C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\experiments\G5_ANGLE45_NATIVE3D_20H_1024\03_best_partial\g5_crossing_angles.csv` |
| events (regenerated / audit) | 2321 / 2321 |
| matched on (route_a, route_b, plane) | **2321** |
| only in the regeneration | **0** |
| only in the audit | **0** |
| max \|Δx\| / \|Δy\| / \|Δz\| (mm) | 5.00e-07 / 4.99e-07 / 0.00e+00 |
| max \|Δangle\| (°) | 5.00e-07 |
| geometry consistent | **True** |

The two independent implementations agree on **every** event; the
positions and angles differ only by the audit CSV's 6-decimal
rounding. The `s_a_mm`/`s_b_mm` columns are deliberately *not* taken
from the audit CSV (different arc-length origin, constant per route,
up to 167.825 mm)
— they come from the regeneration, whose `Route.pos(s_a)` reproduces
the crossing point to 1e-13 mm; see
`frozen_guard/s_convention_report.json`.

## 8. Reproduce

```powershell
$py = "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\.venv\Scripts\python.exe"
$cmp = "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\experiments\G5_ANGLE45_NATIVE3D_20H_1024\05_ctp2_comparison"
& $py "$cmp\run_ctp2_g5.py" --routes "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\experiments\G5_ANGLE45_NATIVE3D_20H_1024\03_best_partial\routes_l3d.json" --out-root "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\experiments\G5_ANGLE45_NATIVE3D_20H_1024\05_ctp2_comparison\ctp2_out" --payload-dir "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\experiments\G5_ANGLE45_NATIVE3D_20H_1024\05_ctp2_comparison\ctp2_payload_g5" --geometry-label "G5_ANGLE45_NATIVE3D_20H_1024/03_best_partial"
```

Board summary: `C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\experiments\G5_ANGLE45_NATIVE3D_20H_1024\05_ctp2_comparison\ctp2_out\board\board_summary_ctp2.json` (sha256 `dc48d3804979b62c56bd3630f196fc72e23ac54b6980d248ba8cd79e342848f8`).
Machine-readable numbers: `g5_ctp2_summary.json`.

