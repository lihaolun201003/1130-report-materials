# -*- coding: utf-8 -*-
"""Second audited patch: make the assign21 *reporting* paths profile-generic.

Only report/diff payload code is touched (no search logic, no expectation is
relaxed).  The 21-height payloads stay structurally compatible; the 20-height
profile simply reports its own whole-orbit Z2 plan.
"""
import re
import sys
from pathlib import Path

PKG = Path(r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D'
           r'\four_side_1024\fanout1024\reheight21')
PATH = PKG / 'assign21.py'

PATCHES = []


def patch(name, old, new, count=1):
    PATCHES.append(dict(name=name, old=old, new=new, count=count))


# --------------------------------------------------------------------- helper
patch('assign21: add Z2 orbit-summary helper',
      "def _new(passed, detail=None):\n",
      "def _z2_orbit_summary(state):\n"
      '    """Whole-orbit Z2 allocation summary derived from the real state.\n'
      "\n"
      "    ``{old_layer: {old_layer, new_planes: {plane: routes}, routes,\n"
      "    orbits}}`` -- profile agnostic: the 21-height profile ends up with a\n"
      "    single new plane per old layer, the 20-height profile may spread one\n"
      "    baseline old layer over several surviving planes.\n"
      '    """\n'
      "    rows = collections.OrderedDict()\n"
      "    for group in state['z2_adjacent_groups']:\n"
      "        info = state['z2_orbit_plane'][int(group['group_id'])]\n"
      "        key = int(info['old_layer'])\n"
      "        entry = rows.setdefault(key, dict(\n"
      "            old_layer=key, new_planes=collections.Counter(), routes=0,\n"
      "            orbits=0))\n"
      "        entry['new_planes'][int(info['new_plane'])] += len(info['route_ids'])\n"
      "        entry['routes'] += len(info['route_ids'])\n"
      "        entry['orbits'] += 1\n"
      "    for entry in rows.values():\n"
      "        entry['new_planes'] = dict(sorted(entry['new_planes'].items()))\n"
      "    return rows\n"
      "\n"
      "\n"
      "def _new(passed, detail=None):\n")

# ------------------------------------------------------- expected orbit counts
patch('assign21: expected Z2 orbit counts from the real plan',
      "    expected_z2_orbits = collections.Counter()\n"
      "    if getattr(M, 'Z2_OTHER_PLAN', None):\n"
      "        for plane_id, capacity in M.Z2_OTHER_PLAN:\n"
      "            expected_z2_orbits[int(plane_id)] += int(capacity)\n"
      "    else:\n"
      "        for old_layer, new_plane in M.Z2_OTHER_OLD_TO_NEW.items():\n"
      "            expected_z2_orbits[int(new_plane)] += int(M.CONTRACT_OLD_LAYER_COUNTS[int(old_layer)] / 4)\n",
      "    expected_z2_orbits = collections.Counter()\n"
      "    if getattr(M, 'Z2_OTHER_PLAN', None):\n"
      "        for plane_id, capacity in M.Z2_OTHER_PLAN:\n"
      "            expected_z2_orbits[int(plane_id)] += int(capacity)\n"
      "    else:\n"
      "        for row in _z2_orbit_summary(state).values():\n"
      "            for plane_id, routes in row['new_planes'].items():\n"
      "                expected_z2_orbits[int(plane_id)] += int(routes) // 4\n")

# ----------------------------------------------------------- audit z2_by_plane
patch('assign21: audit per-plane Z2 counts from the contract',
      "    z2_by_plane = collections.OrderedDict(\n"
      "        (str(new_plane), sum(1 for row in rows\n"
      "                             if row['layer_role'] == 'z2_other'\n"
      "                             and int(row['target_layer']) == int(new_plane)))\n"
      "        for old, new_plane in M.Z2_OTHER_OLD_TO_NEW.items())\n",
      "    z2_by_plane = collections.OrderedDict(\n"
      "        (str(int(plane_id)), sum(1 for row in rows\n"
      "                                 if row['layer_role'] == 'z2_other'\n"
      "                                 and int(row['target_layer']) == int(plane_id)))\n"
      "        for plane_id in M.CONTRACT_Z2_OTHER_COUNTS)\n")

# ------------------------------------------------- audit z2_other old_to_new key
patch('assign21: audit Z2 old_to_new block',
      "        z2_other=dict(\n"
      "            orbits=len(state['z2_adjacent_groups']),\n"
      "            old_to_new={str(old): int(new) for old, new\n"
      "                        in M.Z2_OTHER_OLD_TO_NEW.items()},\n"
      "            routes_per_new_plane=dict(z2_by_plane),\n",
      "        z2_other=dict(\n"
      "            orbits=len(state['z2_adjacent_groups']),\n"
      "            old_to_new={str(old): item['new_planes'] for old, item\n"
      "                        in _z2_orbit_summary(state).items()},\n"
      "            plan=([[int(plane_id), int(capacity)] for plane_id, capacity\n"
      "                   in M.Z2_OTHER_PLAN]\n"
      "                  if getattr(M, 'Z2_OTHER_PLAN', None) else None),\n"
      "            routes_per_new_plane=dict(z2_by_plane),\n")

# ------------------------------------------------------- build_diff z2 mapping
patch('assign21: diff Z2 mapping rows',
      "    z2_mapping = []\n"
      "    for old_layer, new_plane in M.Z2_OTHER_OLD_TO_NEW.items():\n"
      "        orbits = [group_id for group_id, info\n"
      "                  in _state()['z2_orbit_plane'].items()\n"
      "                  if int(info['old_layer']) == int(old_layer)]\n"
      "        z2_mapping.append(dict(\n"
      "            old_layer=int(old_layer),\n"
      "            old_label=_baseline_old_label(old_layer),\n"
      "            old_z_mm=_baseline_old_z(old_layer),\n"
      "            new_plane=int(new_plane),\n"
      "            new_label=M.plane_label(new_plane),\n"
      "            new_z_mm=M.plane_z(new_plane),\n"
      "            old_route_count=int(EXPECTED_OLD_LAYER_COUNTS[int(old_layer)]),\n"
      "            new_route_count=int(new_plane_counts[int(new_plane)]),\n"
      "            orbits=len(orbits),\n"
      "            direction_old=('down' if _baseline_old_z(old_layer)\n"
      "                           < float(C.INTERFACE_Z['z2']) else 'up'),\n"
      "            direction_new=M.direction_for(int(new_plane), 'z2'),\n"
      "        ))\n",
      "    z2_mapping = []\n"
      "    for old_layer, summary in _z2_orbit_summary(_state()).items():\n"
      "        z2_mapping.append(dict(\n"
      "            old_layer=int(old_layer),\n"
      "            old_label=_baseline_old_label(old_layer),\n"
      "            old_z_mm=_baseline_old_z(old_layer),\n"
      "            new_planes={str(plane_id): int(routes) for plane_id, routes\n"
      "                        in summary['new_planes'].items()},\n"
      "            new_plane=(int(next(iter(summary['new_planes'])))\n"
      "                       if len(summary['new_planes']) == 1 else None),\n"
      "            new_label=(M.plane_label(int(next(iter(summary['new_planes']))))\n"
      "                       if len(summary['new_planes']) == 1 else None),\n"
      "            new_z_mm=(M.plane_z(int(next(iter(summary['new_planes']))))\n"
      "                      if len(summary['new_planes']) == 1 else None),\n"
      "            old_route_count=int(EXPECTED_OLD_LAYER_COUNTS[int(old_layer)]),\n"
      "            new_route_count=int(summary['routes']),\n"
      "            orbits=int(summary['orbits']),\n"
      "            direction_old=('down' if _baseline_old_z(old_layer)\n"
      "                           < float(C.INTERFACE_Z['z2']) else 'up'),\n"
      "            direction_new=([M.direction_for(int(plane_id), 'z2')\n"
      "                            for plane_id in sorted(summary['new_planes'])]),\n"
      "        ))\n")

patch('assign21: diff Z2 note',
      "        z2_other=dict(old_to_new=[dict(item) for item in z2_mapping],\n"
      "                      note='baseline whole-layer C4 orbit groups are remapped '\n"
      "                           '1:1 to new planes; direction flips are documented '\n"
      "                           'in direction_changes'),\n",
      "        z2_other=dict(old_to_new=[dict(item) for item in z2_mapping],\n"
      "                      plan=([[int(plane_id), int(capacity)]\n"
      "                             for plane_id, capacity in M.Z2_OTHER_PLAN]\n"
      "                            if getattr(M, 'Z2_OTHER_PLAN', None) else None),\n"
      "                      note='baseline whole-layer C4 orbit groups are '\n"
      "                           'remapped to the new planes by the active '\n"
      "                           'profile allocation (21 heights: 1:1 old layer '\n"
      "                           'map; 20 heights: whole-orbit plan over the 7 '\n"
      "                           'surviving Z2 other planes); direction flips are '\n"
      "                           'documented in direction_changes'),\n")

patch('assign21: diff manual note',
      "            note='manual groups keep their baseline route membership and '\n"
      "                 'plane ids; the Z1 manual z values follow the new model, so '\n"
      "                 'planes 3/4/5 shift to -0.30/-0.25/-0.20 mm',\n",
      "            note='manual groups keep their baseline route membership and '\n"
      "                 'plane ids; only the physical z of each manual plane '\n"
      "                 'follows the active height model: ' + ', '.join(\n"
      "                     'L%s=%+.3f' % (M.plane_label(int(spec['plane_id'])),\n"
      "                                    float(spec['z_mm']))\n"
      "                     for spec in M.MANUAL_GROUP_SPECS.values()),\n")

patch('assign21: diff z1 plan note',
      "                      note='64 whole C4 opposite orbits sorted by group_id '\n"
      "                           'are consumed from the plan (52/52/52/52/48)'),\n",
      "                      note='64 whole C4 opposite orbits sorted by group_id '\n"
      "                           'are consumed from the plan %s' % (\n"
      "                               tuple((int(plane), int(capacity) * 4)\n"
      "                                     for plane, capacity\n"
      "                                     in M.Z1_OTHER_PLAN),)),\n")

patch('assign21: experiment A z2 old_to_new',
      "            z2_old_to_new={str(old): int(new) for old, new\n"
      "                           in M.Z2_OTHER_OLD_TO_NEW.items()},\n",
      "            z2_old_to_new={str(old): item['new_planes'] for old, item\n"
      "                           in _z2_orbit_summary(_state()).items()},\n")

patch('assign21: experiment name (2 sites)',
      "        experiment='FANOUT_FIRST_21_HEIGHT_REBALANCED_1024',",
      "        experiment=M.EXPERIMENT_NAME,", count=2)


def main():
    text = PATH.read_text(encoding='utf-8')
    failures = []
    for item in PATCHES:
        found = text.count(item['old'])
        if found != item['count']:
            failures.append((item['name'], found, item['count']))
            continue
        text = text.replace(item['old'], item['new'])
        print(f'OK   {item["name"]}  ({found} site(s))')
    PATH.write_text(text, encoding='utf-8')
    if failures:
        print('\nFAILURES:')
        for name, found, want in failures:
            print(f'  {name}: found {found}, expected {want}')
    # report residual risky literals
    print('\n--- residual 21/19/z literals in assign21.py ---')
    for number, line in enumerate(text.splitlines(), 1):
        if re.search(r"(?<![0-9_.])(21|19)(?![0-9_.])", line) and \
                not line.strip().startswith('#'):
            print(f'{number}: {line.strip()[:160]}')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
