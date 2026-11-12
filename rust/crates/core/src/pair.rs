//! The "Wire pair C" calculator: port of `compute_pair` in `coilcal/gui/pair.py` (C′ of two
//! parallel insulated wires, the bare / uniform-dielectric / effective-radius comparisons, the
//! sweep over the surface gap) plus the potential map the field plot draws, and the input
//! checks of `InsulatedWire` / `Dielectric` / `pair_capacitance`.

// `!(x > 0.0)` is deliberate: it rejects NaN, as the Python `not x > 0` checks do.
#![allow(clippy::neg_cmp_op_on_partial_ord)]

use crate::app::{Data, Dielectric, Values, check_dielectric, linspace, put};
use crate::c64;
use crate::wirepair::{
    InsulatedWire, WirePair, bare_pair_capacitance, effective_radius, pair_capacitance,
};

const MM: f64 = 1e-3;

#[derive(Clone, Debug)]
pub struct WireParams {
    pub conductor_d_mm: f64,
    /// Outer Ø over the insulation (= conductor Ø for bare wire).
    pub insulation_d_mm: f64,
    pub insulation: Dielectric,
}

#[derive(Clone, Debug)]
pub struct PairParams {
    pub w1: WireParams,
    pub w2: WireParams,
    /// Wire 2 identical to wire 1 (then `w2` is ignored).
    pub same: bool,
    /// `false`: spacing = insulation surface gap; `true`: centre-to-centre.
    pub centre: bool,
    pub spacing_mm: f64,
}

impl WireParams {
    fn wire(&self, name: &str) -> Result<InsulatedWire, String> {
        if !(self.conductor_d_mm > 0.0) {
            return Err(format!("{name}: conductor Ø must be positive"));
        }
        if !(self.insulation_d_mm >= self.conductor_d_mm) {
            return Err(format!(
                "{name}: insulation outer Ø is below the conductor Ø"
            ));
        }
        check_dielectric(&format!("{name}: insulation"), &self.insulation)?;
        let (a, b) = (
            self.conductor_d_mm * MM / 2.0,
            self.insulation_d_mm * MM / 2.0,
        );
        // InsulatedWire.eps: the sleeve's permittivity, 1 for a bare wire
        let eps = if b > a {
            self.insulation.eps()
        } else {
            c64::new(1.0, 0.0)
        };
        Ok(InsulatedWire { a, b, eps })
    }
}

impl PairParams {
    pub fn decode(vals: &mut Values) -> Result<PairParams, String> {
        let mut wire = |k: &str| -> Result<WireParams, String> {
            let mut g = |f: &str| vals.get(&format!("{k}.{f}"));
            Ok(WireParams {
                conductor_d_mm: g("conductor_d_mm")?,
                insulation_d_mm: g("insulation_d_mm")?,
                insulation: Dielectric {
                    eps_r: g("eps_r")?,
                    tan_delta: g("tan_delta")?,
                },
            })
        };
        let (w1, w2) = (wire("w1")?, wire("w2")?);
        let p = PairParams {
            w1,
            w2,
            same: vals.get("same")? != 0.0,
            centre: match vals.get("spacing_ref")? as i64 {
                0 => false,
                1 => true,
                _ => return Err("bad spacing_ref code".into()),
            },
            spacing_mm: vals.get("spacing_mm")?,
        };
        vals.finish()?;
        Ok(p)
    }

    /// The two wires, each with its εr (used by the effective-radius and uniform comparisons).
    fn wires(&self) -> Result<[(InsulatedWire, f64); 2], String> {
        let w1 = (self.w1.wire("wire 1")?, self.w1.insulation.eps_r);
        let w2 = if self.same {
            w1
        } else {
            (self.w2.wire("wire 2")?, self.w2.insulation.eps_r)
        };
        Ok([w1, w2])
    }
}

pub struct PairResults {
    pub res: WirePair,
    pub c_bare: f64,
    /// Whole space filled with the common εr (NaN if the εr differ or a wire is bare).
    pub c_uniform: f64,
    pub c_eff_radius: f64,
    pub gap: Vec<f64>,
    pub sweep_exact: Vec<f64>,
    pub sweep_bare: Vec<f64>,
    pub sweep_uniform: Vec<f64>,
    pub sweep_eff: Vec<f64>,
    /// Potential map for 1 V across the pair: `phi[iy * nx + ix]` (real part).
    pub field_x: Vec<f64>,
    pub field_y: Vec<f64>,
    pub phi: Vec<f64>,
}

pub fn compute(p: &PairParams) -> Result<PairResults, String> {
    let [(w1, e1), (w2, e2)] = p.wires()?;
    let s = if p.centre {
        p.spacing_mm * MM
    } else {
        p.spacing_mm * MM + w1.b + w2.b
    };
    let res = pair_capacitance(w1, w2, s, 1e-9, 1024)?;
    let insulated = [w1.b > w1.a, w2.b > w2.a];
    // _common_eps: one εr shared by both sleeves, and no bare wire
    let eps = if insulated[0] && insulated[1] && e1 == e2 {
        Some(e1)
    } else {
        None
    };
    let (ae1, ae2) = (
        effective_radius(w1.a, w1.b, e1),
        effective_radius(w2.a, w2.b, e2),
    );

    // sweep: surface gap from touching (or nearly, for bare wires) to a few diameters
    let d_out = 2.0 * w1.b.max(w2.b);
    let g_now = s - w1.b - w2.b;
    let g_max = (3.0 * d_out).max(1.5 * g_now);
    let g_min = if insulated[0] && insulated[1] {
        0.0
    } else {
        0.02 * w1.a.min(w2.a)
    };
    let gap = linspace(g_min, g_max, 41);
    let ss: Vec<f64> = gap.iter().map(|g| g + w1.b + w2.b).collect();
    let bare = |a1: f64, a2: f64, x: f64| bare_pair_capacitance(a1, a2, x);
    let sweep_exact = ss
        .iter()
        .map(|&x| Ok(pair_capacitance(w1, w2, x, 1e-6, 256)?.c.re))
        .collect::<Result<Vec<_>, String>>()?;
    let sweep_bare = ss
        .iter()
        .map(|&x| bare(w1.a, w2.a, x))
        .collect::<Result<Vec<_>, _>>()?;
    let sweep_eff = ss
        .iter()
        .map(|&x| bare(ae1, ae2, x))
        .collect::<Result<Vec<_>, _>>()?;
    let sweep_uniform = sweep_bare
        .iter()
        .map(|c| eps.map_or(f64::NAN, |e| e * c))
        .collect();
    let c_bare = bare(w1.a, w2.a, s)?;

    // potential map (gui/pair.py draw_pair)
    let bmax = w1.b.max(w2.b);
    let field_x = linspace(
        -s / 2.0 - w1.b - 1.2 * bmax,
        s / 2.0 + w2.b + 1.2 * bmax,
        420,
    );
    let field_y = linspace(-2.0 * bmax, 2.0 * bmax, 260);
    let phi = field_y
        .iter()
        .flat_map(|&y| field_x.iter().map(move |&x| (x, y)))
        .map(|(x, y)| res.potential(x, y).re)
        .collect();
    Ok(PairResults {
        c_bare,
        c_uniform: eps.map_or(f64::NAN, |e| e * c_bare),
        c_eff_radius: bare(ae1, ae2, s)?,
        res,
        gap,
        sweep_exact,
        sweep_bare,
        sweep_uniform,
        sweep_eff,
        field_x,
        field_y,
        phi,
    })
}

impl PairResults {
    pub fn encode(&self, out: &mut Vec<u8>) {
        use Data::{Complex, Real};
        let r = &self.res;
        let wires: Vec<f64> = r
            .wires
            .iter()
            .flat_map(|w| [w.a, w.b, w.eps.re, w.eps.im])
            .collect();
        // n_terms, converged, spacing, c_bare, c_uniform, c_eff_radius
        let scalars = [
            r.n_terms as f64,
            r.converged as u8 as f64,
            r.spacing,
            self.c_bare,
            self.c_uniform,
            self.c_eff_radius,
        ];
        let (n, nx, ny) = (self.gap.len(), self.field_x.len(), self.field_y.len());
        let items: Vec<(&str, Vec<usize>, Data)> = vec![
            ("c", vec![1], Complex(std::slice::from_ref(&r.c))),
            ("v", vec![2], Complex(&r.v)),
            ("wires", vec![2, 4], Real(&wires)),
            ("scalars", vec![scalars.len()], Real(&scalars)),
            ("gap", vec![n], Real(&self.gap)),
            ("sweep_exact", vec![n], Real(&self.sweep_exact)),
            ("sweep_bare", vec![n], Real(&self.sweep_bare)),
            ("sweep_uniform", vec![n], Real(&self.sweep_uniform)),
            ("sweep_eff", vec![n], Real(&self.sweep_eff)),
            ("field_x", vec![nx], Real(&self.field_x)),
            ("field_y", vec![ny], Real(&self.field_y)),
            ("phi", vec![ny, nx], Real(&self.phi)),
        ];
        out.extend((items.len() as u32).to_le_bytes());
        for (name, shape, data) in items {
            put(out, name, &shape, data);
        }
    }
}
