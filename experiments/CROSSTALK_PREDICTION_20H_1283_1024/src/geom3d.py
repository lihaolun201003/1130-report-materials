"""Exact 3-D centre-line geometry for the Native-3D glass-waveguide routes.

All lengths are millimetres, all angles radians.  Three analytic primitives are
supported, matching ``routes_l3d.json`` exactly:

``line``
    planar straight segment at constant ``z``.
``arc``
    planar circular arc at constant ``z``.
``transition``
    two exact circular arcs of equal radius in the vertical plane of the local
    inward direction (a G1 S-curve).  This is the fabrication primitive used by
    the 20-height router, *not* a polyline approximation.

The arc-length parameterisation is analytic: for every segment ``u`` in
``[0, 1]`` maps linearly onto ``s in [s0, s0 + length]``.  No chord
approximations are used anywhere in the length statistics.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

__all__ = ["Segment", "Route", "build_route", "build_routes"]


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n == 0.0:
        raise ValueError("zero-length vector")
    return v / n


@dataclass(slots=True)
class Segment:
    """One analytic geometric primitive of a route centre line."""

    kind: str                 # 'line' | 'arc' | 'transition'
    part_kind: str            # 'flat' | 'transition'
    tag: str                  # 'lead' | 'fanout' | 'body' | 'mid' | ''
    part_index: int
    seg_index: int
    length: float             # true arc length, mm
    s0: float                 # global route arclength at u=0
    z0: float
    z1: float
    p0: np.ndarray            # 2-D (x, y) start
    p1: np.ndarray            # 2-D (x, y) end
    center: np.ndarray | None = None
    radius: float = 0.0
    start_angle: float = 0.0
    sweep: float = 0.0
    direction: np.ndarray | None = None
    theta: float = 0.0
    sign: float = 1.0

    # ------------------------------------------------------------------ eval
    def point(self, u) -> np.ndarray:
        u_arr = np.asarray(u, dtype=float)
        scalar = u_arr.ndim == 0
        uu = np.atleast_1d(u_arr).reshape(-1)
        if self.kind == "line":
            xy = self.p0 + uu[:, None] * (self.p1 - self.p0)
            z = np.full(uu.shape, self.z0)
        elif self.kind == "arc":
            ang = self.start_angle + self.sweep * uu
            xy = self.center + self.radius * np.stack(
                [np.cos(ang), np.sin(ang)], axis=-1
            )
            z = np.full(uu.shape, self.z0)
        elif self.kind == "transition":
            xy, z = self._transition_xy_z(uu)
        else:  # pragma: no cover
            raise ValueError(self.kind)
        out = np.concatenate([xy, z[:, None]], axis=1)
        return out[0] if scalar else out.reshape(u_arr.shape + (3,))

    def _transition_xy_z(self, uu: np.ndarray):
        R = self.radius
        d = self.direction
        th = self.theta
        sgn = self.sign
        first = uu <= 0.5
        phi = np.clip(2.0 * th * uu, 0.0, th)
        xy1 = self.p0 + (R * np.sin(phi))[:, None] * d
        z1 = self.z0 + sgn * R * (1.0 - np.cos(phi))
        psi = np.clip(2.0 * th * (uu - 0.5), 0.0, th)
        # centre of the second arc: C = A + R sin(th) d - R cos(th) sgn z,
        # with A the end of the first arc = p0 + R sin(th) d, hence C_xy = p1.
        c2_xy = self.p1
        c2_z = (self.z0 + sgn * R * (1.0 - math.cos(th))
                - sgn * R * math.cos(th))
        xy2 = c2_xy + (-(R * np.sin(th - psi)))[:, None] * d
        z2 = c2_z + sgn * R * np.cos(th - psi)
        xy = np.where(first[:, None], xy1, xy2)
        z = np.where(first, z1, z2)
        return xy, z

    def tangent(self, u) -> np.ndarray:
        u_arr = np.asarray(u, dtype=float)
        scalar = u_arr.ndim == 0
        uu = np.atleast_1d(u_arr).reshape(-1)
        if self.kind == "line":
            t = np.array([*(self.p1 - self.p0) / self.length, 0.0])
            out = np.broadcast_to(t, uu.shape + (3,)).copy()
        elif self.kind == "arc":
            ang = self.start_angle + self.sweep * uu
            s = 1.0 if self.sweep >= 0 else -1.0
            out = np.concatenate(
                [s * np.stack([-np.sin(ang), np.cos(ang)], axis=-1),
                 np.zeros((uu.size, 1))], axis=1
            )
        elif self.kind == "transition":
            first = uu <= 0.5
            phi = np.clip(2.0 * self.theta * uu, 0.0, self.theta)
            psi = np.clip(2.0 * self.theta * (uu - 0.5), 0.0, self.theta)
            ang = np.where(first, phi, self.theta - psi)
            xy = np.cos(ang)[:, None] * self.direction
            out = np.concatenate([xy, (self.sign * np.sin(ang))[:, None]], axis=1)
        else:  # pragma: no cover
            raise ValueError(self.kind)
        return out[0] if scalar else out.reshape(u_arr.shape + (3,))

    def curvature(self, u) -> np.ndarray:
        u_arr = np.asarray(u, dtype=float)
        if self.kind == "line":
            out = np.zeros(np.atleast_1d(u_arr).size)
        else:
            out = np.full(np.atleast_1d(u_arr).size, 1.0 / self.radius)
        return float(out[0]) if u_arr.ndim == 0 else out.reshape(u_arr.shape)

    # ----------------------------------------------------------------- aabb
    def aabb(self) -> tuple[np.ndarray, np.ndarray]:
        """Exact 3-D axis aligned bounding box."""
        zlo, zhi = min(self.z0, self.z1), max(self.z0, self.z1)
        if self.kind in ("line", "transition"):
            lo = np.minimum(self.p0, self.p1)
            hi = np.maximum(self.p0, self.p1)
        else:  # arc
            pts = [self.p0, self.p1]
            a0, a1 = self.start_angle, self.start_angle + self.sweep
            lo_a, hi_a = min(a0, a1), max(a0, a1)
            for k in range(-8, 9):
                a = k * math.pi / 2.0
                if lo_a <= a <= hi_a:
                    pts.append(self.center + self.radius
                               * np.array([math.cos(a), math.sin(a)]))
            P = np.asarray(pts)
            lo, hi = P.min(axis=0), P.max(axis=0)
        return (np.array([lo[0], lo[1], zlo]),
                np.array([hi[0], hi[1], zhi]))


@dataclass(slots=True)
class Route:
    route_id: int
    source_endpoint: str
    target_endpoint: str
    source_side: str
    target_side: str
    plane: str
    layer_role: str
    manual_group: str
    start_z_mm: float
    target_z_mm: float
    target_plane: int
    target_plane_label: str
    n_transitions: int
    n_mid_transitions: int
    native_3d: bool
    direct: bool
    declared_length: float
    xy_length: float
    parts_json: list
    segments: list[Segment] = field(default_factory=list)
    total_length: float = 0.0
    s_breaks: np.ndarray = field(default_factory=lambda: np.zeros(1))
    aabb_lo: np.ndarray | None = None
    aabb_hi: np.ndarray | None = None

    # ------------------------------------------------------------------ eval
    def _locate(self, s: np.ndarray) -> np.ndarray:
        s = np.clip(s, 0.0, self.total_length)
        idx = np.searchsorted(self.s_breaks, s, side="right") - 1
        return np.clip(idx, 0, len(self.segments) - 1)

    def point_at_s(self, s) -> np.ndarray:
        s_arr = np.asarray(s, dtype=float)
        scalar = s_arr.ndim == 0
        ss = np.atleast_1d(s_arr).reshape(-1)
        idx = self._locate(ss)
        out = np.empty((ss.size, 3))
        for k in np.unique(idx):
            m = idx == k
            g = self.segments[int(k)]
            u = np.clip((ss[m] - g.s0) / g.length, 0.0, 1.0)
            out[m] = g.point(u)
        return out[0] if scalar else out.reshape(s_arr.shape + (3,))

    def tangent_at_s(self, s) -> np.ndarray:
        s_arr = np.asarray(s, dtype=float)
        scalar = s_arr.ndim == 0
        ss = np.atleast_1d(s_arr).reshape(-1)
        idx = self._locate(ss)
        out = np.empty((ss.size, 3))
        for k in np.unique(idx):
            m = idx == k
            g = self.segments[int(k)]
            u = np.clip((ss[m] - g.s0) / g.length, 0.0, 1.0)
            out[m] = g.tangent(u)
        return out[0] if scalar else out.reshape(s_arr.shape + (3,))

    def curvature_at_s(self, s) -> np.ndarray:
        s_arr = np.asarray(s, dtype=float)
        scalar = s_arr.ndim == 0
        ss = np.atleast_1d(s_arr).reshape(-1)
        idx = self._locate(ss)
        out = np.empty(ss.size)
        for k in np.unique(idx):
            m = idx == k
            g = self.segments[int(k)]
            u = np.clip((ss[m] - g.s0) / g.length, 0.0, 1.0)
            out[m] = g.curvature(u)
        return float(out[0]) if scalar else out.reshape(s_arr.shape)

    def sample(self, ds: float) -> np.ndarray:
        n = max(2, int(math.ceil(self.total_length / ds)) + 1)
        return self.point_at_s(np.linspace(0.0, self.total_length, n))

    def recompute(self) -> None:
        s = 0.0
        for g in self.segments:
            g.s0 = s
            s += g.length
        self.total_length = s
        self.s_breaks = np.array([g.s0 for g in self.segments] + [s])
        self.aabb_lo = np.min([g.aabb()[0] for g in self.segments], axis=0)
        self.aabb_hi = np.max([g.aabb()[1] for g in self.segments], axis=0)


def _build_flat_segment(pr: dict, part: dict, part_index: int, seg_index: int) -> Segment:
    kind = pr["kind"]
    z_mm = float(part["z_mm"])
    p0 = np.asarray(pr["p0"], dtype=float)
    p1 = np.asarray(pr["p1"], dtype=float)
    if kind == "line":
        return Segment(
            kind="line", part_kind="flat", tag=str(part.get("tag", "")),
            part_index=part_index, seg_index=seg_index,
            length=float(np.linalg.norm(p1 - p0)), s0=0.0,
            z0=z_mm, z1=z_mm, p0=p0, p1=p1,
        )
    if kind == "arc":
        radius = float(pr["radius"])
        sweep = float(pr["sweep"])
        return Segment(
            kind="arc", part_kind="flat", tag=str(part.get("tag", "")),
            part_index=part_index, seg_index=seg_index,
            length=abs(radius * sweep), s0=0.0, z0=z_mm, z1=z_mm,
            p0=p0, p1=p1, center=np.asarray(pr["center"], dtype=float),
            radius=radius, start_angle=float(pr["start_angle"]), sweep=sweep,
        )
    raise ValueError(f"unknown flat primitive {kind}")


def _build_transition(part: dict, part_index: int) -> Segment:
    p0 = np.asarray(part["start"], dtype=float)
    direction = np.asarray(part["direction"], dtype=float)
    z0, z1 = float(part["z0"]), float(part["z1"])
    radius = float(part["radius_mm"])
    dz = z1 - z0
    theta = math.acos(max(-1.0, min(1.0, 1.0 - abs(dz) / (2.0 * radius))))
    sign = 1.0 if dz >= 0 else -1.0
    p1 = p0 + 2.0 * radius * math.sin(theta) * direction
    return Segment(
        kind="transition", part_kind="transition",
        tag=str(part.get("tag", "")), part_index=part_index, seg_index=0,
        length=2.0 * radius * theta, s0=0.0, z0=z0, z1=z1, p0=p0, p1=p1,
        direction=direction, radius=radius, theta=theta, sign=sign,
    )


def build_route(r: dict) -> Route:
    route = Route(
        route_id=int(r["route_id"]),
        source_endpoint=str(r["source_endpoint"]),
        target_endpoint=str(r["target_endpoint"]),
        source_side=str(r["source_side"]),
        target_side=str(r["target_side"]),
        plane=str(r["plane"]),
        layer_role=str(r["layer_role"]),
        manual_group=str(r.get("manual_group", "") or ""),
        start_z_mm=float(r["start_z_mm"]),
        target_z_mm=float(r["target_z_mm"]),
        target_plane=int(r["target_plane"]),
        target_plane_label=str(r["target_plane_label"]),
        n_transitions=int(r.get("n_transitions", 0)),
        n_mid_transitions=int(r.get("n_mid_transitions", 0) or 0),
        native_3d=bool(r.get("native_3d", False)),
        direct=bool(r.get("direct", False)),
        declared_length=float(r["length_mm"]),
        xy_length=float(r["xy_length_mm"]),
        parts_json=r["parts"],
    )
    segs: list[Segment] = []
    for pi, part in enumerate(r["parts"]):
        if part["kind"] == "flat":
            for si, pr in enumerate(part.get("primitives", [])):
                segs.append(_build_flat_segment(pr, part, pi, si))
        elif part["kind"] == "transition":
            segs.append(_build_transition(part, pi))
        else:
            raise ValueError(f"unknown part kind {part['kind']}")
    route.segments = segs
    route.recompute()
    return route


def build_routes(doc: dict) -> list[Route]:
    routes = [build_route(r) for r in doc["routes"]]
    routes.sort(key=lambda r: r.route_id)
    return routes
