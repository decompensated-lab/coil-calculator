"""Magnetic field of a coil via magpylib (quasi-static / DC field shape)."""

from __future__ import annotations

from typing import Literal

import magpylib as magpy
import numpy as np
from scipy.constants import mu_0

from .geometry import SolenoidCoil

Model = Literal["rings", "helix"]


def to_magpylib(
    coil: SolenoidCoil,
    current: float = 1.0,
    model: Model = "rings",
    pts_per_turn: int = 180,
):
    """Build a magpylib source for the coil.

    ``model="rings"``: one ``current.Circle`` per turn (no pitch, no net axial current).
    ``model="helix"``: one ``current.Polyline`` along the helical centreline. The polygon
    radius is enlarged so each turn encloses the same area as the true circle. Leads are not
    modelled, so the helix carries a net axial current (as the real winding does) without a
    return path.
    """
    if model == "rings":
        return magpy.Collection(
            *[
                magpy.current.Circle(
                    position=c,
                    orientation=coil.orientation,
                    diameter=coil.mean_d,
                    current=current,
                )
                for c in coil.turn_centers()
            ]
        )
    if model == "helix":
        verts = coil.helix_points_local(pts_per_turn)
        dphi = 2 * np.pi / pts_per_turn
        verts[:, :2] *= np.sqrt(dphi / np.sin(dphi))  # equal-area polygon
        return magpy.current.Polyline(
            current=current,
            vertices=verts,
            position=coil.position,
            orientation=coil.orientation,
        )
    raise ValueError(f"unknown model {model!r}")


def field_B(
    coil: SolenoidCoil,
    points,
    current: float = 1.0,
    model: Model = "rings",
    **kwargs,
) -> np.ndarray:
    """Flux density B [T] at global ``points`` (shape (..., 3)) for coil current ``current`` [A]."""
    src = to_magpylib(coil, current=current, model=model, **kwargs)
    return np.asarray(magpy.getB(src, np.asarray(points, dtype=float), sumup=True))


def B_axis_rings(coil: SolenoidCoil, z, current: float = 1.0) -> np.ndarray:
    """Exact on-axis B_z of the ring model at local axial coordinate(s) ``z`` [T]."""
    z = np.asarray(z, dtype=float)
    r = coil.mean_radius
    dz = z[..., None] - coil.turn_z()
    return (mu_0 * current * r**2 / (2 * (r**2 + dz**2) ** 1.5)).sum(-1)


def B_axis_sheet(coil: SolenoidCoil, z, current: float = 1.0) -> np.ndarray:
    """On-axis B_z of the equivalent uniform current sheet (length N*pitch) [T]."""
    z = np.asarray(z, dtype=float)
    r, h = coil.mean_radius, coil.length / 2
    n = coil.n_turns / coil.length
    return mu_0 * n * current / 2 * ((z + h) / np.hypot(r, z + h) - (z - h) / np.hypot(r, z - h))
