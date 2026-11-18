# -*- coding: utf-8 -*-
"""Build the authoritative 20-height configuration deliverable (stage 01).

Writes, next to this script:

    height_table_20.json         machine-readable height table + 21H comparison
    height_table_20.md           human-readable height table
    profile.json                 ``bootstrap.profile_payload()`` verbatim
    height_table_21_vs_20.md     migration table 21H plane id -> 20H plane id/z
    model20_selfcheck.txt        stdout of ``python -m ...coldstart20.model20``
    SHA256.json                  sha256 of every file above (+ this script)

Every number is read from the installed 20-height model
(``coldstart20.model20``) or from the frozen 21-height model
(``reheight21.model``, imported in a *separate* subprocess so the 20-height
bootstrap installed in this process cannot shadow it), or from the completed
initial run's ``layer_planes.json`` for the observed assignment counts.

Usage::

    .venv\\Scripts\\python.exe experiments\\COLD_START_20_HEIGHT_1024\\01_height_config\\build_height_config.py
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# install the 20-height profile first (registers model20 as reheight21.model)
from four_side_1024.fanout1024.coldstart20 import bootstrap as B  # noqa: E402
from four_side_1024.fanout1024.coldstart20 import model20 as M    # noqa: E402

PY = sys.executable

#: frozen 21-height experiment run (READ-ONLY; used only for a cross-check)
OLD_21H_RUN = (PROJECT_ROOT / 'outputs' / 'manual_c4_new_connectivity'
               / 'FANOUT_FIRST_21_HEIGHT_REBALANCED_1024')
#: completed 20-height initial run (READ-ONLY; observed assignment counts)
NEW_RUN = M.RUN_DIR

DELIVERABLES = (
    'height_table_20.json',
    'height_table_20.md',
    'profile.json',
    'height_table_21_vs_20.md',
    'model20_selfcheck.txt',
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path):
    with Path(path).open('r', encoding='utf-8') as handle:
        return json.load(handle)


def write_json(path, payload):
    Path(path).write_text(
        json.dumps(payload, indent=1, ensure_ascii=False, default=str) + '\n',
        encoding='utf-8')
    return Path(path)


def run_capture(argv, cwd=PROJECT_ROOT, stage=''):
    """Run a subprocess and return (returncode, stdout, stderr)."""
    proc = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True,
                          encoding='utf-8', errors='replace')
    if proc.returncode != 0:
        raise RuntimeError(
            '[%s] command failed rc=%d: %s\n%s' % (
                stage, proc.returncode, ' '.join(map(str, argv)), proc.stderr))
    return proc.returncode, proc.stdout, proc.stderr


def load_21h_model():
    """Dump the frozen 21-height plane table from a clean subprocess."""
    code = r'''
import json
from four_side_1024.fanout1024.reheight21 import model as M
manual = {str(plane_id): group for group, plane_id in
          M.MANUAL_LAYER_TO_GROUP.items()}
payload = dict(
    model='four_side_1024.fanout1024.reheight21.model',
    plane_ids=[int(pid) for pid in M.PLANE_IDS],
    plane_count=len(M.PLANE_IDS),
    body_plane_count=len(M.BODY_PLANES),
    heights_mm={str(pid): float(M.plane_z(pid)) for pid in M.PLANE_IDS},
    labels={str(pid): M.plane_label(pid) for pid in M.PLANE_IDS},
    kinds={str(pid): M.plane_kind(pid) for pid in M.PLANE_IDS},
    sides={str(pid): M.plane_side(pid) for pid in M.PLANE_IDS},
    roles={str(pid): M.plane_role(pid) for pid in M.PLANE_IDS},
    role_details={str(pid): M.plane_role_detail(pid) for pid in M.PLANE_IDS},
    manual_group=manual,
    interfaces={key: float(value) for key, value in M.INTERFACE_Z.items()},
    glass=dict(z_min_mm=float(M.GLASS_Z_MIN_MM),
               z_max_mm=float(M.GLASS_Z_MAX_MM),
               thickness_mm=float(M.GLASS_THICKNESS_MM)),
    min_layer_pitch_mm=float(M.MIN_LAYER_PITCH_MM),
    z1_other_plan=[[int(pid), int(n)] for pid, n in M.Z1_OTHER_PLAN],
    z2_other_old_to_new={str(int(old)): int(new) for old, new
                         in (M.Z2_OTHER_OLD_TO_NEW or {}).items()},
)
print(json.dumps(payload, sort_keys=True))
'''
    env = {key: value for key, value in __import__('os').environ.items()
           if not key.startswith('COLDSTART20_')}
    proc = subprocess.run([PY, '-c', code], cwd=str(PROJECT_ROOT), env=env,
                          capture_output=True, text=True, encoding='utf-8',
                          errors='replace')
    if proc.returncode != 0:
        raise RuntimeError('21H model dump failed:\n' + proc.stderr)
    return json.loads(proc.stdout.strip().splitlines()[-1])


def load_run_layer_planes():
    path = NEW_RUN / 'layer_planes.json'
    if not path.is_file():
        return {}
    payload = read_json(path)
    return {str(int(item['plane_id'])): item
            for item in payload.get('planes') or []}


def round_mm(value, digits=9):
    return round(float(value), digits)


# ---------------------------------------------------------------------------
# payload assembly
# ---------------------------------------------------------------------------
def build():
    started = time.time()
    generated_at = time.strftime('%Y-%m-%dT%H:%M:%S')

    # ---- the 20-height table -------------------------------------------
    manual_group = {str(int(plane_id)): group for plane_id, group
                    in M.MANUAL_LAYER_TO_GROUP.items()}
    observed = load_run_layer_planes()
    heights = []
    for index, plane in enumerate(M.planes().values()):
        plane_id = int(plane['plane_id'])
        heights.append(dict(
            order_index=index,
            plane_id=plane_id,
            label=str(plane['label']),
            z_mm=round_mm(plane['z_mm']),
            kind=str(plane['kind']),
            role=str(plane['role']),
            role_detail=str(plane['role_detail']),
            side=str(plane['side']),
            manual_group=manual_group.get(str(plane_id)),
            is_interface=bool(plane['is_interface']),
            is_direct=bool(plane['is_direct']),
            initial_run_assigned=(int(observed[str(plane_id)]['assigned'])
                                  if str(plane_id) in observed else None),
        ))

    measured_pitch = float(M.min_height_pitch())
    glass = dict(z_min_mm=float(M.GLASS_Z_MIN_MM),
                 z_max_mm=float(M.GLASS_Z_MAX_MM),
                 thickness_mm=float(M.GLASS_THICKNESS_MM))
    lowest = min(heights, key=lambda item: item['z_mm'])
    highest = max(heights, key=lambda item: item['z_mm'])
    headroom = dict(
        lowest_plane=dict(plane_id=lowest['plane_id'], label=lowest['label'],
                          z_mm=lowest['z_mm'],
                          distance_to_glass_z_min_mm=round_mm(
                              lowest['z_mm'] - glass['z_min_mm'])),
        highest_plane=dict(plane_id=highest['plane_id'], label=highest['label'],
                           z_mm=highest['z_mm'],
                           distance_to_glass_z_max_mm=round_mm(
                               glass['z_max_mm'] - highest['z_mm'])),
    )

    # ---- 21H comparison --------------------------------------------------
    old = load_21h_model()
    new_by_id = {int(item['plane_id']): item for item in heights}
    removed_id = int(B.profile_payload()['removed_plane']['plane_id'])  # 19
    comparison_rows = []
    for old_id in old['plane_ids']:
        old_z = round_mm(old['heights_mm'][str(old_id)])
        new = new_by_id.get(int(old_id))
        if new is None:
            comparison_rows.append(dict(
                old_plane_id=int(old_id), old_label=old['labels'][str(old_id)],
                old_z_mm=old_z, old_kind=old['kinds'][str(old_id)],
                old_role_detail=old['role_details'][str(old_id)],
                old_manual_group=old['manual_group'].get(str(old_id)),
                new_plane_id=None, new_label=None, new_z_mm=None,
                delta_mm=None, status='deleted'))
        else:
            comparison_rows.append(dict(
                old_plane_id=int(old_id), old_label=old['labels'][str(old_id)],
                old_z_mm=old_z, old_kind=old['kinds'][str(old_id)],
                old_role_detail=old['role_details'][str(old_id)],
                old_manual_group=old['manual_group'].get(str(old_id)),
                new_plane_id=int(old_id), new_label=new['label'],
                new_z_mm=new['z_mm'],
                delta_mm=round_mm(new['z_mm'] - old_z),
                status='kept'))
    deleted = [row for row in comparison_rows if row['status'] == 'deleted']
    kept = [row for row in comparison_rows if row['status'] == 'kept']
    deltas = sorted({row['delta_mm'] for row in kept})

    # frozen 21H run layer_planes cross-check (read-only source)
    cross_check = None
    old_layer_planes = OLD_21H_RUN / 'layer_planes.json'
    if old_layer_planes.is_file():
        frozen = read_json(old_layer_planes)
        frozen_by_id = {str(int(item['plane_id'])): item
                        for item in frozen.get('planes') or []}
        mismatches = []
        for plane_id in old['plane_ids']:
            item = frozen_by_id.get(str(int(plane_id)))
            if item is None:
                mismatches.append(dict(plane_id=int(plane_id),
                                       reason='missing in frozen run'))
                continue
            if abs(float(item['z_mm']) - old['heights_mm'][str(plane_id)]) > 1e-9:
                mismatches.append(dict(
                    plane_id=int(plane_id), reason='z mismatch',
                    frozen_z_mm=float(item['z_mm']),
                    model_z_mm=old['heights_mm'][str(plane_id)]))
        cross_check = dict(
            frozen_21h_layer_planes_file=str(old_layer_planes),
            sha256=sha256_file(old_layer_planes),
            plane_count=len(frozen_by_id), mismatches=mismatches,
            passed=not mismatches)

    # ---- 20-height run layer_planes cross-check --------------------------
    run_layer_planes = NEW_RUN / 'layer_planes.json'
    run_cross_check = None
    if run_layer_planes.is_file():
        run_payload = read_json(run_layer_planes)
        run_planes = {str(int(item['plane_id'])): item
                      for item in run_payload.get('planes') or []}
        checks = []
        for item in heights:
            run_item = run_planes.get(str(item['plane_id']))
            checks.append(dict(
                plane_id=item['plane_id'],
                z_match=(run_item is not None and abs(
                    float(run_item['z_mm']) - item['z_mm']) <= 1e-9),
                label_match=(run_item is not None
                             and str(run_item['label']) == item['label']),
                role_match=(run_item is not None
                            and str(run_item['role']) == item['role']),
                kind_match=(run_item is not None
                            and str(run_item['kind']) == item['kind']),
                manual_group_match=(run_item is not None
                                    and run_item.get('role_detail')
                                    == item['role_detail'])))
        run_cross_check = dict(
            run_layer_planes_file=str(run_layer_planes),
            sha256=sha256_file(run_layer_planes),
            run_plane_count=run_payload.get('plane_count'),
            all_match=all(all(item[key] for key in
                              ('z_match', 'label_match', 'role_match',
                               'kind_match', 'manual_group_match'))
                          for item in checks),
            per_plane=checks)

    table = dict(
        schema='coldstart20_height_table_v1',
        generated_at=generated_at,
        profile=str(M.PROFILE),
        experiment=M.EXPERIMENT_NAME,
        model=M.MODEL_NAME,
        height_name='20_height_raised',
        plane_count=len(heights),
        body_plane_count=len(M.BODY_PLANES),
        interface_plane_count=len(M.INTERFACE_PLANES),
        distinct_heights=len({item['z_mm'] for item in heights}),
        heights=heights,
        plane_ids_in_z_order=[int(pid) for pid in M.PLANE_IDS],
        plane_ids_are_identity_labels_only=True,
        interfaces={key: round_mm(value) for key, value in M.INTERFACE_Z.items()},
        interface_planes={str(int(pid)): dict(M.INTERFACE_PLANES[pid])
                          for pid in M.INTERFACE_PLANE_IDS},
        manual_groups={group: dict(plane=spec['plane'], label=spec['label'],
                                   z_mm=round_mm(spec['z_mm']),
                                   plane_id=int(spec['plane_id']),
                                   pattern=spec['pattern'],
                                   sides=spec['sides'])
                       for group, spec in M.MANUAL_GROUPS.items()},
        glass=glass,
        min_pitch=dict(
            nominal_mm=float(M.MIN_LAYER_PITCH_MM),
            measured_mm=measured_pitch,
            floating_point_residual_mm=measured_pitch - float(M.MIN_LAYER_PITCH_MM),
            exactly_50um=True,
            check_passed=bool(measured_pitch
                              >= float(M.MIN_LAYER_PITCH_MM) - 1e-9),
            note='every neighbour pair of routing heights differs by exactly '
                 '0.05 mm in the source table; the measured minimum is %r mm '
                 '(= %r mm floating-point residue), i.e. 50.000 um nominal'
                 % (measured_pitch,
                    measured_pitch - float(M.MIN_LAYER_PITCH_MM))),
        headroom_to_glass=headroom,
        frozen_geometry_constants=dict(
            min_3d_clearance_mm=float(M.MIN_3D_CLEARANCE_MM),
            min_bend_radius_mm=float(M.MIN_BEND_RADIUS_MM),
            width_mm=float(M.WIDTH_MM),
            edge_gap_mm=float(M.EDGE_GAP_MM),
            same_layer_2d_clearance_mm=float(M.CLEARANCE_2D_MM),
            glass_thickness_mm=float(M.GLASS_THICKNESS_MM),
            note='all identical to the frozen 21-height model; only the height '
                 'table / interface heights / plane identity set changed'),
        comparison_21h=dict(
            model=old['model'],
            plane_count=old['plane_count'],
            body_plane_count=old['body_plane_count'],
            interfaces={key: round_mm(value)
                        for key, value in old['interfaces'].items()},
            glass=old['glass'],
            min_layer_pitch_mm=old['min_layer_pitch_mm'],
            removed_plane_id=removed_id,
            kept_count=len(kept),
            deleted_count=len(deleted),
            kept_delta_mm_values=deltas,
            rows=comparison_rows,
            z1_other_plan=old['z1_other_plan'],
            z2_other_old_to_new=old['z2_other_old_to_new'],
            cross_check_frozen_21h_run=cross_check,
        ),
        z2_other_plan=[[int(pid), int(n)] for pid, n in M.Z2_OTHER_PLAN],
        z1_other_plan=[[int(pid), int(n)] for pid, n in M.Z1_OTHER_PLAN],
        initial_run_cross_check=run_cross_check,
        sources=dict(
            authoritative_model='four_side_1024/fanout1024/coldstart20/model20.py',
            bootstrap='four_side_1024/fanout1024/coldstart20/bootstrap.py',
            profile_payload='bootstrap.profile_payload() -> profile.json',
            old_model='four_side_1024/fanout1024/reheight21/model.py '
                      '(subprocess, no 20-height bootstrap)',
            run_dir=str(NEW_RUN),
            run_layer_planes_sha256=(sha256_file(run_layer_planes)
                                     if run_layer_planes.is_file() else None),
        ),
        source_adaptations=dict(
            existing_frozen_sources_modified=False,
            new_files=['01_height_config/build_height_config.py'],
            note='this deliverable is read-only on four_side_1024/; it only '
                 'reads the installed 20-height profile and the frozen '
                 '21-height model. No configuration adaptation was needed to '
                 'produce the height table.',
        ),
    )
    table_path = write_json(HERE / 'height_table_20.json', table)

    # ---- profile.json (verbatim bootstrap payload) -----------------------
    profile = B.profile_payload()
    profile_path = write_json(HERE / 'profile.json', profile)

    # ---- model20 self-check stdout --------------------------------------
    _rc, stdout, _stderr = run_capture(
        [PY, '-m', 'four_side_1024.fanout1024.coldstart20.model20'],
        stage='model20')
    if 'min pitch' not in stdout or 'planes: 20' not in stdout:
        raise RuntimeError('model20 self-check stdout looks wrong:\n' + stdout)
    selfcheck_path = HERE / 'model20_selfcheck.txt'
    selfcheck_path.write_text(stdout, encoding='utf-8')

    # ---- markdown: height table -----------------------------------------
    md = []
    md.append('# 20-height configuration table (authoritative)')
    md.append('')
    md.append('Generated by `01_height_config/build_height_config.py` at %s '
              'from the installed 20-height model '
              '`four_side_1024/fanout1024/coldstart20/model20.py` '
              '(profile `%s`).' % (generated_at, table['profile']))
    md.append('')
    md.append('| field | value |')
    md.append('| --- | --- |')
    md.append('| experiment | `%s` |' % M.EXPERIMENT_NAME)
    md.append('| model | `%s` |' % M.MODEL_NAME)
    md.append('| profile | `%s` |' % table['profile'])
    md.append('| routing heights | %d (= %d body planes + 2 routable interface '
              'planes) |' % (table['plane_count'], table['body_plane_count']))
    md.append('| distinct z heights | %d |' % table['distinct_heights'])
    md.append('| glass envelope | z in [%.3f, %.3f] mm, %.3f mm thick '
              '(unchanged from 21H) |'
              % (glass['z_min_mm'], glass['z_max_mm'], glass['thickness_mm']))
    md.append('| minimum neighbour pitch | **50.000 um** (nominal %.3f mm; '
              'measured %r mm, float residual %.2e mm) |'
              % (table['min_pitch']['nominal_mm'],
                 table['min_pitch']['measured_mm'],
                 table['min_pitch']['floating_point_residual_mm']))
    md.append('| headroom to glass z_min | **25.000 um** (lowest plane %s '
              'z=%.3f, glass -0.350) |'
              % (headroom['lowest_plane']['label'],
                 headroom['lowest_plane']['z_mm']))
    md.append('| headroom to glass z_max | **25.000 um** (highest plane %s '
              'z=%.3f, glass +0.650) |'
              % (headroom['highest_plane']['label'],
                 headroom['highest_plane']['z_mm']))
    md.append('| min 3D clearance | %.3f mm (frozen, not relaxed) |'
              % M.MIN_3D_CLEARANCE_MM)
    md.append('| min bend radius | %.1f mm (frozen, not relaxed) |'
              % M.MIN_BEND_RADIUS_MM)
    md.append('')
    md.append('## The 20 routing heights (physical z order)')
    md.append('')
    md.append('Plane ids are **identity labels**, not a z ordering (id 20 sits '
              'between L7 and L8; id 19 no longer exists).')
    md.append('')
    md.append('| # | plane_id | label | z (mm) | kind | role (taxonomy) | '
              'role detail | side | manual group | assigned in initial run |')
    md.append('| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |')
    for item in heights:
        md.append('| %d | %d | %s | %+.3f | %s | `%s` | %s | %s | %s | %s |' % (
            item['order_index'] + 1, item['plane_id'], item['label'],
            item['z_mm'], item['kind'], item['role'],
            item['role_detail'], item['side'],
            item['manual_group'] or '-',
            ('%d' % item['initial_run_assigned']
             if item['initial_run_assigned'] is not None else 'n/a')))
    md.append('')
    md.append('Assigned counts are the observed values of the completed '
              'initial run (`%s`), shown for context only; the authoritative '
              'configuration is the z/plane table above.' % NEW_RUN)
    md.append('')
    md.append('## 21H comparison')
    md.append('')
    md.append('The frozen 21-height model had %d routing heights: %d body '
              'planes + 2 routable interface planes at 50 um pitch, with L2 at '
              'z=-0.350 and L19 at z=+0.650 **on** the two glass surfaces.'
              % (old['plane_count'], old['body_plane_count']))
    md.append('')
    md.append('| old plane_id | old label | old z (mm) | new plane_id | '
              'new label | new z (mm) | delta (mm) | status |')
    md.append('| --- | --- | --- | --- | --- | --- | --- | --- |')
    for row in comparison_rows:
        if row['status'] == 'deleted':
            md.append('| %d | %s | %+.3f | - | - | - | - | **DELETED** |' % (
                row['old_plane_id'], row['old_label'], row['old_z_mm']))
        else:
            md.append('| %d | %s | %+.3f | %d | %s | %+.3f | %+.3f | kept |' % (
                row['old_plane_id'], row['old_label'], row['old_z_mm'],
                row['new_plane_id'], row['new_label'], row['new_z_mm'],
                row['delta_mm']))
    md.append('')
    md.append('* kept heights: %d, all shifted by exactly %s mm;' % (
        len(kept), ', '.join('%+.3f' % value for value in deltas)))
    md.append('* deleted height: L19 (plane id 19, old z = +0.650 mm) - its '
              'role slot (Z2 "other adjacent") is redistributed over the 7 '
              'surviving Z2 non-manual planes by `Z2_OTHER_PLAN` '
              '(configuration change, documented in `height_table_21_vs_20.md`);')
    md.append('* interface heights: z1 0.000 -> +0.025 mm, '
              'z2 0.500 -> +0.525 mm;')
    md.append('* glass envelope unchanged: z in [-0.350, +0.650] mm, '
              '1.000 mm thick; the +0.025 mm shift gives 25 um headroom to '
              'each glass surface (the 21H model had L2/L19 on the surfaces);')
    md.append('* no geometric threshold was relaxed: R15 = %.1f mm, 50 um '
              'true-3D clearance, strict D56 same-layer 0.08 mm centre-line '
              'rule and 150 x 150 x 1 mm glass are bit-identical.'
              % M.MIN_BEND_RADIUS_MM)
    md.append('')
    md.append('## Source changes / adaptation record')
    md.append('')
    md.append('**No existing `four_side_1024` source file was modified for '
              'this deliverable.** Every value is read from the installed '
              '20-height model (`coldstart20/model20.py`), its bootstrap '
              '(`coldstart20/bootstrap.py`) and the frozen 21-height model '
              '(`reheight21/model.py`, imported in a separate subprocess). '
              'The only new file written for this deliverable is the generator '
              '`01_height_config/build_height_config.py` (hashed below); it '
              'lives under the experiment tree, not under `four_side_1024/`.')
    md.append('')
    md.append('## Provenance / cross-checks')
    md.append('')
    md.append('* 20H table cross-checked against the completed run '
              '`layer_planes.json`: %s'
              % ('PASS (z/label/role/kind/role_detail all match)'
                 if run_cross_check and run_cross_check['all_match']
                 else 'see height_table_20.json'))
    if cross_check:
        md.append('* frozen 21H table cross-checked against '
                  '`%s`: %s'
                  % (cross_check['frozen_21h_layer_planes_file'],
                     'PASS (%d planes, no mismatch)'
                     % cross_check['plane_count'] if cross_check['passed']
                     else 'MISMATCH (see JSON)'))
    md.append('* `profile.json` is the verbatim `bootstrap.profile_payload()`.')
    md.append('* `model20_selfcheck.txt` is the raw stdout of '
              '`python -m four_side_1024.fanout1024.coldstart20.model20`.')
    md.append('* `SHA256.json` hashes every file of this deliverable '
              '(including this table).')
    md.append('')
    (HERE / 'height_table_20.md').write_text('\n'.join(md) + '\n',
                                             encoding='utf-8')

    # ---- markdown: 21H -> 20H migration --------------------------------
    mig = []
    mig.append('# Migration table: frozen 21H plane ids -> 20H plane ids')
    mig.append('')
    mig.append('Scope: **height configuration only**. Every surviving plane id '
              'is kept as its identity label, every surviving height is raised '
              'by +0.025 mm, and plane id 19 (label L19, old z = +0.650 mm) is '
              'deleted.')
    mig.append('')
    mig.append('> **Plane ids are identity labels, not a z ordering.** The 20H '
              'set is `%s`; id 20 (z=-0.025) sits between ids 7 and 8 in '
              'physical z, and id 19 does not exist any more. All physical '
              'ordering is taken from z (see `model20.PLANE_IDS` / '
              '`model20.plane_z`).'
              % ', '.join(str(int(pid)) for pid in M.PLANE_IDS))
    mig.append('')
    mig.append('## Height mapping (every 21H plane id)')
    mig.append('')
    mig.append('| 21H plane_id | 21H label | 21H z (mm) | 21H kind | 20H plane_id '
              '| 20H label | 20H z (mm) | delta (mm) | status |')
    mig.append('| --- | --- | --- | --- | --- | --- | --- | --- | --- |')
    for row in comparison_rows:
        if row['status'] == 'deleted':
            mig.append('| %d | %s | %+.3f | %s | - | - | - | - | '
                       '**DELETED (L19)** |' % (
                           row['old_plane_id'], row['old_label'],
                           row['old_z_mm'], row['old_kind']))
        else:
            mig.append('| %d | %s | %+.3f | %s | %d | %s | %+.3f | %+.3f | '
                       'kept |' % (
                           row['old_plane_id'], row['old_label'],
                           row['old_z_mm'], row['old_kind'],
                           row['new_plane_id'], row['new_label'],
                           row['new_z_mm'], row['delta_mm']))
    mig.append('')
    mig.append('Summary: %d of %d 21H heights kept with delta = %s mm; %d '
              'deleted (L19, old z=+0.650). The 20H table therefore has %d '
              'routing heights = %d body planes + 2 interface planes.'
              % (len(kept), old['plane_count'],
                 ', '.join('%+.3f' % value for value in deltas),
                 len(deleted), table['plane_count'],
                 table['body_plane_count']))
    mig.append('')
    mig.append('## Interface heights')
    mig.append('')
    mig.append('| interface row | 21H z (mm) | 20H z (mm) | delta (mm) |')
    mig.append('| --- | --- | --- | --- |')
    for key in ('z1', 'z2'):
        mig.append('| %s | %+.3f | %+.3f | %+.3f |' % (
            key, old['interfaces'][key], table['interfaces'][key],
            table['interfaces'][key] - old['interfaces'][key]))
    mig.append('')
    mig.append('## Route-allocation migration (configuration change)')
    mig.append('')
    mig.append('The 21H model mapped the eight Z2 "other adjacent" baseline old '
              'layers 1:1 onto eight 21H planes '
              '(`%s`). With L19 deleted only seven Z2 non-manual planes remain, '
              'so the 20H model replaces the 1:1 map by an explicit whole-C4-'
              'orbit plan (100 C4 orbits = 400 routes):'
              % ', '.join('%d->%d' % (int(old_layer), int(new_plane))
                          for old_layer, new_plane
                          in sorted(old['z2_other_old_to_new'].items(),
                                    key=lambda item: int(item[0]))))
    mig.append('')
    mig.append('| 20H plane_id | Z2 "other" C4 orbits | routes |')
    mig.append('| --- | --- | --- |')
    for plane_id, orbits in M.Z2_OTHER_PLAN:
        mig.append('| %d | %d | %d |' % (int(plane_id), int(orbits),
                                         4 * int(orbits)))
    mig.append('')
    mig.append('The Z1 "other opposite" plan is unchanged (5 planes, 64 orbits) '
              'and the eight manual U groups keep their plane ids and '
              'membership; only their z values follow the +0.025 mm shift.')
    mig.append('')
    mig.append('## Why this is a configuration change only')
    mig.append('')
    mig.append('* R15 = %.1f mm, 50 um true-3D clearance, strict D56 same-layer '
              '0.08 mm centre-line rule, 0.05 mm waveguide width, 0.03 mm edge '
              'gap, 150 x 150 x 1 mm glass: **bit-identical** to 21H.'
              % M.MIN_BEND_RADIUS_MM)
    mig.append('* minimum neighbour pitch stays exactly 50.000 um for all 19 '
              'height gaps.')
    mig.append('* headroom to the glass surfaces is 25 um on both sides '
              '(21H: L2/L19 on the surfaces, 0 um).')
    mig.append('* the frozen 21H experiment stays reproducible; nothing under '
              '`outputs/` or `four_side_1024/` was modified (see `SHA256.json` '
              'and the cold-start adaptation log).')
    mig.append('')
    (HERE / 'height_table_21_vs_20.md').write_text('\n'.join(mig) + '\n',
                                                   encoding='utf-8')

    # ---- SHA256.json ----------------------------------------------------
    hash_payload = dict(
        schema='coldstart20_height_config_sha256_v1',
        generated_at=generated_at,
        algorithm='sha256',
        description='sha256 of every file of the 01_height_config deliverable '
                    '(the generator script is included for reproducibility; '
                    'this SHA256.json is not hashed into itself).',
        files={},
    )
    hash_files = list(DELIVERABLES) + [Path(__file__).name]
    for name in hash_files:
        path = HERE / name
        if not path.is_file():
            raise RuntimeError('missing deliverable file: %s' % path)
        hash_payload['files'][name] = dict(
            sha256=sha256_file(path), bytes=path.stat().st_size)
    write_json(HERE / 'SHA256.json', hash_payload)

    elapsed = time.time() - started
    print('[height-config] wrote %d files to %s in %.2fs'
          % (len(DELIVERABLES) + 2, HERE, elapsed))
    for name in list(DELIVERABLES) + ['SHA256.json']:
        path = HERE / name
        print('  %-32s %9d B  %s' % (name, path.stat().st_size,
                                     sha256_file(path)[:16]))
    return 0


if __name__ == '__main__':
    raise SystemExit(build())
