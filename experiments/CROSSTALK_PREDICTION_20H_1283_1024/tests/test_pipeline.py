"""Numerical and data-consistency checks for the crosstalk prediction pipeline.

Run with:  python -m pytest tests -q     (or)     python tests/test_pipeline.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from src.config import BEST_VALID, CONFIG
from src.dataio import TOTAL_LENGTH_MM, load_dataset
from src.lengths import length_table, summary
from src.modes import effective_index_model, solve_modes


def test_route_count_and_hash():
    ds = load_dataset(BEST_VALID)
    assert len(ds.routes) == 1024
    assert len({r.route_id for r in ds.routes}) == 1024
    assert ds.sha_check["routes_l3d.json"]["ok"]


def test_total_length():
    ds = load_dataset(BEST_VALID)
    summ = summary(length_table(ds))
    assert abs(summ["total_length_mm"] - TOTAL_LENGTH_MM) < 1e-4
    assert summ["all_decompositions_exact"]


def test_crossing_count():
    ds = load_dataset(BEST_VALID)
    assert ds.crossing_stats["totals"]["crossings"] == 1283
    assert ds.crossing_stats["totals"]["crossing_pairs"] == 1221


def test_mode_normalisation_and_count():
    opt = CONFIG["optics"]["reference"]
    sol = solve_modes(opt)
    g = sol.guided()
    assert g.n_guided >= 1
    for i in range(len(g.n_eff)):
        power = float(np.sum(g.fields[i] ** 2)) * g.grid_um ** 2
        assert abs(power - 1.0) < 1e-6
    assert g.n_guided == 3          # multimode at 9x9 um, dn=0.0065, 1310 nm


def test_eim_close_to_full_scalar():
    opt = CONFIG["optics"]["reference"]
    sol = solve_modes(opt).guided()
    eim = effective_index_model(opt)
    assert abs(eim.n_eff - float(sol.n_eff[0])) / float(sol.n_eff[0]) < 5e-3


def test_energy_conservation(tmp_path=None):
    opt_path = ROOT / "outputs" / "optical" / "crosstalk_matrix_linear.npy"
    if not opt_path.exists():
        return
    T = np.load(opt_path)
    assert T.shape == (1024, 1024)
    assert np.all(T >= 0.0)
    assert float(T.sum(axis=0).max()) <= 1.0 + 1e-9


def test_diagonal_is_propagation_loss():
    opt_path = ROOT / "outputs" / "optical" / "crosstalk_matrix_linear.npy"
    loss_path = ROOT / "outputs" / "geometry" / "propagation_loss.csv"
    stat_path = ROOT / "outputs" / "optical" / "crosstalk_per_route.csv"
    if not (opt_path.exists() and loss_path.exists() and stat_path.exists()):
        return
    import pandas as pd
    T = np.load(opt_path)
    df = pd.read_csv(loss_path)
    st = pd.read_csv(stat_path)
    p = CONFIG["crossing_model"]["resolution_floor"]
    expected = (10 ** (-df.loss_base_db.to_numpy() / 10.0)
                * (1.0 - p) ** st.n_crossings.to_numpy())
    np.testing.assert_allclose(np.diag(T), expected, rtol=1e-9)


def main() -> int:
    tests = [test_route_count_and_hash, test_total_length, test_crossing_count,
             test_mode_normalisation_and_count, test_eim_close_to_full_scalar,
             test_energy_conservation, test_diagonal_is_propagation_loss]
    ok = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
            ok += 1
        except Exception as exc:
            print(f"FAIL {t.__name__}: {exc}")
    print(f"{ok}/{len(tests)} passed")
    return 0 if ok == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
