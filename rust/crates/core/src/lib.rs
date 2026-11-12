//! Numerical kernels of coilcal, ported from the Python reference, and the app layer on top
//! (`app` for the coil model, `pair` for the wire-pair calculator; both behind `app::call`).

#[allow(non_camel_case_types)]
pub type c64 = num_complex::Complex<f64>;

pub mod app;
pub mod capacitance;
pub mod circuit;
pub mod field;
pub mod geometry;
pub mod inductance;
pub mod linalg;
pub mod loops;
pub mod mutual;
pub mod pair;
pub mod special;
pub mod vna;
pub mod wirepair;
