"""Model, plots and summary for the 'Wire pair C' tab (no Qt here)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np
from matplotlib.colors import LogNorm
from matplotlib.figure import Figure
from matplotlib.patches import Circle
from matplotlib.ticker import FuncFormatter
from scipy.constants import c as C0

from ..materials import Dielectric, Material
from ..types import FloatArray
from ..wirepair import (
    InsulatedWire,
    WirePairResult,
    bare_pair_capacitance,
    effective_radius,
    pair_capacitance,
)
from .plots import AQUA, BLUE, GRID, INK, MUTED, ORANGE, _style
from .richtext import _row, si, tex

MM = 1e-3


class SpacingRef(StrEnum):
    """How the wire spacing is specified."""

    SURFACE = "insulation surface gap"  # 0 = sleeves touching
    CENTRE = "centre-to-centre"


@dataclass(frozen=True)
class WireParams:
    conductor_d_mm: float = 1.0
    insulation_d_mm: float = 1.5  # outer diameter; = conductor_d_mm for bare wire
    material: Material = Material.PTFE
    eps_r: float = 2.1
    tan_delta: float = 0.0002

    def __post_init__(self) -> None:
        object.__setattr__(self, "material", Material(self.material))

    def wire(self) -> InsulatedWire:
        return InsulatedWire(
            self.conductor_d_mm * MM,
            self.insulation_d_mm * MM,
            Dielectric(self.eps_r, self.tan_delta),
        )


@dataclass(frozen=True)
class PairParams:
    w1: WireParams = field(default_factory=WireParams)
    w2: WireParams = field(default_factory=WireParams)
    same: bool = True  # wire 2 identical to wire 1
    spacing_ref: SpacingRef = SpacingRef.SURFACE
    spacing_mm: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "spacing_ref", SpacingRef(self.spacing_ref))

    def wires(self) -> tuple[InsulatedWire, InsulatedWire]:
        w1 = self.w1.wire()
        return w1, (w1 if self.same else self.w2.wire())

    def centre_spacing(self) -> float:
        """Centre-to-centre distance [m]."""
        w1, w2 = self.wires()
        if self.spacing_ref is SpacingRef.CENTRE:
            return self.spacing_mm * MM
        return self.spacing_mm * MM + w1.b + w2.b


@dataclass(frozen=True)
class PairResults:
    params: PairParams
    res: WirePairResult
    c_bare: float  # same conductors and centre spacing, no insulation
    c_uniform: float | None  # whole space filled with the (common) εr; None if εr differ
    c_eff_radius: float  # bare formula with effective radii
    # sweep vs insulation surface gap
    gap: FloatArray
    sweep_exact: FloatArray
    sweep_bare: FloatArray
    sweep_uniform: FloatArray | None
    sweep_eff: FloatArray

    @property
    def eps_eff(self) -> float:
        return self.res.capacitance / self.c_bare

    @property
    def z0_line(self) -> float:
        """Quasi-TEM characteristic impedance of the pair as a balanced line [Ω]."""
        return float(1 / (C0 * np.sqrt(self.res.capacitance * self.c_bare)))


def _common_eps(w1: InsulatedWire, w2: InsulatedWire) -> float | None:
    eps = {w.dielectric.eps_r for w in (w1, w2) if w.b > w.a}
    if len(eps) != 1:
        return None
    if any(w.b == w.a for w in (w1, w2)):
        return None
    return eps.pop()


def compute_pair(p: PairParams, n_sweep: int = 41) -> PairResults:
    w1, w2 = p.wires()
    s = p.centre_spacing()
    res = pair_capacitance(w1, w2, spacing=s)
    eps = _common_eps(w1, w2)
    ae1, ae2 = effective_radius(w1), effective_radius(w2)

    # sweep: surface gap from touching (or nearly, for bare wires) to a few diameters
    d_out = 2 * max(w1.b, w2.b)
    g_now = s - w1.b - w2.b
    g_max = max(3 * d_out, 1.5 * g_now)
    g_min = 0.0 if (w1.b > w1.a and w2.b > w2.a) else 0.02 * min(w1.a, w2.a)
    gap = np.linspace(g_min, g_max, n_sweep)
    ss = gap + w1.b + w2.b
    exact = np.array(
        [pair_capacitance(w1, w2, spacing=x, rtol=1e-6, max_terms=256).capacitance for x in ss]
    )
    bare = np.array([bare_pair_capacitance(w1.a, w2.a, x) for x in ss])
    eff = np.array([bare_pair_capacitance(ae1, ae2, x) for x in ss])
    return PairResults(
        params=p,
        res=res,
        c_bare=bare_pair_capacitance(w1.a, w2.a, s),
        c_uniform=None if eps is None else eps * bare_pair_capacitance(w1.a, w2.a, s),
        c_eff_radius=bare_pair_capacitance(ae1, ae2, s),
        gap=gap,
        sweep_exact=exact,
        sweep_bare=bare,
        sweep_uniform=None if eps is None else eps * bare,
        sweep_eff=eff,
    )


# ---------------------------------------------------------------------------------------
def draw_pair(fig: Figure, r: PairResults) -> None:
    """Left: |E| and equipotentials for 1 V across the pair. Right: C' vs surface gap."""
    fig.clear()
    ax_f, ax_c = fig.subplots(1, 2, width_ratios=[1.25, 1])
    res = r.res
    w1, w2 = res.wires
    s = res.spacing
    bmax = max(w1.b, w2.b)
    x = np.linspace(-s / 2 - w1.b - 1.2 * bmax, s / 2 + w2.b + 1.2 * bmax, 420)
    y = np.linspace(-2.0 * bmax, 2.0 * bmax, 260)
    xx, yy = np.meshgrid(x, y)
    phi = res.potential(xx, yy).real
    ey, ex = np.gradient(-phi, y, x)
    emag = np.hypot(ex, ey) * MM  # V/mm
    inside = np.zeros(xx.shape, bool)
    for xc, w in zip(res.centres, res.wires, strict=True):
        inside |= np.hypot(xx - xc, yy) < w.a
    emag[inside] = np.nan
    hi = float(np.nanpercentile(emag, 99.7))
    im = ax_f.pcolormesh(
        x / MM, y / MM, emag, cmap="Blues", norm=LogNorm(hi * 1e-2, hi), shading="auto"
    )
    v1, v2 = res.conductor_potentials.real
    ax_f.contour(
        x / MM,
        y / MM,
        np.where(inside, np.nan, phi),
        levels=np.linspace(min(v1, v2), max(v1, v2), 21)[1:-1],
        colors=MUTED,
        linewidths=0.6,
    )
    for xc, w in zip(res.centres, res.wires, strict=True):
        if w.b > w.a:
            ax_f.add_patch(
                Circle((xc / MM, 0), w.b / MM, facecolor="none", edgecolor=ORANGE, lw=1.4)
            )
        ax_f.add_patch(Circle((xc / MM, 0), w.a / MM, facecolor="#b87333", edgecolor=INK, lw=0.8))
    fig.colorbar(im, ax=ax_f, label="|E| [V/mm] at 1 V across the pair", shrink=0.8)
    ax_f.set_aspect("equal")
    ax_f.set_xlim(x[0] / MM, x[-1] / MM)
    ax_f.set_ylim(y[0] / MM, y[-1] / MM)
    ax_f.set_xlabel("x [mm]")
    ax_f.set_ylabel("y [mm]")
    _style(ax_f, grid=False)
    ax_f.set_title("|E| and equipotentials (0.05 V steps)", loc="left", color=INK, fontsize=10)

    g = r.gap / MM
    # exact first in the legend, but drawn on top of the near-coincident approximation
    ax_c.plot(
        g, r.sweep_exact * 1e12, color=BLUE, lw=2, label="insulated, in air (exact)", zorder=4
    )
    if r.sweep_uniform is not None:
        ax_c.plot(
            g, r.sweep_uniform * 1e12, color=ORANGE, ls="--", lw=1.5, label="all space filled, εr"
        )
    ax_c.plot(g, r.sweep_eff * 1e12, color=AQUA, ls="-.", lw=1.5, label="effective-radius approx.")
    ax_c.plot(g, r.sweep_bare * 1e12, color=MUTED, ls=":", lw=1.5, label="bare conductors, air")
    g_now = (res.spacing - w1.b - w2.b) / MM
    ax_c.axvline(g_now, color=MUTED, lw=1)
    ax_c.plot(
        [g_now], [res.capacitance * 1e12], "o", color=BLUE, ms=8, mec="white", mew=2, zorder=5
    )
    ax_c.set_yscale("log")
    plain = FuncFormatter(lambda v, _: f"{v:g}")
    ax_c.yaxis.set_major_formatter(plain)
    ax_c.yaxis.set_minor_formatter(plain)
    ax_c.tick_params(axis="y", which="minor", labelsize=8, labelcolor=MUTED)
    ax_c.set_xlabel("insulation surface gap [mm]")
    ax_c.set_ylabel("C′ [pF/m]")
    ax_c.legend(fontsize=8, frameon=False)
    _style(ax_c)
    ax_c.grid(True, which="minor", color=GRID, lw=0.5)
    ax_c.set_title("C′ vs spacing", loc="left", color=INK, fontsize=10)


# ---------------------------------------------------------------------------------------
def pair_summary_html(r: PairResults, dark: bool = False) -> str:
    ink, muted, warn = (
        ("#f0efec", "#a8a79f", "#f0a050") if dark else ("#1f1f1e", "#6b6a64", "#b4541a")
    )

    def row(sym: str, val: str, note: str = "") -> str:
        return _row(sym, val, note, ink, muted)

    res = r.res
    w1, w2 = res.wires
    c = res.capacitance
    pfm = lambda v: f"{v * 1e12:.4g} pF/m"
    gap = res.spacing - w1.b - w2.b
    rows = [
        row(r"C'", pfm(c), "exact, insulation + air"),
        row(r"C'_\mathrm{bare}", pfm(r.c_bare), "insulation removed"),
    ]
    if r.c_uniform is not None:
        rows.append(
            row(
                r"\varepsilon_r C'_\mathrm{bare}",
                pfm(r.c_uniform),
                f"all space dielectric (C′ = {c / r.c_uniform:.1%} of it)",
            )
        )
    rows += [
        row(
            r"C'_{a_\mathrm{eff}}",
            pfm(r.c_eff_radius),
            f"effective-radius approx., {r.c_eff_radius / c - 1:+.2%}",
        ),
        row(
            r"\tan\delta_\mathrm{eff}",
            f"{res.tan_delta:.3g}",
            f"G′ = {si(res.conductance(1e6), 'S/m', 3)} @ 1 MHz",
        ),
    ]
    line = [
        row(r"\varepsilon_\mathrm{eff}=C'/C'_\mathrm{air}", f"{r.eps_eff:.4f}"),
        row(r"Z_0=1/(c_0\sqrt{C' C'_\mathrm{air}})", f"{r.z0_line:.4g} Ω", "balanced, quasi-TEM"),
        row(r"v/c_0=1/\sqrt{\varepsilon_\mathrm{eff}}", f"{1 / np.sqrt(r.eps_eff):.4f}"),
        row(r"L'_\mathrm{ext}", si(1 / (C0**2 * r.c_bare), "H/m"), "external (HF)"),
    ]
    geo = [
        row(r"s", f"{res.spacing / MM:.4g} mm", "centre-to-centre"),
        row(r"g", f"{gap / MM:.4g} mm", "insulation surface gap"),
    ]
    for k, w in enumerate(res.wires):
        if r.params.same and k == 1:
            break
        label = "wires 1, 2" if r.params.same else f"wire {k + 1}"
        geo.append(
            row(
                rf"t_{{{k + 1}}}",
                f"{(w.b - w.a) / MM:.4g} mm",
                f"insulation thickness, {label}",
            )
        )
    notes = []
    if not res.converged:
        notes.append(f"multipole series not fully converged ({res.n_terms} terms)")
    warn_html = "".join(f"<div style='color:{warn}'>⚠ {m}</div>" for m in notes)
    cols = [
        f"<h3 style='margin:0'>Capacitance per length</h3><table>{''.join(rows)}</table>",
        f"<h3 style='margin:0'>As a two-wire line</h3><table>{''.join(line)}</table>",
        (
            f"<h3 style='margin:0'>Geometry</h3><table>{''.join(geo)}</table>"
            f"<p style='color:{muted}'>{res.n_terms} multipole terms per wire</p>"
        ),
    ]
    cells = "".join(f"<td valign='top' style='padding-right:28px'>{c}</td>" for c in cols)
    return (
        f"<div style='color:{ink}'>{warn_html}<table cellspacing='0'><tr>{cells}</tr></table>"
        f"<p style='color:{muted}'>Two long parallel wires, insulation in air; "
        f"{tex(r'C = q/(V_1-V_2)', ink)} with equal and opposite charges.</p></div>"
    )
