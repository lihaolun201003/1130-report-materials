"""V6 - mode-resolved crossing S-matrix (fundamental and higher-order modes).

The reference channel is a **3-mode** guide (n_eff = 1.504555, 1.501880 x2), so a
crosstalk prediction that only launches and detects the fundamental mode is not
a complete multimode analysis.  Here the full 3-D BPM launches each guided mode
of the input arm and projects the field at the output planes onto every guided
mode of both arms, giving the local mode-resolved S-matrix

    |S_(j,n),(i,m)|^2 = P_out(port j, mode n) / P_in(port i, mode m).

Because the in-plane effective-index model is single-mode by construction, the
multimode part must be done with the full 3-D channel (this script).
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

from ctp2 import bpm as B                                       # noqa: E402
from ctp2.params import OUT_CROSSINGS, REF                     # noqa: E402


def db(x):
    return 10.0 * math.log10(max(float(x), 1e-300))


def main() -> None:
    t0 = time.time()
    angles = [5.0, 10.0, 20.0, 90.0]
    rows = []
    for th in angles:
        for m in (0, 1):
            t = time.time()
            r = B.run_crossing_3d_multimode(REF, th, launch_mode=m,
                                            port_separation_um=40.0,
                                            dx_um=0.25, dy_um=0.25, dz_um=0.6)
            for key, val in r["P"].items():
                rows.append({"theta_deg": th, "launch_mode": m,
                             "output": key, "power": val, "power_db": db(val),
                             "energy": r["energy"], "seconds": time.time() - t})
            print(f"th={th:5.1f} launch={m}: "
                  + " ".join(f"{k.split('_')[-1]}={db(v):6.1f}" for k, v in r["P"].items())
                  + f"  [E={r['energy']:.5f}, {time.time()-t:.0f}s]", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(OUT_CROSSINGS / "multimode_crossing_smatrix.csv", index=False)

    # summary: how much of the crosstalk goes into higher-order modes, and how
    # much a higher-order launch changes the fundamental crosstalk
    summary = {"angles": angles, "guided_mode_count": 3, "records": []}
    for th in angles:
        sub = df[df.theta_deg == th]
        g = lambda m, out: float(sub[(sub.launch_mode == m) & (sub.output == out)].power.iloc[0]) \
            if len(sub[(sub.launch_mode == m) & (sub.output == out)]) else float("nan")
        tot_cross_0 = sum(g(0, f"cross_arm2_mode{n}") for n in (0, 1, 2))
        tot_cross_1 = sum(g(1, f"cross_arm2_mode{n}") for n in (0, 1, 2))
        tot_thru_0 = sum(g(0, f"through_arm1_mode{n}") for n in (0, 1, 2))
        summary["records"].append({
            "theta_deg": th,
            "crosstalk_total_fund_launch_db": db(tot_cross_0),
            "crosstalk_into_fund_fund_launch_db": db(g(0, "cross_arm2_mode0")),
            "crosstalk_into_higher_fund_launch_db": db(tot_cross_0 - g(0, "cross_arm2_mode0")),
            "through_total_fund_launch_db": db(tot_thru_0),
            "crosstalk_total_higher_launch_db": db(tot_cross_1),
            "crosstalk_into_fund_higher_launch_db": db(g(1, "cross_arm2_mode0")),
            "higher_order_fraction_of_crosstalk": float(
                (tot_cross_0 - g(0, "cross_arm2_mode0")) / max(tot_cross_0, 1e-300)),
        })
    summary["runtime_seconds"] = time.time() - t0
    summary["note"] = ("the board-level matrix assumes fundamental-mode launch and "
                       "fundamental-mode detection on every route; the entries "
                       "above quantify what that assumption misses")
    (OUT_CROSSINGS / "multimode_summary.json").write_text(
        json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1), flush=True)


if __name__ == "__main__":
    main()
