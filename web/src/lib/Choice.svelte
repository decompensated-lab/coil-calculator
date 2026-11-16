<!-- Labelled select over a fixed list of option values (the value is also the label): one
     row of a `.props` grid. -->
<script lang="ts" generics="T extends string">
  import { TIPS } from './help';

  let {
    label,
    tip,
    value = $bindable(),
    options,
    text = (o: T) => o,
    onchange,
  }: {
    label: string;
    tip: string;
    value: T;
    options: readonly T[];
    text?: (o: T) => string;
    onchange?: () => void;
  } = $props();
</script>

<label title={TIPS[tip]}>
  <span>{label}</span>
  <select bind:value {onchange}>
    {#each options as o (o)}
      <option value={o}>{text(o)}</option>
    {/each}
  </select>
</label>
