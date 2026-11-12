import numpy as np
import pytest

import coilcal as cc
from coilcal.circuit import CoilNetwork
from coilcal.vna import (
    driven_port_currents,
    driven_turn_currents,
    incident_voltage,
    series_thru_s,
    shunt_thru_s,
    thru_network,
    z_to_s,
)


def typical(n=10, **kw):
    return cc.SolenoidCoil(wire_d=1.0e-3, pitch=2.0e-3, former_d=0.150, n_turns=n, **kw)


def test_z_to_s_scalar_cases():
    assert z_to_s(np.array([[50.0]]))[0, 0] == pytest.approx(0)
    assert z_to_s(np.array([[1e12]]))[0, 0] == pytest.approx(1, abs=1e-9)
    # a lossless reciprocal network gives a unitary S
    z = 1j * np.array([[30.0, 10.0], [10.0, 70.0]])
    s = z_to_s(z)
    assert np.allclose(s.conj().T @ s, np.eye(2))


def test_incident_voltage():
    assert incident_voltage(0.0) == pytest.approx(np.sqrt(2 * 50 * 1e-3))


@pytest.mark.parametrize("mode,formula", [("series", series_thru_s), ("shunt", shunt_thru_s)])
def test_thru_network_matches_formula_at_low_freq(mode, formula):
    c = typical(10)
    f = 1e5
    s = z_to_s(thru_network(c, mode).solve([f]).z)[0]
    z_dut = cc.ac_resistance(c, f) + 2j * np.pi * f * cc.self_inductance(c, f)
    s11, s21 = formula(z_dut)
    # residual ~1e-4 is the physical capacitance to the reference that the ideal formula lacks
    assert s[0, 0] == pytest.approx(s11, abs=1e-3)
    assert s[1, 0] == pytest.approx(s21, abs=1e-3)
    assert s[0, 1] == pytest.approx(s[1, 0], abs=1e-12)


def test_series_thru_notch_at_srf():
    c = typical(20)
    net = thru_network(c, "series")
    s21 = z_to_s(net.solve(np.geomspace(1e6, 3e7, 400)).z)[:, 1, 0]
    assert np.abs(s21).min() < 0.05  # parallel resonance blocks transmission


def test_driven_currents_consistent_with_s():
    a, b = typical(10), typical(5, position=[0, 0, 0.065])
    res = CoilNetwork([a, b], ground="end").solve([1e6, 5e6])
    vp = incident_voltage(0.0)
    i_turn, i_port = driven_turn_currents(res, [2 * vp, 0.0])
    s = z_to_s(res.z)
    # transmitted wave at port 2: b2 = -I2 * sqrt(z0) ... V2 = -z0 I2 -> b2 = V2/sqrt(z0)
    b2 = -50 * i_port[:, 1] / np.sqrt(50)
    a1 = vp / np.sqrt(50)
    assert np.allclose(b2 / a1, s[:, 1, 0])
    # first turn of A carries the port-1 current up to capacitive leakage at the terminal
    assert abs(i_turn[0, 0]) == pytest.approx(abs(i_port[0, 0]), rel=1e-2, abs=0)
    assert np.allclose(driven_port_currents(res.z, [2 * vp, 0]), i_port)
