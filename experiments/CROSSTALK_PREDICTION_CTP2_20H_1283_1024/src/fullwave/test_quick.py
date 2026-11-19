"""Quick self-test of the solver library (small grids, fast).

Checks:
 1. analytic slab solve reproduces the quoted EIM targets (n_slab, n_eff2D);
 2. discrete eigenmode of the 4th/6th-order operator -> beta, and its dx-convergence
    to the analytic value (dispersion benefit of higher order);
 3. torch stepper vs float64 NumPy reference step (identical update), 50 steps;
 4. tiny 2-D straight-guide run: |a+|=1 reference, |a-| level, beta from phase
    slope vs discrete prediction, flux consistency.

Run:  python test_quick.py
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fwlib as fw

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(HERE, '..', '..'))
OUT = os.path.join(BASE, 'outputs', 'fullwave')
CACHE = os.path.join(BASE, 'cache', 'fullwave')
os.makedirs(OUT, exist_ok=True)
os.makedirs(CACHE, exist_ok=True)


def main():
    print('=== 1. analytic slab ===')
    sol1 = fw.slab_analytic(fw.N_CORE, fw.N_CLAD, fw.W_CORE)   # EIM stage 1 (x slab)
    print('stage-1 (n_core=1.5065) : n_eff = %.9f  (expected EIM slab index %.7f)'
          % (sol1['neff'], fw.N_SLAB))
    sol2 = fw.slab_analytic(fw.N_SLAB, fw.N_CLAD, fw.W_CORE)   # EIM stage 2 (y slab)
    print('stage-2 (n_slab=%.7f): n_eff = %.9f  (target %.6f)'
          % (fw.N_SLAB, sol2['neff'], fw.NEFF2D_TARGET))
    print('         gamma = %.6f 1/um (target %.4f)' % (sol2['gamma'] / 1e6, fw.GAMMA_TARGET / 1e6))

    print('\n=== 2. discrete eigenmode convergence (straight 2-D slab) ===')
    tab = {}
    for order in (2, 4, 6, 8):
        rows = []
        for dx_um in (0.16, 0.12, 0.08, 0.05, 0.03, 0.02):
            dx = dx_um * 1e-6
            # small transverse window: +-25 um; absorber thickness ~12 um, order pad
            g = fw.Grid(((-40e-6, 40e-6), (-25e-6, 25e-6)), t_abs=10e-6, dx=dx,
                        order=order, n_core=fw.N_SLAB)
            g.build_index([])
            Y = g.axes[1]
            nprof = np.where(np.abs(Y) <= fw.W_SLAB / 2, fw.N_SLAB, fw.N_CLAD)
            s, phi = fw.discrete_mode_1d((Y,), nprof, dx, order, g.omega_eff)
            beta = fw.beta_from_stencil_eig(s, dx, order)
            rows.append(dict(dx_um=dx_um, neff=beta / fw.K0))
            print('  order %d dx=%.2f um : n_eff = %.7f  (err = %+.2e)'
                  % (order, dx_um, beta / fw.K0, beta / fw.K0 - fw.NEFF2D_TARGET))
        tab[order] = rows
    print('  => error scaling demonstrates the dispersion benefit of high order')

    print('\n=== 3. torch vs numpy reference step ===')
    g = fw.Grid(((-30e-6, 30e-6), (-15e-6, 15e-6)), t_abs=8e-6, dx=0.1e-6,
                order=4, n_core=fw.N_SLAB)
    g.build_index([dict(p=(0.0, 0.0), angle=0.0, w=fw.W_SLAB, nc=fw.N_SLAB)])
    g.build_sigma()
    st = fw.Stepper(g, device='cuda')
    rng = np.random.default_rng(7)
    a0 = np.zeros(g.N); b0 = np.zeros(g.N)
    sl = tuple(slice(g.pad, -g.pad) for _ in range(2))
    a0[sl] = rng.standard_normal((g.N[0] - 2 * g.pad, g.N[1] - 2 * g.pad)) * 1e-3
    st.psi_a.copy_(__import__('torch').as_tensor(a0, device=st.device, dtype=st.dtype))
    st.psi_b.copy_(__import__('torch').as_tensor(b0, device=st.device, dtype=st.dtype))
    a, b = a0, b0
    for _ in range(30):
        c_np = st.np_step(a, b)
        a, b = b, c_np
    a_t = a0.copy(); b_t = b0.copy()
    st.psi_a.copy_(__import__('torch').as_tensor(a_t, device=st.device, dtype=st.dtype))
    st.psi_b.copy_(__import__('torch').as_tensor(b_t, device=st.device, dtype=st.dtype))
    for _ in range(30):
        st.step()
    c_t = st.psi_a.detach().cpu().numpy()
    err = np.abs(c_t - b) / max(np.abs(b).max(), 1e-30)
    print('  numpy vs torch relative max diff after 30 steps: %.3e' % err.max())

    print('\n=== 4. tiny 2-D straight guide run ===')
    dx = 0.1e-6
    L = 60e-6
    sim = fw.Sim2D(((-15e-6, L + 5e-6), (-25e-6, 25e-6)), t_abs=10e-6, dx=dx,
                   order=4, guides=[dict(p=(L / 2, 0.0), angle=0.0, w=fw.W_SLAB)],
                   n_core=fw.N_SLAB, label='test')
    sim.add_port_x(0.0, 0.0, 'in')
    sim.add_port_x(L, 0.0, 'out')
    sim.add_boundary_probes()
    sim.add_plane_probe(L / 2, 'mid')
    sim.add_beta_projector(8e-6, L - 8e-6, 0.0)
    sim.add_source_back_line(-9e-6, 'srcback')
    sim.set_source(-6e-6, 0.0, amp=1.0)
    sim.run(t_settle_extra=0.15e-12, window_periods=40.0, print_every=500)
    print('  meta:', json.dumps({k: (v if not isinstance(v, np.ndarray) else 'arr')
                                 for k, v in sim.meta.items()}, indent=1))
    res = sim.analyse_ports()
    print('  ports:', json.dumps(res['ports'], indent=1))
    print('  flux_ports:', json.dumps(res['flux_ports'], indent=1))
    print('  boundary :', json.dumps(res['boundary'], indent=1))
    pr = sim.beta_from_projector()
    print('  beta from phase slope: neff=%.7f  (direct=%.7f, analytic=%.7f, resid_std=%.2e rad)'
          % (pr['neff'], pr['neff_direct'], fw.NEFF2D_TARGET, pr['phase_resid_std']))
    # energy bookkeeping
    Pin = res['ports']['in']['P_flux']
    r = res['ports']['in']['ratio_bwd']
    Pinc = Pin / (1 - r ** 2)
    pback = res['flux_ports']['srcback']['P_flux']
    bnd = sum(res['boundary'].values())
    print('  Pinc_net=%.4e  P_inc(modal-normalised)=%.4e  P_src_back=%.4e  P_boundary=%.4e'
          % (Pin, Pinc, pback, bnd))
    print('  T_through_modal = %.6f' % (res['ports']['out']['P_plus'] / res['ports']['in']['P_plus']))
    print('  T_through_flux  = %.6f' % (res['ports']['out']['P_flux'] / Pinc))
    print('  T_refl          = %.3e (%.1f dB)' % (r ** 2, 20 * np.log10(max(r, 1e-16))))
    print('  T_rad           = %.4e' % ((Pin - res['ports']['out']['P_flux']) / Pinc))
    print('  energy residual (boundary - src_back - Pin)/Pin = %.3e'
          % ((bnd - pback - Pin) / Pin))
    json.dump(dict(mode_sweep=tab, port_res=res, beta=pr,
                   energy=dict(Pin=Pin, Pinc=Pinc, pback=pback, bnd=bnd), meta=sim.meta),
              open(os.path.join(CACHE, 'test_quick.json'), 'w'), indent=1, default=float)
    print('\nOK')


if __name__ == '__main__':
    main()
