"""Insulation and former dielectrics in the turn capacitance (coilcal.capacitance)."""

import numpy as np
import pytest
from _bem2d import Polygon2D, Wire2D, capacitance_2d

import coilcal as cc
from coilcal.capacitance import auto_n_sub, capacitance_matrix, isolated_capacitance
from coilcal.circuit import CoilNetwork
from coilcal.geometry import Former
from coilcal.materials import Dielectric
from coilcal.wirepair import InsulatedWire, pair_capacitance

MM = 1e-3
BIG = 20.0  # former Ø [m]: turns of a 10 m radius coil are locally a 2-D wire pair


def _pair_c_per_length(coil: cc.SolenoidCoil, **kw) -> float:
    """Differential capacitance of a 2-turn coil per unit turn length [F/m]."""
    p = np.linalg.inv(np.real(capacitance_matrix([coil], **kw)))
    return float(1 / (p[0, 0] + p[1, 1] - 2 * p[0, 1]) / (2 * np.pi * coil.mean_radius))


@pytest.mark.parametrize(
    ("ins", "eps", "pitch"),
    [(1.5, 3.5, 2.0), (1.5, 3.5, 1.5), (1.06, 3.6, 1.06), (2.0, 2.1, 2.0), (1.5, 1.0, 1.5)],
)
def test_insulated_turns_match_exact_2d_pair(ins, eps, pitch):
    coil = cc.SolenoidCoil(
        1 * MM, pitch * MM, BIG, 2, insulation_d=ins * MM, insulation=Dielectric(eps)
    )
    ref = pair_capacitance(
        InsulatedWire(1 * MM, ins * MM, Dielectric(eps)), spacing=pitch * MM
    ).capacitance
    assert _pair_c_per_length(coil) == pytest.approx(ref, rel=2e-3, abs=0)


def test_auto_n_sub():
    assert auto_n_sub([cc.SolenoidCoil(1e-3, 2e-3, 0.15, 3)]) == 16
    tight = cc.SolenoidCoil(1e-3, 1.06e-3, 0.15, 3, insulation_d=1.06e-3)
    assert auto_n_sub([tight]) == 48


def _former_case(ins, eps_i, wall, eps_f, overhang, pitch=2.0):
    coil = cc.SolenoidCoil(
        1 * MM,
        pitch * MM,
        BIG,
        2,
        insulation_d=ins * MM,
        insulation=Dielectric(eps_i),
        former=Former(wall * MM, Dielectric(eps_f), overhang * MM),
    )
    b = ins / 2 * MM
    x1 = (pitch + overhang) * MM
    slab = Polygon2D(
        np.array([[-x1, -wall * MM], [x1, -wall * MM], [x1, 0], [-x1, 0]]),
        eps_f,
        grade_to=[(-pitch / 2 * MM, 0), (pitch / 2 * MM, 0)],
    )
    wires = [
        Wire2D(-pitch / 2 * MM, b, 0.5 * MM, b, eps_i, 0.5),
        Wire2D(pitch / 2 * MM, b, 0.5 * MM, b, eps_i, -0.5),
    ]
    n = 512
    ref = capacitance_2d(wires, [slab], n, h_min=2 * np.pi * b / n, h_max=0.025 * MM)
    return _pair_c_per_length(coil), ref


@pytest.mark.parametrize(
    ("case", "rel"),
    [
        ((1.4, 1.0, 2.0, 4.0, 1.0), 2e-3),  # wires lifted off the former by a vacuum sleeve
        ((1.06, 3.6, 3.0, 2.6, 2.0), 5e-3),  # enamelled wire touching the former
    ],
)
def test_former_matches_2d_bem(case, rel):
    c3, c2 = _former_case(*case)
    assert c3 == pytest.approx(c2, rel=rel, abs=0)


def test_neutral_dielectrics_change_nothing():
    plain = cc.SolenoidCoil(1e-3, 2e-3, 0.15, 6)
    same = cc.SolenoidCoil(
        1e-3, 2e-3, 0.15, 6, former=Former(3e-3, Dielectric(1.0), 5e-3), insulation=Dielectric(3)
    )  # vacuum former; insulation without insulation_d has no thickness
    assert not same.has_dielectrics
    assert np.allclose(capacitance_matrix([same]), capacitance_matrix([plain]), rtol=1e-12)


def test_former_raises_capacitance_and_lowers_srf():
    def coil(eps):
        return cc.SolenoidCoil(
            1e-3, 2e-3, 0.15, 12, insulation_d=1.06e-3, insulation=Dielectric(3.6),
            former=Former(3e-3, Dielectric(eps), 5e-3),
        )  # fmt: skip

    cs = [isolated_capacitance(coil(e)) for e in (1.0, 2.6, 4.4)]
    assert cs[0] < cs[1] < cs[2]
    srfs = [CoilNetwork([coil(e)], ground="end").srf() for e in (1.0, 4.4)]
    assert srfs[1] < srfs[0]
    # the dielectric is only near the winding: much less than εr times the capacitance
    assert cs[2] < 1.5 * cs[0]


def test_lossy_dielectric_gives_complex_symmetric_c_and_loss():
    coil = cc.SolenoidCoil(
        1e-3, 2e-3, 0.15, 8, insulation_d=1.06e-3, insulation=Dielectric(3.6, 0.02),
        former=Former(3e-3, Dielectric(3.0, 0.02), 5e-3),
    )  # fmt: skip
    c = capacitance_matrix([coil])
    assert np.iscomplexobj(c)
    assert np.allclose(c, c.T)
    assert np.all(np.diag(c).imag < 0)  # C' − jC'': conductance ωC'' > 0
    lossless = cc.SolenoidCoil(
        1e-3, 2e-3, 0.15, 8, insulation_d=1.06e-3, insulation=Dielectric(3.6),
        former=Former(3e-3, Dielectric(3.0), 5e-3),
    )  # fmt: skip
    f = [3e6]
    r_lossy = CoilNetwork([coil], ground="end").solve(f).z_in(0)[0].real
    r_lossless = CoilNetwork([lossless], ground="end").solve(f).z_in(0)[0].real
    assert r_lossy > r_lossless


def test_shared_former_merges_and_bad_geometry_is_rejected():
    f = Former(3e-3, Dielectric(2.6), 0.5e-3)
    a = cc.SolenoidCoil(1e-3, 2e-3, 0.15, 4, former=f)
    b = cc.SolenoidCoil(1e-3, 2e-3, 0.15, 3, former=f, position=[0, 0, 9e-3])  # tubes touch
    c = capacitance_matrix([a, b])
    assert np.all(np.isfinite(c)) and np.allclose(c, c.T)
    # a coil wound inside another coil's former wall
    inner = cc.SolenoidCoil(1e-3, 2e-3, 0.144, 3)  # wire centre at r = 72.5 mm, wall 72–75 mm
    with pytest.raises(ValueError, match="intersects a coil former"):
        capacitance_matrix([a, inner])
    with pytest.raises(ValueError, match="former wall"):
        cc.SolenoidCoil(1e-3, 2e-3, 0.15, 3, former=Former(0.08))
