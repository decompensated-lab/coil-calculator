"""Qt main window."""

from __future__ import annotations

import sys

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6 import QtCore, QtGui, QtWidgets

from . import plots
from .help import GUIDE_HTML, TAB_TIPS, TIPS
from .model import GAP_REFS, GROUND_CHOICES, VNA_SETUPS, CoilParams, Params, Results, compute
from .richtext import summary_html


class PlotTab(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.fig = Figure(layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.fig)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(NavigationToolbar2QT(self.canvas, self))
        lay.addWidget(self.canvas)


def _tip(widget: QtWidgets.QWidget, key: str) -> QtWidgets.QWidget:
    widget.setToolTip(TIPS[key])
    widget.setWhatsThis(TIPS[key])
    widget.setStatusTip(TIPS[key].split("\n")[0])
    return widget


def _dspin(value, lo, hi, step, decimals=3, suffix=""):
    w = QtWidgets.QDoubleSpinBox()
    w.setRange(lo, hi)
    w.setDecimals(decimals)
    w.setSingleStep(step)
    w.setValue(value)
    w.setSuffix(suffix)
    w.setKeyboardTracking(False)
    return w


def _ispin(value, lo, hi):
    w = QtWidgets.QSpinBox()
    w.setRange(lo, hi)
    w.setValue(value)
    w.setKeyboardTracking(False)
    return w


def _combo(items, current):
    w = QtWidgets.QComboBox()
    w.addItems(list(items))
    w.setCurrentText(current)
    return w


def _label(text: str, key: str) -> QtWidgets.QLabel:
    """Form label with a small ⓘ hint; hovering it shows the same tooltip as the field."""
    lab = QtWidgets.QLabel(f"{text} <span style='color:#8a8980'>ⓘ</span>")
    return _tip(lab, key)


def _changed_signal(w):
    if isinstance(w, QtWidgets.QComboBox):
        return w.currentTextChanged
    return w.valueChanged


class CoilBox(QtWidgets.QGroupBox):
    changed = QtCore.Signal()

    def __init__(self, title: str, p: CoilParams):
        super().__init__(title)
        self.form = QtWidgets.QFormLayout(self)
        self.wire = _dspin(p.wire_d_mm, 0.01, 20, 0.05, suffix=" mm")
        self.pitch = _dspin(p.pitch_mm, 0.01, 50, 0.1, suffix=" mm")
        self.former = _dspin(p.former_d_mm, 1, 2000, 1, decimals=2, suffix=" mm")
        self.turns = _ispin(p.turns, 1, 500)
        self.ground = _combo(GROUND_CHOICES, p.ground)
        for text, key, w in (
            ("wire Ø", "wire", self.wire),
            ("pitch", "pitch", self.pitch),
            ("former Ø", "former", self.former),
            ("turns", "turns", self.turns),
            ("terminals", "ground", self.ground),
        ):
            self.form.addRow(_label(text, key), _tip(w, key))
            _changed_signal(w).connect(self.changed)

    def params(self) -> CoilParams:
        return CoilParams(
            self.wire.value(),
            self.pitch.value(),
            self.former.value(),
            self.turns.value(),
            self.ground.currentText(),
        )


class _Signals(QtCore.QObject):
    done = QtCore.Signal(int, object)
    failed = QtCore.Signal(int, str)


class _Job(QtCore.QRunnable):
    def __init__(self, gen: int, params: Params, signals: _Signals):
        super().__init__()
        self.gen, self.params, self.signals = gen, params, signals

    def run(self):
        try:
            self.signals.done.emit(self.gen, compute(self.params))
        except Exception as e:  # noqa: BLE001 - surface any model error in the UI
            self.signals.failed.emit(self.gen, f"{type(e).__name__}: {e}")


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, params: Params | None = None):
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
        self.gap_ref = _combo(GAP_REFS, p.gap_ref)
        self.gap = _dspin(p.gap_mm, -2000, 2000, 1, decimals=2, suffix=" mm")
        self.offset = _dspin(p.offset_mm, -2000, 2000, 1, decimals=2, suffix=" mm")
        for text, key, w in (
            ("gap reference", "gap_ref", self.gap_ref),
            ("axial gap", "gap", self.gap),
            ("lateral offset", "offset", self.offset),
        ):
            self.box_b.form.addRow(_label(text, key), _tip(w, key))

        box_f = QtWidgets.QGroupBox("Analysis")
        ff = QtWidgets.QFormLayout(box_f)
        self.f_min = _dspin(p.f_min_mhz, 1e-4, 1e4, 0.1, decimals=4, suffix=" MHz")
        self.f_max = _dspin(p.f_max_mhz, 1e-3, 1e4, 1, decimals=3, suffix=" MHz")
        self.n_freq = _ispin(p.n_freq, 10, 5000)
        self.f_view = _dspin(p.f_view_mhz, 1e-4, 1e4, 0.5, decimals=4, suffix=" MHz")
        self.z_load = _dspin(p.z_load, 1e-3, 1e9, 10, decimals=3, suffix=" Ω")
        self.r_factor = _dspin(p.r_factor, 0.1, 20, 0.1, decimals=2)
        self.coupling = _combo(["full", "magnetic", "electric"], p.coupling)
        for text, key, w in (
            ("f min", "f_min", self.f_min),
            ("f max", "f_max", self.f_max),
            ("points", "n_freq", self.n_freq),
            ("view f", "f_view", self.f_view),
            ("B load", "z_load", self.z_load),
            ("R factor", "r_factor", self.r_factor),
            ("inter-coil coupling", "coupling", self.coupling),
        ):
            ff.addRow(_label(text, key), _tip(w, key))

        box_v = QtWidgets.QGroupBox("VNA")
        fv = QtWidgets.QFormLayout(box_v)
        self.vna_setup = _combo(VNA_SETUPS, p.vna_setup)
        self.z0 = _dspin(p.z0, 1, 1000, 1, decimals=1, suffix=" Ω")
        self.p_dbm = _dspin(p.p_dbm, -100, 40, 1, decimals=1, suffix=" dBm")
        self.fill = _combo(["|I|", "|V|", "none"], "|I|")
        for text, key, w in (
            ("setup", "vna_setup", self.vna_setup),
            ("Z0", "z0", self.z0),
            ("source power", "p_dbm", self.p_dbm),
            ("cross-section fill", "fill", self.fill),
        ):
            fv.addRow(_label(text, key), _tip(w, key))

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

        # ---- right: tabs + summary -------------------------------------------------
        self.tabs = QtWidgets.QTabWidget()
        self.plot_tabs: dict[str, tuple[PlotTab, object]] = {}
        for name, fn in (
            (
                "Cross-section",
                lambda fig, r: plots.draw_cross_section(fig, r, self.fill.currentText()),
            ),
            ("Side view", plots.draw_side_view),
            ("Impedance", plots.draw_impedance),
            ("Transfer A→B", plots.draw_transfer),
            ("VNA", plots.draw_vna),
            ("Turn currents", plots.draw_distribution),
        ):
            tab = PlotTab()
            idx = self.tabs.addTab(tab, name)
            self.tabs.setTabToolTip(idx, TAB_TIPS[name])
            self.plot_tabs[name] = (tab, fn)
        self._dirty: set[str] = set()
        self.tabs.currentChanged.connect(self._draw_current)

        self.summary = QtWidgets.QTextBrowser()
        self.summary.setOpenExternalLinks(False)
        self.summary.setToolTip("Results at the view frequency. Hover the controls for help.")
        right = QtWidgets.QSplitter(QtCore.Qt.Vertical)
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
        self._timer = QtCore.QTimer(self, singleShot=True, interval=250)
        self._timer.timeout.connect(self.recompute)
        self.box_a.changed.connect(self._timer.start)
        self.box_b.changed.connect(self._timer.start)
        self.box_b.toggled.connect(self._timer.start)
        for w in (
            self.gap_ref, self.gap, self.offset, self.f_min, self.f_max, self.n_freq,
            self.f_view, self.z_load, self.r_factor, self.coupling, self.vna_setup, self.z0,
            self.p_dbm,
        ):  # fmt: skip
            _changed_signal(w).connect(self._timer.start)
        self.fill.currentTextChanged.connect(lambda _: self._mark_dirty({"Cross-section"}))
        self.recompute()

    def _build_menu(self):
        menu = self.menuBar().addMenu("&Help")
        guide = QtGui.QAction("Model && usage guide", self, shortcut="F1")
        guide.triggered.connect(self.show_guide)
        menu.addAction(guide)
        whats = QtWidgets.QWhatsThis.createAction(self)
        whats.setText("What's this? (click a control)")
        menu.addAction(whats)

    def show_guide(self):
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
            gap_ref=self.gap_ref.currentText(),
            gap_mm=self.gap.value(),
            offset_mm=self.offset.value(),
            f_min_mhz=self.f_min.value(),
            f_max_mhz=self.f_max.value(),
            n_freq=self.n_freq.value(),
            f_view_mhz=self.f_view.value(),
            z_load=self.z_load.value(),
            r_factor=self.r_factor.value(),
            coupling=self.coupling.currentText(),
            vna_setup=self.vna_setup.currentText(),
            z0=self.z0.value(),
            p_dbm=self.p_dbm.value(),
        )

    def recompute(self, blocking: bool = False):
        self._gen += 1
        self.status.setText("computing…")
        job = _Job(self._gen, self.params(), self._signals)
        if blocking:
            job.run()
        else:
            self._pool.start(job)

    @QtCore.Slot(int, object)
    def _on_done(self, gen: int, r: Results):
        if gen != self._gen:
            return  # stale result
        self._result = r
        self.status.setText("")
        dark = self.palette().color(QtGui.QPalette.Base).lightness() < 128
        self.summary.setHtml(summary_html(r, dark=dark))
        self._mark_dirty(set(self.plot_tabs))

    @QtCore.Slot(int, str)
    def _on_failed(self, gen: int, msg: str):
        if gen == self._gen:
            self.status.setText(f"<span style='color:#c0392b'>{msg}</span>")

    def _mark_dirty(self, names: set[str]):
        self._dirty |= names
        self._draw_current()

    def _draw_current(self, *_):
        """Redraw only the visible tab; others are redrawn when shown."""
        if self._result is None:
            return
        name = self.tabs.tabText(self.tabs.currentIndex())
        if name in self._dirty:
            tab, fn = self.plot_tabs[name]
            fn(tab.fig, self._result)
            tab.canvas.draw_idle()
            self._dirty.discard(name)

    def draw_all(self):
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
