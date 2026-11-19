import os
p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'make_report.py')
s = open(p, encoding='utf-8').read()
s = s.replace("r['kappa_cmt_mm_inv']", "r['kappa_mm_inv']")
open(p, 'w', encoding='utf-8').write(s)
print('patched make_report.py key names')
