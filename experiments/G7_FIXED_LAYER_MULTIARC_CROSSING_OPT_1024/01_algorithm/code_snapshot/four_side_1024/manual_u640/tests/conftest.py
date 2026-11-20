# -*- coding: utf-8 -*-
"""pytest configuration for the manual_u640 verification test suite.

The suite is meant to run from the project root with ``pytest -q``.  It must
not depend on the historical ``outputs/`` directories: the real input CSV is
read directly and every geometric sample is constructed in ``tmp_path``.
"""
from __future__ import annotations

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = TESTS_DIR.parent
PROJECT_ROOT = PACKAGE_DIR.parents[1]

for path in (str(PROJECT_ROOT), str(TESTS_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)
