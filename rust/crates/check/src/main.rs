//! Check binary: answers kernel requests from pytest over stdin/stdout (see `wire`).

mod wire;

use coilcal_core::{c64, linalg};
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

fn dispatch(name: &str, args: Vec<Array>) -> Result<Vec<Array>, String> {
    match name {
        "echo" => Ok(args),
        "solve" => solve(&args),
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
