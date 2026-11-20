# -*- coding: utf-8 -*-
"""Install the **20-height profile** into the frozen 1024-route pipeline.

The frozen optimisation chain (``assign21`` -> ``run21`` -> ``nonc4`` ->
``native3d`` -> ``xyzrouter`` G1/G2/G3 -> ``xyzrouter.g4``) never parameterises
its height table: every module does ``from ..reheight21 import model as M`` and
reads the plane table from that single module.  That is exactly the seam this
cold-start rebuild uses.

Importing this module (it installs on import) does three things, in order:

1. registers :mod:`four_side_1024.fanout1024.coldstart20.model20` under the
   module key ``four_side_1024.fanout1024.reheight21.model`` *and* as the
   ``model`` attribute of the ``reheight21`` package, so every later
   ``from ..reheight21 import model as M`` (and ``from . import model as M``
   inside ``validate21``) resolves to the 20-height model;
2. re-points the two interface heights in the legacy ``common`` constants
   (``common.INTERFACE_Z`` / ``Z1_INTERFACE_MM`` / ``Z2_INTERFACE_MM``) and the
   default ``l3d.layers.INTERFACE_ROWS`` at the new 20-height values
   (+0.025 mm / +0.525 mm);
3. drops the cached ``l3d`` stack so that every later ``layer_stack()`` call is
   built from the 20-height table.

Nothing else is touched: every geometric threshold (R15, 50 um 3D clearance,
strict D56, glass envelope, 1024 connections) stays bit-identical, and the
frozen 21-height experiment stays reproducible in a process that does **not**
import this bootstrap.

Usage
-----
Every cold-start driver must import this module **before** any pipeline module::

    from four_side_1024.fanout1024.coldstart20 import bootstrap as B
    B.install(run_dir=...)            # already installed on import
    from four_side_1024.fanout1024.reheight21 import run21

The guard :func:`assert_20_height_profile` fails loudly if the profile was not
installed (e.g. because a driver imported ``run21`` first), so a silent 21-height
run is impossible.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .. import common as C
from . import model20 as M20
from . import paths20 as P20
from . import profile_env as PE

_MODEL_KEY = 'four_side_1024.fanout1024.reheight21.model'
_PKG_KEY = 'four_side_1024.fanout1024.reheight21'

_INSTALLED = False
_INSTALL_LOG = []


def _log(message):
    _INSTALL_LOG.append(str(message))


# ===========================================================================
# 1. model registration
# ===========================================================================
def install_model():
    """Register ``model20`` as ``reheight21.model`` (idempotent)."""
    import four_side_1024.fanout1024.reheight21 as package21
    sys.modules[_MODEL_KEY] = M20
    setattr(package21, 'model', M20)
    _log(f'{_MODEL_KEY} -> coldstart20.model20')
    return M20


# ===========================================================================
# 2. interface-height constants
# ===========================================================================
def install_interface_heights():
    """Point the legacy interface-height constants at the 20-height values."""
    old = dict(C.INTERFACE_Z)
    C.Z1_INTERFACE_MM = float(M20.Z1_INTERFACE_MM)
    C.Z2_INTERFACE_MM = float(M20.Z2_INTERFACE_MM)
    # ``common.INTERFACE_Z`` is a module level dict read through
    # ``common.interface_z()``; update it in place so every existing importer
    # (fanout, layer2d, assemble, assign) sees the new heights.
    C.INTERFACE_Z.clear()
    C.INTERFACE_Z.update({key: float(value)
                          for key, value in M20.INTERFACE_Z.items()})
    from ...l3d import layers as L3D
    rows_before = dict(L3D.INTERFACE_ROWS)
    L3D.INTERFACE_ROWS.clear()
    L3D.INTERFACE_ROWS.update({key: float(value)
                               for key, value in M20.INTERFACE_Z.items()})
    # the AUTHORITATIVE port model (fslw.ports -> v3c4.inputs.ENDPOINTS) takes
    # the two 2x16 MPO row heights from fslw.config.PLANE_Z_MM.  The port XY
    # geometry (0.25 mm column pitch, 0.5 mm row pitch, 9 mm connector pitch)
    # is untouched; only the two row heights follow the 20-height model, and the
    # row separation stays exactly 0.5 mm.
    from ...fslw import config as FS
    plane_z_before = dict(FS.PLANE_Z_MM)
    row_pitch_before = (float(plane_z_before[2]) - float(plane_z_before[1]))
    FS.PLANE_Z_MM[1] = float(M20.Z1_INTERFACE_MM)
    FS.PLANE_Z_MM[2] = float(M20.Z2_INTERFACE_MM)
    row_pitch_after = float(FS.PLANE_Z_MM[2]) - float(FS.PLANE_Z_MM[1])
    if abs(row_pitch_after - row_pitch_before) > 1e-12:
        raise RuntimeError('port row pitch changed: %.9f -> %.9f'
                           % (row_pitch_before, row_pitch_after))
    _log(f'common.INTERFACE_Z {old} -> {dict(C.INTERFACE_Z)}')
    _log(f'l3d.INTERFACE_ROWS {rows_before} -> {dict(L3D.INTERFACE_ROWS)}')
    _log(f'fslw.config.PLANE_Z_MM {plane_z_before} -> {dict(FS.PLANE_Z_MM)} '
         f'(row pitch {row_pitch_after:.6f} mm unchanged)')
    return dict(C.INTERFACE_Z)


# ===========================================================================
# 3. run-directory binding
# ===========================================================================
def bind_run_dir(run_dir):
    """Re-point every writable ``model`` path at ``run_dir`` (created)."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    M20.RUN_DIR = run_dir
    M20.NEW_RUN_DIR = run_dir
    M20.NEW_ASSIGNMENT = run_dir / 'assignment_1024.csv'
    M20.NEW_ASSIGNMENT_AUDIT = run_dir / 'assignment_audit.json'
    M20.NEW_ASSIGNMENT_DIFF_JSON = run_dir / 'assignment_diff_vs_baseline.json'
    M20.NEW_ASSIGNMENT_DIFF_MD = run_dir / 'assignment_diff_vs_baseline.md'
    M20.LAYER_PLANES_JSON = run_dir / 'layer_planes.json'
    M20.NEW_STACK_JSON = run_dir / 'physical_layer_stack.json'
    M20.NEW_RULES_JSON = run_dir / 'process_rules.json'
    M20.NEW_EXPERIMENT_A = run_dir / 'experiment_A'
    M20.NEW_ASSIGNMENT_CSV = M20.NEW_ASSIGNMENT
    M20.NEW_LAYER_PLANES_JSON = M20.LAYER_PLANES_JSON
    M20.reset_stack()
    _log(f'RUN_DIR -> {run_dir}')
    return run_dir


# ===========================================================================
# 4. guards
# ===========================================================================
def is_installed():
    return sys.modules.get(_MODEL_KEY) is M20


def assert_20_height_profile(context=''):
    """Fail loudly unless the 20-height profile is actually installed."""
    if not is_installed():
        raise RuntimeError(
            'the 20-height profile is NOT installed: a pipeline module was '
            'imported before coldstart20.bootstrap.  Import the bootstrap '
            'first (context=%r)' % (context,))
    if len(M20.PLANE_IDS) != 20:
        raise RuntimeError(f'expected 20 routing heights, got {len(M20.PLANE_IDS)}')
    if 19 in M20.PLANE_IDS:
        raise RuntimeError('deleted plane identity 19 is still present')
    if abs(float(C.INTERFACE_Z['z1']) - 0.025) > 1e-12:
        raise RuntimeError(f'common.INTERFACE_Z not re-pointed: {C.INTERFACE_Z}')
    from ...l3d import layers as L3D
    if abs(float(L3D.INTERFACE_ROWS['z1']) - 0.025) > 1e-12:
        raise RuntimeError(f'l3d.INTERFACE_ROWS not re-pointed: '
                           f'{L3D.INTERFACE_ROWS}')
    return True


def install(run_dir=None):
    """Run the whole installation (idempotent) and optionally bind a run dir."""
    global _INSTALLED
    if run_dir is not None:
        bind_run_dir(run_dir)
    if not _INSTALLED:
        install_model()
        install_interface_heights()
        # publish the 20-height run directories for the frozen path modules
        # (see coldstart20.profile_env); the historical 21-height paths are the
        # defaults when these variables are absent.
        P20.ensure_dirs()
        PE.activate(M20.PROFILE, P20.ENV_PATHS)
        _log('profile env activated: ' + ', '.join(
            '%s=%s' % (key, value) for key, value in P20.ENV_PATHS.items()))
        M20.reset_stack()
        _INSTALLED = True
    assert_20_height_profile('install')
    return M20


install()


# ===========================================================================
# 5. introspection / reporting
# ===========================================================================
def profile_payload():
    """Machine-readable description of the installed profile."""
    return dict(
        profile=M20.PROFILE,
        experiment=M20.EXPERIMENT_NAME,
        model='four_side_1024.fanout1024.coldstart20.model20',
        installed_as=_MODEL_KEY,
        plane_count=len(M20.PLANE_IDS),
        body_plane_count=len(M20.BODY_PLANES),
        interface_plane_ids=list(M20.INTERFACE_PLANE_IDS),
        plane_ids=[int(pid) for pid in M20.PLANE_IDS],
        plane_heights_mm={str(pid): float(M20.plane_z(pid))
                          for pid in M20.PLANE_IDS},
        interfaces={key: float(value) for key, value in M20.INTERFACE_Z.items()},
        removed_plane=dict(plane_id=19, old_z_mm=0.65),
        height_shift_mm=0.025,
        glass=dict(z_min_mm=M20.GLASS_Z_MIN_MM,
                   z_max_mm=M20.GLASS_Z_MAX_MM,
                   thickness_mm=M20.GLASS_THICKNESS_MM),
        measured_min_pitch_mm=M20.min_height_pitch(),
        min_pitch_mm=M20.MIN_LAYER_PITCH_MM,
        min_3d_clearance_mm=M20.MIN_3D_CLEARANCE_MM,
        min_bend_radius_mm=M20.MIN_BEND_RADIUS_MM,
        glass_headroom_mm=dict(
            lowest=(M20.plane_z(2) - M20.GLASS_Z_MIN_MM),
            highest=(M20.GLASS_Z_MAX_MM - M20.plane_z(18))),
        run_dir=str(M20.RUN_DIR),
        baseline_run_dir=str(M20.BASELINE_RUN_DIR),
        contract_plane_counts={str(pid): int(count) for pid, count
                               in M20.CONTRACT_PLANE_COUNTS.items()},
        contract_direct_routes=dict(M20.CONTRACT_DIRECT_ROUTES),
        contract_transition_routes=int(M20.CONTRACT_TRANSITION_ROUTES),
        contract_endpoint_transitions=int(M20.CONTRACT_ENDPOINT_TRANSITIONS),
        install_log=list(_INSTALL_LOG),
        legacy_interface_rows_restored=False,
    )


def write_profile_json(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile_payload(), indent=1,
                               ensure_ascii=False, default=str) + '\n',
                    encoding='utf-8')
    return path


def summary_lines():
    payload = profile_payload()
    lines = [
        'profile          : %s' % payload['profile'],
        'experiment       : %s' % payload['experiment'],
        'routing heights  : %d (%d body + 2 interface)' % (
            payload['plane_count'], payload['body_plane_count']),
        'plane ids        : %s' % payload['plane_ids'],
        'interfaces       : %s' % payload['interfaces'],
        'min pitch        : %.6f mm' % payload['measured_min_pitch_mm'],
        '3D clearance     : %.6f mm' % payload['min_3d_clearance_mm'],
        'Rmin             : %.6f mm' % payload['min_bend_radius_mm'],
        'glass headroom   : low %.4f / high %.4f mm' % (
            payload['glass_headroom_mm']['lowest'],
            payload['glass_headroom_mm']['highest']),
        'run dir          : %s' % payload['run_dir'],
    ]
    return lines
