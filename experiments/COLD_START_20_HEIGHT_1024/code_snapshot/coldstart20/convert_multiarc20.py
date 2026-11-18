# -*- coding: utf-8 -*-
"""Stage-0 *planar multi-arc conversion* of the 20-height 1024-route ablation.

This is the 20-height port of the archived 21-height tool
``experiments/G4_MULTI_ARC_ABLATION_1024/tools/convert_multi_arc.py``
(read-only evidence).  The archived file itself is **not** modified.

Why a conversion is needed
--------------------------
The inherited ON start (the 20H G3 ``best_valid``) may contain planar
``short-S`` geometry: two tangent, opposite-sweep R15 arcs with no straight line
between them.  A strict *NoMultiArc* system must express those connections in
the ablated grammar, so this stage re-plans **exactly the routes that carry at
least one real local multi-arc region** with the standard G4 planner.  It never
edits an arc by hand and never replaces a route by a polyline.

Everything except the multi-arc policy is the frozen G4 machinery
---------------------------------------------------------------
* planner    : ``joint_world.JointWorld.plan_candidates`` with the standard
               ``JW.PLAN_CFG`` (3 free target heights, 2 lead pairs,
               160/320 pre-screen, ``d56_top=16``, 4 candidates per
               height/lead option) -- the exact configuration the G4 search
               uses;
* legality   : frozen strict D56 + true-3D ``state.evaluate_candidate``;
* acceptance : the exact crossing delta of every candidate (``mode='clean'``);
* choice     : best (minimal exact crossing delta, then shortest) legal
               candidate -- deterministic, no randomness, no wall-clock
               dependence;
* residual   : a route with **no** legal candidate keeps its old geometry and
               is reported as ``residual`` (never silently deleted, never
               force-replaced); the pre-registered rule of
               ``00_audit/multiarc.md`` §3.3 then says the strict common start
               does not exist for this start, no diluted OFF arm may be run;
* invariants : all non-target routes are byte-identical afterwards; the output
               must contain **0** local multi-arc regions; 1024 routes, 0
               failed; the frozen independent validator
               (``reheight21.validate21`` machinery via
               ``xyzrouter.validate_xyz --manual-policy fully_optimizable``)
               must pass under the 20-height profile.

Cost separation (mandatory, see the audit)
------------------------------------------
This stage measures effect **A** = the exact crossing delta caused by
re-expressing the inherited ON geometry in the OFF grammar.  It is *not* part
of effect **B** (the ON/OFF search-ability difference measured from the common
converted start); the two must never be added into a "value of multi-arc"
number.

Usage
-----
::

    .venv\\Scripts\\python.exe -m \\
        four_side_1024.fanout1024.coldstart20.convert_multiarc20 \\
        --start-dir <20H G3 best_valid> \\
        --out-dir   experiments/COLD_START_20_HEIGHT_1024/09_multi_arc_ablation/common_start_off \\
        [--baseline-dir <20H identity authority>] [--max-routes N]

The G4 driver ``run_multiarc.py convert`` calls :func:`main` with the frozen
experiment paths and turns the result into ``OFF_FEASIBILITY.json``.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

#: the multi-arc policy must be in place *before* ``layer2d`` is imported.
#: ``setdefault`` keeps an explicit ``G4_ENABLE_MULTI_ARC=1`` from being
#: silently overridden, but the converter then refuses to run (see main()).
os.environ.setdefault('G4_ENABLE_MULTI_ARC', '0')

from . import bootstrap as B                     # noqa: E402  installs 20H profile
from . import model20 as M                       # noqa: E402
from . import paths20 as P20                     # noqa: E402

ROOT = Path(__file__).resolve().parents[3]

SCHEMA = 'coldstart20_multi_arc_conversion_v1'

#: bootstrap preamble for every validator child process.  The child must import
#: ``coldstart20.bootstrap`` *before* the validator modules, otherwise
#: ``reheight21.model`` resolves to the frozen 21-height table in the child.
BOOTSTRAP_PREAMBLE = (
    "import sys, runpy\n"
    "from four_side_1024.fanout1024.coldstart20 import bootstrap as _coldstart20\n"
    "_coldstart20.install()\n"
    "_coldstart20.assert_20_height_profile('multiarc-validator-child')\n"
    "sys.argv[0] = 'validate_xyz'\n"
    "runpy.run_module("
    "'four_side_1024.fanout1024.xyzrouter.validate_xyz', run_name='__main__')\n"
)


# ===========================================================================
# small IO helpers (no G4 import needed before the policy is fixed)
# ===========================================================================
def _read_json(path, default=None):
    path = Path(path)
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding='utf-8-sig'))


def _write_json(path, payload, indent=1):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=indent,
                               default=str) + '\n', encoding='utf-8')
    return path


def _sha256(path):
    import hashlib
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _rel(path):
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except Exception:                                       # noqa: BLE001
        return str(path)


def _crossings_from_artifacts(start_dir):
    """Reported crossing total of a start dir (crossing_stats / summary)."""
    for name in ('crossing_stats.json', 'summary.json'):
        payload = _read_json(Path(start_dir) / name)
        if not isinstance(payload, dict):
            continue
        value = ((payload.get('totals') or {}).get('crossings')
                 or payload.get('crossings'))
        if value is not None:
            return int(value)
    return None


# ===========================================================================
# multi-arc detection (frozen policy definition)
# ===========================================================================
def route_flat_multi_arc(route, layer2d):
    """Local multi-arc regions of every flat (in-plane) chain of one route."""
    found = []
    for index, part in enumerate(route.get('parts') or ()):
        if part.get('kind') != 'flat':
            continue
        for region in layer2d.local_multi_arc_regions(
                part.get('primitives') or []):
            found.append(dict(part=index, z_mm=float(part['z_mm']), **region))
    return found


def multi_arc_route_ids(state, layer2d):
    return [int(rid) for rid in sorted(state.routes)
            if route_flat_multi_arc(state.routes[rid], layer2d)]


# ===========================================================================
# layer_planes.json (20H model table for the converted run dir)
# ===========================================================================
def _assigned_counts(state):
    counts = Counter()
    for rid in state.routes:
        row = state.rows.get(int(rid)) or {}
        try:
            counts[int(float(row['target_layer']))] += 1
        except (KeyError, TypeError, ValueError):
            continue
    return dict(counts)


def write_layer_planes(out_dir, state):
    """Write the 20-height ``layer_planes.json`` contract next to the state.

    ``validate_xyz`` uses ``<run>/layer_planes.json`` when present (instead of
    falling back to the baseline's table); writing it here makes the converted
    common start self-describing: the validator reads the same 20 heights the
    conversion targeted.
    """
    payload = M.layer_planes_payload(assigned=_assigned_counts(state))
    return _write_json(Path(out_dir) / 'layer_planes.json', payload)


# ===========================================================================
# validator wrapper (fresh process, 20H profile installed first)
# ===========================================================================
def run_validator_xyz(run_dir, out_dir, baseline_dir=None,
                      manual_policy='fully_optimizable', timeout=None):
    """Run the frozen independent validator in a fresh 20H-profile process."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, '-c', BOOTSTRAP_PREAMBLE,
           '--run-dir', str(run_dir), '--out-dir', str(out_dir)]
    if baseline_dir:
        cmd.extend(['--baseline-dir', str(baseline_dir)])
    cmd.extend(['--manual-policy', str(manual_policy)])
    started = time.time()
    result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                            encoding='utf-8', errors='replace',
                            timeout=timeout)
    seconds = round(time.time() - started, 2)
    log_path = out_dir / 'validator.log'
    log_path.write_text(
        '#' * 78 + '\n# %s\n# exit=%s seconds=%.2f\n# %s\n'
        % (' '.join(cmd), result.returncode, seconds, '#' * 78)
        + (result.stdout or '') + '\n--- stderr ---\n' + (result.stderr or ''),
        encoding='utf-8')
    report = _read_json(out_dir / 'validation.json', default={}) or {}
    counts = report.get('counts') or {}
    return dict(
        exit_code=int(result.returncode),
        seconds=seconds,
        validation_pass=report.get('validation_pass'),
        geometry_pass=report.get('geometry_pass'),
        contract_pass=report.get('contract_pass'),
        violation_count=report.get('violation_count'),
        model_plane_count=(report.get('model') or {}).get('plane_count'),
        model_source=(report.get('model') or {}).get('source'),
        routed=counts.get('routed'),
        failed=counts.get('failed'),
        same_plane_crossings=counts.get('same_plane_crossings'),
        crossing_pairs=counts.get('same_plane_crossing_pairs'),
        min_3d_clearance_mm=counts.get('min_3d_clearance_mm'),
        min_non_crossing_centerline_mm=counts.get(
            'min_non_crossing_centerline_mm'),
        min_flat_arc_radius_mm=counts.get('min_flat_arc_radius_mm'),
        run_dir=str(run_dir), out_dir=str(out_dir),
        validation_json=str(out_dir / 'validation.json'),
        validator_log=str(log_path),
        manual_policy=str(manual_policy),
        baseline_dir=(str(baseline_dir) if baseline_dir else None))


# ===========================================================================
# 21H-style "same validator" diagnostic (validate21 under the 20H bootstrap)
# ===========================================================================
def run_validate21(run_dir, out_dir):
    """Diagnostic run of the profile-generic ``reheight21.validate21``.

    This is the cold-start chain's validator (``coldstart20.run_validate``).
    It is recorded but **not** a blocking gate for a G4 conversion: its
    assignment contract (``SPEC_MANUAL_FIXED``) describes the stage-A
    assignment, while a G4/G3 state legitimately re-targets heights.  The
    blocking gate is the G4 validator :func:`run_validator_xyz`.
    """
    from . import run_validate
    try:
        code = run_validate.main(['--run-dir', str(run_dir),
                                  '--out-dir', str(out_dir)])
    except Exception as error:                              # noqa: BLE001
        return dict(blocking=False, ok=False, error=repr(error))
    summary = _read_json(Path(run_dir) / 'coldstart20_validation_summary.json',
                         default={}) or {}
    report = _read_json(Path(out_dir) / 'validation.json', default={}) or {}
    return dict(blocking=False, ok=bool(report.get('validation_pass')),
                exit_code=int(code),
                validation_pass=report.get('validation_pass'),
                violation_count=report.get('violation_count'),
                model_plane_count=(report.get('model') or {}).get('plane_count'),
                model_source=(report.get('model') or {}).get('source'),
                summary=dict(summary))


# ===========================================================================
# conversion
# ===========================================================================
def build_parser():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--start-dir', default=None,
                        help='20H ON start (default: the 20H G3 best_valid)')
    parser.add_argument('--out-dir', default=None,
                        help='converted common start (default: '
                             '<MULTIARC_ROOT>/common_start_off)')
    parser.add_argument('--baseline-dir', default=None,
                        help='identity/port authority for the validator')
    parser.add_argument('--max-routes', type=int, default=0,
                        help='debug only: convert at most N target routes')
    parser.add_argument('--log', default=None)
    parser.add_argument('--with-validate21', dest='with_validate21',
                        action='store_true', default=True,
                        help='record the non-blocking validate21 diagnostic')
    parser.add_argument('--no-validate21', dest='with_validate21',
                        action='store_false')
    parser.add_argument('--skip-validator', action='store_true',
                        help='debug only: do not run the independent validator')
    return parser


def _resolve_authority(explicit, paths):
    if explicit:
        return Path(explicit)
    candidates = [Path(paths.AUTHORITY_DIR), Path(P20.INIT_RUN)]
    for candidate in candidates:
        if (candidate / 'routes_l3d.json').is_file() and \
                (candidate / 'assignment_1024.csv').is_file():
            return candidate
    return candidates[0]


def main(argv=None):
    args = build_parser().parse_args(argv)
    B.install()
    B.assert_20_height_profile('convert_multiarc20')

    out_dir = Path(args.out_dir) if args.out_dir else (
        Path(P20.MULTIARC) / 'common_start_off')
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = Path(args.log) if args.log else out_dir / 'convert.log'
    log_file = log_path.open('w', encoding='utf-8')

    def log(message):
        line = '[%s] %s' % (time.strftime('%Y-%m-%dT%H:%M:%S'), message)
        print(line, flush=True)
        log_file.write(line + '\n')
        log_file.flush()

    # the G4 path module fingerprints the 20H G3 start at import time; make it
    # use the *explicitly requested* start instead of requiring the default
    # ``XYZ_RUN/best_valid`` to be present (useful for the dry-run / tests and
    # harmless in the real protocol, where ``run_multiarc.py start`` has
    # verified exactly this dir).
    start_dir = Path(args.start_dir) if args.start_dir else None
    if start_dir is None:
        from ..xyzrouter import paths as XP
        start_dir = Path(XP.XYZ_RUN_DIR) / 'best_valid'
    if not (start_dir / 'routes_l3d.json').is_file():
        log('[convert] FATAL start dir has no routes_l3d.json: %s' % start_dir)
        log_file.close()
        return 2
    os.environ.setdefault('COLDSTART20_START_SHA',
                          _sha256(start_dir / 'routes_l3d.json'))
    crossings = _crossings_from_artifacts(start_dir)
    if crossings is not None:
        os.environ.setdefault('COLDSTART20_START_CROSSINGS', str(int(crossings)))

    from .. import layer2d as L2
    from ..xyzrouter import route_builder as RB
    from ..xyzrouter.g4 import arm_base as AB
    from ..xyzrouter.g4 import artifacts as ART
    from ..xyzrouter.g4 import joint_world as JW
    from ..xyzrouter.g4 import paths as GP

    if L2.MULTI_ARC_POLICY.get('enabled'):
        # a converter that runs with the policy ON would "convert" nothing
        log('[convert] FATAL multi_arc policy is enabled (%s). The converter '
            'must be the first pipeline import after setting '
            'G4_ENABLE_MULTI_ARC=0; re-run in a fresh process.'
            % L2.MULTI_ARC_POLICY)
        log_file.close()
        return 2

    started = time.time()
    log('=' * 78)
    log('[convert] profile=%s planes=%d interfaces=%s'
        % (M.PROFILE, len(M.PLANE_IDS), M.INTERFACE_Z))
    log('[convert] multi_arc_enabled=%s (source=%s)'
        % (L2.MULTI_ARC_POLICY['enabled'], L2.MULTI_ARC_POLICY['source']))
    log('[convert] start=%s' % start_dir)
    log('[convert] out=%s' % out_dir)

    spec = AB.ArmSpec('stage0_convert', out_dir=out_dir,
                      start_dir=str(start_dir), log=log)
    ctx = AB.ArmContext(spec).load()
    state = ctx.state
    #: exact crossing total of the loaded start (never a global constant)
    start_crossings = int(state.total)
    start_sha = str(ctx.baseline['routes_sha256'])
    start_assignment_sha = str(ctx.baseline['assignment_sha256'])
    jw = JW.JointWorld(state, ledger=ctx.ledger, log=log)
    log('[convert] start crossings=%d routes=%d sha256=%s'
        % (start_crossings, len(state.routes), start_sha))

    before = multi_arc_route_ids(state, L2)
    log('[convert] routes with a planar multi-arc region in the start geometry: '
        '%d (recomputed for 20H; the 21H value 197 is not assumed)'
        % len(before))
    targets = before[:args.max_routes] if args.max_routes else list(before)

    #: invariant: every non-target route must be bit-identical afterwards
    def _canonical(route):
        return json.dumps(route, sort_keys=True, ensure_ascii=False)

    non_target_ids = [int(rid) for rid in sorted(state.routes)
                      if int(rid) not in set(targets)]
    non_target_before = {rid: _canonical(state.routes[rid])
                         for rid in non_target_ids}

    records = []
    converted = 0
    residual = []
    leaked = []
    errors = []
    for position, rid in enumerate(targets, 1):
        rid = int(rid)
        old_regions = len(route_flat_multi_arc(state.routes[rid], L2))
        t0 = time.time()
        try:
            candidates = jw.plan_candidates(rid, cfg=JW.PLAN_CFG,
                                            mode='clean')
        except Exception as error:                          # noqa: BLE001
            errors.append(rid)
            residual.append(rid)
            records.append(dict(route_id=rid, status='error',
                                old_regions=old_regions, error=repr(error)))
            log('[convert] route %d planner error: %r' % (rid, error))
            continue
        chosen = candidates[0] if candidates else None
        if chosen is None:
            residual.append(rid)
            records.append(dict(route_id=rid, status='no_legal_candidate',
                                old_regions=old_regions))
            continue
        if not L2.MULTI_ARC_POLICY['enabled'] and \
                route_flat_multi_arc(chosen.route, L2):
            # hard invariant: with the policy disabled no candidate may carry
            # a local multi-arc region (defensive -- the generator forbids it)
            leaked.append(rid)
            residual.append(rid)
            records.append(dict(route_id=rid, status='policy_leak',
                                old_regions=old_regions))
            continue
        old_row = dict(state.row(rid))
        old_layer = int(old_row.get('target_layer') or 0)
        old_z = float(old_row.get('target_z_mm') or 0.0)
        row = RB.row_for_target(old_row, int(chosen.layer),
                                float(chosen.z_mm))
        commit = jw.replace_one(rid, chosen.route, row=row,
                                note='stage0_multi_arc_conversion')
        converted += 1
        records.append(dict(
            route_id=rid, status='converted', old_regions=old_regions,
            new_regions=len(route_flat_multi_arc(chosen.route, L2)),
            family=chosen.family, kind=chosen.kind,
            delta=int(chosen.delta if chosen.delta is not None else 0),
            commit_delta=int(commit.get('delta') or 0),
            layer=int(chosen.layer), z_mm=float(chosen.z_mm),
            old_layer=old_layer, old_z_mm=old_z,
            length_mm=round(float(chosen.route.get('length_mm') or 0.0), 6),
            total_after=int(state.total),
            seconds=round(time.time() - t0, 2)))
        if position % 20 == 0:
            log('[convert] %d/%d converted=%d total=%d residual=%d (%.0fs)'
                % (position, len(targets), converted, state.total,
                   len(residual), time.time() - started))

    # ---- hard invariants ------------------------------------------------
    after = multi_arc_route_ids(state, L2)
    non_target_changed = [rid for rid in non_target_ids
                          if _canonical(state.routes[rid]) !=
                          non_target_before[rid]]
    routes_preserved = len(state.routes) == 1024
    log('[convert] done converted=%d residual=%d errors=%d multi_arc_left=%d '
        'total=%d->%d non_target_changed=%d routes=%d'
        % (converted, len(residual), len(errors), len(after),
           start_crossings, state.total, len(non_target_changed),
           len(state.routes)))

    # ---- artifacts ------------------------------------------------------
    write_layer_planes(out_dir, state)
    hashes = ART.flush(state, ctx.baseline, out_dir,
                       note='stage-0 planar multi-arc conversion (20H, '
                            'multi_arc=%s)' % L2.MULTI_ARC_POLICY['enabled'],
                       log=log)
    validation = None
    validation21 = None
    if not args.skip_validator:
        baseline_dir = _resolve_authority(args.baseline_dir, GP)
        if not (Path(baseline_dir) / 'routes_l3d.json').is_file() or not (
                Path(baseline_dir) / 'assignment_1024.csv').is_file():
            log('[convert] FATAL the 20H identity/port authority does not '
                'exist: %s (need routes_l3d.json + assignment_1024.csv); '
                'pass --baseline-dir explicitly' % baseline_dir)
            log_file.close()
            return 2
        log('[convert] independent validator (fresh 20H process): baseline=%s'
            % baseline_dir)
        validation = run_validator_xyz(out_dir, out_dir / 'validation_xyz',
                                       baseline_dir=baseline_dir)
        log('[convert] validator exit=%s pass=%s violations=%s model_planes=%s'
            % (validation['exit_code'], validation['validation_pass'],
               validation['violation_count'],
               validation['model_plane_count']))
        if args.with_validate21:
            log('[convert] diagnostic validate21 (non-blocking) ...')
            validation21 = run_validate21(out_dir, out_dir / 'validation21')
            log('[convert] validate21 exit=%s pass=%s violations=%s'
                % (validation21.get('exit_code'),
                   validation21.get('validation_pass'),
                   validation21.get('violation_count')))

    feasible = bool(
        converted == len(targets)
        and not residual
        and not leaked
        and not errors
        and not after
        and not non_target_changed
        and routes_preserved
        and (validation is None or (
            validation['validation_pass'] is True
            and int(validation['violation_count'] or 0) == 0
            and int(validation['model_plane_count'] or 0) == 20)))

    validation_pass = None if validation is None else validation['validation_pass']
    report = dict(
        schema=SCHEMA,
        profile=M.PROFILE,
        feasible=bool(feasible),
        policy=dict(L2.MULTI_ARC_POLICY),
        planner=dict(JW.PLAN_CFG),
        start_dir=str(start_dir),
        start_sha256=start_sha,
        start_assignment_sha256=start_assignment_sha,
        start_crossings=start_crossings,
        out_dir=_rel(out_dir),
        routes_sha256=hashes.get('routes_l3d_json'),
        assignment_sha256=hashes.get('assignment_1024_csv'),
        multi_arc_routes_before=len(before),
        multi_arc_route_ids_before=list(before),
        targets=len(targets),
        converted=int(converted),
        residual=int(len(residual)),
        residual_route_ids=list(residual),
        error_route_ids=list(errors),
        multi_arc_routes_after=len(after),
        multi_arc_route_ids_after=list(after),
        policy_leaks=list(leaked),
        non_target_routes_unchanged=(not non_target_changed),
        non_target_changed_route_ids=list(non_target_changed),
        routes_preserved=bool(routes_preserved),
        crossings_after=int(state.total),
        crossing_delta_from_start=int(state.total) - start_crossings,
        total_length_mm=round(float(state.total_length()), 6),
        seconds=round(time.time() - started, 2),
        ledger=ctx.ledger.summary(),
        records=records,
        validation=validation,
        validation_pass=validation_pass,
        validation21=validation21,
        determinism=dict(randomness='none', choice_rule='min exact crossing '
                          'delta, then shortest', planner_cfg_frozen=True))
    report_path = out_dir / 'conversion_report.json'
    GP.write_json(report_path, report)
    log('[convert] report %s feasible=%s A(crossings)=%+d'
        % (report_path, feasible, report['crossing_delta_from_start']))
    log('[convert] validation pass=%s' % validation_pass)
    log_file.close()
    print(json.dumps({key: report[key] for key in (
        'feasible', 'multi_arc_routes_before', 'converted', 'residual',
        'multi_arc_routes_after', 'start_crossings', 'crossings_after',
        'crossing_delta_from_start', 'total_length_mm', 'routes_sha256',
        'validation_pass')}, ensure_ascii=False, indent=1), flush=True)
    return 0 if feasible else 4


if __name__ == '__main__':
    raise SystemExit(main())
