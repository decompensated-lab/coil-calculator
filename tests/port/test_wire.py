import numpy as np
import pytest


def test_echo_round_trips_bit_exactly(port):
    rng = np.random.default_rng(0)
    arrays = [
        np.float64(np.pi),
        rng.normal(size=(3, 4)),
        rng.normal(size=5) + 1j * rng.normal(size=5),
        np.array([np.nan, -0.0, np.inf, 5e-324, np.finfo(float).max]),
        np.empty((0, 2)),
    ]
    back = port("echo", *arrays)
    assert len(back) == len(arrays)
    for a, b in zip(arrays, back, strict=True):
        a = np.asarray(a)
        assert b.shape == a.shape and b.dtype.kind == a.dtype.kind
        assert a.tobytes() == b.tobytes()


def test_large_array_round_trips(port):
    a = np.random.default_rng(1).normal(size=(500, 500, 2)).view(complex)[..., 0]
    assert port("echo", a)[0].tobytes() == a.tobytes()


def test_unknown_function_is_an_error(port):
    with pytest.raises(RuntimeError, match="unknown function"):
        port("no_such_function")
