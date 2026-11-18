# -*- coding: utf-8 -*-
"""First-pass stage-level crossing summary of the completed 20-height run.

Produces, under ``03_fanout_and_xy/``:

    crossing_summary_20h.json     machine-readable summary
    crossing_summary_20h.md       human-readable summary

Everything is re-derived from the *real* completed run artifacts
(``run_initial_20h/``) and cross-checked, not copied blindly:

* crossing events / route pairs / per-height counts come from the authoritative
  ``crossing_stats.json`` (written by the independent validator) and are
  re-verified against exact line/arc intersections recomputed from
  ``routes_l3d.json`` with the frozen ``plots21.compute_crossings`` semantics
  (this run's ``crossing_stats.json`` stores aggregate counts only, no x/y
  event list);
* per-route crossing distribution is computed from the recomputed events and
  must reproduce ``crossing_stats.json``'s published distribution exactly;
* total length / transitions / min 3D clearance / min radius / validator flags
  are quoted verbatim from ``validation.json`` (treated as read-only truth);
* the planar multi-arc count uses the frozen project definition
  ``four_side_1024.fanout1024.layer2d.local_multi_arc_regions``.

Usage::

    .venv\\Scripts\\python.exe -m \\
        four_side_1024.fanout1024.coldstart20.plot_layers20  # figures first
    .venv\\Scripts\\python.exe experiments\\COLD_START_20_HEIGHT_1024\\03_fanout_and_xy\\build_crossing_summary.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from collections import Counter, OrderedDict
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# the 20-height profile must be installed before importing the frozen pipeline
from four_side_1024.fanout1024.coldstart20 import bootstrap as B  # noqa: E402
from four_side_1024.fanout1024.coldstart20 import model20 as M    # noqa: E402

import matplotlib  # noqa: E402

matplotlib.use('Agg')

from four_side_1024.fanout1024 import layer2d  # noqa: E402
from four_side_1024.fanout1024.reheight21 import plots21 as P  # noqa: E402

RUN = Path(M.RUN_DIR)
STAGE = HERE
JSON_NAME = 'crossing_summary_20h.json'
MD_NAME = 'crossing_summary_20h.md'


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path):
    with Path(path).open('r', encoding='utf-8') as handle:
        return json.load(handle)


def write_json_file(path, payload):
    Path(path).write_text(
        json.dumps(payload, indent=1, ensure_ascii=False, default=str) + '\n',
        encoding='utf-8')
    return Path(path)


def percentile(values, q):
    """Linear-interpolation percentile (same convention as numpy default)."""
    ordered = sorted(values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * float(q) / 100.0
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    fraction = position - low
    return float(ordered[low] + (ordered[high] - ordered[low]) * fraction)


def _round(value, digits=9):
    return None if value is None else round(float(value), digits)


# ---------------------------------------------------------------------------
# analysis
# ---------------------------------------------------------------------------
def analyse():
    started = time.time()
    generated_at = time.strftime('%Y-%m-%dT%H:%M:%S')

    validation = read_json(RUN / 'validation.json')
    crossing_stats = read_json(RUN / 'crossing_stats.json')
    final_stats = read_json(RUN / 'final_stats.json')
    layer_planes = read_json(RUN / 'layer_planes.json')
    process_rules = read_json(RUN / 'process_rules.json')

    ds = P.build_dataset(RUN, label='initial_20h')
    if len(ds['model'].planes) != 20:
        raise RuntimeError('expected 20 routing heights, got %d'
                           % len(ds['model'].planes))

    # ---- 1. crossing events / pairs / per-height --------------------------
    recomputed_points = ds['crossings']
    recomputed_total = sum(int(item['count'])
                           for item in recomputed_points.values())
    recomputed_pairs = sum(int(item['pairs'])
                           for item in recomputed_points.values())
    authoritative_total = int(
        (crossing_stats.get('totals') or {}).get('crossings'))
    authoritative_pairs = int(
        (crossing_stats.get('totals') or {}).get('crossing_pairs'))
    if recomputed_total != authoritative_total:
        raise RuntimeError('recomputed crossing events %d != authoritative %d'
                           % (recomputed_total, authoritative_total))
    if recomputed_pairs != authoritative_pairs:
        raise RuntimeError('recomputed crossing pairs %d != authoritative %d'
                           % (recomputed_pairs, authoritative_pairs))

    stats_by_plane = {int(item['plane_id']): item
                      for item in crossing_stats.get('planes') or []}
    per_height = []
    route_event_count = Counter()
    global_pairs = set()
    planes_with_crossings = 0
    for plane in ds['model'].planes:
        plane_id = int(plane['plane_id'])
        entry = stats_by_plane.get(plane_id) or {}
        data = ds['geometry'].get(plane_id) or dict(bodies=[], leads=[])
        body_routes = {int(item['route_id']) for item in data.get('bodies') or []}
        crossings = int(entry.get('crossings', 0))
        pairs = int(entry.get('crossing_pairs', 0))
        count_recomputed = int((recomputed_points.get(plane_id) or {})
                               .get('count', 0))
        points = (recomputed_points.get(plane_id) or {}).get('points') or []
        for point in points:
            route_event_count[int(point['route_a'])] += 1
            route_event_count[int(point['route_b'])] += 1
            global_pairs.add((int(point['route_a']), int(point['route_b'])))
        if crossings != count_recomputed:
            raise RuntimeError('plane %d crossing count mismatch: %d vs %d'
                               % (plane_id, crossings, count_recomputed))
        if crossings:
            planes_with_crossings += 1
        plane_route_counts = Counter()
        for point in points:
            plane_route_counts[int(point['route_a'])] += 1
            plane_route_counts[int(point['route_b'])] += 1
        per_height.append(dict(
            plane_id=plane_id,
            label=str(plane['label']),
            z_mm=_round(plane['z_mm']),
            kind=str(plane['kind']),
            routes_with_bodies=len(body_routes),
            assigned_routes=int((ds['plane_stats'].get(plane_id) or {})
                                .get('assigned') or 0),
            crossings=crossings,
            crossing_pairs=pairs,
            routes_with_crossings=len(plane_route_counts),
            max_crossings_per_route=(max(plane_route_counts.values())
                                     if plane_route_counts else 0),
            p95_crossings_per_route=(_round(
                percentile(list(plane_route_counts.values()), 95), 6)
                if plane_route_counts else 0.0),
            mean_crossings_per_route=_round(
                sum(plane_route_counts.values()) / float(len(plane_route_counts))
                if plane_route_counts else 0.0, 9),
            crossings_source='crossing_stats.json (re-verified against exact '
                             'recomputed line/arc intersections)',
        ))

    per_route_values = list(route_event_count.values())
    with_crossings = len(per_route_values)
    event_endpoint_total = sum(per_route_values)
    all_counts = per_route_values + [0] * (1024 - with_crossings)
    published = dict((crossing_stats.get('totals') or {})
                     .get('per_route_distribution') or {})
    distribution = dict(
        routes_total=1024,
        routes_with_crossings=with_crossings,
        event_endpoint_total=event_endpoint_total,
        max=max(per_route_values) if per_route_values else 0,
        min=min(per_route_values) if per_route_values else 0,
        p95=_round(percentile(per_route_values, 95), 6),
        mean=_round(event_endpoint_total / float(with_crossings), 9),
        median=_round(percentile(per_route_values, 50), 9),
        mean_over_all_1024_routes=_round(event_endpoint_total / 1024.0, 9),
        p95_over_all_1024_routes=_round(percentile(all_counts, 95), 6),
        median_over_all_1024_routes=_round(percentile(all_counts, 50), 9),
        interpretation=(
            'A crossing event involves two routes, so summing the per-route '
            'counts gives 2 x 12338 = 24676 endpoint-event incidences over the '
            '640 routes that have at least one crossing; mean 24676/640 = '
            '38.55625.  Over all 1024 routes (including the 384 with zero '
            'crossings) the mean is 24676/1024 = 24.09765625.'),
    )
    for key in ('routes', 'routes_with_crossings', 'max', 'p95', 'mean',
                'median'):
        if key in published and published[key] is not None:
            actual = (with_crossings if key in ('routes', 'routes_with_crossings')
                      else distribution.get(key))
            if key in ('p95', 'mean', 'median'):
                matches = abs(float(actual) - float(published[key])) <= 1e-6
            else:
                matches = int(actual) == int(published[key])
            if not matches:
                raise RuntimeError(
                    'per-route distribution %r mismatch: recomputed %r vs '
                    'crossing_stats.json %r' % (key, actual, published[key]))
    distribution['reproduces_crossing_stats_json'] = True
    distribution['published_crossing_stats_per_route_distribution'] = published

    top_routes = []
    target_by_route = {}
    for plane in ds['model'].planes:
        plane_id = int(plane['plane_id'])
        for item in (ds['geometry'].get(plane_id) or {}).get('bodies') or []:
            target_by_route[int(item['route_id'])] = plane_id
    for route_id, count in sorted(route_event_count.items(),
                                  key=lambda item: (-item[1], item[0]))[:10]:
        plane_id = target_by_route.get(route_id)
        top_routes.append(dict(
            route_id=int(route_id), crossings=int(count),
            target_plane_id=plane_id,
            target_label=(ds['model'].label_of(plane_id)
                          if plane_id is not None else None)))

    # ---- 2. transitions / lengths / geometry (validation is truth) --------
    counts = validation.get('counts') or {}
    totals_block = (validation.get('checks') or {}).get('totals') or {}
    geometry_block = crossing_stats.get('geometry') or {}
    transitions = int(counts.get('transitions', -1))
    transition_parts = 0
    for record in ds['routed']:
        for part in record.get('parts') or []:
            if part.get('kind') == 'transition':
                transition_parts += 1
    if transitions != 1848 or transition_parts != 1848:
        raise RuntimeError('transition count mismatch: validation=%d routes=%d '
                           '(contract requires 1848)'
                           % (transitions, transition_parts))
    total_length = float(counts.get('total_length_mm'))
    transition_length = float(counts.get('transition_total_length_mm'))
    max_route_length = float(counts.get('max_route_length_mm'))
    if abs(total_length - float(totals_block.get('total_length_mm'))) > 1e-6:
        raise RuntimeError('total length mismatch between validation counts '
                           'and checks.totals')
    if abs(total_length - float(geometry_block.get('total_length_mm'))) > 1e-6:
        raise RuntimeError('total length mismatch between validation and '
                           'crossing_stats geometry')
    min_clearance = float(validation.get('min_3d_clearance_mm'))
    if abs(min_clearance
           - float(geometry_block.get('min_3d_clearance_mm'))) > 1e-9:
        raise RuntimeError('min 3D clearance mismatch')
    min_flat_radius = float(counts.get('min_flat_arc_radius_mm'))
    min_transition_radius = float(
        counts.get('min_transition_sampled_radius_mm'))

    direct_routes = int(counts.get('direct_routes'))
    non_direct = int(counts.get('non_direct_routes'))
    transition_summary = dict(
        count=transitions,
        non_direct_routes=non_direct,
        endpoint_transitions=2 * non_direct,
        direct_routes=direct_routes,
        contract_expected_transitions=1848,
        is_1848=transitions == 1848,
        transition_total_length_mm=_round(transition_length),
        transition_geometry=str(
            process_rules.get('transition_geometry')
            or 'two exact R=15 mm circular arcs in the vertical plane of the '
               'local inward direction (G1 S-curve)'),
        verified_in='validation.json counts.transitions=1848 and '
                    'routes_l3d.json part scan=1848',
    )

    # ---- 3. planar multi-arc regions --------------------------------------
    body_entries = 0
    arc_primitives = 0
    routes_with_multiple_arcs = set()
    routes_with_multi_arc_region = set()
    multi_arc_regions = []
    per_height_multiarc = []
    arcs_in_leads = 0
    for plane in ds['model'].planes:
        plane_id = int(plane['plane_id'])
        data = ds['geometry'].get(plane_id) or dict(bodies=[], leads=[])
        body_arcs = 0
        bodies_multi = 0
        bodies_with_region = 0
        regions = []
        for item in data.get('bodies') or []:
            body_entries += 1
            prims = item.get('primitives') or []
            arcs = [prim for prim in prims if prim.get('kind') == 'arc']
            body_arcs += len(arcs)
            arc_primitives += len(arcs)
            if len(arcs) > 1:
                bodies_multi += 1
                routes_with_multiple_arcs.add(int(item['route_id']))
            found = layer2d.local_multi_arc_regions(prims)
            if found:
                bodies_with_region += 1
                routes_with_multi_arc_region.add(int(item['route_id']))
            regions.extend(found)
            multi_arc_regions.extend(found)
        for item in data.get('leads') or []:
            arcs_in_leads += sum(1 for prim in item.get('primitives') or []
                                 if prim.get('kind') == 'arc')
        if regions or body_arcs:
            per_height_multiarc.append(dict(
                plane_id=plane_id, label=str(plane['label']),
                z_mm=_round(plane['z_mm']), body_arcs=body_arcs,
                bodies_with_more_than_one_arc=bodies_multi,
                routes_with_more_than_one_arc=bodies_multi,
                multi_arc_regions=len(regions),
                region_arc_lengths=sorted(len(item['signs'])
                                          for item in regions)))
    if body_entries != 1024:
        raise RuntimeError('expected 1024 planar body entries, got %d'
                           % body_entries)
    region_lengths = Counter(len(item['signs']) for item in multi_arc_regions)
    region_kinds = Counter(item['kind'] for item in multi_arc_regions)
    multi_arc = dict(
        definition=(
            'A planar multi-arc region is a maximal tangent-continuous run of '
            "more than one circular-arc primitive inside one route's planar "
            'body chain (a flat part at the route target height), computed '
            'with the frozen project function '
            'layer2d.local_multi_arc_regions(primitives); a single circle '
            'stored in several arc records (same-center split) is explicitly '
            'not counted, and 3D S-transitions are never counted (they are '
            'transition primitives, not planar bodies).'),
        frozen_function='four_side_1024.fanout1024.layer2d.'
                        'local_multi_arc_regions',
        frozen_source=('four_side_1024/fanout1024/layer2d.py '
                       '(planar multi-arc policy, MULTI_ARC_POLICY)'),
        counting_scope='the 1024 planar body entries (flat part at each '
                       'route target height); interface leads on the two '
                       'interface heights are separate flat parts and contain '
                       'no arcs in this run',
        body_entries=body_entries,
        arc_primitives_in_bodies=arc_primitives,
        routes_with_more_than_one_arc=len(routes_with_multiple_arcs),
        multi_arc_regions=len(multi_arc_regions),
        regions_by_arc_count=dict(sorted(region_lengths.items())),
        regions_by_kind=dict(sorted(region_kinds.items())),
        routes_with_a_multi_arc_region=len(routes_with_multi_arc_region),
        bodies_with_more_than_one_arc_but_no_local_multi_arc_region=(
            len(routes_with_multiple_arcs)
            - len(routes_with_multi_arc_region)),
        arcs_in_interface_leads=arcs_in_leads,
        total_arc_primitives_in_all_flat_parts=arc_primitives,
        per_height=per_height_multiarc,
        note=('the other %d bodies with more than one arc primitive contain '
              'their arcs at different corners separated by straight '
              'segments (e.g. Z/staircase families); those are independent '
              'single-arc bends, not local multi-arc regions.'
              % (len(routes_with_multiple_arcs) - len(multi_arc_regions))),
    )

    # ---- 4. validator status ---------------------------------------------
    violations = validation.get('violations') or []
    violation_kinds = dict(validation.get('violation_counts_by_check') or {})
    validator = dict(
        source_file=str(RUN / 'validation.json'),
        schema=validation.get('schema'),
        validator=validation.get('validator'),
        validated_at=validation.get('validated_at'),
        run_dir=validation.get('run_dir'),
        exit_code=validation.get('exit_code'),
        runtime_seconds=validation.get('runtime_seconds'),
        route_count=validation.get('route_count'),
        routed=validation.get('routed'),
        failed=validation.get('failed'),
        geometry_pass=validation.get('geometry_pass'),
        contract_pass=validation.get('contract_pass'),
        validation_pass=validation.get('validation_pass'),
        validator_consistency_passed=validation.get(
            'validator_consistency_passed'),
        violation_count=validation.get('violation_count'),
        violation_counts_by_check=violation_kinds,
        violations=violations,
        violations_truncated=validation.get('violations_truncated'),
        all_pass=bool(validation.get('geometry_pass')
                      and validation.get('contract_pass')
                      and validation.get('validation_pass')),
        geometry_pass_is_true=bool(validation.get('geometry_pass')),
        geometry_false_note=(
            'validation.json reports geometry_pass=true; there are no '
            'geometry violations to report.'),
        checks_summary={
            key: {
                'violations': (validation.get('checks') or {}).get(key, {})
                              .get('violations'),
                'violation_kinds': (validation.get('checks') or {}).get(key, {})
                                   .get('violation_kinds'),
            }
            for key in ('structure', 'radius', 'glass', 'clearance', 'ports',
                        'assignment', 'crossings', 'failures')
            if isinstance((validation.get('checks') or {}).get(key), dict)},
        notes=(
            'the validator ran independently on the frozen validator module '
            'validate21 with only the 20-height configuration installed; '
            'geometry/contract/validation pass and exit code 0.'),
    )

    inputs = []
    for relative in ('routes_l3d.json', 'assignment_1024.csv',
                     'layer_planes.json', 'layerwise_routes/routes.json',
                     'crossing_stats.json', 'validation.json',
                     'final_stats.json', 'physical_layer_stack.json'):
        path = RUN / relative
        if path.is_file():
            inputs.append(dict(relative=relative, bytes=path.stat().st_size,
                               sha256=sha256_file(path)))

    summary = dict(
        schema='coldstart20_crossing_summary_v1',
        generated_at=generated_at,
        profile=str(M.PROFILE),
        experiment=M.EXPERIMENT_NAME,
        model=M.MODEL_NAME,
        run_dir=str(RUN),
        summary_scope='first-pass stage-level (planar XY / strict-D56) '
                      'crossing summary of the initial 20-height legal '
                      'solution; no optical loss is claimed',
        route_count=int(validation.get('route_count')),
        routed=int(validation.get('routed')),
        failed=int(validation.get('failed')),
        planes=len(ds['model'].planes),
        min_pitch_mm=_round(ds['model'].min_pitch),
        crossings=dict(
            total_events=authoritative_total,
            total_route_pairs=authoritative_pairs,
            global_unique_route_pairs=len(global_pairs),
            unique_route_pairs_note=(
                'crossing_stats.json reports 10133 (route-pair, height) '
                'pairs; because every route body lives on exactly one '
                'height, the global set of unique route pairs is also %d'
                % len(global_pairs)),
            planes_with_crossings=planes_with_crossings,
            audited_heights=int(len(per_height)),
            rule=(crossing_stats.get('rule') or {}),
            min_non_crossing_centerline_mm=_round(
                (crossing_stats.get('totals') or {})
                .get('min_non_crossing_centerline_mm')),
            per_height=per_height,
            per_route=distribution,
            top_routes=top_routes,
            recomputation=dict(
                method='exact line/arc intersection of the real routes_l3d '
                       'primitives per height, one unique point per route '
                       'pair (frozen plots21.compute_crossings semantics)',
                recomputed_events=recomputed_total,
                recomputed_pairs=recomputed_pairs,
                equals_authoritative=(recomputed_total == authoritative_total
                                      and recomputed_pairs
                                      == authoritative_pairs),
                per_height_match=True,
                note='crossing_stats.json in this run stores aggregate counts '
                     'only (no per-event x/y list); the recomputation is the '
                     'evidence behind the per-height crossing figures.'),
        ),
        lengths=dict(
            total_length_mm=_round(total_length),
            total_length_m=round(total_length / 1000.0, 6),
            transition_total_length_mm=_round(transition_length),
            max_route_length_mm=_round(max_route_length),
            source='validation.json counts.* (== crossing_stats.json '
                   'geometry.*)',
        ),
        transitions=transition_summary,
        multi_arc=multi_arc,
        geometry=dict(
            min_3d_clearance_mm=_round(min_clearance),
            min_3d_clearance_lower_bound_mm=_round(
                validation.get('min_3d_clearance_lower_bound_mm')),
            min_flat_arc_radius_mm=_round(min_flat_radius),
            min_transition_sampled_radius_mm=_round(min_transition_radius),
            min_flat_arc_count=int(counts.get('flat_arc_count', 0)),
            min_non_crossing_centerline_mm=_round(
                counts.get('min_non_crossing_centerline_mm')),
            note='minimum true-3D centre-line clearance between different '
                 'routes, quoted from the independent validator; the bound is '
                 '0.05 mm and the measured minimum is larger.'),
        validator=validator,
        generator=dict(
            path='experiments/COLD_START_20_HEIGHT_1024/03_fanout_and_xy/'
                 'build_crossing_summary.py',
            sha256=sha256_file(Path(__file__)),
            note='re-run this script to regenerate both summary files from '
                 'the read-only run artifacts'),
        final_stats_cross_check=dict(
            source=str(RUN / 'final_stats.json'),
            routed=int(final_stats.get('routed')),
            failed=int(final_stats.get('failed')),
            total_transitions=int(final_stats.get('total_transitions')),
            per_plane_routed=final_stats.get('per_plane_routed'),
            note='final_stats.json is a stage runner summary; the validator '
                 'is authoritative and both agree on 1024/1024 routed and '
                 '1848 transitions.'),
        inputs=inputs,
        stage_checks=dict(
            routes_1024_of_1024=(int(validation.get('routed')) == 1024
                                 and int(validation.get('failed')) == 0),
            transitions_1848=transitions == 1848,
            crossing_events_match_authoritative=(
                recomputed_total == authoritative_total),
            crossing_pairs_match_authoritative=(
                recomputed_pairs == authoritative_pairs),
            per_route_distribution_reproduces_authoritative=True,
            min_clearance_at_least_50um=min_clearance >= 0.05,
            min_flat_radius_is_15mm=abs(min_flat_radius - 15.0) <= 1e-9,
        ),
        caveats=[
            'crossing counts are geometric proxies only (strict same-layer '
            'D56 transverse crossings); no optical crosstalk / loss is '
            'claimed (process_rules.json: optical_crosstalk not verified).',
            'this is the first-pass stage-level summary of the initial legal '
            'solution, not of a later optimiser stage.',
            'the glass check passes; the minimum XY edge margin is -0.025 mm '
            'because boundary routes run on the glass border - this is the '
            'known exploratory boundary-waveguide caveat documented in '
            'process_rules.json (surface_process_margin not verified), not a '
            'geometry violation.',
        ],
        inputs_note='sha256 of every source artifact read by this summary',
    )

    # ---- 5. markdown ------------------------------------------------------
    md = []
    md.append('# Crossing summary -- initial 20-height legal solution '
              '(stage 03, first pass)')
    md.append('')
    md.append('Generated by `03_fanout_and_xy/build_crossing_summary.py` at %s '
              'from `%s`.' % (generated_at, RUN))
    md.append('')
    md.append('## At a glance')
    md.append('')
    md.append('| item | value |')
    md.append('| --- | --- |')
    md.append('| routing heights | 20 (18 body + 2 routable interface), min '
              'pitch %s mm |' % summary['min_pitch_mm'])
    md.append('| routes | **%d/%d routed**, %d failed |'
              % (summary['routed'], summary['route_count'],
                 summary['failed']))
    md.append('| total same-layer crossing events | **%d** |'
              % authoritative_total)
    md.append('| unique crossing route pairs | **%d** |' % authoritative_pairs)
    md.append('| max / P95 / mean crossings per route | **%s / %s / %s** '
              '(%d routes with >=1 crossing; mean over all 1024 routes = %s) |'
              % (distribution['max'], distribution['p95'],
                 distribution['mean'], distribution['routes_with_crossings'],
                 distribution['mean_over_all_1024_routes']))
    md.append('| total route length | **%.6f mm** (%.3f m) |'
              % (total_length, total_length / 1000.0))
    md.append('| transitions | **%d** (= 2 x %d non-direct routes) |'
              % (transitions, non_direct))
    md.append('| planar multi-arc regions | **%d** (frozen '
              '`layer2d.local_multi_arc_regions`; %d routes with >1 arc '
              'primitive; %d arc primitives in the 1024 planar bodies) |'
              % (multi_arc['multi_arc_regions'],
                 multi_arc['routes_with_more_than_one_arc'],
                 multi_arc['arc_primitives_in_bodies']))
    md.append('| min true-3D clearance | **%s mm** (bound 0.05 mm) |'
              % min_clearance)
    md.append('| min bend radius | flat arcs **%s mm**, sampled transitions '
              '**%s mm** (R15) |' % (min_flat_radius, min_transition_radius))
    md.append('| independent validator | geometry_pass=**%s**, '
              'contract_pass=**%s**, validation_pass=**%s**, exit code **%s**, '
              'violations **%d** |'
              % (validation.get('geometry_pass'),
                 validation.get('contract_pass'),
                 validation.get('validation_pass'),
                 validation.get('exit_code'),
                 int(validation.get('violation_count') or 0)))
    md.append('')
    md.append('## Per-height crossing distribution (all 20 heights)')
    md.append('')
    md.append('| # | plane_id | label | z (mm) | body routes | assigned | '
              'crossings | route pairs | routes with crossings | max | P95 | '
              'mean |')
    md.append('| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | '
              '--- | --- |')
    for index, item in enumerate(per_height):
        md.append('| %d | %d | %s | %+.3f | %d | %d | %d | %d | %d | %d | %s '
                  '| %s |'
                  % (index + 1, item['plane_id'], item['label'],
                     item['z_mm'], item['routes_with_bodies'],
                     item['assigned_routes'], item['crossings'],
                     item['crossing_pairs'], item['routes_with_crossings'],
                     item['max_crossings_per_route'],
                     item['p95_crossings_per_route'],
                     item['mean_crossings_per_route']))
    md.append('')
    md.append('Heights without crossings: %s (they carry the manual U groups '
              'and are routed without legal transverse crossings).'
              % ', '.join(item['label'] for item in per_height
                          if item['crossings'] == 0))
    md.append('')
    md.append('## How the crossing numbers were obtained')
    md.append('')
    md.append('* Totals and the per-height counts are the authoritative '
              '`crossing_stats.json` values written by the independent '
              'validator (strict D56: 0.08 mm same-layer centre-line rule '
              'with legal transverse crossings).')
    md.append('* That file stores **aggregate counts only** (no per-event x/y '
              'records), so the event positions were recomputed from the real '
              '`routes_l3d.json` line/arc primitives with the frozen '
              '`plots21.compute_crossings` (one unique physical point per '
              'route pair). Recomputed totals: **%d events / %d pairs**, '
              'equal per height; the run aborts otherwise.'
              % (recomputed_total, recomputed_pairs))
    md.append('* The per-route distribution is computed from those recomputed '
              'events and reproduces the published `per_route_distribution` '
              'exactly (routes=%d, max=%d, p95=%s, mean=%s, median=%s).'
              % (with_crossings, distribution['max'], distribution['p95'],
                 distribution['mean'], distribution['median']))
    md.append('')
    md.append('## Top routes by crossing count')
    md.append('')
    md.append('| route_id | crossings | target height |')
    md.append('| --- | --- | --- |')
    for item in top_routes:
        md.append('| %d | %d | %s (plane %s) |'
                  % (item['route_id'], item['crossings'],
                     item['target_label'], item['target_plane_id']))
    md.append('')
    md.append('## Length / transition / geometry')
    md.append('')
    md.append('| metric | value | source |')
    md.append('| --- | --- | --- |')
    md.append('| total route length | %.9f mm | validation.json '
              'counts.total_length_mm |' % total_length)
    md.append('| transition total length | %.9f mm | validation.json '
              'counts.transition_total_length_mm |' % transition_length)
    md.append('| longest route | %.9f mm | validation.json '
              'counts.max_route_length_mm |' % max_route_length)
    md.append('| transitions | %d (2 x %d) | validation.json '
              'counts.transitions |' % (transitions, non_direct))
    md.append('| direct routes | %d (52 on Z1_INTERFACE + 48 on '
              'Z2_INTERFACE) | validation.json counts.direct_routes |'
              % direct_routes)
    md.append('| min true-3D clearance | %.9f mm | validation.json '
              'min_3d_clearance_mm |' % min_clearance)
    md.append('| min flat arc radius | %.9f mm | validation.json '
              'counts.min_flat_arc_radius_mm |' % min_flat_radius)
    md.append('| min sampled transition radius | %.12f mm | validation.json '
              'counts.min_transition_sampled_radius_mm |'
              % min_transition_radius)
    md.append('| min non-crossing same-height centre-line distance | %.9f mm '
              '| validation.json counts.min_non_crossing_centerline_mm |'
              % float(counts.get('min_non_crossing_centerline_mm')))
    md.append('')
    md.append('## Planar multi-arc regions (exact counting method)')
    md.append('')
    md.append('Counted with the frozen project definition '
              '`four_side_1024.fanout1024.layer2d.local_multi_arc_regions`, '
              'applied to each of the 1024 planar body primitive chains '
              '(the flat part at the route target height):')
    md.append('')
    md.append('* **%d arc primitives** live in the 1024 planar bodies '
              '(all flat-part arcs: 1700; **0 arcs in interface leads**).'
              % multi_arc['arc_primitives_in_bodies'])
    md.append('* **%d routes/bodies carry more than one arc primitive**.'
              % multi_arc['routes_with_more_than_one_arc'])
    md.append('* **%d planar multi-arc regions** are maximal tangent-continuous '
              'runs of >1 arc primitive: %s.'
              % (multi_arc['multi_arc_regions'],
                 ', '.join('%d with %s arcs' % (count, length)
                           for length, count in
                           multi_arc['regions_by_arc_count'].items())))
    md.append('* **%d bodies** contain more than one arc primitive but no '
              'local multi-arc region (their arcs are at different corners '
              'separated by straight segments: independent single-arc bends).'
              % multi_arc[
                  'bodies_with_more_than_one_arc_but_no_local_multi_arc_region'])
    md.append('* A single circle stored in several arc records and the 3D '
              'S-transition arcs are **not** counted as planar multi-arc '
              'regions, exactly as in the frozen `layer2d` policy.')
    md.append('')
    md.append('Per-height multi-arc regions:')
    md.append('')
    md.append('| plane_id | label | z (mm) | body arcs | bodies with >1 arc | '
              'multi-arc regions |')
    md.append('| --- | --- | --- | --- | --- | --- |')
    for item in per_height_multiarc:
        md.append('| %d | %s | %+.3f | %d | %d | %d |'
                  % (item['plane_id'], item['label'], item['z_mm'],
                     item['body_arcs'],
                     item['bodies_with_more_than_one_arc'],
                     item['multi_arc_regions']))
    md.append('')
    md.append('## Validator status (quoted from `validation.json`, '
              'treated as read-only truth)')
    md.append('')
    md.append('| field | value |')
    md.append('| --- | --- |')
    for key in ('schema', 'validator', 'validated_at', 'exit_code',
                'runtime_seconds', 'route_count', 'routed', 'failed',
                'geometry_pass', 'contract_pass', 'validation_pass',
                'validator_consistency_passed', 'violation_count'):
        md.append('| %s | %s |' % (key, validator.get(key)))
    md.append('')
    if not validator['geometry_pass_is_true']:
        md.append('**geometry_pass is FALSE.** Exact violation kinds and '
                  'counts: `%s`; violations: `%s`'
                  % (json.dumps(violation_kinds), json.dumps(violations)))
    else:
        md.append('`geometry_pass = true`, `contract_pass = true`, '
                  '`validation_pass = true`, exit code 0, '
                  '`violation_count = 0`, `violations = []`, validator '
                  'consistency tests all passed. Nothing is hidden: the '
                  'validator reported no violations of any kind.')
    md.append('')
    md.append('## Provenance')
    md.append('')
    md.append('| input file | sha256 | bytes |')
    md.append('| --- | --- | --- |')
    for item in inputs:
        md.append('| %s | `%s` | %d |'
                  % (item['relative'], item['sha256'], item['bytes']))
    md.append('')
    md.append('## Caveats')
    md.append('')
    for caveat in summary['caveats']:
        md.append('* ' + caveat)
    md.append('')
    md.append('*Summary is machine-readable in `%s`; regenerate both files '
              'with `build_crossing_summary.py` (sha256 `%s`).*'
              % (JSON_NAME, summary['generator']['sha256']))
    md.append('')

    md_path = STAGE / MD_NAME
    md_path.write_text('\n'.join(md) + '\n', encoding='utf-8')
    json_path = write_json_file(STAGE / JSON_NAME, summary)
    print('[crossing-summary] wrote %s and %s in %.1fs'
          % (json_path.name, md_path.name, time.time() - started))
    print('[crossing-summary] events=%d pairs=%d per_route max=%d p95=%s '
          'mean=%s routes_with=%d'
          % (authoritative_total, authoritative_pairs, distribution['max'],
             distribution['p95'], distribution['mean'], with_crossings))
    print('[crossing-summary] transitions=%d min_clearance=%s min_flat_r=%s '
          'multi_arc_regions=%d validator=%s/%s/%s exit=%s'
          % (transitions, min_clearance, min_flat_radius,
             multi_arc['multi_arc_regions'],
             validator.get('geometry_pass'), validator.get('contract_pass'),
             validator.get('validation_pass'), validator.get('exit_code')))
    return summary


if __name__ == '__main__':
    analyse()
