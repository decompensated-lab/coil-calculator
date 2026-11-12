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
  <header>
    <h1>coilcal <span>turn-level coil model</span></h1>
    <fieldset class="mode">
      <legend>Model</legend>
      <label><input type="radio" bind:group={mode} value="coils" /> Coils</label>
      <label title={TAB_TIPS['Wire pair C']}>
        <input type="radio" bind:group={mode} value="pair" /> Wire pair C
      </label>
    </fieldset>
    {#if !onPair}
      <Num label="view f" tip="f_view" bind:value={params.f_view_mhz} unit="MHz" step={0.5} />
    {/if}
    <p class={['status', { error: active.error }]} aria-live="polite">
      {#if active.error}
        input error
      {:else if active.busy}
        computing…
      {:else if active.result}
        {active.ms.toFixed(0)} ms
      {/if}
    </p>
    <Guide />
  </header>

  <aside>
    <details open={wide.current || setup}
      ontoggle={(e) => { if (!wide.current) setup = e.currentTarget.open; }}>
      <summary>Setup</summary>
      {#if onPair}
        <PairForm bind:pair coilA={params.a} />
      {:else}
        <CoilTable bind:params />
        <fieldset disabled={!params.b_enabled}>
          <legend>Placement of B</legend>
          <Choice label="gap reference" tip="gap_ref" bind:value={params.gap_ref} options={GAP_REFS} />
          <Num label="axial gap" tip="gap" bind:value={params.gap_mm} unit="mm" step={1} />
          <Num label="lateral offset" tip="offset" bind:value={params.offset_mm} unit="mm" step={1} />
        </fieldset>
        <fieldset>
          <legend>Measurement</legend>
          <Choice label="VNA setup" tip="vna_setup" bind:value={params.vna_setup} options={VNA_SETUPS} />
          <Num label="Z0" tip="z0" bind:value={params.z0} unit="Ω" step={1} min={1} />
          <Choice label="drive" tip="drive" bind:value={params.drive} options={DRIVES} />
          <Num label="source power" tip="p_dbm" bind:value={params.p_dbm} unit="dBm" step={1}
            disabled={params.drive !== 'source power'} />
          <Num label="P1 current" tip="i_drive" bind:value={params.i_drive_a} unit="A" step={0.1}
            min={0} disabled={params.drive === 'source power'} />
          <Num label="load on B" tip="z_load" bind:value={params.z_load} unit="Ω" step={10} />
        </fieldset>
        <fieldset>
          <legend>Sweep and model</legend>
          <Num label="f min" tip="f_min" bind:value={params.f_min_mhz} unit="MHz" step={0.1} />
          <Num label="f max" tip="f_max" bind:value={params.f_max_mhz} unit="MHz" step={1} />
          <Num label="points" tip="n_freq" bind:value={params.n_freq} step={1} min={10} max={5000} />
          <Num label="R factor" tip="r_factor" bind:value={params.r_factor} step={0.1} min={0.1} />
          <Choice label="coil coupling" tip="coupling" bind:value={params.coupling}
            options={COUPLINGS} />
        </fieldset>
      {/if}
    </details>
  </aside>

  <main>
    {#if active.error}
      <p class="banner" role="alert">{active.error}</p>
    {/if}
    {#if onPair}
      {#if pairComputer.result}
        {@const stale = pairComputer.error || pairComputer.busy}
        <PairPlot r={pairComputer.result} />
        <section class={['summary', 'pair', { stale }]}>
          <PairSummary r={pairComputer.result} />
        </section>
      {/if}
    {:else if computer.result}
      {@const r = computer.result}
      {@const stale = computer.error || computer.busy}
      <div class={['top', { stale }]}>
        <KeyNumbers {r} />
        {#if r.warnings.length}
          <details class="warnings">
            <summary>⚠ {r.warnings.length} model {r.warnings.length > 1 ? 'warnings' : 'warning'}</summary>
            <ul>
              {#each r.warnings as w (w)}<li>{w}</li>{/each}
            </ul>
          </details>
        {/if}
      </div>
      <div class="cards">
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
        <Card title="At {si(r.fView, 'Hz')}" {...size('snapshot')}>
          <Tabs tabs={SNAPSHOT} bind:selected={snapshot} label="At the view frequency" tips={TIPS}>
            {#snippet panel()}
              {#if snapshot === 'Turn currents'}
                <TurnCurrents {r} />
              {:else}
                <BzProfiles {r} bind:cutZ={params.x_line_z_mm} />
              {/if}
            {/snippet}
          </Tabs>
        </Card>
        <Card title="Numbers at {si(r.fView, 'Hz')}" class={['summary', { stale }]}
          {...size('numbers')}>
          <Summary {r} />
        </Card>
      </div>
    {:else if !computer.error}
      <p class="muted">Loading the model…</p>
    {/if}
  </main>
</div>

<style>
  .app {
    display: grid;
    grid-template-columns: 360px minmax(0, 1fr);
    grid-template-rows: auto minmax(0, 1fr);
    grid-template-areas:
      'top  top'
      'side main';
    height: 100dvh;
  }
  header {
    grid-area: top;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px 18px;
    padding: 6px 14px;
    border-bottom: 1px solid var(--grid);
    background: var(--panel);
  }
  h1 {
    margin: 0;
    font-size: 1.15rem;
  }
  h1 span {
    font-weight: 400;
    color: var(--muted);
    font-size: 0.85rem;
  }
  /* the two models as a segmented control: native radios, drawn as one pill */
  .mode {
    display: flex;
    margin: 0;
    padding: 2px;
    border-radius: 6px;
    background: var(--input);
  }
  .mode legend {
    position: absolute;
    clip-path: inset(50%);
  }
  .mode label {
    padding: 1px 10px;
    border-radius: 4px;
    cursor: pointer;
  }
  .mode input {
    position: absolute;
    opacity: 0;
  }
  .mode label:has(:checked) {
    color: var(--bg);
    background: var(--accent);
  }
  .mode label:has(:focus-visible) {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
  header :global(.row) {
    grid-template-columns: auto 7em;
    margin: 0;
  }
  .status {
    margin: 0 0 0 auto;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  .status.error {
    color: var(--error);
  }
  aside {
    grid-area: side;
    overflow-y: auto;
    padding: 12px 14px;
    border-right: 1px solid var(--grid);
    background: var(--panel);
  }
  aside summary {
    display: none;
    font-weight: 600;
    cursor: pointer;
  }
  main {
    grid-area: main;
    overflow-y: auto;
    padding: 12px 16px;
    min-width: 0;
    container-type: inline-size;
  }
  .top {
    display: flex;
    flex-wrap: wrap;
    align-items: start;
    justify-content: space-between;
    gap: 6px 24px;
    margin-bottom: 12px;
  }
  .warnings {
    max-width: 60ch;
    color: var(--warn);
  }
  .warnings summary {
    cursor: pointer;
  }
  .warnings ul {
    margin: 4px 0 0;
    padding-left: 1.2em;
  }
  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(400px, 100%), 1fr));
    gap: 12px;
    align-items: start;
  }
  /* an expanded card is alone in the grid */
  .cards:has(> :global(.max)) > :global(:not(.max)) {
    display: none;
  }
  /* three columns: the table takes the two free ones of the second row */
  @container (min-width: 1224px) {
    .cards > :global(.summary:not(.folded, .max)) {
      grid-column: span 2;
    }
  }
  .summary.pair {
    margin-top: 12px;
    padding-top: 10px;
    border-top: 1px solid var(--grid);
  }
  .stale,
  .cards > :global(.stale) {
    opacity: 0.55;
  }
  .banner {
    margin: 0 0 10px;
    padding: 6px 10px;
    border-left: 3px solid var(--error);
    color: var(--error);
    background: var(--panel);
    white-space: pre-wrap;
  }
  @media (max-width: 759.98px) {
    .app {
      grid-template-columns: minmax(0, 1fr);
      grid-template-areas: 'top' 'side' 'main';
      height: auto;
    }
    aside {
      border-right: 0;
      border-bottom: 1px solid var(--grid);
    }
    aside summary {
      display: list-item;
    }
    aside details[open] summary {
      margin-bottom: 8px;
    }
  }
</style>
