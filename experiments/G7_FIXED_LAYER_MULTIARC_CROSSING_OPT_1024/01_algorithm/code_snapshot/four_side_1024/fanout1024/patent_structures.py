# -*- coding: utf-8 -*-
"""专利图 6(a)-(d) / 图 7(a)-(c) 七种「组合圆弧」构型的纯几何分类器.

本模块从 frozen D56 原语链（R=15 mm 的 quarter arc、short-S 双弧、直线）的
**真实几何**出发，而不是从候选家族名字出发，判定一条平面 body（一个 flat part
的 ``line``/``arc`` 原语序列）使用了专利中的哪一种组合圆弧构型:

===========  ==========================================================
type         专利构型（说明书 [0031]-[0034]，附图 6/7）
===========  ==========================================================
``6a``       图6(a) 单组短 S: 对侧连接，用一组组合圆弧完成横移
``6b``       图6(b) 双组短 S: 对侧连接，横向偏移分配给两组组合圆弧
``6c``       图6(c) 短 S 在 Z 型块之前
``6d``       图6(d) 短 S 在 Z 型块之后
``7a``       图7(a) 横移后转向: 相邻侧连接，先短 S 横移再 90° 转向
``7b``       图7(b) 转向后横移: 相邻侧连接，先 90° 转向再短 S 横移
``7c``       图7(c) 两次横移后转向: 相邻侧连接，转向前布置两组短 S
===========  ==========================================================

几何基础（与 ``layer2d``/``fslw.geom`` 的 frozen D56 原语集完全一致）:

* **Q**（quarter arc）: 单段 ``|sweep| = pi/2``、``radius = R`` 的圆弧;
* **S**（短 S / 组合圆弧）: 两段半径相同、转向相反、公共切点直接相切、单段转角
  ``theta = acos(1 - |d|/(2R))`` 小于 ``pi/2`` 的圆弧对。两端切线方向一致，
  横向偏移 ``|d| = 2R(1-cos theta)``，前进行程 ``F = 2R sin theta``。
  ``|sweep| = pi/2`` 的两段直接相切反向 90° 圆弧 = ``|d| = 2R`` 的**边界形态**
  （``boundary=True``，专利图 2(b) 的直接相邻反向圆弧），同样计为 S; 它与
  「中间直线为 0 的退化 Z」几何重合，见判定规则第 4 条的歧义说明;
* **Z**（Z 型横移块）: 两段反向 quarter arc 之间夹一段直线: ``Q(s) L(w) Q(-s)``。
  其横向位移为 ``s * (2R + w)``，前进行程 ``2R``。``w = 0`` 时两 quarter arc 直接
  相切，称为**退化 Z**（零直线 Z 块），此时它与「theta = pi/2 的极限 S」几何上重合，
  但按专利定义既不是短 S（缺 theta<pi/2）也不是标准 Z（缺中间直线），本模块把它
  当作 Z 块处理并在证据里标注 ``degenerate=True``，**不计入** 七种构型;
* **同圆拆分**（``same_circle_split``）: 同一个圆被存成多段 arc 记录
  （``U_QUARTER_PAIR`` 的 ``middle = 0`` 情形）。两段同圆心，不构成任何几何自由度，
  既不是 S 也不是 Z，**不计入** 七种构型（与 ``layer2d.local_multi_arc_regions``
  的 frozen 口径一致）;
* **独立转角**: 单段 quarter arc（``ADJ_L`` / ``ADJ_Z_TURN`` 等），或两段同向
  quarter arc 之间夹直线（U 型回转）——单独出现时不构成组合圆弧构型。

判定规则（可复现，全部只依赖原语几何，不依赖候选 family 名称）
------------------------------------------------------------------
1. **切向连续弧串**: 相邻两个 arc 满足 ``|p1 - p0| <= 1e-6`` 且
   ``角差(末切线, 初切线) <= 1e-6 rad`` 时视为同一极大切向连续弧串（与
   ``layer2d.local_multi_arc_regions`` 完全相同的口径）。
2. **token 化**: 每个极大弧串按「从左到右贪心」分解成 token:
   优先配对成 ``S``（两弧反向、等 |sweep|、严格亚 90°、圆心不同）; 否则单段
   quarter 记为 ``Q``; 其余记为 ``arc_other``（不参与构型判定）。全串同圆心的弧串
   合并为一个 ``same_circle`` token（储存拆分，不算多弧自由度）。直线为 ``LINE``。
   * 3 弧串 ``S+Q`` / ``Q+S``、4 弧串 ``S+S``、5 弧串 ``S+S+Q`` 等「连续退化串」
     都由该贪心规则自然还原，无需额外特判;
   * 当两个 S 块直接相邻（中间无直线）形成 4 弧串时，``(+θ,-θ,+θ,-θ)`` 型符号
     串的唯一完整配对就是 ``(1,2)(3,4)``，贪心分解与生成 move 顺序一致。
3. **净转向**: 平面 body 的净转向 = 所有 arc 的 sweep 之和（直线不改变方向）。
   取 ``k = round(sum / (pi/2))``，残差须 ``<= 1e-6 rad``。``k = 0`` 为对侧连接
   （图 6 族），``|k| = 1`` 为相邻侧连接（图 7 族），``|k| = 2`` 为同侧连接
   （图 5 族，短 S 只作为 U 型回转的前置补偿，不属于图 6/7）。
4. **Z 块配对**: 从左到右扫描 ``Q`` token，若其后只隔 ``LINE`` token 的下一个非
   直线 token 仍是 ``Q`` 且 turn 符号相反，则二者组成一个 Z 块。Z 块要求两
   quarter arc 之间**存在长度 > POS_TOL(1e-6 mm) 的直线**; 直线长度为零（或只剩
   可忽略的舍入残线 <= POS_TOL）的两段反向 quarter arc 视为**边界组合圆弧**
   （``|d| = 2R``、``theta = pi/2``、``boundary=True`` 的 short-S，专利图 2(b)
   的「直接相邻反向圆弧」），先在第 2 步合成为 S token，不再组成 Z 块。
   这条规则决定了一个真实歧义: 两段反向 90° 圆弧直接相切时，「theta = pi/2 的
   极限短 S」与「中间直线为 0 的退化 Z」是同一条曲线；本分类器按上述规则统一
   计为 **S（组合圆弧）**，与 ``layer2d.local_multi_arc_regions`` 把它算作
   局部多弧区域的口径一致，保证逐构型消融开关能真正拦住这类候选。
   边界注记: 生成器合法 Z 块的最短直线为 1e-6 mm，与 routes_l3d.json 的六位
   小数坐标量化同量级; 若该直线量化后 <= POS_TOL，也按 boundary S 处理。全量
   普查中恰好命中 1 条线路（route 449，位于 6b/6c 判定边界，见
   ``scratch/struct_census/census.md`` 的歧义小节）；这是冻结的判定规则,
   不因单条边界线路调整。
5. **构型判定**（要求 body 中除 ``LINE``/``same_circle`` 外的 token 全部被该构型
   占用，否则记为 unclassified，不强行套类）::

      k == 0（对侧连接，图 6）:
          1 个 S 且 0 个 Z                      -> 6a
          2 个 S 且 0 个 Z                      -> 6b
          1 个 S 且 1 个 Z，S 在 Z 两个 Q 之前   -> 6c
          1 个 S 且 1 个 Z，S 在 Z 两个 Q 之后   -> 6d
          0 个 S（纯 Z / 直线 / 退化 Z）         -> 无构型实例
          其余（如 3 个 S、S 夹在 Z 中间、未配对的 Q） -> unclassified

      |k| == 1（相邻侧连接，图 7）:
          恰有 1 个未配对的转向 Q（不在 Z 块内），且 0 个 Z 块:
              S 在转向 Q 之前 x1                  -> 7a
              S 在转向 Q 之后 x1                  -> 7b
              S 在转向 Q 之前 x2                  -> 7c
          其余（S 与 Z 并存、转向 Q 数量不为 1 等） -> unclassified

      |k| == 2（同侧连接）: 若含 S，则属于专利图 5 的「先横移再 U 型回转」，
          不是图 6/7 的任何一种，记为 ``short_s_blocks()`` 中的
          ``relation='same'`` 用法，不产生 STRUCTURE_TYPES 实例。
6. **多实例**: 生成语法下每个 flat body 至多承载一个图 6/7 构型实例; 一条 route
   可以有多个 flat part（多物理高度身体段），因此一条线路可含多个实例
   （``classify_route`` 逐 part 输出并附 ``part_index``）。同一 flat body 内若出现
   多个独立构型（例如 4 个 S 块 = 两个 6b），当前版本返回 unclassified 并在
   ``diagnostics`` 中说明，不做重叠切分——宁可拒判也不放宽几何规则。
7. **夹直线**: 构型判定对块间直线长度完全不敏感（可以为 0，即两结构直接相切），
   直线长度只写入 ``evidence``（例如 ``s_to_z_gap_mm``、``z_straight_mm``）。
   因此「S 与 Q 直接相切」的 3 弧连续串仍是 7a/7b/6c/6d，只是被标注为
   ``attached=True``。

几何自检（evidence）
--------------------
对每个实例按 token 顺序做一次「位移合成」: 以首弧初切线为基准方向，S 贡献
``shift * rot90(h)``，Z 贡献 ``sign(Q1)*(2R+w) * rot90(h)``，Q 贡献
``R*h + s*R*rot90(h)`` 并旋转 90°。合成位移与实际首末弧端点位移之差记为
``displacement_closure_mm``（候选生成器产出的 body 通常 < 1e-9；JSON 六位小数
坐标 < 1e-4）。该自检不参与分类，只作为「真实几何」的可审计证据。

坐标稳健性: 位置容差 1e-6 mm、角度容差 1e-6 rad，与 ``layer2d`` 的 frozen
口径一致；把 ``routes_l3d.json`` 的六位小数坐标直接喂进来即可，无需重算弧参数。

公共 API
--------
``STRUCTURE_TYPES``                      七种构型 type 元组
``classify_primitives(primitives)``      一个 flat body 的原语链 -> 实例列表
``classify_route(route)``                整条 route（含 parts）-> 实例列表
``route_types(route_or_primitives)``     便捷集合
``route_structure_instances(parts_or_primitives)``
                                         任务书接口: 接受 primitives 列表 /
                                         flat part 列表 / route dict / route 列表
``analyze_primitives(primitives)``       完整分析（token、Z 块、弧串归属、诊断）
``tokenize_primitives(primitives)``      token 化结果（调试/报告用）
``short_s_blocks(primitives)``           所有短 S 块（含不属于图 6/7 的用法）
``arc_runs(primitives)``                 极大切向连续弧串（含单弧）
``multi_arc_regions(primitives)``        与 ``layer2d.local_multi_arc_regions``
                                         同口径的局部多弧区域（对账用）

本模块只依赖标准库 ``math``，无副作用、无全局状态，可在候选生成热路径上调用
（单条 body 的典型耗时为几十微秒量级）。
"""
from __future__ import annotations

import math

__all__ = [
    'STRUCTURE_TYPES', 'PATENT_FIGURE', 'STRUCTURE_CAPTION', 'TOLERANCES',
    'classify_primitives', 'classify_route', 'route_types',
    'route_structure_instances', 'analyze_primitives', 'tokenize_primitives',
    'short_s_blocks', 'arc_runs', 'multi_arc_regions',
]

#: 七种专利构型 type(顺序与专利附图 6(a)-(d)、7(a)-(c) 一致)
STRUCTURE_TYPES = ('6a', '6b', '6c', '6d', '7a', '7b', '7c')

#: type -> 专利附图编号
PATENT_FIGURE = {
    '6a': '图6(a)', '6b': '图6(b)', '6c': '图6(c)', '6d': '图6(d)',
    '7a': '图7(a)', '7b': '图7(b)', '7c': '图7(c)',
}

#: type -> 专利原文构型名称
STRUCTURE_CAPTION = {
    '6a': '单组短S',
    '6b': '双组短S',
    '6c': '短S在Z型块之前',
    '6d': '短S在Z型块之后',
    '7a': '横移后转向',
    '7b': '转向后横移',
    '7c': '两次横移后转向',
}

#: 判定容差（与 layer2d 的 frozen 口径一致; 只读，不在运行时修改）
TOLERANCES = {
    'pos_mm': 1e-6,          # 切点重合 / 圆心相同的判定
    'angle_rad': 1e-6,       # 切向连续 / S 两弧等转角
    'quarter_rad': 1e-6,     # |sweep| 是否等于 pi/2
    'net_turn_rad': 1e-6,    # 净转向必须是 pi/2 的整数倍
    'radius_mm': 1e-9,       # 同一弧串内半径一致
    'closure_mm': 1e-4,      # evidence 位移自检的参考阈值（不参与判定）
}

_POS_TOL = TOLERANCES['pos_mm']
_ANG_TOL = TOLERANCES['angle_rad']
_QUARTER_TOL = TOLERANCES['quarter_rad']
_NET_TOL = TOLERANCES['net_turn_rad']
_RADIUS_TOL = TOLERANCES['radius_mm']

_HALF_PI = math.pi / 2.0

#: token kind 常量
_LINE = 'line'
_QUARTER = 'quarter'
_SHORT_S = 'short_s'
_SAME_CIRCLE = 'same_circle'
_ARC_OTHER = 'arc_other'
_NEUTRAL_TOKENS = (_LINE, _SAME_CIRCLE)


# ---------------------------------------------------------------------------
# 极简几何辅助（纯 stdlib，定义与 layer2d/fslw.geom 的 frozen 版本一致）
# ---------------------------------------------------------------------------
def _xy(point):
    return (float(point[0]), float(point[1]))


def _dist(a, b):
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def _dot(a, b):
    return float(a[0]) * float(b[0]) + float(a[1]) * float(b[1])


def _rot90(vector):
    """左转 90°: (x, y) -> (-y, x)。"""
    return (-float(vector[1]), float(vector[0]))


def _unit(vector):
    norm = math.hypot(float(vector[0]), float(vector[1]))
    if norm <= 1e-15 or not math.isfinite(norm):
        return (0.0, 0.0)
    return (float(vector[0]) / norm, float(vector[1]) / norm)


def _rotate(vector, angle):
    c, s = math.cos(angle), math.sin(angle)
    return (float(vector[0]) * c - float(vector[1]) * s,
            float(vector[0]) * s + float(vector[1]) * c)


def _arc_start_tangent(arc):
    """圆弧起点切线方向（与 layer2d._start_tangent 相同定义）。"""
    angle = float(arc['start_angle'])
    sign = 1.0 if float(arc['sweep']) >= 0.0 else -1.0
    return (-sign * math.sin(angle), sign * math.cos(angle))


def _arc_end_tangent(arc):
    angle = float(arc['start_angle']) + float(arc['sweep'])
    sign = 1.0 if float(arc['sweep']) >= 0.0 else -1.0
    return (-sign * math.sin(angle), sign * math.cos(angle))


def _line_tangent(line):
    dx = float(line['p1'][0]) - float(line['p0'][0])
    dy = float(line['p1'][1]) - float(line['p0'][1])
    return _unit((dx, dy))


def _prim_start_tangent(prim):
    if prim.get('kind') == 'arc':
        return _arc_start_tangent(prim)
    return _line_tangent(prim)


def _prim_end_tangent(prim):
    if prim.get('kind') == 'arc':
        return _arc_end_tangent(prim)
    return _line_tangent(prim)


def _tangent_gap(a, b):
    """两个单位切向之间的夹角（弧度; 与 layer2d._tangent_gap 相同定义）。"""
    na = math.hypot(a[0], a[1])
    nb = math.hypot(b[0], b[1])
    if na <= 1e-12 or nb <= 1e-12:
        return math.pi
    value = (a[0] * b[0] + a[1] * b[1]) / (na * nb)
    return math.acos(max(-1.0, min(1.0, value)))


def _prim_length(prim):
    if prim.get('kind') == 'arc':
        return abs(float(prim['sweep'])) * float(prim['radius'])
    return _dist(prim['p0'], prim['p1'])


def _sweep_sign(arc):
    return 1 if float(arc['sweep']) >= 0.0 else -1


def _is_quarter(arc):
    return abs(abs(float(arc['sweep'])) - _HALF_PI) <= _QUARTER_TOL


def _is_sub_quarter(arc):
    """严格小于 90°（短 S 的单弧转角; 排除 |sweep| = pi/2 的退化工况）。"""
    sweep = abs(float(arc['sweep']))
    return _QUARTER_TOL < sweep < _HALF_PI - _QUARTER_TOL


def _is_short_s_pair(left, right):
    """两段切向连续圆弧是否构成短 S 的一对（几何判据，不依赖 move 名）。"""
    if not _is_sub_quarter(left) or not _is_sub_quarter(right):
        return False
    if _sweep_sign(left) == _sweep_sign(right):
        return False
    if abs(abs(float(left['sweep'])) - abs(float(right['sweep']))) > _ANG_TOL:
        return False
    if abs(float(left['radius']) - float(right['radius'])) > _RADIUS_TOL:
        return False
    # 圆心不同（相同则属同圆拆分，不是短 S）
    if _dist(_xy(left['center']), _xy(right['center'])) <= _POS_TOL:
        return False
    # 公共切点直接相切（调用方已按弧串分组, 这里再核对一次）
    return (_dist(_xy(left['p1']), _xy(right['p0'])) <= _POS_TOL
            and _tangent_gap(_arc_end_tangent(left),
                             _arc_start_tangent(right)) <= _ANG_TOL)


def _is_boundary_short_s_pair(left, right):
    """两段**直接相切的反向 quarter arc**（中间无直线）。

    这是组合圆弧在 ``|d| = 2R``（``theta = pi/2``）处的极限形态（专利图 2(b)
    的「直接相邻反向圆弧」）: 两段 90° 反向圆弧在公共切点直接相连，横向位移
    ``2R``、前进行程 ``2R``。它与「直线长度 = 0 的退化 Z 块」是**同一条曲线**,
    本分类器按固定规则把它计为 **short-S（boundary=True）**，只有
    ``straight_mm > POS_TOL`` 的两反向 quarter 之间才允许组成 Z 块。

    判据: 两弧 ``|sweep| = pi/2``（容差内）、转向相反、半径相同、圆心不同、
    公共切点直接相切。调用方保证二者属于同一极大切向连续弧串。
    """
    if not _is_quarter(left) or not _is_quarter(right):
        return False
    if _sweep_sign(left) == _sweep_sign(right):
        return False
    if abs(float(left['radius']) - float(right['radius'])) > _RADIUS_TOL:
        return False
    if _dist(_xy(left['center']), _xy(right['center'])) <= _POS_TOL:
        return False
    return (_dist(_xy(left['p1']), _xy(right['p0'])) <= _POS_TOL
            and _tangent_gap(_arc_end_tangent(left),
                             _arc_start_tangent(right)) <= _ANG_TOL)


# ---------------------------------------------------------------------------
# 1) 极大切向连续弧串（与 layer2d.local_multi_arc_regions 同口径）
# ---------------------------------------------------------------------------
def arc_runs(primitives):
    """返回原语链中所有极大切向连续弧串（含单弧串）。

    每项::

        dict(first=<prim index>, prim_indices=[...], n_arcs=<int>,
             length_mm=<arc length sum>, start_xy=[x, y], end_xy=[x, y],
             same_centre=<bool>, centres=[[x, y], ...], sweeps=[rad, ...],
             radius_mm=<float>)

    「切向连续」判定与 ``layer2d.local_multi_arc_regions`` 完全一致
    （位置 1e-6 mm、角度 1e-6 rad）。
    """
    prims = list(primitives or ())
    out = []
    total = len(prims)
    index = 0
    while index < total:
        prim = prims[index]
        if prim.get('kind') != 'arc':
            index += 1
            continue
        run = [index]
        cursor = index
        while cursor + 1 < total and prims[cursor + 1].get('kind') == 'arc':
            left, right = prims[cursor], prims[cursor + 1]
            if (_dist(left['p1'], right['p0']) > _POS_TOL
                    or _tangent_gap(_arc_end_tangent(left),
                                    _arc_start_tangent(right)) > _ANG_TOL):
                break
            run.append(cursor + 1)
            cursor += 1
        index = cursor + 1
        arcs = [prims[i] for i in run]
        centres = [_xy(a['center']) for a in arcs]
        same_centre = all(_dist(c, centres[0]) <= _POS_TOL for c in centres)
        radii = [float(a['radius']) for a in arcs]
        out.append(dict(
            first=int(run[0]),
            prim_indices=[int(i) for i in run],
            n_arcs=len(run),
            length_mm=sum(_prim_length(a) for a in arcs),
            start_xy=[float(arcs[0]['p0'][0]), float(arcs[0]['p0'][1])],
            end_xy=[float(arcs[-1]['p1'][0]), float(arcs[-1]['p1'][1])],
            same_centre=bool(same_centre),
            centres=[list(c) for c in centres],
            sweeps=[float(a['sweep']) for a in arcs],
            radius_mm=radii[0] if radii else 0.0,
            radii_mm=radii,
        ))
    return out


def multi_arc_regions(primitives):
    """与 ``layer2d.local_multi_arc_regions`` 同口径的局部多弧区域（对账）。

    只返回 ``n_arcs >= 2`` 且圆心不全相同的切向连续弧串; ``kind`` 语义与
    frozen 函数一致（``multi_arc`` = 反向 sweep, ``same_sign_multi`` = 异常保护）。
    """
    found = []
    for run in arc_runs(primitives):
        if run['n_arcs'] < 2 or run['same_centre']:
            continue
        signs = [1 if sweep >= 0.0 else -1 for sweep in run['sweeps']]
        found.append(dict(
            first=int(run['first']),
            n_arcs=int(run['n_arcs']),
            kind='multi_arc' if len(set(signs)) > 1 else 'same_sign_multi',
            signs=signs,
            start=list(run['start_xy']),
            end=list(run['end_xy']),
        ))
    return found


# ---------------------------------------------------------------------------
# 2) token 化 + Z 块配对
# ---------------------------------------------------------------------------
def _token(kind, prim_indices, prims, **extra):
    token = dict(kind=kind,
                 prim_indices=[int(i) for i in prim_indices],
                 first=int(prim_indices[0]),
                 last=int(prim_indices[-1]))
    if kind == _LINE:
        token['length_mm'] = _dist(prims[prim_indices[0]]['p0'],
                                   prims[prim_indices[0]]['p1'])
    else:
        token['n_arcs'] = len(prim_indices)
        token['length_mm'] = sum(_prim_length(prims[i]) for i in prim_indices)
    token.update(extra)
    return token


def _short_s_token(run, prims, left_index, boundary=False):
    left, right = prims[run[left_index]], prims[run[left_index + 1]]
    radius = float(left['radius'])
    theta = 0.5 * (abs(float(left['sweep'])) + abs(float(right['sweep'])))
    sign = _sweep_sign(left)
    shift = sign * 2.0 * radius * (1.0 - math.cos(theta))
    token = _token(_SHORT_S, [run[left_index], run[left_index + 1]], prims,
                   theta_rad=theta, sweep_signs=[_sweep_sign(left),
                                                _sweep_sign(right)],
                   sign=sign, shift_mm=shift,
                   radius_mm=radius,
                   boundary=bool(boundary),
                   centres=[list(_xy(left['center'])),
                            list(_xy(right['center']))],
                   start_xy=[float(left['p0'][0]), float(left['p0'][1])],
                   end_xy=[float(right['p1'][0]), float(right['p1'][1])],
                   entry_tangent=list(_arc_start_tangent(left)),
                   exit_tangent=list(_arc_end_tangent(right)))
    token['patent_formula_shift_mm'] = 2.0 * radius * (1.0 - math.cos(theta))
    return token


def _synthetic_boundary_s(first_quarter, second_quarter, prims):
    """把（可能被极短直线隔开的）两段反向 quarter token 合成 boundary short-S。"""
    left = prims[first_quarter['first']]
    right = prims[second_quarter['first']]
    token = _token(
        _SHORT_S, [int(first_quarter['first']), int(second_quarter['first'])],
        prims,
        theta_rad=_HALF_PI,
        sweep_signs=[int(first_quarter['sign']), int(second_quarter['sign'])],
        sign=int(first_quarter['sign']),
        shift_mm=float(int(first_quarter['sign']) * 2.0
                       * float(first_quarter['radius_mm'])),
        radius_mm=float(first_quarter['radius_mm']),
        boundary=True,
        centres=[list(_xy(left['center'])), list(_xy(right['center']))],
        start_xy=[float(left['p0'][0]), float(left['p0'][1])],
        end_xy=[float(right['p1'][0]), float(right['p1'][1])],
        entry_tangent=list(_arc_start_tangent(left)),
        exit_tangent=list(_arc_end_tangent(right)))
    token['patent_formula_shift_mm'] = float(token['shift_mm'])
    return token


def _decompose_run(run, prims):
    """一个极大弧串 -> token 列表（从左到右贪心配对 S，其余按单弧处理）。"""
    tokens = []
    indices = run['prim_indices']
    count = len(indices)
    # 注意: 单弧串的 same_centre 恒为 True（只有一个圆心），但单弧不是「同圆拆分」,
    # 必须按 Q / arc_other 处理; 只有 >=2 段且圆心全同才是储存层面的同圆拆分。
    if count >= 2 and run['same_centre']:
        return [_token(_SAME_CIRCLE, indices, prims)]
    radius = float(prims[indices[0]]['radius'])
    bad_radius = any(abs(float(prims[i]['radius']) - radius) > _RADIUS_TOL
                     for i in indices)
    if bad_radius:
        return [_token(_ARC_OTHER, indices, prims)]
    cursor = 0
    while cursor < count:
        if cursor + 1 < count:
            left, right = prims[indices[cursor]], prims[indices[cursor + 1]]
            if _is_short_s_pair(left, right):
                tokens.append(_short_s_token(indices, prims, cursor))
                cursor += 2
                continue
            if _is_boundary_short_s_pair(left, right):
                # |d| = 2R 边界: 两段直接相切的 90° 反向圆弧 -> boundary short-S
                tokens.append(_short_s_token(indices, prims, cursor,
                                             boundary=True))
                cursor += 2
                continue
        arc = prims[indices[cursor]]
        if _is_quarter(arc):
            tokens.append(_token(
                _QUARTER, [indices[cursor]], prims,
                sign=_sweep_sign(arc),
                start_xy=[float(arc['p0'][0]), float(arc['p0'][1])],
                end_xy=[float(arc['p1'][0]), float(arc['p1'][1])],
                entry_tangent=list(_arc_start_tangent(arc)),
                exit_tangent=list(_arc_end_tangent(arc)),
                radius_mm=float(arc['radius'])))
        else:
            tokens.append(_token(
                _ARC_OTHER, [indices[cursor]], prims,
                sweeps=[float(arc['sweep'])],
                radius_mm=float(arc['radius'])))
        cursor += 1
    return tokens


def _tokenize(primitives):
    """原语链 -> (tokens, diagnostics)。tokens 按路径顺序排列。"""
    prims = list(primitives or ())
    diagnostics = []
    tokens = []
    runs = arc_runs(prims)
    run_by_first = {int(run['first']): run for run in runs}
    index = 0
    total = len(prims)
    while index < total:
        prim = prims[index]
        kind = prim.get('kind')
        if kind == 'line':
            tokens.append(_token(_LINE, [index], prims,
                                 p0=[float(prim['p0'][0]),
                                     float(prim['p0'][1])],
                                 p1=[float(prim['p1'][0]),
                                     float(prim['p1'][1])]))
            index += 1
        elif kind == 'arc':
            run = run_by_first.get(index)
            if run is None:  # pragma: no cover - 理论不可达
                diagnostics.append('arc_not_in_run@%d' % index)
                index += 1
                continue
            tokens.extend(_decompose_run(run, prims))
            index = run['prim_indices'][-1] + 1
        else:  # pragma: no cover - 非法原语
            diagnostics.append('unknown_primitive@%d:%r' % (index, kind))
            index += 1
    # 两条直接相切/仅隔可忽略舍入残线的反向 quarter arc -> boundary short-S
    return _fuse_boundary_short_s(tokens, prims), diagnostics


def _token_positions(tokens):
    """token 对象 id -> tokens 下标（避免用 dict 相等性 .index() 误匹配）。"""
    return {id(token): index for index, token in enumerate(tokens)}


def _fuse_boundary_short_s(tokens, prims):
    """把「被极短直线(<= POS_TOL)隔开」的两反向 quarter token 合成为 boundary S。

    规则（与 docstring 一致）: 只有中间直线长度 **大于** ``POS_TOL`` 的两反向
    quarter arc 才能组成 Z 块; 中间直线为零（或只有一条可忽略的舍入残线）时,
    两弧直接相切, 属于 ``|d| = 2R`` 的 boundary short-S。
    """
    out = []
    count = len(tokens)
    index = 0
    while index < count:
        token = tokens[index]
        if token['kind'] == _QUARTER:
            cursor = index + 1
            straight = 0.0
            while cursor < count and tokens[cursor]['kind'] == _LINE:
                straight += tokens[cursor]['length_mm']
                cursor += 1
            if (cursor < count and tokens[cursor]['kind'] == _QUARTER
                    and tokens[cursor]['sign'] == -token['sign']
                    and straight <= _POS_TOL):
                out.append(_synthetic_boundary_s(token, tokens[cursor], prims))
                index = cursor + 1
                continue
        out.append(token)
        index += 1
    return out


def _pair_z_blocks(tokens):
    """从左到右配对 ``Q L* Q``（反向 turn, 中间只允许直线）成 Z 块。

    只有中间直线长度 ``> POS_TOL`` 时才成为 Z 块; ``straight_mm = 0`` 的两反向
    quarter arc 在 ``_fuse_boundary_short_s`` 中已被合成 boundary short-S。
    """
    blocks = []
    count = len(tokens)
    index = 0
    while index < count:
        if tokens[index]['kind'] != _QUARTER:
            index += 1
            continue
        cursor = index + 1
        straight = 0.0
        while cursor < count and tokens[cursor]['kind'] == _LINE:
            straight += tokens[cursor]['length_mm']
            cursor += 1
        if (cursor < count and tokens[cursor]['kind'] == _QUARTER
                and tokens[cursor]['sign'] == -tokens[index]['sign']
                and straight > _POS_TOL):
            radius = float(tokens[index]['radius_mm'])
            sign = int(tokens[index]['sign'])
            blocks.append(dict(
                first_token=int(index), second_token=int(cursor),
                first_q_first_prim=int(tokens[index]['first']),
                second_q_first_prim=int(tokens[cursor]['first']),
                straight_mm=float(straight),
                degenerate=False,
                sign=sign,
                radius_mm=float(radius),
                shift_mm=float(sign * (2.0 * radius + straight)),
                n_arcs=2,
                prim_indices=[int(tokens[index]['first']),
                              int(tokens[cursor]['first'])],
            ))
            index = cursor + 1
        else:
            index += 1
    return blocks


# ---------------------------------------------------------------------------
# 3) 构型判定
# ---------------------------------------------------------------------------
def _net_turn_quarters(prims):
    """净转向（quarter 单位）+ 残差; 无弧时返回 (0, 0.0)。"""
    total = 0.0
    for prim in prims:
        if prim.get('kind') == 'arc':
            total += float(prim['sweep'])
    quarters = int(round(total / _HALF_PI))
    residual = abs(total - quarters * _HALF_PI)
    return quarters, residual


def _simulate_units(units, first_arc, tokens):
    """按路径顺序合成实例位移（evidence 自检）。

    ``units`` 为 ``(kind, payload, token_index)`` 序列（kind ∈ S/Z/Q），块与块之间
    的 ``LINE`` token 沿当前 heading 贡献前进行程。S 的合位移为
    ``shift * rot90(h) + 2R sin(theta) * h``，Z 块为
    ``shift * rot90(h) + 2R * h``，quarter arc 为
    ``R * h + sign * R * rot90(h)`` 并把 heading 旋转 90°。
    """
    heading = _arc_start_tangent(first_arc)
    radius = float(first_arc['radius'])
    total = [0.0, 0.0]
    prev_end = None
    for kind, payload, token_index in units:
        if kind == 'Z':
            start_token = int(payload['first_token'])
            end_token = int(payload['second_token'])
        else:
            start_token = end_token = int(token_index)
        if prev_end is not None:
            for cursor in range(prev_end + 1, start_token):
                if tokens[cursor]['kind'] == _LINE:
                    length = float(tokens[cursor]['length_mm'])
                    total[0] += length * heading[0]
                    total[1] += length * heading[1]
        left = _rot90(heading)
        if kind == 'S':
            shift = float(payload['shift_mm'])
            advance = 2.0 * float(payload['radius_mm']) * math.sin(
                float(payload['theta_rad']))
            total[0] += shift * left[0] + advance * heading[0]
            total[1] += shift * left[1] + advance * heading[1]
        elif kind == 'Z':
            shift = float(payload['shift_mm'])
            advance = 2.0 * float(payload['radius_mm'])
            total[0] += shift * left[0] + advance * heading[0]
            total[1] += shift * left[1] + advance * heading[1]
        else:  # Q
            sign = int(payload['sign'])
            total[0] += radius * heading[0] + sign * radius * left[0]
            total[1] += radius * heading[1] + sign * radius * left[1]
            heading = _rotate(heading, sign * _HALF_PI)
        prev_end = end_token
    return total, heading


def _instance(type_, relation, s_tokens, z_blocks, turn_tokens, tokens, prims,
              token_pos=None):
    """构造一个构型实例记录（含第一性几何证据）。"""
    if token_pos is None:  # pragma: no cover - 内部调用总是传入
        token_pos = _token_positions(tokens)
    arc_indices = []
    for token in s_tokens + turn_tokens:
        arc_indices.extend(token['prim_indices'])
    for block in z_blocks:
        arc_indices.extend(block['prim_indices'])
    arc_indices = sorted(set(int(i) for i in arc_indices))
    block_seq = []      # 按 token 顺序排列的 (token index, kind, payload)
    for token in s_tokens:
        block_seq.append((token_pos[id(token)], 'S', token))
    for block in z_blocks:
        block_seq.append((block['first_token'], 'Z', block))
    for token in turn_tokens:
        block_seq.append((token_pos[id(token)], 'Q', token))
    block_seq.sort(key=lambda item: item[0])
    first_arc = prims[arc_indices[0]]
    last_arc = prims[arc_indices[-1]]
    units = [(kind, payload, token_index)
             for token_index, kind, payload in block_seq]
    predicted, exit_heading = _simulate_units(units, first_arc, tokens)
    start_xy = _xy(first_arc['p0'])
    end_xy = _xy(last_arc['p1'])
    actual = (end_xy[0] - start_xy[0], end_xy[1] - start_xy[1])
    closure = math.hypot(predicted[0] - actual[0], predicted[1] - actual[1])
    entry_heading = _arc_start_tangent(first_arc)
    lateral = _dot(actual, _rot90(entry_heading))

    def _gap(previous_token_index, next_token_index):
        gap = 0.0
        for cursor in range(previous_token_index + 1, next_token_index):
            if tokens[cursor]['kind'] == _LINE:
                gap += tokens[cursor]['length_mm']
        return float(gap)

    evidence = dict(
        relation=relation,
        block_order=''.join(kind for _i, kind, _p in block_seq),
        entry_heading=[float(entry_heading[0]), float(entry_heading[1])],
        exit_heading=[float(exit_heading[0]), float(exit_heading[1])],
        predicted_displacement_mm=[float(predicted[0]), float(predicted[1])],
        actual_displacement_mm=[float(actual[0]), float(actual[1])],
        displacement_closure_mm=float(closure),
        lateral_displacement_mm=float(lateral),
        s_shifts_mm=[float(t['shift_mm']) for t in s_tokens],
        z_shifts_mm=[float(b['shift_mm']) for b in z_blocks],
        s_theta_rad=[float(t['theta_rad']) for t in s_tokens],
        z_straight_mm=[float(b['straight_mm']) for b in z_blocks],
        degenerate_z=any(bool(b['degenerate']) for b in z_blocks),
        radii_mm=sorted({round(float(prims[i]['radius']), 9)
                         for i in arc_indices}),
        tolerances=dict(TOLERANCES),
    )
    # 结构块之间的夹直线 / 相切关系（attached 表示两结构直接相切）
    attached = dict()
    if s_tokens and z_blocks:
        block = z_blocks[0]
        before = min(token_pos[id(t)] for t in s_tokens) < block['first_token']
        start = token_pos[id(s_tokens[-1] if before else s_tokens[0])]
        end = block['first_token'] if before else block['second_token']
        attached['s_to_z'] = bool(_gap(start, end) <= _POS_TOL)
        evidence['s_to_z_gap_mm'] = _gap(start, end)
    if turn_tokens:
        turn_index = token_pos[id(turn_tokens[0])]
        s_indices = [token_pos[id(t)] for t in s_tokens]
        if s_indices:
            nearest = min(s_indices, key=lambda i: abs(i - turn_index))
            lo, hi = (nearest, turn_index) if nearest < turn_index else (
                turn_index, nearest)
            evidence['s_to_turn_gap_mm'] = _gap(lo, hi)
            attached['s_to_turn'] = bool(_gap(lo, hi) <= _POS_TOL)
    if attached:
        evidence['attached'] = attached

    instance = dict(
        type=type_,
        patent_figure=PATENT_FIGURE[type_],
        caption=STRUCTURE_CAPTION[type_],
        relation=relation,
        first=int(arc_indices[0]),
        last=int(arc_indices[-1]),
        n_arcs=len(arc_indices),
        arc_indices=arc_indices,
        token_indices=sorted(int(i) for i in
                             [token_pos[id(t)] for t in s_tokens]
                             + [token_pos[id(t)] for t in turn_tokens]
                             + [b['first_token'] for b in z_blocks]
                             + [b['second_token'] for b in z_blocks]),
        s_blocks=[dict(first=int(t['first']), last=int(t['last']),
                       n_arcs=2,
                       theta_rad=float(t['theta_rad']),
                       shift_mm=float(t['shift_mm']),
                       sweep_signs=list(t['sweep_signs']))
                  for t in s_tokens],
        z_blocks=[dict(first=int(b['first_q_first_prim']),
                       last=int(b['second_q_first_prim']),
                       n_arcs=2,
                       straight_mm=float(b['straight_mm']),
                       degenerate=bool(b['degenerate']),
                       shift_mm=float(b['shift_mm']))
                  for b in z_blocks],
        turn_quarters=[dict(first=int(t['first']), n_arcs=1,
                            sign=int(t['sign']))
                       for t in turn_tokens],
        start_xy=[float(start_xy[0]), float(start_xy[1])],
        end_xy=[float(end_xy[0]), float(end_xy[1])],
        direction_deg=math.degrees(math.atan2(entry_heading[1],
                                              entry_heading[0])),
        arc_length_mm=float(sum(_prim_length(prims[i]) for i in arc_indices)),
        span_xy_mm=float(math.hypot(end_xy[0] - start_xy[0],
                                    end_xy[1] - start_xy[1])),
        evidence=evidence,
    )
    return instance


def analyze_primitives(primitives):
    """一个 flat body 原语链的完整结构分析。

    返回::

        dict(instances=[...七种构型实例...],
             short_s_blocks=[...所有短S块(含非图6/7用法)...],
             tokens=[...token 化结果...],
             z_blocks=[...Z 型块...],
             arc_runs=[...极大切向连续弧串...],
             net_turn_quarters=int, net_turn_residual_rad=float,
             relation='opposite'|'adjacent'|'same'|'other'|None,
             unclassified=[...拒绝判定的原因...],
             diagnostics=[...])
    """
    prims = [dict(prim) for prim in (primitives or ())]
    tokens, diagnostics = _tokenize(prims)
    token_pos = _token_positions(tokens)
    runs = arc_runs(prims)
    z_blocks = _pair_z_blocks(tokens)
    quarters = _net_turn_quarters(prims)
    net_quarters, residual = quarters
    if not any(prim.get('kind') == 'arc' for prim in prims):
        relation = None
    elif residual > _NET_TOL:
        relation = None
        diagnostics.append('net_turn_not_axis:%.9f' % residual)
    elif net_quarters == 0:
        relation = 'opposite'
    elif abs(net_quarters) == 1:
        relation = 'adjacent'
    elif abs(net_quarters) == 2:
        relation = 'same'
    else:
        relation = 'other'

    z_token_indices = set()
    for block in z_blocks:
        z_token_indices.add(block['first_token'])
        z_token_indices.add(block['second_token'])
    quarter_tokens = [tok for tok in tokens if tok['kind'] == _QUARTER]
    turn_tokens = [tok for tok in quarter_tokens
                   if token_pos[id(tok)] not in z_token_indices]
    s_tokens = [tok for tok in tokens if tok['kind'] == _SHORT_S]

    instances = []
    unclassified = []
    if relation == 'opposite':
        consumed = set()
        if len(s_tokens) == 1 and not z_blocks and not turn_tokens:
            instance = _instance('6a', relation, s_tokens, [], [], tokens,
                                 prims, token_pos)
            consumed.update(instance['token_indices'])
            instances.append(instance)
        elif len(s_tokens) == 2 and not z_blocks and not turn_tokens:
            instance = _instance('6b', relation, s_tokens, [], [], tokens,
                                 prims, token_pos)
            consumed.update(instance['token_indices'])
            instances.append(instance)
        elif len(s_tokens) == 1 and len(z_blocks) == 1 and not turn_tokens:
            s_index = token_pos[id(s_tokens[0])]
            z_block = z_blocks[0]
            if s_index < z_block['first_token']:
                type_ = '6c'
            elif s_index > z_block['second_token']:
                type_ = '6d'
            else:  # S 夹在 Z 两个 quarter 之间（Z 配对规则下不应发生）
                type_ = None
                unclassified.append('short_s_inside_z_block')
            if type_ is not None:
                instance = _instance(type_, relation, s_tokens, z_blocks,
                                     [], tokens, prims, token_pos)
                consumed.update(instance['token_indices'])
                instances.append(instance)
        elif not s_tokens:
            # 纯 Z / 纯直线 / 退化 Z：没有组合圆弧，不属于图 6 构型
            pass
        else:
            unclassified.append(
                'opposite_structure_not_in_patent:nS=%d,nZ=%d,nTurnQ=%d'
                % (len(s_tokens), len(z_blocks), len(turn_tokens)))
        # 除 LINE / same_circle 外不允许有未占用 token
        leftovers = [tok['kind'] for tok in tokens
                     if tok['kind'] not in _NEUTRAL_TOKENS
                     and token_pos[id(tok)] not in consumed]
        if instances and leftovers:
            unclassified.append('unconsumed_tokens:' + ','.join(leftovers))
            instances = []
    elif relation == 'adjacent':
        if not s_tokens:
            # 没有组合圆弧的相邻侧 body（ADJ_L / ADJ_Z_TURN / loop 等）不是
            # 图 7 的组合圆弧构型，无需记为 unclassified。
            pass
        elif len(turn_tokens) != 1:
            unclassified.append('adjacent_with_%d_turn_quarters'
                                % len(turn_tokens))
        elif z_blocks:
            unclassified.append('adjacent_with_z_block:nZ=%d' % len(z_blocks))
        else:
            turn_index = token_pos[id(turn_tokens[0])]
            before = [tok for tok in s_tokens
                      if token_pos[id(tok)] < turn_index]
            after = [tok for tok in s_tokens
                     if token_pos[id(tok)] > turn_index]
            type_ = None
            if len(before) == 1 and not after:
                type_ = '7a'
            elif not before and len(after) == 1:
                type_ = '7b'
            elif len(before) == 2 and not after:
                type_ = '7c'
            if type_ is not None:
                instance = _instance(type_, relation, s_tokens, [],
                                     turn_tokens, tokens, prims, token_pos)
                consumed = set(instance['token_indices'])
                leftovers = [tok['kind'] for tok in tokens
                             if tok['kind'] not in _NEUTRAL_TOKENS
                             and token_pos[id(tok)] not in consumed]
                if leftovers:
                    unclassified.append('unconsumed_tokens:'
                                        + ','.join(leftovers))
                else:
                    instances.append(instance)
            else:
                unclassified.append(
                    'adjacent_short_s_not_in_patent:nBefore=%d,nAfter=%d'
                    % (len(before), len(after)))
    elif relation == 'same':
        if s_tokens:
            unclassified.append('same_side_short_s_is_figure5_not_figure6_7')
    elif relation is None:
        if s_tokens or z_blocks:
            unclassified.append('non_axis_net_turn')

    # 所有短 S 块（含不属于图 6/7 的用法）
    instance_by_token = {}
    for instance in instances:
        for s_block in instance['s_blocks']:
            instance_by_token[s_block['first']] = (instance['type'], s_block)
    short_blocks = []
    for token in s_tokens:
        owner = instance_by_token.get(int(token['first']))
        entry = dict(
            first=int(token['first']),
            last=int(token['last']),
            n_arcs=2,
            theta_rad=float(token['theta_rad']),
            sweep_signs=list(token['sweep_signs']),
            shift_mm=float(token['shift_mm']),
            entry_tangent=[float(v) for v in token['entry_tangent']],
            start_xy=[float(v) for v in token['start_xy']],
            end_xy=[float(v) for v in token['end_xy']],
            relation=relation,
            structure_type=owner[0] if owner else None,
            attached_to_z=None,
            attached_to_turn=None,
        )
        for instance in instances:
            evidence = instance['evidence']
            if int(token['first']) in instance['arc_indices']:
                attached = evidence.get('attached') or {}
                entry['attached_to_z'] = bool(
                    attached.get('s_to_z')) if instance['z_blocks'] else None
                entry['attached_to_turn'] = bool(
                    attached.get('s_to_turn')) if instance['turn_quarters'] else None
                break
        short_blocks.append(entry)

    return dict(
        instances=instances,
        short_s_blocks=short_blocks,
        tokens=tokens,
        z_blocks=[dict(block) for block in z_blocks],
        arc_runs=runs,
        net_turn_quarters=int(net_quarters),
        net_turn_residual_rad=float(residual),
        relation=relation,
        unclassified=list(unclassified),
        diagnostics=list(diagnostics),
    )


# ---------------------------------------------------------------------------
# 4) 对外接口（任务书 / layer2d 消融门 API 契约）
# ---------------------------------------------------------------------------
def classify_primitives(primitives):
    """一个 flat body 的 line/arc primitives 列表 -> 七种构型实例列表。

    每项至少含 ``{'type', 'first', 'n_arcs'}``; 完整字段见 ``analyze_primitives``。
    输入就是 ``layer2d._build_candidate(spec, frame)`` 产出的 world primitives
    （世界坐标 ``line``/``arc`` dict 列表），纯净、无副作用、可热路径调用。

    * 无构型（纯直线 / 纯独立转角 / 纯 Z / 同侧 U 型回转 / 同圆拆分 / 非专利
      组合）时返回 ``[]``;
    * 输入若跨多个 flat part 拼接（body 链不连续）不在本函数职责内，
      请用 ``classify_route``。
    """
    return analyze_primitives(primitives)['instances']


def classify_route(route):
    """完整 route（含 ``parts``） -> 所有 flat part 的构型实例列表。

    每个实例附加 ``part_index``（``route['parts']`` 下标）、``part_kind``、
    ``layer_id``、``z_mm``（该 flat part 的物理高度）与 ``route_id``。
    """
    if not isinstance(route, dict):
        return []
    route_id = route.get('route_id')
    out = []
    for part_index, part in enumerate(route.get('parts') or ()):
        if not isinstance(part, dict) or part.get('kind') != 'flat':
            continue
        prims = part.get('primitives') or ()
        if not prims:
            continue
        for instance in classify_primitives(prims):
            record = dict(instance)
            record['route_id'] = route_id
            record['part_index'] = int(part_index)
            record['part_kind'] = 'flat'
            record['layer_id'] = part.get('layer_id')
            record['z_mm'] = (float(part['z_mm'])
                              if part.get('z_mm') is not None else None)
            out.append(record)
    return out


def route_types(route_or_primitives):
    """便捷集合: route dict 或 primitives list -> ``set(STRUCTURE_TYPES)``。"""
    if isinstance(route_or_primitives, dict):
        return {instance['type'] for instance in classify_route(route_or_primitives)}
    if isinstance(route_or_primitives, (list, tuple)):
        if route_or_primitives and isinstance(route_or_primitives[0], dict) \
                and route_or_primitives[0].get('kind') in ('line', 'arc'):
            return {instance['type']
                    for instance in classify_primitives(route_or_primitives)}
        # 兼容 flat part 列表 / route 列表
        return {instance['type']
                for instance in route_structure_instances(route_or_primitives)}
    return set()


def route_structure_instances(parts_or_primitives):
    """任务书接口: 从 primitives / flat part 列表 / route dict / route 列表
    提取七种构型实例（自动分派，保证一条 route 的实例带 part 元数据）。
    """
    value = parts_or_primitives
    if isinstance(value, dict):
        if 'parts' in value or 'route_id' in value:
            return classify_route(value)
        if value.get('kind') == 'flat':
            return classify_primitives(value.get('primitives') or ())
        if value.get('kind') in ('line', 'arc'):
            return classify_primitives([value])
        return []
    if isinstance(value, (list, tuple)):
        if not value:
            return []
        first = value[0]
        if isinstance(first, dict):
            if first.get('kind') in ('line', 'arc'):
                return classify_primitives(list(value))
            if first.get('kind') == 'flat':
                out = []
                for part in value:
                    if isinstance(part, dict) \
                            and part.get('kind') == 'flat':
                        out.extend(classify_primitives(
                            part.get('primitives') or ()))
                return out
            if 'parts' in first or 'route_id' in first:
                out = []
                for route in value:
                    if isinstance(route, dict):
                        out.extend(classify_route(route))
                return out
        return []
    return []


def short_s_blocks(primitives):
    """一个 flat body 中所有短 S 块的清单（含不属于图 6/7 的用法）。

    每项: ``first``/``last``（arc 原语下标）、``theta_rad``、``shift_mm``、
    ``relation``（opposite/adjacent/same/other）、``structure_type``（若属于
    七种构型之一，则为对应 type，否则 None）、``attached_to_z``/``attached_to_turn``。
    用于核对「存在组合圆弧但未被七种构型覆盖」的用法（例如同侧连接图 5 结构）。
    """
    return analyze_primitives(primitives)['short_s_blocks']


def tokenize_primitives(primitives):
    """token 化结果（调试/报告用）: ``dict(tokens, z_blocks, diagnostics)``。"""
    prims = [dict(prim) for prim in (primitives or ())]
    tokens, diagnostics = _tokenize(prims)
    return dict(tokens=tokens, z_blocks=_pair_z_blocks(tokens),
                diagnostics=diagnostics)
