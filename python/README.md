# coilcal: the Python library and the Qt desktop app

The reference implementation of the model described in the [top-level README](../README.md)
(models, validation, caveats, credits). The browser app in [`../web/`](../web/) is a port of
this code and is tested against it.

```bash
uv sync                      # Python 3.12, deps pinned in uv.lock (7-day cooldown)
uv run coilcal-gui           # Qt GUI (F1 = guide; hover any control for help)
uv run pytest -q             # full test suite (~35 s; GUI tests run offscreen)
uv run python examples/demo.py --turns-a 10 --turns-b 5 --freq 5e6 --gap 0.05
```

Run these from this directory (`python/`).

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
  the drive level, given as source power in dBm or as the peak current into port 1 at the
  view frequency (the summary then shows the power that current needs).
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
  port/           the Rust port (../web/rust) against this code (needs cargo and Node)
examples/         demo.py (CLI, writes examples/out/), demo.ipynb
scripts/          affected.py: run only the checks a change affects
                  gen_help.py: write the browser app's help texts from gui/help.py
```

## Development

```bash
uv run ruff check src tests examples scripts
uv run ruff format src tests examples scripts
uv run mypy
uv run pytest -q
uv run python scripts/affected.py     # only what your changes affect
```

Licence: [MIT](../LICENSE).
