<!-- Labelled number input: one row of a `.props` grid (name, field, unit). An empty field
     binds null; the model rejects it as "not a number". -->
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
    disabled = false,
    oninput,
  }: {
    label: string;
    tip: string;
    value: number;
    unit?: string;
    step?: number | 'any';
    min?: number;
    max?: number;
    disabled?: boolean;
    oninput?: () => void;
  } = $props();
</script>

<label title={TIPS[tip]}>
  <span>{label}</span>
  <input type="number" placeholder=" " bind:value {step} {min} {max} {disabled} {oninput} />
  {#if unit}<span>{unit}</span>{/if}
</label>
