<!-- Left: |E| and equipotentials for 1 V across the pair. Right: C′ vs surface gap
     (gui/pair.py draw_pair). -->
<script lang="ts">
  import { contour, decades, heatmap, logNorm, percentile } from './fieldplot';
  import Frame from './Frame.svelte';
  import { DASH, DASH_DOT, DOTTED, GRAY, INK, MAGENTA, TEAL, type Panel, charts } from './plot';
  import { type PairResults, g } from './results';

  let { r }: { r: PairResults } = $props();

  function field(r: PairResults) {
    const [xs, ys, phi] = [r.fieldX, r.fieldY, r.phi];
    const [nx, ny] = [xs.length, ys.length];
    const centres = [-r.spacing / 2, r.spacing / 2];
    const inside = (i: number, j: number) =>
      r.wires.some((w, k) => Math.hypot(xs[i] - centres[k], ys[j]) < w.a);
    // E = −∇φ as numpy.gradient: central differences, one-sided at the edges
    const diff = (f: (k: number) => number, c: ArrayLike<number>, k: number, n: number) => {
      const [lo, hi] = [Math.max(k - 1, 0), Math.min(k + 1, n - 1)];
      return (f(hi) - f(lo)) / (c[hi] - c[lo]);
    };
    const emag = new Float64Array(nx * ny);
    const masked = new Float64Array(nx * ny);
    for (let j = 0; j < ny; j++) {
      for (let i = 0; i < nx; i++) {
        const p = j * nx + i;
        const ex = diff((k) => phi[j * nx + k], xs, i, nx);
        const ey = diff((k) => phi[k * nx + i], ys, j, ny);
        const isIn = inside(i, j);
        emag[p] = isIn ? NaN : Math.hypot(ex, ey) * 1e-3; // V/mm
        masked[p] = isIn ? NaN : phi[p];
      }
    }
    const hi = percentile(emag, 99.7);
    const norm = logNorm(hi * 1e-2, hi);
    const x = Array.from(xs, (v) => v * 1e3);
    const y = Array.from(ys, (v) => v * 1e3);
    const [v1, v2] = [r.v[0].re, r.v[1].re];
    const levels = Array.from({ length: 19 }, (_, k) => Math.min(v1, v2) + ((k + 1) / 20) * Math.abs(v1 - v2));
    const fmt = (a: number, b: number) => `${a.toFixed(4)},${b.toFixed(4)}`;
    return {
      x, y,
      dx: x[1] - x[0],
      dy: y[1] - y[0],
      image: heatmap(emag, nx, ny, norm),
      contours: levels.map((l) => contour(x, y, masked, l, fmt)).join(''),
      ticks: decades(hi * 1e-2, hi).map((v) => ({ t: norm(v), text: g(v, 3) })),
      circles: r.wires.map((w, k) => ({ xc: centres[k] * 1e3, a: w.a * 1e3, b: w.b * 1e3 })),
    };
  }

  function sweep(r: PairResults): Panel[] {
    const pf = (a: Float64Array) => Array.from(a, (c) => c * 1e12);
    const gNow = (r.spacing - r.wires[0].b - r.wires[1].b) * 1e3;
    const uniform = r.sweepUniform.every(Number.isNaN) ? [] : [pf(r.sweepUniform)];
    return [
      {
        data: [Array.from(r.gap, (v) => v * 1e3), pf(r.sweepExact), ...uniform, pf(r.sweepEff), pf(r.sweepBare)],
        series: [
          { label: 'insulated, in air (exact)', stroke: INK, width: 2 },
          ...(uniform.length ? [{ label: 'all space filled, εr', stroke: MAGENTA, width: 1.5, dash: DASH }] : []),
          { label: 'effective-radius approx.', stroke: TEAL, width: 1.5, dash: DASH_DOT },
          { label: 'bare conductors, air', stroke: GRAY, width: 1.5, dash: DOTTED },
        ],
        height: 340, yLog: true, yTicks: 'plain', xLabel: 'insulation surface gap [mm]',
        yLabel: 'C′ [pF/m]',
        marks: [{ x: gNow, color: 'muted' }, { x: gNow, y: r.c.re * 1e12, color: INK }],
      },
    ];
  }

  const f = $derived(field(r));
</script>

<div class="pair">
  <div>
    <h3 class="plot-title">|E| and equipotentials (0.05 V steps)</h3>
    <Frame x0={f.x[0]} x1={f.x[f.x.length - 1]} y0={f.y[0]} y1={f.y[f.y.length - 1]}
      xLabel="x [mm]" yLabel="y [mm]"
      colorbar={{ label: '|E| [V/mm] at 1 V across the pair', ticks: f.ticks }}
      label="Electric field magnitude and equipotentials around the two wires">
      <image href={f.image} x={f.x[0] - f.dx / 2} y={f.y[0] - f.dy / 2}
        width={f.x[f.x.length - 1] - f.x[0] + f.dx} height={f.y[f.y.length - 1] - f.y[0] + f.dy}
        preserveAspectRatio="none" />
      <path class="equi" d={f.contours} />
      {#each f.circles as c (c.xc)}
        {#if c.b > c.a}<circle class="sleeve" cx={c.xc} cy="0" r={c.b} />{/if}
        <circle class="conductor" cx={c.xc} cy="0" r={c.a} />
      {/each}
    </Frame>
  </div>
  <div>
    <h3 class="plot-title">C′ vs spacing</h3>
    <div class="chart" {@attach charts(sweep(r))}></div>
  </div>
</div>

<style>
  .pair {
    display: grid;
    flex: 1;
    grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr);
    grid-auto-rows: minmax(0, 1fr);
    gap: 16px;
    min-height: 0;
    padding: 6px 8px;
  }
  .pair > div {
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .equi {
    fill: none;
    stroke: var(--dim);
    stroke-width: 0.6px;
    vector-effect: non-scaling-stroke;
  }
  .sleeve {
    fill: none;
    stroke: var(--fg);
    stroke-width: 1px;
    vector-effect: non-scaling-stroke;
  }
  .conductor {
    fill: #b87333;
    stroke: var(--fg);
    stroke-width: 1px;
    vector-effect: non-scaling-stroke;
  }
  @media (max-width: 1000px) {
    .pair {
      grid-template-columns: minmax(0, 1fr);
      grid-auto-rows: auto;
    }
  }
</style>
