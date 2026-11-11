//! Check binary: answers kernel requests from pytest over stdin/stdout (see `wire`).

mod wire;

use coilcal_core::{c64, linalg, loops, special};
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

fn dispatch(name: &str, args: Vec<Array>) -> Result<Vec<Array>, String> {
    match name {
        "echo" => Ok(args),
        "solve" => solve(&args),
        "ellipk" => map_real(&args, |[m]| special::ellipk(m)),
        "ellipe" => map_real(&args, |[m]| special::ellipe(m)),
        "ellipkm1" => map_real(&args, |[p]| special::ellipkm1(p)),
        "jve" => jve(&args),
        "constants" => Ok(vec![
            Array::scalar(loops::MU_0),
            Array::scalar(loops::RHO_CU),
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
