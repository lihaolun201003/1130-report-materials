# -*- coding: utf-8 -*-
"""Export / statistics for the manual-u640 640-channel 3D routing round.

Writes the four result artifacts of ``outputs/manual_u640/`` (CONTRACT.md 搂6):

* ``routes.json``      - all 640 records: the routed records with their full
  ``parts`` 3D geometry plus the failed / missing records with their structured
  failure reason (never dropped, never counted as success);
* ``route_table.csv``  - one row per record with identity, assignment, layer,
  length, bend, clearance / crossing and loss columns (UTF-8-SIG for Excel);
* ``per_layer.csv``    - per logical layer counts, conflicts, crossings, length
  and propagation loss;
* ``statistics.json``  - totals, manual L1-L6 + automatic L7+ group statistics,
  per-layer and per-physical-plane statistics, loss model provenance, pending
  items and failure summary.

Loss model
----------
Only the propagation term is calibrated in the existing project configuration
(``four_side_1024/fslw/config.py``: ``PROPAGATION_LOSS_DB_PER_CM = 0.05``).
Bend loss and crossing loss are declared ``unknown_uncalibrated`` there for this
glass process, so those columns are written as ``pending`` together with a
``loss_status`` that says exactly why.  No number is invented and no legacy
polymer estimate is quoted as a glass truth.

Optional inputs
---------------
``assembled`` (the :func:`four_side_1024.manual_u640.assemble.assemble` return
dict) and ``verification`` (the ``verify.verify_all`` return dict) may be
``None`` (e.g. the ``--reuse-routes`` pipeline mode); the affected columns are
then ``pending`` / computed from the route geometry where that is exact.
A missing ``verification`` never silently becomes a zero conflict count.

Public API
----------
``export_all(routes, data, stack, out_dir, verification=None, assembled=None,
failures=None, log=print) -> dict``
"""
from __future__ import annotations

import csv
import json
import math
import time
from collections import Counter, OrderedDict
from pathlib import Path

from . import config as C

SCHEMA_ROUTES = 'four_side_1024_manual_u640_routes_v1'
SCHEMA_STATISTICS = 'four_side_1024_manual_u640_statistics_v1'
SCHEMA_PER_LAYER_CSV = 'four_side_1024_manual_u640_per_layer_csv_v1'
SCHEMA_ROUTE_TABLE_CSV = 'four_side_1024_manual_u640_route_table_csv_v1'
TOOL = 'four_side_1024.manual_u640.export'
TOTAL_RECORDS = 640

#: columns required by the task statement (order kept; extra columns appended)
ROUTE_TABLE_COLUMNS = [
    'uid', 'original_route_id', 'dataset', 'relation',
    'source_port_id', 'target_port_id',
    'source_x_mm', 'source_y_mm', 'target_x_mm', 'target_y_mm',
    'assignment', 'manual_group',
    'assigned_logical_layer', 'target_layer', 'layer_z_mm',
    'layer_sequence', 'n_transitions',
    'path_length_mm', 'flat_length_mm', 'transition_length_mm',
    'min_bend_radius_mm', 'bend_count',
    'min_clearance_mm', 'crossing_count',
    'propagation_loss_db', 'bend_loss_db', 'crossing_loss_db', 'loss_status',
    'status', 'failure_reason',
]
#: additional traceability columns (allowed by "at least the listed columns")
ROUTE_TABLE_EXTRA_COLUMNS = [
    'route_id', 'plane', 'source_side', 'target_side',
    'source_endpoint_id', 'target_endpoint_id',
    'source_z_mm', 'target_z_mm',
    'layer_z_sequence', 'layer_source', 'csv_assigned_layer',
    'crossing_source', 'verification_violation_count', 'failure_detail',
]

PER_LAYER_COLUMNS = [
    'logical_layer', 'layer_label', 'layer_type', 'physical_z_mm',
    'routes', 'routed', 'manual_routes', 'automatic_routes', 'failed',
    'conflicts', 'crossing_events', 'crossing_pairs',
    'total_length_mm', 'propagation_loss_db', 'conflict_source',
]


# ---------------------------------------------------------------------------
# generic helpers
# ---------------------------------------------------------------------------
def _as_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _json_safe(value):
    """Recursively replace NaN/Inf and numpy scalars so JSON stays strict."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (int, str, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, 'item'):          # numpy scalar
        try:
            return _json_safe(value.item())
        except (TypeError, ValueError):
            return str(value)
    if hasattr(value, 'tolist'):        # numpy array
        try:
            return _json_safe(value.tolist())
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _normalise_records(value, warnings, what='routes'):
    """Accept list / ``{'routes': [...]}`` payload / JSON path -> list of dict."""
    raw = value
    if raw is None:
        return []
    if isinstance(raw, (str, Path)):
        try:
            raw = _load_json(raw)
        except (OSError, json.JSONDecodeError) as exc:
            warnings.append(f'cannot read {what} file {value}: {exc}')
            return []
    if isinstance(raw, dict):
        for key in ('routes', 'all_routes', 'records', 'failures'):
            items = raw.get(key)
            if isinstance(items, list):
                raw = items
                break
        else:
            warnings.append(f'unsupported {what} payload keys: '
                            f'{sorted(raw)[:8]}')
            return []
    if not isinstance(raw, (list, tuple)):
        warnings.append(f'unsupported {what} container: {type(raw).__name__}')
        return []
    return [item for item in raw if isinstance(item, dict)]


def _load_stack(stack):
    if stack is not None:
        return stack
    from . import stack as stack_module
    return stack_module.LayerStack(C.MAX_LOGICAL_LAYERS)


def _load_data(data, warnings):
    if data is not None:
        return data
    try:
        from . import inputs as input_module
        return input_module.load_inputs()
    except Exception as exc:  # noqa: BLE001 - export can still run on routes only
        warnings.append(f'input data unavailable ({type(exc).__name__}: {exc}); '
                        f'route order falls back to the given records')
        return None


# ---------------------------------------------------------------------------
# route queries (same conventions as plots.py / CONTRACT.md 搂2)
# ---------------------------------------------------------------------------
def _iter_parts(route):
    parts = route.get('parts')
    return parts if isinstance(parts, list) else []


def _flat_parts(route):
    return [part for part in _iter_parts(route)
            if isinstance(part, dict) and part.get('kind') == 'flat']


def _transition_parts(route):
    return [part for part in _iter_parts(route)
            if isinstance(part, dict) and part.get('kind') == 'transition']


def _is_routed(route):
    if route.get('status') not in (None, 'routed'):
        return False
    return bool(_flat_parts(route)) or bool(_transition_parts(route))


def _layer_of_z(z_mm, stack):
    z = _as_float(z_mm)
    if z is None:
        return None
    for plane in ('z1', 'z2'):
        if abs(z - float(C.PLANE_Z_MM[plane])) <= 1e-9:
            return int(C.INTERFACE_LAYER_ID)
    for layer_id in stack.routing_layer_ids:
        if abs(z - float(C.layer_z(layer_id))) <= 1e-9:
            return int(layer_id)
    return None


def _route_layer(route, stack):
    for key in ('logical_layer', 'target_layer'):
        value = _as_int(route.get(key))
        if value is not None:
            return value
    for part in _flat_parts(route):
        layer_id = _layer_of_z(part.get('z_mm'), stack)
        if layer_id is not None:
            return layer_id
    return None


def _route_layer_z(route, stack):
    """Physical z of the route's routing layer (L1 -> its own row height)."""
    layer_id = _route_layer(route, stack)
    if layer_id is None:
        layer_id = _layer_of_z(route.get('start_z_mm'), stack)
    if layer_id is None:
        return None
    if layer_id == C.INTERFACE_LAYER_ID:
        z = _as_float(route.get('start_z_mm'))
        if z is None:
            z = _as_float(route.get('source_z_mm'))
        if z is None:
            port = route.get('source_port') or {}
            z = _as_float(port.get('z_mm'))
        return z
    return float(C.layer_z(layer_id))


def _flat_length(route):
    total = 0.0
    for part in _flat_parts(route):
        total += _as_float(part.get('length_mm')) or 0.0
    return total


def _transition_length(route):
    total = 0.0
    for part in _transition_parts(route):
        total += _as_float(part.get('length_mm')) or 0.0
    return total


def _route_length(route):
    value = _as_float(route.get('length_mm'))
    if value is not None:
        return value
    total = 0.0
    for part in _iter_parts(route):
        total += _as_float(part.get('length_mm')) or 0.0
    return total if total > 0.0 else None


def _min_bend_radius(route):
    radii = []
    for part in _iter_parts(route):
        if part.get('kind') == 'flat':
            for primitive in part.get('primitives') or []:
                if primitive.get('kind') == 'arc':
                    radius = _as_float(primitive.get('radius'))
                    if radius is not None:
                        radii.append(radius)
        else:
            radius = _as_float(part.get('radius_mm'))
            if radius is not None:
                radii.append(radius)
    return min(radii) if radii else _as_float(
        route.get('min_bend_radius_mm'))


def _bend_count(route):
    value = _as_int(route.get('bend_count'))
    if value is not None:
        return value
    count = 0
    for part in _iter_parts(route):
        if part.get('kind') == 'flat':
            count += sum(1 for primitive in part.get('primitives') or []
                         if primitive.get('kind') == 'arc')
        else:
            count += 2   # one elevation S-curve = two R15 arcs
    return count


def _layer_sequence(route):
    sequence = route.get('layer_sequence')
    if isinstance(sequence, list) and sequence:
        out = []
        for value in sequence:
            number = _as_int(value)
            if number is not None:
                out.append(number)
        return out
    return []


def _layer_z_sequence(route):
    sequence = route.get('layer_z_sequence')
    if isinstance(sequence, list) and sequence:
        return [value for value in (_as_float(item) for item in sequence)
                if value is not None]
    return []


def _route_uid(route):
    uid = route.get('uid')
    return str(uid) if uid is not None else None


# ---------------------------------------------------------------------------
# verification / assembled extraction (both are optional)
# ---------------------------------------------------------------------------
def _uid_of_key(key):
    if isinstance(key, int):
        return None
    text = str(key)
    return text if ':' in text else None


def _metric(entry, names):
    if isinstance(entry, bool) or entry is None:
        return None
    if isinstance(entry, (int, float)):
        return None
    if not isinstance(entry, dict):
        return None
    for name in names:
        value = entry.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value) if isinstance(value, float) else int(value)
    return None


def _index_by_uid(value):
    """``{uid: dict}`` from a dict/list of per-route metric records."""
    out = {}
    if isinstance(value, dict):
        for key, item in value.items():
            uid = _uid_of_key(key)
            if uid is None:
                continue
            if isinstance(item, dict):
                out[uid] = item
            elif isinstance(item, (int, float)) and not isinstance(item, bool):
                out.setdefault(uid, {})['_number'] = item
    elif isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            uid = _uid_of_key(item.get('uid') or item.get('route_uid') or '')
            if uid is None:
                uid = _uid_of_key(item.get('uid'))
            if uid is None:
                continue
            out[uid] = item
    return out


def _extract_route_metrics(verification):
    """Per-route min clearance / crossing count from the verification dict."""
    metrics = {}
    if not isinstance(verification, dict):
        return metrics
    candidates = []
    for key in ('per_route', 'route_metrics', 'per_route_metrics',
                'route_summary', 'routes'):
        if key in verification:
            candidates.append(verification[key])
    crossings = verification.get('crossings')
    if isinstance(crossings, dict):
        for key in ('per_route', 'route_crossings', 'by_route'):
            if key in crossings:
                candidates.append(crossings[key])
        # a plain ``{uid: count}`` map is accepted as crossing counts
        if any(_uid_of_key(key) for key in crossings):
            candidates.append(crossings)
    for candidate in candidates:
        for uid, item in _index_by_uid(candidate).items():
            slot = metrics.setdefault(uid, {})
            if not isinstance(item, dict):
                continue
            if '_number' in item:
                slot.setdefault('crossing_count', item['_number'])
                continue
            clearance = _metric(item, ('min_clearance_mm', 'min_clearance',
                                       'clearance_mm'))
            crossing = _metric(item, ('crossing_count', 'crossings',
                                      'n_crossings', 'crossing_events'))
            violations = _metric(item, ('violation_count', 'violations',
                                        'world_violations', 'n_violations'))
            if clearance is not None:
                slot['min_clearance_mm'] = clearance
            if crossing is not None:
                slot['crossing_count'] = crossing
            if violations is not None:
                slot['verification_violation_count'] = violations
    return metrics


def _layer_key(value):
    """``1``/``'1'``/``'L1'`` -> 1; ``None``/``'unassigned'`` -> None."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = int(value)
        return number if 1 <= number <= C.MAX_LOGICAL_LAYERS else None
    text = str(value).strip().upper()
    if text.startswith('L'):
        text = text[1:]
    try:
        number = int(float(text))
    except (TypeError, ValueError):
        return None
    return number if 1 <= number <= C.MAX_LOGICAL_LAYERS else None


def _conflict_metrics(entry):
    out = {}
    if isinstance(entry, bool) or entry is None:
        return out
    if isinstance(entry, (int, float)):
        out['conflicts'] = entry
        return out
    if not isinstance(entry, dict):
        return out
    conflicts = _metric(entry, ('conflicts', 'violations', 'conflict_count',
                                'world_violations', 'n_conflicts'))
    crossings = _metric(entry, ('crossings', 'crossing_events',
                                'crossing_count', 'n_crossings'))
    pairs = _metric(entry, ('crossing_pairs', 'pairs', 'unique_crossing_pairs'))
    if conflicts is not None:
        out['conflicts'] = conflicts
    if crossings is not None:
        out['crossings'] = crossings
    if pairs is not None:
        out['crossing_pairs'] = pairs
    return out


def _extract_per_layer_verification(verification):
    """``{logical_layer|None: {conflicts, crossings, crossing_pairs}}``."""
    out = {}
    if not isinstance(verification, dict):
        return out
    for key in ('per_layer', 'per_logical_layer', 'layers'):
        value = verification.get(key)
        if isinstance(value, dict):
            for layer_key, item in value.items():
                layer = _layer_key(layer_key)
                metrics = _conflict_metrics(item)
                if metrics:
                    out.setdefault(layer, {}).update(metrics)
        elif isinstance(value, list):
            for item in value:
                if not isinstance(item, dict):
                    continue
                layer = _layer_key(
                    item.get('logical_layer', item.get('layer_id',
                                                      item.get('layer'))))
                metrics = _conflict_metrics(item)
                if metrics:
                    out.setdefault(layer, {}).update(metrics)
    # the independent crossing table is reported separately as
    # ``crossings.per_layer = {layer: {events, pairs, min_angle_deg}}``
    crossings = verification.get('crossings')
    if isinstance(crossings, dict):
        per_layer = crossings.get('per_layer')
        if isinstance(per_layer, dict):
            for layer_key, item in per_layer.items():
                layer = _layer_key(layer_key)
                if layer is None or not isinstance(item, dict):
                    continue
                slot = out.setdefault(layer, {})
                if item.get('events') is not None:
                    slot.setdefault('crossings', item['events'])
                if item.get('pairs') is not None:
                    slot.setdefault('crossing_pairs', item['pairs'])
    return out


def _extract_per_plane_verification(verification):
    """``{z_mm: {conflicts, crossings, crossing_pairs}}``."""
    out = {}
    if not isinstance(verification, dict):
        return out
    for key in ('per_plane', 'per_physical_plane', 'planes'):
        value = verification.get(key)
        if isinstance(value, dict):
            for plane_key, item in value.items():
                z = _as_float(plane_key)
                if z is None and isinstance(item, dict):
                    z = _as_float(item.get('z_mm'))
                if z is None:
                    continue
                metrics = _conflict_metrics(item)
                if metrics:
                    out.setdefault(round(z, 6), {}).update(metrics)
        elif isinstance(value, list):
            for item in value:
                if not isinstance(item, dict):
                    continue
                z = _as_float(item.get('z_mm'))
                if z is None:
                    continue
                metrics = _conflict_metrics(item)
                if metrics:
                    out.setdefault(round(z, 6), {}).update(metrics)
    crossings = verification.get('crossings')
    if isinstance(crossings, dict):
        per_plane = crossings.get('per_plane')
        if isinstance(per_plane, dict):
            for plane_key, item in per_plane.items():
                z = _as_float(plane_key)
                if z is None or not isinstance(item, dict):
                    continue
                slot = out.setdefault(round(z, 6), {})
                if item.get('events') is not None:
                    slot.setdefault('crossings', item['events'])
                if item.get('pairs') is not None:
                    slot.setdefault('crossing_pairs', item['pairs'])
    return out


def _fill_crossing_counts(entries, verification_layers, assembled_planes,
                          verification_available):
    """Fill missing per-route crossing counts with an exact layer-level value.

    A per-route crossing count needs a route-level audit.  When only a layer /
    physical-plane crossing count exists, the number is copied into the column
    **and** flagged via ``crossing_source='layer_level:...'`` - it is never
    presented as a per-route measurement.
    """
    filled = 0
    for entry in entries:
        if entry.get('crossing_count') is not None:
            entry['crossing_source'] = 'verification_per_route'
            continue
        if entry.get('status') != 'routed':
            entry['crossing_source'] = 'pending'
            continue
        layer = entry.get('assigned_logical_layer')
        if verification_available and isinstance(layer, int):
            metrics = verification_layers.get(layer)
            if isinstance(metrics, dict) and metrics.get('crossings') is not None:
                entry['crossing_count'] = int(metrics['crossings'])
                entry['crossing_source'] = (
                    f'layer_level:verification per_layer L{layer} '
                    f'(not per-route)')
                filled += 1
                continue
        z = entry.get('layer_z_mm')
        if z is not None:
            plane = assembled_planes.get(round(float(z), 6))
            if isinstance(plane, dict) and plane.get('crosssings') is not None:
                entry['crossing_count'] = int(plane['crosssings'])
                entry['crossing_source'] = (
                    f'layer_level:assembled plane z={round(float(z), 6)} '
                    f'(not per-route)')
                filled += 1
                continue
        entry['crossing_source'] = 'pending'
    return filled


def _extract_verification_summary(verification):
    if not isinstance(verification, dict):
        return None
    summary = verification.get('summary')
    return summary if isinstance(summary, dict) else None


def _assembled_plane_rows(assembled):
    if not isinstance(assembled, dict):
        return OrderedDict()
    planes = assembled.get('plane_crossings')
    out = OrderedDict()
    if not isinstance(planes, dict):
        return out
    for key, item in planes.items():
        z = _as_float(item.get('z_mm') if isinstance(item, dict) else key)
        if z is None:
            z = _as_float(key)
        if z is None:
            continue
        if not isinstance(item, dict):
            continue
        out[round(z, 6)] = dict(
            z_mm=round(z, 6),
            logical_layer=_as_int(item.get('logical_layer')),
            routes=_as_int(item.get('routes')) or 0,
            parts=_as_int(item.get('parts')) or 0,
            conflicts=_as_int(item.get('conflicts')),
            crosssings=_as_int(item.get('crossing_events')),
            crossing_pairs=_as_int(item.get('crossing_pairs')))
    return out


def _assembled_layer_rows(assembled):
    if not isinstance(assembled, dict):
        return []
    rows = assembled.get('per_layer')
    return rows if isinstance(rows, list) else []


def _verification_context(verification):
    """Small JSON-ready summary of the verification (or ``pending`` marker)."""
    if not isinstance(verification, dict):
        return dict(status='pending',
                    note='verify.verify_all() output not provided (None) - '
                         'clearance / conflict columns are pending, not zero')
    summary = _extract_verification_summary(verification)
    violations = verification.get('violations')
    failed_routes = verification.get('failed_routes')
    crossings = verification.get('crossings')
    crossing_total = None
    if isinstance(crossings, dict):
        crossing_total = _as_int(crossings.get('total'))
    return dict(
        status='provided',
        summary=_json_safe(summary) if summary is not None else 'pending',
        violations_count=(len(violations) if isinstance(violations, list)
                          else _as_int(violations)),
        violations_by_kind=(_json_safe((summary or {}).get('violations_by_kind'))
                            if isinstance(summary, dict) else None),
        checks_passed=((summary or {}).get('checks_passed')
                       if isinstance(summary, dict) else None),
        checks_failed=((summary or {}).get('checks_failed')
                       if isinstance(summary, dict) else None),
        failed_routes_count=(len(failed_routes)
                             if isinstance(failed_routes, list) else None),
        min_clearance_mm=_json_safe(verification.get('min_clearance_mm')),
        min_radius_mm=_json_safe(verification.get('min_radius_mm')),
        min_cross_angle_deg=_json_safe(verification.get('min_cross_angle_deg')),
        crossing_events_total=crossing_total,
        violation_examples=_json_safe(violations[:20])
        if isinstance(violations, list) else [],
    )


# ---------------------------------------------------------------------------
# per-layer row construction
# ---------------------------------------------------------------------------
def _compute_layer_rows(data, routed, non_routed, stack):
    """Own L1..Lmax per-layer statistics (used when assembled is unavailable)."""
    by_layer = OrderedDict()
    for route in routed:
        layer = _route_layer(route, stack)
        if layer is None:
            layer = 'unassigned'
        row = by_layer.setdefault(layer, dict(routes=[], failed=[]))
        row['routes'].append(route)
    for route in non_routed:
        layer = _route_layer(route, stack)
        if layer is None:
            layer = 'unassigned'
        row = by_layer.setdefault(layer, dict(routes=[], failed=[]))
        row['failed'].append(route)
    rows = []
    for layer in sorted(by_layer,
                        key=lambda value: (isinstance(value, str),
                                           value if isinstance(value, str)
                                           else int(value))):
        item = by_layer[layer]
        layer_routes = item['routes']
        layer_int = None if isinstance(layer, str) else int(layer)
        if layer_int is None:
            z_values = []
            label = 'unassigned'
            layer_type = 'unassigned'
        elif layer_int == C.INTERFACE_LAYER_ID:
            z_values = [float(C.Z1_MM), float(C.Z2_MM)]
            label = 'L1'
            layer_type = 'interface'
        else:
            z_values = [float(C.layer_z(layer_int))]
            label = f'L{layer_int}'
            layer_type = 'routing'
        total_length = sum(_route_length(route) or 0.0 for route in layer_routes)
        manual = 0
        for route in layer_routes:
            if (route.get('assignment') == 'manual_fixed_u' or
                    (data is not None
                     and (data.by_uid.get(_route_uid(route)) or {})
                     .get('assignment') == 'manual_fixed_u')):
                manual += 1
        rows.append(dict(
            logical_layer=layer_int, layer_label=label, layer_type=layer_type,
            physical_z_mm=z_values, routes=len(layer_routes),
            manual_routes=manual, automatic_routes=len(layer_routes) - manual,
            failed=len(item['failed']),
            total_length_mm=round(total_length, 6),
            propagation_loss_db=round(
                total_length / 10.0 * C.PROPAGATION_LOSS_DB_PER_CM, 9)))
    return rows


def _merge_layer_rows(assembled_rows, computed_rows, assembled_planes,
                      verification_layers):
    """Merge assembled / computed layer rows + conflict numbers.

    Priority for the conflict numbers: verification > assembled > ``pending``.
    """
    base = OrderedDict()
    for row in list(assembled_rows) + list(computed_rows):
        if not isinstance(row, dict):
            continue
        layer = _layer_key(row.get('logical_layer'))
        if layer not in base:
            base[layer] = dict(row)
        else:
            for key, value in row.items():
                if base[layer].get(key) in (None, '', [], 0) and value:
                    base[layer][key] = value
    # conflict sums from the assembled per-plane crossing audit
    plane_conflicts = Counter()
    plane_crossings = Counter()
    plane_pairs = Counter()
    for plane in assembled_planes.values():
        layer = plane.get('logical_layer')
        layer = _layer_key(layer)
        if layer is None:
            continue
        conflicts = plane.get('conflicts')
        if conflicts is not None:
            plane_conflicts[layer] += conflicts
        crossings = plane.get('crosssings')
        if crossings is not None:
            plane_crossings[layer] += crossings
        pairs = plane.get('crossing_pairs')
        if pairs is not None:
            plane_pairs[layer] += pairs

    merged = []
    for layer, row in base.items():
        item = dict(row)
        item['logical_layer'] = layer
        if layer is None:
            item.setdefault('layer_label', 'unassigned')
            item.setdefault('layer_type', 'unassigned')
        z_values = item.get('physical_z_mm')
        if isinstance(z_values, (int, float)):
            z_values = [float(z_values)]
        elif isinstance(z_values, list):
            z_values = [value for value in (_as_float(z) for z in z_values)
                        if value is not None]
        else:
            z_values = []
        # the layer's own physical height(s): L1 carries both interface rows,
        # every routing layer is one plane (assembled rows list every plane a
        # *route* touches, which would mix the L1 arms into the L2 height)
        if layer == C.INTERFACE_LAYER_ID:
            z_values = [float(C.Z1_MM), float(C.Z2_MM)]
        elif layer is not None:
            z_values = [float(C.layer_z(int(layer)))]
        item['physical_z_mm'] = z_values
        routed_count = _as_int(item.get('routes'))
        if routed_count is None:
            routed_count = _as_int(item.get('routed')) or 0
        item['routes'] = routed_count
        item['routed'] = routed_count
        item.setdefault('manual_routes', 0)
        item.setdefault('automatic_routes', 0)
        item.setdefault('failed', 0)
        # conflicts: verification first, then the assembled crossing audit
        conflicts = None
        source = 'pending'
        verif = verification_layers.get(layer) if layer is not None else None
        if isinstance(verif, dict) and verif.get('conflicts') is not None:
            conflicts = verif['conflicts']
            source = 'verification'
        elif layer is not None and plane_conflicts.get(layer) is not None:
            conflicts = plane_conflicts[layer]
            source = 'assembled_per_plane'
        crossings = None
        crossings_source = 'pending'
        if isinstance(verif, dict) and verif.get('crossings') is not None:
            crossings = verif['crossings']
            crossings_source = 'verification'
        elif layer is not None and plane_crossings.get(layer) is not None:
            crossings = plane_crossings[layer]
            crossings_source = 'assembled_per_plane'
        pairs = None
        if isinstance(verif, dict) and verif.get('crossing_pairs') is not None:
            pairs = verif['crossing_pairs']
        elif layer is not None and plane_pairs.get(layer) is not None:
            pairs = plane_pairs[layer]
        item['conflicts'] = conflicts
        item['crossing_events'] = crossings
        item['crossing_pairs'] = pairs
        item['conflict_source'] = (f'conflicts:{source}; crossings:{crossings_source}')
        if item.get('total_length_mm') is None:
            item['total_length_mm'] = 0.0
        if item.get('propagation_loss_db') is None:
            item['propagation_loss_db'] = round(
                float(item['total_length_mm']) / 10.0
                * C.PROPAGATION_LOSS_DB_PER_CM, 9)
        merged.append(item)
    merged.sort(key=lambda row: (row['logical_layer'] is None,
                                 row['logical_layer']
                                 if row['logical_layer'] is not None else 99))
    return merged


# ---------------------------------------------------------------------------
# record normalisation (one row / one json entry per input record)
# ---------------------------------------------------------------------------
def _csv_value(value):
    if value is None:
        return 'pending'
    if isinstance(value, bool):
        return 'yes' if value else 'no'
    if isinstance(value, float):
        if not math.isfinite(value):
            return 'pending'
        return f'{value:.6f}'
    if isinstance(value, (list, tuple)):
        if not value:
            return 'pending'
        return ';'.join(_csv_value(item) for item in value)
    return str(value)


def _format_float(value, digits=6):
    number = _as_float(value)
    if number is None:
        return None
    return round(number, digits)


def _make_record_entry(record, routed_route, failed_route, stack,
                       verification_metrics, verification_available,
                       violation_counts):
    """Normalised per-record entry used by routes.json and route_table.csv."""
    uid = record.get('uid') if isinstance(record, dict) else None
    routed_route = routed_route or {}
    failed_route = failed_route or {}
    source = routed_route if routed_route else failed_route
    status = 'routed' if routed_route else (
        failed_route.get('status') or 'failed')
    if not routed_route and not failed_route:
        status = 'missing'

    def pick(key, default=None):
        if key in source and source.get(key) is not None:
            return source[key]
        if isinstance(record, dict) and record.get(key) is not None:
            return record[key]
        return default

    logical_layer = _route_layer(source, stack) if source else None
    if logical_layer is None and isinstance(record, dict):
        assigned = _as_int(record.get('assigned_layer'))
        assignment = record.get('assignment')
        if assignment == 'manual_fixed_u' and assigned is not None:
            logical_layer = assigned
    layer_z = None
    if routed_route:
        layer_z = _route_layer_z(routed_route, stack)
    elif logical_layer is not None:
        if logical_layer == C.INTERFACE_LAYER_ID:
            layer_z = _as_float(record.get('source_z_mm')) if record else None
        else:
            layer_z = float(C.layer_z(logical_layer))
    assignment = pick('assignment')
    manual = assignment == 'manual_fixed_u'
    layer_source = ('csv_assigned_layer' if manual
                    else ('router_allocated' if status == 'routed' else 'pending'))
    csv_assigned = None
    if isinstance(record, dict):
        csv_assigned = record.get('assigned_layer_csv') or record.get(
            'csv_assigned_layer')
    csv_assigned = csv_assigned or pick('csv_assigned_layer')
    source_xy = pick('source_xy_mm') or pick('source_xy')
    target_xy = pick('target_xy_mm') or pick('target_xy')
    if source_xy is None and isinstance(record, dict):
        source_xy = record.get('source_xy')
    if target_xy is None and isinstance(record, dict):
        target_xy = record.get('target_xy')

    length = _route_length(routed_route) if routed_route else None
    flat_length = _flat_length(routed_route) if routed_route else None
    transition_length = _transition_length(routed_route) if routed_route else None
    min_radius = _min_bend_radius(routed_route) if routed_route else None
    bend_count = _bend_count(routed_route) if routed_route else None
    propagation = (round(length / 10.0 * C.PROPAGATION_LOSS_DB_PER_CM, 9)
                   if length is not None else None)
    metrics = verification_metrics.get(uid) if isinstance(uid, str) else None
    metrics = metrics or {}
    min_clearance = metrics.get('min_clearance_mm')
    crossing_count = metrics.get('crossing_count')
    crossing_source = 'verification_per_route' if crossing_count is not None \
        else 'pending'
    world_violations = metrics.get('verification_violation_count')
    if world_violations is None:
        world_violations = (violation_counts.get(uid, 0)
                            if verification_available else None)

    entry = dict(
        uid=uid,
        route_id=_as_int(source.get('route_id')) if source else None,
        original_route_id=_as_int(pick('original_route_id')),
        dataset=pick('dataset') or pick('plane'),
        plane=pick('plane') or pick('dataset'),
        relation=pick('relation'),
        source_side=pick('source_side'),
        target_side=pick('target_side'),
        source_port_id=pick('source_port_id'),
        target_port_id=pick('target_port_id'),
        source_endpoint_id=pick('source_endpoint_id'),
        target_endpoint_id=pick('target_endpoint_id'),
        source_xy_mm=[float(v) for v in source_xy] if source_xy else None,
        target_xy_mm=[float(v) for v in target_xy] if target_xy else None,
        source_z_mm=_format_float(pick('source_z_mm')),
        target_z_mm=_format_float(pick('target_z_mm')),
        assignment=assignment,
        manual_group=pick('manual_group'),
        u_pair=pick('u_pair'),
        csv_assigned_layer=csv_assigned,
        assigned_logical_layer=logical_layer,
        logical_layer=logical_layer,
        target_layer=logical_layer,
        layer_source=layer_source,
        layer_z_mm=_format_float(layer_z),
        layer_sequence=_layer_sequence(source) if source else [],
        layer_z_sequence=[_format_float(value)
                          for value in _layer_z_sequence(source)]
        if source else [],
        n_transitions=_as_int(source.get('n_transitions')) if source else 0,
        path_length_mm=_format_float(length),
        length_mm=_format_float(length),
        flat_length_mm=_format_float(flat_length),
        transition_length_mm=_format_float(transition_length),
        min_bend_radius_mm=_format_float(min_radius),
        bend_count=bend_count,
        min_clearance_mm=_format_float(min_clearance),
        crossing_count=_as_int(crossing_count),
        crossing_source=crossing_source,
        propagation_loss_db=propagation,
        bend_loss_db=None,
        crossing_loss_db=None,
        loss_status=('propagation_only_bend_crossing_uncalibrated'
                     if status == 'routed'
                     else 'not_applicable_route_not_routed'),
        verification_violation_count=world_violations,
        status=status,
        failure_reason=(
            source.get('failure_reason') if status != 'routed' else None),
        failure_detail=(_json_safe(source.get('failure_detail'))
                        if status != 'routed' else None),
    )
    if not entry['failure_reason'] and status != 'routed':
        entry['failure_reason'] = ('record_missing_from_pipeline'
                                   if status == 'missing'
                                   else 'unspecified_failure')
    return entry


# ---------------------------------------------------------------------------
# writing helpers
# ---------------------------------------------------------------------------
def _write_json(path, payload, log):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(payload), indent=1,
                               ensure_ascii=False) + '\n', encoding='utf-8')
    log(f'[export] wrote {path.name}')
    return path


def _write_csv(path, fieldnames, rows, log):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames,
                                extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key))
                             for key in fieldnames})
    log(f'[export] wrote {path.name} ({len(rows)} rows)')
    return path


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------
def _loss_record():
    process = C.process_record()
    return dict(
        propagation_loss_db_per_cm=C.PROPAGATION_LOSS_DB_PER_CM,
        propagation_loss_source=('four_side_1024/fslw/config.py '
                                 'PROPAGATION_LOSS_DB_PER_CM (existing project '
                                 'configuration, read via '
                                 'four_side_1024/manual_u640/config.py)'),
        propagation_model='dB = length_mm / 10 * 0.05 dB/cm',
        bend_loss=dict(status='pending',
                       source='four_side_1024/fslw/config.py BEND_LOSS',
                       declared=process.get('bend_loss'),
                       note=('no measured bend-loss function exists for this '
                             'glass process; R = 15 mm is a geometry constraint '
                             'only - no number is invented')),
        crossing_loss=dict(status='pending',
                           source='four_side_1024/fslw/config.py CROSSING_LOSS',
                           declared=process.get('crossing_loss'),
                           note=('crossing optical feasibility is not confirmed; '
                                 'the crossing count is a geometric metric only '
                                 '- no number is invented')),
        legacy_polymer_model=dict(status='not_used',
                                  note=('the old AutoRouter polymer loss model '
                                        '(loss_model.py / '
                                        'waveguide_calculator.py) is kept as '
                                        'history only and is NOT a glass '
                                        'process truth for this round')),
    )


def _failure_summary(non_routed):
    by_reason = Counter()
    uids = OrderedDict()
    for route in non_routed:
        reason = route.get('failure_reason') or 'unspecified_failure'
        by_reason[str(reason)] += 1
        uids.setdefault(str(reason), []).append(route.get('uid'))
    return dict(total=len(non_routed),
                by_reason=dict(by_reason.most_common()),
                examples={reason: items[:8] for reason, items in uids.items()})


def _group_statistics(data, routed_by_uid, failed_by_uid):
    manual = OrderedDict()
    auto = OrderedDict()
    if data is not None:
        from . import inputs as input_module
        manual_names = getattr(input_module, 'MANUAL_LAYERS', {})
        for layer_id, uids in data.manual_groups.items():
            routed = sum(1 for uid in uids if uid in routed_by_uid)
            manual[str(layer_id)] = dict(
                layer_id=int(layer_id),
                group=manual_names.get(int(layer_id)),
                total=len(uids), routed=routed,
                failed=len(uids) - routed)
        for group, uids in data.auto_groups.items():
            routed = sum(1 for uid in uids if uid in routed_by_uid)
            auto[group] = dict(total=len(uids), routed=routed,
                               failed=len(uids) - routed)
    return dict(manual_layers=manual, automatic_groups=auto)


def _auto_layer_statistics(layer_rows, data):
    out = []
    for row in layer_rows:
        layer = row.get('logical_layer')
        if layer is None or int(layer) < C.FIRST_AUTO_LAYER_ID:
            continue
        out.append(dict(logical_layer=int(layer),
                        layer_label=row.get('layer_label'),
                        physical_z_mm=row.get('physical_z_mm'),
                        routes=row.get('routes'),
                        manual_routes=row.get('manual_routes'),
                        automatic_routes=row.get('automatic_routes'),
                        failed=row.get('failed'),
                        conflicts=row.get('conflicts'),
                        crossing_events=row.get('crossing_events'),
                        total_length_mm=row.get('total_length_mm'),
                        propagation_loss_db=row.get('propagation_loss_db')))
    return out


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------
def export_all(routes, data, stack, out_dir, verification=None, assembled=None,
               failures=None, log=print):
    """Write routes.json / route_table.csv / per_layer.csv / statistics.json.

    Parameters
    ----------
    routes:
        routed-record list (``status='routed'``, full ``parts`` geometry).  A
        JSON path or ``{'routes': [...]}`` payload is also accepted; entries
        whose ``status == 'failed'`` are moved to the failure list.
    data:
        :class:`four_side_1024.manual_u640.inputs.InputData` (may be ``None``;
        the CSV is then reloaded, or the route order is used).
    stack:
        :class:`four_side_1024.manual_u640.stack.LayerStack`.
    out_dir:
        export directory (``outputs/manual_u640``).
    verification:
        optional ``verify.verify_all`` dict; per-route clearance / crossing
        numbers are merged when present, otherwise those columns are
        ``pending``.
    assembled:
        optional ``assemble.assemble`` dict (per-plane crossings, per-layer
        statistics, loss record, used layers/planes); used to fill the layer
        and plane statistics, merged with the verification numbers
        (verification wins).
    failures:
        optional failed-record list (``status='failed'``, ``parts=[]``).
    log:
        injectable logger.
    """
    started = time.perf_counter()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    warnings = []
    stack = _load_stack(stack)
    data = _load_data(data, warnings)

    routed_input = _normalise_records(routes, warnings, 'routes')
    failure_input = _normalise_records(failures, warnings, 'failures')
    # split anything that arrived in the "routes" container by status
    routed = []
    moved_failed = []
    for route in routed_input:
        if route.get('status') == 'failed' or not _is_routed(route):
            moved_failed.append(route)
        else:
            routed.append(route)
    failed_pool = OrderedDict()
    for route in moved_failed + failure_input:
        uid = _route_uid(route)
        if uid is None:
            warnings.append('failed record without uid ignored')
            continue
        if uid not in failed_pool:
            failed_pool[uid] = route
    routed_by_uid = OrderedDict()
    for route in routed:
        uid = _route_uid(route)
        if uid is None:
            warnings.append('routed record without uid ignored')
            continue
        if uid in routed_by_uid:
            warnings.append(f'duplicate routed record {uid} ignored')
            continue
        routed_by_uid[uid] = route
    for uid in list(failed_pool):
        if uid in routed_by_uid:
            warnings.append(f'record {uid} reported both routed and failed; '
                            f'the routed record is kept')
            failed_pool.pop(uid)

    # ordered 640-record list (input CSV order; never drop a record)
    if data is not None:
        order = [record['uid'] for record in data.records]
        record_by_uid = {record['uid']: record for record in data.records}
        unknown = [uid for uid in list(routed_by_uid) + list(failed_pool)
                   if uid not in record_by_uid]
        if unknown:
            warnings.append(f'{len(unknown)} records are not in the input CSV: '
                            f'{unknown[:5]}')
    else:
        order = list(routed_by_uid) + [uid for uid in failed_pool
                                      if uid not in routed_by_uid]
        record_by_uid = {uid: dict(uid=uid) for uid in order}

    verification_metrics = _extract_route_metrics(verification)
    verification_layers = _extract_per_layer_verification(verification)
    verification_planes = _extract_per_plane_verification(verification)
    verification_available = isinstance(verification, dict)
    violation_counts = Counter()
    if isinstance(verification, dict):
        for violation in verification.get('violations') or []:
            if not isinstance(violation, dict):
                continue
            for key in ('uid', 'uid_a', 'uid_b'):
                uid = violation.get(key)
                if isinstance(uid, str):
                    violation_counts[uid] += 1

    entries = []
    routed_entries = []
    failed_entries = []
    for uid in order:
        record = record_by_uid.get(uid) or dict(uid=uid)
        routed_route = routed_by_uid.get(uid)
        failed_route = failed_pool.get(uid)
        entry = _make_record_entry(
            record, routed_route, failed_route, stack, verification_metrics,
            verification_available, violation_counts)
        entries.append(entry)
        if entry['status'] == 'routed':
            routed_entries.append(entry)
        else:
            failed_entries.append(entry)
    unmatched = [uid for uid in list(routed_by_uid) + list(failed_pool)
                 if uid not in set(order)]
    if unmatched:
        warnings.append(f'{len(unmatched)} records were not part of the '
                        f'640-record input order: {unmatched[:5]}')
    # per-route crossing counts: verification route metrics first, otherwise an
    # exact layer/plane-level number with an explicit source note
    assembled_planes = _assembled_plane_rows(assembled)
    layer_level_filled = _fill_crossing_counts(
        entries, verification_layers, assembled_planes, verification_available)

    # ---- routes.json -----------------------------------------------------
    layers_used = sorted({entry['assigned_logical_layer']
                          for entry in routed_entries
                          if entry['assigned_logical_layer'] is not None})
    physical_planes = _physical_plane_statistics(
        routed_by_uid, data, stack, assembled, verification_planes)
    routes_payload = dict(
        schema=SCHEMA_ROUTES,
        tool=TOOL,
        generated_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
        note=('one entry per input record (640); routed entries carry the full '
              '3D parts geometry, failed entries carry parts=[] and a '
              'structured failure reason'),
        route_count=len(entries),
        routed=len(routed_entries),
        failed=len(failed_entries),
        logical_layers_used=layers_used,
        physical_planes_used=sorted(physical_planes),
        process=C.process_record(),
        layer_stack=stack.payload(getattr(stack, 'max_layer',
                                          C.MAX_LOGICAL_LAYERS)),
        verification=_verification_context(verification),
        routes=_json_safe(_routes_json_entries(entries, routed_by_uid,
                                               failed_pool)),
    )
    routes_path = _write_json(out_dir / 'routes.json', routes_payload, log)

    # ---- route_table.csv -------------------------------------------------
    table_rows = [_table_row(entry) for entry in entries]
    table_path = _write_csv(
        out_dir / 'route_table.csv',
        ROUTE_TABLE_COLUMNS + ROUTE_TABLE_EXTRA_COLUMNS,
        table_rows, log)

    # ---- per_layer.csv ---------------------------------------------------
    computed_rows = _compute_layer_rows(data, routed, list(failed_pool.values()),
                                        stack)
    layer_rows = _merge_layer_rows(_assembled_layer_rows(assembled),
                                   computed_rows,
                                   _assembled_plane_rows(assembled),
                                   verification_layers)
    layer_path = _write_csv(out_dir / 'per_layer.csv', PER_LAYER_COLUMNS,
                            layer_rows, log)

    # ---- statistics.json -------------------------------------------------
    deployed = _loss_record()
    length_total = sum(entry['path_length_mm'] or 0.0
                       for entry in routed_entries)
    flat_total = sum(entry['flat_length_mm'] or 0.0 for entry in routed_entries)
    transition_total = sum(entry['transition_length_mm'] or 0.0
                           for entry in routed_entries)
    propagation_total = (length_total / 10.0
                         * C.PROPAGATION_LOSS_DB_PER_CM)
    assembled_loss = (assembled.get('loss')
                      if isinstance(assembled, dict) else None)
    if isinstance(assembled_loss, dict):
        deployed['assembled_loss_record'] = _json_safe(assembled_loss)
        deployed['propagation_loss_db'] = _as_float(
            assembled_loss.get('propagation_loss_db'))
        deployed['total_length_mm'] = _as_float(
            assembled_loss.get('total_length_mm'))
    else:
        deployed['propagation_loss_db'] = round(propagation_total, 6)
        deployed['total_length_mm'] = round(length_total, 6)
    pending = ['bend_loss_db', 'crossing_loss_db']
    if not verification_available:
        pending.extend(['min_clearance_mm', 'verification_conflicts'])
    if not isinstance(assembled, dict):
        pending.extend(['per_plane_crossing_events',
                        'assembled_layer_conflicts'])
    per_route_crossing_available = any(
        entry['crossing_source'] == 'verification_per_route'
        for entry in routed_entries)
    if not per_route_crossing_available:
        pending.append('per_route_crossing_count')

    verification_context = _verification_context(verification)
    # geometric conflicts only: the independent per-plane conflict audit.  The
    # full violation list also contains non-geometric bookkeeping findings
    # (e.g. a legitimately failed automatic route), which are reported
    # separately and must NOT be presented as geometric conflicts.
    verification_plane_conflicts = None
    if verification_available and verification_planes:
        values = [metrics.get('conflicts') for metrics in
                  verification_planes.values()
                  if metrics.get('conflicts') is not None]
        if values:
            verification_plane_conflicts = sum(values)
    plane_conflicts_total = sum(
        plane.get('conflicts') or 0
        for plane in _assembled_plane_rows(assembled).values())
    if verification_plane_conflicts is not None:
        conflicts_total = verification_plane_conflicts
        conflicts_source = ('verification.per_plane conflicts (independent '
                            'geometric audit; legal crossings excluded)')
    elif isinstance(assembled, dict):
        conflicts_total = plane_conflicts_total
        conflicts_source = 'assembled.plane_crossings conflicts'
    else:
        conflicts_total = None
        conflicts_source = ('pending: verification and assemble outputs not '
                            'provided')
    verification_violations = verification_context.get('violations_count')
    crossing_total = verification_context.get('crossing_events_total')
    crossing_source = ('verification.crossings.total (independent audit; legal '
                       'crossings, not violations)')
    if crossing_total is None and isinstance(assembled, dict):
        crossing_total = _as_int(assembled.get('crossing_events_total'))
        crossing_source = ('assembled.plane_crossings (legal crossings; '
                           'not violations)')
    if crossing_total is None:
        crossing_source = 'pending'

    min_radius = None
    radii = [entry['min_bend_radius_mm'] for entry in routed_entries
             if entry['min_bend_radius_mm'] is not None]
    if radii:
        min_radius = min(radii)
    min_clearance = verification_context.get('min_clearance_mm')
    if min_clearance is None:
        min_clearance = 'pending'

    assignment_groups = _group_statistics(
        data,
        {entry['uid']: entry for entry in routed_entries},
        {entry['uid']: entry for entry in failed_entries})
    manual_rows = (assignment_groups.get('manual_layers') or {}).values()
    auto_rows = (assignment_groups.get('automatic_groups') or {}).values()
    group_totals = dict(
        manual=dict(records=sum(item.get('total') or 0 for item in manual_rows),
                    routed=sum(item.get('routed') or 0 for item in manual_rows),
                    failed=sum(item.get('failed') or 0 for item in manual_rows),
                    logical_layers=list(C.MANUAL_LAYER_IDS)),
        automatic=dict(records=sum(item.get('total') or 0 for item in auto_rows),
                       routed=sum(item.get('routed') or 0 for item in auto_rows),
                       failed=sum(item.get('failed') or 0 for item in auto_rows),
                       logical_layers=[layer for layer in layers_used
                                       if layer >= C.FIRST_AUTO_LAYER_ID],
                       layer_assignment_note=('automatic layers are allocated '
                                              'by the router from L7 upwards '
                                              '(one layer per group when '
                                              'possible)')),
    )

    statistics = dict(
        schema=SCHEMA_STATISTICS,
        tool=TOOL,
        generated_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
        input=(dict(path=data.path, sha256=data.sha256,
                    validation_passed=data.validation.get('passed'),
                    total_records=len(data.records))
               if data is not None else 'pending'),
        model=dict(
            board_mm=[C.BOARD_MM, C.BOARD_MM],
            waveguide_width_mm=C.WIDTH_MM,
            min_centerline_clearance_mm=C.CLEARANCE_MM,
            min_bend_radius_mm=C.RADIUS_MM,
            min_cross_angle_deg=C.MIN_CROSS_ANGLE_DEG,
            layer_pitch_mm=C.LAYER_PITCH_MM,
            base_routing_z_mm=C.BASE_ROUTING_Z_MM,
            plane_z_mm=dict(C.PLANE_Z_MM),
            interface_layer=C.INTERFACE_LAYER_ID,
            manual_layer_ids=list(C.MANUAL_LAYER_IDS),
            first_auto_layer_id=C.FIRST_AUTO_LAYER_ID,
            layer_stack_provenance=C.PROVENANCE,
            layer_stack_note=C.STACK_NOTE,
        ),
        totals=dict(
            records=len(entries),
            routed=len(routed_entries),
            failed=len(failed_entries),
            missing=sum(1 for entry in failed_entries
                        if entry['status'] == 'missing'),
            success_rate=round(len(routed_entries) / max(len(entries), 1), 6),
            expected_records=TOTAL_RECORDS,
            record_count_ok=(len(entries) == TOTAL_RECORDS),
        ),
        assignment_groups=assignment_groups,
        group_totals=group_totals,
        datasets=dict(Counter(entry['dataset'] for entry in entries
                              if entry['dataset'])),
        layers=dict(
            used_logical_layers=layers_used,
            logical_layer_count=len(layers_used),
            used_physical_planes=sorted(physical_planes),
            physical_plane_count=len(physical_planes),
            manual_routing_layer_count=sum(
                1 for layer in layers_used if layer < C.FIRST_AUTO_LAYER_ID
                and layer != C.INTERFACE_LAYER_ID),
            automatic_routing_layer_count=sum(
                1 for layer in layers_used
                if layer >= C.FIRST_AUTO_LAYER_ID),
            per_layer=layer_rows,
            automatic_layers=_auto_layer_statistics(layer_rows, data),
        ),
        geometry=dict(
            total_length_mm=round(length_total, 6),
            total_flat_length_mm=round(flat_total, 6),
            total_transition_length_mm=round(transition_total, 6),
            mean_length_mm=round(length_total / max(len(routed_entries), 1), 6),
            min_bend_radius_mm=min_radius,
            min_bend_radius_source=('minimum over the exact R15 arc radii of '
                                    'every routed primitive'),
            min_clearance_mm=min_clearance,
            min_clearance_source=('verification.min_clearance_mm'
                                  if min_clearance != 'pending'
                                  else 'pending: verify.verify_all() not provided'),
            conflicts=conflicts_total if conflicts_total is not None
            else 'pending',
            conflicts_source=conflicts_source,
            verification_violations_total=(
                verification_violations
                if isinstance(verification_violations, int) else 'pending'),
            verification_violations_by_kind=(
                verification_context.get('violations_by_kind') or 'pending'),
            verification_checks=(dict(
                passed=verification_context.get('checks_passed'),
                total=verification_context.get('summary', {}).get('checks_total')
                if isinstance(verification_context.get('summary'), dict) else None,
                failed=verification_context.get('checks_failed'))
                if verification_available else 'pending'),
            crossing_events_total=(crossing_total
                                   if crossing_total is not None else 'pending'),
            crossing_events_source=crossing_source,
            crossing_count_source=(
                'per-route counts from verification where available; '
                f'{layer_level_filled} routed records use an exact layer-level '
                'crossing count flagged in route_table.csv via crossing_source; '
                'the remaining records are pending'),
            crossing_count_per_route_records=sum(
                1 for entry in routed_entries
                if entry['crossing_source'] == 'verification_per_route'),
            crossing_count_layer_level_records=layer_level_filled,
            per_physical_plane=physical_planes,
        ),
        assumptions=[
            ('all 640 input records are present exactly once: routed records '
             'with status=routed, failures with status=failed and a structured '
             'reason; a record the pipeline did not report is status=missing.'),
            ('per-layer conflicts merge assembled.plane_crossings with the '
             'independent verification; verification wins, and when neither is '
             'available the value is pending - never a silent 0.'),
            ('min_clearance_mm comes from verify.verify_all only; it is pending '
             'when verification is not provided.'),
            ('route_table.csv crossing_count is a verification per-route metric '
             'when available, otherwise the exact layer/plane crossing count '
             'with an explicit crossing_source flag, otherwise pending.'),
            ('loss model: propagation 0.05 dB/cm x length is the only calibrated '
             'term of the existing configuration; bend and crossing loss are '
             'unknown_uncalibrated in four_side_1024/fslw/config.py and stay '
             'pending - the legacy polymer model is not used as glass truth.'),
            ('layer heights are simulation inputs (unconfirmed_simulation), not '
             'confirmed fabrication parameters.'),
        ],
        loss=deployed,
        failures=_failure_summary(failed_entries),
        verification=verification_context,
        assembled_available=isinstance(assembled, dict),
        loss_status='propagation_only_bend_crossing_uncalibrated',
        pending=pending,
        warnings=warnings,
        elapsed_s=None,
    )
    statistics['elapsed_s'] = round(time.perf_counter() - started, 2)
    statistics_path = _write_json(out_dir / 'statistics.json', statistics, log)

    files = dict(routes_json=str(routes_path),
                 route_table_csv=str(table_path),
                 per_layer_csv=str(layer_path),
                 statistics_json=str(statistics_path))
    result = dict(
        schema='four_side_1024_manual_u640_export_v1',
        out_dir=str(out_dir),
        files=files,
        counts=dict(records=len(entries), routed=len(routed_entries),
                    failed=len(failed_entries),
                    missing=statistics['totals']['missing'],
                    manual_routed=sum(
                        1 for entry in routed_entries
                        if entry['assignment'] == 'manual_fixed_u'),
                    manual_failed=sum(
                        1 for entry in failed_entries
                        if entry['assignment'] == 'manual_fixed_u'),
                    auto_routed=sum(
                        1 for entry in routed_entries
                        if entry['assignment'] != 'manual_fixed_u'),
                    auto_failed=sum(
                        1 for entry in failed_entries
                        if entry['assignment'] != 'manual_fixed_u')),
        layers=dict(used_logical_layers=layers_used,
                    logical_layer_count=len(layers_used),
                    physical_plane_count=len(physical_planes)),
        totals=statistics['totals'],
        geometry=statistics['geometry'],
        loss=dict(propagation_loss_db=deployed.get('propagation_loss_db'),
                  propagation_loss_db_per_cm=C.PROPAGATION_LOSS_DB_PER_CM,
                  bend_loss='pending', crossing_loss='pending',
                  loss_status=statistics['loss_status']),
        per_layer_rows=len(layer_rows),
        warnings=warnings,
        elapsed_s=round(time.perf_counter() - started, 2),
    )
    log(f'[export] {len(entries)} records: {len(routed_entries)} routed, '
        f'{len(failed_entries)} failed | propagation loss '
        f'{deployed.get("propagation_loss_db")} dB | '
        f'pending: {", ".join(pending)}')
    return result


def _routes_json_entries(entries, routed_by_uid, failed_by_uid=None):
    """Full JSON entries: routed geometry + export metrics, failures with parts."""
    failed_by_uid = failed_by_uid or {}
    out = []
    for entry in entries:
        uid = entry['uid']
        route = routed_by_uid.get(uid)
        if route is not None:
            item = dict(route)
        else:
            failure = failed_by_uid.get(uid)
            item = dict(failure) if failure is not None else dict()
            item.setdefault('uid', uid)
            item.setdefault('status', 'failed')
            item.setdefault('parts', [])
            item.setdefault('primitives_2d', [])
        item['status'] = entry['status']
        for key in ('assigned_logical_layer', 'target_layer', 'logical_layer',
                    'layer_source', 'layer_z_mm', 'layer_sequence',
                    'layer_z_sequence', 'n_transitions', 'path_length_mm',
                    'length_mm', 'flat_length_mm', 'transition_length_mm',
                    'min_bend_radius_mm', 'bend_count', 'min_clearance_mm',
                    'crossing_count', 'crossing_source', 'propagation_loss_db',
                    'bend_loss_db', 'crossing_loss_db', 'loss_status',
                    'verification_violation_count', 'failure_reason'):
            if key in item or entry.get(key) is not None:
                item[key] = entry.get(key)
        item.setdefault('manual_group', entry.get('manual_group'))
        item.setdefault('relation', entry.get('relation'))
        item.setdefault('dataset', entry.get('dataset'))
        item.setdefault('original_route_id', entry.get('original_route_id'))
        item.setdefault('source_port_id', entry.get('source_port_id'))
        item.setdefault('target_port_id', entry.get('target_port_id'))
        item.setdefault('assignment', entry.get('assignment'))
        if entry['status'] != 'routed':
            item['parts'] = [] if not item.get('parts') else item['parts']
            item['status'] = entry['status']
            item['failure_reason'] = entry['failure_reason']
        out.append(item)
    return out


def _table_row(entry):
    row = dict(entry)
    source_xy = entry.get('source_xy_mm') or [None, None]
    target_xy = entry.get('target_xy_mm') or [None, None]
    row['source_x_mm'] = _format_float(source_xy[0])
    row['source_y_mm'] = _format_float(source_xy[1])
    row['target_x_mm'] = _format_float(target_xy[0])
    row['target_y_mm'] = _format_float(target_xy[1])
    row['layer_sequence'] = ('-'.join(str(value) for value in
                                      entry.get('layer_sequence') or [])
                             or None)
    row['layer_z_sequence'] = (';'.join(f'{value:.3f}' for value in
                                        entry.get('layer_z_sequence') or [])
                               or None)
    return row


def _physical_plane_statistics(routed_by_uid, data, stack, assembled,
                               verification_planes):
    """``{z_mm: {...}}`` of every physical plane used by the routed records."""
    heights = Counter()
    for route in routed_by_uid.values():
        for part in _flat_parts(route):
            z = _as_float(part.get('z_mm'))
            if z is not None:
                heights[round(z, 6)] += 1
    planes = OrderedDict()
    assembled_planes = _assembled_plane_rows(assembled)
    for z in sorted(set(heights) | set(assembled_planes)):
        layer = _layer_of_z(z, stack) if z is not None else None
        if layer is None and z is not None:
            layer = assembled_planes.get(z, {}).get('logical_layer')
        item = dict(
            z_mm=z,
            logical_layer=_layer_key(layer),
            flat_parts=heights.get(z, 0),
        )
        assembled_item = assembled_planes.get(z) or {}
        verif_item = verification_planes.get(z) or {}
        for key, source in (('routes', assembled_item),
                            ('conflicts', assembled_item),
                            ('crossing_events', assembled_item),
                            ('crossing_pairs', assembled_item)):
            value = source.get(key)
            if value is not None:
                item[key] = value
        for key, source_key in (('verification_conflicts', 'conflicts'),
                                ('verification_crossings', 'crossings')):
            value = verif_item.get(source_key)
            if value is not None:
                item[key] = value
        if 'verification_conflicts' in item:
            item['conflicts'] = item['verification_conflicts']
            item['conflicts_source'] = 'verification'
        elif 'conflicts' in item:
            item['conflicts_source'] = 'assembled'
        else:
            item['conflicts'] = None
            item['conflicts_source'] = 'pending'
        planes[z] = item
    return planes


# ---------------------------------------------------------------------------
# CLI (debug helper; the pipeline calls export_all directly)
# ---------------------------------------------------------------------------
def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(
        description='Export the manual_u640 route table / per-layer / statistics.')
    parser.add_argument('--routes', required=True,
                        help='routes.json (payload or list)')
    parser.add_argument('--out', default='outputs/manual_u640')
    parser.add_argument('--verification', default=None,
                        help='optional validation.json from verify.py')
    parser.add_argument('--assembled', default=None,
                        help='optional assemble.json')
    parser.add_argument('--max-layer', type=int, default=C.MAX_LOGICAL_LAYERS)
    args = parser.parse_args(argv)
    from . import inputs as input_module
    from . import stack as stack_module
    data = input_module.load_inputs()
    stack = stack_module.LayerStack(args.max_layer)
    verification = (_load_json(args.verification)
                    if args.verification else None)
    assembled = _load_json(args.assembled) if args.assembled else None
    routes = []
    failures = []
    payload = _load_json(args.routes)
    items = payload['routes'] if isinstance(payload, dict) else payload
    for item in items:
        if item.get('status') == 'failed':
            failures.append(item)
        else:
            routes.append(item)
    result = export_all(routes, data, stack, args.out,
                        verification=verification, assembled=assembled,
                        failures=failures)
    print(json.dumps({key: result[key] for key in ('counts', 'layers', 'loss',
                                                   'warnings', 'elapsed_s')},
                     indent=1, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
