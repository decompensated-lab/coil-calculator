//! Browser entry points for `wasm32-unknown-unknown` (the module has no imports).
//!
//! The worker copies a request (format: `coilcal_core::app`) into a buffer from [`alloc`],
//! calls [`call`], reads `u32 len` + response from the returned pointer, then frees both
//! buffers with [`dealloc`]. A panic traps (`panic = "abort"`); the worker then starts over
//! with a fresh instance.

use std::ptr::slice_from_raw_parts_mut;

/// A zeroed buffer of `len` bytes.
#[unsafe(no_mangle)]
pub extern "C" fn alloc(len: usize) -> *mut u8 {
    Box::into_raw(vec![0u8; len].into_boxed_slice()) as *mut u8
}

/// Frees a buffer from [`alloc`] or [`call`] (`len` = its full length).
///
/// # Safety
/// `ptr` and `len` must come from one of those calls, and the buffer is freed only once.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn dealloc(ptr: *mut u8, len: usize) {
    drop(unsafe { Box::from_raw(slice_from_raw_parts_mut(ptr, len)) });
}

/// Runs `app::call` on the request at `ptr`; returns a buffer of `4 + len` bytes.
///
/// # Safety
/// `ptr..ptr + len` must be readable memory of this module.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn call(ptr: *const u8, len: usize) -> *mut u8 {
    let req = unsafe { std::slice::from_raw_parts(ptr, len) };
    let resp = coilcal_core::app::call(req);
    let mut out = Vec::with_capacity(4 + resp.len());
    out.extend((resp.len() as u32).to_le_bytes());
    out.extend(resp);
    Box::into_raw(out.into_boxed_slice()) as *mut u8
}
