r"""Capacitance per unit length between two long, parallel, insulated round wires in air.

Each wire is a round conductor (radius a) inside a concentric dielectric sleeve (outer radius
b, complex permittivity εr), the rest of space is vacuum/air. This is *not* the textbook
two-wire line in a uniform medium: the field crosses the dielectric–air boundary, so the
result lies between the bare-wire value and εr times it.

Method: 2-D multipole expansion (exact apart from truncation, converges geometrically unless
the sleeves touch, then algebraically). Around wire k the air potential is

    φ = −q_k/(2π ε0) ln r_k + Σ_n c_kn r_k^{-n} cos nθ_k + Σ_m d_km r_k^m cos mθ_k ,

where the regular part d (the field of the other wire) is obtained by re-expanding the other
wire's line charge and multipoles about wire k (both centres lie on the x axis, so only cosine
terms appear). Solving the sleeve problem for one harmonic (φ = const on r = a, φ and εr ∂φ/∂r
continuous at r = b) gives the reflection coefficient

    c_n = Γ_n b^{2n} d_n,   Γ_n = [(1 − u) − εr(1 + u)] / [(1 − u) + εr(1 + u)],  u = (a/b)^{2n}

(εr = 1 → bare conductor of radius a; εr → ∞ → bare conductor of radius b; a → 0 → plain
dielectric rod). The monopole part gives the conductor potential
V_k = q_k/(2π ε0)·[ln(b/a)/εr − ln b] + d_k0. With q1 = −q2 = q, C' = q / (V1 − V2).

A complex εr = εr'(1 − j tanδ) is carried through unchanged; the result is C' − jC'', i.e. a
shunt conductance G' = ω C'' per unit length (``tan_delta`` = C''/C').
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
from scipy.constants import epsilon_0
from scipy.special import gammaln

from .materials import Dielectric
from .types import ComplexArray, FloatArray

__all__ = [
    "InsulatedWire",
    "WirePairResult",
    "bare_pair_capacitance",
    "effective_radius",
    "pair_capacitance",
]


@dataclass(frozen=True, slots=True)
class InsulatedWire:
    """Round conductor with an optional concentric insulation sleeve. Lengths in metres."""

    conductor_d: float
    insulation_d: float | None = None  # outer diameter of the insulation; None = bare
    dielectric: Dielectric = field(default_factory=Dielectric)

    def __post_init__(self) -> None:
        if not self.conductor_d > 0:
            raise ValueError(f"conductor_d must be > 0, got {self.conductor_d}")
        if self.insulation_d is not None and not self.insulation_d >= self.conductor_d:
            raise ValueError(
                f"insulation_d ({self.insulation_d}) < conductor_d ({self.conductor_d})"
            )

    @property
    def a(self) -> float:
        return self.conductor_d / 2

    @property
    def b(self) -> float:
        return (self.insulation_d if self.insulation_d is not None else self.conductor_d) / 2

    @property
    def eps(self) -> complex:
        return self.dielectric.eps_complex if self.b > self.a else 1.0 + 0j


def bare_pair_capacitance(a1: float, a2: float, s: float) -> float:
    """Exact C' [F/m] between two bare round conductors (radii a1, a2, centre spacing s)."""
    if s <= a1 + a2:
        raise ValueError("conductors overlap or touch")
    return float(2 * np.pi * epsilon_0 / np.arccosh((s * s - a1 * a1 - a2 * a2) / (2 * a1 * a2)))


def effective_radius(w: InsulatedWire) -> float:
    """Radius of the bare wire with the same isolated (monopole) capacitance: b·(a/b)^(1/εr).

    Exact for a lone wire; ignores the field crowding between close neighbours.
    """
    return float(w.b * (w.a / w.b) ** (1 / w.dielectric.eps_r)) if w.b > w.a else w.a


@dataclass(frozen=True)
class WirePairResult:
    """Solution for charges +q (wire 1) and −q (wire 2), scaled to 1 V between conductors.

    Wire 1 is centred at x = −s/2, wire 2 at x = +s/2.
    """

    wires: tuple[InsulatedWire, InsulatedWire]
    spacing: float
    c_complex: complex  # F/m, C' − jC''
    n_terms: int
    converged: bool
    _coef: ComplexArray  # (2, N) scaled multipole coefficients c̃
    _dreg: ComplexArray  # (2, N+1) scaled regular coefficients d̃ (index 0 = constant)
    _q: complex  # q/(2π ε0) [V] on wire 1 for 1 V difference
    _v: ComplexArray  # (2,) conductor potentials [V]

    @property
    def capacitance(self) -> float:
        """C' [F/m]."""
        return float(self.c_complex.real)

    @property
    def tan_delta(self) -> float:
        """Effective loss tangent of the line, C''/C'."""
        return float(-self.c_complex.imag / self.c_complex.real)

    def conductance(self, freq: float) -> float:
        """Shunt conductance G' [S/m] at ``freq`` from the dielectric loss."""
        return float(2 * np.pi * freq * -self.c_complex.imag)

    @property
    def conductor_potentials(self) -> ComplexArray:
        """Potentials [V] of conductors 1 and 2 (V1 − V2 = 1 V; common mode → 0 at ∞)."""
        return self._v.copy()

    @property
    def centres(self) -> FloatArray:
        return np.array([-self.spacing / 2, self.spacing / 2])

    def potential(self, x: FloatArray, y: FloatArray) -> ComplexArray:
        """Potential [V] at points (x, y) for 1 V between the conductors."""
        x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
        n = np.arange(1, self._coef.shape[1] + 1)
        qs = (self._q, -self._q)
        out = np.zeros(x.shape, complex)
        rk, th = [], []
        for xc in self.centres:
            rk.append(np.hypot(x - xc, y))
            th.append(np.arctan2(y, x - xc))
        in_air = np.ones(x.shape, bool)
        for k, w in enumerate(self.wires):
            in_air &= rk[k] >= w.b
        # air: line charges + multipoles of both wires
        for k, w in enumerate(self.wires):
            r = np.maximum(rk[k][in_air], w.b)
            cos = np.cos(np.outer(th[k][in_air], n))
            out[in_air] += -qs[k] * np.log(r) + (self._coef[k] * cos * (w.b / r)[:, None] ** n).sum(
                axis=1
            )
        # inside each wire: sleeve solution, conductor constant
        for k, w in enumerate(self.wires):
            cond = rk[k] < w.a
            out[cond] = self._v[k]
            sl = (rk[k] >= w.a) & (rk[k] < w.b)
            if sl.any():
                r = rk[k][sl]
                u = (w.a / w.b) ** (2 * n)
                amp = 2 * self._dreg[k, 1:] / ((1 - u) + w.eps * (1 + u))
                radial = (r[:, None] / w.b) ** n - u * (w.b / r)[:, None] ** n
                harm = (amp * radial * np.cos(np.outer(th[k][sl], n))).sum(axis=1)
                out[sl] = self._v[k] - qs[k] / w.eps * np.log(r / w.a) + harm
        return out


def _solve(w1: InsulatedWire, w2: InsulatedWire, s: float, n_terms: int) -> WirePairResult:
    wires = (w1, w2)
    n = np.arange(1, n_terms + 1)
    m = n
    gam = []
    for w in wires:
        u = (w.a / w.b) ** (2 * n)
        gam.append(((1 - u) - w.eps * (1 + u)) / ((1 - u) + w.eps * (1 + u)))
    # Lengths normalised by s; potentials in units of q/(2π ε0) with q1 = 1, q2 = -1.
    b = np.array([w1.b, w2.b]) / s
    q = np.array([1.0, -1.0])
    dsign = {(0, 1): -1.0, (1, 0): 1.0}  # sign of D = x_k − x_j (|D| = 1)
    # regular field at k from j:  log term h, multipole re-expansion T
    h = np.zeros((2, n_terms), complex)
    t = {}
    lg = gammaln(n[None, :] + m[:, None]) - gammaln(m[:, None] + 1) - gammaln(n[None, :])
    for (k, j), sg in dsign.items():
        h[k] = -q[j] * (-1.0) ** (m + 1) / m * (sg * b[k]) ** m
        mag = np.exp(lg + m[:, None] * np.log(b[k]) + n[None, :] * np.log(b[j]))
        t[k, j] = mag * (-1.0) ** m[:, None] * sg ** (m[:, None] + n[None, :])
    g1, g2 = gam
    a_mat = np.block(
        [
            [np.eye(n_terms), -g1[:, None] * t[0, 1]],
            [-g2[:, None] * t[1, 0], np.eye(n_terms)],
        ]
    )
    rhs = np.concatenate([g1 * h[0], g2 * h[1]])
    coef = np.linalg.solve(a_mat, rhs).reshape(2, n_terms)
    d = np.stack([h[0] + t[0, 1] @ coef[1], h[1] + t[1, 0] @ coef[0]])
    v = np.empty(2, complex)
    d0 = np.empty(2, complex)
    for (k, j), sg in dsign.items():
        w = wires[k]
        d0[k] = (coef[j] * (sg * b[j]) ** n).sum()  # ln|D| = 0 in units of s
        v[k] = q[k] * (np.log(w.b / w.a) / w.eps - np.log(b[k])) + d0[k]
    dv = v[0] - v[1]
    # Rescale to 1 V across the pair. Because q1 + q2 = 0 the potentials are the same whether
    # lengths are measured in units of s or in metres (the ln s terms cancel).
    scale = 1 / dv
    return WirePairResult(
        wires=wires,
        spacing=s,
        c_complex=complex(2 * np.pi * epsilon_0 * scale),
        n_terms=n_terms,
        converged=False,
        _coef=coef * scale,
        _dreg=np.concatenate([d0[:, None], d], axis=1) * scale,
        _q=complex(scale),
        _v=v * scale,
    )


def pair_capacitance(
    w1: InsulatedWire,
    w2: InsulatedWire | None = None,
    spacing: float = 0.0,
    *,
    rtol: float = 1e-9,
    max_terms: int = 1024,
) -> WirePairResult:
    """C' between two parallel insulated wires at centre-to-centre ``spacing`` [m].

    The sleeves may touch (``spacing == b1 + b2``) but not overlap. The number of multipole
    terms is doubled from 8 until C' changes by less than ``rtol`` (relative) or
    ``max_terms`` is reached (``converged`` reports which).
    """
    w2 = w1 if w2 is None else w2
    if spacing < (w1.b + w2.b) * (1 - 1e-12):
        raise ValueError(
            f"spacing {spacing:g} m < sum of outer radii {w1.b + w2.b:g} m (wires overlap)"
        )
    if spacing <= w1.a + w2.a:
        raise ValueError("bare conductors touch")
    nt = 8
    prev = _solve(w1, w2, spacing, nt)
    while nt < max_terms:
        nt = min(2 * nt, max_terms)
        cur = _solve(w1, w2, spacing, nt)
        if abs(cur.c_complex - prev.c_complex) <= rtol * abs(cur.c_complex):
            return _with_converged(cur, True)
        prev = cur
    return _with_converged(prev, False)


def _with_converged(r: WirePairResult, ok: bool) -> WirePairResult:
    return replace(r, converged=ok)
