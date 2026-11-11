"""Step 4 of the re-plan: ``coilcal.circuit`` and ``coilcal.vna`` against their Rust port.

Network results are compared per frequency, normwise (largest difference over the ports
relative to the largest value), because near a resonance single entries pass through zero.
"""

import numpy as np
import pytest
from conftest import coil_table

from coilcal import vna
from coilcal.circuit import CoilNetwork
from coilcal.gui import model as gm
from coilcal.types import Coupling, Grounding, Port, TerminalEnd, ThruMode

GUI = gm.Params()
COILS = GUI.coils()
FREQS = np.union1d(np.geomspace(1e5, 30e6, 60), [5e6])
CODE = {Grounding.FLOATING: 0, Grounding.START: 1, Grounding.END: 2}
COUPLING = {Coupling.FULL: 0, Coupling.MAGNETIC: 1, Coupling.ELECTRIC: 2}
END = {TerminalEnd.START: 0, TerminalEnd.END: 1}


def spec(coils, ground, coupling=Coupling.FULL, r_factor=1.0, ports=None):
    rows = []
    for p in ports or []:
        rows.append([x for t in p for x in ((-1, 0) if t is None else (t[0], END[t[1]]))])
    return (
        coil_table(coils),
        np.array([CODE[Grounding.parse(g)] for g in ground], float),
        COUPLING[coupling],
        r_factor,
        np.array(rows, float).reshape(-1, 4),
    )


def close(got, ref, rtol):
    """Per leading index (frequency): max|got - ref| <= rtol * max|ref|."""
    got, ref = np.asarray(got), np.asarray(ref)
    assert got.shape == ref.shape
    axes = tuple(range(1, ref.ndim))
    diff = np.abs(got - ref).max(axis=axes)
    scale = np.abs(ref).max(axis=axes)
    assert np.all(diff <= rtol * scale), np.max(diff / scale)


SINGLE = COILS[:1]
NETWORKS = {
    "gui-default": (COILS, GUI.grounds, Coupling.FULL, 1.0, None),
    "floating": (COILS, [None, None], Coupling.FULL, 1.0, None),
    "magnetic": (COILS, GUI.grounds, Coupling.MAGNETIC, 1.0, None),
    "electric": (COILS, GUI.grounds, Coupling.ELECTRIC, 1.0, None),
    "r-factor": (SINGLE, ["start"], Coupling.FULL, 2.0, None),
    "explicit-ports": (COILS, [None, "end"], Coupling.FULL, 1.0,
                       [Port((0, TerminalEnd.START), None), Port((1, TerminalEnd.START), (0, TerminalEnd.END))]),
}  # fmt: skip
# The nodal matrices have cond up to 8e7 (cond·ε ≈ 2e-8); z and turn currents agree to ~1e-12.
RTOL = 1e-10
# Node voltages of a floating network: its common-mode potential is fixed only through the
# turns' capacitance to infinity, so they carry the whole matrix's conditioning (measured
# 1.7e-10 against cond·ε ≈ 2e-8), while their differences (z) agree to 1e-12.
RTOL_V = 1e-9


@pytest.mark.parametrize("name", NETWORKS)
def test_network_solve(port, name):
    coils, ground, coupling, rf, ports = NETWORKS[name]
    net = CoilNetwork(coils, ground=ground, coupling=coupling, r_factor=rf, ports=ports)
    ref = net.solve(FREQS)
    z, i_turn, v_node, c_node = port(
        "network_solve", *spec(coils, ground, coupling, rf, ports), FREQS
    )
    close(c_node[None], net.c_node[None], 1e-12)
    close(z, ref.z, RTOL)
    close(i_turn, ref.turn_currents, RTOL)
    close(v_node, ref.node_voltages, RTOL_V)


@pytest.mark.parametrize("mode", list(ThruMode))
@pytest.mark.parametrize("gnd", list(TerminalEnd))
def test_thru_network(port, mode, gnd):
    ref = vna.thru_network(COILS[1], mode, ground_end=gnd, r_factor=1.5).solve(FREQS)
    z, i_turn, v_node = port(
        "thru_solve", coil_table(COILS[1:]), list(ThruMode).index(mode), END[gnd], 1.5, FREQS
    )
    close(z, ref.z, RTOL)
    close(i_turn, ref.turn_currents, RTOL)
    close(v_node, ref.node_voltages, RTOL)


def test_srf_and_resonance(port):
    hi = 1e9
    net = CoilNetwork(COILS, ground=GUI.grounds)
    for k in range(2):
        (f,) = port("network_srf", *spec(COILS, GUI.grounds), k, 1e4, hi, 400)
        assert float(f) == pytest.approx(net.srf(k, f_lo=1e4, f_hi=hi), rel=1e-12, abs=0)
    for c, g in zip(COILS, GUI.grounds, strict=True):
        for coil in (c, c.without_dielectrics()):  # the GUI's "alone" and "vacuum" SRFs
            ref = CoilNetwork([coil], ground=g).resonance(f_lo=1e4, f_hi=hi)
            f0, q, rp = port("network_resonance", *spec([coil], [g]), 0, 1e4, hi)
            assert float(f0) == pytest.approx(ref.freq, rel=1e-12, abs=0)
            assert float(q) == pytest.approx(ref.q, rel=1e-9, abs=0)  # finite difference: 1.4e-11
            assert float(rp) == pytest.approx(ref.r_parallel, rel=1e-11, abs=0)


def test_no_resonance_in_range_is_nan(port):
    (f,) = port("network_srf", *spec(SINGLE, ["end"]), 0, 1e3, 1e4, 50)
    assert np.isnan(f) and np.isnan(
        CoilNetwork(SINGLE, ground="end").srf(f_lo=1e3, f_hi=1e4, n_scan=50)
    )


def test_vna_helpers(port):
    res = CoilNetwork(COILS, ground=GUI.grounds).solve(FREQS)
    (s,) = port("z_to_s", res.z, 50.0)
    close(s, vna.z_to_s(res.z, 50.0), 1e-13)
    v_plus = vna.incident_voltage(0.0, 50.0)
    assert port("incident_voltage", np.array([0.0, -10.0]), np.array([50.0, 75.0]))[
        0
    ] == pytest.approx([v_plus, vna.incident_voltage(-10.0, 75.0)], rel=1e-15, abs=0)
    emf = np.array([2 * v_plus, 0.0])
    turn, i_port = port("driven_turn_currents", res.z, res.turn_currents, emf, 50.0)
    turn_ref, i_port_ref = vna.driven_turn_currents(res, emf, 50.0)
    close(i_port, i_port_ref, 1e-13)
    close(turn, turn_ref, 1e-13)
    (fs,) = port("geomspace", 1e4, 3e8, 400)
    assert fs == pytest.approx(np.geomspace(1e4, 3e8, 400), rel=1e-15, abs=0)


def test_bad_port_is_an_error(port):
    ports = [Port((5, TerminalEnd.START), None)]
    with pytest.raises(IndexError, match="out of range"):
        CoilNetwork(SINGLE, ports=ports)
    with pytest.raises(RuntimeError, match="out of range"):
        port("network_solve", *spec(SINGLE, [None], ports=ports), FREQS)
