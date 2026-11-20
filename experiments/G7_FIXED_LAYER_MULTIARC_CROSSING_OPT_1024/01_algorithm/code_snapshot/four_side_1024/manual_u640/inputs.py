# -*- coding: utf-8 -*-
"""Input reader / identity model for the 640-record manual grouping CSV.

The CSV is the authoritative input of this round: 640 original records, each with
a data-source partition (``input_dataset`` = ``z1`` / ``z2``), an original
``route_id`` and the source/target connector-port identities and millimetre
coordinates.  Nothing here re-pairs, de-duplicates or re-orders the records.

What this module fixes
----------------------
* one **unique internal id** per record: ``uid = '<dataset>:<route_id>'`` (the
  CSV's own ``route_uid``) plus :func:`internal_int_id` for the collision worlds;
* the **physical port model** of every endpoint: the same 150 x 150 mm board and
  the same 2 x 16 IEC port table as ``four_side_1024.fslw.ports``, but the
  ``z2`` data source is on interface **row 2** (physical height 0.5 mm) even
  though the CSV's port strings / ``layer`` column say ``...:1:...`` / ``z1``.
  This is the "Z2 layer field still says z1" issue called out by the task;
* the **manual fixed-U layer groups** L1..L6 and the **automatic groups**
  (z1 opposite / z2 adjacent), exactly as encoded in the CSV;
* explicit checks for duplicate endpoints inside and across the two data
  sources.  Records are never merged: the 24 identical XY port pairs between
  ``z1`` and ``z2`` are physically distinct ports (0.0 mm vs 0.5 mm height) and
  are reported as such.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, OrderedDict
from pathlib import Path

from . import config as C

DATASETS = ('z1', 'z2')
MANUAL_LAYERS = {1: 'NS-1', 2: 'NS-2', 3: 'EW-1', 4: 'EW-2', 5: 'Z2-N-1',
                 6: 'Z2-N-2'}
#: Required manual-group counts of the task statement.
MANUAL_LAYER_COUNTS = {1: 64, 2: 64, 3: 64, 4: 64, 5: 13, 6: 15}
#: Required automatic-group counts of the task statement.
AUTO_GROUP_COUNTS = {'z1_opposite': 256, 'z2_adjacent': 100}
SIDE_INWARD = {'N': (0.0, -1.0), 'S': (0.0, 1.0), 'E': (-1.0, 0.0),
               'W': (1.0, 0.0)}
SIDES = 'NSEW'
TOL = 1e-9
COORD_TOL = 1e-6


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def sha256_file(path):
    raw = Path(path).read_bytes()
    return hashlib.sha256(raw).hexdigest(), raw


def internal_int_id(uid):
    """Collision-world integer id; unique across the two data sources."""
    dataset, _, route_id = str(uid).partition(':')
    base = 1 if dataset == 'z1' else 2
    return base * 100000 + int(route_id)


def print_xy(port_id):
    """``'N02:1:13'`` -> ``('N02', 13)``; the row digit is not trusted."""
    connector, _row, column = str(port_id).split(':')
    return connector, int(column)


def endpoint_xy(connector, column):
    """Board XY of one 2x16 IEC port column (existing fslw port model)."""
    from four_side_1024.fslw import ports as FSLW_PORTS
    index = int(str(connector)[1:])
    along = FSLW_PORTS.port_along_mm(index, int(column))
    from four_side_1024.inputs import board_xy
    return tuple(float(v) for v in board_xy(str(connector)[0], along))


def physical_row(dataset):
    """Physical interface row of one data source (1 -> z=0.0, 2 -> z=0.5)."""
    return 1 if dataset == 'z1' else 2


def physical_z(dataset):
    return float(C.PLANE_Z_MM[dataset])


# ---------------------------------------------------------------------------
# CSV records
# ---------------------------------------------------------------------------
def read_csv_rows(path=None):
    path = Path(C.INPUT_CSV if path is None else path)
    text = path.read_text(encoding='utf-8-sig')
    rows = list(csv.DictReader(text.splitlines()))
    return rows, sha256_file(path)[0]


def _record(row):
    """Convert one CSV row to the internal identity record (no geometry)."""
    dataset = str(row['input_dataset']).strip()
    route_id = int(row['route_id'])
    uid = str(row['route_uid']).strip() or f'{dataset}:{route_id}'
    if uid != f'{dataset}:{route_id}':
        raise ValueError(f'route_uid {uid!r} does not match {dataset}:{route_id}')
    source_connector, source_column = print_xy(row['source_port_id'])
    target_connector, target_column = print_xy(row['target_port_id'])
    record = dict(
        uid=uid,
        internal_id=internal_int_id(uid),
        dataset=dataset,
        plane=dataset,
        original_route_id=route_id,
        relation=str(row['relation']).strip(),
        source_side=str(row['source_side']).strip(),
        target_side=str(row['target_side']).strip(),
        source_connector=source_connector,
        target_connector=target_connector,
        source_column=source_column,
        target_column=target_column,
        source_channel=int(row['source_channel']),
        target_channel=int(row['target_channel']),
        source_port_id=str(row['source_port_id']).strip(),
        target_port_id=str(row['target_port_id']).strip(),
        source_xy=[float(row['source_x_mm']), float(row['source_y_mm'])],
        target_xy=[float(row['target_x_mm']), float(row['target_y_mm'])],
        csv_source_row=int(row['source_row']),
        csv_target_row=int(row['target_row']),
        source_row=physical_row(dataset),
        target_row=physical_row(dataset),
        source_z_mm=physical_z(dataset),
        target_z_mm=physical_z(dataset),
        csv_layer_tag=str(row.get('layer', '') or '').strip(),
        assignment=str(row['routing_method']).strip(),
        routing_status_csv=str(row['routing_status']).strip(),
        manual_group=(str(row.get('manual_group') or '').strip() or None),
        manual_group_order=(str(row.get('manual_group_order') or '').strip() or None),
        u_pair=(str(row.get('u_pair') or '').strip() or None),
        u_logical_layer=(str(row.get('u_logical_layer') or '').strip() or None),
        assigned_layer_csv=(str(row.get('assigned_layer') or '').strip() or None),
        cross_dataset_same_port_pair=str(
            row.get('cross_dataset_same_port_pair') or 'NO').strip(),
    )
    # manual layers arrive as 'L1'..'L6'
    layer_csv = record['assigned_layer_csv']
    record['assigned_layer'] = (int(layer_csv[1:]) if layer_csv
                                and layer_csv.upper().startswith('L') else None)
    return record


def _endpoint(record, which):
    """Physical port record of one route end."""
    port_id = record['source_port_id'] if which == 'source' else record['target_port_id']
    connector, column = print_xy(port_id)
    side = record['source_side'] if which == 'source' else record['target_side']
    xy = record['source_xy'] if which == 'source' else record['target_xy']
    row = physical_row(record['dataset'])
    return dict(
        endpoint_id=f"{connector}:{row}:{column}",
        csv_port_id=port_id,
        connector=connector,
        side=side,
        column=int(column),
        row=int(row),
        plane=record['dataset'],
        z_mm=float(C.PLANE_Z_MM[record['dataset']]),
        layer_id=C.INTERFACE_LAYER_ID,
        xy=[float(xy[0]), float(xy[1])],
        routing_xy=[float(xy[0]), float(xy[1])],
        inward=list(SIDE_INWARD[side]),
        physical_along_mm=float(_along(connector, column)),
    )


def _along(connector, column):
    from four_side_1024.fslw import ports as FSLW_PORTS
    return FSLW_PORTS.port_along_mm(int(str(connector)[1:]), int(column))


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------
def _check(checks, name, ok, detail=None):
    checks[name] = dict(passed=bool(ok), detail=detail)
    return bool(ok)


def _validate(records, checks):
    by_uid = {record['uid']: record for record in records}
    uids = [record['uid'] for record in records]
    _check(checks, 'record_count_640', len(records) == 640, len(records))
    _check(checks, 'uid_unique', len(set(uids)) == len(uids),
           len(uids) - len(set(uids)))
    per_dataset = Counter(record['dataset'] for record in records)
    _check(checks, 'dataset_counts', per_dataset == Counter({'z1': 512, 'z2': 128}),
           dict(per_dataset))
    for dataset in DATASETS:
        ids = [record['original_route_id'] for record in records
               if record['dataset'] == dataset]
        _check(checks, f'route_id_unique_{dataset}', len(set(ids)) == len(ids),
               len(ids) - len(set(ids)))
        ports = []
        for record in records:
            if record['dataset'] != dataset:
                continue
            ports.extend([record['source_endpoint_id'], record['target_endpoint_id']])
        _check(checks, f'port_used_once_{dataset}', len(set(ports)) == len(ports),
               len(ports) - len(set(ports)))
    # coordinate model of every endpoint (never move a port)
    bad = []
    for record in records:
        for which in ('source', 'target'):
            endpoint = record[f'{which}_endpoint']
            expected = endpoint_xy(endpoint['connector'], endpoint['column'])
            if (abs(endpoint['xy'][0] - expected[0]) > COORD_TOL
                    or abs(endpoint['xy'][1] - expected[1]) > COORD_TOL):
                bad.append(dict(uid=record['uid'], which=which,
                                csv=list(endpoint['xy']),
                                port_model=list(expected)))
    _check(checks, 'endpoint_coordinates_match_port_model', not bad, bad[:10])
    # CSV row digit vs physical row: z2 records carry row 1 in the CSV identity
    mismatched = [record['uid'] for record in records
                  if record['csv_source_row'] != record['source_row']
                  or record['csv_target_row'] != record['target_row']]
    checks['csv_row_vs_physical_row'] = dict(
        passed=True,
        detail=dict(
            note=('z2 records keep the CSV row-1 identity but are routed on '
                  'physical interface row 2 (0.5 mm); reported, never merged'),
            csv_mismatch_count=len(mismatched),
            examples=mismatched[:8]))
    # CSV layer column of every record (the task warns z2 may still say z1)
    layers = Counter(record['csv_layer_tag'] for record in records)
    checks['csv_layer_tag'] = dict(
        passed=True,
        detail=dict(values=dict(layers),
                    note=('the CSV layer column is not the physical routing layer; '
                          'input_dataset is authoritative')))
    # cross data-source port reuse: different physical planes, not a conflict
    z1_ports = set()
    z2_ports = set()
    for record in records:
        target = z1_ports if record['dataset'] == 'z1' else z2_ports
        target.add(record['source_endpoint_id'])
        target.add(record['target_endpoint_id'])
    shared = sorted(z1_ports & z2_ports)
    same_pair = [record['uid'] for record in records
                 if record['cross_dataset_same_port_pair'] == 'YES']
    _check(checks, 'cross_dataset_port_reuse_audited', True,
           dict(z1_ports=len(z1_ports), z2_ports=len(z2_ports),
                shared_xy_columns=len(shared), shared_examples=shared[:12],
                identical_port_pairs_rows=len(same_pair), rows=same_pair,
                note=('a z1 and a z2 connection may share the same 2x16 column '
                      'because they are on interface row 1 (z=0.0) and row 2 '
                      '(z=0.5); the records are kept separate')))
    # relations / sides consistency
    bad = []
    for record in records:
        sides = {record['source_side'], record['target_side']}
        relation = record['relation']
        if relation == 'same':
            ok = record['source_side'] == record['target_side']
        elif relation == 'opposite':
            ok = sides in ({'N', 'S'}, {'E', 'W'})
        elif relation == 'adjacent':
            ok = len(sides) == 2 and sides not in ({'N', 'S'}, {'E', 'W'})
        else:
            ok = False
        if not ok:
            bad.append(record['uid'])
    _check(checks, 'relation_matches_sides', not bad, bad[:10])
    return by_uid


def _attach_endpoints(records):
    """Attach the physical port records (interface row 1 or 2) to every route."""
    for record in records:
        record['source_endpoint'] = _endpoint(record, 'source')
        record['target_endpoint'] = _endpoint(record, 'target')
        record['source_endpoint_id'] = record['source_endpoint']['endpoint_id']
        record['target_endpoint_id'] = record['target_endpoint']['endpoint_id']
    return records


def _assemble(records, by_uid, checks):
    """Build the group tables and check their counts."""
    # -- manual fixed-U groups --------------------------------------------
    manual = {layer_id: [] for layer_id in C.MANUAL_LAYER_IDS}
    manual_meta = {}
    for record in records:
        if record['assignment'] != 'manual_fixed_u':
            continue
        layer_id = record['assigned_layer']
        if layer_id is None or layer_id not in manual:
            continue
        manual[layer_id].append(record['uid'])
        manual_meta.setdefault(layer_id, set()).add(record['manual_group'])
    manual_groups = OrderedDict()
    for layer_id in C.MANUAL_LAYER_IDS:
        uids = manual[layer_id]
        manual_groups[layer_id] = uids
        groups = sorted(manual_meta.get(layer_id, set()))
        _check(checks, f'manual_layer_L{layer_id}_count',
               len(uids) == MANUAL_LAYER_COUNTS[layer_id],
               dict(expected=MANUAL_LAYER_COUNTS[layer_id], actual=len(uids)))
        _check(checks, f'manual_layer_L{layer_id}_group_name',
               groups == [MANUAL_LAYERS[layer_id]], groups)
        sides = Counter(by_uid[uid]['source_side'] for uid in uids)
        _check(checks, f'manual_layer_L{layer_id}_same_side',
               all(by_uid[uid]['relation'] == 'same' for uid in uids),
               dict(sides=dict(sides)))
        # same-side separation must be at least 2R for a planar U-turn
        minimum = None
        for uid in uids:
            record = by_uid[uid]
            separation = _separation(record)
            minimum = separation if minimum is None else min(minimum, separation)
        _check(checks, f'manual_layer_L{layer_id}_separation_ge_2R',
               minimum is not None and minimum >= 2.0 * C.RADIUS_MM - 1e-9,
               dict(min_separation_mm=minimum, two_r_mm=2.0 * C.RADIUS_MM))
    manual_total = sum(len(uids) for uids in manual_groups.values())
    _check(checks, 'manual_total_284', manual_total == 284, manual_total)

    # -- automatic groups --------------------------------------------------
    auto_groups = OrderedDict()
    for record in records:
        if record['assignment'] != 'existing_algorithm':
            continue
        if record['dataset'] == 'z1' and record['relation'] == 'opposite':
            key = 'z1_opposite_NS' if record['source_side'] in ('N', 'S') else 'z1_opposite_EW'
        elif record['dataset'] == 'z2' and record['relation'] == 'adjacent':
            key = 'z2_adjacent'
        else:
            key = 'unclassified'
        auto_groups.setdefault(key, []).append(record['uid'])
    auto_groups = OrderedDict(sorted(auto_groups.items()))
    total_auto = sum(len(uids) for uids in auto_groups.values())
    _check(checks, 'auto_total_356', total_auto == 356, total_auto)
    expected_auto = {'z1_opposite_NS': 128, 'z1_opposite_EW': 128,
                     'z2_adjacent': 100}
    for key, count in expected_auto.items():
        _check(checks, f'auto_group_{key}_count',
               len(auto_groups.get(key, [])) == count,
               len(auto_groups.get(key, [])))
    _check(checks, 'auto_group_unclassified_empty',
           'unclassified' not in auto_groups,
           len(auto_groups.get('unclassified', [])))
    _check(checks, 'all_records_classified',
           total_auto + manual_total == len(records),
           dict(auto=total_auto, manual=manual_total, records=len(records)))
    return manual_groups, auto_groups


def _separation(record):
    dx = record['target_xy'][0] - record['source_xy'][0]
    dy = record['target_xy'][1] - record['source_xy'][1]
    return (dx * dx + dy * dy) ** 0.5


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------
class InputData:
    """Loaded and validated 640-record input."""

    def __init__(self, path=None):
        self.path = str(Path(C.INPUT_CSV if path is None else path))
        rows, sha = read_csv_rows(self.path)
        self.sha256 = sha
        self.raw_rows = rows
        records = _attach_endpoints([_record(row) for row in rows])
        checks = OrderedDict()
        by_uid = _validate(records, checks)
        self.manual_groups, self.auto_groups = _assemble(records, by_uid, checks)
        self.records = records
        self.by_uid = by_uid
        self.checks = checks
        self.manual_groups = OrderedDict(
            (int(layer_id), list(uids))
            for layer_id, uids in self.manual_groups.items())
        self.auto_groups = OrderedDict(self.auto_groups)
        self.validation = self._validation_payload()

    # -- queries -----------------------------------------------------------
    def __len__(self):
        return len(self.records)

    def record(self, uid):
        return self.by_uid[uid]

    def records_for(self, uids):
        return [self.by_uid[uid] for uid in uids]

    def manual_sides(self, layer_id):
        """``{side: [uid, ...]}`` of one manual layer (N/S/E/W)."""
        sides = OrderedDict((side, []) for side in SIDES)
        for uid in self.manual_groups[int(layer_id)]:
            sides[self.by_uid[uid]['source_side']].append(uid)
        return OrderedDict((side, uids) for side, uids in sides.items() if uids)

    def group_records(self, uids):
        return [self.by_uid[uid] for uid in uids]

    # -- serialisation -----------------------------------------------------
    def _validation_payload(self):
        failed = [name for name, item in self.checks.items() if not item['passed']]
        return dict(
            schema='four_side_1024_manual_u640_input_validation_v1',
            input_csv=self.path,
            sha256=self.sha256,
            total_records=len(self.records),
            datasets=dict(Counter(record['dataset'] for record in self.records)),
            manual_total=sum(len(uids) for uids in self.manual_groups.values()),
            auto_total=sum(len(uids) for uids in self.auto_groups.values()),
            manual_layer_counts={str(layer_id): len(uids)
                                 for layer_id, uids in self.manual_groups.items()},
            auto_group_counts={key: len(uids)
                               for key, uids in self.auto_groups.items()},
            checks=self.checks,
            failed_checks=failed,
            passed=not failed,
        )

    def routes_json(self):
        """Identity-only record list (no geometry)."""
        out = []
        for record in self.records:
            item = {key: value for key, value in record.items()
                    if key not in ('source_endpoint', 'target_endpoint')}
            item['source_endpoint'] = dict(record['source_endpoint'])
            item['target_endpoint'] = dict(record['target_endpoint'])
            out.append(item)
        return out

    def groups_json(self):
        return dict(
            schema='four_side_1024_manual_u640_groups_v1',
            manual_layers={str(layer_id): dict(
                group=MANUAL_LAYERS[layer_id], uids=list(uids),
                sides={side: list(side_uids)
                       for side, side_uids in self.manual_sides(layer_id).items()},
                count=len(uids))
                for layer_id, uids in self.manual_groups.items()},
            auto_groups={key: dict(uids=list(uids), count=len(uids))
                         for key, uids in self.auto_groups.items()},
        )


def load_inputs(path=None):
    """Load, validate and expose the 640-record manual grouping CSV."""
    return InputData(path)
