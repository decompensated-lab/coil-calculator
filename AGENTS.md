# AGENTS.md

`coilcal` is a numerical physics library plus Qt GUI for single-layer cylindrical coils:
static B / L / M, a turn-level circuit model with turn-to-turn capacitance (insulation and
former dielectrics), VNA S-parameters, and a 2-D insulated wire-pair calculator. Python 3.12,
numpy/scipy, magpylib, matplotlib, PySide6-Essentials. User-facing docs: `README.md`.

## Commands

```bash
uv sync                                   # install (respects the cooldown in pyproject.toml)
uv run pytest -q                          # all tests, ~15 s; GUI tests run offscreen
uv run pytest -q tests/test_dielectric.py -k former   # a focused subset
uv run ruff check src tests examples      # lint (add --fix for safe fixes)
uv run ruff format src tests examples     # format (line length 100)
uv run mypy                               # type check src/coilcal (disallow_untyped_defs)
uv run python examples/demo.py            # CLI demo, writes examples/out/ (git-ignored)
uv run coilcal-gui                        # the GUI (needs a display)
QT_QPA_PLATFORM=offscreen uv run python script.py     # render GUI widgets headless

uv run pytest -q tests/port --port-backend native     # port tests against the native build
cd rust && cargo fmt --check && cargo clippy --all-targets -- -D warnings && cargo test
OPENBLAS_NUM_THREADS=1 uv run python tests/port/bench.py --pyodide   # port vs reference timings
                                          # (--pyodide needs `pnpm install` in tests/port/pyodide)
```

Before calling a change done, run ruff (check and format), mypy, and pytest. All must pass.
If `rust/` changed, also run the cargo line above.
For GUI changes, also render the affected tab offscreen (`widget.grab().save(...)`) and look
at the image.

## Layout

* `src/coilcal/`: library modules, one per concern. Each module's docstring states its method
  and assumptions; keep those current.
  * `capacitance.py`: charge simulation + sleeve DtN + former BEM. Results are cached per
    geometry.
  * `circuit.py`: MNA network, `Resonance`.
  * `wirepair.py`: 2-D multipole.
* `src/coilcal/gui/`:
  * `model.py`: pure compute, `Params` → `Results`, no Qt.
  * `plots.py`, `pair.py`: matplotlib drawing, no Qt.
  * `richtext.py`: HTML summary with mathtext images.
  * `help.py`: every tooltip and the F1 guide.
  * `widgets.py`, `window.py`, `pairtab.py`: Qt.
* `tests/`: pytest. `_bem2d.py` is an independent 2-D BEM used only as a reference.
* `rust/`: the WASM rewrite's numerics core (work in progress, see `PLAN.md` if present).
  `crates/core` holds the kernels, `crates/check` a stdin/stdout binary that `tests/port/`
  drives to compare every kernel with the Python reference (the WASM build runs under Node's
  `node:wasi`; the tests skip without cargo or Node). Python stays the reference.

## Conventions

* **Units and phasors:** SI everywhere internally (metres, H, F, Hz); the GUI converts mm/MHz
  at its edge. Phasors are peak amplitudes. Positive current is CCW about the coil's local +z.
* **Mode-like options are `StrEnum`s** (`coilcal.types`, `coilcal.materials.Material`, GUI
  enums in `gui/model.py`). Public functions accept the enum or its string value and validate
  with `Enum(value)`. Never compare raw strings.
* **Typing:** full annotations, PEP 695 aliases (`FloatArray`, `ComplexArray`). Frozen
  dataclasses for geometry and materials.
* **Qt combo boxes:** use `EnumCombo` (`gui/widgets.py`). Qt turns `StrEnum` item data into
  plain `str`.
* **Tooltips:** every new GUI control gets a tooltip key in `gui/help.py` (`TIPS` /
  `TAB_TIPS`). Mention new tabs in `GUIDE_HTML`.
* **Summary quantities must stay meaningful:** hide or relabel values that lose their meaning
  near resonance, as is done for L_eff and X/R, rather than printing nonsense.

## Physics and numerics rules

* **Every new model needs an independent cross-check test:** a closed form, a limit, or a
  different numerical method. Not just a regression value. See `tests/test_dielectric.py` and
  `tests/test_wirepair.py`.
* **Write relative comparisons as `pytest.approx(x, rel=..., abs=0)`.** The default
  `abs=1e-12` silently passes any pF-scale value.
* **Check convergence before choosing defaults.** Change one discretisation parameter at a
  time and compare against the reference.
* **Use the lossless path when nothing is lossy.** A lossy dielectric makes `capacitance_matrix`
  complex; otherwise keep it real.
* **Report what is not modelled.** Currently: the proximity effect (`r_factor`), radiation,
  fixtures and ground planes, frequency-dependent εr/tanδ, and other coils' formers between
  non-coaxial groups. Do not present estimates (Medhurst) as field solutions.

## Git

* Commit at reasonable, self-contained points: tests green, one topic per commit.
* Imperative subject line, with a body that explains the why.
* Do not commit generated output (`examples/out/`, caches) or `.claude/settings.local.json`.

## Agent compatibility

* `AGENTS.md` is canonical. `CLAUDE.md` is a committed symlink to it; keep it that way and
  never replace either with a copy.
* `.agents/` (skills etc.) is primary. `.claude/skills` is a committed symlink to
  `../.agents/skills`; add new shared agent assets under `.agents/` and symlink them.

## Security and dependencies

* **Supply-chain cooldown:** 7 days for Python packages (`[tool.uv] exclude-newer = "7 days"`
  in `pyproject.toml`) and 3 days for anything web-related (pnpm/npm). If a critical update
  must break the cooldown, run a vulnerability scan first (e.g. `uvx pip-audit`) and note it
  in the commit.
* **Rust crates:** same 7-day rule; check the publish date of a crate version (and of new
  transitive dependencies) before adding it, pin it, and commit `rust/Cargo.lock`.
* **Toolchains:** `uv` for Python and `pnpm` for JS. Do not use pip, poetry or npm directly.
* **Containers:** prefer podman, but keep Dockerfiles Docker-compatible. Follow uv's
  caching / non-editable install guidance:
  https://docs.astral.sh/uv/guides/integration/docker/#non-editable-installs
* **Qt:** keep `pyside6-essentials` (no WebEngine). Rich text uses matplotlib mathtext in a
  `QTextBrowser`.

## Boundaries

* **Always:** run the checks above before finishing. Add or adjust tests together with the
  code. Update README, docstrings and GUI help when behaviour or defaults change.
* **Ask first:**
  * adding or upgrading dependencies, or loosening the cooldown;
  * changing GUI defaults or public API signatures;
  * loosening a test tolerance;
  * rewriting git history or pushing.
* **Never:**
  * commit secrets;
  * edit `uv.lock` or `.venv/` by hand;
  * weaken a validation test to make it pass without explaining the physics;
  * delete or replace the `CLAUDE.md` / `.claude/skills` symlinks.
