# -*- coding: utf-8 -*-
"""Build every G6 figure from the delivered artefacts (reproducible offline).

Inputs (all under ``experiments/G6_ANGLE45_MULTIARC_SA_20H_1024``):
  * ``02_sa_runs/warm_B_v4``                     search run (per-seed histories)
  * ``00_baseline/frozen_g5_v5``                 before geometry
  * ``03_best_partial/validation/independent``   after geometry (angle CSV)
  * ``02_sa_runs/early2``                        early-start ON/OFF stats
  * ``02_sa_runs/ablations/ablation_summary.json``
Outputs: ``05_figures/*.png``
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)

from four_side_1024.fanout1024.xyzrouter.g6 import plots  # noqa: E402

EXP = os.path.abspath(os.path.join(HERE, '..'))
FIG = os.path.join(EXP, '05_figures')
RUN = os.path.join(EXP, '02_sa_runs')
BASELINE = os.path.join(EXP, '00_baseline')


def _cross_csv(root):
    for base, _dirs, files in os.walk(root):
        for name in files:
            if name == 'g5_crossing_angles.csv':
                return os.path.join(base, name)
    return None


def main():
    os.makedirs(FIG, exist_ok=True)
    made = []
    warm = os.path.join(RUN, 'warm_B_v4')
    if os.path.isdir(warm):
        made.append(plots.fig_search_curves(
            warm, os.path.join(FIG, 'fig01_search_curves.png'),
            title='G6 warm start (G5 51-violation state): MultiArc SA'))
        made.append(plots.fig_temperature(
            warm, os.path.join(FIG, 'fig02_temperature_acceptance.png')))
        made.append(plots.fig_neighbourhood(
            warm, os.path.join(FIG, 'fig03_neighbourhood_contribution.png')))
    before_csv = _cross_csv(os.path.join(BASELINE, 'validation_g5_v5'))
    after_csv = _cross_csv(os.path.join(EXP, '03_best_feasible'))
    if before_csv and after_csv:
        made.append(plots.fig_angle_hist(
            before_csv, after_csv,
            os.path.join(FIG, 'fig04_angle_histogram_before_after.png')))
        made.append(plots.fig_per_layer(
            after_csv, os.path.join(FIG, 'fig05_per_layer_crossings.png')))
    early = os.path.join(RUN, 'early2')
    off = os.path.join(early, 'early_off', 'early_stats.json')
    on = os.path.join(early, 'early_on', 'early_stats.json')
    if os.path.exists(off) and os.path.exists(on):
        with open(off, encoding='utf-8') as handle:
            off_stats = json.load(handle)
        with open(on, encoding='utf-8') as handle:
            on_stats = json.load(handle)
        made.append(plots.fig_early_compare(
            off_stats, on_stats,
            os.path.join(FIG, 'fig06_early_start_angle_aware.png')))
    print('[figures] wrote %d figures' % len(made))
    for path in made:
        print('  ' + path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
