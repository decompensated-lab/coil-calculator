# coilcal: the browser app

**<https://ivan-galinskiy.github.io/coil-calculator/>**

The same app as the Qt GUI in [`../python/`](../python/), running in the browser with no
server: the model is ported to Rust and compiled to WebAssembly, and the interface is a
Svelte page with every plot of the Qt GUI. The model itself (methods, validation, caveats,
credits) is described in the [top-level README](../README.md).

Instead of one tab at a time it is a dashboard: the key numbers stay on top, and a geometry
or field picture, a frequency sweep, a snapshot at the view frequency and the full table
(one column per coil) are visible together. Both coils are entered side by side. A click in
a sweep plot sets the view frequency; the side view reads |B| under the pointer, and a click
there moves the height of the Bz(x) cut. Each panel folds away by its heading or expands to
the whole results area (Escape restores). The wire-pair calculator is a separate mode.

It is laid out as a desktop tool: the inputs on a rail on the left, the results on the desk,
a status bar below. The panels share the height of the window and the plots fit their
panel; on a small window the desk scrolls rather than squeezing them, and on a phone the
page scrolls. The look (monospace, ruled like a datasheet, light only) gives every colour
one job: ivory cells are typed into, steel keys are pressed, white holds results, and coil
A is drawn in ink, coil B in dashed magenta, in every plot.

```bash
pnpm install && pnpm dev    # needs the Rust toolchain pinned in rust/rust-toolchain.toml
```

* **Python stays the reference.** `../python/tests/port/` runs every Rust kernel and the
  whole app computation against the Python code (agreement 1e-16 to 1e-10, each tolerance
  justified by the conditioning in its test). They need cargo and Node and skip otherwise.
* **Speed:** the default GUI case computes in about 0.3 s in the browser (Python: 0.5 s); the
  capacitance solve is 2.5–4× faster than the Python code under Pyodide
  (`../python/tests/port/bench.py --pyodide`).

## How it is built

```
rust/               the model in Rust (toolchain pinned in rust/rust-toolchain.toml)
  crates/core         one module per Python module, plus app.rs (parameters -> everything
                      the app shows) and pair.rs (the wire-pair calculator)
  crates/web          the WebAssembly module: exports alloc / dealloc / call, no imports
  crates/check        stdin/stdout driver used by the port tests
src/                the interface (Svelte 5, TypeScript)
  lib/protocol.ts     parameters, defaults and the byte format of the module's `call`
  lib/worker.ts       the model in a Web Worker; the newest request wins
  lib/plot.ts, Frame.svelte, fieldplot.ts   plots (uPlot and SVG)
  lib/help.ts         tooltips and the guide, generated from ../python/src/coilcal/gui/help.py
  App.svelte          the dashboard
scripts/            smoke.ts (Node check of the module), screenshot.ts (headless Chromium)
```

`pnpm build` compiles the Rust crate to `wasm32-unknown-unknown`, copies the module to
`src/lib/coilcal.wasm` and bundles the page into `dist/`: static files with relative paths,
so they can be served from any directory.

## Development

```bash
pnpm install
pnpm dev                     # dev server (builds the WASM module first)
pnpm check && pnpm build     # svelte-check and the production build
(cd rust && cargo fmt --check && cargo clippy --all-targets -- -D warnings && cargo test)
(cd ../python && uv run pytest -q tests/port)    # the port against the Python reference
(cd ../python && uv run python scripts/gen_help.py)   # after editing the help texts
```

## Deployment

`.github/workflows/pages.yml` builds this directory and publishes `dist/` to GitHub Pages on
every push to `main`. The published site includes `LICENSE.txt` and
`THIRD_PARTY_NOTICES.txt`.

Licence: [MIT](../LICENSE).
