"""Run the whole crosstalk-prediction pipeline end to end."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
STEPS = ["run_e1.py", "run_e2.py", "run_e3.py", "run_e4.py", "run_e5.py",
         "run_e6.py", "make_figures.py", "run_manifest.py", "run_report.py",
         "..\\tests\\test_pipeline.py"]


def main() -> int:
    t0 = time.time()
    for s in STEPS:
        path = SCRIPTS / s
        print(f"\n=== {s} ===", flush=True)
        rc = subprocess.call([sys.executable, str(path)], cwd=str(ROOT))
        if rc != 0:
            print(f"[FAIL] {s} exited with {rc}")
            return rc
    print(f"\nall steps finished in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
