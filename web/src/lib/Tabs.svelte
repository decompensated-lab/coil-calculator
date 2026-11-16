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

  // keep the selected tab visible when the row scrolls (also covers selection by script);
  // not on mount: several tab rows share a page, and it must not jump to the last one
  let mounted = false;
  $effect(() => {
    const el = document.getElementById(id(selected));
    const options = { block: 'nearest', inline: 'nearest', container: 'nearest' };
    if (mounted) el?.scrollIntoView(options as ScrollIntoViewOptions);
    mounted = true;
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
<div class="tabpanel" role="tabpanel" aria-labelledby={id(selected)} tabindex="0">
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
    flex: none;
    padding: 6px 8px 0;
    background: var(--bg);
    border-bottom: 1px solid var(--line);
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
  /* a tab is a key; the open one is inverted and capped with the lit bar */
  [role='tab'] {
    flex: none;
    margin-right: -1px; /* adjacent tabs share a rule */
    padding-top: 3px; /* room for the cap, so the bar never crowds the label */
    border-bottom: 0; /* the rule of the row closes them */
  }
  /* selection follows focus, so the focused tab is the inverted one */
  [role='tab']:focus-visible {
    outline-offset: -4px;
    outline-color: #fff;
  }
  [aria-selected='true'],
  [aria-selected='true']:hover {
    font-weight: 700;
    color: #fff;
    background: var(--fg);
    box-shadow: inset 0 3px var(--on);
  }
  /* the well the selected plot lies in: it gives the plot all its height */
  .tabpanel {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-height: 0;
    padding: 6px 8px;
    overflow: auto;
  }
  .tabpanel:focus-visible {
    outline-offset: -2px;
  }
</style>
