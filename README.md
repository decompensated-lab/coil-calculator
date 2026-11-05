# coilcal

Quasi-static modelling of single-layer cylindrical coils, parametrised like Coil64
(wire Ø, pitch, former Ø, turns). SI units throughout.

```bash
uv sync
uv run pytest -q
uv run python examples/demo.py --turns-a 10 --turns-b 5 --freq 5e6 --gap 0.05
uv run coilcal-gui        # Qt GUI (F1 = guide; hover any control for help)
uv run mypy               # static type check (configured in pyproject.toml)
```

Mode-like arguments are `StrEnum`s in `coilcal.types` (`Grounding`, `Coupling`, `FieldModel`,
`MutualMethod`, `ThruMode`, `TerminalEnd`). Plain strings such as `"end"` are still
accepted but are validated, so a typo raises `ValueError` instead of being silently ignored.

```python
import coilcal as cc
from scipy.spatial.transform import Rotation as R

a = cc.SolenoidCoil(wire_d=1.0e-3, pitch=2.0e-3, former_d=0.150, n_turns=10)
b = cc.SolenoidCoil(
    1.0e-3,
    2.0e-3,
    0.150,
    5,
    position=[0.02, 0, 0.08],
    orientation=R.from_euler("x", 15, degrees=True),
)

cc.self_inductance(a, freq=5e6)  # H
cc.mutual_inductance(a, b)  # H (arbitrary pose)
cc.coupling_coefficient(a, b)
cc.induced_emf(a, b, current_a=1.0, freq=5e6)  # complex V, open circuit
cc.induced_voltage_loaded(a, b, 1.0, 5e6, z_load=50)  # complex V across a 50 Ω load
cc.field_B(a, points, current=1.0, model="rings" | "helix")  # T, via magpylib
print(cc.check_quasistatic(a, f_max=5e6))  # SRF / electrical-length report
```

## Models

| quantity | method | cross-check (tests) |
|---|---|---|
| geometry | wire centre at `former_d/2 + wire_d/2` (Coil64), length `N·pitch` | |
| B-field | magpylib: one `Circle` per turn, or a `Polyline` helix (pitch + axial current) | exact on-axis ring sum; current sheet; dipole far field |
| L | Σ turn self-inductance (round-wire loop, skin-effect internal inductance from Bessel solution) + Σ Maxwell turn-pair mutuals | Nagaoka + Rosa corrections (agree to ~2e-5); Wheeler |
| M | turn-pair sum: Maxwell (coaxial) or analytic ring vector potential ∮A·dl with adaptive periodic trapezoid (any pose) | magpylib flux through each turn's disk (agree to ~1e-6); reciprocity |
| C_self, SRF | Medhurst fit, lumped `1/(2π√(LC))` | estimates only (±10–20 %), flagged outside l/D 0.1–50 |
| R_ac | isolated-wire skin effect | proximity effect **not** included |

Sign convention: positive current circulates CCW about the coil's local +z axis; M > 0 when
positive currents give aiding flux. Flipping a coil (180°) flips the sign of M.

## Turn-level network (non-DC effects)

`CoilNetwork([a, b], ground=["end", "end"])` builds a lumped network with one branch per
turn. Each branch is `R + jωL` and is coupled to every other turn through the inductance
matrix above. The Maxwell capacitance matrix between turns comes from a charge-simulation
electrostatic solver (axisymmetric within coaxial coils, thin-wire between other coils) and is
mapped onto the winding nodes. `solve(freqs)` returns:

* the port Z-matrix: `Z11` (input impedance, `effective_inductance`) and `Z21` (open-circuit
  V_B per ampere in A, including capacitive feed-through); use `loaded_voltage(z_load)` for a
  terminated coil B;
* per-turn currents and node voltages, plus the complex B-field from them (`net.field_B`);
* `net.srf()`: the first parallel resonance at a port.

`coupling="magnetic"` or `"electric"` keeps only one inter-coil path, to split the two
contributions. `ports=[Port(...), ...]` defines arbitrary fixtures. `coilcal.vna` adds Z→S
conversion, series/shunt-thru fixtures and source-power drive.

Checks: the low-frequency limit reproduces the static L, M and R to 1e-6. The capacitance
solver matches an isolated torus and the two-wire line formula to about 1e-4. The network is
reciprocal.

### Insulation and former dielectrics

```python
from coilcal import Dielectric, Former, Material, SolenoidCoil

coil = SolenoidCoil(
    wire_d=1.0e-3, pitch=2.0e-3, former_d=0.150, n_turns=10,
    insulation_d=1.06e-3, insulation=Material.ENAMEL.dielectric,      # εr 3.6, tanδ 0.01
    former=Former(wall=3e-3, dielectric=Material.PMMA.dielectric, overhang=10e-3),
)
```

Both enter the turn-to-turn capacitance matrix; inductance is unaffected.

* **Insulation:** eliminated exactly. Each wire is locally 2-D, so the sleeve becomes a
  per-harmonic boundary condition on its outer surface.
* **Former:** a dielectric tube modelled with boundary elements. Panels on its outer, inner
  and end faces carry bound charge.
* **Loss:** a lossy dielectric (`tan_delta > 0`) makes C complex, so the network includes the
  dielectric loss.

Checks:

* Insulated turns of a very large coil match the exact 2-D insulated pair to 2e-3, including
  touching turns. The number of charges per turn grows automatically for tight windings.
* With a former, they match an independent 2-D boundary-element reference to 0.1–0.5%. That
  includes enamelled wire touching the former.

Typical effect on the self-resonant frequency, for 1 mm enamelled wire on a 150 mm, 3 mm-wall
PMMA former:

| turns | pitch 2 mm | close-wound |
|---|---|---|
| 10 | −10% | −22% |
| 30 | −5% | −14% |

Close-wound coils with many turns are slow: about 30 s for 100 turns.

Not modelled: proximity effect (approximate it with `r_factor`), radiation, ground
planes/fixtures, and other coils' formers when coils are not coaxial. Each turn is assumed much shorter than
a wavelength (true here: 0.47 m against 60 m).

## Insulated wire pair (2-D)

`coilcal.wirepair.pair_capacitance(w1, w2, spacing)` gives the capacitance per unit length
between two long parallel round conductors, each in a concentric dielectric sleeve, with air
outside. It uses a multipole expansion with an exact reflection coefficient per harmonic for
each sleeve, and is exact apart from series truncation. A complex permittivity
(`Dielectric(eps_r, tan_delta)`, presets in `coilcal.materials.Material`) gives the line's
effective loss tangent and shunt conductance.

```python
from coilcal.materials import Dielectric
from coilcal.wirepair import InsulatedWire, pair_capacitance

w = InsulatedWire(1e-3, 1.5e-3, Dielectric(2.1, 2e-4))  # Ø1 mm in Ø1.5 mm PTFE
pair_capacitance(w, spacing=1.5e-3).capacitance          # touching: 44.4 pF/m
```

Checks:

* the closed-form bare pair (to 1e-9);
* the εr → 1 and εr → ∞ limits;
* the effective-radius formula b·(a/b)^(1/εr), which becomes exact at large spacing;
* an independent panel BEM (about 1e-3, limited by the BEM).

The GUI's **Wire pair C** tab wraps it with a field map, C′ vs spacing, and the pair viewed
as a two-wire line (Z0, velocity factor). The coil model does not use it yet.

## Caveats at 5 MHz with a 150 mm former

Each turn is ~0.47 m of wire (λ = 60 m at 5 MHz). `check_quasistatic` shows that:

* ~12 turns already reach 0.1 λ of conductor, and the Medhurst SRF estimate for 10 turns is
  ~8.6 MHz: apparent inductance at 5 MHz is then ~50 % above the static value.
* 50 turns (100 mm long) have an estimated SRF of ~3 MHz, below the operating band.

So the static field *shape* stays valid for few-turn coils, but the terminal L and the EMF
measured at the terminals need the SRF correction (or fewer turns / smaller coils).
