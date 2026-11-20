# -*- coding: utf-8 -*-
"""Input-model tests for the 640-record manual grouping CSV.

These tests read the real input CSV (never an ``outputs/`` artefact) and check
that the identity model behind the verification is the authoritative one.
"""
from __future__ import annotations

import math

import pytest

from four_side_1024.manual_u640 import config as C
from four_side_1024.manual_u640 import inputs as I


@pytest.fixture(scope='session')
def data():
    return I.load_inputs()


def test_record_count_and_datasets(data):
    assert len(data) == 640
    assert len(data.records) == 640
    datasets = {}
    for record in data.records:
        datasets[record['dataset']] = datasets.get(record['dataset'], 0) + 1
    assert datasets == {'z1': 512, 'z2': 128}
    assert len({record['uid'] for record in data.records}) == 640
    assert len(data.by_uid) == 640


def test_manual_groups(data):
    expected = {1: 64, 2: 64, 3: 64, 4: 64, 5: 13, 6: 15}
    counts = {int(layer): len(uids)
              for layer, uids in data.manual_groups.items()}
    assert counts == expected
    assert sum(counts.values()) == 284
    names = {1: 'NS-1', 2: 'NS-2', 3: 'EW-1', 4: 'EW-2',
             5: 'Z2-N-1', 6: 'Z2-N-2'}
    for layer, group_name in names.items():
        uids = data.manual_groups[layer]
        groups = {data.record(uid)['manual_group'] for uid in uids}
        assert groups == {group_name}
        assert all(data.record(uid)['assignment'] == 'manual_fixed_u'
                   for uid in uids)
        assert all(data.record(uid)['relation'] == 'same' for uid in uids)


def test_auto_groups(data):
    groups = {key: len(uids) for key, uids in data.auto_groups.items()}
    assert groups == {'z1_opposite_NS': 128, 'z1_opposite_EW': 128,
                      'z2_adjacent': 100}
    assert sum(groups.values()) == 356
    assert all(data.record(uid)['assignment'] == 'existing_algorithm'
               for uids in data.auto_groups.values() for uid in uids)


def test_z2_physical_row_and_height(data):
    for record in data.records:
        if record['dataset'] == 'z1':
            assert record['source_row'] == 1
            assert record['target_row'] == 1
            assert record['source_z_mm'] == 0.0
            assert record['target_z_mm'] == 0.0
        else:
            # the CSV identity strings still say row 1 / "z1"; physically the
            # records live on interface row 2 at z = 0.5 mm.
            assert record['csv_source_row'] == 1
            assert record['source_row'] == 2
            assert record['target_row'] == 2
            assert record['source_z_mm'] == 0.5
            assert record['target_z_mm'] == 0.5
            assert record['source_endpoint']['row'] == 2
            assert record['source_endpoint']['z_mm'] == 0.5


def test_ports_used_exactly_once_per_dataset(data):
    for dataset, expected in (('z1', 1024), ('z2', 256)):
        ports = []
        for record in data.records:
            if record['dataset'] != dataset:
                continue
            ports.extend([record['source_endpoint_id'],
                          record['target_endpoint_id']])
        assert len(ports) == expected
        assert len(set(ports)) == expected
    # the z2 records use the same 2x16 columns as z1 but on physical row 2:
    # the physical endpoint identities differ, the XY positions coincide.
    z1_xy = {(round(record['source_xy'][0], 9), round(record['source_xy'][1], 9))
             for record in data.records if record['dataset'] == 'z1'}
    z1_xy |= {(round(record['target_xy'][0], 9), round(record['target_xy'][1], 9))
              for record in data.records if record['dataset'] == 'z1'}
    z2_xy = {(round(record['source_xy'][0], 9), round(record['source_xy'][1], 9))
             for record in data.records if record['dataset'] == 'z2'}
    z2_xy |= {(round(record['target_xy'][0], 9), round(record['target_xy'][1], 9))
              for record in data.records if record['dataset'] == 'z2'}
    assert len(z1_xy) == 1024
    assert len(z2_xy) == 256
    assert len(z2_xy & z1_xy) == 256


def test_cross_dataset_same_port_pairs_retained(data):
    flagged = [record for record in data.records
               if record['cross_dataset_same_port_pair'] == 'YES']
    assert len(flagged) == 24
    assert {record['dataset'] for record in flagged} == {'z1', 'z2'}
    # every flagged z1 record has a mirrored z2 record with the same two
    # physical columns; the two records stay separate (no de-duplication)
    by_columns = {}
    for record in flagged:
        key = tuple(sorted([record['source_port_id'].replace(':1:', ':'),
                            record['target_port_id'].replace(':1:', ':')]))
        by_columns.setdefault(key, []).append(record)
    assert len(by_columns) == 12
    for key, records in by_columns.items():
        assert sorted(record['dataset'] for record in records) == ['z1', 'z2']
        assert len({record['uid'] for record in records}) == 2
        heights = {record['dataset']: record['source_z_mm'] for record in records}
        assert heights == {'z1': 0.0, 'z2': 0.5}
        # the two records connect the same two ports in opposite directions
        z1_record = next(item for item in records if item['dataset'] == 'z1')
        z2_record = next(item for item in records if item['dataset'] == 'z2')
        assert z1_record['source_port_id'] == z2_record['target_port_id']
        assert z1_record['target_port_id'] == z2_record['source_port_id']
        assert z1_record['source_channel'] == z2_record['target_channel']
        assert z1_record['target_channel'] == z2_record['source_channel']


def test_endpoint_coordinates_match_port_model(data):
    for record in data.records:
        for which in ('source', 'target'):
            endpoint = record[f'{which}_endpoint']
            expected = I.endpoint_xy(endpoint['connector'], endpoint['column'])
            assert abs(endpoint['xy'][0] - expected[0]) <= 1e-6
            assert abs(endpoint['xy'][1] - expected[1]) <= 1e-6
            assert abs(record[f'{which}_xy'][0] - expected[0]) <= 1e-6
            assert abs(record[f'{which}_xy'][1] - expected[1]) <= 1e-6


def test_relations_match_sides(data):
    for record in data.records:
        sides = {record['source_side'], record['target_side']}
        if record['relation'] == 'same':
            assert record['source_side'] == record['target_side']
        elif record['relation'] == 'opposite':
            assert sides in ({'N', 'S'}, {'E', 'W'})
        elif record['relation'] == 'adjacent':
            assert len(sides) == 2
            assert sides not in ({'N', 'S'}, {'E', 'W'})
        else:  # pragma: no cover - CSV never contains another relation
            pytest.fail(f'unexpected relation {record["relation"]}')


def test_input_validation_passes(data):
    assert data.validation['passed'] is True
    assert data.validation['failed_checks'] == []
    assert data.validation['total_records'] == 640
    assert data.validation['manual_total'] == 284
    assert data.validation['auto_total'] == 356
    # route_id / uid identity is dataset-local and never re-paired
    for uid, record in data.by_uid.items():
        assert uid == f'{record["dataset"]}:{record["original_route_id"]}'
        assert record['internal_id'] == I.internal_int_id(uid)


def test_manual_separations_support_2r(data):
    """Every manual fixed U has a same-side port separation of at least 2R."""
    for layer, uids in data.manual_groups.items():
        for uid in uids:
            record = data.record(uid)
            separation = math.hypot(
                record['target_xy'][0] - record['source_xy'][0],
                record['target_xy'][1] - record['source_xy'][1])
            assert separation >= 2.0 * C.RADIUS_MM - 1e-9


def test_stack_heights():
    from four_side_1024.manual_u640 import stack as ST
    stack = ST.LayerStack()
    assert stack.z_for_layer(1, 'z1') == 0.0
    assert stack.z_for_layer(1, 'z2') == 0.5
    assert stack.z_for_layer(2) == 0.65
    assert stack.z_for_layer(3) == 0.8
    for layer_id in range(2, stack.max_layer):
        assert abs((stack.z_for_layer(layer_id + 1)
                    - stack.z_for_layer(layer_id)) - C.LAYER_PITCH_MM) <= 1e-12
    for layer_id in range(2, stack.max_layer):
        assert stack.z_for_layer(layer_id + 1) - stack.z_for_layer(layer_id) \
            >= C.CLEARANCE_MM
