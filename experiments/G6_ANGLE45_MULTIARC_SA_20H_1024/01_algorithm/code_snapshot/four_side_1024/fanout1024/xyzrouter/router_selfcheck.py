# -*- coding: utf-8 -*-
"""Self-check of the XYZ search machinery on a real route of the 2409 baseline.

Proves: exact R15 motion primitives, heading-aware state, corridor planning,
joint XY+Z search (both XY and Z change) and exact acceptance.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024.xyzrouter import experiment as E
from four_side_1024.fanout1024.xyzrouter import local_reroute as LR
from four_side_1024.fanout1024.xyzrouter import motion_primitives as MP
from four_side_1024.fanout1024.xyzrouter import route_builder as RB
from four_side_1024.fanout1024.xyzrouter import route_state as RS
from four_side_1024.fanout1024.xyzrouter import world_adapter as WA
from four_side_1024.fanout1024.xyzrouter import xyz_search as XS
from four_side_1024.fanout1024.xyzrouter import corridor_search as CS

OUT = Path(ROOT) / 'outputs' / 'manual_c4_new_connectivity' / \
    'XYZ_JOINT_G123_1024' / 'router_validation' / 'selfcheck'
OUT.mkdir(parents=True, exist_ok=True)

report = dict(started=time.strftime('%Y-%m-%dT%H:%M:%S'))

# ---- 1. exact motion primitives -------------------------------------------
chain = MP.chain((10.0, 20.0), (0.0, 1.0),
                 [('L', 30.0), ('Q', 1), ('L', 25.0), ('Q', 1), ('L', 12.0)])
MP.validate_chain(chain['primitives'], (10.0, 20.0), (0.0, 1.0),
                  chain['end'], chain['heading'])
radii = sorted({round(float(prim['radius']), 9)
                for prim in chain['primitives'] if prim['kind'] == 'arc'})
report['motion_primitives'] = dict(
    primitives=len(chain['primitives']),
    length_mm=round(chain['length_mm'], 6),
    end=[round(v, 6) for v in chain['end']],
    heading=[round(v, 6) for v in chain['heading']],
    arc_radii=radii,
    exact_r15=bool(radii == [15.0]),
)

# ---- 2. heading-aware state ----------------------------------------------
state = RS.SearchState(x=10.0, y=20.0, z=-0.15, heading=(0.0, 1.0))
advanced = state.advance(chain['primitives'], chain['length_mm'], 10.0,
                         chain['end'], chain['heading'])
report['route_state'] = dict(start=state.pose(), key=state.key(),
                             end=advanced.pose(), length_mm=advanced.length_mm)

# ---- 3. corridor planning on a real crowded height -----------------------
baseline, world = E.load_state(None, log=lambda *_a, **_k: None)
report['baseline'] = dict(dir=baseline['dir'], crossings=int(world.total))
grid = CS.occupancy_grid(world.plane_routes(-0.15))
start = (5.0, 5.0)
goal = (145.0, 145.0)
t0 = time.time()
path = CS.astar(start, goal, grid)
report['corridor_search'] = dict(
    cell_mm=CS.CELL_MM, occupied_cells=len(grid),
    astar_cells=(None if path is None else len(path)),
    seconds=round(time.time() - t0, 3),
    free_ratio=None if not path else round(
        sum(1 for key in path if not grid.get(key)) / len(path), 4))

# ---- 4. joint XY+Z search on the real highest-crossing route -------------
rid = 158
row = world.row(rid)
before = world.route(rid)
old_events = sum(world.route_plane_events(rid, z) for z in world.groups(rid))
t0 = time.time()
combos = XS.plan_combos(world, rid)
record = XS.beam_search(world, rid, beam=3)
seconds = time.time() - t0
if record is not None:
    applied = LR.apply(world, record)
    old_xy = RB.body_xy_signature(before)
    new_xy = RB.body_xy_signature(world.route(rid))
    report['joint_search'] = dict(
        route_id=int(rid), seconds=round(seconds, 3),
        combos_prescreened=len(combos),
        beam=3,
        old_layer=int(before.get('target_layer')),
        new_layer=int(world.route(rid).get('target_layer')),
        old_z=float(before.get('target_z_mm')),
        new_z=float(world.route(rid).get('target_z_mm')),
        old_crossings=int(old_events),
        delta=int(record['delta']),
        xy_changed=bool(old_xy != new_xy),
        family=record.get('family'),
        corridor_cost=record.get('corridor_cost'),
        old_body_length_mm=round(
            sum(float(p.get('length_mm') or 0) for p in before['parts']
                if p['kind'] == 'flat'), 6),
        new_body_length_mm=round(
            sum(float(p.get('length_mm') or 0) for p in world.route(rid)['parts']
                if p['kind'] == 'flat'), 6),
        total_after=int(world.total),
    )
else:
    report['joint_search'] = dict(route_id=int(rid), result='no candidate')
report['search_space'] = XS.search_space_summary()

# ---- 5. exact 3D check of the new route ----------------------------------
violations = world.validate_all()
report['world_validation'] = dict(
    valid=violations['valid'], violations=len(violations['violations']),
    kinds=violations['violation_kinds'], total_after=int(world.total))
report['finished'] = time.strftime('%Y-%m-%dT%H:%M:%S')
(OUT / 'router_selfcheck.json').write_text(
    json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=1))
