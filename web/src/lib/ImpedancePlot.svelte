<!-- Input impedance of each coil vs frequency (gui/plots.py draw_impedance). -->
<script lang="ts">
  import { COIL_COLORS, type Mark, type Panel, charts } from './plot';
  import { type Results, abs, at } from './results';

  let { r, onview }: { r: Results; onview: (mhz: number) => void } = $props();

  function panels(r: Results): Panel[] {
    const nc = r.coils.length;
    const mhz = Array.from(r.freqs, (f) => f / 1e6);
    const top: number[][] = [mhz];
    const bottom: number[][] = [mhz];
    const series = [];
    for (let k = 0; k < nc; k++) {
      const [lF, rF, lDc] = [r.lF(k), r.rF(k), r.lDc[k]];
      const w = (i: number) => 2 * Math.PI * r.freqs[i];
      const z = (i: number) => at(r.z, (i * nc + k) * nc + k);
      top.push(mhz.map((_, i) => abs(z(i))), mhz.map((_, i) => Math.hypot(rF[i], w(i) * lF[i])));
      bottom.push(mhz.map((_, i) => z(i).im / w(i) / lDc), mhz.map((_, i) => lF[i] / lDc));
      const name = `coil ${'AB'[k]}`;
      series.push(
        { label: `${name} network`, stroke: COIL_COLORS[k], width: 1.5 },
        { label: `${name} quasi-DC`, stroke: COIL_COLORS[k], width: 1.5, dash: [2, 4] },
      );
    }
    // view frequency (grey) and each coil's first resonance in the network (dashed)
    const marks: Mark[] = [
      { x: r.fView / 1e6, color: 'muted' },
      ...[...r.srfHere].flatMap((f, k) =>
        Number.isFinite(f) ? [{ x: f / 1e6, color: COIL_COLORS[k], dash: [6, 4] }] : [],
      ),
    ];
    return [
      { data: top, series, height: 240, xLog: true, yLog: true, xHidden: true,
        xLabel: 'f [MHz]', yLabel: '|Z_in| [Ω]', marks },
      { data: bottom, series: series.map((s) => ({ ...s })), height: 150, xLog: true,
        xTicks: 'plain', yRange: [0, 3], xLabel: 'frequency [MHz]', yLabel: 'L_eff / L_DC',
        marks, legend: false },
    ];
  }
</script>

<h3 class="plot-title">
  Input impedance (other coil open) — dotted: quasi-DC R(f)+jωL(f), dashed: SRF
</h3>
<div class="chart" {@attach charts(panels(r), 'impedance', onview)}></div>
