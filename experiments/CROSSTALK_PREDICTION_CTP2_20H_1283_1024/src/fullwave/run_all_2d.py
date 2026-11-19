"""Driver: run the 2-D tilted-guide calibrations and the crossing cases.

Sequential GPU execution (single GPU).  Each case writes a JSON in cache/fullwave.
"""
import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fwlib as fw
import run_2d_tilted as T
import run_2d_crossing as C

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(HERE, '..', '..'))
CACHE = os.path.join(BASE, 'cache', 'fullwave')


def get_tilted(theta, dx, order=4, force=False, window=40.0):
    label = f'tilt{theta:g}_dx{dx:g}_o{order}'
    fn = os.path.join(CACHE, f'tilted_{label}.json')
    if os.path.exists(fn) and not force:
        return json.load(open(fn))
    sim, meta = T.build(theta, dx, order=order, label=label)
    meta['label'] = label
    t0 = time.time()
    sim.run(window_periods=window, print_every=8000)
    res = T.analyse(sim, meta, time.time() - t0)
    res['label'] = label
    json.dump(res, open(fn, 'w'), indent=1, default=float)
    print('  [tilted %s] beta=%.6f/um T=%.5f floor=%.1f dB wall=%.0fs'
          % (label, res['beta_arm'] / 1e6, res['T_through'], res['floor_db'],
             res['wall_s']), flush=True)
    return res


def get_cross(theta, dx, sep, order=4, force=False, window=60.0, snapshot=False,
              beta_arm=None, label=None):
    label = label or f'theta{theta:g}_dx{dx:g}_o{order}_sep{sep:g}'
    fn = os.path.join(CACHE, f'cross_{label}.json')
    if os.path.exists(fn) and not force:
        return json.load(open(fn))
    if beta_arm is None:
        tilted = get_tilted(theta, dx, order=order)
        beta_arm = tilted['beta_arm'] / 1e6
    sim, meta = C.make_crossing_sim(theta, dx, sep, order=order, label=label)
    meta['label'] = label
    for nm in ('cross_p', 'cross_m'):
        sim.oblique_arms[nm]['beta_override'] = beta_arm * 1e6
    print('  [cross %s] cells=%.1fM dt=%.3e' % (label, meta['cells'] / 1e6,
                                                meta['dt']), flush=True)
    t0 = time.time()
    sim.run(window_periods=window, print_every=8000)
    if snapshot:
        step = max(1, int(np.ceil(sim.dx / 0.15e-6)))
        np.savez(os.path.join(CACHE, f'snap_{label}.npz'),
                 psi=sim.st.psi_a.detach().cpu().numpy()[::step, ::step],
                 x=sim.g.axes[0][::step], y=sim.g.axes[1][::step])
    res = C.analyse_crossing(sim, meta, time.time() - t0)
    res['label'] = label
    json.dump(res, open(fn, 'w'), indent=1, default=float)
    print('  [cross %s] T_th=%.5f XT=%.2f dB refl=%.1f dB T_rad=%.3e resid=%.1e '
          'wall=%.0fs' % (label, res['T_through'], res['crosstalk_db'],
                          res['reflection_db'], res['T_radiation'],
                          res['energy_residual'], res['wall_s']), flush=True)
    return res


CASES = [
    # (theta_deg, dx_um, sep_um, order, snapshot)
    (30, 0.05, 40, 4, False),
    (20, 0.05, 40, 4, True),
    (10, 0.05, 30, 4, False),
    (5, 0.05, 30, 4, True),
    (15, 0.05, 30, 4, False),
    (45, 0.05, 40, 4, False),
    (60, 0.05, 40, 4, False),
    (75, 0.05, 40, 4, False),
    (90, 0.05, 40, 4, False),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cases', type=str, default='main',
                    help='main | fine | custom:theta:dx:sep,...')
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--window', type=float, default=60.0)
    args = ap.parse_args()
    t00 = time.time()
    if args.cases == 'main':
        cases = CASES
    elif args.cases == 'fine':
        cases = [(20, 0.03, 40, 4, False), (30, 0.03, 40, 4, False),
                 (10, 0.04, 30, 4, False)]
    else:
        cases = []
        for tok in args.cases.split(';'):
            th, dx, sep = [float(x) for x in tok.split(',')]
            cases.append((th, dx, sep, 4, False))
    results = {}
    for (th, dx, sep, order, snap) in cases:
        results[f'{th}_{dx}'] = get_cross(th, dx, sep, order=order,
                                          force=args.force, window=args.window,
                                          snapshot=snap)
    print('TOTAL wall %.0f s' % (time.time() - t00), flush=True)


if __name__ == '__main__':
    main()
