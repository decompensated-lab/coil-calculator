// Runs the Rust/WASM model off the main thread: {id, params} in, {id, resp, ms} out.
import wasmUrl from './coilcal.wasm?url';
import { type Exports, type Params, callWasm, decode, encode } from './protocol';

const scope = self as unknown as Worker;
let module: Promise<Exports> | null = null;

async function load(): Promise<Exports> {
  const bytes = await (await fetch(wasmUrl)).arrayBuffer();
  const { instance } = await WebAssembly.instantiate(bytes);
  return instance.exports as unknown as Exports;
}

scope.onmessage = async (e: MessageEvent<{ id: number; params: Params }>) => {
  const { id, params } = e.data;
  try {
    module ??= load();
    const ex = await module;
    const t0 = performance.now();
    const resp = decode(callWasm(ex, encode(params)));
    const ms = performance.now() - t0;
    const transfer = resp.ok
      ? Object.values(resp.raw).flatMap((v) => ('data' in v ? [v.data.buffer] : []))
      : [];
    scope.postMessage({ id, resp, ms }, transfer);
  } catch (err) {
    module = null; // a trap (Rust panic) leaves the instance unusable: start over
    scope.postMessage({ id, resp: { ok: false, error: `internal error: ${err}` }, ms: 0 });
  }
};
