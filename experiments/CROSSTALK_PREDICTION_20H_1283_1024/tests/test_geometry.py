"""Geometric invariants of the analytic curve engine (run directly)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from src.config import BEST_VALID, CONFIG
from src.dataio import load_dataset


def main() -> int:
    ds = load_dataset(BEST_VALID, verify_hash=False)
    worst_cont = 0.0
    worst_end = 0.0
    worst_len = 0.0
    for r in ds.routes:
        prev = None
        for g in r.segments:
            p0 = g.point(0.0)
            p1 = g.point(1.0)
            worst_end = max(worst_end, float(np.linalg.norm(p0 - np.array([*g.p0, g.z0]))))
            worst_end = max(worst_end, float(np.linalg.norm(p1 - np.array([*g.p1, g.z1]))))
            if prev is not None:
                worst_cont = max(worst_cont, float(np.linalg.norm(p0 - prev)))
            prev = p1
            # arc length by fine quadrature must equal the analytic length
            u = np.linspace(0.0, 1.0, 4001)
            P = g.point(u)
            L = float(np.sum(np.linalg.norm(np.diff(P, axis=0), axis=1)))
            worst_len = max(worst_len, abs(L - g.length) / max(g.length, 1e-12))
    print(f"max segment endpoint error        : {worst_end:.3e} mm")
    print(f"max segment continuity jump       : {worst_cont:.3e} mm")
    print(f"max relative arc-length error     : {worst_len:.3e}")
    ok = worst_end < 1e-9 and worst_cont < 1e-9 and worst_len < 1e-6
    print("GEOMETRY OK" if ok else "GEOMETRY FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
