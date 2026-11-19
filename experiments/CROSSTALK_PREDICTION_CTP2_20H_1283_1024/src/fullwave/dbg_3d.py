"""Debug 3-D port normalization: compare modal amplitude and Poynting flux."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fwlib as fw
import fwlib3d as f3

dx = 0.30e-6
W = fw.W_CORE
phys = ((-40e-6, 60e-6), (-8e-6, 8e-6), (-8e-6, 8e-6))
sim = f3.Sim3D(phys, 8e-6, dx, order=6,
               guides=[dict(p=(0.0, 0.0, 0.0), angle=0.0, w=W, h=W, nc=fw.N_CORE)],
               n_core=fw.N_CORE, label='smoke')
sim.add_port_x(-10e-6, 0.0, 0.0, 'in')
sim.add_port_x(50e-6, 0.0, 0.0, 'through')
sim.set_source(-30e-6, 0.0, 0.0)
sim.run(window_periods=30, print_every=2000)
res = sim.analyse()
for nm, p in [(p['name'], p) for p in sim.ports]:
    C = p['box'].get()
    m = sim.m
    il = p['ix'] - p['box'].sl[0].start
    psi = C[il]
    dyz = dx * dx
    inner = dyz * np.sum(p['phi'] * psi)
    D = sim._d1(C, il, 0)
    innerD = dyz * np.sum(p['phi'] * D)
    print(nm, 'inner=%s innerD/inner=%s' % (str(inner), str(innerD / inner)),
          'i*beta_d=', 1j * p['beta_d'])
    print('   abs(innerD/inner)/beta_d -1 =', abs(innerD / inner) / p['beta_d'] - 1.0)
    print('   a_plus=%.4e  P_plus=%.4e  P_flux=%.4e   ratio modal/flux=%.4f'
          % (res['ports'][nm]['a_plus'], res['ports'][nm]['P_plus'],
             res['ports'][nm]['P_flux'],
             res['ports'][nm]['P_plus'] / res['ports'][nm]['P_flux']))
    # compare the measured transverse profile with phi
    print('   max|phi|=%.3e max|psi|=%.3e  inner/(norm) ...' % (np.abs(p['phi']).max(),
                                                              np.abs(psi).max()))
    ratio = np.abs(psi) / np.maximum(np.abs(p['phi']), 1e-30)
    sel = np.abs(p['phi']) > 0.3 * np.abs(p['phi']).max()
    print('   |psi|/|phi| over core region: mean %.4e std/mean %.3f'
          % (ratio[sel].mean(), ratio[sel].std() / abs(ratio[sel].mean())))
    # manual normalisation check
    Nw = sim.window_values
    A = 4.0 * abs(inner) / Nw
    om, beta = sim.omega, p['beta']
    P_expected = 0.5 * om * beta * A ** 2
    flux_manual = 4.0 * (2 * om / Nw ** 2) * dx ** 3 * np.sum(
        np.imag(np.conj(psi) * D))
    print('   A=%.4e  P_modal=%.4e  flux_manual=%.4e  ratio=%.4f  beta_corr=%.6f'
          % (A, P_expected, flux_manual, P_expected / flux_manual,
             abs(D[sel]).sum() / abs(psi[sel]).sum() * 0 + 1.0))
    print('   sum|psi|^2*dx^3=%.4e  (A N/4)^2/dx^2=%.4e  ratio=%.4f'
          % (np.sum(np.abs(psi) ** 2) * dx ** 3,
             (A * Nw / 4) ** 2 / dx ** 2,
             np.sum(np.abs(psi) ** 2) * dx ** 3 / ((A * Nw / 4) ** 2 / dx ** 2)))

