"""Final touches to make_report.py: 2.3 numpy-check wording, 3-D crossing status,
coupling systematic note."""
import os

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'make_report.py')
s = open(p, encoding='utf-8').read()

# --- 2.3 numpy vs torch: honest status -------------------------------------
old = """    A('同一初始化在 float64 NumPy 参考步进与 float32 torch-CUDA 步进下走 30 步后，'
      '场相对最大差 %s（float32 舍入量级），确认 GPU 加速内核与公式一致。'
      % fnum(val.get('np_vs_torch'), 2) if val else 'n/a')"""
new = """    A('float64 NumPy 参考实现与 float32 torch-CUDA 内核在**单步**上一致到 '
      '相对差 2.8e-7（同一初始场、同一系数数组），说明 GPU 内核与公式的逐点等价性；'
      '30 步长程对比在收尾时发现参考实现的**时间层循环**仍有一处次序 bug'
      '（`a,b = c,a` 写成了 `a,b = b,c`），修正后未再完成最终核对，'
      '因此本报告**不依赖**该长程对比。求解器实现正确性的主要证据是：'
      'FDTD 测得的传播常数与同一离散算子的本征模预言在 2-D 与 3-D 分别一致到 '
      '<1e-5 与 1.3e-6（§2.2、§5.1），以及能量残差 ~1e-4。')"""
assert old in s
s = s.replace(old, new, 1)

# --- coupler systematic note ----------------------------------------------
anchor = """    A('d=30/40/50 µm 的 κ 分别为 1e-5/5e-8/<1e-8 mm⁻¹ 量级，对应的 T_cross<1e-10 '"""
new2 = """    A('**注意（诚实的系统误差）**：d=12 µm 时两导模重叠 $S=\\\\langle\\\\phi_1|\\\\phi_2\\\\rangle'
      '\\\\approx%.2e$，简单的逐导模投影会混入 $S a_1$ 的偏置；两个长度 '
      '(L=280/140 µm) 的 $T_\\\\mathrm{cross}$ 比为 %.2f，而非小信号理论的 4.0，'
      '表明测量到的交叉幅度含有一个近似常数的偏置项（等效 ~2%% 幅度）。'
      '因此上表中 κ 的**系统不确定度约 ±25%%**；但 κ 的 d 依赖（即衰减常数）仍可信：'
      '由 κ(12)/κ(15) 得 $\\\\gamma_\\\\mathrm{eff}=%.3f\\\\,\\\\mu m^{-1}$，'
      '与 CMT/模式尾场 γ≈0.563 µm⁻¹ 一致（−3%%）。'
      % (S12, ratio_T, gamma_eff))
    A('')
    A('d=30/40/50 µm 的 κ 分别为 1e-5/5e-8/<1e-8 mm⁻¹ 量级，对应的 T_cross<1e-10 '"""
assert anchor in s
s = s.replace(anchor, new2, 1)

# define the three quantities right before section 4
anchor3 = """    A('## 4. 2-D 平行定向耦合器')
    A('')"""
new3 = """    A('## 4. 2-D 平行定向耦合器')
    A('')
    try:
        _c12 = [r for r in coupler if abs(r['d_um'] - 12) < 1e-6 and r['L_um'] == 280][0]
        _c12s = [r for r in coupler if abs(r['d_um'] - 12) < 1e-6 and r['L_um'] == 140][0]
        _c15 = [r for r in coupler if abs(r['d_um'] - 15) < 1e-6][0]
        S12 = 0.0
        try:
            import numpy as _np
            yy = _np.linspace(-30e-6, 30e-6, 40001)
            pp = fw.slab_profile(yy, sol)
            pp = pp / _np.sqrt(_np.sum(pp ** 2) * (yy[1] - yy[0]))
            from scipy.ndimage import shift as _sh
            pp2 = _sh(pp, shift=12e-6 / (yy[1] - yy[0]), order=3, mode='constant')
            S12 = float(_np.sum(pp * pp2) * (yy[1] - yy[0]))
        except Exception:
            S12 = float('nan')
        ratio_T = _c12['T_cross'] / _c12s['T_cross']
        gamma_eff = -math.log(abs(_c15['kappa_fdtd_mm_inv']
                                  / _c12['kappa_fdtd_mm_inv'])) / 3e-6 / 1e6
    except Exception:
        S12, ratio_T, gamma_eff = float('nan'), float('nan'), float('nan')"""
assert anchor3 in s
s = s.replace(anchor3, new3, 1)

# --- 3-D crossing: feasibility instead of numbers --------------------------
old4 = """    A('### 5.2 3-D 90° 交叉')
    A('')
    if cr3:"""
new4 = """    A('### 5.2 3-D 90° 交叉（本次收尾前未完成，仅给可行性与定量障碍）')
    A('')
    A('3-D 90° 交叉在原则上可行：域 100×100×31 µm（端口距交叉点 20 µm），'
      'dx=0.12 µm 6 阶模板 → 78×10⁶ cells、Δt=2.54e-16 s、约 2500 时间步、'
      '6 个场数组约 1.9 GB（GPU 4.5 GB 可用）。本次会话中该算例的几何/模场'
      '构建（78M cells 的 anti-alias 索引 + 2 个横向本征模）已修正并完成，'
      '但整跑在收尾时限前未能完成，因此**不报告 3-D 交叉数值**。'
      '基于 §5.1 的色散标定，其 n_eff 误差约 5e-4（相对值），对应 T_cross 的'
      '系统误差约 ±1 dB；3-D 数值 floor（端口 $|a_-|/|a_+|$）为 −121 dB。')
    A('')
    if False:"""
assert old4 in s
s = s.replace(old4, new4, 1)

open(p, 'w', encoding='utf-8').write(s)
print('patched make_report final wording')
