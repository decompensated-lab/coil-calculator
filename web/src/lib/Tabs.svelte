<!-- Tab bar and one panel for the selected tab (only that panel is rendered, like the Qt app
     draws only the visible tab). Selection follows focus. -->
<script lang="ts">
  import type { Snippet } from 'svelte';

  let {
    tabs,
    selected = $bindable(),
    label,
    tips = {},
    panel,
  }: {
    tabs: readonly string[];
    selected: string;
    label: string;
    tips?: Record<string, string>;
    panel: Snippet;
  } = $props();

  const uid = $props.id();
  const id = (t: string) => `${uid}-${tabs.indexOf(t)}`;
  // focusgroup gives the tablist its roles and arrow-key focus (Chrome 150+); elsewhere a
  // roving tabindex and the key handler below do the same
  const native = Object.hasOwn(HTMLElement.prototype, 'focusGroup');

  function keydown(e: KeyboardEvent) {
    if (native) return;
    const i = tabs.indexOf(selected);
    const next = ({ ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 } as Record<string, number>)[e.key];
    if (next === undefined) return;
    e.preventDefault();
    document.getElementById(id(tabs[(next + tabs.length) % tabs.length]))?.focus();
  }

  // keep the selected tab visible when the row scrolls (also covers selection by script)
  $effect(() => {
    const options = { block: 'nearest', inline: 'nearest', container: 'nearest' };
    document.getElementById(id(selected))?.scrollIntoView(options as ScrollIntoViewOptions);
  });

  // edge fades without scroll-driven animations: mark the ends that have more tabs beyond
  function fades(list: HTMLElement) {
    if (CSS.supports('animation-timeline', 'scroll()')) return;
    const [first, last] = [list.firstElementChild!, list.lastElementChild!];
    const io = new IntersectionObserver(
      (entries) => {
        for (const { target, intersectionRatio } of entries) {
          list.classList.toggle(target === first ? 'more-start' : 'more-end', intersectionRatio < 1);
        }
      },
      { root: list, threshold: 1, rootMargin: '1px' },
    );
    io.observe(first);
    io.observe(last);
    return () => io.disconnect();
  }
</script>

<div class="tablist" role="tablist" aria-label={label} onkeydown={keydown} {@attach fades}
  {...{ focusgroup: 'tablist nomemory' }}>
  {#each tabs as t (t)}
    <button type="button" role="tab" id={id(t)} aria-selected={t === selected}
      tabindex={native ? undefined : t === selected ? 0 : -1} title={tips[t]}
      onclick={() => (selected = t)} onfocus={() => (selected = t)}
      {...{ focusgroupstart: t === selected ? '' : undefined }}>
      {t}
    </button>
  {/each}
</div>
<div class="panel" role="tabpanel" aria-labelledby={id(selected)} tabindex="0">
  {@render panel()}
</div>

<style>
  @property --fade-start {
    syntax: '<length>';
    inherits: false;
    initial-value: 0px;
  }
  @property --fade-end {
    syntax: '<length>';
    inherits: false;
    initial-value: 0px;
  }
  .tablist {
    display: flex;
    overflow-x: auto;
    scrollbar-width: none;
    border-bottom: 1px solid var(--grid);
    margin-bottom: 10px;
    --fade-size: 3rem;
    scroll-padding-inline: var(--fade-size);
    mask-image: linear-gradient(to right, transparent, black var(--fade-start),
      black calc(100% - var(--fade-end)), transparent);
    animation: reveal-fade-start linear both, hide-fade-end linear both;
    animation-timeline: scroll(self inline);
    animation-range: 0 var(--fade-size), calc(100% - var(--fade-size)) 100%;
    transition: --fade-start 0.2s, --fade-end 0.2s;
  }
  .tablist:global(.more-start) {
    --fade-start: var(--fade-size);
  }
  .tablist:global(.more-end) {
    --fade-end: var(--fade-size);
  }
  @keyframes reveal-fade-start {
    to {
      --fade-start: var(--fade-size);
    }
  }
  @keyframes hide-fade-end {
    from {
      --fade-end: var(--fade-size);
    }
  }
  [role='tab'] {
    position: relative;
    flex: none;
    padding: 6px 12px;
    font: inherit;
    color: var(--muted);
    background: none;
    border: 0;
    cursor: pointer;
  }
  [role='tab']:hover {
    color: var(--ink);
  }
  /* selected: colour plus an underline (a border, which forced-colours mode keeps) */
  [aria-selected='true'] {
    color: var(--accent);
  }
  [aria-selected='true']::after {
    content: '';
    position: absolute;
    inset: auto 0 0;
    border-block-end: 3px solid var(--accent);
  }
  .panel:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
</style>
