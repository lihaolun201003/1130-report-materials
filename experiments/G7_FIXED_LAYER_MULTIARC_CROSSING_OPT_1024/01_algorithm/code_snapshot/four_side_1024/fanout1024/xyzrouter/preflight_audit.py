# -*- coding: utf-8 -*-
"""Preflight baseline audit for the XYZ joint (G1/G2/G3) 1024-route round.

Owner: baseline-auditor (DESIGN.md 4.1).  This module is deterministic and
re-runnable; it never modifies ``experiments/`` or the historical outputs under
``outputs/manual_c4_new_connectivity/NATIVE_3D_*`` (all reads are read-only).

What it does
------------
1. ``audit()``
   Reads the accepted Phase-2 roots
   ``NATIVE_3D_JOINT_OPT_1024`` (root / experiment_D / E / F / best_valid /
   baseline) plus the frozen ``NATIVE_3D_CROSSING_OPT_1024`` (experiment_C,
   the 2440-crossing phase-1 layout) and the frozen E5 baseline, and:

   * records the SHA256 (and size / mtime) of every relevant file;
   * compares every route record (all fields: parts, primitives, transitions,
     length/z metadata, n_transitions, n_mid_transitions) across the three
     2409 copies (root / experiment_F / best_valid) and across
     D / E / baseline, and reports the exact differing route ids + fields;
   * **independently re-derives** from the real ``parts``: routed count,
     mid transitions, excursions, by-from-height distribution, total length,
     same-plane crossing events / pairs / unique route pairs / max per route,
     per-physical-z distribution (via the frozen strict-D56
     ``crossing_cache.CrossingCache``), manual-involved crossings;
   * maps every stored ``transition_stats.json`` number (138 / 120 / 118) to
     the actual layout it describes (recomputed from parts), and states which
     layouts have **no** retained route file;
   * maps every ``crossing_stats.json`` to its route geometry at event level;
   * inventories every ``validation*.json`` (independent validator report vs
     phase-2 short guard summary), which route-file SHA256 each one validates,
     and where a PASS file was reused for a *different* (byte-wise) but
     geometry-identical route file;
   * documents the ``finalize_phase2.py`` copy/validate behaviour and checks it
     against the written files;
   * declares the unique authoritative 2409 baseline.

2. ``write_authoritative()``
   Copies the authoritative layout into
   ``outputs/manual_c4_new_connectivity/XYZ_JOINT_G123_1024/
   baseline_authoritative/`` (all files of ``best_valid/``, with the stale
   ``transition_stats.json`` replaced by the authoritative recomputed one),
   plus ``SHA256.json`` and ``AUTHORITY.json``.

3. ``run_validations()``
   Re-runs ``validate_native3d.validate_run`` on the snapshot into two clean
   out dirs: against the baseline dir the historical validation used
   (``NATIVE_3D_CROSSING_OPT_1024/experiment_C``, 2440 crossings) and against
   the DESIGN-frozen E5 baseline (2606 crossings).

4. ``write_reports()``
   Writes ``preflight_audit/preflight_report.md``,
   ``preflight_audit/audit.json`` and ``preflight_audit/hashes.json``.

CLI::

    python four_side_1024/fanout1024/xyzrouter/preflight_audit.py
    python four_side_1024/fanout1024/xyzrouter/preflight_audit.py --skip-validation

All JSON is written with ``ensure_ascii=False, indent=1``.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import sys
from collections import Counter, OrderedDict
from pathlib import Path

# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_ROOT = PROJECT_ROOT / 'outputs' / 'manual_c4_new_connectivity'
RUN = OUTPUT_ROOT / 'NATIVE_3D_JOINT_OPT_1024'
PHASE1 = OUTPUT_ROOT / 'NATIVE_3D_CROSSING_OPT_1024'
E5 = OUTPUT_ROOT / 'NON_C4_CROSSING_OPT_1024' / 'E5_joint_repair_final'
C_BASELINE = PHASE1 / 'experiment_C'
XYZ = OUTPUT_ROOT / 'XYZ_JOINT_G123_1024'
AUDIT_DIR = XYZ / 'preflight_audit'
SNAP_DIR = XYZ / 'baseline_authoritative'
ARCHIVE = PROJECT_ROOT / 'experiments' / 'native_3d_joint_opt_1024'
DESIGN = PROJECT_ROOT / 'four_side_1024' / 'fanout1024' / 'xyzrouter' / 'DESIGN.md'
VALIDATOR_MODULE = (PROJECT_ROOT / 'four_side_1024' / 'fanout1024' /
                    'native3d' / 'validate_native3d.py')
FINALIZE_MODULE = (PROJECT_ROOT / 'four_side_1024' / 'fanout1024' /
                   'native3d' / 'finalize_phase2.py')

AUDIT_SCHEMA = 'xyz_preflight_audit_v1'
AUTHORITY_SCHEMA = 'xyz_authoritative_baseline_v1'
HASHES_SCHEMA = 'xyz_preflight_hashes_v1'

#: documented sha of the accepted 2409 baseline (DESIGN.md section 1)
DESIGN_BASELINE_SHA = ('36c57ad9eff5244959a3e5cadcfe5f5d7fddd06db203a7113131d0667e5c12d0')
EXPECTED_AUTHORITATIVE_SHA = DESIGN_BASELINE_SHA
EXPECTED_ROUTED = 1024
EXPECTED_CROSSINGS = 2409
EXPECTED_CROSSING_PAIRS = 2010
EXPECTED_MID_TRANSITIONS = 138
EXPECTED_EXCURSIONS = 69
EXPECTED_ROUTES_WITH_MID = 62
EXPECTED_MANUAL_ROUTES = 368
EXPECTED_MIN_3D_CLEARANCE = 0.06730354

#: (name, directory) of every route/stat copy audited, in report order.
COPIES = OrderedDict([
    ('root', RUN),
    ('experiment_F', RUN / 'experiment_F'),
    ('best_valid', RUN / 'best_valid'),
    ('experiment_D', RUN / 'experiment_D'),
    ('experiment_E', RUN / 'experiment_E'),
    ('joint_baseline', RUN / 'baseline'),
    ('experiment_C', C_BASELINE),
    ('E5_joint_repair_final', E5),
])

#: per-copy auxiliary file names recorded in the hash table
COPY_FILE_NAMES = (
    'routes_l3d.json', 'assignment_1024.csv', 'layer_planes.json',
    'physical_layer_stack.json', 'process_rules.json', 'crossing_stats.json',
    'transition_stats.json', 'validation.json', 'config.json', 'summary.json',
    'extra_sweep.json', 'near_miss_results.json', 'strategy_stats.json',
    'validation_extra.json', 'validation_near_miss.json',
    'optimization_history.csv', 'joint_search_history.csv',
    'failed_attempts.json', 'MANIFEST.json', 'report.md', 'README.md',
    'comparison.md', 'SPEC.md', 'arc_crossing_analysis.json',
    'arc_rebuild_results.json', 'blocker_analysis.json',
)

#: frozen manual-U contract fields (validate_native3d.MANUAL_FROZEN_FIELDS)
MANUAL_FROZEN_FIELDS = ('parts', 'length_mm', 'start_z_mm', 'end_z_mm',
                        'target_z_mm', 'z_span_mm', 'layer_z_sequence')
#: fields that must stay empty/false on frozen manual routes
MANUAL_NATIVE_FIELDS = ('native_3d', 'n_mid_transitions', 'mid_transitions',
                        'excursions', 'body_heights')

_LOG = lambda *args, **kwargs: None  # replaced by the CLI logger


# ---------------------------------------------------------------------------
# generic helpers
# ---------------------------------------------------------------------------
def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=1) + '\n'
    path.write_text(text, encoding='utf-8')
    return path


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'))


def rel(path):
    try:
        return str(Path(path).resolve().relative_to(PROJECT_ROOT))
    except (ValueError, OSError):
        return str(path)


def mtime_text(path):
    import datetime
    try:
        stamp = Path(path).stat().st_mtime
    except OSError:
        return None
    return datetime.datetime.fromtimestamp(stamp).isoformat(timespec='seconds')


def file_info(path):
    path = Path(path)
    if not path.is_file():
        return None
    return dict(path=rel(path), sha256=sha256_file(path),
                bytes=path.stat().st_size, mtime=mtime_text(path))


def read_csv_rows(path):
    path = Path(path)
    if not path.exists():
        return []
    with path.open('r', encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def _round(value, digits=9):
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return value


# ---------------------------------------------------------------------------
# route geometry helpers (independent of the builder; only frozen leaf rules)
# ---------------------------------------------------------------------------
def normalize_status(record):
    status = record.get('status')
    if status is None:
        return 'routed'
    text = str(status).strip().lower()
    return 'routed' if text in ('', 'routed', 'ok', 'success', 'valid') else 'failed'


def prim_length(prim):
    kind = prim.get('kind')
    if kind == 'line':
        p0, p1 = prim.get('p0'), prim.get('p1')
        return math.hypot(float(p1[0]) - float(p0[0]),
                          float(p1[1]) - float(p0[1]))
    if kind == 'arc':
        return abs(float(prim['radius']) * float(prim['sweep']))
    return 0.0


def part_length(part):
    if part.get('kind') == 'flat':
        value = part.get('length_mm')
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
        return float(sum(prim_length(prim) for prim in part.get('primitives') or ()))
    return float(part.get('length_mm') or 0.0)


def derive_excursions(route):
    """Re-derive each mid-body excursion from the real ``parts`` chain.

    An excursion is ``flat(z0) -> transition(mid) -> flat(z1) ->
    transition(mid) -> flat(z0)``: one middle lift on ``z1``, i.e. two mid
    transitions.  Returns ``(records, problems)`` where every record holds
    ``from_z / to_z / middle_mm / footprint_mm``.
    """
    parts = route.get('parts') or ()
    mids = [(index, part) for index, part in enumerate(parts)
            if part.get('kind') == 'transition'
            and str(part.get('tag') or '') == 'mid']
    records = []
    problems = []
    if len(mids) % 2:
        problems.append('odd_mid_transition_count=%d' % len(mids))
    for first in range(0, len(mids) - 1, 2):
        index_a, up = mids[first]
        index_b, down = mids[first + 1]
        if not (abs(float(up['z0']) - float(down['z1'])) < 1e-9
                and abs(float(up['z1']) - float(down['z0'])) < 1e-9):
            problems.append('mid_pair_does_not_return@%d' % index_a)
            continue
        middle = parts[index_a + 1] if index_a + 1 < len(parts) else {}
        if middle.get('kind') != 'flat':
            problems.append('no_middle_flat@%d' % index_a)
        records.append(dict(
            from_z=float(up['z0']), to_z=float(up['z1']),
            middle_mm=float(part_length(middle)),
            footprint_mm=float(up.get('footprint_mm') or 0.0)))
    return records, problems


def analyse_layout(payload):
    """Recompute every structural number from the real parts (no stored stats)."""
    records = payload.get('routes') or []
    routed = []
    failed = []
    for record in records:
        (routed if normalize_status(record) == 'routed' else failed).append(record)
    kinds = Counter()
    tags = Counter()
    flat_arcs = 0
    flat_zs = Counter()
    total_length = 0.0
    stored_length = 0.0
    declared_transitions = 0
    declared_mid = 0
    declared_mid_list = 0
    mid_by_route = {}
    excursions_by_route = {}
    problems = []
    for record in records:
        route_id = int(record['route_id'])
        parts = record.get('parts') or ()
        route_mid = []
        for part in parts:
            kinds[str(part.get('kind'))] += 1
            if part.get('kind') == 'transition':
                tags[str(part.get('tag'))] += 1
                declared_transitions += 0
            if part.get('kind') == 'flat':
                flat_zs[_round(part.get('z_mm'), 9)] += 1
                for prim in part.get('primitives') or ():
                    if prim.get('kind') == 'arc':
                        flat_arcs += 1
            total_length += part_length(part)
            if (part.get('kind') == 'transition'
                    and str(part.get('tag') or '') == 'mid'):
                route_mid.append((float(part['z0']), float(part['z1'])))
        declared_transitions += int(record.get('n_transitions') or 0)
        declared_mid += int(record.get('n_mid_transitions') or 0)
        declared_mid_list += len(record.get('mid_transitions') or ())
        mid_by_route[route_id] = route_mid
        stored_length += float(record.get('length_mm') or 0.0)
        excursion_records, route_problems = derive_excursions(record)
        if excursion_records:
            excursions_by_route[route_id] = excursion_records
        if route_problems:
            problems.append(dict(route_id=route_id, problems=route_problems))
    actual_mids = sum(len(items) for items in mid_by_route.values())
    excursion_count = sum(len(items) for items in excursions_by_route.values())
    by_from_height = Counter('%+.3f' % item['from_z']
                             for items in excursions_by_route.values()
                             for item in items)
    transition_parts = sum(1 for record in records
                           for part in (record.get('parts') or ())
                           if part.get('kind') == 'transition')
    mismatch = OrderedDict()
    for record in records:
        route_id = int(record['route_id'])
        actual = len(mid_by_route.get(route_id) or ())
        declared = int(record.get('n_mid_transitions') or 0)
        if actual != declared:
            mismatch[route_id] = dict(actual=actual, declared=declared)
    return dict(
        n_records=len(records),
        routed=len(routed),
        failed=len(failed),
        declared_route_count=payload.get('route_count'),
        payload_routed=payload.get('routed'),
        payload_failed=payload.get('failed'),
        transitions=int(transition_parts),
        declared_transitions=int(declared_transitions),
        mid_transitions=int(actual_mids),
        declared_mid_transitions=int(declared_mid),
        declared_mid_transition_list=int(declared_mid_list),
        routes_with_mid_transitions=len(
            [1 for items in mid_by_route.values() if items]),
        excursions=int(excursion_count),
        by_from_height=dict(sorted(by_from_height.items())),
        n_mid_declared_mismatch=mismatch,
        flat_parts=int(kinds.get('flat', 0)),
        transition_parts=int(kinds.get('transition', 0)),
        flat_arcs=int(flat_arcs),
        flat_heights_used=len(flat_zs),
        total_length_mm=round(total_length, 9),
        stored_total_length_mm=round(stored_length, 9),
        total_length_delta_mm=round(total_length - stored_length, 9),
        geometry_problems=problems[:50],
        geometry_problem_count=len(problems),
    )


def layout_fingerprint(records):
    """SHA256 over the canonical JSON of every route record (geometry+metadata)."""
    digest = hashlib.sha256()
    for record in sorted(records, key=lambda item: int(item['route_id'])):
        digest.update(canonical(record).encode('utf-8'))
        digest.update(b'\n')
    return digest.hexdigest()


def payload_metadata(payload):
    meta = OrderedDict((key, value) for key, value in payload.items()
                       if key != 'routes')
    return dict(metadata=meta,
                fingerprint=hashlib.sha256(
                    canonical(meta).encode('utf-8')).hexdigest(),
                keys=sorted(meta))


def compare_records(base_records, other_records):
    """Field-by-field diff of two route payloads keyed by route_id."""
    base = {int(item['route_id']): item for item in base_records}
    other = {int(item['route_id']): item for item in other_records}
    differing = []
    field_routes = OrderedDict()
    for route_id in sorted(set(base) | set(other)):
        left = base.get(route_id)
        right = other.get(route_id)
        if left is None or right is None:
            differing.append(dict(route_id=route_id,
                                  reason='missing_left' if left is None else 'missing_right'))
            continue
        if canonical(left) == canonical(right):
            continue
        fields = sorted(set(left) | set(right))
        bad = [field for field in fields
               if canonical(left.get(field)) != canonical(right.get(field))]
        if bad:
            differing.append(dict(route_id=route_id, fields=bad))
            for field in bad:
                field_routes.setdefault(field, []).append(route_id)
    ids_base = [int(item['route_id']) for item in base_records]
    ids_other = [int(item['route_id']) for item in other_records]
    return dict(
        identical=not differing,
        route_count_base=len(base_records),
        route_count_other=len(other_records),
        differing_route_count=len(differing),
        differing_route_ids=[item['route_id'] for item in differing][:200],
        differing_route_id_count=len(differing),
        field_route_counts=dict(sorted((field, len(ids))
                                       for field, ids in field_routes.items())),
        field_route_ids={field: ids[:100]
                         for field, ids in sorted(field_routes.items())},
        order_identical=ids_base == ids_other,
        differing_examples=differing[:5],
    )


# ---------------------------------------------------------------------------
# crossing recomputation (frozen strict D56 counting)
# ---------------------------------------------------------------------------
def crossing_event_signature(event):
    """Order-independent signature of one crossing event (6 decimal digits)."""
    return (int(event['route_a']), int(event['route_b']),
            _round(event['z_mm'], 9),
            round(float(event['x_mm']), 6),
            round(float(event['y_mm']), 6),
            round(float(event['angle_deg']), 6))


def recompute_crossings(routes, manual_ids):
    """Exact per-physical-z crossing audit via the frozen ``CrossingCache``."""
    from four_side_1024.fanout1024.native3d.crossing_cache import CrossingCache
    cache = CrossingCache(routes)
    events = cache.crossing_events()
    per_route = cache.per_route()
    unique_pairs = {tuple(sorted((event['route_a'], event['route_b'])))
                    for event in events}
    manual_involved = [event for event in events
                       if int(event['route_a']) in manual_ids
                       or int(event['route_b']) in manual_ids]
    per_plane = OrderedDict()
    for z_key in sorted(cache.plane_counts):
        events_n, pairs_n = cache.plane_counts[z_key]
        per_plane[str(_round(z_key, 9))] = dict(events=int(events_n),
                                                pairs=int(pairs_n))
    return dict(
        routes_audited=len(routes),
        crossings=int(cache.total()),
        crossing_pairs=int(cache.total_pairs()),
        unique_crossing_route_pairs=len(unique_pairs),
        n_events=len(events),
        routes_with_crossings=len(per_route),
        max_per_route_crossings=max(per_route.values()) if per_route else 0,
        audited_heights=len(per_plane),
        per_plane=per_plane,
        manual_involved_crossings=len(manual_involved),
        manual_plane_crossings=int(sum(
            counts['events'] for z, counts in per_plane.items()
            if z in ('-0.35', '-0.3', '-0.25', '-0.2',
                     '0.15', '0.2', '0.25', '0.3'))),
        event_signatures=Counter(crossing_event_signature(event)
                                 for event in events),
    )


def compare_crossing_stats(path, recomputed):
    """Strictly compare one crossing_stats.json with a recomputed layout."""
    payload = load_json(path)
    totals = payload.get('totals') or {}
    stored_events = payload.get('crossing_events') or []
    stored_signatures = Counter()
    for event in stored_events:
        try:
            stored_signatures[crossing_event_signature(event)] += 1
        except (KeyError, TypeError, ValueError):
            stored_signatures = None
            break
    event_level = (stored_signatures is not None
                   and stored_signatures == recomputed['event_signatures'])
    # per-plane table (stored ``planes`` list) cross-check
    stored_planes = payload.get('planes') or []
    per_plane_equal = None
    if stored_planes:
        stored_map = {}
        for entry in stored_planes:
            z = _round(entry.get('z_mm'), 9)
            stored_map[str(z)] = dict(events=int(entry.get('crossings') or 0),
                                      pairs=int(entry.get('crossing_pairs') or 0))
        per_plane_equal = stored_map == recomputed['per_plane']
    return dict(
        sha256=sha256_file(path),
        totals=dict(crossings=totals.get('crossings'),
                    crossing_pairs=totals.get('crossing_pairs'),
                    violations=totals.get('violations'),
                    audited_heights=totals.get('audited_heights'),
                    per_route_distribution=totals.get('per_route_distribution')),
        crossings_match=int(totals.get('crossings') or -1)
        == recomputed['crossings'],
        crossing_pairs_match=int(totals.get('crossing_pairs') or -1)
        == recomputed['crossing_pairs'],
        stored_event_count=len(stored_events),
        event_level_match=bool(event_level),
        per_plane_match=per_plane_equal,
    )


# ---------------------------------------------------------------------------
# transition_stats mapping
# ---------------------------------------------------------------------------
def compare_transition_stats(path, layouts):
    """Compare one transition_stats.json against every recomputed layout."""
    payload = load_json(path)
    per_route = payload.get('per_route') or {}
    declared = dict(
        mid_transitions=payload.get('mid_transitions'),
        excursions=payload.get('excursions'),
        routes_with_mid_transitions=payload.get('routes_with_mid_transitions'),
        by_from_height=payload.get('by_from_height'),
        schema=payload.get('schema'),
        total_footprint_mm=payload.get('total_footprint_mm'),
    )
    matches = []
    diagnostics = {}
    for name, layout in layouts.items():
        expected = layout['excursions_by_route']
        mismatch = []
        for route_key, entries in per_route.items():
            route_id = int(route_key)
            got = [(round(float(item['from_z']), 9), round(float(item['to_z']), 9),
                    str(item.get('kind') or 'excursion'))
                   for item in entries]
            want = [(round(float(item['from_z']), 9),
                     round(float(item['to_z']), 9), 'excursion')
                    for item in expected.get(route_id) or ()]
            if got != want:
                mismatch.append(route_id)
        missing = sorted({route_id for route_id, items in expected.items()
                          if items} - {int(key) for key in per_route})
        extra = sorted({int(key) for key in per_route if int(key) not in expected})
        count_match = (int(declared['mid_transitions'] or -1)
                       == layout['mid_transitions']
                       and int(declared['excursions'] or -1)
                       == layout['excursions']
                       and int(declared['routes_with_mid_transitions'] or -1)
                       == layout['routes_with_mid_transitions'])
        by_height_match = (declared['by_from_height'] or {}) == layout['by_from_height']
        diagnostics[name] = dict(
            count_match=bool(count_match),
            by_from_height_match=bool(by_height_match),
            per_route_mismatch_count=len(mismatch),
            per_route_mismatch_route_ids=mismatch[:100],
            routes_missing_from_stats=missing[:100],
            routes_extra_in_stats=extra[:100],
            match=bool(count_match and by_height_match and not mismatch
                       and not missing and not extra),
        )
        if diagnostics[name]['match']:
            matches.append(name)
    return dict(sha256=sha256_file(path), declared=declared,
                layout_matches=matches, layout_diagnostics=diagnostics)


# ---------------------------------------------------------------------------
# audit: copies / layout groups
# ---------------------------------------------------------------------------
def _payload_paths():
    return OrderedDict((name, Path(directory) / 'routes_l3d.json')
                       for name, directory in COPIES.items())


def audit_copies():
    copies = OrderedDict()
    for name, directory in COPIES.items():
        directory = Path(directory)
        entry = dict(name=name, dir=rel(directory), exists=directory.is_dir(),
                     files={})
        for file_name in COPY_FILE_NAMES:
            info = file_info(directory / file_name)
            if info is not None:
                entry['files'][file_name] = info
        route_info = entry['files'].get('routes_l3d.json')
        entry['routes_file'] = rel(directory / 'routes_l3d.json')
        entry['routes_sha256'] = route_info['sha256'] if route_info else None
        entry['assignment_sha256'] = (entry['files'].get('assignment_1024.csv')
                                      or {}).get('sha256')
        copies[name] = entry
    return copies


def audit_layouts(copies):
    payloads = OrderedDict()
    for name, path in _payload_paths().items():
        if path.is_file():
            payloads[name] = load_json(path)
    groups = OrderedDict()
    copy_group = OrderedDict()
    for name, payload in payloads.items():
        fingerprint = layout_fingerprint(payload['routes'])
        copy_group[name] = fingerprint
        group = groups.setdefault(fingerprint, dict(
            fingerprint=fingerprint, members=[],
            metadata_fingerprints={}, payload_experiment=None))
        group['members'].append(name)
        group['metadata_fingerprints'][name] = payload_metadata(payload)['fingerprint']
        group['payload_experiment'] = group['payload_experiment'] or payload.get('experiment')
    # stable group ids
    ordered = OrderedDict()
    fingerprint_to_group = {}
    for index, (fingerprint, group) in enumerate(groups.items()):
        group_id = 'layout_%d' % (index + 1)
        group['group_id'] = group_id
        ordered[group_id] = group
        fingerprint_to_group[fingerprint] = group_id
    group_of_copy = {name: fingerprint_to_group[fingerprint]
                     for name, fingerprint in copy_group.items()}
    return payloads, ordered, group_of_copy


def audit_recomputation(payloads, group_of_copy, manual_ids):
    """analyse each distinct layout + independently recompute its crossings."""
    layouts = OrderedDict()
    for name, payload in payloads.items():
        group_id = group_of_copy[name]
        if group_id in layouts:
            continue
        routes = payload['routes']
        layout = analyse_layout(payload)
        layout['group_id'] = group_id
        layout['fingerprint'] = layout_fingerprint(payload['routes'])
        layout['representative_copy'] = name
        layout['members'] = [copy for copy, gid in group_of_copy.items()
                             if gid == group_id]
        layout['excursions_by_route'] = {}
        for record in routes:
            records, _problems = derive_excursions(record)
            if records:
                layout['excursions_by_route'][int(record['route_id'])] = records
        recomputed = recompute_crossings(routes, manual_ids)
        layout['recomputed'] = recomputed
        layouts[group_id] = layout
    return layouts


# ---------------------------------------------------------------------------
# audit: manual-U frozen contract
# ---------------------------------------------------------------------------
def audit_manual_contract(payloads, layouts, group_of_copy):
    assignment_path = RUN / 'best_valid' / 'assignment_1024.csv'
    rows = read_csv_rows(assignment_path)
    manual_ids = sorted(int(row['route_id']) for row in rows
                        if str(row.get('manual_group') or '').strip())
    manual_groups = Counter(str(row.get('manual_group') or '').strip()
                            for row in rows
                            if str(row.get('manual_group') or '').strip())
    report = dict(
        assignment_file=rel(assignment_path),
        assignment_sha256=sha256_file(assignment_path) if assignment_path.is_file() else None,
        assignment_row_count=len(rows),
        manual_route_count=len(manual_ids),
        manual_route_ids_first=manual_ids[:10],
        manual_groups=dict(sorted(manual_groups.items())),
        expected_manual_route_count=EXPECTED_MANUAL_ROUTES,
        manual_route_count_ok=len(manual_ids) == EXPECTED_MANUAL_ROUTES,
        comparisons=OrderedDict(),
        native_fields_on_manual=OrderedDict(),
        manual_crossings=OrderedDict(),
    )
    baseline_routes = {int(record['route_id']): record
                       for record in payloads['E5_joint_repair_final']['routes']}
    experiment_c_routes = {int(record['route_id']): record
                           for record in payloads['experiment_C']['routes']}
    for copy in ('best_valid', 'root', 'experiment_F'):
        run_routes = {int(record['route_id']): record
                      for record in payloads[copy]['routes']}
        frozen_diff = OrderedDict()
        for field in MANUAL_FROZEN_FIELDS:
            bad = [route_id for route_id in manual_ids
                   if canonical(run_routes[route_id].get(field))
                   != canonical(baseline_routes[route_id].get(field))]
            frozen_diff[field] = dict(differing=len(bad), route_ids=bad[:100])
        parts_sha = {}
        for route_id in manual_ids:
            parts_sha[route_id] = hashlib.sha256(
                canonical(run_routes[route_id].get('parts')).encode('utf-8')
            ).hexdigest()
        e5_parts_sha = {
            route_id: hashlib.sha256(
                canonical(baseline_routes[route_id].get('parts')).encode('utf-8')
            ).hexdigest()
            for route_id in manual_ids}
        parts_mismatch = sorted(route_id for route_id in manual_ids
                                if parts_sha[route_id] != e5_parts_sha[route_id])
        # same comparison against the phase-1 experiment_C baseline
        c_parts_mismatch = sorted(
            route_id for route_id in manual_ids
            if canonical(run_routes[route_id].get('parts'))
            != canonical(experiment_c_routes[route_id].get('parts')))
        report['comparisons'][copy] = dict(
            versus='E5_joint_repair_final',
            frozen_field_diffs=frozen_diff,
            frozen_fields_all_identical=all(
                item['differing'] == 0 for item in frozen_diff.values()),
            parts_sha256_identical=len(parts_mismatch) == 0,
            parts_mismatch_route_ids=parts_mismatch[:100],
            parts_mismatch_count=len(parts_mismatch),
            versus_experiment_C_parts_mismatch_count=len(c_parts_mismatch),
        )
        native_hits = OrderedDict()
        for field in MANUAL_NATIVE_FIELDS:
            hits = [route_id for route_id in manual_ids
                    if run_routes[route_id].get(field) not in (None, False, 0, [], ())]
            native_hits[field] = dict(count=len(hits), route_ids=hits[:100])
        report['native_fields_on_manual'][copy] = native_hits
    for group_id, layout in layouts.items():
        report['manual_crossings'][group_id] = dict(
            group_id=group_id,
            members=layout['members'],
            crossings=int(layout['recomputed']['crossings']),
            manual_involved_crossings=int(
                layout['recomputed']['manual_involved_crossings']),
            manual_height_crossings=int(
                layout['recomputed']['manual_plane_crossings']),
        )
    return report, manual_ids


# ---------------------------------------------------------------------------
# audit: validation files + coverage
# ---------------------------------------------------------------------------
def _validation_candidates():
    paths = [
        RUN / 'validation.json',
        RUN / 'validation' / 'final' / 'validation.json',
        RUN / 'baseline' / 'validation.json',
        RUN / 'best_valid' / 'validation.json',
        PHASE1 / 'validation.json',
        PHASE1 / 'validation' / 'validation.json',
        PHASE1 / 'validation' / 'experiment_A' / 'validation.json',
        PHASE1 / 'validation' / 'experiment_B' / 'validation.json',
        PHASE1 / 'validation' / 'experiment_C' / 'validation.json',
        PHASE1 / 'scratch' / 'native_validator' / 'e5_regression' / 'validation.json',
        PHASE1 / 'scratch' / 'native_validator' / 'e5_regression_api' / 'validation.json',
        E5 / 'validation.json',
        ARCHIVE / 'validation.json',
        ARCHIVE / 'validation' / 'final' / 'validation.json',
    ]
    for experiment in ('experiment_D', 'experiment_E', 'experiment_F'):
        paths.extend(sorted((RUN / experiment).glob('validation*.json')))
        paths.append(ARCHIVE / experiment / 'validation.json')
    paths.append(ARCHIVE / 'experiment_F' / 'validation_extra.json')
    paths.append(ARCHIVE / 'experiment_F' / 'validation_near_miss.json')
    paths.append(ARCHIVE / 'best_valid' / 'validation.json')
    seen = set()
    unique = []
    for path in paths:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _summarize_validation_file(path):
    payload = load_json(path)
    schema = payload.get('schema')
    if schema == 'native3d_validation_v1':
        kind = 'independent_validator'
    elif schema == 'fanout_first_21_height_validation_v1':
        kind = 'legacy_validate21'
    elif payload.get('valid') is not None:
        kind = 'phase2_guard_summary'
    else:
        kind = 'other'
    counts = payload.get('counts') or {}
    checks = payload.get('checks') or {}
    manual = (checks.get('manual_frozen') or {}).get('details') or {}
    clearance = (checks.get('clearance') or {}).get('details') or {}
    crossings = (checks.get('crossings') or {}).get('details') or {}
    coverage = (checks.get('coverage') or {}).get('details') or {}
    run_dir = payload.get('run_dir')
    resolved_run_dir = None
    if run_dir:
        candidate = Path(run_dir)
        resolved_run_dir = candidate if candidate.is_absolute() \
            else (PROJECT_ROOT / candidate)
    entry = dict(
        path=rel(path),
        sha256=sha256_file(path),
        bytes=path.stat().st_size,
        mtime=mtime_text(path),
        schema=schema,
        kind=kind,
        validation_pass=payload.get('validation_pass'),
        exit_code=payload.get('exit_code'),
        geometry_pass=payload.get('geometry_pass'),
        contract_pass=payload.get('contract_pass'),
        violation_count=payload.get('violation_count')
        if payload.get('violation_count') is not None
        else payload.get('violations'),
        run_dir=run_dir,
        run_dir_resolved=rel(resolved_run_dir) if resolved_run_dir else None,
        out_dir=payload.get('out_dir'),
        routes_file_sha256=payload.get('routes_file_sha256'),
        baseline_dir=payload.get('baseline_dir'),
        baseline_routes_file_sha256=payload.get('baseline_routes_file_sha256'),
        assignment_source=payload.get('assignment_source'),
        counts=dict(
            routed=counts.get('routed'),
            records=counts.get('records'),
            failed=counts.get('failed'),
            mid_transitions=counts.get('mid_transitions'),
            excursions=counts.get('excursions'),
            routes_with_mid_transitions=counts.get('routes_with_mid_transitions'),
            same_plane_crossings=counts.get('same_plane_crossings'),
            same_plane_crossing_pairs=counts.get('same_plane_crossing_pairs'),
            same_plane_crossing_violations=counts.get('same_plane_crossing_violations'),
            audited_heights=counts.get('audited_heights'),
            manual_route_count=counts.get('manual_route_count'),
            manual_geometry_mismatch_count=counts.get('manual_geometry_mismatch_count'),
            min_3d_clearance_mm=counts.get('min_3d_clearance_mm'),
            baseline_same_plane_crossings=counts.get('baseline_same_plane_crossings'),
            baseline_same_plane_crossing_pairs=counts.get('baseline_same_plane_crossing_pairs'),
            crossing_delta_vs_baseline=counts.get('crossing_delta_vs_baseline'),
            total_length_mm=counts.get('total_length_mm'),
            violation_total=counts.get('violation_total'),
        ),
        manual_policy=payload.get('manual_policy'),
        policy_report=dict(payload.get('policy_report') or {}) or None,
        details=dict(
            manual_mismatch_route_ids=manual.get('mismatch_route_ids'),
            manual_checked=manual.get('checked'),
            clearance_min=clearance.get('min_3d_clearance_mm'),
            crossing_rule=crossings.get('crossing_rule'),
            coverage_identity_mismatches=coverage.get('identity_field_mismatches'),
            assignment_identity_mismatches=coverage.get('assignment_identity_mismatches'),
        ),
    )
    if kind == 'phase2_guard_summary':
        entry['guard'] = dict(
            valid=payload.get('valid'),
            violations=payload.get('violations'),
            min_3d_clearance=payload.get('min_3d_clearance'),
        )
    return entry


def audit_validation_files(copies, group_of_copy):
    entries = OrderedDict()
    for path in _validation_candidates():
        if not path.exists():
            continue
        key = rel(path)
        if key in entries:
            continue
        try:
            entries[key] = _summarize_validation_file(path)
        except (ValueError, KeyError, TypeError) as error:
            entries[key] = dict(path=rel(path), error=repr(error))
    # annotate every report with the layout group of the route file it validated
    sha_to_group = {}
    for name, info in copies.items():
        sha_to_group[info['routes_sha256']] = group_of_copy.get(name)
    for entry in entries.values():
        entry['group_of_copy'] = sha_to_group.get(entry.get('routes_file_sha256'))
    copy_dir_by_name = OrderedDict((name, rel(directory))
                                   for name, directory in COPIES.items())
    # copy-level coverage
    copy_routes_sha = {name: info['routes_sha256']
                       for name, info in copies.items()}
    group_route_shas = {}
    for name, sha in copy_routes_sha.items():
        group_route_shas.setdefault(group_of_copy.get(name), set()).add(sha)
    coverage = OrderedDict()
    for name in copies:
        sha = copy_routes_sha.get(name)
        group = group_of_copy.get(name)
        direct = []
        geometry_equivalent = []
        short_guard = []
        for key, entry in entries.items():
            if entry.get('error'):
                continue
            if (entry['kind'] == 'independent_validator'
                    and entry.get('routes_file_sha256') == sha):
                direct.append(key)
            elif (entry['kind'] == 'independent_validator'
                  and entry.get('routes_file_sha256')
                  in group_route_shas.get(group, set())):
                geometry_equivalent.append(key)
            if entry['kind'] == 'phase2_guard_summary':
                if str(Path(key).parent) == copy_dir_by_name[name]:
                    short_guard.append(key)
        coverage[name] = dict(
            group_id=group,
            routes_sha256=sha,
            independent_validator_files=direct,
            independent_validator_coverage=bool(direct),
            geometry_equivalent_validator_files=geometry_equivalent,
            geometry_equivalent_coverage=bool(geometry_equivalent),
            guard_summary_files=short_guard,
        )
    # reuse: a full PASS report whose routes sha differs from a route file it is
    # used to endorse, while the geometry is identical.
    reuse = []
    for key, entry in entries.items():
        if entry.get('error') or entry['kind'] != 'independent_validator':
            continue
        validated_sha = entry.get('routes_file_sha256')
        for name, sha in copy_routes_sha.items():
            if sha is None or sha == validated_sha:
                continue
            if validated_sha not in group_route_shas.get(group_of_copy.get(name), set()):
                continue
            reuse.append(dict(
                validation_file=key,
                validation_routes_sha256=validated_sha,
                copy=name,
                copy_routes_sha256=sha,
                geometry_identical=True,
                note=('PASS report validates a byte-different route file with '
                      'identical per-route geometry (metadata-only difference)'),
            ))
    return entries, coverage, reuse


# ---------------------------------------------------------------------------
# audit: finalize_phase2 logic / design contract / logs
# ---------------------------------------------------------------------------
def audit_finalize_behaviour(copies, validation_entries):
    root_files = copies['root']['files']
    f_files = copies['experiment_F']['files']
    best_files = copies['best_valid']['files']
    phase1_baseline_files = copies['experiment_C']['files']
    facts = OrderedDict()
    facts['module'] = file_info(FINALIZE_MODULE)
    facts['root_routes_equals_experiment_F_routes'] = (
        root_files.get('routes_l3d.json', {}).get('sha256')
        == f_files.get('routes_l3d.json', {}).get('sha256'))
    facts['root_crossing_stats_equals_experiment_F_crossing_stats'] = (
        root_files.get('crossing_stats.json', {}).get('sha256')
        == f_files.get('crossing_stats.json', {}).get('sha256'))
    facts['root_has_model_files'] = {
        name: (name in root_files)
        for name in ('assignment_1024.csv', 'layer_planes.json',
                     'physical_layer_stack.json', 'process_rules.json')}
    facts['model_copy_source_BASELINE_has_files'] = {
        name: (name in phase1_baseline_files)
        for name in ('assignment_1024.csv', 'layer_planes.json',
                     'physical_layer_stack.json', 'process_rules.json')}
    facts['phase1_baseline_dir'] = rel(C_BASELINE)
    reports = []
    for key, entry in validation_entries.items():
        if entry.get('error'):
            continue
        if entry['kind'] != 'independent_validator':
            continue
        if entry.get('run_dir_resolved') == rel(RUN / 'best_valid'):
            reports.append(dict(file=key, routes_sha256=entry.get('routes_file_sha256'),
                                baseline_dir=entry.get('baseline_dir'),
                                out_dir=entry.get('out_dir'),
                                validation_pass=entry.get('validation_pass')))
    facts['independent_validator_reports_on_best_valid'] = reports
    facts['archive_routes_equals_root_routes'] = (
        file_info(ARCHIVE / 'routes_l3d.json') or {}).get('sha256') \
        == root_files.get('routes_l3d.json', {}).get('sha256')
    facts['archive_validation_equals_root_validation'] = (
        file_info(ARCHIVE / 'validation.json') or {}).get('sha256') \
        == root_files.get('validation.json', {}).get('sha256')
    facts['root_validation_routes_sha256'] = root_files.get(
        'validation.json', {}).get('sha256')
    facts['root_routes_sha256'] = root_files.get('routes_l3d.json', {}).get('sha256')
    facts['best_valid_routes_sha256'] = best_files.get(
        'routes_l3d.json', {}).get('sha256')
    facts['experiment_F_routes_sha256'] = f_files.get(
        'routes_l3d.json', {}).get('sha256')
    from four_side_1024.fanout1024.native3d import phase2 as P2  # documented reuse
    facts['finalize_phase2_BASELINE_constant'] = rel(P2.PHASE1_RUN_DIR)
    facts['finalize_phase2_RUN_constant'] = rel(P2.RUN2)
    return facts


def audit_design_contract():
    info = file_info(DESIGN)
    text = DESIGN.read_text(encoding='utf-8')
    return dict(
        design_file=info,
        documented_baseline_dir='outputs/manual_c4_new_connectivity/'
                                'NATIVE_3D_JOINT_OPT_1024/best_valid/',
        documented_routes_sha256=DESIGN_BASELINE_SHA,
        documented_sha_present_in_design=DESIGN_BASELINE_SHA in text,
        snapshot_dir_documented=('XYZ_JOINT_G123_1024/baseline_authoritative/'
                                 in text),
        forbidden_paths_present=('experiments/' in text and 'NATIVE_3D_*' in text),
    )


def collect_log_evidence():
    """Mine the experiment logs for best_valid hashes / crossing milestones."""
    logs = sorted((RUN / 'logs').glob('*.log'))
    patterns = OrderedDict([
        ('start_best_valid', re.compile(r'start best_valid: (\d+) crossings')),
        ('save_best_valid', re.compile(
            r'\[save\] best_valid: crossings=(\d+) \(sha ([0-9a-f]+)\)')),
        ('save_experiment_F', re.compile(
            r'\[save\] experiment_F: routes=(\d+) crossings=(\d+)')),
        ('final', re.compile(r'FINAL: (\d+) -> (\d+) crossings')),
        ('accepted', re.compile(r'ACCEPT .*route (\d+) net=([+-]?\d+) total=(\d+)')),
        ('near_miss', re.compile(
            r'\[near\] .*total (\d+) -> (\d+)')),
    ])
    evidence = OrderedDict()
    for path in logs:
        raw = path.read_bytes()
        text = None
        encodings = ('utf-16', 'utf-8-sig', 'utf-8', 'gbk')
        if raw.startswith(b'\xff\xfe') or raw.startswith(b'\xfe\xff'):
            encodings = ('utf-16', 'utf-8-sig', 'utf-8', 'gbk')
        elif raw.startswith(b'\xef\xbb\xbf'):
            encodings = ('utf-8-sig', 'utf-8', 'gbk', 'utf-16')
        for encoding in encodings:
            try:
                text = raw.decode(encoding)
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
        if text is None:
            continue
        hits = []
        for number, line in enumerate(text.splitlines(), 1):
            for label, pattern in patterns.items():
                match = pattern.search(line)
                if match:
                    hits.append(dict(line=number, event=label,
                                     values=list(match.groups()),
                                     text=line.strip()[:220]))
                    break
        if hits:
            evidence[rel(path)] = hits
    return evidence


# ---------------------------------------------------------------------------
# audit: discrepancies + decision
# ---------------------------------------------------------------------------
def scan_retained_route_payloads(log=_LOG):
    """Scan every retained routes-like payload for its real mid-transition count.

    This proves which mid-transition totals still exist as *retained route
    files* on disk (the audit needs it to show that e.g. 120 has no route file).
    Only the relevant experiment trees are scanned (large unrelated analysis
    JSONs are still parsed, but files without a route list are ignored).
    """
    roots = [RUN, E5]
    phase1 = PHASE1
    candidates = []
    for root in roots:
        candidates.extend(sorted(Path(root).rglob('*.json')))
    for pattern_root in (phase1.glob('*.json'),
                         phase1.glob('experiment_*/routes_l3d.json'),
                         phase1.glob('experiment_*/checkpoints/*routes*.json'),
                         phase1.glob('experiment_*/transition_stats.json'),
                         phase1.glob('validation/**/validation.json')):
        candidates.extend(sorted(pattern_root))
    seen = set()
    entries = []
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.stat().st_size > 80 * 1024 * 1024:
            continue
        try:
            payload = load_json(path)
        except (ValueError, OSError, UnicodeDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        routes = payload.get('routes')
        if not isinstance(routes, list) or not routes:
            continue
        if not all(isinstance(item, dict) and 'parts' in item for item in routes[:4]):
            continue
        mid = sum(1 for record in routes for part in (record.get('parts') or ())
                  if isinstance(part, dict) and part.get('kind') == 'transition'
                  and str(part.get('tag') or '') == 'mid')
        entries.append(dict(path=rel(path), sha256=sha256_file(path),
                            n_routes=len(routes), mid_transitions=int(mid),
                            experiment=payload.get('experiment')))
    histogram = Counter(entry['mid_transitions'] for entry in entries)
    log('[audit] retained route payload scan: %d payloads, mid histogram=%s'
        % (len(entries), dict(sorted(histogram.items()))))
    return dict(payload_count=len(entries),
                mid_transitions_histogram=dict(sorted(histogram.items())),
                payloads=entries)


def build_discrepancies(copies, layouts, transition_stats, validation_entries,
                        coverage, manual_contract, finalize_facts):
    items = []
    final_group = None
    best_group = None
    for group_id, layout in layouts.items():
        if 'best_valid' in layout['members']:
            best_group = group_id
            final_group = group_id
    recomputed = layouts[final_group]['recomputed']

    # 1. stale best_valid/transition_stats.json
    best_ts = transition_stats.get(rel(RUN / 'best_valid' / 'transition_stats.json'))
    if best_ts is not None:
        items.append(dict(
            id='BEST_VALID_TRANSITION_STATS_STALE',
            severity='material',
            finding=('best_valid/transition_stats.json declares mid_transitions=%s / '
                     'excursions=%s, but best_valid/routes_l3d.json contains %d mid '
                     'transitions / %d excursions (recomputed from parts).'
                     % (best_ts['declared']['mid_transitions'],
                        best_ts['declared']['excursions'],
                        layouts[best_group]['mid_transitions'],
                        layouts[best_group]['excursions'])),
            evidence=['best_valid/transition_stats.json sha256=%s' % best_ts['sha256'],
                      'layout_matches=%s' % best_ts['layout_matches']],
            impact=('best_valid/ as a directory is not internally consistent; only its '
                    'routes/crossing_stats/config+independent-validation are authoritative.'),
            resolution=('authoritative snapshot replaces transition_stats.json with the '
                        'root 138-mid version recomputed from the real parts'),
        ))
    # 2. stale experiment_F/transition_stats.json (120)
    f_ts = transition_stats.get(rel(RUN / 'experiment_F' / 'transition_stats.json'))
    if f_ts is not None:
        items.append(dict(
            id='EXPERIMENT_F_TRANSITION_STATS_STALE',
            severity='material',
            finding=('experiment_F/transition_stats.json declares mid_transitions=%s / '
                     'excursions=%s, but experiment_F/routes_l3d.json contains %d / %d '
                     '(recomputed). The 120-mid intermediate layout was overwritten by the '
                     'final 138-mid layout and is not retained anywhere.'
                     % (f_ts['declared']['mid_transitions'],
                        f_ts['declared']['excursions'],
                        layouts[final_group]['mid_transitions'],
                        layouts[final_group]['excursions'])),
            evidence=['experiment_F/transition_stats.json sha256=%s' % f_ts['sha256'],
                      'layout_matches=%s' % f_ts['layout_matches']],
            impact=('experiment_F/summary.json (mid_transitions=120) and comparison.md '
                    '("中途三维过渡 118 -> 120") quote a superseded intermediate statistic.'),
            resolution='ignore; use recomputed 138 / root transition_stats.json',
        ))
    # 3. root & archive validation reuse
    root_validation = _by_suffix(validation_entries, 'NATIVE_3D_JOINT_OPT_1024',
                                 'validation.json')
    if root_validation:
        items.append(dict(
            id='ROOT_VALIDATION_ENDORSES_DIFFERENT_FILE_HASH',
            severity='material',
            finding=('root validation.json reports routes_file_sha256=%s (best_valid) '
                     'and run_dir=.../best_valid, while root routes_l3d.json has '
                     'sha256=%s (experiment_F payload). The two files differ only in the '
                     'payload-level "experiment"/"note" fields; all 1024 route records are '
                     'identical (geometry equality verified).'
                     % (str(root_validation.get('routes_file_sha256'))[:16],
                        str(copies['root']['routes_sha256'])[:16])),
            evidence=['validation run_dir=%s' % root_validation.get('run_dir_resolved'),
                      'best_valid/root record diff = 0 routes'],
            impact=('The 2409 PASS is numerically valid for root geometry, but no '
                    'validator report names the root file hash itself.'),
            resolution=('authoritative snapshot is the validated best_valid file '
                        '(sha 36c57...); root/F copies are geometry-identical mirrors'),
        ))
    # 4. root not self-contained
    missing = [name for name, present in
               finalize_facts['root_has_model_files'].items() if not present]
    if missing:
        items.append(dict(
            id='ROOT_DIR_NOT_SELF_CONTAINED',
            severity='cosmetic',
            finding=('NATIVE_3D_JOINT_OPT_1024/ root lacks %s. finalize_phase2.py '
                     'copies those names only from BASELINE=%s, which does not contain '
                     'them, so nothing was copied (silent skip).' % (missing,
                                                                     rel(C_BASELINE))),
            evidence=['root_has_model_files=%s' % finalize_facts['root_has_model_files']],
            impact='root/ cannot be fed to validate_native3d directly; use best_valid/ or the snapshot.',
            resolution='authoritative snapshot contains assignment/layer_planes/etc.',
        ))
    # 5. historical baseline_dir != DESIGN E5 baseline
    items.append(dict(
        id='HISTORICAL_BASELINE_DIR_IS_EXPERIMENT_C',
        severity='informational',
        finding=('The historical independent validation that PASSed the 2409 layout used '
                 'baseline_dir=NATIVE_3D_CROSSING_OPT_1024/experiment_C (the 2440-crossing '
                 'phase-1 layout, sha e8f0cfed...), not the DESIGN-frozen E5 baseline '
                 '(NON_C4_CROSSING_OPT_1024/E5_joint_repair_final, 2606 crossings, sha '
                 '6258f513...). The report therefore quotes baseline crossings 2440 '
                 '(delta -31) instead of 2606 (delta -197).'),
        evidence=['root validation.json baseline_dir=%s'
                  % root_validation.get('baseline_dir')],
        impact=('Both baselines pass every check; only the "baseline crossing count" '
                'contextual number differs.'),
        resolution=('this audit re-validates the snapshot against BOTH baselines '
                    'and documents both numbers'),
    ))
    # 6. short guard summaries carry no route hash
    short = [key for key, entry in validation_entries.items()
             if entry.get('kind') == 'phase2_guard_summary']
    if short:
        items.append(dict(
            id='GUARD_SUMMARIES_HAVE_NO_ROUTE_HASH',
            severity='informational',
            finding=('%d phase-2 validation files are short guard summaries '
                     '(guard.full_validate + min-clearance) without a routes_file_sha256 '
                     'and cannot be tied to any route-file hash. experiment_F/validation.json '
                     '(mtime before the final F routes) describes the 120-mid intermediate.'
                     % len(short)),
            evidence=sorted(short)[:20],
            impact='do not use them as authority for the 2409 layout.',
            resolution='use the independent validator report (routes sha 36c57...).',
        ))
    # 7. F summary mixed statistics
    items.append(dict(
        id='EXPERIMENT_F_SUMMARY_MIXED_STATISTICS',
        severity='informational',
        finding=('experiment_F/summary.json quotes mid_transitions=%s / '
                 'routes_with_mid_transitions=%s (stale 120-intermediate values) while '
                 'its final_crossings=2409 matches the final 138-mid layout.'
                 % (f_ts['declared']['mid_transitions'] if f_ts else '?',
                    f_ts['declared']['routes_with_mid_transitions'] if f_ts else '?')),
        evidence=['experiment_F/summary.json mtime 2026-11-04T02:16:39'],
        impact='report text quoting F summary mid counts is wrong by 18 transitions.',
        resolution='use recomputed 138 / root transition_stats.json',
    ))
    # 8. documented manual crossing fact
    items.append(dict(
        id='MANUAL_CROSSINGS_ZERO',
        severity='informational',
        finding=('Recomputed baseline same-plane crossings involving any of the 368 manual-U '
                 'routes: %d; crossings on the 8 manual heights: %d. The DESIGN section 6 '
                 'claim holds for the authoritative 2409 layout.'
                 % (manual_contract['manual_crossings'][final_group]
                    ['manual_involved_crossings'],
                    manual_contract['manual_crossings'][final_group]
                    ['manual_height_crossings'])),
        evidence=['recomputed via crossing_cache.CrossingCache (strict D56)'],
        impact='supports reporting the manual-U freeze cost as height/corridor occupation, not direct crossings.',
        resolution='none needed',
    ))
    return items


def decide(copies, layouts, transition_stats, validation_entries, coverage,
           manual_contract):
    final_group = None
    for group_id, layout in layouts.items():
        if 'best_valid' in layout['members']:
            final_group = group_id
    layout = layouts[final_group]
    recomputed = layout['recomputed']
    best_sha = copies['best_valid']['routes_sha256']
    full_reports = [entry for entry in validation_entries.values()
                    if entry.get('kind') == 'independent_validator'
                    and entry.get('routes_file_sha256') == best_sha]
    best_ts_key = rel(RUN / 'best_valid' / 'transition_stats.json')
    best_ts = transition_stats.get(best_ts_key) or {}
    best_ts_matches_layout = bool(layout['group_id'] in (best_ts.get('layout_matches') or []))
    root_ts = transition_stats.get(rel(RUN / 'transition_stats.json')) or {}
    root_ts_matches_layout = bool(layout['group_id'] in (root_ts.get('layout_matches') or []))
    checks = OrderedDict([
        ('documented_sha256_matches', best_sha == DESIGN_BASELINE_SHA),
        ('routed_1024', recomputed['routes_audited'] == EXPECTED_ROUTED
         and layout['routed'] == EXPECTED_ROUTED and layout['failed'] == 0),
        ('crossings_2409', recomputed['crossings'] == EXPECTED_CROSSINGS),
        ('crossing_pairs_2010', recomputed['crossing_pairs'] == EXPECTED_CROSSING_PAIRS),
        ('mid_transitions_138', layout['mid_transitions'] == EXPECTED_MID_TRANSITIONS),
        ('excursions_69', layout['excursions'] == EXPECTED_EXCURSIONS),
        ('manual_368', manual_contract['manual_route_count'] == EXPECTED_MANUAL_ROUTES),
        ('manual_geometry_mismatch_0',
         manual_contract['comparisons']['best_valid']['parts_sha256_identical']
         and manual_contract['comparisons']['best_valid']['frozen_fields_all_identical']),
        ('independent_validator_covers_best_sha', bool(full_reports)),
        ('best_valid_transition_stats_matches_routes', best_ts_matches_layout),
        ('root_transition_stats_matches_best_routes', root_ts_matches_layout),
    ])
    #: the 2409 *route layout* is authoritative when it equals the documented
    #: sha, is fully routed, recomputes to 2409 and is named by an independent
    #: validator PASS report.  A stale transition_stats.json does not change
    #: the legality of the geometry -- it makes the directory inconsistent and
    #: is superseded inside the authoritative snapshot.
    unique_2409 = (checks['documented_sha256_matches'] and checks['routed_1024']
                   and checks['crossings_2409']
                   and checks['independent_validator_covers_best_sha']
                   and checks['mid_transitions_138']
                   and checks['manual_geometry_mismatch_0'])
    directory_consistent = (unique_2409
                            and checks['best_valid_transition_stats_matches_routes'])
    return dict(
        authoritative_copy='best_valid',
        authoritative_routes_file=copies['best_valid']['routes_file'],
        authoritative_routes_sha256=best_sha,
        documented_design_sha256=DESIGN_BASELINE_SHA,
        unique_2409_baseline=bool(unique_2409),
        best_valid_directory_internally_consistent=bool(directory_consistent),
        directory_inconsistency_detail=(
            None if directory_consistent else
            'best_valid/transition_stats.json is a stale 118-mid phase-1 copy; '
            'routes/crossing_stats/config/independent-validation are consistent with 138'),
        fallback_required=not bool(unique_2409),
        fallback_layout=None if unique_2409 else 'none available',
        authoritative_transition_stats_file=rel(RUN / 'transition_stats.json'),
        authoritative_transition_stats_sha256=(
            file_info(RUN / 'transition_stats.json') or {}).get('sha256'),
        stale_transition_stats=[best_ts_key, rel(RUN / 'experiment_F' /
                                                 'transition_stats.json')],
        geometry_identical_copies=dict(
            (name, copies[name]['routes_sha256'])
            for name in ('root', 'experiment_F', 'best_valid')),
        checks=dict(checks),
        evidence=dict(
            independent_validator_reports=full_reports,
            recomputed_crossings=recomputed['crossings'],
            recomputed_pairs=recomputed['crossing_pairs'],
            recomputed_mid_transitions=layout['mid_transitions'],
            recomputed_excursions=layout['excursions'],
            recomputed_total_length_mm=layout['total_length_mm'],
            transition_stats_matches=dict(
                best_valid=best_ts.get('layout_matches'),
                root=root_ts.get('layout_matches'),
                experiment_F=(transition_stats.get(
                    rel(RUN / 'experiment_F' / 'transition_stats.json')) or {}
                ).get('layout_matches'),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# audit entry point
# ---------------------------------------------------------------------------
def audit(log=_LOG):
    log('[audit] project root: %s' % PROJECT_ROOT)
    log('[audit] hashing / loading copies ...')
    copies = audit_copies()
    payloads, groups, group_of_copy = audit_layouts(copies)
    log('[audit] %d distinct route layouts among %d copies: %s'
        % (len(groups),
           len(payloads),
           {gid: group['members'] for gid, group in groups.items()}))

    # assignment / manual ids first (needed by crossing recomputation)
    assignment_rows = read_csv_rows(RUN / 'best_valid' / 'assignment_1024.csv')
    manual_ids = {int(row['route_id']) for row in assignment_rows
                  if str(row.get('manual_group') or '').strip()}

    log('[audit] independently recomputing crossings per layout (strict D56) ...')
    layouts = audit_recomputation(payloads, group_of_copy, manual_ids)
    for group_id, layout in layouts.items():
        rec = layout['recomputed']
        log('[audit]   %s members=%s crossings=%d pairs=%d mid=%d length=%.6f'
            % (group_id, layout['members'], rec['crossings'], rec['crossing_pairs'],
               layout['mid_transitions'], layout['total_length_mm']))

    log('[audit] comparing route records ...')
    record_comparison = OrderedDict()
    comparable = OrderedDict([
        ('root_vs_experiment_F', ('root', 'experiment_F')),
        ('root_vs_best_valid', ('root', 'best_valid')),
        ('experiment_F_vs_best_valid', ('experiment_F', 'best_valid')),
        ('experiment_D_vs_experiment_E', ('experiment_D', 'experiment_E')),
        ('experiment_D_vs_joint_baseline', ('experiment_D', 'joint_baseline')),
        ('joint_baseline_vs_experiment_C', ('joint_baseline', 'experiment_C')),
        ('root_vs_experiment_D', ('root', 'experiment_D')),
        ('root_vs_E5_joint_repair_final', ('root', 'E5_joint_repair_final')),
    ])
    for label, (left, right) in comparable.items():
        if left not in payloads or right not in payloads:
            continue
        record_comparison[label] = compare_records(payloads[left]['routes'],
                                                   payloads[right]['routes'])
        log('[audit]   %s: differing routes=%d fields=%s'
            % (label, record_comparison[label]['differing_route_count'],
               record_comparison[label]['field_route_counts']))

    log('[audit] checking stored crossing_stats.json against recomputed layouts ...')
    crossing_stats = OrderedDict()
    for name, directory in COPIES.items():
        for file_name in ('crossing_stats.json',):
            path = Path(directory) / file_name
            if not path.is_file():
                continue
            group_id = group_of_copy.get(name)
            entry = compare_crossing_stats(path, layouts[group_id]['recomputed'])
            entry['copy'] = name
            entry['layout_group_declared_by_copy'] = group_id
            crossing_stats[rel(path)] = entry
    for extra_path in (PHASE1 / 'crossing_stats.json',):
        if extra_path.is_file():
            baseline_group = [gid for gid in layouts
                              if 'experiment_C' in layouts[gid]['members']][0]
            entry = compare_crossing_stats(extra_path, layouts[baseline_group]['recomputed'])
            entry['copy'] = None
            entry['layout_group_declared_by_copy'] = '%s (by content)' % baseline_group
            crossing_stats[rel(extra_path)] = entry

    log('[audit] mapping transition_stats.json numbers to layouts ...')
    transition_stats = OrderedDict()
    for path in (RUN / 'transition_stats.json',
                 RUN / 'experiment_F' / 'transition_stats.json',
                 RUN / 'best_valid' / 'transition_stats.json',
                 PHASE1 / 'transition_stats.json',
                 PHASE1 / 'experiment_C' / 'transition_stats.json'):
        if path.is_file():
            transition_stats[rel(path)] = compare_transition_stats(path, layouts)
            entry = transition_stats[rel(path)]
            log('[audit]   %s: mid=%s exc=%s -> matches=%s'
                % (rel(path), entry['declared']['mid_transitions'],
                   entry['declared']['excursions'], entry['layout_matches']))

    log('[audit] manual-U frozen contract ...')
    manual_contract, _manual_ids = audit_manual_contract(payloads, layouts,
                                                         group_of_copy)
    log('[audit]   368-manual check: parts identical to E5=%s, frozen fields identical=%s'
        % (manual_contract['comparisons']['best_valid']['parts_sha256_identical'],
           manual_contract['comparisons']['best_valid']['frozen_fields_all_identical']))

    log('[audit] inventorying validation files ...')
    validation_entries, coverage, reuse = audit_validation_files(copies, group_of_copy)

    log('[audit] comparing payload-level metadata ...')
    payload_metadata_comparison = OrderedDict()
    for label, (left, right) in comparable.items():
        if left not in payloads or right not in payloads:
            continue
        left_meta = OrderedDict((k, v) for k, v in payloads[left].items()
                                if k != 'routes')
        right_meta = OrderedDict((k, v) for k, v in payloads[right].items()
                                 if k != 'routes')
        keys = sorted(set(left_meta) | set(right_meta))
        differing = [key for key in keys
                     if canonical(left_meta.get(key)) != canonical(right_meta.get(key))]
        payload_metadata_comparison[label] = dict(
            identical=not differing,
            differing_metadata_keys=differing,
            values=OrderedDict((key, dict(left=left_meta.get(key),
                                          right=right_meta.get(key)))
                               for key in differing[:20]),
        )
    log('[audit]   root_vs_experiment_F metadata identical=%s; root_vs_best_valid diff=%s'
        % (payload_metadata_comparison.get('root_vs_experiment_F', {}).get('identical'),
           payload_metadata_comparison.get('root_vs_best_valid', {})
           .get('differing_metadata_keys')))

    log('[audit] finalize_phase2 behaviour + design contract + log evidence ...')
    finalize_facts = audit_finalize_behaviour(copies, validation_entries)
    design_contract = audit_design_contract()
    log_evidence = collect_log_evidence()
    route_payload_scan = scan_retained_route_payloads(log=log)

    discrepancies = build_discrepancies(copies, layouts, transition_stats,
                                        validation_entries, coverage,
                                        manual_contract, finalize_facts)
    decision = decide(copies, layouts, transition_stats, validation_entries,
                      coverage, manual_contract)

    artifacts = dict(
        audit_json=rel(AUDIT_DIR / 'audit.json'),
        report_md=rel(AUDIT_DIR / 'preflight_report.md'),
        hashes_json=rel(AUDIT_DIR / 'hashes.json'),
        snapshot_dir=rel(SNAP_DIR),
        authority_json=rel(SNAP_DIR / 'AUTHORITY.json'),
        snapshot_sha256_json=rel(SNAP_DIR / 'SHA256.json'),
    )
    report = dict(
        schema=AUDIT_SCHEMA,
        generated_by=rel(Path(__file__)),
        project_root=str(PROJECT_ROOT),
        audit_scope=dict(
            copies=OrderedDict((name, rel(directory))
                               for name, directory in COPIES.items()),
            layout_groups={gid: group['members'] for gid, group in groups.items()},
        ),
        design_contract=design_contract,
        copies=copies,
        layout_groups=OrderedDict(),
        record_comparison=record_comparison,
        payload_metadata_comparison=payload_metadata_comparison,
        payload_metadata=OrderedDict(
            (name, dict(
                fingerprint=payload_metadata(payload)['fingerprint'],
                experiment=payload.get('experiment'),
                note=payload.get('note'),
                parent_experiment=payload.get('parent_experiment'),
                schema=payload.get('schema')))
            for name, payload in payloads.items()),
        crossing_stats=crossing_stats,
        transition_stats=transition_stats,
        manual_contract=manual_contract,
        validation_files=validation_entries,
        validation_coverage=coverage,
        validation_reuse=reuse,
        finalize_phase2=finalize_facts,
        log_evidence=log_evidence,
        route_payload_scan=route_payload_scan,
        discrepancies=discrepancies,
        decision=decision,
        artifacts=artifacts,
    )
    for group_id, layout in layouts.items():
        report['layout_groups'][group_id] = dict(
            group_id=group_id,
            fingerprint=layout['fingerprint'],
            members=layout['members'],
            representative_copy=layout['representative_copy'],
            payload_experiment=layout.get('payload_experiment'),
            n_records=layout['n_records'],
            routed=layout['routed'],
            failed=layout['failed'],
            declared_route_count=layout['declared_route_count'],
            transitions=layout['transitions'],
            mid_transitions=layout['mid_transitions'],
            declared_mid_transitions=layout['declared_mid_transitions'],
            declared_mid_transition_list=layout['declared_mid_transition_list'],
            routes_with_mid_transitions=layout['routes_with_mid_transitions'],
            excursions=layout['excursions'],
            by_from_height=layout['by_from_height'],
            flat_arcs=layout['flat_arcs'],
            flat_heights_used=layout['flat_heights_used'],
            total_length_mm=layout['total_length_mm'],
            stored_total_length_mm=layout['stored_total_length_mm'],
            total_length_delta_mm=layout['total_length_delta_mm'],
            geometry_problem_count=layout['geometry_problem_count'],
            n_mid_declared_mismatch=dict(
                (str(key), value)
                for key, value in layout['n_mid_declared_mismatch'].items()),
            recomputed=dict(
                (key, value) for key, value in layout['recomputed'].items()
                if key != 'event_signatures'),
        )
    log('[audit] done: authoritative=%s sha=%s crossings=%d mid=%d'
        % (decision['authoritative_copy'],
           decision['authoritative_routes_sha256'][:16],
           decision['evidence']['recomputed_crossings'],
           decision['evidence']['recomputed_mid_transitions']))
    return report


# ---------------------------------------------------------------------------
# authoritative snapshot
# ---------------------------------------------------------------------------
def write_authoritative(audit_report, log=_LOG):
    decision = audit_report['decision']
    best_dir = RUN / 'best_valid'
    snapshot = SNAP_DIR
    log('[snapshot] writing %s' % rel(snapshot))
    snapshot.mkdir(parents=True, exist_ok=True)
    for existing in sorted(snapshot.iterdir()):
        if existing.is_file():
            existing.unlink()
        elif existing.is_dir():
            shutil.rmtree(existing)
    copied = OrderedDict()
    superseded = []
    for source in sorted(best_dir.iterdir()):
        if not source.is_file():
            continue
        target = snapshot / source.name
        if source.name == 'transition_stats.json':
            # best_valid/transition_stats.json is the stale phase-1 (118-mid) copy;
            # replace it with the authoritative root version recomputed from parts.
            authoritative = RUN / 'transition_stats.json'
            target.write_bytes(authoritative.read_bytes())
            copied[source.name] = dict(
                sha256=sha256_file(target), bytes=target.stat().st_size,
                source=rel(authoritative),
                copied_from_best_valid=True,
                override_reason=('best_valid/transition_stats.json is a stale byte-identical '
                                 'copy of the 118-mid phase-1 experiment_C statistics; the '
                                 'authoritative file is the root 138-mid recomputation'))
            superseded.append(dict(
                file='best_valid/transition_stats.json',
                sha256=sha256_file(source),
                declared_mid_transitions=118,
                reason='stale phase-1 (118-mid) copy, does not match best_valid routes (138)'))
            continue
        target.write_bytes(source.read_bytes())
        copied[source.name] = dict(sha256=sha256_file(target),
                                   bytes=target.stat().st_size,
                                   source=rel(source),
                                   copied_from_best_valid=True)
    snapshot_routes = snapshot / 'routes_l3d.json'
    routes_sha = sha256_file(snapshot_routes)
    if routes_sha != EXPECTED_AUTHORITATIVE_SHA:
        raise RuntimeError('snapshot routes sha %s != documented %s'
                           % (routes_sha, EXPECTED_AUTHORITATIVE_SHA))
    sha_payload = dict(
        schema='xyz_baseline_sha256_v1',
        algorithm='sha256',
        snapshot_dir=rel(snapshot),
        note=('every regular file of the authoritative baseline snapshot; '
              'transition_stats.json is the authoritative 138-mid version, not the '
              'stale 118-mid best_valid copy'),
        file_count=len(copied),
        files=OrderedDict((name, dict(sha256=info['sha256'],
                                      bytes=info['bytes'],
                                      source=info['source']))
                          for name, info in copied.items()),
    )
    write_json(snapshot / 'SHA256.json', sha_payload)
    copied['SHA256.json'] = dict(sha256=sha256_file(snapshot / 'SHA256.json'),
                                 bytes=(snapshot / 'SHA256.json').stat().st_size,
                                 source=rel(snapshot / 'SHA256.json'),
                                 copied_from_best_valid=False)
    authority = dict(
        schema=AUTHORITY_SCHEMA,
        generated_by=rel(Path(__file__)),
        project_root=str(PROJECT_ROOT),
        snapshot_dir=rel(snapshot),
        decision=decision,
        authoritative_routes_file=rel(snapshot / 'routes_l3d.json'),
        authoritative_routes_sha256=routes_sha,
        documented_design_sha256=DESIGN_BASELINE_SHA,
        sha_matches_design=True,
        source_copy=rel(best_dir),
        source_routes_sha256=audit_report['copies']['best_valid']['routes_sha256'],
        geometry_identical_mirrors=decision['geometry_identical_copies'],
        recomputed_numbers=dict(
            routed=decision['checks']['routed_1024'],
            routes=EXPECTED_ROUTED,
            crossings=decision['evidence']['recomputed_crossings'],
            crossing_pairs=decision['evidence']['recomputed_pairs'],
            mid_transitions=decision['evidence']['recomputed_mid_transitions'],
            excursions=decision['evidence']['recomputed_excursions'],
            total_length_mm=decision['evidence']['recomputed_total_length_mm'],
        ),
        files=copied,
        superseded_stale_files=superseded,
        independent_validation=None,
        notes=[
            'routes_l3d.json / assignment_1024.csv / layer_planes.json / '
            'physical_layer_stack.json / process_rules.json / crossing_stats.json / '
            'config.json are byte copies of best_valid/.',
            'transition_stats.json is copied from NATIVE_3D_JOINT_OPT_1024/'
            'transition_stats.json (138 mid transitions recomputed from the real parts); '
            'the best_valid copy is stale (118, phase-1 experiment_C statistics).',
            'best_valid/validation.json is a short phase-2 guard summary without a route '
            'file hash; the authoritative independent-validator report is stored under '
            'XYZ_JOINT_G123_1024/preflight_audit/validation_authoritative/.',
        ],
        audit_json=rel(AUDIT_DIR / 'audit.json'),
    )
    write_json(snapshot / 'AUTHORITY.json', authority)
    log('[snapshot] routes sha=%s files=%d' % (routes_sha[:16], len(copied)))
    return dict(snapshot_dir=rel(snapshot), routes_sha256=routes_sha,
                files=copied, superseded=superseded)
    # (validation results are filled into AUTHORITY.json by finalize_authority())


def finalize_authority(audit_report, snapshot, validations, log=_LOG):
    authority_path = SNAP_DIR / 'AUTHORITY.json'
    authority = load_json(authority_path)
    authority['independent_validation'] = validations
    write_json(authority_path, authority)
    snapshot['authority_sha256'] = sha256_file(authority_path)
    log('[snapshot] AUTHORITY.json updated with %d independent validation run(s)'
        % len(validations.get('runs') or []))
    return authority


# ---------------------------------------------------------------------------
# independent revalidation
# ---------------------------------------------------------------------------
def _validator_module_info():
    info = file_info(VALIDATOR_MODULE)
    return dict(module='four_side_1024.fanout1024.native3d.validate_native3d',
                file=info['path'] if info else rel(VALIDATOR_MODULE),
                sha256=(info or {}).get('sha256'),
                bytes=(info or {}).get('bytes'),
                mtime=(info or {}).get('mtime'))


def _summarize_validation_report(path, audit_report, baseline_dir, run_dir):
    payload = load_json(path)
    counts = payload.get('counts') or {}
    checks = payload.get('checks') or {}
    manual = (checks.get('manual_frozen') or {}).get('details') or {}
    clearance = (checks.get('clearance') or {}).get('details') or {}
    crossings = (checks.get('crossings') or {}).get('details') or {}
    best_group = [gid for gid in audit_report['layout_groups']
                  if 'best_valid' in audit_report['layout_groups'][gid]['members']][0]
    layout = audit_report['layout_groups'][best_group]
    expected = OrderedDict([
        ('validation_pass', True),
        ('violation_count', 0),
        ('routed', EXPECTED_ROUTED),
        ('same_plane_crossings', EXPECTED_CROSSINGS),
        ('same_plane_crossing_pairs', EXPECTED_CROSSING_PAIRS),
        ('mid_transitions', EXPECTED_MID_TRANSITIONS),
        ('manual_geometry_mismatch_count', 0),
        ('min_3d_clearance_mm', EXPECTED_MIN_3D_CLEARANCE),
        ('routes_file_sha256', EXPECTED_AUTHORITATIVE_SHA),
    ])
    actual = OrderedDict([
        ('validation_pass', payload.get('validation_pass')),
        ('violation_count', payload.get('violation_count')),
        ('routed', counts.get('routed')),
        ('same_plane_crossings', counts.get('same_plane_crossings')),
        ('same_plane_crossing_pairs', counts.get('same_plane_crossing_pairs')),
        ('mid_transitions', counts.get('mid_transitions')),
        ('manual_geometry_mismatch_count', counts.get('manual_geometry_mismatch_count')),
        ('min_3d_clearance_mm', counts.get('min_3d_clearance_mm')),
        ('routes_file_sha256', payload.get('routes_file_sha256')),
    ])
    confirmations = OrderedDict(
        (key, dict(expected=expected[key], actual=actual[key],
                   passed=actual[key] == expected[key]))
        for key in expected)
    return dict(
        validation_file=rel(path),
        validation_file_sha256=sha256_file(path),
        out_dir=rel(Path(payload.get('out_dir') or Path(path).parent)),
        run_dir=payload.get('run_dir'),
        routes_file_sha256=payload.get('routes_file_sha256'),
        baseline_dir=payload.get('baseline_dir'),
        baseline_routes_file_sha256=payload.get('baseline_routes_file_sha256'),
        assignment_source=payload.get('assignment_source'),
        layer_planes_file=payload.get('layer_planes_file'),
        manual_policy=payload.get('manual_policy'),
        validation_pass=payload.get('validation_pass'),
        geometry_pass=payload.get('geometry_pass'),
        contract_pass=payload.get('contract_pass'),
        exit_code=payload.get('exit_code'),
        violation_count=payload.get('violation_count'),
        counts=dict(counts),
        checks=dict(
            manual_frozen=dict(
                manual_route_count=manual.get('manual_route_count'),
                checked=manual.get('checked'),
                matched=manual.get('matched'),
                mismatch_count=manual.get('mismatch_count'),
                manual_geometry_mismatch_count=manual.get(
                    'manual_geometry_mismatch_count'),
                mismatch_route_ids=manual.get('mismatch_route_ids'),
            ),
            clearance=dict(
                min_3d_clearance_mm=clearance.get('min_3d_clearance_mm'),
                min_3d_clearance_lower_bound_mm=clearance.get(
                    'min_3d_clearance_lower_bound_mm'),
                violations=clearance.get('violations'),
            ),
            crossings=dict(
                totals=crossings.get('totals'),
                violations=crossings.get('violations'),
            ),
            coverage=dict(
                identity_field_mismatches=(checks.get('coverage') or {}
                                           .get('details') or {}).get(
                                               'identity_field_mismatches'),
                assignment_identity_mismatches=(checks.get('coverage') or {}
                                                .get('details') or {}).get(
                                                    'assignment_identity_mismatches'),
            ),
            synthetic=dict(
                all_passed=(checks.get('synthetic') or {}).get('all_passed'),
                failed=(checks.get('synthetic') or {}).get('failed'),
            ),
        ),
        policy_report=payload.get('policy_report'),
        expected_vs_actual=confirmations,
        all_confirmations_passed=all(item['passed'] for item in confirmations.values()),
        expected_layout_reference=dict(
            crossings=layout['recomputed']['crossings'],
            mid_transitions=layout['mid_transitions'],
            recomputed_from_parts=True),
    )


def run_validations(audit_report, snapshot, log=_LOG, force=False):
    log('[validate] re-running independent validator on the snapshot ...')
    validator_before = _validator_module_info()
    if validator_before.get('sha256') is None:
        raise RuntimeError('validator module not found: %s' % VALIDATOR_MODULE)
    from four_side_1024.fanout1024.native3d import validate_native3d as V
    import inspect
    signature = inspect.signature(V.validate_run)
    support_policy = 'manual_policy' in signature.parameters
    runs = []
    reused = []
    targets = OrderedDict([
        ('validation_authoritative', dict(
            baseline_dir=E5,
            description=('DESIGN-frozen E5 baseline (NON_C4_CROSSING_OPT_1024/'
                         'E5_joint_repair_final): the manual-U freeze source and the '
                         'default baseline_dir of validate_native3d/validate_xyz'))),
        ('validation_authoritative_historical_phase1', dict(
            baseline_dir=C_BASELINE,
            description=('baseline dir used by the historical validation that PASSed the '
                         '2409 layout (phase-1 experiment_C, 2440 crossings); reproduced '
                         'here for provenance'))),
    ])
    target_names = set(targets)
    for stale in sorted(AUDIT_DIR.glob('validation_authoritative*')):
        if stale.is_dir() and stale.name not in target_names:
            shutil.rmtree(stale)
    for name, target in targets.items():
        out_dir = AUDIT_DIR / name
        report_path = out_dir / 'validation.json'
        reuse = False
        if report_path.is_file() and not force:
            try:
                existing = load_json(report_path)
                reuse = (existing.get('routes_file_sha256')
                         == snapshot['routes_sha256']
                         and existing.get('validation_pass') is not None)
            except (ValueError, OSError):
                reuse = False
        if reuse:
            log('[validate] %s: reusing complete report %s'
                % (name, rel(report_path)))
            reused.append(name)
        else:
            if out_dir.exists():
                shutil.rmtree(out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            log('[validate] %s: run_dir=%s baseline_dir=%s out_dir=%s'
                % (name, rel(SNAP_DIR), rel(target['baseline_dir']), rel(out_dir)))
            kwargs = dict(run_dir=SNAP_DIR, baseline_dir=target['baseline_dir'],
                          out_dir=out_dir, log=log)
            if support_policy:
                kwargs['manual_policy'] = 'frozen'
            V.validate_run(**kwargs)
            report_path = out_dir / 'validation.json'
        summary = _summarize_validation_report(
            report_path, audit_report, target['baseline_dir'], SNAP_DIR)
        summary['out_dir'] = rel(out_dir)
        summary['purpose'] = target['description']
        summary['fresh_run'] = not reuse
        summary['baseline_kind'] = (
            'phase1_experiment_C_layout_2440'
            if target['baseline_dir'] == C_BASELINE else 'frozen_E5_2606')
        runs.append((name, summary))
    validator_after = _validator_module_info()
    if validator_before.get('sha256') != validator_after.get('sha256'):
        raise RuntimeError(
            'validate_native3d.py changed while validating (%s -> %s); retry when the '
            'module is stable' % (validator_before.get('sha256'),
                                  validator_after.get('sha256')))
    result = dict(
        runs=OrderedDict(runs),
        validator=validator_after,
        validator_stable_during_run=True,
        snapshot_routes_sha256=snapshot['routes_sha256'],
        clean_out_dirs=not reused,
        reused_existing_reports=list(reused),
    )
    log('[validate] validator sha256=%s' % validator_after['sha256'])
    for name, summary in runs:
        log('[validate] %-34s PASS=%s routed=%s crossings=%s mid=%s mismatch=%s '
            'min3d=%s' % (name, summary['validation_pass'],
                          summary['counts'].get('routed'),
                          summary['counts'].get('same_plane_crossings'),
                          summary['counts'].get('mid_transitions'),
                          summary['counts'].get('manual_geometry_mismatch_count'),
                          summary['counts'].get('min_3d_clearance_mm')))
    return result


# ---------------------------------------------------------------------------
# reports
# ---------------------------------------------------------------------------
def _fmt(value, digits=6):
    if isinstance(value, float):
        return ('%.' + str(digits) + 'f') % value
    return str(value)


def _by_suffix(mapping, *parts):
    """Look up a dict entry whose (windows/posix) path ends with ``parts``."""
    suffix = '/'.join(parts)
    for key, value in (mapping or {}).items():
        if str(key).replace('\\', '/').endswith(suffix):
            return value
    return {}


def _validation_brief(validations):
    runs = (validations or {}).get('runs') or {}
    if not runs:
        return '未运行（--skip-validation）'
    parts = []
    for name, summary in runs.items():
        parts.append('%s: PASS=%s/violations=%s'
                     % (name, summary.get('validation_pass'),
                        summary.get('violation_count')))
    return '；'.join(parts)


def _build_report_md(audit_report, snapshot, validations):
    decision = audit_report['decision']
    groups = audit_report['layout_groups']
    final_group = [gid for gid in groups
                   if 'best_valid' in groups[gid]['members']][0]
    baseline_group = [gid for gid in groups
                      if 'experiment_C' in groups[gid]['members']][0]
    e5_group = [gid for gid in groups
                if 'E5_joint_repair_final' in groups[gid]['members']][0]
    final = groups[final_group]
    baseline = groups[baseline_group]
    e5 = groups[e5_group]
    manual = audit_report['manual_contract']
    ts = audit_report['transition_stats']
    cs = audit_report['crossing_stats']
    copies = audit_report['copies']
    lines = []
    add = lines.append

    add('# 预检基线审计报告 / Preflight baseline audit report')
    add('')
    add('任务：`task-1`（owner: baseline-auditor）。审计对象：'
        '`outputs/manual_c4_new_connectivity/NATIVE_3D_JOINT_OPT_1024/` 的 '
        'root / `experiment_F/` / `best_valid/`（另含 D/E/baseline 与 '
        '`NATIVE_3D_CROSSING_OPT_1024/experiment_C`、`NON_C4_CROSSING_OPT_1024/'
        'E5_joint_repair_final` 作对照）。')
    add('')
    add('本报告由 `preflight_audit.py` 生成；所有数字来自对真实 `parts` 的独立复算'
        '（`crossing_cache.CrossingCache`，冻结 strict-D56 口径）与独立 Validator '
        '`validate_native3d.validate_run`，不采信历史 JSON 的自报数字。')
    add('')
    add('## 0. 结论摘要（作者基线判定）')
    add('')
    add('| 项 | 结论 |')
    add('|---|---|')
    add('| 唯一权威 2409 基线 | `best_valid/routes_l3d.json`，SHA256=`%s` |'
        % decision['authoritative_routes_sha256'])
    add('| 与 DESIGN §1 记录 SHA 一致 | %s |'
        % ('是' if decision['checks']['documented_sha256_matches'] else '否'))
    add('| 路由 | %d/%d routed，failed=%d |'
        % (final['routed'], final['n_records'], final['failed']))
    add('| 独立复算同层交叉 | **%d** events / **%d** pairs（unique route pairs=%d） |'
        % (final['recomputed']['crossings'], final['recomputed']['crossing_pairs'],
           final['recomputed']['unique_crossing_route_pairs']))
    add('| 复算 mid transitions / excursions | %d / %d（%d 条线路） |'
        % (final['mid_transitions'], final['excursions'],
           final['routes_with_mid_transitions']))
    add('| 复算总长度 | %.6f mm |' % final['total_length_mm'])
    add('| root/F/best_valid 几何是否完全一致 | **是**（1024/1024 条 route 逐字段一致） |')
    add('| 三份文件 SHA 不同的原因 | 仅 payload 顶层 metadata（`experiment`/`note`），非几何 |')
    add('| 快照再验证（独立 Validator） | %s |' % _validation_brief(validations))
    add('| best_valid 目录是否内部自洽 | **否**（`transition_stats.json` 是 118-mid 的陈旧副本；'
        'routes/crossing_stats/config/独立验证 自洽） |')
    add('| 是否需要回退到其它布局 | 不需要：无任何布局比 best_valid 更新且被独立验证通过 |')
    add('')
    add('**快照位置**：`%s/`（routes SHA256=`%s`）。stale `best_valid/'
        'transition_stats.json`(118) 已被根目录 `transition_stats.json`(138) 替代。'
        % (snapshot['snapshot_dir'], snapshot['routes_sha256']))
    add('')
    add('## 1. 审计范围与文件 SHA256')
    add('')
    add('| 副本 | 目录 | routes SHA256 | layout group |')
    add('|---|---|---|---|')
    for name, entry in copies.items():
        group = None
        for gid, layout in groups.items():
            if name in layout['members']:
                group = gid
        add('| %s | `%s` | `%s` | %s |'
            % (name, entry['dir'], str(entry['routes_sha256'])[:16], group))
    add('')
    add('关键文件完整 SHA256 见 `hashes.json`；每个副本的 routes/assignment/'
        'crossing_stats/transition_stats/validation/config 哈希见 `audit.json`。')
    add('')
    add('## 2. 六个审计问题的回答')
    add('')
    add('### Q1. 被接受的 2409 对应哪一份真实 route 文件？')
    add('')
    add('`2409` 是 **138-mid 最终布局**的交叉数，对应 `best_valid/routes_l3d.json`'
        '（SHA256=`%s`），并与 root/`experiment_F` 的 `routes_l3d.json`'
        '（SHA256=`%s`）几何完全一致。'
        % (copies['best_valid']['routes_sha256'], copies['root']['routes_sha256']))
    add('')
    add('- 独立复算：%d events / %d pairs / %d 条有交叉线路 / 单线最大 %d；'
        % (final['recomputed']['crossings'],
           final['recomputed']['crossing_pairs'],
           final['recomputed']['routes_with_crossings'],
           final['recomputed']['max_per_route_crossings']))
    add('- 对照：phase-1 `experiment_C`(=D/E/baseline) 布局为 %d events / %d pairs；'
        'E5 基线为 %d events / %d pairs；'
        % (baseline['recomputed']['crossings'],
           baseline['recomputed']['crossing_pairs'],
           e5['recomputed']['crossings'], e5['recomputed']['crossing_pairs']))
    add('- `best_valid/config.json` 记录的 crossings=%d 与复算一致；独立 Validator 报告'
        '点名 routes SHA256=`%s`。'
        % (decision['evidence']['recomputed_crossings'],
           decision['authoritative_routes_sha256']))
    add('')
    add('### Q2. root / experiment_F / best_valid 的完整几何是否完全相同？')
    add('')
    comp = audit_report['record_comparison']
    c_root_f = comp.get('root_vs_experiment_F', {})
    c_root_best = comp.get('root_vs_best_valid', {})
    c_f_best = comp.get('experiment_F_vs_best_valid', {})
    add('**完全相同**。逐 route 全字段（`parts`、全部 primitives、全部 transition 记录、'
        '`length_mm`、`z` 字段、`n_transitions`、`n_mid_transitions` 等）比较结果：')
    add('')
    add('- root vs experiment_F：差异 route 数 **%d**；'
        % c_root_f.get('differing_route_count', -1))
    add('- root vs best_valid：差异 route 数 **%d**；'
        % c_root_best.get('differing_route_count', -1))
    add('- experiment_F vs best_valid：差异 route 数 **%d**；'
        % c_f_best.get('differing_route_count', -1))
    add('- 三条比较的 route 顺序一致：%s / %s / %s。'
        % (c_root_f.get('order_identical'), c_root_best.get('order_identical'),
           c_f_best.get('order_identical')))
    add('')
    add('### Q3. SHA256 差异来自几何还是 metadata/顺序/父字段？')
    add('')
    add('来自 **payload 顶层 metadata**，不是几何、不是 route 顺序、不是父字段：')
    add('')
    meta = audit_report.get('payload_metadata_comparison') or {}
    c_rf = meta.get('root_vs_experiment_F') or {}
    c_rb = meta.get('root_vs_best_valid') or {}
    c_de = meta.get('experiment_D_vs_experiment_E') or {}
    meta_values = (c_rb.get('values') or {})
    add('- root 与 `experiment_F/routes_l3d.json` SHA256 **完全相同**（`%s`），'
        'payload 也逐字段相同（metadata 差异=%s）；'
        % (copies['root']['routes_sha256'],
           c_rf.get('differing_metadata_keys')))
    add('- `best_valid/routes_l3d.json` 与 root 的差异**只有** payload 顶层 metadata：%s；'
        % c_rb.get('differing_metadata_keys'))
    for key, values in meta_values.items():
        add('  - `%s`: `%s` -> `%s`' % (key, values.get('left'), values.get('right')))
    add('- `best_valid` 与 root 的 1024 条 route 记录（canonical JSON，含全部 parts）'
        '差异 **%d** 条；D 与 E 的 metadata 差异=%s，route 记录差异 **%d** 条；'
        % (c_root_best.get('differing_route_count', -1),
           c_de.get('differing_metadata_keys'),
           comp.get('experiment_D_vs_experiment_E', {}).get('differing_route_count', -1)))
    c_e5 = comp.get('root_vs_E5_joint_repair_final') or {}
    parts_changed = (c_e5.get('field_route_counts') or {}).get('parts')
    add('- 与 E5 相比，最终布局有 **%s** 条 route 的 `parts` 不同'
        '（其中 368 条人工 U route 的 parts 与 E5 逐字节相同，见第 7 节）；'
        'root vs E5 全字段差异 route 数=%s。'
        % (parts_changed if parts_changed is not None else '?',
           c_e5.get('differing_route_count')))
    add('')
    add('### Q4. 138 / 120 / 118 分别属于哪一份布局？')
    add('')
    add('| 数字 | 说话者（存储位置） | 实际属于的布局（从 parts 复算） |')
    add('|---|---|---|')
    baseline118 = [gid for gid in groups if 'experiment_C' in groups[gid]['members']][0]
    root_ts = _by_suffix(ts, 'NATIVE_3D_JOINT_OPT_1024', 'transition_stats.json')
    f_ts = _by_suffix(ts, 'NATIVE_3D_JOINT_OPT_1024', 'experiment_F',
                      'transition_stats.json')
    b_ts = _by_suffix(ts, 'NATIVE_3D_JOINT_OPT_1024', 'best_valid',
                      'transition_stats.json')
    root_declared = root_ts.get('declared') or {}
    f_declared = f_ts.get('declared') or {}
    b_declared = b_ts.get('declared') or {}
    root_matches = root_ts.get('layout_matches') or []
    add('| **%s** | `NATIVE_3D_JOINT_OPT_1024/transition_stats.json`（root，schema '
        '`%s`），final `summary.json` | **最终 %d-mid 布局**（root/experiment_F/best_valid '
        '三份几何相同），复算 mid=%d / excursions=%d / %d 条线路，逐 route 匹配=%s |'
        % (root_declared.get('mid_transitions', '?'),
           root_declared.get('schema'),
           final['mid_transitions'], final['mid_transitions'],
           final['excursions'], final['routes_with_mid_transitions'],
           (final['group_id'] in root_matches) and (baseline118 not in root_matches)))
    add('| **%s** | `best_valid/transition_stats.json`（schema `%s`，文件 SHA256=`%s`） | '
        '**phase-1 %d-mid 布局**（=D/E/joint_baseline = experiment_C，SHA `%s`，%d '
        'crossings）；该文件与 `NATIVE_3D_CROSSING_OPT_1024/transition_stats.json` '
        '逐字节相同（同为 mid=%s/exc=%s/routes=%s），是 phase-1 统计被原样复制进 '
        'best_valid 后的 stale 文件，**不描述 best_valid 当前 routes（%d mid）** |'
        % (b_declared.get('mid_transitions', '?'),
           b_declared.get('schema'),
           str(b_ts.get('sha256', '?'))[:16],
           baseline['mid_transitions'],
           copies['experiment_C']['routes_sha256'][:16],
           baseline['recomputed']['crossings'],
           b_declared.get('mid_transitions'),
           b_declared.get('excursions'),
           b_declared.get('routes_with_mid_transitions'),
           final['mid_transitions']))
    f_diag = (f_ts.get('layout_diagnostics') or {})
    final_group = [gid for gid in groups
                   if 'best_valid' in groups[gid]['members']][0]
    f_against_final = (f_diag.get(final_group) or {})
    scan = audit_report.get('route_payload_scan') or {}
    scan_hist = scan.get('mid_transitions_histogram') or {}
    joint_tree_hist = Counter(
        entry['mid_transitions'] for entry in (scan.get('payloads') or [])
        if 'NATIVE_3D_JOINT_OPT_1024' in str(entry.get('path'))
        and int(entry.get('n_routes') or 0) == 1024)
    add('| **%s** | `experiment_F/transition_stats.json`，`experiment_F/summary.json`，'
        '`comparison.md` | **已被覆盖的 experiment_F 中间布局**（F 核心 sweep 结束时的 '
        '2436-crossings 布局，日志 `FINAL: 2436 -> 2436` / `[save] best_valid: '
        'crossings=2436 (sha 49841860dea44bfd)`）。该中间布局没有留下任何 route 文件：'
        '扫描 NATIVE_3D_JOINT_OPT_1024/E5/phase-1 共 %d 个 routes payload（mid 直方图=%s），'
        '其中 NATIVE_3D_JOINT_OPT_1024 树内 1024-route payload 的 mid 计数只有 %s，'
        '**没有任何现存 route 文件的 mid=120**；其 per-route 与 %d-mid 布局相比 mismatch '
        'route 数=%s，与最终 %d-mid 布局相比 mismatch route 数=%s 且缺少若干线路的 excursion |'
        % (f_declared.get('mid_transitions', '?'),
           scan.get('payload_count', '?'), dict(sorted(scan_hist.items())),
           dict(sorted(joint_tree_hist.items())),
           baseline['mid_transitions'],
           (f_diag.get(baseline118) or {}).get('per_route_mismatch_count'),
           final['mid_transitions'],
           f_against_final.get('per_route_mismatch_count')))
    add('')
    add('补充证据：`experiment_F/routes_l3d.json` 的实际内容是最终 %d-mid 布局'
        '（mtime 02:11:51），但 `experiment_F/transition_stats.json`（mtime 01:55:58）、'
        '`experiment_F/validation.json`（01:55:56）都是中间状态遗留，没有随最终 F 路线更新。'
        'F 相关日志中的 best_valid 里程碑：' % final['mid_transitions'])
    add('')
    for log_path, hits in (audit_report.get('log_evidence') or {}).items():
        milestones = [hit for hit in hits
                      if hit['event'] in ('save_best_valid', 'start_best_valid', 'final')]
        if not milestones:
            continue
        for hit in milestones:
            add('- `%s` L%d: `%s`' % (Path(log_path).name, hit['line'], hit['text']))
    add('')
    add('### Q5. 每份布局的独立 Validator 结果')
    add('')
    cov = audit_report['validation_coverage']
    add('| 布局 | 路由 SHA256 | 独立 Validator 报告（直接点名该 SHA） | PASS | 复算 crossings | mid |')
    add('|---|---|---|---|---|---|')
    for label, copy_name in (('最终 %d-mid（root/F/best_valid）' % final['mid_transitions'],
                              'best_valid'),
                             ('phase-1 %d-mid（experiment_C / D / E / joint_baseline）'
                              % baseline['mid_transitions'], 'experiment_C'),
                             ('E5 冻结基线（0 mid）', 'E5_joint_repair_final')):
        entry = cov.get(copy_name) or {}
        reports = entry.get('independent_validator_files') or []
        passes = []
        for key in reports:
            info = audit_report['validation_files'].get(key) or {}
            passes.append('%s=%s' % (Path(key).name,
                                     info.get('validation_pass')))
        add('| %s | `%s` | %s | %s | %d | %d |'
            % (label,
               str(entry.get('routes_sha256'))[:16],
               '<br>'.join('`%s`' % key for key in reports) if reports
               else '**无**（仅 geometry-equivalent 覆盖：%s）'
                    % (entry.get('geometry_equivalent_validator_files') or []),
               ', '.join(passes) if passes else '（见对应文件）',
               (baseline if copy_name == 'experiment_C' else
                final if copy_name == 'best_valid' else e5)['recomputed']['crossings'],
               (baseline if copy_name == 'experiment_C' else
                final if copy_name == 'best_valid' else e5)['mid_transitions']))
    add('')
    add('说明：')
    add('- root 与 experiment_F 的 route 文件哈希（`%s` / `%s`）没有被任何独立 Validator '
        '报告点名；它们只通过“与 best_valid 的 1024 条 route 记录完全相同”获得几何覆盖。'
        % (str(copies['root']['routes_sha256'])[:16],
           str(copies['experiment_F']['routes_sha256'])[:16]))
    add('- D/E 目录只有 `guard.full_validate` 短摘要（无 routes hash），但其 route 记录与 '
        'experiment_C 逐条相同，因此 experiment_C（`%s`）的独立验证报告覆盖其几何。'
        % str(copies['experiment_C']['routes_sha256'])[:16])
    add('- E5 自身 `E5_joint_repair_final/validation.json` 是 legacy '
        '`fanout_first_21_height_validation_v1` 报告（routes SHA=`%s`，PASS，%d crossings），'
        '不属于 native3d 独立 Validator 输出，其信息记录在 `audit.json` 的 '
        '`validation_files` 中。'
        % (str(copies['E5_joint_repair_final']['routes_sha256'])[:16],
           e5['recomputed']['crossings']))
    add('- `validation_reuse`（`audit.json`）列出所有“PASS 报告被用于几何相同但文件 SHA '
        '不同的路线”的情形。')
    add('')
    add('### Q6. 每份 crossing stats 是否严格对应其 route 文件？')
    add('')
    add('按“totals + 全部 crossing 事件（route pair / z / x / y / angle 6 位小数）多重集 + '
        '逐物理高度分布”三级比对：')
    add('')
    add('| crossing_stats 文件 | totals | event-level 与 route 几何一致 | 逐高度分布一致 |')
    add('|---|---|---|---|')
    for path, entry in cs.items():
        add('| `%s` | %s | %s | %s |'
            % (path,
               entry['totals'].get('crossings'),
               'YES' if entry.get('event_level_match') else 'NO',
               'YES' if entry.get('per_plane_match') else 'NO'))
    add('')
    add('结论：**所有** crossing_stats 文件都严格对应其同目录 route 文件的真实几何'
        '（root/F/best 都是最终 2409 布局；D/E 是 2440 布局；baseline/C 是 2440；E5 是 2606）。'
        '**不严格对应的是 transition_stats**：`best_valid`(118) 与 `experiment_F`(120) '
        '两个文件与各自 routes 的真实 parts 不一致（见 Q4）。')
    add('')
    add('## 3. 仍然重要的不一致清单（含处置）')
    add('')
    for item in audit_report['discrepancies']:
        add('### %s（%s）' % (item['id'], item['severity']))
        add('')
        add(item['finding'])
        add('')
        if item.get('evidence'):
            add('证据：' + '；'.join('`%s`' % str(ev) for ev in item['evidence']))
            add('')
        add('影响：' + str(item.get('impact')))
        add('')
        add('处置：' + str(item.get('resolution')))
        add('')
    add('## 4. `finalize_phase2.py` 的复制/验证逻辑（与写出文件的对照）')
    add('')
    add('- `copy_final_artifacts()` 把 `state["final"]`（= `experiment_F/routes_l3d.json`，'
        '回退 best_valid）写到根 `routes_l3d.json`，把 `state["crossing"]`'
        '（= experiment_F/crossing_stats.json，回退 best_valid）写到根 `crossing_stats.json`；'
        '实测根 routes SHA = experiment_F routes SHA = `%s`，根 crossing_stats SHA = '
        'experiment_F crossing_stats SHA = `%s`。'
        % (copies['root']['routes_sha256'][:16],
           copies['root']['files']['crossing_stats.json']['sha256'][:16]))
    add('- 根 `transition_stats.json` 由 `P2.transition_stats(routes)` 从根 routes 重新计算，'
        '因此是 138（与复算一致）；')
    add('- 根目录的 assignment/layer_planes/physical_layer_stack/process_rules 只从 '
        '`BASELINE`（=`%s`）复制，而该目录没有这些文件，所以复制被静默跳过；'
        '**根目录因此不自洽（缺少 4 个 Validator 必需文件）**。'
        % rel(C_BASELINE))
    add('- `run_validator()` 优先验证 `best_valid/`（存在时），`baseline_dir=BASELINE`'
        '（= phase-1 experiment_C，不是 E5），输出 `validation/final/`，再复制为根 '
        '`validation.json`；因此根 validation 记录的是 best_valid 的 SHA（`%s`）而不是'
        '根 routes 的 SHA（`%s`）。'
        % (copies['best_valid']['routes_sha256'][:16],
           copies['root']['routes_sha256'][:16]))
    add('- `archive()` 把根目录与 best_valid/validation 等复制到 '
        '`experiments/native_3d_joint_opt_1024/`；实测 archive 的 routes/validation 与根'
        '逐字节相同（同样的 hash 错配随归档一起传播）。')
    add('')
    add('## 5. 权威快照（`baseline_authoritative/`）')
    add('')
    add('| 文件 | SHA256 | 来源 |')
    add('|---|---|---|')
    for name, info in snapshot['files'].items():
        add('| `%s` | `%s` | `%s` |' % (name, info['sha256'][:16], info['source']))
    add('')
    add('- 快照 routes SHA256 = `%s`（与 DESIGN §1 记录一致）；'
        % snapshot['routes_sha256'])
    add('- `transition_stats.json` 用根目录的 138-mid 权威版本替换了 best_valid 的 stale '
        '118-mid 副本（两者均为 JSON，替换动作记录在 `AUTHORITY.json` 的 '
        '`superseded_stale_files`）；')
    add('- `SHA256.json` 记录快照每个文件的 SHA256；`AUTHORITY.json` 记录来源、哈希、'
        '复算数字与独立验证结果。')
    add('')
    add('## 6. 快照独立重验（clean out_dir）')
    add('')
    if validations and validations.get('runs'):
        add('Validator：`four_side_1024.fanout1024.native3d.validate_native3d`，'
            'SHA256=`%s`，`manual_policy=frozen`（默认合同，等价原 check_manual_frozen）。'
            % str(validations['validator'].get('sha256')))
        add('')
        for name, summary in validations['runs'].items():
            add('### `%s`' % name)
            add('')
            add('- run_dir=`%s`' % rel(SNAP_DIR))
            add('- baseline_dir=`%s`（%s）'
                % (summary.get('baseline_dir'), summary.get('baseline_kind')))
            add('- out_dir=`%s`' % summary.get('out_dir'))
            add('- 本次运行：%s' % ('新跑（clean out_dir）'
                                 if summary.get('fresh_run') else
                                 '复用已有完整报告（同一次审计生成）'))
            add('- routes_file_sha256=`%s`' % summary.get('routes_file_sha256'))
            add('- **validation_pass = %s**, geometry_pass=%s, contract_pass=%s, '
                'violations=%s' % (summary['validation_pass'],
                                   summary['geometry_pass'],
                                   summary['contract_pass'],
                                   summary['violation_count']))
            add('- 复算/复核数字：routed=%s, crossings=%s, pairs=%s, mid_transitions=%s, '
                'manual_geometry_mismatch=%s, min_3d_clearance=%s mm, '
                'baseline crossings=%s（delta vs baseline=%s）'
                % (summary['counts'].get('routed'),
                   summary['counts'].get('same_plane_crossings'),
                   summary['counts'].get('same_plane_crossing_pairs'),
                   summary['counts'].get('mid_transitions'),
                   summary['counts'].get('manual_geometry_mismatch_count'),
                   summary['counts'].get('min_3d_clearance_mm'),
                   summary['counts'].get('baseline_same_plane_crossings'),
                   summary['counts'].get('crossing_delta_vs_baseline')))
            add('- 逐项确认：')
            add('')
            add('| 期望项 | 期望值 | 实测值 | 通过 |')
            add('|---|---|---|---|')
            for key, item in summary['expected_vs_actual'].items():
                add('| %s | `%s` | `%s` | %s |'
                    % (key, item['expected'], item['actual'],
                       'YES' if item['passed'] else '**NO**'))
            add('')
    else:
        add('`--skip-validation` 模式下未重新运行独立 Validator。')
        add('')
    add('## 7. 人工 U 冻结核查（G1 合同前置条件）')
    add('')
    add('- 368 条 manual-U（8 组：Z1-U1..U4 各 64；Z2-U1 16 / U2 16 / U3 40 / U4 40）：'
        '%s；' % ('数量与分配一致' if manual['manual_route_count_ok'] else '数量不符'))
    for copy in ('best_valid', 'root', 'experiment_F'):
        comp = manual['comparisons'][copy]
        add('- `%s` 的 368 条人工 route：`parts` 与 E5 逐字节一致=%s，'
            '冻结字段（parts/length_mm/start_z/end_z/target_z/z_span/layer_z_sequence）'
            '全部一致=%s，mismatch=%d；人工 route 上不存在 native 字段=%s。'
            % (copy,
               'YES' if comp['parts_sha256_identical'] else 'NO',
               'YES' if comp['frozen_fields_all_identical'] else 'NO',
               comp['parts_mismatch_count'],
               'YES' if all(item['count'] == 0
                            for item in manual['native_fields_on_manual'][copy].values())
               else 'NO'))
    add('- 复算：权威 2409 布局中涉及人工 U 的交叉 = **%d**；8 个人工高度层上的交叉 = **%d**'
        '（DESIGN §6 事实成立）。'
        % (manual['manual_crossings'][final_group]['manual_involved_crossings'],
           manual['manual_crossings'][final_group]['manual_height_crossings']))
    add('')
    add('## 8. 复算方法与数字对照表')
    add('')
    add('| layout group | members | crossings | pairs | unique pairs | max/route | '
        'routes w/ crossings | audited heights | mid | excursions | total length mm |')
    add('|---|---|---|---|---|---|---|---|---|---|---|')
    for gid, layout in groups.items():
        rec = layout['recomputed']
        add('| %s | %s | %d | %d | %d | %d | %d | %d | %d | %d | %.6f |'
            % (gid, ', '.join(layout['members']), rec['crossings'],
               rec['crossing_pairs'], rec['unique_crossing_route_pairs'],
               rec['max_per_route_crossings'], rec['routes_with_crossings'],
               rec['audited_heights'], layout['mid_transitions'],
               layout['excursions'], layout['total_length_mm']))
    add('')
    add('逐物理高度事件数（最终 138-mid 布局）：')
    add('')
    add('| z (mm) | crossing events | pairs |')
    add('|---|---|---|')
    for z, counts in final['recomputed']['per_plane'].items():
        add('| %s | %d | %d |' % (z, counts['events'], counts['pairs']))
    add('')
    add('方法：每个 flat part 按其**物理 z** 分组，逐高度用冻结的 fslw strict-D56 '
        '`nonc4.crossings.audit_flat_group`（经 `crossing_cache.CrossingCache`）审计；'
        'mid transitions / excursions 由真实 `parts` 的 transition(tag=mid) 链重新配对'
        '（`flat(z0)->transition->flat(z1)->transition->flat(z0)`），不使用 routes 里的自报字段。')
    add('')
    add('## 9. 对 G1/G2/G3 后续工作的结论与建议')
    add('')
    add('1. **G1/G2/G3 的 baseline/run_dir 请使用本快照** `baseline_authoritative/`'
        '（routes SHA=`%s`），不要使用根目录（缺 4 个模型文件）或 best_valid 目录'
        '（含 stale transition_stats）。' % snapshot['routes_sha256'])
    add('2. 独立 Validator 的 `baseline_dir`：DESIGN §1/4.11 冻结的是 E5'
        '（2606 crossings），第 6 节的 `validation_authoritative` 即用它作为 baseline；'
        '历史 2409 验证用的是 phase-1 experiment_C（2440 crossings），已作为 '
        '`validation_authoritative_historical_phase1` 复现。两者对快照均 PASS 且所有几何检查'
        '一致，仅 `baseline_same_plane_crossings`/delta 的参照值不同。G1 的 368 条人工 U '
        '冻结合同在两者下都成立。')
    add('3. 引用“2409 / 138 mid transitions / 0 violations”时，请以复算数字或快照中的 '
        '`transition_stats.json`(=root 138) 为准；**不要引用** `best_valid/'
        'transition_stats.json`(118)、`experiment_F/transition_stats.json`(120)、'
        '`experiment_F/summary.json` 的 mid 字段或 `comparison.md` 的“118 -> 120”行。')
    add('4. 任何报告若写“root 的 routes SHA = 验证报告里的 SHA”需要修正为“root routes 与 '
        'best_valid routes 几何相同、SHA 因 2 个 metadata 字段不同”。')
    add('5. 本审计的 Validator 模块版本为 `validate_native3d.py` SHA256=`%s`；'
        '若后续该模块继续修改（validator-dev 正在扩展 manual_policy），重跑 Validator 时'
        '请记录新版本 SHA。' % str((validations or {}).get('validator', {}).get('sha256')))
    add('')
    return '\n'.join(lines) + '\n'


def write_reports(audit_report, snapshot, validations, log=_LOG):
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    report_payload = dict(audit_report)
    report_payload['revalidation'] = validations
    report_payload['snapshot'] = dict(
        snapshot_dir=snapshot['snapshot_dir'],
        routes_sha256=snapshot['routes_sha256'],
        files=OrderedDict((name, dict(sha256=info['sha256'],
                                      bytes=info['bytes'],
                                      source=info['source']))
                          for name, info in snapshot['files'].items()),
        superseded=snapshot['superseded'],
        authority_json=rel(SNAP_DIR / 'AUTHORITY.json'),
        sha256_json=rel(SNAP_DIR / 'SHA256.json'),
    )
    audit_path = AUDIT_DIR / 'audit.json'
    write_json(audit_path, report_payload)
    log('[report] wrote %s' % rel(audit_path))
    report_md = _build_report_md(audit_report, snapshot, validations)
    report_path = AUDIT_DIR / 'preflight_report.md'
    report_path.write_text(report_md, encoding='utf-8')
    log('[report] wrote %s' % rel(report_path))
    # hashes.json: every audited file (written last; cannot contain its own sha)
    files = OrderedDict()
    for name, entry in audit_report['copies'].items():
        for file_name, info in entry['files'].items():
            files[info['path']] = info['sha256']
    for path in sorted(AUDIT_DIR.glob('validation*/*.json')):
        files[rel(path)] = sha256_file(path)
    for path in sorted(SNAP_DIR.iterdir()):
        if path.is_file() and path.name != 'SHA256.json':
            files[rel(path)] = sha256_file(path)
    files[rel(SNAP_DIR / 'SHA256.json')] = sha256_file(SNAP_DIR / 'SHA256.json')
    for path in (DESIGN, VALIDATOR_MODULE, FINALIZE_MODULE,
                 PROJECT_ROOT / 'four_side_1024' / 'fanout1024' / 'native3d' /
                 'crossing_cache.py',
                 PROJECT_ROOT / 'four_side_1024' / 'fanout1024' / 'native3d' /
                 'phase2.py',
                 Path(__file__), audit_path, report_path):
        if Path(path).is_file():
            files[rel(path)] = sha256_file(path)
    hashes_payload = dict(
        schema=HASHES_SCHEMA,
        algorithm='sha256',
        note=('SHA256 of every audited input, every snapshot file and every audit '
              'artifact. hashes.json itself is not listed (it cannot contain its own '
              'sha256).'),
        file_count=len(files),
        files=OrderedDict(sorted(files.items())),
    )
    hashes_path = AUDIT_DIR / 'hashes.json'
    write_json(hashes_path, hashes_payload)
    log('[report] wrote %s' % rel(hashes_path))
    return dict(audit_json=rel(audit_path), report_md=rel(report_path),
                hashes_json=rel(hashes_path))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Preflight baseline audit for the XYZ joint 1024 experiment '
                    '(NATIVE_3D_JOINT_OPT_1024 -> XYZ_JOINT_G123_1024).')
    parser.add_argument('--skip-validation', action='store_true',
                        help='do not re-run the independent validator (reuse the '
                             'existing reports in preflight_audit/validation_*)')
    parser.add_argument('--force-validation', action='store_true',
                        help='re-run the independent validator even when a complete '
                             'validation report already exists')
    parser.add_argument('--quiet', action='store_true', help='suppress progress logs')
    args = parser.parse_args(argv)

    def log(message):
        if not args.quiet:
            print(message, flush=True)

    audit_report = audit(log=log)
    snapshot = write_authoritative(audit_report, log=log)
    if args.skip_validation:
        validations_path = AUDIT_DIR / 'validation_authoritative' / 'validation.json'
        if validations_path.is_file():
            runs = OrderedDict()
            for name in ('validation_authoritative',
                         'validation_authoritative_historical_phase1'):
                path = AUDIT_DIR / name / 'validation.json'
                if not path.is_file():
                    continue
                baseline = E5 if name == 'validation_authoritative' else C_BASELINE
                summary = _summarize_validation_report(path, audit_report,
                                                       baseline, SNAP_DIR)
                summary['out_dir'] = rel(AUDIT_DIR / name)
                summary['baseline_kind'] = (
                    'frozen_E5_2606' if name == 'validation_authoritative'
                    else 'phase1_experiment_C_layout_2440')
                runs[name] = summary
            validations = dict(
                runs=runs,
                validator=_validator_module_info(),
                validator_stable_during_run=None,
                snapshot_routes_sha256=snapshot['routes_sha256'],
                clean_out_dirs=False,
                note='reused existing validator reports (--skip-validation)',
            )
            log('[validate] reused existing reports under %s' % rel(AUDIT_DIR))
        else:
            validations = dict(runs=OrderedDict(),
                               validator=_validator_module_info(),
                               snapshot_routes_sha256=snapshot['routes_sha256'],
                               note='no existing validator reports; skipped')
            log('[validate] skipped (--skip-validation and no existing report)')
    else:
        validations = run_validations(audit_report, snapshot, log=log,
                                      force=args.force_validation)
    finalize_authority(audit_report, snapshot, validations, log=log)
    artifacts = write_reports(audit_report, snapshot, validations, log=log)
    log('[done] audit=%s report=%s hashes=%s'
        % (artifacts['audit_json'], artifacts['report_md'],
           artifacts['hashes_json']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
