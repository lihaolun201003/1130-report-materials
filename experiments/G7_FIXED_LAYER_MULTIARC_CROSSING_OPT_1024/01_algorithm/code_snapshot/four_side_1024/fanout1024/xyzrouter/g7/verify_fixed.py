# -*- coding: utf-8 -*-
"""G7 fixed-structure verifier (Fixed-Layer + Fixed-Transition acceptance).

Compares a candidate payload with the frozen G6 manifest extracted from the real
``routes_l3d.json``: every route's part-kind sequence, all non-body geometry
(R15 transitions, interface lead flats, native-3D excursion parts), the real body
height, layer sequences and transition counts must be unchanged.  Only the body
flat of the 527 modifiable standard routes may differ.

Usage::

    python -m ...g7.verify_fixed \
        --reference <G6 routes_l3d.json> --candidate <G7 routes_l3d.json> \
        --out <dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os

from . import frozen as FR


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', required=True,
                        help='frozen G6 routes_l3d.json')
    parser.add_argument('--candidate', required=True,
                        help='G7 candidate routes_l3d.json')
    parser.add_argument('--out', required=True)
    parser.add_argument('--manifest', default=None,
                        help='optional pre-built frozen manifest JSON')
    args = parser.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    ref_path = os.path.abspath(args.reference)
    cand_path = os.path.abspath(args.candidate)
    if args.manifest and os.path.exists(args.manifest):
        manifest = FR.load_manifest(args.manifest)
    else:
        with open(ref_path, encoding='utf-8') as handle:
            reference = json.load(handle)
        manifest = FR.build_manifest(reference['routes'])
    with open(cand_path, encoding='utf-8') as handle:
        candidate = json.load(handle)
    result = FR.verify_payload(candidate['routes'], manifest)
    changed = []
    entries = manifest['entries']
    ref_routes = {}
    if os.path.exists(ref_path):
        with open(ref_path, encoding='utf-8') as handle:
            ref_routes = {int(route['route_id']): route
                          for route in json.load(handle)['routes']}
    cand_routes = {int(route['route_id']): route
                   for route in candidate['routes']}
    for rid_key, entry in entries.items():
        rid = int(rid_key)
        if entry['kind'] != 'modifiable' or rid not in ref_routes:
            continue
        index = entry['body_index']
        before = FR._part_signature(ref_routes[rid]['parts'][index])
        after = FR._part_signature(cand_routes[rid]['parts'][index])
        if before != after:
            changed.append(rid)
    payload = dict(
        schema='g7_fixed_verify_v1',
        reference=ref_path, candidate=cand_path,
        reference_sha256=_sha256(ref_path),
        candidate_sha256=_sha256(cand_path),
        manifest_route_count=len(entries),
        modifiable_routes=sum(1 for entry in entries.values()
                              if entry['kind'] == 'modifiable'),
        frozen_routes=sum(1 for entry in entries.values()
                          if entry['kind'] != 'modifiable'),
        frozen_classification=dict(
            direct=sum(1 for entry in entries.values()
                       if entry['kind'] == 'direct'),
            manual=sum(1 for entry in entries.values()
                       if entry['kind'] == 'manual'),
            native=sum(1 for entry in entries.values()
                       if entry['kind'] == 'native')),
        changed_body_routes=len(changed),
        changed_route_ids=changed[:200],
        **{'pass': result['pass']},
        violation_count=result['violation_count'],
        violations=result['violations'][:100],
    )
    path = os.path.join(args.out, 'fixed_structure_verification.json')
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle, indent=1, ensure_ascii=False)
    print(json.dumps({key: payload[key] for key in
                      ('pass', 'violation_count', 'changed_body_routes',
                       'modifiable_routes', 'frozen_routes')},
                     ensure_ascii=False))
    return 0 if payload['pass'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
