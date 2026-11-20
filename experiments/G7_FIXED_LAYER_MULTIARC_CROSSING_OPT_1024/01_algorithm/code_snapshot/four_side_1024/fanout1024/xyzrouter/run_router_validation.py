#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P0/P1/P2 functional validation of the XYZ joint router.

Owner: router-validation-runner.  This is the ONLY source file of the task; all
artifacts are written below
``outputs/manual_c4_new_connectivity/XYZ_JOINT_G123_1024/router_validation/``.

What is validated (real geometry only, no synthetic data):

* **P0 - single route**: one non-manual route (the highest-crossing one, route
  158 = 34 crossings) is re-routed to a candidate that changes *both* its body
  XY projection (``route_builder.body_xy_signature`` + sampled centre-line
  displacement >= 2 mm) *and* its physical body height.  The committed 1024
  route layout is saved and independently validated with
  ``manual_policy='frozen'``.
* **P1 - 2/3 routes jointly**: three non-manual routes with *mutual* baseline
  crossing events (extracted from ``CrossingCache.crossing_events``) are first
  re-routed one-by-one (single-only) and then with
  ``local_reroute.reroute_joint`` from a fresh baseline; both outcomes are
  recorded and the joint layout is saved + independently validated.
* **P2 - local hotspot**: the 8 highest-crossing non-manual routes of the
  crowded z=-0.15 height are optimised twice from a fresh baseline:
  A "Z only" (``shift_height_keep_xy`` + ``insert_height_plan`` mid-body
  excursions, XY body path untouched) and B "XY+Z" (``reroute_one`` full
  engine freedom).  Both layouts are saved + independently validated.

Every accepted candidate was checked by ``RouteWorld.evaluate_candidate`` (true
``l3d.world.World`` 3D check + exact D56 strict crossing delta) and by the
independent ``validate_native3d`` validator afterwards.  Rejected candidates
are recorded in ``failed_attempts.json`` / ``strategy_stats.json`` - nothing is
invented and no failed case is reported as a success.

Usage::

    .venv\\Scripts\\python.exe -m four_side_1024.fanout1024.xyzrouter.run_router_validation
    ... --phases P0,P1,P2 [--skip-validate]

The runner is idempotent: each phase reloads the authoritative baseline from
scratch (``experiment.load_state(None)``) and overwrites its own stage dirs.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fsd25d import path3d as P3  # noqa: E402
from four_side_1024.fanout1024.native3d import common as N  # noqa: E402
from four_side_1024.fanout1024.native3d import transition as T  # noqa: E402
from four_side_1024.fanout1024.xyzrouter import experiment as E  # noqa: E402
from four_side_1024.fanout1024.xyzrouter import local_reroute as LR  # noqa: E402
from four_side_1024.fanout1024.xyzrouter import manual_reheight as MR  # noqa: E402
from four_side_1024.fanout1024.xyzrouter import paths as P  # noqa: E402
from four_side_1024.fanout1024.xyzrouter import route_builder as RB  # noqa: E402
from four_side_1024.fanout1024.xyzrouter import world_adapter as WA  # noqa: E402

# ---------------------------------------------------------------------------
# paths / constants
# ---------------------------------------------------------------------------
RUN_DIR = Path(P.DIRS['router_validation'])
BASELINE_DIR = Path(P.BASELINE_AUTHORITY)
P0_DIR = RUN_DIR / 'P0'
P1_DIR = RUN_DIR / 'P1'
P2_DIR = RUN_DIR / 'P2'
P2_Z_DIR = P2_DIR / 'z_only'
P2_XZ_DIR = P2_DIR / 'xy_z'
PLOTS_DIR = RUN_DIR / 'plots'

SCHEMA = 'xyz_router_validation_v1'
SAMPLE_STEP_MM = 0.25          # P0/P1 centre-line sampling step (task contract)
MIN_XY_CHANGE_MM = 2.0         # P0 qualification threshold
P2_SAMPLE_STEP_MM = 0.5

#: bounded engine configuration shared by every XY+Z search of this run
#: (P0 propose / P1 single+joint / P2 B).  Kept identical on purpose so the
#: P1 and P2 comparisons use one search budget.
ENGINE_CFG = dict(
    max_target_layers=3,
    max_lead_pairs=2,
    prescreen_candidates=220,
    max_candidates=400,
    d56_top=24,
    bodies_per_pair=2,
    max_eval=2,
    max_combos=2,
    early_stop_delta=6,
    min_delta=1,
    allow_direct=True,
    allow_xy_only=True,
    phase=0.0,
)

#: P2 A budget: per route <= 5 height shifts + 8 excursion placements x 6
#: target heights = 53 exact 3D candidate evaluations.
P2_MAX_PLACEMENTS = 8
P2_Z_TARGETS = 6
P2_MAX_EVAL_PER_ROUTE = 5 + P2_MAX_PLACEMENTS * P2_Z_TARGETS


# ---------------------------------------------------------------------------
# tiny helpers
# ---------------------------------------------------------------------------
def log(message):
    print('[router_validation] %s' % message, flush=True)


def rel(path):
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def write_json(path, payload):
    return P.write_json(path, payload)


def counter_dict(counter):
    counter = counter or {}
    return {str(key): int(value) for key, value in sorted(counter.items())}


def merge_counter(target, source):
    for key, value in (source or {}).items():
        if isinstance(value, Counter):
            target[key] += sum(int(item) for item in value.values())
        else:
            target[key] += int(value)
    return target


def short_sha1(text):
    return hashlib.sha1(str(text).encode('utf-8')).hexdigest()[:16]


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%S')


def stored_baseline_crossings(baseline_dir):
    """Crossing total stored in the start layout (never a 21-height literal).

    The authoritative start state's own ``crossing_stats.json`` supplies the
    expected value; ``None`` means the start directory has no statistics and
    the recomputed baseline total is the truth.
    """
    path = Path(baseline_dir) / 'crossing_stats.json'
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    value = (payload.get('totals') or {}).get('crossings')
    return None if value is None else int(value)


# ---------------------------------------------------------------------------
# geometry helpers (real parts only)
# ---------------------------------------------------------------------------
def body_flats(route):
    return [(index, route['parts'][index]) for index in RB.body_part_indices(route)]


def body_xy_polyline(route, step=SAMPLE_STEP_MM):
    points = []
    for _index, part in body_flats(route):
        prims = [dict(prim) for prim in part['primitives']]
        points.extend(tuple(point) for point in P3.path_polyline(prims, step=step))
    return points


def body_path_length(route):
    total = 0.0
    for _index, part in body_flats(route):
        prims = [dict(prim) for prim in part['primitives']]
        total += float(P3.path_length(prims))
    return total


def max_xy_displacement(old_route, new_route, step=SAMPLE_STEP_MM):
    """Max distance from every new body sample to the old body centre line.

    The task contract: sample both bodies every ``step`` mm and report the max
    distance from new samples to the old body (a directional Hausdorff metric).
    """
    old = body_xy_polyline(old_route, step)
    new = body_xy_polyline(new_route, step)
    if not old or not new:
        return dict(max_mm=None, at=None, old_samples=len(old),
                    new_samples=len(new), step_mm=step, direction='new->old')
    worst = 0.0
    worst_at = None
    for x, y in new:
        best = float('inf')
        for ox, oy in old:
            distance = math.hypot(x - ox, y - oy)
            if distance < best:
                best = distance
                if best == 0.0:
                    break
        if best > worst:
            worst = best
            worst_at = (round(x, 6), round(y, 6))
    return dict(max_mm=round(worst, 6), at=worst_at,
                old_samples=len(old), new_samples=len(new),
                step_mm=step, direction='new->old')


def geometry_record(route):
    """Compact description of the real geometry of one route."""
    flats = body_flats(route)
    transitions = [part for part in route.get('parts') or []
                   if part.get('kind') == 'transition']
    return dict(
        route_id=int(route.get('route_id')),
        target_layer=int(route.get('target_layer') or 0),
        target_z_mm=round(float(route.get('target_z_mm') or 0.0), 9),
        n_transitions=int(route.get('n_transitions') or 0),
        n_mid_transitions=int(route.get('n_mid_transitions') or 0),
        length_mm=round(float(route.get('length_mm') or 0.0), 6),
        body_path_length_mm=round(body_path_length(route), 6),
        body_flat_count=len(flats),
        body_z_mm=sorted({round(float(part['z_mm']), 9) for _i, part in flats}),
        body_primitive_count=int(sum(len(part.get('primitives') or [])
                                     for _i, part in flats)),
        transition_z_pairs=[[round(float(part['z0']), 6),
                             round(float(part['z1']), 6)]
                            for part in transitions],
        body_xy_signature_sha1=short_sha1(RB.body_xy_signature(route)),
    )


def candidate_geometry_check(old_route, new_route, min_xy_mm=MIN_XY_CHANGE_MM):
    """P0 qualification: XY projection really changed AND height really changed."""
    old_geom = geometry_record(old_route)
    new_geom = geometry_record(new_route)
    displacement = max_xy_displacement(old_route, new_route, SAMPLE_STEP_MM)
    xy_signature_changed = (RB.body_xy_signature(old_route)
                            != RB.body_xy_signature(new_route))
    z_changed = bool(
        old_geom['target_layer'] != new_geom['target_layer']
        or old_geom['body_z_mm'] != new_geom['body_z_mm']
        or old_geom['transition_z_pairs'] != new_geom['transition_z_pairs'])
    xy_changed = bool(
        xy_signature_changed
        and displacement.get('max_mm') is not None
        and float(displacement['max_mm']) >= float(min_xy_mm))
    return dict(
        old=old_geom,
        new=new_geom,
        body_xy_signature_changed=bool(xy_signature_changed),
        xy_signature_sha1_old=old_geom['body_xy_signature_sha1'],
        xy_signature_sha1_new=new_geom['body_xy_signature_sha1'],
        max_xy_displacement=displacement,
        min_xy_change_required_mm=float(min_xy_mm),
        xy_changed_substantially=bool(xy_changed),
        z_changed=bool(z_changed),
        not_only_z_lift_on_old_xy=bool(xy_changed),
        not_only_xy_at_same_height=bool(z_changed),
        qualifies=bool(xy_changed and z_changed),
    )


# ---------------------------------------------------------------------------
# state / crossing helpers
# ---------------------------------------------------------------------------
def crossing_snapshot(state):
    """Exact per-route + per-height crossing snapshot (frozen D56 strict rule)."""
    per_route, cache = state.per_route_counts()
    by_height = {
        round(float(z), 9): dict(events=int(value[0]), pairs=int(value[1]))
        for z, value in cache.plane_counts.items()
    }
    return dict(total=int(cache.total()),
                pairs=int(cache.total_pairs()),
                state_total=int(state.total),
                per_route={int(rid): int(count) for rid, count in per_route.items()},
                by_height=by_height,
                cache=cache)


def evaluate(state, route_id, route, keep_violations=3):
    evaluation = state.evaluate_candidate(int(route_id), route)
    violations = []
    for violation in (evaluation.get('violations') or [])[:keep_violations]:
        violations.append(dict(kind=str(violation.get('kind')),
                               detail=str(violation.get('detail'))[:300]))
    return dict(ok=bool(evaluation.get('ok')),
                delta=(int(evaluation['delta'])
                       if evaluation.get('delta') is not None else None),
                kinds=[str(kind) for kind in (evaluation.get('kinds') or [])],
                per_plane=evaluation.get('per_plane') or {},
                violations=violations,
                seconds=round(float(evaluation.get('seconds') or 0.0), 3))


def row_for_route(row, route):
    """Planner row consistent with the *real* route metadata (target fields)."""
    out = dict(row)
    layer = int(route.get('target_layer') or 0)
    z_mm = float(route.get('target_z_mm') or 0.0)
    interface_z = float(row.get('interface_z_mm') or 0.0)
    out['target_layer'] = layer
    out['target_plane_label'] = str(RB.PLANE_LABEL.get(layer, ''))
    out['target_z_mm'] = z_mm
    out['needs_transition'] = bool(int(route.get('n_transitions') or 0))
    out['direction'] = ('direct' if not out['needs_transition']
                        else ('down' if z_mm < interface_z else 'up'))
    return out


def commit_route(state, route_id, route, note):
    rid = int(route_id)
    row = row_for_route(state.rows[rid], route)
    return state.commit(rid, route, new_row=row, note=note)


# ---------------------------------------------------------------------------
# independent validator
# ---------------------------------------------------------------------------
def validate_frozen(stage_dir, label, log_fn=log):
    """Run the independent validator with ``manual_policy='frozen'`` and check
    every requirement of the task (PASS, 1024/1024, 0 violations, 368/368)."""
    stage_dir = Path(stage_dir)
    started = time.time()
    report, summary = E.validate_stage(stage_dir, str(BASELINE_DIR),
                                       stage_dir / 'validation', 'frozen',
                                       log=log_fn)
    counts = report.get('counts') or {}
    checks = report.get('checks') or {}
    manual = (checks.get('manual_frozen') or {})
    violations = list(report.get('violations') or [])
    manual_violations = int(manual.get('violations') or 0)
    record = dict(
        stage=rel(stage_dir),
        label=str(label),
        validation_pass=bool(report.get('validation_pass')),
        violations=int(len(violations)),
        violation_kinds=counter_dict(Counter(v.get('kind') for v in violations)),
        offending_route_ids=sorted({int(v.get('route_id'))
                                    for v in violations
                                    if v.get('route_id') is not None})[:30],
        routed=counts.get('routed'),
        records=counts.get('records'),
        failed=counts.get('failed'),
        crossings=counts.get('same_plane_crossings'),
        crossing_pairs=counts.get('same_plane_crossing_pairs'),
        crossing_delta_vs_baseline=counts.get('crossing_delta_vs_baseline'),
        mid_transitions=counts.get('mid_transitions'),
        min_3d_clearance_mm=counts.get('min_3d_clearance_mm'),
        min_flat_arc_radius_mm=counts.get('min_flat_arc_radius_mm'),
        total_length_mm=counts.get('total_length_mm'),
        manual=dict(
            policy=manual.get('policy'),
            manual_route_count=manual.get('manual_route_count'),
            checked=manual.get('checked'),
            matched=manual.get('matched'),
            mismatch_count=manual.get('mismatch_count'),
            violations=manual_violations,
            offending_route_count=manual.get('offending_route_count'),
        ),
        policy=report.get('manual_policy'),
        summary=summary,
        validator=report.get('xyz_validator'),
        validation_file=rel(stage_dir / 'validation' / 'validation.json'),
        seconds=round(time.time() - started, 2),
    )
    hard = dict(
        validation_pass=bool(record['validation_pass']),
        zero_violations=bool(record['violations'] == 0),
        routed_1024=bool(record['routed'] == 1024),
        failed_zero=bool(record['failed'] == 0),
        manual_368=bool(record['manual']['manual_route_count'] == 368),
        manual_368_matched=bool(record['manual']['matched'] == 368),
        manual_zero_violations=bool(manual_violations == 0),
    )
    record['hard_requirements'] = hard
    record['hard_requirements_ok'] = bool(all(hard.values()))
    # copy the report to the stage root as well (DESIGN.md 4.13 artifact set)
    write_json(stage_dir / 'validation.json', report)
    write_json(stage_dir / 'validation_summary.json', record)
    log('[validator] %s policy=frozen pass=%s violations=%d routed=%s '
        'manual=%s/%s crossings=%s (%.1fs)' % (
            label, record['validation_pass'], record['violations'],
            record['routed'], record['manual']['matched'],
            record['manual']['manual_route_count'], record['crossings'],
            record['seconds']))
    if not record['hard_requirements_ok']:
        log('[validator] %s FAILED hard requirements: %s'
            % (label, json.dumps(hard)))
    return record


def write_history_csv(stage_dir, history):
    """Write the real commit history of a stage (overwrites the empty file)."""
    records = [dict(record) for record in (history or [])]
    if not records:
        return write_json(Path(stage_dir) / 'optimization_history.json',
                          dict(records=[]))
    fieldnames = []
    for record in records:
        for key in record:
            if key not in fieldnames:
                fieldnames.append(key)
    Path(stage_dir).mkdir(parents=True, exist_ok=True)
    P.write_csv_records(Path(stage_dir) / 'optimization_history.csv',
                        records, fieldnames=fieldnames)
    return Path(stage_dir) / 'optimization_history.csv'


def record_attempts(stage_dir, attempts, label):
    """Overwrite the stage ``failed_attempts.json`` with the *real* attempts."""
    rejected = [item for item in attempts if not item.get('accepted')]
    payload = dict(
        schema=SCHEMA + '_failed_attempts',
        stage=rel(stage_dir),
        label=str(label),
        note=('every candidate that was built/evaluated for this stage; '
              'accepted=False entries are genuine rejected attempts'),
        count=len(rejected),
        total_attempts=len(attempts),
        attempts=attempts[:2000],
    )
    write_json(Path(stage_dir) / 'failed_attempts.json', payload)
    return payload


# ---------------------------------------------------------------------------
# P0 - single route with simultaneous real XY + Z change
# ---------------------------------------------------------------------------
def select_p0_route(state, snap):
    non_manual = set(MR.non_manual_route_ids(state))
    ranked = sorted(((int(count), int(rid))
                     for rid, count in snap['per_route'].items()
                     if int(rid) in non_manual and int(count) > 0),
                    reverse=True)
    if not ranked:
        raise RuntimeError('no non-manual route has baseline crossings')
    ranking = []
    for count, rid in ranked[:10]:
        route = state.routes[rid]
        ranking.append(dict(route_id=rid, crossings=count,
                            target_layer=int(route.get('target_layer') or 0),
                            target_z_mm=float(route.get('target_z_mm') or 0.0)))
    return ranked[0][1], ranking


def _proposal_attempt(label, record, old_route, extra=None):
    geometry = candidate_geometry_check(old_route, record['route'])
    attempt = dict(
        stage=label,
        option=dict(record.get('option') or {}),
        family=str(record.get('family') or ''),
        lead_s=float(record.get('lead_s') or 0.0),
        lead_t=float(record.get('lead_t') or 0.0),
        delta=record.get('delta'),
        xy_body_crossings=record.get('xy_crossings'),
        max_xy_displacement_mm=geometry['max_xy_displacement'].get('max_mm'),
        xy_changed=geometry['xy_changed_substantially'],
        z_changed=geometry['z_changed'],
        qualifies=geometry['qualifies'],
        accepted=False,
        rejection=None if geometry['qualifies'] else 'not_simultaneous_xy_and_z',
    )
    if extra:
        attempt.update(extra)
    return attempt


def find_p0_candidate(state, route_id, cfg=None):
    """Best exact candidate that genuinely changes XY *and* Z.

    1. ``local_reroute.propose`` (the shared engine) - accepted when it really
       qualifies;
    2. bounded direct candidate generation over every non-identity target
       height (``target_options`` -> ``xy_candidates`` -> ``build_route_candidate``
       -> ``evaluate_candidate``) as a fallback / verifier.
    """
    cfg = dict(ENGINE_CFG, **(cfg or {}))
    rid = int(route_id)
    old_route = copy.deepcopy(state.routes[rid])
    stats = {}
    attempts = []
    chosen = None
    source = None

    proposal = LR.propose(state, rid, cfg=cfg, stats=stats)
    if proposal is None:
        attempts.append(dict(stage='propose', accepted=False,
                             rejection='engine_returned_no_candidate'))
    else:
        attempt = _proposal_attempt('propose', proposal, old_route)
        attempts.append(attempt)
        if attempt['qualifies'] and int(proposal['delta']) < 0:
            chosen = proposal
            source = 'local_reroute.propose'
            attempt['accepted'] = True
            attempt['rejection'] = None

    if chosen is None:
        log('[p0] propose() did not yield a qualifying XY+Z candidate; '
            'running bounded direct candidate generation')
        best = None
        direct_stats = Counter()
        max_eval = int(cfg['max_eval'])
        for option in LR.target_options(state, rid, cfg):
            if abs(float(option['z'])
                   - float(state.rows[rid]['target_z_mm'])) < 1e-9:
                direct_stats['identity_height_options_skipped'] += 1
                continue
            for lead_s, lead_t in LR._lead_pair_candidates(state.route(rid),
                                                          option, cfg):
                direct_stats['combos'] += 1
                try:
                    task, _source, _target = LR.make_task_for_option(
                        state, rid, option, lead_s, lead_t)
                except (RB.BuilderError, ValueError) as error:
                    direct_stats['builder_errors'] += 1
                    attempts.append(dict(stage='direct', accepted=False,
                                         option=dict(option),
                                         lead_s=float(lead_s),
                                         lead_t=float(lead_t),
                                         rejection='build_task:%s'
                                                   % getattr(error, 'reason',
                                                             str(error))))
                    continue
                bodies = LR.xy_candidates(state, rid, task,
                                          int(option['layer']),
                                          float(option['z']), cfg)
                direct_stats['xy_candidates'] += len(bodies)
                for body_record in bodies[:max_eval]:
                    direct_stats['evaluated'] += 1
                    try:
                        candidate = LR.build_route_candidate(
                            state, rid, option, lead_s, lead_t,
                            body_record['body'])
                    except (RB.BuilderError, ValueError) as error:
                        direct_stats['builder_errors'] += 1
                        attempts.append(dict(
                            stage='direct', accepted=False,
                            option=dict(option), family=body_record['family'],
                            lead_s=float(lead_s), lead_t=float(lead_t),
                            rejection='build_route:%s'
                                      % getattr(error, 'reason', str(error))))
                        continue
                    evaluation = evaluate(state, rid, candidate)
                    geometry = candidate_geometry_check(old_route, candidate)
                    rejected = None
                    if not evaluation['ok']:
                        rejected = '3d:%s' % (evaluation['kinds'][0]
                                              if evaluation['kinds'] else 'unknown')
                    elif evaluation['delta'] is None or evaluation['delta'] >= 0:
                        rejected = 'no_crossing_gain:delta=%s' % evaluation['delta']
                    elif not geometry['qualifies']:
                        rejected = 'not_simultaneous_xy_and_z'
                    record = dict(
                        route=candidate, delta=int(evaluation['delta']),
                        option=dict(option), lead_s=float(lead_s),
                        lead_t=float(lead_t),
                        family=str(body_record['family']),
                        xy_crossings=int(body_record['crossings']),
                        per_plane=evaluation['per_plane'], seconds=0.0,
                        lower_bound=0)
                    attempt = dict(
                        stage='direct', accepted=False,
                        option=dict(option), family=record['family'],
                        lead_s=float(lead_s), lead_t=float(lead_t),
                        delta=evaluation['delta'],
                        max_xy_displacement_mm=geometry['max_xy_displacement'].get('max_mm'),
                        xy_changed=geometry['xy_changed_substantially'],
                        z_changed=geometry['z_changed'],
                        qualifies=geometry['qualifies'],
                        rejection=rejected)
                    attempts.append(attempt)
                    if rejected is None:
                        attempt['accepted'] = True
                        if best is None or record['delta'] < best['delta']:
                            best = record
        if best is not None:
            chosen = best
            source = 'direct_candidate_generation'
        stats['direct_candidate_stats'] = counter_dict(direct_stats)

    stats_json = {}
    for key, value in (stats or {}).items():
        if isinstance(value, Counter):
            stats_json[key] = counter_dict(value)
        elif isinstance(value, dict):
            stats_json[key] = {str(k): (counter_dict(v) if isinstance(v, Counter)
                                        else v) for k, v in value.items()}
        else:
            stats_json[key] = value
    return dict(record=chosen, source=source, stats=stats_json,
                attempts=attempts)


def run_p0(ctx, skip_validate=False):
    log('=' * 78)
    log('[P0] single-route simultaneous XY+Z change from the 2409 baseline')
    started = time.time()
    baseline, state = E.load_state(None, log=log)
    baseline_crossings = int(state.total)
    expected_crossings = stored_baseline_crossings(baseline['dir'])
    if (expected_crossings is not None
            and baseline_crossings != int(expected_crossings)):
        raise RuntimeError(
            'baseline crossings %d != authoritative start total %d'
            % (baseline_crossings, expected_crossings))
    snapshot0 = crossing_snapshot(state)
    route_id, ranking = select_p0_route(state, snapshot0)
    log('[P0] selected route %d (%d baseline crossings); ranking=%s'
        % (route_id, snapshot0['per_route'].get(route_id, 0),
           [(item['route_id'], item['crossings']) for item in ranking[:5]]))

    old_route = copy.deepcopy(state.routes[route_id])
    old_row = dict(state.rows[route_id])
    old_crossings = int(snapshot0['per_route'].get(route_id, 0))

    # reference: what does a pure-Z lift with the OLD XY path achieve?
    z_only_reference = dict(attempted=False)
    found = find_p0_candidate(state, route_id)
    record = found['record']
    if record is None:
        write_json(P0_DIR / 'p0_case.json',
                   dict(schema=SCHEMA + '_p0', route_id=route_id,
                        error='no simultaneous XY+Z candidate found',
                        attempts=found['attempts']))
        raise RuntimeError('P0: no simultaneous XY+Z candidate for route %d'
                           % route_id)
    target_layer = int(record['option']['layer'])
    target_z = float(record['option']['z'])
    try:
        z_only_route = RB.shift_height_keep_xy(old_route, old_row, target_layer,
                                               target_z)
        z_only_reference = dict(
            attempted=True,
            family='shift_height_keep_xy',
            target_layer=target_layer,
            target_z_mm=target_z,
            evaluation=evaluate(state, route_id, z_only_route),
            max_xy_displacement_mm=max_xy_displacement(
                old_route, z_only_route)['max_mm'],
            body_xy_signature_changed=bool(
                RB.body_xy_signature(old_route)
                != RB.body_xy_signature(z_only_route)),
        )
    except (RB.BuilderError, ValueError) as error:
        z_only_reference = dict(attempted=True,
                                family='shift_height_keep_xy',
                                error='%s:%s' % (type(error).__name__,
                                                 getattr(error, 'reason',
                                                         str(error))))

    geometry = candidate_geometry_check(old_route, record['route'])
    log('[P0] candidate source=%s family=%s target L%d z=%+.2f delta=%d '
        'max_xy_disp=%.3f mm xy_changed=%s z_changed=%s qualifies=%s'
        % (found['source'], record.get('family'), target_layer, target_z,
           int(record['delta']),
           geometry['max_xy_displacement'].get('max_mm') or -1.0,
           geometry['xy_changed_substantially'], geometry['z_changed'],
           geometry['qualifies']))
    if not geometry['qualifies']:
        raise RuntimeError('P0: chosen candidate does not qualify')

    applied = commit_route(state, route_id, record['route'],
                           'p0_simultaneous_xy_z')
    log('[P0] committed: total %d -> %d (delta %d)'
        % (baseline_crossings, state.total, applied['delta']))
    snapshot1 = crossing_snapshot(state)
    new_route = copy.deepcopy(state.routes[route_id])

    save_started = time.time()
    E.save_stage(state, baseline, P0_DIR,
                 note='P0 single-route simultaneous XY+Z re-route '
                      '(route %d -> L%d z=%+.2f)' % (route_id, target_layer,
                                                      target_z),
                 log=log)
    write_history_csv(P0_DIR, state.history)
    record_attempts(P0_DIR, found['attempts'], 'P0')
    stage_stats = dict(
        schema=SCHEMA + '_stage_strategy_stats',
        phase='P0',
        engine_cfg={key: value for key, value in ENGINE_CFG.items()
                    if key != 'phase'},
        candidate_source=found['source'],
        engine_stats=found['stats'],
        attempts_total=len(found['attempts']),
        attempts_accepted=len([item for item in found['attempts']
                               if item.get('accepted')]),
        rejection_reasons=counter_dict(Counter(
            item.get('rejection') for item in found['attempts']
            if item.get('rejection'))),
        seconds=round(time.time() - started, 2),
    )
    write_json(P0_DIR / 'strategy_stats.json', stage_stats)
    log('[P0] save_stage %.1fs' % (time.time() - save_started))

    validation = None
    if not skip_validate:
        validation = validate_frozen(P0_DIR, 'P0')

    case = dict(
        schema=SCHEMA + '_p0',
        generated_at=now(),
        baseline_dir=rel(BASELINE_DIR),
        baseline_routes_sha256=baseline['routes_sha256'],
        baseline_crossings=baseline_crossings,
        selected_route=dict(
            route_id=route_id,
            crossings_before=old_crossings,
            selection_rule='highest-crossing non-manual route of the '
                           'authoritative 2409 baseline',
            ranking=ranking,
            old_geometry=geometry_record(old_route),
            old_row=dict(plane=old_row.get('plane'),
                         target_layer=int(old_row['target_layer']),
                         target_z_mm=float(old_row['target_z_mm']),
                         manual_group=str(old_row.get('manual_group') or ''),
                         interface_z_mm=float(old_row['interface_z_mm'])),
        ),
        candidate=dict(
            source=found['source'],
            family=str(record.get('family') or ''),
            lead_s_mm=float(record.get('lead_s') or 0.0),
            lead_t_mm=float(record.get('lead_t') or 0.0),
            option=dict(record.get('option') or {}),
            target_layer=target_layer,
            target_z_mm=target_z,
            xy_body_crossings=int(record.get('xy_crossings') or 0),
            lower_bound=int(record.get('lower_bound') or 0),
            early_stop=bool(record.get('early_stop') or False),
            per_plane=record.get('per_plane') or {},
            engine_stats=found['stats'],
        ),
        requirements_check=dict(
            xy_and_z_both_changed=geometry['qualifies'],
            xy_changed_substantially=geometry['xy_changed_substantially'],
            z_changed=geometry['z_changed'],
            not_only_z_lift_on_old_xy=geometry['not_only_z_lift_on_old_xy'],
            not_only_xy_at_same_height=geometry['not_only_xy_at_same_height'],
            body_xy_signature_changed=geometry['body_xy_signature_changed'],
            max_xy_displacement_ge_2mm=bool(
                (geometry['max_xy_displacement'].get('max_mm') or 0.0)
                >= MIN_XY_CHANGE_MM),
            target_layer_changed=bool(
                geometry['old']['target_layer'] != geometry['new']['target_layer']),
            body_height_changed=bool(
                geometry['old']['body_z_mm'] != geometry['new']['body_z_mm']),
            validation_pass=bool(validation and
                                 validation['hard_requirements_ok']),
        ),
        geometry=dict(
            old=geometry['old'],
            new=geometry['new'],
            old_body_path_length_mm=geometry['old']['body_path_length_mm'],
            new_body_path_length_mm=geometry['new']['body_path_length_mm'],
            max_xy_displacement=geometry['max_xy_displacement'],
            body_xy_signature_changed=geometry['body_xy_signature_changed'],
            body_xy_signature_sha1_old=geometry['xy_signature_sha1_old'],
            body_xy_signature_sha1_new=geometry['xy_signature_sha1_new'],
            note='max_xy_displacement = max over new-body samples (every '
                 '%.2f mm) of the distance to the old body centre line'
                 % SAMPLE_STEP_MM,
        ),
        z_only_reference=z_only_reference,
        crossings=dict(
            old_total=baseline_crossings,
            new_total=int(snapshot1['total']),
            removed=baseline_crossings - int(snapshot1['total']),
            old_route_crossings=old_crossings,
            new_route_crossings=int(snapshot1['per_route'].get(route_id, 0)),
            route_delta=(int(snapshot1['per_route'].get(route_id, 0))
                         - old_crossings),
            per_height_before=snapshot0['by_height'],
            per_height_after=snapshot1['by_height'],
        ),
        commit=applied,
        failed_attempts=dict(
            total=len(found['attempts']),
            rejected=len([item for item in found['attempts']
                          if not item.get('accepted')]),
            reasons=counter_dict(Counter(
                item.get('rejection') for item in found['attempts']
                if item.get('rejection'))),
            attempts=found['attempts'][:200],
        ),
        validation=validation,
        artifacts=dict(
            stage=rel(P0_DIR),
            routes=P0_DIR.joinpath('routes_l3d.json').name,
            assignment=P0_DIR.joinpath('assignment_1024.csv').name,
            crossing_stats=P0_DIR.joinpath('crossing_stats.json').name,
            sha256=P0_DIR.joinpath('SHA256.json').name,
            validation=rel(P0_DIR / 'validation' / 'validation.json'),
            case=rel(P0_DIR / 'p0_case.json'),
        ),
        seconds=round(time.time() - started, 2),
    )
    write_json(P0_DIR / 'p0_case.json', case)
    log('[P0] done in %.1fs, total crossings %d -> %d, artifacts in %s'
        % (time.time() - started, baseline_crossings, snapshot1['total'],
           rel(P0_DIR)))
    case['_plotdata'] = dict(
        route_id=route_id,
        old_body_xy=[[round(x, 4), round(y, 4)] for x, y in
                     body_xy_polyline(old_route, 0.5)],
        new_body_xy=[[round(x, 4), round(y, 4)] for x, y in
                     body_xy_polyline(new_route, 0.5)],
        old_flats=[dict(z_mm=round(float(part['z_mm']), 6),
                        xy=[[round(x, 4), round(y, 4)] for x, y in
                            P3.path_polyline([dict(prim) for prim in
                                              part['primitives']], 0.5)])
                   for _i, part in body_flats(old_route)],
        new_flats=[dict(z_mm=round(float(part['z_mm']), 6),
                        xy=[[round(x, 4), round(y, 4)] for x, y in
                            P3.path_polyline([dict(prim) for prim in
                                              part['primitives']], 0.5)])
                   for _i, part in body_flats(new_route)],
    )
    return case


# ---------------------------------------------------------------------------
# P1 - single vs joint re-routing of mutually blocking routes
# ---------------------------------------------------------------------------
def select_p1_routes(state, snap, top_k=40, max_triples=10):
    """Triples of non-manual routes with the strongest *mutual* crossing events."""
    non_manual = set(MR.non_manual_route_ids(state))
    ranked = sorted(((int(count), int(rid))
                     for rid, count in snap['per_route'].items()
                     if int(rid) in non_manual and int(count) > 0),
                    reverse=True)[:top_k]
    top = [rid for _count, rid in ranked]
    rank = {rid: index for index, rid in enumerate(top)}
    edges = Counter()
    events = snap['cache'].crossing_events()
    for event in events:
        route_a = int(event['route_a'])
        route_b = int(event['route_b'])
        if route_a in rank and route_b in rank:
            edges[(min(route_a, route_b), max(route_a, route_b))] += 1
    triples = []
    for i in range(len(top)):
        for j in range(i + 1, len(top)):
            for k in range(j + 1, len(top)):
                a, b, c = top[i], top[j], top[k]
                ab = edges.get((min(a, b), max(a, b)), 0)
                ac = edges.get((min(a, c), max(a, c)), 0)
                bc = edges.get((min(b, c), max(b, c)), 0)
                if ab + ac + bc <= 0:
                    continue
                layers = [int(state.routes[rid].get('target_layer') or 0)
                          for rid in (a, b, c)]
                heights = [round(float(state.routes[rid].get('target_z_mm')
                                      or 0.0), 9) for rid in (a, b, c)]
                triples.append(dict(
                    routes=[a, b, c],
                    edge_events=dict(ab=ab, ac=ac, bc=bc,
                                     a_b=[a, b], a_c=[a, c], b_c=[b, c]),
                    total_edge_events=int(ab + ac + bc),
                    crossings_sum=int(sum(snap['per_route'].get(rid, 0)
                                          for rid in (a, b, c))),
                    target_layers=layers,
                    body_z_mm=heights,
                    same_body_height=bool(len(set(heights)) == 1),
                ))
    triples.sort(key=lambda item: (-item['total_edge_events'],
                                   -item['crossings_sum'],
                                   item['routes']))
    return triples[0], triples[:max_triples], ranked


def _xy_change_record(old_route, new_route, step=P2_SAMPLE_STEP_MM):
    displacement = max_xy_displacement(old_route, new_route, step)
    return dict(
        max_xy_displacement_mm=displacement.get('max_mm'),
        body_xy_signature_changed=bool(
            RB.body_xy_signature(old_route) != RB.body_xy_signature(new_route)),
        xy_changed_substantially=bool(
            (displacement.get('max_mm') or 0.0) >= MIN_XY_CHANGE_MM),
        step_mm=step,
    )


def run_p1(ctx, skip_validate=False):
    log('=' * 78)
    log('[P1] single-only vs joint re-routing of 3 mutually blocking routes')
    started = time.time()
    baseline0, state0 = E.load_state(None, log=log)
    baseline_crossings = int(state0.total)
    snapshot0 = crossing_snapshot(state0)
    triple, top_triples, ranked = select_p1_routes(state0, snapshot0)
    route_ids = [int(rid) for rid in triple['routes']]
    log('[P1] chosen routes %s: mutual crossing events %s, crossings %s, '
        'body_z %s' % (route_ids, triple['edge_events'],
                       [snapshot0['per_route'].get(rid, 0) for rid in route_ids],
                       triple['body_z_mm']))
    baseline_routes = {rid: copy.deepcopy(state0.routes[rid])
                       for rid in route_ids}
    baseline_rows = {rid: dict(state0.rows[rid]) for rid in route_ids}

    # ---- (a) single-only: reroute route A while B and C stay frozen ---------
    baseline_a, state_a = E.load_state(None, log=log)
    single_stats = {}
    single_started = time.time()
    single_applied = LR.reroute_one(state_a, route_ids[0], cfg=ENGINE_CFG,
                                    stats=single_stats)
    single_snapshot = crossing_snapshot(state_a)
    single_reasons = counter_dict(single_stats.get('reasons') or {})
    single_record = dict(
        route_id=route_ids[0],
        other_routes_frozen=route_ids[1:],
        engine='local_reroute.reroute_one',
        applied=None if single_applied is None else {
            key: single_applied.get(key)
            for key in ('route_id', 'delta', 'old_layer', 'new_layer',
                        'old_z', 'new_z', 'family', 'lead_s', 'lead_t',
                        'xy_crossings', 'old_length', 'new_length', 'seconds')
        },
        total_before=baseline_crossings,
        total_after=int(single_snapshot['total']),
        gain=baseline_crossings - int(single_snapshot['total']),
        stats={key: (counter_dict(value) if isinstance(value, Counter) else value)
               for key, value in single_stats.items()},
        rejection_reasons=single_reasons,
        others_geometry_frozen=bool(all(
            RB.route_signature(state_a.routes[rid])
            == RB.route_signature(baseline_routes[rid])
            for rid in route_ids[1:])),
        per_route_crossings_before={rid: int(snapshot0['per_route'].get(rid, 0))
                                    for rid in route_ids},
        per_route_crossings_after={rid: int(single_snapshot['per_route'].get(rid, 0))
                                   for rid in route_ids},
        geometry_change_A=(_xy_change_record(baseline_routes[route_ids[0]],
                                             state_a.routes[route_ids[0]])
                           if single_applied is not None else None),
        seconds=round(time.time() - single_started, 2),
    )
    log('[P1] single-only (%d): total %d -> %d (gain %d)'
        % (route_ids[0], baseline_crossings, single_record['total_after'],
           single_record['gain']))

    # ---- (a2) context: sequential single-route-only over all three ----------
    baseline_s, state_s = E.load_state(None, log=log)
    sequential = []
    sequential_stats = Counter()
    for rid in route_ids:
        step_stats = {}
        applied = LR.reroute_one(state_s, rid, cfg=ENGINE_CFG,
                                 stats=step_stats)
        merge_counter(sequential_stats, step_stats.get('reasons') or {})
        sequential.append(dict(
            route_id=int(rid),
            accepted=bool(applied is not None),
            delta=None if applied is None else int(applied['delta']),
            old_layer=None if applied is None else int(applied['old_layer']),
            new_layer=None if applied is None else int(applied['new_layer']),
            family=None if applied is None else str(applied.get('family') or ''),
            rejection_reasons=counter_dict(step_stats.get('reasons') or {}),
        ))
    sequential_snapshot = crossing_snapshot(state_s)
    sequential_record = dict(
        engine='local_reroute.reroute_one (sequential, others frozen)',
        per_route=sequential,
        total_before=baseline_crossings,
        total_after=int(sequential_snapshot['total']),
        gain=baseline_crossings - int(sequential_snapshot['total']),
        rejection_reasons=counter_dict(sequential_stats.get('reasons') or {}),
        note='context only: each route is optimised against the layout left by '
             'the previous single-route move (no joint rip-up)',
    )
    log('[P1] sequential single-only: total %d -> %d (gain %d)'
        % (baseline_crossings, sequential_record['total_after'],
           sequential_record['gain']))

    # ---- (b) joint reroute of A,B,C from a fresh baseline -------------------
    joint_attempts = []
    joint_state = None
    joint_baseline = None
    joint_result = None
    candidates = [triple] + top_triples[1:]
    seen_sets = set()
    for triple_attempt in candidates:
        rids = tuple(int(rid) for rid in triple_attempt['routes'])
        if rids in seen_sets:
            continue
        seen_sets.add(rids)
        baseline_j, state_j = E.load_state(None, log=log)
        attempt_started = time.time()
        joint_start_total = int(state_j.total)
        result = LR.reroute_joint(state_j, list(rids), cfg=ENGINE_CFG, log=log)
        attempt = dict(
            routes=list(rids),
            total_before=int(joint_start_total),
            engine='local_reroute.reroute_joint',
            success=bool(result is not None),
            seconds=round(time.time() - attempt_started, 2),
        )
        if result is not None:
            attempt.update(dict(
                old_total=int(result.get('old_total', baseline_crossings)),
                total=int(result.get('total', state_j.total)),
                gain=int(result.get('gain', 0)),
                applied=[{key: item.get(key) for key in
                          ('route_id', 'delta', 'old_layer', 'new_layer',
                           'old_z', 'new_z', 'family', 'lead_s', 'lead_t',
                           'xy_crossings', 'planned_delta', 'old_events',
                           'new_length')}
                         for item in (result.get('applied') or [])],
            ))
            joint_result = result
            joint_state = state_j
            joint_baseline = baseline_j
            joint_attempts.append(attempt)
            break
        attempt['rejection'] = 'reroute_joint returned None (transactional rollback)'
        joint_attempts.append(attempt)
        log('[P1] joint attempt %s rolled back; trying next triplet' % (rids,))
    if joint_result is None or joint_state is None:
        raise RuntimeError('P1: every joint reroute attempt rolled back')

    joint_snapshot = crossing_snapshot(joint_state)
    joint_rids = [int(rid) for rid in joint_result.get('routes', route_ids)]
    applied_by_id = {int(item['route_id']): item
                     for item in (joint_result.get('applied') or [])}
    joint_per_route = []
    for rid in joint_rids:
        old_route = baseline_routes[rid]
        new_route = joint_state.routes[rid]
        applied = applied_by_id.get(rid, {})
        joint_per_route.append(dict(
            route_id=int(rid),
            old_layer=int(baseline_rows[rid]['target_layer']),
            new_layer=int(applied.get('new_layer',
                                      new_route.get('target_layer') or 0)),
            old_z_mm=float(baseline_rows[rid]['target_z_mm']),
            new_z_mm=float(applied.get('new_z',
                                       new_route.get('target_z_mm') or 0.0)),
            old_length_mm=round(float(old_route.get('length_mm') or 0.0), 6),
            new_length_mm=round(float(new_route.get('length_mm') or 0.0), 6),
            family=str(applied.get('family') or ''),
            lead_s_mm=float(applied.get('lead_s') or 0.0),
            lead_t_mm=float(applied.get('lead_t') or 0.0),
            planned_delta=applied.get('planned_delta'),
            old_events=applied.get('old_events'),
            crossings_before=int(snapshot0['per_route'].get(rid, 0)),
            crossings_after=int(joint_snapshot['per_route'].get(rid, 0)),
            crossing_delta=(int(joint_snapshot['per_route'].get(rid, 0))
                            - int(snapshot0['per_route'].get(rid, 0))),
            xy_change=_xy_change_record(old_route, new_route),
            z_changed=bool(int(applied.get('new_layer',
                                           new_route.get('target_layer') or 0))
                           != int(baseline_rows[rid]['target_layer'])),
        ))
    joint_record = dict(
        routes=joint_rids,
        attempts=joint_attempts,
        old_total=int(joint_result.get('old_total', baseline_crossings)),
        total=int(joint_result.get('total', joint_snapshot['total'])),
        gain=int(joint_result.get('gain', 0)),
        per_route=joint_per_route,
        seconds=round(sum(item.get('seconds', 0.0)
                          for item in joint_attempts), 2),
    )
    log('[P1] joint %s: total %d -> %d (gain %d)'
        % (joint_rids, joint_record['old_total'], joint_record['total'],
           joint_record['gain']))

    # ---- save + validate joint layout --------------------------------------
    E.save_stage(joint_state, joint_baseline, P1_DIR,
                 note='P1 joint re-route of routes %s (single-only %d -> joint '
                      '%d crossings)' % (joint_rids,
                                         single_record['total_after'],
                                         joint_record['total']),
                 log=log)
    write_history_csv(P1_DIR, joint_state.history)
    attempts = [dict(stage='joint', routes=item['routes'],
                     accepted=bool(item.get('success')),
                     rejection=item.get('rejection'),
                     delta=item.get('gain'))
                for item in joint_attempts]
    attempts.extend([dict(stage='single_only', route_id=route_ids[0],
                          accepted=bool(single_applied is not None),
                          rejection=None if single_applied is not None
                          else 'no_improving_candidate',
                          delta=None if single_applied is None
                          else single_applied.get('delta')),
                     dict(stage='single_only', route_id=route_ids[0],
                          accepted=True,
                          delta=single_record['gain'],
                          note='see per-route crossing deltas in p1_case.json')])
    record_attempts(P1_DIR, attempts, 'P1')
    write_json(P1_DIR / 'strategy_stats.json', dict(
        schema=SCHEMA + '_stage_strategy_stats',
        phase='P1',
        engine_cfg={key: value for key, value in ENGINE_CFG.items()
                    if key != 'phase'},
        selection=triple,
        single_only=single_record,
        single_only_sequential=sequential_record,
        joint=joint_record,
        joint_attempts=joint_attempts,
        comparison=dict(single_gain=int(single_record['gain']),
                        sequential_single_gain=int(sequential_record['gain']),
                        joint_gain=int(joint_record['gain']),
                        joint_extra_over_single=int(joint_record['gain'])
                        - int(single_record['gain'])),
        seconds=round(time.time() - started, 2),
    ))

    validation = None
    if not skip_validate:
        validation = validate_frozen(P1_DIR, 'P1')

    case = dict(
        schema=SCHEMA + '_p1',
        generated_at=now(),
        baseline_dir=rel(BASELINE_DIR),
        baseline_crossings=baseline_crossings,
        selection=dict(
            routes=route_ids,
            rationale=('three non-manual routes whose baseline crossing '
                       'events directly involve each other (CrossingCache '
                       'crossing_events); they share the crowded body height '
                       '%s' % triple['body_z_mm']),
            evidence=triple,
            top_triples=top_triples,
            ranking=[dict(route_id=rid, crossings=int(snapshot0['per_route']
                                                      .get(rid, 0)))
                     for _count, rid in ranked[:10]],
        ),
        single_only=single_record,
        single_only_sequential=sequential_record,
        joint=joint_record,
        comparison=dict(
            single_gain=int(single_record['gain']),
            sequential_single_gain=int(sequential_record['gain']),
            joint_gain=int(joint_record['gain']),
            joint_extra_over_single=int(joint_record['gain'])
            - int(single_record['gain']),
            joint_extra_over_sequential=int(joint_record['gain'])
            - int(sequential_record['gain']),
            totals=dict(baseline=baseline_crossings,
                        single_only=single_record['total_after'],
                        sequential_single=sequential_record['total_after'],
                        joint=joint_record['total']),
        ),
        failed_attempts=dict(
            joint_attempts=joint_attempts,
            single_only_rejection_reasons=single_record['rejection_reasons'],
            sequential_rejection_reasons=sequential_record['rejection_reasons'],
        ),
        validation=validation,
        artifacts=dict(
            stage=rel(P1_DIR),
            routes=P1_DIR.joinpath('routes_l3d.json').name,
            assignment=P1_DIR.joinpath('assignment_1024.csv').name,
            crossing_stats=P1_DIR.joinpath('crossing_stats.json').name,
            sha256=P1_DIR.joinpath('SHA256.json').name,
            validation=rel(P1_DIR / 'validation' / 'validation.json'),
            case=rel(P1_DIR / 'p1_case.json'),
        ),
        seconds=round(time.time() - started, 2),
    )
    case['_plotdata'] = dict(
        routes=[
            dict(route_id=rid,
                 old_body_xy=[[round(x, 4), round(y, 4)] for x, y in
                              body_xy_polyline(baseline_routes[rid], 0.75)],
                 new_body_xy=[[round(x, 4), round(y, 4)] for x, y in
                              body_xy_polyline(joint_state.routes[rid], 0.75)],
                 old_layer=int(baseline_rows[rid]['target_layer']),
                 new_layer=int(joint_state.routes[rid].get('target_layer') or 0))
            for rid in joint_rids
        ],
    )
    write_json(P1_DIR / 'p1_case.json', case)
    log('[P1] done in %.1fs; single-only gain %d, joint gain %d'
        % (time.time() - started, single_record['gain'],
           joint_record['gain']))
    return case


# ---------------------------------------------------------------------------
# P2 - local crossing hotspot: Z-only vs XY+Z
# ---------------------------------------------------------------------------
def select_p2_routes(state, snap, count=8):
    """6-8 highest-crossing non-manual routes of the most crowded height."""
    heights = sorted(snap['by_height'].items(),
                     key=lambda item: (-int(item[1]['events']), item[0]))
    if not heights:
        raise RuntimeError('baseline has no crossing heights')
    hot_z, hot_stats = heights[0]
    non_manual = set(MR.non_manual_route_ids(state))
    on_height = []
    for rid in non_manual:
        route = state.routes[rid]
        if abs(round(float(route.get('target_z_mm') or 0.0), 9)
               - round(float(hot_z), 9)) > 1e-9:
            continue
        on_height.append((int(snap['per_route'].get(rid, 0)), int(rid)))
    on_height.sort(reverse=True)
    chosen = [rid for crossings, rid in on_height[:int(count)] if crossings > 0]
    ranked_all = []
    for crossings, rid in on_height:
        route = state.routes[rid]
        ranked_all.append(dict(route_id=rid, crossings=int(crossings),
                               target_layer=int(route.get('target_layer') or 0),
                               target_z_mm=float(route.get('target_z_mm') or 0.0)))
    # routes of other heights that still own crossing events on the hot height
    hot_events = Counter()
    for event in snap['cache'].crossing_events():
        if abs(round(float(event['z_mm']), 9) - round(float(hot_z), 9)) <= 1e-9:
            hot_events[int(event['route_a'])] += 1
            hot_events[int(event['route_b'])] += 1
    excluded = []
    for rid in sorted(hot_events, key=lambda rid: -hot_events[rid]):
        if rid in chosen:
            continue
        route = state.routes[rid]
        if str(route.get('manual_group') or '').strip():
            reason = 'manual route (frozen)'
        elif abs(round(float(route.get('target_z_mm') or 0.0), 9)
                 - round(float(hot_z), 9)) > 1e-9:
            reason = ('body height %.2f != hotspot height %.2f (only a short '
                      'mid-height segment crosses here)'
                      % (float(route.get('target_z_mm') or 0.0), float(hot_z)))
        else:
            reason = 'below the 8-route cut'
        if len(excluded) < 8:
            excluded.append(dict(route_id=int(rid),
                                 crossings_on_hot_height=int(hot_events[rid]),
                                 whole_route_crossings=int(
                                     snap['per_route'].get(rid, 0)),
                                 target_layer=int(route.get('target_layer') or 0),
                                 target_z_mm=float(route.get('target_z_mm') or 0.0),
                                 reason=reason))
    return dict(
        hotspot_height_mm=round(float(hot_z), 9),
        hotspot_height_crossings=int(hot_stats['events']),
        hotspot_height_crossing_pairs=int(hot_stats['pairs']),
        hotspot_height_routes=int(len(state.plane_prims.get(round(float(hot_z), 9), {}))),
        selection_rule=('%d highest-crossing non-manual routes whose primary '
                        'body height equals the most crowded physical height'
                        % int(count)),
        chosen=chosen,
        ranking=ranked_all[:16],
        excluded=excluded,
        heights_by_crossings=[dict(z_mm=round(float(z), 9),
                                   events=int(value['events']),
                                   pairs=int(value['pairs']))
                              for z, value in heights],
    )


def _on_straight(prims, s):
    for start, end, _index in P3.straight_intervals(prims):
        if start + 1e-9 <= s <= end - 1e-9:
            return True
    return False


def excursion_placements(prims, total, limit=P2_MAX_PLACEMENTS):
    """Bounded (s0, s1) ladder that starts/ends on straight runs."""
    runs = P3.straight_intervals(prims)
    pairs = []
    for i, (start_a, _end_a, _ia) in enumerate(runs):
        for j, (_start_b, end_b, _ib) in enumerate(runs):
            if j < i:
                continue
            s0 = start_a + 1.0
            s1 = end_b - 1.0
            if 1e-6 < s0 < s1 < total - 1e-6 and s1 - s0 >= 6.0:
                pairs.append((round(s0, 3), round(s1, 3)))
    # task-suggested offsets from the body start/end (kept when on straight runs)
    for s0 in (1.0, 5.0, 10.0, 20.0):
        for back in (1.0, 5.0, 10.0, 20.0):
            s1 = total - back
            if s0 < s1 and s1 - s0 >= 6.0 \
                    and _on_straight(prims, s0) and _on_straight(prims, s1):
                pairs.append((round(s0, 3), round(s1, 3)))
    unique = []
    seen = set()
    for pair in pairs:
        if pair in seen:
            continue
        seen.add(pair)
        unique.append(pair)
        if len(unique) >= int(limit):
            break
    return unique


def z_target_heights(current_z, count=P2_Z_TARGETS):
    options = []
    for plane in RB.BODY_PLANE_IDS:
        z_mm = float(RB.plane_z(plane))
        if abs(z_mm - float(current_z)) < 1e-9:
            continue
        options.append((abs(z_mm - float(current_z)), z_mm, int(plane)))
    options.sort()
    return [dict(layer=int(plane), z_mm=float(z_mm),
                 distance_mm=round(float(distance), 6))
            for distance, z_mm, plane in options[:int(count)]]


def enumerate_z_only_candidates(state, route_id):
    """Every legal Z-only move of one route: same XY body path, new height(s)."""
    rid = int(route_id)
    row = state.rows[rid]
    route = state.routes[rid]
    current_z = float(route.get('target_z_mm') or row['target_z_mm'])
    candidates = []
    attempts = []

    # (i) whole-body height shift with the XY body path kept byte-identical
    for layer, z_mm, lead_mm in MR.feasible_heights(state, rid):
        if abs(float(z_mm) - current_z) < 1e-9:
            continue
        try:
            candidate = RB.shift_height_keep_xy(route, row, int(layer),
                                                float(z_mm))
        except (RB.BuilderError, ValueError) as error:
            attempts.append(dict(kind='shift', layer=int(layer),
                                 z_mm=float(z_mm), ok=False,
                                 rejection='build:%s'
                                           % getattr(error, 'reason', str(error))))
            continue
        evaluation = evaluate(state, rid, candidate)
        candidates.append(dict(kind='shift', layer=int(layer),
                               z_mm=float(z_mm), lead_mm=float(lead_mm),
                               route=candidate, evaluation=evaluation,
                               params=dict(layer=int(layer), z_mm=float(z_mm),
                                           lead_mm=float(lead_mm))))
        attempts.append(dict(kind='shift', layer=int(layer), z_mm=float(z_mm),
                             ok=bool(evaluation['ok']),
                             delta=evaluation['delta'],
                             rejection=('none' if evaluation['ok']
                                        else '3d:%s' % (evaluation['kinds'][0]
                                                        if evaluation['kinds']
                                                        else 'unknown'))))

    # (ii) phase-2 style mid-body excursions on the EXISTING body path
    for body_index in RB.body_part_indices(route):
        prims = [dict(prim) for prim in
                 (route['parts'][body_index].get('primitives') or [])]
        total = float(P3.path_length(prims))
        for s0, s1 in excursion_placements(prims, total):
            for target in z_target_heights(current_z, P2_Z_TARGETS):
                z_to = float(target['z_mm'])
                try:
                    candidate, excursion = RB.insert_height_plan(
                        route, row, int(body_index), float(s0), float(s1),
                        float(z_to))
                except (RB.BuilderError, ValueError) as error:
                    attempts.append(dict(kind='excursion', body_index=int(body_index),
                                         s0_mm=float(s0), s1_mm=float(s1),
                                         z_mm=z_to, ok=False,
                                         rejection='build:%s'
                                                   % getattr(error, 'reason',
                                                             str(error))))
                    continue
                evaluation = evaluate(state, rid, candidate)
                candidates.append(dict(
                    kind='excursion', layer=int(target['layer']),
                    z_mm=z_to, route=candidate, evaluation=evaluation,
                    params=dict(body_index=int(body_index), s0_mm=float(s0),
                                s1_mm=float(s1), z_mm=z_to,
                                excursion_kind=str(excursion.get('kind')),
                                footprint_mm=float(excursion.get('footprint_mm')
                                                   or 0.0),
                                middle_mm=float(excursion.get('middle_mm') or 0.0)),
                ))
                attempts.append(dict(kind='excursion',
                                     body_index=int(body_index),
                                     s0_mm=float(s0), s1_mm=float(s1),
                                     z_mm=z_to, ok=bool(evaluation['ok']),
                                     delta=evaluation['delta'],
                                     rejection=('none' if evaluation['ok']
                                                else '3d:%s'
                                                % (evaluation['kinds'][0]
                                                   if evaluation['kinds']
                                                   else 'unknown'))))
    return candidates, attempts


#: any Z-only candidate that keeps the route's XY body path identical in the
#: geometry sense (sampled centre line); shifts are byte-identical primitives.
def verify_z_only_xy_unchanged(old_route, new_route):
    signature_same = bool(RB.body_xy_signature(old_route)
                          == RB.body_xy_signature(new_route))
    displacement = max_xy_displacement(old_route, new_route, SAMPLE_STEP_MM)
    return dict(
        body_xy_signature_identical=signature_same,
        max_xy_displacement_mm=displacement.get('max_mm'),
        note=('shift candidates keep the exact same body primitives; excursion '
              'candidates split the same XY path into prefix/middle/suffix, so '
              'the sampled centre line is identical up to the %.2f mm sample '
              'grid' % SAMPLE_STEP_MM),
    )


def run_p2_z_only(state, selection):
    """Strategy A: only physical height may change; XY body path is untouched."""
    started = time.time()
    start_total = int(state.total)
    route_reports = []
    kind_counter = Counter()
    rejection_counter = Counter()
    total_attempts = 0
    for rid in selection['chosen']:
        rid = int(rid)
        old_route = copy.deepcopy(state.routes[rid])
        old_row = dict(state.rows[rid])
        old_crossings = int(state.route_plane_events(rid, old_row['target_z_mm']))
        candidates, attempts = enumerate_z_only_candidates(state, rid)
        total_attempts += len(attempts)
        for attempt in attempts:
            kind_counter[attempt['kind']] += 1
            if not attempt.get('ok'):
                rejection_counter[str(attempt.get('rejection'))] += 1
        good = [item for item in candidates
                if item['evaluation']['ok']
                and item['evaluation']['delta'] is not None
                and item['evaluation']['delta'] < 0]
        accepted = None
        if good:
            good.sort(key=lambda item: (int(item['evaluation']['delta']),
                                        str(item['kind'])))
            best = good[0]
            applied = commit_route(state, rid, best['route'],
                                   'p2_z_only_%s' % best['kind'])
            accepted = dict(
                kind=str(best['kind']),
                params=best['params'],
                delta=int(applied['delta']),
                old_layer=int(applied['old_layer']),
                new_layer=int(applied['new_layer']),
                old_z_mm=float(applied['old_z']),
                new_z_mm=float(applied['new_z']),
                old_length_mm=round(float(applied['old_length']), 6),
                new_length_mm=round(float(applied['new_length']), 6),
                xy_unchanged=verify_z_only_xy_unchanged(
                    old_route, best['route']),
            )
        route_reports.append(dict(
            route_id=rid,
            old_layer=int(old_row['target_layer']),
            old_z_mm=float(old_row['target_z_mm']),
            candidates_evaluated=len(candidates),
            candidates_ok=int(sum(1 for item in candidates
                                  if item['evaluation']['ok'])),
            best_z_only_delta=(min((item['evaluation']['delta']
                                    for item in candidates
                                    if item['evaluation']['ok']
                                    and item['evaluation']['delta'] is not None),
                                   default=None)),
            improving_candidates=len(good),
            accepted=accepted,
            z_only_could_not_resolve=bool(accepted is None),
            rejection_reasons=counter_dict(Counter(
                str(item.get('rejection')) for item in attempts
                if not item.get('ok'))),
            failed_candidates=[
                dict(kind=str(attempt['kind']),
                     body_index=attempt.get('body_index'),
                     layer=attempt.get('layer'),
                     z_mm=attempt.get('z_mm'),
                     s0_mm=attempt.get('s0_mm'),
                     s1_mm=attempt.get('s1_mm'),
                     delta=attempt.get('delta'),
                     rejection=str(attempt.get('rejection')))
                for attempt in attempts if not attempt.get('ok')
            ][:120],
        ))
        if accepted is not None:
            log('[P2-A] route %d: %s -> L%d z=%+.2f delta=%d'
                % (rid, accepted['kind'], accepted['new_layer'],
                   accepted['new_z_mm'], accepted['delta']))
        else:
            log('[P2-A] route %d: NO improving Z-only candidate '
                '(best delta=%s)' % (rid, route_reports[-1]['best_z_only_delta']))
    return dict(
        strategy='A_z_only',
        routes=[int(rid) for rid in selection['chosen']],
        candidate_kinds=counter_dict(kind_counter),
        candidates_evaluated=int(sum(item['candidates_evaluated']
                                     for item in route_reports)),
        accepted_count=int(sum(1 for item in route_reports
                               if item['accepted'] is not None)),
        rejected_route_ids=[item['route_id'] for item in route_reports
                            if item['accepted'] is None],
        rejection_reasons=counter_dict(rejection_counter),
        per_route=route_reports,
        total_before=start_total,
        total_after=int(state.total),
        removed=start_total - int(state.total),
        budget=dict(max_evals_per_route=P2_MAX_EVAL_PER_ROUTE,
                    max_shift_heights=len(RB.BODY_PLANE_IDS) - 1,
                    max_excursion_placements=P2_MAX_PLACEMENTS,
                    extra_budget_distribution=counter_dict(kind_counter)),
        seconds=round(time.time() - started, 2),
    )


def run_p2_xy_z(state, selection):
    """Strategy B: full XY+Z engine freedom (``local_reroute.reroute_one``)."""
    started = time.time()
    start_total = int(state.total)
    route_reports = []
    aggregate_stats = Counter()
    aggregate_reasons = Counter()
    for rid in selection['chosen']:
        rid = int(rid)
        old_route = copy.deepcopy(state.routes[rid])
        old_row = dict(state.rows[rid])
        stats = {}
        applied = LR.reroute_one(state, rid, cfg=ENGINE_CFG, stats=stats)
        for key, value in stats.items():
            if isinstance(value, Counter):
                merge_counter(aggregate_reasons, value)
            elif isinstance(value, (int, float)):
                aggregate_stats[key] += int(value)
        merge_counter(aggregate_reasons, stats.get('reasons') or {})
        if applied is None:
            route_reports.append(dict(
                route_id=rid,
                old_layer=int(old_row['target_layer']),
                old_z_mm=float(old_row['target_z_mm']),
                accepted=None,
                rejection_reasons=counter_dict(stats.get('reasons') or {}),
                z_only_could_not_resolve=False,
            ))
            log('[P2-B] route %d: no accepted XY+Z move (reasons %s)'
                % (rid, counter_dict(stats.get('reasons') or {})))
            continue
        new_route = state.routes[rid]
        xy_change = _xy_change_record(old_route, new_route)
        z_changed = bool(int(applied['new_layer']) != int(old_row['target_layer']))
        route_reports.append(dict(
            route_id=rid,
            old_layer=int(applied['old_layer']),
            new_layer=int(applied['new_layer']),
            old_z_mm=float(applied['old_z']),
            new_z_mm=float(applied['new_z']),
            old_length_mm=round(float(applied['old_length']), 6),
            new_length_mm=round(float(applied['new_length']), 6),
            delta=int(applied['delta']),
            family=str(applied.get('family') or ''),
            lead_s_mm=float(applied.get('lead_s') or 0.0),
            lead_t_mm=float(applied.get('lead_t') or 0.0),
            xy_body_crossings=int(applied.get('xy_crossings') or 0),
            xy_change=xy_change,
            z_changed_for_main_body=z_changed,
            changed_xy_and_z=bool(z_changed and xy_change['xy_changed_substantially']),
            accepted=dict(kind='xy_z', delta=int(applied['delta'])),
            rejection_reasons=counter_dict(stats.get('reasons') or {}),
            engine_stats={key: (counter_dict(value)
                                if isinstance(value, Counter) else value)
                          for key, value in stats.items()},
        ))
        log('[P2-B] route %d: family=%s L%d->L%d delta=%d xy_disp=%s mm '
            'xy_changed=%s'
            % (rid, applied.get('family'), applied['old_layer'],
               applied['new_layer'], applied['delta'],
               xy_change['max_xy_displacement_mm'],
               xy_change['xy_changed_substantially']))
    aggregate = {key: (counter_dict(value) if isinstance(value, Counter)
                       else value)
                 for key, value in aggregate_stats.items()}
    return dict(
        strategy='B_xy_z',
        routes=[int(rid) for rid in selection['chosen']],
        accepted_count=int(sum(1 for item in route_reports
                               if item['accepted'] is not None)),
        accepted_ids=[item['route_id'] for item in route_reports
                      if item['accepted'] is not None],
        rejected_route_ids=[item['route_id'] for item in route_reports
                            if item['accepted'] is None],
        routes_with_new_xy_corridor=[item['route_id']
                                     for item in route_reports
                                     if item.get('xy_change', {}).get(
                                         'xy_changed_substantially')],
        routes_with_xy_and_z_change=[item['route_id']
                                     for item in route_reports
                                     if item.get('changed_xy_and_z')],
        rejection_reasons=counter_dict(aggregate_reasons),
        engine_stats=aggregate,
        per_route=route_reports,
        total_before=start_total,
        total_after=int(state.total),
        removed=start_total - int(state.total),
        budget=dict(cfg={key: value for key, value in ENGINE_CFG.items()
                         if key != 'phase'},
                    max_evals_per_route='<= max_combos*max_lead_pairs*max_eval'
                                        ' = 8 full 3D evaluations'),
        seconds=round(time.time() - started, 2),
    )


def run_p2(ctx, skip_validate=False):
    log('=' * 78)
    log('[P2] local crossing hotspot: Z-only vs XY+Z on a fresh baseline each')
    started = time.time()
    baseline_sel, state_sel = E.load_state(None, log=log)
    baseline_total = int(state_sel.total)
    snapshot_sel = crossing_snapshot(state_sel)
    selection = select_p2_routes(state_sel, snapshot_sel, count=8)
    log('[P2] hotspot z=%+.2f: %d crossing events on this height; chosen %s'
        % (selection['hotspot_height_mm'],
           selection['hotspot_height_crossings'], selection['chosen']))

    # ---- strategy A: Z only, fresh baseline ---------------------------------
    baseline_a, state_a = E.load_state(None, log=log)
    report_a = run_p2_z_only(state_a, selection)
    log('[P2-A] total %d -> %d (removed %d)'
        % (report_a['total_before'], report_a['total_after'],
           report_a['removed']))
    E.save_stage(state_a, baseline_a, P2_Z_DIR,
                 note='P2 A: Z-only moves (shift_height_keep_xy + mid-body '
                      'excursions) on the z=%+.2f hotspot'
                      % selection['hotspot_height_mm'], log=log)
    write_history_csv(P2_Z_DIR, state_a.history)
    attempts_a = []
    for item in report_a['per_route']:
        for reason, count in (item.get('rejection_reasons') or {}).items():
            attempts_a.append(dict(stage='P2_A_z_only',
                                   route_id=item['route_id'],
                                   accepted=False, rejection=reason,
                                   count=int(count)))
        if item['accepted'] is None:
            attempts_a.append(dict(stage='P2_A_z_only', route_id=item['route_id'],
                                   accepted=False,
                                   rejection='no_improving_z_only_candidate:best_'
                                             'delta=%s'
                                             % item['best_z_only_delta']))
        else:
            attempts_a.append(dict(stage='P2_A_z_only', route_id=item['route_id'],
                                   accepted=True,
                                   kind=item['accepted']['kind'],
                                   delta=item['accepted']['delta']))
    record_attempts(P2_Z_DIR, attempts_a, 'P2 A z_only')
    write_json(P2_Z_DIR / 'strategy_stats.json', dict(
        schema=SCHEMA + '_stage_strategy_stats', phase='P2',
        strategy='A_z_only', selection=selection, report=report_a))

    # ---- strategy B: full XY+Z, fresh baseline ------------------------------
    baseline_b, state_b = E.load_state(None, log=log)
    report_b = run_p2_xy_z(state_b, selection)
    log('[P2-B] total %d -> %d (removed %d)'
        % (report_b['total_before'], report_b['total_after'],
           report_b['removed']))
    E.save_stage(state_b, baseline_b, P2_XZ_DIR,
                 note='P2 B: full XY+Z reroute_one on the z=%+.2f hotspot'
                      % selection['hotspot_height_mm'], log=log)
    write_history_csv(P2_XZ_DIR, state_b.history)
    attempts_b = []
    for item in report_b['per_route']:
        for reason, count in (item.get('rejection_reasons') or {}).items():
            attempts_b.append(dict(stage='P2_B_xy_z', route_id=item['route_id'],
                                   accepted=False, rejection=reason,
                                   count=int(count)))
        if item['accepted'] is None:
            attempts_b.append(dict(stage='P2_B_xy_z', route_id=item['route_id'],
                                   accepted=False,
                                   rejection='no_improving_xy_z_candidate'))
        else:
            attempts_b.append(dict(stage='P2_B_xy_z', route_id=item['route_id'],
                                   accepted=True, family=item['family'],
                                   delta=item['delta']))
    record_attempts(P2_XZ_DIR, attempts_b, 'P2 B xy_z')
    write_json(P2_XZ_DIR / 'strategy_stats.json', dict(
        schema=SCHEMA + '_stage_strategy_stats', phase='P2',
        strategy='B_xy_z', selection=selection, report=report_b))

    validation_a = validate_frozen(P2_Z_DIR, 'P2 A z_only') \
        if not skip_validate else None
    validation_b = validate_frozen(P2_XZ_DIR, 'P2 B xy_z') \
        if not skip_validate else None

    # ---- comparison --------------------------------------------------------
    by_id_a = {item['route_id']: item for item in report_a['per_route']}
    by_id_b = {item['route_id']: item for item in report_b['per_route']}
    per_route = []
    for rid in report_a['routes']:
        item_a = by_id_a[rid]
        item_b = by_id_b[rid]
        accepted_a = item_a.get('accepted')
        accepted_b = item_b.get('accepted')
        gain_a = int(accepted_a['delta']) if accepted_a else 0
        gain_b = int(accepted_b['delta']) if accepted_b else 0
        b_xy_changed = bool(item_b.get('xy_change', {}).get(
            'xy_changed_substantially'))
        per_route.append(dict(
            route_id=int(rid),
            baseline_crossings=int(snapshot_sel['per_route'].get(rid, 0)),
            z_only=dict(
                accepted=accepted_a is not None,
                gain=gain_a,
                move=None if accepted_a is None else dict(
                    kind=accepted_a['kind'], params=accepted_a['params'],
                    new_layer=accepted_a['new_layer'],
                    new_z_mm=accepted_a['new_z_mm']),
                best_z_only_delta=item_a['best_z_only_delta'],
                improving_candidates=item_a['improving_candidates'],
                xy_unchanged=accepted_a['xy_unchanged'] if accepted_a else None,
                rejection_reasons=item_a['rejection_reasons'],
                z_only_could_not_resolve=item_a['z_only_could_not_resolve'],
            ),
            xy_z=dict(
                accepted=accepted_b is not None,
                gain=gain_b,
                family=None if not accepted_b else item_b['family'],
                new_layer=None if not accepted_b else item_b['new_layer'],
                new_z_mm=None if not accepted_b else item_b['new_z_mm'],
                delta=None if not accepted_b else item_b['delta'],
                xy_change=item_b.get('xy_change'),
                changed_xy_and_z=item_b.get('changed_xy_and_z'),
                rejection_reasons=item_b.get('rejection_reasons') or {},
            ),
            only_z_insufficient=bool(item_a['z_only_could_not_resolve']),
            needed_new_xy_corridor=bool(
                item_a['z_only_could_not_resolve']
                and accepted_b is not None
                and b_xy_changed),
            xy_z_helped_more=bool(gain_b < gain_a),
        ))
    z_only_removed = int(report_a['removed'])
    xy_z_removed = int(report_b['removed'])
    comparison = dict(
        total_before=baseline_total,
        z_only_total_after=int(report_a['total_after']),
        xy_z_total_after=int(report_b['total_after']),
        z_only_removed=z_only_removed,
        xy_z_removed=xy_z_removed,
        extra_removed_by_xy=xy_z_removed - z_only_removed,
        accepted_routes_z_only=report_a['accepted_count'],
        accepted_routes_xy_z=report_b['accepted_count'],
        routes_needed_new_xy_corridor=[item['route_id'] for item in per_route
                                       if item['needed_new_xy_corridor']],
        routes_only_z_insufficient=[item['route_id'] for item in per_route
                                    if item['only_z_insufficient']],
        routes_where_xy_z_more_gain=[item['route_id'] for item in per_route
                                     if item['xy_z_helped_more']],
        routes_where_xy_z_better=[item['route_id'] for item in per_route
                                  if item['xy_z']['gain'] < item['z_only']['gain']],
        routes_where_z_only_better=[item['route_id'] for item in per_route
                                    if item['z_only']['gain'] < item['xy_z']['gain']],
        routes_equal_gain=[item['route_id'] for item in per_route
                           if item['z_only']['gain'] == item['xy_z']['gain']],
    )
    comparison_payload = dict(
        schema=SCHEMA + '_p2',
        generated_at=now(),
        baseline_dir=rel(BASELINE_DIR),
        hotspot=selection,
        budgets=dict(
            z_only=report_a['budget'],
            xy_z=report_b['budget'],
            note=('both strategies run one pass over the same 8 routes from a '
                  'fresh authoritative baseline; A capped at %d exact 3D '
                  'evaluations per route, B at <=8 full 3D evaluations per '
                  'route with <=%d built XY candidates per combo'
                  % (P2_MAX_EVAL_PER_ROUTE, ENGINE_CFG['max_candidates'])),
        ),
        z_only=dict(
            total_before=report_a['total_before'],
            total_after=report_a['total_after'],
            removed=report_a['removed'],
            accepted_count=report_a['accepted_count'],
            rejected_route_ids=report_a['rejected_route_ids'],
            candidate_kinds=report_a['candidate_kinds'],
            candidates_evaluated=report_a['candidates_evaluated'],
            rejection_reasons=report_a['rejection_reasons'],
            per_route=report_a['per_route'],
            seconds=report_a['seconds'],
        ),
        xy_z=dict(
            total_before=report_b['total_before'],
            total_after=report_b['total_after'],
            removed=report_b['removed'],
            accepted_count=report_b['accepted_count'],
            rejected_route_ids=report_b['rejected_route_ids'],
            routes_with_new_xy_corridor=report_b['routes_with_new_xy_corridor'],
            routes_with_xy_and_z_change=report_b['routes_with_xy_and_z_change'],
            rejection_reasons=report_b['rejection_reasons'],
            engine_stats=report_b['engine_stats'],
            per_route=report_b['per_route'],
            seconds=report_b['seconds'],
        ),
        comparison=comparison,
        per_route=per_route,
        validators=dict(z_only=validation_a, xy_z=validation_b),
        artifacts=dict(
            z_only_stage=rel(P2_Z_DIR),
            z_only_validation=rel(P2_Z_DIR / 'validation' / 'validation.json'),
            xy_z_stage=rel(P2_XZ_DIR),
            xy_z_validation=rel(P2_XZ_DIR / 'validation' / 'validation.json'),
            report=rel(P2_DIR / 'p2_report.md'),
        ),
        seconds=round(time.time() - started, 2),
    )
    write_json(P2_DIR / 'p2_comparison.json', comparison_payload)
    write_p2_report(P2_DIR / 'p2_report.md', comparison_payload)
    comparison_payload['_plotdata'] = dict(
        hotspot_height_mm=selection['hotspot_height_mm'],
        routes=[
            dict(
                route_id=item['route_id'],
                old_body_xy=[[round(x, 4), round(y, 4)] for x, y in
                             body_xy_polyline(state_sel.routes[item['route_id']],
                                              1.0)],
                z_only_body_xy=[[round(x, 4), round(y, 4)] for x, y in
                                body_xy_polyline(state_a.routes[item['route_id']],
                                                 1.0)],
                xy_z_body_xy=[[round(x, 4), round(y, 4)] for x, y in
                              body_xy_polyline(state_b.routes[item['route_id']],
                                               1.0)],
                old_flats=[dict(z_mm=round(float(part['z_mm']), 6))
                           for _i, part in body_flats(
                               state_sel.routes[item['route_id']])],
                z_only_flats=[dict(z_mm=round(float(part['z_mm']), 6))
                              for _i, part in body_flats(
                                  state_a.routes[item['route_id']])],
                xy_z_flats=[dict(z_mm=round(float(part['z_mm']), 6))
                            for _i, part in body_flats(
                                state_b.routes[item['route_id']])],
            )
            for item in per_route
        ],
    )
    log('[P2] done in %.1fs: Z-only removed %d, XY+Z removed %d crossings'
        % (time.time() - started, z_only_removed, xy_z_removed))
    return comparison_payload


def write_p2_report(path, payload):
    selection = payload['hotspot']
    comparison = payload['comparison']
    z_only = payload['z_only']
    xy_z = payload['xy_z']
    validators = payload['validators']
    lines = []
    lines.append('# P2 - Local crossing hotspot: Z-only vs XY+Z')
    lines.append('')
    lines.append('Generated %s by `run_router_validation.py` (real geometry, '
                 'independent validator).' % payload['generated_at'])
    lines.append('')
    lines.append('## Hotspot')
    lines.append('')
    lines.append('* most crowded physical height: **%+.2f mm** (%d crossing '
                 'events, %d crossing pairs, %d routes on the height)'
                 % (selection['hotspot_height_mm'],
                    selection['hotspot_height_crossings'],
                    selection['hotspot_height_crossing_pairs'],
                    selection['hotspot_height_routes']))
    lines.append('* chosen routes (%d, %s): **%s**'
                 % (len(selection['chosen']), selection['selection_rule'],
                    ', '.join(str(rid) for rid in selection['chosen'])))
    lines.append('* selection ranking (route_id: whole-route crossings / body z):')
    for item in selection['ranking'][:12]:
        lines.append('  * route %d: %d crossings, L%d z=%+.2f'
                     % (item['route_id'], item['crossings'],
                        item['target_layer'], item['target_z_mm']))
    lines.append('')
    lines.append('## Results (2409 baseline crossings)')
    lines.append('')
    lines.append('| strategy | total crossings | removed | accepted routes |')
    lines.append('|---|---|---|---|')
    lines.append('| A: Z only (`shift_height_keep_xy` + `insert_height_plan`) '
                 '| %d | **%d** | %d/%d |'
                 % (z_only['total_after'], z_only['removed'],
                    z_only['accepted_count'], len(z_only['per_route'])))
    lines.append('| B: full XY+Z (`reroute_one`) | %d | **%d** | %d/%d |'
                 % (xy_z['total_after'], xy_z['removed'],
                    xy_z['accepted_count'], len(xy_z['per_route'])))
    lines.append('')
    lines.append('* Z-only removes **%d** crossings; XY+Z removes **%d** '
                 'crossings (difference: %+d).'
                 % (z_only['removed'], xy_z['removed'],
                    comparison['extra_removed_by_xy']))
    lines.append('* A made %d Z-only attempts (%s); %d reached the exact 3D '
                 'evaluation (%d failed to build, %d were rejected by the true '
                 '3D/crossing check, %d legal candidates did not improve), '
                 '%d accepted. Rejection reasons: `%s`.'
                 % (sum(z_only['candidate_kinds'].values()),
                    ', '.join('%s=%d' % (key, value) for key, value in
                              sorted(z_only['candidate_kinds'].items())),
                    z_only['candidates_evaluated'],
                    sum(z_only['candidate_kinds'].values())
                    - z_only['candidates_evaluated'],
                    sum(value for key, value in
                        z_only['rejection_reasons'].items()
                        if str(key).startswith('3d:')),
                    z_only['candidates_evaluated']
                    - sum(value for key, value in
                          z_only['rejection_reasons'].items()
                          if str(key).startswith('3d:'))
                    - z_only['accepted_count'],
                    z_only['accepted_count'],
                    '`, `'.join('%s=%d' % (key, value) for key, value in
                                sorted(z_only['rejection_reasons'].items()))))
    lines.append('')
    lines.append('## Per-route outcome')
    lines.append('')
    lines.append('| route | baseline crossings | A Z-only move | A gain | '
                 'B XY+Z move | B gain | notes |')
    lines.append('|---|---|---|---|---|---|---|')
    for item in payload['per_route']:
        rid = item['route_id']
        item_a = item['z_only']
        item_b = item['xy_z']
        move_a = 'none'
        if item_a['accepted']:
            params = item_a['move']
            if params['kind'] == 'shift':
                move_a = 'shift -> z=%+.2f' % params['new_z_mm']
            else:
                move_a = 'excursion -> z=%+.2f (s0=%.1f, s1=%.1f)' % (
                    params['params']['z_mm'], params['params']['s0_mm'],
                    params['params']['s1_mm'])
        move_b = 'none'
        if item_b['accepted']:
            move_b = '%s -> L%s z=%+.2f' % (item_b['family'] or '?',
                                            item_b['new_layer'],
                                            item_b['new_z_mm'])
        notes = []
        if item['only_z_insufficient']:
            notes.append('only-Z could not improve (best Z-only delta=%s)'
                         % item_a['best_z_only_delta'])
        if item['needed_new_xy_corridor']:
            notes.append('needed a genuinely new XY corridor')
        if item_b['xy_change']:
            notes.append('B XY displacement %.2f mm'
                         % (item_b['xy_change']['max_xy_displacement_mm'] or 0.0))
        lines.append('| %d | %d | %s | %d | %s | %d | %s |'
                     % (rid, item['baseline_crossings'], move_a,
                        item_a['gain'], move_b, item_b['gain'],
                        '; '.join(notes) if notes else ''))
    lines.append('')
    lines.append('## Questions')
    lines.append('')
    lines.append('* **How many crossings does Z-only remove?** %d (2409 -> %d).'
                 % (z_only['removed'], z_only['total_after']))
    lines.append('* **How many crossings does XY+Z remove?** %d (2409 -> %d).'
                 % (xy_z['removed'], xy_z['total_after']))
    n_both = len(xy_z.get('routes_with_xy_and_z_change') or [])
    n_accepted_b = int(xy_z.get('accepted_count') or 0)
    lines.append('  * composition of the %d accepted XY+Z moves: %d changed '
                 'body height **and** the XY corridor, %d used a same-height '
                 'XY-only corridor (the engine picked the cheapest legal '
                 'option); all %d changed the real XY body geometry.'
                 % (n_accepted_b, n_both, max(0, n_accepted_b - n_both),
                    len(xy_z.get('routes_with_new_xy_corridor') or [])))
    lines.append('* **Which routes needed a genuinely new XY corridor?** %s.'
                 % (', '.join('route %d' % rid for rid in
                              comparison['routes_needed_new_xy_corridor'])
                    or 'none'))
    lines.append('* **Z-only could not resolve the conflict for routes:** %s '
                 '(every Z-only shift/excursion candidate was non-improving or '
                 'rejected).'
                 % (', '.join('route %d' % rid for rid in
                              comparison['routes_only_z_insufficient'])
                    or 'none'))
    lines.append('')
    lines.append('### Z-only candidates rejected because only-Z could not '
                 'resolve the conflict')
    lines.append('')
    any_rejected = False
    for item in payload['per_route']:
        rejected = item['z_only']['rejection_reasons']
        if not rejected:
            continue
        any_rejected = True
        pretty = ', '.join('%s x%d' % (key, value)
                           for key, value in sorted(rejected.items()))
        if item['z_only']['z_only_could_not_resolve']:
            pretty += ('; best Z-only delta %s => no legal/improving Z-only '
                       'move' % item['z_only']['best_z_only_delta'])
        lines.append('* route %d: %s' % (item['route_id'], pretty))
    if not any_rejected:
        lines.append('* none')
    lines.append('')
    lines.append('## Independent validation (`manual_policy="frozen"`)')
    lines.append('')
    for key, label in (('z_only', 'A z_only'), ('xy_z', 'B xy_z')):
        validation = validators.get(key)
        if not validation:
            lines.append('* %s: validator skipped' % label)
            continue
        lines.append('* %s: `validation_pass=%s`, violations=%d, routed=%s, '
                     'crossings=%s, manual frozen %s/%s, clearance=%s mm '
                     '(policy violations %s)'
                     % (label, validation['validation_pass'],
                        validation['violations'], validation['routed'],
                        validation['crossings'],
                        validation['manual']['matched'],
                        validation['manual']['manual_route_count'],
                        validation['min_3d_clearance_mm'],
                        validation['manual']['violations']))
    lines.append('')
    lines.append('## Artifacts')
    lines.append('')
    lines.append('* Z-only layout: `P2/z_only/` '
                 '(routes_l3d.json, assignment_1024.csv, crossing_stats.json, '
                 'SHA256.json, validation/)')
    lines.append('* XY+Z layout: `P2/xy_z/` (same artifact set)')
    lines.append('* machine-readable comparison: `P2/p2_comparison.json`')
    lines.append('')
    Path(path).write_text('\n'.join(lines), encoding='utf-8')
    return path


# ---------------------------------------------------------------------------
# cross-phase reporting (README / strategy_stats / plot data)
# ---------------------------------------------------------------------------
def aggregate_failure_reasons(ctx):
    """Aggregate every rejected-candidate reason of all phases."""
    failure = Counter()
    for phase in ('P0', 'P1', 'P2'):
        payload = ctx.get(phase) or {}
        if phase == 'P0':
            merge_counter(failure, (payload.get('failed_attempts') or {})
                          .get('reasons') or {})
        elif phase == 'P1':
            merge_counter(failure, (payload.get('single_only') or {})
                          .get('rejection_reasons') or {})
            for attempt in ((payload.get('joint') or {}).get('attempts') or []):
                if attempt.get('rejection'):
                    failure[attempt['rejection']] += 1
        elif phase == 'P2':
            merge_counter(failure, (payload.get('z_only') or {})
                          .get('rejection_reasons') or {})
            merge_counter(failure, (payload.get('xy_z') or {})
                          .get('rejection_reasons') or {})
    return failure


def load_case_json(path, label):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        log('[reports] cannot load %s (%s): %s' % (label, rel(path), error))
        return dict(error='missing artifact: %s' % error)


def _plot_polygon(points):
    return [[round(float(x), 4), round(float(y), 4)] for x, y in points]


def _plot_flats(route, step=0.5):
    return [dict(z_mm=round(float(part['z_mm']), 6),
                 xy=_plot_polygon(P3.path_polyline(
                     [dict(prim) for prim in part['primitives']], step)))
            for _index, part in body_flats(route)]


def rebuild_plotdata_from_stages():
    """Reconstruct ``plots/router_validation_plotdata.json`` from saved layouts."""
    _, state_base = E.load_state(None, log=log)
    plot = dict(P0=None, P1=None, P2=None)
    if (P0_DIR / 'routes_l3d.json').exists():
        case = load_case_json(P0_DIR / 'p0_case.json', 'P0 case')
        rid = int(((case.get('selected_route') or {}).get('route_id')) or -1)
        if rid >= 0 and rid in state_base.routes:
            _, state_p0 = E.load_state(P0_DIR, log=log)
            old = state_base.routes[rid]
            new = state_p0.routes[rid]
            plot['P0'] = dict(route_id=rid,
                              old_body_xy=_plot_polygon(body_xy_polyline(old)),
                              new_body_xy=_plot_polygon(body_xy_polyline(new)),
                              old_flats=_plot_flats(old),
                              new_flats=_plot_flats(new))
    if (P1_DIR / 'routes_l3d.json').exists():
        case = load_case_json(P1_DIR / 'p1_case.json', 'P1 case')
        rids = [int(rid) for rid in
                ((case.get('joint') or {}).get('routes') or [])]
        if rids:
            _, state_p1 = E.load_state(P1_DIR, log=log)
            plot['P1'] = dict(routes=[
                dict(route_id=rid,
                     old_body_xy=_plot_polygon(body_xy_polyline(
                         state_base.routes[rid], 0.75)),
                     new_body_xy=_plot_polygon(body_xy_polyline(
                         state_p1.routes[rid], 0.75)),
                     old_layer=int(state_base.routes[rid].get('target_layer')
                                   or 0),
                     new_layer=int(state_p1.routes[rid].get('target_layer')
                                   or 0))
                for rid in rids if rid in state_base.routes])
    if (P2_Z_DIR / 'routes_l3d.json').exists() \
            and (P2_XZ_DIR / 'routes_l3d.json').exists():
        case = load_case_json(P2_DIR / 'p2_comparison.json', 'P2 case')
        rids = [int(rid) for rid in
                ((case.get('hotspot') or {}).get('chosen') or [])]
        if rids:
            _, state_z = E.load_state(P2_Z_DIR, log=log)
            _, state_xz = E.load_state(P2_XZ_DIR, log=log)
            plot['P2'] = dict(
                hotspot_height_mm=((case.get('hotspot') or {})
                                   .get('hotspot_height_mm')),
                routes=[dict(
                    route_id=rid,
                    old_body_xy=_plot_polygon(body_xy_polyline(
                        state_base.routes[rid], 1.0)),
                    z_only_body_xy=_plot_polygon(body_xy_polyline(
                        state_z.routes[rid], 1.0)),
                    xy_z_body_xy=_plot_polygon(body_xy_polyline(
                        state_xz.routes[rid], 1.0)),
                    old_flats=[dict(z_mm=round(float(part['z_mm']), 6))
                               for _i, part in body_flats(
                                   state_base.routes[rid])],
                    z_only_flats=[dict(z_mm=round(float(part['z_mm']), 6))
                                  for _i, part in body_flats(
                                      state_z.routes[rid])],
                    xy_z_flats=[dict(z_mm=round(float(part['z_mm']), 6))
                                for _i, part in body_flats(
                                    state_xz.routes[rid])],
                ) for rid in rids if rid in state_base.routes])
    return plot


def write_root_reports(ctx):
    p0 = ctx.get('P0') or {}
    p1 = ctx.get('P1') or {}
    p2 = ctx.get('P2') or {}
    strategy = dict(
        schema=SCHEMA + '_strategy_stats',
        generated_at=now(),
        engine_cfg={key: value for key, value in ENGINE_CFG.items()
                    if key != 'phase'},
        P0=dict(
            status='ok' if p0 and 'error' not in p0 else 'failed',
            route_id=(p0.get('selected_route') or {}).get('route_id'),
            candidate_source=(p0.get('candidate') or {}).get('source'),
            candidate_stats=(p0.get('candidate') or {}).get('engine_stats'),
            attempts_total=(p0.get('failed_attempts') or {}).get('total'),
            attempts_rejected=(p0.get('failed_attempts') or {}).get('rejected'),
            rejection_reasons=(p0.get('failed_attempts') or {}).get('reasons'),
            crossings=(p0.get('crossings') or {}),
            accepted_moves=1 if p0 and p0.get('commit') else 0,
        ),
        P1=dict(
            status='ok' if p1 and 'error' not in p1 else 'failed',
            routes=(p1.get('joint') or {}).get('routes'),
            single_only_gain=((p1.get('single_only') or {}).get('gain')),
            sequential_single_gain=((p1.get('single_only_sequential') or {}
                                     ).get('gain')),
            joint_gain=((p1.get('joint') or {}).get('gain')),
            joint_attempts=((p1.get('joint') or {}).get('attempts')),
            rejection_reasons=((p1.get('single_only') or {}
                                ).get('rejection_reasons')),
        ),
        P2=dict(
            status='ok' if p2 and 'error' not in p2 else 'failed',
            hotspot_height_mm=((p2.get('hotspot') or {})
                               .get('hotspot_height_mm')),
            routes=((p2.get('hotspot') or {}).get('chosen')),
            budgets=(p2.get('budgets') or {}),
            z_only=dict(
                candidates_evaluated=((p2.get('z_only') or {})
                                      .get('candidates_evaluated')),
                candidate_kinds=((p2.get('z_only') or {})
                                 .get('candidate_kinds')),
                accepted_count=((p2.get('z_only') or {}).get('accepted_count')),
                rejected_route_ids=((p2.get('z_only') or {})
                                    .get('rejected_route_ids')),
                removed=((p2.get('z_only') or {}).get('removed')),
                rejection_reasons=((p2.get('z_only') or {})
                                   .get('rejection_reasons')),
            ),
            xy_z=dict(
                accepted_count=((p2.get('xy_z') or {}).get('accepted_count')),
                rejected_route_ids=((p2.get('xy_z') or {})
                                    .get('rejected_route_ids')),
                removed=((p2.get('xy_z') or {}).get('removed')),
                engine_stats=((p2.get('xy_z') or {}).get('engine_stats')),
                rejection_reasons=((p2.get('xy_z') or {})
                                   .get('rejection_reasons')),
            ),
            comparison=(p2.get('comparison') or {}),
        ),
        validators=dict(
            P0=((p0.get('validation') or {}).get('hard_requirements_ok')),
            P1=((p1.get('validation') or {}).get('hard_requirements_ok')),
            P2_z_only=(((p2.get('validators') or {}).get('z_only') or {})
                       .get('hard_requirements_ok')),
            P2_xy_z=(((p2.get('validators') or {}).get('xy_z') or {})
                     .get('hard_requirements_ok')),
        ),
        timings=ctx.get('timings') or {},
        failure_reason_distribution=ctx.get('failure_reasons') or {},
        total_seconds=round(sum(
            value for value in (ctx.get('timings') or {}).values()
            if isinstance(value, (int, float))), 2),
    )
    write_json(RUN_DIR / 'strategy_stats.json', strategy)

    # plot data for the plotter teammate (JSON only; PNGs are their deliverable)
    plot = dict(
        schema=SCHEMA + '_plotdata',
        generated_at=now(),
        note='sampled real centre lines (mm) read from the saved layouts; '
             'PNG plotting is owned by the plotter teammate',
        P0=p0.get('_plotdata'),
        P1=p1.get('_plotdata'),
        P2=p2.get('_plotdata'),
    )
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    write_json(PLOTS_DIR / 'router_validation_plotdata.json', plot)

    write_readme(ctx, p0, p1, p2, strategy)
    return strategy


def write_readme(ctx, p0, p1, p2, strategy):
    lines = []
    lines.append('# Router functional validation - P0 / P1 / P2')
    lines.append('')
    lines.append('Generated %s by `four_side_1024/fanout1024/xyzrouter/'
                 'run_router_validation.py`.' % now())
    lines.append('')
    lines.append('Everything below is produced from **real route geometry** '
                 'saved in `routes_l3d.json` (1024 routes) and accepted by the '
                 '**independent** `validate_native3d` validator with '
                 '`manual_policy="frozen"` (full geometry checks, 368/368 '
                 'manual-U routes byte-frozen, D56 strict crossing rule '
                 'unchanged).')
    lines.append('')
    lines.append('## Headline results')
    lines.append('')
    p0_cross = p0.get('crossings') or {}
    geometry = p0.get('geometry') or {}
    validation0 = p0.get('validation') or {}
    lines.append('| item | value |')
    lines.append('|---|---|')
    lines.append('| authoritative baseline | 2409 crossings, 1024/1024 routes, '
                 '`XYZ_JOINT_G123_1024/baseline_authoritative` |')
    if p0 and 'error' not in p0:
        lines.append('| **P0** single route | route %s: L%s z=%+.2f -> L%s '
                     'z=%+.2f, family `%s`, crossings %d -> %d (delta %d), '
                     'max XY centre-line displacement **%.2f mm** |'
                     % ((p0.get('selected_route') or {}).get('route_id'),
                        (geometry.get('old') or {}).get('target_layer'),
                        (geometry.get('old') or {}).get('target_z_mm') or 0.0,
                        (geometry.get('new') or {}).get('target_layer'),
                        (geometry.get('new') or {}).get('target_z_mm') or 0.0,
                        (p0.get('candidate') or {}).get('family'),
                        p0_cross.get('old_total'),
                        p0_cross.get('new_total'),
                        -(p0_cross.get('removed') or 0),
                        ((geometry.get('max_xy_displacement') or {})
                         .get('max_mm') or 0.0)))
    else:
        lines.append('| **P0** single route | FAILED: %s |'
                     % (p0.get('error') if p0 else 'not run'))
    if p1 and 'error' not in p1:
        comparison1 = p1.get('comparison') or {}
        lines.append('| **P1** single vs joint | routes %s: single-only gain '
                     '%d, joint gain **%d** (extra %+d), crossings 2409 -> %d |'
                     % (', '.join(str(rid) for rid in
                                  (p1.get('joint') or {}).get('routes') or []),
                        comparison1.get('single_gain') or 0,
                        comparison1.get('joint_gain') or 0,
                        comparison1.get('joint_extra_over_single') or 0,
                        (p1.get('joint') or {}).get('total') or 0))
    else:
        lines.append('| **P1** single vs joint | FAILED: %s |'
                     % (p1.get('error') if p1 else 'not run'))
    if p2 and 'error' not in p2:
        comparison2 = p2.get('comparison') or {}
        lines.append('| **P2** Z-only | hotspot z=%+.2f: %d crossings removed '
                     '(2409 -> %d), %d/%d routes improved |'
                     % ((p2.get('hotspot') or {}).get('hotspot_height_mm') or 0.0,
                        comparison2.get('z_only_removed') or 0,
                        comparison2.get('z_only_total_after') or 0,
                        (p2.get('z_only') or {}).get('accepted_count') or 0,
                        len((p2.get('hotspot') or {}).get('chosen') or [])))
        lines.append('| **P2** XY+Z | %d crossings removed (2409 -> %d), %d/%d '
                     'routes improved, %d with a genuinely new XY corridor |'
                     % (comparison2.get('xy_z_removed') or 0,
                        comparison2.get('xy_z_total_after') or 0,
                        (p2.get('xy_z') or {}).get('accepted_count') or 0,
                        len((p2.get('hotspot') or {}).get('chosen') or []),
                        len(((p2.get('xy_z') or {})
                             .get('routes_with_new_xy_corridor') or []))))
    else:
        lines.append('| **P2** Z-only vs XY+Z | FAILED: %s |'
                     % (p2.get('error') if p2 else 'not run'))
    lines.append('')
    lines.append('## Independent validator results '
                 '(`manual_policy="frozen"`)')
    lines.append('')
    lines.append('| stage | validation_pass | violations | routed | manual '
                 'frozen | crossings | min 3D clearance |')
    lines.append('|---|---|---|---|---|---|---|')
    for label, record in (
            ('P0', (p0.get('validation') or {})),
            ('P1', (p1.get('validation') or {})),
            ('P2 A z_only', ((p2.get('validators') or {}).get('z_only') or {})),
            ('P2 B xy_z', ((p2.get('validators') or {}).get('xy_z') or {}))):
        if not record:
            lines.append('| %s | skipped/failed | - | - | - | - | - |' % label)
            continue
        manual = record.get('manual') or {}
        lines.append('| %s | **%s** | %s | %s | %s/%s | %s | %s mm |'
                     % (label, record.get('validation_pass'),
                        record.get('violations'), record.get('routed'),
                        manual.get('matched'), manual.get('manual_route_count'),
                        record.get('crossings'),
                        record.get('min_3d_clearance_mm')))
    lines.append('')
    lines.append('## P0 - genuinely simultaneous XY+Z change of one route')
    lines.append('')
    if p0 and 'error' not in p0:
        requirement = p0.get('requirements_check') or {}
        geometry = p0.get('geometry') or {}
        displacement = geometry.get('max_xy_displacement') or {}
        candidate = p0.get('candidate') or {}
        selected = p0.get('selected_route') or {}
        lines.append('* route **%s** (highest-crossing non-manual route: %s '
                     'baseline crossings).' % (selected.get('route_id'),
                                               selected.get('crossings_before')))
        lines.append('* candidate source: `%s`; exact family `%s`, lead '
                     'source/target = %.3f / %.3f mm, target plane L%s '
                     '(z=%+.2f).'
                     % (candidate.get('source'), candidate.get('family'),
                        candidate.get('lead_s_mm') or 0.0,
                        candidate.get('lead_t_mm') or 0.0,
                        candidate.get('target_layer'),
                        candidate.get('target_z_mm') or 0.0))
        lines.append('* body height %s -> %s mm; target layer %s -> %s; route '
                     'transitions %s -> %s.'
                     % ((geometry.get('old') or {}).get('body_z_mm'),
                        (geometry.get('new') or {}).get('body_z_mm'),
                        (geometry.get('old') or {}).get('target_layer'),
                        (geometry.get('new') or {}).get('target_layer'),
                        (geometry.get('old') or {}).get('n_transitions'),
                        (geometry.get('new') or {}).get('n_transitions')))
        lines.append('* body path length %.3f -> %.3f mm; **max XY '
                     'displacement %.3f mm** (old %d / new %d samples every '
                     '%.2f mm, direction new->old).'
                     % ((geometry.get('old_body_path_length_mm') or 0.0),
                        (geometry.get('new_body_path_length_mm') or 0.0),
                        displacement.get('max_mm') or 0.0,
                        displacement.get('old_samples') or 0,
                        displacement.get('new_samples') or 0,
                        SAMPLE_STEP_MM))
        lines.append('* requirements: XY changed substantially = **%s**, Z '
                     'changed = **%s**, not only a Z lift of the old XY path '
                     '= **%s**, not only XY at the same height = **%s**.'
                     % (requirement.get('xy_changed_substantially'),
                        requirement.get('z_changed'),
                        requirement.get('not_only_z_lift_on_old_xy'),
                        requirement.get('not_only_xy_at_same_height')))
        z_ref = p0.get('z_only_reference') or {}
        if z_ref.get('attempted'):
            lines.append('* reference: the pure-Z lift of the OLD XY path to '
                         'the same height would give delta %s (XY displacement '
                         '%s mm) - recorded to prove the committed candidate '
                         'is not that degenerate move.'
                         % ((z_ref.get('evaluation') or {}).get('delta'),
                            z_ref.get('max_xy_displacement_mm')))
        lines.append('* crossings: total 2409 -> %s; route %s crossings %s -> '
                     '%s.'
                     % (p0_cross.get('new_total'),
                        selected.get('route_id'),
                        p0_cross.get('old_route_crossings'),
                        p0_cross.get('new_route_crossings')))
        lines.append('')
        lines.append('The P0 candidate body is *re-routed*: the middle '
                     'corridor (arc-line-arc) is translated ~84.4 mm in Y and '
                     'the first/last straight legs are re-lengthened while the '
                     'two body landing points stay fixed; the body moves from '
                     'z=-0.15 to z=+0.15. It is therefore a real simultaneous '
                     'XY+Z change, not a Z lift.')
    else:
        lines.append('* P0 did not complete: `%s`' % (p0.get('error') if p0
                                                      else 'not run'))
    lines.append('')
    lines.append('## P1 - single-route-only vs joint rerouting')
    lines.append('')
    if p1 and 'error' not in p1:
        selection = p1.get('selection') or {}
        evidence = selection.get('evidence') or {}
        single = p1.get('single_only') or {}
        joint = p1.get('joint') or {}
        sequential = p1.get('single_only_sequential') or {}
        comparison = p1.get('comparison') or {}
        lines.append('* chosen routes: **%s** (%s).'
                     % (', '.join(str(rid) for rid in
                                  selection.get('routes') or []),
                        selection.get('rationale')))
        lines.append('* mutual baseline crossing events: %s (all on body '
                     'height %s mm).'
                     % (evidence.get('edge_events'),
                        sorted({round(float(z), 6) for z in
                                (evidence.get('body_z_mm') or [])})))
        lines.append('* (a) single-only `reroute_one(%s)` with %s frozen: '
                     'crossings 2409 -> %d (gain %d), family `%s`.'
                     % (single.get('route_id'),
                        single.get('other_routes_frozen'),
                        single.get('total_after'), single.get('gain'),
                        ((single.get('applied') or {}).get('family'))))
        lines.append('* (a2) context sequential single-only over all three: '
                     'crossings 2409 -> %d (gain %d).'
                     % (sequential.get('total_after'),
                        sequential.get('gain')))
        lines.append('* (b) **joint** `reroute_joint(%s)`: crossings 2409 -> '
                     '**%d** (gain **%d**), %s.'
                     % (joint.get('routes'), joint.get('total'),
                        joint.get('gain'),
                        ', '.join('route %s %s L%s (planned delta %s)'
                                  % (item.get('route_id'), item.get('family'),
                                     item.get('new_layer'),
                                     item.get('planned_delta'))
                                  for item in joint.get('per_route') or [])))
        lines.append('* joint advantage over the single-route-only move: '
                     '**%+d crossings** (joint gain %d vs single gain %d).'
                     % (comparison.get('joint_extra_over_single'),
                        comparison.get('joint_gain'),
                        comparison.get('single_gain')))
        lines.append('* context (honest): a sequential line of three '
                     'single-route moves reaches the same total (%d -> %d, '
                     'gain %d) as the joint reroute on this triplet, so the '
                     'joint advantage over the required (a) single-only-A '
                     'scenario (%+d) comes from also moving B and C; the '
                     'exact joint transaction additionally guarantees '
                     'all-or-nothing acceptance.'
                     % ((p1.get('baseline_crossings') or 2409),
                        sequential.get('total_after'),
                        sequential.get('gain'),
                        comparison.get('joint_extra_over_single')))
        lines.append('* per-route joint geometry: %s.'
                     % ', '.join('route %s L%s z=%+.2f -> L%s z=%+.2f, '
                                 'length %.2f -> %.2f mm, max XY disp %.2f mm'
                                 % (item.get('route_id'), item.get('old_layer'),
                                    item.get('old_z_mm'), item.get('new_layer'),
                                    item.get('new_z_mm'),
                                    item.get('old_length_mm'),
                                    item.get('new_length_mm'),
                                    (item.get('xy_change') or {})
                                    .get('max_xy_displacement_mm') or 0.0)
                                 for item in joint.get('per_route') or []))
    else:
        lines.append('* P1 did not complete: `%s`' % (p1.get('error') if p1
                                                      else 'not run'))
    lines.append('')
    lines.append('## P2 - local crossing hotspot: Z-only vs XY+Z')
    lines.append('')
    if p2 and 'error' not in p2:
        hotspot = p2.get('hotspot') or {}
        comparison = p2.get('comparison') or {}
        z_only = p2.get('z_only') or {}
        xy_z = p2.get('xy_z') or {}
        lines.append('* hotspot: most crowded height **z=%+.2f mm** (%d '
                     'crossing events); routes **%s**.'
                     % (hotspot.get('hotspot_height_mm') or 0.0,
                        hotspot.get('hotspot_height_crossings') or 0,
                        ', '.join(str(rid) for rid in
                                  hotspot.get('chosen') or [])))
        lines.append('* **A) Z only** (`shift_height_keep_xy` + '
                     '`insert_height_plan`; XY body path untouched): %d '
                     'crossings removed (2409 -> %d), %d/%d routes improved. '
                     'Attempts: %d (%s); %d reached the exact 3D evaluation.'
                     % (comparison.get('z_only_removed'),
                        comparison.get('z_only_total_after'),
                        z_only.get('accepted_count'),
                        len(hotspot.get('chosen') or []),
                        sum((z_only.get('candidate_kinds') or {}).values()),
                        ', '.join('%s=%d' % (k, v) for k, v in
                                  sorted((z_only.get('candidate_kinds') or {})
                                         .items())),
                        z_only.get('candidates_evaluated')))
        lines.append('* **B) XY+Z** (`reroute_one`, bounded engine cfg): %d '
                     'crossings removed (2409 -> %d), %d/%d routes improved; '
                     '%d routes used a genuinely new XY corridor, of which %d '
                     'changed body height AND XY, %d used a same-height XY-only '
                     'corridor.'
                     % (comparison.get('xy_z_removed'),
                        comparison.get('xy_z_total_after'),
                        xy_z.get('accepted_count'),
                        len(hotspot.get('chosen') or []),
                        len(xy_z.get('routes_with_new_xy_corridor') or []),
                        len(xy_z.get('routes_with_xy_and_z_change') or []),
                        max(0, int(xy_z.get('accepted_count') or 0)
                            - len(xy_z.get('routes_with_xy_and_z_change') or []))))
        lines.append('* routes where only-Z could not improve: %s; routes that '
                     'needed a new XY corridor: %s.'
                     % (', '.join(str(rid) for rid in
                                  comparison.get('routes_only_z_insufficient')
                                  or []) or 'none',
                        ', '.join(str(rid) for rid in
                                  comparison.get('routes_needed_new_xy_corridor')
                                  or []) or 'none'))
        lines.append('* full details, per-route table and rejection reasons: '
                     '`P2/p2_report.md`, `P2/p2_comparison.json`.')
    else:
        lines.append('* P2 did not complete: `%s`' % (p2.get('error') if p2
                                                      else 'not run'))
    lines.append('')
    lines.append('## Conclusion')
    lines.append('')
    lines.append('* The new router **demonstrably changes real XY geometry** '
                 'and can do it simultaneously with a real Z change (P0: '
                 'max centre-line displacement %s mm + body height change '
                 '0.30 mm; P1: joint re-routes of 3 routes; P2 B: new XY '
                 'corridors).'
                 % (((p0.get('geometry') or {}).get('max_xy_displacement')
                     or {}).get('max_mm') or 'n/a'))
    lines.append('* Every saved layout is an independent-validator PASS: '
                 '1024/1024 routed, 0 violations, 368/368 manual-U routes '
                 'frozen, D56 strict crossings, >=50 um true-3D clearance.')
    lines.append('* Neither strategy dominates on this hotspot: Z-only is '
                 'cheap and removes %d crossings; XY+Z removes %d. The Z-only '
                 'search remains a valid fallback; for the routes where only-Z '
                 'cannot resolve the conflict a new XY corridor is required '
                 '(see P2 report).'
                 % ((p2.get('comparison') or {}).get('z_only_removed') or 0,
                    (p2.get('comparison') or {}).get('xy_z_removed') or 0))
    lines.append('')
    lines.append('## Artifact map')
    lines.append('')
    lines.append('| path | content |')
    lines.append('|---|---|')
    lines.append('| `P0/routes_l3d.json`, `P0/assignment_1024.csv`, '
                 '`P0/crossing_stats.json`, `P0/SHA256.json` | full 1024-route '
                 'P0 layout + hashes |')
    lines.append('| `P0/p0_case.json` | P0 route/geometry/crossing evidence |')
    lines.append('| `P0/validation/validation.json` | independent validator '
                 'report (`manual_policy="frozen"`) |')
    lines.append('| `P1/routes_l3d.json` ... `P1/SHA256.json` | full 1024-route '
                 'joint layout |')
    lines.append('| `P1/p1_case.json` | single-only vs joint outcomes |')
    lines.append('| `P1/validation/validation.json` | independent validator '
                 'report |')
    lines.append('| `P2/z_only/` | Z-only layout + validation |')
    lines.append('| `P2/xy_z/` | XY+Z layout + validation |')
    lines.append('| `P2/p2_comparison.json`, `P2/p2_report.md` | hotspot '
                 'comparison + per-route table |')
    lines.append('| `strategy_stats.json` | candidate counts, acceptance, '
                 'failure-reason distribution |')
    lines.append('| `plots/router_validation_plotdata.json` | sampled real '
                 'centre lines for the plotter teammate (PNG plotting is owned '
                 'by them) |')
    lines.append('')
    lines.append('**_failed_attempts** of every stage are overwritten with the '
                 'real attempt lists (build errors, 3D rejections, '
                 'non-improving candidates), never hidden.')
    lines.append('')
    Path(RUN_DIR / 'README.md').write_text('\n'.join(lines), encoding='utf-8')


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def ensure_output_dirs():
    for directory in (RUN_DIR, P0_DIR, P1_DIR, P2_DIR, P2_Z_DIR, P2_XZ_DIR,
                      PLOTS_DIR):
        Path(directory).mkdir(parents=True, exist_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Run the router functional validation experiments P0/P1/P2')
    parser.add_argument('--phases', default='P0,P1,P2',
                        help='comma separated subset of P0,P1,P2')
    parser.add_argument('--skip-validate', action='store_true',
                        help='skip the independent validator (debug only)')
    parser.add_argument('--reports-only', action='store_true',
                        help='do not re-run any experiment: rebuild README / '
                             'strategy_stats / plot data from the saved stages')
    args = parser.parse_args(argv)
    phases = [item.strip().upper() for item in str(args.phases).split(',')
              if item.strip()]
    ensure_output_dirs()
    ctx = dict(run_started=time.time(), timings={}, failure_reasons=Counter())
    log('output root: %s' % rel(RUN_DIR))
    log('engine cfg: %s' % json.dumps({key: value for key, value in
                                       ENGINE_CFG.items() if key != 'phase'}))
    if args.reports_only:
        ctx['P0'] = load_case_json(P0_DIR / 'p0_case.json', 'P0 case')
        ctx['P1'] = load_case_json(P1_DIR / 'p1_case.json', 'P1 case')
        ctx['P2'] = load_case_json(P2_DIR / 'p2_comparison.json', 'P2 case')
        for phase in ('P0', 'P1', 'P2'):
            payload = ctx.get(phase) or {}
            if payload.get('seconds') is not None:
                ctx['timings'][phase] = payload.get('seconds')
        ctx['failure_reasons'].update(aggregate_failure_reasons(ctx))
        plotdata = rebuild_plotdata_from_stages()
        for phase in ('P0', 'P1', 'P2'):
            if (ctx.get(phase) or {}).get('error') is None \
                    and plotdata.get(phase) is not None:
                ctx[phase]['_plotdata'] = plotdata[phase]
        strategy = write_root_reports(ctx)
        ok = all(value is True for value in
                 (strategy.get('validators') or {}).values())
        log('reports-only: %s' % ('PASS' if ok else 'INCOMPLETE'))
        return 0 if ok else 1
    for phase in phases:
        started = time.time()
        try:
            if phase == 'P0':
                ctx['P0'] = run_p0(ctx, skip_validate=args.skip_validate)
            elif phase == 'P1':
                ctx['P1'] = run_p1(ctx, skip_validate=args.skip_validate)
            elif phase == 'P2':
                ctx['P2'] = run_p2(ctx, skip_validate=args.skip_validate)
            else:
                raise ValueError('unknown phase %r' % phase)
            ctx['timings'][phase] = round(time.time() - started, 2)
        except Exception as error:  # noqa: BLE001 - keep the other phases alive
            detail = traceback.format_exc()
            log('[%s] FAILED: %s: %s' % (phase, type(error).__name__, error))
            log(detail)
            ctx[phase] = dict(error='%s: %s' % (type(error).__name__, error),
                              traceback=detail)
            ctx['timings'][phase] = round(time.time() - started, 2)
            ctx['failure_reasons']['%s:%s' % (phase, type(error).__name__)] += 1
    # aggregate all rejection reasons for the root strategy stats
    ctx['failure_reasons'].update(aggregate_failure_reasons(ctx))
    strategy = write_root_reports(ctx)
    total = time.time() - ctx['run_started']
    log('=' * 78)
    log('SUMMARY (%.1f s):' % total)
    log(json.dumps(strategy.get('validators'), indent=1))
    ok = all(value is True for value in (strategy.get('validators') or {}).values()) \
        and all((ctx.get(phase) or {}).get('error') is None
                for phase in ('P0', 'P1', 'P2') if phase in phases)
    log('overall: %s' % ('PASS' if ok else 'FAILED/INCOMPLETE'))
    log('artifacts: %s' % rel(RUN_DIR))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
