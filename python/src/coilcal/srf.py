"""Quick self-capacitance / self-resonance estimates and quasi-static validity checks.

These use Medhurst's empirical formula (bare wire, no former, fitted to measurements in his
set-up), not a field solution. For the field-solved resonance including insulation, former
and dielectric loss use ``CoilNetwork([coil], ground=...).resonance()``; for short, wide
coils it typically lies well above the Medhurst estimate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.constants import c as C0

from .geometry import SolenoidCoil
from .inductance import ac_resistance, self_inductance
from .loops import skin_depth


def self_capacitance_medhurst(coil: SolenoidCoil) -> float:
    """Medhurst's empirical self-capacitance of a single-layer coil in free space [F].

    ``C[pF] = D[cm] (0.1126 l/D + 0.08 + 0.27/sqrt(l/D))``, D = wire-centre diameter.
    Fitted for roughly 0.1 < l/D < 50 and close-ish spacing; ignores former dielectric.
    """
    d_cm = coil.mean_d * 100
    ratio = coil.length / coil.mean_d
    return d_cm * (0.1126 * ratio + 0.08 + 0.27 / np.sqrt(ratio)) * 1e-12


def srf_lumped(coil: SolenoidCoil, freq: float | None = None) -> float:
    """Self-resonant frequency estimate ``1 / (2 pi sqrt(L C_medhurst))`` [Hz]."""
    return 1 / (2 * np.pi * np.sqrt(self_inductance(coil, freq) * self_capacitance_medhurst(coil)))


@dataclass
class QuasiStaticReport:
    f_max: float
    inductance: float
    self_capacitance: float
    srf: float
    wire_length: float
    wire_length_over_lambda: float
    skin_depth: float
    ac_resistance: float
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.warnings

    def __str__(self) -> str:
        lines = [
            f"f_max                = {self.f_max / 1e6:.3g} MHz",
            f"L (at f_max)         = {self.inductance * 1e6:.4g} uH",
            f"C_self (Medhurst)    = {self.self_capacitance * 1e12:.3g} pF",
            f"SRF (lumped est.)    = {self.srf / 1e6:.3g} MHz  (f_max/SRF = {self.f_max / self.srf:.2f})",
            f"wire length          = {self.wire_length:.3g} m  ({self.wire_length_over_lambda:.3f} lambda)",
            f"skin depth           = {self.skin_depth * 1e6:.3g} um",
            f"R_ac (skin only)     = {self.ac_resistance:.3g} ohm",
        ]
        lines += [f"WARNING: {w}" for w in self.warnings] or ["quasi-static assumption OK"]
        return "\n".join(lines)


def check_quasistatic(
    coil: SolenoidCoil,
    f_max: float,
    max_srf_ratio: float = 0.3,
    max_electrical_length: float = 0.1,
) -> QuasiStaticReport:
    """Check whether a DC-shaped field / lumped L is a fair model up to ``f_max``.

    Flags ``f_max > max_srf_ratio * SRF`` (apparent L rises as 1/(1-(f/SRF)^2), i.e. ~10 % at
    0.3 SRF) and conductor length above ``max_electrical_length`` wavelengths (current no longer
    uniform along the wire).
    """
    lam = C0 / f_max
    rep = QuasiStaticReport(
        f_max=f_max,
        inductance=self_inductance(coil, f_max),
        self_capacitance=self_capacitance_medhurst(coil),
        srf=srf_lumped(coil, f_max),
        wire_length=coil.wire_length,
        wire_length_over_lambda=coil.wire_length / lam,
        skin_depth=skin_depth(f_max),
        ac_resistance=ac_resistance(coil, f_max),
    )
    if f_max > max_srf_ratio * rep.srf:
        boost = 1 / (1 - min(f_max / rep.srf, 0.999) ** 2) - 1
        rep.warnings.append(
            f"f_max is {f_max / rep.srf:.2f} x the Medhurst SRF estimate; apparent inductance "
            f"off by up to ~{boost:.0%} (CoilNetwork gives the field-solved value)"
            if f_max < rep.srf
            else f"f_max is ABOVE the estimated SRF ({f_max / rep.srf:.2f} x)"
        )
    ratio = coil.length / coil.mean_d
    if not 0.1 <= ratio <= 50:
        rep.warnings.append(
            f"l/D = {ratio:.3g} is outside Medhurst's fitted range (0.1-50); C_self/SRF unreliable"
        )
    if rep.wire_length_over_lambda > max_electrical_length:
        n_ok = int(max_electrical_length * lam / (coil.wire_length / coil.n_turns))
        rep.warnings.append(
            f"wire is {rep.wire_length_over_lambda:.2f} lambda long; current not uniform along "
            f"winding (<= ~{n_ok} turns keeps it under {max_electrical_length} lambda)"
        )
    return rep
