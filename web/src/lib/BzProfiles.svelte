<!-- Bz along A's axis and across the coils (gui/plots.py draw_bz_profiles): the in-phase part,
     referenced to the phase of Bz at the on-axis maximum, so return flux keeps its sign.
     Dotted: the same coils with a uniform current, their mean turn current (quasi-DC shape). -->
<script lang="ts">
  import Num from './Num.svelte';
  import type { Arr } from './protocol';
  import { COIL_COLORS, DASH, DOTTED, GRAY, INK, type Mark, type Panel, charts, coilName } from './plot';
  import { type Results, at, g, mul, si, driveLabel } from './results';

  let { r, cutZ = $bindable() }: { r: Results; cutZ: number } = $props();

  function view(r: Results) {
    const n = r.lineZ.length;
    let iMax = 0;
    let bMax = 0;
    for (let i = 0; i < n; i++) {
      const b = Math.hypot(r.bzZ.data[2 * i], r.bzZ.data[2 * i + 1]);
      if (b > bMax) [iMax, bMax] = [i, b];
    }
    const ref = at(r.bzZ, iMax);
    const rot = bMax > 0 ? { re: ref.re / bMax, im: -ref.im / bMax } : { re: 1, im: 0 };
    let quad = 0;
    for (let i = 0; i < n; i++) quad = Math.max(quad, Math.abs(mul(at(r.bzZ, i), rot).im));
    // in-phase part in µT; NaN (inside a wire) becomes a gap
    const inphase = (a: Arr) =>
      Array.from({ length: a.data.length / 2 }, (_, i) => {
        const v = mul(at(a, i), rot).re * 1e6;
        return Number.isNaN(v) ? null : v;
      });
    const name = (k: number) => coilName(r.vnaPair, r.setupIndex, k);
    const color = (k: number) => COIL_COLORS[name(k) === 'A' ? 0 : 1];
    const zCut = r.params.x_line_z_mm;
    const zero: Mark = { y: 0, color: 'muted' };
    const bands: Mark[] = r.vnaCoils.map((c, k) => ({
      x: (c.position[2] - c.length / 2) * 1e3,
      x1: (c.position[2] + c.length / 2) * 1e3,
      color: color(k),
      alpha: 0.12,
      label: `coil ${name(k)}`,
    }));
    const radii: Mark[] = r.vnaCoils.flatMap((c, k) =>
      [-1, 1].map((side) => ({
        x: (side * c.mean_radius + c.position[0]) * 1e3,
        color: color(k),
        alpha: 0.6,
      })),
    );
    const series = () => [
      { label: 'network currents', stroke: INK, width: 1.5 },
      { label: 'mean turn current', stroke: GRAY, width: 1.5, dash: DOTTED },
    ];
    const panels: Panel[] = [
      {
        data: [Array.from(r.lineZ, (z) => z * 1e3), inphase(r.bzZ), inphase(r.bzZUniform)],
        series: series(),
        height: 190,
        xName: 'z [mm]',
        xLabel: 'z along coil A axis [mm]  (dashed: height of the B_z(x) cut)',
        yLabel: 'B_z [µT peak]',
        marks: [...bands, { x: zCut, color: 'muted', dash: DASH }, zero],
      },
      {
        data: [Array.from(r.lineX, (x) => x * 1e3), inphase(r.bzX), inphase(r.bzXUniform)],
        series: series(),
        height: 190,
        xName: 'x [mm]',
        xLabel: `x [mm] at z = ${g(zCut, 6)} mm  (vertical lines: winding radii)`,
        yLabel: 'B_z [µT peak]',
        marks: [...radii, zero],
      },
    ];
    return { panels, quad: quad / Math.max(bMax, 1e-300) };
  }

  const v = $derived(view(r));
</script>

<div class="head">
  <h3 class="plot-title">
    In-phase B<sub>z</sub> — {r.params.vna_setup}, {driveLabel(r)} at P1, {si(r.fView, 'Hz')}
    (quadrature part ≤ {(100 * v.quad).toFixed(1)}% of peak)
  </h3>
  <div class="props one">
    <Num label="cut at z" tip="x_line_z" bind:value={cutZ} unit="mm" step={1} />
  </div>
</div>
<div class="chart" {@attach charts(v.panels)}></div>

<style>
  .head {
    display: flex;
    flex: none;
    align-items: start;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 2px;
  }
  .head .plot-title {
    flex: 1 1 0;
    min-width: 0;
  }
  .head .props {
    flex: none;
    grid-template-columns: auto 5em auto;
  }
</style>
