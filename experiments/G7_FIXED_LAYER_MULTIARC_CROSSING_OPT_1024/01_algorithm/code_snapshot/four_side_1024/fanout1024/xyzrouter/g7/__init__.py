# -*- coding: utf-8 -*-
"""G7 -- fixed-layer MultiArc crossing minimization on top of the G6 solution.

G6 established a legal 1024-route / 20-height / theta >= 45 deg solution with
4578 same-height crossings.  G7 freezes the *whole* G6 invalidity-relevant
structure (real per-route height sequences, R15 transitions, ports, artificial
U structures, direct-route interfaces) and only re-plans MultiArc body geometry
to reduce the crossing count.

Modules
-------
``frozen``  build/verify the frozen-structure manifest extracted from the real
            ``routes_l3d.json`` (never from the stale assignment CSV);
``engine``  authoritative crossing bookkeeping: per-physical-plane audits with
            the *same* ``fslw.validate_fslw`` strict-D56 code as the frozen
            project validator, plus 3-D clearance and per-route contributions;
``sa``      fixed-layer simulated annealing with E = N_cross;
``run_g7``  multi-seed driver (checkpoints / resume / cycles);
``run_polish_g7`` deterministic best-improvement pass over the residual hotspots.
"""
from __future__ import annotations

__all__ = ['frozen', 'engine', 'sa']
