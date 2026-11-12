//! VNA views of coil networks; port of `coilcal/vna.py` (what the app uses).
//!
//! Real reference impedance `z0` on every port, `S = (Z − z0)(Z + z0)^-1`; a source of
//! available power P has incident peak voltage `V+ = sqrt(2 z0 P)` and EMF `2 V+` behind `z0`.
//! The closed-form series/shunt thru S-parameters of the reference (cross-checks) are not ported.

use crate::c64;
use crate::circuit::{Coupling, End, Network, NetworkResult};
use crate::geometry::Coil;
use crate::linalg::solve_lu;

/// Coil in a two-port thru fixture.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ThruMode {
    /// Start terminal on port 1's centre conductor, end on port 2's; nothing grounded.
    Series,
    /// One terminal on the joined centre line of both ports, `ground_end` on the shields.
    Shunt,
}

/// S-parameters `(F, P, P)` from Z-parameters `(F, P, P)`.
pub fn z_to_s(z: &[c64], np: usize, z0: f64) -> Result<Vec<c64>, String> {
    let mut out = Vec::with_capacity(z.len());
    for zf in z.chunks_exact(np * np) {
        // S = (Z − z0 I)(Z + z0 I)^-1 == solve((Z + z0 I)ᵀ, (Z − z0 I)ᵀ)ᵀ
        let shifted = |sign: f64| -> Vec<c64> {
            (0..np * np)
                .map(|ij| {
                    let (i, j) = (ij / np, ij % np);
                    zf[j * np + i] + if i == j { sign * z0 } else { 0.0 }
                })
                .collect()
        };
        let x = solve_lu(&shifted(1.0), &shifted(-1.0), np, np).ok_or("singular Z + z0")?;
        out.extend((0..np * np).map(|ij| x[(ij % np) * np + ij / np]));
    }
    Ok(out)
}

/// Peak incident wave voltage V+ for available source power `p_dbm` [V].
pub fn incident_voltage(p_dbm: f64, z0: f64) -> f64 {
    (2.0 * z0 * 1e-3 * 10f64.powf(p_dbm / 10.0)).sqrt()
}

/// Port currents `(F, P)` with source EMFs `emf` behind `z0` on every port.
pub fn driven_port_currents(
    z: &[c64],
    np: usize,
    emf: &[c64],
    z0: f64,
) -> Result<Vec<c64>, String> {
    let mut out = Vec::with_capacity(z.len() / np);
    for zf in z.chunks_exact(np * np) {
        let a: Vec<c64> = (0..np * np)
            .map(|ij| zf[ij] + if ij / np == ij % np { z0 } else { 0.0 })
            .collect();
        out.extend(solve_lu(&a, emf, np, 1).ok_or("singular Z + z0")?);
    }
    Ok(out)
}

/// Turn currents `(F, T)` and port currents `(F, P)` for VNA-style excitation, superposing the
/// unit-current solutions in `res`.
pub fn driven_turn_currents(
    res: &NetworkResult,
    np: usize,
    emf: &[c64],
    z0: f64,
) -> Result<(Vec<c64>, Vec<c64>), String> {
    let i_port = driven_port_currents(&res.z, np, emf, z0)?;
    let nf = res.freqs.len();
    let nt = res.turn_currents.len() / (nf * np);
    let mut turn = vec![c64::new(0.0, 0.0); nf * nt];
    for f in 0..nf {
        for p in 0..np {
            let ip = i_port[f * np + p];
            for t in 0..nt {
                turn[f * nt + t] += ip * res.turn_currents[(f * np + p) * nt + t];
            }
        }
    }
    Ok((turn, i_port))
}

/// The coil alone (moved to the origin) in a two-port thru fixture.
pub fn thru_network(
    coil: &Coil,
    mode: ThruMode,
    ground_end: End,
    r_factor: f64,
    rho: f64,
) -> Result<Network, String> {
    let coil = Coil {
        position: [0.0; 3],
        ..coil.clone()
    };
    let (ground, ports) = match mode {
        ThruMode::Series => (
            None,
            [(Some((0, End::Start)), None), (Some((0, End::End)), None)],
        ),
        ThruMode::Shunt => {
            let hot = if ground_end == End::End {
                End::Start
            } else {
                End::End
            };
            (
                Some(ground_end),
                [(Some((0, hot)), None), (Some((0, hot)), None)],
            )
        }
    };
    Network::new(
        &[coil],
        &[ground],
        Coupling::Full,
        r_factor,
        rho,
        None,
        Some(&ports),
    )
}
