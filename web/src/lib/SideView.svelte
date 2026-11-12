<!-- x–z plane through the coil axes: |B| (peak) map, field lines at the phase of maximum
     field, wires and formers at true scale (gui/plots.py draw_side_view). The pointer reads
     |B|; a click moves the height of the Bz(x) cut (dashed). -->
<script lang="ts">
  import { decades, heatmap, logNorm, percentile, streamlines } from './fieldplot';
  import Frame from './Frame.svelte';
  import { COIL_COLORS, coilName } from './plot';
  import { type Results, g, si, driveLabel } from './results';

  let { r, oncut }: { r: Results; oncut: (z_mm: number) => void } = $props();

  function view(r: Results) {
    const x = Array.from(r.fieldX, (v) => v * 1e3);
    const z = Array.from(r.fieldZ, (v) => v * 1e3);
    const [nx, nz] = [x.length, z.length];
    const b = r.fieldB.data; // (nz, nx, 3) complex, interleaved
    const n = nx * nz;
    const mag = new Float64Array(n);
    // phase that maximises the real field energy: θ = arg(Σ b·b) / 2
    let [sr, si_] = [0, 0];
    for (let p = 0; p < n; p++) {
      let m = 0;
      for (let c = 0; c < 3; c++) {
        const [re, im] = [b[6 * p + 2 * c], b[6 * p + 2 * c + 1]];
        m += re * re + im * im;
        sr += re * re - im * im;
        si_ += 2 * re * im;
      }
      mag[p] = Math.sqrt(m) * 1e6; // µT
    }
    const th = 0.5 * Math.atan2(si_, sr);
    const [ct, st] = [Math.cos(th), Math.sin(th)];
    const real = (p: number, c: number) => b[6 * p + 2 * c] * ct + b[6 * p + 2 * c + 1] * st;
    const bx = Float64Array.from({ length: n }, (_, p) => real(p, 0));
    const bz = Float64Array.from({ length: n }, (_, p) => real(p, 2));
    const hi = percentile(mag, 99.5);
    const lo = Math.max(hi * 1e-3, Math.min(...mag));
    const norm = logNorm(lo, hi);
    const lines = streamlines(x, z, bx, bz, 1.3);
    const [dx, dz] = [(x[nx - 1] - x[0]) / (nx - 1), (z[nz - 1] - z[0]) / (nz - 1)];
    const coils = r.vnaCoils.map((c, k) => {
      const color = COIL_COLORS[coilName(r.vnaPair, r.setupIndex, k) === 'A' ? 0 : 1];
      const zt = Array.from({ length: c.n_turns }, (_, i) =>
        ((i - (c.n_turns - 1) / 2) * c.pitch + c.position[2]) * 1e3,
      );
      return { c, color, zt, x0: c.position[0] * 1e3, zc: c.position[2] * 1e3 };
    });
    /** |B| [µT] at a point, bilinear between the grid nodes. */
    const probe = (px: number, pz: number) => {
      const [fx, fz] = [(px - x[0]) / dx, (pz - z[0]) / dz];
      const [i, j] = [Math.min(Math.floor(fx), nx - 2), Math.min(Math.floor(fz), nz - 2)];
      const [u, w] = [fx - i, fz - j];
      const m = (a: number, b: number) => mag[(j + b) * nx + i + a];
      return (1 - w) * ((1 - u) * m(0, 0) + u * m(1, 0)) + w * ((1 - u) * m(0, 1) + u * m(1, 1));
    };
    return {
      x, z, dx, dz, lo, hi, coils, probe,
      image: heatmap(mag, nx, nz, norm),
      paths: lines.map((l) => 'M' + l.map(([a, c]) => `${a.toFixed(2)},${c.toFixed(2)}`).join('L')),
      // one arrow per line, at its middle, pointing along the field
      arrows: lines.map((l) => {
        const m = Math.floor(l.length / 2);
        const [p, q] = [l[Math.max(m - 1, 0)], l[Math.min(m + 1, l.length - 1)]];
        return { at: l[m], angle: (Math.atan2(q[1] - p[1], q[0] - p[0]) * 180) / Math.PI };
      }),
      ticks: decades(lo, hi).map((v) => ({ t: norm(v), text: g(v, 3) })),
    };
  }

  const v = $derived(view(r));
  const a = $derived((v.x[v.x.length - 1] - v.x[0]) / 120); // arrow size
  let hover: { x: number; y: number } | null = $state(null);
</script>

<h3 class="plot-title">
  {r.params.vna_setup} — {driveLabel(r)} at P1, {si(r.fView, 'Hz')}
</h3>
<Frame x0={v.x[0]} x1={v.x[v.x.length - 1]} y0={v.z[0]} y1={v.z[v.z.length - 1]}
  xLabel="x [mm]" yLabel="z (coil A axis) [mm]"
  colorbar={{ label: '|B| [µT peak]', ticks: v.ticks }} maxHeight={0.6}
  label="Magnetic field magnitude and field lines in the plane of the coil axes"
  onprobe={(p) => (hover = p)} onpick={(p) => oncut(Number(p.y.toFixed(1)))}>
  <image href={v.image} x={v.x[0] - v.dx / 2} y={v.z[0] - v.dz / 2}
    width={v.x[v.x.length - 1] - v.x[0] + v.dx} height={v.z[v.z.length - 1] - v.z[0] + v.dz}
    preserveAspectRatio="none" />
  <g class="lines">
    {#each v.paths as d, i (i)}<path {d} />{/each}
  </g>
  <g class="arrows">
    {#each v.arrows as ar, i (i)}
      <path d="M{-a},{-0.6 * a}L{a},0L{-a},{0.6 * a}Z"
        transform="translate({ar.at[0]} {ar.at[1]}) rotate({ar.angle})" />
    {/each}
  </g>
  {#each v.coils as { c, color, zt, x0, zc }, k (k)}
    {#each [-1, 1] as side (side)}
      {@const xc = side * c.mean_radius * 1e3 + x0}
      {@const xf = side * (c.former_d / 2) * 1e3 + x0}
      {#if c.former}
        {@const half = (c.length / 2 + c.former.overhang) * 1e3}
        {@const wall = c.former.wall * 1e3}
        <rect class="former" x={side > 0 ? xf - wall : xf} y={zc - half} width={wall}
          height={2 * half} stroke={color} />
      {:else}
        <line x1={xf} x2={xf} y1={zt[0] - 3} y2={zt[zt.length - 1] + 3} stroke={color}
          opacity="0.6" />
      {/if}
      {#each zt as zi (zi)}
        <circle cx={xc} cy={zi} r={c.wire_d * 500} fill={color} />
      {/each}
    {/each}
  {/each}
  <line class="cut" x1={v.x[0]} x2={v.x[v.x.length - 1]} y1={r.params.x_line_z_mm}
    y2={r.params.x_line_z_mm} />
  {#if hover}
    <line class="hair" x1={hover.x} x2={hover.x} y1={v.z[0]} y2={v.z[v.z.length - 1]} />
    <line class="hair" x1={v.x[0]} x2={v.x[v.x.length - 1]} y1={hover.y} y2={hover.y} />
  {/if}
</Frame>
<p class="readout muted">
  {#if hover}
    x = {hover.x.toFixed(1)} mm, z = {hover.y.toFixed(1)} mm:
    <b>|B| = {si(v.probe(hover.x, hover.y) * 1e-6, 'T', 3)}</b> peak
  {:else}
    Point at the map to read |B|; click to move the B<sub>z</sub>(x) cut (dashed).
  {/if}
</p>

<style>
  .lines path {
    fill: none;
    stroke: var(--muted);
    stroke-width: 0.7px;
    vector-effect: non-scaling-stroke;
  }
  .arrows path {
    fill: var(--muted);
  }
  .former {
    fill: #d9d6cc;
    fill-opacity: 0.8;
    stroke-width: 0.6px;
    vector-effect: non-scaling-stroke;
  }
  line {
    vector-effect: non-scaling-stroke;
  }
  .cut,
  .hair {
    stroke: var(--ink);
    stroke-width: 1px;
    pointer-events: none;
  }
  .cut {
    stroke-dasharray: 6 4;
  }
  .hair {
    opacity: 0.45;
  }
  .readout {
    margin: 4px 0 0;
    min-height: 1.4em;
    font-variant-numeric: tabular-nums;
  }
  .readout b {
    color: var(--ink);
  }
</style>
