# 20-height planar multi-arc ON/OFF controlled ablation

Experiment root: `experiments/COLD_START_20_HEIGHT_1024/09_multi_arc_ablation/`
Controlled variable: **`enable_multi_arc` only**
(`four_side_1024/fanout1024/layer2d.py` `MULTI_ARC_POLICY` / `multi_arc_enabled`
/ `_LayerRouter._iter_candidates`, propagated to the joint router by
`xyzrouter/local_reroute.py`; env override `G4_ENABLE_MULTI_ARC`).
Everything else is identical: the same 20-height physical configuration, the
same 1024 authoritative connections, the same cold assignment, the same seeds
(0 / 1 / 2 as used by the cold-start routing loop), the same candidate budgets
(600 / 1200 / 1800), the same independent validator and the same geometric
constraints (R15 = 15 mm, strict D56, true-3D >= 0.05 mm, glass envelope).

## Part A -- strict common-start ablation (pre-registered design): FEASIBLE START DOES NOT EXIST

The pre-registered strict design (the one used for the 21-height experiment in
`1130-report-materials`) requires the ON and OFF arms to start from the **same
converted geometry**: take the accepted 20-height G3 legal optimum (1395
crossings, routes SHA256 `a6aa6997...`) and convert every planar multi-arc body
into a legal single-arc-equivalent body (`run_multiarc convert`, a deterministic
minimum-delta conversion using the frozen `JointWorld.plan_candidates(mode='clean')`).

Result (`common_start_off/conversion_report.json`, `START.json`, `ABORTED_OFF_INFEASIBLE.json`):

| quantity | value |
|---|---:|
| common start (G3 legal optimum) | 1395 crossings, 213 routes with planar multi-arc bodies |
| routes converted to an OFF-legal body | 212 / 213 |
| **residual multi-arc routes** | **1** (route id 456) |
| crossings after conversion | 4559 (**+3164**, conversion cost, measured on the same route set) |
| policy leaks / illegal converted routes | 0 |
| validator on converted start | PASS (fresh 20H process, 0 violations) |

The conversion is deterministic and was retried with the maximum-route debug
setting; route 456 has no OFF-legal replacement body inside the current
20-height table (one fewer Z2 body plane than the 21-height model removed the
escape height this route needs).  Per the **pre-registered OFF-feasibility
rule**, a residual OFF arm is *not* diluted into the comparison: the strict
common-start B comparison is **declared infeasible for 20 heights** and no ON/OFF
arm pair is fabricated from it.  This is a geometric finding about the 20-height
table, not a validation failure.

*Historical 21-height reference (frozen archive, not a 20H result):* the strict
design was feasible there; ON 2203 vs OFF 3601 mean crossings (-1398), with
conversion delta 1322 -> 3967 (+2645).

## Part B -- cold-start ON/OFF ablation (executed, fully controlled)

Because Part A has no common start, the same ON/OFF question is answered at the
**cold-start stage**, where a mathematically identical common start exists for
free: both arms start from the *same* deterministic 20-height assignment
(`02_annealing/cold_assignment_20h/assignment_1024.csv`) and run the identical
`run_initial` pipeline (fanout -> strict-D56 planar routing -> 3D assembly ->
joint repair), differing **only** in `G4_ENABLE_MULTI_ARC`.

| arm | enable_multi_arc | routed | failed | crossings | crossing pairs | max/route | P95 | mean/route | min 3D (mm) | planar arc primitives | routes with >=2 planar arcs | validator |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| ON  | 1 (default) | 1024 | 0 | **12338** | 10133 | 83 | 68.0 | 38.56 | 0.086499 | 1700 | 646 | PASS (0 violations) |
| OFF | 0 (`G4_ENABLE_MULTI_ARC=0`) | 1024 | 0 | **14233** | 10637 | 82 | 70.05 | 44.48 | 0.100011 | 1960 | 636 | PASS (0 violations) |

* both arms are 1024/1024 with 0 failed routes and independent-validator PASS;
  neither arm is invalid, so the comparison is between two legal layouts
  obtained with identical effort;
* the only algorithmic factor is the planar multi-arc candidate family;
* **history is not attributed across arms**: the ON arm started from the same
  cold assignment as the OFF arm; the OFF arm is not charged with the ON arm's
  later G-stage reductions.

Reading: at the cold-start stage the multi-arc candidate family lowers the
same-plane crossing count by **1895 events (-13.3 %)** and the crossing-pair
count by 504 (-5.0 %) at equal legality and equal search budget, at a slightly
lower measured minimum 3D clearance (0.0865 mm vs 0.1000 mm -- both far above
the 0.05 mm requirement) and a slightly shorter total path (see
`final_metrics.json`).  The OFF arm compensates with more single-arc corner
fillets in total (1960 arc primitives) but fewer routes whose body is a genuine
multi-arc chain (636), which is the expected signature of the switch.

**This ablation is an independent mechanism check.  It does not and must not
change the main experiment, which keeps MultiArc ON for every reported solution.**

Reproduction
------------
```powershell
cd "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D"
$PY = ".venv\Scripts\python.exe"
# strict common-start attempt (Part A)
& $PY -m four_side_1024.fanout1024.coldstart20.run_multiarc start
& $PY -m four_side_1024.fanout1024.coldstart20.run_multiarc convert   # exits 4: OFF infeasible
# cold-start controlled arms (Part B)
& $PY -m four_side_1024.fanout1024.coldstart20.run_initial        # ON  -> 03_fanout_and_xy/run_initial_20h
$env:G4_ENABLE_MULTI_ARC = '0'
& $PY -m four_side_1024.fanout1024.coldstart20.run_initial --run-dir experiments\COLD_START_20_HEIGHT_1024\09_multi_arc_ablation\cold_start_off
& $PY -m four_side_1024.fanout1024.coldstart20.run_validate --run-dir experiments\COLD_START_20_HEIGHT_1024\09_multi_arc_ablation\cold_start_off
```
