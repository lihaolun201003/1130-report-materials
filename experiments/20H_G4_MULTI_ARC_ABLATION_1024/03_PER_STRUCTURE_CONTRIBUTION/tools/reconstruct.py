# -*- coding: utf-8 -*-
"""Deterministic geometry reconstruction for per-patent-structure ablations.

Given a legal 1024-route state and a set of patent structures to disable, this
tool rebuilds **only the routes that actually use one of those structures** in
the ablated grammar:

* the candidate generator runs with ``G4_DISABLED_STRUCTURES`` set, so the
  geometric gate in ``layer2d._iter_candidates`` never emits a candidate that
  contains a disabled structure;
* every rebuilt candidate is re-checked with the independent geometric
  classifier before it is accepted (defence in depth -- the family name is
  never trusted);
* the search order is: frozen ``PLAN_CFG`` -> expanded height/lead search ->
  forced search over **every** 20H body plane; the deterministic minimum exact
  crossing-delta candidate wins;
* a route with no legal alternative stays untouched and is reported as a
  residual (never deleted, never force-replaced).

This is the "geometric substitution cost" step of the per-structure experiment:
``crossings_after - crossings_before`` is measured on the same 1024-route state,
before any G4 optimisation.

Usage::

    python .../reconstruct.py --start-dir <state> --out-dir <dir> \
        --disable 6a [--all-multi-arc] [--no-validator]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-dir', required=True)
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--disable', nargs='*', default=[],
                        help='patent structures to remove: 6a 6b 6c 6d 7a 7b 7c')
    parser.add_argument('--all-multi-arc', action='store_true',
                        help='remove every local planar multi-arc region '
                             '(NoMultiArc group); implies --disable all')
    parser.add_argument('--no-escalation', action='store_true')
    parser.add_argument('--no-forced-fallback', action='store_true')
    parser.add_argument('--max-routes', type=int, default=0,
                        help='debug only')
    parser.add_argument('--skip-validator', action='store_true')
    parser.add_argument('--baseline-dir', default=None)
    parser.add_argument('--label', default='')
    return parser


def _read_json(path, default=None):
    path = Path(path)
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding='utf-8-sig'))


def _sha256(path):
    import hashlib
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv=None):
    args = build_parser().parse_args(argv)
    disable = sorted({str(item).strip().lower() for item in args.disable
                      if str(item).strip()})
    if args.all_multi_arc:
        disable = []
    # the switch must be in force BEFORE layer2d is imported
    os.environ['G4_DISABLED_STRUCTURES'] = ' '.join(disable)
    if args.all_multi_arc:
        os.environ['G4_ENABLE_MULTI_ARC'] = '0'

    sys.path.insert(0, str(ROOT))
    from four_side_1024.fanout1024.coldstart20 import bootstrap as B
    B.install()
    B.assert_20_height_profile('reconstruct')

    from four_side_1024.fanout1024 import layer2d as L2
    from four_side_1024.fanout1024.coldstart20 import model20 as M20
    from four_side_1024.fanout1024.xyzrouter import route_builder as RB
    from four_side_1024.fanout1024.xyzrouter.g4 import arm_base as AB
    from four_side_1024.fanout1024.xyzrouter.g4 import artifacts as ART
    from four_side_1024.fanout1024.xyzrouter.g4 import joint_world as JW
    from four_side_1024.fanout1024.xyzrouter.g4 import paths as GP
    from four_side_1024.fanout1024.coldstart20 import convert_multiarc20 as CV
    from four_side_1024.fanout1024.coldstart20 import run_multiarc as MA

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / 'reconstruct.log'
    log_file = log_path.open('w', encoding='utf-8')

    def log(message):
        line = '[%s] %s' % (time.strftime('%Y-%m-%dT%H:%M:%S'), message)
        print(line, flush=True)
        log_file.write(line + '\n')
        log_file.flush()

    start_dir = Path(args.start_dir)
    if not start_dir.is_absolute():
        start_dir = ROOT / start_dir
    if not (start_dir / 'routes_l3d.json').is_file():
        log('[recon] FATAL no start state: %s' % start_dir)
        return 2

    log('[recon] profile=%s planes=%d' % (M20.PROFILE, len(M20.PLANE_IDS)))
    log('[recon] multi_arc_enabled=%s disabled=%s' % (
        L2.MULTI_ARC_POLICY['enabled'], sorted(L2.disabled_structures())))
    log('[recon] start=%s out=%s' % (start_dir, out_dir))

    spec = AB.ArmSpec('structure_rebuild', out_dir=out_dir,
                      start_dir=str(start_dir), log=log)
    ctx = AB.ArmContext(spec).load()
    state = ctx.state
    start_crossings = int(state.total)
    start_sha = str(ctx.baseline['routes_sha256'])
    start_assignment_sha = str(ctx.baseline['assignment_sha256'])
    jw = JW.JointWorld(state, ledger=ctx.ledger, log=log)
    log('[recon] start crossings=%d routes=%d sha=%s' % (
        start_crossings, len(state.routes), start_sha))

    classifier = L2._structure_classifier()
    log('[recon] classifier=%s' % (
        'patent_structures' if classifier is not None else 'MISSING'))
    if classifier is None and not args.all_multi_arc:
        log('[recon] FATAL the geometric classifier is required for '
            'per-structure ablation')
        return 2

    def route_tags(route):
        if args.all_multi_arc:
            prims = []
            for part in route.get('parts') or ():
                prims.extend(part.get('primitives') or ())
            return {'multi_arc'} if L2.local_multi_arc_regions(prims) else set()
        return L2.structure_types_of_route(route)

    targets = [int(rid) for rid in sorted(state.routes)
               if route_tags(state.routes[rid]) & set(disable or ['multi_arc'])]
    if args.max_routes:
        targets = targets[:int(args.max_routes)]
    log('[recon] target routes using %s: %d'
        % (sorted(disable) if disable else 'multi_arc', len(targets)))

    def accepted(route):
        if args.all_multi_arc:
            prims = []
            for part in route.get('parts') or ():
                prims.extend(part.get('primitives') or ())
            return not L2.local_multi_arc_regions(prims)
        tags = L2.structure_types_of_route(route)
        return not (tags & set(disable))

    attempts_catalogue = {
        'frozen': dict(JW.PLAN_CFG),
        'expanded': dict(CV.ESCALATION_CFG),
    }
    started = time.time()
    records = []
    residual = []
    for position, rid in enumerate(targets, 1):
        rid = int(rid)
        t0 = time.time()
        attempts = []
        chosen = None
        plan_cfg_used = None
        try:
            order = [] if args.no_escalation else ['frozen', 'expanded']
            if not order:
                order = ['frozen']
            for stage in order:
                cfg = attempts_catalogue[stage]
                cands = jw.plan_candidates(rid, cfg=cfg, mode='clean')
                legal = [c for c in cands if accepted(c.route)]
                attempts.append(dict(stage=stage, candidates=len(cands),
                                     legal=len(legal)))
                if legal:
                    chosen = legal[0]
                    plan_cfg_used = stage
                    break
            if chosen is None and not args.no_forced_fallback:
                best = None
                for plane in RB.BODY_PLANE_IDS:
                    z = float(RB.PLANE_Z[int(plane)])
                    cands = jw.plan_forced(
                        rid, int(plane), z,
                        cfg=dict(max_lead_pairs=6, max_return=8,
                                 d56_top=64, prescreen_candidates=640,
                                 max_candidates=2560),
                        mode='clean')
                    legal = [c for c in cands if accepted(c.route)]
                    attempts.append(dict(stage='forced', plane=int(plane),
                                         candidates=len(cands),
                                         legal=len(legal)))
                    if legal:
                        candidate = legal[0]
                        key = (candidate.delta if candidate.delta is not None
                               else 10 ** 9, int(candidate.layer))
                        if best is None or key < best[0]:
                            best = (key, candidate)
                if best is not None:
                    chosen = best[1]
                    plan_cfg_used = 'forced'
        except Exception as error:                           # noqa: BLE001
            records.append(dict(route_id=rid, status='error',
                                error=repr(error), attempts=attempts))
            residual.append(rid)
            log('[recon] route %d planner error: %r' % (rid, error))
            continue
        if chosen is None:
            residual.append(rid)
            records.append(dict(route_id=rid, status='no_legal_candidate',
                                old_types=sorted(route_tags(
                                    state.routes[rid])), attempts=attempts))
            continue
        old_route = state.routes[rid]
        old_row = dict(state.row(rid))
        old_layer = int(old_row.get('target_layer') or 0)
        row = RB.row_for_target(old_row, int(chosen.layer),
                                float(chosen.z_mm))
        commit = jw.replace_one(rid, chosen.route, row=row,
                                note='structure_rebuild[%s]'
                                     % ','.join(disable or ['multi_arc']))
        records.append(dict(
            route_id=rid, status='rebuilt', stage=plan_cfg_used,
            old_types=sorted(route_tags(old_route)),
            new_types=sorted(route_tags(state.routes[rid])),
            old_layer=old_layer, new_layer=int(chosen.layer),
            old_z_mm=float(old_row.get('target_z_mm') or 0.0),
            new_z_mm=float(chosen.z_mm),
            family=str(chosen.family or ''),
            delta=int(chosen.delta if chosen.delta is not None else 0),
            commit_delta=int(commit.get('delta') or 0),
            total_after=int(state.total),
            attempts=attempts,
            seconds=round(time.time() - t0, 2)))
        if position % 10 == 0:
            log('[recon] %d/%d rebuilt=%d total=%d residual=%d (%.0fs)'
                % (position, len(targets), len(records) - len(residual),
                   state.total, len(residual), time.time() - t0))

    left = [int(rid) for rid in sorted(state.routes)
            if route_tags(state.routes[rid]) & set(disable or ['multi_arc'])]
    log('[recon] done targets=%d residual=%d remaining=%d total=%d->%d (%.0fs)'
        % (len(targets), len(residual), len(left), start_crossings,
           state.total, time.time() - started))

    CV.write_layer_planes(out_dir, state)
    hashes = ART.flush(state, ctx.baseline, out_dir,
                       note='deterministic %s structure reconstruction'
                            % (','.join(disable) or 'all-multi-arc'),
                       log=log)

    validation = None
    if not args.skip_validator:
        baseline_dir = args.baseline_dir
        if baseline_dir is None:
            baseline_dir = str(GP.AUTHORITY_DIR)
        log('[recon] independent validator ...')
        validation = MA.run_validator_xyz(out_dir, out_dir / 'validation_xyz',
                                          baseline_dir=baseline_dir)
        log('[recon] validator pass=%s violations=%s'
            % (validation.get('validation_pass'),
               validation.get('violation_count')))

    report = dict(
        schema='g4_structure_reconstruction_v1',
        label=args.label,
        profile='20_height_raised',
        start_dir=str(start_dir),
        start_routes_sha256=start_sha,
        start_assignment_sha256=start_assignment_sha,
        start_crossings=start_crossings,
        disabled_structures=(sorted(disable) if disable else ['multi_arc']),
        all_multi_arc=bool(args.all_multi_arc),
        targets=len(targets),
        rebuilt=int(len(records) - len(residual)),
        residual=int(len(residual)),
        residual_route_ids=residual,
        remaining_with_disabled=left,
        crossings_after=int(state.total),
        crossing_delta=int(state.total) - start_crossings,
        total_length_mm=round(float(state.total_length()), 6),
        seconds=round(time.time() - started, 2),
        ledger=ctx.ledger.summary(),
        routes_sha256=hashes.get('routes_l3d_json'),
        assignment_sha256=hashes.get('assignment_1024_csv'),
        records=records,
        validation=validation,
        planner=dict(JW.PLAN_CFG),
        planner_escalation=dict(CV.ESCALATION_CFG),
        classifier=str(getattr(classifier, '__file__', None)),
        structure_counters=L2.structure_counters_snapshot(),
    )
    report_path = out_dir / 'reconstruction_report.json'
    GP.write_json(report_path, report)
    log('[recon] report %s feasible=%s delta=%+d'
        % (report_path, not residual and not left, report['crossing_delta']))
    log_file.close()
    print(json.dumps({key: report[key] for key in (
        'disabled_structures', 'targets', 'rebuilt', 'residual',
        'remaining_with_disabled', 'start_crossings', 'crossings_after',
        'crossing_delta', 'routes_sha256')}, ensure_ascii=False, indent=1),
          flush=True)
    return 0 if (not residual and not left) else 4


if __name__ == '__main__':
    raise SystemExit(main())
