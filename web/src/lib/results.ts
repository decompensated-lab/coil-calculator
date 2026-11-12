// Typed view of the arrays app::call returns, plus complex and number-formatting helpers.
import { type Arr, type PairParams, type Params, type Raw, VNA_SETUPS } from './protocol';

export interface Complex {
  re: number;
  im: number;
}
export const abs = (z: Complex) => Math.hypot(z.re, z.im);
export const deg = (z: Complex) => (Math.atan2(z.im, z.re) * 180) / Math.PI;
export const mul = (a: Complex, b: Complex): Complex => ({
  re: a.re * b.re - a.im * b.im,
  im: a.re * b.im + a.im * b.re,
});
export const div = (a: Complex, b: Complex): Complex => {
  const d = b.re * b.re + b.im * b.im;
  return { re: (a.re * b.re + a.im * b.im) / d, im: (a.im * b.re - a.re * b.im) / d };
};

/** Element `i` (flat row-major index) of a complex array. */
export const at = (a: Arr, i: number): Complex => ({ re: a.data[2 * i], im: a.data[2 * i + 1] });

/** One coil, SI units (the coil-table columns of app.rs). */
export interface Coil {
  wire_d: number;
  pitch: number;
  former_d: number;
  n_turns: number;
  position: [number, number, number];
  insulation_d: number;
  former: { wall: number; overhang: number } | null;
  length: number;
  mean_radius: number;
  wire_length: number;
}

function coils(a: Arr): Coil[] {
  return Array.from({ length: a.shape[0] }, (_, i) => {
    const r = a.data.subarray(19 * i, 19 * (i + 1));
    const mean_radius = (r[2] + r[11]) / 2;
    return {
      wire_d: r[0],
      pitch: r[1],
      former_d: r[2],
      n_turns: r[3],
      position: [r[4], r[5], r[6]],
      insulation_d: r[11],
      former: r[14] ? { wall: r[15], overhang: r[18] } : null,
      length: r[3] * r[1],
      mean_radius,
      wire_length: r[3] * Math.hypot(2 * Math.PI * mean_radius, r[1]),
    };
  });
}

export function view(raw: Raw, params: Params) {
  const arr = (k: string) => raw[k] as Arr;
  const real = (k: string) => arr(k).data;
  const [iView, vPlus, vnaPair, mStatic, kStatic, electricFraction] = real('scalars');
  const freqs = real('freqs');
  const nf = freqs.length;
  const perCoil = (k: string) => (c: number) => real(k).subarray(c * nf, (c + 1) * nf);
  const vnaCoils = coils(arr('vna_coils'));
  const offsets = (extra: number) =>
    vnaCoils.reduce((o, c) => [...o, o[o.length - 1] + c.n_turns + extra], [0]);
  return {
    params,
    coils: coils(arr('coils')),
    vnaCoils,
    /** Turn and node index ranges of each VNA coil: `[off[k], off[k + 1])`. */
    turnOffsets: offsets(0),
    nodeOffsets: offsets(1),
    setupIndex: VNA_SETUPS.indexOf(params.vna_setup),
    freqs,
    iView,
    fView: freqs[iView],
    /** (F, C, C) */
    z: arr('z'),
    lDc: real('l_dc'),
    lF: perCoil('l_f'),
    rF: perCoil('r_f'),
    srfNet: real('srf_net'),
    qSrf: real('q_srf'),
    rpSrf: real('rp_srf'),
    srfHere: real('srf_here'),
    srfMedhurst: real('srf_medhurst'),
    cMedhurst: real('c_medhurst'),
    srfVacuum: real('srf_vacuum'),
    vnaPair: vnaPair === 1,
    /** (F, 2, 2) */
    s: arr('s'),
    /** (F, 2) */
    drivePortI: arr('drive_port_i'),
    vPlus,
    /** Available source power at port 1 [dBm]: as set, or what the set current needs. */
    pDbm:
      params.drive === 'source power'
        ? params.p_dbm
        : 10 * Math.log10(vPlus ** 2 / (2 * params.z0) / 1e-3),
    /** (F, T) turn currents and (F, Nn) node voltages for the VNA drive. */
    driveTurnI: arr('drive_turn_i'),
    driveNodeV: arr('drive_node_v'),
    fieldX: real('field_x'),
    fieldZ: real('field_z'),
    /** (nz, nx, 3) complex B [T] in the plane y = 0. */
    fieldB: arr('field_b'),
    lineZ: real('line_z'),
    bzZ: arr('bz_z'),
    bzZUniform: arr('bz_z_uniform'),
    lineX: real('line_x'),
    bzX: arr('bz_x'),
    bzXUniform: arr('bz_x_uniform'),
    mStatic,
    kStatic,
    electricFraction,
    warnings: raw.warnings as string[],
  };
}
export type Results = ReturnType<typeof view>;

/** The drive level as it was set, for plot titles (`Results.drive_label`). */
export const driveLabel = (r: Results) =>
  r.params.drive === 'source power' ? `${g(r.params.p_dbm, 6)} dBm` : `${g(r.params.i_drive_a, 6)} A`;

/** Coil `k` at the view frequency: input impedance (other coil open) and what follows. */
export function coilAtView(r: Results, k: number) {
  const nc = r.coils.length;
  const w = 2 * Math.PI * r.fView;
  const z = at(r.z, (r.iView * nc + k) * nc + k);
  const rAc = r.rF(k)[r.iView];
  return { z, rAc, lEff: z.im / w, qL: (w * r.lDc[k]) / rAc };
}

/** Python's `format(x, f".{digits}g")`. */
export function g(x: number, digits = 4): string {
  if (!Number.isFinite(x)) return '—';
  if (x === 0) return '0';
  const strip = (s: string) => (s.includes('.') ? s.replace(/\.?0+$/, '') : s);
  const exp = Math.floor(Math.log10(Math.abs(Number(x.toPrecision(digits)))));
  if (exp < -4 || exp >= digits) {
    const [m, e] = x.toExponential(digits - 1).split('e');
    return `${strip(m)}e${e[0]}${e.slice(1).padStart(2, '0')}`;
  }
  return strip(x.toFixed(Math.max(digits - 1 - exp, 0)));
}

const PREFIX: [number, string][] = [
  [1e9, 'G'], [1e6, 'M'], [1e3, 'k'], [1, ''], [1e-3, 'm'], [1e-6, 'µ'], [1e-9, 'n'], [1e-12, 'p'],
];

/** SI prefix formatting, e.g. `si(2.3e-6, 'H') -> '2.3 µH'` (gui/richtext.py `si`). */
export function si(x: number, unit: string, digits = 4): string {
  if (!Number.isFinite(x)) return '—';
  if (x === 0) return `0 ${unit}`;
  for (const [scale, p] of PREFIX) {
    if (Math.abs(x) >= scale * 0.9995) return `${g(x / scale, digits)} ${p}${unit}`;
  }
  return `${g(x, digits)} ${unit}`;
}

/** `f"{x:+.1%}"`. */
export const pct = (x: number) => `${x >= 0 ? '+' : ''}${(100 * x).toFixed(1)}%`;

/** Typed view of the wire-pair response (rust/crates/core/src/pair.rs). */
export function pairView(raw: Raw, params: PairParams) {
  const arr = (k: string) => raw[k] as Arr;
  const real = (k: string) => arr(k).data;
  const [nTerms, converged, spacing, cBare, cUniform, cEff] = real('scalars');
  const w = real('wires');
  const wire = (k: number) => ({ a: w[4 * k], b: w[4 * k + 1] });
  return {
    params,
    /** C' − jC'' [F/m]. */
    c: at(arr('c'), 0),
    /** Conductor potentials [V] for 1 V across the pair. */
    v: [at(arr('v'), 0), at(arr('v'), 1)],
    wires: [wire(0), wire(1)],
    nTerms,
    converged: converged === 1,
    spacing,
    cBare,
    cUniform,
    cEff,
    gap: real('gap'),
    sweepExact: real('sweep_exact'),
    sweepBare: real('sweep_bare'),
    sweepUniform: real('sweep_uniform'),
    sweepEff: real('sweep_eff'),
    fieldX: real('field_x'),
    fieldY: real('field_y'),
    /** (ny, nx) potential [V]. */
    phi: real('phi'),
  };
}
export type PairResults = ReturnType<typeof pairView>;
