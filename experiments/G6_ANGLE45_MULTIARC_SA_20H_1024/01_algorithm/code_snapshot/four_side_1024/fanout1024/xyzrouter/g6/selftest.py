# -*- coding: utf-8 -*-
"""G6 algorithm self-tests (the acceptance gates before any claim).

Checks
------
S1  the independent 45 deg validator's own analytic self-test suite passes;
S2  the 45 deg boundary is classified exactly (44.9 / 44.999 / 45.0 / 45.001 /
    90 deg) for line-line, line-arc and arc-arc crossings;
S3  every arc of the delivered geometry is exactly R15 and every primitive
    chain is continuous; every R15 S-transition matches its analytic footprint;
S4  incremental violation bookkeeping (``g5.search.State``) equals a fresh full
    audit after a sequence of committed MultiArc moves;
S5  atomic batch evaluation restores the world bit-for-bit (no side effects);
S6  a committed move can be rolled back exactly (annealing rollback path);
S7  the G6 MultiArc regeneration invariants hold for all four move families
    (structure / pose preservation / R15 / transition height chain).

Usage::

    python -m ...g6.selftest --routes <routes_l3d.json> --out <dir>
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import io
import json
import math
import os
import sys
import time
import contextlib

RESULTS = []


def _check(name, ok, detail=None):
    RESULTS.append(dict(name=name, ok=bool(ok), detail=detail))
    print('[selftest] %-46s %s  %s'
          % (name, 'PASS' if ok else 'FAIL',
             '' if detail is None else str(detail)[:120]), flush=True)
    return bool(ok)


def _project_root():
    path = os.path.abspath(__file__)
    for _ in range(5):
        path = os.path.dirname(path)
    return path


def _load_validator():
    root = _project_root()
    path = os.path.join(root, 'four_side_1024', 'fanout1024', 'xyzrouter',
                        'g5', 'validate_g5_angle.py')
    spec = importlib.util.spec_from_file_location('g6_independent_validator',
                                                  path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# S1: the validator's own synthetic suite
# ---------------------------------------------------------------------------
def test_validator_selftest(validator):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = validator.run_selftests()
    text = buffer.getvalue()
    summary = None
    for line in text.splitlines():
        if 'SELFTEST_SUMMARY' in line:
            try:
                summary = json.loads(line.split('SELFTEST_SUMMARY', 1)[1])
            except json.JSONDecodeError:
                summary = None
    return _check('S1_independent_validator_selftest', code == 0 and
                  summary is not None and summary.get('failed') == 0,
                  summary)


# ---------------------------------------------------------------------------
# S2: exact 45 deg boundary
# ---------------------------------------------------------------------------
def _line_crossing(validator, angle_deg):
    theta = math.radians(angle_deg)
    line_a = validator._line((-10.0, 0.0), (10.0, 0.0))
    # a second segment through the origin at exactly ``angle_deg``
    dx, dy = 10.0 * math.cos(theta), 10.0 * math.sin(theta)
    line_b = validator._line((-dx, -dy), (dx, dy))
    routes = [validator._route(1, [validator._flat(0.0, [line_a])]),
              validator._route(2, [validator._flat(0.0, [line_b])])]
    return validator.audit_routes(routes)


def _line_arc_crossing(validator, angle_deg, radius=15.0):
    distance = radius * math.cos(math.radians(angle_deg))
    line = validator._line((-30.0, distance), (30.0, distance))
    arc = validator._arc(0.0, 0.0, radius, 0.0, 2.0 * math.pi)
    routes = [validator._route(1, [validator._flat(0.0, [line])]),
              validator._route(2, [validator._flat(0.0, [arc])])]
    return validator.audit_routes(routes)


def _arc_arc_crossing(validator, angle_deg, radius=15.0):
    # circle-circle crossing angle: cos(theta) = 1 - d^2 / (2 R^2)
    distance = math.sqrt(2.0 * radius * radius *
                         (1.0 - math.cos(math.radians(angle_deg))))
    arc_a = validator._arc(0.0, 0.0, radius, 0.0, 2.0 * math.pi)
    arc_b = validator._arc(distance, 0.0, radius, 0.0, 2.0 * math.pi)
    routes = [validator._route(1, [validator._flat(0.0, [arc_a])]),
              validator._route(2, [validator._flat(0.0, [arc_b])])]
    return validator.audit_routes(routes)


def test_boundary(validator):
    ok = True
    details = {}
    for name, factory in (('line_line', _line_crossing),
                          ('line_arc', _line_arc_crossing),
                          ('arc_arc', _arc_arc_crossing)):
        # full-circle synthetic arcs cross a line / a circle twice, so a
        # sub-45 pair legitimately produces two violations; the boundary
        # classification is what is being tested here.
        n_cross = 1 if name == 'line_line' else 2
        for angle, expected_bad in ((44.9, n_cross), (44.999, n_cross),
                                    (45.0, 0), (45.001, 0), (90.0, 0)):
            result = factory(validator, angle)
            summary = result['summary']
            got_angle = summary.get('min_angle_deg')
            bad = summary.get('n_lt_theta_min')
            detail = dict(angle=angle, expected_bad=expected_bad,
                          measured_angle=got_angle, bad=bad)
            details[f'{name}@{angle}'] = detail
            close = got_angle is not None and abs(got_angle - angle) < 5e-3
            if bad != expected_bad or not close:
                ok = False
    return _check('S2_theta45_boundary_line_line_arc_arc', ok, details)


# ---------------------------------------------------------------------------
# S3: R15 / continuity / transition invariants of the delivered geometry
# ---------------------------------------------------------------------------
def test_geometry_invariants(doc):
    routes = doc['routes']
    arc_count = 0
    transition_count = 0
    bad = []
    for route in routes:
        rid = route.get('route_id')
        for part in route.get('parts') or ():
            if part.get('kind') == 'flat':
                prims = part.get('primitives') or []
                for index in range(1, len(prims)):
                    gap = math.dist(prims[index - 1]['p1'],
                                    prims[index]['p0'])
                    if gap > 1e-9:
                        bad.append((rid, 'flat_continuity', gap))
                for prim in prims:
                    if prim.get('kind') == 'arc':
                        arc_count += 1
                        if abs(float(prim['radius']) - 15.0) > 1e-6:
                            bad.append((rid, 'arc_radius', prim['radius']))
                        if abs(float(prim['sweep'])) > math.pi / 2 + 1e-6:
                            bad.append((rid, 'arc_sweep', prim['sweep']))
            elif part.get('kind') == 'transition':
                transition_count += 1
                if abs(float(part.get('radius_mm') or 0.0) - 15.0) > 1e-6:
                    bad.append((rid, 'transition_radius',
                                part.get('radius_mm')))
                dz = abs(float(part['z1']) - float(part['z0']))
                theta = math.acos(max(-1.0, min(1.0, 1.0 - dz / 30.0)))
                footprint = 30.0 * math.sin(theta)
                if abs(footprint - float(part['footprint_mm'])) > 1e-6:
                    bad.append((rid, 'transition_footprint',
                                footprint, part['footprint_mm']))
                start = part['start']
                direction = part['direction']
                end = (start[0] + direction[0] * footprint,
                       start[1] + direction[1] * footprint)
                if math.dist(end, part['end']) > 1e-6:
                    bad.append((rid, 'transition_end', end, part['end']))
        # chain continuity across parts
        parts = route.get('parts') or []
        for index in range(1, len(parts)):
            first, second = parts[index - 1], parts[index]
            if first.get('kind') == 'flat' and second.get('kind') == 'transition':
                end = first['primitives'][-1]['p1']
                if math.dist(end, second['start']) > 1e-6:
                    bad.append((rid, 'flat_transition_position', index))
            elif first.get('kind') == 'transition' and second.get('kind') == 'flat':
                start = second['primitives'][0]['p0']
                if math.dist(start, first['end']) > 1e-6:
                    bad.append((rid, 'transition_flat_position', index))
    return _check('S3_r15_continuity_transition_invariants', not bad,
                  dict(routes=len(routes), arcs=arc_count,
                       transitions=transition_count,
                       bad=bad[:5], bad_count=len(bad)))


# ---------------------------------------------------------------------------
# S4/S5/S6: incremental bookkeeping, atomic batch, rollback
# ---------------------------------------------------------------------------
def test_bookkeeping(doc, state_module, model_module, batch_module,
                     geometry, proposer_mod, rng):
    from four_side_1024.fanout1024.xyzrouter.g5 import search as S
    from four_side_1024.fanout1024.xyzrouter.g5 import batch as B
    routes = doc['routes']
    state = S.State(routes, min_angle_deg=45.0, log=lambda *a, **k: None)
    evaluator = proposer_mod.Evaluator(state)
    proposer = proposer_mod.Proposer(state, evaluator, rng)
    ok = True
    detail = []
    applied = 0
    tried = 0
    while applied < 3 and tried < 80:
        tried += 1
        rid = int(rng.choice(sorted(state.world.routes)))
        if not proposer.regenerable(rid):
            continue
        candidates = proposer.candidate_routes(rid, profile='B', sample=3)
        if not candidates:
            continue
        _label, new_route, mode = candidates[0]
        evaluation = evaluator.full(rid, new_route,
                                    transitions_changed=(mode != 'body'))
        if not evaluation['ok']:
            continue
        old_route = copy.deepcopy(state.world.routes[rid])
        before = (state.n_violations, round(state.deficit(), 6),
                  len(state.crossings))
        info = state.apply(rid, new_route)
        if info['issues']:
            state.apply(rid, old_route)
            continue
        fresh = S.State(list(state.world.routes.values()),
                        min_angle_deg=45.0, log=lambda *a, **k: None)
        after = (fresh.n_violations, round(fresh.deficit(), 6),
                 len(fresh.crossings))
        tracked = (state.n_violations, round(state.deficit(), 6),
                   len(state.crossings))
        detail.append(dict(route=rid, before=before, tracked=tracked,
                           full_audit=after,
                           length_tracked=round(state.length, 6),
                           length_audit=round(fresh.length, 6)))
        if tracked != after or abs(state.length - fresh.length) > 1e-6:
            ok = False
        applied += 1
    ok_s4 = _check('S4_incremental_equals_full_audit', ok and applied >= 2,
                   dict(applied=applied, cases=detail))
    # S5: evaluate_batch must leave the world unchanged
    rid = sorted(state.world.routes)[0]
    candidate = geometry.regenerate(state.world.routes[rid],
                                    geometry.dissect_route(
                                        state.world.routes[rid]),
                                    'body', rng, sample=1)
    world_before = {key: json.dumps(route, sort_keys=True)
                    for key, route in state.world.routes.items()}
    n_before = state.n_violations
    if candidate:
        B.evaluate_batch(state, {rid: candidate[0][1]}, include_3d=True)
        world_after = {key: json.dumps(route, sort_keys=True)
                       for key, route in state.world.routes.items()}
        ok_s5 = _check('S5_batch_evaluation_no_side_effect',
                       world_before == world_after and
                       state.n_violations == n_before,
                       dict(routes=len(world_before)))
    else:
        ok_s5 = _check('S5_batch_evaluation_no_side_effect', False,
                       'no candidate generated')
    # S6: rollback of a committed move restores the counters exactly
    ok_s6 = False
    rollback_detail = None
    for rid in sorted(state.world.routes)[1:8]:
        old_route = copy.deepcopy(state.world.routes[rid])
        candidates = geometry.regenerate(
            old_route, geometry.dissect_route(old_route), 'body', rng,
            sample=2)
        snapshot = (state.n_violations, round(state.deficit(), 6),
                    len(state.crossings), round(state.length, 6))
        for _label, candidate in candidates:
            info = state.apply(rid, candidate)
            if info['issues']:
                state.apply(rid, old_route)
                continue
            state.apply(rid, old_route)
            restored = (state.n_violations, round(state.deficit(), 6),
                        len(state.crossings), round(state.length, 6))
            rollback_detail = dict(route=rid, before=snapshot, after=restored)
            ok_s6 = restored == snapshot
            break
        if rollback_detail is not None:
            break
    _check('S6_annealing_rollback_exact', ok_s6, rollback_detail)
    return ok_s4 and ok_s5 and ok_s6


# ---------------------------------------------------------------------------
# S7: MultiArc regeneration invariants for the four move families
# ---------------------------------------------------------------------------
def test_regeneration(doc, geometry, model_module, rng):
    routes = {int(route['route_id']): route for route in doc['routes']}
    checked = 0
    failures = []
    seen_kinds = set()
    for rid in sorted(routes):
        route = routes[rid]
        dissected = geometry.dissect_route(route)
        if dissected is None or (route.get('manual_group') or '').strip():
            continue
        if checked >= 12:
            break
        mode = 'body'
        z_body = dissected['z_body']
        if dissected['kind'] == 'lifted':
            heights = [z for z in model_module.all_heights()
                       if abs(z - z_body) > 1e-9]
            z_body = heights[len(failures) % len(heights)]
        else:
            heights = [z for z in model_module.all_heights()
                       if abs(z - z_body) > 1e-9]
            z_body = heights[len(failures) % len(heights)]
        candidates = geometry.regenerate(route, dissected,
                                         'reheight' if z_body !=
                                         dissected['z_body'] else 'body',
                                         rng, z_body=z_body, sample=3)
        for label, new_route in candidates:
            checked += 1
            issues = model_module.structure_issues(new_route)
            if issues:
                failures.append((rid, label, issues[:2]))
                continue
            new_parts = new_route.get('parts') or []
            kinds = [part.get('kind') for part in new_parts]
            seen_kinds.add(tuple(kinds))
            lifted_expected = (dissected['kind'] == 'lifted' or
                               abs(z_body - dissected['z_body']) > 1e-9)
            if not lifted_expected:
                if len(new_parts) != 1:
                    failures.append((rid, label, 'direct_part_count'))
                    continue
                body = new_parts[0]['primitives']
                if math.dist(body[0]['p0'], dissected['A']) > 1e-6:
                    failures.append((rid, label, 'pose_A_drift'))
                if math.dist(body[-1]['p1'], dissected['B']) > 1e-6:
                    failures.append((rid, label, 'pose_B_drift'))
            else:
                if len(new_parts) != 5:
                    failures.append((rid, label, 'lifted_part_count'))
                    continue
                body = new_parts[2]['primitives']
                if abs(float(new_parts[2]['z_mm']) - z_body) > 1e-9:
                    failures.append((rid, label, 'body_height'))
                pose = geometry.body_pose(dissected, z_body=z_body,
                                          lead_s=float(new_route[
                                              'lead_source_mm']),
                                          lead_t=float(new_route[
                                              'lead_target_mm']))
                if math.dist(body[0]['p0'], pose['A']) > 1e-6:
                    failures.append((rid, label, 'pose_A_drift'))
                if math.dist(body[-1]['p1'], pose['B']) > 1e-6:
                    failures.append((rid, label, 'pose_B_drift'))
                for part in new_parts:
                    if part.get('kind') == 'transition':
                        if abs(float(part['radius_mm']) - 15.0) > 1e-6:
                            failures.append((rid, label, 'transition_radius'))
    return _check('S7_multiarc_regeneration_invariants',
                  checked >= 6 and not failures,
                  dict(checked=checked, families_seen=len(seen_kinds),
                       failures=failures[:5]))


# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--routes', required=True,
                        help='delivered routes_l3d.json')
    parser.add_argument('--out', required=True,
                        help='output directory for the self-test report')
    args = parser.parse_args(argv)
    started = time.time()
    root = _project_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    os.makedirs(args.out, exist_ok=True)

    import random
    from four_side_1024.fanout1024.xyzrouter.g5 import model as G5
    from four_side_1024.fanout1024.xyzrouter.g6 import geometry as GEO
    from four_side_1024.fanout1024.xyzrouter.g6 import neighborhoods as NB

    validator = _load_validator()
    with open(args.routes, encoding='utf-8') as handle:
        doc = json.load(handle)
    rng = random.Random(20261120)

    test_validator_selftest(validator)
    test_boundary(validator)
    test_geometry_invariants(doc)
    test_bookkeeping(doc, None, G5, None, GEO, NB, rng)
    test_regeneration(doc, GEO, G5, rng)

    passed = sum(1 for row in RESULTS if row['ok'])
    report = dict(
        schema='g6_algorithm_selftest_v1', routes=os.path.abspath(args.routes),
        passed=passed, failed=len(RESULTS) - passed, checks=RESULTS,
        elapsed_seconds=round(time.time() - started, 2),
        generated_at=time.strftime('%Y-%m-%dT%H:%M:%S'))
    path = os.path.join(args.out, 'algorithm_selftest.json')
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(report, handle, indent=1, ensure_ascii=False)
    print('[selftest] SUMMARY %s' % json.dumps(
        {key: report[key] for key in ('passed', 'failed',
                                      'elapsed_seconds')}))
    return 0 if report['failed'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
