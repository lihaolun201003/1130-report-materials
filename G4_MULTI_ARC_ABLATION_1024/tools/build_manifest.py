# -*- coding: utf-8 -*-
"""Build ``MANIFEST.json`` (+ SHA256 table) of the ablation deliverable set.

Every file below ``experiments/G4_MULTI_ARC_ABLATION_1024`` is hashed (bytes +
sha256) and grouped by top-level directory, with the key evidence files marked.
``MANIFEST.json`` itself and the scratch directory are excluded.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXP = Path(__file__).resolve().parents[1]
SKIP_PARTS = {'_scratch', '__pycache__', '.git'}
KEY_FILES = {
    'report.md': 'final report of the ablation',
    'MANIFEST.json': 'this manifest',
    'RUNBOOK.md': 'exact commands / seeds / parameters',
    'baseline_audit/flat_multi_arc_G4_best_1185.json':
        'planar multi-arc audit of the archived G4 original',
    'baseline_audit/flat_multi_arc_G3_start_1322.json':
        'planar multi-arc audit of the common start point',
    'no_multi_arc/01_convert/conversion_report.json':
        'stage-0 conversion of the 197 inherited multi-arc routes',
    'validation/baseline_G4_best_1185/validation.json':
        'independent Validator on the archived G4 original',
    'comparison/per_layer_crossings_compare.csv':
        'per-height crossing comparison table',
    'comparison/overview_3d_both_arms.png':
        'complete 3-D overview of both arms',
}


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    files = []
    for path in sorted(EXP.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(EXP)
        if any(part in SKIP_PARTS for part in relative.parts):
            continue
        if relative.name in ('MANIFEST.json', 'SHA256SUMS.csv'):
            continue
        files.append(dict(path=str(relative).replace('\\', '/'),
                          bytes=path.stat().st_size,
                          sha256=sha256(path)))
    groups = {}
    for item in files:
        top = item['path'].split('/')[0] if '/' in item['path'] else '(root)'
        groups.setdefault(top, []).append(item)
    key = {name: dict(path=name, role=role)
           for name, role in KEY_FILES.items() if (EXP / name).exists()}
    payload = dict(
        schema='g4_multi_arc_ablation_manifest_v1',
        experiment='G4_MULTI_ARC_ABLATION_1024',
        generated_at=datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
        root=str(EXP.name),
        file_count=len(files),
        total_bytes=sum(item['bytes'] for item in files),
        groups={name: len(items) for name, items in groups.items()},
        key_files=key,
        files=files,
    )
    (EXP / 'MANIFEST.json').write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
    lines = ['path,bytes,sha256']
    for item in files:
        lines.append('%s,%d,%s' % (item['path'], item['bytes'], item['sha256']))
    (EXP / 'SHA256SUMS.csv').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(dict(file_count=payload['file_count'],
                          total_bytes=payload['total_bytes'],
                          groups=payload['groups']), ensure_ascii=False,
                     indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

