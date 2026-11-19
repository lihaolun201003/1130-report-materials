"""Debug oblique arm sampling on the crossing geometry."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fwlib as fw
from run_2d_crossing import make_crossing_sim
from scipy.ndimage import map_coordinates

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(HERE, '..', '..'))
CACHE = os.path.join(BASE, 'cache', 'fullwave')

theta_deg, dx_um, sep_um = 30.0, 0.08, 40.0
sim, meta = make_crossing_sim(theta_deg, dx_um, sep_um, order=4, t_abs_um=14.0,
                              label='dbg', device='cuda')
print('N', sim.g.N, 'cells', meta['cells'])
sim.run(window_periods=30, print_every=3000)
arm = sim.oblique_arms['cross_p']
fp = arm['entries'][1]
C = fp['box'].get()
print('box shape', C.shape, 'box slice', fp['box'].sl)
print('|C| max in box', np.abs(C).max())
psi, Dn = sim._sample_line(C, fp)
print('sampled |psi| max', np.abs(psi).max(), ' |Dn| max', np.abs(Dn).max())
print('sampled psi (subsample 100):', np.round(np.abs(psi[::100]) * 1e9, 4), 'e-9')
print('sampled Dn (subsample 100):', np.round(np.abs(Dn[::100]) * 1e9, 4), 'e-9')
# check phi
print('phi max', np.abs(arm['phi']).max(), 'sum phi^2 dl', np.sum(arm['phi'] ** 2) * arm['dl'])
inner = arm['dl'] * np.sum(arm['phi'] * psi)
innerD = arm['dl'] * np.sum(arm['phi'] * Dn)
print('inner', inner, ' innerD', innerD)
print('beta_guess', arm and fw.fw_slab_analytic()['beta'])
print('ratio innerD/inner', innerD / inner)
# Also check: where is the field actually around that location? Inspect the DFT box row maxima
i0, i1 = fp['box'].sl[0].start, fp['box'].sl[0].stop
j0, j1 = fp['box'].sl[1].start, fp['box'].sl[1].stop
print('box x range um', sim.g.axes[0][i0] * 1e6, sim.g.axes[0][i1 - 1] * 1e6)
print('box y range um', sim.g.axes[1][j0] * 1e6, sim.g.axes[1][j1 - 1] * 1e6)
print('fp line x range um', fp['xs'].min() * 1e6, fp['xs'].max() * 1e6,
      ' y range', fp['ys'].min() * 1e6, fp['ys'].max() * 1e6)
print('fp fx range', fp['fx'].min(), fp['fx'].max(), ' fy range', fp['fy'].min(), fp['fy'].max())
print('expected box size', i1 - i0, j1 - j0, ' = ', fp['fy'].max() - fp['fy'].min(),
      fp['fx'].max() - fp['fx'].min())
# where's the max |C| in the box
ii, jj = np.unravel_index(np.argmax(np.abs(C)), C.shape)
print('max |C| at local', ii, jj, ' global x,y um',
      sim.g.axes[0][i0 + ii] * 1e6, sim.g.axes[1][j0 + jj] * 1e6)
# through port for reference
res = sim.analyse_ports()
print('through a+', res['ports']['through']['a_plus'], ' in a+', res['ports']['in']['a_plus'])
