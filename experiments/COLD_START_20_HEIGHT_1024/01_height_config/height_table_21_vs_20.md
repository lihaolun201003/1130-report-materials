# Migration table: frozen 21H plane ids -> 20H plane ids

Scope: **height configuration only**. Every surviving plane id is kept as its identity label, every surviving height is raised by +0.025 mm, and plane id 19 (label L19, old z = +0.650 mm) is deleted.

> **Plane ids are identity labels, not a z ordering.** The 20H set is `2, 3, 4, 5, 6, 7, 20, 1001, 8, 9, 10, 11, 12, 13, 14, 15, 16, 1002, 17, 18`; id 20 (z=-0.025) sits between ids 7 and 8 in physical z, and id 19 does not exist any more. All physical ordering is taken from z (see `model20.PLANE_IDS` / `model20.plane_z`).

## Height mapping (every 21H plane id)

| 21H plane_id | 21H label | 21H z (mm) | 21H kind | 20H plane_id | 20H label | 20H z (mm) | delta (mm) | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | L2 | -0.350 | body | 2 | L2 | -0.325 | +0.025 | kept |
| 3 | L3 | -0.300 | body | 3 | L3 | -0.275 | +0.025 | kept |
| 4 | L4 | -0.250 | body | 4 | L4 | -0.225 | +0.025 | kept |
| 5 | L5 | -0.200 | body | 5 | L5 | -0.175 | +0.025 | kept |
| 6 | L6 | -0.150 | body | 6 | L6 | -0.125 | +0.025 | kept |
| 7 | L7 | -0.100 | body | 7 | L7 | -0.075 | +0.025 | kept |
| 20 | L20 | -0.050 | body | 20 | L20 | -0.025 | +0.025 | kept |
| 1001 | Z1_INTERFACE | +0.000 | interface_body | 1001 | Z1_INTERFACE | +0.025 | +0.025 | kept |
| 8 | L8 | +0.050 | body | 8 | L8 | +0.075 | +0.025 | kept |
| 9 | L9 | +0.100 | body | 9 | L9 | +0.125 | +0.025 | kept |
| 10 | L10 | +0.150 | body | 10 | L10 | +0.175 | +0.025 | kept |
| 11 | L11 | +0.200 | body | 11 | L11 | +0.225 | +0.025 | kept |
| 12 | L12 | +0.250 | body | 12 | L12 | +0.275 | +0.025 | kept |
| 13 | L13 | +0.300 | body | 13 | L13 | +0.325 | +0.025 | kept |
| 14 | L14 | +0.350 | body | 14 | L14 | +0.375 | +0.025 | kept |
| 15 | L15 | +0.400 | body | 15 | L15 | +0.425 | +0.025 | kept |
| 16 | L16 | +0.450 | body | 16 | L16 | +0.475 | +0.025 | kept |
| 1002 | Z2_INTERFACE | +0.500 | interface_body | 1002 | Z2_INTERFACE | +0.525 | +0.025 | kept |
| 17 | L17 | +0.550 | body | 17 | L17 | +0.575 | +0.025 | kept |
| 18 | L18 | +0.600 | body | 18 | L18 | +0.625 | +0.025 | kept |
| 19 | L19 | +0.650 | body | - | - | - | - | **DELETED (L19)** |

Summary: 20 of 21 21H heights kept with delta = +0.025 mm; 1 deleted (L19, old z=+0.650). The 20H table therefore has 20 routing heights = 18 body planes + 2 interface planes.

## Interface heights

| interface row | 21H z (mm) | 20H z (mm) | delta (mm) |
| --- | --- | --- | --- |
| z1 | +0.000 | +0.025 | +0.025 |
| z2 | +0.500 | +0.525 | +0.025 |

## Route-allocation migration (configuration change)

The 21H model mapped the eight Z2 "other adjacent" baseline old layers 1:1 onto eight 21H planes (`8->9, 9->14, 14->15, 15->16, 16->17, 17->18, 18->19, 19->1002`). With L19 deleted only seven Z2 non-manual planes remain, so the 20H model replaces the 1:1 map by an explicit whole-C4-orbit plan (100 C4 orbits = 400 routes):

| 20H plane_id | Z2 "other" C4 orbits | routes |
| --- | --- | --- |
| 9 | 14 | 56 |
| 14 | 14 | 56 |
| 15 | 14 | 56 |
| 16 | 14 | 56 |
| 17 | 16 | 64 |
| 18 | 16 | 64 |
| 1002 | 12 | 48 |

The Z1 "other opposite" plan is unchanged (5 planes, 64 orbits) and the eight manual U groups keep their plane ids and membership; only their z values follow the +0.025 mm shift.

## Why this is a configuration change only

* R15 = 15.0 mm, 50 um true-3D clearance, strict D56 same-layer 0.08 mm centre-line rule, 0.05 mm waveguide width, 0.03 mm edge gap, 150 x 150 x 1 mm glass: **bit-identical** to 21H.
* minimum neighbour pitch stays exactly 50.000 um for all 19 height gaps.
* headroom to the glass surfaces is 25 um on both sides (21H: L2/L19 on the surfaces, 0 um).
* the frozen 21H experiment stays reproducible; nothing under `outputs/` or `four_side_1024/` was modified (see `SHA256.json` and the cold-start adaptation log).

