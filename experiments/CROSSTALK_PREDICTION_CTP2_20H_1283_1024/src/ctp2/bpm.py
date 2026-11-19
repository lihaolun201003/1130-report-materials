"""Split-step Fourier BPM (2-D effective-index and full 3-D scalar).

Solves the scalar paraxial envelope equation

    dA/dz = i/(2 beta0) * ( lap_perp A + k0^2 (n^2 - n_ref^2) A ),
    psi = A exp(i beta0 z)

with the symmetric (Strang) split-step scheme: half index step, full-step
diffraction in Fourier space, half index step (second order in dz).

Port analysis for a *tilted* arm
--------------------------------
For an arm whose axis is tilted by ``phi`` from the propagation (z) axis the
guided field is ``psi = a phi((x-xc)cos phi) exp(i beta (x sin phi + z cos phi))``.
The paraxial equation is invariant under the shear ``x -> x - z tan phi``, so the
projected index profile (width ``w/cos phi``) is the *exact* paraxial structure
of a tilted strip.  The orthonormal port function is

    u(x) = sqrt(cos phi) phi((x-xc)cos phi) exp(i beta sin phi (x-xc)),
    int |u|^2 dx = 1,  power of the mode = |<u|A>|^2,

which is the correct normalisation for a tilted port (CTP-1.0 normalised tilted
ports as if they were untilted, a factor ~cos(theta) error in power).

Limitations (documented, tested): the paraxial approximation is excellent for
phi <~ 15 deg and degrades as O(phi^4) in the phase; the method has no
back-reflection and no wide-angle correction, so crossings above ~30 deg are
NOT computed with BPM (they are handled by the 2-D FDFD solver).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .optics import EIM, solve_channel
from .params import Optics


# --------------------------------------------------------------------- helpers
def _next_pow2(n: int) -> int:
    return 1 << int(math.ceil(math.log2(max(n, 2))))


def absorbing_mask(n: int, width: int, strength: float = 14.0,
                   power: float = 3.0) -> np.ndarray:
    m = np.ones(n)
    if width <= 0:
        return m
    t = np.linspace(0.0, 1.0, width, endpoint=False)
    prof = np.exp(-strength * t ** power)
    m[:width] = prof[::-1]
    m[-width:] = prof
    return m


def _edges(coord: np.ndarray) -> np.ndarray:
    e = np.empty(len(coord) + 1)
    e[1:-1] = 0.5 * (coord[1:] + coord[:-1])
    e[0] = coord[0] - 0.5 * (coord[1] - coord[0])
    e[-1] = coord[-1] + 0.5 * (coord[-1] - coord[-2])
    return e


def _strip_fraction(edges: np.ndarray, xc: float, hw: float, d: float) -> np.ndarray:
    lo = np.maximum(edges[:-1], xc - hw)
    hi = np.minimum(edges[1:], xc + hw)
    return np.clip((hi - lo) / d, 0.0, 1.0)


def sample_avg_1d(func, x: np.ndarray, xc: float, dx: float, sub: int = 4):
    """Cell-averaged sampling of a 1-D profile (anti-aliasing low-pass filter).

    Point sampling of a mode whose evanescent tail is not band-limited to the
    grid injects spurious high-k content that radiates and shows up as a fake
    loss of ~1 %.  Averaging over 4 sub-cells per grid cell removes it.
    """
    acc = 0.0
    for i in range(sub):
        acc = acc + func(x - xc + (-0.5 + (i + 0.5) / sub) * dx)
    return acc / sub


def sample_avg_2d(func, x: np.ndarray, y: np.ndarray, xc: float, yc: float,
                  dx: float, dy: float, sub: int = 3):
    X, Y = np.meshgrid(x, y)
    acc = 0.0
    for i in range(sub):
        for j in range(sub):
            acc = acc + func(X - xc + (-0.5 + (i + 0.5) / sub) * dx,
                             Y - yc + (-0.5 + (j + 0.5) / sub) * dy)
    return acc / (sub * sub)


# ------------------------------------------------------------- 2-D BPM kernel
def ssfm_2d(A0: np.ndarray, x: np.ndarray, *, k0: float, n_ref: float,
            beta0: float, z_start: float, dz: float, n_steps: int,
            index_n2, mask: np.ndarray, record_every: int = 0) -> tuple:
    """Symmetric split-step propagation of a 2-D envelope."""
    dx = x[1] - x[0]
    kx = 2.0 * math.pi * np.fft.fftfreq(len(x), d=dx)
    diffract = np.exp(-1j * kx ** 2 * dz / (2.0 * beta0))
    A = np.asarray(A0, complex).copy()
    snaps = []
    z = z_start
    for step in range(n_steps):
        A = A * np.exp(1j * k0 * (index_n2(z) - n_ref ** 2) * (dz / 2.0) / (2.0 * n_ref))
        A = np.fft.ifft(diffract * np.fft.fft(A))
        z += dz
        A = A * np.exp(1j * k0 * (index_n2(z) - n_ref ** 2) * (dz / 2.0) / (2.0 * n_ref))
        A *= mask
        if record_every and step % record_every == 0:
            snaps.append((z, np.abs(A) ** 2))
    return A, snaps


def ssfm_3d(A0: np.ndarray, x: np.ndarray, y: np.ndarray, *, k0: float,
            n_ref: float, beta0: float, z_start: float, dz: float,
            n_steps: int, index_n2, mask: np.ndarray,
            record_every: int = 0) -> tuple:
    dx = x[1] - x[0]
    dy = y[1] - y[0]
    kx = 2.0 * math.pi * np.fft.fftfreq(len(x), d=dx)
    ky = 2.0 * math.pi * np.fft.fftfreq(len(y), d=dy)
    KX, KY = np.meshgrid(kx, ky)
    diffract = np.exp(-1j * (KX ** 2 + KY ** 2) * dz / (2.0 * beta0))
    A = np.asarray(A0, complex).copy()
    snaps = []
    z = z_start
    for step in range(n_steps):
        A = A * np.exp(1j * k0 * (index_n2(z) - n_ref ** 2) * (dz / 2.0) / (2.0 * n_ref))
        A = np.fft.ifft2(diffract * np.fft.fft2(A))
        z += dz
        A = A * np.exp(1j * k0 * (index_n2(z) - n_ref ** 2) * (dz / 2.0) / (2.0 * n_ref))
        A *= mask
        if record_every and step % record_every == 0:
            snaps.append((z, np.abs(A) ** 2))
    return A, snaps


# ------------------------------------------------------------------- results
@dataclass
class Crossing2DResult:
    theta_deg: float
    T_through: float
    T_cross: float
    T_radiation: float
    energy: float
    dx_um: float
    dz_um: float
    half_z_um: float
    n_steps: int
    port_separation_um: float
    status: str = "ok"
    diagnostics: dict = field(default_factory=dict)

    def as_row(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "diagnostics"}
        d["T_cross_db"] = 10 * math.log10(max(self.T_cross, 1e-300))
        d["T_through_db"] = 10 * math.log10(max(self.T_through, 1e-300))
        return d


@dataclass
class Crossing3DResult(Crossing2DResult):
    dy_um: float = 0.0
    nx: int = 0
    ny: int = 0


# -------------------------------------------------------------- 2-D crossing
def run_crossing_2d(eim: EIM, theta_deg: float, *, port_separation_um: float = 50.0,
                    dx_um: float = 0.1, dz_um: float | None = None,
                    margin_um: float | None = None, absorber_um: float = 12.0,
                    absorber_strength: float = 16.0,
                    max_steps: int = 40000) -> Crossing2DResult:
    th = math.radians(theta_deg)
    phi = th / 2.0
    tanp, sinp, cosp = math.tan(phi), math.sin(phi), math.cos(phi)
    w = eim.core_w_um
    n_slab, n0 = eim.n_slab, eim.n_clad
    k0, beta0 = eim.k0, eim.beta

    half_z = port_separation_um / (2.0 * math.tan(phi)) if theta_deg > 1e-6 else 1e5
    if margin_um is None:
        margin_um = max(3.0 * w, 0.30 * port_separation_um)
    half_x = port_separation_um + margin_um
    nx = _next_pow2(int(2 * half_x / dx_um) + 1)
    x = (np.arange(nx) - (nx - 1) / 2.0) * dx_um
    if dz_um is None:
        dz_um = 0.4
    n_steps = int(math.ceil(2 * half_z / dz_um))
    dz = 2 * half_z / n_steps
    ed = _edges(x)
    hw = (w / 2.0) / cosp
    mask = absorbing_mask(nx, int(round(absorber_um / dx_um)), absorber_strength)

    def index_n2(z):
        f = _strip_fraction(ed, +z * tanp, hw, dx_um) + \
            _strip_fraction(ed, -z * tanp, hw, dx_um)
        return n0 ** 2 + np.clip(f, 0.0, 1.0) * (n_slab ** 2 - n0 ** 2)

    def port(xc, tilt, dxs=dx_um):
        def prof_func(xx):
            return np.interp(xx * math.cos(tilt), eim.s, eim.phi, left=0.0,
                             right=0.0)
        prof = sample_avg_1d(prof_func, x, xc, dxs)
        return math.sqrt(math.cos(tilt)) * prof * \
            np.exp(1j * beta0 * math.sin(tilt) * (x - xc))

    A0 = port(-half_z * tanp, +phi).astype(complex)
    P_in = float(np.sum(np.abs(A0) ** 2) * dx_um)
    A, _ = ssfm_2d(A0, x, k0=k0, n_ref=n0, beta0=beta0, z_start=-half_z,
                   dz=dz, n_steps=n_steps, index_n2=index_n2, mask=mask)
    dA = dx_um
    p_th = abs(np.sum(np.conj(port(+half_z * tanp, +phi)) * A) * dA) ** 2 / P_in
    p_cr = abs(np.sum(np.conj(port(-half_z * tanp, -phi)) * A) * dA) ** 2 / P_in
    total = float(np.sum(np.abs(A) ** 2) * dA / P_in)
    return Crossing2DResult(
        theta_deg=float(theta_deg), T_through=float(p_th), T_cross=float(p_cr),
        T_radiation=float(max(0.0, total - p_th - p_cr)), energy=total,
        dx_um=dx_um, dz_um=dz, half_z_um=half_z, n_steps=n_steps,
        port_separation_um=2 * half_z * tanp,
        diagnostics={"nx": nx, "half_x_um": half_x, "n_steps": n_steps},
    )


# -------------------------------------------------------------- 3-D crossing
_CHANNEL_CACHE: dict = {}


def channel_mode(optics: Optics):
    key = (optics.wavelength_nm, optics.n_clad, optics.delta_n, optics.core_w_um,
           optics.core_h_um, optics.profile)
    if key not in _CHANNEL_CACHE:
        sol = solve_channel(optics, half_um=30.0, step_um=0.2, n_modes=3)
        i0 = int(np.argmax(sol.n_eff))
        _CHANNEL_CACHE[key] = (sol.interpolator(i0), float(sol.n_eff[i0]),
                               float(sol.beta[i0]), sol)
    return _CHANNEL_CACHE[key]


def _channel_on_grid(optics: Optics, x: np.ndarray, y: np.ndarray, xc: float,
                     yc: float = 0.0) -> np.ndarray:
    interp, _, _, _ = channel_mode(optics)
    X, Y = np.meshgrid(x, y)
    f = interp(X - xc, Y - yc)
    dA = (x[1] - x[0]) * (y[1] - y[0])
    n = math.sqrt(max(float(np.sum(f ** 2)) * dA, 1e-300))
    return f / n


def run_crossing_3d(optics: Optics, theta_deg: float, *,
                    port_separation_um: float = 40.0,
                    dx_um: float = 0.3, dy_um: float = 0.3,
                    dz_um: float | None = None,
                    margin_um: float | None = None,
                    absorber_um: float = 8.0, absorber_strength: float = 16.0,
                    vertical_offset_um: float = 0.0) -> Crossing3DResult:
    """Full 3-D scalar BPM of two channel waveguides crossing at ``theta_deg``.

    ``vertical_offset_um`` displaces the second guide vertically (cross-layer
    crossing geometry); 0 = same physical routing plane.
    """
    th = math.radians(theta_deg)
    phi = th / 2.0
    tanp, cosp = math.tan(phi), math.cos(phi)
    w, hh = optics.core_w_um, optics.core_h_um
    n0 = optics.n_clad
    _, n_eff_mode, beta0, _ = channel_mode(optics)
    k0 = optics.k0
    beta0 = k0 * n_eff_mode

    half_z = port_separation_um / (2.0 * math.tan(phi)) if theta_deg > 1e-6 else 1e5
    if margin_um is None:
        margin_um = max(3.0 * w, 0.30 * port_separation_um)
    half_x = port_separation_um + margin_um
    half_y = max(2.2 * hh, abs(vertical_offset_um) / 2.0 + 2.0 * hh)
    nx = _next_pow2(int(2 * half_x / dx_um) + 1)
    ny = _next_pow2(int(2 * half_y / dy_um) + 1)
    x = (np.arange(nx) - (nx - 1) / 2.0) * dx_um
    y = (np.arange(ny) - (ny - 1) / 2.0) * dy_um
    if dz_um is None:
        dz_um = 0.6
    n_steps = int(math.ceil(2 * half_z / dz_um))
    dz = 2 * half_z / n_steps
    edx, edy = _edges(x), _edges(y)
    hw = (w / 2.0) / cosp
    hh_half = hh / 2.0
    fy = _strip_fraction(edy, vertical_offset_um / 2.0, hh_half, dy_um) + \
        _strip_fraction(edy, -vertical_offset_um / 2.0, hh_half, dy_um)
    fy = np.clip(fy, 0.0, 1.0)
    mask = np.outer(absorbing_mask(ny, int(round(absorber_um / dy_um)),
                                   absorber_strength),
                    absorbing_mask(nx, int(round(absorber_um / dx_um)),
                                   absorber_strength))
    dn2 = optics.n_core ** 2 - n0 ** 2

    def index_n2(z):
        fx = np.clip(_strip_fraction(edx, +z * tanp, hw, dx_um) +
                     _strip_fraction(edx, -z * tanp, hw, dx_um), 0.0, 1.0)
        return n0 ** 2 + np.outer(fy, fx) * dn2

    f_interp, _, _, _ = channel_mode(optics)

    def port(xc, yc, tilt):
        def pf(xx, yy):
            return f_interp(xx * math.cos(tilt), yy)
        prof = sample_avg_2d(pf, x, y, xc, yc, dx_um, dy_um, sub=3)
        n = math.sqrt(max(float(np.sum(prof ** 2)) * dx_um * dy_um, 1e-300))
        return prof / n * np.exp(1j * beta0 * math.sin(tilt) * (x - xc))[None, :]

    A0 = port(-half_z * tanp, -vertical_offset_um / 2.0, +phi)
    A, _ = ssfm_3d(A0, x, y, k0=k0, n_ref=n0, beta0=beta0, z_start=-half_z,
                   dz=dz, n_steps=n_steps, index_n2=index_n2, mask=mask)
    dA = dx_um * dy_um
    P_in = 1.0
    p_th = abs(np.sum(np.conj(port(+half_z * tanp, +vertical_offset_um / 2.0,
                                  +phi)) * A) * dA) ** 2 / P_in
    p_cr = abs(np.sum(np.conj(port(-half_z * tanp, -vertical_offset_um / 2.0,
                                  -phi)) * A) * dA) ** 2 / P_in
    total = float(np.sum(np.abs(A) ** 2) * dA / P_in)
    return Crossing3DResult(
        theta_deg=float(theta_deg), T_through=float(p_th), T_cross=float(p_cr),
        T_radiation=float(max(0.0, total - p_th - p_cr)), energy=total,
        dx_um=dx_um, dz_um=dz, half_z_um=half_z, n_steps=n_steps,
        port_separation_um=2 * half_z * tanp,
        dy_um=dy_um, nx=nx, ny=ny,
        diagnostics={"half_x_um": half_x, "half_y_um": half_y})


# -------------------------------------------------------- parallel couplers
def run_parallel_2d(eim: EIM, separation_um: float, length_um: float, *,
                    dx_um: float = 0.08, dz_um: float = 0.5,
                    margin_um: float = 25.0) -> dict:
    w = eim.core_w_um
    n_slab, n0 = eim.n_slab, eim.n_clad
    k0, beta0 = eim.k0, eim.beta
    half_x = separation_um / 2.0 + margin_um + 2 * w
    nx = _next_pow2(int(2 * half_x / dx_um) + 1)
    x = (np.arange(nx) - (nx - 1) / 2.0) * dx_um
    ed = _edges(x)
    f = _strip_fraction(ed, -separation_um / 2.0, w / 2.0, dx_um) + \
        _strip_fraction(ed, +separation_um / 2.0, w / 2.0, dx_um)
    n2 = n0 ** 2 + np.clip(f, 0, 1) * (n_slab ** 2 - n0 ** 2)
    n_steps = int(math.ceil(length_um / dz_um))
    dz = length_um / n_steps
    kx = 2.0 * math.pi * np.fft.fftfreq(nx, d=dx_um)
    diffract = np.exp(-1j * kx ** 2 * dz / (2.0 * beta0))
    damp = np.exp(1j * k0 * (n2 - n0 ** 2) * dz / (2.0 * n0))
    mask = absorbing_mask(nx, int(round(8.0 / dx_um)), 16.0)

    def mode(xc):
        prof = np.interp(x - xc, eim.s, eim.phi, left=0.0, right=0.0)
        return prof / math.sqrt(max(float(np.sum(prof ** 2)) * dx_um, 1e-300))

    u1, u2 = mode(-separation_um / 2.0), mode(+separation_um / 2.0)
    A = u1.astype(complex)
    P_in = float(np.sum(np.abs(A) ** 2) * dx_um)
    for _ in range(n_steps):
        A = np.fft.ifft(diffract * np.fft.fft(A * damp))
        A *= mask
    a1 = np.sum(np.conj(u1) * A) * dx_um
    a2 = np.sum(np.conj(u2) * A) * dx_um
    return {"separation_um": separation_um, "length_um": length_um,
            "P_bar": float(abs(a1) ** 2 / P_in),
            "P_cross": float(abs(a2) ** 2 / P_in),
            "total": float(np.sum(np.abs(A) ** 2) * dx_um / P_in),
            "dx_um": dx_um, "dz_um": dz}


def run_parallel_3d(optics: Optics, separation_um: float, length_um: float, *,
                    vertical_offset_um: float = 0.0, dx_um: float = 0.25,
                    dy_um: float = 0.25, dz_um: float = 1.0,
                    margin_um: float = 14.0) -> dict:
    interp, n_eff_mode, _, _ = channel_mode(optics)
    n0 = optics.n_clad
    k0 = optics.k0
    beta0 = k0 * n_eff_mode
    half_x = separation_um / 2.0 + margin_um + optics.core_w_um
    half_y = max(2.2 * optics.core_h_um,
                 abs(vertical_offset_um) / 2.0 + 2.0 * optics.core_h_um)
    nx = _next_pow2(int(2 * half_x / dx_um) + 1)
    ny = _next_pow2(int(2 * half_y / dy_um) + 1)
    x = (np.arange(nx) - (nx - 1) / 2.0) * dx_um
    y = (np.arange(ny) - (ny - 1) / 2.0) * dy_um
    edx, edy = _edges(x), _edges(y)
    fx = _strip_fraction(edx, -separation_um / 2.0, optics.core_w_um / 2.0, dx_um) + \
        _strip_fraction(edx, +separation_um / 2.0, optics.core_w_um / 2.0, dx_um)
    fy = _strip_fraction(edy, vertical_offset_um / 2.0, optics.core_h_um / 2.0, dy_um) + \
        _strip_fraction(edy, -vertical_offset_um / 2.0, optics.core_h_um / 2.0, dy_um)
    n2 = n0 ** 2 + np.clip(np.outer(np.clip(fy, 0, 1), np.clip(fx, 0, 1)), 0, 1) * \
        (optics.n_core ** 2 - n0 ** 2)
    n_steps = int(math.ceil(length_um / dz_um))
    dz = length_um / n_steps
    kx = 2.0 * math.pi * np.fft.fftfreq(nx, d=dx_um)
    ky = 2.0 * math.pi * np.fft.fftfreq(ny, d=dy_um)
    KX, KY = np.meshgrid(kx, ky)
    diffract = np.exp(-1j * (KX ** 2 + KY ** 2) * dz / (2.0 * beta0))
    damp = np.exp(1j * k0 * (n2 - n0 ** 2) * dz / (2.0 * n0))
    mask = np.outer(absorbing_mask(ny, int(round(6.0 / dy_um)), 16.0),
                    absorbing_mask(nx, int(round(6.0 / dx_um)), 16.0))

    def mode(xc):
        X, Y = np.meshgrid(x, y)
        prof = interp(X - xc, Y - vertical_offset_um / 2.0)
        prof = prof / math.sqrt(max(float(np.sum(prof ** 2)) * dx_um * dy_um, 1e-300))
        return prof

    u1, u2 = mode(-separation_um / 2.0), mode(+separation_um / 2.0)
    A = u1.astype(complex)
    P_in = float(np.sum(np.abs(A) ** 2) * dx_um * dy_um)
    for _ in range(n_steps):
        A = np.fft.ifft2(diffract * np.fft.fft2(A * damp))
        A *= mask
    a1 = np.sum(np.conj(u1) * A) * dx_um * dy_um
    a2 = np.sum(np.conj(u2) * A) * dx_um * dy_um
    return {"separation_um": separation_um, "length_um": length_um,
            "vertical_offset_um": vertical_offset_um,
            "P_bar": float(abs(a1) ** 2 / P_in),
            "P_cross": float(abs(a2) ** 2 / P_in),
            "total": float(np.sum(np.abs(A) ** 2) * dx_um * dy_um / P_in),
            "dx_um": dx_um, "dy_um": dy_um, "dz_um": dz}




# ------------------------------------------------ 3-D multimode crossing
def run_crossing_3d_multimode(optics: Optics, theta_deg: float, *,
                              launch_mode: int = 0,
                              port_separation_um: float = 40.0,
                              dx_um: float = 0.25, dy_um: float = 0.25,
                              dz_um: float = 0.6, margin_um: float | None = None,
                              absorber_um: float = 8.0,
                              absorber_strength: float = 16.0) -> dict:
    """Launch one guided mode of arm 1 and project on every guided mode of both arms.

    Returns the mode-resolved power transmission matrix of the crossing, i.e. the
    local S-matrix element magnitudes ``|S_(j,n),(1,m)|^2 = P_out(j,n)/P_in``.
    This is what the specification calls V6: fundamental -> higher order and
    higher order -> fundamental conversion are both measured.
    """
    th = math.radians(theta_deg)
    phi = th / 2.0
    tanp, cosp = math.tan(phi), math.cos(phi)
    w, hh = optics.core_w_um, optics.core_h_um
    n0 = optics.n_clad
    _, n_eff0, _, sol = channel_mode(optics)
    k0 = optics.k0
    ng = int(sol.guided.sum())
    modes = list(range(min(ng, 3)))
    if launch_mode not in modes:
        raise ValueError(f"launch_mode {launch_mode} not guided")
    betas = [float(sol.beta[i]) for i in modes]
    beta0 = betas[0]

    half_z = port_separation_um / (2.0 * math.tan(phi)) if theta_deg > 1e-6 else 1e5
    if margin_um is None:
        margin_um = max(3.0 * w, 0.30 * port_separation_um)
    half_x = port_separation_um + margin_um
    half_y = max(2.2 * hh, 2.0 * hh)
    nx = _next_pow2(int(2 * half_x / dx_um) + 1)
    ny = _next_pow2(int(2 * half_y / dy_um) + 1)
    x = (np.arange(nx) - (nx - 1) / 2.0) * dx_um
    y = (np.arange(ny) - (ny - 1) / 2.0) * dy_um
    n_steps = int(math.ceil(2 * half_z / dz_um))
    dz = 2 * half_z / n_steps
    edx, edy = _edges(x), _edges(y)
    hw = (w / 2.0) / cosp
    fy = np.clip(_strip_fraction(edy, 0.0, hh / 2.0, dy_um), 0.0, 1.0)
    mask = np.outer(absorbing_mask(ny, int(round(absorber_um / dy_um)),
                                   absorber_strength),
                    absorbing_mask(nx, int(round(absorber_um / dx_um)),
                                   absorber_strength))
    dn2 = optics.n_core ** 2 - n0 ** 2

    def index_n2(z):
        fx = np.clip(_strip_fraction(edx, +z * tanp, hw, dx_um) +
                     _strip_fraction(edx, -z * tanp, hw, dx_um), 0.0, 1.0)
        return n0 ** 2 + np.outer(fy, fx) * dn2

    def port(mode, xc, tilt):
        pf = sol.interpolator(mode)

        def wrapped(xx, yy):
            return pf(xx * math.cos(tilt), yy)

        prof = sample_avg_2d(wrapped, x, y, xc, 0.0, dx_um, dy_um, sub=3)
        nn = math.sqrt(max(float(np.sum(prof ** 2)) * dx_um * dy_um, 1e-300))
        return prof / nn * np.exp(1j * betas[mode] * math.sin(tilt) * (x - xc))[None, :]

    A0 = port(launch_mode, -half_z * tanp, +phi)
    A, _ = ssfm_3d(A0, x, y, k0=k0, n_ref=n0, beta0=beta0, z_start=-half_z,
                   dz=dz, n_steps=n_steps, index_n2=index_n2, mask=mask)
    dA = dx_um * dy_um
    total = float(np.sum(np.abs(A) ** 2) * dA)
    out = {}
    for name, sgn in (("through_arm1", +1.0), ("cross_arm2", -1.0)):
        for m in modes:
            u = port(m, sgn * half_z * tanp, sgn * phi)
            a = np.sum(np.conj(u) * A) * dA
            out[f"{name}_mode{m}"] = float(abs(a) ** 2)
    return {"theta_deg": float(theta_deg), "launch_mode": int(launch_mode),
            "guided_modes": modes, "P": out, "energy": total,
            "dx_um": dx_um, "dy_um": dy_um, "dz_um": dz,
            "half_z_um": half_z, "port_separation_um": 2 * half_z * tanp}
