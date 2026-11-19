"""Parallel coupler with properly orthogonalised two-guide port analysis.

For d=12 um the two isolated modes overlap with S = <phi1|phi2> ~ a few percent.
The naive projection b_i = <phi_i|psi> then mixes the guides: b1 = a1 + S a2,
b2 = S a1 + a2.  We solve this 2x2 system for (a1,a2) at the output plane.

Run: python run_2d_coupler2.py --d 12 --L 280
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
N_SLAB = fw.N_SLAB
W_SLAB = fw.W_SLAB


def build(d_um, L_um=280.0, dx_um=0.05, order=4, t_abs_um=14.0, label=None,
          device='cuda'):
    d = d_um * 1e-6
    L = L_um * 1e-6
    yh = d / 2 + W_SLAB / 2 + 6e-6
    phys = ((-L / 2 - 22e-6, L / 2 + 8e-6), (-yh, yh))
    guides = [dict(p=(0.0, -d / 2), angle=0.0, w=W_SLAB, nc=N_SLAB),
              dict(p=(0.0, +d / 2), angle=0.0, w=W_SLAB, nc=N_SLAB)]
    label = label or f'cpl2_d{d_um:g}_L{L_um:g}'
    sim = fw.Sim2D(phys, t_abs_um * 1e-6, dx_um * 1e-6, order=order,
                   guides=guides, n_core=N_SLAB, label=label, device=device)
    sim.add_port_x(-L / 2, -d / 2, 'in')
    sim.add_port_x(+L / 2, -d / 2, 'out1')
    sim.add_port_x(+L / 2, +d / 2, 'out2')
    sim.add_boundary_probes()
    sim.set_source(-L / 2 - 8e-6, -d / 2)
    return sim, dict(case='coupler2', d_um=d_um, L_um=L_um, dx_um=dx_um,
                     order=order, t_abs_um=t_abs_um,
                     phys_um=[[a * 1e6, b * 1e6] for a, b in phys],
                     N=list(sim.g.N), cells=int(np.prod(sim.g.N)), dt=sim.dt,
                     S=sim.g.S, label=label)


def analyse(sim, meta, wall):
    om = sim.omega
    N = sim.window_values
    dx = sim.dx
    # guide modes / overlap S
    _, phi1, beta1, bd1, _ = sim.guide_profile_1d(-meta['d_um'] * 1e-6 / 2, W_SLAB)
    _, phi2, beta2, bd2, _ = sim.guide_profile_1d(+meta['d_um'] * 1e-6 / 2, W_SLAB)
    S = float(dx * np.sum(phi1 * phi2))
    ports = [p for p in sim.ports]
    # input amplitude (guide 1 only)
    box_in = [p for p in ports if p['name'] == 'in'][0]
    C = box_in['box'].get()
    il = box_in['ix'] - box_in['box'].sl[0].start
    Din = sim._box_deriv_x(C, il, box_in['box'])
    b_in = 0.5 * (dx * np.sum(box_in['phi'] * C[il])
                  + (dx * np.sum(box_in['phi'] * Din)) / (1j * box_in['beta_d']))
    a_inc = 4.0 * abs(b_in) / N
    P_inc = 0.5 * om * box_in['beta'] * a_inc ** 2
    # output amplitudes with orthogonalisation
    def proj(name, phi):
        p = [q for q in ports if q['name'] == name][0]
        Ca = p['box'].get()
        ila = p['ix'] - p['box'].sl[0].start
        D = sim._box_deriv_x(Ca, ila, p['box'])
        b = 0.5 * (dx * np.sum(phi * Ca[ila])
                   + (dx * np.sum(phi * D)) / (1j * p['beta_d']))
        return b
    b1 = proj('out1', phi1)
    b2 = proj('out2', phi2)
    a1 = (b1 - S * b2) / (1 - S ** 2)
    a2 = (b2 - S * b1) / (1 - S ** 2)
    P1 = 0.5 * om * beta1 * abs(a1) ** 2
    P2 = 0.5 * om * beta2 * abs(a2) ** 2
    # naive (non-orthogonalised) values for comparison
    P1n = 0.5 * om * beta1 * abs(b1) ** 2
    P2n = 0.5 * om * beta2 * abs(b2) ** 2
    L = meta['L_um'] * 1e-6
    T_bar = P1 / P_inc
    T_cross = P2 / P_inc
    kappa = float(np.arcsin(np.sqrt(min(max(T_cross, 0.0), 1.0))) / L)
    res = sim.analyse_ports()
    bnd = res['boundary']
    P_in_net = res['ports']['in']['P_flux']
    P_boundary = sum(bnd.values())
    resid = (P_boundary - bnd.get('bnd_L', 0.0) - P_in_net) / P_in_net
    out = dict(label=meta.get('label', ''), wall_s=float(wall), meta=meta,
               S_overlap=S, T_bar=float(T_bar), T_cross=float(T_cross),
               crosstalk_db=float(10 * np.log10(max(T_cross, 1e-30))),
               bar_db=float(10 * np.log10(max(T_bar, 1e-30))),
               T_cross_naive=float(P2n / P_inc),
               T_bar_naive=float(P1n / P_inc),
               kappa_fdtd_mm_inv=float(kappa * 1e-3), kappa_L=float(kappa * L),
               T_reflection=float(res['ports']['in']['P_minus']
                                  / (0.5 * om * box_in['beta'] * a_inc ** 2)),
               energy_residual=float(resid),
               P_inc=float(P_inc), P_in_net=float(P_in_net),
               P_boundary=float(P_boundary), boundary={k: float(v) for k, v in bnd.items()},
               n_tot=int(sim.n_tot))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--d', type=float, default=12.0)
    ap.add_argument('--L', type=float, default=280.0)
    ap.add_argument('--dx', type=float, default=0.05)
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--window', type=float, default=40.0)
    args = ap.parse_args()
    label = f'cpl2_d{args.d:g}_L{args.L:g}_dx{args.dx:g}'
    fn = os.path.join(CACHE, f'coupler2_{label}.json')
    if os.path.exists(fn) and not args.force:
        print('exists', fn)
        return
    print('=== coupler2 d=%g L=%g ===' % (args.d, args.L))
    sim, meta = build(args.d, args.L, dx_um=args.dx, label=label)
    t0 = time.time()
    sim.run(window_periods=args.window, print_every=10000)
    out = analyse(sim, meta, time.time() - t0)
    json.dump(out, open(fn, 'w'), indent=1, default=float)
    print('  S=%.4e  T_bar=%.5f  T_cross=%.4e (%.2f dB)  kappa=%.4e 1/mm '
          '(naive T_cross=%.3e)  resid=%.1e  wall=%.0fs'
          % (out['S_overlap'], out['T_bar'], out['T_cross'],
             out['crosstalk_db'], out['kappa_fdtd_mm_inv'],
             out['T_cross_naive'], out['energy_residual'], out['wall_s']))


if __name__ == '__main__':
    main()
