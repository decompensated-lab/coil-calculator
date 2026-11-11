//! Special functions, in scipy's conventions (`scipy.special`); domain errors give NaN.
//!
//! * Complete elliptic integrals (parameter `m = k^2`): Cephes `ellpk`/`ellpe` by S. L. Moshier,
//!   ported from SciPy's `xsf` (BSD-3), i.e. the same algorithm and coefficients as scipy:
//!   `P(p) − ln(p) Q(p)` in `p = 1 − m`, no iteration (this sits in the innermost loop of the
//!   capacitance assembly).
//! * Exponentially scaled Bessel functions of the first kind for complex argument from the
//!   `complex-bessel` crate (a port of Amos, the same library behind `scipy.special.jve`).

use crate::c64;

const ELLPK_P: [f64; 11] = [
    1.37982864606273237150E-4,
    2.28025724005875567385E-3,
    7.97404013220415179367E-3,
    9.85821379021226008714E-3,
    6.87489687449949877925E-3,
    6.18901033637687613229E-3,
    8.79078273952743772254E-3,
    1.49380448916805252718E-2,
    3.08851465246711995998E-2,
    9.65735902811690126535E-2,
    1.38629436111989062502E0,
];
const ELLPK_Q: [f64; 11] = [
    2.94078955048598507511E-5,
    9.14184723865917226571E-4,
    5.94058303753167793257E-3,
    1.54850516649762399335E-2,
    2.39089602715924892727E-2,
    3.01204715227604046988E-2,
    3.73774314173823228969E-2,
    4.88280347570998239232E-2,
    7.03124996963957469739E-2,
    1.24999999999870820058E-1,
    4.99999999999999999821E-1,
];
const ELLPK_C1: f64 = 1.3862943611198906188E0; // ln 4
const ELLPE_P: [f64; 11] = [
    1.53552577301013293365E-4,
    2.50888492163602060990E-3,
    8.68786816565889628429E-3,
    1.07350949056076193403E-2,
    7.77395492516787092951E-3,
    7.58395289413514708519E-3,
    1.15688436810574127319E-2,
    2.18317996015557253103E-2,
    5.68051945617860553470E-2,
    4.43147180560990850618E-1,
    1.00000000000000000299E0,
];
const ELLPE_Q: [f64; 10] = [
    3.27954898576485872656E-5,
    1.00962792679356715133E-3,
    6.50609489976927491433E-3,
    1.68862163993311317300E-2,
    2.61769742454493659583E-2,
    3.34833904888224918614E-2,
    4.27180926518931511717E-2,
    5.85936634471101055642E-2,
    9.37499997197644278445E-2,
    2.49999999999888314361E-1,
];
const MACHEP: f64 = 1.1102230246251565404236316680908203125E-16; // 2^-53

/// Horner evaluation, highest coefficient first (Cephes `polevl`).
fn polevl(x: f64, coef: &[f64]) -> f64 {
    coef[1..].iter().fold(coef[0], |acc, &c| acc * x + c)
}

/// `K(1 - p)`, accurate as `p -> 0` (`scipy.special.ellipkm1`, Cephes `ellpk`).
pub fn ellipkm1(p: f64) -> f64 {
    if p < 0.0 {
        return f64::NAN;
    }
    if p > 1.0 {
        if p.is_infinite() {
            return 0.0;
        }
        return ellipkm1(1.0 / p) / p.sqrt();
    }
    if p > MACHEP {
        polevl(p, &ELLPK_P) - p.ln() * polevl(p, &ELLPK_Q)
    } else if p == 0.0 {
        f64::INFINITY
    } else {
        ELLPK_C1 - 0.5 * p.ln() // also NaN in, NaN out
    }
}

/// `K(m)`, complete elliptic integral of the first kind (`scipy.special.ellipk`).
pub fn ellipk(m: f64) -> f64 {
    ellipkm1(1.0 - m)
}

/// `E(m)`, complete elliptic integral of the second kind (`scipy.special.ellipe`, Cephes `ellpe`).
pub fn ellipe(m: f64) -> f64 {
    let x = 1.0 - m;
    if x <= 0.0 {
        return if x == 0.0 { 1.0 } else { f64::NAN };
    }
    if x > 1.0 {
        return ellipe(1.0 - 1.0 / x) * x.sqrt();
    }
    polevl(x, &ELLPE_P) - x.ln() * (x * polevl(x, &ELLPE_Q))
}

/// `exp(-|Im z|) J_nu(z)` (`scipy.special.jve`).
pub fn jve(nu: f64, z: c64) -> c64 {
    complex_bessel::besselj_scaled(nu, z).unwrap_or(c64::new(f64::NAN, f64::NAN))
}
