"""CTP-2.0: Literature-Grounded, Multi-Method Validated Full-Board Crosstalk Prediction.

This package supersedes CTP-1.0 (``experiments/CROSSTALK_PREDICTION_20H_1283_1024``).
The frozen CTP-1.0 tree is *never* modified; every comparison is made against its
published outputs.

Modules
-------
params      immutable physics / board constants and the parameter-sweep presets
dataio      frozen-input loading + SHA256 verification + route geometry parsing
optics      mode solvers (3-D cross-section scalar FDE, effective-index model)
coupling    two-waveguide coupling: overlap integral, symmetry-reduced supermode
            validation, exponential asymptotics with explicit validity range
crossing2d  local crossing kernels: corrected 2-D FDTD, BPM, CMT integral
bpm         split-step Fourier BPM (2-D in-plane and full 3-D)
board       full-board 1024x1024 propagation assembly
"""
from __future__ import annotations

__version__ = "2.0.0"
