"""Magnetic field of a coil via magpylib (quasi-static / DC field shape)."""

from __future__ import annotations

import magpylib as magpy
import numpy as np
from scipy.constants import mu_0

from .geometry import SolenoidCoil
from .types import ArrayLike, FieldModel, FloatArray


def to_magpylib(
    coil: SolenoidCoil,
    current: float = 1.0,
    model: FieldModel | str = FieldModel.RINGS,
    pts_per_turn: int = 180,
) -> magpy.Collection | magpy.current.Polyline:
    """Build a magpylib source for the coil.

    ``model="rings"``: one ``current.Circle`` per turn (no pitch, no net axial current).
    ``model="helix"``: one ``current.Polyline`` along the helical centreline. The polygon
    radius is enlarged so each turn encloses the same area as the true circle. Leads are not
    modelled, so the helix carries a net axial current (as the real winding does) without a
    return path.
    """
    model = FieldModel(model)
    if model is FieldModel.RINGS:
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
    if model is FieldModel.HELIX:
        verts = coil.helix_points_local(pts_per_turn)
        dphi = 2 * np.pi / pts_per_turn
        verts[:, :2] *= np.sqrt(dphi / np.sin(dphi))  # equal-area polygon
        return magpy.current.Polyline(
            current=current,
            vertices=verts,
            position=coil.position,
            orientation=coil.orientation,
        )
    raise AssertionError(model)  # unreachable: enum is exhaustive


def field_B(
    coil: SolenoidCoil,
    points: ArrayLike,
    current: float = 1.0,
    model: FieldModel | str = FieldModel.RINGS,
    pts_per_turn: int = 180,
) -> FloatArray:
    """Flux density B [T] at global ``points`` (shape (..., 3)) for coil current ``current`` [A]."""
    src = to_magpylib(coil, current=current, model=model, pts_per_turn=pts_per_turn)
    return np.asarray(magpy.getB(src, np.asarray(points, dtype=float), sumup=True))


def B_axis_rings(coil: SolenoidCoil, z: ArrayLike, current: float = 1.0) -> FloatArray:
    """Exact on-axis B_z of the ring model at local axial coordinate(s) ``z`` [T]."""
    zz = np.asarray(z, dtype=float)
    r = coil.mean_radius
    dz = zz[..., None] - coil.turn_z()
    return (mu_0 * current * r**2 / (2 * (r**2 + dz**2) ** 1.5)).sum(-1)


def B_axis_sheet(coil: SolenoidCoil, z: ArrayLike, current: float = 1.0) -> FloatArray:
    """On-axis B_z of the equivalent uniform current sheet (length N*pitch) [T]."""
    zz = np.asarray(z, dtype=float)
    r, h = coil.mean_radius, coil.length / 2
    n = coil.n_turns / coil.length
    return (
        mu_0 * n * current / 2 * ((zz + h) / np.hypot(r, zz + h) - (zz - h) / np.hypot(r, zz - h))
    )
