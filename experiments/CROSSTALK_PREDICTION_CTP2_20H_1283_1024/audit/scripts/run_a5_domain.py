"""ANOMALY A, part 3 - does the 5 deg legacy domain truncate the coupling region?

Compares the 5 deg crossing solved in
  (a) the legacy domain  (ports at guide separation d = 10 um, half-length 126 um)
  (b) an enlarged domain (asymmetric, +arm port at d = 20 um, x_max = 242 um)
at the SAME grid (0.2196 um, i.e. the legacy E3 grid at 5 deg), and reports the
guided power in both crossed arms, the through/reflection powers, total
scattered power and the energy balance.  Also integrates the physical CMT
cumulative coupling to show what fraction of the coupling lies outside |u|<126 um.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import audit_lib as AL
import ctp2_corrected as CC
import physical_kappa as PK

OUT = AL.AUDIT
TH = 5.0
GRID = 0.219615
PML = 5.0


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
    kap = PK.load_or_build_kappa(opt)
    results = {}
    # ---------------- (a) legacy-size domain (cached corrected solve)
    a = CC.solve_corrected_cached(opt, TH, grid=GRID, d_port=10.0, pml=PML,
                                  strength=3.0, max_unknowns=420_000)
    d10 = a[0]
    pa10 = analyse(d10, hw=14.0)
    results["legacy_domain"] = {k: pa10[k] for k in
                                ("T_through", "T_through_fund", "T_through_higher",
                                 "R", "T_cross_plus", "T_cross_minus",
                                 "T_cross", "T_cross_fund", "T_cross_higher",
                                 "radiation", "P_src_norm", "u_list",
                                 "separation_at_port_um", "energy_1_minus_sum")}
    results["legacy_domain"]["grid"] = float(d10["grid"])
    results["legacy_domain"]["N"] = int(d10["unknowns"])
    results["legacy_domain"]["domain_um"] = list(np.asarray(d10["domain_um"]))
    print("[a] legacy domain:", {k: results['legacy_domain'][k] for k in
                                 ("T_through", "T_cross", "T_cross_plus",
                                  "T_cross_minus", "radiation")}, flush=True)

    # ---------------- (b) enlarged domain, port at d = 20 um
    bounds = dict(x_min=-60.0, x_max=242.0, y_min=-36.0, y_max=36.0)
    b = CC.corrected_cache_path(TH, GRID, 20.0, PML, 3.0, "_enlarged_d20")
    if b.exists():
        dd = np.load(b)
        d20 = {k: (dd[k] if dd[k].ndim else float(dd[k])) for k in dd.files}
    else:
        r = CC.solve_crossing_corrected(opt, TH, grid_um=GRID, d_port_um=20.0,
                                        pml_um=PML, pml_strength=3.0,
                                        max_unknowns=1_200_000, bounds=bounds)
        np.savez_compressed(
            b, theta=np.float64(r["theta"]), grid=np.float64(r["grid"]),
            pml=np.float64(r["pml"]), strength=np.float64(r["strength"]),
            Lx=np.float64(r["Lx"]), Ly=np.float64(r["Ly"]),
            bounds=np.asarray(r["bounds"], float),
            unknowns=np.int64(r["unknowns"]), n_eff_disc=np.float64(r["n_eff_disc"]),
            n_eff=np.float64(r["n_eff"]), beta_disc=np.float64(r["beta_disc"]),
            n_slab=np.float64(r["n_slab"]), P_src=np.float64(r["P_src"]),
            flux_inc=np.float64(r["flux_inc"]), runtime=np.float64(r["runtime"]),
            x=r["x"], y=r["y"], psi_s=r["psi_s"], psi_inc=r["psi_inc"],
            phi=r["phi"])
        dl = np.load(b)
        d20 = {k: (dl[k] if dl[k].ndim else float(dl[k])) for k in dl.files}
    u_max = 229.5
    u_list = [0.5 * u_max, 0.75 * u_max, u_max]
    pa20 = analyse(d20, hw=10.0, u_list=u_list)
    results["enlarged_domain"] = {k: pa20[k] for k in
                                  ("T_through", "T_through_fund", "T_through_higher",
                                   "R", "T_cross_plus", "T_cross_minus",
                                   "T_cross", "T_cross_fund", "T_cross_higher",
                                   "radiation", "P_src_norm", "u_list",
                                   "separation_at_port_um", "energy_1_minus_sum")}
    results["enlarged_domain"]["grid"] = float(d20["grid"])
    results["enlarged_domain"]["N"] = int(d20["unknowns"])
    results["enlarged_domain"]["domain_um"] = [float(d20["Lx"])*2, float(d20["Ly"])*2]
    results["enlarged_domain"]["bounds"] = list(np.asarray(d20["bounds"]))
    print("[b] enlarged domain:", {k: results['enlarged_domain'][k] for k in
                                   ("T_through", "T_cross", "T_cross_plus",
                                    "T_cross_minus", "radiation")}, flush=True)
    print("[b] arm scan (u, power, amp):", flush=True)
    for lbl in ("cross_plus", "cross_minus"):
        for rr in pa20["arms"][lbl]:
            print(f"   {lbl} u={rr['u']:.1f} sep={rr['u']*math.sin(math.radians(TH)):.2f}"
                  f" power={rr['power']:.4e} amp={rr['amp']:.4e}", flush=True)

    # ---------------- (c) how much of the CMT coupling is truncated at |u|<126?
    print("\n[c] physical CMT cumulative coupling:", flush=True)
    gam = kap["gamma"]
    sin_t = math.sin(math.radians(TH))
    s = np.arange(-3000.0, 3000.0 + 1e-9, 0.02)
    dsep = np.abs(s) * sin_t
    k = np.asarray(PK.kappa_eim(opt, dsep, kap))
    dbeta = kap["beta"] * (1.0 - math.cos(math.radians(TH)))
    integ = k * np.exp(-1j * dbeta * s)
    full = np.trapezoid(integ, s) * 1e-3
    cum = np.cumsum(integ) * 0.02 * 1e-3
    for ucut in (119.9, 229.5, 300.0, 460.0):
        mask = np.abs(s) <= ucut
        part = np.trapezoid(integ[mask], s[mask]) * 1e-3
        results[f"cmt_truncated_at_{ucut:g}"] = {
            "amplitude": float(abs(part)),
            "T_cross": float(abs(part) ** 2),
            "fraction_of_full_amplitude": float(abs(part) / max(abs(full), 1e-300))}
        print(f"   |u|<{ucut:6.1f} um: |A|={abs(part):.5f} "
              f"T={abs(part)**2:.4e} "
              f"({abs(part)/max(abs(full),1e-300)*100:.2f}% of full) |A_full|={abs(full):.5f}",
              flush=True)
    # decay scale of the coupling region
    results["cmt_scale_um"] = float(1.0 / (gam * sin_t))
    results["kappa_at_10um_mm_inv"] = float(np.atleast_1d(PK.kappa_eim(opt, 10.0, kap))[0])
    results["gamma_per_um"] = float(gam)
    print(f"   coupling decay length 1/(gamma sin t) = {1/(gam*sin_t):.2f} um; "
          f"legacy grid domain half-length = 126.3 um", flush=True)
    AL.jdump(OUT / "a3_domain_test_5deg.json", results)
    print("[A3] done")


if __name__ == "__main__":
    main()
