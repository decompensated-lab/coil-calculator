//! Special functions, in scipy's conventions (`scipy.special`); domain errors give NaN.
//!
//! * Complete elliptic integrals, parameter convention `m = k^2`, from the `ellip` crate
//!   (Boost's algorithms; scipy uses Cephes, so the two agree to a few ε, not bit for bit).
//! * Exponentially scaled Bessel functions of the first kind for complex argument from the
//!   `complex-bessel` crate (a port of Amos, the same library behind `scipy.special.jve`).

use crate::c64;

/// `K(m)`, complete elliptic integral of the first kind (`scipy.special.ellipk`).
pub fn ellipk(m: f64) -> f64 {
    ellip::ellipk(m).unwrap_or(f64::NAN)
}

/// `E(m)`, complete elliptic integral of the second kind (`scipy.special.ellipe`).
pub fn ellipe(m: f64) -> f64 {
    ellip::ellipe(m).unwrap_or(f64::NAN)
}

/// `K(1 - p)`, accurate as `p -> 0` (`scipy.special.ellipkm1`).
///
/// Uses `K(m) = R_F(0, 1 - m, 1)`, which takes `p = 1 - m` directly.
pub fn ellipkm1(p: f64) -> f64 {
    if p == 0.0 {
        return f64::INFINITY; // R_F rejects two zero arguments
    }
    ellip::elliprf(0.0, p, 1.0).unwrap_or(f64::NAN)
}

/// `exp(-|Im z|) J_nu(z)` (`scipy.special.jve`).
pub fn jve(nu: f64, z: c64) -> c64 {
    complex_bessel::besselj_scaled(nu, z).unwrap_or(c64::new(f64::NAN, f64::NAN))
}
