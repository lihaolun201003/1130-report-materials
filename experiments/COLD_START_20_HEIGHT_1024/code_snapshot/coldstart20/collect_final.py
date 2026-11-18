# -*- coding: utf-8 -*-
"""Collect the 20-height stage curve and the 21-height comparison.

Reads every stage's verified artifacts (never recomputes geometry) and writes
``12_reports/stage_curve_20h.{json,md}`` plus the 21H-vs-20H comparison table.
Missing stages are reported honestly as ``not run yet`` instead of being
interpolated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path

from . import bootstrap as B          # installs the 20-height profile on import
from . import model20 as M
from . import paths20 as P20


def _load(path):
    if path is None:
        return None
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return None


def _sha256(path):
    path = Path(path)
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _find(run_dir, *names):
    run_dir = Path(run_dir)
    for name in names:
        path = run_dir / name
        if path.is_file():
            return path
    return None


def _validation_status(run_dir):
    payload = _load(_find(run_dir, 'validation.json'))
    if not payload:
        return dict(available=False)
    return dict(
        available=True,
        validation_pass=payload.get('validation_pass'),
        geometry_pass=payload.get('geometry_pass'),
        contract_pass=payload.get('contract_pass'),
        violation_count=payload.get('violation_count'),
        validator=payload.get('validator'),
        routes_sha256=payload.get('routes_file_sha256'),
    )


def _crossing_stats(run_dir):
    payload = _load(_find(run_dir, 'crossing_stats.json'))
    if not payload:
        return dict(available=False)
    totals = payload.get('totals') or {}
    per_route = payload.get('per_route') or payload.get('per_route_counts')
    counts = []
    if isinstance(per_route, dict):
        counts = [int(value) for value in per_route.values()
                  if isinstance(value, (int, float))]
    elif isinstance(per_route, list):
        counts = [int(value.get('crossings') or 0) for value in per_route
                  if isinstance(value, dict)]
    if not counts:
        totals_dist = totals.get('per_route_distribution') or {}
        if totals_dist:
            distribution = dict(max=totals_dist.get('max', 0),
                                p95=totals_dist.get('p95', 0.0),
                                mean=totals_dist.get('mean', 0.0),
                                routes_with_crossings=totals_dist.get(
                                    'routes_with_crossings', 0))
        else:
            distribution = dict(max=0, p95=0.0, mean=0.0,
                                routes_with_crossings=0)
    else:
        distribution = dict(
            max=max(counts),
            p95=_percentile(counts, 95),
            mean=round(statistics.fmean(counts), 4),
            routes_with_crossings=sum(1 for value in counts if value > 0))
    routed = payload.get('routed')
    failed = payload.get('failed')
    if routed is None or failed is None:
        # native3d crossing_stats only carries crossing geometry; take the
        # route counts from the layout itself
        routes_payload = _load(Path(run_dir) / 'routes_l3d.json') or {}
        records = routes_payload.get('routes') or []
        if records:
            failed = sum(1 for record in records
                         if str(record.get('status') or '') == 'failed')
            routed = len(records) - failed
    return dict(
        available=True,
        crossings=totals.get('crossings'),
        crossing_pairs=totals.get('crossing_pairs'),
        routed=routed,
        failed=failed,
        per_route_distribution=distribution,
    )


def _percentile(values, percentile):
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    index = (len(ordered) - 1) * percentile / 100.0
    low = int(index)
    high = min(low + 1, len(ordered) - 1)
    fraction = index - low
    return round(ordered[low] * (1 - fraction) + ordered[high] * fraction, 4)


def _final_stats(run_dir):
    run_dir = Path(run_dir)
    payload = _load(_find(run_dir, 'final_stats.json')) or {}
    validation = _load(_find(run_dir, 'validation.json')) or {}
    counts = validation.get('counts') or {}
    routes_payload = _load(_find(run_dir, 'routes_l3d.json')) or {}
    records = routes_payload.get('routes') or []
    transitions = None
    total_length = payload.get('total_length_mm')
    max_length = payload.get('max_route_length_mm')
    if records:
        transitions = sum(
            1 for record in records for part in (record.get('parts') or ())
            if part.get('kind') == 'transition')
        if total_length is None:
            total_length = routes_payload.get('total_length_mm')
        if max_length is None:
            lengths = [float(record.get('length_mm') or 0.0)
                       for record in records]
            max_length = max(lengths) if lengths else None
    transition_payload = _load(_find(run_dir, 'transition_stats.json')) or {}
    out = dict(
        available=bool(payload or validation),
        routed=payload.get('routed', counts.get('routed')),
        failed=payload.get('failed', counts.get('failed')),
        direct_routes=payload.get('direct_routes',
                                 counts.get('direct_routes')),
        transition_routes=payload.get('transition_routes'),
        total_transitions=(payload.get('total_transitions')
                           or payload.get('transitions')
                           or counts.get('transitions') or transitions),
        total_length_mm=(total_length
                         or counts.get('total_length_mm')),
        max_route_length_mm=(max_length
                             or counts.get('max_route_length_mm')),
        min_3d_clearance_mm=(payload.get('min_3d_clearance_mm')
                             or counts.get('min_3d_clearance_mm')),
        radius_mm=(payload.get('radius_mm')
                   or counts.get('min_flat_arc_radius_mm')),
        world_violations=payload.get('world_violations'),
        mid_transitions=transition_payload.get('mid_transitions'),
        routes_with_mid_transitions=transition_payload.get(
            'routes_with_mid_transitions'),
    )
    return out


def _transition_stats(run_dir):
    payload = _load(_find(run_dir, 'transition_stats.json'))
    if not payload:
        return dict(available=False)
    return dict(available=True,
                mid_transitions=payload.get('mid_transitions')
                or payload.get('total'),
                routes_with_mid=payload.get('routes_with_mid_transitions'))


def _multi_arc(run_dir):
    """Planar multi-arc regions of the final layout (arc primitive runs)."""
    routes = _load(_find(run_dir, 'routes_l3d.json'))
    if not routes:
        return dict(available=False)
    routes_with_multi = 0
    arc_primitives = 0
    for route in routes.get('routes') or ():
        if str(route.get('status') or '') == 'failed':
            continue
        planar_arcs = 0
        for part in route.get('parts') or ():
            if part.get('kind') != 'flat':
                continue
            prims = part.get('primitives') or ()
            arcs = [prim for prim in prims if prim.get('kind') == 'arc']
            planar_arcs += len(arcs)
        arc_primitives += planar_arcs
        if planar_arcs >= 2:
            routes_with_multi += 1
    return dict(available=True, planar_arc_primitives=arc_primitives,
                routes_with_two_or_more_planar_arcs=routes_with_multi)


#: stage registry: (key, label, base dir, run dir, parent stage)
STAGES = (
    ('S03_initial_cold_start',
     '03 initial fanout-first + D56 multi-arc + 3D (cold assignment)',
     P20.FANOUT_XY, P20.INIT_RUN, None),
    ('S04_E5_joint_repair',
     '04 from-scratch annealing + joint repair (accepted E5)',
     P20.INITIAL_3D, P20.E5_DIR, 'S03_initial_cold_start'),
    ('S05_native3d_phase1',
     '05 Native 3D Phase 1 (A/B/C mid-body R15 layer change)',
     P20.NATIVE3D_ABC, P20.NATIVE3D_ABC_RUN, 'S04_E5_joint_repair'),
    ('S06_native3d_phase2',
     '06 Native 3D Phase 2 (D/E/F joint make-way + arc rebuild)',
     P20.NATIVE3D_DEF, P20.NATIVE3D_DEF_RUN, 'S05_native3d_phase1'),
    ('S07_G123',
     '07 XYZ joint optimisation G1/G2a/G2b/G3',
     P20.G123, Path(P20.XYZ_RUN) / 'best_valid', 'S06_native3d_phase2'),
    ('S08_G4_arms_best',
     '08 G4 best independent arm (G4c-free)',
     P20.G4, Path(P20.G4) / '05_arm_G4c_free' / 'best_valid', 'S07_G123'),
    ('S08_G4_chain',
     '08 G4 progressive chain (best link)',
     P20.G4, Path(P20.G4) / '08_progressive_chain' / '03_link_G4d',
     'S08_G4_arms_best'),
    ('S10_final_best',
     'final best legal 20-height solution (frozen)',
     P20.BEST_VALID, Path(P20.BEST_VALID), 'S08_G4_chain'),
)

#: frozen 21-height reference curve (historical, read-only, NOT a target)
REFERENCE_21H = (
    ('21H initial fanout-first baseline', 11890),
    ('21H E5 joint repair', 2606),
    ('21H Native 3D Phase 1', 2440),
    ('21H Native 3D Phase 2', 2409),
    ('21H G3', 1322),
    ('21H G4 best legal', 1185),
)


def collect():
    B.install()
    entries = []
    previous = None
    for key, label, base, run_dir, _parent in STAGES:
        run_dir = Path(run_dir)
        entry = dict(stage=key, label=label, run_dir=str(run_dir),
                     exists=run_dir.exists(),
                     crossing=_crossing_stats(run_dir),
                     validation=_validation_status(run_dir),
                     final_stats=_final_stats(run_dir),
                     transition=_transition_stats(run_dir),
                     multi_arc=_multi_arc(run_dir),
                     routes_sha256=_sha256(run_dir / 'routes_l3d.json'))
        # promote the headline numbers to the top level as well, so generic
        # consumers (e.g. the stage-curve figure) can read them without knowing
        # the nested artifact schema
        entry['crossings'] = entry['crossing'].get('crossings')
        entry['crossing_pairs'] = entry['crossing'].get('crossing_pairs')
        entry['routed'] = entry['crossing'].get('routed')
        entry['failed'] = entry['crossing'].get('failed')
        entry['status'] = ('available' if entry['crossings'] is not None
                           else 'not run yet')
        crossings = entry['crossing'].get('crossings')
        previous_crossings = (previous or {}).get('crossing', {}).get('crossings')
        if crossings is not None and previous_crossings is not None:
            entry['delta_crossings'] = int(crossings) - int(previous_crossings)
        entries.append(entry)
        previous = entry
    return entries


def render_markdown(entries):
    lines = ['# 20-height experiment: stage curve (independently validated)', '']
    lines.append('Every number below is read from the stage artifacts written '
                 'in this experiment; nothing is interpolated and no stage is '
                 'credited with an earlier stage\'s gain.')
    lines.append('')
    header = ('| stage | routed | failed | crossings | crossing pairs | '
              'unique-pair | max/route | P95 | mean | min 3D (mm) | R min (mm) | '
              'transitions | total length (mm) | validator | delta |')
    lines.append(header)
    lines.append('|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|')
    for entry in entries:
        crossing = entry['crossing']
        stats = entry['final_stats']
        validation = entry['validation']
        if not crossing.get('available'):
            lines.append(f"| {entry['stage']} | - | - | not run yet | - | - | - "
                         f"| - | - | - | - | - | - | - | - |")
            continue
        distribution = crossing.get('per_route_distribution') or {}
        delta = entry.get('delta_crossings')
        lines.append('| %s | %s | %s | **%s** | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
            entry['stage'], crossing.get('routed'), crossing.get('failed'),
            crossing.get('crossings'), crossing.get('crossing_pairs'),
            crossing.get('crossing_pairs'),
            distribution.get('max', 'n/a'), distribution.get('p95', 'n/a'),
            distribution.get('mean', 'n/a'),
            stats.get('min_3d_clearance_mm', 'n/a'),
            stats.get('radius_mm', 'n/a'),
            stats.get('total_transitions', 'n/a'),
            stats.get('total_length_mm', 'n/a'),
            ('PASS' if validation.get('validation_pass') else
             ('FAIL' if validation.get('available') else 'n/a')),
            ('%+d' % delta) if delta is not None else 'n/a'))
    lines.append('')
    lines.append('## 21-height historical reference (frozen, read-only)')
    lines.append('')
    lines.append('These are the historical 21-height numbers.  They are a '
                 'reference curve only -- **not** a target and not directly '
                 'attributable to the 20-height stages.')
    lines.append('')
    lines.append('| historical stage | crossings |')
    lines.append('|---|---:|')
    for label, value in REFERENCE_21H:
        lines.append('| %s | %d |' % (label, value))
    lines.append('')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', default=None)
    args = parser.parse_args(argv)
    B.install()
    out_dir = Path(args.out_dir or P20.REPORTS)
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = collect()
    payload = dict(schema='coldstart20_stage_curve_v1', profile=M.PROFILE,
                   plane_count=len(M.PLANE_IDS),
                   body_plane_count=len(M.BODY_PLANES),
                   interfaces=dict(M.INTERFACE_Z),
                   reference_21h=[dict(stage=label, crossings=value)
                                  for label, value in REFERENCE_21H],
                   stages=entries)
    (out_dir / 'stage_curve_20h.json').write_text(
        json.dumps(payload, indent=1, ensure_ascii=False, default=str) + '\n',
        encoding='utf-8')
    markdown = render_markdown(entries)
    (out_dir / 'stage_curve_20h.md').write_text(markdown + '\n',
                                                encoding='utf-8')
    print(markdown)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
