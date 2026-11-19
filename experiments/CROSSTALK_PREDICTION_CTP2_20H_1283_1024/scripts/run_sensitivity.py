"""Parameter sensitivity of the *local crossing model* and of kappa.

The specification asks for a sensitivity study over lambda = 1310/1550 nm,
Delta n = 0.0045/0.0065/0.008, core width 6/9/12 um, core height 7/9/11 um and
step/graded profiles.  Modes and kappa are already produced by
``run_v1_modes.py`` / ``run_v2_coupling.py``; here the crossing crosstalk itself
is recomputed for every preset (BPM where it is valid, Born for the asymptotic
large-angle part).
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

from ctp2 import bpm as B, coupling as C, crossing as X, optics as O   # noqa: E402
from ctp2.params import OUT_COUPLING, REF, SENSITIVITY_PRESETS        # noqa: E402


def db(x):
    return 10.0 * math.log10(max(float(x), 1e-300))


def main() -> None:
    t0 = time.time()
    rows = []
    for opt in SENSITIVITY_PRESETS:
        eim = O.build_eim(opt)
        kmodel, _ = C.build_kappa_model(opt, separations=(9., 12., 15., 20., 24.))
        rec = {"parameter_set": opt.label, "wavelength_nm": opt.wavelength_nm,
               "delta_n": opt.delta_n, "core_width_um": opt.core_w_um,
               "core_height_um": opt.core_h_um, "profile": opt.profile,
               "eim_n_slab": eim.n_slab, "eim_n_eff": eim.n_eff,
               "gamma_per_um": eim.gamma_um,
               "kappa_15um_mm_inv": float(kmodel.kappa(15.0)),
               "kappa_30um_mm_inv": float(kmodel.kappa(30.0)),
               "kappa_50um_mm_inv": float(kmodel.kappa(50.0))}
        for th in (2.0, 5.0, 7.5, 10.0):
            r = B.run_crossing_2d(eim, th, port_separation_um=60.0,
                                  dx_um=0.12, dz_um=0.4)
            rec[f"XT_{th:g}deg_db"] = db(r.T_cross)
            rec[f"Tthrough_{th:g}deg_db"] = db(r.T_through)
        for th in (15.0, 20.0, 30.0, 45.0, 60.0, 90.0):
            b = X.born_crossing_2d(eim, th)
            rec[f"XT_{th:g}deg_db"] = b["T_cross_born_db"]
        rows.append(rec)
        print(f"{opt.label:16s} gamma={eim.gamma_um:.4f} "
              f"k50={kmodel.kappa(50.0):.3e} "
              f"XT5={rec['XT_5deg_db']:.1f} XT10={rec['XT_10deg_db']:.1f} "
              f"XT20={rec['XT_20deg_db']:.1f} dB  [{time.time()-t0:.0f}s]",
              flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(OUT_COUPLING / "sensitivity_crossing.csv", index=False)
    (OUT_COUPLING / "sensitivity_summary.json").write_text(
        json.dumps(df.to_dict("records"), indent=1), encoding="utf-8")
    print(df.to_string(index=False), flush=True)


if __name__ == "__main__":
    main()

