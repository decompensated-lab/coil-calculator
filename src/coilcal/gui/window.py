"""Qt main window."""

from __future__ import annotations

import sys
from collections.abc import Callable

from matplotlib.figure import Figure
from PySide6 import QtCore, QtGui, QtWidgets

from ..types import Coupling, Grounding
from . import plots
from .help import GUIDE_HTML, TAB_TIPS
from .model import CoilParams, Fill, GapRef, Params, Results, VnaSetup, compute
from .pairtab import WirePairTab
from .richtext import summary_html
from .widgets import (
    DielectricEdit,
    EnumCombo,
    Field,
    PlotTab,
    _add_rows,
    _changed_signal,
    _dspin,
    _ispin,
    _label,
)

DrawFn = Callable[[Figure, Results], None]
PAIR_TAB = "Wire pair C"


class CoilBox(QtWidgets.QGroupBox):
    changed = QtCore.Signal()

    def __init__(self, title: str, p: CoilParams) -> None:
        super().__init__(title)
        self.form = QtWidgets.QFormLayout(self)
        self.wire = _dspin(p.wire_d_mm, 0.01, 20, 0.05, suffix=" mm")
        self.pitch = _dspin(p.pitch_mm, 0.01, 50, 0.1, suffix=" mm")
        self.former = _dspin(p.former_d_mm, 1, 2000, 1, decimals=2, suffix=" mm")
        self.turns = _ispin(p.turns, 1, 500)
        self.ground: EnumCombo[Grounding] = EnumCombo(
            [Grounding.END, Grounding.START, Grounding.FLOATING], p.ground, lambda g: g.label
        )
        self.ins_d = _dspin(p.insulation_d_mm, 0.01, 30, 0.01, decimals=3, suffix=" mm")
        self.ins = DielectricEdit(
            p.insulation_material, p.insulation, ("ins_mat", "ins_eps", "ins_tand")
        )
        self.wall = _dspin(p.former_wall_mm, 0.01, 1000, 0.5, decimals=2, suffix=" mm")
        self.overhang = _dspin(p.former_overhang_mm, 0, 2000, 1, decimals=1, suffix=" mm")
        self.fmr = DielectricEdit(
            p.former_material, p.former, ("former_mat", "former_eps", "former_tand")
        )
        rows: list[tuple[str, str, Field]] = [
            ("wire Ø", "wire", self.wire),
            ("insulated Ø", "ins_d", self.ins_d),
            ("pitch", "pitch", self.pitch),
            ("former Ø", "former", self.former),
            ("turns", "turns", self.turns),
            ("terminals", "ground", self.ground),
        ]
        _add_rows(self.form, rows)
        self.form.addRow(_label("insulation", "ins_mat"), self.ins)
        _add_rows(
            self.form,
            [
                ("former wall", "former_wall", self.wall),
                ("overhang", "former_overhang", self.overhang),
            ],
        )
        self.form.addRow(_label("former", "former_mat"), self.fmr)
        self._wire_prev = p.wire_d_mm
        self.wire.valueChanged.connect(self._keep_insulation)
        for _, _, w in rows:
            _changed_signal(w).connect(self.changed)
        for w2 in (self.wall, self.overhang):
            w2.valueChanged.connect(self.changed)
        self.ins.changed.connect(self.changed)
        self.fmr.changed.connect(self.changed)
        self.ins_d.setMinimum(p.wire_d_mm)

    def _keep_insulation(self, value: float) -> None:
        """Changing the wire Ø keeps the insulation thickness."""
        thickness = max(self.ins_d.value() - self._wire_prev, 0.0)
        self._wire_prev = value
        self.ins_d.blockSignals(True)
        self.ins_d.setMinimum(value)
        self.ins_d.setValue(value + thickness)
        self.ins_d.blockSignals(False)

    def params(self) -> CoilParams:
        return CoilParams(
            wire_d_mm=self.wire.value(),
            pitch_mm=self.pitch.value(),
            former_d_mm=self.former.value(),
            turns=self.turns.value(),
            ground=self.ground.value(),
            insulation_d_mm=self.ins_d.value(),
            insulation_material=self.ins.material.value(),
            insulation=self.ins.value(),
            former_wall_mm=self.wall.value(),
            former_overhang_mm=self.overhang.value(),
            former_material=self.fmr.material.value(),
            former=self.fmr.value(),
        )


class _Signals(QtCore.QObject):
    done = QtCore.Signal(int, object)
    failed = QtCore.Signal(int, str)


class _Job(QtCore.QRunnable):
    def __init__(self, gen: int, params: Params, signals: _Signals) -> None:
        super().__init__()
        self.gen, self.params, self.signals = gen, params, signals

    def run(self) -> None:
        try:
            result = compute(self.params)
        except Exception as e:  # noqa: BLE001 - surface any model error in the UI
            self._emit(self.signals.failed, f"{type(e).__name__}: {e}")
        else:
            self._emit(self.signals.done, result)

    def _emit(self, signal: QtCore.SignalInstance, payload: object) -> None:
        try:
            signal.emit(self.gen, payload)
        except RuntimeError:  # window closed while computing
            pass


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, params: Params | None = None) -> None:
        super().__init__()
        self.setWindowTitle("coilcal — turn-level coil model")
        p = params or Params()
        self._gen = 0
        self._result: Results | None = None
        self._signals = _Signals()
        self._signals.done.connect(self._on_done)
        self._signals.failed.connect(self._on_failed)
        self._pool = QtCore.QThreadPool.globalInstance()

        # ---- left: parameters ------------------------------------------------------
        self.box_a = CoilBox("Coil A (driven)", p.a)
        self.box_b = CoilBox("Coil B (pickup)", p.b)
        self.box_b.setCheckable(True)
        self.box_b.setChecked(p.b_enabled)
        self.box_b.setToolTip("Untick to model coil A alone.")
        self.gap_ref: EnumCombo[GapRef] = EnumCombo(GapRef, p.gap_ref)
        self.gap = _dspin(p.gap_mm, -2000, 2000, 1, decimals=2, suffix=" mm")
        self.offset = _dspin(p.offset_mm, -2000, 2000, 1, decimals=2, suffix=" mm")
        _add_rows(
            self.box_b.form,
            [
                ("gap reference", "gap_ref", self.gap_ref),
                ("axial gap", "gap", self.gap),
                ("lateral offset", "offset", self.offset),
            ],
        )

        box_v = QtWidgets.QGroupBox("VNA")
        self.vna_setup: EnumCombo[VnaSetup] = EnumCombo(VnaSetup, p.vna_setup)
        self.z0 = _dspin(p.z0, 1, 1000, 1, decimals=1, suffix=" Ω")
        self.p_dbm = _dspin(p.p_dbm, -100, 40, 1, decimals=1, suffix=" dBm")
        self.fill: EnumCombo[Fill] = EnumCombo(Fill, Fill.CURRENT)
        _add_rows(
            QtWidgets.QFormLayout(box_v),
            [
                ("setup", "vna_setup", self.vna_setup),
                ("Z0", "z0", self.z0),
                ("source power", "p_dbm", self.p_dbm),
                ("cross-section fill", "fill", self.fill),
            ],
        )

        box_f = QtWidgets.QGroupBox("Analysis")
        self.f_min = _dspin(p.f_min_mhz, 1e-4, 1e4, 0.1, decimals=4, suffix=" MHz")
        self.f_max = _dspin(p.f_max_mhz, 1e-3, 1e4, 1, decimals=3, suffix=" MHz")
        self.n_freq = _ispin(p.n_freq, 10, 5000)
        self.f_view = _dspin(p.f_view_mhz, 1e-4, 1e4, 0.5, decimals=4, suffix=" MHz")
        self.z_load = _dspin(p.z_load, 1e-3, 1e9, 10, decimals=3, suffix=" Ω")
        self.r_factor = _dspin(p.r_factor, 0.1, 20, 0.1, decimals=2)
        self.coupling: EnumCombo[Coupling] = EnumCombo(Coupling, p.coupling)
        self.x_line_z = _dspin(p.x_line_z_mm, -2000, 2000, 1, decimals=2, suffix=" mm")
        _add_rows(
            QtWidgets.QFormLayout(box_f),
            [
                ("f min", "f_min", self.f_min),
                ("f max", "f_max", self.f_max),
                ("points", "n_freq", self.n_freq),
                ("view f", "f_view", self.f_view),
                ("B load", "z_load", self.z_load),
                ("R factor", "r_factor", self.r_factor),
                ("inter-coil coupling", "coupling", self.coupling),
                ("Bz(x) at z", "x_line_z", self.x_line_z),
            ],
        )

        self.status = QtWidgets.QLabel("")
        self.status.setWordWrap(True)
        left = QtWidgets.QWidget()
        ll = QtWidgets.QVBoxLayout(left)
        for w in (self.box_a, self.box_b, box_v, box_f, self.status):
            ll.addWidget(w)
        ll.addStretch(1)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(left)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(330)
        self._inputs = scroll

        # ---- right: tabs + summary -------------------------------------------------
        self.tabs = QtWidgets.QTabWidget()
        self.plot_tabs: dict[str, tuple[PlotTab, DrawFn]] = {}
        tab_defs: list[tuple[str, DrawFn]] = [
            ("Cross-section", lambda fig, r: plots.draw_cross_section(fig, r, self.fill.value())),
            ("Side view", plots.draw_side_view),
            ("Bz profiles", plots.draw_bz_profiles),
            ("Impedance", plots.draw_impedance),
            ("Transfer A→B", plots.draw_transfer),
            ("VNA", plots.draw_vna),
            ("Turn currents", plots.draw_distribution),
        ]
        for name, fn in tab_defs:
            tab = PlotTab()
            idx = self.tabs.addTab(tab, name)
            self.tabs.setTabToolTip(idx, TAB_TIPS[name])
            self.plot_tabs[name] = (tab, fn)
        self.pair_tab = WirePairTab(coil_a=self.box_a.params)
        idx = self.tabs.addTab(self.pair_tab, PAIR_TAB)
        self.tabs.setTabToolTip(idx, TAB_TIPS[PAIR_TAB])
        self._dirty: set[str] = set()
        self.tabs.currentChanged.connect(self._draw_current)

        self.summary = QtWidgets.QTextBrowser()
        self.summary.setToolTip("Results at the view frequency. Hover the controls for help.")
        right = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        right.addWidget(self.tabs)
        right.addWidget(self.summary)
        right.setSizes([620, 300])

        split = QtWidgets.QSplitter()
        split.addWidget(scroll)
        split.addWidget(right)
        split.setSizes([340, 1100])
        self.setCentralWidget(split)
        self.setStatusBar(QtWidgets.QStatusBar())
        self.resize(1500, 950)
        self._build_menu()

        # ---- wiring ----------------------------------------------------------------
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.recompute)
        self.box_a.changed.connect(self._timer.start)
        self.box_b.changed.connect(self._timer.start)
        self.box_b.toggled.connect(self._timer.start)
        inputs: list[Field] = [
            self.gap_ref, self.gap, self.offset, self.f_min, self.f_max, self.n_freq,
            self.f_view, self.z_load, self.r_factor, self.coupling, self.vna_setup, self.z0,
            self.p_dbm, self.x_line_z,
        ]  # fmt: skip
        for inp in inputs:
            _changed_signal(inp).connect(self._timer.start)
        self.fill.currentIndexChanged.connect(lambda _: self._mark_dirty({"Cross-section"}))
        self.recompute()

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("&Help")
        guide = QtGui.QAction("Model && usage guide", self)
        guide.setShortcut(QtGui.QKeySequence("F1"))
        guide.triggered.connect(self.show_guide)
        menu.addAction(guide)
        whats = QtWidgets.QWhatsThis.createAction(self)
        whats.setText("What's this? (click a control)")
        menu.addAction(whats)

    def show_guide(self) -> None:
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("coilcal guide")
        lay = QtWidgets.QVBoxLayout(dlg)
        tb = QtWidgets.QTextBrowser()
        tb.setHtml(GUIDE_HTML)
        lay.addWidget(tb)
        dlg.resize(700, 600)
        dlg.show()

    # ------------------------------------------------------------------------------------
    def params(self) -> Params:
        return Params(
            a=self.box_a.params(),
            b=self.box_b.params(),
            b_enabled=self.box_b.isChecked(),
            gap_ref=self.gap_ref.value(),
            gap_mm=self.gap.value(),
            offset_mm=self.offset.value(),
            f_min_mhz=self.f_min.value(),
            f_max_mhz=self.f_max.value(),
            n_freq=self.n_freq.value(),
            f_view_mhz=self.f_view.value(),
            z_load=self.z_load.value(),
            r_factor=self.r_factor.value(),
            coupling=self.coupling.value(),
            vna_setup=self.vna_setup.value(),
            z0=self.z0.value(),
            p_dbm=self.p_dbm.value(),
            x_line_z_mm=self.x_line_z.value(),
        )

    def recompute(self, blocking: bool = False) -> None:
        self._gen += 1
        self.status.setText("computing…")
        try:
            params = self.params()
        except ValueError as e:  # invalid combination of inputs
            self._on_failed(self._gen, f"ValueError: {e}")
            return
        job = _Job(self._gen, params, self._signals)
        if blocking:
            job.run()
        else:
            self._pool.start(job)

    @QtCore.Slot(int, object)
    def _on_done(self, gen: int, r: Results) -> None:
        if gen != self._gen:
            return  # stale result
        self._result = r
        self.status.setText("")
        dark = self.palette().color(QtGui.QPalette.ColorRole.Base).lightness() < 128
        self.summary.setHtml(summary_html(r, dark=dark))
        self._mark_dirty(set(self.plot_tabs))

    @QtCore.Slot(int, str)
    def _on_failed(self, gen: int, msg: str) -> None:
        if gen == self._gen:
            self.status.setText(f"<span style='color:#c0392b'>{msg}</span>")

    def _mark_dirty(self, names: set[str]) -> None:
        self._dirty |= names
        self._draw_current()

    def _draw_current(self, *_: object) -> None:
        """Redraw only the visible tab; others are redrawn when shown."""
        name = self.tabs.tabText(self.tabs.currentIndex())
        # the wire-pair tab is stand-alone: it brings its own inputs and summary
        self.summary.setVisible(name != PAIR_TAB)
        self._inputs.setVisible(name != PAIR_TAB)
        if self._result is None:
            return
        if name in self._dirty:
            tab, fn = self.plot_tabs[name]
            fn(tab.fig, self._result)
            tab.canvas.draw_idle()
            self._dirty.discard(name)

    def draw_all(self) -> None:
        """Redraw every stale tab immediately (used by tests / screenshots)."""
        if self._result is None:
            return
        for name in list(self._dirty):
            tab, fn = self.plot_tabs[name]
            fn(tab.fig, self._result)
            tab.canvas.draw()
        self._dirty.clear()


def main() -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
