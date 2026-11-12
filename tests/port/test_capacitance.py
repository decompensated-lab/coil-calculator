"""``coilcal.capacitance`` against its Rust port.

The assembled system is compared row by row (entries relative to the row's largest; the DFT
rows mix terms of very different size, so single entries can be tiny), the capacitance matrix
against its largest entry. The solve then adds ~cond(A)·ε to the solution (see
``test_linalg.py``); C agrees to ~1e-12 even for the 2454-unknown tight case.
"""

from unittest import mock

import numpy as np
import pytest
from conftest import coil_table
from scipy.constants import epsilon_0
from scipy.spatial.transform import Rotation as R

from coilcal import capacitance as cap
from coilcal.geometry import Former, SolenoidCoil
from coilcal.gui import model as gm
from coilcal.materials import Dielectric

# System rows: measured <= 3.6e-13, in the highest DFT harmonic rows of a turn acting on
# itself, where the sum over collocation points cancels (large self-term values, small
# high-harmonic result) and numpy's einsum adds in a different order.
RTOL_ROW = 1e-12
# Capacitance matrix: <= 1e-13 typical. The near-touching "tight" case (cond(A) = 7.7e8)
# differs by 4.7e-12, and that is C's own sensitivity: numpy re-solving the port's matrix
# (rows equal to ~1e-13) moves C by 6e-12, the port's solver on the reference matrix by 5.5e-12.
RTOL_C = 1e-11
DEFAULTS = (0.6, 256, 0.6)  # alpha, n_phi, h_wire

ENAMEL, PMMA = Dielectric(3.6, 0.02), Dielectric(2.6, 0.01)
TUBE = Former(3e-3, PMMA, 1e-2)


def coil(n=6, pitch=2e-3, ins_d=1.06e-3, ins=ENAMEL, former=TUBE, **kw):
    return SolenoidCoil(1e-3, pitch, 0.15, n, insulation_d=ins_d, insulation=ins, former=former,
                        **kw)  # fmt: skip


def reference(coils, n_sub=None):
    cap._CACHE.clear()
    with mock.patch.object(np.linalg, "solve", wraps=np.linalg.solve) as spy:
        c = cap.capacitance_matrix(coils, n_sub=n_sub)
    cap._CACHE.clear()
    a, rhs = spy.call_args.args
    return a, rhs, c


lossless = {"ins": Dielectric(3.6), "former": Former(3e-3, Dielectric(2.6), 1e-2)}
CASES = {
    "gui-default": gm.Params().coils(),
    "gui-single": gm.Params(b_enabled=False).coils(),
    "lossless": [coil(**lossless), coil(4, **lossless, position=[0, 0, 0.04])],
    "bare-no-former": [coil(ins_d=None, ins=Dielectric(), former=None)],
    "insulation-only": [coil(former=None)],
    "former-only": [coil(ins_d=None, ins=Dielectric())],
    "tight": [coil(8, pitch=1.07e-3)],
    # coaxial, axis reversed: enters its group with sgn = -1
    "flipped": [coil(), coil(4, position=[0, 0, 0.05], orientation=R.from_euler("x", 180, True))],
    # identical formers touching end to end are merged into one tube
    "merged-formers": [coil(4, former=Former(3e-3, PMMA, 0.0)),
                       coil(4, former=Former(3e-3, PMMA, 0.0), position=[0, 0, 8e-3])],
    # non-coaxial groups: thin-wire coupling
    "offset": gm.Params(offset_mm=20.0).coils(),
    "tilted": [coil(), coil(3, former=None, position=[0.0, 0.25, 0.03],
                            orientation=R.from_euler("y", 70, True))],
}  # fmt: skip


@pytest.mark.parametrize("name", CASES)
def test_system_and_capacitance(port, name):
    coils = CASES[name]
    a_ref, rhs_ref, c_ref = reference(coils)
    a, rhs, _ = port("capacitance_system", coil_table(coils), 0, *DEFAULTS)
    assert a.shape == a_ref.shape  # same panel count: identical meshing decisions
    assert a.dtype == a_ref.dtype and rhs.dtype == rhs_ref.dtype
    rowmax = np.abs(a_ref).max(axis=1, keepdims=True)
    assert np.all(np.abs(a - a_ref) <= RTOL_ROW * rowmax)
    assert rhs == pytest.approx(rhs_ref, rel=1e-15, abs=0)

    c, _ = port("capacitance_matrix", coil_table(coils), 0, *DEFAULTS)
    assert c.dtype == c_ref.dtype
    assert np.all(np.abs(c - c_ref) <= RTOL_C * np.abs(c_ref).max())


def test_explicit_n_sub(port):
    coils = CASES["insulation-only"]
    _, _, c_ref = reference(coils, n_sub=10)
    c, _ = port("capacitance_matrix", coil_table(coils), 10, *DEFAULTS)
    assert np.all(np.abs(c - c_ref) <= RTOL_C * np.abs(c_ref).max())


@pytest.mark.parametrize("name", CASES)
def test_auto_n_sub(port, name):
    (n,) = port("auto_n_sub", coil_table(CASES[name]))
    assert n == cap.auto_n_sub(CASES[name])


@pytest.mark.parametrize(
    "coils, n_sub, match",
    [
        (CASES["insulation-only"], 7, "n_sub must be even"),
        (CASES["insulation-only"], 2, "n_sub must be even"),
        # same axis, different former walls overlapping axially
        ([coil(4, former=Former(3e-3, PMMA, 1e-2)),
          coil(4, former=Former(2e-3, PMMA, 1e-2), position=[0, 0, 0.012])], 0, "formers intersect"),
    ],
)  # fmt: skip
def test_errors(port, coils, n_sub, match):
    with pytest.raises(ValueError, match=match):
        cap._CACHE.clear()
        cap.capacitance_matrix(coils, n_sub=n_sub or None)
    with pytest.raises(RuntimeError, match=match):
        port("capacitance_matrix", coil_table(coils), n_sub, *DEFAULTS)


def test_winding_inside_former_is_an_error(port):
    # the geometry class prevents this for one coil; a second coil's former can cut a winding
    a = coil(4, former=None)
    b = SolenoidCoil(1e-3, 2e-3, 0.152, 2, position=[0, 0, 0.01],
                     former=Former(3e-3, PMMA, 1e-2))  # fmt: skip
    with pytest.raises(ValueError, match="intersects a coil former"):
        cap._CACHE.clear()
        cap.capacitance_matrix([a, b])
    with pytest.raises(RuntimeError, match="intersects a coil former"):
        port("capacitance_matrix", coil_table([a, b]), 0, *DEFAULTS)


def test_constants(port):
    assert port("constants")[2] == epsilon_0
    x8, w8, x2, w2 = port("gauss_legendre")
    for got, (x, w) in [((x8, w8), np.polynomial.legendre.leggauss(8)),
                        ((x2, w2), np.polynomial.legendre.leggauss(2))]:  # fmt: skip
        assert got[0].tobytes() == x.tobytes() and got[1].tobytes() == w.tobytes()


def test_ring_kernels(port):
    rng = np.random.default_rng(7)
    n = 5000
    b = rng.uniform(1e-3, 0.2, n)
    rho = b * rng.choice([1e-3, 0.5, 1.0, 1.0 + 1e-6, 2.0, 50.0], n) * rng.uniform(0.9, 1.1, n)
    z = b * rng.choice([0.0, 1e-6, 1e-2, 1.0, 30.0], n) * rng.uniform(-1, 1, n)
    (phi,) = port("ring_potential", b, rho, z)
    assert phi == pytest.approx(cap.ring_potential(b, rho, z), rel=1e-14, abs=0)
    er_ref, ez_ref = cap.ring_field(b, rho, z)
    (er,), (ez,) = port("ring_field_rho", b, rho, z), port("ring_field_z", b, rho, z)
    # E_rho = (K - (b²-ρ²+z²)/q² E)/(ρ√d²): near the axis (small m = 4bρ/d²) the bracket
    # cancels like the one in loops.py (reference and port alike; measured 4e-10 at ρ/b = 1e-3),
    # so the same conditioning bound applies. The solver only evaluates near the source ring.
    m = 4 * b * rho / ((b + rho) ** 2 + z**2)
    tol = (1e-13 + 64 * np.finfo(float).eps / m**2) * np.hypot(er_ref, ez_ref)
    assert np.all(np.abs(er - er_ref) <= tol)
    assert np.all(np.abs(ez - ez_ref) <= tol)
