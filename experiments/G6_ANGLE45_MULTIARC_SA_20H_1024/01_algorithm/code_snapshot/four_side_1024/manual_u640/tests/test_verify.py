# -*- coding: utf-8 -*-
"""Tests of ``verify.verify_all`` on self-built legal and illegal samples.

The legal sample is a quarter-pair U-turn between two real ports of a small
synthetic CSV (built with ``paths2d.build_flat_route``); it must produce no
violations.  The illegal samples (too-small radius, insufficient same-plane
clearance, moved endpoint) must be detected.
"""
from __future__ import annotations

import copy

import pytest

from four_side_1024.manual_u640 import paths2d as P
from four_side_1024.manual_u640 import verify

from _route_helpers import (build_u_route, build_u_primitives, make_input,
                            stack_object)

#: outer U ports: N01 column 1 (x = 5.625) -> N08 column 1 (x = 68.625)
OUTER_PORTS = dict(source=('N01', 1), target=('N08', 1))
#: inner U ports nested inside the outer one: separation 36 mm >= 2R
INNER_PORTS = dict(source=('N02', 1), target=('N06', 1))


def _single_u_input(tmp_path):
    data = make_input(tmp_path, [OUTER_PORTS])
    return data, stack_object()


def test_legal_sample_has_no_violations(tmp_path):
    data, stack = _single_u_input(tmp_path)
    record = data.records[0]
    route = build_u_route(record)
    result = verify.verify_all([route], data, stack, log=lambda message: None)

    assert result['violations'] == []
    checks = result['checks']
    for name in ('record_count_640', ):
        assert name in checks
    for name in ('record_conservation', 'port_occupancy', 'port_occupancy_z1',
                 'manual_layer_assignment', 'manual_all_routed',
                 'single_route_geometry', 'single_route_checks',
                 'arc_min_radius', 'arc_radius_exactly_15',
                 'same_plane_conflicts_d56_strict',
                 'same_plane_conflicts_independent', 'same_plane_crosscheck',
                 'cross_plane_flat_vertical_separation',
                 'cross_plane_3d_clearance', 'self_clearance',
                 'u_nesting_depth_order', 'u_nesting_depth_gap',
                 'u_depth_within_board', 'u_bulge_hosts_transition',
                 'failure_authenticity'):
        assert checks[name]['passed'], (name, checks[name])
    assert result['summary']['routed'] == 1
    assert result['summary']['failed'] == 0
    assert result['summary']['min_radius_mm'] == 15.0
    assert result['min_radius_mm'] == 15.0
    assert result['min_cross_angle_deg'] is None      # no crossings at all
    assert result['crossings']['total'] == 0
    # the independent U-depth audit recovers the analytic depth R + 0 = 15 mm
    assert len(result['u_depth_table']) == 1
    entry = result['u_depth_table'][0]
    assert entry['uid'] == record['uid']
    assert abs(entry['depth_mm'] - 15.0) <= 1e-6
    assert entry['nesting_level'] == 0
    assert result['failed_routes'] == []


def test_small_radius_is_detected(tmp_path):
    data, stack = _single_u_input(tmp_path)
    record = data.records[0]
    # same ports, but a 10 mm bend radius (illegal: must be >= 15)
    primitives = build_u_primitives(record, radius=10.0)
    route = P.build_flat_route(record, primitives)
    result = verify.verify_all([route], data, stack, log=lambda message: None)
    kinds = {item['kind'] for item in result['violations']}
    assert 'arc_radius_below_min' in kinds
    assert result['checks']['arc_min_radius']['passed'] is False
    assert result['checks']['single_route_checks']['passed'] is False
    assert result['min_radius_mm'] == pytest.approx(10.0)


def test_insufficient_same_plane_clearance_is_detected(tmp_path):
    """Two nested U's whose deep runs are only 0.05 mm apart (< 0.08)."""
    data = make_input(tmp_path, [OUTER_PORTS, INNER_PORTS])
    stack = stack_object()
    outer = build_u_route(data.record('z1:1'), depth_offset=0.0)
    inner = build_u_route(data.record('z1:2'), depth_offset=0.05)
    result = verify.verify_all([outer, inner], data, stack,
                               log=lambda message: None)
    kinds = {item['kind'] for item in result['violations']}
    same_plane_kinds = {kind for kind in kinds if kind.startswith('same_plane_')}
    assert same_plane_kinds, kinds
    assert 'same_plane_spacing' in same_plane_kinds
    assert result['checks']['same_plane_conflicts_independent']['passed'] is False
    # the nested U's must also violate the U-depth ladder audit: the wider U
    # is not deeper than the nested one
    assert ('u_nesting_depth_order' in kinds
            or 'u_nesting_depth_gap_too_small' in kinds)
    # per-plane statistics must show the conflict too
    plane = result['per_plane']['0.0']
    assert plane['conflicts'] >= 1
    assert plane['min_clearance_mm'] is not None
    assert plane['min_clearance_mm'] < 0.08
    # ...and the U table records the conflicting pair
    table = {entry['uid']: entry for entry in result['u_depth_table']}
    assert table['z1:1']['conflicts_with_u'] == ['z1:2']
    assert table['z1:2']['conflicts_with_u'] == ['z1:1']


def test_moved_endpoint_is_detected(tmp_path):
    data, stack = _single_u_input(tmp_path)
    record = data.records[0]
    legal = build_u_route(record)
    route = copy.deepcopy(legal)

    def shift(point):
        return [float(point[0]) + 0.01, float(point[1])]

    for prim in route['primitives_2d']:
        for key in ('p0', 'p1', 'center'):
            if key in prim:
                prim[key] = shift(prim[key])
    for part in route['parts']:
        if part.get('kind') != 'flat':
            continue
        for prim in part['primitives']:
            for key in ('p0', 'p1', 'center'):
                if key in prim:
                    prim[key] = shift(prim[key])
    result = verify.verify_all([route], data, stack, log=lambda message: None)
    kinds = {item['kind'] for item in result['violations']}
    assert 'route_endpoint_mismatch' in kinds
    assert result['checks']['single_route_checks']['passed'] is False


def test_verify_detects_record_conservation_and_failure_reason(tmp_path):
    data, stack = _single_u_input(tmp_path)
    record = data.records[0]
    route = build_u_route(record)
    # drop the route -> missing record violation
    result = verify.verify_all([], data, stack, log=lambda message: None)
    kinds = {item['kind'] for item in result['violations']}
    assert 'record_identity_mismatch' in kinds
    assert result['checks']['record_conservation']['passed'] is False
    # a failed record without a reason is not accepted
    failed = P.failed_record(record, 'x', logical_layer=1)
    failed['failure_reason'] = None
    result = verify.verify_all([route, failed], data, stack,
                               log=lambda message: None)
    kinds = {item['kind'] for item in result['violations']}
    assert 'failed_route_without_reason' in kinds
    assert result['checks']['failure_authenticity']['passed'] is False


def test_cross_plane_3d_violation_is_detected(tmp_path):
    """A lifted route's elevation S-curve must keep 3D clearance to other flats.

    Route A is a legal lifted U-turn on L2; its descent transition ends at the
    L1 height.  A second (flat L1) route is moved so its centre-line passes
    exactly through that transition end point: the true 3D centre-line distance
    becomes 0 and must be reported (the 2D same-plane audit alone cannot see
    this, because the two *flats* are not the conflicting geometry).
    """
    data = make_input(tmp_path, [
        dict(source=('N01', 1), target=('N08', 1), assigned_layer='L2',
             relation='same'),
        dict(source=('S01', 1), target=('S08', 1), side='S',
             assigned_layer='L1', relation='same'),
    ])
    stack = stack_object()
    lifted = P.build_lifted_route(data.record('z1:1'),
                                  build_u_primitives(data.record('z1:1')),
                                  2)
    assert lifted is not None
    transition = [part for part in lifted['parts']
                  if part.get('kind') == 'transition'][-1]
    target = transition['end']
    flat = build_u_route(data.record('z1:2'))

    # translate the flat route so that its first primitive passes through the
    # transition end point (the transport itself is not important here)
    first = flat['parts'][0]['primitives'][0]
    delta = (float(target[0]) - float(first['p0'][0]),
             float(target[1]) - float(first['p0'][1]))

    def translate(route):
        for prim in route.get('primitives_2d') or []:
            for key in ('p0', 'p1', 'center'):
                if key in prim:
                    prim[key] = [prim[key][0] + delta[0], prim[key][1] + delta[1]]
        for part in route.get('parts') or []:
            if part.get('kind') != 'flat':
                continue
            for prim in part.get('primitives') or []:
                for key in ('p0', 'p1', 'center'):
                    if key in prim:
                        prim[key] = [prim[key][0] + delta[0],
                                     prim[key][1] + delta[1]]

    translate(flat)
    result = verify.verify_all([lifted, flat], data, stack,
                               log=lambda message: None)
    kinds = {item['kind'] for item in result['violations']}
    assert 'transition_vs_flat_3d' in kinds, kinds
    assert result['checks']['cross_plane_3d_clearance']['passed'] is False
    # the transition endpoint itself is at z = 0: the reported distance is ~0
    item = next(item for item in result['violations']
                if item['kind'] == 'transition_vs_flat_3d')
    assert item['distance_mm'] < 1e-3


def test_verify_cli_load_routes_file(tmp_path):
    data, stack = _single_u_input(tmp_path)
    record = data.records[0]
    route = build_u_route(record)
    import json
    path = tmp_path / 'routes.json'
    path.write_text(json.dumps({'routes': [route]}), encoding='utf-8')
    routes, payload = verify.load_routes_file(path)
    assert len(routes) == 1
    assert payload['routes'][0]['uid'] == record['uid']
    plain = tmp_path / 'plain.json'
    plain.write_text(json.dumps([route]), encoding='utf-8')
    routes, payload = verify.load_routes_file(plain)
    assert len(routes) == 1 and payload is None


def test_verify_result_is_json_ready(tmp_path):
    import json
    data, stack = _single_u_input(tmp_path)
    route = build_u_route(data.records[0])
    result = verify.verify_all([route], data, stack, log=lambda message: None)
    text = json.dumps(result, allow_nan=False)
    assert '"violations"' in text
    for key in ('summary', 'checks', 'violations', 'per_plane', 'per_layer',
                'min_clearance_mm', 'min_radius_mm', 'min_cross_angle_deg',
                'u_depth_table', 'crossings', 'failed_routes'):
        assert key in result
