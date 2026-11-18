# -*- coding: utf-8 -*-
"""Assemble every final metric of the 20-height experiment into one payload.

Reads only artifacts that already exist (never recomputes geometry) and writes
``12_reports/final_metrics.json`` plus small markdown tables.  Missing stages are
reported as ``not run`` -- nothing is interpolated or hidden.
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


def _first(directory, *names):
    directory = Path(directory)
    for name in names:
        path = directory / name
        if path.is_file():
            return path
    return None


def _first_in_chain(directories, *names):
    for directory in directories:
        for name in names:
            path = Path(directory) / name
            if path.is_file():
                return path
    return None


def _full_validation(layout_dir):
    """First validation payload that carries the full measurement block.

    A ``best_valid`` snapshot may carry a 3-line validation summary; the stage
    root / arm root carries the full independent validator report.  Prefer the
    full one, never the summary.
    """
    layout_dir = Path(layout_dir)
    candidates = (layout_dir / 'validation.json',
                  layout_dir / 'validation' / 'validation.json',
                  layout_dir.parent / 'validation.json',
                  layout_dir.parent / 'validation' / 'validation.json',
                  layout_dir.parent / 'validation' / 'final' / 'validation.json')
    fallback = {}
    for path in candidates:
        payload = _load(path)
        if not payload:
            continue
        if payload.get('counts'):
            return payload
        if not fallback:
            fallback = payload
    return fallback


def _crossing_stats(layout_dir):
    layout_dir = Path(layout_dir)
    path = _first_in_chain(
        (layout_dir, layout_dir.parent, layout_dir.parent.parent),
        'crossing_stats.json')
    return _load(path) or {}


def _percentile(values, percentile):
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    index = (len(ordered) - 1) * percentile / 100.0
    low = int(index)
    high = min(low + 1, len(ordered) - 1)
    fraction = index - low
    return round(ordered[low] * (1 - fraction) + ordered[high] * fraction, 4)


def layout_metrics(layout_dir):
    """Everything measurable about one legal layout directory."""
    layout_dir = Path(layout_dir)
    routes_path = layout_dir / 'routes_l3d.json'
    if not routes_path.is_file():
        return dict(available=False, dir=str(layout_dir))
    routes_payload = _load(routes_path) or {}
    routed_from_counts = None
    records = [record for record in (routes_payload.get('routes') or ())
               if str(record.get('status') or '') != 'failed']
    stats = _crossing_stats(layout_dir)
    validation = _full_validation(layout_dir)
    counts = validation.get('counts') or {}
    final_stats = _load(_first(layout_dir, 'final_stats.json')) or {}
    transition = _load(_first(layout_dir, 'transition_stats.json')) or {}

    transitions = 0
    total_length = 0.0
    max_length = 0.0
    planar_arcs = 0
    routes_with_multi_arc = 0
    routes_with_mid = 0
    min_flat_radius = None
    for record in records:
        length = float(record.get('length_mm') or 0.0)
        total_length += length
        max_length = max(max_length, length)
        arcs_this_route = 0
        mid = 0
        for part in record.get('parts') or ():
            if part.get('kind') == 'transition':
                transitions += 1
                if part.get('tag') == 'mid':
                    mid += 1
                radius = part.get('radius_mm')
                if radius is not None:
                    min_flat_radius = (radius if min_flat_radius is None
                                       else min(min_flat_radius, radius))
            elif part.get('kind') == 'flat':
                for prim in part.get('primitives') or ():
                    if prim.get('kind') == 'arc':
                        planar_arcs += 1
                        arcs_this_route += 1
                        radius = prim.get('radius')
                        if radius is not None:
                            min_flat_radius = (radius if min_flat_radius is None
                                               else min(min_flat_radius, radius))
        if arcs_this_route >= 2:
            routes_with_multi_arc += 1
        if mid:
            routes_with_mid += 1
    totals = stats.get('totals') or {}
    distribution = totals.get('per_route_distribution') or {}
    if totals.get('crossings') is None:
        # the frozen RouteWorld recount lives in the validator counts
        totals = dict(crossings=counts.get('same_plane_crossings'),
                      crossing_pairs=counts.get('same_plane_crossing_pairs'))
        distribution = counts.get('per_route_crossing_distribution') or {}
    if not distribution:
        distribution = counts.get('per_route_crossing_distribution') or {}
    if routed_from_counts is None:
        routed_from_counts = counts.get('routed')
    return dict(
        available=True, dir=str(layout_dir),
        routes_sha256=_sha256(routes_path),
        route_count=len(records) or routed_from_counts,
        failed=(len((routes_payload.get('routes') or ())) - len(records))
        or counts.get('failed'),
        crossings=totals.get('crossings'),
        crossing_pairs=totals.get('crossing_pairs'),
        per_route=distribution,
        transitions=transitions,
        routes_with_mid_transitions=routes_with_mid,
        mid_transitions=transition.get('mid_transitions'),
        planar_arc_primitives=planar_arcs,
        routes_with_two_or_more_planar_arcs=routes_with_multi_arc,
        total_length_mm=round(total_length, 6),
        max_route_length_mm=round(max_length, 6),
        min_flat_arc_radius_mm=min_flat_radius,
        # the INDEPENDENT validator measurement wins over the router's own
        # final_stats (which only stores the acceptance bound, e.g. 0.05)
        min_3d_clearance_mm=(counts.get('min_3d_clearance_mm')
                             or final_stats.get('min_3d_clearance_mm')
                             or totals.get('min_3d_clearance_mm')),
        validator=dict(
            name=validation.get('validator'),
            validation_pass=validation.get('validation_pass'),
            geometry_pass=validation.get('geometry_pass'),
            contract_pass=validation.get('contract_pass'),
            violation_count=(validation.get('violation_count')
                             if validation.get('violation_count') is not None
                             else counts.get('violation_total')),
            manual_policy=validation.get('manual_policy')
            or validation.get('manual_model'),
            path=str(_first_in_chain((layout_dir, layout_dir.parent),
                                     'validation.json')),
        ),
    )


#: (key, label, layout dir) for every stage that produced a legal layout
STAGE_LAYOUTS = (
    ('S03_initial_cold_start', 'cold assignment -> fanout -> D56 multi-arc XY -> 3D',
     P20.INIT_RUN),
    ('S04_E5_joint_repair', 'from-scratch annealing + joint repair (accepted E5)',
     P20.E5_DIR),
    ('S05_native3d_phase1', 'Native 3D Phase 1 (A/B/C)',
     P20.NATIVE3D_ABC_RUN),
    ('S06_native3d_phase2', 'Native 3D Phase 2 (D/E/F)',
     Path(P20.NATIVE3D_DEF_RUN) / 'best_valid'),
    ('S07_G123', 'XYZ joint G1 -> G2a -> G2b -> G3',
     Path(P20.XYZ_RUN) / 'best_valid'),
    ('S08_G4_C0', 'G4 control arm C0 (continuation)', Path(P20.G4) / '01_arm_C0' / 'best_valid'),
    ('S08_G4a', 'G4a manual-U groups kept, group XY+Z rebuild',
     Path(P20.G4) / '02_arm_G4a' / 'best_valid'),
    ('S08_G4b', 'G4b manual-U dynamic regrouping + height migration',
     Path(P20.G4) / '03_arm_G4b' / 'best_valid'),
    ('S08_G4c_frozen', 'G4c-frozen ALNS make-way, manual-U frozen',
     Path(P20.G4) / '04_arm_G4c_frozen' / 'best_valid'),
    ('S08_G4c_free', 'G4c-free ALNS make-way, manual-U unfrozen',
     Path(P20.G4) / '05_arm_G4c_free' / 'best_valid'),
    ('S08_G4d', 'G4d large-neighbourhood global ALNS',
     Path(P20.G4) / '06_arm_G4d' / 'best_valid'),
    ('S08_G4_chain_link2', 'G4 progressive chain link 2: G4c rerun from '
     'best(G4a,G4b)', Path(P20.G4) / '08_progressive_chain' / '02_link_G4c'),
    ('S08_G4_chain_link4', 'G4 progressive chain link 4: G4d from the best G4c '
     'checkpoint', Path(P20.G4) / '08_progressive_chain' / '03_link_G4d'),
    ('S10_best_valid', 'FINAL best legal 20-height solution (frozen)',
     Path(P20.BEST_VALID)),
)

#: frozen 21-height reference curve (read-only, NOT a target)
REFERENCE_21H = (
    ('21H initial fanout-first baseline', 11890),
    ('21H E5 joint repair', 2606),
    ('21H Native 3D Phase 1', 2440),
    ('21H Native 3D Phase 2', 2409),
    ('21H G3', 1322),
    ('21H G4 best legal', 1185),
)


def _g4_arm_records():
    root = Path(P20.G4)
    records = []
    for arm_dir in sorted(root.glob('0*_arm_*')):
        summary = _load(arm_dir / 'summary.json') or {}
        ledger = (_load(arm_dir / 'budget_ledger.json')
                  or _load(arm_dir / 'budget_ledger.live.json') or {})
        validation = _load(_first(arm_dir / 'validation', 'validation.json')) or {}
        records.append(dict(
            arm=arm_dir.name,
            start_crossings=summary.get('start_crossings'),
            crossings=summary.get('crossings') or summary.get('final_crossings'),
            accepted=summary.get('accepted'),
            validation_pass=validation.get('validation_pass',
                                           summary.get('validation_pass')),
            seconds=summary.get('seconds') or summary.get('search_seconds'),
            ledger=ledger,
        ))
    return records


def _ablation():
    root = Path(P20.MULTIARC)
    start = _load(root / 'START.json') or {}
    aborted = _load(root / 'ABORTED_OFF_INFEASIBLE.json') or {}
    conversion = _load(root / 'common_start_off' / 'conversion_report.json') or {}
    on_arm = layout_metrics(P20.INIT_RUN)
    off_dir = root / 'cold_start_off'
    off_arm = layout_metrics(off_dir) if (off_dir / 'routes_l3d.json').is_file() \
        else dict(available=False, dir=str(off_dir))
    return dict(
        protocol='strict common-start ON/OFF (pre-registered) + supplementary '
                 'cold-start ON/OFF from the identical cold assignment',
        start=dict(crossings=start.get('crossings'),
                   routes_sha256=start.get('routes_sha256'),
                   multi_arc_regions=start.get('multi_arc_regions')),
        strict_off_conversion=dict(
            feasible=conversion.get('feasible'),
            multi_arc_routes_before=conversion.get('multi_arc_routes_before'),
            converted=conversion.get('converted'),
            residual=conversion.get('residual'),
            residual_route_ids=conversion.get('residual_route_ids'),
            crossings_before=conversion.get('start_crossings'),
            crossings_after=conversion.get('crossings_after'),
            crossing_delta=conversion.get('crossing_delta_from_start'),
            aborted=bool(aborted),
        ),
        cold_start_on=on_arm,
        cold_start_off=off_arm,
    )


def collect():
    stages = []
    previous = None
    for key, label, layout in STAGE_LAYOUTS:
        metrics = layout_metrics(layout)
        metrics.update(stage=key, label=label)
        if metrics.get('available') and previous is not None \
                and previous.get('available') and previous.get('crossings') is not None \
                and metrics.get('crossings') is not None:
            metrics['delta_crossings'] = (int(metrics['crossings'])
                                          - int(previous['crossings']))
        stages.append(metrics)
        previous = metrics
    return dict(
        schema='coldstart20_final_metrics_v1',
        profile=M.PROFILE,
        experiment=M.EXPERIMENT_NAME,
        model=M.MODEL_NAME,
        height_table=dict(
            plane_count=len(M.PLANE_IDS),
            body_plane_count=len(M.BODY_PLANES),
            plane_ids=[int(pid) for pid in M.PLANE_IDS],
            z_mm={str(pid): float(M.plane_z(pid)) for pid in M.PLANE_IDS},
            interfaces={key: float(value)
                        for key, value in M.INTERFACE_Z.items()},
            min_pitch_mm=M.min_height_pitch(),
            glass_z_mm=[M.GLASS_Z_MIN_MM, M.GLASS_Z_MAX_MM],
            headroom_mm=dict(low=M.plane_z(2) - M.GLASS_Z_MIN_MM,
                             high=M.GLASS_Z_MAX_MM - M.plane_z(18)),
        ),
        constraints=dict(
            min_bend_radius_mm=M.MIN_BEND_RADIUS_MM,
            min_3d_clearance_mm=M.MIN_3D_CLEARANCE_MM,
            same_layer_width_mm=M.WIDTH_MM,
            same_layer_edge_gap_mm=M.EDGE_GAP_MM,
            same_layer_clearance_mm=M.CLEARANCE_2D_MM,
            glass_thickness_mm=M.GLASS_THICKNESS_MM,
            route_count=1024,
            manual_route_count=368,
        ),
        stages=stages,
        reference_21h=[dict(stage=label, crossings=value)
                       for label, value in REFERENCE_21H],
        g4_arms=_g4_arm_records(),
        multi_arc_ablation=_ablation(),
    )


def render_markdown(payload):
    lines = ['# 20-height final metrics (machine-collected)', '']
    lines.append('| stage | routed | crossings | pairs | max/route | P95 | '
                 'mean | min 3D (mm) | min R (mm) | transitions | multi-arc '
                 'routes | length (mm) | validator | delta |')
    lines.append('|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|')
    for stage in payload['stages']:
        if not stage.get('available'):
            lines.append(f"| {stage['stage']} | not run yet | - | - | - | - | - "
                         f"| - | - | - | - | - | - | - |")
            continue
        distribution = stage.get('per_route') or {}
        lines.append('| %s | %s | **%s** | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
            stage['stage'], stage.get('route_count'),
            stage.get('crossings'), stage.get('crossing_pairs'),
            distribution.get('max'), distribution.get('p95'),
            distribution.get('mean'), stage.get('min_3d_clearance_mm'),
            stage.get('min_flat_arc_radius_mm'), stage.get('transitions'),
            stage.get('routes_with_two_or_more_planar_arcs'),
            stage.get('total_length_mm'),
            ('PASS' if (stage.get('validator') or {}).get('validation_pass')
             else 'FAIL'),
            ('%+d' % stage['delta_crossings'])
            if stage.get('delta_crossings') is not None else 'n/a'))
    lines.append('')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', default=None)
    args = parser.parse_args(argv)
    B.install()
    out_dir = Path(args.out_dir or P20.REPORTS)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = collect()
    (out_dir / 'final_metrics.json').write_text(
        json.dumps(payload, indent=1, ensure_ascii=False, default=str) + '\n',
        encoding='utf-8')
    markdown = render_markdown(payload)
    (out_dir / 'final_metrics.md').write_text(markdown + '\n', encoding='utf-8')
    print(markdown)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
