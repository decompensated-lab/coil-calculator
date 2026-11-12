# coilcal

Models of single-layer cylindrical coils, parametrised like Coil64 (wire Ø, insulated Ø,
pitch, former Ø, turns). It covers the static field, inductance and mutual inductance. It
also has a turn-level circuit model for frequencies up to and beyond self-resonance. That
model includes turn-to-turn capacitance with the wire insulation and the former's dielectric,
VNA S-parameters, and a Qt GUI. SI units throughout. Phasors are peak amplitudes.

```bash
uv sync                      # Python 3.12, deps pinned in uv.lock (7-day cooldown)
uv run coilcal-gui           # Qt GUI (F1 = guide; hover any control for help)
uv run pytest -q             # full test suite (~25 s; GUI tests run offscreen)
uv run python examples/demo.py --turns-a 10 --turns-b 5 --freq 5e6 --gap 0.05
```

## Library

### Static (quasi-DC) quantities

```python
import numpy as np
import coilcal as cc
from scipy.spatial.transform import Rotation as R

a = cc.SolenoidCoil(wire_d=1.0e-3, pitch=2.0e-3, former_d=0.150, n_turns=10)
b = cc.SolenoidCoil(1.0e-3, 2.0e-3, 0.150, 5,
                    position=[0.02, 0, 0.08], orientation=R.from_euler("x", 15, degrees=True))

cc.self_inductance(a, freq=5e6)                         # H (skin-effect internal L)
cc.mutual_inductance(a, b)                              # H, any pose
cc.coupling_coefficient(a, b)
cc.induced_emf(a, b, current_a=1.0, freq=5e6)           # complex V, B open
cc.induced_voltage_loaded(a, b, 1.0, 5e6, z_load=50)    # complex V across 50 Ω
pts = np.array([[0, 0, z] for z in np.linspace(-0.1, 0.1, 5)])
cc.field_B(a, pts, current=1.0, model="rings")          # T, via magpylib ("helix" too)
print(cc.check_quasistatic(a, f_max=5e6))               # Medhurst SRF / electrical length
```

### Insulation and former

```python
from coilcal import Dielectric, Former, Material, SolenoidCoil

coil = SolenoidCoil(
    wire_d=1.0e-3, pitch=2.0e-3, former_d=0.150, n_turns=10,
    insulation_d=1.06e-3, insulation=Material.ENAMEL.dielectric,       # εr 3.6, tanδ 0.01
    former=Former(wall=3e-3, dielectric=Material.PMMA.dielectric, overhang=10e-3),
)
```

* **Placement:** the wire centre sits at `former_d/2 + insulation_d/2`.
* **What the dielectrics affect:** only the capacitance. Inductance and field are unchanged.
* **Values:** `Material` presets are typical values around 1 MHz, so prefer datasheet values;
  use `Dielectric(eps_r, tan_delta)` for custom ones.
* **Sharing a former:** coaxial coils with the same `Former` settings whose tubes meet share
  one tube.

### Turn-level network, resonance and VNA

```python
from coilcal import CoilNetwork

pickup = SolenoidCoil(1.0e-3, 2.0e-3, 0.150, 5, position=[0, 0, 0.065])  # coaxial with coil
net = CoilNetwork([coil, pickup], ground=["end", "end"])  # "end" / "start" / "floating"
res = net.solve(np.geomspace(1e5, 3e7, 400))
res.z_in(0)                   # input impedance of coil 0 (coil 1 open)
res.effective_inductance(0)   # Im Z / ω
res.transfer_impedance(1, 0)  # Z21: open-circuit V at coil 1 per ampere into coil 0
res.loaded_voltage(50.0)      # V at coil 1 across 50 Ω per ampere into coil 0
net.srf()                     # first parallel resonance at port 0 [Hz]
net.resonance()               # Resonance(freq, q, r_parallel); Q includes dielectric loss
```

* **Topology:** every turn is a branch `R + jωL`. The branches are coupled through the full
  turn-to-turn inductance matrix and through the Maxwell capacitance matrix between turns,
  mapped onto the winding nodes.
* **Other ports:** `ports=[Port(...), ...]` defines any fixture.
* **Diagnostics:** `coupling="magnetic"` or `"electric"` keeps only one coupling path between
  coils.
* **`coilcal.vna`:** Z→S conversion, series- and shunt-thru fixtures (`thru_network`), and
  currents driven by a source power (`driven_turn_currents`).

### Insulated wire pair (2-D)

```python
from coilcal.wirepair import InsulatedWire, pair_capacitance

w = InsulatedWire(1e-3, 1.5e-3, Dielectric(2.1, 2e-4))   # Ø1 mm in Ø1.5 mm PTFE
r = pair_capacitance(w, spacing=1.5e-3)                  # sleeves touching
r.capacitance, r.tan_delta                               # 44.4 pF/m, effective tanδ
```

* **What it is:** a stand-alone calculator for C′ between two long parallel wires with
  dielectric sleeves in air. It is not used by the coil model.
* **As a transmission line:** using one wire as the forward conductor and the other as the
  return is the same differential mode the calculation assumes. So
  Z0 = 1/(c₀√(C′·C′_air)) is what you would measure.

### Enums and typing

* **Mode-like arguments are `StrEnum`s** in `coilcal.types`: `Grounding`, `Coupling`,
  `FieldModel`, `MutualMethod`, `ThruMode`, `TerminalEnd`.
* **Plain strings such as `"end"` are accepted but validated,** so a typo raises `ValueError`.
* **The package is type-checked:** `uv run mypy`.

## GUI (`uv run coilcal-gui`)

**Left panel:**
* **Each coil:** geometry, terminals, and insulation/former materials. Each material has a
  preset plus editable εr and tan δ.
* **Placement of B:** a gap measured either edge-to-edge or centre-to-centre, plus a lateral
  offset.
* **VNA setup:** A on P1 with B on P2, or one coil series-thru or shunt-thru. Also Z0 and
  source power.
* **Analysis settings:** sweep range, view frequency, B's load, R factor and coupling paths.

**Tabs:**

| tab | shows |
|---|---|
| Cross-section | wires at true size and pitch on the former wall; fill = turn current or voltage for the VNA drive |
| Side view | \|B\| map and field lines in the x–z plane for the VNA drive |
| Bz profiles | in-phase Bz along the axis and across at a chosen height; dotted = uniform-current (quasi-DC) shape |
| Impedance | Z_in of each coil (other open) vs the quasi-DC R + jωL; L_eff/L_DC |
| Transfer A→B | Z21 vs jωM, and the voltage into the chosen load |
| VNA | S-parameters (dB, phase, Smith) of the chosen setup |
| Turn currents | current per turn and voltage per node |
| Wire pair C | the 2-D insulated-pair calculator, with field map, C′ vs gap, and Z0 / velocity factor |

**Summary panel, per coil:**

| quantity | meaning |
|---|---|
| L_DC | static inductance |
| L_eff, X/R | from the network at the view frequency; hidden near or above any resonance of the system, where they stop meaning inductance or Q |
| Q_L = ωL_DC/R_ac | copper-only Q, valid well below resonance |
| f_SRF and Q_SRF | resonance of the coil alone; Q includes conductor and dielectric loss |
| f_res | the same resonance with the other coil present but open (shown when it differs) |
| f_SRF without dielectrics | the same coil with vacuum insulation and no former |
| Medhurst SRF | the empirical estimate, for comparison |

Warnings flag a view frequency near a resonance, a tight pitch with no proximity correction
(R factor = 1), and l/D outside Medhurst's fitted range.

## Browser app (work in progress, branch `wasm-rewrite`)

The same app, running in the browser with no server: the model is ported to Rust and compiled
to WebAssembly, and the interface is a Svelte page with every tab of the Qt GUI.

```bash
cd web && pnpm install && pnpm dev   # needs the Rust toolchain in rust/rust-toolchain.toml
```

* **Python stays the reference.** `tests/port/` runs every Rust kernel and the whole app
  computation against the Python code (agreement 1e-16 to 1e-10, each tolerance justified by
  the conditioning in its test). They need cargo and Node and skip otherwise.
* **Speed:** the default GUI case computes in about 0.3 s in the browser (Python: 0.5 s); the
  capacitance solve is 2.5–4× faster than the Python code under Pyodide
  (`tests/port/bench.py --pyodide`).

## Models

| quantity | method |
|---|---|
| B-field | magpylib: one `Circle` per turn, or a `Polyline` helix (pitch and axial current) |
| L | Σ round-wire loop self-inductance with skin-effect internal inductance (Bessel) + Σ Maxwell turn-pair mutuals |
| M | turn-pair sums: Maxwell elliptic formula (coaxial) or ∮A·dl of the analytic ring vector potential, adaptive trapezoid (any pose) |
| R_ac | isolated-wire skin effect × `r_factor` (proximity effect not computed) |
| C between turns, coaxial coils | axisymmetric charge simulation. Insulation enters as an exact per-harmonic Dirichlet-to-Neumann condition on the sleeve surface. The former is a boundary-element tube carrying bound charge. Charges per turn are increased automatically for tight windings |
| C between turns, non-coaxial coils | thin-wire potential coefficients averaged around each ring; each former acts only within its own coaxial group |
| network | modified nodal analysis per frequency; lossy dielectrics make C complex |
| resonance Q | slope of the port susceptance, `Q = (ω0/2G)·dB/dω` |
| wire pair | 2-D multipole expansion with an exact reflection coefficient per harmonic for each sleeve |

Sign convention: positive current circulates CCW about the coil's local +z axis. M > 0 when
positive currents aid each other; flipping a coil by 180° flips the sign of M.

## Validation (tests)

| model | checked against | agreement |
|---|---|---|
| self-inductance L | Nagaoka + Rosa corrections | 1e-4 |
| self-inductance L | Wheeler | 2% |
| mutual inductance M | magpylib flux through each turn | 1e-5 |
| mutual inductance M | dipole far field, reciprocity | — |
| on-axis B | exact ring sum and current-sheet formula | — |
| capacitance, bare wire | torus formula | 1e-3 |
| capacitance, bare wire | two-wire line | 1e-3 |
| insulated turns of a 10 m-radius coil | exact 2-D insulated pair, incl. touching turns | 2e-3 |
| former + wires | independent 2-D panel BEM (`tests/_bem2d.py`) | 0.1–0.5% |
| network at low frequency | static L, M, R | 1e-6 |
| network | reciprocity | — |
| Q_SRF | f0 / (−3 dB bandwidth) | 2% |
| S-parameters | ideal series/shunt thru formulas | — |
| S-parameters | passivity | — |
| wire pair | closed-form bare pair | 1e-9 |
| wire pair | εr → 1 and εr → ∞ limits | — |
| wire pair | effective-radius limit | — |
| wire pair | independent BEM | 1e-3 |

Relative comparisons use `pytest.approx(..., rel=..., abs=0)`. Without `abs=0`, the default
absolute tolerance of 1e-12 swamps pF-scale values.

## Typical numbers and caveats (150 mm former, 1 mm wire, 2 mm pitch, end grounded)

| turns | wire / λ at 5 MHz | network SRF bare → enamel + 3 mm PMMA | Q_SRF bare → dielectrics | L_eff / L at 5 MHz | Medhurst SRF |
|---|---|---|---|---|---|
| 5 | 0.04 | 25.4 → 22.1 MHz | 1280 → 170 | 1.04 → 1.05 | 13.2 MHz |
| 10 | 0.08 | 13.7 → 12.2 MHz | 1550 → 210 | 1.15 → 1.20 | 8.5 MHz |
| 20 | 0.16 | 7.6 → 7.1 MHz | 1790 → 300 | 1.76 → 2.0 | 5.6 MHz |
| 30 | 0.24 | 5.5 → 5.2 MHz | 1900 → 390 | near resonance | 4.4 MHz |
| 50 | 0.40 | 3.7 → 3.5 MHz | 1970 → 560 | above resonance | 3.2 MHz |

* **Use well below resonance:** the static field *shape* holds, but terminal L and EMF need
  the network model above about 0.3 × SRF.
* **Dielectric loss dominates Q at resonance,** even for enamel (tanδ 0.01) on PMMA (0.015).
  The tan δ values are assumptions; the computed Q follows them almost one-for-one.
* **Medhurst predicts lower SRFs than this free-space solver.** His values are measured
  fits, made in his measurement environment.
* **What a VNA sees:** an uncompensated cable or fixture capacitance adds directly to the
  coil's (50 Ω coax is about 100 pF/m). Calibrate at the coil terminals.
* **Not modelled:**
  * the proximity effect (set `r_factor`; about 1.2–3 for pitch < 2.5 × wire Ø);
  * radiation;
  * nearby metal, ground planes and the measurement fixture;
  * frequency-dependent εr and tan δ;
  * other coils' formers when the coils are not coaxial.
* **Speed:** close-wound coils with many turns are slow, about 30 s for 100 turns. Results
  are cached per geometry.

## Layout

```
src/coilcal/
  geometry.py     SolenoidCoil, Former
  materials.py    Dielectric, Material presets
  types.py        StrEnums, Port, array type aliases
  loops.py        ring/filament kernels: mutual inductance, vector potential, skin effect
  field.py        magpylib models, on-axis formulas
  inductance.py   self-inductance and the Nagaoka/Rosa/Wheeler checks, R_ac
  mutual.py       mutual inductance, coupling, EMF
  capacitance.py  turn capacitance matrix (CSM + sleeve DtN + former BEM), cached
  circuit.py      CoilNetwork (MNA), NetworkResult, Resonance
  vna.py          S-parameters, thru fixtures, source drive
  srf.py          Medhurst estimates, quasi-static validity report
  wirepair.py     2-D insulated wire pair
  gui/            Qt app: model.py (pure compute), plots.py, richtext.py, pair*.py, window.py
tests/            pytest; _bem2d.py is the independent 2-D BEM reference
  port/           Rust port against the Python reference (needs cargo and Node)
examples/         demo.py (CLI, writes examples/out/), demo.ipynb
scripts/          affected.py: run only the checks a change affects
rust/             Rust port: crates/core (model + app layer), check (test driver), web (WASM)
web/              browser app (Svelte 5, Vite, TypeScript)
```
