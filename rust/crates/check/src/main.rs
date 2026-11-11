//! Check binary: answers kernel requests from pytest over stdin/stdout (see `wire`).

mod wire;

use coilcal_core::capacitance::{self as cap, Matrix};
use coilcal_core::circuit::{self, Coupling, End, Network, NetworkResult, Terminal};
use coilcal_core::geometry::{Coil, Former};
use coilcal_core::vna;
use coilcal_core::wirepair::{self as wp, InsulatedWire};
use coilcal_core::{c64, field, inductance as ind, linalg, loops, mutual, special};
use std::io::{self, BufReader, BufWriter};
use std::time::Instant;
use wire::Array;

/// Complex view of an array (real arrays are promoted).
fn to_c64(a: &Array) -> Vec<c64> {
    if a.complex {
        a.data
            .as_chunks::<2>()
            .0
            .iter()
            .map(|&[re, im]| c64::new(re, im))
            .collect()
    } else {
        a.data.iter().map(|&r| c64::new(r, 0.0)).collect()
    }
}

fn from_c64(shape: Vec<usize>, v: &[c64]) -> Array {
    Array::complex(shape, v.iter().flat_map(|z| [z.re, z.im]).collect())
}

/// `solve(A, B) -> [X, seconds]`; `B` may be a vector. Real unless either input is complex.
fn solve(args: &[Array]) -> Result<Vec<Array>, String> {
    let [a, b] = args else {
        return Err("expected A, B".into());
    };
    let n = a.shape[0];
    if a.shape != [n, n] || b.shape.first() != Some(&n) || b.shape.len() > 2 {
        return Err(format!("bad shapes {:?}, {:?}", a.shape, b.shape));
    }
    let k = b.shape.get(1).copied().unwrap_or(1);
    let t0 = Instant::now();
    let x = if a.complex || b.complex {
        let x = linalg::solve_lu(&to_c64(a), &to_c64(b), n, k).ok_or("singular matrix")?;
        from_c64(b.shape.clone(), &x)
    } else {
        let x = linalg::solve_lu(&a.data, &b.data, n, k).ok_or("singular matrix")?;
        Array::real(b.shape.clone(), x)
    };
    Ok(vec![x, Array::scalar(t0.elapsed().as_secs_f64())])
}

/// Element type of an elementwise result.
trait Elem {
    const COMPLEX: bool;
    fn push_to(self, out: &mut Vec<f64>);
}
impl Elem for f64 {
    const COMPLEX: bool = false;
    fn push_to(self, out: &mut Vec<f64>) {
        out.push(self);
    }
}
impl Elem for c64 {
    const COMPLEX: bool = true;
    fn push_to(self, out: &mut Vec<f64>) {
        out.extend([self.re, self.im]);
    }
}

/// Applies `f` elementwise to `N` real arrays of one shape (pytest broadcasts beforehand).
fn map_real<const N: usize, T: Elem>(
    args: &[Array],
    f: impl Fn([f64; N]) -> T,
) -> Result<Vec<Array>, String> {
    let Ok(xs) = <&[Array; N]>::try_from(args) else {
        return Err(format!("expected {N} arrays, got {}", args.len()));
    };
    if xs.iter().any(|x| x.complex || x.shape != xs[0].shape) {
        return Err("expected real arrays of one shape".into());
    }
    let mut out = Vec::new();
    for i in 0..xs[0].data.len() {
        f(core::array::from_fn(|j| xs[j].data[i])).push_to(&mut out);
    }
    let shape = xs[0].shape.clone();
    Ok(vec![if T::COMPLEX {
        Array::complex(shape, out)
    } else {
        Array::real(shape, out)
    }])
}

/// `jve(nu, z)` for a scalar order and an array of (complex) arguments.
fn jve(args: &[Array]) -> Result<Vec<Array>, String> {
    let [nu, z] = args else {
        return Err("expected nu, z".into());
    };
    if nu.complex || nu.data.len() != 1 {
        return Err("nu must be a real scalar".into());
    }
    let out: Vec<c64> = to_c64(z)
        .into_iter()
        .map(|z| special::jve(nu.data[0], z))
        .collect();
    Ok(vec![from_c64(z.shape.clone(), &out)])
}

/// `[(n, 3)] -> [[x, y, z]; n]` for ring centres.
fn points(a: &Array) -> Result<Vec<[f64; 3]>, String> {
    match a.shape[..] {
        [_, 3] if !a.complex => Ok(a.data.as_chunks::<3>().0.to_vec()),
        _ => Err(format!("expected real (n, 3) points, got {:?}", a.shape)),
    }
}

fn scalar(a: &Array) -> Result<f64, String> {
    match a.data[..] {
        [x] if !a.complex => Ok(x),
        _ => Err("expected a real scalar".into()),
    }
}

/// `mutual_rings(ra, quat_a, centers_a, rb, quat_b, centers_b, n_phi)`.
fn mutual_rings(args: &[Array]) -> Result<Vec<Array>, String> {
    let [ra, qa, ca, rb, qb, cb, n_phi] = args else {
        return Err("expected 7 arrays".into());
    };
    let quat = |q: &Array| <[f64; 4]>::try_from(&q.data[..]).map_err(|_| "quaternion needs 4");
    let (ca, cb) = (points(ca)?, points(cb)?);
    let m = loops::mutual_rings(
        scalar(ra)?,
        quat(qa)?,
        &ca,
        scalar(rb)?,
        quat(qb)?,
        &cb,
        scalar(n_phi)? as usize,
    );
    Ok(vec![Array::real(vec![ca.len(), cb.len()], m)])
}

/// Coils as rows of `[wire_d, pitch, former_d, n_turns, px, py, pz, qx, qy, qz, qw,
/// insulation_d, ins_eps_re, ins_eps_im, has_former, wall, f_eps_re, f_eps_im, overhang]`.
fn coils(a: &Array) -> Result<Vec<Coil>, String> {
    let [_, 19] = a.shape[..] else {
        return Err(format!("coils: bad shape {:?}", a.shape));
    };
    let rows = a.data.as_chunks::<19>().0;
    Ok(rows
        .iter()
        .map(|r| Coil {
            wire_d: r[0],
            pitch: r[1],
            former_d: r[2],
            n_turns: r[3] as usize,
            position: [r[4], r[5], r[6]],
            quat: [r[7], r[8], r[9], r[10]],
            insulation_d: r[11],
            insulation_eps: c64::new(r[12], r[13]),
            former: (r[14] != 0.0).then(|| Former {
                wall: r[15],
                eps: c64::new(r[16], r[17]),
                overhang: r[18],
            }),
        })
        .collect())
}

/// `(coils, n_sub, alpha, n_phi, h_wire)`; `n_sub = 0` means automatic.
fn cap_args(args: &[Array]) -> Result<(Vec<Coil>, cap::Options), String> {
    let [c, n_sub, alpha, n_phi, h_wire] = args else {
        return Err("expected 5 arrays".into());
    };
    let n_sub = scalar(n_sub)? as usize;
    let opt = cap::Options {
        n_sub: (n_sub > 0).then_some(n_sub),
        alpha: scalar(alpha)?,
        n_phi: scalar(n_phi)? as usize,
        h_wire: scalar(h_wire)?,
    };
    Ok((coils(c)?, opt))
}

/// `capacitance_system(...) -> [A, rhs, seconds]`, real unless lossy.
fn capacitance_system(args: &[Array]) -> Result<Vec<Array>, String> {
    let (coils, opt) = cap_args(args)?;
    let t0 = Instant::now();
    let s = cap::system(&coils, &opt)?;
    let secs = Array::scalar(t0.elapsed().as_secs_f64());
    let out = |v: &[c64], shape: Vec<usize>| {
        if s.lossy {
            from_c64(shape, v)
        } else {
            Array::real(shape, v.iter().map(|z| z.re).collect())
        }
    };
    Ok(vec![
        out(&s.a, vec![s.n, s.n]),
        out(&s.rhs, vec![s.n, s.n_turns]),
        secs,
    ])
}

/// `capacitance_matrix(...) -> [C, seconds]`.
fn capacitance_matrix(args: &[Array]) -> Result<Vec<Array>, String> {
    let (coils, opt) = cap_args(args)?;
    let t0 = Instant::now();
    let c = cap::capacitance_matrix(&coils, &opt)?;
    let secs = Array::scalar(t0.elapsed().as_secs_f64());
    let n: usize = coils.iter().map(|c| c.n_turns).sum();
    Ok(vec![
        match c {
            Matrix::Real(v) => Array::real(vec![n, n], v),
            Matrix::Complex(v) => from_c64(vec![n, n], &v),
        },
        secs,
    ])
}

/// `coil_quantities(coils, freqs)`: per coil (rows) and frequency (columns, 0 = DC)
/// `[L, L_rosa, R_ac, srf_lumped, k_s, k_m]`, then per coil `[L_sheet, L_wheeler, C_medhurst]`.
fn coil_quantities(args: &[Array]) -> Result<Vec<Array>, String> {
    let [c, f] = args else {
        return Err("expected coils, freqs".into());
    };
    let (cs, fs) = (coils(c)?, &f.data);
    let grid = |g: &dyn Fn(&Coil, f64) -> f64| {
        let v = cs
            .iter()
            .flat_map(|c| fs.iter().map(move |&f| g(c, f)))
            .collect();
        Array::real(vec![cs.len(), fs.len()], v)
    };
    let per = |g: &dyn Fn(&Coil) -> f64| Array::real(vec![cs.len()], cs.iter().map(g).collect());
    Ok(vec![
        grid(&ind::self_inductance),
        grid(&ind::rosa_inductance),
        grid(&|c, f| ind::ac_resistance(c, f, loops::RHO_CU)),
        grid(&ind::srf_lumped),
        grid(&|c, f| ind::rosa_corrections(c, f).0),
        grid(&|c, f| ind::rosa_corrections(c, f).1),
        per(&ind::sheet_inductance),
        per(&ind::wheeler_inductance),
        per(&ind::self_capacitance_medhurst),
    ])
}

/// `mutual_matrix(coils[a, b], n_phi (0 = auto), rtol, max_n_phi)`.
fn mutual_matrix(args: &[Array]) -> Result<Vec<Array>, String> {
    let [c, n_phi, rtol, max_n] = args else {
        return Err("expected 4 arrays".into());
    };
    let [a, b] = &coils(c)?[..] else {
        return Err("expected two coils".into());
    };
    let n_phi = scalar(n_phi)? as usize;
    let m = mutual::mutual_matrix(
        a,
        b,
        (n_phi > 0).then_some(n_phi),
        scalar(rtol)?,
        scalar(max_n)? as usize,
    )?;
    Ok(vec![Array::real(vec![a.n_turns, b.n_turns], m)])
}

/// `unit_fields(coils, points (P, 3)) -> (T, P, 3)`.
fn unit_fields(args: &[Array]) -> Result<Vec<Array>, String> {
    let [c, pts] = args else {
        return Err("expected coils, points".into());
    };
    let (cs, pts) = (coils(c)?, points(pts)?);
    let t: usize = cs.iter().map(|c| c.n_turns).sum();
    Ok(vec![Array::real(
        vec![t, pts.len(), 3],
        field::unit_fields(&cs, &pts),
    )])
}

/// `b_axis(coil, z) -> [B_z rings, B_z sheet]` per ampere.
fn b_axis(args: &[Array]) -> Result<Vec<Array>, String> {
    let [c, z] = args else {
        return Err("expected coil, z".into());
    };
    let [coil] = &coils(c)?[..] else {
        return Err("expected one coil".into());
    };
    let map = |g: fn(&Coil, f64) -> f64| {
        Array::real(
            z.shape.clone(),
            z.data.iter().map(|&z| g(coil, z)).collect(),
        )
    };
    Ok(vec![map(field::b_axis_rings), map(field::b_axis_sheet)])
}

/// `pair_capacitance(wires (2, 4) [a, b, eps_re, eps_im], spacing, rtol, max_terms,
/// points (P, 2)) -> [C, n_terms, converged, V (2,), potential (P,), tan_delta, G'(1 MHz)]`.
fn pair_capacitance(args: &[Array]) -> Result<Vec<Array>, String> {
    let [w, s, rtol, max_terms, pts] = args else {
        return Err("expected 5 arrays".into());
    };
    let ([_, 4], [_, 2]) = (&w.shape[..], &pts.shape[..]) else {
        return Err("bad shapes".into());
    };
    let wire = |r: &[f64]| InsulatedWire {
        a: r[0],
        b: r[1],
        eps: c64::new(r[2], r[3]),
    };
    let res = wp::pair_capacitance(
        wire(&w.data[..4]),
        wire(&w.data[4..8]),
        scalar(s)?,
        scalar(rtol)?,
        scalar(max_terms)? as usize,
    )?;
    let phi: Vec<c64> = pts
        .data
        .as_chunks::<2>()
        .0
        .iter()
        .map(|&[x, y]| res.potential(x, y))
        .collect();
    Ok(vec![
        from_c64(vec![], &[res.c]),
        Array::scalar(res.n_terms as f64),
        Array::scalar(res.converged as u8 as f64),
        from_c64(vec![2], &res.v),
        from_c64(vec![phi.len()], &phi),
        Array::scalar(res.tan_delta()),
        Array::scalar(res.conductance(1e6)),
    ])
}

/// `(coils, ground codes (C,) [0 floating, 1 start, 2 end], coupling [0 full, 1 magnetic,
/// 2 electric], r_factor, ports (P, 4) [plus coil (-1 = ref), plus end (0 start, 1 end),
/// minus coil, minus end]; (0, 4) = one port per coil)`.
fn network(args: &[Array]) -> Result<Network, String> {
    let [c, g, cp, rf, ports] = args else {
        return Err("expected 5 network arrays".into());
    };
    let end = |x: f64| if x == 0.0 { End::Start } else { End::End };
    let ground: Vec<Option<End>> = g
        .data
        .iter()
        .map(|&x| (x != 0.0).then(|| end(x - 1.0)))
        .collect();
    let coupling = match scalar(cp)? as u8 {
        0 => Coupling::Full,
        1 => Coupling::Magnetic,
        _ => Coupling::Electric,
    };
    let term = |coil: f64, e: f64| -> Terminal { (coil >= 0.0).then(|| (coil as usize, end(e))) };
    let ports: Vec<(Terminal, Terminal)> = ports
        .data
        .as_chunks::<4>()
        .0
        .iter()
        .map(|r| (term(r[0], r[1]), term(r[2], r[3])))
        .collect();
    let ports = (!ports.is_empty()).then_some(&ports[..]);
    Network::new(
        &coils(c)?,
        &ground,
        coupling,
        scalar(rf)?,
        loops::RHO_CU,
        None,
        ports,
    )
}

fn result_arrays(r: &NetworkResult, np: usize) -> Vec<Array> {
    let nf = r.freqs.len();
    let nt = r.turn_currents.len() / (nf * np).max(1);
    let nn = r.node_voltages.len() / (nf * np).max(1);
    vec![
        from_c64(vec![nf, np, np], &r.z),
        from_c64(vec![nf, np, nt], &r.turn_currents),
        from_c64(vec![nf, np, nn], &r.node_voltages),
    ]
}

/// `network_solve(<network>, freqs) -> [z, turn_currents, node_voltages, c_node]`.
fn network_solve(args: &[Array]) -> Result<Vec<Array>, String> {
    let net = network(&args[..5])?;
    let r = net.solve(&args[5].data)?;
    let mut out = result_arrays(&r, net.ports.len());
    let nn = (net.c_node.len() as f64).sqrt() as usize;
    out.push(from_c64(vec![nn, nn], &net.c_node));
    Ok(out)
}

/// `network_srf(<network>, port, f_lo, f_hi, n_scan)`.
fn network_srf(args: &[Array]) -> Result<Vec<Array>, String> {
    let net = network(&args[..5])?;
    let [p, lo, hi, n] = &args[5..] else {
        return Err("expected port, f_lo, f_hi, n_scan".into());
    };
    let f = net.srf(
        scalar(p)? as usize,
        scalar(lo)?,
        scalar(hi)?,
        scalar(n)? as usize,
    )?;
    Ok(vec![Array::scalar(f)])
}

/// `network_resonance(<network>, port, f_lo, f_hi) -> [f, q, r_parallel]`.
fn network_resonance(args: &[Array]) -> Result<Vec<Array>, String> {
    let net = network(&args[..5])?;
    let [p, lo, hi] = &args[5..] else {
        return Err("expected port, f_lo, f_hi".into());
    };
    let r = net.resonance(scalar(p)? as usize, scalar(lo)?, scalar(hi)?)?;
    Ok([r.freq, r.q, r.r_parallel].map(Array::scalar).into())
}

/// `thru_solve(coil, mode [0 series, 1 shunt], ground_end [0 start, 1 end], r_factor, freqs)`.
fn thru_solve(args: &[Array]) -> Result<Vec<Array>, String> {
    let [c, mode, gnd, rf, freqs] = args else {
        return Err("expected 5 arrays".into());
    };
    let [coil] = &coils(c)?[..] else {
        return Err("expected one coil".into());
    };
    let mode = if scalar(mode)? == 0.0 {
        vna::ThruMode::Series
    } else {
        vna::ThruMode::Shunt
    };
    let gnd = if scalar(gnd)? == 0.0 {
        End::Start
    } else {
        End::End
    };
    let net = vna::thru_network(coil, mode, gnd, scalar(rf)?, loops::RHO_CU)?;
    Ok(result_arrays(&net.solve(&freqs.data)?, 2))
}

/// `driven_turn_currents(z (F, P, P), turn_currents (F, P, T), emf (P,), z0)`.
fn driven_turn_currents(args: &[Array]) -> Result<Vec<Array>, String> {
    let [z, tc, emf, z0] = args else {
        return Err("expected 4 arrays".into());
    };
    let [nf, np, _] = z.shape[..] else {
        return Err("z must be (F, P, P)".into());
    };
    let res = NetworkResult {
        freqs: vec![0.0; nf],
        z: to_c64(z),
        turn_currents: to_c64(tc),
        node_voltages: vec![],
    };
    let (turn, port) = vna::driven_turn_currents(&res, np, &to_c64(emf), scalar(z0)?)?;
    Ok(vec![
        from_c64(vec![nf, tc.shape[2]], &turn),
        from_c64(vec![nf, np], &port),
    ])
}

fn dispatch(name: &str, args: Vec<Array>) -> Result<Vec<Array>, String> {
    match name {
        "echo" => Ok(args),
        "solve" => solve(&args),
        "ellipk" => map_real(&args, |[m]| special::ellipk(m)),
        "ellipe" => map_real(&args, |[m]| special::ellipe(m)),
        "ellipkm1" => map_real(&args, |[p]| special::ellipkm1(p)),
        "jve" => jve(&args),
        "coil_quantities" => coil_quantities(&args),
        "nagaoka" => map_real(&args, |[d, l]| ind::nagaoka(d, l)),
        "mutual_matrix" => mutual_matrix(&args),
        "unit_fields" => unit_fields(&args),
        "b_axis" => b_axis(&args),
        "pair_capacitance" => pair_capacitance(&args),
        "bare_pair_capacitance" => {
            let [a1, a2, s] = &args[..] else {
                return Err("expected a1, a2, s".into());
            };
            Ok(vec![Array::scalar(wp::bare_pair_capacitance(
                scalar(a1)?,
                scalar(a2)?,
                scalar(s)?,
            )?)])
        }
        "effective_radius" => map_real(&args, |[a, b, e]| wp::effective_radius(a, b, e)),
        "network_solve" => network_solve(&args),
        "network_srf" => network_srf(&args),
        "network_resonance" => network_resonance(&args),
        "thru_solve" => thru_solve(&args),
        "driven_turn_currents" => driven_turn_currents(&args),
        "z_to_s" => {
            let [z, z0] = &args[..] else {
                return Err("expected z, z0".into());
            };
            let np = z.shape.last().copied().unwrap_or(0);
            Ok(vec![from_c64(
                z.shape.clone(),
                &vna::z_to_s(&to_c64(z), np, scalar(z0)?)?,
            )])
        }
        "incident_voltage" => map_real(&args, |[p, z0]| vna::incident_voltage(p, z0)),
        "geomspace" => {
            let [a, b, n] = &args[..] else {
                return Err("expected start, stop, num".into());
            };
            let v = circuit::geomspace(scalar(a)?, scalar(b)?, scalar(n)? as usize);
            Ok(vec![Array::real(vec![v.len()], v)])
        }
        "capacitance_system" => capacitance_system(&args),
        "capacitance_matrix" => capacitance_matrix(&args),
        "auto_n_sub" => {
            let c = coils(args.first().ok_or("expected coils")?)?;
            Ok(vec![Array::scalar(cap::auto_n_sub(&c) as f64)])
        }
        "ring_potential" => map_real(&args, |[b, rho, z]| cap::ring_potential(b, rho, z)),
        "ring_field_rho" => map_real(&args, |[b, rho, z]| cap::ring_all(b, rho, z).1),
        "ring_field_z" => map_real(&args, |[b, rho, z]| cap::ring_all(b, rho, z).2),
        "gauss_legendre" => Ok([&cap::GL8_X[..], &cap::GL8_W, &cap::GL2_X, &cap::GL2_W]
            .map(|v| Array::real(vec![v.len()], v.to_vec()))
            .into()),
        "constants" => Ok(vec![
            Array::scalar(loops::MU_0),
            Array::scalar(loops::RHO_CU),
            Array::scalar(cap::EPS0),
        ]),
        "mutual_coaxial" => map_real(&args, |[r1, r2, dz]| loops::mutual_coaxial(r1, r2, dz)),
        "a_phi_over_rho" => map_real(&args, |[a, rho, z]| loops::a_phi_over_rho(a, rho, z)),
        "mutual_rings" => mutual_rings(&args),
        "skin_depth" => map_real(&args, |[f, rho]| loops::skin_depth(f, rho)),
        "internal_impedance_per_length" => map_real(&args, |[a, f, rho]| {
            loops::internal_impedance_per_length(a, f, rho)
        }),
        "internal_inductance_per_length" => map_real(&args, |[a, f, rho]| {
            loops::internal_inductance_per_length(a, f, rho)
        }),
        "loop_self_inductance" => map_real(&args, |[r, a, f]| loops::loop_self_inductance(r, a, f)),
        _ => Err(format!("unknown function {name:?}")),
    }
}

fn main() -> io::Result<()> {
    let mut input = BufReader::new(io::stdin().lock());
    let mut output = BufWriter::new(io::stdout().lock());
    while let Some((name, args)) = wire::read_request(&mut input)? {
        wire::write_response(&mut output, &dispatch(&name, args))?;
    }
    Ok(())
}
