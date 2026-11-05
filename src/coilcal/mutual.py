"""Mutual inductance between coils and derived quantities (quasi-static)."""

from __future__ import annotations

from typing import Literal

import magpylib as magpy
import numpy as np

from .field import Model, to_magpylib
from .geometry import SolenoidCoil
from .inductance import ac_resistance, self_inductance
from .loops import mutual_coaxial, mutual_rings


def _coaxial_sign(a: SolenoidCoil, b: SolenoidCoil, atol: float = 1e-12) -> int:
    """+1/-1 if the coils share an axis (parallel/antiparallel), else 0."""
    ax_a, ax_b = a.axis, b.axis
    if np.linalg.norm(np.cross(ax_a, ax_b)) > atol:
        return 0
    d = b.position - a.position
    scale = max(a.mean_radius, b.mean_radius)
    if np.linalg.norm(d - np.dot(d, ax_a) * ax_a) > atol * max(scale, 1.0):
        return 0
    return 1 if np.dot(ax_a, ax_b) > 0 else -1


def mutual_matrix(
    a: SolenoidCoil,
    b: SolenoidCoil,
    n_phi: int | None = None,
    rtol: float = 1e-9,
    max_n_phi: int = 1 << 14,
) -> np.ndarray:
    """Turn-by-turn mutual inductances (N_a, N_b) [H] using the ring model.

    Coaxial coils use Maxwell's closed form; otherwise the vector-potential line integral is
    evaluated with ``n_phi`` points per ring, or (``n_phi=None``) doubled from 64 until the
    matrix changes by less than ``rtol * sum|M_ij|``.
    """
    sign = _coaxial_sign(a, b)
    if sign:
        za = np.dot(a.turn_centers() - a.position, a.axis)
        zb = np.dot(b.turn_centers() - a.position, a.axis)
        return sign * mutual_coaxial(a.mean_radius, b.mean_radius, zb[None, :] - za[:, None])

    def run(n):
        return mutual_rings(
            a.mean_radius, a.orientation, a.turn_centers(),
            b.mean_radius, b.orientation, b.turn_centers(),
            n_phi=n,
        )  # fmt: skip

    if n_phi is not None:
        return run(n_phi)
    n = 64
    prev = run(n)
    while n < max_n_phi:
        n *= 2
        cur = run(n)
        # scale by sum|M_ij| so that configurations with M ~ 0 (by symmetry) still converge
        if np.abs(cur - prev).sum() <= rtol * np.abs(cur).sum():
            return cur
        prev = cur
    raise RuntimeError(
        f"mutual inductance did not converge with n_phi={max_n_phi} (do the windings touch?)"
    )


def mutual_inductance(
    a: SolenoidCoil,
    b: SolenoidCoil,
    method: Literal["rings", "flux"] = "rings",
    **kwargs,
) -> float:
    """Mutual inductance between coils ``a`` and ``b`` [H].

    ``method="rings"`` (default, accurate): ring model, see :func:`mutual_matrix`.
    ``method="flux"``: independent check; magpylib field of ``a`` integrated over the flat disk
    spanned by each turn of ``b`` (kwargs: ``model``, ``n_r``, ``n_phi``, ``pts_per_turn``). Less
    accurate when a winding of ``a`` passes close to a disk of ``b``; slow with ``model="helix"``.

    Sign: positive when positive currents in both coils produce aiding flux.
    """
    if method == "rings":
        return float(mutual_matrix(a, b, **kwargs).sum())
    if method == "flux":
        return flux_linkage(a, b, current_a=1.0, **kwargs)
    raise ValueError(f"unknown method {method!r}")


def flux_linkage(
    a: SolenoidCoil,
    b: SolenoidCoil,
    current_a: float = 1.0,
    model: Model = "rings",
    n_r: int = 48,
    n_phi: int = 96,
    pts_per_turn: int = 180,
) -> float:
    """Total flux of coil ``a`` (carrying ``current_a``) linked by the turns of ``b`` [Wb]."""
    x, w = np.polynomial.legendre.leggauss(n_r)
    rb = b.mean_radius
    r = (x + 1) * rb / 2
    wr = w * rb / 2 * r  # includes Jacobian r dr
    phi = 2 * np.pi * np.arange(n_phi) / n_phi
    rr, pp = np.meshgrid(r, phi, indexing="ij")
    disk = np.stack([rr * np.cos(pp), rr * np.sin(pp), np.zeros_like(rr)], -1).reshape(-1, 3)
    weights = (wr[:, None] * np.full(n_phi, 2 * np.pi / n_phi)[None, :]).ravel()

    local = (
        disk[None, :, :]
        + np.stack([np.zeros(b.n_turns), np.zeros(b.n_turns), b.turn_z()], -1)[:, None, :]
    )
    pts = b.to_global(local.reshape(-1, 3))
    src = to_magpylib(a, current=current_a, model=model, pts_per_turn=pts_per_turn)
    bfield = np.asarray(magpy.getB(src, pts, sumup=True))
    bn = bfield @ b.axis
    return float((bn.reshape(b.n_turns, -1) * weights).sum())


def coupling_coefficient(
    a: SolenoidCoil, b: SolenoidCoil, freq: float | None = None, m: float | None = None
) -> float:
    """k = M / sqrt(L_a L_b)."""
    m = mutual_inductance(a, b) if m is None else m
    return m / np.sqrt(self_inductance(a, freq) * self_inductance(b, freq))


def induced_emf(
    a: SolenoidCoil,
    b: SolenoidCoil,
    current_a: complex,
    freq: float,
    m: float | None = None,
) -> complex:
    """Open-circuit EMF phasor in coil ``b`` for current phasor ``current_a`` in ``a`` [V].

    ``V_b = -j omega M I_a`` (Faraday sign; take ``abs()`` for amplitude). If ``current_a`` is a
    peak (RMS) amplitude, the result is a peak (RMS) amplitude.
    """
    m = mutual_inductance(a, b) if m is None else m
    return -1j * 2 * np.pi * freq * m * current_a


def induced_voltage_loaded(
    a: SolenoidCoil,
    b: SolenoidCoil,
    current_a: complex,
    freq: float,
    z_load: complex,
    m: float | None = None,
    include_resistance: bool = True,
) -> complex:
    """Voltage across a load ``z_load`` connected to coil ``b`` [V].

    Coil ``a`` is current-driven (its current is imposed, so the back-reaction of ``b`` does not
    change it). Coil ``b`` is modelled as ``R_b + j omega L_b`` in series with the EMF.
    """
    emf = induced_emf(a, b, current_a, freq, m)
    omega = 2 * np.pi * freq
    z_b = 1j * omega * self_inductance(b, freq)
    if include_resistance:
        z_b += ac_resistance(b, freq)
    return emf * z_load / (z_load + z_b)
