"""Independent 2-D reference: panel BEM for parallel round wires and dielectric polygons.

Total-charge formulation with piecewise-constant density on straight panels and *exact*
panel integrals (closed form for a uniformly charged segment), so near-contact geometries
are handled without quadrature error. Error is O(h) from the geometry/density discretisation;
use :func:`richardson` across two resolutions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.constants import epsilon_0


@dataclass
class Wire2D:
    x: float
    y: float
    a: float  # conductor radius
    b: float | None = None  # insulation outer radius
    eps: float = 1.0
    v: float = 0.0  # potential (common mode is solved for, so only differences matter)


@dataclass
class Polygon2D:
    vertices: np.ndarray  # (V, 2), counter-clockwise
    eps: float
    grade_to: list[tuple[float, float]] = field(default_factory=list)


def _segment(p1, p2, x):
    """φ·2πε0 and E·2πε0 (global components) at points x of unit-density segments."""
    t = p2 - p1
    length = np.linalg.norm(t, axis=-1)
    t = t / length[..., None]
    n = np.stack([t[..., 1], -t[..., 0]], axis=-1)
    d = x - p1
    s = (d * t).sum(-1)
    u = (d * n).sum(-1)

    def f(v):
        r2 = v * v + u * u
        with np.errstate(divide="ignore", invalid="ignore"):
            lg = np.where(r2 > 0, v * np.log(np.where(r2 > 0, r2, 1)), 0.0)
            at = np.where(u != 0, u * np.arctan(v / np.where(u != 0, u, 1)), 0.0)
        return 0.5 * (lg - 2 * v + 2 * at)

    phi = -(f(s) - f(s - length))
    with np.errstate(divide="ignore", invalid="ignore"):
        es = 0.5 * np.log((s * s + u * u) / ((s - length) ** 2 + u * u))
    eu = np.arctan2(u * length, s * (s - length) + u * u)
    return phi, es[..., None] * t + eu[..., None] * n


def _circle(xc, yc, r, n):
    t = 2 * np.pi * np.arange(n + 1) / n
    return np.stack([xc + r * np.cos(t), yc + r * np.sin(t)], axis=1)


def _graded_polygon(poly: Polygon2D, h_min: float, h_max: float) -> np.ndarray:
    pts = [poly.vertices[0]]
    v = poly.vertices
    focus = np.array(poly.grade_to) if poly.grade_to else np.zeros((0, 2))
    for c0, c1 in zip(v, np.roll(v, -1, axis=0), strict=True):
        length = np.linalg.norm(c1 - c0)
        d = (c1 - c0) / length
        s = [0.0]
        while s[-1] < length:
            p = c0 + d * s[-1]
            df = np.min(np.linalg.norm(focus - p, axis=1)) if len(focus) else np.inf
            dist = min(df, s[-1], length - s[-1])
            s.append(s[-1] + np.clip(0.3 * dist, h_min, h_max))
        nodes = np.asarray(s) * length / s[-1]
        pts += list(c0 + nodes[1:, None] * d)
    return np.asarray(pts)


def capacitance_2d(
    wires: list[Wire2D], polys: list[Polygon2D], n_circle: int, h_min: float, h_max: float
) -> float:
    """C' [F/m] of wire 0 against the others for the given potentials (V0 − V1 = 1 V)."""
    p1, p2, kind, owner, lam = [], [], [], [], []
    for k, w in enumerate(wires):
        c = _circle(w.x, w.y, w.a, n_circle)
        p1.append(c[:-1])
        p2.append(c[1:])
        kind += ["cond"] * n_circle
        owner += [k] * n_circle
        lam += [0.0] * n_circle
        if w.b is not None and w.b > w.a:
            c = _circle(w.x, w.y, w.b, n_circle)
            p1.append(c[:-1])
            p2.append(c[1:])
            kind += ["iface"] * n_circle
            owner += [k] * n_circle
            lam += [(w.eps - 1) / (w.eps + 1)] * n_circle
    for poly in polys:
        c = _graded_polygon(poly, h_min, h_max)
        c = np.vstack([c, c[:1]]) if not np.allclose(c[-1], c[0]) else c
        p1.append(c[:-1])
        p2.append(c[1:])
        n = len(c) - 1
        kind += ["iface"] * n
        owner += [-1] * n
        lam += [(poly.eps - 1) / (poly.eps + 1)] * n
    a1, a2 = np.concatenate(p1), np.concatenate(p2)
    kind_a, owner_a, lam_a = np.array(kind), np.array(owner), np.array(lam)
    mid = 0.5 * (a1 + a2)
    length = np.linalg.norm(a2 - a1, axis=1)
    tan = (a2 - a1) / length[:, None]
    nrm = np.stack([tan[:, 1], -tan[:, 0]], axis=1)
    phi, e = _segment(a1[None], a2[None], mid[:, None])
    npan = len(mid)
    idx = np.arange(npan)
    e[idx, idx] = 0.0  # principal value of the normal field on a flat panel
    en = (e * nrm[:, None, :]).sum(-1)
    eps_w = np.array([w.eps if (w.b is not None and w.b > w.a) else 1.0 for w in wires])
    a = np.zeros((npan + 1, npan + 1))
    rhs = np.zeros(npan + 1)
    cond = kind_a == "cond"
    ci, ii = np.nonzero(cond)[0], np.nonzero(~cond)[0]
    a[ci, :npan] = phi[ci]
    a[ci, npan] = -1.0
    rhs[ci] = [wires[o].v for o in owner_a[ci]]
    a[ii, :npan] = -(lam_a[ii, None] / np.pi) * en[ii]
    a[ii, ii] += 1.0
    a[npan, :npan] = np.where(cond, length * eps_w[np.maximum(owner_a, 0)], 0.0)
    s = np.linalg.solve(a, rhs)[:npan]
    q0 = 2 * np.pi * epsilon_0 * (s * length * eps_w[0])[cond & (owner_a == 0)].sum()
    dv = wires[0].v - wires[1].v
    return float(q0 / dv)


def richardson(f, n: int, **kw) -> float:
    """Extrapolate an O(h) quantity from resolutions n and 2n (f(n, **kw))."""
    return 2 * f(2 * n, **kw) - f(n, **kw)
