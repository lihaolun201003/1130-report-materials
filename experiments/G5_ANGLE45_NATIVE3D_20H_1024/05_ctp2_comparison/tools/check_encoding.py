# -*- coding: utf-8 -*-
"""Diagnostic: are the two edited files still valid UTF-8 (and was the BOM kept)?

Run once after editing the work copy.  Prints, for each edited file, the byte
length, whether the frozen original carried a UTF-8 BOM, and every non-ASCII
character that survives in the copy.
"""
from __future__ import annotations

import pathlib

FROZEN = pathlib.Path(
    r"C:\Users\lihao\Desktop\Graduation Project\work\1130-report-materials"
    r"\experiments\CROSSTALK_PREDICTION_CTP2_20H_1283_1024\src\ctp2")
COPY = pathlib.Path(
    r"C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D"
    r"\experiments\G5_ANGLE45_NATIVE3D_20H_1024\05_ctp2_comparison\ctp2_g5\src\ctp2")

BOM = b"\xef\xbb\xbf"

for name in ("params.py", "geometry.py", "crossing.py", "__init__.py"):
    for tag, base in (("frozen", FROZEN), ("copy", COPY)):
        raw = (base / name).read_bytes()
        print("%-7s %-12s bytes=%6d bom=%-5s head=%r"
              % (tag, name, len(raw), raw[:3] == BOM, raw[:8]))
    print()

for name in ("params.py", "geometry.py"):
    raw = (COPY / name).read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        print("UTF8 DECODE FAIL", name, exc)
        continue
    odd = sorted({c for c in text if ord(c) > 126})
    print("%-12s valid utf-8, %d non-ascii distinct %r"
          % (name, len(odd), odd))
    for ch in odd:
        print("    %-6r U+%04X count=%d" % (ch, ord(ch), text.count(ch)))
