<!-- Material preset plus editable εr and tan δ; editing them switches the preset to "custom". -->
<script lang="ts">
  import Choice from './Choice.svelte';
  import Num from './Num.svelte';
  import { type Dielectric, MATERIALS, type Material } from './protocol';

  let {
    label,
    tips,
    material = $bindable(),
    value = $bindable(),
    onpreset,
  }: {
    label: string;
    tips: [string, string, string];
    material: Material;
    value: Dielectric;
    /** Called after a preset was picked. */
    onpreset?: () => void;
  } = $props();

  const names = Object.keys(MATERIALS) as Material[];

  function preset() {
    const d = MATERIALS[material];
    if (d) value = { ...d };
    onpreset?.();
  }

  function manual() {
    const d = MATERIALS[material];
    if (d && (d.eps_r !== value.eps_r || d.tan_delta !== value.tan_delta)) material = 'custom';
  }
</script>

<Choice {label} tip={tips[0]} bind:value={material} options={names} onchange={preset} />
<div class="pair">
  <Num label="εr" tip={tips[1]} bind:value={value.eps_r} step={0.1} min={1} oninput={manual} />
  <Num label="tan δ" tip={tips[2]} bind:value={value.tan_delta} step={0.001} min={0}
    oninput={manual} />
</div>
