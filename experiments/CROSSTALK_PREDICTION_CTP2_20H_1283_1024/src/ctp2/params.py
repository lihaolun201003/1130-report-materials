"""Immutable physical / board parameters for CTP-2.0 and the sweep presets.

Everything that is *frozen* by the project specification lives here as a
module-level constant so that no script can silently change it:

* propagation loss  alpha = 0.05 dB/cm  ->  Loss = 0.005 * L[mm] dB
* R15 extra bend loss = 0 dB (arc length still counted in the propagation loss)
* 20 physical routing heights, 18 body + 2 interface
* 9x9 um, dn = 0.0065, n_clad = 1.50, lambda = 1310 nm reference cross-section

The reference cross-section is a *computational assumption* documented in the
CTP-1.0 report; it is not part of the frozen routing geometry (the geometric
``waveguide_width_mm = 0.05`` is a layout pitch, never an optical core size).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from pathlib import Path

# ---------------------------------------------------------------- frozen rules
ALPHA_DB_PER_CM = 0.05
"""Unified propagation loss (engineering assumption, MUST NOT be changed)."""

BEND_EXTRA_LOSS_DB = 0.0
"""Additional loss of an R15 bend. The arc length is still counted."""

WAVELENGTH_NM = 1310.0
N_CLAD = 1.50
DELTA_N = 0.0065
CORE_W_UM = 9.0
CORE_H_UM = 9.0

N_ROUTES = 1024
N_PLANES = 20
N_BODY_PLANES = 18
N_INTERFACE_PLANES = 2
N_CROSSINGS = 1283
N_CROSSING_PAIRS = 1221
N_ROUTES_WITH_CROSSINGS = 647
TOTAL_LENGTH_MM = 156597.221522
ROUTES_SHA256 = "35d7ebed00339bee21fe0ca47075c9b34008120522a47933a099efacf0b90753"
MIN_BEND_RADIUS_MM = 15.0
MIN_3D_CLEARANCE_MM = 0.05
MIN_LAYER_PITCH_MM = 0.05
SAME_LAYER_2D_CLEARANCE_MM = 0.08
GLASS_Z_RANGE_MM = (-0.35, 0.65)
PLANE_HEIGHTS_MM = {
    2: -0.325, 3: -0.275, 4: -0.225, 5: -0.175, 6: -0.125, 7: -0.075,
    20: -0.025, 1001: 0.025, 8: 0.075, 9: 0.125, 10: 0.175, 11: 0.225,
    12: 0.275, 13: 0.325, 14: 0.375, 15: 0.425, 16: 0.475, 1002: 0.525,
    17: 0.575, 18: 0.625,
}

# .../experiments/CROSSTALK_PREDICTION_CTP2_20H_1283_1024/src/ctp2/params.py
_HERE = Path(__file__).resolve()
EXPERIMENT = _HERE.parents[2]                 # .../CROSSTALK_PREDICTION_CTP2_20H_1283_1024
REPO_ROOT = _HERE.parents[4]                  # .../1130-report-materials

CTP1_DIR = REPO_ROOT / "experiments" / "CROSSTALK_PREDICTION_20H_1283_1024"
BEST_VALID = REPO_ROOT / "experiments" / "COLD_START_20_HEIGHT_1024" / "10_best_valid"

OUT_MODES = EXPERIMENT / "outputs" / "modes"
OUT_COUPLING = EXPERIMENT / "outputs" / "coupling"
OUT_CROSSINGS = EXPERIMENT / "outputs" / "crossings"
OUT_BOARD = EXPERIMENT / "outputs" / "board"
OUT_FIGURES = EXPERIMENT / "outputs" / "figures"
OUT_FULLWAVE = EXPERIMENT / "outputs" / "fullwave"
CACHE = EXPERIMENT / "cache"

for _d in (OUT_MODES, OUT_COUPLING, OUT_CROSSINGS, OUT_BOARD, OUT_FIGURES,
           OUT_FULLWAVE, CACHE):
    _d.mkdir(parents=True, exist_ok=True)

# input files whose bytes are frozen
FROZEN_INPUTS = (
    "routes_l3d.json",
    "assignment_1024.csv",
    "layer_planes.json",
    "physical_layer_stack.json",
    "process_rules.json",
    "crossing_stats.json",
    "validation.json",
    "SHA256.json",
)


# ------------------------------------------------------------- optics presets
@dataclass(frozen=True)
class Optics:
    """Reference cross-section of the waveguide."""

    wavelength_nm: float = WAVELENGTH_NM
    n_clad: float = N_CLAD
    delta_n: float = DELTA_N
    core_w_um: float = CORE_W_UM
    core_h_um: float = CORE_H_UM
    profile: str = "step"          # "step" | "graded"
    label: str = "REF"

    # -------- derived
    @property
    def n_core(self) -> float:
        return self.n_clad + self.delta_n

    @property
    def lam_um(self) -> float:
        return self.wavelength_nm * 1e-3

    @property
    def k0(self) -> float:
        return 2.0 * math.pi / self.lam_um

    @property
    def na(self) -> float:
        return math.sqrt(max(self.n_core ** 2 - self.n_clad ** 2, 0.0))

    @property
    def v_number(self) -> float:
        """Normalised frequency with the core *half* width (slab convention)."""
        return self.k0 * (self.core_w_um / 2.0) * self.na

    @property
    def gamma_clad_um(self) -> float:
        """Decay constant of the evanescent tail in a homogeneous cladding [1/um].

        Evaluated with the *guiding* mode's effective index, which is filled in
        by the mode solver; this property uses the first-order estimate
        n_eff ~ n_clad + dn/2 which is only used for sanity checks.
        """
        return self.k0 * math.sqrt(max((self.n_clad + self.delta_n / 2) ** 2
                                       - self.n_clad ** 2, 0.0))

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "wavelength_nm": self.wavelength_nm,
            "n_clad": self.n_clad,
            "delta_n": self.delta_n,
            "core_width_um": self.core_w_um,
            "core_height_um": self.core_h_um,
            "profile": self.profile,
        }

    def replace(self, **kw) -> "Optics":
        return replace(self, **kw)


REF = Optics()

#: sensitivity study required by the specification (wavelength / dn / w / h / profile)
SENSITIVITY_PRESETS: tuple[Optics, ...] = (
    REF,
    REF.replace(wavelength_nm=1550.0, label="lambda_1550"),
    REF.replace(delta_n=0.0045, label="dn_0.0045"),
    REF.replace(delta_n=0.0080, label="dn_0.0080"),
    REF.replace(core_w_um=6.0, label="w_6um"),
    REF.replace(core_w_um=12.0, label="w_12um"),
    REF.replace(core_h_um=7.0, label="h_7um"),
    REF.replace(core_h_um=11.0, label="h_11um"),
    REF.replace(profile="graded", label="profile_graded"),
)

#: crossing angles used for the local model database (benchmark + real-board bins)
CROSSING_ANGLES_DEG: tuple[float, ...] = (
    1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.5, 10.0, 12.5, 15.0, 17.5, 20.0,
    22.5, 25.0, 27.5, 30.0, 35.0, 40.0, 45.0, 50.0, 55.0, 60.0, 65.0,
    70.0, 75.0, 80.0, 85.0, 90.0,
)

#: centre-to-centre separations for the parallel-coupler database
SEPARATIONS_UM: tuple[float, ...] = (
    9.0, 10.0, 12.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 50.0, 60.0,
    70.0, 80.0, 100.0, 120.0, 150.0,
)

#: vertical offsets for cross-layer coupling (20 layers -> multiples of 50 um)
VERTICAL_OFFSETS_UM: tuple[float, ...] = (
    0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 100.0, 150.0,
)

#: propagation segment lengths for the coupler validation (um)
COUPLER_LENGTHS_UM: tuple[float, ...] = (100.0, 500.0, 1000.0, 2000.0, 5000.0)
