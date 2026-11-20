# -*- coding: utf-8 -*-
"""Synthetic consistency tests for the independent Native-3D validator.

Run standalone::

    python -m four_side_1024.fanout1024.native3d.tests_native3d.synthetic_native3d

or through ``validate_native3d.validate_run`` (the suite is embedded in
``validation.json`` under ``synthetic_consistency``).

The suite builds routes **in memory only** and asserts the independent
validator's acceptance/rejection behaviour:

(a) a complete Native-3D route (interface leads + fanout R15 transitions + a
    mid-body L6 -> L7 -> L6 duck-out) is ACCEPTED by the structure, metadata,
    R15, glass and true-3D world checks;
(b) a 0.049 mm cross-plane z offset is REJECTED (and 0.05 mm is legal);
(c) an R=14 mm transition is REJECTED;
(d) a 1e-3 mm position discontinuity at a junction is REJECTED;
(e) a flat that overlaps another route on the same physical plane is REJECTED.
"""
from __future__ import annotations

import math

from ....fsd25d import path3d as P
from ....l3d.world import World
from .. import validate_native3d as V

R15 = float(V.R15_MM)
MODEL = V._build_model(V._model_planes())
PLANE_6_Z = MODEL['z_map'][6]      # -0.15
PLANE_7_Z = MODEL['z_map'][7]      # -0.10
INTERFACE_Z1 = MODEL['interface_z']['z1']
INTERFACE_Z2 = MODEL['interface_z']['z2']


# ===========================================================================
# in-memory builders (no Lead builder code is imported)
# ===========================================================================
def _line(p0, p1):
    return dict(kind='line', p0=[float(p0[0]), float(p0[1])],
                p1=[float(p1[0]), float(p1[1])])


def _model_plane_id(z_mm):
    plane_id = V._plane_of_z(MODEL, z_mm)
    if plane_id is None:
        raise ValueError('height %r is not one of the 21 routing heights' % z_mm)
    return int(plane_id)


def _flat_part(z_mm, primitives, layer_id=None, tag='body'):
    flat = dict(kind='flat',
                layer_id=int(layer_id) if layer_id is not None
                else _model_plane_id(z_mm),
                z_mm=float(z_mm), primitives=[dict(prim) for prim in primitives],
                tag=str(tag))
    flat['length_mm'] = float(P.path_length(flat['primitives']))
    return flat


def _spacing(z_from, z_to, radius=R15):
    """``(theta, footprint, length)`` of one R15 S-curve."""
    theta = P.transition_theta(float(z_to) - float(z_from), radius=radius)
    return (theta, float(2.0 * radius * math.sin(theta)),
            float(2.0 * radius * theta))


def build_duckout_route(z_from=None, z_to=None, radius=R15,
                        discontinuity_mm=0.0, route_id=900001):
    """Standalone flat/duck-out/flat route on one straight run (no leads)."""
    z_from = PLANE_6_Z if z_from is None else float(z_from)
    z_to = PLANE_7_Z if z_to is None else float(z_to)
    x_start, x_up, middle, x_down, x_end = 20.0, 30.0, 10.0, 40.0, 90.0
    up = P.make_transition([x_up, 50.0], [1.0, 0.0], z_from, z_to,
                           radius=radius)
    down = P.make_transition([x_down, 50.0], [1.0, 0.0], z_to, z_from,
                             radius=radius)
    if discontinuity_mm:
        up = dict(up)
        up['start'] = [up['start'][0] + float(discontinuity_mm), up['start'][1]]
    parts = [
        _flat_part(z_from, [_line((x_start, 50.0), (x_up, 50.0))]),
        up,
        _flat_part(z_to, [_line((up['end'][0], 50.0), (x_down, 50.0))]),
        down,
        _flat_part(z_from, [_line((down['end'][0], 50.0), (x_end, 50.0))]),
    ]
    return dict(route_id=int(route_id), plane='z1',
                source_endpoint='SYN:1:0', target_endpoint='SYN:1:1',
                n_transitions=2, parts=parts)


def build_complete_native_route(route_id=900101):
    """A complete port-to-port Native-3D route: leads + fanouts + duck-out.

    Starts at the real z1 port ``N01:1:1`` (routing_xy (5.625, 150.0), inward
    (0, -1)) and ends at the real z1 port ``S01:1:1`` (routing_xy (5.625, 0.0),
    inward (0, 1)); the body goes L6 -> L7 -> L6 through one mid-body duck-out.
    """
    source_xy = (5.625, 150.0)
    target_xy = (5.625, 0.0)
    direction = (0.0, -1.0)
    lead = 0.25
    lead_start = (source_xy[0], source_xy[1] - lead)
    fanout_in = P.make_transition(lead_start, direction, INTERFACE_Z1,
                                  PLANE_6_Z, radius=R15)
    body_a_start = (fanout_in['end'][0], fanout_in['end'][1])
    body_a_end_y = 120.0
    mid_up = P.make_transition([source_xy[0], body_a_end_y], direction,
                               PLANE_6_Z, PLANE_7_Z, radius=R15)
    body_b_end_y = 110.0
    mid_down = P.make_transition([source_xy[0], body_b_end_y], direction,
                                 PLANE_7_Z, PLANE_6_Z, radius=R15)
    body_c_end_y = 80.0
    fanout_out = P.make_transition([source_xy[0], body_c_end_y], direction,
                                   PLANE_6_Z, INTERFACE_Z1, radius=R15)
    lead_start_y = float(fanout_out['end'][1])
    parts = [
        _flat_part(INTERFACE_Z1,
                   [_line(source_xy, lead_start)], layer_id=1, tag='lead'),
        dict(fanout_in, tag='fanout'),
        _flat_part(PLANE_6_Z,
                   [_line(body_a_start, (source_xy[0], body_a_end_y))],
                   tag='body'),
        dict(mid_up, tag='mid'),
        _flat_part(PLANE_7_Z,
                   [_line(mid_up['end'], (source_xy[0], body_b_end_y))],
                   tag='body'),
        dict(mid_down, tag='mid'),
        _flat_part(PLANE_6_Z,
                   [_line(mid_down['end'], (source_xy[0], body_c_end_y))],
                   tag='body'),
        dict(fanout_out, tag='fanout'),
        _flat_part(INTERFACE_Z1,
                   [_line((source_xy[0], lead_start_y), target_xy)],
                   layer_id=1, tag='lead'),
    ]
    body_heights = [PLANE_6_Z, PLANE_7_Z, PLANE_6_Z]
    body_planes = [6, 7, 6]
    flat_lengths = [float(part['length_mm']) for part in parts
                    if part['kind'] == 'flat']
    transition_lengths = []
    transition_footprints = []
    for part in parts:
        if part['kind'] != 'transition':
            continue
        _theta, footprint, length = _spacing(part['z0'], part['z1'])
        transition_lengths.append(length)
        transition_footprints.append(footprint)
    length_mm = float(sum(flat_lengths) + sum(transition_lengths))
    xy_length_mm = float(sum(flat_lengths) + sum(transition_footprints))
    mid_transitions = [dict(part_index=3, from_z=PLANE_6_Z, to_z=PLANE_7_Z,
                            tag='mid'),
                       dict(part_index=5, from_z=PLANE_7_Z, to_z=PLANE_6_Z,
                            tag='mid')]
    return dict(
        route_id=int(route_id),
        plane='z1',
        source_endpoint='N01:1:1',
        target_endpoint='S01:1:1',
        source_row=1,
        target_row=1,
        target_layer=6,
        target_plane=6,
        target_plane_label='L6',
        target_z_mm=PLANE_6_Z,
        needs_transition=True,
        layer_sequence=[1, 6, 7, 6, 1],
        layer_z_sequence=[INTERFACE_Z1, PLANE_6_Z, PLANE_7_Z, PLANE_6_Z,
                          INTERFACE_Z1],
        n_transitions=4,
        n_mid_transitions=2,
        lifted=True,
        layers_used=[1, 6, 7],
        length_mm=round(length_mm, 9),
        xy_length_mm=round(xy_length_mm, 9),
        z_span_mm=round(max(body_heights) - min(body_heights), 9),
        start_z_mm=INTERFACE_Z1,
        end_z_mm=INTERFACE_Z1,
        native_3d=True,
        body_heights=body_heights,
        mid_transitions=mid_transitions,
        excursions=[dict(s_start_mm=30.0, s_end_mm=40.0,
                         from_z=PLANE_6_Z, to_z=PLANE_7_Z,
                         from_plane=6, to_plane=7,
                         up_part_index=3, down_part_index=5,
                         middle_part_index=4)],
        parts=parts,
    )


def build_two_excursion_route(route_id=900151):
    """A complete native route with TWO independent mid-body excursions.

    z1 port -> fanout -> L6 body -> duck-out L6/L7/L6 -> L6 body -> duck-out
    L6/L5/L6 -> L6 body -> fanout -> z1 port (13 parts, 4 mid transitions, 2
    excursions).  Exercises the multi-excursion native metadata bookkeeping.
    """
    source_xy = (5.625, 150.0)
    target_xy = (5.625, 0.0)
    direction = (0.0, -1.0)
    x = source_xy[0]
    z0 = PLANE_6_Z            # -0.15
    z_a = PLANE_7_Z           # -0.10
    z_b = MODEL['z_map'][5]   # -0.20
    lead_start = (x, source_xy[1] - 0.25)
    fanout_in = P.make_transition(lead_start, direction, INTERFACE_Z1, z0,
                                  radius=R15)
    up1 = P.make_transition([x, 130.0], direction, z0, z_a, radius=R15)
    down1 = P.make_transition([x, 120.0], direction, z_a, z0, radius=R15)
    up2 = P.make_transition([x, 105.0], direction, z0, z_b, radius=R15)
    down2 = P.make_transition([x, 90.0], direction, z_b, z0, radius=R15)
    fanout_out = P.make_transition([x, 80.0], direction, z0, INTERFACE_Z1,
                                   radius=R15)
    parts = [
        _flat_part(INTERFACE_Z1, [_line(source_xy, lead_start)], layer_id=1,
                   tag='lead'),
        dict(fanout_in, tag='fanout'),
        _flat_part(z0, [_line(fanout_in['end'], (x, 130.0))], tag='body'),
        dict(up1, tag='mid'),
        _flat_part(z_a, [_line(up1['end'], (x, 120.0))], tag='body'),
        dict(down1, tag='mid'),
        _flat_part(z0, [_line(down1['end'], (x, 105.0))], tag='body'),
        dict(up2, tag='mid'),
        _flat_part(z_b, [_line(up2['end'], (x, 90.0))], tag='body'),
        dict(down2, tag='mid'),
        _flat_part(z0, [_line(down2['end'], (x, 80.0))], tag='body'),
        dict(fanout_out, tag='fanout'),
        _flat_part(INTERFACE_Z1, [_line(fanout_out['end'], target_xy)],
                   layer_id=1, tag='lead'),
    ]
    body_heights = [z0, z_a, z0, z_b, z0]
    body_planes = [6, 7, 6, 5, 6]
    flat_lengths = [float(part['length_mm']) for part in parts
                    if part['kind'] == 'flat']
    transition_lengths = []
    transition_footprints = []
    for part in parts:
        if part['kind'] != 'transition':
            continue
        _theta, footprint, length = _spacing(part['z0'], part['z1'])
        transition_lengths.append(length)
        transition_footprints.append(footprint)
    length_mm = float(sum(flat_lengths) + sum(transition_lengths))
    xy_length_mm = float(sum(flat_lengths) + sum(transition_footprints))
    mid_transitions = [
        dict(part_index=3, from_z=z0, to_z=z_a, tag='mid'),
        dict(part_index=5, from_z=z_a, to_z=z0, tag='mid'),
        dict(part_index=7, from_z=z0, to_z=z_b, tag='mid'),
        dict(part_index=9, from_z=z_b, to_z=z0, tag='mid'),
    ]
    return dict(
        route_id=int(route_id),
        plane='z1',
        source_endpoint='N01:1:1',
        target_endpoint='S01:1:1',
        source_row=1,
        target_row=1,
        target_layer=6,
        target_plane=6,
        target_plane_label='L6',
        target_z_mm=z0,
        needs_transition=True,
        layer_sequence=[1] + body_planes + [1],
        layer_z_sequence=[INTERFACE_Z1] + body_heights + [INTERFACE_Z1],
        n_transitions=6,
        n_mid_transitions=4,
        lifted=True,
        layers_used=[1] + sorted(set(body_planes)),
        length_mm=round(length_mm, 9),
        xy_length_mm=round(xy_length_mm, 9),
        z_span_mm=round(max(body_heights) - min(body_heights), 9),
        start_z_mm=INTERFACE_Z1,
        end_z_mm=INTERFACE_Z1,
        native_3d=True,
        body_heights=body_heights,
        mid_transitions=mid_transitions,
        excursions=[dict(s_start_mm=40.0, s_end_mm=50.0,
                         from_z=z0, to_z=z_a, from_plane=6, to_plane=7,
                         up_part_index=3, down_part_index=5,
                         middle_part_index=4),
                    dict(s_start_mm=110.0, s_end_mm=120.0,
                         from_z=z0, to_z=z_b, from_plane=6, to_plane=5,
                         up_part_index=7, down_part_index=9,
                         middle_part_index=8)],
        parts=parts,
    )


_MODEL_STACK = None


def _model_stack():
    """The frozen 21-height layer stack (built from the model table)."""
    global _MODEL_STACK
    if _MODEL_STACK is None:
        from ....l3d.layers import build_stack
        heights = dict(V.V21.body_heights_of(V._model_planes()))
        _MODEL_STACK = build_stack('native3d_synthetic', heights=heights,
                                   note='synthetic consistency tests')
    return _MODEL_STACK


def _fresh_world(clearance=V.MIN_3D_CLEARANCE_MM):
    return World(_model_stack(), clearance=clearance)


# ===========================================================================
# individual tests
# ===========================================================================
def test_a_duckout_accepted():
    """(a) duck-out L6 -> L7 -> L6 on a straight flat is accepted."""
    route = build_duckout_route()
    structure_errors = World.check_structure(route)
    world_violations = _fresh_world().check_route(route, check_self=True)
    radius_violations = []
    V.V21.check_radius(route, radius_violations)
    junctions = V._junction_report(route, MODEL)
    max_position_gap = max((item.get('position_gap_mm') or 0.0)
                           for item in junctions)
    max_z_gap = max((item.get('z_gap_mm') or 0.0) for item in junctions)
    max_tangent_gap = max((item.get('tangent_gap') or 0.0) for item in junctions)
    passed = (not structure_errors and not world_violations
              and not radius_violations
              and max_position_gap <= V.TOL_POS_MM
              and max_z_gap <= V.TOL_Z_MM
              and max_tangent_gap <= V.TOL_TANGENT)
    return dict(
        name='duckout_L6_L7_L6_accepted', passed=bool(passed),
        detail=dict(structure_errors=structure_errors[:4],
                    world_violations=world_violations[:4],
                    radius_violations=radius_violations[:4],
                    max_position_gap_mm=max_position_gap,
                    max_z_gap_mm=max_z_gap,
                    max_tangent_gap=max_tangent_gap))


def test_b_49um_offset_rejected():
    """(b) a 0.049 mm cross-plane z offset is rejected; 0.05 mm is legal."""
    z_base = PLANE_6_Z
    base = World.flat_route(900201, 'z1',
                            [_line((20.0, 60.0), (90.0, 60.0))], z_base,
                            layer_id=6)
    world_bad = _fresh_world()
    world_bad.add_route(base)
    candidate_bad = World.flat_route(
        900202, 'z1', [_line((20.0, 60.0), (90.0, 60.0))],
        z_base + 0.049, layer_id=7)
    bad_violations = world_bad.check_route(candidate_bad, check_self=True)
    bad_kinds = sorted({str(item.get('kind')) for item in bad_violations})
    model_membership = V._plane_of_z(MODEL, z_base + 0.049) is None
    world_ok = _fresh_world()
    world_ok.add_route(base)
    candidate_ok = World.flat_route(
        900203, 'z1', [_line((20.0, 70.0), (90.0, 70.0))],
        z_base + 0.05, layer_id=7)
    ok_violations = world_ok.check_route(candidate_ok, check_self=True)
    passed = (bool(bad_violations)
              and 'flat_cross_plane_too_close' in bad_kinds
              and model_membership
              and not ok_violations)
    return dict(
        name='z_offset_49um_rejected', passed=bool(passed),
        detail=dict(rejection_kinds=bad_kinds,
                    rejection_violations=bad_violations[:3],
                    flat_z_not_model_height=bool(model_membership),
                    control_50um_violations=ok_violations[:3]))


def test_c_radius_14_rejected():
    """(c) an R=14 mm transition is rejected."""
    route = build_duckout_route(radius=14.0)
    radius_violations = []
    details = V.V21.check_radius(route, radius_violations)
    kinds = sorted({str(item.get('kind')) for item in radius_violations})
    passed = bool(radius_violations) \
        and 'transition_declared_radius_not_r15' in kinds \
        and 'transition_true_3d_radius_below_r15' in kinds
    return dict(
        name='radius_14_rejected', passed=bool(passed),
        detail=dict(violation_kinds=kinds,
                    violations=radius_violations[:4],
                    transition_count=details.get('transition_count'),
                    min_sampled_radius=details.get(
                        'transition_min_sampled_radius')))


def test_d_position_discontinuity_rejected():
    """(d) a 1e-3 mm position discontinuity is rejected."""
    route = build_duckout_route(discontinuity_mm=1e-3)
    world_structure = World.check_structure(route)
    junctions = V._junction_report(route, MODEL)
    max_gap = max((item.get('position_gap_mm') or 0.0) for item in junctions)
    passed = bool(world_structure) \
        and 'flat_transition_position_mismatch' in world_structure \
        and max_gap > V.TOL_POS_MM
    return dict(
        name='position_discontinuity_1e-3_rejected', passed=bool(passed),
        detail=dict(world_structure_errors=world_structure[:4],
                    max_position_gap_mm=max_gap,
                    tolerance_mm=V.TOL_POS_MM))


def test_e_flat_overlap_rejected():
    """(e) a flat that overlaps another route on the same plane is rejected."""
    z = PLANE_6_Z
    world = _fresh_world()
    world.add_route(World.flat_route(
        900301, 'z1', [_line((20.0, 80.0), (90.0, 80.0))], z, layer_id=6))
    overlap = World.flat_route(
        900302, 'z1', [_line((30.0, 80.0), (60.0, 80.0))], z, layer_id=6)
    violations = world.check_route(overlap, check_self=True)
    kinds = sorted({str(item.get('kind')) for item in violations})
    passed = bool(violations) and 'flat_same_plane_conflict' in kinds
    return dict(
        name='flat_overlap_rejected', passed=bool(passed),
        detail=dict(violation_kinds=kinds, violations=violations[:4]))


def test_f_complete_native_route_accepted():
    """(f) a complete port-to-port Native-3D route passes every re-derived check."""
    route = build_complete_native_route()
    endpoints = V.C.endpoints()
    structure_violations = []
    stats = dict(routes_checked=0, parts_total=0, flats_total=0,
                 transitions_total=0, junctions_checked=0,
                 max_position_gap_mm=0.0, max_z_gap_mm=0.0,
                 max_tangent_gap=0.0, world_structure_flagged=0,
                 tagged_parts=0, missing_tags=0, direct_routes=0,
                 non_direct_routes=0, native_routes=0)
    V._check_route_structure(route, MODEL, endpoints, structure_violations, stats)
    metadata_block = V.check_native_metadata([route], MODEL, {})
    radius_block = V.check_radius([route])
    world_violations = _fresh_world().check_route(route, check_self=True)
    details = dict(
        structure_violations=structure_violations[:6],
        metadata_violations=(metadata_block['violations'] or [])[:6],
        radius_violations=(radius_block['violations'] or [])[:6],
        world_violations=world_violations[:6],
        max_position_gap_mm=stats['max_position_gap_mm'],
        max_z_gap_mm=stats['max_z_gap_mm'],
        max_tangent_gap=stats['max_tangent_gap'],
        metadata_counts=dict(
            native_routes=metadata_block['details'].get('native_routes'),
            mid_transitions=metadata_block['details'].get('mid_transitions'),
            excursions=metadata_block['details'].get('excursions')),
    )
    passed = not structure_violations \
        and not metadata_block['violations'] \
        and not radius_block['violations'] \
        and not world_violations
    return dict(name='complete_native_route_accepted', passed=bool(passed),
                detail=details)


def test_g_two_excursions_accepted():
    """(g) a complete native route with two independent excursions is accepted."""
    route = build_two_excursion_route()
    endpoints = V.C.endpoints()
    structure_violations = []
    stats = dict(routes_checked=0, parts_total=0, flats_total=0,
                 transitions_total=0, junctions_checked=0,
                 max_position_gap_mm=0.0, max_z_gap_mm=0.0,
                 max_tangent_gap=0.0, world_structure_flagged=0,
                 tagged_parts=0, missing_tags=0, direct_routes=0,
                 non_direct_routes=0, native_routes=0)
    V._check_route_structure(route, MODEL, endpoints, structure_violations, stats)
    metadata_block = V.check_native_metadata([route], MODEL, {})
    radius_block = V.check_radius([route])
    world_violations = _fresh_world().check_route(route, check_self=True)
    recomputed = V.recompute_route(route, MODEL)
    details = dict(
        structure_violations=structure_violations[:6],
        metadata_violations=(metadata_block['violations'] or [])[:6],
        radius_violations=(radius_block['violations'] or [])[:6],
        world_violations=world_violations[:6],
        max_position_gap_mm=stats['max_position_gap_mm'],
        max_z_gap_mm=stats['max_z_gap_mm'],
        max_tangent_gap=stats['max_tangent_gap'],
        recomputed=dict(
            body_heights=recomputed['body_heights'],
            mid_part_indices=[entry['part_index']
                              for entry in recomputed['mid_entries']],
            excursion_indices=[(entry['up_part_index'],
                                entry['middle_part_index'],
                                entry['down_part_index'])
                               for entry in recomputed['excursions']],
            layer_sequence=recomputed['expected_layer_sequence']),
        metadata_counts=dict(
            native_routes=metadata_block['details'].get('native_routes'),
            mid_transitions=metadata_block['details'].get('mid_transitions'),
            excursions=metadata_block['details'].get('excursions'),
            max_body_flats_per_route=metadata_block['details'].get(
                'max_body_flats_per_route')),
    )
    passed = (not structure_violations
              and not metadata_block['violations']
              and not radius_block['violations']
              and not world_violations
              and len(recomputed['excursions']) == 2)
    return dict(name='two_excursions_accepted', passed=bool(passed),
                detail=details)


#: required suite (task acceptance), in stable order
TEST_FUNCTIONS = (
    test_a_duckout_accepted,
    test_b_49um_offset_rejected,
    test_c_radius_14_rejected,
    test_d_position_discontinuity_rejected,
    test_e_flat_overlap_rejected,
    test_f_complete_native_route_accepted,
    test_g_two_excursions_accepted,
)


# ===========================================================================
# suite runner
# ===========================================================================
def run_synthetic_tests(model=None, log=None):
    """Run the in-memory consistency suite; returns a JSON-able payload."""
    tests = []
    for function in TEST_FUNCTIONS:
        try:
            result = function()
        except Exception as error:  # noqa: BLE001 - a failing test is reported
            result = dict(name=function.__name__, passed=False,
                          detail='%s: %s' % (type(error).__name__, error))
        tests.append(dict(name=str(result.get('name') or function.__name__),
                          passed=bool(result.get('passed')),
                          detail=result.get('detail')))
        if log is not None:
            log('[synthetic] %-45s %s'
                % (tests[-1]['name'], 'PASS' if tests[-1]['passed'] else 'FAIL'))
    payload = dict(
        schema=V.CONSISTENCY_SCHEMA,
        validator=V.VALIDATOR_ID,
        generated_at=V._now(),
        r15_mm=R15,
        clearance_mm=V.MIN_3D_CLEARANCE_MM,
        layer_pitch_mm=V.MIN_LAYER_PITCH_MM,
        route_fixtures=dict(
            duckout='flat/transition(up)/flat/transition(down)/flat on a '
                    'straight run',
            complete='real z1 ports N01:1:1 -> S01:1:1 with 2 fanout + 2 mid '
                     'R15 transitions and one L6->L7->L6 duck-out',
            two_excursions='real z1 ports with 2 fanout + 4 mid R15 '
                           'transitions and two independent duck-outs '
                           '(L6/L7/L6 and L6/L5/L6)'),
        tests=tests,
        all_passed=all(test['passed'] for test in tests),
    )
    return payload


def test_synthetic_consistency_suite():
    """pytest entry point."""
    payload = run_synthetic_tests()
    failed = [test for test in payload['tests'] if not test['passed']]
    assert payload['all_passed'], 'synthetic tests failed: %r' % (
        [(test['name'], test['detail']) for test in failed],)


def main(argv=None):
    payload = run_synthetic_tests(log=print)
    print('')
    print('synthetic consistency: %s (%d/%d passed)'
          % ('PASS' if payload['all_passed'] else 'FAIL',
             sum(1 for test in payload['tests'] if test['passed']),
             len(payload['tests'])))
    return 0 if payload['all_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

