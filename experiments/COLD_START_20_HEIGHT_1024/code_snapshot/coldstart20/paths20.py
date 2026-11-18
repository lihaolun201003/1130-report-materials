# -*- coding: utf-8 -*-
"""All writable directories of the cold-start 20-height experiment.

One directory per deliverable stage of
``experiments/COLD_START_20_HEIGHT_1024/``.  ``bootstrap`` publishes these as
``COLDSTART20_*`` environment variables so the frozen pipeline path modules
resolve to them (see :mod:`coldstart20.profile_env`).
"""
from __future__ import annotations

from pathlib import Path

#: the deliverable root
EXP_ROOT = Path(__file__).resolve().parents[3] / 'experiments' / 'COLD_START_20_HEIGHT_1024'

#: 01 -- the new height table / process rules / baseline snapshot
HEIGHT_CONFIG = EXP_ROOT / '01_height_config'
#: 02 -- from-scratch layer assignment + simulated-annealing evidence
ANNEALING = EXP_ROOT / '02_annealing'
#: 03 -- fanout + strict-D56 multi-arc planar routing of the cold assignment
FANOUT_XY = EXP_ROOT / '03_fanout_and_xy'
#: 04 -- initial 3D assembly, joint repair, first 1024/1024 legal checkpoint
INITIAL_3D = EXP_ROOT / '04_initial_3d_and_e5_repair'
#: 05 -- Native 3D Phase 1 (A/B/C)
NATIVE3D_ABC = EXP_ROOT / '05_native3d_abc'
#: 06 -- Native 3D Phase 2 (D/E/F)
NATIVE3D_DEF = EXP_ROOT / '06_native3d_def'
#: 07 -- G1 / G2a / G2b / G3
G123 = EXP_ROOT / '07_g123'
#: 08 -- G4a / G4b / G4c-frozen / G4c-free / G4d
G4 = EXP_ROOT / '08_g4'
#: 09 -- controlled multi-arc ON/OFF ablation
MULTIARC = EXP_ROOT / '09_multi_arc_ablation'
#: 10 -- the frozen best legal 20-height solution
BEST_VALID = EXP_ROOT / '10_best_valid'
#: 11 -- figures
FIGURES = EXP_ROOT / '11_figures'
#: 12 -- reports
REPORTS = EXP_ROOT / '12_reports'

#: stage run directories consumed by the frozen pipeline modules
INIT_RUN = FANOUT_XY / 'run_initial_20h'
NONC4_ROOT = INITIAL_3D / 'nonc4_programme'
E5_DIR = NONC4_ROOT / 'E5_joint_repair_final'
NATIVE3D_ABC_RUN = NATIVE3D_ABC / 'run_native3d_phase1'
NATIVE3D_DEF_RUN = NATIVE3D_DEF / 'run_native3d_phase2'
XYZ_RUN = G123 / 'run_xyz_joint_1024_20h'
G4_ROOT = G4

#: bootstrap environment mapping
ENV_PATHS = {
    'INIT_RUN': INIT_RUN,
    'FANOUT_BASELINE_DIR': INIT_RUN,
    'NONC4_ROOT': NONC4_ROOT,
    'E5_DIR': E5_DIR,
    'NATIVE3D_ABC_RUN': NATIVE3D_ABC_RUN,
    'NATIVE3D_DEF_RUN': NATIVE3D_DEF_RUN,
    'XYZ_RUN': XYZ_RUN,
    'G4_ROOT': G4_ROOT,
    'MULTIARC_ROOT': MULTIARC,
}

ALL_STAGE_DIRS = (
    HEIGHT_CONFIG, ANNEALING, FANOUT_XY, INITIAL_3D, NATIVE3D_ABC,
    NATIVE3D_DEF, G123, G4, MULTIARC, BEST_VALID, FIGURES, REPORTS,
)


def ensure_dirs():
    for path in ALL_STAGE_DIRS:
        Path(path).mkdir(parents=True, exist_ok=True)
    return ALL_STAGE_DIRS


def as_dict():
    return dict(
        experiment_root=str(EXP_ROOT),
        height_config=str(HEIGHT_CONFIG),
        annealing=str(ANNEALING),
        fanout_xy=str(FANOUT_XY),
        initial_3d=str(INITIAL_3D),
        native3d_abc=str(NATIVE3D_ABC),
        native3d_def=str(NATIVE3D_DEF),
        g123=str(G123),
        g4=str(G4),
        multiarc=str(MULTIARC),
        best_valid=str(BEST_VALID),
        figures=str(FIGURES),
        reports=str(REPORTS),
        init_run=str(INIT_RUN),
        nonc4_root=str(NONC4_ROOT),
        e5_dir=str(E5_DIR),
        native3d_abc_run=str(NATIVE3D_ABC_RUN),
        native3d_def_run=str(NATIVE3D_DEF_RUN),
        xyz_run=str(XYZ_RUN),
    )
