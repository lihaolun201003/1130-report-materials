"""Deliverable-2: 3-D scalar FDTD spot checks.

Cases
  straight : 3-D straight channel -> n_eff from the propagation phase (compared
             with the discrete-mode prediction, the Richardson-extrapolated
             discrete value and the lead-supplied converged value 1.50455547)
  cross90  : 90-degree crossing -> T_through / T_cross (EIM comparison)
  coupler  : parallel channels d=15 um in-plane, vertical offsets dz=10, 20 um
             -> small-signal crosstalk bound / measurement vs CMT

Run:  python run_3d.py --case straight
      python run_3d.py --case cross90
      python run_3d.py --case coupler
"""
import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fwlib as fw
import fwlib3d as f3

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(HERE, '..', '..'))
CACHE = os.path.join(BASE, 'cache', 'fullwave')
OUT = os.path.join(BASE, 'outputs', 'fullwave')
for d in (CACHE, OUT):
    os.makedirs(d, exist_ok=True)

N_CORE = fw.N_CORE
W = fw.W_CORE
NEFF_TARGET = 1.50455547
NEFF_EIM = fw.NEFF2D_TARGET


def energy_budget(sim, res, name=''):
    P = res['ports']
    bnd = res['boundary']
    om = sim.omega
    b_in = P['in']['beta']
    P_inc = 0.5 * om * b_in * P['in']['a_plus'] ** 2
    P_refl = 0.5 * om * b_in * P['in']['a_minus'] ** 2
    P_in_net = P['in']['P_flux']
    out = dict(P_inc=P_inc, P_refl=P_refl, P_in_net=P_in_net,
               r_amp=P['in']['a_minus'] / max(P['in']['a_plus'], 1e-300),
               T_reflection=P_refl / P_inc)
    if 'srcback' in P:
        out['P_srcback'] = -P['srcback']['P_flux']
    if 'through' in P:
        out['T_through'] = 0.5 * om * P['through']['beta'] * P['through']['a_plus'] ** 2 / P_inc
        out['P_th_flux'] = P['through']['P_flux']
    if 'cross_p' in P:
        out['P_cross'] = (0.5 * om * P['cross_p']['beta'] * P['cross_p']['a_plus'] ** 2
                          + 0.5 * om * P['cross_m']['beta'] * P['cross_m']['a_plus'] ** 2)
        out['P_cross_flux'] = P['cross_p']['P_flux'] - P['cross_m']['P_flux']
        out['T_cross'] = out['P_cross'] / P_inc
    if 'out1' in P:
        out['P_out1'] = 0.5 * om * P['out1']['beta'] * P['out1']['a_plus'] ** 2
        out['P_out2'] = 0.5 * om * P['out2']['beta'] * P['out2']['a_plus'] ** 2
        out['T_bar'] = out['P_out1'] / P_inc
        out['T_cross'] = out['P_out2'] / P_inc
    P_boundary = sum(bnd.values())
    out['P_boundary'] = P_boundary
    # the source emits backwards as well; that power leaves through the left
    # boundary (bnd_L).  The energy-balance check is therefore
    #   (everything except bnd_L) == P_in_net
    bnd_L = bnd.get('bnd_L', 0.0)
    out['P_back_emitted_boundary'] = bnd_L
    out['energy_residual'] = (P_boundary - bnd_L - P_in_net) / P_in_net
    # radiation from the guide-flux budget (what is not in the port fluxes)
    port_flux_sum = P_in_net
    if 'through' in P:
        port_flux_sum = 0.0
        port_flux_sum = out.get('P_th_flux', 0.0)
        if 'P_cross_flux' in out:
            port_flux_sum += out['P_cross_flux']
        out['T_radiation'] = (P_in_net - port_flux_sum) / P_inc
    return out


def build_straight(dx=0.12, order=6, t_abs_um=8.0, label='s3d'):
    phys = ((-35e-6, 55e-6), (-9.5e-6, 9.5e-6), (-9.5e-6, 9.5e-6))
    sim = f3.Sim3D(phys, t_abs_um * 1e-6, dx * 1e-6, order=order,
                   guides=[dict(p=(0.0, 0.0, 0.0), angle=0.0, w=W, h=W, nc=N_CORE)],
                   n_core=N_CORE, label=label)
    sim.add_port_x(-25e-6, 0.0, 0.0, 'in')
    sim.add_port_x(45e-6, 0.0, 0.0, 'through')
    sim.add_port_x(-30e-6, 0.0, 0.0, 'srcback')
    sim.add_beta_projector(-18e-6, 40e-6, 0.0, 0.0, 'proj')
    sim.add_boundary_probes()
    sim.set_source(-32e-6, 0.0, 0.0)
    return sim, dict(case='straight', dx_um=dx, order=order, t_abs_um=t_abs_um)


def build_cross90(dx=0.12, order=6, t_abs_um=7.0, sep_um=20.0,
                  phys_half=25e-6, label='x90'):
    sep = sep_um * 1e-6
    phys = ((-phys_half, phys_half), (-phys_half, phys_half),
            (-9.5e-6, 9.5e-6))
    guides = [dict(p=(0.0, 0.0, 0.0), angle=0.0, w=W, h=W, nc=N_CORE),
              dict(p=(0.0, 0.0, 0.0), angle=np.pi / 2, w=W, h=W, nc=N_CORE)]
    sim = f3.Sim3D(phys, t_abs_um * 1e-6, dx * 1e-6, order=order, guides=guides,
                   n_core=N_CORE, label=label)
    sim.add_port_x(-sep, 0.0, 0.0, 'in')
    sim.add_port_x(sep, 0.0, 0.0, 'through')
    sim.add_port_y(+sep, 0.0, 0.0, 'cross_p')
    sim.add_port_y(-sep, 0.0, 0.0, 'cross_m')
    sim.add_port_x(-(sep + 4e-6), 0.0, 0.0, 'srcback')
    sim.add_boundary_probes()
    sim.set_source(-(sep + 5e-6), 0.0, 0.0)
    return sim, dict(case='cross90', dx_um=dx, order=order, t_abs_um=t_abs_um,
                     sep_um=sep_um)


def build_coupler(dx=0.12, order=6, t_abs_um=7.0, d_um=15.0, dz_um=0.0,
                  length_um=30.0, label='c3d'):
    d = d_um * 1e-6
    dz = dz_um * 1e-6
    yh = max(9.5e-6, d + 4.5e-6 + 5e-6)
    zh = max(9.5e-6, abs(dz) + 4.5e-6 + 5e-6)
    xh = length_um * 1e-6
    phys = ((-xh, xh), (-yh, yh), (-zh, zh))
    guides = [dict(p=(0.0, 0.0, 0.0), angle=0.0, w=W, h=W, nc=N_CORE),
              dict(p=(0.0, d, dz), angle=0.0, w=W, h=W, nc=N_CORE)]
    sim = f3.Sim3D(phys, t_abs_um * 1e-6, dx * 1e-6, order=order, guides=guides,
                   n_core=N_CORE, label=label)
    sim.add_port_x(-xh + 5e-6, 0.0, 0.0, 'in')
    sim.add_port_x(xh - 5e-6, 0.0, 0.0, 'out1')
    sim.add_port_x(xh - 5e-6, d, dz, 'out2')
    sim.add_port_x(-xh + 1e-6, 0.0, 0.0, 'srcback')
    sim.add_boundary_probes()
    sim.set_source(-xh + 2e-6, 0.0, 0.0)
    return sim, dict(case='coupler', dx_um=dx, order=order, t_abs_um=t_abs_um,
                     d_um=d_um, dz_um=dz_um, length_um=length_um)


def run_case(build_fn, tag, force=False, window=50.0):
    fn = os.path.join(CACHE, f'3d_{tag}.json')
    if os.path.exists(fn) and not force:
        return json.load(open(fn))
    sim, meta = build_fn()
    print('  [%s] cells=%.1fM N=%s dt=%.3e S=%.3f'
          % (tag, np.prod(sim.N) / 1e6, sim.N, sim.dt, sim.g.S), flush=True)
    t0 = time.time()
    sim.run(window_periods=window, print_every=3000)
    res = sim.analyse()
    out = energy_budget(sim, res)
    out['meta'] = dict(meta, **sim.meta)
    out['ports'] = res['ports']
    out['boundary'] = res['boundary']
    out['wall_s'] = float(time.time() - t0)
    if sim.proj is not None:
        pr = sim.beta_from_projector()
        out['beta_meas'] = pr
        out['n_eff_fdtd'] = pr['neff']
        out['n_eff_discrete'] = pr['neff_discrete']
        out['n_eff_err_vs_target'] = pr['neff'] - NEFF_TARGET
        out['n_eff_err_vs_discrete'] = pr['neff'] - pr['neff_discrete']
    # stringify port dict keys for JSON safety
    out['ports'] = {k: {kk: float(vv) for kk, vv in v.items()}
                    for k, v in res['ports'].items()}
    out['boundary'] = {k: float(v) for k, v in res['boundary'].items()}
    json.dump(out, open(fn, 'w'), indent=1, default=float)
    print('  [%s] wall=%.0fs' % (tag, out['wall_s']), flush=True)
    if 'T_through' in out:
        print('  [%s] T_through=%.5f  T_cross=%.4e  T_refl=%.2e  resid=%.2e'
              % (tag, out['T_through'], out.get('T_cross', 0.0),
                 out['T_reflection'], out['energy_residual']), flush=True)
    if 'n_eff_fdtd' in out:
        print('  [%s] n_eff FDTD=%.8f  discrete(%.2f um)=%.8f  target=%.8f'
              % (tag, out['n_eff_fdtd'], meta['dx_um'], out['n_eff_discrete'],
                 NEFF_TARGET), flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', type=str, default='straight')
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--window', type=float, default=50.0)
    args = ap.parse_args()
    if args.case == 'straight':
        run_case(lambda: build_straight(), 'straight_dx0.12_o6',
                 force=args.force, window=args.window)
    elif args.case == 'cross90':
        run_case(lambda: build_cross90(), 'cross90_dx0.12_o6',
                 force=args.force, window=args.window)
    elif args.case == 'coupler':
        for (d_um, dz_um) in [(15.0, 0.0), (0.0, 10.0), (0.0, 20.0)]:
            tag = f'coupler_d{d_um:g}_dz{dz_um:g}_dx0.12_o6'
            run_case(lambda d_um=d_um, dz_um=dz_um: build_coupler(d_um=d_um,
                                                                 dz_um=dz_um),
                     tag, force=args.force, window=args.window)


if __name__ == '__main__':
    main()
