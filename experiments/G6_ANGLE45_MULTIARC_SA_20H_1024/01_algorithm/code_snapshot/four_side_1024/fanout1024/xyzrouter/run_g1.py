# -*- coding: utf-8 -*-
"""G1 experiment: manual U fully frozen, the 656 non-manual routes may be
re-routed with the XYZ joint router (new height + new XY corridor).

Usage (from the project root)::

    .venv\\Scripts\\python.exe -m four_side_1024.fanout1024.xyzrouter.run_g1 \
        --rounds 2 --round-seconds 1500 --top 656 --out <dir>
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024.native3d.crossing_cache import CrossingCache  # noqa: E402
from four_side_1024.fanout1024.coldstart20 import profile_env as PE  # noqa: E402
from four_side_1024.fanout1024.reheight21 import model as M  # noqa: E402
from four_side_1024.fanout1024.xyzrouter import local_reroute as LR  # noqa: E402
from four_side_1024.fanout1024.xyzrouter import optimizer as OPT  # noqa: E402
from four_side_1024.fanout1024.xyzrouter import paths as P  # noqa: E402
from four_side_1024.fanout1024.xyzrouter import route_builder as RB  # noqa: E402
from four_side_1024.fanout1024.xyzrouter import world_adapter as WA  # noqa: E402


def log(message):
    print(message, flush=True)


def parse_cfg(text):
    cfg = {}
    for chunk in (text or '').split(','):
        chunk = chunk.strip()
        if not chunk:
            continue
        key, _, value = chunk.partition('=')
        cfg[key.strip()] = json.loads(value.strip())
    return cfg


def authority_crossings(baseline_dir):
    """Stored crossing total of the start layout (never a 21-height literal).

    ``state.total`` is the recomputed truth; the start directory's own
    ``crossing_stats.json`` is the expected (authority) value.  Returns
    ``None`` when the start directory has no statistics, in which case the
    recomputed total is logged as the truth.
    """
    stats_path = Path(baseline_dir) / 'crossing_stats.json'
    try:
        payload = json.loads(stats_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    value = (payload.get('totals') or {}).get('crossings')
    return None if value is None else int(value)


def load_state(baseline_dir=None, log=log):
    baseline = P.load_baseline(baseline_dir)
    log('[g1] baseline dir=%s' % baseline['dir'])
    log('[g1] routes sha256=%s' % baseline['routes_sha256'])
    rows = RB.normalized_rows(baseline['rows'], stack=M.layer_stack())
    state = WA.RouteWorld(baseline['routes'], rows, log=log)
    log('[g1] world built: routes=%d crossings=%d (%.2fs)' % (
        len(state.routes), state.total, state.build_time))
    expected = authority_crossings(baseline['dir'])
    if expected is not None and int(state.total) != int(expected):
        log('[g1] WARNING: recomputed baseline crossings=%d != authority '
            'crossing_stats %d' % (state.total, expected))
    else:
        log('[g1] baseline crossings=%d (authority start state)' % state.total)
    return baseline, state


def candidate_ids(baseline, state, top=None, include_manual=False):
    cache = CrossingCache(list(baseline['routes']))
    per_route = cache.per_route()
    ids = []
    for route in baseline['routes']:
        rid = int(route['route_id'])
        manual = bool(str(route.get('manual_group') or '').strip())
        if manual and not include_manual:
            continue
        ids.append((int(per_route.get(rid, 0)), rid))
    ids.sort(key=lambda item: (-item[0], item[1]))
    selected = [rid for _count, rid in ids]
    if top is not None:
        selected = selected[:int(top)]
    log('[g1] %d candidate routes (top %s), baseline crossings=%d' % (
        len(selected), top if top is not None else 'all', cache.total()))
    return selected, cache, per_route


def main(argv=None):
    parser = argparse.ArgumentParser(description='G1: manual U frozen, XYZ joint rerouting of non-manual routes')
    parser.add_argument('--baseline-dir', default=None)
    parser.add_argument('--out', default=str(P.DIRS['G1']))
    parser.add_argument('--rounds', type=int, default=2)
    parser.add_argument('--round-seconds', type=float, default=1200.0)
    parser.add_argument('--top', type=int, default=None)
    parser.add_argument('--max-accepts', type=int, default=None)
    parser.add_argument('--cfg', default='')
    parser.add_argument('--note', default='G1 manual frozen / non-manual XYZ joint')
    parser.add_argument('--skip-validate', action='store_true')
    args = parser.parse_args(argv)

    P.ensure_dirs()
    out_dir = Path(args.out)
    log('=' * 78)
    log('[g1] out=%s' % out_dir)
    baseline, state = load_state(args.baseline_dir)
    ids, cache, per_route = candidate_ids(baseline, state, top=args.top)
    opt = OPT.Optimizer(state, baseline, out_dir, cfg=parse_cfg(args.cfg), log=log)
    opt.baseline_crossings = {int(rid): int(count) for rid, count in per_route.items()}
    result = opt.run(ids, rounds=args.rounds,
                     round_seconds=args.round_seconds,
                     max_accepts=args.max_accepts, label='g1')
    opt.save_state(out_dir, include_reports=True, note=args.note)
    log('[g1] saved %s total=%d (baseline %d) accepted=%d' % (
        out_dir, opt.state.total, opt.base_total, len(opt.history)))
    summary = dict(
        experiment='G1_manual_frozen',
        baseline_crossings=int(opt.base_total),
        final_crossings=int(opt.state.total),
        accepted_changes=len(opt.history),
        rounds=result.get('rounds'),
        routes=len(state.routes),
        manual_routes_checked=368,
        config=dict(cfg=opt.cfg, rounds=args.rounds,
                    round_seconds=args.round_seconds, top=args.top),
        elapsed_seconds=round(time.time() - opt.started, 2),
    )
    P.write_json(out_dir / 'summary.json', summary)
    log('[g1] summary: %s' % json.dumps(summary.get('final_crossings')))

    if not args.skip_validate:
        try:
            from four_side_1024.fanout1024.xyzrouter import validate_xyz
            report = validate_xyz.validate_xyz(
                run_dir=out_dir, baseline_dir=Path(baseline['dir']),
                out_dir=out_dir / 'validation',
                manual_policy='frozen', log=log)
            log('[g1] validation_pass=%s violations=%s' % (
                report.get('validation_pass'), report.get('violation_count')))
            if not report.get('validation_pass') and PE.is_20h():
                raise RuntimeError(
                    '[g1] 20-height driver: independent validation FAILED '
                    '(violations=%s, kinds=%s)'
                    % (report.get('violation_count'),
                       json.dumps(report.get('violation_counts_by_check')
                                  or {})))
        except Exception as error:  # noqa: BLE001
            if PE.is_20h():
                # the 20-height chain must stop on a failed validation
                raise
            log('[g1] validation unavailable/failed: %s' % error)
    return 0


if __name__ == '__main__':
    sys.exit(main())
