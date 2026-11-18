# Independent validation summary (20H multi-arc ablation)

Validator: four_side_1024.fanout1024.xyzrouter.validate_xyz (fresh process, coldstart20.bootstrap installed first)
manual_policy: `fully_optimizable`; expected model heights: 20

| arm | tag | status | validator | engine val | violations | model heights | multi-arc | gates |
|---|---|---|---|---|---:|---:|---:|---|
| on | c1_on_20261104 | ok | True | True | 0 | 20 | 209 | True |
| on | c1_on_20261116 | ok | True | True | 0 | 20 | 183 | True |
| on | c1_on_20261130 | ok | True | True | 0 | 20 | 147 | True |
| off | c1_off_20261104 | ok | True | True | 0 | 20 | 0 | True |
| off | c1_off_20261116 | ok | True | True | 0 | 20 | 0 | True |
| off | c1_off_20261130 | ok | True | True | 0 | 20 | 0 | True |
| on | a1_on_20261104 | ok | True | True | 0 | 20 | 137 | True |
| on | a1_on_20261116 | ok | True | True | 0 | 20 | 133 | True |
| on | a1_on_20261130 | ok | True | True | 0 | 20 | 153 | True |
| off | a1_off_20261104 | ok | True | True | 0 | 20 | 0 | True |
| off | a1_off_20261116 | ok | True | True | 0 | 20 | 0 | True |
| off | a1_off_20261130 | ok | True | True | 0 | 20 | 0 | True |

