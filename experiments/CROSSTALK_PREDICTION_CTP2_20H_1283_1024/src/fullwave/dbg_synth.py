"""Test the oblique line derivative/interpolation sign with a synthetic mode."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fwlib as fw
from run_2d_tilted import build

sim, meta = build(30, 0.05, label='synth')
g = sim.g
sol = fw.fw_slab_analytic()
beta = sol['beta']
x = g.axes[0][:, None]
y = g.axes[1][None, :]


def synth_C(fp, arm):
    """build the DFT 'box' that a pure forward mode would produce on the line.
    We emulate a pure complex exponential along u and *unit amplitude*, then rescale
    to the window convention (arbitrary: only ratios matter)."""
    cpt = np.array(fp['p0']) * 0 + (np.array(fp['p0']) + np.array(fp['p1'])) / 2
    eu = arm['eu']
    es = arm['es']
    u = (x - cpt[0]) * eu[0] + (y - cpt[1]) * eu[1]
    s = (x - cpt[0]) * es[0] + (y - cpt[1]) * es[1]
    phi = fw.fw_slab_profile(s, sol)
    C = phi * np.exp(1j * beta * u)
    i0, i1 = fp['box'].sl[0].start, fp['box'].sl[0].stop
    j0, j1 = fp['box'].sl[1].start, fp['box'].sl[1].stop
    return C[i0:i1, j0:j1]


for nm in ('out', 'in'):
    arm = sim.oblique_arms[nm]
    fp = arm['entries'][1]
    C = synth_C(fp, arm)
    psi, Dn = sim._sample_line(C, fp)
    dl = arm['dl']
    phi = arm['phi']
    inner = dl * np.sum(phi * psi)
    innerD = dl * np.sum(phi * Dn)
    N = 1000.0
    print(nm, 'innerD/inner =', innerD / inner, ' i*beta =', 1j * beta)
    bplus = 0.5 * (inner + innerD / (1j * beta))
    bminus = 0.5 * (inner - innerD / (1j * beta))
    print('   |b+|/|inner| =', abs(bplus) / abs(inner), ' |b-|/|inner| =',
          abs(bminus) / abs(inner))
