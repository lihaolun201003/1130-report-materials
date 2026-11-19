"""Render every figure of the crosstalk-prediction report."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.figures import generate_all


def main() -> int:
    done = generate_all()
    print(f"[FIG] {len(done)} figures written to outputs/figures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
