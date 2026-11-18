# Code changes used by the per-patent-structure experiment

Full snapshots of every source file that differs from the 20H baseline.

| file | change | why |
|---|---|---|
| `four_side_1024/fanout1024/patent_structures.py` | **new** geometry-only classifier of the seven patent configurations (S/Q/Z tokenisation, combination priority, no family-name lookup) | the ablation must disable a *real geometry*, not a candidate-family string |
| `four_side_1024/fanout1024/layer2d.py` | `G4_DISABLED_STRUCTURES` policy + post-build geometric gate in `_LayerRouter._iter_candidates`; per-structure candidate counters (`G4_STRUCTURE_STATS_PATH`) | the only changed variable of the 7 ablations; default (env unset) is byte-identical to the baseline (layer-route digest regression) |
| `four_side_1024/fanout1024/xyzrouter/local_reroute.py` | forwards `cfg['disabled_structures']` into the layer router | makes the switch reach the G4 `xy_candidates()` path |
| `four_side_1024/fanout1024/xyzrouter/g4/joint_world.py` | counts exact-3D/D56-valid candidates per structure when `G4_STRUCTURE_STATS_PATH` is set | “candidate generated” vs “geometrically legal” are different quantities and must be measured, not inferred |

The classifier is validated by `scratch/struct_census/test_patent_structures.py`
(35 passed) and reconciled with `layer2d.local_multi_arc_regions`
(215 regions / 213 routes, 0 mismatches).

No geometry constraint, validator, budget or acceptance rule was changed.
