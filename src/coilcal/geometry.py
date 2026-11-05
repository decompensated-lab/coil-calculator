"""Coil geometry definitions (SI units: metres)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.spatial.transform import Rotation

from .types import ArrayLike, FloatArray, Handedness


@dataclass(frozen=True)
class SolenoidCoil:
    """Single-layer cylindrical coil, parametrised like Coil64.

    Parameters
    ----------
    wire_d
        Bare conductor diameter [m].
    pitch
        Winding pitch (axial distance between adjacent turn centres) [m].
    former_d
        Former (coil form) outer diameter [m]. Wire centres sit at
        ``former_d/2 + wire_d/2`` (use ``insulation_d`` for insulated wire).
    n_turns
        Number of turns (integer).
    position
        Global position of the coil centre [m].
    orientation
        Rotation taking the coil's local frame (axis = local +z) to the global frame.
    insulation_d
        Outer diameter of insulated wire [m]; defaults to ``wire_d``. Only affects
        where the wire centre sits relative to the former.
    handedness
        :class:`Handedness` of the helix (only used by the helix field model).

    Convention: positive current circulates counter-clockwise about the local +z axis,
    so a positive current produces +z field inside the coil.
    """

    wire_d: float
    pitch: float
    former_d: float
    n_turns: int
    position: FloatArray = field(default_factory=lambda: np.zeros(3))
    orientation: Rotation = field(default_factory=Rotation.identity)
    insulation_d: float | None = None
    handedness: Handedness = Handedness.RIGHT

    def __post_init__(self) -> None:
        # normalise loosely typed inputs (lists, None, ints) and validate
        object.__setattr__(self, "position", np.asarray(self.position, dtype=float).reshape(3))
        if self.orientation is None:
            object.__setattr__(self, "orientation", Rotation.identity())
        if not isinstance(self.orientation, Rotation):
            raise TypeError("orientation must be a scipy.spatial.transform.Rotation")
        if int(self.n_turns) != self.n_turns or self.n_turns < 1:
            raise ValueError("n_turns must be a positive integer")
        object.__setattr__(self, "n_turns", int(self.n_turns))
        for name in ("wire_d", "pitch", "former_d"):
            if not getattr(self, name) > 0:
                raise ValueError(f"{name} must be positive")
        if self.pitch < self.outer_wire_d:
            raise ValueError(f"pitch ({self.pitch}) < wire outer diameter ({self.outer_wire_d})")
        object.__setattr__(self, "handedness", Handedness(self.handedness))

    # --- derived geometry -------------------------------------------------------------
    @property
    def outer_wire_d(self) -> float:
        return self.wire_d if self.insulation_d is None else self.insulation_d

    @property
    def wire_radius(self) -> float:
        return self.wire_d / 2

    @property
    def mean_radius(self) -> float:
        """Radius of the wire centreline [m]."""
        return (self.former_d + self.outer_wire_d) / 2

    @property
    def mean_d(self) -> float:
        return 2 * self.mean_radius

    @property
    def length(self) -> float:
        """Winding length N*pitch [m] (equivalent current-sheet length, as in Coil64)."""
        return self.n_turns * self.pitch

    @property
    def wire_length(self) -> float:
        """Length of the helical conductor, excluding leads [m]."""
        return self.n_turns * np.hypot(2 * np.pi * self.mean_radius, self.pitch)

    @property
    def axis(self) -> FloatArray:
        """Unit coil axis in global coordinates."""
        return self.orientation.apply([0.0, 0.0, 1.0])

    # --- discretisations --------------------------------------------------------------
    def turn_z(self) -> FloatArray:
        """Local axial positions of the N turns (ring model), centred on 0 [m]."""
        n = self.n_turns
        return (np.arange(n, dtype=np.float64) - (n - 1) / 2) * self.pitch

    def turn_centers(self) -> FloatArray:
        """Global centres of the N turns, shape (N, 3)."""
        local = np.zeros((self.n_turns, 3))
        local[:, 2] = self.turn_z()
        return self.to_global(local)

    def helix_points_local(self, pts_per_turn: int = 72) -> FloatArray:
        """Helix centreline in the local frame, shape (N*pts_per_turn+1, 3).

        Runs from z = -N*p/2 to +N*p/2 (same extent as the equivalent current sheet).
        """
        n = self.n_turns
        t = np.linspace(0.0, 2 * np.pi * n, n * pts_per_turn + 1)
        r = self.mean_radius
        z = self.pitch * t / (2 * np.pi) - self.length / 2
        # Current always circulates CCW about +z (angle t increases along the path).
        # handedness=+1: z increases with t (right-handed, current flows -z -> +z);
        # handedness=-1: z decreases with t (left-handed, current flows +z -> -z).
        return np.column_stack([r * np.cos(t), r * np.sin(t), int(self.handedness) * z])

    def helix_points(self, pts_per_turn: int = 72) -> FloatArray:
        """Helix centreline in global coordinates."""
        return self.to_global(self.helix_points_local(pts_per_turn))

    def to_global(self, local_pts: ArrayLike) -> FloatArray:
        return self.orientation.apply(np.asarray(local_pts, dtype=float)) + self.position

    def to_local(self, global_pts: ArrayLike) -> FloatArray:
        return self.orientation.inv().apply(np.asarray(global_pts, dtype=float) - self.position)

    def moved(
        self, position: ArrayLike | None = None, orientation: Rotation | None = None
    ) -> SolenoidCoil:
        """Copy of this coil with a new pose."""
        return SolenoidCoil(
            wire_d=self.wire_d,
            pitch=self.pitch,
            former_d=self.former_d,
            n_turns=self.n_turns,
            position=self.position if position is None else np.asarray(position, dtype=float),
            orientation=self.orientation if orientation is None else orientation,
            insulation_d=self.insulation_d,
            handedness=self.handedness,
        )
