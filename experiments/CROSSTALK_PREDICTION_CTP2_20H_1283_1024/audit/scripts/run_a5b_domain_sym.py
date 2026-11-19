"""Clean 5-degree domain-size test: symmetric domains only (no artificial cut of
the tilted guide close to the input guide).  Compares Lx = 126.3 um (legacy E3
domain) with Lx = 180 um at the same grid h = 0.2196 um."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import audit_lib as AL
import ctp2_corrected as CC
import physical_kappa as PK

OUT = AL.AUDIT
TH, GRID, PML = 5.0, 0.219615, 5.0


def analyse(d, hw=14.0, u_list=None):
    dd = dict(x=np.asarray(d["x"]), y=np.asarray(d["y"]),
              psi_s=np.asarray(d["psi_s"]), psi_inc=np.asarray(d["psi_inc"]),
              phi=np.asarray(d["phi"]), beta_disc=float(d["beta_disc"]),
              grid=float(d["grid"]), pml=float(d["pml"]),
              Lx=float(d["Lx"]), Ly=float(d["Ly"]), P_src=float(d["P_src"]),
              theta=TH, bounds=d.get("bounds"), n_slab=float(d["n_slab"]))
    return CC.port_analysis2(dd, opt, theta_deg=TH, u_list=u_list,
                             half_width_um=hw)


def main():
    global opt
    opt, eim = AL.beam()
    out = {}
    # baseline: legacy symmetric domain
    d10 = CC.solve_corrected_cached(opt, TH, grid=GRID, d_port=10.0, pml=PML,
                                    strength=3.0, max_unknowns=420_000)[0]
    pa10 = analyse(d10)
    out["Lx126"] = {k: pa10[k] for k in
                    ("T_through", "T_through_fund", "T_through_higher", "R",
                     "T_cross", "T_cross_fund", "T_cross_plus", "T_cross_minus",
                     "radiation", "u_list", "separation_at_port_um")}
    out["Lx126"]["N"] = int(d10["unknowns"])
    print("[Lx=126.3 legacy]", {k: out['Lx126'][k] for k in
                               ('T_through', 'T_cross', 'T_cross_fund',
                                'radiation')}, flush=True)
    # enlarged symmetric domain Lx=180
    bounds = dict(x_min=-180.0, x_max=180.0, y_min=-36.0, y_max=36.0)
    p = CC.corrected_cache_path(TH, GRID, 20.0, PML, 3.0, "_sym180")
    if p.exists():
        dd = np.load(p)
        d180 = {k: (dd[k] if dd[k].ndim else float(dd[k])) for k in dd.files}
    else:
        r = CC.solve_crossing_corrected(opt, TH, grid_um=GRID, d_port_um=20.0,
                                        pml_um=PML, pml_strength=3.0,
                                        max_unknowns=1_200_000, bounds=bounds)
        np.savez_compressed(
            p, theta=np.float64(r["theta"]), grid=np.float64(r["grid"]),
            pml=np.float64(r["pml"]), strength=np.float64(r["strength"]),
            Lx=np.float64(r["Lx"]), Ly=np.float64(r["Ly"]),
            bounds=np.asarray(r["bounds"], float),
            unknowns=np.int64(r["unknowns"]), n_eff_disc=np.float64(r["n_eff_disc"]),
            n_eff=np.float64(r["n_eff"]), beta_disc=np.float64(r["beta_disc"]),
            n_slab=np.float64(r["n_slab"]), P_src=np.float64(r["P_src"]),
            flux_inc=np.float64(r["flux_inc"]), runtime=np.float64(r["runtime"]),
            x=r["x"], y=r["y"], psi_s=r["psi_s"], psi_inc=r["psi_inc"],
            phi=r["phi"])
        dl = np.load(p)
        d180 = {k: (dl[k] if dl[k].ndim else float(dl[k])) for k in dl.files}
    # ports along the crossed guide where the guides are 14 / 17 / 20 um apart
    u = np.asarray(d180["x"])  # unused
    u_list = [14.0 / math.sin(math.radians(TH)), 17.0 / math.sin(math.radians(TH)),
              20.0 / math.sin(math.radians(TH))]
    pa180 = analyse(d180, hw=14.0, u_list=u_list)
    out["Lx180"] = {k: pa180[k] for k in
                    ("T_through", "T_through_fund", "T_through_higher", "R",
                     "T_cross", "T_cross_fund", "T_cross_plus", "T_cross_minus",
                     "radiation", "u_list", "separation_at_port_um")}
    out["Lx180"]["N"] = int(d180["unknowns"])
    print("[Lx=180 symmetric]",
          {k: out['Lx180'][k] for k in ('T_through', 'T_cross', 'T_cross_fund',
                                        'radiation')}, flush=True)
    print("  arm scan (u, separation, power, amp):", flush=True)
    for rr in pa180["arms"]["cross_plus"]:
        print(f"    u={rr['u']:.1f} sep={rr['u']*math.sin(math.radians(TH)):.1f} "
              f"power={rr['power']:.4e} amp={rr['amp']:.4e}", flush=True)
    # analytic CMT cumulative: what fraction lies outside the legacy domain?
    kap = PK.load_or_build_kappa(opt)
    sin_t = math.sin(math.radians(TH))
    s = np.arange(-4000.0, 4000.0 + 1e-9, 0.02)
    k = np.asarray(PK.kappa_eim(opt, np.abs(s) * sin_t, kap))
    dbeta = kap["beta"] * (1.0 - math.cos(math.radians(TH)))
    integ = k * np.exp(-1j * dbeta * s)
    full = np.trapezoid(integ, s) * 1e-3
    cut = {}
    for uc in (126.3, 180.0, 229.5):
        m = np.abs(s) <= uc
        part = np.trapezoid(integ[m], s[m]) * 1e-3
        cut[f"u<{uc:g}"] = {"absA": float(abs(part)), "ratio_to_full": float(abs(part) / abs(full))}
        print(f"  CMT cumulative |u|<{uc:.1f} um: |A|={abs(part):.4f} "
              f"({abs(part)/abs(full)*100:.2f}% of full |A|={abs(full):.4f})", flush=True)
    out["cmt_cumulative"] = cut
    AL.jdump(OUT / "a3b_domain_symmetric_test.json", out)
    print("[A3b] done")


if __name__ == "__main__":
    main()
