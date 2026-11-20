# -*- coding: utf-8 -*-
"""Single place where the *existing* project modules are imported.

``r15.profile_r15.apply()`` must run before any module that binds the radius at
import time, hence this module is imported first by the adapter.
"""
from __future__ import annotations

from four_side_1024.r15 import profile_r15

profile_r15.apply()

from four_side_1024.d56 import frames as ROUTER_FRAMES          # noqa: E402
from four_side_1024.d56 import index as D56_INDEX               # noqa: E402
from four_side_1024.fslw import config as FSLW_CFG              # noqa: E402
from four_side_1024.fslw import geom as FSLW_GEOM               # noqa: E402
from four_side_1024.fslw import search as ROUTER_SEARCH         # noqa: E402
from four_side_1024.l3d import layers as L3D_LAYERS            # noqa: E402
from four_side_1024.l3d import paths as L3D_PATHS               # noqa: E402
from four_side_1024.l3d import world as L3D_WORLD               # noqa: E402
from four_side_1024.r15 import u_geometry as U_GEOMETRY         # noqa: E402


class C:
    """Process parameters, all read from the existing project configuration."""

    RADIUS_MM = float(FSLW_CFG.RADIUS_MM)              # 15.0 (R15 profile)
    WIDTH_MM = float(FSLW_CFG.WIDTH_MM)                # 0.050
    EDGE_GAP_MM = float(FSLW_CFG.EDGE_GAP_MM)          # 0.030
    CLEARANCE_MM = float(FSLW_CFG.CLEARANCE_MM)        # 0.080
    SAGITTA_MM = float(FSLW_CFG.SAGITTA_MM)
    MIN_CROSS_ANGLE_DEG = float(FSLW_CFG.MIN_CROSS_ANGLE_DEG)
    PROPAGATION_LOSS_DB_PER_CM = float(FSLW_CFG.PROPAGATION_LOSS_DB_PER_CM)
    INTERFACE_LAYER_ID = 1                              # four_side_1024.l3d.layers


__all__ = ['C', 'ROUTER_FRAMES', 'D56_INDEX', 'FSLW_CFG', 'FSLW_GEOM',
           'ROUTER_SEARCH', 'L3D_LAYERS', 'L3D_PATHS', 'L3D_WORLD',
           'U_GEOMETRY', 'profile_r15']
