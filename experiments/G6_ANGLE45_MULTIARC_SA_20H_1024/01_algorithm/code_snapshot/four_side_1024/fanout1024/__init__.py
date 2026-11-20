# -*- coding: utf-8 -*-
"""Fanout-First, layer-wise 2D routing system for the 1024-channel 3D optical
waveguide experiment (corrected 1 mm / 50 um process rules).

Modules
-------
common      : constants, true connectivity/ports, layer stack, process rules.
verify      : P0/P1 - Excel audit, verified Z1/Z2 manual-U CSVs, assignment.
assign      : 1024 target-layer assignment (8 fixed manual layers + 10 others).
fanout      : R15 3D S-curve port transitions and global 3D coordination.
layer2d     : per-physical-layer 2D R15 routing of the landing-to-landing body.
assemble    : stitch transitions + bodies + interface leads into full 3D routes.
run_all     : experiment A-E drivers and the joint repair loop.
validate_final : independent final validator (same rules as the online world).
plots / report : figures and Markdown reports.
"""
