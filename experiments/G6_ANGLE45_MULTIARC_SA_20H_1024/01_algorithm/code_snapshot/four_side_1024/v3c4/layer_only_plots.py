"""Per-layer true-3D plots of the existing V4-C4 crossing-lift result.

No routing is re-run: the figures are rendered directly from the saved
``routes_l3d.json`` / ``layer_stack.json`` of
``outputs/four_side_1024_v4_c4_crossing_lift``.

A route is shown in a layer figure when **at least one of its flat parts lies on
that layer**; the whole 3D route (all flat + all transition parts) is then drawn.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

XLIM = (-5.0, 155.0)
YLIM = (-5.0, 155.0)
ZLIM = (-0.1, 2.7)
VIEW = dict(elev=26, azim=-58)
FIGSIZE = (12.0, 11.0)
OUT_ROOT = 'outputs/four_side_1024_v4_c4_crossing_lift'
SUB_DIR = 'layer_only_plots'


def _read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _style_map(stack_payload):
    style = {0.0: ('#1f6fd6', 'L1-z1  z=0.0 mm'),
             0.5: ('#e07b1a', 'L1-z2  z=0.5 mm')}
    palette = {2: '#2f9e44', 3: '#7048e8', 4: '#e03131', 5: '#0c8599'}
    for layer_id, layer in stack_payload['layers'].items():
        layer_id = int(layer_id)
        if layer_id == 1:
            continue
        z = round(float(layer['physical_z_mm']), 6)
        style[z] = (palette[layer_id], f'L{layer_id}  z={z:g} mm')
    return style


def _layer_specs(stack_payload):
    layers = stack_payload['layers']
    specs = [
        dict(key='L1_z1', title='L1-z1', name='接口层第一排 / row1',
             layer_id=1, z_mm=0.0),
        dict(key='L1_z2', title='L1-z2', name='接口层第二排 / row2',
             layer_id=1, z_mm=0.5),
    ]
    for layer_id in (2, 3, 4, 5):
        z = round(float(layers[str(layer_id)]['physical_z_mm']), 6)
        specs.append(dict(key=f'L{layer_id}', title=f'L{layer_id}',
                          name=f'布线层 L{layer_id}', layer_id=layer_id,
                          z_mm=z))
    return specs


def _select_routes(routed_records, spec):
    layer_id = int(spec['layer_id'])
    z_wanted = spec.get('z_mm')
    selected = []
    for record in routed_records:
        keep = False
        for part in record['parts']:
            if part['kind'] != 'flat' or int(part['layer_id']) != layer_id:
                continue
            if z_wanted is not None and abs(float(part['z_mm']) - z_wanted) > 1e-9:
                continue
            keep = True
            break
        if keep:
            selected.append(record)
    return selected


def _draw_route(ax, record, style, linewidth_flat=0.55, alpha_flat=0.8):
    from .lift_cross_run import _part_samples

    for part in record['parts']:
        points = _part_samples(part)
        if len(points) == 0:
            continue
        if part['kind'] == 'flat':
            z = round(float(part['z_mm']), 6)
            color = style.get(z, ('#444444', ''))[0]
            ax.plot(points[:, 0], points[:, 1], points[:, 2], color=color,
                    linewidth=linewidth_flat, alpha=alpha_flat,
                    solid_capstyle='round')
        else:
            ax.plot(points[:, 0], points[:, 1], points[:, 2], color='#7a7a7a',
                    linewidth=max(linewidth_flat, 0.65), alpha=0.7,
                    solid_capstyle='round')


def _decorate(ax, title=None, layer_name=None, height_text=None, count_text=None,
              title_fontsize=12):
    ax.set_xlim(*XLIM)
    ax.set_ylim(*YLIM)
    ax.set_zlim(*ZLIM)
    ax.set_xlabel('x (mm)')
    ax.set_ylabel('y (mm)')
    ax.set_zlabel('z (mm)')
    ax.view_init(**VIEW)
    ax.set_box_aspect((1.0, 1.0, 0.62))
    ax.grid(True)
    lines = []
    if title:
        lines.append(title)
    if layer_name:
        lines.append(layer_name)
    if height_text:
        lines.append(height_text)
    if count_text:
        lines.append(count_text)
    if lines:
        ax.set_title('\n'.join(lines), fontsize=title_fontsize, pad=12)


def _save(fig, png_path):
    png_path = Path(png_path)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_path, dpi=200, bbox_inches='tight')
    fig.savefig(png_path.with_suffix('.svg'), bbox_inches='tight')
    plt.close(fig)


def _legend_figure(style, path):
    fig, ax = plt.subplots(figsize=(10.5, 7.0))
    ax.axis('off')
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.text(0.5, 0.95, 'V4-C4 交叉规避式三维抬升 — 颜色与层高对应关系',
            ha='center', va='center', fontsize=15, fontweight='bold')
    ax.text(0.5, 0.885, '（每张单层图使用完全相同的颜色/坐标范围/视角）',
            ha='center', va='center', fontsize=10, color='#555555')
    ordered = [0.0, 0.5] + sorted(z for z in style if z not in (0.0, 0.5))
    y = 0.78
    for z in ordered:
        color, label = style[z]
        ax.plot([0.12, 0.30], [y, y], color=color, linewidth=6,
                solid_capstyle='round')
        ax.text(0.34, y, label, va='center', fontsize=13)
        ax.text(0.72, y, f'layer flat z = {z:g} mm', va='center',
                fontsize=11, color='#444444')
        y -= 0.105
    ax.plot([0.12, 0.30], [y, y], color='#7a7a7a', linewidth=4)
    ax.text(0.34, y, '升降过渡 S 曲线（R=15 mm，只允许在直线段上）',
            va='center', fontsize=11)
    ax.text(0.5, 0.045, '数据来源：routes_l3d.json（1020/1024 布通，'
                        '255/256 完整 C4 四元组）',
            ha='center', va='center', fontsize=9, color='#555555')
    _save(fig, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=None)
    parser.add_argument('--out', type=Path, default=None)
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parents[2]
    root = Path(args.root or (repo / OUT_ROOT))
    out_dir = Path(args.out or (root / SUB_DIR))
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = _read_json(root / 'routes_l3d.json')
    stack_payload = _read_json(root / 'layer_stack.json')
    routed = [record for record in payload['routes']
              if record.get('status') == 'routed']
    style = _style_map(stack_payload)
    specs = _layer_specs(stack_payload)

    counts = {}
    for spec in specs:
        selected = _select_routes(routed, spec)
        counts[spec['key']] = len(selected)
        fig = plt.figure(figsize=FIGSIZE)
        ax = fig.add_subplot(111, projection='3d')
        for record in selected:
            _draw_route(ax, record, style)
        if not selected:
            ax.text2D(0.5, 0.5, '0 routes\n（该层没有任何波导）',
                      transform=ax.transAxes, ha='center', va='center',
                      fontsize=20, color='#888888')
        _decorate(
            ax,
            title=f'图名：{spec["key"]}_3d_only',
            layer_name=f'层：{spec["title"]}（{spec["name"]}）',
            height_text=f'物理高度：z = {spec["z_mm"]:g} mm',
            count_text=f'显示波导数量：{len(selected)} routes'
                       '（每条显示完整 3D 路线）',
            title_fontsize=11)
        _save(fig, out_dir / f'{spec["key"]}_3d_only.png')
        print(f'{spec["key"]}: {len(selected)} routes')

    # all layers together
    fig = plt.figure(figsize=FIGSIZE)
    ax = fig.add_subplot(111, projection='3d')
    for record in routed:
        _draw_route(ax, record, style, linewidth_flat=0.5, alpha_flat=0.75)
    _decorate(ax, title='图名：all_layers_3d_full',
              layer_name='层：L1-z1 / L1-z2 / L2 / L3 / L4 / L5（全部）',
              height_text='物理高度：z = 0.0 / 0.5 / '
                          + ' / '.join(f'{round(float(stack_payload["layers"][str(layer)]["physical_z_mm"]), 6):g}'
                                       for layer in (2, 3, 4, 5)) + ' mm',
              count_text=f'显示波导数量：{len(routed)} routes（全部三维路线）',
              title_fontsize=11)
    _save(fig, out_dir / 'all_layers_3d_full.png')
    print(f'all_layers_3d_full: {len(routed)} routes')

    # legend only
    _legend_figure(style, out_dir / 'legend_only.png')
    print('legend_only: color/height legend')

    _write_json = (out_dir / 'layer_plot_counts.json')
    _write_json.write_text(json.dumps(
        dict(counts=counts, total_routed=len(routed),
             layer_heights_mm={str(layer): float(
                 stack_payload['layers'][str(layer)]['physical_z_mm'])
                 for layer in (2, 3, 4, 5)},
             note='single-layer figures show every route having at least one '
                  'flat part on that layer, drawn as its complete 3D route'),
        ensure_ascii=False, indent=1), encoding='utf-8')
    print('counts:', counts)
    print('written to', out_dir)
    return counts


if __name__ == '__main__':
    main()
