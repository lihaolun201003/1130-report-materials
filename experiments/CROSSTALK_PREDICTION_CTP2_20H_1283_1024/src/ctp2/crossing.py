"""Local crossing model database: independent methods and their comparison.

Methods implemented here
------------------------
``born_2d``   first-order (Born / weak-scattering) amplitude of the same
              in-plane problem, evaluated by direct 2-D quadrature:

                  a_cross = -i k0^2/(2 beta) int int_{guide2} (n^2 - n_bg^2)
                             psi_1(r) psi_2^*(r) dA

              with psi_1 = phi_1(y) exp(i beta x) and
              psi_2 = phi_2(s) exp(i beta q), (x,y) = (q cos t - s sin t,
              q sin t + s cos t).  This is *exact* to first order in the index
              perturbation; its relative error is O(|a|), so it is trustworthy
              for |a| << 1 (crossings above ~10 deg) and is used precisely there.
              CTP-1.0's ``crossing_born`` collapsed this double integral to
              ``Phi(q)^2 / sin(t)`` which is **wrong** (the second factor must be
              the transform of the mode over guide 2's core, not over the whole
              line); the numerical quadrature used here avoids that error.

``bpm2d``     split-step BPM (see :mod:`ctp2.bpm`), authoritative for 1-20 deg.
``bpm3d``     full 3-D split-step BPM, used to quantify the effective-index error.
``fdfd2d``    corrected 2-D FDFD (see :mod:`ctp2.fdfd2d`), authoritative for
              large angles where a small domain suffices.

Every entry in the database carries ``method``, ``validity``, ``uncertainty_db``
and the numerical diagnostics needed to judge it.  No value is silently
replaced by a floor.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .optics import EIM


# ---------------------------------------------------------------- Born kernel
def born_crossing_2d(eim: EIM, theta_deg: float, n_q: int = 4001,
                     n_s: int = 601) -> dict:
    """First-order scattered amplitude into the forward mode of the cross arm."""
    th = math.radians(theta_deg)
    sin_t, cos_t = math.sin(th), math.cos(th)
    beta = eim.beta
    k0 = eim.k0
    w = eim.core_w_um
    phi = eim.phi
    s_ax = eim.s
    dn2 = eim.n_slab ** 2 - eim.n_clad ** 2

    # transverse samples inside guide 2's core
    s = np.linspace(-w / 2.0, w / 2.0, n_s)
    phi_s = np.interp(s, s_ax, phi, left=0.0, right=0.0)
    # longitudinal range: |psi_1| decays on 1/gamma, so +-40 um is ample
    Lq = 40.0
    q = np.linspace(-Lq, Lq, n_q)
    dq = q[1] - q[0]
    ds = s[1] - s[0]

    Q, S = np.meshgrid(q, s, indexing="ij")          # (n_q, n_s)
    X = Q * cos_t - S * sin_t
    Y = Q * sin_t + S * cos_t
    phi_1 = np.interp(Y, s_ax, phi, left=0.0, right=0.0)
    phase = np.exp(1j * beta * (X - Q))
    integrand = dn2 * phi_1 * phi_s[None, :] * phase
    I = np.sum(integrand) * dq * ds
    a = -1j * (k0 ** 2 / (2.0 * beta)) * I
    amp = float(abs(a))
    return {
        "theta_deg": float(theta_deg),
        "amplitude_born": amp,
        "T_cross_born": float(amp ** 2),
        "T_cross_born_db": float(10 * math.log10(max(amp ** 2, 1e-300))),
        "born_expansion_parameter": amp,
        "expected_relative_error": float(min(1.0, amp)),
        "method": "born_2d_quadrature",
        "regime": ("weak" if amp < 0.05 else
                   "moderate" if amp < 0.3 else "strong_invalid"),
    }


# ------------------------------------------------- multichannel port S-matrix
def born_multimode_2d(eim: EIM, theta_deg: float, n_q: int = 3001,
                      n_s: int = 401, n_modes: int = 1) -> dict:
    """Born amplitudes between the guided modes of the two arms.

    The in-plane EIM structure is single-mode, so only m=n=0 exists here; the
    multi-mode analysis is done with the full 3-D channel (§V6) where the guide
    really is 3-mode.  This function therefore documents the single-mode result
    and returns the (0,0) element of the S matrix.
    """
    r = born_crossing_2d(eim, theta_deg, n_q=n_q, n_s=n_s)
    return {"theta_deg": float(theta_deg),
            "S": {(0, 0): r["amplitude_born"]},
            "T": {(0, 0): r["T_cross_born"]},
            "method": "born_multimode_2d (single in-plane mode)"}


# -------------------------------------------------------------- model chooser
@dataclass
class CrossingModel:
    """Piecewise-validated T_cross(theta) with an explicit uncertainty."""

    rows: list = field(default_factory=list)
    angles: np.ndarray = None
    t_cross_nominal: np.ndarray = None
    t_cross_low: np.ndarray = None
    t_cross_high: np.ndarray = None
    method_per_angle: list = field(default_factory=list)
    uncertainty_db: np.ndarray = None

    def __post_init__(self):
        rows = sorted(self.rows, key=lambda r: r["theta_deg"])
        self.angles = np.array([r["theta_deg"] for r in rows])
        self.t_cross_nominal = np.array([r["T_cross_nominal"] for r in rows])
        self.t_cross_low = np.array([r["T_cross_low"] for r in rows])
        self.t_cross_high = np.array([r["T_cross_high"] for r in rows])
        self.method_per_angle = [r["method"] for r in rows]
        self.uncertainty_db = np.array([r["uncertainty_db"] for r in rows])

    def evaluate(self, theta_deg):
        """Log-linear interpolation in theta between database nodes."""
        th = np.atleast_1d(np.asarray(theta_deg, float))
        out_n = np.empty_like(th)
        out_lo = np.empty_like(th)
        out_hi = np.empty_like(th)
        for arr, key in ((out_n, self.t_cross_nominal),
                         (out_lo, self.t_cross_low),
                         (out_hi, self.t_cross_high)):
            arr[:] = np.exp(np.interp(np.log(np.clip(th, 1e-6, None)),
                                      np.log(self.angles),
                                      np.log(np.maximum(key, 1e-300))))
        return (float(out_n[0]) if np.ndim(theta_deg) == 0 else out_n,
                float(out_lo[0]) if np.ndim(theta_deg) == 0 else out_lo,
                float(out_hi[0]) if np.ndim(theta_deg) == 0 else out_hi)

    def as_rows(self) -> list[dict]:
        return self.rows
