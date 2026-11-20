# -*- coding: utf-8 -*-
"""Minimal input adapter for the corrected manual Z1/Z2 grouping files.

This package deliberately does **not** implement a new router, clustering,
compatibility graph or optimisation framework.  It only

1. reads the two manual files exactly as given (connection pairing and grouping
   untouched, z1/z2 plane identity taken from the data source rather than from the
   unreliable export ``layer`` column), and
2. feeds them into the existing project code paths (R=15 U geometry, sequential
   2D router, ``l3d`` elevation lift, true-3D world, canonical geometry checks).

See ``run_minimal_check.py`` for the static check + one minimal adaptation run.
"""
