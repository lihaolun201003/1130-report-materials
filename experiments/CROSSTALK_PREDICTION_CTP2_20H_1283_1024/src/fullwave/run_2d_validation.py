"""Deliverable-1 validation: 2-D scalar FDTD straight waveguide.

Produces
  outputs/fullwave/fdtd2d_validation.csv   (FDTD + discrete-mode reference data)
  outputs/fullwave/fdtd2d_convergence.csv  (dx/order dispersion study incl. gamma)
  outputs/fullwave/absorber_reflection.csv (lossy-layer absorber reflectivity)

Checks
  1. NumPy reference step vs torch step (float64 vs float32 kernels).
  2. Discrete eigenmode n_eff(dx, order) -> Richardson extrapolation vs analytic.
  3. FDTD straight guide: measured beta from the phase slope of the mode
     projection, propagation loss over 200 um, |a-|/|a+| level.
  4. dx convergence (0.08, 0.05, 0.03, 0.02 um) and CFL variation.
  5. graded absorber reflectivity vs layer thickness.

Run:  python run_2d_validation.py [--quick]
"""
import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fwlib as fw

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(HERE, '..', '..'))
OUT = os.path.join(BASE, 'outputs', 'fullwave')
CACHE = os.path.join(BASE, 'cache', 'fullwave')
FIGS = os.path.join(OUT, 'figs')
for d in (OUT, CACHE, FIGS):
    os.makedirs(d, exist_ok=True)

N_SLAB = fw.N_SLAB
W_SLAB = fw.W_SLAB
SOL2 = fw.slab_analytic(N_SLAB, fw.N_CLAD, W_SLAB)


# -----------------------------------------------------------------------------
def discrete_reference(dx_um_list=(0.16, 0.12, 0.08, 0.05, 0.03, 0.02),
                       orders=(2, 4, 6, 8), t_abs_um=12.0):
    """n_eff and cladding decay gamma of the discrete eigenmode of the scheme."""
    rows = []
    for order in orders:
        for dx_um in dx_um_list:
            dx = dx_um * 1e-6
            g = fw.Grid(((-40e-6, 40e-6), (-25e-6, 25e-6)), t_abs=t_abs_um * 1e-6,
                        dx=dx, order=order, n_core=N_SLAB)
            g.build_index([])
            Y = g.axes[1]
            nprof = np.where(np.abs(Y) <= W_SLAB / 2, N_SLAB, fw.N_CLAD)
            s, phi = fw.discrete_mode_1d((Y,), nprof, dx, order, g.omega_eff)
            beta = fw.beta_from_stencil_eig(s, dx, order)
            # discrete cladding decay from the exact discrete dispersion relation
            A = -fw.lam_fd2(beta * dx, order)
            tmp = A - (g.omega_eff * dx / fw.C0) ** 2 * fw.N_CLAD ** 2
            gam = 2 * np.arcsinh(np.sqrt(max(tmp, 0.0) / 4)) / dx if tmp > 0 else 0.0
            rows.append(dict(order=order, dx_um=dx_um, neff=beta / fw.K0,
                             err=beta / fw.K0 - SOL2['neff'], gamma_um=gam / 1e6,
                             gamma_err_pct=100 * (gam / SOL2['gamma'] - 1.0)))
    return rows


def richardson(rows, order_key=None, power=2.0):
    """extrapolate n_eff to dx->0 assuming error ~ C dx^power."""
    rows = sorted(rows, key=lambda r: r['dx_um'], reverse=True)
    if len(rows) < 2:
        return None
    (a, b) = rows[-2], rows[-1]
    r = (a['dx_um'] / b['dx_um']) ** power
    return (b['neff'] - a['neff'] / r) / (1.0 - 1.0 / r)


def fdtd_straight(dx_um, order=4, S_factor=0.90, t_abs_um=14.0, A_abs=7.0,
                  label=None, window=40.0, device='cuda'):
    """one straight-guide FDTD run; returns dict of measurements."""
    dx = dx_um * 1e-6
    x0, x1 = -30e-6, 215e-6
    yhalf = W_SLAB / 2 + 10e-6
    phys = ((x0, x1), (-yhalf, yhalf))
    t_abs = t_abs_um * 1e-6
    label = label or f'straight_dx{dx_um:g}_o{order}'
    sim = fw.Sim2D(phys, t_abs, dx, order=order,
                   guides=[dict(p=(0.0, 0.0), angle=0.0, w=W_SLAB, nc=N_SLAB)],
                   n_core=N_SLAB, label=label, device=device, A_abs=A_abs,
                   S_factor=S_factor)
    sim.add_port_x(-12e-6, 0.0, 'in')
    sim.add_port_x(205e-6, 0.0, 'out')
    sim.add_port_x(-18e-6, 0.0, 'srcback')
    sim.add_beta_projector(-8e-6, 200e-6, 0.0, 'proj')
    sim.add_boundary_probes()
    sim.set_source(-24e-6, 0.0)
    t0 = time.time()
    sim.run(window_periods=window, print_every=8000)
    wall = time.time() - t0
    res = sim.analyse_ports()
    P = res['ports']
    om = sim.omega
    P_inc = 0.5 * om * P['in']['beta'] * P['in']['a_plus'] ** 2
    P_refl = 0.5 * om * P['in']['beta'] * P['in']['a_minus'] ** 2
    P_th = 0.5 * om * P['out']['beta'] * P['out']['a_plus'] ** 2
    pr = sim.beta_from_projector()
    # propagation loss from the projection envelope
    prj = sim.projectors['proj']
    c = prj['re'].detach().cpu().numpy() + 1j * prj['im'].detach().cpu().numpy()
    xx = sim.g.axes[0][prj['i0']:prj['i1']]
    env = np.abs(c)
    good = env > 0.02 * env.max()
    coef = np.polyfit(xx[good], np.log(env[good]), 1)
    loss_db_per_200um = -20.0 / np.log(10.0) * coef[0] * 200e-6
    # discrete reference at the same dx/order
    g = sim.g
    nprof = np.where(np.abs(g.axes[1]) <= W_SLAB / 2, N_SLAB, fw.N_CLAD)
    s, phi = fw.discrete_mode_1d((g.axes[1],), nprof, dx, order, g.omega_eff)
    beta_disc = fw.beta_from_stencil_eig(s, dx, order)
    bnd = sum(res['boundary'].values())
    P_in_net = P['in']['P_flux']
    P_srcback = -P['srcback']['P_flux']
    out = dict(label=label, kind='fdtd', dx_um=dx_um, order=order,
               S=float(sim.g.S), t_abs_um=t_abs_um, A_abs=A_abs,
               n_eff_fdtd=pr['neff'], beta_per_um=pr['beta'] / 1e6,
               n_eff_discrete=beta_disc / fw.K0, n_eff_analytic=SOL2['neff'],
               n_eff_err=pr['neff'] - SOL2['neff'],
               n_eff_err_vs_discrete=pr['neff'] - beta_disc / fw.K0,
               phase_resid_std=pr['phase_resid_std'],
               loss_db_per_200um=float(loss_db_per_200um),
               a_minus_ratio_db=float(20 * np.log10(max(P['in']['a_minus']
                                                         / P['in']['a_plus'], 1e-30))),
               through_a_minus_db=float(20 * np.log10(max(P['out']['a_minus']
                                                          / P['out']['a_plus'], 1e-30))),
               T_through=float(P_th / P_inc),
               T_through_flux=float(P['out']['P_flux'] / P_inc),
               T_reflection=float(P_refl / P_inc),
               reflection_db=float(20 * np.log10(max(P['in']['a_minus']
                                                     / P['in']['a_plus'], 1e-30))),
               flux_vs_modal=float(P['out']['P_flux'] / P_th),
               P_in_net=float(P_in_net), P_srcback=float(P_srcback),
               P_boundary=float(bnd),
               energy_residual=float((bnd - P_in_net - P_srcback) / P_in_net),
               wall_s=float(wall), cells=int(np.prod(sim.g.N)),
               steps=int(sim.n_tot), dt=float(sim.dt),
               steps_per_period=float((2 * np.pi / fw.OMEGA0) / sim.dt))
    return out


def numpy_vs_torch():
    """cross-check the torch steer with a float64 numpy implementation."""
    import torch
    g = fw.Grid(((-30e-6, 30e-6), (-15e-6, 15e-6)), t_abs=8e-6, dx=0.1e-6,
                order=4, n_core=N_SLAB)
    g.build_index([dict(p=(0.0, 0.0), angle=0.0, w=W_SLAB, nc=N_SLAB)])
    g.build_sigma()
    st = fw.Stepper(g, device='cuda')
    rng = np.random.default_rng(7)
    a0 = np.zeros(g.N); b0 = np.zeros(g.N)
    sl = tuple(slice(g.pad, -g.pad) for _ in range(2))
    a0[sl] = rng.standard_normal((g.N[0] - 2 * g.pad, g.N[1] - 2 * g.pad)) * 1e-3
    st.psi_a.copy_(torch.as_tensor(a0, device=st.device, dtype=st.dtype))
    st.psi_b.copy_(torch.as_tensor(b0, device=st.device, dtype=st.dtype))
    a, b = a0, b0
    for _ in range(30):
        c = st.np_step(a, b)
        a, b = b, c
    for _ in range(30):
        st.step()
    ct = st.psi_a.detach().cpu().numpy()
    return float(np.abs(ct - b).max() / max(np.abs(b).max(), 1e-30))


def write_csv(path, rows, cols=None):
    if not rows:
        return
    if cols is None:
        cols = list(rows[0].keys())
    with open(path, 'w', encoding='utf-8') as f:
        f.write(','.join(cols) + '\n')
        for r in rows:
            vals = []
            for c in cols:
                v = r.get(c, '')
                if isinstance(v, float):
                    vals.append('%.10g' % v)
                else:
                    vals.append(str(v))
            f.write(','.join(vals) + '\n')
    print('  wrote', path, '(%d rows)' % len(rows))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--quick', action='store_true')
    ap.add_argument('--skip-fdtd', action='store_true')
    ap.add_argument('--cases', type=str, default='main')
    args = ap.parse_args()
    print('=== 2-D validation ===')
    # ---- 0. numpy vs torch stepper -----------------------------------------
    nd = numpy_vs_torch()
    print('  NumPy(float64) vs torch(float32) 30-step relative field difference: %.2e' % nd)
    json.dump(dict(np_vs_torch_rel_diff=nd),
              open(os.path.join(CACHE, 'validation_np_torch.json'), 'w'), indent=1)
    # ---- 1. discrete eigenmode convergence (cheap, CPU) --------------------
    dxs = (0.12, 0.08, 0.05, 0.03, 0.02) if not args.quick else (0.12, 0.08, 0.05)
    rows_disc = discrete_reference(dx_um_list=dxs)
    conv_rows = []
    for order in sorted(set(r['order'] for r in rows_disc)):
        sub = [r for r in rows_disc if r['order'] == order]
        ext = richardson(sub, power=2.0)
        for r in sub:
            rr = dict(kind='discrete_mode', **r, neff_extrap=ext,
                      extrap_err=(ext - SOL2['neff']) if ext is not None else None)
            conv_rows.append(rr)
        print('  order %d: n_eff(dx=0.02)=%.7f  Richardson(dx^2) extrap=%.7f '
              '(analytic %.7f, err %.1e)'
              % (order, [r['neff'] for r in sub if r['dx_um'] == 0.02][0],
                 ext, SOL2['neff'], ext - SOL2['neff']))
    write_csv(os.path.join(OUT, 'fdtd2d_convergence.csv'), conv_rows)
    # ---- 2. FDTD straight-guide runs ---------------------------------------
    if args.skip_fdtd:
        return
    fdtd_rows = []
    if args.cases == 'main':
        run_list = [(0.08, 4, 0.90, 14.0, 7.0),
                    (0.05, 4, 0.90, 14.0, 7.0),
                    (0.03, 4, 0.90, 14.0, 7.0),
                    (0.02, 4, 0.90, 14.0, 7.0),
                    (0.05, 2, 0.90, 14.0, 7.0),
                    (0.05, 6, 0.90, 14.0, 7.0),
                    (0.05, 4, 0.60, 14.0, 7.0),
                    (0.05, 4, 0.75, 14.0, 7.0),
                    (0.05, 4, 0.90, 10.0, 7.0),
                    (0.05, 4, 0.90, 20.0, 7.0),
                    (0.05, 4, 0.90, 14.0, 5.0),
                    (0.05, 4, 0.90, 14.0, 9.0)]
    else:
        run_list = []
        for tok in args.cases.split(';'):
            v = [float(x) for x in tok.split(',')]
            run_list.append((v[0], int(v[1]), v[2], v[3], v[4]))
    for (dx_um, order, S, tabs, A) in run_list:
        r = fdtd_straight(dx_um, order=int(order), S_factor=S, t_abs_um=tabs,
                          A_abs=A)
        fdtd_rows.append(r)
        print('  dx=%.2f o=%d S=%.2f tabs=%.0f A=%.0f: n_eff=%.7f (disc %.7f, '
              'analytic %.7f) err=%+.2e  T=%.5f  a-/a+=%.1f dB loss=%.3f dB/200um  '
              'flux/modal=%.5f  resid=%.1e  %.0fs'
              % (r['dx_um'], r['order'], r['S'], r['t_abs_um'], r['A_abs'],
                 r['n_eff_fdtd'], r['n_eff_discrete'], r['n_eff_analytic'],
                 r['n_eff_err'], r['T_through'], r['a_minus_ratio_db'],
                 r['loss_db_per_200um'], r['flux_vs_modal'], r['energy_residual'],
                 r['wall_s']), flush=True)
    # Richardson extrapolation of the FDTD n_eff over dx (order 4 runs)
    o4 = sorted([r for r in fdtd_rows if r['order'] == 4 and r['t_abs_um'] == 14.0
                 and r['S'] == 0.90 and r['A_abs'] == 7.0],
                key=lambda r: r['dx_um'], reverse=True)
    ext = richardson([dict(dx_um=r['dx_um'], neff=r['n_eff_fdtd']) for r in o4], power=2.0)
    for r in fdtd_rows:
        r['fdtd_neff_extrap_dx2'] = ext
    write_csv(os.path.join(OUT, 'fdtd2d_validation.csv'), fdtd_rows)
    # absorber table
    ab = [r for r in fdtd_rows if r['order'] == 4 and abs(r['dx_um'] - 0.05) < 1e-9
          and r['S'] == 0.90 and r['A_abs'] == 7.0]
    write_csv(os.path.join(OUT, 'absorber_reflection.csv'),
              [dict(t_abs_um=r['t_abs_um'], A_abs=r['A_abs'],
                    through_port_reflection_db=r['through_a_minus_db'],
                    input_port_reflection_db=r['a_minus_ratio_db'],
                    T_reflection=r['T_reflection']) for r in ab])
    print('  FDTD Richardson extrapolated n_eff (dx^2):', ext)
    json.dump(dict(fdtd=fdtd_rows, discrete=rows_disc, np_vs_torch=nd),
              open(os.path.join(CACHE, 'validation_2d.json'), 'w'), indent=1,
              default=float)
    print('DONE')


if __name__ == '__main__':
    main()
