<!-- Inputs of the wire-pair calculator (gui/pairtab.py WireBox and spacing box). -->
<script lang="ts">
  import Choice from './Choice.svelte';
  import DielectricEdit from './DielectricEdit.svelte';
  import { TIPS } from './help';
  import Num from './Num.svelte';
  import { type CoilParams, type PairParams, SPACING_REFS, type WireParams } from './protocol';

  let { pair = $bindable(), coilA }: { pair: PairParams; coilA: CoilParams } = $props();

  const round = (v: number) => Number(v.toFixed(9));

  // changing the reference converts the number, so the geometry stays the same
  let lastRef = $state.snapshot(pair.spacing_ref);
  function refChanged() {
    if (pair.spacing_ref === lastRef) return;
    const w2 = pair.same ? pair.w1 : pair.w2;
    const outer = (pair.w1.insulation_d_mm + w2.insulation_d_mm) / 2;
    const v = pair.spacing_mm + (pair.spacing_ref === 'centre-to-centre' ? outer : -outer);
    pair.spacing_mm = Math.max(round(v), 0);
    lastRef = pair.spacing_ref;
  }

  /** Coil A's wire Ø on both conductors (insulation thickness kept), its pitch as spacing. */
  function fromCoilA() {
    for (const w of [pair.w1, pair.w2]) {
      const t = Math.max(w.insulation_d_mm - w.conductor_d_mm, 0);
      w.conductor_d_mm = coilA.wire_d_mm;
      w.insulation_d_mm = round(coilA.wire_d_mm + t);
    }
    pair.spacing_ref = lastRef = 'centre-to-centre';
    pair.spacing_mm = coilA.pitch_mm;
  }

  function bare(w: WireParams) {
    if (w.material === 'air / none') w.insulation_d_mm = w.conductor_d_mm;
  }
</script>

{#snippet wire(w: WireParams)}
  <Num label="conductor Ø" tip="pair_cond" bind:value={w.conductor_d_mm} unit="mm" step={0.05}
    min={0.001} />
  <Num label="insulation Ø" tip="pair_ins" bind:value={w.insulation_d_mm} unit="mm" step={0.05}
    min={w.conductor_d_mm} />
  <DielectricEdit label="insulation" tips={['pair_material', 'pair_eps', 'pair_tand']}
    bind:material={w.material} bind:value={w.insulation} onpreset={() => bare(w)} />
{/snippet}

<fieldset>
  <legend>Wire 1</legend>
  {@render wire(pair.w1)}
</fieldset>
<fieldset disabled={pair.same}>
  <legend title={TIPS.pair_same}>
    <label>
      <input type="checkbox" checked={!pair.same} onchange={(e) => (pair.same = !e.currentTarget.checked)} />
      Wire 2 differs from wire 1
    </label>
  </legend>
  {@render wire(pair.w2)}
</fieldset>
<fieldset>
  <legend>Spacing</legend>
  <Choice label="reference" tip="pair_ref" bind:value={pair.spacing_ref} options={SPACING_REFS}
    onchange={refChanged} />
  <Num label="spacing" tip="pair_spacing" bind:value={pair.spacing_mm} unit="mm" step={0.05}
    min={0} />
  <button type="button" class="from-a" title={TIPS.pair_from_a} onclick={fromCoilA}>
    From coil A (wire Ø, pitch)
  </button>
</fieldset>

<style>
  .from-a {
    margin-top: 6px;
    width: 100%;
    padding: 4px 8px;
    font: inherit;
    color: inherit;
    background: var(--input);
    border: 1px solid var(--grid);
    border-radius: 4px;
    cursor: pointer;
  }
  .from-a:hover {
    border-color: var(--muted);
  }
</style>
