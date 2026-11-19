# -*- coding: utf-8 -*-
"""Iterate the re-layering solver: each pass re-places routes in the world left
by the previous pass, so routes that were blocked by a temporarily occupied
height get another chance.  Cheap (about a minute per pass) and monotone in the
number of routes that find a conflict-free height.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXP = ROOT / 'experiments' / 'G5_ANGLE45_NATIVE3D_20H_1024'
PY = str(ROOT / '.venv' / 'Scripts' / 'python.exe')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--passes', type=int, default=6)
    parser.add_argument('--start', default=str(EXP / '03_best_partial'
                                              / 'routes_l3d.json'))
    parser.add_argument('--out', default=str(EXP / '02_search_runs'
                                             / 'relayer_iter'))
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    current = Path(args.start)
    history = []
    for index in range(args.passes):
        directory = out / ('pass_%02d' % index)
        command = [PY, str(EXP / '01_algorithm' / 'relayer.py'),
                   '--routes', str(current), '--out', str(directory),
                   '--time-limit', '1800']
        result = subprocess.run(command, capture_output=True, text=True,
                                cwd=str(ROOT))
        summary = None
        path = directory / 'relayer_result.json'
        if path.exists():
            summary = json.loads(path.read_text(encoding='utf-8'))
        else:
            print(result.stdout[-2000:])
            print(result.stderr[-2000:])
            break
        state = summary['summary']
        history.append(dict(pass_index=index, violations=state['violations'],
                            crossings=state['crossings'],
                            deficit=state['deficit'],
                            min_angle=state['min_angle'],
                            hard_issues=state['hard_issues'],
                            moves=summary['moves'],
                            failed=len(summary['failures'])))
        print('[pass %d] violations=%d crossings=%d deficit=%.1f moves=%d '
              'failed=%d' % (index, state['violations'], state['crossings'],
                             state['deficit'], summary['moves'],
                             len(summary['failures'])), flush=True)
        if state['violations'] == 0:
            break
        current = directory / 'routes_l3d.json'
    (out / 'iteration_history.json').write_text(
        json.dumps(history, indent=1, ensure_ascii=False), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
