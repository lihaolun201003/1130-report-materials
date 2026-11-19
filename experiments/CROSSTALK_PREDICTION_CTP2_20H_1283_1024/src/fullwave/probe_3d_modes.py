"""3-D channel: discrete transverse eigenmode study + CMT coupling coefficients.

All CPU (sparse eigsh).  Computes:
  * n_eff of the fundamental 3-D channel mode for several dx / stencil order,
    and Richardson-extrapolated value (target from the lead: 1.50455547);
  * 2-D transverse decay constants (cladding) and the 2-D EIM proxy value;
  * CMT coupling coefficients kappa(d) for two identical channels:
      - horizontal in-plane offset d (centres distance in the plane)
      - vertical offset dz
    using the converged mode (fine grid, continuous-operator discretisation).
"""
import json
import os
import sys

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import eigsh

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(HERE, '..', '..'))
CACHE = os.path.join(BASE, 'cache', 'fullwave')
OUT = os.path.join(BASE, 'outputs', 'fullwave')
sys.path.insert(0, HERE)
import fwlib as fw

N_CLAD = fw.N_CLAD
N_CORE = fw.N_CORE
W = fw.W_CORE
SOL_EIM = fw.slab_analytic(fw.N_SLAB, N_CLAD, fw.W_SLAB)


def build_L1(N, dx, order=2):
    c = fw.fd2_coeffs(order)
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


def channel_mode(dx, half=20e-6, order=2, omega=None, n_modes=4):
    """fundamental guided mode of the 9x9 um channel on a (y,z) grid.
    Returns s(=-lambda_x>0), phi(Na,Nb) normalised int phi^2 dA = 1, beta, n_eff."""
    N = int(round(2 * half / dx)) + 1
    ax = -half + dx * np.arange(N)
    Y = ax[:, None]
    Z = ax[None, :]
    n = np.where((np.abs(Y) <= W / 2) & (np.abs(Z) <= W / 2), N_CORE, N_CLAD)
    La = build_L1(N, dx, order)
    Lb = build_L1(N, dx, order)
    I = sparse.identity
    L2 = (sparse.kron(I(N), La) + sparse.kron(Lb, I(N))).tocsr()
    if omega is None:
        # use a CFL-like dt for consistency with the FDTD run
        order_fd = 6
        S = 0.44
        dt = S * dx * 1.5 / fw.C0
        omega = 2.0 / dt * np.sin(fw.OMEGA0 * dt / 2.0)
    d = (omega / fw.C0) ** 2 * (n.ravel() ** 2)
    M = (L2 + sparse.diags(d)).tocsr()
    vals, vecs = eigsh(M, k=n_modes, which='LA')
    idx = np.argsort(vals)[::-1]
    for j in idx:
        s = vals[j]
        if s <= 0:
            continue
        phi = vecs[:, j].reshape(N, N)
        mx = np.max(np.abs(phi))
        edge = max(np.abs(phi[0, :]).max(), np.abs(phi[-1, :]).max(),
                   np.abs(phi[:, 0]).max(), np.abs(phi[:, -1]).max())
        if mx <= 0 or edge / mx > 1e-2:
            continue
        phi = phi / np.sqrt(np.sum(phi ** 2) * dx * dx)
        beta = np.sqrt(s)
        return dict(s=s, phi=phi, ax=ax, beta=beta, neff=beta / fw.K0,
                    dx=dx, N=N)
    raise RuntimeError('no mode')


def mode_gamma(phi, ax):
    """fit the cladding decay constants along y and z through the centre."""
    j0 = np.argmin(np.abs(ax))
    prof = np.abs(phi[:, j0]) / np.max(np.abs(phi))
    idx = np.where(prof > 1e-4)[0]
    i1 = idx[-1]
    sel = np.arange(max(idx[0], i1 - 25), i1)
    gy = -np.polyfit(ax[sel], np.log(prof[sel]), 1)[0]
    prof2 = np.abs(phi[j0, :]) / np.max(np.abs(phi))
    idx2 = np.where(prof2 > 1e-4)[0]
    i2 = idx2[-1]
    sel2 = np.arange(max(idx2[0], i2 - 25), i2)
    gz = -np.polyfit(ax[sel2], np.log(prof2[sel2]), 1)[0]
    return float(gy), float(gz)


def cmt_kappa(mode, d_m, dz_m, n_core=N_CORE, n_clad=N_CLAD):
    """CMT coupling coefficient between two identical channels.
    kappa = (k0^2/(2 beta)) * (n_core^2-n_clad^2) * Int_{core of guide 2} phi1 phi2 dA
            / Int phi^2 dA
    guide 2 is displaced by d in y (in-plane) and dz in z.  Units 1/m."""
    phi = mode['phi']; ax = mode['ax']; dx = mode['dx']
    # shift guide-2 core mask in the index space
    dy = d_m / dx
    dz = dz_m / dx
    # fractional shift with bilinear interpolation of phi (shift -d)
    from scipy.ndimage import shift as ndshift
    phi2 = ndshift(phi, shift=(-dy, -dz), order=3, mode='constant')
    mask2 = np.abs(phi2) >= 0  # placeholder
    # core mask of guide 2 evaluated at grid points
    Y = ax[:, None]
    Z = ax[None, :]
    core2 = ((np.abs(Y - d_m) <= W / 2) & (np.abs(Z - dz_m) <= W / 2)).astype(float)
    num = np.sum(core2 * phi * phi2) * dx * dx
    den = np.sum(phi ** 2) * dx * dx
    k0 = fw.K0
    beta = mode['beta']
    kappa = k0 ** 2 / (2 * beta) * (n_core ** 2 - n_clad ** 2) * num / den
    return float(kappa), float(num / den)


def main():
    res = {}
    print('=== 3-D channel discrete mode (2-D transverse eigenproblem) ===')
    print('target n_eff (converged, from lead) = 1.50455547 ; EIM 2D = %.8f'
          % SOL_EIM['neff'])
    rows = []
    for order in (2, 4):
        for dx_um in (0.20, 0.15, 0.12, 0.10, 0.08, 0.06):
            dx = dx_um * 1e-6
            m = channel_mode(dx, half=20e-6, order=order)
            gy, gz = mode_gamma(m['phi'], m['ax'])
            rows.append(dict(order=order, dx_um=dx_um, neff=m['neff'],
                             err=m['neff'] - 1.50455547, gamma_y_um=gy / 1e6,
                             gamma_z_um=gz / 1e6))
            print('  order %d dx=%.2f: n_eff=%.8f (err %+.2e)  gamma_y=%.4f/um '
                  'gamma_z=%.4f/um' % (order, dx_um, m['neff'], m['neff'] - 1.50455547,
                                       gy / 1e6, gz / 1e6), flush=True)
    res['mode_rows'] = rows
    # Richardson (dx^2) extrapolation for each order
    for order in (2, 4):
        sub = sorted([r for r in rows if r['order'] == order],
                     key=lambda r: r['dx_um'], reverse=True)
        a, b = sub[-2], sub[-1]
        r = (a['dx_um'] / b['dx_um']) ** 2
        ext = (b['neff'] - a['neff'] / r) / (1 - 1 / r)
        print('  order %d Richardson(dx^2) extrapolated n_eff = %.8f (err %+.2e)'
              % (order, ext, ext - 1.50455547))
        res[f'neff_extrap_order{order}'] = ext
    # ---- converged mode for CMT (fine grid, 2nd-order operator) ------------
    print('=== CMT coupling coefficients from the converged 3-D mode ===')
    m = channel_mode(0.05e-6, half=22e-6, order=2)
    gy, gz = mode_gamma(m['phi'], m['ax'])
    print('  converged mode: n_eff=%.8f  gamma_y=%.4f/um gamma_z=%.4f/um'
          % (m['neff'], gy / 1e6, gz / 1e6))
    res['conv_mode'] = dict(neff=m['neff'], gamma_y_um=gy / 1e6,
                            gamma_z_um=gz / 1e6)
    ktab = []
    for d_um in (12, 15, 20, 30, 40, 50):
        kap, ov = cmt_kappa(m, d_um * 1e-6, 0.0)
        ktab.append(dict(kind='horizontal', d_um=d_um, dz_um=0.0,
                         kappa_mm_inv=kap * 1e-3, overlap=ov))
        print('  horizontal d=%5.1f um : kappa = %.4e 1/mm  (overlap %.3e)'
              % (d_um, kap * 1e-3, ov), flush=True)
    for dz_um in (10, 20, 30):
        kap, ov = cmt_kappa(m, 0.0, dz_um * 1e-6)
        ktab.append(dict(kind='vertical', d_um=0.0, dz_um=dz_um,
                         kappa_mm_inv=kap * 1e-3, overlap=ov))
        print('  vertical   dz=%5.1f um : kappa = %.4e 1/mm  (overlap %.3e)'
              % (dz_um, kap * 1e-3, ov), flush=True)
    # fine scan for the in-plane case d=15
    for d_um in (14, 15, 16):
        kap, ov = cmt_kappa(m, d_um * 1e-6, 0.0)
        print('  fine horizontal d=%.0f: kappa=%.5e 1/mm' % (d_um, kap * 1e-3))
    res['cmt'] = ktab
    # 2-D in-plane EIM CMT for reference
    y = np.linspace(-30e-6, 30e-6, 60001)
    phi = fw.slab_profile(y, SOL_EIM)
    phi = phi / np.sqrt(np.sum(phi ** 2) * (y[1] - y[0]))
    beta2 = SOL_EIM['beta']
    k2 = []
    for d_um in (12, 15, 20, 30, 40, 50):
        d = d_um * 1e-6
        from scipy.ndimage import shift as ndshift
        dy = d / (y[1] - y[0])
        phi2 = ndshift(phi, shift=-dy, order=3, mode='constant')
        core2 = (np.abs(y - d) <= W / 2).astype(float)
        num = np.sum(core2 * phi * phi2) * (y[1] - y[0])
        den = np.sum(phi ** 2) * (y[1] - y[0])
        kappa = fw.K0 ** 2 / (2 * beta2) * (fw.N_SLAB ** 2 - fw.N_CLAD ** 2) * num / den
        k2.append(dict(d_um=d_um, kappa_mm_inv=kappa * 1e-3))
        print('  2-D EIM CMT d=%5.1f um: kappa = %.4e 1/mm' % (d_um, kappa * 1e-3))
    res['cmt_2d'] = k2
    shp = [c['kappa_mm_inv'] for c in k2 if c['d_um'] in (15, 25, 35)]
    if len(shp) >= 2:
        import math
        # effective exponential decay constant of kappa(d)
        k15 = [c['kappa_mm_inv'] for c in k2 if c['d_um'] == 15][0]
        k30 = [c['kappa_mm_inv'] for c in k2 if c['d_um'] == 30][0]
        k50 = [c['kappa_mm_inv'] for c in k2 if c['d_um'] == 50][0]
        g1 = -math.log(k30 / k15) / (15e-6) / 1e6
        g2 = -math.log(k50 / k30) / (20e-6) / 1e6
        print('  kappa(d) effective decay constants: gamma(15-30)=%.4f/um, '
              'gamma(30-50)=%.4f/um  (mode gamma = %.4f/um)'
              % (g1, g2, SOL_EIM['gamma'] / 1e6))
        res['kappa_decay_gamma_um'] = [g1, g2]
    json.dump(res, open(os.path.join(CACHE, 'mode3d_cmt.json'), 'w'), indent=1,
              default=float)
    print('saved', os.path.join(CACHE, 'mode3d_cmt.json'))


if __name__ == '__main__':
    main()
