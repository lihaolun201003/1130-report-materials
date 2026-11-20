# -*- coding: utf-8 -*-
"""Final figure suite for the completed 20-height / 1024-route 3D routing run.

The script is **layout-agnostic**: it is driven by one legal-layout run
directory and only reads the frozen JSON artifacts (``routes_l3d.json``,
``crossing_stats.json``, ``layer_planes.json``, ``physical_layer_stack.json``,
``assignment_1024.csv``, ``validation.json``, ``final_stats.json``).  It is
bootstrap-first (the 20-height profile is installed by
:mod:`four_side_1024.fanout1024.coldstart20.bootstrap`), idempotent, and works
on any stage layout of ``experiments/COLD_START_20_HEIGHT_1024/`` -- from the
initial 12338-crossing solution to the native-3D / G-stage refinements.

Figures produced (all PNG, ``matplotlib.use('Agg')``):

``01_layers_all_in_one.png``   all 1024 routes projected in XY, every flat part
                               and transition coloured by its **real physical
                               height z** (20 heights labelled on the
                               colourbar) + a second panel with the route count
                               per height.
``02_3d_global.png``           true 3D (mplot3d) drawing of all 1024 routes as
                               3D polylines (real flats, sampled S-curves), the
                               150x150x1.0 mm glass envelope wireframe, view
                               elevation 30 deg, colour = routing height.
``03_height_profile.png``      per-height occupancy bar chart ordered by z
                               (each route counted once at its body height),
                               plus the authoritative crossing count per height.
``04_crossing_hotspot_zoom.png`` the three densest 20x20 mm same-height XY
                               crossing cells: involved routes, crossing
                               markers, counts and the idle (0-crossing)
                               height list.
``05_multi_arc_examples.png``  three real planar multi-arc routes (2 arcs /
                               3+ arcs / arcs at separate corners) with arc
                               centres and radii annotated, plus the height
                               profile along the path under each.
``06_crossing_curve_vs_stage.png`` 20H stage curve (from
                               ``12_reports/stage_curve_20h.json`` when present,
                               otherwise constructed from the known stage dirs)
                               with the historical 21H reference curve as a
                               separate dashed line (explicitly not a target).
``07_21h_vs_20h.png``          grouped bar comparison of the six reachable
                               stage positions (21H historical vs 20H read from
                               the stage dirs; missing 20H stages are labelled
                               "not run yet", never plotted as zero).
``08_compare_<slug>.png``      only with ``--compare <other layout>``: side by
                               side XY rendering of the two layouts.
``figure_manifest.json``       every file with sha256, source layout, route /
                               crossing numbers, profile, reproduction command.
``README.md``                  human readable description of the same.
``render_timings.json``        wall-clock diagnostic only (NOT part of the
                               deterministic manifest hash set).

Honesty rules implemented here:

* every routed route of the layout is drawn (1024/1024); nothing is filtered,
  down-sampled or deleted.  Only the *drawing resolution* of transitions is
  chosen by the display step (documented per figure);
* crossing **counts** shown in titles / manifest are the authoritative values
  from ``crossing_stats.json``.  The per-event marker positions are recomputed
  from the real line/arc primitives exactly like
  ``plots21.compute_crossings`` (the independent validator semantics) and the
  recomputed totals are verified against the authoritative totals; a mismatch
  is reported as a caveat, never silently averaged away;
* the 21H curve is a historical reference read from the frozen 21H archive
  paths and is labelled as a reference, not a target;
* 20H stages that do not exist yet are reported as "not run yet", never 0.

Usage::

    .venv\\Scripts\\python.exe -m four_side_1024.fanout1024.coldstart20.plot_final ^
        --layout experiments\\COLD_START_20_HEIGHT_1024\\05_native3d_abc\\run_native3d_phase1 ^
        --out-dir experiments\\COLD_START_20_HEIGHT_1024\\11_figures\\test_on_stage05 ^
        --label "stage-05 native-3D phase 1"

    # optional layout comparison
    ... --compare experiments\\COLD_START_20_HEIGHT_1024\\04_initial_3d_and_e5_repair\\nonc4_programme\\E5_joint_repair_final
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import sys
import time
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# the 20-height profile MUST be installed before any pipeline module is used
# ---------------------------------------------------------------------------
from four_side_1024.fanout1024.coldstart20 import bootstrap as B  # noqa: E402
from four_side_1024.fanout1024.coldstart20 import model20 as M20   # noqa: E402
from four_side_1024.fanout1024.coldstart20 import paths20 as P20   # noqa: E402

import matplotlib  # noqa: E402

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Circle, Rectangle  # noqa: E402

from four_side_1024.fanout1024 import layer2d  # noqa: E402
from four_side_1024.fanout1024.reheight21 import plots21 as P  # noqa: E402

HERE = Path(__file__).resolve()
SCRIPT_NAME = 'four_side_1024/fanout1024/coldstart20/plot_final.py'
SCHEMA = 'coldstart20_final_figure_suite_v1'
MANIFEST_NAME = 'figure_manifest.json'
README_NAME = 'README.md'
TIMINGS_NAME = 'render_timings.json'

DPI_DEFAULT = 150
MAX_PNG_BYTES = 8_000_000
BOARD_MM = float(P.BOARD_MM)
CELL_MM = 20.0                     # hotspot cell size required by the task
ZOOM_MM = 40.0                     # hotspot window (2x2 cells, clipped to board)
FLAT_STEP_2D = 0.15                # display sampling of a flat part in 2D
TRANS_STEP_2D = 0.20               # display sampling of an S-curve in 2D
BASE_LW = 0.25
BASE_ALPHA = 0.8

FIGS = OrderedDict([
    ('01_layers_all_in_one.png', 'all 1024 routes in XY coloured by physical '
     'height (20 heights on the colourbar) + routes per height'),
    ('02_3d_global.png', 'true 3D drawing of all 1024 routes (+1 mm glass '
     'envelope), view elevation 30 deg, colour = routing height'),
    ('03_height_profile.png', 'per-height occupancy (routes per body height) '
     'ordered by z + authoritative crossings per height'),
    ('04_crossing_hotspot_zoom.png', 'top-3 densest 20x20 mm same-height '
     'crossing cells with involved routes, markers, counts and idle heights'),
    ('05_multi_arc_examples.png', 'three real planar multi-arc routes with '
     'annotated arc centres/radii + height profile along the path'),
    ('06_crossing_curve_vs_stage.png', '20H crossing curve over the stages vs '
     'the historical 21H reference curve (not a target)'),
    ('07_21h_vs_20h.png', 'grouped bars: 21H historical vs 20H reachable stage '
     'positions; missing 20H stages are "not run yet"'),
])

#: the six reachable stage positions of the 20H experiment (in run order)
STAGE_ORDER = (
    'initial',
    'post_anneal_repair',
    'native3d_phase1',
    'native3d_phase2',
    'g3',
    'g4_best',
)
STAGE_LABELS = {
    'initial': 'initial legal 20H\n(fanout + XY)',
    'post_anneal_repair': 'post-annealing\n+ E5 joint repair',
    'native3d_phase1': 'Native-3D\nphase 1',
    'native3d_phase2': 'Native-3D\nphase 2',
    'g3': 'G1/G2/G3\n(manual full XYZ)',
    'g4_best': 'G4 best\n(progressive chain)',
}
STAGE_SHORT = {
    'initial': 'initial',
    'post_anneal_repair': 'E5 repair',
    'native3d_phase1': 'native p1',
    'native3d_phase2': 'native p2',
    'g3': 'G3',
    'g4_best': 'G4 best',
}

#: candidate run directories of each 20H stage (first existing wins)
STAGE_CANDIDATES = OrderedDict([
    ('initial', (P20.INIT_RUN,)),
    ('post_anneal_repair', (P20.E5_DIR,)),
    ('native3d_phase1', (P20.NATIVE3D_ABC_RUN,)),
    ('native3d_phase2', (P20.NATIVE3D_DEF_RUN / 'best_valid',
                         P20.NATIVE3D_DEF_RUN)),
    ('g3', (P20.XYZ_RUN / 'best_valid', P20.XYZ_RUN / 'G3_manual_full_xyz')),
    ('g4_best', (P20.G4_ROOT / '07_best_valid', P20.G4_ROOT / 'best_valid')),
])

#: historical 21H reference archive directories (read-only, frozen 21H runs)
REF21_ROOT = PROJECT_ROOT / 'outputs' / 'manual_c4_new_connectivity'
REF21_CANDIDATES = OrderedDict([
    ('initial', (REF21_ROOT / 'FANOUT_FIRST_21_HEIGHT_REBALANCED_1024',)),
    ('post_anneal_repair', (REF21_ROOT / 'NON_C4_CROSSING_OPT_1024',)),
    ('native3d_phase1', (REF21_ROOT / 'NATIVE_3D_CROSSING_OPT_1024',)),
    ('native3d_phase2', (REF21_ROOT / 'NATIVE_3D_JOINT_OPT_1024',)),
    ('g3', (REF21_ROOT / 'XYZ_JOINT_G123_1024' / 'best_valid',)),
    ('g4_best', (PROJECT_ROOT / 'experiments' / 'xyz_joint_g4_1024'
                 / '07_best_valid',)),
])
REF21_STAGE_CURVE = P20.REPORTS / 'stage_curve_20h.json'


# ---------------------------------------------------------------------------
# small IO / formatting helpers
# ---------------------------------------------------------------------------
def read_json(path):
    """Read a JSON file; tolerate the UTF-8 BOM found in some frozen files."""
    with Path(path).open('r', encoding='utf-8-sig') as handle:
        return json.load(handle)


def write_json(path, payload):
    Path(path).write_text(
        json.dumps(payload, indent=1, ensure_ascii=False, default=str) + '\n',
        encoding='utf-8')
    return Path(path)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def rel_path(path):
    """Project-relative POSIX path when possible (portable manifest)."""
    path = Path(path).resolve()
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _as_int(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text.lstrip('-').isdigit():
            return int(text)
    return None


def _as_float(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _slug(text, limit=40):
    out = []
    for char in str(text).lower():
        if char.isalnum():
            out.append(char)
        elif out and out[-1] != '_':
            out.append('_')
    return ''.join(out).strip('_')[:limit] or 'layout'


def _fmt_z(value):
    return '%+.3f' % float(value)


def _wrap_items(items, max_chars=170):
    """Join '; '-separated items into lines of at most ``max_chars``."""
    lines, current = [], ''
    for item in items:
        piece = item if not current else '; ' + item
        if current and len(current) + len(piece) > max_chars:
            lines.append(current)
            current = item
        else:
            current += piece
    if current:
        lines.append(current)
    return lines


def _file_entry(path):
    path = Path(path)
    if not path.exists():
        return None
    return dict(path=rel_path(path), bytes=path.stat().st_size,
                sha256=sha256_file(path))


# ---------------------------------------------------------------------------
# crossing totals from any of the frozen crossing_stats.json schemas
# ---------------------------------------------------------------------------
def crossing_totals_from_payload(payload):
    """(crossings, pairs) from a crossing_stats/victory payload, or (None, None)."""
    if not isinstance(payload, dict):
        return None, None
    for key in ('totals', 'counts', 'crossing_totals', 'summary'):
        node = payload.get(key)
        if not isinstance(node, dict):
            continue
        count = _as_int(node.get('crossings'))
        pairs = _as_int(node.get('crossing_pairs'))
        if count is not None:
            return count, pairs
    count = _as_int(payload.get('crossings'))
    pairs = _as_int(payload.get('crossing_pairs'))
    return count, pairs


def read_validation(run_dir):
    payload = read_json(Path(run_dir) / 'validation.json') if (
        Path(run_dir) / 'validation.json').exists() else None
    if not isinstance(payload, dict):
        return None
    return dict(
        schema=payload.get('schema'),
        validated_at=payload.get('validated_at'),
        validation_pass=payload.get('validation_pass'),
        geometry_pass=payload.get('geometry_pass'),
        contract_pass=payload.get('contract_pass'),
        violation_count=_as_int(payload.get('violation_count')),
    )


# ---------------------------------------------------------------------------
# per-route planar multi-arc analysis (frozen layer2d definition)
# ---------------------------------------------------------------------------
def route_arc_profile(record, model):
    """Planar arcs and multi-arc runs of one real route (read only)."""
    arcs, regions = [], []
    for part_index, part in enumerate(record.get('parts') or []):
        if not isinstance(part, dict) or part.get('kind') != 'flat':
            continue
        primitives = [prim for prim in (part.get('primitives') or [])
                      if isinstance(prim, dict)]
        if not primitives:
            continue
        plane_id = model.classify_flat(part.get('z_mm'), part.get('layer_id'))
        for prim_index, prim in enumerate(primitives):
            if prim.get('kind') == 'arc':
                arcs.append(dict(prim=prim, plane_id=plane_id,
                                 part_index=part_index,
                                 prim_index=prim_index))
        if any(prim.get('kind') == 'arc' for prim in primitives):
            for region in layer2d.local_multi_arc_regions(primitives):
                regions.append(dict(region=region, plane_id=plane_id,
                                    part_index=part_index))
    return arcs, regions


# ---------------------------------------------------------------------------
# layout analysis (all numbers below come from the layout artifacts)
# ---------------------------------------------------------------------------
def analyse_layout(layout_dir, label=None):
    started = time.time()
    run_dir = Path(layout_dir).resolve()
    routes_path = run_dir / 'routes_l3d.json'
    crossing_path = run_dir / 'crossing_stats.json'
    if not routes_path.exists():
        raise SystemExit('layout has no routes_l3d.json: %s' % run_dir)
    ds = P.build_dataset(run_dir, label='layout')
    model = ds['model']
    records = list(ds['routed'])
    failed = list(ds['failed'])
    payload = (ds.get('routes') or {}).get('payload') or {}
    cmap = plt.get_cmap('turbo')
    norm = plt.Normalize(model.z_min, model.z_max)

    # ---- authoritative crossing numbers -----------------------------------
    auth_total = auth_pairs = None
    auth_source = ''
    if crossing_path.exists():
        cross_payload = read_json(crossing_path)
        auth_total, auth_pairs = crossing_totals_from_payload(cross_payload)
        auth_source = 'crossing_stats.json'
    if auth_total is None:
        totals = ds.get('crossing_totals') or {}
        auth_total = _as_int(totals.get('crossings'))
        auth_pairs = _as_int(totals.get('pairs'))
        auth_source = 'plots21.load_crossing_info' if auth_total is not None else ''
    recomputed_total = sum(int(data['count'])
                           for data in ds['crossings'].values())
    recomputed_pairs = sum(int(data['pairs'])
                           for data in ds['crossings'].values())
    counts_match = (auth_total is not None
                    and recomputed_total == int(auth_total))

    # ---- glass envelope + profile ----------------------------------------
    stack = read_json(run_dir / 'physical_layer_stack.json') if (
        run_dir / 'physical_layer_stack.json').exists() else {}
    planes_json = read_json(run_dir / 'layer_planes.json') if (
        run_dir / 'layer_planes.json').exists() else {}
    glass = OrderedDict()
    source_glass = ''
    for source_name, node in (('layer_planes.json', planes_json.get('glass')),
                              ('physical_layer_stack.json', None),
                              ('coldstart20.model20', None)):
        if isinstance(node, dict) and 'z_min_mm' in node:
            glass = OrderedDict(z_min_mm=float(node['z_min_mm']),
                                z_max_mm=float(node['z_max_mm']),
                                thickness_mm=float(node.get('thickness_mm',
                                                           node['z_max_mm']
                                                           - node['z_min_mm'])))
            source_glass = source_name
            break
    if not glass:
        z_range = stack.get('glass_z_range_mm')
        thickness = _as_float(stack.get('glass_thickness_mm'))
        if isinstance(z_range, (list, tuple)) and len(z_range) >= 2:
            glass = OrderedDict(z_min_mm=float(z_range[0]),
                                z_max_mm=float(z_range[1]),
                                thickness_mm=float(thickness if thickness
                                                   else z_range[1] - z_range[0]))
            source_glass = 'physical_layer_stack.json'
    if not glass:
        glass = OrderedDict(z_min_mm=float(M20.GLASS_Z_MIN_MM),
                            z_max_mm=float(M20.GLASS_Z_MAX_MM),
                            thickness_mm=float(M20.GLASS_THICKNESS_MM))
        source_glass = 'coldstart20.model20'

    # ---- per-height table -------------------------------------------------
    planes = []
    body_route_sum = 0
    for plane in model.planes:
        plane_id = plane['plane_id']
        geometry = ds['geometry'].get(plane_id) or {}
        bodies = geometry.get('bodies') or []
        leads = geometry.get('leads') or []
        body_ids = sorted({int(entry['route_id']) for entry in bodies
                           if entry.get('route_id') is not None})
        lead_ids = sorted({int(entry['route_id']) for entry in leads
                           if entry.get('route_id') is not None})
        auth = ds['crossing_counts'].get(plane_id) or {}
        crossing = ds['crossings'].get(plane_id) or dict(
            points=[], count=0, pairs=0, by_kind=Counter())
        auth_crossings = _as_int(auth.get('crossings'))
        auth_pairs_plane = _as_int(auth.get('pairs'))
        if auth_crossings is None:
            auth_crossings = int(crossing['count'])
            auth_pairs_plane = int(crossing['pairs'])
            auth_plane_source = 'recomputed'
        else:
            auth_plane_source = auth.get('source') or 'crossing_stats.json'
        body_route_sum += len(body_ids)
        points = list(crossing.get('points') or [])
        plane_entry = OrderedDict(
            plane_id=int(plane_id),
            label=str(plane['label']),
            z_mm=float(plane['z_mm']),
            kind=str(plane.get('kind') or 'body'),
            side=plane.get('side'),
            is_interface=bool(plane.get('is_interface')),
            routes=len(body_ids),
            body_parts=len(bodies),
            routes_with_geometry=len(set(body_ids) | set(lead_ids)),
            lead_parts=len(leads),
            crossings=int(auth_crossings),
            crossing_pairs=int(auth_pairs_plane if auth_pairs_plane is not None
                               else 0),
            crossings_recomputed=int(crossing['count']),
            pairs_recomputed=int(crossing['pairs']),
            crossings_source=auth_plane_source,
            crossing_kinds={str(k): int(v)
                            for k, v in (crossing.get('by_kind') or {}).items()},
            idle=bool(int(auth_crossings) == 0),
            crossing_points=points,
        )
        planes.append(plane_entry)
    planes.sort(key=lambda item: (item['z_mm'], item['plane_id']))
    plane_by_id = {item['plane_id']: item for item in planes}
    idle_heights = [item for item in planes if item['idle']]
    active_heights = [item for item in planes if not item['idle']]

    # ---- per-route statistics --------------------------------------------
    route_plane = dict(ds.get('route_plane') or {})
    route_stats = OrderedDict()
    for record in records:
        route_id = _as_int(record.get('route_id'))
        if route_id is None:
            continue
        arcs, regions = route_arc_profile(record, model)
        target = route_plane.get(route_id)
        route_stats[route_id] = dict(
            route_id=route_id,
            target_plane=target,
            n_arcs=len(arcs),
            n_regions=len(regions),
            arcs=arcs,
            regions=regions,
            n_transitions=_as_int(record.get('n_transitions')) or 0,
            n_mid_transitions=_as_int(record.get('n_mid_transitions')) or 0,
            length_mm=_as_float(record.get('length_mm')),
            record=record,
        )

    total_route_records = _as_int(payload.get('route_count'))
    if total_route_records is None:
        total_route_records = len(payload.get('routes') or [])
    routed_count = _as_int(payload.get('routed'))
    if routed_count is None:
        routed_count = len(records)
    failed_count = _as_int(payload.get('failed'))
    if failed_count is None:
        failed_count = len(failed)

    # ---- data quality caveats --------------------------------------------
    caveats = []
    if counts_match:
        caveats.append(
            'crossing counts: the authoritative crossing_stats.json totals '
            '(%d events / %d pairs) are reproduced exactly by recomputing the '
            'real line/arc intersections of every flat part of every route '
            '(plots21.compute_crossings semantics); the per-event marker '
            'positions in the figures are those recomputed exact '
            'intersections.' % (int(auth_total), int(auth_pairs or 0)))
    else:
        caveats.append(
            'crossing counts: crossing_stats.json reports %s events but the '
            'exact recomputation from routes_l3d.json gives %d; the figure '
            'titles use the authoritative count, the markers show the '
            'recomputed intersections - treat the two as different '
            'quantities.' % (str(auth_total), recomputed_total))
    if planes and sum(int(item['crossings']) for item in planes) != int(
            auth_total or 0):
        caveats.append(
            'crossing counts: the per-height crossing counts in the source '
            'JSON do not sum to the reported total; both are shown as in the '
            'source (no redistribution).')
    event_coords_in_source = False
    if crossing_path.exists():
        node_planes = []
        try:
            raw_cross = read_json(crossing_path)
            if isinstance(raw_cross.get('planes'), list):
                node_planes = raw_cross['planes']
        except (OSError, ValueError):
            node_planes = []
        event_coords_in_source = any(
            isinstance(entry, dict) and any(
                isinstance(entry.get(key), list) and entry.get(key)
                for key in ('crossing_points', 'points', 'positions', 'hotspots'))
            for entry in node_planes)
    if not event_coords_in_source:
        caveats.append(
            'crossing_stats.json of this layout stores aggregate counts only '
            '(no per-event x/y list); the crossing markers drawn here are '
            'recomputed from the real line/arc primitives.')
    if stack:
        provenance = stack.get('provenance')
        formal = stack.get('formal_acceptance_allowed')
        if provenance or formal is not None:
            caveats.append(
                'process stack: physical_layer_stack.json declares '
                'provenance=%r / formal_acceptance_allowed=%r -- the figures '
                'describe a simulated stack, not a tape-out-confirmed process.'
                % (provenance, formal))
    summary_path = P20.REPORTS / 'stage05_native3d_phase1_summary.json'
    validation = read_validation(run_dir)
    if summary_path.exists():
        try:
            stale = read_json(summary_path)
        except (OSError, ValueError):
            stale = {}
        stale_node = (stale.get('validation') if isinstance(stale, dict) else None)
        if isinstance(stale_node, dict):
            stale_pass = stale_node.get('validation_pass')
            stale_viol = _as_int(stale_node.get('violations'))
            layout_pass = (validation or {}).get('validation_pass')
            layout_viol = (validation or {}).get('violation_count')
            if (stale_pass is False and layout_pass is True
                    and stale_viol is not None and layout_viol is not None
                    and stale_viol != layout_viol):
                caveats.append(
                    'stale auxiliary summary: 12_reports/'
                    'stage05_native3d_phase1_summary.json reports '
                    'validation_pass=%r / %d violations, while the stage own '
                    'validation.json reports validation_pass=%r / %d '
                    'violations. The figures use validation.json / '
                    'STAGE05_GATE.json; treat the auxiliary summary as stale '
                    '(it recorded the planar validate21 audit, which is not '
                    'applicable to Native-3D bodies).'
                    % (stale_pass, stale_viol, layout_pass, layout_viol))
    if body_route_sum != routed_count:
        caveats.append(
            'per-height occupancy: the routes-with-body counts sum to %d but '
            'the layout reports %d routed routes; the discrepancy is shown as '
            'read, no route is reassigned.' % (body_route_sum, routed_count))
    if failed_count:
        caveats.append(
            'the layout reports %d failed route record(s); only routed routes '
            'are drawn (the count is stated in the manifest).' % failed_count)

    data = dict(
        layout_dir=run_dir,
        label=str(label) if label else run_dir.name,
        model=model,
        dataset=ds,
        records=records,
        failed_records=failed,
        payload=payload,
        route_plane=route_plane,
        route_stats=route_stats,
        planes=planes,
        plane_by_id=plane_by_id,
        idle_heights=idle_heights,
        active_heights=active_heights,
        cmap=cmap,
        norm=norm,
        glass=glass,
        glass_source=source_glass,
        profile=OrderedDict(
            name=str(M20.PROFILE),
            model='four_side_1024.fanout1024.coldstart20.model20',
            plane_count=len(planes),
            body_plane_count=sum(1 for item in planes
                                 if not item['is_interface']),
            interface_plane_ids=[item['plane_id'] for item in planes
                                 if item['is_interface']],
            plane_table=[OrderedDict(plane_id=item['plane_id'],
                                     label=item['label'],
                                     z_mm=item['z_mm'],
                                     kind=item['kind'])
                         for item in planes],
            glass=dict(glass),
            glass_source=source_glass,
            min_bend_radius_mm=float(M20.MIN_BEND_RADIUS_MM),
            min_3d_clearance_mm=float(M20.MIN_3D_CLEARANCE_MM),
            min_layer_pitch_mm=float(M20.MIN_LAYER_PITCH_MM),
            measured_min_pitch_mm=(float(stack['measured_min_height_pitch_mm'])
                                   if _as_float(stack.get(
                                       'measured_min_height_pitch_mm')) is not None
                                   else None),
            provenance=stack.get('provenance'),
            provenance_label=stack.get('provenance_label'),
            formal_acceptance_allowed=stack.get('formal_acceptance_allowed'),
            source=('layer_planes.json' if planes_json else
                    'reheight21.model (installed 20-height profile)'),
        ),
        totals=OrderedDict(
            route_records=total_route_records,
            routed=routed_count,
            failed=failed_count,
            body_occupancy_sum=body_route_sum,
            crossings=int(auth_total) if auth_total is not None else None,
            crossing_pairs=int(auth_pairs) if auth_pairs is not None else None,
            crossings_recomputed=recomputed_total,
            crossing_pairs_recomputed=recomputed_pairs,
            crossings_match=bool(counts_match),
            source=auth_source,
            event_coordinates_in_source=bool(event_coords_in_source),
        ),
        validation=validation,
        files=OrderedDict(
            (name, _file_entry(run_dir / name))
            for name in ('routes_l3d.json', 'crossing_stats.json',
                         'layer_planes.json', 'physical_layer_stack.json',
                         'assignment_1024.csv', 'validation.json',
                         'final_stats.json')
            if (run_dir / name).exists()),
        caveats=caveats,
        analysis_seconds=round(time.time() - started, 3),
    )
    return data


# ---------------------------------------------------------------------------
# stage tables (06 / 07)
# ---------------------------------------------------------------------------
def read_stage_entry(candidates):
    for candidate in candidates:
        candidate = Path(candidate)
        crossing_path = candidate / 'crossing_stats.json'
        routes_path = candidate / 'routes_l3d.json'
        if not crossing_path.exists():
            continue
        payload = read_json(crossing_path)
        crossings, pairs = crossing_totals_from_payload(payload)
        return OrderedDict(
            status='available',
            dir=rel_path(candidate),
            abs_dir=str(candidate.resolve()),
            crossings=crossings,
            crossing_pairs=pairs,
            validation=read_validation(candidate),
            files=OrderedDict(
                (name, _file_entry(candidate / name))
                for name in ('routes_l3d.json', 'crossing_stats.json')
                if (candidate / name).exists()),
        )
    return OrderedDict(status='not run yet', dir=None, abs_dir=None,
                       crossings=None, crossing_pairs=None, validation=None,
                       files=OrderedDict())


def build_stage_tables():
    """20H stage table + historical 21H reference table (both from JSON)."""
    stages = OrderedDict()
    for key in STAGE_ORDER:
        entry = read_stage_entry(STAGE_CANDIDATES[key])
        entry['key'] = key
        entry['label'] = STAGE_LABELS[key]
        entry['short'] = STAGE_SHORT[key]
        stages[key] = entry
    reference = OrderedDict()
    for key in STAGE_ORDER:
        entry = read_stage_entry(REF21_CANDIDATES[key])
        entry['key'] = key
        entry['label'] = STAGE_LABELS[key]
        entry['short'] = STAGE_SHORT[key]
        entry['note'] = 'historical 21H reference'
        reference[key] = entry
    override = OrderedDict(status='absent', path=rel_path(REF21_STAGE_CURVE),
                           entries=None)
    if REF21_STAGE_CURVE.exists():
        try:
            payload = read_json(REF21_STAGE_CURVE)
        except (OSError, ValueError):
            payload = None
        items = None
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            for key in ('stages', 'points', 'curve', 'stage_curve', 'rows'):
                if isinstance(payload.get(key), list):
                    items = payload[key]
                    break
        normalised = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            title = (item.get('label') or item.get('stage')
                     or item.get('name'))
            count = _as_int(item.get('crossings'))
            if count is None:
                count = _as_int(item.get('crossing_count'))
            if title is None or count is None:
                continue
            normalised.append(OrderedDict(
                label=str(title),
                short=str(item.get('short') or title),
                crossings=count,
                crossing_pairs=_as_int(item.get('crossing_pairs')),
                status=str(item.get('status') or 'available'),
                dir=(rel_path(item['layout_dir'])
                     if item.get('layout_dir') else None),
            ))
        if len(normalised) >= 2:
            override = OrderedDict(status='used',
                                   path=rel_path(REF21_STAGE_CURVE),
                                   entries=normalised)
        elif normalised:
            override = OrderedDict(status='mismatched',
                                   path=rel_path(REF21_STAGE_CURVE),
                                   entries=normalised)
    return stages, reference, override


# ---------------------------------------------------------------------------
# drawing helpers
# ---------------------------------------------------------------------------
def draw_board(ax, grid_step=25, title=None, title_fontsize=9.5):
    ax.set_xlim(0.0, BOARD_MM)
    ax.set_ylim(0.0, BOARD_MM)
    ax.set_aspect('equal', adjustable='box')
    for value in range(0, int(BOARD_MM) + 1, grid_step):
        ax.axvline(value, color='#999999', lw=0.25, alpha=0.18, zorder=0)
        ax.axhline(value, color='#999999', lw=0.25, alpha=0.18, zorder=0)
    ax.add_patch(Rectangle((0.0, 0.0), BOARD_MM, BOARD_MM, fill=False,
                           lw=0.9, edgecolor='#222222', zorder=10))
    ax.set_xticks(list(range(0, int(BOARD_MM) + 1, grid_step)))
    ax.set_yticks(list(range(0, int(BOARD_MM) + 1, grid_step)))
    ax.tick_params(labelsize=6.0, length=2.0, pad=1.0)
    ax.set_xlabel('x (mm)', fontsize=7.0, labelpad=1.0)
    ax.set_ylabel('y (mm)', fontsize=7.0, labelpad=1.0)
    for spine in ax.spines.values():
        spine.set_linewidth(0.6)
    if title:
        ax.set_title(title, fontsize=title_fontsize, pad=5.0)
    return ax


def entry_polylines(entry, step):
    """Polylines of one geometry entry (explicit step, no stale cache)."""
    polylines = []
    for prim in entry.get('primitives') or []:
        polyline = P.prim_polyline(prim, step=step)
        if polyline is not None and len(polyline) >= 2:
            polylines.append(polyline)
    return polylines


def height_colour(data, z_mm):
    return data['cmap'](data['norm'](float(z_mm)))


def layout_xy_segments(data, flat_step=FLAT_STEP_2D, trans_step=TRANS_STEP_2D,
                       mode='route'):
    """XY segments of all routes with a colour per route or per local height.

    ``mode='route'``  one colour per route = its body (target) routing height,
                     which is the route-level "coloured by physical height"
                     reading of the figure; leads/transitions inherit it.
    ``mode='part'``   every flat part is coloured by its own z and every
                     transition segment by its local z (per-height view).
    """
    segments, colours = [], []
    cmap, norm = data['cmap'], data['norm']
    for record in data['records']:
        route_id = _as_int(record.get('route_id'))
        target_plane = data['route_plane'].get(route_id)
        target = data['plane_by_id'].get(target_plane)
        route_colour = (cmap(norm(target['z_mm'])) if target
                        else (0.5, 0.5, 0.5, 1.0))
        for part in record.get('parts') or []:
            if not isinstance(part, dict):
                continue
            kind = part.get('kind')
            if kind == 'flat':
                z_mm = _as_float(part.get('z_mm'))
                if z_mm is None:
                    continue
                colour = route_colour if mode == 'route' else cmap(norm(z_mm))
                for prim in part.get('primitives') or []:
                    polyline = P.prim_polyline(prim, step=flat_step)
                    if polyline is None or len(polyline) < 2:
                        continue
                    segments.append(polyline)
                    colours.append(colour)
            elif kind == 'transition':
                try:
                    samples = P._transition_samples_local(part,
                                                          step=trans_step)
                except Exception:  # noqa: BLE001 - skip unparsable transition
                    continue
                for first, second in zip(samples, samples[1:]):
                    segments.append([(first[0], first[1]),
                                     (second[0], second[1])])
                    if mode == 'route':
                        colours.append(route_colour)
                    else:
                        colours.append(cmap(norm(0.5 * (first[2] + second[2]))))
    return segments, colours


def add_height_colourbar(fig, cax, data, fontsize=5.9, label=None):
    mappable = plt.cm.ScalarMappable(norm=data['norm'], cmap=data['cmap'])
    mappable.set_array(np.asarray([data['model'].z_min, data['model'].z_max]))
    colorbar = fig.colorbar(mappable, cax=cax)
    ticks = [item['z_mm'] for item in data['planes']]
    labels = ['%s %s' % (item['label'], _fmt_z(item['z_mm']))
              for item in data['planes']]
    colorbar.set_ticks(ticks)
    colorbar.set_ticklabels(labels)
    colorbar.ax.tick_params(labelsize=fontsize, length=2.0, pad=1.0)
    colorbar.set_label(label or 'routing height z (mm) - 20 heights',
                       fontsize=7.0)
    return colorbar


def save_figure(fig, out_dir, filename, dpi, timings, extra=None):
    path = Path(out_dir) / filename
    started = time.perf_counter()
    fig.savefig(path, dpi=dpi,
                metadata={'Software': 'coldstart20.plot_final'})
    elapsed = time.perf_counter() - started
    plt.close(fig)
    size = path.stat().st_size
    timings[filename] = round(elapsed, 3)
    meta = OrderedDict(
        file=filename,
        sha256=sha256_file(path),
        bytes=size,
        megabytes=round(size / 1e6, 3),
        dpi=int(dpi),
        render_seconds=round(elapsed, 3),
        description=FIGS.get(filename, ''),
    )
    if extra:
        meta.update(extra)
    print('[plot_final] %-34s %7.2f MB  %6.2f s' % (filename, size / 1e6,
                                                   elapsed), flush=True)
    return meta


# ---------------------------------------------------------------------------
# (1) all routes in XY coloured by physical height + routes per height
# ---------------------------------------------------------------------------
def fig_layers_all_in_one(data, out_dir, dpi, timings):
    fig = plt.figure(figsize=(15.8, 7.8))
    ax = fig.add_axes([0.040, 0.095, 0.440, 0.800])
    cax = fig.add_axes([0.462, 0.150, 0.009, 0.700])
    ax_bar = fig.add_axes([0.700, 0.095, 0.285, 0.800])

    segments, colours = layout_xy_segments(data, mode='route')
    collection = LineCollection(segments, colors=colours, linewidths=BASE_LW,
                                alpha=0.72, zorder=3, rasterized=True)
    ax.add_collection(collection)
    draw_board(ax, title='all %d routes projected in XY - colour = route body '
               'height (target routing height)' % len(data['records']),
               title_fontsize=9.6)
    add_height_colourbar(fig, cax, data, fontsize=5.7)
    ax.text(0.008, 0.004,
            'every route drawn (%d/%d routed); %d flat primitives + %d '
            'transitions sampled at %.2f mm (display resolution only); '
            'board 150x150 mm'
            % (len(data['records']), data['totals']['routed'],
               sum(len(part.get('primitives') or [])
                   for record in data['records']
                   for part in (record.get('parts') or [])
                   if part.get('kind') == 'flat'),
               sum(1 for record in data['records']
                   for part in (record.get('parts') or [])
                   if part.get('kind') == 'transition'),
               TRANS_STEP_2D),
            transform=ax.transAxes, fontsize=5.8, color='#333333',
            va='bottom', ha='left')

    # ---- routes per height -----------------------------------------------
    y_positions = np.arange(len(data['planes']))
    colours_by_plane = [height_colour(data, item['z_mm'])
                        for item in data['planes']]
    routes_per_height = [item['routes'] for item in data['planes']]
    bar = ax_bar.barh(y_positions, routes_per_height, height=0.78,
                      color=colours_by_plane, edgecolor='#222222',
                      linewidth=0.35, zorder=3)
    for index, item in enumerate(data['planes']):
        if item['is_interface']:
            bar[index].set_hatch('///')
            bar[index].set_edgecolor('#111111')
        ax_bar.text(item['routes'] + 1.5, index, '%d' % item['routes'],
                    va='center', ha='left', fontsize=5.8, color='#222222')
        ax_bar.plot([item['routes_with_geometry']], [index], marker='|',
                    markersize=8.0, color='#111111', zorder=5)
    ax_bar.set_yticks(y_positions)
    ax_bar.set_yticklabels([item['label'] for item in data['planes']])
    ax_bar.tick_params(labelsize=6.0, length=2.0, pad=1.0)
    ax_bar.set_xlim(0.0, max(routes_per_height + [1]) * 1.18)
    ax_bar.set_xlabel('routes routed at this height (body occupancy)',
                      fontsize=7.0)
    ax_bar.set_title('route count per height (ordered by z)', fontsize=10.0)
    ax_bar.grid(axis='x', lw=0.3, alpha=0.3, zorder=0)
    for spine in ax_bar.spines.values():
        spine.set_linewidth(0.6)
    handles = [
        Line2D([0], [0], color='#1f77b4', lw=2.4,
               label='routes routed at this height (body)'),
        Line2D([0], [0], color='#111111', lw=0, marker='|', markersize=8,
               label='routes with geometry here (leads/lifts incl.)'),
        Rectangle((0, 0), 1, 1, facecolor='none', edgecolor='#111111',
                  hatch='///', label='routable interface height'),
    ]
    ax_bar.legend(handles=handles, fontsize=5.4, loc='upper right',
                  frameon=True, framealpha=0.92)
    ax_bar.text(0.99, 0.012,
                'sum of routed-at-height = %d (each route counted once); '
                'z of each height is on the colourbar' % sum(routes_per_height),
                transform=ax_bar.transAxes, fontsize=5.6, ha='right',
                va='bottom', color='#333333')

    fig.suptitle('%s - 20-height 1024-route experiment: all routes coloured by '
                 'physical height and routes per height'
                 % data['label'], fontsize=11.5, y=0.985)
    fig.text(0.5, 0.012,
             'crossings: %s events / %s pairs (authoritative crossing_stats.json; '
             '%d exact line/arc intersections recomputed)  -  layout: %s'
             % (data['totals']['crossings'], data['totals']['crossing_pairs'],
                data['totals']['crossings_recomputed'],
                rel_path(data['layout_dir'])),
             ha='center', fontsize=6.3, color='#333333')
    return save_figure(fig, out_dir, '01_layers_all_in_one.png', dpi, timings,
                       dict(routes_drawn=len(data['records']),
                            colours='physical height z (turbo norm %.3f..%.3f)'
                                    % (data['model'].z_min,
                                       data['model'].z_max),
                            second_panel='route count per height'))


# ---------------------------------------------------------------------------
# (2) true 3D view of all routes + glass envelope
# ---------------------------------------------------------------------------
def fig_3d_global(data, out_dir, dpi, timings):
    from mpl_toolkits.mplot3d.art3d import Line3DCollection

    model = data['model']
    buckets = OrderedDict()
    skipped = 0
    for record in data['records']:
        route_id = _as_int(record.get('route_id'))
        polyline = P.route_3d_polyline(record)
        if polyline is None:
            skipped += 1
            continue
        plane_id = data['route_plane'].get(route_id)
        buckets.setdefault(plane_id, []).append(polyline)

    fig = plt.figure(figsize=(13.8, 10.6))
    ax = fig.add_axes([0.00, 0.03, 0.735, 0.90], projection='3d')
    cax = fig.add_axes([0.828, 0.30, 0.012, 0.44])
    glass = data['glass']
    for item in data['planes']:
        segments = buckets.get(item['plane_id']) or []
        if not segments:
            continue
        colour = height_colour(data, item['z_mm'])
        collection = Line3DCollection(segments, colors=[colour],
                                      linewidths=0.25, alpha=0.45)
        ax.add_collection3d(collection, autolim=False)
    other = buckets.get(None) or []
    if other:
        collection = Line3DCollection(other, colors=['#7f7f7f'],
                                      linewidths=0.25, alpha=0.45)
        ax.add_collection3d(collection, autolim=False)

    # ---- glass envelope: 150 x 150 x 1.0 mm box --------------------------
    z_min, z_max = glass['z_min_mm'], glass['z_max_mm']
    edge_style = dict(color='#5b8db8', lw=0.8, alpha=0.85)
    corners = [(0.0, 0.0), (BOARD_MM, 0.0), (BOARD_MM, BOARD_MM),
               (0.0, BOARD_MM), (0.0, 0.0)]
    for z_value in (z_min, z_max):
        ax.plot([c[0] for c in corners], [c[1] for c in corners],
                [z_value] * len(corners), **edge_style)
    for x_corner, y_corner in corners[:-1]:
        ax.plot([x_corner, x_corner], [y_corner, y_corner],
                [z_min, z_max], **edge_style)
    fig.text(0.015, 0.055,
             'glass envelope: %d x %d x %.2f mm box (z %s .. %s mm), '
             'drawn as wireframe'
             % (int(BOARD_MM), int(BOARD_MM), glass['thickness_mm'],
                _fmt_z(z_min), _fmt_z(z_max)),
             fontsize=7.2, color='#2f6690', ha='left')

    ax.set_xlim(0.0, BOARD_MM)
    ax.set_ylim(0.0, BOARD_MM)
    ax.set_zlim(z_min - 0.03, z_max + 0.06)
    ax.set_xticks(list(range(0, int(BOARD_MM) + 1, 25)))
    ax.set_yticks(list(range(0, int(BOARD_MM) + 1, 25)))
    ax.set_zticks([-0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    ax.tick_params(labelsize=6.0, pad=0.5)
    ax.set_xlabel('X (mm)', fontsize=8.0, labelpad=2)
    ax.set_ylabel('Y (mm)', fontsize=8.0, labelpad=2)
    ax.set_zlabel('Z (mm)', fontsize=8.0, labelpad=2)
    ax.view_init(elev=30, azim=-60)
    ax.set_box_aspect((1.0, 1.0, 0.40), zoom=1.12)
    ax.grid(True, lw=0.25, alpha=0.25)
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.pane.set_alpha(0.06)

    add_height_colourbar(fig, cax, data, fontsize=5.6,
                         label='routing height z (mm) - 20 heights')
    fig.suptitle('%s - all %d routed routes in true 3D geometry, colour = '
                 'routing height\n(real flats sampled at %s mm, S-curve '
                 'transitions sampled at %s mm; glass envelope %dx%dx%.2f mm)'
                 % (data['label'], len(data['records']),
                    getattr(P, 'STEP_3D_FLAT_MM', 2.0),
                    getattr(P, 'STEP_3D_TRANSITION_MM', 0.06),
                    int(BOARD_MM), int(BOARD_MM), glass['thickness_mm']),
                 fontsize=11.0, y=0.97)
    fig.text(0.5, 0.02,
             'view elevation 30 deg, azimuth -60 deg  -  records %d, routed %d, '
             'failed %d, unplottable %d  -  crossings %s events / %s pairs '
             '(crossing_stats.json)  -  layout: %s'
             % (data['totals']['route_records'], data['totals']['routed'],
                data['totals']['failed'], skipped,
                data['totals']['crossings'], data['totals']['crossing_pairs'],
                rel_path(data['layout_dir'])),
             ha='center', fontsize=6.3, color='#333333')
    return save_figure(fig, out_dir, '02_3d_global.png', dpi, timings,
                       dict(routes_drawn=len(data['records']) - skipped,
                            routes_skipped=skipped,
                            view=dict(elev=30, azim=-60),
                            glass=dict(glass)))


# ---------------------------------------------------------------------------
# (3) per-height occupancy
# ---------------------------------------------------------------------------
def fig_height_profile(data, out_dir, dpi, timings):
    fig = plt.figure(figsize=(14.6, 7.4))
    ax = fig.add_axes([0.055, 0.20, 0.90, 0.66])
    x_positions = np.arange(len(data['planes']))
    occupancy = [item['routes'] for item in data['planes']]
    colours = [height_colour(data, item['z_mm']) for item in data['planes']]
    bars = ax.bar(x_positions, occupancy, width=0.78, color=colours,
                  edgecolor='#222222', linewidth=0.35, zorder=3)
    for index, item in enumerate(data['planes']):
        if item['is_interface']:
            bars[index].set_hatch('///')
            bars[index].set_edgecolor('#111111')
        ax.text(index, item['routes'] + 1.0, '%d' % item['routes'],
                ha='center', va='bottom', fontsize=6.0)
        ax.plot([index], [item['routes_with_geometry']], marker='_',
                markersize=11.0, markeredgewidth=1.0, color='#111111',
                zorder=5)
    ax.set_xticks(x_positions)
    ax.set_xticklabels(['%s\n%s' % (item['label'], _fmt_z(item['z_mm']))
                        for item in data['planes']], fontsize=5.9)
    ax.set_ylabel('routes whose body occupies this height', fontsize=8.0)
    ax.set_ylim(0.0, max(occupancy + [1]) * 1.30)
    ax.grid(axis='y', lw=0.3, alpha=0.3, zorder=0)
    ax.tick_params(axis='y', labelsize=6.2)
    for spine in ax.spines.values():
        spine.set_linewidth(0.6)

    ax_cross = ax.twinx()
    crossings = [item['crossings'] for item in data['planes']]
    ax_cross.plot(x_positions, crossings, color='#d62728', lw=1.0, marker='x',
                  markersize=5.0, mew=0.9, zorder=6,
                  label='crossings on this height (crossing_stats.json)')
    for index, item in enumerate(data['planes']):
        if item['crossings'] > 0:
            ax_cross.annotate('%d' % item['crossings'],
                              (index, item['crossings']),
                              textcoords='offset points', xytext=(0, 7),
                              ha='center', fontsize=5.8, color='#a01313')
    ax_cross.set_ylabel('same-height crossing events', fontsize=8.0,
                        color='#a01313')
    ax_cross.tick_params(axis='y', labelsize=6.2, colors='#a01313')
    ax_cross.set_ylim(0.0, max(crossings + [1]) * 1.28)
    handles = [
        Rectangle((0, 0), 1, 1, facecolor='#bbbbbb', edgecolor='#222222',
                  label='routes routed at this height (body occupancy)'),
        Line2D([0], [0], color='#111111', lw=0, marker='_', markersize=11,
               label='routes with geometry at this height (leads/lifts incl.)'),
        Line2D([0], [0], color='#d62728', lw=1.0, marker='x', markersize=5,
               label='crossings on this height (authoritative)'),
    ]
    ax.legend(handles=handles, fontsize=6.3, loc='upper left', frameon=True,
              framealpha=0.92)
    fig.suptitle('%s - per-height occupancy ordered by z (%d heights: %d body '
                 '+ %d routable interface)\nsum of routed-at-height = %d '
                 '(every route counted once at its body height); layouts with '
                 'mid-path lifts also show the geometry-occupancy marker'
                 % (data['label'],
                    len(data['planes']),
                    sum(1 for item in data['planes']
                        if not item['is_interface']),
                    sum(1 for item in data['planes'] if item['is_interface']),
                    sum(occupancy)), fontsize=10.5, y=0.975)
    idle_text = ', '.join(item['label'] for item in data['idle_heights'])
    fig.text(0.5, 0.045,
             'idle heights with 0 crossings (%d of %d): %s   -   active heights '
             'with crossings (%d): %s'
             % (len(data['idle_heights']), len(data['planes']),
                idle_text or 'none',
                len(data['active_heights']),
                ', '.join(item['label'] for item in data['active_heights'])
                or 'none'),
             ha='center', fontsize=6.3, color='#333333')
    fig.text(0.5, 0.014,
             'total crossings %s events / %s pairs (crossing_stats.json); '
             'per-height counts are the source values (no redistribution)  -  '
             'layout: %s'
             % (data['totals']['crossings'], data['totals']['crossing_pairs'],
                rel_path(data['layout_dir'])),
             ha='center', fontsize=6.0, color='#333333')
    return save_figure(fig, out_dir, '03_height_profile.png', dpi, timings,
                       dict(occupancy={item['label']: item['routes']
                                       for item in data['planes']},
                            crossings={item['label']: item['crossings']
                                       for item in data['planes']},
                            idle_heights=[item['label']
                                          for item in data['idle_heights']]))


# ---------------------------------------------------------------------------
# (4) top-3 20x20 mm crossing hotspots
# ---------------------------------------------------------------------------
def crossing_cells(data, cell_mm=CELL_MM):
    cells = defaultdict(list)
    for item in data['planes']:
        for point in item['crossing_points']:
            key = (item['plane_id'], int(math.floor(point['x'] / cell_mm)),
                   int(math.floor(point['y'] / cell_mm)))
            cells[key].append(point)
    ranked = sorted(cells.items(),
                    key=lambda item: (-len(item[1]), item[0][0],
                                      item[0][1], item[0][2]))
    return ranked


def _window_for_cell(gx, gy, cell_mm, window_mm):
    x_centre = gx * cell_mm + cell_mm / 2.0
    y_centre = gy * cell_mm + cell_mm / 2.0
    half = window_mm / 2.0
    x_min = min(max(x_centre - half, 0.0), BOARD_MM - window_mm)
    y_min = min(max(y_centre - half, 0.0), BOARD_MM - window_mm)
    return x_min, x_min + window_mm, y_min, y_min + window_mm


def fig_crossing_hotspot(data, out_dir, dpi, timings):
    ranked = crossing_cells(data)
    selected = ranked[:3]
    fig = plt.figure(figsize=(17.2, 7.0))
    axes = [fig.add_axes([0.035 + index * 0.32, 0.255, 0.295, 0.60])
            for index in range(len(selected))]
    hotspot_meta = []
    cmap = plt.get_cmap('turbo')
    for index, ((plane_id, gx, gy), points_in_cell) in enumerate(selected):
        ax = axes[index]
        plane = data['plane_by_id'][plane_id]
        geometry = data['dataset']['geometry'].get(plane_id) or {}
        bodies = geometry.get('bodies') or []
        x0, x1, y0, y1 = _window_for_cell(gx, gy, CELL_MM, ZOOM_MM)
        # -- background routes on this height ------------------------------
        background = []
        for entry in bodies:
            background.extend(entry_polylines(entry, step=0.35))
        if background:
            ax.add_collection(LineCollection(
                background, colors='#8a9aa8', linewidths=0.22, alpha=0.55,
                zorder=2, rasterized=True))
        # -- involved routes ------------------------------------------------
        involved = sorted({point['route_a'] for point in points_in_cell}
                          | {point['route_b'] for point in points_in_cell})
        colours = [cmap(value) for value in np.linspace(0.03, 0.97,
                                                        max(1, len(involved)))]
        drawn = 0
        for colour, route_id in zip(colours, involved):
            for entry in bodies:
                if _as_int(entry.get('route_id')) != route_id:
                    continue
                polylines = entry_polylines(entry, step=0.08)
                if not polylines:
                    continue
                ax.add_collection(LineCollection(
                    polylines, colors=[colour], linewidths=0.9, alpha=0.95,
                    zorder=4, rasterized=True))
                drawn += 1
        # -- crossing points ------------------------------------------------
        window_points = [point for point in plane['crossing_points']
                         if x0 <= point['x'] <= x1 and y0 <= point['y'] <= y1]
        others = [point for point in window_points
                  if not (gx * CELL_MM <= point['x'] <= (gx + 1) * CELL_MM
                          and gy * CELL_MM <= point['y'] <= (gy + 1) * CELL_MM)]
        if others:
            ax.scatter([point['x'] for point in others],
                       [point['y'] for point in others], marker='x', s=9,
                       linewidths=0.5, color='#666666', alpha=0.55, zorder=5)
        ax.scatter([point['x'] for point in points_in_cell],
                   [point['y'] for point in points_in_cell], marker='x', s=26,
                   linewidths=0.8, color='#d62728', alpha=0.95, zorder=6,
                   label='crossing event in the cell')
        ax.add_patch(Rectangle((gx * CELL_MM, gy * CELL_MM), CELL_MM, CELL_MM,
                               fill=False, lw=1.0, ls='--', edgecolor='#111111',
                               zorder=7))
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)
        ax.set_aspect('equal', adjustable='box')
        ax.set_xticks(np.arange(x0, x1 + 1e-9, 10.0))
        ax.set_yticks(np.arange(y0, y1 + 1e-9, 10.0))
        ax.tick_params(labelsize=5.4, length=2.0, pad=1.0)
        ax.set_xlabel('x (mm)', fontsize=6.4, labelpad=0.5)
        ax.set_ylabel('y (mm)', fontsize=6.4, labelpad=0.5)
        for spine in ax.spines.values():
            spine.set_linewidth(0.6)
        ax.set_title('%s (z %s mm) - cell x[%d,%d] y[%d,%d] mm\n%d crossings '
                     'in this 20x20 mm cell - %d routes involved'
                     % (plane['label'], _fmt_z(plane['z_mm']), gx * CELL_MM,
                        (gx + 1) * CELL_MM, gy * CELL_MM, (gy + 1) * CELL_MM,
                        len(points_in_cell), len(involved)), fontsize=8.2)
        ax.text(0.0, -0.155,
                'height total %d events / %d pairs  -  idle heights (0 '
                'crossings, %d): %s'
                % (plane['crossings'], plane['crossing_pairs'],
                   len(data['idle_heights']),
                   ', '.join(item['label'] for item in data['idle_heights'])
                   or 'none'),
                transform=ax.transAxes, fontsize=5.7, color='#333333',
                va='top', ha='left', wrap=True)
        hotspot_meta.append(OrderedDict(
            rank=index + 1,
            plane_id=plane_id, label=plane['label'], z_mm=plane['z_mm'],
            cell_mm=[gx * CELL_MM, gy * CELL_MM, CELL_MM, CELL_MM],
            crossings_in_cell=len(points_in_cell),
            plane_crossings=plane['crossings'],
            plane_crossing_pairs=plane['crossing_pairs'],
            routes_involved=involved,
            routes_drawn=drawn,
            idle_heights=[item['label'] for item in data['idle_heights']],
        ))
    fig.suptitle('%s - top %d densest 20x20 mm same-height crossing cells '
                 '(all 20 heights scanned; cell rank by crossing events)'
                 % (data['label'], len(selected)), fontsize=11.2, y=0.975)
    fig.text(0.5, 0.075,
             'red x = crossing event inside the dashed 20x20 mm cell; grey x = '
             'crossing event of the same height inside the 40x40 mm zoom '
             'window; thin grey = all other routes on that height; coloured '
             'thick lines = the routes involved in the cell. Counts are the '
             'authoritative per-height crossing_stats.json values; marker '
             'positions are the exact recomputed line/arc intersections.',
             ha='center', fontsize=6.2, color='#333333')
    fig.text(0.5, 0.025,
             'scan: %d non-empty cells over %d heights  -  total crossings %s '
             'events / %s pairs  -  layout: %s'
             % (len(ranked), len(data['planes']),
                data['totals']['crossings'], data['totals']['crossing_pairs'],
                rel_path(data['layout_dir'])),
             ha='center', fontsize=6.2, color='#333333')
    return save_figure(fig, out_dir, '04_crossing_hotspot_zoom.png', dpi,
                       timings, dict(hotspots=hotspot_meta,
                                     cells_scanned=len(ranked)))


# ---------------------------------------------------------------------------
# (5) three real planar multi-arc example routes
# ---------------------------------------------------------------------------
def select_multi_arc_examples(data):
    """Pick (route, category) examples deterministically from the real layout."""
    routes = list(data['route_stats'].values())
    routes.sort(key=lambda item: item['route_id'])
    max_arcs = max((item['n_arcs'] for item in routes), default=0)
    used = set()
    picks = []

    def _first(predicate, key=None):
        candidates = [item for item in routes
                      if item['route_id'] not in used and predicate(item)]
        if not candidates:
            return None
        if key is not None:
            candidates.sort(key=key)
        return candidates[0]

    # (a) exactly 2 arcs as one tangent multi-arc run
    pick_a = _first(lambda item: item['n_arcs'] == 2 and item['n_regions'] >= 1)
    if pick_a is not None:
        picks.append(dict(stage_key='a', category='2 arcs, one tangent '
                          'multi-arc run', route=pick_a, fallback=False))
        used.add(pick_a['route_id'])
    else:
        pick_a = _first(lambda item: item['n_arcs'] == 2)
        if pick_a is not None:
            picks.append(dict(stage_key='a', category='2 arcs (no tangent '
                              'multi-arc run in this layout)', route=pick_a,
                              fallback=True))
            used.add(pick_a['route_id'])

    # (b) 3+ arcs; honest fallback when the layout has no such route
    pick_b = _first(lambda item: item['n_arcs'] >= 3,
                    key=lambda item: (-item['n_arcs'], item['route_id']))
    if pick_b is not None:
        picks.append(dict(stage_key='b', category='%d arcs (3+ arc case)'
                          % pick_b['n_arcs'], route=pick_b, fallback=False))
        used.add(pick_b['route_id'])
    else:
        pick_b = _first(lambda item: item['n_arcs'] >= 2,
                        key=lambda item: (-item['n_arcs'], item['route_id']))
        if pick_b is not None:
            picks.append(dict(stage_key='b',
                              category='3+ arcs NOT AVAILABLE in this layout '
                              '(max %d): highest-arc remaining route'
                              % max_arcs, route=pick_b, fallback=True))
            used.add(pick_b['route_id'])

    # (c) arcs at separate corners: two arcs, no tangent multi-arc run,
    #     maximising the distance between the two arc centres
    def centre_distance(item):
        centres = []
        for arc in item['arcs']:
            centre = arc['prim'].get('center')
            if isinstance(centre, (list, tuple)) and len(centre) >= 2:
                centres.append((float(centre[0]), float(centre[1])))
        if len(centres) < 2:
            return -1.0
        return math.hypot(centres[0][0] - centres[1][0],
                          centres[0][1] - centres[1][1])

    candidates = [item for item in routes
                  if item['route_id'] not in used and item['n_arcs'] >= 2
                  and item['n_regions'] == 0]
    candidates.sort(key=lambda item: (-centre_distance(item),
                                      item['route_id']))
    if candidates:
        pick_c = candidates[0]
        picks.append(dict(stage_key='c', category='arcs at separate corners',
                          route=pick_c, fallback=False))
        used.add(pick_c['route_id'])
    else:
        pick_c = _first(lambda item: item['n_arcs'] >= 2)
        if pick_c is not None:
            picks.append(dict(
                stage_key='c',
                category='arcs at separate corners NOT AVAILABLE in this '
                'layout: every remaining multi-arc route is one tangent '
                'multi-arc run; highest-arc remaining route shown',
                route=pick_c, fallback=True))
            used.add(pick_c['route_id'])
    if not picks:
        longest = sorted(routes,
                         key=lambda item: (-(item['length_mm'] or 0.0),
                                           item['route_id']))[:3]
        for index, item in enumerate(longest):
            picks.append(dict(stage_key='abc'[index],
                              category='no planar arcs in this layout - '
                              'longest route shown', route=item,
                              fallback=True))
    return picks, max_arcs


def _draw_planar_route(ax, route_item, data, annotate_arcs=True):
    record = route_item['record']
    target_plane = route_item['target_plane']
    body_colour = '#1f4e9c'
    lead_colour = '#9aa7b4'
    arc_colour = '#b2182b'
    body_polylines, lead_polylines = [], []
    for part in record.get('parts') or []:
        if not isinstance(part, dict) or part.get('kind') != 'flat':
            continue
        plane_id = data['model'].classify_flat(part.get('z_mm'),
                                               part.get('layer_id'))
        primitives = [prim for prim in (part.get('primitives') or [])
                      if isinstance(prim, dict)]
        polylines = [P.prim_polyline(prim, step=0.08) for prim in primitives]
        polylines = [item for item in polylines
                     if item is not None and len(item) >= 2]
        if plane_id == target_plane:
            body_polylines.extend(polylines)
        else:
            lead_polylines.extend(polylines)
    if lead_polylines:
        ax.add_collection(LineCollection(lead_polylines, colors=lead_colour,
                                         linewidths=0.9, alpha=0.8, ls='--',
                                         zorder=2, rasterized=True))
    if body_polylines:
        ax.add_collection(LineCollection(body_polylines, colors=body_colour,
                                         linewidths=1.6, alpha=0.95, zorder=3,
                                         rasterized=True))
    if annotate_arcs:
        for arc_index, arc in enumerate(route_item['arcs'], start=1):
            prim = arc['prim']
            centre = prim.get('center')
            radius = _as_float(prim.get('radius'))
            if centre is None or radius is None or radius <= 0:
                continue
            is_body = arc['plane_id'] == target_plane
            ax.add_patch(Circle((float(centre[0]), float(centre[1])), radius,
                                fill=False, lw=0.55, ls=':', color=arc_colour,
                                alpha=0.75 if is_body else 0.35, zorder=4))
            ax.plot([float(centre[0])], [float(centre[1])], marker='+',
                    markersize=6.0, mew=0.9, color=arc_colour,
                    alpha=0.95 if is_body else 0.4, zorder=5)
            start = prim.get('p0')
            if isinstance(start, (list, tuple)) and len(start) >= 2:
                ax.plot([float(centre[0]), float(start[0])],
                        [float(centre[1]), float(start[1])],
                        lw=0.4, ls=':', color=arc_colour,
                        alpha=0.8 if is_body else 0.35, zorder=4)
                mid_x = 0.5 * (float(centre[0]) + float(start[0]))
                mid_y = 0.5 * (float(centre[1]) + float(start[1]))
                ax.annotate('R=%.2f' % radius, (mid_x, mid_y),
                            textcoords='offset points', xytext=(3, 3),
                            fontsize=5.6, color=arc_colour,
                            alpha=0.95 if is_body else 0.45)
    # start / end of the real geometry
    first_point = last_point = None
    for part in record.get('parts') or []:
        if not isinstance(part, dict):
            continue
        if part.get('kind') == 'flat':
            for prim in part.get('primitives') or []:
                if not isinstance(prim, dict):
                    continue
                point = prim.get('p0')
                if isinstance(point, (list, tuple)) and len(point) >= 2:
                    first_point = (float(point[0]), float(point[1]))
                    break
            if first_point is not None:
                break
    for part in reversed(record.get('parts') or []):
        if not isinstance(part, dict):
            continue
        if part.get('kind') == 'flat':
            for prim in reversed(part.get('primitives') or []):
                if not isinstance(prim, dict):
                    continue
                point = prim.get('p1')
                if isinstance(point, (list, tuple)) and len(point) >= 2:
                    last_point = (float(point[0]), float(point[1]))
                    break
            if last_point is not None:
                break
    if first_point is not None:
        ax.plot([first_point[0]], [first_point[1]], marker='o', markersize=5.2,
                color='#2ca02c', zorder=6)
    if last_point is not None:
        ax.plot([last_point[0]], [last_point[1]], marker='s', markersize=5.0,
                color='#d95f02', zorder=6)
    return body_polylines, lead_polylines


def fig_multi_arc_examples(data, out_dir, dpi, timings):
    import textwrap
    picks, max_arcs = select_multi_arc_examples(data)
    count = max(1, len(picks))
    fig = plt.figure(figsize=(16.8, 11.2))
    top_height = 0.375
    for index, pick in enumerate(picks):
        left = 0.030 + index * (0.965 / count)
        width = (0.965 / count) - 0.022
        centre = left + width / 2.0
        ax_xy = fig.add_axes([left, 0.478, width, top_height])
        ax_profile = fig.add_axes([left, 0.195, width, 0.175])
        route_item = pick['route']
        route_id = route_item['route_id']
        record = route_item['record']
        target_plane = route_item['target_plane']
        plane = data['plane_by_id'].get(target_plane) or {}
        length_mm = route_item['length_mm']
        _draw_planar_route(ax_xy, route_item, data)
        draw_board(ax_xy)
        labels = ', '.join('%s %s' % (item['label'], _fmt_z(item['z_mm']))
                           for item in data['planes']
                           if item['plane_id'] in
                           {arc['plane_id'] for arc in route_item['arcs']})
        if plane:
            target_text = 'target %s (z %s)' % (plane['label'],
                                                _fmt_z(plane['z_mm']))
        else:
            target_text = 'target height n/a'
        ax_xy.set_title(
            '(%s) route %d - %d planar arcs (%d multi-arc run(s))\n'
            '%s - length_mm %.2f - %d transitions (%d mid-path)'
            % (pick['stage_key'], route_id, route_item['n_arcs'],
               route_item['n_regions'], target_text,
               length_mm if length_mm is not None else float('nan'),
               route_item['n_transitions'], route_item['n_mid_transitions']),
            fontsize=7.8)
        category_lines = textwrap.wrap(pick['category'], width=82) or ['']
        fig.text(centre, 0.437,
                 'arcs on: %s  -  body / lead colours as in the caption'
                 % (labels or 'n/a'), ha='center', va='center',
                 fontsize=5.8, color='#333333')
        fig.text(centre, 0.417,
                 'category: ' + '\n'.join(category_lines), ha='center',
                 va='center', fontsize=5.8, color='#333333')
        # ---- height profile along the real 3D path -----------------------
        polyline = P.route_3d_polyline(record)
        if polyline is not None and len(polyline) >= 2:
            steps = np.sqrt(np.sum(np.diff(polyline, axis=0) ** 2, axis=1))
            distance = np.concatenate([[0.0], np.cumsum(steps)])
            ax_profile.plot(distance, polyline[:, 2], color='#1f4e9c',
                            lw=1.1)
            for item in data['planes']:
                ax_profile.axhline(item['z_mm'], color='#aaaaaa', lw=0.25,
                                   alpha=0.55, zorder=0)
            if plane:
                ax_profile.axhline(plane['z_mm'], color='#d62728', lw=0.9,
                                   ls='--', zorder=2,
                                   label='target height %s (z %s)'
                                   % (plane['label'], _fmt_z(plane['z_mm'])))
            ax_profile.set_xlim(0.0, float(distance[-1]))
            ax_profile.set_ylim(data['glass']['z_min_mm'],
                                data['glass']['z_max_mm'])
            ax_profile.set_xlabel('centerline path length (mm, real 3D '
                                  'geometry)', fontsize=6.2)
            ax_profile.set_ylabel('z (mm)', fontsize=6.2)
            ax_profile.tick_params(labelsize=5.4, length=2.0, pad=1.0)
            ax_profile.grid(lw=0.25, alpha=0.3)
            ax_profile.legend(fontsize=5.4, loc='upper right', frameon=True,
                              framealpha=0.9)
            for spine in ax_profile.spines.values():
                spine.set_linewidth(0.6)
            ax_profile.set_title('height profile along the path (%d sampled '
                                 'points)' % len(polyline), fontsize=7.0)
    fig.suptitle('%s - geometry of real planar multi-arc routes: XY path with '
                 'arc centres / radii (top) and height profile along the path '
                 '(bottom)\nselection rule: (a) 2 arcs in one tangent multi-arc '
                 'run, (b) 3+ arcs, (c) arcs at separate corners'
                 % data['label'], fontsize=10.6, y=0.985)
    notes = []
    for pick in picks:
        if pick['fallback']:
            notes.append('(%s) %s' % (pick['stage_key'], pick['category']))
    note_text = '; '.join(notes) if notes else \
        'all three requested multi-arc categories exist in this layout'
    fig.text(0.5, 0.070,
             'max planar arcs in this layout: %d  -  %s' % (max_arcs,
                                                           note_text),
             ha='center', fontsize=6.3, color='#333333')
    fig.text(0.5, 0.028,
             'solid blue = route body at its target height; dashed grey = flat '
             'leads at other heights; dotted circle = real arc, R label = real '
             'radius; green circle = start of real geometry, orange square = '
             'end; length_mm from routes_l3d.json  -  layout: %s'
             % rel_path(data['layout_dir']), ha='center', fontsize=5.9,
             color='#333333')
    return save_figure(fig, out_dir, '05_multi_arc_examples.png', dpi, timings,
                       dict(max_planar_arcs=max_arcs,
                            examples=[dict(panel=pick['stage_key'],
                                           category=pick['category'],
                                           fallback=pick['fallback'],
                                           route_id=pick['route']['route_id'],
                                           n_arcs=pick['route']['n_arcs'],
                                           n_regions=pick['route']['n_regions'],
                                           target_plane=pick['route']['target_plane'],
                                           length_mm=pick['route']['length_mm'])
                                      for pick in picks]))


# ---------------------------------------------------------------------------
# (6) crossing curve over the 20H stages vs the historical 21H reference
# ---------------------------------------------------------------------------
def fig_stage_curve(data, out_dir, dpi, timings, yscale='log'):
    stages, reference, override = build_stage_tables()
    keys = list(STAGE_ORDER)
    available_20h = [stages[key]['crossings'] for key in keys
                     if stages[key]['crossings'] is not None]
    x_positions = np.arange(len(keys), dtype=float)
    fig = plt.figure(figsize=(14.8, 8.6))
    ax = fig.add_axes([0.075, 0.255, 0.885, 0.60])

    if override['status'] == 'used':
        labels = [entry['short'] for entry in override['entries']]
        values = [entry['crossings'] for entry in override['entries']]
        x_positions = np.arange(len(labels), dtype=float)
        keys = [entry['short'] for entry in override['entries']]
        source_note = '20H curve from 12_reports/stage_curve_20h.json'
        curve_rows = [dict(stage=entry['short'], label=entry['label'],
                           crossings=entry['crossings'],
                           status=entry['status'], dir=entry['dir'])
                      for entry in override['entries']]
    else:
        labels = [STAGE_SHORT[key] for key in keys]
        values = [stages[key]['crossings'] for key in keys]
        source_note = ('20H curve constructed from the known stage run '
                       'directories (12_reports/stage_curve_20h.json absent)')
        curve_rows = [dict(stage=STAGE_SHORT[key],
                           label=STAGE_LABELS[key].replace('\n', ' '),
                           crossings=stages[key]['crossings'],
                           status=stages[key]['status'],
                           dir=stages[key]['dir']) for key in keys]

    y_values = [value if value is not None else np.nan for value in values]
    line_20h = ax.plot(x_positions, y_values, color='#1f4e9c', lw=1.8,
                       marker='o', markersize=7.0, zorder=5,
                       label='20H - this experiment (crossing_stats.json)')[0]
    for index, value in enumerate(values):
        if value is None:
            ax.annotate('not run yet', (x_positions[index], 0.02),
                        xycoords=('data', 'axes fraction'),
                        textcoords='offset points', xytext=(0, 2),
                        ha='center', va='bottom', fontsize=6.6,
                        color='#b2182b', rotation=90)
            continue
        title = curve_rows[index]['stage'] if curve_rows[index].get('stage') \
            else labels[index]
        ax.annotate('%s\n%d' % (title, value),
                    (x_positions[index], value),
                    textcoords='offset points', xytext=(0, 11),
                    ha='center', fontsize=7.0, color='#123e7c')

    ref_values = [reference[key]['crossings'] for key in STAGE_ORDER]
    if any(value is not None for value in ref_values):
        ref_y = [value if value is not None else np.nan
                 for value in ref_values]
        ref_x = (np.arange(len(STAGE_ORDER), dtype=float)
                 if override['status'] != 'used'
                 else np.linspace(0.0, len(STAGE_ORDER) - 1.0,
                                  len(STAGE_ORDER)))
        ax.plot(ref_x, ref_y, color='#7f7f7f', lw=1.4, ls='--', marker='s',
                markersize=4.8, zorder=4,
                label='21H - historical reference (NOT a target)')
        for index, value in enumerate(ref_values):
            if value is None:
                continue
            ax.annotate('%d' % value, (ref_x[index], value),
                        textcoords='offset points', xytext=(0, -13),
                        ha='center', fontsize=6.4, color='#555555')

    ax.set_xticks(np.arange(len(labels), dtype=float))
    ax.set_xticklabels(labels, fontsize=8.0)
    ax.set_xlim(-0.55, len(labels) - 0.45)
    if yscale == 'log':
        ax.set_yscale('log')
        bottom = 500.0
    else:
        bottom = 0.0
    top = (max(available_20h + [value for value in ref_values if value])
           if (available_20h or any(ref_values)) else 13000) * 2.1
    ax.set_ylim(bottom, top)
    ax.set_ylabel('same-height crossing events per layout (log scale)'
                  if yscale == 'log' else
                  'same-height crossing events per layout', fontsize=8.5)
    ax.set_xlabel('stage (run order)', fontsize=8.5)
    ax.grid(True, which='major', lw=0.35, alpha=0.4)
    ax.grid(True, which='minor', lw=0.15, alpha=0.2)
    ax.tick_params(labelsize=7.0)
    for spine in ax.spines.values():
        spine.set_linewidth(0.6)
    ax.legend(fontsize=8.0, loc='upper right', frameon=True, framealpha=0.95)
    ax.set_title('%s - crossing count over the 20H stages, with the historical '
                 '21H reference curve as a separate dashed line'
                 % data['label'], fontsize=11.0)
    box_text = ('21H curve = historical reference from the frozen 21H archive '
                '(six 21H runs, see manifest for the exact source files). It '
                'is NOT a target and NOT a like-for-like baseline: the 20H '
                'stack deletes plane L19 and shifts every height by +0.025 mm. '
                '%s.' % source_note)
    fig.text(0.075, 0.155, box_text, fontsize=6.9, color='#333333',
             wrap=True, ha='left')
    status_bits = []
    for index, row in enumerate(curve_rows):
        if row['crossings'] is None:
            status_bits.append('%s = not run yet' % labels[index])
    ref_available = sum(1 for value in ref_values if value is not None)
    fig.text(0.075, 0.105,
             '20H stage availability: %s   -   21H reference points read: '
             '%d/%d'
             % ('; '.join(status_bits) if status_bits else 'all six stages '
                'available', ref_available, len(STAGE_ORDER)),
             fontsize=6.6, color='#333333')
    source_lines = _wrap_items(
        ['%s=%s' % (STAGE_SHORT[key], reference[key]['dir'] or 'n/a')
         for key in STAGE_ORDER], max_chars=165)
    fig.text(0.075, 0.062,
             '20H values are the authoritative crossing_stats.json totals of '
             'each stage layout; missing stage directories are reported as '
             '"not run yet", never as zero.', fontsize=6.2, color='#333333')
    for line_index, line in enumerate(source_lines):
        prefix = '21H sources: ' if line_index == 0 else ' ' * 13
        fig.text(0.075, 0.050 - 0.017 * line_index, prefix + line,
                 fontsize=5.6, color='#333333')
    meta = save_figure(fig, out_dir, '06_crossing_curve_vs_stage.png', dpi,
                       timings, dict(
                           yscale=yscale,
                           stage_curve_source=('12_reports/stage_curve_20h.json'
                                               if override['status'] == 'used'
                                               else 'constructed from stage '
                                               'dirs'),
                           stages_20h=[dict(key=row.get('stage'),
                                            crossing=row.get('crossings'),
                                            status=row.get('status'),
                                            dir=row.get('dir'))
                                       for row in curve_rows],
                           reference_21h=[dict(key=STAGE_SHORT[key],
                                               crossings=reference[key]['crossings'],
                                               crossing_pairs=reference[key]['crossing_pairs'],
                                               status=reference[key]['status'],
                                               dir=reference[key]['dir'])
                                          for key in STAGE_ORDER],
                       ))
    return meta, dict(stages=stages, reference=reference,
                      override=override, curve_rows=curve_rows)


# ---------------------------------------------------------------------------
# (7) 21H historical vs 20H reachable stage positions
# ---------------------------------------------------------------------------
def fig_21h_vs_20h(data, out_dir, dpi, timings, stage_tables):
    stages = stage_tables['stages']
    reference = stage_tables['reference']
    keys = list(STAGE_ORDER)
    x_positions = np.arange(len(keys), dtype=float)
    width = 0.36
    fig = plt.figure(figsize=(15.0, 8.4))
    ax = fig.add_axes([0.085, 0.235, 0.885, 0.62])
    ref_values = [reference[key]['crossings'] for key in keys]
    values_20h = [stages[key]['crossings'] for key in keys]

    bars_ref = ax.bar(x_positions - width / 2.0,
                      [value if value is not None else 0 for value in ref_values],
                      width=width, color='#9e9e9e', edgecolor='#555555',
                      linewidth=0.4, zorder=3,
                      label='21H - historical reference (NOT a target)')
    bars_20h = []
    for index, value in enumerate(values_20h):
        if value is None:
            ax.annotate('not run yet', (x_positions[index] + width / 2.0, 0.012),
                        xycoords=('data', 'axes fraction'),
                        textcoords='offset points', xytext=(0, 0),
                        ha='center', va='bottom', fontsize=7.0,
                        color='#b2182b', rotation=90)
        else:
            bars_20h.append(ax.bar(x_positions[index] + width / 2.0, value,
                                   width=width, color='#1f4e9c',
                                   edgecolor='#0d2c63', linewidth=0.4,
                                   zorder=3,
                                   label='20H - this experiment' if not bars_20h
                                   else None)[0])
    for index, value in enumerate(ref_values):
        if value is None:
            continue
        ax.annotate('%d' % value, (x_positions[index] - width / 2.0, value),
                    textcoords='offset points', xytext=(0, 3),
                    ha='center', fontsize=7.2, color='#444444')
    for index, value in enumerate(values_20h):
        if value is None or ref_values[index] is None:
            continue
        reduction = 100.0 * (1.0 - value / float(ref_values[index]))
        ax.annotate('%d\n(%+.1f%% vs 21H)' % (value, -reduction),
                    (x_positions[index] + width / 2.0, value),
                    textcoords='offset points', xytext=(0, 3),
                    ha='center', fontsize=7.0, color='#123e7c')
    ax.set_xticks(x_positions)
    ax.set_xticklabels([STAGE_LABELS[key] for key in keys], fontsize=7.4)
    ax.set_ylabel('same-height crossing events (crossing_stats.json)',
                  fontsize=8.5)
    ax.set_ylim(0.0, max([value for value in ref_values + values_20h
                         if value is not None] + [1]) * 1.24)
    ax.grid(axis='y', lw=0.35, alpha=0.35, zorder=0)
    ax.tick_params(labelsize=7.0)
    for spine in ax.spines.values():
        spine.set_linewidth(0.6)
    handles = [
        Rectangle((0, 0), 1, 1, facecolor='#9e9e9e', edgecolor='#555555',
                  label='21H - historical reference (NOT a target)'),
        Rectangle((0, 0), 1, 1, facecolor='#1f4e9c', edgecolor='#0d2c63',
                  label='20H - this experiment'),
    ]
    ax.legend(handles=handles, fontsize=8.0, loc='upper right', frameon=True,
              framealpha=0.95)
    ax.set_title('%s - reachable stage positions: 21H historical reference vs '
                 'the 20H numbers read from the stage directories\n'
                 '(missing 20H stages are marked "not run yet" instead of 0; '
                 'percentage = 20H change vs the 21H reference at the same '
                 'position)' % data['label'], fontsize=10.2)
    fig.text(0.5, 0.145,
             '21H bars are historical reference values read from the frozen '
             '21H archive crossing_stats.json files (not a target; exact '
             'source paths are listed in figure_manifest.json). 20H bars are '
             'the authoritative totals of the 20H stage layouts; a stage with '
             'no crossing_stats.json yet is reported as "not run yet", never '
             'as zero.', ha='center', fontsize=6.9, color='#333333',
             wrap=True)
    fig.text(0.5, 0.075,
             '21H reference archive: outputs/manual_c4_new_connectivity/'
             '{FANOUT_FIRST_21_HEIGHT_REBALANCED_1024, NON_C4_CROSSING_OPT_1024, '
             'NATIVE_3D_CROSSING_OPT_1024, NATIVE_3D_JOINT_OPT_1024, '
             'XYZ_JOINT_G123_1024/best_valid} and '
             'experiments/xyz_joint_g4_1024/07_best_valid',
             ha='center', fontsize=5.9, color='#333333')
    fig.text(0.5, 0.035,
             '20H stage directories: 03_fanout_and_xy, 04_.../E5_joint_repair_final, '
             '05_native3d_abc, 06_native3d_def/best_valid, 07_g123, 08_g4 '
             '(only stages with crossing_stats.json are drawn)',
             ha='center', fontsize=5.9, color='#333333')
    return save_figure(fig, out_dir, '07_21h_vs_20h.png', dpi, timings, dict(
        stages_20h=[dict(key=STAGE_SHORT[key],
                         crossings=stages[key]['crossings'],
                         status=stages[key]['status'],
                         dir=stages[key]['dir']) for key in keys],
        reference_21h=[dict(key=STAGE_SHORT[key],
                            crossings=reference[key]['crossings'],
                            dir=reference[key]['dir']) for key in keys],
        note='21H bars are a historical reference, not a target',
    ))


# ---------------------------------------------------------------------------
# (8, optional) --compare layout
# ---------------------------------------------------------------------------
def fig_compare_layouts(data, other, out_dir, dpi, timings):
    fig = plt.figure(figsize=(15.6, 7.4))
    axes = [fig.add_axes([0.045, 0.115, 0.44, 0.75]),
            fig.add_axes([0.525, 0.115, 0.44, 0.75])]
    for ax, layout in zip(axes, (data, other)):
        segments, colours = layout_xy_segments(layout, mode='route')
        ax.add_collection(LineCollection(segments, colors=colours,
                                         linewidths=0.22, alpha=0.8, zorder=3,
                                         rasterized=True))
        draw_board(ax, title='%s\n%d routes - %s crossings / %s pairs'
                   % (layout['label'], len(layout['records']),
                      layout['totals']['crossings'],
                      layout['totals']['crossing_pairs']), title_fontsize=9.2)
    slug = _slug(other['label'], 32)
    fig.suptitle('layout comparison - all routes projected in XY, colour = '
                 'physical height z (same colour scale)\nleft: %s   -   '
                 'right: %s' % (data['label'], other['label']),
                 fontsize=10.8, y=0.975)
    difference = None
    if (data['totals']['crossings'] is not None
            and other['totals']['crossings'] is not None):
        difference = (int(other['totals']['crossings'])
                      - int(data['totals']['crossings']))
    fig.text(0.5, 0.035,
             'crossings: layout A %s events / %s pairs, layout B %s events / '
             '%s pairs  (delta B-A: %s)  -  layout A: %s  -  layout B: %s'
             % (data['totals']['crossings'], data['totals']['crossing_pairs'],
                other['totals']['crossings'], other['totals']['crossing_pairs'],
                difference if difference is not None else 'n/a',
                rel_path(data['layout_dir']), rel_path(other['layout_dir'])),
             ha='center', fontsize=6.6, color='#333333')
    return save_figure(fig, out_dir, '08_compare_%s.png' % slug, dpi, timings,
                       dict(compare=dict(
                           label_a=data['label'],
                           dir_a=rel_path(data['layout_dir']),
                           crossings_a=data['totals']['crossings'],
                           pairs_a=data['totals']['crossing_pairs'],
                           label_b=other['label'],
                           dir_b=rel_path(other['layout_dir']),
                           crossings_b=other['totals']['crossings'],
                           pairs_b=other['totals']['crossing_pairs'],
                           delta_crossings=difference)))


# ---------------------------------------------------------------------------
# README / manifest
# ---------------------------------------------------------------------------
def build_reproduction_command(data, args):
    parts = [
        '.venv\\Scripts\\python.exe -m %s'
        % 'four_side_1024.fanout1024.coldstart20.plot_final',
        '--layout "%s"' % Path(data['layout_dir']),
        '--out-dir "%s"' % Path(Path(args.out_dir).resolve()),
        '--label "%s"' % data['label'],
    ]
    if args.compare:
        parts.append('--compare "%s"' % Path(args.compare).resolve())
    parts.append('--dpi %d' % int(args.dpi))
    parts.append('--yscale %s' % args.yscale)
    return ' '.join(parts)


def write_readme(out_dir, data, figures, stage_tables, manifest_name,
                 timings_name, command):
    lines = []
    lines.append('# Final figure suite - %s' % data['label'])
    lines.append('')
    lines.append('Generated by `%s` (bootstrap-first 20-height profile, '
                 '`matplotlib.use("Agg")`).' % SCRIPT_NAME)
    lines.append('')
    lines.append('* layout (source of every drawn route): `%s`'
                 % rel_path(data['layout_dir']))
    lines.append('* routes: **%s** route records, **%s** routed, **%s** failed'
                 % (data['totals']['route_records'],
                    data['totals']['routed'], data['totals']['failed']))
    lines.append('* crossings: **%s events / %s pairs** (authoritative '
                 '`crossing_stats.json`); exact recomputation from the real '
                 'line/arc primitives gives **%d events / %d pairs** '
                 '(match: %s)'
                 % (data['totals']['crossings'],
                    data['totals']['crossing_pairs'],
                    data['totals']['crossings_recomputed'],
                    data['totals']['crossing_pairs_recomputed'],
                    'yes' if data['totals']['crossings_match'] else 'NO'))
    lines.append('* heights: **%d** (%d body + %d routable interface), z = %s '
                 '.. %s mm; glass envelope 150x150x%.2f mm (z %s .. %s mm)'
                 % (data['profile']['plane_count'],
                    data['profile']['body_plane_count'],
                    len(data['profile']['interface_plane_ids']),
                    _fmt_z(data['profile']['plane_table'][0]['z_mm']),
                    _fmt_z(data['profile']['plane_table'][-1]['z_mm']),
                    data['glass']['thickness_mm'],
                    _fmt_z(data['glass']['z_min_mm']),
                    _fmt_z(data['glass']['z_max_mm'])))
    if data['validation']:
        validation = data['validation']
        lines.append('* layout validation (`validation.json`): validation_pass '
                     '= **%s**, geometry_pass = %s, contract_pass = %s, '
                     'violations = %s'
                     % (validation.get('validation_pass'),
                        validation.get('geometry_pass'),
                        validation.get('contract_pass'),
                        validation.get('violation_count')))
    lines.append('')
    lines.append('## Figures')
    lines.append('')
    lines.append('| file | size (MB) | sha256 (first 16) | shows |')
    lines.append('| --- | --- | --- | --- |')
    for figure in figures:
        lines.append('| `%s` | %.2f | `%s` | %s |'
                     % (figure['file'], figure['bytes'] / 1e6,
                        figure['sha256'][:16],
                        FIGS.get(figure['file'],
                                 figure.get('description', ''))))
    lines.append('')
    lines.append('Wall-clock render times (diagnostic only, not part of the '
                 'deterministic hash set) are written to `%s`.' % timings_name)
    lines.append('')
    lines.append('## Reproduce exactly')
    lines.append('')
    lines.append('```bat')
    lines.append(command)
    lines.append('```')
    lines.append('')
    lines.append('The script is idempotent: rerunning it on the same layout and '
                 'out-dir rewrites the same PNGs, this README and '
                 '`%s`; only `%s` changes.' % (manifest_name, timings_name))
    lines.append('')
    lines.append('## Data sources (all numbers are read, never invented)')
    lines.append('')
    for name, entry in data['files'].items():
        if entry:
            lines.append('* `%s` - %d bytes, sha256 `%s`'
                         % (name, entry['bytes'], entry['sha256']))
    lines.append('')
    lines.append('## Data-quality caveats')
    lines.append('')
    for caveat in data['caveats']:
        lines.append('* %s' % caveat)
    lines.append('* figures 06/07 read the six 20H stage directories at '
                 'generation time (no timestamps are embedded in any figure): '
                 'if a later stage is still running (for example 06 native-3D '
                 'phase 2), rerun this script after it finishes so the curve / '
                 'bar comparison reflects the final stage values.')
    lines.append('')
    lines.append('## Stage curve / 21H reference (figures 06 and 07)')
    lines.append('')
    lines.append('* 20H curve source: %s'
                 % ('`12_reports/stage_curve_20h.json`'
                    if stage_tables['override']['status'] == 'used'
                    else 'constructed from the known 20H stage run directories '
                    '(the override JSON does not exist yet)'))
    lines.append('')
    lines.append('| stage position | 20H status | 20H crossings | 21H reference '
                 'crossings | 21H source |')
    lines.append('| --- | --- | --- | --- | --- |')
    for key in STAGE_ORDER:
        stage = stage_tables['stages'][key]
        ref = stage_tables['reference'][key]
        lines.append('| %s | %s | %s | %s | `%s` |'
                     % (STAGE_SHORT[key], stage['status'],
                        stage['crossings'] if stage['crossings'] is not None
                        else 'not run yet',
                        ref['crossings'] if ref['crossings'] is not None
                        else 'n/a', ref['dir'] or 'n/a'))
    lines.append('')
    lines.append('**The 21H line/bars are a historical reference from the '
                 'frozen 21H archive, not a target and not a like-for-like '
                 'baseline** (the 20H stack deletes plane L19 and shifts every '
                 'height by +0.025 mm).')
    lines.append('')
    lines.append('## Regenerate later for the final layout')
    lines.append('')
    lines.append('```bat')
    lines.append('.venv\\Scripts\\python.exe -m '
                 'four_side_1024.fanout1024.coldstart20.plot_final '
                 '--layout "experiments\\COLD_START_20_HEIGHT_1024\\'
                 '10_best_valid\\<final run dir>" '
                 '--out-dir "experiments\\COLD_START_20_HEIGHT_1024\\'
                 '11_figures\\final" --label "final 20H layout"')
    lines.append('```')
    lines.append('')
    lines.append('The script works unchanged on any legal layout that has a '
                 '`routes_l3d.json` (plus `crossing_stats.json` for the '
                 'authoritative counts).')
    lines.append('')
    return Path(out_dir) / README_NAME, '\n'.join(lines) + '\n'


def write_manifest(out_dir, data, figures, stage_tables, readme_entry,
                   command, args):
    # wall-clock render times are diagnostic only: never part of the
    # deterministic manifest (the manifest must be byte-stable across reruns)
    manifest_figures = [OrderedDict(
        (key, value) for key, value in figure.items()
        if key != 'render_seconds') for figure in figures]
    manifest = OrderedDict(
        schema=SCHEMA,
        script=SCRIPT_NAME,
        script_sha256=sha256_file(HERE),
        label=data['label'],
        layout=OrderedDict(
            dir=rel_path(data['layout_dir']),
            abs_dir=str(Path(data['layout_dir'])),
            files=data['files'],
        ),
        profile=data['profile'],
        routes=dict(
            route_records=data['totals']['route_records'],
            routed=data['totals']['routed'],
            failed=data['totals']['failed'],
            body_occupancy_sum=data['totals']['body_occupancy_sum'],
            routes_drawn=len(data['records']),
            downsampled=False,
        ),
        crossings=dict(
            source=data['totals']['source'],
            authoritative_total=data['totals']['crossings'],
            authoritative_pairs=data['totals']['crossing_pairs'],
            recomputed_total=data['totals']['crossings_recomputed'],
            recomputed_pairs=data['totals']['crossing_pairs_recomputed'],
            exact_match=bool(data['totals']['crossings_match']),
            event_coordinates_in_source=bool(
                data['totals']['event_coordinates_in_source']),
            per_height={(item['label']): dict(
                plane_id=item['plane_id'], z_mm=item['z_mm'],
                crossings=item['crossings'],
                crossing_pairs=item['crossing_pairs'],
                crossings_recomputed=item['crossings_recomputed'],
                routes_with_body=item['routes'],
                body_parts=item['body_parts'],
                routes_with_geometry=item['routes_with_geometry'],
                idle=item['idle'],
            ) for item in data['planes']},
        ),
        height_profile=[OrderedDict(
            plane_id=item['plane_id'], label=item['label'],
            z_mm=item['z_mm'], kind=item['kind'],
            routes_with_body=item['routes'], body_parts=item['body_parts'],
            routes_with_geometry=item['routes_with_geometry'],
            crossings=item['crossings'],
        ) for item in data['planes']],
        layout_validation=data['validation'],
        figures=manifest_figures,
        files=OrderedDict([(figure['file'], dict(
            sha256=figure['sha256'], bytes=figure['bytes']))
            for figure in manifest_figures] + (
                [(README_NAME, dict(sha256=readme_entry['sha256'],
                                    bytes=readme_entry['bytes']))]
                if readme_entry else [])),
        readme=readme_entry,
        stage_curve=dict(
            source=('12_reports/stage_curve_20h.json'
                    if stage_tables['override']['status'] == 'used'
                    else 'constructed from the known 20H stage directories'),
            override_file=stage_tables['override']['path'],
            stages={key: dict(label=STAGE_LABELS[key].replace('\n', ' '),
                              status=stage_tables['stages'][key]['status'],
                              dir=stage_tables['stages'][key]['dir'],
                              crossings=stage_tables['stages'][key]['crossings'],
                              crossing_pairs=stage_tables['stages'][key]['crossing_pairs'])
                    for key in STAGE_ORDER},
            reference_21h={key: dict(
                label=STAGE_LABELS[key].replace('\n', ' '),
                status=stage_tables['reference'][key]['status'],
                dir=stage_tables['reference'][key]['dir'],
                crossings=stage_tables['reference'][key]['crossings'],
                crossing_pairs=stage_tables['reference'][key]['crossing_pairs'])
                for key in STAGE_ORDER},
            note='the 21H values are a historical reference, not a target',
        ),
        caveats=list(data['caveats']),
        notes=[
            'all 1024 routes are drawn from the layout routes_l3d.json; no '
            'route, part or crossing is filtered, down-sampled or moved',
            'figures 06/07 read the six 20H stage directories at generation '
            'time (no timestamps are embedded); if a stage is still running, '
            'rerun after it finishes to refresh the stage curve / comparison',
            'the 21H reference values come from the frozen 21H archive and are '
            'a historical reference, not a target and not a like-for-like '
            'baseline (the 20H stack deletes plane L19 and shifts every height '
            'by +0.025 mm)',
        ],
        reproduction=dict(
            command=command,
            module='four_side_1024.fanout1024.coldstart20.plot_final',
            arguments=dict(layout=str(Path(data['layout_dir']).resolve()),
                           out_dir=str(Path(args.out_dir).resolve()),
                           label=data['label'],
                           compare=(str(Path(args.compare).resolve())
                                    if args.compare else None),
                           dpi=int(args.dpi), yscale=args.yscale),
            python=sys.version.split()[0],
            matplotlib=matplotlib.__version__,
            script_sha256=sha256_file(HERE),
        ),
        honesty=dict(
            all_routes_drawn=True,
            routes_downsampled=False,
            crossing_counts_from='crossing_stats.json (authoritative)',
            crossing_markers='exact line/arc intersections recomputed with '
                             'plots21.compute_crossings semantics',
            reference_21h_is_a_target=False,
            missing_stages_reported_as='not run yet',
            output_files_hashed='every PNG in this directory + README.md',
            unhashed_diagnostics=[TIMINGS_NAME],
        ),
    )
    total_bytes = sum(figure['bytes'] for figure in figures)
    manifest['totals'] = OrderedDict(
        figure_count=len(figures),
        figure_bytes=total_bytes,
        figure_megabytes=round(total_bytes / 1e6, 3),
        max_figure_megabytes=round(max(
            [figure['bytes'] for figure in figures] + [0]) / 1e6, 3),
    )
    path = Path(out_dir) / MANIFEST_NAME
    write_json(path, manifest)
    return path, manifest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser():
    parser = argparse.ArgumentParser(
        prog='four_side_1024.fanout1024.coldstart20.plot_final',
        description='Final figure suite of the 20-height 1024-route run '
                    '(bootstrap-first; works on any legal layout run dir).')
    parser.add_argument('--layout', required=True,
                        help='layout run dir containing routes_l3d.json '
                             '(e.g. .../05_native3d_abc/run_native3d_phase1)')
    parser.add_argument('--out-dir', required=True,
                        help='output directory for the figures + manifest')
    parser.add_argument('--label', default=None,
                        help='human readable layout label used in titles '
                             '(default: run-dir name)')
    parser.add_argument('--compare', default=None,
                        help='optional second legal layout to compare against '
                             '(adds 08_compare_<slug>.png)')
    parser.add_argument('--dpi', type=int, default=DPI_DEFAULT,
                        help='figure dpi (default %d)' % DPI_DEFAULT)
    parser.add_argument('--yscale', choices=('log', 'linear'), default='log',
                        help='y axis of figure 06 (default log)')
    parser.add_argument('--only', default=None,
                        help='debug aid: comma separated figure prefixes to '
                             'render (e.g. 01,02); default all')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    only = None
    if args.only:
        only = {part.strip() if not part.strip().endswith('.png')
                else part.strip()[:2] for part in args.only.split(',')
                if part.strip()}

    print('[plot_final] profile: %s (%d heights)'
          % (M20.PROFILE, len(M20.PLANE_IDS)), flush=True)
    data = analyse_layout(args.layout, label=args.label)
    print('[plot_final] layout: %s  routes %d/%d  crossings %s/%s (match %s)'
          % (data['label'], len(data['records']), data['totals']['route_records'],
             data['totals']['crossings'], data['totals']['crossings_recomputed'],
             data['totals']['crossings_match']), flush=True)
    other = None
    if args.compare:
        other = analyse_layout(args.compare, label=args.label + ' (compare)')
        print('[plot_final] compare layout: %s  crossings %s'
              % (rel_path(other['layout_dir']), other['totals']['crossings']),
              flush=True)

    # warm up fonts / layout so the per-figure timings are meaningful
    warm = plt.figure(figsize=(1.0, 1.0))
    warm.savefig(io.BytesIO(), format='png', dpi=50)
    plt.close(warm)

    timings = OrderedDict()
    figures = []
    builders = [
        ('01', fig_layers_all_in_one),
        ('02', fig_3d_global),
        ('03', fig_height_profile),
        ('04', fig_crossing_hotspot),
        ('05', fig_multi_arc_examples),
    ]
    for prefix, builder in builders:
        if only and prefix not in only:
            continue
        figures.append(builder(data, out_dir, args.dpi, timings))

    stages, reference, override = build_stage_tables()
    stage_tables = dict(stages=stages, reference=reference, override=override)
    if not only or '06' in only:
        meta, _ = fig_stage_curve(data, out_dir, args.dpi, timings,
                                  yscale=args.yscale)
        figures.append(meta)
    if not only or '07' in only:
        figures.append(fig_21h_vs_20h(data, out_dir, args.dpi, timings,
                                      stage_tables))
    if other is not None:
        figures.append(fig_compare_layouts(data, other, out_dir, args.dpi,
                                           timings))

    # render timings are a diagnostic, deliberately outside the manifest hashes
    write_json(out_dir / TIMINGS_NAME,
               OrderedDict(timings=timings,
                           note='wall-clock diagnostic; excluded from '
                                'figure_manifest.json hashes'))

    command = build_reproduction_command(data, args)
    readme_path, readme_text = write_readme(out_dir, data, figures,
                                            stage_tables, MANIFEST_NAME,
                                            TIMINGS_NAME, command)
    readme_path.write_text(readme_text, encoding='utf-8')
    readme_entry = _file_entry(readme_path)
    manifest_path, manifest = write_manifest(out_dir, data, figures,
                                             stage_tables, readme_entry,
                                             command, args)
    total = sum(figure['bytes'] for figure in figures)
    print('[plot_final] wrote %d figures (%.2f MB total) + %s + %s -> %s'
          % (len(figures), total / 1e6, README_NAME, MANIFEST_NAME, out_dir),
          flush=True)
    largest = max(figures, key=lambda item: item['bytes']) if figures else None
    if largest and largest['bytes'] > MAX_PNG_BYTES:
        print('[plot_final] WARNING: %s is %.2f MB (> %.1f MB budget)'
              % (largest['file'], largest['bytes'] / 1e6,
                 MAX_PNG_BYTES / 1e6), flush=True)
    slowest = max(figures, key=lambda item: item['render_seconds']) if figures \
        else None
    if slowest:
        print('[plot_final] largest %s (%.2f MB), slowest %s (%.2f s)'
              % (largest['file'], largest['bytes'] / 1e6,
                 slowest['file'], slowest['render_seconds']), flush=True)
    print('[plot_final] reproduction: %s' % command, flush=True)
    return manifest


if __name__ == '__main__':
    main()
