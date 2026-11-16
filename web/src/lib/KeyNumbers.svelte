<!-- The handful of results that stay visible above the plots; the full table has the rest. -->
<script lang="ts">
  import { COIL_COLORS } from './plot';
  import { type Results, abs, at, coilAtView, g, si } from './results';

  let { r }: { r: Results } = $props();

  /** Label and one value per coil, or a single value for the pair. */
  const tiles = $derived.by(() => {
    const ks = r.coils.map((_, k) => k);
    const v = ks.map((k) => coilAtView(r, k));
    const f = si(r.fView, 'Hz');
    const s21 = 20 * Math.log10(Math.max(abs(at(r.s, r.iView * 4 + 2)), 1e-30));
    const out: { label: string; values: string[]; perCoil: boolean }[] = [
      { label: 'L (DC)', values: ks.map((k) => si(r.lDc[k], 'H')), perCoil: true },
      { label: 'SRF', values: ks.map((k) => si(r.srfNet[k], 'Hz')), perCoil: true },
      { label: 'Q (copper)', values: ks.map((k) => g(v[k].qL)), perCoil: true },
      { label: `|Z in| at ${f}`, values: ks.map((k) => si(abs(v[k].z), 'Ω')), perCoil: true },
    ];
    if (ks.length === 2) out.push({ label: 'k', values: [r.kStatic.toFixed(4)], perCoil: false });
    out.push({ label: `|S21| at ${f}`, values: [`${s21.toFixed(2)} dB`], perCoil: false });
    return out;
  });
</script>

<dl>
  {#each tiles as t (t.label)}
    <div>
      <dt>{t.label}</dt>
      {#each t.values as value, k (k)}
        <dd>
          {#if t.perCoil}<small style:color={COIL_COLORS[k]}>{'AB'[k]}</small>{/if}
          {value}
        </dd>
      {/each}
    </div>
  {/each}
</dl>

<style>
  dl {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 26px;
    margin: 0;
  }
  dt {
    color: var(--dim);
  }
  dd {
    margin: 0;
    font-size: 17px;
    line-height: 22px;
    white-space: nowrap;
  }
  small {
    font-size: 11px;
    font-weight: 700;
  }
</style>
