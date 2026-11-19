"""E3: two-waveguide coupling database and the crossing transfer curve."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from src.config import CONFIG, EXPERIMENT_ROOT, parameter_sets, reference_optics
from src.coupling import build_coupling_model, supermode_kappa
from src.crossing import crossing_born, crossing_cmt, solve_crossing
from src.dataio import write_csv, write_json
from src.modes import effective_index_model


def main() -> int:
    t0 = time.time()
    out = EXPERIMENT_ROOT / "outputs" / "optical"
    cache = EXPERIMENT_ROOT / "cache"
    out.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)

    opt = reference_optics()
    model, rows = build_coupling_model(opt, "REF")
    print(f"[E3] kappa model: gamma={model.gamma_per_um:.4f}/um "
          f"d_hi={model.d_hi}um  ({time.time() - t0:.1f}s)")

    # vertical-offset dependence (pure dz, same lateral position)
    dz_rows = []
    for dz in CONFIG["coupling"]["vertical_offset_values_um"]:
        if dz == 0:
            continue
        s = supermode_kappa(opt, float(dz), "y")
        dz_rows.append({
            "parameter_set": "REF", "offset_type": "vertical_dz",
            "dz_um": float(dz), "dx_um": 0.0,
            "kappa_supermode_mm_inv": s["kappa_mm_inv"],
            "delta_n_eff": s["delta_n_eff"],
        })
        print(f"      dz={dz:5.1f}um  kappa={s['kappa_mm_inv']:.4e}/mm")
    for dx in (5.0, 10.0, 15.0, 20.0):
        for dz in (10.0, 20.0, 30.0, 50.0):
            d_eff = float(np.hypot(dx, dz))
            dz_rows.append({
                "parameter_set": "REF", "offset_type": "combined_dx_dz",
                "dz_um": float(dz), "dx_um": float(dx),
                "d_eff_um": d_eff,
                "kappa_model_mm_inv": float(model.kappa(d_eff)),
            })

    # ---------------- crossing curve (local FDFD, reference parameters)
    eim = effective_index_model(opt)
    angles = CONFIG["crossing_model"]["angles_deg"]
    cross_rows = []
    for a in angles:
        t1 = time.time()
        try:
            r = solve_crossing(opt, float(a), eim=eim, d_port_um=10.0,
                               max_unknowns=420_000, pml_um=5.0)
            row = r.as_row()
            row["runtime_s"] = time.time() - t1
            cross_rows.append(row)
            print(f"      crossing {a:5.1f}deg h={r.grid_um:.3f} "
                  f"X={r.T_cross:.3e} ({row['T_cross_db']:.1f} dB) "
                  f"T={r.T_through:.6f}  {row['runtime_s']:.0f}s")
        except Exception as exc:                     # pragma: no cover
            print(f"      crossing {a} failed: {exc}")
        write_json(cache / "crossing_curve_REF.json", cross_rows)

    tab = []
    for row in cross_rows:
        a = row["theta_deg"]
        b = crossing_born(eim, a)
        c = crossing_cmt(opt, a, model, eim.beta2d)
        tab.append({
            "theta_deg": a,
            "T_cross_fdfd": row["T_cross"],
            "T_cross_fdfd_db": row["T_cross_db"],
            "T_through_fdfd": row["T_through"],
            "loss_db_fdfd": row["loss_db"],
            "resolution_limited": int(row["T_cross"] < 1e-7),
            "T_cross_born": b["T_cross"],
            "amplitude_born": b["amplitude"],
            "regime_born": b["regime"],
            "T_cross_cmt": c["T_cross_cmt"],
            "grid_um": row["grid_um"],
            "unknowns": row["unknowns"],
            "n_guided_modes": row["n_guided_modes"],
        })
    write_csv(out / "crossing_transfer_curve.csv", tab)

    # ---------------- parameter-set coupling summary
    pset_rows = []
    for ps in parameter_sets():
        m, _ = build_coupling_model(ps, ps["label"], d_max_um=22.0,
                                    step_um=2.0, validate_overlap=False)
        e = effective_index_model(ps)
        pset_rows.append({
            "parameter_set": ps["label"],
            "wavelength_nm": ps["wavelength_nm"],
            "delta_n": ps["delta_n"],
            "core_width_um": ps["core_width_um"],
            "core_height_um": ps["core_height_um"],
            "profile": ps["profile"],
            "gamma_per_um": m.gamma_per_um,
            "gamma_db_per_um": m.gamma_db_per_um(),
            "kappa_10um_mm_inv": float(m.kappa(10.0)),
            "kappa_15um_mm_inv": float(m.kappa(15.0)),
            "kappa_20um_mm_inv": float(m.kappa(20.0)),
            "kappa_30um_mm_inv": float(m.kappa(30.0)),
            "kappa_50um_mm_inv": float(m.kappa(50.0)),
            "kappa_62um_mm_inv": float(m.kappa(62.0)),
            "eim_n_slab": e.n_slab,
            "eim_n_eff": e.n_eff,
        })
        print(f"      {ps['label']:14s} gamma={m.gamma_per_um:.4f} "
              f"kappa20={m.kappa(20.0):.3e} kappa62={m.kappa(62.0):.3e}")

    write_csv(out / "coupling_coefficients.csv", rows)
    write_csv(out / "coupling_vertical_offsets.csv", dz_rows)
    write_csv(out / "coupling_parameter_sweep.csv", pset_rows)
    write_json(out / "e3_summary.json", {
        "reference_model": {
            "gamma_per_um": model.gamma_per_um,
            "gamma_db_per_um": model.gamma_db_per_um(),
            "d_lo_um": model.d_lo, "d_hi_um": model.d_hi,
            "kappa_floor_mm_inv": model.kappa_floor,
            "n_points_computed": len(model.d_um),
        },
        "crossing_curve": tab,
        "vertical_offsets": dz_rows,
        "parameter_sweep": pset_rows,
        "runtime_seconds": time.time() - t0,
    })
    print(f"[E3] done in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
