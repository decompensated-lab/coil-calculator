// Runs a WASI (preview 1) module under Node's built-in node:wasi, with stdio passed through.
import { readFile } from "node:fs/promises";
import { WASI } from "node:wasi";

const wasi = new WASI({ version: "preview1", args: process.argv.slice(2), env: {} });
const module = await WebAssembly.compile(await readFile(process.argv[2]));
const instance = await WebAssembly.instantiate(module, wasi.getImportObject());
process.exitCode = wasi.start(instance);
