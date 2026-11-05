"""Matplotlib drawing functions for the GUI tabs (pure: Figure + Results in, nothing out)."""

from __future__ import annotations

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import PatchCollection
from matplotlib.colors import LogNorm, Normalize
from matplotlib.figure import Figure
from matplotlib.patches import Circle, Rectangle

from ..types import ComplexArray, FloatArray
from .model import Fill, Results, SetupKind

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, GRID = "#1f1f1e", "#6b6a64", "#e4e3de"
COIL_COLORS = (BLUE, ORANGE)
INSULATION, FORMER = "#e9c98f", "#d9d6cc"  # dielectric fills (amber enamel, grey former)


def _style(ax: Axes, grid: bool = True) -> None:
    if grid:
        ax.grid(True, color=GRID, lw=0.8)
    else:
        ax.grid(False)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(MUTED)
    ax.tick_params(colors=MUTED)


def _vline_view(r: Results, *axes: Axes) -> None:
    for ax in axes:
        ax.axvline(r.f_view / 1e6, color=MUTED, lw=1)


def _turn_values(r: Results, k: int, fill: Fill) -> FloatArray | None:
    i = r.drive_turn_i[r.i_view]
    v = r.drive_node_v[r.i_view]
    if fill is Fill.CURRENT:
        return np.abs(i[r.vna_net.turn_slice(k)])
    if fill is Fill.VOLTAGE:
        vn = v[r.vna_net.node_slice(k)]
        return np.abs(0.5 * (vn[:-1] + vn[1:]))
    return None


def _coil_name(r: Results, k: int) -> str:
    if r.vna_kind is SetupKind.PAIR:
        return "AB"[k]
    idx = r.params.vna_setup.coil
    assert idx is not None
    return "AB"[idx]


# ---------------------------------------------------------------------------------------
def draw_cross_section(fig: Figure, r: Results, fill: Fill | str = Fill.CURRENT) -> None:
    """One strip per coil: the wire cross-sections ('ooooooo') at true wire size and pitch.

    Each strip is cropped to its own winding so 1 mm wires stay legible next to a 150 mm
    former. Horizontal = position along A's axis; vertical = radius.
    """
    fill = Fill(fill)
    fig.clear()
    coils = r.vna_coils
    axes = fig.subplots(len(coils), 1, squeeze=False)[:, 0]
    vals = [_turn_values(r, k, fill) for k in range(len(coils))]
    finite = [v for v in vals if v is not None]
    norm = None
    if finite:
        allv = np.concatenate(finite)
        lo, hi = float(allv.min()), float(allv.max())
        norm = Normalize(lo, hi if hi > lo else lo * (1 + 1e-9) + 1e-30)
    sm = None
    for k, (ax, c) in enumerate(zip(axes, coils, strict=True)):
        z = (c.turn_z() + c.position[2]) * 1e3
        rr, rw = c.mean_radius * 1e3, c.wire_radius * 1e3
        ro = c.outer_radius * 1e3
        name = _coil_name(r, k)
        if ro > rw:  # insulation sleeves
            ax.add_collection(
                PatchCollection(
                    [Circle((zi, rr), ro) for zi in z],
                    facecolor=INSULATION,
                    edgecolor="none",
                    zorder=1,
                )
            )
        pc = PatchCollection(
            [Circle((zi, rr), rw) for zi in z], edgecolor=COIL_COLORS["AB".index(name)], lw=1.2
        )
        if vals[k] is not None:
            pc.set_array(vals[k])
            pc.set_cmap("Blues")
            pc.set_norm(norm)
            sm = pc
        else:
            pc.set_facecolor("white")
        ax.add_collection(pc)
        pc.set_zorder(2)
        rf = c.former_d / 2 * 1e3
        pad = 1.5 * c.pitch * 1e3
        if c.former is not None:
            half = (c.length / 2 + c.former.overhang) * 1e3
            zc = c.position[2] * 1e3
            ax.add_patch(
                Rectangle(
                    (zc - half, rf - c.former.wall * 1e3),
                    2 * half,
                    c.former.wall * 1e3,
                    facecolor=FORMER,
                    edgecolor=MUTED,
                    lw=0.8,
                    zorder=0,
                )
            )
        else:
            ax.axhline(rf, color=MUTED, lw=0.8, ls=":")
        ax.set_xlim(z.min() - pad, z.max() + pad)
        ax.set_ylim(rf - 3 * rw, rr + 3 * rw)
        ax.set_aspect("equal", adjustable="box")
        _style(ax, grid=False)
        ax.set_ylabel("r [mm]")
        ax.set_xlabel("position along coil A axis [mm]", fontsize=8, color=MUTED)
        extra = ""
        if name == "B" and r.vna_kind is SetupKind.PAIR and r.params.offset_mm:
            extra = f" — lateral offset {r.params.offset_mm:g} mm (projected on A's axis)"
        ax.set_title(
            f"coil {name}: {c.n_turns} turns, wire Ø{c.wire_d * 1e3:g}/{c.outer_wire_d * 1e3:g} mm, "
            f"pitch {c.pitch * 1e3:g} mm, former Ø{c.former_d * 1e3:g} mm{extra}",
            loc="left",
            color=INK,
            fontsize=9,
        )
    if sm is not None:
        label = "|I_turn| [A peak]" if fill is Fill.CURRENT else "|V_turn| [V peak]"
        fig.colorbar(sm, ax=list(axes), label=label, shrink=0.9)
    fig.suptitle(
        f"Winding cross-section — {r.params.vna_setup}, {r.params.p_dbm:g} dBm, "
        f"{r.f_view / 1e6:.4g} MHz",
        x=0.01,
        ha="left",
    )


# ---------------------------------------------------------------------------------------
def draw_side_view(fig: Figure, r: Results) -> None:
    """x–z plane through the coil axes: |B| (peak) map, field lines, wires at true scale."""
    fig.clear()
    ax = fig.subplots()
    x, z, b = r.field_x * 1e3, r.field_z * 1e3, r.field_b
    bmag = np.sqrt((np.abs(b) ** 2).sum(-1))  # peak amplitude of the elliptical field
    # phase that maximises the real field energy -> representative instantaneous direction
    theta = 0.5 * np.angle((b * b).sum())
    breal = (b * np.exp(-1j * theta)).real
    hi = float(np.percentile(bmag, 99.5))
    lo = max(hi * 1e-3, float(bmag.min()))
    im = ax.pcolormesh(
        x, z, bmag * 1e6, cmap="Blues", norm=LogNorm(lo * 1e6, hi * 1e6), shading="auto"
    )
    ax.streamplot(
        x, z, breal[..., 0], breal[..., 2], color=MUTED, linewidth=0.6, density=1.3, arrowsize=0.6
    )
    for k, c in enumerate(r.vna_coils):
        color = COIL_COLORS["AB".index(_coil_name(r, k))]
        zt = (c.turn_z() + c.position[2]) * 1e3
        for side in (-1, 1):
            xc = (side * c.mean_radius + c.position[0]) * 1e3
            ax.add_collection(
                PatchCollection(
                    [Circle((xc, zi), c.wire_radius * 1e3) for zi in zt],
                    facecolor=color,
                    edgecolor=color,
                )
            )
            rf = c.former_d / 2 * 1e3
            xf = side * rf + c.position[0] * 1e3  # former surface
            if c.former is not None:
                half = (c.length / 2 + c.former.overhang) * 1e3
                wall = c.former.wall * 1e3
                ax.add_patch(
                    Rectangle(
                        (xf - wall if side > 0 else xf, c.position[2] * 1e3 - half),
                        wall,
                        2 * half,
                        facecolor=FORMER,
                        edgecolor=color,
                        lw=0.6,
                        alpha=0.8,
                    )
                )
            else:
                ax.plot([xf, xf], [zt.min() - 3, zt.max() + 3], color=color, lw=0.8, alpha=0.6)
    fig.colorbar(im, ax=ax, label="|B| [µT peak]")
    ax.set_aspect("equal")
    ax.set_xlim(x[0], x[-1])
    ax.set_ylim(z[0], z[-1])
    ax.set_xlabel("x [mm]")
    ax.set_ylabel("z (coil A axis) [mm]")
    _style(ax, grid=False)
    ax.set_title(
        f"{r.params.vna_setup} — {r.params.p_dbm:g} dBm at P1, {r.f_view / 1e6:.4g} MHz",
        loc="left",
        color=INK,
        fontsize=10,
    )


# ---------------------------------------------------------------------------------------
def draw_impedance(fig: Figure, r: Results) -> None:
    fig.clear()
    ax1, ax2 = fig.subplots(2, 1, sharex=True)
    f = r.freqs
    w = 2 * np.pi * f
    for k in range(len(r.coils)):
        col = COIL_COLORS[k]
        z = r.res.z[:, k, k]
        ax1.loglog(f / 1e6, np.abs(z), color=col, label=f"coil {'AB'[k]} network")
        zq = r.r_f[k] + 1j * w * r.l_f[k]
        ax1.loglog(f / 1e6, np.abs(zq), color=col, ls=":", lw=1.5, label=f"coil {'AB'[k]} quasi-DC")
        ax2.semilogx(f / 1e6, z.imag / w / r.l_dc[k], color=col)
        ax2.semilogx(f / 1e6, r.l_f[k] / r.l_dc[k], color=col, ls=":", lw=1.5)
        if np.isfinite(r.srf_net[k]) and r.srf_net[k] <= f[-1]:
            for ax in (ax1, ax2):
                ax.axvline(r.srf_net[k] / 1e6, color=col, ls="--", lw=0.8)
    _vline_view(r, ax1, ax2)
    for ax in (ax1, ax2):
        _style(ax)
    ax1.set_ylabel("|Z_in| [Ω]")
    ax1.legend(frameon=False, fontsize=8)
    ax1.set_title(
        "Input impedance (other coil open) — dotted: quasi-DC R(f)+jωL(f), dashed: SRF",
        loc="left",
        fontsize=10,
    )
    ax2.set_ylabel("L_eff / L_DC")
    ax2.set_ylim(0, 3)
    ax2.set_xlabel("frequency [MHz]")
    fig.align_ylabels()


def draw_transfer(fig: Figure, r: Results) -> None:
    fig.clear()
    if len(r.coils) < 2:
        fig.text(0.5, 0.5, "enable coil B", ha="center", color=MUTED)
        return
    ax1, ax2 = fig.subplots(2, 1, sharex=True)
    f = r.freqs
    z21 = r.res.transfer_impedance()
    qs = 2 * np.pi * f * abs(r.m_static)
    ax1.loglog(f / 1e6, np.abs(z21), color=BLUE, label="network |Z21| (B open)")
    ax1.loglog(f / 1e6, qs, color=MUTED, ls=":", lw=1.5, label="quasi-static ωM")
    ax1.loglog(
        f / 1e6,
        np.abs(r.res.loaded_voltage(r.params.z_load)),
        color=ORANGE,
        label=f"into {r.params.z_load:g} Ω",
    )
    ax1.set_ylabel("|V_B| per A in A [V/A]")
    ax1.legend(frameon=False, fontsize=8)
    ax1.set_title("A → B transfer", loc="left", fontsize=10)
    ax2.semilogx(f / 1e6, np.abs(z21) / qs, color=BLUE)
    ax2.axhline(1, color=MUTED, lw=0.8, ls=":")
    ax2.set_ylabel("|Z21| / ωM")
    ax2.set_ylim(0, 3)
    ax2.set_xlabel("frequency [MHz]")
    _vline_view(r, ax1, ax2)
    for ax in (ax1, ax2):
        _style(ax)
    fig.align_ylabels()


# ---------------------------------------------------------------------------------------
def smith_grid(ax: Axes) -> None:
    """Minimal Smith chart grid (constant-r circles and constant-x arcs)."""
    t = np.linspace(0, 2 * np.pi, 400)
    ax.plot(np.cos(t), np.sin(t), color=MUTED, lw=1)
    for rn in (0.2, 0.5, 1, 2, 5):
        c, rad = rn / (1 + rn), 1 / (1 + rn)
        ax.plot(c + rad * np.cos(t), rad * np.sin(t), color=GRID, lw=0.8)
    for xn in (0.2, 0.5, 1, 2, 5):
        for sgn in (1, -1):
            # circle centre (1, 1/x), radius 1/x, clipped to the unit disk
            cx, cy, rad = 1.0, sgn / xn, 1 / xn
            px, py = cx + rad * np.cos(t), cy + rad * np.sin(t)
            inside = px**2 + py**2 <= 1.0001
            px, py = np.where(inside, px, np.nan), np.where(inside, py, np.nan)
            ax.plot(px, py, color=GRID, lw=0.8)
    ax.axhline(0, color=GRID, lw=0.8)
    ax.set_aspect("equal")
    ax.set_xlim(-1.05, 1.05)
    ax.set_ylim(-1.05, 1.05)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)


def draw_vna(fig: Figure, r: Results) -> None:
    fig.clear()
    gs = fig.add_gridspec(2, 2, width_ratios=[1.5, 1])
    ax_db = fig.add_subplot(gs[0, 0])
    ax_ph = fig.add_subplot(gs[1, 0], sharex=ax_db)
    ax_sm = fig.add_subplot(gs[:, 1])
    f = r.freqs / 1e6
    s = r.s
    traces = [("S11", s[:, 0, 0], BLUE), ("S21", s[:, 1, 0], ORANGE)]
    if r.vna_kind is SetupKind.PAIR:
        traces.append(("S22", s[:, 1, 1], AQUA))
    for name, y, col in traces:
        ax_db.semilogx(f, 20 * np.log10(np.maximum(np.abs(y), 1e-15)), color=col, label=name)
        ax_ph.semilogx(f, np.degrees(np.angle(y)), color=col, label=name)
    ax_db.set_ylabel("|S| [dB]")
    ax_db.legend(frameon=False, fontsize=8)
    ax_db.set_title(f"{r.params.vna_setup}, Z0 = {r.params.z0:g} Ω", loc="left", fontsize=10)
    ax_ph.set_ylabel("phase [°]")
    ax_ph.set_ylim(-185, 185)
    ax_ph.set_yticks([-180, -90, 0, 90, 180])
    ax_ph.set_xlabel("frequency [MHz]")
    _vline_view(r, ax_db, ax_ph)
    for ax in (ax_db, ax_ph):
        _style(ax)
    smith_grid(ax_sm)
    refl = [("S11", s[:, 0, 0], BLUE)]
    if r.vna_kind is SetupKind.PAIR:
        refl.append(("S22", s[:, 1, 1], AQUA))
    for name, y, col in refl:
        ax_sm.plot(y.real, y.imag, color=col, lw=1.5, label=name)
        ax_sm.plot(y[r.i_view].real, y[r.i_view].imag, "o", color=col, ms=8, mec="white", mew=2)
    ax_sm.legend(frameon=False, fontsize=8, loc="upper left")
    ax_sm.set_title("Smith chart (● = view f)", fontsize=10)
    fig.align_ylabels()


# ---------------------------------------------------------------------------------------
def draw_distribution(fig: Figure, r: Results) -> None:
    fig.clear()
    ax1, ax2 = fig.subplots(2, 1)
    i = r.drive_turn_i[r.i_view]
    v = r.drive_node_v[r.i_view]
    for k, c in enumerate(r.vna_coils):
        name = _coil_name(r, k)
        col = COIL_COLORS["AB".index(name)]
        n = np.arange(1, c.n_turns + 1)
        ax1.plot(n, np.abs(i[r.vna_net.turn_slice(k)]), "o-", color=col, ms=4, label=f"coil {name}")
        vs = v[r.vna_net.node_slice(k)]
        ax2.plot(np.arange(len(vs)), np.abs(vs), "o-", color=col, ms=4, label=f"coil {name}")
    ax1.set_ylabel("|I_turn| [A peak]")
    ax1.set_yscale("log")
    ax1.legend(frameon=False, fontsize=8)
    ax1.set_title(
        f"{r.params.vna_setup}, {r.params.p_dbm:g} dBm at P1, {r.f_view / 1e6:.4g} MHz",
        loc="left",
        fontsize=10,
    )
    ax2.set_ylabel("|V_node| [V peak]")
    ax2.set_xlabel("turn / node index (0 = start terminal)")
    for ax in (ax1, ax2):
        _style(ax)
    fig.align_ylabels()


# ---------------------------------------------------------------------------------------
def draw_bz_profiles(fig: Figure, r: Results) -> None:
    """Bz along A's axis (vs z) and across the coils (vs x at the chosen z).

    Bz is a phasor; the plots show its in-phase component, referenced to the phase of Bz at
    the on-axis maximum, so sign reversals (return flux) stay visible. Dotted: the same coils
    carrying a uniform current equal to their mean turn current (quasi-DC shape).
    """
    fig.clear()
    ax_z, ax_x = fig.subplots(2, 1)
    ref = r.bz_z[np.nanargmax(np.abs(r.bz_z))]
    rot = np.exp(-1j * np.angle(ref)) if abs(ref) > 0 else 1.0
    quad = np.nanmax(np.abs((r.bz_z * rot).imag)) / max(np.nanmax(np.abs(r.bz_z)), 1e-300)

    def inphase(b: ComplexArray) -> FloatArray:
        return (b * rot).real * 1e6  # µT

    ax_z.plot(r.line_z * 1e3, inphase(r.bz_z), color=BLUE, label="network currents")
    ax_z.plot(r.line_z * 1e3, inphase(r.bz_z_uniform), color=MUTED, ls=":", lw=1.5,
              label="uniform current (mean turn current)")  # fmt: skip
    ax_x.plot(r.line_x * 1e3, inphase(r.bz_x), color=BLUE, label="network currents")
    ax_x.plot(r.line_x * 1e3, inphase(r.bz_x_uniform), color=MUTED, ls=":", lw=1.5,
              label="uniform current")  # fmt: skip
    z_cut = r.params.x_line_z_mm
    for k, c in enumerate(r.vna_coils):
        col = COIL_COLORS["AB".index(_coil_name(r, k))]
        zc = c.position[2] * 1e3
        half = c.length / 2 * 1e3
        ax_z.axvspan(zc - half, zc + half, color=col, alpha=0.12, lw=0)
        ax_z.text(
            zc, 0.97, f"coil {_coil_name(r, k)}", transform=ax_z.get_xaxis_transform(),
            ha="center", va="top", color=col, fontsize=8,
        )  # fmt: skip
        for side in (-1, 1):
            ax_x.axvline((side * c.mean_radius + c.position[0]) * 1e3, color=col, lw=1,
                         alpha=0.6)  # fmt: skip
    ax_z.axvline(z_cut, color=MUTED, lw=1, ls="--")
    for ax in (ax_z, ax_x):
        ax.axhline(0, color=MUTED, lw=0.8)
        ax.set_ylabel("B_z in-phase [µT peak]")
        ax.legend(frameon=False, fontsize=8)
        _style(ax)
    ax_z.set_xlabel("z along coil A axis [mm]  (dashed: height of the Bz(x) cut)")
    ax_x.set_xlabel(f"x [mm] at z = {z_cut:g} mm  (vertical lines: winding radii)")
    ax_z.set_title(
        f"B_z on the axis — {r.params.vna_setup}, {r.params.p_dbm:g} dBm, "
        f"{r.f_view / 1e6:.4g} MHz  (quadrature part ≤ {quad:.1%} of peak)",
        loc="left",
        fontsize=10,
    )
    ax_x.set_title("B_z across the coils", loc="left", fontsize=10)
    fig.align_ylabels()
