"""Dielectric materials for wire insulation.

The presets are *typical* room-temperature values around 1 MHz. Real compounds vary
(flexible PVC especially: εr ≈ 3–5, tanδ ≈ 0.02–0.1 depending on plasticiser and
frequency), so treat them as starting points and override with datasheet values.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = ["Dielectric", "Material"]


@dataclass(frozen=True, slots=True)
class Dielectric:
    """Linear isotropic dielectric: ε = ε0·εr·(1 − j·tanδ)."""

    eps_r: float = 1.0
    tan_delta: float = 0.0

    def __post_init__(self) -> None:
        if not self.eps_r >= 1.0:
            raise ValueError(f"eps_r must be >= 1, got {self.eps_r}")
        if not self.tan_delta >= 0.0:
            raise ValueError(f"tan_delta must be >= 0, got {self.tan_delta}")

    @property
    def eps_complex(self) -> complex:
        """Complex relative permittivity εr(1 − j tanδ) (e^{jωt} convention)."""
        return self.eps_r * (1 - 1j * self.tan_delta)


class Material(StrEnum):
    """Insulation presets. ``CUSTOM`` has no fixed values."""

    AIR = "air / bare"
    PTFE = "PTFE"
    PE = "polyethylene"
    ENAMEL = "enamel (PU / polyester-imide)"
    POLYIMIDE = "polyimide (Kapton)"
    SILICONE = "silicone rubber"
    PVC = "PVC (flexible)"
    CUSTOM = "custom"

    @property
    def dielectric(self) -> Dielectric | None:
        return _PRESETS.get(self)


_PRESETS: dict[Material, Dielectric] = {
    Material.AIR: Dielectric(1.0, 0.0),
    Material.PTFE: Dielectric(2.1, 0.0002),
    Material.PE: Dielectric(2.3, 0.0003),
    Material.ENAMEL: Dielectric(3.6, 0.01),
    Material.POLYIMIDE: Dielectric(3.4, 0.003),
    Material.SILICONE: Dielectric(3.0, 0.002),
    Material.PVC: Dielectric(3.5, 0.05),
}
