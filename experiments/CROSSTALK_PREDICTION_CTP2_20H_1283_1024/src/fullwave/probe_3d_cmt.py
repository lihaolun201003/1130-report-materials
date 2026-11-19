"""3-D channel CMT coupling coefficients from the converged scalar channel mode.

Solves the 2-D transverse eigenproblem (continuous Laplacian, 2nd-order FD) on a
large domain so that the cladding tail is not distorted by the Dirichlet wall,
fits the cladding decay constants, and computes the CMT coupling coefficient

    kappa = (k0^2/(2 beta)) (n_core^2-n_clad^2) Int_{core2} phi1 phi2 dA / Int phi1^2 dA

for two identical channels separated horizontally by d or vertically by dz.

Also reports the discrete-mode n_eff convergence (Richardson) vs the converged
value 1.50455547 and the 2-D EIM proxy 1.50458471.
"""
import json
import os
import sys
import time

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import eigsh

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(HERE, '..', '..'))
CACHE = os.path.join(BASE, 'cache', 'fullwave')
sys.path.insert(0, HERE)
import fwlib as fw

N_CLAD, N_CORE, W = fw.N_CLAD, fw.N_CORE, fw.W_CORE
TARGET = 1.50455547
EIM = fw.slab_analytic(fw.N_SLAB, N_CLAD, fw.W_SLAB)['neff']


def lap1d(N, dx):
    e = np.ones(N)
    return sparse.diags([e[:-1], -2 * e, e[:-1]], [-1, 0, 1]) / dx ** 2


def channel_mode(half, dx, n_core=N_CORE, n_clad=N_CLAD, k=3):
    N = int(round(2 * half / dx)) + 1
    ax = -half + dx * np.arange(N)
    Y = ax[:, None]
    Z = ax[None, :]
    n = np.where((np.abs(Y) <= W / 2) & (np.abs(Z) <= W / 2), n_core, n_clad)
    L = lap1d(N, dx)
    I = sparse.identity(N)
    L2 = (sparse.kron(I, L) + sparse.kron(L, I)).tocsr()
    # use the continuous frequency (no leapfrog correction) for the CMT model
    M = (L2 + sparse.diags((fw.K0 ** 2) * n.ravel() ** 2)).tocsr()
    vals, vecs = eigsh(M, k=k, which='LA')
    order = np.argsort(vals)[::-1]
    for j in order:
        s = vals[j]
        if s <= 0:
            continue
        phi = vecs[:, j].reshape(N, N)
        mx = np.abs(phi).max()
        edge = max(np.abs(phi[0, :]).max(), np.abs(phi[-1, :]).max(),
                   np.abs(phi[:, 0]).max(), np.abs(phi[:, -1]).max())
        if edge / mx > 1e-3:
            continue
        phi /= np.sqrt(np.sum(phi ** 2) * dx * dx)
        return dict(phi=phi, ax=ax, dx=dx, neff=np.sqrt(s) / fw.K0, N=N)
    raise RuntimeError('no mode')


def fit_gamma(prof, ax, r1, r2):
    """fit d ln|prof| / dr in the annulus r1<r<r2 (metres)."""
    sel = (np.abs(ax) > r1) & (np.abs(ax) < r2)
    r = np.abs(ax[sel])
    p = prof[sel]
    good = p > 0
    return -np.polyfit(r[good], np.log(p[good]), 1)[0]


def cmt(mode, d, dz, n_core=N_CORE, n_clad=N_CLAD):
    from scipy.ndimage import shift as ndshift
    phi, ax, dx = mode['phi'], mode['ax'], mode['dx']
    # displaced mode
    phi2 = ndshift(phi, shift=(-d / dx, -dz / dx), order=3, mode='constant')
    # core mask of the displaced guide
    Y = ax[:, None]
    Z = ax[None, :]
    core2 = ((np.abs(Y - d) <= W / 2) & (np.abs(Z - dz) <= W / 2)).astype(float)
    num = np.sum(core2 * phi * phi2) * dx * dx
    den = np.sum(phi ** 2) * dx * dx
    beta = mode['neff'] * fw.K0
    kappa = fw.K0 ** 2 / (2 * beta) * (n_core ** 2 - n_clad ** 2) * num / den
    return float(kappa), float(num / den)


def main():
    res = {}
    t0 = time.time()
    print('=== discrete 3-D channel mode n_eff convergence (order 2, continuous) ===')
    rows = []
    for dx_um in (0.20, 0.15, 0.12, 0.10, 0.08):
        m = channel_mode(20e-6, dx_um * 1e-6)
        rows.append(dict(dx_um=dx_um, neff=m['neff'], err=m['neff'] - TARGET))
        print('  dx=%.2f: n_eff=%.8f (err %+.2e)  [%.0fs]'
              % (dx_um, m['neff'], m['neff'] - TARGET, time.time() - t0), flush=True)
    srt = sorted(rows, key=lambda r: r['dx_um'], reverse=True)
    a, b = srt[-2], srt[-1]
    r = (a['dx_um'] / b['dx_um']) ** 2
    ext = (b['neff'] - a['neff'] / r) / (1 - 1 / r)
    print('  Richardson(dx^2) extrapolated n_eff = %.8f (target %.8f, EIM %.8f)'
          % (ext, TARGET, EIM))
    res['mode_rows'] = rows
    res['neff_extrap'] = ext
    res['neff_target'] = TARGET
    res['neff_eim'] = EIM
    # ---- converged mode for CMT: large domain, dx = 0.08 -------------------
    print('=== converged mode (half=30 um, dx=0.08) ===', flush=True)
    m = channel_mode(30e-6, 0.08e-6)
    ax = m['ax']
    j0 = np.argmin(np.abs(ax))
    prof = np.abs(m['phi'][:, j0]); prof = prof / prof.max()
    gy = fit_gamma(prof, ax, 10e-6, 22e-6)
    profz = np.abs(m['phi'][j0, :]); profz = profz / profz.max()
    gz = fit_gamma(profz, ax, 10e-6, 22e-6)
    gtot = np.sqrt((m['neff'] ** 2 - N_CLAD ** 2)) * fw.K0
    print('  n_eff=%.8f  gamma_y=%.4f/um gamma_z=%.4f/um  gamma_tot=%.4f/um'
          % (m['neff'], gy / 1e6, gz / 1e6, gtot / 1e6))
    res['conv_mode'] = dict(neff=m['neff'], gamma_y_um=gy / 1e6,
                            gamma_z_um=gz / 1e6, gamma_tot_um=gtot / 1e6)
    np.savez(os.path.join(CACHE, 'mode3d_profiles.npz'),
             ax=ax, phi=m['phi'][:, j0], phi_z=m['phi'][j0, :])
    # ---- CMT ---------------------------------------------------------------
    print('=== CMT coupling coefficients ===')
    ktab = []
    for d_um in (12, 15, 20, 25, 30):
        kap, ov = cmt(m, d_um * 1e-6, 0.0)
        ktab.append(dict(kind='horizontal', d_um=d_um, dz_um=0.0,
                         kappa_mm_inv=kap * 1e-3, overlap=ov))
        print('  horizontal d=%5.1f um: kappa=%.4e 1/mm (%.2f dB beat length %.2f mm)'
              % (d_um, kap * 1e-3, 10 * np.log10(max(abs(kap * 1e-3), 1e-30)),
                 np.pi / (2 * max(kap, 1e-30)) * 1e3), flush=True)
    for dz_um in (10, 20, 25):
        kap, ov = cmt(m, 0.0, dz_um * 1e-6)
        ktab.append(dict(kind='vertical', d_um=0.0, dz_um=dz_um,
                         kappa_mm_inv=kap * 1e-3, overlap=ov))
        print('  vertical   dz=%5.1f um: kappa=%.4e 1/mm'
              % (dz_um, kap * 1e-3), flush=True)
    res['cmt'] = ktab
    # gamma from kappa(d) exponential fit
    kd = {r['d_um']: r['kappa_mm_inv'] for r in ktab if r['kind'] == 'horizontal'}
    if 15 in kd and 25 in kd:
        g = -np.log(abs(kd[25] / kd[15])) / (10e-6) / 1e6
        print('  kappa(d) exponential decay constant (15->25 um): %.4f /um' % g)
        res['kappa_gamma_um'] = float(g)
    json.dump(res, open(os.path.join(CACHE, 'mode3d_cmt.json'), 'w'), indent=1,
              default=float)
    print('saved mode3d_cmt.json  [%.0fs]' % (time.time() - t0))


if __name__ == '__main__':
    main()
