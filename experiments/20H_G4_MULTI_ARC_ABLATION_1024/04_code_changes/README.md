# Code changes used by the 20H multi-arc ablation (round 1 + common start)

This directory freezes the exact source files that differ from the 20H cold-start
baseline. Each file is a full copy (not a diff), so the experiment can be
reproduced by dropping them back into the checkout.

| file | change | why |
|---|---|---|
| `four_side_1024/fanout1024/coldstart20/convert_multiarc20.py` | deterministic two-stage OFF conversion: frozen `PLAN_CFG`, then an expanded height/lead search (`ESCALATION_CFG`) only for routes with **no** frozen candidate | 20H has one body plane fewer; route 456 has no OFF body among the 3 nearest heights but does on plane 3 (`delta=-11`). The escalation only widens the legal search; grammar/R15/D56/3D/validator unchanged. |
| `four_side_1024/fanout1024/coldstart20/paths20.py` | `MULTIARC` honours `COLDSTART20_MULTIARC_ROOT` | lets the strict FINAL re-run live in its own experiment root without touching the historical stage-09 evidence |
| `four_side_1024/fanout1024/coldstart20/run_multiarc.py` | (a) arms read `common_start_off/` by default (not the ON G3 start); (b) engine start fingerprint uses the converted SHA/crossings; (c) `run_meta.start_crossings` reports the converted state; (d) effect floor from the common start; (e) `G4_STRUCTURE_STATS_PATH` counter instrumentation pass-through | the strict protocol requires **both** arms to start from the same converted state; the original port silently started both from G3 and then failed the SHA check |

No change touches the geometry grammar, R15, strict D56, the 0.05 mm true-3D
clearance, the 20-height table, the 1024 connections, the port contract, the
acceptance rule or the validator.

SHA256 of the originals as used by the two rounds is recorded in each
`run_meta.json` / `conversion_report.json` `source_snapshot` block.
