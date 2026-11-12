<!-- Equal-aspect plot frame in data coordinates (y up): axes with ticks and labels, a clip
     region for the content, and an optional colour bar. Content is drawn by the `children`
     snippet in data coordinates (it is placed under a y flip). `onprobe` reports the data
     point under the pointer (null outside the axes), `onpick` a click or tap on one. -->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import { blues, css, ticks } from './fieldplot';

  interface ColorBar {
    label: string;
    /** Tick values and their position t in [0, 1] along the bar. */
    ticks: { t: number; text: string }[];
  }

  let {
    x0,
    x1,
    y0,
    y1,
    xLabel,
    yLabel,
    colorbar,
    label,
    maxHeight = 0.7,
    onprobe,
    onpick,
    children,
  }: {
    x0: number;
    x1: number;
    y0: number;
    y1: number;
    xLabel: string;
    yLabel: string;
    colorbar?: ColorBar;
    /** Accessible description of the plot. */
    label: string;
    /** Height limit as a fraction of the viewport height. */
    maxHeight?: number;
    onprobe?: (point: { x: number; y: number } | null) => void;
    onpick?: (point: { x: number; y: number }) => void;
    children: Snippet;
  } = $props();

  const uid = $props.id();
  const W = $derived(x1 - x0);
  const H = $derived(y1 - y0);
  // font size in data units that renders at FONT_PX: the drawing scales with the element,
  // which is limited by its width and by maxHeight; margins grow with f, so iterate
  const FONT_PX = 12;
  let width = $state(0);
  let innerHeight = $state(0);
  const kx = $derived(4.2 + (colorbar ? 7.5 : 1.2)); // left + right margin / f
  const ky = 4.0; // top + bottom margin / f
  const f = $derived.by(() => {
    let f = Math.max(W, 0.6 * H) / 56;
    if (!width) return f;
    for (let i = 0; i < 4; i++) {
      const scale = Math.min(width / (W + kx * f), (maxHeight * innerHeight) / (H + ky * f));
      f = FONT_PX / scale;
    }
    return f;
  });
  const ml = $derived(4.2 * f);
  const mb = $derived(3.2 * f);
  const mt = $derived(0.8 * f);
  const mr = $derived((kx - 4.2) * f);
  const xt = $derived(ticks(x0, x1, Math.max(3, Math.round(W / (6 * f)))));
  const yt = $derived(ticks(y0, y1, Math.max(2, Math.round(H / (3 * f)))));
  const fmt = (v: number) => Number(v.toPrecision(6)).toString();
  const stops = Array.from({ length: 9 }, (_, i) => i / 8);

  /** Data coordinates of a pointer event, or null outside the axes. */
  function locate(e: MouseEvent & { currentTarget: SVGSVGElement }) {
    const ctm = e.currentTarget.getScreenCTM()!;
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
    const [x, y] = [p.x, -p.y];
    return x >= x0 && x <= x1 && y >= y0 && y <= y1 ? { x, y } : null;
  }
  function pick(e: MouseEvent & { currentTarget: SVGSVGElement }) {
    const p = locate(e);
    if (p) onpick?.(p);
  }
</script>

<svelte:window bind:innerHeight />
<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_noninteractive_element_interactions
     (pointer extras: the readout is supplementary and what a click sets also has an input) -->
<svg
  bind:clientWidth={width}
  class={{ live: onprobe || onpick }}
  onpointermove={onprobe && ((e) => onprobe(locate(e)))}
  onpointerdown={onprobe && ((e) => onprobe(locate(e)))}
  onpointerleave={onprobe && (() => onprobe(null))}
  onclick={onpick && pick}
  viewBox="{x0 - ml} {-y1 - mt} {W + ml + mr} {H + mt + mb}"
  style:max-height="{maxHeight * 100}vh"
  role="img"
  aria-label={label}
  font-size={f}
>
  <defs>
    <clipPath id="{uid}-clip"><rect x={x0} y={y0} width={W} height={H} /></clipPath>
    {#if colorbar}
      <linearGradient id="{uid}-cb" x1="0" y1="1" x2="0" y2="0">
        {#each stops as t (t)}<stop offset={t} stop-color={css(blues(t))} />{/each}
      </linearGradient>
    {/if}
  </defs>
  <g transform="scale(1 -1)">
    <g clip-path="url(#{uid}-clip)">{@render children()}</g>
  </g>
  <g class="axes" stroke-width={f / 12}>
    <rect x={x0} y={-y1} width={W} height={H} fill="none" />
    {#each xt as v (v)}
      <line x1={v} x2={v} y1={-y0} y2={-y0 + 0.4 * f} />
      <text x={v} y={-y0 + 1.5 * f} text-anchor="middle">{fmt(v)}</text>
    {/each}
    {#each yt as v (v)}
      <line x1={x0} x2={x0 - 0.4 * f} y1={-v} y2={-v} />
      <text x={x0 - 0.7 * f} y={-v + 0.35 * f} text-anchor="end">{fmt(v)}</text>
    {/each}
    <text class="label" x={x0 + W / 2} y={-y0 + 2.9 * f} text-anchor="middle">{xLabel}</text>
    <text class="label" transform="translate({x0 - 3.6 * f} {-y0 - H / 2}) rotate(-90)"
      text-anchor="middle">{yLabel}</text>
    {#if colorbar}
      {@const cx = x1 + 1.2 * f}
      <rect x={cx} y={-y1} width={f} height={H} fill="url(#{uid}-cb)" />
      {#each colorbar.ticks as tk (tk.t)}
        <line x1={cx + f} x2={cx + 1.4 * f} y1={-y0 - tk.t * H} y2={-y0 - tk.t * H} />
        <text x={cx + 1.6 * f} y={-y0 - tk.t * H + 0.35 * f}>{tk.text}</text>
      {/each}
      <text class="label" transform="translate({cx + 6.6 * f} {-y0 - H / 2}) rotate(-90)"
        text-anchor="middle">{colorbar.label}</text>
    {/if}
  </g>
</svg>

<style>
  svg {
    display: block;
    width: 100%;
    overflow: visible;
  }
  .live {
    cursor: crosshair;
  }
  .axes line,
  .axes rect {
    stroke: var(--muted);
  }
  .axes text {
    fill: var(--muted);
    stroke: none;
  }
  .axes text.label {
    fill: var(--ink);
  }
</style>
