// Runs the browser module (coilcal_web.wasm) under Node with the TS client code and prints
// JSON for tests/port/test_web.py. Usage: node scripts/smoke.ts <path to coilcal_web.wasm>
import { readFileSync } from 'node:fs';
import {
  type Arr, type Exports, callWasm, decode, defaultParams, encode, flatten,
} from '../src/lib/protocol.ts';

const { instance } = await WebAssembly.instantiate(readFileSync(process.argv[2]));
const ex = instance.exports as unknown as Exports;
const p = defaultParams();
const t0 = performance.now();
const resp = decode(callWasm(ex, encode(p)));
const secs = (performance.now() - t0) / 1000;
if (!resp.ok) throw new Error(resp.error);
const t1 = performance.now();
decode(callWasm(ex, encode({ ...p, f_view_mhz: 3 }))); // geometry unchanged: cached
const secsWarm = (performance.now() - t1) / 1000;
const pick = (k: string) => Array.from((resp.raw[k] as Arr).data);
const bad = decode(callWasm(ex, encode({ ...p, b_enabled: false })));
console.log(JSON.stringify({
  params: flatten(p),
  freqs: pick('freqs'),
  z: pick('z'),
  srf_net: pick('srf_net'),
  scalars: pick('scalars'),
  warnings: resp.raw.warnings,
  error: bad.ok ? null : bad.error,
  secs,
  secsWarm,
}));
