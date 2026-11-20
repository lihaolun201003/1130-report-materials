# 03_best_partial — best pre-polish SA state (history trace, NOT the deliverable)

This directory keeps the best **simulated-annealing** state reached from the G5
warm start before the deterministic last-mile polish.  It is exactly the payload
consumed by `02_sa_runs/polish_1008/`:

* seed 1008 of `02_sa_runs/warm_B_v4` (12 seeds x 8 cycles, profile B = N1);
* N_bad = 4, D_theta = 55.745076 deg, crossings = 4454, length = 157233.701855 mm;
* routes SHA256 = `50d34cad2dd6772109ffe0cab4cf49f1edd5ced99da84c86bf5eeb2c55bb4362`;
* best move index 2831 inside the seed's 8-cycle run.

It is a *search* state, not an engineering-accepted solution: e.g. it still has
4 sub-45-degree crossings.  Acceptance (Validator A + the independent 45 deg
Validator B) was performed on the polished payload in `03_best_feasible/`.  This
state is kept for auditability of the reported chain
(`G6_REPORT.md` sections 5.2 and 5.3).
