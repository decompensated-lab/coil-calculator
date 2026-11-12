//! Filamentary circular-loop magnetostatics: vector potential, mutual and self inductance.
//!
//! Port of `coilcal/loops.py`, formula for formula (same branches and thresholds), SI units.
//! The Python functions broadcast over arrays; these take scalars, except [`mutual_rings`].
//! A frequency of 0 means DC (Python accepts `None` or 0 for that).

use crate::c64;
use crate::geometry::{apply, apply_t, quat_matrix};
use crate::special::{ellipe, ellipk, jve};
use std::f64::consts::PI;

/// Vacuum permeability, `scipy.constants.mu_0` (CODATA 2022) [H/m].
pub const MU_0: f64 = 1.256_637_061_27e-6;
/// Resistivity of annealed copper at 20 °C [ohm m].
pub const RHO_CU: f64 = 1.68e-8;

/// Below this value of `m = k^2` the closed form `(1-m/2)K - E` suffers cancellation; use series.
const M_SERIES: f64 = 1e-3;

/// Mutual inductance of two coaxial circular filaments (Maxwell's formula) [H].
pub fn mutual_coaxial(r1: f64, r2: f64, dz: f64) -> f64 {
    let d2 = (r1 + r2).powi(2) + dz * dz;
    let m = 4.0 * r1 * r2 / d2;
    if m < M_SERIES {
        // M = mu0 pi r1^2 r2^2 / (2 D^3) (1 + 3m/4 + 75m^2/128), D = sqrt(d2)
        let ds = d2.sqrt();
        MU_0 * PI * (r1 * r2).powi(2) / (2.0 * ds.powi(3)) * (1.0 + 0.75 * m + 75.0 / 128.0 * m * m)
    } else {
        let k = m.sqrt();
        MU_0 * (r1 * r2).sqrt() * ((2.0 / k - k) * ellipk(m) - (2.0 / k) * ellipe(m))
    }
}

/// Azimuthal vector potential of a unit-current ring, divided by rho [T].
///
/// Ring of radius `a` in the plane z = 0 centred on the origin, 1 A CCW about +z.
pub fn a_phi_over_rho(a: f64, rho: f64, z: f64) -> f64 {
    let d2 = (a + rho).powi(2) + z * z;
    let m = 4.0 * a * rho / d2;
    if m < M_SERIES {
        // A_phi = mu0 a^2 rho / (4 D^3) (1 + 3m/4 + 75m^2/128)
        MU_0 * a * a / (4.0 * d2.powf(1.5)) * (1.0 + 0.75 * m + 75.0 / 128.0 * m * m)
    } else {
        let k = m.sqrt();
        let a_phi = MU_0 / (PI * k) * (a / rho).sqrt() * ((1.0 - m / 2.0) * ellipk(m) - ellipe(m));
        a_phi / rho
    }
}

/// Mutual inductances between two families of arbitrarily placed circular filaments [H].
///
/// `M_ij = oint_{ring b_j} A(ring a_i) . dl` with the analytic ring vector potential and a
/// periodic trapezoidal rule with `n_phi` points. `quat_a`, `quat_b` are the local -> global
/// rotations (ring normal = local z) in scipy's `as_quat()` order (x, y, z, w). Returns the
/// row-major `centers_a.len() x centers_b.len()` matrix.
pub fn mutual_rings(
    radius_a: f64,
    quat_a: [f64; 4],
    centers_a: &[[f64; 3]],
    radius_b: f64,
    quat_b: [f64; 4],
    centers_b: &[[f64; 3]],
    n_phi: usize,
) -> Vec<f64> {
    let (ra, rb) = (quat_matrix(quat_a), quat_matrix(quat_b));
    // ring b's points and tangents (dl/dphi), expressed in ring a's frame
    let (ring, tang): (Vec<_>, Vec<_>) = (0..n_phi)
        .map(|k| {
            let phi = 2.0 * PI * k as f64 / n_phi as f64;
            let (s, c) = phi.sin_cos();
            let p = apply_t(&ra, apply(&rb, [c * radius_b, s * radius_b, 0.0]));
            let t = apply_t(&ra, apply(&rb, [-s * radius_b, c * radius_b, 0.0]));
            (p, t)
        })
        .unzip();
    let mut out = Vec::with_capacity(centers_a.len() * centers_b.len());
    for ca in centers_a {
        for cb in centers_b {
            let c = apply_t(&ra, std::array::from_fn(|i| cb[i] - ca[i]));
            let sum: f64 = ring
                .iter()
                .zip(&tang)
                .map(|(p, t)| {
                    let q: [f64; 3] = std::array::from_fn(|i| c[i] + p[i]);
                    let g = a_phi_over_rho(radius_a, q[0].hypot(q[1]), q[2]);
                    g * (-q[1] * t[0] + q[0] * t[1])
                })
                .sum();
            out.push(sum * (2.0 * PI / n_phi as f64));
        }
    }
    out
}

/// Skin depth in a non-magnetic conductor [m].
pub fn skin_depth(freq: f64, rho: f64) -> f64 {
    (rho / (PI * freq * MU_0)).sqrt()
}

/// Internal impedance per unit length of an isolated round wire (skin effect only) [ohm/m].
pub fn internal_impedance_per_length(wire_radius: f64, freq: f64, rho: f64) -> c64 {
    if freq == 0.0 {
        return c64::new(rho / (PI * wire_radius * wire_radius), 0.0);
    }
    let a = wire_radius;
    let kc = c64::new(1.0, -1.0) / skin_depth(freq, rho);
    // exponentially scaled Bessel functions: the scale factor cancels in the ratio
    kc * rho / (2.0 * PI * a) * jve(0.0, kc * a) / jve(1.0, kc * a)
}

/// Internal inductance per unit length of a straight round wire [H/m]; DC gives `mu0/(8 pi)`.
pub fn internal_inductance_per_length(wire_radius: f64, freq: f64, rho: f64) -> f64 {
    if freq == 0.0 {
        return MU_0 / (8.0 * PI);
    }
    let omega = 2.0 * PI * freq;
    internal_impedance_per_length(wire_radius, freq, rho).im / omega
}

/// Self-inductance of a single circular loop of round copper wire (thin-wire limit) [H].
pub fn loop_self_inductance(radius: f64, wire_radius: f64, freq: f64) -> f64 {
    let external = MU_0 * radius * ((8.0 * radius / wire_radius).ln() - 2.0);
    external + internal_inductance_per_length(wire_radius, freq, RHO_CU) * 2.0 * PI * radius
}
