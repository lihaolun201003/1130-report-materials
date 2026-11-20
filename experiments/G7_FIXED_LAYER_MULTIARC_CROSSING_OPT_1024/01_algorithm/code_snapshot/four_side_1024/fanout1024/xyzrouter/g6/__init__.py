# -*- coding: utf-8 -*-
"""G6 -- angle-aware MultiArc simulated annealing (theta_min = 45 deg).

G6 keeps the exact G5 route model (per-height chains, strict D56, true 3-D
clearance, exact local-tangent crossing angle) and adds the missing degree of
freedom the G5 search never had: the *planar MultiArc body itself* can be
regenerated, together with the R15 port transitions and the whole-route height.

New modules
-----------
``geometry``      route dissection, MultiArc body regeneration (reuses the frozen
                  ``layer2d`` candidate grammar), lead / height / direct-lift
                  route assembly.
``neighborhoods`` N1..N6 move families (single route, pair, group, re-height,
                  transition/lead joint, combined).
``sa``            simulated-annealing kernel: E = M*N_bad + lambda*D_theta,
                  Metropolis acceptance, adaptive temperature, reheating,
                  checkpoints, multi-seed, best-state tracking and periodic
                  full-audit reconciliation.
"""
from __future__ import annotations

__all__ = ['geometry', 'neighborhoods', 'sa']

THETA_MIN_DEG = 45.0
