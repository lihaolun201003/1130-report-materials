# probe/ — scratch validation probe for the G5 constraint audit

Everything here was produced from a **read-only copy** of the frozen 20-height solution
`experiments\COLD_START_20_HEIGHT_1024\10_best_valid\`.
No existing project file was modified; the source directory was only read
(`routes_l3d.json` still hashes to `35d7ebed00339bee21fe0ca47075c9b34008120522a47933a099efacf0b90753`).

## Layout

| path | what it is |
|---|---|
| `run_dir\` | the scratch run dir: the 5 frozen inputs (`routes_l3d.json`, `assignment_1024.csv`, `layer_planes.json`, `process_rules.json`, `physical_layer_stack.json`) **plus the canonical validator output** (`validation.json`, `validator_consistency_tests.json`) written by `four_side_1024.fanout1024.xyzrouter.validate_xyz` with `--manual-policy fully_optimizable` and the 20H baseline. Exit code 0, 0 violations, 1283 crossings / 1221 pairs. |
| `run_dir_listing_before.txt` | recursive listing (size + sha256) of the run dir before any validation |
| `run_dir_listing_after_native3d.txt` | listing after the validator ran — exactly 2 files added, nothing else touched |
| `validate_xyz_run.log` | full stdout of the canonical run (38.4 s wall, exit 0) |
| `validate_native3d_run.log` | full stdout of the equivalent minimal run (40.6 s wall, exit 0) |
| `validate_native3d_only\` | the two output files of that minimal run (pure `native3d_validation_v1` report, no `xyz_validator` / `policy_report` stamps) |
| `validate_native3d_default_baseline.log` | same validator with the **default** (21H `E5_joint_repair_final`) baseline and a separate `--out-dir`: exit 0, run dir untouched (`--baseline-dir` only changes the comparison baseline and the "vs baseline" numbers) |
| `validate21_attempt_negative\` | the rejected candidate: `python -m four_side_1024.fanout1024.coldstart20.run_validate` (= `reheight21.validate21`, the planar-assembly contract). Exit 1, 580 violations (`structure` 307 `z_span_mismatch`, `assignment` 268, `totals` 5) although the crossing check itself reports 1283 / 1221 / 0 — proof that `validate21` is the wrong contract for G4/G5 native-3D output. Also contains the extra files that runner writes (`crossing_stats.json`, `coldstart20_validation_summary.json`). |
| `angle_window_probe.py` | the strict-D56 admissibility/window probe used by `../CROSSING_RULE_AUDIT.md`: two straight centrelines at 5/10/30/45/90 deg evaluated by **both** independent implementations (`fslw.validate_fslw.evaluate_pair(policy='strict')` and `d56.index.D56Index(crossing_policy='strict')`) at `theta_min = 5 deg` and `45 deg`. Read-only; the 45 deg validator case is produced by assigning `validate_fslw.STRICT_SINE_MIN` in-process. |
| `angle_window_probe.json` | its JSON output (captured stdout) |

## Reproduce

```powershell
$PROJECT = "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D"
$env:PYTHONPATH = $PROJECT
Push-Location $PROJECT

# 1) the angle/window probe (no file changes)
& "$PROJECT\.venv\Scripts\python.exe" `
  "experiments\G5_ANGLE45_NATIVE3D_20H_1024\01_algorithm\constraint_audit\probe\angle_window_probe.py"

# 2) the validator (see ../VALIDATOR_RUNBOOK.md §7 for the full parameterised block)
$code = @"
import sys
from four_side_1024.fanout1024.coldstart20 import bootstrap as B
B.assert_20_height_profile('probe')
from four_side_1024.fanout1024.xyzrouter import validate_xyz as X
sys.exit(X.main(['--run-dir', r'$PWD\experiments\G5_ANGLE45_NATIVE3D_20H_1024\01_algorithm\constraint_audit\probe\run_dir',
                 '--out-dir', r'$PWD\experiments\G5_ANGLE45_NATIVE3D_20H_1024\01_algorithm\constraint_audit\probe\run_dir',
                 '--baseline-dir', r'$PWD\experiments\COLD_START_20_HEIGHT_1024\07_g123\run_xyz_joint_1024_20h\baseline_authoritative',
                 '--manual-policy', 'fully_optimizable']))
"@
$code | & "$PROJECT\.venv\Scripts\python.exe" -
Pop-Location
```

Note: the copies of `validation.json` in this directory contain the **absolute paths of the scratch
location** (`…\01_algorithm\_probe\frozen_20h_copy`) because the validator records `run_dir` /
`out_dir` inside the report; the numbers and the verdict are path-independent.
