"""Inductance, SRF estimates, mutual inductance and the ring field against the Rust port.

References: ``coilcal.inductance``, ``coilcal.srf`` (the two estimates the app shows),
``coilcal.mutual`` (ring method) and magpylib's ``current.Circle`` exactly as
``CoilNetwork.unit_fields`` uses it.
"""

import magpylib as magpy
import numpy as np
import pytest
from conftest import coil_table
from scipy.spatial.transform import Rotation as R

import coilcal as cc
from coilcal import inductance as ind
from coilcal import mutual, srf
from coilcal.materials import Dielectric

RTOL = 1e-13
FREQS = np.array([0.0, 1e3, 5e6, 1e9])  # 0 = DC (Python None)


def typical(n=10, **kw):
    return cc.SolenoidCoil(wire_d=1.0e-3, pitch=2.0e-3, former_d=0.150, n_turns=n, **kw)


COILS = [
    typical(1), typical(2), typical(5), typical(10), typical(50), typical(100),
    cc.SolenoidCoil(0.2e-3, 0.25e-3, 0.01, 40),  # long thin coil, l/D ~ 1
    cc.SolenoidCoil(2e-3, 6e-3, 0.3, 3),  # short wide coil
    cc.SolenoidCoil(1e-3, 1.2e-3, 0.05, 20, insulation_d=1.1e-3, insulation=Dielectric(3.6)),
]  # fmt: skip


def test_coil_quantities(port):
    l, l_rosa, r_ac, f_srf, ks, km, l_sheet, l_wheeler, c_med = port(
        "coil_quantities", coil_table(COILS), FREQS
    )
    f_py = [f or None for f in FREQS]
    for i, c in enumerate(COILS):
        assert l[i] == pytest.approx([ind.self_inductance(c, f) for f in f_py], rel=RTOL, abs=0)
        assert l_rosa[i] == pytest.approx(
            [ind.rosa_inductance(c, f) for f in f_py], rel=RTOL, abs=0
        )
        assert r_ac[i] == pytest.approx([ind.ac_resistance(c, f) for f in f_py], rel=RTOL, abs=0)
        assert f_srf[i] == pytest.approx([srf.srf_lumped(c, f) for f in f_py], rel=RTOL, abs=0)
        corr = np.array([ind.rosa_corrections(c, f) for f in f_py])
        assert ks[i] == pytest.approx(corr[:, 0], rel=RTOL, abs=0)
        assert km[i] == pytest.approx(corr[:, 1], rel=RTOL, abs=0)
        assert l_sheet[i] == pytest.approx(ind.sheet_inductance(c), rel=RTOL, abs=0)
        assert l_wheeler[i] == pytest.approx(ind.wheeler_inductance(c), rel=RTOL, abs=0)
        assert c_med[i] == pytest.approx(srf.self_capacitance_medhurst(c), rel=RTOL, abs=0)


def test_nagaoka(port):
    ratio = np.geomspace(1e-3, 1e3, 400)  # D/l from very long to very short coils
    d, length = ratio * 0.01, np.full_like(ratio, 0.01)
    (got,) = port("nagaoka", d, length)
    ref = np.array([ind.nagaoka(x, y) for x, y in zip(d, length, strict=True)])
    assert got == pytest.approx(ref, rel=RTOL, abs=0)


def _pairs():
    a = typical(10)
    yield "coaxial", a, cc.SolenoidCoil(0.5e-3, 1e-3, 0.10, 15, position=[0, 0, 0.06])
    yield "flipped", a, typical(10, position=[0, 0, 0.05], orientation=R.from_euler("x", 180, True))
    for pos, euler in [([0.03, 0.0, 0.06], [0, 0]), ([0.03, 0.01, 0.06], [20, 10]),
                       ([0.25, 0.0, 0.03], [0, 90])]:  # fmt: skip
        rot = R.from_euler("xy", euler, degrees=True)
        yield f"general {pos} {euler}", a, typical(8, position=pos, orientation=rot)
    yield (
        "zero by symmetry",
        a,
        typical(8, position=[0.25, 0, 0], orientation=R.from_euler("y", 90, True)),
    )
    yield "tiny tilt", a, typical(6, position=[0, 0, 0.05], orientation=R.from_euler("x", 1e-9))


PAIRS = {name: (a, b) for name, a, b in _pairs()}


@pytest.mark.parametrize("name", PAIRS)
@pytest.mark.parametrize("n_phi", [None, 128])
def test_mutual_matrix(port, name, n_phi):
    a, b = PAIRS[name]
    ref = mutual.mutual_matrix(a, b, n_phi=n_phi)
    (got,) = port("mutual_matrix", coil_table([a, b]), n_phi or 0, 1e-9, 1 << 14)
    assert got.shape == ref.shape
    # same quadrature and convergence decisions; summation order differs (cf. mutual_rings)
    assert np.max(np.abs(got - ref)) <= 1e-12 * np.abs(ref).sum()


def test_mutual_non_convergence_is_an_error(port):
    a, b = PAIRS["general [0.03, 0.01, 0.06] [20, 10]"]
    with pytest.raises(RuntimeError, match="did not converge"):
        mutual.mutual_matrix(a, b, max_n_phi=64)
    with pytest.raises(RuntimeError, match="did not converge"):
        port("mutual_matrix", coil_table([a, b]), 0, 1e-9, 64)


def _unit_fields_ref(coils, pts):
    """``CoilNetwork.unit_fields`` without building a network."""
    unit = [
        magpy.current.Circle(position=c0, orientation=c.orientation, diameter=c.mean_d, current=1.0)
        for c in coils
        for c0 in c.turn_centers()
    ]
    return np.asarray(magpy.getB(unit, pts, squeeze=False)).reshape(len(unit), len(pts), 3)


def test_unit_fields(port):
    rng = np.random.default_rng(3)
    a = typical(5)
    b = typical(3, position=[0.02, -0.01, 0.06], orientation=R.from_euler("xz", [30, 40], True))
    r = a.mean_radius
    pts = np.concatenate(
        [
            rng.normal(0, 0.1, (300, 3)),  # around both coils
            np.column_stack([np.zeros(50), np.zeros(50), np.linspace(-0.2, 0.2, 50)]),  # axis
            [[r * (1 + 1e-6), 0, 0], [r, 0, 1e-7], [0, r * (1 - 1e-3), 4e-3]],  # near a wire
            [[r, 0, a.turn_z()[0]]],  # on a wire: magpylib's singular case, B = 0
            rng.normal(0, 10.0, (50, 3)),  # far field
        ]
    )
    (got,) = port("unit_fields", coil_table([a, b]), pts)
    ref = _unit_fields_ref([a, b], pts)
    assert got.shape == ref.shape
    mag = np.linalg.norm(ref, axis=-1, keepdims=True)
    assert np.all(np.abs(got - ref) <= RTOL * mag)
    assert np.all(got[0, 353] == 0) and np.all(ref[0, 353] == 0)


def test_axis_fields(port):
    c = typical(20, position=[0.1, 0.2, 0.3])  # local z: the pose does not matter
    z = np.linspace(-0.3, 0.3, 301)
    rings, sheet = port("b_axis", coil_table([c]), z)
    assert rings == pytest.approx(cc.B_axis_rings(c, z), rel=RTOL, abs=0)
    assert sheet == pytest.approx(cc.B_axis_sheet(c, z), rel=RTOL, abs=0)
