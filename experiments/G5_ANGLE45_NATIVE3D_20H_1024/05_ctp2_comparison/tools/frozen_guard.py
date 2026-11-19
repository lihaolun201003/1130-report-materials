# -*- coding: utf-8 -*-
"""Frozen-tree guard: snapshot and verify hashes + mtimes of the read-only trees.

Two trees must never be written by the G5 CTP-2.0 work:

  A) the CTP-2.0 model tree
     work\\1130-report-materials\\experiments\\CROSSTALK_PREDICTION_CTP2_20H_1283_1024
  B) the frozen G4 routing solution
     OpticalWaveguideRouter2D\\experiments\\COLD_START_20_HEIGHT_1024\\10_best_valid

Usage
-----
    python tools/frozen_guard.py snapshot      # before any work
    python tools/frozen_guard.py verify         # after all work

``verify`` returns a non-zero exit code and prints every file whose size,
mtime or sha256 changed, plus any file added or removed, so a clean run is
positive evidence that the frozen trees were only ever read.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CMP = HERE.parent                       # ...\05_ctp2_comparison
PROJECT = CMP.parents[2]                # ...\OpticalWaveguideRouter2D
WORK = PROJECT.parent / "work" / "1130-report-materials"

TREES = {
    "ctp2_model": WORK / "experiments" / "CROSSTALK_PREDICTION_CTP2_20H_1283_1024",
    "g4_best_valid": PROJECT / "experiments" / "COLD_START_20_HEIGHT_1024" / "10_best_valid",
}
SNAPSHOT = HERE.parent / "frozen_guard" / "frozen_manifest_before.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def walk(root: Path) -> dict:
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for name in sorted(filenames):
            p = Path(dirpath) / name
            try:
                st = p.stat()
            except OSError:
                continue
            out[str(p.relative_to(root)).replace("\\", "/")] = {
                "bytes": st.st_size,
                "mtime_ns": st.st_mtime_ns,
                "sha256": sha256_file(p),
            }
    return out


def snapshot() -> int:
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"taken_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "trees": {}}
    for key, root in TREES.items():
        if not root.exists():
            print(f"[guard] MISSING tree {key}: {root}")
            return 2
        files = walk(root)
        payload["trees"][key] = {"root": str(root), "n_files": len(files),
                                 "total_bytes": sum(f["bytes"] for f in files.values()),
                                 "files": files}
        print(f"[guard] {key}: {len(files)} files, "
              f"{sum(f['bytes'] for f in files.values())/1e6:.1f} MB")
    SNAPSHOT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"[guard] snapshot -> {SNAPSHOT}")
    return 0


def verify() -> int:
    if not SNAPSHOT.exists():
        print(f"[guard] no snapshot at {SNAPSHOT}; run 'snapshot' first")
        return 2
    before = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    report = {"verified_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
              "snapshot_taken_at": before["taken_at"], "trees": {}}
    bad = 0
    for key, root in TREES.items():
        old = before["trees"][key]["files"]
        new = walk(root)
        changed, added, removed = [], [], []
        for rel, meta in new.items():
            if rel not in old:
                added.append(rel)
            elif (meta["sha256"] != old[rel]["sha256"]
                  or meta["bytes"] != old[rel]["bytes"]
                  or meta["mtime_ns"] != old[rel]["mtime_ns"]):
                changed.append({"path": rel,
                                "bytes_before": old[rel]["bytes"],
                                "bytes_after": meta["bytes"],
                                "mtime_ns_before": old[rel]["mtime_ns"],
                                "mtime_ns_after": meta["mtime_ns"],
                                "sha256_before": old[rel]["sha256"],
                                "sha256_after": meta["sha256"]})
        for rel in old:
            if rel not in new:
                removed.append(rel)
        n_hash_mismatch = sum(1 for c in changed if c["sha256_before"] != c["sha256_after"])
        n_mtime_only = len(changed) - n_hash_mismatch
        report["trees"][key] = {
            "root": str(root),
            "n_files_before": len(old),
            "n_files_after": len(new),
            "n_bytes_before": sum(f["bytes"] for f in old.values()),
            "n_bytes_after": sum(f["bytes"] for f in new.values()),
            "n_changed": len(changed),
            "n_changed_hash": n_hash_mismatch,
            "n_changed_mtime_only": n_mtime_only,
            "n_added": len(added),
            "n_removed": len(removed),
            "changed": changed,
            "added": added,
            "removed": removed,
            "untouched": (not changed and not added and not removed),
        }
        bad += len(changed) + len(added) + len(removed)
        print(f"[guard] {key}: before={len(old)} after={len(new)} "
              f"changed={len(changed)} (hash={n_hash_mismatch}) "
              f"added={len(added)} removed={len(removed)}")
        for c in changed[:20]:
            print(f"        CHANGED {c['path']}")
        for a in added[:20]:
            print(f"        ADDED   {a}")
        for r in removed[:20]:
            print(f"        REMOVED {r}")
    report["clean"] = bad == 0
    out = HERE.parent / "frozen_guard" / "frozen_verify_after.json"
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"[guard] {'CLEAN - frozen trees untouched' if bad == 0 else 'DIRTY'}"
          f"  -> {out}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "verify"
    raise SystemExit({"snapshot": snapshot, "verify": verify}[cmd]())
