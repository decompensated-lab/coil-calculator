<script lang="ts">
  import Choice from './lib/Choice.svelte';
  import CoilForm from './lib/CoilForm.svelte';
  import { Computer } from './lib/compute.svelte';
  import BzProfiles from './lib/BzProfiles.svelte';
  import { TAB_TIPS } from './lib/help';
  import ImpedancePlot from './lib/ImpedancePlot.svelte';
  import Num from './lib/Num.svelte';
  import { COUPLINGS, GAP_REFS, VNA_SETUPS, defaultParams } from './lib/protocol';
  import Summary from './lib/Summary.svelte';
  import Tabs from './lib/Tabs.svelte';
  import TransferPlot from './lib/TransferPlot.svelte';
  import TurnCurrents from './lib/TurnCurrents.svelte';
  import VnaPlot from './lib/VnaPlot.svelte';

  const TABS = ['Bz profiles', 'Impedance', 'Transfer A→B', 'VNA', 'Turn currents'] as const;
  let tab: string = $state('Impedance');

  const params = $state(defaultParams());
  const computer = new Computer();

  // recompute shortly after the last edit (the worker keeps only the newest request)
  $effect(() => {
    const p = $state.snapshot(params);
    const t = setTimeout(() => computer.request(p), 120);
    return () => clearTimeout(t);
  });
</script>

<div class="app">
  <aside>
    <h1>coilcal <span>turn-level coil model</span></h1>
    <fieldset>
      <legend>Coil A (driven)</legend>
      <CoilForm bind:coil={params.a} />
    </fieldset>
    <fieldset disabled={!params.b_enabled}>
      <legend title="Untick to model coil A alone.">
        <label><input type="checkbox" bind:checked={params.b_enabled} /> Coil B (pickup)</label>
      </legend>
      <CoilForm bind:coil={params.b}>
        {#snippet extra()}
          <Choice label="gap reference" tip="gap_ref" bind:value={params.gap_ref} options={GAP_REFS} />
          <Num label="axial gap" tip="gap" bind:value={params.gap_mm} unit="mm" step={1} />
          <Num label="lateral offset" tip="offset" bind:value={params.offset_mm} unit="mm" step={1} />
        {/snippet}
      </CoilForm>
    </fieldset>
    <fieldset>
      <legend>VNA</legend>
      <Choice label="setup" tip="vna_setup" bind:value={params.vna_setup} options={VNA_SETUPS} />
      <Num label="Z0" tip="z0" bind:value={params.z0} unit="Ω" step={1} min={1} />
      <Num label="source power" tip="p_dbm" bind:value={params.p_dbm} unit="dBm" step={1} />
    </fieldset>
    <fieldset>
      <legend>Analysis</legend>
      <Num label="f min" tip="f_min" bind:value={params.f_min_mhz} unit="MHz" step={0.1} />
      <Num label="f max" tip="f_max" bind:value={params.f_max_mhz} unit="MHz" step={1} />
      <Num label="points" tip="n_freq" bind:value={params.n_freq} step={1} min={10} max={5000} />
      <Num label="view f" tip="f_view" bind:value={params.f_view_mhz} unit="MHz" step={0.5} />
      <Num label="B load" tip="z_load" bind:value={params.z_load} unit="Ω" step={10} />
      <Num label="R factor" tip="r_factor" bind:value={params.r_factor} step={0.1} min={0.1} />
      <Choice label="inter-coil coupling" tip="coupling" bind:value={params.coupling}
        options={COUPLINGS} />
      <Num label="Bz(x) at z" tip="x_line_z" bind:value={params.x_line_z_mm} unit="mm" step={1} />
    </fieldset>
    <p class={["status", { error: computer.error }]} aria-live="polite">
      {#if computer.error}
        {computer.error}
      {:else if computer.busy}
        computing…
      {:else if computer.result}
        computed in {computer.ms.toFixed(0)} ms
      {/if}
    </p>
  </aside>

  <main>
    {#if computer.error}
      <p class="banner" role="alert">{computer.error}</p>
    {/if}
    {#if computer.result}
      {@const r = computer.result}
      <Tabs tabs={TABS} bind:selected={tab} label="Results" tips={TAB_TIPS}>
        {#snippet panel()}
          {#if tab === 'Bz profiles'}
            <BzProfiles {r} />
          {:else if tab === 'Impedance'}
            <ImpedancePlot {r} />
          {:else if tab === 'Transfer A→B'}
            <TransferPlot {r} />
          {:else if tab === 'VNA'}
            <VnaPlot {r} />
          {:else if tab === 'Turn currents'}
            <TurnCurrents {r} />
          {/if}
        {/snippet}
      </Tabs>
      <section class={["summary", { stale: computer.error || computer.busy }]}>
        <Summary r={computer.result} />
      </section>
    {:else if !computer.error}
      <p class="muted">Loading the model…</p>
    {/if}
  </main>
</div>

<style>
  .app {
    display: grid;
    grid-template-columns: 340px minmax(0, 1fr);
    height: 100vh;
  }
  aside {
    overflow-y: auto;
    padding: 12px 14px;
    border-right: 1px solid var(--grid);
    background: var(--panel);
  }
  h1 {
    margin: 0 0 10px;
    font-size: 1.15rem;
  }
  h1 span {
    font-weight: 400;
    color: var(--muted);
    font-size: 0.85rem;
  }
  fieldset {
    margin: 0 0 10px;
    padding: 6px 10px 8px;
    border: 1px solid var(--grid);
    border-radius: 6px;
  }
  legend {
    font-weight: 600;
    padding: 0 4px;
  }
  main {
    overflow-y: auto;
    padding: 12px 16px;
    min-width: 0;
  }
  .summary {
    margin-top: 12px;
    padding-top: 10px;
    border-top: 1px solid var(--grid);
  }
  .stale {
    opacity: 0.55;
  }
  .status {
    min-height: 1.4em;
    color: var(--muted);
    white-space: pre-wrap;
  }
  .status.error {
    color: var(--error);
  }
  .banner {
    margin: 0 0 10px;
    padding: 6px 10px;
    border-left: 3px solid var(--error);
    color: var(--error);
    background: var(--panel);
  }
  @media (max-width: 760px) {
    .app {
      grid-template-columns: minmax(0, 1fr);
      height: auto;
    }
    aside {
      border-right: 0;
      border-bottom: 1px solid var(--grid);
    }
  }
</style>
