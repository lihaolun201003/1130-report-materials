"""Validation/calibration run: a single straight TILTED waveguide.

Purpose
  * validates the oblique port (forward/backward decomposition) machinery;
  * measures the propagation constant beta(theta, dx, order) of the anti-aliased
    tilted guide -- needed to analyse the crossing cross arms correctly;
  * measures the numerical floor (|a-|/|a+|) of the oblique port;
  * gives the radiation loss of a tilted guide on a cartesian grid.

Run:  python run_2d_tilted.py --theta 30 --dx 0.05
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
CACHE = os.path.join(BASE, 'cache', 'fullwave')
OUT = os.path.join(BASE, 'outputs', 'fullwave')
for d in (CACHE, OUT):
    os.makedirs(d, exist_ok=True)

W_SLAB = fw.W_SLAB


def build(theta_deg, dx_um, order=4, t_abs_um=14.0, L_um=110.0, phw_um=12.0,
          du_um=5.0, n_line=3, label='tilt', device='cuda'):
    theta = np.deg2rad(theta_deg)
    dx = dx_um * 1e-6
    L = L_um * 1e-6
    phw = phw_um * 1e-6
    du = du_um * 1e-6
    uc = L / 2                    # port distance along the arm from the centre
    umax = uc + (n_line - 1) * du
    ex = umax * abs(np.cos(theta)) + phw * abs(np.sin(theta)) + 5e-6
    ey = umax * abs(np.sin(theta)) + phw * abs(np.cos(theta)) + 5e-6
    phys = ((-ex, ex), (-ey, ey))
    t_abs = t_abs_um * 1e-6
    sim = fw.Sim2D(phys, t_abs, dx, order=order,
                   guides=[dict(p=(0.0, 0.0), angle=theta, w=W_SLAB, nc=fw.N_SLAB)],
                   n_core=fw.N_SLAB, label=label, device=device)
    # ports: 'out' in +u direction, 'in' in -u direction (theta+pi)
    sim.add_oblique_arm((0.0, 0.0), theta,
                        [uc + k * du for k in range(n_line)], 'out', halfwidth=phw)
    sim.add_oblique_arm((0.0, 0.0), theta + np.pi,
                        [uc + k * du for k in range(n_line)], 'in', halfwidth=phw)
    sim.add_boundary_probes()
    # source at u = -(uc-8um), i.e. 8um in front of the input port lines
    sim.set_source_oblique((0.0, 0.0), theta, -(uc - 8e-6))
    meta = dict(theta_deg=theta_deg, theta=theta, dx_um=dx_um, order=order,
                t_abs_um=t_abs_um, L_um=L_um, uc_um=uc * 1e6,
                phys_um=[[a * 1e6, b * 1e6] for a, b in phys],
                N=list(sim.g.N), cells=int(np.prod(sim.g.N)),
                dt=sim.dt, S=sim.g.S)
    return sim, meta


def analyse(sim, meta, wall):
    om = sim.omega
    arm_out = sim.analyse_oblique_arm('out')
    arm_in = sim.analyse_oblique_arm('in')
    # incident power from the backward-launched wave seen at the 'in' port lines
    P_inc = max(arm_in['P_plus'][-1], 1e-300)
    P_out = arm_out['P_plus'][-1]
    P_bwd_out = arm_out['P_minus'][-1]
    bnd = sum(v for k, v in sim.analyse_ports()['boundary'].items())
    res = dict(label=meta.get('label', ''), meta=meta, wall_s=float(wall),
               arm_out=arm_out, arm_in=arm_in,
               beta_arm=arm_out['beta'], neff_arm=arm_out['neff'],
               beta_arm_in=arm_in['beta'],
               T_through=float(P_out / P_inc),
               T_out_flux=float(arm_out['flux'][-1] / max(arm_in['flux'][-1], 1e-300)),
               floor_db=float(20 * np.log10(max(arm_out['a_minus'][-1]
                                                 / max(arm_out['a_plus'][-1], 1e-300), 1e-30))),
               floor_plus_db=float(20 * np.log10(max(arm_out['a_plus'][-1]
                                                     / max(arm_in['a_plus'][-1], 1e-300), 1e-30))),
               P_boundary=float(bnd))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--theta', type=float, default=30.0)
    ap.add_argument('--dx', type=float, default=0.05)
    ap.add_argument('--order', type=int, default=4)
    ap.add_argument('--tabs', type=float, default=14.0)
    ap.add_argument('--window', type=float, default=40.0)
    ap.add_argument('--label', type=str, default='')
    ap.add_argument('--device', type=str, default='cuda')
    args = ap.parse_args()
    label = args.label or f'tilt{args.theta:g}_dx{args.dx:g}'
    print(f'=== tilted guide theta={args.theta} dx={args.dx} order={args.order} ===',
          flush=True)
    sim, meta = build(args.theta, args.dx, order=args.order, t_abs_um=args.tabs,
                      label=label, device=args.device)
    print('  cells=%.2f M, dt=%.3e, S=%.3f' % (meta['cells'] / 1e6, meta['dt'],
                                              meta['S']), flush=True)
    t0 = time.time()
    sim.run(window_periods=args.window, print_every=5000)
    res = analyse(sim, meta, time.time() - t0)
    print('  beta_arm = %.6e 1/um  n_eff=%.7f  (beta_arm_in=%.6e)'
          % (res['beta_arm'] / 1e6, res['neff_arm'], res['beta_arm_in'] / 1e6))
    print('  T_through = %.5f   a+_out/a+_in = %.3f dB   |a-|/|a+| floor = %.1f dB'
          % (res['T_through'], res['floor_plus_db'], res['floor_db']))
    print('  wall=%.1f s' % res['wall_s'])
    fn = os.path.join(CACHE, f'tilted_{label}.json')
    json.dump(res, open(fn, 'w'), indent=1, default=float)
    print('  saved', fn)


if __name__ == '__main__':
    main()
