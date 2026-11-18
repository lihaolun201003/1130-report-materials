# -*- coding: utf-8 -*-
"""One-shot, audited source patch: make reheight21 pipeline modules profile-generic.

Every replacement below is exact-match and asserts its occurrence count, so a
silent half-applied patch is impossible.  The 21-height values are unchanged
(they now live in ``model.py`` as the ``CONTRACT_*`` / ``SPEC_*`` tables); the
consumers read them through the ``model`` module, which
``coldstart20.bootstrap`` swaps for the 20-height model.
"""
import io
import sys
from pathlib import Path

PKG = Path(r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D'
           r'\four_side_1024\fanout1024\reheight21')

PATCHES = []


def patch(name, old, new, count=1):
    PATCHES.append(dict(name=name, old=old, new=new, count=count))


# ===========================================================================
# model.py -- schema / experiment literals -> module constants
# ===========================================================================
patch('model.py: MODEL_NAME constant',
      "PROFILE = '21_height_rebalanced'\n",
      "PROFILE = '21_height_rebalanced'\n"
      "#: canonical `model` value written into payloads\n"
      "MODEL_NAME = 'reheight21.model'\n")

patch('model.py: layer_planes schema',
      "        schema='reheight21_layer_planes_v1',\n",
      "        schema=SCHEMA_LAYER_PLANES,\n")
patch('model.py: stack schema',
      "        schema='reheight21_layer_stack_v1',\n",
      "        schema=SCHEMA_LAYER_STACK,\n")
patch('model.py: rules schema',
      "        schema='reheight21_process_rules_v1',\n",
      "        schema=SCHEMA_PROCESS_RULES,\n")
patch('model.py: experiment name (3 sites)',
      "experiment='FANOUT_FIRST_21_HEIGHT_REBALANCED_1024',",
      "experiment=EXPERIMENT_NAME,", count=3)
patch('model.py: model name (2 sites)',
      "model='reheight21.model',",
      "model=MODEL_NAME,", count=2)

# ===========================================================================
# assign21.py -- read the contract tables from the model profile
# ===========================================================================
patch('assign21.py: expected plane counts',
      "EXPECTED_PLANE_COUNTS = collections.OrderedDict([\n"
      "    (2, 64), (3, 64), (4, 64), (5, 64),\n"
      "    (6, 52), (7, 52), (20, 52), (1001, 52), (8, 48),\n"
      "    (9, 48),\n"
      "    (10, 16), (11, 16), (12, 40), (13, 40),\n"
      "    (14, 48), (15, 48), (16, 52), (1002, 48), (17, 52), (18, 52), (19, 52),\n"
      "])\n"
      "EXPECTED_DIRECT_ROUTES = 100\n"
      "EXPECTED_DIRECT_Z1 = 52\n"
      "EXPECTED_DIRECT_Z2 = 48\n"
      "EXPECTED_TRANSITION_ROUTES = 1024 - EXPECTED_DIRECT_ROUTES\n"
      "EXPECTED_ENDPOINT_TRANSITIONS = 2 * EXPECTED_TRANSITION_ROUTES   # 1848\n"
      "EXPECTED_MANUAL_COUNTS = collections.OrderedDict([\n"
      "    ('Z1-U1', 64), ('Z1-U2', 64), ('Z1-U3', 64), ('Z1-U4', 64),\n"
      "    ('Z2-U1', 16), ('Z2-U2', 16), ('Z2-U3', 40), ('Z2-U4', 40),\n"
      "])\n"
      "EXPECTED_MANUAL_TOTAL = sum(EXPECTED_MANUAL_COUNTS.values())      # 368\n"
      "EXPECTED_Z1_OTHER_COUNTS = collections.OrderedDict([\n"
      "    (plane, capacity * 4) for plane, capacity in M.Z1_OTHER_PLAN])\n"
      "# baseline old-layer -> route count (from the frozen baseline assignment)\n"
      "EXPECTED_OLD_LAYER_COUNTS = collections.OrderedDict([\n"
      "    (8, 48), (9, 48), (14, 48), (15, 52), (16, 52), (17, 52), (18, 52),\n"
      "    (19, 48),\n"
      "])\n"
      "#: new-plane route counts implied by the old-layer -> new-plane mapping\n"
      "EXPECTED_Z2_OTHER_COUNTS = collections.OrderedDict(\n"
      "    (int(new_plane), int(EXPECTED_OLD_LAYER_COUNTS[int(old_layer)]))\n"
      "    for old_layer, new_plane in M.Z2_OTHER_OLD_TO_NEW.items())\n"
      "\n"
      "#: manual C4 orbit structure: each manual orbit is split over exactly the two\n"
      "#: fixed planes of its numbering scheme (NS plane + EW plane)\n"
      "EXPECTED_MANUAL_ORBIT_PLANE_SETS = {\n"
      "    (2, 4): 32, (3, 5): 32, (10, 11): 8, (12, 13): 20,\n"
      "}\n",
      "#: ---- every expected value comes from the ACTIVE height profile -------\n"
      "#: ``model.CONTRACT_*`` holds the frozen SPEC contract of the installed\n"
      "#: profile (21 heights: ``reheight21.model``; 20 heights:\n"
      "#: ``coldstart20.model20``).  No expectation is relaxed -- only re-pointed.\n"
      "EXPECTED_PLANE_COUNTS = M.CONTRACT_PLANE_COUNTS\n"
      "EXPECTED_DIRECT_ROUTES = int(M.CONTRACT_DIRECT_ROUTES['total'])\n"
      "EXPECTED_DIRECT_Z1 = int(M.CONTRACT_DIRECT_ROUTES['z1'])\n"
      "EXPECTED_DIRECT_Z2 = int(M.CONTRACT_DIRECT_ROUTES['z2'])\n"
      "EXPECTED_TRANSITION_ROUTES = int(M.CONTRACT_TRANSITION_ROUTES)\n"
      "EXPECTED_ENDPOINT_TRANSITIONS = int(M.CONTRACT_ENDPOINT_TRANSITIONS)\n"
      "EXPECTED_MANUAL_COUNTS = M.CONTRACT_MANUAL_COUNTS\n"
      "EXPECTED_MANUAL_TOTAL = int(M.CONTRACT_MANUAL_TOTAL)\n"
      "EXPECTED_Z1_OTHER_COUNTS = collections.OrderedDict([\n"
      "    (plane, capacity * 4) for plane, capacity in M.Z1_OTHER_PLAN])\n"
      "EXPECTED_OLD_LAYER_COUNTS = M.CONTRACT_OLD_LAYER_COUNTS\n"
      "EXPECTED_Z2_OTHER_COUNTS = M.CONTRACT_Z2_OTHER_COUNTS\n"
      "EXPECTED_MANUAL_ORBIT_PLANE_SETS = dict(M.CONTRACT_MANUAL_ORBIT_PLANE_SETS)\n")

patch('assign21.py: z2 allocation delegates to the profile',
      "def _z2_other_allocation(baseline, z2_orbits):\n"
      '    """Whole C4 ``adjacent`` Z2 orbits: baseline old layer -> new plane."""\n'
      "    route_plane = {}\n"
      "    orbit_plane = collections.OrderedDict()\n"
      "    old_layer_counts = collections.Counter()\n"
      "    for group in z2_orbits:\n"
      "        old_layers = {int(float(baseline['by_id'][int(rid)]['target_layer']))\n"
      "                      for rid in group['route_ids']}\n"
      "        if len(old_layers) != 1:\n"
      "            raise ValueError(f'z2 orbit {group[\"group_id\"]}: baseline old '\n"
      "                             f'layers not unique: {sorted(old_layers)}')\n"
      "        old_layer = old_layers.pop()\n"
      "        if old_layer not in M.Z2_OTHER_OLD_TO_NEW:\n"
      "            raise ValueError(f'z2 orbit {group[\"group_id\"]}: old layer '\n"
      "                             f'{old_layer} has no new-plane mapping')\n"
      "        new_plane = int(M.Z2_OTHER_OLD_TO_NEW[old_layer])\n"
      "        orbit_plane[int(group['group_id'])] = dict(\n"
      "            old_layer=old_layer, new_plane=new_plane,\n"
      "            route_ids=[int(rid) for rid in group['route_ids']])\n"
      "        for rid in group['route_ids']:\n"
      "            route_plane[int(rid)] = new_plane\n"
      "        old_layer_counts[old_layer] += len(group['route_ids'])\n"
      "    return route_plane, orbit_plane, dict(sorted(old_layer_counts.items()))\n",
      "def _z2_other_allocation(baseline, z2_orbits):\n"
      '    """Whole C4 ``adjacent`` Z2 orbits -> new planes of the active profile.\n'
      "\n"
      "    The allocation policy itself lives in the height model (it depends on\n"
      "    how many Z2 ``other`` planes survive):\n"
      "\n"
      "    * 21 heights: 1:1 baseline old-layer -> new-plane map\n"
      "      (``model.Z2_OTHER_OLD_TO_NEW``);\n"
      "    * 20 heights: explicit whole-orbit plan over 7 planes\n"
      "      (``model.Z2_OTHER_PLAN``) because L19 no longer exists.\n"
      '    """\n'
      "    return M.allocate_z2_other(z2_orbits, baseline['by_id'])\n")

patch('assign21.py: all-planes-used check reads the profile count',
      "    add('all_21_planes_used',\n"
      "        len(plane_counts) == 21 and all(plane_counts[plane_id] > 0\n"
      "                                       for plane_id in M.PLANE_IDS),\n"
      "        dict(planes_used=len(plane_counts)), 'all 21 routing heights used')\n"
      "    add('height_count_21_distinct', len(heights) == 21,\n"
      "        dict(distinct_heights=sorted(heights)), '21 distinct physical heights')\n",
      "    add('all_model_planes_used',\n"
      "        len(plane_counts) == len(M.PLANE_IDS)\n"
      "        and all(plane_counts[plane_id] > 0 for plane_id in M.PLANE_IDS),\n"
      "        dict(planes_used=len(plane_counts), expected=len(M.PLANE_IDS)),\n"
      "        'every routing height of the active profile is used')\n"
      "    add('height_count_distinct', len(heights) == len(M.PLANE_IDS),\n"
      "        dict(distinct_heights=sorted(heights), expected=len(M.PLANE_IDS)),\n"
      "        'one distinct physical height per model plane (no coincident z)')\n")

patch('assign21.py: z2 other counts check id',
      "    add('z2_other_counts_48_48_48_52_52_52_52_48',\n"
      "        dict(z2_other_counts) == dict(EXPECTED_Z2_OTHER_COUNTS),\n"
      "        dict(z2_other_counts),\n"
      "        'Z2 other 48/48/48/52/52/52/52/48 via the old-layer mapping')\n",
      "    add('z2_other_counts_match_contract',\n"
      "        dict(z2_other_counts) == dict(EXPECTED_Z2_OTHER_COUNTS),\n"
      "        dict(z2_other_counts),\n"
      "        'Z2 other per-plane counts equal the active profile contract')\n")

patch('assign21.py: z2 orbits follow the profile plan',
      "    z2_orbit_ok = True\n"
      "    z2_detail = []\n"
      "    for group_id, info in state['z2_orbit_plane'].items():\n"
      "        planes = {plane_by_route[int(rid)] for rid in info['route_ids']}\n"
      "        expected = int(M.Z2_OTHER_OLD_TO_NEW[info['old_layer']])\n"
      "        ok = planes == {expected}\n"
      "        z2_orbit_ok = z2_orbit_ok and ok\n"
      "        if not ok:\n"
      "            z2_detail.append(dict(c4_group_id=group_id,\n"
      "                                  planes=sorted(planes), expected=expected))\n"
      "    add('z2_other_orbits_follow_old_layer_map', z2_orbit_ok, z2_detail[:10],\n"
      "        'Z2 other whole orbits remapped by their baseline old target layer')\n",
      "    z2_orbit_ok = True\n"
      "    z2_detail = []\n"
      "    z2_plane_orbits = collections.Counter()\n"
      "    for group_id, info in state['z2_orbit_plane'].items():\n"
      "        planes = {plane_by_route[int(rid)] for rid in info['route_ids']}\n"
      "        expected = int(info['new_plane'])\n"
      "        z2_plane_orbits[int(expected)] += 1\n"
      "        ok = planes == {expected}\n"
      "        z2_orbit_ok = z2_orbit_ok and ok\n"
      "        if not ok:\n"
      "            z2_detail.append(dict(c4_group_id=group_id,\n"
      "                                  planes=sorted(planes), expected=expected))\n"
      "    add('z2_other_orbits_follow_profile_plan', z2_orbit_ok, z2_detail[:10],\n"
      "        'every Z2 other whole orbit stays on the single plane the active '\n"
      "        'profile allocation assigned to it')\n"
      "    expected_z2_orbits = collections.Counter()\n"
      "    if getattr(M, 'Z2_OTHER_PLAN', None):\n"
      "        for plane_id, capacity in M.Z2_OTHER_PLAN:\n"
      "            expected_z2_orbits[int(plane_id)] += int(capacity)\n"
      "    else:\n"
      "        for old_layer, new_plane in M.Z2_OTHER_OLD_TO_NEW.items():\n"
      "            expected_z2_orbits[int(new_plane)] += int(M.CONTRACT_OLD_LAYER_COUNTS[int(old_layer)] / 4)\n"
      "    add('z2_other_orbit_plan_exhaustive',\n"
      "        sum(z2_plane_orbits.values()) == len(state['z2_adjacent_groups'])\n"
      "        and dict(z2_plane_orbits) == dict(expected_z2_orbits),\n"
      "        dict(assigned=dict(z2_plane_orbits),\n"
      "             expected=dict(expected_z2_orbits)),\n"
      "        'the whole-orbit plan consumes exactly the 100 Z2 adjacent orbits')\n")

# schema names in assign21 payloads
patch('assign21.py: audit schema',
      "        schema='reheight21_assignment_audit_v1',",
      "        schema=M.SCHEMA_ASSIGNMENT_AUDIT,")
patch('assign21.py: diff schema',
      "        schema='reheight21_assignment_diff_vs_baseline_v1',",
      "        schema=M.SCHEMA_ASSIGNMENT_DIFF,")
patch('assign21.py: experiment A schema',
      "        schema='reheight21_experiment_A_summary_v1',",
      "        schema=M.SCHEMA_EXPERIMENT_A,")
patch('assign21.py: model name in audit',
      "        model='reheight21.model',",
      "        model=getattr(M, 'MODEL_NAME', 'reheight21.model'),", count=2)

# ===========================================================================
# run21.py -- stage A expectations from the profile
# ===========================================================================
patch('run21.py: stage A expected counts',
      "    expected_counts = {\n"
      "        2: 64, 3: 64, 4: 64, 5: 64, 6: 52, 7: 52, 20: 52, 1001: 52, 8: 48,\n"
      "        9: 48, 10: 16, 11: 16, 12: 40, 13: 40, 14: 48, 15: 48, 16: 52,\n"
      "        1002: 48, 17: 52, 18: 52, 19: 52,\n"
      "    }\n",
      "    expected_counts = dict(M.CONTRACT_PLANE_COUNTS)\n")
patch('run21.py: stage A distinct heights',
      "    heights = {round(M.plane_z(pid), 9) for pid in M.PLANE_IDS}\n"
      "    if len(heights) != 21:\n"
      "        raise ValueError(f'expected 21 distinct heights, got {sorted(heights)}')\n"
      "    if len(direct) != 100:\n"
      "        raise ValueError(f'expected 100 interface-direct rows, got {len(direct)}')\n",
      "    heights = {round(M.plane_z(pid), 9) for pid in M.PLANE_IDS}\n"
      "    if len(heights) != len(M.PLANE_IDS):\n"
      "        raise ValueError(f'expected {len(M.PLANE_IDS)} distinct heights, '\n"
      "                         f'got {sorted(heights)}')\n"
      "    if len(direct) != int(M.CONTRACT_DIRECT_ROUTES['total']):\n"
      "        raise ValueError(f'expected {M.CONTRACT_DIRECT_ROUTES[\"total\"]} '\n"
      "                         f'interface-direct rows, got {len(direct)}')\n")
patch('run21.py: stage A log line',
      "    log(f'stage A ok: rows={len(rows)} planes={dict(planes)} '\n"
      "        f'roles={dict(roles)} direct={len(direct)} heights=21')\n",
      "    log(f'stage A ok: rows={len(rows)} planes={dict(planes)} '\n"
      "        f'roles={dict(roles)} direct={len(direct)} heights={len(heights)}')\n")

# ===========================================================================
# validate21.py -- SPEC tables read from the active profile
# ===========================================================================
patch('validate21.py: import the active model',
      "from .. import common\n",
      "from .. import common\nfrom . import model as M\n")
patch('validate21.py: RUN_DIR default follows the profile',
      "RUN_DIR_21H = OUTPUT_ROOT / 'FANOUT_FIRST_21_HEIGHT_REBALANCED_1024'\n",
      "RUN_DIR_21H = Path(getattr(M, 'RUN_DIR',\n"
      "                           OUTPUT_ROOT / 'FANOUT_FIRST_21_HEIGHT_REBALANCED_1024'))\n")
patch('validate21.py: SPEC body heights from the profile',
      "SPEC_BODY_HEIGHTS = OrderedDict([\n"
      "    (2, -0.35), (3, -0.30), (4, -0.25), (5, -0.20), (6, -0.15), (7, -0.10),\n"
      "    (20, -0.05), (8, 0.05), (9, 0.10), (10, 0.15), (11, 0.20), (12, 0.25),\n"
      "    (13, 0.30), (14, 0.35), (15, 0.40), (16, 0.45), (17, 0.55), (18, 0.60),\n"
      "    (19, 0.65),\n"
      "])\n"
      "SPEC_INTERFACE_PLANES = OrderedDict([\n"
      "    (1001, dict(label='Z1_INTERFACE', z_mm=0.0, interface='z1',\n"
      "                level=common.Z1_INTERFACE_MM)),\n"
      "    (1002, dict(label='Z2_INTERFACE', z_mm=0.5, interface='z2',\n"
      "                level=common.Z2_INTERFACE_MM)),\n"
      "])\n"
      "SPEC_INTERFACE_IDS = set(SPEC_INTERFACE_PLANES)\n"
      "SPEC_MANUAL_FIXED = OrderedDict([\n"
      "    ('Z1-U1', 2), ('Z1-U2', 3), ('Z1-U3', 4), ('Z1-U4', 5),\n"
      "    ('Z2-U1', 10), ('Z2-U2', 11), ('Z2-U3', 12), ('Z2-U4', 13),\n"
      "])\n"
      "#: SPEC.md section 2: exact per-plane assigned route counts\n"
      "SPEC_EXPECTED_ASSIGNED = OrderedDict([\n"
      "    (2, 64), (3, 64), (4, 64), (5, 64),\n"
      "    (6, 52), (7, 52), (20, 52), (1001, 52), (8, 48),\n"
      "    (10, 16), (11, 16), (12, 40), (13, 40),\n"
      "    (9, 48), (14, 48), (15, 48), (16, 52), (17, 52), (18, 52),\n"
      "    (19, 52), (1002, 48),\n"
      "])\n"
      "SPEC_DIRECT_TOTAL = 100\n"
      "SPEC_DIRECT_BY_PLANE = {1001: 52, 1002: 48}\n",
      "#: ---- configuration expectations of the ACTIVE height profile ---------\n"
      "#: (the 21-height values are frozen in ``model.SPEC_*``; the 20-height\n"
      "#: profile supplies its own table and the very same checks are applied)\n"
      "SPEC_BODY_HEIGHTS = OrderedDict(M.SPEC_BODY_HEIGHTS)\n"
      "SPEC_INTERFACE_PLANES = OrderedDict(M.SPEC_INTERFACE_PLANES)\n"
      "SPEC_INTERFACE_IDS = set(M.SPEC_INTERFACE_IDS)\n"
      "SPEC_MANUAL_FIXED = OrderedDict(M.SPEC_MANUAL_FIXED)\n"
      "SPEC_EXPECTED_ASSIGNED = OrderedDict(M.SPEC_EXPECTED_ASSIGNED)\n"
      "SPEC_DIRECT_TOTAL = int(M.SPEC_DIRECT_TOTAL)\n"
      "SPEC_DIRECT_BY_PLANE = dict(M.SPEC_DIRECT_BY_PLANE)\n"
      "SPEC_BODY_PLANE_COUNT = int(M.SPEC_BODY_PLANE_COUNT)\n"
      "SPEC_PLANE_COUNT = int(M.SPEC_PLANE_COUNT)\n")
patch('validate21.py: model plane count expectation',
      "                   expected_plane_count=(18 if baseline_mode else 21),\n",
      "                   expected_plane_count=(18 if baseline_mode\n"
      "                                         else SPEC_PLANE_COUNT),\n")
patch('validate21.py: plane count check',
      "        if details['plane_count'] != 21:\n"
      "            violations.append(dict(kind='plane_count_not_21',\n"
      "                                   detail=f'{details[\"plane_count\"]}'))\n"
      "        if details['body_plane_count'] != 19:\n"
      "            violations.append(dict(kind='body_plane_count_not_19',\n"
      "                                   detail=f'{details[\"body_plane_count\"]}'))\n",
      "        if details['plane_count'] != SPEC_PLANE_COUNT:\n"
      "            violations.append(dict(kind='plane_count_mismatch',\n"
      "                                   detail=f'{details[\"plane_count\"]} != '\n"
      "                                          f'{SPEC_PLANE_COUNT}'))\n"
      "        if details['body_plane_count'] != SPEC_BODY_PLANE_COUNT:\n"
      "            violations.append(dict(kind='body_plane_count_mismatch',\n"
      "                                   detail=f'{details[\"body_plane_count\"]}'\n"
      "                                          f' != {SPEC_BODY_PLANE_COUNT}'))\n")
patch('validate21.py: assignment used-planes check',
      "        if len(plane_counts) != 21:\n"
      "            violations.append(dict(kind='assignment_used_planes_not_21',\n"
      "                                   detail=f'{len(plane_counts)}'))\n",
      "        if len(plane_counts) != SPEC_PLANE_COUNT:\n"
      "            violations.append(dict(\n"
      "                kind='assignment_used_planes_mismatch',\n"
      "                detail=f'{len(plane_counts)} != {SPEC_PLANE_COUNT}'))\n")
patch('validate21.py: crossings audited-planes check',
      "            if audited != 21:\n"
      "                contract_violations.append(_violation(\n"
      "                    'crossings', 'planes_audited_count_not_21',\n"
      "                    detail=f'audited={audited}'))\n",
      "            if audited != SPEC_PLANE_COUNT:\n"
      "                contract_violations.append(_violation(\n"
      "                    'crossings', 'planes_audited_count_mismatch',\n"
      "                    detail=f'audited={audited} != {SPEC_PLANE_COUNT}'))\n")
patch('validate21.py: model plane count contract check',
      "        if model_details.get('plane_count') != 21:\n"
      "            contract_violations.append(_violation(\n"
      "                'model', 'model_plane_count_not_21',\n"
      "                detail=f'{model_details.get(\"plane_count\")}'))\n",
      "        if model_details.get('plane_count') != SPEC_PLANE_COUNT:\n"
      "            contract_violations.append(_violation(\n"
      "                'model', 'model_plane_count_mismatch',\n"
      "                detail=f'{model_details.get(\"plane_count\")} '\n"
      "                       f'!= {SPEC_PLANE_COUNT}'))\n")


def main():
    changed = {}
    failures = []
    for item in PATCHES:
        path = PKG / item['name'].split(':')[0]
        text = path.read_text(encoding='utf-8')
        found = text.count(item['old'])
        if found != item['count']:
            failures.append((item['name'], found, item['count']))
            continue
        text = text.replace(item['old'], item['new'])
        path.write_text(text, encoding='utf-8')
        changed[path.name] = changed.get(path.name, 0) + 1
        print(f'OK   {item["name"]}  ({found} site(s))')
    if failures:
        print('\nFAILURES:')
        for name, found, want in failures:
            print(f'  {name}: found {found}, expected {want}')
        return 1
    print('\nfiles changed:', changed)
    return 0


if __name__ == '__main__':
    sys.exit(main())
