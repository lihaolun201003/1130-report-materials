# 20H multi-arc ON/OFF ablation -- Auxiliary: equal wall-clock budget (900 s)

* profile: `20_height_raised` (20 routing heights)
* common converted start crossings: **4548**
* seeds: 20261104, 20261116, 20261130
* budget: wall_seconds >= 900 (engine stage schedule by wall fractions)

| metric | ON (mean) | OFF (mean) | paired diff (mean) | ON better seeds |
|---|---:|---:|---:|---:|
| final crossings | 2643.3 | 4125.0 | -1481.7 | 3/3 |
| crossing pairs | 2277.7 | 3175.0 | -897.3 | 3/3 |
| routes with crossings | 853.0 | 926.0 | -73.0 | 3/3 |
| max route crossings | 33.3 | 49.0 | -15.7 | 3/3 |
| total length (mm) | 158681.2 | 164948.2 | -6267.1 | 3/3 |
| flat arcs | n/a | n/a | n/a | None/None |
| multi-arc regions | 141.0 | 0.0 | 141.0 | 0/3 |
| d56_candidate_evals | 12173.7 | 12572.7 | -399.0 | 3/3 |
| route_3d_checks | 2128.0 | 1453.7 | 674.3 | 0/3 |
| wall seconds | 966.5 | 966.5 | 0.0 | 2/3 |

## Pre-registered verdict
* verdict: **A**
* rule: A: 3/3 seeds ON<OFF and paired mean gap >= max(200, 5 % of common-start crossings) and ON total length increase <= 5 % and all hard gates pass; C: paired mean gap <= 0 or direction inconsistent; B: otherwise
* effect floor used: **227.0 crossings** (max(200, 5 % of common-start crossings))
* mean paired gap (ON-OFF): **-1481.7**
* seeds ON better: 3/3
* ON length change vs OFF: -3.80 %
* all hard gates pass: **True**
  * 3/3 seeds ON<OFF, paired mean gap -1481.7 >= floor 227.0, length change -3.80 %, all hard gates pass

> Exploratory statistics: 3 seeds, no significance test. Effect A (conversion, shown below) and effect B (this table) are separate quantities and must not be added.

