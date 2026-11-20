# -*- coding: utf-8 -*-
"""Process / layer-stack configuration for the manual-fixed-U 640-channel round.

Every geometric number used by :mod:`four_side_1024.manual_u640` is read from
here.  The values are the *existing project configuration* of the 2026-10-30
150 µm multi-layer round, not newly invented fabrication parameters:

* ``four_side_1024/r15/profile_r15.py``  -> fixed bend radius R = 15 mm
* ``four_side_1024/fslw/config.py``      -> board 150 mm, width 0.050 mm,
  edge gap 0.030 mm, centreline clearance 0.080 mm, plane heights z1 = 0.0,
  z2 = 0.5 mm
* ``four_side_1024/c4/layers.py`` and
  ``four_side_1024/manual_c4/z1_multilayer_150um.py`` -> routing layers L2..L13
  at 0.15 mm pitch above Z2 = 0.5 mm (L2 = 0.65 mm)

Nothing here is a confirmed process parameter.  The layer heights carry the
``unconfirmed_simulation`` provenance exactly as in the existing stack payloads.
"""
from __future__ import annotations

import os
from pathlib import Path

# -- paths ------------------------------------------------------------------
PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parents[1]
INPUT_CSV = (PROJECT_ROOT / 'manual_z1_router' / 'data' / 'exports' / '人工分组'
             / 'z1_z2_manual_u_assignment_v2_640.csv')
OUTPUT_ROOT = PROJECT_ROOT / 'outputs' / 'manual_u640'

# -- process parameters (existing configuration, see module docstring) ------
BOARD_MM = 150.0
WIDTH_MM = 0.050
EDGE_GAP_MM = 0.030
CLEARANCE_MM = WIDTH_MM + EDGE_GAP_MM          # 0.080 mm centreline clearance
RADIUS_MM = 15.0                                # R15 process profile
MIN_CROSS_ANGLE_DEG = 5.0
SAGITTA_MM = 0.0005
PROPAGATION_LOSS_DB_PER_CM = 0.05

#: Physical interface heights of the two CSV data-source planes (model values).
Z1_MM = 0.0
Z2_MM = 0.5
PLANE_Z_MM = {'z1': Z1_MM, 'z2': Z2_MM}
PLANE_ROW = {'z1': 1, 'z2': 2}

#: Routing-layer stack: L1 is the interface layer (carries both rows), L2.. are
#: routing layers at 0.15 mm pitch above Z2 = 0.5 mm (existing c4/150um config).
LAYER_PITCH_MM = 0.15
BASE_ROUTING_Z_MM = 0.65       # physical height of L2
INTERFACE_LAYER_ID = 1
MAX_LOGICAL_LAYERS = 13        # existing c4 stack supports L1..L13

#: Manual fixed-U layers L1..L6 (assignment is given by the input CSV).
MANUAL_LAYER_IDS = (1, 2, 3, 4, 5, 6)
#: First logical layer available to the automatic router.
FIRST_AUTO_LAYER_ID = 7

#: Layer-stack provenance (mirrors the existing payloads).
PROVENANCE = 'unconfirmed_simulation'
STACK_NOTE = ('manual_u640: 0.15 mm layer pitch above Z2 = 0.5 mm; '
              'L1 interface layer with rows z1 = 0.0 / z2 = 0.5; '
              'heights are configurable simulation inputs, not confirmed '
              'fabrication parameters')

#: Accept an override of the layer pitch from the environment for sensitivity
#: studies (never used by the default run).
_ENV_PITCH = os.environ.get('MANUAL_U640_LAYER_PITCH_MM')
if _ENV_PITCH:
    LAYER_PITCH_MM = float(_ENV_PITCH)


def layer_z(layer_id, row=None):
    """Physical height (mm) of one logical layer.

    ``L1`` is the interface layer and needs the CSV data-source plane / row;
    every ``L2..`` layer is a single routing height.
    """
    layer_id = int(layer_id)
    if layer_id == INTERFACE_LAYER_ID:
        if row is None:
            raise ValueError('the interface layer L1 needs a plane/row argument')
        if isinstance(row, str):
            return float(PLANE_Z_MM[row])
        return float(PLANE_Z_MM['z1'] if int(row) == 1 else PLANE_Z_MM['z2'])
    if not 2 <= layer_id <= MAX_LOGICAL_LAYERS:
        raise ValueError(f'layer id out of the supported range 1..{MAX_LOGICAL_LAYERS}: '
                         f'{layer_id}')
    return round(BASE_ROUTING_Z_MM + (layer_id - 2) * LAYER_PITCH_MM, 9)


def routing_layer_ids(max_layer=MAX_LOGICAL_LAYERS):
    return list(range(2, int(max_layer) + 1))


def process_record():
    """JSON-ready process record embedded in every artifact."""
    return dict(
        schema='four_side_1024_manual_u640_process_v1',
        board_mm=[BOARD_MM, BOARD_MM],
        waveguide_width_mm=WIDTH_MM,
        min_edge_gap_mm=EDGE_GAP_MM,
        min_centerline_clearance_mm=CLEARANCE_MM,
        min_bend_radius_mm=RADIUS_MM,
        radius_note=('fixed R = 15 mm for every planar bend and every 3D elevation '
                     'S-curve (2026-10-20 R15 process requirement)'),
        min_cross_angle_deg=MIN_CROSS_ANGLE_DEG,
        sagitta_mm=SAGITTA_MM,
        propagation_loss_db_per_cm=PROPAGATION_LOSS_DB_PER_CM,
        bend_loss=dict(status='unknown_uncalibrated',
                       note='no measured bend-loss function for this glass process; '
                            'R = 15 mm is a geometry constraint only'),
        crossing_loss=dict(status='unknown_uncalibrated',
                           note='crossing optical feasibility not confirmed; the '
                                'crossing count is a geometric metric only'),
        layer_pitch_mm=LAYER_PITCH_MM,
        base_routing_z_mm=BASE_ROUTING_Z_MM,
        interface_layer=INTERFACE_LAYER_ID,
        plane_z_mm=dict(PLANE_Z_MM),
        manual_layer_ids=list(MANUAL_LAYER_IDS),
        first_auto_layer_id=FIRST_AUTO_LAYER_ID,
        layer_stack_provenance=PROVENANCE,
        layer_stack_note=STACK_NOTE,
        source_csv=str(INPUT_CSV),
    )
