<!-- One coil's geometry, terminals, insulation and former (gui/window.py CoilBox). -->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import Choice from './Choice.svelte';
  import DielectricEdit from './DielectricEdit.svelte';
  import Num from './Num.svelte';
  import type { CoilParams, Grounding } from './protocol';

  let { coil = $bindable(), extra }: { coil: CoilParams; extra?: Snippet } = $props();

  const groundText = (g: Grounding) => (g === 'floating' ? 'floating' : `${g} grounded`);
  const grounds: Grounding[] = ['end', 'start', 'floating'];

  // changing the wire Ø keeps the insulation thickness
  let prevWire = $state.snapshot(coil.wire_d_mm);
  function keepInsulation() {
    if (typeof coil.wire_d_mm !== 'number') return;
    const t = Math.max((coil.insulation_d_mm ?? 0) - prevWire, 0);
    coil.insulation_d_mm = Number((coil.wire_d_mm + t).toFixed(9));
    prevWire = coil.wire_d_mm;
  }
</script>

<Num label="wire Ø" tip="wire" bind:value={coil.wire_d_mm} unit="mm" step={0.05} min={0.01}
  oninput={keepInsulation} />
<Num label="insulated Ø" tip="ins_d" bind:value={coil.insulation_d_mm} unit="mm" step={0.01}
  min={coil.wire_d_mm} />
<Num label="pitch" tip="pitch" bind:value={coil.pitch_mm} unit="mm" step={0.1} min={0.01} />
<Num label="former Ø" tip="former" bind:value={coil.former_d_mm} unit="mm" step={1} min={1} />
<Num label="turns" tip="turns" bind:value={coil.turns} step={1} min={1} max={500} />
<Choice label="terminals" tip="ground" bind:value={coil.ground} options={grounds}
  text={groundText} />
<DielectricEdit label="insulation" tips={['ins_mat', 'ins_eps', 'ins_tand']}
  bind:material={coil.insulation_material} bind:value={coil.insulation} />
<Num label="former wall" tip="former_wall" bind:value={coil.former_wall_mm} unit="mm" step={0.5}
  min={0.01} />
<Num label="overhang" tip="former_overhang" bind:value={coil.former_overhang_mm} unit="mm"
  step={1} min={0} />
<DielectricEdit label="former" tips={['former_mat', 'former_eps', 'former_tand']}
  bind:material={coil.former_material} bind:value={coil.former} />
{@render extra?.()}
