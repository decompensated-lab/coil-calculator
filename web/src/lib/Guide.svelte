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

<button type="button" aria-keyshortcuts="F1" onclick={() => dialog.showModal()}>
  Guide <kbd>F1</kbd>
</button>
<a class="key" href={REPO} target="_blank" rel="noopener">Source</a>

<dialog bind:this={dialog} aria-labelledby="guide-title" {...{ closedby: 'any' }}>
  <!-- the title bar; its key is first, so focusing it does not scroll the guide to its end -->
  <form method="dialog">
    <span class="bar">Guide</span>
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
  kbd {
    font: inherit;
    color: var(--dim);
  }
  /* a window of its own: ink bar, the text on paper, a closing rule */
  dialog {
    width: min(84ch, calc(100vw - 32px));
    max-height: 88vh;
    padding: 0;
    color: var(--fg);
    background: var(--bg);
    border: 2px solid var(--line);
  }
  dialog[open] {
    display: flex;
    flex-direction: column;
  }
  /* both rules: without them, scrolling in the dialog or over the backdrop scrolls the page */
  dialog:modal {
    overscroll-behavior: contain;
  }
  dialog::backdrop {
    overflow: hidden;
    overscroll-behavior: contain;
    background: rgb(198 203 209 / 0.82);
  }
  form {
    display: flex;
    flex: none;
    align-items: stretch;
    justify-content: space-between;
    color: #fff;
    background: var(--fg);
  }
  .bar {
    padding: 3px 10px;
    font-weight: 700;
    letter-spacing: 0.04em;
  }
  form button {
    height: auto;
    color: var(--fg);
    border-width: 0 0 0 1px;
  }
  form button:focus-visible {
    outline-color: #fff;
    outline-offset: -4px;
  }
  /* running text: more leading than the interface, and a measure a line can be read in */
  .guide {
    padding: 4px 16px 12px;
    overflow-y: auto;
    overscroll-behavior: contain;
    line-height: 20px;
  }
  .guide :global(:is(h2, h3)) {
    margin: 14px 0 4px;
    font-weight: 700;
  }
  .guide :global(h2) {
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }
  .guide :global(h3) {
    padding-bottom: 2px;
    letter-spacing: 0.04em;
    border-bottom: 1px solid var(--line-2);
  }
  .guide :global(p) {
    margin: 0 0 8px;
  }
  .guide :global(ul) {
    margin: 0 0 8px;
    padding-left: 3ch;
  }
  .build {
    flex: none;
    padding: 4px 16px;
    color: var(--dim);
    border-top: 1px solid var(--line);
  }
</style>
