"""V5 - real 3-D near-approach / cross-layer coupling on the frozen geometry.

CTP-1.0 extracted 61 691 near-approach *records* but never turned them into a
physical interaction: the final matrix only used the 1283 same-layer crossings.
This script closes that gap.

Method
------
1. every route is sampled as an analytic polyline (flat primitives 0.2 mm,
   transitions 0.05 mm -- the sagitta of an R15 arc over 0.2 mm is 0.33 nm, so
   the sampling is not the accuracy limit);
2. a KD-tree over all sample points plus a chunked k-nearest-neighbour query
   finds, for every sample point, the closest point belonging to *another*
   route;
3. the pairs are reduced to per-route-pair minimum 3-D centre-line distances;
4. the pairs that are already accounted for by the 1283 crossing events are
   removed (their distance is zero *by construction* and the local crossing
   kernel covers the whole coupling region);
5. for the closest pairs the accumulated coupled-mode amplitude
   ``a = int kappa(d(s)) ds`` is integrated along the real geometry, and for all
   others a rigorous bound ``a <= L_route * kappa(d_min)`` is reported.

Outputs
-------
``outputs/crossings/near_approaches_ctp2.csv``   per route pair
``outputs/crossings/near_approach_summary.json`` statistics + bounds
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ctp2 import coupling as C, geometry as G, optics as O      # noqa: E402
from ctp2.params import CACHE, OUT_COUPLING, OUT_CROSSINGS, REF  # noqa: E402

FLAT_STEP_MM = 0.2
TRANS_STEP_MM = 0.05
COUPLING_CUTOFF_UM = 200.0
N_INTEGRATE = 250
CHUNK = 150_000


def db(x):
    return 10.0 * math.log10(max(float(x), 1e-300))


def build_polylines(routes: dict):
    pts, owner, sval = [], [], []
    for rid in routes["order"]:
        r = routes["routes"][int(rid)]
        s, xyz, _ = r.polyline(flat_step=FLAT_STEP_MM, trans_step=TRANS_STEP_MM)
        pts.append(xyz)
        owner.append(np.full(len(s), int(rid), dtype=np.int32))
        sval.append(s)
    return (np.concatenate(pts), np.concatenate(owner), np.concatenate(sval))


def main() -> None:
    t0 = time.time()
    routes = G.load_routes()
    crossings = G.load_crossings()
    crossing_pairs = {(min(int(e["route_a"]), int(e["route_b"])),
                       max(int(e["route_a"]), int(e["route_b"])))
                      for e in crossings}
    print(f"routes={len(routes['order'])} crossing pairs excluded={len(crossing_pairs)}",
          flush=True)

    xyz, owner, sval = build_polylines(routes)
    print(f"polyline points={len(xyz)} build={time.time()-t0:.1f}s", flush=True)

    tree = cKDTree(xyz)
    n = len(xyz)
    best: dict[tuple[int, int], tuple[float, float, np.ndarray, float, float]] = {}
    k = 12
    for start in range(0, n, CHUNK):
        stop = min(start + CHUNK, n)
        dist, idx = tree.query(xyz[start:stop], k=k, workers=-1)
        own = owner[start:stop][:, None]
        oth = owner[idx]
        valid = oth != own
        dist = np.where(valid, dist, np.inf)
        sel = dist.min(axis=1)
        arg = dist.argmin(axis=1)
        rows = np.arange(stop - start)
        j = idx[rows, arg]
        keep = np.isfinite(sel) & (sel < COUPLING_CUTOFF_UM / 1000.0 * 3.0)
        for r_, j_, d_ in zip(rows[keep], j[keep], sel[keep]):
            i_ = start + r_
            a, b = int(owner[i_]), int(owner[j_])
            if a == b:
                continue
            key = (min(a, b), max(a, b))
            prev = best.get(key)
            if prev is None or d_ < prev[0]:
                best[key] = (float(d_), i_, xyz[j_].copy(), float(sval[i_]),
                             float(sval[j_]))
        if start % (CHUNK * 4) == 0:
            print(f"  chunk {start}/{n}  pairs so far={len(best)}  "
                  f"[{time.time()-t0:.0f}s]", flush=True)

    print(f"candidate pairs (dist<600um)={len(best)}  [{time.time()-t0:.0f}s]",
          flush=True)

    # ------------------------------------------------------------------ kappa
    kmodel, krows = C.build_kappa_model(REF)
    pd.DataFrame(krows).to_csv(OUT_COUPLING / "kappa_overlap_resolved.csv",
                               index=False)

    rows = []
    for (a, b), (d_mm, i_, pos, sa, sb) in best.items():
        d_um = d_mm * 1e3
        rows.append({
            "route_a": a, "route_b": b,
            "d_min_um": d_um,
            "x_mm": float(pos[0]), "y_mm": float(pos[1]), "z_mm": float(pos[2]),
            "s_a_mm": sa, "s_b_mm": sb,
            "is_crossing_pair": int((a, b) in crossing_pairs),
            "kappa_at_dmin_mm_inv": float(kmodel.kappa(max(d_um, 0.0))),
        })
    df = pd.DataFrame(rows).sort_values("d_min_um").reset_index(drop=True)
    nc_mask = ~df.is_crossing_pair.astype(bool)
    df["rigorous_amp_bound"] = np.where(
        nc_mask,
        df["kappa_at_dmin_mm_inv"] * df["route_a"].map(
            lambda rid: routes["routes"][int(rid)].total_length),
        0.0)

    # ----------------------------------------------- integrate the nearest ones
    near = df[~df.is_crossing_pair.astype(bool)].head(N_INTEGRATE)
    int_rows = []
    for _, r in near.iterrows():
        A = routes["routes"][int(r.route_a)]
        B = routes["routes"][int(r.route_b)]
        Lint = 4.0                              # +-2 mm window
        sa0 = float(np.clip(r.s_a_mm, Lint, A.total_length - Lint))
        ss = np.linspace(sa0 - Lint, sa0 + Lint, 401)
        pa = A.pos(ss)
        sb0 = float(np.clip(r.s_b_mm, 0.0, B.total_length))
        sb = np.linspace(max(0.0, sb0 - Lint), min(B.total_length, sb0 + Lint),
                         801)
        pb = B.pos(sb)
        d_mm = np.sqrt(((pa[:, None, :] - pb[None, :, :]) ** 2).sum(-1)).min(axis=1)
        d_um = d_mm * 1e3                       # kappa expects um
        k = kmodel.kappa(d_um) * 1e-3           # 1/mm -> 1/um
        amp = float(np.trapezoid(k, ss * 1e3))
        int_rows.append({"route_a": int(r.route_a), "route_b": int(r.route_b),
                         "d_min_um": float(d_um.min()),
                         "integrated_amplitude": amp,
                         "integrated_power": amp ** 2,
                         "integrated_power_db": db(amp ** 2)})
    df_int = pd.DataFrame(int_rows).sort_values("integrated_power",
                                               ascending=False)
    df_int.to_csv(OUT_CROSSINGS / "near_approach_integrated_coupling.csv",
                  index=False)
    df.to_csv(OUT_CROSSINGS / "near_approaches_ctp2.csv", index=False)

    non_cross = df[~df.is_crossing_pair.astype(bool)]
    summary = {
        "n_polyline_points": int(len(xyz)),
        "n_candidate_pairs": int(len(df)),
        "n_crossing_pairs_excluded": int(len(crossing_pairs)),
        "n_noncrosing_pairs": int(len(non_cross)),
        "min_distance_noncrosing_um": float(non_cross.d_min_um.min()),
        "median_distance_um": float(non_cross.d_min_um.median()),
        "pairs_within_50um": int((non_cross.d_min_um < 50.0).sum()),
        "pairs_within_80um": int((non_cross.d_min_um < 80.0).sum()),
        "pairs_within_150um": int((non_cross.d_min_um < 150.0).sum()),
        "max_integrated_amplitude": float(df_int.integrated_amplitude.max()),
        "max_integrated_power": float(df_int.integrated_power.max()),
        "max_integrated_power_db": float(df_int.integrated_power_db.max()),
        "worst_pair": (df_int.iloc[0][["route_a", "route_b"]].to_dict()
                       if len(df_int) else None),
        "kappa_model": {"gamma_um": kmodel.gamma_um,
                        "gamma_measured_um": kmodel.gamma_measured_um,
                        "kappa_30um": kmodel.kappa(30.0),
                        "kappa_50um": kmodel.kappa(50.0),
                        "kappa_80um": kmodel.kappa(80.0)},
        "rigorous_bound_note": ("a <= L_route * kappa(d_min); with the largest "
                                "route length 282.3 mm and the largest "
                                "kappa(d_min) of the table this bounds the "
                                "accumulated parallel/cross-layer coupling on "
                                "the whole board"),
        "rigorous_global_amp_bound": float(df.rigorous_amp_bound.max()),
        "rigorous_global_power_bound": float((df.rigorous_amp_bound ** 2).max()),
        "bound_pair": (df.loc[df.rigorous_amp_bound.idxmax(), ["route_a", "route_b"]]
                       .astype(int).to_dict() if len(df) else None),
        "runtime_seconds": time.time() - t0,
    }
    (OUT_CROSSINGS / "near_approach_summary.json").write_text(
        json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1), flush=True)


if __name__ == "__main__":
    main()

