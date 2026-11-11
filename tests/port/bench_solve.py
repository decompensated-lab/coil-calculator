"""Solver spike (PLAN.md, K3): real systems from the reference, solved by the port candidates.

Captures the linear systems that ``numpy.linalg.solve`` sees in the reference (capacitance
systems of the default GUI case and of a tight 30-turn case, lossy = complex and lossless =
real, plus one MNA system), caches them under ``rust/target/port-systems/``, and solves each
with the port's LU in the check binary. Reports cond(A), residuals, the solution difference
to numpy (to be read against cond(A)·ε), the difference in the derived capacitance matrix, and
the solve time measured inside the module.

    uv run python tests/port/bench_solve.py [--backend wasm|wasm-nosimd|native] [--repeat N]

Times are the best of ``--repeat`` runs; the first call into a fresh WASM module is slower
while V8 tiers the code up. numpy runs single-threaded only if ``OPENBLAS_NUM_THREADS=1``.
Not collected by pytest (too slow); ``test_linalg.py`` covers correctness in the suite.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from conftest import RUNNER, RUST, WASM_TARGET, CheckProcess

CACHE = RUST / "target" / "port-systems"
EPS = np.finfo(float).eps


def _cases() -> dict:
    from coilcal.gui import model as gm
    from coilcal.materials import Dielectric

    lossless = {"insulation": Dielectric(3.6, 0.0), "former": Dielectric(2.6, 0.0)}
    tight = {"turns": 30, "pitch_mm": 1.2}  # with the default coil B: 2454 unknowns
    return {
        "default": gm.Params(),
        "default-real": gm.Params(
            a=gm.CoilParams(**lossless), b=gm.CoilParams(turns=5, **lossless)
        ),
        "tight30": gm.Params(a=gm.CoilParams(**tight)),
        "tight30-real": gm.Params(
            a=gm.CoilParams(**tight, **lossless), b=gm.CoilParams(turns=5, **lossless)
        ),
    }


def capture() -> None:
    """Run the reference on each case and store its capacitance system (and one MNA system)."""
    from coilcal import capacitance as cap
    from coilcal.circuit import CoilNetwork

    CACHE.mkdir(parents=True, exist_ok=True)
    cases = _cases()
    for name, params in cases.items():
        path = CACHE / f"{name}.npz"
        if path.exists():
            continue
        cap._CACHE.clear()
        with (
            mock.patch.object(cap, "_solve", wraps=cap._solve) as spy_cap,
            mock.patch.object(np.linalg, "solve", wraps=np.linalg.solve) as spy_solve,
        ):
            c = cap.capacitance_matrix(params.coils())
        a, b = spy_solve.call_args.args
        m = spy_cap.call_args.args[1]
        print(f"captured {name}: n = {len(a)}, {a.dtype}; computing cond(A) ...", flush=True)
        np.savez(path, a=a, b=b, x=np.linalg.solve(a, b), c=c, m=m, cond=np.linalg.cond(a))

    path = CACHE / "mna.npz"
    if not path.exists():
        net = CoilNetwork(cases["default"].coils())
        with mock.patch.object(np.linalg, "solve", wraps=np.linalg.solve) as spy_solve:
            net.solve([5e6])
        a, b = spy_solve.call_args.args
        x = np.linalg.solve(a, b)
        np.savez(path, a=a, b=b, x=x, c=np.zeros(0), m=0, cond=np.linalg.cond(a))


def derived_c(x: np.ndarray, m: int, lossy: bool) -> np.ndarray:
    """Capacitance matrix from the solution, exactly as ``capacitance._solve`` forms it."""
    n_total = x.shape[1]
    c = x[: n_total * m].reshape(n_total, m, n_total).sum(axis=1)
    c = 0.5 * (c + c.T)
    return c if lossy else c.real


def check_process(backend: str) -> CheckProcess:
    if backend == "native":
        subprocess.run(["cargo", "build", "--release", "-q"], cwd=RUST, check=True)
        return CheckProcess([str(RUST / "target" / "release" / "coilcal-check")])
    target, env = RUST / "target", None
    if backend == "wasm-nosimd":
        target = target / "nosimd"
        env = os.environ | {
            "RUSTFLAGS": "-C target-feature=-simd128",
            "CARGO_TARGET_DIR": str(target),
        }
    build = ["cargo", "build", "--release", "-q", "--target", WASM_TARGET]
    subprocess.run(build, cwd=RUST, check=True, env=env)
    wasm = target / WASM_TARGET / "release" / "coilcal-check.wasm"
    return CheckProcess(["node", "--no-warnings", str(RUNNER), str(wasm)])


def run(backend: str, repeat: int) -> list[tuple]:
    port = check_process(backend)
    rows = []
    for path in sorted(CACHE.glob("*.npz")):
        d = np.load(path)
        a, b, xr, cr, m, cond = d["a"], d["b"], d["x"], d["c"], int(d["m"]), float(d["cond"])
        t_np = t_port = np.inf
        for _ in range(repeat):
            t0 = time.perf_counter()
            np.linalg.solve(a, b)
            t_np = min(t_np, time.perf_counter() - t0)
            x, secs = port("solve", a, b)
            t_port = min(t_port, float(secs))
        for solver, xs, t in (("numpy", xr, t_np), ("port", x, t_port)):
            res = np.linalg.norm(a @ xs - b) / np.linalg.norm(b)
            dx = np.linalg.norm(xs - xr) / np.linalg.norm(xr)
            dc = np.nan
            if m:
                c = derived_c(xs, m, np.iscomplexobj(cr))
                dc = np.max(np.abs(c - cr)) / np.max(np.abs(cr))
            rows.append((path.stem, solver, len(a), str(a.dtype), cond, res, dx, dc, t))
    port.close()
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=("wasm", "wasm-nosimd", "native"), default="wasm")
    ap.add_argument("--repeat", type=int, default=3)
    args = ap.parse_args()
    capture()
    rows = run(args.backend, args.repeat)
    print(f"backend: {args.backend} (numpy rows: native LAPACK, timed in Python)")
    print(
        f"{'system':14} {'solver':11} {'n':>5} {'dtype':>10} {'cond(A)':>8} "
        f"{'residual':>9} {'|dX|/|X|':>9} {'cond*eps':>9} {'max|dC|':>9} {'seconds':>8}"
    )
    for name, solver, n, dtype, cond, res, dx, dc, t in rows:
        print(
            f"{name:14} {solver:11} {n:5d} {dtype:>10} {cond:8.1e} "
            f"{res:9.1e} {dx:9.1e} {cond * EPS:9.1e} {dc:9.1e} {t:8.3f}"
        )


if __name__ == "__main__":
    main()
