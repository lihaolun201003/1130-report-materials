# XY+Z 联合三维路由器报告

## 1. 与 Phase-2 make-way 的根本区别

Phase-2（`native3d/joint_reroute.py` + `excursion2.py`）只在**已固定的 XY 路径**上寻找可插入的升降区间，XY 投影不变，遇到“另一个 XY 方向有空余空间”的情况无法利用。

新 `xyzrouter` 的候选是 **(目标物理高度 z, 接口引线长度, 全新 XY 走廊)** 三元组，由 `route_builder` 用精确 R15 几何重建整条线路：
- 目标高度：21 个物理高度中任选（可跨层迁移、可转换接口直连体）；
- XY 走廊：`layer2d` 的 R15 运动原语族库（直线/四分之一圆弧/短 S/L 型/Z 型/U 型/绕行/阶梯），与目标高度联立枚举；
- 端部：引线长度 × 端部 S 型过渡联立重算；
- 评估：先用 O(1) 几何交叉预排序（`PlanePrimGrid`），再对前 `d56_top` 个候选跑冻结 strict-D56 精确评估，最后用真 3D `l3d.world.World`（增量 ignore/replace）验收；
- 事务性：接受/回滚以整条线路为单位，未通过 3D 的候选永不被接受。

## 2. 搜索状态与动作

- 状态：`(目标高度层 z, 引线长度 lead_s/lead_t, XY 走廊几何)`；每条候选都带完整 `(x, y, z, heading)` 几何链。
- 动作：平面直线、R15 圆弧转向、R15 双圆弧 S 型换层、多段组合（直线→圆弧→直线→S 型…）；非法组合直接拒绝。
- 目标函数：字典序 = 真实同层交叉变化 → 路径长度；硬约束（R15/净空/玻璃/D56/端口身份）优先。

## 3. 真实场景验证（P0/P1/P2）

### P0

```json
{
 "schema": "xyz_router_validation_v1_p0",
 "generated_at": "2026-11-18T00:58:59",
 "baseline_dir": "experiments\\COLD_START_20_HEIGHT_1024\\07_g123\\run_xyz_joint_1024_20h\\baseline_authoritative",
 "baseline_routes_sha256": "1498023dd4fe71d711131c6632620aaec2e98941f3682b2060d6a7f0b304f265",
 "baseline_crossings": 3061,
 "selected_route": {
  "route_id": 739,
  "crossings_before": 49,
  "selection_rule": "highest-crossing non-manual route of the authoritative 2409 baseline",
  "ranking": [
   {
    "route_id": 739,
    "crossings": 49,
    "target_layer": 17,
    "target_z_mm": 0.575
   },
   {
    "route_id": 639,
    "crossings": 48,
    "target_layer": 17,
    "target_z_mm": 0.575
   },
   {
    "route_id": 743,
    "crossings": 42,
    "target_layer": 17,
    "target_z_mm": 0.575
   },
   {
    "route_id": 671,
    "crossings": 41,
    "target_layer": 17,
    "target_z_mm": 0.575
   },
   {
    "route_id": 635,
    "crossings": 41,
    "target_layer": 17,
    "target_z_mm": 0.575
   },
   {
    "route_id": 711,
    "crossings": 37,
    "target_layer": 17,
    "target_z_mm": 0.575
   },
   {
    "route_id": 667,
    "crossings": 36,
    "target_layer": 17,
    "target_z_mm": 0.575
   },
   {
    "route_id": 747,
    "crossings": 35,
    "target_layer": 17,
    "target_z_mm": 0.575
   },
   {
    "route_id": 699,
    "crossings": 35,
    "target_layer": 17,
    "target_z_mm": 0.575
   },
   {
    "route_id": 631,
    "crossings": 34,
    "target_layer": 17,
    "target_z_mm": 0.575
   }
  ],
  "old_geometry": {
   "route_id": 739,
   "target_layer": 17,
   "target_z_mm": 0.575,
   "n_transitions": 2,
   "n_mid_transitions": 0,
   "length_mm": 217.56387,
   "body_path_length_mm": 213.599287,
   "body_flat_count": 1,
   "body_z_mm": [
    0.575
   ],
   "body_primitive_count": 3,
   "transition_z_pairs": [
    [
     0.525,
     0.575
    ],
    [
     0.575,
     0.525
    ]
   ],
   "body_xy_signature_sha1": "5478c7544aaf753f"
  },
  "old_row": {
   "plane": "z2",
   "target_layer": 17,
   "target_z_mm": 0.575,
   "manual_group": "",
   "interface_z_mm": 0.525
  }
 },
 "candidate": {
  "source": "local_reroute.propose",
  "family": "ADJ_DOWN_LOOP",
  "lead_s_mm": 0.25,
  "lead_t_mm": 0.25,
  "option": {
   "kind": "migrate",
   "layer": 10,
   "z": 0.175,
   "load": 16,
   "priority": 0
  },
  "target_layer": 10,
  "target_z_mm": 0.175,
  "xy_body_crossings": 0,
  "lower_bound": -49,
  "early_stop": true,
  "per_plane": {
   "0.175": {
    "old": 0,
    "new": 0
   },
   "0.525": {
    "old": 0,
    "new": 0
   },
   "0.575": {
    "old": 49,
    "new": 0
   }
  },
  "engine_stats": {
   "targets": 5,
   "xy_generated": 14,
   "built": 2,
   "rejected_3d": 0,
   "evaluated": 2,
   "combos_pre": 5,
   "combos_eval": 1,
   "reasons": {}
  }
 },
 "requirements_check": {
  "xy_and_z_both_changed": true,
  "xy_changed_substantially": true,
  "z_changed": true,
  "not_only_z_lift_on_old_xy": true,
  "not_only_xy_at_same_height": true,
  "body_xy_signature_changed": true,
  "max_xy_displacement_ge_2mm": true,
  "target_layer_changed": true,
  "body_height_changed": true,
  "validation_pass": true
 },
 "geometry": {
  "old": {
   "route_id": 739,
   "target_layer": 17,
   "target_z_mm": 0.575,
   "n_transitions": 2,
   "n_mid_transitions": 0,
   "length_mm": 217.56387,
   "body_path_length_mm": 213.599287,
   "body_flat_count": 1,
   "body_z_mm": [
    0.575
   ],
   "body_primitive_count": 3,
   "transition_z_pairs": [
    [
     0.525,
     0.575
    ],
    [
     0.575,
     0.525
    ]
   ],
   "body_xy_signature_sha1": "5478c7544aaf753f"
  },
  "new": {
   "route_id": 739,
   "target_layer": 10,
   "target_z_mm": 0.175,
   "n_transitions": 2,
   "n_mid_transitions": 0,
   "length_mm": 264.72154,
   "body_path_length_mm": 255.047454,
   "body_flat_count": 1,
   "body_z_mm": [
    0.175
   ],
   "body_primitive_count": 5,
   "transition_z_pairs": [
    [
     0.525,
     0.175
    ],
    [
     0.175,
     0.525
    ]
   ],
   
```

### P1

```json
{
 "schema": "xyz_router_validation_v1_p1",
 "generated_at": "2026-11-18T01:00:13",
 "baseline_dir": "experiments\\COLD_START_20_HEIGHT_1024\\07_g123\\run_xyz_joint_1024_20h\\baseline_authoritative",
 "baseline_crossings": 3061,
 "selection": {
  "routes": [
   158,
   427,
   149
  ],
  "rationale": "three non-manual routes whose baseline crossing events directly involve each other (CrossingCache crossing_events); they share the crowded body height [-0.125, -0.125, -0.125]",
  "evidence": {
   "routes": [
    158,
    427,
    149
   ],
   "edge_events": {
    "ab": 2,
    "ac": 2,
    "bc": 2,
    "a_b": [
     158,
     427
    ],
    "a_c": [
     158,
     149
    ],
    "b_c": [
     427,
     149
    ]
   },
   "total_edge_events": 6,
   "crossings_sum": 89,
   "target_layers": [
    6,
    6,
    6
   ],
   "body_z_mm": [
    -0.125,
    -0.125,
    -0.125
   ],
   "same_body_height": true
  },
  "top_triples": [
   {
    "routes": [
     158,
     427,
     149
    ],
    "edge_events": {
     "ab": 2,
     "ac": 2,
     "bc": 2,
     "a_b": [
      158,
      427
     ],
     "a_c": [
      158,
      149
     ],
     "b_c": [
      427,
      149
     ]
    },
    "total_edge_events": 6,
    "crossings_sum": 89,
    "target_layers": [
     6,
     6,
     6
    ],
    "body_z_mm": [
     -0.125,
     -0.125,
     -0.125
    ],
    "same_body_height": true
   },
   {
    "routes": [
     158,
     427,
     217
    ],
    "edge_events": {
     "ab": 2,
     "ac": 2,
     "bc": 2,
     "a_b": [
      158,
      427
     ],
     "a_c": [
      158,
      217
     ],
     "b_c": [
      427,
      217
     ]
    },
    "total_edge_events": 6,
    "crossings_sum": 89,
    "target_layers": [
     6,
     6,
     6
    ],
    "body_z_mm": [
     -0.125,
     -0.125,
     -0.125
    ],
    "same_body_height": true
   },
   {
    "routes": [
     158,
     217,
     149
    ],
    "edge_events": {
     "ab": 2,
     "ac": 2,
     "bc": 2,
     "a_b": [
      158,
      217
     ],
     "a_c": [
      158,
      149
     ],
     "b_c": [
      217,
      149
     ]
    },
    "total_edge_events": 6,
    "crossings_sum": 88,
    "target_layers": [
     6,
     6,
     6
    ],
    "body_z_mm": [
     -0.125,
     -0.125,
     -0.125
    ],
    "same_body_height": true
   },
   {
    "routes": [
     8,
     104,
     5
    ],
    "edge_events": {
     "ab": 2,
     "ac": 2,
     "bc": 2,
     "a_b": [
      8,
      104
     ],
     "a_c": [
      8,
      5
     ],
     "b_c": [
      104,
      5
     ]
    },
    "total_edge_events": 6,
    "crossings_sum": 86,
    "target_layers": [
     7,
     7,
     7
    ],
    "body_z_mm": [
     -0.075,
     -0.075,
     -0.075
    ],
    "same_body_height": true
   },
   {
    "routes": [
     427,
     217,
     149
    ],
    "edge_events": {
     "ab": 2,
     "ac": 2,
     "bc": 2,
     "a_b": [
      427,
      217
     ],
     "a_c": [
      427,
      149
     ],
     "b_c": [
      217,
      149
     ]
    },
    "total_edge_events": 6,
    "crossings_sum": 85,
    "target_layers": [
     6,
     6,
     6
    ],
    "body_z_mm": [
     -0.125,
     -0.125,
     -0.125
    ],
    "same_body_height": true
   },
   {
    "routes": [
     427,
     149,
     214
    ],
    "edge_events": {
     "ab": 2,
     "ac": 2,
     "bc": 2,
     "a_b": [
      427,
      149
     ],
     "a_c": [
      427,
      214
     ],
     "b_c": [
      149,
      214
     ]
    },
    "total_edge_events": 6,
    "crossings_sum": 83,
    "target_layers": [
     6,
     6,
     6
    ],
    "body_z_mm": [
     -0.125,
     -0.125,
     -0.125
    ],
    "same_body_height": true
   },
   {
    "routes": [
     158,
     427,
     214
    ],
    "edge_events": {
     "ab": 2,
     "ac": 1,
     "bc": 2,
     "a_b": [
      158,
      427
     ],
     "a_c": [
      158,
      214
     ],
     "b_c": [
      427,
      214
     ]
    },
    "total_edge_events": 5,
    "crossings_sum": 87,
    "targ
```

### P2

```json
{
 "schema": "xyz_router_validation_v1_p2",
 "generated_at": "2026-11-18T01:02:09",
 "baseline_dir": "experiments\\COLD_START_20_HEIGHT_1024\\07_g123\\run_xyz_joint_1024_20h\\baseline_authoritative",
 "hotspot": {
  "hotspot_height_mm": 0.575,
  "hotspot_height_crossings": 979,
  "hotspot_height_crossing_pairs": 979,
  "hotspot_height_routes": 100,
  "selection_rule": "8 highest-crossing non-manual routes whose primary body height equals the most crowded physical height",
  "chosen": [
   739,
   639,
   743,
   671,
   635,
   711,
   667,
   747
  ],
  "ranking": [
   {
    "route_id": 739,
    "crossings": 49,
    "target_layer": 17,
    "target_z_mm": 0.575
   },
   {
    "route_id": 639,
    "crossings": 48,
    "target_layer": 17,
    "target_z_mm": 0.575
   },
   {
    "route_id": 743,
    "crossings": 42,
    "target_layer": 17,
    "target_z_mm": 0.575
   },
   {
    "route_id": 671,
    "crossings": 41,
    "target_layer": 17,
    "target_z_mm": 0.575
   },
   {
    "route_id": 635,
    "crossings": 41,
    "target_layer": 17,
    "target_z_mm": 0.575
   },
   {
    "route_id": 711,
    "crossings": 37,
    "target_layer": 17,
    "target_z_mm": 0.575
   },
   {
    "route_id": 667,
    "crossings": 36,
    "target_layer": 17,
    "target_z_mm": 0.575
   },
   {
    "route_id": 747,
    "crossings": 35,
    "target_layer": 17,
    "target_z_mm": 0.575
   },
   {
    "route_id": 699,
    "crossings": 35,
    "target_layer": 17,
    "target_z_mm": 0.575
   },
   {
    "route_id": 631,
    "crossings": 34,
    "target_layer": 17,
    "target_z_mm": 0.575
   },
   {
    "route_id": 535,
    "crossings": 34,
    "target_layer": 17,
    "target_z_mm": 0.575
   },
   {
    "route_id": 715,
    "crossings": 32,
    "target_layer": 17,
    "target_z_mm": 0.575
   },
   {
    "route_id": 703,
    "crossings": 32,
    "target_layer": 17,
    "target_z_mm": 0.575
   },
   {
    "route_id": 663,
    "crossings": 31,
    "target_layer": 17,
    "target_z_mm": 0.575
   },
   {
    "route_id": 531,
    "crossings": 31,
    "target_layer": 17,
    "target_z_mm": 0.575
   },
   {
    "route_id": 587,
    "crossings": 29,
    "target_layer": 17,
    "target_z_mm": 0.575
   }
  ],
  "excluded": [
   {
    "route_id": 699,
    "crossings_on_hot_height": 35,
    "whole_route_crossings": 35,
    "target_layer": 17,
    "target_z_mm": 0.575,
    "reason": "below the 8-route cut"
   },
   {
    "route_id": 631,
    "crossings_on_hot_height": 34,
    "whole_route_crossings": 34,
    "target_layer": 17,
    "target_z_mm": 0.575,
    "reason": "below the 8-route cut"
   },
   {
    "route_id": 535,
    "crossings_on_hot_height": 34,
    "whole_route_crossings": 34,
    "target_layer": 17,
    "target_z_mm": 0.575,
    "reason": "below the 8-route cut"
   },
   {
    "route_id": 703,
    "crossings_on_hot_height": 32,
    "whole_route_crossings": 32,
    "target_layer": 17,
    "target_z_mm": 0.575,
    "reason": "below the 8-route cut"
   },
   {
    "route_id": 715,
    "crossings_on_hot_height": 32,
    "whole_route_crossings": 32,
    "target_layer": 17,
    "target_z_mm": 0.575,
    "reason": "below the 8-route cut"
   },
   {
    "route_id": 663,
    "crossings_on_hot_height": 31,
    "whole_route_crossings": 31,
    "target_layer": 17,
    "target_z_mm": 0.575,
    "reason": "below the 8-route cut"
   },
   {
    "route_id": 531,
    "crossings_on_hot_height": 31,
    "whole_route_crossings": 31,
    "target_layer": 17,
    "target_z_mm": 0.575,
    "reason": "below the 8-route cut"
   },
   {
    "route_id": 587,
    "crossings_on_hot_height": 29,
    "whole_route_crossings": 29,
    "target_layer": 17,
    "target_z_mm": 0.575,
    "reason": "below the 8-route cut"
   }
  ],
  "heights_by_crossings": [
   {
    "z_mm": 0.575,
    "events": 979,
    "pairs": 979
   },
   {
    "z_mm": -0.125,
    "events": 408,
    "pairs": 294
   },
   {
    "z_mm": -0.075,
    "events": 394,
    "pairs": 291
   },
   {
    "z_mm": -0.025,
    "events":
```

## 4. 几何验证与失败原因

- 每个接受解都由 `native3d.validate_native3d` 独立重建 World 验证：1024/1024、R15、50 µm 净空、玻璃边界、D56、端口身份全部通过。
- G1 搜索候选统计：
```json
{
 "rounds": [
  {
   "label": "g1_r1",
   "seconds": 859.98,
   "accepted": 166,
   "candidates_tried": 656,
   "total_after": 1651,
   "gain": 1410,
   "stats": {
    "tried": 656,
    "targets": 2846,
    "xy_generated": 6294,
    "built": 1210,
    "rejected_3d": 40,
    "evaluated": 1210,
    "combos_pre": 2846,
    "combos_eval": 601,
    "accepted": 166,
    "gain": 1410,
    "no_gain": 490
   },
   "reasons": {
    "no_xy_candidate": 370,
    "transition_vs_flat": 18,
    "transition_vs_transition": 20,
    "flat_vs_transition": 2,
    "no_current_crossings": 70
   }
  },
  {
   "label": "g1_r2",
   "seconds": 573.67,
   "accepted": 53,
   "candidates_tried": 656,
   "total_after": 1485,
   "gain": 166,
   "stats": {
    "tried": 656,
    "targets": 2795,
    "xy_generated": 6060,
    "built": 1178,
    "rejected_3d": 31,
    "evaluated": 1178,
    "combos_pre": 2795,
    "combos_eval": 583,
    "accepted": 53,
    "gain": 166,
    "no_gain": 603
   },
   "reasons": {
    "no_xy_candidate": 361,
    "transition_vs_flat": 22,
    "flat_vs_transition": 3,
    "transition_vs_transition": 6,
    "no_current_crossings": 80
   }
  }
 ],
 "cfg": {
  "max_target_layers": 3,
  "max_lead_pairs": 2,
  "prescreen_candidates": 220,
  "max_candidates": 420,
  "d56_top": 24,
  "bodies_per_pair": 2,
  "max_eval": 2,
  "max_combos": 2,
  "early_stop_delta": 6,
  "min_delta": 1,
  "allow_direct": true,
  "allow_xy_only": true,
  "phase": 0.0
 }
}
```