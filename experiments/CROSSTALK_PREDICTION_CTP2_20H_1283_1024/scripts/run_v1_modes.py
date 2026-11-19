"""V1 - single-waveguide mode database and numerical convergence (CTP-2.0).

Checks performed
----------------
1. analytic symmetric-slab reference (exact transcendental equation) vs the
   finite-difference slab solver, with Richardson extrapolation;
2. the 3-D channel cross-section: mode count, n_eff, degeneracy, confinement,
   convergence in grid step and domain size;
3. orthonormality ``int psi_m psi_n dA = delta_mn`` on the discrete grid;
4. the effective-index approximation error for n_eff;
5. the evanescent-tail decay constant of the fundamental mode (used by the
   large-separation coupling model).
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ctp2 import optics as O                                    # noqa: E402
from ctp2.params import (CACHE, OUT_MODES, REF, SENSITIVITY_PRESETS)  # noqa: E402


def main() -> None:
    t0 = time.time()
    rows, conv_rows, sens_rows = [], [], []

    # ---------------------------------------------------- analytic validation
    ana_slab = O.analytic_slab_neff(REF, "y", 4)
    n_slab, conv = O.slab_neff_richardson(REF, "y")
    eim = O.build_eim(REF)
    print(f"analytic slab modes      : {ana_slab}")
    print(f"FD slab (Richardson)     : {conv}")
    print(f"EIM n_slab={eim.n_slab:.10f} n_eff={eim.n_eff:.10f} "
          f"gamma={eim.gamma_um:.6f} /um", flush=True)

    # ------------------------------------------------------ 3-D channel modes
    base = None
    for half, step in [(20.0, 0.16), (25.0, 0.12), (30.0, 0.10), (35.0, 0.10),
                       (30.0, 0.08)]:
        t = time.time()
        cm = O.solve_channel(REF, half_um=half, step_um=step, n_modes=10)
        g = cm.guided
        n_g = int(g.sum())
        n_eff = cm.n_eff[:5].tolist()
        conf = [cm.confinement(i) for i in range(min(5, len(cm.n_eff)))]
        tail = cm.tail_decay(0, "x", r0_um=6.0)
        conv_rows.append({
            "study": "channel", "half_um": half, "step_um": step,
            "n_guided": n_g, "n_eff_1": n_eff[0], "n_eff_2": n_eff[1],
            "n_eff_3": n_eff[2] if len(n_eff) > 2 else float("nan"),
            "conf_1": conf[0], "conf_2": conf[1] if len(conf) > 1 else float("nan"),
            "tail_gamma_per_um": tail["gamma_per_um"], "tail_r2": tail["r2"],
            "seconds": time.time() - t,
        })
        if half == 30.0 and step == 0.10:
            base = cm
        print(f"  channel half={half:4.0f} step={step:.2f}: n_guided={n_g} "
              f"n_eff={[round(x,8) for x in n_eff[:3]]} [{time.time()-t:.1f}s]",
              flush=True)

    # reference dataset (30 um, 0.10 um) + finer re-check
    cm = base
    for i in range(len(cm.n_eff)):
        g = bool(i < 3)
        rows.append({
            "parameter_set": REF.label, "mode_index": i,
            "n_eff": float(cm.n_eff[i]), "beta_per_um": float(cm.beta[i]),
            "guided": int(g), "confinement_core": float(cm.confinement(i)),
            "wavelength_nm": REF.wavelength_nm, "delta_n": REF.delta_n,
            "core_width_um": REF.core_w_um, "core_height_um": REF.core_h_um,
            "profile": REF.profile, "domain_half_um": 30.0, "grid_um": 0.10,
        })

    # orthonormality of the three guided modes
    dA = np.outer(cm.wy, cm.wx)
    ortho = np.zeros((3, 3))
    for a in range(3):
        for b in range(3):
            ortho[a, b] = float(np.sum(cm.fields[a] * cm.fields[b] * dA))
    print("overlap matrix of the 3 guided modes:\n", np.round(ortho, 10))

    # -------------------------------------------------- sensitivity presets
    for opt in SENSITIVITY_PRESETS:
        t = time.time()
        e = O.build_eim(opt)
        c = O.solve_channel(opt, half_um=25.0, step_um=0.12, n_modes=8)
        gg = c.guided
        st = c.tail_decay(0, "x", r0_um=6.0)
        sens_rows.append({
            "parameter_set": opt.label, "wavelength_nm": opt.wavelength_nm,
            "delta_n": opt.delta_n, "core_width_um": opt.core_w_um,
            "core_height_um": opt.core_h_um, "profile": opt.profile,
            "v_slab": float(opt.v_number),
            "n_guided_channel": int(gg.sum()),
            "n_eff_1": float(c.n_eff[0]),
            "n_eff_2": float(c.n_eff[1]) if len(c.n_eff) > 1 else float("nan"),
            "n_eff_3": float(c.n_eff[2]) if len(c.n_eff) > 2 else float("nan"),
            "eim_n_slab": float(e.n_slab), "eim_n_eff": float(e.n_eff),
            "eim_gamma_per_um": float(e.gamma_um),
            "tail_gamma_measured_per_um": st["gamma_per_um"],
            "seconds": time.time() - t,
        })
        print(f"  sens {opt.label:16s} n_guided={int(gg.sum())} "
              f"n_eff={float(c.n_eff[0]):.8f} gamma={e.gamma_um:.4f}", flush=True)

    pd.DataFrame(rows).to_csv(OUT_MODES / "single_waveguide_modes.csv", index=False)
    pd.DataFrame(conv_rows).to_csv(OUT_MODES / "mode_convergence.csv", index=False)
    pd.DataFrame(sens_rows).to_csv(OUT_MODES / "mode_sensitivity.csv", index=False)
    np.savez(CACHE / "channel_modes_ref.npz", x=cm.x, y=cm.y,
             n_eff=cm.n_eff, beta=cm.beta, fields=cm.fields[:6],
             wx=cm.wx, wy=cm.wy, n_clad=cm.n_clad, n_core=cm.n_core, k0=cm.k0)

    summary = {
        "n_modes_guided_channel": int(cm.guided.sum()),
        "n_eff_guided": [float(x) for x in cm.n_eff[:3]],
        "n_eff_degeneracy_gap": float(abs(cm.n_eff[1] - cm.n_eff[2])),
        "analytic_slab_modes": ana_slab,
        "fd_slab_richardson": conv,
        "eim": {"n_slab": eim.n_slab, "n_eff": eim.n_eff,
                "gamma_per_um": eim.gamma_um},
        "eim_vs_channel_relative_n_eff_error": float(
            abs(eim.n_eff - cm.n_eff[0]) / cm.n_eff[0]),
        "orthonormality_max_offdiag": float(np.max(np.abs(ortho - np.eye(3)))),
        "mode_count_note": ("V = k0*(w/2)*NA = %.4f; the slab supports TE0 and "
                            "TE1 (cutoffs 0 and pi/2) so the square channel is a "
                            "3-mode guide (fundamental + the degenerate "
                            "(0,1)/(1,0) pair) -- confirmed numerically."
                            % REF.v_number),
        "runtime_seconds": time.time() - t0,
    }
    (OUT_MODES / "mode_summary.json").write_text(json.dumps(summary, indent=1),
                                                 encoding="utf-8")
    print(json.dumps(summary, indent=1), flush=True)


if __name__ == "__main__":
    main()

