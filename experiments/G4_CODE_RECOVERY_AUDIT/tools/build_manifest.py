# -*- coding: utf-8 -*-
"""Build ``MANIFEST.json`` + ``SHA256SUMS.csv`` for one deliverable folder.

``MANIFEST.json`` : schema, generation time, root, file_count, total_bytes and
                    one entry per file (sha256, bytes, relative path).
``SHA256SUMS.csv``: flat ``sha256,bytes,path`` table (sorted by path).

Usage::

    python .../tools/build_manifest.py --root <deliverable> [--exclude PATTERN ...]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from pathlib import Path


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--exclude', action='append', default=[],
                        help='substring of a relative path to skip')
    parser.add_argument('--skip-manifest', action='store_true', default=True,
                        help='skip the manifest files themselves (default on)')
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    files = []
    for path in sorted(root.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if any(token and token in rel for token in args.exclude):
            continue
        if args.skip_manifest and rel in ('MANIFEST.json', 'SHA256SUMS.csv'):
            continue
        files.append(dict(path=rel, bytes=path.stat().st_size,
                          sha256=sha256_file(path)))
    payload = dict(
        schema='g4_multi_arc_final_manifest_v1',
        generated_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        root=str(root),
        file_count=len(files),
        total_bytes=int(sum(entry['bytes'] for entry in files)),
        files=files)
    (root / 'MANIFEST.json').write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
    with (root / 'SHA256SUMS.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['sha256', 'bytes', 'path'])
        for entry in files:
            writer.writerow([entry['sha256'], entry['bytes'], entry['path']])
    print('manifest: %d files, %.1f MB' % (len(files),
                                           payload['total_bytes'] / 1e6))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
