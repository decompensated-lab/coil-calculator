<!-- Results at the view frequency (port of gui/richtext.py summary_html). -->
<script lang="ts">
  import katex from 'katex';
  import 'katex/dist/katex.min.css';
  import type { CoilParams, Grounding } from './protocol';
  import { type Results, abs, at, deg, div, g, mul, pct, si } from './results';

  let { r }: { r: Results } = $props();

  type Row = [sym: string, value: string, note?: string];
  interface Section {
    title: string;
    sub?: string[];
    rows: Row[];
  }

  // {@html} below only ever gets KaTeX output for fixed TeX strings and formatted numbers
  const tex = (s: string) => katex.renderToString(s, { throwOnError: false });
  const groundLabel = (g: Grounding) => (g === 'floating' ? 'floating' : `${g} grounded`);
  const nanmin = (xs: number[]) => Math.min(...xs.filter((x) => !Number.isNaN(x)));

  function dielectricLabel(c: CoilParams): string {
    const t = (c.insulation_d_mm - c.wire_d_mm) / 2;
    const ins =
      t > 0 && c.insulation.eps_r !== 1
        ? `insulation εr ${g(c.insulation.eps_r, 6)} (${(t * 1e3).toFixed(0)} µm)`
        : t <= 0
          ? 'bare wire'
          : 'insulation εr 1';
    const fmr =
      c.former.eps_r !== 1
        ? `former εr ${g(c.former.eps_r, 6)}, ${g(c.former_wall_mm, 6)} mm wall`
        : 'no former dielectric';
    return `${ins} · ${fmr}`;
  }

  function sections(r: Results): Section[] {
    const p = r.params;
    const f = r.fView;
    const w = 2 * Math.PI * f;
    const lam = 299_792_458 / f;
    const nc = r.coils.length;
    const i = r.iView;
    // any resonance of the system shows up in every port's Z (through the coupling)
    const fRes = nanmin([...r.srfNet, ...r.srfHere]);
    const below = !Number.isFinite(fRes) || f < 0.5 * fRes;
    const out: Section[] = r.coils.map((c, k) => {
      const z = at(r.z, (i * nc + k) * nc + k);
      const lEff = z.im / w;
      const rAc = r.rF(k)[i];
      const other = nc === 2 ? 'AB'[1 - k] : null;
      const rows: Row[] = [
        ['L_\\mathrm{DC}', si(r.lDc[k], 'H'), 'static, ring model'],
        ['|Z_{in}|', si(abs(z), 'Ω'), `∠ ${deg(z).toFixed(1)}°${other ? `, coil ${other} open` : ''}`],
        [
          'L_\\mathrm{eff}=\\mathrm{Im}\\,Z_{in}/\\omega',
          lEff > 0 ? si(lEff, 'H') : '—',
          lEff > 0 ? `${pct(lEff / r.lDc[k] - 1)} vs DC` : 'capacitive: near/above a resonance',
        ],
        ['R_\\mathrm{ac}', si(rAc, 'Ω'), 'copper: skin effect × R factor'],
        ['Q_L=\\omega L_\\mathrm{DC}/R_\\mathrm{ac}', g((w * r.lDc[k]) / rAc), 'copper only, far below resonance'],
        [
          'X/R\\ \\mathrm{of}\\ Z_{in}',
          below ? g(z.im / z.re) : '—',
          below ? 'incl. dielectric loss and resonance' : 'not a Q here: too close to resonance',
        ],
        ['f_\\mathrm{SRF}', si(r.srfNet[k], 'Hz'), `coil alone, ${groundLabel(p[k ? 'b' : 'a'].ground)}`],
      ];
      if (other && Number.isFinite(r.srfHere[k]) && Math.abs(r.srfHere[k] / r.srfNet[k] - 1) > 1e-3) {
        rows.push(['f_\\mathrm{res}', si(r.srfHere[k], 'Hz'), `with coil ${other} present (open)`]);
      }
      rows.push(
        [
          'Q_\\mathrm{SRF}',
          g(r.qSrf[k]),
          `at resonance, copper + dielectric loss; R_p = ${si(r.rpSrf[k], 'Ω', 3)}`,
        ],
        [
          'f_\\mathrm{SRF}^\\mathrm{no\\ dielectric}',
          si(r.srfVacuum[k], 'Hz'),
          Number.isFinite(r.srfVacuum[k])
            ? `${pct(r.srfNet[k] / r.srfVacuum[k] - 1)} from insulation + former`
            : 'no dielectrics set',
        ],
        [
          'f_\\mathrm{SRF}^\\mathrm{Medhurst}',
          si(r.srfMedhurst[k], 'Hz'),
          `C = ${si(r.cMedhurst[k], 'F', 3)}, bare wire in air`,
        ],
        ['\\ell_\\mathrm{wire}/\\lambda', (c.wire_length / lam).toFixed(3), si(c.wire_length, 'm')],
      );
      return {
        title: `Coil ${'AB'[k]}`,
        sub: [
          `${c.n_turns} turns · ℓ = ${(c.length * 1e3).toFixed(1)} mm · r = ${(c.mean_radius * 1e3).toFixed(2)} mm`,
          dielectricLabel(p[k ? 'b' : 'a']),
        ],
        rows,
      };
    });

    if (nc === 2) {
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
      sub: [p.vna_setup],
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

  const secs = $derived(sections(r));
</script>

<p class="head">
  View frequency <b>{si(r.fView, 'Hz')}</b> · λ = {g(299_792_458 / r.fView, 3)} m ·
  {@html tex('\\omega = 2\\pi f')}
</p>
{#each r.warnings as w (w)}
  <p class="warn">⚠ {w}</p>
{/each}
<div class="cols">
  {#each secs as s (s.title)}
    <section>
      <h3>{s.title}</h3>
      {#each s.sub ?? [] as line (line)}
        <p class="muted">{line}</p>
      {/each}
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
    </section>
  {/each}
</div>

<style>
  .head {
    margin: 0 0 4px;
  }
  .warn {
    margin: 2px 0;
    color: var(--warn);
  }
  .cols {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 28px;
    margin-top: 6px;
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
    vertical-align: middle;
  }
  td.value {
    text-align: right;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
</style>
