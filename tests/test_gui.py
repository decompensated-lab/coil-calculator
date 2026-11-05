import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from coilcal.gui import CoilParams, MainWindow, Params, compute, summary_text


def test_compute_and_summary():
    r = compute(Params(a=CoilParams(turns=8), b=CoilParams(turns=4), tilt_deg=10, offset_mm=5))
    assert r.res.z.shape[1:] == (2, 2)
    assert np.isfinite(r.srf_net[0])
    txt = summary_text(r)
    assert "SRF (network)" in txt and "Z21" in txt


def test_main_window_renders():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow(Params(a=CoilParams(turns=6), b_enabled=False))
    w.recompute(blocking=True)
    app.processEvents()
    assert w._result is not None
    assert "coil A" in w.summary.toPlainText()
    for fill in ("|V|", "none", "|I|"):
        w.fill.setCurrentText(fill)
    w.close()
