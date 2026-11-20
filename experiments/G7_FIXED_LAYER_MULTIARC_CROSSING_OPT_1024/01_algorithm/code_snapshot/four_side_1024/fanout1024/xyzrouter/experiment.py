# -*- coding: utf-8 -*-
"""Shared experiment plumbing for the G1/G2/G3 runs."""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

from ..reheight21 import model as M
from . import local_reroute as LR
from . import manual_reheight as MR
from . import optimizer as OPT
from . import paths as P
from . import route_builder as RB
from . import world_adapter as WA


def log_default(message):
    print(message, flush=True)


def load_state(run_dir=None, log=None):
    """Load a layouts directory (defaults to the authoritative 2409 baseline)."""
    log = log or log_default
    baseline = P.load_baseline(run_dir)
    rows = RB.normalized_rows(baseline['rows'], stack=M.layer_stack())
    state = WA.RouteWorld(baseline['routes'], rows, log=log)
    log('[state] %s routes=%d crossings=%d (%.2fs)' % (
        baseline['dir'], len(state.routes), state.total, state.build_time))
    return baseline, state


def make_optimizer(state, baseline, out_dir, cfg=None, log=None):
    return OPT.Optimizer(state, baseline, Path(out_dir), cfg=cfg, log=log)


def crossing_snapshot(state):
    per_route, cache = state.per_route_counts()
    return dict(total=int(cache.total()),
                pairs=int(cache.total_pairs()),
                per_route={int(k): int(v) for k, v in per_route.items()},
                cache=cache)


def run_nonmanual_optimizer(state, baseline, out_dir, rounds=1,
                            round_seconds=1200, cfg=None, top=None,
                            label='opt', log=None):
    log = log or log_default
    snap = crossing_snapshot(state)
    ids = MR.non_manual_route_ids(state)
    ids.sort(key=lambda rid: (-snap['per_route'].get(int(rid), 0), int(rid)))
    if top is not None:
        ids = ids[:int(top)]
    optimizer = make_optimizer(state, baseline, out_dir, cfg=cfg, log=log)
    optimizer.baseline_crossings = snap['per_route']
    result = optimizer.run(ids, rounds=rounds, round_seconds=round_seconds,
                           label=label)
    optimizer.save_state(out_dir, include_reports=True,
                         note='%s non-manual XYZ joint re-routing' % label)
    return optimizer, result


def run_all_route_optimizer(state, baseline, out_dir, rounds=1,
                            round_seconds=1200, cfg=None, label='g3',
                            log=None):
    log = log or log_default
    snap = crossing_snapshot(state)
    ids = sorted(state.routes, key=lambda rid: (-snap['per_route'].get(int(rid), 0),
                                                int(rid)))
    optimizer = make_optimizer(state, baseline, out_dir, cfg=cfg, log=log)
    optimizer.baseline_crossings = snap['per_route']
    result = optimizer.run(ids, rounds=rounds, round_seconds=round_seconds,
                           label=label)
    optimizer.save_state(out_dir, include_reports=True,
                         note='%s full XYZ joint re-routing (all 1024 routes)'
                              % label)
    return optimizer, result


def save_stage(state, baseline, out_dir, note='', log=None):
    """Persist the current state with the standard artifact set."""
    log = log or log_default
    snap = crossing_snapshot(state)
    optimizer = make_optimizer(state, baseline, out_dir, log=log)
    optimizer.baseline_crossings = snap['per_route']
    optimizer.save_state(Path(out_dir), include_reports=True, note=note)
    return snap


def validate_stage(run_dir, baseline_dir, out_dir, policy, log=None):
    log = log or log_default
    from . import validate_xyz
    report = validate_xyz.validate_xyz(run_dir=Path(run_dir),
                                       baseline_dir=Path(baseline_dir),
                                       out_dir=Path(out_dir),
                                       manual_policy=str(policy), log=log)
    summary = validate_xyz.summarize_report(report)
    log('[validate] policy=%s pass=%s violations=%s crossings=%s' % (
        policy, summary.get('validation_pass'),
        summary.get('violations'), summary.get('crossings')))
    return report, summary


def write_summary(out_dir, payload):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    P.write_json(out_dir / 'summary.json', payload)
    return out_dir / 'summary.json'
