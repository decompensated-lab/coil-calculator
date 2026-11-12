"""The browser client: web/src/lib/protocol.ts with rust/crates/web under Node.

Checks that the TypeScript defaults are the GUI's defaults, and that the request/response
code and the module's exports work end to end (``app::call`` itself is compared with the
Python model in test_app.py).
"""

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from test_app import flat, flat_pair

from coilcal.gui import model as gm
from coilcal.gui import pair as gp

ROOT = Path(__file__).parents[2]
WASM = ROOT / "rust/target/wasm32-unknown-unknown/release/coilcal_web.wasm"


@pytest.fixture(scope="module")
def smoke():
    cargo, node = shutil.which("cargo"), shutil.which("node")
    if cargo is None or node is None:
        pytest.skip("cargo or node not found")
    subprocess.run(
        [cargo, "build", "--release", "--quiet", "-p", "coilcal-web",
         "--target", "wasm32-unknown-unknown"],
        cwd=ROOT / "rust", check=True,
    )  # fmt: skip
    out = subprocess.run(
        [node, "scripts/smoke.ts", str(WASM)],
        cwd=ROOT / "web",
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(out.stdout)


def test_defaults_match_the_gui(smoke):
    assert smoke["params"] == flat(gm.Params())
    assert smoke["pairParams"] == flat_pair(gp.PairParams())


def test_round_trip(smoke):
    r = gm.compute(gm.Params())
    assert smoke["freqs"] == pytest.approx(r.freqs, rel=1e-15, abs=0)
    z = np.array(smoke["z"]).view(np.complex128).reshape(r.res.z.shape)
    assert np.abs(z - r.res.z).max() <= 1e-10 * np.abs(r.res.z).max()
    assert smoke["srf_net"] == pytest.approx(r.srf_net, rel=1e-12, abs=0)
    assert int(smoke["scalars"][0]) == r.i_view
    assert smoke["warnings"] == r.warnings
    assert smoke["error"] == "enable coil B for the A/B coupling setup"
    c = gp.compute_pair(gp.PairParams()).res.c_complex
    assert complex(*smoke["pairC"]) == pytest.approx(c, rel=1e-12, abs=0)
    print(
        f"default compute in Node: {smoke['secs']:.3f} s, cached geometry {smoke['secsWarm']:.3f} s"
    )
