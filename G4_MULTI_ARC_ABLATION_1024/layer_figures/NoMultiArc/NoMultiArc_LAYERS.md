# G4-NoMultiArc

Source (accepted layout): `experiments\G4_MULTI_ARC_ABLATION_1024\no_multi_arc\04_final`

- routes: **1024** (manual-U 368, groups 8)
- crossings (sum of exact-z events): **3484**
- routes SHA256: `7e3674c5add9f17463e355ec47b587871288111750c72fc2d3d675cc882f76ca`
- generated: 2026-11-16 19:58:04

| # | height | z (mm) | body routes | manual-U | groups | crossings | unique pairs | avg/route | max/route | mid-layer routes | covered blocks | idle blocks | congested blocks | max X/block |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | L2 | -0.35 | 40 | 33 | 1 | **133** | 114 | 6.65 | 24 | 0 | 86 | 14 | 21 | 14 |
| 2 | L3 | -0.30 | 68 | 62 | 1 | **131** | 103 | 3.85 | 35 | 0 | 91 | 9 | 17 | 19 |
| 3 | L4 | -0.25 | 66 | 61 | 2 | **96** | 84 | 2.91 | 30 | 0 | 83 | 17 | 16 | 14 |
| 4 | L5 | -0.20 | 92 | 86 | 2 | **126** | 89 | 2.74 | 39 | 0 | 96 | 4 | 22 | 14 |
| 5 | L6 | -0.15 | 38 | 0 | 0 | **271** | 186 | 14.26 | 34 | 6 | 99 | 1 | 48 | 14 |
| 6 | L7 | -0.10 | 36 | 0 | 0 | **276** | 193 | 15.33 | 31 | 8 | 100 | 0 | 53 | 15 |
| 7 | L20 | -0.05 | 38 | 0 | 0 | **196** | 124 | 10.32 | 21 | 10 | 97 | 3 | 39 | 13 |
| 8 | Z1_INTERFACE | +0.00 | 512 | 256 | 4 | **376** | 258 | 1.47 | 41 | 6 | 100 | 0 | 65 | 22 |
| 9 | L8 | +0.05 | 37 | 0 | 0 | **298** | 198 | 16.11 | 29 | 4 | 100 | 0 | 45 | 29 |
| 10 | L9 | +0.10 | 56 | 2 | 1 | **129** | 126 | 4.61 | 20 | 7 | 99 | 1 | 17 | 19 |
| 11 | L10 | +0.15 | 32 | 7 | 3 | **250** | 202 | 15.62 | 27 | 0 | 99 | 1 | 52 | 13 |
| 12 | L11 | +0.20 | 40 | 12 | 2 | **183** | 113 | 9.15 | 24 | 1 | 100 | 0 | 39 | 10 |
| 13 | L12 | +0.25 | 53 | 44 | 3 | **124** | 71 | 4.68 | 31 | 0 | 95 | 5 | 24 | 9 |
| 14 | L13 | +0.30 | 53 | 42 | 2 | **140** | 106 | 5.28 | 39 | 0 | 96 | 4 | 29 | 13 |
| 15 | L14 | +0.35 | 48 | 0 | 0 | **99** | 99 | 4.12 | 18 | 0 | 98 | 2 | 12 | 31 |
| 16 | L15 | +0.40 | 54 | 6 | 1 | **124** | 118 | 4.59 | 18 | 0 | 98 | 2 | 17 | 23 |
| 17 | L16 | +0.45 | 47 | 0 | 0 | **79** | 79 | 3.36 | 12 | 0 | 98 | 2 | 13 | 24 |
| 18 | Z2_INTERFACE | +0.50 | 512 | 112 | 4 | **134** | 128 | 0.52 | 19 | 0 | 100 | 0 | 20 | 31 |
| 19 | L17 | +0.55 | 54 | 6 | 1 | **117** | 117 | 4.33 | 17 | 0 | 97 | 3 | 13 | 23 |
| 20 | L18 | +0.60 | 48 | 0 | 0 | **98** | 98 | 4.08 | 18 | 0 | 98 | 2 | 14 | 25 |
| 21 | L19 | +0.65 | 51 | 7 | 1 | **104** | 101 | 4.08 | 18 | 0 | 98 | 2 | 14 | 23 |

Notes:
- Every number is computed from the accepted `routes_l3d.json` real primitives and the `crossing_stats.json` events with an **exact** physical-z match (rounded to 1e-6 mm).
- *body routes* = routes with at least one flat part on that physical height; *groups* = distinct original `manual_group` labels among those body routes.
- *covered blocks* = 10 x 10 grid of 15 mm blocks touched by flat routes or transition footprints; *idle blocks* = no route geometry at all on that height.
- *congested block* = block with >=2 real crossing events on that height.
