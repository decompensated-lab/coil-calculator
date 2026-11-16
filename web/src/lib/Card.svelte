<!-- A dashboard panel, named by a solid bar. Its heading folds it away (a button inside the
     heading, so screen readers keep the heading), and the key at the end of the bar gives it
     the whole results area. The body is the white well the data lies in; it scrolls when the
     panel is too small for it. -->
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

<section class={['panel', 'card', extra, { max, folded: !open }]}>
  <header class="panel-head">
    <h2><button type="button" aria-expanded={open} onclick={fold}>{title}</button></h2>
    {#if open}
      <span class="hint">{hint}</span>
      <button type="button" class="size" onclick={onmax}>{max ? 'Restore' : 'Expand'}</button>
    {/if}
  </header>
  {#if open}<div class="body">{@render children()}</div>{/if}
</section>

<style>
  .card {
    display: grid;
    grid-template-columns: minmax(0, 1fr); /* a long hint must not widen the panel */
    grid-template-rows: auto minmax(0, 1fr);
  }
  .folded .panel-head {
    border-bottom: 0;
  }
  .body {
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow: auto;
    background: var(--well);
  }
  .hint {
    flex: 1;
    min-width: 0;
    padding: 2px 8px;
    overflow: hidden;
    font-size: 11px;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: #d5dae0;
  }
  /* the last cell of the bar, like the box in the corner of a window */
  .size {
    height: auto;
    font-size: 11px;
    color: var(--fg);
    border-width: 0 0 0 1px;
  }
</style>
