<!-- Results of the wire-pair calculator (gui/pair.py pair_summary_html). -->
<script lang="ts">
  import katex from 'katex';
  import { type PairResults, g, si } from './results';

  let { r }: { r: PairResults } = $props();

  type Row = [sym: string, value: string, note?: string];
  const C0 = 299_792_458;
  /** `f"{x:+.2%}"` */
  const signed = (x: number) => `${x >= 0 ? '+' : ''}${(100 * x).toFixed(2)}%`;
  // {@html} below only ever gets KaTeX output for fixed TeX strings
  const tex = (s: string) => katex.renderToString(s, { throwOnError: false });

  function sections(r: PairResults): { title: string; rows: Row[]; foot?: string }[] {
    const c = r.c.re;
    const pfm = (v: number) => `${g(v * 1e12, 4)} pF/m`;
    const epsEff = c / r.cBare;
    const tanD = -r.c.im / r.c.re;
    const rows: Row[] = [
      ["C'", pfm(c), 'exact, insulation + air'],
      ["C'_\\mathrm{bare}", pfm(r.cBare), 'insulation removed'],
    ];
    if (Number.isFinite(r.cUniform)) {
      rows.push([
        "\\varepsilon_r C'_\\mathrm{bare}",
        pfm(r.cUniform),
        `all space dielectric (C′ = ${(100 * (c / r.cUniform)).toFixed(1)}% of it)`,
      ]);
    }
    rows.push(
      ["C'_{a_\\mathrm{eff}}", pfm(r.cEff), `effective-radius approx., ${signed(r.cEff / c - 1)}`],
      ['\\tan\\delta_\\mathrm{eff}', g(tanD, 3), `G′ = ${si(2 * Math.PI * 1e6 * -r.c.im, 'S/m', 3)} @ 1 MHz`],
    );
    const line: Row[] = [
      ["\\varepsilon_\\mathrm{eff}=C'/C'_\\mathrm{air}", epsEff.toFixed(4)],
      [
        "Z_0=1/(c_0\\sqrt{C' C'_\\mathrm{air}})",
        `${g(1 / (C0 * Math.sqrt(c * r.cBare)), 4)} Ω`,
        'differential (forward/return), quasi-TEM',
      ],
      ['v/c_0=1/\\sqrt{\\varepsilon_\\mathrm{eff}}', (1 / Math.sqrt(epsEff)).toFixed(4)],
      ["L'_\\mathrm{ext}", si(1 / (C0 ** 2 * r.cBare), 'H/m'), 'external (HF)'],
    ];
    const [w1, w2] = r.wires;
    const geo: Row[] = [
      ['s', `${g(r.spacing * 1e3, 4)} mm`, 'centre-to-centre'],
      ['g', `${g((r.spacing - w1.b - w2.b) * 1e3, 4)} mm`, 'insulation surface gap'],
    ];
    for (const [k, w] of r.wires.entries()) {
      if (r.params.same && k === 1) break;
      const who = r.params.same ? 'wires 1, 2' : `wire ${k + 1}`;
      geo.push([`t_{${k + 1}}`, `${g((w.b - w.a) * 1e3, 4)} mm`, `insulation thickness, ${who}`]);
    }
    return [
      { title: 'Capacitance per length', rows },
      { title: 'As a two-wire line', rows: line },
      { title: 'Geometry', rows: geo, foot: `${r.nTerms} multipole terms per wire` },
    ];
  }

  const secs = $derived(sections(r));
</script>

{#if !r.converged}
  <p class="warn">⚠ multipole series not fully converged ({r.nTerms} terms)</p>
{/if}
<div class="cols">
  {#each secs as s (s.title)}
    <section>
      <h3>{s.title}</h3>
      <table>
        <tbody>
          {#each s.rows as [sym, value, note] (sym)}
            <tr>
              <td>{@html tex(sym)}</td>
              <td class="value">{value}</td>
              <td class="muted">{note ?? ''}</td>
            </tr>
          {/each}
        </tbody>
      </table>
      {#if s.foot}<p class="muted">{s.foot}</p>{/if}
    </section>
  {/each}
</div>
<p class="muted">
  Two long parallel wires, insulation in air; {@html tex('C = q/(V_1-V_2)')} with equal and opposite
  charges.
</p>

<style>
  .warn {
    margin: 2px 0;
    color: var(--warn);
  }
  .cols {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 28px;
  }
  h3 {
    margin: 0;
    font-size: 1rem;
  }
  td {
    padding: 1px 8px 1px 0;
    vertical-align: middle;
  }
  td.value {
    text-align: right;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
</style>
