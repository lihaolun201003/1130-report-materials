# -*- coding: utf-8 -*-
"""Authoritative **20-height** layer-plane model for the cold-start rebuild.

This module is the single source of truth for the new
``experiments/COLD_START_20_HEIGHT_1024`` experiment.  It exposes *exactly* the
same public API as :mod:`four_side_1024.fanout1024.reheight21.model` (the frozen
21-height model) so that the whole existing pipeline -- ``assign21``,
``run21``, ``validate21``, ``fanout``, ``layer2d``, ``assemble``, ``nonc4``,
``native3d``, ``xyzrouter``, ``xyzrouter.g4`` -- can be driven unchanged by
installing this module under the ``reheight21.model`` key at import time (see
:mod:`four_side_1024.fanout1024.coldstart20.bootstrap`).

Physical change (the only geometric input that changed)
-------------------------------------------------------
The frozen 21-height model used 21 routing heights at a 50 um pitch:

    -0.350, -0.300, ..., -0.050, 0.000(z1), 0.050, ..., 0.500(z2), ..., 0.650

The 20-height model:

* **deletes** plane ``L19`` (old plane id 19, old z = +0.650 mm);
* **raises every remaining height by +0.025 mm**;
* keeps every surviving ``plane_id`` as its identity label.

Resulting 20 routing heights (18 body planes + 2 routable interface planes)::

    plane_id  label          z (mm)   kind             role
         2    L2            -0.325     body             Z1-U1 (manual, fixed)
         3    L3            -0.275     body             Z1-U2 (manual, fixed)
         4    L4            -0.225     body             Z1-U3 (manual, fixed)
         5    L5            -0.175     body             Z1-U4 (manual, fixed)
         6    L6            -0.125     body             Z1 other opposite
         7    L7            -0.075     body             Z1 other opposite
        20    L20           -0.025     body             Z1 other opposite
      1001    Z1_INTERFACE  +0.025     interface_body   Z1 other opposite (direct 2D)
         8    L8            +0.075     body             Z1 other opposite
         9    L9            +0.125     body             Z2 other adjacent
        10    L10           +0.175     body             Z2-U1 (manual, fixed)
        11    L11           +0.225     body             Z2-U2 (manual, fixed)
        12    L12           +0.275     body             Z2-U3 (manual, fixed)
        13    L13           +0.325     body             Z2-U4 (manual, fixed)
        14    L14           +0.375     body             Z2 other adjacent
        15    L15           +0.425     body             Z2 other adjacent
        16    L16           +0.475     body             Z2 other adjacent
      1002    Z2_INTERFACE  +0.525     interface_body   Z2 other adjacent (direct 2D)
        17    L17           +0.575     body             Z2 other adjacent
        18    L18           +0.625     body             Z2 other adjacent

The glass envelope is unchanged: ``z in [-0.350, +0.650]`` mm, 1.000 mm thick.
The neighbour pitch is still exactly 50 um and the lowest/highest planes sit
25 um inside the glass surfaces (the 21-height model had L2/L19 *on* the
surfaces).

What is a *configuration* change and what is NOT
------------------------------------------------
Changed (configuration only, see ``01_height_config/``):

* the plane height table, the interface heights, the plane identity set;
* the Z2 "other" family allocation plan (100 C4 orbits over 7 planes instead
  of 8) and the derived per-plane expected counts;
* the writable output directories and payload schema names.

**Not** changed (never relaxed): R15 = 15 mm, 50 um true-3D centre-line
clearance, strict same-layer D56 rule (0.05 mm width + 0.03 mm edge gap, legal
transverse crossings), the 150x150x1 mm glass, the 1024 fixed connections and
the manual U group membership/plane ids.  Every threshold constant below is
bit-identical to the frozen 21-height model and is re-asserted by
``coldstart20.tests_model20``.
"""
from __future__ import annotations

import collections
from pathlib import Path

from .. import common as C
from ...l3d.layers import INTERFACE_LAYER_ID, build_stack

# ================================================================ run paths
ROOT = C.ROOT
OUTPUT_ROOT = C.OUTPUT_ROOT

#: the frozen 18-layer baseline (READ-ONLY input: assignment + manual contract)
BASELINE_RUN_NAME = 'FANOUT_FIRST_Z2_MANUAL_VERIFIED_1024'
#: frozen 21-height baseline (READ-ONLY, comparison only)
BASELINE_21H_RUN_NAME = 'FANOUT_FIRST_21_HEIGHT_REBALANCED_1024'
#: logical name of this experiment (recorded inside every payload)
NEW_RUN_NAME = 'FANOUT_FIRST_20_HEIGHT_RAISED_1024'
EXPERIMENT_NAME = 'COLD_START_20_HEIGHT_1024'
PROFILE = '20_height_raised'
#: canonical ``model`` value written into payloads (same field the 21-height
#: model calls MODEL_NAME)
MODEL_NAME = 'coldstart20.model20'

#: the cold-start deliverable root
EXPERIMENT_ROOT = ROOT / 'experiments' / 'COLD_START_20_HEIGHT_1024'
#: this experiment's writable output directory (stage 03: fanout + XY + 3D)
RUN_DIR = EXPERIMENT_ROOT / '03_fanout_and_xy' / 'run_initial_20h'
#: frozen 18-layer baseline experiment (READ-ONLY, never written)
BASELINE_RUN_DIR = OUTPUT_ROOT / BASELINE_RUN_NAME
#: frozen 21-height baseline experiment (READ-ONLY, comparison only)
BASELINE_21H_RUN_DIR = OUTPUT_ROOT / BASELINE_21H_RUN_NAME

#: convenience aliases for the two run directories
NEW_RUN_DIR = RUN_DIR
OLD_RUN_DIR = BASELINE_RUN_DIR

#: baseline files that are read (never written) by the assignment / diff audit
BASE_ASSIGNMENT = BASELINE_RUN_DIR / 'assignment_1024.csv'
BASE_AUDIT_JSON = BASELINE_RUN_DIR / 'assignment_audit.json'
BASE_STACK_JSON = BASELINE_RUN_DIR / 'physical_layer_stack.json'
#: new-experiment deliverable paths
NEW_ASSIGNMENT = RUN_DIR / 'assignment_1024.csv'
NEW_ASSIGNMENT_AUDIT = RUN_DIR / 'assignment_audit.json'
NEW_ASSIGNMENT_DIFF_JSON = RUN_DIR / 'assignment_diff_vs_baseline.json'
NEW_ASSIGNMENT_DIFF_MD = RUN_DIR / 'assignment_diff_vs_baseline.md'
LAYER_PLANES_JSON = RUN_DIR / 'layer_planes.json'
NEW_STACK_JSON = RUN_DIR / 'physical_layer_stack.json'
NEW_RULES_JSON = RUN_DIR / 'process_rules.json'
NEW_EXPERIMENT_A = RUN_DIR / 'experiment_A'
BASELINE_ASSIGNMENT_CSV = BASE_ASSIGNMENT
NEW_ASSIGNMENT_CSV = NEW_ASSIGNMENT
NEW_LAYER_PLANES_JSON = LAYER_PLANES_JSON
BASELINE_AUDIT_JSON = BASE_AUDIT_JSON
BASELINE_STACK_JSON = BASE_STACK_JSON

# ================================================================ geometry
#: ---- every one of these is IDENTICAL to the frozen 21-height model ----
GLASS_THICKNESS_MM = 1.000
GLASS_Z_MIN_MM = -0.35
GLASS_Z_MAX_MM = 0.65
MIN_LAYER_PITCH_MM = 0.05
MIN_3D_CLEARANCE_MM = 0.05
MIN_BEND_RADIUS_MM = 15.0
WIDTH_MM = C.WIDTH_MM                     # 0.05 mm
EDGE_GAP_MM = C.EDGE_GAP_MM               # 0.03 mm
CLEARANCE_2D_MM = C.CLEARANCE_2D_MM       # 0.08 mm same-layer centre line
#: ---- the only changed geometry: the interface heights ----
Z1_INTERFACE_MM = 0.025
Z2_INTERFACE_MM = 0.525

#: 18 body routing heights (plane_id -> z in mm), physical z order
BODY_PLANES = collections.OrderedDict([
    (2, -0.325), (3, -0.275), (4, -0.225), (5, -0.175),
    (6, -0.125), (7, -0.075), (20, -0.025),
    (8, 0.075), (9, 0.125), (10, 0.175), (11, 0.225), (12, 0.275),
    (13, 0.325), (14, 0.375), (15, 0.425), (16, 0.475),
    (17, 0.575), (18, 0.625),
])
BODY_PLANE_Z = BODY_PLANES      # backwards-compatible alias

#: the two interface planes are routable bodies (rows of the l3d interface L1)
INTERFACE_PLANES = collections.OrderedDict([
    (1001, dict(label='Z1_INTERFACE', z_mm=Z1_INTERFACE_MM, plane='z1')),
    (1002, dict(label='Z2_INTERFACE', z_mm=Z2_INTERFACE_MM, plane='z2')),
])
Z1_INTERFACE_PLANE_ID = 1001
Z2_INTERFACE_PLANE_ID = 1002
INTERFACE_PLANE_IDS = (Z1_INTERFACE_PLANE_ID, Z2_INTERFACE_PLANE_ID)

#: mapping of the interface planes onto the l3d stack interface layer L1
INTERFACE_STACK_ROWS = {Z1_INTERFACE_PLANE_ID: 'z1',
                        Z2_INTERFACE_PLANE_ID: 'z2'}

#: all 20 plane ids in physical z order (NOT id order; L19 is gone)
PLANE_IDS = (2, 3, 4, 5, 6, 7, 20, 1001, 8, 9, 10, 11, 12, 13, 14, 15, 16,
             1002, 17, 18)
PLANE_ORDER = PLANE_IDS              # backwards-compatible alias

PLANE_Z = collections.OrderedDict(
    [(plane_id, float(z_mm)) for plane_id, z_mm in BODY_PLANES.items()]
    + [(plane_id, float(spec['z_mm'])) for plane_id, spec
       in INTERFACE_PLANES.items()])
PLANE_Z = collections.OrderedDict((plane_id, PLANE_Z[plane_id])
                                  for plane_id in PLANE_IDS)

PLANE_LABEL = collections.OrderedDict()
for _plane_id in BODY_PLANES:
    PLANE_LABEL[_plane_id] = f'L{_plane_id}'
for _plane_id, _spec in INTERFACE_PLANES.items():
    PLANE_LABEL[_plane_id] = _spec['label']
PLANE_LABEL = collections.OrderedDict((plane_id, PLANE_LABEL[plane_id])
                                      for plane_id in PLANE_IDS)

PLANE_KIND = collections.OrderedDict(
    [(plane_id, 'body') for plane_id in BODY_PLANES]
    + [(plane_id, 'interface_body') for plane_id in INTERFACE_PLANES])
PLANE_KIND = collections.OrderedDict((plane_id, PLANE_KIND[plane_id])
                                     for plane_id in PLANE_IDS)

#: which interface owns the plane in this experiment's fixed allocation
PLANE_SIDE = collections.OrderedDict()
for _plane_id in PLANE_IDS:
    if _plane_id in (1001, 2, 3, 4, 5, 6, 7, 8, 20):
        PLANE_SIDE[_plane_id] = 'z1'
    else:
        PLANE_SIDE[_plane_id] = 'z2'

PLANE_ROLE_DETAIL = collections.OrderedDict([
    (2, 'Z1-U1'), (3, 'Z1-U2'), (4, 'Z1-U3'), (5, 'Z1-U4'),
    (6, 'Z1 other opposite'), (7, 'Z1 other opposite'),
    (20, 'Z1 other opposite'),
    (1001, 'Z1 other opposite (direct 2D)'),
    (8, 'Z1 other opposite'),
    (9, 'Z2 other adjacent'),
    (10, 'Z2-U1'), (11, 'Z2-U2'), (12, 'Z2-U3'), (13, 'Z2-U4'),
    (14, 'Z2 other adjacent'), (15, 'Z2 other adjacent'),
    (16, 'Z2 other adjacent'),
    (1002, 'Z2 other adjacent (direct 2D)'),
    (17, 'Z2 other adjacent'), (18, 'Z2 other adjacent'),
])

#: friendly alias: the descriptive role table (``role_detail``)
PLANE_ROLE = PLANE_ROLE_DETAIL

#: frozen layer-plan role taxonomy of the 20 planes
#: 'z1_manual_u' | 'z2_manual_u' | 'z1_other' | 'z2_other' |
#: 'interface_direct'
_MANUAL_PLANE_IDS_LAYOUT = (2, 3, 4, 5, 10, 11, 12, 13)
PLANE_LAYER_ROLE = collections.OrderedDict()
for _plane_id in PLANE_IDS:
    if _plane_id in (Z1_INTERFACE_PLANE_ID, Z2_INTERFACE_PLANE_ID):
        PLANE_LAYER_ROLE[_plane_id] = 'interface_direct'
    elif _plane_id in _MANUAL_PLANE_IDS_LAYOUT:
        PLANE_LAYER_ROLE[_plane_id] = (
            'z1_manual_u' if PLANE_SIDE[_plane_id] == 'z1'
            else 'z2_manual_u')
    else:
        PLANE_LAYER_ROLE[_plane_id] = (
            'z1_other' if PLANE_SIDE[_plane_id] == 'z1' else 'z2_other')

INTERFACE_Z = {'z1': Z1_INTERFACE_MM, 'z2': Z2_INTERFACE_MM}

#: fixed manual groups of the NEW experiment (plane ids unchanged, z +0.025)
MANUAL_GROUP_SPECS = collections.OrderedDict([
    ('Z1-U1', dict(plane='z1', plane_id=2, label='L2', z_mm=-0.325,
                   pattern='NS-first', sides='NS')),
    ('Z1-U2', dict(plane='z1', plane_id=3, label='L3', z_mm=-0.275,
                   pattern='NS-second', sides='NS')),
    ('Z1-U3', dict(plane='z1', plane_id=4, label='L4', z_mm=-0.225,
                   pattern='EW-first', sides='EW')),
    ('Z1-U4', dict(plane='z1', plane_id=5, label='L5', z_mm=-0.175,
                   pattern='EW-second', sides='EW')),
    ('Z2-U1', dict(plane='z2', plane_id=10, label='L10', z_mm=0.175,
                   pattern='NS-first', sides='NS')),
    ('Z2-U2', dict(plane='z2', plane_id=11, label='L11', z_mm=0.225,
                   pattern='EW-first', sides='EW')),
    ('Z2-U3', dict(plane='z2', plane_id=12, label='L12', z_mm=0.275,
                   pattern='NS-second', sides='NS')),
    ('Z2-U4', dict(plane='z2', plane_id=13, label='L13', z_mm=0.325,
                   pattern='EW-second', sides='EW')),
])

#: frozen public shape: group -> dict(plane, label, z_mm) plus convenience keys
MANUAL_GROUPS = collections.OrderedDict()
for _group, _spec in MANUAL_GROUP_SPECS.items():
    MANUAL_GROUPS[_group] = dict(
        plane=_spec['plane'], label=_spec['label'], z_mm=_spec['z_mm'],
        plane_id=_spec['plane_id'], layer=_spec['plane_id'],
        pattern=_spec['pattern'], sides=_spec['sides'])
MANUAL_LAYER_TO_GROUP = {spec['plane_id']: group
                         for group, spec in MANUAL_GROUPS.items()}
MANUAL_PLANE_IDS = tuple(spec['plane_id'] for spec in MANUAL_GROUPS.values())
MANUAL_ROLES = ('z1_manual_u', 'z2_manual_u')
Z1_GROUP_ORDER = ('Z1-U1', 'Z1-U2', 'Z1-U3', 'Z1-U4')
Z2_GROUP_ORDER = ('Z2-U1', 'Z2-U2', 'Z2-U3', 'Z2-U4')

#: whole-C4-orbit allocation plan for the Z1 ``opposite`` (other) routes:
#: 64 orbits sorted by rotation group_id, consumed in this order.
#: Identical to the frozen 21-height plan: all five planes survive.
Z1_OTHER_PLAN = ((6, 13), (7, 13), (20, 13), (1001, 13), (8, 12))

#: ---- 20-height specific: Z2 ``adjacent`` (other) allocation ---------------
#: 100 C4 orbits (400 routes) must be spread over the SEVEN non-manual Z2
#: planes that survive (9, 14, 15, 16, 1002, 17, 18).  The 21-height model
#: mapped eight baseline old layers 1:1 onto eight planes; with L19 deleted
#: one plane is missing, so the mapping is replaced by an explicit whole-orbit
#: plan: ``(plane_id, number_of_C4_orbits)`` consumed in ascending group_id
#: order.  Counts are multiples of 4 routes (one C4 orbit) -- 14 or 16 orbits.
#: 14*4 + 14*4 + 14*4 + 14*4 + 16*4 + 16*4 + 12*4 = 400 routes = 100 orbits.
Z2_OTHER_PLAN = ((9, 14), (14, 14), (15, 14), (16, 14),
                 (17, 16), (18, 16), (1002, 12))

#: legacy key kept for API compatibility: a 1:1 old-layer -> new-plane map does
#: not exist for 20 heights (one plane fewer).  ``None`` tells the frozen
#: ``reheight21.assign21`` allocation helper to use :data:`Z2_OTHER_PLAN`.
Z2_OTHER_OLD_TO_NEW = None
Z2_OLD_TO_NEW_PLANE = Z2_OTHER_OLD_TO_NEW     # backwards-compatible alias
Z2_LAYER_MAP = Z2_OTHER_OLD_TO_NEW            # convenience alias

#: baseline (18-layer) heights, kept only for the read-only diff audit
BASELINE_LAYER_Z = collections.OrderedDict(C.PHYSICAL_LAYERS)
BASELINE_LAYER_IDS = tuple(C.PHYSICAL_LAYERS)


# ================================================================ payload schema
SCHEMA_LAYER_PLANES = 'reheight20_layer_planes_v1'
SCHEMA_LAYER_STACK = 'reheight20_layer_stack_v1'
SCHEMA_PROCESS_RULES = 'reheight20_process_rules_v1'
SCHEMA_ASSIGNMENT_AUDIT = 'reheight20_assignment_audit_v1'
SCHEMA_ASSIGNMENT_DIFF = 'reheight20_assignment_diff_vs_baseline_v1'
SCHEMA_EXPERIMENT_A = 'reheight20_experiment_A_summary_v1'


# ================================================================ experiment contract
#: frozen SPEC.md section 2 for 20 heights: exact per-plane assigned route counts
CONTRACT_PLANE_COUNTS = collections.OrderedDict([
    (2, 64), (3, 64), (4, 64), (5, 64),
    (6, 52), (7, 52), (20, 52), (1001, 52), (8, 48),
    (9, 56), (10, 16), (11, 16), (12, 40), (13, 40),
    (14, 56), (15, 56), (16, 56), (17, 64), (18, 64), (1002, 48),
])
CONTRACT_Z2_OTHER_COUNTS = collections.OrderedDict([
    (9, 56), (14, 56), (15, 56), (16, 56), (17, 64), (18, 64), (1002, 48),
])
CONTRACT_DIRECT_ROUTES = dict(total=100, z1=52, z2=48)
CONTRACT_TRANSITION_ROUTES = 1024 - CONTRACT_DIRECT_ROUTES['total']      # 924
CONTRACT_ENDPOINT_TRANSITIONS = 2 * CONTRACT_TRANSITION_ROUTES          # 1848
CONTRACT_MANUAL_COUNTS = collections.OrderedDict([
    ('Z1-U1', 64), ('Z1-U2', 64), ('Z1-U3', 64), ('Z1-U4', 64),
    ('Z2-U1', 16), ('Z2-U2', 16), ('Z2-U3', 40), ('Z2-U4', 40),
])
CONTRACT_MANUAL_TOTAL = sum(CONTRACT_MANUAL_COUNTS.values())            # 368
CONTRACT_MANUAL_ORBIT_PLANE_SETS = {
    (2, 4): 32, (3, 5): 32, (10, 11): 8, (12, 13): 20,
}

#: independent validator expectation tables (frozen SPEC copies)
SPEC_BODY_HEIGHTS = collections.OrderedDict(
    [(int(plane_id), float(z_mm)) for plane_id, z_mm in BODY_PLANES.items()])
SPEC_INTERFACE_PLANES = collections.OrderedDict([
    (1001, dict(label='Z1_INTERFACE', z_mm=Z1_INTERFACE_MM, interface='z1',
                level=Z1_INTERFACE_MM)),
    (1002, dict(label='Z2_INTERFACE', z_mm=Z2_INTERFACE_MM, interface='z2',
                level=Z2_INTERFACE_MM)),
])
SPEC_INTERFACE_IDS = set(SPEC_INTERFACE_PLANES)
SPEC_MANUAL_FIXED = collections.OrderedDict([
    ('Z1-U1', 2), ('Z1-U2', 3), ('Z1-U3', 4), ('Z1-U4', 5),
    ('Z2-U1', 10), ('Z2-U2', 11), ('Z2-U3', 12), ('Z2-U4', 13),
])
SPEC_EXPECTED_ASSIGNED = collections.OrderedDict(CONTRACT_PLANE_COUNTS)
SPEC_DIRECT_TOTAL = CONTRACT_DIRECT_ROUTES['total']
SPEC_DIRECT_BY_PLANE = {1001: CONTRACT_DIRECT_ROUTES['z1'],
                        1002: CONTRACT_DIRECT_ROUTES['z2']}
SPEC_BODY_PLANE_COUNT = len(BODY_PLANES)                                 # 18
SPEC_PLANE_COUNT = len(PLANE_IDS)                                        # 20

#: expected baseline (18-layer, READ-ONLY) old-layer route counts of the
#: Z2 ``other`` family; identical to the frozen 21-height expectation because
#: the baseline itself never changes.
CONTRACT_OLD_LAYER_COUNTS = collections.OrderedDict([
    (8, 48), (9, 48), (14, 48), (15, 52), (16, 52), (17, 52), (18, 52),
    (19, 48),
])


# ================================================================ helpers
_STACK = None


def _as_plane_id(plane_id):
    """Accept int ids, numeric strings, ``'L20'`` or ``'Z1_INTERFACE'``."""
    if isinstance(plane_id, str):
        text = plane_id.strip()
        lowered = text.lower()
        for known_id, spec in INTERFACE_PLANES.items():
            if lowered in (str(known_id).lower(), spec['label'].lower()):
                return known_id
        if lowered.startswith('l') and lowered[1:].isdigit():
            return int(lowered[1:])
        if lowered.isdigit() or (lowered.startswith('-')
                                 and lowered[1:].isdigit()):
            return int(lowered)
        raise KeyError(f'unknown plane id/label {plane_id!r}')
    return int(plane_id)


def all_plane_ids():
    """The 20 plane ids in physical z order (alias of :data:`PLANE_IDS`)."""
    return tuple(PLANE_IDS)


def planes():
    """Ordered metadata of the 20 routing heights, in physical z order."""
    result = collections.OrderedDict()
    for index, plane_id in enumerate(PLANE_IDS):
        spec = dict(
            plane_id=int(plane_id),
            label=PLANE_LABEL[plane_id],
            z_mm=float(PLANE_Z[plane_id]),
            kind=PLANE_KIND[plane_id],
            role=PLANE_LAYER_ROLE[plane_id],
            role_detail=PLANE_ROLE_DETAIL[plane_id],
            side=PLANE_SIDE[plane_id],
            order_index=index,
            is_interface=plane_id in INTERFACE_PLANES,
            is_direct=plane_id in INTERFACE_PLANES,
        )
        if plane_id in INTERFACE_PLANES:
            spec.update(dict(
                plane=INTERFACE_PLANES[plane_id]['plane'],
                stack_layer=INTERFACE_LAYER_ID,
                interface_row=INTERFACE_STACK_ROWS[plane_id],
            ))
        else:
            spec.update(dict(plane=None, stack_layer=int(plane_id),
                             interface_row=None))
        result[plane_id] = spec
    return result


def body_plane_ids():
    """The 18 body routing plane ids in z order."""
    return tuple(plane_id for plane_id in PLANE_IDS
                 if plane_id not in INTERFACE_PLANES)


def is_interface_plane(plane_id):
    return _as_plane_id(plane_id) in INTERFACE_PLANES


def is_direct_plane(plane_id):
    """True for the two routable interface heights (1001 / 1002)."""
    return _as_plane_id(plane_id) in INTERFACE_PLANES


def plane_z(plane_id):
    """Physical z (mm) of any of the 20 routing heights."""
    return float(PLANE_Z[_as_plane_id(plane_id)])


def plane_label(plane_id):
    """Human label: ``L2``..``L18``, ``L20``, ``Z1_INTERFACE``, ``Z2_INTERFACE``."""
    return PLANE_LABEL[_as_plane_id(plane_id)]


def plane_kind(plane_id):
    """``'body'`` or ``'interface_body'``."""
    return PLANE_KIND[_as_plane_id(plane_id)]


def plane_side(plane_id):
    """``'z1'`` or ``'z2'``: which interface owns this height."""
    return PLANE_SIDE[_as_plane_id(plane_id)]


def plane_role(plane_id):
    """Frozen layer-plan role taxonomy of the plane."""
    return PLANE_LAYER_ROLE[_as_plane_id(plane_id)]


def plane_role_detail(plane_id):
    """Human detail role of the plane (e.g. ``Z1-U1`` / ``Z1 other opposite``)."""
    return PLANE_ROLE_DETAIL[_as_plane_id(plane_id)]


def interface_z(plane):
    """Interface height of a plane name/id: ``'z1'->+0.025``, ``'z2'->+0.525``.

    Also accepts the interface plane ids 1001/1002 (returns their own height).
    """
    if isinstance(plane, str):
        text = plane.strip().lower()
        if text in INTERFACE_Z:
            return float(INTERFACE_Z[text])
        return plane_z(_as_plane_id(plane))
    try:
        plane_id = int(plane)
    except (TypeError, ValueError):
        raise KeyError(f'unknown interface plane {plane!r}')
    if plane_id in INTERFACE_PLANES:
        return float(INTERFACE_PLANES[plane_id]['z_mm'])
    raise KeyError(f'unknown interface plane {plane!r}')


def interface_plane_for(plane):
    """Interface plane id of ``'z1'``/``'z2'``: z1 -> 1001, z2 -> 1002."""
    if isinstance(plane, str):
        text = plane.strip().lower()
        if text in ('z1', '1001'):
            return Z1_INTERFACE_PLANE_ID
        if text in ('z2', '1002'):
            return Z2_INTERFACE_PLANE_ID
        raise KeyError(f'unknown interface plane {plane!r}')
    plane_id = int(plane)
    if plane_id in INTERFACE_PLANES:
        return plane_id
    if plane_id in (1,):
        raise KeyError('interface layer id is ambiguous; use z1/z2')
    raise KeyError(f'unknown interface plane {plane!r}')


#: backwards-compatible alias
interface_plane_id = interface_plane_for


def needs_transition(plane_id, interface_plane=None):
    """True unless the target height IS the route's interface height."""
    target_z = plane_z(plane_id)
    if interface_plane is None:
        interface_plane = plane_side(plane_id)
    return abs(target_z - interface_z(interface_plane)) > 1e-12


def direction_for(plane_id, interface_plane=None):
    """``'direct'``, ``'down'`` or ``'up'`` per SPEC.md section 2."""
    target_z = plane_z(plane_id)
    if interface_plane is None:
        interface_plane = plane_side(plane_id)
    interface = interface_z(interface_plane)
    if abs(target_z - interface) <= 1e-12:
        return 'direct'
    return 'down' if target_z < interface else 'up'


# drop-in name used by modules that used ``common.layer_z`` before
layer_z = plane_z


def manual_group_plane(group):
    """Fixed plane id of a manual group (``Z1-U1``..``Z2-U4``)."""
    return int(MANUAL_GROUP_SPECS[str(group)]['plane_id'])


def min_height_pitch(plane_ids=None):
    """Smallest physical gap between the (given) routing heights."""
    ids = tuple(plane_ids) if plane_ids is not None else tuple(PLANE_IDS)
    heights = sorted(plane_z(plane_id) for plane_id in ids)
    if len(heights) < 2:
        return float('inf')
    return min(b - a for a, b in zip(heights, heights[1:]))


def ceil_distance_to_glass(z_mm):
    """Smallest distance from a routing height to either glass surface (mm)."""
    return min(float(z_mm) - GLASS_Z_MIN_MM, GLASS_Z_MAX_MM - float(z_mm))


# ================================================================ allocation
def allocate_z2_other(z2_orbits, baseline_by_id):
    """Allocate the 100 Z2 ``adjacent`` C4 orbits over the 7 surviving planes.

    ``z2_orbits`` is the ascending-``group_id`` list of C4 orbit records of the
    Z2 ``adjacent`` family; ``baseline_by_id`` is the READ-ONLY baseline
    assignment (``route_id -> row``) used only for the old-layer bookkeeping.

    Returns ``(route_plane, orbit_plane, old_layer_counts)`` -- exactly the
    triple the frozen :func:`reheight21.assign21._z2_other_allocation` returns,
    so the caller is unchanged.
    """
    plan = list(Z2_OTHER_PLAN)
    route_plane = {}
    orbit_plane = collections.OrderedDict()
    old_layer_counts = collections.Counter()
    index = 0
    for plane_id, capacity in plan:
        for _ in range(int(capacity)):
            if index >= len(z2_orbits):
                raise ValueError('20-height Z2 other plan exceeds the orbit '
                                 'count (need 100 orbits)')
            group = z2_orbits[index]
            index += 1
            old_layers = {int(float(baseline_by_id[int(rid)]['target_layer']))
                          for rid in group['route_ids']}
            if len(old_layers) != 1:
                raise ValueError(f'z2 orbit {group["group_id"]}: baseline old '
                                 f'layers not unique: {sorted(old_layers)}')
            old_layer = old_layers.pop()
            orbit_plane[int(group['group_id'])] = dict(
                old_layer=old_layer, new_plane=int(plane_id),
                route_ids=[int(rid) for rid in group['route_ids']])
            for rid in group['route_ids']:
                route_plane[int(rid)] = int(plane_id)
            old_layer_counts[old_layer] += len(group['route_ids'])
    if index != len(z2_orbits):
        raise ValueError('20-height Z2 other plan does not consume all orbits')
    return route_plane, orbit_plane, dict(sorted(old_layer_counts.items()))


# ================================================================ stack
def layer_stack():
    """``l3d.layers.LayerStack`` for the 20-height model.

    Interface layer L1 keeps *both* interface rows (now z=+0.025 / +0.525);
    the 18 body planes are routing layers keyed by their ``plane_id``
    (2..18 and 20 -- the identity id 19 no longer exists, so the routing id
    set is intentionally not contiguous; physical ordering is always taken
    from ``z``).
    """
    global _STACK
    if _STACK is None:
        _STACK = build_stack(
            'reheight20',
            heights={int(plane_id): float(z_mm)
                     for plane_id, z_mm in BODY_PLANES.items()},
            interface_rows=dict(INTERFACE_Z),
            note='20-height raised model: 18 body planes + routable Z1/Z2 '
                 'interface planes; L19 removed, every surviving height '
                 '+0.025 mm; 50 um minimum pitch')
    return _STACK


#: backwards-compatible alias
stack = layer_stack


def reset_stack():
    """Drop the cached stack (profile switch / tests only)."""
    global _STACK
    _STACK = None
    return None


def raw_stack_payload():
    """Raw ``l3d`` stack dict (interface L1 + 18 body layers)."""
    return layer_stack().to_dict()


# ================================================================ payloads
def write_json(path, obj):
    """Deterministic JSON writer (delegates to :func:`common.write_json`)."""
    return C.write_json(path, obj)


def _assigned_counts_from_disk(assigned=None):
    """Per-plane assigned route counts: explicit mapping or NEW assignment read."""
    if assigned is not None:
        return {int(plane_id): int(count)
                for plane_id, count in dict(assigned).items()}
    try:
        if NEW_ASSIGNMENT.is_file():
            rows, _digest = C.read_csv_rows(NEW_ASSIGNMENT)
            counts = collections.Counter()
            for row in rows:
                counts[int(float(row['target_layer']))] += 1
            return dict(counts)
    except Exception:  # guarded read: never let the fallback payload fail
        pass
    return {}


def layer_planes_payload(assigned=None):
    """``layer_planes.json`` contract: the 20 routing heights + metadata."""
    counts = _assigned_counts_from_disk(assigned)
    plane_entries = []
    for plane_id in PLANE_IDS:
        plane_entries.append(dict(
            plane_id=int(plane_id),
            label=PLANE_LABEL[plane_id],
            z_mm=float(PLANE_Z[plane_id]),
            kind=PLANE_KIND[plane_id],
            role=PLANE_LAYER_ROLE[plane_id],
            role_detail=PLANE_ROLE_DETAIL[plane_id],
            side=PLANE_SIDE[plane_id],
            is_interface=plane_id in INTERFACE_PLANES,
            assigned=int(counts.get(int(plane_id), 0)),
        ))
    assigned_total = sum(entry['assigned'] for entry in plane_entries)
    return dict(
        schema=SCHEMA_LAYER_PLANES,
        profile=PROFILE,
        experiment=EXPERIMENT_NAME,
        model=MODEL_NAME,
        baseline_run_dir=str(BASELINE_RUN_DIR),
        glass=dict(thickness_mm=GLASS_THICKNESS_MM,
                   z_min_mm=GLASS_Z_MIN_MM, z_max_mm=GLASS_Z_MAX_MM),
        interfaces=dict(INTERFACE_Z),
        interface_planes={str(plane_id): dict(INTERFACE_PLANES[plane_id])
                          for plane_id in INTERFACE_PLANE_IDS},
        plane_count=len(PLANE_IDS),
        body_plane_count=len(BODY_PLANES),
        height_count=len({round(plane_z(plane_id), 9)
                          for plane_id in PLANE_IDS}),
        min_pitch_mm=MIN_LAYER_PITCH_MM,
        measured_min_pitch_mm=min_height_pitch(),
        min_pitch_check=dict(minimum=min_height_pitch(),
                             required=MIN_LAYER_PITCH_MM,
                             passed=min_height_pitch()
                             >= MIN_LAYER_PITCH_MM - 1e-9),
        body_planes={str(plane_id): float(z_mm)
                     for plane_id, z_mm in BODY_PLANES.items()},
        planes=plane_entries,
        plane_order=[int(plane_id) for plane_id in PLANE_IDS],
        interface_plane_ids=[int(plane_id)
                             for plane_id in INTERFACE_PLANE_IDS],
        assigned_total=assigned_total,
        assigned_by_role=dict(sorted(collections.Counter(
            entry['role'] for entry in plane_entries
            if entry['assigned'] > 0).items())),
        manual_groups={group: dict(plane=spec['plane'], label=spec['label'],
                                   z_mm=spec['z_mm'],
                                   plane_id=spec['plane_id'])
                       for group, spec in MANUAL_GROUPS.items()},
        z1_other_plan=[[int(plane_id), int(orbits)]
                       for plane_id, orbits in Z1_OTHER_PLAN],
        z2_other_plan=[[int(plane_id), int(orbits)]
                       for plane_id, orbits in Z2_OTHER_PLAN],
        z2_other_old_to_new=None,
        removed_plane=dict(plane_id=19, old_z_mm=0.65,
                           reason='20-height model: L19 deleted'),
        height_shift_mm=0.025,
        min_layer_pitch_mm=MIN_LAYER_PITCH_MM,
    )


def stack_payload():
    """``physical_layer_stack.json`` payload (new stack + 20-height metadata)."""
    payload = raw_stack_payload()
    payload.update(dict(
        schema=SCHEMA_LAYER_STACK,
        profile=PROFILE,
        experiment=EXPERIMENT_NAME,
        model=MODEL_NAME,
        baseline_run_dir=str(BASELINE_RUN_DIR),
        provenance='unconfirmed_simulation',
        provenance_label='exploratory_simulation',
        provenance_note='exploratory simulation input; never reported as a '
                        'formally accepted process condition',
        formal_acceptance_allowed=False,
        glass_thickness_mm=GLASS_THICKNESS_MM,
        glass_z_range_mm=[GLASS_Z_MIN_MM, GLASS_Z_MAX_MM],
        routing_plane_count=len(PLANE_IDS),
        plane_count=len(PLANE_IDS),
        body_plane_count=len(BODY_PLANES),
        plane_order=[int(plane_id) for plane_id in PLANE_IDS],
        plane_labels={str(plane_id): PLANE_LABEL[plane_id]
                      for plane_id in PLANE_IDS},
        plane_roles={str(plane_id): PLANE_LAYER_ROLE[plane_id]
                     for plane_id in PLANE_IDS},
        plane_roles_detail={str(plane_id): PLANE_ROLE_DETAIL[plane_id]
                            for plane_id in PLANE_IDS},
        plane_heights_mm={str(plane_id): float(PLANE_Z[plane_id])
                          for plane_id in PLANE_IDS},
        body_planes={str(plane_id): float(z_mm)
                     for plane_id, z_mm in BODY_PLANES.items()},
        interface_planes={str(plane_id): dict(INTERFACE_PLANES[plane_id])
                          for plane_id in INTERFACE_PLANE_IDS},
        interfaces=dict(INTERFACE_Z),
        route_count=1024,
        interface=dict(z1=Z1_INTERFACE_MM, z2=Z2_INTERFACE_MM),
        manual_planes={str(plane_id): group for plane_id, group
                       in MANUAL_LAYER_TO_GROUP.items()},
        min_layer_pitch_mm=MIN_LAYER_PITCH_MM,
        measured_min_height_pitch_mm=min_height_pitch(),
        min_pitch_check=dict(minimum=min_height_pitch(),
                             required=MIN_LAYER_PITCH_MM,
                             passed=min_height_pitch()
                             >= MIN_LAYER_PITCH_MM - 1e-9),
        note='20 routing heights: body layers 2..18 and 20 (plane id 19 '
             'deleted with L19; ids are identity labels, physical ordering '
             'is always taken from z) + the two routable interface rows of '
             'L1 (ids 1001/1002, now z=+0.025/+0.525); every surviving '
             'height was raised by +0.025 mm; glass envelope unchanged.',
    ))
    return payload


#: backwards-compatible alias
physical_layer_stack_payload = stack_payload


def process_rules_payload():
    """``process_rules.json``: baseline rules + documented 20-height overrides."""
    payload = dict(C.process_rules_payload())
    payload.update(dict(
        schema=SCHEMA_PROCESS_RULES,
        profile=PROFILE,
        experiment=EXPERIMENT_NAME,
        model=MODEL_NAME,
        glass_thickness_mm=GLASS_THICKNESS_MM,
        glass_z_range_mm=[GLASS_Z_MIN_MM, GLASS_Z_MAX_MM],
        interfaces=dict(INTERFACE_Z),
        z1_interface_mm=Z1_INTERFACE_MM,
        z2_interface_mm=Z2_INTERFACE_MM,
        min_layer_pitch_mm=MIN_LAYER_PITCH_MM,
        measured_min_height_pitch_mm=min_height_pitch(),
        min_3d_clearance_mm=MIN_3D_CLEARANCE_MM,
        min_bend_radius_mm=MIN_BEND_RADIUS_MM,
        waveguide_width_mm=WIDTH_MM,
        same_layer_2d_rules='original strict D56 index (width 0.05 + edge gap '
                            '0.03); legal transverse crossings preserved',
        routing_plane_count=len(PLANE_IDS),
        plane_heights_mm={str(plane_id): float(PLANE_Z[plane_id])
                          for plane_id in PLANE_IDS},
        interface_planes={str(plane_id): dict(INTERFACE_PLANES[plane_id])
                          for plane_id in INTERFACE_PLANE_IDS},
        interface_body_routing_rule=(
            'the Z1_INTERFACE (z=+0.025) and Z2_INTERFACE (z=+0.525) heights '
            'are routable 2D body planes in this experiment: a route whose '
            'target height equals its own interface height is DIRECT '
            '(0 transitions, no lead, no S-curve) and its body is a flat part '
            'at that height; it must pass the same strict D56 rule against '
            'every interface lead at the same height and true-3D >= 0.05 mm '
            'against every S-transition sample of other routes'),
        height_model_change=dict(
            removed_plane=dict(plane_id=19, label='L19', old_z_mm=0.65),
            height_shift_mm=0.025,
            body_plane_count=len(BODY_PLANES),
            interface_z_mm=dict(INTERFACE_Z),
            note='20-height model: L19 deleted and every surviving routing '
                 'height raised by +0.025 mm; no geometric threshold changed'),
        explicitly_not_restored=dict(
            global_80um_clearance=False,
            note='the unconfirmed 80 um global clearance is NEVER restored as '
                 'a 3D rule; 0.08 mm only survives as the same-layer 2D '
                 'centre-line rule of the original D56 geometry'),
        unconfirmed=dict(
            optical_crosstalk='not verified',
            fabrication_tolerance='not verified',
            surface_process_margin='not verified; the boundary waveguides '
                                   'only satisfy the current exploratory '
                                   'centre-line model'),
        baseline_process_rules_note='baseline 18-layer values are inherited '
                                    'unchanged from '
                                    'common.process_rules_payload() except '
                                    'the documented 20-height configuration '
                                    'overrides',
    ))
    return payload


#: the l3d interface layer id used by the stack model (kept for consumers)
INTERFACE_LAYER = INTERFACE_LAYER_ID

__all__ = [
    # paths (frozen API)
    'RUN_DIR', 'BASELINE_RUN_DIR', 'BASE_ASSIGNMENT', 'NEW_ASSIGNMENT',
    'LAYER_PLANES_JSON', 'NEW_ASSIGNMENT_AUDIT', 'NEW_ASSIGNMENT_DIFF_JSON',
    'NEW_ASSIGNMENT_DIFF_MD', 'NEW_STACK_JSON', 'NEW_RULES_JSON',
    'NEW_EXPERIMENT_A', 'ROOT', 'OUTPUT_ROOT', 'EXPERIMENT_ROOT',
    'BASELINE_21H_RUN_DIR',
    # geometry constants (frozen API)
    'BODY_PLANES', 'INTERFACE_PLANES', 'PLANE_IDS', 'INTERFACE_Z',
    'MANUAL_GROUPS', 'MANUAL_ROLES', 'Z1_OTHER_PLAN', 'Z2_OTHER_PLAN',
    'Z2_OTHER_OLD_TO_NEW', 'GLASS_THICKNESS_MM', 'GLASS_Z_MIN_MM',
    'GLASS_Z_MAX_MM', 'MIN_LAYER_PITCH_MM', 'MIN_3D_CLEARANCE_MM',
    'MIN_BEND_RADIUS_MM', 'Z1_INTERFACE_MM', 'Z2_INTERFACE_MM',
    'Z1_INTERFACE_PLANE_ID', 'Z2_INTERFACE_PLANE_ID', 'INTERFACE_PLANE_IDS',
    'MANUAL_LAYER_TO_GROUP', 'MANUAL_PLANE_IDS', 'MANUAL_GROUP_SPECS',
    'Z1_GROUP_ORDER', 'Z2_GROUP_ORDER', 'PLANE_Z', 'PLANE_LABEL',
    'PLANE_KIND', 'PLANE_SIDE', 'PLANE_ROLE', 'PLANE_LAYER_ROLE',
    'PLANE_ROLE_DETAIL', 'BASELINE_LAYER_Z',
    'BASELINE_LAYER_IDS', 'INTERFACE_STACK_ROWS', 'WIDTH_MM', 'EDGE_GAP_MM',
    'CLEARANCE_2D_MM',
    # profile / schema
    'PROFILE', 'EXPERIMENT_NAME', 'MODEL_NAME', 'SCHEMA_LAYER_PLANES', 'SCHEMA_LAYER_STACK',
    'SCHEMA_PROCESS_RULES', 'SCHEMA_ASSIGNMENT_AUDIT', 'SCHEMA_ASSIGNMENT_DIFF',
    'SCHEMA_EXPERIMENT_A',
    # experiment contract
    'CONTRACT_PLANE_COUNTS', 'CONTRACT_Z2_OTHER_COUNTS',
    'CONTRACT_DIRECT_ROUTES', 'CONTRACT_TRANSITION_ROUTES',
    'CONTRACT_ENDPOINT_TRANSITIONS', 'CONTRACT_MANUAL_COUNTS',
    'CONTRACT_MANUAL_TOTAL', 'CONTRACT_MANUAL_ORBIT_PLANE_SETS',
    'CONTRACT_OLD_LAYER_COUNTS',
    'SPEC_BODY_HEIGHTS', 'SPEC_INTERFACE_PLANES', 'SPEC_INTERFACE_IDS',
    'SPEC_MANUAL_FIXED', 'SPEC_EXPECTED_ASSIGNED', 'SPEC_DIRECT_TOTAL',
    'SPEC_DIRECT_BY_PLANE', 'SPEC_BODY_PLANE_COUNT', 'SPEC_PLANE_COUNT',
    # helpers (frozen API)
    'plane_z', 'plane_label', 'plane_kind', 'interface_plane_for',
    'interface_z', 'is_direct_plane', 'layer_stack', 'stack_payload',
    'process_rules_payload', 'allocate_z2_other', 'ceil_distance_to_glass',
    # extra helpers / aliases
    'all_plane_ids', 'planes', 'body_plane_ids', 'is_interface_plane',
    'plane_side', 'plane_role', 'plane_role_detail', 'needs_transition',
    'direction_for', 'layer_z', 'manual_group_plane', 'min_height_pitch',
    'reset_stack', 'raw_stack_payload', 'write_json', 'layer_planes_payload',
    'stack', 'physical_layer_stack_payload', 'BODY_PLANE_Z', 'PLANE_ORDER',
    'Z2_OLD_TO_NEW_PLANE', 'Z2_LAYER_MAP', 'INTERFACE_LAYER',
    'BASELINE_ASSIGNMENT_CSV', 'NEW_ASSIGNMENT_CSV', 'NEW_LAYER_PLANES_JSON',
    'NEW_RUN_DIR', 'OLD_RUN_DIR', 'BASELINE_RUN_NAME', 'NEW_RUN_NAME',
    'BASELINE_AUDIT_JSON', 'BASELINE_STACK_JSON',
]


if __name__ == '__main__':  # tiny self-check
    print('profile:', PROFILE)
    print('planes:', len(PLANE_IDS), 'distinct heights:',
          len({plane_z(plane_id) for plane_id in PLANE_IDS}),
          'body:', len(BODY_PLANES))
    print('min pitch:', min_height_pitch(), 'mm')
    for plane_id in PLANE_IDS:
        print(f'  {plane_id:>5d} {plane_label(plane_id):<14s} '
              f'{plane_z(plane_id):+.3f} mm {plane_kind(plane_id):<15s} '
              f'{plane_side(plane_id)} {plane_role(plane_id)}')
    stack_obj = layer_stack()
    print('stack: routing ids', stack_obj.routing_layer_ids,
          'min pitch', stack_obj.min_layer_pitch_mm,
          'interface rows', stack_obj.layers[1].interface_rows)
    print('glass headroom: low',
          ceil_distance_to_glass(plane_z(2)), 'high',
          ceil_distance_to_glass(plane_z(18)))

