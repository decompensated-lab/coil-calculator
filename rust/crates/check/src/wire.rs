//! Binary wire format between pytest and the check binary (all little-endian).
//!
//! ```text
//! request  = u32 name_len, name (utf-8), u32 n_arrays, array*
//! response = u8 0, u32 n_arrays, array*          (success)
//!          | u8 1, u32 msg_len, msg (utf-8)       (error)
//! array    = u8 complex, u8 ndim, u64 shape[ndim], f64 data[prod(shape) * (1 + complex)]
//! ```
//!
//! Complex data is interleaved re/im, which is numpy's `complex128` memory layout.

use std::io::{self, Read, Write};

#[derive(Debug, Clone, PartialEq)]
pub struct Array {
    pub complex: bool,
    pub shape: Vec<usize>,
    /// Row-major (C order); interleaved re/im if `complex`.
    pub data: Vec<f64>,
}

#[allow(dead_code)] // constructors are used by the kernels from M1 on
impl Array {
    pub fn real(shape: Vec<usize>, data: Vec<f64>) -> Self {
        debug_assert_eq!(shape.iter().product::<usize>(), data.len());
        Self {
            complex: false,
            shape,
            data,
        }
    }
    pub fn complex(shape: Vec<usize>, data: Vec<f64>) -> Self {
        debug_assert_eq!(2 * shape.iter().product::<usize>(), data.len());
        Self {
            complex: true,
            shape,
            data,
        }
    }
    pub fn scalar(x: f64) -> Self {
        Self::real(vec![], vec![x])
    }
    pub fn len(&self) -> usize {
        self.shape.iter().product()
    }
}

fn read_u32(r: &mut impl Read) -> io::Result<u32> {
    let mut b = [0; 4];
    r.read_exact(&mut b)?;
    Ok(u32::from_le_bytes(b))
}

#[cfg(test)]
fn read_string(r: &mut impl Read) -> io::Result<String> {
    let n = read_u32(r)? as usize;
    let mut b = vec![0; n];
    r.read_exact(&mut b)?;
    String::from_utf8(b).map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))
}

fn read_array(r: &mut impl Read) -> io::Result<Array> {
    let mut hdr = [0; 2];
    r.read_exact(&mut hdr)?;
    let mut shape = Vec::with_capacity(hdr[1] as usize);
    for _ in 0..hdr[1] {
        let mut b = [0; 8];
        r.read_exact(&mut b)?;
        shape.push(u64::from_le_bytes(b) as usize);
    }
    let complex = hdr[0] != 0;
    let n = shape.iter().product::<usize>() * if complex { 2 } else { 1 };
    let mut bytes = vec![0; 8 * n];
    r.read_exact(&mut bytes)?;
    let data = bytes
        .as_chunks::<8>()
        .0
        .iter()
        .map(|&c| f64::from_le_bytes(c))
        .collect();
    Ok(Array {
        complex,
        shape,
        data,
    })
}

fn write_array(w: &mut impl Write, a: &Array) -> io::Result<()> {
    w.write_all(&[a.complex as u8, a.shape.len() as u8])?;
    for &s in &a.shape {
        w.write_all(&(s as u64).to_le_bytes())?;
    }
    let mut bytes = Vec::with_capacity(8 * a.data.len());
    for x in &a.data {
        bytes.extend_from_slice(&x.to_le_bytes());
    }
    w.write_all(&bytes)
}

/// Reads one request; `Ok(None)` on a clean end of input.
pub fn read_request(r: &mut impl Read) -> io::Result<Option<(String, Vec<Array>)>> {
    let mut b = [0; 4];
    match r.read_exact(&mut b) {
        Err(e) if e.kind() == io::ErrorKind::UnexpectedEof => return Ok(None),
        res => res?,
    }
    let mut name = vec![0; u32::from_le_bytes(b) as usize];
    r.read_exact(&mut name)?;
    let name =
        String::from_utf8(name).map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;
    let n = read_u32(r)?;
    let arrays = (0..n).map(|_| read_array(r)).collect::<io::Result<_>>()?;
    Ok(Some((name, arrays)))
}

#[cfg(test)]
pub fn write_request(w: &mut impl Write, name: &str, arrays: &[Array]) -> io::Result<()> {
    w.write_all(&(name.len() as u32).to_le_bytes())?;
    w.write_all(name.as_bytes())?;
    w.write_all(&(arrays.len() as u32).to_le_bytes())?;
    arrays.iter().try_for_each(|a| write_array(w, a))
}

pub fn write_response(w: &mut impl Write, res: &Result<Vec<Array>, String>) -> io::Result<()> {
    match res {
        Ok(arrays) => {
            w.write_all(&[0])?;
            w.write_all(&(arrays.len() as u32).to_le_bytes())?;
            arrays.iter().try_for_each(|a| write_array(w, a))?;
        }
        Err(msg) => {
            w.write_all(&[1])?;
            w.write_all(&(msg.len() as u32).to_le_bytes())?;
            w.write_all(msg.as_bytes())?;
        }
    }
    w.flush()
}

#[cfg(test)]
pub fn read_response(r: &mut impl Read) -> io::Result<Result<Vec<Array>, String>> {
    let mut tag = [0; 1];
    r.read_exact(&mut tag)?;
    if tag[0] != 0 {
        return Ok(Err(read_string(r)?));
    }
    let n = read_u32(r)?;
    Ok(Ok((0..n)
        .map(|_| read_array(r))
        .collect::<io::Result<_>>()?))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trip_is_bit_exact() {
        let arrays = vec![
            Array::scalar(f64::from_bits(0x7ff8_dead_beef_0001)), // NaN payload survives
            Array::real(
                vec![2, 3],
                vec![1.0, -0.0, f64::INFINITY, 1e-310, f64::MAX, 0.1],
            ),
            Array::complex(vec![2], vec![1.0, 2.0, -3.0, f64::MIN_POSITIVE]),
            Array::real(vec![0, 4], vec![]),
        ];
        let mut buf = Vec::new();
        write_request(&mut buf, "echo", &arrays).unwrap();
        let (name, back) = read_request(&mut buf.as_slice()).unwrap().unwrap();
        assert_eq!(name, "echo");
        let bits = |a: &[Array]| -> Vec<Vec<u64>> {
            a.iter()
                .map(|x| x.data.iter().map(|v| v.to_bits()).collect())
                .collect()
        };
        assert_eq!(bits(&back), bits(&arrays));
        assert!(
            back.iter()
                .zip(&arrays)
                .all(|(a, b)| a.shape == b.shape && a.complex == b.complex)
        );

        for res in [Ok(arrays.clone()), Err("boom".to_string())] {
            let mut buf = Vec::new();
            write_response(&mut buf, &res).unwrap();
            let back = read_response(&mut buf.as_slice()).unwrap();
            assert_eq!(back.map(|a| bits(&a)), res.map(|a| bits(&a)));
        }
    }

    #[test]
    fn clean_eof_ends_the_loop() {
        assert!(read_request(&mut [].as_slice()).unwrap().is_none());
    }
}
