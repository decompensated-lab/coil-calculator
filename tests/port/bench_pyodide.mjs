// Times the Python reference's capacitance_matrix under Pyodide (what a no-rewrite web app
// would run). Usage: node bench_pyodide.mjs <cases.json> <repeat>; cases.json maps a case name
// to its coil table (conftest.coil_table rows). Prints JSON {name: {cold, warm, solve, c}}.
// Only the four modules on the capacitance path are loaded (no magpylib needed). numpy and
// scipy come from the Pyodide CDN for this exact Pyodide version.
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { loadPyodide } from "./pyodide/node_modules/pyodide/pyodide.mjs";

const [casesPath, repeat] = process.argv.slice(2);
const src = fileURLToPath(new URL("../../src/coilcal/", import.meta.url));
const py = await loadPyodide();
await py.loadPackage(["numpy", "scipy"], { messageCallback: () => {} });
py.FS.mkdirTree("/bench/coilcal");
py.FS.writeFile("/bench/coilcal/__init__.py", "");
for (const m of ["types", "materials", "geometry", "capacitance"]) {
  py.FS.writeFile(`/bench/coilcal/${m}.py`, await readFile(src + `${m}.py`, "utf8"));
}
py.globals.set("CASES_JSON", await readFile(casesPath, "utf8"));
py.globals.set("REPEAT", Number(repeat));
const out = await py.runPythonAsync(`
import json, sys, time
sys.path.insert(0, "/bench")
import numpy as np
from scipy.spatial.transform import Rotation
from coilcal import capacitance as cap
from coilcal.geometry import Former, SolenoidCoil
from coilcal.materials import Dielectric

def coil(r):
    former = Former(r[15], Dielectric(r[16], -r[17] / r[16]), r[18]) if r[14] else None
    return SolenoidCoil(r[0], r[1], r[2], int(r[3]), position=r[4:7],
                        orientation=Rotation.from_quat(r[7:11]), insulation_d=r[11],
                        insulation=Dielectric(r[12], -r[13] / r[12]), former=former)

solve_time = [0.0]
orig = np.linalg.solve
def timed(a, b):
    t0 = time.perf_counter(); x = orig(a, b); solve_time[0] += time.perf_counter() - t0
    return x
np.linalg.solve = timed

res = {}
for name, rows in json.loads(CASES_JSON).items():
    coils = [coil(r) for r in rows]
    times, solves = [], []
    for _ in range(REPEAT + 1):
        cap._CACHE.clear(); solve_time[0] = 0.0
        t0 = time.perf_counter(); c = cap.capacitance_matrix(coils)
        times.append(time.perf_counter() - t0); solves.append(solve_time[0])
    res[name] = {"cold": times[0], "warm": min(times[1:]), "solve": min(solves[1:]),
                 "c_re": np.real(c).tolist(), "c_im": np.imag(c).tolist()}
json.dumps(res)
`);
console.log(out);
