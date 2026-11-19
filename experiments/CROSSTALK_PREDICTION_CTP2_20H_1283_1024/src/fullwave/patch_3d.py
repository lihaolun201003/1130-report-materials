import os
p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'run_3d.py')
s = open(p, encoding='utf-8').read()
old = """def energy_budget(sim, res, name=''):
    P = res['ports']
    om = sim.omega"""
new = """def energy_budget(sim, res, name=''):
    P = res['ports']
    bnd = res['boundary']
    om = sim.omega"""
assert old in s
s = s.replace(old, new, 1)
old2 = """    P_boundary = sum(res['boundary'].values())
    pback = out.get('P_srcback', 0.0)
    out['P_boundary'] = P_boundary
    out['energy_residual'] = (P_boundary - P_in_net - pback) / P_in_net"""
new2 = """    P_boundary = sum(bnd.values())
    out['P_boundary'] = P_boundary
    # the source emits backwards as well; that power leaves through the left
    # boundary (bnd_L).  The energy-balance check is therefore
    #   (everything except bnd_L) == P_in_net
    bnd_L = bnd.get('bnd_L', 0.0)
    out['P_back_emitted_boundary'] = bnd_L
    out['energy_residual'] = (P_boundary - bnd_L - P_in_net) / P_in_net"""
assert old2 in s
s = s.replace(old2, new2, 1)
open(p, 'w', encoding='utf-8').write(s)
print('patched run_3d energy budget')
