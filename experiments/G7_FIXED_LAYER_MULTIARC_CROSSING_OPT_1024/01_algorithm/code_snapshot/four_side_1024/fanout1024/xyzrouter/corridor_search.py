# -*- coding: utf-8 -*-
"""Coarse XY corridor planning for the XYZ joint router.

The board is discretised on a coarse grid (``cell`` mm, default 2.5 mm) only for
*planning*: an A* search finds low-occupancy corridors through the flat geometry
of one physical height, and the resulting corridor cost is used to re-rank the
exact R15 candidate chains produced by the motion-primitive family library.
The discretisation never decides legality - every accepted path is re-built with
exact R15 primitives and checked against the true 3D world.
"""
from __future__ import annotations

import heapq
import math

from . import motion_primitives as MP

CELL_MM = 2.5


def cell_key(point, cell=CELL_MM):
    return (int(math.floor(float(point[0]) / cell)),
            int(math.floor(float(point[1]) / cell)))


def occupancy_grid(plane_prims, cell=CELL_MM, margin=0.12):
    """``{cell: count}`` of the flat primitives of one physical height."""
    grid = {}
    for _rid, prims in plane_prims.items():
        for prim in prims:
            if prim.get('kind') == 'line':
                xs = (prim['p0'][0], prim['p1'][0])
                ys = (prim['p0'][1], prim['p1'][1])
            else:
                radius = float(prim['radius'])
                cx, cy = prim['center']
                xs = (cx - radius, cx + radius)
                ys = (cy - radius, cy + radius)
            x0 = int(math.floor((min(xs) - margin) / cell))
            x1 = int(math.floor((max(xs) + margin) / cell))
            y0 = int(math.floor((min(ys) - margin) / cell))
            y1 = int(math.floor((max(ys) + margin) / cell))
            for ix in range(x0, x1 + 1):
                for iy in range(y0, y1 + 1):
                    grid[(ix, iy)] = grid.get((ix, iy), 0) + 1
    return grid


def astar(start, goal, grid, cell=CELL_MM, board=150.0,
          occupied_cost=25.0, turn_cost=1.5):
    """Coarse 8-connected A* corridor between two world points."""
    start_key = cell_key(start, cell)
    goal_key = cell_key(goal, cell)
    limit = int(math.ceil(board / cell)) + 1
    neighbours = ((1, 0), (-1, 0), (0, 1), (0, -1),
                  (1, 1), (1, -1), (-1, 1), (-1, -1))
    open_heap = [(0.0, 0.0, start_key, None)]
    best = {start_key: 0.0}
    parent = {}
    while open_heap:
        estimate, cost, key, previous = heapq.heappop(open_heap)
        if key in best and cost > best[key] + 1e-9:
            continue
        parent.setdefault(key, previous)
        if key == goal_key:
            path = []
            node = key
            while node is not None:
                path.append(node)
                node = parent.get(node)
            return list(reversed(path))
        for dx, dy in neighbours:
            nxt = (key[0] + dx, key[1] + dy)
            if not (0 <= nxt[0] <= limit and 0 <= nxt[1] <= limit):
                continue
            step = math.hypot(dx * cell, dy * cell)
            penalty = occupied_cost * min(3, int(grid.get(nxt, 0)))
            if previous is not None:
                previous_step = (key[0] - previous[0], key[1] - previous[1])
                if (previous_step[0], previous_step[1]) != (dx, dy):
                    penalty += turn_cost
            new_cost = cost + step + penalty
            if new_cost + 1e-9 < best.get(nxt, float('inf')):
                best[nxt] = new_cost
                heuristic = math.dist((nxt[0] * cell, nxt[1] * cell),
                                      (goal_key[0] * cell, goal_key[1] * cell))
                heapq.heappush(open_heap,
                               (new_cost + heuristic, new_cost, nxt, key))
    return None


def corridor_score(primitives, grid, cell=CELL_MM, step=0.5):
    """Cost of one exact chain: corridor occupancy + length (lower is better)."""
    occupied = 0
    samples = 0
    for prim in primitives:
        length = MP._prim_length(prim)
        count = max(2, int(math.ceil(length / step)))
        for index in range(count + 1):
            t = index / count
            if prim['kind'] == 'line':
                point = (prim['p0'][0] + (prim['p1'][0] - prim['p0'][0]) * t,
                         prim['p0'][1] + (prim['p1'][1] - prim['p0'][1]) * t)
            else:
                angle = (float(prim['start_angle'])
                         + float(prim['sweep']) * t)
                point = (prim['center'][0] + float(prim['radius']) * math.cos(angle),
                         prim['center'][1] + float(prim['radius']) * math.sin(angle))
            samples += 1
            if grid.get(cell_key(point, cell), 0):
                occupied += 1
    if not samples:
        return float('inf')
    return float(occupied) / samples * 100.0 + MP.path_length(primitives) * 0.001


def select_corridors(candidates, grid, cell=CELL_MM, keep=4):
    """Re-rank exact candidate chains by their coarse corridor cost."""
    scored = []
    for record in candidates:
        score = corridor_score(record['body'], grid, cell=cell)
        item = dict(record)
        item['corridor_cost'] = round(score, 6)
        scored.append(item)
    scored.sort(key=lambda item: (item['corridor_cost'], item.get('crossings', 0)))
    return scored[:max(1, int(keep))]
