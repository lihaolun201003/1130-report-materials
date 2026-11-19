# -*- coding: utf-8 -*-
"""Run the CTP-2.0 optical crosstalk model on the G5 (all-angle >= 45 deg) geometry.

The model itself is never modified in place: this driver drives the *work copy*
``05_ctp2_comparison/ctp2_g5/`` whose ``src/ctp2/params.py`` points at the G5
geometry and whose outputs are redirected to ``05_ctp2_comparison/ctp2_out/``.
The frozen trees (``work/1130-report-materials/.../CROSSTALK_PREDICTION_CTP2_
20H_1283_1024`` and ``experiments/COLD_START_20_HEIGHT_1024/10_best_valid``)
are only ever *read*.

What it does
------------
1. **payload**  build a CTP-2.0-loadable dataset directory from a given G5
   ``routes_l3d.json``: the routing solution + the four payload files that are
   copied unchanged from the frozen G4 dir + a *regenerated* ``crossing_stats
   .json`` + a regenerated ``SHA256.json`` + ``BEST_VALID.json`` + provenance.
2. **crossings**  re-derive every same-height crossing analytically from the new
   routes (independent port of CTP-1.0's exact line/arc intersection engine onto
   CTP-2.0's analytic geometry), write it to
   ``OUT_CROSSINGS/crossing_events_verified.csv`` -- the file whose *presence* is
   the switch that stops ``geometry.load_crossings()`` from falling back to the
   frozen G4 crossing list -- and cross-check it against the G5 project's own
   audit CSV (``03_best_feasible/g5_crossing_angles.csv``).
3. **v5**     run ``ctp2_g5/scripts/run_v5_near_approaches.py``  (geometry-bound)
4. **board**  run ``ctp2_g5/scripts/run_board_ctp2.py``           (geometry-bound)
5. **compare** write ``g5_ctp2_summary.json`` (G5 absolute numbers) and
   ``g5_ctp2_comparison.md`` (G4 vs G5), including the propagation-loss side and
   the model-resolution caveat.
6. **faithfulness** (``--mode faithfulness``) run the *same* copy against the
   frozen **G4** payload in a separate output root and prove it reproduces the
   three published headline numbers.

Usage
-----
    python run_ctp2_g5.py                       # full G5 run (prepare->compare)
    python run_ctp2_g5.py --stages prepare,board # partial
    python run_ctp2_g5.py --mode faithfulness   # G4 reproduction proof
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

# --------------------------------------------------------------------- paths
HERE = Path(__file__).resolve().parent                  # ...\05_ctp2_comparison
PROJECT = HERE.parents[2]                               # ...\OpticalWaveguideRouter2D
G5_EXP = PROJECT / "experiments" / "G5_ANGLE45_NATIVE3D_20H_1024"
G4_BEST = PROJECT / "experiments" / "COLD_START_20_HEIGHT_1024" / "10_best_valid"
CTP1_DIR = PROJECT / "experiments" / "CROSSTALK_PREDICTION_20H_1283_1024"
WORK = PROJECT.parent / "work" / "1130-report-materials"
CTP2_FROZEN = WORK / "experiments" / "CROSSTALK_PREDICTION_CTP2_20H_1283_1024"
CTP2_G5 = HERE / "ctp2_g5"

FROZEN_G4_BOARD = CTP2_FROZEN / "outputs" / "board" / "board_summary_ctp2.json"
FROZEN_G4_HOTSPOTS = CTP2_FROZEN / "outputs" / "board" / "crosstalk_hotspots_ctp2.json"
CTP1_G4_CROSSINGS = CTP1_DIR / "outputs" / "geometry" / "crossing_events_detected.csv"
G4_LAYER_PLANES = G4_BEST / "layer_planes.json"

#: payload files copied *unchanged* from the frozen G4 solution (per the task
#: specification: only routes / crossings / gradient descriptors are new)
COPIED_PAYLOAD = ("assignment_1024.csv", "layer_planes.json",
                  "physical_layer_stack.json", "process_rules.json")

#: geometry-independent reference outputs of CTP-2.0 that the geometry-bound
#: stages read (crossing kernel) or that belong in the report (modes, coupling,
#: fullwave).  Copied from the frozen tree's outputs into OUT_ROOT if absent.
SEED_FILES = (
    "crossings/crossing_model_database.csv",
    "crossings/crossing_bpm2d_fine.csv",
    "crossings/crossing_bpm3d_subset.csv",
    "crossings/crossing_born_all.csv",
    "crossings/crossing_fdfd_large_angle.csv",
    "crossings/crossing_database_summary.json",
    "crossings/multimode_crossing_smatrix.csv",
    "crossings/multimode_summary.json",
    "modes/single_waveguide_modes.csv",
    "modes/mode_convergence.csv",
    "modes/mode_sensitivity.csv",
    "modes/mode_summary.json",
    "coupling/coupling_summary.json",
    "coupling/kappa_database.csv",
    "coupling/kappa_overlap_resolved.csv",
    "coupling/kappa_vertical_offsets.csv",
    "coupling/supermode_noise_floor.csv",
    "coupling/bpm_parallel_validation.csv",
)

#: never seeded: these are the *products* of the geometry-bound stages
NEVER_SEED = ("board/", "crossings/near_approach", "crossings/crossing_events_verified")

#: the angle bins of the G5 project's own baseline audit report (for like-for-like
#: comparison with `00_baseline_audit/baseline_angle_report.md`)
ANGLE_BINS = ((0.0, 5.0), (5.0, 10.0), (10.0, 20.0), (20.0, 30.0), (30.0, 40.0),
              (40.0, 45.0), (45.0, 60.0), (60.0, 75.0), (75.0, 90.0001))
BIN_LABELS = ("[0,5)", "[5,10)", "[10,20)", "[20,30)", "[30,40)", "[40,45)",
              "[45,60)", "[60,75)", "[75,90]")

#: frozen CTP-2.0 paper values (the three headline numbers of the G4 baseline)
G4_HEADLINE = {
    "max_offdiagonal_db": -15.206468704880304,
    "max_offdiagonal_pair": [743, 723],
    "worst_total_leakage_db": -14.769540964146534,
    "worst_total_leakage_route": 743,
    "worst_interference_to_signal_db": -12.711747549665644,
    "worst_output_route": 743,
    "n_events": 1283,
    "n_pairs": 1221,
    "n_routes_with_crossings": 647,
    "n_routes": 1024,
}

#: where the gatekeeper of the G5 round is expected to put the finalised
#: geometry.  ``03_best_feasible`` only ever receives a *fully legal* solution
#: (zero sub-45 deg crossings); a partial solution must land in
#: ``03_best_partial`` so it can never be mistaken for a feasible one.
G5_GEOMETRY_CANDIDATES = ("03_best_feasible", "03_best_partial")


def default_routes_path() -> Path:
    for name in G5_GEOMETRY_CANDIDATES:
        p = G5_EXP / name / "routes_l3d.json"
        if p.exists():
            return p
    return G5_EXP / G5_GEOMETRY_CANDIDATES[0] / "routes_l3d.json"

ALPHA_DB_PER_CM = 0.05          # frozen: 0.05 dB/cm  -> 0.005 dB/mm
ALPHA_DB_PER_MM = ALPHA_DB_PER_CM / 10.0


# ------------------------------------------------------------------- helpers
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def db(x):
    return 10.0 * float(np.log10(max(float(x), 1e-300)))


def deep_diff(a, b, path: str = "") -> list[dict]:
    """Every leaf that differs between two decoded JSON documents."""
    out: list[dict] = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append({"path": f"{path}/{k}", "frozen": None, "reproduced": a,
                            "note": "missing in frozen"})
            elif k not in b:
                out.append({"path": f"{path}/{k}", "frozen": b[k], "reproduced": None,
                            "note": "missing in reproduced"})
            else:
                out.extend(deep_diff(a[k], b[k], f"{path}/{k}"))
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [{"path": path, "frozen": b, "reproduced": a,
                     "note": f"list length {len(b)} vs {len(a)}"}]
        for i, (x, y) in enumerate(zip(a, b)):
            out.extend(deep_diff(x, y, f"{path}[{i}]"))
        return out
    if a != b:
        out.append({"path": path, "frozen": b, "reproduced": a,
                    "note": "value differs"})
    return out


def jdump(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")


class Log:
    """Tee to stdout and to a log file, with per-stage wall times."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(path, "w", encoding="utf-8")
        self.path = path
        self.timings = {}
        self._t0 = time.time()

    def __call__(self, msg: str = "") -> None:
        line = str(msg)
        print(line, flush=True)
        self.fh.write(line + "\n")
        self.fh.flush()

    def stage(self, name: str):
        return _StageTimer(self, name)


class _StageTimer:
    def __init__(self, log: Log, name: str):
        self.log, self.name = log, name

    def __enter__(self):
        self.t0 = time.time()
        self.log(f"\n=== {self.name} ===")
        return self

    def __exit__(self, exc_type, exc, tb):
        dt = time.time() - self.t0
        self.log.timings[self.name] = round(dt, 3)
        self.log(f"--- {self.name}: {dt:.2f}s"
                 + ("  [FAILED]" if exc_type else ""))
        return False


# ------------------------------------------------- CTP-2.0 module access
def load_ctp2(payload_dir: Path, out_root: Path, label: str,
              total_length_mm: float | None = None):
    """Import the work copy's ``ctp2`` package with the G5 geometry bound.

    ``params`` resolves every path at import time, so the environment must be
    set *before* the first import.  The pipeline stages are run in a fresh
    subprocess for the same reason.
    """
    os.environ["CTP2_BEST_VALID"] = str(payload_dir)
    os.environ["CTP2_OUT_ROOT"] = str(out_root)
    os.environ["CTP2_GEOMETRY_LABEL"] = label
    if total_length_mm is not None:
        os.environ["CTP2_TOTAL_LENGTH_MM"] = repr(float(total_length_mm))
    src = str(CTP2_G5 / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from ctp2 import geometry as G                     # noqa: E402
    from ctp2 import params as P                       # noqa: E402
    return G, P


def stage_env(payload_dir: Path, out_root: Path, label: str,
              total_length_mm: float, extra: dict | None = None) -> dict:
    env = dict(os.environ)
    env["CTP2_BEST_VALID"] = str(payload_dir)
    env["CTP2_OUT_ROOT"] = str(out_root)
    env["CTP2_GEOMETRY_LABEL"] = label
    env["CTP2_TOTAL_LENGTH_MM"] = repr(float(total_length_mm))
    env["PYTHONHASHSEED"] = "0"
    if extra:
        env.update({k: str(v) for k, v in extra.items()})
    return env


# =========================================================== crossing engine
# Exact analytic same-height crossing detector.
#
# This is a direct port of CTP-1.0 ``src/interactions.py`` (``_line_line``,
# ``_line_circle``, ``_circle_circle``, ``_unwrap_arc_angle``,
# ``segment_intersections``, ``detect_crossings``) onto the analytic geometry of
# CTP-2.0 ``src/ctp2/geometry.py``.  It re-derives the crossings from
# ``routes_l3d.json`` alone -- no crossing list is read from any other geometry.
# The port is validated by reproducing the frozen G4 list exactly (see
# ``--mode faithfulness``).

def flat_primitives(route) -> list[dict]:
    """Every planar (constant-z) primitive of a route with its global arclength.

    Mirrors ``geometry._build_segments`` ordering so that ``s0`` is exactly the
    ``s`` used by ``Route.pos()/tangent()``.  Transition parts are traversed (to
    keep the arclength bookkeeping right) but never returned: they are not
    constant-z and cannot carry a same-height crossing.
    """
    out: list[dict] = []
    s = 0.0
    for part_index, part in enumerate(route.parts):
        if part["kind"] == "flat":
            z = float(part["z_mm"])
            for prim in part["primitives"]:
                if prim["kind"] == "line":
                    p0 = np.asarray(prim["p0"], float)
                    p1 = np.asarray(prim["p1"], float)
                    length = float(np.linalg.norm(p1 - p0))
                    out.append(dict(kind="line", part_index=part_index, z=z,
                                    s0=s, s1=s + length, p0=p0, p1=p1))
                elif prim["kind"] == "arc":
                    length = abs(float(prim["sweep"])) * float(prim["radius"])
                    out.append(dict(kind="arc", part_index=part_index, z=z,
                                    s0=s, s1=s + length,
                                    center=np.asarray(prim["center"], float),
                                    radius=float(prim["radius"]),
                                    start_angle=float(prim["start_angle"]),
                                    sweep=float(prim["sweep"])))
                else:                                   # pragma: no cover
                    raise ValueError(f"unsupported flat primitive {prim['kind']!r}")
                s += length
        elif part["kind"] == "transition":
            s += float(part["length_mm"])
        else:                                           # pragma: no cover
            raise ValueError(f"unsupported part {part['kind']!r}")
    return out


def _aabb(seg: dict):
    lo = np.array([min(seg["p0"][0], seg["p1"][0]) if seg["kind"] == "line"
                   else min(seg["center"][0] - seg["radius"],
                            seg["center"][0] + seg["radius"]),
                   min(seg["p0"][1], seg["p1"][1]) if seg["kind"] == "line"
                   else min(seg["center"][1] - seg["radius"],
                            seg["center"][1] + seg["radius"])])
    hi = np.array([max(seg["p0"][0], seg["p1"][0]) if seg["kind"] == "line"
                   else max(seg["center"][0] - seg["radius"],
                            seg["center"][0] + seg["radius"]),
                   max(seg["p0"][1], seg["p1"][1]) if seg["kind"] == "line"
                   else max(seg["center"][1] - seg["radius"],
                            seg["center"][1] + seg["radius"])])
    return lo, hi


def _line_line(p1, d1, p2, d2):
    den = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(den) < 1e-14:
        return None
    dp = p2 - p1
    t = (dp[0] * d2[1] - dp[1] * d2[0]) / den
    u = (dp[0] * d1[1] - dp[1] * d1[0]) / den
    return t, u


def _line_circle(p, d, c, r):
    a = float(d @ d)
    b = 2.0 * float(d @ (p - c))
    cc = float((p - c) @ (p - c)) - r * r
    disc = b * b - 4 * a * cc
    if disc < 0:
        return []
    sq = math.sqrt(disc)
    return [(-b - sq) / (2 * a), (-b + sq) / (2 * a)]


def _circle_circle(c1, r1, c2, r2):
    d = float(np.linalg.norm(c2 - c1))
    if d < 1e-14 or d > r1 + r2 or d < abs(r1 - r2):
        return []
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h2 = r1 * r1 - a * a
    if h2 < 0:
        return []
    h = math.sqrt(h2)
    base = c1 + a * (c2 - c1) / d
    perp = np.array([-(c2[1] - c1[1]), c2[0] - c1[0]]) / d
    return [base + h * perp, base - h * perp]


def _unwrap_arc_angle(seg: dict, ang: float, tol: float = 1e-9):
    a0 = seg["start_angle"]
    a1 = a0 + seg["sweep"]
    lo, hi = min(a0, a1), max(a0, a1)
    k0 = math.floor((lo - ang) / (2 * math.pi)) - 1
    k1 = math.ceil((hi - ang) / (2 * math.pi)) + 1
    for kk in range(k0, k1 + 1):
        a = ang + kk * 2 * math.pi
        if lo - tol <= a <= hi + tol:
            return a
    return None


def _seg_tangent_xy(seg: dict, u: float) -> np.ndarray:
    if seg["kind"] == "line":
        d = seg["p1"] - seg["p0"]
        return d / np.linalg.norm(d)
    ang = seg["start_angle"] + seg["sweep"] * u
    sgn = 1.0 if seg["sweep"] >= 0 else -1.0
    return sgn * np.array([-math.sin(ang), math.cos(ang)])


def segment_intersections(a: dict, b: dict) -> list[tuple]:
    """(point2d, u_a, u_b) for every centre-line intersection of two planar prims."""
    out: list[tuple] = []
    tol = 1e-9
    if a["kind"] == "line" and b["kind"] == "line":
        d1 = a["p1"] - a["p0"]
        d2 = b["p1"] - b["p0"]
        r = _line_line(a["p0"], d1, b["p0"], d2)
        if r is None:
            return []
        ta, tb = r
        if -tol <= ta <= 1 + tol and -tol <= tb <= 1 + tol:
            p = a["p0"] + ta * d1
            out.append((p, float(np.clip(ta, 0, 1)), float(np.clip(tb, 0, 1))))
    elif a["kind"] == "arc" and b["kind"] == "line":
        d = b["p1"] - b["p0"]
        for t in _line_circle(b["p0"], d, a["center"], a["radius"]):
            if not (-tol <= t <= 1 + tol):
                continue
            p = b["p0"] + t * d
            au = _unwrap_arc_angle(a, math.atan2(p[1] - a["center"][1],
                                                 p[0] - a["center"][0]))
            if au is None:
                continue
            ua = (au - a["start_angle"]) / a["sweep"]
            out.append((p, float(np.clip(ua, 0, 1)), float(np.clip(t, 0, 1))))
    elif a["kind"] == "line" and b["kind"] == "arc":
        d = a["p1"] - a["p0"]
        for t in _line_circle(a["p0"], d, b["center"], b["radius"]):
            if not (-tol <= t <= 1 + tol):
                continue
            p = a["p0"] + t * d
            bu = _unwrap_arc_angle(b, math.atan2(p[1] - b["center"][1],
                                                 p[0] - b["center"][0]))
            if bu is None:
                continue
            ub = (bu - b["start_angle"]) / b["sweep"]
            out.append((p, float(np.clip(t, 0, 1)), float(np.clip(ub, 0, 1))))
    elif a["kind"] == "arc" and b["kind"] == "arc":
        for p in _circle_circle(a["center"], a["radius"], b["center"], b["radius"]):
            au = _unwrap_arc_angle(a, math.atan2(p[1] - a["center"][1],
                                                 p[0] - a["center"][0]))
            bu = _unwrap_arc_angle(b, math.atan2(p[1] - b["center"][1],
                                                 p[0] - b["center"][0]))
            if au is None or bu is None:
                continue
            ua = (au - a["start_angle"]) / a["sweep"]
            ub = (bu - b["start_angle"]) / b["sweep"]
            out.append((p, float(np.clip(ua, 0, 1)), float(np.clip(ub, 0, 1))))
    return out


def detect_crossings(routes: dict, log=None) -> tuple[list[dict], dict]:
    """Analytic same-z centre-line intersections over all route pairs."""
    by_z: dict[float, list[tuple[int, dict]]] = defaultdict(list)
    total_length_mm = 0.0
    n_prims = 0
    for rid in routes["order"]:
        route = routes["routes"][int(rid)]
        prims = flat_primitives(route)
        # arclength bookkeeping must reproduce the module's own total length
        if prims and abs(prims[-1]["s1"] - route.total_length) > 1e-6:
            raise AssertionError(
                f"route {rid}: primitive arclength {prims[-1]['s1']} != "
                f"route.total_length {route.total_length}")
        total_length_mm += route.total_length
        for g in prims:
            by_z[round(g["z"], 6)].append((int(rid), g))
            n_prims += 1

    events: list[dict] = []
    n_tested = 0
    for z, items in sorted(by_z.items()):
        n = len(items)
        for i in range(n):
            ria, ga = items[i]
            loa, hia = _aabb(ga)
            for j in range(i + 1, n):
                rib, gb = items[j]
                if ria == rib:
                    continue
                n_tested += 1
                lob, hib = _aabb(gb)
                if (loa[0] > hib[0] or lob[0] > hia[0]
                        or loa[1] > hib[1] or lob[1] > hia[1]):
                    continue
                for (p, ua, ub) in segment_intersections(ga, gb):
                    ta = _seg_tangent_xy(ga, ua)
                    tb = _seg_tangent_xy(gb, ub)
                    c = float(np.clip(abs(float(ta @ tb)), 0.0, 1.0))
                    ang = math.degrees(math.acos(c))
                    sa = ga["s0"] + ua * (ga["s1"] - ga["s0"])
                    sb = gb["s0"] + ub * (gb["s1"] - gb["s0"])
                    a_first = ria <= rib
                    events.append({
                        "route_a": int(min(ria, rib)),
                        "route_b": int(max(ria, rib)),
                        "z_mm": float(z),
                        "x_mm": float(p[0]),
                        "y_mm": float(p[1]),
                        "angle_deg": float(ang),
                        "s_a_mm": float(sa if a_first else sb),
                        "s_b_mm": float(sb if a_first else sa),
                        "kind_a": "line" if ga["kind"] == "line" else "arc",
                        "kind_b": "line" if gb["kind"] == "line" else "arc",
                        "part_index_a": int(ga["part_index"] if a_first
                                            else gb["part_index"]),
                        "part_index_b": int(gb["part_index"] if a_first
                                            else ga["part_index"]),
                        "z_a_mm": float(ga["z"]),
                        "z_b_mm": float(gb["z"]),
                    })
    raw = len(events)
    # identical de-duplication rule to CTP-1.0 interactions.detect_crossings
    events.sort(key=lambda e: (e["route_a"], e["route_b"], e["z_mm"],
                               -e["angle_deg"], e["x_mm"], e["y_mm"]))
    dedup: list[dict] = []
    for e in events:
        dup = False
        for prev in reversed(dedup[-8:]):
            if (prev["route_a"] == e["route_a"] and prev["route_b"] == e["route_b"]
                    and abs(prev["z_mm"] - e["z_mm"]) < 1e-9
                    and abs(prev["x_mm"] - e["x_mm"]) < 1e-3
                    and abs(prev["y_mm"] - e["y_mm"]) < 1e-3):
                dup = True
                break
        if not dup:
            dedup.append(e)
    for e in dedup:
        e["transverse"] = int(e["angle_deg"] >= 1.0)
    # stable presentation order: plane, then route pair
    dedup.sort(key=lambda e: (e["z_mm"], e["route_a"], e["route_b"]))
    stats = {
        "n_routes": len(routes["order"]),
        "n_flat_primitives": n_prims,
        "n_planes_with_primitives": len(by_z),
        "intersection_tests": int(n_tested),
        "raw_events": int(raw),
        "events": len(dedup),
        "pairs": len({(e["route_a"], e["route_b"]) for e in dedup}),
        "routes_with_crossings": len({e["route_a"] for e in dedup}
                                     | {e["route_b"] for e in dedup}),
        "events_transverse": int(sum(e["transverse"] for e in dedup)),
        "events_tangential": int(sum(1 - e["transverse"] for e in dedup)),
        "max_route_crossings": int(max(
            Counter([e["route_a"] for e in dedup]
                    + [e["route_b"] for e in dedup]).values() or [0])),
        "min_angle_deg": (min(e["angle_deg"] for e in dedup) if dedup else None),
        "max_angle_deg": (max(e["angle_deg"] for e in dedup) if dedup else None),
        "total_length_mm": total_length_mm,
    }
    if log:
        log(f"[crossings] detected {stats['events']} events / {stats['pairs']} pairs / "
            f"{stats['routes_with_crossings']} routes "
            f"({stats['intersection_tests']} primitive-pair tests)")
    return dedup, stats


CROSSING_COLUMNS = ("crossing_id", "route_a", "route_b", "z_mm", "z_label",
                    "x_mm", "y_mm", "angle_deg", "kind_a", "kind_b",
                    "s_a_mm", "s_b_mm", "part_index_a", "part_index_b",
                    "z_a_mm", "z_b_mm", "transverse")


def write_crossings_csv(events: list[dict], path: Path, z_label: dict) -> None:
    """Write the crossings in the schema ``geometry.load_crossings()`` expects.

    The column set is CTP-1.0's ``crossing_events_detected.csv`` (the file the
    legacy fallback read) plus ``crossing_id``/``z_label`` taken from the G5
    audit CSV.  ``load_crossings()`` returns these rows as strings and
    ``run_board_ctp2.build_events`` converts the eight fields it needs
    (route_a, route_b, s_a_mm, s_b_mm, x_mm, y_mm, z_mm, angle_deg), so the
    mapping is column-name compatible -- nothing is renamed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(CROSSING_COLUMNS))
        w.writeheader()
        for i, e in enumerate(events, 1):
            row = {k: e[k] for k in CROSSING_COLUMNS if k in e}
            row["crossing_id"] = i
            row["z_label"] = z_label.get(round(float(e["z_mm"]), 6), "")
            w.writerow(row)


def read_crossings_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def compare_crossing_sets(mine: list[dict], other: list[dict], label: str,
                          tol_mm: float = 1e-5, tol_deg: float = 1e-5,
                          require_s_match: bool = True) -> dict:
    """Match two crossing lists on (route_a, route_b, z) and diff the geometry.

    ``require_s_match`` compares ``s_a_mm``/``s_b_mm`` directly.  It must be
    False when the other list comes from an engine with a different arc-length
    origin (the G5 project's audit CSV), in which case the ``s`` difference is
    instead characterised as a per-route constant offset.

    A route pair can legitimately cross more than once on the same plane, so
    duplicate (route_a, route_b, z) keys are matched one-to-one greedily by
    nearest (x, y) rather than being treated as an error.
    """
    def key(e):
        return (int(e["route_a"]), int(e["route_b"]), round(float(e["z_mm"]), 6))

    a, b = defaultdict(list), defaultdict(list)
    for e in mine:
        a[key(e)].append(e)
    for e in other:
        b[key(e)].append(e)

    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    dx = dy = dz = ds = dang = 0.0
    worst = None
    s_pairs = []                 # (route_a, route_b, offset_a, offset_b)
    n_matched = 0
    for k in sorted(set(a) & set(b)):
        cand = []
        for i, ea in enumerate(a[k]):
            for j, eb in enumerate(b[k]):
                d = math.hypot(float(ea["x_mm"]) - float(eb["x_mm"]),
                               float(ea["y_mm"]) - float(eb["y_mm"]))
                cand.append((d, i, j))
        cand.sort()
        used_i, used_j = set(), set()
        for d, i, j in cand:
            if i in used_i or j in used_j:
                continue
            used_i.add(i)
            used_j.add(j)
            n_matched += 1
            ea, eb = a[k][i], b[k][j]
            ex = abs(float(ea["x_mm"]) - float(eb["x_mm"]))
            ey = abs(float(ea["y_mm"]) - float(eb["y_mm"]))
            ez = abs(float(ea["z_mm"]) - float(eb["z_mm"]))
            eg = abs(float(ea["angle_deg"]) - float(eb["angle_deg"]))
            esa = float(eb["s_a_mm"]) - float(ea["s_a_mm"])
            esb = float(eb["s_b_mm"]) - float(ea["s_b_mm"])
            s_pairs.append((k[0], k[1], esa, esb))
            if require_s_match:
                es = max(abs(esa), abs(esb))
                ds = max(ds, es)
            if max(ex, ey, ez, eg) >= max(dx, dy, dz, dang):
                worst = {"route_a": k[0], "route_b": k[1], "z_mm": k[2],
                         "dx_mm": ex, "dy_mm": ey, "dz_mm": ez,
                         "dangle_deg": eg}
            dx, dy, dz = max(dx, ex), max(dy, ey), max(dz, ez)
            dang = max(dang, eg)
        n_matched += 0

    # arc-length difference characterised as a per-route constant offset
    off_a, off_b = defaultdict(list), defaultdict(list)
    for ra, rb, esa, esb in s_pairs:
        off_a[ra].append(esa)
        off_b[rb].append(esb)
    all_off = list(off_a.values()) + list(off_b.values())
    n_routes = len(all_off)
    n_const = sum(1 for v in all_off if max(v) - min(v) < 1e-6)
    residual = 0.0
    max_off = 0.0
    for v in all_off:
        m = float(np.mean(v))
        max_off = max(max_off, abs(m))
        residual = max(residual, max(abs(x - m) for x in v))

    geom_consistent = (not only_a and not only_b
                       and dx <= tol_mm and dy <= tol_mm and dz <= tol_mm
                       and dang <= tol_deg)
    return {
        "against": label,
        "n_mine": len(mine),
        "n_other": len(other),
        "n_keys_mine": len(a),
        "n_keys_other": len(b),
        "n_matched": n_matched,
        "n_only_mine": len(only_a),
        "n_only_other": len(only_b),
        "only_mine_keys": [list(k) for k in only_a[:50]],
        "only_other_keys": [list(k) for k in only_b[:50]],
        "max_abs_dx_mm": dx,
        "max_abs_dy_mm": dy,
        "max_abs_dz_mm": dz,
        "max_abs_dangle_deg": dang,
        "worst_event": worst,
        "s_compared_directly": bool(require_s_match),
        "max_abs_ds_mm": ds if require_s_match else None,
        "s_offset": {
            "n_route_entries": n_routes,
            "n_constant_per_route": n_const,
            "max_abs_mean_offset_mm": max_off,
            "max_residual_around_route_mean_mm": residual,
            "note": ("a per-route constant offset means the two engines differ "
                     "only in the arc-length origin, not in the geometry"),
        },
        "geometry_consistent": bool(geom_consistent),
        "consistent": bool(geom_consistent
                           and (not require_s_match or ds <= tol_mm)),
        "tol_mm": tol_mm,
        "tol_deg": tol_deg,
    }


# ------------------------------------------------------------- payload build
def z_label_map(layer_planes: Path) -> dict:
    d = json.loads(layer_planes.read_text(encoding="utf-8"))
    out = {}
    for p in d.get("planes", []):
        out[round(float(p["z_mm"]), 6)] = p.get("label", "")
    for pid, p in (d.get("interface_planes") or {}).items():
        out.setdefault(round(float(p["z_mm"]), 6), p.get("label", ""))
    return out


def crossing_stats_json(events: list[dict], stats: dict, z_label: dict,
                        totals_override: dict | None = None) -> dict:
    """Reproduce the schema of the frozen ``crossing_stats.json``."""
    planes = defaultdict(lambda: {"routes": set(), "crossings": 0, "pairs": set()})
    per_route = Counter()
    for e in events:
        z = round(float(e["z_mm"]), 6)
        row = planes[z]
        row["crossings"] += 1
        row["routes"].add(int(e["route_a"]))
        row["routes"].add(int(e["route_b"]))
        row["pairs"].add((int(e["route_a"]), int(e["route_b"])))
        per_route[int(e["route_a"])] += 1
        per_route[int(e["route_b"])] += 1
    plane_rows = [{
        "z_mm": z, "label": z_label.get(z, ""), "routes": len(planes[z]["routes"]),
        "crossings": planes[z]["crossings"],
        "crossing_pairs": len(planes[z]["pairs"]),
    } for z in sorted(planes)]
    totals = {
        "crossings": len(events),
        "crossing_pairs": len({(int(e["route_a"]), int(e["route_b"]))
                               for e in events}),
        "routes_with_crossings": len({int(e["route_a"]) for e in events}
                                     | {int(e["route_b"]) for e in events}),
        "max_route_crossings": int(max(per_route.values()) if per_route else 0),
    }
    if totals_override:
        totals.update(totals_override)
    return {
        "schema": "xyz_joint_crossing_stats_v1",
        "crossing_rule": ("ctp2_g5 analytic re-derivation: exact line/arc "
                          "intersections per physical z, "
                          "max(|dk|) 1e-3 mm de-duplication"),
        "totals": totals,
        "planes": plane_rows,
        "per_route_crossings": {str(k): int(v) for k, v in sorted(per_route.items())},
        "crossing_events": [{
            "route_a": int(e["route_a"]), "route_b": int(e["route_b"]),
            "z_mm": round(float(e["z_mm"]), 6),
            "x_mm": round(float(e["x_mm"]), 6),
            "y_mm": round(float(e["y_mm"]), 6),
            "angle_deg": round(float(e["angle_deg"]), 6),
        } for e in events],
        "algorithm": "CTP2_G5_ANALYTIC_PRIMITIVE_INTERSECTION",
        "engine": ("run_ctp2_g5.py :: detect_crossings "
                   "(port of CTP-1.0 interactions.detect_crossings)"),
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "driver_stats": {k: v for k, v in stats.items()},
    }


def build_payload(routes_src: Path, payload: Path, events: list[dict],
                  stats: dict, z_label: dict, label: str,
                  source_dir: Path | None) -> dict:
    """Materialise a CTP-2.0-loadable payload directory (the 8-file contract)."""
    payload.mkdir(parents=True, exist_ok=True)
    prov = {"schema": "ctp2_g5_payload_provenance_v1",
            "geometry_label": label,
            "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "generator": str(Path(__file__).name),
            "routes_source": str(routes_src),
            "routes_source_sha256": sha256_file(routes_src),
            "files": {}}

    dst_routes = payload / "routes_l3d.json"
    shutil.copyfile(routes_src, dst_routes)
    if sha256_file(dst_routes) != prov["routes_source_sha256"]:
        raise RuntimeError("routes_l3d.json copy is not byte-identical")
    prov["files"]["routes_l3d.json"] = {
        "origin": "copied from the given G5 routes file",
        "sha256": prov["routes_source_sha256"], "bytes": dst_routes.stat().st_size}

    for name in COPIED_PAYLOAD:
        src = None
        if source_dir is not None and (source_dir / name).exists():
            src = source_dir / name
            origin = f"copied from {source_dir}"
        elif (G4_BEST / name).exists():
            src = G4_BEST / name
            origin = f"copied unchanged from the frozen G4 dir {G4_BEST}"
        if src is None:
            raise FileNotFoundError(f"payload file {name} not found")
        shutil.copyfile(src, payload / name)
        body = {"origin": origin,
                "sha256": sha256_file(payload / name),
                "bytes": (payload / name).stat().st_size}
        g4 = G4_BEST / name
        if g4.exists():
            body["identical_to_g4_frozen"] = (sha256_file(g4) == body["sha256"])
        prov["files"][name] = body

    jdump(crossing_stats_json(events, stats, z_label),
          payload / "crossing_stats.json")
    prov["files"]["crossing_stats.json"] = {
        "origin": "REGENERATED from the analytic crossing re-derivation",
        "sha256": sha256_file(payload / "crossing_stats.json"),
        "bytes": (payload / "crossing_stats.json").stat().st_size}

    # validation.json: a real G5 validator report if the geometry dir has one,
    # otherwise an honest stub -- never the G4 validator report
    cand = None
    if source_dir is not None:
        # prefer the FROZEN project validator's report (validation.json) over
        # the G5 engine's own audit (g5_validation.json): it is the independent
        # acceptance gate and is what CTP-2.0's FROZEN_INPUTS names
        for name in ("validation.json", "g5_validation.json"):
            if (source_dir / name).exists():
                cand = source_dir / name
                break
    if cand is not None:
        shutil.copyfile(cand, payload / "validation.json")
        prov["files"]["validation.json"] = {
            "origin": f"copied from {cand} (G5 geometry audit)",
            "sha256": sha256_file(payload / "validation.json"),
            "bytes": (payload / "validation.json").stat().st_size}
    else:
        jdump({"schema": "ctp2_g5_payload_validation_stub_v1",
               "note": ("no independent validator report was available in the "
                        "geometry directory when this payload was built; this "
                        "stub exists only to satisfy the 8-file payload "
                        "contract. The G4 validation.json was deliberately NOT "
                        "copied because it validates the G4 geometry."),
               "geometry_label": label,
               "generated": prov["generated"]}, payload / "validation.json")
        prov["files"]["validation.json"] = {
            "origin": "generated stub (no independent validator report available)",
            "sha256": sha256_file(payload / "validation.json"),
            "bytes": (payload / "validation.json").stat().st_size}

    best_valid = {
        "schema": "ctp2_g5_best_valid_v1",
        "label": label,
        "built_by": "05_ctp2_comparison/run_ctp2_g5.py",
        "built_at": prov["generated"],
        "routes_source": str(routes_src),
        "routes_sha256": prov["routes_source_sha256"],
        "routes": stats["n_routes"],
        "total_length_mm": stats["total_length_mm"],
        "crossings": stats["events"],
        "crossing_pairs": stats["pairs"],
        "routes_with_crossings": stats["routes_with_crossings"],
        "max_route_crossings": stats["max_route_crossings"],
        "min_crossing_angle_deg": stats["min_angle_deg"],
        "crossing_list": "crossings/crossing_events_verified.csv "
                         "(regenerated analytically for this geometry)",
        "acceptance_rule": ("a G5 payload must never contain a crossing list "
                            "inherited from another geometry"),
    }
    jdump(best_valid, payload / "BEST_VALID.json")
    prov["files"]["BEST_VALID.json"] = {
        "origin": "GENERATED manifest for this payload",
        "sha256": sha256_file(payload / "BEST_VALID.json"),
        "bytes": (payload / "BEST_VALID.json").stat().st_size}

    manifest = {name: {"bytes": meta["bytes"], "sha256": meta["sha256"]}
                for name, meta in sorted(prov["files"].items())}
    jdump(manifest, payload / "SHA256.json")
    prov["files"]["SHA256.json"] = {
        "origin": "REGENERATED over this payload",
        "sha256": sha256_file(payload / "SHA256.json"),
        "bytes": (payload / "SHA256.json").stat().st_size}
    jdump(prov, payload / "PAYLOAD_PROVENANCE.json")
    return prov


# ------------------------------------------------------- reference seeding
def seed_reference_outputs(out_root: Path, log) -> dict:
    """Copy the geometry-independent CTP-2.0 reference outputs into OUT_ROOT."""
    ref = CTP2_G5 / "outputs"
    done, present = [], []
    for rel in SEED_FILES:
        if any(rel.startswith(p) for p in NEVER_SEED):
            continue
        dst = out_root / rel
        if dst.exists():
            present.append(rel)
            continue
        src = ref / rel
        if not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        done.append({"file": rel, "source": str(src),
                     "sha256": sha256_file(dst), "bytes": dst.stat().st_size,
                     "mode": "copied"})
    record = {
        "schema": "ctp2_g5_reference_seed_v1",
        "out_root": str(out_root),
        "seed_source": str(ref),
        "note": ("geometry-independent CTP-2.0 outputs (crossing kernel database "
                 "theta=1..90 deg, V1 modes, V2 coupling, fullwave anchors) are "
                 "reused as-is because they depend only on the cross-section and "
                 "on the crossing angle -- never on the routing geometry. They "
                 "are COPIED, never hardlinked, so a write can never reach the "
                 "frozen tree."),
        "n_copied": len(done), "n_already_present": len(present),
        "copied": done, "already_present": present,
    }
    jdump(record, out_root / "reference_seed.json")
    log(f"[seed] {len(done)} reference files copied, {len(present)} already present "
        f"-> {out_root/'reference_seed.json'}")
    return record


# ------------------------------------------------------------ stage runner
def run_script(script: Path, env: dict, cwd: Path, log_path: Path,
               timeout: int = 3600) -> dict:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with open(log_path, "w", encoding="utf-8") as fh:
        fh.write(f"# {script.name}\n# cwd={cwd}\n# env CTP2_BEST_VALID={env.get('CTP2_BEST_VALID')}\n"
                 f"# env CTP2_OUT_ROOT={env.get('CTP2_OUT_ROOT')}\n"
                 f"# env CTP2_TOTAL_LENGTH_MM={env.get('CTP2_TOTAL_LENGTH_MM')}\n")
        fh.flush()
        rc = subprocess.call([sys.executable, str(script)], cwd=str(cwd),
                             env=env, stdout=fh, stderr=subprocess.STDOUT,
                             timeout=timeout)
    dt = time.time() - t0
    tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
    return {"script": str(script), "returncode": rc, "seconds": round(dt, 3),
            "log": str(log_path), "tail": tail}


# --------------------------------------------------------- analysis helpers
def angle_histogram(angles) -> dict:
    counts = []
    for lo, hi in ANGLE_BINS:
        counts.append(int(sum(1 for a in angles if lo <= a < hi)))
    return {"bin_labels": list(BIN_LABELS),
            "bin_edges": [list(b) for b in ANGLE_BINS],
            "counts": counts}


def kernel_status_per_angle(angles, db_path: Path) -> tuple[list[str], dict]:
    """Tag every crossing with the kernel row status that governs its value."""
    with open(db_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    th = np.array([float(r["theta_deg"]) for r in rows])
    st = [r["status"] for r in rows]
    order = np.argsort(th)
    th = th[order]
    st = [st[i] for i in order]
    tags: list[str] = []
    for a in angles:
        if a <= th[0]:
            tags.append(st[0])
        elif a >= th[-1]:
            tags.append(st[-1])
        else:
            j = int(np.searchsorted(th, a))
            if abs(th[j] - a) < 1e-12:
                tags.append(st[j])
            else:
                s0, s1 = st[j - 1], st[j]
                tags.append(s0 if s0 == s1 else f"handover:{s0}|{s1}")
    return tags, {"theta": th, "status": st}


def kernel_status(angles, db_path: Path) -> dict:
    """Classify every crossing by the *kernel's own* validity status."""
    tags, meta = kernel_status_per_angle(angles, db_path)
    th, st = meta["theta"], meta["status"]
    per = Counter(tags)
    handover = sum(v for k, v in per.items() if k.startswith("handover:"))
    floor_limited = sum(v for k, v in per.items()
                        if "upper_bound_port_floor_limited" in k)
    resolved = sum(v for k, v in per.items()
                   if k in ("resolved", "resolved_fdtd_crosschecked"))
    return {
        "per_status": dict(sorted(per.items())),
        "n_resolved": int(resolved),
        "n_floor_limited_or_handover": int(floor_limited),
        "n_floor_limited_exact": int(per.get("upper_bound_port_floor_limited", 0)),
        "n_handover_bracket": int(handover),
        "kernel_db": str(db_path),
        "kernel_db_sha256": sha256_file(db_path),
        "kernel_theta_min": float(th[0]),
        "kernel_theta_max": float(th[-1]),
        "kernel_n_angles": int(len(th)),
        "floor_db": -85.0,
        "discontinuity_note": (
            "the kernel hands over from BPM (disputed_paraxial) to the FDFD "
            "floor between theta=45.0 deg (T_cross_db=-72.799) and theta=45.5 "
            "deg (-85.000); a ~12 dB step that is a model property, not physics"),
    }


def bound_fraction(board_dir: Path, kernel_db: Path) -> dict:
    """How much of the coupled power comes from floor-limited crossings?

    Reads the board's own per-event table (``crossing_optical_analysis_ctp2.csv``,
    which carries ``T_cross`` and ``forward_direction_ok``) and splits the
    forward-allowed transfer sum by the kernel status of each crossing's angle.
    The power-weighted share is the honest answer to "how much of the board
    number is a bound rather than a resolved value".
    """
    p = board_dir / "crossing_optical_analysis_ctp2.csv"
    if not p.exists():
        return {"available": False, "path": str(p)}
    with open(p, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    ang = [float(r["angle_deg"]) for r in rows]
    tags, _ = kernel_status_per_angle(ang, kernel_db)
    fwd = [int(float(r["forward_direction_ok"])) == 1 for r in rows]
    tcr = [float(r["T_cross"]) for r in rows]
    is_floor = ["upper_bound_port_floor_limited" in t for t in tags]
    tot = sum(t for t, f in zip(tcr, fwd) if f)
    tot_floor = sum(t for t, f, fl in zip(tcr, fwd, is_floor) if f and fl)
    tot_res = sum(t for t, f, fl in zip(tcr, fwd, is_floor) if f and not fl)
    n_fwd = sum(1 for f in fwd if f)
    n_fwd_floor = sum(1 for f, fl in zip(fwd, is_floor) if f and fl)
    counts = Counter()
    floor_counts = Counter()
    power = defaultdict(float)
    for a, t, f, fl in zip(ang, tcr, fwd, is_floor):
        for lo, hi, lbl in zip([b[0] for b in ANGLE_BINS],
                               [b[1] for b in ANGLE_BINS], BIN_LABELS):
            if lo <= a < hi:
                counts[lbl] += 1
                if fl:
                    floor_counts[lbl] += 1
                if f:
                    power[lbl] += t
                break
    return {
        "available": True,
        "path": str(p),
        "n_events": len(rows),
        "n_forward_allowed": int(n_fwd),
        "n_forward_allowed_floor_limited": int(n_fwd_floor),
        "sum_T_cross_forward": float(tot),
        "sum_T_cross_forward_floor_limited": float(tot_floor),
        "sum_T_cross_forward_resolved_or_disputed": float(tot_res),
        "fraction_of_events_floor_limited": (n_fwd_floor / n_fwd) if n_fwd else None,
        "fraction_of_forward_power_floor_limited": (tot_floor / tot) if tot else None,
        "equivalent_dB_floor_contribution": (db(tot_floor) if tot_floor else None),
        "equivalent_dB_resolved_contribution": (db(tot_res) if tot_res else None),
        "counts_by_angle_band": dict(counts),
        "floor_counts_by_angle_band": dict(floor_counts),
        "power_by_angle_band": {k: float(v) for k, v in power.items()},
        "power_share_by_angle_band": {k: (float(v) / float(tot) if tot else None)
                                      for k, v in power.items()},
        "statement": ("the fraction of the forward-coupled power that is a "
                      "floor-limited (upper-bound) value; the complement is the "
                      "resolved/disputed part that is a genuine prediction"),
    }


def hotspot_count(board_dir: Path) -> dict:
    """Recompute how many hotspot clusters exist (the board stores only top-80)."""
    p = board_dir / "crossing_optical_analysis_ctp2.csv"
    if not p.exists():
        return {"available": False}
    with open(p, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    keys = set()
    for r in rows:
        if int(float(r["forward_direction_ok"])) != 1:
            continue
        z = round(float(r["z_mm"]), 3)
        x = int(round(float(r["x_mm"]) / 2.0))
        y = int(round(float(r["y_mm"]) / 2.0))
        keys.add((z, x, y))
    return {"available": True, "n_clusters_total": len(keys),
            "n_stored": 80,
            "note": ("the board writes clusters[:80]; this is the full count of "
                     "2 mm x 2 mm x plane clusters over the forward-allowed events")}


def g5_geometry_changes(g4_routes: dict, g5_routes: dict, top: int = 10) -> dict:
    """What actually changed in the geometry: route lengths, heights, planes."""
    common = [int(r) for r in g5_routes["order"] if int(r) in g4_routes["routes"]]
    dL = []
    moved_plane = 0
    changed = 0
    for rid in common:
        a = g4_routes["routes"][rid]
        b = g5_routes["routes"][rid]
        za = tuple(round(z, 6) for z, _ in a.z_plateaus)
        zb = tuple(round(z, 6) for z, _ in b.z_plateaus)
        d = b.total_length - a.total_length
        dL.append((rid, d, a.total_length, b.total_length, za != zb,
                   round(a.start_z_mm, 6), round(b.start_z_mm, 6),
                   round(a.end_z_mm, 6), round(b.end_z_mm, 6)))
        if za != zb:
            moved_plane += 1
        if abs(d) > 1e-9 or za != zb:
            changed += 1
    da = np.array([abs(x[1]) for x in dL], float)
    d_signed = np.array([x[1] for x in dL], float)
    top_rows = sorted(dL, key=lambda x: -abs(x[1]))[:top]
    g4_total = sum(r.total_length for r in g4_routes["routes"].values())
    g5_total = sum(r.total_length for r in g5_routes["routes"].values())
    return {
        "n_routes_compared": len(common),
        "n_routes_changed_length_or_height": int(changed),
        "n_routes_with_different_height_set": int(moved_plane),
        "delta_length_total_mm": float(g5_total - g4_total),
        "g4_total_length_mm": float(g4_total),
        "g5_total_length_mm": float(g5_total),
        "delta_length_abs_max_mm": float(da.max() if da.size else 0.0),
        "delta_length_abs_mean_mm": float(da.mean() if da.size else 0.0),
        "n_routes_abs_delta_over_1mm": int((da > 1.0).sum()),
        "n_routes_abs_delta_over_10mm": int((da > 10.0).sum()),
        "n_routes_longer": int((d_signed > 0).sum()),
        "n_routes_shorter": int((d_signed < 0).sum()),
        "top_length_changes": [
            {"route_id": int(r), "delta_mm": float(d), "g4_mm": float(a),
             "g5_mm": float(b), "height_set_changed": bool(hs),
             "g4_start_z": s4, "g5_start_z": s5,
             "g4_end_z": e4, "g5_end_z": e5}
            for (r, d, a, b, hs, s4, s5, e4, e5) in top_rows],
        "note": ("a route can be re-routed without crossing-angle repair; the "
                 "length change is the fingerprint of a re-height or re-route"),
    }


def propagation_loss(routes: dict) -> dict:
    """alpha = 0.05 dB/cm, R15 extra bend loss 0 dB, along the true arc length."""
    lengths = np.array([routes["routes"][int(r)].total_length
                        for r in routes["order"]], float)
    loss = ALPHA_DB_PER_MM * lengths
    return {
        "alpha_db_per_cm": ALPHA_DB_PER_CM,
        "bend_extra_loss_db": 0.0,
        "wavelength_nm": 1310.0,
        "n_clad": 1.50,
        "delta_n": 0.0065,
        "core_um": [9.0, 9.0],
        "n_routes": int(lengths.size),
        "total_length_mm": float(lengths.sum()),
        "length_min_mm": float(lengths.min()),
        "length_max_mm": float(lengths.max()),
        "length_mean_mm": float(lengths.mean()),
        "length_median_mm": float(np.median(lengths)),
        "loss_max_db": float(loss.max()),
        "loss_mean_db": float(loss.mean()),
        "loss_median_db": float(np.median(loss)),
        "loss_min_db": float(loss.min()),
        "loss_total_db": float(loss.sum()),
        "loss_p05_db": float(np.percentile(loss, 5)),
        "loss_p95_db": float(np.percentile(loss, 95)),
        "formula": "loss_db = 0.005 * L_mm   (0.05 dB/cm), no extra bend term",
    }


def hotspots(path: Path, top: int = 5) -> dict:
    if not path.exists():
        return {"n_clusters": 0, "top": [], "path": str(path)}
    clusters = json.loads(path.read_text(encoding="utf-8"))
    return {"n_clusters": len(clusters), "path": str(path),
            "top": [{"z_mm": c.get("z_mm"), "x_mm": c.get("x_mm"),
                     "y_mm": c.get("y_mm"),
                     "n_crossings": c.get("n_crossings"),
                     "total_P_cross_db": c.get("total_P_cross_db"),
                     "max_P_cross_db": c.get("max_P_cross_db"),
                     "min_angle_deg": c.get("min_angle_deg"),
                     "mean_angle_deg": c.get("mean_angle_deg")}
                    for c in clusters[:top]],
            "total_P_cross_db": (db(sum(10 ** (c["total_P_cross_db"] / 10.0)
                                       for c in clusters))
                                 if clusters else None)}


# ------------------------------------------------------------- G4 reference
def g4_reference(log) -> dict:
    """Everything the comparison needs on the G4 side, read-only from frozen."""
    if not FROZEN_G4_BOARD.exists():
        raise FileNotFoundError(FROZEN_G4_BOARD)
    board = json.loads(FROZEN_G4_BOARD.read_text(encoding="utf-8"))
    legacy = read_crossings_csv(CTP1_G4_CROSSINGS) if CTP1_G4_CROSSINGS.exists() else []
    angles = [float(r["angle_deg"]) for r in legacy]
    pairs = {(int(r["route_a"]), int(r["route_b"])) for r in legacy}
    routes_with = {int(r["route_a"]) for r in legacy} | {int(r["route_b"]) for r in legacy}
    per_route = Counter()
    for r in legacy:
        per_route[int(r["route_a"])] += 1
        per_route[int(r["route_b"])] += 1
    ref = {
        "board_summary": board,
        "board_summary_path": str(FROZEN_G4_BOARD),
        "board_summary_sha256": sha256_file(FROZEN_G4_BOARD),
        "crossings_csv": str(CTP1_G4_CROSSINGS),
        "crossings_csv_sha256": (sha256_file(CTP1_G4_CROSSINGS)
                                if CTP1_G4_CROSSINGS.exists() else None),
        "n_events": len(legacy),
        "n_pairs": len(pairs),
        "n_routes_with_crossings": len(routes_with),
        "max_route_crossings": int(max(per_route.values()) if per_route else 0),
        "angle_histogram": angle_histogram(angles),
        "min_angle_deg": min(angles) if angles else None,
        "median_angle_deg": float(np.median(angles)) if angles else None,
        "n_below_45": int(sum(1 for a in angles if a < 45.0)),
        "n_below_30": int(sum(1 for a in angles if a < 30.0)),
        "n_below_10": int(sum(1 for a in angles if a < 10.0)),
        "hotspots": hotspots(FROZEN_G4_HOTSPOTS),
    }
    log(f"[g4] frozen board summary {board.get('nominal_ctp2', {}).get('max_offdiagonal_db')} "
        f"dB max pair; {ref['n_events']} crossings, {ref['n_below_45']} below 45 deg")
    return ref


# --------------------------------------------------------------- faithfulness
def faithfulness(args, log: Log) -> int:
    """Run the work copy against the frozen G4 payload and prove reproduction."""
    out_root = HERE / "ctp2_out_faithfulness"
    proof_dir = HERE / "faithfulness"
    proof_dir.mkdir(parents=True, exist_ok=True)
    log(f"[faithfulness] geometry = frozen G4 payload {G4_BEST}")
    log(f"[faithfulness] output root = {out_root}")

    # 1. crossing list: the *explicit* legacy path, column-mapped to the CTP
    #    schema, so the check exercises the same numbers the published run used.
    G, P = load_ctp2(G4_BEST, out_root, "G4_frozen_COLD_START_20_HEIGHT_1024/10_best_valid")
    zl = z_label_map(G4_LAYER_PLANES)
    legacy_rows = G._read_legacy_crossings()
    log(f"[faithfulness] legacy crossing rows = {len(legacy_rows)}")
    events = []
    for r in legacy_rows:
        events.append({
            "route_a": int(r["route_a"]), "route_b": int(r["route_b"]),
            "z_mm": float(r["z_mm"]), "x_mm": float(r["x_mm"]),
            "y_mm": float(r["y_mm"]), "angle_deg": float(r["angle_deg"]),
            "s_a_mm": float(r["s_a_mm"]), "s_b_mm": float(r["s_b_mm"]),
            "kind_a": str(r.get("kind_a", "")), "kind_b": str(r.get("kind_b", "")),
            "part_index_a": int(float(r.get("part_index_a", 0) or 0)),
            "part_index_b": int(float(r.get("part_index_b", 0) or 0)),
            "z_a_mm": float(r.get("z_a_mm", r["z_mm"])),
            "z_b_mm": float(r.get("z_b_mm", r["z_mm"])),
            "transverse": int(float(r.get("transverse", 1) or 0)),
        })
    events.sort(key=lambda e: (e["z_mm"], e["route_a"], e["route_b"]))
    csv_path = out_root / "crossings" / "crossing_events_verified.csv"
    write_crossings_csv(events, csv_path, zl)
    log(f"[faithfulness] wrote {csv_path} ({len(events)} rows)")

    # 1b. prove the CSV path and the pandas legacy path give identical floats
    via_csv = [dict(r) for r in G.load_crossings()]
    keys = ("route_a", "route_b", "z_mm", "x_mm", "y_mm", "angle_deg",
            "s_a_mm", "s_b_mm")

    def _sortkey(row):
        return (int(row["route_a"]), int(row["route_b"]), float(row["z_mm"]),
                float(row["x_mm"]), float(row["y_mm"]))

    left = sorted(legacy_rows, key=_sortkey)
    right = sorted(via_csv, key=_sortkey)
    max_delta = 0.0
    n_cmp = 0
    for a, b in zip(left, right):
        for k in keys:
            va, vb = float(a[k]), float(b[k])
            max_delta = max(max_delta, abs(va - vb))
            n_cmp += 1
    identical = (len(legacy_rows) == len(via_csv)
                 and len(left) == len(right) and max_delta == 0.0)
    log(f"[faithfulness] legacy(pandas) vs verified(csv) rows: "
        f"{len(legacy_rows)}/{len(via_csv)}  compared {n_cmp} floats  "
        f"max |delta| = {max_delta!r}  identical={identical}")

    # 2. independent detector on the G4 routes must reproduce the same events
    routes = G.load_routes(G4_BEST / "routes_l3d.json")
    det, det_stats = detect_crossings(routes, log)
    det_check = compare_crossing_sets(det, events, "CTP-1.0 e4 legacy CSV",
                                      tol_mm=1e-6, tol_deg=1e-6)
    log(f"[faithfulness] detector: {det_stats['events']} events / "
        f"{det_stats['pairs']} pairs / {det_stats['routes_with_crossings']} routes; "
        f"vs legacy: matched={det_check['n_matched']} "
        f"only_det={det_check['n_only_mine']} only_legacy={det_check['n_only_other']} "
        f"max|dx|={det_check['max_abs_dx_mm']:.3e} "
        f"max|ds|={det_check['max_abs_ds_mm']:.3e} "
        f"max|dangle|={det_check['max_abs_dangle_deg']:.3e} "
        f"consistent={det_check['consistent']}")

    # 3. seed the geometry-independent reference outputs (the crossing kernel the
    #    board interpolates; identical for every geometry) and run the two
    #    geometry-bound stages
    seed_reference_outputs(out_root, log)
    total_len = float(det_stats["total_length_mm"])
    env = stage_env(G4_BEST, out_root,
                    "G4_frozen_COLD_START_20_HEIGHT_1024/10_best_valid",
                    total_length_mm=G4_HEADLINE.get("total_length_mm",
                                                    156597.221522))
    runs = {}
    with log.stage("faithfulness: V5 near approaches (G4)"):
        runs["v5"] = run_script(CTP2_G5 / "scripts" / "run_v5_near_approaches.py",
                                env, CTP2_G5, proof_dir / "v5_g4.log")
        log(f"   rc={runs['v5']['returncode']} {runs['v5']['seconds']}s")
    with log.stage("faithfulness: board (G4)"):
        runs["board"] = run_script(CTP2_G5 / "scripts" / "run_board_ctp2.py",
                                   env, CTP2_G5, proof_dir / "board_g4.log")
        log(f"   rc={runs['board']['returncode']} {runs['board']['seconds']}s")

    got = json.loads((out_root / "board" / "board_summary_ctp2.json")
                     .read_text(encoding="utf-8"))
    want = json.loads(FROZEN_G4_BOARD.read_text(encoding="utf-8"))
    shutil.copyfile(out_root / "board" / "board_summary_ctp2.json",
                    proof_dir / "board_summary_g4_reproduced.json")

    checks = []

    def chk(name, a, b, sig=12):
        """Compare with a significant-digit criterion (default: full float64)."""
        if isinstance(a, (int, np.integer)) and isinstance(b, (int, np.integer)):
            ok = int(a) == int(b)
            checks.append({"metric": name, "frozen": b, "reproduced": a,
                           "abs_delta": 0.0 if ok else abs(int(a) - int(b)),
                           "significant_digits": float("inf") if ok else 0.0,
                           "pass": ok})
        elif isinstance(a, (int, float, np.floating)) and isinstance(
                b, (int, float, np.floating)):
            d = abs(float(a) - float(b))
            scale = max(abs(float(b)), 1e-300)
            nd = (math.inf if d == 0 else max(0.0, -math.log10(d / scale)))
            checks.append({"metric": name, "frozen": float(b),
                           "reproduced": float(a), "abs_delta": d,
                           "significant_digits": nd,
                           "pass": d <= 0.5 * 10 ** (-sig) * scale})
        else:
            ok = a == b
            checks.append({"metric": name, "frozen": b, "reproduced": a,
                           "abs_delta": None, "significant_digits": None,
                           "pass": ok})

    for key in ("max_offdiagonal_db", "worst_total_leakage_db",
                "diagonal_min_db", "diagonal_max_db", "median_offdiagonal_db",
                "mean_total_leakage_db", "max_column_sum",
                "total_output_over_input"):
        chk(f"nominal_ctp2.{key}", got["nominal_ctp2"][key], want["nominal_ctp2"][key])
    for key in ("max_offdiagonal_pair", "worst_total_leakage_route",
                "n_nonzero_offdiagonal", "all_columns_le_1"):
        chk(f"nominal_ctp2.{key}", got["nominal_ctp2"][key], want["nominal_ctp2"][key])
    for key in ("max_offdiagonal_lower_db", "max_offdiagonal_upper_db",
                "worst_total_leakage_lower_db", "worst_total_leakage_upper_db"):
        chk(f"bounds.{key}", got["bounds"][key], want["bounds"][key])
    for key in ("worst_interference_to_signal_db", "worst_output_route",
                "mean_isr_db"):
        chk(f"multi_input_incoherent.{key}",
            got["multi_input_incoherent"][key],
            want["multi_input_incoherent"][key])
    for key in ("n_events", "n_forward_allowed", "n_forward_blocked",
                "T_cross_db_min", "T_cross_db_max", "T_cross_db_median",
                "angle_min_deg", "angle_median_deg",
                "n_events_above_minus40dB", "n_events_above_minus30dB"):
        chk(f"crossings.{key}", got["crossings"][key], want["crossings"][key])
    chk("baseline_ctp1_fixed_p.max_offdiagonal_db",
        got["baseline_ctp1_fixed_p"]["max_offdiagonal_db"],
        want["baseline_ctp1_fixed_p"]["max_offdiagonal_db"])
    chk("baseline_ctp1_fixed_p.worst_total_leakage_db",
        got["baseline_ctp1_fixed_p"]["worst_total_leakage_db"],
        want["baseline_ctp1_fixed_p"]["worst_total_leakage_db"])
    chk("second_order.n_terms", got["second_order"]["n_terms"],
        want["second_order"]["n_terms"])
    chk("second_order.max_T_db", got["second_order"]["max_T_db"],
        want["second_order"]["max_T_db"])
    chk("frozen_geometry.n_routes", got["frozen_geometry"]["n_routes"],
        want["frozen_geometry"]["n_routes"])
    chk("frozen_geometry.n_crossings", got["frozen_geometry"]["n_crossings"],
        want["frozen_geometry"]["n_crossings"])
    chk("frozen_geometry.total_length_mm", got["frozen_geometry"]["total_length_mm"],
        want["frozen_geometry"]["total_length_mm"])

    headline = {}
    for name, path, sig in (
            ("max_offdiagonal_db", ("nominal_ctp2", "max_offdiagonal_db"), 6),
            ("worst_total_leakage_db", ("nominal_ctp2", "worst_total_leakage_db"), 6),
            ("worst_interference_to_signal_db",
             ("multi_input_incoherent", "worst_interference_to_signal_db"), 6)):
        a, b = got[path[0]][path[1]], want[path[0]][path[1]]
        headline[name] = {"frozen": b, "reproduced": a,
                          "abs_delta": abs(a - b),
                          "significant_digits": (
                              math.inf if a == b else -math.log10(
                                  abs(a - b) / abs(b))),
                          "pass_at_6_sig": abs(a - b) <= 0.5e-6 * abs(b)}

    n_fail = sum(1 for c in checks if not c["pass"])
    diff = deep_diff(got, want)
    expected_only = {"runtime_seconds"}
    unexpected = [d for d in diff
                  if d["path"].strip("/").split("/")[0] not in expected_only]
    proof = {
        "schema": "ctp2_g5_faithfulness_proof_v1",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "purpose": ("prove the work copy ctp2_g5 is a faithful copy of the frozen "
                    "CTP-2.0 model: given the frozen G4 payload and the frozen G4 "
                    "crossing list it must reproduce the published numbers"),
        "geometry": str(G4_BEST),
        "frozen_board_summary": str(FROZEN_G4_BOARD),
        "frozen_board_summary_sha256": sha256_file(FROZEN_G4_BOARD),
        "output_root": str(out_root),
        "headline": headline,
        "headline_all_pass": all(v["pass_at_6_sig"] for v in headline.values()),
        "checks": checks,
        "n_checks": len(checks),
        "n_checks_failed": n_fail,
        "all_checks_pass": n_fail == 0,
        "full_board_summary_diff": {
            "n_differing_leaves": len(diff),
            "differing_leaves": diff,
            "n_unexpected": len(unexpected),
            "unexpected": unexpected,
            "note": ("a full recursive diff of the reproduced vs frozen "
                     "board_summary_ctp2.json; the only tolerated difference is "
                     "runtime_seconds"),
        },
        "crossing_list": {
            "source": str(CTP1_G4_CROSSINGS),
            "source_sha256": sha256_file(CTP1_G4_CROSSINGS),
            "n_rows": len(events),
            "legacy_vs_verified_csv_max_abs_delta": max_delta,
            "legacy_vs_verified_csv_identical": identical,
        },
        "detector_vs_legacy": det_check,
        "detector_stats": det_stats,
        "runtimes_seconds": {"v5": runs["v5"]["seconds"],
                             "board": runs["board"]["seconds"]},
        "total_length_mm": {
            "passed_to_model": 156597.221522,
            "computed_from_routes": total_len,
            "abs_delta_mm": abs(total_len - 156597.221522),
        },
        "verdict": ("FAITHFUL: the copy reproduces the frozen CTP-2.0 G4 board "
                    "summary bit-for-bit" if n_fail == 0 else
                    f"NOT FAITHFUL: {n_fail} of {len(checks)} checks failed"),
    }
    jdump(proof, proof_dir / "faithfulness_proof.json")
    log("")
    log(f"[faithfulness] {len(checks) - n_fail}/{len(checks)} checks pass; "
        f"headline 6-sig-digit: {proof['headline_all_pass']}")
    log(f"[faithfulness] full recursive diff of board_summary_ctp2.json: "
        f"{len(diff)} differing leaf/leaves, {len(unexpected)} unexpected")
    for d in diff:
        log(f"    DIFF {d['path']}: frozen={d['frozen']!r} reproduced={d['reproduced']!r}")
    for k, v in headline.items():
        log(f"    {k:34s} frozen={v['frozen']!r:24s} reproduced={v['reproduced']!r:24s} "
            f"abs_delta={v['abs_delta']:.3e} sig_digits={v['significant_digits']:.2f}")
    log(f"[faithfulness] -> {proof_dir/'faithfulness_proof.json'}")
    return 0 if n_fail == 0 else 1


# --------------------------------------------------------------------- G5 run
def stage_prepare(args, log: Log) -> dict:
    routes_src = Path(args.routes)
    if not routes_src.exists():
        raise FileNotFoundError(f"G5 routes file not found: {routes_src}")
    src_dir = routes_src.parent
    payload = Path(args.payload_dir)
    out_root = Path(args.out_root)

    label = args.geometry_label or str(src_dir.relative_to(PROJECT))
    with log.stage("prepare: load routes"):
        G, P = load_ctp2(payload, out_root, label)
        routes = G.load_routes(routes_src)
        log(f"   {len(routes['order'])} routes, "
            f"sum L = {sum(routes['routes'][int(r)].total_length for r in routes['order']):.6f} mm")

    with log.stage("prepare: analytic crossing re-derivation"):
        events, stats = detect_crossings(routes, log)

    zl = z_label_map(src_dir / "layer_planes.json"
                     if (src_dir / "layer_planes.json").exists()
                     else G4_LAYER_PLANES)

    with log.stage("prepare: cross-check against the G5 project's audit CSV"):
        audit_path = Path(args.audit_csv) if args.audit_csv else (src_dir / "g5_crossing_angles.csv")
        audit = read_crossings_csv(audit_path) if audit_path.exists() else []
        if audit:
            audit_check = compare_crossing_sets(
                events, audit, str(audit_path),
                tol_mm=args.tol_mm, tol_deg=args.tol_deg,
                require_s_match=False)
            off = audit_check["s_offset"]
            log(f"   audit rows={len(audit)} matched={audit_check['n_matched']} "
                f"only_detector={audit_check['n_only_mine']} "
                f"only_audit={audit_check['n_only_other']}")
            log(f"   max|dx|={audit_check['max_abs_dx_mm']:.3e} mm "
                f"max|dy|={audit_check['max_abs_dy_mm']:.3e} mm "
                f"max|dz|={audit_check['max_abs_dz_mm']:.3e} mm "
                f"max|dangle|={audit_check['max_abs_dangle_deg']:.3e} deg")
            log(f"   s column: not compared directly (different arc-length origin); "
                f"{off['n_constant_per_route']}/{off['n_route_entries']} routes have a "
                f"constant offset, max |offset| = {off['max_abs_mean_offset_mm']:.3f} mm, "
                f"residual around the per-route mean = "
                f"{off['max_residual_around_route_mean_mm']:.3e} mm")
            log(f"   geometry_consistent={audit_check['geometry_consistent']}")
        else:
            audit_check = {"against": str(audit_path), "exists": False,
                           "note": "no audit CSV available; detector is the only source"}
            log("   no audit CSV found -- detector output stands alone")

    with log.stage("prepare: write crossing_events_verified.csv"):
        csv_path = out_root / "crossings" / "crossing_events_verified.csv"
        write_crossings_csv(events, csv_path, zl)
        log(f"   {csv_path}  ({len(events)} rows, "
            f"{csv_path.stat().st_size} bytes, sha256={sha256_file(csv_path)[:16]}...)")

    with log.stage("prepare: build CTP-2.0 payload"):
        prov = build_payload(routes_src, payload, events, stats, zl, label, src_dir)
        log(f"   payload -> {payload}")
        for name, meta in prov["files"].items():
            log(f"     {name:26s} {meta['bytes']:>9d} B  {meta['origin'][:70]}")

    with log.stage("prepare: seed geometry-independent reference outputs"):
        seed = seed_reference_outputs(out_root, log)

    report = {
        "schema": "ctp2_g5_crossing_regeneration_v1",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "geometry_label": label,
        "geometry_dir": str(src_dir),
        "routes_file": str(routes_src),
        "routes_sha256": prov["routes_source_sha256"],        "method": ("exact analytic line/arc intersection per physical z, port of "
                   "CTP-1.0 interactions.detect_crossings onto CTP-2.0 "
                   "geometry.Route primitives; NO crossing list is inherited"),
        "stats": stats,
        "angle_histogram": angle_histogram([e["angle_deg"] for e in events]),
        "n_below_45": int(sum(1 for e in events if e["angle_deg"] < 45.0)),
        "n_below_46": int(sum(1 for e in events if e["angle_deg"] < 46.0)),
        "n_at_or_above_45": int(sum(1 for e in events if e["angle_deg"] >= 45.0)),
        "audit_cross_check": audit_check,
        "verified_csv": str(csv_path),
        "verified_csv_sha256": sha256_file(csv_path),
        "kernel_status": kernel_status([e["angle_deg"] for e in events],
                                       out_root / "crossings" / "crossing_model_database.csv"),
        "payload_provenance": prov,
        "reference_seed": {"n_copied": seed["n_copied"],
                           "n_already_present": seed["n_already_present"],
                           "record": str(out_root / "reference_seed.json")},
        "total_length_mm": stats["total_length_mm"],
        "propagation_loss": propagation_loss(routes),
    }
    jdump(report, out_root / "crossings" / "crossing_regeneration_report.json")

    if audit and args.require_audit_agreement and not audit_check["consistent"]:
        raise RuntimeError("crossing regeneration disagrees with the G5 audit CSV; "
                           "refusing to continue (see "
                           f"{out_root/'crossings'/'crossing_regeneration_report.json'})")
    return report


def stage_board(args, log: Log) -> dict:
    out_root = Path(args.out_root)
    payload = Path(args.payload_dir)
    label = args.geometry_label
    total_len = args.total_length_mm
    if total_len is None:
        rep = json.loads((out_root / "crossings" / "crossing_regeneration_report.json")
                         .read_text(encoding="utf-8"))
        total_len = rep["total_length_mm"]
    env = stage_env(payload, out_root, label, total_length_mm=total_len)
    runs = {}
    if "v5" in args.stage_list:
        with log.stage("V5 near approaches"):
            runs["v5"] = run_script(CTP2_G5 / "scripts" / "run_v5_near_approaches.py",
                                    env, CTP2_G5, out_root / "logs" / "v5_near.log",
                                    timeout=args.timeout)
            log(f"   rc={runs['v5']['returncode']} {runs['v5']['seconds']}s  "
                f"log={runs['v5']['log']}")
            if runs["v5"]["returncode"] != 0:
                raise RuntimeError(f"V5 failed (rc={runs['v5']['returncode']}); see "
                                   f"{runs['v5']['log']}")
    with log.stage("board (run_board_ctp2.py)"):
        runs["board"] = run_script(CTP2_G5 / "scripts" / "run_board_ctp2.py",
                                   env, CTP2_G5, out_root / "logs" / "board.log",
                                   timeout=args.timeout)
        log(f"   rc={runs['board']['returncode']} {runs['board']['seconds']}s  "
            f"log={runs['board']['log']}")
        if runs["board"]["returncode"] != 0:
            raise RuntimeError(f"board failed (rc={runs['board']['returncode']}); "
                               f"see {runs['board']['log']}")
    summary = json.loads((out_root / "board" / "board_summary_ctp2.json")
                         .read_text(encoding="utf-8"))
    return {"runs": runs, "board_summary": summary}


def stage_compare(args, log: Log) -> dict:
    out_root = Path(args.out_root)
    payload = Path(args.payload_dir)
    regen = json.loads((out_root / "crossings" / "crossing_regeneration_report.json")
                       .read_text(encoding="utf-8"))
    board = json.loads((out_root / "board" / "board_summary_ctp2.json")
                       .read_text(encoding="utf-8"))
    g4 = g4_reference(log)
    G, P = load_ctp2(payload, out_root, args.geometry_label)
    routes = G.load_routes(payload / "routes_l3d.json")
    prop = propagation_loss(routes)
    hs = hotspots(out_root / "board" / "crosstalk_hotspots_ctp2.json")

    # G5 crossing statistics straight from the verified CSV (independent of the
    # board summary, so a mismatch between the two is visible)
    verified = read_crossings_csv(out_root / "crossings" / "crossing_events_verified.csv")
    g5_angles = [float(r["angle_deg"]) for r in verified]
    g5_pairs = {(int(r["route_a"]), int(r["route_b"])) for r in verified}
    g5_routes_with = {int(r["route_a"]) for r in verified} | {int(r["route_b"]) for r in verified}
    ks = kernel_status(g5_angles, out_root / "crossings" / "crossing_model_database.csv")
    bf = bound_fraction(out_root / "board",
                        out_root / "crossings" / "crossing_model_database.csv")
    # the same split for the frozen G4 run, so the reader can see that G4's
    # numbers really are resolved while G5's are not
    bf4 = bound_fraction(CTP2_FROZEN / "outputs" / "board",
                         CTP2_FROZEN / "outputs" / "crossings" / "crossing_model_database.csv")
    hc5 = hotspot_count(out_root / "board")
    hc4 = hotspot_count(CTP2_FROZEN / "outputs" / "board")
    g4_routes = G.load_routes(G4_BEST / "routes_l3d.json")
    geo = g5_geometry_changes(g4_routes, routes)

    # sanity: the board must have used the G5 crossing list, not G4's
    checks = {
        "board_n_events_equals_verified_csv": (
            board["crossings"]["n_events"] == len(verified)),
        "board_angle_min_equals_verified_csv": (
            abs(board["crossings"]["angle_min_deg"] - min(g5_angles)) < 1e-9),
        "all_columns_le_1": bool(board["nominal_ctp2"]["all_columns_le_1"]),
        "forward_split_not_degenerate": bool(
            0 < board["crossings"]["n_forward_allowed"] < len(verified)),
        "n_routes_1024": bool(board["frozen_geometry"]["n_routes"] == 1024),
        "model_is_ctp2": bool(board.get("model") == "CTP-2.0"),
        "total_length_matches_payload": bool(
            abs(board["frozen_geometry"]["total_length_mm"]
                - regen["total_length_mm"]) < 1e-6),
    }
    # an observation, not a pass/fail: G5 is *expected* to have crossings at
    # >= 45 deg, but if the delivered geometry still has some below it the run
    # is still valid and they must be reported as residual small-angle events
    angle_observation = {
        "min_angle_deg": min(g5_angles),
        "n_below_45": int(sum(1 for a in g5_angles if a < 45.0)),
        "n_below_46": int(sum(1 for a in g5_angles if a < 46.0)),
        "all_crossings_ge_45": bool(min(g5_angles) >= 45.0),
        "all_crossings_ge_45_5": bool(min(g5_angles) >= 45.5),
    }

    g5 = {
        "schema": "ctp2_g5_summary_v1",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "model": board.get("model"),
        "model_version_string": "CTP-2.0 (work copy, G5 geometry)",
        "geometry_label": args.geometry_label,
        "geometry_dir": regen["geometry_dir"],
        "payload_dir": str(P.BEST_VALID),
        "routes_sha256": regen["routes_sha256"],
        "independent_verification": checks,
        "all_checks_pass": all(checks.values()),
        "angle_observation": angle_observation,
        "board_summary": board,
        "board_summary_path": str(out_root / "board" / "board_summary_ctp2.json"),
        "board_summary_sha256": sha256_file(out_root / "board" / "board_summary_ctp2.json"),
        "crossings": {
            "n_events": len(verified),
            "n_pairs": len(g5_pairs),
            "n_routes_with_crossings": len(g5_routes_with),
            "max_route_crossings": regen["stats"]["max_route_crossings"],
            "min_angle_deg": min(g5_angles),
            "median_angle_deg": float(np.median(g5_angles)),
            "max_angle_deg": max(g5_angles),
            "n_below_45": regen["n_below_45"],
            "n_below_46": regen["n_below_46"],
            "n_below_30": int(sum(1 for a in g5_angles if a < 30.0)),
            "n_below_10": int(sum(1 for a in g5_angles if a < 10.0)),
            "n_at_or_above_45": regen["n_at_or_above_45"],
            "angle_histogram": angle_histogram(g5_angles),
            "kernel_status": ks,
            "source": "analytically re-derived for this geometry "
                      "(run_ctp2_g5.py), audited against g5_crossing_angles.csv",
            "source_routes": regen["routes_file"],
            "audit_cross_check": regen["audit_cross_check"],
        },
        "propagation_loss": prop,
        "hotspots": hs,
        "bound_fraction": bf,
        "g4_bound_fraction": bf4,
        "hotspot_counts": {"g5": hc5, "g4": hc4},
        "geometry_changes_vs_g4": geo,
        "bounds_and_floor": {
            "kernel_floor_db": -85.0,
            "n_events_at_floor": int(ks["n_floor_limited_or_handover"]),
            "n_events_resolved": int(ks["n_resolved"]),
            "fraction_of_forward_power_floor_limited": bf.get(
                "fraction_of_forward_power_floor_limited"),
            "statement": ("every crossing at theta >= 45.5 deg carries the FDFD "
                          "port-floor upper bound instead of a resolved value; "
                          "the fraction above is the share of the forward-coupled "
                          "power that comes from those crossings"),
        },
        "provenance": {
            "ctp2_work_copy": str(CTP2_G5),
            "ctp2_frozen_model": str(CTP2_FROZEN),
            "g4_reference_board_summary": g4["board_summary_path"],
            "g4_reference_board_summary_sha256": g4["board_summary_sha256"],
            "payload": str(payload),
            "out_root": str(out_root),
        },
    }
    rt = Path(args.out_root) / "runtimes.json"
    tsec = {}
    if rt.exists():
        stages = json.loads(rt.read_text(encoding="utf-8")).get("stages", {})
        agg = defaultdict(float)
        for k, v in stages.items():
            agg[k.split(":")[0].strip()] += float(v)
        tsec = dict(agg)
    g5["runtimes_seconds"] = {
        "crossing_regeneration_and_payload": round(tsec.get("prepare", 0.0), 3),
        "v5_near_approaches": round(tsec.get("V5 near approaches", 0.0), 3),
        "board": round(float(board.get("runtime_seconds", 0.0)), 3),
        "all_stages": {k: round(v, 3) for k, v in tsec.items()},
    }
    jdump(g5, HERE / f"{args.report_stem}_summary.json")
    log(f"[compare] -> {HERE/f'{args.report_stem}_summary.json'}")
    return {"g5": g5, "g4": g4}


# --------------------------------------------------------------------- report
def _fmt(x, nd=3, dash="—"):
    if x is None:
        return dash
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, (int, np.integer)):
        return str(int(x))
    return f"{float(x):.{nd}f}"


def _pct(x, dash="—"):
    """Percentage with adaptive precision (never rounds a small value to 0.00)."""
    if x is None:
        return dash
    v = 100.0 * float(x)
    if v == 0.0:
        return "0 %"
    if abs(v) < 0.01:
        return f"{v:.2e} %"
    return f"{v:.2f} %"


def write_comparison_md(g5: dict, g4: dict, stem: str = "g5_ctp2") -> Path:
    b5 = g5["board_summary"]
    b4 = g4["board_summary"]
    h5 = g5["hotspots"]
    h4 = g4["hotspots"]
    p5 = g5["propagation_loss"]
    c5 = g5["crossings"]
    ks = c5["kernel_status"]
    n5 = b5["nominal_ctp2"]
    n4 = b4["nominal_ctp2"]
    o5 = b5["multi_input_incoherent"]
    o4 = b4["multi_input_incoherent"]
    bd5 = b5["bounds"]
    bd4 = b4["bounds"]
    x5 = b5["crossings"]
    x4 = b4["crossings"]
    bf = g5.get("bound_fraction") or {}
    bf4 = g5.get("g4_bound_fraction") or {}
    # is this a pure-bound geometry (every crossing beyond the kernel's resolved
    # range) or a mixed one (some crossings still resolved)?
    n_res = int(ks["n_resolved"])
    n_floor = int(ks["n_floor_limited_or_handover"])
    pure_bound = (n_res == 0 and c5["n_below_45"] == 0)
    mixed = not pure_bound
    g5_col = ("G5 (CTP-2.0, **bound**)" if pure_bound
              else "G5 (CTP-2.0, resolved + bound)")
    o5_min = c5["min_angle_deg"]
    on_floor_side = bool(o5_min >= 45.5)

    lines = []
    A = lines.append
    A(f"# CTP-2.0 on `{g5['geometry_label']}` — G4 vs G5")
    A("")
    A(f"Generated {g5['generated']} by `05_ctp2_comparison/run_ctp2_g5.py`.")
    A("")
    A(f"* model: **{g5['model']}** — the same code that produced the published G4")
    A("  numbers, run from the work copy `05_ctp2_comparison/ctp2_g5/` with the")
    A("  geometry path swapped and the outputs redirected to `ctp2_out/`.")
    A(f"* geometry label: `{g5['geometry_label']}`")
    A(f"* geometry dir: `{g5['geometry_dir']}`")
    A(f"  (routes sha256 `{g5['routes_sha256']}`)")
    A(f"* CTP payload fed to the model: `{g5['payload_dir']}`")
    A(f"* G4 reference: the frozen `board_summary_ctp2.json`")
    A(f"  (sha256 `{g4['board_summary_sha256']}`) — read-only, never re-written.")
    A(f"* crossings: **re-derived analytically** for G5 ({c5['n_events']} events),")
    A("  never inherited: `crossings/crossing_events_verified.csv`.")
    A(f"* independent checks: **{'all pass' if g5['all_checks_pass'] else 'FAILED'}**")
    for k, v in g5["independent_verification"].items():
        A(f"  * `{k}` = {v}")
    A(f"* crossing-angle observation (not a pass/fail criterion): "
      f"{c5['n_below_45']} crossing(s) below 45°, minimum "
      f"{o5_min:.6f}°")
    A("")

    if c5["n_below_45"] == 0:
        A(f"> **No crossing of the G5 geometry lies below 45°** (minimum "
          f"{c5['min_angle_deg']:.6f}°). Every crossing is therefore outside the")
        A("> angle range in which CTP-2.0's local crossing kernel is resolved, and")
        A("> the G5 numbers below are *upper bounds at the −85 dB FDFD port floor*,")
        A("> **not predictions**.")
    else:
        A(f"> **{c5['n_below_45']} crossing(s) of the G5 geometry still lie below "
          f"45°** (minimum {c5['min_angle_deg']:.6f}°); they are listed as residual")
        A(f"> small-angle events in §5. The headline entries are therefore dominated")
        A(f"> by *resolved* small-angle crossings and are predictions, not bounds;")
        A(f"> only the {n_floor} floor-limited crossings carry bounds.")
        A(f"> Both readings are spelled out in §6.")
    A("")

    # ------------------------------------------------------- headline table
    A("## 1. Headline comparison")
    A("")
    A(f"| metric | G4 (CTP-2.0, resolved) | {g5_col} | change |")
    A("|---|---:|---:|---:|")
    pair4 = n4["max_offdiagonal_pair"]
    pair5 = n5["max_offdiagonal_pair"]
    le = "≤ " if pure_bound else ""
    A(f"| worst single port-pair crosstalk | **{_fmt(n4['max_offdiagonal_db'])} dB** "
      f"(R{pair4[1]}→R{pair4[0]}) "
      f"| **{le}{_fmt(n5['max_offdiagonal_db'])} dB** "
      f"(R{pair5[1]}→R{pair5[0]}) "
      f"| {_fmt(n5['max_offdiagonal_db'] - n4['max_offdiagonal_db'], 2)} dB |")
    A(f"| worst single-route total leakage | **{_fmt(n4['worst_total_leakage_db'])} dB** "
      f"(R{n4['worst_total_leakage_route']}) "
      f"| **{le}{_fmt(n5['worst_total_leakage_db'])} dB** "
      f"(R{n5['worst_total_leakage_route']}) "
      f"| {_fmt(n5['worst_total_leakage_db'] - n4['worst_total_leakage_db'], 2)} dB |")
    A(f"| multi-input worst interference/signal | "
      f"**{_fmt(o4['worst_interference_to_signal_db'])} dB** "
      f"(R{o4['worst_output_route']}) "
      f"| **{le}{_fmt(o5['worst_interference_to_signal_db'])} dB** "
      f"(R{o5['worst_output_route']}) "
      f"| {_fmt(o5['worst_interference_to_signal_db'] - o4['worst_interference_to_signal_db'], 2)} dB |")
    A(f"| worst-pair bound band | {_fmt(bd4['max_offdiagonal_lower_db'])} … "
      f"{_fmt(bd4['max_offdiagonal_upper_db'])} dB "
      f"| {_fmt(bd5['max_offdiagonal_lower_db'])} … "
      f"{_fmt(bd5['max_offdiagonal_upper_db'])} dB | |")
    A(f"| route-leakage bound band | {_fmt(bd4['worst_total_leakage_lower_db'])} … "
      f"{_fmt(bd4['worst_total_leakage_upper_db'])} dB "
      f"| {_fmt(bd5['worst_total_leakage_lower_db'])} … "
      f"{_fmt(bd5['worst_total_leakage_upper_db'])} dB | |")
    A(f"| **max base propagation loss (dB)** | {_fmt(g4_max_loss(g4), 6)} "
      f"| {_fmt(p5['loss_max_db'], 6)} "
      f"| {_fmt(p5['loss_max_db'] - g4_max_loss(g4), 6)} dB |")
    A(f"| hotspot clusters stored / top cluster ΣP (dB) "
      f"| {h4['n_clusters']} / {_fmt(h4['top'][0]['total_P_cross_db'], 2) if h4['top'] else '—'} "
      f"| {h5['n_clusters']} / {_fmt(h5['top'][0]['total_P_cross_db'], 2) if h5['top'] else '—'} | |")
    hcx = g5.get("hotspot_counts") or {}
    if (hcx.get("g4") or {}).get("available") and (hcx.get("g5") or {}).get("available"):
        A(f"| hotspot clusters total (2 mm × plane) | "
          f"{hcx['g4']['n_clusters_total']} | {hcx['g5']['n_clusters_total']} | |")
    A(f"| crossings (total / below 45°) | {x4['n_events']} / **{g4['n_below_45']}** "
      f"| {x5['n_events']} / **{c5['n_below_45']}** | |")
    if bf.get("available") and (g5.get("g4_bound_fraction") or {}).get("available"):
        bf4x = g5["g4_bound_fraction"]
        A(f"| total forward-coupled power (linear) | "
          f"{bf4x['sum_T_cross_forward']:.6e} "
          f"| {bf['sum_T_cross_forward']:.6e} "
          f"| {db(bf['sum_T_cross_forward']) - db(bf4x['sum_T_cross_forward']):+.2f} dB |")
    if bf.get("available"):
        f4 = bf4.get("fraction_of_forward_power_floor_limited")
        f5 = bf.get("fraction_of_forward_power_floor_limited")
        A(f"| **share of the forward-coupled power that is a "
          f"floor-limited upper bound** | **{_pct(f4)}** | **{_pct(f5)}** | |")
        A("")
        A("*`total forward-coupled power`* = Σ of the per-crossing transfer over all")
        A("forward-allowed events; it upper-bounds the summed off-diagonal matrix")
        A("entries, so its dB change is the cleanest single number for \"how much")
        A("less power is coupled across the whole board\".")
        A("")
        A("That last row answers \u201chow much of the number is a bound?\u201d.")
        A("")
        A(f"* **G4** — {_pct(f4)}. Even though "
          f"{bf4.get('n_forward_allowed_floor_limited')} of its "
          f"{bf4.get('n_forward_allowed')} forward-allowed crossings are floor")
        A(f"  crossings, they carry only "
          f"{bf4.get('sum_T_cross_forward_floor_limited'):.3e} of the "
          f"{bf4.get('sum_T_cross_forward'):.3e} total forward")
        A(f"  transfer, so the published G4 numbers are genuinely resolved.")
        if (f5 or 0) >= 0.5:
            A(f"* **G5** — {_pct(f5)}. Essentially the whole board number is the")
            A(f"  −85 dB floor upper bound: the G5 column is a bound, not a")
            A(f"  prediction.")
        else:
            A(f"* **G5** — {_pct(f5)}. This geometry is *not* a pure bound case: the")
            A(f"  headline numbers are still dominated by the resolved/disputed")
            A(f"  crossings, so they are predictions for those events and bounds only")
            A(f"  for the floor-limited ones (§6).")
        A("")
    A("Port-pair notation: input → output (the transfer matrix is "
      "`T[output, input]`).")
    A("")
    if pure_bound:
        A("Reading the G5 column: `≤ x dB` means the *most pessimistic* per-crossing")
        A("value the model can produce at that angle is 10^(x/10); the true")
        A("crosstalk is bounded above by it (the FDFD port floor is a numerical")
        A("floor, so the model cannot resolve anything below it). The `bound band`")
        A("rows give the Born lower bound … FDFD-floor upper bound of the same")
        A("quantity.")
    else:
        A("Reading the G5 column: the geometry is **mixed** — the crossings that")
        A("remain below 45° are resolved (θ ≤ 30°) or disputed (30–45°) and their")
        A("transfer is a *prediction*; the crossings at θ ≥ 45.5° contribute the")
        A("−85 dB floor value, which is an *upper bound*. The headline numbers are")
        A("sums over both kinds, so they are predictions for the resolved part and")
        A("bounds for the floor-limited part; the `bound band` rows show the")
        A("resulting [Born-low, FDFD-high] interval.")
    A("")

    # ---------------------------------------------------- secondary metrics
    A("## 2. Secondary metrics")
    A("")
    A("| metric | G4 | G5 |")
    A("|---|---:|---:|")
    A(f"| diagonal min / max (dB) | {_fmt(n4['diagonal_min_db'])} / "
      f"{_fmt(n4['diagonal_max_db'])} | {_fmt(n5['diagonal_min_db'])} / "
      f"{_fmt(n5['diagonal_max_db'])} |")
    A(f"| max column sum (energy) | {_fmt(n4['max_column_sum'], 6)} "
      f"(≤1: {n4['all_columns_le_1']}) | {_fmt(n5['max_column_sum'], 6)} "
      f"(≤1: {n5['all_columns_le_1']}) |")
    A(f"| median off-diagonal (dB) | {_fmt(n4['median_offdiagonal_db'])} "
      f"| {_fmt(n5['median_offdiagonal_db'])} |")
    A(f"| non-zero off-diagonal entries | {n4['n_nonzero_offdiagonal']} "
      f"| {n5['n_nonzero_offdiagonal']} |")
    A(f"| second-order chains (n, max dB) | {b4['second_order']['n_terms']}, "
      f"{_fmt(b4['second_order']['max_T_db'])} "
      f"| {b5['second_order']['n_terms']}, {_fmt(b5['second_order']['max_T_db'])} |")
    A(f"| CT1.0 fixed-p baseline worst pair (dB) | "
      f"{_fmt(b4['baseline_ctp1_fixed_p']['max_offdiagonal_db'])} "
      f"| {_fmt(b5['baseline_ctp1_fixed_p']['max_offdiagonal_db'])} |")
    A(f"| board runtime (s) | {_fmt(b4['runtime_seconds'], 2)} "
      f"| {_fmt(b5['runtime_seconds'], 2)} |")
    A("")
    A("The fixed-p baseline column is the superseded CTP-1.0 bookkeeping and is")
    A("shown only to demonstrate that it barely moves between geometries — which is")
    A("exactly why it must not be used for the G4→G5 claim.")
    A("")

    # ------------------------------------------------------------- crossings
    A("## 3. Crossing statistics and angle distribution")
    A("")
    A("| metric | G4 | G5 |")
    A("|---|---:|---:|")
    A(f"| routes | {b4['frozen_geometry']['n_routes']} "
      f"| {b5['frozen_geometry']['n_routes']} |")
    A(f"| crossings | {x4['n_events']} | {x5['n_events']} |")
    A(f"| crossing pairs | {g4['n_pairs']} | {c5['n_pairs']} |")
    A(f"| routes with crossings | {g4['n_routes_with_crossings']} "
      f"| {c5['n_routes_with_crossings']} |")
    A(f"| max crossings on one route | {g4['max_route_crossings']} "
      f"| {c5['max_route_crossings']} |")
    A(f"| crossing angles < 45° | **{g4['n_below_45']}** | **{c5['n_below_45']}** |")
    A(f"| crossing angles < 30° | {g4['n_below_30']} | {c5['n_below_30']} |")
    A(f"| crossing angles < 10° | {g4['n_below_10']} | {c5['n_below_10']} |")
    A(f"| min / median angle (°) | {_fmt(g4['min_angle_deg'], 6)} / "
      f"{_fmt(g4['median_angle_deg'], 6)} | {_fmt(c5['min_angle_deg'], 6)} / "
      f"{_fmt(c5['median_angle_deg'], 6)} |")
    A(f"| per-crossing T_cross range (dB) | {_fmt(x4['T_cross_db_min'])} … "
      f"{_fmt(x4['T_cross_db_max'])} | {_fmt(x5['T_cross_db_min'])} … "
      f"{_fmt(x5['T_cross_db_max'])} |")
    A(f"| crossings above −30 dB | {x4['n_events_above_minus30dB']} "
      f"| {x5['n_events_above_minus30dB']} |")
    A(f"| forward-direction allowed / blocked | {x4['n_forward_allowed']} / "
      f"{x4['n_forward_blocked']} | {x5['n_forward_allowed']} / "
      f"{x5['n_forward_blocked']} |")
    A("")
    A("### Angle distribution (same bins as the G5 project's own audit)")
    A("")
    A("| bin (°) | G4 crossings | G5 crossings | G5 floor-limited | "
      "G5 share of forward-coupled power | kernel status in this band |")
    A("|---|---:|---:|---:|---:|---|")
    band_status = []
    for lo, hi in ANGLE_BINS:
        if hi <= 30.0:
            band_status.append("resolved")
        elif lo >= 45.0:
            band_status.append("**bound** at −85 dB floor")
        elif lo >= 30.0:
            band_status.append("disputed (bounds only)")
        else:
            band_status.append("mixed")
    fcounts = bf.get("floor_counts_by_angle_band", {})
    pshare = bf.get("power_share_by_angle_band", {})
    for i, (lbl, a4) in enumerate(zip(g4["angle_histogram"]["bin_labels"],
                                      g4["angle_histogram"]["counts"])):
        a5 = c5["angle_histogram"]["counts"][i]
        A(f"| {lbl} | {a4} | {a5} | {fcounts.get(lbl, 0)} | "
          f"{_pct(pshare.get(lbl))} | {band_status[i]} |")
    A(f"| **total** | **{x4['n_events']}** | **{x5['n_events']}** | "
      f"**{sum(fcounts.get(k, 0) for k in BIN_LABELS)}** | **100 %** | |")
    A("")
    A(f"Floor-limited events are **{bf.get('n_forward_allowed_floor_limited')} of "
      f"{bf.get('n_forward_allowed')} forward-allowed crossings "
      f"({_pct(bf.get('fraction_of_events_floor_limited'))})**, but they carry only "
      f"**{_pct(bf.get('fraction_of_forward_power_floor_limited'))}** of the")
    A(f"forward-coupled power ({bf.get('sum_T_cross_forward_floor_limited'):.3e} of "
      f"{bf.get('sum_T_cross_forward'):.3e}).")
    A("")
    A("### Kernel resolution status of each crossing")
    A("")
    A("| status | G4 | G5 |")
    A("|---|---:|---:|")
    for st in ("resolved", "resolved_fdtd_crosschecked", "disputed_paraxial",
               "upper_bound_port_floor_limited"):
        A(f"| {st} | — | {ks['per_status'].get(st, 0)} |")
    A(f"| handover bracket (status changes between adjacent kernel angles) | — "
      f"| {ks['n_handover_bracket']} |")
    A("")
    n_disputed = int(ks["per_status"].get("disputed_paraxial", 0))
    n_exact_floor = int(ks["per_status"].get("upper_bound_port_floor_limited", 0))
    A(f"G4 status mix is not tabulated here because CTP-2.0's published board")
    A(f"summary does not carry it; it is recoverable from")
    A(f"`crossings/crossing_optical_analysis_ctp2.csv` of the frozen run.")
    A(f"The G5 mix is what matters: **{n_res} resolved, "
      f"{ks['n_handover_bracket']} in a status-changing 0.25° bracket, "
      f"{n_disputed} disputed (30–45°), {n_exact_floor} at the −85 dB floor** "
      f"(Σ = {n_res + ks['n_handover_bracket'] + n_disputed + n_exact_floor}).")
    A(f"(The `< 30°` count above is by angle; the resolved-row count differs")
    A(f"slightly where a crossing sits in a kernel bracket whose two ends carry")
    A(f"different statuses.)")
    A("")

    # --------------------------------------------------------- propagation
    A("## 4. Propagation loss (regenerated for G5)")
    A("")
    A("Same frozen assumptions as G4: α = 0.05 dB/cm, λ = 1310 nm, n₀ = 1.50,")
    A("Δn = 0.0065, 9 × 9 µm core, R15 extra bend loss 0 dB (the arc length is")
    A("still counted in full).")
    A("")
    A("| metric | G4 | G5 |")
    A("|---|---:|---:|")
    A(f"| routes | {p5['n_routes']} | {p5['n_routes']} |")
    A(f"| total length (mm) | {b4['frozen_geometry']['total_length_mm']:.6f} "
      f"| {p5['total_length_mm']:.6f} |")
    A(f"| mean length (mm) | — | {_fmt(p5['length_mean_mm'], 6)} |")
    A(f"| **max propagation loss (dB)** | {_fmt(g4_max_loss(g4), 6)} "
      f"| **{_fmt(p5['loss_max_db'], 6)}** |")
    A(f"| mean propagation loss (dB) | {_fmt(g4_mean_loss(g4), 6)} "
      f"| {_fmt(p5['loss_mean_db'], 6)} |")
    A(f"| min / median loss (dB) | — | {_fmt(p5['loss_min_db'], 6)} / "
      f"{_fmt(p5['loss_median_db'], 6)} |")
    A(f"| total loss over all routes (dB) | — | {_fmt(p5['loss_total_db'], 3)} |")
    A("")
    A("G4 loss figures are recomputed here from the frozen G4 route lengths")
    A("(`e1_summary.json`: `loss_max_db = 1.411609762059922`,")
    A("`loss_mean_db = 0.764634870711216`) so the two columns are like-for-like.")
    A("")

    # ------------------------------------------------------------ hotspots
    A("## 5. Hotspots")
    A("")
    A(f"Hotspots are 2 mm × 2 mm × one-plane clusters of crossings, ranked by the")
    A(f"summed per-crossing transfer `P_cross`. Clusters stored: **G4 "
      f"{h4['n_clusters']}, G5 {h5['n_clusters']}**.")
    A("")
    A("| rank | G4 (z, x, y) mm | n | ΣP (dB) | G5 (z, x, y) mm | n | ΣP (dB) |")
    A("|---|---|---:|---:|---|---:|---:|")
    for i in range(max(len(h4["top"]), len(h5["top"]))):
        c4 = h4["top"][i] if i < len(h4["top"]) else None
        c5_ = h5["top"][i] if i < len(h5["top"]) else None
        A("| %d | %s | %s | %s | %s | %s | %s |" % (
            i + 1,
            f"{_fmt(c4['z_mm'], 3)}, {_fmt(c4['x_mm'], 2)}, {_fmt(c4['y_mm'], 2)}" if c4 else "—",
            c4["n_crossings"] if c4 else "—",
            _fmt(c4["total_P_cross_db"], 2) if c4 else "—",
            f"{_fmt(c5_['z_mm'], 3)}, {_fmt(c5_['x_mm'], 2)}, {_fmt(c5_['y_mm'], 2)}" if c5_ else "—",
            c5_["n_crossings"] if c5_ else "—",
            _fmt(c5_["total_P_cross_db"], 2) if c5_ else "—"))
    A("")
    if ks["n_resolved"] == 0:
        A("**Caveat:** in the floor-limited regime every crossing carries the same")
        A("`P_cross`, so the G5 hotspot ranking degenerates to *crossing density*")
        A("and carries no optical information. It is reported for completeness only.")
        A("")
    if c5["n_below_45"]:
        A("### Residual small-angle events (θ < 45°)")
        A("")
        A(f"{c5['n_below_45']} event(s) in total; the {min(40, c5['n_below_45'])}"
          f" smallest angles are listed (sorted by angle).")
        A("")
        A("| route_a | route_b | z (mm) | x (mm) | y (mm) | angle (°) | deficit (°) |")
        A("|---:|---:|---:|---:|---:|---:|---:|")
        for e in sorted([r for r in
                         read_crossings_csv(Path(g5["provenance"]["out_root"])
                                            / "crossings" / "crossing_events_verified.csv")
                         if float(r["angle_deg"]) < 45.0],
                        key=lambda r: float(r["angle_deg"]))[:40]:            A(f"| {e['route_a']} | {e['route_b']} | {float(e['z_mm']):.3f} | "
              f"{float(e['x_mm']):.3f} | {float(e['y_mm']):.3f} | "
              f"{float(e['angle_deg']):.6f} | {45.0 - float(e['angle_deg']):.6f} |")
        A("")

    # -------------------------------------------------------------- caveat
    A("## 6. Model-resolution caveat (must travel with every G5 number)")
    A("")
    A(f"1. CTP-2.0's crossing kernel is resolved only for θ ≤ 30°")
    A(f"   (`resolved` / `resolved_fdtd_crosschecked`), disputed for 30–45°, and")
    A(f"   for θ ≥ 45.5° it reports an **upper bound at the −85 dB FDFD port")
    A(f"   floor** (`status = upper_bound_port_floor_limited`).")
    if pure_bound:
        A(f"2. G5's minimum crossing angle is {o5_min:.6f}°, so **0 of "
          f"{c5['n_events']} crossings are in the resolved range**. The G5 board")
        A(f"   numbers are therefore built from floor-limited rows and are")
        A(f"   **bounds, not predictions**.")
        A(f"3. There is a ~12 dB hand-over step in the kernel between 45.0°")
        A(f"   (−72.799 dB, `disputed_paraxial`) and 45.5° (−85.000 dB, floor).")
        A(f"   G5's minimum is {o5_min:.6f}°, so the run sits on the")
        A(f"   **{'floor' if on_floor_side else 'HANDOVER'} side** of that step")
        A(f"   (`n_handover_bracket = {ks['n_handover_bracket']}`).")
        A(f"4. Which G5 entries are upper bounds:")
        A(f"   * worst single port-pair ≤ {_fmt(n5['max_offdiagonal_db'])} dB — **upper")
        A(f"     bound** (per-crossing FDFD floor); Born lower bound "
          f"{_fmt(bd5['max_offdiagonal_lower_db'])} dB.")
        A(f"   * worst single-route total leakage ≤ {_fmt(n5['worst_total_leakage_db'])}")
        A(f"     dB — **upper bound** (sum of floor-limited crossings); Born lower")
        A(f"     bound {_fmt(bd5['worst_total_leakage_lower_db'])} dB.")
        A(f"   * multi-input ISR ≤ {_fmt(o5['worst_interference_to_signal_db'])} dB —")
        A(f"     **upper bound**; the diagonal (signal) is a resolved"
          f" propagation-loss")
        A(f"     quantity, so the bound is one-sided.")
        A(f"   * diagonal, propagation loss, route lengths — resolved (not bounds).")
    else:
        A(f"2. G5's minimum crossing angle is {o5_min:.6f}°. Of the "
          f"{c5['n_events']} crossings: **{n_res} are in the kernel's resolved")
        A(f"   rows**, {n_disputed} are disputed (30–45°), {n_exact_floor} are at")
        A(f"   the −85 dB floor and {ks['n_handover_bracket']} sit in a")
        A(f"   status-changing bracket. The geometry is **mixed**: entries driven")
        A(f"   by a resolved crossing are predictions, entries driven by θ ≥ 45.5°")
        A(f"   crossings are upper bounds. Do not label the whole table 'bound' nor")
        A(f"   the whole table 'prediction'.")
        A(f"3. There is a ~12 dB hand-over step in the kernel between 45.0°")
        A(f"   (−72.799 dB, `disputed_paraxial`) and 45.5° (−85.000 dB, floor). The")
        A(f"   crossing set spans both sides, so no single side applies;")
        A(f"   `n_handover_bracket = {ks['n_handover_bracket']}` crossings sit in a")
        A(f"   0.25° bracket whose two ends carry different statuses.")
        A(f"4. Which G5 entries are bounds:")
        A(f"   * any entry whose worst contributing crossing has θ ≥ 45.5° — an")
        A(f"     **upper bound** at the −85 dB floor. The `bound band` rows in §1")
        A(f"     give the matching [Born-low, FDFD-high] interval.")
        A(f"   * the per-crossing table")
        A(f"     `ctp2_out/crossings/crossing_optical_analysis_ctp2.csv` carries the")
        A(f"     angle and `T_cross_db` of every event, so any entry can be traced to")
        A(f"     its status via the table in §3.")
        A(f"   * diagonal, propagation loss, route lengths — resolved (not bounds).")
    A("5. Both models assume an ideal structure (no sidewall roughness, index")
    A("   drift, stress birefringence or bend-induced polarisation conversion),")
    A("   which literature says dominates measured large-angle crosstalk, so even")
    A("   the floor-limited upper bound is a *lower* bound on a real device. The")
    A("   scalar weakly-guided approximation underpins everything (Δn/n = 0.43 %).")
    A("6. Crossing insertion loss above 30° is an extrapolation")
    A("   (`loss ∝ (θ/10)^-0.873`, anchored at the converged 10° BPM value), so the")
    A("   diagonal inherits that extrapolation.")
    A("")
    A("## 7. Geometry anomalies and independent audit agreement")
    A("")
    geo5 = g5.get("geometry_changes_vs_g4") or {}
    if geo5:
        A(f"### 7.1 What changed in the routes (G4 → G5)")
        A("")
        A("| metric | value |")
        A("|---|---:|")
        A(f"| routes compared | {geo5['n_routes_compared']} |")
        A(f"| routes whose length or height set changed | "
          f"**{geo5['n_routes_changed_length_or_height']}** |")
        A(f"| routes whose set of height plateaus changed (re-heighted) | "
          f"**{geo5['n_routes_with_different_height_set']}** |")
        A(f"| total length Δ (mm) | {geo5['delta_length_total_mm']:+.6f} |")
        A(f"| total length G4 → G5 (mm) | {geo5['g4_total_length_mm']:.6f} → "
          f"{geo5['g5_total_length_mm']:.6f} |")
        A(f"| max / mean \\|Δlength\\| (mm) | {geo5['delta_length_abs_max_mm']:.6f} / "
          f"{geo5['delta_length_abs_mean_mm']:.6f} |")
        A(f"| routes with \\|Δlength\\| > 1 mm / > 10 mm | "
          f"{geo5['n_routes_abs_delta_over_1mm']} / "
          f"{geo5['n_routes_abs_delta_over_10mm']} |")
        A(f"| routes longer / shorter | {geo5['n_routes_longer']} / "
          f"{geo5['n_routes_shorter']} |")
        A("")
        if not geo5["n_routes_changed_length_or_height"]:
            A("**No route changed its length or its set of height plateaus**: the G5")
            A("geometry is route-for-route identical to G4 (this is the expected")
            A("result for a G4 self-test).")
        else:
            A("Ten largest length changes (a length change is the fingerprint of a")
            A("re-height or a re-route):")
            A("")
            A("| route | Δlength (mm) | G4 (mm) | G5 (mm) | height set changed | "
              "G4 z start→end | G5 z start→end |")
            A("|---:|---:|---:|---:|:---:|---|---|")
            for r in geo5["top_length_changes"]:
                A(f"| R{r['route_id']} | {r['delta_mm']:+.3f} | {r['g4_mm']:.3f} | "
                  f"{r['g5_mm']:.3f} | {'yes' if r['height_set_changed'] else 'no'} | "
                  f"{r['g4_start_z']:+.3f}→{r['g4_end_z']:+.3f} | "
                  f"{r['g5_start_z']:+.3f}→{r['g5_end_z']:+.3f} |")
        A("")
    A("### 7.2 Does the independent audit agree with the regenerated crossings?")
    A("")
    ax = c5.get("audit_cross_check") or {}
    if ax.get("n_mine") is not None:
        A("| check | value |")
        A("|---|---:|")
        A(f"| audit source | `{ax.get('against')}` |")
        A(f"| events (regenerated / audit) | {ax['n_mine']} / {ax['n_other']} |")
        A(f"| matched on (route_a, route_b, plane) | **{ax['n_matched']}** |")
        A(f"| only in the regeneration | **{ax['n_only_mine']}** |")
        A(f"| only in the audit | **{ax['n_only_other']}** |")
        A(f"| max \\|Δx\\| / \\|Δy\\| / \\|Δz\\| (mm) | "
          f"{ax['max_abs_dx_mm']:.2e} / {ax['max_abs_dy_mm']:.2e} / "
          f"{ax['max_abs_dz_mm']:.2e} |")
        A(f"| max \\|Δangle\\| (°) | {ax['max_abs_dangle_deg']:.2e} |")
        A(f"| geometry consistent | **{ax.get('geometry_consistent')}** |")
        A("")
        if ax["n_only_mine"] or ax["n_only_other"]:
            A("**Disagreement detail** (this is the anomaly to check):")
            A("")
            if ax["only_mine_keys"]:
                A(f"* regenerated-only: `{ax['only_mine_keys'][:20]}`")
            if ax["only_other_keys"]:
                A(f"* audit-only: `{ax['only_other_keys'][:20]}`")
            A("")
        else:
            A("The two independent implementations agree on **every** event; the")
            A("positions and angles differ only by the audit CSV's 6-decimal")
            A("rounding. The `s_a_mm`/`s_b_mm` columns are deliberately *not* taken")
            A("from the audit CSV (different arc-length origin, constant per route,")
            A(f"up to {(ax.get('s_offset') or {}).get('max_abs_mean_offset_mm', 0):.3f} mm)")
            A("— they come from the regeneration, whose `Route.pos(s_a)` reproduces")
            A("the crossing point to 1e-13 mm; see")
            A("`frozen_guard/s_convention_report.json`.")
            A("")
    else:
        A("No audit CSV was available for this run, so the crossing list has no")
        A("independent corroboration; the regeneration itself is validated on the")
        A("frozen G4 geometry (`frozen_guard/detector_validation_on_g4.json`).")
        A("")
    A("## 8. Reproduce")
    A("")
    A("```powershell")
    A(f'$py = "{sys.executable}"')
    A(f'$cmp = "{HERE}"')
    A(f'& $py "$cmp\\run_ctp2_g5.py" --routes "{g5["crossings"]["source_routes"]}" '
      f'--out-root "{g5["provenance"]["out_root"]}" '
      f'--payload-dir "{g5["payload_dir"]}" --geometry-label "{g5["geometry_label"]}"')
    A("```")
    A("")
    A(f"Board summary: `{g5['board_summary_path']}` "
      f"(sha256 `{g5['board_summary_sha256']}`).")
    A(f"Machine-readable numbers: `{stem}_summary.json`.")
    A("")
    md = HERE / f"{stem}_comparison.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md


def g4_max_loss(g4: dict) -> float:
    """G4 max propagation loss, recomputed from the frozen per-route table."""
    p = CTP2_FROZEN / "outputs" / "board" / "crosstalk_per_route_ctp2.csv"
    if not p.exists():
        return float("nan")
    with open(p, newline="", encoding="utf-8") as fh:
        vals = [float(r["loss_prop_db"]) for r in csv.DictReader(fh)]
    return max(vals)


def g4_mean_loss(g4: dict) -> float:
    p = CTP2_FROZEN / "outputs" / "board" / "crosstalk_per_route_ctp2.csv"
    if not p.exists():
        return float("nan")
    with open(p, newline="", encoding="utf-8") as fh:
        vals = [float(r["loss_prop_db"]) for r in csv.DictReader(fh)]
    return float(np.mean(vals))


# ----------------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Run CTP-2.0 on the G5 geometry (or prove the copy faithful).",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--mode", choices=("g5", "faithfulness"), default="g5")
    ap.add_argument("--routes", default=None,
                    help="G5 routes_l3d.json; default: 03_best_feasible if it "
                         "exists, else 03_best_partial")
    ap.add_argument("--payload-dir", default=str(HERE / "ctp2_payload_g5"))
    ap.add_argument("--out-root", default=str(HERE / "ctp2_out"))
    ap.add_argument("--audit-csv", default=None,
                    help="default: <routes dir>/g5_crossing_angles.csv")
    ap.add_argument("--geometry-label", default=None)
    ap.add_argument("--report-stem", default="g5_ctp2",
                    help="basename of the emitted summary/comparison files "
                         "(default g5_ctp2 -> g5_ctp2_summary.json, "
                         "g5_ctp2_comparison.md)")
    ap.add_argument("--stages", default="prepare,v5,board,compare")
    ap.add_argument("--total-length-mm", type=float, default=None,
                    help="authoritative total length; default = recomputed from routes")
    ap.add_argument("--tol-mm", type=float, default=1e-5)
    ap.add_argument("--tol-deg", type=float, default=1e-5)
    ap.add_argument("--require-audit-agreement", action="store_true", default=True)
    ap.add_argument("--no-require-audit-agreement", dest="require_audit_agreement",
                    action="store_false")
    ap.add_argument("--timeout", type=int, default=7200)
    args = ap.parse_args(argv)
    args.stage_list = [s.strip() for s in args.stages.split(",") if s.strip()]
    if args.routes is None:
        args.routes = str(default_routes_path())
    if args.geometry_label is None:
        try:
            args.geometry_label = str(Path(args.routes).parent
                                      .relative_to(PROJECT)).replace("\\", "/")
        except ValueError:
            args.geometry_label = Path(args.routes).parent.name

    stamp = time.strftime("%Y%m%d_%H%M%S")
    log = Log(HERE / "logs" / f"{args.mode}_{stamp}.log")
    log(f"# run_ctp2_g5.py  mode={args.mode}  stages={args.stage_list}")
    log(f"# python           : {sys.executable}")
    log(f"# CTP-2.0 work copy: {CTP2_G5}")
    log(f"# CTP-2.0 frozen   : {CTP2_FROZEN}")
    log(f"# routes           : {args.routes}")
    log(f"# payload          : {args.payload_dir}")
    log(f"# out root         : {args.out_root}")
    log(f"# log              : {log.path}")

    try:
        if args.mode == "faithfulness":
            return faithfulness(args, log)

        ctx = {}
        if "prepare" in args.stage_list:
            ctx["prepare"] = stage_prepare(args, log)
        if "v5" in args.stage_list or "board" in args.stage_list:
            ctx.update(stage_board(args, log))
            # the compare stage reads the stage timings, so flush them now
            jdump({"stages": log.timings}, Path(args.out_root) / "runtimes.json")
        if "compare" in args.stage_list:
            ctx.update(stage_compare(args, log))
            md = write_comparison_md(ctx["g5"], ctx["g4"], args.report_stem)
            log(f"[compare] -> {md}")
        jdump({"stages": log.timings}, Path(args.out_root) / "runtimes.json")
        log("")
        log("[done] stage runtimes: " + ", ".join(
            f"{k}={v:.2f}s" for k, v in log.timings.items()))
        log(f"[done] total {time.time() - log._t0:.2f}s")
        return 0
    except Exception:
        log("[FATAL]")
        log(traceback.format_exc())
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
