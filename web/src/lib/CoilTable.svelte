<!-- Both coils side by side: one row per parameter, one column per coil (gui/window.py
     CoilBox, twice). Former details and the dielectric numbers are folded away; picking the
     "custom" material opens them. -->
<script lang="ts">
  import { TIPS } from './help';
  import { type CoilParams, type Grounding, MATERIALS, type Material, type Params } from './protocol';

  let { params = $bindable() }: { params: Params } = $props();

  const KEYS = ['a', 'b'] as const;
  type Key = (typeof KEYS)[number];
  type Field = 'wire_d_mm' | 'insulation_d_mm' | 'pitch_mm' | 'former_d_mm' | 'turns'
    | 'former_wall_mm' | 'former_overhang_mm';
  type Part = 'insulation' | 'former';

  const grounds: Grounding[] = ['end', 'start', 'floating'];
  const groundText = (g: Grounding) => (g === 'floating' ? 'floating' : `${g} grounded`);
  const materials = Object.keys(MATERIALS) as Material[];
  const off = (k: Key) => k === 'b' && !params.b_enabled;
  const name = (label: string, k: Key) => `${label}, coil ${k.toUpperCase()}`;
  let details = $state(false);

  // changing the wire Ø keeps the insulation thickness
  const prevWire = $state.snapshot({ a: params.a.wire_d_mm, b: params.b.wire_d_mm });
  function keepInsulation(k: Key) {
    const c = params[k];
    if (typeof c.wire_d_mm !== 'number') return;
    const t = Math.max((c.insulation_d_mm ?? 0) - prevWire[k], 0);
    c.insulation_d_mm = Number((c.wire_d_mm + t).toFixed(9));
    prevWire[k] = c.wire_d_mm;
  }

  /** A preset fills εr and tan δ; editing them turns the preset into "custom". */
  function preset(c: CoilParams, part: Part) {
    const d = MATERIALS[c[`${part}_material`]];
    if (d) c[part] = { ...d };
    else details = true;
  }
  function manual(c: CoilParams, part: Part) {
    const d = MATERIALS[c[`${part}_material`]];
    if (d && (d.eps_r !== c[part].eps_r || d.tan_delta !== c[part].tan_delta)) {
      c[`${part}_material`] = 'custom';
    }
  }
</script>

{#snippet num(label: string, tip: string, field: Field, unit: string, step: number, min: number, max?: number)}
  <div class="line" role="group" aria-label={label}>
    <span class="name" title={TIPS[tip]}>{label}</span>
    {#each KEYS as k (k)}
      <input type="number" placeholder=" " aria-label={name(label, k)} disabled={off(k)} {step}
        min={field === 'insulation_d_mm' ? params[k].wire_d_mm : min} {max}
        bind:value={params[k][field]}
        oninput={field === 'wire_d_mm' ? () => keepInsulation(k) : undefined} />
    {/each}
    <span class="unit">{unit}</span>
  </div>
{/snippet}

{#snippet dielectric(label: string, tip: string, part: Part, field: 'eps_r' | 'tan_delta', step: number, min: number)}
  <div class="line" role="group" aria-label={label}>
    <span class="name" title={TIPS[tip]}>{label}</span>
    {#each KEYS as k (k)}
      <input type="number" placeholder=" " aria-label={name(label, k)} disabled={off(k)} {step}
        {min} bind:value={params[k][part][field]} oninput={() => manual(params[k], part)} />
    {/each}
    <span class="unit"></span>
  </div>
{/snippet}

{#snippet material(label: string, tip: string, part: Part)}
  <div class="line wide" role="group" aria-label={label}>
    <span class="name" title={TIPS[tip]}>{label}</span>
    {#each KEYS as k (k)}
      <select aria-label={name(label, k)} disabled={off(k)}
        bind:value={params[k][`${part}_material`]} onchange={() => preset(params[k], part)}>
        {#each materials as m (m)}<option>{m}</option>{/each}
      </select>
    {/each}
  </div>
{/snippet}

<fieldset>
  <legend>Coils</legend>
  <div class="line head">
    <span></span>
    <span>A <small>driven</small></span>
    <label title="Untick to model coil A alone.">
      <input type="checkbox" bind:checked={params.b_enabled} /> B <small>pickup</small>
    </label>
    <span></span>
  </div>
  {@render num('wire Ø', 'wire', 'wire_d_mm', 'mm', 0.05, 0.01)}
  {@render num('insulated Ø', 'ins_d', 'insulation_d_mm', 'mm', 0.01, 0.01)}
  {@render num('pitch', 'pitch', 'pitch_mm', 'mm', 0.1, 0.01)}
  {@render num('former Ø', 'former', 'former_d_mm', 'mm', 1, 1)}
  {@render num('turns', 'turns', 'turns', '', 1, 1, 500)}
  <div class="line wide" role="group" aria-label="terminals">
    <span class="name" title={TIPS.ground}>terminals</span>
    {#each KEYS as k (k)}
      <select aria-label={name('terminals', k)} disabled={off(k)} bind:value={params[k].ground}>
        {#each grounds as g (g)}<option value={g}>{groundText(g)}</option>{/each}
      </select>
    {/each}
  </div>
  {@render material('insulation', 'ins_mat', 'insulation')}
  {@render material('former', 'former_mat', 'former')}
  <details bind:open={details}>
    <summary>Former size, εr and tan δ</summary>
    {@render num('former wall', 'former_wall', 'former_wall_mm', 'mm', 0.5, 0.01)}
    {@render num('overhang', 'former_overhang', 'former_overhang_mm', 'mm', 1, 0)}
    {@render dielectric('insulation εr', 'ins_eps', 'insulation', 'eps_r', 0.1, 1)}
    {@render dielectric('insul. tan δ', 'ins_tand', 'insulation', 'tan_delta', 0.001, 0)}
    {@render dielectric('former εr', 'former_eps', 'former', 'eps_r', 0.1, 1)}
    {@render dielectric('former tan δ', 'former_tand', 'former', 'tan_delta', 0.001, 0)}
  </details>
</fieldset>

<style>
  .line {
    display: grid;
    grid-template-columns: 6.5em minmax(0, 1fr) minmax(0, 1fr) 1.8em;
    align-items: center;
    gap: 6px;
    margin: 3px 0;
  }
  /* selects need the width: the label gets its own line */
  .wide {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }
  .wide .name {
    grid-column: 1 / -1;
    margin-bottom: -4px;
  }
  .name,
  .unit {
    color: var(--muted);
  }
  .name {
    cursor: help;
  }
  .head {
    font-weight: 600;
  }
  small {
    font-weight: 400;
    color: var(--muted);
  }
  :disabled {
    opacity: 0.5;
  }
  details {
    margin-top: 6px;
  }
  summary {
    color: var(--muted);
    cursor: pointer;
  }
</style>
