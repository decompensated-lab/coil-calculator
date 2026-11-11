"""K4-K6: ``coilcal.loops`` against its Rust port.

Tolerances follow PLAN.md, except where the reference formula is ill-conditioned; there the
bound is derived from the conditioning and was checked against an exact (50-digit series)
value, which showed the *reference itself* is off by the same amount:

* Just above ``_M_SERIES`` the bracket ``(1 - m/2) K - E = pi m^2/32 + ...`` cancels terms of
  size ``pi/2``, amplifying any difference in K, E by ``16/m^2`` (1.6e7 at m = 1e-3, i.e.
  ~7 digits, not the 3 the plan assumed); reference-vs-exact is up to 2.8e-9 there. With the
  ``ellip`` crate the port differed by up to 8.9e-9; since K and E are the same Cephes code as
  scipy's they agree exactly, but the bound ``1e-13 + 64 ε/m^2`` stays: it is what the formula
  guarantees, and bit-equality would hang on two ``log`` implementations agreeing.
* ``L_int = Im(Z)/ω``: at low frequency Z is nearly real, so its imaginary part carries an
  absolute error of order ε|Z|. Z itself agrees to 1e-15; L_int is compared with an absolute
  bound ``1e-13 |Z|/ω``.
"""

import numpy as np
import pytest
from scipy.constants import mu_0
from scipy.spatial.transform import Rotation as R

import coilcal as cc
import coilcal.loops as L

EPS = np.finfo(float).eps
RTOL = 1e-13
rng = np.random.default_rng(20261112)


def m_of(r1, r2, dz):
    return 4 * r1 * r2 / ((r1 + r2) ** 2 + dz**2)


def assert_close_cancelling(got, ref, m):
    """Elementwise ``|got/ref - 1| <= 1e-13 + 64 ε/m^2`` on the elliptic branch."""
    with np.errstate(divide="ignore"):
        tol = np.where(m < 1e-3, RTOL, RTOL + 64 * EPS / m**2)
    assert np.all(np.abs(got - ref) <= tol * np.abs(ref)), np.max(np.abs(got / ref - 1) / tol)


def test_constants(port):
    mu, rho_cu, _ = port("constants")
    assert mu == mu_0 and rho_cu == L.RHO_CU


def _coaxial_inputs():
    n = 4000
    r1 = rng.uniform(1e-3, 0.2, n)
    r2 = rng.uniform(1e-3, 0.2, n)
    dz = rng.uniform(-1, 1, n) * rng.choice([1e-4, 1e-2, 1.0], n)
    # m on both sides of _M_SERIES = 1e-3 (and exactly on it, up to rounding)
    mt = np.concatenate([1e-3 * np.exp(rng.uniform(-0.05, 0.05, n - 1)), [1e-3]])
    dzt = np.sqrt(4 * r1 * r2 / mt - (r1 + r2) ** 2)
    r = rng.uniform(0.01, 0.1, 200)  # m -> 1: equal radii, dz -> 0 (m rounds to 1 below 1e-7)
    dz1 = r * np.geomspace(1e-7, 1e-1, 200)
    return (
        np.concatenate([r1, r1, r1, r]),
        np.concatenate([r2, r2, r2, r]),
        np.concatenate([dz, dzt, 0 * r1, dz1]),
    )


def test_mutual_coaxial(port):
    r1, r2, dz = _coaxial_inputs()
    (got,) = port("mutual_coaxial", r1, r2, dz)
    assert_close_cancelling(got, L.mutual_coaxial(r1, r2, dz), m_of(r1, r2, dz))


def test_mutual_coaxial_touching_is_infinite(port):
    (got,) = port("mutual_coaxial", np.array([0.05]), np.array([0.05]), np.array([0.0]))
    assert got[0] == L.mutual_coaxial(0.05, 0.05, 0.0)[()] == np.inf


def test_mutual_coaxial_test_suite_geometries(port):
    # tests/test_coilcal.py: both branches around the threshold, and the Maxwell check
    for args in [(0.05, 0.05, np.array([3.0, 3.2])), (0.07, 0.05, np.array([0.01, 0.05]))]:
        r1, r2, dz = np.broadcast_arrays(*args)
        (got,) = port("mutual_coaxial", r1, r2, dz)
        assert_close_cancelling(got, L.mutual_coaxial(r1, r2, dz), m_of(r1, r2, dz))


def test_a_phi_over_rho(port):
    n = 6000
    a = rng.uniform(1e-3, 0.2, n)
    rho = a * rng.choice([0.0, 1e-6, 1e-3, 0.1, 1.0, 10.0], n) * rng.uniform(0, 2, n)
    z = rng.uniform(-0.5, 0.5, n) * rng.choice([0.0, 1e-3, 1.0], n)
    # the existing continuity test's sweep straddles the threshold
    rho2 = np.geomspace(1e-6, 1e-2, 400)
    a = np.concatenate([a, np.full(400, 0.075)])
    rho = np.concatenate([rho, rho2])
    z = np.concatenate([z, np.full(400, 0.01)])
    (got,) = port("a_phi_over_rho", a, rho, z)
    ref = L.a_phi_over_rho(a, rho, z)
    assert np.count_nonzero(rho == 0) > 100  # on axis
    assert_close_cancelling(got, ref, m_of(a, rho, z))


def _freqs():
    return np.concatenate([[0.0], np.geomspace(1.0, 1e10, 999)])


def test_skin_depth(port):
    f = np.geomspace(1.0, 1e10, 1000)
    rho = rng.uniform(1e-8, 1e-6, 1000)
    (got,) = port("skin_depth", f, rho)
    ref = np.array([L.skin_depth(x, y) for x, y in zip(f, rho, strict=True)])
    assert got == pytest.approx(ref, rel=RTOL, abs=0)


def test_internal_impedance_and_inductance(port):
    f = _freqs()
    a = rng.uniform(1e-5, 3e-3, len(f))  # a/δ from ~1e-4 to ~1e3, plus DC
    rho = np.full(len(f), L.RHO_CU)
    (z,) = port("internal_impedance_per_length", a, f, rho)
    zr = np.array([L.internal_impedance_per_length(x, y) for x, y in zip(a, f, strict=True)])
    assert z == pytest.approx(zr, rel=RTOL, abs=0)

    (li,) = port("internal_inductance_per_length", a, f, rho)
    lr = np.array([L.internal_inductance_per_length(x, y) for x, y in zip(a, f, strict=True)])
    assert li[0] == lr[0] == mu_0 / (8 * np.pi)  # DC branch
    omega = 2 * np.pi * f[1:]
    assert np.all(np.abs(li[1:] - lr[1:]) <= RTOL * np.abs(zr[1:]) / omega)


def test_loop_self_inductance(port):
    f = _freqs()
    radius = rng.uniform(1e-3, 0.3, len(f))
    a = rng.uniform(1e-5, 3e-3, len(f))
    (got,) = port("loop_self_inductance", radius, a, f)
    ref = np.array([L.loop_self_inductance(*t) for t in zip(radius, a, f, strict=True)])
    z = np.abs([L.internal_impedance_per_length(x, y) for x, y in zip(a, f, strict=True)])
    # L_int carries an absolute error ~ε|Z|/ω (see module docstring); DC has no such term
    scale = np.abs(ref) + np.divide(2 * np.pi * radius * z, 2 * np.pi * f, where=f > 0, out=0 * f)
    assert np.all(np.abs(got - ref) <= RTOL * scale)


def typical(n, **kw):
    return cc.SolenoidCoil(wire_d=1.0e-3, pitch=2.0e-3, former_d=0.150, n_turns=n, **kw)


def _ring_cases():
    """Ring families of tests/test_coilcal.py (general poses, symmetric zero, tiny tilt)."""
    ident = R.identity()
    yield 0.07, ident, [[0, 0, 0.0]], 0.05, ident, [[0, 0, 0.01], [0, 0, 0.05]], 64
    a = typical(10)
    poses = [
        ([0.03, 0.0, 0.06], R.from_euler("xy", [0, 0], degrees=True)),
        ([0.03, 0.01, 0.06], R.from_euler("xy", [20, 10], degrees=True)),
        ([0.25, 0.0, 0.03], R.from_euler("xy", [0, 90], degrees=True)),
        ([0.25, 0.0, 0.0], R.from_euler("y", 90, degrees=True)),  # M = 0 by symmetry
        ([0.0, 0.0, 0.05], R.from_euler("x", 1e-9)),  # nearly coaxial
    ]
    for pos, rot in poses:
        b = typical(8, position=pos, orientation=rot)
        for n_phi in (64, 512):
            yield (
                a.mean_radius, a.orientation, a.turn_centers(),
                b.mean_radius, b.orientation, b.turn_centers(), n_phi,
            )  # fmt: skip
    # random poses for both families, including a rotated source family
    for _ in range(3):
        ra, rb = R.random(random_state=rng), R.random(random_state=rng)
        ca, cb = rng.normal(0, 0.05, (4, 3)), rng.normal(0, 0.05, (5, 3)) + [0, 0, 0.3]
        yield 0.04, ra, ca, 0.06, rb, cb, 256


@pytest.mark.parametrize("case", list(_ring_cases()))
def test_mutual_rings(port, case):
    radius_a, rot_a, ca, radius_b, rot_b, cb, n_phi = case
    ref = L.mutual_rings(radius_a, rot_a, ca, radius_b, rot_b, cb, n_phi=n_phi)
    (got,) = port(
        "mutual_rings",
        radius_a, rot_a.as_quat(), np.asarray(ca, float),
        radius_b, rot_b.as_quat(), np.asarray(cb, float), n_phi,
    )  # fmt: skip
    assert got.shape == ref.shape
    # same quadrature, different summation order and rotation arithmetic
    assert np.max(np.abs(got - ref)) <= 1e-12 * np.abs(ref).sum()
