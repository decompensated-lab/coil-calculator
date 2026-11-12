"""Shared enums and type aliases.

All mode-like parameters are ``StrEnum``s. Public functions also accept the plain string
values (``"end"``, ``"magnetic"``, ...); these are validated on entry via ``Enum(value)``, so a
typo raises ``ValueError: 'magnetc' is not a valid Coupling`` instead of silently doing
something else.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import NamedTuple

import numpy as np
from numpy.typing import ArrayLike, NDArray

type FloatArray = NDArray[np.float64]
type ComplexArray = NDArray[np.complex128]

__all__ = [
    "ArrayLike",
    "ComplexArray",
    "Coupling",
    "FieldModel",
    "FloatArray",
    "Grounding",
    "Handedness",
    "MutualMethod",
    "Port",
    "Terminal",
    "TerminalEnd",
    "ThruMode",
]


class Handedness(IntEnum):
    """Helix winding sense (only matters for the helix field model)."""

    RIGHT = 1
    LEFT = -1


class TerminalEnd(StrEnum):
    """One of the two terminals of a coil. Current enters the coil at START."""

    START = "start"
    END = "end"


class Grounding(StrEnum):
    """Which coil terminal (if any) is tied to the reference / coax shield."""

    FLOATING = "floating"
    START = "start"
    END = "end"

    @classmethod
    def parse(cls, value: Grounding | str | None) -> Grounding:
        """Accept an enum, its string value, or ``None`` (= floating)."""
        return cls.FLOATING if value is None else cls(value)

    @property
    def terminal(self) -> TerminalEnd | None:
        """The grounded terminal, or ``None`` if floating."""
        return None if self is Grounding.FLOATING else TerminalEnd(self.value)

    @property
    def label(self) -> str:
        return "floating" if self is Grounding.FLOATING else f"{self.value} grounded"


class Coupling(StrEnum):
    """Which inter-coil coupling paths a network keeps (diagnostic)."""

    FULL = "full"
    MAGNETIC = "magnetic"  # mutual inductance only
    ELECTRIC = "electric"  # inter-coil capacitance only


class FieldModel(StrEnum):
    """Current model used for magpylib field computations."""

    RINGS = "rings"  # one circular loop per turn
    HELIX = "helix"  # helical polyline (pitch + net axial current)


class MutualMethod(StrEnum):
    RINGS = "rings"  # turn-pair filament sums (accurate, default)
    FLUX = "flux"  # magpylib flux through each turn's disk (independent check)


class ThruMode(StrEnum):
    """Two-port through-fixture topology for a single coil."""

    SERIES = "series"  # coil between the two centre conductors
    SHUNT = "shunt"  # coil from the joined centre line to ground


type Terminal = tuple[int, TerminalEnd] | None
"""``(coil_index, end)`` or ``None`` for the reference node."""


class Port(NamedTuple):
    """A network port: current enters at ``plus`` and leaves at ``minus``."""

    plus: Terminal
    minus: Terminal
