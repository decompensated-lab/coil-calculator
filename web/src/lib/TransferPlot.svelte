<!-- A → B transfer: |Z21| against the quasi-static ωM and the voltage into the load
     (gui/plots.py draw_transfer). -->
<script lang="ts">
  import { BLUE, ORANGE, type Mark, type Panel, charts } from './plot';
  import { type Results, abs, at, div, g, mul } from './results';

  let { r, onview }: { r: Results; onview: (mhz: number) => void } = $props();

  function panels(r: Results): Panel[] {
    const mhz = Array.from(r.freqs, (f) => f / 1e6);
    const zl = { re: r.params.z_load, im: 0 };
    const z21 = mhz.map((_, i) => at(r.z, i * 4 + 2));
    const qs = mhz.map((_, i) => 2 * Math.PI * r.freqs[i] * Math.abs(r.mStatic));
    const vl = z21.map((z, i) => {
      const z22 = at(r.z, i * 4 + 3);
      return abs(div(mul(z, zl), { re: zl.re + z22.re, im: z22.im }));
    });
    const marks: Mark[] = [{ x: r.fView / 1e6, color: 'muted' }];
    return [
      {
        data: [mhz, z21.map(abs), qs, vl],
        series: [
          { label: 'network |Z21| (B open)', stroke: BLUE, width: 1.5 },
          { label: 'quasi-static ωM', stroke: 'gray', width: 1.5, dash: [2, 4] },
          { label: `into ${g(r.params.z_load, 6)} Ω`, stroke: ORANGE, width: 1.5 },
        ],
        height: 240, xLog: true, yLog: true, xHidden: true, xLabel: 'f [MHz]',
        yLabel: '|V_B| per A in A [V/A]', marks,
      },
      {
        data: [mhz, z21.map((z, i) => abs(z) / qs[i])],
        series: [{ label: '|Z21| / ωM', stroke: BLUE, width: 1.5 }],
        height: 150, xLog: true, xTicks: 'plain', yRange: [0, 3], xLabel: 'frequency [MHz]',
        yLabel: '|Z21| / ωM', marks: [...marks, { y: 1, color: 'muted', dash: [2, 4] }],
        legend: false,
      },
    ];
  }
</script>

<h3 class="plot-title">A → B transfer</h3>
{#if r.coils.length < 2}
  <p class="muted">Enable coil B for the transfer plot.</p>
{:else}
  <div class="chart" {@attach charts(panels(r), 'transfer', onview)}></div>
{/if}
