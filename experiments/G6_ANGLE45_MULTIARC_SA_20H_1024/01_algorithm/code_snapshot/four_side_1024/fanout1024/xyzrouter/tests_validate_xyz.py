# -*- coding: utf-8 -*-
"""Tests for the G1/G2/G3 manual-policy validator extension (task-2).

Run from the project root::

    .venv\\Scripts\\python.exe -m four_side_1024.fanout1024.xyzrouter.tests_validate_xyz

What is verified
----------------
1. ``frozen`` regression: ``validate_xyz`` on the authoritative 2409 baseline
   snapshot (``XYZ_JOINT_G123_1024/baseline_authoritative`` when ready, else
   ``NATIVE_3D_JOINT_OPT_1024/best_valid``) with
   ``baseline_dir=<the baseline recorded in its validation.json>`` must PASS:
   1024/1024 routed, 2409 crossings / 2010 pairs, 0 violations, 138 mid
   transitions, min 3D clearance 0.06730354 mm.
2. Default behaviour unchanged: the new ``frozen`` report is deep-compared
   against the pre-extension ``validate_run`` output (captured in
   ``validator_tests/old_behavior_frozen`` before the edit; falls back to the
   archived ``NATIVE_3D_JOINT_OPT_1024/validation.json``).
3. Synthetic ``height_only`` acceptance: 3 manual routes are legally rebuilt
   with a new body z (identical body XY, leads/transitions recomputed with
   ``fanout.candidate_transitions`` + ``assemble.assemble_route``); the G2
   contract accepts them and all geometry checks still run.  A changed body XY
   primitive / endpoint id / body flat count is rejected exactly where the
   contract says it must be.
4. Constraints are not weakened: R15, 50 um 3D clearance, D56 strict crossing
   rule/counting, model-height and native part-chain checks are asserted
   untouched (constants, report numbers, direct negative cases and the
   validator's own synthetic consistency suite).

Outputs
-------
``<out-dir>/tests_validate_xyz_result.json``          full machine-readable result
``<out-dir>/regression_frozen/validation.json``       frozen regression report
``<out-dir>/synthetic_height_only/run/``              synthetic run directory
``<out-dir>/synthetic_height_only/validation_height_only/validation.json``

Exit code: 0 = all cases passed, 1 = at least one case failed.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import inspect
import json
import math
import shutil
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024 import common as C
from four_side_1024.fanout1024 import fanout as F
from four_side_1024.fanout1024 import assemble as A
from four_side_1024.fanout1024.native3d import validate_native3d as V
from four_side_1024.fanout1024.reheight21 import model as M
from four_side_1024.fanout1024.reheight21 import validate21 as V21
from four_side_1024.fanout1024.xyzrouter import validate_xyz as X

TEST_SCHEMA = 'xyz_validator_tests_v1'

OUTPUT_ROOT = ROOT / 'outputs' / 'manual_c4_new_connectivity'
XYZ_ROOT = OUTPUT_ROOT / 'XYZ_JOINT_G123_1024'
DEFAULT_OUT_DIR = XYZ_ROOT / 'preflight_audit' / 'validator_tests'
BEST_VALID = OUTPUT_ROOT / 'NATIVE_3D_JOINT_OPT_1024' / 'best_valid'
AUTHORITATIVE = XYZ_ROOT / 'baseline_authoritative'
ARCHIVED_REPORT = OUTPUT_ROOT / 'NATIVE_3D_JOINT_OPT_1024' / 'validation.json'
EXPERIMENT_C = OUTPUT_ROOT / 'NATIVE_3D_CROSSING_OPT_1024' / 'experiment_C'
E5_BASELINE = OUTPUT_ROOT / 'NON_C4_CROSSING_OPT_1024' / 'E5_joint_repair_final'
AUTHORITY_ROUTE_SHA = ('36c57ad9eff5244959a3e5cadcfe5f5d7fddd06db203a71131'
                       '31d0667e5c12d0')
PRE_EDIT_REFERENCE = 'old_behavior_frozen/validation.json'

EXPECT = dict(
    routed=1024, failed=0, records=1024,
    crossings=2409, crossing_pairs=2010,
    mid_transitions=138, transitions=1990, flat_arc_count=1596,
    audited_heights=21, manual_routes=368,
    min_3d_clearance=0.06730354, min_3d_clearance_tol=1e-6,
    total_length=157566.008124, total_length_tol=1e-3,
    violation_count=0, manual_geometry_mismatch_count=0,
)

#: one synthetic height-changed route per group (Z1 + Z2 coverage)
SYNTHETIC_GROUPS = ('Z1-U1', 'Z1-U2', 'Z2-U1')

#: volatile report fields ignored by the default-behaviour regression compare
REPORT_SKIP_KEYS = frozenset({
    'runtime_seconds', 'seconds', 'validated_at', 'generated_at',
    'out_dir', 'run_dir', 'baseline_dir', 'routes_file',
    'baseline_routes_file', 'assignment_file', 'layer_planes_file',
    'validation_file', 'consistency_file', 'path', 'xyz_validator',
    'manual_policy', 'policy_report', 'policy', 'contract',
})


# ===========================================================================
# tiny helpers
# ===========================================================================
def _ensure(condition, message):
    if not condition:
        raise AssertionError(message)


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1,
                               default=str) + '\n', encoding='utf-8')
    return path


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _close(left, right, tol):
    return abs(float(left) - float(right)) <= tol


def _canon(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, default=str)


def _json_normalize(value):
    """Round-trip through JSON so tuples become lists / numpy types vanish."""
    try:
        return json.loads(json.dumps(value, default=str))
    except (TypeError, ValueError):
        return value


def _pct(value, digits=3):
    return round(float(value), digits)


def _deep_subset_diffs(reference, candidate, path='', skip=REPORT_SKIP_KEYS):
    """Every value of ``reference`` must be present/equal in ``candidate``."""
    # normalise both sides through JSON so tuples/lists compare identically
    reference = _json_normalize(reference)
    candidate = _json_normalize(candidate)
    if isinstance(reference, dict):
        if not isinstance(candidate, dict):
            return ['%s: expected dict, got %s'
                    % (path, type(candidate).__name__)]
        diffs = []
        for key in sorted(reference):
            if key in skip:
                continue
            diffs.extend(_deep_subset_diffs(reference[key],
                                            candidate.get(key),
                                            '%s.%s' % (path, key), skip))
        return diffs
    if isinstance(reference, list):
        if not isinstance(candidate, list):
            return ['%s: expected list, got %s'
                    % (path, type(candidate).__name__)]
        if len(reference) != len(candidate):
            return ['%s: list length %d != %d'
                    % (path, len(reference), len(candidate))]
        diffs = []
        for index, (left, right) in enumerate(zip(reference, candidate)):
            diffs.extend(_deep_subset_diffs(left, right,
                                            '%s[%d]' % (path, index), skip))
        return diffs
    if isinstance(reference, bool) or isinstance(candidate, bool):
        return [] if reference == candidate else \
            ['%s: %r != %r' % (path, reference, candidate)]
    if isinstance(reference, (int, float)) and isinstance(candidate, (int, float)):
        if abs(float(reference) - float(candidate)) <= \
                1e-12 * max(1.0, abs(float(reference))):
            return []
        return ['%s: %r != %r' % (path, reference, candidate)]
    return [] if reference == candidate else \
        ['%s: %r != %r' % (path, reference, candidate)]


# ===========================================================================
# input resolution
# ===========================================================================
def _resolve_inputs(log=print):
    """Locate the run snapshot + the baseline used by its validation.json."""
    detail = dict(authoritative_ready=False, authoritative_reason=None,
                  run_source=None, run_dir=None, baseline_dir=None,
                  baseline_source=None, run_routes_sha256=None)
    run_dir = BEST_VALID
    authoritative = AUTHORITATIVE
    auth_files = [authoritative / name for name in
                  ('routes_l3d.json', 'assignment_1024.csv',
                   'layer_planes.json')]
    if all(path.exists() for path in auth_files):
        sha = _sha256(authoritative / 'routes_l3d.json')
        if sha.lower() == AUTHORITY_ROUTE_SHA:
            run_dir = authoritative
            detail['authoritative_ready'] = True
            detail['run_source'] = 'baseline_authoritative'
        else:
            detail['authoritative_reason'] = (
                'routes_l3d.json sha256=%s != authority %s'
                % (sha, AUTHORITY_ROUTE_SHA))
    else:
        missing = [str(path.relative_to(ROOT)) for path in auth_files
                   if not path.exists()]
        detail['authoritative_reason'] = (
            'baseline_authoritative incomplete (missing %r)' % (missing,))
    if not detail['authoritative_ready']:
        detail['run_source'] = 'best_valid (authoritative snapshot not ready)'
        run_dir = BEST_VALID
        log('[inputs] authoritative snapshot not used: %s'
            % detail['authoritative_reason'])
    detail['run_dir'] = str(run_dir)
    detail['run_routes_sha256'] = _sha256(run_dir / 'routes_l3d.json')
    # -- baseline: the one recorded in the historical validation.json ------
    baseline_dir, baseline_source = None, None
    archived = _read_json(ARCHIVED_REPORT)
    if isinstance(archived, dict):
        value = archived.get('baseline_dir')
        if isinstance(value, str) and value:
            candidate = Path(value)
            if not candidate.is_absolute():
                candidate = ROOT / candidate
            if (candidate / 'routes_l3d.json').exists():
                baseline_dir = candidate
                baseline_source = ('archived %s:baseline_dir'
                                   % ARCHIVED_REPORT.relative_to(ROOT))
    if baseline_dir is None:
        for candidate, source in (
                (EXPERIMENT_C, 'NATIVE_3D_CROSSING_OPT_1024/experiment_C'),
                (E5_BASELINE, 'NON_C4_CROSSING_OPT_1024/E5_joint_repair_final'),
                (BEST_VALID, 'best_valid (self-baseline fallback)')):
            if (candidate / 'routes_l3d.json').exists():
                baseline_dir = candidate
                baseline_source = source
                break
    _ensure(baseline_dir is not None, 'no usable baseline directory found')
    # -- optional AUTHORITY.json cross-check of the E5 baseline ------------
    authority_e5 = None
    for name in ('AUTHORITY.json', 'hashes.json', 'validation.json'):
        payload = _read_json(authoritative / name)
        if not isinstance(payload, dict):
            continue
        for key in ('e5_baseline_dir', 'baseline_dir', 'e5_baseline'):
            value = payload.get(key)
            if isinstance(value, dict):
                value = value.get('path') or value.get('dir')
            if isinstance(value, str) and value.strip():
                candidate = Path(value)
                if not candidate.is_absolute():
                    candidate = ROOT / candidate
                if (candidate / 'routes_l3d.json').exists():
                    authority_e5 = str(candidate)
                    break
        if authority_e5:
            break
    detail['baseline_dir'] = str(baseline_dir)
    detail['baseline_source'] = baseline_source
    detail['authority_e5_baseline'] = authority_e5
    _ensure((Path(run_dir) / 'routes_l3d.json').exists(),
            'run routes_l3d.json missing: %s' % run_dir)
    return detail


def _cached_inputs(context):
    if 'inputs' not in context:
        context['inputs'] = _resolve_inputs(context['log'])
    return context['inputs']


def _cached_data(context):
    """Load the run/baseline routes + assignment once (read-only copies)."""
    if 'data' in context:
        return context['data']
    inputs = _cached_inputs(context)
    run_dir = Path(inputs['run_dir'])
    baseline_dir = Path(inputs['baseline_dir'])
    rows = list(csv.DictReader(
        (run_dir / 'assignment_1024.csv').open('r', encoding='utf-8-sig',
                                               newline='')))
    assignment_by_id = {int(row['route_id']): row for row in rows}
    payload, records = V21.load_payload(run_dir / 'routes_l3d.json')
    _, baseline_records = V21.load_payload(baseline_dir / 'routes_l3d.json')
    baseline_by_id = {int(record['route_id']): record
                      for record in baseline_records}
    routed = copy.deepcopy(list(records))
    manual_ids = sorted(route_id for route_id, row in assignment_by_id.items()
                        if str(row.get('manual_group') or '').strip())
    data = dict(
        run_dir=run_dir, baseline_dir=baseline_dir,
        payload=payload, routed=routed, records=records,
        assignment_by_id=assignment_by_id, assignment_rows=rows,
        baseline_by_id=baseline_by_id, manual_ids=manual_ids,
        model=V._build_model(V._model_planes()),
        endpoints=C.endpoints(),
    )
    context['data'] = data
    context['log']('[inputs] routed=%d baseline=%d manual=%d'
                   % (len(routed), len(baseline_records), len(manual_ids)))
    return data


def _routed_by_id(routed):
    return {int(record['route_id']): record for record in routed}


def _replace_record(routed, record):
    route_id = int(record['route_id'])
    output = []
    replaced = False
    for item in routed:
        if int(item['route_id']) == route_id:
            output.append(record)
            replaced = True
        else:
            output.append(item)
    if not replaced:
        output.append(record)
    return output


# ===========================================================================
# synthetic legal height change (G2-accepted rebuild)
# ===========================================================================
def _body_flat_primitive_copy(route):
    indices = V.body_flat_indices(route)
    _ensure(len(indices) == 1,
            'route %r: expected exactly one body flat, got %d'
            % (route.get('route_id'), len(indices)))
    return copy.deepcopy(route['parts'][indices[0]]['primitives'])


def _body_by_z(planes):
    return {round(float(plane['z_mm']), 9): int(plane_id)
            for plane_id, plane in planes.items()
            if str(plane.get('kind')) == 'body'}


def _choose_new_height(route, planes):
    """One routing height closer to the interface than the baseline height."""
    old_z = float(route['target_z_mm'])
    interface_z = C.interface_z(route['plane'])
    step = 0.05 if interface_z > old_z else -0.05
    new_z = round(old_z + step, 9)
    plane_id = _body_by_z(planes).get(new_z)
    _ensure(plane_id is not None,
            'route %r: no body plane at z=%r' % (route.get('route_id'), new_z))
    _ensure(int(plane_id) != int(route['target_layer']),
            'route %r: new height equals baseline height'
            % (route.get('route_id'),))
    return int(plane_id), float(new_z)


def _rebuild_height_only_route(route, assignment_row, new_plane_id, new_z):
    """Rebuild a manual route with identical body XY but a new body height.

    The only geometric freedom used is the G2-allowed one: the body flat
    primitives (XY) are copied byte-identically, the interface leads are
    re-derived so the body endpoints do not move, and both fanout S-curves are
    recomputed for the new ``z`` with the frozen R=15 mm rule.
    """
    body_primitives = _body_flat_primitive_copy(route)
    start_xy = (float(body_primitives[0]['p0'][0]),
                float(body_primitives[0]['p0'][1]))
    end_xy = (float(body_primitives[-1]['p1'][0]),
              float(body_primitives[-1]['p1'][1]))
    endpoints = C.endpoints()
    source_port = tuple(float(value) for value in
                        endpoints[route['source_endpoint']]['routing_xy'])
    target_port = tuple(float(value) for value in
                        endpoints[route['target_endpoint']]['routing_xy'])
    interface_z = float(C.interface_z(route['plane']))
    dz = abs(float(new_z) - interface_z)
    ratio = max(-1.0, min(1.0, 1.0 - dz / (2.0 * F.RADIUS_MM)))
    theta = math.acos(ratio)
    footprint = 2.0 * F.RADIUS_MM * math.sin(theta)
    lead_source = math.hypot(source_port[0] - start_xy[0],
                             source_port[1] - start_xy[1]) - footprint
    lead_target = math.hypot(target_port[0] - end_xy[0],
                             target_port[1] - end_xy[1]) - footprint
    _ensure(lead_source >= F.MIN_LEAD_MM - 1e-9
            and lead_target >= F.MIN_LEAD_MM - 1e-9,
            'route %r: rebuilt leads below %.2f mm (source=%.6f target=%.6f)'
            % (route.get('route_id'), F.MIN_LEAD_MM, lead_source, lead_target))
    row = dict(assignment_row)
    row['target_layer'] = int(new_plane_id)
    row['target_plane'] = int(new_plane_id)
    row['target_z_mm'] = float(new_z)
    source_transition = F.candidate_transitions(
        row, 'source', int(new_plane_id), leads=[lead_source],
        target_z=float(new_z))[0]
    target_transition = F.candidate_transitions(
        row, 'target', int(new_plane_id), leads=[lead_target],
        target_z=float(new_z))[0]
    return A.assemble_route(row, source_transition, target_transition,
                            body_primitives)


def _synthetic_route_ids(assignment_by_id):
    picks = []
    for group in SYNTHETIC_GROUPS:
        match = None
        for route_id in sorted(assignment_by_id):
            row = assignment_by_id[route_id]
            if str(row.get('manual_group') or '') == group:
                match = route_id
                break
        _ensure(match is not None, 'no manual route found for group %r' % group)
        picks.append(match)
    return picks


def _build_synthetic_height_changed(context):
    """Return ``(picks, modified_routed, rebuilt_by_id)`` for G2 acceptance."""
    data = _cached_data(context)
    picks = _synthetic_route_ids(data['assignment_by_id'])
    by_id = _routed_by_id(data['routed'])
    planes = M.planes()
    rebuilt = {}
    for route_id in picks:
        baseline_route = by_id[route_id]
        plane_id, new_z = _choose_new_height(baseline_route, planes)
        rebuilt[route_id] = _rebuild_height_only_route(
            baseline_route, data['assignment_by_id'][route_id], plane_id,
            new_z)
    modified = copy.deepcopy(data['routed'])
    for route_id, route in rebuilt.items():
        modified = _replace_record(modified, route)
    return picks, modified, rebuilt


# ===========================================================================
# case runner
# ===========================================================================
class CaseRunner:
    def __init__(self, log):
        self.log = log
        self.cases = []

    def run(self, name, category, function, skip=None):
        if skip:
            self.cases.append(dict(name=name, category=category, passed=True,
                                   skipped=True, detail=str(skip)))
            self.log('[SKIP] %-10s %s (%s)' % (category, name, skip))
            return
        started = time.time()
        case = dict(name=name, category=category, started_at=datetime.now()
                    .isoformat(timespec='seconds'))
        try:
            detail = function()
            passed = True
            if isinstance(detail, dict) and detail.get('passed') is False:
                passed = False
            case.update(passed=passed, detail=detail)
        except Exception as error:  # noqa: BLE001 - reported as a failed case
            case.update(passed=False,
                        detail='%s: %s' % (type(error).__name__, error),
                        traceback=traceback.format_exc()[-4000:])
        case['seconds'] = round(time.time() - started, 2)
        self.cases.append(case)
        self.log('[%s] %-10s %s (%.2fs)'
                 % ('PASS' if case['passed'] else 'FAIL', category, name,
                    case['seconds']))
        return case


# ===========================================================================
# case 1: contract unit tests (cheap, dictionary level)
# ===========================================================================
def _check_contract(block, expected_violations, expected_kinds=None,
                    route_ids=None):
    violations = block['violations']
    details = block['details']
    _ensure(len(violations) == expected_violations,
            'expected %d contract violations, got %d (%r)'
            % (expected_violations, len(violations),
               details.get('violation_kinds')))
    if expected_kinds is not None:
        for kind in expected_kinds:
            _ensure(kind in details['violation_kinds'],
                    'expected violation kind %r in %r'
                    % (kind, details['violation_kinds']))
    if route_ids is not None:
        offending = set(details.get('offending_route_ids') or [])
        for route_id in route_ids:
            _ensure(route_id in offending,
                    'route %r missing from offending ids %r'
                    % (route_id, sorted(offending)[:10]))
    return details


def _test_contract_acceptance(context):
    data = _cached_data(context)
    detail = {}
    for policy in V.MANUAL_POLICIES:
        block = V.check_manual_contract(
            data['routed'], data['assignment_by_id'], data['baseline_by_id'],
            policy)
        details = _check_contract(block, 0)
        _ensure(details['manual_route_count'] == len(data['manual_ids']),
                'manual route count changed for policy %r' % policy)
        _ensure(details['checked'] == len(data['manual_ids']),
                'checked count changed for policy %r' % policy)
        _ensure(details['matched'] == len(data['manual_ids']),
                'matched count changed for policy %r' % policy)
        _ensure(details['policy'] == policy,
                'policy field %r != %r' % (details.get('policy'), policy))
        _ensure(isinstance(details.get('contract'), dict),
                'contract summary missing for policy %r' % policy)
        contract = details['contract']
        _ensure(list(contract['geometry_checks']) == list(V.GEOMETRY_CHECKS),
                'geometry checks echoed incorrectly for policy %r' % policy)
        for key, value in (('r15_mm', V.R15_MM),
                           ('min_3d_clearance_mm', V.MIN_3D_CLEARANCE_MM),
                           ('crossing_grouping', 'per physical z')):
            _ensure(contract['constraints'][key] == value,
                    'constraint %r not echoed for policy %r' % (key, policy))
        if policy == 'frozen':
            _ensure(contract['body_xy_fixed'] is True
                    and contract['body_z_fixed'] is True,
                    'frozen contract summary wrong')
            _ensure(sorted(contract['frozen_fields'])
                    == sorted(V.MANUAL_FROZEN_FIELDS),
                    'frozen field list changed')
        elif policy == 'height_only':
            _ensure(contract['body_xy_fixed'] is True
                    and contract['body_z_fixed'] is False,
                    'height_only contract summary wrong')
            _ensure(contract['xy_tolerance_mm'] == 1e-6,
                    'height_only XY tolerance changed')
        else:
            _ensure(contract['body_xy_fixed'] is False,
                    'fully_optimizable contract summary wrong')
        detail[policy] = dict(violations=0,
                              manual_route_count=details['manual_route_count'],
                              matched=details['matched'])
    # the frozen report block must be check_manual_frozen + additive fields
    direct = V.check_manual_frozen(data['routed'], data['assignment_by_id'],
                                   data['baseline_by_id'])
    contract_block = V.check_manual_contract(
        data['routed'], data['assignment_by_id'], data['baseline_by_id'],
        'frozen')
    trimmed = {key: value for key, value in contract_block['details'].items()
               if key not in ('policy', 'contract')}
    _ensure(_canon(trimmed) == _canon(direct['details']),
            'frozen contract report fields differ from check_manual_frozen')
    _ensure(_canon(contract_block['violations'])
            == _canon(direct['violations']),
            'frozen contract violations differ from check_manual_frozen')
    detail['frozen_equals_check_manual_frozen'] = True
    return detail


def _test_contract_height_only_accepts_rebuild(context):
    data = _cached_data(context)
    picks, modified, rebuilt = _build_synthetic_height_changed(context)
    for policy in ('height_only', 'fully_optimizable'):
        block = V.check_manual_contract(
            modified, data['assignment_by_id'], data['baseline_by_id'], policy)
        details = _check_contract(block, 0)
        _ensure(details['matched'] == len(data['manual_ids']),
                '%s rejected the legally rebuilt manual routes: %r'
                % (policy, details['violation_kinds']))
        _ensure(details['body_z_changed_count'] == len(picks),
                '%s body_z_changed_count=%r expected %d'
                % (policy, details.get('body_z_changed_count'), len(picks)))
        _ensure(set(picks).issubset(set(details['body_z_changed_route_ids'])),
                '%s did not record the changed body z route ids' % policy)
    if True:
        frozen = V.check_manual_contract(
            modified, data['assignment_by_id'], data['baseline_by_id'],
            'frozen')
        _check_contract(frozen, len(picks),
                        expected_kinds=['manual_route_geometry_changed'],
                        route_ids=picks)
        _ensure(set(frozen['details']['mismatch_route_ids']) == set(picks),
                'frozen mismatch ids %r != %r'
                % (frozen['details']['mismatch_route_ids'], picks))
    # the rebuilt routes must still pass every per-route geometry check
    geometry = {}
    for route_id in picks:
        route = rebuilt[route_id]
        groups = (
            ('structure', V.check_structure([route], data['model'],
                                            data['endpoints'])),
            ('native_metadata', V.check_native_metadata(
                [route], data['model'], data['assignment_by_id'])),
            ('radius', V.check_radius([route])),
            ('glass', V.check_glass([route])),
        )
        for name, block in groups:
            _ensure(len(block['violations']) == 0,
                    'rebuilt route %r failed %s: %r'
                    % (route_id, name, block['details']['violation_kinds']))
            geometry.setdefault(name, 0)
            geometry[name] += 1
    # identity is untouched, body XY is byte-identical
    by_baseline = data['baseline_by_id']
    for route_id in picks:
        rebuilt_route = rebuilt[route_id]
        for field in V.MANUAL_IDENTITY_FIELDS:
            _ensure(_canon(rebuilt_route.get(field))
                    == _canon(by_baseline[route_id].get(field)),
                    'rebuilt route %r identity field %r changed'
                    % (route_id, field))
        _ensure(_canon(V._body_flat_xy_fingerprint(rebuilt_route))
                == _canon(V._body_flat_xy_fingerprint(by_baseline[route_id])),
                'rebuilt route %r body XY fingerprint changed'
                % (route_id,))
    return dict(picks=picks, geometry_checks=geometry,
                frozen_violations=len(picks),
                height_only_accepted=True)


def _copy_first_manual_route(context, route_id=None):
    data = _cached_data(context)
    by_id = _routed_by_id(data['routed'])
    route_id = route_id if route_id is not None else data['manual_ids'][0]
    return route_id, copy.deepcopy(by_id[route_id])


def _test_contract_rejections(context):
    data = _cached_data(context)
    results = {}

    def expect_violations(policy, routed, count, kinds=None, route_ids=None):
        block = V.check_manual_contract(
            routed, data['assignment_by_id'], data['baseline_by_id'], policy)
        details = _check_contract(block, count, expected_kinds=kinds,
                                  route_ids=route_ids)
        return dict(violations=len(block['violations']),
                    violation_kinds=details['violation_kinds'])

    # 1. body XY shift > 1e-6 mm is rejected by height_only, free under G3
    route_id, route = _copy_first_manual_route(context)
    body_index = V.body_flat_indices(route)[0]
    route['parts'][body_index]['primitives'][0]['p0'][0] += 2e-6
    routed_bad_xy = _replace_record(data['routed'], route)
    results['xy_shift_2e-6_height_only'] = expect_violations(
        'height_only', routed_bad_xy, 1,
        kinds=['manual_body_xy_changed'], route_ids=[route_id])
    results['xy_shift_2e-6_fully_optimizable'] = expect_violations(
        'fully_optimizable', routed_bad_xy, 0)
    # 2. body XY shift within the 1e-6 tolerance is accepted
    route_id, route = _copy_first_manual_route(context)
    body_index = V.body_flat_indices(route)[0]
    route['parts'][body_index]['primitives'][0]['p0'][0] += 5e-7
    routed_tol = _replace_record(data['routed'], route)
    results['xy_shift_5e-7_height_only'] = expect_violations(
        'height_only', routed_tol, 0)
    # 3. endpoint identity change: G2/G3 contracts reject it directly; the
    #    frozen contract only freezes parts/z fields, so the always-on
    #    coverage check is the one that must reject an identity change.
    route_id, route = _copy_first_manual_route(context)
    route['source_endpoint'] = 'N99:9:9'
    routed_bad_id = _replace_record(data['routed'], route)
    results['endpoint_changed_frozen_contract'] = expect_violations(
        'frozen', routed_bad_id, 0)
    coverage_block = V.check_coverage(
        data['payload'], routed_bad_id, routed_bad_id, [],
        list(data['baseline_by_id'].values()), {},
        data['assignment_by_id'])
    _ensure('identity_field_mismatch'
            in coverage_block['details']['violation_kinds'],
            'coverage did not reject the changed endpoint: %r'
            % coverage_block['details']['violation_kinds'])
    results['endpoint_changed_coverage'] = dict(
        violations=len(coverage_block['violations']),
        violation_kinds=coverage_block['details']['violation_kinds'])
    results['endpoint_changed_height_only'] = expect_violations(
        'height_only', routed_bad_id, 1,
        kinds=['manual_identity_changed'], route_ids=[route_id])
    results['endpoint_changed_fully_optimizable'] = expect_violations(
        'fully_optimizable', routed_bad_id, 1,
        kinds=['manual_identity_changed'], route_ids=[route_id])
    # 4. body flat count change: G2 rejects, G3 (geometry free) allows
    route_id, route = _copy_first_manual_route(context)
    parts = route['parts']
    route['parts'] = [copy.deepcopy(parts[0]), copy.deepcopy(parts[1]),
                      copy.deepcopy(parts[3]), copy.deepcopy(parts[4])]
    routed_no_body = _replace_record(data['routed'], route)
    results['body_flat_removed_height_only'] = expect_violations(
        'height_only', routed_no_body, 1,
        kinds=['manual_body_flat_count_changed'], route_ids=[route_id])
    results['body_flat_removed_fully_optimizable'] = expect_violations(
        'fully_optimizable', routed_no_body, 0)
    # 5. a missing manual route is a violation under every policy
    route_id = data['manual_ids'][0]
    routed_missing = [record for record in data['routed']
                      if int(record['route_id']) != route_id]
    for policy in V.MANUAL_POLICIES:
        results['missing_route_%s' % policy] = expect_violations(
            policy, routed_missing, 1, kinds=['manual_route_missing'],
            route_ids=[route_id])
    # 6. contract must NOT reject a legal non-model body z (full geometry
    #    checks do that instead): z freedom belongs to G2/G3, legality to the
    #    always-on native-metadata check.
    route_id, route = _copy_first_manual_route(context)
    body_index = V.body_flat_indices(route)[0]
    route['parts'][body_index]['z_mm'] = -0.37
    routed_bad_z = _replace_record(data['routed'], route)
    block = V.check_manual_contract(routed_bad_z, data['assignment_by_id'],
                                    data['baseline_by_id'], 'height_only')
    details = _check_contract(block, 0)
    _ensure(details['body_z_changed_count'] >= 1,
            'z-change not recorded as an allowed body-z change')
    illegal = V.check_native_metadata([route], data['model'], {})
    _ensure(len(illegal['violations']) >= 1,
            'native_metadata did not reject non-model body z')
    _ensure('flat_z_not_model_height' in illegal['details']['violation_kinds'],
            'native_metadata violation kind changed: %r'
            % illegal['details']['violation_kinds'])
    results['non_model_z'] = dict(
        contract_accepted=True,
        metadata_violation_kinds=illegal['details']['violation_kinds'])
    return results


def _test_contract_units(context):
    detail = {}
    detail['acceptance'] = _test_contract_acceptance(context)
    detail['height_only_rebuild'] = _test_contract_height_only_accepts_rebuild(
        context)
    detail['rejections'] = _test_contract_rejections(context)
    return detail


# ===========================================================================
# case 2: frozen regression on the authoritative snapshot
# ===========================================================================
def _test_regression(context):
    inputs = _cached_inputs(context)
    out_dir = Path(context['out_dir']) / 'regression_frozen'
    data = _cached_data(context)
    report = X.validate_xyz(
        run_dir=inputs['run_dir'],
        baseline_dir=inputs['baseline_dir'],
        out_dir=out_dir,
        manual_policy='frozen',
        skip_min_clearance=False,
        skip_synthetic=False,
        log=context['log'],
    )
    context['regression_report'] = report
    counts = report.get('counts') or {}
    _ensure(report.get('validation_pass') is True,
            'frozen regression did not PASS: violations=%r kinds=%r'
            % (report.get('violation_count'), report.get('violation_kinds')))
    _ensure(int(report.get('violation_count') or 0) == 0,
            'frozen regression violation_count=%r'
            % report.get('violation_count'))
    for key in ('routed', 'failed', 'records'):
        _ensure(counts.get(key) == EXPECT[key],
                'counts[%r]=%r expected %r'
                % (key, counts.get(key), EXPECT[key]))
    for key in ('crossings', 'crossing_pairs', 'mid_transitions',
                'transitions', 'flat_arc_count', 'audited_heights'):
        actual = counts.get('same_plane_crossings' if key == 'crossings'
                            else 'same_plane_crossing_pairs'
                            if key == 'crossing_pairs' else key)
        _ensure(actual == EXPECT[key],
                'counts[%r]=%r expected %r' % (key, actual, EXPECT[key]))
    clearance = counts.get('min_3d_clearance_mm')
    _ensure(_close(clearance, EXPECT['min_3d_clearance'],
                   EXPECT['min_3d_clearance_tol']),
            'min_3d_clearance=%r expected %r'
            % (clearance, EXPECT['min_3d_clearance']))
    total_length = counts.get('total_length_mm')
    _ensure(_close(total_length, EXPECT['total_length'],
                   EXPECT['total_length_tol']),
            'total_length=%r expected %r' % (total_length, EXPECT['total_length']))
    _ensure(counts.get('manual_route_count') == EXPECT['manual_routes'],
            'manual_route_count=%r' % counts.get('manual_route_count'))
    _ensure(counts.get('manual_geometry_mismatch_count')
            == EXPECT['manual_geometry_mismatch_count'],
            'manual_geometry_mismatch_count=%r'
            % counts.get('manual_geometry_mismatch_count'))
    # -- policy report -----------------------------------------------------
    _ensure(report.get('manual_policy') == 'frozen',
            'report manual_policy=%r' % report.get('manual_policy'))
    policy_report = report.get('policy_report') or {}
    _ensure(policy_report.get('policy') == 'frozen',
            'policy_report policy=%r' % policy_report.get('policy'))
    _ensure(policy_report.get('passed') is True,
            'policy_report passed=%r' % policy_report.get('passed'))
    _ensure(int(policy_report.get('violation_count') or 0) == 0,
            'policy_report violation_count=%r'
            % policy_report.get('violation_count'))
    _ensure(policy_report.get('manual_route_count') == EXPECT['manual_routes'],
            'policy_report manual_route_count=%r'
            % policy_report.get('manual_route_count'))
    _ensure(policy_report.get('matched') == EXPECT['manual_routes'],
            'policy_report matched=%r' % policy_report.get('matched'))
    manual_block = (report.get('checks') or {}).get('manual_frozen') or {}
    _ensure(manual_block.get('policy') == 'frozen',
            'checks.manual_frozen.policy=%r' % manual_block.get('policy'))
    _ensure(int(manual_block.get('violations') or 0) == 0,
            'checks.manual_frozen.violations=%r'
            % manual_block.get('violations'))
    _ensure(isinstance(manual_block.get('contract'), dict),
            'checks.manual_frozen.contract missing')
    # -- summary helper ----------------------------------------------------
    summary = X.summarize_report(report)
    expected_summary = dict(
        validation_pass=True,
        violations=0,
        routed=EXPECT['routed'],
        failed=EXPECT['failed'],
        crossings=EXPECT['crossings'],
        crossing_pairs=EXPECT['crossing_pairs'],
        mid_transitions=EXPECT['mid_transitions'],
        min_3d_clearance=EXPECT['min_3d_clearance'],
        total_length=EXPECT['total_length'],
        policy='frozen',
        policy_violations=0,
    )
    for key, value in expected_summary.items():
        if isinstance(value, float):
            _ensure(_close(summary[key], value, 1e-9),
                    'summarize_report[%r]=%r expected %r'
                    % (key, summary[key], value))
        else:
            _ensure(summary[key] == value,
                    'summarize_report[%r]=%r expected %r'
                    % (key, summary[key], value))
    _ensure(set(summary) == set(expected_summary),
            'summarize_report keys %r != expected %r'
            % (sorted(summary), sorted(expected_summary)))
    # -- file provenance ---------------------------------------------------
    path = out_dir / 'validation.json'
    _ensure(path.exists(), 'validation.json not written: %s' % path)
    written = X.load_validation_report(path)
    _ensure(written.get('manual_policy') == 'frozen',
            'written manual_policy=%r' % written.get('manual_policy'))
    _ensure(isinstance(written.get('policy_report'), dict),
            'written policy_report missing')
    _ensure(X.summarize_report(written) == summary,
            'summarize_report mismatch between in-memory and written report')
    context['regression_summary'] = summary
    return dict(
        summary=summary,
        validation_pass=report.get('validation_pass'),
        routes_file_sha256=report.get('routes_file_sha256'),
        baseline_dir=report.get('baseline_dir'),
        run_source=inputs['run_source'],
        validation_file=str(path),
        runtime_seconds=report.get('runtime_seconds'),
    )


# ===========================================================================
# case 3: default behaviour unchanged (old validate_run report comparison)
# ===========================================================================
def _test_default_unchanged(context):
    report = context.get('regression_report')
    _ensure(report is not None, 'regression report missing')
    out_dir = Path(context['out_dir'])
    reference_path = out_dir / PRE_EDIT_REFERENCE
    reference_source = 'pre-edit validate_run output (captured before edit)'
    if not reference_path.exists():
        reference_path = ARCHIVED_REPORT
        reference_source = 'archived NATIVE_3D_JOINT_OPT_1024/validation.json'
    reference = _read_json(reference_path)
    _ensure(isinstance(reference, dict),
            'old validator report not readable: %s' % reference_path)
    diffs = []
    diffs.extend(_deep_subset_diffs(reference.get('counts') or {},
                                    report.get('counts') or {}, 'counts'))
    diffs.extend(_deep_subset_diffs(reference.get('checks') or {},
                                    report.get('checks') or {}, 'checks'))
    diffs.extend(_deep_subset_diffs(reference.get('model') or {},
                                    report.get('model') or {}, 'model'))
    diffs.extend(_deep_subset_diffs(
        reference.get('synthetic_consistency') or {},
        report.get('synthetic_consistency') or {}, 'synthetic_consistency'))
    for key in ('validation_pass', 'geometry_pass', 'contract_pass',
                'violation_count', 'violation_kinds',
                'violation_counts_by_check', 'offending_route_ids',
                'offending_route_count', 'exit_code', 'violations',
                'violations_truncated', 'regression'):
        diffs.extend(_deep_subset_diffs({key: reference.get(key)},
                                        {key: report.get(key)}, key))
    # the frozen manual block itself must be identical modulo additive fields
    old_manual = ((reference.get('checks') or {}).get('manual_frozen') or {})
    new_manual = ((report.get('checks') or {}).get('manual_frozen') or {})
    diffs.extend(_deep_subset_diffs(old_manual, new_manual,
                                    'manual_frozen',
                                    REPORT_SKIP_KEYS - {'policy', 'contract'}))
    _ensure(not diffs,
            'default (frozen) behaviour changed: %d differences, first: %r'
            % (len(diffs), diffs[:8]))
    # archived report is provenance for the 2409 numbers
    archived = _read_json(ARCHIVED_REPORT)
    archived_counts_match = None
    if isinstance(archived, dict) and isinstance(archived.get('counts'), dict):
        archived_counts_match = archived['counts'] == report.get('counts')
        _ensure(archived_counts_match,
                'new frozen counts differ from the archived validation.json: %r'
                % [key for key in archived['counts']
                   if archived['counts'].get(key)
                   != (report.get('counts') or {}).get(key)])
    return dict(reference=str(reference_path),
                reference_source=reference_source,
                difference_count=0,
                archive_counts_equal=archived_counts_match,
                additive_report_keys=sorted(
                    set(report) - set(reference)),
                additive_check_keys=sorted(
                    set(new_manual) - set(old_manual)))


# ===========================================================================
# case 4: synthetic height_only full validation path
# ===========================================================================
def _test_synthetic_height_only_full(context):
    inputs = _cached_inputs(context)
    data = _cached_data(context)
    picks, modified, rebuilt = _build_synthetic_height_changed(context)
    synth_root = Path(context['out_dir']) / 'synthetic_height_only'
    run_dir = synth_root / 'run'
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(data['payload'])
    payload['routes'] = modified
    _write_json(run_dir / 'routes_l3d.json', payload)
    shutil.copyfile(data['run_dir'] / 'assignment_1024.csv',
                    run_dir / 'assignment_1024.csv')
    layer_planes = data['run_dir'] / 'layer_planes.json'
    if not layer_planes.exists():
        layer_planes = data['baseline_dir'] / 'layer_planes.json'
    _ensure(layer_planes.exists(),
            'no layer_planes.json to build the synthetic run dir')
    shutil.copyfile(layer_planes, run_dir / 'layer_planes.json')
    out_dir = synth_root / 'validation_height_only'
    report = X.validate_xyz(
        run_dir=run_dir,
        baseline_dir=inputs['baseline_dir'],
        out_dir=out_dir,
        manual_policy='height_only',
        skip_min_clearance=True,
        skip_synthetic=True,
        log=context['log'],
    )
    checks = report.get('checks') or {}
    # -- the G2 contract accepts the legal rebuild -------------------------
    policy_report = report.get('policy_report') or {}
    _ensure(report.get('manual_policy') == 'height_only',
            'synthetic report manual_policy=%r'
            % report.get('manual_policy'))
    _ensure(policy_report.get('passed') is True,
            'height_only rejected legal rebuild: %r'
            % policy_report.get('violation_kinds'))
    _ensure(int(policy_report.get('violation_count') or 0) == 0,
            'height_only contract violations=%r'
            % policy_report.get('violation_count'))
    manual = checks.get('manual_frozen') or {}
    _ensure(int(manual.get('violations') or 0) == 0,
            'checks.manual_frozen violations=%r'
            % manual.get('violation_kinds'))
    _ensure(manual.get('manual_route_count') == len(data['manual_ids']),
            'manual_route_count changed in synthetic run')
    _ensure(manual.get('matched') == len(data['manual_ids']),
            'matched=%r in synthetic run' % manual.get('matched'))
    _ensure(int(manual.get('body_z_changed_count') or 0) == len(picks),
            'body_z_changed_count=%r expected %d'
            % (manual.get('body_z_changed_count'), len(picks)))
    _ensure(set(picks).issubset(
        set(manual.get('body_z_changed_route_ids') or [])),
        'changed manual route ids not recorded in synthetic report')
    _ensure(set(picks).issubset(
        set(policy_report.get('body_z_changed_route_ids') or [])),
        'changed manual route ids missing from policy_report')
    _ensure((manual.get('contract') or {}).get('body_xy_fixed') is True,
            'height_only contract summary not carried in the report')
    # -- all geometry checks still ran (nothing skipped) -------------------
    for name in V.GEOMETRY_CHECKS + V.CONTRACT_CHECKS:
        _ensure(name in checks, 'check %r missing from synthetic report' % name)
    _ensure(checks['clearance'].get('routes_checked') == len(modified),
            'clearance did not check every route: %r'
            % checks['clearance'].get('routes_checked'))
    _ensure(checks.get('clearance', {}).get('clearance_mm')
            == V.MIN_3D_CLEARANCE_MM,
            'clearance rule changed: %r'
            % checks.get('clearance', {}).get('clearance_mm'))
    _ensure(checks['crossings'].get('audited_heights') == EXPECT['audited_heights'],
            'crossing audit heights=%r'
            % checks['crossings'].get('audited_heights'))
    _ensure('strict D56' in str(checks['crossings'].get('crossing_rule')),
            'D56 crossing rule string changed')
    for name in ('structure', 'native_metadata', 'radius', 'glass',
                 'coverage', 'ports'):
        block = checks.get(name) or {}
        _ensure(int(block.get('violations') or 0) == 0,
                'legal height rebuild surprisingly failed %r: %r'
                % (name, block.get('violation_kinds')))
    # -- global routability is not claimed for this synthetic case --------
    geometry_violations = sum(
        int((checks.get(name) or {}).get('violations') or 0)
        for name in V.GEOMETRY_CHECKS)
    _ensure(report.get('contract_pass') is True,
            'contract_pass=%r in synthetic report' % report.get('contract_pass'))
    _ensure(bool(report.get('validation_pass'))
            == (geometry_violations == 0 and report.get('contract_pass')),
            'validation_pass is not derived from the checks (hidden violations!)')
    if geometry_violations > 0:
        _ensure(report.get('validation_pass') is False,
                'geometry violations were hidden by a PASS')
        _ensure(report.get('violation_count', 0) >= geometry_violations,
                'violation_count does not include the geometry violations')
    # -- frozen policy would reject the very same run ---------------------
    frozen_block = V.check_manual_contract(
        modified, data['assignment_by_id'], data['baseline_by_id'], 'frozen')
    _ensure(len(frozen_block['violations']) == len(picks),
            'frozen contract violations=%d expected %d'
            % (len(frozen_block['violations']), len(picks)))
    _ensure(set(frozen_block['details']['mismatch_route_ids']) == set(picks),
            'frozen mismatch ids %r'
            % frozen_block['details']['mismatch_route_ids'])
    written = X.load_validation_report(out_dir)
    _ensure(written.get('manual_policy') == 'height_only'
            and isinstance(written.get('policy_report'), dict),
            'written synthetic validation.json misses the policy block')
    detail = dict(
        run_dir=str(run_dir),
        validation_file=str(out_dir / 'validation.json'),
        picks=picks,
        policy_report_passed=policy_report.get('passed'),
        body_z_changed_count=manual.get('body_z_changed_count'),
        contract_pass=report.get('contract_pass'),
        geometry_pass=report.get('geometry_pass'),
        validation_pass=report.get('validation_pass'),
        geometry_violation_kinds={
            name: (checks.get(name) or {}).get('violation_kinds')
            for name in V.GEOMETRY_CHECKS
            if int((checks.get(name) or {}).get('violations') or 0) > 0},
        note=('synthetic rebuilt run is not required to be globally routable; '
              'the policy contract acceptance and the full-check execution '
              'are the assertions'),
        frozen_rejected=len(frozen_block['violations']),
    )
    context['synthetic_summary'] = detail
    return detail


# ===========================================================================
# case 5: constraints / rules are not weakened
# ===========================================================================
def _test_constraints(context):
    report = context.get('regression_report')
    _ensure(report is not None, 'regression report missing')
    data = _cached_data(context)
    checks = report.get('checks') or {}
    result = {}

    # -- frozen constants --------------------------------------------------
    constants = dict(
        R15_MM=V.R15_MM,
        MIN_3D_CLEARANCE_MM=V.MIN_3D_CLEARANCE_MM,
        MIN_LAYER_PITCH_MM=V.MIN_LAYER_PITCH_MM,
        TOL_RADIUS_MM=V.TOL_RADIUS_MM,
        TOL_POS_MM=V.TOL_POS_MM,
        TOL_Z_MM=V.TOL_Z_MM,
    )
    _ensure(constants['R15_MM'] == 15.0, 'R15 changed: %r' % constants)
    _ensure(constants['MIN_3D_CLEARANCE_MM'] == 0.05,
            '50 um clearance changed: %r' % constants)
    _ensure(constants['MIN_LAYER_PITCH_MM'] == 0.05,
            '50 um layer pitch changed: %r' % constants)
    _ensure(list(V.GEOMETRY_CHECKS) == ['structure', 'native_metadata',
                                        'radius', 'glass', 'clearance',
                                        'crossings'],
            'GEOMETRY_CHECKS changed: %r' % (V.GEOMETRY_CHECKS,))
    _ensure(list(V.CONTRACT_CHECKS) == ['coverage', 'ports', 'manual_frozen',
                                        'model', 'synthetic'],
            'CONTRACT_CHECKS changed: %r' % (V.CONTRACT_CHECKS,))
    result['constants'] = constants
    result['geometry_checks'] = list(V.GEOMETRY_CHECKS)

    # -- public signatures -------------------------------------------------
    signature = inspect.signature(V.validate_run)
    parameters = list(signature.parameters)
    _ensure(parameters == ['run_dir', 'baseline_dir', 'out_dir',
                           'skip_min_clearance', 'log', 'regression',
                           'skip_synthetic', 'manual_policy'],
            'validate_run parameter order changed: %r' % (parameters,))
    _ensure(signature.parameters['manual_policy'].default == 'frozen',
            'validate_run manual_policy default is not frozen')
    _ensure(str(inspect.signature(V.check_manual_contract))
            == "(routed, assignment_by_id, baseline_by_id, policy='frozen')",
            'check_manual_contract signature changed: %r'
            % (str(inspect.signature(V.check_manual_contract)),))
    _ensure(str(inspect.signature(X.validate_xyz)).startswith(
        '(run_dir, baseline_dir, out_dir, manual_policy='),
        'validate_xyz signature changed: %r'
        % (str(inspect.signature(X.validate_xyz)),))

    # -- R15 / clearance / crossing report numbers -------------------------
    radius = checks.get('radius') or {}
    _ensure(radius.get('flat_arc_count') == EXPECT['flat_arc_count'],
            'flat_arc_count=%r' % radius.get('flat_arc_count'))
    _ensure(radius.get('transition_count') == EXPECT['transitions'],
            'transition_count=%r' % radius.get('transition_count'))
    _ensure(int(radius.get('violations') or 0) == 0, 'radius violations present')
    _ensure(radius.get('min_flat_arc_radius_mm') == 15.0,
            'flat arc radius min=%r' % radius.get('min_flat_arc_radius_mm'))
    sampled = radius.get('transition_min_sampled_radius')
    _ensure(sampled is not None and sampled >= 15.0 - 1e-6,
            'sampled transition radius=%r' % sampled)
    clearance = checks.get('clearance') or {}
    _ensure(clearance.get('clearance_mm') == 0.05,
            'clearance_mm=%r' % clearance.get('clearance_mm'))
    _ensure(clearance.get('min_3d_clearance_lower_bound_mm') == 0.05,
            'clearance lower bound=%r'
            % clearance.get('min_3d_clearance_lower_bound_mm'))
    crossings = checks.get('crossings') or {}
    totals = crossings.get('totals') or {}
    _ensure(totals.get('crossings') == EXPECT['crossings'],
            'crossings=%r' % totals.get('crossings'))
    _ensure(totals.get('crossing_pairs') == EXPECT['crossing_pairs'],
            'crossing_pairs=%r' % totals.get('crossing_pairs'))
    _ensure(int(totals.get('violations') or 0) == 0,
            'D56 crossing violations=%r' % totals.get('violations'))
    _ensure(crossings.get('audited_heights') == EXPECT['audited_heights'],
            'audited_heights=%r' % crossings.get('audited_heights'))
    _ensure('strict D56' in str(crossings.get('crossing_rule')),
            'D56 crossing rule string changed: %r'
            % crossings.get('crossing_rule'))
    _ensure('physical z' in str(crossings.get('crossing_rule')),
            'crossing grouping changed: %r' % crossings.get('crossing_rule'))
    result['radius'] = dict(
        flat_arc_count=radius.get('flat_arc_count'),
        transition_count=radius.get('transition_count'),
        min_flat_arc_radius_mm=radius.get('min_flat_arc_radius_mm'),
        transition_min_sampled_radius=sampled)
    result['crossings'] = dict(totals=totals,
                               audited_heights=crossings.get('audited_heights'),
                               crossing_rule=crossings.get('crossing_rule'))
    result['clearance'] = dict(
        clearance_mm=clearance.get('clearance_mm'),
        min_3d_clearance_mm=clearance.get('min_3d_clearance_mm'),
        lower_bound_mm=clearance.get('min_3d_clearance_lower_bound_mm'))

    # -- archiVal report: geometry check blocks identical to the old run ---
    archive = _read_json(ARCHIVED_REPORT)
    old_diffs = []
    if isinstance(archive, dict):
        for name in V.GEOMETRY_CHECKS + ('coverage', 'ports'):
            old_diffs.extend(_deep_subset_diffs(
                (archive.get('checks') or {}).get(name) or {},
                checks.get(name) or {}, 'checks.%s' % name))
    _ensure(not old_diffs,
            'geometry check blocks changed vs archived report: %r'
            % old_diffs[:8])
    result['geometry_blocks_equal_to_archive'] = True

    # -- the validator's own synthetic rejection suite still passes --------
    synthetic = report.get('synthetic_consistency') or {}
    _ensure(synthetic.get('all_passed') is True,
            'synthetic consistency suite failed: %r' % synthetic.get('error'))
    tests = {test.get('name'): test for test in synthetic.get('tests') or []}
    expected_true = (
        'duckout_L6_L7_L6_accepted', 'complete_native_route_accepted',
        'two_excursions_accepted',
        'z_offset_49um_rejected', 'radius_14_rejected',
        'position_discontinuity_1e-3_rejected', 'flat_overlap_rejected')
    missing = [name for name in expected_true if name not in tests]
    _ensure(not missing, 'synthetic suite cases missing: %r' % missing)
    for name in expected_true:
        _ensure(tests[name].get('passed') is True,
                'synthetic case %r failed: %r'
                % (name, tests[name].get('detail')))
    result['synthetic_suite'] = {name: True for name in expected_true}

    # -- direct negative checks on a *manual* route ------------------------
    manual_route = copy.deepcopy(
        _routed_by_id(data['routed'])[data['manual_ids'][0]])
    body_index = V.body_flat_indices(manual_route)[0]
    # 50 um pitch / model-height rule: a non-model body z must be rejected
    illegal_z = copy.deepcopy(manual_route)
    illegal_z['parts'][body_index]['z_mm'] = -0.37
    metadata_block = V.check_native_metadata([illegal_z], data['model'], {})
    _ensure(len(metadata_block['violations']) >= 1,
            'native_metadata accepted a non-model body z')
    _ensure('flat_z_not_model_height'
            in metadata_block['details']['violation_kinds'],
            'native_metadata kinds=%r'
            % metadata_block['details']['violation_kinds'])
    structure_block = V.check_structure([illegal_z], data['model'],
                                        data['endpoints'])
    _ensure(len(structure_block['violations']) >= 1,
            'structure accepted a non-model body z')
    result['manual_route_non_model_z_rejected'] = dict(
        native_metadata=metadata_block['details']['violation_kinds'],
        structure=structure_block['details']['violation_kinds'])
    # R15: a declared R=14 flat arc on a manual route must be rejected
    illegal_radius = copy.deepcopy(manual_route)
    primitive_index = None
    for index, primitive in enumerate(
            illegal_radius['parts'][body_index]['primitives']):
        if primitive.get('kind') == 'arc':
            primitive_index = index
            break
    _ensure(primitive_index is not None, 'manual route has no body arc')
    illegal_radius['parts'][body_index]['primitives'][primitive_index][
        'radius'] = 14.0
    radius_block = V.check_radius([illegal_radius])
    _ensure(len(radius_block['violations']) >= 1,
            'check_radius accepted a declared R=14 arc on a manual route')
    result['manual_route_r14_rejected'] = radius_block['details'][
        'violation_kinds']
    # identity / port rule: port pose perturbation must be rejected
    illegal_port = copy.deepcopy(manual_route)
    illegal_port['parts'][0]['primitives'][0]['p0'][0] += 1e-3
    port_block = V.check_structure([illegal_port], data['model'],
                                   data['endpoints'])
    _ensure(len(port_block['violations']) >= 1,
            'structure accepted a shifted manual-route port')
    result['manual_route_port_shift_rejected'] = port_block['details'][
        'violation_kinds']

    # -- policy must never weaken the pass/fail definition -----------------
    block_by_name = {name: int((checks.get(name) or {}).get('violations') or 0)
                     for name in V.GEOMETRY_CHECKS + V.CONTRACT_CHECKS}
    _ensure(report.get('geometry_pass') == all(
        block_by_name[name] == 0 for name in V.GEOMETRY_CHECKS),
        'geometry_pass does not cover all geometry checks')
    _ensure(report.get('contract_pass') == all(
        block_by_name[name] == 0 for name in V.CONTRACT_CHECKS),
        'contract_pass does not cover all contract checks')
    result['pass_derivation'] = dict(
        geometry_pass=report.get('geometry_pass'),
        contract_pass=report.get('contract_pass'),
        validation_pass=report.get('validation_pass'))
    return result


# ===========================================================================
# case 6: policy_report normalisation + invalid policy handling
# ===========================================================================
def _test_policy_plumbing(context):
    data = _cached_data(context)
    # 1. build_policy_report works on a report stripped of additive fields
    report = context.get('regression_report')
    if report is None:
        out_dir = Path(context['out_dir'])
        report = _read_json(out_dir / 'regression_frozen' / 'validation.json')
        if not isinstance(report, dict):
            report = _read_json(ARCHIVED_REPORT)
    _ensure(isinstance(report, dict), 'no report available for plumbing test')
    stripped = {key: value for key, value in report.items()
                if key not in ('manual_policy', 'policy_report')}
    policy_report = X.build_policy_report(stripped, 'frozen')
    _ensure(policy_report.get('policy') == 'frozen',
            'build_policy_report policy=%r' % policy_report.get('policy'))
    _ensure(policy_report.get('passed') is True,
            'build_policy_report passed=%r' % policy_report.get('passed'))
    _ensure(policy_report.get('manual_route_count')
            == len(data['manual_ids']),
            'build_policy_report manual count=%r'
            % policy_report.get('manual_route_count'))
    # 2. a policy violation can never stay hidden behind validation_pass=True
    fake = dict(validation_pass=True, geometry_pass=True, contract_pass=True,
                exit_code=0, violation_count=2, violations=[], counts={},
                checks={'manual_frozen': dict(
                    violations=2, violation_kinds={'x': 2},
                    manual_route_count=368, checked=368, matched=366,
                    mismatch_count=2, mismatch_route_ids=[1, 2],
                    rule='fake', contract=None)})
    normalised = X._normalize_report(fake, 'height_only', log=lambda *_: None)
    _ensure(normalised.get('passed') is False,
            'normaliser kept policy violations as passed')
    _ensure(fake.get('validation_pass') is False,
            'normaliser did not force validation_pass=False')
    _ensure(fake.get('exit_code') == 1,
            'normaliser did not force exit_code=1')
    # 3. invalid policy names are rejected everywhere
    raised = []
    for function, kwargs in (
            (lambda: V.validate_run(manual_policy='bogus'), {}),
            (lambda: V.check_manual_contract(
                data['routed'], data['assignment_by_id'],
                data['baseline_by_id'], 'bogus'), {}),
            (lambda: X.validate_xyz(
                run_dir=data['run_dir'], baseline_dir=data['baseline_dir'],
                out_dir=Path(context['out_dir']) / 'bogus_policy',
                manual_policy='bogus', log=lambda *_: None), {})):
        try:
            function()
        except ValueError:
            raised.append(True)
        else:
            raised.append(False)
    _ensure(all(raised), 'invalid manual_policy was accepted somewhere: %r'
            % raised)
    # 4. CLI input-error exit code 2 (missing run dir) is cheap to verify
    missing = Path(context['out_dir']) / 'does_not_exist'
    import contextlib
    import io
    stderr_buffer = io.StringIO()
    with contextlib.redirect_stderr(stderr_buffer):
        exit_code = X.main(['--run-dir', str(missing), '--baseline-dir',
                            str(data['baseline_dir']), '--out-dir',
                            str(Path(context['out_dir']) / 'cli_error')])
    _ensure(exit_code == 2, 'CLI exit code for a missing run dir is %r'
            % exit_code)
    _ensure('INPUT ERROR' in stderr_buffer.getvalue(),
            'CLI did not report the input error on stderr')
    # 5. load_validation_report accepts a directory or a file
    written = Path(context['out_dir']) / 'regression_frozen' / 'validation.json'
    if not written.exists():
        for candidate in (Path(context['out_dir']) / PRE_EDIT_REFERENCE,
                          ARCHIVED_REPORT):
            if Path(candidate).exists():
                written = Path(candidate)
                break
    _ensure(written.exists(), 'no validation report available for loader test')
    _ensure(X.load_validation_report(written)
            == X.load_validation_report(written.parent),
            'load_validation_report dir/file mismatch')
    return dict(policy_report_built=True, hidden_violation_normalised=True,
                invalid_policy_rejected=True, cli_exit_code_2=True,
                loader_dir_file_equal=True)


# ===========================================================================
# orchestration
# ===========================================================================
def run_tests(out_dir=DEFAULT_OUT_DIR, log=print, skip_full=False):
    started = time.time()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    context = dict(log=log, out_dir=out_dir)
    runner = CaseRunner(log)
    log('=' * 78)
    log('[tests] project root: %s' % ROOT)
    log('[tests] out dir    : %s' % out_dir)
    log('[tests] python     : %s' % sys.version.split()[0])
    runner.run('inputs_resolution', 'inputs',
               lambda: _cached_inputs(context))
    runner.run('contract_units', 'contract',
               lambda: _test_contract_units(context))
    runner.run('policy_plumbing', 'contract',
               lambda: _test_policy_plumbing(context))
    runner.run('frozen_regression', 'regression',
               lambda: _test_regression(context), skip=skip_full)
    runner.run('default_behaviour_unchanged', 'regression',
               lambda: _test_default_unchanged(context),
               skip=skip_full or 'regression_report' not in context)
    runner.run('constraints_not_weakened', 'constraints',
               lambda: _test_constraints(context),
               skip=skip_full or 'regression_report' not in context)
    runner.run('synthetic_height_only_full', 'synthetic',
               lambda: _test_synthetic_height_only_full(context),
               skip=skip_full)
    categories = {}
    for case in runner.cases:
        bucket = categories.setdefault(case['category'],
                                       dict(passed=0, failed=0, skipped=0))
        if case.get('skipped'):
            bucket['skipped'] += 1
        elif case['passed']:
            bucket['passed'] += 1
        else:
            bucket['failed'] += 1
    failed = [case for case in runner.cases
              if not case['passed'] and not case.get('skipped')]
    summary = dict(
        cases=len(runner.cases),
        passed=sum(1 for case in runner.cases
                   if case['passed'] and not case.get('skipped')),
        failed=len(failed),
        skipped=sum(1 for case in runner.cases if case.get('skipped')),
        all_passed=not failed,
        categories=categories,
        seconds=round(time.time() - started, 2),
    )
    result = dict(
        schema=TEST_SCHEMA,
        generated_at=datetime.now().isoformat(timespec='seconds'),
        project_root=str(ROOT),
        python=sys.version,
        out_dir=str(out_dir),
        inputs=context.get('inputs'),
        summary=summary,
        regression=context.get('regression_summary'),
        synthetic_height_only=context.get('synthetic_summary'),
        cases=runner.cases,
    )
    result_path = out_dir / 'tests_validate_xyz_result.json'
    _write_json(result_path, result)
    log('=' * 78)
    for case in runner.cases:
        if case.get('skipped'):
            continue
        if not case['passed']:
            log('[FAILED CASE] %s (%s)' % (case['name'], case['category']))
            log('  %s' % str(case.get('detail'))[:1200])
    log('[tests] %s: %d/%d cases passed, %d failed, %d skipped (%.1fs)'
        % ('ALL PASS' if summary['all_passed'] else 'FAIL',
           summary['passed'], summary['cases'] - summary['skipped'],
           summary['failed'], summary['skipped'], summary['seconds']))
    log('[tests] wrote %s' % result_path)
    return result, (0 if summary['all_passed'] else 1)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Tests for the XYZ joint-router manual-policy validator '
                    'extension (frozen / height_only / fully_optimizable).')
    parser.add_argument('--out-dir', default=str(DEFAULT_OUT_DIR),
                        help='artifact directory (default: preflight_audit/'
                             'validator_tests)')
    parser.add_argument('--skip-full', action='store_true',
                        help='skip the two 1024-route full validations '
                             '(contract unit tests only)')
    args = parser.parse_args(argv)
    result, exit_code = run_tests(out_dir=Path(args.out_dir),
                                  log=lambda message: print(message,
                                                            flush=True),
                                  skip_full=args.skip_full)
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
