"""Electrostatics of coil turns: Maxwell capacitance matrix between turns (free space).

Each turn is treated as a closed ring conductor (toroidal surface of the wire radius) at a
single potential. Within a group of coaxial coils the problem is axisymmetric and solved with
the *charge simulation method*: ``n_sub`` ring charges inside each wire cross-section and as
many collocation rings on its surface. This captures charge crowding between closely spaced
turns. Between non-coaxial coils (always well separated compared to the wire radius) a
thin-wire potential coefficient averaged around the ring is used.

The reference conductor is infinity (no ground plane); the former's dielectric is ignored.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from scipy.constants import epsilon_0
from scipy.special import ellipk

from .geometry import SolenoidCoil
from .types import ArrayLike, FloatArray

_K = 1 / (4 * np.pi * epsilon_0)


def ring_potential(b: ArrayLike, rho: ArrayLike, z: ArrayLike) -> FloatArray:
    """Potential [V] at cylindrical (rho, z) of a ring of radius ``b`` in z=0 carrying 1 C."""
    bb, rr, zz = np.broadcast_arrays(*(np.asarray(x, dtype=float) for x in (b, rho, z)))
    d2 = (bb + rr) ** 2 + zz**2
    m = 4 * bb * rr / d2
    return _K * (2 / np.pi) * ellipk(m) / np.sqrt(d2)


def _axial_frame(coils: Sequence[SolenoidCoil]) -> tuple[FloatArray, FloatArray] | None:
    """Common axis origin/direction for a coaxial group, or None if not coaxial."""
    ref = coils[0]
    ax = ref.axis
    for c in coils[1:]:
        if np.linalg.norm(np.cross(ax, c.axis)) > 1e-12:
            return None
        d = c.position - ref.position
        if np.linalg.norm(d - np.dot(d, ax) * ax) > 1e-12 * max(1.0, ref.mean_radius):
            return None
    return ref.position, ax


def _coaxial_groups(coils: Sequence[SolenoidCoil]) -> list[list[int]]:
    groups: list[list[int]] = []
    for i, c in enumerate(coils):
        for g in groups:
            if _axial_frame([coils[g[0]], c]) is not None:
                g.append(i)
                break
        else:
            groups.append([i])
    return groups


def _csm_potential_matrix(
    coils: Sequence[SolenoidCoil], origin: FloatArray, axis: FloatArray, n_sub: int, alpha: float
) -> FloatArray:
    """Axisymmetric CSM: potential at collocation rings due to unit charge rings."""
    theta = 2 * np.pi * (np.arange(n_sub) + 0.5) / n_sub
    parts: list[list[FloatArray]] = [[], [], [], []]
    rc, zc, rp, zp = parts
    for c in coils:
        z0 = np.dot(c.position - origin, axis) * np.sign(np.dot(c.axis, axis))
        zt = z0 + np.sign(np.dot(c.axis, axis)) * c.turn_z()
        a = c.wire_radius
        rc.append(c.mean_radius + alpha * a * np.cos(theta)[None, :] + 0 * zt[:, None])
        zc.append(zt[:, None] + alpha * a * np.sin(theta)[None, :])
        rp.append(c.mean_radius + a * np.cos(theta)[None, :] + 0 * zt[:, None])
        zp.append(zt[:, None] + a * np.sin(theta)[None, :])
    rc_a, zc_a, rp_a, zp_a = (np.concatenate([x.ravel() for x in arr]) for arr in parts)
    return ring_potential(rc_a[None, :], rp_a[:, None], zp_a[:, None] - zc_a[None, :])


def _thin_ring_potential_coeffs(a: SolenoidCoil, b: SolenoidCoil, n_phi: int) -> FloatArray:
    """Average potential on each turn of ``a`` per coulomb on each turn of ``b`` (NA, NB)."""
    phi = 2 * np.pi * np.arange(n_phi) / n_phi
    ring = np.column_stack([np.cos(phi), np.sin(phi), np.zeros(n_phi)]) * a.mean_radius
    out = np.empty((a.n_turns, b.n_turns))
    inv_b = b.orientation.inv()
    pts_a = a.turn_centers()[:, None, :] + a.orientation.apply(ring)[None, :, :]  # (NA,P,3)
    for j, cb in enumerate(b.turn_centers()):
        q = inv_b.apply((pts_a - cb).reshape(-1, 3)).reshape(pts_a.shape)
        v = ring_potential(b.mean_radius, np.hypot(q[..., 0], q[..., 1]), q[..., 2])
        out[:, j] = v.mean(axis=1)
    return out


def capacitance_matrix(
    coils: Sequence[SolenoidCoil],
    n_sub: int = 16,
    alpha: float = 0.6,
    n_phi: int = 256,
) -> FloatArray:
    """Maxwell capacitance matrix [F] between all turns of ``coils`` (in order).

    ``Q = C V`` with turn potentials referenced to infinity. Diagonal entries are positive,
    off-diagonal entries negative.
    """
    coils = list(coils)
    counts = [c.n_turns for c in coils]
    offs = np.concatenate([[0], np.cumsum(counts)])
    n_total = offs[-1]
    nsub_total = n_total * n_sub

    p = np.empty((nsub_total, nsub_total))
    groups = _coaxial_groups(coils)
    sub = lambda i: slice(offs[i] * n_sub, offs[i + 1] * n_sub)
    for g in groups:
        frame = _axial_frame([coils[i] for i in g])
        assert frame is not None  # groups are coaxial by construction
        origin, axis = frame
        pg = _csm_potential_matrix([coils[i] for i in g], origin, axis, n_sub, alpha)
        go = np.concatenate([[0], np.cumsum([counts[i] * n_sub for i in g])])
        for ii, i in enumerate(g):
            for jj, j in enumerate(g):
                p[sub(i), sub(j)] = pg[go[ii] : go[ii + 1], go[jj] : go[jj + 1]]
    for gi, g in enumerate(groups):
        for h in groups[gi + 1 :]:
            for i in g:
                for j in h:
                    pij = _thin_ring_potential_coeffs(coils[i], coils[j], n_phi)
                    # every collocation ring of turn i sees the same potential from every
                    # charge ring of turn j (thin-wire approximation between distant coils)
                    blk = np.repeat(np.repeat(pij, n_sub, axis=0), n_sub, axis=1)
                    p[sub(i), sub(j)] = blk
                    p[sub(j), sub(i)] = blk.T

    s = np.zeros((n_total, nsub_total))
    for t in range(n_total):
        s[t, t * n_sub : (t + 1) * n_sub] = 1.0
    c = s @ np.linalg.solve(p, s.T)
    return 0.5 * (c + c.T)


def isolated_capacitance(coil: SolenoidCoil, n_sub: int = 16, alpha: float = 0.6) -> float:
    """Capacitance of the whole winding to infinity with all turns shorted together [F]."""
    return float(capacitance_matrix([coil], n_sub=n_sub, alpha=alpha).sum())
