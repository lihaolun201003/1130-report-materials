# -*- coding: utf-8 -*-
"""End-to-end pipeline: manual fixed-U (L1-L6) + automatic (L7+) 640-channel 3D routing.

Usage
-----
::

    .\\.venv\\Scripts\\python.exe -m four_side_1024.manual_u640.run
    .\\.venv\\Scripts\\python.exe -m four_side_1024.manual_u640.run --output outputs/manual_u640

    # re-use an existing routes.json (verification/plots/export only)
    .\\.venv\\Scripts\\python.exe -m four_side_1024.manual_u640.run --reuse-routes

The run writes everything below ``outputs/manual_u640/`` (see CONTRACT.md §6).
It never widens a constraint: a route the assemblies reject stays failed and is
reported with its reason.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import traceback
from pathlib import Path

from . import config as C


# ---------------------------------------------------------------------------
# logging
# ---------------------------------------------------------------------------
class RunLog:
    """Console + immediately flushed file logger (so a long run is observable)."""

    def __init__(self, path=None):
        self.lines = []
        self.path = Path(path) if path is not None else None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text('', encoding='utf-8')
            self._handle = open(self.path, 'a', encoding='utf-8')

    def __call__(self, message):
        text = f'[{time.strftime("%H:%M:%S")}] {message}'
        self.lines.append(text)
        print(text, flush=True)
        if self.path is not None:
            self._handle.write(text + '\n')
            self._handle.flush()

    def flush(self):
        if self.path is not None:
            self._handle.flush()


def _write_json(path, payload, indent=1):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=indent,
                               default=_json_default) + '\n', encoding='utf-8')
    return path


def _json_default(value):
    if isinstance(value, (set, tuple)):
        return list(value)
    if hasattr(value, 'tolist'):
        return value.tolist()
    return str(value)


def _json_safe(value):
    """Recursively replace NaN/Inf by None so the JSON stays strict."""
    import math

    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


# ---------------------------------------------------------------------------
# pipeline steps
# ---------------------------------------------------------------------------
def _prepare_outputs(data, out_dir, log):
    inputs_dir = out_dir / 'inputs'
    inputs_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(data.path, inputs_dir / 'input.csv')
    _write_json(inputs_dir / 'input_validation.json', data.validation)
    _write_json(inputs_dir / 'groups.json', data.groups_json())
    log(f'[run] input written: {inputs_dir / "input.csv"} '
        f'({len(data)} records, validation passed={data.validation["passed"]})')


def _route_manual(data, stack, log):
    from . import u_routes
    log('[run] === manual fixed-U routing (L1-L6, 284 records) ===')
    started = time.perf_counter()
    routes, failures, stats = u_routes.build_manual_u_routes(data, stack, log=log)
    log(f'[run] manual routing done in {time.perf_counter() - started:.1f}s: '
        f'routed={len(routes)} failed={len(failures)}')
    return routes, failures, stats


def _route_auto(data, stack, log, obstacle_routes=None):
    from . import auto_routes
    log('[run] === automatic routing (L7+, 356 records) ===')
    if obstacle_routes:
        log(f'[run] automatic routing is obstacle-aware: {len(obstacle_routes)} '
            f'manual L1-L6 routes are pre-loaded into its 3D world')
    started = time.perf_counter()
    try:
        routes, failures, stats = auto_routes.build_auto_routes(
            data, stack, log=log, obstacle_routes=obstacle_routes)
    except TypeError:
        # older signature without obstacle avoidance (kept for compatibility)
        log('[run] WARNING: auto_routes.build_auto_routes has no '
            'obstacle_routes parameter; running without 3D obstacle avoidance')
        routes, failures, stats = auto_routes.build_auto_routes(data, stack, log=log)
    log(f'[run] automatic routing done in {time.perf_counter() - started:.1f}s: '
        f'routed={len(routes)} failed={len(failures)}')
    return routes, failures, stats


def _verify(routes, data, stack, out_dir, log):
    try:
        from . import verify
    except Exception as error:  # pragma: no cover - module is optional during dev
        log(f'[run] independent verification unavailable: {error}')
        return None
    log('[run] === independent geometric verification ===')
    started = time.perf_counter()
    result = verify.verify_all(routes, data, stack, log=log)
    log(f'[run] verification done in {time.perf_counter() - started:.1f}s')
    _write_json(out_dir / 'validation.json', _json_safe(result))
    return result


def _render(routes, stack, data, out_dir, log):
    try:
        from . import plots
    except Exception as error:  # pragma: no cover
        log(f'[run] plotting unavailable: {error}')
        return None
    log('[run] === rendering 2D per-layer + 3D figures ===')
    started = time.perf_counter()
    result = plots.render_all(routes, stack, data, out_dir / 'plots', log=log)
    log(f'[run] plotting done in {time.perf_counter() - started:.1f}s')
    return result


def _export(routes, failures, data, stack, out_dir, verification, assembled, log):
    try:
        from . import export
    except Exception as error:  # pragma: no cover
        log(f'[run] export module unavailable: {error}')
        return None
    log('[run] === exporting route table / statistics ===')
    started = time.perf_counter()
    result = export.export_all(routes, data, stack, out_dir,
                               verification=verification, assembled=assembled,
                               failures=failures, log=log)
    log(f'[run] export done in {time.perf_counter() - started:.1f}s')
    return result


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def run(args, log=None):
    from four_side_1024.r15 import profile_r15
    profile_r15.apply()          # R = 15 mm before any routing import

    from . import inputs
    from . import stack as stack_module
    from . import assemble as assemble_module

    out_dir = Path(args.output).resolve() if args.output else C.OUTPUT_ROOT
    out_dir.mkdir(parents=True, exist_ok=True)
    log = RunLog(out_dir / 'log.txt') if log is None else log
    started = time.perf_counter()
    log(f'[run] output directory: {out_dir}')
    log(f'[run] process profile: R={C.RADIUS_MM} mm, width={C.WIDTH_MM} mm, '
        f'edge gap={C.EDGE_GAP_MM} mm, clearance={C.CLEARANCE_MM} mm, '
        f'layer pitch={C.LAYER_PITCH_MM} mm')

    data = inputs.load_inputs(args.input)
    _prepare_outputs(data, out_dir, log)

    stack_max = int(args.max_layer or C.MAX_LOGICAL_LAYERS)
    stack = stack_module.LayerStack(stack_max)
    log(f'[run] layer stack: L1 interface rows z1={C.Z1_MM} / z2={C.Z2_MM}; '
        f'routing layers L2..L{stack_max} at '
        f'{C.BASE_ROUTING_Z_MM}..{C.layer_z(stack_max)} mm')

    if args.reuse_routes:
        routes_path = out_dir / 'routes.json'
        if not routes_path.exists():
            raise FileNotFoundError(f'--reuse-routes needs {routes_path}')
        payload = json.loads(routes_path.read_text(encoding='utf-8'))
        routes = payload['routes'] if isinstance(payload, dict) else payload
        failures = [route for route in routes if route.get('status') == 'failed']
        routes = [route for route in routes if route.get('status') != 'failed']
        assembled = None
        log(f'[run] reusing {routes_path}: routed={len(routes)} '
            f'failed={len(failures)}')
    else:
        manual = _route_manual(data, stack, log)
        auto = _route_auto(data, stack, log, obstacle_routes=manual[0])
        log('[run] === assembling 640 records into the true-3D world ===')
        assembled = assemble_module.assemble(data, stack, manual, auto, log=log)
        routes = assembled['routes']
        failures = assembled['failures']
        _write_json(out_dir / 'assemble.json', _json_safe(dict(
            world_violations=assembled['world_violations'],
            world_accepted=assembled['world_accepted'],
            world_elapsed_s=assembled['world_elapsed_s'],
            plane_crossings=assembled['plane_crossings'],
            crossing_events_total=assembled['crossing_events_total'],
            used_logical_layers=assembled['used_logical_layers'],
            used_physical_planes=assembled['used_physical_planes'],
            logical_layer_count=assembled['logical_layer_count'],
            physical_plane_count=assembled['physical_plane_count'],
            per_layer=assembled['per_layer'],
            loss=assembled['loss'],
            router_stats=assembled['router_stats'],
            elapsed_s=assembled['elapsed_s'],
        )))

    all_records = list(routes) + list(failures)
    verification = None
    if not args.skip_verify:
        verification = _verify(all_records, data, stack, out_dir, log)
    if not args.skip_plots:
        _render(all_records, stack, data, out_dir, log)
    export_result = _export(routes, failures, data, stack, out_dir, verification,
                            assembled, log)

    manifest = dict(
        schema='four_side_1024_manual_u640_run_manifest_v1',
        started_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
        elapsed_s=round(time.perf_counter() - started, 2),
        command=' '.join(sys.argv),
        args=vars(args),
        input=dict(path=data.path, sha256=data.sha256,
                   validation_passed=data.validation['passed'],
                   failed_checks=data.validation['failed_checks']),
        process=C.process_record(),
        layer_stack=stack.payload(stack.max_layer),
        counts=dict(
            records=len(all_records),
            routed=len(routes),
            failed=len(failures),
            manual_routed=sum(1 for route in routes
                              if route.get('assignment') == 'manual_fixed_u'),
            manual_failed=sum(1 for route in failures
                              if route.get('assignment') == 'manual_fixed_u'),
            auto_routed=sum(1 for route in routes
                            if route.get('assignment') == 'existing_algorithm'),
            auto_failed=sum(1 for route in failures
                            if route.get('assignment') == 'existing_algorithm'),
        ),
        used_logical_layers=(assembled['used_logical_layers']
                            if assembled else sorted({route['logical_layer']
                                                     for route in routes
                                                     if route.get('logical_layer')})),
        used_physical_planes=(assembled['used_physical_planes']
                              if assembled else sorted({part['z_mm']
                                                        for route in routes
                                                        for part in route.get('parts') or []
                                                        if part['kind'] == 'flat'})),
        world_violations=(len(assembled['world_violations']) if assembled else None),
        verification_summary=(None if verification is None else
                              verification.get('summary')),
        export=export_result,
    )
    _write_json(out_dir / 'run_manifest.json', _json_safe(manifest))

    log('')
    log('=' * 78)
    log(f'RESULT: {manifest["counts"]["routed"]}/640 routed, '
        f'{manifest["counts"]["failed"]} failed')
    log(f'  manual L1-L6 : {manifest["counts"]["manual_routed"]}/284 '
        f'(failed {manifest["counts"]["manual_failed"]})')
    log(f'  automatic    : {manifest["counts"]["auto_routed"]}/356 '
        f'(failed {manifest["counts"]["auto_failed"]})')
    log(f'  logical layers used : {manifest["used_logical_layers"]}')
    log(f'  physical planes     : {manifest["used_physical_planes"]}')
    log(f'  world violations    : {manifest["world_violations"]}')
    log(f'  output directory    : {out_dir}')
    log('=' * 78)
    log.flush()
    return manifest


def build_parser():
    parser = argparse.ArgumentParser(
        description='640-channel manual fixed-U + automatic 3D routing pipeline')
    parser.add_argument('--input', default=None,
                        help='manual grouping CSV (default: project input)')
    parser.add_argument('--output', default=None,
                        help='output directory (default: outputs/manual_u640)')
    parser.add_argument('--max-layer', type=int, default=C.MAX_LOGICAL_LAYERS,
                        help='highest logical routing layer of the stack')
    parser.add_argument('--reuse-routes', action='store_true',
                        help='skip routing; reuse <output>/routes.json')
    parser.add_argument('--skip-verify', action='store_true')
    parser.add_argument('--skip-plots', action='store_true')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        run(args)
    except Exception:
        traceback.print_exc()
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
