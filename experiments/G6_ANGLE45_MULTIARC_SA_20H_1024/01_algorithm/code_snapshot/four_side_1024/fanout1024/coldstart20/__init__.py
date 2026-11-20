# -*- coding: utf-8 -*-
"""Cold-start **20-height** rebuild of the 1024-channel 3D waveguide system.

This package is the *only* new code required to run the whole, already audited
optimisation chain (``reheight21`` -> ``nonc4`` -> ``native3d`` ->
``xyzrouter`` G1/G2/G3 -> ``xyzrouter.g4`` -> multi-arc ablation) on a 20-height
physical model instead of the frozen 21-height model.

Modules
-------
``model20``    -- authoritative 20-height model (same public API as
                  ``reheight21.model``): 18 body planes + 2 routable interface
                  planes, L19 deleted, every surviving height +0.025 mm.
``bootstrap``  -- installs the 20-height profile into the frozen pipeline by
                  registering ``model20`` under the ``reheight21.model`` module
                  key *before* any pipeline module is imported, and by
                  re-pointing the configured interface heights / output roots.
``tests_model20`` -- independent checks: 50 um pitch, glass envelope, no rule
                  relaxation (49 um pair must still be rejected), 21-height
                  legacy stack still validates, contract counts sum to 1024.
``drivers``    -- the per-stage entry points for the cold-start experiment.

The 21-height code and every historical artifact stay read-only; the 20-height
run writes only below
``experiments/COLD_START_20_HEIGHT_1024/``.
"""
from __future__ import annotations

__all__ = ['model20', 'bootstrap']
