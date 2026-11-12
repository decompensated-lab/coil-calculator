//! Dense solve `A X = B` (the reference is `numpy.linalg.solve`, i.e. LAPACK `?gesv`).
//!
//! Right-looking blocked LU with partial pivoting on the augmented row-major matrix
//! `[A | B]`, so the trailing update also performs the forward substitution; then a row-wise
//! back substitution. Pivots use `|re| + |im|` like LAPACK's `izamax`. The trailing update is a
//! packed GEMM with an explicit f64x2 micro-kernel under WASM `simd128` (one f64x2 holds two
//! reals or one complex) and a portable fallback elsewhere. It reaches the native 128-bit-SIMD
//! floor for real matrices; see `python/tests/port/bench.py` for the measurements.
//!
//! All matrices are row-major (numpy's C order).

use crate::c64;
use std::ops::{Add, Div, Mul, Sub};

/// Element type of the LU.
pub trait Scalar:
    Copy + Default + Add<Output = Self> + Sub<Output = Self> + Mul<Output = Self> + Div<Output = Self>
{
    /// Rows and columns of the GEMM micro-kernel tile (chosen by measurement under V8).
    const MR: usize;
    const NR: usize;
    /// Pivot magnitude (`|re| + |im|` for complex, as LAPACK's `izamax`).
    fn abs1(self) -> f64;
    /// `c[r * ldc + j] -= sum_p a[p * MR + r] * b[p * NR + j]` for the `mr x nr` corner.
    fn kernel(kb: usize, a: &[Self], b: &[Self], c: &mut [Self], ldc: usize, mr: usize, nr: usize);
}

#[cfg(not(all(target_arch = "wasm32", target_feature = "simd128")))]
use portable as kernels;
#[cfg(all(target_arch = "wasm32", target_feature = "simd128"))]
use simd as kernels;

impl Scalar for f64 {
    const MR: usize = 4;
    const NR: usize = 4;
    fn abs1(self) -> f64 {
        self.abs()
    }
    fn kernel(kb: usize, a: &[f64], b: &[f64], c: &mut [f64], ldc: usize, mr: usize, nr: usize) {
        kernels::real::<{ Self::MR }, { Self::NR / 2 }>(kb, a, b, c, ldc, mr, nr);
    }
}

impl Scalar for c64 {
    const MR: usize = 2;
    const NR: usize = 2;
    fn abs1(self) -> f64 {
        self.re.abs() + self.im.abs()
    }
    fn kernel(kb: usize, a: &[c64], b: &[c64], c: &mut [c64], ldc: usize, mr: usize, nr: usize) {
        kernels::complex::<{ Self::MR }, { Self::NR }>(kb, a, b, c, ldc, mr, nr);
    }
}

/// Portable micro-kernels, same tiles and summation order as `simd`.
#[cfg(not(all(target_arch = "wasm32", target_feature = "simd128")))]
#[allow(clippy::needless_range_loop)] // index loops over register tiles read best
mod portable {
    use super::c64;

    /// Real tile of `MR` rows by `2 * NV` columns.
    pub fn real<const MR: usize, const NV: usize>(
        kb: usize,
        a: &[f64],
        b: &[f64],
        c: &mut [f64],
        ldc: usize,
        mr: usize,
        nr: usize,
    ) {
        let mut acc = [[[0.0; 2]; NV]; MR];
        #[allow(clippy::chunks_exact_to_as_chunks)] // 2 * NV is not a const expression
        let b = b.chunks_exact(2 * NV);
        for (ap, bp) in a.as_chunks::<MR>().0.iter().zip(b).take(kb) {
            for r in 0..MR {
                for v in 0..NV {
                    for l in 0..2 {
                        acc[r][v][l] += ap[r] * bp[2 * v + l];
                    }
                }
            }
        }
        for r in 0..mr {
            for j in 0..nr {
                c[r * ldc + j] -= acc[r][j / 2][j % 2];
            }
        }
    }

    /// Complex tile of `MR` rows by `NC` columns.
    pub fn complex<const MR: usize, const NC: usize>(
        kb: usize,
        a: &[c64],
        b: &[c64],
        c: &mut [c64],
        ldc: usize,
        mr: usize,
        nr: usize,
    ) {
        // a*b = re(a)·(re b, im b) + im(a)·(−im b, re b): accumulate both products, combine once
        let mut acc_re = [[[0.0; 2]; NC]; MR];
        let mut acc_im = [[[0.0; 2]; NC]; MR];
        for (ap, bp) in a
            .as_chunks::<MR>()
            .0
            .iter()
            .zip(b.as_chunks::<NC>().0)
            .take(kb)
        {
            for r in 0..MR {
                for j in 0..NC {
                    let bv = [bp[j].re, bp[j].im];
                    for l in 0..2 {
                        acc_re[r][j][l] += ap[r].re * bv[l];
                        acc_im[r][j][l] += ap[r].im * bv[l];
                    }
                }
            }
        }
        for r in 0..mr {
            for j in 0..nr {
                let (re, im) = (acc_re[r][j], acc_im[r][j]);
                c[r * ldc + j] -= c64::new(re[0] - im[1], re[1] + im[0]);
            }
        }
    }
}

/// Explicit WASM `simd128` micro-kernels (one f64x2 = two reals or one complex).
#[cfg(all(target_arch = "wasm32", target_feature = "simd128"))]
#[allow(clippy::needless_range_loop)] // index loops over register tiles read best
mod simd {
    use super::c64;
    use core::arch::wasm32::*;

    /// Real tile of `MR` rows by `2 * NV` columns.
    #[inline(never)] // separate function so V8 tiers it up during the first solve
    pub fn real<const MR: usize, const NV: usize>(
        kb: usize,
        a: &[f64],
        b: &[f64],
        c: &mut [f64],
        ldc: usize,
        mr: usize,
        nr: usize,
    ) {
        assert!(a.len() >= kb * MR && b.len() >= kb * 2 * NV);
        let mut acc = [[f64x2_splat(0.0); NV]; MR];
        for p in 0..kb {
            // SAFETY: in bounds by the assert; wasm loads need no alignment.
            unsafe {
                let bp = b.as_ptr().add(p * 2 * NV);
                let bv: [v128; NV] = core::array::from_fn(|v| v128_load(bp.add(2 * v).cast()));
                for r in 0..MR {
                    let av = f64x2_splat(*a.get_unchecked(p * MR + r));
                    for v in 0..NV {
                        acc[r][v] = f64x2_add(acc[r][v], f64x2_mul(av, bv[v]));
                    }
                }
            }
        }
        for r in 0..mr {
            for v in 0..NV {
                for l in 0..2 {
                    let j = 2 * v + l;
                    if j < nr {
                        let x = if l == 0 {
                            f64x2_extract_lane::<0>(acc[r][v])
                        } else {
                            f64x2_extract_lane::<1>(acc[r][v])
                        };
                        c[r * ldc + j] -= x;
                    }
                }
            }
        }
    }

    /// Complex tile of `MR` rows by `NC` columns.
    #[inline(never)]
    pub fn complex<const MR: usize, const NC: usize>(
        kb: usize,
        a: &[c64],
        b: &[c64],
        c: &mut [c64],
        ldc: usize,
        mr: usize,
        nr: usize,
    ) {
        assert!(a.len() >= kb * MR && b.len() >= kb * NC);
        let mut acc_re = [[f64x2_splat(0.0); NC]; MR];
        let mut acc_im = [[f64x2_splat(0.0); NC]; MR];
        for p in 0..kb {
            // SAFETY: in bounds by the assert; c64 is repr(C) (re, im).
            unsafe {
                let bp = b.as_ptr().add(p * NC);
                let bv: [v128; NC] = core::array::from_fn(|j| v128_load(bp.add(j).cast()));
                let ap = a.as_ptr().add(p * MR).cast::<f64>();
                for r in 0..MR {
                    let ar = v128_load64_splat(ap.add(2 * r).cast());
                    let ai = v128_load64_splat(ap.add(2 * r + 1).cast());
                    for j in 0..NC {
                        acc_re[r][j] = f64x2_add(acc_re[r][j], f64x2_mul(ar, bv[j]));
                        acc_im[r][j] = f64x2_add(acc_im[r][j], f64x2_mul(ai, bv[j]));
                    }
                }
            }
        }
        // a*b = re(a)·(re b, im b) + im(a)·(−im b, re b)
        let sign = f64x2(-1.0, 1.0);
        for r in 0..mr {
            for j in 0..nr {
                let im = acc_im[r][j];
                let t = f64x2_add(acc_re[r][j], f64x2_mul(i64x2_shuffle::<1, 0>(im, im), sign));
                let z = &mut c[r * ldc + j];
                *z -= c64::new(f64x2_extract_lane::<0>(t), f64x2_extract_lane::<1>(t));
            }
        }
    }
}

const NB: usize = 64; // panel width
const MC: usize = 192; // rows of L21 packed per block
const NC: usize = 512; // columns of U12 packed per block

/// Solves `A X = B` for row-major `a` (n x n) and `b` (n x k); returns row-major `X`.
///
/// Returns `None` if a pivot is exactly zero (singular matrix).
pub fn solve_lu<T: Scalar>(a: &[T], b: &[T], n: usize, k: usize) -> Option<Vec<T>> {
    assert_eq!(a.len(), n * n);
    assert_eq!(b.len(), n * k);
    let w = n + k; // row stride of the augmented matrix [A | B]
    let mut m = vec![T::default(); n * w];
    for i in 0..n {
        m[i * w..i * w + n].copy_from_slice(&a[i * n..(i + 1) * n]);
        m[i * w + n..(i + 1) * w].copy_from_slice(&b[i * k..(i + 1) * k]);
    }
    let mut apack = vec![T::default(); MC.div_ceil(T::MR) * T::MR * NB];
    let mut bpack = vec![T::default(); NC.div_ceil(T::NR) * T::NR * NB];
    // The phases are separate non-inlined functions so that V8 can tier each one up between
    // calls; one big function would run its first (and only) call in baseline code.
    for k0 in (0..n).step_by(NB) {
        let k1 = (k0 + NB).min(n);
        factor_panel(&mut m, n, w, k0, k1)?;
        solve_u12(&mut m, w, k0, k1);
        if k1 < n {
            update_trailing(&mut m, n, w, k0, k1, &mut apack, &mut bpack);
        }
    }
    Some(back_substitute(&m, n, k))
}

/// Unblocked LU with row interchanges of rows `k0..n`, columns `k0..k1` (whole rows swap).
#[inline(never)]
fn factor_panel<T: Scalar>(m: &mut [T], n: usize, w: usize, k0: usize, k1: usize) -> Option<()> {
    for j in k0..k1 {
        let p = (j..n)
            .max_by(|&x, &y| m[x * w + j].abs1().total_cmp(&m[y * w + j].abs1()))
            .unwrap();
        if m[p * w + j].abs1() == 0.0 {
            return None;
        }
        if p != j {
            let (lo, hi) = m.split_at_mut(p * w);
            lo[j * w..(j + 1) * w].swap_with_slice(&mut hi[..w]);
        }
        let (top, rest) = m.split_at_mut((j + 1) * w);
        let prow = &top[j * w..];
        for row in rest.chunks_exact_mut(w) {
            let l = row[j] / prow[j];
            row[j] = l;
            for c in j + 1..k1 {
                row[c] = row[c] - l * prow[c];
            }
        }
    }
    Some(())
}

/// `U12 = L11^-1 A12`: rows `k0..k1`, columns `k1..w` (includes the right-hand sides).
#[inline(never)]
fn solve_u12<T: Scalar>(m: &mut [T], w: usize, k0: usize, k1: usize) {
    for j in k0..k1 {
        let (top, rest) = m.split_at_mut((j + 1) * w);
        let prow = &top[j * w..];
        for row in rest[..(k1 - j - 1) * w].chunks_exact_mut(w) {
            let l = row[j];
            for c in k1..w {
                row[c] = row[c] - l * prow[c];
            }
        }
    }
}

/// `A22 -= L21 U12` (rows `k1..n`, columns `k1..w`) as a packed GEMM.
#[inline(never)]
fn update_trailing<T: Scalar>(
    m: &mut [T],
    n: usize,
    w: usize,
    k0: usize,
    k1: usize,
    apack: &mut [T],
    bpack: &mut [T],
) {
    let kb = k1 - k0;
    let (top, bottom) = m.split_at_mut(k1 * w);
    for jc in (k1..w).step_by(NC) {
        let nc = NC.min(w - jc);
        // pack U12[:, jc..jc+nc] as NR-wide strips, p-major within a strip, zero-padded
        for (s, j0) in (0..nc).step_by(T::NR).enumerate() {
            let dst = &mut bpack[s * T::NR * kb..(s + 1) * T::NR * kb];
            for p in 0..kb {
                for jj in 0..T::NR {
                    let col = j0 + jj;
                    dst[p * T::NR + jj] = if col < nc {
                        top[(k0 + p) * w + jc + col]
                    } else {
                        T::default()
                    };
                }
            }
        }
        for ic in (0..n - k1).step_by(MC) {
            let mc = MC.min(n - k1 - ic);
            // pack L21[ic..ic+mc, :] as MR-high strips, p-major within a strip
            for (s, i0) in (0..mc).step_by(T::MR).enumerate() {
                let dst = &mut apack[s * T::MR * kb..(s + 1) * T::MR * kb];
                for ii in 0..T::MR {
                    let row = i0 + ii;
                    for p in 0..kb {
                        dst[p * T::MR + ii] = if row < mc {
                            bottom[(ic + row) * w + k0 + p]
                        } else {
                            T::default()
                        };
                    }
                }
            }
            for (sj, j0) in (0..nc).step_by(T::NR).enumerate() {
                let bp = &bpack[sj * T::NR * kb..(sj + 1) * T::NR * kb];
                let nr = T::NR.min(nc - j0);
                for (si, i0) in (0..mc).step_by(T::MR).enumerate() {
                    let ap = &apack[si * T::MR * kb..(si + 1) * T::MR * kb];
                    let mr = T::MR.min(mc - i0);
                    T::kernel(
                        kb,
                        ap,
                        bp,
                        &mut bottom[(ic + i0) * w + jc + j0..],
                        w,
                        mr,
                        nr,
                    );
                }
            }
        }
    }
}

/// `U X = Y` with `Y` in columns `n..n+k` of the factorised augmented matrix.
#[inline(never)]
fn back_substitute<T: Scalar>(m: &[T], n: usize, k: usize) -> Vec<T> {
    let w = n + k;
    let mut x = vec![T::default(); n * k];
    for i in (0..n).rev() {
        let mut acc = m[i * w + n..(i + 1) * w].to_vec();
        for j in i + 1..n {
            let u = m[i * w + j];
            for (a, &xj) in acc.iter_mut().zip(&x[j * k..(j + 1) * k]) {
                *a = *a - u * xj;
            }
        }
        let d = m[i * w + i];
        for (xi, a) in x[i * k..(i + 1) * k].iter_mut().zip(acc) {
            *xi = a / d;
        }
    }
    x
}
