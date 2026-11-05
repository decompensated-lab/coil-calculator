import numpy as np
import pytest
from scipy.constants import epsilon_0
from scipy.spatial.transform import Rotation as R

import coilcal as cc
from coilcal.capacitance import capacitance_matrix, isolated_capacitance
from coilcal.circuit import CoilNetwork


def typical(n=10, **kw):
    return cc.SolenoidCoil(wire_d=1.0e-3, pitch=2.0e-3, former_d=0.150, n_turns=n, **kw)


# --- capacitance ------------------------------------------------------------------------
def test_torus_capacitance():
    c = typical(1)
    r, a = c.mean_radius, c.wire_radius
    thin = 4 * np.pi**2 * epsilon_0 * r / np.log(8 * r / a)
    assert isolated_capacitance(c) == pytest.approx(thin, rel=1e-3)


@pytest.mark.parametrize("pitch", [1.2e-3, 2e-3, 4e-3])
def test_adjacent_turns_vs_two_wire_line(pitch):
    c = cc.SolenoidCoil(1e-3, pitch, 0.15, 2)
    p = np.linalg.inv(capacitance_matrix([c]))
    c_diff = 1 / (p[0, 0] + p[1, 1] - 2 * p[0, 1])
    two_wire = 2 * np.pi * c.mean_radius * np.pi * epsilon_0 / np.arccosh(pitch / c.wire_d)
    assert c_diff == pytest.approx(two_wire, rel=1e-3)


def test_capacitance_matrix_properties():
    a, b = (
        typical(6),
        typical(4, position=[0.01, 0, 0.05], orientation=R.from_euler("x", 10, degrees=True)),
    )
    c = capacitance_matrix([a, b])
    assert np.allclose(c, c.T)
    assert np.all(np.diag(c) > 0)
    assert np.all(c[~np.eye(len(c), dtype=bool)] < 0)
    assert np.all(np.linalg.eigvalsh(c) > 0)


def test_capacitance_coaxial_vs_thin_wire_path():
    a = typical(4)
    b = typical(4, position=[0, 0, 0.08])
    tilted = b.moved(orientation=R.from_euler("x", 1e-9))
    c1 = capacitance_matrix([a, b])[:4, 4:]
    c2 = capacitance_matrix([a, tilted])[:4, 4:]
    assert np.allclose(c1, c2, rtol=2e-3)


# --- network ----------------------------------------------------------------------------
@pytest.mark.parametrize("ground", [None, "end", "start"])
def test_low_frequency_limit_matches_static(ground):
    a, b = typical(10), typical(5, position=[0, 0, 0.065])
    net = CoilNetwork([a, b], ground=ground)
    f = 1e3
    r = net.solve([f])
    assert r.effective_inductance(0)[0] == pytest.approx(cc.self_inductance(a, f), rel=1e-6)
    assert r.effective_inductance(1)[0] == pytest.approx(cc.self_inductance(b, f), rel=1e-6)
    zm = r.transfer_impedance(1, 0)[0] / (2j * np.pi * f)
    assert zm.real == pytest.approx(cc.mutual_inductance(a, b), rel=1e-6)
    assert r.z_in(0)[0].real == pytest.approx(cc.ac_resistance(a, f), rel=1e-4)


def test_reciprocity_and_tilted_pair():
    a = typical(8)
    b = typical(5, position=[0.03, 0, 0.07], orientation=R.from_euler("y", 20, degrees=True))
    r = CoilNetwork([a, b], ground=["end", None]).solve([1e5, 3e6])
    assert np.allclose(r.z[:, 0, 1], r.z[:, 1, 0], rtol=1e-9)


def test_current_uniform_at_low_freq_and_not_near_srf():
    a = typical(20)
    net = CoilNetwork([a], ground="end")
    srf = net.srf()
    r = net.solve([1e3, 0.8 * srf])
    i = np.abs(r.current_distribution(0))
    assert np.allclose(i[0], 1.0, rtol=1e-6)
    assert i[1].max() / i[1].min() > 1.05


def test_srf_is_parallel_resonance_and_in_ballpark():
    a = typical(50)
    net = CoilNetwork([a], ground="end")
    srf = net.srf()
    z = net.solve([0.98 * srf, srf, 1.02 * srf]).z_in()
    assert abs(z[1]) > 10 * abs(z[0]) and abs(z[1]) > 10 * abs(z[2])
    # Medhurst (empirical, includes former/fixtures) lands within ~30 %
    assert srf == pytest.approx(cc.srf_lumped(a), rel=0.3)


def test_coupling_split_magnetic_plus_electric():
    a, b = typical(10), typical(5, position=[0, 0, 0.065])
    f = 1e5  # far from resonance: contributions add linearly
    full = CoilNetwork([a, b], ground="end").solve([f]).transfer_impedance()[0]
    mag = CoilNetwork([a, b], ground="end", coupling="magnetic").solve([f]).transfer_impedance()[0]
    ele = CoilNetwork([a, b], ground="end", coupling="electric").solve([f]).transfer_impedance()[0]
    assert abs(full - mag) < 1e-3 * abs(full)
    assert abs(ele) < 1e-3 * abs(mag)
    # contributions add (approximately; each diagnostic network drops some loading)
    assert abs(full - (mag + ele)) < 1e-5 * abs(full)


def test_network_field_matches_static_at_low_freq():
    a = typical(6)
    net = CoilNetwork([a], ground="end")
    r = net.solve([1e3])
    pts = np.array([[0, 0, 0.0], [0.05, 0.01, 0.03]])
    assert np.allclose(net.field_B(r, pts).real, cc.field_B(a, pts), rtol=1e-6)


def test_enum_arguments_validated():
    from coilcal.types import Coupling, Grounding, Port, TerminalEnd

    a = typical(4)
    with pytest.raises(ValueError, match="not a valid Coupling"):
        CoilNetwork([a], coupling="magnetc")
    with pytest.raises(ValueError, match="not a valid Grounding"):
        CoilNetwork([a], ground="middle")
    with pytest.raises(IndexError):
        CoilNetwork([a], ports=[Port((1, TerminalEnd.START), None)])
    # strings and enums are interchangeable
    z1 = CoilNetwork([a], ground="end", coupling="full").solve([1e6]).z
    z2 = CoilNetwork([a], ground=Grounding.END, coupling=Coupling.FULL).solve([1e6]).z
    assert np.array_equal(z1, z2)
