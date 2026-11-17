# -*- coding: utf-8 -*-
"""Compare the trusted G4 code snapshot with the current production package.

Inputs
------
trusted : ``g4_xyz_joint_1024/08_code/`` extracted from 11.9-second-report-all-work
          commit ``833a009b411c`` (contains ``g4/*.py`` + SHA256.json + SPEC_G4.md)
current : ``OpticalWaveguideRouter2D/four_side_1024/fanout1024/xyzrouter/g4/``
ablation: ``1130-report-materials/G4_MULTI_ARC_ABLATION_1024/code_changes/``
          (``*.orig`` / ``*.after`` snapshots of the two 1130 ablation rounds)

Outputs (under ``--out``)
-------------------------
``file_table.csv``     one row per file: status + sha256 of every variant
``diffs/<name>.diff``  unified diff trusted -> current for every changed file
``signatures.json``    class/def signatures added / removed / changed per file
``settings.json``      budget, stage schedule, operator weights, acceptance rules
``summary.json``       machine-readable roll-up

Read-only: nothing outside ``--out`` is written.
"""
from __future__ import annotations

import argparse
import ast
import csv
import difflib
import hashlib
import json
import re
from pathlib import Path

TRUSTED_SUBDIR = Path('g4_xyz_joint_1024') / '08_code'


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_text(path):
    return Path(path).read_text(encoding='utf-8-sig', errors='replace')


def diff_text(a_text, b_text, a_name, b_name):
    return ''.join(difflib.unified_diff(
        a_text.splitlines(keepends=True), b_text.splitlines(keepends=True),
        fromfile='a/' + a_name, tofile='b/' + b_name, n=4))


def signatures(text):
    """Class / function signatures, including nested defs."""
    found = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return found
    def walk(node, prefix=''):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                found.append(dict(kind='class', name=prefix + child.name,
                                  line=child.lineno))
                walk(child, prefix + child.name + '.')
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [a.arg for a in child.args.args]
                if child.args.vararg:
                    args.append('*' + child.args.vararg.arg)
                if child.args.kwarg:
                    args.append('**' + child.args.kwarg.arg)
                defaults = len(child.args.defaults)
                found.append(dict(kind='def', name=prefix + child.name,
                                  line=child.lineno, args=args,
                                  n_defaults=defaults))
                walk(child, prefix + child.name + '.')
    walk(tree)
    return found


def sig_key(sig):
    if sig['kind'] == 'class':
        return ('class', sig['name'])
    return ('def', sig['name'], tuple(sig['args']), sig['n_defaults'])


def extract_settings(text, filename):
    """Pull the budget / schedule / operator constants out of one module."""
    out = {}
    for name in ('DEFAULT_BUDGET', 'ARM_BUDGETS', 'STAGE_SIZES',
                 'STAGE_FRACTIONS', 'DEFAULT_CFG', 'SEED', 'START_CROSSINGS',
                 'PLAN_CFG', 'PROBE_CFG', 'TARGET_CFG', 'BLOCKER_CFG',
                 'SWEEP_CFG', 'SWEEP_QUALITY_CFG', 'MULTI_ARC_POLICY'):
        match = re.search(r'^%s\s*=\s*(\(|\[|\{|dict\()' % re.escape(name),
                          text, re.MULTILINE)
        if not match:
            continue
        start = match.start()
        depth = 0
        end = start
        for index in range(match.end() - 1, len(text)):
            char = text[index]
            if char in '([{':
                depth += 1
            elif char in ')]}':
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        out[name] = text[start:end].strip()
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trusted', required=True)
    parser.add_argument('--current', required=True)
    parser.add_argument('--ablation', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)

    trusted_root = Path(args.trusted)
    # allow pointing either at 08_code/ or at its parent
    if (trusted_root / 'g4').is_dir():
        trusted_dir = trusted_root / 'g4'
    else:
        trusted_dir = trusted_root / TRUSTED_SUBDIR / 'g4'
    trusted_code_dir = trusted_dir.parent
    current_dir = Path(args.current)
    ablation_dir = Path(args.ablation)
    out = Path(args.out)
    (out / 'diffs').mkdir(parents=True, exist_ok=True)

    # ---- 1. verify the snapshot against its own SHA256.json ----------------
    manifest = json.loads((trusted_code_dir / 'SHA256.json').read_text(
        encoding='utf-8-sig'))
    snapshot_check = []
    for entry in manifest.get('files') or ():
        path = trusted_code_dir / entry['snapshot'].replace('code/', '')
        actual = sha256(path) if path.exists() else None
        snapshot_check.append(dict(path=entry['snapshot'], expected=entry['sha256'],
                                   actual=actual,
                                   ok=bool(actual == entry['sha256'])))

    # ---- 2. file table ----------------------------------------------------
    trusted_files = sorted(p.name for p in trusted_dir.glob('*.py'))
    current_files = sorted(p.name for p in current_dir.glob('*.py'))
    rows = []
    diffs_written = []
    for name in sorted(set(trusted_files) | set(current_files)):
        t_path = trusted_dir / name
        c_path = current_dir / name
        orig = ablation_dir / (name + '.orig')
        after = ablation_dir / (name + '.after')
        t_sha = sha256(t_path) if t_path.exists() else None
        c_sha = sha256(c_path) if c_path.exists() else None
        status = ('missing_in_current' if not c_path.exists()
                  else 'added_in_current' if not t_path.exists()
                  else 'identical' if t_sha == c_sha else 'modified')
        row = dict(file=name, status=status, trusted_sha256=t_sha,
                   current_sha256=c_sha,
                   trusted_bytes=(t_path.stat().st_size if t_path.exists() else None),
                   current_bytes=(c_path.stat().st_size if c_path.exists() else None),
                   ablation_orig_sha256=(sha256(orig) if orig.exists() else None),
                   ablation_after_sha256=(sha256(after) if after.exists() else None),
                   trusted_equals_orig=bool(
                       t_path.exists() and orig.exists()
                       and sha256(t_path) == sha256(orig)),
                   current_equals_after=bool(
                       c_path.exists() and after.exists()
                       and sha256(c_path) == sha256(after)))
        rows.append(row)
        if status == 'modified':
            text = diff_text(read_text(t_path), read_text(c_path), name, name)
            (out / 'diffs' / (name + '.diff')).write_text(text, encoding='utf-8')
            added = sum(1 for line in text.splitlines()
                        if line.startswith('+') and not line.startswith('+++'))
            removed = sum(1 for line in text.splitlines()
                          if line.startswith('-') and not line.startswith('---'))
            row['lines_added'] = added
            row['lines_removed'] = removed
            diffs_written.append(dict(file=name, added=added, removed=removed))

    with (out / 'file_table.csv').open('w', encoding='utf-8', newline='') as h:
        fieldnames = list(rows[0].keys())
        for extra in ('lines_added', 'lines_removed'):
            if any(extra in row for row in rows) and extra not in fieldnames:
                fieldnames.append(extra)
        writer = csv.DictWriter(h, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)

    # ---- 3. signatures ----------------------------------------------------
    sig_report = {}
    for name in sorted(set(trusted_files) | set(current_files)):
        t_path = trusted_dir / name
        c_path = current_dir / name
        t_sigs = {sig_key(s): s for s in
                  signatures(read_text(t_path))} if t_path.exists() else {}
        c_sigs = {sig_key(s): s for s in
                  signatures(read_text(c_path))} if c_path.exists() else {}
        added = [c_sigs[k] for k in c_sigs if k not in t_sigs]
        removed = [t_sigs[k] for k in t_sigs if k not in c_sigs]
        if added or removed:
            sig_report[name] = dict(
                added=[dict(kind=s['kind'], name=s['name'], line=s['line'],
                            args=s.get('args')) for s in added],
                removed=[dict(kind=s['kind'], name=s['name'], line=s['line'],
                              args=s.get('args')) for s in removed],
                total_trusted=len(t_sigs), total_current=len(c_sigs))
    (out / 'signatures.json').write_text(
        json.dumps(sig_report, ensure_ascii=False, indent=1), encoding='utf-8')

    # ---- 4. settings ------------------------------------------------------
    settings = {}
    for name in sorted(set(trusted_files) | set(current_files)):
        t_settings = (extract_settings(read_text(trusted_dir / name), name)
                      if (trusted_dir / name).exists() else {})
        c_settings = (extract_settings(read_text(current_dir / name), name)
                      if (current_dir / name).exists() else {})
        if t_settings or c_settings:
            changed = {key: dict(trusted=t_settings.get(key),
                                 current=c_settings.get(key))
                       for key in set(t_settings) | set(c_settings)
                       if t_settings.get(key) != c_settings.get(key)}
            settings[name] = dict(all=dict(trusted=t_settings, current=c_settings),
                                  changed=changed)
    (out / 'settings.json').write_text(
        json.dumps(settings, ensure_ascii=False, indent=1), encoding='utf-8')

    # ---- 5. summary -------------------------------------------------------
    summary = dict(
        schema='g4_code_recovery_audit_v1',
        trusted_source=dict(
            repo='11.9-second-report-all-work', commit='833a009b411c',
            path='g4_xyz_joint_1024/08_code/g4',
            manifest_generated_at=manifest.get('generated_at'),
            manifest_all_match_source=manifest.get('all_match_source'),
            file_count=manifest.get('file_count'),
            total_bytes=manifest.get('total_bytes')),
        snapshot_self_check=dict(
            files=len(snapshot_check),
            ok=sum(1 for entry in snapshot_check if entry['ok']),
            failed=[entry for entry in snapshot_check if not entry['ok']]),
        counts=dict(
            trusted_files=len(trusted_files), current_files=len(current_files),
            identical=sum(1 for row in rows if row['status'] == 'identical'),
            modified=sum(1 for row in rows if row['status'] == 'modified'),
            missing_in_current=sum(1 for row in rows
                                   if row['status'] == 'missing_in_current'),
            added_in_current=sum(1 for row in rows
                                 if row['status'] == 'added_in_current')),
        modified_files=diffs_written,
        signature_changes=sig_report,
        settings_changes={name: sorted(value['changed'])
                          for name, value in settings.items() if value['changed']})
    (out / 'summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')

    print(json.dumps(summary, ensure_ascii=False, indent=1)[:6000])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
