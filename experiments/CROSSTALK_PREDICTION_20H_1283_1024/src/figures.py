"""Figures for the 1024-channel crosstalk prediction report."""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection
from mpl_toolkits.mplot3d.art3d import Line3DCollection

from .config import CONFIG, EXPERIMENT_ROOT
from .dataio import load_dataset
from .config import BEST_VALID

FIG = EXPERIMENT_ROOT / "outputs" / "figures"
OPT = EXPERIMENT_ROOT / "outputs" / "optical"
GEO = EXPERIMENT_ROOT / "outputs" / "geometry"
DPI = CONFIG["figure_dpi"]

plt.rcParams.update({
    "figure.dpi": 110,
    "savefig.dpi": DPI,
    "font.size": 9,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "axes.axisbelow": True,
    "figure.autolayout": False,
})


def _save(fig, name: str, svg: bool = False):
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / f"{name}.png", bbox_inches="tight")
    if svg:
        fig.savefig(FIG / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------- fig 1
def fig_length_distribution():
    df = pd.read_csv(GEO / "route_lengths.csv")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    ax = axes[0]
    ax.hist([df.L_straight_mm, df.L_planar_arc_mm, df.L_transition_arc_mm],
            bins=40, stacked=True, label=["straight", "planar arc", "3-D transition"],
            color=["#4C72B0", "#DD8452", "#55A868"])
    ax.set_xlabel("length per route (mm)")
    ax.set_ylabel("number of routes")
    ax.set_title("1024 routes: length decomposition")
    ax.legend(frameon=False)
    ax = axes[1]
    ax.hist(df.L_total_mm, bins=50, color="#4C72B0", alpha=0.85)
    ax.axvline(df.L_total_mm.mean(), color="k", ls="--", lw=1,
               label=f"mean {df.L_total_mm.mean():.1f} mm")
    ax.set_xlabel("total propagation length (mm)")
    ax.set_ylabel("number of routes")
    ax.set_title(f"total = {df.L_total_mm.sum():,.2f} mm (authoritative "
                 f"156 597.221 522 mm)")
    ax.legend(frameon=False)
    fig.suptitle("E1 - true arc-length statistics of the 20-height, 1283-crossing solution",
                 y=1.02)
    _save(fig, "fig01_length_distribution", svg=True)


# --------------------------------------------------------------------- fig 2
def fig_loss_distribution():
    df = pd.read_csv(GEO / "propagation_loss.csv")
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.hist(df.loss_base_db, bins=50, color="#55A868", alpha=0.9)
    ax.axvline(df.loss_base_db.mean(), color="k", ls="--", lw=1,
               label=f"mean {df.loss_base_db.mean():.3f} dB")
    ax.set_xlabel("base propagation loss (dB)  @ 0.05 dB/cm, R15 extra bend loss = 0")
    ax.set_ylabel("number of routes")
    ax.set_title("E1 - propagation loss of the 1024 routes")
    ax.legend(frameon=False)
    ax.text(0.02, 0.95, f"min {df.loss_base_db.min():.3f} dB   "
            f"max {df.loss_base_db.max():.3f} dB   "
            f"total {df.loss_base_db.sum():.1f} dB",
            transform=ax.transAxes, va="top", fontsize=8)
    _save(fig, "fig02_propagation_loss", svg=True)


# --------------------------------------------------------------------- fig 3
def fig_mode_fields():
    z = np.load(OPT / "mode_reference.npz")
    x, y, fields, neff = z["x"], z["y"], z["fields"], z["n_eff"]
    nshow = min(3, int(np.sum(neff > 1.5 + 1e-7)))
    fig, axes = plt.subplots(1, nshow + 1, figsize=(3.4 * (nshow + 1), 3.3))
    for i in range(nshow):
        ax = axes[i]
        f = np.abs(fields[i])
        im = ax.imshow(f, origin="lower", extent=[x[0], x[-1], y[0], y[-1]],
                       cmap="magma")
        ax.set_title(f"mode {i}: n_eff={neff[i]:.6f}")
        ax.set_xlabel("x (um)")
        if i == 0:
            ax.set_ylabel("y (um)")
        fig.colorbar(im, ax=ax, fraction=0.046)
    ax = axes[-1]
    idx = int(np.argmin(np.abs(y)))
    for i in range(nshow):
        ax.plot(x, fields[i][idx], label=f"mode {i}")
    ax.set_xlim(-14, 14)
    ax.set_xlabel("x (um) at y = 0")
    ax.set_ylabel("normalised field")
    ax.set_title("cross-section cut")
    ax.legend(frameon=False, fontsize=7)
    fig.suptitle("E2 - scalar weak-guidance modes, 9x9 um core, Delta n = 0.0065, "
                 "lambda = 1310 nm", y=1.02)
    _save(fig, "fig03_mode_fields", svg=True)


# --------------------------------------------------------------------- fig 4
def fig_mode_convergence():
    conv = pd.read_csv(OPT / "mode_convergence.csv")
    g = conv[conv.study == "grid"].sort_values("grid_um")
    d = conv[conv.study == "domain"].sort_values("domain_um")
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    ax = axes[0]
    ax.plot(g.grid_um, g.n_eff_fund, "o-", label="n_eff (fundamental)")
    ax.set_xlabel("grid spacing (um)")
    ax.set_ylabel("n_eff")
    ax2 = ax.twinx()
    ax2.plot(g.grid_um, g.n_guided, "s--", color="tab:red", label="guided modes")
    ax2.set_ylabel("guided modes", color="tab:red")
    ax.set_title("grid convergence")
    ax = axes[1]
    ax.plot(d.domain_um, d.n_eff_fund, "o-", color="tab:green")
    ax.set_xlabel("computational window (um)")
    ax.set_ylabel("n_eff")
    ax.set_title("domain convergence")
    fig.suptitle("E2 - numerical convergence of the mode solver", y=1.03)
    _save(fig, "fig04_mode_convergence", svg=True)


# --------------------------------------------------------------------- fig 5
def fig_coupling_vs_separation():
    df = pd.read_csv(OPT / "coupling_coefficients.csv")
    comp = df[df.validity == "computed"].sort_values("separation_um")
    extrap = df[df.validity == "extrapolated"].sort_values("separation_um")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    ax = axes[0]
    ax.semilogy(comp.separation_um, comp.kappa_supermode_mm_inv, "o-",
                ms=3, label="supermode splitting")
    ax.semilogy(comp.separation_um, comp.kappa_overlap_mm_inv, "x--",
                ms=4, label="overlap integral")
    ax.semilogy(extrap.separation_um, extrap.kappa_supermode_mm_inv, ":",
                color="grey", label="exponential extrapolation")
    ax.set_xlabel("centre-to-centre separation d (um)")
    ax.set_ylabel(r"$\kappa$ (mm$^{-1}$)")
    ax.set_title(r"$\kappa(d)$ at $\lambda$=1310 nm, $\Delta n$=0.0065, 9x9 um")
    ax.legend(frameon=False, fontsize=8)
    ax.set_ylim(1e-14, 10)
    ax = axes[1]
    d = np.linspace(10, 60, 250)
    kk = np.asarray(comp.kappa_supermode_mm_inv, float)
    dd = np.asarray(comp.separation_um, float)
    fit = dd >= max(dd.min(), 15.0)
    slope, icpt = np.polyfit(dd[fit], np.log(kk[fit]), 1)
    kfit = np.exp(icpt + slope * d)
    for L in (0.1, 1.0, 10.0):
        ax.semilogy(d, np.maximum(np.sin(kfit * L) ** 2, 1e-30), label=f"L = {L} mm")
    ax.set_xlabel("separation (um)")
    ax.set_ylabel("cross-coupled power fraction")
    ax.set_title("parallel interaction vs length (exponential tail fit)")
    ax.legend(frameon=False, fontsize=8)
    ax.set_ylim(1e-20, 1)
    fig.suptitle("E3 - two-waveguide coupling database", y=1.02)
    _save(fig, "fig05_coupling_vs_separation", svg=True)


# --------------------------------------------------------------------- fig 6
def fig_crosstalk_vs_length():
    df = pd.read_csv(OPT / "coupling_coefficients.csv")
    comp = df[df.validity == "computed"].sort_values("separation_um")
    d = comp.separation_um.to_numpy()
    # build a smooth kappa curve
    dd = np.linspace(d.min(), d.max(), 300)
    kk = np.exp(np.interp(dd, d, np.log(np.clip(comp.kappa_supermode_mm_inv.to_numpy(),
                                               1e-30, None))))
    Ls = np.logspace(-2, 2, 160)
    P = np.sin(np.outer(Ls, kk)) ** 2
    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    im = ax.pcolormesh(dd, Ls, np.maximum(P, 1e-16), shading="auto",
                       cmap="viridis", norm=matplotlib.colors.LogNorm(1e-12, 1))
    ax.set_yscale("log")
    ax.set_xlabel("separation (um)")
    ax.set_ylabel("parallel interaction length L (mm)")
    ax.set_title(r"E3 - crosstalk $P=\sin^2(\kappa L)$ vs separation and length")
    fig.colorbar(im, ax=ax, label="power fraction")
    ax.contour(dd, Ls, np.maximum(P, 1e-16), levels=[1e-4, 1e-3, 1e-2],
               colors="w", linewidths=0.6)
    _save(fig, "fig06_crosstalk_vs_length", svg=True)


# --------------------------------------------------------------------- fig 7
def fig_crosstalk_matrix():
    T = np.load(OPT / "crosstalk_matrix_linear.npy")
    ids = pd.read_csv(OPT / "crosstalk_per_route.csv").route_id.to_numpy()
    M = 10 * np.log10(np.maximum(T, 1e-300))
    off = M.copy()
    np.fill_diagonal(off, np.nan)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.2))
    ax = axes[0]
    im = ax.imshow(off, origin="lower", cmap="magma", vmin=-130, vmax=-55,
                   interpolation="nearest")
    ax.set_xlabel("input route index")
    ax.set_ylabel("output route index")
    ax.set_title("off-diagonal crosstalk (dB)")
    fig.colorbar(im, ax=ax, label="dB")
    ax = axes[1]
    # group by target height
    df = pd.read_csv(OPT / "crosstalk_per_route.csv")
    order = np.argsort(df.target_z_mm.to_numpy())[::-1]
    ax.imshow(off[np.ix_(order, order)], origin="lower", cmap="magma",
              vmin=-130, vmax=-55, interpolation="nearest")
    ax.set_title("reordered by physical height (top = highest z)")
    ax.set_xlabel("input (height-grouped)")
    ax.set_ylabel("output (height-grouped)")
    fig.suptitle("E5 - 1024x1024 port crosstalk matrix (upper bound; every "
                 "crossing contributes the resolution floor)", y=1.02)
    _save(fig, "fig07_crosstalk_matrix", svg=True)


# --------------------------------------------------------------------- fig 8
def fig_route_ranking():
    df = pd.read_csv(OPT / "crosstalk_per_route.csv")
    top = df.sort_values("total_leakage_from_db", ascending=False).head(25)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    ax = axes[0]
    y = np.arange(len(top))
    ax.barh(y, -top.total_leakage_from_db, color="#C44E52")
    ax.set_yticks(y)
    ax.set_yticklabels([f"R{int(r)}" for r in top.route_id], fontsize=7)
    ax.invert_yaxis()
    ax.set_xlabel("total leakage magnitude (dB, larger is worse)")
    ax.set_title("25 worst input routes")
    ax = axes[1]
    ax.scatter(df.n_crossings, df.total_leakage_from_db, s=12, alpha=0.6)
    ax.set_xlabel("crossings on route")
    ax.set_ylabel("total leakage (dB)")
    ax.set_title("crossing count vs leakage")
    fig.suptitle("E5 - per-route crosstalk risk", y=1.02)
    _save(fig, "fig08_route_ranking", svg=True)


# --------------------------------------------------------------------- fig 9
def fig_layer_risk():
    df = pd.read_csv(GEO / "layer_statistics.csv")
    df = df.sort_values("z_mm")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    ax = axes[0]
    ax.barh(df.z_mm, df.n_crossings, height=0.035, color="#4C72B0")
    ax.set_yticks(df.z_mm)
    ax.set_yticklabels([f"{z:+.3f}" for z in df.z_mm], fontsize=7)
    ax.set_xlabel("crossing events")
    ax.set_ylabel("physical height z (mm)")
    ax.set_title("crossings per routing height")
    ax = axes[1]
    ax.barh(df.z_mm, df.total_length_mm, height=0.035, color="#55A868")
    ax.set_yticks(df.z_mm)
    ax.set_yticklabels([f"{z:+.3f}" for z in df.z_mm], fontsize=7)
    ax.set_xlabel("total propagation length (mm)")
    ax.set_title("route length per height")
    fig.suptitle("E5 - 20-height distribution", y=1.02)
    _save(fig, "fig09_layer_risk", svg=True)


# -------------------------------------------------------------------- fig 10
def fig_crossing_angles():
    df = pd.read_csv(OPT / "crossing_optical_analysis.csv")
    curve = pd.read_csv(OPT / "crossing_transfer_curve.csv")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    ax = axes[0]
    bins = np.arange(0, 95, 5)
    ax.hist(df.angle_deg, bins=bins, color="#4C72B0", alpha=0.9)
    ax.set_xlabel("crossing angle (deg)")
    ax.set_ylabel("number of events")
    ax.set_title(f"{len(df)} same-plane crossings")
    ax = axes[1]
    ax.semilogy(curve.theta_deg, np.maximum(curve.T_cross_fdfd, 1e-12), "o-",
                label="local 2-D FDFD")
    ax.axhline(CONFIG["crossing_model"]["resolution_floor"], color="r", ls="--",
               lw=1, label="model resolution floor")
    ax.semilogy(curve.theta_deg, np.maximum(curve.T_cross_born, 1e-300), "s--",
                ms=3, color="grey", label="Born (first order)")
    ax.set_xlabel("crossing angle (deg)")
    ax.set_ylabel("cross-coupled power")
    ax.set_ylim(1e-14, 1)
    ax.set_title("predicted transfer per crossing")
    ax.legend(frameon=False, fontsize=7)
    fig.suptitle("E5 - 1283 geometric crossings: angle distribution and optical "
                 "transfer", y=1.02)
    _save(fig, "fig10_crossing_angles", svg=True)


# -------------------------------------------------------------------- fig 11
def fig_3d_hotspots():
    ds = load_dataset(BEST_VALID, verify_hash=False)
    hotspots = json.load(open(OPT / "crosstalk_hotspots.json"))["clusters"]
    fig = plt.figure(figsize=(9, 7.5))
    ax = fig.add_subplot(111, projection="3d")
    xs, ys, zs = [], [], []
    for r in ds.routes:
        P = r.sample(0.8)
        xs.append(P[:, 0]); ys.append(P[:, 1]); zs.append(P[:, 2])
        xs.append([np.nan]); ys.append([np.nan]); zs.append([np.nan])
    ax.plot(np.concatenate(xs), np.concatenate(ys), np.concatenate(zs),
            color="#335577", lw=0.2, alpha=0.35)
    if hotspots:
        hx = [h["x_mm"] for h in hotspots]
        hy = [h["y_mm"] for h in hotspots]
        hz = [h["z_mm"] for h in hotspots]
        ss = np.array([h["n_crossings"] for h in hotspots], float)
        sc = ax.scatter(hx, hy, hz, c=hz, cmap="plasma", s=12 + 6 * ss,
                        depthshade=False, edgecolors="k", linewidths=0.2)
        fig.colorbar(sc, ax=ax, shrink=0.6, label="z (mm)")
    ax.set_xlim(0, 150)
    ax.set_ylim(0, 150)
    ax.set_zlim(-0.35, 0.65)
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    ax.set_zlabel("z (mm)")
    ax.set_title("E5 - true 3-D routes and crosstalk hotspots\n"
                 f"{len(hotspots)} clusters, sphere size = events per 2x2 mm cell")
    ax.view_init(elev=22, azim=-58)
    _save(fig, "fig11_3d_hotspots", svg=True)


# -------------------------------------------------------------------- fig 12
def fig_hotspot_zoom():
    hotspots = json.load(open(OPT / "crosstalk_hotspots.json"))["clusters"]
    if not hotspots:
        return
    h = hotspots[0]
    routes = h["routes"][:6]
    ds = load_dataset(BEST_VALID, verify_hash=False)
    rid = {r.route_id: r for r in ds.routes}
    fig, ax = plt.subplots(figsize=(6.4, 5.6))
    for k, r in enumerate(routes):
        route = rid[r]
        P = route.sample(0.02)
        m = ((P[:, 0] > h["x_mm"] - 12) & (P[:, 0] < h["x_mm"] + 12)
             & (P[:, 1] > h["y_mm"] - 12) & (P[:, 1] < h["y_mm"] + 12))
        if m.any():
            ax.plot(P[m, 0], P[m, 1], lw=1.4, label=f"R{r} (z={P[m, 2][0]:+.3f})")
    ax.plot(h["x_mm"], h["y_mm"], "r*", ms=14, label="hotspot centroid")
    ax.set_aspect("equal")
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    ax.set_title(f"E5 - highest-risk crossing cluster at z={h['z_mm']:+.3f} mm\n"
                 f"{h['n_crossings']} events, {len(h['routes'])} routes")
    ax.legend(frameon=False, fontsize=7)
    _save(fig, "fig12_hotspot_zoom", svg=True)


# -------------------------------------------------------------------- fig 13
def fig_sensitivity():
    sweep = pd.read_csv(OPT / "coupling_parameter_sweep.csv")
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4))
    ax = axes[0]
    for _, row in sweep.iterrows():
        ax.semilogy([10, 15, 20, 30, 50, 62],
                    [row.kappa_10um_mm_inv, row.kappa_15um_mm_inv,
                     row.kappa_20um_mm_inv, row.kappa_30um_mm_inv,
                     row.kappa_50um_mm_inv, row.kappa_62um_mm_inv],
                    "o-", ms=3, label=row.parameter_set)
    ax.set_xlabel("separation (um)")
    ax.set_ylabel(r"$\kappa$ (mm$^{-1}$)")
    ax.set_title("coupling vs optical parameters")
    ax.legend(frameon=False, fontsize=6, ncol=2)
    ax = axes[1]
    df = sweep.sort_values("gamma_per_um")
    ax.barh(np.arange(len(df)), df.gamma_per_um, color="#4C72B0")
    ax.set_yticks(np.arange(len(df)))
    ax.set_yticklabels(df.parameter_set, fontsize=7)
    ax.set_xlabel(r"decay constant $\gamma$ (um$^{-1}$)")
    ax.set_title("evanescent decay vs parameters")
    fig.suptitle("E6 - parameter sensitivity", y=1.02)
    _save(fig, "fig13_sensitivity", svg=True)


# -------------------------------------------------------------------- fig 14
def fig_crossing_vs_crosstalk():
    df = pd.read_csv(OPT / "crosstalk_per_route.csv")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    ax = axes[0]
    ax.scatter(df.n_crossings, df.total_leakage_from_db, s=14, alpha=0.65,
               color="#C44E52")
    ax.set_xlabel("geometric crossings on route")
    ax.set_ylabel("total predicted crosstalk (dB)")
    ax.set_title("crossing count vs optical crosstalk")
    ax = axes[1]
    ax.scatter(df.L_total_mm, df.loss_base_db, s=10, alpha=0.6, color="#4C72B0")
    ax.set_xlabel("route length (mm)")
    ax.set_ylabel("propagation loss (dB)")
    ax.set_title("length vs loss")
    fig.suptitle("E5/E6 - is the 1283-crossing count a proxy for optical risk?",
                 y=1.02)
    _save(fig, "fig14_crossing_vs_crosstalk", svg=True)


def generate_all():
    fns = [fig_length_distribution, fig_loss_distribution, fig_mode_fields,
           fig_mode_convergence, fig_coupling_vs_separation,
           fig_crosstalk_vs_length, fig_crosstalk_matrix, fig_route_ranking,
           fig_layer_risk, fig_crossing_angles, fig_3d_hotspots,
           fig_hotspot_zoom, fig_sensitivity, fig_crossing_vs_crosstalk]
    done = []
    for fn in fns:
        try:
            fn()
            done.append(fn.__name__)
            print(f"  ok {fn.__name__}")
        except Exception as exc:                    # pragma: no cover
            print(f"  FAIL {fn.__name__}: {exc}")
    return done
