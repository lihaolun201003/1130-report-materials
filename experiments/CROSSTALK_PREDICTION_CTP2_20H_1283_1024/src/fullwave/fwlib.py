"""Independent scalar time-domain full-wave (FDTD) solver for weakly-guided glass
waveguides.  Deliberately written from scratch (no reuse of any FDFD code).

Physics solved:
    2-D in-plane (EIM):   d2(psi)/dt2 = (c/n(x,y))^2 lap(psi)
    3-D scalar:           d2(psi)/dt2 = (c/n(x,y,z))^2 lap(psi)

Scheme
    * explicit leapfrog in time
    * 2nd / 4th / 6th / 8th order central spatial stencils (order is a parameter)
    * graded damping ("sponge") absorbing layers:  psi_tt + 2 sigma psi_t = ...
      sigma(x,y,z) = sum_i sigma_i(x_i) is a separable cubic-in-depth ramp; this is
      a *lossy-layer* absorber, NOT a PML.  Its reflectivity is measured explicitly
      in the validation runs (see run_2d_validation.py).
    * soft mode-shaped source line fed by a smoothly ramped sinusoid
    * port analysis by complex DFT of (psi, dpsi/dn) and projection on the discrete
      eigenmode of the *same discrete operator* the solver uses (so that forward /
      backward splitting is consistent with the numerical dispersion of the scheme)
    * power flux from the scalar Poynting vector S = -psi_t grad(psi)
    * everything is done in SI units.

Torch-CUDA is used only as an accelerator.  A NumPy reference implementation of
one step (identical formulas, float64) is provided and cross-checked in the
validation script.  All runs are reproducible from the scripts in this directory.

Author: independent implementation produced for the CTP2 crosstalk study.
"""
import json
import os
import time

import numpy as np
import torch
import torch.nn.functional as F
from scipy import optimize, sparse
from scipy.sparse.linalg import eigsh

# ----------------------------------------------------------------------------- 
# constants / problem definition
# -----------------------------------------------------------------------------
C0 = 299792458.0
LAM0 = 1.31e-6
K0 = 2.0 * np.pi / LAM0
OMEGA0 = K0 * C0
N_CLAD = 1.500
N_CORE = 1.5065           # 3-D channel core index
W_CORE = 9e-6             # square core width
N_SLAB = 1.5055213        # EIM slab index for the 2-D in-plane problem
W_SLAB = 9e-6
NEFF2D_TARGET = 1.504585
NEFF3D_TARGET = 1.504557
GAMMA_TARGET = 0.597e6    # 1/m, target tail decay constant quoted in the task
GAMMA3D_TARGET = 0.56e6


# -----------------------------------------------------------------------------
# finite difference stencils
# -----------------------------------------------------------------------------
def fd2_coeffs(order):
    """Coefficients c[k], k=0..m of the 1-D central 2nd-derivative stencil:
    d2f/dx2 ~= sum_k c[k]*(f[i-k]+f[i+k])/dx^2   (k=0 term not doubled)."""
    if order == 2:
        return np.array([-2.0, 1.0])
    if order == 4:
        return np.array([-30.0 / 12.0, 16.0 / 12.0, -1.0 / 12.0])
    if order == 6:
        return np.array([-49.0 / 18.0, 3.0 / 2.0, -3.0 / 20.0, 1.0 / 90.0])
    if order == 8:
        return np.array([-205.0 / 72.0, 8.0 / 5.0, -1.0 / 5.0, 8.0 / 315.0, -1.0 / 560.0])
    raise ValueError(order)


def fd1_coeffs(order):
    """Coefficients d[k], k=1..m of the first derivative:
    df/dx ~= sum_{k>=1} d[k]*(f[i+k]-f[i-k])/dx."""
    if order == 2:
        return np.array([0.5])
    if order == 4:
        return np.array([8.0 / 12.0, -1.0 / 12.0])
    if order == 6:
        return np.array([3.0 / 4.0, -3.0 / 20.0, 1.0 / 60.0])
    if order == 8:
        return np.array([4.0 / 5.0, -1.0 / 5.0, 4.0 / 105.0, -1.0 / 280.0])
    raise ValueError(order)


def eigmax_fd2(order):
    """largest |eigenvalue| of the dimensionless 1-D stencil (at theta=pi)."""
    c = fd2_coeffs(order)
    m = len(c) - 1
    return abs(c[0] + 2.0 * np.sum([c[k] * (-1.0) ** k for k in range(1, m + 1)]))


def cfl_smax(order, ndim):
    """max Courant number S = c*dt/(n*dx) for the leapfrog + order stencil scheme."""
    return np.sqrt(4.0 / (ndim * eigmax_fd2(order)))


def lam_fd2(theta, order):
    """dimensionless eigenvalue of the 1-D 2nd-derivative stencil at phase theta."""
    c = fd2_coeffs(order)
    m = len(c) - 1
    return c[0] + 2.0 * np.sum([c[k] * np.cos(k * theta) for k in range(1, m + 1)])


def beta_from_stencil_eig(s, dx, order):
    """Given the transverse eigenproblem eigenvalue s = -lambda_x (1/m^2), return
    beta (1/m) of the discrete mode according to the exact stencil dispersion:
    -lam_fd2(beta*dx) = s*dx^2."""
    target = s * dx * dx
    A = lambda th: -lam_fd2(th, order)
    hi = 3.05
    # A(theta) increases from 0; make sure the bracket contains the root
    while A(hi) < target and hi < np.pi - 1e-6:
        hi = min(hi * 1.3, np.pi - 1e-6)
    return optimize.brentq(lambda th: A(th) - target, 1e-12, hi) / dx


def beta_deriv_fd(beta, dx, order):
    """Eigenvalue of the discrete first-derivative stencil applied to exp(i beta x),
    i.e. D exp(i beta x) = i * beta_d * exp(i beta x).  Used in port splitting so
    that forward/backward decompositions are exact for discrete modes."""
    d = fd1_coeffs(order)
    tot = 0.0
    for k, dk in enumerate(d, start=1):
        tot += dk * np.sin(k * beta * dx)
    return 2.0 * tot / dx


# -----------------------------------------------------------------------------
# analytic symmetric slab mode (continuous operator)
# -----------------------------------------------------------------------------
def slab_analytic(n_core, n_clad, w, lam=LAM0, mode=0):
    """Solve the scalar symmetric-slab transcendental equation.
    Returns dict with neff, beta, kappa (core transverse wavenumber),
    gamma (cladding decay), u, v.  mode=0 fundamental (even), 1 first odd, ..."""
    k0 = 2.0 * np.pi / lam
    V = k0 * w / 2.0 * np.sqrt(n_core ** 2 - n_clad ** 2)

    def eve(u):   # even modes: u tan u = v
        return u * np.tan(u) - np.sqrt(max(V * V - u * u, 0.0))

    def odd(u):   # odd modes: -u cot u = v
        return -u / np.tan(u) - np.sqrt(max(V * V - u * u, 0.0))

    # roots of u tan u = v: fundamental in (0,pi/2), higher even modes in successive
    # intervals separated by the odd-mode cutoffs pi/2, pi, 3pi/2, ...
    kind = 'e' if mode % 2 == 0 else 'o'
    branch = mode // 2
    if kind == 'e':
        lo = 1e-9 if branch == 0 else np.pi * branch + 1e-9
        hi = np.pi / 2 * (2 * branch + 1) - 1e-9
    else:
        lo = np.pi / 2 * (2 * branch + 1) + 1e-9
        hi = np.pi * (branch + 1) - 1e-9
    f = eve if kind == 'e' else odd
    u = optimize.brentq(f, lo, hi, xtol=1e-14)
    v = np.sqrt(max(V * V - u * u, 0.0))
    kappa = 2.0 * u / w
    gamma = 2.0 * v / w
    beta = np.sqrt(k0 ** 2 * n_core ** 2 - kappa ** 2)
    return dict(neff=beta / k0, beta=beta, kappa=kappa, gamma=gamma, u=u, v=v,
                V=V, n_core=n_core, n_clad=n_clad, w=w, mode=mode)


def slab_profile(y, sol):
    """Analytic mode profile (arbitrary but fixed normalisation = 1 at the core
    centre).  y in metres, scalar or array."""
    y = np.asarray(y)
    w, kap, gam = sol['w'], sol['kappa'], sol['gamma']
    ay = np.abs(y)
    core = ay <= w / 2.0
    val = np.where(core,
                   np.cos(kap * y),
                   np.cos(kap * w / 2.0) * np.exp(-gam * (ay - w / 2.0)))
    return val


def fw_slab_analytic(w=W_SLAB):
    """analytic fundamental mode of the 2-D in-plane EIM slab."""
    return slab_analytic(N_SLAB, N_CLAD, w)


fw_slab_profile = slab_profile


# -----------------------------------------------------------------------------
# discrete eigenmode solvers (modes of the *numerically discretised* operator)
# -----------------------------------------------------------------------------
def _build_L1(N, dx, order):
    """1-D discrete 2nd-derivative operator (sparse), Dirichlet (zero) outside."""
    c = fd2_coeffs(order)
    m = len(c) - 1
    rows, cols, vals = [], [], []
    for i in range(N):
        for k in range(0, m + 1):
            cl = c[k] / (dx * dx)
            if k == 0:
                rows.append(i); cols.append(i); vals.append(cl)
            else:
                if i + k < N:
                    rows.append(i); cols.append(i + k); vals.append(cl)
                if i - k >= 0:
                    rows.append(i); cols.append(i - k); vals.append(cl)
    return sparse.csr_matrix((vals, (rows, cols)), shape=(N, N))


def discrete_mode_1d(axes, n_prof, dx, order, omega_eff, n_modes=6):
    """Lowest-loss guided mode of the discretised 1-D transverse problem.
    Returns (s, phi, diag) where s = -lambda_x > 0 (1/m^2) and phi normalised so
    that sum(phi^2)*dx == 1 (i.e. int |phi|^2 dy = 1)."""
    N = len(axes[0])
    L = _build_L1(N, dx, order)
    npro = np.asarray(n_prof, dtype=np.float64)
    M = (L + sparse.diags((omega_eff / C0) ** 2 * npro ** 2)).toarray()
    M = 0.5 * (M + M.T)
    vals, vecs = np.linalg.eigh(M)
    idx = np.argsort(vals)[::-1][:n_modes]
    best = None
    for j in idx:
        s = vals[j]
        phi = vecs[:, j]
        if s <= 0:
            continue
        # guided-mode test: localised inside the core, tiny at the domain edge
        edge = max(abs(phi[0]), abs(phi[-1]))
        mid = np.max(np.abs(phi))
        if mid <= 0:
            continue
        if edge / mid < 1e-3:
            if best is None or s > best[0]:
                best = (s, phi)
            break
    if best is None:
        raise RuntimeError('no guided discrete mode found')
    s, phi = best
    phi = phi / np.sqrt(np.sum(phi ** 2) * dx)
    if phi[int(np.argmax(np.abs(phi)))] < 0:
        phi = -phi
    return s, phi


def discrete_mode_2d(axes, n_prof2, dx, order, omega_eff, n_modes=24):
    """Guided mode of the discretised 2-D transverse problem (for the 3-D solver).
    axes = (ax_a, ax_b); n_prof2 shape (Na,Nb); returns s, phi(shape Na,Nb)
    normalised so sum(phi^2)*dx^2 = 1.

    The largest eigenvalues of the shifted operator form a quasi-continuum of
    box modes; the guided mode is identified as the most strongly *localised*
    eigenvector (smallest boundary/peak ratio), which is unambiguous because the
    guided mode is exponentially small at the box boundary."""
    Na, Nb = len(axes[0]), len(axes[1])
    La = _build_L1(Na, dx, order)
    Lb = _build_L1(Nb, dx, order)
    I = sparse.identity
    L2 = (sparse.kron(I(Nb), La) + sparse.kron(Lb, I(Na))).tocsr()
    d = (omega_eff / C0) ** 2 * (np.asarray(n_prof2, dtype=np.float64).ravel() ** 2)
    M = (L2 + sparse.diags(d)).tocsr()
    vals, vecs = eigsh(M, k=n_modes, which='LA')
    best = None
    for j in np.argsort(vals)[::-1]:
        s = vals[j]
        if s <= 0:
            continue
        phi = vecs[:, j].reshape(Na, Nb)
        mx = np.max(np.abs(phi))
        if mx <= 0:
            continue
        edge = max(abs(phi[0, :]).max(), abs(phi[-1, :]).max(),
                   abs(phi[:, 0]).max(), abs(phi[:, -1]).max())
        ratio = edge / mx
        if ratio > 1e-2:
            continue
        if best is None or ratio < best[0]:
            best = (ratio, s, phi)
    if best is not None:
        _, s, phi = best
        phi = phi / np.sqrt(np.sum(phi ** 2) * dx * dx)
        if phi[np.unravel_index(np.argmax(np.abs(phi)), phi.shape)] < 0:
            phi = -phi
        return s, phi
    raise RuntimeError('no guided discrete mode found')


# -----------------------------------------------------------------------------
# grid + geometry
# -----------------------------------------------------------------------------
class Grid:
    """Uniform Cartesian grid with zero-padded borders (order//2 cells) and a
    separable graded lossy-layer absorber outside the "physical" box."""

    def __init__(self, phys, t_abs, dx, order, n_core=N_CORE, n_clad=N_CLAD,
                 A_abs=7.0, m_abs=3.0, n_min=N_CLAD, S_factor=0.90):
        self.ndim = len(phys)
        self.dx = dx
        self.order = order
        self.pad = order // 2
        self.phys = [tuple(map(float, p)) for p in phys]
        self.t_abs = float(t_abs)
        self.n_core = float(n_core)
        self.n_clad = float(n_clad)
        self.A_abs = float(A_abs)
        self.m_abs = float(m_abs)
        lo = [p[0] - self.t_abs for p in self.phys]
        hi = [p[1] + self.t_abs for p in self.phys]
        self.Nphys = [int(round((hi[i] - lo[i]) / dx)) + 1 for i in range(self.ndim)]
        self.N = [int(self.Nphys[i] + 2 * self.pad) for i in range(self.ndim)]
        self.axes = [lo[i] + (np.arange(self.N[i], dtype=np.float64) - self.pad) * dx
                     for i in range(self.ndim)]
        # physical-box index range in the full array
        self.i_phys = []
        for i in range(self.ndim):
            a = self.pad + int(round(self.t_abs / dx))
            b = self.pad + self.Nphys[i] - 1 - int(round(self.t_abs / dx))
            self.i_phys.append((a, b))
        # CFL
        self.S_max = cfl_smax(order, self.ndim)
        self.S = S_factor * self.S_max
        self.S_factor = S_factor
        self.dt = self.S * dx * n_min / C0
        self.omega_eff = 2.0 / self.dt * np.sin(OMEGA0 * self.dt / 2.0)
        self.sigma_max = self.A_abs * (self.m_abs + 1.0) * C0 / (n_core * self.t_abs)

    def coords(self):
        """broadcastable coordinate arrays for building index fields."""
        return self.axes

    # ------------------------------------------------------------------ index
    @staticmethod
    def _area_above_frac(fac, p, q):
        """Normalised area fraction of the unit square (cell) with n.r > t, where
        fac = t/h (h = half cell), n = (p,q) unit normal with p>=q>=0.
        Exact closed form for a square cut by a straight line."""
        fac = np.asarray(fac, dtype=np.float64)
        if q < 1e-9:
            return np.clip((1.0 - fac) / 2.0, 0.0, 1.0)
        def _pos(f):
            f = np.asarray(f, dtype=np.float64)
            out = np.empty_like(f)
            big = f >= (p + q)
            mid = (f >= (p - q)) & ~big
            low = ~big & ~mid
            out[big] = 0.0
            out[mid] = (p + q - f[mid]) ** 2 / (8.0 * p * q)
            out[low] = np.clip((1.0 - f[low] / p) / 2.0, 0.0, 0.5)
            return out
        return np.where(fac >= 0.0, _pos(fac), 1.0 - _pos(-fac))

    def _fill_fraction_slab(self, s_center, w):
        """Fill fraction of a cell (area average) for a slab |s|<w/2, where
        s_center is the signed transverse coordinate at cell centres.  The normal
        of the interfaces is at angle theta from the y axis; p,q are its components
        (passed through self._fill_pq)."""
        h = 0.5 * self.dx
        p, q = self._fill_pq
        a_hi = self._area_above_frac((w / 2.0 - s_center) / h, p, q)
        a_lo = self._area_above_frac((-w / 2.0 - s_center) / h, p, q)
        return ((1.0 - a_hi) * a_lo).astype(np.float32)

    def _fill_fraction_1d(self, zc, z_center, hh):
        """Fill fraction for an axis-aligned slab |z-z_center|<hh along an axis
        (no area averaging needed except sub-cell shift)."""
        h = 0.5 * self.dx
        return np.clip((hh - np.abs(zc - z_center) + h) / self.dx, 0.0, 1.0).astype(np.float32)

    def build_index(self, guides, antialias=True):
        """guides: list of dicts.
        2-D: {'p':(x,y), 'angle':rad, 'w':m, 'nc':..}  (slab, infinite out of plane)
        3-D: {'p':(x,y,z), 'angle':rad, 'w':m, 'h':m, 'nc':..} (channel, axis in xy
             plane, rectangular cross-section w (in-plane transverse) x h (z)).
        antialias: area-average the squared index across cells cut by a tilted
        interface (sub-cell accurate, removes staircase roughness).
        """
        nd = self.ndim
        n2 = np.full(self.N, self.n_clad ** 2, dtype=np.float64)
        ax = self.axes
        if nd == 2:
            X = ax[0][:, None]
            Y = ax[1][None, :]
            for g in guides:
                px, py = g['p']
                th = g['angle']
                s = -np.sin(th) * (X - px) + np.cos(th) * (Y - py)
                hw = g['w'] / 2.0
                nc = g.get('nc', self.n_core)
                if not antialias:
                    mask = np.abs(s) <= hw
                    n2[mask] = nc ** 2
                else:
                    p = max(abs(np.sin(th)), 1e-12)
                    q = abs(np.cos(th))
                    if p < q:
                        p, q = q, p
                    self._fill_pq = (p, q)
                    fill = self._fill_fraction_slab(np.asarray(s, dtype=np.float64), 2 * hw)
                    n2 = n2 * (1.0 - fill) + (nc ** 2) * fill
                    del fill, s
        elif nd == 3:
            X = ax[0][:, None, None]
            Y = ax[1][None, :, None]
            Z = ax[2][None, None, :]
            for g in guides:
                px, py, pz = g['p']
                th = g['angle']
                s = -np.sin(th) * (X - px) + np.cos(th) * (Y - py)
                hw = g['w'] / 2.0
                hh = g['h'] / 2.0
                nc = g.get('nc', self.n_core)
                if not antialias:
                    mask = (np.abs(s) <= hw) & (np.abs(Z - pz) <= hh)
                    n2[mask] = nc ** 2
                else:
                    p = max(abs(np.sin(th)), 1e-12)
                    q = abs(np.cos(th))
                    if p < q:
                        p, q = q, p
                    self._fill_pq = (p, q)
                    fill = self._fill_fraction_slab(np.asarray(s, dtype=np.float64), 2 * hw)
                    fill = np.asarray(fill).reshape(self.N[0], self.N[1])
                    zfill = self._fill_fraction_1d(Z[0, 0, :], pz, hh)
                    fill3 = fill[:, :, None] * zfill[None, None, :].astype(np.float64)
                    n2 = n2 * (1.0 - fill3) + (nc ** 2) * fill3
                    del fill, zfill, fill3, s
        else:
            raise ValueError(nd)
        n = np.sqrt(n2).astype(np.float32)
        self.n_index = n
        # core mask as flat indices (used by the 3-D stepper's core correction)
        self.core_flat = np.flatnonzero((n > self.n_clad + 1e-6).ravel())
        self.core_n = float(np.median(n.ravel()[self.core_flat])) if self.core_flat.size else self.n_core
        return n

    def build_sigma(self, guides=None):
        """Separable cubic graded lossy layer outside the physical box."""
        nd = self.ndim
        sig = np.zeros(self.N, dtype=np.float64)
        for i in range(nd):
            co = self.axes[i]
            a, b = self.phys[i]
            prof = np.zeros_like(co)
            left = co < a
            right = co > b
            prof[left] = self.sigma_max * ((a - co[left]) / self.t_abs) ** self.m_abs
            prof[right] = self.sigma_max * ((co[right] - b) / self.t_abs) ** self.m_abs
            shape = [1] * nd
            shape[i] = -1
            sig = sig + prof.reshape(shape)
        self.sigma = sig.astype(np.float32)
        return self.sigma


# -----------------------------------------------------------------------------
# torch stepper
# -----------------------------------------------------------------------------
class Stepper:
    """Explicit leapfrog stepper for  psi_tt = (c/n)^2 lap(psi)  with graded damping.
    Internally on CUDA (float32) or CPU; NumPy reference step provided."""

    def __init__(self, grid: Grid, device='cuda'):
        self.g = grid
        self.ndim = grid.ndim
        self.device = torch.device(device if torch.cuda.is_available() else 'cpu')
        self.order = grid.order
        self.m = grid.order // 2
        self.dx = grid.dx
        self.dt = grid.dt
        self.N = grid.N
        self.dtype = torch.float32
        # ---- coefficient arrays (same layout as the field) -------------------
        n = torch.as_tensor(grid.n_index, device=self.device, dtype=self.dtype)
        sig = torch.as_tensor(grid.sigma, device=self.device, dtype=self.dtype)
        sdt = sig * np.float32(self.dt)
        kn = (np.float32(C0 * self.dt / self.dx) ** 2) / (n * n)
        self.P2 = (2.0 / (1.0 + sdt)).contiguous()
        self.Ab = ((1.0 - sdt) / (1.0 + sdt)).contiguous()
        self.K = (kn / (1.0 + sdt)).contiguous()
        del sig, sdt, kn, n
        self.kn_clad = np.float32((C0 * self.dt / self.dx) ** 2) / np.float32(grid.n_clad ** 2)
        self.kn_core = np.float32((C0 * self.dt / self.dx) ** 2) / np.float32(grid.core_n ** 2)
        # fields (3 time levels)
        self.psi_a = torch.zeros(self.N, device=self.device, dtype=self.dtype)
        self.psi_b = torch.zeros(self.N, device=self.device, dtype=self.dtype)
        self.psi_c = torch.zeros(self.N, device=self.device, dtype=self.dtype)
        # ---- Laplacian machinery --------------------------------------------
        c = fd2_coeffs(grid.order)
        self.c2 = c.astype(np.float32)
        if self.ndim == 2:
            k = np.zeros((2 * self.m + 1, 2 * self.m + 1), dtype=np.float32)
            k[self.m, self.m] = 2.0 * c[0]
            for kk in range(1, self.m + 1):
                k[self.m + kk, self.m] = c[kk]
                k[self.m - kk, self.m] = c[kk]
                k[self.m, self.m + kk] = c[kk]
                k[self.m, self.m - kk] = c[kk]
            self.kern2d = torch.as_tensor(k, device=self.device, dtype=self.dtype)[None, None]
            self._lap_2d = self._laplacian_2d
            self._lap_plain = self._laplacian_2d
        else:
            # 3-D: separable conv2d on a y-padded layout
            m = self.m
            Ny = self.N[1]
            self.Ny_pad = Ny + 2 * m
            k1 = [float(x) for x in c]
            self.kx = torch.zeros(1, 1, 2 * m + 1, 1, device=self.device, dtype=self.dtype)
            self.ky = torch.zeros(1, 1, 2 * m + 1, 1, device=self.device, dtype=self.dtype)
            self.kz = torch.zeros(1, 1, 1, 2 * m + 1, device=self.device, dtype=self.dtype)
            for kk in range(self.m + 1):
                self.kx[0, 0, m + kk, 0] = k1[kk]
                if kk > 0:
                    self.kx[0, 0, m - kk, 0] = k1[kk]
                self.ky[0, 0, m + kk, 0] = k1[kk]
                if kk > 0:
                    self.ky[0, 0, m - kk, 0] = k1[kk]
                self.kz[0, 0, 0, m + kk] = k1[kk]
                if kk > 0:
                    self.kz[0, 0, 0, m - kk] = k1[kk]
            self._lap_3d = self._laplacian_3d
            self._lap_plain = self._laplacian_3d
            # fields are stored on the y-padded layout
            shp = (self.N[0], self.Ny_pad, self.N[2])
            self.psi_a = torch.zeros(shp, device=self.device, dtype=self.dtype)
            self.psi_b = torch.zeros(shp, device=self.device, dtype=self.dtype)
            self.psi_c = torch.zeros(shp, device=self.device, dtype=self.dtype)
            # coefficient arrays must use the same y-padded layout
            def _padc(arr):
                out = torch.zeros(shp, device=self.device, dtype=self.dtype)
                out[:, self.m:self.m + Ny, :] = arr
                return out
            self.P2 = _padc(self.P2)
            self.Ab = _padc(self.Ab)
            self.K = _padc(self.K)
            self.y_pad = (self.m, self.m + Ny)
        # statistics
        self.steps_done = 0
        self.wall = 0.0

    # ---------------------------------------------------------------- helpers
    def _laplacian_2d(self, a):
        return F.conv2d(a.unsqueeze(0).unsqueeze(0), self.kern2d,
                        padding=self.m).squeeze(0).squeeze(0)

    def _laplacian_3d(self, a):
        Nx, Nyp, Nz = a.shape
        m = self.m
        v = a.view(Nx, Nyp * Nz).unsqueeze(0).unsqueeze(0)
        lap = F.conv2d(v, self.kx, padding=(m, 0))
        v2 = a.view(Nx * Nyp, Nz).unsqueeze(0).unsqueeze(0)
        tmp = F.conv2d(v2, self.ky, padding=(m, 0))
        lap.add_(tmp.view(1, 1, Nx, Nyp * Nz))
        tmp = F.conv2d(v2, self.kz, padding=(0, m))
        lap.add_(tmp.view(1, 1, Nx, Nyp * Nz))
        return lap.view(Nx, Nyp, Nz)

    # ------------------------------------------------------------ one step
    def step(self, source=None):
        """advance one time step. source = (flat_indices tensor, values tensor,
        scalar amplitude)"""
        a, b, c = self.psi_a, self.psi_b, self.psi_c
        lap = self._lap_plain(a)
        torch.mul(a, self.P2, out=c)
        c.addcmul_(b, self.Ab, value=-1.0)
        c.addcmul_(lap, self.K)
        if self.ndim == 3:
            # enforce the zero (Dirichlet) condition in the y-padding rows
            y0, y1 = self.y_pad
            c[:, :y0, :] = 0.0
            c[:, y1:, :] = 0.0
        if source is not None:
            idx, vals, amp = source
            if idx is not None and len(idx):
                c.view(-1)[idx] += vals * amp
        # rotate time levels
        self.psi_c = b
        self.psi_b = a
        self.psi_a = c
        self.steps_done += 1
        return c

    # ------------------------------------------------------------ NumPy reference
    def np_step(self, a, b, order=None, use_gpu_coeffs=True):
        """One step in float64 NumPy using identical coefficient arrays (reference
        implementation used only to cross-check the torch kernels)."""
        if use_gpu_coeffs:
            P2 = self.P2.detach().cpu().numpy().astype(np.float64)
            Ab = self.Ab.detach().cpu().numpy().astype(np.float64)
            K = self.K.detach().cpu().numpy().astype(np.float64)
            kn_clad = float(self.kn_clad)
            kn_core = float(self.kn_core)
        lap = np.zeros_like(a)
        c2 = self.c2 if order is None else fd2_coeffs(order)
        mm = len(c2) - 1
        nd = a.ndim
        lap += nd * c2[0] * a
        for ax in range(nd):
            for kk in range(1, mm + 1):
                sa = [slice(None)] * nd
                sb = [slice(None)] * nd
                sa[ax] = slice(kk, None)
                sb[ax] = slice(None, -kk)
                lap[tuple(sa)] += c2[kk] * a[tuple(sb)]
                sa[ax] = slice(None, -kk)
                sb[ax] = slice(kk, None)
                lap[tuple(sa)] += c2[kk] * a[tuple(sb)]
        c = P2 * a - Ab * b + K * lap
        return c

    def energy(self):
        a = self.psi_a
        return float((a * a).sum().item())


# -----------------------------------------------------------------------------
# DFT probe machinery
# -----------------------------------------------------------------------------
class DftBox:
    """Accumulates the complex DFT (Hann-windowed) of the field on a rectangular
    sub-box."""

    def __init__(self, sl, shape, device):
        self.sl = sl
        self.re = torch.zeros(shape, device=device, dtype=torch.float32)
        self.im = torch.zeros(shape, device=device, dtype=torch.float32)

    def add(self, field, zr, zi, w):
        v = field[self.sl]
        wr = zr * w
        wi = zi * w
        self.re.add_(v, alpha=wr)
        self.im.add_(v, alpha=wi)

    def get(self):
        return (self.re.detach().cpu().numpy()
                + 1j * self.im.detach().cpu().numpy())


class ProjectorBox:
    """Projects the field on a mode profile and accumulates the DFT of the 1-D
    projection as a function of the first index (used for phase-slope / beta)."""

    def __init__(self, i0, i1, phi, weights, device, n_out):
        self.i0, self.i1 = i0, i1
        self.re = torch.zeros(n_out, device=device, dtype=torch.float32)
        self.im = torch.zeros(n_out, device=device, dtype=torch.float32)
        if phi is not None:
            self.w = weights
            self.phi_t = torch.as_tensor(phi, device=device, dtype=torch.float32)
            self.use_phi = True
        else:
            self.use_phi = False

    def add(self, field, zr, zi, w, sl_extra=None):
        wr = zr * w
        wi = zi * w
        sub = field[self.i0:self.i1]
        if self.use_phi:
            proj = (sub * self.phi_t).sum(dim=tuple(range(1, field.ndim)))
        else:
            proj = sub.sum(dim=tuple(range(1, field.ndim)))
        self.re.add_(proj, alpha=wr)
        self.im.add_(proj, alpha=wi)


# -----------------------------------------------------------------------------
# main 2-D simulation driver
# -----------------------------------------------------------------------------
class Sim2D:
    def __init__(self, phys, t_abs, dx, order=6, guides=None,
                 n_core=N_CORE, n_clad=N_CLAD, A_abs=7.0, m_abs=3.0,
                 device='cuda', label='sim2d', S_factor=0.90):
        self.label = label
        self.g = Grid(phys, t_abs, dx, order, n_core=n_core, n_clad=n_clad,
                      A_abs=A_abs, m_abs=m_abs, S_factor=S_factor)
        self.g.build_index(guides if guides is not None else [])
        self.g.build_sigma()
        self.st = Stepper(self.g, device=device)
        self.device = self.st.device
        self.dx = dx
        self.dt = self.g.dt
        self.omega = OMEGA0
        self.T = 2 * np.pi / OMEGA0
        self.vg = C0 / NEFF2D_TARGET
        self.ports = []        # modal ports
        self.flux_ports = []   # oblique flux lines
        self.oblique_arms = {}  # named sets of oblique port lines
        self.probes = {}       # name -> DftBox
        self.projectors = {}   # name -> ProjectorBox
        self.source = None
        self.t_ramp = 0.0
        self._snapshot_hooks = {}

    # ------------------------------------------------------------- utilities
    def x_index(self, x):
        return int(round((x - self.g.axes[0][0]) / self.dx))

    def y_index(self, y):
        return int(round((y - self.g.axes[1][0]) / self.dx))

    def x_of(self, i):
        return self.g.axes[0][i]

    def y_of(self, j):
        return self.g.axes[1][j]

    # ------------------------------------------------------------------ modes
    def guide_profile_1d(self, yc, w, n_core=None):
        """discrete mode of an isolated slab guide centred at yc (metres).
        Returns (s, phi, beta, beta_d, neff)."""
        g = self.g
        n_core = g.n_core if n_core is None else n_core
        Y = g.axes[1]
        nprof = np.where(np.abs(Y - yc) <= w / 2.0, n_core, g.n_clad)
        s, phi = discrete_mode_1d((Y,), nprof, self.dx, g.order, g.omega_eff)
        beta = beta_from_stencil_eig(s, self.dx, g.order)
        bd = beta_deriv_fd(beta, self.dx, g.order)
        return s, phi, beta, bd, beta / K0

    # ----------------------------------------------------------------- ports
    def add_port_x(self, x, yc, name, halfwidth=10e-6, direction=+1, w=W_SLAB,
                   n_core=None):
        """Modal port on a vertical line at x.  direction=+1 means propagation
        along +x (through direction)."""
        ix = self.x_index(x)
        m = self.g.pad
        i0, i1 = ix - m - 1, ix + m + 1 + 1
        sl = (slice(i0, i1), slice(0, self.g.N[1]))
        shape = (i1 - i0, self.g.N[1])
        box = DftBox(sl, shape, self.device)
        s, phi, beta, bd, neff = self.guide_profile_1d(yc, w, n_core=n_core)
        self.ports.append(dict(name=name, x=x, yc=yc, ix=ix, box=box, phi=phi,
                               beta=beta, beta_d=bd, neff=neff, direction=direction,
                               halfwidth=halfwidth, s=s))
        return self.ports[-1]

    def add_flux_line(self, p0, p1, name, npts=801, normal=None):
        """Oblique power-flux line from p0 to p1 (2-D physical coords, metres).
        normal: optional (nx,ny) unit vector of the flux direction; if None it is
        taken as the in-plane normal of (p1-p0) rotated by +90 deg."""
        m = self.g.pad + 2
        xs = np.linspace(p0[0], p1[0], npts)
        ys = np.linspace(p0[1], p1[1], npts)
        fx = (xs - self.g.axes[0][0]) / self.dx
        fy = (ys - self.g.axes[1][0]) / self.dx
        i0 = int(np.floor(fx.min())) - m
        i1 = int(np.ceil(fx.max())) + m + 1
        j0 = int(np.floor(fy.min())) - m
        j1 = int(np.ceil(fy.max())) + m + 1
        i0 = max(i0, 0); j0 = max(j0, 0)
        i1 = min(i1, self.g.N[0]); j1 = min(j1, self.g.N[1])
        sl = (slice(i0, i1), slice(j0, j1))
        shape = (i1 - i0, j1 - j0)
        box = DftBox(sl, shape, self.device)
        dl = float(np.hypot(xs[1] - xs[0], ys[1] - ys[0]))
        if normal is None:
            vx = p1[0] - p0[0]; vy = p1[1] - p0[1]
            vn = np.hypot(vx, vy)
            normal = (-vy / vn, vx / vn)
        self.flux_ports.append(dict(name=name, box=box, fx=fx - i0, fy=fy - j0,
                                    xs=xs, ys=ys, dl=dl, p0=p0, p1=p1,
                                    normal=normal))
        return self.flux_ports[-1]

    def add_boundary_probes(self, name='bnd'):
        """DFT boxes along the 4 sides of the physical box (for boundary flux)."""
        g = self.g
        m = g.pad
        i0p, i1p = g.i_phys[0]
        j0p, j1p = g.i_phys[1]
        mp = m + 1
        # left / right : rows [i- m.. i+m], cols physical box
        self.probes[name + '_L'] = DftBox((slice(i0p - m, i0p + m + 1), slice(j0p, j1p + 1)),
                                          (2 * m + 1, j1p - j0p + 1), self.device)
        self.probes[name + '_R'] = DftBox((slice(i1p - m, i1p + m + 1), slice(j0p, j1p + 1)),
                                          (2 * m + 1, j1p - j0p + 1), self.device)
        self.probes[name + '_B'] = DftBox((slice(i0p, i1p + 1), slice(j0p - m, j0p + m + 1)),
                                          (i1p - i0p + 1, 2 * m + 1), self.device)
        self.probes[name + '_T'] = DftBox((slice(i0p, i1p + 1), slice(j1p - m, j1p + m + 1)),
                                          (i1p - i0p + 1, 2 * m + 1), self.device)

    # ------------------------------------------------------- oblique arm ports
    def add_oblique_arm(self, center, theta, u_list, name, halfwidth=12e-6,
                        w=W_SLAB):
        """Port lines perpendicular to a straight arm with direction angle theta
        (rad), located at along-arm coordinates u_list (metres, can be negative)."""
        eu = np.array([np.cos(theta), np.sin(theta)])
        es = np.array([-np.sin(theta), np.cos(theta)])
        u_list = np.asarray(u_list, dtype=np.float64)
        npts = int(np.ceil(2 * halfwidth / (self.dx * 0.5))) + 1
        s = np.linspace(-halfwidth, halfwidth, npts)
        dl = s[1] - s[0]
        sol = fw_slab_analytic(w=w)
        phi_s = fw_slab_profile(s, sol)
        phi_s = phi_s / np.sqrt(np.sum(phi_s ** 2) * dl)
        entries = []
        for u in u_list:
            cpt = np.array(center) + u * eu
            p0 = cpt - halfwidth * es
            p1 = cpt + halfwidth * es
            fp = self.add_flux_line(p0, p1, f'{name}_{len(entries):02d}', npts=npts,
                                    normal=(eu[0], eu[1]))
            fp['u'] = float(u)
            fp['sep'] = float(abs(u * np.sin(theta)))
            entries.append(fp)
        self.oblique_arms[name] = dict(center=tuple(center), theta=theta,
                                       eu=eu, es=es, s=s, dl=dl, phi=phi_s,
                                       entries=entries, halfwidth=halfwidth)

    def _sample_line(self, C, fp):
        """interpolate complex psi and normal derivative psi_n on an oblique line."""
        from scipy.ndimage import convolve1d, map_coordinates
        om_ = self.omega
        d = fd1_coeffs(self.g.order)
        ker = np.zeros(2 * len(d) + 1)
        for k, dk in enumerate(d, start=1):
            # scipy.ndimage.convolve1d reverses the kernel, hence this sign layout
            ker[len(d) - k] = dk
            ker[len(d) + k] = -dk
        Cr = np.ascontiguousarray(np.real(C)); Ci = np.ascontiguousarray(np.imag(C))
        Dr = convolve1d(Cr, ker, axis=0, mode='constant') / self.dx
        Di = convolve1d(Ci, ker, axis=0, mode='constant') / self.dx
        Er = convolve1d(Cr, ker, axis=1, mode='constant') / self.dx
        Ei = convolve1d(Ci, ker, axis=1, mode='constant') / self.dx
        coords = np.vstack([fp['fx'], fp['fy']])
        psi = (map_coordinates(Cr, coords, order=3)
               + 1j * map_coordinates(Ci, coords, order=3))
        gx = (map_coordinates(Dr, coords, order=3)
              + 1j * map_coordinates(Di, coords, order=3))
        gy = (map_coordinates(Er, coords, order=3)
              + 1j * map_coordinates(Ei, coords, order=3))
        nx, ny = fp['normal']
        return psi, nx * gx + ny * gy

    def analyse_oblique_arm(self, name, beta_guess=None):
        """forward/backward modal decomposition on a set of oblique port lines.
        The propagation constant of the arm is fitted from the phase advance
        between lines, then the decomposition is redone with the fitted value."""
        arm = self.oblique_arms[name]
        om = self.omega
        N = self.window_values
        dl, phi = arm['dl'], arm['phi']
        th = arm['theta']
        if beta_guess is None:
            sol = fw_slab_analytic(w=W_SLAB)
            beta_guess = sol['beta']
        us, inners, innerDs, fluxes = [], [], [], []
        for fp in arm['entries']:
            C = fp['box'].get()
            psi, Dn = self._sample_line(C, fp)
            inners.append(dl * np.sum(phi * psi))
            innerDs.append(dl * np.sum(phi * Dn))
            fluxes.append(4.0 * (2 * om / N ** 2) * dl * np.sum(np.imag(np.conj(psi) * Dn)))
            us.append(fp['u'])
        inners = np.asarray(inners); innerDs = np.asarray(innerDs)
        fluxes = np.asarray(fluxes); us = np.asarray(us)
        # ---- fit beta from the phase of the forward projection
        ph = np.angle(inners) - beta_guess * us
        ph = np.unwrap(ph)
        A = np.vstack([us, np.ones_like(us)]).T
        coef, *_ = np.linalg.lstsq(A, ph, rcond=None)
        beta_fit = beta_guess + coef[0]
        if arm.get('beta_override') is not None:
            beta_fit = float(arm['beta_override'])
        ph2 = np.angle(inners) - beta_fit * us
        ph2 = np.unwrap(ph2)
        coef2, *_ = np.linalg.lstsq(A, ph2, rcond=None)
        phase_resid = float(np.std(ph2 - A @ coef2))
        # ---- redo decomposition with fitted beta
        bplus = 0.5 * (inners + innerDs / (1j * beta_fit))
        bminus = 0.5 * (inners - innerDs / (1j * beta_fit))
        aplus = 4.0 * np.abs(bplus) / N
        aminus = 4.0 * np.abs(bminus) / N
        Pplus = 0.5 * om * beta_fit * aplus ** 2
        Pminus = 0.5 * om * beta_fit * aminus ** 2
        return dict(name=name, u=us.tolist(), sep=[float(u * np.sin(th)) for u in us],
                    a_plus=aplus.tolist(), a_minus=aminus.tolist(),
                    P_plus=Pplus.tolist(), P_minus=Pminus.tolist(),
                    flux=fluxes.tolist(), beta=float(beta_fit),
                    beta_guess=float(beta_guess),
                    neff=float(beta_fit / K0),
                    phase_resid=phase_resid)


    def add_plane_probe(self, x, name='plane', direction='x'):
        """DFT on a single interior plane (for mode-shape / launch diagnostics)."""
        ix = self.x_index(x)
        m = self.g.pad
        sl = (slice(ix - m - 1, ix + m + 2), slice(0, self.g.N[1]))
        shape = (2 * m + 3, self.g.N[1])
        self.probes[name] = DftBox(sl, shape, self.device)

    def add_beta_projector(self, x0, x1, yc, name='proj', w=W_SLAB, n_core=None):
        g = self.g
        _, phi, beta, bd, neff = self.guide_profile_1d(yc, w, n_core=n_core)
        i0, i1 = self.x_index(x0), self.x_index(x1) + 1
        phi_t = phi.reshape(1, -1)
        self.projectors[name] = dict(
            i0=i0, i1=i1, phi=phi, beta=beta, beta_d=bd,
            re=torch.zeros(i1 - i0, device=self.device, dtype=torch.float32),
            im=torch.zeros(i1 - i0, device=self.device, dtype=torch.float32))

    def add_source_back_line(self, x, name='srcback'):
        """flux line just behind the source (to measure backward emission)."""
        ys = np.linspace(self.g.phys[1][0] * 0.9, self.g.phys[1][1] * 0.9, 2)
        self.add_flux_line((x, ys[0]), (x, ys[1]), name, npts=2)

    # ---------------------------------------------------------------- source
    def set_source(self, x, yc, amp=None, w=W_SLAB, ramp_periods=10.0, n_core=None):
        """soft mode-shaped line source.  amp defaults to the value that launches a
        guided wave of order-unity amplitude: for a line source f(y) sin(wt) in
        psi_tt = ... + f the generated guided amplitude is ~ f/(2 beta v^2)."""
        g = self.g
        ix = self.x_index(x)
        _, phi, beta, bd, neff = self.guide_profile_1d(yc, w, n_core=n_core)
        idx = torch.as_tensor(ix * g.N[1] + np.arange(g.N[1]), device=self.device,
                              dtype=torch.long)
        vals = torch.as_tensor(phi, device=self.device, dtype=self.dtype)
        if amp is None:
            v2 = (C0 / neff) ** 2
            amp = 2.0 * beta * v2
        self.source = dict(x=x, ix=ix, idx=idx, vals=vals, amp=float(amp),
                           yc=yc, w=w, beta=beta, phi=phi)
        self.t_ramp = ramp_periods * self.T
        return self.source

    def set_source_oblique(self, center, theta, u0, amp=None, w=W_SLAB,
                           ramp_periods=10.0, band=0.75, phi_norm=400.0):
        """soft mode-shaped line source perpendicular to a straight arm with
        direction angle theta, located at u=u0 along the arm from `center`.
        The source profile is the analytic slab mode sampled at the cells that
        intersect the source line."""
        g = self.g
        eu = np.array([np.cos(theta), np.sin(theta)])
        es = np.array([-np.sin(theta), np.cos(theta)])
        cpt = np.array(center, dtype=np.float64) + u0 * eu
        X = g.axes[0][:, None]
        Y = g.axes[1][None, :]
        u = (X - cpt[0]) * eu[0] + (Y - cpt[1]) * eu[1]
        s = (X - cpt[0]) * es[0] + (Y - cpt[1]) * es[1]
        mask = (np.abs(u) <= band * self.dx) & (np.abs(s) <= w / 2.0)
        idx = np.flatnonzero(mask.ravel())
        sol = fw_slab_analytic(w=w)
        vals = fw_slab_profile(np.asarray(s[mask], dtype=np.float64), sol)
        vals = vals / np.max(np.abs(vals))
        idx_t = torch.as_tensor(idx.astype(np.int64), device=self.device,
                                dtype=torch.long)
        vals_t = torch.as_tensor(vals.astype(np.float32), device=self.device,
                                 dtype=self.dtype)
        if amp is None:
            v2 = (C0 / sol['neff']) ** 2
            amp = 2.0 * sol['beta'] * v2 / phi_norm
        self.source = dict(x=float(cpt[0]), y=float(cpt[1]), ix=-1, idx=idx_t,
                           vals=vals_t, amp=float(amp), theta=theta, u0=u0)
        self.t_ramp = ramp_periods * self.T
        return self.source

    @property
    def dtype(self):
        return torch.float32

    # --------------------------------------------------------------- run loop
    def run(self, t_settle_extra=0.3e-12, window_periods=80.0, print_every=2000,
            max_steps=400000, snapshot_steps=(), progress=True):
        g, st = self.g, self.st
        # time budget: ramp + settle (max light path from source to any probe) + window
        src = self.source
        pts = []
        for p in self.ports:
            pts.append((p['x'], p['yc']))
        for fp in self.flux_ports:
            pts.append(tuple(fp['p0'])); pts.append(tuple(fp['p1']))
        for nm, bx in self.probes.items():
            i0 = bx.sl[0].start; i1 = bx.sl[0].stop
            j0 = bx.sl[1].start; j1 = bx.sl[1].stop
            pts.append((g.axes[0][i0], g.axes[1][j0]))
            pts.append((g.axes[0][i1 - 1], g.axes[1][j1 - 1]))
        x0s = float(src['x'])
        y0s = float(src.get('yc', src.get('y', 0.0)))
        dmax = max([np.hypot(a - x0s, b - y0s) for (a, b) in pts] + [0.0])
        t_settle = self.t_ramp + dmax / self.vg + t_settle_extra
        t_win = window_periods * self.T
        n_start = int(np.ceil(t_settle / self.dt))
        n_win = int(np.round(t_win / self.dt))
        n_tot = min(n_start + n_win, max_steps)
        self.meta = dict(t_ramp=self.t_ramp, t_settle=t_settle, t_window=t_win,
                         n_start=n_start, n_win=n_win, n_tot=n_tot, dmax=dmax,
                         dt=self.dt, dx=self.dx, order=g.order,
                         N=list(g.N), n_index_cells=int(np.prod(g.N)),
                         S=self.g.S, S_max=self.g.S_max, t_abs=g.t_abs)
        # precompute source time series (ramp * sin)
        t = np.arange(n_tot + 1) * self.dt
        ramp = np.ones_like(t)
        tr = np.where(t < self.t_ramp, t, 0.0)
        ramp = np.where(t < self.t_ramp,
                        0.5 * (1.0 - np.cos(np.pi * tr / max(self.t_ramp, 1e-30))), 1.0)
        src_ts = (src['amp'] * ramp * np.sin(self.omega * t) * self.dt * self.dt
                  ).astype(np.float64)
        # reset fields
        st.psi_a.zero_(); st.psi_b.zero_(); st.psi_c.zero_()
        st.steps_done = 0
        snaps = {}
        win_start = n_start
        win_len = max(n_win, 1)
        kk = 0
        t0 = time.time()
        dt = self.dt
        omega = self.omega
        z = complex(1.0, 0.0)
        dphase = np.exp(1j * omega * dt)
        coeffs = [fd1_coeffs(g.order)]
        for n in range(n_tot):
            st.step(source=(src['idx'], src['vals'], float(src_ts[n])))
            if n >= win_start:
                # Hann window over the DFT window
                w = 0.5 * (1.0 - np.cos(2 * np.pi * kk / win_len))
                zr, zi = z.real * w, z.imag * w
                z *= dphase
                kk += 1
                for bx in self.probes.values():
                    bx.add(st.psi_a, zr, zi, 1.0)
                for p in self.ports:
                    p['box'].add(st.psi_a, zr, zi, 1.0)
                for fp in self.flux_ports:
                    fp['box'].add(st.psi_a, zr, zi, 1.0)
                for nm, pr in self.projectors.items():
                    sub = st.psi_a[pr['i0']:pr['i1']]
                    proj = (sub * torch.as_tensor(pr['phi'], device=st.psi_a.device,
                                                  dtype=torch.float32)[None, :]).sum(dim=1)
                    pr['re'].add_(proj, alpha=zr)
                    pr['im'].add_(proj, alpha=zi)
            for sstep in snapshot_steps:
                if n + 1 == sstep:
                    snaps[sstep] = st.psi_a.detach().cpu().numpy().copy()
            if progress and (n + 1) % print_every == 0:
                mx = float(st.psi_a.abs().max().item())
                el = time.time() - t0
                print(f'  [{self.label}] step {n+1}/{n_tot}  max|psi|={mx:.3e}  '
                      f'{el:.1f}s  ({(n+1)/el:.0f} steps/s)', flush=True)
                if not np.isfinite(mx) or mx > 1e3:
                    raise RuntimeError('divergence detected')
        self.wall = time.time() - t0
        self.n_tot = n_tot
        self.snaps = snaps
        self.window_values = kk
        if progress:
            print(f'  [{self.label}] done: {n_tot} steps in {self.wall:.1f}s '
                  f'({n_tot/self.wall:.0f} steps/s)', flush=True)
        return self

    # ------------------------------------------------------------- analysis
    def _box_deriv_x(self, C, ix_local, box):
        """discrete 1st derivative along x at local row ix_local of a complex box."""
        d = fd1_coeffs(self.g.order)
        m = self.g.pad
        out = np.zeros(C.shape[1:], dtype=np.complex128)
        for k, dk in enumerate(d, start=1):
            out += dk * (C[ix_local + k] - C[ix_local - k]) / self.dx
        return out

    def _box_deriv_y(self, C, jy_local):
        d = fd1_coeffs(self.g.order)
        out = np.zeros(C.shape[0], dtype=np.complex128)
        for k, dk in enumerate(d, start=1):
            out += dk * (C[:, jy_local + k] - C[:, jy_local - k]) / self.dx
        return out

    def analyse_ports(self):
        """modal decomposition + fluxes.  All powers are in arbitrary units where
        the incident guided power is P_inc."""
        g = self.g
        dy = self.dx
        nwin = self.window_values
        om = self.omega
        res = dict(ports={}, flux_ports={}, boundary={})
        # ---- modal ports
        for p in self.ports:
            C = p['box'].get()
            ix_local = p['ix'] - p['box'].sl[0].start
            psi_p = C[ix_local]
            D = self._box_deriv_x(C, ix_local, p['box'])
            phi = p['phi']
            dy = self.dx
            inner = dy * np.sum(phi * psi_p)
            innerD = dy * np.sum(phi * D)
            beta_d = p['beta_d']
            bplus = 0.5 * (inner + innerD / (1j * beta_d))
            bminus = 0.5 * (inner - innerD / (1j * beta_d))
            # physical guided-mode (phasor) amplitude: b+ = a*N/4 with the Hann window
            aplus = 4.0 * abs(bplus) / nwin
            aminus = 4.0 * abs(bminus) / nwin
            P = 0.5 * om * p['beta'] * aplus ** 2
            Pref = 0.5 * om * p['beta'] * aminus ** 2
            # power flux through the port line (independent cross-check)
            Pf = self._flux_from_box(C, ix_local, p['box'], axis=0)
            res['ports'][p['name']] = dict(
                a_plus=float(aplus), a_minus=float(aminus),
                ratio_bwd=float(aminus / aplus) if aplus > 0 else float('inf'),
                P_plus=float(P), P_minus=float(Pref), P_flux=float(Pf),
                beta=float(p['beta']), neff=float(p['neff']))
        # ---- flux ports (oblique lines)
        for fp in self.flux_ports:
            C = fp['box'].get()
            Pf = self._flux_oblique(C, fp)
            res['flux_ports'][fp['name']] = dict(P_flux=float(Pf))
        # ---- boundary
        for nm, bx in self.probes.items():
            C = bx.get()
            if nm.endswith('_L'):
                mi = self.g.pad
                Pf = -self._flux_from_box(C, mi, bx, axis=0)
            elif nm.endswith('_R'):
                mi = self.g.pad
                Pf = self._flux_from_box(C, mi, bx, axis=0)
            elif nm.endswith('_B'):
                mi = self.g.pad
                Pf = -self._flux_from_box(C, mi, bx, axis=1)
            elif nm.endswith('_T'):
                mi = self.g.pad
                Pf = self._flux_from_box(C, mi, bx, axis=1)
            else:
                continue
            res['boundary'][nm] = float(Pf)
        return res
    def _flux_from_box(self, C, ilocal, box, axis=0):
        """power flux in +axis direction through the line at local index ilocal."""
        om = self.omega
        nwin = self.window_values
        d = fd1_coeffs(self.g.order)
        if axis == 0:
            D = np.zeros(C.shape[1:], dtype=np.complex128)
            for k, dk in enumerate(d, start=1):
                D += dk * (C[ilocal + k] - C[ilocal - k]) / self.dx
            integ = np.sum(np.imag(np.conj(C[ilocal]) * D))
            return float(4.0 * 2.0 * om / nwin ** 2 * self.dx * integ)
        else:
            D = np.zeros(C.shape[0], dtype=np.complex128)
            for k, dk in enumerate(d, start=1):
                D += dk * (C[:, ilocal + k] - C[:, ilocal - k]) / self.dx
            integ = np.sum(np.imag(np.conj(C[:, ilocal]) * D))
            return float(4.0 * 2.0 * om / nwin ** 2 * self.dx * integ)

    def _flux_oblique(self, C, fp):
        om = self.omega
        nwin = self.window_values
        psi, Dn = self._sample_line(C, fp)
        integ = np.sum(np.imag(np.conj(psi) * Dn))
        return float(4.0 * 2.0 * om / nwin ** 2 * fp['dl'] * integ)

    def beta_from_projector(self, name='proj'):
        pr = self.projectors[name]
        c = pr['re'].detach().cpu().numpy() + 1j * pr['im'].detach().cpu().numpy()
        phase = np.unwrap(np.angle(c))
        x = self.g.axes[0][pr['i0']:pr['i1']]
        # robust linear fit
        A = np.vstack([x, np.ones_like(x)]).T
        coef, *_ = np.linalg.lstsq(A, phase, rcond=None)
        beta = coef[0]
        resid = phase - A @ coef
        return dict(beta=float(beta), neff=float(beta / K0),
                    phase_resid_std=float(np.std(resid)),
                    beta_direct=pr['beta'], neff_direct=pr['beta'] / K0)
