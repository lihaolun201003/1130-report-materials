"""Central configuration of the 1024-channel crosstalk prediction study.

Every physical constant used anywhere in the pipeline lives here so that the
emitted ``simulation_config.yaml`` is a complete record of the run.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]           # OpticalWaveguideRouter2D
EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]        # this experiment
BEST_VALID = (PROJECT_ROOT / "experiments" / "COLD_START_20_HEIGHT_1024"
              / "10_best_valid")
REPORTS_SRC = PROJECT_ROOT / "experiments" / "COLD_START_20_HEIGHT_1024" / "12_reports"

CONFIG: dict = {
    "schema": "crosstalk_prediction_config_v1",
    "model_version": "CTP-1.0",
    "experiment": "CROSSTALK_PREDICTION_20H_1283_1024",
    "units": {
        "length": "mm",
        "wavelength": "nm",
        "propagation_loss": "dB/cm",
        "crosstalk": "dB (10*log10 of linear power ratio)",
        "angle": "deg",
    },
    "inputs": {
        "best_valid_dir": str(BEST_VALID),
        "routes_file": "routes_l3d.json",
        "routes_sha256_expected":
            "35d7ebed00339bee21fe0ca47075c9b34008120522a47933a099efacf0b90753",
        "total_length_mm_expected": 156597.221522,
        "crossing_events_expected": 1283,
        "crossing_pairs_expected": 1221,
        "planes_expected": 20,
        "routes_expected": 1024,
        "verify_sha256": True,
    },
    # ---------------------------------------------------------------- optics
    "optics": {
        "reference": {
            "label": "REF",
            "wavelength_nm": 1310.0,
            "n_clad": 1.50,
            "delta_n": 0.0065,
            "core_width_um": 9.0,
            "core_height_um": 9.0,
            "profile": "step",
            "core_shape": "rect",
        },
        "propagation_loss_db_per_cm": 0.05,
        "bend_extra_loss_db": 0.0,
        "min_bend_radius_mm": 15.0,
        "wavelengths_nm": [1310.0, 1550.0],
        "delta_n_values": [0.0045, 0.0065, 0.0080],
        "core_width_um_values": [6.0, 9.0, 12.0],
        "core_height_um_values": [7.0, 9.0, 11.0],
        "profiles": ["step", "graded"],
        "graded_sigma_fraction": 0.5,
        "graded_definition":
            "n(r)=n_clad+delta_n*exp(-ln(2)*(r/r_half)^2) with r_half = "
            "sigma_fraction * core half-width; equivalent-width convention "
            "documented in the report",
    },
    # ------------------------------------------------------------- mode solver
    "mode_solver": {
        "equation": "scalar weak-guidance Helmholtz: lap(psi)+k0^2 n^2 psi = beta^2 psi",
        "boundary": "dirichlet",
        "domain_um": 22.4,
        "grid_um": 0.2,
        "convergence_grids_um": [0.4, 0.28, 0.2, 0.14, 0.1],
        "convergence_domains_um": [16.8, 22.4, 28.0, 39.2],
        "n_modes": 12,
        "shift_offset": 0.0015,
        "eig_tol": 1e-10,
        "max_iter": 20000,
    },
    # ---------------------------------------------------------------- coupling
    "coupling": {
        "method": ["supermode_symmetry", "overlap_integral"],
        "supermodes": True,
        "separation_min_um": 0.0,
        "separation_max_um": 120.0,
        "separation_points": 121,
        "vertical_offset_values_um": [0.0, 10.0, 20.0, 30.0, 40.0, 50.0],
        "wavelengths_nm": [1310.0, 1550.0],
        "kappa_floor_mm_inv": 1e-14,
        "kappa_ceiling_mm_inv": 100.0,
        "interp": "log(kappa) piecewise-linear in d, clamped below floor",
    },
    # ------------------------------------------------------------- interactions
    "interactions": {
        "spatial_cutoff_um": 150.0,
        "optical_cutoff_um": 60.0,
        "fine_step_um": 0.5,
        "coarse_step_um": 4.0,
        "refine_step_um": 0.125,
        "crossing_match_tol_mm": 0.002,
        "min_parallel_length_um": 0.5,
        "angle_bins_deg": [0, 5, 10, 15, 20, 25, 30, 40, 50, 60, 75, 90],
    },
    # -------------------------------------------------------------------- board
    "board": {
        "input_port": "source_endpoint",
        "output_port": "target_endpoint",
        "second_order": True,
        "mode_excitation": "fundamental (LP01-like scalar mode)",
        "coherent_combination": "first-order amplitude with phase-mismatch integral",
        "multi_channel": "incoherent (random optical phase) power summation",
        "energy_check": True,
    },
    # ------------------------------------------------------------ crossing model
    "crossing_model": {
        "primary": "fdfd_eim_2d",
        "fallback": "cmt_local_supermode_integral",
        "angles_deg": [5.0, 7.5, 10.0, 12.5, 15.0, 17.5, 20.0, 25.0, 30.0,
                       35.0, 40.0, 45.0, 50.0, 60.0, 70.0, 80.0, 90.0],
        "wavelengths_nm": [1310.0, 1550.0],
        "grid_um": 0.15,
        "pml_cells": 12,
        "pml_thickness_um": 4.0,
        "pml_strength": 3.0,
        "domain_margin_um": 12.0,
        "domain_length_factor": 4.0,
        "max_unknowns": 230000,
        "validate_with_cmt": True,
        "resolution_floor": 1.0e-7,
        "resolution_floor_note":
            "local FDFD resolves crossing crosstalk down to ~1e-7 (PML + "
            "dispersion residual); values below this are reported as the "
            "conservative bound 1e-7 rather than as a false numeric value",
    },
    "random_seed": 20261119,
    "figure_dpi": 220,
}


def reference_optics() -> dict:
    return deepcopy(CONFIG["optics"]["reference"])


def parameter_sets() -> list[dict]:
    """Parameter combinations for the sensitivity study (E6)."""
    base = reference_optics()
    sets: list[dict] = []

    def add(label: str, **kw):
        s = deepcopy(base)
        s.update(kw)
        s["label"] = label
        if s not in sets:
            sets.append(s)

    add("REF")
    for lam in CONFIG["optics"]["wavelengths_nm"]:
        if lam != base["wavelength_nm"]:
            add(f"lambda_{int(lam)}", wavelength_nm=lam)
    for dn in CONFIG["optics"]["delta_n_values"]:
        if dn != base["delta_n"]:
            add(f"dn_{dn:.4f}", delta_n=dn)
    for w in CONFIG["optics"]["core_width_um_values"]:
        if w != base["core_width_um"]:
            add(f"w_{int(w)}um", core_width_um=w)
    for h in CONFIG["optics"]["core_height_um_values"]:
        if h != base["core_height_um"]:
            add(f"h_{int(h)}um", core_height_um=h)
    for prof in CONFIG["optics"]["profiles"]:
        if prof != base["profile"]:
            add(f"profile_{prof}", profile=prof)
    return sets
