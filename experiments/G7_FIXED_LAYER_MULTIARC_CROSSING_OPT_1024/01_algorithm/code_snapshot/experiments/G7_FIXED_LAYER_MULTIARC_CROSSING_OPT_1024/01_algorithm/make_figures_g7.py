# -*- coding: utf-8 -*-
"""Build all G7 figures from the delivered artefacts.

Inputs: 00_frozen_g6/, 02_sa_runs/arm_*/, 03_best_valid/, 06_reports/g7_analysis.json
Outputs: 05_figures/*.png
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
EXP = os.path.abspath(os.path.join(HERE, '..'))
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)

from four_side_1024.fanout1024.xyzrouter.g7 import plots_g7  # noqa: E402

FIG = os.path.join(EXP, '05_figures')
RUN = os.path.join(EXP, '02_sa_runs')
FROZEN = os.path.join(EXP, '00_frozen_g6')
BEST = os.path.join(EXP, '03_best_valid')
REPORTS = os.path.join(EXP, '06_reports')


def _cross_csv(root):
    for base, _dirs, files in os.walk(root):
        for name in files:
            if name == 'g5_crossing_angles.csv':
                return os.path.join(base, name)
    return None


def _best(value, default=None):
    return value if value is not None else default


def main():
    os.makedirs(FIG, exist_ok=True)
    made = []
    arms = dict(A=os.path.join(RUN, 'arm_A_plane'),
                B=os.path.join(RUN, 'arm_B_plane'),
                C=os.path.join(RUN, 'arm_C_plane'))
    arms = {key: value for key, value in arms.items() if os.path.isdir(value)}
    if arms:
        made.append(plots_g7.fig_convergence(
            arms, os.path.join(FIG, 'fig01_convergence.png')))
    arm_best = {}
    for arm, run_dir in arms.items():
        summary_path = os.path.join(run_dir, 'sweep_summary.json')
        if os.path.exists(summary_path):
            with open(summary_path, encoding='utf-8') as handle:
                summary = json.load(handle)
            if summary.get('best_key'):
                arm_best[arm] = int(summary['best_key'][0])
    if arm_best:
        made.append(plots_g7.fig_arm_compare(
            arm_best, os.path.join(FIG, 'fig02_arm_comparison.png')))
    analysis_path = os.path.join(REPORTS, 'g7_analysis.json')
    if os.path.exists(analysis_path):
        with open(analysis_path, encoding='utf-8') as handle:
            analysis = json.load(handle)
        made.append(plots_g7.fig_per_layer_compare(
            analysis, os.path.join(FIG, 'fig03_per_layer_crossings.png')))
        made.append(plots_g7.fig_route_distribution(
            analysis, os.path.join(FIG, 'fig04_route_distribution.png')))
        made.append(plots_g7.fig_attribution(
            analysis, os.path.join(FIG, 'fig05_attribution.png')))
    before_csv = _cross_csv(FROZEN)
    after_csv = _cross_csv(BEST)
    if before_csv and after_csv:
        made.append(plots_g7.fig_hotspots(
            before_csv, after_csv,
            os.path.join(FIG, 'fig06_angle_histogram_before_after.png')))
        made.append(plots_g7.fig_per_layer_crossings(
            after_csv, os.path.join(FIG, 'fig07_per_layer_crossing_map.png')))
    before_routes = os.path.join(FROZEN, 'routes_l3d.json')
    after_routes = os.path.join(BEST, 'routes_l3d.json')
    if os.path.exists(before_routes):
        made.append(plots_g7.fig_per_layer_geometry(
            before_routes, os.path.join(FIG, 'fig08_per_layer_routes_before.png')))
    if os.path.exists(after_routes):
        made.append(plots_g7.fig_per_layer_geometry(
            after_routes, os.path.join(FIG, 'fig09_per_layer_routes_after.png')))
    print('[g7-figures] wrote %d figures' % len(made))
    for path in made:
        print('  ' + path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
