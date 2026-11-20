# -*- coding: utf-8 -*-
"""G7 frozen-structure manifest (the Fixed-Layer + Fixed-Transition contract).

The G6 payload's *real* geometry is the only source of truth: the G6 validator
already recorded 134 routes whose stale assignment row disagrees with the real
body height, so the freeze manifest is built from ``routes_l3d.json`` itself:

* per route: the full part-kind sequence and, for every non-body part, a
  canonical rounded signature of its geometry (transition start/direction/z0/z1/
  radius/footprint/end/length, lead-flat primitives, native-3D excursion parts);
* the body flat index and its real z (the only part G7 may replace), plus the
  body plateau list of native-3D routes (frozen);
* classification: ``modifiable`` = standard 5-part lifted route without a manual
  group; everything else (92 direct, 368 artificial-U, 37 native-3D) is frozen.

``verify_payload`` re-checks the manifest on any candidate payload and reports
every violation with its route id.
"""
from __future__ import annotations

import json
import math

BODY_MODIFIABLE_KINDS = ['flat', 'transition', 'flat', 'transition', 'flat']


def _round(value, digits=9):
    if isinstance(value, (list, tuple)):
        return [_round(item, digits) for item in value]
    if isinstance(value, dict):
        return {key: _round(item, digits) for key, item in sorted(value.items())}
    if isinstance(value, float):
        out = round(value, digits)
        return 0.0 if out == 0.0 else out
    return value


def _prim_signature(prim):
    return _round({key: value for key, value in prim.items()}, 9)


def _part_signature(part):
    if part.get('kind') == 'flat':
        return _round(dict(kind='flat', z_mm=part.get('z_mm'),
                           layer_id=part.get('layer_id'),
                           primitives=[_prim_signature(prim) for prim in
                                       part.get('primitives') or []]), 9)
    return _round({key: value for key, value in part.items()
                   if key != 'tag'}, 9)


def classify(route):
    """Return ``modifiable`` / ``direct`` / ``manual`` / ``native``."""
    if (route.get('manual_group') or '').strip():
        return 'manual'
    ntr = int(route.get('n_transitions') or 0)
    if ntr == 0:
        return 'direct'
    if ntr == 2 and [part.get('kind') for part in route.get('parts') or ()] \
            == BODY_MODIFIABLE_KINDS:
        return 'modifiable'
    return 'native'


def build_manifest(routes):
    entries = {}
    for route in routes:
        rid = int(route['route_id'])
        kind = classify(route)
        parts = route.get('parts') or []
        body_indices = [index for index, part in enumerate(parts)
                        if part.get('kind') == 'flat']
        if kind == 'modifiable':
            body_index = body_indices[1]
        else:
            # direct / manual / native-3D routes are completely frozen: their
            # geometry must not change at all (G7 only rewrites the body
            # MultiArc of the 527 standard lifted routes).
            body_index = None
        signatures = [_part_signature(part) for index, part in enumerate(parts)
                      if index != body_index]
        entries[str(rid)] = dict(
            route_id=rid, kind=kind, n_transitions=int(route.get('n_transitions') or 0),
            part_kinds=[part.get('kind') for part in parts],
            body_index=body_index,
            body_z=(float(parts[body_index]['z_mm'])
                    if body_index is not None else None),
            body_indices=body_indices,
            body_heights=[round(float(parts[index]['z_mm']), 9)
                          for index in body_indices],
            z_sequence=[round(float(part['z_mm']), 9) for part in parts
                        if part.get('kind') == 'flat'],
            layer_sequence=_round(route.get('layer_sequence')),
            layer_z_sequence=_round(route.get('layer_z_sequence')),
            layers_used=_round(route.get('layers_used')),
            frozen_parts={index: signature
                          for index, signature in zip(
                              [i for i in range(len(parts)) if i != body_index],
                              signatures)},
            lead_source_mm=route.get('lead_source_mm'),
            lead_target_mm=route.get('lead_target_mm'),
            start_z_mm=route.get('start_z_mm'),
            end_z_mm=route.get('end_z_mm'),
            direct=bool(route.get('direct')),
            source_endpoint=route.get('source_endpoint'),
            target_endpoint=route.get('target_endpoint'),
            source_side=route.get('source_side'),
            target_side=route.get('target_side'),
            manual_group=route.get('manual_group') or '',
        )
    return dict(schema='g7_frozen_manifest_v1', route_count=len(entries),
                entries=entries)


def verify_payload(routes, manifest, body_only_checks=True):
    """Check a candidate payload against the frozen manifest.

    Returns ``dict(pass, violations, counts)``.  Every violation carries the
    route id and the reason.  This is the *Fixed-Layer + Fixed-Transition*
    verifier used at every accepted checkpoint and at final acceptance.
    """
    entries = manifest['entries']
    violations = []
    ids = {int(route['route_id']): route for route in routes}
    if len(ids) != int(manifest['route_count']):
        violations.append(dict(kind='route_count', got=len(ids),
                               expected=int(manifest['route_count'])))
    for rid_key, entry in entries.items():
        rid = int(rid_key)
        route = ids.get(rid)
        if route is None:
            violations.append(dict(kind='route_missing', route_id=rid))
            continue
        parts = route.get('parts') or []
        if [part.get('kind') for part in parts] != entry['part_kinds']:
            violations.append(dict(kind='part_kinds_changed', route_id=rid,
                                   got=[part.get('kind') for part in parts],
                                   expected=entry['part_kinds']))
            continue
        body_index = entry['body_index']
        if body_index is not None:
            z = float(parts[body_index]['z_mm'])
            if abs(z - float(entry['body_z'])) > 1e-9:
                violations.append(dict(kind='body_height_changed',
                                       route_id=rid, got=z,
                                       expected=entry['body_z']))
        for index, signature in entry['frozen_parts'].items():
            index = int(index)
            if index >= len(parts):
                violations.append(dict(kind='frozen_part_missing',
                                       route_id=rid, index=index))
                continue
            if _part_signature(parts[index]) != signature:
                violations.append(dict(kind='frozen_part_changed',
                                       route_id=rid, index=index,
                                       part_kind=parts[index].get('kind')))
        for key in ('layer_sequence', 'layer_z_sequence', 'layers_used'):
            expected = entry.get(key)
            if expected is not None and _round(route.get(key)) != expected:
                violations.append(dict(kind=f'{key}_changed', route_id=rid,
                                       got=_round(route.get(key)),
                                       expected=expected))
                break
        if int(route.get('n_transitions') or 0) != entry['n_transitions']:
            violations.append(dict(kind='n_transitions_changed',
                                   route_id=rid))
        for key in ('start_z_mm', 'end_z_mm', 'direct'):
            expected = entry.get(key)
            got = route.get(key)
            if isinstance(expected, float):
                if got is None or abs(float(got) - expected) > 1e-9:
                    violations.append(dict(kind=f'{key}_changed', route_id=rid,
                                           got=got, expected=expected))
            elif got != expected:
                violations.append(dict(kind=f'{key}_changed', route_id=rid,
                                       got=got, expected=expected))
    return dict(schema='g7_fixed_verify_v1', **{'pass': not violations},
                violation_count=len(violations),
                violations=violations[:200],
                checked_routes=len(ids))


def write_manifest(path, manifest):
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(manifest, handle, indent=1, ensure_ascii=False)
    return path


def load_manifest(path):
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)
