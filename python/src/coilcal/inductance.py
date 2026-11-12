"""Self-inductance and resistance of single-layer coils."""

from __future__ import annotations

import numpy as np
from scipy.constants import mu_0
from scipy.special import ellipe, ellipk

from .geometry import SolenoidCoil
from .loops import (
    RHO_CU,
    internal_impedance_per_length,
    internal_inductance_per_length,
    loop_self_inductance,
    mutual_coaxial,
)


def self_inductance(coil: SolenoidCoil, freq: float | None = None) -> float:
    """Self-inductance from the ring model [H].

    ``L = N L_turn + 2 sum_k (N-k) M(k*pitch)``: each turn is a round-wire loop (thin-wire
    formula, internal inductance from the skin-effect solution at ``freq``; ``None`` = DC),
    turn-to-turn coupling uses Maxwell's filament formula, which is exact for round wires
    with uniform/axisymmetric current (GMD = centre distance). Proximity effect is ignored.
    """
    n, r = coil.n_turns, coil.mean_radius
    l_turn = loop_self_inductance(r, coil.wire_radius, freq)
    k = np.arange(1, n)
    mutual = np.sum((n - k) * mutual_coaxial(r, r, k * coil.pitch)) if n > 1 else 0.0
    return float(n * l_turn + 2 * mutual)


def nagaoka(diameter: float, length: float) -> float:
    """Nagaoka coefficient K_L of a uniform cylindrical current sheet (exact, elliptic)."""
    k2 = diameter**2 / (diameter**2 + length**2)
    k, kp2 = np.sqrt(k2), 1 - k2
    return float(
        4 / (3 * np.pi * np.sqrt(kp2)) * (kp2 / k2 * (ellipk(k2) - ellipe(k2)) + ellipe(k2) - k)
    )


def sheet_inductance(coil: SolenoidCoil) -> float:
    """Lorenz/Nagaoka current-sheet inductance (diameter = wire-centre diameter) [H]."""
    d, length, n = coil.mean_d, coil.length, coil.n_turns
    return mu_0 * np.pi * d**2 / 4 * n**2 / length * nagaoka(d, length)


def rosa_corrections(coil: SolenoidCoil, freq: float | None = None) -> tuple[float, float]:
    """Rosa's round-wire corrections (k_s, k_m) to the current-sheet inductance.

    ``L = L_sheet - mu0 R N (k_s + k_m)``. ``k_s = 3/2 - Y - ln(2p/d)`` (strip vs round-wire
    self-inductance; ``Y`` = internal inductance factor, 1/4 at DC giving Rosa's 5/4 - ln(2p/d)),
    ``k_m`` from Knight's asymptotic fit to Rosa's mutual-correction table.
    """
    n, p, d = coil.n_turns, coil.pitch, coil.wire_d
    y = internal_inductance_per_length(coil.wire_radius, freq) * 2 * np.pi / mu_0
    ks = 1.5 - y - np.log(2 * p / d)
    km = (
        np.log(2 * np.pi)
        - 1.5
        - np.log(n) / (6 * n)
        - 0.33084236 / n
        - 1 / (120 * n**3)
        + 1 / (504 * n**5)
        - 0.0011923 / n**7
        + 0.0005068 / n**9
    )
    return float(ks), float(km)


def rosa_inductance(coil: SolenoidCoil, freq: float | None = None) -> float:
    """Nagaoka sheet inductance with Rosa round-wire corrections [H] (Coil64-style check)."""
    ks, km = rosa_corrections(coil, freq)
    return sheet_inductance(coil) - mu_0 * coil.mean_radius * coil.n_turns * (ks + km)


def wheeler_inductance(coil: SolenoidCoil) -> float:
    """Wheeler's long-coil approximation ``mu0 pi R^2 N^2 / (l + 0.9 R)`` [H] (rough check)."""
    r = coil.mean_radius
    return mu_0 * np.pi * r**2 * coil.n_turns**2 / (coil.length + 0.9 * r)


def ac_resistance(coil: SolenoidCoil, freq: float | None = None, rho: float = RHO_CU) -> float:
    """Wire resistance including skin effect of an isolated wire [ohm].

    Proximity effect between turns is NOT included; for pitch ~ 2 d it typically adds tens of %
    at frequencies where the skin depth is much smaller than the wire radius.
    """
    return coil.wire_length * internal_impedance_per_length(coil.wire_radius, freq or 0, rho).real
