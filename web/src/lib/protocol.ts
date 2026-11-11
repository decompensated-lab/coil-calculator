// Parameters, defaults and the byte format of `app::call` (rust/crates/core/src/app.rs).
// Mirrors coilcal/gui/model.py's Params and coilcal/materials.py; tests/port/test_web.py checks
// that the defaults and the encoding match the Python reference.
// No imports, so Node can run this file directly (type stripping).

export interface Dielectric {
  eps_r: number;
  tan_delta: number;
}

/** Dielectric presets around 1 MHz (`coilcal.materials.Material`); null = no fixed values. */
export const MATERIALS = {
  'air / none': { eps_r: 1.0, tan_delta: 0.0 },
  PTFE: { eps_r: 2.1, tan_delta: 0.0002 },
  polyethylene: { eps_r: 2.3, tan_delta: 0.0003 },
  polypropylene: { eps_r: 2.25, tan_delta: 0.0005 },
  'enamel (PU / polyester-imide)': { eps_r: 3.6, tan_delta: 0.01 },
  'polyimide (Kapton)': { eps_r: 3.4, tan_delta: 0.003 },
  'silicone rubber': { eps_r: 3.0, tan_delta: 0.002 },
  'PVC (flexible)': { eps_r: 3.5, tan_delta: 0.05 },
  'PVC (rigid pipe)': { eps_r: 3.0, tan_delta: 0.012 },
  'acrylic (PMMA)': { eps_r: 2.6, tan_delta: 0.015 },
  polycarbonate: { eps_r: 2.9, tan_delta: 0.01 },
  'acetal (POM)': { eps_r: 3.7, tan_delta: 0.005 },
  'PLA (3-D print, solid)': { eps_r: 2.8, tan_delta: 0.01 },
  'FR4 / G10 epoxy-glass': { eps_r: 4.4, tan_delta: 0.02 },
  custom: null,
} as const satisfies Record<string, Dielectric | null>;
export type Material = keyof typeof MATERIALS;

// Enum-like options: the value is the label, the code sent to Rust is the index.
export const GROUNDINGS = ['floating', 'start', 'end'] as const;
export const GAP_REFS = ['edge-to-edge', 'centre-to-centre'] as const;
export const COUPLINGS = ['full', 'magnetic', 'electric'] as const;
export const VNA_SETUPS = [
  'A on P1, B on P2 (coupling)',
  'A series-thru (P1–A–P2)',
  'A shunt-thru (A to ground)',
  'B series-thru (P1–B–P2)',
  'B shunt-thru (B to ground)',
] as const;
export type Grounding = (typeof GROUNDINGS)[number];
export type GapRef = (typeof GAP_REFS)[number];
export type Coupling = (typeof COUPLINGS)[number];
export type VnaSetup = (typeof VNA_SETUPS)[number];

export interface CoilParams {
  wire_d_mm: number;
  pitch_mm: number;
  former_d_mm: number;
  turns: number;
  ground: Grounding;
  /** Outer Ø over the insulation (= wire Ø for bare wire). */
  insulation_d_mm: number;
  insulation_material: Material;
  insulation: Dielectric;
  former_wall_mm: number;
  former_overhang_mm: number;
  /** 'air / none' = no former. */
  former_material: Material;
  former: Dielectric;
}

export interface Params {
  a: CoilParams;
  b: CoilParams;
  b_enabled: boolean;
  gap_ref: GapRef;
  gap_mm: number;
  offset_mm: number;
  f_min_mhz: number;
  f_max_mhz: number;
  n_freq: number;
  f_view_mhz: number;
  z_load: number;
  r_factor: number;
  coupling: Coupling;
  vna_setup: VnaSetup;
  z0: number;
  p_dbm: number;
  /** Height of the Bz(x) profile (0 = centre of coil A). */
  x_line_z_mm: number;
}

const preset = (m: Material): Dielectric => ({ ...MATERIALS[m]! });

export function defaultCoil(turns = 10): CoilParams {
  return {
    wire_d_mm: 1.0,
    pitch_mm: 2.0,
    former_d_mm: 150.0,
    turns,
    ground: 'end',
    insulation_d_mm: 1.06,
    insulation_material: 'enamel (PU / polyester-imide)',
    insulation: preset('enamel (PU / polyester-imide)'),
    former_wall_mm: 3.0,
    former_overhang_mm: 10.0,
    former_material: 'acrylic (PMMA)',
    former: preset('acrylic (PMMA)'),
  };
}

export function defaultParams(): Params {
  return {
    a: defaultCoil(10),
    b: defaultCoil(5),
    b_enabled: true,
    gap_ref: 'edge-to-edge',
    gap_mm: 50.0,
    offset_mm: 0.0,
    f_min_mhz: 0.1,
    f_max_mhz: 30.0,
    n_freq: 300,
    f_view_mhz: 5.0,
    z_load: 50.0,
    r_factor: 1.0,
    coupling: 'full',
    vna_setup: VNA_SETUPS[0],
    z0: 50.0,
    p_dbm: 0.0,
    x_line_z_mm: 0.0,
  };
}

/** Parameter name -> value as `Params::decode` expects them (empty inputs become NaN). */
export function flatten(p: Params): Record<string, number> {
  const num = (v: number | null | undefined) => (typeof v === 'number' ? v : NaN);
  const out: Record<string, number> = {};
  for (const [k, c] of [['a', p.a], ['b', p.b]] as const) {
    for (const f of ['wire_d_mm', 'pitch_mm', 'former_d_mm', 'turns', 'insulation_d_mm',
      'former_wall_mm', 'former_overhang_mm'] as const) {
      out[`${k}.${f}`] = num(c[f]);
    }
    out[`${k}.ground`] = GROUNDINGS.indexOf(c.ground);
    out[`${k}.insulation_eps_r`] = num(c.insulation.eps_r);
    out[`${k}.insulation_tan_delta`] = num(c.insulation.tan_delta);
    out[`${k}.former_eps_r`] = num(c.former.eps_r);
    out[`${k}.former_tan_delta`] = num(c.former.tan_delta);
  }
  for (const f of ['gap_mm', 'offset_mm', 'f_min_mhz', 'f_max_mhz', 'n_freq', 'f_view_mhz',
    'z_load', 'r_factor', 'z0', 'p_dbm', 'x_line_z_mm'] as const) {
    out[f] = num(p[f]);
  }
  out.b_enabled = p.b_enabled ? 1 : 0;
  out.gap_ref = GAP_REFS.indexOf(p.gap_ref);
  out.coupling = COUPLINGS.indexOf(p.coupling);
  out.vna_setup = VNA_SETUPS.indexOf(p.vna_setup);
  return out;
}

export function encode(p: Params): Uint8Array {
  const values = Object.entries(flatten(p));
  const utf8 = new TextEncoder();
  const names = values.map(([n]) => utf8.encode(n));
  const size = 4 + names.reduce((s, n) => s + 4 + n.length + 8, 0);
  const buf = new Uint8Array(size);
  const dv = new DataView(buf.buffer);
  let pos = 0;
  dv.setUint32(pos, values.length, true);
  pos += 4;
  values.forEach(([, v], i) => {
    dv.setUint32(pos, names[i].length, true);
    buf.set(names[i], pos + 4);
    pos += 4 + names[i].length;
    dv.setFloat64(pos, v, true);
    pos += 8;
  });
  return buf;
}

/** A real or complex (re, im interleaved) row-major array. */
export interface Arr {
  shape: number[];
  complex: boolean;
  data: Float64Array;
}
export type Raw = Record<string, Arr | string[]>;
export type Response = { ok: true; raw: Raw } | { ok: false; error: string };

export function decode(buf: Uint8Array): Response {
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  const utf8 = new TextDecoder();
  let pos = 0;
  const u32 = () => ((pos += 4), dv.getUint32(pos - 4, true));
  const text = (n: number) => ((pos += n), utf8.decode(buf.subarray(pos - n, pos)));
  if (buf[pos++] !== 0) return { ok: false, error: text(u32()) };
  const raw: Raw = {};
  for (let i = u32(); i > 0; i--) {
    const name = text(u32());
    const kind = buf[pos++];
    const shape = Array.from({ length: buf[pos++] }, u32);
    const n = shape.reduce((a, b) => a * b, 1);
    if (kind === 2) {
      raw[name] = Array.from({ length: n }, () => text(u32()));
    } else {
      const len = n * (kind === 1 ? 2 : 1);
      // copy: Float64Array needs 8-byte alignment
      const data = new Float64Array(buf.slice(pos, pos + 8 * len).buffer);
      pos += 8 * len;
      raw[name] = { shape, complex: kind === 1, data };
    }
  }
  return { ok: true, raw };
}

/** The exports of coilcal_web.wasm (rust/crates/web). */
export interface Exports {
  memory: WebAssembly.Memory;
  alloc(len: number): number;
  dealloc(ptr: number, len: number): void;
  call(ptr: number, len: number): number;
}

/** One request through the module's memory. */
export function callWasm(ex: Exports, req: Uint8Array): Uint8Array {
  const p = ex.alloc(req.length);
  new Uint8Array(ex.memory.buffer, p, req.length).set(req);
  const r = ex.call(p, req.length);
  ex.dealloc(p, req.length);
  const len = new DataView(ex.memory.buffer).getUint32(r, true);
  const resp = new Uint8Array(ex.memory.buffer, r + 4, len).slice();
  ex.dealloc(r, len + 4);
  return resp;
}
