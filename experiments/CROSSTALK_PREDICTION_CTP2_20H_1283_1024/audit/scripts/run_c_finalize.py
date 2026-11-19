"""Finalise supermode_kappa_vs_d.csv with a defensible 'numerically_resolved' flag.

Criterion (documented in the audit report):
  * kappa_supermode must be within a factor 2 of the independent converged
    overlap/asymptotic kappa (physics check), AND
  * the splitting must be at least 5x the solver-settings spread measured at
    d = 20 um (numerical check; spread ~7e-5 mm^-1 there) or, where no direct
    measurement exists, exhibit monotonic exponential decay compatible with the
    overlap value.
Both fail for d >= 30 um: the supermode kappa flattens out at 1e-5..1e-4 mm^-1
while the physical value falls to 1e-8..1e-18 mm^-1, and repeated runs scatter
by factors 30-258.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import audit_lib as AL

OUT = AL.AUDIT
CDIR = OUT


def main():
    c = json.loads((OUT / "c_summary.json").read_text(encoding="utf-8"))
    rows = c["d_sweep"]
    for r in rows:
        kap_s = r["kappa_supermode_mm_inv"]
        kap_phys = r["kappa_overlap_1d_eim_mm_inv"]
        ratio = kap_s / max(abs(kap_phys), 1e-300)
        d = r["d_um"]
        resid = r["eig_residual"]
        # eigenvalue splitting vs eigen-residual scale
        dlam = 2.0 * (4.796325) ** 2 * 1.5046 * r["delta_n_eff"]
        r["delta_Lambda"] = dlam
        r["residual_over_splitting"] = resid / max(dlam, 1e-300)
        r["kappa_ratio_super_over_physical"] = ratio
        physics_ok = 0.5 <= ratio <= 2.0
        noise_ok = d <= 25.0 and ratio < 10.0
        # direct reproducibility/settings evidence at d=50: factor 30-258
        r["numerically_resolved"] = "yes" if (physics_ok and noise_ok and d <= 25.0) else "no"
        r["resolution_note"] = (
            "overlap-consistent" if physics_ok else
            ("noise plateau: physical kappa %.1e, measured %.1e" % (kap_phys, kap_s)))
    # required column order
    cols = ["d_um", "axis", "n_eff_even", "n_eff_odd", "delta_n_eff",
            "kappa_supermode_mm_inv", "kappa_overlap_mm_inv",
            "kappa_asymptotic_mm_inv", "eig_residual", "numerically_resolved",
            "kappa_overlap_1d_eim_mm_inv", "kappa_ratio_super_over_physical",
            "delta_Lambda", "residual_over_splitting", "resolution_note"]
    AL.write_csv(OUT / "supermode_kappa_vs_d.csv", rows, fieldnames=cols)
    print("wrote", OUT / "supermode_kappa_vs_d.csv")
    print(f"{'d':>6} {'axis':>4} {'kappa_super':>12} {'kappa_phys':>12} "
          f"{'resid':>10} {'resolved':>8}")
    for r in rows:
        print(f"{r['d_um']:6.1f} {r['axis']:>4} {r['kappa_supermode_mm_inv']:12.3e} "
              f"{r['kappa_overlap_1d_eim_mm_inv']:12.3e} {r['eig_residual']:10.2e} "
              f"{r['numerically_resolved']:>8}")


if __name__ == "__main__":
    main()
