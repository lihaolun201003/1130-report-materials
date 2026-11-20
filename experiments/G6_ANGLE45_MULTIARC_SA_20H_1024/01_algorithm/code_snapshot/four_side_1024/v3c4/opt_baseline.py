"""Baseline artefacts (964/1024 layout): route JSON, checkpoints, plots, validation."""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from .profile import apply as apply_profile

ROUTING_ROOT_NAME = 'outputs/four_side_1024_v3_c4_routing'
OPT_ROOT_NAME = 'outputs/four_side_1024_v3_c4_optimization'


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _write(path, payload, indent=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=indent, ensure_ascii=False),
                    encoding='utf-8')
    return path


def build_baseline(routing_root, opt_root, log=print):
    """Copy the accepted 964 layout into the optimization tree and plot it."""
    apply_profile()
    from . import inputs as V3
    from . import plots_opt

    routing_root = Path(routing_root)
    opt_root = Path(opt_root)
    out_dir = opt_root / 'baseline_964'
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(out_dir / 'plots', ignore_errors=True)
    (out_dir / 'plots').mkdir(parents=True, exist_ok=True)

    combined_path = routing_root / 'c4_2d' / 'routes_1024.json'
    combined = _read(combined_path)
    records = combined['routes']
    routed = [r for r in records if r.get('status') == 'routed']
    payloads = {plane: plots_opt.load_plane_records(routing_root, plane)
                for plane in ('z1', 'z2')}
    groups_all, route_group = V3.build_groups()
    failed_entries = plots_opt.failed_group_entries(payloads, groups_all)
    routed_by_plane = {plane: sum(1 for r in routed if r.get('plane') == plane)
                       for plane in ('z1', 'z2')}
    routed_count = len(routed)
    log(f'[baseline] routed={routed_count} ({routed_by_plane}), '
        f'failed groups={len(failed_entries)}')

    # ---- route data + checkpoint -------------------------------------------------
    baseline_routes = dict(combined)
    baseline_routes['schema'] = 'four_side_1024_v3c4_optimization_baseline_v1'
    baseline_routes['note'] = ('accepted 964/1024 layout copied from '
                               'c4_2d/routes_1024.json (not re-routed)')
    _write(out_dir / 'routes_964.json', baseline_routes, indent=None)
    checkpoint = dict(
        schema='four_side_1024_v3c4_optimization_checkpoint_v1',
        stage='baseline_964', routed=routed_count, routed_by_plane=routed_by_plane,
        rejected_route_ids=[int(r['route_id']) for r in records
                            if r.get('status') != 'routed'],
        rejected_group_ids=[entry['group_id'] for entry in failed_entries],
        source_combined=str(combined_path),
        timestamp=time.strftime('%Y-%m-%dT%H:%M:%S'))
    _write(out_dir / 'checkpoint.json', checkpoint, indent=1)
    (out_dir / 'checkpoints').mkdir(exist_ok=True)
    for plane in ('z1', 'z2'):
        source = routing_root / 'c4_2d' / plane / 'checkpoint.json'
        if source.exists():
            shutil.copy2(source, out_dir / 'checkpoints' / f'c4_2d_{plane}_checkpoint.json')

    # ---- validation references ---------------------------------------------------
    validation = dict(
        schema='four_side_1024_v3c4_optimization_baseline_validation_v1',
        stage='baseline_964', routed=routed_count,
        c4_2d_combined=_read(routing_root / 'c4_2d' / 'validation_combined.json'),
        c4_l3d=_read(routing_root / 'c4_l3d' / 'validation.json'),
    )
    validation['passed'] = bool(
        validation['c4_2d_combined'].get('passed')
        and validation['c4_l3d'].get('passed'))
    _write(out_dir / 'validation.json', validation, indent=1)

    # ---- plots -------------------------------------------------------------------
    plots = out_dir / 'plots'
    plots_opt.plot_overview(records, None, routed_count,
                            'V3-C4 baseline 964（基线俯视总图）',
                            plots / '01_overview_baseline_964.png',
                            failed_groups=failed_entries)
    plots_opt.plot_by_row(records, routed_by_plane['z1'], routed_by_plane['z2'],
                          'V3-C4 baseline 964（分排：row1 对边 / row2 邻边）',
                          plots / '02_by_row_baseline_964.png')
    records_3d = plots_opt.load_3d_records(routing_root, payloads)
    plots_opt.plot_layers(records_3d, routed_count,
                          'V3-C4 baseline 964（L1–L5 分层）',
                          plots / '03_layers_baseline_964.png')
    plots_opt.plot_3d(records_3d, routed_count,
                      'V3-C4 baseline 964（三维）',
                      plots / '04_3d_baseline_964.png')
    plots_opt.plot_failed(records, failed_entries, routed_count,
                          'V3-C4 baseline 964（失败四元组位置）',
                          plots / '05_failed_groups_baseline_964.png')

    summary = dict(
        schema='four_side_1024_v3c4_optimization_baseline_summary_v1',
        stage='baseline_964', routed=routed_count, total=1024,
        failed=1024 - routed_count, routed_by_plane=routed_by_plane,
        routed_groups=sum(1 for g in groups_all
                          if all(any(int(r['route_id']) == rid
                                     and r.get('status') == 'routed'
                                     for r in records)
                                 for rid in g['route_ids'])),
        failed_groups=[entry['group_id'] for entry in failed_entries],
        validation_passed=validation['passed'],
        source_combined=str(combined_path),
        plots=sorted(str(p.relative_to(opt_root)) for p in plots.glob('*')),
        timestamp=time.strftime('%Y-%m-%dT%H:%M:%S'))
    _write(out_dir / 'summary.json', summary, indent=1)
    log(f'[baseline] written {out_dir} plots={len(summary["plots"])} '
        f'validation={"PASS" if validation["passed"] else "FAIL"}')
    return summary


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--routing-root', type=Path, default=None)
    parser.add_argument('--out', type=Path, default=None)
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parents[2]
    routing_root = args.routing_root or (repo / ROUTING_ROOT_NAME)
    opt_root = args.out or (repo / OPT_ROOT_NAME)
    summary = build_baseline(routing_root, opt_root)
    print(json.dumps({k: summary[k] for k in
                      ('stage', 'routed', 'failed', 'routed_groups',
                       'validation_passed')}, ensure_ascii=False))
    return summary


if __name__ == '__main__':
    main()
