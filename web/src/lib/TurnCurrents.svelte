<!-- Turn currents and node voltages for the VNA drive (gui/plots.py draw_distribution). -->
<script lang="ts">
  import { COIL_STYLES, type Panel, charts, coilName } from './plot';
  import { type Results, abs, at, g, si, driveLabel } from './results';

  let { r }: { r: Results } = $props();

  function panels(r: Results): Panel[] {
    const i = r.iView;
    const nt = r.turnOffsets[r.turnOffsets.length - 1];
    const nn = r.nodeOffsets[r.nodeOffsets.length - 1];
    const maxN = Math.max(...r.vnaCoils.map((c) => c.n_turns));
    const turns = Array.from({ length: maxN }, (_, n) => n + 1);
    const nodes = Array.from({ length: maxN + 1 }, (_, n) => n);
    const cur: (number | null)[][] = [turns];
    const volt: (number | null)[][] = [nodes];
    const series = r.vnaCoils.map((c, k) => {
      const t0 = r.turnOffsets[k];
      const n0 = r.nodeOffsets[k];
      cur.push(turns.map((n) => (n <= c.n_turns ? abs(at(r.driveTurnI, i * nt + t0 + n - 1)) : null)));
      volt.push(nodes.map((n) => (n <= c.n_turns ? abs(at(r.driveNodeV, i * nn + n0 + n)) : null)));
      const style = COIL_STYLES[coilName(r.vnaPair, r.setupIndex, k) === 'A' ? 0 : 1];
      return {
        label: `coil ${coilName(r.vnaPair, r.setupIndex, k)}`,
        ...style,
        width: 1.5,
        points: { show: true, size: 6, fill: style.stroke },
      };
    });
    return [
      { data: cur, series, height: 190, yLog: true, xInt: true, xLabel: 'turn', yLabel: '|I| [A peak]',
        yTicks: 'si' },
      { data: volt, series: series.map((s) => ({ ...s })), height: 190, xInt: true, xLabel: 'turn / node index (0 = start terminal)',
        yLabel: '|V| [V peak]', yTicks: 'si', legend: false },
    ];
  }
</script>

<h3 class="plot-title">
  {r.params.vna_setup}, {driveLabel(r)} at P1, {si(r.fView, 'Hz')}
</h3>
<div class="chart" {@attach charts(panels(r))}></div>
