# -*- coding: utf-8 -*-
"""Reconstruct the provenance of the archived 1185 solution from the trusted repo.

Reads (read-only) from ``11.9-second-report-all-work`` at commit ``833a009b411c``:

* ``g4_xyz_joint_1024/06_arms/*/config.json`` / ``budget_ledger.json`` /
  ``summary.json`` -- the five isolated arms (C0, G4a, G4b, G4c_frozen,
  G4c_free, G4d)
* ``g4_xyz_joint_1024/07_chain/progressive_chain.json`` -- the chain table
* ``g4_xyz_joint_1024/07_chain/0*/SHA256.json`` -- the per-link route hashes
* ``g4_xyz_joint_1024/03_best_valid/{summary,SHA256}.json`` -- the published final

and writes ``chain_provenance.json``: which arm produced which state, which
state is the parent of which, and where the three different route hashes of the
"link 3" output come from.

Usage::

    python tools/extract_chain_provenance.py --repo <11.9 repo> --out <dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

COMMIT = '833a009b411c'
ROOT = 'g4_xyz_joint_1024'


def blob(repo, path):
    result = subprocess.run(['git', '-C', str(repo), 'cat-file', 'blob',
                             '%s:%s' % (COMMIT, path)], capture_output=True)
    return result.stdout


def read_json(repo, path):
    data = blob(repo, path)
    if not data:
        return None
    return json.loads(data.decode('utf-8-sig'))


def sha(data):
    return hashlib.sha256(data).hexdigest() if data else None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    repo = Path(args.repo)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    arms = {}
    for arm_dir in ('01_arm_C0', '02_arm_G4a', '03_arm_G4b', '04_arm_G4c_frozen',
                    '05_arm_G4c_free', '06_arm_G4d', '06b_G4d_warm_from_1189'):
        config = read_json(repo, '%s/06_arms/%s/config.json' % (ROOT, arm_dir))
        ledger = read_json(repo, '%s/06_arms/%s/budget_ledger.json' % (ROOT, arm_dir))
        summary = read_json(repo, '%s/06_arms/%s/summary.json' % (ROOT, arm_dir))
        if config is None:
            continue
        routes_blob = blob(repo, '%s/06_arms/%s/best_valid/routes_l3d.json'
                           % (ROOT, arm_dir))
        arms[arm_dir] = dict(
            config=dict(arm=config.get('arm'), seed=config.get('seed'),
                        budget=config.get('budget'),
                        start_dir=config.get('start_dir'),
                        start_routes_sha256=config.get('start_routes_sha256'),
                        start_crossings=config.get('start_crossings'),
                        started_at=config.get('started_at'),
                        cfg=config.get('cfg')),
            ledger=dict(route_3d_checks=(ledger or {}).get('route_3d_checks'),
                        d56_candidate_evals=(ledger or {}).get('d56_candidate_evals'),
                        accepted_transactions=(ledger or {}).get('accepted_transactions'),
                        gain=(ledger or {}).get('gain'),
                        wall_seconds=(ledger or {}).get('wall_seconds'),
                        written_at=(ledger or {}).get('written_at')),
            final_crossings=(summary or {}).get('crossings'),
            final_pairs=(summary or {}).get('crossing_pairs'),
            delta_vs_start=(summary or {}).get('delta_vs_start'),
            total_length_mm=(summary or {}).get('total_length_mm'),
            best_valid_routes_sha256=sha(routes_blob),
            best_valid_routes_bytes=len(routes_blob) if routes_blob else None)

    chain_payload = read_json(repo, '%s/07_chain/progressive_chain.json' % ROOT)
    links = {}
    for link in ('00_link_G3_start', '01_link_best_G4ab', '02_link_G4c',
                 '02b_link_best_G4c', '03_link_G4d'):
        data = read_json(repo, '%s/07_chain/%s/SHA256.json' % (ROOT, link))
        links[link] = data

    published = read_json(repo, '%s/03_best_valid/summary.json' % ROOT)
    published_sha = read_json(repo, '%s/03_best_valid/SHA256.json' % ROOT)
    published_routes = blob(repo, '%s/03_best_valid/routes_l3d.json' % ROOT)

    payload = dict(
        schema='g4_chain_provenance_v1',
        source=dict(repo=str(repo), commit=COMMIT),
        arms=arms,
        chain_links=links,
        chain_table=chain_payload,
        published=dict(
            summary=published,
            declared=published_sha,
            routes_l3d_json_sha256=sha(published_routes),
            routes_bytes=len(published_routes) if published_routes else None),
        notes=[
            'every arm in 06_arms starts from the same G3 start (start_crossings '
            '1322, routes sha256 711cf910...); they are independent A-class arms, '
            'not a chain',
            'the chain in 07_chain inherits real checkpoints: link1 = G4b '
            'best_valid, link2b = G4c_free best_valid, link3 = G4d run started '
            'from link2b',
            'the published 03_best_valid declares selected_from=chain_link3_G4d '
            'and its route file hash is b74ae511...',
            'the chain link directories kept only SHA256.json + validation/, so '
            'the link-3 route file itself is not in the archive; the link records '
            '22b0c5fe... and the chain table reports a0bf4c70..., which cannot be '
            'reconciled byte-wise from the archive alone',
            'the assignment hash recorded for link3 (2d7363ec...) equals the '
            'published assignment hash, and the crossing_stats hash '
            '(c526abda...) equals the published one, so link3 and the published '
            'file describe the same solution',
        ])
    (out / 'chain_provenance.json').write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')

    print('%-26s %6s %6s %8s %8s %8s  %s'
          % ('arm', 'start', 'final', 'gain', 'r3d', 'd56', 'wall_s'))
    for name, entry in arms.items():
        print('%-26s %6s %6s %8s %8s %8s  %s'
              % (name, entry['config']['start_crossings'],
                 entry['final_crossings'], entry['delta_vs_start'],
                 entry['ledger']['route_3d_checks'],
                 entry['ledger']['d56_candidate_evals'],
                 entry['ledger']['wall_seconds']))
    print()
    for name, entry in links.items():
        print('%-22s %s' % (name, json.dumps(entry, ensure_ascii=False)))
    print()
    print('published 1185 routes sha256 :', sha(published_routes))
    print('published summary           :', json.dumps(
        {k: published.get(k) for k in ('selected_from', 'start_crossings',
                                       'final_crossings', 'route_sha256' if False
                                       else 'routes_sha256', 'validation_pass')},
        ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
