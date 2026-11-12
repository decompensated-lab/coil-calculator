import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from coilcal.gui import CoilParams, MainWindow, Params, compute, summary_html
from coilcal.gui.model import Fill, GapRef, VnaSetup, check_overlap
from coilcal.materials import Material


@pytest.mark.parametrize("setup", list(VnaSetup))
def test_compute_all_vna_setups(setup):
    r = compute(Params(a=CoilParams(turns=8), b=CoilParams(turns=4), offset_mm=5, vna_setup=setup))
    assert r.s.shape[1:] == (2, 2)
    assert np.all(np.abs(r.s) <= 1 + 1e-9)  # passive
    assert np.isfinite(r.field_b).all()
    html = summary_html(r)
    assert "Coil A" in html and "<img" in html


def test_nested_coils_centre_reference():
    p = Params(
        a=CoilParams(turns=10),
        b=CoilParams(turns=4, former_d_mm=100),
        gap_ref=GapRef.CENTRE,
        gap_mm=0.0,
    )
    _a, b = p.coils()
    assert b.position[2] == 0.0
    r = compute(p)
    assert r.k_static > 0.1  # nested coaxial coils couple strongly


def test_overlap_rejected():
    p = Params(gap_ref="centre-to-centre", gap_mm=0.0)  # same radius, same place
    with pytest.raises(ValueError, match="intersect"):
        p.coils()
    a, b = Params(gap_ref="centre-to-centre", gap_mm=100.0).coils()
    check_overlap(a, b)


def test_main_window_renders_all_tabs():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow(Params(a=CoilParams(turns=6), b=CoilParams(turns=3)))
    w.recompute(blocking=True)
    app.processEvents()
    assert w._result is not None
    w.draw_all()
    for fill in Fill:
        w.fill.set_value(fill)
        w.draw_all()
    assert w.box_a.wire.toolTip()
    w.close()


def test_params_validate_strings_and_reject_typos():
    p = Params(gap_ref="centre-to-centre", coupling="magnetic", vna_setup=VnaSetup.A_SHUNT.value)
    assert p.gap_ref is GapRef.CENTRE and p.vna_setup is VnaSetup.A_SHUNT
    with pytest.raises(ValueError, match="not a valid"):
        Params(coupling="magnetc")
    assert CoilParams(ground="floating").ground.terminal is None


def test_bz_profiles_match_static_at_low_frequency():
    from coilcal import B_axis_rings

    p = Params(
        a=CoilParams(turns=10),
        vna_setup=VnaSetup.A_SERIES,
        f_min_mhz=0.001,
        f_max_mhz=1.0,
        n_freq=20,
        f_view_mhz=0.001,
        x_line_z_mm=1.0,  # 10 turns at 2 mm pitch: a wire centre sits at z = +1 mm
    )
    r = compute(p)
    i_coil = r.drive_turn_i[r.i_view].mean()
    expected = B_axis_rings(r.vna_coils[0], r.line_z, current=1.0) * i_coil
    assert np.allclose(r.bz_z, expected, rtol=1e-6, atol=1e-15)
    assert np.allclose(r.bz_z, r.bz_z_uniform, rtol=1e-6)
    # x-cut through the winding plane: wire interiors are masked, centre value matches the axis
    assert np.isnan(r.bz_x).any()
    centre = np.argmin(np.abs(r.line_x))
    on_axis = np.interp(1e-3, r.line_z, r.bz_z.real)
    assert r.bz_x[centre].real == pytest.approx(on_axis, rel=1e-3, abs=0)


def test_current_drive_is_the_power_drive_rescaled():
    from coilcal.gui.model import Drive

    base = {"n_freq": 20, "f_view_mhz": 3.0}
    for setup in (VnaSetup.PAIR, VnaSetup.A_SHUNT):
        r = compute(Params(vna_setup=setup, drive=Drive.CURRENT, i_drive_a=0.25, **base))
        assert abs(r.drive_port_i[r.i_view, 0]) == pytest.approx(0.25, rel=1e-12, abs=0)
        assert "0.25 A" in r.drive_label
        # the same source given as its power: every drive quantity agrees
        ref = compute(Params(vna_setup=setup, p_dbm=r.p_dbm, **base))
        assert r.v_plus == pytest.approx(ref.v_plus, rel=1e-12, abs=0)
        for key in ("drive_turn_i", "drive_port_i", "drive_node_v", "field_b", "bz_z"):
            got, want = getattr(r, key), getattr(ref, key)
            assert np.abs(got - want).max() <= 1e-10 * np.abs(want).max(), key
        assert np.array_equal(r.s, ref.s)  # S-parameters do not depend on the level
    with pytest.raises(ValueError, match="must be positive"):
        compute(Params(drive="port 1 current", i_drive_a=0.0, **base))


def test_wire_pair_tab():
    from coilcal.gui.pair import PairParams, SpacingRef, WireParams, compute_pair, pair_summary_html

    r = compute_pair(PairParams(spacing_ref=SpacingRef.CENTRE, spacing_mm=2.0))
    assert r.res.spacing == pytest.approx(2e-3)
    assert r.c_bare < r.res.capacitance < r.c_uniform
    assert np.all(np.diff(r.sweep_exact) < 0)  # C' falls with spacing
    assert "pF/m" in pair_summary_html(r)
    # different wires: no single εr for the 'uniform medium' comparison
    p = PairParams(same=False, w2=WireParams(0.5, 0.5, Material.AIR, 1.0, 0.0))
    assert compute_pair(p).c_uniform is None

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow(Params(a=CoilParams(turns=4, wire_d_mm=0.8, pitch_mm=1.7), b_enabled=False))
    tab = w.pair_tab
    assert tab.result is not None
    tab.box1.material.set_value(Material.PVC)
    assert tab.box1.eps.value() == pytest.approx(3.5)
    tab.box1.eps.setValue(4.2)  # manual edit -> custom
    assert tab.box1.material.value() is Material.CUSTOM
    # changing the reference keeps the geometry
    s0 = tab.params().centre_spacing()
    tab.spacing_ref.set_value(SpacingRef.CENTRE)
    assert tab.params().centre_spacing() == pytest.approx(s0)
    tab.load_coil_a()
    p = tab.params()
    assert p.w1.conductor_d_mm == pytest.approx(0.8)
    assert p.centre_spacing() == pytest.approx(1.7e-3)
    assert tab.result is not None and tab.result.res.spacing == pytest.approx(1.7e-3)
    tab.spacing.setValue(0.1)  # overlapping sleeves -> error shown, no crash
    tab.recompute()
    assert "overlap" in tab.status.text()
    w.tabs.setCurrentWidget(tab)
    app.processEvents()
    w.close()


def test_coil_dielectrics_in_gui_model():
    from coilcal.materials import Dielectric

    bare = CoilParams(
        turns=6, insulation_d_mm=1.0, former_material=Material.AIR, former=Dielectric(1.0)
    )
    c = bare.build()
    assert c.former is None and not c.has_dielectrics
    r = compute(Params(a=CoilParams(turns=6), b=CoilParams(turns=3)))
    assert r.coils[0].former is not None and r.coils[0].has_dielectrics
    assert r.srf_net[0] < r.srf_vacuum[0]  # dielectrics lower the SRF
    assert "former εr 2.6" in summary_html(r)
    # B wound inside A's former wall is rejected
    nested = Params(b=CoilParams(turns=3, former_d_mm=144.0), gap_ref="centre-to-centre", gap_mm=0)
    with pytest.raises(ValueError, match="former wall of A"):
        nested.coils()


def test_coil_box_keeps_insulation_thickness():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow(Params(a=CoilParams(turns=4), b_enabled=False))
    box = w.box_a
    box.wire.setValue(0.5)
    assert box.ins_d.value() == pytest.approx(0.56)
    box.ins.material.set_value(Material.PTFE)
    assert box.params().insulation.eps_r == pytest.approx(2.1)
    assert box.params().insulation_material is Material.PTFE
    app.processEvents()
    w.close()


def test_summary_never_shows_negative_q_or_inductance_near_resonance():
    from coilcal.materials import Dielectric

    a = CoilParams(
        wire_d_mm=0.51, insulation_d_mm=1.1, pitch_mm=1.1, former_d_mm=160, turns=22,
        insulation_material=Material.PVC, insulation=Dielectric(3.5, 0.05),
        former_material=Material.PVC_RIGID, former=Dielectric(3.0, 0.012),
    )  # fmt: skip
    r = compute(Params(a=a, f_view_mhz=5.0))
    assert r.srf_here[0] < r.srf_net[0]  # coil B (open) pulls A's resonance down
    assert r.f_view > r.srf_here[0]  # the view frequency is just above it
    html = summary_html(r)
    assert "capacitive: near/above a resonance" in html and "not a Q here" in html
    assert html.count("not a Q here") == 2  # B sees A's resonance through the coupling
    assert 50 < r.q_srf[0] < 300
    assert any("first resonance" in w for w in r.warnings)
