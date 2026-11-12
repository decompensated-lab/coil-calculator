<!-- A dashboard panel. Its heading folds it away (a button inside the heading, so screen
     readers keep the heading), and "Expand" gives it the whole results area. A folded or
     expanded panel takes a full row of the card grid. -->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { ClassValue } from 'svelte/elements';

  let {
    title,
    hint = '',
    max,
    onmax,
    class: extra,
    children,
  }: {
    title: string;
    /** Short usage note beside the title. */
    hint?: string;
    /** This panel is the expanded one. */
    max: boolean;
    /** Expand this panel, or restore the grid if it is expanded. */
    onmax: () => void;
    class?: ClassValue;
    children: Snippet;
  } = $props();

  let open = $state(true);
  function fold() {
    open = !open;
    if (!open && max) onmax();
  }
</script>

<section class={['card', extra, { max, folded: !open }]}>
  <header>
    <h2><button type="button" aria-expanded={open} onclick={fold}>{title}</button></h2>
    {#if open}
      <span class="hint">{hint}</span>
      <button type="button" class="size" onclick={onmax}>{max ? 'Restore' : 'Expand'}</button>
    {/if}
  </header>
  {#if open}{@render children()}{/if}
</section>

<style>
  .card {
    min-width: 0;
    padding: 8px 12px 12px;
    border: 1px solid var(--grid);
    border-radius: 8px;
  }
  .folded {
    padding-bottom: 8px;
  }
  .folded,
  .max {
    grid-column: 1 / -1;
  }
  header {
    display: flex;
    align-items: baseline;
    gap: 0.8em;
  }
  h2 {
    margin: 0;
    font-size: 0.75rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }
  button {
    padding: 0;
    font: inherit;
    letter-spacing: inherit;
    text-transform: inherit;
    color: var(--muted);
    background: none;
    border: 0;
    cursor: pointer;
  }
  button:hover {
    color: var(--ink);
  }
  /* the fold marker, next to the label it belongs to */
  h2 button::before {
    content: '▸';
    display: inline-block;
    width: 1.2em;
    rotate: 0deg;
  }
  h2 button[aria-expanded='true']::before {
    rotate: 90deg;
  }
  .hint {
    flex: 1;
    font-size: 0.75rem;
    color: var(--muted);
  }
  .size {
    font-size: 0.75rem;
    text-decoration: underline dotted;
  }
</style>
