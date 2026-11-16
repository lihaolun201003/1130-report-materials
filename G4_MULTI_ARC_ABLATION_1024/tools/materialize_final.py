# -*- coding: utf-8 -*-
"""Materialise a final run directory for one arm (byte-identical routes + stats).

``best_valid/`` of a G4 arm only stores ``routes_l3d.json`` + ``assignment_1024.csv``
+ ``SHA256.json``.  The per-height figure/table pipeline (``g4/plots_g4.py``)
reads a *run directory* that also carries ``crossing_stats.json`` and
``summary.json``.  This tool copies the two geometry files **byte for byte**
(so the routes SHA256 is preserved) and writes the two derived statistics files
with the same engine code the arms use (``optimizer.Optimizer.crossing_stats``),
plus a validation copy.

Usage::

    python materialize_final.py --best <arm>/03_G4d/best_valid \
        --out <arm>/04_final [--validation <arm>/03_G4d/validation]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024.xyzrouter import optimizer as OPT     # noqa: E402
from four_side_1024.fanout1024.xyzrouter import route_builder as RB  # noqa: E402
from four_side_1024.fanout1024.xyzrouter import world_adapter as WA  # noqa: E402
from four_side_1024.fanout1024.xyzrouter.g4 import paths as GP       # noqa: E402
from four_side_1024.fanout1024.reheight21 import model as M          # noqa: E402


def _sha(path):
    return GP.sha256_file(path)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--best', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--validation', default=None)
    parser.add_argument('--note', default='')
    args = parser.parse_args(argv)

    best = Path(args.best)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name in ('routes_l3d.json', 'assignment_1024.csv'):
        shutil.copyfile(best / name, out / name)

    payload = json.loads((best / 'routes_l3d.json').read_text(encoding='utf-8'))
    rows = GP.read_csv_rows(best / 'assignment_1024.csv')
    normalized = RB.normalized_rows(rows, stack=M.layer_stack())
    state = WA.RouteWorld(payload.get('routes') or [], normalized,
                          log=lambda *_a: None)
    baseline = dict(payload=payload, routes=payload.get('routes') or [],
                    rows=rows)
    optimizer = OPT.Optimizer(state, baseline, out, log=lambda *_a: None)
    optimizer.baseline_crossings = getattr(state, 'start_crossings', {}) or {}
    stats = optimizer.crossing_stats()
    GP.write_json(out / 'crossing_stats.json', stats)
    summary = dict(
        crossings=int(stats['totals']['crossings']),
        crossing_pairs=int(stats['totals']['crossing_pairs']),
        routes_with_crossings=int(stats['totals']['routes_with_crossings']),
        max_route_crossings=int(stats['totals']['max_route_crossings']),
        total_length_mm=round(float(state.total_length()), 6),
        mid_transitions=int(state.mid_transition_count()),
        routes=int(len(state.routes)),
        source_best=str(best),
        note=args.note,
        plane_counts={str(z): dict(events=int(v[0]), pairs=int(v[1]),
                                   routes=len(state.plane_prims.get(z, {})))
                      for z, v in sorted(state.plane_counts.items())},
    )
    GP.write_json(out / 'summary.json', summary)
    if args.validation:
        target = out / 'validation'
        target.mkdir(parents=True, exist_ok=True)
        for name in ('validation.json', 'validator_consistency_tests.json'):
            source = Path(args.validation) / name
            if source.exists():
                shutil.copyfile(source, target / name)
    hashes = dict(
        routes_l3d_json=_sha(out / 'routes_l3d.json'),
        assignment_1024_csv=_sha(out / 'assignment_1024.csv'),
        crossing_stats_json=_sha(out / 'crossing_stats.json'),
        summary_json=_sha(out / 'summary.json'),
        source_routes_l3d_json=_sha(best / 'routes_l3d.json'),
    )
    GP.write_json(out / 'SHA256.json', hashes)
    print(json.dumps(dict(out=str(out), crossings=summary['crossings'],
                          pairs=summary['crossing_pairs'],
                          max_route_crossings=summary['max_route_crossings'],
                          total_length_mm=summary['total_length_mm'],
                          routes_sha256=hashes['routes_l3d_json'],
                          byte_identical=(hashes['routes_l3d_json']
                                          == hashes['source_routes_l3d_json'])),
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
