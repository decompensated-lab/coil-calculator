<!-- Results at the view frequency (port of gui/richtext.py summary_html): one table with a
     column per coil, then the A → B and VNA quantities. -->
<script lang="ts">
  import katex from 'katex';
  import 'katex/dist/katex.min.css';
  import type { Grounding } from './protocol';
  import { type Results, abs, at, coilAtView, deg, div, g, mul, pct, si } from './results';

  let { r }: { r: Results } = $props();

  /** A value, or a value with a per-coil remark under it. */
  type Cell = string | [value: string, detail: string];
  interface CoilRow {
    sym: string;
    cells: Cell[];
    note?: string;
  }
  type Row = [sym: string, value: string, note?: string];
  interface Section {
    title: string;
    sub?: string;
    rows: Row[];
  }

  // {@html} below only ever gets KaTeX output for fixed TeX strings and formatted numbers
  const tex = (s: string) => katex.renderToString(s, { throwOnError: false });
  const groundLabel = (g: Grounding) => (g === 'floating' ? 'floating' : `${g} grounded`);
  const nanmin = (xs: number[]) => Math.min(...xs.filter((x) => !Number.isNaN(x)));

  function coilRows(r: Results): CoilRow[] {
    const p = r.params;
    const lam = 299_792_458 / r.fView;
    const ks = r.coils.map((_, k) => k);
    const v = ks.map((k) => coilAtView(r, k));
    const two = ks.length === 2;
    // any resonance of the system shows up in every port's Z (through the coupling)
    const fRes = nanmin([...r.srfNet, ...r.srfHere]);
    const below = !Number.isFinite(fRes) || r.fView < 0.5 * fRes;
    const shifted = (k: number) =>
      two && Number.isFinite(r.srfHere[k]) && Math.abs(r.srfHere[k] / r.srfNet[k] - 1) > 1e-3;
    const row = (sym: string, cell: (k: number) => Cell, note?: string): CoilRow => ({
      sym, cells: ks.map(cell), note,
    });
    return [
      row('L_\\mathrm{DC}', (k) => si(r.lDc[k], 'H'), 'static, ring model'),
      row('|Z_{in}|', (k) => [si(abs(v[k].z), 'Ω'), `∠ ${deg(v[k].z).toFixed(1)}°`],
        two ? 'other coil open' : undefined),
      row('L_\\mathrm{eff}', (k) =>
        v[k].lEff > 0
          ? [si(v[k].lEff, 'H'), `${pct(v[k].lEff / r.lDc[k] - 1)} vs DC`]
          : ['—', 'capacitive'],
        v.some((c) => c.lEff <= 0) ? 'Im Z_in/ω; capacitive near or above a resonance' : 'Im Z_in/ω'),
      row('R_\\mathrm{ac}', (k) => si(v[k].rAc, 'Ω'), 'skin effect × R factor'),
      row('Q_L', (k) => g(v[k].qL), 'ωL_DC/R_ac: copper only'),
      row('X/R\\ \\mathrm{of}\\ Z_{in}', (k) => (below ? g(v[k].z.im / v[k].z.re) : '—'),
        below ? 'incl. dielectric loss' : 'not a Q: too close to resonance'),
      row('f_\\mathrm{SRF}', (k) => [si(r.srfNet[k], 'Hz'), groundLabel(p[k ? 'b' : 'a'].ground)],
        'coil alone'),
      ...(ks.some(shifted)
        ? [row('f_\\mathrm{res}', (k) => (shifted(k) ? si(r.srfHere[k], 'Hz') : '—'),
            'other coil present (open)')]
        : []),
      row('Q_\\mathrm{SRF}', (k) => g(r.qSrf[k]), 'copper + dielectric loss'),
      row('R_p', (k) => si(r.rpSrf[k], 'Ω', 3), 'at resonance'),
      row('f_\\mathrm{SRF}^\\mathrm{no\\ dielectric}', (k) =>
        Number.isFinite(r.srfVacuum[k])
          ? [si(r.srfVacuum[k], 'Hz'), `${pct(r.srfNet[k] / r.srfVacuum[k] - 1)} with dielectric`]
          : ['—', 'no dielectrics set'],
        'no insulation, no former'),
      row('f_\\mathrm{SRF}^\\mathrm{Medhurst}', (k) =>
        [si(r.srfMedhurst[k], 'Hz'), `C = ${si(r.cMedhurst[k], 'F', 3)}`],
        'estimate, bare wire'),
      row('\\ell_\\mathrm{wire}', (k) =>
        [si(r.coils[k].wire_length, 'm'), `${(r.coils[k].wire_length / lam).toFixed(3)} λ`]),
      row('\\ell', (k) => `${(r.coils[k].length * 1e3).toFixed(1)} mm`, 'winding length'),
      row('r', (k) => `${(r.coils[k].mean_radius * 1e3).toFixed(2)} mm`, 'mean radius'),
    ];
  }

  function sections(r: Results): Section[] {
    const p = r.params;
    const i = r.iView;
    const w = 2 * Math.PI * r.fView;
    const out: Section[] = [];
    if (r.coils.length === 2) {
      const z21 = at(r.z, i * 4 + 2);
      const z22 = at(r.z, i * 4 + 3);
      const ratio = div(z21, { re: 0, im: w * r.mStatic });
      const zl = { re: p.z_load, im: 0 };
      const vl = div(mul(z21, zl), { re: zl.re + z22.re, im: z22.im });
      const rows: Row[] = [
        ['M', si(r.mStatic, 'H'), 'static'],
        ['k=M/\\sqrt{L_A L_B}', r.kStatic.toFixed(4)],
        ['|Z_{21}|', si(abs(z21), 'Ω'), '= open-circuit V_B per A in A'],
        ['|Z_{21}|/\\omega M', abs(ratio).toFixed(4), `∠ ${deg(ratio).toFixed(2)}°`],
        [`|V_B|\\,@\\,${g(p.z_load, 6)}\\,\\Omega`, si(abs(vl), 'V/A')],
      ];
      if (Number.isFinite(r.electricFraction)) {
        rows.push(['|Z_{21}^{(E)}|/|Z_{21}|', `${(100 * r.electricFraction).toFixed(2)}%`, 'capacitive path']);
      }
      out.push({ title: 'A → B (open circuit)', rows });
    }

    const db = (z: { re: number; im: number }) => (20 * Math.log10(Math.max(abs(z), 1e-30))).toFixed(2);
    const sp = [0, 2, 3].map((j) => at(r.s, i * 4 + j));
    let bMax = 0;
    for (let j = 0; j < r.fieldB.data.length; j += 2) {
      bMax = Math.max(bMax, Math.hypot(r.fieldB.data[j], r.fieldB.data[j + 1]));
    }
    out.push({
      title: 'VNA',
      sub: p.vna_setup,
      rows: [
        ...(['S_{11}', 'S_{21}', 'S_{22}'].map((s, j): Row => [s, `${db(sp[j])} dB`, `∠ ${deg(sp[j]).toFixed(1)}°`])),
        ['V^{+}', si(r.vPlus, 'V'), `peak, ${g(p.p_dbm, 6)} dBm into ${g(p.z0, 6)} Ω`],
        ['|I_{P1}|', si(abs(at(r.drivePortI, 2 * i)), 'A'), 'peak'],
        ['|I_{P2}|', si(abs(at(r.drivePortI, 2 * i + 1)), 'A'), 'peak'],
        ['|B|_\\mathrm{max}', si(bMax, 'T'), 'in side-view plane'],
      ],
    });
    return out;
  }

  const coil = $derived(coilRows(r));
  const secs = $derived(sections(r));
</script>

<div class="cols">
<!-- svelte-ignore a11y_no_noninteractive_tabindex (a scrolling region must take keyboard focus) -->
<div class="scroll" role="region" aria-label="Coil quantities at the view frequency" tabindex="0">
  <table>
    <thead>
      <tr>
        <td></td>
        {#each r.coils as _, k (k)}<th scope="col">Coil {'AB'[k]}</th>{/each}
        <td></td>
      </tr>
    </thead>
    <tbody>
      {#each coil as row (row.sym)}
        <tr>
          <th scope="row">{@html tex(row.sym)}</th>
          {#each row.cells as cell, k (k)}
            {#if typeof cell === 'string'}
              <td class="value">{cell}</td>
            {:else}
              <td class="value">{cell[0]}<small>{cell[1]}</small></td>
            {/if}
          {/each}
          <td class="muted">{row.note ?? ''}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>
  {#each secs as s (s.title)}
    <section>
      <h3>{s.title}</h3>
      {#if s.sub}<p class="muted">{s.sub}</p>{/if}
      <table>
        <tbody>
          {#each s.rows as [sym, value, note] (sym)}
            <tr>
              <th scope="row">{@html tex(sym)}</th>
              <td class="value">{value}</td>
              <td class="muted">{note ?? ''}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </section>
  {/each}
</div>

<style>
  .scroll {
    max-width: 100%;
    overflow-x: auto;
  }
  .scroll:focus-visible {
    outline: 2px solid var(--accent);
  }
  table {
    border-collapse: separate;
    border-spacing: 0;
  }
  thead th {
    padding: 0 8px 2px 0;
    text-align: right;
  }
  tbody th {
    position: sticky;
    inset-inline-start: 0;
    padding: 1px 10px 1px 0;
    font-weight: 400;
    text-align: left;
    vertical-align: top;
    white-space: nowrap;
    background: var(--bg);
  }
  .cols {
    display: flex;
    flex-wrap: wrap;
    align-items: start;
    gap: 12px 28px;
  }
  h3 {
    margin: 0;
    font-size: 1rem;
  }
  p.muted {
    margin: 0;
  }
  .muted {
    color: var(--muted);
  }
  td {
    padding: 1px 8px 1px 0;
    vertical-align: top;
  }
  td.value {
    text-align: right;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  small {
    display: block;
    font-weight: 400;
    color: var(--muted);
  }
</style>
