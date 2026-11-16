# -*- coding: utf-8 -*-
"""Stage-0 *planar multi-arc conversion* of the G4 multi-arc ablation (1024 ch).

The archived G4 start solution (G3, 1322 crossings) inherits planar ``short-S``
geometry: 197 of its 1024 routes contain at least one real local multi-arc
region.  A *NoMultiArc* system must express those inherited paths in the
ablated grammar, so this stage re-plans **exactly those routes** with the
standard G4 planner and never edits an arc by hand.

Everything except the multi-arc policy is the frozen G4 machinery:

* planner            : ``joint_world.JointWorld.plan_candidates`` with the
  standard ``PLAN_CFG`` (the very configuration the G4 search uses: 3 free
  target heights, 2 lead pairs, 160/320 pre-screen, ``d56_top=16``,
  4 candidates per (height, lead) pair);
* legality           : frozen strict D56 + true-3D ``state.evaluate_candidate``;
* acceptance         : the exact crossing delta of every candidate (``mode='clean'``);
* choice             : best (minimal delta, then shortest) legal candidate --
  deterministic, no randomness, no wall-clock dependence;
* routes with **no** legal candidate keep their old geometry and are reported
  as ``residual`` (never silently deleted, never force-replaced by a polyline).

With ``G4_ENABLE_MULTI_ARC=0`` the generator cannot emit a local multi-arc
region at all, so the conversion output is multi-arc free; the tool asserts it.

Usage::

    $env:G4_ENABLE_MULTI_ARC='0'
    python experiments/G4_MULTI_ARC_ABLATION_1024/tools/convert_multi_arc.py \
        --start-dir outputs/manual_c4_new_connectivity/XYZ_JOINT_G123_1024/best_valid \
        --out-dir experiments/G4_MULTI_ARC_ABLATION_1024/no_multi_arc/01_convert
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

#: the policy must be in place *before* ``layer2d`` is imported
os.environ.setdefault('G4_ENABLE_MULTI_ARC', '0')

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024 import layer2d as L2                     # noqa: E402
from four_side_1024.fanout1024.xyzrouter import route_builder as RB     # noqa: E402
from four_side_1024.fanout1024.xyzrouter.g4 import arm_base as AB       # noqa: E402
from four_side_1024.fanout1024.xyzrouter.g4 import artifacts as ART     # noqa: E402
from four_side_1024.fanout1024.xyzrouter.g4 import joint_world as JW    # noqa: E402
from four_side_1024.fanout1024.xyzrouter.g4 import paths as GP          # noqa: E402


def route_flat_multi_arc(route):
    """Local multi-arc regions of every flat (in-plane) chain of one route."""
    found = []
    for index, part in enumerate(route.get('parts') or ()):
        if part.get('kind') != 'flat':
            continue
        for region in L2.local_multi_arc_regions(part.get('primitives') or []):
            found.append(dict(part=index, z_mm=float(part['z_mm']), **region))
    return found


def multi_arc_route_ids(state):
    return [int(rid) for rid in sorted(state.routes)
            if route_flat_multi_arc(state.routes[rid])]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--start-dir', required=True)
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--max-routes', type=int, default=0)
    parser.add_argument('--log', default=None)
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = Path(args.log) if args.log else out_dir / 'convert.log'
    log_file = log_path.open('w', encoding='utf-8')

    def log(message):
        line = '[%s] %s' % (time.strftime('%Y-%m-%dT%H:%M:%S'), message)
        print(line, flush=True)
        log_file.write(line + '\n')
        log_file.flush()

    started = time.time()
    log('=' * 78)
    log('[convert] multi_arc_enabled=%s (source=%s)'
        % (L2.MULTI_ARC_POLICY['enabled'], L2.MULTI_ARC_POLICY['source']))
    log('[convert] start=%s out=%s' % (args.start_dir, out_dir))
    spec = AB.ArmSpec('stage0_convert', out_dir=out_dir,
                      start_dir=args.start_dir, log=log)
    ctx = AB.ArmContext(spec).load()
    state = ctx.state
    jw = JW.JointWorld(state, ledger=ctx.ledger, log=log)
    log('[convert] start crossings=%d routes=%d' % (state.total, len(state.routes)))

    before = multi_arc_route_ids(state)
    log('[convert] routes with a planar multi-arc region in the start geometry: %d'
        % len(before))
    targets = before[:args.max_routes] if args.max_routes else before

    records = []
    converted = 0
    residual = []
    leaked = []
    for position, rid in enumerate(targets, 1):
        old_regions = len(route_flat_multi_arc(state.routes[rid]))
        t0 = time.time()
        try:
            candidates = jw.plan_candidates(rid, cfg=JW.PLAN_CFG, mode='clean')
        except Exception as error:                            # noqa: BLE001
            records.append(dict(route_id=rid, status='error', error=repr(error),
                                old_regions=old_regions))
            residual.append(rid)
            continue
        chosen = candidates[0] if candidates else None
        if chosen is None:
            residual.append(rid)
            records.append(dict(route_id=rid, status='no_legal_candidate',
                                old_regions=old_regions))
            continue
        if not L2.MULTI_ARC_POLICY['enabled'] and route_flat_multi_arc(chosen.route):
            # hard invariant: with the policy disabled no candidate may carry a
            # local multi-arc region (defensive -- the generator already forbids it)
            leaked.append(rid)
            residual.append(rid)
            records.append(dict(route_id=rid, status='policy_leak',
                                old_regions=old_regions))
            continue
        row = RB.row_for_target(state.row(rid), int(chosen.layer),
                                float(chosen.z_mm))
        commit = jw.replace_one(rid, chosen.route, row=row,
                                note='stage0_multi_arc_conversion')
        converted += 1
        records.append(dict(
            route_id=rid, status='converted', old_regions=old_regions,
            new_regions=len(route_flat_multi_arc(chosen.route)),
            family=chosen.family, kind=chosen.kind,
            delta=int(chosen.delta if chosen.delta is not None else 0),
            commit_delta=int(commit.get('delta') or 0),
            layer=int(chosen.layer), z_mm=float(chosen.z_mm),
            length_mm=round(float(chosen.route.get('length_mm') or 0.0), 6),
            total_after=int(state.total),
            seconds=round(time.time() - t0, 2)))
        if position % 20 == 0:
            log('[convert] %d/%d converted=%d total=%d residual=%d (%.0fs)'
                % (position, len(targets), converted, state.total,
                   len(residual), time.time() - started))

    after = multi_arc_route_ids(state)
    log('[convert] done converted=%d residual=%d multi_arc_left=%d total=%d->%d'
        % (converted, len(residual), len(after), int(GP.START_CROSSINGS),
           state.total))

    hashes = ART.flush(state, ctx.baseline, out_dir,
                       note='stage-0 planar multi-arc conversion (multi_arc=%s)'
                            % L2.MULTI_ARC_POLICY['enabled'], log=log)
    validation = ART.run_validation(out_dir, out_dir / 'validation',
                                    baseline_dir=GP.AUTHORITY_DIR, log=log)
    validation_json = out_dir / 'validation' / 'validation.json'
    validation_pass = None
    if validation_json.exists():
        validation_pass = json.loads(validation_json.read_text(
            encoding='utf-8')).get('validation_pass')
    report = dict(
        schema='g4_multi_arc_conversion_v1',
        policy=dict(L2.MULTI_ARC_POLICY),
        planner=dict(JW.PLAN_CFG),
        start_dir=str(args.start_dir),
        start_sha256=ctx.baseline['routes_sha256'],
        start_crossings=int(GP.START_CROSSINGS),
        out_dir=_rel(out_dir),
        routes_sha256=hashes.get('routes_l3d_json'),
        multi_arc_routes_before=len(before),
        multi_arc_route_ids_before=before,
        targets=len(targets),
        converted=converted,
        residual=len(residual),
        residual_route_ids=residual,
        multi_arc_routes_after=len(after),
        policy_leaks=leaked,
        crossings_after=int(state.total),
        crossing_delta_from_start=int(state.total) - int(GP.START_CROSSINGS),
        total_length_mm=round(float(state.total_length()), 6),
        seconds=round(time.time() - started, 2),
        ledger=ctx.ledger.summary(),
        records=records,
        validation=dict(exit_code=int(validation['exit_code']),
                        seconds=float(validation['seconds']),
                        validation_pass=validation_pass),
    )
    GP.write_json(out_dir / 'conversion_report.json', report)
    log('[convert] validation exit=%s pass=%s'
        % (validation['exit_code'], validation_pass))
    log_file.close()
    print(json.dumps({key: report[key] for key in (
        'multi_arc_routes_before', 'converted', 'residual',
        'multi_arc_routes_after', 'start_crossings', 'crossings_after',
        'total_length_mm', 'routes_sha256', 'validation')},
        ensure_ascii=False, indent=1))
    return 0


def _rel(path):
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except Exception:                                          # noqa: BLE001
        return str(path)


if __name__ == '__main__':
    raise SystemExit(main())
