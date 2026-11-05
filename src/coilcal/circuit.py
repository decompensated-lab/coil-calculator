"""Turn-level circuit model of one or more coils (magneto- + electro-quasistatic).

Every turn is a lumped branch ``R_k + j omega L`` coupled to every other turn (of any coil)
through the full turn-to-turn inductance matrix. Turn ``k`` of a coil runs from node ``k`` to
node ``k+1`` (``N+1`` nodes per coil; node 0 = start terminal, node N = end terminal). The
Maxwell capacitance matrix between turns is mapped onto nodes by assigning each turn the mean
potential of its two end nodes. Each turn is electrically small (one 150 mm turn ~ 0.5 m << the
60 m wavelength at 5 MHz), so retardation inside a turn is neglected; radiation is ignored.

The resulting network captures self-resonance, non-uniform current along the winding, and
inductive + capacitive coupling between coils. It is solved by modified nodal analysis.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import magpylib as magpy
import numpy as np
from scipy.optimize import brentq

from .capacitance import capacitance_matrix
from .geometry import SolenoidCoil
from .loops import (
    RHO_CU,
    internal_impedance_per_length,
    internal_inductance_per_length,
    loop_self_inductance,
    mutual_coaxial,
)
from .mutual import mutual_matrix

Ground = Literal["start", "end"] | None
Coupling = Literal["full", "magnetic", "electric"]
Terminal = tuple[int, Literal["start", "end"]] | None  # (coil index, which end); None = reference
REF = -1  # node index used for the reference (infinity / grounded shield)


@dataclass
class NetworkResult:
    """Solution of a :class:`CoilNetwork` over frequency.

    Attributes
    ----------
    freqs : (F,)
    z : (F, P, P) port impedance matrix [ohm]; ``z[f, i, j] = V_i / I_j`` with all other ports open.
    turn_currents : (F, P, T) turn currents [A] for 1 A driven into each port (others open).
    node_voltages : (F, P, Nn) node voltages [V] for the same excitations (grounded nodes = 0).
    """

    network: CoilNetwork
    freqs: np.ndarray
    z: np.ndarray
    turn_currents: np.ndarray
    node_voltages: np.ndarray

    def z_in(self, port: int = 0) -> np.ndarray:
        return self.z[:, port, port]

    def effective_inductance(self, port: int = 0) -> np.ndarray:
        """Apparent inductance ``Im(Z_ii)/omega`` [H] (diverges at self-resonance)."""
        return self.z_in(port).imag / (2 * np.pi * self.freqs)

    def transfer_impedance(self, to_port: int = 1, from_port: int = 0) -> np.ndarray:
        """Open-circuit voltage at ``to_port`` per ampere into ``from_port`` [ohm]."""
        return self.z[:, to_port, from_port]

    def loaded_voltage(self, z_load: complex, to_port: int = 1, from_port: int = 0) -> np.ndarray:
        """Voltage across ``z_load`` on ``to_port`` per ampere into ``from_port`` [V/A].

        Valid for a two-port with the drive port current-imposed.
        """
        z21 = self.z[:, to_port, from_port]
        z22 = self.z[:, to_port, to_port]
        return z21 * z_load / (z_load + z22)

    def current_distribution(self, coil: int, port: int = 0) -> np.ndarray:
        """Turn currents of ``coil`` for 1 A into ``port``, shape (F, N_coil)."""
        sl = self.network.turn_slice(coil)
        return self.turn_currents[:, port, sl]


class CoilNetwork:
    """Turn-level network of coils.

    By default each coil gets one port across its two terminals (current enters at "start").

    Parameters
    ----------
    coils
        Coils in the system (any poses).
    ground
        Per coil: ``None`` (floating; port is differential and the system's reference is
        infinity through the turns' capacitance), ``"start"`` or ``"end"`` (that terminal is
        tied to the reference node, as when a coax shield connects to it).
    coupling
        ``"full"``; ``"magnetic"`` drops inter-coil capacitance; ``"electric"`` drops inter-coil
        mutual inductance (diagnostic for separating coupling paths).
    r_factor
        Multiplier on the isolated-wire skin-effect resistance (proximity effect).
    ports
        Optional explicit ports as ``(plus, minus)`` terminal pairs, each terminal being
        ``(coil_index, "start"|"end")`` or ``None`` for the reference node. E.g. a series-thru
        fixture: ``[((0, "start"), None), ((0, "end"), None)]``.
    """

    def __init__(
        self,
        coils: Sequence[SolenoidCoil],
        ground: Sequence[Ground] | Ground = None,
        coupling: Coupling = "full",
        r_factor: float = 1.0,
        rho: float = RHO_CU,
        n_sub: int = 16,
        ports: Sequence[tuple[Terminal, Terminal]] | None = None,
    ) -> None:
        self.coils = list(coils)
        nc = len(self.coils)
        self.ground = [ground] * nc if ground is None or isinstance(ground, str) else list(ground)
        self.coupling = coupling
        self.r_factor = r_factor
        self.rho = rho

        counts = [c.n_turns for c in self.coils]
        self.turn_offsets = np.concatenate([[0], np.cumsum(counts)]).astype(int)
        self.node_offsets = np.concatenate([[0], np.cumsum([n + 1 for n in counts])]).astype(int)
        nt, nn = self.turn_offsets[-1], self.node_offsets[-1]

        # --- inductance: external part (frequency independent) ------------------------
        l_ext = np.zeros((nt, nt))
        for i, a in enumerate(self.coils):
            si = self.turn_slice(i)
            dz = a.turn_z()[:, None] - a.turn_z()[None, :]
            blk = mutual_coaxial(a.mean_radius, a.mean_radius, np.where(dz == 0, 1.0, dz))
            np.fill_diagonal(blk, loop_self_inductance(a.mean_radius, a.wire_radius, None))
            l_ext[si, si] = blk
            for j in range(i + 1, nc):
                if coupling == "electric":
                    continue
                mij = mutual_matrix(a, self.coils[j])
                l_ext[si, self.turn_slice(j)] = mij
                l_ext[self.turn_slice(j), si] = mij.T
        # remove the DC internal inductance; it is added back per frequency
        per_turn = lambda f: np.concatenate([np.full(c.n_turns, f(c)) for c in self.coils])
        self.turn_length = per_turn(lambda c: c.wire_length / c.n_turns)  # helical, for R
        self.turn_circ = per_turn(lambda c: 2 * np.pi * c.mean_radius)  # for internal L
        self.wire_radius = per_turn(lambda c: c.wire_radius)
        l_int_dc = internal_inductance_per_length(self.wire_radius[0], None) * self.turn_circ
        self.l_ext = l_ext - np.diag(l_int_dc)

        # --- capacitance: turns -> nodes ----------------------------------------------
        if coupling == "magnetic" and nc > 1:
            c_turn = np.zeros((nt, nt))
            for i, c in enumerate(self.coils):
                c_turn[self.turn_slice(i), self.turn_slice(i)] = capacitance_matrix(
                    [c], n_sub=n_sub
                )
        else:
            c_turn = capacitance_matrix(self.coils, n_sub=n_sub)
        self.c_turn = c_turn
        t = np.zeros((nt, nn))
        for i, c in enumerate(self.coils):
            for k in range(c.n_turns):
                t[self.turn_offsets[i] + k, self.node_offsets[i] + k] = 0.5
                t[self.turn_offsets[i] + k, self.node_offsets[i] + k + 1] = 0.5
        self.c_node = t.T @ c_turn @ t

        # --- incidence (nodes x turns): +1 at from-node, -1 at to-node ----------------
        inc = np.zeros((nn, nt))
        for i, c in enumerate(self.coils):
            for k in range(c.n_turns):
                inc[self.node_offsets[i] + k, self.turn_offsets[i] + k] = 1.0
                inc[self.node_offsets[i] + k + 1, self.turn_offsets[i] + k] = -1.0
        self.incidence = inc

        grounded = []
        for i, (c, g) in enumerate(zip(self.coils, self.ground, strict=True)):
            if g == "start":
                grounded.append(self.node_offsets[i])
            elif g == "end":
                grounded.append(self.node_offsets[i] + c.n_turns)
            elif g is not None:
                raise ValueError(f"ground must be None/'start'/'end', got {g!r}")
        self.free_nodes = np.setdiff1d(np.arange(nn), grounded)

        # ports as (plus node, minus node); current enters the network at "plus"
        if ports is None:
            ports = [((i, "start"), (i, "end")) for i in range(nc)]
        self.ports = [(self.terminal_node(p), self.terminal_node(m)) for p, m in ports]

    def terminal_node(self, terminal: Terminal) -> int:
        """Global node index of ``(coil, "start"|"end")``; ``None`` -> :data:`REF`."""
        if terminal is None:
            return REF
        coil, end = terminal
        if end == "start":
            return int(self.node_offsets[coil])
        if end == "end":
            return int(self.node_offsets[coil] + self.coils[coil].n_turns)
        raise ValueError(f"terminal end must be 'start' or 'end', got {end!r}")

    # ------------------------------------------------------------------------------------
    def turn_slice(self, coil: int) -> slice:
        return slice(self.turn_offsets[coil], self.turn_offsets[coil + 1])

    def node_slice(self, coil: int) -> slice:
        return slice(self.node_offsets[coil], self.node_offsets[coil + 1])

    def branch_impedance(self, freq: float) -> np.ndarray:
        """Turn branch impedance matrix ``R + j omega L`` at ``freq`` [ohm]."""
        omega = 2 * np.pi * freq
        zint = np.array(
            [internal_impedance_per_length(a, freq, self.rho) for a in self.wire_radius]
        )
        r = zint.real * self.turn_length * self.r_factor
        l_int = zint.imag / omega * self.turn_circ
        return 1j * omega * self.l_ext + np.diag(r + 1j * omega * l_int)

    def solve(self, freqs) -> NetworkResult:
        freqs = np.atleast_1d(np.asarray(freqs, dtype=float))
        nn, nt = self.incidence.shape
        fn = self.free_nodes
        nf = len(fn)
        a_free = self.incidence[fn]
        c_free = self.c_node[np.ix_(fn, fn)]
        pos = {n: k for k, n in enumerate(fn)}
        n_ports = len(self.ports)

        rhs = np.zeros((nf + nt, n_ports), dtype=complex)
        for p, (n_plus, n_minus) in enumerate(self.ports):
            if n_plus in pos:
                rhs[pos[n_plus], p] += 1.0
            if n_minus in pos:
                rhs[pos[n_minus], p] -= 1.0

        z = np.empty((len(freqs), n_ports, n_ports), dtype=complex)
        i_turn = np.empty((len(freqs), n_ports, nt), dtype=complex)
        v_node = np.zeros((len(freqs), n_ports, nn), dtype=complex)
        for fi, f in enumerate(freqs):
            omega = 2 * np.pi * f
            m = np.block(
                [
                    [1j * omega * c_free, a_free],
                    [a_free.T, -self.branch_impedance(f)],
                ]
            )
            x = np.linalg.solve(m, rhs)
            v = np.zeros((nn + 1, n_ports), dtype=complex)  # extra last row = REF (0 V)
            v[fn] = x[:nf]
            v_node[fi] = v[:nn].T
            i_turn[fi] = x[nf:].T
            for q, (n_plus, n_minus) in enumerate(self.ports):
                z[fi, q] = v[n_plus] - v[n_minus]  # REF = -1 hits the zero row
        return NetworkResult(self, freqs, z, i_turn, v_node)

    # ------------------------------------------------------------------------------------
    def srf(self, port: int = 0, f_lo: float = 1e4, f_hi: float = 1e9, n_scan: int = 400) -> float:
        """First self-resonance seen at ``port`` (other ports open) [Hz], or ``nan``.

        Located as the first sign change of ``Im(Z_ii)`` from + to - (parallel resonance).
        """
        fs = np.geomspace(f_lo, f_hi, n_scan)
        x = self.solve(fs).z[:, port, port].imag
        idx = np.nonzero((x[:-1] > 0) & (x[1:] <= 0))[0]
        if not len(idx):
            return float("nan")
        k = idx[0]

        # Im(Z) passes through a pole at parallel resonance: bracket on 1/Z instead (zero).
        def g(f):
            return (1 / self.solve([f]).z[0, port, port]).imag

        return float(brentq(g, fs[k], fs[k + 1], xtol=1e-6 * fs[k]))

    def unit_fields(self, points) -> np.ndarray:
        """B [T] at ``points`` per ampere in each turn, shape (T, *points.shape)."""
        pts = np.asarray(points, dtype=float)
        unit = [
            magpy.current.Circle(
                position=center, orientation=c.orientation, diameter=c.mean_d, current=1.0
            )
            for c in self.coils
            for center in c.turn_centers()
        ]
        g = np.asarray(magpy.getB(unit, pts.reshape(-1, 3), squeeze=False))
        return g.reshape((len(unit), *pts.shape))

    def field_B(
        self,
        result: NetworkResult,
        points,
        freq_index: int = 0,
        port: int = 0,
        turn_currents: np.ndarray | None = None,
    ):
        """Complex B phasor [T] at global ``points``.

        Uses ``turn_currents`` (shape (T,)) if given, else 1 A into ``port`` (others open).
        """
        i = result.turn_currents[freq_index, port] if turn_currents is None else turn_currents
        return np.tensordot(i, self.unit_fields(points), axes=1)
