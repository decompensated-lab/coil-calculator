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
from typing import NamedTuple

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
from .types import (
    ArrayLike,
    ComplexArray,
    Coupling,
    FloatArray,
    Grounding,
    Port,
    Terminal,
    TerminalEnd,
)

REF = -1  # node index used for the reference (infinity / grounded shield)
GroundSpec = Grounding | str | None


class Resonance(NamedTuple):
    """A parallel self-resonance seen at a port."""

    freq: float  # [Hz]
    q: float  # resonator Q (conductor + dielectric loss)
    r_parallel: float  # |Z| at resonance [Ω]


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
    freqs: FloatArray
    z: ComplexArray
    turn_currents: ComplexArray
    node_voltages: ComplexArray

    def z_in(self, port: int = 0) -> ComplexArray:
        return self.z[:, port, port]

    def effective_inductance(self, port: int = 0) -> FloatArray:
        """Apparent inductance ``Im(Z_ii)/omega`` [H] (diverges at self-resonance)."""
        return self.z_in(port).imag / (2 * np.pi * self.freqs)

    def transfer_impedance(self, to_port: int = 1, from_port: int = 0) -> ComplexArray:
        """Open-circuit voltage at ``to_port`` per ampere into ``from_port`` [ohm]."""
        return self.z[:, to_port, from_port]

    def loaded_voltage(self, z_load: complex, to_port: int = 1, from_port: int = 0) -> ComplexArray:
        """Voltage across ``z_load`` on ``to_port`` per ampere into ``from_port`` [V/A].

        Valid for a two-port with the drive port current-imposed.
        """
        z21 = self.z[:, to_port, from_port]
        z22 = self.z[:, to_port, to_port]
        return z21 * z_load / (z_load + z22)

    def current_distribution(self, coil: int, port: int = 0) -> ComplexArray:
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
        :class:`Grounding` per coil, or one value for all. ``FLOATING`` (or ``None``): the port
        is differential and the system's reference is infinity through the turns'
        capacitance. ``START``/``END``: that terminal is tied to the reference node, as when a
        coax shield connects to it.
    coupling
        ``"full"``; ``"magnetic"`` drops inter-coil capacitance; ``"electric"`` drops inter-coil
        mutual inductance (diagnostic for separating coupling paths).
    r_factor
        Multiplier on the isolated-wire skin-effect resistance (proximity effect).
    ports
        Optional explicit :class:`Port` objects ``(plus, minus)``, each terminal being
        ``(coil_index, TerminalEnd)`` or ``None`` for the reference node. E.g. a series-thru
        fixture: ``[Port((0, TerminalEnd.START), None), Port((0, TerminalEnd.END), None)]``.
    """

    def __init__(
        self,
        coils: Sequence[SolenoidCoil],
        ground: Sequence[GroundSpec] | GroundSpec = None,
        coupling: Coupling | str = Coupling.FULL,
        r_factor: float = 1.0,
        rho: float = RHO_CU,
        n_sub: int | None = None,
        ports: Sequence[Port | tuple[Terminal, Terminal]] | None = None,
    ) -> None:
        self.coils = list(coils)
        nc = len(self.coils)
        if ground is None or isinstance(ground, str):
            self.ground = [Grounding.parse(ground)] * nc
        else:
            self.ground = [Grounding.parse(g) for g in ground]
            if len(self.ground) != nc:
                raise ValueError(f"got {len(self.ground)} ground settings for {nc} coils")
        coupling = Coupling(coupling)
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
                if coupling is Coupling.ELECTRIC:
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
        if coupling is Coupling.MAGNETIC and nc > 1:
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

        grounded = [
            self.terminal_node((i, g.terminal))
            for i, g in enumerate(self.ground)
            if g.terminal is not None
        ]
        self.free_nodes = np.setdiff1d(np.arange(nn), grounded)

        # ports as (plus node, minus node); current enters the network at "plus"
        if ports is None:
            ports = [Port((i, TerminalEnd.START), (i, TerminalEnd.END)) for i in range(nc)]
        self.ports: list[tuple[int, int]] = [
            (self.terminal_node(p), self.terminal_node(m)) for p, m in ports
        ]

    def terminal_node(self, terminal: Terminal | tuple[int, str]) -> int:
        """Global node index of ``(coil, TerminalEnd)``; ``None`` -> :data:`REF`."""
        if terminal is None:
            return REF
        coil, end = terminal
        if not 0 <= coil < len(self.coils):
            raise IndexError(f"coil index {coil} out of range (have {len(self.coils)} coils)")
        if TerminalEnd(end) is TerminalEnd.START:
            return int(self.node_offsets[coil])
        return int(self.node_offsets[coil] + self.coils[coil].n_turns)

    # ------------------------------------------------------------------------------------
    def turn_slice(self, coil: int) -> slice:
        return slice(self.turn_offsets[coil], self.turn_offsets[coil + 1])

    def node_slice(self, coil: int) -> slice:
        return slice(self.node_offsets[coil], self.node_offsets[coil + 1])

    def branch_impedance(self, freq: float) -> ComplexArray:
        """Turn branch impedance matrix ``R + j omega L`` at ``freq`` [ohm]."""
        omega = 2 * np.pi * freq
        zint = np.array(
            [internal_impedance_per_length(a, freq, self.rho) for a in self.wire_radius]
        )
        r = zint.real * self.turn_length * self.r_factor
        l_int = zint.imag / omega * self.turn_circ
        return 1j * omega * self.l_ext + np.diag(r + 1j * omega * l_int)

    def solve(self, freqs: ArrayLike) -> NetworkResult:
        f_arr = np.atleast_1d(np.asarray(freqs, dtype=float))
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

        z = np.empty((len(f_arr), n_ports, n_ports), dtype=complex)
        i_turn = np.empty((len(f_arr), n_ports, nt), dtype=complex)
        v_node = np.zeros((len(f_arr), n_ports, nn), dtype=complex)
        for fi, f in enumerate(f_arr):
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
        return NetworkResult(self, f_arr, z, i_turn, v_node)

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
        def g(f: float) -> float:
            return float((1 / self.solve([f]).z[0, port, port]).imag)

        return float(brentq(g, fs[k], fs[k + 1], xtol=1e-6 * fs[k]))

    def resonance(self, port: int = 0, f_lo: float = 1e4, f_hi: float = 1e9) -> Resonance:
        """First parallel resonance at ``port`` (other ports open), with its Q.

        Q is the resonator (unloaded) Q from the slope of the port susceptance,
        ``Q = (ω0 / 2G)·dB/dω`` at ``Y = G + jB = 1/Z_ii``; it includes conductor and
        dielectric loss. ``r_parallel = 1/G`` is the impedance at resonance.
        """
        f0 = self.srf(port, f_lo, f_hi)
        if not np.isfinite(f0):
            return Resonance(float("nan"), float("nan"), float("nan"))
        e = 1e-5
        y = 1 / self.solve([f0 * (1 - e), f0, f0 * (1 + e)]).z[:, port, port]
        w0 = 2 * np.pi * f0
        db_dw = (y[2].imag - y[0].imag) / (2 * e * w0)
        return Resonance(f0, float(w0 * db_dw / (2 * y[1].real)), float(1 / y[1].real))

    def unit_fields(self, points: ArrayLike) -> FloatArray:
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
        points: ArrayLike,
        freq_index: int = 0,
        port: int = 0,
        turn_currents: ComplexArray | None = None,
    ) -> ComplexArray:
        """Complex B phasor [T] at global ``points``.

        Uses ``turn_currents`` (shape (T,)) if given, else 1 A into ``port`` (others open).
        """
        i = result.turn_currents[freq_index, port] if turn_currents is None else turn_currents
        return np.tensordot(i, self.unit_fields(points), axes=1)
