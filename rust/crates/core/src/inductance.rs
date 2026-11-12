//! Self-inductance, resistance and quick self-capacitance estimates of single-layer coils.
//!
//! Port of `coilcal/inductance.py` and of the two estimates of `coilcal/srf.py` the app shows
//! (Medhurst's empirical self-capacitance and the lumped SRF built on it). A frequency of 0
//! means DC (Python's `None`).

use crate::geometry::Coil;
use crate::loops::{
    MU_0, RHO_CU, internal_impedance_per_length, internal_inductance_per_length,
    loop_self_inductance, mutual_coaxial,
};
use crate::special::{ellipe, ellipk};
use std::f64::consts::PI;

/// Ring-model self-inductance [H]: `N L_turn + 2 Σ_k (N-k) M(k·pitch)`.
pub fn self_inductance(coil: &Coil, freq: f64) -> f64 {
    let (n, r) = (coil.n_turns, coil.mean_radius());
    let l_turn = loop_self_inductance(r, coil.wire_radius(), freq);
    let mutual: f64 = (1..n)
        .map(|k| (n - k) as f64 * mutual_coaxial(r, r, k as f64 * coil.pitch))
        .sum();
    n as f64 * l_turn + 2.0 * mutual
}

/// Nagaoka coefficient K_L of a uniform cylindrical current sheet (exact, elliptic).
pub fn nagaoka(diameter: f64, length: f64) -> f64 {
    let k2 = diameter * diameter / (diameter * diameter + length * length);
    let (k, kp2) = (k2.sqrt(), 1.0 - k2);
    4.0 / (3.0 * PI * kp2.sqrt()) * (kp2 / k2 * (ellipk(k2) - ellipe(k2)) + ellipe(k2) - k)
}

/// Lorenz/Nagaoka current-sheet inductance (diameter = wire-centre diameter) [H].
pub fn sheet_inductance(coil: &Coil) -> f64 {
    let (d, length, n) = (coil.mean_d(), coil.length(), coil.n_turns as f64);
    MU_0 * PI * d * d / 4.0 * (n * n) / length * nagaoka(d, length)
}

/// Rosa's round-wire corrections `(k_s, k_m)` to the current-sheet inductance.
pub fn rosa_corrections(coil: &Coil, freq: f64) -> (f64, f64) {
    let (n, p, d) = (coil.n_turns as f64, coil.pitch, coil.wire_d);
    let y = internal_inductance_per_length(coil.wire_radius(), freq, RHO_CU) * 2.0 * PI / MU_0;
    let ks = 1.5 - y - (2.0 * p / d).ln();
    let km =
        (2.0 * PI).ln() - 1.5 - n.ln() / (6.0 * n) - 0.33084236 / n - 1.0 / (120.0 * n.powi(3))
            + 1.0 / (504.0 * n.powi(5))
            - 0.0011923 / n.powi(7)
            + 0.0005068 / n.powi(9);
    (ks, km)
}

/// Nagaoka sheet inductance with Rosa's round-wire corrections [H].
pub fn rosa_inductance(coil: &Coil, freq: f64) -> f64 {
    let (ks, km) = rosa_corrections(coil, freq);
    sheet_inductance(coil) - MU_0 * coil.mean_radius() * coil.n_turns as f64 * (ks + km)
}

/// Wheeler's long-coil approximation `mu0 pi R^2 N^2 / (l + 0.9 R)` [H].
pub fn wheeler_inductance(coil: &Coil) -> f64 {
    let (r, n) = (coil.mean_radius(), coil.n_turns as f64);
    MU_0 * PI * r * r * (n * n) / (coil.length() + 0.9 * r)
}

/// Wire resistance with the skin effect of an isolated wire (no proximity effect) [ohm].
pub fn ac_resistance(coil: &Coil, freq: f64, rho: f64) -> f64 {
    coil.wire_length() * internal_impedance_per_length(coil.wire_radius(), freq, rho).re
}

/// Medhurst's empirical self-capacitance in free space [F] (an estimate, not a field solution).
pub fn self_capacitance_medhurst(coil: &Coil) -> f64 {
    let d_cm = coil.mean_d() * 100.0;
    let ratio = coil.length() / coil.mean_d();
    d_cm * (0.1126 * ratio + 0.08 + 0.27 / ratio.sqrt()) * 1e-12
}

/// Self-resonance estimate `1 / (2 pi sqrt(L C_medhurst))` [Hz].
pub fn srf_lumped(coil: &Coil, freq: f64) -> f64 {
    1.0 / (2.0 * PI * (self_inductance(coil, freq) * self_capacitance_medhurst(coil)).sqrt())
}
