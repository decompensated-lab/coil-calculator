<!-- Input impedance of each coil vs frequency (gui/plots.py draw_impedance). -->
<script lang="ts">
  import uPlot from 'uplot';
  import 'uplot/dist/uPlot.min.css';
  import { type Results, abs, at, g, si } from './results';

  let { r }: { r: Results } = $props();

  const COLORS = ['#2a78d6', '#eb6834'];

  function charts(r: Results) {
    return (node: HTMLElement) => {
      const css = getComputedStyle(node);
      const muted = css.getPropertyValue('--muted').trim();
      const grid = css.getPropertyValue('--grid').trim();
      const nc = r.coils.length;
      const mhz = Array.from(r.freqs, (f) => f / 1e6);
      const top: number[][] = [mhz];
      const bottom: number[][] = [mhz];
      const series: uPlot.Series[] = [{ label: 'f [MHz]' }];
      for (let k = 0; k < nc; k++) {
        const zAbs: number[] = [];
        const zQuasi: number[] = [];
        const lEff: number[] = [];
        const lQuasi: number[] = [];
        const [lF, rF, lDc] = [r.lF(k), r.rF(k), r.lDc[k]];
        r.freqs.forEach((f, i) => {
          const w = 2 * Math.PI * f;
          const z = at(r.z, (i * nc + k) * nc + k);
          zAbs.push(abs(z));
          zQuasi.push(Math.hypot(rF[i], w * lF[i]));
          lEff.push(z.im / w / lDc);
          lQuasi.push(lF[i] / lDc);
        });
        top.push(zAbs, zQuasi);
        bottom.push(lEff, lQuasi);
        const name = `coil ${'AB'[k]}`;
        series.push(
          { label: `${name} network`, stroke: COLORS[k], width: 1.5 },
          { label: `${name} quasi-DC`, stroke: COLORS[k], width: 1.5, dash: [2, 4] },
        );
      }
      // view frequency (grey) and each coil's resonance in the network (dashed)
      const marks = (u: uPlot) => {
        const { ctx, bbox } = u;
        const line = (fMHz: number, color: string, dash: number[]) => {
          const px = u.valToPos(fMHz, 'x', true);
          if (px < bbox.left || px > bbox.left + bbox.width) return;
          ctx.save();
          ctx.strokeStyle = color;
          ctx.setLineDash(dash);
          ctx.lineWidth = devicePixelRatio;
          ctx.beginPath();
          ctx.moveTo(px, bbox.top);
          ctx.lineTo(px, bbox.top + bbox.height);
          ctx.stroke();
          ctx.restore();
        };
        line(r.fView / 1e6, muted, []);
        r.srfHere.forEach((f, k) => Number.isFinite(f) && line(f / 1e6, COLORS[k], [6, 4]));
      };
      const axis = { stroke: muted, grid: { stroke: grid, width: 1 }, ticks: { stroke: grid } };
      const siTicks = (_u: uPlot, v: number[]) => v.map((x) => (x == null ? '' : si(x, '', 3).trim()));
      // the sweep exactly (uPlot would round a log range out to whole decades)
      const x = { time: false, distr: 3, range: (_u: uPlot, lo: number, hi: number) => [lo, hi] } as uPlot.Scale;
      const common = {
        width: node.clientWidth,
        cursor: { sync: { key: 'impedance' } },
        hooks: { draw: [marks] },
      };
      const heights = [300, 170];
      const upper = new uPlot(
        {
          ...common,
          height: heights[0],
          scales: { x, y: { distr: 3 } },
          series,
          axes: [
            { ...axis, values: (_u, v) => v.map(() => '') },
            { ...axis, label: '|Z_in| [Ω]', values: siTicks, size: 64 },
          ],
        },
        top as uPlot.AlignedData,
        node,
      );
      const lower = new uPlot(
        {
          ...common,
          height: heights[1],
          scales: { x, y: { auto: false, range: [0, 3] } },
          series: series.map((s) => ({ ...s })),
          legend: { show: false },
          axes: [
            { ...axis, label: 'frequency [MHz]', values: (_u, v) => v.map((f) => (f == null ? '' : g(f, 3))) },
            { ...axis, label: 'L_eff / L_DC', size: 64 },
          ],
        },
        bottom as uPlot.AlignedData,
        node,
      );
      const ro = new ResizeObserver(() => {
        upper.setSize({ width: node.clientWidth, height: heights[0] });
        lower.setSize({ width: node.clientWidth, height: heights[1] });
      });
      ro.observe(node);
      return () => {
        ro.disconnect();
        upper.destroy();
        lower.destroy();
      };
    };
  }
</script>

<h3>Input impedance (other coil open) — dotted: quasi-DC R(f)+jωL(f), dashed: SRF</h3>
<div class="chart" {@attach charts(r)}></div>

<style>
  h3 {
    margin: 0 0 4px;
    font-size: 0.95rem;
    font-weight: 500;
  }
  .chart {
    width: 100%;
    min-width: 0;
  }
</style>
