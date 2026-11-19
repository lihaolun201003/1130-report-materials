"""2-D parallel directional coupler (in-plane EIM geometry).

Two identical slabs (w=9 um, n=1.5055213) side by side, centre separation d,
coupling length L (input port -> output ports).  A mode-shaped source launches
the fundamental mode into guide 1 only.  At the output plane the guided
amplitudes of both guides are measured by modal projection.

Because the weak guidance (dn=0.00552) makes kappa tiny, the full beat length
L_beat = pi/(2 kappa) is 4 mm (d=12) to 20 mm (d=15) -- far beyond any affordable
FDTD domain.  We therefore measure the small-signal crosstalk T_cross = sin^2(kappa L)
~ (kappa L)^2 and extract kappa = asin(sqrt(T_cross))/L.  The (kappa L)^2 scaling
is verified by running two lengths.

Run:  python run_2d_coupler.py --d 15 --L 280
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

N_SLAB = fw.N_SLAB
W_SLAB = fw.W_SLAB


def build(d_um, L_um=280.0, dx_um=0.05, order=4, t_abs_um=14.0, label=None,
          device='cuda'):
    d = d_um * 1e-6
    L = L_um * 1e-6
    yh = d / 2 + W_SLAB / 2 + 6e-6
    phys = ((-L / 2 - 22e-6, L / 2 + 8e-6), (-yh, yh))
    guides = [dict(p=(0.0, -d / 2), angle=0.0, w=W_SLAB, nc=N_SLAB),
              dict(p=(0.0, d / 2), angle=0.0, w=W_SLAB, nc=N_SLAB)]
    label = label or f'cpl_d{d_um:g}_L{L_um:g}'
    sim = fw.Sim2D(phys, t_abs_um * 1e-6, dx_um * 1e-6, order=order,
                   guides=guides, n_core=N_SLAB, label=label, device=device)
    sim.add_port_x(-L / 2, -d / 2, 'in')
    sim.add_port_x(+L / 2, -d / 2, 'out1')
    sim.add_port_x(+L / 2, +d / 2, 'out2')
    sim.add_port_x(-L / 2 - 8e-6, -d / 2, 'srcback')
    sim.add_boundary_probes()
    sim.set_source(-L / 2 - 8e-6, -d / 2)
    meta = dict(case='coupler', d_um=d_um, L_um=L_um, dx_um=dx_um, order=order,
                t_abs_um=t_abs_um, phys_um=[[a * 1e6, b * 1e6] for a, b in phys],
                N=list(sim.g.N), cells=int(np.prod(sim.g.N)), dt=sim.dt,
                S=sim.g.S)
    return sim, meta


def analyse(sim, meta, wall):
    res = sim.analyse_ports()
    P = res['ports']
    om = sim.omega
    P_inc = 0.5 * om * P['in']['beta'] * P['in']['a_plus'] ** 2
    P_refl = 0.5 * om * P['in']['beta'] * P['in']['a_minus'] ** 2
    P1 = 0.5 * om * P['out1']['beta'] * P['out1']['a_plus'] ** 2
    P2 = 0.5 * om * P['out2']['beta'] * P['out2']['a_plus'] ** 2
    P_in_net = P['in']['P_flux']
    P_boundary = sum(res['boundary'].values())
    P_srcback = -P['srcback']['P_flux']
    T_bar = P1 / P_inc
    T_cross = P2 / P_inc
    L = meta['L_um'] * 1e-6
    kappa = float(np.arcsin(np.sqrt(min(max(T_cross, 0.0), 1.0))) / L)
    out = dict(label=meta.get('label', ''), wall_s=float(wall), meta=meta,
               ports={k: {kk: float(vv) for kk, vv in v.items()}
                      for k, v in P.items()},
               boundary={k: float(v) for k, v in res['boundary'].items()},
               T_bar=float(T_bar), T_cross=float(T_cross),
               crosstalk_db=float(10 * np.log10(max(T_cross, 1e-30))),
               bar_db=float(10 * np.log10(max(T_bar, 1e-30))),
               T_reflection=float(P_refl / P_inc),
               reflection_db=float(20 * np.log10(max(P['in']['a_minus']
                                                     / P['in']['a_plus'], 1e-30))),
               kappa_fdtd_mm_inv=float(kappa * 1e-3),
               kappa_m_per_s=float(kappa),
               P_inc=float(P_inc), P_in_net=float(P_in_net),
               P_srcback=float(P_srcback), P_boundary=float(P_boundary),
               energy_residual=float((P_boundary - P_in_net - P_srcback)
                                     / P_in_net),
               kappa_L=float(kappa * L),
               sin2_check=float(np.sin(kappa * L) ** 2))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--d', type=float, default=15.0)
    ap.add_argument('--L', type=float, default=280.0)
    ap.add_argument('--dx', type=float, default=0.05)
    ap.add_argument('--order', type=int, default=4)
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--window', type=float, default=40.0)
    args = ap.parse_args()
    label = f'cpl_d{args.d:g}_L{args.L:g}_dx{args.dx:g}'
    fn = os.path.join(CACHE, f'coupler_{label}.json')
    if os.path.exists(fn) and not args.force:
        print('exists', fn)
        return
    print('=== parallel coupler d=%g um L=%g um dx=%g ===' % (args.d, args.L, args.dx))
    sim, meta = build(args.d, args.L, dx_um=args.dx, order=args.order, label=label)
    meta['label'] = label
    print('  cells=%.2fM dt=%.3e' % (meta['cells'] / 1e6, meta['dt']), flush=True)
    t0 = time.time()
    sim.run(window_periods=args.window, print_every=8000)
    out = analyse(sim, meta, time.time() - t0)
    json.dump(out, open(fn, 'w'), indent=1, default=float)
    print('  T_bar=%.5f (%.2f dB)  T_cross=%.4e (%.2f dB)  kappa=%.4e 1/mm  '
          'refl=%.1f dB  resid=%.1e  wall=%.0fs'
          % (out['T_bar'], out['bar_db'], out['T_cross'], out['crosstalk_db'],
             out['kappa_fdtd_mm_inv'], out['reflection_db'],
             out['energy_residual'], out['wall_s']), flush=True)


if __name__ == '__main__':
    main()
