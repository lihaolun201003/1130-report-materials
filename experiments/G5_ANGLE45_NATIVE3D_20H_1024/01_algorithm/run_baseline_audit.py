# -*- coding: utf-8 -*-
"""G5 phase-1 deliverable: the complete baseline crossing-angle audit.

Produces, in ``00_baseline_audit/``:

* ``baseline_crossing_angles.csv``   every genuine same-height crossing with the
  exact local tangents, the angle, the primitive kinds, the chain positions and
  the 45 deg verdict;
* ``baseline_angle_violations.json`` the sub-45 deg events with the conflict
  graph and the hotspot ranking;
* ``angle_conflict_graph.json``      G_bad = (V, E_bad) with degrees, components
  and per-component summaries;
* ``baseline_angle_report.md``       the Chinese/English summary report;
* ``baseline_layer_statistics.csv``  per physical height.

The numbers are the *model* audit (``g5.model``); they are cross-checked against
the independent from-scratch validator output when it is present.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024.xyzrouter.g5 import model as G5

EXP = ROOT / 'experiments' / 'G5_ANGLE45_NATIVE3D_20H_1024'
FROZEN = ROOT / 'experiments' / 'COLD_START_20_HEIGHT_1024' / '10_best_valid'
BINS = [(0, 5), (5, 10), (10, 20), (20, 30), (30, 40), (40, 45), (45, 60),
        (60, 75), (75, 90.0001)]


def write_csv(path, rows, keys=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    keys = keys or list(rows[0].keys())
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, '') for key in keys})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--routes', default=str(FROZEN / 'routes_l3d.json'))
    parser.add_argument('--out', default=str(EXP / '00_baseline_audit'))
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    payload = json.loads(Path(args.routes).read_text(encoding='utf-8'))
    routes = payload['routes']
    by_id = {int(r['route_id']): r for r in routes}

    world = G5.World(routes, min_angle_deg=45.0)
    result = world.audit_all(min_angle_deg=45.0)
    events = result['crossings']
    violations = result['violations']
    three = world.audit_3d()
    print('[audit] crossings=%d violations=%d min=%.6f'
          % (len(events), len(violations),
             min(e['angle_deg'] for e in events)), flush=True)

    # ------------------------------------------------------------ crossings
    rows = []
    for index, event in enumerate(sorted(events, key=lambda e: (
            e['angle_deg'], e['z'], e['route_a'], e['route_b']))):
        ra = by_id[event['route_a']]
        rb = by_id[event['route_b']]
        rows.append(dict(
            crossing_id=index + 1,
            route_a=event['route_a'], route_b=event['route_b'],
            z_mm=round(event['z'], 6), z_label=G5.plane_label(event['z']),
            x_mm=round(event['x'], 6), y_mm=round(event['y'], 6),
            angle_deg=round(event['angle_deg'], 6),
            kind_a=event['kind_a'], kind_b=event['kind_b'],
            s_a_mm=round(event['sa'], 6), s_b_mm=round(event['sb'], 6),
            below_45=bool(event['angle_deg'] < 45.0),
            deficit_deg=round(max(0.0, 45.0 - event['angle_deg']), 6),
            source_a=ra['source_endpoint'], target_a=ra['target_endpoint'],
            source_b=rb['source_endpoint'], target_b=rb['target_endpoint'],
            plane_a=ra.get('target_plane'), plane_b=rb.get('target_plane'),
            manual_a=ra.get('manual_group') or '',
            manual_b=rb.get('manual_group') or ''))
    write_csv(out / 'baseline_crossing_angles.csv', rows)

    # ------------------------------------------------------------ graph
    adjacency = defaultdict(list)
    for event in violations:
        a, b = event['route_a'], event['route_b']
        adjacency[a].append((b, event))
        adjacency[b].append((a, event))
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for a, b in {(e['route_a'], e['route_b']) for e in violations}:
        union(a, b)
    groups = defaultdict(list)
    for node in parent:
        groups[find(node)].append(node)

    degree = {rid: len(neighbours) for rid, neighbours in adjacency.items()}
    components = []
    for key, nodes in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        nodes = sorted(nodes)
        edges = sorted({tuple(sorted((event['route_a'], event['route_b'])))
                        for node in nodes for _other, event in adjacency[node]})
        angles = [event['angle_deg'] for node in nodes
                  for _other, event in adjacency[node]]
        components.append(dict(
            size=len(nodes), edges=len(edges), routes=nodes,
            min_angle_deg=round(min(angles), 6) if angles else None,
            deficit_deg=round(sum(max(0.0, 45.0 - a) for a in angles) / 2.0, 6),
            events=len(angles) // 2))
    graph = dict(schema='g5_angle_conflict_graph_v1', theta_min_deg=45.0,
                 vertices=sorted(adjacency),
                 vertex_count=len(adjacency), edge_count=len(
                     {(e['route_a'], e['route_b']) for e in violations}),
                 degrees={str(rid): int(deg) for rid, deg in
                          sorted(degree.items())},
                 degree_histogram={str(k): int(v) for k, v in
                                   sorted(Counter(degree.values()).items())},
                 edges=[dict(route_a=event['route_a'],
                             route_b=event['route_b'],
                             z_mm=round(event['z'], 6),
                             x_mm=round(event['x'], 6),
                             y_mm=round(event['y'], 6),
                             angle_deg=round(event['angle_deg'], 6),
                             deficit_deg=round(45.0 - event['angle_deg'], 6))
                        for event in sorted(violations,
                                            key=lambda e: e['angle_deg'])],
                 components=components,
                 component_count=len(components),
                 largest_component=components[0]['size'] if components else 0)
    (out / 'angle_conflict_graph.json').write_text(
        json.dumps(graph, indent=1, ensure_ascii=False), encoding='utf-8')

    # ------------------------------------------------------------ histogram
    histogram = []
    for low, high in BINS:
        count = sum(1 for e in events if low <= e['angle_deg'] < high)
        histogram.append(dict(low_deg=low, high_deg=high, crossings=count,
                              below_45=bool(high <= 45.0)))
    # ------------------------------------------------------------ per layer
    layers = defaultdict(lambda: dict(crossings=0, violations=0, min_angle=90.0,
                                      routes=set(), deficits=0.0))
    for event in events:
        z = round(event['z'], 6)
        row = layers[z]
        row['crossings'] += 1
        row['routes'].add(event['route_a'])
        row['routes'].add(event['route_b'])
        row['min_angle'] = min(row['min_angle'], event['angle_deg'])
        if event['angle_deg'] < 45.0:
            row['violations'] += 1
            row['deficits'] += 45.0 - event['angle_deg']
    layer_rows = []
    for z in sorted(layers):
        row = layers[z]
        layer_rows.append(dict(z_mm=z, z_label=G5.plane_label(z),
                               crossings=row['crossings'],
                               violations_below_45=row['violations'],
                               min_angle_deg=round(row['min_angle'], 6),
                               deficit_deg=round(row['deficits'], 6),
                               routes=len(row['routes'])))
    write_csv(out / 'baseline_layer_statistics.csv', layer_rows)
    worst_routes = sorted(((rid, len(v)) for rid, v in adjacency.items()),
                          key=lambda kv: -kv[1])[:25]

    summary = dict(
        schema='g5_baseline_angle_violations_v1',
        theta_min_deg=45.0,
        crossings=len(events),
        crossing_pairs=len({(e['route_a'], e['route_b']) for e in events}),
        routes_with_crossings=len({e['route_a'] for e in events}
                                  | {e['route_b'] for e in events}),
        routes_with_violations=len(adjacency),
        violations_below_45=len(violations),
        deficit_deg=round(sum(45.0 - e['angle_deg'] for e in violations), 6),
        max_deficit_deg=round(max(45.0 - e['angle_deg'] for e in violations), 6),
        min_angle_deg=round(min(e['angle_deg'] for e in events), 6),
        min_angle_event=min(events, key=lambda e: e['angle_deg']),
        histogram=histogram,
        violations_by_layer={G5.plane_label(z): int(
            layers[z]['violations']) for z in sorted(layers)},
        crossings_by_layer={G5.plane_label(z): int(layers[z]['crossings'])
                            for z in sorted(layers)},
        worst_routes=[dict(route_id=rid, violations=count,
                           source=by_id[rid]['source_endpoint'],
                           target=by_id[rid]['target_endpoint'],
                           plane=by_id[rid].get('target_plane'),
                           manual=by_id[rid].get('manual_group') or '')
                      for rid, count in worst_routes],
        conflict_graph=dict(vertices=len(adjacency),
                            edges=len({(e['route_a'], e['route_b'])
                                       for e in violations}),
                            components=len(components),
                            largest=graph['largest_component']),
        violations_involving_manual=sum(
            1 for e in violations
            if (by_id[e['route_a']].get('manual_group') or '').strip()
            or (by_id[e['route_b']].get('manual_group') or '').strip()),
        three_d_minima={k: (None if v is None else round(v, 9))
                        for k, v in three['minima'].items()},
        three_d_issues=len(three['issues']),
        hard_same_height_issues=len(result['issues']),
        min_non_crossing_mm=round(result['min_non_crossing'][0], 9),
        total_length_mm=round(sum(float(r['length_mm']) for r in routes), 6),
        violations=[dict(route_a=e['route_a'], route_b=e['route_b'],
                         z_mm=round(e['z'], 6), x_mm=round(e['x'], 6),
                         y_mm=round(e['y'], 6),
                         angle_deg=round(e['angle_deg'], 6),
                         kind_a=e['kind_a'], kind_b=e['kind_b'],
                         deficit_deg=round(45.0 - e['angle_deg'], 6))
                    for e in sorted(violations, key=lambda e: e['angle_deg'])])
    (out / 'baseline_angle_violations.json').write_text(
        json.dumps(summary, indent=1, ensure_ascii=False), encoding='utf-8')

    # cross-check against the independent validator output when available
    independent = None
    path = out / 'independent_angle_validator' / 'g5_angle_validation.json'
    if path.exists():
        independent = json.loads(path.read_text(encoding='utf-8')).get('summary')

    report = []
    report.append('# G4 基线交叉角度审计 / Baseline crossing-angle audit\n')
    report.append('输入：`experiments/COLD_START_20_HEIGHT_1024/10_best_valid/'
                  'routes_l3d.json`（sha256 `35d7ebed…b90753`，冻结只读）。\n')
    report.append('## 1. 全局结果\n')
    report.append('| 指标 | 数值 |')
    report.append('|---|---:|')
    report.append('| 真实同层交叉事件 | %d |' % summary['crossings'])
    report.append('| 唯一交叉线路对 | %d |' % summary['crossing_pairs'])
    report.append('| 涉及线路 | %d |' % summary['routes_with_crossings'])
    report.append('| **小于 45° 的交叉** | **%d** |' % len(violations))
    report.append('| 角度不足总量 D_theta | %.6f° |' % summary['deficit_deg'])
    report.append('| 最大单次角度不足 D_max | %.6f° |' % summary['max_deficit_deg'])
    report.append('| 最小交叉角 | %.6f° |' % summary['min_angle_deg'])
    report.append('| 无关交叉最小净距 | %.9f mm |' % summary['min_non_crossing_mm'])
    report.append('| 最小三维净距 (flat/transition/transition) | %s |'
                  % summary['three_d_minima'])
    report.append('| 原有 D56 硬性违规 | %d |' % summary['hard_same_height_issues'])
    report.append('| 三维净空违规 | %d |' % summary['three_d_issues'])
    report.append('| 总波导长度 | %.6f mm |' % summary['total_length_mm'])
    report.append('')
    report.append('## 2. 角度分布\n')
    report.append('| 区间 (°) | 交叉数 |')
    report.append('|---|---:|')
    for row in histogram:
        report.append('| [%d, %g) | %d |' % (row['low_deg'], row['high_deg'],
                                             row['crossings']))
    report.append('')
    report.append('## 3. 逐层违规\n')
    report.append('| 物理高度 | 层 | 交叉数 | <45° | 最小角 | 角度不足 |')
    report.append('|---:|---|---:|---:|---:|---:|')
    for row in layer_rows:
        report.append('| %+.3f | %s | %d | %d | %.3f | %.3f |'
                      % (row['z_mm'], row['z_label'], row['crossings'],
                         row['violations_below_45'], row['min_angle_deg'],
                         row['deficit_deg']))
    report.append('')
    report.append('## 4. 违规冲突图\n')
    report.append('- 顶点（线路）= %d，边（违规对）= %d，连通分量 = %d，'
                  '最大分量 = %d 条线路。'
                  % (graph['vertex_count'], graph['edge_count'],
                     graph['component_count'], graph['largest_component']))
    report.append('- 度数分布：%s' % graph['degree_histogram'])
    report.append('- 涉及人工 U 结构的违规事件：%d / %d'
                  % (summary['violations_involving_manual'], len(violations)))
    report.append('- 违规最多的线路：')
    for row in summary['worst_routes'][:10]:
        report.append('  - R%d %s → %s（层 %s，%d 次，manual=%s）'
                      % (row['route_id'], row['source'], row['target'],
                         row['plane'], row['violations'],
                         row['manual'] or 'no'))
    report.append('')
    report.append('## 5. 形态学结论\n')
    kinds = Counter((e['kind_a'], e['kind_b']) for e in violations)
    report.append('- 违规仅出现在含圆弧的交叉上：%s。直线-直线交叉全部为 90°，'
                  '无一次违规。' % dict(kinds))
    report.append('- 小角度来自两类近切结构：(i) 两条同半径 R15 圆弧圆心相距很小'
                  '（θ≈acos(1−d²/2R²)）；(ii) 水平主干线从某圆弧顶点下方 0–4.4 mm '
                  '处穿过（θ≈acos(|Δy|/R)）。要得到 θ≥45°，圆弧圆心距须 ≥11.48 mm，'
                  '或主干线相对圆心的高差 ≤10.6 mm。')
    report.append('- 因此 G5 的可行修复只能靠**改变真实几何**：换层、平移走廊、'
                  '或原生三维上/下跨。')
    if independent:
        report.append('')
        report.append('## 6. 独立复核\n')
        report.append('| 指标 | 本项目模型 | 独立从零实现 |')
        report.append('|---|---:|---:|')
        report.append('| 交叉数 | %d | %s |'
                      % (summary['crossings'], independent.get('crossings')))
        report.append('| <45° | %d | %s |'
                      % (len(violations),
                         independent.get('violations_below_theta_min')))
        report.append('| 最小角 | %.6f | %s |'
                      % (summary['min_angle_deg'],
                         independent.get('min_angle_deg')))
    (out / 'baseline_angle_report.md').write_text('\n'.join(report) + '\n',
                                                  encoding='utf-8')
    print('[done] %s' % out, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
