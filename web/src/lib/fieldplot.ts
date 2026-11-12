// Helpers for the equal-aspect SVG plots (cross-section, side view, wire-pair field): a
// "Blues" colour map, heat-map images, log scaling, nice ticks, streamlines and contours.

/** matplotlib's "Blues", sampled at 9 stops. */
const BLUES = [
  [247, 251, 255], [222, 235, 247], [198, 219, 239], [158, 202, 225], [107, 174, 214],
  [66, 146, 198], [33, 113, 181], [8, 81, 156], [8, 48, 107],
];

/** Colour of `t` in [0, 1] (clamped) as [r, g, b]. */
export function blues(t: number): [number, number, number] {
  const x = Math.min(Math.max(t, 0), 1) * (BLUES.length - 1);
  const i = Math.min(Math.floor(x), BLUES.length - 2);
  const f = x - i;
  return [0, 1, 2].map((c) => Math.round(BLUES[i][c] + f * (BLUES[i + 1][c] - BLUES[i][c]))) as [
    number,
    number,
    number,
  ];
}
export const css = ([r, g, b]: [number, number, number]) => `rgb(${r} ${g} ${b})`;

/** Log scaling to [0, 1] between `lo` and `hi`. */
export const logNorm = (lo: number, hi: number) => (v: number) =>
  Math.log(v / lo) / Math.log(hi / lo);

/** The `q`-th percentile (0..100) of the finite values. */
export function percentile(values: ArrayLike<number>, q: number): number {
  const v = Array.from(values).filter(Number.isFinite).sort((a, b) => a - b);
  const x = (q / 100) * (v.length - 1);
  const i = Math.floor(x);
  return i + 1 < v.length ? v[i] + (x - i) * (v[i + 1] - v[i]) : v[i];
}

/** PNG data URL of a row-major `ny × nx` grid; NaN cells are transparent. Row 0 is the top
 *  of the image, which a `Frame` (y flipped) shows at the bottom, i.e. at the lowest y. */
export function heatmap(values: ArrayLike<number>, nx: number, ny: number, t: (v: number) => number) {
  const canvas = document.createElement('canvas');
  canvas.width = nx;
  canvas.height = ny;
  const ctx = canvas.getContext('2d')!;
  const img = ctx.createImageData(nx, ny);
  for (let j = 0; j < ny; j++) {
    for (let i = 0; i < nx; i++) {
      const v = values[j * nx + i];
      const o = 4 * (j * nx + i);
      if (Number.isNaN(v)) continue;
      const [r, g, b] = blues(t(v));
      img.data.set([r, g, b, 255], o);
    }
  }
  ctx.putImageData(img, 0, 0);
  return canvas.toDataURL();
}

/** About `n` round tick values covering [lo, hi]. */
export function ticks(lo: number, hi: number, n = 6): number[] {
  const raw = (hi - lo) / n;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= raw)!;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9 * step; v += step) {
    out.push(Math.abs(v) < 1e-9 * step ? 0 : v);
  }
  return out;
}

/** Decades (1, 10, 100, ...) within [lo, hi]. */
export function decades(lo: number, hi: number): number[] {
  const out = [];
  for (let e = Math.ceil(Math.log10(lo)); 10 ** e <= hi * (1 + 1e-12); e++) out.push(10 ** e);
  return out;
}

/**
 * Field lines of the vector field (u, v) on the regular grid x × y (row-major, row = y), in the
 * spirit of matplotlib's streamplot: lines start from seeds spread over a coarse occupancy grid,
 * are traced both ways along the unit direction (RK2), and stop where another line already
 * passed, at the border, or where the field vanishes. Returns polylines in data coordinates.
 */
export function streamlines(
  x: ArrayLike<number>,
  y: ArrayLike<number>,
  u: ArrayLike<number>,
  v: ArrayLike<number>,
  density = 1.3,
): [number, number][][] {
  const nx = x.length;
  const ny = y.length;
  const [x0, y0] = [x[0], y[0]];
  const [dx, dy] = [(x[nx - 1] - x0) / (nx - 1), (y[ny - 1] - y0) / (ny - 1)];
  const nm = Math.round(30 * density); // occupancy grid, as matplotlib
  const mask = new Uint8Array(nm * nm);
  // grid coordinates (0..nx-1, 0..ny-1) <-> mask cells
  const cell = (gx: number, gy: number) =>
    Math.min(nm - 1, Math.floor((gy / (ny - 1)) * nm)) * nm + Math.min(nm - 1, Math.floor((gx / (nx - 1)) * nm));
  const field = (gx: number, gy: number): [number, number] | null => {
    if (gx < 0 || gy < 0 || gx > nx - 1 || gy > ny - 1) return null;
    const i = Math.min(Math.floor(gx), nx - 2);
    const j = Math.min(Math.floor(gy), ny - 2);
    const [fx, fy] = [gx - i, gy - j];
    const at = (a: ArrayLike<number>) =>
      (a[j * nx + i] * (1 - fx) + a[j * nx + i + 1] * fx) * (1 - fy) +
      (a[(j + 1) * nx + i] * (1 - fx) + a[(j + 1) * nx + i + 1] * fx) * fy;
    // direction in grid units (cells may not be square)
    const [a, b] = [at(u) / dx, at(v) / dy];
    const s = Math.hypot(a, b);
    return s > 0 && Number.isFinite(s) ? [a / s, b / s] : null;
  };
  const h = 0.3; // step in grid cells
  const maxSteps = 4 * (nx + ny);
  const trace = (gx: number, gy: number, sign: number, cells: Set<number>) => {
    const pts: [number, number][] = [];
    const start = cell(gx, gy);
    for (let n = 0; n < maxSteps; n++) {
      const d1 = field(gx, gy);
      if (!d1) break;
      const d2 = field(gx + 0.5 * h * sign * d1[0], gy + 0.5 * h * sign * d1[1]);
      if (!d2) break;
      gx += h * sign * d2[0];
      gy += h * sign * d2[1];
      const c = cell(gx, gy);
      if (gx < 0 || gy < 0 || gx > nx - 1 || gy > ny - 1) break;
      if (c !== start && !cells.has(c)) {
        if (mask[c]) break;
        cells.add(c);
      }
      pts.push([gx, gy]);
    }
    return pts;
  };
  // seeds: mask cells from the outside in (matplotlib's spiral), skipping occupied ones
  const order: number[] = [];
  for (let ring = 0; ring < nm / 2; ring++) {
    const lo = ring;
    const hi = nm - 1 - ring;
    for (let i = lo; i <= hi; i++) order.push(lo * nm + i, hi * nm + i, i * nm + lo, i * nm + hi);
  }
  const lines: [number, number][][] = [];
  const toData = ([gx, gy]: [number, number]): [number, number] => [x0 + gx * dx, y0 + gy * dy];
  for (const c of new Set(order)) {
    if (mask[c]) continue;
    const gx = ((c % nm) + 0.5) * ((nx - 1) / nm);
    const gy = (Math.floor(c / nm) + 0.5) * ((ny - 1) / nm);
    const cells = new Set([c]);
    const back = trace(gx, gy, -1, cells);
    const fwd = trace(gx, gy, 1, cells);
    const line = [...back.reverse(), [gx, gy] as [number, number], ...fwd];
    if (line.length * h < 0.08 * (nx + ny)) continue; // too short: drop, leave cells free
    for (const k of cells) mask[k] = 1;
    lines.push(line.map(toData));
  }
  return lines;
}

/**
 * Contour line segments of `f` (row-major ny × nx on x × y) at `level` (marching squares;
 * cells with a NaN corner are skipped). Returns an SVG path string in data coordinates.
 */
export function contour(
  x: ArrayLike<number>,
  y: ArrayLike<number>,
  f: ArrayLike<number>,
  level: number,
  fmt: (px: number, py: number) => string,
): string {
  const nx = x.length;
  const ny = y.length;
  let d = '';
  const lerp = (a: number, b: number, fa: number, fb: number) => a + ((level - fa) / (fb - fa)) * (b - a);
  for (let j = 0; j < ny - 1; j++) {
    for (let i = 0; i < nx - 1; i++) {
      const c = [f[j * nx + i], f[j * nx + i + 1], f[(j + 1) * nx + i + 1], f[(j + 1) * nx + i]];
      if (c.some(Number.isNaN)) continue;
      const px = [x[i], x[i + 1], x[i + 1], x[i]];
      const py = [y[j], y[j], y[j + 1], y[j + 1]];
      const cross: [number, number][] = [];
      for (let e = 0; e < 4; e++) {
        const [a, b] = [e, (e + 1) % 4];
        if (c[a] < level !== c[b] < level) {
          cross.push([lerp(px[a], px[b], c[a], c[b]), lerp(py[a], py[b], c[a], c[b])]);
        }
      }
      // 2 crossings: one segment; 4 (saddle): pair them in order
      for (let k = 0; k + 1 < cross.length; k += 2) {
        d += `M${fmt(...cross[k])}L${fmt(...cross[k + 1])}`;
      }
    }
  }
  return d;
}
