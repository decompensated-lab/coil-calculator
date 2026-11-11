// Main-thread side of the worker: at most one request in flight; while busy only the newest
// parameters are kept, and a result that is already outdated is dropped.
import type { Params, Response } from './protocol';
import { type Results, view } from './results';

export class Computer {
  result = $state.raw<Results | null>(null);
  error = $state<string | null>(null);
  busy = $state(false);
  ms = $state(0);
  #worker = new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' });
  #inflight: Params | null = null;
  #pending: Params | null = null;
  #id = 0;

  constructor() {
    this.#worker.onmessage = (e: MessageEvent<{ resp: Response; ms: number }>) => {
      const params = this.#inflight!;
      if (this.#pending) {
        this.#send(this.#pending); // this result is outdated
        return;
      }
      this.busy = false;
      this.#inflight = null;
      const { resp, ms } = e.data;
      if (resp.ok) {
        this.result = view(resp.raw, params);
        this.error = null;
        this.ms = ms;
      } else {
        this.error = resp.error;
      }
    };
  }

  /** `params` must be a plain object (use `$state.snapshot`). */
  request(params: Params) {
    if (this.busy) this.#pending = params;
    else this.#send(params);
  }

  #send(params: Params) {
    this.busy = true;
    this.#inflight = params;
    this.#pending = null;
    this.#worker.postMessage({ id: ++this.#id, params });
  }
}
