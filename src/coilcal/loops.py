"""Filamentary circular-loop magnetostatics: vector potential, mutual and self inductance.

All functions are vectorised with numpy broadcasting and use SI units.
"""

from __future__ import annotations

import numpy as np
from scipy.constants import mu_0
from scipy.spatial.transform import Rotation
from scipy.special import ellipe, ellipk, jve

from .types import ArrayLike, FloatArray

RHO_CU = 1.68e-8  # resistivity of annealed copper at 20 °C [ohm m]

# Below this value of m = k^2 the closed form (1-m/2)K - E suffers cancellation; use series.
_M_SERIES = 1e-3


def mutual_coaxial(r1: ArrayLike, r2: ArrayLike, dz: ArrayLike) -> FloatArray:
    """Mutual inductance of two coaxial circular filaments (Maxwell's formula) [H].

    ``M = mu0 sqrt(r1 r2) [(2/k - k) K(k) - (2/k) E(k)]``, ``k^2 = 4 r1 r2 / ((r1+r2)^2 + dz^2)``.
    """
    r1, r2, dz = np.broadcast_arrays(*(np.asarray(x, dtype=float) for x in (r1, r2, dz)))
    d2 = (r1 + r2) ** 2 + dz**2
    m = 4 * r1 * r2 / d2
    out = np.empty_like(m)
    small = m < _M_SERIES
    # Large-distance branch: M = mu0*pi*r1^2 r2^2 / (2 D^3) * (1 + 3m/4 + 75m^2/128) with D=sqrt(d2)
    ms, ds = m[small], np.sqrt(d2[small])
    out[small] = (
        mu_0
        * np.pi
        * (r1[small] * r2[small]) ** 2
        / (2 * ds**3)
        * (1 + 0.75 * ms + 75 / 128 * ms**2)
    )
    ml = m[~small]
    k = np.sqrt(ml)
    out[~small] = (
        mu_0 * np.sqrt(r1[~small] * r2[~small]) * ((2 / k - k) * ellipk(ml) - (2 / k) * ellipe(ml))
    )
    return out


def a_phi_over_rho(a: ArrayLike, rho: ArrayLike, z: ArrayLike) -> FloatArray:
    """Azimuthal vector potential of a unit-current ring, divided by rho [T].

    Ring of radius ``a`` in the plane z=0 centred on the origin, current 1 A CCW about +z.
    Returning ``A_phi / rho`` keeps the result finite on the axis; the Cartesian vector
    potential is then ``A = (A_phi/rho) * (-y, x, 0)``.
    """
    a, rho, z = np.broadcast_arrays(*(np.asarray(x, dtype=float) for x in (a, rho, z)))
    d2 = (a + rho) ** 2 + z**2
    m = 4 * a * rho / d2
    out = np.empty_like(m)
    small = m < _M_SERIES
    # series: A_phi = mu0 a^2 rho / (4 D^3) * (1 + 3m/4 + 75m^2/128)
    ms = m[small]
    out[small] = mu_0 * a[small] ** 2 / (4 * d2[small] ** 1.5) * (1 + 0.75 * ms + 75 / 128 * ms**2)
    ml = m[~small]
    k = np.sqrt(ml)
    al, rl = a[~small], rho[~small]
    a_phi = mu_0 / (np.pi * k) * np.sqrt(al / rl) * ((1 - ml / 2) * ellipk(ml) - ellipe(ml))
    out[~small] = a_phi / rl
    return out


def mutual_rings(
    radius_a: float,
    rot_a: Rotation,
    centers_a: ArrayLike,
    radius_b: float,
    rot_b: Rotation,
    centers_b: ArrayLike,
    n_phi: int = 128,
) -> FloatArray:
    """Mutual inductances between two families of arbitrarily placed circular filaments.

    Computes ``M_ij = oint_{ring b_j} A(ring a_i) . dl`` with the analytic ring vector
    potential and a periodic trapezoidal rule (spectrally convergent in ``n_phi``).

    Parameters
    ----------
    radius_a, radius_b
        Ring radii [m].
    rot_a, rot_b
        ``scipy.spatial.transform.Rotation`` local->global for each family (ring normal = local z).
    centers_a, centers_b
        Ring centres, shapes (NA, 3) and (NB, 3) [m].
    n_phi
        Number of quadrature points around each ring of family b.

    Returns
    -------
    ndarray (NA, NB) of mutual inductances [H].
    """
    ca_all = np.atleast_2d(np.asarray(centers_a, dtype=float))
    cb_all = np.atleast_2d(np.asarray(centers_b, dtype=float))
    phi = 2 * np.pi * np.arange(n_phi) / n_phi
    ring = np.column_stack([np.cos(phi), np.sin(phi), np.zeros(n_phi)]) * radius_b
    tang = np.column_stack([-np.sin(phi), np.cos(phi), np.zeros(n_phi)]) * radius_b  # dl/dphi

    rel = rot_a.inv() * rot_b  # b-local -> a-local rotation
    ring_a = rel.apply(ring)  # (P,3) offsets in a-frame
    tang_a = rel.apply(tang)  # (P,3)

    out = np.empty((len(ca_all), len(cb_all)))
    inv_a = rot_a.inv()
    for i, ca in enumerate(ca_all):
        cb_a = inv_a.apply(cb_all - ca)  # (NB,3) centres of b rings in ring-i frame
        q = cb_a[:, None, :] + ring_a[None, :, :]  # (NB,P,3)
        rho = np.hypot(q[..., 0], q[..., 1])
        g = a_phi_over_rho(radius_a, rho, q[..., 2])
        integrand = g * (-q[..., 1] * tang_a[:, 0] + q[..., 0] * tang_a[:, 1])
        out[i] = integrand.sum(axis=1) * (2 * np.pi / n_phi)
    return out


def internal_inductance_per_length(
    wire_radius: float, freq: float | None, rho: float = RHO_CU
) -> float:
    """Internal inductance per unit length of a straight round wire [H/m].

    Uses the exact Bessel-function solution of the skin effect. ``freq=None`` or 0 gives the
    DC value ``mu0/(8 pi)``; at high frequency it tends to ``mu0 delta / (4 pi a)``.
    """
    if not freq:
        return float(mu_0 / (8 * np.pi))
    omega = 2 * np.pi * freq
    return float(internal_impedance_per_length(wire_radius, freq, rho).imag / omega)


def internal_impedance_per_length(
    wire_radius: float, freq: float | None, rho: float = RHO_CU
) -> complex:
    """Internal impedance per unit length of an isolated round wire (skin effect only) [ohm/m]."""
    if not freq:
        return complex(rho / (np.pi * wire_radius**2), 0.0)
    a = wire_radius
    kc = (1 - 1j) / skin_depth(freq, rho)
    # exponentially scaled Bessel functions: the scale factor cancels in the ratio
    return complex(kc * rho / (2 * np.pi * a) * jve(0, kc * a) / jve(1, kc * a))


def skin_depth(freq: float, rho: float = RHO_CU) -> float:
    """Skin depth in a non-magnetic conductor [m]."""
    return float(np.sqrt(rho / (np.pi * freq * mu_0)))


def loop_self_inductance(radius: float, wire_radius: float, freq: float | None = None) -> float:
    """Self-inductance of a single circular loop of round wire (thin-wire limit) [H].

    ``L = mu0 R (ln(8R/a) - 2) + L_int' * 2 pi R``; at DC the internal term is mu0 R/4.
    """
    external = mu_0 * radius * (np.log(8 * radius / wire_radius) - 2)
    return float(external + internal_inductance_per_length(wire_radius, freq) * 2 * np.pi * radius)
