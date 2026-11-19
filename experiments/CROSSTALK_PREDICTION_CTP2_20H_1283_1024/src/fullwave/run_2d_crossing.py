"""2-D scalar FDTD for the in-plane EIM waveguide CROSSING problem.

Geometry (effective-index reduction of the 3-D channel):
  two identical slabs of width 9 um crossing at angle theta, core n=1.5055213,
  cladding n=1.500, lambda=1.31 um.  Guide 1 along x, guide 2 at angle theta
  (area-averaged / anti-aliased index on the tilted guide).
  A mode-shaped soft source launches the fundamental mode into guide 1 only.
  Ports are placed where the two guide centre lines are `sep` apart; beyond that
  separation the residual coupling is < -100 dB (checked by a port-distance run).

Measurements
  * through port : forward/backward modal decomposition (a+/a-)
  * both cross arms : forward/backward modal decomposition on oblique port lines;
    the arm propagation constant is taken from the tilted-guide calibration run
    (run_2d_tilted.py) when --beta-arm is supplied
  * power budget : guided modal powers + Poynting flux through every port line
    and through the closed boundary of the physical region.

Run examples:
  python run_2d_crossing.py --theta 20 --dx 0.05 --sep 40 --label t20_dx05
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


def make_crossing_sim(theta_deg, dx_um, sep_um, order=4, t_abs_um=14.0,
                      port_hw_um=12.0, n_line=3, du_um=5.0,
                      label='cross', device='cuda', t_abs_y_um=None,
                      x_margin=22.0, x_margin_r=30.0, y_margin=8.0,
                      only_guide1=False):
    theta = np.deg2rad(theta_deg)
    dx = dx_um * 1e-6
    sep = sep_um * 1e-6
    Xp = sep / np.sin(theta)
    phw = port_hw_um * 1e-6
    du = du_um * 1e-6
    xleft = Xp + x_margin * 1e-6
    xright = Xp + x_margin_r * 1e-6
    yhalf = sep + n_line * du * np.sin(theta) + phw * abs(np.cos(theta)) + \
        y_margin * 1e-6
    phys = ((-xleft, xright), (-yhalf, yhalf))
    guides = [dict(p=(0.0, 0.0), angle=0.0, w=W_SLAB, nc=N_SLAB)]
    if not only_guide1:
        guides.append(dict(p=(0.0, 0.0), angle=theta, w=W_SLAB, nc=N_SLAB))
    t_abs = t_abs_um * 1e-6
    sim = fw.Sim2D(phys, t_abs, dx, order=order, guides=guides,
                   n_core=N_SLAB, label=label, device=device)
    # --- ports --------------------------------------------------------------
    sim.add_port_x(-Xp, 0.0, 'in')
    sim.add_port_x(+Xp, 0.0, 'through')
    sim.add_port_x(-(Xp + 13e-6), 0.0, 'srcback')
    us = [sep / np.sin(theta) + k * du for k in range(n_line)]
    # note: distance along the arm for a transverse separation sep is sep/sin(theta)
    sim.add_oblique_arm((0.0, 0.0), theta, us, 'cross_p', halfwidth=phw)
    sim.add_oblique_arm((0.0, 0.0), theta + np.pi, us, 'cross_m', halfwidth=phw)
    sim.add_boundary_probes()
    # --- source -------------------------------------------------------------
    sim.set_source(-(Xp + 8e-6), 0.0)
    meta = dict(theta_deg=theta_deg, theta=theta, dx_um=dx_um, order=order,
                sep_um=sep_um, t_abs_um=t_abs_um, Xp_um=Xp * 1e6,
                phys_um=[[a * 1e6, b * 1e6] for a, b in phys],
                N=list(sim.g.N), cells=int(np.prod(sim.g.N)),
                dt=sim.dt, S=sim.g.S, S_max=sim.g.S_max,
                port_hw_um=port_hw_um, du_um=du_um, n_line=n_line)
    return sim, meta


def analyse_crossing(sim, meta, t_wall):
    res_ports = sim.analyse_ports()
    om = sim.omega
    P = res_ports['ports']
    b_in = P['in']['beta']
    P_inc = 0.5 * om * b_in * P['in']['a_plus'] ** 2
    P_refl = 0.5 * om * b_in * P['in']['a_minus'] ** 2
    r_amp = P['in']['a_minus'] / P['in']['a_plus']
    P_in_net = P['in']['P_flux']
    a_th = P['through']['a_plus']
    P_th_modal = 0.5 * om * P['through']['beta'] * a_th ** 2
    P_th_flux = P['through']['P_flux']
    arm_p = sim.analyse_oblique_arm('cross_p')
    arm_m = sim.analyse_oblique_arm('cross_m')
    P_xp = arm_p['P_plus'][-1]
    P_xm = arm_m['P_plus'][-1]
    P_xp_flux = arm_p['flux'][-1]
    P_xm_flux = arm_m['flux'][-1]
    P_bwd_x = arm_p['P_minus'][-1] + arm_m['P_minus'][-1]
    P_boundary = sum(res_ports['boundary'].values())
    P_srcback = -P['srcback']['P_flux']
    # --- crosstalk / budget --------------------------------------------------
    T_th = P_th_modal / P_inc
    T_th_flux = P_th_flux / P_inc
    T_x = (P_xp + P_xm) / P_inc
    T_x_flux = (P_xp_flux + P_xm_flux) / P_inc
    T_refl = P_refl / P_inc
    # Radiation = injected power that is neither guided through nor guided cross.
    # (Flux-based bookkeeping cannot separate radiation that happens to cross a
    # port plane, so the guided modal powers are used for the radiation budget.)
    T_in = P_in_net / P_inc
    T_rad = (T_in - T_th - T_x)
    resid = (P_boundary - P_in_net - P_srcback) / P_in_net
    # cross-arm power consistency (guided power constant along the arm)
    xp_rel_var = float(np.std(arm_p['P_plus']) / np.mean(arm_p['P_plus']))
    out = dict(label=meta.get('label', ''), wall_s=float(t_wall),
               meta=meta, ports=P, flux_ports=res_ports['flux_ports'],
               boundary=res_ports['boundary'],
               arm_p={k: arm_p[k] for k in ('a_plus', 'a_minus', 'P_plus', 'P_minus',
                                            'flux', 'beta', 'neff', 'phase_resid', 'u',
                                            'sep')},
               arm_m={k: arm_m[k] for k in ('a_plus', 'a_minus', 'P_plus', 'P_minus',
                                            'flux', 'beta', 'neff', 'phase_resid', 'u',
                                            'sep')},
               P_inc=P_inc, P_in_net=P_in_net, P_th_modal=P_th_modal,
               P_th_flux=P_th_flux, P_cross=P_xp + P_xm,
               P_cross_flux=P_xp_flux + P_xm_flux,
               P_boundary=P_boundary, P_srcback=P_srcback,
               T_through=float(T_th), T_through_flux=float(T_th_flux),
               T_cross=float(T_x), T_cross_flux=float(T_x_flux),
               T_cross_p=float(P_xp / P_inc), T_cross_m=float(P_xm / P_inc),
               T_reflection=float(T_refl), T_radiation=float(T_rad),
               T_backward_cross=float(P_bwd_x / P_inc),
               crosstalk_db=float(10 * np.log10(max(T_x, 1e-30))),
               corsstalk_flux_db=float(10 * np.log10(max(T_x_flux, 1e-30))),
               through_db=float(10 * np.log10(max(T_th, 1e-30))),
               reflection_db=float(20 * np.log10(max(r_amp, 1e-30))),
               energy_residual=float(resid),
               arm_plus_relvar=xp_rel_var,
               r_amp=float(r_amp))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--theta', type=float, default=20.0)
    ap.add_argument('--dx', type=float, default=0.05)
    ap.add_argument('--sep', type=float, default=40.0)
    ap.add_argument('--order', type=int, default=4)
    ap.add_argument('--tabs', type=float, default=14.0)
    ap.add_argument('--label', type=str, default='')
    ap.add_argument('--window', type=float, default=60.0)
    ap.add_argument('--beta-arm', type=float, default=None,
                    help='arm beta from the tilted-guide calibration (1/um)')
    ap.add_argument('--snapshot', action='store_true')
    ap.add_argument('--device', type=str, default='cuda')
    args = ap.parse_args()
    label = args.label or f'theta{args.theta:g}_dx{args.dx:g}_sep{args.sep:g}'
    print(f'=== crossing theta={args.theta} deg dx={args.dx} um sep={args.sep} um '
          f'order={args.order} ===', flush=True)
    sim, meta = make_crossing_sim(args.theta, args.dx, args.sep, order=args.order,
                                  t_abs_um=args.tabs, label=label,
                                  device=args.device)
    if args.beta_arm is not None:
        for nm in ('cross_p', 'cross_m'):
            sim.oblique_arms[nm]['beta_override'] = args.beta_arm * 1e6
    print('  cells=%d (%.1f M), dt=%.4e s, S=%.3f'
          % (meta['cells'], meta['cells'] / 1e6, meta['dt'], meta['S']), flush=True)
    t0 = time.time()
    snap_steps = ()
    if args.snapshot:
        # snapshot shortly after the DFT window has started
        snap_steps = ()
    sim.run(window_periods=args.window, print_every=4000,
            snapshot_steps=snap_steps)
    if args.snapshot:
        psi = sim.st.psi_a.detach().cpu().numpy()
        step = max(1, int(np.ceil(sim.dx / 0.15e-6)))
        np.savez(os.path.join(CACHE, f'snap_{label}.npz'),
                 psi=psi[::step, ::step], x=sim.g.axes[0][::step],
                 y=sim.g.axes[1][::step])
    out = analyse_crossing(sim, meta, time.time() - t0)
    print('  T_through = %.5f (%.2f dB)   T_cross = %.4e (%.2f dB)'
          % (out['T_through'], out['through_db'], out['T_cross'], out['crosstalk_db']))
    print('  T_cross(+u)=%.3e  T_cross(-u)=%.3e  T_back_x=%.2e  T_refl=%.3e (%.1f dB)'
          % (out['T_cross_p'], out['T_cross_m'], out['T_backward_cross'],
             out['T_reflection'], out['reflection_db']))
    print('  T_rad = %.4e   energy: P_in_net=%.4e P_boundary=%.4e P_srcback=%.4e '
          'residual=%.2e' % (out['T_radiation'], out['P_in_net'], out['P_boundary'],
                             out['P_srcback'], out['energy_residual']))
    print('  arm beta = %.6f 1/um  (n_eff=%.7f)  rel var of P_plus=%.2e'
          % (out['arm_p']['beta'] / 1e6, out['arm_p']['neff'], out['arm_plus_relvar']))
    print('  wall = %.1f s' % out['wall_s'])
    fn = os.path.join(CACHE, f'cross_{label}.json')
    json.dump(out, open(fn, 'w'), indent=1, default=float)
    print('  saved', fn)
    return out


if __name__ == '__main__':
    main()
