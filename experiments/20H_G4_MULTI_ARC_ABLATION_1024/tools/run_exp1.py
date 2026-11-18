# -*- coding: utf-8 -*-
"""Experiment 1 driver -- 20H G4 planar multi-arc ON/OFF ablation (original design).

Replicates ``experiments/G4_MULTI_ARC_ABLATION_1024`` (21H) on the 20-height,
1024-channel model:

    G3 start (1395 crossings)
      -> audit
      -> Stage-0 OFF conversion of every planar multi-arc body
      -> ON  : G4c_free 1800 s + G4d 1200 s (multi-arc ON,  start = G3)
      -> OFF : G4c_free 1800 s + G4d 1200 s (multi-arc OFF, start = converted)
      -> independent validator on both finals
      -> independent audit, per-layer tables, decomposition, report

The only changed algorithm variable is ``G4_ENABLE_MULTI_ARC``.
Everything (20 planes, R15, D56, 3-D clearance, 1024 connections, seeds,
validator) is unchanged.

Usage (from the repository root)::

    .venv\\Scripts\\python.exe experiments\\20H_G4_MULTI_ARC_ABLATION_1024\\tools\\run_exp1.py all
    .venv\\Scripts\\python.exe experiments\\20H_G4_MULTI_ARC_ABLATION_1024\\tools\\run_exp1.py status
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PY = str(ROOT / '.venv' / 'Scripts' / 'python.exe')
EXP = ROOT / 'experiments' / '20H_G4_MULTI_ARC_ABLATION_1024'
G3 = (ROOT / 'experiments' / 'COLD_START_20_HEIGHT_1024' / '07_g123'
      / 'run_xyz_joint_1024_20h' / 'best_valid')
COMMON = EXP / '01_common_start'
LOGS = EXP / 'logs'
SEED = 20261104
SECONDS_C_FREE = 1800.0
SECONDS_G4D = 1200.0
ON = EXP / '02_experiment1' / 'on'
OFF = EXP / '02_experiment1' / 'off'
TABLES = EXP / '02_experiment1' / 'tables'

DRIVER = 'four_side_1024.fanout1024.coldstart20.run_g4'
ENGINE = 'four_side_1024.fanout1024.xyzrouter.g4.run_g4_engine'
CONVERT = 'four_side_1024.fanout1024.coldstart20.convert_multiarc20'
VALIDATE = 'four_side_1024.fanout1024.coldstart20.run_validate'


def log(message):
    line = '[%s] %s' % (time.strftime('%Y-%m-%dT%H:%M:%S'), message)
    print(line, flush=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    with (LOGS / 'run_exp1.log').open('a', encoding='utf-8') as handle:
        handle.write(line + '\n')


def run(argv, env_extra=None, log_name=None, timeout=None):
    env = dict(os.environ)
    env.update(env_extra or {})
    log('RUN %s' % ' '.join(argv))
    started = time.time()
    if log_name:
        LOGS.mkdir(parents=True, exist_ok=True)
        with (LOGS / log_name).open('a', encoding='utf-8') as handle:
            handle.write('\n===== %s =====\n' % time.strftime('%Y-%m-%dT%H:%M:%S'))
            handle.flush()
            completed = subprocess.run(argv, cwd=str(ROOT), env=env,
                                       stdout=handle,
                                       stderr=subprocess.STDOUT,
                                       timeout=timeout)
    else:
        completed = subprocess.run(argv, cwd=str(ROOT), env=env,
                                   timeout=timeout)
    log('DONE exit=%s (%.1fs)' % (completed.returncode,
                                  time.time() - started))
    return int(completed.returncode)


def _arm_argv(arm, seconds, start_dir, out_dir):
    return [PY, '-m', DRIVER, '_run', '--module', ENGINE, '--',
            '--arm', arm, '--seconds', str(float(seconds)),
            '--seed', str(SEED), '--start-dir', str(start_dir),
            '--out-dir', str(out_dir)]


def _best(directory):
    best = Path(directory) / 'best_valid'
    return best if (best / 'routes_l3d.json').is_file() else Path(directory)


def _arm_done(directory):
    path = Path(directory) / 'summary_g4.json'
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding='utf-8-sig'))
    except Exception:                                        # noqa: BLE001
        return False
    return bool(payload.get('final_crossings') is not None
                and _best(directory).joinpath('routes_l3d.json').is_file())


def stage_audit():
    target = EXP / '00_audit'
    target.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))
    from four_side_1024.fanout1024.coldstart20 import bootstrap as B
    B.install()
    from four_side_1024.fanout1024 import layer2d as L2
    from four_side_1024.fanout1024.coldstart20 import run_multiarc as MA
    audit = MA.audit_state(G3, label='g3_start')
    routes = json.loads((G3 / 'routes_l3d.json').read_text(
        encoding='utf-8'))['routes']
    types = {key: dict(instances=0, routes=0) for key in L2.STRUCTURE_TYPES}
    for route in routes:
        for item in L2._structure_classifier().classify_route(route):
            key = str(item.get('type'))
            if key in types:
                types[key]['instances'] += 1
        for key in L2.structure_types_of_route(route):
            if key in types:
                types[key]['routes'] += 1
    payload = dict(
        schema='g4_multi_arc_ablation_audit_v1',
        g3_start=dict(path=str(G3.relative_to(ROOT)),
                      routes_sha256=_sha256(G3 / 'routes_l3d.json'),
                      assignment_sha256=_sha256(
                          G3 / 'assignment_1024.csv'),
                      validation=_read_json(G3 / 'validation.json')),
        g3_geometry=audit,
        g3_patent_structures=types,
        classifier=str(getattr(L2._structure_classifier(), '__file__', None)),
    )
    (target / 'g3_start.json').write_text(
        json.dumps(payload, indent=1, ensure_ascii=False) + '\n',
        encoding='utf-8')
    log('audit written %s (crossings=%s, multi_arc_routes=%s)'
        % (target / 'g3_start.json', audit.get('crossings'),
           (audit.get('multi_arc') or {}).get('routes_with_multi_arc')))


def _sha256(path):
    import hashlib
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def stage_convert(force=False):
    report = COMMON / 'conversion_report.json'
    if report.is_file() and not force:
        payload = json.loads(report.read_text(encoding='utf-8-sig'))
        if payload.get('feasible') and int(payload.get('residual') or 0) == 0:
            log('conversion already feasible: crossings=%s residual=0'
                % payload.get('crossings_after'))
            return 0
    COMMON.mkdir(parents=True, exist_ok=True)
    argv = [PY, '-m', CONVERT, '--start-dir', str(G3),
            '--out-dir', str(COMMON),
            '--log', str(LOGS / 'convert.log')]
    code = run(argv, env_extra={'G4_ENABLE_MULTI_ARC': '0'},
               log_name='convert.stdout.log')
    if code != 0:
        log('conversion FAILED exit=%s' % code)
        return code
    payload = json.loads(report.read_text(encoding='utf-8-sig'))
    log('conversion feasible=%s crossings=%s residual=%s escalated=%s'
        % (payload.get('feasible'), payload.get('crossings_after'),
           payload.get('residual'), payload.get('escalated_route_ids')))
    return 0 if payload.get('feasible') else 4


def stage_on():
    first = ON / '01_c_free'
    if not _arm_done(first):
        code = run(_arm_argv('G4c_free', SECONDS_C_FREE, G3, first),
                   env_extra={'G4_ENABLE_MULTI_ARC': '1'},
                   log_name='on_c_free.log')
        if code != 0:
            return code
    else:
        log('ON c-free already done: %s' % first)
    second = ON / '02_g4d'
    if not _arm_done(second):
        code = run(_arm_argv('G4d', SECONDS_G4D, _best(first), second),
                   env_extra={'G4_ENABLE_MULTI_ARC': '1'},
                   log_name='on_g4d.log')
        if code != 0:
            return code
    else:
        log('ON G4d already done: %s' % second)
    return 0


def stage_off():
    first = OFF / '01_c_free'
    if not _arm_done(first):
        code = run(_arm_argv('G4c_free', SECONDS_C_FREE, COMMON, first),
                   env_extra={'G4_ENABLE_MULTI_ARC': '0'},
                   log_name='off_c_free.log')
        if code != 0:
            return code
    else:
        log('OFF c-free already done: %s' % first)
    second = OFF / '02_g4d'
    if not _arm_done(second):
        code = run(_arm_argv('G4d', SECONDS_G4D, _best(first), second),
                   env_extra={'G4_ENABLE_MULTI_ARC': '0'},
                   log_name='off_g4d.log')
        if code != 0:
            return code
    else:
        log('OFF G4d already done: %s' % second)
    return 0


def stage_validate():
    worker = (EXP / '03_PER_STRUCTURE_CONTRIBUTION' / 'tools'
              / 'validate_state_xyz.py')
    authority = (ROOT / 'experiments' / 'COLD_START_20_HEIGHT_1024'
                 / '07_g123' / 'run_xyz_joint_1024_20h'
                 / 'baseline_authoritative')
    for name, arm_dir in (('on', ON / '02_g4d'), ('off', OFF / '02_g4d')):
        out = arm_dir / 'validation_final'
        if (out / 'validation.json').is_file() and (
                json.loads((out / 'validation.json').read_text(
                    encoding='utf-8-sig')).get('validation_pass') is True):
            log('%s validation already PASS' % name)
            continue
        code = run([PY, str(worker), '--run-dir', str(_best(arm_dir)),
                    '--out-dir', str(out),
                    '--baseline-dir', str(authority)],
                   log_name='validate_%s.log' % name)
        if code != 0:
            return code
    return 0


def stage_collect():
    sys.path.insert(0, str(ROOT))
    from four_side_1024.fanout1024.coldstart20 import bootstrap as B
    B.install()
    from four_side_1024.fanout1024.coldstart20 import run_multiarc as MA
    targets = {
        'g3_start': G3,
        'common_start_off': COMMON,
        'on_c_free': ON / '01_c_free',
        'on_g4d': ON / '02_g4d',
        'off_c_free': OFF / '01_c_free',
        'off_g4d': OFF / '02_g4d',
    }
    payload = {}
    for key, path in targets.items():
        run_dir = _best(path)
        log('audit %s -> %s' % (key, run_dir))
        payload[key] = MA.audit_state(run_dir, label=key)
        payload[key]['arm_dir'] = str(path.relative_to(ROOT))
        payload[key]['summary'] = _read_json(Path(path) / 'summary_g4.json')
        payload[key]['validation_final'] = _read_json(
            Path(path) / 'validation_final' / 'validation.json') or _read_json(
            run_dir / 'validation.json') or _read_json(
            Path(path) / 'validation.json')
    TABLES.mkdir(parents=True, exist_ok=True)
    (TABLES / 'exp1_metrics.json').write_text(
        json.dumps(payload, indent=1, ensure_ascii=False) + '\n',
        encoding='utf-8')
    _write_tables(payload)
    log('metrics written %s' % (TABLES / 'exp1_metrics.json'))
    return 0


def _read_json(path):
    path = Path(path)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except Exception:                                        # noqa: BLE001
        return None


def _write_tables(payload):
    import csv
    rows = []
    for key in ('g3_start', 'common_start_off', 'on_c_free', 'on_g4d',
                'off_c_free', 'off_g4d'):
        item = payload[key]
        summary = item.get('summary') or {}
        census = item.get('multi_arc') or {}
        rows.append(dict(
            state=key,
            crossings=item.get('crossings'),
            crossing_pairs=item.get('crossing_pairs'),
            routes_with_crossings=item.get('routes_with_crossings'),
            max_route_crossings=item.get('max_route_crossings'),
            p95_route_crossings=item.get('p95_route_crossings'),
            total_length_mm=item.get('total_length_mm'),
            flat_arcs=item.get('flat_arcs'),
            flat_lines=item.get('flat_lines'),
            transition_parts=item.get('transition_parts'),
            mid_transitions=item.get('mid_transitions'),
            multi_arc_routes=census.get('routes_with_multi_arc'),
            multi_arc_regions=census.get('total_regions'),
            seconds=summary.get('seconds'),
            d56_candidate_evals=(summary.get('ledger') or {}).get(
                'd56_candidate_evals'),
            route_3d_checks=(summary.get('ledger') or {}).get(
                'route_3d_checks'),
            routes_sha256=item.get('routes_sha256')))
    path = TABLES / 'exp1_states.csv'
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    # per-height crossing / pair table
    heights = set()
    for item in payload.values():
        heights.update((item.get('plane_counts') or {}).keys())
    heights = sorted(heights, key=float)
    per_height = []
    for z in heights:
        row = dict(z_mm=z)
        for key in ('g3_start', 'common_start_off', 'on_g4d', 'off_g4d'):
            counts = (payload[key].get('plane_counts') or {}).get(z) or {}
            row[key + '_events'] = counts.get('events', 0)
            row[key + '_pairs'] = counts.get('pairs', 0)
            row[key + '_routes'] = counts.get('routes', 0)
        per_height.append(row)
    path = TABLES / 'exp1_per_height.csv'
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(per_height[0]))
        writer.writeheader()
        writer.writerows(per_height)
    # effect decomposition
    g3 = int(payload['g3_start']['crossings'])
    common = int(payload['common_start_off']['crossings'])
    on = int(payload['on_g4d']['crossings'])
    off = int(payload['off_g4d']['crossings'])
    on_free = int(payload['on_c_free']['crossings'])
    off_free = int(payload['off_c_free']['crossings'])
    decomposition = dict(
        g3_start=g3,
        conversion_delta=common - g3,
        common_start_off=common,
        on_g4c_free=on_free,
        on_g4d=on,
        on_search_gain=on - g3,
        off_g4c_free=off_free,
        off_g4d=off,
        off_search_gain=off - common,
        final_difference=off - on,
        on_total_length_mm=payload['on_g4d'].get('total_length_mm'),
        off_total_length_mm=payload['off_g4d'].get('total_length_mm'),
        on_multi_arc_regions=payload['on_g4d'].get('multi_arc_regions'),
        off_multi_arc_regions=payload['off_g4d'].get('multi_arc_regions'),
        on_validator=payload['on_g4d'].get('validation_final'),
        off_validator=payload['off_g4d'].get('validation_final'),
    )
    (TABLES / 'exp1_decomposition.json').write_text(
        json.dumps(decomposition, indent=1, ensure_ascii=False) + '\n',
        encoding='utf-8')
    log('tables written %s' % TABLES)


def status():
    for name, path in (('convert', COMMON),
                       ('on_c_free', ON / '01_c_free'),
                       ('on_g4d', ON / '02_g4d'),
                       ('off_c_free', OFF / '01_c_free'),
                       ('off_g4d', OFF / '02_g4d')):
        print('%-12s done=%s %s' % (name, _arm_done(path)
                                    if 'c_free' in name or 'g4d' in name
                                    else (path / 'conversion_report.json').is_file(),
                                    path))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    command = argv[0] if argv else 'all'
    LOGS.mkdir(parents=True, exist_ok=True)
    EXP.mkdir(parents=True, exist_ok=True)
    if command == 'status':
        status()
        return 0
    if command in ('audit', 'all'):
        stage_audit()
    if command in ('convert', 'all'):
        code = stage_convert(force='--force' in argv)
        if code:
            return code
    if command in ('on', 'all'):
        code = stage_on()
        if code:
            return code
    if command in ('off', 'all'):
        code = stage_off()
        if code:
            return code
    if command in ('validate', 'all'):
        code = stage_validate()
        if code:
            return code
    if command in ('collect', 'all'):
        code = stage_collect()
        if code:
            return code
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
