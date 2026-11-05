"""VNA views of coil networks: S-parameters and source-driven currents.

Conventions: real reference impedance ``z0`` on every port, power waves
``a = (V + z0 I) / (2 sqrt(z0))``, ``S = (Z - z0)(Z + z0)^-1``. A source of available power
``P`` has incident peak voltage ``V+ = sqrt(2 z0 P)`` and EMF ``2 V+`` behind ``z0``.
"""

from __future__ import annotations

from typing import Literal

import numpy as np

from .circuit import CoilNetwork, NetworkResult
from .geometry import SolenoidCoil

ThruMode = Literal["series", "shunt"]


def z_to_s(z: np.ndarray, z0: float = 50.0) -> np.ndarray:
    """Convert Z-parameters (..., P, P) to S-parameters with reference ``z0``."""
    z = np.asarray(z, dtype=complex)
    eye = np.eye(z.shape[-1])
    # S = (Z - z0 I)(Z + z0 I)^-1  ==  solve((Z + z0 I)^T, (Z - z0 I)^T)^T
    lhs = np.swapaxes(z + z0 * eye, -1, -2)
    rhs = np.swapaxes(z - z0 * eye, -1, -2)
    return np.swapaxes(np.linalg.solve(lhs, rhs), -1, -2)


def series_thru_s(z_dut, z0: float = 50.0) -> tuple[np.ndarray, np.ndarray]:
    """(S11, S21) of an ideal two-terminal impedance in series between two ports."""
    z_dut = np.asarray(z_dut, dtype=complex)
    return z_dut / (z_dut + 2 * z0), 2 * z0 / (z_dut + 2 * z0)


def shunt_thru_s(z_dut, z0: float = 50.0) -> tuple[np.ndarray, np.ndarray]:
    """(S11, S21) of an ideal two-terminal impedance shunted to ground between two ports."""
    z_dut = np.asarray(z_dut, dtype=complex)
    return -z0 / (z0 + 2 * z_dut), 2 * z_dut / (z0 + 2 * z_dut)


def incident_voltage(p_dbm: float, z0: float = 50.0) -> float:
    """Peak incident wave voltage V+ for available source power ``p_dbm`` [V]."""
    return float(np.sqrt(2 * z0 * 1e-3 * 10 ** (p_dbm / 10)))


def thru_network(
    coil: SolenoidCoil, mode: ThruMode, ground_end: Literal["start", "end"] = "end", **kw
) -> CoilNetwork:
    """Coil alone in a two-port through fixture.

    ``series``: start terminal on port 1's centre conductor, end terminal on port 2's; nothing
    grounded (the coil's capacitance to the reference/shields is kept).
    ``shunt``: one terminal on the joined centre line of ports 1 and 2, the other
    (``ground_end``) on the shields.
    """
    coil = coil.moved(position=[0, 0, 0])
    if mode == "series":
        return CoilNetwork(
            [coil], ground=None, ports=[((0, "start"), None), ((0, "end"), None)], **kw
        )
    if mode == "shunt":
        hot = "start" if ground_end == "end" else "end"
        return CoilNetwork(
            [coil], ground=ground_end, ports=[((0, hot), None), ((0, hot), None)], **kw
        )
    raise ValueError(f"mode must be 'series' or 'shunt', got {mode!r}")


def driven_port_currents(z: np.ndarray, emf: np.ndarray, z0: float = 50.0) -> np.ndarray:
    """Port currents (F, P) with source EMFs ``emf`` (P,) behind ``z0`` on every port."""
    z = np.asarray(z, dtype=complex)
    eye = np.eye(z.shape[-1])
    emf = np.broadcast_to(np.asarray(emf, dtype=complex), z.shape[:-1])
    return np.linalg.solve(z + z0 * eye, emf[..., None])[..., 0]


def driven_turn_currents(
    res: NetworkResult, emf: np.ndarray, z0: float = 50.0
) -> tuple[np.ndarray, np.ndarray]:
    """Turn currents (F, T) and port currents (F, P) for VNA-style excitation.

    ``emf`` gives each port's source EMF (e.g. ``[2 V+, 0]`` to drive port 1 with all ports
    terminated in ``z0``). Superposes the unit-current solutions stored in ``res``.
    """
    i_port = driven_port_currents(res.z, emf, z0)
    return np.einsum("fp,fpt->ft", i_port, res.turn_currents), i_port
