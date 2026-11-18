# -*- coding: utf-8 -*-
"""Third audited patch: remaining 21-height literals in assign21 reporting/logs."""
import sys
from pathlib import Path

PATH = (Path(r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D'
             r'\four_side_1024\fanout1024\reheight21') / 'assign21.py')

PATCHES = [
    ('Q6 height-count question',
     "             question='21 distinct heights with min pitch >= 0.05 mm?',\n"
     "             answer=(audit['height_count'] == 21\n",
     "             question=('%d distinct heights with min pitch >= 0.05 mm?'\n"
     "                       % len(M.PLANE_IDS)),\n"
     "             answer=(audit['height_count'] == len(M.PLANE_IDS)\n"),
    ('direct-route note',
     "            note='Z1: baseline L6/L7 routes now direct on Z1_INTERFACE; '\n"
     "                 'Z2: baseline L19 routes now direct on Z2_INTERFACE'),\n",
     "            note='direct routes target their own interface height: '\n"
     "                 'Z1 plane 1001 (z=%+.3f), Z2 plane 1002 (z=%+.3f)'\n"
     "                 % (M.plane_z(1001), M.plane_z(1002))),\n"),
    ('summary header line',
     "        '=== 21-height experiment A: layer model + 1024 assignment + diff ===',\n",
     "        '=== %s: layer model + 1024 assignment + diff ===' % M.EXPERIMENT_NAME,\n"),
    ('summary rows/planes line',
     "        f\"z2 {audit['z2']}, 21 planes / \"\n",
     "        f\"z2 {audit['z2']}, {len(M.PLANE_IDS)} planes / \"\n"),
    ('markdown diff header',
     "    lines.append('# 21-height rebalanced 1024 assignment 閳? diff vs the '\n",
     "    lines.append('# %s assignment 閳? diff vs the '\n"
     "                 % M.EXPERIMENT_NAME +\n"),
    ('markdown plane-count header',
     "    lines.append('## 1. Plane counts (baseline 18 planes -> new 21 planes)')\n",
     "    lines.append('## 1. Plane counts (baseline %d planes -> new %d planes)'\n"
     "                 % (len(C.PHYSICAL_LAYERS), len(M.PLANE_IDS)))\n"),
    ('experiment A log header',
     "                          '=== 21-height experiment A: layer model + 1024 assignment + diff ===',\n",
     "                          '=== %s experiment A: layer model + 1024 '\n"
     "                          'assignment + diff ===' % M.EXPERIMENT_NAME,\n"),
    ('Q7 orbit evidence count',
     "             evidence=dict(non_manual_orbits=164)),\n",
     "             evidence=dict(non_manual_orbits=(\n"
     "                 len(state['z1_opposite_groups'])\n"
     "                 + len(state['z2_adjacent_groups'])))),\n"),
]


def main():
    text = PATH.read_text(encoding='utf-8')
    failures = []
    for name, old, new in PATCHES:
        found = text.count(old)
        if found != 1:
            failures.append((name, found))
            continue
        text = text.replace(old, new)
        print(f'OK   {name}')
    PATH.write_text(text, encoding='utf-8')
    for name, found in failures:
        print(f'FAIL {name}: found {found}')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())

