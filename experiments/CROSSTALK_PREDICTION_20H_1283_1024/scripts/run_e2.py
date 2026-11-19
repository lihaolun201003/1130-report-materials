"""E2: single-waveguide scalar mode analysis + numerical convergence."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from src.config import (CONFIG, EXPERIMENT_ROOT, parameter_sets,
                        reference_optics)
from src.dataio import write_csv, write_json
from src.modes import (convergence_rows, effective_index_model, mode_rows,
                       solve_modes)


def main() -> int:
    t0 = time.time()
    out = EXPERIMENT_ROOT / "outputs" / "optical"
    opt = reference_optics()
    sol = solve_modes(opt)
    g = sol.guided()
    print(f"[E2] reference: n_guided={g.n_guided} n_eff={np.round(g.n_eff, 6)}")

    rows = mode_rows(sol, "REF")
    conv = convergence_rows(opt, "REF")
    # parameter sweep of the guided-mode count
    sweep_rows = []
    for ps in parameter_sets():
        s = solve_modes(ps, domain_um=CONFIG["mode_solver"]["domain_um"],
                        grid_um=CONFIG["mode_solver"]["grid_um"])
        gg = s.guided()
        sweep_rows.append({
            "parameter_set": ps["label"],
            "wavelength_nm": ps["wavelength_nm"],
            "delta_n": ps["delta_n"],
            "core_width_um": ps["core_width_um"],
            "core_height_um": ps["core_height_um"],
            "profile": ps["profile"],
            "n_guided": gg.n_guided,
            "n_eff_fund": float(gg.n_eff[0]) if len(gg.n_eff) else float("nan"),
            "confinement_fund": float(gg.confinement(0)) if len(gg.n_eff) else float("nan"),
            "birefringence_proxy_none": 1,
            "single_mode": int(gg.n_guided == 1),
        })
        print(f"      {ps['label']:14s} modes={gg.n_guided} "
              f"n_eff={gg.n_eff[0]:.6f}" if len(gg.n_eff) else ps["label"])

    eim = effective_index_model(opt)
    e2 = {
        "reference": {
            "n_eff": [float(x) for x in g.n_eff],
            "beta_per_um": [float(x) for x in g.beta],
            "n_guided": int(g.n_guided),
            "single_mode": bool(g.n_guided == 1),
            "confinement": [float(g.confinement(i)) for i in range(len(g.n_eff))],
            "domain_um": sol.domain_um,
            "grid_um": sol.grid_um,
            "n_clad": sol.n_clad,
            "n_core": sol.n_core,
            "eim_n_slab": float(eim.n_slab),
            "eim_n_eff": float(eim.n_eff),
            "eim_rel_error_vs_full": float((eim.n_eff - g.n_eff[0]) / g.n_eff[0]),
        },
        "convergence": conv,
        "sweep": sweep_rows,
        "equation": CONFIG["mode_solver"]["equation"],
        "approximation": "scalar weak-guidance (not a full-vector Maxwell solve)",
    }
    write_csv(out / "single_waveguide_modes.csv", rows)
    write_csv(out / "mode_convergence.csv", conv)
    write_csv(out / "mode_sweep.csv", sweep_rows)
    write_json(out / "e2_summary.json", e2)
    print(f"[E2] done in {time.time() - t0:.1f}s")

    # persist the reference mode field for later plots / coupling work
    np.savez_compressed(out / "mode_reference.npz",
                        x=sol.x, y=sol.y, fields=sol.fields,
                        n_eff=sol.n_eff, beta=sol.beta,
                        eim_s=eim.s, eim_phi=eim.phi,
                        eim_n_slab=eim.n_slab, eim_n_eff=eim.n_eff)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
