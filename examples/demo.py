"""Demo: typical Coil64-style coil pair at up to 5 MHz.

    uv run python examples/demo.py [--turns-a 10] [--turns-b 5] [--freq 5e6] [--gap 0.05]

Prints inductances, the quick (Medhurst) validity report, induced EMF, and the field-solved
self-resonance of coil A from the turn-level network: bare, and enamelled on a PMMA former.
Writes plots to ``examples/out/``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LogNorm

import coilcal as cc

BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, MUTED, GRID = "#1f1f1e", "#6b6a64", "#e4e3de"

plt.rcParams.update(
    {
        "axes.edgecolor": MUTED,
        "axes.labelcolor": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "lines.linewidth": 2,
        "font.size": 10,
    }
)


def make_coil(n: int, **kw) -> cc.SolenoidCoil:
    return cc.SolenoidCoil(wire_d=1.0e-3, pitch=2.0e-3, former_d=0.150, n_turns=n, **kw)


def plot_field_map(coil: cc.SolenoidCoil, out: Path) -> None:
    x = np.linspace(-0.20, 0.20, 321)
    z = np.linspace(-0.15, 0.15, 241)
    xx, zz = np.meshgrid(x, z)
    pts = np.stack([xx, np.zeros_like(xx), zz], -1)
    b = cc.field_B(coil, pts, current=1.0)
    bmag = np.linalg.norm(b, axis=-1) * 1e6  # uT per A

    fig, ax = plt.subplots(figsize=(7, 5.2), layout="constrained")
    ax.grid(False)
    lo = np.percentile(bmag, 2)
    im = ax.pcolormesh(
        x * 1e3, z * 1e3, bmag, cmap="Blues", norm=LogNorm(lo, bmag.max() / 5), shading="auto"
    )
    step = 6
    ax.streamplot(
        x[::step] * 1e3, z[::step] * 1e3, b[::step, ::step, 0], b[::step, ::step, 2],
        color=MUTED, linewidth=0.6, density=1.1, arrowsize=0.6,
    )  # fmt: skip
    r = coil.mean_radius * 1e3
    zt = coil.turn_z() * 1e3
    for s in (-1, 1):
        ax.plot(np.full_like(zt, s * r), zt, "o", ms=2.5, color=ORANGE, mec="none")
    fig.colorbar(im, ax=ax, label="|B| per ampere [µT/A]")
    ax.set_xlabel("x [mm]")
    ax.set_ylabel("z (coil axis) [mm]")
    ax.set_aspect("equal")
    ax.set_title(
        f"|B| in the x–z plane, {coil.n_turns} turns, Ø{coil.former_d * 1e3:.0f} mm former",
        loc="left", color=INK,
    )  # fmt: skip
    fig.savefig(out / "field_map.png", dpi=150)
    plt.close(fig)


def plot_mutual(a: cc.SolenoidCoil, b: cc.SolenoidCoil, out: Path) -> None:
    gaps = np.linspace(0.0, 0.20, 41)  # winding-edge to winding-edge axial gap
    base = (a.length + b.length) / 2
    m_axial = [cc.mutual_inductance(a, b.moved(position=[0, 0, base + g])) * 1e6 for g in gaps]

    offsets = np.linspace(0.0, 0.25, 41)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4), layout="constrained", sharey=True)
    ax1.plot(gaps * 1e3, m_axial, color=BLUE)
    ax1.set_xlabel("axial gap between windings [mm]")
    ax1.set_ylabel("mutual inductance M [µH]")
    ax1.set_title("Coaxial, varying gap", loc="left", color=INK)

    for gap, color in ((0.02, BLUE), (0.05, ORANGE)):
        m = [cc.mutual_inductance(a, b.moved(position=[o, 0, base + gap])) * 1e6 for o in offsets]
        ax2.plot(offsets * 1e3, m, color=color, label=f"gap {gap * 1e3:.0f} mm")
        ax2.annotate(
            f"gap {gap * 1e3:.0f} mm", (offsets[3] * 1e3, m[3]), xytext=(6, 4),
            textcoords="offset points", color=INK, fontsize=9,
        )  # fmt: skip
    ax2.axhline(0, color=MUTED, lw=0.8)
    ax2.set_xlabel("lateral offset of coil B [mm]")
    ax2.set_title("Parallel axes, lateral offset", loc="left", color=INK)
    ax2.legend(frameon=False)
    fig.suptitle(f"M between coil A ({a.n_turns} t) and coil B ({b.n_turns} t)", x=0.01, ha="left")
    fig.savefig(out / "mutual.png", dpi=150)
    plt.close(fig)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--turns-a", type=int, default=10)
    p.add_argument("--turns-b", type=int, default=5)
    p.add_argument("--freq", type=float, default=5e6)
    p.add_argument("--gap", type=float, default=0.05, help="axial gap between windings [m]")
    args = p.parse_args()

    out = Path(__file__).parent / "out"
    out.mkdir(exist_ok=True)

    a = make_coil(args.turns_a)
    b = make_coil(args.turns_b, position=[0, 0, (a.length + make_coil(args.turns_b).length) / 2])
    b = b.moved(position=[0, 0, b.position[2] + args.gap])
    f = args.freq

    for name, c in (("A", a), ("B", b)):
        print(f"=== coil {name}: {c.n_turns} turns, length {c.length * 1e3:.1f} mm ===")
        print(f"L_DC = {cc.self_inductance(c) * 1e6:.4g} uH   (Rosa/Nagaoka check "
              f"{cc.rosa_inductance(c) * 1e6:.4g} uH, Wheeler {cc.wheeler_inductance(c) * 1e6:.4g} uH)")  # fmt: skip
        print(cc.check_quasistatic(c, f))
        print()

    m = cc.mutual_inductance(a, b)
    k = cc.coupling_coefficient(a, b, freq=f, m=m)
    v = cc.induced_emf(a, b, 1.0, f, m=m)
    v50 = cc.induced_voltage_loaded(a, b, 1.0, f, z_load=50.0, m=m)
    print(f"=== A -> B, coaxial, gap {args.gap * 1e3:.0f} mm ===")
    print(f"M = {m * 1e6:.4g} uH, k = {k:.4f}")
    print(f"1 A at {f / 1e6:.3g} MHz in A: open-circuit EMF in B = {abs(v):.4g} V "
          f"(phase {np.degrees(np.angle(v)):.0f} deg), into 50 ohm = {abs(v50):.4g} V")  # fmt: skip

    print("\n=== coil A, turn-level network (one end grounded) ===")
    insulated = {
        "insulation_d": 1.06e-3,
        "insulation": cc.Material.ENAMEL.dielectric,
        "former": cc.Former(3e-3, cc.Material.PMMA.dielectric, overhang=10e-3),
    }
    for label, coil in (
        ("bare, no former", a),
        ("enamel on 3 mm PMMA", make_coil(args.turns_a, **insulated)),
    ):
        net = cc.CoilNetwork([coil], ground="end")
        res = net.resonance()
        l_eff = net.solve([f]).effective_inductance(0)[0]
        print(f"{label:20s}: SRF {res.freq / 1e6:.3g} MHz, Q_SRF {res.q:.0f}, "
              f"L_eff({f / 1e6:.3g} MHz) / L_DC = {l_eff / cc.self_inductance(coil):.3f}")  # fmt: skip

    plot_field_map(a, out)
    plot_mutual(a, make_coil(args.turns_b), out)
    print(f"\nplots written to {out}/")


if __name__ == "__main__":
    main()
