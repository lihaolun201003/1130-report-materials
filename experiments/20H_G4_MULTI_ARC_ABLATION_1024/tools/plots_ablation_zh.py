# -*- coding: utf-8 -*-
"""Chinese patent-style L6 ON/OFF comparison (independent entry point).

This script does **not** change the English figure pipeline.  It reads the same
real experiment states as ``plots_ablation.py compare-layers`` and redraws only
the L6 physical height (plane 6, z = -0.125 mm) with Chinese annotations:

* left  = 启用组合圆弧  (the ON arm, run ``c1_on_20261116``, 2093 crossings)
* right = 禁用组合圆弧  (the OFF arm, run ``c1_off_20261130``, 4052 crossings)

All geometry, colours, crossing markers and statistics come from the original
``routes_l3d.json`` / ``crossing_stats.json``; the two panels share the same
150 x 150 mm limits, scale and equal aspect.  The authoritative L6 counts are
verified against the task statement (108 events / 99 pairs vs 399 / 276) and
written to ``data_check.json`` next to the figures.

Output: PNG (300 dpi) + SVG under ``<experiment>/patent_zh/``.

Usage::

    .venv\\Scripts\\python.exe experiments\\20H_G4_MULTI_ARC_ABLATION_FINAL_1024\\
        tools\\plots_ablation_zh.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT.parents[3]
EXP1_TOOLS = (PROJECT_ROOT / 'experiments'
              / '20H_G4_MULTI_ARC_ABLATION_1024' / 'tools')
for extra in (str(PROJECT_ROOT), str(EXP1_TOOLS), str(SCRIPT.parent)):
    if extra not in sys.path:
        sys.path.insert(0, extra)

# importing the frozen English pipeline installs the 20-height profile
import plots_ablation as PA  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.font_manager import FontProperties, findfont  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from four_side_1024.fanout1024.coldstart20 import plot_layers20 as L20  # noqa: E402
from four_side_1024.fanout1024.reheight21 import plots21 as P  # noqa: E402

EXP_ROOT = PROJECT_ROOT / 'experiments' / '20H_G4_MULTI_ARC_ABLATION_FINAL_1024'
DEFAULT_A = EXP_ROOT / 'runs' / 'on' / 'c1_on_20261116' / 'best_valid'
DEFAULT_B = EXP_ROOT / 'runs' / 'off' / 'c1_off_20261130' / 'best_valid'
DEFAULT_OUT = EXP_ROOT / 'patent_zh'
PLANE_LABEL = 'L6'

# Chinese typography: SimSun for body text, SimHei for titles (both shipped
# with Windows and present in the matplotlib font list used by this project)
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['SimSun', 'SimHei', 'Microsoft YaHei',
                                   'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['svg.fonttype'] = 'path'   # embedded glyph outlines -> no tofu


def _font(family):
    try:
        path = findfont(FontProperties(family=family), fallback_to_default=False)
        return FontProperties(fname=path)
    except Exception:                                        # noqa: BLE001
        return FontProperties(family=family)


BODY_FONT = _font('SimSun')
TITLE_FONT = _font('SimHei')


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def stats_path(state_dir):
    """The authoritative crossing_stats.json of a best_valid state."""
    state_dir = Path(state_dir)
    for candidate in (state_dir / 'crossing_stats.json',
                      state_dir.parent / 'crossing_stats.json'):
        if candidate.is_file():
            return candidate
    raise SystemExit('crossing_stats.json not found for %s' % state_dir)


def find_l6(state):
    for plane in state['model'].planes:
        if str(plane['label']) == PLANE_LABEL:
            return plane
    raise SystemExit('L6 plane not found in the 20H model')


def panel(ax, state, info, title):
    pid = int(info['plane_id'])
    data = state['ds']['geometry'].get(pid) or dict(bodies=[], leads=[])
    P._draw_leads(ax, data.get('leads') or [])
    P._draw_entries(ax, data.get('bodies') or [], state['ds']['model'])
    P._draw_crossings(ax, info['crossing_points'])
    P._draw_ports(ax, P._assignment_rows_for_plane(state['ds'], pid))
    P._decorate_board(ax, title, title_fontsize=9.0)
    ax.title.set_fontproperties(TITLE_FONT)
    ax.title.set_color('#111111')
    ax.set_xlabel('x 坐标 (mm)', fontsize=8.2, labelpad=1.5,
                  fontproperties=BODY_FONT)
    ax.set_ylabel('y 坐标 (mm)', fontsize=8.2, labelpad=1.5,
                  fontproperties=BODY_FONT)
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontproperties(BODY_FONT)
        label.set_fontsize(6.4)


def chinese_legend(info):
    handles = [
        Line2D([0], [0], color=P.GROUP_COLORS['Z1-U1'], lw=1.5,
               label='人工 U 组（Z1-U1…Z2-U4）'),
        Line2D([0], [0], color=P.OTHER_COLORS['z1_other'], lw=1.5,
               label='Z1 其余对侧线路'),
        Line2D([0], [0], color=P.OTHER_COLORS['z2_other'], lw=1.5,
               label='Z2 其余相邻侧线路'),
        Line2D([0], [0], color=P.DIRECT_BODY_COLOR, lw=1.5,
               label='接口直连本体（本层布线）'),
    ]
    if info['interface_lead_parts']:
        handles.append(Line2D([0], [0], color=P.LEAD_COLOR, lw=0.9, alpha=0.7,
                              label='冻结接口引出线（其他线路）'))
    handles.append(Line2D([0], [0], color='#333333', marker='o', lw=0,
                          markersize=4.0, label='端口及内向刻度'))
    handles.append(Line2D([0], [0], color=P.CROSSING_COLOR, marker='x', lw=0,
                          markersize=5.2, label='交叉点（真实几何）'))
    for handle in handles:
        handle.set_label(handle.get_label())
    return handles


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--a', default=str(DEFAULT_A),
                        help='ON state (default: c1_on_20261116 best_valid)')
    parser.add_argument('--b', default=str(DEFAULT_B),
                        help='OFF state (default: c1_off_20261130 best_valid)')
    parser.add_argument('--out-dir', default=str(DEFAULT_OUT))
    parser.add_argument('--dpi', type=int, default=300)
    parser.add_argument('--name', default='L6_combo_arc_ON_vs_OFF_zh')
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    inputs_root = out_dir / '_inputs'
    state_a = PA.analyze_state(Path(args.a), inputs_root, label='on_2093')
    state_b = PA.analyze_state(Path(args.b), inputs_root, label='off_4052')
    PA._verify_same_model(state_a, state_b)

    plane = find_l6(state_a)
    pid = int(plane['plane_id'])
    z_mm = float(plane['z_mm'])
    info_a = state_a['per_plane'][pid]
    info_b = state_b['per_plane'][pid]

    checks = {
        'plane_label': PLANE_LABEL,
        'plane_id': pid,
        'z_mm': z_mm,
        'a_events': int(info_a['crossing_count']),
        'a_pairs': int(info_a['crossing_pairs']),
        'a_body_routes': int(info_a['route_count']),
        'b_events': int(info_b['crossing_count']),
        'b_pairs': int(info_b['crossing_pairs']),
        'b_body_routes': int(info_b['route_count']),
    }
    expected = dict(a_events=108, a_pairs=99, a_body_routes=41,
                    b_events=399, b_pairs=276, b_body_routes=44)
    problems = ['%s=%s expected %s' % (key, checks[key], value)
                for key, value in expected.items() if checks[key] != value]
    if problems:
        raise SystemExit('DATA CHECK FAILED (real artifacts disagree with the '
                         'task statement): ' + '; '.join(problems))

    fig = plt.figure(figsize=(14.2, 7.6), facecolor='white')
    ax_a = fig.add_axes([0.045, 0.155, 0.415, 0.655])
    ax_b = fig.add_axes([0.540, 0.155, 0.415, 0.655])
    panel(
        ax_a, state_a, info_a,
        '启用组合圆弧\n物理高度 L6   z = %.3f mm\n'
        '本层布线 %d 条 | 交叉 %d 次 / %d 对'
        % (z_mm, info_a['route_count'], info_a['crossing_count'],
           info_a['crossing_pairs']))
    panel(
        ax_b, state_b, info_b,
        '禁用组合圆弧\n物理高度 L6   z = %.3f mm\n'
        '本层布线 %d 条 | 交叉 %d 次 / %d 对'
        % (z_mm, info_b['route_count'], info_b['crossing_count'],
           info_b['crossing_pairs']))

    fig.suptitle(
        '20 层 1024 通道组合圆弧消融：物理高度 L6 布线对比',
        fontsize=13.0, fontproperties=TITLE_FONT, y=0.985)
    fig.text(0.5, 0.918,
             '左：启用组合圆弧（交叉 %d 次 / %d 对）       '
             '右：禁用组合圆弧（交叉 %d 次 / %d 对）       '
             '差值：%+d 次'
             % (info_a['crossing_count'], info_a['crossing_pairs'],
                info_b['crossing_count'], info_b['crossing_pairs'],
                int(info_b['crossing_count']) - int(info_a['crossing_count'])),
             ha='center', fontsize=9.2, fontproperties=BODY_FONT,
             color='#222222')

    handles = chinese_legend(info_a)
    legend = fig.legend(handles=handles, loc='lower center', ncol=4,
                        fontsize=8.0, frameon=True, framealpha=1.0,
                        edgecolor='#bbbbbb', bbox_to_anchor=(0.5, 0.042))
    for text in legend.get_texts():
        text.set_fontproperties(BODY_FONT)
    fig.text(0.5, 0.012,
             '两图使用同一 150 × 150 mm 板面、同一坐标范围与比例；'
             '红色 × 为真实同层交叉点；数值由原始实验交叉统计读取并核对。',
             ha='center', fontsize=7.2, fontproperties=BODY_FONT,
             color='#444444')

    png = out_dir / (args.name + '.png')
    svg = out_dir / (args.name + '.svg')
    fig.savefig(png, dpi=int(args.dpi), facecolor='white',
                bbox_inches='tight', pad_inches=0.12)
    fig.savefig(svg, format='svg', facecolor='white',
                bbox_inches='tight', pad_inches=0.12)
    plt.close(fig)

    payload = dict(
        schema='20h_l6_multi_arc_compare_zh_v1',
        generated_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
        script=str(SCRIPT),
        command=' '.join(sys.argv),
        a=dict(label='启用组合圆弧', run_dir=str(Path(args.a)),
               routes_sha256=sha256(Path(args.a) / 'routes_l3d.json'),
               crossing_stats=str(stats_path(args.a)),
               crossing_stats_sha256=sha256(stats_path(args.a))),
        b=dict(label='禁用组合圆弧', run_dir=str(Path(args.b)),
               routes_sha256=sha256(Path(args.b) / 'routes_l3d.json'),
               crossing_stats=str(stats_path(args.b)),
               crossing_stats_sha256=sha256(stats_path(args.b))),
        counts=checks,
        expected=expected,
        data_check='PASS',
        output=dict(png=str(png), svg=str(svg),
                    png_sha256=sha256(png), svg_sha256=sha256(svg),
                    dpi=int(args.dpi)),
        labels=dict(
            title='20 层 1024 通道组合圆弧消融：物理高度 L6 布线对比',
            left='启用组合圆弧', right='禁用组合圆弧',
            axis=('x 坐标 (mm)', 'y 坐标 (mm)'),
            legend=[handle.get_label() for handle in handles],
            footer='两图使用同一 150 × 150 mm 板面、同一坐标范围与比例；'
                   '红色 × 为真实同层交叉点；数值由原始实验交叉统计读取并核对。'),
    )
    (out_dir / 'data_check.json').write_text(
        json.dumps(payload, indent=1, ensure_ascii=False) + '\n',
        encoding='utf-8')
    print(json.dumps(dict(counts=checks, png=str(png), svg=str(svg),
                          dpi=args.dpi), ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
