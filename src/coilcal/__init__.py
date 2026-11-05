"""coilcal: quasi-static modelling of single-layer cylindrical coils (SI units)."""

from .capacitance import capacitance_matrix, isolated_capacitance
from .circuit import CoilNetwork, NetworkResult
from .field import B_axis_rings, B_axis_sheet, field_B, to_magpylib
from .geometry import Former, SolenoidCoil
from .inductance import (
    ac_resistance,
    nagaoka,
    rosa_inductance,
    self_inductance,
    sheet_inductance,
    wheeler_inductance,
)
from .loops import loop_self_inductance, mutual_coaxial, mutual_rings, skin_depth
from .materials import Dielectric, Material
from .mutual import (
    coupling_coefficient,
    flux_linkage,
    induced_emf,
    induced_voltage_loaded,
    mutual_inductance,
    mutual_matrix,
)
from .srf import QuasiStaticReport, check_quasistatic, self_capacitance_medhurst, srf_lumped

__all__ = [
    "B_axis_rings",
    "B_axis_sheet",
    "CoilNetwork",
    "Dielectric",
    "Former",
    "Material",
    "NetworkResult",
    "QuasiStaticReport",
    "SolenoidCoil",
    "ac_resistance",
    "capacitance_matrix",
    "check_quasistatic",
    "coupling_coefficient",
    "field_B",
    "flux_linkage",
    "induced_emf",
    "induced_voltage_loaded",
    "isolated_capacitance",
    "loop_self_inductance",
    "mutual_coaxial",
    "mutual_inductance",
    "mutual_matrix",
    "mutual_rings",
    "nagaoka",
    "rosa_inductance",
    "self_capacitance_medhurst",
    "self_inductance",
    "sheet_inductance",
    "skin_depth",
    "srf_lumped",
    "to_magpylib",
    "wheeler_inductance",
]
