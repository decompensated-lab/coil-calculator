<!-- The model and usage guide (gui/help.py GUIDE_HTML) in a modal dialog; F1 opens it.
     Next to its button: the link to the source. The dialog ends with the build's commit
     and the licences that are published with the site. -->
<script lang="ts">
  import { GUIDE_HTML } from './help';

  const REPO = 'https://github.com/ivan-galinskiy/coil-calculator';
  // the deploy workflow sets VITE_COMMIT to the commit it builds
  const commit: string | undefined = import.meta.env.VITE_COMMIT;

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
<a class="open" href={REPO} target="_blank" rel="noopener">Source</a>

<dialog bind:this={dialog} aria-labelledby="guide-title" {...{ closedby: 'any' }}>
  <!-- first, so focusing it does not scroll the guide to its end -->
  <form method="dialog">
    <!-- svelte-ignore a11y_autofocus (initial focus inside a modal dialog is intended) -->
    <button autofocus>Close</button>
  </form>
  <!-- trusted, static HTML from gui/help.py -->
  <div class="guide">{@html GUIDE_HTML}</div>
  <p class="build">
    {#if commit}
      Build <a href="{REPO}/commit/{commit}" target="_blank" rel="noopener">{commit.slice(0, 7)}</a> ·
    {/if}
    <a href="./LICENSE.txt" target="_blank">MIT licence</a>
    · <a href="./THIRD_PARTY_NOTICES.txt" target="_blank">third-party notices</a>
  </p>
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
    text-decoration: none;
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
  .guide :global(a),
  .build a {
    color: var(--accent);
  }
  .build {
    margin: 16px 0 0;
    padding-top: 8px;
    border-top: 1px solid var(--grid);
    color: var(--muted);
    font-size: 0.85rem;
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
