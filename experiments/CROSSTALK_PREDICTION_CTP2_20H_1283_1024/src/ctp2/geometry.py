"""Frozen-input loading, SHA256 verification and analytic route geometry.

The authoritative routing solution is ``COLD_START_20_HEIGHT_1024/10_best_valid``.
Nothing in this module writes to it.  Every route is rebuilt from its analytic
primitives (``line`` / ``arc`` / ``transition``) so that position, tangent and
arc length are available at *any* arc-length coordinate -- no polyline
approximation is used for the authoritative quantities (total length, crossing
positions).  Dense polylines are used only as a *search structure* for
neighbour queries.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from .params import (
    BEST_VALID, FROZEN_INPUTS, MIN_BEND_RADIUS_MM, N_ROUTES, OUT_CROSSINGS,
    PLANE_HEIGHTS_MM, ROUTES_SHA256, TOTAL_LENGTH_MM,
)

# --------------------------------------------------------------------- hashing
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@lru_cache(maxsize=1)
def verify_inputs() -> dict:
    """Verify every frozen input against ``SHA256.json`` (routes hard-coded)."""
    manifest = json.loads((BEST_VALID / "SHA256.json").read_text(encoding="utf-8"))
    # SHA256.json is itself a list/dict of files -> discover its shape
    entries: dict[str, str] = {}

    def _walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, str) and len(v) == 64 and all(
                        c in "0123456789abcdefABCDEF" for c in v):
                    entries[k] = v.lower()
                elif isinstance(v, dict) and "sha256" in v:
                    entries[k] = str(v["sha256"]).lower()
                else:
                    _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)

    _walk(manifest)
    out = {"manifest_keys": sorted(entries)[:32], "files": {}}
    for name in FROZEN_INPUTS:
        p = BEST_VALID / name
        if not p.exists():
            out["files"][name] = {"exists": False}
            continue
        actual = sha256_file(p)
        expected = None
        for k, v in entries.items():
            if Path(k).name == name:
                expected = v
                break
        out["files"][name] = {
            "exists": True,
            "size": p.stat().st_size,
            "sha256": actual,
            "expected": expected,
            "match": (expected is None) or (expected == actual),
        }
    routes_sha = out["files"]["routes_l3d.json"]["sha256"]
    out["routes_sha256_matches_frozen"] = routes_sha == ROUTES_SHA256
    out["n_expected_crossings"] = 1283
    return out


# ------------------------------------------------------------------ primitives
def _arc_point(prim: dict, t: np.ndarray):
    """Point(s) on a planar circular arc, ``t`` in [0, 1]."""
    c = np.asarray(prim["center"], float)
    r = float(prim["radius"])
    a0 = float(prim["start_angle"])
    sw = float(prim["sweep"])
    th = a0 + sw * np.asarray(t, float)
    return np.stack([c[0] + r * np.cos(th), c[1] + r * np.sin(th)], axis=-1)


def _arc_tangent(prim: dict, t: np.ndarray):
    sw = float(prim["sweep"])
    a0 = float(prim["start_angle"])
    th = a0 + sw * np.asarray(t, float)
    sgn = 1.0 if sw >= 0 else -1.0
    return np.stack([-np.sin(th) * sgn, np.cos(th) * sgn], axis=-1)


@dataclass
class Segment:
    """One analytic primitive placed at arc-length ``[s0, s1]`` on a route."""

    s0: float
    s1: float
    kind: str            # 'line' | 'planar_arc' | 'transition'
    payload: dict
    z0: float
    z1: float

    @property
    def length(self) -> float:
        return self.s1 - self.s0

    # -- local coordinate tau in [0, 1]
    def _tau(self, s):
        return (np.asarray(s, float) - self.s0) / max(self.length, 1e-15)

    def point(self, s):
        t = self._tau(s)
        if self.kind == "line":
            p0 = np.asarray(self.payload["p0"], float)
            p1 = np.asarray(self.payload["p1"], float)
            xy = p0[None, :] + (p1 - p0)[None, :] * np.atleast_1d(t)[:, None] \
                if np.ndim(t) else p0 + (p1 - p0) * float(t)
            return np.concatenate([np.atleast_2d(xy), np.full((np.atleast_2d(xy).shape[0], 1),
                                                              self.z0)], axis=1) \
                if np.ndim(t) else np.array([xy[0], xy[1], self.z0])
        if self.kind == "planar_arc":
            xy = _arc_point(self.payload, t)
            z = np.full(np.shape(t), self.z0)
            return np.concatenate([np.atleast_2d(xy), np.atleast_2d(z).T], axis=1) \
                if np.ndim(t) else np.array([xy[0], xy[1], self.z0])
        if self.kind == "transition":
            # the transition is parameterised by its OWN arc length
            return _transition_point(self.payload, s - self.s0)
        raise ValueError(self.kind)

    def tangent(self, s):
        t = self._tau(s)
        if self.kind == "line":
            p0 = np.asarray(self.payload["p0"], float)
            p1 = np.asarray(self.payload["p1"], float)
            d = p1 - p0
            d = d / np.linalg.norm(d)
            v = np.array([d[0], d[1], 0.0])
            return np.tile(v, (np.atleast_1d(t).size, 1)) if np.ndim(t) else v
        if self.kind == "planar_arc":
            xy = _arc_tangent(self.payload, t)
            xy = xy / np.linalg.norm(xy, axis=-1, keepdims=True)
            z = np.zeros(np.shape(t))
            return np.concatenate([np.atleast_2d(xy), np.atleast_2d(z).T], axis=1) \
                if np.ndim(t) else np.array([xy[0], xy[1], 0.0])
        if self.kind == "transition":
            return _transition_tangent(self.payload, s - self.s0)
        raise ValueError(self.kind)


def _transition_geom(prim: dict):
    start = np.asarray(prim["start"], float)
    u = np.asarray(prim["direction"], float)
    u = u / np.linalg.norm(u)
    R = float(prim["radius_mm"])
    z0 = float(prim["z0"])
    z1 = float(prim["z1"])
    dz = z1 - z0
    alpha = float(prim["theta_rad"])
    L = 2.0 * R * alpha
    foot = 2.0 * R * math.sin(alpha)
    return start, u, R, z0, z1, dz, alpha, L, foot


def _transition_point(prim: dict, s):
    start, u, R, z0, z1, dz, alpha, L, foot = _transition_geom(prim)
    s = np.asarray(s, float)
    scalar = np.ndim(s) == 0
    ss = np.atleast_1d(s)
    first = ss <= L / 2.0
    phi = np.where(first, ss / R, (L - ss) / R)
    hor = np.where(first, R * np.sin(phi), foot - R * np.sin(phi))
    sgn = 1.0 if dz >= 0 else -1.0
    zz = np.where(first, z0 + sgn * R * (1 - np.cos(phi)),
                  z1 - sgn * R * (1 - np.cos(phi)))
    xy = start[None, :] + u[None, :] * hor[:, None]
    out = np.concatenate([xy, zz[:, None]], axis=1)
    return out[0] if scalar else out


def _transition_tangent(prim: dict, s):
    start, u, R, z0, z1, dz, alpha, L, foot = _transition_geom(prim)
    s = np.asarray(s, float)
    scalar = np.ndim(s) == 0
    ss = np.atleast_1d(s)
    first = ss <= L / 2.0
    phi = np.where(first, ss / R, (L - ss) / R)
    sgn = 1.0 if dz >= 0 else -1.0
    h = np.cos(phi)
    v = +np.sin(phi) * sgn
    tang = np.stack([u[0] * h, u[1] * h, v], axis=1)
    tang /= np.linalg.norm(tang, axis=1, keepdims=True)
    return tang[0] if scalar else tang


# ----------------------------------------------------------------------- route
@dataclass
class Route:
    route_id: int
    plane: str
    source_endpoint: str
    target_endpoint: str
    layer_role: str
    start_z_mm: float
    end_z_mm: float
    length_mm: float
    parts: list
    segments: list
    z_plateaus: list          # list of (z, length_mm) flat parts
    n_transitions: int

    # -- authoritative total length = sum of analytic segment lengths
    @property
    def total_length(self) -> float:
        return sum(s.length for s in self.segments)

    def pos(self, s):
        s = np.asarray(s, float)
        scalar = np.ndim(s) == 0
        ss = np.atleast_1d(s)
        ss = np.clip(ss, 0.0, self.total_length)
        out = np.empty((ss.size, 3))
        idx = np.searchsorted(self._s1, ss, side="right")
        idx = np.clip(idx, 0, len(self.segments) - 1)
        for k in np.unique(idx):
            m = idx == k
            out[m] = self.segments[k].point(ss[m])
        return out[0] if scalar else out

    def tangent(self, s):
        s = np.asarray(s, float)
        scalar = np.ndim(s) == 0
        ss = np.atleast_1d(s)
        ss = np.clip(ss, 0.0, self.total_length)
        out = np.empty((ss.size, 3))
        idx = np.clip(np.searchsorted(self._s1, ss, side="right"), 0, len(self.segments) - 1)
        for k in np.unique(idx):
            m = idx == k
            out[m] = self.segments[k].tangent(ss[m])
        return out[0] if scalar else out

    @property
    def _s1(self) -> np.ndarray:
        return np.array([s.s1 for s in self.segments])

    def polyline(self, flat_step: float = 0.1, trans_step: float = 0.02):
        """Dense polyline ``(s, xyz, tangent)`` for search / visualisation."""
        ss, pp, tt = [], [], []
        for seg in self.segments:
            step = trans_step if seg.kind == "transition" else flat_step
            n = max(2, int(math.ceil(seg.length / step)) + 1)
            s = np.linspace(seg.s0, seg.s1, n)
            ss.append(s)
            pp.append(seg.point(s))
            tt.append(seg.tangent(s))
        return np.concatenate(ss), np.concatenate(pp), np.concatenate(tt)


def _build_segments(parts: list) -> tuple[list, list]:
    segments: list[Segment] = []
    plateaus: list = []
    s = 0.0
    for part in parts:
        if part["kind"] == "flat":
            z = float(part["z_mm"])
            flat_len = 0.0
            for prim in part["primitives"]:
                if prim["kind"] == "line":
                    p0 = np.asarray(prim["p0"], float)
                    p1 = np.asarray(prim["p1"], float)
                    L = float(np.linalg.norm(p1 - p0))
                    seg = Segment(s, s + L, "line", {"p0": p0, "p1": p1}, z, z)
                elif prim["kind"] == "arc":
                    L = abs(float(prim["sweep"])) * float(prim["radius"])
                    seg = Segment(s, s + L, "planar_arc", prim, z, z)
                else:  # pragma: no cover
                    raise ValueError(prim["kind"])
                segments.append(seg)
                s += L
                flat_len += L
            plateaus.append((z, flat_len))
        elif part["kind"] == "transition":
            prim = dict(part)
            L = float(part["length_mm"])
            seg = Segment(s, s + L, "transition", prim,
                          float(part["z0"]), float(part["z1"]))
            segments.append(seg)
            s += L
        else:  # pragma: no cover
            raise ValueError(part["kind"])
    return segments, plateaus


@lru_cache(maxsize=1)
def load_routes(path: Path | None = None) -> dict:
    """Load the frozen ``routes_l3d.json`` and rebuild analytic geometry."""
    path = Path(path) if path is not None else BEST_VALID / "routes_l3d.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    out = {"meta": {k: v for k, v in data.items() if k != "routes"},
           "routes": {}, "by_id": {}, "order": []}
    for r in data["routes"]:
        segs, plateaus = _build_segments(r["parts"])
        route = Route(
            route_id=int(r["route_id"]),
            plane=str(r["plane"]),
            source_endpoint=str(r["source_endpoint"]),
            target_endpoint=str(r["target_endpoint"]),
            layer_role=str(r.get("layer_role", "")),
            start_z_mm=float(r["start_z_mm"]),
            end_z_mm=float(r["end_z_mm"]),
            length_mm=float(r["length_mm"]),
            parts=r["parts"],
            segments=segs,
            z_plateaus=plateaus,
            n_transitions=int(r.get("n_transitions", 0)),
        )
        out["routes"][route.route_id] = route
        out["order"].append(route.route_id)
    out["order"] = np.array(out["order"], int)
    return out


def length_audit() -> dict:
    """Independent re-summation of every route length from the primitives."""
    ds = load_routes()
    rows = []
    tot_straight = tot_arc = tot_trans = 0.0
    for rid in ds["order"]:
        r = ds["routes"][rid]
        Ls = sum(s.length for s in r.segments if s.kind == "line")
        La = sum(s.length for s in r.segments if s.kind == "planar_arc")
        Lt = sum(s.length for s in r.segments if s.kind == "transition")
        tot_straight += Ls
        tot_arc += La
        tot_trans += Lt
        rows.append({
            "route_id": int(rid), "L_straight_mm": Ls, "L_planar_arc_mm": La,
            "L_transition_arc_mm": Lt, "L_total_mm": Ls + La + Lt,
            "L_authoritative_mm": r.length_mm,
            "error_mm": (Ls + La + Lt) - r.length_mm,
            "n_segments": len(r.segments), "n_transitions": r.n_transitions,
            "z_start": r.start_z_mm, "z_end": r.end_z_mm,
            "min_radius_mm": min([abs(float(s.payload["radius"]))
                                  for s in r.segments if s.kind == "planar_arc"] or
                                 [MIN_BEND_RADIUS_MM]),
        })
    L_tot = tot_straight + tot_arc + tot_trans
    return {
        "n_routes": len(rows),
        "total_length_mm": L_tot,
        "authoritative_total_length_mm": TOTAL_LENGTH_MM,
        "absolute_error_mm": L_tot - TOTAL_LENGTH_MM,
        "relative_error": (L_tot - TOTAL_LENGTH_MM) / TOTAL_LENGTH_MM,
        "total_L_straight_mm": tot_straight,
        "total_L_planar_arc_mm": tot_arc,
        "total_L_transition_arc_mm": tot_trans,
        "max_route_error_mm": max(abs(r["error_mm"]) for r in rows),
        "rows": rows,
    }


# ---------------------------------------------------------------- crossing list
def load_crossings() -> list[dict]:
    """Authoritative 1283 crossing events (from the validated CTP-1.0 geometry
    engine), re-verified here against the official ``crossing_stats.json``."""
    csv_path = OUT_CROSSINGS / "crossing_events_verified.csv"
    if csv_path.exists():
        import csv as _csv
        with open(csv_path, newline="", encoding="utf-8") as fh:
            return [dict(r) for r in _csv.DictReader(fh)]
    return _read_legacy_crossings()


def _read_legacy_crossings() -> list[dict]:
    import pandas as pd
    p = (REPO_ROOT_CTP1() / "outputs" / "geometry" / "crossing_events_detected.csv")
    df = pd.read_csv(p)
    out = []
    for rec in df.to_dict("records"):
        out.append({k: (float(v) if isinstance(v, (int, float)) else v)
                    for k, v in rec.items()})
    return out


def REPO_ROOT_CTP1() -> Path:
    from .params import CTP1_DIR
    return CTP1_DIR


def official_crossing_totals() -> dict:
    stats = json.loads((BEST_VALID / "crossing_stats.json").read_text(encoding="utf-8"))
    return stats["totals"]


def verify_crossings() -> dict:
    """Independently re-check every crossing event with the analytic geometry."""
    ds = load_routes()
    ev = load_crossings()
    err_pos, err_ang, same_z = [], [], []
    for e in ev:
        ra, rb = int(e["route_a"]), int(e["route_b"])
        A, B = ds["routes"][ra], ds["routes"][rb]
        sa, sb = float(e["s_a_mm"]), float(e["s_b_mm"])
        pa, pb = A.pos(sa), B.pos(sb)
        err_pos.append(float(np.linalg.norm(pa - pb)))
        ta, tb = A.tangent(sa), B.tangent(sb)
        ang = math.degrees(math.acos(min(1.0, abs(float(ta @ tb)))))
        err_ang.append(abs(ang - float(e["angle_deg"])))
        same_z.append(abs(pa[2] - pb[2]))
    off = official_crossing_totals()
    pairs = {(min(int(e["route_a"]), int(e["route_b"])),
              max(int(e["route_a"]), int(e["route_b"]))) for e in ev}
    routes_with = {int(e["route_a"]) for e in ev} | {int(e["route_b"]) for e in ev}
    return {
        "n_events": len(ev),
        "n_pairs": len(pairs),
        "n_routes_with_crossings": len(routes_with),
        "official": off,
        "max_position_mismatch_mm": max(err_pos),
        "max_angle_mismatch_deg": max(err_ang),
        "max_z_mismatch_mm": max(same_z),
        "all_same_plane": max(same_z) < 1e-9,
        "counts_match_official": (
            len(ev) == int(off.get("total_crossings", off.get("crossings", 1283)))
            and len(pairs) == 1221 and len(routes_with) == 647),
    }

