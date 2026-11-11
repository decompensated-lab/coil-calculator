<!-- x–z plane through the coil axes: |B| (peak) map, field lines at the phase of maximum
     field, wires and formers at true scale (gui/plots.py draw_side_view). -->
<script lang="ts">
  import { decades, heatmap, logNorm, percentile, streamlines } from './fieldplot';
  import Frame from './Frame.svelte';
  import { COIL_COLORS, coilName } from './plot';
  import { type Results, g, si } from './results';

  let { r }: { r: Results } = $props();

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
    return {
      x, z, dx, dz, lo, hi, coils,
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
</script>

<h3 class="plot-title">
  {r.params.vna_setup} — {g(r.params.p_dbm, 6)} dBm at P1, {si(r.fView, 'Hz')}
</h3>
<Frame x0={v.x[0]} x1={v.x[v.x.length - 1]} y0={v.z[0]} y1={v.z[v.z.length - 1]}
  xLabel="x [mm]" yLabel="z (coil A axis) [mm]"
  colorbar={{ label: '|B| [µT peak]', ticks: v.ticks }}
  label="Magnetic field magnitude and field lines in the plane of the coil axes">
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
</Frame>

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
</style>
