//! The app layer: GUI parameters -> everything the app shows. Port of `compute` and the
//! parameter classes of `coilcal/gui/model.py`, plus the input validation that the Python
//! constructors (`Dielectric`, `Former`, `SolenoidCoil`, `check_overlap`) do there.
//!
//! [`call`] is the byte interface used by the browser worker and by the port tests:
//!
//! * request: `u32 count`, then per parameter `u32 name_len, name (UTF-8), f64 value`;
//! * response: `u8 0`, `u32 count`, then per result `u32 name_len, name, u8 kind, u8 ndim,
//!   u32 shape[ndim]`, followed by the data: kind 0 real f64, kind 1 complex (re, im
//!   interleaved), kind 2 UTF-8 text lines (`u32 len, bytes` each, shape = `[lines]`);
//!   or `u8 1`, `u32 len`, error message.
//!
//! All integers and floats are little-endian. Parameter names are listed in [`Params::decode`].

// `!(x > 0.0)` is deliberate throughout: it rejects NaN, as the Python `not x > 0` checks do.
#![allow(clippy::neg_cmp_op_on_partial_ord)]

use crate::c64;
use crate::circuit::{Coupling, End, Network, geomspace};
use crate::field::circle_b;
use crate::geometry::{Coil, Former, Vec3};
use crate::inductance::{ac_resistance, self_capacitance_medhurst, self_inductance, srf_lumped};
use crate::loops::RHO_CU;
use crate::mutual::mutual_inductance;
use crate::vna::{self, ThruMode};

const MM: f64 = 1e-3;

/// εr(1 − j tanδ).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Dielectric {
    pub eps_r: f64,
    pub tan_delta: f64,
}

impl Dielectric {
    pub fn eps(&self) -> c64 {
        c64::new(self.eps_r, -self.eps_r * self.tan_delta)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum GapRef {
    /// 0 = windings end to end (one pitch apart).
    Edge,
    /// 0 = B centred on A (nested).
    Centre,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum VnaSetup {
    Pair,
    ASeries,
    AShunt,
    BSeries,
    BShunt,
}

impl VnaSetup {
    /// DUT coil index and fixture of a thru setup.
    fn thru(self) -> Option<(usize, ThruMode)> {
        match self {
            VnaSetup::Pair => None,
            VnaSetup::ASeries => Some((0, ThruMode::Series)),
            VnaSetup::AShunt => Some((0, ThruMode::Shunt)),
            VnaSetup::BSeries => Some((1, ThruMode::Series)),
            VnaSetup::BShunt => Some((1, ThruMode::Shunt)),
        }
    }
}

/// One coil as the GUI describes it (millimetres).
#[derive(Clone, Debug)]
pub struct CoilParams {
    pub wire_d_mm: f64,
    pub pitch_mm: f64,
    pub former_d_mm: f64,
    pub turns: f64,
    /// Grounded terminal (`None` = floating).
    pub ground: Option<End>,
    /// Outer diameter over the insulation (= wire Ø for bare wire).
    pub insulation_d_mm: f64,
    pub insulation: Dielectric,
    pub former_wall_mm: f64,
    pub former_overhang_mm: f64,
    /// Former dielectric; εr = 1 without loss means no former.
    pub former: Dielectric,
}

#[derive(Clone, Debug)]
pub struct Params {
    pub a: CoilParams,
    pub b: CoilParams,
    pub b_enabled: bool,
    pub gap_ref: GapRef,
    pub gap_mm: f64,
    pub offset_mm: f64,
    pub f_min_mhz: f64,
    pub f_max_mhz: f64,
    pub n_freq: f64,
    pub f_view_mhz: f64,
    pub z_load: f64,
    pub r_factor: f64,
    pub coupling: Coupling,
    pub vna_setup: VnaSetup,
    pub z0: f64,
    pub p_dbm: f64,
    /// Height of the Bz(x) profile (0 = centre of coil A).
    pub x_line_z_mm: f64,
}

fn check_dielectric(what: &str, d: &Dielectric) -> Result<(), String> {
    if !(d.eps_r >= 1.0) {
        return Err(format!("{what} εr must be ≥ 1"));
    }
    if !(d.tan_delta >= 0.0) {
        return Err(format!("{what} tan δ must be ≥ 0"));
    }
    Ok(())
}

impl CoilParams {
    /// `CoilParams.build` with the `SolenoidCoil` / `Former` / `Dielectric` validation.
    pub fn build(&self, name: &str, position: Vec3) -> Result<Coil, String> {
        let err = |m: &str| Err(format!("coil {name}: {m}"));
        if self.turns.fract() != 0.0 || !(self.turns >= 1.0) {
            return err("turns must be a positive integer");
        }
        for (what, v) in [
            ("wire Ø", self.wire_d_mm),
            ("pitch", self.pitch_mm),
            ("former Ø", self.former_d_mm),
        ] {
            if !(v > 0.0) {
                return err(&format!("{what} must be positive"));
            }
        }
        check_dielectric(&format!("coil {name}: insulation"), &self.insulation)?;
        check_dielectric(&format!("coil {name}: former"), &self.former)?;
        let ins_d = self.insulation_d_mm.max(self.wire_d_mm);
        if self.pitch_mm < ins_d {
            return err(&format!(
                "pitch ({} mm) < insulated wire Ø ({ins_d} mm)",
                self.pitch_mm
            ));
        }
        let former = if self.former.eps() != c64::new(1.0, 0.0) {
            if !(self.former_wall_mm > 0.0) {
                return err("former wall must be > 0");
            }
            if !(self.former_overhang_mm >= 0.0) {
                return err("former overhang must be ≥ 0");
            }
            if !(self.former_wall_mm < self.former_d_mm / 2.0) {
                return err("former wall must be less than the former radius");
            }
            Some(Former {
                wall: self.former_wall_mm * MM,
                eps: self.former.eps(),
                overhang: self.former_overhang_mm * MM,
            })
        } else {
            None
        };
        Ok(Coil {
            wire_d: self.wire_d_mm * MM,
            pitch: self.pitch_mm * MM,
            former_d: self.former_d_mm * MM,
            n_turns: self.turns as usize,
            position,
            quat: [0.0, 0.0, 0.0, 1.0],
            insulation_d: ins_d * MM,
            insulation_eps: self.insulation.eps(),
            former,
        })
    }
}

impl Params {
    /// The coils, B placed by the gap rule; checks that they do not intersect.
    pub fn coils(&self) -> Result<Vec<Coil>, String> {
        let a = self.a.build("A", [0.0; 3])?;
        if !self.b_enabled {
            return Ok(vec![a]);
        }
        let b0 = self.b.build("B", [0.0; 3])?;
        let z = match self.gap_ref {
            GapRef::Centre => self.gap_mm * MM,
            GapRef::Edge => (a.length() + b0.length()) / 2.0 + self.gap_mm * MM,
        };
        let b = Coil {
            position: [self.offset_mm * MM, 0.0, z],
            ..b0
        };
        check_overlap(&a, &b)?;
        Ok(vec![a, b])
    }

    fn validate(&self) -> Result<(), String> {
        if !(0.0 < self.f_min_mhz && self.f_min_mhz < self.f_max_mhz) {
            return Err("need 0 < f_min < f_max".into());
        }
        if self.n_freq.fract() != 0.0 || !(self.n_freq >= 2.0) {
            return Err("the number of frequency points must be an integer ≥ 2".into());
        }
        for (what, v) in [
            ("view frequency", self.f_view_mhz),
            ("Z0", self.z0),
            ("R factor", self.r_factor),
        ] {
            if !(v > 0.0) {
                return Err(format!("{what} must be positive"));
            }
        }
        Ok(())
    }

    /// Parameters from `name -> value`; enums are codes (see the match arms). Every name must
    /// be present and finite, and no other names are allowed.
    pub fn decode(values: &[(String, f64)]) -> Result<Params, String> {
        let mut used = vec![false; values.len()];
        let mut get = |name: &str| -> Result<f64, String> {
            let i = values
                .iter()
                .position(|(n, _)| n == name)
                .ok_or(format!("missing parameter {name}"))?;
            used[i] = true;
            let v = values[i].1;
            if !v.is_finite() {
                return Err(format!("an input is empty or not a number ({name})"));
            }
            Ok(v)
        };
        let mut coil = |k: &str| -> Result<CoilParams, String> {
            let mut g = |f: &str| get(&format!("{k}.{f}"));
            Ok(CoilParams {
                wire_d_mm: g("wire_d_mm")?,
                pitch_mm: g("pitch_mm")?,
                former_d_mm: g("former_d_mm")?,
                turns: g("turns")?,
                ground: match g("ground")? as i64 {
                    0 => None,
                    1 => Some(End::Start),
                    2 => Some(End::End),
                    _ => return Err(format!("bad {k}.ground code")),
                },
                insulation_d_mm: g("insulation_d_mm")?,
                insulation: Dielectric {
                    eps_r: g("insulation_eps_r")?,
                    tan_delta: g("insulation_tan_delta")?,
                },
                former_wall_mm: g("former_wall_mm")?,
                former_overhang_mm: g("former_overhang_mm")?,
                former: Dielectric {
                    eps_r: g("former_eps_r")?,
                    tan_delta: g("former_tan_delta")?,
                },
            })
        };
        let (a, b) = (coil("a")?, coil("b")?);
        let p = Params {
            a,
            b,
            b_enabled: get("b_enabled")? != 0.0,
            gap_ref: match get("gap_ref")? as i64 {
                0 => GapRef::Edge,
                1 => GapRef::Centre,
                _ => return Err("bad gap_ref code".into()),
            },
            gap_mm: get("gap_mm")?,
            offset_mm: get("offset_mm")?,
            f_min_mhz: get("f_min_mhz")?,
            f_max_mhz: get("f_max_mhz")?,
            n_freq: get("n_freq")?,
            f_view_mhz: get("f_view_mhz")?,
            z_load: get("z_load")?,
            r_factor: get("r_factor")?,
            coupling: match get("coupling")? as i64 {
                0 => Coupling::Full,
                1 => Coupling::Magnetic,
                2 => Coupling::Electric,
                _ => return Err("bad coupling code".into()),
            },
            vna_setup: match get("vna_setup")? as i64 {
                0 => VnaSetup::Pair,
                1 => VnaSetup::ASeries,
                2 => VnaSetup::AShunt,
                3 => VnaSetup::BSeries,
                4 => VnaSetup::BShunt,
                _ => return Err("bad vna_setup code".into()),
            },
            z0: get("z0")?,
            p_dbm: get("p_dbm")?,
            x_line_z_mm: get("x_line_z_mm")?,
        };
        if let Some(i) = used.iter().position(|u| !u) {
            return Err(format!("unknown parameter {}", values[i].0));
        }
        Ok(p)
    }
}

/// Error if the windings or formers of two parallel-axis coils intersect (`check_overlap`).
pub fn check_overlap(a: &Coil, b: &Coil) -> Result<(), String> {
    let off = (b.position[0] - a.position[0]).hypot(b.position[1] - a.position[1]);
    for (c, d, names) in [(a, b, ["A", "B"]), (b, a, ["B", "A"])] {
        // winding of d vs former wall of c (radii measured from c's axis)
        let Some(f) = c.former else { continue };
        let half = c.length() / 2.0 + f.overhang;
        if (d.position[2] - c.position[2]).abs() >= half + d.length() / 2.0 + d.outer_radius() {
            continue;
        }
        let r_out = c.former_d / 2.0;
        let r_in = r_out - f.wall;
        let lo = d.mean_radius() - off - d.outer_radius();
        let hi = d.mean_radius() + off + d.outer_radius();
        if lo < r_out - 1e-12 && hi > r_in + 1e-12 {
            return Err(format!(
                "the winding of {} intersects the former wall of {}: change the gap or the \
                 former diameter / wall",
                names[1], names[0]
            ));
        }
    }
    let za = (
        a.position[2] - a.length() / 2.0,
        a.position[2] + a.length() / 2.0,
    );
    let zb = (
        b.position[2] - b.length() / 2.0,
        b.position[2] + b.length() / 2.0,
    );
    let clearance = (a.insulation_d + b.insulation_d) / 2.0;
    if za.1 + clearance / 2.0 <= zb.0 || zb.1 + clearance / 2.0 <= za.0 {
        return Ok(());
    }
    // B's winding spans radii [Rb - off, Rb + off] measured from A's axis
    let lo = b.mean_radius() - off - clearance;
    let hi = b.mean_radius() + off + clearance;
    if lo < a.mean_radius() && a.mean_radius() < hi {
        return Err(
            "windings of A and B intersect: increase the gap, or make the radii differ \
                    by more than the lateral offset plus one wire diameter"
                .into(),
        );
    }
    Ok(())
}

fn has_dielectrics(c: &Coil) -> bool {
    let one = c64::new(1.0, 0.0);
    let ins = c.insulation_d > c.wire_d && c.insulation_eps != one;
    ins || c.former.is_some_and(|f| f.eps != one)
}

/// `numpy.linspace(start, stop, num)`.
pub fn linspace(start: f64, stop: f64, num: usize) -> Vec<f64> {
    let step = (stop - start) / (num - 1) as f64;
    let mut out: Vec<f64> = (0..num).map(|i| i as f64 * step + start).collect();
    out[num - 1] = stop;
    out
}

/// Python's `format(x, f".{digits}g")`.
pub fn fmt_g(x: f64, digits: usize) -> String {
    if !x.is_finite() {
        return format!("{x}");
    }
    let strip = |s: String| {
        if s.contains('.') {
            s.trim_end_matches('0').trim_end_matches('.').to_string()
        } else {
            s
        }
    };
    let sci = format!("{:.*e}", digits - 1, x);
    let (mant, exp) = sci.split_once('e').unwrap();
    let exp: i32 = exp.parse().unwrap();
    if exp < -4 || exp >= digits as i32 {
        let sign = if exp < 0 { '-' } else { '+' };
        format!("{}e{sign}{:02}", strip(mant.to_string()), exp.abs())
    } else {
        strip(format!("{:.*}", (digits as i32 - 1 - exp) as usize, x))
    }
}

/// Everything the app shows, row-major. `C` coils, `F` frequencies, `T`/`Nn` turns/nodes of the
/// VNA network.
pub struct Results {
    pub coils: Vec<Coil>,
    pub freqs: Vec<f64>,
    pub i_view: usize,
    /// `(F, C, C)` open-circuit Z of the A/B network.
    pub z: Vec<c64>,
    pub l_dc: Vec<f64>,
    /// `(C, F)` quasi-DC L(f) and skin-effect R(f) × r_factor.
    pub l_f: Vec<f64>,
    pub r_f: Vec<f64>,
    /// Each coil alone (own grounding): first resonance, its Q and |Z| there.
    pub srf_net: Vec<f64>,
    pub q_srf: Vec<f64>,
    pub rp_srf: Vec<f64>,
    /// First resonance at each coil's port in the full network (others open).
    pub srf_here: Vec<f64>,
    pub srf_medhurst: Vec<f64>,
    pub c_medhurst: Vec<f64>,
    /// Same coil without insulation/former dielectrics (NaN if it has none).
    pub srf_vacuum: Vec<f64>,
    pub vna_pair: bool,
    pub vna_coils: Vec<Coil>,
    /// `(F, 2, 2)`.
    pub s: Vec<c64>,
    /// `(F, T)`, `(F, 2)`, `(F, Nn)` for the VNA drive.
    pub drive_turn_i: Vec<c64>,
    pub drive_port_i: Vec<c64>,
    pub drive_node_v: Vec<c64>,
    pub v_plus: f64,
    pub field_x: Vec<f64>,
    pub field_z: Vec<f64>,
    /// `(nz, nx, 3)` complex B [T] in the side-view plane y = 0.
    pub field_b: Vec<c64>,
    pub line_z: Vec<f64>,
    pub bz_z: Vec<c64>,
    /// Same coils with the mean turn current of each coil.
    pub bz_z_uniform: Vec<c64>,
    pub line_x: Vec<f64>,
    /// NaN inside the wires.
    pub bz_x: Vec<c64>,
    pub bz_x_uniform: Vec<c64>,
    pub m_static: f64,
    pub k_static: f64,
    pub electric_fraction: f64,
    pub warnings: Vec<String>,
}

/// `Σ_t I_t B_t(p)` for each point (ring field per turn, coils in order).
fn field(coils: &[Coil], currents: &[c64], points: &[Vec3]) -> Vec<[c64; 3]> {
    let mut out = vec![[c64::new(0.0, 0.0); 3]; points.len()];
    let mut t = 0;
    for c in coils {
        let rot = c.rotation();
        for center in c.turn_centers() {
            let i = currents[t];
            for (o, &pt) in out.iter_mut().zip(points) {
                let b = circle_b(c.mean_radius(), center, &rot, pt);
                for k in 0..3 {
                    o[k] += i * b[k];
                }
            }
            t += 1;
        }
    }
    out
}

/// `_field_grid`: side-view grid around the coils.
fn field_grid(coils: &[Coil]) -> (Vec<f64>, Vec<f64>) {
    let fold = |init: f64, f: fn(f64, f64) -> f64, g: &dyn Fn(&Coil) -> f64| {
        coils.iter().map(g).fold(init, f)
    };
    let r_max = fold(f64::NEG_INFINITY, f64::max, &|c| {
        c.mean_radius() + c.position[0].abs()
    });
    let z_lo = fold(f64::INFINITY, f64::min, &|c| {
        c.position[2] - c.length() / 2.0
    });
    let z_hi = fold(f64::NEG_INFINITY, f64::max, &|c| {
        c.position[2] + c.length() / 2.0
    });
    let margin = 0.6 * r_max;
    let x = linspace(-1.5 * r_max, 1.5 * r_max, 161);
    let (zc, half) = (
        (z_lo + z_hi) / 2.0,
        ((z_hi - z_lo) / 2.0 + margin).max(1.2 * r_max),
    );
    (x, linspace(zc - half, zc + half, 121))
}

pub fn compute(p: &Params) -> Result<Results, String> {
    p.validate()?;
    let coils = p.coils()?;
    let nc = coils.len();
    let thru = p.vna_setup.thru();
    match thru {
        None if nc < 2 => return Err("enable coil B for the A/B coupling setup".into()),
        Some((idx, _)) if idx >= nc => return Err("enable coil B for a B thru setup".into()),
        _ => {}
    }
    let grounds = [p.a.ground, p.b.ground][..nc].to_vec();
    let net = Network::new(&coils, &grounds, p.coupling, p.r_factor, RHO_CU, None, None)?;
    let f_view = p.f_view_mhz * 1e6;
    let mut freqs = geomspace(p.f_min_mhz * 1e6, p.f_max_mhz * 1e6, p.n_freq as usize);
    freqs.push(f_view);
    freqs.sort_by(f64::total_cmp);
    freqs.dedup();
    let nf = freqs.len();
    let res = net.solve(&freqs)?;
    let i_view = freqs.iter().position(|&f| f == f_view).unwrap();
    let hi = (p.f_max_mhz * 1e6 * 10.0).max(1e9);

    // ---- VNA configuration ------------------------------------------------------------
    let (thru_net, thru_res);
    let (vna_net, vna_res) = match thru {
        None => (&net, &res),
        Some((idx, mode)) => {
            let gnd = grounds[idx].unwrap_or(End::End);
            thru_net = vna::thru_network(&coils[idx], mode, gnd, p.r_factor, RHO_CU)?;
            thru_res = thru_net.solve(&freqs)?;
            (&thru_net, &thru_res)
        }
    };
    let s = vna::z_to_s(&vna_res.z, 2, p.z0)?;
    let v_plus = vna::incident_voltage(p.p_dbm, p.z0);
    let emf = [c64::new(2.0 * v_plus, 0.0), c64::new(0.0, 0.0)];
    let (drive_turn_i, drive_port_i) = vna::driven_turn_currents(vna_res, 2, &emf, p.z0)?;
    let nn = vna_res.node_voltages.len() / (nf * 2);
    let drive_node_v: Vec<c64> = (0..nf * nn)
        .map(|fn_| {
            let (f, n) = (fn_ / nn, fn_ % nn);
            (0..2)
                .map(|q| drive_port_i[f * 2 + q] * vna_res.node_voltages[(f * 2 + q) * nn + n])
                .sum()
        })
        .collect();

    let vcoils = &vna_net.coils;
    let (fx, fz) = field_grid(vcoils);
    let nt = drive_turn_i.len() / nf;
    let i_turns = &drive_turn_i[i_view * nt..(i_view + 1) * nt];
    let grid: Vec<Vec3> = fz
        .iter()
        .flat_map(|&z| fx.iter().map(move |&x| [x, 0.0, z]))
        .collect();
    let field_b: Vec<c64> = field(vcoils, i_turns, &grid).concat();

    // ---- Bz line profiles -------------------------------------------------------------
    let mut i_uniform = i_turns.to_vec();
    for k in 0..vcoils.len() {
        let sl = vna_net.turn_offsets[k]..vna_net.turn_offsets[k + 1];
        let mean = i_turns[sl.clone()].iter().sum::<c64>() / sl.len() as f64;
        i_uniform[sl].fill(mean);
    }
    let line_z = linspace(fz[0], fz[fz.len() - 1], 601);
    let line_x = linspace(fx[0], fx[fx.len() - 1], 801);
    let z_cut = p.x_line_z_mm * MM;
    let pts_z: Vec<Vec3> = line_z.iter().map(|&z| [0.0, 0.0, z]).collect();
    let pts_x: Vec<Vec3> = line_x.iter().map(|&x| [x, 0.0, z_cut]).collect();
    let bz = |cur: &[c64], pts: &[Vec3]| -> Vec<c64> {
        field(vcoils, cur, pts).iter().map(|b| b[2]).collect()
    };
    let inside: Vec<bool> = line_x
        .iter()
        .map(|&x| {
            vcoils.iter().any(|c| {
                [-1.0, 1.0].iter().any(|side| {
                    let xc = side * c.mean_radius() + c.position[0];
                    c.turn_z()
                        .iter()
                        .any(|tz| (x - xc).hypot(z_cut - (tz + c.position[2])) < c.wire_radius())
                })
            })
        })
        .collect();
    let mask = |mut v: Vec<c64>| {
        for (b, &ins) in v.iter_mut().zip(&inside) {
            if ins {
                *b = c64::new(f64::NAN, 0.0);
            }
        }
        v
    };

    // ---- resonances and single-coil quantities ----------------------------------------
    let mut srf_net = Vec::new();
    let mut q_srf = Vec::new();
    let mut rp_srf = Vec::new();
    let mut srf_vacuum = Vec::new();
    for (c, &g) in coils.iter().zip(&grounds) {
        let alone = Network::new(
            std::slice::from_ref(c),
            &[g],
            Coupling::Full,
            p.r_factor,
            RHO_CU,
            None,
            None,
        )?;
        let r = alone.resonance(0, 1e4, hi)?;
        srf_net.push(r.freq);
        q_srf.push(r.q);
        rp_srf.push(r.r_parallel);
        srf_vacuum.push(if has_dielectrics(c) {
            let bare = Coil {
                insulation_eps: c64::new(1.0, 0.0),
                former: None,
                ..c.clone()
            };
            Network::new(
                &[bare],
                &[g],
                Coupling::Full,
                p.r_factor,
                RHO_CU,
                None,
                None,
            )?
            .srf(0, 1e4, hi, 400)?
        } else {
            f64::NAN
        });
    }
    let srf_here = if nc > 1 {
        (0..nc)
            .map(|k| net.srf(k, 1e4, hi, 400))
            .collect::<Result<_, _>>()?
    } else {
        vec![srf_net[0]]
    };
    let l_dc: Vec<f64> = coils.iter().map(|c| self_inductance(c, 0.0)).collect();
    let l_f = coils
        .iter()
        .flat_map(|c| freqs.iter().map(move |&f| self_inductance(c, f)))
        .collect();
    let r_f = coils
        .iter()
        .flat_map(|c| {
            freqs
                .iter()
                .map(move |&f| ac_resistance(c, f, RHO_CU) * p.r_factor)
        })
        .collect();

    let (mut m_static, mut k_static, mut electric_fraction) = (f64::NAN, f64::NAN, f64::NAN);
    if nc == 2 {
        m_static = mutual_inductance(&coils[0], &coils[1])?;
        k_static = m_static / (l_dc[0] * l_dc[1]).sqrt();
        if p.coupling == Coupling::Full {
            let ele = Network::new(
                &coils,
                &grounds,
                Coupling::Electric,
                p.r_factor,
                RHO_CU,
                None,
                None,
            )?;
            let z_e = ele.solve(&[f_view])?.z[2]; // z[0, 1, 0]
            electric_fraction = z_e.norm() / res.z[i_view * 4 + 2].norm();
        }
    }

    let mut warnings = Vec::new();
    for (k, c) in coils.iter().enumerate() {
        let name = ["A", "B"][k];
        let ratio = c.length() / c.mean_d();
        if !(0.1..=50.0).contains(&ratio) {
            warnings.push(format!(
                "coil {name}: l/D = {}, outside Medhurst's fitted range",
                fmt_g(ratio, 2)
            ));
        }
        let f_res = match (srf_net[k].is_nan(), srf_here[k].is_nan()) {
            (true, _) => srf_here[k],
            (_, true) => srf_net[k],
            _ => srf_net[k].min(srf_here[k]),
        };
        if f_res.is_finite() && f_view > 0.3 * f_res {
            let place = if f_view > f_res { "above" } else { "near" };
            warnings.push(format!(
                "coil {name}: view frequency is {:.3} × its first resonance ({place} it): \
                 L_eff and X/R are dominated by the resonance, not the inductance",
                f_view / f_res
            ));
        }
        if c.pitch < 2.5 * c.wire_d && p.r_factor == 1.0 {
            warnings.push(format!(
                "coil {name}: pitch is {} × wire Ø; the proximity effect (not modelled) raises \
                 R, by tens of % up to 2–3× for touching turns: set R factor",
                fmt_g(c.pitch / c.wire_d, 2)
            ));
        }
        let lam = 299_792_458.0 / f_view;
        if c.wire_length() / lam > 0.1 {
            warnings.push(format!(
                "coil {name}: wire is {:.2} λ long; lumped-turn model is still fine, the static \
                 model is not",
                c.wire_length() / lam
            ));
        }
    }

    Ok(Results {
        srf_medhurst: coils.iter().map(|c| srf_lumped(c, 0.0)).collect(),
        c_medhurst: coils.iter().map(self_capacitance_medhurst).collect(),
        vna_coils: vcoils.clone(),
        coils,
        i_view,
        z: res.z,
        l_dc,
        l_f,
        r_f,
        srf_net,
        q_srf,
        rp_srf,
        srf_here,
        srf_vacuum,
        vna_pair: thru.is_none(),
        s,
        drive_port_i,
        drive_node_v,
        v_plus,
        field_b,
        bz_z: bz(i_turns, &pts_z),
        bz_z_uniform: bz(&i_uniform, &pts_z),
        bz_x: mask(bz(i_turns, &pts_x)),
        bz_x_uniform: mask(bz(&i_uniform, &pts_x)),
        drive_turn_i,
        field_x: fx,
        field_z: fz,
        line_z,
        line_x,
        m_static,
        k_static,
        electric_fraction,
        warnings,
        freqs,
    })
}

// ---- byte interface -----------------------------------------------------------------

enum Data<'a> {
    Real(&'a [f64]),
    Complex(&'a [c64]),
    Text(&'a [String]),
}

fn put(out: &mut Vec<u8>, name: &str, shape: &[usize], data: Data) {
    out.extend((name.len() as u32).to_le_bytes());
    out.extend(name.as_bytes());
    let kind = match data {
        Data::Real(_) => 0u8,
        Data::Complex(_) => 1,
        Data::Text(_) => 2,
    };
    out.extend([kind, shape.len() as u8]);
    for &n in shape {
        out.extend((n as u32).to_le_bytes());
    }
    match data {
        Data::Real(v) => v.iter().for_each(|x| out.extend(x.to_le_bytes())),
        Data::Complex(v) => v.iter().for_each(|z| {
            out.extend(z.re.to_le_bytes());
            out.extend(z.im.to_le_bytes());
        }),
        Data::Text(v) => v.iter().for_each(|s| {
            out.extend((s.len() as u32).to_le_bytes());
            out.extend(s.as_bytes());
        }),
    }
}

/// `(C, 19)` coil table, the column layout of `tests/port/conftest.py::coil_table`.
fn coil_table(coils: &[Coil]) -> Vec<f64> {
    coils
        .iter()
        .flat_map(|c| {
            let f = c.former.unwrap_or(Former {
                wall: 0.0,
                eps: c64::new(0.0, 0.0),
                overhang: 0.0,
            });
            let [px, py, pz] = c.position;
            let [qx, qy, qz, qw] = c.quat;
            [
                c.wire_d,
                c.pitch,
                c.former_d,
                c.n_turns as f64,
                px,
                py,
                pz,
                qx,
                qy,
                qz,
                qw,
                c.insulation_d,
                c.insulation_eps.re,
                c.insulation_eps.im,
                c.former.is_some() as u8 as f64,
                f.wall,
                f.eps.re,
                f.eps.im,
                f.overhang,
            ]
        })
        .collect()
}

impl Results {
    pub fn encode(&self, out: &mut Vec<u8>) {
        use Data::{Complex, Real, Text};
        let (nc, nf) = (self.coils.len(), self.freqs.len());
        let nt = self.drive_turn_i.len() / nf;
        let nn = self.drive_node_v.len() / nf;
        let (nz, nx) = (self.field_z.len(), self.field_x.len());
        let scalars = [
            self.i_view as f64,
            self.v_plus,
            self.vna_pair as u8 as f64,
            self.m_static,
            self.k_static,
            self.electric_fraction,
        ];
        let (coils, vna_coils) = (coil_table(&self.coils), coil_table(&self.vna_coils));
        let items: Vec<(&str, Vec<usize>, Data)> = vec![
            ("coils", vec![nc, 19], Real(&coils)),
            ("freqs", vec![nf], Real(&self.freqs)),
            ("z", vec![nf, nc, nc], Complex(&self.z)),
            ("l_dc", vec![nc], Real(&self.l_dc)),
            ("l_f", vec![nc, nf], Real(&self.l_f)),
            ("r_f", vec![nc, nf], Real(&self.r_f)),
            ("srf_net", vec![nc], Real(&self.srf_net)),
            ("q_srf", vec![nc], Real(&self.q_srf)),
            ("rp_srf", vec![nc], Real(&self.rp_srf)),
            ("srf_here", vec![nc], Real(&self.srf_here)),
            ("srf_medhurst", vec![nc], Real(&self.srf_medhurst)),
            ("c_medhurst", vec![nc], Real(&self.c_medhurst)),
            ("srf_vacuum", vec![nc], Real(&self.srf_vacuum)),
            (
                "vna_coils",
                vec![self.vna_coils.len(), 19],
                Real(&vna_coils),
            ),
            ("s", vec![nf, 2, 2], Complex(&self.s)),
            ("drive_turn_i", vec![nf, nt], Complex(&self.drive_turn_i)),
            ("drive_port_i", vec![nf, 2], Complex(&self.drive_port_i)),
            ("drive_node_v", vec![nf, nn], Complex(&self.drive_node_v)),
            ("field_x", vec![nx], Real(&self.field_x)),
            ("field_z", vec![nz], Real(&self.field_z)),
            ("field_b", vec![nz, nx, 3], Complex(&self.field_b)),
            ("line_z", vec![self.line_z.len()], Real(&self.line_z)),
            ("bz_z", vec![self.line_z.len()], Complex(&self.bz_z)),
            (
                "bz_z_uniform",
                vec![self.line_z.len()],
                Complex(&self.bz_z_uniform),
            ),
            ("line_x", vec![self.line_x.len()], Real(&self.line_x)),
            ("bz_x", vec![self.line_x.len()], Complex(&self.bz_x)),
            (
                "bz_x_uniform",
                vec![self.line_x.len()],
                Complex(&self.bz_x_uniform),
            ),
            // i_view, v_plus, vna_pair, m_static, k_static, electric_fraction
            ("scalars", vec![scalars.len()], Real(&scalars)),
            ("warnings", vec![self.warnings.len()], Text(&self.warnings)),
        ];
        out.extend((items.len() as u32).to_le_bytes());
        for (name, shape, data) in items {
            put(out, name, &shape, data);
        }
    }
}

fn decode_request(req: &[u8]) -> Result<Vec<(String, f64)>, String> {
    let mut pos = 0;
    let mut take = |n: usize| -> Result<&[u8], String> {
        let s = req.get(pos..pos + n).ok_or("truncated request")?;
        pos += n;
        Ok(s)
    };
    let u32_ = |b: &[u8]| u32::from_le_bytes(b.try_into().unwrap()) as usize;
    let count = u32_(take(4)?);
    let mut out = Vec::with_capacity(count);
    for _ in 0..count {
        let len = u32_(take(4)?);
        let name = String::from_utf8(take(len)?.to_vec()).map_err(|_| "bad parameter name")?;
        let v = f64::from_le_bytes(take(8)?.try_into().unwrap());
        out.push((name, v));
    }
    Ok(out)
}

/// Request bytes -> response bytes (see the module docs).
pub fn call(req: &[u8]) -> Vec<u8> {
    let result = decode_request(req)
        .and_then(|v| Params::decode(&v))
        .and_then(|p| compute(&p));
    let mut out = Vec::new();
    match result {
        Ok(r) => {
            out.push(0);
            r.encode(&mut out);
        }
        Err(e) => {
            out.push(1);
            out.extend((e.len() as u32).to_le_bytes());
            out.extend(e.as_bytes());
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::fmt_g;

    #[test]
    fn fmt_g_matches_python() {
        // format(x, ".2g") in CPython
        for (x, want) in [
            (0.0, "0"),
            (1.0, "1"),
            (0.75, "0.75"),
            (2.0, "2"),
            (12.5, "12"),
            (13.5, "14"),
            (99.6, "1e+02"),
            (0.0001234, "0.00012"),
            (0.00001234, "1.2e-05"),
            (123456.0, "1.2e+05"),
            (1.05, "1.1"),
        ] {
            assert_eq!(fmt_g(x, 2), want, "{x}");
        }
    }
}
