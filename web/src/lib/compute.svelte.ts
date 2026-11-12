// Main-thread side of a worker: at most one request in flight; while busy only the newest
// parameters are kept, and a result that is already outdated is dropped. `flatten` turns the
// parameters into the request, `view` the response into results.
import type { Raw, Response } from './protocol';

export class Computer<P, R> {
  result = $state.raw<R | null>(null);
  error = $state<string | null>(null);
  busy = $state(false);
  ms = $state(0);
  #worker = new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' });
  #inflight: P | null = null;
  #pending: P | null = null;
  #id = 0;

  constructor(
    private flatten: (p: P) => Record<string, number>,
    private view: (raw: Raw, p: P) => R,
  ) {
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
        this.result = this.view(resp.raw, params);
        this.error = null;
        this.ms = ms;
      } else {
        this.error = resp.error;
      }
    };
  }

  /** `params` must be a plain object (use `$state.snapshot`). */
  request(params: P) {
    if (this.busy) this.#pending = params;
    else this.#send(params);
  }

  #send(params: P) {
    this.busy = true;
    this.#inflight = params;
    this.#pending = null;
    this.#worker.postMessage({ id: ++this.#id, values: this.flatten(params) });
  }
}
