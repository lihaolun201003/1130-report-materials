"""CMT coupling coefficients from the converged scalar modes (no FDTD).

2-D: in-plane EIM slab (analytic mode profile).
3-D: channel mode from the saved transverse eigenmode slices, reconstructed as a
     separable product (the exact 2-D mode is used for n_eff / decay constants;
     the separability error on the overlap integral is small).

Outputs cache/fullwave/cmt.json
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(HERE, '..', '..'))
CACHE = os.path.join(BASE, 'cache', 'fullwave')
sys.path.insert(0, HERE)
import fwlib as fw

N_CLAD, N_CORE, W = fw.N_CLAD, fw.N_CORE, fw.W_CORE


def cmt2d(d_um_list):
    """in-plane EIM slab coupling."""
    sol = fw.fw_slab_analytic()
    y = np.linspace(-40e-6, 40e-6, 80001)
    dy = y[1] - y[0]
    phi = fw.slab_profile(y, sol)
    phi = phi / np.sqrt(np.sum(phi ** 2) * dy)
    beta = sol['beta']
    out = []
    for d_um in d_um_list:
        d = d_um * 1e-6
        from scipy.ndimage import shift as nds
        phi2 = nds(phi, shift=+d / dy, order=3, mode='constant')
        x2 = (np.abs(y - d) <= W / 2).astype(float)
        num = np.sum(x2 * phi * phi2) * dy
        den = np.sum(phi ** 2) * dy
        kap = fw.K0 ** 2 / (2 * beta) * (fw.N_SLAB ** 2 - N_CLAD ** 2) * num / den
        out.append(dict(d_um=d_um, kappa_mm_inv=kap * 1e-3,
                        beat_length_mm=float(np.pi / (2 * kap) * 1e3)))
    return out


def cmt3d():
    d = np.load(os.path.join(CACHE, 'mode3d_profiles.npz'))
    ax = d['ax']
    phi_y = np.abs(d['phi'])
    phi_z = np.abs(d['phi_z'])
    # rebuild sign-coherent profiles by taking the real part (mode is real apart
    # from an arbitrary global sign; use absolute value is wrong for the overlap
    # only near sign changes, so use the raw real parts)
    raw = np.load(os.path.join(CACHE, 'mode3d_profiles.npz'))
    # the saved arrays are |phi| slices; use them (positive definite) which is a
    # very good approximation for the fundamental mode (no nodes)
    phi_y = phi_y / np.sqrt(np.sum(phi_y ** 2) * (ax[1] - ax[0]))
    phi_z = phi_z / np.sqrt(np.sum(phi_z ** 2) * (ax[1] - ax[0]))
    dx = ax[1] - ax[0]
    # decay fit
    p = phi_y / phi_y.max()
    sel = (np.abs(ax) > 10e-6) & (np.abs(ax) < 22e-6)
    gam = -np.polyfit(np.abs(ax[sel]), np.log(p[sel]), 1)[0]
    beta = 1.50455547 * fw.K0
    # 2-D overlap factor: the separability normalisation
    # phi(y,z) = phi_y(y) phi_z(z) / sqrt( sum phi_y^2 dy * sum phi_z^2 dy ) ...
    # with each 1-D slice normalised int = 1, the product is normalised int dA = 1
    from scipy.ndimage import shift as nds
    out = []
    Y = ax[:, None]
    Z = ax[None, :]
    phiy2_y = None
    for d_um, dz_um in [(15, 0), (20, 0), (0, 10), (0, 20), (0, 25)]:
        dd = d_um * 1e-6
        ddz = dz_um * 1e-6
        py2 = nds(phi_y, shift=+dd / dx, order=3, mode='constant')
        pz2 = nds(phi_z, shift=+ddz / dx, order=3, mode='constant')
        core2 = ((np.abs(Y - dd) <= W / 2) & (np.abs(Z - ddz) <= W / 2)).astype(float)
        # integral over dA of phi1*phi2 over guide-2 core
        # phi1 = phi_y(y)*phi_z(z), phi2 = phi_y(y-d)*phi_z(z-dz)
        num = np.sum(core2 * (phi_y[:, None] * phi_z[None, :]) *
                     (py2[:, None] * pz2[None, :])) * dx * dx
        kap = fw.K0 ** 2 / (2 * beta) * (N_CORE ** 2 - N_CLAD ** 2) * num
        out.append(dict(kind='horizontal' if dz_um == 0 else 'vertical',
                        d_um=float(d_um), dz_um=float(dz_um),
                        kappa_mm_inv=kap * 1e-3,
                        beat_length_mm=float(np.pi / (2 * abs(kap)) * 1e3)))
    return out, dict(gamma_y_um=gam / 1e6, beta=beta)


def main():
    res = {}
    print('=== 2-D in-plane EIM CMT ===')
    tab2 = cmt2d([12, 15, 20, 25, 30, 40, 50])
    for r in tab2:
        print('  d=%5.1f um: kappa=%.4e 1/mm  (beat %.3g mm)'
              % (r['d_um'], r['kappa_mm_inv'], r['beat_length_mm']))
    res['cmt_2d'] = tab2
    # effective exponential decay constant from kappa(d)
    kd = {r['d_um']: r['kappa_mm_inv'] for r in tab2}
    if 15 in kd and 25 in kd:
        g = -np.log(abs(kd[25] / kd[15])) / 10e-6 / 1e6
        print('  effective kappa(d) decay constant: gamma_eff = %.4f /um'
              % g)
        res['kappa_gamma_um'] = float(g)
    print('=== 3-D CMT (separable reconstruction of the converged mode) ===')
    tab3, info = cmt3d()
    for r in tab3:
        print('  %-10s d=%4.1f dz=%4.1f um: kappa=%.4e 1/mm  (beat %.3g mm)'
              % (r['kind'], r['d_um'], r['dz_um'], r['kappa_mm_inv'],
                 r['beat_length_mm']))
    res['cmt_3d'] = tab3
    res['mode3d'] = info
    print('  mode decay gamma_y = %.4f /um' % info['gamma_y_um'])
    json.dump(res, open(os.path.join(CACHE, 'cmt.json'), 'w'), indent=1,
              default=float)


if __name__ == '__main__':
    main()
