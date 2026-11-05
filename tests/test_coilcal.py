import numpy as np
import pytest
from scipy.constants import mu_0
from scipy.spatial.transform import Rotation as R

import coilcal as cc
from coilcal.loops import a_phi_over_rho, internal_inductance_per_length, mutual_coaxial


def typical(n=10, **kw):
    return cc.SolenoidCoil(wire_d=1.0e-3, pitch=2.0e-3, former_d=0.150, n_turns=n, **kw)


# --- geometry ---------------------------------------------------------------------------
def test_geometry_coil64_convention():
    c = typical(10)
    assert c.mean_radius == pytest.approx(0.0755)
    assert c.length == pytest.approx(0.020)
    assert c.wire_length == pytest.approx(10 * np.hypot(2 * np.pi * 0.0755, 2e-3))
    with pytest.raises(ValueError):
        cc.SolenoidCoil(1e-3, 0.5e-3, 0.15, 10)


def test_pose_transforms():
    rot = R.from_euler("zyx", [10, 20, 30], degrees=True)
    c = typical(5, position=[0.1, -0.2, 0.3], orientation=rot)
    assert np.allclose(c.axis, rot.apply([0, 0, 1]))
    pts = np.random.default_rng(0).normal(size=(4, 3))
    assert np.allclose(c.to_local(c.to_global(pts)), pts)


# --- field ------------------------------------------------------------------------------
def test_axis_field_magpylib_vs_exact():
    c = typical(20)
    z = np.linspace(-0.15, 0.15, 31)
    pts = np.column_stack([0 * z, 0 * z, z])
    assert np.allclose(cc.field_B(c, pts)[:, 2], cc.B_axis_rings(c, z), rtol=1e-10)
    # helix ~ current sheet on axis
    assert np.allclose(cc.field_B(c, pts, model="helix")[:, 2], cc.B_axis_sheet(c, z), rtol=1e-3)


def test_field_follows_pose():
    rot = R.from_euler("x", 90, degrees=True)
    c = typical(8, position=[0.01, 0.02, 0.03], orientation=rot)
    b = cc.field_B(c, c.position)
    assert np.allclose(b / np.linalg.norm(b), c.axis)
    assert np.linalg.norm(b) == pytest.approx(cc.B_axis_rings(c, 0.0), rel=1e-10, abs=0)


def test_far_field_dipole():
    c = typical(10)
    z = 5.0
    m = c.n_turns * np.pi * c.mean_radius**2
    assert cc.field_B(c, [0, 0, z])[2] == pytest.approx(
        mu_0 * m / (2 * np.pi * z**3), rel=1e-3, abs=0
    )


# --- loop primitives --------------------------------------------------------------------
def test_vector_potential_series_branch_continuous():
    a, z = 0.075, 0.01
    # straddle m = 1e-3 threshold
    rho = np.geomspace(1e-6, 1e-2, 400)
    g = a_phi_over_rho(a, rho, z)
    assert np.all(np.abs(np.diff(np.log(g))) < 1e-3)


def test_mutual_coaxial_series_vs_elliptic():
    r = 0.05
    d = np.array([3.0, 3.2])  # m around threshold, both branches
    m = mutual_coaxial(r, r, d)
    dip = mu_0 * np.pi * r**4 / (2 * (4 * r**2 + d**2) ** 1.5)
    assert np.allclose(m, dip, rtol=1e-3)


def test_mutual_rings_matches_maxwell_coaxial():
    rot = R.identity()
    ca = np.array([[0, 0, 0.0]])
    cb = np.array([[0, 0, 0.01], [0, 0, 0.05]])
    m = cc.mutual_rings(0.07, rot, ca, 0.05, rot, cb, n_phi=64)
    assert np.allclose(m[0], mutual_coaxial(0.07, 0.05, cb[:, 2]), rtol=1e-12)


def test_internal_inductance_limits():
    a = 0.5e-3
    assert internal_inductance_per_length(a, None) == pytest.approx(mu_0 / (8 * np.pi))
    assert internal_inductance_per_length(a, 10.0) == pytest.approx(
        mu_0 / (8 * np.pi), rel=1e-6, abs=0
    )
    f = 1e9
    hf = mu_0 * cc.skin_depth(f) / (4 * np.pi * a)
    assert internal_inductance_per_length(a, f) == pytest.approx(hf, rel=1e-2, abs=0)


# --- self inductance --------------------------------------------------------------------
def test_nagaoka_known_values():
    assert cc.nagaoka(1, 1) == pytest.approx(0.6884, abs=1e-4)
    assert cc.nagaoka(1, 1e4) == pytest.approx(1.0, abs=1e-3)


@pytest.mark.parametrize("n", [2, 5, 10, 50, 100])
@pytest.mark.parametrize("freq", [None, 5e6])
def test_self_inductance_vs_rosa(n, freq):
    c = typical(n)
    assert cc.self_inductance(c, freq) == pytest.approx(
        cc.rosa_inductance(c, freq), rel=1e-4, abs=0
    )


def test_self_inductance_vs_wheeler_long_coil():
    c = typical(100)  # l/D ~ 1.3, Wheeler good to ~1 % here
    assert cc.self_inductance(c) == pytest.approx(cc.wheeler_inductance(c), rel=0.02, abs=0)


def test_hf_inductance_lower_than_dc():
    c = typical(10)
    assert cc.self_inductance(c, 5e6) < cc.self_inductance(c)


# --- mutual inductance ------------------------------------------------------------------
def test_mutual_coaxial_rings_vs_flux():
    a = typical(10)
    b = cc.SolenoidCoil(0.5e-3, 1e-3, 0.10, 15, position=[0, 0, 0.06])
    assert cc.mutual_inductance(a, b) == pytest.approx(
        cc.mutual_inductance(a, b, method="flux"), rel=1e-6
    )


@pytest.mark.parametrize(
    "pos,euler",
    [
        ([0.03, 0.0, 0.06], [0, 0]),
        ([0.03, 0.01, 0.06], [20, 10]),
        ([0.25, 0.0, 0.03], [0, 90]),
    ],
)
def test_mutual_general_vs_flux_and_reciprocity(pos, euler):
    a = typical(10)
    b = typical(8, position=pos, orientation=R.from_euler("xy", euler, degrees=True))
    m = cc.mutual_inductance(a, b)
    assert m == pytest.approx(cc.mutual_inductance(a, b, method="flux"), rel=1e-5, abs=0)
    assert m == pytest.approx(cc.mutual_inductance(b, a), rel=1e-9, abs=0)


def test_mutual_zero_by_symmetry():
    a = typical(10)
    b = typical(8, position=[0.25, 0, 0], orientation=R.from_euler("y", 90, degrees=True))
    scale = np.abs(cc.mutual_matrix(a, b)).sum()
    assert abs(cc.mutual_inductance(a, b)) < 1e-9 * scale


def test_mutual_general_path_equals_coaxial_path():
    a = typical(10)
    b = typical(6, position=[0, 0, 0.05])
    tiny = b.moved(orientation=R.from_euler("x", 1e-9))  # forces general path
    assert cc.mutual_inductance(a, tiny) == pytest.approx(
        cc.mutual_inductance(a, b), rel=1e-7, abs=0
    )


def test_mutual_sign_flip_and_helix_flux():
    a = typical(10)
    b = typical(10, position=[0, 0, 0.05])
    flipped = b.moved(orientation=R.from_euler("x", 180, degrees=True))
    assert cc.mutual_inductance(a, flipped) == pytest.approx(-cc.mutual_inductance(a, b))
    # helix model of the source coil gives nearly the same linkage
    m_helix = cc.mutual_inductance(
        a, b, method="flux", model="helix", n_r=16, n_phi=16, pts_per_turn=90
    )
    assert m_helix == pytest.approx(cc.mutual_inductance(a, b), rel=2e-3, abs=0)


def test_coupling_and_emf():
    a = typical(10)
    b = typical(10, position=[0, 0, 0.03])
    m = cc.mutual_inductance(a, b)
    k = cc.coupling_coefficient(a, b, m=m)
    assert 0 < k < 1
    v = cc.induced_emf(a, b, 1.0, 1e6, m=m)
    assert v == pytest.approx(-1j * 2 * np.pi * 1e6 * m)
    # loaded with huge impedance -> open circuit EMF
    v_oc = cc.induced_voltage_loaded(a, b, 1.0, 1e6, z_load=1e12, m=m)
    assert v_oc == pytest.approx(v, rel=1e-6, abs=0)


# --- SRF / validity ---------------------------------------------------------------------
def test_quasistatic_report():
    few = cc.check_quasistatic(typical(10), 1e6)
    assert few.ok
    short = cc.check_quasistatic(typical(3), 1e6)
    assert any("Medhurst" in w for w in short.warnings)
    many = cc.check_quasistatic(typical(50), 5e6)
    assert not many.ok
    assert many.srf < 5e6
