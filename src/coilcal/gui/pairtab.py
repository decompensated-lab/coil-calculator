"""'Wire pair C' tab: capacitance per length of two parallel insulated wires in air."""

from __future__ import annotations

from collections.abc import Callable

from PySide6 import QtCore, QtGui, QtWidgets

from ..materials import Material
from .model import CoilParams
from .pair import (
    PairParams,
    PairResults,
    SpacingRef,
    WireParams,
    compute_pair,
    draw_pair,
    pair_summary_html,
)
from .widgets import EnumCombo, PlotTab, _add_rows, _dspin, _tip


class WireBox(QtWidgets.QGroupBox):
    """Conductor Ø, insulation Ø and dielectric for one wire."""

    changed = QtCore.Signal()

    def __init__(self, title: str, p: WireParams) -> None:
        super().__init__(title)
        self.form = QtWidgets.QFormLayout(self)
        self.cond = _dspin(p.conductor_d_mm, 0.001, 100, 0.05, decimals=4, suffix=" mm")
        self.ins = _dspin(p.insulation_d_mm, 0.001, 200, 0.05, decimals=4, suffix=" mm")
        self.material: EnumCombo[Material] = EnumCombo(Material, p.material)
        self.eps = _dspin(p.eps_r, 1.0, 1000, 0.1, decimals=3)
        self.tand = _dspin(p.tan_delta, 0.0, 1.0, 0.001, decimals=5)
        _add_rows(
            self.form,
            [
                ("conductor Ø", "pair_cond", self.cond),
                ("insulation outer Ø", "pair_ins", self.ins),
                ("material", "pair_material", self.material),
                ("εr", "pair_eps", self.eps),
                ("tan δ", "pair_tand", self.tand),
            ],
        )
        self.material.currentIndexChanged.connect(self._preset)
        self.eps.valueChanged.connect(self._manual)
        self.tand.valueChanged.connect(self._manual)
        self.cond.valueChanged.connect(self._clamp)
        for w in (self.cond, self.ins, self.eps, self.tand):
            w.valueChanged.connect(self.changed)
        self.material.currentIndexChanged.connect(self.changed)
        self._clamp()

    def _preset(self) -> None:
        d = self.material.value().dielectric
        if d is None:
            return
        for w, v in ((self.eps, d.eps_r), (self.tand, d.tan_delta)):
            w.blockSignals(True)
            w.setValue(v)
            w.blockSignals(False)
        if self.material.value() is Material.AIR:
            self.ins.setValue(self.cond.value())

    def _manual(self) -> None:
        d = self.material.value().dielectric
        if d is not None and (d.eps_r, d.tan_delta) != (self.eps.value(), self.tand.value()):
            self.material.blockSignals(True)
            self.material.set_value(Material.CUSTOM)
            self.material.blockSignals(False)

    def _clamp(self) -> None:
        """Insulation outer Ø can't be below the conductor Ø."""
        self.ins.setMinimum(self.cond.value())

    def set_conductor(self, d_mm: float) -> None:
        thickness = max(self.ins.value() - self.cond.value(), 0.0)
        self.cond.setValue(d_mm)
        self.ins.setValue(d_mm + thickness)

    def params(self) -> WireParams:
        return WireParams(
            conductor_d_mm=self.cond.value(),
            insulation_d_mm=self.ins.value(),
            material=self.material.value(),
            eps_r=self.eps.value(),
            tan_delta=self.tand.value(),
        )


class WirePairTab(QtWidgets.QWidget):
    """Self-contained tab; independent of the coil inputs except for 'From coil A'."""

    def __init__(
        self,
        coil_a: Callable[[], CoilParams] | None = None,
        params: PairParams | None = None,
    ) -> None:
        super().__init__()
        p = params or PairParams()
        self._coil_a = coil_a
        self.result: PairResults | None = None

        self.box1 = WireBox("Wire 1", p.w1)
        self.box2 = WireBox("Wire 2 differs from wire 1", p.w2)
        self.box2.setCheckable(True)
        self.box2.setChecked(not p.same)
        _tip(self.box2, "pair_same")

        box_s = QtWidgets.QGroupBox("Spacing")
        self.spacing_ref: EnumCombo[SpacingRef] = EnumCombo(SpacingRef, p.spacing_ref)
        self.spacing = _dspin(p.spacing_mm, 0.0, 1000, 0.05, decimals=4, suffix=" mm")
        form = QtWidgets.QFormLayout(box_s)
        _add_rows(
            form,
            [
                ("reference", "pair_ref", self.spacing_ref),
                ("spacing", "pair_spacing", self.spacing),
            ],
        )
        self.from_coil = _tip(QtWidgets.QPushButton("From coil A (wire Ø, pitch)"), "pair_from_a")
        self.from_coil.clicked.connect(self.load_coil_a)
        self.from_coil.setEnabled(coil_a is not None)
        form.addRow(self.from_coil)

        self.status = QtWidgets.QLabel("")
        self.status.setWordWrap(True)
        left = QtWidgets.QWidget()
        ll = QtWidgets.QVBoxLayout(left)
        for w in (self.box1, self.box2, box_s, self.status):
            ll.addWidget(w)
        ll.addStretch(1)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(left)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(300)

        self.plot = PlotTab()
        self.summary = QtWidgets.QTextBrowser()
        right = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        right.addWidget(self.plot)
        right.addWidget(self.summary)
        right.setSizes([520, 260])
        split = QtWidgets.QSplitter()
        split.addWidget(scroll)
        split.addWidget(right)
        split.setSizes([310, 900])
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(split)

        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self.recompute)
        self.box1.changed.connect(self._timer.start)
        self.box2.changed.connect(self._timer.start)
        self.box2.toggled.connect(self._timer.start)
        self.spacing_ref.currentIndexChanged.connect(self._ref_changed)
        self.spacing.valueChanged.connect(self._timer.start)
        self._last_ref = p.spacing_ref
        self.recompute()

    def params(self) -> PairParams:
        return PairParams(
            w1=self.box1.params(),
            w2=self.box2.params(),
            same=not self.box2.isChecked(),
            spacing_ref=self.spacing_ref.value(),
            spacing_mm=self.spacing.value(),
        )

    def _ref_changed(self) -> None:
        """Convert the spacing value so the geometry doesn't jump when the reference changes."""
        new = self.spacing_ref.value()
        if new is not self._last_ref:
            p = self.params()
            w1, w2 = p.wires()
            outer_mm = (w1.b + w2.b) * 1e3
            v = self.spacing.value()
            v = v + outer_mm if new is SpacingRef.CENTRE else v - outer_mm
            self.spacing.blockSignals(True)
            self.spacing.setValue(max(v, 0.0))
            self.spacing.blockSignals(False)
            self._last_ref = new
        self._timer.start()

    def load_coil_a(self) -> None:
        if self._coil_a is None:
            return
        a = self._coil_a()
        self.box1.set_conductor(a.wire_d_mm)
        self.box2.set_conductor(a.wire_d_mm)
        self.spacing_ref.set_value(SpacingRef.CENTRE)  # converts, then we overwrite
        self.spacing.setValue(a.pitch_mm)
        self.recompute()

    def recompute(self) -> None:
        try:
            r = compute_pair(self.params())
        except ValueError as e:
            self.status.setText(f"<span style='color:#c0392b'>ValueError: {e}</span>")
            return
        self.status.setText("")
        self.result = r
        dark = self.palette().color(QtGui.QPalette.ColorRole.Base).lightness() < 128
        self.summary.setHtml(pair_summary_html(r, dark=dark))
        draw_pair(self.plot.fig, r)
        self.plot.canvas.draw_idle()
