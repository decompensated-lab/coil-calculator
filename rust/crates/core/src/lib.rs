//! Numerical kernels of coilcal, ported from the Python reference.

#[allow(non_camel_case_types)]
pub type c64 = num_complex::Complex<f64>;

pub mod capacitance;
pub mod circuit;
pub mod field;
pub mod geometry;
pub mod inductance;
pub mod linalg;
pub mod loops;
pub mod mutual;
pub mod special;
pub mod vna;
pub mod wirepair;
