"""Qt GUI: coil cross-section, impedance, transfer and turn-current views.

Run with ``uv run coilcal-gui``. Calculations run in a worker thread and are re-triggered
(debounced) whenever a parameter changes.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.collections import PatchCollection
from matplotlib.colors import Normalize
from matplotlib.figure import Figure
from matplotlib.patches import Circle
from PySide6 import QtCore, QtGui, QtWidgets
from scipy.constants import c as C0
from scipy.spatial.transform import Rotation

from .circuit import CoilNetwork, NetworkResult
from .geometry import SolenoidCoil
from .inductance import ac_resistance, self_inductance
from .mutual import mutual_inductance
from .srf import srf_lumped

BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, MUTED, GRID = "#1f1f1e", "#6b6a64", "#e4e3de"
COIL_COLORS = (BLUE, ORANGE)
GROUND_CHOICES = {"floating": None, "end grounded": "end", "start grounded": "start"}


# ======================================================================================
# Pure computation (no Qt) -- also used by tests
# ======================================================================================
@dataclass
class CoilParams:
    wire_d_mm: float = 1.0
    pitch_mm: float = 2.0
    former_d_mm: float = 150.0
    turns: int = 10
    ground: str = "end grounded"

    def build(self, **pose) -> SolenoidCoil:
        return SolenoidCoil(
            wire_d=self.wire_d_mm * 1e-3,
            pitch=self.pitch_mm * 1e-3,
            former_d=self.former_d_mm * 1e-3,
            n_turns=self.turns,
            **pose,
        )


@dataclass
class Params:
    a: CoilParams = field(default_factory=CoilParams)
    b: CoilParams = field(default_factory=lambda: CoilParams(turns=5))
    b_enabled: bool = True
    gap_mm: float = 50.0  # winding edge to winding edge, along A's axis
    offset_mm: float = 0.0  # lateral (x) offset of B
    tilt_deg: float = 0.0  # rotation of B about its own y axis
    f_min_mhz: float = 0.1
    f_max_mhz: float = 30.0
    n_freq: int = 300
    f_view_mhz: float = 5.0
    z_load: float = 50.0
    r_factor: float = 1.0
    coupling: str = "full"

    def coils(self) -> list[SolenoidCoil]:
        a = self.a.build()
        if not self.b_enabled:
            return [a]
        b0 = self.b.build()
        z = (a.length + b0.length) / 2 + self.gap_mm * 1e-3
        b = self.b.build(
            position=[self.offset_mm * 1e-3, 0.0, z],
            orientation=Rotation.from_euler("y", self.tilt_deg, degrees=True),
        )
        return [a, b]


@dataclass
class Results:
    params: Params
    coils: list[SolenoidCoil]
    net: CoilNetwork
    res: NetworkResult
    i_view: int
    l_dc: list[float]
    srf_net: list[float]
    srf_medhurst: list[float]
    m_static: float = float("nan")
    k_static: float = float("nan")
    electric_fraction: float = float("nan")

    @property
    def f_view(self) -> float:
        return float(self.res.freqs[self.i_view])


def compute(p: Params) -> Results:
    coils = p.coils()
    grounds = [GROUND_CHOICES[p.a.ground], GROUND_CHOICES[p.b.ground]][: len(coils)]
    net = CoilNetwork(coils, ground=grounds, coupling=p.coupling, r_factor=p.r_factor)
    f_view = p.f_view_mhz * 1e6
    freqs = np.union1d(np.geomspace(p.f_min_mhz * 1e6, p.f_max_mhz * 1e6, p.n_freq), [f_view])
    res = net.solve(freqs)
    i_view = int(np.argmin(np.abs(freqs - f_view)))
    hi = max(p.f_max_mhz * 1e6 * 10, 1e9)
    out = Results(
        params=p,
        coils=coils,
        net=net,
        res=res,
        i_view=i_view,
        l_dc=[self_inductance(c) for c in coils],
        srf_net=[
            CoilNetwork([c], ground=g, r_factor=p.r_factor).srf(f_lo=1e4, f_hi=hi)
            for c, g in zip(coils, grounds, strict=True)
        ],
        srf_medhurst=[srf_lumped(c) for c in coils],
    )
    if len(coils) == 2:
        out.m_static = mutual_inductance(*coils)
        out.k_static = out.m_static / np.sqrt(out.l_dc[0] * out.l_dc[1])
        if p.coupling == "full":
            ele = CoilNetwork(coils, ground=grounds, coupling="electric", r_factor=p.r_factor)
            z_e = ele.solve([f_view]).z[0, 1, 0]
            out.electric_fraction = abs(z_e) / abs(res.z[i_view, 1, 0])
    return out


def summary_text(r: Results) -> str:
    f = r.f_view
    lam = C0 / f
    lines = [f"view frequency  {f / 1e6:.4g} MHz   (lambda = {lam:.3g} m)", ""]
    for k, c in enumerate(r.coils):
        z = r.res.z[r.i_view, k, k]
        name = "AB"[k]
        lines += [
            (
                f"--- coil {name}: {c.n_turns} turns, l = {c.length * 1e3:.1f} mm, "
                f"r = {c.mean_radius * 1e3:.2f} mm"
            ),
            f"L_DC                {r.l_dc[k] * 1e6:10.4g} uH",
            (
                f"L_eff @ f           {z.imag / (2 * np.pi * f) * 1e6:10.4g} uH"
                f"   ({z.imag / (2 * np.pi * f) / r.l_dc[k] - 1:+.1%})"
            ),
            f"Z_in @ f            {abs(z):10.4g} ohm  ∠{np.degrees(np.angle(z)):6.1f}°",
            f"R_ac (skin, x{r.params.r_factor:g})   {ac_resistance(c, f) * r.params.r_factor:10.4g} ohm",
            f"SRF (network)       {r.srf_net[k] / 1e6:10.4g} MHz   [{(r.params.a, r.params.b)[k].ground}]",
            f"SRF (Medhurst est.) {r.srf_medhurst[k] / 1e6:10.4g} MHz",
            f"wire length         {c.wire_length:10.4g} m   ({c.wire_length / lam:.3f} lambda)",
            "",
        ]
    if len(r.coils) == 2:
        z21 = r.res.z[r.i_view, 1, 0]
        qs = 2j * np.pi * f * r.m_static
        vl = r.res.loaded_voltage(r.params.z_load)[r.i_view]
        lines += [
            "--- A -> B",
            f"M (static)          {r.m_static * 1e6:10.4g} uH",
            f"k (static)          {r.k_static:10.4f}",
            f"|Z21| @ f           {abs(z21):10.4g} ohm   (quasi-static {abs(qs):.4g})",
            f"Z21 / (j w M)       {abs(z21 / qs):10.4f}  ∠{np.degrees(np.angle(z21 / qs)):.2f}°",
            f"V_B open / I_A      {abs(z21):10.4g} V/A",
            f"V_B into {r.params.z_load:g} ohm   {abs(vl):10.4g} V/A",
        ]
        if np.isfinite(r.electric_fraction):
            lines.append(f"capacitive share    {r.electric_fraction:10.2%} of |Z21|")
    return "\n".join(lines)


# ======================================================================================
# Plotting helpers
# ======================================================================================
def _style(ax):
    ax.grid(True, color=GRID, lw=0.8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(MUTED)
    ax.tick_params(colors=MUTED)


def draw_cross_section(fig: Figure, r: Results, fill: str = "|I|") -> None:
    """One strip per coil: the wire cross-sections ('ooooooo') at true wire size and pitch.

    Horizontal = position along coil A's axis [mm]; vertical = radius [mm]. Each strip is
    cropped to its own winding so 1 mm wires stay visible next to a 150 mm former.
    """
    fig.clear()
    coils = r.coils
    a = coils[0]
    axes = fig.subplots(len(coils), 1, squeeze=False)[:, 0]
    i_port = r.res.turn_currents[r.i_view, 0]  # 1 A into coil A, other ports open
    v_node = r.res.node_voltages[r.i_view, 0]
    vals = []
    for k, c in enumerate(coils):
        if fill == "|I|":
            vals.append(np.abs(i_port[r.net.turn_slice(k)]))
        elif fill == "|V|":
            v = v_node[r.net.node_slice(k)]
            vals.append(np.abs(0.5 * (v[:-1] + v[1:])))
        else:
            vals.append(None)
    finite = [v for v in vals if v is not None]
    norm = None
    if finite:
        allv = np.concatenate(finite)
        lo, hi = float(allv.min()), float(allv.max())
        norm = Normalize(lo, hi if hi > lo else lo + 1e-12)
    cmap = "Blues"

    sm = None
    for k, (ax, c) in enumerate(zip(axes, coils, strict=True)):
        z = np.dot(c.turn_centers() - a.position, a.axis) * 1e3
        rr = c.mean_radius * 1e3
        rw = c.wire_radius * 1e3
        patches = [Circle((zi, rr), rw) for zi in z]
        pc = PatchCollection(patches, edgecolor=COIL_COLORS[k], linewidth=1.2)
        if vals[k] is not None:
            pc.set_array(vals[k])
            pc.set_cmap(cmap)
            pc.set_norm(norm)
            sm = pc
        else:
            pc.set_facecolor("white")
        ax.add_collection(pc)
        rf = c.former_d / 2 * 1e3
        ax.axhspan(rf - 4 * rw, rf, color=GRID, zorder=0)
        ax.axhline(rf, color=MUTED, lw=0.8)
        # each strip zooms on its own winding so the wires stay legible
        pad = 1.5 * c.pitch * 1e3
        ax.set_xlim(z.min() - pad, z.max() + pad)
        ax.set_ylim(rf - 3 * rw, rr + 3 * rw)
        ax.set_aspect("equal", adjustable="box")
        _style(ax)
        ax.grid(False)
        ax.set_ylabel("r [mm]")
        extra = ""
        if k == 1 and (r.params.offset_mm or r.params.tilt_deg):
            extra = (
                f" — offset {r.params.offset_mm:g} mm, tilt {r.params.tilt_deg:g}°"
                " (drawn projected on A's axis)"
            )
        ax.set_title(
            f"coil {'AB'[k]}: {c.n_turns} turns, wire Ø{c.wire_d * 1e3:g} mm, pitch "
            f"{c.pitch * 1e3:g} mm, former Ø{c.former_d * 1e3:g} mm{extra}",
            loc="left",
            color=INK,
            fontsize=9,
        )
    for ax in axes:
        ax.set_xlabel("position along coil A axis [mm]", fontsize=8, color=MUTED)
    if sm is not None:
        label = "|I_turn| per A into coil A" if fill == "|I|" else "|V_turn| per A into coil A [V]"
        fig.colorbar(sm, ax=list(axes), label=label, shrink=0.9)
    fig.suptitle(f"Winding cross-section at {r.f_view / 1e6:.4g} MHz", x=0.01, ha="left")


def draw_impedance(fig: Figure, r: Results) -> None:
    fig.clear()
    ax1, ax2 = fig.subplots(2, 1, sharex=True)
    f = r.res.freqs / 1e6
    for k, c in enumerate(r.coils):
        z = r.res.z[:, k, k]
        ax1.loglog(f, np.abs(z), color=COIL_COLORS[k], label=f"coil {'AB'[k]}")
        ax2.semilogx(f, z.imag / (2 * np.pi * r.res.freqs) / r.l_dc[k], color=COIL_COLORS[k])
        for ax in (ax1, ax2):
            if np.isfinite(r.srf_net[k]) and r.srf_net[k] / 1e6 <= f[-1]:
                ax.axvline(r.srf_net[k] / 1e6, color=COIL_COLORS[k], ls=":", lw=1)
    for ax in (ax1, ax2):
        ax.axvline(r.f_view / 1e6, color=MUTED, lw=1)
        _style(ax)
    ax1.set_ylabel("|Z_in| [Ω]")
    ax1.legend(frameon=False)
    ax1.set_title("Input impedance (other coil open); dotted = SRF of coil alone", loc="left")
    ax2.set_ylabel("L_eff / L_DC")
    ax2.set_ylim(0, 3)
    ax2.axhline(1, color=MUTED, lw=0.8)
    ax2.set_xlabel("frequency [MHz]")
    fig.align_ylabels()


def draw_transfer(fig: Figure, r: Results) -> None:
    fig.clear()
    if len(r.coils) < 2:
        fig.text(0.5, 0.5, "enable coil B", ha="center", color=MUTED)
        return
    ax1, ax2 = fig.subplots(2, 1, sharex=True)
    f = r.res.freqs
    z21 = r.res.transfer_impedance()
    qs = 2 * np.pi * f * abs(r.m_static)
    ax1.loglog(f / 1e6, np.abs(z21), color=BLUE, label="network |Z21| (open B)")
    ax1.loglog(f / 1e6, qs, color=MUTED, ls="--", lw=1.2, label="quasi-static ωM")
    ax1.loglog(
        f / 1e6,
        np.abs(r.res.loaded_voltage(r.params.z_load)),
        color=ORANGE,
        label=f"into {r.params.z_load:g} Ω",
    )
    ax1.set_ylabel("V_B per A in coil A [V/A]")
    ax1.legend(frameon=False)
    ax1.set_title("A → B transfer", loc="left")
    ax2.semilogx(f / 1e6, np.abs(z21) / qs, color=BLUE)
    ax2.axhline(1, color=MUTED, lw=0.8)
    ax2.set_ylabel("|Z21| / ωM")
    ax2.set_ylim(0, 3)
    ax2.set_xlabel("frequency [MHz]")
    for ax in (ax1, ax2):
        ax.axvline(r.f_view / 1e6, color=MUTED, lw=1)
        _style(ax)
    fig.align_ylabels()


def draw_distribution(fig: Figure, r: Results) -> None:
    fig.clear()
    ax1, ax2 = fig.subplots(2, 1)
    i = r.res.turn_currents[r.i_view, 0]
    v = r.res.node_voltages[r.i_view, 0]
    sl = r.net.turn_slice(0)
    n = np.arange(1, r.coils[0].n_turns + 1)
    ax1.plot(n, np.abs(i[sl]), "o-", color=BLUE, ms=4)
    ax1.axhline(1, color=MUTED, lw=0.8)
    ax1.set_ylabel("|I_turn| [A]")
    ax1.set_title(f"Coil A, 1 A at its terminals, {r.f_view / 1e6:.4g} MHz", loc="left")
    vs = v[r.net.node_slice(0)]
    ax2.plot(np.arange(len(vs)), np.abs(vs), "o-", color=BLUE, ms=4)
    ax2.set_ylabel("|V_node| [V]")
    ax2.set_xlabel("turn / node index (0 = start terminal)")
    for ax in (ax1, ax2):
        _style(ax)
    fig.align_ylabels()


# ======================================================================================
# Qt widgets
# ======================================================================================
class PlotTab(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.fig = Figure(layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.fig)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(NavigationToolbar2QT(self.canvas, self))
        lay.addWidget(self.canvas)


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


class CoilBox(QtWidgets.QGroupBox):
    changed = QtCore.Signal()

    def __init__(self, title: str, p: CoilParams):
        super().__init__(title)
        form = QtWidgets.QFormLayout(self)
        self.wire = _dspin(p.wire_d_mm, 0.01, 20, 0.05, suffix=" mm")
        self.pitch = _dspin(p.pitch_mm, 0.01, 50, 0.1, suffix=" mm")
        self.former = _dspin(p.former_d_mm, 1, 2000, 1, decimals=2, suffix=" mm")
        self.turns = _ispin(p.turns, 1, 500)
        self.ground = QtWidgets.QComboBox()
        self.ground.addItems(list(GROUND_CHOICES))
        self.ground.setCurrentText(p.ground)
        for label, w in (
            ("wire Ø", self.wire),
            ("pitch", self.pitch),
            ("former Ø", self.former),
            ("turns", self.turns),
            ("terminals", self.ground),
        ):
            form.addRow(label, w)
            sig = w.currentTextChanged if isinstance(w, QtWidgets.QComboBox) else w.valueChanged
            sig.connect(self.changed)

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
        form_b = self.box_b.layout()
        self.gap = _dspin(p.gap_mm, -1000, 2000, 1, decimals=2, suffix=" mm")
        self.offset = _dspin(p.offset_mm, -2000, 2000, 1, decimals=2, suffix=" mm")
        self.tilt = _dspin(p.tilt_deg, -180, 180, 1, decimals=1, suffix=" °")
        form_b.addRow("axial gap", self.gap)
        form_b.addRow("lateral offset", self.offset)
        form_b.addRow("tilt (about y)", self.tilt)

        box_f = QtWidgets.QGroupBox("Analysis")
        ff = QtWidgets.QFormLayout(box_f)
        self.f_min = _dspin(p.f_min_mhz, 1e-4, 1e4, 0.1, decimals=4, suffix=" MHz")
        self.f_max = _dspin(p.f_max_mhz, 1e-3, 1e4, 1, decimals=3, suffix=" MHz")
        self.f_view = _dspin(p.f_view_mhz, 1e-4, 1e4, 0.5, decimals=4, suffix=" MHz")
        self.n_freq = _ispin(p.n_freq, 10, 5000)
        self.z_load = _dspin(p.z_load, 1e-3, 1e9, 10, decimals=3, suffix=" Ω")
        self.r_factor = _dspin(p.r_factor, 0.1, 20, 0.1, decimals=2)
        self.coupling = QtWidgets.QComboBox()
        self.coupling.addItems(["full", "magnetic", "electric"])
        self.coupling.setCurrentText(p.coupling)
        self.fill = QtWidgets.QComboBox()
        self.fill.addItems(["|I|", "|V|", "none"])
        for label, w in (
            ("f min", self.f_min),
            ("f max", self.f_max),
            ("points", self.n_freq),
            ("view f", self.f_view),
            ("B load", self.z_load),
            ("R factor (proximity)", self.r_factor),
            ("inter-coil coupling", self.coupling),
            ("cross-section fill", self.fill),
        ):
            ff.addRow(label, w)

        self.status = QtWidgets.QLabel("")
        self.status.setWordWrap(True)
        left = QtWidgets.QWidget()
        ll = QtWidgets.QVBoxLayout(left)
        for w in (self.box_a, self.box_b, box_f, self.status):
            ll.addWidget(w)
        ll.addStretch(1)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(left)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(300)

        # ---- right: tabs + summary -------------------------------------------------
        self.tabs = QtWidgets.QTabWidget()
        self.tab_xs, self.tab_z, self.tab_t, self.tab_d = (PlotTab() for _ in range(4))
        self.tabs.addTab(self.tab_xs, "Cross-section")
        self.tabs.addTab(self.tab_z, "Impedance")
        self.tabs.addTab(self.tab_t, "Transfer A→B")
        self.tabs.addTab(self.tab_d, "Turn currents")
        self.summary = QtWidgets.QPlainTextEdit(readOnly=True)
        self.summary.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont))
        right = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        right.addWidget(self.tabs)
        right.addWidget(self.summary)
        right.setSizes([600, 260])

        split = QtWidgets.QSplitter()
        split.addWidget(scroll)
        split.addWidget(right)
        split.setSizes([320, 1000])
        self.setCentralWidget(split)
        self.resize(1400, 900)

        # ---- wiring ----------------------------------------------------------------
        self._timer = QtCore.QTimer(self, singleShot=True, interval=250)
        self._timer.timeout.connect(self.recompute)
        self.box_a.changed.connect(self._timer.start)
        self.box_b.changed.connect(self._timer.start)
        self.box_b.toggled.connect(self._timer.start)
        for w in (self.gap, self.offset, self.tilt, self.f_min, self.f_max, self.f_view):
            w.valueChanged.connect(self._timer.start)
        for w in (self.n_freq, self.z_load, self.r_factor):
            w.valueChanged.connect(self._timer.start)
        self.coupling.currentTextChanged.connect(self._timer.start)
        self.fill.currentTextChanged.connect(self._redraw_cross_section)
        self.recompute()

    def params(self) -> Params:
        return Params(
            a=self.box_a.params(),
            b=self.box_b.params(),
            b_enabled=self.box_b.isChecked(),
            gap_mm=self.gap.value(),
            offset_mm=self.offset.value(),
            tilt_deg=self.tilt.value(),
            f_min_mhz=self.f_min.value(),
            f_max_mhz=self.f_max.value(),
            n_freq=self.n_freq.value(),
            f_view_mhz=self.f_view.value(),
            z_load=self.z_load.value(),
            r_factor=self.r_factor.value(),
            coupling=self.coupling.currentText(),
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
            return  # stale
        self._result = r
        self.status.setText("")
        self.summary.setPlainText(summary_text(r))
        self._redraw_cross_section()
        for tab, fn in ((self.tab_z, draw_impedance), (self.tab_t, draw_transfer)):
            fn(tab.fig, r)
            tab.canvas.draw_idle()
        draw_distribution(self.tab_d.fig, r)
        self.tab_d.canvas.draw_idle()

    @QtCore.Slot(int, str)
    def _on_failed(self, gen: int, msg: str):
        if gen == self._gen:
            self.status.setText(f"<span style='color:#c0392b'>{msg}</span>")

    def _redraw_cross_section(self):
        if self._result is None:
            return
        draw_cross_section(self.tab_xs.fig, self._result, self.fill.currentText())
        self.tab_xs.canvas.draw_idle()


def main() -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
