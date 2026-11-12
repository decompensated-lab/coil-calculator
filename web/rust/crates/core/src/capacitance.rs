//! Electrostatics of coil turns: Maxwell capacitance matrix between turns.
//!
//! Port of `coilcal/capacitance.py`, step for step (same discretisation, adaptive panel
//! quadrature, meshing decisions and system layout); see the Python module docstring for the
//! method: charge simulation for the wires with the insulation sleeve eliminated by its
//! per-harmonic Dirichlet-to-Neumann map, boundary elements for the former, and a thin-wire
//! coupling between non-coaxial coils. [`capacitance_matrix`] is uncached (the benchmarks time
//! it); [`capacitance_matrix_cached`] memoises per geometry like the Python module and is what
//! the network uses.

use crate::c64;
use crate::geometry::{Coil, Vec3, apply, apply_t, dot, norm, sub};
use crate::linalg::solve_lu;
use crate::special::{ellipe, ellipkm1};
use std::f64::consts::PI;

/// `scipy.constants.epsilon_0` (CODATA 2022) [F/m].
pub const EPS0: f64 = 8.8541878188e-12;
const K: f64 = 1.0 / (4.0 * PI * EPS0);

/// `numpy.polynomial.legendre.leggauss(8)` and `(2)`, bit for bit.
pub const GL8_X: [f64; 8] = [
    -0.9602898564975362,
    -0.7966664774136267,
    -0.525532409916329,
    -0.18343464249564978,
    0.18343464249564978,
    0.525532409916329,
    0.7966664774136267,
    0.9602898564975362,
];
pub const GL8_W: [f64; 8] = [
    0.10122853629037706,
    0.22238103445337443,
    0.3137066458778869,
    0.36268378337836166,
    0.36268378337836166,
    0.3137066458778869,
    0.22238103445337443,
    0.10122853629037706,
];
pub const GL2_X: [f64; 2] = [-0.5773502691896257, 0.5773502691896257];
pub const GL2_W: [f64; 2] = [1.0, 1.0];

// --- ring-charge kernels -----------------------------------------------------------------

/// Potential [V] at cylindrical (rho, z) of a ring of radius `b` in z = 0 carrying 1 C.
pub fn ring_potential(b: f64, rho: f64, z: f64) -> f64 {
    let d2 = (b + rho).powi(2) + z * z;
    let m1 = ((b - rho).powi(2) + z * z) / d2; // 1 - m, computed without cancellation
    K * (2.0 / PI) * ellipkm1(m1) / d2.sqrt()
}

/// Potential, E_rho and E_z of a 1 C ring (radius b, plane z = 0) at (rho > 0, z).
pub fn ring_all(b: f64, rho: f64, z: f64) -> (f64, f64, f64) {
    let d2 = (b + rho).powi(2) + z * z;
    let q2 = (b - rho).powi(2) + z * z;
    let m1 = q2 / d2;
    let k = ellipkm1(m1);
    let e = ellipe(1.0 - m1);
    let sd = d2.sqrt();
    let phi = K * (2.0 / PI) * k / sd;
    let ez = K * (2.0 / PI) * z * e / (q2 * sd);
    let er = K / PI * (k - (b * b - rho * rho + z * z) / q2 * e) / (rho * sd);
    (phi, er, ez)
}

// --- coaxial groups --------------------------------------------------------------------

fn cross(a: Vec3, b: Vec3) -> Vec3 {
    [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]
}

/// Common axis origin/direction for a coaxial group, or None if not coaxial.
fn axial_frame(coils: &[&Coil]) -> Option<(Vec3, Vec3)> {
    let rf = coils[0];
    let ax = rf.axis();
    for c in &coils[1..] {
        if norm(cross(ax, c.axis())) > 1e-12 {
            return None;
        }
        let d = sub(c.position, rf.position);
        let along = dot(d, ax);
        if norm(std::array::from_fn(|i| d[i] - along * ax[i])) > 1e-12 * rf.mean_radius().max(1.0) {
            return None;
        }
    }
    Some((rf.position, ax))
}

fn coaxial_groups(coils: &[Coil]) -> Vec<Vec<usize>> {
    let mut groups: Vec<Vec<usize>> = Vec::new();
    for (i, c) in coils.iter().enumerate() {
        match groups
            .iter_mut()
            .find(|g| axial_frame(&[&coils[g[0]], c]).is_some())
        {
            Some(g) => g.push(i),
            None => groups.push(vec![i]),
        }
    }
    groups
}

/// Average potential on each turn of `a` per coulomb on each turn of `b`, row-major (NA, NB).
fn thin_ring_potential_coeffs(a: &Coil, b: &Coil, n_phi: usize) -> Vec<f64> {
    let (ra, rb) = (a.rotation(), b.rotation());
    let ring: Vec<Vec3> = (0..n_phi)
        .map(|k| {
            let phi = 2.0 * PI * k as f64 / n_phi as f64;
            apply(
                &ra,
                [
                    phi.cos() * a.mean_radius(),
                    phi.sin() * a.mean_radius(),
                    0.0,
                ],
            )
        })
        .collect();
    let (ca, cb) = (a.turn_centers(), b.turn_centers());
    let mut out = vec![0.0; ca.len() * cb.len()];
    for (j, cbj) in cb.iter().enumerate() {
        for (i, cai) in ca.iter().enumerate() {
            let sum: f64 = ring
                .iter()
                .map(|p| {
                    let q = apply_t(&rb, std::array::from_fn(|l| cai[l] + p[l] - cbj[l]));
                    ring_potential(b.mean_radius(), q[0].hypot(q[1]), q[2])
                })
                .sum();
            out[i * cb.len() + j] = sum / n_phi as f64;
        }
    }
    out
}

// --- geometry of one coaxial group in its (rho, z) half-plane ------------------------------

/// All turns of a coaxial group: centre (r, z), conductor radius a, insulation radius b, ε.
#[derive(Default)]
struct Wires {
    r: Vec<f64>,
    z: Vec<f64>,
    a: Vec<f64>,
    b: Vec<f64>,
    eps: Vec<c64>,
}

#[derive(Clone, Copy, PartialEq)]
struct Tube {
    r_in: f64,
    r_out: f64,
    z0: f64,
    z1: f64,
    eps: c64,
}

/// Straight ring panels in the (rho, z) half-plane with uniform surface charge.
#[derive(Default)]
struct Panels {
    p1: Vec<[f64; 2]>,
    p2: Vec<[f64; 2]>,
    lam: Vec<c64>, // (ε − 1)/(ε + 1)
}

impl Panels {
    fn len(&self) -> usize {
        self.p1.len()
    }
    fn mid(&self, j: usize) -> [f64; 2] {
        [
            0.5 * (self.p1[j][0] + self.p2[j][0]),
            0.5 * (self.p1[j][1] + self.p2[j][1]),
        ]
    }
    fn half(&self, j: usize) -> [f64; 2] {
        [
            0.5 * (self.p2[j][0] - self.p1[j][0]),
            0.5 * (self.p2[j][1] - self.p1[j][1]),
        ]
    }
    fn seg(&self, j: usize) -> [f64; 2] {
        [self.p2[j][0] - self.p1[j][0], self.p2[j][1] - self.p1[j][1]]
    }
    fn length(&self, j: usize) -> f64 {
        let s = self.seg(j);
        (s[0] * s[0] + s[1] * s[1]).sqrt()
    }
    /// Unit normal pointing out of the dielectric (boundary traversed counter-clockwise).
    fn normal(&self, j: usize) -> [f64; 2] {
        let (s, l) = (self.seg(j), self.length(j));
        [s[1] / l, -(s[0] / l)]
    }
    fn area(&self, j: usize) -> f64 {
        2.0 * PI * self.mid(j)[0] * self.length(j)
    }
}

fn group_geometry(coils: &[&Coil], origin: Vec3, axis: Vec3) -> Result<(Wires, Vec<Tube>), String> {
    let mut w = Wires::default();
    let mut tubes = Vec::new();
    for c in coils {
        let sgn = dot(c.axis(), axis).signum();
        let z0 = dot(sub(c.position, origin), axis) * sgn;
        let n = c.n_turns;
        w.r.extend(std::iter::repeat_n(c.mean_radius(), n));
        w.z.extend(c.turn_z().iter().map(|tz| z0 + sgn * tz));
        w.a.extend(std::iter::repeat_n(c.wire_radius(), n));
        w.b.extend(std::iter::repeat_n(c.outer_radius(), n));
        w.eps.extend(std::iter::repeat_n(c.sleeve_eps(), n));
        if let Some(f) = c.former
            && f.eps != c64::new(1.0, 0.0)
        {
            let half = c.length() / 2.0 + f.overhang;
            let ro = c.former_d / 2.0;
            tubes.push(Tube {
                r_in: ro - f.wall,
                r_out: ro,
                z0: z0 - half,
                z1: z0 + half,
                eps: f.eps,
            });
        }
    }
    let tubes = merge_tubes(tubes, &w)?;
    Ok((w, tubes))
}

/// Join identical tubes that touch or overlap axially; reject intersecting bodies.
fn merge_tubes(mut tubes: Vec<Tube>, w: &Wires) -> Result<Vec<Tube>, String> {
    tubes.sort_by(|s, t| {
        (s.r_in, s.r_out, s.z0)
            .partial_cmp(&(t.r_in, t.r_out, t.z0))
            .unwrap()
    });
    let mut merged: Vec<Tube> = Vec::new();
    for t in tubes {
        match merged.last_mut() {
            Some(last)
                if (last.r_in, last.r_out, last.eps) == (t.r_in, t.r_out, t.eps)
                    && t.z0 <= last.z1 =>
            {
                last.z1 = last.z1.max(t.z1);
            }
            _ => merged.push(t),
        }
    }
    for (i, t) in merged.iter().enumerate() {
        for u in &merged[i + 1..] {
            if t.r_in < u.r_out && u.r_in < t.r_out && t.z0 < u.z1 && u.z0 < t.z1 {
                return Err("coil formers intersect (overlapping tubes of different specs)".into());
            }
        }
        // distance from each wire centre to the tube's rectangle must be >= its outer radius
        for k in 0..w.r.len() {
            let dr = (t.r_in - w.r[k]).max(w.r[k] - t.r_out).max(0.0);
            let dz = (t.z0 - w.z[k]).max(w.z[k] - t.z1).max(0.0);
            if dr.hypot(dz) < w.b[k] * (1.0 - 1e-9) {
                return Err("a winding intersects a coil former".into());
            }
        }
    }
    Ok(merged)
}

/// Panels on each tube's boundary, sized ~0.4 × distance to the nearest wire or corner.
fn mesh_tubes(tubes: &[Tube], w: &Wires, h_min: f64) -> Panels {
    let mut pan = Panels::default();
    for t in tubes {
        let h_max = h_min.max(0.2 * t.r_out).max(0.1 * (t.z1 - t.z0));
        let corners = [
            [t.r_in, t.z0],
            [t.r_out, t.z0],
            [t.r_out, t.z1],
            [t.r_in, t.z1],
        ];
        for e in 0..4 {
            let (c0, c1) = (corners[e], corners[(e + 1) % 4]);
            let diff = [c1[0] - c0[0], c1[1] - c0[1]];
            let length = (diff[0] * diff[0] + diff[1] * diff[1]).sqrt();
            let d = [diff[0] / length, diff[1] / length];
            let nvec = [d[1], -d[0]]; // outward normal of this edge

            // a wire touching this edge gets a panel centred on the contact point, so that no
            // panel edge (where the piecewise-constant charge jumps) sits under the contact
            let mut forced = Vec::new();
            for k in 0..w.r.len() {
                let rel = [w.r[k] - c0[0], w.z[k] - c0[1]];
                let along = rel[0] * d[0] + rel[1] * d[1];
                let off = rel[0] * nvec[0] + rel[1] * nvec[1];
                if (off - w.b[k]).abs() < 1e-9 * w.b[k] && along > 0.0 && along < length {
                    forced.extend([along - h_min / 2.0, along + h_min / 2.0]);
                }
            }
            forced.sort_by(f64::total_cmp);
            forced.retain(|&f| f > 0.0 && f < length);

            let mut nodes = vec![0.0];
            for target in forced.into_iter().chain([length]) {
                let start = *nodes.last().unwrap();
                if target <= start {
                    continue;
                }
                let mut s_loc = vec![start];
                while *s_loc.last().unwrap() < target {
                    let sv = *s_loc.last().unwrap();
                    let p = [c0[0] + d[0] * sv, c0[1] + d[1] * sv];
                    let dw = (0..w.r.len())
                        .map(|k| (w.r[k] - p[0]).hypot(w.z[k] - p[1]) - w.b[k])
                        .fold(f64::INFINITY, f64::min);
                    let dist = dw.min(sv).min(length - sv);
                    s_loc.push(sv + (0.4 * dist).max(h_min).min(h_max));
                }
                let last = *s_loc.last().unwrap();
                nodes.extend(
                    s_loc[1..]
                        .iter()
                        .map(|s| start + (s - start) * (target - start) / (last - start)),
                );
            }
            let lam = (t.eps - 1.0) / (t.eps + 1.0);
            for pair in nodes.windows(2) {
                pan.p1
                    .push([c0[0] + pair[0] * d[0], c0[1] + pair[0] * d[1]]);
                pan.p2
                    .push([c0[0] + pair[1] * d[0], c0[1] + pair[1] * d[1]]);
                pan.lam.push(lam);
            }
        }
    }
    pan
}

/// Quadrature level for panel `j` seen from (tr, tz): 0 = 2-point Gauss on the whole panel,
/// n >= 1 = n sub-panels with 8 points each (subdivided close to the panel).
fn panel_level(pan: &Panels, j: usize, tr: f64, tz: f64) -> usize {
    let (p1, seg, length) = (pan.p1[j], pan.seg(j), pan.length(j));
    let rel = [tr - p1[0], tz - p1[1]];
    let tpar = ((rel[0] * seg[0] + rel[1] * seg[1]) / (length * length)).clamp(0.0, 1.0);
    let dv = [rel[0] - tpar * seg[0], rel[1] - tpar * seg[1]];
    let dist = (dv[0] * dv[0] + dv[1] * dv[1]).sqrt();
    let ratio = length / dist.max(1e-300);
    if ratio < 0.15 {
        0
    } else if ratio < 0.5 {
        1
    } else {
        1 << ((4.0 * ratio).log2().ceil().clamp(1.0, 9.0) as u32)
    }
}

/// Potential, E_rho, E_z at (tr, tz) per unit total charge on panel `j`.
fn panel_eval(pan: &Panels, j: usize, tr: f64, tz: f64, level: usize) -> (f64, f64, f64) {
    let (mid, half) = (pan.mid(j), pan.half(j));
    let mut acc = (0.0, 0.0, 0.0);
    let mut point = |x: f64, w: f64| {
        let qr = mid[0] + x * half[0];
        let qz = mid[1] + x * half[1];
        // charge weight per unit panel charge: dq = σ 2πρ ds with σ = 1/area
        let wq = w * qr / (2.0 * mid[0]);
        let (phi, er, ez) = ring_all(qr, tr, tz - qz);
        acc.0 += wq * phi;
        acc.1 += wq * er;
        acc.2 += wq * ez;
    };
    if level == 0 {
        for (x, w) in GL2_X.into_iter().zip(GL2_W) {
            point(x, w);
        }
    } else {
        let n = level as f64;
        for i in 0..level {
            for (gx, gw) in GL8_X.into_iter().zip(GL8_W) {
                point(((2 * i + 1) as f64 + gx) / n - 1.0, gw / n);
            }
        }
    }
    acc
}

/// Real DFT on the collocation angles: row-major (M, M) matrix and each row's harmonic.
fn dft_rows(m: usize) -> (Vec<f64>, Vec<usize>) {
    let theta: Vec<f64> = (0..m)
        .map(|j| 2.0 * PI * (j as f64 + 0.5) / m as f64)
        .collect();
    let mf = m as f64;
    let mut rows = vec![1.0 / mf; m];
    let mut harm = vec![0];
    for k in 1..m / 2 {
        rows.extend(theta.iter().map(|t| 2.0 / mf * (k as f64 * t).cos()));
        rows.extend(theta.iter().map(|t| 2.0 / mf * (k as f64 * t).sin()));
        harm.extend([k, k]);
    }
    // cos(M/2·θ) vanishes on these angles
    rows.extend(theta.iter().map(|t| 1.0 / mf * ((m / 2) as f64 * t).sin()));
    harm.push(m / 2);
    (rows, harm)
}

/// Sleeve DtN coefficients of harmonic `k` for one wire, normalised:
/// `p · b·∂φ/∂r − q · φ = −q0 · V` (the right-hand side only for k = 0).
fn dtn(a: f64, b: f64, eps: c64, k: usize) -> (f64, c64) {
    let u = (a / b).powf(2.0 * k as f64);
    let p = if k == 0 { (b / a).ln() } else { 1.0 - u };
    let q = if k == 0 {
        eps
    } else {
        k as f64 * eps * (1.0 + u)
    };
    let scale = 4.0 * PI * EPS0 * b / (p.abs() + q.norm());
    (p * scale, q * scale)
}

// --- main solver ---------------------------------------------------------------------

/// Discretisation options; defaults as in `capacitance_matrix`.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Options {
    /// Ring charges per turn (even, >= 4); `None` = [`auto_n_sub`].
    pub n_sub: Option<usize>,
    pub alpha: f64,
    pub n_phi: usize,
    pub h_wire: f64,
}

impl Default for Options {
    fn default() -> Self {
        Self {
            n_sub: None,
            alpha: 0.6,
            n_phi: 256,
            h_wire: 0.6,
        }
    }
}

/// Charge rings per turn for ~1e-3 accuracy of the turn-to-turn capacitance.
pub fn auto_n_sub(coils: &[Coil]) -> usize {
    let mut n: f64 = 16.0;
    for c in coils {
        let g = (c.pitch - c.wire_d).max(1e-12);
        n = n.max(16.0 * (c.outer_radius() / g).sqrt());
    }
    64.0_f64.min(8.0 * (n / 8.0).ceil()) as usize
}

/// The linear system of the charge simulation, row-major.
pub struct System {
    /// `n x n`.
    pub a: Vec<c64>,
    /// `n x n_turns`: one right-hand side per driven turn.
    pub rhs: Vec<c64>,
    pub n: usize,
    pub n_turns: usize,
    pub n_sub: usize,
    /// True if a dielectric is lossy; otherwise all imaginary parts are zero.
    pub lossy: bool,
}

/// Assembles the system that `capacitance._solve` passes to `numpy.linalg.solve`.
pub fn system(coils: &[Coil], opt: &Options) -> Result<System, String> {
    let m = opt.n_sub.unwrap_or_else(|| auto_n_sub(coils));
    if !m.is_multiple_of(2) || m < 4 {
        return Err("n_sub must be even and >= 4".into());
    }
    let mut toffs = vec![0];
    for c in coils {
        toffs.push(toffs.last().unwrap() + c.n_turns);
    }
    let n_total = *toffs.last().unwrap();
    let nw = n_total * m; // wire unknowns (and rows): turn t, sub-index -> t*m + j
    let groups = coaxial_groups(coils);
    let theta: Vec<f64> = (0..m)
        .map(|j| 2.0 * PI * (j as f64 + 0.5) / m as f64)
        .collect();
    let (cos_t, sin_t): (Vec<f64>, Vec<f64>) = theta.iter().map(|t| (t.cos(), t.sin())).unzip();
    let (fmat, harm) = dft_rows(m);

    // geometry, panels and global index of every group's turns / panels
    let mut geo = Vec::new();
    let mut n_pan_total = 0;
    for g in &groups {
        let gc: Vec<&Coil> = g.iter().map(|&i| &coils[i]).collect();
        let (origin, axis) = axial_frame(&gc).expect("groups are coaxial by construction");
        let (wires, tubes) = group_geometry(&gc, origin, axis)?;
        // panels near a wire must be finer than its collocation spacing (2πb/M)
        let bmin = wires.b.iter().copied().fold(f64::INFINITY, f64::min);
        let pan = mesh_tubes(&tubes, &wires, opt.h_wire * PI * bmin / m as f64);
        let turns: Vec<usize> = g.iter().flat_map(|&i| toffs[i]..toffs[i + 1]).collect();
        let poff = nw + n_pan_total;
        n_pan_total += pan.len();
        geo.push((wires, pan, turns, poff));
    }
    let nu = nw + n_pan_total;
    let lossy = geo
        .iter()
        .any(|(w, p, ..)| w.eps.iter().any(|e| e.im != 0.0) || p.lam.iter().any(|l| l.im != 0.0));

    let mut a = vec![c64::new(0.0, 0.0); nu * nu];
    let mut rhs = vec![c64::new(0.0, 0.0); nu * n_total];

    for (wires, pan, turns, poff) in &geo {
        let tg = wires.r.len();
        // charge rings, flattened turn-major
        let mut sr = Vec::with_capacity(tg * m);
        let mut sz = Vec::with_capacity(tg * m);
        for t in 0..tg {
            for j in 0..m {
                sr.push(wires.r[t] + opt.alpha * wires.b[t] * cos_t[j]);
                sz.push(wires.z[t] + opt.alpha * wires.b[t] * sin_t[j]);
            }
        }
        let cols_w: Vec<usize> = turns.iter().flat_map(|&t| t * m..(t + 1) * m).collect();
        let npan = pan.len();
        let ncols = cols_w.len() + npan;
        assemble_wire_rows(
            &mut a, nu, m, wires, pan, turns, *poff, &sr, &sz, &cols_w, &cos_t, &sin_t, &fmat,
            &harm, ncols,
        );
        for (t, &turn) in turns.iter().enumerate() {
            let (_, q0) = dtn(wires.a[t], wires.b[t], wires.eps[t], 0);
            rhs[turn * m * n_total + turn] = -q0;
        }
        // former panels: total-charge BEM rows
        for p in 0..npan {
            let (mid, nrm) = (pan.mid(p), pan.normal(p));
            let fac = 2.0 * EPS0 * pan.lam[p] * pan.area(p);
            let row = &mut a[(poff + p) * nu..(poff + p + 1) * nu];
            for (u, &col) in cols_w.iter().enumerate() {
                let (_, er, ez) = ring_all(sr[u], mid[0], mid[1] - sz[u]);
                row[col] = -(fac * (er * nrm[0] + ez * nrm[1]));
            }
            for q in 0..npan {
                let level = if q == p {
                    16
                } else {
                    panel_level(pan, q, mid[0], mid[1])
                };
                let (_, per, pez) = panel_eval(pan, q, mid[0], mid[1], level);
                let eye = if q == p { 1.0 } else { 0.0 };
                row[poff + q] = eye - fac * (per * nrm[0] + pez * nrm[1]);
            }
        }
    }

    // thin-wire coupling between coaxial groups (enters the k = 0 row of each turn)
    for (gi, g) in groups.iter().enumerate() {
        for h in &groups[gi + 1..] {
            for &i in g {
                for &j in h {
                    let pij = thin_ring_potential_coeffs(&coils[i], &coils[j], opt.n_phi);
                    let nj = coils[j].n_turns;
                    for (x, y, transposed) in [(i, j, false), (j, i, true)] {
                        let c = &coils[x];
                        let (_, q0) = dtn(c.wire_radius(), c.outer_radius(), c.sleeve_eps(), 0);
                        for tx in 0..coils[x].n_turns {
                            let row = (toffs[x] + tx) * m;
                            for ty in 0..coils[y].n_turns {
                                let pxy = if transposed {
                                    pij[ty * nj + tx]
                                } else {
                                    pij[tx * nj + ty]
                                };
                                for s in 0..m {
                                    a[row * nu + (toffs[y] + ty) * m + s] = -(q0 * pxy);
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    Ok(System {
        a,
        rhs,
        n: nu,
        n_turns: n_total,
        n_sub: m,
        lossy,
    })
}

/// Rows of the wire collocation conditions of one group (one turn at a time).
#[allow(clippy::too_many_arguments)]
#[inline(never)] // keeps the hot loop a separate function for V8's tier-up
fn assemble_wire_rows(
    a: &mut [c64],
    nu: usize,
    m: usize,
    wires: &Wires,
    pan: &Panels,
    turns: &[usize],
    poff: usize,
    sr: &[f64],
    sz: &[f64],
    cols_w: &[usize],
    cos_t: &[f64],
    sin_t: &[f64],
    fmat: &[f64],
    harm: &[usize],
    ncols: usize,
) {
    let nw_g = cols_w.len();
    let mut ph = vec![0.0; m * ncols];
    let mut dr = vec![0.0; m * ncols];
    let mut ph3 = vec![0.0; ncols];
    let mut dr3 = vec![0.0; ncols];
    for (t, &turn) in turns.iter().enumerate() {
        // potential and ∂φ/∂r = −E·n at the turn's collocation rings, per unit source charge
        for j in 0..m {
            let cr = wires.r[t] + wires.b[t] * cos_t[j];
            let cz = wires.z[t] + wires.b[t] * sin_t[j];
            let (php, drp) = (
                &mut ph[j * ncols..(j + 1) * ncols],
                &mut dr[j * ncols..(j + 1) * ncols],
            );
            for u in 0..nw_g {
                let (phi, er, ez) = ring_all(sr[u], cr, cz - sz[u]);
                php[u] = phi;
                drp[u] = -(cos_t[j] * er + sin_t[j] * ez);
            }
            for q in 0..pan.len() {
                let (phi, er, ez) = panel_eval(pan, q, cr, cz, panel_level(pan, q, cr, cz));
                php[nw_g + q] = phi;
                drp[nw_g + q] = -(cos_t[j] * er + sin_t[j] * ez);
            }
        }
        // harmonic rows: p·b·DFT(∂φ/∂r) − q·DFT(φ)
        for r in 0..m {
            ph3.fill(0.0);
            dr3.fill(0.0);
            for j in 0..m {
                let f = fmat[r * m + j];
                for u in 0..ncols {
                    ph3[u] += f * ph[j * ncols + u];
                    dr3[u] += f * dr[j * ncols + u];
                }
            }
            let (p, q) = dtn(wires.a[t], wires.b[t], wires.eps[t], harm[r]);
            let pb = p * wires.b[t];
            let row = &mut a[(turn * m + r) * nu..(turn * m + r + 1) * nu];
            for (u, &col) in cols_w.iter().enumerate() {
                row[col] = pb * dr3[u] - q * ph3[u];
            }
            for qq in 0..pan.len() {
                row[poff + qq] = pb * dr3[nw_g + qq] - q * ph3[nw_g + qq];
            }
        }
    }
}

/// Maxwell capacitance matrix [F], row-major `n_turns x n_turns`; complex only if a
/// dielectric is lossy (as in the reference).
#[derive(Clone)]
pub enum Matrix {
    Real(Vec<f64>),
    Complex(Vec<c64>),
}

/// `capacitance_matrix(coils, n_sub, alpha, n_phi, h_wire)` of the reference.
pub fn capacitance_matrix(coils: &[Coil], opt: &Options) -> Result<Matrix, String> {
    let s = system(coils, opt)?;
    let (n, nt, m) = (s.n, s.n_turns, s.n_sub);
    let sol: Vec<c64> = if s.lossy {
        solve_lu(&s.a, &s.rhs, n, nt).ok_or("singular capacitance system")?
    } else {
        let re = |v: &[c64]| v.iter().map(|z| z.re).collect::<Vec<_>>();
        let (a, rhs) = (re(&s.a), re(&s.rhs));
        drop(s.a);
        let x = solve_lu(&a, &rhs, n, nt).ok_or("singular capacitance system")?;
        x.into_iter().map(|v| c64::new(v, 0.0)).collect()
    };
    // C[i, j] = Σ_sub charge of turn i for 1 V on turn j, then symmetrised
    let mut c = vec![c64::new(0.0, 0.0); nt * nt];
    for i in 0..nt {
        for s_ in 0..m {
            let row = &sol[(i * m + s_) * nt..(i * m + s_ + 1) * nt];
            for (cj, x) in c[i * nt..(i + 1) * nt].iter_mut().zip(row) {
                *cj += x;
            }
        }
    }
    let sym: Vec<c64> = (0..nt * nt)
        .map(|ij| 0.5 * (c[ij] + c[(ij % nt) * nt + ij / nt]))
        .collect();
    Ok(if s.lossy {
        Matrix::Complex(sym)
    } else {
        Matrix::Real(sym.iter().map(|z| z.re).collect())
    })
}

/// Results kept by [`capacitance_matrix_cached`] (the reference keeps 32 as well).
const CACHE_SIZE: usize = 32;
type CacheEntry = (Vec<Coil>, Options, Matrix);
static CACHE: std::sync::Mutex<Vec<CacheEntry>> = std::sync::Mutex::new(Vec::new());

/// [`capacitance_matrix`] memoised per geometry, like the reference's `capacitance_matrix`: one
/// app update builds up to six networks over the same coils, and changing only the frequency,
/// drive or VNA setup reuses every matrix.
pub fn capacitance_matrix_cached(coils: &[Coil], opt: &Options) -> Result<Matrix, String> {
    let lookup = |cache: &mut Vec<CacheEntry>| {
        let i = cache.iter().position(|(c, o, _)| c == coils && o == opt)?;
        let hit = cache.remove(i);
        let m = hit.2.clone();
        cache.push(hit); // most recently used last
        Some(m)
    };
    if let Some(m) = lookup(&mut CACHE.lock().unwrap()) {
        return Ok(m);
    }
    let m = capacitance_matrix(coils, opt)?;
    let mut cache = CACHE.lock().unwrap();
    cache.push((coils.to_vec(), *opt, m.clone()));
    if cache.len() > CACHE_SIZE {
        cache.remove(0);
    }
    Ok(m)
}
