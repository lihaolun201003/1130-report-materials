"""Render ten editable SVGs and vector A4 PDFs, plus PNG review copies."""
import argparse
import json
from math import ceil, cos, pi, sin, tan
import os
from pathlib import Path
import warnings

import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager, pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, PathPatch, Polygon, Rectangle
from matplotlib.path import Path as MplPath
import numpy as np
from PIL import Image, ImageDraw
import pymupdf

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
BLACK, WHITE = "#000000", "#ffffff"
DASH = (0, (4, 2.4))
SHORT_DASH = (0, (1.8, 1.65))
CHAIN = (0, (7, 2, 1, 2))
FIGURE_TITLES = [
    "总体技术流程", "端口弦与交叉冲突图", "连接家族及高度兼容关系",
    "模拟退火流程", "分组优化前后", "组标签与物理高度映射",
    "三维波导空间构造", "端口弦严格相交判定", "20 个物理高度及家族分配",
    "E1 与 E3 实际同高交叉",
]


def setup_font(path):
    font_manager.fontManager.addfont(str(path))
    name = font_manager.FontProperties(fname=path).get_name()
    plt.rcParams.update({"font.family": name, "pdf.fonttype": 42, "svg.fonttype": "none",
                         "svg.hashsalt": "patent-20h", "path.simplify": False,
                         "axes.unicode_minus": False, "savefig.facecolor": WHITE})


class Drawing:
    def __init__(self, number):
        self.fig = plt.figure(figsize=(210 / 25.4, 297 / 25.4), facecolor=WHITE)
        self.ax = self.fig.add_axes([0, 0, 1, 1], xlim=(0, 210), ylim=(297, 0))
        self.ax.set_axis_off()
        self.text(105, 28, "说明书附图", 16)
        self.text(105, 267, f"图{number}", 14)

    def text(self, x, y, label, fs=11, align="center", blank=False, **style):
        bbox = dict(facecolor=WHITE, edgecolor="none", pad=1.25) if blank else None
        self.ax.text(x, y, label, size=fs, color=BLACK, va="center", ha=align,
                     bbox=bbox, zorder=6, **style)

    def line(self, *points, lw=0.85, ls="-", z=2):
        x, y = zip(*points)
        self.ax.plot(x, y, color=BLACK, lw=lw, ls=ls, solid_capstyle="butt",
                     dash_capstyle="butt", solid_joinstyle="round", zorder=z)

    def rect(self, x, y, w, h, lw=0.85, ls="-"):
        self.ax.add_patch(Rectangle((x, y), w, h, fill=False, edgecolor=BLACK,
                                    lw=lw, ls=ls, zorder=3))

    def dot(self, x, y, r=0.86, open_circle=False, lw=0.8):
        self.ax.add_patch(Circle((x, y), r, edgecolor=BLACK,
                                 facecolor=WHITE if open_circle else BLACK, lw=lw, zorder=5))

    def arrow(self, start, end, lw=0.85):
        self.ax.add_patch(FancyArrowPatch(start, end, arrowstyle="->", shrinkA=0, shrinkB=0,
                                          mutation_scale=9, lw=lw, color=BLACK, zorder=4))

    def elbows(self, *points):
        if len(points) > 2:
            self.line(*points[:-1])
        self.arrow(*points[-2:])

    def box(self, x, y, w, h, label, fs=11.5):
        self.rect(x - w / 2, y - h / 2, w, h)
        self.text(x, y, label, fs)

    def diamond(self, x, y, w, h, label, fs=11):
        corners = [(x - w / 2, y), (x, y - h / 2), (x + w / 2, y), (x, y + h / 2)]
        self.ax.add_patch(Polygon(corners, closed=True, fill=False, edgecolor=BLACK, lw=0.85))
        self.text(x, y, label, fs)

    def node(self, x, y, tag):
        self.dot(x, y, r=5, open_circle=True, lw=0.9)
        self.text(x, y, tag, 11.5)

    def path(self, vertices, codes, lw=0.9, z=3):
        self.ax.add_patch(PathPatch(MplPath(vertices, codes), fill=False, color=BLACK, lw=lw,
                                    capstyle="round", joinstyle="round", zorder=z))


def identifier(prefix, number):
    return f"{prefix}{number}"


def draw1(d, data):
    labels = [
        "固定端口位置、连接关系及物理高度资源",
        "步骤1  建立线路交叉冲突图",
        "步骤2  确定线路家族及可用高度",
        "步骤3  模拟退火优化线路分组",
        "步骤4  映射实际物理高度",
        "步骤5  构造并校验三维波导",
        "三维光波导布线结果",
    ]
    ys = list(range(62, 231, 28))
    for i, (y, label) in enumerate(zip(ys, labels)):
        d.box(105, y, 117, 15, label, 13)
        if i:
            d.arrow((105, ys[i - 1] + 7.5), (105, y - 7.5))
    d.text(41, ys[0], "输入", 10, "right")
    d.text(41, ys[-1], "输出", 10, "right")


def intersection(first, second):
    p, q = map(np.array, first)
    a, b = map(np.array, second)
    t, _ = np.linalg.solve(np.column_stack((q - p, a - b)), a - p)
    return p + t * (q - p)


def draw2(d, data):
    d.rect(27, 90, 59, 76)
    # c labels sit outside the chord bundle near the endpoints.
    label_positions = [(41, 106), (75, 99), (41, 132), (42, 152)]
    for i, (start, finish) in enumerate(data["chords"], 1):
        d.line(start, finish, lw=1)
        for (x, y), prefix, offset, align in ((start, "a", -3, "right"), (finish, "b", 3, "left")):
            d.dot(x, y, r=0.85)
            d.text(x + offset, y, identifier(prefix, i), 11, align)
        lx, ly = label_positions[i - 1]
        d.text(lx, ly, identifier("c", i), 11)
    for i, j in data["edges"]:
        point = intersection(data["chords"][i - 1], data["chords"][j - 1])
        d.dot(*point, r=0.65, open_circle=True, lw=0.75)

    d.arrow((101, 128), (120, 128))
    points = {1: (142, 104), 2: (179, 104), 3: (179, 153), 4: (142, 153)}
    for i, j in data["edges"]:
        d.line(points[i], points[j], lw=1)
    for i, (x, y) in points.items():
        d.node(x, y, identifier("v", i))
    d.text(56.5, 182, "（a）端口弦", 12.5)
    d.text(160.5, 182, "（b）交叉冲突图", 12.5)
    d.dot(29, 205, r=0.75, open_circle=True)
    d.text(34, 205, "严格相交点", 10.5, "left")
    d.text(124, 199, "顶点  光波导线路", 10.5, "left")
    d.text(124, 210, "无向边  潜在交叉关系", 10.5, "left")


def table(d, xs, ys, rows, fs=10.5):
    for x in xs:
        d.line((x, ys[0]), (x, ys[-1]), lw=0.63)
    for y in ys:
        d.line((xs[0], y), (xs[-1], y), lw=0.63)
    for j, row in enumerate(rows):
        for i, value in enumerate(row):
            d.text((xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2, str(value), fs)


def draw3(d, data):
    for x, title in ((58, "第一接口行 Z1"), (151, "第二接口行 Z2")):
        d.text(x, 65, title, 13)
        d.rect(x - 25, 82, 50, 50)
        for dx, dy, side in ((0, -31, "N"), (31, 0, "E"), (0, 31, "S"), (-31, 0, "W")):
            d.text(x + dx, 107 + dy, side, 10)
    d.line((58, 82), (58, 132), lw=1.15)
    d.line((33, 107), (83, 107), lw=1.15)
    d.text(53, 94, "V", align="right")
    d.text(70, 113, "H")
    for start, end, x, y, tag in [
        ((126, 97), (141, 82), 138, 94, "NW"), ((161, 82), (176, 97), 164, 94, "NE"),
        ((126, 117), (141, 132), 138, 120, "SW"), ((161, 132), (176, 117), 164, 120, "SE"),
    ]:
        d.line(start, end, lw=1.15)
        d.text(x, y, tag, 10)
    d.text(58, 149, "V 南北向    H 东西向", 10.5)
    d.rect(23, 166, 70, 45)
    for y, label in ((176, "Z1V 与 Z1H"), (188.5, f"{data['z1_cross_family']} / 16384"),
                     (201, "主体高度互斥")):
        d.text(58, y, label, 11)
    matrix = data["family_matrix_z2"]
    z2 = ["NE", "SE", "NW", "SW"]
    rows = [["", *z2]] + [[name, *["/" if v is None else v for v in vals]]
                          for name, vals in zip(z2, matrix)]
    table(d, [109, 125, 141, 157, 173, 189], list(range(166, 212, 9)), rows)
    d.text(105, 223, "跨家族严格相交弦对数", 11)
    d.text(105, 237, "0 表示端口弦无交叉，实际共面须校验", 11)


def draw4(d, data):
    x = 105
    labels = {
        48: "打乱初始组标签", 66: "局部下降至整轮无改进", 84: "设置初温",
        102: "随机单点移组", 120: "由邻接计数差求能量差",
        177: "乘降温因子", 215: "复算并比较重启末态", 252: "输出最佳分组",
    }
    for y, label in labels.items():
        d.box(x, y, 76, 11, label, 11)
    for a, b in ((48, 66), (66, 84), (84, 102), (102, 120)):
        d.arrow((x, a + 5.5), (x, b - 5.5))
    d.diamond(x, 139, 87, 17, "接受候选分组？")
    d.arrow((x, 125.5), (x, 130.5))
    for px, side, state in ((48, "是", "更新状态"), (162, "否", "保持状态")):
        corner = x + (-43.5 if px < x else 43.5)
        d.elbows((corner, 139), (px, 139), (px, 152.5))
        d.text(px + (4 if px < x else -4), 145, side, 9,
               align="left" if px < x else "right")
        d.box(px, 158, 30, 11, state, 10.5)
        d.line((px, 163.5), (px, 168), (x, 168))
    d.arrow((x, 168), (x, 171.5))
    d.diamond(x, 196, 80, 17, "本轮退火停止？")
    d.arrow((x, 182.5), (x, 187.5))
    d.elbows((145, 196), (190, 196), (190, 102), (143, 102))
    d.text(181, 192, "否", 9)
    d.arrow((x, 204.5), (x, 209.5))
    d.text(112, 207, "是", 9)
    d.diamond(x, 233, 80, 17, "结束重启？")
    d.arrow((x, 220.5), (x, 224.5))
    d.elbows((65, 233), (20, 233), (20, 48), (67, 48))
    d.text(31, 229, "否", 9)
    d.arrow((x, 241.5), (x, 246.5))
    d.text(112, 244, "是", 9)


def draw5(d, data):
    for panel, left in enumerate((22, 117)):
        groups = data["groups"][panel]
        if panel == 0:
            groups = [groups[0], list(reversed(groups[1]))]
        xs = [left + 13, left + 56]
        first_y, second_y = 116, 159
        points = {i: (x, y) for group, x in zip(groups, xs)
                  for i, y in zip(group, (first_y, second_y))}
        for group, x in enumerate(xs, 1):
            d.rect(x - 12, 103, 24, 69, lw=0.85, ls=SHORT_DASH)
            d.text(x, 95, f"高度组{group}", 10.5)
        for i, j in data["edges"]:
            a, b = points[i], points[j]
            if panel == 1 and (i, j) == (2, 3):
                # Route one of the four edges around the cycle to avoid a visual intersection.
                d.line(a, (191, 80), (b[0] - 17, 80), (b[0] - 17, b[1]), b,
                       ls=DASH, lw=1.0)
            else:
                d.line(a, b, lw=1.18 if a[0] == b[0] else 1.0,
                       ls="-" if a[0] == b[0] else DASH)
        for i, (x, y) in points.items():
            d.node(x, y, identifier("v", i))
        timing = ["优化前", "优化后"][panel]
        letter = "ab"[panel]
        d.text(left + 34.5, 185, f"（{letter}）{timing}：组内冲突边数为{data['energies'][panel]}", 10.5)
    for x, style, label in ((34, "-", "组内冲突边"), (112, DASH, "组间冲突边")):
        d.line((x, 207), (x + 16, 207), lw=1.15, ls=style)
        d.text(x + 20, 207, label, 10.5, "left")
    d.text(105, 224, "四条线路的分组示例", 10.5)


def height_label(plane, include_id=False):
    if plane in (1001, 1002):
        label = f"Z{plane - 1000}接口"
        return f"{label}（{plane}）" if include_id else label
    return f"L{plane}"


def z_text(z):
    return f"{z:+.3f}".replace("-", "−")


def draw6(d, data):
    d.text(105, 75, "20 高度实验的 Z1H 家族", 13)
    xs = (46, 105, 164)
    for x, label in zip(xs, ("组标签", "物理高度标识", "实际 z / mm")):
        d.text(x, 98, label, 12)
    d.line((27, 107), (183, 107), lw=0.75)
    heights = {h["plane_id"]: h["z_mm"] for h in data["heights"]}
    for i, plane in enumerate(data["families"]["Z1H"], 1):
        y = 93 + i * 28
        d.box(xs[0], y, 31, 14, f"组{i}", 12)
        d.box(xs[1], y, 50, 14, height_label(plane, True), 11.5)
        d.box(xs[2], y, 32, 14, z_text(heights[plane]), 12)
        d.arrow((xs[0] + 17, y), (xs[1] - 27, y))
        d.arrow((xs[1] + 27, y), (xs[2] - 18, y))
    d.text(105, 208, "按家族允许高度列表的顺序映射", 11)


def arc_cubics(center, radius, start, sweep):
    """Return Bezier controls for circular arcs split at 22.5 degrees or less."""
    n = max(1, ceil(abs(sweep) / (pi / 8)))
    for i in range(n):
        a, b = start + sweep * i / n, start + sweep * (i + 1) / n
        scale = 4 / 3 * tan((b - a) / 4) * radius
        p = np.array(center) + radius * np.array([cos(a), sin(a)])
        q = np.array(center) + radius * np.array([cos(b), sin(b)])
        yield p + scale * np.array([-sin(a), cos(a)]), q - scale * np.array([-sin(b), cos(b)]), q


def double_arc(d, start, finish, lw=1.25):
    # Use equal radii and opposite curvatures with horizontal tangent at both ends.
    x, y = start
    x1, y1 = finish
    f = x1 - x
    # The spatial sketch exaggerates vertical distances for readability.
    delta = min(abs(y1 - y), 0.5 * f)
    vertical_scale = (y1 - y) / delta
    theta = 2 * np.arctan2(delta, f)
    radius = (f * f + delta * delta) / (4 * delta)
    local = [np.array([0.0, 0.0])]
    for controls in arc_cubics((0.0, radius), radius, -pi / 2, theta):
        local.extend(controls)
    for controls in arc_cubics((f, delta - radius), radius, pi / 2 + theta, -theta):
        local.extend(controls)
    d.path([(x + a, y + vertical_scale * b) for a, b in local],
           [MplPath.MOVETO] + [MplPath.CURVE4] * (len(local) - 1), lw=lw)


def draw7(d, data):
    # Follow the original page 7 callouts and parallel-plane layout.
    depth = 34
    for front in (109, 137):
        back = front - depth
        d.line((30, front), (156, front), (181, back), (55, back), (30, front), lw=0.65, ls=DASH)
    d.text(24, 106, "h", 11)
    d.text(23, 134, "zp", 11)
    lift_x = 25 * (137 - 127) / depth
    direct_x = 25 * (137 - 115) / depth
    lift_ports = ((30 + lift_x, 127), (156 + lift_x, 127))
    direct_ports = ((30 + direct_x, 115), (156 + direct_x, 115))
    d.line(lift_ports[0], (57, 127), lw=1.25, z=4)
    double_arc(d, (57, 127), (74, 99))
    d.line((74, 99), (132, 99), lw=1.25, z=4)
    double_arc(d, (132, 99), (149, 127))
    d.line((149, 127), lift_ports[1], lw=1.25, z=4)
    d.line(*direct_ports, lw=1.25, z=4)
    for p in (*lift_ports, *direct_ports):
        d.dot(*p, r=0.9)
    for x, y, text, edge in [
        (47, 147, "71", ((48, 143), (52, 127))),
        (61, 67, "72", ((62, 71), (66, 110))),
        (104, 67, "73", ((104, 71), (104, 99))),
        (158, 150, "74", ((158, 146), (158, 115))),
    ]:
        d.line(*edge, lw=0.65)
        d.text(x, y, text, 11)
    d.text(105, 161, "（a）多高度布线的空间构造", 12)
    p, q, m = (59, 220), (148, 190), (103.5, 205)
    d.line((36, 220), p, lw=1.25)
    double_arc(d, p, q)
    d.line(q, (173, 190), lw=1.25)
    for point, x, y, label in ((p, 55, 225, "P"), (q, 148, 184, "Q"), (m, 110, 211, "M")):
        d.dot(*point, r=0.84)
        d.text(x, y, label, 11)
    d.line((59, 222), (59, 239), lw=0.56, ls=DASH)
    d.line((148, 192), (148, 239), lw=0.56, ls=DASH)
    d.line((59, 237), (148, 237), lw=0.65)
    for x in (59, 148):
        d.line((x, 235), (x, 239), lw=0.65)
    d.text(104, 243, "F", 11)
    d.line((171, 190), (171, 220), lw=0.65)
    d.line((168.5, 220), (173.5, 220), lw=0.65)
    d.text(177, 205, "d", 11)
    d.text(105, 253, "（b）双圆弧升降过渡截面", 12)


def draw8(d, data):
    captions = [
        ("（a）严格相交", "建立冲突边"),
        ("（b）不相交", "不建立冲突边"),
        ("（c）端点接触", "不计为严格相交"),
    ]
    for k, (case, (caption, note)) in enumerate(zip(data["cases"], captions)):
        x0 = 28 + k * 63
        pair = [[(x0 + x, 101 + 1.45 * y) for x, y in chord] for chord in case]
        for chord in pair:
            d.line(*chord, lw=1.2)
            for point in chord:
                d.dot(*point, r=0.82)
        if k == 0:
            d.dot(*intersection(*pair), r=1.05, open_circle=True)
        for i, chord in enumerate(pair, 1):
            for label, (x, y) in zip(("a", "b"), chord):
                if k == 2 and x == x0 + 16:
                    continue
                left = label == "a"
                d.text(x + (-3.2 if left else 3.2), y, identifier(label, i), 11.5,
                       "right" if left else "left")
        if k == 2:
            x, y = pair[0][1]
            d.line((x, y - 2.2), (x, y - 7), lw=0.6)
            d.text(x, y - 11, "b1 = a2", 11.5)
        d.text(x0 + 14, 161, caption, 12)
        d.text(x0 + 14, 176, note, 11)


def draw9(d, data):
    top, bottom = 66, 224
    glass = data["glass"]
    ymax, ymin = glass["z_max_mm"], glass["z_min_mm"]
    to_y = lambda z: top + (ymax - z) / (ymax - ymin) * (bottom - top)
    d.text(105, 49, "玻璃板 150 mm × 150 mm × 1 mm", 12.5)
    d.rect(30, top, 41, bottom - top, lw=0.9)
    d.text(74, 59, "高度", 10, "left")
    d.text(100, 59, "z / mm", 10)
    kind = {"frozen": "-", "movable": DASH, "interface": CHAIN}
    for h in data["heights"]:
        y = to_y(h["z_mm"])
        style = "interface" if h["is_interface"] else ("frozen" if h["manual_group"] else "movable")
        d.line((31, y), (70, y), ls=kind[style], lw=0.96)
        d.text(74, y, height_label(h["plane_id"]), 9, "left")
        d.text(100, y, z_text(h["z_mm"]), 9.25)

    # Offset arrows show the XZ orientation while the z stack retains true spacing.
    d.arrow((19, 78), (19, 60))
    d.text(19, 55, "Z", 10)
    d.arrow((31, 231), (53, 231))
    d.text(57, 231, "X", 10)
    d.text(35, 60, "上表面  +0.650", 9, "left")
    d.text(66, 231, "下表面", 9, "left")
    d.text(100, 231, "−0.350", 9)

    d.text(151, 71, "E3 家族允许高度", 12)
    rows = [["家族", "高度标识"]] + [[f, "、".join(height_label(p) for p in planes)]
                                      for f, planes in data["families"].items()]
    table(d, [117, 141, 192], list(range(82, 174, 13)), rows, fs=9.75)
    d.text(119, 182, "相邻高度间距 50 μm", 10.2, "left")
    d.text(119, 191, "上下表面各留 25 μm", 10.2, "left")
    d.text(119, 200, "高度标识按实际 z 排列", 10.2, "left")
    for y, style, label in (
        (237, "frozen", "预设 U 形线路占用的主体高度"),
        (244, "movable", "可动线路所用主体高度"),
        (251, "interface", "可布线的接口高度"),
    ):
        d.line((22, y), (36, y), lw=0.95, ls=kind[style])
        d.text(40, y, label, 9.75, "left")
    d.text(119, 233, "18 个主体高度及 2 个接口高度", 9.6, "left")
    d.text(119, 242, "8 个高度分配给 368 条预设线路", 9.6, "left")
    d.text(119, 251, "12 个高度供 656 条可动线路分组", 9.6, "left")


def route_path(d, primitives, transform):
    vertices = [transform(primitives[0]["p0"])]
    codes = [MplPath.MOVETO]
    for p in primitives:
        if p["kind"] == "line":
            vertices.append(transform(p["p1"]))
            codes.append(MplPath.LINETO)
        else:
            for controls in arc_cubics(p["center"], p["radius"], p["start_angle"], p["sweep"]):
                vertices.extend(map(transform, controls))
                codes.extend([MplPath.CURVE4] * 3)
    d.path(vertices, codes, lw=0.23)


def draw10(d, data):
    sample = data["experiments"]
    d.text(105, 63, f"物理高度 L7（z = {z_text(sample['E1']['z_mm'])} mm）", 13)
    w, y0 = 73, 86
    for x0, code, caption in [(23, "E1", "（a）E1  确定性分组"),
                             (116, "E3", "（b）E3  模拟退火分组")]:
        e = sample[code]

        def trans(p):
            return x0 + p[0] * w / 150, y0 + (150 - p[1]) * w / 150

        d.text(x0 + w / 2, 76, caption, 12)
        d.rect(x0, y0, w, w, lw=0.75)
        for value in (0, 50, 100, 150):
            px, py = trans((value, value))
            d.line((px, y0 + w), (px, y0 + w + 1.8), lw=0.65)
            d.line((x0, py), (x0 - 1.8, py), lw=0.65)
            d.text(px, y0 + w + 5, str(value), 9)
            d.text(x0 - 3, py, str(value), 9, "right")
        d.text(x0 - 9.5, y0 + w / 2, "Y / mm", 9.25, rotation=90)
        d.text(x0 + w / 2, y0 + w + 11, "X / mm", 9.25)
        for route in e["paths"].values():
            for part in route:
                route_path(d, part, trans)
        points = [trans((marker["x_mm"], marker["y_mm"])) for marker in e["events"]]
        xx, yy = zip(*points)
        d.ax.scatter(xx, yy, s=1.44, marker="o", facecolor=BLACK, edgecolor="none", zorder=5)
        d.text(x0 + w / 2, 183,
               f"L7 同高交叉 {e['plane_crossings']} 次（{e['plane_route_count']} 条线路）", 11.25)
    d.dot(67, 194, r=0.42)
    d.text(72, 194, "实际同高交叉事件的位置", 10.25, "left")
    keys = ["intragroup_chords", "crossings_all_heights", "assignment_rows"]
    labels = ["同组端口弦冲突边数", "实际同高交叉事件数", "布通线路数"]
    rows = [["全部高度统计", "E1", "E3"]] + [
        [label, sample["E1"][key], sample["E3"][key]] for key, label in zip(keys, labels)
    ]
    table(d, [35, 111, 143, 175], [204, 214, 224, 234, 244], rows, 10.75)
    d.text(105, 253, "分配顺序  E1 按端口，E3 按线路编号", 10.1)


def review_outputs(font):
    combined = OUT / "说明书附图_10图_草稿.pdf"
    overview = Image.new("RGB", (1800, 1040), WHITE)
    pen = ImageDraw.Draw(overview)
    from PIL import ImageFont
    title_font = ImageFont.truetype(str(font), 21)
    document = pymupdf.open()
    svg_namespace = '{http://www.w3.org/2000/svg}'
    from xml.etree import ElementTree as ET

    for n in range(1, 11):
        tag = f"图{n:02d}"
        svg = ET.parse(OUT / "svg" / f"{tag}.svg").getroot()
        assert list(svg.iter(f"{svg_namespace}text")) and not list(svg.iter(f"{svg_namespace}image"))
        with pymupdf.open(OUT / "pdf" / f"{tag}.pdf") as raw:
            assert len(raw) == 1 and not raw[0].get_images()
            document.insert_pdf(raw)
        with Image.open(OUT / "png" / f"{tag}.png") as page:
            # Trim only the blank page margins for the review sheet.
            from PIL import ImageChops
            box = ImageChops.difference(page.convert("RGB"), Image.new("RGB", page.size, WHITE)).getbbox()
            card = page.crop(box)
            card.thumbnail((320, 448), Image.Resampling.LANCZOS)
            col, row = (n - 1) % 5, (n - 1) // 5
            left, top = col * 360, row * 520
            pen.rectangle((left + 8, top + 8, left + 351, top + 506), outline=BLACK, width=1)
            pen.text((left + 180, top + 30), FIGURE_TITLES[n - 1], fill=BLACK,
                     font=title_font, anchor="mm")
            overview.paste(card, (left + (360 - card.width) // 2, top + 49 + (448 - card.height) // 2))

    document.set_metadata({"title": "说明书附图（10 图草稿）", "subject": "三维光波导多高度优化布线方法"})
    document.set_toc([[1, f"图{n}  {title}", n] for n, title in enumerate(FIGURE_TITLES, 1)])
    document.save(combined, deflate=True, garbage=4)
    document.close()
    overview.save(OUT / "10图预览总览.png")
    with pymupdf.open(combined) as final:
        assert final.page_count == 10
        for n, page in enumerate(final, 1):
            assert abs(page.rect.width - 595.276) < 0.1 and abs(page.rect.height - 841.890) < 0.1
            words = page.get_text()
            assert f"图{n}\n" in words and "说明书附图" in words
            assert "\ufffd" not in words and len(page.get_drawings()) > 0 and not page.get_images()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default_font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc"
    parser.add_argument("--font", type=Path, default=default_font, help="Path to a Chinese TrueType font")
    args = parser.parse_args()
    setup_font(args.font)
    data = json.loads((HERE / "绘图数据.json").read_text(encoding="utf-8"))
    for ext in ("svg", "pdf", "png"):
        (OUT / ext).mkdir(exist_ok=True)
    with warnings.catch_warnings():
        warnings.filterwarnings("error", message="Glyph .* missing from font")
        for i, draw in enumerate([draw1, draw2, draw3, draw4, draw5, draw6, draw7, draw8, draw9, draw10], 1):
            d = Drawing(i)
            draw(d, data)
            tag = f"图{i:02d}"
            for ext in ("svg", "pdf"):
                d.fig.savefig(OUT / ext / f"{tag}.{ext}")
            plt.close(d.fig)
            # Render the actual delivered PDF rather than the intermediate canvas.
            with pymupdf.open(OUT / "pdf" / f"{tag}.pdf") as pdf:
                pdf[0].get_pixmap(dpi=200, alpha=False).save(OUT / "png" / f"{tag}.png")
    review_outputs(args.font)


if __name__ == "__main__":
    main()
