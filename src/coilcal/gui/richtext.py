"""HTML summary with TeX-typeset symbols (matplotlib mathtext -> inline PNG)."""

from __future__ import annotations

import base64
import io
from functools import lru_cache

import numpy as np
from matplotlib.font_manager import FontProperties
from matplotlib.mathtext import math_to_image

from .model import Results

_PREFIX = [
    (1e9, "G"),
    (1e6, "M"),
    (1e3, "k"),
    (1, ""),
    (1e-3, "m"),
    (1e-6, "µ"),
    (1e-9, "n"),
    (1e-12, "p"),
]


def si(x: float | None, unit: str, digits: int = 4) -> str:
    """Format with an SI prefix, e.g. ``si(2.3e-6, 'H') -> '2.3 µH'``."""
    if x is None or not np.isfinite(x):
        return "—"
    if x == 0:
        return f"0 {unit}"
    for scale, p in _PREFIX:
        if abs(x) >= scale * 0.9995:
            return f"{x / scale:.{digits}g} {p}{unit}"
    return f"{x:.{digits}g} {unit}"


@lru_cache(maxsize=512)
def tex(expr: str, color: str = "#1f1f1e", size: float = 13.0, scale: float = 2.0) -> str:
    """Inline ``<img>`` of a mathtext expression (rendered at ``scale``x for HiDPI)."""
    buf = io.BytesIO()
    math_to_image(
        f"${expr}$", buf, prop=FontProperties(size=size), dpi=72 * scale, format="png", color=color
    )
    data = buf.getvalue()
    w = int.from_bytes(data[16:20], "big") / scale
    h = int.from_bytes(data[20:24], "big") / scale
    b64 = base64.b64encode(data).decode()
    return (
        f'<img src="data:image/png;base64,{b64}" width="{w:.0f}" height="{h:.0f}" '
        'style="vertical-align: middle">'
    )


def _row(sym: str, value: str, note: str = "", ink: str = "#1f1f1e", muted: str = "#6b6a64") -> str:
    return (
        f"<tr><td style='padding:1px 10px 1px 0'>{tex(sym, ink)}</td>"
        f"<td align='right' style='padding:1px 8px'><b>{value}</b></td>"
        f"<td style='color:{muted}; padding-left:6px'>{note}</td></tr>"
    )


def summary_html(r: Results, dark: bool = False) -> str:
    ink, muted, warn = (
        ("#f0efec", "#a8a79f", "#f0a050") if dark else ("#1f1f1e", "#6b6a64", "#b4541a")
    )
    f = r.f_view
    w = 2 * np.pi * f
    lam = 299_792_458 / f

    def row(sym: str, val: str, note: str = "") -> str:
        return _row(sym, val, note, ink, muted)

    cols = []
    for k, c in enumerate(r.coils):
        z = r.res.z[r.i_view, k, k]
        l_eff = z.imag / w
        rows = [
            row(r"L_\mathrm{DC}", si(r.l_dc[k], "H"), "static, ring model"),
            row(
                r"L_\mathrm{eff}=\mathrm{Im}\,Z_{in}/\omega",
                si(l_eff, "H"),
                f"{l_eff / r.l_dc[k] - 1:+.1%} vs DC",
            ),
            row(r"|Z_{in}|", si(abs(z), "Ω"), f"∠ {np.degrees(np.angle(z)):.1f}°"),
            row(r"R_\mathrm{ac}", si(r.r_f[k][r.i_view], "Ω"), "skin effect × R factor"),
            row(r"Q=\omega L/R", f"{l_eff * w / max(z.real, 1e-30):.4g}", "from network Z"),
            row(
                r"f_\mathrm{SRF}",
                si(r.srf_net[k], "Hz"),
                f"network, {r.params.grounds[k].label}",
            ),
            row(
                r"f_\mathrm{SRF}^\mathrm{Medhurst}",
                si(r.srf_medhurst[k], "Hz"),
                f"C = {si(r.c_medhurst[k], 'F', 3)}",
            ),
            row(
                r"\ell_\mathrm{wire}/\lambda", f"{c.wire_length / lam:.3f}", si(c.wire_length, "m")
            ),
        ]
        cols.append(
            f"<h3 style='margin:0'>Coil {'AB'[k]}</h3>"
            f"<p style='color:{muted}; margin:0'>{c.n_turns} turns · ℓ = {c.length * 1e3:.1f} mm · "
            f"r = {c.mean_radius * 1e3:.2f} mm</p><table>{''.join(rows)}</table>"
        )

    if len(r.coils) == 2:
        z21 = r.res.z[r.i_view, 1, 0]
        qs = 1j * w * r.m_static
        vl = r.res.loaded_voltage(r.params.z_load)[r.i_view]
        rows = [
            row("M", si(r.m_static, "H"), "static"),
            row(r"k=M/\sqrt{L_A L_B}", f"{r.k_static:.4f}"),
            row(r"|Z_{21}|", si(abs(z21), "Ω"), "= open-circuit V_B per A in A"),
            row(
                r"|Z_{21}|/\omega M",
                f"{abs(z21 / qs):.4f}",
                f"∠ {np.degrees(np.angle(z21 / qs)):.2f}°",
            ),
            row(rf"|V_B|\,@\,{r.params.z_load:g}\,\Omega", si(abs(vl), "V/A")),
        ]
        if np.isfinite(r.electric_fraction):
            rows.append(
                row(r"|Z_{21}^{(E)}|/|Z_{21}|", f"{r.electric_fraction:.2%}", "capacitive path")
            )
        cols.append(f"<h3 style='margin:0'>A → B (open circuit)</h3><table>{''.join(rows)}</table>")

    # VNA column
    s = r.s[r.i_view]
    db = lambda x: 20 * np.log10(max(abs(x), 1e-30))
    i_p = r.drive_port_i[r.i_view]
    rows = [
        row(r"S_{11}", f"{db(s[0, 0]):.2f} dB", f"∠ {np.degrees(np.angle(s[0, 0])):.1f}°"),
        row(r"S_{21}", f"{db(s[1, 0]):.2f} dB", f"∠ {np.degrees(np.angle(s[1, 0])):.1f}°"),
        row(r"S_{22}", f"{db(s[1, 1]):.2f} dB", f"∠ {np.degrees(np.angle(s[1, 1])):.1f}°"),
        row(r"V^{+}", si(r.v_plus, "V"), f"peak, {r.params.p_dbm:g} dBm into {r.params.z0:g} Ω"),
        row(r"|I_{P1}|", si(abs(i_p[0]), "A"), "peak"),
        row(r"|I_{P2}|", si(abs(i_p[1]), "A"), "peak"),
        row(r"|B|_\mathrm{max}", si(np.abs(r.field_b).max(), "T"), "in side-view plane"),
    ]
    cols.append(
        f"<h3 style='margin:0'>VNA</h3><p style='color:{muted}; margin:0'>{r.params.vna_setup}</p>"
        f"<table>{''.join(rows)}</table>"
    )

    head = (
        f"<p style='margin:0 0 4px 0'>View frequency <b>{si(f, 'Hz')}</b> · λ = {lam:.3g} m · "
        f"{tex(r'\omega = 2\pi f', ink)}</p>"
    )
    warn_html = "".join(f"<div style='color:{warn}'>⚠ {m}</div>" for m in r.warnings)
    cells = "".join(f"<td valign='top' style='padding-right:28px'>{c}</td>" for c in cols)
    return (
        f"<div style='color:{ink}'>{head}{warn_html}"
        f"<table cellspacing='0'><tr>{cells}</tr></table></div>"
    )
