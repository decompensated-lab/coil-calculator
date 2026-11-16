// Stacked uPlot panels with the app's styling (gui/plots.py `_style`): theme colours from CSS
// variables, SI tick labels, marker lines/bands, a shared cursor, and resizing with the
// container. Use as `{@attach charts(panels, options)}` on an empty `.chart` element. A legend
// goes above its panel and its hover values have a fixed format and width, so nothing moves
// under the cursor. The panels share the height the element is given (app.css `.chart`), less
// the legends, in proportion to their `height`.
import uPlot from 'uplot';
import 'uplot/dist/uPlot.min.css';
import { g, si } from './results';

// Traces. The data is ink (the darkest line in a plot); the second and third trace differ
// from it and from each other in lightness as well as hue, and carry a dash as a second cue,
// so they survive colour blindness and a gray printout (measured with the palette audit of
// the UI studies: OKLab distance >= 0.10 for every pair under every kind of dichromacy).
// Blue, orange, cyan, green, yellow and red have jobs in the interface and are never a trace.
export const INK = '#0e1318'; // = --fg in app.css
export const MAGENTA = '#e0489f';
export const TEAL = '#00695f';
export const GRAY = '#757b82'; // references and estimates, always dotted
export const DASH = [7, 3];
export const DASH_DOT = [7, 3, 2, 3];
export const DOTTED = [2, 3];
/** Line style of coil A and coil B. */
export const COIL_STYLES = [{ stroke: INK }, { stroke: MAGENTA, dash: DASH }];
export const COIL_COLORS = [INK, MAGENTA];
const FONT = '11px "JetBrains Mono", monospace';

/** A vertical (`x`) or horizontal (`y`) line, a vertical band `x..x1`, or a point (`x`, `y`). */
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
  /** Name of x in the legend (default: `xLabel` without its remark in parentheses). */
  xName?: string;
  yLabel?: string;
  /** Hide the x tick labels (upper panel of a shared-x stack). */
  xHidden?: boolean;
  /** Only whole-number x ticks (turn numbers). */
  xInt?: boolean;
  /** Tick labels: SI prefixes (default for log axes) or plain numbers. */
  xTicks?: 'si' | 'plain';
  yTicks?: 'si' | 'plain';
  marks?: Mark[];
  legend?: boolean;
  title?: string;
}

const ticks = (kind: 'si' | 'plain') => (_u: uPlot, v: number[]) =>
  v.map((x) => (x == null ? '' : kind === 'si' ? si(x, '', 3).trim() : g(x, 4)));
/** Legend value under the cursor, in the notation of the axis. */
const value = (kind: 'si' | 'plain') => (_u: uPlot, v: number | null) =>
  v == null ? '--' : kind === 'si' ? si(v, '', 4).trim() : g(v, 4);

export interface ChartOptions {
  /** Panels with the same key share the cursor. */
  sync?: string;
  /** Gets the x value of a plain click (a drag still zooms, a double click resets). */
  onpick?: (x: number) => void;
}

export function charts(panels: Panel[], { sync, onpick }: ChartOptions = {}) {
  return (node: HTMLElement) => {
    const css = getComputedStyle(node);
    const muted = css.getPropertyValue('--dim').trim();
    const grid = css.getPropertyValue('--plot-grid').trim();
    const ink = css.getPropertyValue('--fg').trim();
    const axis = {
      stroke: muted, font: FONT, labelFont: FONT, labelSize: 18,
      grid: { stroke: grid, width: 1 }, ticks: { stroke: muted, width: 1, size: 4 },
    };
    const total = panels.reduce((sum, p) => sum + p.height, 0);
    node.style.setProperty('--chart-h', String(total));
    const legends: HTMLElement[] = [];
    const height = (p: Panel) => {
      const free = node.clientHeight - legends.reduce((sum, el) => sum + el.offsetHeight, 0);
      return Math.max(Math.floor((free * p.height) / total), 1);
    };
    const plots = panels.map((p) => {
      const draw = (u: uPlot) => {
        const { ctx, bbox } = u;
        for (const m of p.marks ?? []) {
          ctx.save();
          ctx.strokeStyle = ctx.fillStyle = m.color === 'muted' ? muted : m.color;
          ctx.setLineDash((m.dash ?? []).map((d) => d * devicePixelRatio));
          ctx.lineWidth = devicePixelRatio;
          ctx.globalAlpha = m.alpha ?? 1;
          if (m.x != null && m.y != null) {
            const [px, py] = [u.valToPos(m.x, 'x', true), u.valToPos(m.y, 'y', true)];
            ctx.beginPath();
            ctx.arc(px, py, 5 * devicePixelRatio, 0, 2 * Math.PI);
            ctx.fill();
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = 2 * devicePixelRatio;
            ctx.stroke();
          } else if (m.x != null && m.x1 != null) {
            const [a, b] = [u.valToPos(m.x, 'x', true), u.valToPos(m.x1, 'x', true)];
            const lo = Math.max(Math.min(a, b), bbox.left);
            const hi = Math.min(Math.max(a, b), bbox.left + bbox.width);
            if (hi > lo) ctx.fillRect(lo, bbox.top, hi - lo, bbox.height);
            if (m.label) {
              ctx.globalAlpha = 1;
              ctx.fillStyle = ink;
              ctx.font = `${11 * devicePixelRatio}px "JetBrains Mono", monospace`;
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
        // the ink rule that closes the plot area, over the grid and the traces
        ctx.save();
        ctx.strokeStyle = ink;
        ctx.lineWidth = devicePixelRatio;
        const half = devicePixelRatio / 2;
        ctx.strokeRect(bbox.left + half, bbox.top + half, bbox.width - 2 * half, bbox.height - 2 * half);
        ctx.restore();
      };
      const dashName = (_u: uPlot, i: number) => {
        const d = p.series[i - 1]?.dash;
        return !d ? 'solid' : d[0] <= 2 ? 'dotted' : 'dashed';
      };
      const xKind = p.xTicks ?? (p.xLog ? 'si' : 'plain');
      const yKind = p.yTicks ?? (p.yLog ? 'si' : 'plain');
      const exact = (_u: uPlot, lo: number, hi: number): uPlot.Range.MinMax => [lo, hi];
      const opts: uPlot.Options = {
        width: node.clientWidth,
        height: height(p),
        title: p.title,
        cursor: sync ? { sync: { key: sync } } : {},
        legend: {
          show: p.legend ?? true,
          mount: (_u, el) => {
            legends.push(el);
            node.append(el); // before the panel's own root, which uPlot appends after this
          },
          markers: { width: 2, dash: dashName },
        },
        // the data range exactly (uPlot would round a log range out to whole decades)
        scales: {
          x: { time: false, distr: p.xLog ? 3 : 1, range: exact },
          y: p.yRange
            ? { auto: false, range: p.yRange, distr: p.yLog ? 3 : 1 }
            : { distr: p.yLog ? 3 : 1 },
        },
        series: [
          { label: p.xName ?? p.xLabel?.replace(/\s*\(.*\)$/, '') ?? 'x', value: value(xKind) },
          ...p.series.map((s) => ({ value: value(yKind), ...s })),
        ],
        axes: [
          {
            ...axis,
            size: p.xHidden ? 8 : 24,
            label: p.xHidden ? undefined : p.xLabel,
            values: p.xHidden ? (_u, v) => v.map(() => '') : ticks(xKind),
            ...(p.xInt ? { incrs: [1, 2, 5, 10, 20, 50, 100] } : {}),
          },
          { ...axis, label: p.yLabel, values: ticks(yKind), size: 46 },
        ],
        hooks: { draw: [draw] },
      };
      const u = new uPlot(opts, p.data as uPlot.AlignedData, node);
      u.root.style.color = ink;
      if (onpick) {
        // a plain click picks; wait out a possible double click (it resets the zoom)
        let down = 0;
        let timer = 0;
        u.over.style.cursor = 'pointer';
        u.over.addEventListener('mousedown', (e) => (down = e.clientX));
        u.over.addEventListener('click', (e) => {
          clearTimeout(timer);
          if (e.detail > 1 || Math.abs(e.clientX - down) >= 3) return;
          const x = u.posToVal(u.cursor.left!, 'x');
          timer = setTimeout(() => onpick(x), 250);
        });
      }
      return u;
    });
    // the element's size is given from outside (flex), so resizing the panels cannot loop;
    // the first call also accounts for the legends, which were not all there at creation
    const ro = new ResizeObserver(() => {
      plots.forEach((u, i) => u.setSize({ width: node.clientWidth, height: height(panels[i]) }));
    });
    ro.observe(node);
    return () => {
      ro.disconnect();
      plots.forEach((u) => u.destroy());
      legends.forEach((el) => el.remove());
    };
  };
}

/** Name of VNA coil `k` ('A' or 'B'): thru setups measure one coil alone. */
export function coilName(vnaPair: boolean, setupIndex: number, k: number): 'A' | 'B' {
  if (vnaPair) return k ? 'B' : 'A';
  return setupIndex <= 2 ? 'A' : 'B';
}
