//! Check binary: answers kernel requests from pytest over stdin/stdout (see `wire`).

mod wire;

use coilcal_core::capacitance::{self as cap, Matrix};
use coilcal_core::geometry::{Coil, Former};
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
