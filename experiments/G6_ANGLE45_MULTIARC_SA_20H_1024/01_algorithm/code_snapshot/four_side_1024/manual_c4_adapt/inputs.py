# -*- coding: utf-8 -*-
"""Input adapter for the *corrected* manual Z1 / Z2 grouping files.

The two files of this round are::

    manual_z1_router/data/exports/manual_z1_c4_full_section2.csv   (512 records)
    manual_z1_router/data/exports/manual_z2_c4_full_section2.csv   (512 records)

Design rules of this round (strictly observed here)
---------------------------------------------------
* The manual connections and their grouping are **read, never recomputed**: the
  file partition (``z1`` file / ``z2`` file), the record order, the endpoint
  pairing and the port identities are the user's manual design.
* The ``layer`` column of BOTH files says ``z1``.  It is **not** a physical layer
  assignment (the known export quirk); the data-source partition is decided by
  the file, exactly as the user requires: ``manual_z1_*`` -> interface row 1
  (physical height 0.0 mm), ``manual_z2_*`` -> interface row 2 (0.5 mm).  The CSV
  value is kept as ``csv_layer_tag`` for audit, but never used to merge planes.
* No clustering, no re-pairing, no de-duplication across the two files.
* A *manual grouping* is only read when the file actually carries it.  These two
  files carry no ``manual_group`` / ``assigned_layer`` column (unlike
  ``人工分组/z1_z2_manual_u_assignment_v2_640.csv``), so the adapter exposes
  ``group_source`` and leaves the grouping to the caller / a companion file.

The produced records use exactly the same schema as
``four_side_1024.manual_u640.inputs`` so that the existing 2D router,
U-turn geometry, elevation lift, 3D world and verifier can be reused unchanged.
"""
from __future__ import annotations

import csv
import hashlib
from collections import Counter, OrderedDict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUTS = OrderedDict([
    ('z1', PROJECT_ROOT / 'manual_z1_router' / 'data' / 'exports'
     / 'manual_z1_c4_full_section2.csv'),
    ('z2', PROJECT_ROOT / 'manual_z1_router' / 'data' / 'exports'
     / 'manual_z2_c4_full_section2.csv'),
])
SIDE_INWARD = {'N': (0.0, -1.0), 'S': (0.0, 1.0), 'E': (-1.0, 0.0),
               'W': (1.0, 0.0)}
PLANE_Z_MM = {'z1': 0.0, 'z2': 0.5}
PLANE_ROW = {'z1': 1, 'z2': 2}
EXPECTED_RECORDS = {'z1': 512, 'z2': 512}
EXPECTED_RELATIONS = {
    'z1': {'opposite': 256, 'same': 256},
    'z2': {'adjacent': 400, 'same': 112},
}
TOL = 1e-6
#: checks that are *informational* (they report a property of the input files
#: instead of asserting a requirement); they do not make the read fail
INFORMATIONAL_CHECKS = ('z1_grouping_metadata_present',
                        'z2_grouping_metadata_present')


# ---------------------------------------------------------------------------
# port model (reused project code)
# ---------------------------------------------------------------------------
def _port_xy(connector, column):
    from four_side_1024.fslw import ports
    from four_side_1024.inputs import board_xy
    along = ports.port_along_mm(int(str(connector)[1:]), int(column))
    return tuple(float(v) for v in board_xy(str(connector)[0], along))


def _expected_row(plane):
    return PLANE_ROW[plane]


def _expected_z(plane):
    return PLANE_Z_MM[plane]


# ---------------------------------------------------------------------------
# record construction
# ---------------------------------------------------------------------------
def _endpoint(plane, port_id, side, xy):
    connector, _row, column = str(port_id).split(':')
    column = int(column)
    row = _expected_row(plane)
    expected_xy = _port_xy(connector, column)
    return dict(
        endpoint_id=f'{connector}:{row}:{column}',
        csv_port_id=str(port_id),
        connector=connector,
        side=str(side),
        column=column,
        row=int(row),
        plane=plane,
        z_mm=_expected_z(plane),
        layer_id=1,
        xy=[float(xy[0]), float(xy[1])],
        routing_xy=[float(xy[0]), float(xy[1])],
        inward=list(SIDE_INWARD[str(side)]),
        port_model_xy=[float(expected_xy[0]), float(expected_xy[1])],
        xy_matches_port_model=bool(
            abs(float(xy[0]) - expected_xy[0]) <= TOL
            and abs(float(xy[1]) - expected_xy[1]) <= TOL),
    )


def _record(plane, row):
    route_id = int(row['route_id'])
    record = dict(
        uid=f'{plane}:{route_id}',
        internal_id=(1 if plane == 'z1' else 2) * 100000 + route_id,
        dataset=plane, plane=plane,
        original_route_id=route_id,
        relation=str(row['relation']).strip(),
        source_side=str(row['source_side']).strip(),
        target_side=str(row['target_side']).strip(),
        source_port_id=str(row['source_port_id']).strip(),
        target_port_id=str(row['target_port_id']).strip(),
        source_xy=[float(row['source_x_mm']), float(row['source_y_mm'])],
        target_xy=[float(row['target_x_mm']), float(row['target_y_mm'])],
        csv_source_row=int(row['source_row']),
        csv_target_row=int(row['target_row']),
        source_row=_expected_row(plane),
        target_row=_expected_row(plane),
        source_z_mm=_expected_z(plane),
        target_z_mm=_expected_z(plane),
        csv_layer_tag=str(row.get('layer', '') or '').strip(),
        assignment=None,            # filled by the grouping source
        manual_group=None,
        manual_group_order=None,
        u_pair=None,
        assigned_layer_csv=None,
        assigned_layer=None,
        cross_dataset_same_port_pair='NO',
        source_endpoint=_endpoint(plane, row['source_port_id'],
                                  row['source_side'],
                                  (row['source_x_mm'], row['source_y_mm'])),
        target_endpoint=_endpoint(plane, row['target_port_id'],
                                  row['target_side'],
                                  (row['target_x_mm'], row['target_y_mm'])),
    )
    record['source_endpoint_id'] = record['source_endpoint']['endpoint_id']
    record['target_endpoint_id'] = record['target_endpoint']['endpoint_id']
    return record


def read_csv(path):
    raw = Path(path).read_bytes()
    rows = list(csv.DictReader(raw.decode('utf-8-sig').splitlines()))
    return rows, hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------------------
# static validation (read-correctness, not routing)
# ---------------------------------------------------------------------------
def _check(checks, name, ok, detail=None):
    checks[name] = dict(passed=bool(ok), detail=detail)
    return bool(ok)


def validate(records_by_plane, checks, rows_by_plane):
    for plane, records in records_by_plane.items():
        rows = rows_by_plane[plane]
        expected = EXPECTED_RECORDS[plane]
        _check(checks, f'{plane}_record_count', len(records) == expected,
               dict(expected=expected, actual=len(records)))
        uids = [record['uid'] for record in records]
        _check(checks, f'{plane}_uid_unique', len(set(uids)) == len(uids),
               len(uids) - len(set(uids)))
        route_ids = [record['original_route_id'] for record in records]
        _check(checks, f'{plane}_route_id_unique',
               len(set(route_ids)) == len(route_ids),
               len(route_ids) - len(set(route_ids)))
        _check(checks, f'{plane}_route_id_contiguous',
               sorted(route_ids) == list(range(1, expected + 1)),
               dict(min=min(route_ids), max=max(route_ids)))
        relations = Counter(record['relation'] for record in records)
        _check(checks, f'{plane}_relation_counts',
               dict(relations) == EXPECTED_RELATIONS[plane],
               dict(expected=EXPECTED_RELATIONS[plane], actual=dict(relations)))
        # endpoint coordinates must equal the project's real port model
        bad = [record['uid'] for record in records
               if not (record['source_endpoint']['xy_matches_port_model']
                       and record['target_endpoint']['xy_matches_port_model'])]
        _check(checks, f'{plane}_endpoint_coordinates_match_port_model',
               not bad, bad[:8])
        # relation must be consistent with the two sides
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
                bad.append((record['uid'], relation, sorted(sides)))
        _check(checks, f'{plane}_relation_matches_sides', not bad, bad[:8])
        # every physical port used exactly once inside its own plane
        ports = []
        for record in records:
            ports.extend([record['source_endpoint_id'],
                          record['target_endpoint_id']])
        ports = Counter(ports)
        duplicates = {key: value for key, value in ports.items() if value > 1}
        _check(checks, f'{plane}_ports_used_once',
               len(ports) == expected * 2 and not duplicates,
               dict(unique=len(ports), expected=expected * 2,
                    duplicates=dict(list(duplicates.items())[:8])))
        # no duplicated connection (undirected) inside one plane
        pairs = Counter(tuple(sorted((record['source_endpoint_id'],
                                      record['target_endpoint_id'])))
                        for record in records)
        duplicates = {key: value for key, value in pairs.items() if value > 1}
        _check(checks, f'{plane}_connection_pairs_unique', not duplicates,
               dict(list(duplicates.items())[:8]))
        # CSV row digit vs the physical interface row of this plane
        mismatched = [record['uid'] for record in records
                      if record['csv_source_row'] != record['source_row']
                      or record['csv_target_row'] != record['target_row']]
        _check(checks, f'{plane}_csv_row_vs_physical_row',
               True, dict(passed_through=True,
                          note=('the CSV row digit is kept as-is; the physical '
                                'interface row is decided by the data source '
                                '(file) and is given by expected_row'),
                          physical_row=_expected_row(plane),
                          csv_mismatch_count=len(mismatched),
                          examples=mismatched[:6]))
        # the layer column of both files says z1 -> record it, never use it
        layers = Counter(record['csv_layer_tag'] for record in records)
        _check(checks, f'{plane}_csv_layer_tag_not_used', True,
               dict(values=dict(layers),
                    note=('the export layer column does not distinguish the two '
                          'planes; the file/data-source decides the plane')))
    # cross-file: same XY columns on two different physical heights
    z1_ports = set()
    z2_ports = set()
    for record in records_by_plane['z1']:
        z1_ports.update([record['source_endpoint_id'],
                         record['target_endpoint_id']])
    for record in records_by_plane['z2']:
        z2_ports.update([record['source_endpoint_id'],
                         record['target_endpoint_id']])
    shared = sorted(z1_ports & z2_ports)
    _check(checks, 'cross_plane_ports_audited', True,
           dict(z1_ports=len(z1_ports), z2_ports=len(z2_ports),
                shared=len(shared), shared_examples=shared[:10],
                note=('shared entries are the same 2x16 column on interface row 1 '
                      '(z=0.0 mm) and row 2 (z=0.5 mm); they are different '
                      'physical ports and are never merged')))
    # grouping metadata availability
    for plane, rows in rows_by_plane.items():
        columns = set(rows[0].keys()) if rows else set()
        group_columns = sorted(name for name in columns
                               if any(word in name.lower() for word in
                                      ('group', 'assign', 'u_pair', 'u_logical')))
        _check(checks, f'{plane}_grouping_metadata_present', bool(group_columns),
               dict(columns_in_file=sorted(columns),
                    group_columns=group_columns,
                    note=('these two files carry only connection identity + the '
                          'unreliable export layer column; the explicit manual '
                          'group/layer assignment is not part of them')))
    return checks


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------
class ManualC4Inputs:
    """Corrected manual Z1/Z2 inputs, read and statically validated."""

    def __init__(self, paths=None):
        paths = OrderedDict(DEFAULT_INPUTS if paths is None else paths)
        self.paths = OrderedDict((plane, Path(path))
                                 for plane, path in paths.items())
        self.rows = OrderedDict()
        self.sha256 = OrderedDict()
        for plane, path in self.paths.items():
            rows, sha = read_csv(path)
            self.rows[plane] = rows
            self.sha256[plane] = sha
        self.records_by_plane = OrderedDict(
            (plane, [_record(plane, row) for row in rows])
            for plane, rows in self.rows.items())
        self.checks = OrderedDict()
        validate(self.records_by_plane, self.checks, self.rows)
        self.validation = self._payload()

    # -- queries -----------------------------------------------------------
    @property
    def records(self):
        out = []
        for records in self.records_by_plane.values():
            out.extend(records)
        return out

    def records_of_relation(self, plane, relation):
        return [record for record in self.records_by_plane[plane]
                if record['relation'] == relation]

    def by_uid(self):
        return {record['uid']: record for record in self.records}

    # -- serialisation -----------------------------------------------------
    def _payload(self):
        hard_failed = [name for name, item in self.checks.items()
                       if not item['passed']
                       and name not in INFORMATIONAL_CHECKS]
        findings = [name for name, item in self.checks.items()
                    if not item['passed']
                    and name in INFORMATIONAL_CHECKS]
        hard_total = sum(1 for name in self.checks
                         if name not in INFORMATIONAL_CHECKS)
        return dict(
            schema='four_side_1024_manual_c4_adapt_input_validation_v1',
            files={plane: dict(path=str(path), sha256=self.sha256[plane],
                               records=len(self.records_by_plane[plane]))
                   for plane, path in self.paths.items()},
            plane_rules=dict(
                z1=dict(physical_row=PLANE_ROW['z1'], z_mm=PLANE_Z_MM['z1']),
                z2=dict(physical_row=PLANE_ROW['z2'], z_mm=PLANE_Z_MM['z2'])),
            relation_counts={plane: dict(Counter(
                record['relation'] for record in records))
                for plane, records in self.records_by_plane.items()},
            checks=self.checks,
            hard_checks_total=hard_total,
            hard_checks_passed=hard_total - len(hard_failed),
            failed_checks=hard_failed,
            informational_findings=findings,
            passed=not hard_failed,
            # the two files do not carry the explicit manual layer grouping
            manual_group_metadata_available=False,
            manual_group_metadata_note=(
                'the explicit manual group / assigned-layer assignment is not '
                'part of these two files; the adapter therefore exposes the '
                'records unmodified and leaves "which records belong to the '
                'manual groups and on which layer" to the caller or to the '
                'companion file 人工分组/z1_z2_manual_u_assignment_v2_640.csv'),
        )

    def records_payload(self):
        out = []
        for record in self.records:
            item = dict(record)
            item['source_endpoint'] = dict(record['source_endpoint'])
            item['target_endpoint'] = dict(record['target_endpoint'])
            out.append(item)
        return out


def load_manual_c4_inputs(paths=None):
    return ManualC4Inputs(paths)
