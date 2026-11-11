//! Coil description and rotations; port of the parts of `coilcal/geometry.py` that the kernels
//! use. The kernels assume valid coils; `app::CoilParams::build` validates the app's input.

use crate::c64;

pub type Vec3 = [f64; 3];
pub type Mat3 = [[f64; 3]; 3];

/// Rotation matrix of a quaternion in scipy's `as_quat()` order (x, y, z, w).
pub fn quat_matrix(q: [f64; 4]) -> Mat3 {
    let n = q.iter().map(|v| v * v).sum::<f64>().sqrt();
    let [x, y, z, w] = q.map(|v| v / n);
    [
        [
            w * w + x * x - y * y - z * z,
            2.0 * (x * y - z * w),
            2.0 * (x * z + y * w),
        ],
        [
            2.0 * (x * y + z * w),
            w * w - x * x + y * y - z * z,
            2.0 * (y * z - x * w),
        ],
        [
            2.0 * (x * z - y * w),
            2.0 * (y * z + x * w),
            w * w - x * x - y * y + z * z,
        ],
    ]
}

/// `R v`.
pub fn apply(r: &Mat3, v: Vec3) -> Vec3 {
    std::array::from_fn(|i| r[i][0] * v[0] + r[i][1] * v[1] + r[i][2] * v[2])
}

/// `R^T v` (inverse rotation).
pub fn apply_t(r: &Mat3, v: Vec3) -> Vec3 {
    std::array::from_fn(|i| r[0][i] * v[0] + r[1][i] * v[1] + r[2][i] * v[2])
}

pub fn dot(a: Vec3, b: Vec3) -> f64 {
    a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}

pub fn sub(a: Vec3, b: Vec3) -> Vec3 {
    [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
}

pub fn norm(a: Vec3) -> f64 {
    dot(a, a).sqrt()
}

/// Dielectric coil former: a tube of radial `wall` under the winding.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Former {
    pub wall: f64,
    /// Complex relative permittivity εr(1 − j tanδ).
    pub eps: c64,
    /// Extension beyond the winding (N·pitch long) at each end [m].
    pub overhang: f64,
}

/// Single-layer cylindrical coil (`SolenoidCoil`), SI units.
#[derive(Clone, Debug, PartialEq)]
pub struct Coil {
    pub wire_d: f64,
    pub pitch: f64,
    pub former_d: f64,
    pub n_turns: usize,
    pub position: Vec3,
    /// Local -> global rotation, scipy `as_quat()` order (x, y, z, w).
    pub quat: [f64; 4],
    /// Outer diameter over the insulation (= `wire_d` for bare wire).
    pub insulation_d: f64,
    /// Complex relative permittivity of the insulation.
    pub insulation_eps: c64,
    pub former: Option<Former>,
}

impl Coil {
    pub fn wire_radius(&self) -> f64 {
        self.wire_d / 2.0
    }
    pub fn outer_radius(&self) -> f64 {
        self.insulation_d / 2.0
    }
    /// Permittivity of the insulation sleeve (1 for bare wire, whatever `insulation_eps` says).
    pub fn sleeve_eps(&self) -> c64 {
        if self.outer_radius() > self.wire_radius() {
            self.insulation_eps
        } else {
            c64::new(1.0, 0.0)
        }
    }
    pub fn mean_radius(&self) -> f64 {
        (self.former_d + self.insulation_d) / 2.0
    }
    pub fn mean_d(&self) -> f64 {
        2.0 * self.mean_radius()
    }
    /// Length of the helical conductor, excluding leads [m].
    pub fn wire_length(&self) -> f64 {
        self.n_turns as f64 * (2.0 * std::f64::consts::PI * self.mean_radius()).hypot(self.pitch)
    }
    pub fn length(&self) -> f64 {
        self.n_turns as f64 * self.pitch
    }
    pub fn rotation(&self) -> Mat3 {
        quat_matrix(self.quat)
    }
    pub fn axis(&self) -> Vec3 {
        apply(&self.rotation(), [0.0, 0.0, 1.0])
    }
    /// Local axial positions of the turns, centred on 0.
    pub fn turn_z(&self) -> Vec<f64> {
        let n = self.n_turns as f64;
        (0..self.n_turns)
            .map(|i| (i as f64 - (n - 1.0) / 2.0) * self.pitch)
            .collect()
    }
    /// Global turn centres.
    pub fn turn_centers(&self) -> Vec<Vec3> {
        let r = self.rotation();
        self.turn_z()
            .into_iter()
            .map(|z| {
                let p = apply(&r, [0.0, 0.0, z]);
                std::array::from_fn(|i| p[i] + self.position[i])
            })
            .collect()
    }
}
