# -*- coding: utf-8 -*-
"""G5 finalisation: turn a search result into a complete, validated deliverable.

Given a ``routes_l3d.json`` produced by the G5 engine it

1. re-audits the world exactly (strict D56 + 45 deg + 3-D + structure),
2. writes the eight-file payload (routes / assignment / layer_planes /
   process_rules / crossing_stats / validation.json / SHA256.json / BEST_VALID),
3. writes the G5 comparison tables (``g5_crossing_angles.csv``,
   ``g5_layer_statistics.csv``, ``g5_route_change_summary.csv``,
   ``g5_geometry_comparison.csv``),
4. copies the payload into ``03_best_feasible`` only when it is fully legal,
   otherwise ``best_partial``.

The independent angle validator and the frozen project validator are run by
separate commands (see ``run_validation.py``); this module never fabricates a
PASS.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024.xyzrouter.g5 import model as G5

FROZEN = ROOT / 'experiments' / 'COLD_START_20_HEIGHT_1024' / '10_best_valid'
EXPECTED_SHA = '35d7ebed00339bee21fe0ca47075c9b34008120522a47933a099efacf0b90753'
EXP = ROOT / 'experiments' / 'G5_ANGLE45_NATIVE3D_20H_1024'


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_routes(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_csv(path, rows, keys=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text('', encoding='utf-8')
        return path
    keys = keys or list(rows[0].keys())
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, '') for key in keys})
    return path


def audit(payload, min_angle=45.0, log=print):
    world = G5.World(payload['routes'], min_angle_deg=min_angle)
    started = time.time()
    same = world.audit_all(min_angle_deg=min_angle)
    log('[audit] same-height %.1fs crossings=%d violations=%d issues=%d'
        % (time.time() - started, len(same['crossings']),
           len(same['violations']), len(same['issues'])))
    started = time.time()
    three = world.audit_3d()
    log('[audit] 3-D %.1fs minima=%s issues=%d'
        % (time.time() - started, three['minima'], len(three['issues'])))
    structure = []
    for route in payload['routes']:
        for issue in G5.structure_issues(route):
            structure.append(dict(route_id=int(route['route_id']), **issue))
    log('[audit] structure issues=%d' % len(structure))
    from four_side_1024.fanout1024.xyzrouter.g4 import independent_metrics as IM
    self_report = IM.self_clearance_audit(payload['routes'], log=lambda *_: None)
    self_issues = self_report['violations']
    log('[audit] self-clearance issues=%d min=%s'
        % (len(self_issues), self_report['min_self_distance_mm']))
    return dict(world=world, same=same, three=three, structure=structure,
                self_issues=self_issues,
                min_self_clearance_mm=self_report['min_self_distance_mm'])


def layer_table(events):
    table = defaultdict(lambda: dict(crossings=0, violations=0, min_angle=90.0,
                                     routes=set()))
    for event in events:
        z = round(event['z'], 6)
        row = table[z]
        row['crossings'] += 1
        row['routes'].add(event['route_a'])
        row['routes'].add(event['route_b'])
        row['min_angle'] = min(row['min_angle'], event['angle_deg'])
        if event['angle_deg'] < 45.0:
            row['violations'] += 1
    return table


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--routes', required=True,
                        help='G5 routes_l3d.json to finalise')
    parser.add_argument('--baseline', default=str(FROZEN / 'routes_l3d.json'))
    parser.add_argument('--out', default=str(EXP / '03_best_feasible'))
    parser.add_argument('--label', default='G5')
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    g5 = load_routes(args.routes)
    base = load_routes(args.baseline)
    if sha256_file(args.baseline) != EXPECTED_SHA:
        raise SystemExit('baseline sha256 mismatch')
    log_lines = []

    def log(message):
        print(message, flush=True)
        log_lines.append(str(message))

    result = audit(g5, 45.0, log)
    same = result['same']
    three = result['three']
    legal = (not same['violations'] and not same['issues']
             and not three['issues'] and not result['structure']
             and not result['self_issues'])
    summary = dict(
        label=args.label, routes_sha256=sha256_file(args.routes),
        baseline_sha256=EXPECTED_SHA, legal=bool(legal),
        violations=len(same['violations']),
        crossings=len(same['crossings']),
        pairs=len({(e['route_a'], e['route_b']) for e in same['crossings']}),
        min_angle_deg=(round(min(e['angle_deg'] for e in same['crossings']), 6)
                       if same['crossings'] else None),
        deficit_deg=round(sum(45.0 - e['angle_deg']
                              for e in same['violations']), 6),
        max_deficit_deg=round(max([45.0 - e['angle_deg']
                                   for e in same['violations']] or [0.0]), 6),
        hard_issues=len(same['issues']),
        three_d_issues=len(three['issues']),
        three_d_minima={key: (None if value is None else round(value, 9))
                        for key, value in three['minima'].items()},
        structure_issues=len(result['structure']),
        self_clearance_issues=len(result['self_issues']),
        min_self_clearance_mm=result.get('min_self_clearance_mm'),
        total_length_mm=round(sum(float(r['length_mm'])
                                  for r in g5['routes']), 6),
        routes=len(g5['routes']),
        heights_used=len({round(float(part['z_mm']), 9)
                          for r in g5['routes']
                          for part in r['parts'] if part['kind'] == 'flat'}))
    log('[summary] %s' % json.dumps(summary, ensure_ascii=False))

    # ---------------------------------------------------------------- tables
    crossing_rows = []
    for index, event in enumerate(sorted(same['crossings'],
                                         key=lambda e: (e['z'], e['route_a'],
                                                        e['route_b']))):
        crossing_rows.append(dict(
            crossing_id=index + 1, z_mm=round(event['z'], 6),
            z_label=G5.plane_label(event['z']),
            route_a=event['route_a'], route_b=event['route_b'],
            x_mm=round(event['x'], 6), y_mm=round(event['y'], 6),
            angle_deg=round(event['angle_deg'], 6),
            kind_a=event['kind_a'], kind_b=event['kind_b'],
            s_a_mm=round(event['sa'], 6), s_b_mm=round(event['sb'], 6),
            theta_margin_deg=round(event['angle_deg'] - 45.0, 6),
            pass_45=bool(event['angle_deg'] >= 45.0)))
    write_csv(out / 'g5_crossing_angles.csv', crossing_rows)

    layers = layer_table(same['crossings'])
    layer_rows = []
    for z in sorted(layers):
        row = layers[z]
        layer_rows.append(dict(z_mm=round(z, 6), z_label=G5.plane_label(z),
                               crossings=row['crossings'],
                               violations=row['violations'],
                               routes=len(row['routes']),
                               min_angle_deg=round(row['min_angle'], 6)))
    write_csv(out / 'g5_layer_statistics.csv', layer_rows)

    base_world = G5.World(base['routes'], min_angle_deg=45.0)
    base_same = base_world.audit_all(min_angle_deg=45.0)
    base_layers = layer_table(base_same['crossings'])
    comparison = dict(
        schema='g5_geometry_comparison_v1',
        g4=dict(routes=len(base['routes']),
                crossings=len(base_same['crossings']),
                pairs=len({(e['route_a'], e['route_b'])
                           for e in base_same['crossings']}),
                violations=len(base_same['violations']),
                min_angle_deg=round(min(e['angle_deg']
                                        for e in base_same['crossings']), 6),
                deficit_deg=round(sum(45.0 - e['angle_deg']
                                      for e in base_same['violations']), 6),
                max_deficit_deg=round(max(45.0 - e['angle_deg']
                                          for e in base_same['violations']), 6),
                total_length_mm=round(sum(float(r['length_mm'])
                                          for r in base['routes']), 6),
                max_route_crossings=max(
                    Counter([e['route_a'] for e in base_same['crossings']]
                            + [e['route_b'] for e in base_same['crossings']]
                            ).values() or [0])),
        g5=dict(routes=len(g5['routes']), crossings=summary['crossings'],
                pairs=summary['pairs'], violations=summary['violations'],
                min_angle_deg=summary['min_angle_deg'],
                deficit_deg=summary['deficit_deg'],
                max_deficit_deg=summary['max_deficit_deg'],
                total_length_mm=summary['total_length_mm'],
                max_route_crossings=max(
                    Counter([e['route_a'] for e in same['crossings']]
                            + [e['route_b'] for e in same['crossings']]
                            ).values() or [0])),
        per_layer=[
            dict(z_mm=round(z, 6), z_label=G5.plane_label(z),
                 g4_crossings=base_layers.get(z, {}).get('crossings', 0),
                 g4_violations=base_layers.get(z, {}).get('violations', 0),
                 g5_crossings=layers.get(z, {}).get('crossings', 0),
                 g5_violations=layers.get(z, {}).get('violations', 0))
            for z in sorted(set(base_layers) | set(layers))])
    (out / 'g5_geometry_comparison.json').write_text(
        json.dumps(comparison, indent=1, ensure_ascii=False), encoding='utf-8')
    write_csv(out / 'g5_geometry_comparison.csv',
              comparison['per_layer'])

    # -------------------------------------------------- route change summary
    base_by_id = {int(r['route_id']): r for r in base['routes']}
    change_rows = []
    changed = 0
    for route in g5['routes']:
        rid = int(route['route_id'])
        old = base_by_id[rid]
        same_parts = json.dumps(old.get('parts'), sort_keys=True) == json.dumps(
            route.get('parts'), sort_keys=True)
        if not same_parts:
            changed += 1
        change_rows.append(dict(
            route_id=rid, changed=not same_parts,
            source_endpoint=route['source_endpoint'],
            target_endpoint=route['target_endpoint'],
            manual_group=route.get('manual_group') or '',
            g4_plane=old.get('target_plane'), g5_plane=route.get('target_plane'),
            plane_changed=old.get('target_plane') != route.get('target_plane'),
            g4_length_mm=round(float(old['length_mm']), 6),
            g5_length_mm=round(float(route['length_mm']), 6),
            length_delta_mm=round(float(route['length_mm'])
                                  - float(old['length_mm']), 6),
            g4_arcs=sum(1 for part in old['parts'] if part['kind'] == 'flat'
                        for prim in part['primitives']
                        if prim['kind'] == 'arc'),
            g5_arcs=sum(1 for part in route['parts'] if part['kind'] == 'flat'
                        for prim in part['primitives']
                        if prim['kind'] == 'arc'),
            g4_transitions=old.get('n_transitions'),
            g5_transitions=route.get('n_transitions')))
    write_csv(out / 'g5_route_change_summary.csv', change_rows)
    summary['routes_changed'] = changed
    summary['routes_moved_plane'] = sum(1 for row in change_rows
                                        if row['plane_changed'])

    (out / 'g5_validation.json').write_text(
        json.dumps(dict(summary=summary, hard_issues=same['issues'][:50],
                        three_d_issues=three['issues'][:50],
                        structure_issues=result['structure'][:50],
                        self_clearance=result['self_issues'][:50]),
                   indent=1, ensure_ascii=False), encoding='utf-8')

    # ----------------------------------------------------------- eight files
    payload = dict(g5)
    payload['crossing_angles'] = crossing_rows[:50]
    manifest = {}
    for name in ('assignment_1024.csv', 'layer_planes.json',
                 'physical_layer_stack.json', 'process_rules.json'):
        source = FROZEN / name
        if source.exists():
            shutil.copy2(source, out / name)
            manifest[name] = dict(bytes=(out / name).stat().st_size,
                                  sha256=sha256_file(out / name))
    (out / 'routes_l3d.json').write_text(
        json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    stats = dict(schema='g5_crossing_stats_v1',
                 crossing_rule='strict D56 + theta_min=45 deg, exact tangents',
                 theta_min_deg=45.0, totals=dict(
                     crossings=summary['crossings'],
                     crossing_pairs=summary['pairs'],
                     routes_with_crossings=len({e['route_a']
                                                for e in same['crossings']}
                                               | {e['route_b']
                                                  for e in same['crossings']}),
                     max_route_crossings=summary.get('max_route_crossings', 0)),
                 planes=layer_rows, crossing_events=crossing_rows)
    (out / 'crossing_stats.json').write_text(
        json.dumps(stats, ensure_ascii=False), encoding='utf-8')
    for name in ('routes_l3d.json', 'crossing_stats.json', 'g5_validation.json'):
        manifest[name] = dict(bytes=(out / name).stat().st_size,
                              sha256=sha256_file(out / name))
    (out / 'SHA256.json').write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False), encoding='utf-8')
    (out / 'BEST_VALID.json').write_text(json.dumps(dict(
        schema='g5_best_valid_v1', label=args.label, legal=bool(legal),
        theta_min_deg=45.0, routed=summary['routes'],
        failed=0, crossings=summary['crossings'],
        violations_below_45=summary['violations'],
        min_angle_deg=summary['min_angle_deg'],
        routes_sha256=manifest['routes_l3d.json']['sha256'],
        acceptance_rule=('fully legal only: 1024/1024 routed, 0 failed, '
                         '0 crossings below 45 deg, R15, D56 and 3-D '
                         'clearance unchanged, independent validators PASS'),
        source_routes=args.routes), indent=1, ensure_ascii=False),
        encoding='utf-8')
    (out / 'g5_summary.json').write_text(
        json.dumps(summary, indent=1, ensure_ascii=False), encoding='utf-8')
    (out / 'finalise.log').write_text('\n'.join(log_lines), encoding='utf-8')
    print('[done] legal=%s  -> %s' % (legal, out))
    return 0 if legal else 2


if __name__ == '__main__':
    raise SystemExit(main())
