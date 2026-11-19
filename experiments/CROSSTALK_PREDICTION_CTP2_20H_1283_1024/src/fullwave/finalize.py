"""Final packaging (wrap-up): produce validation CSVs under NEW names and the
final fullwave_report.md, WITHOUT touching the already-frozen
outputs/fullwave/fdtd2d_convergence.csv (lead instruction)."""
import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(HERE, '..', '..'))
CACHE = os.path.join(BASE, 'cache', 'fullwave')
OUT = os.path.join(BASE, 'outputs', 'fullwave')
FIGS = os.path.join(OUT, 'figs')
sys.path.insert(0, HERE)
import fwlib as fw
import make_outputs as mo
import make_report as mr

# never overwrite the frozen CSVs while generating the report
mo.write_csv = lambda *a, **k: None
mr.mo.write_csv = lambda *a, **k: None


def raw_write(path, rows, cols=None):
    if not rows:
        print('  (skip empty)', path)
        return
    if cols is None:
        cols = list(rows[0].keys())
    with open(path, 'w', encoding='utf-8') as f:
        f.write(','.join(cols) + '\n')
        for r in rows:
            vals = []
            for c in cols:
                v = r.get(c, '')
                if isinstance(v, float):
                    vals.append('%.10g' % v)
                else:
                    vals.append(str(v))
            f.write(','.join(vals) + '\n')
    print('  wrote', path, '(%d rows)' % len(rows))


def wait_for(fn, timeout=420):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if os.path.exists(fn):
            # size must be stable (writer closed)
            s1 = os.path.getsize(fn); time.sleep(1.5)
            try:
                s2 = os.path.getsize(fn)
            except OSError:
                continue
            if s1 == s2 and s1 > 0:
                return True
        time.sleep(5)
    return False


def main():
    print('--- finalize ---')
    print('waiting for validation_2d.json ...')
    have_val = wait_for(os.path.join(CACHE, 'validation_2d.json'), timeout=420)
    print('validation available:', have_val)
    val = mo.load(os.path.join(CACHE, 'validation_2d.json'), {}) if have_val else {}
    # ---- validation CSV (new file name) -----------------------------------
    if have_val:
        rows = mo.collect_validation()
        raw_write(os.path.join(OUT, 'fdtd2d_validation.csv'), rows)
        conv = []
        sol = fw.slab_analytic(fw.N_SLAB, fw.N_CLAD, fw.W_SLAB)
        for r in val.get('discrete', []):
            conv.append(dict(kind='straight_eigenmode', dx_um=r['dx_um'],
                             order=r['order'], quantity='n_eff', value=r['neff'],
                             reference=sol['neff'], error=r['err'],
                             gamma_um=r['gamma_um'],
                             gamma_err_pct=r['gamma_err_pct'], note=''))
        for r in val.get('fdtd', []):
            conv.append(dict(kind='straight_FDTD', dx_um=r['dx_um'],
                             order=r['order'], quantity='n_eff',
                             value=r['n_eff_fdtd'],
                             reference=r['n_eff_analytic'],
                             error=r['n_eff_err'], gamma_um='',
                             gamma_err_pct='',
                             note='S=%.2f t_abs=%.0f A=%.0f' % (r['S'], r['t_abs_um'],
                                                                r['A_abs'])))
        cross = mo.collect_crossing()
        byang = {}
        for r in cross:
            byang.setdefault(r['theta_deg'], []).append(r)
        for th, rs in byang.items():
            if len(rs) < 2:
                continue
            rs = sorted(rs, key=lambda r: r['dx_um'])
            for r in rs:
                conv.append(dict(kind='crossing', dx_um=r['dx_um'],
                                 order=r['order'],
                                 quantity='XT_dB(%.0fdeg)' % th,
                                 value=r['T_cross_db'],
                                 reference=r.get('bpm_xt_db', ''),
                                 error=(r['T_cross_db'] - r['bpm_xt_db']
                                        if r.get('bpm_xt_db', '') != '' else ''),
                                 gamma_um='', gamma_err_pct='',
                                 note='domain %s um' % r['domain_um']))
        raw_write(os.path.join(OUT, 'fdtd2d_convergence_v2.csv'), conv,
                  cols=['kind', 'dx_um', 'order', 'quantity', 'value', 'reference',
                        'error', 'gamma_um', 'gamma_err_pct', 'note'])
    # ---- figures ----------------------------------------------------------
    try:
        mo.fig_crossing_maps(['theta5_dx0.05_o4_sep30', 'theta20_dx0.05_o4_sep40'],
                             os.path.join(FIGS, 'fig_crossing_maps.png'))
        mo.fig_convergence(os.path.join(FIGS, 'fig_convergence.png'))
        coupler, cmt = mo.collect_coupler()
        mo.fig_coupler(coupler, cmt, os.path.join(FIGS, 'fig_coupler.png'))
        mo.fig_mode_launch(os.path.join(FIGS, 'fig_mode_launch.png'))
    except Exception as e:
        print('figure error (ignored):', e)
    # ---- final report -----------------------------------------------------
    mr.main()
    # quick sanity print of the key numbers
    print('--- key numbers ---')
    cross = mo.collect_crossing()
    finest = {}
    for r in cross:
        finest.setdefault(r['theta_deg'], []).append(r)
    for th in sorted(finest):
        rs = sorted(finest[th], key=lambda r: r['dx_um'])
        print('theta=%3g dx=%.2f XT=%.2f dB T_th=%.4f T_rad=%.4f'
              % (th, rs[0]['dx_um'], rs[0]['T_cross_db'], rs[0]['T_through'],
                 max(rs[0]['T_radiation'], 0.0)))
    st = mo.load(os.path.join(CACHE, '3d_straight_dx0.12_o6.json'))
    if st:
        print('3D straight: n_eff FDTD=%.8f discrete=%.8f (rel diff %.1e), '
              'target=1.50455547' % (st['n_eff_fdtd'], st['n_eff_discrete'],
                                     abs(st['n_eff_err_vs_discrete']) / st['n_eff_discrete']))
    print('done')


if __name__ == '__main__':
    main()
