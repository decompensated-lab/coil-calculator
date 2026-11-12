"""``coilcal.wirepair`` against its Rust port."""

import numpy as np
import pytest
from scipy.constants import epsilon_0

from coilcal.materials import Dielectric
from coilcal.wirepair import (
    InsulatedWire,
    bare_pair_capacitance,
    effective_radius,
    pair_capacitance,
)

MM = 1e-3
PTFE = Dielectric(2.1, 2e-4)  # GUI default
GUI = InsulatedWire(1.0 * MM, 1.5 * MM, PTFE)


def table(w1, w2):
    return np.array([[w.a, w.b, w.eps.real, w.eps.imag] for w in (w1, w2)])


CASES = {
    "gui-default-touching": (GUI, GUI, 1.5 * MM),
    "gap": (GUI, GUI, 2.0 * MM),
    "far": (GUI, GUI, 20 * MM),
    "bare": (InsulatedWire(1 * MM), InsulatedWire(1 * MM), 1.3 * MM),
    "unequal": (InsulatedWire(0.5 * MM, 0.9 * MM, Dielectric(3.6, 0.02)),
                InsulatedWire(1.2 * MM, 1.4 * MM, Dielectric(2.6)), 1.4 * MM),
    "bare-and-insulated": (InsulatedWire(1 * MM), GUI, 1.6 * MM),
    "lossless": (InsulatedWire(1 * MM, 1.6 * MM, Dielectric(4.0)),
                 InsulatedWire(1 * MM, 1.6 * MM, Dielectric(4.0)), 1.7 * MM),
}  # fmt: skip


def _points(w1, w2, s):
    rng = np.random.default_rng(5)
    xs = np.concatenate([
        [-s / 2, -s / 2 + 0.9 * w1.a, -s / 2 - (w1.a + w1.b) / 2, s / 2 + (w2.a + w2.b) / 2],
        rng.uniform(-3 * s, 3 * s, 200),
    ])  # fmt: skip
    ys = np.concatenate([[0.0, 0.0, 0.0, 1e-5], rng.uniform(-2 * s, 2 * s, 200)])
    return np.column_stack([xs, ys])  # conductor, sleeve of each wire, air


@pytest.mark.parametrize("name", CASES)
@pytest.mark.parametrize("rtol, max_terms", [(1e-9, 1024), (1e-6, 256)])  # result, sweep (GUI)
def test_pair_capacitance(port, name, rtol, max_terms):
    w1, w2, s = CASES[name]
    ref = pair_capacitance(w1, w2, spacing=s, rtol=rtol, max_terms=max_terms)
    pts = _points(w1, w2, s)
    c, n_terms, conv, v, phi, tand, g = port(
        "pair_capacitance", table(w1, w2), s, rtol, max_terms, pts
    )
    assert (int(n_terms), bool(conv)) == (ref.n_terms, ref.converged)  # same decisions
    assert complex(c) == pytest.approx(ref.c_complex, rel=1e-12, abs=0)
    assert v == pytest.approx(ref.conductor_potentials, rel=1e-12, abs=1e-12)
    phi_ref = ref.potential(pts[:, 0], pts[:, 1])
    assert np.all(np.abs(phi - phi_ref) <= 1e-12)  # potentials of a 1 V pair
    if ref.c_complex.imag:
        assert float(tand) == pytest.approx(ref.tan_delta, rel=1e-10, abs=0)
        assert float(g) == pytest.approx(ref.conductance(1e6), rel=1e-10, abs=0)


def test_errors(port):
    for w1, w2, s, match in [
        (GUI, GUI, 1.4 * MM, "overlap"),
        (InsulatedWire(1 * MM), InsulatedWire(1 * MM), 1.0 * MM, "bare conductors touch"),
    ]:
        with pytest.raises(ValueError, match=match):
            pair_capacitance(w1, w2, spacing=s)
        with pytest.raises(RuntimeError, match=match):
            port("pair_capacitance", table(w1, w2), s, 1e-9, 1024, np.zeros((0, 2)))


def test_bare_pair_and_effective_radius(port):
    for a1, a2, s in [(0.5e-3, 0.5e-3, 1.1e-3), (0.2e-3, 1e-3, 5e-3), (1e-3, 1e-3, 1.0)]:
        (c,) = port("bare_pair_capacitance", a1, a2, s)
        assert c == pytest.approx(bare_pair_capacitance(a1, a2, s), rel=1e-14, abs=0)
        assert c > 0 and c < 2 * np.pi * epsilon_0 * 10
    with pytest.raises(RuntimeError, match="overlap or touch"):
        port("bare_pair_capacitance", 1e-3, 1e-3, 2e-3)
    ws = [GUI, InsulatedWire(1 * MM), InsulatedWire(0.3 * MM, 2 * MM, Dielectric(7.0))]
    a, b = np.array([w.a for w in ws]), np.array([w.b for w in ws])
    e = np.array([w.dielectric.eps_r for w in ws])
    (got,) = port("effective_radius", a, b, e)
    assert got == pytest.approx([effective_radius(w) for w in ws], rel=1e-15, abs=0)
