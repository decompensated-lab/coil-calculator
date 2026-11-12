import numpy as np
import pytest
from scipy.constants import epsilon_0

from coilcal.materials import Dielectric, Material
from coilcal.wirepair import (
    InsulatedWire,
    bare_pair_capacitance,
    effective_radius,
    pair_capacitance,
)

MM = 1e-3


def _bem_pair(w1: InsulatedWire, w2: InsulatedWire, s: float, n: int) -> float:
    """Independent check: 2-D panel BEM in the total-charge (free + bound) formulation.

    Unknowns: total charge density on each conductor surface and bound charge density on each
    sleeve surface (flat chord panels, midpoint collocation, Gauss-Legendre far terms). Sleeve
    condition: σ_b = 2 ε0 (εr − 1)/(εr + 1) · E_n(average). Free charge on a conductor is εr
    times the total charge on its surface. A common-mode potential keeps q1 + q2 = 0.
    """
    gx, gw = np.polynomial.legendre.leggauss(8)
    pans = []  # (mid (P,2), normal (P,2), tangent (P,2), length (P,), kind, wire)
    for k, (w, xc) in enumerate(((w1, -s / 2), (w2, s / 2))):
        radii = [(w.a, "cond")] + ([(w.b, "sleeve")] if w.b > w.a else [])
        for rad, kind in radii:
            t = 2 * np.pi * np.arange(n + 1) / n
            p = np.stack([xc + rad * np.cos(t), rad * np.sin(t)], axis=1)
            mid = 0.5 * (p[1:] + p[:-1])
            tan = p[1:] - p[:-1]
            ln = np.linalg.norm(tan, axis=1)
            tan = tan / ln[:, None]
            nor = np.stack([tan[:, 1], -tan[:, 0]], axis=1)  # outward for CCW
            pans.append((mid, nor, tan, ln, kind, k))
    mid = np.concatenate([p[0] for p in pans])
    nor = np.concatenate([p[1] for p in pans])
    tan = np.concatenate([p[2] for p in pans])
    ln = np.concatenate([p[3] for p in pans])
    kind = np.concatenate([[p[4]] * len(p[0]) for p in pans])
    wire = np.concatenate([[p[5]] * len(p[0]) for p in pans])
    npan = len(mid)
    # quadrature points on each source panel
    qp = (mid[:, None, :] + tan[:, None, :] * (gx[None, :, None] * ln[:, None, None] / 2))[None]
    qw = gw[None, :] * ln[:, None] / 2  # (P, Q)
    d = mid[:, None, None, :] - qp  # (P_obs, P_src, Q, 2)
    r2 = (d**2).sum(-1)
    pot = -(np.log(r2) / 2 * qw[None]).sum(-1) / (2 * np.pi)  # φ per unit σ/ε0
    en = ((d * nor[:, None, None, :]).sum(-1) / r2 * qw[None]).sum(-1) / (2 * np.pi)
    i = np.arange(npan)
    pot[i, i] = -ln * (np.log(ln / 2) - 1) / (2 * np.pi)
    en[i, i] = 0.0
    eps = np.array([w1.dielectric.eps_r if w1.b > w1.a else 1.0,
                    w2.dielectric.eps_r if w2.b > w2.a else 1.0])  # fmt: skip
    # unknowns: σ (npan), V0 ; rows: panels, charge neutrality
    a = np.zeros((npan + 1, npan + 1))
    rhs = np.zeros(npan + 1)
    for p in range(npan):
        if kind[p] == "cond":
            a[p, :npan] = pot[p]
            a[p, npan] = -1.0
            rhs[p] = 0.5 if wire[p] == 0 else -0.5
        else:
            lam = (eps[wire[p]] - 1) / (eps[wire[p]] + 1)
            a[p, :npan] = -2 * lam * en[p]
            a[p, p] += 1.0
    cond = kind == "cond"
    a[npan, :npan] = np.where(cond, ln * eps[wire], 0.0)
    sig = np.linalg.solve(a, rhs)[:npan]
    q1 = (sig * ln * eps[wire])[cond & (wire == 0)].sum()
    return float(epsilon_0 * q1)


@pytest.mark.parametrize("s_mm", [1.05, 2.0, 7.0])
def test_bare_limit_matches_closed_form(s_mm):
    w = InsulatedWire(1 * MM)
    r = pair_capacitance(w, spacing=s_mm * MM)
    assert r.converged
    assert r.capacitance == pytest.approx(
        bare_pair_capacitance(0.5 * MM, 0.5 * MM, s_mm * MM), rel=1e-9, abs=0
    )


def test_unequal_bare_wires():
    w1, w2 = InsulatedWire(1 * MM), InsulatedWire(0.3 * MM)
    r = pair_capacitance(w1, w2, spacing=1.0 * MM)
    assert r.capacitance == pytest.approx(
        bare_pair_capacitance(0.5 * MM, 0.15 * MM, 1 * MM), rel=1e-9, abs=0
    )


def test_eps_one_sleeve_is_bare_and_huge_eps_is_conductor_of_radius_b():
    s = 2.4 * MM
    air = InsulatedWire(1 * MM, 1.6 * MM, Dielectric(1.0))
    assert pair_capacitance(air, spacing=s).capacitance == pytest.approx(
        bare_pair_capacitance(0.5 * MM, 0.5 * MM, s), rel=1e-9, abs=0
    )
    metal = InsulatedWire(1 * MM, 1.6 * MM, Dielectric(1e7))
    assert pair_capacitance(metal, spacing=s).capacitance == pytest.approx(
        bare_pair_capacitance(0.8 * MM, 0.8 * MM, s), rel=1e-5, abs=0
    )


@pytest.mark.parametrize(
    ("w1", "w2", "s_mm"),
    [
        (InsulatedWire(1 * MM, 1.8 * MM, Dielectric(4.0)), None, 2.2),
        (InsulatedWire(1 * MM, 1.6 * MM, Dielectric(2.1)), None, 3.0),
        (InsulatedWire(1 * MM, 1.8 * MM, Dielectric(6.0)),
         InsulatedWire(0.6 * MM, 1.4 * MM, Dielectric(2.5)), 2.0),
        (InsulatedWire(1 * MM, 1.8 * MM, Dielectric(3.0)), InsulatedWire(0.8 * MM), 1.8),
    ],
)  # fmt: skip
def test_against_independent_bem(w1, w2, s_mm):
    w2 = w1 if w2 is None else w2
    s = s_mm * MM
    c = pair_capacitance(w1, w2, spacing=s).capacitance
    # BEM error is ~O(1/n); Richardson-extrapolate two resolutions
    bem = 2 * _bem_pair(w1, w2, s, 240) - _bem_pair(w1, w2, s, 120)
    assert bem / c == pytest.approx(1.0, abs=1e-3)


def test_between_bare_and_uniform_medium_and_far_field_limit():
    w = InsulatedWire(1 * MM, 1.5 * MM, Dielectric(3.5))
    for s in (1.5 * MM, 2 * MM, 5 * MM):
        c = pair_capacitance(w, spacing=s).capacitance
        bare = bare_pair_capacitance(0.5 * MM, 0.5 * MM, s)
        assert bare < c < 3.5 * bare
    # far apart: only the monopole matters -> effective-radius formula becomes exact
    s = 200 * MM
    a_eff = effective_radius(w)
    assert pair_capacitance(w, spacing=s).capacitance == pytest.approx(
        bare_pair_capacitance(a_eff, a_eff, s), rel=1e-4, abs=0
    )


def test_touching_sleeves_converge():
    w = InsulatedWire(1 * MM, 1.5 * MM, Dielectric(3.5))
    r = pair_capacitance(w, spacing=1.5 * MM, rtol=1e-6)
    assert r.converged
    assert np.isfinite(r.capacitance)


def test_loss_tangent_bounded_by_material():
    w = InsulatedWire(1 * MM, 1.5 * MM, Dielectric(3.5, 0.02))
    r = pair_capacitance(w, spacing=2 * MM)
    assert 0 < r.tan_delta < 0.02
    assert r.conductance(1e6) == pytest.approx(2 * np.pi * 1e6 * r.capacitance * r.tan_delta)
    lossless = pair_capacitance(InsulatedWire(1 * MM, 1.5 * MM, Dielectric(3.5)), spacing=2 * MM)
    assert r.capacitance == pytest.approx(lossless.capacitance, rel=1e-3, abs=0)


def test_potential_boundary_values():
    w1 = InsulatedWire(1 * MM, 1.6 * MM, Dielectric(3.0))
    w2 = InsulatedWire(0.6 * MM, 1.0 * MM, Dielectric(5.0))
    s = 2.0 * MM
    r = pair_capacitance(w1, w2, spacing=s)
    th = np.linspace(0, 2 * np.pi, 50)
    # conductor surfaces: 1 V difference, constant
    v1 = r.potential(-s / 2 + 0.5 * MM * 1.0001 * np.cos(th), 0.5 * MM * 1.0001 * np.sin(th))
    v2 = r.potential(s / 2 + 0.3 * MM * 1.0001 * np.cos(th), 0.3 * MM * 1.0001 * np.sin(th))
    assert np.ptp(v1.real) < 1e-3 and np.ptp(v2.real) < 1e-3
    assert (v1.mean() - v2.mean()).real == pytest.approx(1.0, abs=2e-3)
    # potential continuous across the sleeve surface of wire 1
    rin, rout = 0.8 * MM * (1 - 1e-6), 0.8 * MM * (1 + 1e-6)
    vin = r.potential(-s / 2 + rin * np.cos(th), rin * np.sin(th))
    vout = r.potential(-s / 2 + rout * np.cos(th), rout * np.sin(th))
    assert np.max(np.abs(vin - vout)) < 1e-4


def test_validation_and_presets():
    with pytest.raises(ValueError, match="overlap"):
        pair_capacitance(InsulatedWire(1 * MM, 1.5 * MM), spacing=1.4 * MM)
    with pytest.raises(ValueError):
        InsulatedWire(1 * MM, 0.9 * MM)
    with pytest.raises(ValueError):
        Dielectric(0.5)
    assert Material.CUSTOM.dielectric is None
    assert Material("PTFE").dielectric == Dielectric(2.1, 0.0002)
