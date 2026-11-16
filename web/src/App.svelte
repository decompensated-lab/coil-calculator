<script lang="ts">
  import { MediaQuery } from 'svelte/reactivity';
  import BzProfiles from './lib/BzProfiles.svelte';
  import Card from './lib/Card.svelte';
  import Choice from './lib/Choice.svelte';
  import CoilTable from './lib/CoilTable.svelte';
  import { Computer } from './lib/compute.svelte';
  import CrossSection, { type Fill } from './lib/CrossSection.svelte';
  import Guide from './lib/Guide.svelte';
  import { TAB_TIPS } from './lib/help';
  import ImpedancePlot from './lib/ImpedancePlot.svelte';
  import KeyNumbers from './lib/KeyNumbers.svelte';
  import Num from './lib/Num.svelte';
  import PairForm from './lib/PairForm.svelte';
  import PairPlot from './lib/PairPlot.svelte';
  import PairSummary from './lib/PairSummary.svelte';
  import {
    COUPLINGS, DRIVES, GAP_REFS, VNA_SETUPS, defaultPair, defaultParams, flatten, flattenPair,
  } from './lib/protocol';
  import { pairView, si, view } from './lib/results';
  import SideView from './lib/SideView.svelte';
  import Summary from './lib/Summary.svelte';
  import Tabs from './lib/Tabs.svelte';
  import TransferPlot from './lib/TransferPlot.svelte';
  import TurnCurrents from './lib/TurnCurrents.svelte';
  import VnaPlot from './lib/VnaPlot.svelte';

  // The window: title bar, toolbar, the rail where things are set, the desk where they are
  // read, status bar. On the desk the panels share the height of the window, but none goes
  // below a usable height: the desk scrolls instead (and on a narrow screen the page does).
  // one card per kind of plot, so a picture, a sweep and a snapshot are visible together
  const GEOMETRY = ['Side view', 'Cross-section'] as const;
  const SWEEP = ['Impedance', 'Transfer A→B', 'VNA', 'Smith'] as const;
  const SNAPSHOT = ['Turn currents', 'Bz profiles'] as const;
  const TIPS = { ...TAB_TIPS, Smith: TAB_TIPS.VNA };
  let geometry: string = $state(GEOMETRY[0]);
  let sweep: string = $state(SWEEP[0]);
  let snapshot: string = $state(SNAPSHOT[0]);
  let fill: Fill = $state('|I|');
  /** Title of the expanded card, if any; the others are hidden meanwhile. */
  let maxed: string | null = $state(null);
  const size = (title: string) => ({
    max: maxed === title,
    onmax: () => (maxed = maxed === title ? null : title),
  });
  // the wire-pair calculator is stand-alone: it brings its own inputs and results
  let mode = $state<'coils' | 'pair'>('coils');

  let params = $state(defaultParams());
  let pair = $state(defaultPair());
  const computer = new Computer(flatten, view);
  const pairComputer = new Computer(flattenPair, pairView);
  const onPair = $derived(mode === 'pair');
  const active = $derived(onPair ? pairComputer : computer);

  // narrow screens: results first, the inputs fold away
  const wide = new MediaQuery('min-width: 760px');
  let setup = $state(false);
  const turns = $derived(computer.result?.coils.reduce((n, c) => n + c.n_turns, 0) ?? 0);

  /** A click in a sweep plot moves the view frequency there. */
  const onview = (mhz: number) => (params.f_view_mhz = Number(mhz.toPrecision(4)));

  // recompute shortly after the last edit (each worker keeps only the newest request)
  $effect(() => {
    const p = $state.snapshot(params);
    const t = setTimeout(() => computer.request(p), 120);
    return () => clearTimeout(t);
  });
  $effect(() => {
    const p = $state.snapshot(pair);
    const t = setTimeout(() => pairComputer.request(p), 120);
    return () => clearTimeout(t);
  });
</script>

<svelte:window
  onkeydown={(e) => {
    // Escape restores the grid (but leave it to an open dialog)
    if (e.key === 'Escape' && !document.querySelector('dialog[open]')) maxed = null;
  }}
/>

<div class="app">
  <header class="titlebar">
    <h1>coilcal <span>turn-level coil model</span></h1>
  </header>

  <div class="toolbar">
    <fieldset class="mode">
      <legend>Model</legend>
      <label class="key"><input type="radio" bind:group={mode} value="coils" />Coils</label>
      <label class="key" title={TAB_TIPS['Wire pair C']}>
        <input type="radio" bind:group={mode} value="pair" />Wire pair C
      </label>
    </fieldset>
    {#if !onPair}
      <span class="sep"></span>
      <div class="props one">
        <Num label="view frequency" tip="f_view" bind:value={params.f_view_mhz} unit="MHz"
          step={0.5} />
      </div>
    {/if}
    <span class="grow"></span>
    <Guide />
  </div>

  <aside class="rail">
    <section class="panel">
      <header class="panel-head">
        <h2>
          {#if wide.current}
            Setup
          {:else}
            <button type="button" aria-expanded={setup} onclick={() => (setup = !setup)}>
              Setup
            </button>
          {/if}
        </h2>
      </header>
      <div class="form" hidden={!wide.current && !setup}>
        {#if onPair}
          <PairForm bind:pair coilA={params.a} />
        {:else}
          <CoilTable bind:params />
          <fieldset disabled={!params.b_enabled}>
            <legend>Placement of B</legend>
            <div class="props">
              <Choice label="gap reference" tip="gap_ref" bind:value={params.gap_ref}
                options={GAP_REFS} />
              <Num label="axial gap" tip="gap" bind:value={params.gap_mm} unit="mm" step={1} />
              <Num label="lateral offset" tip="offset" bind:value={params.offset_mm} unit="mm"
                step={1} />
            </div>
          </fieldset>
          <fieldset>
            <legend>Measurement</legend>
            <div class="props">
              <Choice label="VNA setup" tip="vna_setup" bind:value={params.vna_setup}
                options={VNA_SETUPS} />
              <Num label="Z0" tip="z0" bind:value={params.z0} unit="Ω" step={1} min={1} />
              <Choice label="drive" tip="drive" bind:value={params.drive} options={DRIVES} />
              <Num label="source power" tip="p_dbm" bind:value={params.p_dbm} unit="dBm" step={1}
                disabled={params.drive !== 'source power'} />
              <Num label="P1 current" tip="i_drive" bind:value={params.i_drive_a} unit="A"
                step={0.1} min={0} disabled={params.drive === 'source power'} />
              <Num label="load on B" tip="z_load" bind:value={params.z_load} unit="Ω" step={10} />
            </div>
          </fieldset>
          <fieldset>
            <legend>Sweep and model</legend>
            <div class="props">
              <Num label="f min" tip="f_min" bind:value={params.f_min_mhz} unit="MHz" step={0.1} />
              <Num label="f max" tip="f_max" bind:value={params.f_max_mhz} unit="MHz" step={1} />
              <Num label="points" tip="n_freq" bind:value={params.n_freq} step={1} min={10}
                max={5000} />
              <Num label="R factor" tip="r_factor" bind:value={params.r_factor} step={0.1}
                min={0.1} />
              <Choice label="coil coupling" tip="coupling" bind:value={params.coupling}
                options={COUPLINGS} />
            </div>
          </fieldset>
        {/if}
      </div>
    </section>
  </aside>

  <main>
    {#if active.error}
      <p class="banner err" role="alert">{active.error}</p>
    {/if}
    {#if onPair}
      {#if pairComputer.result}
        {@const stale = pairComputer.error || pairComputer.busy}
        <div class="cards">
          <div class="col">
            <Card title="Field and capacitance" {...size('pair')}>
              <PairPlot r={pairComputer.result} />
            </Card>
            <Card title="Numbers" class={['summary', 'fit', { stale }]} {...size('pair numbers')}>
              <PairSummary r={pairComputer.result} />
            </Card>
          </div>
        </div>
      {/if}
    {:else if computer.result}
      {@const r = computer.result}
      {@const stale = computer.error || computer.busy}
      <section class={['panel', { stale }]}>
        <header class="panel-head"><h2>Key numbers</h2></header>
        <div class="keys">
          <KeyNumbers {r} />
          {#if r.warnings.length}
            <details class="warnings">
              <summary class="banner">
                {r.warnings.length} model {r.warnings.length > 1 ? 'warnings' : 'warning'}
              </summary>
              <ul>
                {#each r.warnings as w (w)}<li>{w}</li>{/each}
              </ul>
            </details>
          {/if}
        </div>
      </section>
      <div class="cards">
        <div class="col">
          <Card title="Geometry and field" {...size('geometry')}>
            <Tabs tabs={GEOMETRY} bind:selected={geometry} label="Geometry and field" tips={TIPS}>
              {#snippet panel()}
                {#if geometry === 'Side view'}
                  <SideView {r} oncut={(z) => (params.x_line_z_mm = z)} />
                {:else}
                  <CrossSection {r} bind:fill />
                {/if}
              {/snippet}
            </Tabs>
          </Card>
          <Card title="At {si(r.fView, 'Hz')}" {...size('snapshot')}>
            <Tabs tabs={SNAPSHOT} bind:selected={snapshot} label="At the view frequency"
              tips={TIPS}>
              {#snippet panel()}
                {#if snapshot === 'Turn currents'}
                  <TurnCurrents {r} />
                {:else}
                  <BzProfiles {r} bind:cutZ={params.x_line_z_mm} />
                {/if}
              {/snippet}
            </Tabs>
          </Card>
        </div>
        <div class="col">
          <Card title="Frequency sweep" hint="click a plot to set the view frequency"
            {...size('sweep')}>
            <Tabs tabs={SWEEP} bind:selected={sweep} label="Frequency sweep" tips={TIPS}>
              {#snippet panel()}
                {#if sweep === 'Impedance'}
                  <ImpedancePlot {r} {onview} />
                {:else if sweep === 'Transfer A→B'}
                  <TransferPlot {r} {onview} />
                {:else}
                  <VnaPlot {r} {onview} smith={sweep === 'Smith'} />
                {/if}
              {/snippet}
            </Tabs>
          </Card>
          <Card title="Numbers at {si(r.fView, 'Hz')}" class={['summary', { stale }]}
            {...size('numbers')}>
            <Summary {r} />
          </Card>
        </div>
      </div>
    {:else if !computer.error}
      <p class="muted">Loading the model…</p>
    {/if}
  </main>

  <footer class="statusbar">
    <span class={['status', { error: active.error }]} aria-live="polite">
      {#if active.error}
        <i class="led err"></i>input error
      {:else if active.busy}
        <i class="led off"></i>computing…
      {:else if active.result}
        <i class="led"></i>model ready
      {/if}
    </span>
    {#if !onPair && computer.result?.warnings.length}
      {@const n = computer.result.warnings.length}
      <span><i class="led warn"></i>{n} {n > 1 ? 'warnings' : 'warning'}</span>
    {/if}
    {#if active.result}<span>{active.ms.toFixed(0)} ms</span>{/if}
    <span class="grow"></span>
    {#if onPair}
      {#if pairComputer.result}<span>{pairComputer.result.nTerms} multipole terms per wire</span>{/if}
    {:else if computer.result}
      {@const n = computer.result.coils.length}
      <span>{n} {n > 1 ? 'coils' : 'coil'}, {turns} turns</span>
    {/if}
  </footer>
</div>

<style>
  .app {
    display: grid;
    grid-template-columns: 384px minmax(0, 1fr);
    grid-template-rows: auto auto minmax(0, 1fr) auto;
    grid-template-areas:
      'title  title'
      'tools  tools'
      'rail   desk'
      'status status';
    height: 100dvh;
  }
  .titlebar {
    grid-area: title;
    padding: 3px 10px;
    color: #fff;
    background: var(--fg);
  }
  h1 {
    margin: 0;
    font: inherit;
    font-weight: 700;
    letter-spacing: 0.04em;
  }
  h1 span {
    margin-left: 1ch;
    font-weight: 400;
    color: #c6cbd1;
  }
  .toolbar {
    grid-area: tools;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    padding: 6px 8px;
    border-bottom: 1px solid var(--line);
  }
  .sep {
    align-self: stretch;
    width: 1px;
    margin: -6px 4px;
    background: var(--line);
  }
  .grow {
    flex: 1;
  }
  /* the two models as lamp keys: native radios, each drawn as a key with a lamp at its foot,
     unlit or lit, so what is on is marked twice */
  .mode {
    display: flex;
    margin: 0;
    padding: 0;
    border: 0;
  }
  .mode legend {
    position: absolute;
    clip-path: inset(50%);
  }
  .mode label {
    padding-bottom: 4px;
    box-shadow:
      inset 0 -3px var(--off),
      inset 0 -4px var(--line);
  }
  .mode label + label {
    margin-left: -1px; /* adjacent cells share a rule */
  }
  .mode label:has(:checked) {
    box-shadow:
      inset 0 -3px var(--on),
      inset 0 -4px var(--line);
  }
  .mode input {
    position: absolute;
    opacity: 0;
    pointer-events: none;
  }
  .mode label:has(:focus-visible) {
    z-index: 1;
    outline: 2px solid var(--fg);
    outline-offset: 1px;
  }

  /* Zones: the rail and the desk meet at a rule, and panels are sheets lying on them */
  .rail {
    grid-area: rail;
    display: grid;
    grid-template-rows: minmax(0, 1fr);
    min-height: 0;
    padding: 8px;
    background: var(--rail);
    border-right: 1px solid var(--line);
  }
  .rail .panel {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto minmax(0, 1fr);
    min-height: 0;
  }
  .rail .panel-head {
    background: var(--head);
  }
  .form {
    padding: 0 8px 8px;
    overflow-y: auto;
  }
  main {
    grid-area: desk;
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-width: 0;
    padding: 8px;
    overflow-y: auto;
    background: var(--desk);
    container-type: inline-size;
  }
  main > :not(.cards) {
    flex: none;
  }
  .keys {
    display: flex;
    flex-wrap: wrap;
    align-items: start;
    justify-content: space-between;
    gap: 6px 24px;
    padding: 6px 8px 8px;
  }
  /* warnings: a yellow block that opens into the list, which then takes a row of its own */
  .warnings[open] {
    flex-basis: 100%;
    background: var(--well);
    border: 1px solid var(--line);
  }
  .warnings summary {
    display: flex;
  }
  .warnings summary::before {
    content: '\25B2';
  }
  .warnings summary::after {
    content: '+';
    margin-left: auto;
    padding-left: 2ch;
  }
  .warnings[open] summary {
    border-width: 0 0 1px;
  }
  .warnings[open] summary::after {
    content: '\2212';
  }
  .warnings ul {
    padding: 4px 8px 4px 3ch;
  }
  /* two columns of panels; the panels of a column share its height */
  .cards {
    display: flex;
    flex: 1 0 auto;
    gap: 8px;
  }
  .col {
    display: flex;
    flex: 1 1 0;
    flex-direction: column;
    gap: 8px;
    min-width: 0;
  }
  .cards :global(.card) {
    flex: 1 0 320px; /* never below a usable height: the desk scrolls instead */
    min-height: 0; /* ... and never as tall as its content: the panel scrolls instead */
  }
  .cards :global(.card:is(.folded, .fit:not(.max))) {
    flex: none;
  }
  /* an expanded card is alone on the desk */
  .cards:has(:global(.max)) :global(.card:not(.max)),
  .cards:has(:global(.max)) .col:not(:has(:global(.max))) {
    display: none;
  }
  /* a desk too narrow for two readable plots side by side: one column, in reading order */
  @container (max-width: 1000px) {
    .cards {
      flex-direction: column;
    }
    .col {
      display: contents;
    }
    .col:last-child > :global(:nth-child(1)) {
      order: 2;
    }
    .col:first-child > :global(:nth-child(2)) {
      order: 3;
    }
    .col:last-child > :global(:nth-child(2)) {
      order: 4;
    }
  }
  .stale,
  .cards :global(.stale) {
    opacity: 0.55;
  }
  .banner {
    white-space: pre-wrap;
  }
  .statusbar {
    grid-area: status;
    display: flex;
    border-top: 1px solid var(--line);
  }
  .statusbar > span {
    display: flex;
    align-items: center;
    gap: 8px;
    height: 22px;
    padding: 0 10px;
    white-space: nowrap;
  }
  .statusbar > span:not(:empty) + span {
    border-left: 1px solid var(--line);
  }
  /* a narrow screen: the page scrolls, the inputs fold away and everything has its natural
     height */
  @media (max-width: 759.98px) {
    .app {
      display: block;
      height: auto;
    }
    .rail {
      display: block;
      border-right: 0;
      border-bottom: 1px solid var(--line);
    }
    main {
      --chart-k: 1;
      overflow: visible;
    }
    .sep {
      display: none;
    }
    .cards :global(.card) {
      flex: none;
    }
  }
</style>
