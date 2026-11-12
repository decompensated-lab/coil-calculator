"""VNA views of coil networks: S-parameters and source-driven currents.

Conventions: real reference impedance ``z0`` on every port, power waves
``a = (V + z0 I) / (2 sqrt(z0))``, ``S = (Z - z0)(Z + z0)^-1``. A source of available power
``P`` has incident peak voltage ``V+ = sqrt(2 z0 P)`` and EMF ``2 V+`` behind ``z0``.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .circuit import CoilNetwork, NetworkResult
from .geometry import SolenoidCoil
from .types import ArrayLike, ComplexArray, Grounding, Port, TerminalEnd, ThruMode


def z_to_s(z: ArrayLike, z0: float = 50.0) -> ComplexArray:
    """Convert Z-parameters (..., P, P) to S-parameters with reference ``z0``."""
    zc = np.asarray(z, dtype=complex)
    eye = np.eye(zc.shape[-1])
    # S = (Z - z0 I)(Z + z0 I)^-1  ==  solve((Z + z0 I)^T, (Z - z0 I)^T)^T
    lhs = np.swapaxes(zc + z0 * eye, -1, -2)
    rhs = np.swapaxes(zc - z0 * eye, -1, -2)
    return np.swapaxes(np.linalg.solve(lhs, rhs), -1, -2)


def series_thru_s(z_dut: ArrayLike, z0: float = 50.0) -> tuple[ComplexArray, ComplexArray]:
    """(S11, S21) of an ideal two-terminal impedance in series between two ports."""
    z = np.asarray(z_dut, dtype=np.complex128)
    s11: ComplexArray = z / (z + 2 * z0)
    s21: ComplexArray = 2 * z0 / (z + 2 * z0)
    return s11, s21


def shunt_thru_s(z_dut: ArrayLike, z0: float = 50.0) -> tuple[ComplexArray, ComplexArray]:
    """(S11, S21) of an ideal two-terminal impedance shunted to ground between two ports."""
    z = np.asarray(z_dut, dtype=np.complex128)
    s11: ComplexArray = -z0 / (z0 + 2 * z)
    s21: ComplexArray = 2 * z / (z0 + 2 * z)
    return s11, s21


def incident_voltage(p_dbm: float, z0: float = 50.0) -> float:
    """Peak incident wave voltage V+ for available source power ``p_dbm`` [V]."""
    return float(np.sqrt(2 * z0 * 1e-3 * 10 ** (p_dbm / 10)))


def thru_network(
    coil: SolenoidCoil,
    mode: ThruMode | str,
    ground_end: TerminalEnd | str = TerminalEnd.END,
    **kw: Any,
) -> CoilNetwork:
    """Coil alone in a two-port through fixture.

    ``SERIES``: start terminal on port 1's centre conductor, end terminal on port 2's; nothing
    grounded (the coil's capacitance to the reference/shields is kept).
    ``SHUNT``: one terminal on the joined centre line of ports 1 and 2, the other
    (``ground_end``) on the shields.
    """
    coil = coil.moved(position=np.zeros(3))
    if ThruMode(mode) is ThruMode.SERIES:
        ports = [Port((0, TerminalEnd.START), None), Port((0, TerminalEnd.END), None)]
        return CoilNetwork([coil], ground=Grounding.FLOATING, ports=ports, **kw)
    gnd = TerminalEnd(ground_end)
    hot = TerminalEnd.START if gnd is TerminalEnd.END else TerminalEnd.END
    ports = [Port((0, hot), None), Port((0, hot), None)]
    return CoilNetwork([coil], ground=Grounding(gnd.value), ports=ports, **kw)


def driven_port_currents(z: ArrayLike, emf: ArrayLike, z0: float = 50.0) -> ComplexArray:
    """Port currents (F, P) with source EMFs ``emf`` (P,) behind ``z0`` on every port."""
    zc = np.asarray(z, dtype=complex)
    eye = np.eye(zc.shape[-1])
    e = np.broadcast_to(np.asarray(emf, dtype=complex), zc.shape[:-1])
    return np.linalg.solve(zc + z0 * eye, e[..., None])[..., 0]


def driven_turn_currents(
    res: NetworkResult, emf: ArrayLike, z0: float = 50.0
) -> tuple[ComplexArray, ComplexArray]:
    """Turn currents (F, T) and port currents (F, P) for VNA-style excitation.

    ``emf`` gives each port's source EMF (e.g. ``[2 V+, 0]`` to drive port 1 with all ports
    terminated in ``z0``). Superposes the unit-current solutions stored in ``res``.
    """
    i_port = driven_port_currents(res.z, emf, z0)
    return np.einsum("fp,fpt->ft", i_port, res.turn_currents), i_port
