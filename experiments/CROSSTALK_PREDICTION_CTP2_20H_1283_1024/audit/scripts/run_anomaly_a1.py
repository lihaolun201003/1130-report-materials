"""Anomaly A step 1: reproduce the legacy crossing curve with fields kept.

Runs the legacy solve_crossing with the EXACT settings used by scripts/run_e3.py
(d_port=10 um, pml=5 um, max_unknowns=420k, grid start 0.15 um) and caches the
raw fields, then prints what the legacy port projection produces.  A full
independent analysis is done in run_anomaly_a2.py.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import audit_lib as AL

ANGLES = [float(a) for a in sys.argv[1:]] or [90.0, 10.0, 5.0]


def main():
    opt, eim = AL.beam()
    print(f"EIM: n_slab={eim.n_slab:.9f} n_eff2d={eim.n_eff:.9f} "
          f"beta2d={eim.beta2d:.6f}/um k0={eim.k0:.6f}/um")
    rows = []
    for th in ANGLES:
        t0 = time.time()
        d, path = AL.run_crossing_cached(opt, eim, th, grid=0.15, d_port=10.0,
                                         pml=5.0, strength=3.0, force=False)
        h = float(d["grid"])
        print(f"\ntheta={th:5.1f}  grid={h:.4f}  domain={np.asarray(d['domain'])}"
              f"  N={int(d['unknowns'])}  runtime={float(d['runtime']):.1f}s")
        print(f"  legacy: T_through={float(d['T_through']):.9f} "
              f"T_cross={float(d['T_cross']):.4e} ({AL.db(float(d['T_cross'])):.2f} dB) "
              f"n_guided={int(d['n_guided'])} beta_disc={float(d['beta_disc']):.6f} "
              f"n_eff_disc={float(d['n_eff_disc']):.6f}")
        # legacy incident mode implied beta vs physical sqrt(Lambda)
        k0 = eim.k0
        lam = np.sqrt(max(float(d["n_eff_disc"]) ** 2 * k0 ** 2, 0))
        print(f"  discrete beta/k0={float(d['beta_disc'])/k0:.6f}  "
              f"(physical sqrt(Lam)/k0={lam/k0:.6f}) -> dispersion inflation "
              f"{(float(d['beta_disc'])/k0-1)*100:+.3f}%")
        rows.append({k: (float(d[k]) if np.ndim(d[k]) == 0 else np.asarray(d[k]).tolist())
                     for k in ("theta", "grid", "T_through", "T_cross", "T_loss",
                               "energy_error", "n_slab", "n_eff_disc", "beta_disc",
                               "n_guided", "domain", "unknowns", "runtime")})
        print(f"  cached at {path.name}")
    AL.jdump(AL.AUDIT / "a1_baseline_runs.json", rows)


if __name__ == "__main__":
    main()
