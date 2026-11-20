# -*- coding: utf-8 -*-
"""G6 geometry: dissect a 3-D route, regenerate its MultiArc body, rebuild it.

The frozen per-physical-layer 2-D router (``fanout1024/layer2d.py``) already
contains the *complete* planar MultiArc candidate grammar (U / opposite /
adjacent families, quarter arcs, R15 short-S, detours, loops, staircases) and
the exact pose-preserving canonical-frame machinery.  G6 does **not**
reimplement it: this module

1. pulls one routed body chain apart into its two port/landing poses and the
   body plane (``dissect_route``);
2. re-enumerates *all* layer2d candidate bodies for a given pose
   (``enumerate_specs`` / ``build_bodies``) -- the frozen body is always inside
   this set (verified on the frozen G4 payload), so the grammar is identical;
3. rebuilds a complete, structurally valid route: either by swapping the body
   primitives in place (``with_body``) or by reconstructing the two R15 port
   transitions for a *new* body height / new port lead-out length
   (``assemble_lifted`` / ``assemble_direct``).

Everything here is pure geometry on plain dicts; legality is decided by the G5
exact model (``g5.model``) and the batch evaluator (``g5.batch``) elsewhere.
"""
from __future__ import annotations

import copy
import math
import random
from collections import OrderedDict

from ..g5 import model as G5
from ..g5 import candidates as C5
from ... import layer2d as L2
from ....fsd25d.path3d import make_transition

#: process minimum of the interface lead-out flat (fanout planner contract)
MIN_LEAD_MM = 0.25
#: lead-out lengths the fanout planner itself uses
LEAD_CHOICES = (0.25, 1.0, 2.0, 4.0, 8.0, 16.0)
#: pose acceptance tolerance (structure_issues / validator use 1e-6)
POSE_TOL = 1e-6


# ---------------------------------------------------------------------------
# 1. route dissection
# ---------------------------------------------------------------------------
def _vec(value):
    return (float(value[0]), float(value[1]))


def _prim_chain(prims):
    """Sanity-check a flat primitive chain and return its end poses."""
    if not prims:
        return None
    for index in range(1, len(prims)):
        if math.dist(_vec(prims[index - 1]['p1']),
                     _vec(prims[index]['p0'])) > 1e-9:
            return None
    A = _vec(prims[0]['p0'])
    B = _vec(prims[-1]['p1'])
    dA = L2._start_tangent(prims[0])
    arrival = L2._end_tangent(prims[-1])
    return dict(A=A, B=B, dA=dA, arrival=arrival,
                dB=(-arrival[0], -arrival[1]))


def dissect_route(route):
    """Return the body-pose description of one route, or ``None``.

    Supported shapes (the only ones present in the frozen G4/G5 payload):

    * ``direct``  -- one flat part, no transition       (n_transitions == 0)
    * ``lifted``  -- flat/transition/flat/transition/flat, one body flat part
                     (n_transitions == 2, non-native-3D)
    """
    if not isinstance(route, dict):
        return None
    parts = route.get('parts') or []
    ntr = int(route.get('n_transitions') or 0)
    if ntr == 0:
        flats = [i for i, part in enumerate(parts)
                 if part.get('kind') == 'flat']
        if len(flats) != 1:
            return None
        index = flats[0]
        prims = parts[index].get('primitives') or []
        ends = _prim_chain(prims)
        if ends is None:
            return None
        z = float(parts[index]['z_mm'])
        return dict(kind='direct', body_index=index, z_body=z, prims=prims,
                    zs=z, zt=z, lead_s=0.0, lead_t=0.0,
                    Ps=ends['A'], Pt=ends['B'], ds=ends['dA'],
                    dt=(-ends['dB'][0], -ends['dB'][1]), **ends)
    if len(parts) != 5:
        return None
    if [part.get('kind') for part in parts] != [
            'flat', 'transition', 'flat', 'transition', 'flat']:
        return None
    lead_in, up, body, down, lead_out = parts
    prims = body.get('primitives') or []
    ends = _prim_chain(prims)
    if ends is None:
        return None
    try:
        ds = _vec(up['direction'])
        dt = _vec(down['direction'])
        zs = float(lead_in['z_mm'])
        zt = float(lead_out['z_mm'])
        z_body = float(body['z_mm'])
        lead_s = float(L2._path_length(lead_in.get('primitives') or []))
        lead_t = float(L2._path_length(lead_out.get('primitives') or []))
        Ps = _vec(lead_in['primitives'][0]['p0'])
        Pt = _vec(lead_out['primitives'][-1]['p1'])
        up_end = _vec(up['end'])
        down_start = _vec(down['start'])
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    # the lead flats must be axis-aligned lines of the declared length
    if math.dist(Ps, _vec(lead_in['primitives'][0]['p1'])) > 1e-9 + lead_s:
        return None
    if (math.dist(up_end, ends['A']) > POSE_TOL
            or math.dist(down_start, ends['B']) > POSE_TOL):
        return None
    if (L2._tangent_gap(ds, ends['dA']) > 1e-6
            or L2._tangent_gap(dt, ends['arrival']) > 1e-6):
        return None
    return dict(kind='lifted', body_index=2, z_body=z_body, prims=prims,
                zs=zs, zt=zt, lead_s=lead_s, lead_t=lead_t,
                Ps=Ps, Pt=Pt, ds=ds, dt=dt, **ends)


def body_pose(dissected, z_body=None, lead_s=None, lead_t=None):
    """Landing poses ``A/B/dA/dB`` for a (possibly new) height / lead pair.

    ``A = Ps + (lead_s + footprint(z_body - zs)) * ds`` and
    ``B = Pt - (lead_t + footprint(z_body - zt)) * dt`` -- the same closure the
    frozen fanout planner uses (``fsd25d.path3d.make_transition``).
    """
    z_body = float(dissected['z_body'] if z_body is None else z_body)
    lead_s = float(dissected['lead_s'] if lead_s is None else lead_s)
    lead_t = float(dissected['lead_t'] if lead_t is None else lead_t)
    fps = L2.footprint_mm(z_body - dissected['zs'])
    fpt = L2.footprint_mm(z_body - dissected['zt'])
    ds, dt = dissected['ds'], dissected['dt']
    Ps, Pt = dissected['Ps'], dissected['Pt']
    A = (Ps[0] + (lead_s + fps) * ds[0], Ps[1] + (lead_s + fps) * ds[1])
    B = (Pt[0] - (lead_t + fpt) * dt[0], Pt[1] - (lead_t + fpt) * dt[1])
    return dict(A=A, B=B, dA=dissected['dA'],
                dB=(-dissected['arrival'][0], -dissected['arrival'][1]),
                z_body=z_body, lead_s=lead_s, lead_t=lead_t)


def body_task(dissected, route):
    """Canonical-frame task record understood by ``layer2d.canonical_frame``."""
    pose = body_pose(dissected)
    return dict(route_id=int(route['route_id']), A=pose['A'], dA=pose['dA'],
                B=pose['B'], dB=pose['dB'],
                relation=route.get('relation') or '',
                manual_group=route.get('manual_group') or '',
                source_side=route.get('source_side'),
                target_side=route.get('target_side'))


# ---------------------------------------------------------------------------
# 2. MultiArc body enumeration (the frozen layer2d grammar)
# ---------------------------------------------------------------------------
def enumerate_specs(dissected, route, cfg=None, phase=0.0, pose=None):
    """All ``layer2d`` candidate specs for one body pose.

    Returns ``(frame, specs, error)``.  ``phase`` shifts the deterministic
    ladders exactly like the router's ``ordering_seed`` phase does.
    """
    base = dict(L2.DEFAULT_CFG, **(cfg or {}))
    task = body_task(dissected, route)
    if pose is not None:
        task.update(A=pose['A'], dA=pose['dA'], B=pose['B'], dB=pose['dB'])
    frame, error = L2.canonical_frame(task)
    if frame is None:
        return None, [], error
    kind = frame['kind']
    try:
        if kind == 'same':
            specs = list(L2._same_side_specs(frame, base, phase))
            try:
                specs += list(L2._library_u_specs(task, frame))
            except Exception:  # noqa: BLE001 - library family is optional
                pass
        elif kind == 'opposite':
            specs = list(L2._opposite_specs(frame, base, phase))
        else:
            specs = list(L2._adjacent_specs(frame, base, phase))
    except Exception:  # noqa: BLE001 - a broken family must not kill the SA
        return frame, [], 'spec_error'
    return frame, specs, None


def build_bodies(frame, specs, max_build=800, rng=None, self_check=False):
    """Build candidate body chains (world primitives) from specs.

    Applies exactly the frozen router's build gate (``_build_candidate``:
    pose / R15 / continuity / board).  The (expensive) self-clearance audit is
    only run when ``self_check`` is true; the proposer runs it on the sampled
    candidates instead of on every enumerated body.
    """
    out = []
    order = list(specs)
    if rng is not None and len(order) > 1:
        rng.shuffle(order)
    for spec in order:
        world, reason = L2._build_candidate(spec, frame)
        if world is None:
            continue
        if self_check and not L2._self_clearance_ok(world):
            continue
        out.append((str(spec.get('family')), dict(spec.get('params') or {}),
                    world))
        if len(out) >= max_build:
            break
    return out


def sample_bodies(bodies, count, rng):
    if not bodies:
        return []
    if len(bodies) <= count:
        return list(bodies)
    return rng.sample(bodies, count)


def sample_self_clear(bodies, count, rng):
    """Sample ``count`` bodies and keep only self-clear ones (cheap audit)."""
    picked = []
    for family, params, world in sample_bodies(bodies, count * 2, rng):
        if L2._self_clearance_ok(world):
            picked.append((family, params, world))
        if len(picked) >= count:
            break
    return picked


# ---------------------------------------------------------------------------
# 3. route re-assembly
# ---------------------------------------------------------------------------
def classify_prim(prim):
    """Return a JSON primitive with the frozen primitive key order."""
    prim = dict(prim)
    prim.setdefault('layer', 0)
    return prim


def _flat_part(z_mm, primitives, layer_id, tag, length_mm=None):
    prims = [classify_prim(prim) for prim in primitives]
    length = (float(L2._path_length(prims)) if length_mm is None
              else float(length_mm))
    return dict(kind='flat', layer_id=int(layer_id), z_mm=float(z_mm),
                length_mm=length, primitives=prims, tag=str(tag))


def _lead_part(p0, p1, z_mm, lead_mm):
    """Interface lead-out flat, traversed from ``p0`` to ``p1``."""
    prim = dict(kind='line',
                p0=[float(p0[0]), float(p0[1])],
                p1=[float(p1[0]), float(p1[1])], layer=0)
    return _flat_part(z_mm, [prim], 1, 'lead', length_mm=lead_mm)


def _body_z_layer(z_body):
    pid = G5.plane_of_z(z_body)
    if pid is None:
        return None
    return int(pid)


def with_body(route, dissected, body_world):
    """Swap only the body primitives of an existing route (same pose/height)."""
    if dissected is None or not body_world:
        return None
    start = _vec(body_world[0]['p0'])
    end = _vec(body_world[-1]['p1'])
    if math.dist(start, dissected['A']) > POSE_TOL:
        return None
    if math.dist(end, dissected['B']) > POSE_TOL:
        return None
    new = copy.deepcopy(route)
    parts = new['parts']
    index = dissected['body_index']
    if parts[index].get('kind') != 'flat':
        return None
    parts[index]['primitives'] = [classify_prim(prim) for prim in body_world]
    parts[index]['length_mm'] = float(L2._path_length(
        parts[index]['primitives']))
    parts[index]['z_mm'] = float(dissected['z_body'])
    return C5._finalise(new)


def assemble_direct(template, dissected, z_body, body_world):
    """Rebuild a direct (no-transition) route on one interface row."""
    if dissected is None or dissected['kind'] != 'direct' or not body_world:
        return None
    layer = _body_z_layer(z_body)
    if layer is None:
        return None
    if abs(z_body - dissected['zs']) > 1e-9:
        return None
    start = _vec(body_world[0]['p0'])
    end = _vec(body_world[-1]['p1'])
    if (math.dist(start, dissected['A']) > POSE_TOL
            or math.dist(end, dissected['B']) > POSE_TOL):
        return None
    new = copy.deepcopy(template)
    new['parts'] = [_flat_part(z_body, body_world, layer, 'body')]
    new['start_z_mm'] = float(z_body)
    new['end_z_mm'] = float(z_body)
    new['lead_source_mm'] = 0.0
    new['lead_target_mm'] = 0.0
    new['n_transitions'] = 0          # must be coherent before metadata rebuild
    new['direct'] = True
    return C5._finalise(new)


def assemble_lifted(template, dissected, z_body, lead_s, lead_t, body_world,
                    pose=None):
    """Rebuild a lifted route with (new) body height / lead lengths.

    The rail is exactly the frozen structure::

        lead(flat, zs) -> up transition -> body(flat, z_body)
                       -> down transition -> lead(flat, zt)

    with both transitions the analytic two-arc R15 S-curve of
    ``fsd25d.path3d.make_transition``.  Also upgrades a ``direct`` route to a
    lifted one (the G4 ``lift_direct`` inverse move).
    """
    if dissected is None or not body_world:
        return None
    zs, zt = float(dissected['zs']), float(dissected['zt'])
    if abs(z_body - zs) < 1e-9 or abs(z_body - zt) < 1e-9:
        return None                       # zero-height transition is not a route
    lead_s = float(lead_s)
    lead_t = float(lead_t)
    if lead_s < MIN_LEAD_MM - 1e-12 or lead_t < MIN_LEAD_MM - 1e-12:
        return None
    pose = pose if pose is not None else body_pose(
        dissected, z_body=z_body, lead_s=lead_s, lead_t=lead_t)
    start = _vec(body_world[0]['p0'])
    end = _vec(body_world[-1]['p1'])
    if (math.dist(start, pose['A']) > POSE_TOL
            or math.dist(end, pose['B']) > POSE_TOL):
        return None
    ds, dt = dissected['ds'], dissected['dt']
    Ps, Pt = dissected['Ps'], dissected['Pt']
    start_s = (Ps[0] + lead_s * ds[0], Ps[1] + lead_s * ds[1])
    start_t = (Pt[0] - lead_t * dt[0], Pt[1] - lead_t * dt[1])
    up = make_transition(start_s, ds, zs, z_body, radius=L2.R15)
    down = make_transition(end, dt, z_body, zt, radius=L2.R15)
    up['kind'] = 'transition'
    down['kind'] = 'transition'
    up['tag'] = 'fanout'
    down['tag'] = 'fanout'
    if (math.dist(_vec(up['end']), pose['A']) > POSE_TOL
            or math.dist(_vec(down['end']), start_t) > POSE_TOL):
        return None
    layer = _body_z_layer(z_body)
    if layer is None:
        return None
    parts = [
        _lead_part(Ps, start_s, zs, lead_s),
        up,
        _flat_part(z_body, body_world, layer, 'body'),
        down,
        _lead_part(start_t, Pt, zt, lead_t),
    ]
    new = copy.deepcopy(template)
    new['parts'] = parts
    new['start_z_mm'] = zs
    new['end_z_mm'] = zt
    new['lead_source_mm'] = lead_s
    new['lead_target_mm'] = lead_t
    # ``rebuild_metadata`` derives the body flats from ``n_transitions``: a
    # stale 0 (direct template) would treat both lead flats as body plateaus and
    # corrupt layer_sequence / layer_z_sequence.  Keep it coherent.
    new['n_transitions'] = sum(1 for part in parts
                               if part.get('kind') == 'transition')
    new['n_mid_transitions'] = 0
    new['native_3d'] = False
    new['mid_transitions'] = []
    new['direct'] = False
    return C5._finalise(new)


# ---------------------------------------------------------------------------
# 4. regeneration driver
# ---------------------------------------------------------------------------
def body_signature(prims):
    return tuple((prim.get('kind'),
                  round(float(prim['p0'][0]), 6), round(float(prim['p0'][1]), 6),
                  round(float(prim['p1'][0]), 6), round(float(prim['p1'][1]), 6))
                 for prim in (prims or ()))


def regenerate(route, dissected, mode, rng, cfg=None, z_body=None, leads=None,
               sample=6, max_build=800, phase=None):
    """Yield ``(label, new_route)`` MultiArc body candidates for one route.

    ``mode``:

    * ``body``      -- same height, same leads (pure planar MultiArc change)
    * ``lead``      -- same height, new port lead-out lengths (transition move)
    * ``reheight``  -- new body height (transitions rebuilt), lead choice
    * ``lift``      -- direct route lifted onto a body height
    """
    if dissected is None or not dissected['prims']:
        return []
    current = body_signature(dissected['prims'])
    out = []
    if mode == 'body':
        pose = body_pose(dissected)
        frame, specs, err = enumerate_specs(
            dissected, route, cfg=cfg, phase=0.0 if phase is None else phase,
            pose=pose)
        if frame is None:
            return []
        bodies = build_bodies(frame, specs, max_build=max_build, rng=rng)
        for family, params, world in sample_self_clear(bodies, sample, rng):
            if body_signature(world) == current:
                continue
            if dissected['kind'] == 'direct':
                new = assemble_direct(route, dissected, dissected['z_body'],
                                      world)
                tag = 'direct'
            else:
                new = with_body(route, dissected, world)
                tag = 'body'
            if new is not None:
                out.append((f'multiarc:{tag}:{family}', new))
        return out
    if mode == 'lead':
        if dissected['kind'] != 'lifted' or leads is None:
            return []
        lead_s, lead_t = float(leads[0]), float(leads[1])
        if (abs(lead_s - dissected['lead_s']) < 1e-9
                and abs(lead_t - dissected['lead_t']) < 1e-9):
            return []
        pose = body_pose(dissected, z_body=dissected['z_body'],
                         lead_s=lead_s, lead_t=lead_t)
        frame, specs, err = enumerate_specs(dissected, route, cfg=cfg,
                                            phase=0.0 if phase is None else phase,
                                            pose=pose)
        if frame is None:
            return []
        bodies = build_bodies(frame, specs, max_build=max_build, rng=rng)
        for family, params, world in sample_self_clear(bodies, sample, rng):
            new = assemble_lifted(route, dissected, dissected['z_body'],
                                  lead_s, lead_t, world, pose=pose)
            if new is not None:
                out.append((f'multiarc:lead:{family}:{lead_s:g}/{lead_t:g}',
                            new))
        return out
    if mode in ('reheight', 'lift'):
        if z_body is None:
            return []
        z_body = float(z_body)
        if abs(z_body - dissected['z_body']) < 1e-9:
            return []
        lead_s, lead_t = dissected['lead_s'], dissected['lead_t']
        if leads is not None:
            lead_s, lead_t = float(leads[0]), float(leads[1])
        lead_s = max(lead_s, MIN_LEAD_MM)
        lead_t = max(lead_t, MIN_LEAD_MM)
        pose = body_pose(dissected, z_body=z_body, lead_s=lead_s,
                         lead_t=lead_t)
        frame, specs, err = enumerate_specs(dissected, route, cfg=cfg,
                                            phase=0.0 if phase is None else phase,
                                            pose=pose)
        if frame is None:
            return []
        bodies = build_bodies(frame, specs, max_build=max_build, rng=rng)
        for family, params, world in sample_self_clear(bodies, sample, rng):
            new = assemble_lifted(route, dissected, z_body, lead_s, lead_t,
                                  world, pose=pose)
            if new is not None:
                out.append((f'multiarc:{mode}:{family}:z={z_body:+.3f}',
                            new))
        return out
    return out
