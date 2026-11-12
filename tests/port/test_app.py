"""The app layer against ``app::call`` in Rust: ``coilcal.gui.model.compute`` and the
wire-pair calculator ``coilcal.gui.pair.compute_pair``.

The request and response go through the same byte format the browser worker uses
(``rust/crates/core/src/app.rs``), so this also checks that format.
"""

import struct
from dataclasses import replace

import numpy as np
import pytest
from conftest import coil_table

from coilcal.gui import model as gm
from coilcal.gui import pair as gp
from coilcal.materials import Dielectric, Material
from coilcal.types import Coupling, Grounding

GROUND = {Grounding.FLOATING: 0, Grounding.START: 1, Grounding.END: 2}
COIL_FIELDS = ["wire_d_mm", "pitch_mm", "former_d_mm", "turns", "insulation_d_mm",
               "former_wall_mm", "former_overhang_mm"]  # fmt: skip


def flat(p: gm.Params) -> dict[str, float]:
    d: dict[str, float] = {"kind": 0}
    for k, c in (("a", p.a), ("b", p.b)):
        d |= {f"{k}.{f}": getattr(c, f) for f in COIL_FIELDS}
        d |= {
            f"{k}.ground": GROUND[c.ground],
            f"{k}.insulation_eps_r": c.insulation.eps_r,
            f"{k}.insulation_tan_delta": c.insulation.tan_delta,
            f"{k}.former_eps_r": c.former.eps_r,
            f"{k}.former_tan_delta": c.former.tan_delta,
        }
    for f in ["gap_mm", "offset_mm", "f_min_mhz", "f_max_mhz", "n_freq", "f_view_mhz",
              "z_load", "r_factor", "z0", "p_dbm", "x_line_z_mm"]:  # fmt: skip
        d[f] = getattr(p, f)
    d["b_enabled"] = p.b_enabled
    d["gap_ref"] = list(gm.GapRef).index(p.gap_ref)
    d["coupling"] = list(Coupling).index(p.coupling)
    d["vna_setup"] = list(gm.VnaSetup).index(p.vna_setup)
    return d


def encode(values: dict[str, float]) -> np.ndarray:
    out = struct.pack("<I", len(values))
    for name, v in values.items():
        out += struct.pack("<I", len(name)) + name.encode() + struct.pack("<d", float(v))
    return np.frombuffer(out, np.uint8).astype(float)


def decode(arr: np.ndarray) -> dict[str, np.ndarray | list[str]]:
    buf = arr.astype(np.uint8).tobytes()
    pos = 0

    def take(n: int) -> bytes:
        nonlocal pos
        pos += n
        return buf[pos - n : pos]

    def u32() -> int:
        return struct.unpack("<I", take(4))[0]

    if take(1)[0]:
        raise ValueError(take(u32()).decode())
    out: dict[str, np.ndarray | list[str]] = {}
    for _ in range(u32()):
        name = take(u32()).decode()
        kind, ndim = take(2)
        shape = [u32() for _ in range(ndim)]
        n = int(np.prod(shape))
        if kind == 2:
            out[name] = [take(u32()).decode() for _ in range(n)]
        else:
            data = np.frombuffer(take(8 * n * (1 + kind)), "<f8")
            out[name] = (data.view(np.complex128) if kind else data).reshape(shape)
    assert pos == len(buf)
    return out


def call(port, p: gm.Params | gp.PairParams):
    (resp,) = port("app", encode(flat(p) if isinstance(p, gm.Params) else flat_pair(p)))
    return decode(resp)


def close(got, ref, rtol):
    """Per leading index: max|got - ref| <= rtol * max|ref| (NaN where the reference is)."""
    got, ref = np.asarray(got), np.asarray(ref)
    assert got.shape == ref.shape
    assert np.array_equal(np.isnan(got), np.isnan(ref))
    got, ref = np.nan_to_num(got), np.nan_to_num(ref)
    axes = tuple(range(1, ref.ndim))
    diff = np.abs(got - ref).max(axis=axes)
    scale = np.abs(ref).max(axis=axes)
    assert np.all(diff <= rtol * scale), np.max(diff / scale)


def approx(x, rel):
    return pytest.approx(np.asarray(x, float), rel=rel, abs=0, nan_ok=True)


BARE = {"insulation_d_mm": 1.0, "former_material": Material.AIR, "former": Dielectric()}
CASES = {
    "gui-default": gm.Params(),
    "a-alone-series": gm.Params(b_enabled=False, vna_setup=gm.VnaSetup.A_SERIES),
    "b-shunt-magnetic": gm.Params(
        b=gm.CoilParams(turns=7, ground=None), coupling=Coupling.MAGNETIC,
        vna_setup=gm.VnaSetup.B_SHUNT),
    "nested-offset": gm.Params(
        b=gm.CoilParams(former_d_mm=100, turns=6, former_wall_mm=2), gap_ref=gm.GapRef.CENTRE,
        gap_mm=0.0, offset_mm=5.0, x_line_z_mm=3.0),
    "bare-warnings": gm.Params(  # l/D, near-resonance, proximity and wire-length warnings
        a=gm.CoilParams(turns=2, pitch_mm=1.2, ground=None, **BARE),
        b=gm.CoilParams(turns=30, pitch_mm=1.1, **BARE),
        coupling=Coupling.ELECTRIC, f_view_mhz=25.0, f_max_mhz=40.0),
    "lossless-tuned": gm.Params(
        a=gm.CoilParams(insulation=Dielectric(3.6), former=Dielectric(2.6), ground="start"),
        offset_mm=12.0, r_factor=1.5, z0=75.0, p_dbm=10.0, n_freq=120, f_view_mhz=0.37),
}  # fmt: skip
# Network results: as in test_circuit (cond up to 8e7); floating node voltages carry the whole
# matrix's conditioning, see RTOL_V there.
RTOL, RTOL_V = 1e-10, 1e-9


@pytest.mark.parametrize("name", CASES)
def test_compute(port, name):
    p = CASES[name]
    r = gm.compute(p)
    got = call(port, p)
    i_view, v_plus, vna_pair, m, k, ef = got["scalars"]
    assert (int(i_view), bool(vna_pair)) == (r.i_view, r.vna_kind is gm.SetupKind.PAIR)
    assert got["freqs"] == approx(r.freqs, 1e-15)
    assert got["coils"] == approx(coil_table(r.coils), 1e-15)
    assert got["vna_coils"] == approx(coil_table(r.vna_coils), 1e-15)
    assert [v_plus, m, k] == approx([r.v_plus, r.m_static, r.k_static], 1e-12)
    assert ef == approx(r.electric_fraction, 1e-9)  # ratio of two network solves
    close(got["z"], r.res.z, RTOL)
    for key in ["l_dc", "l_f", "r_f", "srf_medhurst", "c_medhurst"]:
        assert got[key] == approx(getattr(r, key), 1e-13), key
    for key in ["srf_net", "srf_here", "srf_vacuum"]:
        assert got[key] == approx(getattr(r, key), 1e-12), key
    assert got["q_srf"] == approx(r.q_srf, 1e-9)  # finite difference, cf. test_circuit
    assert got["rp_srf"] == approx(r.rp_srf, 1e-11)
    close(got["s"], r.s, RTOL)
    close(got["drive_port_i"], r.drive_port_i, RTOL)
    close(got["drive_turn_i"], r.drive_turn_i, RTOL)
    close(got["drive_node_v"], r.drive_node_v, RTOL_V)
    for key in ["field_x", "field_z", "line_z", "line_x"]:
        assert got[key] == approx(getattr(r, key), 1e-15), key
    # fields: superpositions of the drive currents above, relative to the largest value
    close(got["field_b"][None], r.field_b[None], RTOL)
    for key in ["bz_z", "bz_z_uniform", "bz_x", "bz_x_uniform"]:
        close(got[key][None], getattr(r, key)[None], RTOL)
    assert got["warnings"] == r.warnings


ERRORS = {
    "pitch < insulated wire": lambda: gm.Params(a=gm.CoilParams(pitch_mm=1.0)),
    "windings intersect": lambda: gm.Params(gap_ref=gm.GapRef.CENTRE, gap_mm=0.0,
                                            b=gm.CoilParams(former_d_mm=150.5)),
    "winding in former": lambda: gm.Params(gap_ref=gm.GapRef.CENTRE, gap_mm=0.0,
                                           b=gm.CoilParams(former_d_mm=143)),
    "wall >= radius": lambda: gm.Params(a=gm.CoilParams(former_d_mm=5.0, former_wall_mm=3.0)),
    "eps_r < 1": lambda: gm.Params(a=gm.CoilParams(insulation=Dielectric(0.5))),
    "f_min >= f_max": lambda: gm.Params(f_min_mhz=5.0, f_max_mhz=5.0),
    "pair without B": lambda: gm.Params(b_enabled=False),
    "B thru without B": lambda: gm.Params(b_enabled=False, vna_setup=gm.VnaSetup.B_SERIES),
}  # fmt: skip


def _unchecked(make):
    """Build the Params without Python's constructor checks, to send the same values."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(gm.Params, "__post_init__", lambda self: None)
        mp.setattr(Dielectric, "__post_init__", lambda self: None)
        return make()


@pytest.mark.parametrize("name", ERRORS)
def test_invalid_input_is_an_error(port, name):
    make = ERRORS[name]
    with pytest.raises(ValueError):
        gm.compute(make())  # raises in a constructor or in compute
    p = _unchecked(make)
    with pytest.raises(ValueError):
        call(port, p)


def test_bad_requests(port):
    good = flat(gm.Params())
    for values, match in [
        ({k: v for k, v in good.items() if k != "z0"}, "missing parameter z0"),
        (good | {"z_0": 50.0}, "unknown parameter z_0"),
        (good | {"gap_mm": float("nan")}, "empty or not a number \\(gap_mm\\)"),
        (good | {"vna_setup": 9}, "bad vna_setup"),
        (good | {"a.turns": 2.5}, "turns must be a positive integer"),
    ]:
        (resp,) = port("app", encode(values))
        with pytest.raises(ValueError, match=match):
            decode(resp)


def test_capacitance_is_reused(port):
    """Changing only the view frequency and the drive reuses every capacitance matrix."""
    import time

    p = gm.Params()
    call(port, replace(p, f_view_mhz=4.0))
    t0 = time.perf_counter()
    call(port, replace(p, f_view_mhz=3.0, p_dbm=5.0))
    warm = time.perf_counter() - t0
    t0 = time.perf_counter()
    call(port, replace(p, a=replace(p.a, turns=11)))  # new geometry: A, A+B, vacuum A solved
    cold = time.perf_counter() - t0
    assert warm < 0.7 * cold, (warm, cold)


# ---- wire-pair calculator (kind 1): gui/pair.py compute_pair ---------------------------


def flat_pair(p: gp.PairParams) -> dict[str, float]:
    d: dict[str, float] = {"kind": 1}
    for k, w in (("w1", p.w1), ("w2", p.w2)):
        for f in ["conductor_d_mm", "insulation_d_mm", "eps_r", "tan_delta"]:
            d[f"{k}.{f}"] = getattr(w, f)
    d["same"] = p.same
    d["spacing_ref"] = list(gp.SpacingRef).index(p.spacing_ref)
    d["spacing_mm"] = p.spacing_mm
    return d


CENTRE = gp.SpacingRef.CENTRE
BARE_WIRE = gp.WireParams(1.0, 1.0, Material.AIR, 1.0, 0.0)
PAIRS = {
    "gui-default": gp.PairParams(),
    "bare": gp.PairParams(w1=BARE_WIRE, spacing_mm=0.3),
    "unequal-centre": gp.PairParams(
        w2=gp.WireParams(0.5, 0.9, Material.PVC, 3.5, 0.05), same=False, spacing_ref=CENTRE,
        spacing_mm=2.0),
    "from-coil-a": gp.PairParams(
        w1=gp.WireParams(1.0, 1.06, Material.ENAMEL, 3.6, 0.01), spacing_ref=CENTRE,
        spacing_mm=2.0),
    "lossless-gap": gp.PairParams(w1=gp.WireParams(1.0, 1.6, Material.CUSTOM, 4.0), spacing_mm=1.0),
    "bare-and-insulated": gp.PairParams(w2=BARE_WIRE, same=False, spacing_mm=0.5),
}  # fmt: skip


@pytest.mark.parametrize("name", PAIRS)
def test_pair(port, name):
    p = PAIRS[name]
    r = gp.compute_pair(p)
    got = call(port, p)
    n_terms, converged, spacing, c_bare, c_uniform, c_eff = got["scalars"]
    assert (int(n_terms), bool(converged)) == (r.res.n_terms, r.res.converged)
    assert complex(got["c"][0]) == pytest.approx(r.res.c_complex, rel=1e-12, abs=0)
    assert got["v"] == pytest.approx(r.res.conductor_potentials, rel=1e-12, abs=1e-12)
    w = [[x.a, x.b, x.eps.real, x.eps.imag] for x in r.res.wires]
    assert got["wires"] == approx(w, 1e-15)
    assert spacing == pytest.approx(r.res.spacing, rel=1e-15, abs=0)
    uniform = np.nan if r.c_uniform is None else r.c_uniform
    assert [c_bare, c_uniform, c_eff] == approx([r.c_bare, uniform, r.c_eff_radius], 1e-14)
    assert got["gap"] == approx(r.gap, 1e-15)
    assert got["sweep_exact"] == approx(r.sweep_exact, 1e-12)  # same convergence decisions
    for key in ["sweep_bare", "sweep_eff"]:
        assert got[key] == approx(getattr(r, key), 1e-14), key
    uniform = np.full_like(r.gap, np.nan) if r.sweep_uniform is None else r.sweep_uniform
    assert got["sweep_uniform"] == approx(uniform, 1e-14)
    # the potential map draw_pair evaluates (1 V across the pair)
    s, (w1, w2) = r.res.spacing, r.res.wires
    bmax = max(w1.b, w2.b)
    x = np.linspace(-s / 2 - w1.b - 1.2 * bmax, s / 2 + w2.b + 1.2 * bmax, 420)
    y = np.linspace(-2.0 * bmax, 2.0 * bmax, 260)
    assert got["field_x"] == approx(x, 1e-15)
    assert got["field_y"] == approx(y, 1e-15)
    xx, yy = np.meshgrid(x, y)
    assert np.abs(got["phi"] - r.res.potential(xx, yy).real).max() <= 1e-12


PAIR_ERRORS = {
    "sleeves overlap": gp.PairParams(spacing_ref=CENTRE, spacing_mm=1.0),
    "conductor Ø 0": gp.PairParams(w1=gp.WireParams(0.0, 1.5)),
    "insulation < conductor": gp.PairParams(w1=gp.WireParams(1.0, 0.8)),
    "eps_r < 1": gp.PairParams(w1=gp.WireParams(1.0, 1.5, Material.CUSTOM, 0.5)),
    "bare conductors touch": gp.PairParams(w1=BARE_WIRE, spacing_ref=CENTRE, spacing_mm=1.0),
}


@pytest.mark.parametrize("name", PAIR_ERRORS)
def test_pair_invalid_input_is_an_error(port, name):
    p = PAIR_ERRORS[name]
    with pytest.raises(ValueError):
        gp.compute_pair(p)
    with pytest.raises(ValueError):
        call(port, p)
