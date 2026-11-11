//! Quasi-static B field of the ring model.
//!
//! Replaces magpylib for what the app uses: `magpylib.current.Circle` (one loop per turn, as
//! in `CoilNetwork.unit_fields`), ported formula for formula from magpylib 6.0.1 (BSD-3):
//! Ortner et al., "Numerically stable and computationally efficient expression for the magnetic
//! field of a current loop", Magnetism 3 (2023) 11-31, which uses Bulirsch's `cel` with its
//! first iteration done analytically. Plus the on-axis closed forms of `coilcal/field.py`. The
//! helix (polyline) model is a cross-check of the Python reference and is not ported.

use crate::geometry::{Coil, Vec3, apply, apply_t, sub};
use crate::loops::MU_0;
use std::f64::consts::PI;

/// Bulirsch `cel` iteration continued from a prepared state (magpylib `_cel_iter`).
fn cel_iter(
    mut qc: f64,
    mut p: f64,
    mut g: f64,
    mut cc: f64,
    mut ss: f64,
    mut em: f64,
    mut kk: f64,
) -> f64 {
    while (g - qc).abs() > g * 1e-8 {
        qc = 2.0 * kk.sqrt();
        kk = em * qc;
        g = kk / p;
        (cc, ss) = (cc + ss / p, 2.0 * (ss + cc * g));
        p += g;
        g = em;
        em += qc;
    }
    (PI / 2.0) * (ss + cc * em) / (em * (em + p))
}

/// `(H_r, H_z)` [A/m] of a 1 A loop of radius `r0` in z = 0 at cylindrical (r, z).
fn circle_h(r0: f64, r: f64, z: f64) -> (f64, f64) {
    // express through ratios
    let (r, z) = (r / r0, z / r0);
    let z2 = z * z;
    let x0 = z2 + (r + 1.0).powi(2);
    let k2 = 4.0 * r / x0;
    let q2 = (z2 + (r - 1.0).powi(2)) / x0;
    let q = q2.sqrt();
    let p = 1.0 + q;
    let pf = 1.0 / (4.0 * PI * r0 * x0.sqrt() * q2);
    // cel* part
    let cc = k2 * 4.0 * z / x0;
    let ss = 2.0 * cc * q / p;
    let hr = pf * cel_iter(q, p, 1.0, cc, ss, p, q);
    // cel** part
    let k4 = k2 * k2;
    let cc = k4 - (q2 + 1.0) * (4.0 / x0);
    let ss = 2.0 * q * (k4 / p - (4.0 / x0) * p);
    let hz = -pf * cel_iter(q, p, 1.0, cc, ss, p, q);
    (hr, hz)
}

/// B [T] at global `point` of a 1 A loop (radius `r0`, centre, local -> global rotation).
pub fn circle_b(r0: f64, center: Vec3, rot: &crate::geometry::Mat3, point: Vec3) -> Vec3 {
    let p = apply_t(rot, sub(point, center));
    let (r, phi, z) = ((p[0] * p[0] + p[1] * p[1]).sqrt(), p[1].atan2(p[0]), p[2]);
    if (r - r0).abs() < 1e-15 * r0 && z == 0.0 {
        return [0.0; 3]; // on the wire: magpylib returns 0
    }
    let (hr, hz) = circle_h(r0, r, z);
    let h = [hr * phi.cos(), hr * phi.sin(), hz];
    let b = apply(rot, h);
    b.map(|v| v * MU_0)
}

/// B [T] at `points` per ampere in each turn of each coil, row-major `(T, P, 3)`.
pub fn unit_fields(coils: &[Coil], points: &[Vec3]) -> Vec<f64> {
    let mut out = Vec::new();
    for c in coils {
        let rot = c.rotation();
        for center in c.turn_centers() {
            for &pt in points {
                out.extend(circle_b(c.mean_radius(), center, &rot, pt));
            }
        }
    }
    out
}

/// Exact on-axis B_z of the ring model at local axial coordinate `z` [T] per ampere.
pub fn b_axis_rings(coil: &Coil, z: f64) -> f64 {
    let r = coil.mean_radius();
    coil.turn_z()
        .iter()
        .map(|tz| {
            let dz = z - tz;
            MU_0 * r * r / (2.0 * (r * r + dz * dz).powf(1.5))
        })
        .sum()
}

/// On-axis B_z of the equivalent uniform current sheet (length N·pitch) [T] per ampere.
pub fn b_axis_sheet(coil: &Coil, z: f64) -> f64 {
    let (r, h) = (coil.mean_radius(), coil.length() / 2.0);
    let n = coil.n_turns as f64 / coil.length();
    MU_0 * n / 2.0 * ((z + h) / r.hypot(z + h) - (z - h) / r.hypot(z - h))
}
