"""K1, K2: special functions of the port against ``scipy.special``.

The elliptic integrals are a port of the same Cephes routines scipy uses, so they agree to the
last bit except where the two ``log`` implementations differ: measured ellipk 0, ellipkm1 0,
ellipe 1.4e-16. jve (Amos port vs Amos) 1.1e-15, J0/J1 ratio 1.2e-15.
"""

import numpy as np
import pytest
from scipy import special as sp

RTOL_ELLIP = 1e-14  # plan target; kept although the agreement is now ~1e-16
RTOL_BESSEL = 1e-13

rng = np.random.default_rng(20261111)
M = np.concatenate(
    [
        [0.0, 5e-324, 1e-3 * (1 - 1e-12), 1e-3, 1e-3 * (1 + 1e-12)],  # _M_SERIES threshold
        np.linspace(0, 1, 2001)[:-1],
        np.geomspace(1e-300, 0.1, 500),
        1 - np.geomspace(1e-16, 0.1, 500),  # m -> 1
        rng.uniform(0, 1, 5000),
        [-1e-3, -0.5, -10.0],  # negative m is valid for both
    ]
)
P = np.concatenate([np.geomspace(1e-300, 1, 1000), rng.uniform(0, 1, 2000), [1.0]])
# skin-effect argument (1 - j)·a/δ with a/δ from 1e-3 to 1e3
X = np.concatenate([np.geomspace(1e-3, 1e3, 1000), rng.uniform(0, 1e3, 1000)])
Z = (1 - 1j) * X


@pytest.mark.parametrize("name", ["ellipk", "ellipe"])
def test_elliptic(port, name):
    (got,) = port(name, M)
    assert got == pytest.approx(getattr(sp, name)(M), rel=RTOL_ELLIP, abs=0)


def test_ellipkm1(port):
    (got,) = port("ellipkm1", P)
    assert got == pytest.approx(sp.ellipkm1(P), rel=RTOL_ELLIP, abs=0)


def test_elliptic_special_values(port):
    m = np.array([1.0, 1.5, np.inf, np.nan])
    assert np.array_equal(port("ellipk", m)[0], sp.ellipk(m), equal_nan=True)
    assert np.array_equal(port("ellipe", m)[0], sp.ellipe(m), equal_nan=True)
    assert port("ellipkm1", np.array([0.0]))[0][0] == sp.ellipkm1(0.0) == np.inf


@pytest.mark.parametrize("nu", [0.0, 1.0])
def test_jve(port, nu):
    (got,) = port("jve", nu, Z)
    assert got == pytest.approx(sp.jve(nu, Z), rel=RTOL_BESSEL, abs=0)


def test_bessel_ratio(port):
    """The only use: J0/J1 at (1 - j)·a/δ in the internal impedance."""
    ratio = port("jve", 0.0, Z)[0] / port("jve", 1.0, Z)[0]
    assert ratio == pytest.approx(sp.jve(0, Z) / sp.jve(1, Z), rel=RTOL_BESSEL, abs=0)
