# -*- coding: utf-8 -*-
"""Repair the delivered G5 payload after the CTP-2.0 review.

Two defects were found by the independent crosstalk review:

1. ``crossing_stats.json`` reported ``totals.max_route_crossings = 0`` because
   ``run_finalise.py`` read a key the summary never stored.
2. ``g5_summary.json`` carried the sha256 of the *search input* while the
   delivered ``routes_l3d.json`` is re-serialised, so two different (both true)
   hashes appeared in the tree.

This script fixes both **without touching ``routes_l3d.json``** (its bytes, and
therefore every hash the validators and CTP-2.0 recorded, stay identical) and
re-indexes ``SHA256.json``.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'experiments' / 'G5_ANGLE45_NATIVE3D_20H_1024' / '03_best_partial'


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    routes_hash = sha256(OUT / 'routes_l3d.json')
    rows = list(csv.DictReader((OUT / 'g5_crossing_angles.csv')
                               .open(encoding='utf-8')))
    counts = {}
    for row in rows:
        for rid in (row['route_a'], row['route_b']):
            counts[rid] = counts.get(rid, 0) + 1
    max_route = max(counts.items(), key=lambda kv: kv[1]) if counts else (None, 0)

    stats = json.loads((OUT / 'crossing_stats.json').read_text(encoding='utf-8'))
    stats['totals']['max_route_crossings'] = int(max_route[1])
    stats['totals']['max_route_crossings_route'] = int(max_route[0])
    stats['totals']['routes_with_crossings'] = len(counts)
    stats['note'] = ('max_route_crossings recomputed from g5_crossing_angles.csv '
                     'after the CTP-2.0 review (run_finalise.py had read a key '
                     'that was never stored); routes_l3d.json is unchanged.')
    (OUT / 'crossing_stats.json').write_text(
        json.dumps(stats, ensure_ascii=False), encoding='utf-8')

    summary = json.loads((OUT / 'g5_summary.json').read_text(encoding='utf-8'))
    summary['routes_sha256_input'] = summary.get('routes_sha256')
    summary['routes_sha256_delivered'] = routes_hash
    summary['routes_sha256_note'] = (
        'the input search result and the delivered payload differ only by JSON '
        're-serialisation (compact dumps + crossing_angles sample); the '
        'delivered hash is routes_sha256_delivered and is the one indexed in '
        'SHA256.json / BEST_VALID.json')
    summary['max_route_crossings'] = int(max_route[1])
    summary['max_route_crossings_route'] = int(max_route[0])
    (OUT / 'g5_summary.json').write_text(
        json.dumps(summary, indent=1, ensure_ascii=False), encoding='utf-8')

    manifest = {}
    for path in sorted(OUT.iterdir()):
        if path.is_file() and path.name not in ('SHA256.json',):
            manifest[path.name] = dict(bytes=path.stat().st_size,
                                       sha256=sha256(path))
    (OUT / 'SHA256.json').write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False), encoding='utf-8')
    print('[repair] routes_l3d.json sha256 = %s (unchanged)' % routes_hash)
    print('[repair] max_route_crossings = %d (route %s)'
          % (max_route[1], max_route[0]))
    print('[repair] SHA256.json now indexes %d files' % len(manifest))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
