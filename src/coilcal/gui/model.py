"""GUI-independent model: parameters -> all results shown in the GUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import numpy as np

from ..circuit import CoilNetwork, NetworkResult, Resonance
from ..geometry import Former, SolenoidCoil
from ..inductance import ac_resistance, self_inductance
from ..materials import Dielectric, Material
from ..mutual import mutual_inductance
from ..srf import self_capacitance_medhurst, srf_lumped
from ..types import ComplexArray, Coupling, FloatArray, Grounding, TerminalEnd, ThruMode
from ..vna import driven_turn_currents, incident_voltage, thru_network, z_to_s


class GapRef(StrEnum):
    """Reference point for B's axial position."""

    EDGE = "edge-to-edge"  # 0 = windings end to end (one pitch apart)
    CENTRE = "centre-to-centre"  # 0 = B centred on A (nested)


class SetupKind(StrEnum):
    PAIR = "pair"
    THRU = "thru"


class VnaSetup(StrEnum):
    """VNA configuration; the value is the GUI label."""

    PAIR = "A on P1, B on P2 (coupling)"
    A_SERIES = "A series-thru (P1–A–P2)"
    A_SHUNT = "A shunt-thru (A to ground)"
    B_SERIES = "B series-thru (P1–B–P2)"
    B_SHUNT = "B shunt-thru (B to ground)"

    @property
    def kind(self) -> SetupKind:
        return SetupKind.PAIR if self is VnaSetup.PAIR else SetupKind.THRU

    @property
    def coil(self) -> int | None:
        """Index of the DUT coil for thru setups (0 = A, 1 = B)."""
        return {VnaSetup.PAIR: None, VnaSetup.A_SERIES: 0, VnaSetup.A_SHUNT: 0}.get(self, 1)

    @property
    def mode(self) -> ThruMode | None:
        if self in (VnaSetup.A_SERIES, VnaSetup.B_SERIES):
            return ThruMode.SERIES
        if self in (VnaSetup.A_SHUNT, VnaSetup.B_SHUNT):
            return ThruMode.SHUNT
        return None


class Fill(StrEnum):
    """What colours the wire circles in the cross-section."""

    CURRENT = "|I|"
    VOLTAGE = "|V|"
    NONE = "none"


def _preset(m: Material) -> Dielectric:
    d = m.dielectric
    assert d is not None
    return d


@dataclass
class CoilParams:
    wire_d_mm: float = 1.0
    pitch_mm: float = 2.0
    former_d_mm: float = 150.0
    turns: int = 10
    ground: Grounding = Grounding.END
    # insulation: outer Ø over the insulation (= wire Ø for bare wire) and its dielectric
    insulation_d_mm: float = 1.06
    insulation_material: Material = Material.ENAMEL
    insulation: Dielectric = field(default_factory=lambda: _preset(Material.ENAMEL))
    # former: dielectric tube under the winding (material AIR = no former)
    former_wall_mm: float = 3.0
    former_overhang_mm: float = 10.0
    former_material: Material = Material.PMMA
    former: Dielectric = field(default_factory=lambda: _preset(Material.PMMA))

    def __post_init__(self) -> None:
        self.ground = Grounding.parse(self.ground)
        self.insulation_material = Material(self.insulation_material)
        self.former_material = Material(self.former_material)

    def build(self, **pose: Any) -> SolenoidCoil:
        mm = 1e-3
        former = None
        if self.former.eps_complex != 1:
            former = Former(self.former_wall_mm * mm, self.former, self.former_overhang_mm * mm)
        return SolenoidCoil(
            wire_d=self.wire_d_mm * mm,
            pitch=self.pitch_mm * mm,
            former_d=self.former_d_mm * mm,
            n_turns=self.turns,
            insulation_d=max(self.insulation_d_mm, self.wire_d_mm) * mm,
            insulation=self.insulation,
            former=former,
            **pose,
        )

    def dielectric_label(self) -> str:
        """Short description, e.g. 'enamel εr 3.6 · PMMA former εr 2.6, 3 mm'."""
        parts = []
        t = (self.insulation_d_mm - self.wire_d_mm) / 2
        if t > 0 and self.insulation.eps_r != 1:
            parts.append(f"insulation εr {self.insulation.eps_r:g} ({t * 1e3:.0f} µm)")
        else:
            parts.append("bare wire" if t <= 0 else "insulation εr 1")
        if self.former.eps_r != 1:
            parts.append(f"former εr {self.former.eps_r:g}, {self.former_wall_mm:g} mm wall")
        else:
            parts.append("no former dielectric")
        return " · ".join(parts)


@dataclass
class Params:
    a: CoilParams = field(default_factory=CoilParams)
    b: CoilParams = field(default_factory=lambda: CoilParams(turns=5))
    b_enabled: bool = True
    gap_ref: GapRef = GapRef.EDGE
    gap_mm: float = 50.0
    offset_mm: float = 0.0
    f_min_mhz: float = 0.1
    f_max_mhz: float = 30.0
    n_freq: int = 300
    f_view_mhz: float = 5.0
    z_load: float = 50.0
    r_factor: float = 1.0
    coupling: Coupling = Coupling.FULL
    vna_setup: VnaSetup = VnaSetup.PAIR
    z0: float = 50.0
    p_dbm: float = 0.0
    x_line_z_mm: float = 0.0  # height of the Bz(x) profile (0 = centre of coil A)

    def __post_init__(self) -> None:
        # accept plain strings (e.g. from tests or saved settings) but fail loudly on typos
        self.gap_ref = GapRef(self.gap_ref)
        self.coupling = Coupling(self.coupling)
        self.vna_setup = VnaSetup(self.vna_setup)
        if not 0 < self.f_min_mhz < self.f_max_mhz:
            raise ValueError("need 0 < f_min < f_max")

    def coils(self) -> list[SolenoidCoil]:
        a = self.a.build()
        if not self.b_enabled:
            return [a]
        b0 = self.b.build()
        if self.gap_ref is GapRef.CENTRE:
            z = self.gap_mm * 1e-3
        else:
            z = (a.length + b0.length) / 2 + self.gap_mm * 1e-3
        b = self.b.build(position=np.array([self.offset_mm * 1e-3, 0.0, z]))
        check_overlap(a, b)
        return [a, b]

    @property
    def ab(self) -> list[CoilParams]:
        return [self.a, self.b]

    @property
    def grounds(self) -> list[Grounding]:
        return [self.a.ground, self.b.ground]


def check_overlap(a: SolenoidCoil, b: SolenoidCoil) -> None:
    """Raise ValueError if the windings or formers of two parallel-axis coils intersect."""
    off = float(np.hypot(*(b.position[:2] - a.position[:2])))
    for c, d, names in ((a, b, "AB"), (b, a, "BA")):
        # winding of d vs former wall of c (radii measured from c's axis)
        if c.former is None:
            continue
        half = c.length / 2 + c.former.overhang
        if abs(d.position[2] - c.position[2]) >= half + d.length / 2 + d.outer_radius:
            continue
        r_out = c.former_d / 2
        r_in = r_out - c.former.wall
        lo, hi = d.mean_radius - off - d.outer_radius, d.mean_radius + off + d.outer_radius
        if lo < r_out - 1e-12 and hi > r_in + 1e-12 and not (c is d):
            raise ValueError(
                f"the winding of {names[1]} intersects the former wall of {names[0]}: change the "
                "gap or the former diameter / wall"
            )
    za = (a.position[2] - a.length / 2, a.position[2] + a.length / 2)
    zb = (b.position[2] - b.length / 2, b.position[2] + b.length / 2)
    clearance = (a.outer_wire_d + b.outer_wire_d) / 2
    if za[1] + clearance / 2 <= zb[0] or zb[1] + clearance / 2 <= za[0]:
        return
    # B's winding spans radii [Rb - off, Rb + off] measured from A's axis
    lo, hi = b.mean_radius - off - clearance, b.mean_radius + off + clearance
    if lo < a.mean_radius < hi:
        raise ValueError(
            "windings of A and B intersect: increase the gap, or make the radii differ by more "
            "than the lateral offset plus one wire diameter"
        )


@dataclass
class Results:
    params: Params
    coils: list[SolenoidCoil]
    net: CoilNetwork
    res: NetworkResult
    i_view: int
    l_dc: list[float]
    l_f: list[FloatArray]  # quasi-DC L(f) (internal inductance follows skin effect)
    r_f: list[FloatArray]  # skin-effect R(f) x r_factor
    srf_net: list[float]  # each coil alone (its own grounding)
    q_srf: list[float]  # resonator Q at srf_net (conductor + dielectric loss)
    rp_srf: list[float]  # |Z| at srf_net
    srf_here: list[float]  # first resonance at each coil's port in the full network (others open)
    srf_medhurst: list[float]
    c_medhurst: list[float]
    srf_vacuum: list[float]  # same coil without insulation/former dielectrics (nan if none)
    # VNA view
    vna_kind: SetupKind
    vna_coils: list[SolenoidCoil]
    vna_net: CoilNetwork
    vna_res: NetworkResult
    s: ComplexArray  # (F, 2, 2)
    drive_turn_i: ComplexArray  # (F, T) turn currents for the VNA drive
    drive_port_i: ComplexArray  # (F, 2)
    drive_node_v: ComplexArray  # (F, Nn)
    v_plus: float
    # side-view field at f_view
    field_x: FloatArray
    field_z: FloatArray
    field_b: ComplexArray  # (nz, nx, 3) complex [T]
    # Bz profiles at f_view: on A's axis vs z, and across vs x at z = x_line_z
    line_z: FloatArray
    bz_z: ComplexArray
    bz_z_uniform: ComplexArray  # same coils, uniform (mean) turn current per coil
    line_x: FloatArray
    bz_x: ComplexArray  # NaN inside the wires
    bz_x_uniform: ComplexArray
    m_static: float = float("nan")
    k_static: float = float("nan")
    electric_fraction: float = float("nan")
    warnings: list[str] = field(default_factory=list)

    @property
    def f_view(self) -> float:
        return float(self.res.freqs[self.i_view])

    @property
    def freqs(self) -> FloatArray:
        return self.res.freqs


def _field_grid(
    coils: list[SolenoidCoil], nx: int = 161, nz: int = 121
) -> tuple[FloatArray, FloatArray]:
    r_max = max(c.mean_radius + abs(c.position[0]) for c in coils)
    z_lo = min(c.position[2] - c.length / 2 for c in coils)
    z_hi = max(c.position[2] + c.length / 2 for c in coils)
    margin = 0.6 * r_max
    x = np.linspace(-1.5 * r_max, 1.5 * r_max, nx)
    zc, half = (z_lo + z_hi) / 2, max((z_hi - z_lo) / 2 + margin, 1.2 * r_max)
    z = np.linspace(zc - half, zc + half, nz)
    return x, z


def compute(p: Params) -> Results:
    coils = p.coils()
    grounds = p.grounds[: len(coils)]
    net = CoilNetwork(coils, ground=grounds, coupling=p.coupling, r_factor=p.r_factor)
    f_view = p.f_view_mhz * 1e6
    freqs = np.union1d(np.geomspace(p.f_min_mhz * 1e6, p.f_max_mhz * 1e6, p.n_freq), [f_view])
    res = net.solve(freqs)
    i_view = int(np.argmin(np.abs(freqs - f_view)))
    hi = max(p.f_max_mhz * 1e6 * 10, 1e9)

    # ---- VNA configuration -------------------------------------------------------------
    setup = p.vna_setup
    if setup.kind is SetupKind.PAIR:
        if len(coils) < 2:
            raise ValueError("enable coil B for the A/B coupling setup")
        vna_coils, vna_net, vna_res = coils, net, res
    else:
        idx, mode = setup.coil, setup.mode
        assert idx is not None and mode is not None
        if idx >= len(coils):
            raise ValueError("enable coil B for a B thru setup")
        gnd = grounds[idx].terminal or TerminalEnd.END
        vna_net = thru_network(coils[idx], mode, ground_end=gnd, r_factor=p.r_factor)
        vna_coils = vna_net.coils
        vna_res = vna_net.solve(freqs)
    s = z_to_s(vna_res.z, p.z0)
    v_plus = incident_voltage(p.p_dbm, p.z0)
    emf = np.array([2 * v_plus, 0.0])
    drive_turn_i, drive_port_i = driven_turn_currents(vna_res, emf, p.z0)
    drive_node_v = np.einsum("fp,fpn->fn", drive_port_i, vna_res.node_voltages)

    fx, fz = _field_grid(vna_coils)
    xx, zz = np.meshgrid(fx, fz)
    pts = np.stack([xx, np.zeros_like(xx), zz], -1)
    field_b = np.tensordot(drive_turn_i[i_view], vna_net.unit_fields(pts), axes=1)

    # ---- Bz line profiles -------------------------------------------------------------
    i_turns = drive_turn_i[i_view]
    i_uniform = np.empty_like(i_turns)
    for k in range(len(vna_coils)):
        sl = vna_net.turn_slice(k)
        i_uniform[sl] = i_turns[sl].mean()
    line_z = np.linspace(fz[0], fz[-1], 601)
    line_x = np.linspace(fx[0], fx[-1], 801)
    z_cut = p.x_line_z_mm * 1e-3
    pts_z = np.column_stack([np.zeros_like(line_z), np.zeros_like(line_z), line_z])
    pts_x = np.column_stack([line_x, np.zeros_like(line_x), np.full_like(line_x, z_cut)])
    gz_z = vna_net.unit_fields(pts_z)[..., 2]  # (T, n)
    gz_x = vna_net.unit_fields(pts_x)[..., 2]
    inside = np.zeros(len(line_x), dtype=bool)
    for c in vna_coils:
        for side in (-1.0, 1.0):
            xc = side * c.mean_radius + c.position[0]
            zc = c.turn_z() + c.position[2]
            d = np.hypot(line_x[:, None] - xc, z_cut - zc[None, :])
            inside |= (d < c.wire_radius).any(axis=1)
    bz_x = (i_turns @ gz_x).astype(np.complex128)
    bz_x_uniform = (i_uniform @ gz_x).astype(np.complex128)
    bz_x[inside] = np.nan
    bz_x_uniform[inside] = np.nan

    alone: list[Resonance] = [
        CoilNetwork([c], ground=g, r_factor=p.r_factor).resonance(f_lo=1e4, f_hi=hi)
        for c, g in zip(coils, grounds, strict=True)
    ]
    srf_here = (
        [net.srf(k, f_lo=1e4, f_hi=hi) for k in range(len(coils))]
        if len(coils) > 1
        else [alone[0].freq]
    )

    l_f, r_f = [], []
    for c in coils:
        l_f.append(np.array([self_inductance(c, f) for f in freqs]))
        r_f.append(np.array([ac_resistance(c, f) for f in freqs]) * p.r_factor)

    out = Results(
        params=p,
        coils=coils,
        net=net,
        res=res,
        i_view=i_view,
        l_dc=[self_inductance(c) for c in coils],
        l_f=l_f,
        r_f=r_f,
        srf_net=[x.freq for x in alone],
        q_srf=[x.q for x in alone],
        rp_srf=[x.r_parallel for x in alone],
        srf_here=srf_here,
        srf_medhurst=[srf_lumped(c) for c in coils],
        srf_vacuum=[
            CoilNetwork([c.without_dielectrics()], ground=g, r_factor=p.r_factor).srf(
                f_lo=1e4, f_hi=hi
            )
            if c.has_dielectrics
            else float("nan")
            for c, g in zip(coils, grounds, strict=True)
        ],
        c_medhurst=[self_capacitance_medhurst(c) for c in coils],
        vna_kind=setup.kind,
        vna_coils=vna_coils,
        vna_net=vna_net,
        vna_res=vna_res,
        s=s,
        drive_turn_i=drive_turn_i,
        drive_port_i=drive_port_i,
        drive_node_v=drive_node_v,
        v_plus=v_plus,
        field_x=fx,
        field_z=fz,
        field_b=field_b,
        line_z=line_z,
        bz_z=(i_turns @ gz_z).astype(np.complex128),
        bz_z_uniform=(i_uniform @ gz_z).astype(np.complex128),
        line_x=line_x,
        bz_x=bz_x,
        bz_x_uniform=bz_x_uniform,
    )
    if len(coils) == 2:
        out.m_static = mutual_inductance(coils[0], coils[1])
        out.k_static = out.m_static / np.sqrt(out.l_dc[0] * out.l_dc[1])
        if p.coupling is Coupling.FULL:
            ele = CoilNetwork(
                coils, ground=grounds, coupling=Coupling.ELECTRIC, r_factor=p.r_factor
            )
            z_e = ele.solve([f_view]).z[0, 1, 0]
            out.electric_fraction = abs(z_e) / abs(res.z[i_view, 1, 0])

    for k, c in enumerate(coils):
        name = "AB"[k]
        ratio = c.length / c.mean_d
        if not 0.1 <= ratio <= 50:
            out.warnings.append(f"coil {name}: l/D = {ratio:.2g}, outside Medhurst's fitted range")
        f_res = np.nanmin([out.srf_net[k], out.srf_here[k]])
        if np.isfinite(f_res) and f_view > 0.3 * f_res:
            where = "above" if f_view > f_res else "near"
            out.warnings.append(
                f"coil {name}: view frequency is {f_view / f_res:.3f} × its first resonance "
                f"({where} it): L_eff and X/R are dominated by the resonance, not the inductance"
            )
        if c.pitch < 2.5 * c.wire_d and p.r_factor == 1.0:
            out.warnings.append(
                f"coil {name}: pitch is {c.pitch / c.wire_d:.2g} × wire Ø; the proximity effect "
                "(not modelled) raises R, by tens of % up to 2–3× for touching turns: set R factor"
            )
        lam = 299_792_458 / f_view
        if c.wire_length / lam > 0.1:
            out.warnings.append(
                f"coil {name}: wire is {c.wire_length / lam:.2f} λ long; lumped-turn model is "
                "still fine, the static model is not"
            )
    return out
