"""K3: the port's dense LU against ``numpy.linalg.solve``.

The solution difference is judged against cond(A)·ε (two backward-stable solvers with
different pivot or summation order may differ by that much), the residual against numpy's own.
"""

import numpy as np
import pytest

import coilcal.capacitance as cap
from coilcal.geometry import Former, SolenoidCoil
from coilcal.materials import Dielectric

EPS = np.finfo(float).eps


def _check(port, a, b):
    x, secs = port("solve", a, b)
    xr = np.linalg.solve(a, b)
    assert x.shape == xr.shape and x.dtype == xr.dtype
    assert float(secs) >= 0
    res = np.linalg.norm(a @ x - b) / np.linalg.norm(b)
    res_np = np.linalg.norm(a @ xr - b) / np.linalg.norm(b)
    assert res <= max(4 * res_np, 4 * len(a) * EPS)
    dx = np.linalg.norm(x - xr) / np.linalg.norm(xr)
    assert dx <= 10 * np.linalg.cond(a) * EPS
    return x


# sizes straddle the panel width (64) and the micro-tile edges
@pytest.mark.parametrize("n", [1, 2, 5, 63, 64, 65, 130, 257])
@pytest.mark.parametrize("cplx", [False, True])
@pytest.mark.parametrize("k", [None, 1, 7])
def test_random_systems(port, n, cplx, k):
    rng = np.random.default_rng(n * 100 + (k or 0) + cplx)
    shape_b = (n,) if k is None else (n, k)
    a = rng.normal(size=(n, n)) + n * np.eye(n) * rng.uniform(0, 1)
    b = rng.normal(size=shape_b)
    if cplx:
        a = a + 1j * rng.normal(size=(n, n))
        b = b + 1j * rng.normal(size=shape_b)
    _check(port, a, b)


def test_pivoting_is_needed(port):
    # zero leading pivot: fails without row interchanges
    a = np.array([[0.0, 1.0, 2.0], [1.0, 0.0, 3.0], [4.0, -3.0, 8.0]])
    _check(port, a, np.array([1.0, 2.0, 3.0]))


def test_mixed_real_matrix_complex_rhs(port):
    rng = np.random.default_rng(3)
    a = rng.normal(size=(20, 20))
    _check(port, a, rng.normal(size=(20, 2)) + 1j * rng.normal(size=(20, 2)))


def test_singular_matrix_is_an_error(port):
    with pytest.raises(RuntimeError, match="singular"):
        port("solve", np.zeros((3, 3)), np.ones(3))


@pytest.mark.parametrize("tan_delta", [0.0, 0.02])
def test_capacitance_system(port, tan_delta, monkeypatch):
    """A real charge-simulation system (ill-conditioned) and the capacitance derived from it."""
    ins, frm = Dielectric(3.6, tan_delta), Dielectric(2.6, tan_delta)
    coil = SolenoidCoil(1e-3, 1.3e-3, 0.05, 6, insulation_d=1.1e-3, insulation=ins,
                        former=Former(2e-3, frm, 5e-3))  # fmt: skip
    captured = []
    orig = np.linalg.solve
    monkeypatch.setattr(np.linalg, "solve", lambda a, b: captured.append((a, b)) or orig(a, b))
    cap._CACHE.clear()
    c_ref = cap.capacitance_matrix([coil], n_sub=8)
    monkeypatch.undo()
    cap._CACHE.clear()
    (a, b), *_ = captured
    assert np.iscomplexobj(a) == (tan_delta > 0)
    x = _check(port, a, b)
    n_total, m = b.shape[1], 8
    c = x[: n_total * m].reshape(n_total, m, n_total).sum(axis=1)
    c = 0.5 * (c + c.T)
    c = c if tan_delta else c.real
    assert np.max(np.abs(c - c_ref)) <= 1e-12 * np.max(np.abs(c_ref))
