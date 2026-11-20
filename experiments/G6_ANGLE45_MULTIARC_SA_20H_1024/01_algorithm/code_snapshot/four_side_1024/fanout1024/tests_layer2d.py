# -*- coding: utf-8 -*-
"""Self-tests of the per-layer 2D R15 body router (``fanout1024.layer2d``).

Run with::

    .venv\\Scripts\\python.exe four_side_1024\\fanout1024\\tests_layer2d.py

The tests are also pytest-compatible (functions named ``test_*``).

Coverage
--------
A. synthetic per-class poses (same-side U / opposite / adjacent): full routing,
   exact start/end poses, exact R=15 arcs, board bounds, strict-D56 re-check and
   byte-level determinism.
B. the 8 real manual-U layers (L2-L5, L10-L13, 368 routes) from the verified
   assignment: every route must be routed.
C. synthetic opposite (L6, 128 routes) and adjacent (L8, 50 routes) layers built
   from the true z1-opposite / z2-adjacent connections: high success + reasons.
D. integration smoke test against the live fanout artifacts (if present): all
   18 layers, reporting per-layer counts (read-only use of the run directory).
E. the ``initial_routes`` joint-repair primitive (frozen layout insertion).
"""
from __future__ import annotations

import csv
import json
import math
import sys
import unittest
from collections import OrderedDict, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from four_side_1024.fanout1024 import common, layer2d  # noqa: E402
from four_side_1024.fsd25d import path3d  # noqa: E402
from four_side_1024.d56.index import D56Index, prepare as d56_prepare  # noqa: E402
from four_side_1024.fsd25d.world25d import primitive_bbox  # noqa: E402

RUN_DIR = common.RUN_DIR
ASSIGNMENT_CSV = RUN_DIR / 'assignment_1024.csv'
FANOUT_SELECTED = RUN_DIR / 'fanout_selected.json'
BATCH_LIMIT = 20000      # deterministic per-test bound on candidate evaluations

#: 21-height experiment root (SPEC: reheight21/SPEC.md) -- read-only in tests
NEW_RUN_DIR = (common.OUTPUT_ROOT / 'FANOUT_FIRST_21_HEIGHT_REBALANCED_1024')
NEW_ASSIGNMENT_CSV = NEW_RUN_DIR / 'assignment_1024.csv'
NEW_FANOUT_SELECTED = NEW_RUN_DIR / 'fanout_selected.json'

#: 21 routable heights of the new experiment (SPEC section 1)
PLANE_Z21 = OrderedDict([
    (2, -0.35), (3, -0.30), (4, -0.25), (5, -0.20),
    (6, -0.15), (7, -0.10), (20, -0.05),
    (1001, 0.0), (8, 0.05), (9, 0.10),
    (10, 0.15), (11, 0.20), (12, 0.25), (13, 0.30),
    (14, 0.35), (15, 0.40), (16, 0.45), (1002, 0.5),
    (17, 0.55), (18, 0.60), (19, 0.65),
])
INTERFACE_PLANES21 = (1001, 1002)
PLANE_LABEL21 = {2: 'L2', 3: 'L3', 4: 'L4', 5: 'L5', 6: 'L6', 7: 'L7',
                 20: 'L20', 1001: 'Z1_INTERFACE', 8: 'L8', 9: 'L9',
                 10: 'L10', 11: 'L11', 12: 'L12', 13: 'L13',
                 14: 'L14', 15: 'L15', 16: 'L16', 1002: 'Z2_INTERFACE',
                 17: 'L17', 18: 'L18', 19: 'L19'}
Z2_OLD_TO_NEW = {8: 9, 9: 14, 14: 15, 15: 16, 16: 17, 17: 18, 18: 19,
                 19: 1002}
Z1_PLAN21 = [(6, 13), (7, 13), (20, 13), (1001, 13), (8, 12)]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def load_assignment_rows():
    if not ASSIGNMENT_CSV.is_file():
        return None
    rows = []
    with open(ASSIGNMENT_CSV, encoding='utf-8-sig', newline='') as handle:
        for row in csv.DictReader(handle):
            record = dict(row)
            record['route_id'] = int(row['route_id'])
            record['target_layer'] = int(row['target_layer'])
            record['target_z_mm'] = float(row['target_z_mm'])
            rows.append(record)
    return rows


def load_fanout_selected():
    if not FANOUT_SELECTED.is_file():
        return None
    payload = json.loads(FANOUT_SELECTED.read_text(encoding='utf-8'))
    selected = payload.get('selected') if isinstance(payload, dict) else None
    if selected is None:
        return None
    return {int(key): value for key, value in selected.items()}


def tasks_for_rows(rows, lead=2.0):
    """Landing tasks for assignment rows with a fixed lead (synthetic fanout)."""
    landings = layer2d.synthesize_landings(rows, lead=lead)
    return layer2d.make_tasks_from_assignment(rows, landings)


def body_errors(body, task, label='body'):
    """Independent structural audit of one routed body chain."""
    prims = body['primitives']
    errors = []
    if not prims:
        return [f'{label}:empty']
    A = (float(task['A'][0]), float(task['A'][1]))
    B = (float(task['B'][0]), float(task['B'][1]))
    dA = (float(task['dA'][0]), float(task['dA'][1]))
    dB = (float(task['dB'][0]), float(task['dB'][1]))
    # exact endpoint poses
    if math.hypot(prims[0]['p0'][0] - A[0], prims[0]['p0'][1] - A[1]) > 1e-6:
        errors.append(f'{label}:start_point_mismatch')
    if math.hypot(prims[-1]['p1'][0] - B[0], prims[-1]['p1'][1] - B[1]) > 1e-6:
        errors.append(f'{label}:end_point_mismatch')
    start_tangent = layer2d._start_tangent(prims[0])
    end_tangent = layer2d._end_tangent(prims[-1])
    if layer2d._tangent_gap(start_tangent, dA) > 1e-4:
        errors.append(f'{label}:start_tangent_mismatch')
    if layer2d._tangent_gap(end_tangent, (-dB[0], -dB[1])) > 1e-4:
        errors.append(f'{label}:end_tangent_mismatch')
    # chain continuity, radius, orthogonal lines, board bounds
    for index, prim in enumerate(prims):
        if prim['kind'] == 'arc':
            if abs(float(prim['radius']) - 15.0) > 1e-9:
                errors.append(f'{label}:arc_radius:{index}')
            if abs(float(prim['sweep'])) > math.pi / 2.0 + 1e-9:
                errors.append(f'{label}:arc_sweep:{index}')
            center = prim['center']
            radius = float(prim['radius'])
            start_angle = float(prim['start_angle'])
            sweep = float(prim['sweep'])
            for key, angle in (('p0', start_angle), ('p1', start_angle + sweep)):
                calc = (center[0] + radius * math.cos(angle),
                        center[1] + radius * math.sin(angle))
                if math.hypot(calc[0] - prim[key][0],
                              calc[1] - prim[key][1]) > 1e-7:
                    errors.append(f'{label}:arc_inconsistent:{index}')
        elif prim['kind'] == 'line':
            dx = abs(prim['p1'][0] - prim['p0'][0])
            dy = abs(prim['p1'][1] - prim['p0'][1])
            if dx > 1e-9 and dy > 1e-9:
                errors.append(f'{label}:diagonal_line:{index}')
            if math.hypot(prim['p1'][0] - prim['p0'][0],
                          prim['p1'][1] - prim['p0'][1]) < 1e-12:
                errors.append(f'{label}:zero_line:{index}')
        else:
            errors.append(f'{label}:unknown_primitive:{index}')
        box = primitive_bbox(prim)
        if box[0] < -1e-6 or box[1] < -1e-6 or box[2] > 150.0 + 1e-6 \
                or box[3] > 150.0 + 1e-6:
            errors.append(f'{label}:outside_board:{index}')
        if index:
            previous = prims[index - 1]
            if math.hypot(previous['p1'][0] - prim['p0'][0],
                          previous['p1'][1] - prim['p0'][1]) > 1e-9:
                errors.append(f'{label}:discontinuous:{index}')
            if layer2d._tangent_gap(layer2d._end_tangent(previous),
                                    layer2d._start_tangent(prim)) > 1e-6:
                errors.append(f'{label}:tangent_kink:{index}')
    return errors


def recheck_layer_conflicts(routed, label='layer'):
    """Rebuild a fresh strict D56 index over the routed bodies (order check)."""
    index = D56Index(width=0.05, gap=0.03, sagitta=0.0005,
                     min_cross_angle_deg=5.0, crossing_policy='strict')
    errors = []
    for route_id in sorted(routed):
        prims = routed[route_id]['primitives']
        evaluation = index.evaluate(d56_prepare(prims))
        if not evaluation.valid:
            errors.append(f'{label}:conflict:{route_id}:{evaluation.reason}')
            break
        index.add(route_id, d56_prepare(prims))
    return errors


def assert_bodies(testcase, result, task_map, label):
    routed = result['routed']
    for route_id, body in routed.items():
        task = task_map[int(route_id)]
        errors = body_errors(body, task, f'{label}:{route_id}')
        testcase.assertFalse(errors, errors[:5])
    errors = recheck_layer_conflicts(routed, label)
    testcase.assertFalse(errors, errors[:5])


# ---------------------------------------------------------------------------
# A. synthetic per-class poses
# ---------------------------------------------------------------------------
class TestSyntheticClasses(unittest.TestCase):
    """12 realistic synthetic tasks per layer class, fully routed and audited."""

    @classmethod
    def setUpClass(cls):
        cls.rows = load_assignment_rows()
        if cls.rows is None:
            raise unittest.SkipTest('assignment_1024.csv not available')
        by_relation = {}
        for row in cls.rows:
            by_relation.setdefault(row['relation'], []).append(row)
        cls.by_relation = by_relation
        # landing depth 4.5..6.0 mm: choose the lead that gives such a depth
        cls.leads = {}
        for layer_id, z_mm in ((2, -0.35), (6, -0.11), (8, 0.05)):
            plane = 'z1' if layer_id < 8 else 'z2'
            footprint = layer2d.footprint_mm(
                z_mm - common.interface_z(plane))
            lead = max(0.25, 4.6 - footprint)
            cls.leads[layer_id] = round(min(lead, 6.0 - footprint), 6)

    def _tasks(self, relation, layer_id, count=12):
        rows = [row for row in self.by_relation[relation]
                if row['target_layer'] == layer_id][:count]
        self.assertEqual(len(rows), count,
                         f'not enough {relation} rows on L{layer_id}')
        lead = self.leads[layer_id]
        z_mm = common.layer_z(layer_id)
        plane = 'z1' if layer_id < 8 else 'z2'
        footprint = layer2d.footprint_mm(z_mm - common.interface_z(plane))
        depth = lead + footprint
        self.assertGreaterEqual(depth, 4.4)
        self.assertLessEqual(depth, 6.2)
        tasks_map = tasks_for_rows(rows, lead=lead)
        self.assertIn(layer_id, tasks_map)
        return tasks_map[layer_id]['tasks']

    def _check(self, relation, layer_id):
        tasks = self._tasks(relation, layer_id)
        z_mm = common.layer_z(layer_id)
        result = layer2d.route_layer(layer_id, z_mm, tasks, obstacles=[],
                                     budget=600, rr_rounds=2, log=lambda *a: None)
        stats = result['stats']
        self.assertEqual(stats['success'], len(tasks),
                         f'{relation}: routed {stats["success"]}/{len(tasks)} '
                         f'failed={result["failed"]}')
        task_map = {task['route_id']: task for task in tasks}
        assert_bodies(self, result, task_map, f'synthetic_{relation}')
        # determinism: an identical rerun must produce identical geometry
        again = layer2d.route_layer(layer_id, z_mm, tasks, obstacles=[],
                                    budget=600, rr_rounds=2,
                                    log=lambda *a: None)
        self.assertEqual(sorted(result['routed']), sorted(again['routed']))
        for route_id in result['routed']:
            first = json.dumps(result['routed'][route_id]['primitives'],
                               sort_keys=True)
            second = json.dumps(again['routed'][route_id]['primitives'],
                                sort_keys=True)
            self.assertEqual(first, second,
                             f'determinism mismatch for route {route_id}')

    def test_same_side_u(self):
        self._check('same', 2)

    def test_opposite(self):
        self._check('opposite', 6)

    def test_adjacent(self):
        self._check('adjacent', 8)


# ---------------------------------------------------------------------------
# B. the 8 real manual-U layers (368 routes)
# ---------------------------------------------------------------------------
class TestManualLayers(unittest.TestCase):
    MANUAL_LAYERS = (2, 3, 4, 5, 10, 11, 12, 13)

    def test_all_manual_layers_routed(self):
        rows = load_assignment_rows()
        if rows is None:
            self.skipTest('assignment_1024.csv not available')
        manual = [row for row in rows if row.get('manual_group')]
        self.assertEqual(len(manual), 368)
        tasks_map = tasks_for_rows(manual, lead=2.0)
        self.assertEqual(sorted(tasks_map), list(self.MANUAL_LAYERS))
        result = layer2d.route_all_layers(tasks_map, out_dir=None,
                                          log=lambda *a: None)
        self.assertEqual(len(result['layers']), 8)
        total_input = total_routed = 0
        for layer_id, layer_result in result['layers'].items():
            stats = layer_result['stats']
            total_input += stats['input']
            total_routed += stats['success']
            task_map = {task['route_id']: task
                        for task in tasks_map[layer_id]['tasks']}
            assert_bodies(self, layer_result, task_map, f'manual_L{layer_id}')
            self.assertEqual(stats['success'], stats['input'],
                             f'L{layer_id} routed {stats["success"]}'
                             f'/{stats["input"]} failed={layer_result["failed"]}')
        self.assertEqual(total_input, 368)
        self.assertEqual(total_routed, 368)
        # the failed list must be reconciled: no stale entries at all
        self.assertEqual(sum(len(layer['failed'])
                             for layer in result['layers'].values()), 0)
        # a second deterministic run gives identical geometry
        again = layer2d.route_all_layers(tasks_map, out_dir=None,
                                         log=lambda *a: None)
        for layer_id in result['layers']:
            first = result['layers'][layer_id]['routed']
            second = again['layers'][layer_id]['routed']
            self.assertEqual(sorted(first), sorted(second))
            for route_id in first:
                self.assertEqual(
                    json.dumps(first[route_id]['primitives'], sort_keys=True),
                    json.dumps(second[route_id]['primitives'], sort_keys=True))


# ---------------------------------------------------------------------------
# C. synthetic opposite / adjacent layers
# ---------------------------------------------------------------------------
class TestOppositeAdjacentLayers(unittest.TestCase):

    def test_opposite_128_routes(self):
        rows = load_assignment_rows()
        if rows is None:
            self.skipTest('assignment_1024.csv not available')
        opposite = [row for row in rows
                    if row['relation'] == 'opposite'
                    and row['target_layer'] in (6, 7)]
        self.assertEqual(len(opposite), 256)
        selected = [row for row in opposite if row['target_layer'] == 6][:128]
        self.assertEqual(len(selected), 128)
        tasks_map = tasks_for_rows(selected, lead=2.0)
        layer_id = 6
        result = layer2d.route_layer(layer_id, common.layer_z(layer_id),
                                     tasks_map[layer_id]['tasks'],
                                     obstacles=[], budget=600, rr_rounds=2,
                                     log=lambda *a: None)
        stats = result['stats']
        success = stats['success']
        rate = success / float(stats['input'])
        print(f'[test] synthetic L6 opposite: {success}/{stats["input"]} '
              f'({100.0 * rate:.1f}%) families={stats.get("families")} '
              f'reasons={ {r["reason"]: sum(1 for x in result["failed"] if x["reason"] == r["reason"]) for r in result["failed"]} }')
        self.assertGreaterEqual(rate, 0.95,
                                f'opposite layer success {success}/'
                                f'{stats["input"]} below 95%')
        task_map = {task['route_id']: task
                    for task in tasks_map[layer_id]['tasks']}
        assert_bodies(self, result, task_map, 'synthetic_opposite')
        # every failure must be a real assigned route id with a real reason
        assigned = set(task_map)
        for record in result['failed']:
            self.assertIn(int(record['route_id']), assigned)
            self.assertTrue(record['reason'])
        self.assertEqual({int(r['route_id']) for r in result['failed']},
                         assigned - set(result['routed']))

    def test_adjacent_50_routes(self):
        rows = load_assignment_rows()
        if rows is None:
            self.skipTest('assignment_1024.csv not available')
        adjacent = [row for row in rows
                    if row['relation'] == 'adjacent'
                    and row['target_layer'] == 8][:50]
        self.assertEqual(len(adjacent), 48)  # final assignment has 48 on L8
        tasks_map = tasks_for_rows(adjacent, lead=2.0)
        layer_id = 8
        result = layer2d.route_layer(layer_id, common.layer_z(layer_id),
                                     tasks_map[layer_id]['tasks'],
                                     obstacles=[], budget=600, rr_rounds=2,
                                     log=lambda *a: None)
        stats = result['stats']
        rate = stats['success'] / float(stats['input'])
        print(f'[test] synthetic L8 adjacent: {stats["success"]}/'
              f'{stats["input"]} ({100.0 * rate:.1f}%) '
              f'families={stats.get("families")}')
        self.assertGreaterEqual(rate, 0.95)
        task_map = {task['route_id']: task
                    for task in tasks_map[layer_id]['tasks']}
        assert_bodies(self, result, task_map, 'synthetic_adjacent')


# ---------------------------------------------------------------------------
# E. frozen-layout repair primitive (initial_routes)
# ---------------------------------------------------------------------------
class TestInitialRoutesRepair(unittest.TestCase):

    def test_repair_into_frozen_layout(self):
        rows = load_assignment_rows()
        if rows is None:
            self.skipTest('assignment_1024.csv not available')
        manual = [row for row in rows if row['target_layer'] == 2]
        tasks_map = tasks_for_rows(manual, lead=2.0)
        layer_id = 2
        z_mm = common.layer_z(layer_id)
        full = layer2d.route_layer(layer_id, z_mm,
                                   tasks_map[layer_id]['tasks'],
                                   obstacles=[], log=lambda *a: None)
        self.assertEqual(full['stats']['success'], len(tasks_map[layer_id]['tasks']))
        route_ids = list(full['routed'])
        frozen = {rid: full['routed'][rid]['primitives']
                  for rid in route_ids[:-1]}
        target = route_ids[-1]
        task = next(item for item in tasks_map[layer_id]['tasks']
                    if item['route_id'] == target)
        repair = layer2d.route_layer(
            layer_id, z_mm, [task], obstacles=[], budget=1200,
            rr_rounds=0, initial_routes=frozen, log=lambda *a: None)
        self.assertEqual(repair['stats']['initial_routes'], len(frozen))
        self.assertEqual(set(repair['routed']), {target})
        self.assertEqual(repair['stats']['input'], 1)
        self.assertEqual(repair['stats']['success'], 1)
        # frozen bodies must be acting as strict blockers
        index = D56Index(width=0.05, gap=0.03, sagitta=0.0005,
                         min_cross_angle_deg=5.0, crossing_policy='strict')
        for rid, prims in frozen.items():
            index.add(rid, d56_prepare(prims))
        evaluation = index.evaluate(
            d56_prepare(repair['routed'][target]['primitives']))
        self.assertTrue(evaluation.valid, evaluation.reason)
        # route_all_layers must forward a per-layer initial_routes map
        subset = {layer_id: dict(layer_id=layer_id, z_mm=z_mm, tasks=[task],
                                 obstacles=[])}
        aggregated = layer2d.route_all_layers(
            subset, out_dir=None, initial_routes={layer_id: frozen},
            log=lambda *a: None)
        self.assertEqual(
            aggregated['layers'][layer_id]['stats']['initial_routes'],
            len(frozen))
        self.assertEqual(len(aggregated['layers'][layer_id]['routed']), 1)


# ---------------------------------------------------------------------------
# D. integration smoke test (read-only against the live run directory)
# ---------------------------------------------------------------------------
class TestIntegration(unittest.TestCase):
    """Route all 18 layers using the live fanout landings + layer obstacles."""

    def test_all_layers_integration(self):
        rows = load_assignment_rows()
        selected = load_fanout_selected()
        if rows is None or selected is None:
            self.skipTest('fanout_selected.json not available yet')
        from four_side_1024.fanout1024 import fanout
        landings = fanout.landings(selected)
        layers = {}
        for row in rows:
            layer_id = int(row['target_layer'])
            pose = landings.get(int(row['route_id']))
            if pose is None:
                continue
            entry = layers.setdefault(
                layer_id, dict(layer_id=layer_id,
                               z_mm=common.layer_z(layer_id),
                               tasks=[], obstacles=[]))
            entry['tasks'].append(dict(
                route_id=int(row['route_id']),
                manual_group=row.get('manual_group') or '',
                relation=row.get('relation') or '',
                source_side=row.get('source_side'),
                target_side=row.get('target_side'),
                A=tuple(pose['A']), dA=tuple(pose['dA']),
                B=tuple(pose['B']), dB=tuple(pose['dB'])))
        for layer_id in layers:
            layers[layer_id]['obstacles'] = fanout.layer_obstacles(
                selected, layer_id)
        result = layer2d.route_all_layers(layers, out_dir=None,
                                          log=lambda *a: None)
        total_input = total_routed = 0
        for layer_id, layer_result in result['layers'].items():
            stats = layer_result['stats']
            total_input += stats['input']
            total_routed += stats['success']
            print(f'[test] integration L{layer_id}: {stats["success"]}/'
                  f'{stats["input"]} failed={stats["failed"]} '
                  f'{stats["seconds"]:.1f}s')
        print(f'[test] integration total: {total_routed}/{total_input}')
        # every failure record is a real route id with a real reason
        for layer_result in result['layers'].values():
            for record in layer_result['failed']:
                self.assertTrue(record['reason'])
                self.assertLessEqual(len(record['blockers']), 64)
        self.assertGreaterEqual(total_routed, 1000,
                                f'integration rolled back to {total_routed}/'
                                f'{total_input}')


# ---------------------------------------------------------------------------
# F. 21-height experiment: arbitrary plane ids, explicit z_mm, interface planes
# ---------------------------------------------------------------------------
def _truthy(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'y')
    return bool(value)


def _build_synthetic_21_rows():
    """Approximate 21-plane assignment from the baseline assignment (SPEC s.2).

    Used only when the real 21-height artifacts do not exist yet; the real
    experiment C run consumes the fanout owner's artifacts instead.
    """
    rows = load_assignment_rows()
    if rows is None:
        return None
    by_id = {row['route_id']: row for row in rows}
    plane_of = {}
    for row in rows:
        if row.get('manual_group'):
            plane_of[row['route_id']] = int(row['target_layer'])
    groups = defaultdict(list)
    for row in rows:
        if row.get('manual_group') or row.get('plane') != 'z1':
            continue
        groups[int(row.get('c4_group_id') or 0)].append(row['route_id'])
    orbit_ids = sorted(groups)
    cursor = 0
    for plane_id, count in Z1_PLAN21:
        for group_id in orbit_ids[cursor:cursor + count]:
            for route_id in groups[group_id]:
                plane_of[route_id] = plane_id
        cursor += count
    for row in rows:
        if row.get('manual_group') or row.get('plane') != 'z2':
            continue
        plane_of[row['route_id']] = Z2_OLD_TO_NEW[int(row['target_layer'])]
    out = []
    for route_id in sorted(plane_of):
        row = dict(by_id[route_id])
        plane_id = plane_of[route_id]
        row['plane_id'] = plane_id
        row['target_z_mm'] = PLANE_Z21[plane_id]
        row['interface_z_mm'] = common.interface_z(row['plane'])
        row['needs_transition'] = abs(
            row['target_z_mm'] - row['interface_z_mm']) > 1e-12
        row['target_layer'] = plane_id
        out.append(row)
    return out


def _synthetic_21_fanout(rows):
    """``(landings, leads_by_plane, transitions)`` from the baseline fanout.

    Frozen interface leads use the baseline lead lengths (real lead choices of
    the 21-height fanout run may differ); the S-curve transitions are rebuilt to
    the new plane z values with the true R15 geometry and sampled at 0.02 mm,
    exactly like ``fanout.layer_obstacles``.
    """
    baseline_selected = load_fanout_selected()
    if baseline_selected is None:
        return None, None, None
    endpoints = common.endpoints()
    landings = {}
    leads = defaultdict(dict)
    transitions = []
    for row in rows:
        route_id = row['route_id']
        plane = str(row['plane'])
        interface_id = 1001 if plane == 'z1' else 1002
        z0 = float(row['interface_z_mm'])
        zt = float(row['target_z_mm'])
        src = endpoints[str(row['source_endpoint'])]
        dst = endpoints[str(row['target_endpoint'])]
        p_s = tuple(float(v) for v in src['routing_xy'])
        p_t = tuple(float(v) for v in dst['routing_xy'])
        d_s = tuple(float(v) for v in src['inward'])
        d_t = tuple(float(v) for v in dst['inward'])
        if not row['needs_transition']:
            landings[route_id] = dict(A=p_s, dA=d_s, B=p_t, dB=d_t)
            continue
        base = baseline_selected[route_id]
        lead_s = float(base['source']['lead_mm'])
        lead_t = float(base['target']['lead_mm'])
        q_s = (p_s[0] + lead_s * d_s[0], p_s[1] + lead_s * d_s[1])
        q_t = (p_t[0] + lead_t * d_t[0], p_t[1] + lead_t * d_t[1])
        leads[interface_id][route_id * 2] = [dict(
            kind='line', p0=list(p_s), p1=list(q_s), layer=0)]
        leads[interface_id][route_id * 2 + 1] = [dict(
            kind='line', p0=list(p_t), p1=list(q_t), layer=0)]
        src_trans = path3d.make_transition(q_s, d_s, z0, zt, radius=15.0)
        dst_trans = path3d.make_transition(q_t, d_t, z0, zt, radius=15.0)
        transitions.append((route_id, 'source', src_trans))
        transitions.append((route_id, 'target', dst_trans))
        footprint = float(src_trans['footprint_mm'])
        landings[route_id] = dict(
            A=(q_s[0] + footprint * d_s[0], q_s[1] + footprint * d_s[1]),
            dA=d_s,
            B=(q_t[0] + footprint * d_t[0], q_t[1] + footprint * d_t[1]),
            dB=d_t,
        )
    return landings, leads, transitions


def _interface_obstacles(transitions, plane_z, step=0.02, band=0.07):
    """Transition-sample obstacles with ``|z - plane_z| <= band`` (one height)."""
    out = []
    for route_id, role, transition in transitions:
        z_lo = min(float(transition['z0']), float(transition['z1']))
        z_hi = max(float(transition['z0']), float(transition['z1']))
        if plane_z < z_lo - band or plane_z > z_hi + band:
            continue
        for sample in path3d.transition_samples(transition, step=step):
            if abs(float(sample[2]) - plane_z) <= band:
                out.append(dict(x=float(sample[0]), y=float(sample[1]),
                                z=float(sample[2]),
                                route_id=int(route_id), role=role))
    return out


def _candidate_lead_line(a, b):
    return [dict(kind='line', p0=[float(a[0]), float(a[1])],
                 p1=[float(b[0]), float(b[1])], layer=0)]


class TestMultiHeightLayerKeys(unittest.TestCase):
    """Arbitrary plane ids (20 / 1001 / 1002) with explicit z_mm and frozen leads."""

    @staticmethod
    def _u_task(route_id, offset):
        # same-side U at the board edge (depth 0): A/B on the N side, separation 50
        return dict(route_id=route_id, relation='same',
                    A=(10.0 + offset, 150.0), dA=(0.0, -1.0),
                    B=(60.0 + offset, 150.0), dB=(0.0, -1.0))

    def test_new_plane_ids_and_explicit_z(self):
        far_obstacle = dict(x=5.0, y=5.0, z=0.02, route_id=999,
                            role='debug')
        fake_lead = {9999: _candidate_lead_line((0.5, 0.5), (1.5, 0.5))}
        layers = OrderedDict()
        for index, (plane_id, z_mm) in enumerate(
                ((1001, 0.0), (1002, 0.5), (20, -0.05))):
            layers[plane_id] = dict(
                layer_id=plane_id, z_mm=z_mm,
                tasks=[self._u_task(100 + index, 0.0)],
                obstacles=[dict(far_obstacle)])
        result = layer2d.route_all_layers(
            layers, out_dir=None, initial_routes={1001: fake_lead},
            log=lambda *a: None)
        self.assertEqual(sorted(result['layers']), [20, 1001, 1002])
        expected_active = {1001: 1, 1002: 0, 20: 0}  # |dz| = .02 / .48 / .07
        for plane_id, layer_result in result['layers'].items():
            stats = layer_result['stats']
            self.assertEqual(stats['layer_id'], plane_id)
            self.assertAlmostEqual(stats['z_mm'], layers[plane_id]['z_mm'],
                                   places=12)
            self.assertEqual(stats['success'], 1, layer_result['failed'])
            self.assertEqual(stats['obstacle_samples_active'],
                             expected_active[plane_id],
                             f'plane {plane_id}: z_mm was not used for the '
                             f'obstacle height filter')
            self.assertEqual(stats['initial_routes'],
                             1 if plane_id == 1001 else 0)
            self.assertNotIn(9999, layer_result['routed'])
        # an explicit z_mm must also win for a standard baseline layer id
        shifted = layer2d.route_all_layers(
            {2: dict(layer_id=2, z_mm=0.123,
                     tasks=[self._u_task(7, 0.0)], obstacles=[])},
            out_dir=None, log=lambda *a: None)
        self.assertAlmostEqual(shifted['layers'][2]['stats']['z_mm'], 0.123,
                               places=12)
        # no silent common.layer_z fallback for the new plane ids
        with self.assertRaises(KeyError):
            layer2d.route_all_layers(
                {1001: dict(layer_id=1001,
                            tasks=[self._u_task(8, 0.0)], obstacles=[])},
                out_dir=None, log=lambda *a: None)

    def test_router_is_height_agnostic(self):
        # identical empty-obstacle tasks must give identical bodies at any z
        tasks = [self._u_task(11, 0.0), self._u_task(12, 5.0)]
        first = layer2d.route_layer(1001, 0.0, tasks, obstacles=[],
                                    log=lambda *a: None)
        second = layer2d.route_layer(20, -0.05, tasks, obstacles=[],
                                     log=lambda *a: None)
        third = layer2d.route_layer(2, 0.25, tasks, obstacles=[],
                                    log=lambda *a: None)
        self.assertEqual(first['stats']['success'], len(tasks))
        for other in (second, third):
            self.assertEqual(sorted(first['routed']), sorted(other['routed']))
            for route_id in first['routed']:
                self.assertEqual(
                    json.dumps(first['routed'][route_id]['primitives'],
                               sort_keys=True),
                    json.dumps(other['routed'][route_id]['primitives'],
                               sort_keys=True))


class TestInterfacePlaneRouting(unittest.TestCase):
    """Full 2D bodies at z=0 / z=0.5 among the frozen interface leads."""

    @classmethod
    def setUpClass(cls):
        cls.rows = _build_synthetic_21_rows()
        if cls.rows is None:
            raise unittest.SkipTest('baseline assignment not available')
        cls.landings, cls.leads, cls.transitions = _synthetic_21_fanout(cls.rows)
        if cls.leads is None:
            raise unittest.SkipTest('baseline fanout_selected.json not available')

    def _tasks_for_plane(self, plane_id):
        tasks = []
        for row in self.rows:
            if row['plane_id'] != plane_id:
                continue
            pose = self.landings[row['route_id']]
            tasks.append(dict(
                route_id=row['route_id'],
                manual_group=row.get('manual_group') or '',
                relation=row.get('relation') or '',
                source_side=row.get('source_side'),
                target_side=row.get('target_side'),
                A=tuple(pose['A']), dA=tuple(pose['dA']),
                B=tuple(pose['B']), dB=tuple(pose['dB'])))
        return tasks

    def test_interface_planes_route_among_leads(self):
        expected = {1001: 52, 1002: 48}
        expected_leads = {1001: 920, 1002: 928}
        for plane_id in INTERFACE_PLANES21:
            plane_z = PLANE_Z21[plane_id]
            tasks = self._tasks_for_plane(plane_id)
            self.assertEqual(len(tasks), expected[plane_id])
            leads = self.leads[plane_id]
            self.assertEqual(len(leads), expected_leads[plane_id])
            obstacles = _interface_obstacles(self.transitions, plane_z)
            self.assertGreater(len(obstacles), 1000)
            result = layer2d.route_layer(
                plane_id, plane_z, tasks, obstacles=obstacles, budget=1200,
                rr_rounds=2, initial_routes=leads, log=lambda *a: None)
            stats = result['stats']
            print(f'[test] interface plane {plane_id} '
                  f'({PLANE_LABEL21[plane_id]} z={plane_z:+.1f}): '
                  f'{stats["success"]}/{stats["input"]} routed, '
                  f'{stats["failed"]} failed, leads={len(leads)}, '
                  f'obstacles={len(obstacles)}, families={stats["families"]}')
            self.assertEqual(stats['success'], len(tasks),
                             f'interface plane {plane_id}: '
                             f'{result["failed"]}')
            self.assertEqual(stats['initial_routes'], len(leads))
            task_map = {task['route_id']: task for task in tasks}
            # exact poses / R15 / board / strict D56 among the routed bodies
            assert_bodies(self, result, task_map, f'interface_{plane_id}')
            # D56 against the frozen leads: all bodies valid, crossings legal
            index = D56Index(width=0.05, gap=0.03, sagitta=0.0005,
                             min_cross_angle_deg=5.0,
                             crossing_policy='strict')
            for lead_id in sorted(leads):
                index.add(lead_id, d56_prepare(leads[lead_id]))
            crossings = 0
            for route_id in sorted(result['routed']):
                prims = result['routed'][route_id]['primitives']
                evaluation = index.evaluate(d56_prepare(prims))
                self.assertTrue(evaluation.valid,
                                f'plane {plane_id} route {route_id}: '
                                f'{evaluation.reason}')
                crossings += len(evaluation.crossings)
                index.add(route_id, d56_prepare(prims))
            print(f'[test] interface plane {plane_id}: legal crossings vs '
                  f'leads/bodies = {crossings}')
            self.assertGreater(crossings, 0,
                               'no legal transverse crossing was accepted vs '
                               'the frozen leads')


class Test21HeightRealArtifacts(unittest.TestCase):
    """Real-artifact check once the 21-height fanout run is available."""

    def test_all_21_planes_real(self):
        if not (NEW_ASSIGNMENT_CSV.is_file() and NEW_FANOUT_SELECTED.is_file()):
            self.skipTest('21-height fanout artifacts not available yet')
        try:
            from four_side_1024.fanout1024.reheight21 import model as M21
        except Exception:  # pragma: no cover - model module always present now
            M21 = None
        from four_side_1024.fanout1024 import fanout
        with open(NEW_ASSIGNMENT_CSV, encoding='utf-8-sig', newline='') as fh:
            rows = [dict(r) for r in csv.DictReader(fh)]
        for row in rows:
            row['route_id'] = int(row['route_id'])
            row['target_layer'] = int(row['target_layer'])
            row['target_z_mm'] = float(row['target_z_mm'])
        payload = json.loads(NEW_FANOUT_SELECTED.read_text(encoding='utf-8'))
        selected = {int(k): v for k, v in payload['selected'].items()}
        landings = fanout.landings(selected)
        plane_ids = list(M21.PLANE_IDS) if M21 is not None else list(PLANE_Z21)
        plane_z = ({int(pid): float(M21.plane_z(pid)) for pid in plane_ids}
                   if M21 is not None else dict(PLANE_Z21))
        row_by_id = {row['route_id']: row for row in rows}
        layers = OrderedDict()
        leads = defaultdict(dict)
        for route_id, pair in selected.items():
            direct = _truthy(pair.get('direct')) or bool(
                pair.get('source', {}).get('direct'))
            if direct:
                continue
            row = row_by_id.get(route_id)
            if M21 is not None and row is not None:
                interface_plane = int(M21.interface_plane_for(row['plane']))
            else:
                record = pair['source']
                interface_plane = 1001 if abs(
                    float(record.get('z0', 0.0))) < 1e-9 else 1002
            for role, key in (('source', route_id * 2),
                              ('target', route_id * 2 + 1)):
                record = pair[role]
                lead_part = record.get('lead_part')
                if lead_part:
                    leads[interface_plane][key] = list(
                        lead_part['primitives'])
        for row in rows:
            plane_id = int(row['target_layer'])
            pose = landings.get(row['route_id'])
            if pose is None:
                continue
            entry = layers.setdefault(plane_id, dict(
                layer_id=plane_id, z_mm=plane_z[plane_id],
                tasks=[], obstacles=[]))
            entry['tasks'].append(dict(
                route_id=row['route_id'],
                manual_group=row.get('manual_group') or '',
                relation=row.get('relation') or '',
                A=tuple(pose['A']), dA=tuple(pose['dA']),
                B=tuple(pose['B']), dB=tuple(pose['dB'])))
        for plane_id in layers:
            try:
                layers[plane_id]['obstacles'] = fanout.layer_obstacles(
                    selected, plane_id, layer_z=layers[plane_id]['z_mm'])
            except TypeError:
                layers[plane_id]['obstacles'] = fanout.layer_obstacles(
                    selected, plane_id)
        result = layer2d.route_all_layers(
            layers, out_dir=None, initial_routes=dict(leads),
            log=lambda *a: None)
        total_input = total_routed = 0
        for plane_id, layer_result in result['layers'].items():
            stats = layer_result['stats']
            total_input += stats['input']
            total_routed += stats['success']
            print(f'[test] plane {plane_id} '
                  f'({PLANE_LABEL21.get(plane_id)}) z={stats["z_mm"]:+.2f}: '
                  f'{stats["success"]}/{stats["input"]} '
                  f'failed={stats["failed"]}')
        self.assertEqual(total_input, 1024)
        self.assertGreaterEqual(total_routed, 1000)
        self.assertEqual(sorted(result['layers']), sorted(plane_ids))
        # frozen interface leads must be present and actually used (SPEC s.4)
        self.assertEqual(len(leads[1001]), 920)
        self.assertEqual(len(leads[1002]), 928)
        for plane_id in INTERFACE_PLANES21:
            layer_result = result['layers'][plane_id]
            self.assertEqual(layer_result['stats']['initial_routes'],
                             len(leads[plane_id]))
            self.assertEqual(layer_result['stats']['success'],
                             layer_result['stats']['input'],
                             f'interface plane {plane_id} not fully routed: '
                             f'{layer_result["failed"]}')


if __name__ == '__main__':
    unittest.main(verbosity=2)
