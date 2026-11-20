# -*- coding: utf-8 -*-
"""Fanout-First 1 mm/50 um router.

Pipeline: assign target layers -> build true R15 port fanouts -> build a new
layer-wise 2D body between the landing points -> assemble the full 3D route ->
validate in the corrected 50 um world.

This is deliberately a decomposed fanout-first router, not a claim of native
global 3D search.  Old 2D routes are not used as the body.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

from . import bidirectional_50um_assignment as A50
from . import glass_1mm_process_rules as RULES
from ..l3d.world import World
from ..l3d.layers import build_stack
from ..fsd25d.path3d import make_transition
from ..legacy_geometry import _orthogonal_quarters

V4 = A50.V4
OUT = Path(A50.OUT).parent / 'FANOUT_FIRST_Z2_MANUAL_VERIFIED_1024'
LAYERS = OrderedDict(A50.PHYSICAL_LAYERS)
Z_INTERFACE = {1: 0.0, 2: 0.5}


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, obj):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str),
                    encoding='utf-8')


# ---------------------------------------------------------------- assignment
Z2_TEMPLATES = {
    'Z2-U1': {
        'side_kind': 'NS', 'layer': 10,
        'pairs': [('01', '08'), ('02', '08'), ('02', '07'), ('03', '07'),
                  ('09', '16'), ('09', '15'), ('10', '15'), ('10', '14')],
    },
    'Z2-U2': {
        'side_kind': 'EW', 'layer': 11,
        'pairs': [('01', '08'), ('02', '08'), ('02', '07'), ('03', '07'),
                  ('09', '16'), ('09', '15'), ('10', '15'), ('10', '14')],
    },
    'Z2-U3': {
        'side_kind': 'NS', 'layer': 12,
        'pairs': [('01', '16'), ('02', '15'), ('03', '14'),
                  ('04', '13'), ('05', '12'), ('06', '11')],
    },
    'Z2-U4': {
        'side_kind': 'EW', 'layer': 13,
        'pairs': [('01', '16'), ('02', '15'), ('03', '14'),
                  ('04', '13'), ('05', '12'), ('06', '11')],
    },
}


def _side_ok(rec, kind):
    return rec['source_endpoint'][0] in kind and rec['target_endpoint'][0] in kind


def match_z2_manual(records):
    matched = {}
    for rec in records:
        if rec.get('plane') != 'z2':
            continue
        rid = int(rec['route_id'])
        se = rec['source_endpoint'].split(':')
        te = rec['target_endpoint'].split(':')
        pair = tuple(sorted((se[0], te[0])))
        for group, spec in Z2_TEMPLATES.items():
            kind = spec['side_kind']
            if not _side_ok(rec, kind):
                continue
            for a, b in spec['pairs']:
                sides = (('N', 'S') if kind == 'NS' else ('E', 'W'))
                valid = False
                for s in sides:
                    if pair == tuple(sorted((s + a, s + b))):
                        valid = True
                if valid and rid not in matched:
                    matched[rid] = (group, spec['layer'])
                    break
            if rid in matched:
                break
    return matched


def build_assignment():
    records = read_json(V4 / 'routes_1024.json')['routes']
    old_assign = {int(r['route_id']): r for r in read_json(A50.OUT.parent / 'MANUAL_20L_FIXED_ASSIGNMENT_FULL/assignment_1024.json')['rows']}
    phase = read_json(A50.OUT.parent / 'MANUAL_LAYERS_20L_PROTO/phaseB.json')['results']
    z1_manual = {int(k): int(v['layer']) for k, v in phase.items()}
    z2_manual = match_z2_manual(records)
    rows = []
    for rec in sorted(records, key=lambda r: int(r['route_id'])):
        rid = int(rec['route_id'])
        plane = rec['plane']
        old_layer = None
        if plane == 'z1' and rid in z1_manual:
            old_layer = z1_manual[rid]
            group = f'Z1-U{old_layer - 1}'
            target = old_layer  # L2-L5
            kind = 'z1_manual_u'
        elif plane == 'z1':
            rel = rec['relation']
            group = 'Z1-NS' if rel == 'opposite' and rec['source_endpoint'][0] in 'NS' else 'Z1-EW'
            target = 6 if group == 'Z1-NS' else 7
            kind = 'z1_other'
            group = 'Z1-rel-NS' if target == 6 else 'Z1-rel-EW'
        elif rid in z2_manual:
            group, target = z2_manual[rid]
            kind = 'z2_manual_u'
        elif old_assign[rid].get('target_layer') is None:
            group = 'Z2-interface'
            target = None
            kind = 'z2_interface'
        else:
            # distribute other Z2 over L8,L9,L14-L19 in route order
            group = f"Z2-other-{old_assign[rid].get('target_layer')}"
            kind = 'z2_other'
            target = None
        if plane == 'z2' and target is None and kind != 'z2_interface':
            pool = [8, 9, 14, 15, 16, 17, 18, 19]
            target = pool[rid % len(pool)]
        rows.append(dict(route_id=rid, plane=plane, kind=kind, group=group,
                         source_endpoint=rec['source_endpoint'],
                         target_endpoint=rec['target_endpoint'],
                         source_side=rec['source_side'],
                         target_side=rec['target_side'],
                         relation=rec['relation'],
                         source_row=int(rec['source_row']),
                         target_row=int(rec['target_row']),
                         target_layer=target,
                         target_z=(Z_INTERFACE[2] if target is None
                                   else LAYERS[target]),
                         manual_group=(group if kind in
                                       ('z1_manual_u', 'z2_manual_u') else '')))
    return rows


# ---------------------------------------------------------------- fanout
def _endpoint(rec, role):
    if role == 'source':
        return (float(rec['source_endpoint'].split(':')[1]),) if False else None
    return None


def endpoint_xy(rec, role):
    # endpoint strings are connector:row:col; use canonical routing coordinates
    # from the V4 record's source/target port if available; otherwise use the
    # campaign endpoint table.
    from ..v3c4.inputs import ENDPOINTS
    ep = rec['source_endpoint'] if role == 'source' else rec['target_endpoint']
    return ENDPOINTS[ep]['routing_xy']


def inward_dir(rec, role):
    from ..v3c4.inputs import ENDPOINTS
    ep = rec['source_endpoint'] if role == 'source' else rec['target_endpoint']
    return tuple(ENDPOINTS[ep]['inward'])


def fanout(rec, role, target_z, target_layer, lead=2.0):
    """Return (flat_part | None, transition_part | None, landing, direction)."""
    p = endpoint_xy(rec, role)
    d = inward_dir(rec, role)
    z0 = Z_INTERFACE[1 if rec['plane'] == 'z1' else 2]
    if abs(target_z - z0) < 1e-12:
        return None, None, (p[0], p[1]), d
    s = (p[0] + d[0] * lead, p[1] + d[1] * lead)
    trans = make_transition(s, d, z0, target_z, radius=15.0)
    flat = dict(kind='flat', layer_id=1, z_mm=z0, length_mm=lead,
                primitives=[dict(kind='line', p0=[p[0], p[1]],
                                 p1=[s[0], s[1]], layer=0)])
    return flat, trans, tuple(trans['end']), d


# ---------------------------------------------------------------- 2D body
def _path_candidates(A, dA, B, dB):
    # Leads must be long enough to host R15 corners.  The landing tangents are
    # preserved by straight entry/exit runs; candidate tracks then explore the
    # board instead of relying on one midpoint dogleg.
    leads = (16.0, 22.0, 32.0, 48.0)
    for lead in leads:
        A0 = (A[0] + dA[0] * lead, A[1] + dA[1] * lead)
        B0 = (B[0] - dB[0] * lead, B[1] - dB[1] * lead)
        conns = []
        if abs(A0[0] - B0[0]) < 1e-9 or abs(A0[1] - B0[1]) < 1e-9:
            conns.append([A0, B0])
        else:
            conns.append([A0, (B0[0], A0[1]), B0])
            conns.append([A0, (A0[0], B0[1]), B0])
        for track in (15.0, 30.0, 50.0, 75.0, 100.0, 120.0, 135.0):
            conns.append([A0, (track, A0[1]), (track, B0[1]), B0])
            conns.append([A0, (A0[0], track), (B0[0], track), B0])
        for mx in (0.25, 0.5, 0.75):
            x = A0[0] + (B0[0] - A0[0]) * mx
            y = A0[1] + (B0[1] - A0[1]) * mx
            conns.append([A0, (x, A0[1]), (x, B0[1]), B0])
            conns.append([A0, (A0[0], y), (B0[0], y), B0])
        for conn in conns:
            pts = [A, A0] + conn[1:-1] + [B0, B]
            clean = []
            for p in pts:
                if not clean or math.dist(p, clean[-1]) > 1e-9:
                    clean.append(p)
            if len(clean) < 2:
                continue
            try:
                prims = _orthogonal_quarters(clean, 15.0)
            except Exception:
                continue
            yield [dict(x) for x in prims]


def main_path(A, dA, B, dB):
    for prims in _path_candidates(A, dA, B, dB):
        yield prims


def make_route_candidates(rec, target_layer, target_z, candidate_budget=256):
    """Yield full Fanout-First routes over distinct lead and body candidates."""
    z0s = Z_INTERFACE[1 if rec['plane'] == 'z1' else 2]
    leads = (16.0, 22.0, 32.0, 48.0)
    yielded = set()
    emitted = 0
    for src_lead in leads:
        sflat, strans, A, dA = fanout(rec, 'source', target_z,
                                      target_layer, src_lead)
        for dst_lead in leads:
            tflat, ttrans, B, dB_raw = fanout(rec, 'target', target_z,
                                              target_layer, dst_lead)
            dB = (-dB_raw[0], -dB_raw[1])
            for prims in _path_candidates(A, dA, B, dB):
                signature = tuple((p.get('kind'), tuple(p.get('p0', ())),
                                   tuple(p.get('p1', ()))) for p in prims)
                if signature in yielded:
                    continue
                yielded.add(signature)
                route = _assemble(rec, target_layer, target_z, sflat,
                                  strans, prims, ttrans, tflat,
                                  source_lead=src_lead, target_lead=dst_lead)
                yield route
                emitted += 1
                if emitted >= int(candidate_budget):
                    return


def make_route(rec, target_layer, target_z, src_lead=2.0, dst_lead=2.0):
    """Compatibility wrapper returning the first generated full route."""
    for route in make_route_candidates(rec, target_layer, target_z):
        return route, None
    return None, 'no_body'


def _assemble(rec, target_layer, target_z, sflat, strans, body, ttrans, tflat,
              source_lead=2.0, target_lead=2.0):
    parts = []
    if sflat is not None:
        parts.append(sflat)
        parts.append(strans)
    parts.append(dict(kind='flat', layer_id=int(target_layer), z_mm=float(target_z),
                      length_mm=0.0, primitives=body))
    if ttrans is not None:
        parts.append(ttrans); parts.append(tflat)
    # target fanout must be reverse of the target port; constructed separately
    if ttrans is not None:
        tparts = _target_parts(rec, target_z, target_layer, target_lead)
        parts[-2:] = tparts
    length = sum(float(p.get('length_mm') or 0.0) for p in parts)
    return dict(route_id=int(rec['route_id']), plane=rec['plane'],
                relation=rec['relation'],
                source_endpoint=rec['source_endpoint'],
                target_endpoint=rec['target_endpoint'],
                source_side=rec['source_side'],
                target_side=rec['target_side'],
                start_z_mm=float(Z_INTERFACE[1 if rec['plane'] == 'z1' else 2]),
                end_z_mm=float(Z_INTERFACE[1 if rec['plane'] == 'z1' else 2]),
                layer_sequence=[1, int(target_layer), 1],
                layer_z_sequence=[Z_INTERFACE[1 if rec['plane'] == 'z1' else 2],
                                  float(target_z),
                                  Z_INTERFACE[1 if rec['plane'] == 'z1' else 2]],
                n_transitions=sum(1 for p in parts if p['kind'] == 'transition'),
                lifted=True, layers_used=[1, int(target_layer)],
                length_mm=length, xy_length_mm=length,
                z_span_mm=abs(float(target_z) - Z_INTERFACE[
                    1 if rec['plane'] == 'z1' else 2]),
                parts=parts)


def _target_parts(rec, target_z, target_layer, lead=2.0):
    from ..v3c4.inputs import ENDPOINTS
    ep = ENDPOINTS[rec['target_endpoint']]
    p = ep['routing_xy']; d = ep['inward']
    z0 = Z_INTERFACE[1 if rec['plane'] == 'z1' else 2]
    s = (p[0] + d[0] * lead, p[1] + d[1] * lead)
    trans = make_transition(s, d, z0, target_z, radius=15.0)
    # forward route arrives at trans.end (landing) with -d, then reverse transition
    arrival = trans['end']
    rev = make_transition(arrival, (-d[0], -d[1]), target_z, z0, radius=15.0)
    sflat = dict(kind='flat', layer_id=1, z_mm=z0, length_mm=lead,
                 primitives=[dict(kind='line', p0=rev['end'],
                                  p1=[p[0], p[1]], layer=0)])
    return [rev, sflat]


# ---------------------------------------------------------------- world
class FanoutWorld:
    def __init__(self):
        self.stack = build_stack('ablation_custom',
                                 heights={int(k): float(v) for k, v in LAYERS.items()})
        self.world = World(self.stack, clearance=RULES.MIN_3D_CLEARANCE_MM)
        self.success = OrderedDict()
        self.failures = []

    def add(self, route):
        v = self.world.check_route(route)
        if v:
            return v
        self.world.add_route(route)
        self.success[int(route['route_id'])] = route
        return None


def run_experiment(rows, limit=None, mode='full'):
    world = FanoutWorld()
    failures = []
    order = sorted(rows, key=lambda r: 0 if r['kind'] in
                   ('z1_manual_u', 'z2_manual_u') else 1)
    for index, row in enumerate(order, 1):
        if limit and index > limit:
            break
        rec = row['_record']
        if row['kind'] == 'fanout_only':
            continue
        route, reason = make_route(rec, row['target_layer'], row['target_z'])
        if route is None:
            failures.append(dict(route_id=row['route_id'], reason=reason,
                                 phase='fanout' if 'transition' in str(reason)
                                 else 'body'))
            continue
        v = world.add(route)
        if v:
            failures.append(dict(route_id=row['route_id'], reason=v[0].get('kind'),
                                 detail=v[0], phase='world'))
    return world, failures


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    assignment = OUT / 'assignment_1024.csv'
    if not assignment.is_file():
        raise FileNotFoundError(
            f'verified assignment is required and will not be regenerated: {assignment}')
    result = run_assigned(assignment, OUT)
    summary = {key: value for key, value in result.items()
               if key not in ('routes', 'world', 'failures')}
    summary['failure_count'] = len(result['failures'])
    write_json(OUT / 'run_summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return result


def run_assigned(assignment_csv, out_dir, candidate_budget=160,
                 rr_rounds=2, rr_rip=2):
    """Run full Fanout-First routing from the verified assignment table.

    Each route gets fresh port fanouts and a new R15 body candidate.  Failed
    routes are retried against the live 3D world; bounded blocker rip-up then
    retries the failed route and restores/rebuilds the ripped routes.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    records = {int(r['route_id']): r
               for r in read_json(V4 / 'routes_1024.json')['routes']}
    with open(assignment_csv, encoding='utf-8-sig', newline='') as fh:
        rows = list(csv.DictReader(fh))
    if len(rows) != 1024 or len({int(r['route_id']) for r in rows}) != 1024:
        raise ValueError('expected exactly 1024 unique assignment route ids')
    for row in rows:
        rid = int(row['route_id'])
        if rid not in records:
            raise ValueError(f'assignment route_id {rid} is absent from source routes')
        row['_record'] = records[rid]
        row['target_layer'] = int(row['physical_layer'])
        row['target_z'] = float(row['target_z_mm'])
    world = FanoutWorld()
    selected, failures, attempted = {}, {}, Counter()

    def try_route(row, budget):
        rid = int(row['route_id'])
        attempted[rid] += 1
        blockers = set()
        for index, route in enumerate(make_route_candidates(
                row['_record'], row['target_layer'], row['target_z'], budget), 1):
            violations = world.world.check_route(route)
            if not violations:
                world.world.add_route(route)
                route['status'] = 'routed'
                route['candidate_id'] = f"{rid}-body-{index}"
                selected[rid] = route
                failures.pop(rid, None)
                return True, blockers
            for violation in violations:
                if violation.get('other_route') is not None:
                    blockers.add(int(violation['other_route']))
                blockers.update(int(v) for v in violation.get('blockers', []))
        failures[rid] = dict(route_id=rid, phase='layerwise_2d_or_world',
                             reason='candidate_budget_exhausted',
                             candidate_budget=budget,
                             blockers=sorted(blockers))
        return False, blockers

    ordered = sorted(rows, key=lambda r: (
        0 if str(r.get('manual_group', '')).startswith(('Z1-U', 'Z2-U')) else 1,
        int(r['route_id'])))
    candidate_audit = []
    for i, row in enumerate(ordered, 1):
        ok, blockers = try_route(row, candidate_budget)
        rid = int(row['route_id'])
        candidate_audit.append(dict(route_id=rid, target_layer=row['target_layer'],
                                    candidate_budget=candidate_budget,
                                    selected=ok, blockers=sorted(blockers)))
        if i % 64 == 0:
            print(f'[fanout-first] {i}/1024 routed={len(selected)} '
                  f'failed={len(failures)}', flush=True)

    rr_history = []
    row_by_id = {int(r['route_id']): r for r in rows}
    for rr in range(1, int(rr_rounds) + 1):
        gained = 0
        pending = sorted(failures)
        for rid in pending:
            failure = failures.get(rid)
            if failure is None:
                continue
            blockers = [b for b in failure.get('blockers', [])
                        if b in selected][:int(rr_rip)]
            if not blockers:
                # Try an expanded candidate window without disturbing accepted routes.
                ok, _ = try_route(row_by_id[rid], candidate_budget * (rr + 1))
                gained += int(ok)
                continue
            old = {b: selected.pop(b) for b in blockers}
            for b in blockers:
                world.world.remove_route(b)
            ok, _ = try_route(row_by_id[rid], candidate_budget * (rr + 1))
            restored = True
            if ok:
                for b in blockers:
                    rebuilt, _ = try_route(row_by_id[b], candidate_budget)
                    if not rebuilt:
                        restored = False
                        break
                if restored:
                    gained += 1
                    continue
            # Transaction rollback: remove any partial replacements and put the
            # exact previous accepted geometry back into the world.
            for b in blockers:
                if b in selected:
                    selected.pop(b)
                    world.world.remove_route(b)
            if rid in selected:
                selected.pop(rid)
                world.world.remove_route(rid)
            failures[rid] = failure
            for b, old_route in old.items():
                world.world.add_route(old_route)
                selected[b] = old_route
        rr_history.append(dict(round=rr, attempted=len(pending), gained=gained,
                               routed=len(selected), failed=len(failures)))
        if gained == 0:
            break

    endpoints = []
    for row in rows:
        rec = row['_record']; target_z = float(row['target_z_mm'])
        for role in ('source', 'target'):
            xy = endpoint_xy(rec, role); direction = inward_dir(rec, role)
            z0 = Z_INTERFACE[1 if rec['plane'] == 'z1' else 2]
            endpoints.append(dict(route_id=int(row['route_id']),
                endpoint_role=role, source_xyz=[*xy, z0],
                target_layer=int(row['physical_layer']), target_z=target_z,
                candidate_id='lead-16/22/32/48',
                landing_candidates=[[xy[0]+lead*direction[0],
                                     xy[1]+lead*direction[1], target_z]
                                    for lead in (16.0,22.0,32.0,48.0)],
                landing_tangent=list(direction)))
    write_json(out_dir / 'layerwise_endpoints/endpoints.json', endpoints)
    write_json(out_dir / 'fanout_candidates.json', candidate_audit)
    write_json(out_dir / 'fanout_selected.json',
               {str(rid): route.get('candidate_id') for rid, route in selected.items()})
    write_json(out_dir / 'layerwise_routes/routes.json',
               {str(rid): route for rid, route in selected.items()})
    write_json(out_dir / 'routes_l3d.json', dict(
        schema='four_side_1024_v2_l3d_routes_v1', topology='V2',
        route_count=len(rows), routes=[selected.get(int(r['route_id']),
            dict(route_id=int(r['route_id']), status='failed',
                 reason=failures.get(int(r['route_id']), {}).get('reason',
                                                                 'not_attempted')))
            for r in rows], layer_stack=world.stack.to_dict(),
        process=dict(radius_mm=15.0, clearance_mm=RULES.MIN_3D_CLEARANCE_MM,
                     width_mm=0.05, mode='corrected_50um')))
    write_json(out_dir / 'failed_routes.json',
               dict(total=len(failures), failures=list(failures.values())))
    write_json(out_dir / 'rrr_summary.json', rr_history)
    return dict(routed=len(selected), failed=len(failures),
                attempts=sum(attempted.values()), rrr=rr_history,
                failures=list(failures.values()), routes=selected,
                world=world)


if __name__ == '__main__':
    main()
