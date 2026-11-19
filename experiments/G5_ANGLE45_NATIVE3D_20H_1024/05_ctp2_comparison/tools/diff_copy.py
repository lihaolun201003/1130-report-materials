# -*- coding: utf-8 -*-
"""Report the exact file-level diff between the frozen CTP-2.0 tree and the G5 copy.

    python tools/diff_copy.py

Prints, for ``src/``, ``scripts/`` and ``config/``, every file whose bytes differ
from the frozen original, and writes ``frozen_guard/copy_diff.json``.  A file
that only differs because it is *new* (present in the copy, absent from the
original) is listed separately.  Used to back the claim in PIPELINE_G5.md that
the work copy differs from the frozen tree in exactly N files.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CMP = HERE.parent
PROJECT = CMP.parents[2]
WORK = PROJECT.parent / "work" / "1130-report-materials"

ORIG = WORK / "experiments" / "CROSSTALK_PREDICTION_CTP2_20H_1283_1024"
COPY = CMP / "ctp2_g5"
SCOPES = ("src", "scripts", "config", "tests", "docs")
SKIP_DIRS = {"__pycache__"}


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def files(root: Path) -> dict:
    out = {}
    for scope in SCOPES:
        base = root / scope
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_dir() or any(part in SKIP_DIRS for part in p.parts):
                continue
            out[str(p.relative_to(root)).replace("\\", "/")] = p
    return out


def main() -> int:
    a, b = files(ORIG), files(COPY)
    changed, added, removed = [], [], []
    for rel, pa in a.items():
        if rel not in b:
            removed.append(rel)
            continue
        sa, sb = sha(pa), sha(b[rel])
        if sa != sb:
            changed.append({"path": rel, "sha256_frozen": sa, "sha256_copy": sb})
    for rel in b:
        if rel not in a:
            added.append(rel)
    report = {
        "frozen_root": str(ORIG),
        "copy_root": str(COPY),
        "scopes": list(SCOPES),
        "n_files_frozen": len(a),
        "n_files_copy": len(b),
        "n_changed": len(changed),
        "n_added": len(added),
        "n_removed": len(removed),
        "changed": changed,
        "added": added,
        "removed": removed,
        "identical": not (changed or added or removed),
    }
    out = CMP / "frozen_guard" / "copy_diff.json"
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")

    # unified diff of every changed text file, for the record
    import difflib
    chunks = []
    for c in changed:
        rel = c["path"]
        try:
            ta = (ORIG / rel).read_text(encoding="utf-8").splitlines(keepends=True)
            tb = (COPY / rel).read_text(encoding="utf-8").splitlines(keepends=True)
        except UnicodeDecodeError:
            continue
        chunks.extend(difflib.unified_diff(
            ta, tb, fromfile=f"frozen/{rel}", tofile=f"g5_copy/{rel}", n=3))
    (CMP / "frozen_guard" / "params_geometry.diff").write_text(
        "".join(chunks), encoding="utf-8")

    print(f"[diff] frozen={len(a)} copy={len(b)} changed={len(changed)} "
          f"added={len(added)} removed={len(removed)}")
    for c in changed:
        print(f"  CHANGED {c['path']}")
    for c in added:
        print(f"  ADDED   {c}")
    for c in removed:
        print(f"  REMOVED {c}")
    print(f"[diff] -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
