# -*- coding: utf-8 -*-
"""Strict planar **multi-arc ON/OFF ablation** on the 20-height 1024-route router.

This is the bootstrap-first, PowerShell-free (plain Python) port of the strict
FINAL protocol of ``experiments/G4_MULTI_ARC_ABLATION_FINAL_1024``
(read-only evidence) to the 20-height physical model installed by
:mod:`four_side_1024.fanout1024.coldstart20.bootstrap`.

The protocol in one paragraph
-----------------------------
Both arms read the **same converted common start** (the 20H G3 ``best_valid``
re-expressed in the ablated grammar by Stage-0 conversion, ``multi_arc = 0``);
the **only** algorithm variable is ``enable_multi_arc`` (``G4_ENABLE_MULTI_ARC``
1/0) injected in ``layer2d._LayerRouter._iter_candidates``; the search is
stopped by a **counted budget** (``d56_candidate_evals = 24000`` primary,
``route_3d_checks = 9000`` secondary guard, 5400 s wall safety net only), on
the same 3 pre-registered seeds; the same frozen validator
(``xyzrouter.validate_xyz`` -> ``native3d.validate_native3d`` ->
``reheight21.validate21`` helpers, all imported after the 20H bootstrap) and
the same geometry thresholds apply.  Cost separation is mandatory:
**A** = conversion delta (ON start -> OFF start), **B** = ON vs OFF search
result from the common start, **C** = historical 21H archive (read-only).
A and B are reported separately and are never added into one "value of
multi-arc" number.

Pre-registered OFF feasibility
------------------------------
If Stage-0 conversion leaves residual multi-arc regions or an illegal route,
``convert`` records the failure in ``common_start_off/conversion_report.json``
and ``OFF_FEASIBILITY.json``; ``chain``/``all`` then stop **without** running
any arm.  A diluted OFF arm (keeping residual ON geometry) would silently
re-introduce the variable and is forbidden.

Subcommands
-----------
``start``     verify the 20H G3 common start (geometry / profile / independent
              crossings / validator) and write ``START.json``.
``convert``   Stage-0 OFF conversion of the common start (effect A); blocks the
              arms if not feasible.
``arm-on``    one MULTI-ARC ON arm (``G4_ENABLE_MULTI_ARC=1``) for one seed.
``arm-off``   one MULTI-ARC OFF arm (``G4_ENABLE_MULTI_ARC=0``) for one seed.
``chain``     start -> convert -> primary 2 arms x 3 seeds -> analyse.
``all``       ``chain`` + the auxiliary equal-wall-clock (900 s) arms.
``analyse``   independent audit + A/B/C accounting + pre-registered verdict.

Every subcommand supports ``--dry-run`` (prints the resolved start dir, arm
dirs, budget contract and confirms the multi-arc switch default and its code
location; nothing is executed, nothing is written).

Usage
-----
::

    .venv\\Scripts\\python.exe -m \\
        four_side_1024.fanout1024.coldstart20.run_multiarc --help
    .venv\\Scripts\\python.exe -m \\
        four_side_1024.fanout1024.coldstart20.run_multiarc chain --dry-run

This driver never edits the archived experiment directories
(``experiments/G4_MULTI_ARC_ABLATION_1024``,
``experiments/G4_MULTI_ARC_ABLATION_FINAL_1024``,
``1130-report-materials``): they are read-only evidence.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from . import bootstrap as B          # installs the 20-height profile on import
from . import model20 as M
from . import paths20 as P20

ROOT = Path(__file__).resolve().parents[3]
MODULE = 'four_side_1024.fanout1024.coldstart20.run_multiarc'

# ===========================================================================
# frozen protocol constants -- evidence: EXPERIMENT_SPEC.md + FROZEN_CONFIG.json
# of experiments/G4_MULTI_ARC_ABLATION_FINAL_1024 and 00_audit/multiarc.md
# ===========================================================================
EXPERIMENT_NAME = 'COLD_START_20_HEIGHT_1024'

ARMS = ('on', 'off')
ARM_ENV = {'on': '1', 'off': '0'}
ENGINE_ARM = 'G4c_free'

SEEDS = (20261104, 20261116, 20261130)

#: PRIMARY = equal candidate-evaluation budget (the main result axis)
PRIMARY = dict(
    kind='primary',
    tag_prefix='c1',
    counted_d56_budget=24000,
    counted_checks_guard=9000,
    wall_safety_net_seconds=5400.0,
    counted_sweep_fraction=0.18,
    stage_sizes=(8, 16, 32, 64),
    stage_fractions=(0.22, 0.24, 0.26, 0.28),
    sweep_ratio=0.18,
    stop_rule='d56_candidate_evals >= 24000 (secondary route_3d_checks >= 9000; '
              '5400 s wall clock is a pure safety net, designed not to trigger)',
)
#: AUXILIARY = equal wall-clock control (secondary, same seeds)
AUX = dict(
    kind='auxiliary',
    tag_prefix='a1',
    counted_d56_budget=0,
    counted_checks_guard=0,
    wall_seconds=900.0,
    counted_sweep_fraction=0.18,
    stage_sizes=(8, 16, 32, 64),
    stage_fractions=(0.22, 0.24, 0.26, 0.28),
    sweep_ratio=0.18,
    stop_rule='wall_seconds >= 900 (engine stage schedule by wall fractions)',
)

#: pre-registered decision rule (EXPERIMENT_SPEC.md section 9, transferred to 20H)
EFFECT_FLOOR_ABS = 200          # crossings, the 21H FINAL absolute floor
EFFECT_FLOOR_RATIO = 0.05       # 5 % of the 20H common-start crossings
LENGTH_MAX_GROWTH = 0.05        # ON total length may be at most +5 % vs OFF
D56_OVERSHOOT_MAX = 0.10        # one operator call; 21H FINAL measured <= 0.64 %

#: hard gates (EXPERIMENT_SPEC.md section 8) -- thresholds are frozen, never relaxed
GATE_R15_MM = 15.0
GATE_R15_TRANSITION_TOL = 1e-6
GATE_3D_CLEARANCE_MM = 0.05
GATE_D56_CENTERLINE_MM = 0.08
GATE_TOL = 1e-9

VALIDATOR_POLICY = 'fully_optimizable'

#: bootstrap preamble for every independent validator child process
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
# paths
# ===========================================================================
def exp_root():
    return Path(P20.MULTIARC)


def start_json_path():
    return exp_root() / 'START.json'


def feasibility_json_path():
    return exp_root() / 'OFF_FEASIBILITY.json'


def abort_json_path():
    return exp_root() / 'ABORTED_OFF_INFEASIBLE.json'


def common_off_dir():
    return exp_root() / 'common_start_off'


def conversion_report_path():
    return common_off_dir() / 'conversion_report.json'


def runs_root():
    return exp_root() / 'runs'


def run_dir(arm, tag):
    return runs_root() / str(arm) / str(tag)


def audit_dir():
    return exp_root() / 'audit'


def tables_dir():
    return exp_root() / 'tables'


def logs_dir():
    return exp_root() / 'logs'


def validation_dir():
    return exp_root() / 'validation'


def protocol_path():
    return exp_root() / 'PROTOCOL.md'


def convert_module_path():
    return Path(__file__).resolve().parent / 'convert_multiarc20.py'


def _ensure_output_dirs():
    for path in (exp_root(), runs_root(), audit_dir(), tables_dir(),
                 logs_dir(), validation_dir(), exp_root() / 'config'):
        Path(path).mkdir(parents=True, exist_ok=True)


# ===========================================================================
# small IO helpers
# ===========================================================================
def _now():
    return time.strftime('%Y-%m-%dT%H:%M:%S')


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


def _read_csv_rows(path):
    with Path(path).open('r', encoding='utf-8-sig', newline='') as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv(path, rows, fieldnames=None):
    rows = list(rows)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text('', encoding='utf-8')
        return path
    fieldnames = fieldnames or list(rows[0].keys())
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames,
                                extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow({key: ('' if row.get(key) is None
                                   else row.get(key)) for key in fieldnames})
    return path


def _sha256(path):
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


def _stats(values):
    values = [v for v in values if v is not None]
    values = [float(v) for v in values]
    n = len(values)
    if not n:
        return dict(n=0, mean=None, std=None, min=None, max=None, median=None)
    ordered = sorted(values)
    mean = sum(ordered) / n
    std = None
    if n > 1:
        std = (sum((v - mean) ** 2 for v in ordered) / (n - 1)) ** 0.5
    mid = n // 2
    median = (ordered[mid] if n % 2 else 0.5 * (ordered[mid - 1] + ordered[mid]))
    return dict(n=n, mean=round(mean, 6), std=(None if std is None
                                               else round(std, 6)),
                min=round(ordered[0], 6), max=round(ordered[-1], 6),
                median=round(median, 6))


def _fmt(value, digits=1):
    if value is None:
        return 'n/a'
    if isinstance(value, float):
        return ('%.' + str(digits) + 'f') % value
    return str(value)


# ===========================================================================
# path resolution
# ===========================================================================
def xyz_paths():
    from ..xyzrouter import paths as XP
    return XP


def resolve_start_dir(explicit=None):
    """The 20H common ON start: the 20H G3 ``best_valid``."""
    if explicit:
        path = Path(explicit)
        return path if path.is_absolute() else (ROOT / path)
    XP = xyz_paths()
    candidates = [Path(XP.XYZ_RUN_DIR) / 'best_valid',
                  Path(P20.G123) / 'best_valid']
    for candidate in candidates:
        if (candidate / 'routes_l3d.json').is_file():
            return candidate
    return candidates[0]


def resolve_authority_dir(explicit=None):
    """Identity / port / manual-contract authority for the validator.

    Preferred: the 20H ``XYZ_RUN/baseline_authoritative`` snapshot (the G123
    chain's authority; contains the 20H ``layer_planes.json`` the validator
    needs).  Fallback: the 20H stage-03 legal layout ``INIT_RUN`` (same 1024
    connections/ports, same 20H model table).  Never the 21H authority: its
    ``layer_planes.json`` would make the validator report 21 heights.
    """
    if explicit:
        return Path(explicit)
    XP = xyz_paths()
    candidates = [Path(XP.BASELINE_AUTHORITY), Path(P20.INIT_RUN)]
    for candidate in candidates:
        if (candidate / 'routes_l3d.json').is_file() and \
                (candidate / 'assignment_1024.csv').is_file():
            return candidate
    return candidates[0]


def authority_plane_count(authority_dir):
    payload = _read_json(Path(authority_dir) / 'layer_planes.json')
    if not isinstance(payload, dict):
        return None
    if payload.get('plane_count') is not None:
        return int(payload['plane_count'])
    planes = payload.get('planes')
    if isinstance(planes, (list, dict)):
        return len(planes)
    return None


# ===========================================================================
# profile / pipeline helpers  (import the pipeline only after bootstrap)
# ===========================================================================
def _load_state(run_dir_path):
    """Load one 1024-route state into the frozen ``RouteWorld`` (20H profile)."""
    from ..xyzrouter import route_builder as RB
    from ..xyzrouter import world_adapter as WA
    payload = _read_json(Path(run_dir_path) / 'routes_l3d.json')
    if not isinstance(payload, dict) or not payload.get('routes'):
        raise RuntimeError('no routes in %s' % run_dir_path)
    rows = _read_csv_rows(Path(run_dir_path) / 'assignment_1024.csv')
    normalized = RB.normalized_rows(rows, stack=M.layer_stack())
    state = WA.RouteWorld(payload['routes'], normalized,
                          log=lambda *_a, **_k: None)
    return state, payload, rows


def _frozen_crossings(state):
    """Per-route crossings from the frozen strict-D56 audit (independent)."""
    from ..nonc4 import crossings as X
    per_route = {}
    events = []
    pairs = set()
    for z_key in sorted(state.plane_prims):
        prims = {rid: list(chain)
                 for rid, chain in state.plane_prims[z_key].items()}
        if not prims:
            continue
        result = X.audit_flat_group(prims)
        for event in result.get('crossings') or ():
            route_a = int(event['route_a'])
            route_b = int(event['route_b'])
            per_route[route_a] = per_route.get(route_a, 0) + 1
            per_route[route_b] = per_route.get(route_b, 0) + 1
            pairs.add((min(route_a, route_b), max(route_a, route_b)))
            events.append(dict(route_a=route_a, route_b=route_b,
                               z_mm=float(z_key)))
    return per_route, events, pairs


def _multi_arc_census(state):
    """Planar multi-arc census with the frozen policy definition."""
    from .. import layer2d as L2
    from ..xyzrouter import world_adapter as WA
    per_route = {}
    per_height = {}
    total_regions = 0
    routes_with = 0
    total_arcs = 0
    kinds = {}
    for rid in sorted(state.routes):
        groups = WA.route_flat_groups(state.routes[rid])
        regions = []
        for z_key in sorted(groups):
            for chain in groups[z_key]:
                for region in L2.local_multi_arc_regions(chain):
                    region = dict(region)
                    region['z_mm'] = float(z_key)
                    regions.append(region)
                    key = '%.6f' % float(z_key)
                    per_height[key] = per_height.get(key, 0) + 1
                    kinds[str(region.get('kind'))] = \
                        kinds.get(str(region.get('kind')), 0) + 1
        if regions:
            routes_with += 1
            total_regions += len(regions)
            total_arcs += sum(int(r['n_arcs']) for r in regions)
            per_route[str(int(rid))] = regions
    return dict(routes_with_multi_arc=int(routes_with),
                total_regions=int(total_regions),
                arcs_in_regions=int(total_arcs),
                kinds=dict(sorted(kinds.items())),
                per_height=dict(sorted(per_height.items())),
                per_route_with_multi_arc=per_route)


def _route_primitives_census(state):
    """Flat-arc / line / transition / flat-height counts of a state."""
    flat_arcs = 0
    flat_lines = 0
    transitions = 0
    flat_heights = set()
    for rid in state.routes:
        for part in state.routes[rid].get('parts') or ():
            if part.get('kind') == 'transition':
                transitions += 1
                continue
            if part.get('kind') != 'flat':
                continue
            flat_heights.add(round(float(part.get('z_mm') or 0.0), 9))
            for prim in part.get('primitives') or ():
                if prim.get('kind') == 'arc':
                    flat_arcs += 1
                elif prim.get('kind') == 'line':
                    flat_lines += 1
    return dict(flat_arcs=int(flat_arcs), flat_lines=int(flat_lines),
                transition_parts=int(transitions),
                flat_heights=sorted(flat_heights))


def audit_state(run_dir_path, label=''):
    """Full independent census of one route state (port of ``audit_state.py``)."""
    run_dir_path = Path(run_dir_path)
    state, payload, rows = _load_state(run_dir_path)
    per_route, events, pairs = _frozen_crossings(state)
    census = _multi_arc_census(state)
    prims = _route_primitives_census(state)
    route_ids = sorted(int(rid) for rid in state.routes)
    counts = sorted(int(per_route.get(rid, 0)) for rid in route_ids)
    n = len(counts)
    p95 = counts[min(n - 1, int(round(0.95 * (n - 1))))] if n else 0
    plane_counts = {}
    for z_key, value in sorted(state.plane_counts.items()):
        plane_counts['%.6f' % float(z_key)] = dict(
            events=int(value[0]), pairs=int(value[1]),
            routes=len(state.plane_prims.get(z_key, {})))
    routes_path = run_dir_path / 'routes_l3d.json'
    assignment_path = run_dir_path / 'assignment_1024.csv'
    return dict(
        schema='coldstart20_multiarc_audit_v1',
        label=str(label),
        run_dir=_rel(run_dir_path),
        profile=M.PROFILE,
        plane_count=len(M.PLANE_IDS),
        routes_sha256=_sha256(routes_path),
        assignment_sha256=(_sha256(assignment_path)
                           if assignment_path.is_file() else None),
        routes_schema=payload.get('schema'),
        routes_algorithm=payload.get('algorithm'),
        routes_loaded=len(state.routes),
        rows=len(rows),
        crossings=int(len(events)),
        crossing_pairs=int(len(pairs)),
        state_total=int(state.total),
        state_total_matches_audit=bool(int(state.total) == len(events)),
        routes_with_crossings=int(sum(1 for v in per_route.values() if v)),
        max_route_crossings=int(max(per_route.values()) if per_route else 0),
        p95_route_crossings=int(p95),
        total_length_mm=round(float(state.total_length()), 6),
        mid_transitions=int(state.mid_transition_count()),
        flat_arcs=prims['flat_arcs'],
        flat_lines=prims['flat_lines'],
        transition_parts=prims['transition_parts'],
        flat_heights_mm=prims['flat_heights'],
        multi_arc=census,
        plane_counts=plane_counts,
        per_route_crossings={str(rid): int(value)
                             for rid, value in sorted(per_route.items())},
    )


# ===========================================================================
# independent validator (fresh process with the 20H profile installed first)
# ===========================================================================
def run_validator_xyz(run_dir_path, out_dir, baseline_dir=None,
                      manual_policy=VALIDATOR_POLICY, timeout=3600):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, '-c', BOOTSTRAP_PREAMBLE,
           '--run-dir', str(run_dir_path), '--out-dir', str(out_dir)]
    if baseline_dir:
        cmd.extend(['--baseline-dir', str(baseline_dir)])
    cmd.extend(['--manual-policy', str(manual_policy)])
    started = time.time()
    result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True,
                            text=True, encoding='utf-8', errors='replace',
                            timeout=timeout)
    seconds = round(time.time() - started, 2)
    log_path = out_dir / 'validator.log'
    log_path.write_text(
        '#' * 78 + '\n# command: %s\n# exit=%s seconds=%.2f\n'
        % (' '.join(cmd), result.returncode, seconds) + '#' * 78 + '\n'
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
        min_transition_sampled_radius_mm=counts.get(
            'min_transition_sampled_radius_mm'),
        run_dir=str(run_dir_path),
        out_dir=str(out_dir),
        validation_json=str(out_dir / 'validation.json'),
        validator_log=str(log_path),
        manual_policy=str(manual_policy),
        baseline_dir=(str(baseline_dir) if baseline_dir else None),
    )


# ===========================================================================
# multi-arc switch verification (the only changed algorithm factor)
# ===========================================================================
def _source_lines(path):
    try:
        return Path(path).read_text(encoding='utf-8').splitlines()
    except OSError:
        return []


def _find_lines(lines, needle):
    return [index + 1 for index, line in enumerate(lines) if needle in line]


def _function_info(func):
    import inspect
    try:
        source_lines, start = inspect.getsourcelines(func)
        return int(start), ''.join(source_lines)
    except (OSError, TypeError):
        return None, ''


def switch_report():
    """Verify the multi-arc switch default and its exact code location.

    Returns a report dict; raises ``RuntimeError`` when the frozen switch
    contract is not what the protocol assumes (a silent code change must never
    be reported as "same experiment").
    """
    inherited = os.environ.pop('G4_ENABLE_MULTI_ARC', None)
    from .. import layer2d as L2
    from ..xyzrouter import local_reroute as LR

    policy = dict(L2.MULTI_ARC_POLICY)
    l2_path = Path(L2.__file__)
    l2_lines = _source_lines(l2_path)
    lr_path = Path(LR.__file__)
    lr_lines = _source_lines(lr_path)

    init_start, init_src = _function_info(L2._LayerRouter.__init__)
    iter_start, iter_src = _function_info(L2._LayerRouter._iter_candidates)
    g4_root = ROOT / 'four_side_1024' / 'fanout1024' / 'xyzrouter' / 'g4'
    engine_lines = _source_lines(g4_root / 'run_g4_engine.py')
    g4c_lines = _source_lines(g4_root / 'run_g4c.py')
    alns_lines = _source_lines(g4_root / 'alns.py')

    report = dict(
        env_at_import=inherited,
        policy=policy,
        policy_definition_line=_find_lines(l2_lines, 'MULTI_ARC_POLICY = dict('),
        override_helper_line=_find_lines(l2_lines, 'def multi_arc_enabled('),
        local_region_definition_line=_find_lines(
            l2_lines, 'def local_multi_arc_regions('),
        spec_prefilter_line=_find_lines(l2_lines,
                                        'def spec_uses_multi_arc('),
        constructor_read_line=_find_lines(l2_lines, 'self.enable_multi_arc ='),
        iter_candidates_start=iter_start,
        iter_candidates_prefilter=('multi_arc_enabled' in iter_src
                                   or "spec_uses_multi_arc" in iter_src
                                   or "('S'" in iter_src),
        iter_candidates_hard_gate=('local_multi_arc_regions' in iter_src
                                   and 'multi_arc_forbidden' in iter_src),
        init_reads_policy=('self.enable_multi_arc' in init_src),
        local_reroute_file=_rel(lr_path),
        local_reroute_propagation_line=_find_lines(
            lr_lines, "enable_multi_arc'] = L2.multi_arc_enabled(cfg)"),
        budget_flag_engine=_find_lines(engine_lines, '--counted-d56-budget'),
        budget_flag_g4c=_find_lines(g4c_lines, '--counted-d56-budget'),
        counted_sweep_fraction_line=_find_lines(
            alns_lines, 'counted_sweep_fraction=0.18'),
        counted_mode_line=_find_lines(alns_lines, 'counted_d56'),
        layer2d_file=_rel(l2_path),
    )
    # -- contract checks ---------------------------------------------------
    problems = []
    notes = []
    if report['env_at_import'] is not None:
        notes.append('G4_ENABLE_MULTI_ARC was set in the parent environment '
                     '(%r); it was removed before importing layer2d so the '
                     'default policy can be observed' % inherited)
    if policy.get('enabled') is not True:
        problems.append('default policy is not ON: %r' % (policy,))
    if str(policy.get('source')) != 'default:enabled':
        problems.append('policy source is not the unset default: %r'
                        % (policy.get('source'),))
    if not report['policy_definition_line']:
        problems.append('MULTI_ARC_POLICY definition not found in layer2d.py')
    if not report['override_helper_line']:
        problems.append('multi_arc_enabled() not found in layer2d.py')
    if not report['constructor_read_line']:
        problems.append('_LayerRouter.__init__ does not read the policy')
    if not report['iter_candidates_start']:
        problems.append('_LayerRouter._iter_candidates not found')
    if not report['iter_candidates_prefilter']:
        problems.append('_iter_candidates has no multi-arc spec prefilter')
    if not report['iter_candidates_hard_gate']:
        problems.append('_iter_candidates has no geometric hard gate '
                        '(local_multi_arc_regions / multi_arc_forbidden)')
    if not report['local_reroute_propagation_line']:
        problems.append('local_reroute.py does not propagate enable_multi_arc')
    if not report['budget_flag_engine'] or not report['budget_flag_g4c']:
        problems.append('the counted-budget flags are missing from the engine')
    if L2.multi_arc_enabled({'enable_multi_arc': False}) is not False:
        problems.append("explicit cfg override {'enable_multi_arc': False} "
                        'is ignored')
    if L2.multi_arc_enabled({}) is not True:
        problems.append('multi_arc_enabled({}) does not follow the ON default')
    report['notes'] = notes
    report['problems'] = problems
    report['ok'] = not problems
    if problems:
        raise RuntimeError('multi-arc switch verification failed: '
                           + '; '.join(problems))
    return report


def _switch_lines(report):
    return [
        'multi-arc switch: G4_ENABLE_MULTI_ARC (1=ON, 0=OFF) -- the ONLY '
        'changed algorithm factor',
        '  default policy (env unset): enabled=%s source=%s  [%s]'
        % (report['policy'].get('enabled'), report['policy'].get('source'),
           'OK'),
        '  policy definition : %s:%s  MULTI_ARC_POLICY = dict(...)'
        % (report['layer2d_file'], report['policy_definition_line']),
        '  override helper   : %s:%s  def multi_arc_enabled(cfg=None)'
        % (report['layer2d_file'], report['override_helper_line']),
        '  constructor read  : %s:%s  self.enable_multi_arc = ...'
        % (report['layer2d_file'], report['constructor_read_line']),
        '  injection point   : %s:%s  _LayerRouter._iter_candidates '
        '(spec prefilter + geometric hard gate OK)'
        % (report['layer2d_file'], report['iter_candidates_start']),
        '  propagation       : %s:%s  router_cfg[\'enable_multi_arc\'] = '
        'L2.multi_arc_enabled(cfg)'
        % (report['local_reroute_file'],
           report['local_reroute_propagation_line']),
        '  counted-budget plumbing: run_g4_engine.py:%s, run_g4c.py:%s, '
        'alns.py:%s'
        % (report['budget_flag_engine'], report['budget_flag_g4c'],
           report['counted_sweep_fraction_line']),
    ]


# ===========================================================================
# shared plan / dry-run reporting
# ===========================================================================
def _tag(kind, arm, seed):
    return '%s_%s_%s' % (kind['tag_prefix'], arm, seed)


def _start_echo(start_dir):
    """Cheap (no RouteWorld) description of the resolved start dir."""
    start_dir = Path(start_dir)
    routes_path = start_dir / 'routes_l3d.json'
    assignment_path = start_dir / 'assignment_1024.csv'
    echo = dict(dir=_rel(start_dir), exists=routes_path.is_file(),
                routes_l3d_json=str(routes_path),
                assignment_1024_csv=str(assignment_path),
                routes_sha256=None, assignment_sha256=None,
                routes_schema=None, route_count=None, routed=None,
                failed=None, reported_crossings=None,
                crossing_stats=None)
    if not routes_path.is_file():
        return echo
    echo['routes_sha256'] = _sha256(routes_path)
    if assignment_path.is_file():
        echo['assignment_sha256'] = _sha256(assignment_path)
    payload = _read_json(routes_path, default={}) or {}
    echo['routes_schema'] = payload.get('schema')
    echo['route_count'] = payload.get('route_count')
    echo['routed'] = payload.get('routed')
    echo['failed'] = payload.get('failed')
    stats_path = start_dir / 'crossing_stats.json'
    if stats_path.is_file():
        stats = _read_json(stats_path, default={}) or {}
        totals = stats.get('totals') or {}
        echo['reported_crossings'] = totals.get('crossings')
        echo['crossing_stats'] = _rel(stats_path)
    if echo['reported_crossings'] is None:
        summary = _read_json(start_dir / 'summary.json', default={}) or {}
        echo['reported_crossings'] = summary.get('crossings')
    return echo


def plan_payload(include_aux=False, start_dir=None, authority_dir=None,
                 seeds=None):
    start_dir = resolve_start_dir(start_dir)
    authority = resolve_authority_dir(authority_dir)
    off_dir = common_off_dir()
    seeds = list(seeds or SEEDS)
    model_planes = len(M.PLANE_IDS)
    payload = dict(
        profile=dict(profile=M.PROFILE,
                     plane_count=model_planes,
                     body_plane_count=len(M.BODY_PLANES),
                     plane_ids=[int(pid) for pid in M.PLANE_IDS],
                     interface_z={key: float(value)
                                  for key, value in M.INTERFACE_Z.items()},
                     min_pitch_mm=float(M.MIN_LAYER_PITCH_MM)),
        project_root=_rel(ROOT),
        experiment_root=_rel(exp_root()),
        start=_start_echo(start_dir),
        common_off=dict(dir=_rel(off_dir),
                        exists=(off_dir / 'routes_l3d.json').is_file(),
                        conversion_report=str(conversion_report_path()),
                        conversion_report_exists=conversion_report_path().is_file()),
        authority=dict(dir=_rel(authority),
                       exists=(Path(authority) / 'routes_l3d.json').is_file(),
                       layer_planes_plane_count=authority_plane_count(
                           authority)),
        seeds=list(seeds),
        engine_arm=ENGINE_ARM,
        primary=dict(PRIMARY),
        auxiliary=dict(AUX),
        include_aux=bool(include_aux),
    )
    payload['primary_arms'] = {
        arm: [_rel(run_dir(arm, _tag(PRIMARY, arm, seed))) for seed in seeds]
        for arm in ARMS}
    payload['aux_arms'] = {
        arm: [_rel(run_dir(arm, _tag(AUX, arm, seed))) for seed in seeds]
        for arm in ARMS}
    payload['arms'] = {
        arm: [(PRIMARY['tag_prefix'], seed,
               _rel(run_dir(arm, _tag(PRIMARY, arm, seed))))
              for seed in seeds] for arm in ARMS}
    return payload


def print_plan(plan, title, actions=()):
    profile = plan['profile']
    start = plan['start']
    print('=' * 78)
    print('[20H multi-arc ON/OFF ablation] %s' % title)
    print('=' * 78)
    print('profile           : %s  planes=%d (18 body + 2 interface)  '
          'z1=+%.3f z2=+%.3f  min_pitch=%.3f mm'
          % (profile['profile'], profile['plane_count'],
             profile['interface_z']['z1'], profile['interface_z']['z2'],
             profile['min_pitch_mm']))
    print('project root      : %s' % str(ROOT))
    print('experiment root   : %s' % plan['experiment_root'])
    print('generation root   : %s (G3 best_valid is the common ON start)'
          % _rel(P20.G123))
    print('start dir         : %s  exists=%s'
          % (start['dir'], start['exists']))
    if start['exists']:
        print('  start routes     : sha256=%s  route_count=%s routed=%s '
              'failed=%s schema=%s'
              % (start['routes_sha256'], start['route_count'],
                 start['routed'], start['failed'], start['routes_schema']))
        print('  start crossings  : reported=%s  (%s)'
              % (start['reported_crossings'], start['crossing_stats']))
    else:
        print('  BLOCKED: the 20H G3 output does not exist yet -- run the 20H '
              'cold-start + G1/G2/G3 chain first (stage 07).')
    off = plan['common_off']
    print('common OFF start  : %s  exists=%s  conversion_report=%s'
          % (off['dir'], off['exists'], off['conversion_report_exists']))
    print('authority dir     : %s  exists=%s  layer_planes_plane_count=%s'
          % (plan['authority']['dir'], plan['authority']['exists'],
             plan['authority']['layer_planes_plane_count']))
    print('engine arm        : %s' % plan['engine_arm'])
    primary = plan['primary']
    print('budget PRIMARY    : counted_d56_budget=%d  counted_checks_guard=%d  '
          'wall_safety_net=%.0fs  counted_sweep_fraction=%.2f'
          % (primary['counted_d56_budget'], primary['counted_checks_guard'],
             primary['wall_safety_net_seconds'],
             primary['counted_sweep_fraction']))
    print('                    stage_sizes=%s stage_fractions=%s'
          % (','.join(str(v) for v in primary['stage_sizes']),
             ','.join(str(v) for v in primary['stage_fractions'])))
    print('                    stop_rule: %s' % primary['stop_rule'])
    print('budget AUXILIARY  : wall=%.0fs  no counted caps  (secondary control)'
          % AUX['wall_seconds'])
    print('seeds             : %s (pre-registered)'
          % ', '.join(str(seed) for seed in plan['seeds']))
    print('arms              : on  = G4_ENABLE_MULTI_ARC=1, start=common OFF '
          'start')
    print('                    off = G4_ENABLE_MULTI_ARC=0, start=common OFF '
          'start  (the ONLY changed variable)')
    try:
        switch = switch_report()
    except RuntimeError as error:
        print('multi-arc switch  : VERIFICATION FAILED -- %s' % error)
        raise
    for line in _switch_lines(switch):
        print(line)
    print('arm dirs (primary):')
    for arm in ARMS:
        for (prefix, seed, path) in plan['arms'][arm]:
            print('  %-4s %-8s %s' % (arm, prefix, path))
    if plan['include_aux']:
        print('arm dirs (auxiliary):')
        for arm in ARMS:
            for path in plan['aux_arms'][arm]:
                print('  %-4s a1       %s' % (arm, path))
    if actions:
        print('-' * 78)
        print('planned actions (--dry-run: nothing is executed / written):')
        for index, action in enumerate(actions, 1):
            print('  %2d. %s' % (index, action))
    print('=' * 78)
    return switch


def _dry_run_done():
    print('[dry-run] no file was written and no pipeline stage was executed.',
          flush=True)
    return 0


# ===========================================================================
# START verification
# ===========================================================================
START_SCHEMA = 'coldstart20_multiarc_start_v1'


def _start_geometry_checks(start_dir, authority_dir):
    """Independent 20H checks of the common start (raises on a hard failure)."""
    state, payload, rows = _load_state(start_dir)
    problems = []

    if len(M.PLANE_IDS) != 20 or 19 in M.PLANE_IDS:
        problems.append('20-height profile not installed properly')
    model_z = {round(float(M.plane_z(pid)), 9) for pid in M.PLANE_IDS}
    prims = _route_primitives_census(state)
    unknown_heights = [z for z in prims['flat_heights'] if z not in model_z]
    if unknown_heights:
        problems.append('flat heights not in the 20H model: %r'
                        % unknown_heights[:10])

    interface_ids = {int(pid) for pid in M.INTERFACE_PLANE_IDS}
    plane_ids = {int(pid) for pid in M.PLANE_IDS}
    bad_layers = []
    bad_z = []
    bad_interface = []
    manual = 0
    direct = 0
    sides = {}
    for row in rows:
        try:
            layer = int(float(row.get('target_layer')))
        except (TypeError, ValueError):
            bad_layers.append(row.get('route_id'))
            continue
        if layer not in plane_ids:
            bad_layers.append(layer)
        target_z = row.get('target_z_mm')
        try:
            target_z = float(target_z)
        except (TypeError, ValueError):
            target_z = None
        if target_z is not None:
            expected = round(float(M.plane_z(layer)), 9)
            if abs(round(target_z, 9) - expected) > 1e-9:
                bad_z.append((row.get('route_id'), target_z, expected))
        interface_z = row.get('interface_z_mm')
        try:
            interface_z = float(interface_z)
        except (TypeError, ValueError):
            interface_z = None
        if interface_z is not None:
            allowed = {round(float(M.Z1_INTERFACE_MM), 9),
                       round(float(M.Z2_INTERFACE_MM), 9)}
            if round(interface_z, 9) not in allowed:
                bad_interface.append((row.get('route_id'), interface_z))
        if str(row.get('manual_group') or '').strip():
            manual += 1
        if str(row.get('needs_transition') or '').strip().lower() in (
                'false', '0', 'no', 'none', ''):
            direct += 1
        sides[str(row.get('plane') or '')] = \
            sides.get(str(row.get('plane') or ''), 0) + 1
    if bad_layers:
        problems.append('assignment target layers not in the 20H model: %r'
                        % bad_layers[:10])
    if bad_z:
        problems.append('assignment target_z does not match the 20H model: %r'
                        % bad_z[:5])
    if bad_interface:
        problems.append('assignment interface_z not in {0.025, 0.525}: %r'
                        % bad_interface[:5])
    if manual != int(M.CONTRACT_MANUAL_TOTAL):
        problems.append('manual route count %d != contract %d'
                        % (manual, int(M.CONTRACT_MANUAL_TOTAL)))

    per_route, events, pairs = _frozen_crossings(state)
    crossings = int(len(events))
    if crossings != int(state.total):
        problems.append('independent crossing count %d != state.total %d'
                        % (crossings, int(state.total)))
    stats = _read_json(Path(start_dir) / 'crossing_stats.json', default={}) or {}
    reported = ((stats.get('totals') or {}).get('crossings')
                or stats.get('crossings'))
    if reported is None:
        summary = _read_json(Path(start_dir) / 'summary.json', default={}) or {}
        reported = summary.get('crossings')
    if reported is not None and int(reported) != crossings:
        problems.append('reported start crossings %d != independent %d'
                        % (int(reported), crossings))

    route_ids = sorted(int(rid) for rid in state.routes)
    if len(route_ids) != 1024:
        problems.append('routed %d != 1024' % len(route_ids))
    if int(payload.get('route_count') or 0) != 1024:
        problems.append('route_count %r != 1024' % payload.get('route_count'))
    if int(payload.get('failed') or 0) != 0:
        problems.append('failed routes declared: %r' % payload.get('failed'))

    census = _multi_arc_census(state)
    result = dict(
        checks=dict(
            profile_20_height=(len(M.PLANE_IDS) == 20 and 19 not in M.PLANE_IDS),
            flat_heights_in_model=(not unknown_heights),
            assignment_layers_in_model=(not bad_layers),
            assignment_target_z_matches_model=(not bad_z),
            assignment_interface_z_matches_model=(not bad_interface),
            manual_route_count=int(manual),
            manual_route_count_matches_contract=(
                manual == int(M.CONTRACT_MANUAL_TOTAL)),
            direct_routes=int(direct),
            routed_1024=(len(route_ids) == 1024),
            failed_zero=(int(payload.get('failed') or 0) == 0),
            crossings_recomputed=crossings,
            crossings_reported=(None if reported is None else int(reported)),
            crossings_match=(reported is not None
                             and int(reported) == crossings),
        ),
        problems=problems,
        crossings=crossings,
        crossing_pairs=int(len(pairs)),
        routes_with_crossings=int(sum(1 for v in per_route.values() if v)),
        max_route_crossings=int(max(per_route.values()) if per_route else 0),
        total_length_mm=round(float(state.total_length()), 6),
        multi_arc=dict(routes_with_multi_arc=census['routes_with_multi_arc'],
                       total_regions=census['total_regions'],
                       arcs_in_regions=census['arcs_in_regions'],
                       kinds=census['kinds'],
                       per_height=census['per_height']),
        manual_route_count=int(manual),
        direct_routes=int(direct),
        plane_side_counts=dict(sorted(sides.items())),
        plane_count=len(M.PLANE_IDS),
        flat_heights_mm=prims['flat_heights'],
        flat_arcs=prims['flat_arcs'],
        flat_lines=prims['flat_lines'],
        transition_parts=prims['transition_parts'],
        assignment_rows=len(rows),
        routes_sha256=_sha256(Path(start_dir) / 'routes_l3d.json'),
        assignment_sha256=_sha256(Path(start_dir) / 'assignment_1024.csv'),
    )
    return result


def _source_snapshot():
    files = [
        Path(__file__),
        convert_module_path(),
        ROOT / 'four_side_1024' / 'fanout1024' / 'layer2d.py',
        ROOT / 'four_side_1024' / 'fanout1024' / 'xyzrouter' / 'local_reroute.py',
        ROOT / 'four_side_1024' / 'fanout1024' / 'xyzrouter' / 'g4' / 'alns.py',
        ROOT / 'four_side_1024' / 'fanout1024' / 'xyzrouter' / 'g4' / 'run_g4_engine.py',
        ROOT / 'four_side_1024' / 'fanout1024' / 'xyzrouter' / 'g4' / 'run_g4c.py',
        ROOT / 'four_side_1024' / 'fanout1024' / 'coldstart20' / 'bootstrap.py',
        ROOT / 'four_side_1024' / 'fanout1024' / 'coldstart20' / 'model20.py',
    ]
    snapshot = {}
    for path in files:
        if Path(path).is_file():
            snapshot[_rel(path)] = _sha256(path)
    return snapshot


def _protocol_echo():
    path = protocol_path()
    if not path.is_file():
        return dict(path=_rel(path), present=False, sha256=None)
    return dict(path=_rel(path), present=True, sha256=_sha256(path))


def cmd_start(args):
    B.install()
    B.assert_20_height_profile('run_multiarc.start')
    start_dir = resolve_start_dir(args.start_dir)
    authority = resolve_authority_dir(args.baseline_dir)

    if args.dry_run:
        plan = plan_payload(include_aux=False, start_dir=args.start_dir,
                            authority_dir=args.baseline_dir,
                            seeds=_seed_list(args))
        actions = [
            'verify the 20H profile (20 planes, plane 19 absent, '
            'interfaces +0.025/+0.525)',
            'load %s with the frozen RouteWorld and recompute the exact '
            'strict-D56 crossing total independently' % _rel(start_dir),
            'assert: 1024 routes / 0 failed / 20H height table / assignment '
            'target layers + z / manual count %d'
            % int(M.CONTRACT_MANUAL_TOTAL),
            'census the planar multi-arc regions of the ON start '
            '(count recomputed; the 21H 197 is not assumed)',
            'run the frozen independent validator in a fresh process with the '
            '20H bootstrap -> %s'
            % _rel(validation_dir() / 'start'),
            'write %s (profile, SHAs, crossings, multi-arc census, budget '
            'contract, seeds, source snapshot)' % _rel(start_json_path()),
        ]
        print_plan(plan, 'start --dry-run', actions)
        print('validator         : fresh process '
              '"python -c <coldstart20.bootstrap> validate_xyz" '
              '--manual-policy %s' % VALIDATOR_POLICY)
        print('authority dir     : %s  (layer_planes plane_count=%s)'
              % (plan['authority']['dir'],
                 plan['authority']['layer_planes_plane_count']))
        return _dry_run_done()

    _ensure_output_dirs()
    print('[start] profile: %s | %s'
          % (M.PROFILE, ' | '.join(B.summary_lines())), flush=True)
    if not (start_dir / 'routes_l3d.json').is_file():
        print('[start] FATAL the 20H G3 common start does not exist: %s'
              % start_dir, file=sys.stderr)
        print('[start] this is the blocked prerequisite: the 20H cold-start + '
              'G1/G2/G3 chain (stage 07) must produce '
              'run_xyz_joint_1024_20h/best_valid first.', file=sys.stderr)
        return 2
    print('[start] start dir: %s' % start_dir, flush=True)
    authority_available = ((Path(authority) / 'routes_l3d.json').is_file()
                           and (Path(authority) /
                                'assignment_1024.csv').is_file())
    if not authority_available:
        print('[start] WARNING the 20H identity/port authority is missing: %s '
              '-- the independent validator cannot run without it'
              % authority, file=sys.stderr)

    echo = _start_echo(start_dir)
    if start_json_path().is_file() and not args.force:
        existing = _read_json(start_json_path(), default={}) or {}
        if existing.get('routes_sha256') == echo['routes_sha256']:
            print('[start] already verified (START.json matches the current '
                  'start sha); use --force to re-verify.', flush=True)
            return 0 if existing.get('ok', True) else 1

    info = _start_geometry_checks(start_dir, authority)
    checks_failed = bool(info['problems'])
    if checks_failed:
        print('[start] START CHECKS FAILED (recorded honestly in START.json):',
              file=sys.stderr)
        for problem in info['problems']:
            print('  - %s' % problem, file=sys.stderr)

    validator = None
    if not args.skip_validator and not checks_failed and authority_available:
        print('[start] independent validator (fresh 20H process) ...',
              flush=True)
        validator = run_validator_xyz(start_dir, validation_dir() / 'start',
                                      baseline_dir=authority)
        print('[start] validator exit=%s pass=%s violations=%s model_planes=%s'
              % (validator['exit_code'], validator['validation_pass'],
                 validator['violation_count'],
                 validator['model_plane_count']), flush=True)
        if not (validator['validation_pass'] is True
                and int(validator['violation_count'] or 0) == 0
                and int(validator['model_plane_count'] or 0) == len(M.PLANE_IDS)):
            print('[start] the common start did NOT pass the frozen 20H '
                  'validator; START.json is written with ok=false so that '
                  'convert/chain refuse to run.', file=sys.stderr)

    payload = dict(
        schema=START_SCHEMA,
        generated_at=_now(),
        experiment=EXPERIMENT_NAME,
        profile=M.PROFILE,
        model='four_side_1024.fanout1024.coldstart20.model20',
        plane_count=len(M.PLANE_IDS),
        plane_ids=[int(pid) for pid in M.PLANE_IDS],
        interface_z={key: float(value) for key, value in M.INTERFACE_Z.items()},
        start_dir=_rel(start_dir),
        start_dir_abs=str(start_dir),
        routes_sha256=info['routes_sha256'],
        assignment_sha256=info['assignment_sha256'],
        routes_schema=echo['routes_schema'],
        route_count=int(echo['route_count'] or 0),
        routed=int(echo['routed'] or 0),
        failed=int(echo['failed'] or 0),
        crossings_independent=int(info['crossings']),
        crossings_reported=info['checks']['crossings_reported'],
        crossing_pairs=int(info['crossing_pairs']),
        routes_with_crossings=int(info['routes_with_crossings']),
        max_route_crossings=int(info['max_route_crossings']),
        total_length_mm=info['total_length_mm'],
        multi_arc=info['multi_arc'],
        manual_route_count=info['manual_route_count'],
        direct_routes=info['direct_routes'],
        plane_side_counts=info['plane_side_counts'],
        flat_arcs=info['flat_arcs'],
        flat_lines=info['flat_lines'],
        transition_parts=info['transition_parts'],
        checks=info['checks'],
        problems=list(info['problems']),
        authority=dict(dir=_rel(authority),
                       available=bool(authority_available),
                       layer_planes_plane_count=authority_plane_count(
                           authority)),
        validator=validator,
        budget=dict(primary=dict(PRIMARY), auxiliary=dict(AUX)),
        seeds=_seed_list(args),
        decision_rule=dict(
            rule='A: 3/3 seeds ON<OFF and paired mean gap >= '
                 'max(200, 5 % of common-start crossings) and ON total length '
                 'increase <= 5 % and all hard gates pass; C: paired mean gap '
                 '<= 0 or direction inconsistent; B: otherwise',
            effect_floor_abs=EFFECT_FLOOR_ABS,
            effect_floor_ratio=EFFECT_FLOOR_RATIO,
            length_max_growth=LENGTH_MAX_GROWTH,
            effect_floor_crossings=max(
                int(EFFECT_FLOOR_ABS),
                int(round(EFFECT_FLOOR_RATIO * int(info['crossings']))))),
        protocol=_protocol_echo(),
        source_snapshot=_source_snapshot(),
        ok=bool(
            not info['problems']
            and (args.skip_validator or authority_available)
            and (validator is None or (
                validator['validation_pass'] is True
                and int(validator['violation_count'] or 0) == 0
                and int(validator['model_plane_count'] or 0) == len(M.PLANE_IDS))
            )),
    )
    _write_json(start_json_path(), payload)
    print('[start] wrote %s  ok=%s  crossings=%d  multi_arc_regions=%d'
          % (start_json_path(), payload['ok'], payload['crossings_independent'],
             payload['multi_arc']['total_regions']), flush=True)
    return 0 if payload['ok'] else 1


# ===========================================================================
# CONVERT (Stage-0 OFF conversion, effect A)
# ===========================================================================
FEASIBILITY_SCHEMA = 'coldstart20_multiarc_off_feasibility_v1'


def _check_verified_start(allow_unverified=False):
    """Load START.json and make sure it still describes the current start."""
    if not start_json_path().is_file():
        return None, ['START.json is missing: run "run_multiarc.py start" '
                      'first']
    start = _read_json(start_json_path(), default={}) or {}
    problems = []
    if not start.get('ok', False) and not allow_unverified:
        problems.append('START.json is not ok: the common start failed a '
                        'check or the 20H validator')
    current = resolve_start_dir(start.get('start_dir'))
    routes_path = Path(current) / 'routes_l3d.json'
    if not routes_path.is_file():
        problems.append('the recorded start dir has no routes_l3d.json: %s'
                        % current)
    elif _sha256(routes_path) != start.get('routes_sha256'):
        problems.append('the start routes_l3d.json changed since START.json '
                        '(sha mismatch): re-run start --force')
    return start, problems


def cmd_convert(args):
    # IMPORTANT: the OFF policy must be in force before *any* pipeline import.
    # ``xyzrouter/__init__.py`` imports ``local_reroute`` which imports
    # ``layer2d`` (which reads G4_ENABLE_MULTI_ARC once at import time), so even
    # importing ``xyzrouter.paths`` would freeze the policy.  This is the first
    # statement of the command (except for --dry-run, where the default policy
    # must remain observable for the switch verification).
    if not args.dry_run:
        os.environ['G4_ENABLE_MULTI_ARC'] = '0'
    B.install()
    B.assert_20_height_profile('run_multiarc.convert')
    start, start_problems = _check_verified_start(args.allow_unverified_start)
    authority = resolve_authority_dir(args.baseline_dir)
    if start_problems and not args.dry_run:
        for problem in start_problems:
            print('[convert] %s' % problem, file=sys.stderr)
        return 2

    if args.dry_run:
        plan = plan_payload(include_aux=False, start_dir=args.start_dir,
                            authority_dir=args.baseline_dir,
                            seeds=_seed_list(args))
        actions = [
            'set G4_ENABLE_MULTI_ARC=0 before importing layer2d '
            '(fresh process; hard assertion in the converter)',
            'load the 20H G3 start into the frozen JointWorld',
            'detect the routes with a real local planar multi-arc region '
            '(recomputed for 20H; 197 is not assumed)',
            're-plan exactly those routes with the standard G4 planner '
            '(JW.PLAN_CFG, mode=clean) and commit the deterministic minimum '
            'exact-crossing-delta candidate',
            'report residual routes (no legal candidate) instead of deleting '
            'or force-replacing them; assert non-target routes unchanged',
            'assert the converted state contains 0 local multi-arc regions',
            'run the frozen independent validator (fresh 20H process) -> '
            '%s' % _rel(common_off_dir() / 'validation_xyz'),
            'write conversion_report.json + layer_planes.json and '
            'OFF_FEASIBILITY.json; effect A = crossing delta',
        ]
        print_plan(plan, 'convert --dry-run', actions)
        print('conversion out dir: %s' % _rel(common_off_dir()))
        print('A accounting      : crossing_delta = converted crossings - '
              'start crossings (kept SEPARATE from effect B)')
        print('pre-registered    : residual > 0 or illegal route => OFF '
              'infeasible => no diluted OFF arm is ever run')
        return _dry_run_done()

    _ensure_output_dirs()
    # the converter itself re-asserts the OFF policy before importing layer2d
    from . import convert_multiarc20 as CV

    argv = ['--start-dir', str(resolve_start_dir(start.get('start_dir'))),
            '--out-dir', str(common_off_dir()),
            '--log', str(logs_dir() / 'convert.log')]
    if authority:
        argv.extend(['--baseline-dir', str(authority)])
    if args.max_routes:
        argv.extend(['--max-routes', str(int(args.max_routes))])
    if args.skip_validator:
        argv.append('--skip-validator')
    print('[convert] stage-0 OFF conversion: start=%s out=%s'
          % (argv[1], argv[3]), flush=True)
    code = int(CV.main(argv))

    report = _read_json(conversion_report_path(), default={}) or {}
    validator = report.get('validation') or {}
    # a debug run without the independent validator can never freeze a
    # feasible OFF common start (pre-registered gate)
    feasible = (bool(report.get('feasible')) and code == 0
                and not args.skip_validator
                and validator.get('validation_pass') is True)
    payload = dict(
        schema=FEASIBILITY_SCHEMA,
        generated_at=_now(),
        profile=M.PROFILE,
        feasible=bool(feasible),
        conversion_exit_code=int(code),
        start_dir=report.get('start_dir'),
        start_sha256=report.get('start_sha256'),
        start_crossings=report.get('start_crossings'),
        converted=report.get('converted'),
        residual=report.get('residual'),
        residual_route_ids=report.get('residual_route_ids'),
        policy_leaks=report.get('policy_leaks'),
        multi_arc_routes_before=report.get('multi_arc_routes_before'),
        multi_arc_routes_after=report.get('multi_arc_routes_after'),
        crossings_after=report.get('crossings_after'),
        crossing_delta_from_start=report.get('crossing_delta_from_start'),
        total_length_mm=report.get('total_length_mm'),
        routes_sha256=report.get('routes_sha256'),
        assignment_sha256=report.get('assignment_sha256'),
        validation_pass=report.get('validation_pass'),
        validator=dict(
            exit_code=validator.get('exit_code'),
            validation_pass=validator.get('validation_pass'),
            violation_count=validator.get('violation_count'),
            model_plane_count=validator.get('model_plane_count'),
            validation_json=validator.get('validation_json')),
        effect=dict(
            name='A',
            definition='crossing delta caused by re-expressing the inherited '
                       'ON geometry in the OFF grammar',
            crossing_delta=int(report.get('crossing_delta_from_start') or 0),
            note='effect A is NOT attributed to search ability (effect B)'),
        protocol=_protocol_echo(),
        source_snapshot=_source_snapshot(),
    )
    reasons = []
    if not report:
        reasons.append('conversion_report.json missing')
    if int(report.get('residual') or 0) > 0:
        residual_ids = report.get('residual_route_ids') or []
        reasons.append('residual multi-arc routes: %d (first 20: %s)'
                       % (len(residual_ids), residual_ids[:20]))
    if int(report.get('multi_arc_routes_after') or 0) > 0:
        left_ids = report.get('multi_arc_route_ids_after') or []
        reasons.append('multi-arc regions remain after conversion: %d routes '
                       '(first 20: %s; a max-routes debug run also lands here)'
                       % (len(left_ids), left_ids[:20]))
    if report.get('policy_leaks'):
        reasons.append('policy leaks: %s' % report.get('policy_leaks'))
    if report.get('validation') is None:
        reasons.append('independent validator was skipped (--skip-validator)')
    elif report.get('validation_pass') is not True:
        reasons.append('the converted start did not pass the frozen 20H '
                       'validator')
    payload['reasons'] = reasons
    _write_json(feasibility_json_path(), payload)

    if payload['feasible']:
        if abort_json_path().exists():
            abort_json_path().unlink()
        print('[convert] OFF common start FEASIBLE: crossings %s -> %s '
              '(A=%+d), multi_arc %s -> 0, converted %s, residual 0'
              % (payload['start_crossings'], payload['crossings_after'],
                 payload['effect']['crossing_delta'],
                 payload['multi_arc_routes_before'], payload['converted']),
              flush=True)
        return 0
    abort = dict(schema='coldstart20_multiarc_off_infeasible_v1',
                 generated_at=_now(), profile=M.PROFILE,
                 verdict='OFF common start does not exist for this 20H start',
                 reasons=reasons,
                 conversion_report=str(conversion_report_path()),
                 feasibility=str(feasibility_json_path()),
                 rule='pre-registered: residual > 0 or illegal route => do NOT '
                      'run a diluted OFF arm; report effect A (conversion '
                      'cost / residual routes) as the 20H grammar '
                      'feasibility result')
    _write_json(abort_json_path(), abort)
    print('[convert] OFF common start INFEASIBLE (pre-registered handling):',
          file=sys.stderr)
    for reason in reasons:
        print('  - %s' % reason, file=sys.stderr)
    print('[convert] wrote %s ; no arm will be run.'
          % abort_json_path(), file=sys.stderr)
    return 4


# ===========================================================================
# ARM execution (counted-budget search + independent validation + audit)
# ===========================================================================
def _install_profile_validator_patch():
    """Force the engine-embedded validator to run under the 20H profile.

    ``g4.artifacts.run_validation`` launches ``validate_xyz`` in a fresh
    process; that child reads ``reheight21.model`` at import time, so without
    the bootstrap it would validate 20H routes against the frozen 21H table.
    The driver re-binds the function in *its own process only* (no source file
    is modified) so the embedded validator is the same frozen validator under
    the same 20H profile as the fresh-process ``validation_final`` run.
    """
    from ..xyzrouter.g4 import artifacts as ART
    current = getattr(ART.run_validation, '_coldstart20_profile_patch', False)
    if current:
        return False

    def run_validation_20h(run_dir, out_dir, baseline_dir=None,
                           manual_policy=VALIDATOR_POLICY, python=None,
                           log=None):
        del python  # the profile bootstrap is injected via -c
        report = run_validator_xyz(run_dir, out_dir,
                                   baseline_dir=baseline_dir,
                                   manual_policy=manual_policy)
        if log is not None:
            log('[validator] %s -> exit=%s (%.1fs) model_planes=%s'
                % (out_dir, report['exit_code'], report['seconds'],
                   report['model_plane_count']))
        return dict(exit_code=report['exit_code'],
                    seconds=report['seconds'],
                    stdout='',
                    stderr='',
                    run_dir=str(run_dir),
                    out_dir=str(out_dir),
                    manual_policy=str(manual_policy),
                    model_plane_count=report['model_plane_count'],
                    validation_pass=report['validation_pass'],
                    violation_count=report['violation_count'])

    run_validation_20h._coldstart20_profile_patch = True
    ART.run_validation = run_validation_20h
    return True


def _freeze_env_for_arm(arm, start):
    """The ONE changed variable + the verified G3 fingerprint for g4.paths."""
    os.environ['G4_ENABLE_MULTI_ARC'] = ARM_ENV[arm]
    if start:
        os.environ['COLDSTART20_START_SHA'] = str(start.get('routes_sha256'))
        os.environ['COLDSTART20_START_CROSSINGS'] = str(
            int(start.get('crossings_independent') or 0))


def _arm_budget(kind, args):
    if kind['kind'] == 'primary':
        return dict(counted_d56_budget=int(kind['counted_d56_budget']),
                    counted_checks_guard=int(kind['counted_checks_guard']),
                    wall_seconds=float(kind['wall_safety_net_seconds']))
    return dict(counted_d56_budget=0, counted_checks_guard=0,
                wall_seconds=float(kind['wall_seconds']))


def _engine_argv(arm, kind, seed, start_dir, out_dir, tag, args):
    budget = _arm_budget(kind, args)
    argv = ['--arm', ENGINE_ARM,
            '--seconds', str(budget['wall_seconds']),
            '--seed', str(int(seed)),
            '--start-dir', str(start_dir),
            '--out-dir', str(out_dir),
            '--tag', str(tag)]
    if budget['counted_d56_budget'] > 0:
        argv.extend(['--counted-d56-budget',
                     str(budget['counted_d56_budget'])])
    if budget['counted_checks_guard'] > 0:
        argv.extend(['--counted-checks-guard',
                     str(budget['counted_checks_guard'])])
    return argv, budget


def _evaluate_gates(arm, validator, audit, engine_exit, engine_validator=None):
    counts = (validator or {}).get('counts') or {}
    validation_json_path = (validator or {}).get('validation_json')
    if not counts and validation_json_path:
        validation_json = _read_json(validation_json_path, default={}) or {}
        counts = validation_json.get('counts') or {}
    values = dict(
        routed_1024=(counts.get('routed') == 1024
                     and int(counts.get('failed') or 0) == 0),
        validator_pass=((validator or {}).get('validation_pass') is True),
        engine_validator_pass=bool(
            (engine_validator or {}).get('validation_pass') is True
            and int((engine_validator or {}).get('violation_count') or 0) == 0
            and int(((engine_validator or {}).get('model') or {}
                     ).get('plane_count') or 0) == len(M.PLANE_IDS)),
        violations_zero=(int((validator or {}).get('violation_count') or 0)
                         == 0),
        model_height_count_20=(int((validator or {}).get('model_plane_count')
                                  or 0) == len(M.PLANE_IDS)),
        engine_exit_zero=(int(engine_exit or 0) == 0),
        radius_ok=_gate_ge(counts.get('min_flat_arc_radius_mm'),
                           GATE_R15_MM)
        and _gate_ge(counts.get('min_transition_sampled_radius_mm'),
                     GATE_R15_MM - GATE_R15_TRANSITION_TOL),
        clearance_ok=_gate_ge(counts.get('min_3d_clearance_mm'),
                              GATE_3D_CLEARANCE_MM),
        d56_centerline_ok=_gate_ge(counts.get('min_non_crossing_centerline_mm'),
                                   GATE_D56_CENTERLINE_MM),
        multi_arc_absent_for_off=(
            True if arm == 'on'
            else int(((audit or {}).get('multi_arc') or {}).get(
                'total_regions') or 0) == 0),
    )
    consistency = dict(
        validator_crossings_equals_audit=bool(
            (counts.get('same_plane_crossings') is not None)
            and (audit or {}).get('crossings') is not None
            and int(counts['same_plane_crossings'])
            == int((audit or {}).get('crossings'))),
        audit_routes_sha256_equals_best_valid=bool(
            ((audit or {}).get('routes_sha256')
             == ((audit or {}).get('best_valid_routes_sha256')))),
    )
    values['consistency'] = consistency
    values['all_ok'] = all(bool(value) for key, value in values.items()
                           if key != 'consistency') and all(consistency.values())
    return values


def _gate_ge(value, threshold):
    try:
        return float(value) >= float(threshold) - GATE_TOL
    except (TypeError, ValueError):
        return False


def _best_valid_sha(run_dir_path):
    sha = _read_json(Path(run_dir_path) / 'best_valid' / 'SHA256.json',
                     default={}) or {}
    return sha.get('routes_l3d_json')


def _run_arm(args, arm, kind, seed, tag):
    B.install()
    B.assert_20_height_profile('run_multiarc.arm')
    start = _read_json(start_json_path(), default={}) or {}
    out_dir = run_dir(arm, tag)
    budget = _arm_budget(kind, args)
    start_dir = resolve_start_dir(args.start_dir or start.get('start_dir'))
    conversion = _read_json(conversion_report_path(), default={}) or {}
    engine_argv, budget = _engine_argv(arm, kind, seed, start_dir, out_dir,
                                       tag, args)

    if args.dry_run:
        plan = plan_payload(include_aux=(kind['kind'] == 'auxiliary'),
                            start_dir=start_dir,
                            authority_dir=args.baseline_dir,
                            seeds=_seed_list(args))
        actions = [
            'set G4_ENABLE_MULTI_ARC=%s (ON=1 / OFF=0) before importing '
            'layer2d -- the ONLY changed algorithm factor' % ARM_ENV[arm],
            'run the frozen G4 engine in this process: %s'
            % ' '.join(engine_argv),
            'engine-embedded + fresh-process independent validator under the '
            '20H bootstrap -> %s, %s'
            % (_rel(out_dir / 'validation'),
               _rel(out_dir / 'validation_final')),
            'independent geometry audit (frozen D56 recount + multi-arc '
            'census) -> %s' % _rel(out_dir / 'audit_state.json'),
            'evaluate the pre-registered hard gates and write run_meta.json / '
            'RUN_VERDICT.json',
            'start state = the SAME converted common start for both arms: %s '
            '(sha256=%s)' % (_rel(start_dir),
                             conversion.get('routes_sha256')),
        ]
        print_plan(plan, 'arm-%s --dry-run  (tag=%s seed=%s kind=%s)'
                   % (arm, tag, seed, kind['kind']), actions)
        print('arm env var       : G4_ENABLE_MULTI_ARC=%s' % ARM_ENV[arm])
        print('arm out dir       : %s' % _rel(out_dir))
        print('arm budget        : %s' % json.dumps(budget, ensure_ascii=False))
        print('engine argv       : %s' % ' '.join(engine_argv))
        return _dry_run_done()

    # ---- prerequisites ---------------------------------------------------
    authority = resolve_authority_dir(args.baseline_dir)
    problems = []
    if not start.get('ok', False):
        problems.append('START.json is missing or not ok -- run start first')
    if not conversion:
        problems.append('conversion_report.json missing -- run convert first')
    feasibility = _read_json(feasibility_json_path(), default={}) or {}
    if not feasibility.get('feasible'):
        problems.append('OFF_FEASIBILITY.json is missing or not feasible -- '
                        'the pre-registered rule forbids running any arm')
    if not (Path(authority) / 'routes_l3d.json').is_file() or not (
            Path(authority) / 'assignment_1024.csv').is_file():
        problems.append('the 20H identity/port authority does not exist: %s '
                        '(need routes_l3d.json + assignment_1024.csv)'
                        % authority)
    if not (Path(start_dir) / 'routes_l3d.json').is_file():
        problems.append('the converted common start does not exist: %s'
                        % start_dir)
    elif conversion and _sha256(Path(start_dir) / 'routes_l3d.json') != \
            conversion.get('routes_sha256'):
        problems.append('the converted common start SHA changed since the '
                        'conversion report: both arms must start from the same '
                        'frozen state')
    if conversion and int(conversion.get('start_crossings') or -1) != \
            int(start.get('crossings_independent') or -2):
        problems.append('the conversion started from a different state than '
                        'START.json')
    if problems:
        for problem in problems:
            print('[arm-%s] %s' % (arm, problem), file=sys.stderr)
        return 2

    _ensure_output_dirs()
    _freeze_env_for_arm(arm, start)
    patched = _install_profile_validator_patch()
    try:
        from ..xyzrouter.g4 import paths as GP
        # the engine-embedded validator uses GP.AUTHORITY_DIR; bind it to the
        # resolved 20H authority in this process only (no source file change)
        GP.AUTHORITY_DIR = authority
        from ..xyzrouter.g4 import run_g4_engine as ENGINE
    except Exception as error:                          # noqa: BLE001
        print('[arm-%s] cannot import the frozen G4 engine under the 20H '
              'profile: %r' % (arm, error), file=sys.stderr)
        print('[arm-%s] prerequisite: the 20H G3 best_valid must exist '
              '(g4/paths.py fingerprints it at import time).' % arm,
              file=sys.stderr)
        return 2

    print('[arm-%s] tag=%s seed=%d kind=%s start=%s'
          % (arm, tag, seed, kind['kind'], start_dir), flush=True)
    print('[arm-%s] G4_ENABLE_MULTI_ARC=%s  budget=%s  embedded-validator '
          '20H patch=%s' % (arm, ARM_ENV[arm],
                            json.dumps(budget, ensure_ascii=False), patched),
          flush=True)
    started = time.time()
    engine_exit = 1
    engine_error = None
    try:
        engine_exit = int(ENGINE.main(engine_argv))
    except SystemExit as exc:                       # argparse/engine exit
        engine_exit = int(exc.code or 0)
    except Exception as error:                      # noqa: BLE001
        engine_error = repr(error)
        print('[arm-%s] ENGINE CRASHED: %r' % (arm, error), file=sys.stderr)
        import traceback
        traceback.print_exc()
    engine_seconds = round(time.time() - started, 2)
    print('[arm-%s] engine exit=%s in %.1fs (out=%s)'
          % (arm, engine_exit, engine_seconds, out_dir), flush=True)

    # ---- fresh-process independent validator ----------------------------
    engine_validator = _read_json(out_dir / 'validation' / 'validation.json',
                                  default={}) or {}
    validator = None
    if not args.skip_validator:
        validator = run_validator_xyz(out_dir / 'best_valid',
                                      out_dir / 'validation_final',
                                      baseline_dir=authority)
        print('[arm-%s] validation_final exit=%s pass=%s violations=%s '
              'model_planes=%s (%.1fs)'
              % (arm, validator['exit_code'], validator['validation_pass'],
                 validator['violation_count'],
                 validator['model_plane_count'], validator['seconds']),
              flush=True)

    # ---- independent geometry audit -------------------------------------
    audit = None
    if (out_dir / 'best_valid' / 'routes_l3d.json').is_file():
        audit = audit_state(out_dir / 'best_valid',
                            label='%s_%s' % (arm, tag))
        audit['best_valid_routes_sha256'] = _best_valid_sha(out_dir)
        _write_json(out_dir / 'audit_state.json', audit)
        print('[arm-%s] audit crossings=%d multi_arc_regions=%d '
              'multi_arc_routes=%d state_total_matches_audit=%s'
              % (arm, audit['crossings'],
                 audit['multi_arc']['total_regions'],
                 audit['multi_arc']['routes_with_multi_arc'],
                 audit['state_total_matches_audit']), flush=True)

    gates = _evaluate_gates(arm, validator, audit, engine_exit,
                            engine_validator=engine_validator)
    ledger = _read_json(out_dir / 'budget_ledger.json', default={}) or {}
    strategy = _read_json(out_dir / 'strategy_stats.json', default={}) or {}
    extra = strategy.get('extra') or {}
    summary = _read_json(out_dir / 'summary.json', default={}) or {}
    counted = extra.get('counted_budget') or {}
    meta = dict(
        schema='coldstart20_multiarc_run_meta_v1',
        arm=arm,
        tag=tag,
        kind=kind['kind'],
        seed=int(seed),
        g4_enable_multi_arc=ARM_ENV[arm],
        profile=M.PROFILE,
        plane_count=len(M.PLANE_IDS),
        start_dir=_rel(start_dir),
        start_routes_sha256=conversion.get('routes_sha256'),
        start_crossings=conversion.get('start_crossings'),
        start_multi_arc_regions=conversion.get('multi_arc_routes_after'),
        out_dir=_rel(out_dir),
        engine_arm=ENGINE_ARM,
        engine_argv=engine_argv,
        budget=dict(
            counted_d56_budget=int(counted.get('d56_target')
                                   or budget['counted_d56_budget']),
            counted_checks_guard=(counted.get('checks_guard')
                                  if counted.get('checks_guard') is not None
                                  else budget['counted_checks_guard']),
            wall_seconds=budget['wall_seconds'],
            counted_sweep_fraction=PRIMARY['counted_sweep_fraction'],
            stage_sizes=list(PRIMARY['stage_sizes']),
            stage_fractions=list(PRIMARY['stage_fractions']),
            stop_rule=kind['stop_rule']),
        ledger=dict(
            d56_candidate_evals=ledger.get('d56_candidate_evals'),
            route_3d_checks=ledger.get('route_3d_checks'),
            xy_candidates_generated=ledger.get('xy_candidates_generated'),
            valid_candidates=ledger.get('valid_candidates'),
            rejected_3d=ledger.get('rejected_3d'),
            accepted_changes=ledger.get('accepted_changes'),
            transactions=ledger.get('transactions'),
            wall_seconds=ledger.get('wall_seconds')),
        counted_budget=counted,
        summary=dict(
            crossings=summary.get('crossings'),
            crossing_pairs=summary.get('crossing_pairs'),
            routes_with_crossings=summary.get('routes_with_crossings'),
            max_route_crossings=summary.get('max_route_crossings'),
            total_length_mm=summary.get('total_length_mm'),
            start_crossings=summary.get('start_crossings'),
            delta_vs_start=summary.get('delta_vs_start')),
        audit=dict(
            crossings=(audit or {}).get('crossings'),
            crossing_pairs=(audit or {}).get('crossing_pairs'),
            routes_with_crossings=(audit or {}).get('routes_with_crossings'),
            max_route_crossings=(audit or {}).get('max_route_crossings'),
            total_length_mm=(audit or {}).get('total_length_mm'),
            multi_arc_regions=((audit or {}).get('multi_arc') or {}).get(
                'total_regions'),
            multi_arc_routes=((audit or {}).get('multi_arc') or {}).get(
                'routes_with_multi_arc'),
            routes_sha256=(audit or {}).get('routes_sha256'),
            state_total_matches_audit=(audit or {}).get(
                'state_total_matches_audit')),
        engine=dict(exit_code=int(engine_exit), seconds=engine_seconds,
                    error=engine_error),
        validator=validator,
        engine_validator=dict(
            validation_pass=engine_validator.get('validation_pass'),
            violation_count=engine_validator.get('violation_count'),
            model_plane_count=(engine_validator.get('model') or {}
                               ).get('plane_count')),
        gates=gates,
        protocol=_protocol_echo(),
        source_snapshot=_source_snapshot(),
        python=sys.executable,
        host=os.environ.get('COMPUTERNAME') or '',
        started_at='',
        finished_at=_now(),
    )
    _write_json(out_dir / 'run_meta.json', meta)
    _write_json(out_dir / 'RUN_VERDICT.json',
                dict(schema='coldstart20_multiarc_run_verdict_v1',
                     arm=arm, tag=tag, seed=int(seed),
                     all_gates_pass=bool(gates['all_ok']),
                     gates=gates, out_dir=_rel(out_dir),
                     finished_at=_now()))
    print('[arm-%s] gates: %s'
          % (arm, json.dumps(gates, ensure_ascii=False, sort_keys=True)),
          flush=True)
    if engine_error is not None or not gates['all_ok']:
        print('[arm-%s] RUN NOT VALID (engine error or a hard gate failed)'
              % arm, file=sys.stderr)
        return 1
    print('[arm-%s] DONE tag=%s final_crossings=%s (audit) start=%s'
          % (arm, tag, (audit or {}).get('crossings'),
             conversion.get('start_crossings')), flush=True)
    return 0


def cmd_arm(args, arm):
    # IMPORTANT: the ONE changed variable must be set before *any* pipeline
    # import: importing ``xyzrouter.paths`` executes ``xyzrouter/__init__.py``
    # -> ``local_reroute`` -> ``layer2d``, and layer2d reads the multi-arc
    # policy once at import time.  (In --dry-run the default policy must be
    # observable instead, so the env var is left unset.)
    if not args.dry_run:
        os.environ['G4_ENABLE_MULTI_ARC'] = ARM_ENV[arm]
    kind = PRIMARY if args.kind == 'primary' else AUX
    seed = int(args.seed)
    tag = args.tag or _tag(kind, arm, seed)
    return _run_arm(args, arm, kind, seed, tag)


# ===========================================================================
# analysis: independent audit + A/B/C accounting + pre-registered verdict
# ===========================================================================
def _collect_run(arm, kind, seed):
    tag = _tag(kind, arm, seed)
    directory = run_dir(arm, tag)
    if not (directory / 'best_valid' / 'routes_l3d.json').is_file():
        return dict(arm=arm, kind=kind['kind'], tag=tag, seed=int(seed),
                    status='missing', run_dir=_rel(directory))
    meta = _read_json(directory / 'run_meta.json', default={}) or {}
    summary = _read_json(directory / 'summary.json', default={}) or {}
    strategy = _read_json(directory / 'strategy_stats.json',
                          default={}) or {}
    ledger = _read_json(directory / 'budget_ledger.json', default={}) or {}
    validator_engine = _read_json(directory / 'validation' / 'validation.json',
                                  default={}) or {}
    validator_final = _read_json(
        directory / 'validation_final' / 'validation.json', default={}) or {}
    audit = _read_json(directory / 'audit_state.json', default={}) or {}
    if not audit:
        try:
            audit = audit_state(directory / 'best_valid',
                                label='%s_%s' % (arm, tag))
            audit['best_valid_routes_sha256'] = _best_valid_sha(directory)
        except Exception as error:                        # noqa: BLE001
            audit = dict(error=repr(error))
    counts = validator_final.get('counts') or {}
    extra = strategy.get('extra') or {}
    counted = extra.get('counted_budget') or {}
    gates = _evaluate_gates(
        arm,
        dict(validation_pass=validator_final.get('validation_pass'),
             violation_count=validator_final.get('violation_count'),
             model_plane_count=(validator_final.get('model') or {}
                                ).get('plane_count'),
             counts=counts,
             validation_json=validator_final.get('validation_file')),
        audit, meta.get('engine', {}).get('exit_code'),
        engine_validator=validator_engine)
    record = dict(
        arm=arm,
        kind=kind['kind'],
        tag=tag,
        seed=int(seed),
        status='ok',
        run_dir=_rel(directory),
        start_crossings=(meta.get('start_crossings')
                         or summary.get('start_crossings')),
        start_routes_sha256=meta.get('start_routes_sha256'),
        g4_enable_multi_arc=meta.get('g4_enable_multi_arc'),
        final_crossings=_pick(audit.get('crossings'),
                              summary.get('crossings'),
                              counts.get('same_plane_crossings')),
        crossing_pairs=_pick(audit.get('crossing_pairs'),
                             summary.get('crossing_pairs'),
                             counts.get('same_plane_crossing_pairs')),
        routes_with_crossings=_pick(audit.get('routes_with_crossings'),
                                    summary.get('routes_with_crossings')),
        max_route_crossings=_pick(audit.get('max_route_crossings'),
                                  summary.get('max_route_crossings')),
        total_length_mm=_pick(audit.get('total_length_mm'),
                              summary.get('total_length_mm'),
                              counts.get('total_length_mm')),
        flat_arcs=audit.get('flat_arcs'),
        flat_lines=audit.get('flat_lines'),
        transition_parts=audit.get('transition_parts'),
        multi_arc_regions=_pick(
            (audit.get('multi_arc') or {}).get('total_regions'),
            summary.get('multi_arc_regions')),
        multi_arc_routes=_pick(
            (audit.get('multi_arc') or {}).get('routes_with_multi_arc'),
            summary.get('multi_arc_routes')),
        d56_candidate_evals=_pick(ledger.get('d56_candidate_evals'),
                                  counted.get('d56_used')),
        route_3d_checks=ledger.get('route_3d_checks'),
        xy_candidates_generated=ledger.get('xy_candidates_generated'),
        valid_candidates=ledger.get('valid_candidates'),
        rejected_3d=ledger.get('rejected_3d'),
        accepts=ledger.get('accepted_changes'),
        transactions=ledger.get('transactions'),
        wall_seconds=ledger.get('wall_seconds'),
        counted_d56_target=counted.get('d56_target'),
        counted_checks_guard=counted.get('checks_guard'),
        counted_sweep_fraction=counted.get('sweep_fraction'),
        validator_pass=validator_final.get('validation_pass'),
        validator_final_pass=validator_final.get('validation_pass'),
        validator_engine_pass=validator_engine.get('validation_pass'),
        violations=validator_final.get('violation_count'),
        model_plane_count=(validator_final.get('model') or {}).get(
            'plane_count'),
        min_3d_clearance_mm=counts.get('min_3d_clearance_mm'),
        min_non_crossing_centerline_mm=counts.get(
            'min_non_crossing_centerline_mm'),
        min_flat_arc_radius_mm=counts.get('min_flat_arc_radius_mm'),
        min_transition_sampled_radius_mm=counts.get(
            'min_transition_sampled_radius_mm'),
        routed=counts.get('routed'),
        failed=counts.get('failed'),
        routes_sha256=audit.get('routes_sha256'),
        best_valid_routes_sha256=audit.get('best_valid_routes_sha256'),
        gates=gates,
        engine_exit=meta.get('engine', {}).get('exit_code'),
    )
    # budget contract checks (counted mode reached the target, overshoot bounded)
    target = record.get('counted_d56_target')
    used = record.get('d56_candidate_evals')
    record['budget_checks'] = dict(
        counted_target_present=bool(target),
        d56_target_met=bool(target and used is not None
                            and int(used) >= int(target)),
        d56_overshoot_ratio=(None if not target or used is None
                             else round((int(used) - int(target))
                                        / float(target), 6)),
        d56_overshoot_ok=(None if not target or used is None
                          else (int(used) - int(target))
                          / float(target) <= D56_OVERSHOOT_MAX),
        checks_guard_present=bool(record.get('counted_checks_guard')),
        checks_guard_not_hit=(None if not record.get('counted_checks_guard')
                              else int(record.get('route_3d_checks') or 0)
                              < int(record['counted_checks_guard'])),
    )
    record['valid'] = bool(gates['all_ok']
                           and record['budget_checks']['d56_target_met']
                           and record['budget_checks']['d56_overshoot_ok'])
    return record


def _pick(*values):
    for value in values:
        if value is not None:
            return value
    return None


def _paired_block(runs, metric):
    by_seed = {arm: {int(run['seed']): run for run in runs if run['arm'] == arm
                     and run['status'] == 'ok'}
               for arm in ARMS}
    seeds = sorted(set(by_seed['on']) & set(by_seed['off']))
    on = [by_seed['on'][seed].get(metric) for seed in seeds]
    off = [by_seed['off'][seed].get(metric) for seed in seeds]
    diffs = [(a - b) if (a is not None and b is not None) else None
             for a, b in zip(on, off)]
    block = dict(
        seeds=seeds,
        on=on,
        off=off,
        diff_on_minus_off=diffs,
        n_on_better=sum(1 for d in diffs if d is not None and d < 0),
        n_off_better=sum(1 for d in diffs if d is not None and d > 0),
        n_tie=sum(1 for d in diffs if d == 0),
        on_stats=_stats([v for v in on]),
        off_stats=_stats([v for v in off]),
        diff_stats=_stats([v for v in diffs]),
    )
    if metric == 'total_length_mm':
        relative = []
        for a, b in zip(on, off):
            if a is not None and b not in (None, 0):
                relative.append((float(a) - float(b)) / float(b))
        block['relative_on_vs_off'] = [round(v, 6) for v in relative]
        block['relative_mean'] = (round(sum(relative) / len(relative), 6)
                                  if relative else None)
    return block


def _load_historical_reference():
    """Read-only historical 21H FINAL numbers (effect C reference, NOT 20H)."""
    base = ROOT / 'experiments' / 'G4_MULTI_ARC_ABLATION_FINAL_1024'
    summary_path = base / 'tables' / 'summary_c1.json'
    stage0_path = base / 'tables' / 'stage0_audit.json'
    payload = _read_json(summary_path, default=None)
    stage0 = _read_json(stage0_path, default=None)
    if not isinstance(payload, dict) and not isinstance(stage0, dict):
        return dict(available=False, path=_rel(summary_path))
    paired = (payload or {}).get('paired') or {}
    final = paired.get('final_crossings') or {}
    decision = (payload or {}).get('decision') or {}
    historical_a = None
    if isinstance(stage0, dict):
        historical_a = dict(
            source=_rel(stage0_path),
            g3_crossings=(stage0.get('g3') or {}).get('crossings'),
            converted_crossings=(stage0.get('converted') or {}).get(
                'crossings'),
            targets=stage0.get('targets'),
            converted=stage0.get('converted_count'),
            residual=stage0.get('residual'),
            delta=stage0.get('delta_total_independent'),
            length_delta_mm=(stage0.get('length') or {}).get(
                'converted_minus_g3_mm'),
        )
    return dict(
        available=True,
        path=_rel(summary_path),
        source='experiments/G4_MULTI_ARC_ABLATION_FINAL_1024 (21H, read-only)',
        common_start_crossings=(payload or {}).get('start_crossings'),
        on_final=final.get('on'),
        off_final=final.get('off'),
        paired_diff=final.get('diff_on_minus_off'),
        paired_diff_mean=(final.get('diff_stats') or {}).get('mean'),
        verdict=decision.get('verdict'),
        historical_A=historical_a,
        historical_C=dict(
            source='G4_MULTI_ARC_ABLATION_1024/report.md (read-only prose)',
            on_final=1202, off_final=3484, difference=2282,
            note='historical mixed package (different start + unequal budget); '
                 'it is A + B + budget/start differences, never a 20H number'),
        note='historical 21H numbers; never mixed into the 20H effect B and '
             'never added to effect A',
    )


def _markdown_summary(summary):
    lines = ['# 20H multi-arc ON/OFF ablation -- %s' % summary['label'], '']
    start = summary.get('start_crossings')
    lines.append('* profile: `%s` (%s routing heights)'
                 % (summary['profile'], summary['plane_count']))
    lines.append('* common converted start crossings: **%s**' % start)
    lines.append('* seeds: %s' % ', '.join(str(s) for s in summary['seeds']))
    lines.append('* budget: %s' % summary['budget']['stop_rule'])
    lines.append('')
    metric_rows = [
        ('final crossings', 'final_crossings'),
        ('crossing pairs', 'crossing_pairs'),
        ('routes with crossings', 'routes_with_crossings'),
        ('max route crossings', 'max_route_crossings'),
        ('total length (mm)', 'total_length_mm'),
        ('flat arcs', 'flat_arcs'),
        ('multi-arc regions', 'multi_arc_regions'),
        ('d56_candidate_evals', 'd56_candidate_evals'),
        ('route_3d_checks', 'route_3d_checks'),
        ('wall seconds', 'wall_seconds'),
    ]
    lines.append('| metric | ON (mean) | OFF (mean) | paired diff (mean) '
                 '| ON better seeds |')
    lines.append('|---|---:|---:|---:|---:|')
    for title, key in metric_rows:
        block = summary['paired'].get(key) or {}
        on = (block.get('on_stats') or {}).get('mean')
        off = (block.get('off_stats') or {}).get('mean')
        diff = (block.get('diff_stats') or {}).get('mean')
        lines.append('| %s | %s | %s | %s | %s/%s |'
                     % (title, _fmt(on), _fmt(off), _fmt(diff),
                        block.get('n_on_better'), block.get('n_seeds')))
    lines.append('')
    lines.append('## Pre-registered verdict')
    decision = summary['decision']
    lines.append('* verdict: **%s**' % decision['verdict'])
    lines.append('* rule: %s' % decision['rule'])
    lines.append('* effect floor used: **%.1f crossings** (%s)'
                 % (decision['effect_floor_crossings'],
                    'max(200, 5 % of common-start crossings)'))
    lines.append('* mean paired gap (ON-OFF): **%s**'
                 % _fmt(decision['mean_paired_gap']))
    lines.append('* seeds ON better: %s/%s' % (decision['seeds_on_better'],
                                               decision['n_seeds']))
    lines.append('* ON length change vs OFF: %s'
                 % ('n/a' if decision['relative_length_change'] is None
                    else '%+.2f %%' % (100 * decision['relative_length_change'])))
    lines.append('* all hard gates pass: **%s**' % decision['all_hard_gates_pass'])
    for reason in decision.get('reasons') or []:
        lines.append('  * %s' % reason)
    lines.append('')
    lines.append('> Exploratory statistics: 3 seeds, no significance test. '
                 'Effect A (conversion, shown below) and effect B (this table) '
                 'are separate quantities and must not be added.')
    lines.append('')
    if summary.get('effect_a'):
        effect_a = summary['effect_a']
        lines.append('## Effect A -- Stage-0 conversion cost (separate)')
        lines.append('* %s -> %s crossings (%+d); converted %s routes, '
                     'residual %s'
                     % (effect_a.get('start_crossings'),
                        effect_a.get('crossings_after'),
                        int(effect_a.get('crossing_delta') or 0),
                        effect_a.get('converted'), effect_a.get('residual')))
        lines.append('')
    return '\n'.join(lines) + '\n'


def cmd_analyse(args):
    B.install()
    B.assert_20_height_profile('run_multiarc.analyse')

    kinds = [PRIMARY] + ([AUX] if args.with_aux else [])
    analyse_seeds = _seed_list(args)
    plan_runs = [(arm, kind, seed) for kind in kinds for arm in ARMS
                 for seed in analyse_seeds]

    if args.dry_run:
        plan = plan_payload(include_aux=bool(args.with_aux),
                            start_dir=args.start_dir,
                            authority_dir=args.baseline_dir,
                            seeds=_seed_list(args))
        actions = [
            'collect every run under %s (%d expected)' % (_rel(runs_root()),
                                                          len(plan_runs)),
            'load/recompute the independent geometry audit (frozen D56 '
            'crossings + planar multi-arc census)',
            'evaluate the pre-registered hard gates per run (1024/1024, R15, '
            '3D 0.05, D56 0.08, 0 violations, OFF multi-arc = 0, validator pass)',
            'build the A / B / C accounting (A conversion, B search, C '
            'historical 21H reference -- never merged)',
            'evaluate the pre-registered decision rule on the primary arms',
            'write tables/runs.{json,csv}, tables/summary_c1.{json,md}, '
            'tables/abc.json, tables/decision.json, validation/summary.json',
        ]
        print_plan(plan, 'analyse --dry-run', actions)
        print('analysis inputs   : START.json=%s  conversion_report=%s  '
              'feasibility=%s'
              % (start_json_path().is_file(),
                 conversion_report_path().is_file(),
                 feasibility_json_path().is_file()))
        print('analysis outputs  : %s' % _rel(tables_dir()))
        return _dry_run_done()

    _ensure_output_dirs()
    start = _read_json(start_json_path(), default={}) or {}
    conversion = _read_json(conversion_report_path(), default={}) or {}
    feasibility = _read_json(feasibility_json_path(), default={}) or {}

    runs = [_collect_run(arm, kind, seed)
            for (arm, kind, seed) in plan_runs]
    present = [run for run in runs if run['status'] == 'ok']
    if not present:
        print('[analyse] no completed arm run found under %s -- nothing to '
              'analyse' % runs_root(), file=sys.stderr)
        _write_json(tables_dir() / 'runs.json',
                    dict(schema='coldstart20_multiarc_runs_v1',
                         generated_at=_now(), runs=runs))
        return 2

    start_crossings = (conversion.get('start_crossings')
                       or start.get('crossings_independent'))
    effect_floor = max(int(EFFECT_FLOOR_ABS),
                       int(round(EFFECT_FLOOR_RATIO * int(start_crossings or 0))))

    summaries = {}
    for kind in kinds:
        kind_runs = [run for run in runs if run['kind'] == kind['kind']]
        paired = {}
        for metric in ('final_crossings', 'delta_vs_start', 'crossing_pairs',
                       'routes_with_crossings', 'max_route_crossings',
                       'total_length_mm', 'multi_arc_regions',
                       'multi_arc_routes', 'd56_candidate_evals',
                       'route_3d_checks', 'wall_seconds'):
            if metric == 'delta_vs_start':
                for run in kind_runs:
                    if run.get('status') == 'ok' and \
                            run.get('final_crossings') is not None and \
                            run.get('start_crossings') is not None:
                        run['delta_vs_start'] = (int(run['final_crossings'])
                                                 - int(run['start_crossings']))
            paired[metric] = _paired_block(kind_runs, metric)
            paired[metric]['n_seeds'] = len(paired[metric]['seeds'])
        gates = {run['arm'] + '/' + run['tag']: run.get('gates')
                 for run in kind_runs if run.get('status') == 'ok'}
        all_gates = bool(gates) and all(
            (gate or {}).get('all_ok') for gate in gates.values())
        all_valid = all(run.get('valid') for run in kind_runs
                        if run.get('status') == 'ok') and \
            all(run['status'] == 'ok' for run in kind_runs)
        mean_gap = (paired['final_crossings'].get('diff_stats') or {}).get('mean')
        relative_length = paired['total_length_mm'].get('relative_mean')
        direction_ok = (paired['final_crossings']['n_on_better']
                        == len(paired['final_crossings']['seeds'])
                        and paired['final_crossings']['n_off_better'] == 0
                        and len(paired['final_crossings']['seeds']) ==
                        len(analyse_seeds))
        effect_ok = bool(mean_gap is not None and
                         mean_gap <= -float(effect_floor))
        length_ok = bool(relative_length is not None
                         and relative_length <= LENGTH_MAX_GROWTH)
        if not direction_ok or (mean_gap is not None and mean_gap >= 0):
            verdict = 'C'
            reasons = ['direction inconsistent or mean paired gap >= 0']
        elif not (effect_ok and length_ok and all_gates and all_valid):
            verdict = 'B'
            reasons = []
            if not effect_ok:
                reasons.append('paired mean gap %.1f is smaller than the '
                               'pre-registered floor %.1f'
                               % (mean_gap, effect_floor))
            if not length_ok:
                reasons.append('ON length change exceeds +%.0f %%'
                               % (100 * LENGTH_MAX_GROWTH))
            if not all_gates:
                reasons.append('a hard gate failed in at least one run')
            if not all_valid:
                reasons.append('a run is missing or did not meet its counted '
                               'budget contract')
        else:
            verdict = 'A'
            reasons = ['3/3 seeds ON<OFF, paired mean gap %.1f >= floor %.1f, '
                       'length change %+.2f %%, all hard gates pass'
                       % (mean_gap, effect_floor, 100 * relative_length)]
        summary = dict(
            schema='coldstart20_multiarc_summary_v1',
            generated_at=_now(),
            kind=kind['kind'],
            label=('Primary: equal candidate-evaluation budget (d56 = %d)'
                   % kind['counted_d56_budget']
                   if kind['kind'] == 'primary'
                   else 'Auxiliary: equal wall-clock budget (%.0f s)'
                        % kind['wall_seconds']),
            profile=M.PROFILE,
            plane_count=len(M.PLANE_IDS),
            seeds=list(analyse_seeds),
            start_crossings=start_crossings,
            budget=dict(kind),
            runs=[run for run in kind_runs],
            paired=paired,
            gates=gates,
            decision=dict(
                rule='A: 3/3 seeds ON<OFF and paired mean gap >= '
                     'max(200, 5 % of common-start crossings) and ON total '
                     'length increase <= 5 % and all hard gates pass; C: '
                     'paired mean gap <= 0 or direction inconsistent; '
                     'B: otherwise',
                effect_floor_crossings=float(effect_floor),
                effect_floor_abs=EFFECT_FLOOR_ABS,
                effect_floor_ratio=EFFECT_FLOOR_RATIO,
                mean_paired_gap=mean_gap,
                seeds_on_better=paired['final_crossings']['n_on_better'],
                seeds_off_better=paired['final_crossings']['n_off_better'],
                n_seeds=len(paired['final_crossings']['seeds']),
                relative_length_change=relative_length,
                all_hard_gates_pass=all_gates,
                all_runs_valid=all_valid,
                verdict=verdict,
                reasons=reasons,
                caveat='exploratory statistics (3 seeds, no significance '
                       'test, single machine); conclusions hold only for the '
                       'frozen D56 candidate grammar and this 20H start'),
        )
        summaries[kind['kind']] = summary

    primary = summaries['primary']
    effect_a = dict(
        name='A',
        definition=conversion.get('schema') and
        'crossing delta when the inherited ON geometry is re-expressed in the '
        'OFF grammar (Stage-0 conversion)',
        start_crossings=conversion.get('start_crossings'),
        crossings_after=conversion.get('crossings_after'),
        crossing_delta=conversion.get('crossing_delta_from_start'),
        multi_arc_routes_before=conversion.get('multi_arc_routes_before'),
        converted=conversion.get('converted'),
        residual=conversion.get('residual'),
        residual_route_ids=conversion.get('residual_route_ids'),
        multi_arc_routes_after=conversion.get('multi_arc_routes_after'),
        total_length_mm=conversion.get('total_length_mm'),
        validation_pass=conversion.get('validation_pass'),
        feasible=feasibility.get('feasible'),
        report=str(conversion_report_path()),
    )
    effect_b = dict(
        name='B',
        definition='ON vs OFF search result from the SAME converted common '
                   'start, same code, same counted budget, only '
                   'enable_multi_arc toggled',
        start_crossings=start_crossings,
        on_final=primary['paired']['final_crossings']['on'],
        off_final=primary['paired']['final_crossings']['off'],
        paired_diff=primary['paired']['final_crossings']['diff_on_minus_off'],
        paired_mean=primary['paired']['final_crossings']['diff_stats']['mean'],
        verdict=primary['decision']['verdict'],
    )
    abc = dict(
        schema='coldstart20_multiarc_abc_accounting_v1',
        generated_at=_now(),
        profile=M.PROFILE,
        A=effect_a,
        B=effect_b,
        C=_load_historical_reference(),
        separation_rule='A, B and C are three distinct quantities: C is the '
                        'historical 21H mixed-package difference (A + B + '
                        'budget/start differences); A is conversion cost only; '
                        'B is search-ability only. Never add A and B into one '
                        '"value of multi-arc" number and never attribute the '
                        'conversion cost to the search gain.',
    )
    effects = dict(schema='coldstart20_multiarc_effects_v1',
                   generated_at=_now(), profile=M.PROFILE,
                   A=effect_a, B=effect_b, C=abc['C'])

    # ---- write artifacts -------------------------------------------------
    _write_json(tables_dir() / 'runs.json',
                dict(schema='coldstart20_multiarc_runs_v1',
                     generated_at=_now(), profile=M.PROFILE,
                     seeds=list(analyse_seeds), runs=runs))
    _write_csv(tables_dir() / 'runs.csv', [
        dict(arm=run['arm'], kind=run['kind'], tag=run['tag'],
             seed=run['seed'], status=run['status'],
             valid=run.get('valid'),
             start_crossings=run.get('start_crossings'),
             final_crossings=run.get('final_crossings'),
             crossing_pairs=run.get('crossing_pairs'),
             routes_with_crossings=run.get('routes_with_crossings'),
             max_route_crossings=run.get('max_route_crossings'),
             total_length_mm=run.get('total_length_mm'),
             multi_arc_regions=run.get('multi_arc_regions'),
             multi_arc_routes=run.get('multi_arc_routes'),
             d56_candidate_evals=run.get('d56_candidate_evals'),
             route_3d_checks=run.get('route_3d_checks'),
             wall_seconds=run.get('wall_seconds'),
             validator_pass=run.get('validator_pass'),
             violations=run.get('violations'),
             min_3d_clearance_mm=run.get('min_3d_clearance_mm'),
             min_flat_arc_radius_mm=run.get('min_flat_arc_radius_mm'),
             routes_sha256=run.get('routes_sha256'),
             all_gates_pass=(run.get('gates') or {}).get('all_ok'),
             run_dir=run.get('run_dir'))
        for run in runs])
    _write_json(tables_dir() / 'summary_c1.json', primary)
    (tables_dir() / 'summary_c1.md').write_text(
        _markdown_summary(primary), encoding='utf-8')
    if 'auxiliary' in summaries:
        _write_json(tables_dir() / 'summary_a1.json', summaries['auxiliary'])
        (tables_dir() / 'summary_a1.md').write_text(
            _markdown_summary(summaries['auxiliary']), encoding='utf-8')
    _write_json(tables_dir() / 'abc.json', abc)
    _write_json(tables_dir() / 'effects.json', effects)
    _write_json(tables_dir() / 'decision.json', primary['decision'])

    # ---- effect A per-route table ---------------------------------------
    records = conversion.get('records') or []
    _write_csv(tables_dir() / 'stage0_per_route.csv', records)
    stage0 = dict(
        schema='coldstart20_multiarc_stage0_audit_v1',
        generated_at=_now(),
        profile=M.PROFILE,
        start_dir=conversion.get('start_dir'),
        start_sha256=conversion.get('start_sha256'),
        start_crossings=conversion.get('start_crossings'),
        out_dir=conversion.get('out_dir'),
        routes_sha256=conversion.get('routes_sha256'),
        assignment_sha256=conversion.get('assignment_sha256'),
        multi_arc_routes_before=conversion.get('multi_arc_routes_before'),
        multi_arc_route_ids_before=conversion.get('multi_arc_route_ids_before'),
        targets=conversion.get('targets'),
        converted=conversion.get('converted'),
        residual=conversion.get('residual'),
        residual_route_ids=conversion.get('residual_route_ids'),
        multi_arc_routes_after=conversion.get('multi_arc_routes_after'),
        crossings_after=conversion.get('crossings_after'),
        crossing_delta_from_start=conversion.get('crossing_delta_from_start'),
        total_length_mm=conversion.get('total_length_mm'),
        ledger=conversion.get('ledger'),
        validation=conversion.get('validation'),
        validation21=conversion.get('validation21'),
        per_route_table=str(tables_dir() / 'stage0_per_route.csv'),
    )
    _write_json(tables_dir() / 'stage0_audit.json', stage0)

    # ---- independent validation summary ---------------------------------
    validation_summary = dict(
        schema='coldstart20_multiarc_validation_summary_v1',
        generated_at=_now(),
        profile=M.PROFILE,
        validator='four_side_1024.fanout1024.xyzrouter.validate_xyz '
                  '(fresh process, coldstart20.bootstrap installed first)',
        manual_policy=VALIDATOR_POLICY,
        expected_model_height_count=len(M.PLANE_IDS),
        runs=[dict(arm=run['arm'], tag=run['tag'], kind=run['kind'],
                   seed=run['seed'],
                   status=run['status'],
                   validator_pass=run.get('validator_pass'),
                   validator_engine_pass=run.get('validator_engine_pass'),
                   violations=run.get('violations'),
                   model_plane_count=run.get('model_plane_count'),
                   multi_arc_regions=run.get('multi_arc_regions'),
                   gates=run.get('gates'))
              for run in runs],
    )
    _write_json(validation_dir() / 'summary.json', validation_summary)
    (validation_dir() / 'summary.md').write_text(
        _markdown_validation(validation_summary), encoding='utf-8')

    # ---- top-level report ----------------------------------------------
    report_lines = [
        '# 20H planar multi-arc ON/OFF ablation -- analysis',
        '',
        '* profile: `%s` (%d routing heights, %d body)'
        % (M.PROFILE, len(M.PLANE_IDS), len(M.BODY_PLANES)),
        '* common converted start: %s crossings (sha256 `%s`)'
        % (start_crossings, (conversion.get('routes_sha256') or '')[:16]),
        '* OFF feasibility: %s'
        % ('feasible' if feasibility.get('feasible') else
           'infeasible / not attempted'),
        '* primary verdict: **%s**' % primary['decision']['verdict'],
        '* auxiliary verdict: %s'
        % (summaries.get('auxiliary', {}).get('decision', {}).get('verdict',
                                                                  'n/a')),
        '',
        '## Effect A (conversion cost, separate from search)',
        '%s -> %s crossings (%+d), converted %s routes, residual %s'
        % (effect_a['start_crossings'], effect_a['crossings_after'],
           int(effect_a['crossing_delta'] or 0), effect_a['converted'],
           effect_a['residual']),
        '',
        '## Effect B (the only search-ability measurement)',
        'ON final crossings mean %s vs OFF mean %s; paired mean gap %s; '
        'verdict %s'
        % (_fmt((primary['paired']['final_crossings'].get('on_stats')
                 or {}).get('mean')),
           _fmt((primary['paired']['final_crossings'].get('off_stats')
                 or {}).get('mean')),
           _fmt(effect_b['paired_mean']),
           primary['decision']['verdict']),
        '',
        '## Effect C (historical 21H reference, read-only)',
        json.dumps(abc['C'], ensure_ascii=False, indent=1),
        '',
        '## Separation rule',
        abc['separation_rule'],
        '',
        'Tables: `tables/summary_c1.md`, `tables/abc.json`, '
        '`tables/stage0_audit.json`, `tables/runs.csv`; '
        'validation: `validation/summary.md`.',
    ]
    (exp_root() / 'report.md').write_text('\n'.join(report_lines) + '\n',
                                          encoding='utf-8')
    print('[analyse] verdict(primary)=%s  mean paired gap=%s  '
          'effect floor=%.0f  start crossings=%s'
          % (primary['decision']['verdict'],
             _fmt(primary['decision']['mean_paired_gap']),
             float(effect_floor), start_crossings), flush=True)
    print('[analyse] wrote %s/summary_c1.md, summary_a1.md (if aux), abc.json, '
          'decision.json, stage0_audit.json, validation/summary.md, report.md'
          % _rel(tables_dir()), flush=True)
    return 0


def _markdown_validation(payload):
    lines = ['# Independent validation summary (20H multi-arc ablation)', '']
    lines.append('Validator: %s' % payload['validator'])
    lines.append('manual_policy: `%s`; expected model heights: %s'
                 % (payload['manual_policy'],
                    payload['expected_model_height_count']))
    lines.append('')
    lines.append('| arm | tag | status | validator | engine val | violations '
                 '| model heights | multi-arc | gates |')
    lines.append('|---|---|---|---|---|---:|---:|---:|---|')
    for run in payload['runs']:
        lines.append('| %s | %s | %s | %s | %s | %s | %s | %s | %s |'
                     % (run['arm'], run['tag'], run['status'],
                        run['validator_pass'], run['validator_engine_pass'],
                        run['violations'], run['model_plane_count'],
                        run['multi_arc_regions'],
                        (run['gates'] or {}).get('all_ok')))
    lines.append('')
    return '\n'.join(lines) + '\n'


# ===========================================================================
# chain / all orchestration
# ===========================================================================
CHAIN_SCHEMA = 'coldstart20_multiarc_chain_v1'


def _stage_header(name):
    print('=' * 78, flush=True)
    print('[chain] stage: %s' % name, flush=True)
    print('=' * 78, flush=True)


def _spawn_stage(name, argv, timeout=None):
    log_path = logs_dir() / ('%s.log' % name)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    print('[chain] $ %s' % ' '.join(argv), flush=True)
    result = subprocess.run(argv, cwd=str(ROOT), capture_output=True,
                            text=True, encoding='utf-8', errors='replace',
                            timeout=timeout)
    seconds = round(time.time() - started, 2)
    log_path.write_text(
        '#' * 78 + '\n# command: %s\n# exit=%s seconds=%.2f\n'
        % (' '.join(argv), result.returncode, seconds) + '#' * 78 + '\n'
        + (result.stdout or '') + '\n--- stderr ---\n' + (result.stderr or ''),
        encoding='utf-8')
    print('[chain] exit=%s in %.1fs (log %s)'
          % (result.returncode, seconds, _rel(log_path)), flush=True)
    tail = (result.stdout or '').strip().splitlines()[-12:]
    for line in tail:
        print('  | %s' % line, flush=True)
    if result.returncode != 0:
        for line in (result.stderr or '').strip().splitlines()[-12:]:
            print('  ! %s' % line, file=sys.stderr, flush=True)
    return dict(stage=name, command=argv, exit_code=int(result.returncode),
                seconds=seconds, log=_rel(log_path))


def _python_argv(action, extra):
    return [sys.executable, '-m', MODULE, action] + list(extra)


def _seed_list(args):
    text = str(args.seeds or ','.join(str(seed) for seed in SEEDS))
    return [int(part) for part in text.split(',') if str(part).strip()]


def _ensure_start_stage(args, stages):
    start = _read_json(start_json_path(), default={}) or {}
    if start and not args.refresh_start:
        current = resolve_start_dir(start.get('start_dir'))
        routes_path = Path(current) / 'routes_l3d.json'
        sha_ok = (routes_path.is_file()
                  and _sha256(routes_path) == start.get('routes_sha256'))
        if sha_ok and start.get('ok'):
            print('[chain] start already verified (START.json matches the '
                  'current sha and ok=true)', flush=True)
            return 0
        if sha_ok and not start.get('ok'):
            print('[chain] START.json exists but records ok=false (the common '
                  'start failed a check); refusing to continue. Re-run '
                  '"start --force" after fixing the start.', file=sys.stderr)
            return 1
        print('[chain] START.json is stale (start changed); re-running start',
              flush=True)
    argv = _python_argv('start', [])
    if args.start_dir:
        argv.extend(['--start-dir', str(args.start_dir)])
    if args.baseline_dir:
        argv.extend(['--baseline-dir', str(args.baseline_dir)])
    if args.skip_validator:
        argv.append('--skip-validator')
    if args.force or args.refresh_start:
        argv.append('--force')
    stage = _spawn_stage('01_start', argv)
    stages.append(stage)
    return stage['exit_code']


def _ensure_convert_stage(args, stages):
    start = _read_json(start_json_path(), default={}) or {}
    feasibility = _read_json(feasibility_json_path(), default={}) or {}
    report = _read_json(conversion_report_path(), default={}) or {}
    start_ok = (start.get('routes_sha256')
                and report.get('start_sha256') == start.get('routes_sha256'))
    if feasibility.get('feasible') and report and start_ok \
            and not args.refresh_convert:
        print('[chain] converted common start already frozen '
              '(feasible, same start sha)', flush=True)
        return 0
    if feasibility and feasibility.get('feasible') is False \
            and report and start_ok and not args.refresh_convert:
        print('[chain] pre-registered OFF infeasibility already recorded; '
              'refusing to run any arm', file=sys.stderr)
        return 4
    argv = _python_argv('convert', [])
    if args.start_dir:
        argv.extend(['--start-dir', str(args.start_dir)])
    if args.baseline_dir:
        argv.extend(['--baseline-dir', str(args.baseline_dir)])
    if args.skip_validator:
        argv.append('--skip-validator')
    if args.force:
        argv.append('--force')
    stage = _spawn_stage('02_convert', argv,
                         timeout=float(args.convert_timeout))
    stages.append(stage)
    return stage['exit_code']


def _arm_label(kind, arm, seed):
    return '%s_%s_%s' % (kind['tag_prefix'], arm, seed)


def _run_matrix(args, kinds, stages):
    codes = {}
    seeds = _seed_list(args)
    for kind in kinds:
        for seed in seeds:
            for arm in ARMS:
                label = _arm_label(kind, arm, seed)
                argv = _python_argv('arm-%s' % arm,
                                    ['--seed', str(seed),
                                     '--tag', label,
                                     '--kind', kind['kind']])
                if args.start_dir:
                    argv.extend(['--start-dir', str(args.start_dir)])
                if args.baseline_dir:
                    argv.extend(['--baseline-dir', str(args.baseline_dir)])
                if args.skip_validator:
                    argv.append('--skip-validator')
                stage = _spawn_stage('03_%s' % label, argv,
                                     timeout=float(args.arm_timeout))
                stages.append(stage)
                codes[label] = stage['exit_code']
    return codes


def _analyse_argv(args, with_aux):
    argv = _python_argv('analyse', [])
    if with_aux:
        argv.append('--with-aux')
    if args.baseline_dir:
        argv.extend(['--baseline-dir', str(args.baseline_dir)])
    return argv


def _run_chain(args, with_aux):
    _ensure_output_dirs()
    stages = []
    codes = {}
    started = _now()

    _stage_header('01_start')
    code = _ensure_start_stage(args, stages)
    codes['start'] = code
    if code != 0:
        print('[chain] start failed -- stopping', file=sys.stderr)
        return _finish_chain(args, stages, codes, started, {'aborted': 'start'})

    _stage_header('02_convert')
    code = _ensure_convert_stage(args, stages)
    codes['convert'] = code
    if code == 4:
        print('[chain] pre-registered OFF infeasibility: no arm is run '
              '(see OFF_FEASIBILITY.json / ABORTED_OFF_INFEASIBLE.json)',
              file=sys.stderr)
        return _finish_chain(args, stages, codes, started,
                             {'aborted': 'off_infeasible'})
    if code != 0:
        print('[chain] convert failed -- stopping', file=sys.stderr)
        return _finish_chain(args, stages, codes, started, {'aborted': 'convert'})

    _stage_header('03_arms (primary)')
    codes.update(_run_matrix(args, [PRIMARY], stages))
    if with_aux:
        _stage_header('03_arms (auxiliary)')
        codes.update(_run_matrix(args, [AUX], stages))

    _stage_header('04_analyse')
    stage = _spawn_stage('04_analyse', _analyse_argv(args, with_aux),
                         timeout=float(args.analyse_timeout))
    stages.append(stage)
    codes['analyse'] = stage['exit_code']
    return _finish_chain(args, stages, codes, started, {})


def _finish_chain(args, stages, codes, started, extra):
    payload = dict(
        schema=CHAIN_SCHEMA,
        command=args.command,
        generated_at=_now(),
        started_at=started,
        profile=M.PROFILE,
        plane_count=len(M.PLANE_IDS),
        seeds=_seed_list(args),
        budget=dict(primary=dict(PRIMARY), auxiliary=dict(AUX)),
        stages=stages,
        exit_codes=codes,
        protocol=_protocol_echo(),
        source_snapshot=_source_snapshot(),
        **extra)
    _write_json(exp_root() / 'CHAIN.json', payload)
    if extra.get('aborted'):
        return 4 if extra['aborted'] == 'off_infeasible' else 1
    arms_ok = all(code == 0 for label, code in codes.items()
                  if label not in ('start', 'convert', 'analyse'))
    analyse_code = codes.get('analyse')
    print('=' * 78, flush=True)
    print('[chain] summary: %s'
          % json.dumps({label: code for label, code in codes.items()}),
          flush=True)
    if analyse_code == 0:
        summary = _read_json(tables_dir() / 'summary_c1.json', default={})
        decision = (summary or {}).get('decision') or {}
        print('[chain] pre-registered verdict: %s (A/B/C accounting in %s)'
              % (decision.get('verdict'), _rel(tables_dir() / 'abc.json')),
              flush=True)
    print('[chain] CHAIN.json written to %s' % _rel(exp_root() / 'CHAIN.json'),
          flush=True)
    return 0 if (arms_ok and analyse_code == 0) else 1


def cmd_chain(args):
    if args.dry_run:
        plan = plan_payload(include_aux=False,
                            start_dir=args.start_dir,
                            authority_dir=args.baseline_dir,
                            seeds=_seed_list(args))
        actions = [
            'start  -- verify the 20H G3 best_valid common start (skipped when '
            'START.json already matches the current sha)',
            'convert -- Stage-0 OFF conversion + OFF feasibility gate (effect A)',
            'arm-on  x %d seeds: G4_ENABLE_MULTI_ARC=1 from the SAME converted '
            'start' % len(_seed_list(args)),
            'arm-off x %d seeds: G4_ENABLE_MULTI_ARC=0 from the SAME converted '
            'start' % len(_seed_list(args)),
            'analyse -- independent audits, A/B/C accounting, pre-registered '
            'verdict',
            'stop before any arm if the conversion leaves a residual multi-arc '
            'route or an illegal route (pre-registered OFF feasibility)',
        ]
        switch = print_plan(plan, 'chain --dry-run', actions)
        print('start gate        : START.json present=%s  ok=%s'
              % (start_json_path().is_file(),
                 (_read_json(start_json_path(), default={}) or {}).get('ok')))
        print('multi-arc switch  : verified at %s:%s (default ON, env '
              'G4_ENABLE_MULTI_ARC=1/0 per arm)'
              % (switch['layer2d_file'], switch['policy_definition_line']))
        print('run commands      : python -m %s start | convert | arm-on | '
              'arm-off | analyse' % MODULE)
        return _dry_run_done()
    return _run_chain(args, with_aux=False)


def cmd_all(args):
    if args.dry_run:
        plan = plan_payload(include_aux=True,
                            start_dir=args.start_dir,
                            authority_dir=args.baseline_dir,
                            seeds=_seed_list(args))
        actions = [
            'start  -- verify the 20H G3 best_valid common start',
            'convert -- Stage-0 OFF conversion + OFF feasibility gate (effect A)',
            'arm-on / arm-off x %d seeds (PRIMARY: counted d56=%d, checks=%d, '
            'wall safety %.0f s)'
            % (len(_seed_list(args)), PRIMARY['counted_d56_budget'],
               PRIMARY['counted_checks_guard'],
               PRIMARY['wall_safety_net_seconds']),
            'arm-on / arm-off x %d seeds (AUXILIARY: %.0f s wall, no counted '
            'caps)' % (len(_seed_list(args)), AUX['wall_seconds']),
            'analyse -- independent audits, A/B/C accounting, pre-registered '
            'verdict for both budgets',
        ]
        switch = print_plan(plan, 'all --dry-run', actions)
        print('aux arm dirs      : on=%s  off=%s'
              % (','.join(_rel(run_dir('on', _tag(AUX, 'on', seed)))
                          for seed in _seed_list(args)),
                 ','.join(_rel(run_dir('off', _tag(AUX, 'off', seed)))
                          for seed in _seed_list(args))))
        print('multi-arc switch  : verified at %s:%s (default ON)'
              % (switch['layer2d_file'], switch['policy_definition_line']))
        return _dry_run_done()
    return _run_chain(args, with_aux=True)


# ===========================================================================
# CLI
# ===========================================================================
def _add_common(parser):
    parser.add_argument('--start-dir', default=None,
                        help='override the 20H common start dir '
                             '(default: the 20H G3 best_valid)')
    parser.add_argument('--baseline-dir', default=None,
                        help='override the identity/port/manual authority dir')
    parser.add_argument('--seeds', default=None,
                        help='comma-separated seeds (default: %s)'
                             % ','.join(str(s) for s in SEEDS))
    parser.add_argument('--skip-validator', action='store_true',
                        help='debug only: skip the independent validator')
    parser.add_argument('--dry-run', action='store_true',
                        help='print the resolved plan and exit; nothing is '
                             'executed or written')


def build_parser():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)

    p_start = sub.add_parser('start', help='verify the common 20H start and '
                                           'write START.json')
    _add_common(p_start)
    p_start.add_argument('--force', action='store_true')
    p_start.set_defaults(func=cmd_start)

    p_convert = sub.add_parser('convert', help='Stage-0 OFF conversion of the '
                                               'common start (effect A)')
    _add_common(p_convert)
    p_convert.add_argument('--force', action='store_true')
    p_convert.add_argument('--allow-unverified-start', action='store_true')
    p_convert.add_argument('--max-routes', type=int, default=0,
                           help='debug only: convert at most N target routes')
    p_convert.set_defaults(func=cmd_convert)

    for arm in ARMS:
        p_arm = sub.add_parser('arm-%s' % arm,
                               help='run one MULTI-ARC %s arm for one seed'
                                    % arm.upper())
        _add_common(p_arm)
        p_arm.add_argument('--seed', type=int, default=SEEDS[0])
        p_arm.add_argument('--tag', default=None)
        p_arm.add_argument('--kind', default='primary',
                           choices=['primary', 'auxiliary'])
        p_arm.set_defaults(func=lambda args, arm=arm: cmd_arm(args, arm))

    p_chain = sub.add_parser('chain', help='start -> convert -> primary arms '
                                           '-> analyse')
    _add_common(p_chain)
    p_chain.add_argument('--refresh-start', action='store_true')
    p_chain.add_argument('--refresh-convert', action='store_true')
    p_chain.add_argument('--force', action='store_true')
    p_chain.add_argument('--arm-timeout', type=float, default=9000.0)
    p_chain.add_argument('--convert-timeout', type=float, default=7200.0)
    p_chain.add_argument('--analyse-timeout', type=float, default=7200.0)
    p_chain.set_defaults(func=cmd_chain)

    p_all = sub.add_parser('all', help='chain + auxiliary 900 s arms + analyse')
    _add_common(p_all)
    p_all.add_argument('--refresh-start', action='store_true')
    p_all.add_argument('--refresh-convert', action='store_true')
    p_all.add_argument('--force', action='store_true')
    p_all.add_argument('--arm-timeout', type=float, default=9000.0)
    p_all.add_argument('--convert-timeout', type=float, default=7200.0)
    p_all.add_argument('--analyse-timeout', type=float, default=7200.0)
    p_all.set_defaults(func=cmd_all)

    p_analyse = sub.add_parser('analyse', help='independent audits + A/B/C '
                                               'accounting + verdict')
    _add_common(p_analyse)
    p_analyse.add_argument('--with-aux', action='store_true',
                           help='also analyse the auxiliary 900 s arms')
    p_analyse.set_defaults(func=cmd_analyse)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    # ``arm-*`` subcommands need the env var set before layer2d is imported;
    # cmd_arm() sets it before importing any pipeline module.  Nothing here
    # imports layer2d.
    return int(args.func(args))


if __name__ == '__main__':
    raise SystemExit(main())
