# -*- coding: utf-8 -*-
"""Small-sample test of the delivered export module.

The export is called on one synthetic route in ``tmp_path`` (never on
``outputs/``) and the written artefacts are inspected: the required files must
exist, ``route_table.csv`` must carry the task's column set, and the JSON
payloads must be self-consistent.
"""
from __future__ import annotations

import csv
import json

import pytest

export = pytest.importorskip('four_side_1024.manual_u640.export')

from four_side_1024.manual_u640 import stack as ST  # noqa: E402

from _route_helpers import build_u_route, make_input  # noqa: E402

REQUIRED_ROUTE_TABLE_COLUMNS = [
    'uid', 'original_route_id', 'dataset', 'relation',
    'source_port_id', 'target_port_id',
    'source_x_mm', 'source_y_mm', 'target_x_mm', 'target_y_mm',
    'assignment', 'manual_group',
    'assigned_logical_layer', 'target_layer', 'layer_z_mm',
    'layer_sequence', 'n_transitions',
    'path_length_mm', 'min_bend_radius_mm', 'bend_count',
    'min_clearance_mm', 'crossing_count',
    'propagation_loss_db', 'bend_loss_db', 'crossing_loss_db', 'loss_status',
    'status', 'failure_reason',
]


@pytest.fixture()
def small_case(tmp_path):
    data = make_input(tmp_path, [dict(source=('N01', 1), target=('N08', 1))])
    stack = ST.LayerStack()
    route = build_u_route(data.records[0])
    return data, stack, [route]


def test_export_writes_expected_files(tmp_path, small_case):
    data, stack, routes = small_case
    out_dir = tmp_path / 'export'
    result = export.export_all(routes, data, stack, out_dir,
                               log=lambda message: None)
    assert isinstance(result, dict)
    for name in ('routes.json', 'route_table.csv', 'per_layer.csv',
                 'statistics.json'):
        path = out_dir / name
        assert path.exists(), f'{name} was not written'
        assert path.stat().st_size > 0

    # route table columns
    with (out_dir / 'route_table.csv').open(encoding='utf-8-sig',
                                            newline='') as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        rows = list(reader)
    for column in REQUIRED_ROUTE_TABLE_COLUMNS:
        assert column in header, f'missing route_table.csv column {column}'
    assert len(rows) == len(routes)
    row = rows[0]
    assert row['uid'] == routes[0]['uid']
    assert row['status'] == 'routed'
    assert abs(float(row['min_bend_radius_mm']) - 15.0) <= 1e-6

    # per-layer csv columns
    with (out_dir / 'per_layer.csv').open(encoding='utf-8-sig',
                                          newline='') as handle:
        reader = csv.DictReader(handle)
        per_layer_header = reader.fieldnames or []
        per_layer_rows = list(reader)
    for column in ('logical_layer', 'layer_label', 'routes', 'routed',
                   'failed', 'conflicts', 'total_length_mm'):
        assert column in per_layer_header
    assert per_layer_rows

    # routes.json holds the same routed records
    payload = json.loads((out_dir / 'routes.json').read_text(encoding='utf-8'))
    if isinstance(payload, dict):
        stored = payload.get('routes') or []
    else:
        stored = payload
    assert len(stored) >= len(routes)

    # statistics.json is JSON with the expected top level info
    statistics = json.loads((out_dir / 'statistics.json').read_text(
        encoding='utf-8'))

    def has_key(value, key):
        if isinstance(value, dict):
            if key in value:
                return True
            return any(has_key(item, key) for item in value.values())
        if isinstance(value, list):
            return any(has_key(item, key) for item in value)
        return False

    for key in ('total_records', 'routed', 'failed', 'schema'):
        assert has_key(statistics, key), f'missing statistics key {key}'


def test_export_accepts_verification_metrics(tmp_path, small_case):
    data, stack, routes = small_case
    uid = routes[0]['uid']
    verification = {
        'schema': 'sample_verification',
        'summary': dict(passed=True, violations=0),
        'violations': [],
        'per_plane': {},
        'per_layer': {},
        'min_clearance_mm': 0.0812,
        'min_radius_mm': 15.0,
        'route_metrics': {uid: dict(min_clearance_mm=0.0812,
                                    crossing_count=2)},
        'crossings': dict(total=2, per_route={uid: 2}),
        'u_depth_table': [],
        'failed_routes': [],
    }
    out_dir = tmp_path / 'export_verification'
    export.export_all(routes, data, stack, out_dir,
                      verification=verification, failures=[],
                      log=lambda message: None)
    with (out_dir / 'route_table.csv').open(encoding='utf-8-sig',
                                            newline='') as handle:
        row = next(csv.DictReader(handle))
    # the verification numbers must be merged into the table, not left pending
    assert abs(float(row['min_clearance_mm']) - 0.0812) <= 1e-9
    assert int(float(row['crossing_count'])) == 2
