"""Live differential tests of the Rust/WASM port against the Python reference.

A session fixture builds ``rust/`` (``cargo build --release``) and keeps one check-binary
process alive; ``port(name, *arrays)`` sends a request in the binary wire format described in
``rust/crates/check/src/wire.rs`` and returns the response arrays. ``--port-backend`` picks the
WASM build run under Node's ``node:wasi`` (default) or the native build. Missing cargo or
Node skips these tests.
"""

from __future__ import annotations

import shutil
import struct
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import IO

import numpy as np
import pytest

RUST = Path(__file__).parents[2] / "rust"
RUNNER = Path(__file__).with_name("run_wasi.mjs")
WASM_TARGET = "wasm32-wasip1"

Port = Callable[..., list[np.ndarray]]


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--port-backend",
        choices=("wasm", "native"),
        default="wasm",
        help="run the port tests against the WASM build under Node (default) or natively",
    )


def _write_array(out: IO[bytes], a: np.ndarray) -> None:
    a = np.asarray(a)
    cplx = np.iscomplexobj(a)
    a = np.asarray(a, dtype=np.complex128 if cplx else np.float64, order="C")  # keeps 0-d
    out.write(struct.pack(f"<BB{a.ndim}Q", cplx, a.ndim, *a.shape))
    out.write(a.astype(a.dtype.newbyteorder("<"), copy=False).tobytes())


def _read_exact(inp: IO[bytes], n: int) -> bytes:
    b = inp.read(n)
    if len(b) != n:
        raise RuntimeError("check binary closed its output (crashed?)")
    return b


def _read_array(inp: IO[bytes]) -> np.ndarray:
    cplx, ndim = _read_exact(inp, 2)
    shape = struct.unpack(f"<{ndim}Q", _read_exact(inp, 8 * ndim))
    dtype = np.dtype("<c16" if cplx else "<f8")
    n = int(np.prod(shape))
    return np.frombuffer(_read_exact(inp, n * dtype.itemsize), dtype).reshape(shape).copy()


class CheckProcess:
    def __init__(self, cmd: list[str]) -> None:
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def __call__(self, name: str, *arrays: object) -> list[np.ndarray]:
        assert self.proc.stdin is not None and self.proc.stdout is not None
        out, inp = self.proc.stdin, self.proc.stdout
        out.write(struct.pack("<I", len(name)) + name.encode())
        out.write(struct.pack("<I", len(arrays)))
        for a in arrays:
            _write_array(out, np.asarray(a))
        out.flush()
        if _read_exact(inp, 1)[0]:
            (n,) = struct.unpack("<I", _read_exact(inp, 4))
            raise RuntimeError(f"{name}: {_read_exact(inp, n).decode()}")
        (n,) = struct.unpack("<I", _read_exact(inp, 4))
        return [_read_array(inp) for _ in range(n)]

    def close(self) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.close()
        self.proc.wait(timeout=10)


@pytest.fixture(scope="session")
def port(request: pytest.FixtureRequest) -> Iterator[Port]:
    backend = request.config.getoption("--port-backend")
    cargo = shutil.which("cargo")
    if cargo is None:
        pytest.skip("cargo not found: Rust port not built")
    cmd = [cargo, "build", "--release", "--quiet", "-p", "coilcal-check"]
    if backend == "wasm":
        node = shutil.which("node")
        if node is None:
            pytest.skip("node not found: cannot run the WASM build")
        cmd += ["--target", WASM_TARGET]
    subprocess.run(cmd, cwd=RUST, check=True)
    if backend == "wasm":
        wasm = RUST / "target" / WASM_TARGET / "release" / "coilcal-check.wasm"
        proc = CheckProcess([node, "--no-warnings", str(RUNNER), str(wasm)])
    else:
        proc = CheckProcess([str(RUST / "target" / "release" / "coilcal-check")])
    yield proc
    proc.close()
