"""Numeric crosstalk floor control run: SAME crossing domain/ports but with the
tilted guide REMOVED.  Any guided amplitude extracted at the cross-arm ports is
then pure numerical/radiation leakage, i.e. the crosstalk measurement floor.

Run:  python run_floor_check.py --theta 20 --dx 0.05 --sep 40
"""
import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fwlib as fw
import run_2d_crossing as C

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(HERE, '..', '..'))
CACHE = os.path.join(BASE, 'cache', 'fullwave')
OUT = os.path.join(BASE, 'outputs', 'fullwave')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--theta', type=float, default=20.0)
    ap.add_argument('--dx', type=float, default=0.05)
    ap.add_argument('--sep', type=float, default=40.0)
    ap.add_argument('--window', type=float, default=60.0)
    ap.add_argument('--label', type=str, default='')
    args = ap.parse_args()
    label = args.label or f'floor_theta{args.theta:g}_dx{args.dx:g}'
    tilt = json.load(open(os.path.join(
        CACHE, f'tilted_tilt{args.theta:g}_dx{args.dx:g}_o4.json')))
    beta = tilt['beta_arm'] / 1e6
    sim, meta = C.make_crossing_sim(args.theta, args.dx, args.sep, order=4,
                                    label=label, only_guide1=True)
    for nm in ('cross_p', 'cross_m'):
        sim.oblique_arms[nm]['beta_override'] = beta * 1e6
    print('=== floor check theta=%g dx=%g (guide 2 removed) ===' %
          (args.theta, args.dx), flush=True)
    print('  cells=%.1fM' % (meta['cells'] / 1e6), flush=True)
    t0 = time.time()
    sim.run(window_periods=args.window, print_every=8000)
    out = C.analyse_crossing(sim, meta, time.time() - t0)
    out['label'] = label
    out['floor_check'] = True
    fn = os.path.join(CACHE, f'floor_{label}.json')
    json.dump(out, open(fn, 'w'), indent=1, default=float)
    print('  cross-arm guided power / P_inc = %.2f dB  (T_cross=%.2e)'
          % (out['crosstalk_db'], out['T_cross']))
    print('  also: backward arm %.1f dB, through %.4f, T_rad=%.3e'
          % (10 * np.log10(max(out['T_backward_cross'], 1e-30)), out['T_through'],
             out['T_radiation']))
    print('  wall=%.0f s' % out['wall_s'])


if __name__ == '__main__':
    main()
