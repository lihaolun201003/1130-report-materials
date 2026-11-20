# -*- coding: utf-8 -*-
"""Cold-start driver: 20-height assignment -> fanout -> D56 XY -> 3D -> E5 repair.

This is the 20-height equivalent of the frozen 21-height run::

    python -m four_side_1024.fanout1024.reheight21.assign21
    python -m four_side_1024.fanout1024.reheight21.run21 --stages ABCDE

but it installs the 20-height profile first and writes only below
``experiments/COLD_START_20_HEIGHT_1024/``.

Stages (frozen ``run21`` semantics, unchanged)
---------------------------------------------
A  layer model + 1024-row assignment + audit + baseline diff      (assign21)
B  endpoint R15 transitions + interface-direct records            (fanout)
C  per-height strict-D56 multi-arc 2D body routing                (layer2d)
D  full 3D assembly + strict 0.05 mm world check                  (assemble)
E  joint repair loop until 1024/1024 or a real failure list
F  final independent experiment-D summary

Usage
-----
::

    .venv\\Scripts\\python.exe -m four_side_1024.fanout1024.coldstart20.run_initial
    .venv\\Scripts\\python.exe -m four_side_1024.fanout1024.coldstart20.run_initial \\
        --stages CDE --max-iters 4
"""
from __future__ import annotations

import argparse
import sys
import time

from . import bootstrap as B          # installs the 20-height profile on import
from . import model20 as M


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stages', default='ABCDEF')
    parser.add_argument('--max-iters', type=int, default=3)
    parser.add_argument('--run-dir', default=None)
    parser.add_argument('--skip-assign', action='store_true',
                        help='reuse the existing assignment_1024.csv')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    B.install()
    if args.run_dir:
        B.bind_run_dir(args.run_dir)
    else:
        B.bind_run_dir(M.RUN_DIR)
    B.assert_20_height_profile('run_initial')

    from ..reheight21 import assign21, run21

    started = time.time()
    if not args.skip_assign:
        print('[20h] stage A0: assignment + audit + baseline diff', flush=True)
        assign21.main()
    else:
        print('[20h] stage A0: skipped (reuse existing assignment)', flush=True)

    log = run21.make_logger(tag='20h')
    log(f'20-height cold start: stages={args.stages} '
        f'max_iters={args.max_iters} run_dir={M.RUN_DIR}')
    log('profile: ' + ' | '.join(B.summary_lines()))
    result = run21.run_stages(args.stages, max_iters=args.max_iters, log=log)
    log(f'20-height cold start done in {time.time() - started:.1f}s')
    return result


if __name__ == '__main__':
    main()
