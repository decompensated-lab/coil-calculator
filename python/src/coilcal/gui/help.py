"""Tooltips and the in-app guide."""

TIPS = {
    # coil geometry
    "wire": "Bare conductor diameter. The skin-effect resistance and internal inductance use it.",
    "pitch": "Axial distance between the centres of adjacent turns (Coil64 'p'). "
    "Must be ≥ the wire diameter.",
    "former": "Outer diameter of the coil form. Wire centres sit at former/2 + insulated Ø/2.",
    "ins_d": "Outer diameter over the insulation (Coil64's 'wire diameter with insulation'). "
    "Equal to the wire Ø means bare wire. Changing the wire Ø keeps the insulation thickness. "
    "Typical enamel on 1 mm wire: 1.04–1.09 mm.",
    "ins_mat": "Insulation material: fills εr and tan δ with typical values around 1 MHz "
    "(edit them for datasheet values; the preset then shows 'custom'). The insulation is a "
    "dielectric sleeve that raises the turn-to-turn capacitance.",
    "ins_eps": "Relative permittivity of the wire insulation.",
    "ins_tand": "Loss tangent of the insulation. It makes the capacitance lossy, which lowers "
    "Q near self-resonance.",
    "former_wall": "Radial wall thickness of the former tube (inward from the former Ø).",
    "former_overhang": "How far the former tube extends beyond the winding at each end. Coils "
    "with the same former settings whose tubes meet are treated as one shared tube.",
    "former_mat": "Former material. 'air / none' removes the former from the electrostatics "
    "(the former Ø still sets the winding radius). The former's dielectric raises the coil's "
    "self-capacitance and lowers its SRF.",
    "former_eps": "Relative permittivity of the former.",
    "former_tand": "Loss tangent of the former material.",
    "turns": "Number of turns. The model has one lumped branch per turn.",
    "ground": "How this coil's terminals relate to the reference (the coax shield / VNA ground)."
    "\n• end/start grounded: that terminal is on the shield (single-ended).\n• floating: "
    "neither terminal touches the shield (balanced feed, e.g. through a balun).\n"
    "Used by the Impedance/Transfer tabs and the 'A on P1, B on P2' VNA setup. In the "
    "series-thru setup both terminals go to centre conductors, so this is ignored.",
    # placement
    "gap_ref": "Reference for the axial gap:\n• edge-to-edge: 0 = windings just touching end to end"
    " (one pitch apart).\n• centre-to-centre: 0 = B centred on A (nested). Nesting needs the radii"
    " to differ by more than one wire diameter plus the lateral offset.",
    "gap": "Axial position of coil B along A's axis, measured as set by 'gap reference'.",
    "offset": "Lateral (x) displacement of B's axis from A's axis; the axes stay parallel.",
    # analysis
    "f_min": "Lowest frequency of the sweep (logarithmic spacing).",
    "f_max": "Highest frequency of the sweep.",
    "n_freq": "Number of sweep points. The view frequency is always included exactly.",
    "f_view": "Frequency used by the summary, the cross-section fill, the turn-current plot, "
    "the side view and the Bz profiles. It is marked by a grey line in the sweep plots. Keep "
    "it well below the first resonance to read L_eff and X/R.",
    "z_load": "Load on coil B for the 'into load' transfer curve (Transfer tab).",
    "r_factor": "Multiplier on the isolated-wire skin-effect resistance, to account for "
    "the proximity effect between turns (not computed). Rough guide: ~1.2–1.5 for pitch ≈ 2·d, "
    "up to 2–3 for touching turns.",
    "coupling": "Diagnostic: keep both inter-coil coupling paths (full), only the magnetic one "
    "(mutual inductance), or only the electric one (inter-coil capacitance).",
    "fill": "What colours the wire circles in the cross-section: turn current magnitude, turn "
    "potential magnitude, or nothing. Values are for the selected VNA drive.",
    "x_line_z": "Height z (along coil A's axis) of the horizontal cut used for the Bz(x) "
    "profile in the 'Bz profiles' tab. 0 = centre of coil A.",
    # vna
    "vna_setup": "VNA configuration used by the VNA tab, side-view field, cross-section fill and "
    "turn-current plot:\n• A on P1, B on P2: each coil is a one-port (terminal setting decides "
    "which end is on the shield); S21 is the coupling.\n• series-thru: the coil sits between "
    "the centre conductors of P1 and P2 (good for high impedances).\n• shunt-thru: the coil goes"
    " from the joined P1/P2 centre line to ground (good for low impedances).\nIn the thru setups"
    " the coil is measured alone.",
    "z0": "Reference impedance of the VNA ports (also their source and load impedance).",
    "p_dbm": "Available source power at port 1. It sets the absolute currents and fields "
    "(incident peak voltage V+ = √(2·Z0·P)). All other ports are terminated in Z0.",
    "drive": "How the drive level is given:\n"
    "• source power: the available power at port 1, as on a VNA.\n"
    "• port 1 current: the source is scaled so that the current into port 1 at the view "
    "frequency has the set peak value; the summary shows the power this needs.",
    "i_drive": "Peak current into port 1 at the view frequency. In the 'A on P1, B on P2' and "
    "series-thru setups this is the current into the coil's terminal; in shunt-thru part of "
    "it goes into port 2's termination.",
    # wire pair tab
    "pair_cond": "Diameter of the bare conductor.",
    "pair_ins": "Outer diameter over the insulation (Coil64's 'wire diameter with insulation'). "
    "Equal to the conductor Ø means bare wire.",
    "pair_material": "Insulation material preset: fills εr and tan δ with typical values around "
    "1 MHz. Datasheet values vary, so edit εr / tan δ (the preset then shows 'custom').",
    "pair_eps": "Relative permittivity of the insulation sleeve. Space outside the sleeves is "
    "air (εr = 1).",
    "pair_tand": "Dielectric loss tangent of the insulation. The result is an effective tan δ of "
    "the line, smaller because part of the field is in air, and a shunt conductance G′ = ωC′tanδ.",
    "pair_same": "Tick to give wire 2 its own conductor, insulation and material. Unticked, "
    "wire 2 is identical to wire 1.",
    "pair_ref": "How the spacing is given:\n• insulation surface gap: 0 = sleeves touching.\n"
    "• centre-to-centre: the distance between the conductor axes (e.g. the coil pitch).\n"
    "Changing the reference converts the number so the geometry stays the same.",
    "pair_spacing": "Distance between the wires, measured as set by 'reference'. The sleeves may "
    "touch but not overlap.",
    "pair_from_a": "Copy coil A's wire Ø to both conductors (keeping the insulation thickness) "
    "and set the centre-to-centre spacing to coil A's pitch: the 2-D turn-to-turn problem of "
    "the coil, without the curvature and the other turns.",
}

TAB_TIPS = {
    "Cross-section": "The windings drawn as rows of wire cross-sections at true wire size and "
    "pitch, cropped to the winding. Fill = turn current or voltage for the VNA drive.",
    "Side view": "Both coils in the x–z plane with the magnetic field at the view frequency "
    "for the selected VNA setup and source power. Colour = |B| peak amplitude; lines = field "
    "direction at the phase of maximum field.",
    "Bz profiles": "Axial field component Bz along coil A's axis (vs z) and across the coils "
    "(vs x at the chosen height). Shows the in-phase part for the selected VNA drive; dotted "
    "= the same coils with uniform current, i.e. the quasi-DC field shape.",
    "Impedance": "Input impedance of each coil (other coil open) versus frequency, with the "
    "quasi-DC approximation R(f) + jωL dotted. The lower panel is the apparent inductance "
    "relative to L_DC.",
    "Transfer A→B": "Open-circuit voltage in B per ampere in A (Z21) compared with the "
    "quasi-static jωM, and the voltage into the chosen load.",
    "VNA": "S-parameters of the selected VNA setup: magnitude (dB), phase and Smith chart.",
    "Wire pair C": "Stand-alone calculator: capacitance per unit length between two long "
    "parallel round wires with dielectric insulation, surrounded by air. Exact 2-D multipole "
    "solution, with field map, C′ vs spacing, and the pair viewed as a two-wire line.",
    "Turn currents": "Current in each turn and voltage at each node for the selected VNA drive. "
    "Near self-resonance the internal current can far exceed the terminal current.",
}

GUIDE_HTML = """
<h2>coilcal: turn-level coil model</h2>
<p>Single-layer coils are described the way Coil64 does it (wire Ø, pitch, former Ø, turns).
Every turn is a lumped circuit branch. It is coupled to every other turn, in both coils,
through</p>
<ul>
<li>the exact <b>turn-to-turn inductance matrix</b> (Maxwell's formula / ring vector potential),
plus skin-effect resistance and internal inductance per turn;</li>
<li>the <b>turn-to-turn capacitance matrix</b> from an electrostatic charge-simulation solver
(it resolves charge crowding between neighbouring wires).</li>
</ul>
<p>The capacitance includes the wire insulation (a dielectric sleeve around each turn) and
the former (a dielectric tube under the winding), both with dielectric loss (tan δ).</p>
<p>Solving this network over frequency gives self-resonance, non-uniform current along the
winding, and both inductive and capacitive coupling between coils. Each turn is assumed much
shorter than a wavelength (fine to ~100 MHz for a 150 mm coil). Radiation, the proximity
effect (use <i>R factor</i>) and nearby metal are not modelled. When the coils are not
coaxial, each coil's former only acts on its own winding.</p>
<h3>Tabs</h3>
<ul>
<li><b>Impedance / Transfer</b>: open-circuit Z-parameters of the A/B pair. They don't depend
on the VNA fixture. Dotted lines are the quasi-DC model.</li>
<li><b>VNA</b>, <b>Side view</b>, <b>Bz profiles</b>, <b>Cross-section</b> fill and <b>Turn
currents</b> follow the selected <i>VNA setup</i>. Port 1 is driven with the chosen power; all
ports are terminated in Z0.</li>
</ul>
<h3>Wire pair C</h3>
<p>A separate calculator for two long, parallel, insulated wires in air: the capacitance per
unit length, effective loss tangent, and the pair's impedance and velocity factor as a two-wire line.
The dielectric sleeve and the surrounding air are both modelled (multipole expansion, exact up to
series truncation), so the result lies between the bare-wire value and εr times it. It does not
change the coil model above.</p>
<h3>Summary panel</h3>
<ul>
<li><b>L<sub>eff</sub></b> = Im Z<sub>in</sub>/ω and <b>X/R</b> at the view frequency come from
the network. Near or above a resonance, of this coil or of a coupled one, they no longer mean
inductance or Q, so they are hidden.</li>
<li><b>Q<sub>L</sub></b> = ωL<sub>DC</sub>/R<sub>ac</sub>: copper-only Q, valid well below
resonance.</li>
<li><b>f<sub>SRF</sub>, Q<sub>SRF</sub></b>: first parallel resonance of the coil alone and its
resonator Q. That Q includes conductor and dielectric loss; R<sub>p</sub> is |Z| at
resonance.</li>
<li><b>f<sub>res</sub></b>: the same resonance with the other coil present (open).</li>
<li><b>f<sub>SRF</sub> without dielectrics</b>: the same coil with vacuum insulation and no
former. <b>Medhurst</b>: the empirical estimate, for comparison.</li>
</ul>
<p>When measuring with a VNA, calibrate at the coil terminals: about 100 pF/m of
uncompensated coax adds straight to the coil's capacitance.</p>
<h3>Conventions</h3>
<p>Phasors are peak amplitudes. Positive current circulates counter-clockwise about +z
(right-hand rule: field along +z inside). Z21 is the open-circuit voltage at B per ampere into
A. S = (Z − Z0)(Z + Z0)<sup>−1</sup>.</p>
<p>Hover over any control or tab for details.</p>
<h3>Credits</h3>
<p>coilcal was inspired by <a href="https://coil32.net">Coil64</a> and its predecessor Coil32,
and describes a coil the way they do. The Python library and desktop app are built on NumPy,
SciPy, Magpylib, Matplotlib and Qt for Python. The browser app is built on Svelte, uPlot and
KaTeX and set in JetBrains Mono; its model is a Rust port of the Python code and includes
routines ported from Magpylib and SciPy.</p>
<p>The methods go back to Maxwell (coaxial-loop mutual inductance), Nagaoka and Rosa
(current-sheet inductance and round-wire corrections, with Knight's fit), Wheeler, Medhurst
(empirical self-capacitance), Singer, Steinbigler and Weiss (charge simulation), and Ortner,
Leitner and Slanovc (field of a current loop).</p>
<p>Source code, the full list of references and all licences:
<a href="https://github.com/ivan-galinskiy/coil-calculator">github.com/ivan-galinskiy/coil-calculator</a>.
coilcal is free software under the MIT licence and comes without warranty: check its
predictions against a measurement before relying on them.</p>
"""
