# -*- coding: utf-8 -*-
"""Environment-variable bridge between the 20-height profile and the frozen path modules.

The frozen pipeline modules resolve their run directories at import time from
``common.OUTPUT_ROOT`` (e.g. ``NATIVE_3D_JOINT_OPT_1024``).  Re-pointing them
without editing every default would be impossible, so each path module reads a
single environment variable (with the frozen value as default).  This module is
the *only* place that knows the variable names.

The frozen 21-height pipeline is unaffected: with no ``COLDSTART20_*`` variable
set every default is the historical path.
"""
from __future__ import annotations

import os
from pathlib import Path

PREFIX = 'COLDSTART20_'
PROFILE_KEY = PREFIX + 'PROFILE'
PROFILE_20H = '20_height_raised'

#: environment variable -> human description (used by the report)
VARIABLES = {
    'INIT_RUN': '20H fanout-first + D56 XY + 3D initial legal run (stage 03)',
    'FANOUT_BASELINE_DIR': 'same as INIT_RUN (frozen manual-U geometry source)',
    'NONC4_ROOT': '20H C4-free annealing + joint-repair programme (stage 04)',
    'E5_DIR': '20H accepted joint-repair legal solution (E5 analog)',
    'NATIVE3D_ABC_RUN': '20H Native-3D Phase 1 run (stage 05)',
    'NATIVE3D_DEF_RUN': '20H Native-3D Phase 2 run (stage 06)',
    'XYZ_RUN': '20H G1/G2/G3 XYZ joint optimisation run (stage 07)',
    'G4_ROOT': '20H G4 global ALNS archive (stage 08)',
    'MULTIARC_ROOT': '20H multi-arc ON/OFF ablation (stage 09)',
}


def is_20h():
    """True when the 20-height profile is active for this process."""
    return os.environ.get(PROFILE_KEY, '') == PROFILE_20H


def path_env(name, default):
    """Path from ``COLDSTART20_<name>`` or ``default``."""
    value = os.environ.get(PREFIX + name)
    return Path(value) if value else Path(default)


def int_env(name, default=None):
    """Integer from ``COLDSTART20_<name>`` or ``default``."""
    value = os.environ.get(PREFIX + name)
    if value is None or str(value).strip() == '':
        return default
    return int(str(value).strip())


def set_env(name, value):
    os.environ[PREFIX + name] = str(value)


def activate(profile, paths):
    """Mark the profile active and publish every path variable."""
    os.environ[PROFILE_KEY] = str(profile)
    for key, value in paths.items():
        set_env(key, value)


def snapshot():
    """Current values of every cold-start variable (for the report)."""
    return {key: os.environ.get(PREFIX + key) for key in VARIABLES}


def describe():
    lines = ['cold-start profile active: %s' % is_20h()]
    for key, description in VARIABLES.items():
        lines.append('  %-22s %s%-(value)s  # %s' % (key, PREFIX, description))
    return lines
