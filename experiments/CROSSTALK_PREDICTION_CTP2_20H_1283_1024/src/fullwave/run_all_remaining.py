"""Run all remaining GPU cases sequentially (single GPU), with error isolation."""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(HERE, '..', '..'))
CACHE = os.path.join(BASE, 'cache', 'fullwave')
PY = sys.executable

STEPS = [
    # fine 2-D crossing resolutions (critical for the BMT cross-check)
    ['run_all_2d.py', '--cases', 'fine'],
    # 3-D spot checks
    ['run_3d.py', '--case', 'straight'],
    ['run_3d.py', '--case', 'cross90'],
    # 2-D parallel coupler
    ['run_2d_coupler.py', '--d', '12', '--L', '280'],
    ['run_2d_coupler.py', '--d', '12', '--L', '140'],
    ['run_2d_coupler.py', '--d', '15', '--L', '280'],
    ['run_2d_coupler.py', '--d', '20', '--L', '280'],
    # 2-D straight-guide validation
    ['run_2d_validation.py'],
    # 3-D couplers
    ['run_3d.py', '--case', 'coupler'],
]


def main():
    log = open(os.path.join(CACHE, 'log_remaining.txt'), 'a', encoding='utf-8')
    t00 = time.time()
    for cmd in STEPS:
        line = '\n===== %s @ %.0fs =====' % (' '.join(cmd), time.time() - t00)
        print(line, flush=True)
        log.write(line + '\n'); log.flush()
        try:
            r = subprocess.run([PY, '-u'] + cmd, cwd=HERE,
                               stdout=log, stderr=subprocess.STDOUT,
                               timeout=5400)
            print('  exit', r.returncode, flush=True)
        except Exception as e:
            print('  FAILED:', e, flush=True)
            log.write('FAILED: %s\n' % e); log.flush()
    msg = '\nALL DONE %.0f s' % (time.time() - t00)
    print(msg); log.write(msg + '\n'); log.flush(); log.close()


if __name__ == '__main__':
    main()
