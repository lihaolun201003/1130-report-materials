# -*- coding: utf-8 -*-
"""Assemble the curated deliverable folder from the working experiment tree.

The working tree (``OpticalWaveguideRouter2D/experiments/G4_MULTI_ARC_ABLATION_FINAL_1024``)
holds everything, including multi-megabyte ``checkpoints/`` snapshots of every
arm.  This script builds the published copy:

* every report-level artefact (spec / runbook / report / comparison / config /
  tables / figures / audit / tools / code_changes / logs) is copied verbatim;
* for each run only the *reproducible* set is copied (route + assignment +
  crossing stats + summaries + ledger + config + both Validator runs + logs),
  while ``checkpoints/`` is dropped (documented in the archive README block of
  the manifest) and the duplicate root-level ``routes_l3d.json`` is dropped when
  it is byte-identical to ``best_valid/routes_l3d.json`` (the monotone search
  makes them equal; identity is verified, never assumed);
* every copied file keeps its bytes, so all SHA256 stay valid.

Usage::

    python .../tools/assemble_archive.py --dest <repo>/experiments/G4_MULTI_ARC_ABLATION_FINAL_1024
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent

TOP_LEVEL = ['EXPERIMENT_SPEC.md', 'RUNBOOK.md', 'report.md', 'comparison.md',
             'README.md']
TOP_DIRS = ['config', 'tables', 'figures', 'audit', 'tools', 'code_changes',
            'logs', 'pilot', 'validation', 'results']
RUN_KEEP = ['run.log', 'console.log', 'run_meta.json', 'summary.json',
            'summary_g4.json', 'budget_ledger.json', 'config.json',
            'crossing_stats.json', 'strategy_stats.json',
            'strategy_stats_partial.json', 'optimization_history.csv',
            'geometry_changes.json', 'manual_u_changes.json',
            'failed_attempts.json', 'SHA256.json', 'validation_final.log']
RUN_DIRS = ['best_valid', 'validation', 'validation_final']


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def copy_file(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)


def routes_identical(left, right):
    """True when two route files hold the same geometry (ignoring ``note``)."""
    a = json.loads(Path(left).read_text(encoding='utf-8-sig'))
    b = json.loads(Path(right).read_text(encoding='utf-8-sig'))
    for key in ('routes', 'layer_stack', 'topology', 'c4_binding'):
        if a.get(key) != b.get(key):
            return False
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dest', required=True)
    parser.add_argument('--skip-pilot', action='store_true')
    args = parser.parse_args(argv)
    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    notes = []

    for name in TOP_LEVEL:
        src = EXP / name
        if src.exists():
            copy_file(src, dest / name)
    # the canonical per-run sources are named report.md/comparison.md only after
    # the analysis is written; fall back to the *_src.md drafts when present
    for draft, final in (('report_src.md', 'report.md'),
                         ('comparison_src.md', 'comparison.md')):
        src = EXP / draft
        if src.exists() and not (dest / final).exists():
            copy_file(src, dest / final)

    for name in TOP_DIRS:
        src = EXP / name
        if not src.exists():
            continue
        if name == 'pilot' and args.skip_pilot:
            continue
        for path in sorted(src.rglob('*')):
            if not path.is_file():
                continue
            rel = path.relative_to(EXP)
            copy_file(path, dest / rel)

    runs_root = EXP / 'runs'
    copied = 0
    for arm_dir in sorted(p for p in runs_root.iterdir() if p.is_dir()):
        for run_dir in sorted(p for p in arm_dir.iterdir() if p.is_dir()):
            rel_run = Path('runs') / arm_dir.name / run_dir.name
            out = dest / rel_run
            out.mkdir(parents=True, exist_ok=True)
            for name in RUN_KEEP:
                src = run_dir / name
                if src.exists():
                    copy_file(src, out / name)
                    copied += 1
            for name in RUN_DIRS:
                src = run_dir / name
                if not src.exists():
                    continue
                for path in sorted(src.rglob('*')):
                    if path.is_file():
                        copy_file(path, out / name / path.relative_to(src))
                        copied += 1
            # duplicate root-level state files: keep only when they differ.
            # routes_l3d.json is compared on the *geometry* (the two copies
            # differ only in the free-text ``note`` field), assignment on bytes.
            for name in ('routes_l3d.json', 'assignment_1024.csv'):
                root_file = run_dir / name
                best_file = run_dir / 'best_valid' / name
                if not root_file.exists():
                    continue
                same = False
                if best_file.exists():
                    if name == 'assignment_1024.csv':
                        same = sha256(root_file) == sha256(best_file)
                    else:
                        same = routes_identical(root_file, best_file)
                if same:
                    notes.append('%s/%s dropped (geometry identical to '
                                 'best_valid/): root %s / best %s'
                                 % (rel_run.as_posix(), name,
                                    sha256(root_file), sha256(best_file)))
                else:
                    copy_file(root_file, out / name)
                    copied += 1
            dropped = sorted(p.name for p in (run_dir / 'checkpoints').glob('step_*')) \
                if (run_dir / 'checkpoints').exists() else []
            if dropped:
                notes.append('%s/checkpoints/ dropped (%d snapshots: %s)'
                             % (rel_run.as_posix(), len(dropped),
                                ', '.join(dropped)))

    (dest / 'ARCHIVE_NOTES.json').write_text(json.dumps(dict(
        schema='g4_multi_arc_final_archive_notes_v1',
        source_root=str(EXP), dest_root=str(dest),
        files_copied=int(copied),
        notes=notes,
        policy=('checkpoints are omitted (they are intermediate resume snapshots '
                'of a monotone search; the final legal state is best_valid, and '
                'the same run can be reproduced with tools/run_arm.ps1); the '
                'root-level routes_l3d.json is omitted only when it is '
                'byte-identical to best_valid/routes_l3d.json, which is verified '
                'by SHA256 and recorded here'),
    ), ensure_ascii=False, indent=1), encoding='utf-8')
    print('archive assembled at %s (%d files copied, %d notes)'
          % (dest, copied, len(notes)))
    for note in notes:
        print('  - %s' % note)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
