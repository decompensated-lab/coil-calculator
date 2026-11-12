<!-- The windings as rows of wire cross-sections at true size and pitch, one strip per coil,
     each centred on its own winding and all at the same scale (gui/plots.py
     draw_cross_section). Fill: turn current or turn potential for the VNA drive. -->
<script lang="ts">
  import Choice from './Choice.svelte';
  import { blues, css } from './fieldplot';
  import Frame from './Frame.svelte';
  import { COIL_COLORS, coilName } from './plot';
  import { type Results, abs, at, g, si, driveLabel } from './results';

  export type Fill = '|I|' | '|V|' | 'none';
  const FILLS: Fill[] = ['|I|', '|V|', 'none'];
  let { r, fill = $bindable() }: { r: Results; fill: Fill } = $props();

  const INSULATION = '#e9c98f';
  const FORMER = '#d9d6cc';

  function view(r: Results, fill: Fill) {
    const i = r.iView;
    const nt = r.turnOffsets[r.turnOffsets.length - 1];
    const nn = r.nodeOffsets[r.nodeOffsets.length - 1];
    const values = r.vnaCoils.map((c, k) => {
      if (fill === 'none') return null;
      return Array.from({ length: c.n_turns }, (_, t) => {
        if (fill === '|I|') return abs(at(r.driveTurnI, i * nt + r.turnOffsets[k] + t));
        const n = i * nn + r.nodeOffsets[k] + t;
        const [a, b] = [at(r.driveNodeV, n), at(r.driveNodeV, n + 1)];
        return Math.hypot((a.re + b.re) / 2, (a.im + b.im) / 2); // turn at its mean potential
      });
    });
    const all = values.flat().filter((v): v is number => v != null);
    const lo = Math.min(...all);
    const hi = Math.max(...all);
    const t = (v: number) => (hi > lo ? (v - lo) / (hi - lo) : 0.5);
    const strips = r.vnaCoils.map((c, k) => {
      const name = coilName(r.vnaPair, r.setupIndex, k);
      const z = Array.from({ length: c.n_turns }, (_, n) =>
        ((n - (c.n_turns - 1) / 2) * c.pitch + c.position[2]) * 1e3,
      );
      const [rr, rw, ro] = [c.mean_radius * 1e3, (c.wire_d / 2) * 1e3, (c.insulation_d / 2) * 1e3];
      const rf = (c.former_d / 2) * 1e3;
      const pad = 1.5 * c.pitch * 1e3;
      const offset = name === 'B' && r.vnaPair && r.params.offset_mm
        ? ` — lateral offset ${g(r.params.offset_mm, 6)} mm (projected on A's axis)`
        : '';
      return {
        c, name, z, rr, rw, ro, rf,
        color: COIL_COLORS[name === 'A' ? 0 : 1],
        x0: z[0] - pad,
        x1: z[z.length - 1] + pad,
        y0: rf - 3 * rw,
        y1: rr + 3 * rw,
        fills: values[k]?.map((v) => css(blues(t(v)))),
        values: values[k],
        title: `coil ${name}: ${c.n_turns} turns, wire Ø${g(c.wire_d * 1e3, 6)}/${g(c.insulation_d * 1e3, 6)} mm, pitch ${g(c.pitch * 1e3, 6)} mm, former Ø${g(c.former_d * 1e3, 6)} mm${offset}`,
      };
    });
    // the same axial span for every strip, so equal wires are drawn equally large
    const span = Math.max(...strips.map((s) => s.x1 - s.x0));
    for (const s of strips) [s.x0, s.x1] = [(s.x0 + s.x1 - span) / 2, (s.x0 + s.x1 + span) / 2];
    return { strips, lo, hi };
  }

  const v = $derived(view(r, fill));
  const unit = $derived(fill === '|I|' ? 'A' : 'V');
</script>

<h3 class="plot-title">
  Winding cross-section — {r.params.vna_setup}, {driveLabel(r)} at P1, {si(r.fView, 'Hz')}
</h3>
{#each v.strips as s (s.name)}
  <p class="strip-title">{s.title}</p>
  <Frame x0={s.x0} x1={s.x1} y0={s.y0} y1={s.y1} xLabel="position along coil A axis [mm]"
    yLabel="r [mm]" label="Cross-section of coil {s.name}'s winding" maxHeight={0.4}>
    {#if s.c.former}
      {@const half = (s.c.length / 2 + s.c.former.overhang) * 1e3}
      <rect class="former" x={s.c.position[2] * 1e3 - half} y={s.rf - s.c.former.wall * 1e3}
        width={2 * half} height={s.c.former.wall * 1e3} fill={FORMER} />
    {:else}
      <line class="no-former" x1={s.x0} x2={s.x1} y1={s.rf} y2={s.rf} />
    {/if}
    {#each s.z as zi, n (n)}
      {#if s.ro > s.rw}<circle cx={zi} cy={s.rr} r={s.ro} fill={INSULATION} />{/if}
      <circle class="wire" cx={zi} cy={s.rr} r={s.rw} stroke={s.color}
        style:fill={s.fills?.[n] ?? 'var(--bg)'}>
        {#if s.values}<title>turn {n + 1}: {fill} = {si(s.values[n], unit, 3)}</title>{/if}
      </circle>
    {/each}
  </Frame>
{/each}
<div class="legend">
  <Choice label="fill" tip="fill" bind:value={fill} options={FILLS} />
  {#if fill !== 'none'}
    <span>{si(v.lo, unit, 3)}</span>
    <span class="bar"></span>
    <span>{si(v.hi, unit, 3)}</span>
    <span class="muted">peak, per turn</span>
  {/if}
</div>

<style>
  .strip-title {
    margin: 10px 0 2px;
    font-size: 0.9rem;
  }
  .former {
    stroke: var(--muted);
    stroke-width: 0.8px;
    vector-effect: non-scaling-stroke;
  }
  .no-former {
    stroke: var(--muted);
    stroke-dasharray: 2 3;
    vector-effect: non-scaling-stroke;
  }
  .wire {
    stroke-width: 1.2px;
    vector-effect: non-scaling-stroke;
  }
  .legend {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    margin-top: 8px;
    font-size: 0.85rem;
  }
  .legend :global(.row) {
    grid-template-columns: auto 5em;
    margin-right: 8px;
  }
  .bar {
    width: 140px;
    height: 12px;
    background: linear-gradient(to right, #f7fbff, #c6dbef, #6baed6, #2171b5, #08306b);
    border: 1px solid var(--grid);
  }
</style>
