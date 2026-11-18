# -*- coding: utf-8 -*-
"""Select and freeze the final **best legal** 20-height solution.

Every stage writes its own legal layout.  This module scans all of them, ranks
them by (fully legal first, then fewest same-plane crossing events) and freezes
the winner into ``experiments/COLD_START_20_HEIGHT_1024/10_best_valid/`` together
with a SHA256 index and an acceptance record.

"Legal" means the layout carries a *passing independent validation* produced by
its own stage validator (planar stages: ``reheight21.validate21``; Native-3D /
G stages: ``native3d.validate_native3d``), with 1024/1024 routes routed and
0 violations.  A layout with fewer crossings but a missing or failing
validation can never win -- that is the explicit acceptance rule of the task.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from . import bootstrap as B          # installs the 20-height profile on import
from . import model20 as M
from . import paths20 as P20


def _sha256(path):
    path = Path(path)
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def _candidate_specs():
    """(key, label, layout dir) of every stage that can produce a legal layout."""
    g4 = Path(P20.G4_ROOT)
    multi = Path(P20.MULTIARC)
    specs = [
        ('03_initial', 'fanout-first + D56 multi-arc + 3D (cold assignment)',
         Path(P20.INIT_RUN)),
        ('04_E5', 'from-scratch annealing + joint repair (accepted E5)',
         Path(P20.E5_DIR)),
        ('05_native3d_phase1', 'Native 3D Phase 1 (A/B/C)',
         Path(P20.NATIVE3D_ABC_RUN)),
        ('06_native3d_phase2', 'Native 3D Phase 2 (D/E/F)',
         Path(P20.NATIVE3D_DEF_RUN) / 'best_valid'),
        ('07_G123', 'G1/G2a/G2b/G3 XYZ joint optimisation',
         Path(P20.XYZ_RUN) / 'best_valid'),
        ('08_G4_best', 'G4 arms best legal',
         g4 / '07_best_valid'),
        ('08_G4_chain_link2', 'G4 progressive chain link 2 (G4c rerun from '
         'best(G4a,G4b))', g4 / '08_progressive_chain' / '02_link_G4c'),
        ('08_G4_chain_link4', 'G4 progressive chain link 4 (G4d from the best '
         'G4c checkpoint)', g4 / '08_progressive_chain' / '03_link_G4d'),
        ('09_multiarc_on', 'multi-arc ablation ON arm (cold start)',
         Path(P20.INIT_RUN)),
        ('09_multiarc_off', 'multi-arc ablation OFF arm (cold start)',
         multi / 'cold_start_off'),
    ]
    # per-arm G4 layouts, if the archive created them
    for key in ('02_arm_G4a', '03_arm_G4b', '04_arm_G4c_frozen',
                '05_arm_G4c_free', '06_arm_G4d'):
        for sub in ('best_valid', ''):
            path = g4 / key / sub
            specs.append((f'08_G4_{key.split("_", 2)[-1]}' + ('/' + sub if sub else ''),
                          f'G4 arm {key}' + (f' {sub}' if sub else ''), path))
    return specs


def _validation_of(layout_dir):
    """Read the stage's own independent validation result."""
    for name in ('validation.json', 'validation/validation.json'):
        payload = _load(Path(layout_dir) / name)
        if not payload:
            continue
        routed = payload.get('routed')
        counts = payload.get('counts') or {}
        if routed is None:
            routed = counts.get('routed')
        return dict(
            available=True,
            path=str(Path(layout_dir) / name),
            validator=payload.get('validator'),
            validation_pass=payload.get('validation_pass'),
            geometry_pass=payload.get('geometry_pass'),
            contract_pass=payload.get('contract_pass'),
            violation_count=payload.get('violation_count'),
            routed=routed,
            failed=payload.get('failed',
                               counts.get('failed')),
        )
    return dict(available=False)


def scan():
    candidates = []
    for key, label, layout_dir in _candidate_specs():
        layout_dir = Path(layout_dir)
        routes_path = layout_dir / 'routes_l3d.json'
        stats_path = layout_dir / 'crossing_stats.json'
        if not routes_path.is_file() or not stats_path.is_file():
            candidates.append(dict(key=key, label=label, layout_dir=str(layout_dir),
                                   exists=False))
            continue
        stats = _load(stats_path) or {}
        totals = stats.get('totals') or {}
        validation = _validation_of(layout_dir)
        # route counts: crossing_stats of the Native-3D stages only carries
        # crossing geometry, so fall back to the independent validator report
        # and finally to the route payload itself
        routed = stats.get('routed')
        failed = stats.get('failed')
        if routed is None:
            routed = validation.get('routed')
        if failed is None:
            failed = validation.get('failed')
        if routed is None:
            routes_payload = _load(routes_path) or {}
            records = routes_payload.get('routes') or []
            failed = sum(1 for record in records
                         if str(record.get('status') or '') == 'failed')
            routed = len(records) - failed
        legal = bool(validation.get('validation_pass')) \
            and not int(failed or 0) and int(routed or 0) == 1024 \
            and not int(validation.get('violation_count') or 0)
        candidates.append(dict(
            key=key, label=label, layout_dir=str(layout_dir), exists=True,
            crossings=totals.get('crossings'),
            crossing_pairs=totals.get('crossing_pairs'),
            routed=routed, failed=failed,
            validation=validation,
            routes_sha256=_sha256(routes_path),
            legal=legal,
        ))
    return candidates


def rank(candidates):
    def key(item):
        if not item.get('exists'):
            return (3, 0, 10 ** 9)
        if item.get('legal'):
            return (0, 0, int(item.get('crossings') or 10 ** 9))
        return (1, 0, int(item.get('crossings') or 10 ** 9))
    return sorted(candidates, key=key)


FREEZE_FILES = ('routes_l3d.json', 'assignment_1024.csv', 'layer_planes.json',
                'process_rules.json', 'physical_layer_stack.json',
                'crossing_stats.json', 'validation.json',
                'transition_stats.json', 'final_stats.json')


def freeze(winner, out_dir, log=print):
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    source = Path(winner['layout_dir'])
    copied = []
    for name in FREEZE_FILES:
        src = source / name
        if not src.is_file() and name == 'validation.json':
            src = source / 'validation' / 'validation.json'
        if src.is_file():
            shutil.copy2(src, out_dir / name)
            copied.append(name)
    index = {}
    for path in sorted(out_dir.rglob('*')):
        if path.is_file() and path.name != 'SHA256.json':
            index[str(path.relative_to(out_dir))] = dict(
                bytes=path.stat().st_size, sha256=_sha256(path))
    payload = dict(
        schema='coldstart20_best_valid_v1',
        profile=M.PROFILE,
        experiment=M.EXPERIMENT_NAME,
        plane_count=len(M.PLANE_IDS),
        body_plane_count=len(M.BODY_PLANES),
        interfaces=dict(M.INTERFACE_Z),
        source_stage=winner['key'],
        source_label=winner['label'],
        source_layout_dir=str(source),
        routed=winner['routed'], failed=winner['failed'],
        crossings=winner['crossings'],
        crossing_pairs=winner['crossing_pairs'],
        routes_sha256=winner['routes_sha256'],
        validation=winner['validation'],
        copied=copied,
        acceptance_rule=('fully legal only: 1024/1024 routed, 0 failed, '
                         'passing independent validation, 0 violations; then '
                         'fewest same-plane crossing events'),
    )
    (out_dir / 'BEST_VALID.json').write_text(
        json.dumps(payload, indent=1, ensure_ascii=False, default=str) + '\n',
        encoding='utf-8')
    (out_dir / 'SHA256.json').write_text(
        json.dumps(index, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    log(f'[freeze] {winner["key"]} -> {out_dir} '
        f'(crossings={winner["crossings"]}, sha={str(winner["routes_sha256"])[:16]})')
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true',
                        help='freeze the winner into 10_best_valid')
    parser.add_argument('--out-dir', default=None)
    args = parser.parse_args(argv)
    B.install()
    P20.ensure_dirs()
    candidates = rank(scan())
    payload = dict(schema='coldstart20_best_valid_selection_v1',
                   profile=M.PROFILE, candidates=candidates,
                   winner=candidates[0] if candidates else None)
    out_dir = Path(args.out_dir or P20.BEST_VALID)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'selection_scan.json').write_text(
        json.dumps(payload, indent=1, ensure_ascii=False, default=str) + '\n',
        encoding='utf-8')
    for item in candidates:
        if not item.get('exists'):
            print(f'  - {item["key"]:<28} not present')
            continue
        print('  %s %-28s crossings=%s routed=%s failed=%s validation=%s'
              % ('*' if item.get('legal') else ' ', item['key'],
                 item.get('crossings'), item.get('routed'), item.get('failed'),
                 (item.get('validation') or {}).get('validation_pass')))
    winner = candidates[0] if candidates else None
    if args.apply and winner and winner.get('legal'):
        freeze(winner, out_dir)
    elif args.apply:
        print('[freeze] no fully legal candidate yet -- not freezing anything')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
