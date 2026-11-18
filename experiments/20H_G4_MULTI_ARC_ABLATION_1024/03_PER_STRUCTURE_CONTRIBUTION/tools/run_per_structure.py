# -*- coding: utf-8 -*-
"""Per-patent-structure contribution experiment (20H, 1024 channels).

Reference start: the frozen 20H best legal solution
``experiments/COLD_START_20_HEIGHT_1024/10_best_valid``
(1283 same-plane crossing events, 1221 crossing pairs, 1024/1024 legal).

Groups (each seeded independently from that same state, never inheriting
another group's optimisation result):

* ``full_on``       every combined-arc structure enabled (control)
* ``no_multi_arc``  every planar multi-arc body removed and rebuilt
* ``ablate_6a`` .. ``ablate_7c``  exactly one patent structure disabled

For every group the start state is first rebuilt geometrically so that it
contains **no** instance of the disabled structure(s) (for ``full_on`` the
reference state is used unchanged), then the frozen G4c-free engine runs with
the same seed / counted budget / validator.  Three pre-registered seeds:
20261104, 20261116, 20261130.

The reported quantities are kept strictly separate:

1. ``1283 -> crossings_after_reconstruction``  geometry substitution cost
2. ``reconstruction -> after G4``              search improvement
3. ``final(group) - final(full_on)``           ablation benefit of the structure

Usage is measured on the real final geometry with the independent classifier
(``patent_structures``), never inferred from candidate family names.

Usage::

    python .../run_per_structure.py prepare
    python .../run_per_structure.py runs
    python .../run_per_structure.py validate
    python .../run_per_structure.py collect
    python .../run_per_structure.py status
"""
from __future__ import annotations

import csv
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PY = str(ROOT / '.venv' / 'Scripts' / 'python.exe')
BASE = (ROOT / 'experiments' / 'COLD_START_20_HEIGHT_1024'
        / '10_best_valid')
EXP = ROOT / 'experiments' / '20H_G4_MULTI_ARC_ABLATION_1024' \
    / '03_PER_STRUCTURE_CONTRIBUTION'
STATES = EXP / '01_states'
RUNS = EXP / '02_runs'
TABLES = EXP / 'tables'
LOGS = EXP / 'logs'
TOOLS = EXP / 'tools'
AUTHORITY = (ROOT / 'experiments' / 'COLD_START_20_HEIGHT_1024' / '07_g123'
             / 'run_xyz_joint_1024_20h' / 'baseline_authoritative')
SEEDS = (20261104, 20261116, 20261130)
STRUCTURE_TYPES = ('6a', '6b', '6c', '6d', '7a', '7b', '7c')
COUNTED_D56 = 24000
COUNTED_CHECKS = 9000
WALL_SAFETY = 5400.0
MAX_PARALLEL = 6
DRIVER = 'four_side_1024.fanout1024.coldstart20.run_g4'
ENGINE = 'four_side_1024.fanout1024.xyzrouter.g4.run_g4_engine'
VALIDATE = 'four_side_1024.fanout1024.coldstart20.run_validate'

GROUPS = [
    dict(key='full_on', label='Full-ON', disable=[], all_multi_arc=False,
         env_multi_arc='1', reconstruct=False),
    dict(key='no_multi_arc', label='NoMultiArc', disable=[],
         all_multi_arc=True, env_multi_arc='0', reconstruct=True),
    dict(key='ablate_6a', label='Ablation-6a', disable=['6a'],
         all_multi_arc=False, env_multi_arc='1', reconstruct=True),
    dict(key='ablate_6b', label='Ablation-6b', disable=['6b'],
         all_multi_arc=False, env_multi_arc='1', reconstruct=True),
    dict(key='ablate_6c', label='Ablation-6c', disable=['6c'],
         all_multi_arc=False, env_multi_arc='1', reconstruct=True),
    dict(key='ablate_6d', label='Ablation-6d', disable=['6d'],
         all_multi_arc=False, env_multi_arc='1', reconstruct=True),
    dict(key='ablate_7a', label='Ablation-7a', disable=['7a'],
         all_multi_arc=False, env_multi_arc='1', reconstruct=True),
    dict(key='ablate_7b', label='Ablation-7b', disable=['7b'],
         all_multi_arc=False, env_multi_arc='1', reconstruct=True),
    dict(key='ablate_7c', label='Ablation-7c', disable=['7c'],
         all_multi_arc=False, env_multi_arc='1', reconstruct=True),
]


def log(message):
    line = '[%s] %s' % (time.strftime('%Y-%m-%dT%H:%M:%S'), message)
    print(line, flush=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    with (LOGS / 'run_per_structure.log').open('a', encoding='utf-8') as handle:
        handle.write(line + '\n')


def read_json(path, default=None):
    path = Path(path)
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except Exception:                                        # noqa: BLE001
        return default


def sha256_file(path):
    import hashlib
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def spawn(argv, env_extra, log_name):
    LOGS.mkdir(parents=True, exist_ok=True)
    handle = (LOGS / log_name).open('a', encoding='utf-8')
    handle.write('\n===== %s =====\n' % time.strftime('%Y-%m-%dT%H:%M:%S'))
    handle.flush()
    values = dict(os.environ)
    values.update(env_extra)
    values.setdefault('OMP_NUM_THREADS', '1')
    values.setdefault('OPENBLAS_NUM_THREADS', '1')
    values.setdefault('NUMEXPR_NUM_THREADS', '1')
    log('spawn %s -> %s' % (' '.join(argv), log_name))
    process = subprocess.Popen(argv, cwd=str(ROOT), env=values,
                               stdout=handle, stderr=subprocess.STDOUT)
    return process, handle


def wait_all(jobs):
    failures = []
    for name, process, handle in jobs:
        code = process.wait()
        handle.close()
        log('finish %s exit=%s' % (name, code))
        if code != 0:
            failures.append((name, code))
    return failures


def run_sync(argv, env_extra, log_name, timeout=None):
    handle = (LOGS / log_name).open('a', encoding='utf-8')
    handle.write('\n===== %s =====\n' % time.strftime('%Y-%m-%dT%H:%M:%S'))
    handle.flush()
    values = dict(os.environ)
    values.update(env_extra)
    log('run %s' % ' '.join(argv))
    completed = subprocess.run(argv, cwd=str(ROOT), env=values,
                               stdout=handle, stderr=subprocess.STDOUT,
                               timeout=timeout)
    handle.close()
    log('done exit=%s' % completed.returncode)
    return int(completed.returncode)


def state_dir(group):
    return STATES / group['key']


def run_dir(group, seed):
    return RUNS / group['key'] / ('seed_%d' % seed)


def _state_ready(group):
    path = state_dir(group)
    return ((path / 'routes_l3d.json').is_file()
            and (path / 'assignment_1024.csv').is_file())


def stage_prepare(force=False, only=None):
    jobs = []
    for group in GROUPS:
        if only and group['key'] not in only:
            continue
        path = state_dir(group)
        if _state_ready(group) and not force:
            log('state %s exists -- skip' % group['key'])
            continue
        path.mkdir(parents=True, exist_ok=True)
        if not group['reconstruct']:
            for name in ('routes_l3d.json', 'assignment_1024.csv',
                         'layer_planes.json', 'crossing_stats.json',
                         'SHA256.json', 'BEST_VALID.json', 'validation.json'):
                source = BASE / name
                if source.is_file():
                    import shutil
                    shutil.copy2(source, path / name)
            payload = dict(
                schema='g4_structure_state_v1', group=group['key'],
                label=group['label'], disable=group['disable'],
                all_multi_arc=group['all_multi_arc'],
                source=str(BASE), reconstruction=None,
                crossings=read_json(BASE / 'crossing_stats.json', {}) or {},
                routes_sha256=sha256_file(BASE / 'routes_l3d.json'),
            )
            (path / 'STATE.json').write_text(
                json.dumps(payload, indent=1, ensure_ascii=False) + '\n',
                encoding='utf-8')
            log('state %s copied from reference (no reconstruction)'
                % group['key'])
            continue
        argv = [PY, str(TOOLS / 'reconstruct.py'),
                '--start-dir', str(BASE), '--out-dir', str(path),
                '--label', group['label']]
        if group['all_multi_arc']:
            argv.append('--all-multi-arc')
        else:
            argv.extend(['--disable'] + list(group['disable']))
        env_extra = {
            'G4_ENABLE_MULTI_ARC': group['env_multi_arc'],
            'G4_DISABLED_STRUCTURES': ' '.join(group['disable']),
        }
        process, handle = spawn(argv, env_extra,
                                'reconstruct_%s.log' % group['key'])
        jobs.append((group['key'], process, handle))
    failures = wait_all(jobs)
    return failures


def _run_done(group, seed):
    out = run_dir(group, seed)
    return ((out / 'best_valid' / 'routes_l3d.json').is_file()
            and (out / 'summary_g4.json').is_file())


def _pending_runs(force=False, only=None, seeds=None):
    """(group, seed) pairs that still need a real run."""
    pending = []
    seeds = tuple(seeds or SEEDS)
    for group in GROUPS:
        if only and group['key'] not in only:
            continue
        for seed in seeds:
            if _run_done(group, seed) and not force:
                log('run %s %d exists -- skip' % (group['key'], seed))
                continue
            pending.append((group, seed))
    return pending


def _launch_run(group, seed):
    out = run_dir(group, seed)
    out.mkdir(parents=True, exist_ok=True)
    start = state_dir(group)
    start_sha = sha256_file(start / 'routes_l3d.json')
    start_stats = read_json(start / 'crossing_stats.json', {}) or {}
    start_crossings = int(start_stats.get('total')
                          or start_stats.get('crossings') or 0)
    env_extra = {
        'G4_ENABLE_MULTI_ARC': group['env_multi_arc'],
        'G4_DISABLED_STRUCTURES': ' '.join(group['disable']),
        'G4_STRUCTURE_STATS_PATH': str(out / 'structure_counters.json'),
        'COLDSTART20_START_SHA': start_sha,
        'COLDSTART20_START_CROSSINGS': str(start_crossings),
    }
    argv = [PY, '-m', DRIVER, '_run', '--module', ENGINE, '--',
            '--arm', 'G4c_free', '--seconds', str(WALL_SAFETY),
            '--seed', str(seed), '--start-dir', str(start),
            '--out-dir', str(out), '--tag',
            '%s_%d' % (group['key'], seed),
            '--counted-d56-budget', str(COUNTED_D56),
            '--counted-checks-guard', str(COUNTED_CHECKS)]
    process, handle = spawn(argv, env_extra,
                            'run_%s_%d.log' % (group['key'], seed))
    return ('%s_%d' % (group['key'], seed), process, handle)


def stage_runs(force=False, only=None, seeds=None):
    """Legacy helper: launch pending runs (caller must batch them)."""
    return [_launch_run(group, seed)
            for group, seed in _pending_runs(force, only, seeds)]


def _pending_validations(force=False, only=None):
    pending = []
    for group in GROUPS:
        if only and group['key'] not in only:
            continue
        for seed in SEEDS:
            out = run_dir(group, seed)
            best = out / 'best_valid'
            if not (best / 'routes_l3d.json').is_file():
                log('validate: missing run %s %d' % (group['key'], seed))
                continue
            target = out / 'validation_final'
            if (target / 'validation.json').is_file() and not force:
                try:
                    if json.loads((target / 'validation.json').read_text(
                            encoding='utf-8-sig')).get(
                                'validation_pass') is True:
                        continue
                except Exception:                            # noqa: BLE001
                    pass
            pending.append((group, seed))
    return pending


def _launch_validate(group, seed):
    out = run_dir(group, seed)
    best = out / 'best_valid'
    target = out / 'validation_final'
    argv = [PY, str(TOOLS / 'validate_state_xyz.py'),
            '--run-dir', str(best), '--out-dir', str(target),
            '--baseline-dir', str(AUTHORITY)]
    process, handle = spawn(argv, {}, 'validate_%s_%d.log'
                            % (group['key'], seed))
    return (('validate_%s_%d' % (group['key'], seed)), process, handle)


def stage_validate(force=False, only=None):
    """Legacy helper: launch pending validations (caller must batch)."""
    return [_launch_validate(group, seed)
            for group, seed in _pending_validations(force, only)]


def stage_collect():
    sys.path.insert(0, str(ROOT))
    from four_side_1024.fanout1024.coldstart20 import bootstrap as B
    B.install()
    from four_side_1024.fanout1024 import layer2d as L2
    from four_side_1024.fanout1024.coldstart20 import run_multiarc as MA

    classifier = L2._structure_classifier()
    if classifier is None:
        raise SystemExit('patent_structures.py is missing: cannot measure '
                         'per-structure usage')
    TABLES.mkdir(parents=True, exist_ok=True)
    usage = {}
    reference = _census_route_dir(BASE, MA, L2)
    payload = dict(schema='g4_per_structure_runs_v1', generated_at=time.strftime(
        '%Y-%m-%dT%H:%M:%S'), reference_start=str(BASE),
        reference=reference, groups={})
    for group in GROUPS:
        state = state_dir(group)
        state_census = _census_route_dir(state, MA, L2)
        recon = read_json(state / 'reconstruction_report.json')
        group_payload = dict(
            key=group['key'], label=group['label'],
            disable=group['disable'], all_multi_arc=group['all_multi_arc'],
            state=str(state), start_reconstruction=recon,
            state_census=state_census, seeds={})
        for seed in SEEDS:
            out = run_dir(group, seed)
            best = out / 'best_valid'
            # a killed/stale attempt may leave a copied start as best_valid;
            # only a completed run (summary_g4.json written at the end) counts
            if not (out / 'summary_g4.json').is_file() or not (
                    best / 'routes_l3d.json').is_file():
                group_payload['seeds'][str(seed)] = dict(missing=True)
                continue
            audit = MA.audit_state(best, label='%s_%d' % (group['key'], seed))
            census = _census_route_dir(best, MA, L2)
            summary = read_json(out / 'summary_g4.json', {}) or {}
            validation = read_json(out / 'validation_final' / 'validation.json',
                                   {}) or read_json(out / 'validation.json', {})
            counters = read_json(out / 'structure_counters.json', {}) or {}
            transaction = _transaction_attribution(out, census)
            group_payload['seeds'][str(seed)] = dict(
                missing=False, dir=str(out),
                crossings=audit['crossings'],
                crossing_pairs=audit['crossing_pairs'],
                routes_with_crossings=audit['routes_with_crossings'],
                max_route_crossings=audit['max_route_crossings'],
                p95_route_crossings=audit['p95_route_crossings'],
                total_length_mm=audit['total_length_mm'],
                flat_arcs=audit['flat_arcs'], flat_lines=audit['flat_lines'],
                multi_arc=audit['multi_arc'], census=census,
                summary=summary, validation=validation,
                counters=counters, transaction=transaction,
                routes_sha256=audit['routes_sha256'],
            )
        payload['groups'][group['key']] = group_payload
        log('collected %s' % group['key'])
    (TABLES / 'per_structure_runs.json').write_text(
        json.dumps(payload, indent=1, ensure_ascii=False) + '\n',
        encoding='utf-8')
    _write_core_tables(payload)
    return 0


def _census_route_dir(path, MA, L2):
    """Per-type instance / route / height census of one route state."""
    path = Path(path)
    routes_payload = json.loads((path / 'routes_l3d.json').read_text(
        encoding='utf-8'))
    routes = routes_payload['routes']
    classifier = L2._structure_classifier()
    counts = {key: dict(instances=0, routes=0, heights={}, route_ids=[])
              for key in L2.STRUCTURE_TYPES}
    multi_arc_routes = 0
    for route in routes:
        rid = int(route['route_id'])
        instances = classifier.classify_route(route)
        types = {str(item.get('type')) for item in instances}
        prims = []
        for part in route.get('parts') or ():
            prims.extend(part.get('primitives') or ())
        if L2.local_multi_arc_regions(prims):
            multi_arc_routes += 1
        for key in types:
            counts[key]['routes'] += 1
            if rid not in counts[key]['route_ids']:
                counts[key]['route_ids'].append(rid)
        # height distribution comes from the instance's own flat part, never
        # from the first flat part (which is the interface lead at z=0.025/0.525)
        for item in instances:
            key = str(item.get('type'))
            if key not in counts:
                continue
            counts[key]['instances'] += 1
            zkey = '%.6f' % float(item.get('z_mm') or 0.0)
            counts[key]['heights'][zkey] = counts[key]['heights'].get(zkey, 0) + 1
    return dict(routes=len(routes), multi_arc_routes=multi_arc_routes,
                types=counts)


def _transaction_attribution(out, census):
    """Attribute accepted G4 transaction deltas to the structures they touched.

    The delta is the transaction's true crossing change; a transaction that
    changes routes carrying several structures is reported once under each
    structure (``involving``) and once under the exclusive tag set, so gains are
    never added twice into a single "value of multi-arc" number.
    """
    stats = read_json(out / 'strategy_stats.json', {}) or {}
    history = (stats.get('extra') or {}).get('transaction_history') or []
    routes_types = {}
    for key, item in census['types'].items():
        for rid in item['route_ids']:
            routes_types.setdefault(int(rid), set()).add(key)
    attribution = {key: dict(transactions=0, involving_gain=0,
                             exclusive_gain=0, exclusive_transactions=0)
                   for key in ('6a', '6b', '6c', '6d', '7a', '7b', '7c')}
    for record in history:
        if not record.get('accepted', True):
            continue
        delta = int(record.get('delta') or 0)
        tags = set()
        for rid in record.get('routes') or ():
            tags |= routes_types.get(int(rid), set())
        for key in tags:
            attribution[key]['transactions'] += 1
            attribution[key]['involving_gain'] += delta
        if len(tags) == 1:
            key = next(iter(tags))
            attribution[key]['exclusive_transactions'] += 1
            attribution[key]['exclusive_gain'] += delta
    return attribution


def _stats(values):
    values = [float(v) for v in values if v is not None]
    if not values:
        return dict(n=0)
    return dict(n=len(values), mean=statistics.mean(values),
                std=(statistics.stdev(values) if len(values) > 1 else 0.0),
                min=min(values), max=max(values),
                median=statistics.median(values))


def _write_core_tables(payload):
    rows = []
    reference = payload['reference']
    full_on = payload['groups']['full_on']
    full_final = [s.get('crossings') for s in full_on['seeds'].values()
                  if not s.get('missing')]
    full_mean = statistics.mean(full_final) if full_final else None
    full_len = [s.get('total_length_mm') for s in full_on['seeds'].values()
                if not s.get('missing')]
    full_len_mean = statistics.mean(full_len) if full_len else None
    for group in GROUPS:
        item = payload['groups'][group['key']]
        finals = [s.get('crossings') for s in item['seeds'].values()
                  if not s.get('missing')]
        lengths = [s.get('total_length_mm') for s in item['seeds'].values()
                   if not s.get('missing')]
        recon = item.get('start_reconstruction') or {}
        # usage is measured on the Full-ON control's real final geometry
        usage_means = {}
        for key in STRUCTURE_TYPES:
            values = [s['census']['types'][key]['routes']
                      for s in full_on['seeds'].values()
                      if not s.get('missing')]
            usage_means[key] = (statistics.mean(values) if values else 0.0)
        if group['key'] == 'full_on':
            used_routes = sum(usage_means.values())
            accepted = ''
        elif group['key'] == 'no_multi_arc':
            used_routes = reference['multi_arc_routes']
            accepted = ''
        else:
            used_routes = usage_means.get(group['disable'][0], '')
            trans = []
            for seed_payload in item['seeds'].values():
                if seed_payload.get('missing'):
                    continue
                trans.append(seed_payload['transaction'][group['disable'][0]])
            accepted = sum(t['transactions'] for t in trans)
        rows.append(dict(
            key=group['key'], label=group['label'],
            used_routes=(used_routes if used_routes is not None
                         else reference['multi_arc_routes']),
            accepted_transactions=accepted,
            reconstruction_crossings=recon.get('crossings_after'),
            reconstruction_delta=recon.get('crossing_delta'),
            final_crossings_mean=(statistics.mean(finals) if finals else None),
            final_crossings_std=(statistics.stdev(finals)
                                 if len(finals) > 1 else 0.0),
            final_crossings=json.dumps(finals),
            benefit_vs_full=(statistics.mean(finals) - full_mean
                             if finals and full_mean is not None else None),
            length_mean=(statistics.mean(lengths) if lengths else None),
            length_delta=(statistics.mean(lengths) - full_len_mean
                          if lengths and full_len_mean is not None else None),
        ))
    fields = list(rows[0])
    with (TABLES / 'per_structure_core.csv').open(
            'w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    lines = ['# 七种专利组合圆弧构型的独立消融（20层，1024通道）', '',
             '参考起点：`10_best_valid`，1283 次同层交叉、1221 对交叉线路。', '',
             '| 组 | 使用线路数 | 最终接受事务 | 重构后交叉 | 重构代价 | '
             'G4后交叉(均值) | 标准差 | 相对 Full-ON | 长度变化(mm) |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for row in rows:
        def fmt(value, digits=1):
            return '' if value is None else ('%.*f' % (digits, value)
                                             if isinstance(value, float)
                                             else str(value))
        lines.append('| %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
            row['label'], fmt(row['used_routes']),
            fmt(row['accepted_transactions']),
            fmt(row['reconstruction_crossings']),
            fmt(row['reconstruction_delta']),
            fmt(row['final_crossings_mean']),
            fmt(row['final_crossings_std']),
            fmt(row['benefit_vs_full']),
            fmt(row['length_delta'])))
    (TABLES / 'per_structure_core.md').write_text(
        '\n'.join(lines) + '\n', encoding='utf-8')

    # -------- the requested seven-row core table -------------------------
    type_rows = []
    for key in STRUCTURE_TYPES:
        group = next(item for item in GROUPS
                     if item['disable'] == [key])
        item = payload['groups'][group['key']]
        finals = [s.get('crossings') for s in item['seeds'].values()
                  if not s.get('missing')]
        lengths = [s.get('total_length_mm') for s in item['seeds'].values()
                   if not s.get('missing')]
        recon = item.get('start_reconstruction') or {}
        transactions = 0
        exclusive_gain = 0
        involving_gain = 0
        # aggregate acceptance evidence over the whole 27-run experiment:
        # a structure can be accepted in its own ablation (as a substitute) or
        # in another group's search, so this is the honest total
        for other_group in GROUPS:
            for seed_payload in payload['groups'][
                    other_group['key']]['seeds'].values():
                if seed_payload.get('missing'):
                    continue
                stats = seed_payload['transaction'][key]
                transactions += int(stats['transactions'])
                exclusive_gain += int(stats['exclusive_gain'])
                involving_gain += int(stats['involving_gain'])
        built = 0
        valid = 0
        instrumented = 0
        for other_group in GROUPS:
            for seed_payload in payload['groups'][
                    other_group['key']]['seeds'].values():
                if seed_payload.get('missing'):
                    continue
                counters = seed_payload.get('counters') or {}
                rows = (counters.get('counters') or {}).get(key) or {}
                built += int(rows.get('bodies_built') or 0)
                valid += int(rows.get('d56_valid') or 0)
                if counters:
                    instrumented += 1
        values = [s['census']['types'][key]['routes']
                  for s in full_on['seeds'].values()
                  if not s.get('missing')]
        used_routes = statistics.mean(values) if values else 0.0
        type_rows.append(dict(
            structure=key,
            used_routes=used_routes,
            accepted_transactions=transactions,
            accepted_gain_involving=involving_gain,
            accepted_gain_exclusive=exclusive_gain,
            candidates_built=built,
            candidates_geometry_valid=valid,
            instrumented_runs=instrumented,
            final_crossings_mean=(statistics.mean(finals) if finals else None),
            final_crossings_std=(statistics.stdev(finals)
                                 if len(finals) > 1 else 0.0),
            final_crossings=json.dumps(finals),
            benefit_vs_full=(statistics.mean(finals) - full_mean
                             if finals and full_mean is not None else None),
            reconstruction_crossings=recon.get('crossings_after'),
            reconstruction_delta=recon.get('crossing_delta'),
            length_delta=(statistics.mean(lengths) - full_len_mean
                          if lengths and full_len_mean is not None else None),
            length_mean=(statistics.mean(lengths) if lengths else None),
            validator=json.dumps([s.get('validation', {}).get('validation_pass')
                                  for s in item['seeds'].values()
                                  if not s.get('missing')]),
        ))
    with (TABLES / 'per_structure_table.csv').open(
            'w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(type_rows[0]))
        writer.writeheader()
        writer.writerows(type_rows)
    lines = ['# 七种专利组合圆弧构型独立收益（20层，1024通道）', '',
             '参考起点：`10_best_valid`（1283 交叉，1221 对）；'
             'Full-ON 为该起点的同预算三随机种子对照。', '',
             '| 专利构型 | 使用线路数 | 最终接受次数 | 禁用后交叉数(均值) | '
             '独立收益Δ | 长度变化(mm) |', '|---|---:|---:|---:|---:|---:|']
    for row in type_rows:
        def fmt(value, digits=1):
            return '' if value is None else ('%.*f' % (digits, value)
                                             if isinstance(value, float)
                                             else str(value))
        lines.append('| 图%s | %s | %s | %s | %s | %s |' % (
            row['structure'], fmt(row['used_routes']),
            fmt(row['accepted_transactions']),
            fmt(row['final_crossings_mean']),
            fmt(row['benefit_vs_full']), fmt(row['length_delta'])))
    lines += ['', '## 候选生成 / 几何合法 / 接受事务（27 次消融运行汇总）', '',
              '说明：`bodies_built` 与 `d56_valid` 来自 `G4_STRUCTURE_STATS_PATH`'
              ' 每进程计数器；`full_on`/`no_multi_arc` 的 6 次运行在计数器补丁'
              '之前完成，`d56_valid` 记为 0（已在报告中注明），其余 21 次运行完整。',
              '',
              '| 构型 | bodies_built | d56_valid | 已插桩运行数 | 接受事务 | '
              'involving_gain | exclusive_gain |',
              '|---|---:|---:|---:|---:|---:|---:|']
    for row in type_rows:
        lines.append('| 图%s | %d | %d | %d | %d | %d | %d |' % (
            row['structure'], row['candidates_built'],
            row['candidates_geometry_valid'], row['instrumented_runs'],
            row['accepted_transactions'], row['accepted_gain_involving'],
            row['accepted_gain_exclusive']))
    (TABLES / 'per_structure_table.md').write_text(
        '\n'.join(lines) + '\n', encoding='utf-8')
    log('core tables written %s' % (TABLES / 'per_structure_table.md'))


def status():
    for group in GROUPS:
        state_ok = _state_ready(group)
        runs = []
        for seed in SEEDS:
            out = run_dir(group, seed)
            summary = read_json(out / 'summary_g4.json', {}) or {}
            runs.append(summary.get('final_crossings'))
        print('%-14s state=%-5s finals=%s' % (group['key'], state_ok, runs))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    command = argv[0] if argv else 'all'
    EXP.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    if command == 'status':
        status()
        return 0
    if command in ('prepare', 'all'):
        failures = stage_prepare(force='--force' in argv)
        if failures:
            log('prepare failures %s' % failures)
            return 1
    if command in ('runs', 'all'):
        only = None
        seeds = None
        if '--only' in argv:
            only = set(argv[argv.index('--only') + 1].split(','))
        if '--seeds' in argv:
            seeds = [int(value) for value in
                     argv[argv.index('--seeds') + 1].split(',')]
        pending = _pending_runs(force='--force' in argv, only=only,
                                seeds=seeds)
        failures = []
        while pending:
            batch, pending = pending[:MAX_PARALLEL], pending[MAX_PARALLEL:]
            log('runs: launching %d, %d queued' % (len(batch), len(pending)))
            jobs = [_launch_run(group, seed) for group, seed in batch]
            failures.extend(wait_all(jobs))
        if failures:
            log('run failures %s' % failures)
            return 1
    if command in ('validate', 'all'):
        pending = _pending_validations(force='--force' in argv)
        failures = []
        while pending:
            batch, pending = pending[:4], pending[4:]
            log('validate: launching %d, %d queued' % (len(batch), len(pending)))
            jobs = [_launch_validate(group, seed) for group, seed in batch]
            failures.extend(wait_all(jobs))
        if failures:
            log('validate failures %s' % failures)
            return 1
    if command in ('collect', 'all'):
        return stage_collect()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
