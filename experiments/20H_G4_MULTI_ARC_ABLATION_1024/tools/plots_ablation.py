# -*- coding: utf-8 -*-
"""Figures, tables and statistics for the 20-height G4 planar multi-arc ablation.

Two experiment rounds are analysed from their **real** artifacts only:

* Round 1 (original design) ``experiments/20H_G4_MULTI_ARC_ABLATION_1024``
* Round 2 (strict common start) ``experiments/20H_G4_MULTI_ARC_ABLATION_FINAL_1024``

The only changed algorithm variable is ``G4_ENABLE_MULTI_ARC`` (ON vs OFF);
everything else (20 routing heights = 18 body planes + 2 routable interface
planes, R15, strict D56, 3-D clearance, 1024 connections, validator) is fixed.

Nothing is estimated or synthesised: every number is read from a real artifact
(``routes_l3d.json`` / ``assignment_1024.csv`` / ``crossing_stats.json`` /
``strategy_stats.json`` / ``summary*.json`` / ``validation*.json`` /
``audit_state.json`` / ``conversion_report.json``) or recomputed exactly from
the stored line/arc primitives (``four_side_1024/fanout1024/reheight21/plots21.py``
semantics).  Missing inputs raise a clear error instead of producing a figure.

Sub-commands
------------
``layers``          per-height routing figures -- delegates to the frozen
                    ``coldstart20/plot_layers20.py::build(run_dir, out_dir)``
``compare-layers``  same-height side-by-side A|B panels (one per height) plus a
                    20-height overview; each panel is annotated with its own
                    crossing count
``global3d``        true-3-D global routing comparison of both states (1024
                    real centre lines including the S-curve transitions)
``route-case``      local XY geometry of the same ``route_id`` in both states
                    (real arcs/lines, multi-arc regions and the ablated detour
                    are annotated)
``layer-stats``     per-height crossing events / unique pairs / route counts
                    with exact-z matching (CSV + JSON + grouped bar chart)
``offset-2r``       the Stage-0 conversion cost: per-route lateral offset
                    ``|bx|`` against the 2R = 30 mm threshold (CSV + scatter +
                    binned summary)
``curves``          search-progress curves (crossings vs d56 candidate
                    evaluations / route 3-D checks / wall seconds), several runs
                    overlaid
``seed-summary``    three-seed ON/OFF paired table (mean, sample std ddof=1,
                    min/max, paired difference) + box/scatter figure
``summary-tables``  markdown core tables (crossings, unique pairs, max per-route
                    crossings, length, validation status)

Reproduce (from the project root, bundled venv)::

    .venv\\Scripts\\python.exe experiments\\20H_G4_MULTI_ARC_ABLATION_1024\\tools\\plots_ablation.py layers ^
        --run-dir experiments\\COLD_START_20_HEIGHT_1024\\10_best_valid ^
        --out-dir  experiments\\20H_G4_MULTI_ARC_ABLATION_1024\\05_figures

Conventions
-----------
* Every figure is written as PNG (>= 150 dpi) and SVG.
* ``<out-dir>/manifest.json`` records, per invocation: command line, UTC/local
  timestamps, every source file with its SHA256 + size, every output file with
  its SHA256 + size, the statistics source (authoritative vs exactly
  recomputed) and the exact definition of the derived quantities.
* ``<out-dir>/README.md`` is a generated index of the produced figures.

The script only writes under ``--out-dir`` (default: the round's figure
directory).  It never modifies pipeline code, run data or ``layer2d.py``.
"""
from __future__ import annotations

import argparse
import csv
import fnmatch
import hashlib
import json
import math
import os
import re
import statistics
import sys
import time
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# the 20-height profile MUST be installed before any frozen pipeline module is
# imported (it registers model20 as reheight21.model); bootstrap installs on
# import, exactly like every other coldstart20 driver does.
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from four_side_1024.fanout1024.coldstart20 import bootstrap as B  # noqa: E402

B.assert_20_height_profile('plots_ablation import')

import matplotlib  # noqa: E402

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Circle, Rectangle  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Line3DCollection  # noqa: E402
from PIL import Image  # noqa: E402

from four_side_1024.fanout1024 import layer2d as L2  # noqa: E402
from four_side_1024.fanout1024.coldstart20 import model20 as M20  # noqa: E402
from four_side_1024.fanout1024.coldstart20 import plot_layers20 as L20  # noqa: E402
from four_side_1024.fanout1024.reheight21 import plots21 as P  # noqa: E402
from four_side_1024.fanout1024.xyzrouter import route_builder as RB  # noqa: E402

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------
SCRIPT_PATH = Path(__file__).resolve()
SCRIPT_REL = 'experiments/20H_G4_MULTI_ARC_ABLATION_1024/tools/plots_ablation.py'
SCHEMA = '20h_g4_multi_arc_ablation_figures_v1'
MANIFEST_NAME = 'manifest.json'
README_NAME = 'README.md'

EXP1_ROOT = PROJECT_ROOT / 'experiments' / '20H_G4_MULTI_ARC_ABLATION_1024'
EXP2_ROOT = PROJECT_ROOT / 'experiments' / '20H_G4_MULTI_ARC_ABLATION_FINAL_1024'
EXP1_FIGURES = EXP1_ROOT / '05_figures'
EXP2_FIGURES = EXP2_ROOT / '04_figures'
COLD20_ROOT = PROJECT_ROOT / 'experiments' / 'COLD_START_20_HEIGHT_1024'
G3_START = COLD20_ROOT / '07_g123' / 'run_xyz_joint_1024_20h' / 'best_valid'
FINAL_20H = COLD20_ROOT / '10_best_valid'

R15_MM = float(L2.R15)                      # 15.0 mm, frozen
TWO_R_MM = 2.0 * R15_MM                     # 30.0 mm threshold
BOARD_MM = float(P.BOARD_MM)                # 150 x 150 mm
DPI_DEFAULT = 165                           # per-height spec: >= 150 dpi
AXIS_Z_TOL = 1e-9
COLOR_A = '#1565c0'                         # ON / A / variant 1
COLOR_B = '#c62828'                         # OFF / B / variant 2
COLOR_START = '#6d4c41'
COLOR_OTHER = '#9aa7b4'
COLOR_ARC = '#00838f'
COLOR_CROSS = '#e53935'
SRC_SCHEMA_ROUTES = 'xyz_joint_g4_routes_v1'


class DataError(RuntimeError):
    """Raised when a required real artifact is missing or inconsistent."""


# ---------------------------------------------------------------------------
# small generic helpers
# ---------------------------------------------------------------------------
def read_json(path, default=None):
    """Read a JSON file (tolerant BOM/whitespace); ``default`` when absent."""
    path = Path(path)
    if not path.is_file():
        return default
    try:
        text = path.read_text(encoding='utf-8-sig')
        return json.loads(text) if text.strip() else default
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=1, ensure_ascii=False, default=str) + '\n'
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(text, encoding='utf-8')
    os.replace(tmp, path)
    return path


def read_csv_rows(path):
    path = Path(path)
    if not path.is_file():
        raise DataError('required CSV artifact is missing: %s' % path)
    with path.open('r', encoding='utf-8-sig', newline='') as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv(path, rows, fieldnames=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    if fieldnames is None:
        if not rows:
            raise DataError('cannot write an empty table without fieldnames: %s'
                            % path)
        fieldnames = list(rows[0].keys())
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames,
                                extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    return path


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def as_float(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def rel(path):
    """Project-relative POSIX-ish path when possible, else the absolute path."""
    path = Path(path)
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except (ValueError, OSError):
        return str(path)


def resolve_path(value):
    """Resolve a user supplied path against the project root."""
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def fmt_z(value):
    return '%+.3f' % float(value)


def sanitize(text, limit=48):
    cleaned = re.sub(r'[^0-9A-Za-z._-]+', '_', str(text)).strip('_')
    return (cleaned or 'state')[:limit]


def require_file(path, what):
    path = Path(path)
    if not path.is_file():
        raise DataError('required %s is missing: %s' % (what, path))
    return path


def file_entry(path, role=None):
    path = Path(path)
    return dict(role=role or path.name, path=rel(path),
                bytes=int(path.stat().st_size), sha256=sha256_file(path))


def now_local():
    return time.strftime('%Y-%m-%dT%H:%M:%S%z')


# ---------------------------------------------------------------------------
# manifest: every invocation appends one auditable entry
# ---------------------------------------------------------------------------
def _manifest_path(out_dir):
    return Path(out_dir) / MANIFEST_NAME


def read_manifest(out_dir):
    payload = read_json(_manifest_path(out_dir))
    if not isinstance(payload, dict) or 'entries' not in payload:
        payload = dict(schema=SCHEMA, script=dict(path=SCRIPT_REL,
                                                  sha256=sha256_file(SCRIPT_PATH)),
                       entries=[])
    return payload


def record_manifest(out_dir, command, argv, sources, outputs, notes,
                    started_at, elapsed_s):
    """Append one invocation record to ``<out-dir>/manifest.json``."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = read_manifest(out_dir)
    tool_sha = sha256_file(SCRIPT_PATH)
    payload['schema'] = SCHEMA
    payload['script'] = dict(path=SCRIPT_REL, sha256=tool_sha)
    payload['generated_at'] = now_local()
    payload['engine'] = dict(
        per_height_driver='four_side_1024/fanout1024/coldstart20/'
                          'plot_layers20.py',
        per_height_driver_sha256=sha256_file(Path(L20.__file__)),
        frozen_engine='four_side_1024/fanout1024/reheight21/plots21.py',
        frozen_engine_sha256=sha256_file(Path(P.__file__)),
        layer2d='four_side_1024/fanout1024/layer2d.py',
        layer2d_sha256=sha256_file(Path(L2.__file__)),
        layer2d_r15_mm=R15_MM,
        profile=str(M20.PROFILE),
        plane_count=len(M20.PLANE_IDS),
        interfaces={key: float(value)
                    for key, value in M20.INTERFACE_Z.items()})
    entry = dict(
        command=command,
        argv=[str(item) for item in argv],
        cwd=str(Path.cwd()),
        started_at=started_at,
        finished_at=now_local(),
        elapsed_seconds=round(float(elapsed_s), 3),
        sources=list(sources),
        outputs=list(outputs),
        notes=notes or {})
    payload['entries'].append(entry)
    write_json(_manifest_path(out_dir), payload)
    return entry


def output_entry(path, out_dir, dpi=None, kind='figure'):
    path = Path(path)
    entry = dict(kind=kind, path=rel(path),
                 path_from_out_dir=str(path.relative_to(Path(out_dir)))
                 if str(path).startswith(str(Path(out_dir))) else str(path),
                 format=path.suffix.lstrip('.').lower(),
                 bytes=int(path.stat().st_size), sha256=sha256_file(path))
    if dpi is not None:
        entry['dpi'] = int(dpi)
    if entry['format'] == 'png':
        with Image.open(path) as image:
            entry['width_px'], entry['height_px'] = image.size
    return entry


def collect_outputs(out_dir, pattern='*', recursive=True):
    out_dir = Path(out_dir)
    found = []
    iterator = out_dir.rglob(pattern) if recursive else out_dir.glob(pattern)
    for path in sorted(iterator):
        if path.is_file() and path.suffix.lower() in ('.png', '.svg', '.csv',
                                                      '.json', '.md'):
            if path.name == MANIFEST_NAME:
                continue
            dpi = DPI_DEFAULT if path.suffix.lower() == '.png' else None
            found.append(output_entry(path, out_dir, dpi=dpi))
    return found


def save_figure(fig, out_dir, stem, dpi, with_svg=True, pad=0.12):
    """Save one figure as PNG (>=150 dpi) + SVG; return output entries."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / (stem + '.png')
    fig.savefig(png, dpi=dpi, bbox_inches='tight', pad_inches=pad)
    outputs = [output_entry(png, out_dir, dpi=dpi)]
    if with_svg:
        svg = out_dir / (stem + '.svg')
        fig.savefig(svg, format='svg', bbox_inches='tight', pad_inches=pad)
        outputs.append(output_entry(svg, out_dir))
    plt.close(fig)
    return outputs


# ---------------------------------------------------------------------------
# state resolution (run dir / best_valid + sibling artifacts) and staging
# ---------------------------------------------------------------------------
#: files the frozen plotting engine or the statistics need, in read order.
ARTIFACT_FILES = (
    'routes_l3d.json',
    'assignment_1024.csv',
    'layer_planes.json',
    'physical_layer_stack.json',
    'process_rules.json',
    'crossing_stats.json',
    'validation.json',
    'summary.json',
    'summary_g4.json',
    'strategy_stats.json',
    'budget_ledger.json',
    'optimization_history.csv',
    'audit_state.json',
    'RUN_VERDICT.json',
    'run_meta.json',
    'geometry_changes.json',
    'failed_attempts.json',
    'config.json',
    'validation_final/validation.json',
)


def resolve_state_dir(run_dir):
    """Resolve a user ``--run-dir`` to ``(state_dir, artifact_root)``.

    * If ``DIR/routes_l3d.json`` exists, ``DIR`` **is** the state (an arm root
      holds the final state; a ``best_valid`` directory holds the best state).
    * Else ``DIR/best_valid/routes_l3d.json`` is used and the sibling artifacts
      of ``DIR`` (crossing_stats.json, validation_final/, ...) are collected
      from ``DIR``.
    """
    raw = Path(run_dir)
    if not raw.exists():
        raw = resolve_path(run_dir)
    if not raw.exists():
        raise DataError('run directory does not exist: %s' % run_dir)
    if (raw / 'routes_l3d.json').is_file():
        return raw, raw
    if (raw / 'best_valid' / 'routes_l3d.json').is_file():
        return raw / 'best_valid', raw
    raise DataError(
        'no routes_l3d.json found in %s nor in %s/best_valid (the state has '
        'not been written yet)' % (raw, raw))


def _search_dirs(state_dir, artifact_root):
    ordered = [state_dir, artifact_root, state_dir.parent]
    seen = set()
    result = []
    for item in ordered:
        try:
            key = str(Path(item).resolve())
        except OSError:
            key = str(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(Path(item))
    return result


def collect_state_files(state_dir, artifact_root):
    """Locate every known artifact in the state dir or its sibling dirs."""
    found = OrderedDict()
    for name in ARTIFACT_FILES:
        for base in _search_dirs(state_dir, artifact_root):
            candidate = Path(base) / name
            if candidate.is_file():
                found[name] = candidate
                break
    if 'routes_l3d.json' not in found:
        raise DataError('routes_l3d.json missing in %s' % state_dir)
    if 'assignment_1024.csv' not in found:
        raise DataError('assignment_1024.csv missing for state %s' % state_dir)
    return found


def state_label(state_dir, artifact_root):
    """Compact deterministic label used in figure file names."""
    try:
        rel_parts = Path(state_dir).resolve().relative_to(
            PROJECT_ROOT.resolve()).parts
    except (ValueError, OSError):
        rel_parts = Path(state_dir).parts[-3:]
    parts = [sanitize(part, 40) for part in rel_parts]
    if parts and parts[0] == 'experiments':
        parts = parts[1:]
    if len(parts) > 3:
        parts = parts[-3:]
    if parts and parts[-1] == 'best_valid' and len(parts) >= 2:
        return sanitize('_'.join(parts[-2:]), 60)
    return sanitize('_'.join(parts) or 'state', 60)


def stage_state(state_dir, artifact_root, label, inputs_root):
    """Return a directory the frozen engine can read as one self-contained run.

    If every artifact already lives in ``state_dir`` the directory is used
    as-is (no copy).  Otherwise a staging directory with byte-identical copies
    (and a ``_staging.json`` provenance file) is built under ``inputs_root``.
    Nothing outside ``--out-dir`` is written.
    """
    state_dir = Path(state_dir)
    artifact_root = Path(artifact_root)
    found = collect_state_files(state_dir, artifact_root)
    outside = [(name, src) for name, src in found.items()
               if Path(src).parent != state_dir]
    if not outside:
        return dict(staged_dir=state_dir, copied=False, files=found,
                    sources={name: rel(src) for name, src in found.items()})
    routes_sha = sha256_file(found['routes_l3d.json'])
    assignment_sha = sha256_file(found['assignment_1024.csv'])
    key = hashlib.sha256(('%s|%s|%s' % (routes_sha, assignment_sha,
                                        label)).encode('utf-8')).hexdigest()[:12]
    stage_dir = Path(inputs_root) / ('%s_%s' % (label, key))
    stage_dir.mkdir(parents=True, exist_ok=True)
    copied = OrderedDict()
    for name, src in found.items():
        target = stage_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        data = Path(src).read_bytes()
        target.write_bytes(data)
        copied[name] = src
    write_json(stage_dir / '_staging.json', dict(
        schema='plots_ablation_staging_v1',
        note='byte-identical copies of real artifacts, staged so that the '
             'frozen 20H plotting engine can read one self-contained run '
             'directory; no value is changed, every source path + SHA256 is '
             'recorded here and in manifest.json',
        state_dir=rel(state_dir), artifact_root=rel(artifact_root),
        files={name: dict(source=rel(src), sha256=sha256_file(src))
               for name, src in copied.items()}))
    return dict(staged_dir=stage_dir, copied=True, files=copied,
                sources={name: rel(src) for name, src in copied.items()})


# ---------------------------------------------------------------------------
# state analysis: frozen dataset + per-plane statistics (authoritative or exact)
# ---------------------------------------------------------------------------
def _prepare_once(staged_dir):
    ds, per_plane, counts = L20.prepare(Path(staged_dir))
    return ds, per_plane, counts


def _check_counts(counts, staged_dir):
    if counts['body_routes_total'] != 1024:
        raise DataError('state %s has %d routed body routes (expected 1024): '
                        'not a complete 1024-route state'
                        % (staged_dir, counts['body_routes_total']))


def analyze_state(run_dir, inputs_root, label=None, allow_sibling_stats=True):
    """Build the frozen dataset for one real state and classify its counts.

    Returns a dict with ``ds`` / ``per_plane`` / ``counts`` plus the exact
    provenance of the crossing numbers:

    ``counts_source == 'authoritative'``
        a real ``crossing_stats.json`` was found adjacent to the state and the
        per-plane counts were re-verified against the exact recomputed
        geometry (``L20.audit_crossings`` PASS);
    ``counts_source == 'recomputed_exact'``
        no matching ``crossing_stats.json`` exists for this exact state (e.g.
        a ``best_valid`` snapshot whose sibling stats belong to a different
        final state); per-plane counts are the exact recomputation from the
        real line/arc primitives (``plots21.compute_all_plane_crossings``),
        which is the same semantics the independent validator uses.
    """
    state_dir, artifact_root = resolve_state_dir(run_dir)
    label = label or state_label(state_dir, artifact_root)
    staged = stage_state(state_dir, artifact_root, label, inputs_root)
    staged_dir = Path(staged['staged_dir'])
    stats_path = Path(staged['files'].get('crossing_stats.json')
                      or (staged_dir / 'crossing_stats.json'))
    stats_origin = None
    if 'crossing_stats.json' in staged['files']:
        src = Path(staged['files']['crossing_stats.json'])
        stats_origin = 'state' if src.parent == state_dir else 'sibling'
    ds, per_plane, counts = _prepare_once(staged_dir)
    _check_counts(counts, staged_dir)

    audit = None
    counts_source = 'recomputed_exact'
    rejected_stats = None
    stats_payload = read_json(stats_path) if stats_path.is_file() else None
    if stats_payload is not None and allow_sibling_stats:
        try:
            audit = L20.audit_crossings(ds, per_plane, staged_dir)
        except RuntimeError as error:
            if stats_origin == 'state':
                raise DataError(
                    'authoritative crossing_stats.json of the state itself does '
                    'not match its own geometry (%s). Refusing to draw: the '
                    'state is internally inconsistent.' % error) from error
            rejected_stats = dict(reason=str(error), origin=stats_origin,
                                  path=rel(stats_path))
            stats_payload = None
            # sibling statistics belong to a different state -> rebuild the
            # dataset without them; counts become the exact recomputation
            (staged_dir / 'crossing_stats.json').unlink()
            ds, per_plane, counts = _prepare_once(staged_dir)
            _check_counts(counts, staged_dir)
        else:
            counts_source = 'authoritative'

    # per-route crossing counts / event list (only from a real stats file)
    per_route = {}
    events = []
    if stats_payload is not None:
        for key, value in (stats_payload.get('per_route_crossings') or {}).items():
            rid = as_int(key)
            if rid is not None:
                per_route[rid] = int(value or 0)
        events = [event for event in (stats_payload.get('crossing_events') or [])
                  if isinstance(event, dict)]
    glass = _glass_of(staged_dir)
    state = dict(
        label=label, run_dir=Path(state_dir), artifact_root=Path(artifact_root),
        staged_dir=staged_dir, staging_copied=bool(staged['copied']),
        files=staged['files'], sources=staged['sources'],
        ds=ds, per_plane=per_plane, counts=counts,
        counts_source=counts_source, crossing_stats=stats_payload,
        crossing_events=events, per_route_crossings=per_route,
        audit=audit, rejected_sibling_stats=rejected_stats,
        stats_path=(stats_path if stats_payload is not None else None),
        glass=glass,
        model=ds['model'])
    print('[state] %-28s routes=%d planes=%d crossings=%d pairs=%d source=%s'
          % (label, len(ds['routed']), len(ds['model'].planes),
             sum(int(info['crossing_count']) for info in per_plane.values()),
             sum(int(info['crossing_pairs']) for info in per_plane.values()),
             counts_source), flush=True)
    return state


def _glass_of(run_dir):
    payload = read_json(Path(run_dir) / 'layer_planes.json', default={}) or {}
    node = payload.get('glass') if isinstance(payload, dict) else None
    if isinstance(node, dict) and 'z_min_mm' in node and 'z_max_mm' in node:
        return dict(z_min_mm=float(node['z_min_mm']),
                    z_max_mm=float(node['z_max_mm']),
                    thickness_mm=float(node.get('thickness_mm',
                                               node['z_max_mm']
                                               - node['z_min_mm'])))
    return dict(z_min_mm=float(M20.GLASS_Z_MIN_MM),
                z_max_mm=float(M20.GLASS_Z_MAX_MM),
                thickness_mm=float(M20.GLASS_THICKNESS_MM))


def state_sources(state, extra_paths=()):
    """Manifest source records for one analysed state."""
    sources = []
    for name, src in state['files'].items():
        entry = file_entry(src, role='state:%s' % name)
        entry['state'] = state['label']
        sources.append(entry)
    if state.get('stats_path') is not None:
        sources.append(dict(state=state['label'], role='crossing_stats_used',
                            **{key: value for key, value in
                               file_entry(state['stats_path']).items()
                               if key != 'role'}))
    for path in extra_paths:
        path = Path(path)
        if path.is_file():
            sources.append(dict(state=state['label'], role=path.name,
                                **{key: value for key, value in
                                   file_entry(path).items()
                                   if key != 'role'}))
    return sources


def state_notes(state):
    notes = dict(
        state_label=state['label'],
        state_dir=rel(state['run_dir']),
        staged_dir=rel(state['staged_dir']),
        staging_copied=state['staging_copied'],
        counts_source=state['counts_source'],
        routes=len(state['ds']['routed']),
        failed_routes=len(state['ds']['failed']),
        plane_count=len(state['model'].planes),
        plane_ids=[int(plane['plane_id']) for plane in state['model'].planes],
        crossings=int(sum(int(info['crossing_count'])
                          for info in state['per_plane'].values())),
        crossing_pairs=int(sum(int(info['crossing_pairs'])
                               for info in state['per_plane'].values())),
        r15_mm=R15_MM, two_r_mm=TWO_R_MM,
        profile=str(M20.PROFILE))
    if state['counts_source'] == 'recomputed_exact':
        notes['counts_note'] = (
            'no crossing_stats.json matches this exact state; per-height '
            'counts are the exact recomputation from the stored line/arc '
            'primitives (plots21.compute_all_plane_crossings semantics, the '
            'same rule the independent validator uses) -- nothing estimated')
    else:
        notes['counts_note'] = (
            'crossing counts are the authoritative crossing_stats.json values '
            'and were re-verified against exact recomputed intersections '
            '(per-plane audit PASS)')
    if state.get('rejected_sibling_stats'):
        notes['rejected_sibling_stats'] = state['rejected_sibling_stats']
    return notes


# ===========================================================================
# 1. layers -- per-height figures (delegate, never re-implement the renderer)
# ===========================================================================
def _render_plane_recomputed(ds, info, annotated):
    """Fallback renderer for states with no matching crossing_stats.json.

    The drawing primitives are the frozen ``plots21`` routines (identical to
    ``plot_layers20._render_plane``); only the footer text is different because
    the crossing counts of this state are the exact recomputation from its real
    geometry instead of a validator-written crossing_stats.json.
    """
    plane_id = info['plane_id']
    data = ds['geometry'].get(plane_id) or dict(bodies=[], leads=[])
    fig = plt.figure(figsize=L20.FIG_SIZE)
    ax = fig.add_axes(L20.AX_RECT)
    P._draw_leads(ax, data.get('leads') or [])
    P._draw_entries(ax, data.get('bodies') or [], ds['model'])
    if annotated:
        P._draw_crossings(ax, info['crossing_points'])
    P._draw_ports(ax, P._assignment_rows_for_plane(ds, plane_id))
    line1, line2, line3 = L20._title_lines(
        info, info['order_index'], len(ds['model'].planes), annotated)
    P._decorate_board(ax, '\n'.join((line1, line2, line3)))
    if not data.get('bodies') and not data.get('leads'):
        ax.text(0.5, 0.5, 'no routed geometry at this height',
                transform=ax.transAxes, ha='center', va='center',
                fontsize=9.5, color='#777777')
    handles = L20._legend_handles(info, annotated)
    fig.legend(handles=handles, loc='lower center',
               ncol=min(6, max(2, len(handles))), fontsize=6.8,
               frameon=True, framealpha=0.9)
    if annotated:
        footer = ('crossings: %d events / %d route pairs -- EXACT recomputation '
                  'from the real line/arc primitives of this state '
                  '(plots21.compute_all_plane_crossings semantics; no '
                  'crossing_stats.json matches this exact state) - %d x %d mm '
                  'board - dpi %d - engine: frozen reheight21/plots21.py'
                  % (info['crossing_count'], info['crossing_pairs'],
                     P.BOARD_MM, P.BOARD_MM, L20.DPI_DEFAULT))
    else:
        footer = ('plain view: crossing markers intentionally omitted (see '
                  '%s/); crossings on this height: %d events / %d pairs (exact '
                  'recomputation from the real geometry) - %d x %d mm board - '
                  'dpi %d - engine: frozen reheight21/plots21.py'
                  % (L20.CROSSINGS_DIR, info['crossing_count'],
                     info['crossing_pairs'], P.BOARD_MM, P.BOARD_MM,
                     L20.DPI_DEFAULT))
    fig.text(0.5, 0.018, footer, ha='center', fontsize=6.0, color='#555555')
    return fig


def render_layers_recomputed(state, out_dir, dpi, with_svg):
    """``plot_layers20.build``-shaped output for the recomputed-counts mode."""
    out_dir = Path(out_dir)
    plain_dir = out_dir / L20.PLAIN_DIR
    crossing_dir = out_dir / L20.CROSSINGS_DIR
    plain_dir.mkdir(parents=True, exist_ok=True)
    crossing_dir.mkdir(parents=True, exist_ok=True)
    ds, per_plane = state['ds'], state['per_plane']
    if len(ds['model'].planes) != 20:
        raise DataError('expected 20 routing heights, got %d'
                        % len(ds['model'].planes))
    figures, plane_table = [], []
    for index, (plane_id, info) in enumerate(per_plane.items()):
        base_name = '%02d_%s_z%s' % (index + 1, info['label'],
                                     fmt_z(info['z_mm']))
        row = dict(plane_id=int(plane_id), label=info['label'],
                   z_mm=info['z_mm'], kind=info['kind'],
                   route_count=info['route_count'],
                   crossing_count=info['crossing_count'],
                   crossing_pairs=info['crossing_pairs'], files={})
        for group, directory, annotated in (
                ('plain', plain_dir, False),
                ('crossings', crossing_dir, True)):
            png = directory / (base_name + '.png')
            svg = (directory / (base_name + '.svg')) if with_svg else None
            fig = _render_plane_recomputed(ds, info, annotated)
            outputs = L20._save_figure(fig, png, svg, dpi)
            for output in outputs:
                figures.append(dict(
                    file='%s/%s' % (directory.name, output['file']),
                    rel_dir=directory.name, group=group,
                    format=output['format'], plane_id=int(plane_id),
                    order_index=index + 1, label=info['label'],
                    z_mm=info['z_mm'], route_count=info['route_count'],
                    assigned_routes=info['assigned_routes'],
                    crossing_count=info['crossing_count'],
                    crossing_pairs=info['crossing_pairs'],
                    crossing_markers_drawn=(len(info['crossing_points'])
                                            if annotated else 0),
                    sha256=output['sha256'], bytes=output['bytes'],
                    width_px=output.get('width_px'),
                    height_px=output.get('height_px'), dpi=output.get('dpi')))
            row['files'][group] = dict(
                png='%s/%s' % (directory.name, png.name),
                svg=('%s/%s' % (directory.name, svg.name)
                     if svg is not None else None))
        plane_table.append(row)
    payload = dict(
        schema='20h_ablation_recomputed_per_height_v1',
        generated_at=now_local(),
        run_dir=rel(state['run_dir']),
        staged_dir=rel(state['staged_dir']),
        out_dir=str(out_dir),
        reason=('crossing_stats.json matching this exact state is not '
                'available; per-height crossing counts are the exact '
                'recomputation from the stored line/arc primitives '
                '(plots21.compute_all_plane_crossings), not an estimate'),
        counts_source=state['counts_source'],
        rejected_sibling_stats=state.get('rejected_sibling_stats'),
        dpi=int(dpi), formats=(['png', 'svg'] if with_svg else ['png']),
        plane_count=len(ds['model'].planes),
        route_count=len(ds['routed']), failed_count=len(ds['failed']),
        totals=dict(crossings=sum(int(info['crossing_count'])
                                  for info in per_plane.values()),
                    crossing_pairs=sum(int(info['crossing_pairs'])
                                       for info in per_plane.values()),
                    multi_arc_regions=sum(int(info['multi_arc_regions'])
                                          for info in per_plane.values()),
                    figure_files=len(figures)),
        engine=dict(
            frozen_engine='four_side_1024/fanout1024/reheight21/plots21.py',
            frozen_engine_sha256=sha256_file(Path(P.__file__)),
            drawing='P._draw_leads / P._draw_entries / P._draw_crossings / '
                    'P._draw_ports / P._decorate_board (frozen, unchanged)'),
        planes=plane_table, figures=figures)
    write_json(out_dir / L20.MANIFEST_NAME, payload)
    readme = out_dir / L20.README_NAME
    readme.write_text(
        '# Per-height routing figures (exact-recomputed crossing counts)\n\n'
        'State: `%s`\n\nThis state has no matching `crossing_stats.json`; the '
        'per-height crossing counts and markers are the exact recomputation '
        'from the real line/arc primitives of this state (the same rule the '
        'independent validator uses).  The drawing routines are the frozen '
        '`reheight21/plots21.py` routines; nothing is estimated.\n\n'
        'See `%s` for the full record.\n'
        % (rel(state['run_dir']), L20.MANIFEST_NAME), encoding='utf-8')
    print('[layers] recomputed-counts mode: %d figure files -> %s'
          % (len(figures), out_dir), flush=True)
    return payload


def cmd_layers(args, started_at, began):
    inputs_root = Path(args.out_dir) / '_inputs'
    state = analyze_state(args.run_dir, inputs_root, label=args.label)
    label = sanitize(args.label or state['label'], 60)
    target = Path(args.out_dir) / ('layers_%s' % label)
    if state['counts_source'] == 'authoritative':
        manifest, manifest_path, readme_path = L20.build(
            state['staged_dir'], target, dpi=args.dpi,
            with_svg=not args.no_svg)
        mode = 'plot_layers20.build (frozen per-height driver)'
        caveat = ('crossing_stats.json matches this exact state; per-plane '
                  'counts re-verified by L20.audit_crossings')
    else:
        manifest = render_layers_recomputed(state, target, args.dpi,
                                            not args.no_svg)
        manifest_path = target / L20.MANIFEST_NAME
        readme_path = target / L20.README_NAME
        mode = 'plots_ablation recomputed-counts renderer'
        caveat = ('no crossing_stats.json matches this exact state; counts are '
                  'the exact recomputation from the real line/arc primitives')
    figure_files = [entry for entry in manifest.get('figures') or []
                    if entry.get('format') in ('png', 'svg')]
    outputs = collect_outputs(target)
    manifests = target / L20.MANIFEST_NAME
    outputs = [entry for entry in outputs
               if Path(PROJECT_ROOT / entry['path']).is_file()]
    notes = dict(mode=mode, caveat=caveat,
                 state=state_notes(state),
                 per_height_manifest=rel(manifests),
                 per_height_manifest_sha256=sha256_file(manifests),
                 figure_count=len(figure_files),
                 formats=(['png', 'svg'] if not args.no_svg else ['png']),
                 board_mm=BOARD_MM,
                 engine=dict(
                     driver='four_side_1024/fanout1024/coldstart20/'
                            'plot_layers20.py',
                     driver_sha256=sha256_file(Path(L20.__file__)),
                     frozen_engine='four_side_1024/fanout1024/reheight21/'
                                   'plots21.py',
                     frozen_engine_sha256=sha256_file(Path(P.__file__))))
    record_manifest(args.out_dir, 'layers', [SCRIPT_REL, 'layers',
                                             '--run-dir', args.run_dir,
                                             '--out-dir', str(args.out_dir),
                                             '--dpi', str(args.dpi)],
                    state_sources(state), outputs, notes, started_at,
                    time.time() - began)
    write_readme(args.out_dir)
    print('[layers] %d figures (%s) in %s'
          % (len(figure_files), ' / '.join(sorted({e['format']
                                                   for e in figure_files})),
             target), flush=True)
    print('[layers] per-height manifest: %s' % manifests, flush=True)
    return 0


# ===========================================================================
# 2. compare-layers -- A|B side by side at every physical height
# ===========================================================================
def _verify_same_model(state_a, state_b):
    key = [(int(plane['plane_id']), str(plane['label']),
            round(float(plane['z_mm']), 9)) for plane in state_a['model'].planes]
    other = [(int(plane['plane_id']), str(plane['label']),
              round(float(plane['z_mm']), 9)) for plane in state_b['model'].planes]
    if key != other:
        raise DataError('the two states do not share the same 20-height model: '
                        '%s vs %s' % (key, other))


def _draw_layer_panel(ax, state, info, title, title_color='#111111'):
    pid = info['plane_id']
    data = state['ds']['geometry'].get(pid) or dict(bodies=[], leads=[])
    P._draw_leads(ax, data.get('leads') or [])
    P._draw_entries(ax, data.get('bodies') or [], state['ds']['model'])
    P._draw_crossings(ax, info['crossing_points'])
    P._draw_ports(ax, P._assignment_rows_for_plane(state['ds'], pid))
    P._decorate_board(ax, title, title_fontsize=7.8)
    ax.title.set_color(title_color)


def _compare_overview(state_a, state_b, out_dir, rows, dpi, with_svg):
    planes = state_a['model'].planes
    fig = plt.figure(figsize=(15.8, 18.6))
    n_rows, n_cols = 5, 4
    for index, plane in enumerate(planes):
        pid = int(plane['plane_id'])
        row = rows[index]
        col, row_index = index % n_cols, index // n_cols
        ax = fig.add_axes([0.012 + col * 0.247,
                           0.795 - row_index * 0.163,
                           0.232, 0.148])
        data_a = state_a['ds']['geometry'].get(pid) or dict(bodies=[])
        data_b = state_b['ds']['geometry'].get(pid) or dict(bodies=[])
        P._draw_entries(ax, data_a.get('bodies') or [], state_a['ds']['model'],
                        color=COLOR_A, linewidth=0.42, alpha=0.90)
        P._draw_entries(ax, data_b.get('bodies') or [], state_b['ds']['model'],
                        color=COLOR_B, linewidth=0.22, alpha=0.62)
        P._decorate_board(
            ax, '%s z=%s | A %d / B %d crossings'
            % (plane['label'], fmt_z(plane['z_mm']),
               row['a_crossings'], row['b_crossings']),
            title_fontsize=5.2, tick_step=50)
        ax.tick_params(labelsize=2.6, length=0.8, pad=0.4)
        ax.set_xlabel('')
        ax.set_ylabel('')
        for spine in ax.spines.values():
            spine.set_visible(False)
    total_a = sum(row['a_crossings'] for row in rows)
    total_b = sum(row['b_crossings'] for row in rows)
    fig.suptitle(
        '20-height overview: routing bodies on every physical height '
        '(20 heights = 18 body planes + 2 interface planes)\n'
        'A %s (blue): %d crossing events / %d pairs   |   B %s (red): %d / %d'
        '   |   difference B-A: %+d events'
        % (state_a['label'], total_a, sum(row['a_pairs'] for row in rows),
           state_b['label'], total_b, sum(row['b_pairs'] for row in rows),
           total_b - total_a), fontsize=10.6, y=0.992)
    fig.text(0.5, 0.008,
             'every routed body at that height is drawn for both states on the '
             'same 150 x 150 mm board; the two overlays share the same scale so '
             'identical routes appear as a red line over a blue one.  Per-panel '
             'counts are the authoritative per-height crossing events of each '
             'state (%s / %s).'
             % (state_a['counts_source'], state_b['counts_source']),
             ha='center', fontsize=6.4, color='#333333')
    return save_figure(fig, out_dir, 'compare_layers_overview', dpi, with_svg,
                       pad=0.08)


def cmd_compare_layers(args, started_at, began):
    inputs_root = Path(args.out_dir) / '_inputs'
    state_a = analyze_state(args.a, inputs_root, label=args.a_label)
    state_b = analyze_state(args.b, inputs_root, label=args.b_label)
    _verify_same_model(state_a, state_b)
    target = Path(args.out_dir) / 'compare_layers'
    target.mkdir(parents=True, exist_ok=True)
    outputs, rows = [], []
    planes = state_a['model'].planes
    for index, plane in enumerate(planes):
        pid = int(plane['plane_id'])
        info_a = state_a['per_plane'][pid]
        info_b = state_b['per_plane'][pid]
        z_mm = float(plane['z_mm'])
        fig = plt.figure(figsize=(14.2, 7.4))
        ax_a = fig.add_axes([0.045, 0.100, 0.415, 0.715])
        ax_b = fig.add_axes([0.540, 0.100, 0.415, 0.715])
        _draw_layer_panel(
            ax_a, state_a, info_a,
            'A  %s\nplane %d  %s  z=%s mm\nbody routes %d | crossings %d '
            'events / %d pairs'
            % (state_a['label'], pid, info_a['label'], fmt_z(z_mm),
               info_a['route_count'], info_a['crossing_count'],
               info_a['crossing_pairs']), COLOR_A)
        _draw_layer_panel(
            ax_b, state_b, info_b,
            'B  %s\nplane %d  %s  z=%s mm\nbody routes %d | crossings %d '
            'events / %d pairs'
            % (state_b['label'], pid, info_b['label'], fmt_z(z_mm),
               info_b['route_count'], info_b['crossing_count'],
               info_b['crossing_pairs']), COLOR_B)
        row = dict(order_index=index + 1, plane_id=pid,
                   label=str(plane['label']), z_mm=round(z_mm, 6),
                   a_crossings=int(info_a['crossing_count']),
                   a_pairs=int(info_a['crossing_pairs']),
                   a_routes=int(info_a['route_count']),
                   b_crossings=int(info_b['crossing_count']),
                   b_pairs=int(info_b['crossing_pairs']),
                   b_routes=int(info_b['route_count']),
                   delta_crossings=int(info_b['crossing_count'])
                   - int(info_a['crossing_count']))
        rows.append(row)
        handles = L20._legend_handles(info_a, True)
        fig.legend(handles=handles, loc='lower center',
                   ncol=min(7, max(2, len(handles))), fontsize=6.9,
                   frameon=True, framealpha=0.92, bbox_to_anchor=(0.5, 0.012))
        fig.suptitle(
            'height %d/%d  -  %s  -  plane %d  -  z = %s mm  -  '
            'left A / right B (same board, same scale, equal aspect)'
            % (index + 1, len(planes), info_a['label'], pid, fmt_z(z_mm)),
            fontsize=10.8, y=0.985)
        fig.text(0.5, 0.936,
                 'crossings: A %d events / %d pairs   B %d / %d   '
                 '(B-A %+d events)  -  counts: %s / %s'
                 % (info_a['crossing_count'], info_a['crossing_pairs'],
                    info_b['crossing_count'], info_b['crossing_pairs'],
                    row['delta_crossings'],
                    state_a['counts_source'], state_b['counts_source']),
                 ha='center', fontsize=6.8, color='#333333')
        outputs.extend(save_figure(
            fig, target, 'compare_layer_%02d_%s_z%s'
            % (index + 1, sanitize(info_a['label'], 12), fmt_z(z_mm)),
            args.dpi, not args.no_svg))
    outputs.extend(_compare_overview(state_a, state_b, target, rows,
                                     args.dpi, not args.no_svg))
    write_csv(target / 'compare_layer_counts.csv', rows)
    write_json(target / 'compare_layer_counts.json', dict(
        schema='20h_ablation_compare_layers_v1',
        generated_at=now_local(),
        a=dict(label=state_a['label'], dir=rel(state_a['run_dir']),
               counts_source=state_a['counts_source']),
        b=dict(label=state_b['label'], dir=rel(state_b['run_dir']),
               counts_source=state_b['counts_source']),
        plane_count=len(planes),
        totals=dict(
            a_crossings=sum(row['a_crossings'] for row in rows),
            a_pairs=sum(row['a_pairs'] for row in rows),
            b_crossings=sum(row['b_crossings'] for row in rows),
            b_pairs=sum(row['b_pairs'] for row in rows),
            delta_crossings=sum(row['delta_crossings'] for row in rows)),
        per_height=rows))
    sources = state_sources(state_a) + state_sources(state_b)
    notes = dict(
        panels=len(planes) + 1,
        description='one 2-panel figure per routing height + one 20-height '
                    'overview; same board/scale/equal aspect in both panels',
        a=state_notes(state_a), b=state_notes(state_b),
        plane_labels=[str(plane['label']) for plane in planes],
        z_mm=[float(plane['z_mm']) for plane in planes],
        dpi=int(args.dpi),
        formats=(['png', 'svg'] if not args.no_svg else ['png']))
    record_manifest(args.out_dir, 'compare-layers',
                    [SCRIPT_REL, 'compare-layers', '--a', args.a, '--b',
                     args.b, '--out-dir', str(args.out_dir),
                     '--a-label', args.a_label, '--b-label', args.b_label],
                    sources, outputs, notes, started_at, time.time() - began)
    write_readme(args.out_dir)
    print('[compare-layers] %d figures -> %s' % (len(outputs), target),
          flush=True)
    return 0


# ===========================================================================
# 3. global3d -- true 3-D comparison of the two complete routings
# ===========================================================================
def _draw_global_3d(ax, state, label, elev, azim):
    ds = state['ds']
    model = state['model']
    cmap = plt.get_cmap('turbo')
    norm = plt.Normalize(model.z_min, model.z_max)
    buckets = OrderedDict()
    skipped = 0
    route_plane = ds.get('route_plane') or {}
    for record in ds['routed']:
        route_id = as_int(record.get('route_id'))
        polyline = P.route_3d_polyline(record)
        if polyline is None or len(polyline) < 2:
            skipped += 1
            continue
        plane_id = route_plane.get(route_id)
        buckets.setdefault(plane_id, []).append(np.asarray(polyline, dtype=float))
    for plane in model.planes:
        segments = buckets.get(int(plane['plane_id'])) or []
        if not segments:
            continue
        collection = Line3DCollection(
            segments, colors=[cmap(norm(float(plane['z_mm'])))],
            linewidths=0.24, alpha=0.52)
        ax.add_collection3d(collection, autolim=False)
    other = buckets.get(None) or []
    if other:
        ax.add_collection3d(Line3DCollection(other, colors=['#7f7f7f'],
                                             linewidths=0.24, alpha=0.5),
                            autolim=False)
    glass = state['glass']
    z_min, z_max = float(glass['z_min_mm']), float(glass['z_max_mm'])
    edge = dict(color='#4575a3', lw=0.7, alpha=0.8)
    corners = [(0.0, 0.0), (BOARD_MM, 0.0), (BOARD_MM, BOARD_MM),
               (0.0, BOARD_MM), (0.0, 0.0)]
    for z_value in (z_min, z_max):
        ax.plot([c[0] for c in corners], [c[1] for c in corners],
                [z_value] * len(corners), **edge)
    for x_corner, y_corner in corners[:-1]:
        ax.plot([x_corner, x_corner], [y_corner, y_corner], [z_min, z_max],
                **edge)
    ax.set_xlim(0.0, BOARD_MM)
    ax.set_ylim(0.0, BOARD_MM)
    ax.set_zlim(z_min - 0.03, z_max + 0.06)
    ax.set_xticks(list(range(0, int(BOARD_MM) + 1, 25)))
    ax.set_yticks(list(range(0, int(BOARD_MM) + 1, 25)))
    ax.set_zticks([-0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    ax.tick_params(labelsize=5.8, pad=0.4)
    ax.set_xlabel('X (mm)', fontsize=8.0, labelpad=2)
    ax.set_ylabel('Y (mm)', fontsize=8.0, labelpad=2)
    ax.set_zlabel('Z (mm)', fontsize=8.0, labelpad=2)
    ax.view_init(elev=elev, azim=azim)
    ax.set_box_aspect((1.0, 1.0, 0.40), zoom=1.10)
    ax.grid(True, lw=0.25, alpha=0.25)
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.pane.set_alpha(0.06)
    crossings = sum(int(info['crossing_count'])
                    for info in state['per_plane'].values())
    pairs = sum(int(info['crossing_pairs'])
                for info in state['per_plane'].values())
    ax.set_title('%s\n%d centre lines, crossings %d / %d pairs'
                 % (label, len(ds['routed']) - skipped, crossings, pairs),
                 fontsize=8.6)
    return dict(routes_drawn=len(ds['routed']) - skipped, routes_skipped=skipped,
                crossings=crossings, crossing_pairs=pairs,
                counts_source=state['counts_source'])


def cmd_global3d(args, started_at, began):
    inputs_root = Path(args.out_dir) / '_inputs'
    state_a = analyze_state(args.a, inputs_root, label=args.a_label)
    state_b = analyze_state(args.b, inputs_root, label=args.b_label)
    _verify_same_model(state_a, state_b)
    target = Path(args.out_dir) / 'global3d'
    target.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(17.0, 9.0))
    ax_a = fig.add_axes([0.005, 0.040, 0.462, 0.775], projection='3d')
    ax_b = fig.add_axes([0.475, 0.040, 0.462, 0.775], projection='3d')
    info_a = _draw_global_3d(ax_a, state_a, state_a['label'],
                             args.elev, args.azim)
    info_b = _draw_global_3d(ax_b, state_b, state_b['label'],
                             args.elev, args.azim)
    ax_a.title.set_color(COLOR_A)
    ax_b.title.set_color(COLOR_B)
    cax = fig.add_axes([0.955, 0.22, 0.010, 0.56])
    model = state_a['model']
    mappable = plt.cm.ScalarMappable(
        norm=plt.Normalize(model.z_min, model.z_max),
        cmap=plt.get_cmap('turbo'))
    mappable.set_array(np.asarray([model.z_min, model.z_max]))
    colorbar = fig.colorbar(mappable, cax=cax)
    colorbar.set_ticks([float(plane['z_mm']) for plane in model.planes])
    colorbar.set_ticklabels(['%s %s' % (plane['label'], fmt_z(plane['z_mm']))
                             for plane in model.planes])
    colorbar.ax.tick_params(labelsize=5.4, length=2.0, pad=1.0)
    colorbar.set_label('routing height z (mm) - 20 heights (18 body + 2 '
                       'interface)', fontsize=6.8)
    glass = state_a['glass']
    fig.suptitle(
        'True-3-D global routing comparison  -  A: %s  vs  B: %s\n'
        'all %d real centre lines per state, transitions included, colour = '
        'routing height; glass envelope %d x %d x %.2f mm; view elev %.0f / '
        'azim %.0f deg'
        % (state_a['label'], state_b['label'], len(state_a['ds']['routed']),
           int(BOARD_MM), int(BOARD_MM), glass['thickness_mm'],
           args.elev, args.azim), fontsize=10.6, y=0.985)
    fig.text(0.5, 0.012,
             'crossings: A %d events / %d pairs (%s)   B %d / %d (%s)   -   '
             'geometry: routes_l3d.json flats sampled at %s mm, S-curve '
             'transitions at %s mm (frozen plots21.route_3d_polyline)'
             % (info_a['crossings'], info_a['crossing_pairs'],
                state_a['counts_source'], info_b['crossings'],
                info_b['crossing_pairs'], state_b['counts_source'],
                getattr(P, 'STEP_3D_FLAT_MM', 2.0),
                getattr(P, 'STEP_3D_TRANSITION_MM', 0.06)),
             ha='center', fontsize=6.6, color='#333333')
    outputs = save_figure(fig, target, 'global3d_compare_A_%s_B_%s'
                          % (sanitize(state_a['label'], 28),
                             sanitize(state_b['label'], 28)),
                          args.dpi, not args.no_svg, pad=0.10)
    payload = dict(
        schema='20h_ablation_global3d_v1', generated_at=now_local(),
        plane_count=len(state_a['model'].planes),
        view=dict(elev=args.elev, azim=args.azim),
        glass=glass, board_mm=BOARD_MM,
        description='every routed route drawn as its stored 3-D centre line '
                    '(flat primitives + analytic S-curve transition samples); '
                    'coloured by routing height; crossings from the state '
                    'statistics (authoritative or exact recomputation)')
    payload['a'] = dict(label=state_a['label'],
                        dir=rel(state_a['run_dir']))
    payload['a'].update({key: value for key, value in info_a.items()
                         if key != 'counts_source'})
    payload['a']['counts_source'] = state_a['counts_source']
    payload['b'] = dict(label=state_b['label'],
                        dir=rel(state_b['run_dir']))
    payload['b'].update({key: value for key, value in info_b.items()
                         if key != 'counts_source'})
    payload['b']['counts_source'] = state_b['counts_source']
    write_json(target / 'global3d_compare.json', payload)
    notes = dict(description=payload['description'],
                 a=state_notes(state_a), b=state_notes(state_b),
                 view=payload['view'], dpi=int(args.dpi),
                 formats=(['png', 'svg'] if not args.no_svg else ['png']))
    record_manifest(args.out_dir, 'global3d',
                    [SCRIPT_REL, 'global3d', '--a', args.a, '--b', args.b,
                     '--out-dir', str(args.out_dir), '--elev', str(args.elev),
                     '--azim', str(args.azim)],
                    state_sources(state_a) + state_sources(state_b),
                    outputs, notes, started_at, time.time() - began)
    write_readme(args.out_dir)
    print('[global3d] wrote %s' % (outputs[0]['path'] if outputs else target),
          flush=True)
    return 0


# ===========================================================================
# 4. route-case -- the same route in both states, real local geometry
# ===========================================================================
def _routes_by_id(state):
    payload = (state['ds'].get('routes') or {}).get('payload') or {}
    return {int(route['route_id']): route
            for route in payload.get('routes') or ()
            if route.get('route_id') is not None}


def _rows_by_id(state):
    return {int(row['route_id']): row for row in state['ds'].get(
        'assignment_rows') or () if as_int(row.get('route_id')) is not None}


def _flat_parts(route):
    return [part for part in route.get('parts') or ()
            if part.get('kind') == 'flat'
            and (part.get('primitives') or ())]


def _target_body_parts(route):
    layer = as_int(route.get('target_layer'))
    z_mm = as_float(route.get('target_z_mm'))
    parts = []
    for part in _flat_parts(route):
        part_layer = as_int(part.get('layer_id'))
        part_z = as_float(part.get('z_mm'))
        if layer is not None and part_layer is not None:
            if part_layer != layer:
                continue
        elif z_mm is not None and part_z is not None:
            if abs(part_z - z_mm) > 1e-6:
                continue
        else:
            continue
        parts.append(part)
    return parts


def _prim_array(prim, samples=64):
    if prim.get('kind') == 'line':
        return np.asarray([prim['p0'], prim['p1']], dtype=float)
    if prim.get('kind') == 'arc':
        cx, cy = float(prim['center'][0]), float(prim['center'][1])
        radius = float(prim['radius'])
        start = float(prim['start_angle'])
        sweep = float(prim['sweep'])
        angles = start + sweep * np.linspace(0.0, 1.0, samples)
        return np.column_stack((cx + radius * np.cos(angles),
                                cy + radius * np.sin(angles)))
    return np.zeros((0, 2), dtype=float)


def _chain_array(parts, samples=64):
    arrays = [array for array in
              (_prim_array(prim, samples) for part in parts
               for prim in part.get('primitives') or ())
              if len(array) >= 2]
    if not arrays:
        return np.zeros((0, 2), dtype=float)
    return np.vstack(arrays)


def _transition_arrays(route):
    arrays = []
    for part in route.get('parts') or ():
        if part.get('kind') != 'transition':
            continue
        try:
            samples = P._transition_samples_local(part)
        except Exception:                                   # noqa: BLE001
            continue
        if samples and len(samples) >= 2:
            arrays.append(np.asarray([[item[0], item[1]] for item in samples],
                                     dtype=float))
    return arrays


def _window_hit(arrays, window):
    x0, x1, y0, y1 = window
    for array in arrays:
        if array.size == 0:
            continue
        if (array[:, 0].max() >= x0 and array[:, 0].min() <= x1
                and array[:, 1].max() >= y0 and array[:, 1].min() <= y1):
            return True
    return False


def _parts_at_z(route, z_mm, tol=1e-6):
    result = []
    for part in _flat_parts(route):
        part_z = as_float(part.get('z_mm'))
        if part_z is not None and abs(part_z - float(z_mm)) <= tol:
            result.append(part)
    return result


def _draw_background_window(ax, routes, z_mm, window, color=COLOR_OTHER,
                            alpha=0.30, linewidth=0.65):
    segments = []
    for route in routes.values():
        for part in _parts_at_z(route, z_mm):
            arrays = [_prim_array(prim, 40) for prim in part.get('primitives') or ()]
            arrays = [array for array in arrays if len(array) >= 2]
            if not arrays or not _window_hit(arrays, window):
                continue
            segments.extend(arrays)
    if segments:
        ax.add_collection(LineCollection(segments, colors=color,
                                         linewidths=linewidth, alpha=alpha,
                                         zorder=2))
    return len(segments)


def _route_case_panel(ax, state, rid, window, color, label, pad_mm):
    routes = _routes_by_id(state)
    if rid not in routes:
        raise DataError('route %d is not present in state %s (%s)'
                        % (rid, state['label'], state['run_dir']))
    route = routes[rid]
    rows = _rows_by_id(state)
    row = rows.get(rid) or {}
    body_z = as_float(route.get('target_z_mm'))
    if body_z is None:
        raise DataError('route %d of %s has no target_z_mm' % (rid, state['label']))
    body_parts = _target_body_parts(route)
    if not body_parts:
        raise DataError('route %d of %s has no body flat on its target height '
                        '(target_layer=%s, target_z_mm=%s)'
                        % (rid, state['label'], route.get('target_layer'),
                           route.get('target_z_mm')))
    body_prims = [prim for part in body_parts
                  for prim in part.get('primitives') or ()]
    body_arrays = [_prim_array(prim) for prim in body_prims]
    body_arrays = [array for array in body_arrays if len(array) >= 2]
    body_all = np.vstack(body_arrays)
    regions = L2.local_multi_arc_regions(body_prims)

    _draw_background_window(ax, routes, body_z, window)
    # full XY footprint of this route (all heights + transitions), very light
    footprint = [_prim_array(prim, 40) for part in _flat_parts(route)
                 for prim in part.get('primitives') or ()]
    footprint = [array for array in footprint if len(array) >= 2]
    footprint.extend(_transition_arrays(route))
    if footprint:
        ax.add_collection(LineCollection(footprint, colors='#b0b7bf',
                                         linewidths=0.9, alpha=0.55,
                                         zorder=3))
    for prim, array in zip(body_prims, body_arrays):
        if prim.get('kind') == 'arc':
            ax.plot(array[:, 0], array[:, 1], color=color, linewidth=3.1,
                    zorder=6, solid_capstyle='round')
        else:
            ax.plot(array[:, 0], array[:, 1], color=color, linewidth=1.8,
                    zorder=5)
    for region in regions:
        start = region['start']
        end = region['end']
        ax.add_patch(Circle(start, 1.6, fill=False, color='#6a1b9a', lw=1.2,
                            zorder=8))
        ax.add_patch(Circle(end, 1.6, fill=False, color='#6a1b9a', lw=1.2,
                            zorder=8))
        mid_x = 0.5 * (float(start[0]) + float(end[0]))
        mid_y = 0.5 * (float(start[1]) + float(end[1]))
        ax.annotate('multi-arc region\n%d arcs (opposite sweeps)'
                    % int(region['n_arcs']), xy=(mid_x, mid_y),
                    xytext=(0, 10), textcoords='offset points',
                    ha='center', fontsize=6.4, color='#4a148c',
                    bbox=dict(boxstyle='round,pad=0.2', fc='#f3e5f5',
                              ec='#8e24aa', lw=0.6, alpha=0.92),
                    arrowprops=dict(arrowstyle='-', color='#8e24aa', lw=0.7),
                    zorder=9)
    # real ports (same identity in both states)
    for prefix, marker, name in (('source', 'o', 'source'),
                                 ('target', 's', 'target')):
        x_mm = as_float(row.get(prefix + '_x_mm'))
        y_mm = as_float(row.get(prefix + '_y_mm'))
        if x_mm is None or y_mm is None:
            continue
        if not (window[0] - 3 <= x_mm <= window[1] + 3
                and window[2] - 3 <= y_mm <= window[3] + 3):
            continue
        ax.scatter([x_mm], [y_mm], s=46, marker=marker, color=color,
                   edgecolors='white', linewidths=0.6, zorder=11)
        ax.annotate(name, xy=(x_mm, y_mm), xytext=(4, 4),
                    textcoords='offset points', fontsize=6.0, color=color,
                    zorder=11)
    # real crossing events that involve this route and sit on this height
    events = [event for event in state['crossing_events']
              if rid in (as_int(event.get('route_a')),
                         as_int(event.get('route_b')))
              and abs(as_float(event.get('z_mm')) - body_z) <= AXIS_Z_TOL]
    in_window = []
    for event in events:
        x_mm, y_mm = as_float(event.get('x_mm')), as_float(event.get('y_mm'))
        if x_mm is None or y_mm is None:
            continue
        if window[0] <= x_mm <= window[1] and window[2] <= y_mm <= window[3]:
            in_window.append((x_mm, y_mm))
    if in_window:
        points = np.asarray(in_window)
        ax.scatter(points[:, 0], points[:, 1], marker='x', s=34,
                   c=COLOR_CROSS, linewidths=1.0, zorder=12,
                   label='crossing of this route')
    ax.set_xlim(window[0], window[1])
    ax.set_ylim(window[2], window[3])
    ax.set_aspect('equal', adjustable='box')
    ax.grid(alpha=0.18)
    ax.set_xlabel('x (mm)', fontsize=7.4)
    ax.set_ylabel('y (mm)', fontsize=7.4)
    ax.tick_params(labelsize=6.0, length=2.0, pad=0.8)
    arc_count = sum(1 for prim in body_prims if prim.get('kind') == 'arc')
    line_count = sum(1 for prim in body_prims if prim.get('kind') == 'line')
    per_route = (state['per_route_crossings'].get(rid, 0)
                 if state['per_route_crossings'] else None)
    ax.set_title(
        '%s: route %d\nz = %s mm  |  body: %d arcs / %d lines  |  multi-arc '
        'regions %d  |  crossings %s%s'
        % (label, rid, fmt_z(body_z), arc_count, line_count, len(regions),
           ('%d total' % per_route) if per_route is not None else 'n/a',
           ('  (%d in window)' % len(in_window)) if in_window else ''),
        fontsize=8.4, color=color)
    return dict(route_id=rid, state=state['label'], z_mm=body_z,
                n_arcs=arc_count, n_lines=line_count,
                n_multi_arc_regions=len(regions),
                multi_arc_signs=[int(sign) for region in regions
                                 for sign in region['signs']],
                length_mm=as_float(route.get('length_mm')),
                per_route_crossings=per_route,
                crossings_in_window=len(in_window),
                body_primitives=len(body_prims),
                n_transitions=int(route.get('n_transitions') or 0),
                target_layer=as_int(route.get('target_layer')),
                source_endpoint=route.get('source_endpoint'),
                target_endpoint=route.get('target_endpoint'))


def _route_body_bounds(state, rid):
    route = _routes_by_id(state)[rid]
    body_parts = _target_body_parts(route)
    array = _chain_array(body_parts)
    if len(array) == 0:
        raise DataError('route %d of %s has no body geometry'
                        % (rid, state['label']))
    return (float(array[:, 0].min()), float(array[:, 0].max()),
            float(array[:, 1].min()), float(array[:, 1].max()))


def _dense_body_points(parts, step=1.0):
    """Dense XY samples of a body chain (lines interpolated at <= ``step`` mm)."""
    points = []
    for part in parts:
        for prim in part.get('primitives') or ():
            kind = prim.get('kind')
            if kind == 'line':
                p0 = np.asarray(prim['p0'], dtype=float)
                p1 = np.asarray(prim['p1'], dtype=float)
                length = float(np.hypot(*(p1 - p0)))
                count = max(2, int(math.ceil(length / step)) + 1)
                t = np.linspace(0.0, 1.0, count)[:, None]
                points.append(p0[None, :] * (1.0 - t) + p1[None, :] * t)
            elif kind == 'arc':
                radius = float(prim['radius'])
                length = radius * abs(float(prim['sweep']))
                count = max(4, int(math.ceil(length / step)) + 1)
                cx, cy = float(prim['center'][0]), float(prim['center'][1])
                angles = (float(prim['start_angle'])
                          + float(prim['sweep']) * np.linspace(0.0, 1.0, count))
                points.append(np.column_stack(
                    (cx + radius * np.cos(angles),
                     cy + radius * np.sin(angles))))
    if not points:
        return np.zeros((0, 2), dtype=float)
    return np.vstack(points)


def _symmetric_difference_bbox(state_a, rid, state_b, threshold=1.0):
    """Bounding box of the points where the two real bodies differ.

    A point of body A whose nearest point of body B is farther than
    ``threshold`` mm (and vice versa) marks a genuine geometric difference --
    exactly the multi-arc region / ablated detour a route-case figure must
    show.  Returns ``None`` when the stored geometry is identical.
    """
    points_a = _dense_body_points(_target_body_parts(_routes_by_id(state_a)[rid]))
    points_b = _dense_body_points(_target_body_parts(_routes_by_id(state_b)[rid]))
    if len(points_a) == 0 or len(points_b) == 0:
        return None
    diffs = []
    for points, other in ((points_a, points_b), (points_b, points_a)):
        if len(points) > 4000:
            stride = int(math.ceil(len(points) / 4000.0))
            points = points[::stride]
        if len(other) > 4000:
            stride = int(math.ceil(len(other) / 4000.0))
            other = other[::stride]
        chunk = 512
        for start in range(0, len(points), chunk):
            block = points[start:start + chunk]
            distances = np.sqrt(((block[:, None, :] - other[None, :, :]) ** 2
                                 ).sum(axis=2))
            nearest = distances.min(axis=1)
            diffs.append(block[nearest > threshold])
    diff = np.vstack(diffs) if diffs else np.zeros((0, 2))
    if len(diff) == 0:
        return None
    return (float(diff[:, 0].min()), float(diff[:, 0].max()),
            float(diff[:, 1].min()), float(diff[:, 1].max()))


def _multi_arc_bbox(state, rid):
    prims = [prim for part in _target_body_parts(_routes_by_id(state)[rid])
             for prim in part.get('primitives') or ()]
    regions = L2.local_multi_arc_regions(prims)
    if not regions:
        return None
    xs = [float(region['start'][0]) for region in regions] + \
         [float(region['end'][0]) for region in regions]
    ys = [float(region['start'][1]) for region in regions] + \
         [float(region['end'][1]) for region in regions]
    return (min(xs), max(xs), min(ys), max(ys))


def _square_window(bbox, pad_mm, max_mm):
    x0, x1, y0, y1 = bbox
    side = max(x1 - x0, y1 - y0, 8.0) + 2.0 * pad_mm
    if max_mm and side > float(max_mm):
        side = float(max_mm)
    cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
    low_x = max(0.0, cx - side / 2.0)
    high_x = min(BOARD_MM, low_x + side)
    low_x = max(0.0, high_x - side)
    low_y = max(0.0, cy - side / 2.0)
    high_y = min(BOARD_MM, low_y + side)
    low_y = max(0.0, high_y - side)
    return (low_x, high_x, low_y, high_y)


def _route_window(state_a, rid, state_b, pad_mm, max_mm=80.0):
    """Local window: centred on the geometry difference (multi-arc/detour)."""
    diff_bbox = _symmetric_difference_bbox(state_a, rid, state_b)
    if diff_bbox is not None:
        rule = 'geometry-difference bbox'
        return _square_window(diff_bbox, pad_mm, max_mm), rule
    multi = _multi_arc_bbox(state_a, rid) or _multi_arc_bbox(state_b, rid)
    if multi is not None:
        rule = 'multi-arc region bbox (bodies geometrically identical)'
        return _square_window(multi, pad_mm, max_mm), rule
    rule = 'body bbox (no local difference, no multi-arc region)'
    boxes = [_route_body_bounds(state_a, rid), _route_body_bounds(state_b, rid)]
    bbox = (min(box[0] for box in boxes), max(box[1] for box in boxes),
            min(box[2] for box in boxes), max(box[3] for box in boxes))
    return _square_window(bbox, pad_mm, max_mm), rule


def _auto_route_ids(state_a, state_b, top):
    routes_a = _routes_by_id(state_a)
    routes_b = _routes_by_id(state_b)
    common = sorted(set(routes_a) & set(routes_b))
    if not common:
        raise DataError('the two states share no route ids')
    per_a = state_a['per_route_crossings']
    per_b = state_b['per_route_crossings']
    ranked = []
    if per_a and per_b:
        ranked = sorted(common, key=lambda rid: abs(int(per_b.get(rid, 0))
                                                    - int(per_a.get(rid, 0))),
                        reverse=True)
    else:
        counter = Counter()
        for event in state_a['crossing_events'] + state_b['crossing_events']:
            for key in ('route_a', 'route_b'):
                rid = as_int(event.get(key))
                if rid in set(common):
                    counter[rid] += 1
        ranked = [rid for rid in counter]
    picks = []
    for rid in ranked:
        if rid not in picks:
            picks.append(rid)
        if len(picks) >= top:
            break
    if not picks:
        raise DataError('cannot auto-select a route case (no per-route '
                        'crossing statistics in either state); pass --route-id')
    return picks


def _parse_route_ids(text):
    if str(text).strip().lower() in ('auto', 'largest', ''):
        return None
    ids = []
    for chunk in str(text).replace(';', ',').split(','):
        chunk = chunk.strip()
        if not chunk:
            continue
        value = as_int(chunk)
        if value is None:
            raise DataError('--route-id expects integers, got %r' % chunk)
        ids.append(value)
    if not ids:
        raise DataError('--route-id is empty')
    return ids


def cmd_route_case(args, started_at, began):
    inputs_root = Path(args.out_dir) / '_inputs'
    state_a = analyze_state(args.a, inputs_root, label=args.a_label)
    state_b = analyze_state(args.b, inputs_root, label=args.b_label)
    _verify_same_model(state_a, state_b)
    rid_list = _parse_route_ids(args.route_id)
    if rid_list is None:
        rid_list = _auto_route_ids(state_a, state_b, max(1, args.top))
        selection = 'auto: largest |per-route crossing difference|'
    else:
        selection = 'explicit --route-id %s' % args.route_id
    target = Path(args.out_dir) / 'route_cases'
    target.mkdir(parents=True, exist_ok=True)
    outputs, rows = [], []
    for rid in rid_list:
        window, window_rule = _route_window(state_a, rid, state_b,
                                            args.pad_mm, args.window_max_mm)
        differs = _symmetric_difference_bbox(state_a, rid, state_b) is not None
        fig = plt.figure(figsize=(14.6, 7.6))
        ax_a = fig.add_axes([0.045, 0.085, 0.435, 0.700])
        ax_b = fig.add_axes([0.535, 0.085, 0.435, 0.700])
        info_a = _route_case_panel(ax_a, state_a, rid, window, COLOR_A,
                                   state_a['label'], args.pad_mm)
        info_b = _route_case_panel(ax_b, state_b, rid, window, COLOR_B,
                                   state_b['label'], args.pad_mm)
        fig.suptitle(
            'route %d  -  local XY geometry of the same route_id in both '
            'states  -  stored bodies %s  -  window: %s'
            % (rid, 'differ locally' if differs else 'identical',
               window_rule), fontsize=11.0, y=0.988)
        fig.text(0.5, 0.940,
                 'A %s: z=%s mm, body %d arcs / %d lines, multi-arc regions '
                 '%d, crossings %s    |    B %s: z=%s mm, body %d arcs / %d '
                 'lines, multi-arc regions %d, crossings %s'
                 % (state_a['label'], fmt_z(info_a['z_mm']),
                    info_a['n_arcs'], info_a['n_lines'],
                    info_a['n_multi_arc_regions'],
                    info_a['per_route_crossings'], state_b['label'],
                    fmt_z(info_b['z_mm']), info_b['n_arcs'], info_b['n_lines'],
                    info_b['n_multi_arc_regions'],
                    info_b['per_route_crossings']),
                 ha='center', fontsize=7.2, color='#222222')
        fig.text(0.5, 0.910,
                 'grey = other routes on the same physical height inside the '
                 'window  -  light grey = full XY footprint of this route  -  '
                 'red x = real same-height crossing events of this route  -  '
                 'purple circles = planar multi-arc region in the stored body  '
                 '-  window x[%.1f, %.1f] y[%.1f, %.1f] mm'
                 % (window[0], window[1], window[2], window[3]),
                 ha='center', fontsize=6.2, color='#444444')
        outputs.extend(save_figure(fig, target, 'route_case_%04d' % rid,
                                   args.dpi, not args.no_svg))
        row = dict(route_id=rid,
                   window_rule=window_rule,
                   bodies_differ_locally=differs,
                   window_x0_mm=round(window[0], 4),
                   window_x1_mm=round(window[1], 4),
                   window_y0_mm=round(window[2], 4),
                   window_y1_mm=round(window[3], 4))
        for prefix, info in (('a', info_a), ('b', info_b)):
            for key, value in info.items():
                if key == 'route_id':
                    continue
                if key == 'multi_arc_signs':
                    value = '|'.join(str(item) for item in value)
                row['%s_%s' % (prefix, key)] = value
        rows.append(row)
        print('[route-case] route %d (%s, bodies %s) -> %s'
              % (rid, window_rule,
                 'differ' if differs else 'identical',
                 target / ('route_case_%04d.png' % rid)), flush=True)
    write_csv(target / 'route_cases.csv', rows)
    write_json(target / 'route_cases.json', dict(
        schema='20h_ablation_route_cases_v1', generated_at=now_local(),
        selection=selection,
        a=dict(label=state_a['label'], dir=rel(state_a['run_dir']),
               counts_source=state_a['counts_source']),
        b=dict(label=state_b['label'], dir=rel(state_b['run_dir']),
               counts_source=state_b['counts_source']),
        window_rule='square window centred on the local geometry difference '
                    'between the two stored bodies (points farther than 1.0 mm '
                    'from the other body), else on the multi-arc region, else '
                    'on the body bbox; expanded by --pad-mm, capped at '
                    '--window-max-mm, clamped to the 150 x 150 mm board',
        cases=rows))
    notes = dict(selection=selection, route_ids=rid_list,
                 pad_mm=args.pad_mm, window_max_mm=args.window_max_mm,
                 a=state_notes(state_a),
                 b=state_notes(state_b), dpi=int(args.dpi),
                 formats=(['png', 'svg'] if not args.no_svg else ['png']))
    record_manifest(args.out_dir, 'route-case',
                    [SCRIPT_REL, 'route-case', '--a', args.a, '--b', args.b,
                     '--route-id', str(args.route_id), '--out-dir',
                     str(args.out_dir)], state_sources(state_a)
                    + state_sources(state_b), outputs, notes, started_at,
                    time.time() - began)
    write_readme(args.out_dir)
    return 0


# ==== IMPLEMENTATION-CONTINUES-2 ====



# ===========================================================================
# 5. layer-stats -- per-height crossing events / unique pairs / routes
# ===========================================================================
STATE_COLORS = (COLOR_A, COLOR_B, COLOR_START, '#2e7d32', '#6a1b9a',
                '#ef6c00', '#37474f')


def _chart_label(path):
    """Compact legend label for a state/run directory."""
    path = Path(path)
    last = sanitize(path.name, 34)
    if last == 'best_valid' and path.parent.name:
        return sanitize('%s-best_valid' % path.parent.name, 48)
    return last


def _states_from_args(args, inputs_root):
    specs = []
    for item in args.state or []:
        name, sep, path = str(item).partition('=')
        if not sep or not path.strip():
            raise DataError('--state expects name=dir, got %r' % item)
        specs.append((name.strip(), path.strip()))
    for path in args.run_dir or []:
        specs.append((None, path))
    if not specs:
        raise DataError('at least one --run-dir or --state is required')
    states = []
    for name, path in specs:
        states.append(analyze_state(path, inputs_root,
                                    label=name or _chart_label(resolve_path(path))))
    return states


def _exact_z_verification(state):
    """Exact-z bookkeeping of the real crossing_events list (per height)."""
    if not state['crossing_events']:
        return {}, dict(available=False,
                        note='crossing_stats.json has no crossing_events list; '
                             'only the authoritative per-plane counters are '
                             'available')
    result = {}
    events = state['crossing_events']
    for event in events:
        z_mm = as_float(event.get('z_mm'))
        if z_mm is None:
            continue
        key = round(z_mm, 9)
        bucket = result.setdefault(key, dict(events=0, pairs=set(), routes=set()))
        bucket['events'] += 1
        route_a = as_int(event.get('route_a'))
        route_b = as_int(event.get('route_b'))
        pair = tuple(sorted((route_a, route_b)))
        bucket['pairs'].add(pair)
        bucket['routes'].update(item for item in (route_a, route_b)
                                if item is not None)
    verification = dict(
        available=True, events=len(events),
        note='crossing_events x/y/z matched to each physical height with '
             'abs(z_event - z_plane) <= %g' % AXIS_Z_TOL)
    return result, verification


def _layer_stats_state(state):
    exact, verification = _exact_z_verification(state)
    rows = []
    verified_all = True
    for index, plane in enumerate(state['model'].planes):
        pid = int(plane['plane_id'])
        z_mm = float(plane['z_mm'])
        info = state['per_plane'][pid]
        bucket = exact.get(round(z_mm, 9)) or dict(events=0, pairs=set(),
                                                   routes=set())
        events_z = bucket['events']
        pairs_z = len(bucket['pairs'])
        routes_z = len(bucket['routes'])
        match = None
        if verification['available']:
            match = bool(events_z == int(info['crossing_count'])
                         and pairs_z == int(info['crossing_pairs']))
            verified_all = verified_all and match
        rows.append(dict(
            state=state['label'], order_index=index + 1, plane_id=pid,
            label=str(plane['label']), z_mm=round(z_mm, 6),
            kind=str(plane.get('kind') or ''),
            role=str(plane.get('role_detail') or plane.get('role') or ''),
            is_interface=bool(plane.get('is_interface')),
            crossings=int(info['crossing_count']),
            crossing_pairs=int(info['crossing_pairs']),
            routes_with_body=int(info['route_count']),
            body_parts=int(info['body_parts']),
            body_arcs=int(info['body_arc_primitives']),
            multi_arc_regions=int(info['multi_arc_regions']),
            interface_lead_parts=int(info['interface_lead_parts']),
            events_from_events=(events_z if verification['available'] else None),
            pairs_from_events=(pairs_z if verification['available'] else None),
            routes_from_events=(routes_z if verification['available'] else None),
            exact_z_match=match,
            counts_source=state['counts_source']))
    verification['all_heights_match'] = bool(
        verification['available'] and verified_all)
    return rows, verification


def cmd_layer_stats(args, started_at, began):
    inputs_root = Path(args.out_dir) / '_inputs'
    states = _states_from_args(args, inputs_root)
    target = Path(args.out_dir) / 'layer_stats'
    target.mkdir(parents=True, exist_ok=True)
    rows, per_state = [], []
    for state in states:
        state_rows, verification = _layer_stats_state(state)
        rows.extend(state_rows)
        per_state.append(dict(label=state['label'],
                              dir=rel(state['run_dir']),
                              counts_source=state['counts_source'],
                              verification=verification,
                              per_height=state_rows))
    write_csv(target / 'layer_stats.csv', rows)
    payload = dict(
        schema='20h_ablation_layer_stats_v1', generated_at=now_local(),
        z_match_rule='exact z match: abs(z_crossing_event - z_plane) <= %g'
                     % AXIS_Z_TOL,
        plane_count=len(states[0]['model'].planes),
        plane_labels=[str(plane['label'])
                      for plane in states[0]['model'].planes],
        z_mm=[float(plane['z_mm']) for plane in states[0]['model'].planes],
        states=per_state,
        totals={state['label']: dict(
            crossings=int(sum(int(info['crossing_count'])
                              for info in state['per_plane'].values())),
            crossing_pairs=int(sum(int(info['crossing_pairs'])
                                   for info in state['per_plane'].values())),
            body_routes=int(sum(int(info['route_count'])
                                for info in state['per_plane'].values())),
            multi_arc_regions=int(sum(int(info['multi_arc_regions'])
                                      for info in state['per_plane'].values())),
            counts_source=state['counts_source'])
            for state in states})
    write_json(target / 'layer_stats.json', payload)

    fig = plt.figure(figsize=(16.6, 6.0))
    axes = [fig.add_axes([0.045, 0.235, 0.275, 0.640]),
            fig.add_axes([0.365, 0.235, 0.275, 0.640]),
            fig.add_axes([0.685, 0.235, 0.275, 0.640])]
    labels = payload['plane_labels']
    z_values = payload['z_mm']
    x = np.arange(len(labels))
    n = len(states)
    width = 0.8 / max(1, n)
    panel_defs = (('crossings', 'same-height crossing events'),
                  ('crossing_pairs', 'unique crossing route pairs'),
                  ('routes_with_body', 'route bodies assigned to the height'))
    for panel_index, (key, ylabel) in enumerate(panel_defs):
        ax = axes[panel_index]
        for offset, state in enumerate(states):
            values = [row[key] for row in rows if row['state'] == state['label']]
            ax.bar(x + (offset - (n - 1) / 2.0) * width, values, width,
                   label='%s (%d)' % (state['label'], sum(values)),
                   color=STATE_COLORS[offset % len(STATE_COLORS)],
                   edgecolor='white', linewidth=0.25)
        ax.set_xticks(x)
        ax.set_xticklabels(['%s\n%s' % (label, fmt_z(z_mm))
                            for label, z_mm in zip(labels, z_values)],
                           fontsize=5.6, rotation=90)
        ax.set_ylabel(ylabel, fontsize=8.4)
        ax.set_xlabel('physical height (label / z in mm)', fontsize=8.0)
        ax.grid(axis='y', alpha=0.22)
        ax.legend(fontsize=6.4, loc='upper right')
        ax.tick_params(labelsize=6.0)
        ax.set_title('(%s) %s' % ('abc'[panel_index], ylabel), fontsize=9.2)
    fig.suptitle(
        'Per physical height: crossing events / unique pairs / route bodies '
        '(20 routing heights = 18 body planes + 2 interface planes)\n'
        'counts: %s'
        % (', '.join('%s=%s' % (state['label'], state['counts_source'])
                     for state in states)), fontsize=10.4, y=0.985)
    fig.text(0.5, 0.028,
             'exact-z matching: every real crossing event is assigned to a '
             'height iff |z_event - z_plane| <= %g mm; authoritative per-plane '
             'counters and event-derived counters agree everywhere: %s.  '
             'Panels: (a) crossing events, (b) unique route pairs, (c) route '
             'bodies assigned to the height.'
             % (AXIS_Z_TOL, ', '.join(
                 '%s=%s' % (item['label'],
                            item['verification'].get('all_heights_match'))
                 for item in per_state)), ha='center', fontsize=6.4,
             color='#333333')
    outputs = save_figure(fig, target, 'layer_stats_bars', args.dpi,
                          not args.no_svg, pad=0.10)
    def _state_note(state, index):
        item = dict(label=state['label'], dir=rel(state['run_dir']),
                    verification=per_state[index]['verification'])
        item.update(state_notes(state))
        return item

    notes = dict(plane_count=payload['plane_count'],
                 z_match_rule=payload['z_match_rule'],
                 states=[_state_note(state, index)
                         for index, state in enumerate(states)],
                 dpi=int(args.dpi),
                 formats=(['png', 'svg'] if not args.no_svg else ['png']))
    sources = []
    for state in states:
        sources.extend(state_sources(state))
    record_manifest(args.out_dir, 'layer-stats',
                    [SCRIPT_REL, 'layer-stats', '--out-dir', str(args.out_dir),
                     '--dpi', str(args.dpi)]
                    + sum((['--run-dir', path] for path in args.run_dir or []),
                          [])
                    + sum((['--state', item] for item in args.state or []), []),
                    sources, outputs + collect_outputs(
                        target, '*.csv', recursive=False) + collect_outputs(
                        target, 'layer_stats.json', recursive=False),
                    notes, started_at, time.time() - began)
    write_readme(args.out_dir)
    print('[layer-stats] %d heights x %d state(s) -> %s'
          % (payload['plane_count'], len(states), target), flush=True)
    return 0


# ===========================================================================
# 6. offset-2r -- Stage-0 conversion lateral offset vs 2R = 30 mm
# ===========================================================================
def _report_path(value):
    """Resolve a path stored in conversion_report.json (abs or project-rel)."""
    if value is None:
        raise DataError('conversion_report.json is missing a required path field')
    path = Path(str(value))
    if path.is_absolute():
        return path
    return (PROJECT_ROOT / path).resolve()


def _normalized_rows_by_id(state):
    rows = state['ds'].get('assignment_rows') or []
    if not rows:
        raise DataError('state %s has no assignment rows' % state['label'])
    normalized = RB.normalized_rows([dict(row) for row in rows], stack=None)
    result = {}
    for row in normalized:
        rid = as_int(row.get('route_id'))
        if rid is not None:
            result[rid] = row
    return result


def _canonical_lateral(row, route):
    """Frozen-D56 canonical frame lateral offset |bx| of one real route body.

    Uses ``route_builder.body_task`` (lifted body) / ``route_builder.direct_task``
    (interface-direct body) + ``layer2d.canonical_frame`` -- exactly the frame
    whose ``bx`` field the frozen grammar uses.  Returns (|bx|, frame_kind,
    error).
    """
    if row is None or route is None:
        return None, None, 'route/row missing'
    layer = as_int(row.get('target_layer'))
    z_mm = as_float(row.get('target_z_mm'))
    if layer is None or z_mm is None:
        return None, None, 'target layer/z missing'
    try:
        lead_s, lead_t = RB.lead_lengths(route)
        if layer in (1001, 1002):
            task = RB.direct_task(row)
        else:
            task = RB.body_task(row, layer, z_mm, lead_s, lead_t)[0]
        frame, error = L2.canonical_frame(task)
    except Exception as error:                              # noqa: BLE001
        return None, None, repr(error)
    if frame is None:
        return None, None, str(error)
    return abs(float(frame['bx'])), str(frame.get('kind') or ''), None


def _body_lateral_from_geometry(row, route):
    """World-frame lateral offset of the stored body landing points.

    Definition: let ``u`` be the inward unit direction of the source port
    (N=(0,-1), S=(0,1), E=(-1,0), W=(1,0)); the lateral unit vector is
    ``v = (-u_y, u_x)``.  The stored body chain of the route (all flat parts on
    the route's target plane, body flat first primitive p0 .. body flat last
    primitive p1) gives the two landing points A and B of the *actual built*
    body; the lateral offset is ``|v . (B - A)|``.  For N/S ports that is |dx|,
    for E/W ports |dy| -- the geometric cross-check of the canonical |bx|.
    """
    if route is None or row is None:
        return None, 'route/row missing'
    inward = row.get('source_inward')
    if not inward or len(inward) != 2:
        return None, 'source_inward missing'
    ux, uy = float(inward[0]), float(inward[1])
    vx, vy = -uy, ux
    body_parts = _target_body_parts(route)
    if not body_parts:
        return None, 'no body flat on the target height'
    prims = [prim for part in body_parts for prim in part.get('primitives') or ()]
    if not prims:
        return None, 'empty body primitives'
    try:
        start = prims[0].get('p0') or prims[0].get('start')
        end = prims[-1].get('p1') or prims[-1].get('end')
        dx = float(end[0]) - float(start[0])
        dy = float(end[1]) - float(start[1])
    except (TypeError, KeyError, IndexError, ValueError):
        return None, 'body endpoint missing'
    return abs(vx * dx + vy * dy), None


def _bucket_defs():
    return [(0.0, 5.0, '0-5'), (5.0, 10.0, '5-10'), (10.0, 15.0, '10-15'),
            (15.0, 20.0, '15-20'), (20.0, 25.0, '20-25'),
            (25.0, 30.0, '25-30 (below 2R)'), (30.0, 35.0, '30-35'),
            (35.0, 40.0, '35-40'), (40.0, 50.0, '40-50'),
            (50.0, float('inf'), '>50')]


def _summarise(values):
    values = [float(value) for value in values if value is not None]
    if not values:
        return dict(n=0, mean=None, median=None, min=None, max=None,
                    sum=None)
    ordered = sorted(values)
    n = len(values)
    median = (ordered[n // 2] if n % 2
              else 0.5 * (ordered[n // 2 - 1] + ordered[n // 2]))
    return dict(n=n, mean=round(sum(values) / n, 6),
                median=round(median, 6), min=ordered[0], max=ordered[-1],
                sum=round(sum(values), 6))


def _offset_rows(report, start_state, conv_state):
    start_routes = _routes_by_id(start_state)
    start_rows = _normalized_rows_by_id(start_state)
    conv_routes = _routes_by_id(conv_state)
    conv_rows = _normalized_rows_by_id(conv_state)
    start_per_route = start_state['per_route_crossings']
    conv_per_route = conv_state['per_route_crossings']
    records = report.get('records') or []
    if not records:
        raise DataError('conversion_report.json contains no records')
    rows, warnings = [], []
    for record in records:
        rid = as_int(record.get('route_id'))
        if rid is None:
            continue
        status = str(record.get('status') or '')
        route_old = start_routes.get(rid)
        route_new = conv_routes.get(rid)
        row_old = start_rows.get(rid)
        row_new = conv_rows.get(rid)
        bx_old, kind_old, error_old = _canonical_lateral(row_old, route_old)
        bx_new, kind_new, error_new = _canonical_lateral(row_new, route_new)
        bx_geom_old, geom_error_old = _body_lateral_from_geometry(row_old,
                                                                  route_old)
        bx_geom_new, geom_error_new = _body_lateral_from_geometry(row_new,
                                                                  route_new)
        if bx_old is None and status == 'converted':
            warnings.append(dict(route_id=rid, kind='canonical_bx_old',
                                 detail=error_old))
        if bx_new is None and status == 'converted':
            warnings.append(dict(route_id=rid, kind='canonical_bx_new',
                                 detail=error_new))
        bx_primary = bx_old if bx_old is not None else bx_new
        delta_commit = as_int(record.get('delta'))
        before = start_per_route.get(rid, 0 if start_per_route else None)
        after = conv_per_route.get(rid, 0 if conv_per_route else None)
        length_old = as_float((route_old or {}).get('length_mm'))
        length_new = as_float((route_new or {}).get('length_mm'))
        old_layer = as_int(record.get('old_layer'))
        new_layer = as_int(record.get('layer'))
        old_z = as_float(record.get('old_z_mm'))
        new_z = as_float(record.get('z_mm'))
        row = dict(
            route_id=rid,
            status=status,
            family=str(record.get('family') or ''),
            chosen_kind=str(record.get('kind') or ''),
            frame_kind_old=kind_old,
            frame_kind_new=kind_new,
            old_layer=old_layer,
            new_layer=new_layer,
            old_z_mm=old_z,
            new_z_mm=new_z,
            same_layer=bool(old_layer is not None and new_layer is not None
                            and old_layer == new_layer),
            old_multi_arc_regions=as_int(record.get('old_regions')),
            new_multi_arc_regions=as_int(record.get('new_regions')),
            bx_mm=(round(float(bx_primary), 9)
                   if bx_primary is not None else None),
            bx_old_mm=(round(float(bx_old), 9)
                       if bx_old is not None else None),
            bx_new_mm=(round(float(bx_new), 9)
                       if bx_new is not None else None),
            bx_geometry_old_mm=(round(float(bx_geom_old), 9)
                                if bx_geom_old is not None else None),
            bx_geometry_new_mm=(round(float(bx_geom_new), 9)
                                if bx_geom_new is not None else None),
            bx_geometry_consistency_mm=(
                round(abs(float(bx_geom_old) - float(bx_old)), 9)
                if bx_geom_old is not None and bx_old is not None else None),
            bx_old_new_consistency_mm=(
                round(abs(float(bx_old) - float(bx_new)), 9)
                if bx_old is not None and bx_new is not None else None),
            below_2R=(None if bx_primary is None
                      else bool(float(bx_primary) < TWO_R_MM - 1e-9)),
            delta_commit=delta_commit,
            total_after=as_int(record.get('total_after')),
            per_route_events_before=before,
            per_route_events_after=after,
            per_route_events_diff=(None if before is None or after is None
                                   else int(after) - int(before)),
            length_before_mm=length_old,
            length_after_mm=length_new,
            length_delta_mm=(None if length_old is None or length_new is None
                             else round(length_new - length_old, 6)),
            seconds=as_float(record.get('seconds')),
            old_geometry_error=geom_error_old,
            new_geometry_error=geom_error_new)
        rows.append(row)
    return rows, warnings


def cmd_offset_2r(args, started_at, began):
    report_path = require_file(resolve_path(args.conversion_report),
                               'conversion report')
    report = read_json(report_path)
    if not isinstance(report, dict):
        raise DataError('not a JSON object: %s' % report_path)
    for key in ('start_dir', 'out_dir', 'records'):
        if key not in report:
            raise DataError('conversion_report.json has no %r field: %s'
                            % (key, report_path))
    start_dir = _report_path(report['start_dir'])
    conv_dir = _report_path(report['out_dir'])
    inputs_root = Path(args.out_dir) / '_inputs'
    start_state = analyze_state(start_dir, inputs_root,
                                label='stage0_start')
    conv_state = analyze_state(conv_dir, inputs_root, label='stage0_converted')
    converted_records = [record for record in report['records']
                         if str(record.get('status')) == 'converted']
    if not converted_records:
        raise DataError('conversion_report.json has no converted records yet')
    rows, warnings = _offset_rows(report, start_state, conv_state)
    converted_rows = [row for row in rows
                      if row['status'] == 'converted'
                      and row['bx_mm'] is not None]
    if not converted_rows:
        raise DataError('no converted record yielded a lateral offset; '
                        'cannot draw the 2R threshold figure')
    all_offsets = [row['bx_mm'] for row in converted_rows]
    all_set = set(all_offsets)
    if len(all_set) == 1:
        raise DataError('all %d converted routes share the same |bx| = %.6f mm; '
                        'a per-route scatter would be degenerate'
                        % (len(converted_rows), all_offsets[0]))
    below = [row for row in converted_rows if row['below_2R'] is True]
    above = [row for row in converted_rows if row['below_2R'] is False]
    bins = []
    for low, high, label in _bucket_defs():
        members = [row for row in converted_rows
                   if row['bx_mm'] is not None
                   and low - 1e-9 <= float(row['bx_mm']) < high - 1e-9]
        deltas = [row['delta_commit'] for row in members
                  if row['delta_commit'] is not None]
        bins.append(dict(low_mm=low, high_mm=(None if high == float('inf')
                                              else high), label=label,
                         routes=len(members),
                         mean_delta_commit=(round(statistics.fmean(deltas), 6)
                                            if deltas else None),
                         sum_delta_commit=(int(sum(deltas)) if deltas else 0),
                         mean_bx_mm=(round(statistics.fmean(
                             [row['bx_mm'] for row in members]), 6)
                             if members else None)))
    by_threshold = dict(
        below_2R=dict(routes=len(below),
                      **{key: value for key, value in _summarise(
                          [row['delta_commit'] for row in below]).items()
                         if key != 'sum'},
                      sum_delta_commit=int(sum(row['delta_commit']
                                               for row in below
                                               if row['delta_commit'] is not None)),
                      share_positive=(round(sum(1 for row in below
                                                if (row['delta_commit'] or 0) > 0)
                                            / len(below), 4) if below else None),
                      share_zero=(round(sum(1 for row in below
                                            if (row['delta_commit'] or 0) == 0)
                                       / len(below), 4) if below else None)),
        at_or_above_2R=dict(
            routes=len(above),
            **{key: value for key, value in _summarise(
                [row['delta_commit'] for row in above]).items()
               if key != 'sum'},
            sum_delta_commit=int(sum(row['delta_commit'] for row in above
                                     if row['delta_commit'] is not None)),
            share_positive=(round(sum(1 for row in above
                                      if (row['delta_commit'] or 0) > 0)
                                  / len(above), 4) if above else None),
            share_zero=(round(sum(1 for row in above
                                  if (row['delta_commit'] or 0) == 0)
                             / len(above), 4) if above else None)))
    commit_sum = int(sum(row['delta_commit'] for row in converted_rows
                         if row['delta_commit'] is not None))
    reported_delta = as_int(report.get('crossing_delta_from_start'))
    inconsistent_tasks = [row for row in converted_rows
                          if row['bx_old_new_consistency_mm'] not in (None, 0.0)]
    adjacent_direct = [row for row in inconsistent_tasks
                       if row['frame_kind_new'] == 'adjacent'
                       or row['frame_kind_old'] == 'adjacent']
    consistency = dict(
        converted_records=len(converted_records),
        records_with_bx=len(converted_rows),
        sum_commit_delta=commit_sum,
        reported_crossing_delta_from_start=reported_delta,
        commit_sum_matches_report=bool(reported_delta is not None
                                       and commit_sum == reported_delta),
        canonical_bx_old_new_max_diff=(round(max(
            [row['bx_old_new_consistency_mm'] for row in converted_rows
             if row['bx_old_new_consistency_mm'] is not None]), 9)
            if any(row['bx_old_new_consistency_mm'] is not None
                   for row in converted_rows) else None),
        geometry_check_max_diff=(round(max(
            [row['bx_geometry_consistency_mm'] for row in converted_rows
             if row['bx_geometry_consistency_mm'] is not None]), 9)
            if any(row['bx_geometry_consistency_mm'] is not None
                   for row in converted_rows) else None),
        start_crossings=as_int(report.get('start_crossings')),
        crossings_after=as_int(report.get('crossings_after')))
    # endpoint identity is checked independently on the two real states
    start_routes = _routes_by_id(start_state)
    conv_routes = _routes_by_id(conv_state)
    mismatch = [row['route_id'] for row in converted_rows
                if row['route_id'] not in start_routes
                or row['route_id'] not in conv_routes
                or str(start_routes[row['route_id']].get('source_endpoint'))
                != str(conv_routes[row['route_id']].get('source_endpoint'))
                or str(start_routes[row['route_id']].get('target_endpoint'))
                != str(conv_routes[row['route_id']].get('target_endpoint'))]
    consistency['same_endpoints'] = not mismatch
    consistency['endpoint_mismatch_route_ids'] = mismatch
    consistency['landing_task_changed_routes'] = len(inconsistent_tasks)
    consistency['landing_task_changed_route_ids'] = [
        row['route_id'] for row in inconsistent_tasks]
    consistency['landing_task_changed_families'] = sorted(
        {str(row['family']) for row in inconsistent_tasks})
    definitions = dict(
        bx_mm=('|bx| = |lateral component of the body landing-pose '
               'displacement (B - A)| in the frozen D56 canonical body frame. '
               'Recomputed from the real assignment_1024.csv + routes_l3d.json '
               'of the inherited state with route_builder.body_task (lifted '
               'body) or route_builder.direct_task (interface-direct body) and '
               'layer2d.canonical_frame; canonical_frame puts A at (0,0) '
               'heading +y, so bx is exactly the frame lateral coordinate of '
               'B.  For N/S ports it is |dx| between the two body landing '
               'points, for E/W ports |dy|.  The reported bx_mm / bx_old_mm is '
               'the inherited (pre-conversion) task; bx_new_mm is the same '
               'quantity of the converted state (reported for completeness).'),
        bx_old_new_note=(
            'bx_new_mm differs from bx_old_mm only for %d routes whose '
            'conversion turned a lifted adjacent-relation body into an '
            'interface-direct body: the direct task has no lead, so its '
            'landing poses (and therefore the canonical bx) change.  bx_old is '
            'the threshold quantity because it is the lateral offset the '
            'conversion had to re-express; the per-route difference is in '
            'bx_old_new_consistency_mm.' % len(adjacent_direct)),
        bx_geometry=('world-frame cross-check computed directly from the '
                     'stored body chain: v . (B - A) with u = source inward '
                     'direction, v = (-u_y, u_x); reported as '
                     'bx_geometry_old_mm / bx_geometry_new_mm.  It equals the '
                     'canonical |bx| on every route (max difference 0.0 mm in '
                     'this conversion), which validates the definition.'),
        below_2R=('a route is "below 2R" iff |bx| < 2R = %.3f mm '
                  '(R15 = %.3f mm, frozen)' % (TWO_R_MM, R15_MM)),
        delta_commit=('crossing change of the global total caused by replacing '
                      'that single route during the sequential Stage-0 '
                      'conversion (conversion_report.json records[].delta); '
                      'only converted routes change, so the sum over records '
                      'equals the global start->converted crossing delta'),
        per_route_events=('number of same-height crossing events the route '
                          'participates in, from the independent '
                          'crossing_stats.json of the start / converted '
                          'states; not additive over routes (a 0 means the '
                          'route has no crossing event in that state)'))
    target = Path(args.out_dir) / 'offset_2r'
    target.mkdir(parents=True, exist_ok=True)
    write_csv(target / 'offset_2r_per_route.csv', rows)
    payload = dict(
        schema='20h_ablation_offset_2r_v1', generated_at=now_local(),
        conversion_report=file_entry(report_path),
        policy=report.get('policy'), planner=report.get('planner'),
        start=dict(dir=rel(start_dir), crossings=as_int(
            report.get('start_crossings')),
            counts_source=start_state['counts_source']),
        converted=dict(dir=rel(conv_dir), crossings=as_int(
            report.get('crossings_after')),
            counts_source=conv_state['counts_source']),
        feasible=report.get('feasible'),
        multi_arc_routes_before=as_int(report.get('multi_arc_routes_before')),
        converted_count=as_int(report.get('converted')),
        residual=as_int(report.get('residual')),
        r15_mm=R15_MM, two_r_mm=TWO_R_MM,
        definitions=definitions,
        by_threshold=by_threshold, bins=bins,
        consistency=consistency,
        warnings=warnings,
        records=rows)
    write_json(target / 'offset_2r_summary.json', payload)

    # ---------------- figure: scatter + binned + 2R buckets ----------------
    fig = plt.figure(figsize=(16.8, 5.4))
    ax0 = fig.add_axes([0.045, 0.18, 0.285, 0.68])
    ax1 = fig.add_axes([0.385, 0.18, 0.285, 0.68])
    ax2 = fig.add_axes([0.725, 0.18, 0.25, 0.68])
    offsets = [float(row['bx_mm']) for row in converted_rows]
    deltas = [int(row['delta_commit'] or 0) for row in converted_rows]
    below_mask = [row['below_2R'] is True for row in converted_rows]
    ax0.scatter([offset for offset, flag in zip(offsets, below_mask) if flag],
                [delta for delta, flag in zip(deltas, below_mask) if flag],
                s=30, color=COLOR_A, alpha=0.82, edgecolors='white',
                linewidths=0.3, label='below 2R (n=%d)' % len(below))
    ax0.scatter([offset for offset, flag in zip(offsets, below_mask) if not flag],
                [delta for delta, flag in zip(deltas, below_mask) if not flag],
                s=30, color=COLOR_B, alpha=0.82, edgecolors='white',
                linewidths=0.3, label='at/above 2R (n=%d)' % len(above))
    ax0.axvline(TWO_R_MM, color='#333333', linestyle='--', linewidth=1.3)
    ax0.axhline(0.0, color='#777777', linewidth=0.7, alpha=0.7)
    ax0.text(TWO_R_MM + 0.8, max(deltas) if deltas else 1.0,
             '2R = %.0f mm' % TWO_R_MM, fontsize=8.2, color='#222222',
             va='top')
    ax0.set_xlabel('lateral offset |bx| of the inherited body task (mm)',
                   fontsize=8.2)
    ax0.set_ylabel('global crossing change of the conversion commit '
                   '(events)', fontsize=8.2)
    ax0.set_title('(a) Stage-0 conversion cost vs lateral offset\n'
                  '%d converted routes' % len(converted_rows), fontsize=9.2)
    ax0.grid(alpha=0.22)
    ax0.legend(fontsize=7.2, loc='lower right')
    labels = [item['label'] for item in bins]
    centers = [item['mean_bx_mm'] if item['mean_bx_mm'] is not None
               else (item['low_mm'] + 2.5) for item in bins]
    colors = [COLOR_A if center < TWO_R_MM else COLOR_B
              for center in centers]
    heights = [item['mean_delta_commit'] if item['mean_delta_commit'] is not None
               else 0.0 for item in bins]
    ax1.bar(centers, heights, width=3.9, color=colors, edgecolor='white',
            linewidth=0.5, alpha=0.9)
    for center, height, item in zip(centers, heights, bins):
        if item['routes']:
            ax1.text(center, height, 'n=%d' % item['routes'], ha='center',
                     va='bottom' if height >= 0 else 'top', fontsize=6.0)
    ax1.axvline(TWO_R_MM, color='#333333', linestyle='--', linewidth=1.3)
    ax1.axhline(0.0, color='#777777', linewidth=0.7, alpha=0.7)
    ax1.set_xlabel('lateral offset bin (mm)', fontsize=8.2)
    ax1.set_ylabel('mean crossing change per converted route (events)',
                   fontsize=8.2)
    ax1.set_title('(b) mean conversion cost per |bx| bin', fontsize=9.2)
    ax1.grid(axis='y', alpha=0.22)
    bucket_labels = ['below 2R\n(<%.0f mm)' % TWO_R_MM,
                     'at/above 2R\n(>=%.0f mm)' % TWO_R_MM]
    bucket_values = [by_threshold['below_2R']['sum_delta_commit'],
                     by_threshold['at_or_above_2R']['sum_delta_commit']]
    bucket_counts = [by_threshold['below_2R']['routes'],
                     by_threshold['at_or_above_2R']['routes']]
    bars = ax2.bar(bucket_labels, bucket_values, color=[COLOR_A, COLOR_B],
                   edgecolor='white', linewidth=0.6, width=0.6)
    for bar, value, count in zip(bars, bucket_values, bucket_counts):
        ax2.text(bar.get_x() + bar.get_width() / 2.0, value,
                 'sum %+d\nn=%d' % (value, count), ha='center',
                 va='bottom' if value >= 0 else 'top', fontsize=7.4)
    ax2.axhline(0.0, color='#777777', linewidth=0.7, alpha=0.7)
    ax2.set_ylabel('total global crossing change (events)', fontsize=8.2)
    ax2.set_title('(c) conversion cost by 2R bucket', fontsize=9.2)
    ax2.grid(axis='y', alpha=0.22)
    fig.suptitle(
        'Stage-0 multi-arc conversion: lateral offset |bx| vs the 2R = %.0f mm '
        'threshold (R15 = %.0f mm, %d converted routes, global delta %+d '
        'crossings)'
        % (TWO_R_MM, R15_MM, len(converted_rows),
           (reported_delta if reported_delta is not None else commit_sum)),
        fontsize=10.6, y=0.975)
    fig.text(0.5, 0.012,
             '|bx|: lateral component of the body landing-pose displacement '
             'in the frozen D56 canonical frame, recomputed from the real '
             'assignment_1024.csv + routes_l3d.json (route_builder.body_task / '
             'direct_task + layer2d.canonical_frame); for N/S ports |bx| = |dx| '
             'of the two body landing points, for E/W ports |dy|; "below 2R" '
             'iff |bx| < %.3f mm.  delta = per-route global crossing change of '
             'the sequential conversion (records[].delta; sum over records = '
             'global start->converted delta: %s).  World-frame geometry check '
             'max |bx_geometry - bx| = %s mm.'
             % (TWO_R_MM, consistency['commit_sum_matches_report'],
                consistency['geometry_check_max_diff']),
             ha='center', fontsize=6.1, color='#333333')
    outputs = save_figure(fig, target, 'offset_2r_threshold', args.dpi,
                          not args.no_svg, pad=0.10)
    outputs += collect_outputs(target, '*.csv', recursive=False)
    outputs += collect_outputs(target, 'offset_2r_summary.json',
                               recursive=False)
    notes = dict(
        definitions=definitions,
        consistency=consistency,
        converted_routes=len(converted_rows),
        below_2R=len(below), at_or_above_2R=len(above),
        two_r_mm=TWO_R_MM, r15_mm=R15_MM,
        conversion_report=file_entry(report_path),
        start_state=state_notes(start_state),
        converted_state=state_notes(conv_state),
        dpi=int(args.dpi),
        formats=(['png', 'svg'] if not args.no_svg else ['png']),
        waits_for=('if the Stage-0 conversion is still running, wait until '
                   'conversion_report.json contains all records and out_dir '
                   'holds the converted routes_l3d.json/crossing_stats.json'))
    record_manifest(args.out_dir, 'offset-2r',
                    [SCRIPT_REL, 'offset-2r', '--conversion-report',
                     args.conversion_report, '--out-dir', str(args.out_dir)],
                    state_sources(start_state, [report_path])
                    + state_sources(conv_state), outputs, notes, started_at,
                    time.time() - began)
    write_readme(args.out_dir)
    print('[offset-2r] %d converted routes (%d below 2R) -> %s'
          % (len(converted_rows), len(below), target), flush=True)
    return 0


# ===========================================================================
# 7. curves -- search progress vs the three counted budget axes
# ===========================================================================
def _short_label(path):
    parts = [sanitize(part, 28) for part in Path(path).parts[-2:]]
    return sanitize('_'.join(parts), 56)


def _read_json_any(paths):
    for path in paths:
        payload = read_json(Path(path))
        if isinstance(payload, dict):
            return payload, Path(path)
    return {}, None


def _load_run_history(run_dir, label=None):
    """Extract one run's search-progress records from its real artifacts."""
    state_dir, artifact_root = resolve_state_dir(run_dir)
    search = _search_dirs(state_dir, artifact_root)
    label = label or _short_label(artifact_root)
    stats_payload, stats_path = _read_json_any(
        [Path(base) / name for base in search
         for name in ('strategy_stats.json', 'strategy_stats_partial.json')])
    extra = stats_payload.get('extra') or {}
    history = None
    source = ''
    top_history = stats_payload.get('history_records')
    extra_history = extra.get('history_records')
    if isinstance(top_history, list) and top_history:
        history = top_history
        source = 'strategy_stats.json:history_records'
    elif isinstance(extra_history, list) and extra_history:
        history = extra_history
        source = 'strategy_stats.json:extra.history_records'
    records = []
    if history:
        for item in history:
            records.append(dict(
                record_index=len(records) + 1,
                d56=as_int(item.get('d56')),
                r3d=as_int(item.get('r3d')),
                wall_seconds=as_float(item.get('wall')),
                total=as_int(item.get('total')),
                best_total=(as_int(item.get('best_total'))
                            if item.get('best_total') is not None
                            else as_int(item.get('total'))),
                accepted=bool(item.get('accepted')),
                gain=as_int(item.get('gain')),
                operator=str(item.get('operator') or ''),
                stage=as_int(item.get('stage'))))
    summary, summary_path = _read_json_any(
        [Path(base) / 'summary.json' for base in search])
    summary_g4, summary_g4_path = _read_json_any(
        [Path(base) / 'summary_g4.json' for base in search])
    start_crossings = (as_int(summary.get('start_crossings'))
                       or as_int(summary_g4.get('start_crossings'))
                       or as_int(extra.get('start_crossings')))
    final_crossings = (as_int(extra.get('final_crossings'))
                       or as_int(summary_g4.get('final_crossings'))
                       or as_int(summary.get('final_crossings')))
    if not records:
        history_csv = None
        for base in search:
            candidate = Path(base) / 'optimization_history.csv'
            if candidate.is_file():
                history_csv = candidate
                break
        if history_csv is not None:
            source = 'optimization_history.csv (per accepted transaction)'
            for item in read_csv_rows(history_csv):
                total = as_int(item.get('total_after'))
                wall = as_float(item.get('wall_seconds'))
                if total is None:
                    continue
                records.append(dict(
                    record_index=len(records) + 1, d56=None, r3d=None,
                    wall_seconds=wall, total=total, best_total=None,
                    accepted=True, gain=as_int(item.get('gain')),
                    operator=str(item.get('family') or ''),
                    stage=as_int(item.get('round_index'))))
            for item in records:
                item['best_total'] = item['total']
    if not records:
        rounds = stats_payload.get('rounds')
        if isinstance(rounds, list) and rounds:
            source = 'strategy_stats.json:rounds (per search round)'
            cumulative = 0.0
            for item in rounds:
                seconds = as_float(item.get('seconds')) or 0.0
                cumulative += seconds
                total = as_int(item.get('total_after'))
                if total is None:
                    continue
                records.append(dict(
                    record_index=len(records) + 1, d56=None, r3d=None,
                    wall_seconds=round(cumulative, 3), total=total,
                    best_total=None, accepted=True,
                    gain=as_int(item.get('gain')),
                    operator=str(item.get('label') or ''),
                    stage=None))
            for item in records:
                item['best_total'] = item['total']
    if not records:
        raise DataError(
            'run %s has no search-progress records: neither '
            'strategy_stats.json (history_records / rounds) nor '
            'optimization_history.csv exists' % artifact_root)
    # running best-so-far curve (monotone in the crossing total)
    best = start_crossings if start_crossings is not None else records[0]['total']
    for item in records:
        if item['total'] is not None:
            best = min(best, item['total'])
        item['running_best'] = best
    if start_crossings is not None:
        records.insert(0, dict(
            record_index=0,
            d56=(0 if records[0].get('d56') is not None else None),
            r3d=(0 if records[0].get('r3d') is not None else None),
            wall_seconds=0.0, total=start_crossings,
            best_total=start_crossings, running_best=start_crossings,
            accepted=False, gain=0, operator='start', stage=None))
        for index, item in enumerate(records):
            item['record_index'] = index
    ledger, ledger_path = _read_json_any(
        [Path(base) / 'budget_ledger.json' for base in search])
    return dict(
        label=label, run_dir=rel(artifact_root), state_dir=rel(state_dir),
        source=source, records=records,
        start_crossings=start_crossings, final_crossings=final_crossings,
        strategy_stats_path=(rel(stats_path) if stats_path else None),
        strategy_stats_sha256=(sha256_file(stats_path) if stats_path else None),
        summary_path=(rel(summary_path) if summary_path else None),
        summary_sha256=(sha256_file(summary_path) if summary_path else None),
        ledger=dict(rel_path=rel(ledger_path) if ledger_path else None,
                    data={key: ledger.get(key) for key in
                          ('d56_candidate_evals', 'route_3d_checks',
                           'wall_seconds', 'transactions')
                          if key in ledger}),
        counts_source=None)


def cmd_curves(args, started_at, began):
    specs = []
    for item in args.state or []:
        name, sep, path = str(item).partition('=')
        if not sep or not path.strip():
            raise DataError('--state expects name=dir, got %r' % item)
        specs.append((name.strip(), path.strip()))
    for path in args.run_dir or []:
        specs.append((None, path))
    if not specs:
        raise DataError('at least one --run-dir or --state is required')
    runs, failures = [], []
    for name, path in specs:
        try:
            runs.append(_load_run_history(path, label=name))
        except DataError as error:
            failures.append(dict(run=rel(resolve_path(path)
                                         if not Path(path).is_absolute()
                                         else path), error=str(error)))
    if not runs:
        raise DataError('no run yielded search-progress records: %s'
                        % json.dumps(failures, ensure_ascii=False))
    target = Path(args.out_dir) / 'curves'
    target.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(16.8, 5.3))
    axes = [fig.add_axes([0.045, 0.17, 0.285, 0.70]),
            fig.add_axes([0.385, 0.17, 0.285, 0.70]),
            fig.add_axes([0.725, 0.17, 0.25, 0.70])]
    axis_defs = (('d56', 'd56 candidate evaluations',
                  'crossings vs d56 candidate evaluations'),
                 ('r3d', 'route 3-D checks',
                  'crossings vs route 3-D checks'),
                 ('wall_seconds', 'wall seconds',
                  'crossings vs wall-clock seconds'))
    panel_has_data = [False, False, False]
    csv_rows = []
    for run_index, run in enumerate(runs):
        color = STATE_COLORS[run_index % len(STATE_COLORS)]
        records = [item for item in run['records']
                   if item.get('running_best') is not None]
        for axis_index, (key, xlabel, title) in enumerate(axis_defs):
            points = [(item[key], item['running_best']) for item in records
                      if item.get(key) is not None]
            points.sort(key=lambda pair: float(pair[0]))
            if not points:
                continue
            panel_has_data[axis_index] = True
            xs = [float(pair[0]) for pair in points]
            ys = [float(pair[1]) for pair in points]
            axes[axis_index].plot(xs, ys, '-', color=color, linewidth=1.5,
                                  label='%s [%s]'
                                  % (run['label'], run['source'].split(' (')[0]))
            raw_points = [(item[key], item['total']) for item in records
                          if item.get(key) is not None
                          and item.get('total') is not None]
            if raw_points and len(raw_points) > 2:
                boundaries = sorted({float(x) for x, _ in raw_points})
                if len(boundaries) <= 4000:
                    axes[axis_index].scatter(
                        [float(x) for x, _ in raw_points],
                        [float(y) for _, y in raw_points], s=2.0, color=color,
                        alpha=0.20, linewidths=0)
            if run['final_crossings'] is not None:
                axes[axis_index].axhline(
                    float(run['final_crossings']), color=color, linewidth=0.7,
                    linestyle=':', alpha=0.65)
        for item in run['records']:
            csv_rows.append(dict(run=run['label'], run_dir=run['run_dir'],
                                 source=run['source'],
                                 record_index=item['record_index'],
                                 d56=item.get('d56'), r3d=item.get('r3d'),
                                 wall_seconds=item.get('wall_seconds'),
                                 total=item.get('total'),
                                 running_best=item.get('running_best'),
                                 accepted=item.get('accepted'),
                                 gain=item.get('gain'),
                                 operator=item.get('operator'),
                                 stage=item.get('stage')))
    for axis_index, (key, xlabel, title) in enumerate(axis_defs):
        ax = axes[axis_index]
        ax.set_xlabel(xlabel, fontsize=8.4)
        ax.set_ylabel('same-height crossing events (best so far)', fontsize=8.4)
        ax.set_title('(%s) %s' % ('abc'[axis_index], title), fontsize=9.2)
        ax.grid(alpha=0.22)
        if panel_has_data[axis_index]:
            ax.legend(fontsize=5.9, loc='upper right')
        else:
            ax.text(0.5, 0.5,
                    'no run provides per-attempt %s records\n(sources: %s)'
                    % (xlabel, ', '.join(sorted({run['source']
                                                 for run in runs}))),
                    transform=ax.transAxes, ha='center', va='center',
                    fontsize=7.6, color='#666666', wrap=True)
    fig.suptitle(
        'Search progress: crossing total vs the three counted budget axes '
        '(20-height G4 multi-arc ablation)\nsolid = best-so-far crossings, '
        'faint dots = current total per accepted attempt, dotted line = final '
        'crossings', fontsize=10.4, y=0.975)
    fig.text(0.5, 0.012,
             'sources: %s   -   d56/route-3D/wall counters are the cumulative '
             'ledger counters recorded per attempt; runs without a per-attempt '
             'history are drawn from optimization_history.csv or per-round '
             'strategy_stats only (stated in the legend)'
             % '; '.join('%s: %s' % (run['label'], run['source'])
                         for run in runs),
             ha='center', fontsize=6.0, color='#333333')
    outputs = save_figure(fig, target, 'search_curves', args.dpi,
                          not args.no_svg, pad=0.10)
    write_csv(target / 'search_curves.csv', csv_rows)
    payload = dict(
        schema='20h_ablation_search_curves_v1', generated_at=now_local(),
        runs=[dict(label=run['label'], run_dir=run['run_dir'],
                   source=run['source'],
                   strategy_stats=run['strategy_stats_path'],
                   strategy_stats_sha256=run['strategy_stats_sha256'],
                   summary=run['summary_path'],
                   summary_sha256=run['summary_sha256'],
                   start_crossings=run['start_crossings'],
                   final_crossings=run['final_crossings'],
                   n_records=len(run['records']),
                   ledger=run['ledger']) for run in runs],
        failures=failures,
        axes=[dict(key=key, xlabel=xlabel, title=title,
                   has_data=panel_has_data[index])
              for index, (key, xlabel, title) in enumerate(axis_defs)],
        note='one figure, three sub-plots; several runs overlaid; only real '
             'recorded counters are plotted')
    write_json(target / 'search_curves.json', payload)
    outputs += collect_outputs(target, 'search_curves.csv', recursive=False)
    outputs += collect_outputs(target, 'search_curves.json', recursive=False)
    sources = []
    for run in runs:
        for base in _search_dirs(resolve_path(run['run_dir']),
                                 resolve_path(run['run_dir'])):
            for name in ('strategy_stats.json', 'strategy_stats_partial.json',
                         'optimization_history.csv', 'summary.json',
                         'summary_g4.json', 'budget_ledger.json'):
                path = Path(base) / name
                if path.is_file():
                    sources.append(file_entry(path, role='run:%s' % name))
    record_manifest(args.out_dir, 'curves',
                    [SCRIPT_REL, 'curves', '--out-dir', str(args.out_dir)]
                    + sum((['--run-dir', path] for path in args.run_dir or []),
                          [])
                    + sum((['--state', item] for item in args.state or []), []),
                    sources, outputs,
                    dict(runs=[run['label'] for run in runs],
                         sources=[run['source'] for run in runs],
                         failures=failures, dpi=int(args.dpi),
                         formats=(['png', 'svg'] if not args.no_svg
                                  else ['png'])),
                    started_at, time.time() - began)
    write_readme(args.out_dir)
    print('[curves] %d run(s) -> %s' % (len(runs), target), flush=True)
    return 0


# ===========================================================================
# 8. seed-summary -- three-seed ON/OFF paired statistics
# ===========================================================================
RUN_NAME_RE = re.compile(r'(?P<kind>[ca]1)_(?P<arm>on|off)_(?P<seed>\d{6,8})')


def _expand_globs(patterns):
    import glob as _glob
    paths = []
    for pattern in patterns:
        text = str(pattern)
        absolute = text if os.path.isabs(text) else str(PROJECT_ROOT / text)
        matches = sorted(_glob.glob(absolute))
        if not matches and Path(text).is_dir():
            matches = [str(Path(text))]
        for match in matches:
            path = Path(match)
            if path.is_dir() and path not in paths:
                paths.append(path)
    return paths


def _run_identity(directory):
    match = RUN_NAME_RE.search(Path(directory).name)
    if match:
        return dict(kind=('c1' if match.group('kind') == 'c1' else 'a1'),
                    prefix=match.group('kind'),
                    arm=match.group('arm'), seed=int(match.group('seed')))
    meta = read_json(Path(directory) / 'run_meta.json', default={}) or {}
    arm = str(meta.get('arm') or '')
    seed = as_int(meta.get('seed'))
    if arm in ('on', 'off') and seed is not None:
        return dict(kind='c1', prefix='c1', arm=arm, seed=seed)
    return None


def _run_metrics(directory):
    """Read every real metric of one arm run (audit first, then summaries)."""
    directory = Path(directory)
    state_dir = directory
    artifact_root = directory
    if not (directory / 'routes_l3d.json').is_file() and \
            (directory / 'best_valid' / 'routes_l3d.json').is_file():
        state_dir = directory / 'best_valid'
    search = _search_dirs(state_dir, artifact_root)
    audit, audit_path = _read_json_any([Path(base) / 'audit_state.json'
                                        for base in search])
    summary, summary_path = _read_json_any([Path(base) / 'summary.json'
                                            for base in search])
    summary_g4, summary_g4_path = _read_json_any(
        [Path(base) / 'summary_g4.json' for base in search])
    validation, validation_path = _read_json_any(
        [Path(base) / 'validation_final' / 'validation.json'
         for base in search]
        + [Path(base) / 'validation.json' for base in search])
    verdict, verdict_path = _read_json_any([Path(base) / 'RUN_VERDICT.json'
                                            for base in search])
    ledger, ledger_path = _read_json_any([Path(base) / 'budget_ledger.json'
                                          for base in search])
    strategy, strategy_path = _read_json_any([Path(base) / 'strategy_stats.json'
                                              for base in search])
    meta, meta_path = _read_json_any([Path(base) / 'run_meta.json'
                                      for base in search])
    crossing_stats, crossing_stats_path = _read_json_any(
        [Path(base) / 'crossing_stats.json' for base in search])
    totals = crossing_stats.get('totals') or {}
    counts = validation.get('counts') or {}
    extra = strategy.get('extra') or {}

    def first(*values):
        for value in values:
            if value is not None:
                return value
        return None

    final_crossings = first(totals.get('crossings'), audit.get('crossings'),
                            summary.get('crossings'),
                            summary.get('final_crossings'),
                            summary_g4.get('final_crossings'),
                            counts.get('same_plane_crossings'))
    crossing_pairs = first(totals.get('crossing_pairs'),
                           audit.get('crossing_pairs'),
                           summary.get('crossing_pairs'),
                           summary_g4.get('crossing_pairs'),
                           counts.get('same_plane_crossing_pairs'))
    max_route = first(totals.get('max_route_crossings'),
                      audit.get('max_route_crossings'),
                      summary.get('max_route_crossings'),
                      summary_g4.get('max_route_crossings'),
                      (counts.get('per_route_crossing_distribution') or {}
                       ).get('max'))
    start_crossings = first(meta.get('start_crossings'),
                            summary.get('start_crossings'),
                            summary_g4.get('start_crossings'),
                            extra.get('start_crossings'),
                            (strategy.get('extra') or {}).get('start_crossings'))
    total_length = first(audit.get('total_length_mm'),
                         summary.get('total_length_mm'),
                         summary_g4.get('total_length_mm'),
                         counts.get('total_length_mm'))
    multi_arc = audit.get('multi_arc') or {}
    ledger_data = ledger or (summary_g4.get('ledger') or {})
    return dict(
        run_dir=rel(artifact_root),
        state_dir=rel(state_dir),
        final_crossings=as_int(final_crossings),
        crossing_pairs=as_int(crossing_pairs),
        max_route_crossings=as_int(max_route),
        start_crossings=as_int(start_crossings),
        delta_vs_start=(as_int(final_crossings) - as_int(start_crossings)
                        if final_crossings is not None
                        and start_crossings is not None else None),
        routes_with_crossings=as_int(first(
            totals.get('routes_with_crossings'),
            audit.get('routes_with_crossings'),
            summary.get('routes_with_crossings'),
            (counts.get('per_route_crossing_distribution') or {}
             ).get('routes_with_crossings'))),
        total_length_mm=as_float(total_length),
        multi_arc_routes=as_int(first(
            (multi_arc.get('routes_with_multi_arc')),
            summary.get('multi_arc_routes'))),
        multi_arc_regions=as_int(first(
            multi_arc.get('total_regions'), summary.get('multi_arc_regions'))),
        d56_candidate_evals=as_int(first(ledger_data.get('d56_candidate_evals'),
                                         (extra.get('counted_budget') or {}
                                          ).get('d56_used'))),
        route_3d_checks=as_int(ledger_data.get('route_3d_checks')),
        wall_seconds=as_float(ledger_data.get('wall_seconds')),
        validator_pass=validation.get('validation_pass'),
        violation_count=as_int(validation.get('violation_count')),
        model_plane_count=as_int((validation.get('model') or {}
                                  ).get('plane_count')),
        all_gates_pass=(verdict.get('all_gates_pass')
                        if verdict else None),
        files_used=[rel(path) for path in
                    (audit_path, summary_path, summary_g4_path,
                     validation_path, verdict_path, ledger_path,
                     strategy_path, meta_path, crossing_stats_path)
                    if path is not None],
        routes_sha256=(audit.get('routes_sha256')
                       or meta.get('start_routes_sha256')))


def _describe_values(values):
    values = [float(value) for value in values if value is not None]
    n = len(values)
    if n == 0:
        return dict(n=0, mean=None, std_ddof1=None, min=None, max=None)
    return dict(n=n, mean=round(statistics.fmean(values), 6),
                std_ddof1=(round(statistics.stdev(values), 6)
                           if n >= 2 else None),
                min=min(values), max=max(values))


def cmd_seed_summary(args, started_at, began):
    patterns = args.runs_glob or [
        'experiments/20H_G4_MULTI_ARC_ABLATION_FINAL_1024/runs/*/c1_*']
    directories = _expand_globs(patterns)
    if not directories:
        raise DataError('no run directory matches %s (the three-seed runs have '
                        'not been produced yet)' % patterns)
    runs, skipped = [], []
    for directory in directories:
        directory = Path(directory)
        has_state = ((directory / 'routes_l3d.json').is_file()
                     or (directory / 'best_valid' / 'routes_l3d.json').is_file()
                     or (directory / 'run_meta.json').is_file()
                     or (directory / 'audit_state.json').is_file())
        if not has_state:
            skipped.append(dict(dir=rel(directory),
                                reason='no arm artifacts yet (still starting / '
                                       'queued)'))
            continue
        identity = _run_identity(directory)
        if identity is None:
            skipped.append(dict(dir=rel(directory),
                                reason='directory name/run_meta does not '
                                       'encode arm+seed'))
            continue
        metrics = _run_metrics(directory)
        record = dict(identity)
        record.update(metrics)
        if record['final_crossings'] is None:
            skipped.append(dict(dir=rel(directory),
                                reason='no crossing count in audit_state.json / '
                                       'summary.json / summary_g4.json / '
                                       'validation_final'))
            continue
        runs.append(record)
    if not runs:
        raise DataError('run directories exist but none yielded a crossing '
                        'count; checked: %s'
                        % json.dumps(skipped, ensure_ascii=False))
    kinds = sorted({run['kind'] for run in runs})
    stats_rows, pair_rows, aggregate = [], [], OrderedDict()
    for kind in kinds:
        kind_runs = [run for run in runs if run['kind'] == kind]
        seeds = sorted({run['seed'] for run in kind_runs})
        arms = sorted({run['arm'] for run in kind_runs})
        aggregate[kind] = OrderedDict()
        for arm in arms:
            arm_runs = sorted([run for run in kind_runs if run['arm'] == arm],
                              key=lambda run: run['seed'])
            values = [run['final_crossings'] for run in arm_runs]
            description = _describe_values(values)
            stats_rows.append(dict(
                kind=kind, arm=arm, metric='final_crossings',
                seeds=' '.join(str(run['seed']) for run in arm_runs),
                **description))
            for metric in ('crossing_pairs', 'max_route_crossings',
                           'routes_with_crossings', 'total_length_mm',
                           'multi_arc_regions', 'multi_arc_routes'):
                stats_rows.append(dict(
                    kind=kind, arm=arm, metric=metric,
                    seeds=' '.join(str(run['seed']) for run in arm_runs),
                    **_describe_values([run[metric] for run in arm_runs])))
            aggregate[kind][arm] = dict(routes=arm_runs,
                                        stats=description)
        if set(arms) == {'on', 'off'}:
            by_seed = defaultdict(dict)
            for run in kind_runs:
                by_seed[run['seed']][run['arm']] = run
            diffs = []
            for seed in seeds:
                pair = by_seed.get(seed) or {}
                if 'on' not in pair or 'off' not in pair:
                    continue
                on_value = pair['on']['final_crossings']
                off_value = pair['off']['final_crossings']
                diff = off_value - on_value
                diffs.append(diff)
                pair_rows.append(dict(
                    kind=kind, seed=seed,
                    on_crossings=on_value, off_crossings=off_value,
                    diff_off_minus_on=diff,
                    on_pairs=pair['on']['crossing_pairs'],
                    off_pairs=pair['off']['crossing_pairs'],
                    on_validator_pass=pair['on']['validator_pass'],
                    off_validator_pass=pair['off']['validator_pass'],
                    on_all_gates_pass=pair['on']['all_gates_pass'],
                    off_all_gates_pass=pair['off']['all_gates_pass'],
                    on_max_route=pair['on']['max_route_crossings'],
                    off_max_route=pair['off']['max_route_crossings']))
            stats_rows.append(dict(kind=kind, arm='paired(off-on)',
                                   metric='final_crossings',
                                   seeds=' '.join(str(seed) for seed in seeds),
                                   **_describe_values(diffs)))
            aggregate[kind]['paired'] = dict(stats=_describe_values(diffs),
                                             values=diffs, seeds=seeds)
    target = Path(args.out_dir) / 'seed_summary'
    target.mkdir(parents=True, exist_ok=True)
    write_csv(target / 'seed_summary_runs.csv', runs)
    write_csv(target / 'seed_summary_stats.csv', stats_rows)
    if pair_rows:
        write_csv(target / 'seed_summary_pairs.csv', pair_rows)
    payload = dict(
        schema='20h_ablation_seed_summary_v1', generated_at=now_local(),
        runs_glob=patterns, run_dirs=[run['run_dir'] for run in runs],
        statistics=dict(mean='arithmetic mean',
                        std_ddof1='sample standard deviation over seeds '
                                  '(ddof=1; null when fewer than 2 seeds)',
                        paired_difference='diff = OFF crossings - ON crossings '
                                          '(negative = ON has fewer crossings, '
                                          'i.e. multi-arc ON is better)',
                        box_plot='box = median/quartiles over seeds, points = '
                                 'individual seeds'),
        runs=runs, stats=stats_rows, pairs=pair_rows,
        aggregate={kind: dict(arms={arm: dict(
            n=value['stats']['n'], mean=value['stats']['mean'],
            std_ddof1=value['stats']['std_ddof1'],
            min=value['stats']['min'], max=value['stats']['max'])
            for arm, value in kind_values.items() if arm != 'paired'},
            paired=kind_values.get('paired'))
            for kind, kind_values in aggregate.items()},
        skipped=skipped)
    write_json(target / 'seed_summary.json', payload)

    fig = plt.figure(figsize=(13.8, 5.6))
    ax_box = fig.add_axes([0.065, 0.16, 0.36, 0.70])
    ax_pair = fig.add_axes([0.50, 0.16, 0.47, 0.70])
    positions, labels, colors = [], [], []
    box_data = []
    position = 1
    tick_positions = []
    for kind_index, kind in enumerate(kinds):
        kind_runs = [run for run in runs if run['kind'] == kind]
        for arm in ('on', 'off'):
            arm_runs = [run for run in kind_runs if run['arm'] == arm]
            if not arm_runs:
                continue
            box_data.append([run['final_crossings'] for run in arm_runs])
            positions.append(position)
            labels.append('%s\n%s' % (kind, arm))
            colors.append(COLOR_A if arm == 'on' else COLOR_B)
            tick_positions.append(position)
            position += 1
        position += 0.6
    boxplot = ax_box.boxplot(box_data, positions=positions, widths=0.52,
                             patch_artist=True, showfliers=False,
                             medianprops=dict(color='#222222', lw=1.2))
    for patch, color in zip(boxplot['boxes'], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.32)
        patch.set_edgecolor(color)
    for position_value, values, color in zip(positions, box_data, colors):
        jitter = np.linspace(-0.13, 0.13, len(values)) if len(values) > 1 \
            else np.zeros(1)
        ax_box.scatter(np.asarray([position_value] * len(values)) + jitter,
                       values, s=42, color=color, edgecolors='white',
                       linewidths=0.6, zorder=4)
        ax_box.annotate('%d' % int(statistics.fmean(values)),
                        xy=(position_value, statistics.fmean(values)),
                        xytext=(0, 8), textcoords='offset points',
                        ha='center', fontsize=7.0, color=color)
    if tick_positions:
        ax_box.set_xticks(tick_positions)
        ax_box.set_xticklabels(labels, fontsize=8.0)
    ax_box.set_ylabel('final same-height crossing events', fontsize=8.6)
    ax_box.set_title('(a) final crossings by arm (box over seeds + points)',
                     fontsize=9.4)
    ax_box.grid(axis='y', alpha=0.22)
    if pair_rows:
        for kind_index, kind in enumerate(sorted({row['kind']
                                                  for row in pair_rows})):
            kind_rows = [row for row in pair_rows if row['kind'] == kind]
            xs = [row['seed'] for row in kind_rows]
            xs_positions = np.arange(len(xs)) + kind_index * (len(xs) + 0.8)
            values = [row['diff_off_minus_on'] for row in kind_rows]
            ax_pair.bar(xs_positions, values, width=0.62,
                        color=['#c62828' if value > 0 else '#1565c0'
                               for value in values],
                        edgecolor='white', linewidth=0.5)
            for x_value, value in zip(xs_positions, values):
                ax_pair.text(x_value, value, '%+d' % value, ha='center',
                             va='bottom' if value >= 0 else 'top',
                             fontsize=7.4)
            ax_pair.set_xticks(list(xs_positions))
            ax_pair.set_xticklabels(['%s\n%d' % (kind, seed)
                                     for seed in xs], fontsize=7.6)
        ax_pair.axhline(0.0, color='#333333', linewidth=0.9)
        ax_pair.set_ylabel('paired difference  OFF - ON  (events)', fontsize=8.6)
        ax_pair.set_title('(b) three-seed paired difference (negative = ON '
                          'better)', fontsize=9.4)
        ax_pair.grid(axis='y', alpha=0.22)
    else:
        ax_pair.text(0.5, 0.5, 'ON/OFF pairs incomplete: a seed needs both arms '
                               'to form a paired difference',
                     transform=ax_pair.transAxes, ha='center', va='center',
                     fontsize=8.4, color='#666666')
    fig.suptitle(
        'Three-seed ON/OFF paired summary (real run artifacts; sample std '
        'ddof=1)\n%s'
        % '   '.join('%s: ON mean %s vs OFF mean %s'
                     % (kind,
                        (aggregate[kind].get('on') or {}).get(
                            'stats', {}).get('mean'),
                        (aggregate[kind].get('off') or {}).get(
                            'stats', {}).get('mean'))
                     for kind in aggregate), fontsize=10.2, y=0.975)
    outputs = save_figure(fig, target, 'seed_summary', args.dpi,
                          not args.no_svg, pad=0.10)
    outputs += collect_outputs(target, '*.csv', recursive=False)
    outputs += collect_outputs(target, 'seed_summary.json', recursive=False)
    sources = []
    for run in runs:
        identity_dir = resolve_path(run['run_dir'])
        for base in _search_dirs(identity_dir, identity_dir):
            for name in ('audit_state.json', 'summary.json', 'summary_g4.json',
                         'RUN_VERDICT.json', 'budget_ledger.json',
                         'strategy_stats.json', 'run_meta.json',
                         'validation_final/validation.json'):
                path = Path(base) / name
                if path.is_file():
                    sources.append(file_entry(path, role='run:%s' % name))
    notes = dict(runs_glob=patterns, runs=[run['run_dir'] for run in runs],
                 skipped=skipped,
                 statistics=payload['statistics'], dpi=int(args.dpi),
                 formats=(['png', 'svg'] if not args.no_svg else ['png']))
    record_manifest(args.out_dir, 'seed-summary',
                    [SCRIPT_REL, 'seed-summary', '--out-dir',
                     str(args.out_dir)]
                    + sum((['--runs-glob', item] for item in patterns), []),
                    sources, outputs, notes, started_at, time.time() - began)
    write_readme(args.out_dir)
    print('[seed-summary] %d run(s) (%d skipped) -> %s'
          % (len(runs), len(skipped), target), flush=True)
    return 0


# ===========================================================================
# 9. summary-tables -- markdown core tables for one experiment round
# ===========================================================================
EXP1_STATE_SPECS = (
    ('g3_start', G3_START, 'reference G3 start (before Stage-0 conversion)'),
    ('common_start_off', None, 'Stage-0 converted common start (multi-arc OFF)'),
    ('on_c_free', None, 'ON: G4c_free stage'),
    ('on_g4d', None, 'ON: G4d final'),
    ('off_c_free', None, 'OFF: G4c_free stage'),
    ('off_g4d', None, 'OFF: G4d final'),
)


def _exp1_state_dirs(root):
    return {
        'g3_start': G3_START,
        'common_start_off': root / '01_common_start',
        'on_c_free': root / '02_experiment1' / 'on' / '01_c_free',
        'on_g4d': root / '02_experiment1' / 'on' / '02_g4d',
        'off_c_free': root / '02_experiment1' / 'off' / '01_c_free',
        'off_g4d': root / '02_experiment1' / 'off' / '02_g4d',
    }


def _state_table_entry(name, role, directory):
    directory = Path(directory)
    entry = dict(state=name, role=role, dir=rel(directory), status='ok')
    expected = []
    if not directory.exists():
        entry.update(status='MISSING',
                     missing='directory does not exist (round still running?)')
        return entry
    routes = directory / 'routes_l3d.json'
    best_routes = directory / 'best_valid' / 'routes_l3d.json'
    if not routes.is_file() and not best_routes.is_file():
        expected.append('routes_l3d.json or best_valid/routes_l3d.json')
    if expected:
        entry.update(status='MISSING', missing='; '.join(expected))
        return entry
    metrics = _run_metrics(directory)
    entry.update(metrics)
    entry['dir'] = rel(directory)
    if metrics.get('final_crossings') is None:
        entry['status'] = 'pending'
        entry['missing'] = ('running / not collected yet: no crossing count in '
                            'crossing_stats.json, audit_state.json, '
                            'summary*.json or validation_final')
    else:
        entry['status'] = 'ok'
    return entry


def _write_summary_markdown(path, title, sections):
    lines = ['# %s' % title, '',
             'Generated by `%s` at %s.' % (SCRIPT_REL, now_local()), '']
    for heading, body_lines in sections:
        lines.append('## %s' % heading)
        lines.append('')
        lines.extend(body_lines)
        lines.append('')
    Path(path).write_text('\n'.join(lines), encoding='utf-8')
    return Path(path)


def _fmt_value(value, digits=1):
    if value is None:
        return 'n/a'
    if isinstance(value, bool):
        return 'yes' if value else 'no'
    if isinstance(value, float):
        return ('%.*f' % (digits, value))
    return str(value)


def _table_lines(header, rows):
    lines = ['| ' + ' | '.join(header) + ' |',
             '| ' + ' | '.join('---' for _ in header) + ' |']
    for row in rows:
        lines.append('| ' + ' | '.join(str(item) for item in row) + ' |')
    return lines


def cmd_summary_tables(args, started_at, began):
    root = resolve_path(args.exp_root)
    if not root.is_dir():
        raise DataError('experiment root does not exist: %s' % root)
    is_exp1 = ((root / '02_experiment1').is_dir()
               or (root / '01_common_start').is_dir())
    is_exp2 = ((root / 'runs').is_dir() or (root / 'START.json').is_file()
               or (root / 'tables').is_dir())
    if not is_exp1 and not is_exp2:
        raise DataError('%s contains neither 02_experiment1/ / 01_common_start/ '
                        '(round 1) nor runs/ (round 2)' % root)
    round_slug = ('round1_original' if is_exp1 and not is_exp2
                  else ('round2_final' if is_exp2 and not is_exp1
                        else 'both'))
    target = Path(args.out_dir) / 'tables' / round_slug
    target.mkdir(parents=True, exist_ok=True)
    payload = dict(schema='20h_ablation_summary_tables_v1',
                   generated_at=now_local(), exp_root=rel(root),
                   round=round_slug,
                   states=[], runs=[], decomposition=None,
                   missing_states=[], missing_runs=[],
                   lead_tables=[])
    sections = []
    if is_exp1:
        state_dirs = _exp1_state_dirs(root)
        lead_index = {}
        lead_metrics_path = root / 'tables' / 'exp1_metrics.json'
        lead_payload = read_json(lead_metrics_path)
        if isinstance(lead_payload, dict):
            for key, item in lead_payload.items():
                if isinstance(item, dict):
                    lead_index[str(key)] = item
        lead_fields = (
            ('final_crossings', ('crossings',)),
            ('crossing_pairs', ('crossing_pairs',)),
            ('routes_with_crossings', ('routes_with_crossings',)),
            ('max_route_crossings', ('max_route_crossings',)),
            ('total_length_mm', ('total_length_mm',)),
            ('multi_arc_routes', ('multi_arc', 'routes_with_multi_arc')),
            ('multi_arc_regions', ('multi_arc', 'total_regions')),
            ('validator_pass', ('validation_final', 'validation_pass')),
            ('violation_count', ('validation_final', 'violation_count')),
            ('model_plane_count', ('validation_final', 'model',
                                   'plane_count')))
        entries = []
        for name, _default, role in EXP1_STATE_SPECS:
            directory = state_dirs.get(name) or _default
            entry = _state_table_entry(name, role, directory) if directory \
                else dict(state=name, role=role, dir='', status='MISSING',
                          missing='state directory unknown')
            lead_item = lead_index.get(name) or {}
            if lead_item:
                filled = []
                for field, path_keys in lead_fields:
                    node = lead_item
                    for key in path_keys:
                        node = node.get(key) if isinstance(node, dict) else None
                    if entry.get(field) is None and node is not None:
                        entry[field] = node
                        filled.append(field)
                if entry['status'] in ('pending', 'MISSING'):
                    entry['status'] = 'ok'
                    entry.pop('missing', None)
                entry['lead_metrics_source'] = rel(lead_metrics_path)
                entry['lead_metrics_fields_filled'] = filled
                if entry.get('routes_sha256') is None:
                    entry['routes_sha256'] = lead_item.get('routes_sha256')
            entries.append(entry)
            if entry['status'] != 'ok':
                payload['missing_states'].append(dict(
                    state=name, dir=entry.get('dir'), missing=entry.get(
                        'missing')))
        payload['states'] = entries
        rows = []
        for entry in entries:
            rows.append([
                '`%s`' % entry['state'],
                'ON' if entry['state'].startswith('on_') else (
                    'OFF' if entry['state'].startswith('off_') else 'start'),
                _fmt_value(entry.get('final_crossings')),
                _fmt_value(entry.get('crossing_pairs')),
                _fmt_value(entry.get('max_route_crossings')),
                _fmt_value(entry.get('total_length_mm'), 2),
                _fmt_value(entry.get('multi_arc_routes')),
                _fmt_value(entry.get('multi_arc_regions')),
                _fmt_value(entry.get('validator_pass')),
                _fmt_value(entry.get('violation_count')),
                'ok' if entry['status'] == 'ok'
                else ('PENDING: %s' % entry.get('missing')
                      if entry['status'] == 'pending'
                      else 'MISSING: %s' % entry.get('missing')),
            ])
        sections.append(('Round 1 -- state table (per-height state audit)', [
            'Crossings / unique pairs / max per-route crossings / total length '
            'are read from the independent `audit_state.json` when present, '
            'else from the authoritative `crossing_stats.json` totals, else '
            'from the independent validator counts (`validation_final/'
            'validation.json`); nothing is estimated.  A state that has not '
            'been produced yet is shown as MISSING.', '']
            + _table_lines(
                ['state', 'arm', 'crossings', 'unique pairs', 'max/route',
                 'length (mm)', 'multi-arc routes', 'multi-arc regions',
                 'validator pass', 'violations', 'status'], rows)))
        by_name = {entry['state']: entry for entry in entries}

        def crossing_of(name):
            entry = by_name.get(name) or {}
            return entry.get('final_crossings')

        g3 = crossing_of('g3_start')
        common = crossing_of('common_start_off')
        on = crossing_of('on_g4d')
        off = crossing_of('off_g4d')
        decomposition = None
        if None not in (g3, common, on, off):
            decomposition = dict(
                g3_start=int(g3), conversion_delta=int(common) - int(g3),
                common_start_off=int(common),
                on_search_gain=int(on) - int(g3),
                off_search_gain=int(off) - int(common),
                final_difference=int(off) - int(on),
                on_g4d=int(on), off_g4d=int(off))
            payload['decomposition'] = decomposition
            rows = [
                ['G3 start -> converted common start (Stage-0 A)',
                 _fmt_value(g3), _fmt_value(common),
                 '%+d' % decomposition['conversion_delta']],
                ['G3 start -> ON final (search effect)',
                 _fmt_value(g3), _fmt_value(on),
                 '%+d' % decomposition['on_search_gain']],
                ['common start -> OFF final (search effect)',
                 _fmt_value(common), _fmt_value(off),
                 '%+d' % decomposition['off_search_gain']],
                ['ON final vs OFF final (B - A at the end)',
                 _fmt_value(on), _fmt_value(off),
                 '%+d' % decomposition['final_difference']],
            ]
            sections.append(('Round 1 -- effect decomposition', [
                'Effect A (conversion cost) = common start - G3 start; effect B '
                '(search from an identical start) = OFF final - common start; '
                'the ON arm starts from the G3 state.', '']
                + _table_lines(['step', 'from crossings', 'to crossings',
                                'delta'], rows)))

        lead_specs = [
            root / 'tables' / 'exp1_metrics.json',
            root / 'tables' / 'exp1_decomposition.json',
            root / 'tables' / 'exp1_states.csv',
            root / 'tables' / 'exp1_per_height.csv',
        ]
        for path in lead_specs:
            if path.is_file():
                payload['lead_tables'].append(file_entry(path))
        if payload['lead_tables']:
            sections.append(('Round 1 -- driver tables detected (cross-check '
                             'only)', [
                'These files are written by the round-1 driver; this script '
                'records them for cross-checking and does not use them as a '
                'substitute for the per-state artifacts.', '']
                + _table_lines(['file', 'bytes', 'sha256'],
                               [[('`%s`' % item['path']), item['bytes'],
                                 '`%s`' % item['sha256'][:16]]
                                for item in payload['lead_tables']])))
    if is_exp2:
        patterns = getattr(args, 'runs_glob', None) or [
            str((root / 'runs') / '*' / '*')]
        directories = _expand_globs(patterns)
        run_records = []
        if not directories:
            payload['missing_runs'].append(dict(
                dir=rel(root / 'runs'),
                reason='no run directory exists yet (the three-seed runs have '
                       'not been produced)'))
        for directory in directories:
            directory = Path(directory)
            has_state = ((directory / 'routes_l3d.json').is_file()
                         or (directory / 'best_valid' / 'routes_l3d.json'
                             ).is_file()
                         or (directory / 'run_meta.json').is_file())
            if not has_state:
                payload['missing_runs'].append(dict(
                    dir=rel(directory),
                    reason='run directory exists but holds no arm artifacts '
                           'yet (still starting / queued)'))
                continue
            identity = _run_identity(directory)
            if identity is None:
                payload['missing_runs'].append(dict(
                    dir=rel(directory), reason='cannot identify arm/seed'))
                continue
            metrics = _run_metrics(directory)
            record = dict(identity)
            record.update(metrics)
            run_records.append(record)
        payload['runs'] = run_records
        rows = []
        for record in sorted(run_records, key=lambda item: (
                item['kind'], item['seed'], item['arm'])):
            rows.append([
                record['kind'], record['arm'], record['seed'],
                _fmt_value(record.get('final_crossings')),
                _fmt_value(record.get('crossing_pairs')),
                _fmt_value(record.get('max_route_crossings')),
                _fmt_value(record.get('total_length_mm'), 2),
                _fmt_value(record.get('multi_arc_regions')),
                _fmt_value(record.get('validator_pass')),
                _fmt_value(record.get('all_gates_pass')),
                '`%s`' % record['run_dir']])
        if rows:
            sections.append(('Round 2 -- per-run table (three seeds, primary '
                             'c1 and auxiliary a1)', [
                'Crossing / pair / max-per-route / length values prefer the '
                'independent `audit_state.json`, then `summary.json` / '
                '`summary_g4.json`, then the fresh-process validator counts.',
                '']
                + _table_lines(
                    ['kind', 'arm', 'seed', 'crossings', 'unique pairs',
                     'max/route', 'length (mm)', 'multi-arc regions',
                     'validator pass', 'all gates pass', 'run dir'], rows)))
    # per-height cross-check of the ON/OFF finals (from real crossing_stats)
    if is_exp1:
        on_entry = payload['states'][3] if len(payload['states']) > 3 else None
        off_entry = payload['states'][5] if len(payload['states']) > 5 else None
        if (on_entry and off_entry and on_entry.get('status') == 'ok'
                and off_entry.get('status') == 'ok'):
            try:
                on_state = analyze_state(on_entry['dir'],
                                         Path(args.out_dir) / '_inputs',
                                         label='summary_on')
                off_state = analyze_state(off_entry['dir'],
                                          Path(args.out_dir) / '_inputs',
                                          label='summary_off')
                rows = []
                for plane in on_state['model'].planes:
                    pid = int(plane['plane_id'])
                    on_info = on_state['per_plane'][pid]
                    off_info = off_state['per_plane'][pid]
                    rows.append([
                        str(plane['label']), fmt_z(plane['z_mm']),
                        _fmt_value(on_info['crossing_count']),
                        _fmt_value(off_info['crossing_count']),
                        '%+d' % (int(off_info['crossing_count'])
                                 - int(on_info['crossing_count'])),
                        _fmt_value(on_info['crossing_pairs']),
                        _fmt_value(off_info['crossing_pairs'])])
                payload['per_height_on_off'] = rows
                sections.append(('Round 1 -- per-height ON vs OFF final '
                                 'crossings', [
                    'Exact-z per-height counters of the two final states; '
                    'sources: %s / %s.'
                    % (on_state['counts_source'], off_state['counts_source']),
                    ''] + _table_lines(
                        ['height', 'z (mm)', 'ON events', 'OFF events',
                         'B-A', 'ON pairs', 'OFF pairs'], rows)))
            except DataError as error:
                payload['per_height_error'] = str(error)
    if payload['missing_states'] or payload['missing_runs']:
        lines = []
        for item in payload['missing_states']:
            lines.append('- state `%s` (%s): %s'
                         % (item['state'], item.get('dir') or '?',
                            item['missing']))
        for item in payload['missing_runs']:
            lines.append('- %s (%s): %s'
                         % (item.get('dir') or '?', item.get('reason') or '',
                            'waiting for the experiment to produce it'))
        sections.append(('Waiting for / missing data (not estimated, not '
                         'filled in)', lines))
    title = ('20H G4 multi-arc ablation -- core summary tables (%s)'
             % payload['round'])
    md = _write_summary_markdown(target / 'summary_tables.md', title, sections)
    if payload['states']:
        write_csv(target / 'summary_states.csv', payload['states'])
    if payload['runs']:
        write_csv(target / 'summary_runs.csv', payload['runs'])
    write_json(target / 'summary_tables.json', payload)
    outputs = collect_outputs(target, '*', recursive=False)
    notes = dict(round=payload['round'], exp_root=rel(root),
                 states=[entry['state'] for entry in payload['states']],
                 runs=[record['run_dir'] for record in payload['runs']],
                 missing_states=payload['missing_states'],
                 missing_runs=payload['missing_runs'],
                 decomposition=payload['decomposition'],
                 lead_tables=payload['lead_tables'],
                 dpi=int(args.dpi),
                 formats=(['png', 'svg'] if not args.no_svg else ['png']))
    sources = [file_entry(root)] if root.is_file() else []
    used_paths = []
    for entry in payload['states']:
        used_paths.extend(entry.get('files_used') or [])
    for record in payload['runs']:
        used_paths.extend(record.get('files_used') or [])
    for item in payload['lead_tables']:
        used_paths.append(item.get('path'))
    seen = set()
    for item in used_paths:
        if not item:
            continue
        path = PROJECT_ROOT / item
        if not path.is_file() or str(path) in seen:
            continue
        seen.add(str(path))
        sources.append(file_entry(path, role='state_or_run_artifact'))
    for item in payload['lead_tables']:
        path = PROJECT_ROOT / item['path']
        if path.is_file():
            sources.append(file_entry(path, role='driver_table'))
    record_manifest(args.out_dir, 'summary-tables',
                    [SCRIPT_REL, 'summary-tables', '--exp-root',
                     args.exp_root, '--out-dir', str(args.out_dir)],
                    sources, outputs, notes, started_at, time.time() - began)
    write_readme(args.out_dir)
    print('[summary-tables] %s -> %s' % (rel(root), md), flush=True)
    return 0


# ===========================================================================
# README index (regenerated after every command)
# ===========================================================================
def write_readme(out_dir):
    out_dir = Path(out_dir)
    payload = read_manifest(out_dir)
    lines = ['# 20H G4 multi-arc ablation -- figure / table index', '',
             'Generated by `%s` at %s.' % (SCRIPT_REL, now_local()), '',
             'Every figure is a real-data rendering of the 20-height G4 '
             'multi-arc ablation; missing artifacts are reported as errors '
             'instead of being estimated.  The full provenance of each '
             'invocation (command line, timestamps, source SHA256, output '
             'SHA256, statistics source and derived-quantity definitions) is '
             'in `%s`.' % MANIFEST_NAME, '',
             '## Re-run on the final experiment data (when it exists)', '',
             'Nothing is estimated, so every command can be re-run unchanged '
             'once the round-1 / round-2 arms finish.  Example commands '
             '(round 1 shown; round 2 analogously, output to '
             '`experiments/20H_G4_MULTI_ARC_ABLATION_FINAL_1024/04_figures`):', '',
             '```bat',
             'rem per-height figures of the ON / OFF final states',
             '.venv\\Scripts\\python.exe experiments\\20H_G4_MULTI_ARC_ABLATION_'
             '1024\\tools\\plots_ablation.py layers ^',
             '    --run-dir experiments\\20H_G4_MULTI_ARC_ABLATION_1024\\'
             '02_experiment1\\on\\02_g4d ^',
             '    --out-dir  experiments\\20H_G4_MULTI_ARC_ABLATION_1024\\'
             '05_figures',
             '',
             'rem same-height side-by-side ON vs OFF + 20-height overview',
             '.venv\\Scripts\\python.exe experiments\\20H_G4_MULTI_ARC_ABLATION_'
             '1024\\tools\\plots_ablation.py compare-layers ^',
             '    --a experiments\\20H_G4_MULTI_ARC_ABLATION_1024\\'
             '02_experiment1\\on\\02_g4d ^',
             '    --b experiments\\20H_G4_MULTI_ARC_ABLATION_1024\\'
             '02_experiment1\\off\\02_g4d ^',
             '    --a-label ON --b-label OFF --out-dir ...\\05_figures',
             '',
             'rem true-3-D comparison, local route cases, per-height tables',
             '.venv\\Scripts\\python.exe ...\\plots_ablation.py global3d '
             '--a ...on\\02_g4d --b ...off\\02_g4d --out-dir ...\\05_figures',
             '.venv\\Scripts\\python.exe ...\\plots_ablation.py route-case '
             '--a ...on\\02_g4d --b ...off\\02_g4d --route-id auto '
             '--out-dir ...\\05_figures',
             '.venv\\Scripts\\python.exe ...\\plots_ablation.py layer-stats '
             '--state ON=...on\\02_g4d --state OFF=...off\\02_g4d '
             '--out-dir ...\\05_figures',
             '',
             'rem Stage-0 conversion lateral offset vs 2R = 30 mm',
             '.venv\\Scripts\\python.exe ...\\plots_ablation.py offset-2r ^',
             '    --conversion-report experiments\\20H_G4_MULTI_ARC_ABLATION_'
             '1024\\01_common_start\\conversion_report.json ^',
             '    --out-dir experiments\\20H_G4_MULTI_ARC_ABLATION_1024\\'
             '05_figures',
             '',
             'rem search curves, three-seed paired summary, core tables',
             '.venv\\Scripts\\python.exe ...\\plots_ablation.py curves '
             '--state ON=...on\\02_g4d --state OFF=...off\\02_g4d '
             '--out-dir ...\\05_figures',
             '.venv\\Scripts\\python.exe ...\\plots_ablation.py seed-summary ^',
             '    --runs-glob "experiments\\20H_G4_MULTI_ARC_ABLATION_FINAL_'
             '1024\\runs\\*\\c1_*" ^',
             '    --out-dir experiments\\20H_G4_MULTI_ARC_ABLATION_FINAL_1024\\'
             '04_figures',
             '.venv\\Scripts\\python.exe ...\\plots_ablation.py summary-tables '
             '--exp-root experiments\\20H_G4_MULTI_ARC_ABLATION_1024 '
             '--out-dir ...\\05_figures',
             '```', '',
             'If a `best_valid/` snapshot is given whose sibling '
             '`crossing_stats.json` belongs to a different final state, the '
             'script verifies the exact per-plane audit; on mismatch it falls '
             'back to the exact recomputation from the real line/arc '
             'primitives (never an estimate) and states the source in '
             '`manifest.json` and in the figure footer.', '']
    for entry in payload.get('entries') or []:
        lines.append('## `%s`  (%s, %.1f s)'
                     % (entry.get('command'), entry.get('finished_at'),
                        entry.get('elapsed_seconds') or 0.0))
        lines.append('')
        lines.append('```')
        lines.append(' '.join(entry.get('argv') or []))
        lines.append('```')
        lines.append('')
        notes = entry.get('notes') or {}
        for key in ('mode', 'caveat', 'selection', 'z_match_rule'):
            if notes.get(key):
                lines.append('- %s: %s' % (key, notes[key]))
        a = notes.get('a') or {}
        b = notes.get('b') or {}
        for label, item in (('A', a), ('B', b)):
            if item:
                lines.append('- %s: `%s` -- %s crossings, counts source '
                             '`%s`' % (label, item.get('state_dir'),
                                       item.get('crossings'),
                                       item.get('counts_source')))
        state = notes.get('state') or {}
        if state:
            lines.append('- state: `%s` -- %s crossings, counts source `%s`'
                         % (state.get('state_dir'), state.get('crossings'),
                            state.get('counts_source')))
        figures = [out for out in entry.get('outputs') or []
                   if out.get('format') in ('png', 'svg')]
        if figures:
            lines.append('')
            lines.append('| file | format | dpi | bytes | sha256 (16) |')
            lines.append('| --- | --- | --- | --- | --- |')
            for out in figures:
                lines.append('| `%s` | %s | %s | %s | `%s` |'
                             % (out.get('path_from_out_dir') or out.get('path'),
                                out.get('format'), out.get('dpi') or '',
                                out.get('bytes'),
                                (out.get('sha256') or '')[:16]))
        lines.append('')
    (out_dir / README_NAME).write_text('\n'.join(lines), encoding='utf-8')
    return out_dir / README_NAME


# ---------------------------------------------------------------------------
# command line
# ---------------------------------------------------------------------------
def build_parser():
    parser = argparse.ArgumentParser(
        prog='plots_ablation.py',
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='All outputs are real-data figures/tables; missing artifacts are '
               'reported as errors instead of being estimated.\n'
               'Typical root: %s' % rel(PROJECT_ROOT))
    parser.add_argument('--version', action='version',
                        version='plots_ablation.py 1.0 (%s)' % SCRIPT_REL)
    sub = parser.add_subparsers(dest='command', metavar='COMMAND')

    def common_cmd(name, help_text, description, out_default):
        item = sub.add_parser(name, help=help_text, description=description,
                              formatter_class=argparse.RawDescriptionHelpFormatter)
        item.add_argument('--out-dir', default=(str(out_default)
                                                if out_default else None),
                          help='output directory (created; default: %s)'
                               % (out_default or 'required'))
        item.add_argument('--dpi', type=int, default=DPI_DEFAULT,
                          help='PNG resolution, >=150 (default %d)'
                               % DPI_DEFAULT)
        item.add_argument('--no-svg', action='store_true',
                          help='write PNG only (SVG is written by default)')
        return item

    # 1. layers
    item = common_cmd('layers', 'per-height routing figures (delegates to '
                      'plot_layers20.build)',
                      'Generate the 20 per-height routing figures + crossing '
                      'figures through the frozen coldstart20 driver\n'
                      'plot_layers20.build(run_dir, out_dir).  No renderer is '
                      're-implemented here.', EXP1_FIGURES)
    item.add_argument('--run-dir', required=True,
                      help='state directory (final run dir or .../best_valid)')
    item.add_argument('--label', default=None,
                      help='state label for the output sub-directory')

    # 2. compare-layers
    item = common_cmd('compare-layers', 'A|B side-by-side per-height panels + '
                      '20-height overview',
                      'Same-height side-by-side comparison (A = ON, B = OFF).\n'
                      'One figure per routing height with both states on equal '
                      'axes, plus a 20-height overview grid.  Each panel is '
                      'titled with its own crossing event / pair count.',
                      EXP1_FIGURES)
    item.add_argument('--a', required=True, help='state A directory (ON)')
    item.add_argument('--b', required=True, help='state B directory (OFF)')
    item.add_argument('--a-label', default='ON', help='legend label of A')
    item.add_argument('--b-label', default='OFF', help='legend label of B')

    # 3. global3d
    item = common_cmd('global3d', 'true-3-D global routing comparison',
                      'True-3-D drawing (mplot3d) of all 1024 real centre lines '
                      'of both states, transitions included, coloured by routing '
                      'height, one glass-envelope view each.', EXP1_FIGURES)
    item.add_argument('--a', required=True, help='state A directory (ON)')
    item.add_argument('--b', required=True, help='state B directory (OFF)')
    item.add_argument('--a-label', default='ON', help='title label of A')
    item.add_argument('--b-label', default='OFF', help='title label of B')
    item.add_argument('--elev', type=float, default=30.0,
                      help='3-D view elevation (default 30)')
    item.add_argument('--azim', type=float, default=-60.0,
                      help='3-D view azimuth (default -60)')

    # 4. route-case
    item = common_cmd('route-case', 'local XY geometry of one route in both '
                      'states',
                      'Local XY geometry of the same route_id in both states, '
                      'same coordinate scale, real arcs/lines, multi-arc '
                      'regions and the ablated replacement annotated.', EXP1_FIGURES)
    item.add_argument('--a', required=True, help='state A directory (ON)')
    item.add_argument('--b', required=True, help='state B directory (OFF)')
    item.add_argument('--route-id', default='auto',
                      help='route id(s): comma separated integers, or "auto" '
                           '(largest per-route crossing difference)')
    item.add_argument('--top', type=int, default=3,
                      help='number of auto-selected routes (default 3)')
    item.add_argument('--pad-mm', type=float, default=6.0,
                      help='window padding around the local geometry (default '
                           '6 mm)')
    item.add_argument('--window-max-mm', type=float, default=80.0,
                      help='maximum window side (default 80 mm; 0 = no cap). '
                           'The window is centred on the geometry difference '
                           'between the two states so the multi-arc region / '
                           'ablated detour is readable even for a long route.')
    item.add_argument('--a-label', default='ON', help='label of A')
    item.add_argument('--b-label', default='OFF', help='label of B')

    # 5. layer-stats
    item = common_cmd('layer-stats', 'per-height crossing / pair / route tables '
                      'and bars',
                      'Per-height crossing events / unique crossing pairs / '
                      'route counts with exact-z matching; CSV + JSON + grouped '
                      'bar chart.', EXP1_FIGURES)
    item.add_argument('--run-dir', action='append', default=[],
                      help='state directory (repeatable); label defaults to a '
                           'compact path label')
    item.add_argument('--state', action='append', default=[],
                      help='explicit name=dir state (repeatable, overrides '
                           '--run-dir labels)')

    # 6. offset-2r
    item = common_cmd('offset-2r', 'Stage-0 conversion lateral offset vs the '
                      '2R = 30 mm threshold',
                      'Per-route lateral offset |bx| of the Stage-0 multi-arc '
                      'conversion against the 2R = 30 mm threshold: CSV + '
                      'scatter + binned summary.\n\n'
                      'Definition: |bx| is the lateral component of the '
                      'landing-pose displacement (B - A) in the frozen D56 '
                      'canonical body frame of the inherited route.  It is '
                      'recomputed from the real assignment_1024.csv + '
                      'routes_l3d.json with route_builder.body_task / '
                      'direct_task and layer2d.canonical_frame -- the exact '
                      'quantity the frozen grammar calls "bx".  For N/S ports '
                      'it is |dx| between the two body landing points, for E/W '
                      'ports |dy|; the world-frame check from the stored body '
                      'endpoints is reported along side.  A route is "below '
                      '2R" iff |bx| < 2R = 30.000 mm (R15 = 15 mm).',
                      EXP1_FIGURES)
    item.add_argument('--conversion-report', required=True,
                      help='conversion_report.json written by the Stage-0 '
                           'conversion (start_dir + out_dir + records)')

    # 7. curves
    item = common_cmd('curves', 'search-progress curves (crossings vs budget '
                      'axes)',
                      'Crossings vs d56 candidate evaluations / route 3-D checks '
                      '/ wall seconds, three sub-plots, several runs overlaid.\n'
                      'Primary source: strategy_stats.json extra.history_records. '
                      'Falls back to optimization_history.csv and to '
                      'strategy_stats.json rounds when a run has no per-attempt '
                      'history (stated on the figure).', EXP1_FIGURES)
    item.add_argument('--run-dir', action='append', default=[],
                      help='run directory (repeatable); label = compact path')
    item.add_argument('--state', action='append', default=[],
                      help='explicit name=dir run (repeatable)')

    # 8. seed-summary
    item = common_cmd('seed-summary', 'three-seed ON/OFF paired statistics',
                      'Three-seed ON/OFF paired table (mean, sample std ddof=1, '
                      'min/max, paired difference) + box/scatter figure.\n'
                      'Reads each run directory under the glob (audit_state.json '
                      '-> summary.json -> summary_g4.json -> validation_final).',
                      EXP2_FIGURES)
    item.add_argument('--runs-glob', action='append', default=[],
                      help='glob(s) of run directories (repeatable; default: '
                           'experiments/20H_G4_MULTI_ARC_ABLATION_FINAL_1024/'
                           'runs/*/c1_*)')

    # 9. summary-tables
    item = common_cmd('summary-tables', 'markdown core tables of one round',
                      'Markdown / CSV / JSON core tables for one experiment '
                      'root: crossings, unique crossing pairs, max per-route '
                      'crossings, total length and independent-validator '
                      'status.  Missing states are reported explicitly (never '
                      'filled in).', None)
    item.add_argument('--exp-root', required=True,
                      help='experiment root (round 1 or round 2 directory)')
    item.add_argument('--runs-glob', action='append', default=[],
                      help='optional glob(s) of round-2 run directories '
                           '(default: <exp-root>/runs)')

    return parser


def _add_common_out_default(args):
    if getattr(args, 'out_dir', None):
        args.out_dir = Path(args.out_dir)
    else:
        if getattr(args, 'exp_root', None):
            root = resolve_path(args.exp_root)
            args.out_dir = (root / '04_figures' if (root / 'runs').is_dir()
                            else root / '05_figures')
        elif args.command == 'seed-summary':
            args.out_dir = EXP2_FIGURES
        else:
            args.out_dir = EXP1_FIGURES


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1
    if getattr(args, 'dpi', DPI_DEFAULT) < 150:
        parser.error('--dpi must be >= 150 (figure spec)')
    _add_common_out_default(args)
    args.out_dir = Path(args.out_dir)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    handlers = {
        'layers': cmd_layers,
        'compare-layers': cmd_compare_layers,
        'global3d': cmd_global3d,
        'route-case': cmd_route_case,
        'layer-stats': cmd_layer_stats,
        'offset-2r': cmd_offset_2r,
        'curves': cmd_curves,
        'seed-summary': cmd_seed_summary,
        'summary-tables': cmd_summary_tables,
    }
    started = now_local()
    began = time.time()
    try:
        return int(handlers[args.command](args, started, began) or 0)
    except DataError as error:
        print('[plots_ablation] DATA ERROR: %s' % error, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
