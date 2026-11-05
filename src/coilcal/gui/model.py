"""GUI-independent model: parameters -> all results shown in the GUI."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..circuit import CoilNetwork, NetworkResult
from ..geometry import SolenoidCoil
from ..inductance import ac_resistance, self_inductance
from ..mutual import mutual_inductance
from ..srf import self_capacitance_medhurst, srf_lumped
from ..vna import driven_turn_currents, incident_voltage, thru_network, z_to_s

GROUND_CHOICES = {"end grounded": "end", "start grounded": "start", "floating": None}
GAP_REFS = ("edge-to-edge", "centre-to-centre")
# label -> (kind, coil index, thru mode)
VNA_SETUPS = {
    "A on P1, B on P2 (coupling)": ("pair", None, None),
    "A series-thru (P1–A–P2)": ("thru", 0, "series"),
    "A shunt-thru (A to ground)": ("thru", 0, "shunt"),
    "B series-thru (P1–B–P2)": ("thru", 1, "series"),
    "B shunt-thru (B to ground)": ("thru", 1, "shunt"),
}


@dataclass
class CoilParams:
    wire_d_mm: float = 1.0
    pitch_mm: float = 2.0
    former_d_mm: float = 150.0
    turns: int = 10
    ground: str = "end grounded"

    def build(self, **pose) -> SolenoidCoil:
        return SolenoidCoil(
            wire_d=self.wire_d_mm * 1e-3,
            pitch=self.pitch_mm * 1e-3,
            former_d=self.former_d_mm * 1e-3,
            n_turns=self.turns,
            **pose,
        )


@dataclass
class Params:
    a: CoilParams = field(default_factory=CoilParams)
    b: CoilParams = field(default_factory=lambda: CoilParams(turns=5))
    b_enabled: bool = True
    gap_ref: str = "edge-to-edge"
    gap_mm: float = 50.0
    offset_mm: float = 0.0
    f_min_mhz: float = 0.1
    f_max_mhz: float = 30.0
    n_freq: int = 300
    f_view_mhz: float = 5.0
    z_load: float = 50.0
    r_factor: float = 1.0
    coupling: str = "full"
    vna_setup: str = "A on P1, B on P2 (coupling)"
    z0: float = 50.0
    p_dbm: float = 0.0

    def coils(self) -> list[SolenoidCoil]:
        a = self.a.build()
        if not self.b_enabled:
            return [a]
        b0 = self.b.build()
        if self.gap_ref == "centre-to-centre":
            z = self.gap_mm * 1e-3
        else:
            z = (a.length + b0.length) / 2 + self.gap_mm * 1e-3
        b = self.b.build(position=[self.offset_mm * 1e-3, 0.0, z])
        check_overlap(a, b)
        return [a, b]

    @property
    def grounds(self):
        return [GROUND_CHOICES[self.a.ground], GROUND_CHOICES[self.b.ground]]


def check_overlap(a: SolenoidCoil, b: SolenoidCoil) -> None:
    """Raise ValueError if the windings of two parallel-axis coils intersect."""
    za = (a.position[2] - a.length / 2, a.position[2] + a.length / 2)
    zb = (b.position[2] - b.length / 2, b.position[2] + b.length / 2)
    clearance = (a.outer_wire_d + b.outer_wire_d) / 2
    if za[1] + clearance / 2 <= zb[0] or zb[1] + clearance / 2 <= za[0]:
        return
    off = float(np.hypot(*(b.position[:2] - a.position[:2])))
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
    l_f: list[np.ndarray]  # quasi-DC L(f) (internal inductance follows skin effect)
    r_f: list[np.ndarray]  # skin-effect R(f) x r_factor
    srf_net: list[float]
    srf_medhurst: list[float]
    c_medhurst: list[float]
    # VNA view
    vna_kind: str
    vna_coils: list[SolenoidCoil]
    vna_net: CoilNetwork
    vna_res: NetworkResult
    s: np.ndarray  # (F, 2, 2)
    drive_turn_i: np.ndarray  # (F, T) turn currents for the VNA drive
    drive_port_i: np.ndarray  # (F, 2)
    drive_node_v: np.ndarray  # (F, Nn)
    v_plus: float
    # side-view field at f_view
    field_x: np.ndarray
    field_z: np.ndarray
    field_b: np.ndarray  # (nz, nx, 3) complex [T]
    m_static: float = float("nan")
    k_static: float = float("nan")
    electric_fraction: float = float("nan")
    warnings: list[str] = field(default_factory=list)

    @property
    def f_view(self) -> float:
        return float(self.res.freqs[self.i_view])

    @property
    def freqs(self) -> np.ndarray:
        return self.res.freqs


def _field_grid(coils: list[SolenoidCoil], nx: int = 161, nz: int = 121):
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
    kind, idx, mode = VNA_SETUPS[p.vna_setup]
    if kind == "thru" and idx >= len(coils):
        raise ValueError("enable coil B for a B thru setup")
    if kind == "pair":
        if len(coils) < 2:
            raise ValueError("enable coil B for the A/B coupling setup")
        vna_coils, vna_net, vna_res = coils, net, res
    else:
        g = grounds[idx] or "end"
        vna_net = thru_network(coils[idx], mode, ground_end=g, r_factor=p.r_factor)
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
        srf_net=[
            CoilNetwork([c], ground=g, r_factor=p.r_factor).srf(f_lo=1e4, f_hi=hi)
            for c, g in zip(coils, grounds, strict=True)
        ],
        srf_medhurst=[srf_lumped(c) for c in coils],
        c_medhurst=[self_capacitance_medhurst(c) for c in coils],
        vna_kind=kind,
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
    )
    if len(coils) == 2:
        out.m_static = mutual_inductance(*coils)
        out.k_static = out.m_static / np.sqrt(out.l_dc[0] * out.l_dc[1])
        if p.coupling == "full":
            ele = CoilNetwork(coils, ground=grounds, coupling="electric", r_factor=p.r_factor)
            z_e = ele.solve([f_view]).z[0, 1, 0]
            out.electric_fraction = abs(z_e) / abs(res.z[i_view, 1, 0])

    for k, c in enumerate(coils):
        name = "AB"[k]
        ratio = c.length / c.mean_d
        if not 0.1 <= ratio <= 50:
            out.warnings.append(f"coil {name}: l/D = {ratio:.2g}, outside Medhurst's fitted range")
        if np.isfinite(out.srf_net[k]) and f_view > 0.3 * out.srf_net[k]:
            out.warnings.append(
                f"coil {name}: view frequency is {f_view / out.srf_net[k]:.2f} × its SRF; "
                "the quasi-static picture no longer holds"
            )
        lam = 299_792_458 / f_view
        if c.wire_length / lam > 0.1:
            out.warnings.append(
                f"coil {name}: wire is {c.wire_length / lam:.2f} λ long; lumped-turn model is "
                "still fine, the static model is not"
            )
    return out
