r"""Electrostatics of coil turns: Maxwell capacitance matrix between turns.

Each turn is a closed ring conductor (a torus of the wire radius ``a``) at a single potential,
optionally inside a concentric dielectric sleeve (the insulation, outer radius ``b``), with
an optional dielectric tube (the :class:`~coilcal.geometry.Former`) under the winding. The
reference conductor is infinity (no ground plane).

Coaxial coils form an axisymmetric problem, solved in the (ρ, z) half-plane:

* **Wires** - charge-simulation method: ``n_sub`` ring charges at radius ``alpha·b`` inside
  each wire represent the field outside the insulation, matched on ``n_sub`` collocation rings
  on the insulation surface ``r = b``. A wire is locally two-dimensional (``b ≪ R``), so the
  sleeve is eliminated exactly by its per-harmonic Dirichlet-to-Neumann map. For harmonic
  ``k`` of the exterior potential on ``r = b`` (wire potential ``V``, sleeve permittivity ε):

      k = 0:  b·ln(b/a)·∂φ/∂r = ε (φ − V)
      k ≥ 1:  b·(1 − u)·∂φ/∂r = k ε (1 + u)·φ,      u = (a/b)^(2k)

  For a bare wire (``b = a``) this is the classic CSM condition φ = V on the wire surface.
* **Former** - boundary elements, total-charge formulation. The tube's rectangular (ρ, z)
  cross-section is divided into straight ring panels carrying bound charge

      σ_b = 2 ε0 (ε − 1)/(ε + 1) · E_n ,

  where E_n is the principal-value normal field of all charges (wires and panels). Panels are
  graded toward the wires and corners; near-singular panel integrals use composite Gauss
  rules.

Between non-coaxial coils (well separated compared to the wire) a thin-wire potential
coefficient averaged around the ring is used, and dielectric bodies act only within their own
coaxial group.

A lossy dielectric (complex ε = εr(1 − j tanδ)) gives a complex C; the network's ``jωC`` then
includes the dielectric loss conductance.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy.constants import epsilon_0
from scipy.special import ellipe, ellipkm1

from .geometry import SolenoidCoil
from .types import ArrayLike, ComplexArray, FloatArray

_K = 1 / (4 * np.pi * epsilon_0)
_GL_X, _GL_W = np.polynomial.legendre.leggauss(8)
_GL2_X, _GL2_W = np.polynomial.legendre.leggauss(2)

__all__ = [
    "auto_n_sub",
    "capacitance_matrix",
    "isolated_capacitance",
    "ring_field",
    "ring_potential",
]


# --- ring-charge kernels ---------------------------------------------------------------
def ring_potential(b: ArrayLike, rho: ArrayLike, z: ArrayLike) -> FloatArray:
    """Potential [V] at cylindrical (rho, z) of a ring of radius ``b`` in z=0 carrying 1 C."""
    bb, rr, zz = np.broadcast_arrays(*(np.asarray(x, dtype=float) for x in (b, rho, z)))
    d2 = (bb + rr) ** 2 + zz**2
    m1 = ((bb - rr) ** 2 + zz**2) / d2  # 1 - m, computed without cancellation
    return _K * (2 / np.pi) * ellipkm1(m1) / np.sqrt(d2)


def _ring_all(
    b: FloatArray, rho: FloatArray, z: FloatArray
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Potential, E_rho and E_z of a 1 C ring (radius b, plane z=0) at (rho > 0, z)."""
    d2 = (b + rho) ** 2 + z**2
    q2 = (b - rho) ** 2 + z**2
    m1 = q2 / d2
    k = ellipkm1(m1)
    e = ellipe(1 - m1)
    sd = np.sqrt(d2)
    phi = _K * (2 / np.pi) * k / sd
    ez = _K * (2 / np.pi) * z * e / (q2 * sd)
    er = _K / np.pi * (k - (b * b - rho * rho + z * z) / q2 * e) / (rho * sd)
    return phi, er, ez


def ring_field(b: ArrayLike, rho: ArrayLike, z: ArrayLike) -> tuple[FloatArray, FloatArray]:
    """Field (E_rho, E_z) [V/m] at (rho > 0, z) of a ring of radius ``b`` in z=0 carrying 1 C."""
    bb, rr, zz = np.broadcast_arrays(*(np.asarray(x, dtype=float) for x in (b, rho, z)))
    _, er, ez = _ring_all(bb, rr, zz)
    return er, ez


# --- coaxial groups ----------------------------------------------------------------------
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


# --- geometry of one coaxial group in its (rho, z) half-plane -------------------------------
@dataclass(frozen=True)
class _Wires:
    """All turns of a coaxial group: centre (R, z), conductor a, insulation b and ε."""

    r: FloatArray
    z: FloatArray
    a: FloatArray
    b: FloatArray
    eps: ComplexArray


@dataclass(frozen=True)
class _Tube:
    r_in: float
    r_out: float
    z0: float
    z1: float
    eps: complex


@dataclass(frozen=True)
class _Panels:
    p1: FloatArray  # (P, 2) start (rho, z)
    p2: FloatArray  # (P, 2) end
    lam: ComplexArray  # (P,) (ε − 1)/(ε + 1)

    @property
    def mid(self) -> FloatArray:
        return 0.5 * (self.p1 + self.p2)

    @property
    def length(self) -> FloatArray:
        return np.asarray(np.linalg.norm(self.p2 - self.p1, axis=1))

    @property
    def normal(self) -> FloatArray:
        """Unit normal pointing out of the dielectric (boundary traversed counter-clockwise)."""
        t = (self.p2 - self.p1) / self.length[:, None]
        return np.column_stack([t[:, 1], -t[:, 0]])

    @property
    def area(self) -> FloatArray:
        return 2 * np.pi * self.mid[:, 0] * self.length


def _group_geometry(
    coils: Sequence[SolenoidCoil], origin: FloatArray, axis: FloatArray
) -> tuple[_Wires, list[_Tube]]:
    r, z, a, b, eps = [], [], [], [], []
    tubes: list[_Tube] = []
    for c in coils:
        sgn = np.sign(np.dot(c.axis, axis))
        z0 = float(np.dot(c.position - origin, axis) * sgn)
        n = c.n_turns
        r.append(np.full(n, c.mean_radius))
        z.append(z0 + sgn * c.turn_z())
        a.append(np.full(n, c.wire_radius))
        b.append(np.full(n, c.outer_radius))
        e = c.insulation.eps_complex if c.outer_radius > c.wire_radius else 1.0
        eps.append(np.full(n, e, dtype=complex))
        f = c.former
        if f is not None and f.dielectric.eps_complex != 1:
            half = c.length / 2 + f.overhang
            ro = c.former_d / 2
            tubes.append(_Tube(ro - f.wall, ro, z0 - half, z0 + half, f.dielectric.eps_complex))
    wires = _Wires(*(np.concatenate(x) for x in (r, z, a, b, eps)))
    return wires, _merge_tubes(tubes, wires)


def _merge_tubes(tubes: list[_Tube], wires: _Wires) -> list[_Tube]:
    """Join identical tubes that touch or overlap axially; reject intersecting bodies."""
    merged: list[_Tube] = []
    for t in sorted(tubes, key=lambda t: (t.r_in, t.r_out, t.z0)):
        last = merged[-1] if merged else None
        if (
            last is not None
            and (last.r_in, last.r_out, last.eps) == (t.r_in, t.r_out, t.eps)
            and t.z0 <= last.z1
        ):
            merged[-1] = _Tube(last.r_in, last.r_out, last.z0, max(last.z1, t.z1), last.eps)
        else:
            merged.append(t)
    for i, t in enumerate(merged):
        for u in merged[i + 1 :]:
            if t.r_in < u.r_out and u.r_in < t.r_out and t.z0 < u.z1 and u.z0 < t.z1:
                raise ValueError("coil formers intersect (overlapping tubes of different specs)")
        # distance from each wire centre to the tube's rectangle must be >= its outer radius
        dr = np.maximum.reduce([t.r_in - wires.r, wires.r - t.r_out, np.zeros_like(wires.r)])
        dz = np.maximum.reduce([t.z0 - wires.z, wires.z - t.z1, np.zeros_like(wires.z)])
        if np.any(np.hypot(dr, dz) < wires.b * (1 - 1e-9)):
            raise ValueError("a winding intersects a coil former")
    return merged


def _mesh_tubes(tubes: list[_Tube], wires: _Wires, h_min: float) -> _Panels:
    """Panels on each tube's boundary, sized ~0.4 × distance to the nearest wire or corner."""
    p1s, p2s, lams = [], [], []
    for t in tubes:
        h_max = max(h_min, 0.2 * t.r_out, 0.1 * (t.z1 - t.z0))
        corners = np.array([(t.r_in, t.z0), (t.r_out, t.z0), (t.r_out, t.z1), (t.r_in, t.z1)])
        for c0, c1 in zip(corners, np.roll(corners, -1, axis=0), strict=True):
            length = float(np.linalg.norm(c1 - c0))
            d = (c1 - c0) / length
            nvec = np.array([d[1], -d[0]])  # outward normal of this edge

            # a wire touching this edge gets a panel centred on the contact point, so that no
            # panel edge (where the piecewise-constant charge jumps) sits under the contact
            rel = np.stack([wires.r - c0[0], wires.z - c0[1]], axis=1)
            along, off = rel @ d, rel @ nvec
            touch = (np.abs(off - wires.b) < 1e-9 * wires.b) & (along > 0) & (along < length)
            forced = np.sort(np.concatenate([along[touch] - h_min / 2, along[touch] + h_min / 2]))
            forced = forced[(forced > 0) & (forced < length)]
            nodes = [0.0]
            for target in [*forced, length]:
                start = nodes[-1]
                if target <= start:
                    continue
                s_loc = [start]
                while s_loc[-1] < target:
                    sv = s_loc[-1]
                    p = c0 + d * sv
                    dw = np.hypot(wires.r - p[0], wires.z - p[1]) - wires.b
                    dist = min(float(dw.min()), sv, length - sv)
                    s_loc.append(sv + float(np.clip(0.4 * dist, h_min, h_max)))
                seg = np.asarray(s_loc)
                seg = start + (seg - start) * (target - start) / (seg[-1] - start)
                nodes += list(seg[1:])
            pts = c0 + np.asarray(nodes)[:, None] * d
            p1s.append(pts[:-1])
            p2s.append(pts[1:])
            lams.append(np.full(len(pts) - 1, (t.eps - 1) / (t.eps + 1)))
    if not p1s:
        return _Panels(np.zeros((0, 2)), np.zeros((0, 2)), np.zeros(0, complex))
    return _Panels(np.concatenate(p1s), np.concatenate(p2s), np.concatenate(lams))


def _panel_eval(
    pan: _Panels, tr: FloatArray, tz: FloatArray, self_pairs: bool = False, chunk: int = 1 << 20
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Potential, E_rho, E_z at targets (tr, tz) per unit total charge on each panel (T, P).

    Charge is uniform in surface density over the panel (a conical/cylindrical strip). The
    Gauss rule is subdivided for targets close to a panel. With ``self_pairs`` the targets are
    the panel midpoints and the self term is the principal value (symmetric composite rule).
    """
    nt, npan = len(tr), len(pan.p1)
    mid, half = pan.mid, 0.5 * (pan.p2 - pan.p1)
    length = pan.length
    out = [np.zeros((nt, npan)) for _ in range(3)]
    if npan == 0 or nt == 0:
        return out[0], out[1], out[2]
    # target-to-segment distance -> subdivision level per pair
    tp = np.stack([tr, tz], axis=1)
    rel = tp[:, None, :] - pan.p1[None, :, :]
    seg = (pan.p2 - pan.p1)[None]
    tpar = np.clip((rel * seg).sum(-1) / (length**2)[None], 0, 1)
    dist = np.linalg.norm(rel - tpar[..., None] * seg, axis=-1)
    ratio = length[None, :] / np.maximum(dist, 1e-300)
    # level 0: far pairs, 2-point Gauss; level n >= 1: n sub-panels with 8 points each
    nsub = np.where(ratio < 0.5, 1, 2 ** np.clip(np.ceil(np.log2(4 * ratio)), 1, 9)).astype(int)
    nsub[ratio < 0.15] = 0
    if self_pairs:
        nsub[np.arange(nt), np.arange(nt)] = 16
    for level in np.unique(nsub):
        if level == 0:
            x, w = _GL2_X, _GL2_W
        else:
            x = ((np.arange(level)[:, None] * 2 + 1 + _GL_X[None, :]) / level - 1).ravel()
            w = np.tile(_GL_W, level) / level
        ti, pj = np.nonzero(nsub == level)
        step = max(1, chunk // len(x))
        for s in range(0, len(ti), step):
            i, j = ti[s : s + step], pj[s : s + step]
            qr = mid[j, 0][:, None] + x[None, :] * half[j, 0][:, None]
            qz = mid[j, 1][:, None] + x[None, :] * half[j, 1][:, None]
            # charge weight per unit panel charge: dq = σ 2πρ ds with σ = 1/area
            wq = w[None, :] * qr / (2 * mid[j, 0][:, None])
            phi, er, ez = _ring_all(qr, tr[i][:, None], tz[i][:, None] - qz)
            out[0][i, j] = (wq * phi).sum(1)
            out[1][i, j] = (wq * er).sum(1)
            out[2][i, j] = (wq * ez).sum(1)
    return out[0], out[1], out[2]


def _dft_rows(m: int) -> tuple[FloatArray, FloatArray]:
    """Real DFT on the collocation angles: (M, M) matrix and the harmonic index of each row."""
    theta = 2 * np.pi * (np.arange(m) + 0.5) / m
    rows, harm = [np.full(m, 1.0 / m)], [0]
    for k in range(1, m // 2):
        rows += [2 / m * np.cos(k * theta), 2 / m * np.sin(k * theta)]
        harm += [k, k]
    rows.append(1 / m * np.sin(m // 2 * theta))  # cos(M/2·θ) vanishes on these angles
    harm.append(m // 2)
    return np.array(rows), np.array(harm, dtype=float)


# --- main solver -----------------------------------------------------------------------
_CACHE: OrderedDict[tuple[object, ...], FloatArray | ComplexArray] = OrderedDict()
_CACHE_SIZE = 32


def _coil_key(c: SolenoidCoil) -> tuple[object, ...]:
    return (
        c.wire_d,
        c.pitch,
        c.former_d,
        c.n_turns,
        tuple(np.round(c.position, 15)),
        tuple(np.round(c.orientation.as_quat(canonical=True), 15)),
        c.insulation_d,
        c.insulation,
        c.former,
    )


def auto_n_sub(coils: Sequence[SolenoidCoil]) -> int:
    """Charge rings per turn for ~1e-3 accuracy of the turn-to-turn capacitance.

    Close turns crowd the charge on facing sides, needing more harmonics: the count grows as
    sqrt(b / g) with g the conductor-to-conductor gap (16 at pitch = 2 × wire Ø; 48 for
    enamelled wire wound with touching turns), capped at 64.
    """
    n = 16.0
    for c in coils:
        g = max(c.pitch - c.wire_d, 1e-12)
        n = max(n, 16 * np.sqrt(c.outer_radius / g))
    return int(min(64, 8 * np.ceil(n / 8)))


def capacitance_matrix(
    coils: Sequence[SolenoidCoil],
    n_sub: int | None = None,
    alpha: float = 0.6,
    n_phi: int = 256,
    h_wire: float = 0.6,
) -> FloatArray | ComplexArray:
    """Maxwell capacitance matrix [F] between all turns of ``coils`` (in order).

    ``Q = C V`` with turn potentials referenced to infinity. Diagonal entries are positive,
    off-diagonal entries negative (real parts, if a dielectric is lossy). The result is real
    unless a dielectric has ``tan_delta > 0``.

    Parameters
    ----------
    n_sub
        Ring charges (and collocation rings) per turn; even. ``None``: :func:`auto_n_sub`.
    alpha
        Radius of the charge rings as a fraction of the insulation radius ``b``.
    n_phi
        Points around the ring for the thin-wire coupling between non-coaxial coils.
    h_wire
        Former panel size at a wire contact as a fraction of half the collocation spacing
        (π·b/n_sub). Must stay below ~1: coarser panels make the near-contact solution erratic.
    """
    coils = list(coils)
    if n_sub is None:
        n_sub = auto_n_sub(coils)
    if n_sub % 2 or n_sub < 4:
        raise ValueError("n_sub must be even and >= 4")
    key = (tuple(_coil_key(c) for c in coils), n_sub, alpha, n_phi, h_wire)
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key].copy()
    c = _solve(coils, n_sub, alpha, n_phi, h_wire)
    _CACHE[key] = c
    if len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)
    return c.copy()


def _solve(
    coils: list[SolenoidCoil], n_sub: int, alpha: float, n_phi: int, h_wire: float
) -> FloatArray | ComplexArray:
    m = n_sub
    counts = [c.n_turns for c in coils]
    toffs = np.concatenate([[0], np.cumsum(counts)]).astype(int)
    n_total = int(toffs[-1])
    nw = n_total * m  # wire unknowns (and rows): turn t, sub-index -> t*m + j
    groups = _coaxial_groups(coils)
    theta = 2 * np.pi * (np.arange(m) + 0.5) / m
    cos_t, sin_t = np.cos(theta), np.sin(theta)
    fmat, harm = _dft_rows(m)

    # geometry, panels and global index of every group's turns / panels
    geo = []
    n_pan_total = 0
    for g in groups:
        frame = _axial_frame([coils[i] for i in g])
        assert frame is not None  # groups are coaxial by construction
        wires, tubes = _group_geometry([coils[i] for i in g], *frame)
        # panels near a wire must be finer than its collocation spacing (2πb/M)
        pan = _mesh_tubes(tubes, wires, h_wire * np.pi * float(wires.b.min()) / m)
        turns = np.concatenate([np.arange(toffs[i], toffs[i + 1]) for i in g])
        geo.append((wires, pan, turns, nw + n_pan_total))
        n_pan_total += len(pan.p1)
    nu = nw + n_pan_total
    lossy = any(np.iscomplexobj(w.eps) and np.any(w.eps.imag) for w, *_ in geo) or any(
        np.any(p.lam.imag) for _, p, *_ in geo
    )
    dtype = complex if lossy else float

    def cast(v: ComplexArray) -> ComplexArray | FloatArray:
        return v if lossy else v.real

    amat = np.zeros((nu, nu), dtype=dtype)
    rhs = np.zeros((nu, n_total), dtype=dtype)

    # per-turn harmonic coefficients of the sleeve DtN map, normalised rows
    def dtn(wires: _Wires) -> tuple[ComplexArray, ComplexArray, FloatArray]:
        k = harm[None, :]
        a, b, e = wires.a[:, None], wires.b[:, None], wires.eps[:, None]
        u = (a / b) ** (2 * k)
        p = np.where(k == 0, np.log(b / a), 1 - u)  # × b·∂φ/∂r
        q = np.where(k == 0, e, k * e * (1 + u))  # × φ
        scale = 4 * np.pi * epsilon_0 * b / (np.abs(p) + np.abs(q))
        return p * scale, q * scale, b[:, 0]

    for wires, pan, turns, poff in geo:
        tg = len(wires.r)
        # charge rings and collocation rings, flattened turn-major
        sr = (wires.r[:, None] + alpha * wires.b[:, None] * cos_t).ravel()
        sz = (wires.z[:, None] + alpha * wires.b[:, None] * sin_t).ravel()
        cols_w = (turns[:, None] * m + np.arange(m)).ravel()
        npan = len(pan.p1)
        cols_p = np.arange(poff, poff + npan)
        p_k, q_k, b = dtn(wires)
        # rows of a turn: its harmonic conditions; row (t, r) shares the unknown index t*m + r.
        # Assemble in chunks of turns to bound the size of the kernel temporaries.
        n_chunk = max(1, (1 << 21) // (m * (tg * m + npan)))
        for t0 in range(0, tg, n_chunk):
            tt = np.arange(t0, min(t0 + n_chunk, tg))
            nr = len(tt)
            cr = (wires.r[tt, None] + wires.b[tt, None] * cos_t).ravel()
            cz = (wires.z[tt, None] + wires.b[tt, None] * sin_t).ravel()
            ct, st = np.tile(cos_t, nr), np.tile(sin_t, nr)
            phi, er, ez = _ring_all(sr[None, :], cr[:, None], cz[:, None] - sz[None, :])
            blocks = [(cols_w, phi, -(ct[:, None] * er + st[:, None] * ez))]
            if npan:
                pphi, per, pez = _panel_eval(pan, cr, cz)
                blocks.append((cols_p, pphi, -(ct[:, None] * per + st[:, None] * pez)))
            rows = (turns[tt][:, None] * m + np.arange(m)).ravel()
            for cols, ph, dr in blocks:
                ph3 = np.einsum("km,tmu->tku", fmat, ph.reshape(nr, m, -1))
                dr3 = np.einsum("km,tmu->tku", fmat, dr.reshape(nr, m, -1))
                blk = p_k[tt, :, None] * b[tt, None, None] * dr3 - q_k[tt, :, None] * ph3
                amat[np.ix_(rows, cols)] = cast(blk.reshape(nr * m, -1))
        rhs[turns * m, turns] = cast(-q_k[:, 0])

        if npan:
            nrm, area = pan.normal, pan.area
            mid = pan.mid
            en_w = np.empty((npan, len(sr)))
            step = max(1, (1 << 21) // len(sr))
            for p0 in range(0, npan, step):
                pp = slice(p0, p0 + step)
                _, er, ez = _ring_all(
                    sr[None, :], mid[pp, 0][:, None], mid[pp, 1][:, None] - sz[None, :]
                )
                en_w[pp] = er * nrm[pp, 0][:, None] + ez * nrm[pp, 1][:, None]
            _, per, pez = _panel_eval(pan, mid[:, 0], mid[:, 1], self_pairs=True)
            en_p = per * nrm[:, 0][:, None] + pez * nrm[:, 1][:, None]
            fac = (2 * epsilon_0 * pan.lam * area)[:, None]
            amat[np.ix_(cols_p, cols_w)] = cast(-fac * en_w)
            amat[np.ix_(cols_p, cols_p)] = cast(np.eye(npan) - fac * en_p)

    # thin-wire coupling between coaxial groups (enters the k = 0 row of each turn)
    def toff_of(i: int) -> slice:
        return slice(int(toffs[i]), int(toffs[i + 1]))

    for gi, g in enumerate(groups):
        for h in groups[gi + 1 :]:
            for i in g:
                for j in h:
                    pij = _thin_ring_potential_coeffs(coils[i], coils[j], n_phi)
                    for x, y, pxy in ((i, j, pij), (j, i, pij.T)):
                        wx = _Wires(
                            np.full(coils[x].n_turns, coils[x].mean_radius),
                            np.zeros(coils[x].n_turns),
                            np.full(coils[x].n_turns, coils[x].wire_radius),
                            np.full(coils[x].n_turns, coils[x].outer_radius),
                            np.full(
                                coils[x].n_turns,
                                coils[x].insulation.eps_complex
                                if coils[x].outer_radius > coils[x].wire_radius
                                else 1.0,
                                dtype=complex,
                            ),
                        )
                        q0 = dtn(wx)[1][:, 0]
                        tx = np.arange(toff_of(x).start, toff_of(x).stop)
                        ty = np.arange(toff_of(y).start, toff_of(y).stop)
                        cols = (ty[:, None] * m + np.arange(m)).ravel()
                        amat[np.ix_(tx * m, cols)] = cast(-q0[:, None] * np.repeat(pxy, m, axis=1))

    sol = np.linalg.solve(amat, rhs)
    c = sol[:nw].reshape(n_total, m, n_total).sum(axis=1)
    c = 0.5 * (c + c.T)
    return c if lossy else c.real


def isolated_capacitance(coil: SolenoidCoil, n_sub: int | None = None, alpha: float = 0.6) -> float:
    """Capacitance of the whole winding to infinity with all turns shorted together [F].

    Real part if a dielectric is lossy.
    """
    return float(np.real(capacitance_matrix([coil], n_sub=n_sub, alpha=alpha).sum()))
