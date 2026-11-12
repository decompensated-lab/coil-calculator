//! Mutual inductance between coils from the ring model; port of `coilcal/mutual.py`
//! (`mutual_matrix`, `mutual_inductance` with `method="rings"`). The magpylib flux method is an
//! independent cross-check of the Python reference and is not ported.

use crate::geometry::{Coil, dot, norm, sub};
use crate::loops::{mutual_coaxial, mutual_rings};

/// +1/-1 if the coils share an axis (parallel/antiparallel), else 0.
pub fn coaxial_sign(a: &Coil, b: &Coil) -> i32 {
    const ATOL: f64 = 1e-12;
    let (ax_a, ax_b) = (a.axis(), b.axis());
    let cross = [
        ax_a[1] * ax_b[2] - ax_a[2] * ax_b[1],
        ax_a[2] * ax_b[0] - ax_a[0] * ax_b[2],
        ax_a[0] * ax_b[1] - ax_a[1] * ax_b[0],
    ];
    if norm(cross) > ATOL {
        return 0;
    }
    let d = sub(b.position, a.position);
    let scale = a.mean_radius().max(b.mean_radius());
    let along = dot(d, ax_a);
    if norm(std::array::from_fn(|i| d[i] - along * ax_a[i])) > ATOL * scale.max(1.0) {
        return 0;
    }
    if dot(ax_a, ax_b) > 0.0 { 1 } else { -1 }
}

/// Turn-by-turn mutual inductances, row-major `(N_a, N_b)` [H].
///
/// Coaxial coils use Maxwell's closed form; otherwise the vector-potential line integral with
/// `n_phi` points per ring, or (`None`) doubled from 64 until the matrix changes by less than
/// `rtol · Σ|M_ij|` (an error if `max_n_phi` is reached).
pub fn mutual_matrix(
    a: &Coil,
    b: &Coil,
    n_phi: Option<usize>,
    rtol: f64,
    max_n_phi: usize,
) -> Result<Vec<f64>, String> {
    let sign = coaxial_sign(a, b);
    let (ca, cb) = (a.turn_centers(), b.turn_centers());
    if sign != 0 {
        let ax = a.axis();
        let za: Vec<f64> = ca.iter().map(|c| dot(sub(*c, a.position), ax)).collect();
        let zb: Vec<f64> = cb.iter().map(|c| dot(sub(*c, a.position), ax)).collect();
        let (ra, rb) = (a.mean_radius(), b.mean_radius());
        return Ok(za
            .iter()
            .flat_map(|zi| {
                zb.iter()
                    .map(move |zj| sign as f64 * mutual_coaxial(ra, rb, zj - zi))
            })
            .collect());
    }
    let run = |n: usize| {
        mutual_rings(
            a.mean_radius(),
            a.quat,
            &ca,
            b.mean_radius(),
            b.quat,
            &cb,
            n,
        )
    };
    if let Some(n) = n_phi {
        return Ok(run(n));
    }
    let mut n = 64;
    let mut prev = run(n);
    while n < max_n_phi {
        n *= 2;
        let cur = run(n);
        // scale by Σ|M_ij| so that configurations with M ~ 0 (by symmetry) still converge
        let change: f64 = cur.iter().zip(&prev).map(|(c, p)| (c - p).abs()).sum();
        if change <= rtol * cur.iter().map(|c| c.abs()).sum::<f64>() {
            return Ok(cur);
        }
        prev = cur;
    }
    Err(format!(
        "mutual inductance did not converge with n_phi={max_n_phi} (do the windings touch?)"
    ))
}

/// Mutual inductance between coils `a` and `b` [H] (ring model, `mutual_matrix` defaults).
pub fn mutual_inductance(a: &Coil, b: &Coil) -> Result<f64, String> {
    Ok(mutual_matrix(a, b, None, 1e-9, 1 << 14)?.iter().sum())
}
