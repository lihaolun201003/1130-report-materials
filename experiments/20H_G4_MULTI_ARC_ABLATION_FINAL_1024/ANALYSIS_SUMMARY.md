# 20H planar multi-arc ON/OFF ablation -- analysis

* profile: `20_height_raised` (20 routing heights, 18 body)
* common converted start: 4548 crossings (sha256 `a84acdbdbb311a67`)
* OFF feasibility: feasible
* primary verdict: **A**
* auxiliary verdict: A

## Effect A (conversion cost, separate from search)
1395 -> 4548 crossings (+3153), converted 213 routes, residual 0

## Effect B (the only search-ability measurement)
ON final crossings mean 2126.3 vs OFF mean 4064.0; paired mean gap -1937.7; verdict A

## Effect C (historical 21H reference, read-only)
{
 "available": true,
 "path": "experiments\\G4_MULTI_ARC_ABLATION_FINAL_1024\\tables\\summary_c1.json",
 "source": "experiments/G4_MULTI_ARC_ABLATION_FINAL_1024 (21H, read-only)",
 "common_start_crossings": 3967,
 "on_final": [
  2203.0,
  2197.0,
  2209.0
 ],
 "off_final": [
  3583.0,
  3613.0,
  3607.0
 ],
 "paired_diff": [
  -1380.0,
  -1416.0,
  -1398.0
 ],
 "paired_diff_mean": -1398.0,
 "verdict": "A",
 "historical_A": {
  "source": "experiments\\G4_MULTI_ARC_ABLATION_FINAL_1024\\tables\\stage0_audit.json",
  "g3_crossings": 1322,
  "converted_crossings": 3967,
  "targets": 197,
  "converted": 197,
  "residual": 0,
  "delta": 2645,
  "length_delta_mm": 8107.713019
 },
 "historical_C": {
  "source": "G4_MULTI_ARC_ABLATION_1024/report.md (read-only prose)",
  "on_final": 1202,
  "off_final": 3484,
  "difference": 2282,
  "note": "historical mixed package (different start + unequal budget); it is A + B + budget/start differences, never a 20H number"
 },
 "note": "historical 21H numbers; never mixed into the 20H effect B and never added to effect A"
}

## Separation rule
A, B and C are three distinct quantities: C is the historical 21H mixed-package difference (A + B + budget/start differences); A is conversion cost only; B is search-ability only. Never add A and B into one "value of multi-arc" number and never attribute the conversion cost to the search gain.

Tables: `tables/summary_c1.md`, `tables/abc.json`, `tables/stage0_audit.json`, `tables/runs.csv`; validation: `validation/summary.md`.
