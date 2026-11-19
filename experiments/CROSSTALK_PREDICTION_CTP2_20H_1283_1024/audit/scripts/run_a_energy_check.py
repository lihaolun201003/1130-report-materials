"""Energy-balance verification for the corrected-solver crossing fields.

Net outward discrete flux of the TOTAL field through a box inside the PML must
be zero (A psi_tot = 0 in the physical region).  Together with the independent
guided-mode projection this pins down the radiation term:
    1 = T_through + R + T_cross + radiation.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import audit_lib as AL
import ctp2_corrected as CC

OUT = AL.AUDIT


def box_flux(field, h, i0, i1, j0, j1):
    fx_r = CC.exact_discrete_flux_x(field, i1, i1 + 1)
    fx_l = CC.exact_discrete_flux_x(field, i0, i0 - 1)
    fy_t = CC.exact_discrete_flux_y(field, j1, j1 + 1)
    fy_b = -CC.exact_discrete_flux_y(field, j0 - 1, j0)
    return {"right": fx_r, "left": fx_l, "top": fy_t, "bottom": fy_b,
            "sum": fx_r + fx_l + fy_t + fy_b}


def main():
    opt, eim = AL.beam()
    rows = []
    for th in (5.0, 10.0, 15.0, 20.0, 30.0, 45.0, 60.0, 90.0):
        try:
            d, p = CC.solve_corrected_cached(opt, th, grid=0.15, d_port=10.0,
                                             pml=5.0, strength=3.0,
                                             max_unknowns=420_000)
        except Exception as exc:
            print(th, "missing:", exc)
            continue
        x, y = np.asarray(d["x"]), np.asarray(d["y"])
        h = float(d["grid"])
        psi_s = np.asarray(d["psi_s"]); psi_inc = np.asarray(d["psi_inc"])
        b = d["bounds"]
        x_min, x_max, y_min, y_max = (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
        pml = float(d["pml"])
        i0 = int(round((x_min + pml + 2 * h - x[0]) / h))
        i1 = int(round((x_max - pml - 2 * h - x[0]) / h))
        j0 = int(round((y_min + pml + 2 * h - y[0]) / h))
        j1 = int(round((y_max - pml - 2 * h - y[0]) / h))
        tot = box_flux(psi_inc + psi_s, h, i0, i1, j0, j1)
        sca = box_flux(psi_s, h, i0, i1, j0, j1)
        F_inc = math.sin(float(d["beta_disc"]) * h) / h
        # forward/backward guided power from a plain 2-plane projection on the
        # (already validated) multi-mode analyser is in a2 results; here just flux
        rows.append({"theta_deg": th, "grid": h, "N": int(d["unknowns"]),
                     "total_box_flux_sum": tot["sum"],
                     "total_box_flux_norm": tot["sum"] / F_inc,
                     "total_right_norm": tot["right"] / F_inc,
                     "total_left_norm": tot["left"] / F_inc,
                     "total_top_norm": tot["top"] / F_inc,
                     "total_bottom_norm": tot["bottom"] / F_inc,
                     "scattered_flux_sum_norm": sca["sum"] / F_inc,
                     "F_inc": F_inc})
        print(f"theta={th:5.1f} grid={h:.4f} N={int(d['unknowns'])}: "
              f"total box flux sum/F_inc={tot['sum']/F_inc:+.3e} "
              f"(right {tot['right']/F_inc:+.4f}, left {tot['left']/F_inc:+.4f}, "
              f"top {tot['top']/F_inc:+.2e}, bottom {tot['bottom']/F_inc:+.2e}) "
              f"| scattered sum/F_inc={sca['sum']/F_inc:+.4f}", flush=True)
    AL.write_csv(OUT / "a_energy_flux_check.csv", rows)
    AL.jdump(OUT / "a_energy_flux_check.json", {"rows": rows})
    print("done")


if __name__ == "__main__":
    main()
