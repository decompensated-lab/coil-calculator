//! Turn-level circuit model of one or more coils; port of `coilcal/circuit.py`.
//!
//! Every turn is a branch `R + jωL` coupled to every other turn through the full inductance
//! matrix; the turn capacitance matrix is mapped onto nodes (each turn at the mean potential of
//! its end nodes) and the network is solved by modified nodal analysis, one dense solve per
//! frequency. See the Python module docstring for the model. Array layouts are row-major.

use crate::c64;
use crate::capacitance::{self, Matrix};
use crate::geometry::Coil;
use crate::linalg::solve_lu;
use crate::loops::{
    internal_impedance_per_length, internal_inductance_per_length, loop_self_inductance,
    mutual_coaxial,
};
use crate::mutual::mutual_matrix;
use std::f64::consts::PI;

/// Node index of the reference (infinity / grounded shield).
pub const REF: isize = -1;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum End {
    Start,
    End,
}

/// `(coil index, end)` or `None` for the reference node.
pub type Terminal = Option<(usize, End)>;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Coupling {
    Full,
    /// Drops inter-coil capacitance.
    Magnetic,
    /// Drops inter-coil mutual inductance.
    Electric,
}

/// A parallel self-resonance seen at a port.
#[derive(Clone, Copy, Debug)]
pub struct Resonance {
    pub freq: f64,
    pub q: f64,
    pub r_parallel: f64,
}

/// Solution over frequency for 1 A into each port (others open), row-major.
pub struct NetworkResult {
    pub freqs: Vec<f64>,
    /// `(F, P, P)`: `z[f, i, j] = V_i / I_j`.
    pub z: Vec<c64>,
    /// `(F, P, T)`.
    pub turn_currents: Vec<c64>,
    /// `(F, P, Nn)`, grounded nodes 0.
    pub node_voltages: Vec<c64>,
}

pub struct Network {
    pub coils: Vec<Coil>,
    pub r_factor: f64,
    pub rho: f64,
    pub turn_offsets: Vec<usize>,
    pub node_offsets: Vec<usize>,
    /// External inductance minus the DC internal part, `(T, T)`.
    l_ext: Vec<f64>,
    turn_length: Vec<f64>,
    turn_circ: Vec<f64>,
    wire_radius: Vec<f64>,
    /// Node capacitance matrix `(Nn, Nn)` (complex if a dielectric is lossy).
    pub c_node: Vec<c64>,
    free_nodes: Vec<usize>,
    /// `(plus, minus)` node of each port; current enters at `plus`.
    pub ports: Vec<(isize, isize)>,
}

impl Network {
    /// `CoilNetwork(coils, ground, coupling, r_factor, rho, n_sub, ports)`; `ground[i]` is the
    /// grounded terminal of coil `i` (`None` = floating); `ports = None` gives one port per coil
    /// from its start to its end terminal.
    pub fn new(
        coils: &[Coil],
        ground: &[Option<End>],
        coupling: Coupling,
        r_factor: f64,
        rho: f64,
        n_sub: Option<usize>,
        ports: Option<&[(Terminal, Terminal)]>,
    ) -> Result<Self, String> {
        let nc = coils.len();
        if ground.len() != nc {
            return Err(format!(
                "got {} ground settings for {nc} coils",
                ground.len()
            ));
        }
        let mut turn_offsets = vec![0];
        let mut node_offsets = vec![0];
        for c in coils {
            turn_offsets.push(turn_offsets.last().unwrap() + c.n_turns);
            node_offsets.push(node_offsets.last().unwrap() + c.n_turns + 1);
        }
        let (nt, nn) = (turn_offsets[nc], node_offsets[nc]);

        // --- inductance: external part (frequency independent) --------------------------
        let mut l_ext = vec![0.0; nt * nt];
        for (i, a) in coils.iter().enumerate() {
            let (oi, r) = (turn_offsets[i], a.mean_radius());
            let tz = a.turn_z();
            let l_self = loop_self_inductance(r, a.wire_radius(), 0.0);
            for p in 0..a.n_turns {
                for q in 0..a.n_turns {
                    let dz = tz[p] - tz[q];
                    l_ext[(oi + p) * nt + oi + q] = if p == q {
                        l_self
                    } else {
                        mutual_coaxial(r, r, dz)
                    };
                }
            }
            for (j, b) in coils.iter().enumerate().skip(i + 1) {
                if coupling == Coupling::Electric {
                    continue;
                }
                let mij = mutual_matrix(a, b, None, 1e-9, 1 << 14)?;
                let oj = turn_offsets[j];
                for p in 0..a.n_turns {
                    for q in 0..b.n_turns {
                        let m = mij[p * b.n_turns + q];
                        l_ext[(oi + p) * nt + oj + q] = m;
                        l_ext[(oj + q) * nt + oi + p] = m;
                    }
                }
            }
        }
        let per_turn = |f: &dyn Fn(&Coil) -> f64| -> Vec<f64> {
            coils
                .iter()
                .flat_map(|c| std::iter::repeat_n(f(c), c.n_turns))
                .collect()
        };
        let turn_length = per_turn(&|c| c.wire_length() / c.n_turns as f64); // helical, for R
        let turn_circ = per_turn(&|c| 2.0 * PI * c.mean_radius()); // for internal L
        let wire_radius = per_turn(&|c| c.wire_radius());
        // remove the DC internal inductance; it is added back per frequency
        let l_int_dc_per_m = internal_inductance_per_length(wire_radius[0], 0.0, rho);
        for t in 0..nt {
            l_ext[t * nt + t] -= l_int_dc_per_m * turn_circ[t];
        }

        // --- capacitance: turns -> nodes --------------------------------------------------
        let opt = capacitance::Options {
            n_sub,
            ..Default::default()
        };
        let as_c64 = |m: Matrix| match m {
            Matrix::Real(v) => v.into_iter().map(|x| c64::new(x, 0.0)).collect(),
            Matrix::Complex(v) => v,
        };
        let c_turn: Vec<c64> = if coupling == Coupling::Magnetic && nc > 1 {
            let mut c = vec![c64::new(0.0, 0.0); nt * nt];
            for (i, coil) in coils.iter().enumerate() {
                let (o, n) = (turn_offsets[i], coil.n_turns);
                let ci = as_c64(capacitance::capacitance_matrix(
                    std::slice::from_ref(coil),
                    &opt,
                )?);
                for p in 0..n {
                    c[(o + p) * nt + o..(o + p) * nt + o + n]
                        .copy_from_slice(&ci[p * n..(p + 1) * n]);
                }
            }
            c
        } else {
            as_c64(capacitance::capacitance_matrix(coils, &opt)?)
        };
        // turn t spans nodes (from[t], from[t] + 1); c_node = Tᵀ C T with T = 0.5 at both
        let from: Vec<usize> = (0..nc)
            .flat_map(|i| (0..coils[i].n_turns).map(move |k| (i, k)))
            .map(|(i, k)| node_offsets[i] + k)
            .collect();
        let mut a_half = vec![c64::new(0.0, 0.0); nn * nt]; // Tᵀ C
        for (i, &n0) in from.iter().enumerate() {
            for n in [n0, n0 + 1] {
                for j in 0..nt {
                    a_half[n * nt + j] += 0.5 * c_turn[i * nt + j];
                }
            }
        }
        let mut c_node = vec![c64::new(0.0, 0.0); nn * nn];
        for p in 0..nn {
            for (j, &n0) in from.iter().enumerate() {
                for n in [n0, n0 + 1] {
                    c_node[p * nn + n] += a_half[p * nt + j] * 0.5;
                }
            }
        }

        let mut net = Network {
            coils: coils.to_vec(),
            r_factor,
            rho,
            turn_offsets,
            node_offsets,
            l_ext,
            turn_length,
            turn_circ,
            wire_radius,
            c_node,
            free_nodes: Vec::new(),
            ports: Vec::new(),
        };
        let mut grounded = Vec::new();
        for (i, g) in ground.iter().enumerate() {
            if let Some(end) = g {
                grounded.push(net.terminal_node(Some((i, *end)))?);
            }
        }
        net.free_nodes = (0..nn as isize)
            .filter(|n| !grounded.contains(n))
            .map(|n| n as usize)
            .collect();
        let default_ports: Vec<(Terminal, Terminal)> = (0..nc)
            .map(|i| (Some((i, End::Start)), Some((i, End::End))))
            .collect();
        for &(p, m) in ports.unwrap_or(&default_ports) {
            let pm = (net.terminal_node(p)?, net.terminal_node(m)?);
            net.ports.push(pm);
        }
        Ok(net)
    }

    /// Global node index of a terminal; `None` -> [`REF`].
    pub fn terminal_node(&self, terminal: Terminal) -> Result<isize, String> {
        let Some((coil, end)) = terminal else {
            return Ok(REF);
        };
        if coil >= self.coils.len() {
            return Err(format!(
                "coil index {coil} out of range (have {} coils)",
                self.coils.len()
            ));
        }
        Ok(match end {
            End::Start => self.node_offsets[coil],
            End::End => self.node_offsets[coil] + self.coils[coil].n_turns,
        } as isize)
    }

    fn n_turns(&self) -> usize {
        *self.turn_offsets.last().unwrap()
    }

    fn n_nodes(&self) -> usize {
        *self.node_offsets.last().unwrap()
    }

    /// Turn branch impedance matrix `R + jωL` at `freq` [ohm], `(T, T)`.
    pub fn branch_impedance(&self, freq: f64) -> Vec<c64> {
        let nt = self.n_turns();
        let omega = 2.0 * PI * freq;
        let jw = c64::new(0.0, omega);
        let mut z: Vec<c64> = self.l_ext.iter().map(|&l| jw * l).collect();
        for t in 0..nt {
            let zint = internal_impedance_per_length(self.wire_radius[t], freq, self.rho);
            let r = zint.re * self.turn_length[t] * self.r_factor;
            let l_int = zint.im / omega * self.turn_circ[t];
            z[t * nt + t] += c64::new(r, 0.0) + jw * l_int;
        }
        z
    }

    /// Port impedances, turn currents and node voltages at each frequency.
    pub fn solve(&self, freqs: &[f64]) -> Result<NetworkResult, String> {
        let (nt, nn, np) = (self.n_turns(), self.n_nodes(), self.ports.len());
        let fnodes = &self.free_nodes;
        let nf = fnodes.len();
        let pos = |n: isize| fnodes.iter().position(|&f| f as isize == n);
        let n = nf + nt;
        let mut rhs = vec![c64::new(0.0, 0.0); n * np];
        for (p, &(plus, minus)) in self.ports.iter().enumerate() {
            if let Some(i) = pos(plus) {
                rhs[i * np + p] += 1.0;
            }
            if let Some(i) = pos(minus) {
                rhs[i * np + p] -= 1.0;
            }
        }
        // incidence restricted to free nodes: +1 at a turn's from-node, -1 at its to-node
        let mut a_free = vec![0.0; nf * nt];
        for (i, c) in self.coils.iter().enumerate() {
            for k in 0..c.n_turns {
                let t = self.turn_offsets[i] + k;
                let n0 = (self.node_offsets[i] + k) as isize;
                if let Some(r) = pos(n0) {
                    a_free[r * nt + t] = 1.0;
                }
                if let Some(r) = pos(n0 + 1) {
                    a_free[r * nt + t] = -1.0;
                }
            }
        }
        let mut res = NetworkResult {
            freqs: freqs.to_vec(),
            z: Vec::with_capacity(freqs.len() * np * np),
            turn_currents: Vec::with_capacity(freqs.len() * np * nt),
            node_voltages: Vec::with_capacity(freqs.len() * np * nn),
        };
        let mut m = vec![c64::new(0.0, 0.0); n * n];
        for &f in freqs {
            let jw = c64::new(0.0, 2.0 * PI * f);
            let zb = self.branch_impedance(f);
            for (r, &fr) in fnodes.iter().enumerate() {
                for (c, &fc) in fnodes.iter().enumerate() {
                    m[r * n + c] = jw * self.c_node[fr * nn + fc];
                }
                for t in 0..nt {
                    m[r * n + nf + t] = c64::new(a_free[r * nt + t], 0.0);
                    m[(nf + t) * n + r] = c64::new(a_free[r * nt + t], 0.0);
                }
            }
            for t in 0..nt {
                for u in 0..nt {
                    m[(nf + t) * n + nf + u] = -zb[t * nt + u];
                }
            }
            let x = solve_lu(&m, &rhs, n, np).ok_or("singular network matrix")?;
            // node voltages with an extra zero row for REF
            let mut v = vec![c64::new(0.0, 0.0); (nn + 1) * np];
            for (r, &fr) in fnodes.iter().enumerate() {
                v[fr * np..(fr + 1) * np].copy_from_slice(&x[r * np..(r + 1) * np]);
            }
            let row = |node: isize| if node == REF { nn } else { node as usize };
            for &(plus, minus) in &self.ports {
                for p in 0..np {
                    res.z.push(v[row(plus) * np + p] - v[row(minus) * np + p]);
                }
            }
            for p in 0..np {
                res.turn_currents
                    .extend((0..nt).map(|t| x[(nf + t) * np + p]));
                res.node_voltages.extend((0..nn).map(|k| v[k * np + p]));
            }
        }
        Ok(res)
    }

    fn z_port(&self, freqs: &[f64], port: usize) -> Result<Vec<c64>, String> {
        let np = self.ports.len();
        let r = self.solve(freqs)?;
        Ok((0..freqs.len())
            .map(|f| r.z[(f * np + port) * np + port])
            .collect())
    }

    /// First parallel self-resonance at `port` (other ports open) [Hz], or NaN: the first
    /// + to − sign change of Im(Z_ii) on a log scan, refined by Brent on Im(1/Z_ii).
    pub fn srf(&self, port: usize, f_lo: f64, f_hi: f64, n_scan: usize) -> Result<f64, String> {
        let fs = geomspace(f_lo, f_hi, n_scan);
        let x: Vec<f64> = self.z_port(&fs, port)?.iter().map(|z| z.im).collect();
        let Some(k) = (0..n_scan - 1).find(|&k| x[k] > 0.0 && x[k + 1] <= 0.0) else {
            return Ok(f64::NAN);
        };
        let mut err = None;
        let mut g = |f: f64| match self.z_port(&[f], port) {
            Ok(z) => recip(z[0]).im,
            Err(e) => {
                err = Some(e);
                f64::NAN
            }
        };
        let root = brentq(
            &mut g,
            fs[k],
            fs[k + 1],
            1e-6 * fs[k],
            4.0 * f64::EPSILON,
            100,
        );
        if let Some(e) = err {
            return Err(e);
        }
        root
    }

    /// First parallel resonance at `port` with its Q (from the slope of the port
    /// susceptance) and the impedance at resonance.
    pub fn resonance(&self, port: usize, f_lo: f64, f_hi: f64) -> Result<Resonance, String> {
        let f0 = self.srf(port, f_lo, f_hi, 400)?;
        if !f0.is_finite() {
            return Ok(Resonance {
                freq: f64::NAN,
                q: f64::NAN,
                r_parallel: f64::NAN,
            });
        }
        let e = 1e-5;
        let y: Vec<c64> = self
            .z_port(&[f0 * (1.0 - e), f0, f0 * (1.0 + e)], port)?
            .into_iter()
            .map(recip)
            .collect();
        let w0 = 2.0 * PI * f0;
        let db_dw = (y[2].im - y[0].im) / (2.0 * e * w0);
        Ok(Resonance {
            freq: f0,
            q: w0 * db_dw / (2.0 * y[1].re),
            r_parallel: 1.0 / y[1].re,
        })
    }
}

/// `1 / z` with Smith's algorithm, as numpy divides complex numbers.
fn recip(z: c64) -> c64 {
    if z.re.abs() >= z.im.abs() {
        let rat = z.im / z.re;
        let scl = 1.0 / (z.re + z.im * rat);
        c64::new(scl, -rat * scl)
    } else {
        let rat = z.re / z.im;
        let scl = 1.0 / (z.im + z.re * rat);
        c64::new(rat * scl, -scl)
    }
}

/// `numpy.geomspace(start, stop, num)`.
pub fn geomspace(start: f64, stop: f64, num: usize) -> Vec<f64> {
    let (l0, l1) = (start.log10(), stop.log10());
    let step = (l1 - l0) / (num - 1) as f64;
    let mut out: Vec<f64> = (0..num).map(|i| 10f64.powf(i as f64 * step + l0)).collect();
    out[0] = start;
    out[num - 1] = stop;
    out
}

/// `scipy.optimize.brentq` (port of scipy's `brentq.c`); an error if not converged.
pub fn brentq(
    f: &mut dyn FnMut(f64) -> f64,
    xa: f64,
    xb: f64,
    xtol: f64,
    rtol: f64,
    iter: usize,
) -> Result<f64, String> {
    let (mut xpre, mut xcur) = (xa, xb);
    let (mut xblk, mut fblk, mut spre, mut scur) = (0.0, 0.0, 0.0, 0.0);
    let mut fpre = f(xpre);
    let mut fcur = f(xcur);
    if fpre == 0.0 {
        return Ok(xpre);
    }
    if fcur == 0.0 {
        return Ok(xcur);
    }
    if fpre.is_sign_negative() == fcur.is_sign_negative() {
        return Err("f(a) and f(b) must have different signs".into());
    }
    for _ in 0..iter {
        if fpre != 0.0 && fcur != 0.0 && fpre.is_sign_negative() != fcur.is_sign_negative() {
            xblk = xpre;
            fblk = fpre;
            scur = xcur - xpre;
            spre = scur;
        }
        if fblk.abs() < fcur.abs() {
            xpre = xcur;
            xcur = xblk;
            xblk = xpre;
            fpre = fcur;
            fcur = fblk;
            fblk = fpre;
        }
        let delta = (xtol + rtol * xcur.abs()) / 2.0;
        let sbis = (xblk - xcur) / 2.0;
        if fcur == 0.0 || sbis.abs() < delta {
            return Ok(xcur);
        }
        if spre.abs() > delta && fcur.abs() < fpre.abs() {
            let stry = if xpre == xblk {
                -fcur * (xcur - xpre) / (fcur - fpre) // interpolate
            } else {
                let dpre = (fpre - fcur) / (xpre - xcur); // extrapolate
                let dblk = (fblk - fcur) / (xblk - xcur);
                -fcur * (fblk * dblk - fpre * dpre) / (dblk * dpre * (fblk - fpre))
            };
            if 2.0 * stry.abs() < spre.abs().min(3.0 * sbis.abs() - delta) {
                spre = scur; // good short step
                scur = stry;
            } else {
                spre = sbis;
                scur = sbis;
            }
        } else {
            spre = sbis;
            scur = sbis;
        }
        xpre = xcur;
        fpre = fcur;
        xcur += if scur.abs() > delta {
            scur
        } else if sbis > 0.0 {
            delta
        } else {
            -delta
        };
        fcur = f(xcur);
    }
    Err(format!(
        "brentq failed to converge after {iter} iterations, value is {xcur}"
    ))
}
