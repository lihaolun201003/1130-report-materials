# -*- coding: utf-8 -*-
"""Small-scale tests of the delivered manual fixed-U modules (L1 and one lifted
layer / one side group only).  They skip cleanly while ``u_geometry`` /
``u_routes`` are not available yet (parallel work), and never run the full 284
record build.
"""
from __future__ import annotations

import math

import pytest

u_geometry = pytest.importorskip('four_side_1024.manual_u640.u_geometry')
u_routes = pytest.importorskip('four_side_1024.manual_u640.u_routes')

from four_side_1024.d56.index import D56Index, prepare  # noqa: E402
from four_side_1024.manual_u640 import config as C  # noqa: E402
from four_side_1024.manual_u640 import inputs as I  # noqa: E402
from four_side_1024.manual_u640 import paths2d as P  # noqa: E402
from four_side_1024.manual_u640 import stack as ST  # noqa: E402

R = float(C.RADIUS_MM)
LOG = lambda message: None  # noqa: E731


@pytest.fixture(scope='session')
def data():
    return I.load_inputs()


@pytest.fixture(scope='session')
def stack():
    return ST.LayerStack()


def _first_side_group(data, layer):
    sides = data.manual_sides(layer)
    assert sides, f'no records for logical layer L{layer}'
    side = sorted(sides)[0]
    return side, data.records_for(sides[side])


def _assert_group_geometry(result, radius=R):
    assert result['failures'] == []
    assert result['routes']
    primitives_by_uid = {}
    for entry in result['routes']:
        primitives = entry['primitives']
        assert primitives, entry['uid']
        arcs = [prim for prim in primitives if prim.get('kind') == 'arc']
        assert arcs, f'{entry["uid"]}: a same-side U-turn needs arcs'
        for arc in arcs:
            assert abs(float(arc['radius']) - radius) <= 1e-9
        ok, errors = P.validate_2d_chain(primitives, entry['record'],
                                         radius=radius)
        assert ok, (entry['uid'], errors)
        primitives_by_uid[entry['uid']] = primitives
    # strict D56 audit of the whole side group: zero violations
    index = D56Index(width=C.WIDTH_MM, gap=C.EDGE_GAP_MM,
                     sagitta=C.SAGITTA_MM,
                     min_cross_angle_deg=C.MIN_CROSS_ANGLE_DEG,
                     crossing_policy='strict')
    prepared = {}
    internal_ids = {}
    for offset, (uid, primitives) in enumerate(primitives_by_uid.items()):
        route_id = 900000 + offset          # D56Index needs integer route ids
        internal_ids[route_id] = uid
        prepared[route_id] = prepare(primitives)
        index.add(route_id, prepared[route_id])
    for route_id, uid in internal_ids.items():
        evaluation = index.evaluate(prepared[route_id], exclude={route_id})
        assert evaluation is not None
        assert evaluation.valid, (uid, evaluation.reason, evaluation.blockers)


def test_layer1_side_group_geometry(data, stack):
    side, records = _first_side_group(data, 1)
    result = u_geometry.build_layer_u_layer(1, side, records, stack, log=LOG)
    _assert_group_geometry(result)
    assert len(result['routes']) == len(records)
    minimum_bulge = u_geometry.min_base_bulge(1, records[0]['dataset'], stack)
    assert minimum_bulge == 0.0
    by_uid = {entry['uid']: entry for entry in result['routes']}
    for entry in result['routes']:
        # L1 is the flat interface layer: no elevation transition is required,
        # but the U depth still has to reach R (the quarter arcs) and equal
        # bulge + R exactly.
        assert entry['depth_mm'] >= R - 1e-9
        assert entry['depth_mm'] == pytest.approx(entry['bulge_mm'] + R,
                                                  abs=1e-9)
        assert entry['valid'] is True
        parent_uid = entry['parent_uid']
        if parent_uid is not None:
            parent = by_uid[parent_uid]
            # the enclosing (wider) U must run deeper than the nested one
            assert parent['depth_mm'] > entry['depth_mm'] + 1e-9
    assert result['d56']['valid'] is True
    assert result['d56']['conflict_count'] == 0


def test_lifted_layer_side_group_depth_and_nesting(data, stack):
    sides = data.manual_sides(2)
    assert sides
    layer = 2
    # use the side group with the fewest records to keep the test fast
    side = min(sides, key=lambda name: len(sides[name]))
    records = data.records_for(sides[side])
    result = u_geometry.build_layer_u_layer(layer, side, records, stack, log=LOG)
    _assert_group_geometry(result)
    plane = records[0]['dataset']
    minimum_bulge = u_geometry.min_base_bulge(layer, plane, stack)
    by_uid = {entry['uid']: entry for entry in result['routes']}
    assert len(by_uid) == len(records)
    for entry in result['routes']:
        # depth = bulge + R; the bulge must host the two transition footprints
        assert entry['bulge_mm'] >= minimum_bulge - 1e-9
        assert entry['depth_mm'] == pytest.approx(entry['bulge_mm'] + R,
                                                  abs=1e-9)
        parent_uid = entry['parent_uid']
        if parent_uid is not None:
            parent = by_uid[parent_uid]
            # the wider (enclosing) U must run deeper than the nested one
            assert parent['depth_mm'] > entry['depth_mm'] + 1e-9
            assert parent['depth_mm'] - entry['depth_mm'] >= C.CLEARANCE_MM - 1e-9
    assert result['d56']['valid'] is True


def test_manual_routes_builder_available(data, stack):
    """The full builder exists and is callable; it is not run over 284 records
    here (that integration run is done by the Lead through ``run.py``)."""
    assert callable(u_routes.build_manual_u_routes)
