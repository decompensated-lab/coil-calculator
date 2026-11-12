# AGENTS.md

`coilcal` models single-layer cylindrical coils: static B / L / M, a turn-level circuit model
with turn-to-turn capacitance (insulation and former dielectrics), VNA S-parameters, and a 2-D
insulated wire-pair calculator. One model, two apps:

* `python/`: the Python library (the reference implementation) and the Qt desktop app.
  Python 3.12, numpy/scipy, magpylib, matplotlib, PySide6-Essentials.
* `web/`: the browser app. The model ported to Rust (`web/rust/`, compiled to WASM) under a
  Svelte interface. Deployed to GitHub Pages by `.github/workflows/pages.yml`.

User-facing docs: `README.md` (overview, models, validation, credits), `python/README.md`
(library and Qt app), `web/README.md` (browser app). State of ongoing work: `HANDOFF.md`
(untracked, if present).

## Commands

Python commands run from `python/`, web commands from `web/`, cargo from `web/rust/`.

```bash
cd python
uv sync                                   # install (respects the cooldown in pyproject.toml)
uv run pytest -q                          # all tests, ~35 s; GUI tests run offscreen
uv run pytest -q tests/test_dielectric.py -k former   # a focused subset
uv run ruff check src tests examples scripts          # lint (--fix for safe fixes)
uv run ruff format src tests examples scripts         # format (line length 100)
uv run mypy                               # type check src/coilcal (disallow_untyped_defs)
uv run python examples/demo.py            # CLI demo, writes examples/out/ (git-ignored)
uv run coilcal-gui                        # the GUI (needs a display)
QT_QPA_PLATFORM=offscreen uv run python script.py     # render GUI widgets headless

uv run python scripts/affected.py         # only the checks/tests your changes affect (-n: plan)
uv run python scripts/affected.py --base main         # ... for everything on the branch
uv run pytest -q tests/port --port-backend native     # port tests against the native build
OPENBLAS_NUM_THREADS=1 uv run python tests/port/bench.py --pyodide   # port vs reference timings
                                          # (--pyodide needs `pnpm install` in tests/port/pyodide)
uv run python scripts/gen_help.py         # regenerate web/src/lib/help.ts from gui/help.py

cd web/rust && cargo fmt --check && cargo clippy --all-targets -- -D warnings && cargo test

cd web && pnpm install && pnpm dev        # the browser app (builds the WASM module first)
cd web && pnpm check && pnpm build        # type-check (svelte-check) and production build
cd web && node scripts/screenshot.ts http://localhost:5173/ out.png   # headless look (Chromium)
    # options: DARK=1, KEYS=ArrowRight,..., NO_FOCUSGROUP=1, 5th argument = JS to run first;
    # CHROMIUM=<binary> if it is not called `chromium`
```

While iterating, `scripts/affected.py` runs only what a change touches (an import graph picks
the Python tests). Before calling a change done, run ruff (check and format), mypy, and pytest.
All must pass.
If `web/rust/` changed, also run the cargo line above. If the rest of `web/` changed, run
`pnpm check` and `pnpm build`, and look at a screenshot of the app (light and `DARK=1`).
For GUI changes, also render the affected tab offscreen (`widget.grab().save(...)`) and look
at the image.

## Layout

* `python/`: a uv project (`pyproject.toml`, `uv.lock`).
  * `src/coilcal/`: library modules, one per concern. Each module's docstring states its
    method and assumptions; keep those current.
    * `capacitance.py`: charge simulation + sleeve DtN + former BEM. Results are cached per
      geometry.
    * `circuit.py`: MNA network, `Resonance`.
    * `wirepair.py`: 2-D multipole.
  * `src/coilcal/gui/`: the Qt app.
    * `model.py`: pure compute, `Params` → `Results`, no Qt.
    * `plots.py`, `pair.py`: matplotlib drawing, no Qt.
    * `richtext.py`: HTML summary with mathtext images.
    * `help.py`: every tooltip and the F1 guide (shared with the browser app).
    * `widgets.py`, `window.py`, `pairtab.py`: Qt.
  * `tests/`: pytest. `_bem2d.py` is an independent 2-D BEM used only as a reference.
  * `tests/port/`: live comparison of every Rust function with the Python reference, on the
    WASM build under Node's `node:wasi` (default) or the native build. `test_web.py` runs the
    TypeScript client against the browser module.
  * `scripts/affected.py`: maps changed files (anywhere in the repository) to the checks and
    tests they affect. `scripts/gen_help.py`: writes `web/src/lib/help.ts`.
  * `examples/`: `demo.py`, `demo.ipynb`.
* `web/`: the browser app (Svelte 5, Vite, TypeScript, uPlot, KaTeX).
  * `rust/`: the Rust port (toolchain pinned in `rust-toolchain.toml`).
    * `crates/core`: one module per Python module, plus `app.rs` (port of `gui/model.py`:
      `compute`, input validation, and `app::call`, the byte interface) and `pair.rs` (port
      of `gui/pair.py`'s `compute_pair`). The `kind` parameter of a request picks the model.
    * `crates/check`: stdin/stdout binary that `python/tests/port/` drives (wire format in
      `wire.rs`).
    * `crates/web`: `cdylib` for `wasm32-unknown-unknown` exporting `alloc`/`dealloc`/`call`
      (no wasm-bindgen, no imports).
  * `src/lib/protocol.ts`: parameters, defaults and the byte format (mirrors `Params` and
    `PairParams`; no imports, so Node runs it in `scripts/smoke.ts`).
  * `src/lib/worker.ts` + `compute.svelte.ts`: the model in a Web Worker, newest request wins.
  * `src/lib/results.ts`: typed views of the responses, complex and SI-format helpers.
  * `src/lib/plot.ts` (uPlot panels) and `Frame.svelte` + `fieldplot.ts` (equal-aspect SVG,
    colour map, streamlines, contours): the matplotlib replacements. One component per plot.
  * `src/App.svelte`: the dashboard (header with the mode switch and view frequency, inputs
    on the left, `KeyNumbers`, then `Card`s (foldable, expandable) that each switch between
    related plots).
    `CoilTable.svelte` is the input table with a column per coil.
  * `src/lib/help.ts`: generated from `gui/help.py`; do not edit by hand.
* `LICENSE` (MIT) and `THIRD_PARTY_NOTICES.md` (ported code, what the browser build bundles,
  runtime dependencies); the web build copies both into the published site.
* `.github/workflows/pages.yml`: builds `web/` and deploys it to GitHub Pages on a push to
  `main`.

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
  `TAB_TIPS`). Mention new tabs in `GUIDE_HTML`. Then run `scripts/gen_help.py`.
* **Summary quantities must stay meaningful:** hide or relabel values that lose their meaning
  near resonance, as is done for L_eff and X/R, rather than printing nonsense.

## Web conventions (`web/`)

* **Svelte 5 runes only.** After editing a component run `pnpm check` and the Svelte
  autofixer (Svelte MCP server); `{@html}` only for KaTeX output and the static guide.
* **HTML/CSS/client JS:** consult the `modern-web-guidance` skill first and follow its
  guides. Features beyond Baseline Widely available get the fallback the guide asks for; a
  polyfill package is a new dependency (ask first), so until approved use a small hand-written
  fallback.
* **Colours** come from the tokens in `src/app.css` (light and dark); plot colours from
  `plot.ts`.
* **A new result reaches the UI** through `app.rs`/`pair.rs` `encode` → `results.ts` view;
  add it to `python/tests/port/test_app.py` against the Python value at the same time.

## Physics and numerics rules

* **Every new model needs an independent cross-check test:** a closed form, a limit, or a
  different numerical method. Not just a regression value. See
  `python/tests/test_dielectric.py` and `python/tests/test_wirepair.py`.
* **Write relative comparisons as `pytest.approx(x, rel=..., abs=0)`.** The default
  `abs=1e-12` silently passes any pF-scale value.
* **Check convergence before choosing defaults.** Change one discretisation parameter at a
  time and compare against the reference.
* **Use the lossless path when nothing is lossy.** A lossy dielectric makes `capacitance_matrix`
  complex; otherwise keep it real.
* **Ported models change in Python first,** then in Rust; `python/tests/port/` must stay green.
  Port tolerances come from the conditioning of the computation, with the reason written in
  the test.
* **Report what is not modelled.** Currently: the proximity effect (`r_factor`), radiation,
  fixtures and ground planes, frequency-dependent εr/tanδ, and other coils' formers between
  non-coaxial groups. Do not present estimates (Medhurst) as field solutions.

## Git

* Commit at reasonable, self-contained points: tests green, one topic per commit.
* Imperative subject line, with a body that explains the why.
* Do not commit generated output (`python/examples/out/`, caches, `web/rust/target/`, `web/dist/`,
  `web/src/lib/coilcal.wasm`) or `.claude/settings.local.json`.

## Agent compatibility

* `AGENTS.md` is canonical. `CLAUDE.md` is a committed symlink to it; keep it that way and
  never replace either with a copy.
* `.agents/` (skills etc.) is primary. `.claude/skills` is a committed symlink to
  `../.agents/skills`; add new shared agent assets under `.agents/` and symlink them.

## Security and dependencies

* **Supply-chain cooldown:** 7 days for Python packages (`[tool.uv] exclude-newer = "7 days"`
  in `python/pyproject.toml`) and 3 days for anything web-related (`minimumReleaseAge: 4320`
  in each `pnpm-workspace.yaml`: `web/`, `python/tests/port/pyodide/`; run pnpx from those
  directories). If a critical update
  must break the cooldown, run a vulnerability scan first (e.g. `uvx pip-audit`) and note it
  in the commit.
* **Rust crates:** same 7-day rule; check the publish date of a crate version (and of new
  transitive dependencies) before adding it, pin it, and commit `web/rust/Cargo.lock`.
* **Toolchains:** `uv` for Python and `pnpm` for JS. Do not use pip, poetry or npm directly.
* **GitHub Actions:** pin every action to a commit SHA (with the version in a comment), and
  apply the same 7-day rule to the release it points at.
* **Containers:** prefer podman, but keep Dockerfiles Docker-compatible. Follow uv's
  caching / non-editable install guidance:
  https://docs.astral.sh/uv/guides/integration/docker/#non-editable-installs
* **Qt:** keep `pyside6-essentials` (no WebEngine). Rich text uses matplotlib mathtext in a
  `QTextBrowser`.

## Boundaries

* **Always:** run the checks above before finishing. Add or adjust tests together with the
  code. Update the READMEs, docstrings and GUI help (Qt and web) when behaviour or defaults
  change. When a dependency is added or code is ported from another project, update
  `THIRD_PARTY_NOTICES.md` and the credits (README "Acknowledgements and references" and the
  guide's Credits section).
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
