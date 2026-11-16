# -*- coding: utf-8 -*-
"""Small self-contained XY geometry renderer for the FINAL ablation figures.

Deliberately independent of the archived plotting stack: it reads the route
files directly, samples every R15 arc analytically (no polyline shortcuts) and
draws the real stored primitives, so a figure can never show a "smoothed"
path that the router did not build.

Public helpers
--------------
``load_run(run_dir)``      -> dict(routes, rows, events, plane_counts, ...)
``flat_chains(route)``     -> [(z_mm, [primitives])]
``sample_chain(prims)``    -> (N,2) array in XY
``draw_window(ax, ...)``   -> draw every route inside an XY window
"""
from __future__ import annotations

import json
import math
from collections import Counter, OrderedDict
from pathlib import Path

import numpy as np

BOARD = 150.0
COLOR_LINE = '#78909c'
COLOR_ARC = '#00838f'
COLOR_HL_ON = '#1565c0'
COLOR_HL_OFF = '#c62828'
COLOR_CROSS = '#e53935'
COLOR_OTHER = '#b0bec5'


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except ValueError:
        return default


def load_run(run_dir):
    run_dir = Path(run_dir)
    payload = read_json(run_dir / 'routes_l3d.json', {}) or {}
    routes = OrderedDict()
    for route in payload.get('routes') or ():
        routes[int(route['route_id'])] = route
    # ``best_valid/`` holds the routes only; the engine writes the crossing
    # statistics next to it, so fall back to the parent directory
    stats = read_json(run_dir / 'crossing_stats.json')
    if stats is None:
        stats = read_json(run_dir.parent / 'crossing_stats.json', {}) or {}
    summary = read_json(run_dir / 'summary.json')
    if summary is None:
        summary = read_json(run_dir.parent / 'summary.json', {}) or {}
    return dict(dir=str(run_dir), routes=routes,
                events=stats.get('crossing_events') or [],
                per_route={int(k): int(v) for k, v in
                           (stats.get('per_route_crossings') or {}).items()},
                summary=summary, payload=payload)


def flat_chains(route):
    """``[(z_mm, [primitive, ...]), ...]`` of the flat parts of one route."""
    chains = []
    for part in route.get('parts') or ():
        if part.get('kind') != 'flat':
            continue
        prims = part.get('primitives') or ()
        if not prims:
            continue
        chains.append((float(part['z_mm']), [dict(p) for p in prims]))
    return chains


def chain_at(route, z_mm, tol=1e-9):
    """All flat primitives of one route on the physical height ``z_mm``."""
    prims = []
    for z, chain in flat_chains(route):
        if abs(z - float(z_mm)) <= tol:
            prims.extend(chain)
    return prims


def sample_prim(prim, samples=48):
    """XY samples of one primitive (arcs sampled analytically)."""
    if prim.get('kind') == 'line':
        return np.asarray([prim['p0'], prim['p1']], dtype=float)
    cx, cy = prim['center']
    radius = float(prim['radius'])
    start = float(prim['start_angle'])
    sweep = float(prim['sweep'])
    angles = start + sweep * np.linspace(0.0, 1.0, samples)
    return np.asarray([[cx + radius * math.cos(a), cy + radius * math.sin(a)]
                       for a in angles], dtype=float)


def sample_chain(prims, samples=48):
    """Single polyline of a chain of primitives (empty array when empty)."""
    arrays = [sample_prim(prim, samples) for prim in prims or ()]
    if not arrays:
        return np.zeros((0, 2), dtype=float)
    return np.vstack(arrays)


def chain_length(prims):
    total = 0.0
    for prim in prims or ():
        if prim.get('kind') == 'line':
            (x0, y0), (x1, y1) = prim['p0'], prim['p1']
            total += math.hypot(x1 - x0, y1 - y0)
        else:
            total += float(prim['radius']) * abs(float(prim['sweep']))
    return total


def route_summary(route, z_mm):
    """Counts/lengths of one route on one physical height."""
    prims = chain_at(route, z_mm)
    return dict(n_arcs=sum(1 for p in prims if p.get('kind') == 'arc'),
                n_lines=sum(1 for p in prims if p.get('kind') == 'line'),
                length_mm=round(chain_length(prims), 6))


def window(arrays, x0, x1, y0, y1):
    """True when a sampled chain enters the XY window."""
    if arrays.size == 0:
        return False
    return bool(arrays[:, 0].max() >= x0 and arrays[:, 0].min() <= x1
                and arrays[:, 1].max() >= y0 and arrays[:, 1].min() <= y1)


def draw_window(ax, run, z_mm, x0, x1, y0, y1, highlight=None,
                highlight_color=COLOR_HL_ON, background_alpha=0.35,
                draw_crossings=True, linewidth_others=0.9):
    """Draw every route of one height inside an XY window.

    ``highlight`` is a dict ``{route_id: color}`` of routes drawn on top.
    Returns the number of background routes drawn.
    """
    highlight = dict(highlight or {})
    drawn = 0
    for rid, route in run['routes'].items():
        prims = chain_at(route, z_mm)
        if not prims:
            continue
        xy = sample_chain(prims)
        if not window(xy, x0, x1, y0, y1):
            continue
        if rid in highlight:
            continue
        ax.plot(xy[:, 0], xy[:, 1], color=COLOR_OTHER, linewidth=linewidth_others,
                alpha=background_alpha, zorder=2, solid_capstyle='round')
        drawn += 1
    for rid, color in sorted(highlight.items()):
        route = run['routes'].get(int(rid))
        if route is None:
            continue
        prims = chain_at(route, z_mm)
        if not prims:
            continue
        # draw lines and arcs with distinct styles, arcs thicker
        for prim in prims:
            xy = sample_prim(prim)
            if prim.get('kind') == 'arc':
                ax.plot(xy[:, 0], xy[:, 1], color=color, linewidth=3.0,
                        zorder=6, solid_capstyle='round')
            else:
                ax.plot(xy[:, 0], xy[:, 1], color=color, linewidth=1.9,
                        zorder=5)
    if draw_crossings:
        points = []
        for event in run['events']:
            if abs(float(event.get('z_mm') or 0.0) - float(z_mm)) > 1e-9:
                continue
            x = float(event.get('x_mm') or 0.0)
            y = float(event.get('y_mm') or 0.0)
            if x0 <= x <= x1 and y0 <= y <= y1:
                points.append((x, y))
        if points:
            arr = np.asarray(points)
            ax.scatter(arr[:, 0], arr[:, 1], marker='x', s=34,
                       c=COLOR_CROSS, linewidths=1.0, zorder=9)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect('equal')
    ax.grid(alpha=0.18)
    return drawn


def events_for_route(run, rid):
    rid = int(rid)
    return [event for event in run['events']
            if rid in (int(event.get('route_a') or -1),
                       int(event.get('route_b') or -1))]


def route_bounds(route, z_mm, pad=6.0):
    prims = chain_at(route, z_mm)
    if not prims:
        return None
    xy = sample_chain(prims)
    return (max(0.0, xy[:, 0].min() - pad), min(BOARD, xy[:, 0].max() + pad),
            max(0.0, xy[:, 1].min() - pad), min(BOARD, xy[:, 1].max() + pad))


def crossing_count_by_height(run):
    counts = Counter()
    for event in run['events']:
        counts[round(float(event.get('z_mm') or 0.0), 6)] += 1
    return counts
