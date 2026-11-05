"""Dielectric materials for wire insulation and coil formers.

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
    """Dielectric presets (insulation and former materials). ``CUSTOM`` has no fixed values."""

    AIR = "air / none"
    PTFE = "PTFE"
    PE = "polyethylene"
    PP = "polypropylene"
    ENAMEL = "enamel (PU / polyester-imide)"
    POLYIMIDE = "polyimide (Kapton)"
    SILICONE = "silicone rubber"
    PVC = "PVC (flexible)"
    PVC_RIGID = "PVC (rigid pipe)"
    PMMA = "acrylic (PMMA)"
    POLYCARBONATE = "polycarbonate"
    POM = "acetal (POM)"
    PLA = "PLA (3-D print, solid)"
    FR4 = "FR4 / G10 epoxy-glass"
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
    Material.PP: Dielectric(2.25, 0.0005),
    Material.PVC_RIGID: Dielectric(3.0, 0.012),
    Material.PMMA: Dielectric(2.6, 0.015),
    Material.POLYCARBONATE: Dielectric(2.9, 0.01),
    Material.POM: Dielectric(3.7, 0.005),
    Material.PLA: Dielectric(2.8, 0.01),
    Material.FR4: Dielectric(4.4, 0.02),
}
