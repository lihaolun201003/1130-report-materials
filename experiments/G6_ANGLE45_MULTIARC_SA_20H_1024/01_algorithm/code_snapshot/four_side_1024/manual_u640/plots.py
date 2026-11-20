# -*- coding: utf-8 -*-
"""Figures for the manual-u640 640-channel 3D routing round.

Two families of figures are produced from the **stored route geometry only**
(``route['parts']``: flat sub-chains of exact R = 15 mm line/arc primitives and
elevation S-curves with ``start/end/z0/z1``):

1. **2D per-layer maps** - one PNG per logical layer ``L1..Lmax``.  A flat part is
   drawn only on its own physical height; the L1 interface layer is split into its
   two physical data-source planes (z1 row ``z = 0.0 mm`` and z2 row
   ``z = 0.5 mm``) because L1 carries both interface rows.  The board outline is
   always the true 150 x 150 mm board with ``aspect = 'equal'``.
2. **3D figures** - every route is sampled in real 3D: flat runs stay at their
   stored physical ``z`` and the elevation transitions are the real two-arc
   S-curves (``z0 -> z1`` over ``2 R sin(theta)``).  Nothing is a 2D curve with a
   constant z glued on.  A full-board overview, a side view (two orthogonal
   projections) and a layer-height profile are written.

Extra: an all-layer XY overlay and a U-nesting zoom (U depth colouring) are added
because the manual fixed-U records are the point of this round.

Everything is headless (``matplotlib.use('Agg')``), English-labelled (the host
has no CJK font), memory is released with ``plt.close`` and a missing / partial
route list never crashes the renderer: individual figures are skipped with a
logged warning instead.

Public API
----------
``render_all(routes, stack, data, out_dir, log=print) -> dict``

``routes`` is the merged record list (routed records with ``parts`` plus failed
records with ``parts = []``); it may also be a JSON path or a ``{'routes': [...]}``
payload.  ``out_dir`` is the figure directory (the pipeline passes
``outputs/manual_u640/plots``).  The returned dict lists every file and the
per-layer counts for the run report.
"""
from __future__ import annotations

import json
import math
import time
from collections import Counter, OrderedDict
from pathlib import Path

import numpy as np

from . import config as C

# ---------------------------------------------------------------------------
# style / constants
# ---------------------------------------------------------------------------
BOARD_MM = float(C.BOARD_MM)
WIDTH_MM = float(C.WIDTH_MM)
RADIUS_MM = float(C.RADIUS_MM)
DPI = 150
SAGITTA_2D_MM = 0.0005          # display polyline accuracy of the R15 arcs (2D)
SAGITTA_3D_MM = 0.003           # display polyline accuracy of the R15 arcs (3D)
TRANSITION_STEP_MM = 0.12       # display step of the elevation S-curves
BOARD_PAD_MM = 8.0
FIG_2D = (8.8, 8.2)
FIG_L1 = (15.6, 7.8)
FIG_3D = (14.4, 9.8)
FIG_SIDE = (15.4, 8.8)
FIG_PROFILE = (15.0, 6.6)
FIG_ZOOM = (11.6, 8.8)

GEOMETRY_NOTE = (
    'Process model (four_side_1024/manual_u640/config.py): board 150 x 150 mm, '
    'waveguide width 0.050 mm, centreline clearance 0.080 mm, fixed bend radius '
    'R = 15 mm, minimum crossing angle 5 deg. Layer heights are simulation '
    'inputs (provenance: unconfirmed_simulation), not confirmed fabrication '
    'parameters.')

#: manual fixed-U groups of the input CSV (one group per layer L1..L6)
MANUAL_GROUP_COLORS = OrderedDict([
    ('NS-1', '#1565c0'),
    ('NS-2', '#00838f'),
    ('EW-1', '#6a1b9a'),
    ('EW-2', '#ad1457'),
    ('Z2-N-1', '#c62828'),
    ('Z2-N-2', '#ef6c00'),
])
#: automatic groups (L7+)
AUTO_GROUP_COLORS = OrderedDict([
    ('z1_opposite_NS', '#2e7d32'),
    ('z1_opposite_EW', '#827717'),
    ('z2_adjacent', '#00897b'),
])
AUTO_GROUP_LABELS = {
    'z1_opposite_NS': 'auto: z1 opposite N-S',
    'z1_opposite_EW': 'auto: z1 opposite E-W',
    'z2_adjacent': 'auto: z2 adjacent',
}
PLANE_COLORS = {'z1': '#1565c0', 'z2': '#c62828'}
TRANSITION_COLOR = '#e65100'
FALLBACK_COLORS = ('#455a64', '#7b1fa2', '#00796b', '#c2185b', '#5d4037',
                   '#0288d1', '#f57c00', '#303f9f')
SIDE_INWARD = {'N': (0.0, -1.0), 'S': (0.0, 1.0),
               'E': (-1.0, 0.0), 'W': (1.0, 0.0)}
ANCHOR = {'N': 0.0, 'S': 0.0, 'E': 0.0, 'W': 0.0}


# ---------------------------------------------------------------------------
# lazy matplotlib
# ---------------------------------------------------------------------------
def _pyplot():
    """Import matplotlib lazily and force the headless Agg backend."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    return plt


def _apply_style(plt):
    plt.rcParams.update({
        'font.size': 8.5,
        'axes.titlesize': 9.5,
        'axes.labelsize': 8.0,
        'xtick.labelsize': 7.0,
        'ytick.labelsize': 7.0,
        'legend.fontsize': 6.8,
        'figure.max_open_warning': 0,
    })
    return plt


# ---------------------------------------------------------------------------
# small value / route helpers
# ---------------------------------------------------------------------------
def _as_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _normalise_routes(routes, warnings):
    """Accept list / ``{'routes': [...]}`` payload / JSON path -> list of dict."""
    raw = routes
    if isinstance(routes, (str, Path)):
        try:
            raw = _load_json(routes)
        except (OSError, json.JSONDecodeError) as exc:
            warnings.append(f'cannot read routes file {routes}: {exc}')
            return []
    if isinstance(raw, dict):
        for key in ('routes', 'all_routes', 'records'):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break
    if not isinstance(raw, (list, tuple)):
        warnings.append(f'unsupported routes container: {type(raw).__name__}')
        return []
    records = []
    for item in raw:
        if isinstance(item, dict):
            records.append(item)
    return records


def _iter_parts(route):
    parts = route.get('parts')
    return parts if isinstance(parts, list) else []


def _flat_parts(route, layer_id=None):
    out = []
    for part in _iter_parts(route):
        if not isinstance(part, dict) or part.get('kind') != 'flat':
            continue
        if layer_id is not None:
            try:
                if int(part.get('layer_id')) != int(layer_id):
                    continue
            except (TypeError, ValueError):
                continue
        if not part.get('primitives'):
            continue
        out.append(part)
    return out


def _transition_parts(route):
    return [part for part in _iter_parts(route)
            if isinstance(part, dict) and part.get('kind') == 'transition']


def _is_routed(route):
    if route.get('status') not in (None, 'routed'):
        return False
    return bool(_flat_parts(route)) or bool(_transition_parts(route))


def _route_plane(route):
    plane = route.get('plane')
    if plane in ('z1', 'z2'):
        return plane
    plane = route.get('dataset')
    if plane in ('z1', 'z2'):
        return plane
    z = _as_float(route.get('start_z_mm'))
    if z is None:
        z = _as_float(route.get('source_z_mm'))
    if z is None:
        port = route.get('source_port') or {}
        z = _as_float(port.get('z_mm'))
    return 'z1' if (z is None or abs(z) < 1e-9) else 'z2'


def _layer_of_z(z_mm):
    """Logical layer id of a physical height (L1 for either interface row)."""
    z = _as_float(z_mm)
    if z is None:
        return None
    for plane in ('z1', 'z2'):
        if abs(z - float(C.PLANE_Z_MM[plane])) <= 1e-9:
            return int(C.INTERFACE_LAYER_ID)
    for layer_id in range(2, int(C.MAX_LOGICAL_LAYERS) + 1):
        if abs(z - float(C.layer_z(layer_id))) <= 1e-9:
            return int(layer_id)
    return None


def _route_layer(route):
    """Logical layer of one route: explicit field first, else from its flats."""
    value = route.get('logical_layer')
    if value is None:
        value = route.get('target_layer')
    try:
        if value is not None:
            return int(value)
    except (TypeError, ValueError):
        pass
    heights = []
    for part in _flat_parts(route):
        z = _as_float(part.get('z_mm'))
        if z is not None:
            heights.append(z)
    for height in sorted(heights, reverse=True):
        layer_id = _layer_of_z(height)
        if layer_id is not None:
            return layer_id
    return None


def _manual_group(route):
    group = route.get('manual_group')
    if isinstance(group, str) and group.strip():
        return group.strip()
    return None


def _auto_group(route):
    dataset = route.get('dataset') or route.get('plane') or 'z1'
    relation = str(route.get('relation') or '')
    side = route.get('source_side')
    if relation == 'opposite':
        return ('z1_opposite_NS' if side in ('N', 'S')
                else 'z1_opposite_EW')
    if relation == 'adjacent':
        return 'z2_adjacent'
    if relation == 'same':
        return f'{dataset}_same_side'
    return f'{dataset}_{relation or "unknown"}'


def _group_of(route):
    """Stable colour-group key + label + palette kind."""
    if route.get('assignment') == 'manual_fixed_u':
        group = _manual_group(route)
        if group is not None:
            return ('manual', group,
                    MANUAL_GROUP_COLORS.get(group, FALLBACK_COLORS[0]))
        return ('manual', 'manual U (group n/a)', FALLBACK_COLORS[0])
    group = _auto_group(route)
    color = AUTO_GROUP_COLORS.get(
        group, FALLBACK_COLORS[hash(group) % len(FALLBACK_COLORS)])
    return ('auto', group, color)


def _group_label(kind, group):
    if kind == 'manual':
        return f'manual U {group}'
    return AUTO_GROUP_LABELS.get(group, f'auto {group}')


# ---------------------------------------------------------------------------
# geometry sampling
# ---------------------------------------------------------------------------
def _sample_flat(part, sagitta=SAGITTA_2D_MM):
    """XY polyline of one flat part (R15 arcs sampled to the given sagitta)."""
    primitives = part.get('primitives') or []
    if not primitives:
        return None
    try:
        from four_side_1024.geometry import sample as sample_primitives
        points = sample_primitives(primitives, float(sagitta))
    except Exception:  # noqa: BLE001 - a bad primitive must not kill the figure
        return None
    if points is None or len(points) < 2:
        return None
    return np.asarray(points, dtype=float)


def _transition_polyline(part, step_mm=TRANSITION_STEP_MM):
    """Real 3D S-curve samples of one stored elevation transition.

    Two circular arcs of radius R in the vertical plane of the local straight
    direction: ``theta = acos(1 - |dz| / (2R))``, footprint ``2 R sin(theta)``.
    """
    radius = _as_float(part.get('radius_mm')) or RADIUS_MM
    z0 = _as_float(part.get('z0'))
    z1 = _as_float(part.get('z1'))
    start = part.get('start')
    direction = part.get('direction')
    if z0 is None or z1 is None or start is None or direction is None:
        return None
    start = np.asarray(start, dtype=float)
    direction = np.asarray(direction, dtype=float)
    norm = float(np.hypot(direction[0], direction[1]))
    if norm <= 0.0 or not math.isfinite(norm):
        return None
    direction = direction / norm
    dz = float(z1) - float(z0)
    if abs(dz) <= 1e-12:
        return None
    sign = 1.0 if dz >= 0.0 else -1.0
    theta = _as_float(part.get('theta_rad'))
    if theta is None or theta <= 0.0:
        ratio = 1.0 - abs(dz) / (2.0 * radius)
        theta = math.acos(max(-1.0, min(1.0, ratio)))
    if theta <= 0.0:
        return None
    footprint = 2.0 * radius * math.sin(theta)
    arc_length = 2.0 * radius * theta
    count = max(2, int(math.ceil(arc_length / max(step_mm, 1e-9))))
    phase = np.linspace(0.0, 2.0 * theta, count + 1)
    first = phase <= theta
    u = np.where(first, radius * np.sin(phase),
                 footprint - radius * np.sin(2.0 * theta - phase))
    w = np.where(first, z0 + sign * radius * (1.0 - np.cos(phase)),
                 z1 - sign * radius * (1.0 - np.cos(2.0 * theta - phase)))
    xy = start[None, :] + u[:, None] * direction[None, :]
    return np.column_stack([xy, w])


def _route_chunks_3d(route, sagitta=SAGITTA_3D_MM,
                     step_mm=TRANSITION_STEP_MM):
    """Real 3D chunks of one route: ``[{kind, points(n,3), layer_id, z_mm}]``."""
    chunks = []
    for part in _iter_parts(route):
        if not isinstance(part, dict):
            continue
        kind = part.get('kind')
        if kind == 'flat':
            xy = _sample_flat(part, sagitta)
            if xy is None:
                continue
            z = _as_float(part.get('z_mm'))
            if z is None:
                z = 0.0
            points = np.column_stack([xy, np.full(len(xy), z)])
            try:
                layer_id = int(part.get('layer_id'))
            except (TypeError, ValueError):
                layer_id = _layer_of_z(z)
            chunks.append(dict(kind='flat', points=points, layer_id=layer_id,
                               z_mm=z))
        elif kind == 'transition':
            points = _transition_polyline(part, step_mm)
            if points is None or len(points) < 2:
                continue
            chunks.append(dict(kind='transition', points=points, layer_id=None,
                               z_mm=None, z0=part.get('z0'),
                               z1=part.get('z1')))
    return chunks


def _depth_mm(points, source_xy, inward):
    """Penetration depth of a flat sub-chain into the board from its port."""
    if points is None or len(points) == 0:
        return None
    delta = np.asarray(points, dtype=float)[:, :2] - np.asarray(source_xy, float)
    values = delta @ np.asarray(inward, float)
    return float(np.max(values))


def _record_inward(route):
    """Inward normal of the route source port (from its side)."""
    side = route.get('source_side')
    if side in SIDE_INWARD:
        return SIDE_INWARD[side]
    return (0.0, -1.0)


def _route_source_xy(route):
    for key in ('source_xy_mm', 'source_xy'):
        value = route.get(key)
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            return [float(value[0]), float(value[1])]
    port = route.get('source_port') or {}
    xy = port.get('xy')
    if isinstance(xy, (list, tuple)) and len(xy) >= 2:
        return [float(xy[0]), float(xy[1])]
    endpoint = route.get('source_endpoint') or {}
    xy = endpoint.get('xy')
    if isinstance(xy, (list, tuple)) and len(xy) >= 2:
        return [float(xy[0]), float(xy[1])]
    return [0.0, 0.0]


# ---------------------------------------------------------------------------
# layer bookkeeping
# ---------------------------------------------------------------------------
def _layer_table(routes, stack, warnings):
    """Per logical layer counts / heights from the route geometry."""
    max_layer_available = int(getattr(stack, 'max_layer', C.MAX_LOGICAL_LAYERS))
    routed = [route for route in routes if _is_routed(route)]
    failed = [route for route in routes
              if route.get('status') == 'failed' or not _is_routed(route)]

    table = OrderedDict()

    def entry(layer_id):
        item = table.get(layer_id)
        if item is None:
            item = dict(layer_id=int(layer_id),
                        layer_label=f'L{int(layer_id)}',
                        layer_type=('interface'
                                    if int(layer_id) == C.INTERFACE_LAYER_ID
                                    else 'routing'),
                        z_mm=([float(C.Z1_MM), float(C.Z2_MM)]
                              if int(layer_id) == C.INTERFACE_LAYER_ID
                              else [float(C.layer_z(int(layer_id)))]),
                        routed=0, manual=0, automatic=0, failed=0,
                        z_plane_counts=Counter())
            table[layer_id] = item
        return item

    for route in routed:
        layers = set()
        explicit = _route_layer(route)
        if explicit is not None and 1 <= int(explicit) <= max_layer_available:
            layers.add(int(explicit))
        for part in _flat_parts(route):
            try:
                layer_id = int(part.get('layer_id'))
            except (TypeError, ValueError):
                layer_id = _layer_of_z(part.get('z_mm'))
            if layer_id is not None and 1 <= layer_id <= max_layer_available:
                layers.add(layer_id)
                z = _as_float(part.get('z_mm'))
                if z is not None:
                    entry(layer_id)['z_plane_counts'][round(z, 6)] += 1
        if not layers:
            warnings.append(f"route {route.get('uid')} has no identifiable "
                            f"logical layer")
            continue
        for layer_id in layers:
            item = entry(layer_id)
            item['routed'] += 1
            if route.get('assignment') == 'manual_fixed_u':
                item['manual'] += 1
            else:
                item['automatic'] += 1
    for route in failed:
        layer_id = _route_layer(route)
        if layer_id is None or not (1 <= layer_id <= max_layer_available):
            continue
        entry(layer_id)['failed'] += 1

    # keep L1..Lmax contiguous (an empty routing layer is still a layer)
    used = sorted(table)
    last = max(used) if used else int(C.INTERFACE_LAYER_ID)
    for layer_id in range(1, max(last, int(C.INTERFACE_LAYER_ID)) + 1):
        entry(layer_id)
    return OrderedDict((key, table[key]) for key in sorted(table))


# ---------------------------------------------------------------------------
# board drawing helpers
# ---------------------------------------------------------------------------
def _port_entries(data):
    """Unique physical port positions of the 640-record input (for orientation)."""
    if data is None:
        return []
    try:
        records = data.records
    except AttributeError:
        return []
    ports = OrderedDict()
    for record in records:
        for which in ('source_endpoint', 'target_endpoint'):
            endpoint = record.get(which)
            if not isinstance(endpoint, dict):
                continue
            key = (endpoint.get('connector'), int(endpoint.get('column', 0)))
            if key in ports:
                continue
            xy = endpoint.get('xy') or [0.0, 0.0]
            ports[key] = dict(connector=endpoint.get('connector'),
                              side=endpoint.get('side'),
                              column=int(endpoint.get('column', 0)),
                              x=float(xy[0]), y=float(xy[1]))
    return list(ports.values())


def _draw_board(ax, port_entries, title=None, pad_mm=BOARD_PAD_MM,
                grid_mm=25.0):
    """True-scale 150 x 150 mm board frame + 25 mm grid + port markers."""
    from matplotlib.patches import Rectangle
    ax.add_patch(Rectangle((0.0, 0.0), BOARD_MM, BOARD_MM, fill=False,
                           edgecolor='#111111', linewidth=1.2, zorder=6))
    for value in np.arange(0.0, BOARD_MM + 1e-9, grid_mm):
        ax.axvline(value, color='#e2e2e2', linewidth=0.35, zorder=0)
        ax.axhline(value, color='#e2e2e2', linewidth=0.35, zorder=0)
    if port_entries:
        xs = [entry['x'] for entry in port_entries]
        ys = [entry['y'] for entry in port_entries]
        ax.scatter(xs, ys, s=3.0, c='#37474f', marker='o', linewidths=0,
                   zorder=7, alpha=0.85)
        seen = set()
        for entry in port_entries:
            connector = entry['connector']
            if connector in seen:
                continue
            seen.add(connector)
            side = entry['side']
            if side == 'N':
                ax.text(entry['x'], BOARD_MM + 1.6, connector, ha='center',
                        va='bottom', fontsize=4.4, color='#455a64', zorder=7, clip_on=True)
            elif side == 'S':
                ax.text(entry['x'], -1.6, connector, ha='center', va='top',
                        fontsize=4.4, color='#455a64', zorder=7, clip_on=True)
            elif side == 'E':
                ax.text(BOARD_MM + 1.6, entry['y'], connector, ha='left',
                        va='center', fontsize=4.4, color='#455a64', zorder=7, clip_on=True)
            elif side == 'W':
                ax.text(-1.6, entry['y'], connector, ha='right', va='center',
                        fontsize=4.4, color='#455a64', zorder=7, clip_on=True)
    ax.set_xlim(-pad_mm, BOARD_MM + pad_mm)
    ax.set_ylim(-pad_mm, BOARD_MM + pad_mm)
    ax.set_aspect('equal')
    ax.set_xlabel('x (mm)')
    ax.set_ylabel('y (mm)')
    ax.set_xticks([0, 25, 50, 75, 100, 125, 150])
    ax.set_yticks([0, 25, 50, 75, 100, 125, 150])
    if title:
        ax.set_title(title, fontsize=9.0)


def _annotate_radius(ax, arc, label='R = 15.0 mm'):
    """Draw the radius of one real R15 arc as a geometric reference."""
    try:
        center = np.asarray(arc['center'], dtype=float)
        p0 = np.asarray(arc['p0'], dtype=float)
        p1 = np.asarray(arc['p1'], dtype=float)
        radius = float(arc.get('radius') or RADIUS_MM)
        start = float(arc.get('start_angle', 0.0))
        sweep = float(arc.get('sweep', 0.0))
        angle = start + sweep / 2.0
        middle = center + radius * np.array([math.cos(angle), math.sin(angle)])
    except (KeyError, TypeError, ValueError):
        return False
    ax.plot([center[0], middle[0]], [center[1], middle[1]], color='#212121',
            linewidth=0.8, linestyle=(0, (2, 2)), zorder=8)
    ax.plot([center[0]], [center[1]], marker='+', markersize=4.0,
            color='#212121', zorder=8)
    ax.annotate(label, xy=(middle[0], middle[1]),
                xytext=(middle[0] + 4.0, middle[1] + 4.0), fontsize=6.2,
                color='#212121', zorder=9,
                arrowprops=dict(arrowstyle='-', linewidth=0.6,
                                color='#212121'))
    return True


def _exaggeration_note(linewidth_pt):
    factor = (float(linewidth_pt) / 72.0 * 25.4) / max(WIDTH_MM, 1e-9)
    return (f'centreline width 0.050 mm drawn ~{factor:.0f}x true width '
            f'for visibility')


def _save(fig, path, log, warnings, rel_base):
    plt = _pyplot()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fig.savefig(path, dpi=DPI)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f'cannot save {path.name}: {exc}')
        plt.close(fig)
        return None
    plt.close(fig)
    try:
        relative = str(path.relative_to(Path(rel_base))).replace('\\', '/')
    except ValueError:
        relative = str(path)
    log(f'[plots] wrote {relative}')
    return path


def _lw_for_count(count):
    if count > 350:
        return 0.5
    if count > 180:
        return 0.65
    if count > 80:
        return 0.85
    return 1.05


def _footnote(fig, text, y=0.010, fontsize=6.4, width=None):
    """Centred, wrapped figure footnote (never clipped horizontally)."""
    import textwrap
    if width is None:
        # ~0.6 em average glyph width: chars that fit one figure width
        width = max(60, int((fig.get_figwidth() - 0.4) * 115.0 / fontsize))
    wrapped = '\n'.join(textwrap.wrap(str(text), width=width))
    fig.text(0.5, y, wrapped, ha='center', va='bottom', fontsize=fontsize,
             color='#37474f',
             bbox=dict(boxstyle='round,pad=0.30', facecolor='#fafafa',
                       edgecolor='#b0bec5', linewidth=0.6, alpha=0.95))
    return wrapped


def _suptitle(fig, text, fontsize=9.8, width=None, y=0.99):
    """Wrapped figure title (the exact strings are long; no clipping)."""
    import textwrap
    if width is None:
        width = max(60, int((fig.get_figwidth() - 0.6) * 115.0 / fontsize))
    wrapped = '\n'.join(textwrap.wrap(str(text), width=width))
    fig.suptitle(wrapped, fontsize=fontsize, y=y)
    return wrapped


def _layer_plane_counts(routes, layer_id, z_mm):
    """Routes having a flat part on (layer_id, exact z)."""
    count = 0
    for route in routes:
        for part in _flat_parts(route, layer_id):
            z = _as_float(part.get('z_mm'))
            if z is not None and abs(z - z_mm) <= 1e-9:
                count += 1
                break
    return count


# ---------------------------------------------------------------------------
# 1) per-layer 2D maps
# ---------------------------------------------------------------------------
def _collect_layer_entries(routes, layer_id, z_mm=None):
    """``[(route, part, points, z)]`` of the flat parts drawn on one plane."""
    entries = []
    for route in routes:
        if not _is_routed(route):
            continue
        for part in _flat_parts(route, layer_id):
            z = _as_float(part.get('z_mm'))
            if z is None:
                continue
            if z_mm is not None and abs(z - z_mm) > 1e-9:
                continue
            points = _sample_flat(part)
            if points is None:
                continue
            entries.append(dict(route=route, part=part, points=points, z=z))
    return entries


def _draw_layer_panel(ax, entries, data, layer_id, z_mm, depth_norm=None,
                      depth_cmap=None):
    """Draw one physical plane of one logical layer; returns style info."""
    port_entries = _port_entries(data)
    _draw_board(ax, port_entries)
    depths = {}
    manual_count = 0
    auto_count = 0
    groups = OrderedDict()
    arc_for_reference = None
    lines = []
    for entry in entries:
        route = entry['route']
        points = entry['points']
        kind, group, color = _group_of(route)
        if kind == 'manual':
            manual_count += 1
        else:
            auto_count += 1
        groups.setdefault((kind, group), color)
        if kind == 'manual' and depth_norm is not None:
            depth = _depth_mm(points, _route_source_xy(route),
                              _record_inward(route))
            if depth is not None:
                depths[id(route)] = depth
                color = depth_cmap(depth_norm(depth))
        lines.append((points, color))
        if arc_for_reference is None:
            for primitive in entry['part'].get('primitives') or []:
                if primitive.get('kind') == 'arc':
                    arc_for_reference = primitive
                    break
    linewidth = _lw_for_count(len(entries))
    uids = {entry['route'].get('uid') for entry in entries}
    manual_uids = {entry['route'].get('uid') for entry in entries
                   if entry['route'].get('assignment') == 'manual_fixed_u'}
    for points, color in lines:
        ax.plot(points[:, 0], points[:, 1], color=color, linewidth=linewidth,
                alpha=0.92, solid_capstyle='round', zorder=4)
    # light-grey dashed projection of the elevation transitions leaving this plane
    for entry in entries:
        route = entry['route']
        for transition in _transition_parts(route):
            try:
                start = transition.get('start')
                end = transition.get('end')
                z0 = _as_float(transition.get('z0'))
                if start is None or end is None or z0 is None:
                    continue
                if z_mm is not None and abs(z0 - z_mm) > 1e-9:
                    continue
                ax.plot([start[0], end[0]], [start[1], end[1]],
                        color='#455a64', linewidth=0.35, linestyle=(0, (1, 2)),
                        alpha=0.30, zorder=2)
            except (TypeError, ValueError, IndexError):
                continue
    if arc_for_reference is not None:
        _annotate_radius(ax, arc_for_reference)
    info = dict(entries=len(entries), routes=len(uids),
                manual=len(manual_uids),
                automatic=len(uids) - len(manual_uids),
                linewidth=linewidth, depths=depths, groups=groups)
    return info


def render_layer_2d(routes, data, layer_id, out_dir, log, warnings):
    """One PNG for one logical layer (L1 gets its two interface planes)."""
    plt = _pyplot()
    layer_id = int(layer_id)
    routed = [route for route in routes if _is_routed(route)]
    failed_count = sum(1 for route in routes
                       if route.get('status') == 'failed'
                       and _route_layer(route) == layer_id)
    if layer_id == C.INTERFACE_LAYER_ID:
        z_values = [float(C.Z1_MM), float(C.Z2_MM)]
    else:
        z_values = [float(C.layer_z(layer_id))]
    planes = [(_layer_plane_counts(routed, layer_id, z), z) for z in z_values]
    automatic = sum(1 for route in routed
                    if route.get('assignment') != 'manual_fixed_u'
                    and _route_layer(route) == layer_id)

    if layer_id == C.INTERFACE_LAYER_ID:
        fig, axes = plt.subplots(1, 2, figsize=FIG_L1)
        plane_info = []
        for index, (count, z) in enumerate(planes):
            entries = _collect_layer_entries(routed, layer_id, z_mm=z)
            info = _draw_layer_panel(axes[index], entries, data, layer_id, z)
            plane_info.append(info)
            plane = 'z1' if abs(z - C.Z1_MM) <= 1e-9 else 'z2'
            axes[index].set_title(
                f'{plane} data-source row (physical z = {z:.3f} mm)\n'
                f'{info["routes"]} routes / {info["entries"]} flat sub-chains '
                f'on this interface plane ({info["manual"]} manual fixed-U, '
                f'{info["automatic"]} automatic)', fontsize=8.6)
            handles = []
            from matplotlib.lines import Line2D
            for (kind, group), color in info['groups'].items():
                handles.append(Line2D([0], [0], color=color, linewidth=1.8,
                                      label=_group_label(kind, group)))
            if handles:
                axes[index].legend(handles=handles, loc='lower right',
                                   fontsize=5.6, framealpha=0.92, ncol=1)
        lw = _lw_for_count(max(count for count, _z in planes))
        _suptitle(
            fig,
            f'L1 interface layer - both physical data-source planes '
            f'(z1 row {C.Z1_MM:.3f} mm / z2 row {C.Z2_MM:.3f} mm) | '
            f'{planes[0][0]} + {planes[1][0]} route-plane occurrences, '
            f'{plane_info[0]["entries"]} + {plane_info[1]["entries"]} flat '
            f'sub-chains | {failed_count} failed records assigned to L1',
            fontsize=9.6)
        _footnote(fig, GEOMETRY_NOTE + '  |  ' + _exaggeration_note(lw))
        fig.subplots_adjust(left=0.05, right=0.985, top=0.86, bottom=0.10,
                            wspace=0.06)
        path = Path(out_dir) / f'{layer_id:02d}_L{layer_id}.png'
        _save(fig, path, log, warnings, out_dir)
        return dict(name=path.name, path=str(path), kind='layer_2d_interface',
                    layer_id=layer_id, planes=[count for count, _z in planes],
                    failed=failed_count)

    # ---- one routing layer panel -----------------------------------------
    entries = _collect_layer_entries(routed, layer_id, z_mm=z_values[0])
    fig, ax = plt.subplots(figsize=FIG_2D)
    manual_entries = [entry for entry in entries
                      if entry['route'].get('assignment') == 'manual_fixed_u']
    depth_norm = None
    depth_cmap = None
    depth_range = None
    if manual_entries:
        from matplotlib.colors import Normalize
        depths = []
        for entry in manual_entries:
            depth = _depth_mm(entry['points'], _route_source_xy(entry['route']),
                              _record_inward(entry['route']))
            if depth is not None:
                depths.append(depth)
        if depths:
            low, high = min(depths), max(depths)
            if high - low <= 1e-9:
                high = low + 1.0
            depth_norm = Normalize(vmin=low, vmax=high)
            depth_cmap = plt.get_cmap('viridis')
    info = _draw_layer_panel(ax, entries, data, layer_id, z_values[0],
                             depth_norm=depth_norm, depth_cmap=depth_cmap)
    from matplotlib.lines import Line2D
    handles = []
    for (kind, group), color in info['groups'].items():
        if kind == 'manual' and depth_norm is not None:
            continue
        handles.append(Line2D([0], [0], color=color, linewidth=1.8,
                              label=_group_label(kind, group)))
    if depth_norm is not None:
        from matplotlib.cm import ScalarMappable
        scalar = ScalarMappable(norm=depth_norm, cmap=depth_cmap)
        cax = fig.add_axes([0.905, 0.20, 0.014, 0.42])
        colorbar = fig.colorbar(scalar, cax=cax)
        colorbar.set_label('manual fixed-U depth (mm)', fontsize=7.5)
        colorbar.ax.tick_params(labelsize=6.5)
        depth_range = (round(depth_norm.vmin, 3), round(depth_norm.vmax, 3))
        handles.append(Line2D([0], [0], color='#455a64', linewidth=1.8,
                              label=f'manual U routes (colour = depth '
                                    f'{depth_range[0]:.1f}-{depth_range[1]:.1f} mm)'))
    if handles:
        ax.legend(handles=handles, loc='upper left', fontsize=6.0,
                  framealpha=0.92)
    z = z_values[0]
    _suptitle(
        fig,
        f'L{layer_id} routing layer | physical z = {z:.3f} mm '
        f'(layer pitch {C.LAYER_PITCH_MM:.2f} mm above L2 = '
        f'{C.BASE_ROUTING_Z_MM:.2f} mm) | {info["routes"]} routed routes '
        f'({info["manual"]} manual / {info["automatic"]} automatic) | '
        f'{failed_count} failed records assigned to this layer',
        fontsize=9.4)
    _footnote(fig, GEOMETRY_NOTE + '  |  ' + _exaggeration_note(info['linewidth']))
    if depth_norm is not None:
        fig.subplots_adjust(left=0.09, right=0.88, top=0.865, bottom=0.145)
    else:
        fig.subplots_adjust(left=0.09, right=0.985, top=0.865, bottom=0.145)
    path = Path(out_dir) / f'{layer_id:02d}_L{layer_id}.png'
    _save(fig, path, log, warnings, out_dir)
    return dict(name=path.name, path=str(path), kind='layer_2d', layer_id=layer_id,
                routes=info['routes'], manual=info['manual'],
                automatic=info['automatic'], failed=failed_count,
                depth_mm=depth_range)


# ---------------------------------------------------------------------------
# 2) all-layer XY overlay (single top view)
# ---------------------------------------------------------------------------
def render_all_layers_xy(routes, data, out_dir, log, warnings):
    plt = _pyplot()
    from matplotlib.collections import LineCollection
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import Normalize
    routed = [route for route in routes if _is_routed(route)]
    entries = []
    for route in routed:
        for part in _flat_parts(route):
            points = _sample_flat(part)
            z = _as_float(part.get('z_mm'))
            if points is None or z is None:
                continue
            entries.append((points, z))
    if not entries:
        warnings.append('all-layer XY overlay skipped: no flat geometry')
        return None
    heights = sorted({round(z, 6) for _points, z in entries})
    norm = Normalize(vmin=min(heights), vmax=max(heights) if len(heights) > 1
                     else min(heights) + 1.0)
    cmap = plt.get_cmap('plasma')
    fig, ax = plt.subplots(figsize=(9.6, 9.0))
    _draw_board(ax, _port_entries(data))
    segments = [points for points, _z in entries]
    colors = [cmap(norm(z)) for _points, z in entries]
    ax.add_collection(LineCollection(segments, colors=colors, linewidths=0.45,
                                     alpha=0.75, zorder=3))
    scalar = ScalarMappable(norm=norm, cmap=cmap)
    colorbar = fig.colorbar(scalar, ax=ax, fraction=0.035, pad=0.02)
    colorbar.set_label('physical z (mm)', fontsize=8.0)
    ticks = []
    labels = []
    for layer_id in range(1, int(C.MAX_LOGICAL_LAYERS) + 1):
        if layer_id == C.INTERFACE_LAYER_ID:
            for plane in ('z1', 'z2'):
                ticks.append(float(C.PLANE_Z_MM[plane]))
                labels.append(f'L1 {plane} {float(C.PLANE_Z_MM[plane]):.2f}')
        else:
            ticks.append(float(C.layer_z(layer_id)))
            labels.append(f'L{layer_id} {C.layer_z(layer_id):.2f}')
    colorbar.set_ticks([tick for tick in ticks
                        if norm.vmin - 1e-9 <= tick <= norm.vmax + 1e-9])
    colorbar.ax.set_yticklabels([label for tick, label in zip(ticks, labels)
                                 if norm.vmin - 1e-9 <= tick <= norm.vmax + 1e-9],
                                fontsize=5.6)
    _suptitle(
        fig,
        f'All used layers in one XY top view | {len(entries)} flat sub-chains '
        f'from {len(routed)} routed routes | colour = physical z '
        f'({norm.vmin:.3f}-{norm.vmax:.3f} mm) | true 150 x 150 mm board scale',
        fontsize=9.5)
    _footnote(fig, GEOMETRY_NOTE)
    fig.subplots_adjust(left=0.08, right=0.90, top=0.915, bottom=0.13)
    path = Path(out_dir) / '00_all_layers_xy.png'
    _save(fig, path, log, warnings, out_dir)
    return dict(name=path.name, path=str(path), kind='all_layers_xy',
                flat_parts=len(entries), planes=len(heights))


# ---------------------------------------------------------------------------
# 3) true-3D overview
# ---------------------------------------------------------------------------
def _plane_label(z_mm, layer_table):
    for layer_id, item in layer_table.items():
        for height in item['z_mm']:
            if abs(float(height) - float(z_mm)) <= 1e-9:
                if layer_id == C.INTERFACE_LAYER_ID:
                    plane = 'z1' if abs(z_mm - C.Z1_MM) <= 1e-9 else 'z2'
                    return f'L1 {plane}'
                return f'L{layer_id}'
    return f'z={z_mm:.2f}'


def _plane_heights(routes):
    heights = set()
    for route in routes:
        if not _is_routed(route):
            continue
        for part in _flat_parts(route):
            z = _as_float(part.get('z_mm'))
            if z is not None:
                heights.add(round(z, 6))
    return sorted(heights)


def _setup_3d_axes(ax, heights, z_mm_min, z_mm_max):
    ax.set_xlim(-BOARD_PAD_MM, BOARD_MM + BOARD_PAD_MM)
    ax.set_ylim(-BOARD_PAD_MM, BOARD_MM + BOARD_PAD_MM)
    span = max(z_mm_max - z_mm_min, 1e-6)
    z_pad = 0.15 * span
    ax.set_zlim(z_mm_min - z_pad, z_mm_max + z_pad)
    z_aspect = 0.40
    ax.set_box_aspect((1.0, 1.0, z_aspect))
    horizontal = 1.0 / float(BOARD_MM + 2.0 * BOARD_PAD_MM)
    vertical = z_aspect / float(span + 2.0 * z_pad)
    exaggeration = vertical / horizontal
    ax.set_xticks([0, 50, 100, 150])
    ax.set_yticks([0, 50, 100, 150])
    ax.set_xlabel('x (mm)')
    ax.set_ylabel('y (mm)')
    ax.set_zlabel('physical z (mm)')
    ax.tick_params(axis='z', pad=1.5, labelsize=6.4)
    return float(exaggeration)


def _collect_3d_segments(routes, log, warnings):
    """Segments + per-segment colour values of every routed route in real 3D."""
    segments = []
    segment_z = []
    kinds = []
    plane_counts = Counter()
    skipped = 0
    for route in routes:
        if not _is_routed(route):
            continue
        chunks = _route_chunks_3d(route)
        if not chunks:
            skipped += 1
            continue
        for chunk in chunks:
            points = chunk['points']
            if len(points) < 2:
                continue
            seg = np.stack([points[:-1], points[1:]], axis=1)
            segments.append(seg)
            if chunk['kind'] == 'transition':
                segment_z.append(np.full(len(seg), np.nan))
                kinds.append(np.zeros(len(seg), dtype=np.int8))
            else:
                segment_z.append(np.full(len(seg), chunk['z_mm']))
                kinds.append(np.ones(len(seg), dtype=np.int8))
                plane_counts[round(chunk['z_mm'], 6)] += 1
    if skipped:
        warnings.append(f'3D overview: {skipped} routed records had no usable '
                        f'geometry')
    if not segments:
        return None
    return dict(segments=np.concatenate(segments, axis=0),
                z_values=np.concatenate(segment_z, axis=0),
                flat_mask=np.concatenate(kinds, axis=0) == 1,
                plane_counts=plane_counts,
                routes=sum(1 for route in routes if _is_routed(route)))


def render_3d_overview(routes, stack, out_dir, log, warnings):
    plt = _pyplot()
    from mpl_toolkits.mplot3d.art3d import Line3DCollection
    from matplotlib.lines import Line2D
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import Normalize
    routed = [route for route in routes if _is_routed(route)]
    data3d = _collect_3d_segments(routes, log, warnings)
    if data3d is None:
        warnings.append('3d_overview skipped: no 3D geometry')
        return None
    heights = _plane_heights(routes)
    if not heights:
        heights = [float(C.Z1_MM), float(C.Z2_MM)]
    norm = Normalize(vmin=min(heights),
                     vmax=max(heights) if len(heights) > 1 else min(heights) + 1.0)
    cmap = plt.get_cmap('plasma')
    segment_z = data3d['z_values']
    flat_mask = data3d['flat_mask']
    colors = np.empty((len(segment_z), 4), dtype=float)
    colors[flat_mask] = cmap(norm(segment_z[flat_mask]))
    colors[~flat_mask] = np.array(_hex_to_rgba(TRANSITION_COLOR))
    fig = plt.figure(figsize=FIG_3D)
    ax = fig.add_subplot(111, projection='3d')
    ax.set_position([-0.02, -0.10, 1.00, 1.18])
    collection = Line3DCollection(data3d['segments'].tolist(), colors=colors,
                                 linewidths=0.30, alpha=0.55)
    ax.add_collection3d(collection)
    layer_table = _layer_table(routes, stack, [])
    exaggeration = _setup_3d_axes(ax, heights, min(heights), max(heights))
    ticks = heights
    tick_fontsize = 5.4 if len(ticks) <= 10 else 4.7
    tick_labels = [f'{_plane_label(z, layer_table)} {z:.2f}' for z in ticks]
    ax.set_zticks(ticks)
    ax.set_zticklabels(tick_labels, fontsize=tick_fontsize)
    handles = []
    for z in heights:
        handles.append(Line2D([0], [0], color=cmap(norm(z)), linewidth=2.0,
                              label=f'{_plane_label(z, layer_table)} = '
                                    f'{z:.3f} mm'))
    handles.append(Line2D([0], [0], color=TRANSITION_COLOR, linewidth=2.0,
                          linestyle='-',
                          label='elevation S-curve transition (R = 15 mm)'))
    legend_fontsize = 6.0 if len(handles) <= 10 else 5.2
    fig.legend(handles=handles, loc='lower center',
               bbox_to_anchor=(0.47, 0.004), fontsize=legend_fontsize,
               ncol=min(7, len(handles)), framealpha=0.92)
    scalar = ScalarMappable(norm=norm, cmap=cmap)
    cax = fig.add_axes([0.905, 0.16, 0.010, 0.50])
    colorbar = fig.colorbar(scalar, cax=cax)
    colorbar.set_label('physical z (mm) of flat runs', fontsize=7.5)
    colorbar.set_ticks(ticks)
    colorbar.ax.set_yticklabels(tick_labels, fontsize=tick_fontsize)
    used_layers = sorted({_route_layer(route) for route in routed
                          if _route_layer(route) is not None})
    layer_text = ', '.join(f'L{layer}' for layer in used_layers)
    _suptitle(
        fig,
        f'True-3D layout of {data3d["routes"]} routed routes on '
        f'{len(heights)} physical planes | logical layers {layer_text}\n'
        f'flat runs at their stored physical z; every elevation transition is '
        f'the real two-arc R = 15 mm S-curve | z axis exaggerated '
        f'~{exaggeration:.0f}x for display | board 150 x 150 mm',
        fontsize=9.8)
    ax.set_position([-0.03, 0.02, 0.94, 1.12])
    path = Path(out_dir) / '3d_overview.png'
    _save(fig, path, log, warnings, out_dir)
    return dict(name=path.name, path=str(path), kind='3d_overview',
                routes=data3d['routes'], physical_planes=len(heights),
                z_exaggeration=round(exaggeration, 1))


def _hex_to_rgba(color):
    color = color.lstrip('#')
    return tuple(int(color[index:index + 2], 16) / 255.0
                 for index in (0, 2, 4)) + (1.0,)


# ---------------------------------------------------------------------------
# 4) side view (real 3D projections)
# ---------------------------------------------------------------------------
def render_3d_side_view(routes, stack, out_dir, log, warnings):
    plt = _pyplot()
    from matplotlib.collections import LineCollection
    from matplotlib.colors import Normalize
    routed = [route for route in routes if _is_routed(route)]
    chunks_all = []
    for route in routed:
        chunks_all.extend(_route_chunks_3d(route))
    if not chunks_all:
        warnings.append('3d_side_view skipped: no 3D geometry')
        return None
    heights = _plane_heights(routes)
    if not heights:
        heights = [float(C.Z1_MM), float(C.Z2_MM)]
    norm = Normalize(vmin=min(heights),
                     vmax=max(heights) if len(heights) > 1 else min(heights) + 1.0)
    cmap = plt.get_cmap('plasma')
    layer_table = _layer_table(routes, stack, [])
    fig, (ax_yz, ax_xz) = plt.subplots(1, 2, figsize=FIG_SIDE, sharey=True)
    collections = {'x': ([], []), 'y': ([], [])}   # view -> (segments, colors)
    for chunk in chunks_all:
        points = chunk['points']
        if len(points) < 2:
            continue
        seg = np.stack([points[:-1], points[1:]], axis=1)
        if chunk['kind'] == 'transition':
            color = _hex_to_rgba(TRANSITION_COLOR)
        else:
            color = cmap(norm(chunk['z_mm']))
        # side view along x: the (y, z) plane; side view along y: the (x, z) plane
        collections['x'][0].append(seg[:, :, [1, 2]])
        collections['x'][1].append(np.tile(color, (len(seg), 1)))
        collections['y'][0].append(seg[:, :, [0, 2]])
        collections['y'][1].append(np.tile(color, (len(seg), 1)))
    for axis, key, label in ((ax_yz, 'x', 'side view along x  (y-z projection)'),
                             (ax_xz, 'y', 'side view along y  (x-z projection)')):
        segments = np.concatenate(collections[key][0], axis=0)
        colors = np.concatenate(collections[key][1], axis=0)
        axis.add_collection(LineCollection(segments, colors=colors,
                                           linewidths=0.25, alpha=0.35,
                                           zorder=2))
        for z in heights:
            axis.axhline(z, color='#90a4ae', linewidth=0.6,
                         linestyle=(0, (4, 3)), zorder=1)
            axis.text(-BOARD_PAD_MM + 1.0, z + 0.012 * (heights[-1] - heights[0]),
                      f'{_plane_label(z, layer_table)} {z:.2f}',
                      fontsize=5.2, va='bottom', ha='left', color='#455a64',
                      zorder=5,
                      bbox=dict(boxstyle='round,pad=0.05', facecolor='white',
                                alpha=0.7, edgecolor='none'))
        axis.set_xlim(-BOARD_PAD_MM, BOARD_MM + BOARD_PAD_MM)
        z_span = heights[-1] - heights[0]
        z_pad = max(0.08, 0.18 * z_span)
        axis.set_ylim(heights[0] - z_pad, heights[-1] + z_pad)
        axis.set_xlabel('y (mm)' if key == 'x' else 'x (mm)')
        axis.set_ylabel('physical z (mm)')
        axis.set_title(label, fontsize=9.0)
        axis.grid(alpha=0.20, linewidth=0.4)
    ax_yz.set_position([0.06, 0.13, 0.405, 0.72])
    ax_xz.set_position([0.545, 0.13, 0.405, 0.72])
    _suptitle(
        fig,
        f'Side view of the true-3D layout: {len(routed)} routed routes | '
        f'orthogonal projections of the real 3D samples (flat runs + R = 15 mm '
        f'elevation S-curves) | {len(heights)} physical planes '
        f'({heights[0]:.3f}-{heights[-1]:.3f} mm)',
        fontsize=9.6)
    _footnote(fig, 'Every line is a projection of a real 3D path sample: flat '
                   'runs sit exactly on their layer height, transitions climb '
                   'the 0.15 mm layer pitch.  z axis is compressed for display; '
                   'colour = physical z, orange = elevation transitions.',
              fontsize=6.4)
    path = Path(out_dir) / '3d_side_view.png'
    _save(fig, path, log, warnings, out_dir)
    return dict(name=path.name, path=str(path), kind='3d_side_view',
                routes=len(routed), physical_planes=len(heights))


# ---------------------------------------------------------------------------
# 5) layer profile (heights + counts)
# ---------------------------------------------------------------------------
def render_layer_profile(routes, stack, out_dir, log, warnings):
    plt = _pyplot()
    layer_table = _layer_table(routes, stack, [])
    if not layer_table:
        warnings.append('layer_profile skipped: no layers')
        return None
    fig, (ax_bar, ax_z) = plt.subplots(
        1, 2, figsize=FIG_PROFILE, gridspec_kw={'width_ratios': [1.55, 1.0]})
    layers = list(layer_table.keys())
    positions = np.arange(len(layers))
    manual = [layer_table[layer]['manual'] for layer in layers]
    automatic = [layer_table[layer]['automatic'] for layer in layers]
    failed = [layer_table[layer]['failed'] for layer in layers]
    ax_bar.bar(positions, manual, width=0.62, color='#1565c0',
               edgecolor='#0d47a1', linewidth=0.4,
               label='manual fixed-U routed (L1-L6)')
    ax_bar.bar(positions, automatic, width=0.62, bottom=manual,
               color='#2e7d32', edgecolor='#1b5e20', linewidth=0.4,
               label='automatic routed (L7+)')
    ax_bar.bar(positions, failed, width=0.62,
               bottom=[m + a for m, a in zip(manual, automatic)],
               color='#bdbdbd', hatch='///', edgecolor='#616161',
               linewidth=0.4, label='failed records assigned to this layer')
    for index, layer in enumerate(layers):
        total = manual[index] + automatic[index] + failed[index]
        if total:
            ax_bar.text(index, total + 1.5, str(total), ha='center',
                        va='bottom', fontsize=6.8)
    ax_bar.set_xticks(positions)
    ax_bar.set_xticklabels(
        [f'L{layer}\n' + ('/'.join(f'{z:.2f}' for z in item['z_mm'])
                          if item['layer_type'] == 'interface'
                          else f'{item["z_mm"][0]:.2f}')
         for layer, item in layer_table.items()], fontsize=6.4)
    ax_bar.set_ylabel('routes using the layer')
    ax_bar.grid(True, axis='y', alpha=0.25, linewidth=0.5)
    ax_bar.legend(fontsize=6.4, loc='upper right', framealpha=0.92)
    routed_total = sum(manual) + sum(automatic)
    max_total = max([m + a + f for m, a, f in zip(manual, automatic, failed)]
                    or [1])
    ax_bar.set_ylim(0.0, max_total * 1.22 + 2.0)
    ax_bar.set_title(
        'Using-layer occurrences per logical layer\n'
        f'(a lifted route is drawn on L1 and on its routing layer) | '
        f'{routed_total} occurrences from {len(routes)} records, '
        f'{sum(failed)} failed assigned', fontsize=8.2)
    # ---- physical z ladder ----------------------------------------------
    for layer, item in layer_table.items():
        if item['layer_type'] == 'interface':
            for plane, z in (('z1', C.Z1_MM), ('z2', C.Z2_MM)):
                ax_z.plot([0.0, 1.0], [z, z], color=PLANE_COLORS[plane],
                          linewidth=1.6)
                ax_z.text(0.02, z, f' L1 {plane} row  z = {z:.3f} mm  '
                                   f'(interface)', fontsize=6.8,
                          va='bottom', color=PLANE_COLORS[plane])
            continue
        z = item['z_mm'][0]
        ax_z.plot([0.0, 1.0], [z, z], color='#6a1b9a', linewidth=1.2,
                  linestyle='-')
        ax_z.text(0.02, z, f' L{layer}  z = {z:.3f} mm  '
                           f'({item["routed"]} routed)', fontsize=6.6,
                  va='bottom', color='#4a148c')
    z_values = list(C.PLANE_Z_MM.values()) + [
        item['z_mm'][0] for item in layer_table.values()
        if item['layer_type'] != 'interface']
    z_low, z_high = min(z_values), max(z_values)
    pad = 0.12 * max(z_high - z_low, 0.1)
    ax_z.set_ylim(z_low - pad, z_high + pad)
    ax_z.set_xlim(0.0, 1.0)
    ax_z.set_xticks([])
    ax_z.set_ylabel('physical z (mm)')
    ax_z.grid(True, axis='y', alpha=0.25, linewidth=0.5)
    ax_z.set_title(
        'Physical layer stack\n'
        f'interface planes + '
        f'{sum(1 for item in layer_table.values() if item["layer_type"] != "interface")} '
        f'routing planes at {C.LAYER_PITCH_MM:.2f} mm pitch', fontsize=8.2)
    _suptitle(
        fig,
        f'Layer profile: {len(layer_table)} logical layers | '
        f'{len({round(z, 6) for item in layer_table.values() for z in item["z_mm"]})} '
        f'physical planes | L1 = interface layer (two rows z1 = {C.Z1_MM:.2f} / '
        f'z2 = {C.Z2_MM:.2f} mm), L2 = {C.BASE_ROUTING_Z_MM:.2f} mm',
        fontsize=9.4)
    _footnote(fig, 'Layer heights: 0.15 mm pitch above z2 = 0.5 mm (existing '
                   'c4 / manual_c4 150 um multilayer configuration); '
                   'provenance unconfirmed_simulation.', fontsize=6.4)
    fig.subplots_adjust(left=0.07, right=0.985, top=0.82, bottom=0.19,
                        wspace=0.45)
    path = Path(out_dir) / 'layer_profile.png'
    _save(fig, path, log, warnings, out_dir)
    return dict(name=path.name, path=str(path), kind='layer_profile',
                logical_layers=len(layer_table),
                physical_planes=len({round(z, 6)
                                     for item in layer_table.values()
                                     for z in item['z_mm']}))


# ---------------------------------------------------------------------------
# 6) U nesting zoom
# ---------------------------------------------------------------------------
def _pick_nesting_scope(routes):
    """Logical layer + board side with the most manual fixed-U flat routes."""
    manual = [route for route in routes
              if _is_routed(route)
              and route.get('assignment') == 'manual_fixed_u']
    if not manual:
        return None, None, []
    layer_counts = Counter()
    for route in manual:
        for layer_id in {int(part.get('layer_id'))
                         for part in _flat_parts(route)
                         if part.get('layer_id') is not None}:
            layer_counts[layer_id] += 1
    candidates = [(count, layer_id) for layer_id, count in layer_counts.items()
                  if layer_id >= 2]
    if candidates:
        layer_id = max(candidates, key=lambda item: (item[0], -item[1]))[1]
    else:
        layer_id = C.INTERFACE_LAYER_ID
    scoped = [route for route in manual
              if any(int(part.get('layer_id')) == layer_id
                     for part in _flat_parts(route))]
    side_counts = Counter(route.get('source_side') for route in scoped)
    if not side_counts:
        return layer_id, None, []
    side = side_counts.most_common(1)[0][0]
    selected = [route for route in scoped if route.get('source_side') == side]
    return layer_id, side, selected


def render_u_nesting_zoom(routes, data, out_dir, log, warnings):
    plt = _pyplot()
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import Normalize
    layer_id, side, selected = _pick_nesting_scope(routes)
    if not selected:
        warnings.append('u_nesting_zoom skipped: no manual fixed-U routes')
        return None
    entries = []
    points_list = []
    for route in selected:
        for part in _flat_parts(route, layer_id):
            points = _sample_flat(part)
            if points is None:
                continue
            depth = _depth_mm(points, _route_source_xy(route),
                              _record_inward(route))
            if depth is None:
                continue
            points_list.append(points)
            entries.append(dict(route=route, part=part, points=points,
                                depth=depth))
    if not entries:
        warnings.append('u_nesting_zoom skipped: no usable flat geometry')
        return None
    depths = [entry['depth'] for entry in entries]
    low, high = min(depths), max(depths)
    if high - low <= 1e-9:
        high = low + 1.0
    norm = Normalize(vmin=low, vmax=high)
    cmap = plt.get_cmap('viridis')
    all_points = np.concatenate(points_list, axis=0)
    x_min, x_max = float(all_points[:, 0].min()), float(all_points[:, 0].max())
    y_min, y_max = float(all_points[:, 1].min()), float(all_points[:, 1].max())
    if side in ('N', 'S'):
        x_lo = max(-BOARD_PAD_MM, min(x_min, 0.0) - 10.0)
        x_hi = min(BOARD_MM + 4.0, max(x_max, BOARD_MM) + 6.0)
        y_lo = max(-BOARD_PAD_MM, y_min - 10.0)
        y_hi = min(BOARD_MM + 6.0, max(y_max, BOARD_MM) + 8.0)
    else:
        x_lo = max(-BOARD_PAD_MM, min(x_min, 0.0) - 12.0)
        x_hi = min(BOARD_MM + 6.0, max(x_max, BOARD_MM) + 8.0)
        y_lo = max(-BOARD_PAD_MM, min(y_min, 0.0) - 10.0)
        y_hi = min(BOARD_MM + 6.0, max(y_max, BOARD_MM) + 6.0)
    x_range = max(x_hi - x_lo, 10.0)
    y_range = max(y_hi - y_lo, 10.0)
    base_width = 11.6
    # size the figure so the equal-aspect board fills its axes box (no bands)
    base_height = max(3.8, min(9.6, (base_width * 0.80 * y_range / x_range)
                               / 0.705 + 0.65))
    fig, ax = plt.subplots(figsize=(base_width, base_height))
    _draw_board(ax, _port_entries(data))
    for entry in entries:
        points = entry['points']
        ax.plot(points[:, 0], points[:, 1], color=cmap(norm(entry['depth'])),
                linewidth=1.3, alpha=0.95, solid_capstyle='round', zorder=4)
        apex_index = int(np.argmax(
            (points[:, :2] - np.asarray(_route_source_xy(entry['route']), float))
            @ np.asarray(_record_inward(entry['route']), float)))
        entry['apex'] = points[apex_index, :2]
    # annotate the deepest few distinct U turns with their real depth
    labelled = []
    depth_span = max(high - low, 1.0)
    for entry in sorted(entries, key=lambda item: -item['depth']):
        if any(abs(entry['depth'] - value) < 0.4 for value in labelled):
            continue
        rank = len(labelled)
        labelled.append(entry['depth'])
        offset_x = (4.0, -10.0)[rank % 2]
        offset_y = ((0.06 + 0.10 * rank) * depth_span) * (
            1.0 if side in ('N',) else -1.0)
        ax.annotate(f'd = {entry["depth"]:.1f} mm',
                    xy=(entry['apex'][0], entry['apex'][1]),
                    xytext=(entry['apex'][0] + offset_x,
                            entry['apex'][1] + offset_y),
                    fontsize=6.2, color='#1a237e', zorder=9,
                    arrowprops=dict(arrowstyle='-', linewidth=0.5,
                                    color='#1a237e'),
                    bbox=dict(boxstyle='round,pad=0.12', facecolor='white',
                              alpha=0.78, edgecolor='none'))
        if len(labelled) >= 5:
            break
    ax.set_xlim(x_lo, x_hi)
    ax.set_ylim(y_lo, y_hi)
    ax.set_aspect('equal', adjustable='box')
    scalar = ScalarMappable(norm=norm, cmap=cmap)
    colorbar = fig.colorbar(scalar, ax=ax, fraction=0.035, pad=0.02)
    colorbar.set_label('U penetration depth (mm)', fontsize=7.5)
    colorbar.ax.tick_params(labelsize=6.5)
    physical_z = (float(C.layer_z(layer_id)) if layer_id >= 2
                  else float(C.Z1_MM))
    _suptitle(
        fig,
        f'U nesting zoom: logical layer L{layer_id} '
        f'(physical z = {physical_z:.3f} mm), side {side}, '
        f'{len(entries)} manual fixed-U flat runs\n'
        f'colour = real U depth (max penetration from the interface edge); '
        f'deeper U turns enclose shallower ones at the same layer/side',
        fontsize=9.2)
    _footnote(fig, 'U depth is computed from the stored flat primitives of each '
                   'route (distance of the U apex from the source port plane). '
                   'Bends are exact R = 15 mm arcs. ' + _exaggeration_note(1.3),
              fontsize=6.2)
    fig.subplots_adjust(left=0.08, right=0.90, top=0.86, bottom=0.155)
    path = Path(out_dir) / 'u_nesting_zoom.png'
    _save(fig, path, log, warnings, out_dir)
    return dict(name=path.name, path=str(path), kind='u_nesting_zoom',
                layer_id=layer_id, side=side, routes=len(entries),
                depth_range_mm=[round(low, 3), round(high, 3)])


# ---------------------------------------------------------------------------
# 7) orchestration
# ---------------------------------------------------------------------------
def render_all(routes, stack, data, out_dir, log=print):
    """Render every 2D per-layer and 3D figure; returns a JSON-ready summary.

    Parameters
    ----------
    routes:
        merged 640-record list (routed records with ``parts`` plus failed
        records), a ``{'routes': [...]}`` payload or a ``routes.json`` path.
    stack:
        :class:`four_side_1024.manual_u640.stack.LayerStack` (only
        ``stack.max_layer`` is used).
    data:
        :class:`four_side_1024.manual_u640.inputs.InputData` (only used for the
        port markers / board orientation; may be ``None``).
    out_dir:
        figure directory (``outputs/manual_u640/plots``).
    log:
        injectable logger (``print`` by default).
    """
    started = time.perf_counter()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    warnings = []
    plt = _apply_style(_pyplot())

    records = _normalise_routes(routes, warnings)
    routed = [route for route in records if _is_routed(route)]
    failed = [route for route in records if not _is_routed(route)]
    log(f'[plots] input: {len(records)} records, {len(routed)} routed, '
        f'{len(failed)} failed/empty -> {out_dir}')

    layer_table = _layer_table(records, stack, warnings)
    files = []

    def _run(label, function, *args):
        step_started = time.perf_counter()
        try:
            result = function(*args)
        except Exception as exc:  # noqa: BLE001 - one figure must not kill the run
            warnings.append(f'{label} failed: {type(exc).__name__}: {exc}')
            log(f'[plots] WARNING {label} skipped ({type(exc).__name__}: {exc})')
            return None
        if result is not None:
            files.append(result)
        log(f'[plots] {label} done in {time.perf_counter() - step_started:.2f}s')
        return result

    # per-layer 2D maps (L1..last used layer)
    for layer_id in layer_table:
        _run(f'layer L{layer_id} 2D map', render_layer_2d, records, data,
             layer_id, out_dir, log, warnings)
    # extra figures
    _run('all-layer XY overlay', render_all_layers_xy, records, data, out_dir,
         log, warnings)
    _run('3D overview', render_3d_overview, records, stack, out_dir, log,
         warnings)
    _run('3D side view', render_3d_side_view, records, stack, out_dir, log,
         warnings)
    _run('layer profile', render_layer_profile, records, stack, out_dir, log,
         warnings)
    _run('U nesting zoom', render_u_nesting_zoom, records, data, out_dir, log,
         warnings)

    elapsed = time.perf_counter() - started
    layer_summary = [dict(layer_id=item['layer_id'],
                          layer_label=item['layer_label'],
                          layer_type=item['layer_type'],
                          z_mm=list(item['z_mm']),
                          routed=item['routed'],
                          manual=item['manual'],
                          automatic=item['automatic'],
                          failed=item['failed'])
                     for item in layer_table.values()]
    result = dict(
        schema='four_side_1024_manual_u640_plots_v1',
        out_dir=str(out_dir),
        figure_count=len(files),
        files=files,
        layers=layer_summary,
        counts=dict(records=len(records), routed=len(routed),
                    failed=len(failed), figures=len(files)),
        used_logical_layers=[item['layer_id'] for item in layer_table.values()
                             if item['routed'] > 0],
        elapsed_s=round(elapsed, 2),
        warnings=warnings,
    )
    log(f'[plots] {len(files)} figures in {elapsed:.1f}s, '
        f'{len(warnings)} warning(s)')
    return result


# ---------------------------------------------------------------------------
# CLI (debug helper; the pipeline calls render_all directly)
# ---------------------------------------------------------------------------
def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(
        description='Render the manual_u640 2D per-layer / 3D figures.')
    parser.add_argument('--routes', required=True,
                        help='routes.json (payload or list)')
    parser.add_argument('--out', default='outputs/manual_u640/plots')
    parser.add_argument('--max-layer', type=int, default=C.MAX_LOGICAL_LAYERS)
    args = parser.parse_args(argv)
    from . import inputs as I
    from . import stack as S
    data = I.load_inputs()
    stack = S.LayerStack(args.max_layer)
    result = render_all(args.routes, stack, data, args.out)
    print(json.dumps({key: result[key]
                      for key in ('figure_count', 'counts', 'elapsed_s',
                                  'warnings')}, indent=1, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
