"""Built-in symbol library: IEC 60617 (= NBN EN 60617) style graphical symbols for single line
diagrams of residential (Belgian RGIE/AREI "eendraadschema" / "schéma unifilaire") and
industrial / commercial LV-MV installations.

A symbol is plain JSON-serialisable data:

    {"id", "name", "category", "prefix", "keywords",
     "prims":     [ {"t": "line"|"poly"|"rect"|"circle"|"arc"|"text", ...} ],
     "terminals": [ {"x", "y", "d": [dx, dy], "n": "name"} ],
     "attrs":     [ {"key", "default"} ]}

Coordinates are local, in mm, origin at the symbol's insertion point, y pointing down.
Terminals sit on the 5 mm grid so wires always land on grid points (a test enforces this).
`keywords` holds English / Dutch / French search terms (e.g. "automaat disjoncteur").
The symbol ids of earlier versions are unchanged.
"""

import math


# ----------------------------------------------------------------- primitives
def L(x1, y1, x2, y2, **k):
    return {"t": "line", "x1": x1, "y1": y1, "x2": x2, "y2": y2, **k}


def PL(pts, closed=False, fill=False, **k):
    return {"t": "poly", "pts": [list(p) for p in pts], "closed": closed, "fill": fill, **k}


def R(x, y, w, h, fill=False, **k):
    return {"t": "rect", "x": x, "y": y, "w": w, "h": h, "fill": fill, **k}


def C(cx, cy, r, fill=False, **k):
    return {"t": "circle", "cx": cx, "cy": cy, "r": r, "fill": fill, **k}


def A(cx, cy, r, a0, a1, **k):
    return {"t": "arc", "cx": cx, "cy": cy, "r": r, "a0": a0, "a1": a1, **k}


def T(x, y, s, size=3.5, bold=False, **k):
    return {"t": "text", "x": x, "y": y, "s": s, "size": size, "bold": bold, **k}


def TERM(x, y, dx, dy, n=""):
    return {"x": x, "y": y, "d": [dx, dy], "n": n}


def SYM(id, name, category, prefix, prims, terminals, attrs=(), kw="", builtin=True):
    return {
        "id": id, "name": name, "category": category, "prefix": prefix, "keywords": kw,
        "prims": prims, "terminals": terminals,
        "attrs": [{"key": k, "default": d} for k, d in attrs],
        "builtin": builtin,
    }


# ------------------------------------------------------------ shared pieces
def _earth(y, w=5):
    """Three decreasing bars below y (IEC earth symbol)."""
    return [L(-w, y, w, y), L(-w * 0.6, y + 2.5, w * 0.6, y + 2.5), L(-w * 0.2, y + 5, w * 0.2, y + 5)]


def _vert(n1="1", n2="2", h=10):
    return [TERM(0, -h, 0, -1, n1), TERM(0, h, 0, 1, n2)]


def _blade():
    """Open switch between terminals (0,-10) and (0,10): fixed contact on top, blade pivots at bottom."""
    return [L(0, -10, 0, -5), L(-2.5, -5, 2.5, -5), L(0, 5, -4, -4), L(0, 5, 0, 10)]


_BK = math.hypot(4, 9)
_BU = (-4 / _BK, -9 / _BK)           # unit vector along the blade (pivot -> tip)
_BN = (9 / _BK, -4 / _BK)            # unit normal
_MID = (-2.0, 0.5)                   # blade mid-point


def _cross(cx=-4.0, cy=-4.0, r=2.5):
    """The 'x' on the blade tip that marks a circuit breaker (auto-tripping switch)."""
    return [L(cx - r, cy - r, cx + r, cy + r), L(cx - r, cy + r, cx + r, cy - r)]


def _bar_at_tip():
    """Bar across the blade tip = switch-disconnector (on-load switching)."""
    return [L(-6.5, -4, -1.5, -4)]


def _toroid_with_link():
    """Residual-current (differential) element: toroid on the load side + dashed link to the mechanism."""
    return [C(0, 7.5, 2.5), PL([(2.5, 7.5), (6, 7.5), (6, 0.5), (-1.2, 0.5)], dash=True)]


def _trip_box():
    """Small thermal-magnetic release box next to the blade (miniature circuit breakers)."""
    return [R(2, -2, 4.5, 4), PL([(3, 1), (3, -1), (5.5, -1)])]


def _fuse_on_blade():
    p0 = (0 + _BU[0] * 1.5, 5 + _BU[1] * 1.5)
    p1 = (0 + _BU[0] * 8.5, 5 + _BU[1] * 8.5)
    w = 1.4
    return [PL([(p0[0] + _BN[0] * w, p0[1] + _BN[1] * w), (p1[0] + _BN[0] * w, p1[1] + _BN[1] * w),
                (p1[0] - _BN[0] * w, p1[1] - _BN[1] * w), (p0[0] - _BN[0] * w, p0[1] - _BN[1] * w)], closed=True)]


def _meter(letter, name, prefix, kw, size=5, ts=None):
    return SYM(name.lower().replace(" ", "_"), name, "Measurement & Metering", prefix,
               [L(0, -10, 0, -5), C(0, 0, 5), L(0, 5, 0, 10), T(0, 0, letter, ts or size, True)],
               _vert(), [], kw)


def build():
    S = []
    add = S.append

    # ================================================== SOURCES & STORAGE
    cat = "Sources & Storage"
    add(SYM("utility", "Utility / Grid Connection", cat, "UT",
            [R(-10, -10, 20, 20), L(0, 10, 0, 15),
             PL([(-4, -7), (3, -1.5), (-3, 1.5), (3, 6)]),
             PL([(3, 8), (0.2, 4.6), (5.4, 4.0)], closed=True, fill=True)],
            [TERM(0, 15, 0, 1, "1")], [("Voltage", "11 kV"), ("Fault level", "250 MVA")],
            "net netaansluiting distributienet réseau raccordement grid supply feeder source"))
    add(SYM("grid_lv", "LV Grid Connection (230/400 V)", cat, "NET",
            [R(-7.5, -7.5, 15, 15), L(0, 7.5, 0, 10), T(0, -2.2, "230/400", 2.6, True), T(0, 2.5, "50 Hz", 2.6)],
            [TERM(0, 10, 0, 1, "1")], [("Supply", "3N~ 230/400 V"), ("Earthing", "TT")],
            "aansluiting net netbeheerder fluvius ores raccordement basse tension laagspanning residential"))
    add(SYM("generator", "Generator", cat, "G",
            [C(0, 0, 10), T(0, -2, "G", 6, True), T(0, 5.5, "3~", 2.8)],
            [TERM(0, 10, 0, 1, "1")], [("Rating", "500 kVA"), ("Voltage", "0.4 kV")],
            "generator groupe électrogène noodgenerator aggregaat stroomgroep"))
    add(SYM("pv", "PV Array", cat, "PV",
            [R(-10, -10, 20, 20), L(-10, 10, 10, -10), L(0, 10, 0, 15), T(-4.5, -5, "PV", 3.2, True)],
            [TERM(0, 15, 0, 1, "1")], [("Rating", "100 kWp"), ("Voltage", "800 V DC")],
            "zonnepanelen photovoltaic photovoltaïque panneaux solaires"))
    add(SYM("battery", "Battery", cat, "BAT",
            [L(0, -10, 0, -3), L(-5, -3, 5, -3), L(-2.5, -1, 2.5, -1), L(-5, 1, 5, 1), L(-2.5, 3, 2.5, 3), L(0, 3, 0, 10)],
            _vert(), [("Capacity", "100 Ah"), ("Voltage", "110 V DC")], "accu batterij batterie dc"))
    add(SYM("bess", "Battery Storage (BESS)", cat, "BESS",
            [R(-10, -7.5, 20, 15), L(0, -15, 0, -7.5), L(-4, -2, 4, -2), L(-2, 0.5, 2, 0.5), L(-4, 3, 4, 3),
             L(0, 7.5, 0, 15), T(6.5, -4.5, "+", 2.5)],
            [TERM(0, -15, 0, -1, "DC"), TERM(0, 15, 0, 1, "AC")],
            [("Capacity", "10 kWh"), ("Power", "5 kW")], "thuisbatterij batterie domestique opslag stockage storage accu"))
    add(SYM("inverter", "Inverter (DC/AC)", cat, "INV",
            [R(-10, -10, 20, 20), L(-10, 10, 10, -10), L(0, -15, 0, -10), L(0, 10, 0, 15),
             T(-4.5, -5, "=", 5), T(4.5, 5, "~", 5)],
            [TERM(0, -15, 0, -1, "DC"), TERM(0, 15, 0, 1, "AC")], [("Rating", "100 kVA")],
            "omvormer onduleur pv inverter dc ac"))
    add(SYM("rectifier", "Rectifier / Charger (AC/DC)", cat, "CH",
            [R(-10, -10, 20, 20), L(-10, 10, 10, -10), L(0, -15, 0, -10), L(0, 10, 0, 15),
             T(-4.5, -5, "~", 5), T(4.5, 5, "=", 5)],
            [TERM(0, -15, 0, -1, "AC"), TERM(0, 15, 0, 1, "DC")], [("Rating", "50 kW")],
            "gelijkrichter redresseur lader chargeur"))
    add(SYM("ups", "UPS", cat, "UPS",
            [R(-10, -7.5, 20, 15), L(0, -15, 0, -7.5), L(0, 7.5, 0, 15), T(0, 0, "UPS", 4.5, True)],
            [TERM(0, -15, 0, -1, "IN"), TERM(0, 15, 0, 1, "OUT")], [("Rating", "20 kVA")],
            "onderbrekingsvrije voeding alimentation sans interruption ononderbroken"))
    add(SYM("changeover", "Changeover Switch (I-0-II / ATS)", cat, "ATS",
            [L(-5, -10, -5, -5), L(5, -10, 5, -5), L(-7, -5, -3, -5), L(3, -5, 7, -5),
             L(0, 5, -4.5, -4), L(0, 5, 0, 10), T(-8.5, -8.5, "I", 2.4), T(8.5, -8.5, "II", 2.4)],
            [TERM(-5, -10, 0, -1, "I"), TERM(5, -10, 0, -1, "II"), TERM(0, 10, 0, 1, "OUT")],
            [("Rating", "100 A"), ("Poles", "4P")],
            "omschakelaar inverseur commutateur transfer ats generator net"))

    # ======================================================= TRANSFORMERS
    cat = "Transformers"
    two_w = [C(0, -5, 10), C(0, 5, 10)]
    add(SYM("trafo2", "Transformer 2-winding", cat, "TR", two_w,
            [TERM(0, -15, 0, -1, "HV"), TERM(0, 15, 0, 1, "LV")],
            [("Rating", "1000 kVA"), ("Voltage", "11/0.4 kV"), ("Vector group", "Dyn11"), ("Impedance", "6 %")],
            "transformator transformateur trafo"))
    add(SYM("trafo_dyn", "Transformer Delta-Star (Dyn)", cat, "TR",
            two_w + [PL([(0, -9), (-3.2, -3.5), (3.2, -3.5)], closed=True),
                     L(0, 5, 0, 1.2), L(0, 5, -3.2, 6.8), L(0, 5, 3.2, 6.8), L(0, 5, 0, 5)],
            [TERM(0, -15, 0, -1, "HV"), TERM(0, 15, 0, 1, "LV")],
            [("Rating", "1000 kVA"), ("Voltage", "11/0.4 kV"), ("Vector group", "Dyn11"), ("Impedance", "6 %")],
            "driehoek ster triangle étoile dyn11 distribution transformer"))
    add(SYM("trafo2_oltc", "Transformer with OLTC", cat, "TR",
            two_w + [L(-9, 10, 9, -10), PL([(9, -10), (5.2, -8.6), (7.6, -5.8)], closed=True, fill=True)],
            [TERM(0, -15, 0, -1, "HV"), TERM(0, 15, 0, 1, "LV")],
            [("Rating", "10 MVA"), ("Voltage", "33/11 kV"), ("Vector group", "Dyn11"), ("Tap range", "+/-10 %")],
            "regelbare trappenschakelaar changeur de prise on load tap changer"))
    add(SYM("trafo3", "Transformer 3-winding", cat, "TR",
            [C(-5, -5, 7.5), C(5, -5, 7.5), C(0, 5, 7.5), L(-5, -12.5, -5, -15), L(5, -12.5, 5, -15), L(0, 12.5, 0, 15)],
            [TERM(-5, -15, 0, -1, "HV"), TERM(5, -15, 0, -1, "MV"), TERM(0, 15, 0, 1, "LV")],
            [("Rating", "20 MVA"), ("Voltage", "132/33/11 kV"), ("Vector group", "YNyn0d1")],
            "driewikkelingstransformator trois enroulements"))
    add(SYM("autotrafo", "Auto-transformer", cat, "AT",
            [C(0, 0, 7.5), L(0, -10, 0, -7.5), L(0, 7.5, 0, 10), L(-7.5, 0, -10, 0),
             L(0, -3, 0, 3)],
            [TERM(0, -10, 0, -1, "1"), TERM(0, 10, 0, 1, "2")], [("Rating", "100 kVA"), ("Ratio", "400/230 V")],
            "spaartransformator autotransformateur"))
    add(SYM("trafo_bell", "Isolating / Safety Transformer", cat, "TRS",
            [L(0, -10, 0, -7.5), C(0, -2.5, 5), C(0, 2.5, 5), L(0, 7.5, 0, 10)],
            _vert(), [("Rating", "40 VA"), ("Voltage", "230/12 V")],
            "scheidingstransformator belltransformator beltransformator transformateur de sonnerie TBTS SELV"))

    # ============================================================ SWITCHGEAR
    cat = "Switchgear"
    sw = _blade()
    add(SYM("cb", "Circuit Breaker", cat, "CB", sw + _cross(), _vert(),
            [("Rating", "630 A"), ("Breaking cap.", "50 kA")], "vermogenschakelaar disjoncteur breaker mccb"))
    add(SYM("acb", "Air Circuit Breaker (draw-out)", cat, "ACB",
            sw + _cross() + [PL([(-2, -8.2), (0, -7), (2, -8.2)]), PL([(-2, 7), (0, 8.2), (2, 7)])], _vert(),
            [("Rating", "3200 A"), ("Breaking cap.", "65 kA"), ("Trip unit", "LSI")],
            "uitneembaar débrochable withdrawable acb powerbreaker"))
    add(SYM("disconnector", "Disconnector / Isolator", cat, "DS", sw, _vert(), [("Rating", "630 A")],
            "scheider sectionneur isolator isolateur"))
    add(SYM("lbs", "Switch-disconnector (load break)", cat, "LBS", sw + _bar_at_tip(), _vert(), [("Rating", "630 A")],
            "lastscheider interrupteur sectionneur load break hoofdschakelaar"))
    add(SYM("fuse_switch", "Fuse-switch Disconnector", cat, "QF", sw + _fuse_on_blade(), _vert(),
            [("Rating", "250 A"), ("Fuse", "NH gG")], "zekeringlastscheider interrupteur sectionneur à fusibles nh"))
    add(SYM("fuse", "Fuse", cat, "F", [L(0, -10, 0, 10), R(-2.5, -7.5, 5, 15)], _vert(), [("Rating", "100 A gG")],
            "zekering smeltveiligheid fusible"))
    add(SYM("contactor", "Contactor", cat, "K", sw + [A(_MID[0], _MID[1], 2.5, 90, 270)], _vert(),
            [("Rating", "AC3 63 A")], "relais contacteur schakelrelais"))
    add(SYM("earth_switch", "Earthing Switch", cat, "ES",
            [L(0, -10, 0, -5), L(-2.5, -5, 2.5, -5), L(0, 5, -4, -4), L(0, 5, 0, 10)] + _earth(10),
            [TERM(0, -10, 0, -1, "1")], [], "aardingsschakelaar sectionneur de terre"))
    add(SYM("surge", "Surge Protective Device (SPD)", cat, "SPD",
            [L(0, -10, 0, -7.5), R(-2.5, -7.5, 5, 10),
             PL([(-1.5, -3), (1.5, -3), (0, 0.5)], closed=True, fill=True), L(0, 2.5, 0, 6)] + _earth(6),
            [TERM(0, -10, 0, -1, "1")], [("Type", "T2"), ("Uc / In", "275 V / 20 kA")],
            "overspanningsbeveiliging parafoudre surge arrester spd bliksem"))

    # ===================================== RESIDENTIAL & COMMERCIAL PROTECTION
    cat = "LV Protection (residential / RGIE)"
    add(SYM("mcb", "Miniature Circuit Breaker (MCB)", cat, "Q",
            sw + _cross() + _trip_box(), _vert(),
            [("Rating", "16 A"), ("Curve", "B"), ("Icn", "6 kA")],
            "automaat disjoncteur divisionnaire installatieautomaat mcb kleinautomaat"))
    add(SYM("service_cb", "Service-entry Breaker", cat, "Q0",
            sw + _cross() + _trip_box(), _vert(),
            [("Rating", "40 A"), ("Curve", "C"), ("Icn", "10 kA")],
            "aansluitingsautomaat disjoncteur de branchement hoofdautomaat main breaker aansluiting"))
    add(SYM("rcd", "Differential Switch (RCD)", cat, "RCD",
            sw + _bar_at_tip() + _toroid_with_link(), _vert(),
            [("Rating", "40 A"), ("Sensitivity", "30 mA"), ("Type", "A")],
            "differentieel differentieelschakelaar interrupteur différentiel rcd fi aardlek 30ma 300ma"))
    add(SYM("rcd_300", "General Differential 300 mA (RCD)", cat, "RCD",
            sw + _bar_at_tip() + _toroid_with_link(), _vert(),
            [("Rating", "63 A"), ("Sensitivity", "300 mA"), ("Type", "A")],
            "algemeen differentieel différentiel général 300 mA hoofddifferentieel selectief"))
    add(SYM("rcbo", "Differential Breaker (RCBO)", cat, "RCBO",
            sw + _cross() + _toroid_with_link(), _vert(),
            [("Rating", "16 A"), ("Curve", "C"), ("Sensitivity", "30 mA"), ("Type", "A")],
            "differentieelautomaat disjoncteur différentiel rcbo"))
    add(SYM("main_switch", "Main Switch (hoofdschakelaar)", cat, "S0",
            sw + _bar_at_tip(), _vert(), [("Rating", "63 A"), ("Poles", "4P")],
            "hoofdschakelaar interrupteur général main isolator"))
    add(SYM("meter_box", "Distribution Board (verdeelbord)", cat, "DB",
            [L(0, -10, 0, -5), R(-10, -5, 20, 10), T(0, 0, "DB", 4.5, True)],
            [TERM(0, -10, 0, -1, "1")], [("Rating", "63 A")], "verdeelkast tableau divisionnaire kast coffret"))
    add(SYM("timer", "Time Switch (tijdschakelaar)", cat, "TS",
            [L(0, -10, 0, -5), R(-4, -5, 8, 10), C(0, 0, 2.6), L(0, 0, 0, -1.8), L(0, 0, 1.4, 0.8), L(0, 5, 0, 10)],
            _vert(), [("Rating", "16 A")], "klokschakelaar horloge minuterie timer"))
    add(SYM("contactor_residential", "Modular Contactor (relais)", cat, "K",
            sw + [A(_MID[0], _MID[1], 2.5, 90, 270)] + [R(2, -2, 4.5, 4)], _vert(),
            [("Rating", "25 A"), ("Coil", "230 V")], "teleruptor télérupteur impulsrelais modulaire"))

    # ======================================================= MOTOR CONTROL
    cat = "Motor Control"
    add(SYM("mpcb", "Motor Protection Breaker (MPCB)", cat, "QM",
            sw + _cross() + [R(2, -2, 4.5, 4), PL([(3, 1), (3, -1), (5.5, -1)]), T(9.5, 0, "M", 2.6)], _vert(),
            [("Rating", "25 A"), ("Setting", "16-20 A")],
            "motorbeveiliging disjoncteur moteur motorschutzschalter mpcb"))
    add(SYM("overload", "Thermal Overload Relay", cat, "FR",
            [L(0, -10, 0, -5), R(-3.5, -5, 7, 10), PL([(-1.5, -3), (-1.5, 0), (1.5, 0), (1.5, 3)]), L(0, 5, 0, 10)],
            _vert(), [("Setting", "10-16 A")], "thermisch relais relais thermique overload"))
    add(SYM("softstarter", "Soft Starter", cat, "SS",
            [R(-10, -7.5, 20, 15), L(0, -15, 0, -7.5), L(0, 7.5, 0, 15), PL([(-6, 4), (-1, 4), (4, -3.5)]),
             T(5.5, 3.2, "SS", 2.6, True)],
            [TERM(0, -15, 0, -1, "IN"), TERM(0, 15, 0, 1, "OUT")], [("Rating", "55 kW")],
            "zachte aanloop démarreur progressif softstarter"))
    add(SYM("stardelta", "Star-Delta Starter", cat, "YD",
            [R(-10, -7.5, 20, 15), L(0, -15, 0, -7.5), L(0, 7.5, 0, 15), T(0, 0, "Y/Δ", 4.5, True)],
            [TERM(0, -15, 0, -1, "IN"), TERM(0, 15, 0, 1, "OUT")], [("Rating", "37 kW")],
            "ster driehoek étoile triangle sterdriehoek"))
    add(SYM("vfd", "Variable Frequency Drive", cat, "VFD",
            [R(-10, -7.5, 20, 15), L(0, -15, 0, -7.5), L(0, 7.5, 0, 15), T(0, 0, "VFD", 4.2, True)],
            [TERM(0, -15, 0, -1, "IN"), TERM(0, 15, 0, 1, "OUT")], [("Rating", "75 kW")],
            "frequentieregelaar variateur de fréquence vsd drive"))
    add(SYM("motor", "Motor 3~", cat, "M",
            [C(0, 0, 10), T(0, -2, "M", 6, True), T(0, 5.5, "3~", 2.8)],
            [TERM(0, -10, 0, -1, "1")], [("Rating", "75 kW"), ("Voltage", "0.4 kV")], "motor moteur asynchrone"))
    add(SYM("motor1", "Motor 1~", cat, "M",
            [C(0, 0, 7.5), T(0, -1.5, "M", 5, True), T(0, 3.5, "1~", 2.6), L(0, -10, 0, -7.5)],
            [TERM(0, -10, 0, -1, "1")], [("Rating", "1.1 kW"), ("Voltage", "230 V")], "eenfasige motor moteur monophasé"))
    add(SYM("estop", "Emergency Stop", cat, "ES",
            [L(0, -10, 0, -5), L(0, 5, 0, 10), L(-4, 0, -4, -5), L(0, 5, -4, 0), A(-4, -5, 2.5, 180, 360)],
            _vert(), [], "noodstop arrêt d'urgence emergency stop"))
    add(SYM("pushbutton", "Push-button", cat, "SB",
            [L(0, -5, 0, -2.5), L(-2, -2.5, 2, -2.5), L(0, 5, 0, 2.5), L(0, 2.5, -2.5, -1.8), L(-1.3, 0.8, -4.5, 0.8),
             L(-4.5, -1, -4.5, 2.6)],
            [TERM(0, -5, 0, -1, "1"), TERM(0, 5, 0, 1, "2")], [], "drukknop bouton poussoir push button"))
    add(SYM("pilot", "Signal Lamp", cat, "H",
            [L(0, -10, 0, -3.5), C(0, 0, 3.5), L(-2.47, -2.47, 2.47, 2.47), L(-2.47, 2.47, 2.47, -2.47), L(0, 3.5, 0, 10)],
            _vert(), [("Colour", "Green")], "signaallamp lampe de signalisation indicator"))

    # ================================================== MEASUREMENT & METERING
    cat = "Measurement & Metering"
    add(SYM("ct", "Current Transformer", cat, "CT",
            [L(0, -10, 0, 10), C(0, 0, 3.5)], _vert(), [("Ratio", "400/5 A"), ("Class", "5P10")],
            "stroomtransformator transformateur de courant ta"))
    add(SYM("ct_core", "Core-balance CT (earth fault)", cat, "CBCT",
            [L(0, -10, 0, 10), C(0, 0, 3.5), C(0, 0, 2.2), T(6.5, 0, "I₀", 2.6)], _vert(),
            [("Ratio", "100/1 A")], "aardlektransformator tore homopolaire zero sequence"))
    add(SYM("vt", "Voltage Transformer", cat, "VT",
            [L(0, -10, 0, -5), C(0, 0, 5), C(0, 5, 5)], [TERM(0, -10, 0, -1, "1")],
            [("Ratio", "11000/110 V"), ("Class", "0.5")], "spanningstransformator transformateur de tension tp"))
    add(SYM("ammeter", "Ammeter", cat, "A", [L(0, -10, 0, -5), C(0, 0, 5), L(0, 5, 0, 10), T(0, 0, "A", 5, True)], _vert(), [],
            "ampèremeter ampèremètre stroommeter"))
    add(SYM("voltmeter", "Voltmeter", cat, "V", [L(0, -10, 0, -5), C(0, 0, 5), L(0, 5, 0, 10), T(0, 0, "V", 5, True)], _vert(), [],
            "voltmeter voltmètre spanningsmeter"))
    add(SYM("wattmeter", "Wattmeter", cat, "W", [L(0, -10, 0, -5), C(0, 0, 5), L(0, 5, 0, 10), T(0, 0, "W", 5, True)], _vert(), [],
            "wattmeter wattmètre vermogen"))
    add(SYM("freqmeter", "Frequency Meter", cat, "Hz", [L(0, -10, 0, -5), C(0, 0, 5), L(0, 5, 0, 10), T(0, 0, "Hz", 3.6, True)], _vert(), [],
            "frequentiemeter fréquencemètre hertz"))
    add(SYM("pfmeter", "Power Factor Meter", cat, "PF", [L(0, -10, 0, -5), C(0, 0, 5), L(0, 5, 0, 10), T(0, 0, "cosφ", 2.7, True)], _vert(), [],
            "arbeidsfactor facteur de puissance cos phi cosinusphi"))
    add(SYM("kwh", "Energy Meter (kWh)", cat, "KWH",
            [L(0, -10, 0, -5), R(-6, -5, 12, 10), L(0, 5, 0, 10), T(0, 0, "kWh", 3.2)], _vert(), [("Class", "1")],
            "kwh teller compteur energiemeter elektriciteitsmeter"))
    add(SYM("smart_meter", "Digital Meter (import / export)", cat, "KWH",
            [L(0, -10, 0, -5), R(-7.5, -5, 15, 10), L(0, 5, 0, 10), T(0, -1.6, "kWh", 3), T(0, 2.6, "⇄", 3.6)], _vert(),
            [("Type", "Digital 3N~"), ("Rating", "63 A")],
            "digitale meter slimme meter compteur communicant injectie afname import export net metering"))
    add(SYM("mfm", "Multifunction Meter", cat, "MFM",
            [L(0, -10, 0, -5), R(-7.5, -5, 15, 10), L(0, 5, 0, 10), T(0, 0, "MFM", 3.4, True)], _vert(), [("Interface", "Modbus")],
            "netanalyser analyseur de réseau power analyser"))

    # ======================================================= PROTECTION RELAYS
    cat = "Protection Relays"

    def relay(id, name, text, size, kw, func):
        return SYM(id, name, cat, "PR",
                   [L(0, -10, 0, -5), R(-7.5, -5, 15, 10), L(0, 5, 0, 10), T(0, 0, text, size, True)], _vert(),
                   [("ANSI / function", func), ("Setting", "")], kw)

    add(relay("relay", "Protection Relay", "R", 5, "beveiligingsrelais relais de protection", "50/51"))
    add(relay("relay_oc", "Overcurrent Relay", "I>", 4.4, "overstroom surintensité 50 51", "50/51"))
    add(relay("relay_ef", "Earth-fault Relay", "I₀>", 4, "aardsluiting défaut terre 50N 51N", "50N/51N"))
    add(relay("relay_diff", "Differential Relay", "ΔI", 4.4, "differentieelbeveiliging différentielle 87", "87T"))
    add(relay("relay_uv", "Voltage Relay", "U<>", 4, "spanningsrelais minimum maximum 27 59", "27/59"))

    # ================================================== LOADS - INDUSTRIAL
    cat = "Loads & Distribution"
    add(SYM("load", "Load (arrow)", cat, "L",
            [L(0, -10, 0, 0), PL([(-2.5, -0.5), (2.5, -0.5), (0, 5)], closed=True, fill=True)],
            [TERM(0, -10, 0, -1, "1")], [("Description", ""), ("Rating", "")], "verbruiker belasting charge consumer"))
    add(SYM("db", "Distribution Board", cat, "DB",
            [L(0, -10, 0, -5), R(-10, -5, 20, 10), T(0, 0, "DB", 4.5, True)],
            [TERM(0, -10, 0, -1, "1")], [("Rating", "400 A")], "verdeler tableau panel kast"))
    add(SYM("mdb", "Main Switchboard (MDB)", cat, "MDB",
            [L(0, -10, 0, -7.5), R(-12.5, -7.5, 25, 15), T(0, 0, "MDB", 4.8, True), L(0, 7.5, 0, 10)],
            _vert(), [("Rating", "3200 A")], "hoofdverdeler tableau général hoofdschakelbord main switchboard lv"))
    add(SYM("heater", "Electric Heater / Resistance", cat, "HE",
            [L(0, -10, 0, -5), R(-7.5, -5, 15, 10), PL([(-5, 0), (-3.5, -2.5), (-1.2, 2.5), (1.2, -2.5), (3.5, 2.5), (5, 0)])],
            [TERM(0, -10, 0, -1, "1")], [("Rating", "9 kW")], "verwarming weerstand chauffage résistance"))
    add(SYM("capbank", "Capacitor Bank (PFC)", cat, "CAP",
            [L(0, -10, 0, -7.5), R(-7.5, -7.5, 15, 15), L(0, -7.5, 0, -1.5), L(-4, -1.5, 4, -1.5), L(-4, 1.5, 4, 1.5),
             L(0, 1.5, 0, 7.5), L(0, 7.5, 0, 10)],
            _vert(), [("Rating", "300 kvar"), ("Detuning", "7 %")], "condensatorbatterij compensatie batterie de condensateurs cosphi"))

    # ========================================================== PASSIVE
    cat = "Passive"
    add(SYM("reactor", "Reactor / Inductor", cat, "X",
            [L(0, -10, 0, -7.5), A(0, -5, 2.5, -90, 90), A(0, 0, 2.5, -90, 90), A(0, 5, 2.5, -90, 90), L(0, 7.5, 0, 10)],
            _vert(), [("Rating", "10 mH")], "smoorspoel inductance bobine reactor"))
    add(SYM("resistor", "Resistor", cat, "R", [L(0, -10, 0, -7.5), R(-2.5, -7.5, 5, 15), L(0, 7.5, 0, 10)], _vert(),
            [("Value", "10 ohm")], "weerstand résistance"))
    add(SYM("capacitor", "Capacitor", cat, "C",
            [L(0, -10, 0, -1.5), L(-6, -1.5, 6, -1.5), L(-6, 1.5, 6, 1.5), L(0, 1.5, 0, 10)], _vert(),
            [("Rating", "100 kvar")], "condensator condensateur"))

    # ============================================ RESIDENTIAL: OUTLETS & LIGHTING
    cat = "Outlets, Switches & Lighting"
    sock_arc = lambda cx: [A(cx, -1.5, 3.5, 0, 180), L(cx, -1.5, cx, 4.5)]
    add(SYM("socket", "Socket Outlet (stopcontact)", cat, "S",
            [L(0, -10, 0, -1.5), L(-3.5, -1.5, 3.5, -1.5)] + sock_arc(0),
            [TERM(0, -10, 0, -1, "1")], [("Points", "1"), ("Type", "2P+E 16 A")],
            "stopcontact prise de courant wcd socket outlet contactdoos"))
    add(SYM("socket2", "Double Socket Outlet", cat, "S",
            [L(0, -10, 0, -1.5), L(-7.5, -1.5, 7.5, -1.5)] + sock_arc(-3.75) + sock_arc(3.75),
            [TERM(0, -10, 0, -1, "1")], [("Points", "2"), ("Type", "2P+E 16 A")],
            "dubbel stopcontact double prise"))
    add(SYM("socket3p", "3-phase Socket (CEE)", cat, "S3",
            [L(0, -10, 0, -1.5), L(-3.5, -1.5, 3.5, -1.5)] + sock_arc(0) +
            [L(-1.5, -9, 1.5, -7.5), L(-1.5, -7.5, 1.5, -6), L(-1.5, -6, 1.5, -4.5)],
            [TERM(0, -10, 0, -1, "1")], [("Type", "3P+N+E 16 A")],
            "krachtstroom prise triphasée cee perilex 400v"))
    add(SYM("light", "Light Point (lichtpunt)", cat, "LT",
            [L(0, -10, 0, -5), C(0, 0, 5), L(-3.5355, -3.5355, 3.5355, 3.5355), L(-3.5355, 3.5355, 3.5355, -3.5355)],
            [TERM(0, -10, 0, -1, "1")], [("Points", "1"), ("Power", "")], "lichtpunt lampe éclairage luminaire verlichting light"))
    add(SYM("lighting", "Lighting Load", cat, "LT",
            [L(0, -10, 0, -5), C(0, 0, 5), L(-3.5355, -3.5355, 3.5355, 3.5355), L(-3.5355, 3.5355, 3.5355, -3.5355)],
            [TERM(0, -10, 0, -1, "1")], [("Rating", "10 kW")], "verlichting éclairage lighting group"))
    add(SYM("light_em", "Emergency Light", cat, "NL",
            [L(0, -10, 0, -5), C(0, 0, 5), PL([(0, 0), (-3.5355, -3.5355), (3.5355, -3.5355)], closed=True, fill=True),
             PL([(0, 0), (-3.5355, 3.5355), (3.5355, 3.5355)], closed=True, fill=True)],
            [TERM(0, -10, 0, -1, "1")], [("Autonomy", "1 h")], "noodverlichting éclairage de secours evacuatie"))
    add(SYM("switch1", "Switch (single pole)", cat, "SW",
            [L(0, -5, 0, -2.5), L(-2, -2.5, 2, -2.5), L(0, 5, 0, 2.5), L(0, 2.5, -3, -2), L(-1.8, 0.1, 0.4, -1.4)],
            [TERM(0, -5, 0, -1, "1"), TERM(0, 5, 0, 1, "2")], [("Type", "1P 10 A")], "schakelaar interrupteur enkelpolig"))
    add(SYM("switch2", "Two-way Switch (wissel)", cat, "SW",
            [L(-5, -5, -5, -2.5), L(5, -5, 5, -2.5), L(-6.5, -2.5, -3.5, -2.5), L(3.5, -2.5, 6.5, -2.5),
             L(0, 2.5, -4.5, -2), L(0, 5, 0, 2.5)],
            [TERM(-5, -5, 0, -1, "1"), TERM(5, -5, 0, -1, "2"), TERM(0, 5, 0, 1, "C")], [("Type", "wissel 10 A")],
            "wisselschakelaar va-et-vient two-way"))
    add(SYM("dimmer", "Dimmer", cat, "DIM",
            [L(0, -5, 0, -2.5), L(-2, -2.5, 2, -2.5), L(0, 5, 0, 2.5), L(0, 2.5, -3, -2),
             L(-5, 5, 4, -4), PL([(5, -5), (2.2, -4.2), (4.2, -2.2)], closed=True, fill=True)],
            [TERM(0, -5, 0, -1, "1"), TERM(0, 5, 0, 1, "2")], [("Rating", "300 W")], "dimmer variateur de lumière"))
    add(SYM("motion", "Motion Detector (PIR)", cat, "PIR",
            [L(0, -10, 0, -5), C(0, 0, 5), T(0, 0, "PIR", 2.8, True)], [TERM(0, -10, 0, -1, "1")], [],
            "bewegingsmelder détecteur de mouvement pir"))
    add(SYM("smoke", "Smoke Detector", cat, "SD",
            [L(0, -10, 0, -4.5), C(0, 0, 4.5), T(0, 0, "S", 4.2, True)], [TERM(0, -10, 0, -1, "1")], [("Type", "230 V")],
            "rookmelder détecteur de fumée"))
    add(SYM("bell", "Doorbell / Buzzer", cat, "BL",
            [L(0, -10, 0, -3.5), A(0, 0, 3.5, 180, 360), L(-3.5, 0, 3.5, 0), L(-1.2, 0, -1.2, 1.5), L(1.2, 0, 1.2, 1.5)],
            [TERM(0, -10, 0, -1, "1")], [("Voltage", "12 V")], "deurbel sonnette zoemer"))

    # ============================================== RESIDENTIAL: APPLIANCES
    cat = "Appliances (residential)"

    def box_app(id, name, prefix, text, kw, attrs, size=4.4, w=15, h=15):
        return SYM(id, name, cat, prefix,
                   [L(0, -10, 0, -h / 2), R(-w / 2, -h / 2, w, h), T(0, 0, text, size, True)],
                   [TERM(0, -10, 0, -1, "1")], attrs, kw)

    add(SYM("cooker", "Electric Cooker / Hob", cat, "CK",
            [L(0, -10, 0, -5), R(-7.5, -5, 15, 10), C(-3, -1.8, 1.6), C(3, -1.8, 1.6), C(-3, 2.2, 1.6), C(3, 2.2, 1.6)],
            [TERM(0, -10, 0, -1, "1")], [("Rating", "11 kW"), ("Circuit", "400 V 3N~")], "elektrisch fornuis kookplaat cuisinière plaque induction"))
    add(SYM("oven", "Oven", cat, "OV",
            [L(0, -10, 0, -5), R(-7.5, -5, 15, 10), R(-5, -2.5, 10, 5), L(-5, 0, 5, 0)],
            [TERM(0, -10, 0, -1, "1")], [("Rating", "3.5 kW")], "oven four"))
    add(SYM("boiler", "Water Heater (boiler)", cat, "WH",
            [L(0, -10, 0, -7.5), R(-5, -7.5, 10, 15), PL([(0, -5), (-2.2, -3), (2.2, -1), (-2.2, 1), (2.2, 3), (0, 5)])],
            [TERM(0, -10, 0, -1, "1")], [("Rating", "2.2 kW"), ("Volume", "80 l")], "elektrische boiler chauffe-eau warmwater"))
    add(box_app("washer", "Washing Machine", "WM", "WM", "wasmachine lave-linge", [("Rating", "2.3 kW")]))
    add(box_app("dishwasher", "Dishwasher", "DW", "DW", "vaatwasser lave-vaisselle", [("Rating", "2 kW")]))
    add(box_app("dryer", "Tumble Dryer", "TD", "TD", "droogkast droogtrommel sèche-linge", [("Rating", "2.5 kW")]))
    add(box_app("heatpump", "Heat Pump", "HP", "HP", "warmtepomp pompe à chaleur", [("Rating", "6 kW"), ("Circuit", "400 V 3N~")], w=20))
    add(box_app("airco", "Air Conditioner", "AC", "AC", "airconditioning klimaat climatisation", [("Rating", "2.5 kW")]))
    add(SYM("fan", "Ventilation Unit", cat, "VE",
            [L(0, -10, 0, -6), C(0, 0, 6), L(0, 0, 0, -4), L(0, 0, -3.46, 2), L(0, 0, 3.46, 2)],
            [TERM(0, -10, 0, -1, "1")], [("Rating", "150 W")], "ventilatie ventilation vmc ventilator"))
    add(SYM("pump", "Pump", cat, "P",
            [L(0, -10, 0, -5), C(0, 0, 5), PL([(-2.2, -2.8), (-2.2, 2.8), (3, 0)], closed=True)],
            [TERM(0, -10, 0, -1, "1")], [("Rating", "0.5 kW")], "pomp pompe circulatiepomp"))
    add(SYM("evse", "EV Charging Point", cat, "EV",
            [L(0, -10, 0, -7.5), R(-6, -7.5, 12, 15), T(0, -2.5, "EV", 4, True), A(0, 3, 2.2, 180, 360), L(-2.2, 3, 2.2, 3)],
            [TERM(0, -10, 0, -1, "1")], [("Rating", "11 kW"), ("Circuit", "400 V 3N~")], "laadpaal borne de recharge elektrische wagen ev charger wallbox"))
    add(SYM("appliance", "Appliance (generic)", cat, "AP",
            [L(0, -10, 0, -5), R(-7.5, -5, 15, 10), T(0, 0, "~", 5)],
            [TERM(0, -10, 0, -1, "1")], [("Description", ""), ("Rating", "")], "toestel appareil generic"))

    # ===================================================== EARTHING & JUNCTIONS
    cat = "Earthing & Junctions"
    add(SYM("ground", "Earth", cat, "", [L(0, 0, 0, 5)] + _earth(5), [TERM(0, 0, 0, -1, "1")], [], "aarde terre earth ground"))
    add(SYM("earth_rod", "Earth Electrode (aardingslus / rod)", cat, "RA",
            [L(0, 0, 0, 5)] + _earth(5)[:1] + [PL([(-1, 7.5), (1, 7.5), (1, 14), (0, 16.5), (-1, 14)], closed=True)],
            [TERM(0, 0, 0, -1, "1")], [("Resistance", "< 30 ohm"), ("Type", "Ring / rod")],
            "aardingselektrode aardingslus piquet de terre aardstaaf earth electrode"))
    add(SYM("met", "Main Earthing Terminal (PE bar)", cat, "PE",
            [R(-7.5, -5, 15, 10), T(0, 0, "PE", 4.2, True)], [TERM(0, -5, 0, -1, "1"), TERM(0, 5, 0, 1, "2")], [],
            "hoofdaardingsklem aardingsklem borne principale de terre bar"))
    add(SYM("ner", "Neutral Earthing Resistor", cat, "NER",
            [L(0, -10, 0, -7.5), R(-3, -7.5, 6, 10), L(0, 2.5, 0, 6)] + _earth(6),
            [TERM(0, -10, 0, -1, "1")], [("Rating", "10 ohm 400 A 10 s")], "nulpuntsweerstand résistance de neutre"))
    add(SYM("cable_end", "Cable Termination", cat, "",
            [L(0, -5, 0, -2.5), PL([(-2.5, -2.5), (2.5, -2.5), (0, 2.5)], closed=True, fill=True)],
            [TERM(0, -5, 0, -1, "1")], [], "kabeleinde extrémité de câble termination"))
    add(SYM("junction", "Junction Box / Node", cat, "J",
            [C(0, 0, 1.1, fill=True)],
            [TERM(0, -5, 0, -1, "N"), TERM(0, 5, 0, 1, "S"), TERM(-5, 0, -1, 0, "W"), TERM(5, 0, 1, 0, "E")],
            [], "aftakdoos boîte de dérivation verbinding knooppunt node"))
    # junction needs visible leads to its four terminals
    S[-1]["prims"] += [L(0, -5, 0, 5), L(-5, 0, 5, 0)]
    return S


BUILTIN = build()
BUILTIN_BY_ID = {s["id"]: s for s in BUILTIN}
