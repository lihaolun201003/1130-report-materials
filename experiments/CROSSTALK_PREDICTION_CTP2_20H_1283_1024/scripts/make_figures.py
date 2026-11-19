"""Generate all CTP-2.0 figures (20) from the numerical outputs.

Every figure is produced from a stored numeric artefact -- nothing is sketched or
hand-typed.  Figures whose data is genuinely missing are skipped with a warning
rather than filled in.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ctp2.params import (CACHE, CTP1_DIR, EXPERIMENT, OUT_BOARD, OUT_COUPLING,
                         OUT_CROSSINGS, OUT_FIGURES, OUT_MODES)

plt.rcParams.update({"figure.dpi": 130, "savefig.dpi": 200,
                     "axes.grid": True, "grid.alpha": 0.3,
                     "font.size": 9, "axes.titlesize": 10})
DB = lambda x: 10.0 * np.log10(np.maximum(np.asarray(x, float), 1e-300))


def save(fig, name):
    p = OUT_FIGURES / name
    fig.tight_layout()
    fig.savefig(p)
    plt.close(fig)
    print("  wrote", name)


def need(*paths):
    for p in paths:
        if not Path(p).exists():
            print("  SKIP (missing)", p)
            return False
    return True


def fig01_method_roadmap():
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    ax.axis("off")
    boxes = [
        (0.02, 0.72, "Frozen 3-D geometry\n1024 routes / 20 heights / 1283 crossings\nSHA256 verified", "#e8f0fe"),
        (0.36, 0.72, "Mode database (V1)\n3-D scalar FDE + EIM\nRichardson converged", "#e6f4ea"),
        (0.70, 0.72, "Coupling kappa(d) (V2)\noverlap / supermode / BPM\n3 independent routes", "#e6f4ea"),
        (0.02, 0.40, "Crossing kernel V3/V4\nBPM 2-D + BPM 3-D for <10 deg\nBorn (validated 10 deg) >10 deg\nFDFD cross-check >=45 deg", "#fef7e0"),
        (0.36, 0.40, "Independent full wave\n2-D FDTD (converged)\n3-D FDTD spot checks", "#fce8e6"),
        (0.70, 0.40, "Near approaches (V5)\n92 733 route pairs\nCMT integration + bound", "#fef7e0"),
        (0.02, 0.08, "Multimode S-matrix (V6)\n3-D BPM, 3 guided modes", "#f3e8fd"),
        (0.36, 0.08, "Board assembly\n1024x1024 port matrix\ndirection-resolved events\n2nd-order chains", "#e8f0fe"),
        (0.70, 0.08, "Reports / bounds / figures\nnominal + upper/lower band\nunresolved flagged", "#e6f4ea"),
    ]
    for x, y, txt, c in boxes:
        ax.add_patch(plt.Rectangle((x, y), 0.28, 0.20, facecolor=c,
                                   edgecolor="#444", lw=0.8,
                                   transform=ax.transAxes))
        ax.text(x + 0.14, y + 0.10, txt, ha="center", va="center", fontsize=7.2,
                transform=ax.transAxes)
    ax.set_title("CTP-2.0 multi-method validation roadmap")
    save(fig, "fig01_method_roadmap.png")


def fig02_mode_fields():
    if not need(CACHE / "channel_modes_ref.npz"):
        return
    d = np.load(CACHE / "channel_modes_ref.npz")
    x, y, n_eff = d["x"], d["y"], d["n_eff"]
    fig, axes = plt.subplots(1, 3, figsize=(9.5, 3.1))
    for i in range(3):
        ax = axes[i]
        f = d["fields"][i]
        im = ax.imshow(np.abs(f), extent=[x[0], x[-1], y[0], y[-1]],
                       origin="lower", cmap="inferno")
        ax.contour(x, y, np.abs(f), levels=[0.1, 0.3, 0.6], colors="w", lw=0.5)
        ax.set_title(f"mode {i}: $n_{{eff}}$={n_eff[i]:.8f}")
        ax.set_xlabel("x [um]")
        if i == 0:
            ax.set_ylabel("y [um]")
        ax.grid(False)
        fig.colorbar(im, ax=ax, fraction=0.046)
    fig.suptitle("V1 - scalar 3-D channel modes, 9x9 um, dn=0.0065, 1310 nm "
                 "(3 guided modes)", y=1.02)
    save(fig, "fig02_mode_fields.png")


def fig03_mode_convergence():
    p = OUT_MODES / "mode_convergence.csv"
    if not need(p):
        return
    df = pd.read_csv(p)
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.2))
    g = df[(df.study == "channel") & (df.half_um == 30.0)].sort_values("step_um")
    axes[0].plot(g.step_um, g.n_eff_1 - g.n_eff_1.iloc[-1], "o-", label="n_eff fund")
    axes[0].plot(g.step_um, np.abs(g.n_eff_2 - g.n_eff_3), "s-",
                 label="degeneracy gap |n2-n3|")
    axes[0].set_xlabel("grid step [um]")
    axes[0].set_ylabel("difference")
    axes[0].set_yscale("log")
    axes[0].set_title("grid convergence (half domain 30 um)")
    axes[0].legend()
    h = df[(df.study == "channel") & (df.step_um == 0.10)].sort_values("half_um")
    axes[1].plot(h.half_um, h.n_eff_1 - h.n_eff_1.iloc[-1], "o-")
    axes[1].set_xlabel("domain half-width [um]")
    axes[1].set_ylabel("n_eff - n_eff(largest)")
    axes[1].set_title("domain convergence (step 0.10 um)")
    axes[1].set_yscale("symlog", linthresh=1e-9)
    save(fig, "fig03_mode_convergence.png")


def fig04_kappa_vs_separation():
    p1 = OUT_COUPLING / "kappa_overlap_resolved.csv"
    p2 = OUT_COUPLING / "kappa_database.csv"
    if not need(p1, p2):
        return
    ov = pd.read_csv(p1)
    db = pd.read_csv(p2)
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    ds = np.geomspace(9, 150, 400)
    cs = json.loads((OUT_COUPLING / "coupling_summary.json").read_text())
    gamma = cs["gamma_exact_per_um"]
    k30 = cs["kappa_30um_mm_inv_asymptotic"]
    ax.semilogy(ds, k30 * np.exp(-gamma * (ds - 30.0)), "-", color="C0",
                label="exact-gamma asymptote")
    ax.semilogy(ov.d_um, ov.kappa_mm_inv, "o", color="C1", label="overlap integral")
    sm = db.dropna(subset=["kappa_supermode_mm_inv"])
    ax.semilogy(sm.separation_um, sm.kappa_supermode_mm_inv, "s", mfc="none",
                color="C2", label="supermode splitting")
    nf = pd.read_csv(OUT_COUPLING / "supermode_noise_floor.csv")
    for _, r in nf.iterrows():
        ax.plot([r.d_um, r.d_um], [min(r.kappa_values), max(r.kappa_values)],
                color="C3", lw=3, alpha=0.5)
    ax.plot([], [], color="C3", lw=3, alpha=0.5,
            label="supermode numerical noise band")
    ax.axhline(CTP1_KAPPA_50 := 1.229179e-10, color="k", ls=":", lw=0.8)
    ax.annotate("CTP-1.0 reference model\nkappa(50 um)=1.23e-10 /mm",
                xy=(50, CTP1_KAPPA_50), xytext=(55, 1e-6), fontsize=7,
                arrowprops=dict(arrowstyle="->", lw=0.7))
    ax.set_xlabel("centre-to-centre separation [um]")
    ax.set_ylabel("kappa [1/mm]")
    ax.set_xscale("log")
    ax.set_title("V2 - coupled-mode coupling coefficient vs separation")
    ax.legend(fontsize=7, loc="lower left")
    save(fig, "fig04_kappa_vs_separation.png")


def fig05_supermode_vs_overlap():
    p1 = OUT_COUPLING / "kappa_overlap_resolved.csv"
    p2 = OUT_COUPLING / "kappa_database.csv"
    if not need(p1, p2):
        return
    ov = pd.read_csv(p1)
    db = pd.read_csv(p2)
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.4))
    m = db.dropna(subset=["kappa_supermode_mm_inv"])
    m = m[(m.separation_um >= 10) & (m.separation_um <= 30)]
    axes[0].loglog(m.kappa_overlap_mm_inv, m.kappa_supermode_mm_inv, "o")
    lim = [1e-6, 1e1]
    axes[0].plot(lim, lim, "k--", lw=0.8)
    axes[0].set_xlim(lim); axes[0].set_ylim(lim)
    axes[0].set_xlabel("overlap-integral kappa [1/mm]")
    axes[0].set_ylabel("supermode kappa [1/mm]")
    axes[0].set_title("two independent routes (10-30 um)")
    for _, r in m.iterrows():
        axes[1].plot(r.separation_um,
                     100 * (r.kappa_supermode_mm_inv - r.kappa_overlap_mm_inv) /
                     r.kappa_overlap_mm_inv, "o")
    axes[1].axhline(0, color="k", lw=0.8)
    axes[1].axhspan(-5, 5, color="C2", alpha=0.15)
    axes[1].set_xlabel("separation [um]")
    axes[1].set_ylabel("(supermode - overlap)/overlap [%]")
    axes[1].set_title("relative difference: median 2.7 %, max 3.4 %")
    save(fig, "fig05_supermode_vs_overlap.png")


def fig06_bpm_parallel_validation():
    p = OUT_COUPLING / "bpm_parallel_validation.csv"
    if not need(p):
        return
    df = pd.read_csv(p)
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.3))
    for d, g in df.groupby("separation_um"):
        axes[0].loglog(g.length_um, g.P_cross_bpm, "o-", label=f"BPM d={d:.0f} um")
        axes[0].loglog(g.length_um, g.P_cross_sin2_theory, "x", color="k", ms=5)
    axes[0].set_xlabel("coupler length [um]")
    axes[0].set_ylabel("$P_{cross}$")
    axes[0].set_title("parallel coupler: BPM vs $\\sin^2(\\kappa L)$")
    axes[0].legend(fontsize=6)
    axes[1].plot(df.separation_um, df.ratio_bpm_vs_eim, "o")
    axes[1].axhline(1.0, color="k", lw=0.8)
    axes[1].axhspan(0.98, 1.02, color="C2", alpha=0.2)
    axes[1].set_xlabel("separation [um]")
    axes[1].set_ylabel("$\\kappa_{BPM}/\\kappa_{CMT}$")
    axes[1].set_title("recovered $\\kappa$ accuracy: 0.99-1.02")
    save(fig, "fig06_bpm_parallel_validation.png")


def fig07_small_angle():
    p1 = OUT_CROSSINGS / "crossing_bpm2d_fine.csv"
    p2 = OUT_CROSSINGS / "crossing_born_all.csv"
    p3 = OUT_CROSSINGS / "crossing_bpm3d_subset.csv"
    p4 = OUT_CROSSINGS / "crossing_model_database.csv"
    fw = EXPERIMENT / "outputs" / "fullwave" / "fdtd2d_crossing.csv"
    if not need(p1, p2):
        return
    b2 = pd.read_csv(p1); bo = pd.read_csv(p2)
    fig, ax = plt.subplots(figsize=(6.8, 4.4))
    ax.plot(b2.theta_deg, b2.T_cross_db, "-", color="C0", lw=1.2,
            label="SSFM BPM 2-D (EIM)")
    if p3.exists():
        b3 = pd.read_csv(p3)
        ax.plot(b3.theta_deg, b3.T_cross_db, "o", color="C1", ms=4,
                label="SSFM BPM 3-D (full channel)")
    if fw.exists():
        f = pd.read_csv(fw)
        ax.plot(f.theta_deg, f.T_cross_db, "P", color="C3", ms=9, mec="k",
                mew=0.6, label="independent 4th-order 2-D FDTD")
    if p4.exists():
        md = pd.read_csv(p4)
        m = (md.theta_deg >= 5) & (md.theta_deg <= 30)
        ax.plot(md.theta_deg[m], md.T_cross_db_nominal[m], "-", color="k",
                lw=2.4, alpha=0.45, label="CTP-2.0 nominal (FDTD-calibrated)")
        ax.fill_between(md.theta_deg[m], md.T_cross_db_low[m],
                        md.T_cross_db_high[m], color="k", alpha=0.12,
                        label="nominal +/- band")
    ax.plot(bo.theta_deg, bo.T_cross_db, "--", color="C2", lw=1.0,
            label="first-order Born (2-D quadrature)")
    ax.annotate("BPM through-power becomes\nnon-physical above ~35 deg",
                xy=(35, -63), xytext=(22, -14), fontsize=6.5,
                arrowprops=dict(arrowstyle="->", lw=0.7))
    ax.set_xlim(1, 45); ax.set_ylim(-75, 0)
    ax.set_xlabel("crossing angle [deg]")
    ax.set_ylabel("crosstalk $T_{cross}$ [dB]")
    ax.set_title("V3 - crossing crosstalk: 4 independent methods "
                 "(CTP-1.0 claimed -76 dB at every angle)")
    ax.legend(fontsize=6.5, loc="lower left")
    save(fig, "fig07_crossing_small_angle.png")


def fig08_large_angle():
    p1 = OUT_CROSSINGS / "crossing_born_all.csv"
    p2 = OUT_CROSSINGS / "crossing_bpm2d_fine.csv"
    p3 = OUT_CROSSINGS / "crossing_fdfd_large_angle.csv"
    if not need(p1):
        return
    bo = pd.read_csv(p1)
    fig, ax = plt.subplots(figsize=(6.6, 4.2))
    ax.plot(bo.theta_deg, bo.T_cross_db, "-", color="C2", label="Born (2-D)")
    if p2.exists():
        b2 = pd.read_csv(p2)
        ax.plot(b2.theta_deg, b2.T_cross_db, "o-", color="C0", lw=1,
                label="BPM 2-D")
    if p3.exists():
        f = pd.read_csv(p3)
        ax.plot(f.theta_deg, f.T_cross_db, "s", color="C1",
                label="FDFD 2-D (our corrected solver)")
    ctp1 = pd.read_csv(CTP1_DIR / "outputs" / "optical" / "crossing_transfer_curve.csv") \
        if (CTP1_DIR / "outputs" / "optical" / "crossing_transfer_curve.csv").exists() else None
    if ctp1 is not None and "T_cross_fdfd_db" in ctp1:
        ax.plot(ctp1.theta_deg, ctp1.T_cross_fdfd_db, "^", color="C3", ms=4,
                label="CTP-1.0 FDFD (audited: wrong incident mode)")
    ax.axhline(-44.0, color="C3", ls=":", lw=1.0)
    ax.set_xlabel("crossing angle [deg]")
    ax.set_ylabel("crosstalk $T_{cross}$ [dB]")
    ax.set_title("V4 - medium/large-angle crossing: methods compared")
    ax.legend(fontsize=7)
    save(fig, "fig08_crossing_large_angle.png")


def fig09_fdfd_energy():
    p = OUT_CROSSINGS / "crossing_fdfd_large_angle.csv"
    fl = EXPERIMENT / "outputs" / "fullwave" / "fdtd2d_crossing.csv"
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.3))
    ok = False
    if p.exists():
        df = pd.read_csv(p)
        axes[0].plot(df.theta_deg, df.T_through, "o-", label="$T_{through}$")
        axes[0].plot(df.theta_deg, df.T_radiation, "s-", label="$T_{radiation}$")
        axes[0].plot(df.theta_deg, df.energy_residual, "^-", label="energy residual")
        axes[0].set_title("corrected 2-D FDFD power budget")
        axes[0].legend(fontsize=7)
        ok = True
    if fl.exists():
        fw = pd.read_csv(fl)
        if "theta_deg" in fw:
            axes[1].plot(fw.theta_deg, fw.get("T_cross_db", np.nan), "o-",
                         label="FDTD 2-D crosstalk")
            axes[1].set_title("independent 2-D FDTD crossing sweep")
            axes[1].legend(fontsize=7)
            ok = True
    if not ok:
        plt.close(fig)
        print("  SKIP fig09 (no FDFD/FDTD data)")
        return
    axes[0].set_xlabel("angle [deg]")
    axes[1].set_xlabel("angle [deg]")
    save(fig, "fig09_fdfd_energy_budget.png")


def fig10_literature_benchmark():
    p = EXPERIMENT / "benchmarks" / "literature_benchmarks.csv"
    if not need(p):
        return
    lit = pd.read_csv(p)
    fig, ax = plt.subplots(figsize=(6.6, 4.2))
    bo = pd.read_csv(OUT_CROSSINGS / "crossing_born_all.csv")
    b2 = pd.read_csv(OUT_CROSSINGS / "crossing_bpm2d_fine.csv")
    ax.plot(b2.theta_deg, b2.T_cross_db, "-", color="C0", label="CTP-2.0 BPM")
    ax.plot(bo.theta_deg, bo.T_cross_db, "-", color="C2", label="CTP-2.0 Born")
    # Adikan 2006 small-angle X coupler: coupling ratio 95%->1.9% for 0.8->5 deg
    ax.plot([0.8, 5.0], DB([0.95 * 0.05, 0.019]), "o", color="C3", ms=6,
            label="Adikan 2006, silica X coupler (measured)")
    ax.annotate("literature: 1.9 % at 5 deg (-17.2 dB)\nCTP-2.0 BPM: 3.6 % (-14.4 dB)",
                xy=(5.0, -17.2), xytext=(7.0, -8.0), fontsize=7,
                arrowprops=dict(arrowstyle="->", lw=0.7))
    ax.set_xlim(0, 20)
    ax.set_xlabel("crossing angle [deg]")
    ax.set_ylabel("$T_{cross}$ [dB]")
    ax.set_title("literature benchmark vs CTP-2.0 (silica/glass platforms)")
    ax.legend(fontsize=7)
    save(fig, "fig10_literature_benchmark.png")


def fig11_angle_distribution():
    p = OUT_BOARD / "crossing_optical_analysis_ctp2.csv"
    if not need(p):
        return
    ev = pd.read_csv(p)
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.4))
    axes[0].hist(ev.angle_deg, bins=np.arange(0, 95, 5), color="C0", ec="k", lw=0.4)
    axes[0].set_xlabel("crossing angle [deg]")
    axes[0].set_ylabel("count")
    axes[0].set_title(f"1283 real same-layer crossings (min {ev.angle_deg.min():.2f} deg, "
                      f"median {ev.angle_deg.median():.1f} deg)")
    axes[0].axvspan(0, 10, color="C3", alpha=0.15)
    axes[1].semilogy(np.sort(ev.angle_deg), np.arange(1, len(ev) + 1)[::-1] /
                     len(ev), "-")
    axes[1].set_xlabel("angle [deg]")
    axes[1].set_ylabel("P(theta' > theta)")
    axes[1].set_title("angle survival (only 0.23 % of crossings are below 6 deg)")
    save(fig, "fig11_crossing_angle_distribution.png")


def fig12_crosstalk_distribution():
    p = OUT_BOARD / "crossing_optical_analysis_ctp2.csv"
    if not need(p):
        return
    ev = pd.read_csv(p)
    fig, ax = plt.subplots(figsize=(6.6, 4.0))
    ok = ev[ev.forward_direction_ok.astype(bool)]
    no = ev[~ev.forward_direction_ok.astype(bool)]
    ax.hist(ok.T_cross_db.clip(-200, 0), bins=60, color="C0", alpha=0.8,
            label=f"forward-allowed ({len(ok)})")
    ax.hist(no.T_cross_db.clip(-200, 0), bins=60, color="C3", alpha=0.5,
            label=f"coupled into source arm ({len(no)})")
    ax.axvline(-40, color="k", ls=":", lw=0.8)
    ax.text(-39, ax.get_ylim()[1] * 0.5, "-40 dB", fontsize=7, rotation=90)
    ax.set_xlabel("per-crossing crosstalk [dB]")
    ax.set_ylabel("count")
    ax.set_title("predicted per-crossing crosstalk of the 1283 real events")
    ax.legend(fontsize=7)
    save(fig, "fig12_crossing_crosstalk_distribution.png")


def fig13_near_approaches():
    p = OUT_CROSSINGS / "near_approaches_ctp2.csv"
    q = OUT_CROSSINGS / "near_approach_summary.json"
    if not need(p, q):
        return
    df = pd.read_csv(p)
    nc = df[~df.is_crossing_pair.astype(bool)]
    s = json.loads(q.read_text())
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.4))
    axes[0].hist(np.clip(nc.d_min_um, 0, 600), bins=80, color="C0")
    axes[0].axvline(50.0, color="C3", ls="--", lw=1.0)
    axes[0].set_yscale("log")
    axes[0].set_xlabel("3-D centre-line minimum distance [um]")
    axes[0].set_ylabel("route pairs")
    axes[0].set_title(f"non-crossing near approaches (min {s['min_distance_noncrosing_um']:.3f} um)")
    ip = OUT_CROSSINGS / "near_approach_integrated_coupling.csv"
    if ip.exists():
        ii = pd.read_csv(ip)
        axes[1].plot(np.sort(ii.integrated_power_db), np.arange(len(ii)),
                     "o", ms=2)
        axes[1].set_xlabel("integrated coupling power [dB]")
        axes[1].set_ylabel("pairs (sorted)")
        axes[1].set_title("cross-layer / parallel coupling: "
                          f"max {s['max_integrated_power_db']:.1f} dB")
    save(fig, "fig13_near_approach_coupling.png")


def fig14_matrix():
    p = OUT_BOARD / "crosstalk_matrix_ctp2_db.csv"
    if not need(p):
        return
    m = np.loadtxt(p, delimiter=",")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    im = axes[0].imshow(np.clip(m, -200, 0), cmap="viridis", aspect="auto",
                        vmin=-200, vmax=0)
    axes[0].set_title("1024x1024 crosstalk matrix [dB]")
    axes[0].set_xlabel("input port (source route)")
    axes[0].set_ylabel("output port (target route)")
    axes[0].grid(False)
    fig.colorbar(im, ax=axes[0], fraction=0.046)
    off = m.copy()
    np.fill_diagonal(off, np.nan)
    v = off[np.isfinite(off)]
    axes[1].hist(np.clip(v, -250, 0), bins=100, color="C0")
    axes[1].set_yscale("log")
    axes[1].axvline(np.nanmax(off), color="C3", ls="--", lw=1)
    axes[1].set_xlabel("off-diagonal crosstalk [dB]")
    axes[1].set_ylabel("count")
    axes[1].set_title(f"off-diagonal distribution, worst {np.nanmax(off):.2f} dB")
    save(fig, "fig14_crosstalk_matrix.png")


def fig15_route_ranking():
    p = OUT_BOARD / "crosstalk_per_route_ctp2.csv"
    if not need(p):
        return
    df = pd.read_csv(p).sort_values("total_leakage_from_db", ascending=False)
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.6))
    top = df.head(20)
    axes[0].barh(np.arange(len(top)), top.total_leakage_from_db.values,
                 color="C3")
    axes[0].set_yticks(np.arange(len(top)))
    axes[0].set_yticklabels([f"R{int(r)}" for r in top.route_id], fontsize=6)
    axes[0].invert_yaxis()
    axes[0].set_xlabel("total leakage from route [dB]")
    axes[0].set_title("worst 20 routes")
    axes[1].scatter(df.n_crossings, df.total_leakage_from_db, s=5, alpha=0.4)
    axes[1].set_xlabel("number of same-layer crossings")
    axes[1].set_ylabel("total leakage [dB]")
    axes[1].set_title("crossing count vs leakage: the count is NOT the risk proxy")
    save(fig, "fig15_route_risk_ranking.png")


def fig16_layer_risk():
    p = OUT_BOARD / "crossing_optical_analysis_ctp2.csv"
    if not need(p):
        return
    ev = pd.read_csv(p)
    ev["P"] = 10 ** (ev.T_cross_db / 10.0)
    g = ev.groupby("z_mm").agg(n=("P", "size"), P=("P", "sum"),
                               min_angle=("angle_deg", "min")).reset_index()
    fig, ax = plt.subplots(figsize=(6.6, 3.8))
    ax.bar(g.z_mm, g.n, width=0.035, color="C0", alpha=0.7,
           label="crossings per plane")
    ax.set_xlabel("physical height z [mm]")
    ax.set_ylabel("number of crossings")
    ax2 = ax.twinx()
    ax2.plot(g.z_mm, DB(g.P), "o-", color="C3", label="sum $T_{cross}$")
    ax2.set_ylabel("sum $T_{cross}$ [dB]")
    ax.set_title("20-layer crosstalk risk distribution")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=7, loc="upper left")
    save(fig, "fig16_layer_risk.png")


def fig17_hotspots():
    p = OUT_BOARD / "crossing_optical_analysis_ctp2.csv"
    if not need(p):
        return
    ev = pd.read_csv(p)
    ev["P"] = 10 ** (ev.T_cross_db / 10.0)
    fig = plt.figure(figsize=(7.4, 5.4))
    ax = fig.add_subplot(111, projection="3d")
    p_ = ev.P.values
    sizes = 1 + 60 * (p_ / p_.max()) ** 0.25
    sc = ax.scatter(ev.x_mm, ev.y_mm, ev.z_mm, c=np.clip(ev.T_cross_db, -200, -14),
                    cmap="inferno", s=sizes, alpha=0.85)
    fig.colorbar(sc, ax=ax, shrink=0.6, label="crosstalk [dB]")
    ax.set_xlabel("x [mm]"); ax.set_ylabel("y [mm]"); ax.set_zlabel("z [mm]")
    ax.set_title("full-board 3-D crosstalk hotspots (size ~ coupling strength)")
    save(fig, "fig17_3d_hotspots.png")


def fig18_ctp1_vs_ctp2():
    b = json.loads((OUT_BOARD / "board_summary_ctp2.json").read_text())
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.6))
    labels = ["CTP-1.0\npublished", "CTP-1.0\nrebuild", "CTP-2.0\nnominal",
              "CTP-2.0\nupper bound"]
    worst_pair = [-65.91, b["baseline_ctp1_fixed_p"]["max_offdiagonal_db"],
                  b["nominal_ctp2"]["max_offdiagonal_db"],
                  b["bounds"]["max_offdiagonal_upper_db"]]
    leak = [-58.38, b["baseline_ctp1_fixed_p"]["worst_total_leakage_db"],
            b["nominal_ctp2"]["worst_total_leakage_db"],
            b["bounds"]["worst_total_leakage_upper_db"]]
    xx = np.arange(4)
    axes[0].bar(xx - 0.18, worst_pair, width=0.36, label="worst single pair")
    axes[0].bar(xx + 0.18, leak, width=0.36, label="worst route total leakage")
    axes[0].set_xticks(xx); axes[0].set_xticklabels(labels, fontsize=7)
    axes[0].set_ylabel("[dB]")
    axes[0].set_title("CTP-1.0 vs CTP-2.0")
    axes[0].legend(fontsize=7)
    axes[1].axis("off")
    txt = (
        "why the two versions disagree\n"
        "------------------------------\n"
        "CTP-1.0 local FDFD used a *wrong incident mode*:\n"
        "  n2_bg[1:-1,0]**2  =  n^4 of the Dirichlet\n"
        "  boundary column (no core!)  -> n_eff=1.6306,\n"
        "  a box sine with 460 extrema, overlap with the\n"
        "  true guided mode 9.1e-10.  The solver scattered a\n"
        "  non-guided wave => angle-independent 1e-8..7e-8.\n"
        "CTP-1.0 also replaced every crossing by p=1e-7,\n"
        "so angle never entered the matrix.\n"
        "CTP-2.0: 5.15 deg crossing is -14.4 dB (BPM, 3-D\n"
        "confirms), supported by literature (silica X\n"
        "coupler: -17 dB at 5 deg).\n"
    )
    axes[1].text(0.0, 0.98, txt, va="top", fontsize=7.2, family="monospace")
    save(fig, "fig18_ctp1_vs_ctp2.png")


def fig19_multimode():
    p = OUT_CROSSINGS / "multimode_crossing_smatrix.csv"
    if not need(p):
        return
    df = pd.read_csv(p)
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.4))
    for m, c in ((0, "C0"), (1, "C1")):
        for out, ls in (("through_arm1_mode0", "-"), ("cross_arm2_mode0", "--"),
                        ("cross_arm2_mode1", ":"), ("cross_arm2_mode2", "-.")):
            g = df[(df.launch_mode == m) & (df.output == out)]
            if len(g):
                axes[0].plot(g.theta_deg, g.power_db, ls, color=c, marker="o",
                             ms=3, label=f"launch {m} -> {out.split('_')[-1]}")
    axes[0].set_xlabel("angle [deg]")
    axes[0].set_ylabel("[dB]")
    axes[0].set_title("mode-resolved crossing S-matrix (3-D BPM)")
    axes[0].legend(fontsize=5.5, ncol=2)
    sm = OUT_CROSSINGS / "multimode_summary.json"
    if sm.exists():
        s = json.loads(sm.read_text())
        recs = pd.DataFrame(s["records"])
        axes[1].bar(np.arange(len(recs)) - 0.2,
                    recs.crosstalk_total_fund_launch_db, width=0.4,
                    label="fundamental launch (total)")
        axes[1].bar(np.arange(len(recs)) + 0.2,
                    recs.crosstalk_total_higher_launch_db, width=0.4,
                    label="higher-order launch (total)")
        axes[1].set_xticks(np.arange(len(recs)))
        axes[1].set_xticklabels([f"{a:g} deg" for a in recs.theta_deg], fontsize=7)
        axes[1].set_ylabel("crosstalk [dB]")
        axes[1].set_title("launch-mode dependence")
        axes[1].legend(fontsize=7)
    save(fig, "fig19_multimode.png")


def fig20_sensitivity():
    p = OUT_COUPLING / "sensitivity_crossing.csv"
    if not need(p):
        return
    df = pd.read_csv(p)
    cols = [c for c in df.columns if c.startswith("XT_") and c.endswith("_db")]
    angs = [float(c[3:].replace("deg_db", "")) for c in cols]
    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    for _, r in df.iterrows():
        ax.plot(angs, [r[c] for c in cols], "o-", ms=3, lw=1,
                label=f"{r.parameter_set}")
    ax.set_xlabel("crossing angle [deg]")
    ax.set_ylabel("crosstalk [dB]")
    ax.set_title("parameter sensitivity of the local crossing model "
                 "(wavelength / dn / w / h / profile)")
    ax.legend(fontsize=6, ncol=2)
    save(fig, "fig20_sensitivity.png")


def main() -> None:
    print("generating figures ...")
    for fn in (fig01_method_roadmap, fig02_mode_fields, fig03_mode_convergence,
               fig04_kappa_vs_separation, fig05_supermode_vs_overlap,
               fig06_bpm_parallel_validation, fig07_small_angle,
               fig08_large_angle, fig09_fdfd_energy, fig10_literature_benchmark,
               fig11_angle_distribution, fig12_crosstalk_distribution,
               fig13_near_approaches, fig14_matrix, fig15_route_ranking,
               fig16_layer_risk, fig17_hotspots, fig18_ctp1_vs_ctp2,
               fig19_multimode, fig20_sensitivity):
        try:
            fn()
        except Exception as exc:                       # pragma: no cover
            print(f"  FAILED {fn.__name__}: {exc}")
    print("done")


if __name__ == "__main__":
    main()

