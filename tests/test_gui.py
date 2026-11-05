import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from coilcal.gui import CoilParams, MainWindow, Params, compute, summary_html
from coilcal.gui.model import VNA_SETUPS, check_overlap


@pytest.mark.parametrize("setup", list(VNA_SETUPS))
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
        gap_ref="centre-to-centre",
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
    for fill in ("|V|", "none", "|I|"):
        w.fill.setCurrentText(fill)
    assert w.box_a.wire.toolTip()
    w.close()
