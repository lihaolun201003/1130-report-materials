# -*- coding: utf-8 -*-
"""Real-geometry visualisation library + CLI for the XYZ joint router.

Owner: ``plotter`` (DESIGN.md section 4.12).

Every figure of this module is drawn from the *stored* route records and the
*stored* crossing records only:

* ``routes_l3d.json`` -> ``payload['routes']``; each route is a chain of
  ``flat`` parts (one physical ``z_mm`` + exact R15 ``primitives``: ``line``
  or ``arc``) and ``transition`` parts (exact S-curve: ``start``,
  ``direction``, ``z0``, ``z1``, ``radius_mm``, ``footprint_mm``); run lengths
  come from ``part['length_mm']``.
* ``crossing_stats.json`` -> ``planes`` (per-height crossing counts / route
  counts) and ``crossing_events`` (real crossing coordinates ``x_mm`` /
  ``y_mm`` / ``z_mm``).
* ``assignment_1024.csv`` -> per-route ``manual_group``, ``target_layer``,
  ``target_z_mm`` (used only for usage / manual-U height figures).

No schematic or invented geometry is ever drawn: flats are sampled from their
real primitives (``four_side_1024.fsd25d.path3d.path_polyline``) and the S-curves
from ``four_side_1024.fsd25d.path3d.transition_samples``.  A route that cannot
be sampled simply does not appear and the sampling failure is counted.

Public API (all return ``{'written': [png...], 'errors': [...]}``)
-------------------------------------------------------------------
``plot_baseline(run_dir, out_dir, prefix='baseline')``
    Global 3D view of all 1024 routes (colour = primary physical height, z
    exaggerated 20x), the 21-panel per-physical-height XY grid (manual-U flats
    red, non-manual blue, stored crossing events marked), the per-height
    crossing + route-count bar chart and the crossing hot-spot density map.

``plot_experiment(run_dir, baseline_dir, out_dir, prefix)``
    The same 3D / 21-panel / crossing-bar / hot-spot figures for one
    experiment, plus: per-height crossing comparison vs baseline, changed-route
    overview (old dashed grey vs new solid colour, up to 200 routes), per-height
    route-usage comparison and the manual-U height assignment before/after
    (only when the experiment assignment still has non-empty ``manual_group``).

``plot_router_validation(baseline_dir, cases, out_dir)``
    ``cases`` = list of dicts with keys ``route_ids``, ``before_dir``,
    ``after_dir``, ``title`` (plus optional ``crossings_before`` /
    ``crossings_after`` / ``route_crossings_before`` / ``route_crossings_after``
    / ``note``).  For every case route id one 2x2 figure is written:
    (a) old vs new XY overlay, (b) Z-vs-arc-length profile sampled from the real
    parts (flats at their z, S-curves via ``transition_samples``), (c) combined
    3D view old vs new, (d) zoomed local overlay around the changed region.
    Exact before/after crossing numbers are annotated.

``plot_compare(summaries, out_dir)``
    ``summaries`` = list of dicts with keys ``name``, ``crossings``,
    ``per_height`` (dict label->crossings, may be None), ``routes_changed``,
    ``manual_changed``, ``mid_transitions``.  Writes the G1/G2a/G2b/G3 crossings
    bar chart (2409 reference line), the delta bar chart, the per-height
    crossing distribution grouped by experiment and a compact summary table.

Support API
-----------
``build_summary(run_dir, name=None, baseline_dir=None)``
    Build one summary dict (for :func:`plot_compare`) from a run directory.
``auto_summaries(baseline_dir=None)``
    Discover baseline + G1/G2a/G2b/G3 run directories and build the summaries.
``load_cases(path)`` / ``normalize_cases(cases)``
    Load / normalise P0/P1/P2 case definitions.
``load_routes``, ``load_crossing_stats``, ``load_assignment``, ``height_table``,
``RouteGeometry``, ``route_polyline3d``, ``route_s_z``, ``route_signature``,
``changed_route_ids``, ``height_info``, ``crossing_total``.

CLI
---
::

    python -m four_side_1024.fanout1024.xyzrouter.visualize \
        --mode baseline --run-dir <dir> --out <plots dir>

    # experiment dashboard (baseline required for the comparison figures)
    python -m four_side_1024.fanout1024.xyzrouter.visualize --mode experiment \
        --run-dir outputs/.../G1_manual_frozen \
        --baseline-dir outputs/.../baseline_authoritative \
        --out outputs/.../plots/G1 --prefix G1

    # P0/P1/P2 router validation cases (JSON file or directory of JSON files)
    python -m four_side_1024.fanout1024.xyzrouter.visualize \
        --mode router_validation --cases <cases.json> --out <plots dir>

    # G1/G2a/G2b/G3 comparison (auto-discovers the run directories when no
    # --summaries file is given)
    python -m four_side_1024.fanout1024.xyzrouter.visualize --mode compare

    # polling loop: plot each experiment as soon as it is complete, then the
    # comparison figures and (optionally) the P0/P1/P2 validation figures
    python -m four_side_1024.fanout1024.xyzrouter.visualize --mode watch \
        --baseline-dir outputs/.../baseline_authoritative \
        --watch-dir G1=outputs/.../G1_manual_frozen \
        --watch-dir G3_cold=outputs/.../fair_comparison/G3_cold \
        --out-root outputs/.../plots \
        --cases outputs/.../router_validation \
        --poll-seconds 120 --timeout-minutes 90

Colour scheme (consistent across all figures)
---------------------------------------------
* manual-U flat parts:   red    ``#d32f2f``
* non-manual flat parts: blue   ``#1565c0``
* S-curve transitions:   purple ``#6a1b9a``
* old / baseline route:  grey   ``#9e9e9e`` (dashed)
* crossing events:       red    ``#e53935`` (x markers)
* per-height colours:    ``turbo`` colormap normalised over the real z range
  ``-0.35 .. +0.65 mm`` (the 21 physical heights of ``reheight21.model``).

Robustness
----------
Each public function catches per-figure exceptions: a bad or missing input
never raises out of the plotting function, it is recorded in ``errors`` (with
the traceback) while the other figures are still produced and the run exits
with code 0 if at least one figure was written.  A manifest JSON is written next
to the PNGs.  At most ``MAX_PNGS_PER_RUN`` (60) PNGs are written per run.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import traceback
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

import matplotlib

try:  # Agg is mandatory: this library must run head-less in the experiment runs
    matplotlib.use('Agg')
except Exception:  # pragma: no cover - already initialised backend
    pass
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.cm import ScalarMappable  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.colors import Normalize  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Rectangle, Patch  # noqa: E402
from mpl_toolkits.mplot3d import Axes3D  # noqa: E402,F401  (3d projection)
from mpl_toolkits.mplot3d.art3d import Line3DCollection  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024.reheight21 import model as M  # noqa: E402
from four_side_1024.fanout1024.xyzrouter import paths as PATHS  # noqa: E402
from four_side_1024.fsd25d import path3d as P3  # noqa: E402

__all__ = [
    # required API
    'plot_baseline', 'plot_experiment', 'plot_router_validation',
    'plot_compare',
    # support API
    'build_summary', 'auto_summaries', 'load_cases', 'normalize_cases',
    'load_routes', 'load_crossing_stats', 'load_assignment', 'height_table',
    'RouteGeometry', 'route_polyline3d', 'route_s_z', 'route_signature',
    'changed_route_ids', 'height_info', 'crossing_total', 'set_quiet',
    'watch_experiments', 'DEFAULT_WATCH_EXPERIMENTS',
    'main',
]

TOOL = 'four_side_1024.fanout1024.xyzrouter.visualize'
SCHEMA = 'xyz_joint_plots_v1'
DPI = 140
BOARD_MM = 150.0
Z_EXAG = 20.0
BASELINE_REFERENCE = 2409.0
MAX_PNGS_PER_RUN = 60
MAX_CHANGED_ROUTES = 200
MAX_ROUTER_VALIDATION_PNGS = 60

# --------------------------------------------------------------------------- #
# style / colour scheme
# --------------------------------------------------------------------------- #
Z_MIN = min(float(z) for z in M.PLANE_Z.values())
Z_MAX = max(float(z) for z in M.PLANE_Z.values())
CMAP = plt.get_cmap('turbo')
Z_NORM = Normalize(vmin=Z_MIN, vmax=Z_MAX)

C_MANUAL = '#d32f2f'          # manual-U flat parts (red)
C_NONMANUAL = '#1565c0'       # non-manual flat parts (blue)
C_TRANSITION = '#6a1b9a'      # exact R15 S-curves (purple)
C_BEFORE = '#9e9e9e'          # old / baseline geometry (dashed grey)
C_CROSS = '#e53935'           # crossing events
C_NEW = '#00897b'             # generic "new" accent
C_BOARD = '#424242'
C_GRID = '#e0e0e0'
C_CONTEXT = '#bdbdbd'         # faint context routes
C_ADDED = '#c62828'
C_REMOVED = '#2e7d32'

EXPERIMENT_COLORS = OrderedDict([
    ('baseline', '#616161'),
    ('G1', '#1e88e5'),
    ('G2a', '#43a047'),
    ('G2b', '#fb8c00'),
    ('G3', '#8e24aa'),
])
_FALLBACK_COLORS = list(plt.get_cmap('tab10').colors)

plt.rcParams.update({
    'figure.facecolor': 'white',
    'axes.facecolor': 'white',
    'savefig.facecolor': 'white',
    'font.size': 9.0,
    'axes.titlesize': 10.0,
    'axes.labelsize': 8.5,
    'xtick.labelsize': 7.5,
    'ytick.labelsize': 7.5,
    'legend.fontsize': 7.5,
    'axes.grid': False,
    'axes.linewidth': 0.6,
    'axes.unicode_minus': False,
})

_QUIET = False


def set_quiet(value):
    """Suppress per-figure console logging (used by the CLI ``--quiet``)."""
    global _QUIET
    _QUIET = bool(value)
    return _QUIET


def _log(message, level='info'):
    if not _QUIET:
        print('[visualize][%s] %s' % (level, message), flush=True)


# --------------------------------------------------------------------------- #
# the 21 physical heights of reheight21.model (physical z order)
# --------------------------------------------------------------------------- #
HEIGHT_ROWS = tuple(OrderedDict([
    ('plane_id', int(pid)),
    ('z_mm', float(z)),
    ('label', str(M.PLANE_LABEL[pid])),
    ('kind', str(M.PLANE_KIND[pid])),
    ('role', str(M.PLANE_LAYER_ROLE[pid])),
    ('manual_group', str(M.MANUAL_LAYER_TO_GROUP.get(int(pid), ''))),
]) for pid, z in M.PLANE_Z.items())
HEIGHT_BY_Z = OrderedDict((round(row['z_mm'], 6), row) for row in HEIGHT_ROWS)
HEIGHT_BY_PID = {row['plane_id']: row for row in HEIGHT_ROWS}
HEIGHT_BY_LABEL = {row['label']: row for row in HEIGHT_ROWS}
HEIGHT_KEYS = [round(row['z_mm'], 6) for row in HEIGHT_ROWS]
HEIGHT_LABELS = [row['label'] for row in HEIGHT_ROWS]
MANUAL_GROUP_ORDER = list(M.MANUAL_GROUPS.keys())


# --------------------------------------------------------------------------- #
# small generic helpers
# --------------------------------------------------------------------------- #
def _to_float(value):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def _fmt_int(value):
    if value is None:
        return 'n/a'
    try:
        return '%d' % int(round(float(value)))
    except (TypeError, ValueError):
        return str(value)


def _fmt_delta(value):
    if value is None:
        return 'n/a'
    try:
        return '%+d' % int(round(float(value)))
    except (TypeError, ValueError):
        return str(value)


def _safe_token(text):
    token = ''.join(char if char.isalnum() else '_' for char in str(text))
    return token.strip('_') or 'x'


def _pick(mapping, keys, default=None):
    if not isinstance(mapping, dict):
        return default
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return default


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return None


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                    encoding='utf-8')
    return path


def _find_input(run_dir, filename):
    """Resolve ``filename`` inside ``run_dir`` or its parent directory."""
    run_dir = Path(run_dir)
    for base in (run_dir, run_dir.parent):
        candidate = base / filename
        if candidate.exists():
            return candidate
    return None


# --------------------------------------------------------------------------- #
# height helpers / colours
# --------------------------------------------------------------------------- #
def _height_info(z_mm):
    """Metadata of the 21-height model entry closest to ``z_mm``."""
    z = _to_float(z_mm)
    if z is None:
        return dict(plane_id=None, z_mm=float('nan'), label='z=nan',
                    kind='custom', role='custom', manual_group='')
    key = round(z, 6)
    if key in HEIGHT_BY_Z:
        return dict(HEIGHT_BY_Z[key])
    return dict(plane_id=None, z_mm=z, label='z%+.3f' % z, kind='custom',
                role='custom', manual_group='')


def height_info(z_mm):
    """Public alias of :func:`_height_info`."""
    return _height_info(z_mm)


def _height_colour(z_mm):
    info = _height_info(z_mm)
    z = info['z_mm']
    if not math.isfinite(z):
        return '#7f7f7f'
    return CMAP(Z_NORM(z))


def _height_text(z_mm):
    info = _height_info(z_mm)
    return '%s %+.2f mm' % (info['label'], info['z_mm'])


def _nearest_height_key(z_mm, tol=1e-4):
    """Map a real z (or a custom z) to the rounded height-table key."""
    z = _to_float(z_mm)
    if z is None:
        return None
    key = round(z, 6)
    if key in HEIGHT_BY_Z:
        return key
    for candidate in HEIGHT_ROWS:
        if abs(candidate['z_mm'] - z) <= tol:
            return round(candidate['z_mm'], 6)
    return key


def _normalize_height_key(key):
    """Accept label (``L2`` / ``Z1_INTERFACE``), plane id or z in mm."""
    if key is None:
        return None
    if isinstance(key, (int, float)):
        z = _to_float(key)
        if z is not None:
            return _nearest_height_key(z)
        return None
    text = str(key).strip()
    if not text:
        return None
    if text in HEIGHT_BY_LABEL:
        return round(HEIGHT_BY_LABEL[text]['z_mm'], 6)
    try:
        pid = int(float(text))
    except (TypeError, ValueError):
        pid = None
    if pid is not None and pid in HEIGHT_BY_PID:
        return round(HEIGHT_BY_PID[pid]['z_mm'], 6)
    z = _to_float(text)
    if z is None:
        return None
    return _nearest_height_key(z)


# --------------------------------------------------------------------------- #
# figure plumbing: per-figure guard + manifest
# --------------------------------------------------------------------------- #
def _apply_style():
    plt.rcParams.update({
        'figure.facecolor': 'white',
        'axes.facecolor': 'white',
        'savefig.facecolor': 'white',
        'axes.unicode_minus': False,
    })


_apply_style()


def _save_figure(fig, path):
    """Save one PNG at ``DPI`` dpi and always close the figure."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fig.savefig(path, dpi=DPI, facecolor='white', bbox_inches='tight',
                    pad_inches=0.08)
    finally:
        plt.close(fig)
    return path


def _guarded(result, name, func, *args, **kwargs):
    """Run one figure function; never let its exception escape."""
    try:
        path = func(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - deliberate per-figure guard
        plt.close('all')
        result['errors'].append(dict(
            figure=str(name),
            error='%s: %s' % (type(exc).__name__, exc),
            traceback=traceback.format_exc(),
        ))
        _log('figure %s failed: %s: %s' % (name, type(exc).__name__, exc),
             level='error')
        return None
    if path is None:
        result['errors'].append(dict(figure=str(name),
                                     error='figure produced no output'))
        return None
    result['written'].append(str(path))
    _log('wrote %s' % path)
    return path


def _new_result():
    return dict(written=[], errors=[], skipped=[])


def _finish(result, out_dir, kind, source, prefix, data=None):
    """Write the run manifest JSON next to the PNGs."""
    out_dir = Path(out_dir)
    try:
        figures = []
        for path_text in result['written']:
            path = Path(path_text)
            figures.append(dict(name=path.name, path=str(path),
                                bytes=path.stat().st_size if path.exists()
                                else 0))
        payload = dict(
            schema=SCHEMA,
            tool=TOOL,
            kind=str(kind),
            source=str(source),
            out_dir=str(out_dir),
            prefix=str(prefix),
            generated_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
            png_count=len(figures),
            figures=figures,
            errors=result['errors'],
            skipped=result.get('skipped', []),
            data=data or {},
        )
        path = _write_json(out_dir / ('%s_manifest.json' % prefix), payload)
        result['manifest'] = str(path)
        # stable per-directory manifest name (one layout per output directory)
        try:
            plain = _write_json(out_dir / 'manifest.json', payload)
            result['manifest_plain'] = str(plain)
        except OSError:
            pass
    except Exception as exc:  # noqa: BLE001 - manifest is non-fatal
        result['errors'].append(dict(figure='manifest',
                                     error='%s: %s' % (type(exc).__name__,
                                                       exc)))
    return result


def _prepare_out_dir(result, out_dir):
    try:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir
    except OSError as exc:
        result['errors'].append(dict(figure='*',
                                     error='cannot create output directory '
                                           '%r: %s' % (out_dir, exc)))
        return None


# --------------------------------------------------------------------------- #
# input loading (routes / crossing stats / assignment)
# --------------------------------------------------------------------------- #
def _load_routes_file(path):
    payload = _read_json(path)
    if payload is None:
        return None
    if isinstance(payload, dict):
        records = payload.get('routes')
        if records is None and isinstance(payload.get('accepted_routes'), list):
            records = payload['accepted_routes']
    elif isinstance(payload, list):
        records = payload
    else:
        return None
    if isinstance(records, dict):
        records = list(records.values())
    routes = []
    for record in records or ():
        if not isinstance(record, dict):
            continue
        status = str(record.get('status') or '').strip().lower()
        if status in ('failed', 'error'):
            continue
        routes.append(record)
    if not routes:
        return None
    routes.sort(key=lambda record: _route_id(record) or 0)
    return routes


def load_routes(run_dir):
    """Load the routed records of ``run_dir/routes_l3d.json`` (or parent)."""
    path = _find_input(run_dir, 'routes_l3d.json')
    if path is None:
        _log('no routes_l3d.json under %s' % run_dir, level='warn')
        return None
    return _load_routes_file(path)


def load_crossing_stats(run_dir):
    """Load ``crossing_stats.json`` (or parent); ``None`` when absent."""
    path = _find_input(run_dir, 'crossing_stats.json')
    if path is None:
        _log('no crossing_stats.json under %s' % run_dir, level='warn')
        return None
    payload = _read_json(path)
    if not isinstance(payload, dict):
        return None
    payload['_path'] = str(path)
    return payload


def load_assignment(run_dir):
    """Load ``assignment_1024.csv`` rows (empty list when absent)."""
    import csv

    path = _find_input(run_dir, 'assignment_1024.csv')
    if path is None:
        return []
    try:
        with Path(path).open('r', encoding='utf-8-sig', newline='') as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except (OSError, ValueError, csv.Error) as exc:
        _log('could not read %s: %s' % (path, exc), level='warn')
        return []


def _load_bundle(run_dir):
    """Load the three data files of one layout directory."""
    run_dir = Path(run_dir)
    routes_path = _find_input(run_dir, 'routes_l3d.json')
    stats_path = _find_input(run_dir, 'crossing_stats.json')
    assign_path = _find_input(run_dir, 'assignment_1024.csv')
    return dict(
        dir=str(run_dir),
        routes=load_routes(run_dir),
        stats=load_crossing_stats(run_dir),
        assignment=load_assignment(run_dir),
        routes_path=str(routes_path) if routes_path is not None else None,
        stats_path=str(stats_path) if stats_path is not None else None,
        assignment_path=str(assign_path) if assign_path is not None else None,
    )


# --------------------------------------------------------------------------- #
# crossing-statistics normalisation (two known schemas)
# --------------------------------------------------------------------------- #
def crossing_total(stats):
    """Total crossing count from a stored ``crossing_stats.json`` payload."""
    if not isinstance(stats, dict):
        return None
    totals = stats.get('totals')
    if isinstance(totals, dict):
        value = _to_float(totals.get('crossings'))
        if value is not None:
            return int(round(value))
    planes = stats.get('planes') or ()
    if planes:
        total = 0
        found = False
        for row in planes:
            if not isinstance(row, dict):
                continue
            value = _to_float(row.get('crossings'))
            if value is not None:
                total += int(round(value))
                found = True
        if found:
            return total
    events = stats.get('crossing_events')
    if isinstance(events, list):
        return len(events)
    return None


#: public alias
_crossing_total = crossing_total


def _crossing_events(stats):
    if not isinstance(stats, dict):
        return []
    events = stats.get('crossing_events')
    if not isinstance(events, list):
        return []
    return [event for event in events if isinstance(event, dict)]


def _event_xy(event):
    x = _to_float(event.get('x_mm'))
    y = _to_float(event.get('y_mm'))
    if x is None or y is None:
        return None
    return (x, y)


def _events_by_height(stats):
    grouped = defaultdict(list)
    for event in _crossing_events(stats):
        z = _to_float(event.get('z_mm'))
        if z is None:
            try:
                pid = int(event.get('plane_id'))
            except (TypeError, ValueError):
                pid = None
            if pid is not None and pid in HEIGHT_BY_PID:
                z = HEIGHT_BY_PID[pid]['z_mm']
        if z is None:
            continue
        grouped[round(z, 6)].append(event)
    return grouped


def _events_for_routes(stats, route_ids):
    wanted = {int(rid) for rid in route_ids or ()}
    if not wanted:
        return []
    out = []
    for event in _crossing_events(stats):
        try:
            route_a = int(event.get('route_a'))
            route_b = int(event.get('route_b'))
        except (TypeError, ValueError):
            continue
        if route_a in wanted or route_b in wanted:
            out.append(event)
    return out


def _per_route_counts(stats):
    """``{route_id: crossing count}`` from a stored crossing-stats payload."""
    if not isinstance(stats, dict):
        return {}
    out = {}
    raw = stats.get('per_route_crossings')
    if isinstance(raw, dict):
        for key, value in raw.items():
            try:
                rid = int(key)
            except (TypeError, ValueError):
                continue
            if isinstance(value, dict):
                value = _pick(value, ('crossings', 'count', 'n'), 0)
            number = _to_float(value)
            if number is not None:
                out[rid] = int(round(number))
    if out:
        return out
    for event in _crossing_events(stats):
        for key in ('route_a', 'route_b'):
            try:
                rid = int(event.get(key))
            except (TypeError, ValueError):
                continue
            out[rid] = out.get(rid, 0) + 1
    return out


def height_table(stats, routes=None, geometry=None):
    """One row per physical height of the 21-height model, physical z order.

    Crossings / route counts come from ``crossing_stats.json`` planes (both the
    ``nonc4_crossing_stats_v1`` baseline schema and the
    ``xyz_joint_crossing_stats_v1`` experiment schema are handled); route
    counts fall back to the real flat parts when the stats file lacks them.
    """
    rows = OrderedDict()
    for info in HEIGHT_ROWS:
        rows[round(info['z_mm'], 6)] = dict(
            plane_id=info['plane_id'], label=info['label'],
            z_mm=info['z_mm'], kind=info['kind'],
            manual_group=info['manual_group'],
            crossings=0, crossing_pairs=0, route_count=0, part_count=0,
            crossing_known=False,
        )
    if isinstance(stats, dict):
        for row in stats.get('planes') or ():
            if not isinstance(row, dict):
                continue
            z = _to_float(row.get('z_mm'))
            if z is None:
                try:
                    pid = int(row.get('plane_id'))
                except (TypeError, ValueError):
                    pid = None
                if pid is not None and pid in HEIGHT_BY_PID:
                    z = HEIGHT_BY_PID[pid]['z_mm']
            if z is None:
                continue
            key = round(z, 6)
            if key not in rows:
                continue
            entry = rows[key]
            value = _to_float(row.get('crossings'))
            if value is not None:
                entry['crossings'] = int(round(value))
                entry['crossing_known'] = True
            value = _to_float(row.get('crossing_pairs'))
            if value is not None:
                entry['crossing_pairs'] = int(round(value))
            routes_value = row.get('route_count')
            if routes_value is None:
                routes_value = row.get('routes')
            number = _to_float(routes_value)
            if number is not None:
                entry['route_count'] = int(round(number))
            number = _to_float(row.get('part_count'))
            if number is not None:
                entry['part_count'] = int(round(number))
            label = str(row.get('label') or '').strip()
            if label:
                entry['label'] = label
            kind = str(row.get('kind') or '').strip()
            if kind:
                entry['kind'] = kind
        if not any(entry['crossing_known'] for entry in rows.values()):
            for key, events in _events_by_height(stats).items():
                if key in rows:
                    rows[key]['crossings'] = len(events)
                    rows[key]['crossing_known'] = True
    if geometry is not None:
        for key, entries in geometry.flat_by_z.items():
            if key in rows and rows[key]['route_count'] <= 0:
                rows[key]['route_count'] = len({entry['route_id']
                                                for entry in entries})
    elif routes is not None:
        id_sets = defaultdict(set)
        for route in routes:
            rid = _route_id(route)
            if rid is None:
                continue
            for part in _flat_parts(route):
                z = _to_float(part.get('z_mm'))
                if z is None:
                    continue
                key = round(z, 6)
                if key in rows:
                    id_sets[key].add(rid)
        for key, ids in id_sets.items():
            if rows[key]['route_count'] <= 0:
                rows[key]['route_count'] = len(ids)
    return [rows[key] for key in HEIGHT_KEYS if key in rows]


def _height_crossing_dict(stats):
    """``{rounded z: crossings}`` from the normalised height table."""
    return {round(row['z_mm'], 6): int(row['crossings'])
            for row in height_table(stats)}


# --------------------------------------------------------------------------- #
# route helpers / real-geometry sampling
# --------------------------------------------------------------------------- #
def _route_id(route):
    if not isinstance(route, dict):
        return None
    try:
        return int(route.get('route_id'))
    except (TypeError, ValueError):
        return None


def _parts(route):
    if not isinstance(route, dict):
        return []
    return [part for part in (route.get('parts') or ())
            if isinstance(part, dict)]


def _flat_parts(route):
    return [part for part in _parts(route) if part.get('kind') == 'flat']


def _transition_parts(route):
    return [part for part in _parts(route) if part.get('kind') == 'transition']


def _route_manual_group(route):
    if not isinstance(route, dict):
        return ''
    return str(route.get('manual_group') or '').strip()


def _route_is_manual(route):
    return bool(_route_manual_group(route))


def _primary_z(route):
    """Primary (assigned body) physical height of a route."""
    z = _to_float(route.get('target_z_mm'))
    if z is not None:
        return z
    best_z = None
    best_length = -1.0
    for part in _flat_parts(route):
        z = _to_float(part.get('z_mm'))
        length = _to_float(part.get('length_mm')) or 0.0
        if z is not None and length > best_length:
            best_z, best_length = z, length
    return best_z


def _route_length(route):
    value = _to_float(route.get('length_mm'))
    if value is not None:
        return value
    total = 0.0
    for part in _parts(route):
        total += _to_float(part.get('length_mm')) or 0.0
    return total


def _transition_tags(route):
    parts = _parts(route)
    positions = [index for index, part in enumerate(parts)
                 if part.get('kind') == 'transition']
    tags = {}
    for offset, index in enumerate(positions):
        tag = str(parts[index].get('tag') or '').strip().lower()
        if tag in ('fanout', 'mid'):
            tags[index] = tag
        else:
            tags[index] = ('fanout' if offset in (0, len(positions) - 1)
                           else 'mid')
    return tags


def _n_transitions(route):
    value = route.get('n_transitions')
    try:
        if value is not None:
            return int(value)
    except (TypeError, ValueError):
        pass
    return len(_transition_parts(route))


def _n_mid_transitions(route):
    value = route.get('n_mid_transitions')
    try:
        if value is not None:
            return int(value)
    except (TypeError, ValueError):
        pass
    tags = [tag for tag in _transition_tags(route).values() if tag == 'mid']
    if tags:
        return len(tags)
    return max(0, _n_transitions(route) - 2)


def _edge_points(points):
    """Corner/edge points of a sampled polyline (2D or 3D)."""
    if points is None or len(points) < 2:
        return None
    return points


def sample_flat_xy(part, step=2.0):
    """Dense 2D polyline of one stored flat part (real lines + R15 arcs)."""
    prims = part.get('primitives') or ()
    if not prims:
        return None
    try:
        points = P3.path_polyline(list(prims), step=max(float(step), 0.05))
    except Exception:  # noqa: BLE001 - bad stored primitive -> not drawable
        return None
    array = np.asarray(points, dtype=float)
    if array.ndim != 2 or array.shape[0] < 2 or array.shape[1] != 2:
        return None
    if not np.isfinite(array).all():
        return None
    return array


def sample_transition_xyz(part, step=0.35):
    """3D samples of one stored exact S-curve transition."""
    try:
        points = P3.transition_samples(part, step=max(float(step), 0.02))
    except Exception:  # noqa: BLE001 - bad stored S-curve -> not drawable
        return None
    array = np.asarray(points, dtype=float)
    if array.ndim != 2 or array.shape[0] < 2 or array.shape[1] != 3:
        return None
    if not np.isfinite(array).all():
        return None
    return array


def _distance3(first, second):
    return math.sqrt((first[0] - second[0]) ** 2
                     + (first[1] - second[1]) ** 2
                     + (first[2] - second[2]) ** 2)


def _decimate(points, stride):
    if points is None or len(points) <= 2 or stride <= 1:
        return points
    out = points[::int(stride)]
    if not np.allclose(out[-1], points[-1]):
        out = np.vstack([out, points[-1:]])
    return out


def _join_chunks(chunks):
    """Join sampled part chunks, dropping duplicated joints."""
    joined = []
    for chunk in chunks:
        if chunk is None or len(chunk) == 0:
            continue
        if joined and _distance3(joined[-1][-1], chunk[0]) < 1e-9:
            chunk = chunk[1:]
        if len(chunk):
            joined.append(chunk)
    if not joined:
        return None
    return np.vstack(joined)


def route_polyline3d(route, step_flat=4.0, step_transition=0.5):
    """True 3D polyline of one route sampled from its real stored parts."""
    chunks = []
    for part in _parts(route):
        kind = part.get('kind')
        if kind == 'flat':
            xy = sample_flat_xy(part, step_flat)
            z = _to_float(part.get('z_mm'))
            if xy is None or z is None:
                continue
            chunks.append(np.column_stack(
                [xy, np.full(len(xy), z, dtype=float)]))
        elif kind == 'transition':
            chunk = sample_transition_xyz(part, step_transition)
            if chunk is not None:
                chunks.append(chunk)
    return _join_chunks(chunks)


def route_s_z(route, step_flat=0.5, step_transition=0.15):
    """``(points3d, s_mm)`` with true 3D arc length from the real parts."""
    parts = _parts(route)
    if not parts:
        return None, None
    try:
        points, lengths = P3.sample_parts(
            parts, step_flat=float(step_flat),
            step_transition=float(step_transition))
    except Exception:  # noqa: BLE001 - stored geometry not drawable
        return None, None
    array = np.asarray(points, dtype=float)
    s_values = np.asarray(lengths, dtype=float)
    if array.ndim != 2 or array.shape[0] < 2 or array.shape[1] != 3:
        return None, None
    if len(s_values) != len(array):
        return None, None
    if not (np.isfinite(array).all() and np.isfinite(s_values).all()):
        return None, None
    return array, s_values


def _route_endpoints_xy(route):
    """Stored source / target port positions (first / last flat ends)."""
    flats = _flat_parts(route)
    if not flats:
        return None, None
    first = sample_flat_xy(flats[0], 1.0)
    last = sample_flat_xy(flats[-1], 1.0)
    start = first[0] if first is not None else None
    end = last[-1] if last is not None else None
    return start, end


def _route_visited_heights(route):
    heights = set()
    for part in _flat_parts(route):
        z = _to_float(part.get('z_mm'))
        if z is not None:
            heights.add(round(z, 6))
    for part in _transition_parts(route):
        for key in ('z0', 'z1'):
            z = _to_float(part.get(key))
            if z is not None:
                heights.add(round(z, 6))
    return sorted(heights)


# --------------------------------------------------------------------------- #
# geometry signatures (geometry diff / changed routes)
# --------------------------------------------------------------------------- #
def _prim_signature(prim):
    """Rounded geometry signature of one real primitive (route_builder style)."""
    if not isinstance(prim, dict):
        return ('bad', repr(prim))
    kind = str(prim.get('kind') or '')
    if kind == 'line':
        return ('line',
                tuple(round(float(v), 6) for v in prim.get('p0') or ()),
                tuple(round(float(v), 6) for v in prim.get('p1') or ()))
    if kind == 'arc':
        return ('arc',
                tuple(round(float(v), 6) for v in prim.get('p0') or ()),
                tuple(round(float(v), 6) for v in prim.get('p1') or ()),
                tuple(round(float(v), 6) for v in prim.get('center') or ()),
                round(float(prim.get('radius')), 6),
                round(float(prim.get('start_angle')), 9),
                round(float(prim.get('sweep')), 9))
    return ('other', kind)


def _part_signature(part):
    if not isinstance(part, dict):
        return ('bad', repr(part))
    if part.get('kind') == 'flat':
        return ('flat', round(float(part.get('z_mm')), 9),
                tuple(_prim_signature(prim)
                      for prim in part.get('primitives') or ()))
    return ('transition',
            tuple(round(float(v), 6) for v in part.get('start') or ()),
            tuple(round(float(v), 6) for v in part.get('direction') or ()),
            round(float(part.get('z0')), 9),
            round(float(part.get('z1')), 9))


def route_signature(route):
    """Rounded geometry fingerprint of a route's real parts.

    Same rounding contract as ``route_builder.route_signature`` (coordinates 6
    decimals, angles 9, physical z 9) so the "changed route" definition matches
    the optimizer's ``geometry_changes.json``.
    """
    try:
        return tuple(_part_signature(part) for part in _parts(route))
    except (TypeError, ValueError, KeyError):
        return None


def changed_route_ids(baseline_routes, routes):
    """Sorted ids whose stored parts differ from the baseline layout."""
    base = {}
    for route in baseline_routes or ():
        rid = _route_id(route)
        if rid is not None:
            base[rid] = route_signature(route)
    changed = []
    for route in routes or ():
        rid = _route_id(route)
        if rid is None:
            continue
        old_signature = base.get(rid)
        new_signature = route_signature(route)
        if old_signature is None or new_signature is None:
            changed.append(rid)
        elif old_signature != new_signature:
            changed.append(rid)
    return sorted(changed)


# --------------------------------------------------------------------------- #
# sampled real geometry cache of a whole route list
# --------------------------------------------------------------------------- #
class RouteGeometry:
    """Sampled real geometry of a route list, bucketed by physical height.

    ``flat_by_z`` maps a rounded physical z to entries
    ``dict(route_id, index, z_mm, pts (N,2), length_mm, manual, manual_group)``.
    Nothing is interpolated beyond the stored primitives / stored S-curves.
    """

    def __init__(self, routes, step_flat=2.0, step_transition=0.35):
        self.routes = list(routes or ())
        self.step_flat = float(step_flat)
        self.step_transition = float(step_transition)
        self.by_id = {}
        self.flat_xy = {}
        self.trans_xyz = {}
        self.flat_by_z = defaultdict(list)
        self.primary_z = {}
        self.manual = {}
        self.manual_group = {}
        self.route_z_keys = {}
        self.sampling_failures = 0
        self._build()

    def _build(self):
        for route in self.routes:
            rid = _route_id(route)
            if rid is None:
                continue
            self.by_id[rid] = route
            self.primary_z[rid] = _primary_z(route)
            group = _route_manual_group(route)
            self.manual[rid] = bool(group)
            self.manual_group[rid] = group
            z_keys = set()
            for index, part in enumerate(_parts(route)):
                try:
                    kind = part.get('kind')
                    if kind == 'flat':
                        xy = sample_flat_xy(part, self.step_flat)
                        z = _to_float(part.get('z_mm'))
                        if xy is None or z is None:
                            self.sampling_failures += 1
                            continue
                        key = round(z, 6)
                        self.flat_xy[(rid, index)] = xy
                        z_keys.add(key)
                        self.flat_by_z[key].append(dict(
                            route_id=rid, index=index, z_mm=z, pts=xy,
                            length_mm=_to_float(part.get('length_mm')) or 0.0,
                            manual=self.manual[rid], manual_group=group))
                    elif kind == 'transition':
                        xyz = sample_transition_xyz(part,
                                                    self.step_transition)
                        z0 = _to_float(part.get('z0'))
                        z1 = _to_float(part.get('z1'))
                        if xyz is None or z0 is None or z1 is None:
                            self.sampling_failures += 1
                            continue
                        self.trans_xyz[(rid, index)] = xyz
                except Exception:  # noqa: BLE001 - one bad part is not fatal
                    self.sampling_failures += 1
            self.route_z_keys[rid] = sorted(z_keys)

    # -- derived geometry ---------------------------------------------------
    def polyline3d(self, route, flat_stride=1):
        rid = _route_id(route)
        chunks = []
        for index, part in enumerate(_parts(route)):
            kind = part.get('kind')
            if kind == 'flat':
                xy = self.flat_xy.get((rid, index))
                z = _to_float(part.get('z_mm'))
                if xy is None or z is None:
                    continue
                if flat_stride > 1:
                    xy = _decimate(xy, flat_stride)
                chunks.append(np.column_stack(
                    [xy, np.full(len(xy), z, dtype=float)]))
            elif kind == 'transition':
                xyz = self.trans_xyz.get((rid, index))
                if xyz is not None:
                    chunks.append(xyz)
        return _join_chunks(chunks)

    def all_flat_arrays(self):
        arrays = []
        for key in HEIGHT_KEYS:
            for entry in self.flat_by_z.get(key, ()):
                arrays.append(entry['pts'])
        return arrays


# --------------------------------------------------------------------------- #
# assignment helpers (usage + manual-U height assignment figures)
# --------------------------------------------------------------------------- #
def assignment_height_counts(assignment_rows, manual_only=False):
    """``{rounded z: route count}`` of an assignment CSV (per target height)."""
    counts = Counter()
    for row in assignment_rows or ():
        if not isinstance(row, dict):
            continue
        if manual_only and not str(row.get('manual_group') or '').strip():
            continue
        z = _to_float(row.get('target_z_mm'))
        if z is None:
            z = _to_float(row.get('target_layer'))  # last resort: plane id
            if z is not None:
                info = HEIGHT_BY_PID.get(int(round(z)))
                z = info['z_mm'] if info else None
        if z is None:
            continue
        key = _nearest_height_key(z)
        if key is not None:
            counts[key] += 1
    return dict(counts)


def _manual_group_heights(assignment_rows):
    """``{manual group: rounded z key}`` of the manual-U routes."""
    grouped = defaultdict(list)
    for row in assignment_rows or ():
        if not isinstance(row, dict):
            continue
        group = str(row.get('manual_group') or '').strip()
        if not group:
            continue
        z = _to_float(row.get('target_z_mm'))
        if z is None:
            continue
        key = _nearest_height_key(z)
        if key is not None:
            grouped[group].append(key)
    out = {}
    for group, keys in grouped.items():
        counter = Counter(keys)
        out[group] = counter.most_common(1)[0][0]
    return out


def _manual_count(assignment_rows):
    return sum(1 for row in assignment_rows or ()
               if isinstance(row, dict)
               and str(row.get('manual_group') or '').strip())


def _height_label_text(key):
    info = HEIGHT_BY_Z.get(key)
    if info is None:
        z = _to_float(key)
        return 'z%+.3f' % z if z is not None else '?'
    return '%s (%+.2f)' % (info['label'], info['z_mm'])


# --------------------------------------------------------------------------- #
# drawing primitives
# --------------------------------------------------------------------------- #
def _draw_board(ax, board=BOARD_MM, linewidth=0.7, color=C_BOARD, label=None):
    ax.add_patch(Rectangle((0.0, 0.0), board, board, fill=False,
                           edgecolor=color, linewidth=linewidth, zorder=0))
    if label:
        ax.text(1.0, board - 2.0, label, fontsize=6.0, color='#616161',
                va='top', ha='left')


def _xy_limits(ax, margin=2.5, labels=True):
    ax.set_xlim(-margin, BOARD_MM + margin)
    ax.set_ylim(-margin, BOARD_MM + margin)
    ax.set_aspect('equal', adjustable='box')
    if labels:
        ax.set_xlabel('X (mm)')
        ax.set_ylabel('Y (mm)')


def _scatter_crossings(ax, events, size=12.0, color=C_CROSS, label=None,
                       marker='x', alpha=0.9, zorder=8):
    points = [_event_xy(event) for event in events or ()]
    points = [point for point in points if point is not None]
    if not points:
        return 0
    array = np.asarray(points, dtype=float)
    ax.scatter(array[:, 0], array[:, 1], marker=marker, s=size, c=color,
               linewidths=0.7, alpha=alpha, zorder=zorder, label=label)
    return len(array)


def _figure_note(ax, text, fontsize=6.5, color='#616161', x=0.01, y=0.01):
    ax.text(x, y, str(text), transform=ax.transAxes, fontsize=fontsize,
            color=color, va='bottom', ha='left')


def _set_3d_axes(ax, title=None, elev=24, azim=-58):
    ax.set_xlim(0.0, BOARD_MM)
    ax.set_ylim(0.0, BOARD_MM)
    ax.set_zlim(Z_MIN * Z_EXAG - 0.8, Z_MAX * Z_EXAG + 0.8)
    tick_heights = [row['z_mm'] for row in HEIGHT_ROWS[::3]]
    if HEIGHT_ROWS[-1]['z_mm'] not in tick_heights:
        tick_heights.append(HEIGHT_ROWS[-1]['z_mm'])
    ax.set_zticks([z * Z_EXAG for z in tick_heights])
    ax.set_zticklabels(['%+.2f' % z for z in tick_heights])
    ax.set_xlabel('X (mm)')
    ax.set_ylabel('Y (mm)')
    ax.set_zlabel('Z (mm) x%.0f' % Z_EXAG)
    ax.tick_params(axis='x', labelsize=7)
    ax.tick_params(axis='y', labelsize=7)
    ax.tick_params(axis='z', labelsize=6.5)
    ax.view_init(elev=elev, azim=azim)
    try:
        ax.set_box_aspect((1.5, 1.5, 0.85))
    except (AttributeError, ValueError):  # pragma: no cover - old mpl
        pass
    if title:
        ax.set_title(title, fontsize=10.0)


def _draw_glass_box(ax):
    """Reference glass box + interface heights (true process heights)."""
    for z in (Z_MIN, Z_MAX):
        ax.plot([0, BOARD_MM, BOARD_MM, 0, 0], [0, 0, BOARD_MM, BOARD_MM, 0],
                [z * Z_EXAG] * 5, color='#9e9e9e', linewidth=0.5, alpha=0.6)
    for x, y in ((0, 0), (BOARD_MM, 0), (BOARD_MM, BOARD_MM), (0, BOARD_MM)):
        ax.plot([x, x], [y, y],
                [Z_MIN * Z_EXAG, Z_MAX * Z_EXAG], color='#9e9e9e',
                linewidth=0.4, alpha=0.5)
    for z, name in ((0.0, 'Z1 interface'), (0.5, 'Z2 interface')):
        ax.plot([0, BOARD_MM, BOARD_MM, 0, 0], [0, 0, BOARD_MM, BOARD_MM, 0],
                [z * Z_EXAG] * 5, color='#1565c0', linewidth=0.5,
                linestyle=':', alpha=0.55)
        ax.text(0.0, -4.0, z * Z_EXAG, '%s z=%+.2f' % (name, z), fontsize=6.0,
                color='#1565c0')


def _colour_segments(points3d):
    """``(segments (N,2,3), colours (N,4))`` coloured by segment mid z."""
    if points3d is None or len(points3d) < 2:
        return None, None
    segments = np.stack([points3d[:-1], points3d[1:]], axis=1)
    mid_z = (points3d[:-1, 2] + points3d[1:, 2]) * 0.5
    colours = CMAP(Z_NORM(mid_z))
    return segments, colours


def _draw_route_flat_xy(ax, route, colour_fn, linewidth=1.3, alpha=0.95,
                        linestyle='-', zorder=4, step=1.5):
    for part in _flat_parts(route):
        xy = sample_flat_xy(part, step)
        z = _to_float(part.get('z_mm'))
        if xy is None or z is None:
            continue
        ax.plot(xy[:, 0], xy[:, 1], color=colour_fn(z), linewidth=linewidth,
                alpha=alpha, linestyle=linestyle, zorder=zorder)


def _draw_route_transitions_xy(ax, route, colour, linewidth=0.9, alpha=0.85,
                               linestyle='-', zorder=3, step=0.3):
    for part in _transition_parts(route):
        xyz = sample_transition_xyz(part, step)
        if xyz is None:
            continue
        ax.plot(xyz[:, 0], xyz[:, 1], color=colour, linewidth=linewidth,
                alpha=alpha, linestyle=linestyle, zorder=zorder)


# --------------------------------------------------------------------------- #
# figure: global 3D overview of all routes
# --------------------------------------------------------------------------- #
def _fig_3d_overview(geometry, out_path, title, total_crossings=None,
                     elev=24, azim=-58):
    segments = []
    colours = []
    manual_count = 0
    drawn = 0
    for rid, route in geometry.by_id.items():
        polyline = geometry.polyline3d(route, flat_stride=3)
        if polyline is None or len(polyline) < 2:
            continue
        drawn += 1
        if geometry.manual.get(rid):
            manual_count += 1
        display = polyline.copy()
        display[:, 2] *= Z_EXAG
        seg = np.stack([display[:-1], display[1:]], axis=1)
        colour = _height_colour(geometry.primary_z.get(rid))
        segments.append(seg)
        colours.append(np.tile(np.asarray(colour, dtype=float),
                               (len(seg), 1)))
    if not segments:
        raise ValueError('no drawable route geometry')

    fig = plt.figure(figsize=(13.8, 10.8))
    ax = fig.add_subplot(111, projection='3d')
    collection = Line3DCollection(np.concatenate(segments, axis=0),
                                  colors=np.concatenate(colours, axis=0),
                                  linewidths=0.33, alpha=0.6)
    ax.add_collection3d(collection, autolim=False)
    _draw_glass_box(ax)
    _set_3d_axes(ax, title=title, elev=elev, azim=azim)
    sm = ScalarMappable(norm=Z_NORM, cmap=CMAP)
    sm.set_array([])
    fig.colorbar(sm, ax=ax, fraction=0.028, pad=0.08, shrink=0.68,
                 label='primary physical height z (mm)')
    handles = [
        Line2D([0], [0], color='#616161', linewidth=1.2,
               label='%d routes sampled from their real parts '
                     '(colour = primary height)' % drawn),
    ]
    ax.legend(handles=handles, loc='upper left', fontsize=7.5,
              framealpha=0.9)
    note = ('crossings: %s   |   z exaggerated x%.0f   |   glass z = '
            '%.2f .. %.2f mm   |   real flats + exact R15 S-curves'
            % (_fmt_int(total_crossings), Z_EXAG, Z_MIN, Z_MAX))
    fig.text(0.5, 0.015, note, ha='center', fontsize=8.0, color='#424242')
    fig.text(0.5, 0.035,
             'manual-U routes: %d   |   non-manual routes: %d   '
             '(drawn with the same primary-height colour)'
             % (manual_count, drawn - manual_count),
             ha='center', fontsize=8.0, color='#424242')
    return _save_figure(fig, out_path)


# --------------------------------------------------------------------------- #
# figure: 21-panel per-physical-height XY grid
# --------------------------------------------------------------------------- #
def _fig_height_panels(geometry, stats, out_path, title, total_crossings=None,
                       ncols=4):
    table = height_table(stats, geometry=geometry)
    table_by_key = OrderedDict((round(row['z_mm'], 6), row) for row in table)
    events_by_key = _events_by_height(stats)
    crossing_known = any(row['crossing_known'] for row in table)
    nrows = int(math.ceil(len(HEIGHT_KEYS) / float(ncols)))
    fig, axes = plt.subplots(nrows, ncols,
                             figsize=(4.75 * ncols + 0.9, 4.35 * nrows + 0.9))
    axes_flat = np.asarray(axes).ravel()
    total_events = 0
    for order, key in enumerate(HEIGHT_KEYS):
        ax = axes_flat[order]
        row = table_by_key.get(key)
        entries = geometry.flat_by_z.get(key, ())
        manual_pts = [entry['pts'] for entry in entries if entry['manual']]
        other_pts = [entry['pts'] for entry in entries if not entry['manual']]
        if manual_pts:
            ax.add_collection(LineCollection(
                manual_pts, colors=C_MANUAL, linewidths=0.55, alpha=0.85,
                label='manual-U flats'))
        if other_pts:
            ax.add_collection(LineCollection(
                other_pts, colors=C_NONMANUAL, linewidths=0.45, alpha=0.75,
                label='non-manual flats'))
        events = events_by_key.get(key, ())
        if events:
            total_events += _scatter_crossings(ax, events, size=9.0)
        _draw_board(ax, linewidth=0.5)
        _xy_limits(ax, margin=2.0, labels=False)
        ax.tick_params(labelsize=5.0)
        if row is None:
            label, z_mm = str(key), float(key)
            n_routes, n_cross = len({entry['route_id'] for entry in entries}), 0
        else:
            label, z_mm = row['label'], row['z_mm']
            n_routes = row['route_count'] or len(
                {entry['route_id'] for entry in entries})
            n_cross = row['crossings']
        cross_text = ('crossings %d' % n_cross if crossing_known
                      else 'crossings n/a')
        ax.set_title('%s  z=%+.2f mm\nroutes %d  %s'
                     % (label, z_mm, n_routes, cross_text), fontsize=8.2)
    for index in range(len(HEIGHT_KEYS), len(axes_flat)):
        axes_flat[index].set_visible(False)
    fig.suptitle(title, fontsize=12.5, y=0.985)
    handles = [
        Line2D([0], [0], color=C_MANUAL, linewidth=1.4,
               label='manual-U flat parts (red)'),
        Line2D([0], [0], color=C_NONMANUAL, linewidth=1.4,
               label='non-manual flat parts (blue)'),
        Line2D([0], [0], marker='x', color=C_CROSS, linestyle='none',
               label='crossing events (%d, from crossing_stats.json)'
                     % total_events),
    ]
    fig.legend(handles=handles, loc='lower center', ncol=3, fontsize=9.0,
               framealpha=0.95, bbox_to_anchor=(0.5, 0.002))
    fig.subplots_adjust(left=0.02, right=0.99, top=0.955, bottom=0.035,
                        hspace=0.36, wspace=0.16)
    note = ('total crossings: %s   |   panels in physical z order   |   '
            'flats drawn from real primitives only'
            % _fmt_int(total_crossings))
    fig.text(0.5, 0.017, note, ha='center', fontsize=8.0, color='#424242')
    return _save_figure(fig, out_path)


# --------------------------------------------------------------------------- #
# figure: per-height crossing + route-count bars
# --------------------------------------------------------------------------- #
def _fig_height_bars(table, out_path, title, total_crossings=None):
    if not table:
        raise ValueError('empty height table')
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14.8, 8.0), sharex=True)
    x = np.arange(len(table))
    values = [row['crossings'] for row in table]
    colours = [_height_colour(row['z_mm']) for row in table]
    bars = ax1.bar(x, values, color=colours, edgecolor='#37474f',
                   linewidth=0.5)
    for bar, value in zip(bars, values):
        if value:
            ax1.text(bar.get_x() + bar.get_width() / 2.0, value,
                     '%d' % value, ha='center', va='bottom', fontsize=6.5,
                     color='#37474f')
    ax1.set_ylabel('crossings')
    ax1.set_title('Crossings per physical height (total %s)'
                  % _fmt_int(total_crossings), fontsize=11.0)
    ax1.set_ylim(0.0, max(values + [1]) * 1.18)
    ax1.grid(axis='y', linewidth=0.3, color=C_GRID)
    known = all(row['crossing_known'] for row in table)
    if not known:
        _figure_note(ax1, 'crossing_stats.json missing/incomplete: '
                          'missing heights shown as 0', fontsize=7.0,
                     color='#b71c1c')
    counts = [row['route_count'] for row in table]
    bars2 = ax2.bar(x, counts, color=colours, edgecolor='#37474f',
                    linewidth=0.5, alpha=0.92)
    for bar, row in zip(bars2, table):
        if row['manual_group']:
            bar.set_hatch('//')
    for bar, value in zip(bars2, counts):
        if value:
            ax2.text(bar.get_x() + bar.get_width() / 2.0, value, '%d' % value,
                     ha='center', va='bottom', fontsize=6.5, color='#37474f')
    ax2.set_ylabel('routes with flat part')
    ax2.set_title('Route count per physical height', fontsize=11.0)
    ax2.set_ylim(0.0, max(counts + [1]) * 1.18)
    ax2.grid(axis='y', linewidth=0.3, color=C_GRID)
    ax2.set_xticks(x)
    ax2.set_xticklabels(['%s\n%+.2f' % (row['label'], row['z_mm'])
                         for row in table], fontsize=7.0)
    ax2.set_xlabel('physical height (21-height model, z order)')
    handles = [Patch(facecolor='#78909c', edgecolor='#37474f',
                     label='normal routing height'),
               Patch(facecolor='#78909c', edgecolor='#37474f', hatch='//',
                     label='manual-U fixed height (crossings = 0)')]
    ax2.legend(handles=handles, loc='upper right', fontsize=7.0,
               framealpha=0.9)
    fig.suptitle(title, fontsize=12.5, y=0.985)
    fig.subplots_adjust(left=0.07, right=0.985, top=0.93, bottom=0.11,
                        hspace=0.32)
    return _save_figure(fig, out_path)


# --------------------------------------------------------------------------- #
# figure: crossing hot-spot density map
# --------------------------------------------------------------------------- #
def _fig_crossing_hotspots(stats, out_path, title, total_crossings=None,
                           table=None):
    events = _crossing_events(stats)
    points = [point for point in (_event_xy(event) for event in events)
              if point is not None]
    fig, ax = plt.subplots(figsize=(11.8, 10.4))
    _draw_board(ax, linewidth=0.8, label='board 150 x 150 mm')
    if points:
        array = np.asarray(points, dtype=float)
        xs, ys = array[:, 0], array[:, 1]
        if len(array) >= 8:
            hexbin = ax.hexbin(xs, ys, gridsize=70, cmap='inferno',
                               mincnt=1, linewidths=0.1,
                               extent=(0.0, BOARD_MM, 0.0, BOARD_MM))
            colorbar = fig.colorbar(hexbin, ax=ax, fraction=0.04, pad=0.02)
            colorbar.set_label('crossing events per hex cell')
        ax.scatter(xs, ys, marker='x', s=9.0, c=C_CROSS, linewidths=0.5,
                   alpha=0.45, zorder=6, label='crossing events (%d)'
                                                % len(array))
        # annotate the three densest 10 mm x 10 mm cells
        bins = np.linspace(0.0, BOARD_MM, 16)
        hist, xedges, yedges = np.histogram2d(xs, ys, bins=[bins, bins])
        cells = sorted(((hist[i, j], i, j)
                        for i in range(hist.shape[0])
                        for j in range(hist.shape[1])), reverse=True)[:3]
        for count, i, j in cells:
            if count < 3:
                continue
            ax.text((xedges[i] + xedges[i + 1]) / 2.0,
                    (yedges[j] + yedges[j + 1]) / 2.0, '%d' % int(count),
                    ha='center', va='center', fontsize=7.5, color='white',
                    bbox=dict(boxstyle='round,pad=0.16', fc='#000000cc',
                              ec='none'), zorder=9)
        _figure_note(ax, 'top densest 10 x 10 mm cells annotated with count',
                     fontsize=7.0)
    else:
        ax.text(BOARD_MM / 2.0, BOARD_MM / 2.0,
                'no crossing events in crossing_stats.json',
                ha='center', va='center', fontsize=11.0, color='#b71c1c')
    _xy_limits(ax, margin=3.0)
    top_text = ''
    if table:
        ranked = sorted(((row['crossings'], row['label'])
                         for row in table if row['crossings'] > 0), reverse=True)
        top_text = '   |   top heights: ' + ', '.join(
            '%s %d' % (label, count) for count, label in ranked[:4]) if ranked \
            else ''
    ax.set_title('%s\n%s crossing events on %d physical heights%s'
                 % (title, _fmt_int(total_crossings), len(
                     {round(_to_float(event.get('z_mm')), 6)
                      for event in events if _to_float(event.get('z_mm'))
                      is not None}), top_text), fontsize=10.5)
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(handles, labels, loc='upper right', fontsize=8.0,
                  framealpha=0.9)
    return _save_figure(fig, out_path)


# --------------------------------------------------------------------------- #
# figure: manual-U height assignment (baseline / before vs after)
# --------------------------------------------------------------------------- #
def _fig_manual_u_heights(rows_before, rows_after, out_path, title,
                          after_name='experiment', include_table=True):
    counts_before = assignment_height_counts(rows_before, manual_only=True)
    counts_after = assignment_height_counts(rows_after, manual_only=True) \
        if rows_after is not None else None
    if not counts_before and not counts_after:
        raise ValueError('no manual_group rows in the supplied assignments')
    groups_before = _manual_group_heights(rows_before)
    groups_after = _manual_group_heights(rows_after) \
        if rows_after is not None else None
    fig, axes = plt.subplots(1, 2 if include_table else 1,
                             figsize=(17.0 if include_table else 13.0, 6.2),
                             gridspec_kw=dict(width_ratios=(
                                 [1.55, 1.0] if include_table else [1.0])))
    ax1 = axes[0] if include_table else axes
    x = np.arange(len(HEIGHT_KEYS))
    width = 0.4
    before_values = [counts_before.get(key, 0) for key in HEIGHT_KEYS]
    ax1.bar(x - width / 2.0, before_values, width=width, color='#9e9e9e',
            edgecolor='#424242', linewidth=0.4, label='baseline')
    if counts_after is not None:
        after_values = [counts_after.get(key, 0) for key in HEIGHT_KEYS]
        ax1.bar(x + width / 2.0, after_values, width=width,
                color='#1e88e5', edgecolor='#0d47a1', linewidth=0.4,
                label=str(after_name))
    ax1.set_xticks(x)
    ax1.set_xticklabels(HEIGHT_LABELS, rotation=55, ha='right', fontsize=7.5)
    ax1.set_ylabel('manual-U route count')
    ax1.set_xlabel('physical height (21-height model, z order)')
    total_manual = _manual_count(rows_after if rows_after is not None
                                 else rows_before)
    ax1.set_title('Manual-U height assignment: %d routes' % total_manual,
                  fontsize=10.5)
    ax1.grid(axis='y', linewidth=0.3, color=C_GRID)
    ax1.legend(fontsize=8.0, framealpha=0.9)
    if include_table:
        ax2 = axes[1]
        ax2.axis('off')
        groups = [group for group in MANUAL_GROUP_ORDER
                  if group in groups_before
                  or (groups_after is not None and group in groups_after)]
        for group in sorted(set(groups_before)
                            | set((groups_after or {}).keys())):
            if group not in groups:
                groups.append(group)
        table_rows = []
        changed_any = False
        for group in groups:
            before_key = groups_before.get(group)
            after_key = (groups_after or {}).get(group)
            changed = (after_key is not None and before_key is not None
                       and before_key != after_key)
            changed_any = changed_any or changed
            table_rows.append([
                group,
                _height_label_text(before_key) if before_key is not None
                else 'n/a',
                _height_label_text(after_key)
                if after_key is not None else 'n/a',
                'CHANGED' if changed else '',
            ])
        ax2.set_title('manual group -> routing height',
                      fontsize=10.0)
        if table_rows:
            table_artist = ax2.table(
                cellText=table_rows,
                colLabels=['manual group', 'baseline height',
                           '%s height' % after_name if counts_after is not None
                           else 'after height', 'status'],
                loc='center', cellLoc='center')
            table_artist.auto_set_font_size(False)
            table_artist.set_fontsize(8.0)
            table_artist.scale(1.0, 1.45)
            for (row_index, col_index), cell in table_artist.get_celld().items():
                if row_index > 0 and col_index == 3 and table_rows[
                        row_index - 1][3]:
                    cell.set_facecolor('#ffebee')
                    cell.get_text().set_color('#b71c1c')
        else:
            ax2.text(0.5, 0.5, 'no manual-U height information',
                     ha='center', va='center', fontsize=10.0)
        if not changed_any and counts_after is not None:
            _figure_note(ax1, 'no manual-U height change vs baseline',
                         fontsize=7.5, color='#2e7d32', x=0.012, y=0.93)
    fig.suptitle(title, fontsize=12.5, y=0.985)
    try:
        fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.95))
    except Exception:  # pragma: no cover - layout is non-fatal
        pass
    return _save_figure(fig, out_path)


# --------------------------------------------------------------------------- #
# figure: per-height route usage comparison (assignment based)
# --------------------------------------------------------------------------- #
def _fig_height_usage(rows_before, rows_after, out_path, title,
                      before_name='baseline', after_name='experiment'):
    counts_before = assignment_height_counts(rows_before)
    counts_after = assignment_height_counts(rows_after)
    if not counts_before and not counts_after:
        raise ValueError('no assignment rows with target heights')
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15.0, 8.6), sharex=True)
    x = np.arange(len(HEIGHT_KEYS))
    width = 0.4
    before_values = [counts_before.get(key, 0) for key in HEIGHT_KEYS]
    after_values = [counts_after.get(key, 0) for key in HEIGHT_KEYS]
    colours = [_height_colour(key) for key in HEIGHT_KEYS]
    ax1.bar(x - width / 2.0, before_values, width=width, color='#9e9e9e',
            edgecolor='#424242', linewidth=0.4, label=str(before_name))
    ax1.bar(x + width / 2.0, after_values, width=width, color=colours,
            edgecolor='#37474f', linewidth=0.4, label=str(after_name))
    ax1.set_ylabel('route count')
    ax1.set_title('Per-height route usage (assignment target heights)',
                  fontsize=11.0)
    ax1.grid(axis='y', linewidth=0.3, color=C_GRID)
    ax1.legend(fontsize=8.0, framealpha=0.9)
    delta = [after - before for after, before in zip(after_values,
                                                     before_values)]
    bar_colours = [C_REMOVED if value < 0 else C_ADDED if value > 0
                   else '#9e9e9e' for value in delta]
    ax2.bar(x, delta, color=bar_colours, edgecolor='#37474f', linewidth=0.4)
    for bar, value in zip(ax2.patches, delta):
        if value:
            ax2.text(bar.get_x() + bar.get_width() / 2.0, value, '%+d' % value,
                     ha='center', va='bottom' if value >= 0 else 'top',
                     fontsize=6.5, color='#37474f')
    ax2.axhline(0.0, color='#424242', linewidth=0.6)
    ax2.set_ylabel('delta (after - baseline)')
    ax2.set_title('Route usage change per physical height', fontsize=10.5)
    ax2.grid(axis='y', linewidth=0.3, color=C_GRID)
    ax2.set_xticks(x)
    ax2.set_xticklabels(['%s\n%+.2f' % (row['label'], row['z_mm'])
                         for row in HEIGHT_ROWS], fontsize=7.0)
    ax2.set_xlabel('physical height (21-height model, z order)')
    fig.suptitle(title, fontsize=12.5, y=0.985)
    fig.subplots_adjust(left=0.07, right=0.985, top=0.93, bottom=0.12,
                        hspace=0.30)
    return _save_figure(fig, out_path)


# --------------------------------------------------------------------------- #
# figure: per-height crossings comparison (experiment vs baseline)
# --------------------------------------------------------------------------- #
def _fig_height_crossings_compare(table_before, table_after, out_path, title,
                                  before_name='baseline',
                                  after_name='experiment'):
    if not table_before or not table_after:
        raise ValueError('empty height table')
    before = {round(row['z_mm'], 6): row for row in table_before}
    after = {round(row['z_mm'], 6): row for row in table_after}
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15.0, 8.6), sharex=True)
    x = np.arange(len(HEIGHT_KEYS))
    width = 0.4
    before_values = [before.get(key, {}).get('crossings', 0)
                     for key in HEIGHT_KEYS]
    after_values = [after.get(key, {}).get('crossings', 0)
                    for key in HEIGHT_KEYS]
    ax1.bar(x - width / 2.0, before_values, width=width, color='#9e9e9e',
            edgecolor='#424242', linewidth=0.4, label=str(before_name))
    ax1.bar(x + width / 2.0, after_values, width=width,
            color=[_height_colour(key) for key in HEIGHT_KEYS],
            edgecolor='#37474f', linewidth=0.4, label=str(after_name))
    ax1.set_ylabel('crossings')
    ax1.set_title('Crossings per physical height: %s vs %s'
                  % (after_name, before_name), fontsize=11.0)
    ax1.grid(axis='y', linewidth=0.3, color=C_GRID)
    ax1.legend(fontsize=8.0, framealpha=0.9)
    delta = [after - before for after, before in zip(after_values,
                                                     before_values)]
    bar_colours = [C_REMOVED if value < 0 else C_ADDED if value > 0
                   else '#9e9e9e' for value in delta]
    ax2.bar(x, delta, color=bar_colours, edgecolor='#37474f', linewidth=0.4)
    for bar, value in zip(ax2.patches, delta):
        if value:
            ax2.text(bar.get_x() + bar.get_width() / 2.0, value, '%+d' % value,
                     ha='center', va='bottom' if value >= 0 else 'top',
                     fontsize=6.5, color='#37474f')
    ax2.axhline(0.0, color='#424242', linewidth=0.6)
    ax2.set_ylabel('delta crossings')
    ax2.set_title('Crossing change per physical height', fontsize=10.5)
    ax2.grid(axis='y', linewidth=0.3, color=C_GRID)
    ax2.set_xticks(x)
    ax2.set_xticklabels(['%s\n%+.2f' % (row['label'], row['z_mm'])
                         for row in HEIGHT_ROWS], fontsize=7.0)
    ax2.set_xlabel('physical height (21-height model, z order)')
    fig.suptitle(title, fontsize=12.5, y=0.985)
    fig.subplots_adjust(left=0.07, right=0.985, top=0.93, bottom=0.12,
                        hspace=0.30)
    return _save_figure(fig, out_path)


# --------------------------------------------------------------------------- #
# figure: changed routes (old dashed grey vs new solid coloured)
# --------------------------------------------------------------------------- #
def _fig_changed_routes(baseline_routes, routes, geometry_before,
                        geometry_after, stats_before, stats_after, out_path,
                        title, max_routes=MAX_CHANGED_ROUTES):
    changed = changed_route_ids(baseline_routes, routes)
    shown = changed
    if len(changed) > int(max_routes):
        stride = int(math.ceil(len(changed) / float(max_routes)))
        shown = changed[::stride][:int(max_routes)]
    fig, ax = plt.subplots(figsize=(13.0, 12.4))
    _draw_board(ax, linewidth=0.8, label='board 150 x 150 mm')
    context = geometry_before.all_flat_arrays()
    if context:
        ax.add_collection(LineCollection(
            context, colors=C_CONTEXT, linewidths=0.25, alpha=0.35,
            zorder=1, label=None))
    old_arrays = []
    new_by_colour = defaultdict(list)
    drawn = 0
    for rid in shown:
        route_old = geometry_before.by_id.get(rid)
        route_new = geometry_after.by_id.get(rid)
        if route_old is not None:
            for part_index, part in enumerate(_parts(route_old)):
                xy = geometry_before.flat_xy.get((rid, part_index))
                if xy is not None:
                    old_arrays.append(xy)
        if route_new is not None:
            for part_index, part in enumerate(_parts(route_new)):
                xy = geometry_after.flat_xy.get((rid, part_index))
                z = _to_float(part.get('z_mm'))
                if xy is None or z is None:
                    continue
                new_by_colour[round(z, 6)].append(xy)
        if route_old is not None and route_new is not None:
            drawn += 1
    if old_arrays:
        ax.add_collection(LineCollection(
            old_arrays, colors=C_BEFORE, linewidths=0.85, linestyles='--',
            alpha=0.9, zorder=3, label='old geometry (baseline, dashed grey)'))
    for key, arrays in new_by_colour.items():
        ax.add_collection(LineCollection(
            arrays, colors=_height_colour(key), linewidths=1.35, alpha=0.95,
            zorder=4))
    handles = [Line2D([0], [0], color=C_BEFORE, linewidth=1.2,
                      linestyle='--', label='old geometry (baseline)'),
               Line2D([0], [0], color=C_NEW, linewidth=1.4,
                      label='new geometry (colour = new flat height)'),
               Line2D([0], [0], color=C_CONTEXT, linewidth=0.8,
                      label='all baseline routes (context)')]
    changed_set = set(changed)
    base_events = _events_for_routes(stats_before, changed_set)
    exp_events = _events_for_routes(stats_after, changed_set)
    n_base = _scatter_crossings(ax, base_events, size=14.0, color='#616161',
                                label='baseline crossing events involving '
                                      'changed routes (%d)' % len(base_events),
                                alpha=0.55, zorder=6)
    n_exp = _scatter_crossings(ax, exp_events, size=14.0, color=C_CROSS,
                               label='new crossing events involving changed '
                                     'routes (%d)' % len(exp_events),
                               alpha=0.85, zorder=7)
    if n_base:
        handles.append(Line2D([0], [0], marker='x', color='#616161',
                              linestyle='none', label='baseline crossings (%d)'
                                                      % n_base))
    if n_exp:
        handles.append(Line2D([0], [0], marker='x', color=C_CROSS,
                              linestyle='none',
                              label='new crossings (%d)' % n_exp))
    _xy_limits(ax, margin=3.0)
    base_total = crossing_total(stats_before)
    exp_total = crossing_total(stats_after)
    if not changed:
        ax.text(BOARD_MM / 2.0, BOARD_MM / 2.0,
                'no route geometry changes vs baseline\n'
                '(all 1024 rounded part signatures identical)',
                ha='center', va='center', fontsize=12.0, color='#2e7d32',
                bbox=dict(boxstyle='round,pad=0.6', fc='#e8f5e9',
                          ec='#2e7d32'))
    ax.set_title('%s\nchanged routes: %d / %d   (drawn %d%s)   '
                 'total crossings: %s -> %s'
                 % (title, len(changed), len(routes), drawn,
                    '' if len(shown) == len(changed)
                    else ', every %d-th' % int(math.ceil(len(changed)
                                                        / float(max_routes))),
                    _fmt_int(base_total), _fmt_int(exp_total)), fontsize=10.8)
    ax.legend(handles=handles, loc='upper right', fontsize=7.2,
              framealpha=0.92)
    return _save_figure(fig, out_path)


# --------------------------------------------------------------------------- #
# router validation figures (P0/P1/P2)
# --------------------------------------------------------------------------- #
def _changed_region(old_route, new_route, pad=8.0, min_span=24.0):
    """XY window around the parts whose stored geometry differs."""
    old_parts = _parts(old_route)
    new_parts = _parts(new_route)
    points = []
    for index in range(max(len(old_parts), len(new_parts))):
        old_part = old_parts[index] if index < len(old_parts) else None
        new_part = new_parts[index] if index < len(new_parts) else None
        try:
            old_sig = _part_signature(old_part) if old_part else None
            new_sig = _part_signature(new_part) if new_part else None
        except (TypeError, ValueError):
            old_sig, new_sig = 'bad', 'good'
        if old_sig == new_sig:
            continue
        for part in (old_part, new_part):
            if part is None:
                continue
            if part.get('kind') == 'flat':
                xy = sample_flat_xy(part, 2.0)
                if xy is not None:
                    points.append(xy)
            else:
                xyz = sample_transition_xyz(part, 0.5)
                if xyz is not None:
                    points.append(xyz[:, :2])
    if not points:
        for part in new_parts or old_parts:
            if part.get('kind') == 'flat':
                xy = sample_flat_xy(part, 2.0)
                if xy is not None:
                    points.append(xy)
    if not points:
        return None
    stacked = np.vstack(points)
    xmin, ymin = stacked.min(axis=0)
    xmax, ymax = stacked.max(axis=0)
    centre_x = (xmin + xmax) / 2.0
    centre_y = (ymin + ymax) / 2.0
    span = max(xmax - xmin, ymax - ymin, float(min_span)) + 2.0 * float(pad)
    xlo = max(-5.0, centre_x - span / 2.0)
    xhi = min(BOARD_MM + 5.0, centre_x + span / 2.0)
    ylo = max(-5.0, centre_y - span / 2.0)
    yhi = min(BOARD_MM + 5.0, centre_y + span / 2.0)
    return dict(xlo=xlo, xhi=xhi, ylo=ylo, yhi=yhi,
                width=xhi - xlo, height=yhi - ylo,
                centre=(centre_x, centre_y))


def _case_route_crossing_count(case, key, route_id):
    mapping = case.get(key)
    if not isinstance(mapping, dict):
        return None
    for probe in (route_id, str(route_id), int(route_id)):
        if probe in mapping:
            value = mapping[probe]
            if isinstance(value, dict):
                value = _pick(value, ('crossings', 'count', 'n'))
            number = _to_float(value)
            if number is not None:
                return int(round(number))
    return None


def _case_crossing_text(case, route_id, before_stats, after_stats):
    before = _to_float(case.get('crossings_before'))
    after = _to_float(case.get('crossings_after'))
    if before is None:
        before = crossing_total(before_stats)
    if after is None:
        after = crossing_total(after_stats)
    parts = []
    delta_text = ''
    if before is not None and after is not None:
        delta_text = '  (delta %s)' % _fmt_delta(after - before)
    parts.append('exact crossings: before=%s  after=%s%s'
                 % (_fmt_int(before), _fmt_int(after), delta_text))
    route_before = _case_route_crossing_count(case, 'route_crossings_before',
                                              route_id)
    route_after = _case_route_crossing_count(case, 'route_crossings_after',
                                             route_id)
    if route_before is not None or route_after is not None:
        parts.append('route R%d crossings: before=%s  after=%s'
                     % (route_id, _fmt_int(route_before),
                        _fmt_int(route_after)))
    note = str(case.get('note') or case.get('annotation') or '').strip()
    if note:
        parts.append(note)
    return '\n'.join(parts)


def _fig_route_validation(old_route, new_route, route_id, case, out_path,
                          before_stats=None, after_stats=None):
    route_reference = new_route or old_route
    case_title = str(case.get('title') or 'case')
    fig = plt.figure(figsize=(16.4, 13.4))
    fig.suptitle('%s   |   route R%d' % (case_title, route_id), fontsize=12.5,
                 y=0.988)
    grid = fig.add_gridspec(2, 2, left=0.055, right=0.975, top=0.855,
                            bottom=0.055, wspace=0.24, hspace=0.28)
    ax_xy = fig.add_subplot(grid[0, 0])
    ax_z = fig.add_subplot(grid[0, 1])
    ax_3d = fig.add_subplot(grid[1, 0], projection='3d')
    ax_zoom = fig.add_subplot(grid[1, 1])

    # ---- (a) old vs new XY overlay on the whole board ---------------------
    _draw_board(ax_xy, linewidth=0.7, label='board 150 x 150 mm')
    if old_route is not None:
        _draw_route_transitions_xy(ax_xy, old_route, C_BEFORE, linewidth=1.0,
                                   alpha=0.9, linestyle='--')
        _draw_route_flat_xy(ax_xy, old_route, lambda z: C_BEFORE,
                            linewidth=1.05, alpha=0.95, linestyle='--')
    if new_route is not None:
        _draw_route_transitions_xy(ax_xy, new_route, C_TRANSITION,
                                   linewidth=1.5, alpha=0.95)
        _draw_route_flat_xy(ax_xy, new_route, _height_colour, linewidth=1.5,
                            alpha=0.98)
        start, end = _route_endpoints_xy(new_route)
        if start is not None:
            ax_xy.plot(start[0], start[1], marker='o', markersize=6.0,
                       color='#2e7d32', markeredgecolor='white', zorder=9,
                       label='source port')
        if end is not None:
            ax_xy.plot(end[0], end[1], marker='s', markersize=6.0,
                       color='#b71c1c', markeredgecolor='white', zorder=9,
                       label='target port')
    _xy_limits(ax_xy, margin=3.0)
    handles = [Line2D([0], [0], color=C_BEFORE, linewidth=1.2,
                      linestyle='--', label='old route (before, dashed grey)'),
               Line2D([0], [0], color=C_NEW, linewidth=1.5,
                      label='new route (colour = flat height)'),
               Line2D([0], [0], color=C_TRANSITION, linewidth=1.2,
                      label='new S-curve transitions')]
    ax_xy.legend(handles=handles, loc='upper right', fontsize=7.0,
                 framealpha=0.9)
    old_len = _route_length(old_route) if old_route is not None else None
    new_len = _route_length(new_route) if new_route is not None else None
    old_heights = len(_route_visited_heights(old_route)) \
        if old_route is not None else 0
    new_heights = len(_route_visited_heights(new_route)) \
        if new_route is not None else 0
    ax_xy.set_title('(a) XY overlay: old vs new\n'
                    'length %.3f -> %.3f mm   heights used %d -> %d'
                    % (old_len or 0.0, new_len or 0.0, old_heights,
                       new_heights), fontsize=9.5)

    # ---- (b) Z vs true 3D arc length --------------------------------------
    old_points, old_s = route_s_z(old_route) if old_route is not None \
        else (None, None)
    new_points, new_s = route_s_z(new_route) if new_route is not None \
        else (None, None)
    if old_points is not None:
        ax_z.plot(old_s, old_points[:, 2], color=C_BEFORE, linestyle='--',
                  linewidth=1.1, label='old route', zorder=3)
    if new_points is not None:
        segments = np.stack([np.column_stack([new_s[:-1], new_points[:-1, 2]]),
                             np.column_stack([new_s[1:], new_points[1:, 2]])],
                            axis=1)
        mid_z = (new_points[:-1, 2] + new_points[1:, 2]) / 2.0
        ax_z.add_collection(LineCollection(
            segments, colors=CMAP(Z_NORM(mid_z)), linewidths=1.6, zorder=4,
            label='new route (colour = z)'))
    visited = _route_visited_heights(route_reference)
    for key in visited:
        colour = _height_colour(key)
        ax_z.axhline(key, color=colour, linewidth=0.6, linestyle=':',
                     alpha=0.75, zorder=2)
        info = _height_info(key)
        ax_z.text(0.995, key, ' %s ' % info['label'], fontsize=6.0,
                  color=colour, ha='right', va='bottom',
                  transform=ax_z.get_yaxis_transform())
    ax_z.set_xlabel('true 3D arc length s (mm)')
    ax_z.set_ylabel('Z (mm)')
    ax_z.grid(linewidth=0.3, color=C_GRID)
    ax_z.set_title('(b) Z vs arc length (flats at their z, S-curves '
                   'interpolated from stored transition_samples)',
                   fontsize=9.0)
    ax_z.legend(fontsize=7.0, framealpha=0.9, loc='upper left')

    # ---- (c) combined 3D old vs new ---------------------------------------
    _draw_glass_box(ax_3d)
    if old_route is not None:
        old_polyline = route_polyline3d(old_route, step_flat=5.0,
                                        step_transition=0.6)
        if old_polyline is not None and len(old_polyline) >= 2:
            display = old_polyline.copy()
            display[:, 2] *= Z_EXAG
            ax_3d.plot(display[:, 0], display[:, 1], display[:, 2],
                       color=C_BEFORE, linestyle='--', linewidth=1.1,
                       label='old route')
    if new_route is not None:
        new_polyline = route_polyline3d(new_route, step_flat=2.0,
                                        step_transition=0.25)
        if new_polyline is not None and len(new_polyline) >= 2:
            segments, colours = _colour_segments(new_polyline)
            display = segments.copy()
            display[:, :, 2] *= Z_EXAG
            if display is not None:
                ax_3d.add_collection3d(Line3DCollection(
                    display, colors=colours, linewidths=2.0, alpha=0.98),
                    autolim=False)
    _set_3d_axes(ax_3d, title='(c) combined 3D view (old dashed grey vs new '
                              'coloured by z; z x%.0f)' % Z_EXAG,
                 elev=24, azim=-58)

    # ---- (d) zoomed local overlay around the changed region ---------------
    window = _changed_region(old_route, new_route)
    _draw_board(ax_zoom, linewidth=0.7)
    if window is None:
        window = dict(xlo=-2.0, xhi=BOARD_MM + 2.0, ylo=-2.0,
                      yhi=BOARD_MM + 2.0, width=BOARD_MM + 4.0,
                      height=BOARD_MM + 4.0, centre=(BOARD_MM / 2.0,
                                                     BOARD_MM / 2.0))
    ax_zoom.set_xlim(window['xlo'], window['xhi'])
    ax_zoom.set_ylim(window['ylo'], window['yhi'])
    ax_zoom.set_aspect('equal', adjustable='box')
    ax_zoom.set_xlabel('X (mm)')
    ax_zoom.set_ylabel('Y (mm)')
    ax_zoom.grid(linewidth=0.3, color=C_GRID)
    if old_route is not None:
        _draw_route_transitions_xy(ax_zoom, old_route, C_BEFORE,
                                   linewidth=1.2, alpha=0.85,
                                   linestyle='--')
        _draw_route_flat_xy(ax_zoom, old_route, lambda z: C_BEFORE,
                            linewidth=1.3, alpha=0.9, linestyle='--')
    if new_route is not None:
        _draw_route_transitions_xy(ax_zoom, new_route, C_TRANSITION,
                                   linewidth=1.8, alpha=0.95)
        _draw_route_flat_xy(ax_zoom, new_route, _height_colour, linewidth=2.0,
                            alpha=0.98)
    route_before_events = [event for event in _events_for_routes(
        before_stats, [route_id]) if _event_xy(event) is not None]
    route_after_events = [event for event in _events_for_routes(
        after_stats, [route_id]) if _event_xy(event) is not None]
    inside = lambda event: (window['xlo'] <= _event_xy(event)[0]  # noqa: E731
                            <= window['xhi'] and window['ylo']
                            <= _event_xy(event)[1] <= window['yhi'])
    before_inside = [event for event in route_before_events if inside(event)]
    after_inside = [event for event in route_after_events if inside(event)]
    _scatter_crossings(ax_zoom, before_inside, size=55.0, color='#616161',
                       marker='x', alpha=0.8, zorder=8)
    _scatter_crossings(ax_zoom, after_inside, size=65.0, color=C_CROSS,
                       marker='+', alpha=0.95, zorder=9)
    zoom_legend = [Line2D([0], [0], marker='x', color='#616161',
                          linestyle='none', markersize=8,
                          label='old crossings in window (%d)'
                                % len(before_inside)),
                   Line2D([0], [0], marker='+', color=C_CROSS,
                          linestyle='none', markersize=9,
                          label='new crossings in window (%d)'
                                % len(after_inside))]
    ax_zoom.legend(handles=zoom_legend, loc='upper right', fontsize=7.0,
                   framealpha=0.9)
    ax_zoom.set_title('(d) local zoom around changed region: %.1f x %.1f mm '
                      'window at (%.1f, %.1f)'
                      % (window['width'], window['height'],
                         window['centre'][0], window['centre'][1]),
                      fontsize=9.0)

    # ---- exact crossing annotation ---------------------------------------
    annotation = _case_crossing_text(case, route_id, before_stats, after_stats)
    fig.text(0.5, 0.945, annotation, ha='center', va='top', fontsize=8.6,
             color='#4a148c',
             bbox=dict(boxstyle='round,pad=0.45', fc='#f3e5f5',
                       ec='#8e24aa'))
    return _save_figure(fig, out_path)


# --------------------------------------------------------------------------- #
# compare figures (G1/G2a/G2b/G3)
# --------------------------------------------------------------------------- #
def _experiment_colour(name, index):
    text = str(name).lower()
    if 'baseline' in text:
        return EXPERIMENT_COLORS['baseline']
    for key, colour in EXPERIMENT_COLORS.items():
        if key != 'baseline' and key.lower() in text:
            return colour
    return _FALLBACK_COLORS[index % len(_FALLBACK_COLORS)]


def _normalize_summaries(summaries):
    normalized = []
    for index, entry in enumerate(summaries or ()):
        if not isinstance(entry, dict):
            continue
        name = str(entry.get('name') or entry.get('experiment')
                   or entry.get('label') or 'experiment_%d' % (index + 1))
        crossings = _to_float(entry.get('crossings'))
        if crossings is None:
            crossings = _to_float(entry.get('final_crossings'))
        if crossings is None:
            crossings = crossing_total(entry.get('crossing_stats'))
        normalized.append(dict(
            name=name,
            crossings=int(round(crossings)) if crossings is not None else None,
            per_height=_normalize_per_height(
                entry.get('per_height') or entry.get('per_height_crossings')),
            routes_changed=_to_int_or_none(entry.get('routes_changed')),
            manual_changed=_to_int_or_none(entry.get('manual_changed')),
            mid_transitions=_to_int_or_none(entry.get('mid_transitions')),
            raw=entry,
        ))
    return normalized


def _to_int_or_none(value):
    number = _to_float(value)
    if number is None:
        return None
    return int(round(number))


def _normalize_per_height(per_height):
    if not isinstance(per_height, dict):
        return None
    out = {}
    for key, value in per_height.items():
        z_key = _normalize_height_key(key)
        number = _to_float(value)
        if z_key is None or number is None:
            continue
        out[z_key] = int(round(number))
    return out or None


def _fig_compare_crossings(summaries, out_path, baseline_reference,
                           title='Total crossings vs baseline reference'):
    names = [summary['name'] for summary in summaries]
    values = [summary['crossings'] if summary['crossings'] is not None else 0
              for summary in summaries]
    x = np.arange(len(names))
    colours = [_experiment_colour(name, index)
               for index, name in enumerate(names)]
    fig, ax = plt.subplots(figsize=(11.8, 6.4))
    bars = ax.bar(x, values, color=colours, edgecolor='#37474f',
                  linewidth=0.6)
    reference = float(baseline_reference)
    ax.axhline(reference, color='#b71c1c', linewidth=1.2, linestyle='-.',
               label='baseline reference = %d' % int(round(reference)))
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2.0, value,
                '%d\n(%s)' % (value, _fmt_delta(value - reference)),
                ha='center', va='bottom', fontsize=8.0)
    ax.set_xticks(x)
    ax.set_xticklabels(names, fontsize=9.0)
    ax.set_ylabel('total crossings')
    spread = max(values + [reference, 1]) - min(values + [0])
    ax.set_ylim(max(0.0, min(values + [reference]) - 0.25 * spread),
                max(values + [reference]) + 0.25 * spread)
    ax.grid(axis='y', linewidth=0.3, color=C_GRID)
    ax.legend(fontsize=8.0, framealpha=0.9)
    ax.set_title('%s\n(bar labels: crossings / delta vs %d)'
                 % (title, int(round(reference))), fontsize=11.0)
    return _save_figure(fig, out_path)


def _fig_compare_delta(summaries, out_path, baseline_reference,
                       title='Crossings delta vs baseline reference'):
    names = []
    deltas = []
    for summary in summaries:
        if summary['crossings'] is None:
            continue
        names.append(summary['name'])
        deltas.append(summary['crossings'] - float(baseline_reference))
    if not names:
        raise ValueError('no summary with a crossing count')
    x = np.arange(len(names))
    colours = [C_REMOVED if delta < 0 else C_ADDED if delta > 0
               else '#9e9e9e' for delta in deltas]
    fig, ax = plt.subplots(figsize=(11.8, 6.2))
    bars = ax.bar(x, deltas, color=colours, edgecolor='#37474f',
                  linewidth=0.6)
    for bar, delta, name in zip(bars, deltas, names):
        percent = (100.0 * delta / float(baseline_reference)
                   if baseline_reference else 0.0)
        ax.text(bar.get_x() + bar.get_width() / 2.0, delta,
                '%+d\n(%+.2f%%)' % (int(round(delta)), percent),
                ha='center', va='bottom' if delta >= 0 else 'top',
                fontsize=8.0)
    ax.axhline(0.0, color='#424242', linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(names, fontsize=9.0)
    ax.set_ylabel('delta crossings (experiment - %d)'
                  % int(round(baseline_reference)))
    if abs(max(deltas + [0.0])) < 1e-9 and abs(min(deltas + [0.0])) < 1e-9:
        ax.set_ylim(-1.0, 1.0)
    ax.grid(axis='y', linewidth=0.3, color=C_GRID)
    handles = [Line2D([0], [0], color=C_REMOVED, linewidth=8,
                      label='fewer crossings than baseline'),
               Line2D([0], [0], color=C_ADDED, linewidth=8,
                      label='more crossings than baseline')]
    ax.legend(handles=handles, fontsize=8.0, framealpha=0.9)
    ax.set_title(title, fontsize=11.0)
    return _save_figure(fig, out_path)


def _fig_compare_per_height(summaries, out_path, title='Per-height crossing '
                            'distribution by experiment'):
    usable = [summary for summary in summaries
              if isinstance(summary.get('per_height'), dict)
              and summary['per_height']]
    fig, ax = plt.subplots(figsize=(16.0, 7.2))
    if not usable:
        ax.axis('off')
        ax.text(0.5, 0.5, 'per-height crossing data unavailable in all '
                          'summaries (per_height = None)',
                ha='center', va='center', fontsize=12.0, color='#b71c1c')
        ax.set_title(title, fontsize=11.0)
        return _save_figure(fig, out_path)
    x = np.arange(len(HEIGHT_KEYS))
    count = len(usable)
    width = min(0.8 / max(count, 1), 0.26)
    for index, summary in enumerate(usable):
        values = [summary['per_height'].get(key, 0) for key in HEIGHT_KEYS]
        offset = (index - (count - 1) / 2.0) * width
        ax.bar(x + offset, values, width=width,
               color=_experiment_colour(summary['name'], index),
               edgecolor='#37474f', linewidth=0.35,
               label='%s (total %s)'
                     % (summary['name'], _fmt_int(summary['crossings'])))
    ax.set_xticks(x)
    ax.set_xticklabels(['%s\n%+.2f' % (row['label'], row['z_mm'])
                        for row in HEIGHT_ROWS], fontsize=7.0)
    ax.set_xlabel('physical height (21-height model, z order)')
    ax.set_ylabel('crossings')
    ax.grid(axis='y', linewidth=0.3, color=C_GRID)
    ax.legend(fontsize=8.0, framealpha=0.9, ncol=2)
    ax.set_title(title, fontsize=11.0)
    return _save_figure(fig, out_path)


def _fig_compare_table(summaries, out_path, baseline_reference,
                       title='G1/G2a/G2b/G3 comparison'):
    headers = ['experiment', 'crossings', 'delta', 'delta %', 'routes changed',
               'manual changed', 'mid transitions']
    rows = []
    for summary in summaries:
        crossings = summary['crossings']
        delta = (crossings - float(baseline_reference)
                 if crossings is not None else None)
        percent = (100.0 * delta / float(baseline_reference)
                   if (delta is not None and baseline_reference) else None)
        rows.append([
            str(summary['name']),
            _fmt_int(crossings),
            _fmt_delta(delta),
            ('%+.2f%%' % percent) if percent is not None else 'n/a',
            _fmt_int(summary['routes_changed']),
            _fmt_int(summary['manual_changed']),
            _fmt_int(summary['mid_transitions']),
        ])
    fig, ax = plt.subplots(figsize=(13.2, 1.5 + 0.5 * max(len(rows), 1)))
    ax.axis('off')
    ax.set_title('%s   (baseline reference = %d)'
                 % (title, int(round(baseline_reference))), fontsize=11.5,
                 pad=14)
    table = ax.table(cellText=rows, colLabels=headers, loc='center',
                     cellLoc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(9.0)
    table.scale(1.0, 1.55)
    for (row_index, col_index), cell in table.get_celld().items():
        if row_index == 0:
            cell.set_facecolor('#37474f')
            cell.get_text().set_color('white')
            cell.get_text().set_fontweight('bold')
            continue
        text = rows[row_index - 1][col_index]
        if col_index in (2, 3) and text not in ('n/a', 'n/a'):
            try:
                value = float(text.replace('%', '').replace('+', ''))
            except ValueError:
                value = 0.0
            if value < 0:
                cell.set_facecolor('#e8f5e9')
                cell.get_text().set_color('#1b5e20')
            elif value > 0:
                cell.set_facecolor('#ffebee')
                cell.get_text().set_color('#b71c1c')
    return _save_figure(fig, out_path)


# --------------------------------------------------------------------------- #
# summaries for plot_compare
# --------------------------------------------------------------------------- #
def build_summary(run_dir, name=None, baseline_dir=None):
    """Build one ``plot_compare`` summary dict from a real run directory."""
    run_dir = Path(run_dir)
    bundle = _load_bundle(run_dir)
    routes = bundle['routes']
    stats = bundle['stats']
    if routes is None and stats is None:
        raise FileNotFoundError('no routes_l3d.json / crossing_stats.json '
                                'under %s' % run_dir)
    crossings = crossing_total(stats)
    per_height = None
    table = None
    if stats is not None or routes is not None:
        table = height_table(stats, routes=routes)
        per_height = OrderedDict((row['label'], int(row['crossings']))
                                 for row in table)
    routes_changed = None
    manual_changed = None
    mid_transitions = None
    if routes is not None:
        mid_transitions = int(sum(_n_mid_transitions(route)
                                  for route in routes))
        if baseline_dir is not None:
            if Path(baseline_dir) == run_dir:
                routes_changed = 0
                manual_changed = 0
            else:
                baseline_routes = load_routes(baseline_dir)
                if baseline_routes:
                    changed = changed_route_ids(baseline_routes, routes)
                    routes_changed = len(changed)
                    changed_set = set(changed)
                    manual_changed = int(sum(
                        1 for route in routes
                        if _route_id(route) in changed_set
                        and (_route_is_manual(route)
                             or any(_route_is_manual(old)
                                    for old in baseline_routes
                                    if _route_id(old) == _route_id(route)))))
    return dict(name=str(name or run_dir.name),
                crossings=int(crossings) if crossings is not None else None,
                per_height=per_height,
                routes_changed=routes_changed,
                manual_changed=manual_changed,
                mid_transitions=mid_transitions)


def auto_summaries(baseline_dir=None):
    """Summaries of the baseline + the G1/G3_cold/G2a/G2b/G3 run directories."""
    baseline_dir = Path(baseline_dir or PATHS.BASELINE_AUTHORITY)
    candidates = [
        ('baseline', Path(PATHS.BASELINE_AUTHORITY)),
        ('G1', Path(PATHS.DIRS['G1'])),
        ('G3_cold', Path(PATHS.DIRS['fair']) / 'G3_cold'),
        ('G2a', Path(PATHS.DIRS['G2a'])),
        ('G2b', Path(PATHS.DIRS['G2b'])),
        ('G3', Path(PATHS.DIRS['G3'])),
    ]
    summaries = []
    for name, path in candidates:
        routes_path = _find_input(path, 'routes_l3d.json')
        stats_path = _find_input(path, 'crossing_stats.json')
        if routes_path is None and stats_path is None:
            _log('compare: skip %s (no routes/crossing stats)' % path,
                 level='warn')
            continue
        try:
            summaries.append(build_summary(path, name, baseline_dir))
        except Exception as exc:  # noqa: BLE001 - one bad run is not fatal
            _log('compare: could not summarise %s: %s' % (path, exc),
                 level='warn')
    return summaries


def load_summaries(path):
    """Load a summaries JSON file (list or ``{'summaries': [...]}``)."""
    payload = _read_json(path)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ('summaries', 'experiments', 'runs'):
            if isinstance(payload.get(key), list):
                return payload[key]
    raise ValueError('summaries JSON %r is not a list of summary dicts'
                     % str(path))


# --------------------------------------------------------------------------- #
# case loading for router validation
# --------------------------------------------------------------------------- #
def _as_int_list(value):
    if value is None:
        return []
    if isinstance(value, bool):
        return []
    if isinstance(value, int):
        return [int(value)]
    if isinstance(value, str):
        tokens = [token.strip() for token in
                  value.replace(';', ',').split(',') if token.strip()]
        out = []
        for token in tokens:
            try:
                out.append(int(float(token)))
            except (TypeError, ValueError):
                continue
        return out
    out = []
    for item in value:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out


def _stage_name_from_path(path):
    """``P0``/``P1``/``P2`` from a case-file name or a ``*_p0`` schema."""
    stem = Path(path).stem.upper()
    match = re.match(r'(P[0-2])', stem)
    if match:
        return match.group(1)
    for token in ('P0', 'P1', 'P2'):
        if token in stem:
            return token
    return str(Path(path).stem)


def _first_number(mapping, keys):
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        number = _to_float(mapping.get(key))
        if number is not None:
            return number
    return None


def _first_text(mapping, keys):
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ''):
            return str(value)
    return None


def _collect_route_ids(payload, limit=64):
    """Best-effort route-id extraction for an unknown validation payload."""
    ids = []
    seen = set()

    def _add(value):
        if isinstance(value, bool) or len(ids) >= limit:
            return
        if isinstance(value, int):
            candidate = int(value)
        elif isinstance(value, dict):
            candidate = None
            for key in ('route_id', 'id', 'rid'):
                number = _to_float(value.get(key))
                if number is not None:
                    candidate = int(round(number))
                    break
            if candidate is None:
                return
        else:
            return
        if candidate not in seen:
            seen.add(candidate)
            ids.append(candidate)

    for key in ('route_ids', 'changed_route_ids', 'focus_routes',
                'hotspot_routes', 'selected_routes', 'joint_routes',
                'single_routes', 'routes'):
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, dict):
            _add(value)
        elif isinstance(value, (list, tuple)):
            for item in value:
                _add(item)
        if ids:
            break
    return ids


def _case_from_validation_payload(payload, path):
    """Convert a ``run_router_validation`` evidence JSON into case dicts.

    The router-validation runner stores one rich evidence JSON per phase
    (``p0_case.json``, ``p1_case.json``, ``p2_comparison.json``) whose
    before/after layouts are real ``routes_l3d.json`` directories.  This
    adapter maps them onto the ``plot_router_validation`` case contract
    (``route_ids`` / ``before_dir`` / ``after_dir`` / ``title`` / crossing
    numbers); it never alters any geometry.
    """
    if not isinstance(payload, dict):
        return None
    schema = str(payload.get('schema') or '')
    stage = _stage_name_from_path(path)
    baseline_dir = _first_text(payload, ('baseline_dir', 'before_dir',
                                         'baseline'))
    artifacts = payload.get('artifacts') or {}
    run_dir = _first_text(artifacts, ('stage', 'run_dir', 'layout_dir'))
    cases = []

    if schema.endswith('_p0'):
        selected = payload.get('selected_route') or {}
        route_id = selected.get('route_id')
        route_ids = _as_int_list([route_id]) if route_id is not None else []
        crossings = payload.get('crossings') or {}
        validation = payload.get('validation') or {}
        before_total = (_first_number(payload, ('baseline_crossings',
                                                'crossings_before'))
                        or _first_number(crossings, ('old_total',
                                                     'before_total')))
        after_total = (_first_number(crossings, ('new_total', 'after_total'))
                       or _first_number(validation, ('crossings',)))
        old_route = _first_number(crossings, ('old_route_crossings',))
        new_route = _first_number(crossings, ('new_route_crossings',))
        geometry = payload.get('geometry') or {}
        old_geom = geometry.get('old') or {}
        new_geom = geometry.get('new') or {}
        note = ('P0: body height %.2f -> %.2f mm, body XY signature %s -> %s; '
                'z-only reference max XY displacement %.3f mm'
                % (_to_float(old_geom.get('target_z_mm')) or 0.0,
                   _to_float(new_geom.get('target_z_mm')) or 0.0,
                   str(old_geom.get('body_xy_signature_sha1') or '?')[:12],
                   str(new_geom.get('body_xy_signature_sha1') or '?')[:12],
                   _to_float((payload.get('z_only_reference') or {}).get(
                       'max_xy_displacement_mm')) or 0.0))
        cases.append(dict(
            title='%s simultaneous XY+Z single-route re-route' % stage,
            route_ids=route_ids, before_dir=baseline_dir,
            after_dir=run_dir or str(Path(path).parent),
            crossings_before=before_total, crossings_after=after_total,
            route_crossings_before=({route_ids[0]: int(old_route)}
                                    if route_ids and old_route is not None
                                    else None),
            route_crossings_after=({route_ids[0]: int(new_route)}
                                   if route_ids and new_route is not None
                                   else None),
            note=note))
        return cases

    if schema.endswith('_p1'):
        selection = payload.get('selection') or {}
        route_ids = _as_int_list(selection.get('routes'))
        if not route_ids:
            route_ids = _collect_route_ids(payload)
        comparison = payload.get('comparison') or {}
        totals = comparison.get('totals') or {}
        before_total = (_first_number(payload, ('baseline_crossings',
                                                'crossings_before'))
                        or _first_number(totals, ('baseline',)))
        after_total = (_first_number(totals, ('joint',))
                       or _first_number(payload, ('final_crossings',)))
        note = ('P1: single-only total %s, sequential-single total %s, joint '
                'total %s (joint extra over single %s)'
                % (_fmt_int(_first_number(totals, ('single_only',))),
                   _fmt_int(_first_number(totals, ('sequential_single',))),
                   _fmt_int(after_total),
                   _fmt_delta(_first_number(comparison,
                                            ('joint_extra_over_single',)))))
        cases.append(dict(
            title='%s single-only vs joint re-route (%d routes)'
                  % (stage, len(route_ids)),
            route_ids=route_ids, before_dir=baseline_dir,
            after_dir=run_dir or str(Path(path).parent),
            crossings_before=before_total, crossings_after=after_total,
            note=note))
        return cases

    if schema.endswith('_p2'):
        comparison = payload.get('comparison') or {}
        hotspot = payload.get('hotspot') or {}
        route_ids = _as_int_list(hotspot.get('route_ids')
                                 or hotspot.get('routes')
                                 or hotspot.get('chosen'))
        if not route_ids:
            route_ids = _collect_route_ids(
                dict(routes=payload.get('per_route') or ()))
        before_total = _first_number(comparison, ('total_before',))
        z_dir = _first_text(artifacts, ('z_only_stage', 'z_only'))
        xyz_dir = _first_text(artifacts, ('xy_z_stage', 'xy_z'))
        z_total = _first_number(comparison, ('z_only_total_after',))
        xyz_total = _first_number(comparison, ('xy_z_total_after',))
        extra = _first_number(comparison, ('extra_removed_by_xy',))
        z_note = ('P2 A (Z-only): %d routes, total crossings %s -> %s'
                  % (len(route_ids), _fmt_int(before_total),
                     _fmt_int(z_total)))
        xyz_note = ('P2 B (XY+Z): %d routes, total crossings %s -> %s; '
                    'XY+Z removes %s more crossing(s) than Z-only'
                    % (len(route_ids), _fmt_int(before_total),
                       _fmt_int(xyz_total), _fmt_delta(extra)))
        if z_dir:
            cases.append(dict(
                title='%s A: Z-only vs baseline' % stage,
                route_ids=route_ids, before_dir=baseline_dir,
                after_dir=z_dir, crossings_before=before_total,
                crossings_after=z_total, note=z_note))
        if xyz_dir:
            cases.append(dict(
                title='%s B: XY+Z vs baseline' % stage,
                route_ids=route_ids, before_dir=baseline_dir,
                after_dir=xyz_dir, crossings_before=before_total,
                crossings_after=xyz_total, note=xyz_note))
            if z_dir:
                cases.append(dict(
                    title='%s C: XY+Z vs Z-only' % stage,
                    route_ids=route_ids, before_dir=z_dir,
                    after_dir=xyz_dir, crossings_before=z_total,
                    crossings_after=xyz_total,
                    note=('P2 C: incremental XY+Z over the Z-only layout; '
                          'total crossings %s -> %s'
                          % (_fmt_int(z_total), _fmt_int(xyz_total)))))
        return cases
    return None


def _load_cases_file(path):
    path = Path(path)
    payload = _read_json(path)
    if isinstance(payload, dict):
        schema = str(payload.get('schema') or '')
        if schema.startswith('xyz_router_validation_v1') \
                and not schema.endswith('plotdata'):
            adapted = _case_from_validation_payload(payload, path)
            if adapted:
                return adapted
    if isinstance(payload, list):
        raw = payload
        defaults = {}
    elif isinstance(payload, dict):
        defaults = {}
        for key in ('before_dir', 'after_dir', 'baseline_dir', 'run_dir',
                    'crossings_before', 'crossings_after'):
            value = payload.get(key)
            if value not in (None, ''):
                defaults[key] = value
        if isinstance(payload.get('cases'), list):
            raw = payload['cases']
        elif payload.get('route_ids') or payload.get('route_id') \
                or payload.get('routes') or payload.get('changed_route_ids'):
            raw = [payload]
        else:
            raise ValueError('case JSON %r has no route_ids / cases' % str(path))
    else:
        raise ValueError('case JSON %r is neither a list nor a dict'
                         % str(path))
    base = path.parent
    cases = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        item = dict(item)
        for key, value in defaults.items():
            item.setdefault(key, value)
        for key in ('before_dir', 'after_dir', 'baseline_dir', 'run_dir'):
            value = item.get(key)
            if not value:
                continue
            candidate = Path(str(value))
            if not candidate.is_absolute():
                resolved = base / candidate
                if resolved.exists():
                    item[key] = str(resolved)
        cases.append(item)
    return cases


def load_cases(path):
    """Load P0/P1/P2 cases from a JSON file or a directory of JSON files.

    When ``path`` is a directory the tree is searched recursively (files whose
    name contains ``case`` or ``comparison`` are preferred, otherwise every
    JSON is tried); directories whose name starts with ``_`` are skipped.
    """
    path = Path(path)
    if path.is_dir():
        candidate_files = []
        for child in sorted(path.rglob('*.json')):
            try:
                relative = child.relative_to(path)
            except ValueError:
                relative = Path(child.name)
            if any(part.startswith('_') for part in relative.parts):
                continue
            name = child.name.lower()
            if 'case' in name or 'comparison' in name:
                candidate_files.append(child)
        if not candidate_files:
            for child in sorted(path.rglob('*.json')):
                try:
                    relative = child.relative_to(path)
                except ValueError:
                    relative = Path(child.name)
                if any(part.startswith('_') for part in relative.parts):
                    continue
                candidate_files.append(child)
        cases = []
        for child in candidate_files:
            try:
                cases.extend(_load_cases_file(child))
            except Exception as exc:  # noqa: BLE001 - one bad file is fine
                _log('cases: skip %s: %s' % (child, exc), level='warn')
        return cases
    return _load_cases_file(path)


def normalize_cases(cases):
    """Normalise case dicts: route ids to int, default dirs/titles."""
    normalized = []
    for index, raw in enumerate(cases or ()):
        if not isinstance(raw, dict):
            continue
        route_ids = []
        for key in ('route_ids', 'routes', 'route_id', 'changed_route_ids',
                    'focus_routes', 'candidates'):
            route_ids = _as_int_list(raw.get(key))
            if route_ids:
                break
        before_dir = (raw.get('before_dir') or raw.get('before')
                      or raw.get('baseline_dir') or None)
        after_dir = (raw.get('after_dir') or raw.get('after')
                     or raw.get('run_dir') or raw.get('experiment_dir')
                     or raw.get('route_run_dir') or None)
        title = str(raw.get('title') or raw.get('name')
                    or raw.get('label') or raw.get('description')
                    or 'case %d' % (index + 1))
        case = dict(raw)
        case.update(dict(index=index + 1, title=title, route_ids=route_ids,
                         before_dir=before_dir, after_dir=after_dir))
        normalized.append(case)
    return normalized


def _resolve_case_directory(value, default_dir):
    """Resolve a case directory, treating ``baseline`` as the baseline dir."""
    if value in (None, ''):
        return Path(default_dir)
    text = str(value).strip()
    if text.lower() in ('baseline', 'baseline_authoritative', 'authoritative',
                        'baseline_dir'):
        return Path(default_dir)
    return Path(text)


# --------------------------------------------------------------------------- #
# public: baseline dashboard
# --------------------------------------------------------------------------- #
def plot_baseline(run_dir=None, out_dir=None, prefix='baseline', quiet=None):
    """Draw the authoritative-baseline figure set from real geometry only.

    Returns ``{'written': [png paths], 'errors': [...], 'skipped': [...]}``.
    """
    if quiet is not None:
        set_quiet(quiet)
    started = time.time()
    result = _new_result()
    run_dir = Path(run_dir or PATHS.BASELINE_AUTHORITY)
    out_dir = Path(out_dir or (Path(PATHS.DIRS['plots']) / 'baseline'))
    out_dir = _prepare_out_dir(result, out_dir)
    if out_dir is None:
        return result
    bundle = _load_bundle(run_dir)
    routes = bundle['routes']
    stats = bundle['stats']
    assignment = bundle['assignment']
    if routes is None:
        result['errors'].append(dict(figure='*',
                                     error='routes_l3d.json not found under '
                                           '%s' % run_dir))
        return _finish(result, out_dir, 'baseline', run_dir, prefix,
                       dict(dir=str(run_dir)))
    geometry = RouteGeometry(routes)
    table = height_table(stats, geometry=geometry)
    total = crossing_total(stats)

    title_3d = ('Authoritative baseline: %d routes, %s crossings   '
                '(colour = primary physical height)'
                % (len(routes), _fmt_int(total)))
    _guarded(result, '3d_overview', _fig_3d_overview, geometry,
             out_dir / ('%s_3d_overview.png' % prefix), title=title_3d,
             total_crossings=total)
    _guarded(result, 'height_panels', _fig_height_panels, geometry, stats,
             out_dir / ('%s_height_panels.png' % prefix),
             title=('Baseline per-physical-height XY views: all %d routes '
                    '(manual-U red, non-manual blue)' % len(routes)),
             total_crossings=total)
    _guarded(result, 'height_crossings', _fig_height_bars, table,
             out_dir / ('%s_height_crossings.png' % prefix),
             title=('Baseline crossings and route count per physical height '
                    '(from crossing_stats.json planes)'),
             total_crossings=total)
    _guarded(result, 'crossing_hotspots', _fig_crossing_hotspots, stats,
             out_dir / ('%s_crossing_hotspots.png' % prefix),
             title='Baseline crossing hot-spot density (real crossing events)',
             total_crossings=total, table=table)
    if _manual_count(assignment) > 0:
        _guarded(result, 'manual_u_heights', _fig_manual_u_heights,
                 assignment, None,
                 out_dir / ('%s_manual_u_heights.png' % prefix),
                 title=('Baseline manual-U height assignment (%d routes)'
                        % _manual_count(assignment)),
                 after_name='after', include_table=False)
    else:
        result['skipped'].append(dict(
            figure='manual_u_heights',
            reason='no manual_group rows in assignment_1024.csv'))

    data = dict(
        dir=str(run_dir),
        routes_path=bundle['routes_path'],
        stats_path=bundle['stats_path'],
        assignment_path=bundle['assignment_path'],
        routes=len(routes),
        crossings=total,
        manual_routes=_manual_count(assignment),
        mid_transitions=int(sum(_n_mid_transitions(route) for route in routes)),
        sampling_failures=geometry.sampling_failures,
        heights=len(table),
        runtime_seconds=round(time.time() - started, 3),
    )
    return _finish(result, out_dir, 'baseline', run_dir, prefix, data)


# --------------------------------------------------------------------------- #
# public: experiment dashboard
# --------------------------------------------------------------------------- #
def plot_experiment(run_dir=None, baseline_dir=None, out_dir=None, prefix=None,
                    quiet=None):
    """Draw the full experiment figure set (real geometry + real crossings)."""
    if quiet is not None:
        set_quiet(quiet)
    started = time.time()
    result = _new_result()
    run_dir = Path(run_dir or PATHS.BASELINE_AUTHORITY)
    baseline_dir = Path(baseline_dir or PATHS.BASELINE_AUTHORITY)
    prefix = str(prefix or run_dir.name)
    out_dir = Path(out_dir or (Path(PATHS.DIRS['plots']) / prefix))
    out_dir = _prepare_out_dir(result, out_dir)
    if out_dir is None:
        return result

    bundle = _load_bundle(run_dir)
    routes = bundle['routes']
    stats = bundle['stats']
    assignment = bundle['assignment']
    if routes is None:
        result['errors'].append(dict(figure='*',
                                     error='routes_l3d.json not found under '
                                           '%s' % run_dir))
        return _finish(result, out_dir, 'experiment', run_dir, prefix,
                       dict(dir=str(run_dir)))
    base_bundle = _load_bundle(baseline_dir)
    base_routes = base_bundle['routes']
    base_stats = base_bundle['stats']
    base_assignment = base_bundle['assignment']
    if base_routes is None:
        result['skipped'].append(dict(
            figure='changed_routes / height_crossings_compare',
            reason='baseline routes_l3d.json not found under %s'
                   % baseline_dir))

    geometry = RouteGeometry(routes)
    table = height_table(stats, geometry=geometry)
    total = crossing_total(stats)
    base_total = crossing_total(base_stats)

    title_3d = ('%s: %d routes, %s crossings (baseline %s)   '
                '(colour = primary physical height)'
                % (prefix, len(routes), _fmt_int(total), _fmt_int(base_total)))
    _guarded(result, '3d_overview', _fig_3d_overview, geometry,
             out_dir / ('%s_3d_overview.png' % prefix), title=title_3d,
             total_crossings=total)
    _guarded(result, 'height_panels', _fig_height_panels, geometry, stats,
             out_dir / ('%s_height_panels.png' % prefix),
             title=('%s per-physical-height XY views: %d routes '
                    '(manual-U red, non-manual blue)' % (prefix, len(routes))),
             total_crossings=total)
    _guarded(result, 'height_crossings', _fig_height_bars, table,
             out_dir / ('%s_height_crossings.png' % prefix),
             title=('%s crossings and route count per physical height'
                    % prefix), total_crossings=total)
    _guarded(result, 'crossing_hotspots', _fig_crossing_hotspots, stats,
             out_dir / ('%s_crossing_hotspots.png' % prefix),
             title=('%s remaining crossing hot-spot density' % prefix),
             total_crossings=total, table=table)

    if base_routes is not None:
        base_geometry = RouteGeometry(base_routes)
        _guarded(result, 'changed_routes', _fig_changed_routes,
                 base_routes, routes, base_geometry, geometry, base_stats,
                 stats, out_dir / ('%s_changed_routes.png' % prefix),
                 title=('%s changed routes: old baseline geometry vs new'
                        % prefix))
        if base_stats is not None:
            base_table = height_table(base_stats, routes=base_routes)
            _guarded(result, 'height_crossings_compare',
                     _fig_height_crossings_compare, base_table, table,
                     out_dir / ('%s_height_crossings_vs_baseline.png'
                                % prefix),
                     title=('%s crossings per physical height vs baseline'
                            % prefix), before_name='baseline',
                     after_name=prefix)
        if base_assignment:
            _guarded(result, 'height_usage_compare', _fig_height_usage,
                     base_assignment, assignment,
                     out_dir / ('%s_height_usage_compare.png' % prefix),
                     title=('%s per-height route usage vs baseline' % prefix),
                     before_name='baseline', after_name=prefix)
    if _manual_count(assignment) > 0:
        _guarded(result, 'manual_u_heights_compare',
                 _fig_manual_u_heights, base_assignment, assignment,
                 out_dir / ('%s_manual_u_heights_compare.png' % prefix),
                 title=('%s manual-U height assignment: baseline -> %s'
                        % (prefix, prefix)),
                 after_name=prefix)
    else:
        result['skipped'].append(dict(
            figure='manual_u_heights_compare',
            reason='experiment assignment_1024.csv has no manual_group rows'))

    data = dict(
        dir=str(run_dir),
        baseline_dir=str(baseline_dir),
        routes=len(routes),
        crossings=total,
        baseline_crossings=base_total,
        manual_routes=_manual_count(assignment),
        baseline_manual_routes=_manual_count(base_assignment),
        mid_transitions=int(sum(_n_mid_transitions(route) for route in routes)),
        changed_routes=(len(changed_route_ids(base_routes, routes))
                        if base_routes is not None else None),
        sampling_failures=geometry.sampling_failures,
        runtime_seconds=round(time.time() - started, 3),
    )
    return _finish(result, out_dir, 'experiment', run_dir, prefix, data)


# --------------------------------------------------------------------------- #
# public: router validation (P0/P1/P2)
# --------------------------------------------------------------------------- #
def plot_router_validation(baseline_dir=None, cases=None, out_dir=None,
                           prefix='router_validation', quiet=None):
    """Draw the P0/P1/P2 old-vs-new validation figures for given case dicts."""
    if quiet is not None:
        set_quiet(quiet)
    started = time.time()
    result = _new_result()
    baseline_dir = Path(baseline_dir or PATHS.BASELINE_AUTHORITY)
    out_dir = Path(out_dir or (Path(PATHS.DIRS['plots']) / prefix))
    out_dir = _prepare_out_dir(result, out_dir)
    if out_dir is None:
        return result
    normalized = normalize_cases(cases or ())
    if not normalized:
        result['errors'].append(dict(figure='*',
                                     error='no router-validation cases given'))
        return _finish(result, out_dir, 'router_validation', baseline_dir,
                       prefix, dict(cases=0))
    cache = {}

    def _bundle(directory):
        key = str(directory)
        if key not in cache:
            cache[key] = _load_bundle(directory)
        return cache[key]

    case_reports = []
    for case in normalized:
        before_dir = _resolve_case_directory(case.get('before_dir'),
                                             baseline_dir)
        after_value = case.get('after_dir')
        if after_value in (None, ''):
            result['errors'].append(dict(
                figure='case %s' % case['title'],
                error='case has no after_dir'))
            continue
        after_dir = _resolve_case_directory(after_value, baseline_dir)
        before_bundle = _bundle(before_dir)
        after_bundle = _bundle(after_dir)
        before_routes = {_route_id(route): route
                         for route in before_bundle['routes'] or ()}
        after_routes = {_route_id(route): route
                        for route in after_bundle['routes'] or ()}
        before_stats = before_bundle['stats']
        after_stats = after_bundle['stats']
        if not before_routes and not after_routes:
            result['errors'].append(dict(
                figure='case %s' % case['title'],
                error='no routes_l3d.json in before_dir/after_dir'))
            continue
        case_report = dict(
            case=case['title'],
            route_ids=list(case['route_ids']),
            before_dir=str(before_dir),
            after_dir=str(after_dir),
            crossings_before=crossing_total(before_stats),
            crossings_after=crossing_total(after_stats),
            figures=[],
        )
        for route_id in case['route_ids']:
            if len(result['written']) >= MAX_ROUTER_VALIDATION_PNGS:
                result['skipped'].append(dict(
                    figure='route R%d' % route_id,
                    reason='reached the %d-PNG cap per run'
                           % MAX_ROUTER_VALIDATION_PNGS))
                continue
            old_route = before_routes.get(route_id)
            new_route = after_routes.get(route_id)
            if old_route is None and new_route is None:
                result['errors'].append(dict(
                    figure='case %s route R%d' % (case['title'], route_id),
                    error='route id not present in before_dir or after_dir'))
                continue
            if old_route is None or new_route is None:
                result['skipped'].append(dict(
                    figure='case %s route R%d' % (case['title'], route_id),
                    reason='route present in only one of before/after'))
            out_path = out_dir / ('%s_case%02d_route%04d.png'
                                  % (prefix, case['index'], route_id))
            written = _guarded(result, 'case %s route R%d'
                               % (case['title'], route_id),
                               _fig_route_validation, old_route, new_route,
                               route_id, case, out_path,
                               before_stats=before_stats,
                               after_stats=after_stats)
            if written is not None:
                case_report['figures'].append(str(written))
        case_reports.append(case_report)

    data = dict(cases=case_reports,
                runtime_seconds=round(time.time() - started, 3))
    return _finish(result, out_dir, 'router_validation', baseline_dir,
                   prefix, data)


# --------------------------------------------------------------------------- #
# public: G1/G2a/G2b/G3 comparison
# --------------------------------------------------------------------------- #
def plot_compare(summaries, out_dir=None, prefix='compare',
                 baseline_reference=BASELINE_REFERENCE, quiet=None):
    """Draw the G1/G2a/G2b/G3 comparison figures from summary dicts."""
    if quiet is not None:
        set_quiet(quiet)
    started = time.time()
    result = _new_result()
    out_dir = Path(out_dir or (Path(PATHS.DIRS['plots']) / 'compare'))
    out_dir = _prepare_out_dir(result, out_dir)
    if out_dir is None:
        return result
    normalized = _normalize_summaries(summaries)
    if not normalized:
        result['errors'].append(dict(figure='*',
                                     error='no usable summaries given'))
        return _finish(result, out_dir, 'compare', 'summaries', prefix,
                       dict(summaries=0))
    reference = float(baseline_reference)
    for summary in normalized:
        if summary['crossings'] is None:
            summary['crossings'] = None
    _guarded(result, 'compare_crossings', _fig_compare_crossings,
             normalized, out_dir / ('%s_crossings_vs_baseline.png' % prefix),
             reference)
    _guarded(result, 'compare_delta', _fig_compare_delta, normalized,
             out_dir / ('%s_delta_vs_baseline.png' % prefix), reference)
    _guarded(result, 'compare_per_height', _fig_compare_per_height,
             normalized, out_dir / ('%s_per_height_crossings.png' % prefix))
    _guarded(result, 'compare_table', _fig_compare_table, normalized,
             out_dir / ('%s_summary_table.png' % prefix), reference)
    data = dict(
        baseline_reference=reference,
        summaries=[dict(name=summary['name'],
                        crossings=summary['crossings'],
                        routes_changed=summary['routes_changed'],
                        manual_changed=summary['manual_changed'],
                        mid_transitions=summary['mid_transitions'],
                        per_height_available=bool(summary['per_height']))
                   for summary in normalized],
        runtime_seconds=round(time.time() - started, 3),
    )
    return _finish(result, out_dir, 'compare', 'summaries', prefix, data)


# --------------------------------------------------------------------------- #
# watch mode: poll the experiment directories and plot them as they finish
# --------------------------------------------------------------------------- #
#: the five G1/G2a/G2b/G3 experiment layouts of this round (name, directory)
DEFAULT_WATCH_EXPERIMENTS = (
    ('G1', Path(PATHS.DIRS['G1'])),
    ('G3_cold', Path(PATHS.DIRS['fair']) / 'G3_cold'),
    ('G2a', Path(PATHS.DIRS['G2a'])),
    ('G2b', Path(PATHS.DIRS['G2b'])),
    ('G3', Path(PATHS.DIRS['G3'])),
)

#: completion marker files of one experiment layout (summary.json is written
#: after the standard artifact set, so it is a reliable "layout is complete"
#: signal even while the independent validator still runs)
RUN_READY_FILES = ('routes_l3d.json', 'crossing_stats.json', 'summary.json')

#: expected P0/P1/P2 router-validation case files (relative to --cases dir)
EXPECTED_VALIDATION_CASES = ('P0/p0_case.json',
                             'P1/p1_case.json',
                             'P2/p2_comparison.json')


def _run_ready(directory):
    directory = Path(directory)
    for name in RUN_READY_FILES:
        path = directory / name
        try:
            if not path.is_file() or path.stat().st_size <= 0:
                return False
        except OSError:
            return False
    return True


def _validation_ready(cases_path):
    path = Path(cases_path)
    try:
        if path.is_file():
            return path.stat().st_size > 0
        if not path.is_dir():
            return False
        for relative in EXPECTED_VALIDATION_CASES:
            candidate = path / relative
            if not candidate.is_file() or candidate.stat().st_size <= 0:
                return False
        return True
    except OSError:
        return False


def _watch_compare(experiments, done, baseline_dir, compare_out, prefix,
                   baseline_reference):
    summaries = []
    try:
        baseline_summary = build_summary(baseline_dir, 'baseline',
                                         baseline_dir)
        baseline_summary['routes_changed'] = 0
        baseline_summary['manual_changed'] = 0
        summaries.append(baseline_summary)
    except Exception as exc:  # noqa: BLE001 - compare is still useful without
        _log('watch: could not summarise baseline: %s' % exc, level='warn')
    for name, directory in experiments:
        if name not in done:
            continue
        try:
            summaries.append(build_summary(directory, name, baseline_dir))
        except Exception as exc:  # noqa: BLE001
            _log('watch: could not summarise %s: %s' % (name, exc),
                 level='warn')
    if not summaries:
        return dict(written=[], errors=[dict(figure='*',
                                             error='no comparable layouts')],
                    skipped=[])
    return plot_compare(summaries, compare_out, prefix=prefix,
                        baseline_reference=baseline_reference)


def _watch_validation(cases_path, baseline_dir, validation_out, prefix):
    try:
        cases = load_cases(cases_path)
    except Exception as exc:  # noqa: BLE001
        return dict(written=[],
                    errors=[dict(figure='*',
                                 error='could not load cases: %s' % exc)],
                    skipped=[])
    if not cases:
        return dict(written=[],
                    errors=[dict(figure='*',
                                 error='no P0/P1/P2 cases under %s'
                                       % cases_path)],
                    skipped=[])
    return plot_router_validation(baseline_dir, cases, validation_out,
                                  prefix=prefix)


def watch_experiments(experiments=None, out_root=None, baseline_dir=None,
                      poll_seconds=120.0, timeout_minutes=90.0,
                      baseline_reference=BASELINE_REFERENCE,
                      compare_out=None, compare_prefix='comparison',
                      cases_path=None, validation_out=None,
                      validation_prefix='router_validation',
                      status_path=None, max_validation_attempts=3):
    """Poll the experiment layouts and plot each one as soon as it is complete.

    A layout is considered complete when ``RUN_READY_FILES`` all exist (a
    partially written ``routes_l3d.json`` is therefore never plotted).  Once all
    experiments are done the comparison figures are written; when ``cases_path``
    points at the P0/P1/P2 validation results those figures are written too.

    Returns a report dict; a JSON status file is kept up to date at
    ``status_path`` (default ``<plots>/watch_status.json``).
    """
    started = time.time()
    poll_seconds = max(float(poll_seconds), 1.0)
    timeout_minutes = max(float(timeout_minutes), 0.0)
    deadline = started + timeout_minutes * 60.0
    experiments = [(str(name), Path(path)) for name, path
                   in (experiments or DEFAULT_WATCH_EXPERIMENTS)]
    out_root = Path(out_root or PATHS.DIRS['plots'])
    baseline_dir = Path(baseline_dir or PATHS.BASELINE_AUTHORITY)
    compare_out = Path(compare_out or (out_root / 'comparison'))
    validation_out = Path(validation_out or (out_root / 'router_validation'))
    status_path = Path(status_path or (out_root / 'watch_status.json'))
    state = dict(
        schema='xyz_joint_watch_v1',
        started_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
        baseline_dir=str(baseline_dir),
        out_root=str(out_root),
        poll_seconds=poll_seconds,
        timeout_minutes=timeout_minutes,
        experiments={},
        compare=None,
        validation=None,
        missing=[],
        finished=False,
    )

    def _write_status():
        try:
            payload = dict(state)
            payload['updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%S')
            payload['elapsed_seconds'] = round(time.time() - started, 1)
            _write_json(status_path, payload)
        except Exception as exc:  # noqa: BLE001 - status is non-fatal
            _log('watch: could not write status %s: %s' % (status_path, exc),
                 level='warn')

    for name, directory in experiments:
        state['experiments'][name] = dict(dir=str(directory), ready=False)
    _write_status()
    done = {}
    compare_result = None
    validation_result = None
    validation_done = cases_path is None
    validation_attempts = 0
    _log('watch: %d experiment layouts, poll %.0fs, timeout %.0f min'
         % (len(experiments), poll_seconds, timeout_minutes))
    while True:
        now = time.time()
        for name, directory in experiments:
            if name in done:
                continue
            ready = _run_ready(directory)
            state['experiments'][name]['ready'] = ready
            if not ready:
                continue
            _log('watch: %s is complete -> plotting into %s'
                 % (name, out_root / name))
            try:
                result = plot_experiment(directory, baseline_dir,
                                         out_root / name, prefix=name)
            except Exception as exc:  # noqa: BLE001 - never kill the watcher
                result = dict(
                    written=[],
                    errors=[dict(figure='*',
                                 error='%s: %s' % (type(exc).__name__, exc),
                                 traceback=traceback.format_exc())],
                    skipped=[])
            done[name] = dict(dir=str(directory),
                              figures=len(result['written']),
                              errors=len(result['errors']),
                              error_details=result['errors'],
                              skipped=result.get('skipped', []),
                              manifest=result.get('manifest'),
                              finished_at=time.strftime('%Y-%m-%dT%H:%M:%S'))
            state['experiments'][name].update(done[name])
            _log('watch: %s -> %d figures, %d errors'
                 % (name, len(result['written']), len(result['errors'])))
            _write_status()
        all_experiments_done = all(name in done for name, _directory
                                   in experiments)
        if all_experiments_done and compare_result is None:
            _log('watch: all experiments done -> comparison figures')
            compare_result = _watch_compare(experiments, done, baseline_dir,
                                            compare_out, compare_prefix,
                                            baseline_reference)
            state['compare'] = dict(
                out=str(compare_out),
                figures=len(compare_result['written']),
                errors=len(compare_result['errors']),
                error_details=compare_result['errors'],
                skipped=compare_result.get('skipped', []),
                manifest=compare_result.get('manifest'))
            _write_status()
            _log('watch: comparison -> %d figures, %d errors'
                 % (len(compare_result['written']),
                    len(compare_result['errors'])))
        if cases_path is not None and not validation_done:
            if _validation_ready(cases_path) or now >= deadline:
                validation_attempts += 1
                _log('watch: router-validation cases ready -> plotting '
                     'into %s' % validation_out)
                validation_result = _watch_validation(
                    cases_path, baseline_dir, validation_out,
                    validation_prefix)
                state['validation'] = dict(
                    cases_path=str(cases_path),
                    out=str(validation_out),
                    attempts=validation_attempts,
                    figures=len(validation_result['written']),
                    errors=len(validation_result['errors']),
                    error_details=validation_result['errors'],
                    skipped=validation_result.get('skipped', []),
                    manifest=validation_result.get('manifest'))
                _write_status()
                _log('watch: router-validation -> %d figures, %d errors'
                     % (len(validation_result['written']),
                        len(validation_result['errors'])))
                if (validation_result['written']
                        or validation_attempts >= max_validation_attempts
                        or now >= deadline):
                    validation_done = True
        if all_experiments_done and validation_done:
            break
        if time.time() >= deadline:
            _log('watch: timeout after %.1f min' % timeout_minutes,
                 level='warn')
            break
        time.sleep(min(poll_seconds, max(1.0, deadline - time.time())))
    # final fallback: comparison with whatever layouts finished before timeout
    if compare_result is None and done:
        _log('watch: final comparison with the layouts that finished',
             level='warn')
        compare_result = _watch_compare(experiments, done, baseline_dir,
                                        compare_out, compare_prefix,
                                        baseline_reference)
        state['compare'] = dict(
            out=str(compare_out), figures=len(compare_result['written']),
            errors=len(compare_result['errors']),
            error_details=compare_result['errors'],
            skipped=compare_result.get('skipped', []),
            manifest=compare_result.get('manifest'))
    # final fallback: attempt the validation figures even without the expected
    # file names (recursive case discovery) and record what is still missing
    if cases_path is not None and not validation_done:
        _log('watch: final router-validation attempt', level='warn')
        validation_result = _watch_validation(cases_path, baseline_dir,
                                              validation_out,
                                              validation_prefix)
        state['validation'] = dict(
            cases_path=str(cases_path), out=str(validation_out),
            attempts=validation_attempts + 1,
            figures=len(validation_result['written']),
            errors=len(validation_result['errors']),
            error_details=validation_result['errors'],
            skipped=validation_result.get('skipped', []),
            manifest=validation_result.get('manifest'))
    state['missing'] = [name for name, _directory in experiments
                        if name not in done]
    state['finished'] = True
    state['elapsed_seconds'] = round(time.time() - started, 1)
    _write_status()
    written = []
    for name in done:
        written.append(dict(kind='experiment', name=name,
                            dir=done[name]['dir'],
                            figures=done[name]['figures']))
    return dict(
        status=str(status_path),
        experiments=state['experiments'],
        compare=state['compare'],
        validation=state['validation'],
        missing=state['missing'],
        elapsed_seconds=state['elapsed_seconds'],
        written=written,
    )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _build_parser():
    parser = argparse.ArgumentParser(
        prog=TOOL,
        description='Real-geometry figures for the XYZ joint router '
                    'baseline / experiments / P0-P1-P2 validation / G1-G2-G3 '
                    'comparison.')
    parser.add_argument('--mode', required=True,
                        choices=['baseline', 'experiment', 'compare',
                                 'router_validation', 'watch'],
                        help='which figure family to produce ("watch" polls '
                             'the experiment directories and plots each one '
                             'as soon as it is complete)')
    parser.add_argument('--run-dir', default=None,
                        help='layout directory (routes_l3d.json ...)')
    parser.add_argument('--baseline-dir', default=None,
                        help='authoritative baseline directory')
    parser.add_argument('--out', default=None,
                        help='output directory for the PNGs')
    parser.add_argument('--prefix', default=None,
                        help='filename prefix / experiment name')
    parser.add_argument('--cases', default=None,
                        help='P0/P1/P2 case JSON file or directory of files')
    parser.add_argument('--summaries', default=None,
                        help='summaries JSON for --mode compare '
                             '(auto-discovery when omitted)')
    parser.add_argument('--watch-dir', action='append', default=None,
                        metavar='NAME=PATH',
                        help='experiment layout for --mode watch (repeatable; '
                             'defaults to the five G1/G3_cold/G2a/G2b/G3 dirs)')
    parser.add_argument('--out-root', default=None,
                        help='root plots directory for --mode watch')
    parser.add_argument('--compare-out', default=None,
                        help='comparison output directory for --mode watch')
    parser.add_argument('--validation-out', default=None,
                        help='router-validation output directory for '
                             '--mode watch')
    parser.add_argument('--status', default=None,
                        help='watch status JSON path for --mode watch')
    parser.add_argument('--poll-seconds', type=float, default=120.0,
                        help='watch poll interval in seconds (default 120)')
    parser.add_argument('--timeout-minutes', type=float, default=90.0,
                        help='watch timeout in minutes (default 90)')
    parser.add_argument('--baseline-reference', type=float,
                        default=BASELINE_REFERENCE,
                        help='baseline crossing reference (default 2409)')
    parser.add_argument('--max-changed-routes', type=int,
                        default=MAX_CHANGED_ROUTES,
                        help='cap on routes drawn in the changed-routes figure')
    parser.add_argument('--quiet', action='store_true',
                        help='suppress per-figure logging')
    return parser


def _report(result, mode, out_dir, manifest=None):
    _log('mode=%s out=%s: %d figures, %d errors, %d skipped'
         % (mode, out_dir, len(result['written']), len(result['errors']),
            len(result.get('skipped', []))))
    for error in result['errors']:
        _log('ERROR %s: %s' % (error.get('figure'), error.get('error')),
             level='error')
    payload = dict(mode=str(mode), out_dir=str(out_dir),
                   written=[str(path) for path in result['written']],
                   errors=result['errors'],
                   skipped=result.get('skipped', []),
                   manifest=manifest or result.get('manifest'))
    print(json.dumps(payload, ensure_ascii=False, indent=1), flush=True)
    return 0 if result['written'] else 1


def main(argv=None):
    """CLI entry point; returns a process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    set_quiet(args.quiet)
    mode = args.mode
    if mode == 'baseline':
        run_dir = args.run_dir or PATHS.BASELINE_AUTHORITY
        out_dir = args.out or (Path(PATHS.DIRS['plots']) / 'baseline')
        result = plot_baseline(run_dir=run_dir, out_dir=out_dir,
                               prefix=args.prefix or 'baseline')
        return _report(result, mode, out_dir)
    if mode == 'experiment':
        run_dir = args.run_dir
        if not run_dir:
            parser.error('--mode experiment requires --run-dir')
        prefix = args.prefix or Path(run_dir).name
        out_dir = args.out or (Path(PATHS.DIRS['plots']) / prefix)
        result = plot_experiment(run_dir=run_dir,
                                 baseline_dir=args.baseline_dir,
                                 out_dir=out_dir, prefix=prefix)
        return _report(result, mode, out_dir)
    if mode == 'router_validation':
        if not args.cases:
            parser.error('--mode router_validation requires --cases')
        try:
            cases = load_cases(args.cases)
        except Exception as exc:  # noqa: BLE001 - report, do not crash
            print(json.dumps(dict(mode=mode, errors=[
                dict(figure='*', error='could not load cases: %s' % exc)]),
                ensure_ascii=False, indent=1), flush=True)
            return 1
        out_dir = args.out or (Path(PATHS.DIRS['plots']) / 'router_validation')
        result = plot_router_validation(
            baseline_dir=args.baseline_dir, cases=cases, out_dir=out_dir,
            prefix=args.prefix or 'router_validation')
        return _report(result, mode, out_dir)
    if mode == 'watch':
        experiments = None
        if args.watch_dir:
            experiments = []
            for spec in args.watch_dir:
                text = str(spec)
                if '=' in text:
                    name, _, directory = text.partition('=')
                    experiments.append((name.strip(), directory.strip()))
                else:
                    experiments.append((Path(text).name, text))
        report = watch_experiments(
            experiments=experiments, out_root=args.out_root,
            baseline_dir=args.baseline_dir,
            poll_seconds=args.poll_seconds,
            timeout_minutes=args.timeout_minutes,
            baseline_reference=args.baseline_reference,
            compare_out=args.compare_out,
            cases_path=args.cases, validation_out=args.validation_out,
            status_path=args.status)
        summary = dict(
            mode='watch', status=report['status'],
            experiments={name: dict(figures=info.get('figures'),
                                    errors=info.get('errors'),
                                    dir=info.get('dir'))
                         for name, info in report['experiments'].items()},
            compare=report['compare'],
            validation=report['validation'],
            missing=report['missing'],
            elapsed_seconds=report['elapsed_seconds'])
        print(json.dumps(summary, ensure_ascii=False, indent=1), flush=True)
        return 0
    # compare
    if args.summaries:
        try:
            summaries = load_summaries(args.summaries)
        except Exception as exc:  # noqa: BLE001 - report, do not crash
            print(json.dumps(dict(mode=mode, errors=[
                dict(figure='*', error='could not load summaries: %s' % exc)]),
                ensure_ascii=False, indent=1), flush=True)
            return 1
    else:
        summaries = auto_summaries(args.baseline_dir)
    out_dir = args.out or (Path(PATHS.DIRS['plots']) / 'compare')
    result = plot_compare(summaries, out_dir=out_dir,
                          prefix=args.prefix or 'compare',
                          baseline_reference=args.baseline_reference)
    return _report(result, mode, out_dir)


if __name__ == '__main__':
    sys.exit(main())
