# 20H multi-arc ON/OFF ablation -- Primary: equal candidate-evaluation budget (d56 = 24000)

* profile: `20_height_raised` (20 routing heights)
* common converted start crossings: **4548**
* seeds: 20261104, 20261116, 20261130
* budget: d56_candidate_evals >= 24000 (secondary route_3d_checks >= 9000; 5400 s wall clock is a pure safety net, designed not to trigger)

| metric | ON (mean) | OFF (mean) | paired diff (mean) | ON better seeds |
|---|---:|---:|---:|---:|
| final crossings | 2126.3 | 4064.0 | -1937.7 | 3/3 |
| crossing pairs | 1910.3 | 3141.3 | -1231.0 | 3/3 |
| routes with crossings | 788.3 | 926.0 | -137.7 | 3/3 |
| max route crossings | 28.0 | 47.7 | -19.7 | 3/3 |
| total length (mm) | 157178.1 | 164915.7 | -7737.6 | 3/3 |
| flat arcs | n/a | n/a | n/a | None/None |
| multi-arc regions | 179.7 | 0.0 | 179.7 | 0/3 |
| d56_candidate_evals | 24037.0 | 24162.3 | -125.3 | 3/3 |
| route_3d_checks | 3829.0 | 2907.0 | 922.0 | 0/3 |
| wall seconds | 1991.4 | 2134.8 | -143.4 | 3/3 |

## Pre-registered verdict
* verdict: **A**
* rule: A: 3/3 seeds ON<OFF and paired mean gap >= max(200, 5 % of common-start crossings) and ON total length increase <= 5 % and all hard gates pass; C: paired mean gap <= 0 or direction inconsistent; B: otherwise
* effect floor used: **227.0 crossings** (max(200, 5 % of common-start crossings))
* mean paired gap (ON-OFF): **-1937.7**
* seeds ON better: 3/3
* ON length change vs OFF: -4.69 %
* all hard gates pass: **True**
  * 3/3 seeds ON<OFF, paired mean gap -1937.7 >= floor 227.0, length change -4.69 %, all hard gates pass

> Exploratory statistics: 3 seeds, no significance test. Effect A (conversion, shown below) and effect B (this table) are separate quantities and must not be added.

