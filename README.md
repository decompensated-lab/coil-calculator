# coilcal: a coil calculator

Models of single-layer cylindrical coils beyond the usual inductance formulas. A coil is
described the way [Coil64](https://coil32.net) does it (wire Ø, insulated Ø, pitch, former Ø,
turns), and the model then follows every turn:

* static field, inductance and mutual inductance of one or two coils in any pose;
* a turn-level circuit model for frequencies up to and beyond self-resonance, with the
  turn-to-turn capacitance solved as a field problem, including the wire insulation and the
  former's dielectric and their loss;
* what a VNA measures: S-parameters of the usual fixtures, turn currents, the field for a
  given drive;
* a separate 2-D calculator for the capacitance of an insulated wire pair.

SI units throughout. Phasors are peak amplitudes.

## One model, two apps

| | Browser app | Desktop app and Python library |
|---|---|---|
| where | [`web/`](web/) | [`python/`](python/) |
| what | the model ported to Rust, compiled to WebAssembly, under a Svelte dashboard; runs entirely in the browser, no server | the reference implementation: a typed Python library (`coilcal`) and a Qt GUI on top of it |
| use it | open **<https://decompensated-lab.github.io/coil-calculator/>** | `cd python && uv sync && uv run coilcal-gui` |
| docs | [`web/README.md`](web/README.md) | [`python/README.md`](python/README.md) |

Both show the same numbers and the same plots. The Python code is the reference: every Rust
function, and the whole app computation, is tested against it
([`python/tests/port/`](python/tests/port/)), so a model changes in Python first and is then
ported.

```
python/           the reference: Python library + Qt desktop app (a uv project)
  src/coilcal/      library modules, one per concern; gui/ is the Qt app
  tests/            pytest; tests/port/ compares the Rust port with the Python reference
  examples/         demo.py (CLI), demo.ipynb
  scripts/          affected.py (run only the checks a change affects), gen_help.py
web/              the browser app (Svelte 5, Vite, TypeScript)
  src/              the interface
  rust/             the model in Rust: crates/core (model + app layer), check (test driver),
                    web (the WASM module)
```

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
| former + wires | independent 2-D panel BEM (`python/tests/_bem2d.py`) | 0.1–0.5% |
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


## Acknowledgements and references

**Inspiration.** This project was inspired by **Coil64** and its predecessor **Coil32**,
the coil calculators of the coil32.net project: <https://coil32.net>, source at
<https://github.com/radioacoustick/Coil64> (GPL-3.0). coilcal borrows their way of
describing a single-layer coil, and uses the same Nagaoka/Rosa current-sheet inductance as a
cross-check of its own. No Coil64 code is used.

**Libraries.**

* The Python reference is built on [NumPy](https://numpy.org), [SciPy](https://scipy.org),
  [Magpylib](https://magpylib.readthedocs.io) (field of the ring and helix models, and an
  independent check of the mutual inductance), [Matplotlib](https://matplotlib.org) and
  [Qt for Python (PySide6)](https://doc.qt.io/qtforpython-6/).
* The browser app is built on [Svelte](https://svelte.dev), [uPlot](https://github.com/leeoniya/uPlot),
  [KaTeX](https://katex.org) and [Vite](https://vite.dev), and set in
  [JetBrains Mono](https://www.jetbrains.com/lp/mono/); the Rust port uses
  [`complex-bessel`](https://github.com/elgar328/complex-bessel) (a port of Amos' Bessel
  package), `num-complex` and `libm`.
* Code ported from other projects: the loop-field formula of Magpylib
  (`web/rust/crates/core/src/field.rs`), and the Cephes elliptic integrals (via SciPy's
  `xsf`) and SciPy's `brentq` (`special.rs`, `circuit.rs`). Their licences are reproduced in
  [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

**Methods and papers.**

* J. C. Maxwell, *A Treatise on Electricity and Magnetism*, vol. 2 (1873), art. 701: mutual
  inductance of two coaxial circles.
* H. Nagaoka, "The inductance coefficients of solenoids", *J. Coll. Sci. Imp. Univ. Tokyo*
  27 (1909): the current-sheet coefficient.
* E. B. Rosa, "Calculation of the self-inductance of single-layer coils", *Bull. Bureau of
  Standards* 2 (1906) 161–187; E. B. Rosa and F. W. Grover, "Formulas and tables for the
  calculation of mutual and self-inductance", *Bull. Bureau of Standards* 8 (1912): the
  round-wire corrections.
* D. W. Knight, "An introduction to the art of solenoid inductance calculation with emphasis
  on radio-frequency applications" (2016), g3ynh.info: the fit to Rosa's mutual-correction
  table.
* H. A. Wheeler, "Simple inductance formulas for radio coils", *Proc. IRE* 16 (1928)
  1398–1400.
* R. G. Medhurst, "H.F. resistance and self-capacitance of single-layer solenoids",
  *Wireless Engineer* 24 (1947) 35–43 and 80–92: the empirical self-capacitance, shown for
  comparison only.
* H. Singer, H. Steinbigler and P. Weiss, "A charge simulation method for the calculation of
  high voltage fields", *IEEE Trans. Power Apparatus and Systems* PAS-93 (1974) 1660–1668.
* C.-W. Ho, A. E. Ruehli and P. A. Brennan, "The modified nodal approach to network
  analysis", *IEEE Trans. Circuits and Systems* 22 (1975) 504–509.
* M. Ortner, P. Leitner and F. Slanovc, "Numerically stable and computationally efficient
  expression for the magnetic field of a current loop", *Magnetism* 3 (2023) 11–31; and
  M. Ortner and L. G. Coliado Bandeira, "Magpylib: a free Python package for magnetic field
  computation", *SoftwareX* 11 (2020) 100466.
* R. Bulirsch, "Numerical calculation of elliptic integrals and elliptic functions. III",
  *Numer. Math.* 13 (1969) 305–315: the `cel` function.
* D. E. Amos, "Algorithm 644: a portable package for Bessel functions of a complex argument
  and nonnegative order", *ACM Trans. Math. Software* 12 (1986) 265–273.
* S. L. Moshier, Cephes Math Library, release 2.8 (2000); R. P. Brent, *Algorithms for
  Minimization without Derivatives* (1973): the root finder behind `brentq`.

## Licence

[MIT](LICENSE). Third-party licences: [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
The results are model predictions with the limits listed above; check them against a
measurement before relying on them.
