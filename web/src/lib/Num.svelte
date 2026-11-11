<!-- Labelled number input. An empty field binds null; the model rejects it as "not a number". -->
<script lang="ts">
  import { TIPS } from './help';

  let {
    label,
    tip,
    value = $bindable(),
    unit = '',
    step = 'any',
    min,
    max,
    oninput,
  }: {
    label: string;
    tip: string;
    value: number;
    unit?: string;
    step?: number | 'any';
    min?: number;
    max?: number;
    oninput?: () => void;
  } = $props();
</script>

<label class="row" title={TIPS[tip]}>
  <span class="name">{label}</span>
  <span class="field">
    <input type="number" placeholder=" " bind:value {step} {min} {max} {oninput} />
    {#if unit}<span class="unit">{unit}</span>{/if}
  </span>
</label>
