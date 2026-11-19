"""Quick smoke test of the 3-D solver on a coarse, small grid."""
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fwlib as fw
import fwlib3d as f3

dx = 0.30e-6
W = fw.W_CORE
phys = ((-30e-6, 30e-6), (-8e-6, 8e-6), (-8e-6, 8e-6))
t0 = time.time()
sim = f3.Sim3D(phys, 8e-6, dx, order=6,
               guides=[dict(p=(0.0, 0.0, 0.0), angle=0.0, w=W, h=W, nc=fw.N_CORE)],
               n_core=fw.N_CORE, label='smoke')
print('grid', sim.N, 'Nyp', sim.Nyp, 'dt', sim.dt, 'cells M',
      np.prod(sim.N) / 1e6, 'setup %.1fs' % (time.time() - t0))
sim.add_port_x(-15e-6, 0.0, 0.0, 'in')
sim.add_port_x(15e-6, 0.0, 0.0, 'through')
sim.add_port_x(-20e-6, 0.0, 0.0, 'srcback')
sim.add_beta_projector(-10e-6, 20e-6, 0.0, 0.0, 'proj')
sim.add_boundary_probes()
sim.set_source(-22e-6, 0.0, 0.0)
t0 = time.time()
sim.run(window_periods=30, print_every=500)
print('run %.1fs' % (time.time() - t0))
res = sim.analyse()
for k, v in res['ports'].items():
    print(k, {kk: ('%.4e' % vv) for kk, vv in v.items()})
print('boundary', {k: '%.3e' % v for k, v in res['boundary'].items()})
pr = sim.beta_from_projector()
print('beta measured %.6e neff=%.7f  discrete neff=%.7f  resid=%.2e'
      % (pr['beta'], pr['neff'], pr['neff_discrete'], pr['resid']))
