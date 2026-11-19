import sys, time, math, json
sys.path.insert(0, r"C:\\Users\\lihao\\Desktop\\Graduation Project\\work\\1130-report-materials\\experiments\\CROSSTALK_PREDICTION_CTP2_20H_1283_1024\src")
import numpy as np
from ctp2.params import REF, OUT_CROSSINGS
from ctp2 import optics as O, bpm as B
def db(x): return 10*math.log10(max(x,1e-300))
eim = O.build_eim(REF)
rows=[]
print("=== V3: 3-D full-vectorised scalar BPM crossing sweep (EIM-free) ===")
for th, dx, dz in [(5.0,0.20,0.5),(7.5,0.20,0.5),(10.0,0.20,0.5),(12.5,0.2,0.5),(15.0,0.2,0.5),(20.0,0.2,0.5),(25.0,0.2,0.5),(30.0,0.2,0.5)]:
    t0=time.time()
    r = B.run_crossing_3d(REF, th, port_separation_um=50.0, dx_um=dx, dy_um=dx, dz_um=dz)
    row = dict(theta_deg=th, T_through=r.T_through, T_cross=r.T_cross,
               T_cross_db=db(r.T_cross), T_radiation=r.T_radiation, energy=r.energy,
               dx_um=dx, dz_um=r.dz_um, nx=r.nx, ny=r.ny, n_steps=r.n_steps,
               port_sep_um=r.port_separation_um, method="bpm3d", seconds=time.time()-t0)
    rows.append(row)
    print("th=%5.1f T_th=%.6f XT=%7.2f dB T_rad=%.5f Etot=%.6f [%.0fs]"%(th,r.T_through,db(r.T_cross),r.T_radiation,r.energy,time.time()-t0))
    json.dump(rows, open(r"C:\\Users\\lihao\\Desktop\\Graduation Project\\work\\1130-report-materials\\experiments\\CROSSTALK_PREDICTION_CTP2_20H_1283_1024\cache\lead\bpm3d_crossing.json","w"), indent=1)
print("done")
