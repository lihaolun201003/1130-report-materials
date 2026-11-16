# -*- coding: utf-8 -*-
"""Write ``results/INDEX.md`` + ``results/INDEX.json`` -- the run index.

The formal run artefacts live in ``runs/<arm>/<tag>/``; this index is the
requested ``results/`` entry point: one row per run with the headline metrics
and the relative path of its complete artefact set.

Usage::

    python .../tools/build_results_index.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs-json', default=str(EXP / 'tables' / 'runs.json'))
    parser.add_argument('--out', default=str(EXP / 'results'))
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    payload = json.loads(Path(args.runs_json).read_text(encoding='utf-8-sig'))
    rows = [row for row in payload['runs'] if row.get('status') == 'complete']
    rows.sort(key=lambda row: (str(row['arm']), str(row['tag'])))

    index = []
    for row in rows:
        rel = 'runs/%s/%s' % (row['arm'], row['tag'])
        index.append(dict(
            arm=row['arm'], tag=row['tag'], seed=row['seed'],
            multi_arc=row.get('multi_arc'),
            final_crossings=row.get('final_crossings'),
            crossing_pairs=row.get('crossing_pairs'),
            total_length_mm=row.get('total_length_mm'),
            multi_arc_regions=row.get('multi_arc_regions'),
            d56_candidate_evals=row.get('d56_candidate_evals'),
            route_3d_checks=row.get('route_3d_checks'),
            wall_seconds=row.get('wall_seconds'),
            validator_pass=row.get('validator_pass'),
            validator_final_pass=row.get('validator_final_pass'),
            routes_sha256=row.get('final_routes_sha256'),
            path=rel))
    (out / 'INDEX.json').write_text(json.dumps(
        dict(schema='g4_multi_arc_final_results_index_v1',
             note='complete ON/OFF artefact sets live under runs/<arm>/<tag>/; '
                  'this folder is the results entry point',
             n_runs=len(index), runs=index), ensure_ascii=False, indent=1),
        encoding='utf-8')

    lines = ['# results/ — 所有 ON / OFF 结果索引', '',
             '本包的完整运行产物位于 `runs/<arm>/<tag>/`（每次运行一个目录，'
             '含 routes / assignment / crossing_stats / 两个 Validator / 日志 / 账本）。',
             '本文件是 `results/` 入口：逐 run 的核心指标与相对路径。', '',
             '| arm | tag | seed | 多圆弧 | 交叉 | 唯一对 | 长度 mm | 多圆弧区域 |'
             ' d56 | r3d | 墙钟 s | Validator | 路径 |',
             '|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|---|']
    for row in index:
        lines.append('| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | `%s` |'
                     % (row['arm'], row['tag'], row['seed'], row['multi_arc'],
                        row['final_crossings'], row['crossing_pairs'],
                        row['total_length_mm'], row['multi_arc_regions'],
                        row['d56_candidate_evals'], row['route_3d_checks'],
                        row['wall_seconds'],
                        'PASS' if row['validator_pass'] else 'FAIL', row['path']))
    lines.append('')
    lines.append('文件名说明：`c1_*` = 主实验（等候选评价预算 d56 = 24000）；'
                 '`a1_*` = 辅助实验（等墙钟 900 s）。')
    (out / 'INDEX.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('wrote %s and %s (%d runs)'
          % (out / 'INDEX.md', out / 'INDEX.json', len(index)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
