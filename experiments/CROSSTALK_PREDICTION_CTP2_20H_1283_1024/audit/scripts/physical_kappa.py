"""Independent physical coupling coefficient kappa(d) for the CTP-1.0 EIM structure.

The crossing FDFD uses the effective-index structure of `modes.effective_index_model`:
a 2-level in-plane index (n_slab inside a strip of width w, n_clad outside).
In that EIM world a 'guide' is a 1-D slab of width w and core index n_slab, and
a parallel displacement of the second guide by d (lateral OR vertical - the
structure is in-plane isotropic) gives the standard perturbative coupling

    kappa(d) = k0^2/(2 beta) * (n_slab^2 - n_clad^2) *
               int_{-w/2}^{w/2} phi(u+d) phi(u) du          [1/um]

with int phi^2 du = 1.  This is evaluated on a large 1-D domain (no shift-invert
noise, no extrapolation) and is fully independent of the legacy supermode code.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import eigsh

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_lib as AL


def inplane_eim_mode(optics: dict, half_um: float = 120.0, h: float = 0.05,
                     tol: float = 1e-13):
    eim = AL.crossing_eim(optics)
    k0 = eim.k0
    n0 = float(optics["n_clad"])
    ns = float(eim.n_slab)
    w = float(optics["core_width_um"])
    n = int(round(2 * half_um / h)) + 1
    x = (np.arange(n) - (n - 1) / 2.0) * h
    n2 = np.where(np.abs(x) <= w / 2.0, ns ** 2, n0 ** 2)
    m = n - 2
    main = -2.0 * np.ones(m) / h ** 2
    off = np.ones(m - 1) / h ** 2
    A = sp.diags([main, off, off], [0, 1, -1], format="csc")
    A = (A + sp.diags(k0 ** 2 * n2[1:-1])).tocsc()
    sigma = (k0 * ns) ** 2 * (1.0 - 1e-6)
    vals, vecs = eigsh(A, k=3, sigma=sigma, which="LM", tol=tol, maxiter=80000)
    order = np.argsort(vals)[::-1]
    vals, vecs = vals[order], vecs[:, order]
    beta_plain = np.sqrt(np.clip(vals, 0.0, None))
    if not (beta_plain[0] / k0 > n0):
        raise RuntimeError("no guided EIM mode")
    p = vecs[:, 0]
    phi = np.zeros(n)
    phi[1:-1] = p / math.sqrt(float(np.sum(p ** 2)) * h)
    return {"x": x, "phi": phi, "h": h, "Lambda": float(vals[0]),
            "beta": float(beta_plain[0]), "n_eff": float(beta_plain[0] / k0),
            "k0": k0, "n0": n0, "ns": ns, "w": w,
            "gamma": float(math.sqrt(max(beta_plain[0] ** 2 - (k0 * n0) ** 2, 0.0)))}


def kappa_eim(optics: dict, d_um, mode: dict | None = None) -> np.ndarray:
    """kappa(d) in mm^-1 for the EIM 2-level structure."""
    m = mode if mode is not None else inplane_eim_mode(optics)
    x, phi, h = m["x"], m["phi"], m["h"]
    interp = lambda q: np.interp(q, x, phi, left=0.0, right=0.0)
    d_arr = np.atleast_1d(np.asarray(d_um, float))
    w = m["w"]
    # int_{|u|<=w/2} phi(u+d) phi(u) du
    u = np.arange(-w / 2.0, w / 2.0 + 1e-12, h)
    out = np.empty(d_arr.size)
    for i, d in enumerate(d_arr):
        out[i] = np.trapezoid(interp(u + d) * interp(u), u)
    pref = m["k0"] ** 2 / (2.0 * m["beta"]) * (m["ns"] ** 2 - m["n0"] ** 2)
    kap_per_um = pref * out
    kap_mm = kap_per_um * 1e3
    return kap_mm if np.ndim(d_um) else float(kap_mm[0])


def kappa_asymptotic(optics: dict, d_um, fit_lo: float = 10.0,
                     fit_hi: float = 15.0, mode: dict | None = None):
    """kappa0*exp(-gamma*d) with gamma = sqrt(beta^2-(k0 n_clad)^2) and kappa0
    fixed by the overlap integral at d in [fit_lo, fit_hi]."""
    m = mode if mode is not None else inplane_eim_mode(optics)
    gamma = m["gamma"]
    ds = np.array([fit_lo, 0.5 * (fit_lo + fit_hi), fit_hi])
    ks = np.atleast_1d(kappa_eim(optics, ds, m))
    k0_fit = np.exp(np.mean(np.log(ks) + gamma * ds))     # ks = k0 exp(-gamma d)
    out = k0_fit * np.exp(-gamma * np.atleast_1d(np.asarray(d_um, float)))
    return (out if np.ndim(d_um) else float(out[0])), float(k0_fit), float(gamma)


def cmt_crossing(mode_dict, beta: float, theta_deg: float, optics: dict = None,
                 s_max_factor: float = 40.0) -> dict:
    """First-order CMT crossing amplitude A = int kappa(|s| sin t) exp(-i db s) ds.

    This is the formula of legacy crossing.py::crossing_cmt, but with the
    converged 1-D EIM kappa(d) (no supermode noise, no d_lo clamp).
    Only the +s (phase-matched, forward) arm is retained; the -s arm is
    phase-mismatched by 2 beta and is negligible for theta -> 0.
    """
    th = math.radians(theta_deg)
    sin_t = max(math.sin(th), 1e-12)
    s_max = s_max_factor / max(mode_dict["gamma"] * sin_t, 1e-12)
    s_max = min(s_max, 5000.0)
    s = np.arange(-s_max, s_max + 1e-9, 0.02)
    d = np.abs(s) * sin_t
    kap = np.asarray(kappa_eim(optics, d, mode_dict))
    dbeta = beta * (1.0 - math.cos(th))
    amp = np.trapezoid(kap * np.exp(-1j * dbeta * s), s) * 1e-3
    P = float(abs(amp) ** 2)
    return {"theta_deg": theta_deg, "amplitude": float(abs(amp)),
            "T_cross": P, "T_cross_db": AL.db(P),
            "unitarised": float(math.sin(min(abs(amp), math.pi / 2)) ** 2),
            "s_max_um": float(s_max), "dbeta_per_um": float(dbeta),
            "valid_weak_coupling": bool(abs(amp) < 0.3)}


def load_or_build_kappa(optics: dict):
    p = AL.CACHE / "kappa_eim_1d.npz"
    if p.exists():
        d = np.load(p)
        return {k: (d[k] if d[k].ndim else float(d[k])) for k in d.files}
    mode = inplane_eim_mode(optics)
    ds = np.concatenate([np.arange(0.0, 30.01, 0.5), np.arange(31.0, 120.1, 1.0)])
    ks = kappa_eim(optics, ds, mode)
    np.savez(p, x=mode["x"], phi=mode["phi"], d_um=ds, kappa_mm=ks,
             beta=np.float64(mode["beta"]), Lambda=np.float64(mode["Lambda"]),
             n_eff=np.float64(mode["n_eff"]), gamma=np.float64(mode["gamma"]),
             k0=np.float64(mode["k0"]), n0=np.float64(mode["n0"]),
             ns=np.float64(mode["ns"]), w=np.float64(mode["w"]),
             h=np.float64(mode["h"]))
    d = np.load(p)
    return {k: (d[k] if d[k].ndim else float(d[k])) for k in d.files}


def legacy_cmt_reported(optics=None) -> dict:
    """CMT values actually reported by the legacy run (outputs/optical)."""
    import csv
    path = Path(AL.LEGACY) / "outputs" / "optical" / "crossing_transfer_curve.csv"
    out = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[float(row["theta_deg"])] = float(row["T_cross_cmt"])
    return out
