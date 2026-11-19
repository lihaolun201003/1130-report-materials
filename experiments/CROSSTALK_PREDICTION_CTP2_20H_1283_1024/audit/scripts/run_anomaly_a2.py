"""ANOMALY A - FDFD vs CMT at small crossing angles.

For every angle:
  1. reproduce the legacy legacy solve (cached by run_anomaly_a1.py)
  2. run the CORRECTED solver (see ctp2_corrected.py: correct incident mode)
  3. analyse both fields with the independent 4-arm port analyser
  4. diagnostics of the legacy incident-mode bug (overlap with the true mode)
  5. physical CMT reference with a converged EIM overlap kappa(d)
Outputs: a_crossing_table.csv, a_energy_balance.csv, a_diagnostics.json
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

ANGLES = [5.0, 10.0, 15.0, 20.0, 30.0, 45.0, 60.0, 90.0]
DPORT = 10.0
PML = 5.0
MAXN = 420_000


def legacy_geometry(opt, theta, h):
    return CC._build_geometry(opt, theta, h, DPORT, PML, MAXN)


def legacy_rhs(geo, psi_inc_leg, h):
    k0 = geo["k0"]
    delta = geo["n2"][1:-1, 1:-1] - geo["n2_bg"][1:-1, 1:-1]
    rhs = (-k0 ** 2 * delta * psi_inc_leg[1:-1, 1:-1]).ravel().astype(complex)
    return rhs


def analyse_legacy(opt, theta, leg):
    h = float(leg["grid"])
    geo = legacy_geometry(opt, theta, h)
    im = CC.correct_incident_mode(geo)
    psi_s = np.asarray(leg["full"])
    psi_inc = np.asarray(leg["psi_inc"])
    beta_leg = float(leg["beta_disc"])
    phi_leg = np.asarray(leg["phi"])
    beta_true = im["beta_disc"]
    phi_true = im["phi"]
    # overlap between the legacy "incident mode" and the true guided mode
    hh = h
    ov = float(np.sum(phi_leg * phi_true) * hh)       # both unit-normalised
    nodes = int(np.sum(np.abs(phi_leg[1:-1]) > np.abs(phi_leg[:-2]))
                + np.sum(np.abs(phi_leg[1:-1]) > np.abs(phi_leg[2:])))
    rhs = legacy_rhs(geo, psi_inc, h)
    P_src = float(np.imag(np.vdot(psi_s[1:-1, 1:-1].ravel(), rhs)) * h * h)
    d = dict(x=geo["x"], y=geo["y"], psi_s=psi_s, psi_inc=psi_inc,
             phi=phi_true, beta_disc=beta_true, grid=h, pml=PML,
             Lx=geo["Lx"], Ly=geo["Ly"], P_src=P_src, theta=theta,
             n_slab=geo["ns"])
    pa = CC.port_analysis2(d, opt, theta_deg=theta)
    # renormalise with the power actually launched by the legacy field
    F_inc_leg = math.sin(beta_leg * h) / h
    pa["P_src_norm"] = P_src / F_inc_leg
    pa["T_cross_norm_legacy_launch"] = pa["T_cross"] / F_inc_leg * (math.sin(beta_true * h) / h)
    return {"overlap_legacy_vs_true": ov, "overlap_sq": ov ** 2,
            "legacy_phi_local_extrema": nodes, "beta_leg": beta_leg,
            "beta_true": beta_true, "n_eff_leg_disc": beta_leg / geo["k0"],
            "n_eff_true_disc": beta_true / geo["k0"],
            "P_src_norm_legacy_launch": pa["P_src_norm"],
            "T_cross_analysed": pa["T_cross"],
            "T_cross_plus": pa["T_cross_plus"],
            "T_cross_minus": pa["T_cross_minus"],
            "R": pa["R"], "T_through_analysed": pa["T_through"],
            "arms": {k: [rr["power"] for rr in v] for k, v in pa["arms"].items()},
            "pa": pa}


def analyse_corrected(opt, theta, cor):
    d = dict(x=np.asarray(cor["x"]), y=np.asarray(cor["y"]),
             psi_s=np.asarray(cor["psi_s"]), psi_inc=np.asarray(cor["psi_inc"]),
             phi=np.asarray(cor["phi"]), beta_disc=float(cor["beta_disc"]),
             grid=float(cor["grid"]), pml=float(cor["pml"]),
             Lx=float(cor["Lx"]), Ly=float(cor["Ly"]),
             P_src=float(cor["P_src"]), theta=theta,
             bounds=cor.get("bounds"), n_slab=float(cor["n_slab"]))
    return CC.port_analysis2(d, opt, theta_deg=theta)


def main():
    opt, eim = AL.beam()
    kap = PK.load_or_build_kappa(opt)      # converged EIM overlap kappa(d) 1-D
    rows_leg, rows_cor, energy_rows, diag = [], [], [], {}
    for th in ANGLES:
        print(f"\n===== theta = {th} deg =====", flush=True)
        leg_path = AL.crossing_cache_path(th, 0.15, DPORT, PML, 3.0, False)
        if not leg_path.exists():
            raise SystemExit(f"missing legacy cache {leg_path.name}; run run_anomaly_a1.py")
        leg = np.load(leg_path)
        # legacy reproduction of the port numbers
        leg_Tcross = float(leg["T_cross"])
        leg_Tthrough = float(leg["T_through"])
        al = analyse_legacy(opt, th, leg)
        print(f" legacy: T_cross_reported={leg_Tcross:.4e} "
              f"T_through={leg_Tthrough:.6f}  |phi_leg . phi_true|^2="
              f"{al['overlap_sq']:.3e}  beta_leg/k0={al['n_eff_leg_disc']:.6f} "
              f"beta_true/k0={al['n_eff_true_disc']:.6f}  "
              f"local_extrema={al['legacy_phi_local_extrema']}", flush=True)
        print(f" legacy re-analysed: T_cross(both arms)={al['T_cross_analysed']:.4e} "
              f"R={al['R']:.4e} scattered/total={al['P_src_norm_legacy_launch']:.4e}",
              flush=True)
        # corrected solve
        cor, cpath = CC.solve_corrected_cached(opt, th, grid=0.15, d_port=DPORT,
                                               pml=PML, strength=3.0,
                                               max_unknowns=MAXN)
        ac = analyse_corrected(opt, th, cor)
        print(f" corrected: grid={float(cor['grid']):.4f} N={int(cor['unknowns'])} "
              f"n_eff_disc={float(cor['n_eff_disc']):.6f} modes="
              f"{[round(mm['n_eff'], 6) for mm in ac['modes']]} "
              f"T_through={ac['T_through']:.6f} (fund {ac['T_through_fund']:.6f},"
              f" hi {ac['T_through_higher']:.2e}) R={ac['R']:.3e} "
              f"T_cross={ac['T_cross']:.4e} (fund {ac['T_cross_fund']:.4e},"
              f" hi {ac['T_cross_higher']:.2e}) rad={ac['radiation']:.4e} "
              f"Psrc={ac['P_src_norm']:.4e} sflux-Psrc={ac['sflux_minus_src']:.2e} "
              f"sep={ac['separation_at_port_um']:.2f}", flush=True)
        # CMT with both kappa models
        cmt_leg_reported = PK.legacy_cmt_reported().get(th, float("nan"))
        cmt_phys = PK.cmt_crossing(kap, kap["beta"], th, optics=opt)
        rows_leg.append({"theta_deg": th, "legacy_T_cross": leg_Tcross,
                         "legacy_T_cross_db": AL.db(leg_Tcross),
                         "legacy_T_through": leg_Tthrough,
                         "reanalysed_T_cross": al["T_cross_analysed"],
                         "reanalysed_T_cross_db": AL.db(al["T_cross_analysed"]),
                         "reanalysed_R": al["R"],
                         "reanalysed_scattered_fraction": al["P_src_norm_legacy_launch"],
                         "grid_um": float(leg["grid"]),
                         "beta_leg": al["beta_leg"], "beta_true": al["beta_true"],
                         "overlap_sq": al["overlap_sq"],
                         "legacy_phi_local_extrema": al["legacy_phi_local_extrema"]})
        rows_cor.append({"theta_deg": th, "grid_um": float(cor["grid"]),
                         "unknowns": int(cor["unknowns"]),
                         "n_eff_disc": float(cor["n_eff_disc"]),
                         "beta_disc": float(cor["beta_disc"]),
                         "T_through": ac["T_through"],
                         "T_through_db": AL.db(ac["T_through"]),
                         "R": ac["R"], "T_cross_plus": ac["T_cross_plus"],
                         "T_cross_minus": ac["T_cross_minus"],
                         "T_cross": ac["T_cross"],
                         "T_cross_db": AL.db(ac["T_cross"]),
                         "radiation": ac["radiation"],
                         "P_src_norm": ac["P_src_norm"],
                         "extinction": ac["extinction"],
                         "extinction_minus_Psrc": ac["extinction_minus_Psrc"],
                         "sflux_minus_src": ac["sflux_minus_src"],
                         "energy_1_minus_sum": ac["energy_1_minus_sum"],
                         "T_through_fund": ac["T_through_fund"],
                         "T_through_higher": ac["T_through_higher"],
                         "T_cross_fund": ac["T_cross_fund"],
                         "T_cross_higher": ac["T_cross_higher"],
                         "separation_at_port_um": ac["separation_at_port_um"],
                         "n_modes_guided": len(ac["modes"]),
                         "guided_fraction": ((abs(ac["d_fwd"]) ** 2 + ac["R"]
                                              + ac["T_through_higher"] + ac["T_cross"])
                                             / ac["P_src_norm"]
                                             if ac["P_src_norm"] > 0 else float("nan")),
                         "T_cross_cmt_legacy": cmt_leg_reported,
                         "T_cross_cmt_physical": cmt_phys["T_cross"],
                         "cmt_physical_amp": cmt_phys["amplitude"],
                         "cmt_physical_unitarised": cmt_phys["unitarised"],
                         "cmt_physical_valid": int(cmt_phys["valid_weak_coupling"])})
        energy_rows.append({"theta_deg": th,
                            "T_through": ac["T_through"],
                            "R": ac["R"],
                            "T_cross": ac["T_cross"],
                            "radiation": ac["radiation"],
                            "sum": ac["T_through"] + ac["R"] + ac["T_cross"] + ac["radiation"],
                            "P_src_norm": ac["P_src_norm"],
                            "extinction": ac["extinction"],
                            "sflux_right": ac["sflux"]["right"] / ac["F_inc"],
                            "sflux_left": ac["sflux"]["left"] / ac["F_inc"],
                            "sflux_top": ac["sflux"]["top"] / ac["F_inc"],
                            "sflux_bottom": ac["sflux"]["bottom"] / ac["F_inc"]})
        diag[f"{th:g}"] = {
            "legacy": {k: v for k, v in al.items() if k not in ("pa", "arms")},
            "legacy_arms": al["arms"],
            "corrected": {k: (v if not isinstance(v, (complex, np.complexfloating))
                              else [v.real, v.imag]) for k, v in ac.items()
                          if k not in ("arms", "extinction", "sflux")
                          and not isinstance(v, np.ndarray)},
            "corrected_arms": {k: [(rr["u"], rr["power"], rr["amp"])
                                   for rr in v] for k, v in ac["arms"].items()},
        }
    AL.jdump(AL.AUDIT / "a_diagnostics.json", diag)
    AL.write_csv(AL.AUDIT / "a_crossing_table.csv", rows_leg + rows_cor)
    # separate clean CSVs
    AL.write_csv(AL.AUDIT / "a_legacy_vs_corrected.csv", rows_cor)
    AL.write_csv(AL.AUDIT / "a_energy_balance.csv", energy_rows)
    # compact combined table
    comb = []
    for rl, rc in zip(rows_leg, rows_cor):
        comb.append({
            "theta_deg": rl["theta_deg"],
            "legacy_T_cross": rl["legacy_T_cross"],
            "legacy_T_cross_db": rl["legacy_T_cross_db"],
            "legacy_T_through": rl["legacy_T_through"],
            "legacy_reanalysed_T_cross": rl["reanalysed_T_cross"],
            "legacy_reanalysed_T_cross_db": rl["reanalysed_T_cross_db"],
            "corrected_T_through": rc["T_through"],
            "corrected_R": rc["R"],
            "corrected_T_cross": rc["T_cross"],
            "corrected_T_cross_db": rc["T_cross_db"],
            "corrected_radiation": rc["radiation"],
            "corrected_P_src": rc["P_src_norm"],
            "cmt_legacy": rl["reanalysed_T_cross"] * 0 + rc["T_cross_cmt_legacy"],
            "cmt_physical": rc["T_cross_cmt_physical"],
            "cmt_physical_db": AL.db(rc["T_cross_cmt_physical"]),
            "grid_um": rc["grid_um"],
        })
    AL.write_csv(AL.AUDIT / "a_summary.csv", comb)
    print("\n[ANOMALY A] done")


if __name__ == "__main__":
    main()
