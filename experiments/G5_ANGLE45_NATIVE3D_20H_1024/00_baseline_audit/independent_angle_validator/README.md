# Independent G5 crossing-angle validator

`four_side_1024/fanout1024/xyzrouter/g5/validate_g5_angle.py` is a **from-scratch,
single-file** re-implementation of the G5 same-height crossing-angle contract for
the 20-height photonic router. It deliberately imports **no project module** — no
`four_side_1024.*`, no `fslw`, `native3d`, `validate21`, `nonc4`, `d56`,
`fsd25d`, `l3d`, `xyzrouter`, and certainly no
`g4.independent_metrics`. Only the Python standard library is used (numpy/scipy
are permitted by the brief but not needed). A runtime guard
(`assert_no_project_imports`) fails the run if any project module sneaks into
`sys.modules`.

The point of the exercise is that the numbers in
`00_baseline_audit/independent_recount/` can be reproduced by a **different
derivation**, not by re-running the code that produced them. This directory
contains that second derivation and its output on the frozen G4 baseline.

---

## 1. How to run it

All commands are PowerShell, from the project root
`C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D`.

### 1.1 Self-tests (no baseline needed, exit code 0 = pass)

```powershell
$env:PYTHONPATH="C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D"
.venv\Scripts\python.exe four_side_1024\fanout1024\xyzrouter\g5\validate_g5_angle.py --selftest
```

### 1.2 Audit of the frozen baseline (reproduces this directory's output)

```powershell
$env:PYTHONPATH="C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D"
.venv\Scripts\python.exe four_side_1024\fanout1024\xyzrouter\g5\validate_g5_angle.py `
    --run-dir experiments\COLD_START_20_HEIGHT_1024\10_best_valid `
    --out-dir experiments\G5_ANGLE45_NATIVE3D_20H_1024\00_baseline_audit\independent_angle_validator
```

### 1.3 Full CLI

```
python validate_g5_angle.py --run-dir <dir with routes_l3d.json> --out-dir <dir>
                            [--theta-min 45.0] [--layers-json <layer_planes.json>]
                            [--routes-file <explicit routes_l3d.json>]
                            [--selftest]
```

* `--theta-min` (default `45.0`) is the hard threshold used for `pass_45`,
  `theta_margin_deg`, the per-height `n_below_45` / deficits, `D_theta` and
  `D_max`. With the default the JSON also reports `n_lt_45`, which is the count
  against the literal 45° rule; the two coincide at the default.
* `--layers-json` optionally supplies physical `z -> layer label` names. Without
  it the labels are derived from the routes document itself
  (`process.plane_heights_mm` and `process.interface_planes`), producing
  `L2 … L20`, `Z1_INTERFACE`, `Z2_INTERFACE`; if neither is available the labels
  fall back to `H00 … H19` in ascending z order. `z_label` is cosmetic only.
* `--routes-file` lets a caller point at a differently named file; the default is
  `<run-dir>/routes_l3d.json`.

Runtime on the frozen baseline: **~0.6–0.7 s** on one core (the brief allows
minutes). Progress lines are printed per height and per phase; the last line is
`G5_ANGLE_SUMMARY {json}`.

---

## 2. What is checked (the physical contract)

All numbers are centre-line, in millimetres.

1. **Same-height only.** Two flat parts interact only if their physical heights
   agree to `|dz| <= 1e-9`. Different heights never "cross" for this rule.
2. **Genuine crossing.** A transverse intersection of two flat primitives of
   *different* routes at the same height, in the interior of both primitives'
   chains (not at a chain end), and not a tangency and not a coincident stretch.
   `transition` parts are vertical R15 S-curves and never participate.
3. **Crossing angle.** `theta = degrees(asin(|t_i x t_j|))` with the exact unit
   2-D tangents at the hit point:
   * line: `(p1 - p0) / |p1 - p0|`;
   * arc:  `(-sin A, cos A) * sign(sweep)` for the hit angle `A`.

   This is the local acute tangent angle in `[0°, 90°]`, *not* an angle between
   route chords. Equivalent closed forms (used by the self-tests):
   * line vs circle, centre-to-line distance `d`:
     `theta = acos(d/R) = 90° − asin(d/R)`; at the brief's calibration point
     `d = R·sin 45°` this is exactly 45° (the brief's `asin(|d|/R)` phrasing
     coincides with the exact value at that point; the general relation is the
     `acos` one, as the chord-through-the-centre case `d = 0 -> 90°` requires);
   * two equal circles, centre distance `d`: `theta = π − 2·acos(d/(2R))`
     (the acute representative when that exceeds 90°).
4. **G5 hard constraint.** Every genuine crossing must satisfy
   `theta >= 45°`. The report counts crossings with `theta < 45° − 1e-9`
   (`n_lt_45` / `N_<45`) and sums the deficit `45° − theta`.
5. **Other reported conditions.**
   * crossings below the old G4 limit `5°` (`n_lt_5`);
   * coincident / overlapping stretches (`overlap_events`);
   * intersection points within `1e-7 mm` of a chain end (`endpoint_touch_events`);
   * same-height route pairs closer than `0.08 mm` **without** a crossing
     (`clearance_violations`).

`verdict.pass_45` is true iff `N_<45 == 0` **and** 0 illegal overlaps **and** 0
endpoint touches **and** 0 clearance violations.

---

## 3. Exactness claims

Every intersection is solved in closed form; nothing is sampled or iterated.

| pair | algebra |
|------|---------|
| line–line | Cramer's rule on `a0 + u·da = b0 + v·db`; if `|cross(da,db)|/(|da||db|) <= 1e-13` treat as parallel, then test collinearity and overlap by projecting both segments on the common direction. |
| line–arc | quadratic in arc length along the unit line direction: `s = -b ± sqrt(R² - dist²)` with `b = (p0-c)·t`, `dist² = |p0-c|² - b²`. A hit is kept if its angle is on the arc (mod-2π sweep containment). |
| arc–arc | `a = (d² + R1² - R2²)/(2d)`, `h² = R1² - a²`; two points `c1 + a·u ± h·perp(u)`, one when `|h²| <= tol`, none when `h² < -tol`. Each point must lie on both arcs. |

The **angle** is computed from the exact unit tangents (no finite differences).
The **intersection residual** — the distance from the reported point to each
primitive, recomputed independently with point-to-segment / point-to-arc
distance — is stored per crossing in the CSV (`residual_a_mm`, `residual_b_mm`)
and summarised as `residual_max_mm`. On the frozen baseline the maximum residual
is `3.7e-14 mm`, i.e. the two independent intersection branches agree to
floating-point noise.

**Clearance distances** are likewise exact: point-to-segment, the perpendicular
foot from the arc centre onto the segment's support, and the line-of-centres
candidates for arc–arc, plus all curve endpoints. Those candidates cover every
local minimum of the distance function between two line/arc primitives.

**Deduplication.** A route corner is interior to the chain but shared by two
primitives, so the same physical point can be reported twice (once per adjacent
primitive pair). Hits are grouped by `(height, route pair)` and merged when they
are within `1e-6 mm`; the representative with the smallest residual is kept, and
if the duplicate local angles disagree (a tangent discontinuity at the corner)
the **sharpest** angle is reported. The baseline has 13 such duplicate groups;
the largest angle spread inside them is `1.8e-12°`, i.e. all corners involved are
tangent-continuous fillets.

**Acceleration.** A uniform 1 mm XY grid per height is filled with the cells a
primitive actually traverses (each ≤1 mm sub-step contributes its integer
bounding box; arcs get one cell of dilation to absorb the chord sagitta). Any two
primitives that touch or come within one cell are guaranteed to share a cell,
which makes the candidate set complete for both crossings and the 0.08 mm rule.
Only primitive pairs of different routes are tested.

---

## 4. Tolerance policy

| quantity | tolerance | meaning |
|---|---|---|
| same height | `1e-9 mm` | `|dz|` for two flat parts to be the same physical plane |
| chain end | `1e-7 mm` | a hit closer than this to either end of the height chain is an `endpoint_touch`, not a crossing |
| hard angle threshold | `1e-9 deg` guard | `theta < 45° − 1e-9` is a violation |
| legacy angle threshold | `1e-9 deg` guard | `theta < 5° − 1e-9` counts toward `n_lt_5` |
| parallel lines | `1e-13` relative | `|sin|` below this is treated as parallel |
| collinearity | `1e-9 mm` | distance from both endpoints of one segment to the other's line |
| tangency | `1e-12 × max(1, R²)` | discriminant band; inside it the hit is `tangent`/`tangent_or_near_tangent`, never a crossing |
| parameter slack | `1e-7 mm` | accepted overshoot at a primitive end (a joint must be found from both sides) |
| arc containment | `1e-10 rad` | angular slack at an arc end |
| coincident circles | centre `1e-9 mm`, radius `1e-9 mm` | same circle -> `coincident`, never a crossing |
| duplicate hit merge | `1e-6 mm` | identical point coming from adjacent primitives |
| clearance | `0.08 mm` (`−1e-9` guard) | same-height non-crossing centre-line limit |

---

## 5. Outputs

All files are UTF-8. This directory is exactly the output of run 1.2.

### `g5_crossing_angles.csv` — every crossing, one row each
`crossing_id, z_mm, z_label, route_a, route_b, x_mm, y_mm, angle_deg, kind_a,
kind_b, s_a_mm, s_b_mm, theta_margin_deg, pass_45, pass_5, source_a, target_a,
source_b, target_b, plane_a, plane_b` plus the diagnostic columns
`residual_a_mm, residual_b_mm, deficit_deg, n_duplicate_hits`.

* `s_a_mm` / `s_b_mm`: arc length from the start of the route's **flat chain at
  that height**, summing primitive lengths (`radius·|sweep|` for arcs) of the
  flat parts at that height in `parts` order. A route can own several flat parts
  at one height (the 0.25 mm interface leads); they are concatenated in file
  order. This is a chain index used for the endpoint rule and reporting, not a
  physically continuous path length across a transition.
* `plane_a` / `plane_b`: the routes' `target_plane`.
* `pass_45` is `angle >= theta_min − 1e-9`; `pass_5` is `angle >= 5° − 1e-9`.
* Floats are written with `repr` precision (round-trip exact), not rounded.

### `g5_angle_validation.json` — summary, per-height stats, histograms, verdict
Top-level keys: `schema`, `generator`, `independence`, `theta_min_deg`,
`tolerances`, `z_labels`, `summary`, `per_height`, `histogram`, `worst_routes`,
`worst_crossings`, `overlap_events`, `endpoint_touch_events`,
`tangent_or_near_tangent_events`, `clearance_violations`, `skipped`.

`summary` contains: `total_crossings`, `unique_route_pairs`,
`routes_with_crossings`, `max_crossings_per_route` (+ `max_crossings_route_ids`),
`min_angle_deg` + `min_angle_crossing_id`, `n_lt_theta_min`, `n_lt_45`, `n_lt_5`,
`D_theta_deg`, `D_max_deg`, `overlap_event_count`,
`overlap_route_pair_count`, `coincident_no_overlap_event_count`,
`endpoint_touch_count`, `tangent_or_near_tangent_count`,
`clearance_violation_count`, `clearance_min_non_crossing_mm` (+ evidence),
`residual_max_mm`, candidate/merge diagnostics, `verdict` (the four components
plus `pass_45` and the failure reasons), `timing_seconds`.

`per_height` has one row per physical height (including heights with zero
crossings): `z_mm, z_label, n_crossings, n_below_45, n_below_5, min_angle_deg,
min_angle_crossing_id, total_deficit_deg, max_deficit_deg, routes_involved,
worst_routes` (top 5 by deficit, then crossings).

`histogram` uses the required bins
`[0,5) [5,10) [10,20) [20,30) [30,40) [40,45) [45,60) [60,75) [75,90]`.

`worst_routes` is the global top 20 by `sum(max(0, 45° − angle))`;
`worst_crossings` is the 20 smallest angles with full records.

### `g5_angle_violations.json` — detail for every failure category
Primary content: `angle_violations`, the full crossing records with
`angle_deg < theta_min`, sorted by angle ascending. The file also carries the
other categories (`overlap_events`, `endpoint_touch_events`,
`tangent_or_near_tangent_events`, `clearance_violations`) so the verdict is
auditable from one place; an empty array means the category is clean.

### `SELFTEST.txt`
The verbatim `--selftest` output plus the calibration table for the frozen
baseline (measured vs target, deltas, and the cross-check against the project's
own recount).

---

## 6. Calibration result on the frozen G4 baseline

Routes file: `experiments\COLD_START_20_HEIGHT_1024\10_best_valid\routes_l3d.json`
sha256 `35d7ebed00339bee21fe0ca47075c9b34008120522a47933a099efacf0b90753`
(verified in-process and recorded in the summary).

| quantity | measured | target | ok |
|---|---|---|---|
| total genuine crossings | 1283 | 1283 | yes |
| unique route pairs | 1221 | 1221 | yes |
| routes with crossings | 647 | 647 | yes |
| max crossings on one route | 17 (route 559) | 17 | yes |
| min crossing angle | 5.153763467155499° | 5.153763° ± 1e-4 | yes |
| N_<45 | 304 | 304 | yes |
| D_theta | 5520.131087842394° | 5520.131076° ± 0.01 | yes (+1.2e-5) |
| D_max | 39.846236532845° | 39.846237° ± 1e-4 | yes (−4.7e-7) |

Side conditions: 0 overlaps, 0 endpoint touches, 0 tangencies, 0 clearance
violations, minimum non-crossing centre-line distance `0.086853441 mm` (the
project's own recount reports the same pair, routes 105/106 at `z = −0.125 mm`),
max intersection residual `3.7e-14 mm`, runtime `~0.6 s`.

Independent cross-check against `00_baseline_audit/independent_recount/` (read
only, not used by the validator): the per-height crossing counts are identical
for all 19 non-empty heights, and all 304 sub-45° events match exactly by
`(height, route pair, x, y)` with a maximum angle difference of `1.6e-12°`. That
agreement, produced by a different code path, is the intended proof of the
re-implementation.

`pass_45` is therefore **False** for this baseline: the 304 sub-45° crossings are
precisely the defect that the G5 repair run must remove.

---

## 7. Interpretation decisions (documented, not hidden)

1. **Tangency is not a crossing.** A line tangent to an arc, tangent circles
   (`d = 2R`) and the slightly-negative-discriminant case are recorded as
   `tangent_or_near_tangent_events`, never as crossings. They therefore never
   contribute to `N_<45` and can never be mistaken for a high-angle crossing.
   The baseline contains zero such events.
2. **Coincident circles.** Same centre and radius within `1e-9` is always
   `coincident`. If the angular ranges also overlap it is an illegal
   `overlap_event` (and fails the verdict); if they do not, the event is
   recorded but counted in `coincident_no_overlap_event_count`, which is not a
   failure because there is no shared stretch.
3. **"Isolated" intersection.** The brief's clause is implemented as *each
   intersection point is isolated*: a tangency/overlap continuum is rejected,
   and duplicate reports of one physical point from adjacent primitives are
   merged. A primitive pair that pierced a circle twice would contribute two
   distinct crossings and is counted transparently in
   `multi_point_primitive_pairs`. On this baseline that counter is **0**, so the
   stricter reading ("exactly one point per primitive pair") would not change a
   single number.
4. **Chain ends.** The chain at a height starts at the first flat part's first
   primitive and ends at the last flat part's last primitive. A hit within
   `1e-7 mm` of either end is an `endpoint_touch` and is not counted as a
   crossing. The baseline has zero.
5. **Clearance exemption.** A route pair with at least one genuine crossing at a
   height is exempt from the 0.08 mm non-crossing rule at that height (near a
   legal transverse crossing the centrelines necessarily approach). Route pairs
   with an illegal overlap are reported under overlaps and are not double
   counted as clearance violations.
6. **`theta_margin_deg`** is `angle − theta_min` (negative for violations), so the
   most negative margin equals `−D_max`.

---

## 8. Self-tests (28 checks, all analytic)

`--selftest` builds synthetic routes and runs them through the **production**
`audit_routes()` path, asserting the computed angle against closed forms within
`1e-9°`:

1. perpendicular lines -> 90°;
2. lines at 45° -> 45°, and at 44.999° -> flagged as a violation with deficit
   0.001°;
3. line vs circle: chords at 30°, 45° and 90° to the tangent direction
   (`d = R·cos θ`), the brief's `d = R·sin 45° -> 45°`, and a chord through the
   centre -> 90° (two crossings each);
4. two equal circles: `d = 2R·cos 67.5°` -> exactly 45°,
   `d = 2R·cos 87.5°` -> exactly 5°;
5. tangent circles, exactly `d = 2R` and slightly outside -> near-tangent, never
   a crossing, never a 45° violation;
6. coincident arcs -> illegal overlap of the analytic length, never a crossing;
7. crossing exactly at a chain end -> `endpoint_touch`, not a crossing;
8. different heights (`dz = 0.05 mm`) -> no crossing;
9. parallel lines at 0.05 mm -> clearance violation; at 0.5 mm -> clean; a
   crossing pair is exempt from the clearance rule;
10. collinear overlap -> 5 mm overlap, no crossing;
11. `s` accumulation across two flat parts at one height (`s = 14` for a hit in
    the second part after a 10 mm first part);
12. tangent-continuous joint hit -> one deduplicated crossing;
13. chord crossing a full circle twice -> two crossings at the right coordinates;
14. exact line–arc tangency -> tangent, not crossing;
15. slightly negative line–arc discriminant -> `tangent_or_near_tangent`;
16. lines at 30° -> the tangent formula gives 30°;
17. exact primitive-pair distances: arc–arc `d − (r1 + r2)`, line–arc `|d − R|`,
    line–line parallel separation.

Run output on the frozen baseline is in `SELFTEST.txt`
(`SELFTEST_SUMMARY {"passed": 28, "failed": 0, ...}`).

---

## 9. Known limits

* **Centre-line geometry only.** No waveguide width, mode profile, crosstalk,
  bend loss or fabrication tolerance is modelled; 45° is a geometric rule.
* **2-D, same-height only.** Transitions and cross-height 3-D clearances are out
  of scope (they are covered by other validators).
* **Heights are clustered at `1e-9 mm`.** Two flat parts whose `z` differs by
  less than that are treated as the same plane; the baseline's 20 heights are
  0.05 mm apart, so this is never ambiguous here.
* **`s` is a height-chain index.** It concatenates flat parts at one height in
  file order; across a transition between two flat parts at the same height it is
  not a physically continuous length. It is used for endpoint detection and
  reporting only, never for the angle.
* **Overlap detection covers collinear line–line and coincident-circle arc–arc.**
  A line and an arc can only touch at isolated points, so no other overlap type
  exists for these primitives.
* **Distance candidates rely on the grid for completeness.** Any two primitives
  that touch or come within one 1 mm cell are guaranteed to be candidates, and
  `0.08 mm < 1 mm`, so the clearance rule is complete; distances larger than one
  cell are not enumerated (they are irrelevant to the threshold).
* **Duplicate-point merge tolerance `1e-6 mm`.** Two genuinely distinct
  crossings of the same route pair closer than that would be merged; impossible
  for transverse crossings in this dataset (verified: 0 multi-point primitive
  pairs).
* **Corner ambiguity.** If a hit sat exactly on a route corner whose two
  primitives were *not* tangent-continuous, the local angle would be ambiguous;
  the sharpest duplicate angle is then reported. The baseline has 13 duplicate
  groups and a maximum angle spread of `1.8e-12°`, so no such corner is present.
* **Data assumptions.** Arc primitives are rebuilt from `center`, `radius`,
  `start_angle`, `sweep`; their stored `p0`/`p1` are ignored (and are consistent
  to ~5e-10 mm in the frozen file, which the audit log confirms). Route
  continuity, layer identity and 3-D clearance are not re-validated here.
* **Python 3.10+**, Windows paths with spaces are handled (all paths are passed
  as single arguments / absolute paths internally).

---

## 10. Files in this directory

| file | content |
|---|---|
| `g5_crossing_angles.csv` | 1283 crossing records (all crossings, full precision) |
| `g5_angle_validation.json` | summary, per-height statistics, histogram, worst lists, verdict |
| `g5_angle_violations.json` | 304 sub-45° events descending in severity (angle ascending) + other violation categories |
| `SELFTEST.txt` | captured self-test output and the calibration table |
| `README.md` | this document |

Nothing in this directory modifies the frozen baseline or any existing project
file; the validator only reads `routes_l3d.json`.
