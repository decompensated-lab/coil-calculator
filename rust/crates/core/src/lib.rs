//! Numerical kernels of coilcal, ported from the Python reference.

#[allow(non_camel_case_types)]
pub type c64 = num_complex::Complex<f64>;

pub mod capacitance;
pub mod geometry;
pub mod linalg;
pub mod loops;
pub mod special;
