"""Reusable Qt widgets and form helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from enum import Enum

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6 import QtCore, QtWidgets

from .help import TIPS


class PlotTab(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.fig = Figure(layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.fig)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(NavigationToolbar2QT(self.canvas, self))
        lay.addWidget(self.canvas)


class EnumCombo[E: Enum](QtWidgets.QComboBox):
    """Combo box whose items are enum members; ``value()`` returns the member, never a string.

    Members are kept in a Python list and mapped by index: Qt would convert ``StrEnum``
    item data to plain strings and lose the member identity.
    """

    def __init__(
        self,
        members: Iterable[E],
        current: E,
        label: Callable[[E], str] = lambda m: str(m.value),
    ) -> None:
        super().__init__()
        self._members: list[E] = list(members)
        for m in self._members:
            self.addItem(label(m))
        self.set_value(current)

    def value(self) -> E:
        return self._members[self.currentIndex()]

    def set_value(self, member: E) -> None:
        if member not in self._members:
            raise ValueError(f"{member!r} is not an option of this combo box")
        self.setCurrentIndex(self._members.index(member))


Field = QtWidgets.QDoubleSpinBox | QtWidgets.QSpinBox | QtWidgets.QComboBox


def _tip[W: QtWidgets.QWidget](widget: W, key: str) -> W:
    text = TIPS[key]
    widget.setToolTip(text)
    widget.setWhatsThis(text)
    widget.setStatusTip(text.split("\n")[0])
    return widget


def _dspin(
    value: float, lo: float, hi: float, step: float, decimals: int = 3, suffix: str = ""
) -> QtWidgets.QDoubleSpinBox:
    w = QtWidgets.QDoubleSpinBox()
    w.setRange(lo, hi)
    w.setDecimals(decimals)
    w.setSingleStep(step)
    w.setValue(value)
    w.setSuffix(suffix)
    w.setKeyboardTracking(False)
    return w


def _ispin(value: int, lo: int, hi: int) -> QtWidgets.QSpinBox:
    w = QtWidgets.QSpinBox()
    w.setRange(lo, hi)
    w.setValue(value)
    w.setKeyboardTracking(False)
    return w


def _label(text: str, key: str) -> QtWidgets.QLabel:
    """Form label with a small ⓘ hint; hovering it shows the same tooltip as the field."""
    return _tip(QtWidgets.QLabel(f"{text} <span style='color:#8a8980'>ⓘ</span>"), key)


def _changed_signal(w: Field) -> QtCore.SignalInstance:
    if isinstance(w, QtWidgets.QComboBox):
        return w.currentIndexChanged
    return w.valueChanged


def _add_rows(form: QtWidgets.QFormLayout, rows: Iterable[tuple[str, str, Field]]) -> None:
    for text, key, w in rows:
        form.addRow(_label(text, key), _tip(w, key))
