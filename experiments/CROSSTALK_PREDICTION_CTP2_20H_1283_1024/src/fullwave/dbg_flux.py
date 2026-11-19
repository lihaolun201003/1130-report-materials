"""Debug: straight-guide port/flux normalization and signs."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fwlib as fw

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(HERE, '..', '..'))

dx = 0.05e-6
phys = ((-30e-6, 130e-6), (-25e-6, 25e-6))
sim = fw.Sim2D(phys, 12e-6, dx, order=4,
               guides=[dict(p=(0, 0), angle=0.0, w=fw.W_SLAB, nc=fw.N_SLAB)],
               n_core=fw.N_SLAB, label='s', device='cuda')
sim.add_port_x(-18e-6, 0.0, 'in')
sim.add_port_x(112e-6, 0.0, 'out')
sim.add_port_x(-20e-6, 0.0, 'srcback')
sim.add_boundary_probes()
sim.set_source(-24e-6, 0.0)
print('N', sim.g.N, 'cells', np.prod(sim.g.N))
sim.run(window_periods=40, print_every=3000)
res = sim.analyse_ports()
print('meta nwin', sim.window_values, 'dt', sim.dt)
for k, v in res['ports'].items():
    print(k, {kk: ('%.4e' % vv if isinstance(vv, float) else vv) for kk, vv in v.items()})
print('boundary', res['boundary'])
# direct checks with the snapshot: projection of the DFT field
om, N = sim.omega, sim.window_values
C = res['ports']['out']['box'].get() if False else None
# inspect DFT amplitude scale directly at the output port box
box = [p for p in sim.ports if p['name'] == 'out'][0]['box']
Cz = box.get()
ixl = 3
psiC = Cz[ixl]
dy = dx
phi = [p for p in sim.ports if p['name'] == 'out'][0]['phi']
inner = dy * np.sum(phi * psiC)
print('inner (out, forward) =', inner, ' |inner| =', abs(inner))
print('expected |inner| = a*N/4 for amplitude a; with a=1 ->', N / 4)
D = np.zeros_like(psiC)
d = fw.fd1_coeffs(4)
for k, dk in enumerate(d, start=1):
    D += dk * (Cz[ixl + k] - Cz[ixl - k]) / dx
print('innerD/inner (should be i*beta_d):', (dy * np.sum(phi * D)) / inner,
      ' i*beta=', 1j * [p for p in sim.ports if p['name'] == 'out'][0]['beta_d'])
# flux from the same box
Pf = sim._flux_from_box(Cz, ixl, box, axis=0)
print('raw flux formula (out):', Pf)
# true guided power from modal amplitude a = 4*inner/N
a = 4 * abs(inner) / N
P_true = 0.5 * om * [p for p in sim.ports if p['name'] == 'out'][0]['beta'] * a ** 2
print('a_true =', a, ' P_true =', P_true, ' P_true/raw_flux =', P_true / Pf)
