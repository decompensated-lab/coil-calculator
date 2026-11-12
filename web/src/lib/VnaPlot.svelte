<!-- S-parameters of the selected VNA setup: |S| in dB and phase, or (`smith`) a Smith chart
     (gui/plots.py draw_vna and smith_grid). -->
<script lang="ts">
  import { AQUA, BLUE, ORANGE, type Panel, charts } from './plot';
  import { type Results, abs, at, deg, g } from './results';

  let { r, smith: chart = false, onview }: { r: Results; smith?: boolean; onview: (mhz: number) => void } =
    $props();

  const R = [0.2, 0.5, 1, 2, 5]; // constant-r circles and constant-x arcs of the grid

  function traces(r: Results) {
    const nf = r.freqs.length;
    const pick = (j: number) => Array.from({ length: nf }, (_, i) => at(r.s, i * 4 + j));
    const all = [
      { name: 'S11', color: BLUE, s: pick(0), smith: true },
      { name: 'S21', color: ORANGE, s: pick(2), smith: false },
    ];
    if (r.vnaPair) all.push({ name: 'S22', color: AQUA, s: pick(3), smith: true });
    return all;
  }

  function panels(r: Results): Panel[] {
    const t = traces(r);
    const mhz = Array.from(r.freqs, (f) => f / 1e6);
    const series = t.map((x) => ({ label: x.name, stroke: x.color, width: 1.5 }));
    const marks = [{ x: r.fView / 1e6, color: 'muted' }];
    return [
      {
        data: [mhz, ...t.map((x) => x.s.map((s) => 20 * Math.log10(Math.max(abs(s), 1e-15))))],
        series, height: 220, xLog: true, xHidden: true, xLabel: 'f [MHz]', yLabel: '|S| [dB]',
        marks,
      },
      {
        data: [mhz, ...t.map((x) => x.s.map(deg))],
        series: series.map((s) => ({ ...s })), height: 170, xLog: true, xTicks: 'plain',
        yRange: [-185, 185], xLabel: 'frequency [MHz]', yLabel: 'phase [°]', marks,
        legend: false,
      },
    ];
  }

  const smith = $derived(
    traces(r)
      .filter((t) => t.smith)
      .map((t) => ({
        ...t,
        points: t.s.map((s) => `${s.re.toFixed(5)},${s.im.toFixed(5)}`).join(' '),
        view: t.s[r.iView],
      })),
  );
</script>

<h3 class="plot-title">{r.params.vna_setup}, Z0 = {g(r.params.z0, 6)} Ω</h3>
{#if !chart}
  <div class="chart" {@attach charts(panels(r), { sync: 'vna', onpick: onview })}></div>
{:else}
  <figure>
    <svg viewBox="-1.08 -1.08 2.16 2.16" role="img" aria-labelledby="smith-caption">
      <defs>
        <clipPath id="unit-disk"><circle r="1" /></clipPath>
      </defs>
      <g transform="scale(1 -1)">
        <g class="grid" clip-path="url(#unit-disk)">
          {#each R as rn (rn)}
            <circle cx={rn / (1 + rn)} r={1 / (1 + rn)} />
            <circle cx="1" cy={1 / rn} r={1 / rn} />
            <circle cx="1" cy={-1 / rn} r={1 / rn} />
          {/each}
          <line x1="-1" x2="1" y1="0" y2="0" />
        </g>
        <circle class="rim" r="1" />
        {#each smith as t (t.name)}
          <polyline points={t.points} stroke={t.color} />
          <circle class="dot" cx={t.view.re} cy={t.view.im} r="0.035" style:fill={t.color} />
        {/each}
      </g>
    </svg>
    <figcaption id="smith-caption">
      Smith chart (● = view f):
      {#each smith as t (t.name)}<span class="key" style:color={t.color}>{t.name}</span>{/each}
    </figcaption>
  </figure>
{/if}

<style>
  figure {
    margin: 0;
  }
  svg {
    display: block;
    width: 100%;
    max-height: 420px;
    overflow: visible;
  }
  svg circle,
  svg line,
  svg polyline {
    fill: none;
    vector-effect: non-scaling-stroke;
  }
  .grid > * {
    stroke: var(--grid);
    stroke-width: 0.8;
  }
  .rim {
    stroke: var(--muted);
    stroke-width: 1;
  }
  polyline {
    stroke-width: 1.5;
  }
  svg circle.dot {
    stroke: var(--bg);
    stroke-width: 2;
  }
  .key {
    margin-left: 0.5em;
  }
  figcaption {
    text-align: center;
    color: var(--muted);
  }
</style>
