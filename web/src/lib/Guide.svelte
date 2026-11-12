<!-- The model and usage guide (gui/help.py GUIDE_HTML) in a modal dialog; F1 opens it. -->
<script lang="ts">
  import { GUIDE_HTML } from './help';

  let dialog: HTMLDialogElement;

  function keydown(e: KeyboardEvent) {
    if (e.key === 'F1' && !dialog.open) {
      e.preventDefault();
      dialog.showModal();
    }
  }
</script>

<svelte:window onkeydown={keydown} />

<button type="button" class="open" aria-keyshortcuts="F1" onclick={() => dialog.showModal()}>
  Guide <kbd>F1</kbd>
</button>

<dialog bind:this={dialog} aria-labelledby="guide-title" {...{ closedby: 'any' }}>
  <!-- first, so focusing it does not scroll the guide to its end -->
  <form method="dialog">
    <!-- svelte-ignore a11y_autofocus (initial focus inside a modal dialog is intended) -->
    <button autofocus>Close</button>
  </form>
  <!-- trusted, static HTML from gui/help.py -->
  <div class="guide">{@html GUIDE_HTML}</div>
</dialog>

<style>
  .open {
    padding: 2px 8px;
    font: inherit;
    font-size: 0.85rem;
    color: inherit;
    background: var(--input);
    border: 1px solid var(--grid);
    border-radius: 4px;
    cursor: pointer;
  }
  kbd {
    font: inherit;
    color: var(--muted);
  }
  dialog {
    width: min(720px, calc(100vw - 32px));
    max-height: 85vh;
    padding: 16px 20px;
    color: var(--ink);
    background: var(--bg);
    border: 1px solid var(--grid);
    border-radius: 8px;
  }
  /* both rules: without them, scrolling in the dialog or over the backdrop scrolls the page */
  dialog:modal {
    overscroll-behavior: contain;
  }
  dialog::backdrop {
    overflow: hidden;
    overscroll-behavior: contain;
    background: rgb(0 0 0 / 0.35);
  }
  .guide :global(h2) {
    margin-top: 0;
  }
  form {
    float: right;
    margin-left: 12px;
  }
  form button {
    padding: 4px 14px;
    font: inherit;
    color: inherit;
    background: var(--input);
    border: 1px solid var(--grid);
    border-radius: 4px;
    cursor: pointer;
  }
</style>
