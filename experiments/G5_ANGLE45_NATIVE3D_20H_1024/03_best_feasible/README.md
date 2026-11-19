# 03_best_feasible — intentionally empty

This directory is reserved for a **fully legal** G5 solution, i.e. one that
satisfies all of:

* 1024/1024 routed, 20 physical heights, R15, strict D56, 50 um true-3D
  clearance, glass envelope, ports/assignment unchanged (frozen validator A),
* **zero genuine same-height crossings below 45 deg** (independent validator B),
* no overlaps / coincident stretches / illegal self-intersections.

The G5 round did **not** reach that state (134 sub-45 deg crossings remain; see
`../03_best_partial` and `../07_reports/G5_REPORT.md`), so nothing is put
here. A partial result is never allowed to masquerade as feasible.
