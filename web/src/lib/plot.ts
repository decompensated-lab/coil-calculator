// Stacked uPlot panels with the app's styling (gui/plots.py `_style`): theme colours from CSS
// variables, SI tick labels, marker lines/bands, a shared cursor, and resizing with the
// container. Use as `{@attach charts(panels, key)}` on an empty element.
import uPlot from 'uplot';
import 'uplot/dist/uPlot.min.css';
import { g, si } from './results';

export const BLUE = '#2a78d6';
export const ORANGE = '#eb6834';
export const AQUA = '#1baf7a';
export const COIL_COLORS = [BLUE, ORANGE];

/** A vertical (`x`) or horizontal (`y`) line, or a vertical band `x..x1`. */
export interface Mark {
  x?: number;
  x1?: number;
  y?: number;
  color: string; // 'muted' = theme colour
  dash?: number[];
  alpha?: number;
  label?: string;
}

export interface Panel {
  /** `[x, ...ys]`; `null` leaves a gap. */
  data: (number | null)[][];
  series: uPlot.Series[];
  height: number;
  xLog?: boolean;
  yLog?: boolean;
  yRange?: [number, number];
  xLabel?: string;
  yLabel?: string;
  /** Hide the x tick labels (upper panel of a shared-x stack). */
  xHidden?: boolean;
  /** Tick labels: SI prefixes (default for log axes) or plain numbers. */
  xTicks?: 'si' | 'plain';
  yTicks?: 'si' | 'plain';
  marks?: Mark[];
  legend?: boolean;
  title?: string;
}

const ticks = (kind: 'si' | 'plain') => (_u: uPlot, v: number[]) =>
  v.map((x) => (x == null ? '' : kind === 'si' ? si(x, '', 3).trim() : g(x, 4)));

export function charts(panels: Panel[], syncKey?: string) {
  return (node: HTMLElement) => {
    const css = getComputedStyle(node);
    const muted = css.getPropertyValue('--muted').trim();
    const grid = css.getPropertyValue('--grid').trim();
    const ink = css.getPropertyValue('--ink').trim();
    const axis = { stroke: muted, grid: { stroke: grid, width: 1 }, ticks: { stroke: grid } };
    const plots = panels.map((p) => {
      const draw = (u: uPlot) => {
        const { ctx, bbox } = u;
        for (const m of p.marks ?? []) {
          ctx.save();
          ctx.strokeStyle = ctx.fillStyle = m.color === 'muted' ? muted : m.color;
          ctx.setLineDash((m.dash ?? []).map((d) => d * devicePixelRatio));
          ctx.lineWidth = devicePixelRatio;
          ctx.globalAlpha = m.alpha ?? 1;
          if (m.x != null && m.x1 != null) {
            const [a, b] = [u.valToPos(m.x, 'x', true), u.valToPos(m.x1, 'x', true)];
            const lo = Math.max(Math.min(a, b), bbox.left);
            const hi = Math.min(Math.max(a, b), bbox.left + bbox.width);
            if (hi > lo) ctx.fillRect(lo, bbox.top, hi - lo, bbox.height);
            if (m.label) {
              ctx.globalAlpha = 1;
              ctx.font = `${11 * devicePixelRatio}px system-ui, sans-serif`;
              ctx.textAlign = 'center';
              ctx.fillText(m.label, (lo + hi) / 2, bbox.top + 14 * devicePixelRatio);
            }
          } else if (m.x != null) {
            const px = u.valToPos(m.x, 'x', true);
            if (px >= bbox.left && px <= bbox.left + bbox.width) {
              ctx.beginPath();
              ctx.moveTo(px, bbox.top);
              ctx.lineTo(px, bbox.top + bbox.height);
              ctx.stroke();
            }
          } else if (m.y != null) {
            const py = u.valToPos(m.y, 'y', true);
            if (py >= bbox.top && py <= bbox.top + bbox.height) {
              ctx.beginPath();
              ctx.moveTo(bbox.left, py);
              ctx.lineTo(bbox.left + bbox.width, py);
              ctx.stroke();
            }
          }
          ctx.restore();
        }
      };
      const xKind = p.xTicks ?? (p.xLog ? 'si' : 'plain');
      const yKind = p.yTicks ?? (p.yLog ? 'si' : 'plain');
      const exact = (_u: uPlot, lo: number, hi: number): uPlot.Range.MinMax => [lo, hi];
      const opts: uPlot.Options = {
        width: node.clientWidth,
        height: p.height,
        title: p.title,
        cursor: syncKey ? { sync: { key: syncKey } } : {},
        legend: { show: p.legend ?? true },
        // the data range exactly (uPlot would round a log range out to whole decades)
        scales: {
          x: { time: false, distr: p.xLog ? 3 : 1, range: exact },
          y: p.yRange
            ? { auto: false, range: p.yRange, distr: p.yLog ? 3 : 1 }
            : { distr: p.yLog ? 3 : 1 },
        },
        series: [{ label: p.xLabel?.replace(/\s*\(.*\)$/, '') ?? 'x' }, ...p.series],
        axes: [
          { ...axis, label: p.xHidden ? undefined : p.xLabel, values: p.xHidden ? (_u, v) => v.map(() => '') : ticks(xKind) },
          { ...axis, label: p.yLabel, values: ticks(yKind), size: 64 },
        ],
        hooks: { draw: [draw] },
      };
      const u = new uPlot(opts, p.data as uPlot.AlignedData, node);
      u.root.style.color = ink;
      return u;
    });
    const ro = new ResizeObserver(() => {
      plots.forEach((u, i) => u.setSize({ width: node.clientWidth, height: panels[i].height }));
    });
    ro.observe(node);
    return () => {
      ro.disconnect();
      plots.forEach((u) => u.destroy());
    };
  };
}

/** Name of VNA coil `k` ('A' or 'B'): thru setups measure one coil alone. */
export function coilName(vnaPair: boolean, setupIndex: number, k: number): 'A' | 'B' {
  if (vnaPair) return k ? 'B' : 'A';
  return setupIndex <= 2 ? 'A' : 'B';
}
