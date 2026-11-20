# -*- coding: utf-8 -*-
"""G5 -- Angle-Constrained Native 3D Waveguide Routing (theta_min = 45 deg).

New hard geometric constraint on top of the frozen G4 20-height solution:

    every genuine same-plane crossing of two waveguides must satisfy
        theta = arccos(|t_i . t_j|) >= 45 deg

where ``t_i`` / ``t_j`` are the *local exact* unit tangents of the true XYZ
centre lines at the true intersection point.

Modules
-------
``geom``      exact 2-D primitive algebra (line / R15 arc), tangents, arc length
``angle``     the 45 deg rule: crossing-angle measurement and classification
``model``     routes <-> per-plane chains, exact legality world (D56 + 3D + R15)
``candidates`` candidate generation (reheight / XY re-route / native-3D excursion)
``search``    ALNS over the frozen G4 solution with lexicographic objective
``audit``     baseline crossing-angle audit + conflict graph
"""
from __future__ import annotations

__all__ = ['geom', 'angle', 'model', 'candidates', 'search', 'audit']

THETA_MIN_DEG = 45.0
