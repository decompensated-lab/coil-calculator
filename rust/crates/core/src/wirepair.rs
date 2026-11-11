//! Capacitance per unit length between two long, parallel, insulated round wires in air.
//!
//! Port of `coilcal/wirepair.py` (2-D multipole expansion with per-harmonic sleeve reflection
//! coefficients, multipole count doubled until C' converges); see the Python module docstring
//! for the method. Complex permittivity gives C' − jC''.

use crate::c64;
use crate::capacitance::EPS0;
use crate::linalg::solve_lu;
use std::f64::consts::PI;

/// Round conductor (radius `a`) in a concentric sleeve (outer radius `b`, permittivity `eps`;
/// pass 1 for a bare wire, as `InsulatedWire.eps` does).
#[derive(Clone, Copy, Debug)]
pub struct InsulatedWire {
    pub a: f64,
    pub b: f64,
    pub eps: c64,
}

/// Exact C' [F/m] between two bare round conductors (radii a1, a2, centre spacing s).
pub fn bare_pair_capacitance(a1: f64, a2: f64, s: f64) -> Result<f64, String> {
    if s <= a1 + a2 {
        return Err("conductors overlap or touch".into());
    }
    Ok(2.0 * PI * EPS0 / ((s * s - a1 * a1 - a2 * a2) / (2.0 * a1 * a2)).acosh())
}

/// Radius of the bare wire with the same isolated capacitance: `b·(a/b)^(1/εr)`.
pub fn effective_radius(a: f64, b: f64, eps_r: f64) -> f64 {
    if b > a {
        b * (a / b).powf(1.0 / eps_r)
    } else {
        a
    }
}

/// Solution for charges +q (wire 1 at x = −s/2) and −q (wire 2 at x = +s/2), scaled to 1 V.
pub struct WirePair {
    pub wires: [InsulatedWire; 2],
    pub spacing: f64,
    /// C' − jC'' [F/m].
    pub c: c64,
    pub n_terms: usize,
    pub converged: bool,
    coef: [Vec<c64>; 2], // scaled multipole coefficients
    dreg: [Vec<c64>; 2], // scaled regular coefficients, index 0 = constant
    q: c64,              // q/(2π ε0) on wire 1 for 1 V difference
    /// Conductor potentials [V] (V1 − V2 = 1 V; common mode → 0 at infinity).
    pub v: [c64; 2],
}

impl WirePair {
    /// Potential [V] at (x, y) for 1 V between the conductors.
    pub fn potential(&self, x: f64, y: f64) -> c64 {
        let centres = [-self.spacing / 2.0, self.spacing / 2.0];
        let qs = [self.q, -self.q];
        let rk = centres.map(|xc| (x - xc).hypot(y));
        let th = centres.map(|xc| y.atan2(x - xc));
        let nt = self.coef[0].len();
        // inside a wire: conductor constant or sleeve solution
        for (k, w) in self.wires.iter().enumerate() {
            if rk[k] < w.a {
                return self.v[k];
            }
            if rk[k] < w.b {
                let r = rk[k];
                let mut harm = c64::new(0.0, 0.0);
                for i in 0..nt {
                    let n = (i + 1) as f64;
                    let u = (w.a / w.b).powf(2.0 * n);
                    let amp = 2.0 * self.dreg[k][i + 1] / ((1.0 - u) + w.eps * (1.0 + u));
                    let radial = (r / w.b).powf(n) - u * (w.b / r).powf(n);
                    harm += amp * radial * (th[k] * n).cos();
                }
                return self.v[k] - qs[k] / w.eps * (r / w.a).ln() + harm;
            }
        }
        // air: line charges + multipoles of both wires
        let mut out = c64::new(0.0, 0.0);
        for (k, w) in self.wires.iter().enumerate() {
            let r = rk[k].max(w.b);
            let mut sum = c64::new(0.0, 0.0);
            for i in 0..nt {
                let n = (i + 1) as f64;
                sum += self.coef[k][i] * (th[k] * n).cos() * (w.b / r).powf(n);
            }
            out += -qs[k] * r.ln() + sum;
        }
        out
    }

    /// Effective loss tangent of the line, C''/C'.
    pub fn tan_delta(&self) -> f64 {
        -self.c.im / self.c.re
    }

    /// Shunt conductance G' [S/m] at `freq` from the dielectric loss.
    pub fn conductance(&self, freq: f64) -> f64 {
        2.0 * PI * freq * -self.c.im
    }
}

fn solve(w: [InsulatedWire; 2], s: f64, nt: usize) -> Result<WirePair, String> {
    let nf = |i: usize| (i + 1) as f64; // harmonic index n (and m) of slot i
    let gam: [Vec<c64>; 2] = w.map(|w| {
        (0..nt)
            .map(|i| {
                let u = (w.a / w.b).powf(2.0 * nf(i));
                ((1.0 - u) - w.eps * (1.0 + u)) / ((1.0 - u) + w.eps * (1.0 + u))
            })
            .collect()
    });
    // lengths normalised by s; potentials in units of q/(2π ε0) with q1 = 1, q2 = −1
    let b = [w[0].b / s, w[1].b / s];
    let q = [1.0, -1.0];
    let pairs = [(0usize, 1usize, -1.0f64), (1, 0, 1.0)]; // (k, j, sign of x_k − x_j)
    let lg = |m: f64, n: f64| libm::lgamma(n + m) - libm::lgamma(m + 1.0) - libm::lgamma(n);
    let sgn = |p: f64| if p % 2.0 == 0.0 { 1.0 } else { -1.0 }; // (−1)^p for integer p
    // regular field at k from j: log term h, multipole re-expansion t (row m, column n)
    let mut h = [vec![0.0; nt], vec![0.0; nt]];
    let mut t = [vec![0.0; nt * nt], vec![0.0; nt * nt]]; // t[k] = T(k, j)
    for &(k, j, sg) in &pairs {
        for mi in 0..nt {
            let m = nf(mi);
            h[k][mi] = -q[j] * sgn(m + 1.0) / m * (sg * b[k]).powf(m);
            for ni in 0..nt {
                let n = nf(ni);
                let mag = (lg(m, n) + m * b[k].ln() + n * b[j].ln()).exp();
                t[k][mi * nt + ni] = mag * sgn(m) * if sg < 0.0 { sgn(m + n) } else { 1.0 };
            }
        }
    }
    let n2 = 2 * nt;
    let mut a = vec![c64::new(0.0, 0.0); n2 * n2];
    let mut rhs = vec![c64::new(0.0, 0.0); n2];
    for &(k, _, _) in &pairs {
        let off = k * nt;
        let other = (1 - k) * nt;
        for mi in 0..nt {
            a[(off + mi) * n2 + off + mi] = c64::new(1.0, 0.0);
            for ni in 0..nt {
                a[(off + mi) * n2 + other + ni] = -(gam[k][mi] * t[k][mi * nt + ni]);
            }
            rhs[off + mi] = gam[k][mi] * h[k][mi];
        }
    }
    let x = solve_lu(&a, &rhs, n2, 1).ok_or("singular multipole system")?;
    let coef = [x[..nt].to_vec(), x[nt..].to_vec()];
    let mut d = [vec![c64::new(0.0, 0.0); nt], vec![c64::new(0.0, 0.0); nt]];
    let mut v = [c64::new(0.0, 0.0); 2];
    let mut d0 = [c64::new(0.0, 0.0); 2];
    for &(k, j, sg) in &pairs {
        for mi in 0..nt {
            let tc: c64 = (0..nt).map(|ni| t[k][mi * nt + ni] * coef[j][ni]).sum();
            d[k][mi] = h[k][mi] + tc;
        }
        d0[k] = (0..nt)
            .map(|ni| coef[j][ni] * (sg * b[j]).powf(nf(ni)))
            .sum(); // ln|D| = 0
        v[k] = q[k] * ((w[k].b / w[k].a).ln() / w[k].eps - b[k].ln()) + d0[k];
    }
    // rescale to 1 V across the pair (the ln s terms cancel because q1 + q2 = 0)
    let scale = 1.0 / (v[0] - v[1]);
    let dreg = [0, 1].map(|k| {
        std::iter::once(d0[k])
            .chain(d[k].iter().copied())
            .map(|z| z * scale)
            .collect()
    });
    Ok(WirePair {
        wires: w,
        spacing: s,
        c: 2.0 * PI * EPS0 * scale,
        n_terms: nt,
        converged: false,
        coef: coef.map(|c| c.into_iter().map(|z| z * scale).collect()),
        dreg,
        q: scale,
        v: v.map(|z| z * scale),
    })
}

/// C' between two parallel insulated wires at centre spacing `spacing` [m]; the number of
/// multipole terms doubles from 8 until C' changes by less than `rtol` or reaches `max_terms`.
pub fn pair_capacitance(
    w1: InsulatedWire,
    w2: InsulatedWire,
    spacing: f64,
    rtol: f64,
    max_terms: usize,
) -> Result<WirePair, String> {
    if spacing < (w1.b + w2.b) * (1.0 - 1e-12) {
        return Err(format!(
            "spacing {spacing} m < sum of outer radii {} m (wires overlap)",
            w1.b + w2.b
        ));
    }
    if spacing <= w1.a + w2.a {
        return Err("bare conductors touch".into());
    }
    let w = [w1, w2];
    let mut nt = 8;
    let mut prev = solve(w, spacing, nt)?;
    while nt < max_terms {
        nt = (2 * nt).min(max_terms);
        let cur = solve(w, spacing, nt)?;
        if (cur.c - prev.c).norm() <= rtol * cur.c.norm() {
            return Ok(WirePair {
                converged: true,
                ..cur
            });
        }
        prev = cur;
    }
    Ok(prev)
}
