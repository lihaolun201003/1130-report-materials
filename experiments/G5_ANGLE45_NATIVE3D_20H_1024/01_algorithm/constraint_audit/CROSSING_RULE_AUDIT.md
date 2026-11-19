# CROSSING-RULE AUDIT — G5 `theta >= 45 deg` change surface

**Project** `OpticalWaveguideRouter2D` (Windows, `.venv` Python 3.10.11)
**Frozen reference** `experiments\COLD_START_20_HEIGHT_1024\10_best_valid\`
(`routes_l3d.json` sha256 `35d7ebed00339bee21fe0ca47075c9b34008120522a47933a099efacf0b90753`)
**Date** 2026-11-19
**Mode** read-only audit; no existing project file was modified.

---

## 0. Executive answer (read this first)

| Question | Answer |
|---|---|
| Authoritative **validator** strict-D56 crossing test | `four_side_1024/fslw/validate_fslw.py` → `evaluate_pair(..., policy="strict")` → `_evaluate_pair_strict()`; the gate is the **module constant `STRICT_SINE_MIN` (line 118, literal `math.sin(math.radians(5.0))`)** compared at **line 1406**. |
| Who calls it for the frozen 20-height run | The verdict of record was produced by `four_side_1024.fanout1024.native3d.validate_native3d` (entry point `…xyzrouter.validate_xyz`, see `VALIDATOR_RUNBOOK.md`): `validate_native3d.check_crossings()` → `reheight21.validate21.check_crossings()` (line 1746; the native validator only **delegates**, it has no crossing logic of its own) → `validate_fslw.audit_route_pairs(..., policy='strict')` → `evaluate_pair` → `_evaluate_pair_strict`. `coldstart20.run_validate` reaches the same `validate21.check_crossings` but applies the *planar-assembly* contract, which G4/G5 native-3D output does not satisfy (see the runbook, run D). |
| Authoritative **search-side** candidate/conflict checker | `four_side_1024/d56/index.py` → `D56Index.evaluate()` → `_evaluate_strict()` (dispatch at line 235); the gate is the **per-instance `self.min_sine`** (line 126) built from the constructor argument `min_cross_angle_deg`, compared at **line 677**. |
| Are they the same code path? | **No — two independent implementations.** `validate_fslw.py` states in its own docstring that it imports no router code (`d56/index.py`, `d56/conflicts.py` "never imported"), and it has its own `_Primitive`/`_PreparedRoute`, its own intersection algebra and its own `_strict_band_edge()`. The numbers happen to agree (verified numerically, §4.3), but the constants are duplicated, so **editing one does not edit the other**. |
| How many constant sites must be edited for `theta_min = 45 deg` (live G5 path) | **1 config constant + 6 hard-coded literals on the live path + the reporting thresholds** (§5.1) — plus 5 optional legacy/sibling copies and the G4 contract-audit labels. |
| Does the 4 mm crossing-window cap become harder at 45 deg? | **No — it becomes strictly easier.** The exempt half-width at 45 deg is `0.08/sin45 + 2*0.0005 = 0.1136 mm` (vs `0.9184 mm` at 5 deg), i.e. **35x** more headroom under the 4 mm cap. A straight-line crossing can never violate the cap for any `theta >= 5 deg`; the cap only ever fires on curved primitives, and a larger minimum angle makes that less likely. |
| What breaks first at 45 deg | Counts, not geometry: of the frozen 1283 same-plane crossing events, **979 (76.3 %) are already >= 45 deg and stay legal; 304 (23.7 %) are in 5 deg .. <45 deg and become `tangent_touch` violations** (min angle in the frozen solution is 5.1538 deg). Those 304 events must be removed by re-routing/re-heighting, not waived. |

---

## 1. Scope and method

Searched (recursively, `*.py` + JSON specifications) for the tokens

```
MIN_CROSS_ANGLE_DEG  min_cross_angle_deg  STRICT_MAX_HALF_WINDOW  SAGITTA
CLEARANCE_2D  EDGE_GAP  WIDTH  MIN_3D_CLEARANCE  crossing_policy  strict
sin(radians(...))  asin(  tangent_touch  endpoint_touch  double_cross
overlap  crossing_window  D56  legal crossing  transverse
```

in `four_side_1024/{fslw,d56,fanout1024/{native3d,reheight21,nonc4,xyzrouter,xyzrouter/g4,coldstart20},v2opt,l3d,fsd25d,manual_u640}`,
`experiments/xyz_joint_g4_1024/code/g4/`, `experiments/COLD_START_20_HEIGHT_1024/`, `outputs/**`, `scratch/**`, `tools/`, `tests/`.

Classification used below:

* **(i) exemption** — code that lets a sub-threshold (shallow / "tangent") crossing be accepted as legal;
* **(ii) statistic** — code that only counts/reports/buckets crossings and cannot accept or reject a route;
* **(iii) unrelated** — same constant/word, different meaning (dead constant, legacy round, placeholder, backup).

"Live G5 path" = executed when the 20-height G4/G5 search or the frozen 20-height validator runs.

---

## 2. The authoritative chain, end to end

### 2.1 Validator (final independent verdict) — the frozen 20-height validator

```
experiments\...\10_best_valid\validation.json
  validator = "four_side_1024.fanout1024.native3d.validate_native3d"
        │
        ▼
four_side_1024/fanout1024/native3d/validate_native3d.py::check_crossings()   (delegation only)
        │   V21.check_crossings(routed, planes, assignment_by_id)
        ▼
four_side_1024/fanout1024/reheight21/validate21.py::check_crossings()        (line 1676)
        │   validate_fslw.audit_route_pairs(prepared, clearance=0.08,
        │                                  sagitta=0.0005, policy='strict')  (line 1746)
        ▼
four_side_1024/fslw/validate_fslw.py::audit_route_pairs()                    (line 1812)
        │   evaluate_pair(first, second, clearance, sagitta, policy)         (line 1838)
        ▼
four_side_1024/fslw/validate_fslw.py::evaluate_pair()                        (line 1598)
        │   if policy == "strict": return _evaluate_pair_strict(...)         (lines 1618-1619)
        ▼
four_side_1024/fslw/validate_fslw.py::_evaluate_pair_strict()                (line 1335)
        │   STRICT_SINE_MIN = math.sin(math.radians(5.0))                    (line 118)
        │   if sine < STRICT_SINE_MIN:  -> "tangent_touch"                   (line 1406)
        ▼
verdict  (violations -> validate21 `crossings` check -> native3d report -> exit code)
```

### 2.2 Search-side candidate legality + global conflict checker (G4/G5 engine)

```
four_side_1024/fanout1024/xyzrouter/g4/arm_base.py::...  self.state = WA.RouteWorld(routes, rows)
        │
        ▼
four_side_1024/fanout1024/xyzrouter/world_adapter.py::RouteWorld
   ├─ evaluate_candidate()  (line 391)
   │     └─ check_3d()  -> l3d.world.World.check_route()          <-- CANDIDATE LEGALITY
   │     └─ crossing_delta() -> index.evaluate()                  <-- crossing bookkeeping
   └─ validate_all()  (line 362)                                  <-- GLOBAL CONFLICT CHECK
         └─ l3d.world.World.check_route() -> PlaneWorld.evaluate()
               └─ d56.index.D56Index(crossing_policy='strict').evaluate()
                     └─ _evaluate_strict()  (line 565)
                           self.min_sine  (line 126)
                           if sine < min_sine: -> "tangent_touch"   (line 677)
```

Two *different* constructors of the same index exist on this path, with **different sources for the
minimum angle**:

| constructor | file:line | minimum angle source |
|---|---|---|
| `l3d.world.PlaneWorld._index()` | `four_side_1024/l3d/world.py:43-46` | `min_cross_angle_deg=C.MIN_CROSS_ANGLE_DEG` → `fslw/config.py:23` |
| `world_adapter.new_index()` | `four_side_1024/fanout1024/xyzrouter/world_adapter.py:39-42` | **literal `min_cross_angle_deg=5.0`** |

`RouteWorld.check_3d()` (legality) uses the **first**; `RouteWorld.crossing_delta()` /
`route_plane_events()` / `g4.joint_world._light_place()` (counting and per-plane bookkeeping) use the
**second**. They must therefore be kept in sync by hand.

---

## 3. Full inventory

### 3.1 Group A — the gate itself (live on the G5 path; **must change**)

#### A1. `four_side_1024/fslw/validate_fslw.py:60-72` — validator constants
```python
 60 # ---------------------------------------------------------------------------
 61 # FSLW SPEC constants (this round; fslw/config.py is the router's copy and is
 62 # deliberately not imported - the numbers are fixed by fslw/SPEC.md 搂1/搂2).
 63 # ---------------------------------------------------------------------------
 64 BOARD = 150.0
 65 RADIUS = 40.0
 66 WIDTH = 0.05
 67 EDGE_GAP = 0.03
 68 CLEARANCE = WIDTH + EDGE_GAP  # 0.080 mm centerline clearance
 69 SAGITTA = 0.0005
 70 CROSSING_SMALL_ANGLE_DEG = 10.0
 71 MIN_CROSS_ANGLE_DEG = 5.0
 72 MAX_HALF_WINDOW = 4.0
```
Note the split: **`MIN_CROSS_ANGLE_DEG` (line 71) is metadata only** (used at 2494 and 2513 to print
`crossing_min_angle_deg` / `min_cross_angle_deg`), while the **real** gate is `STRICT_SINE_MIN`
(line 118). `MAX_HALF_WINDOW` (line 72) is **dead** — never referenced (the live cap is
`STRICT_MAX_HALF_WINDOW`, line 116).
Classification: line 71 **(ii) statistic/metadata**, line 72 **(iii) unrelated (dead)**, line 70 **(ii) statistic**.

#### A2. `four_side_1024/fslw/validate_fslw.py:104-130` — strict-policy block
```python
104 # ---------------------------------------------------------------------------
105 # Strict local-crossing-window policy (SPEC four_side_1024/abcd/SPEC.md 搂2.1).
...
115 # ---------------------------------------------------------------------------
116 STRICT_MAX_HALF_WINDOW = 4.0            # mm; longer c-band running is not a crossing
117 STRICT_LIMIT_TOL = 1e-7                 # violation limit lim = clearance - 1e-7
118 STRICT_SINE_MIN = math.sin(math.radians(5.0))  # D56 minimum genuine crossing angle
119 STRICT_SOLVE_TOL = 1e-5                 # required |h - h*| (SPEC 搂2.1)
120 STRICT_SEARCH_TOL = 1e-5                # internal bracket width (same as the router index)
121 STRICT_SAMPLES = 4                      # coarse samples per probe interval
122 STRICT_GROUP_TOL = 1e-6                 # coincident crossing points are one group
```
**Line 118 is the authoritative validator admissibility constant.** Classification: **(i) exemption
gate** (crossings with `sine >= STRICT_SINE_MIN` are exempted from the 0.08 mm clearance inside their
local window; below it the pair is rejected as `tangent_touch`).

#### A3. `four_side_1024/fslw/validate_fslw.py:1398-1424` — the actual comparison
```python
1398             point = (float(points[0][0]), float(points[0][1]))
1399             t_a = prim_a.parameter(point)
1400             t_b = prim_b.parameter(point)
1401             tangent_a = prim_a.tangent(t_a)
1402             tangent_b = prim_b.tangent(t_b)
1403             sine = min(1.0, abs(_cross(tangent_a, tangent_b)))
1404             sa = first.offsets[index_a] + t_a * prim_a.length
1405             sb = second.offsets[index_b] + t_b * prim_b.length
1406             if sine < STRICT_SINE_MIN:
1407                 touch = True
1408                 if touch_kind is None:
1409                     touch_kind = "tangent_touch"
1410                 if touch_point is None:
1411                     touch_point = point
1412                 continue
1413             if min(sa, first.length - sa,
1414                    sb, second.length - sb) < ENDPOINT_TOUCH_TOL:
1415                 touch = True
...
1421             straight = _is_axis_line(prim_a) and _is_axis_line(prim_b)
1422             crossings.append({"point": point, "sine": sine, "sa": sa, "sb": sb,
1423                               "index_a": index_a, "index_b": index_b,
1424                               "straight": straight})
```
Classification: **(i)** — this is the validator's exemption/rejection decision. The rejection reason
string is `tangent_touch` even for a genuine 20 deg crossing (naming only; no relaxation).

#### A4. `four_side_1024/d56/index.py:43-49` + `111-136` — search-side constants and constructor
```python
 43 EPS = 1e-8
 44 TAU = 2.0 * math.pi
 45 MIN_ANGLE_DEG_DEFAULT = 5.0
 46 # Strict local-crossing-window policy (see four_side_1024/abcd/SPEC.md 搂2).
 47 STRICT_MAX_HALF_WINDOW = 4.0
 48 STRICT_EDGE_TOL = 1e-5
 49 STRICT_SAMPLES = 4
...
111 class D56Index:
112     """Incremental exact conflict index shared by all 1024 single-layer routes."""
113
114     def __init__(self, width=0.05, gap=0.125, sagitta=0.0005, cell=1.5,
115                  min_cross_angle_deg=MIN_ANGLE_DEG_DEFAULT, check_outside=None,
116                  crossing_policy='exact', max_half_window=STRICT_MAX_HALF_WINDOW):
...
126         self.min_sine = math.sin(math.radians(float(min_cross_angle_deg)))
127         self.min_angle_deg = float(min_cross_angle_deg)
128         self.crossing_policy = crossing_policy
129         self.max_half_window = float(max_half_window)
```
Classification: **(i)** — `MIN_ANGLE_DEG_DEFAULT` is the *fallback* exemption threshold;
`min_cross_angle_deg` is the per-instance knob the search passes in.

#### A5. `four_side_1024/d56/index.py:234-236` — strict dispatch
```python
234     def evaluate(self, prepared, exclude=(), stop_on_invalid=True):
235         if self.crossing_policy == 'strict':
236             return self._evaluate_strict(prepared, exclude, stop_on_invalid)
```
Classification: **(iii) dispatch** (no geometry), but it is the switch that selects the strict rule.

#### A6. `four_side_1024/d56/index.py:668-688` — the search-side comparison
```python
668             point = points[0]
669             ta = prim.parameter(point)
670             tb = theirs.parameter(point)
671             tangent_a = prim.tangent(ta)
672             tangent_b = theirs.tangent(tb)
673             sine = min(1.0, abs(tangent_a[0] * tangent_b[1]
674                                 - tangent_a[1] * tangent_b[0]))
675             sa = prepared.offsets[i] + ta * prim.length
676             sb = other.offsets[j] + tb * theirs.length
677             if sine < min_sine:
678                 result.reason = 'tangent_touch'
679                 result.blockers.append(rid)
680                 self.index_seconds += time.perf_counter() - t0
681                 return finish()
```
Also the axis-aligned fast path (same file, lines 617-635) hard-codes `sine=1.0` because two
axis-aligned lines can only meet at 90 deg:
```python
632                         by_route.setdefault(rid, []).append(
633                             dict(i=i, j=j, sa=sa, sb=sb, sine=1.0, point=(vx, hy),
634                                  straight=True))
```
Classification: **(i) exemption gate**; the `sine=1.0` shortcut is safe for any `theta_min <= 90 deg`
but would become wrong if non-axis-aligned lines were ever routed through this fast path.

#### A7. `four_side_1024/d56/index.py:704-756` — strict window construction (angle used only as a probe seed)
```python
704             windows_a = []
705             windows_b = []
706             for group in groups:
...
712                 for record in group:
713                     partners_a.add(record['j'])
714                     partners_b.add(record['i'])
715                     if record['straight']:
716                         # two axis-aligned straight lines: window = clearance/sin
717                         # is exact on both curves (sine == 1 for orthogonal lines)
718                         half = clearance + margin
719                         candidate = (half, half, half, half)
720                     else:
721                         partner_b = other.prims[record['j']]
722                         partner_a = prepared.prims[record['i']]
723                         guess = limit / max(record['sine'], 1e-3)
724                         e_l = self._window_edge(prepared, record['sa'], -1.0,
725                                                 partner_b, guess, limit)
...
732                         if e_l is None or e_r is None or f_l is None or f_r is None:
733                             result.reason = 'crossing_window_excessive'
```
Classification: **(iii) geometry solve, angle-independent** — `guess` only seeds a bisection; the
window half-width is solved from the *real* distance to the partner primitive and capped at
`max_half_window = 4.0 mm` (`_window_edge`, lines 422-516). **This is why raising the angle cannot
tighten the window rule** (see §5.3).

#### A8. `four_side_1024/fslw/config.py:22-23` + `96-97` — the single project-wide config knob
```python
22 SAGITTA_MM = 0.0005
23 MIN_CROSS_ANGLE_DEG = 5.0
...
96         sagitta_mm=SAGITTA_MM,
97         min_cross_angle_deg=MIN_CROSS_ANGLE_DEG,
```
Classification: **(i)** — this is the value every config-driven router reads. Changing it to `45.0`
propagates to: `l3d/world.py:45`, `fslw/search.py:26`, `fslw/run.py:50`, `v2opt/core.py:41`,
`fsd25d/config25d.py:57` → `world25d.py:155`, `router25d.py:451`, `l3d/common.py:143`,
`manual_u640/u_geometry.py:90`, `native3d/crossing_cache.py:45`, `native3d/blocker_analysis.py:285`,
`fanout1024/fanout.py:644`, `manual_u640/{auto_routes,assemble,verify}.py`, `fslw/metrics.py:267`.

#### A9. `four_side_1024/l3d/world.py:39-49` — candidate-legality index (config-driven)
```python
 39     def _index(self, z_mm):
 40         key = plane_key(z_mm)
 41         index = self.indices.get(key)
 42         if index is None:
 43             index = D56Index(width=C.WIDTH_MM, gap=C.EDGE_GAP_MM,
 44                              sagitta=C.SAGITTA_MM,
 45                              min_cross_angle_deg=C.MIN_CROSS_ANGLE_DEG,
 46                              crossing_policy='strict')
 47             self.indices[key] = index
 48             self.parts[key] = {}
 49         return index
```
Classification: **(i)** — this is the **candidate legality checker** reached by
`RouteWorld.evaluate_candidate → check_3d → World.check_route → PlaneWorld.evaluate`.

#### A10. `four_side_1024/fanout1024/xyzrouter/world_adapter.py:39-42` — **hard-coded** literal
```python
 39 def new_index():
 40     return D56Index(width=float(C.WIDTH_MM), gap=float(C.EDGE_GAP_MM),
 41                     sagitta=0.0005, min_cross_angle_deg=5.0,
 42                     crossing_policy='strict')
```
Classification: **(i)** — used by `RouteWorld` for crossing counting / per-plane bookkeeping
(`route_plane_events` line 251, `crossing_delta` line 276, `commit`/`batch_commit` lines 430/528) and
by `g4/joint_world.py::_light_place` (line 247). It does **not** decide legality directly (legality
comes from A9), but it decides *whether a crossing is counted*, so leaving it at 5.0 makes the G5
search's crossing objective and its legality checker disagree.

#### A11. `four_side_1024/fanout1024/layer2d.py:1386-1388` — **hard-coded** literal (2D layer routing)
```python
1386         self.index = D56Index(width=WIDTH, gap=EDGE_GAP,
1387                               sagitta=0.0005, min_cross_angle_deg=5.0,
1388                               crossing_policy='strict')
```
Classification: **(i)** — the index used by the 2D layer router (`nonc4.cross_router` inherits
`self.index` and calls `self.index.evaluate(prepared)` at `nonc4/cross_router.py:427`) and by the
native3d initial-body routing.

#### A12. `four_side_1024/d56/search.py:17-22` — **hard-coded** default cfg
```python
17 DEFAULT_CFG = dict(
18     width=0.05,
19     gap=0.125,
20     sagitta=0.0005,
21     min_radius_mm=5.0,
22     min_cross_angle_deg=5.0,
```
Classification: **(i)** — but only for the *legacy* D56 round. `fslw/search.py:20-26` copies this dict
and then **overrides** `min_cross_angle_deg=C.MIN_CROSS_ANGLE_DEG`, so the live fslw path is
config-driven; `d56/search.py` itself is only reached by the d56 round's own run scripts.

---

### 3.2 Group B — duplicated / sibling implementations (same predicate, other modules)

| # | file:line | snippet | class | live on G5 path? |
|---|---|---|---|---|
| B1 | `four_side_1024/d56/validate_d56.py:80-82`, gate at `1361` | `STRICT_SINE_MIN = math.sin(math.radians(5.0))` … `if sine < STRICT_SINE_MIN:` | (i) | **No** — d56-round validator (`audit_all.py`, `crosscheck_strict.py`, `d56/metrics.py` use it as *their* authority) |
| B2 | `four_side_1024/v3/validate_v3.py:137`, gate at `1528` | same code, v3 round | (i) | **No** — v3 round |
| B3 | `four_side_1024/fsd25d/validate25d.py:1440` | `result = validate_fslw.audit_route_pairs(prepared, policy="strict")` | (iii) consumer | No (25D round) — inherits A2 automatically |
| B4 | `four_side_1024/l3d/validate_l3d.py:1865-1867` | `result = validate.audit_route_pairs(prepared, clearance=CLEARANCE_MM, sagitta=SAGITTA_MM, policy="strict")` | (iii) consumer | No — L3D round validator; inherits A2 |
| B5 | `four_side_1024/l3d/validate_l3d_multi.py:1834` | `policy="strict")` (same call) | (iii) consumer | No |
| B6 | `four_side_1024/fanout1024/nonc4/crossings.py:106-129` | `result = validate_fslw.audit_route_pairs(prepared, clearance=D56_CLEARANCE_MM, sagitta=SAGITTA_MM, policy='strict')` | (iii) consumer | **Yes** (writes `crossing_stats.json`) — inherits A2 automatically |

### 3.3 Group C — a **third independent re-implementation** used as the G4 crosscheck

`four_side_1024/fanout1024/xyzrouter/g4/independent_metrics.py` (live G4 report code) and its frozen
snapshot `experiments/xyz_joint_g4_1024/code/g4/independent_metrics.py`. Its docstring is explicit:
"DELIBERATELY INDEPENDENT … it does not import `validate_fslw` / `nonc4.crossings` / `validate21` to
compute any number."

```python
 65 CLEARANCE_2D_MM = 0.08          # fanout1024/common.py CLEARANCE_2D_MM
...
 71 MIN_CROSS_ANGLE_DEG = 5.0       # fslw/config.py MIN_CROSS_ANGLE_DEG
 72 STRICT_MAX_HALF_WINDOW_MM = 4.0  # fslw/validate_fslw.py STRICT_MAX_HALF_WINDOW
 73 SAGITTA_MM = 0.0005
...
1353                 if reference['sine'] < math.sin(math.radians(MIN_CROSS_ANGLE_DEG)):
1354                     allowed = False
1355                     reasons.append('tangent_touch')
...
1368                 if half > STRICT_MAX_HALF_WINDOW_MM + SAGITTA_MM:
1369                     allowed = False
1370                     reasons.append('crossing_window_excessive')
...
2071             min_crossing_angle_deg=MIN_CROSS_ANGLE_DEG,
2072             max_window_half_mm=STRICT_MAX_HALF_WINDOW_MM,
```
(line numbers `1353/2071` are the snapshot; the live copy has them at `1360/2078`.)

Classification: **(i) exemption gate of a third implementation.** It never accepts routes, but it
produces `illegal_crossing_count` / `allowed_crossing_count` and the `crossing_exemption_policy`
block of the G4 audit; if left at 5 deg it would declare 5–45 deg crossings legal and disagree with
(a) and (c) — a false "validator discrepancy" for G5.

### 3.4 Group D — statistics / reporting only (no accept/reject power)

| # | file:line | snippet | note |
|---|---|---|---|
| D1 | `four_side_1024/fslw/validate_fslw.py:70,1903,1950,2486,2562` | `CROSSING_SMALL_ANGLE_DEG = 10.0` … `if angle < CROSSING_SMALL_ANGLE_DEG: small_angle += 1` … `"small_angle_threshold_deg": CROSSING_SMALL_ANGLE_DEG` | (ii) 10 deg "small angle" bucket. At G5 this bucket should become 45 deg (or be renamed), otherwise the report calls 20 deg crossings "not small" |
| D2 | `four_side_1024/fslw/metrics.py:576-602` | `if angle < 5.0: small_angle_5 += 1` … `"small_angle_5deg_threshold_deg": 5.0` | (ii) literal 5.0 hard-coded statistic |
| D3 | `four_side_1024/fslw/metrics.py:1882-1890` | `statistics["small_angle_5deg_threshold_deg"] = 5.0` | (ii) same, persisted summary |
| D4 | `four_side_1024/v3/metrics.py:1430` | `statistics["small_angle_5deg_threshold_deg"] = 5.0` | (ii) v3 round copy |
| D5 | `four_side_1024/d56/validate_d56.py:2198` | `"crossing_min_angle_deg": 5.0,` | (ii) metadata in the d56 report |
| D6 | `four_side_1024/fslw/validate_fslw.py:2494,2513` | `"crossing_min_angle_deg": MIN_CROSS_ANGLE_DEG,` / `"min_cross_angle_deg": MIN_CROSS_ANGLE_DEG,` | (ii) metadata — *does not* control the gate |
| D7 | `four_side_1024/fanout1024/native3d/crossing_intervals.py:87-88,491,535,1295,1769-1775` | `MIN_CROSS_ANGLE_DEG = 5.0` / `MIN_SINE = math.sin(math.radians(MIN_CROSS_ANGLE_DEG))` / `if record[3] >= min_sine: transverse_s.append(...)` / `'only transverse contacts (angle >= %.1f deg) are counted as crossings' % MIN_CROSS_ANGLE_DEG` | (ii) **planning model**, not a gate: it predicts how many crossings a candidate height change adds/removes; collinear/tangent contacts are "reported separately (never counted as crossings)". It must follow 45 deg or the planner will mis-rank candidates |
| D8 | `four_side_1024/fanout1024/native3d/arc_crossing_analysis.py:74-75,712-715,808-809` | `MIN_CROSS_ANGLE_DEG = 5.0` … `transverse = [item for item in unique if item['sine'] >= cache.min_sine]` | (ii) analysis of arc-crossing regions (report) |
| D9 | `four_side_1024/manual_u640/verify.py:2053-2058` | `ctx.check('crossings_legal_angle_ge_5deg', ctx.min_cross_angle is None or ctx.min_cross_angle >= float(C.MIN_CROSS_ANGLE_DEG) - 1e-9, ...)` | (i) acceptance check **of the manual-U round**, but derived from `C.MIN_CROSS_ANGLE_DEG`, so it follows A8 automatically; the check *name* would become stale |

### 3.5 Group E — dead, legacy or unrelated uses of the same token

| # | file:line | why unrelated |
|---|---|---|
| E1 | `four_side_1024/fslw/validate_fslw.py:72` `MAX_HALF_WINDOW = 4.0` | **dead constant** (never referenced); the live cap is `STRICT_MAX_HALF_WINDOW` (line 116) |
| E2 | `four_side_1024/abcd/run.py:55,140` `min_cross_angle_deg=5.0` | different round (ABCD, R=40 mm / gap 0.125 mm sensitivity study), not imported by the 20H chain |
| E3 | `four_side_1024/manual_u640/config.py:37` `MIN_CROSS_ANGLE_DEG = 5.0` | the manual-U round keeps its **own copy** of the process constants (only `u_geometry.py:90` reads `C.MIN_CROSS_ANGLE_DEG`). Not executed by G5; would need its own edit if that round is re-run |
| E4 | `outputs/manual_c4_new_connectivity/NEW_MANUAL_CSV_1024_FULL_CAMPAIGN/11_corner_radius_analysis/scripts/s03_corner_connectors.py:58` and `s04_structural.py:56` | one-off analysis scripts under `outputs/`, not part of the package |
| E5 | `experiments/**/_source_backup/**`, `experiments/**/archive/code/**`, `experiments/**/backups/**`, `scratch/**`, `scratch_*/**` | frozen copies/backups (`independent_metrics.py`, `contract_audit.py`, `crossing_intervals.py`, `arc_crossing_analysis.py`, `blocker_analysis.py`, `layer2d.py`, `fanout.py`, `validate_v3.py`, …). They contain the same 5.0 literals but no G5 code path imports them. **Do not edit** (they are provenance for the frozen runs) |
| E6 | `four_side_1024/conflicts.py:463` `if sine < 1e-7 or is_endpoint:` | legacy geometric primitives helper; the `1e-7` is a *numerical* tangency epsilon, not the 5 deg rule |
| E7 | `four_side_1024/fslw/validate_fslw.py:100,1659` / `four_side_1024/d56/index.py:980` `SINE_TOL = 1e-7` | see §3.6 — the **legacy/exact policies' exemption** |

### 3.6 Group F — the other exemptions (small-angle crossings are legal *there*)

These are the only places where a *shallow* crossing is accepted with no angle floor. They are the
`legacy` and `exact` policies, kept for sensitivity comparison and **not** used by the frozen 20H
verdict or by the G4/G5 search:

| # | file:line | snippet | class |
|---|---|---|---|
| F1 | `four_side_1024/fslw/validate_fslw.py:1654-1664` | `sine = min(1.0, abs(_cross(tangent_a, tangent_b)))` … `if sine < SINE_TOL or is_endpoint:` → treated as `touch`; `half = clearance / crossing["sine"] + 2.0*sagitta` (line 1696) | (i) legacy/exact exemption — **any** angle > 1e-7 is exempted |
| F2 | `four_side_1024/d56/index.py:353-363` (`evaluate`, non-strict) and `979-981` (`_legacy_evaluate`) | `if sine < min_sine:` / `if sine < 1e-7 or ...` | (i) the `exact`/`legacy` policies of `D56Index` |

For G5 these must **stay** as they are (they are comparison baselines, not the acceptance rule); the
requirement "nothing else may be relaxed" is satisfied by leaving them untouched *and* by not letting
any live path use them (`crossing_policy='strict'` is already asserted by `contract_audit.py:74,86,103`).

### 3.7 Verbatim snippets for the Group B–F rows

`four_side_1024/d56/validate_d56.py:80-82` and gate at `1355-1367` (B1) — byte-identical code to
`fslw/validate_fslw.py`, forked for the d56 round:
```python
 80 STRICT_MAX_HALF_WINDOW = 4.0            # mm; longer c-band running is not a crossing
 81 STRICT_LIMIT_TOL = 1e-7                 # violation limit lim = clearance - 1e-7
 82 STRICT_SINE_MIN = math.sin(math.radians(5.0))  # D56 minimum genuine crossing angle
...
1358             sine = min(1.0, abs(_cross(tangent_a, tangent_b)))
...
1361             if sine < STRICT_SINE_MIN:
1362                 touch = True
1363                 if touch_kind is None:
1364                     touch_kind = "tangent_touch"
```
and its report constant at `2195-2199`:
```python
2195     if policy == "strict":
2196         policy_block.update({
2197             "centerline_clearance_limit_mm": clearance - STRICT_LIMIT_TOL,
2198             "crossing_min_angle_deg": 5.0,
2199             "crossing_max_half_window_mm": STRICT_MAX_HALF_WINDOW,
```

`four_side_1024/v3/validate_v3.py:135-139` and gate at `1528` (B2) — same fork, v3 round:
```python
135 STRICT_MAX_HALF_WINDOW = 4.0            # mm; longer c-band running is not a crossing
136 STRICT_LIMIT_TOL = 1e-7                 # violation limit lim = clearance - 1e-7
137 STRICT_SINE_MIN = math.sin(math.radians(5.0))  # D56 minimum genuine crossing angle
138 STRICT_SOLVE_TOL = 1e-5                 # required |h - h*| (SPEC 搂2.1)
139 STRICT_SEARCH_TOL = 1e-5                # internal bracket width (same as the router index)
```

`four_side_1024/fsd25d/validate25d.py:1438-1441` (B3) — consumer, inherits the validator gate:
```python
1438         started = time.perf_counter()
1439         try:
1440             result = validate_fslw.audit_route_pairs(prepared, policy="strict")
1441         except Exception as exc:  # frozen validator must not crash the audit
```

`four_side_1024/l3d/validate_l3d.py:1864-1867` (B4) and `validate_l3d_multi.py:1831-1834` (B5):
```python
1864         started = time.perf_counter()
1865         result = validate.audit_route_pairs(
1866             prepared, clearance=CLEARANCE_MM, sagitta=SAGITTA_MM,
1867             policy="strict")
```

`four_side_1024/fanout1024/nonc4/crossings.py:125-129` (B6) — consumer used to write
`crossing_stats.json`; inherits the validator gate:
```python
125     result = validate_fslw.audit_route_pairs(
126         prepared, clearance=D56_CLEARANCE_MM, sagitta=SAGITTA_MM,
127         policy='strict')
128     result['prepare_failures'] = failed
129     return result
```

`four_side_1024/fanout1024/xyzrouter/g4/independent_metrics.py:1345-1373` (C) — third independent
implementation (live copy; the archived snapshot has these at 1338-1366):
```python
1345             # every group must be a genuine transverse interior crossing
1346             allowed = True
1347             reasons = []
1348             windows_a = []
1349             for group in groups:
1350                 reference = group[0]
1351                 if reference['sine'] < math.sin(math.radians(MIN_CROSS_ANGLE_DEG)):
1352                     allowed = False
1353                     reasons.append('tangent_touch')
1354                     continue
...
1362                 # distance along chain A from the crossing to the 0.08 edge
1363                 left = _edge_distance(info_a, reference['sa'], info_b[0],
1364                                       LIMIT_2D, -1.0)
1365                 right = _edge_distance(info_a, reference['sa'], info_b[0],
1366                                        LIMIT_2D, 1.0)
1367                 half = max(left, right)
1368                 if half > STRICT_MAX_HALF_WINDOW_MM + SAGITTA_MM:
1369                     allowed = False
1370                     reasons.append('crossing_window_excessive')
```

`four_side_1024/fslw/validate_fslw.py:70` with `1899-1908` (D1) — reporting bucket, 10 deg:
```python
 70 CROSSING_SMALL_ANGLE_DEG = 10.0
...
1899     histogram = OrderedDict((label, 0) for label, _, _ in HIST_BINS)
1900     small_angle = 0
1901     for crossing in crossings:
1902         angle = crossing["angle_deg"]
1903         if angle < CROSSING_SMALL_ANGLE_DEG:
1904             small_angle += 1
1905         for label, low, high in HIST_BINS:
1906             if low <= angle < high:
1907                 histogram[label] += 1
1908                 break
```

`four_side_1024/fslw/metrics.py:579-584` and `599-602` (D2), `1888-1890` (D3):
```python
579     for crossing in crossings:
580         angle = float(crossing.get("angle_deg") or 0.0)
581         if angle < 10.0:
582             small_angle += 1
583         if angle < 5.0:
584             small_angle_5 += 1
...
599         small_angle_threshold_deg=10.0,
600         small_angle_crossing_count=int(small_angle),
601         small_angle_5deg_threshold_deg=5.0,
602         small_angle_5deg_crossing_count=int(small_angle_5),
```

`four_side_1024/v3/metrics.py:1427-1432` (D4):
```python
1427     statistics["small_angle_threshold_deg"] = 10.0
1428     statistics["small_angle_crossing_count"] = merged.get(
1429         "small_angle_crossing_count")
1430     statistics["small_angle_5deg_threshold_deg"] = 5.0
1431     statistics["small_angle_5deg_crossing_count"] = (pair_audit or {}).get(
1432         "small_angle_5deg_crossing_count")
```

`four_side_1024/fslw/validate_fslw.py:2491-2499` and `2512-2515` (D6) — metadata only, **not** a gate:
```python
2491     if policy == "strict":
2492         policy_block.update({
2493             "centerline_clearance_limit_mm": clearance - STRICT_LIMIT_TOL,
2494             "crossing_min_angle_deg": MIN_CROSS_ANGLE_DEG,
2495             "crossing_max_half_window_mm": STRICT_MAX_HALF_WINDOW,
2496             "crossing_solve_tolerance_mm": STRICT_SOLVE_TOL,
2497             "crossing_group_tolerance_mm": STRICT_GROUP_TOL,
2498             "crossing_extra_margin_mm": 2.0 * sagitta,
2499         })
...
2513             "min_cross_angle_deg": MIN_CROSS_ANGLE_DEG,
2514             "max_half_window_mm": STRICT_MAX_HALF_WINDOW,
```

`four_side_1024/fanout1024/native3d/crossing_intervals.py:87-88`, `520-539`, `1295` (D7):
```python
 87 MIN_CROSS_ANGLE_DEG = 5.0            # strict-D56 minimum genuine crossing angle
 88 MIN_SINE = math.sin(math.radians(MIN_CROSS_ANGLE_DEG))
...
520     all_s = []
521     transverse_s = []
...
533         for record in unique:
534             all_s.append(record[0])
535             if record[3] >= min_sine:
536                 transverse_s.append(record[0])
...
1295                   min_cross_angle_deg=MIN_CROSS_ANGLE_DEG,
```

`four_side_1024/fanout1024/native3d/arc_crossing_analysis.py:74-75` and `807-814` (D8):
```python
 74 MIN_CROSS_ANGLE_DEG = 5.0
 75 MIN_SINE = math.sin(math.radians(MIN_CROSS_ANGLE_DEG))
...
807     unique = _dedupe_incidences(incidences)
808     transverse = [item for item in unique if item['sine'] >= cache.min_sine]
809     tangent = [item for item in unique if item['sine'] < cache.min_sine]
810     return dict(transverse=len(transverse), tangent=len(tangent),
811                 overlap_contacts=len(overlaps),
812                 distinct_partners=int(len({item['partner'] for item in transverse})),
813                 distinct_points=int(len(unique)),
814                 incidences=unique)
```

`four_side_1024/manual_u640/verify.py:2053-2058` (D9):
```python
2053     ctx.check('crossings_legal_angle_ge_5deg',
2054               ctx.min_cross_angle is None
2055               or ctx.min_cross_angle >= float(C.MIN_CROSS_ANGLE_DEG) - 1e-9,
2056               dict(min_cross_angle_deg=ctx.min_cross_angle,
2057                    required_deg=float(C.MIN_CROSS_ANGLE_DEG),
2058                    crossings=len(all_crossing_items)))
```

`four_side_1024/abcd/run.py:50-57` (E2) and `140` — ABCD sensitivity round:
```python
 50 def router_config(args, policy='strict'):
 51     cfg = dict(width=base_config()['width_mm'],
 52                gap=base_config()['edge_gap_mm'],
 53                sagitta=base_config()['sagitta_mm'],
 54                min_radius_mm=base_config()['min_radius_mm'],
 55                min_cross_angle_deg=5.0,
 56                crossing_policy=policy,
 57                candidate_budget_per_route=args.candidate_budget,
```

`four_side_1024/manual_u640/config.py:33-38` (E3):
```python
 33 WIDTH_MM = 0.050
 34 EDGE_GAP_MM = 0.030
 35 CLEARANCE_MM = WIDTH_MM + EDGE_GAP_MM          # 0.080 mm centreline clearance
 36 RADIUS_MM = 15.0                                # R15 process profile
 37 MIN_CROSS_ANGLE_DEG = 5.0
 38 SAGITTA_MM = 0.0005
```

`four_side_1024/conflicts.py:457-465` (E6) — numerical tangency epsilon, not the 5 deg rule:
```python
457                     for pt in points:
458                         ta,tb = a.parameter(pt),b.parameter(pt)
459                         tangent_a,tangent_b = a.tangent(ta),b.tangent(tb)
460                         sine = min(1.,abs(_cross(tangent_a,tangent_b)))
461                         sa,sb = route.offsets[i]+ta*a.length,other.offsets[j]+tb*b.length
462                         is_endpoint = min(sa,route.length-sa,sb,other.length-sb) < 1e-7
463                         if sine < 1e-7 or is_endpoint:
464                             touch = True
465                             continue
```

`four_side_1024/d56/index.py:972-985` (E7/F2) — the **legacy** policy's near-zero-angle exemption:
```python
972         for point in points:
973             ta = prim.parameter(point)
974             tb = theirs.parameter(point)
975             tangent_a = prim.tangent(ta)
976             tangent_b = theirs.tangent(tb)
977             sine = min(1.0, abs(tangent_a[0] * tangent_b[1] - tangent_a[1] * tangent_b[0]))
978             sa = prepared.offsets[i] + ta * prim.length
979             sb = other.offsets[j] + tb * theirs.length
980             if sine < 1e-7 or min(sa, prepared.length - sa,
981                                   sb, other.length - sb) < 1e-7:
982                 result.reason = 'touch'
```

`four_side_1024/fslw/validate_fslw.py:1693-1699` (F1) — the **legacy** policy's window formula
(`clearance/sin(angle)`, no angle floor beyond `SINE_TOL = 1e-7`):
```python
1693     intervals_a = []
1694     intervals_b = []
1695     for crossing in crossings:
1696         half = clearance / crossing["sine"] + 2.0 * sagitta
1697         crossing["half"] = half
1698         intervals_a.append((crossing["sa"] - half, crossing["sa"] + half))
1699         intervals_b.append((crossing["sb"] - half, crossing["sb"] + half))
```

`experiments/COLD_START_20_HEIGHT_1024/_source_backup/.../independent_metrics.py:71`,
`.../archive/code/crossing_intervals.py:87`, `.../backups/native3d_def/*/blocker_analysis.py:285`,
`scratch/**`, `outputs/**` (E5) are byte-level copies of the files above and are not imported by any
G5 code path.

---

## 4. Which implementation is authoritative — proof

### 4.1 Validator: `validate_fslw._evaluate_pair_strict` is the only crossing predicate

* `validate_native3d.check_crossings()` — 7 lines, calls `V21.check_crossings` and only relabels the
  rule text:
  ```python
  def check_crossings(routed, planes, assignment_by_id):
      started = time.time()
      violations, details = V21.check_crossings(routed, planes, assignment_by_id)
      details = dict(details)
      details['crossing_rule'] = (
          'every flat part grouped by physical z (all heights, interface leads '
          'merged); fslw strict D56 audit per height; reused '
          'validate21.check_crossings')
  ```
* `validate21.check_crossings()` — groups flats by physical z, prepares them with
  `validate_fslw.prepare_route`, and calls
  `validate_fslw.audit_route_pairs(prepared, clearance=D56_CLEARANCE_MM, sagitta=SAGITTA_MM, policy='strict')`
  (lines 1746-1748).
* `validate_fslw.audit_route_pairs()` → `evaluate_pair()` → `_evaluate_pair_strict()`, gate at line
  1406.
* Independence is documented in the module itself (`validate_fslw.py:8-9`): *"Every predicate the
  verdict depends on is re-derived here; no router code is imported"*, and lines 35-37: *"`d56/index.py`,
  `d56/validate_d56.py`, `d56/conflicts.py` and every `fslw` router module are never imported."*

**⇒ Authoritative validator test = `four_side_1024.fslw.validate_fslw._evaluate_pair_strict`,
constant `STRICT_SINE_MIN` (line 118).**

### 4.2 Search: `d56.index.D56Index._evaluate_strict` is the only crossing predicate

* `l3d.world.World.check_route()` (used by `RouteWorld.check_3d`, `RouteWorld.validate_all`,
  `batch_evaluate`) calls `PlaneWorld.evaluate()` → `D56Index.evaluate()` (strict) → line 677 gate.
* `world_adapter.RouteWorld` and `g4.joint_world.JointWorld` never re-implement the crossing test;
  they consume `D56Index` (`WA.new_index()` for counting, `l3d.world.PlaneWorld` for legality).
* `nonc4.cross_router` inherits `layer2d.Router.index` (`D56Index`, strict).

**⇒ Authoritative search-side test = `four_side_1024.d56.index.D56Index._evaluate_strict`,
per-instance `min_sine` fed by `fslw.config.MIN_CROSS_ANGLE_DEG` (legality) and by a literal `5.0`
(counting).**

### 4.3 They are two independent implementations that currently agree

They are not the same code path: different modules, different primitive classes, different scalar
helpers, different bisection implementations (`_strict_band_edge` vs `_window_edge`), and duplicated
constants (`STRICT_SINE_MIN` vs `min_cross_angle_deg`). A synthetic probe
(`probe/angle_window_probe.py`, output `probe/angle_window_probe.json`) evaluates two straight
centrelines crossing at `theta` with **both** engines at `theta_min = 5 deg` and `45 deg`:

| theta | validator solved half-width | validator @5 deg | validator @45 deg | D56Index @5 deg | D56Index @45 deg |
|---|---|---|---|---|---|
| 5 deg | 0.918902 mm | valid | **tangent_touch** | valid (1 crossing) | **invalid / tangent_touch (0 crossings)** |
| 10 deg | 0.461707 mm | valid | **tangent_touch** | valid (1) | **invalid / tangent_touch (0)** |
| 30 deg | 0.161008 mm | valid | **tangent_touch** | valid (1) | **invalid / tangent_touch (0)** |
| 45 deg | 0.114137 mm | valid | valid | valid (1) | valid (1) |
| 90 deg | 0.081000 mm | valid | valid | valid (1) | valid (1) |

Both engines agree on every row, and both flip validity at exactly 45 deg — **but only because each
was given the new number separately** (the probe sets `validate_fslw.STRICT_SINE_MIN` in-process and
passes `min_cross_angle_deg=45` to `D56Index`). Editing only one of them would silently desynchronise
the search and the final verdict.

---

## 5. Task 3 — the `theta_min = 45 deg` change surface

### 5.1 What is configurable vs hard-coded

**Already configurable (one edit propagates):**

| knob | file:line | feeds |
|---|---|---|
| `fslw.config.MIN_CROSS_ANGLE_DEG` | `four_side_1024/fslw/config.py:23` | `l3d/world.py:45` (candidate legality + global conflict check), `fslw/search.py:26`, `fslw/run.py:50`, `v2opt/core.py:41`, `fsd25d/config25d.py:57` → `world25d.py:155`, `router25d.py:451`, `l3d/common.py:143`, `native3d/crossing_cache.py:45`, `native3d/blocker_analysis.py:285`, `fanout1024/fanout.py:644`, `manual_u640/u_geometry.py:90`, `manual_u640/verify.py:2055`, `fslw/metrics.py:267`, `fslw/config.process_record()` |

**Hard-coded `5.0` / `sin(radians(5.0))` that must be edited individually** (rows 1-6 are on the live
G5 path and **must** change; rows 7-12 belong to other rounds or are optional — change them only if
those rounds are re-run, so that no future audit re-introduces a 5 deg authority):

| # | file:line | literal | consequence if left at 5 deg |
|---|---|---|---|
| 1 | `four_side_1024/fslw/validate_fslw.py:118` | `STRICT_SINE_MIN = math.sin(math.radians(5.0))` | **final validator would accept 5–45 deg crossings** → search/validator disagreement, frozen-style `validation_pass=True` for an illegal G5 solution |
| 2 | `four_side_1024/fanout1024/xyzrouter/world_adapter.py:41` | `min_cross_angle_deg=5.0` | G4 `RouteWorld`/`JointWorld` crossing counts + per-plane bookkeeping use the old rule; crossing objective and `crossing_stats.json` become inconsistent with legality |
| 3 | `four_side_1024/fanout1024/layer2d.py:1387` | `min_cross_angle_deg=5.0` | 2D layer router (and `nonc4`/`native3d` initial bodies) keeps producing 5–45 deg crossings that the final validator will reject |
| 4 | `four_side_1024/fanout1024/native3d/crossing_intervals.py:87-88` | `MIN_CROSS_ANGLE_DEG = 5.0` + `MIN_SINE` | candidate height ranking predicts "legal transverse" for shallow crossings → planner optimises the wrong objective |
| 5 | `four_side_1024/fanout1024/native3d/arc_crossing_analysis.py:74-75` | `MIN_CROSS_ANGLE_DEG = 5.0` + `MIN_SINE` | arc-crossing analysis buckets 5–45 deg as "transverse" |
| 6 | `four_side_1024/fanout1024/xyzrouter/g4/independent_metrics.py:71` | `MIN_CROSS_ANGLE_DEG = 5.0` | third independent re-derivation reports 5–45 deg crossings as legal → false discrepancy alarms in the G4/G5 audit |
| 7 | `four_side_1024/d56/search.py:22` | `min_cross_angle_deg=5.0` in `DEFAULT_CFG` | only the legacy d56 round (fslw/v3 override it); change for hygiene |
| 8 | `four_side_1024/d56/validate_d56.py:82` | `STRICT_SINE_MIN = math.sin(math.radians(5.0))` | d56-round validator (its own authority) — change only if that round is re-run |
| 9 | `four_side_1024/v3/validate_v3.py:137` | `STRICT_SINE_MIN = math.sin(math.radians(5.0))` | v3-round validator — same |
| 10 | `four_side_1024/manual_u640/config.py:37` | `MIN_CROSS_ANGLE_DEG = 5.0` | manual-U round has its own copy — same |
| 11 | `four_side_1024/abcd/run.py:55,140` | `min_cross_angle_deg=5.0` | ABCD sensitivity round — unrelated |
| 12 | `outputs/.../s03_corner_connectors.py:58`, `s04_structural.py:56` | `MIN_CROSS_ANGLE_DEG = 5.0` | one-off analysis scripts — unrelated |

**Reporting thresholds that do not gate anything but should be re-labelled:**

| file:line | literal | action |
|---|---|---|
| `four_side_1024/fslw/validate_fslw.py:70` (+ uses at 1903, 1950, 2486, 2562) | `CROSSING_SMALL_ANGLE_DEG = 10.0` | set to 45.0 or rename to `CROSSING_SMALL_ANGLE_DEG = 45.0` so `small_angle_crossing_count` means "crossings below the legal minimum" |
| `four_side_1024/fslw/metrics.py:583,601,1888` | `5.0`, `"small_angle_5deg_*"` | rename to `small_angle_45deg_*` / value 45.0 |
| `four_side_1024/v3/metrics.py:1430` | `5.0` | same (v3 round) |
| `four_side_1024/d56/validate_d56.py:2198` | `"crossing_min_angle_deg": 5.0` | same (d56 round) |
| `four_side_1024/fanout1024/xyzrouter/g4/contract_audit.py:83,90,91` | `'D56 minimum genuine crossing angle 5 deg'`, `'strict crossing sine threshold sin(5 deg)'`, `'D56 5 deg lower bound'` | text-only pins (regex `^MIN_CROSS_ANGLE_DEG\s*=` / `^STRICT_SINE_MIN\s*=` still matches `45.0`), but the descriptions become false — update the labels |
| frozen `process_rules.json` `"same_layer_2d_rules"` | `"original strict D56 index ...; legal transverse crossings preserved"` | records no number, but G5 run artefacts should record `theta_min = 45 deg` explicitly |

### 5.2 Does the strict-D56 window logic get harder at 45 deg?

The strict rule exempts, around each genuine crossing, the *minimal* arc length on each route over
which the centre line is still inside the 0.08 mm band of its crossing partner, plus `2*sagitta`, and
requires `>= 0.08 mm - 1e-7` everywhere else. The band edge is **solved from the real geometry**
(`_window_edge` / `_strict_band_edge`); the angle only enters as the initial probe
`guess = limit / sin(theta)`.

For two straight centrelines crossing at `theta`, two different distances are quoted in this project:

* **`c / sin(theta)`** — distance measured **along one of the routes** from the crossing point until
  its perpendicular distance to the partner line reaches `c = 0.08 mm`. This is the quantity the
  *window* needs (and the quantity the legacy formula `clearance/sin(angle)` uses).
* **`c / (2 sin(theta/2))`** — distance from the crossing point **along the angle bisector** at which
  the two lines are `c` apart (this is the formula quoted in the task brief). It agrees with
  `c/sin(theta)` to first order for small `theta` but differs at large `theta`.

Both are tabulated; the measured strict half-width from the probe is `c/sin(theta) + 2*sagitta`
(+ up to `STRICT_SEARCH_TOL = 1e-5` bisection slack):

| theta | `c/(2 sin(theta/2))` (bisector) | `c/sin(theta)` (along route) | legacy window half `c/sin + 2*sag` | **measured strict half-width** | 4 mm cap headroom |
|---:|---:|---:|---:|---:|---:|
| 5 deg | 0.917023 mm | 0.917897 mm | 0.918397 mm | **0.918902 mm** | 4.35x |
| 10 deg | 0.458949 mm | 0.460702 mm | 0.461202 mm | **0.461707 mm** | 8.66x |
| 30 deg | 0.154548 mm | 0.160000 mm | 0.160500 mm | **0.161008 mm** | 24.8x |
| 45 deg | 0.104525 mm | 0.113137 mm | 0.113637 mm | **0.114137 mm** | 35.0x |
| 90 deg | 0.056569 mm | 0.080000 mm | 0.080500 mm | **0.081000 mm** | 49.4x |

(The 0.0005 mm offset between "legacy window half" and "measured" is the `2*sagitta` margin plus the
`1e-5` solve tolerance; the strict solver targets `limit = c - 1e-7`.)

**Conclusions**

1. **The window shrinks monotonically with `theta`.** At 45 deg the exempt half-width is 0.114 mm,
   8x smaller than at 5 deg. Therefore the "outside the window the 0.08 mm clearance must hold" rule
   and the `<= 4 mm` cap both become **strictly easier**, not harder. Switching the constant does not
   silently tighten any other geometric requirement.
2. **A straight-line crossing can never violate the 4 mm cap** for any `theta >= 5 deg`: the cap can
   only bind if a route stays within 0.08 mm of its partner for more than 4 mm of arc length, which
   needs `sin(theta) < 0.08/4 = 0.02` (`theta < 1.15 deg`). The frozen 5 deg gate already excludes
   that, and 45 deg excludes it by 35x. The cap exists for **curved** primitives (an arc that runs
   alongside its partner keeps re-approaching it); those are the only cases that produce
   `crossing_window_excessive` (`d56/index.py:732-736`, `validate_fslw.py:1513-1516`).
3. **What actually changes is admissibility, not window shape.** Raising `theta_min` to 45 deg turns
   every `5 <= theta < 45 deg` crossing into a `tangent_touch` violation (both engines), i.e. those
   pairs must be re-routed / re-heighted. Geometry budgets (0.08 mm, 4 mm, 0.05 mm 3D, R15, 20
   heights) are untouched.
4. **Side effect to watch:** the rejection *reason* is still the string `tangent_touch`, and the
   `crossing_angle_histogram`/`small_angle_*` buckets still use 10 deg / 5 deg. For G5 diagnostics,
   add a distinct reason (`crossing_angle_below_min`) and move the reporting buckets to 45 deg;
   neither affects legality.

### 5.3 Impact on the frozen solution (measured)

From `experiments/COLD_START_20_HEIGHT_1024/10_best_valid/crossing_stats.json` (1283 events, 20
audited heights):

| angle bucket | events |
|---|---:|
| 5 – <10 deg | 17 |
| 10 – <15 | 61 |
| 15 – <20 | 31 |
| 20 – <25 | 24 |
| 25 – <30 | 28 |
| 30 – <35 | 37 |
| 35 – <40 | 55 |
| 40 – <45 | 51 |
| **45 – <50** | **214** |
| 50 – <60 | 57 |
| 60 – <75 | 514 |
| 75 – 90 | 194 |
| **total** | **1283** |

* min crossing angle in the frozen solution: **5.1538 deg** (the 5 deg gate is *barely* slack — no
  crossing is below it, and 17 events are within 5 deg of it).
* `>= 45 deg`: **979 events (76.3 %)** stay legal.
* `5 <= theta < 45 deg`: **304 events (23.7 %)** become violations under G5.
* consequence: max crossing count per route (17) and the 1221 crossing pairs cannot be preserved; the
  G5 round must remove 304 events by geometry (re-height / re-route), not by re-labelling them.

**Independent corroboration.** A separate, stdlib-only angle auditor written for this G5 round
(`experiments/G5_ANGLE45_NATIVE3D_20H_1024/00_baseline_audit/independent_angle_validator/`, no project
module imported) reports, on the same frozen file:
`total_crossings = 1283`, `unique_route_pairs = 1221`, `routes_with_crossings = 647`,
`max_crossings_per_route = 17`, `min_angle_deg = 5.153763467`, `n_lt_45 = 304`, `n_lt_5 = 0`,
`overlap_event_count = 0`, `endpoint_touch_count = 0`, `tangent_or_near_tangent_count = 0`,
`clearance_violation_count = 0`, `clearance_min_non_crossing_mm = 0.086853441`, and the verdict
`304 crossings below 45.000 deg`. Every number agrees with the analysis above and with the frozen
`validate_native3d` report (`min_non_crossing_centerline_mm = 0.086853441`,
`same_plane_crossings = 1283`).

### 5.4 Places that *count* crossings with the 5 deg rule and would still report a 5–45 deg crossing as legal

| # | module / function | what it would report | must change? |
|---|---|---|---|
| 1 | `four_side_1024/fanout1024/xyzrouter/g4/independent_metrics.py` → `_same_height_crossings` (line 1360 gate), `crossing_exemption_policy` (line 2078) | `allowed_crossing_count`, `illegal_crossing_count`, `crossing_angle_min/max`, `min_crossing_angle_deg: 5.0` | **yes** (or G4/G5 audit contradicts the validator) |
| 2 | `four_side_1024/fanout1024/native3d/crossing_intervals.py` → `target_intersections` (line 535), `_estimated_added/removed` (lines 923, 958) | `estimated_added`, `estimated_removed` crossing counts, "only transverse contacts (angle >= 5.0 deg) are counted as crossings" | **yes** (planner objective) |
| 3 | `four_side_1024/fanout1024/native3d/arc_crossing_analysis.py` → `TargetCrossingCache` (line 712), `transverse`/`tangent` split (808-809) | arc-crossing report (`transverse`, `tangent`, `distinct_partners`) | **yes** (report only, but would contradict the G5 numbers) |
| 4 | `four_side_1024/fanout1024/native3d/crossing_cache.py:42-46` (`FS.MIN_CROSS_ANGLE_DEG`) → `xyzrouter/optimizer.py:213-248` `crossing_stats()` | `crossing_stats.json` (`totals`, `planes`, `crossing_events`, `angle_deg`) | follows A8 automatically |
| 5 | `four_side_1024/fanout1024/nonc4/crossings.py:106-129` (`audit_route_pairs(policy='strict')`) | `crossing_stats` of the non-C4 stage | follows A2 automatically |
| 6 | `four_side_1024/fslw/metrics.py:576-602, 1882-1890` | `small_angle_5deg_crossing_count`, histogram | statistic only; re-label |
| 7 | `four_side_1024/fslw/validate_fslw.py:1899-1908, 1950` | `small_angle_threshold_deg=10`, `small_angle_crossing_count`, `crossing_angle_histogram` | statistic only; re-label |
| 8 | `four_side_1024/manual_u640/verify.py:2053-2058` | `crossings_legal_angle_ge_5deg` check | follows A8; rename |
| 9 | `four_side_1024/fanout1024/xyzrouter/g4/contract_audit.py:83,90,91` + `check_revalidation` (285-310) | contract labels + crossing-count revalidation | labels must change; counts are recomputed from the validator so they follow A2 |

Two *consumers* are safe by construction because they call the validator rather than re-implementing
it: `nonc4/crossings.py` and `reheight21/validate21.check_crossings` (and therefore
`native3d.validate_native3d.check_crossings`).

---

## 6. Consistency requirements for G5 (checklist)

1. **Search legality** (`d56.index._evaluate_strict`, fed by `l3d/world.py:45` ← `config.py:23`) and
   **search counting** (`world_adapter.new_index()`, `layer2d.py:1387`) must both be 45 deg, otherwise
   the search optimises a crossing count that its own legality test does not believe.
2. **Global conflict check** (`RouteWorld.validate_all` → `l3d.world.World.check_route`) is the same
   code as (1); no separate edit.
3. **Final validator** (`validate_fslw.STRICT_SINE_MIN`) must be 45 deg — it is the *only* gate that
   can reject a 5–45 deg crossing at verdict time.
4. **The 45 deg value must be written in exactly one place per implementation**; recommended:
   `fslw/config.MIN_CROSS_ANGLE_DEG = 45.0` and
   `validate_fslw.STRICT_SINE_MIN = math.sin(math.radians(45.0))`, with
   `world_adapter.new_index()` / `layer2d.py` / `crossing_intervals.py` / `arc_crossing_analysis.py` /
   `independent_metrics.py` changed to *read* `C.MIN_CROSS_ANGLE_DEG` instead of literals. That removes
   four of the five duplicated literals permanently and makes the validator the only remaining
   duplicate (deliberate, since it must stay independent).
5. Add a regression test that asserts
   `sin(radians(config.MIN_CROSS_ANGLE_DEG)) == validate_fslw.STRICT_SINE_MIN` — this is the cheapest
   possible guard against the two implementations drifting apart.
6. Re-validate the frozen solution **before** re-running G5 to confirm the harness: it must still
   pass at 5 deg (see `VALIDATOR_RUNBOOK.md`; reproduced verdict: exit 0, 0 violations, 1283/1221).
   Then G5 runs must show `same_plane_crossing_violations == 0` **and** `crossing_angle_min >= 45`.

---

## 7. Evidence index

| artefact | path |
|---|---|
| end-to-end validator chain (delegation proof) | §2.1, §4.1 |
| search chain (legality vs counting) | §2.2, §4.2 |
| synthetic angle/window probe (both engines, 5/10/30/45/90 deg) | `probe/angle_window_probe.py`, `probe/angle_window_probe.json` |
| frozen validator re-run on a scratch copy (pass) | `probe/run_dir/validation.json`, `probe/validate_native3d_run.log`, `VALIDATOR_RUNBOOK.md` |
| frozen angle distribution (979 / 304 split) | `experiments/COLD_START_20_HEIGHT_1024/10_best_valid/crossing_stats.json` (`crossing_events[].angle_deg`) |
| frozen verdict of record | `experiments/COLD_START_20_HEIGHT_1024/10_best_valid/validation.json` (`schema=native3d_validation_v1`, `exit_code=0`) |
