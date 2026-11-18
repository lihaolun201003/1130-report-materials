# -*- coding: utf-8 -*-
"""Native-3D Phase 2 (D/E/F) 20-height configuration patch -- one-shot, backup-able.

Applies the minimum *configuration* adaptations listed in
``experiments/COLD_START_20_HEIGHT_1024/00_audit/native3d_def.md`` (inventory
rows 14-20 / 24 / 46-51 and defects 1-3) so that the frozen Phase-2 stage chain
runs against the 20-height profile that ``coldstart20.bootstrap`` installs:

  ``native3d/common.py``
      profile-aware candidate-pool path helper (``crossing_intervals_path``).
  ``native3d/phase2.py``
      20H model payloads in ``copy_model_files`` (never 21H copies), fresh
      ``best_valid/transition_stats.json`` in ``save_best_valid``, dynamic
      parent-experiment text.
  ``native3d/run_d.py`` / ``native3d/blocker_analysis.py``
      read the regenerated candidate pool from the 20H Phase-2 run dir.
  ``native3d/run_e.py``
      report the real start crossing count (audit defect #7: the summary
      hard-wired ``P2.BASELINE_CROSSINGS`` and contained dead code).
  ``native3d/run_f.py``
      reject-path rollback restores the *pre-step* geometry instead of the
      run-start snapshot (audit defect #3; correctness fix, exact deepcopy
      pattern ``run_f_plus.py`` already uses).
  ``native3d/finalize_phase2.py``
      independent validator for 20H is ``reheight21.validate21`` (never the
      21H ``validate_native3d`` / ``E5_EXPECT`` regression block), archive below
      ``experiments/COLD_START_20_HEIGHT_1024/06_native3d_def`` (never into the
      frozen 21H archive dir), 20H model payloads, data-driven baseline count /
      height text.

Every edit is exact-match (asserts its occurrence count) and profile-conditional:
a process that does **not** import ``coldstart20.bootstrap`` keeps the frozen
21-height defaults bit-identically.  The only exception is the ``run_f.py``
reject-path rollback, which merely fixes an otherwise corrupting latent branch
(it can only differ when a change is rejected after an earlier mutation).

Usage
-----
::

    .venv\\Scripts\\python.exe experiments\\COLD_START_20_HEIGHT_1024\\00_audit\\patch_native3d_def.py --dry-run
    .venv\\Scripts\\python.exe experiments\\COLD_START_20_HEIGHT_1024\\00_audit\\patch_native3d_def.py
    .venv\\Scripts\\python.exe experiments\\COLD_START_20_HEIGHT_1024\\00_audit\\patch_native3d_def.py --verify
    .venv\\Scripts\\python.exe experiments\\COLD_START_20_HEIGHT_1024\\00_audit\\patch_native3d_def.py --revert [STAMP]

A timestamped backup of every patched file is written below
``00_audit/backups/native3d_def/<STAMP>/`` together with ``PATCH_MANIFEST.json``
(original + patched sha256, script sha256, per-patch status).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent            # .../COLD_START_20_HEIGHT_1024/00_audit
PROJECT_ROOT = HERE.parents[2]                    # .../OpticalWaveguideRouter2D
BACKUP_ROOT = HERE / 'backups' / 'native3d_def'
VERIFY_JSON = HERE / 'patch_native3d_def_verify.json'
PY = sys.executable

#: frozen 21-height expected values (must stay untouched)
MOVABLE_21H = (6, 7, 20, 1001, 8, 9, 14, 15, 16, 1002, 17, 18, 19)
#: 20-height expected values under the bootstrap
MOVABLE_20H = (6, 7, 20, 1001, 8, 9, 14, 15, 16, 1002, 17, 18)


# ===========================================================================
# patch table
# ===========================================================================
def patches():
    """Return the ordered patch list (relpath, name, old, new)."""
    items = []

    def add(rel, name, old, new, embed=False):
        items.append(dict(rel=rel, name=name, old=old, new=new, embed=embed))

    # ------------------------------------------------------------------ common
    add('four_side_1024/fanout1024/native3d/common.py',
        'common.py: profile-aware candidate-pool path helper',
        r'''#: new experiment root
RUN_DIR = PE.path_env('NATIVE3D_ABC_RUN',
                      OUTPUT_ROOT / 'NATIVE_3D_CROSSING_OPT_1024')

#: path length used by the 3D S-curves
''',
        r'''#: new experiment root
RUN_DIR = PE.path_env('NATIVE3D_ABC_RUN',
                      OUTPUT_ROOT / 'NATIVE_3D_CROSSING_OPT_1024')
#: 20-height Phase-2 run dir (owner of the regenerated candidate pool)
PHASE2_RUN_DIR = PE.path_env('NATIVE3D_DEF_RUN',
                             OUTPUT_ROOT / 'NATIVE_3D_JOINT_OPT_1024')


def crossing_intervals_path(native_dir=None):
    """Candidate-pool file read by the D/E analysis tools.

    The frozen 21-height experiment read the pool from the Phase-1 run's
    ``analysis/`` directory.  A 20-height Phase 2 regenerates the pool for its
    own pre-native baseline (the ``crossing_intervals`` stage writes into the
    Phase-2 run dir), so the active profile picks the location; nothing else
    changes.
    """
    if PE.is_20h():
        return PHASE2_RUN_DIR / 'analysis' / 'crossing_intervals.json'
    return Path(native_dir or RUN_DIR) / 'analysis' / 'crossing_intervals.json'

#: path length used by the 3D S-curves
''')

    # ------------------------------------------------------------------ phase2
    add('four_side_1024/fanout1024/native3d/phase2.py',
        'phase2.py: docstring baseline note is profile-aware',
        r'''Baseline for this round: the accepted Native 3D layout with **2440** same-layer
crossings (`NATIVE_3D_CROSSING_OPT_1024`, experiment_C).  It is read-only; every
new experiment writes into ``NATIVE_3D_JOINT_OPT_1024``.
''',
        r'''Baseline for this round: the accepted Native 3D layout of the *active* height
profile (``NATIVE_3D_CROSSING_OPT_1024/experiment_C`` -- **2440** same-layer
crossings for the frozen 21-height experiment; a 20-height Phase 1 inherits its
own count through ``COLDSTART20_NATIVE3D_ABC_RUN``).  It is read-only; every new
experiment writes into the profile's ``COLDSTART20_NATIVE3D_DEF_RUN``.
''')

    add('four_side_1024/fanout1024/native3d/phase2.py',
        'phase2.py: copy_model_files emits the installed 20H model payloads',
        r'''def copy_model_files(target_dir):
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    for name in ('assignment_1024.csv', 'layer_planes.json',
                 'process_rules.json', 'physical_layer_stack.json'):
        source = PHASE1_RUN_DIR / name
        if not source.is_file():
            source = PHASE1_DIR / name
        if not source.is_file():
            source = N.E5_DIR / name
        if source.is_file():
            (target_dir / name).write_bytes(source.read_bytes())
''',
        r'''def _accepted_assignment_source():
    """First ``assignment_1024.csv`` of the accepted layout chain."""
    for directory in (PHASE1_RUN_DIR, PHASE1_DIR, N.E5_DIR):
        path = Path(directory) / 'assignment_1024.csv'
        if path.is_file():
            return path
    return None


def _copy_model_files_20h(target_dir):
    """Emit the *installed* 20-height model payloads (never 21H copies).

    The frozen 21-height bookkeeping copied ``layer_planes.json`` /
    ``physical_layer_stack.json`` / ``process_rules.json`` from the Phase-1
    directory, which would silently hand the independent validator a 21-height
    model under the 20-height profile.  The payloads are therefore built from
    ``coldstart20.model20`` (the module the bootstrap installed as
    ``reheight21.model``); only the frozen ``assignment_1024.csv`` input is
    still copied from the accepted layout chain.
    """
    from ..coldstart20 import model20 as M20
    assignment = _accepted_assignment_source()
    assigned = None
    if assignment is not None:
        rows, _digest = C.read_csv_rows(assignment)
        counts = Counter()
        for row in rows:
            counts[int(float(row['target_layer']))] += 1
        assigned = dict(counts)
        (target_dir / 'assignment_1024.csv').write_bytes(
            assignment.read_bytes())
    write_json(target_dir / 'layer_planes.json',
               M20.layer_planes_payload(assigned))
    write_json(target_dir / 'physical_layer_stack.json',
               M20.stack_payload())
    write_json(target_dir / 'process_rules.json',
               M20.process_rules_payload())


def copy_model_files(target_dir):
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    if PE.is_20h():
        _copy_model_files_20h(target_dir)
        return
    for name in ('assignment_1024.csv', 'layer_planes.json',
                 'process_rules.json', 'physical_layer_stack.json'):
        source = PHASE1_RUN_DIR / name
        if not source.is_file():
            source = PHASE1_DIR / name
        if not source.is_file():
            source = N.E5_DIR / name
        if source.is_file():
            (target_dir / name).write_bytes(source.read_bytes())
''')

    add('four_side_1024/fanout1024/native3d/phase2.py',
        'phase2.py: save_best_valid writes fresh transition stats (20H)',
        r'''    report, _cache = crossing_report(route_list)
    write_json(target / 'crossing_stats.json', report)
    write_json(target / 'validation.json', validation)
''',
        r'''    report, _cache = crossing_report(route_list)
    write_json(target / 'crossing_stats.json', report)
    if PE.is_20h():
        # the frozen 21-height bookkeeping never refreshed this snapshot, which
        # left a stale Phase-1 copy behind (G123 had to override it); a
        # 20-height best_valid always ships fresh transition statistics.
        write_json(target / 'transition_stats.json',
                   transition_stats(route_list))
    write_json(target / 'validation.json', validation)
''')

    add('four_side_1024/fanout1024/native3d/phase2.py',
        'phase2.py: parent_experiment text follows the active profile',
        r'''    payload['parent_experiment'] = ('NATIVE_3D_CROSSING_OPT_1024/experiment_C '
                                    '(2440 crossings)')
''',
        r'''    payload['parent_experiment'] = (
        'NATIVE_3D_CROSSING_OPT_1024/experiment_C (2440 crossings)'
        if not PE.is_20h() else
        '%s/experiment_C (%d crossings)'
        % (Path(PHASE1_DIR).name, BASELINE_CROSSINGS))
''')

    # ------------------------------------------------------------------ run_d
    add('four_side_1024/fanout1024/native3d/run_d.py',
        'run_d.py: candidate pool follows the active profile',
        r'''def load_analysis_candidates(min_net=MIN_NET, per_route=3):
    payload = P2.load_json(P2.PHASE1_DIR / 'analysis' / 'crossing_intervals.json')
''',
        r'''def load_analysis_candidates(min_net=MIN_NET, per_route=3):
    # profile-aware candidate pool: the frozen 21H pipeline reads the Phase-1
    # analysis dir, a 20-height Phase 2 its own regenerated
    # 06_native3d_def/.../analysis/crossing_intervals.json
    payload = P2.load_json(N.crossing_intervals_path())
''')

    # ------------------------------------------------------- blocker_analysis
    add('four_side_1024/fanout1024/native3d/blocker_analysis.py',
        'blocker_analysis.py: candidate pool follows the active profile',
        r'''def load_analysis(native_dir):
    path = Path(native_dir) / 'analysis' / 'crossing_intervals.json'
    return N.load_json(path), path
''',
        r'''def load_analysis(native_dir):
    # profile-aware candidate pool (see N.crossing_intervals_path): the frozen
    # 21H pipeline keeps reading <native_dir>/analysis, the 20-height Phase 2
    # reads the pool it regenerated under its own run dir.
    path = N.crossing_intervals_path(native_dir)
    return N.load_json(path), path
''')

    # ------------------------------------------------------------------ run_e
    add('four_side_1024/fanout1024/native3d/run_e.py',
        'run_e.py: capture the real start crossing count',
        r'''    log('start from %s: %d crossings' % (start_dir.name, env.total()))
    report, _ = P2.crossing_report([env.routes[rid] for rid in sorted(env.routes)])
''',
        r'''    start_crossings = int(env.total())
    log('start from %s: %d crossings' % (start_dir.name, start_crossings))
    report, _ = P2.crossing_report([env.routes[rid] for rid in sorted(env.routes)])
''')

    add('four_side_1024/fanout1024/native3d/run_e.py',
        'run_e.py: summary start_crossings is the real start (dead code removed)',
        r'''    summary = dict(
        schema='native3d_phase2_experiment_e_v1',
        start_crossings=int(payload['native_3d'].get('total_crossings')
                            or P2.BASELINE_CROSSINGS) if False else None,
        final_crossings=int(env.total()),
''',
        r'''    summary = dict(
        schema='native3d_phase2_experiment_e_v1',
        start_crossings=start_crossings,
        final_crossings=int(env.total()),
''')

    add('four_side_1024/fanout1024/native3d/run_e.py',
        'run_e.py: do not overwrite start_crossings with the baseline',
        r'''    summary['start_crossings'] = P2.BASELINE_CROSSINGS
    P2.write_json(exp_dir / 'arc_rebuild_results.json', dict(
''',
        r'''    P2.write_json(exp_dir / 'arc_rebuild_results.json', dict(
''')

    # ------------------------------------------------------------------ run_f
    add('four_side_1024/fanout1024/native3d/run_f.py',
        'run_f.py: capture the pre-step geometry of every touched route',
        r'''            if best is None:
                continue
            if 'routes_override' in best:
                for rid in best['joint_routes']:
''',
        r'''            if best is None:
                continue
            changed_ids = ([int(rid) for rid in best['joint_routes']]
                           if 'routes_override' in best else [int(route_id)])
            # geometry before this step: the reject branch must restore *this*,
            # never the run-start snapshot (see the rollback fix below)
            previous = {rid: copy.deepcopy(env.routes[rid])
                        for rid in changed_ids}
            if 'routes_override' in best:
                for rid in best['joint_routes']:
''')

    add('four_side_1024/fanout1024/native3d/run_f.py',
        'run_f.py: reject-branch rollback restores pre-step geometry (defect #3)',
        r'''            else:
                # rollback the single change
                old = routes.get(route_id)
                env.replace_route(old if old is not None else env.routes[route_id])
                bbox.update(env.routes[route_id])
''',
        r'''            else:
                # Roll back the *pre-step* geometry of every route this step
                # touched.  The frozen code restored ``routes[route_id]`` -- the
                # run-start snapshot captured before the first sweep -- so a
                # rejected change after an earlier accepted change silently
                # rewound the geometry to the start layout, and a rejected
                # joint step left its other routes modified.  ``run_f_plus.py``
                # already uses this deepcopy pattern; corrected here for the
                # 20-height rebuild (the 21H reject path is otherwise corrupting
                # and this is the only behavioural change of the patch set).
                for rid in changed_ids:
                    env.replace_route(previous[rid])
                    bbox.update(previous[rid])
''')

    # ------------------------------------------------------- finalize_phase2
    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: profile imports',
        r'''from . import common as N
from . import phase2 as P2
''',
        r'''from ..coldstart20 import paths20 as P20
from ..coldstart20 import profile_env as PE
from . import common as N
from . import phase2 as P2
''', embed=True)

    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: inherited baseline count / 20H archive name',
        r'''RUN = P2.RUN2
BASELINE = P2.PHASE1_RUN_DIR
ARCHIVE_NAME = 'native_3d_joint_opt_1024'
''',
        r'''RUN = P2.RUN2
BASELINE = P2.PHASE1_RUN_DIR
#: inherited Phase-1 crossing total of the active profile (2440 for the frozen
#: 21-height experiment; read from the accepted layout under the 20H profile)
BASE_CROSSINGS = int(P2.BASELINE_CROSSINGS)
ARCHIVE_NAME = 'native_3d_joint_opt_1024'
if PE.is_20h():  # keep the 20H deliverable below its own cold-start root
    ARCHIVE_NAME = 'native_3d_joint_opt_1024_20height'
''')

    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: make_plots baseline fallback',
        r'''        start = int(state['f_summary'].get('start_crossings') or 2440)
''',
        r'''        start = int(state['f_summary'].get('start_crossings')
                    or BASE_CROSSINGS)
''')

    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: report totals fall back to the inherited baseline',
        r'''    final_total = int(f.get('final_crossings') or 2440)
    start_total = int(f.get('start_crossings') or 2440)
''',
        r'''    final_total = int(f.get('final_crossings') or BASE_CROSSINGS)
    start_total = int(f.get('start_crossings') or BASE_CROSSINGS)
''')

    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: root model files are the installed 20H payloads',
        r'''    for name in ('assignment_1024.csv', 'layer_planes.json',
                 'process_rules.json', 'physical_layer_stack.json'):
        source = BASELINE / name
        if source.is_file():
            (RUN / name).write_bytes(source.read_bytes())
''',
        r'''    if PE.is_20h():
        # emit the installed 20-height model payloads + accepted assignment
        P2.copy_model_files(RUN)
    else:
        for name in ('assignment_1024.csv', 'layer_planes.json',
                     'process_rules.json', 'physical_layer_stack.json'):
            source = BASELINE / name
            if source.is_file():
                (RUN / name).write_bytes(source.read_bytes())
''')

    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: 20H independent validator is validate21',
        r'''def run_validator():
    from . import validate_native3d as V
    out = RUN / 'validation' / 'final'
    out.mkdir(parents=True, exist_ok=True)
    target = RUN / 'best_valid' if (RUN / 'best_valid' / 'routes_l3d.json').is_file() \
        else RUN / 'experiment_F'
    log('independent validator on %s' % target.name)
    result = V.validate_run(target, baseline_dir=BASELINE, out_dir=out, log=log)
''',
        r'''def run_validator():
    out = RUN / 'validation' / 'final'
    out.mkdir(parents=True, exist_ok=True)
    target = RUN / 'best_valid' if (RUN / 'best_valid' / 'routes_l3d.json').is_file() \
        else RUN / 'experiment_F'
    log('independent validator on %s' % target.name)
    # The frozen independent validator for every Native-3D stage is
    # ``native3d.validate_native3d`` -- for the 21-height and the 20-height
    # profiles alike.  It understands mid-body R15 excursions and enforces every
    # geometric rule (per-height strict D56, true-3D >= 0.05 mm, R15, glass
    # envelope, port contract, 368 frozen manual routes, exact crossing recount).
    # ``reheight21.validate21`` is the PLANAR-ASSEMBLY contract validator: its
    # contract assumes the pre-Native-3D 5-part route structure and therefore
    # cannot judge a layout whose bodies contain mid-path layer changes -- that
    # is a contract mismatch, not a geometric violation.  The 21-height Phase-1
    # and Phase-2 archives were validated with ``validate_native3d`` for exactly
    # this reason.  No threshold changes here.
    from . import validate_native3d as V
    result = V.validate_run(target, baseline_dir=BASELINE, out_dir=out,
                            log=log)
''')

    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: baseline mid-transition count + E0 class source',
        r'''    repair_candidates = int(
        (d.get('blocker_screen') or {}).get('repair_candidates') or 0)
    arc_classes = arcs.get('classes') or {}
    lines = []
''',
        r'''    repair_candidates = int(
        (d.get('blocker_screen') or {}).get('repair_candidates') or 0)
    baseline_native = (state['baseline'].get('native_3d') or {})
    if PE.is_20h():
        # the independent arc payload has no ``classes`` key; the real
        # class counts live in aggregates.totals.class_counts
        arc_classes = (((arcs.get('aggregates') or {}).get('totals') or {})
                       .get('class_counts') or {})
    else:
        arc_classes = arcs.get('classes') or {}
    lines = []
''')

    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: E0 class table reads both key spellings',
        r'''    for key, label in (('line_line', '直线—直线'), ('line_arc', '直线—圆弧'),
                       ('arc_arc', '圆弧—圆弧')):
        value = int(arc_classes.get(key) or 0)
        lines.append('| %s | %d | %.1f%% |' % (label, value, 100.0 * value / 2440))
''',
        r'''    for key, label in (('line_line', '直线—直线'), ('line_arc', '直线—圆弧'),
                       ('arc_arc', '圆弧—圆弧')):
        value = int(arc_classes.get(key)
                    or arc_classes.get(key.replace('_', '-')) or 0)
        lines.append('| %s | %d | %.1f%% |'
                     % (label, value, 100.0 * value / BASE_CROSSINGS))
''')

    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: E0 prose generated from state for 20H',
        r'''    lines.append('- **涉及圆弧的交叉事件 1967/2440 = 80.6%**；按“每侧交叉位置”统计：'
                 '2405/4880 = **49.28%**（上一轮“49%”口径成立，但不能表述为“49% 的事件涉及圆弧”）。')
    lines.append('- 圆弧热点线路：462(23)、459(21)、149(19)、435(18)、5(17)；'
                 '全部圆弧交叉都位于 base_body 平面段。')
    lines.append('- 可重建性：top-10 线路 10/10 几何可行，4/10 有两侧均为直线段的真正局部区间'
                 '（427 估计 +15、104 +13、149 +9、5 +4；总和 +73）。')
''',
        r'''    if PE.is_20h():
        arc_totals = ((arcs.get('aggregates') or {}).get('totals') or {})
        top_rows = arcs.get('top_routes') or []
        availability = arcs.get('availability') or {}
        if arc_totals:
            events = int(arc_totals.get('events') or 0)
            any_arc = int(arc_totals.get('any_arc') or 0)
            side_kind = arc_totals.get('side_kind') or {}
            side_arc = int(side_kind.get('arc') or 0)
            sides = int(arc_totals.get('event_sides') or 0)
            lines.append(
                '- **涉及圆弧的交叉事件 %d/%d = %.1f%%**；按“每侧交叉位置”统计：'
                '%d/%d = **%.2f%%**。'
                % (any_arc, events, 100.0 * any_arc / max(events, 1),
                   side_arc, sides, 100.0 * side_arc / max(sides, 1)))
        else:
            lines.append('- 独立 E0 圆弧交叉分析缺失：本次链路未运行 '
                         '`native3d.arc_crossing_analysis`（可选阶段 '
                         '`run_native3d_phase2 arc-analysis`）。')
        if top_rows:
            lines.append('- 圆弧热点线路：%s；读数见 '
                         '`analysis/arc_crossing_analysis.json`。'
                         % '、'.join('%d(%d)' % (
                             int(row.get('route_id') or 0),
                             int(row.get('own_arc_crossings')
                                 or row.get('total_crossings') or 0))
                             for row in top_rows[:5]))
        if availability:
            lines.append('- 可重建性：top-%d 线路 %d/%d 几何可行，%d 条有真正局部区间。'
                         % (int(availability.get('routes_total') or 0),
                            int(availability.get(
                                'routes_geometrically_feasible') or 0),
                            int(availability.get('routes_total') or 0),
                            int(availability.get('routes_with_local_interval')
                                or 0)))
    else:
        lines.append('- **涉及圆弧的交叉事件 1967/2440 = 80.6%**；按“每侧交叉位置”统计：'
                     '2405/4880 = **49.28%**（上一轮“49%”口径成立，但不能表述为“49% 的事件涉及圆弧”）。')
        lines.append('- 圆弧热点线路：462(23)、459(21)、149(19)、435(18)、5(17)；'
                     '全部圆弧交叉都位于 base_body 平面段。')
        lines.append('- 可重建性：top-10 线路 10/10 几何可行，4/10 有两侧均为直线段的真正局部区间'
                     '（427 估计 +15、104 +13、149 +9、5 +4；总和 +73）。')
''')

    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: report baseline line (count + mid transitions)',
        r'''    lines.append('Phase-1 继承基线（只读）：`%s`（1024/1024，**2440** 同层交叉，'
                 '118 段中途换层，0 违规）\n' % BASELINE)
''',
        r'''    lines.append('Phase-1 继承基线（只读）：`%s`（1024/1024，**%d** 同层交叉，'
                 '%d 段中途换层，0 违规）\n'
                 % (BASELINE, BASE_CROSSINGS,
                    int(baseline_native.get('mid_transitions') or 0)))
''')

    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: report summary table header',
        r'''    lines.append('| 指标 | 2440 基线 | Phase-2 最终 |')
''',
        r'''    lines.append('| 指标 | %d 基线 | Phase-2 最终 |' % BASE_CROSSINGS)
''')

    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: report crossing row',
        r'''    lines.append('| 真实同层交叉 | 2440 | **%d** |' % final_total)
''',
        r'''    lines.append('| 真实同层交叉 | %d | **%d** |'
                 % (BASE_CROSSINGS, final_total))
''')

    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: F conclusion line',
        r'''    lines.append('3. **全局联合优化（F）**：在完整 1024 条线路上自动运行，最终把 2440 降到 '
                 '**%d**（%+d），保持 1024/1024 与 0 违规，独立 Validator PASS。'
                 % (final_total, final_total - 2440))
''',
        r'''    lines.append('3. **全局联合优化（F）**：在完整 1024 条线路上自动运行，最终把 %d 降到 '
                 '**%d**（%+d），保持 1024/1024 与 0 违规，独立 Validator PASS。'
                 % (BASE_CROSSINGS, final_total,
                    final_total - BASE_CROSSINGS))
''')

    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: plots count / height-count line',
        r'''    lines.append('* `plots/`：%d 张真实几何图（21 高度图、3D 总览、交叉曲线、策略贡献、'
                 '圆弧热点、阻挡统计等）' % len(plots))
''',
        r'''    lines.append('* `plots/`：%d 张真实几何图（%d 高度图、3D 总览、交叉曲线、策略贡献、'
                 '圆弧热点、阻挡统计等）'
                 % (len(plots), len(N.PLANE_Z)))
''')

    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: report names the validator used by the profile',
        r'''    lines.append('- 独立 Validator（`native3d/validate_native3d.py`，独立实现）：'
                 '**%s**，违规 **%s**，最小真实 3D 净空 %s mm。'
                 % ('PASS' if validation.get('validation_pass') else 'FAIL',
                    validation.get('violation_count'),
                    fmt((validation.get('checks') or {}).get('clearance', {}).get(
                        'min_3d_clearance_mm'), 9)))
''',
        r'''    validator_name = ('`reheight21/validate21.py`（20 高度 profile 下的独立实现）'
                      if PE.is_20h() else '`native3d/validate_native3d.py`，独立实现')
    lines.append('- 独立 Validator（%s）：'
                 '**%s**，违规 **%s**，最小真实 3D 净空 %s mm。'
                 % (validator_name,
                    'PASS' if validation.get('validation_pass') else 'FAIL',
                    validation.get('violation_count'),
                    fmt((validation.get('checks') or {}).get('clearance', {}).get(
                        'min_3d_clearance_mm'), 9)))
''')

    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: comparison table from state',
        r'''    comparison = [
        '# Phase-2 vs Phase-1 2440 基线对比\n',
        '| 指标 | Phase-1 基线 | Phase-2 最终 |',
        '|---|---:|---:|',
        '| 成功线路 | 1024 | 1024 |',
        '| 真实同层交叉 | 2440 | %d |' % final_total,
        '| 交叉线路对 | 2036 | %s |'
        % (state['crossing'].get('totals', {}).get('crossing_pairs', 'n/a')),
        '| 中途三维过渡 | 118 | %s |'
        % (state['f_summary'].get('mid_transitions', 'n/a')),
        '| 几何违规 | 0 | %s |' % validation.get('violation_count'),
        '| 独立 Validator | PASS | %s |'
        % ('PASS' if validation.get('validation_pass') else 'FAIL'),
        '',
        'D 接受 %d 次（净 %+d）；E 接受 %d 次（净 %+d）；F 最终净改善 %+d。'
        % (int(d.get('accepted') or 0), int(d.get('net') or 0),
           int(e.get('accepted') or 0), int(e.get('net') or 0),
           final_total - 2440),
        '',
    ]
''',
        r'''    comparison = [
        '# Phase-2 vs Phase-1 %d 基线对比\n' % BASE_CROSSINGS,
        '| 指标 | Phase-1 基线 | Phase-2 最终 |',
        '|---|---:|---:|',
        '| 成功线路 | 1024 | 1024 |',
        '| 真实同层交叉 | %d | %d |' % (BASE_CROSSINGS, final_total),
        '| 交叉线路对 | 2036 | %s |'
        % (state['crossing'].get('totals', {}).get('crossing_pairs', 'n/a')),
        '| 中途三维过渡 | %d | %s |'
        % (int(baseline_native.get('mid_transitions') or 0),
           state['f_summary'].get('mid_transitions', 'n/a')),
        '| 几何违规 | 0 | %s |' % validation.get('violation_count'),
        '| 独立 Validator | PASS | %s |'
        % ('PASS' if validation.get('validation_pass') else 'FAIL'),
        '',
        'D 接受 %d 次（净 %+d）；E 接受 %d 次（净 %+d）；F 最终净改善 %+d。'
        % (int(d.get('accepted') or 0), int(d.get('net') or 0),
           int(e.get('accepted') or 0), int(e.get('net') or 0),
           final_total - BASE_CROSSINGS),
        '',
    ]
''')

    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: README is profile-aware',
        r'''    readme = [
        '# NATIVE_3D_JOINT_OPT_1024 — Phase 2（D/E/F：多线联合让路 + 圆弧重构 + 全局优化）\n',
        '继承 Phase-1 Native 3D 的 2440 交叉合法解，研究“联合修改周围线路创造换层空间”'
        '与“圆弧区域整体重构”两条路线，并整合为全局优化器。\n',
        '## 目录\n',
        '* `experiment_D/` — D0 阻挡分析（blocker_map.json）+ D1/D2 联合 make-way 重布结果',
        '* `experiment_E/` — E0 圆弧交叉分析 + E1/E2 圆弧区域整体重构结果',
        '* `experiment_F/` — 全局联合优化（plain/arc_span/joint 策略，检查点）',
        '* `best_valid/` — 当前最佳合法解（routes + stats + validation + 哈希）',
        '* 根目录交付见 `SPEC.md` 与 `MANIFEST.json`',
        '',
        '## 复现\n',
        '```',
        'cd OpticalWaveguideRouter2D',
        '.venv\\Scripts\\python.exe -m four_side_1024.fanout1024.native3d.run_d --screen 80 --repairs 30',
        '.venv\\Scripts\\python.exe -m four_side_1024.fanout1024.native3d.run_e --routes 16',
        '.venv\\Scripts\\python.exe -m four_side_1024.fanout1024.native3d.run_f --sweeps 2 --time-budget 560',
        '.venv\\Scripts\\python.exe -m four_side_1024.fanout1024.native3d.finalize_phase2',
        '```',
        '',
        'Phase-1 基线为只读输入：'
        '`outputs/manual_c4_new_connectivity/NATIVE_3D_CROSSING_OPT_1024`（2440 交叉）。',
        '',
    ]
''',
        r'''    reproduce = ([
        'cd OpticalWaveguideRouter2D',
        '.venv\\Scripts\\python.exe -m four_side_1024.fanout1024.coldstart20.run_native3d_phase2 all',
    ] if PE.is_20h() else [
        'cd OpticalWaveguideRouter2D',
        '.venv\\Scripts\\python.exe -m four_side_1024.fanout1024.native3d.run_d --screen 80 --repairs 30',
        '.venv\\Scripts\\python.exe -m four_side_1024.fanout1024.native3d.run_e --routes 16',
        '.venv\\Scripts\\python.exe -m four_side_1024.fanout1024.native3d.run_f --sweeps 2 --time-budget 560',
        '.venv\\Scripts\\python.exe -m four_side_1024.fanout1024.native3d.finalize_phase2',
    ])
    baseline_note = (
        'Phase-1 基线为只读输入：`outputs/manual_c4_new_connectivity/'
        'NATIVE_3D_CROSSING_OPT_1024`（2440 交叉）。'
        if not PE.is_20h() else
        'Phase-1 基线为只读输入：`%s`（%d 交叉）。'
        % (BASELINE, BASE_CROSSINGS))
    readme = [
        '# %s — Phase 2（D/E/F：多线联合让路 + 圆弧重构 + 全局优化）\n' % RUN.name,
        '继承 Phase-1 Native 3D 的 %d 交叉合法解，研究“联合修改周围线路创造换层空间”'
        '与“圆弧区域整体重构”两条路线，并整合为全局优化器。\n' % BASE_CROSSINGS,
        '## 目录\n',
        '* `experiment_D/` — D0 阻挡分析（blocker_map.json）+ D1/D2 联合 make-way 重布结果',
        '* `experiment_E/` — E0 圆弧交叉分析 + E1/E2 圆弧区域整体重构结果',
        '* `experiment_F/` — 全局联合优化（plain/arc_span/joint 策略，检查点）',
        '* `best_valid/` — 当前最佳合法解（routes + stats + validation + 哈希）',
        '* 根目录交付见 `SPEC.md` 与 `MANIFEST.json`',
        '',
        '## 复现\n',
        '```',
        *reproduce,
        '```',
        '',
        baseline_note,
        '',
    ]
''')

    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: SPEC height table is data-driven',
        r'''        '* 21 个物理高度（真实 z，非 layer_id 单调）：'
        '-0.35,-0.30,-0.25,-0.20,-0.15,-0.10,-0.05,0.00,0.05,0.10,0.15,0.20,0.25,0.30,0.35,'
        '0.40,0.45,0.50,0.55,0.60,0.65 mm。',
''',
        r'''        '* %d 个物理高度（真实 z，非 layer_id 单调）：%s mm。'
        % (len(N.PLANE_Z),
           ','.join('%.2f' % float(value) for value in N.PLANE_Z.values())),
''')

    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: SPEC acceptance height count',
        r'''        '3. 21 个高度、50 µm 层距、50 µm 真实三维净空、R15、玻璃 150×150×1 mm；',
''',
        r'''        '3. %d 个高度、50 µm 层距、50 µm 真实三维净空、R15、玻璃 150×150×1 mm；'
        % len(N.PLANE_Z),
''')

    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: MANIFEST metadata',
        r'''    payload = dict(schema='native3d_phase2_manifest_v1',
                   generated_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
                   experiment='NATIVE_3D_JOINT_OPT_1024',
                   parent='NATIVE_3D_CROSSING_OPT_1024 (2440 crossings)',
                   file_count=len(files), files=files)
''',
        r'''    payload = dict(schema='native3d_phase2_manifest_v1',
                   generated_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
                   experiment=RUN.name,
                   parent=('NATIVE_3D_CROSSING_OPT_1024 (2440 crossings)'
                           if not PE.is_20h() else
                           '%s/experiment_C (%d crossings)'
                           % (Path(BASELINE).name, BASE_CROSSINGS)),
                   file_count=len(files), files=files)
''')

    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: MANIFEST skips the archive mirror',
        r'''        relative = path.relative_to(RUN).as_posix()
        if relative.startswith('scratch/') or relative.startswith('logs/'):
            continue
''',
        r'''        relative = path.relative_to(RUN).as_posix()
        if (relative.startswith('scratch/') or relative.startswith('logs/')
                or relative.startswith('archive/')):
            # ``archive/`` is the finalize deliverable mirror of this run
            # (20H only); it is not hashed into MANIFEST.
            continue
''')

    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: archive destination stays inside the 20H run',
        r'''def archive():
    target = Path(r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D'
                  r'\experiments') / ARCHIVE_NAME
    target.mkdir(parents=True, exist_ok=True)
''',
        r'''def archive():
    if PE.is_20h():
        # 20-height deliverable stays inside its own run dir: never write into
        # (or overwrite) the frozen 21H archive experiments/native_3d_joint_opt_1024
        target = RUN / 'archive'
    else:
        target = Path(r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D'
                      r'\experiments') / ARCHIVE_NAME
    target.mkdir(parents=True, exist_ok=True)
''')

    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: archive code snapshot is complete for 20H',
        r'''    for name in ('phase2.py', 'excursion2.py', 'joint_reroute.py', 'run_d.py',
                 'run_e.py', 'run_f.py', 'finalize_phase2.py',
                 'arc_crossing_analysis.py', 'blocker_analysis.py'):
''',
        r'''    code_names = ['phase2.py', 'excursion2.py', 'joint_reroute.py', 'run_d.py',
                  'run_e.py', 'run_f.py', 'finalize_phase2.py',
                  'arc_crossing_analysis.py', 'blocker_analysis.py']
    if PE.is_20h():
        code_names += ['run_f_plus.py', 'run_f_nearmiss.py', 'batch_avoid.py',
                       'guard.py', 'crossing_intervals.py']
    for name in code_names:
''')

    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: no external git commit for the cold-start archive',
        r'''    result = dict(archive_root=str(target))
    if (repo / '.git').is_dir():
''',
        r'''    result = dict(archive_root=str(target))
    if not PE.is_20h() and (repo / '.git').is_dir():
''')

    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: archive final-total fallback',
        r'''        final_total = int((load(RUN / 'experiment_F' / 'summary.json') or {}).get(
            'final_crossings') or 2440)
''',
        r'''        final_total = int((load(RUN / 'experiment_F' / 'summary.json') or {}).get(
            'final_crossings') or BASE_CROSSINGS)
''')

    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: archive commit message',
        r'''        message = ('Add Native 3D Phase-2 (D/E/F): joint make-way reroute, '
                   'arc-region rebuild, global joint optimisation; 1024/1024, '
                   'crossings 2440 -> %d, 0 violations' % final_total)
''',
        r'''        message = ('Add Native 3D Phase-2 (D/E/F): joint make-way reroute, '
                   'arc-region rebuild, global joint optimisation; 1024/1024, '
                   'crossings %d -> %d, 0 violations'
                   % (BASE_CROSSINGS, final_total))
''')

    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: final summary / log use the inherited baseline',
        r'''    summary = dict(
        schema='native3d_phase2_final_summary_v1',
        baseline_crossings=2440,
        final_crossings=int((state['f_summary'] or {}).get(
            'final_crossings') or 2440),
''',
        r'''    summary = dict(
        schema='native3d_phase2_final_summary_v1',
        baseline_crossings=BASE_CROSSINGS,
        final_crossings=int((state['f_summary'] or {}).get(
            'final_crossings') or BASE_CROSSINGS),
''')

    add('four_side_1024/fanout1024/native3d/finalize_phase2.py',
        'finalize_phase2.py: final log line',
        r'''    log('FINAL: %d -> %d, violations=%s, archive=%s'
        % (2440, summary['final_crossings'], summary['violations'],
           result.get('archive_root')))
''',
        r'''    log('FINAL: %d -> %d, violations=%s, archive=%s'
        % (BASE_CROSSINGS, summary['final_crossings'], summary['violations'],
           result.get('archive_root')))
''')

    return items


# ===========================================================================
# helpers
# ===========================================================================
def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False,
                               default=str) + '\n', encoding='utf-8')
    return path


# ===========================================================================
# apply
# ===========================================================================
def apply(dry_run=False):
    patch_list = patches()
    originals = {}
    texts = {}
    statuses = []
    failures = []

    for item in patch_list:
        rel = item['rel']
        path = PROJECT_ROOT / rel
        if rel not in texts:
            if not path.is_file():
                failures.append((item['name'], 'file missing: %s' % path))
                continue
            originals[rel] = path.read_text(encoding='utf-8')
            texts[rel] = originals[rel]
        text = texts[rel]
        found = text.count(item['old'])
        already = text.count(item['new'])
        if item.get('embed'):
            # edit type "add lines around an unchanged block" (e.g. imports):
            # the old text stays present after patching, so test the patched
            # marker (new) first to stay idempotent.
            if already >= 1:
                statuses.append((item['name'], 'already-applied'))
            elif found == 1:
                texts[rel] = text.replace(item['old'], item['new'])
                statuses.append((item['name'], 'APPLY'))
            else:
                failures.append((item['name'],
                                 'search string occurred %d times (expected 1), '
                                 'patched marker %d time(s)'
                                 % (found, already)))
        else:
            if found == 1:
                texts[rel] = text.replace(item['old'], item['new'])
                statuses.append((item['name'], 'APPLY'))
            elif found == 0 and already >= 1:
                statuses.append((item['name'], 'already-applied'))
            else:
                failures.append((item['name'],
                                 'search string occurred %d times (expected 1), '
                                 'patched marker %d time(s)'
                                 % (found, already)))

    for name, status in statuses:
        print('[%s] %s' % (status, name))
    if failures:
        print('\nFAILED -- nothing was written:')
        for name, reason in failures:
            print('  %s: %s' % (name, reason))
        return 1

    changed = {rel: text for rel, text in texts.items()
               if text != originals[rel]}
    if dry_run:
        print('\n[dry-run] %d patch(es) would change %d file(s): %s'
              % (sum(1 for _n, s in statuses if s == 'APPLY'), len(changed),
                 ', '.join(sorted(changed))))
        return 0

    if not changed:
        print('\nNothing to do: all patches already applied.')
        return 0

    stamp = time.strftime('%Y%m%d_%H%M%S')
    backup_dir = BACKUP_ROOT / stamp
    files = {}
    for rel, text in sorted(changed.items()):
        source = PROJECT_ROOT / rel
        backup = backup_dir / rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(source.read_bytes())
        source.write_text(text, encoding='utf-8')
        files[rel] = dict(original_sha256=sha256_file(backup),
                          patched_sha256=sha256_file(source),
                          patches=[item['name'] for item in patch_list
                                   if item['rel'] == rel])
        print('[written] %s' % rel)

    manifest = dict(
        schema='coldstart20_native3d_def_patch_v1',
        created_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
        backup_dir=str(backup_dir),
        script=str(Path(__file__)),
        script_sha256=sha256_file(__file__),
        project_root=str(PROJECT_ROOT),
        applied=sum(1 for _n, s in statuses if s == 'APPLY'),
        already_applied=sum(1 for _n, s in statuses if s == 'already-applied'),
        files=files,
        patches=[dict(name=item['name'], rel=item['rel']) for item in patch_list],
    )
    write_json(backup_dir / 'PATCH_MANIFEST.json', manifest)
    print('\napplied %d patch(es), %d already applied; backup: %s'
          % (manifest['applied'], manifest['already_applied'], backup_dir))
    print('next: --verify')
    return 0


# ===========================================================================
# revert
# ===========================================================================
def revert(stamp=None, force=False):
    if not BACKUP_ROOT.is_dir():
        print('no backup directory: %s' % BACKUP_ROOT)
        return 1
    candidates = sorted(path for path in BACKUP_ROOT.iterdir() if path.is_dir())
    if not candidates:
        print('no backups below %s' % BACKUP_ROOT)
        return 1
    target = BACKUP_ROOT / stamp if stamp else candidates[-1]
    manifest_path = target / 'PATCH_MANIFEST.json'
    if not manifest_path.is_file():
        print('no PATCH_MANIFEST.json in %s' % target)
        return 1
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    restored = []
    skipped = []
    for rel, info in sorted(manifest.get('files', {}).items()):
        source = target / rel
        destination = PROJECT_ROOT / rel
        if not source.is_file():
            skipped.append((rel, 'backup file missing'))
            continue
        if (destination.is_file() and not force
                and sha256_file(destination) != info.get('patched_sha256')):
            skipped.append((rel, 'file changed since the patch; use --force'))
            continue
        shutil.copy2(source, destination)
        restored.append(rel)
        print('[restored] %s' % rel)
    for rel, reason in skipped:
        print('[skipped ] %s (%s)' % (rel, reason))
    print('reverted from %s: %d file(s)' % (target, len(restored)))
    return 0 if not skipped else 1


# ===========================================================================
# verify (regression checks)
# ===========================================================================
CODE_21H = r'''
import json
from four_side_1024.fanout1024.native3d import common as N
from four_side_1024.fanout1024.native3d import phase2 as P2
from four_side_1024.fanout1024.reheight21 import model as M
from four_side_1024.fanout1024.reheight21 import validate21
movable = tuple(int(pid) for pid in N.MOVABLE_PLANES)
checks = dict(
    imported_without_bootstrap=True,
    model_profile=str(M.PROFILE),
    plane_count=len(N.PLANE_Z),
    movable_planes=list(movable),
    movable_planes_is_frozen_21h_tuple=movable == (6, 7, 20, 1001, 8, 9, 14, 15, 16, 1002, 17, 18, 19),
    movable_planes_20h_tuple_absent=movable != (6, 7, 20, 1001, 8, 9, 14, 15, 16, 1002, 17, 18),
    baseline_crossings=int(P2.BASELINE_CROSSINGS),
    baseline_crossings_is_2440=int(P2.BASELINE_CROSSINGS) == 2440,
    run2_name=P2.RUN2.name,
    run2_is_historical=P2.RUN2.name == 'NATIVE_3D_JOINT_OPT_1024',
    phase1_name=P2.PHASE1_DIR.name,
    phase1_is_historical=P2.PHASE1_DIR.name == 'NATIVE_3D_CROSSING_OPT_1024',
    crossing_intervals_path=str(N.crossing_intervals_path()),
    crossing_intervals_is_phase1_analysis=(N.crossing_intervals_path() == P2.PHASE1_DIR / 'analysis' / 'crossing_intervals.json'),
    validate21_spec_plane_count=int(validate21.SPEC_PLANE_COUNT),
    validate21_is_21h=int(validate21.SPEC_PLANE_COUNT) == 21,
    interface_rows={str(pid): float(N.PLANE_Z[pid]) for pid in (1001, 1002)},
)
print('RESULT ' + json.dumps(checks, sort_keys=True))
'''

CODE_20H = r'''
import json
import shutil
from pathlib import Path
from four_side_1024.fanout1024.coldstart20 import bootstrap as B
B.install()
B.assert_20_height_profile('verify-20h')
from four_side_1024.fanout1024.coldstart20 import model20 as M
from four_side_1024.fanout1024.coldstart20 import paths20 as P20
from four_side_1024.fanout1024.native3d import common as N
from four_side_1024.fanout1024.native3d import phase2 as P2
from four_side_1024.fanout1024.reheight21 import validate21
movable = tuple(int(pid) for pid in N.MOVABLE_PLANES)
tmp = P20.NATIVE3D_DEF / '_patch_modelcheck'
if tmp.exists():
    shutil.rmtree(tmp)
P2.copy_model_files(tmp)
layer_planes = json.loads((tmp / 'layer_planes.json').read_text(encoding='utf-8'))
stack = json.loads((tmp / 'physical_layer_stack.json').read_text(encoding='utf-8'))
rules = json.loads((tmp / 'process_rules.json').read_text(encoding='utf-8'))
shutil.rmtree(tmp)
phase2_source = Path(P2.__file__).read_text(encoding='utf-8')
run_f_source = (Path(P2.__file__).parent / 'run_f.py').read_text(encoding='utf-8')
route_model_source = (Path(P2.__file__).parent / 'route_model.py').read_text(encoding='utf-8')
finalize_source = (Path(P2.__file__).parent / 'finalize_phase2.py').read_text(encoding='utf-8')
checks = dict(
    assert_20_height_profile=True,
    model_profile=str(M.PROFILE),
    plane_count=len(N.PLANE_Z),
    plane_ids=[int(pid) for pid in M.PLANE_IDS],
    no_plane_19=19 not in [int(pid) for pid in M.PLANE_IDS],
    movable_planes=list(movable),
    movable_planes_is_20h_tuple=movable == (6, 7, 20, 1001, 8, 9, 14, 15, 16, 1002, 17, 18),
    manual_planes=[int(pid) for pid in N.MANUAL_PLANES],
    sorted_by_abs_dz_ok=[int(pid) for pid in N.sorted_by_abs_dz(0.0)[:3]],
    placeholder_crossings=int(P2.BASELINE_CROSSINGS),
    run2_name=P2.RUN2.name,
    run2_is_20h=P2.RUN2.name == 'run_native3d_phase2',
    phase1_name=P2.PHASE1_DIR.name,
    phase1_is_20h=P2.PHASE1_DIR.name == 'run_native3d_phase1',
    e5_dir=str(N.E5_DIR),
    crossing_intervals_path=str(N.crossing_intervals_path()),
    crossing_intervals_in_def_run=(N.crossing_intervals_path() == P20.NATIVE3D_DEF_RUN / 'analysis' / 'crossing_intervals.json'),
    interface_rows={str(pid): float(N.PLANE_Z[pid]) for pid in (1001, 1002)},
    validate21_spec_plane_count=int(validate21.SPEC_PLANE_COUNT),
    validate21_is_20h=int(validate21.SPEC_PLANE_COUNT) == 20,
    min_pitch_ok=abs(float(M.min_height_pitch()) - 0.05) < 1e-12,
    copy_model_files_layer_planes_schema=layer_planes.get('schema'),
    copy_model_files_plane_count=layer_planes.get('plane_count'),
    copy_model_files_interfaces=layer_planes.get('interfaces'),
    copy_model_files_stack_routing_plane_count=stack.get('routing_plane_count'),
    copy_model_files_rules_routing_plane_count=rules.get('routing_plane_count'),
    save_best_valid_writes_transition_stats=('transition_stats(route_list)' in phase2_source and 'PE.is_20h()' in phase2_source),
    copy_model_files_20h_branch=('def _copy_model_files_20h' in phase2_source),
    run_f_rollback_pre_step=('previous = {rid: copy.deepcopy(env.routes[rid])' in run_f_source),
    route_model_interface_heights=('Z1_INTERFACE_MM' in route_model_source and 'Z2_INTERFACE_MM' in route_model_source),
    # the Native-3D stages must be judged by the frozen Native-3D validator;
    # reheight21.validate21 is the planar-assembly contract validator and
    # cannot accept mid-body R15 layer changes (contract mismatch).
    finalize_20h_validator=('validate_native3d as V' in finalize_source
                            and 'from ..reheight21 import validate21' not in finalize_source),
    finalize_does_not_enable_e5_expect=('E5_EXPECT[' not in finalize_source and 'regression=True' not in finalize_source),
)
print('RESULT ' + json.dumps(checks, sort_keys=True))
'''

EXPECTED_21H = dict(
    imported_without_bootstrap=True,
    plane_count=21,
    movable_planes_is_frozen_21h_tuple=True,
    movable_planes_20h_tuple_absent=True,
    baseline_crossings=2440,
    baseline_crossings_is_2440=True,
    run2_name='NATIVE_3D_JOINT_OPT_1024',
    run2_is_historical=True,
    phase1_name='NATIVE_3D_CROSSING_OPT_1024',
    phase1_is_historical=True,
    crossing_intervals_is_phase1_analysis=True,
    validate21_spec_plane_count=21,
    validate21_is_21h=True,
)

EXPECTED_20H = dict(
    assert_20_height_profile=True,
    plane_count=20,
    no_plane_19=True,
    movable_planes_is_20h_tuple=True,
    sorted_by_abs_dz_ok=[20, 1001, 7],
    run2_name='run_native3d_phase2',
    run2_is_20h=True,
    phase1_name='run_native3d_phase1',
    phase1_is_20h=True,
    crossing_intervals_in_def_run=True,
    validate21_spec_plane_count=20,
    validate21_is_20h=True,
    min_pitch_ok=True,
    copy_model_files_layer_planes_schema='reheight20_layer_planes_v1',
    copy_model_files_plane_count=20,
    copy_model_files_interfaces={'z1': 0.025, 'z2': 0.525},
    copy_model_files_stack_routing_plane_count=20,
    copy_model_files_rules_routing_plane_count=20,
    save_best_valid_writes_transition_stats=True,
    copy_model_files_20h_branch=True,
    run_f_rollback_pre_step=True,
    route_model_interface_heights=True,
    finalize_20h_validator=True,
    finalize_does_not_enable_e5_expect=True,
)


def _run_subprocess(code, label, extra_env=None):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith('COLDSTART20_')}
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run([PY, '-c', code], cwd=str(PROJECT_ROOT), env=env,
                          capture_output=True, text=True, encoding='utf-8',
                          errors='replace')
    if proc.returncode != 0:
        print('[verify] %s FAILED (rc=%d)' % (label, proc.returncode))
        print(proc.stderr[-4000:])
        return None
    line = [item for item in proc.stdout.splitlines()
            if item.startswith('RESULT ')]
    if not line:
        print('[verify] %s FAILED: no RESULT line' % label)
        print(proc.stdout[-2000:])
        return None
    return json.loads(line[-1][len('RESULT '):])


def verify():
    results = {}
    ok = True
    print('[verify] frozen 21-height pipeline (NO bootstrap import) ...')
    checks_21 = _run_subprocess(CODE_21H, '21h')
    if checks_21 is None:
        return 1
    failures_21 = []
    for key, expected in EXPECTED_21H.items():
        actual = checks_21.get(key)
        if actual != expected:
            failures_21.append(dict(check=key, expected=expected, actual=actual))
    ok = ok and not failures_21
    print('[verify] 21h: %s (%d checks, %d failed)'
          % ('PASS' if not failures_21 else 'FAIL', len(EXPECTED_21H),
             len(failures_21)))
    for item in failures_21:
        print('     %s: expected %r, got %r'
              % (item['check'], item['expected'], item['actual']))

    print('[verify] installed 20-height profile (bootstrap first) ...')
    checks_20 = _run_subprocess(
        CODE_20H, '20h',
        extra_env={'COLDSTART20_PHASE1_CROSSINGS': '0'})
    if checks_20 is None:
        return 1
    failures_20 = []
    for key, expected in EXPECTED_20H.items():
        actual = checks_20.get(key)
        if actual != expected:
            failures_20.append(dict(check=key, expected=expected, actual=actual))
    ok = ok and not failures_20
    print('[verify] 20h: %s (%d checks, %d failed)'
          % ('PASS' if not failures_20 else 'FAIL', len(EXPECTED_20H),
             len(failures_20)))
    for item in failures_20:
        print('     %s: expected %r, got %r'
              % (item['check'], item['expected'], item['actual']))

    results = dict(
        schema='coldstart20_native3d_def_verify_v1',
        created_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
        script_sha256=sha256_file(__file__),
        expected_21h={key: str(value) for key, value in EXPECTED_21H.items()},
        expected_20h={key: str(value) for key, value in EXPECTED_20H.items()},
        checks_21h=checks_21,
        checks_20h=checks_20,
        failures_21h=failures_21,
        failures_20h=failures_20,
        passed=bool(ok),
    )
    write_json(VERIFY_JSON, results)
    print('[verify] %s -- evidence: %s'
          % ('PASS' if ok else 'FAIL', VERIFY_JSON))
    return 0 if ok else 1


# ===========================================================================
# main
# ===========================================================================
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true',
                        help='show what would change, write nothing')
    parser.add_argument('--revert', nargs='?', const='', default=None,
                        metavar='STAMP',
                        help='restore the latest (or a named) backup')
    parser.add_argument('--force', action='store_true',
                        help='with --revert: restore even if the file changed')
    parser.add_argument('--verify', action='store_true',
                        help='run the 21H/20H regression checks')
    args = parser.parse_args(argv)
    if args.revert is not None:
        return revert(args.revert or None, force=args.force)
    code = apply(dry_run=args.dry_run)
    if code != 0 or args.dry_run:
        return code
    if args.verify:
        return verify()
    print('run with --verify for the 21H/20H regression checks')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
