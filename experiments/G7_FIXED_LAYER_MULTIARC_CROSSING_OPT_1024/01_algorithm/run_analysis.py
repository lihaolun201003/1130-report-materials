# -*- coding: utf-8 -*-
"""Run the G7 scientific analysis (per-layer stats, attribution, residual probe)."""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
EXP = os.path.abspath(os.path.join(HERE, '..'))
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)

from four_side_1024.fanout1024.xyzrouter.g7 import analysis  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', default=os.path.join(
        EXP, '00_frozen_g6', 'routes_l3d.json'))
    parser.add_argument('--after', default=os.path.join(
        EXP, '03_best_valid', 'routes_l3d.json'))
    parser.add_argument('--reference', default=os.path.join(
        EXP, '00_frozen_g6', 'routes_l3d.json'))
    parser.add_argument('--out', default=os.path.join(EXP, '06_reports'))
    parser.add_argument('--top-n', type=int, default=30)
    args = parser.parse_args(argv)
    run_root = os.path.join(EXP, '02_sa_runs')
    arms = dict(A=os.path.join(run_root, 'arm_A_plane'),
                B=os.path.join(run_root, 'arm_B_plane'),
                C=os.path.join(run_root, 'arm_C_plane'))
    data = analysis.build_analysis(args.before, args.after, run_root, arms,
                                   args.out, reference_path=args.reference,
                                   top_n=args.top_n)
    import json
    print(json.dumps({
        'before_crossings': data['before']['crossings'],
        'after_crossings': data['after']['crossings'],
        'before_pairs': data['before']['unique_pairs'],
        'after_pairs': data['after']['unique_pairs'],
        'residual_probe': {key: data['residual_probe'][key]
                           for key in ('top', 'fixable', 'blocked')},
        'out': args.out}, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
