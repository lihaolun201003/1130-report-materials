# -*- coding: utf-8 -*-
"""Probe: strict-D56 crossing admissibility + window half-width vs crossing angle.

READ-ONLY probe.  It imports the project's two independent strict-D56
implementations and measures, for two straight centre lines crossing at theta:

  1. the authoritative *validator* test
     ``fslw.validate_fslw.evaluate_pair(..., policy='strict')`` (which reads the
     module-global ``STRICT_SINE_MIN``),
  2. the *search-side* test ``d56.index.D56Index(crossing_policy='strict')``
     (which reads the per-instance ``min_cross_angle_deg``),
  3. the solved strict window half-width ``half_a_left`` reported by (1).

Nothing in the project is modified: the 45 deg validator case is produced by
assigning ``validate_fslw.STRICT_SINE_MIN`` in this process only.

Run from the project root::

    set PYTHONPATH=<project root>
    .venv\\Scripts\\python.exe ^
      experiments\\G5_ANGLE45_NATIVE3D_20H_1024\\01_algorithm\\constraint_audit\\probe\\angle_window_probe.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.d56.index import D56Index, prepare as d56_prepare  # noqa: E402
from four_side_1024.fslw import validate_fslw as V  # noqa: E402

CLEARANCE = 0.08
ANGLES = (5.0, 10.0, 30.0, 45.0, 90.0)


def two_lines(theta_deg, length=60.0):
    """Two straight lines through the origin, directions 0 deg and theta."""
    theta = math.radians(theta_deg)
    half = 0.5 * length
    first = dict(kind='line', p0=[-half, 0.0], p1=[half, 0.0])
    second = dict(kind='line',
                  p0=[-half * math.cos(theta), -half * math.sin(theta)],
                  p1=[half * math.cos(theta), half * math.sin(theta)])
    return first, second


def validator_case(theta_deg, sine_min):
    """Return (valid, kinds, half_a_left, half_b_left) from the validator test."""
    first, second = two_lines(theta_deg)
    pa = V.prepare_route([first], route_id='A')
    pb = V.prepare_route([second], route_id='B')
    original = V.STRICT_SINE_MIN
    V.STRICT_SINE_MIN = float(sine_min)
    try:
        result = V.evaluate_pair(pa, pb, clearance=CLEARANCE,
                                 sagitta=V.SAGITTA, policy='strict')
    finally:
        V.STRICT_SINE_MIN = original
    if result is None:
        return None, ['no_interaction'], None, None
    kinds = [item.get('kind') for item in result.get('violations') or []]
    crossings = result.get('crossings') or []
    half_a = crossings[0].get('half_a_left') if crossings else None
    half_b = crossings[0].get('half_b_left') if crossings else None
    return bool(result.get('valid')), kinds, half_a, half_b


def search_case(theta_deg, min_angle_deg):
    """Return (valid, reason) from the search-side D56Index strict evaluation."""
    first, second = two_lines(theta_deg)
    index = D56Index(width=0.05, gap=CLEARANCE - 0.05, sagitta=0.0005,
                     min_cross_angle_deg=min_angle_deg,
                     crossing_policy='strict')
    index.add(1, d56_prepare([first]))
    evaluation = index.evaluate(d56_prepare([second]))
    return bool(evaluation.valid), evaluation.reason, len(evaluation.crossings)


def main():
    sine5 = math.sin(math.radians(5.0))
    sine45 = math.sin(math.radians(45.0))
    rows = []
    for theta in ANGLES:
        rad = math.radians(theta)
        bisector = CLEARANCE / (2.0 * math.sin(rad / 2.0))
        along_line = CLEARANCE / math.sin(rad)
        v5_valid, v5_kinds, half_a, half_b = validator_case(theta, sine5)
        v45_valid, v45_kinds, _h45a, _h45b = validator_case(theta, sine45)
        s5_valid, s5_reason, s5_events = search_case(theta, 5.0)
        s45_valid, s45_reason, s45_events = search_case(theta, 45.0)
        rows.append(dict(
            theta_deg=theta,
            clearance_mm=CLEARANCE,
            analytic_bisector_mm=round(bisector, 6),
            analytic_along_route_mm=round(along_line, 6),
            validator_solved_half_a_mm=(None if half_a is None
                                        else round(half_a, 6)),
            validator_solved_half_b_mm=(None if half_b is None
                                        else round(half_b, 6)),
            validator_sin5_valid=v5_valid,
            validator_sin5_kinds=v5_kinds,
            validator_sin45_valid=v45_valid,
            validator_sin45_kinds=v45_kinds,
            d56index_5deg_valid=s5_valid,
            d56index_5deg_reason=s5_reason,
            d56index_5deg_crossings=s5_events,
            d56index_45deg_valid=s45_valid,
            d56index_45deg_reason=s45_reason,
            d56index_45deg_crossings=s45_events,
        ))
    print(json.dumps(dict(
        probe='strict-D56 crossing admissibility vs crossing angle',
        clearance_mm=CLEARANCE,
        width_mm=0.05,
        edge_gap_mm=0.03,
        sagitta_mm=0.0005,
        validator='four_side_1024.fslw.validate_fslw.evaluate_pair(policy="strict")',
        validator_sine_global='validate_fslw.STRICT_SINE_MIN (= sin(5 deg) in the frozen code)',
        search_side='four_side_1024.d56.index.D56Index(crossing_policy="strict").evaluate',
        rows=rows,
    ), indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
