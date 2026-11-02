"""DXF (AutoCAD R12, ASCII) export so drawings can be opened in AutoCAD / other CAD tools.

Layers:  FRAME, SYM, BUS, WIRE, ANNOT, TEXT.  Units: mm.  Y is flipped (CAD is y-up).
"""

import math

from .render import build_display_list, sheet_size

LAYERS = {"FRAME": 7, "SYM": 7, "BUS": 5, "WIRE": 3, "ANNOT": 8, "TEXT": 7}


def _esc(s):
    return "".join(ch if ord(ch) < 128 else "\\U+%04X" % ord(ch) for ch in s)


def export_dxf(project, library):
    _, H = sheet_size(project["sheet"])
    out = []

    def g(code, val):
        out.append(f"{code}\n{val}")

    def fy(y):
        return H - y

    g(0, "SECTION"); g(2, "HEADER"); g(9, "$ACADVER"); g(1, "AC1009")
    g(9, "$INSUNITS"); g(70, 4); g(0, "ENDSEC")
    g(0, "SECTION"); g(2, "TABLES")
    g(0, "TABLE"); g(2, "LTYPE"); g(70, 2)
    g(0, "LTYPE"); g(2, "CONTINUOUS"); g(70, 0); g(3, "Solid line"); g(72, 65); g(73, 0); g(40, 0.0)
    g(0, "LTYPE"); g(2, "DASHED"); g(70, 0); g(3, "Dashed"); g(72, 65); g(73, 2); g(40, 3.2); g(49, 2.0); g(49, -1.2)
    g(0, "ENDTAB")
    g(0, "TABLE"); g(2, "LAYER"); g(70, len(LAYERS))
    for name, col in LAYERS.items():
        g(0, "LAYER"); g(2, name); g(70, 0); g(62, col); g(6, "CONTINUOUS")
    g(0, "ENDTAB"); g(0, "ENDSEC")
    g(0, "SECTION"); g(2, "ENTITIES")

    def solid(layer, a, b, c_):
        g(0, "SOLID"); g(8, layer)
        for i, (x, y) in enumerate((a, b, c_, c_)):
            g(10 + i, f"{x:.4f}"); g(20 + i, f"{fy(y):.4f}"); g(30 + i, 0)

    for it in build_display_list(project, library):
        layer = it.get("layer", "SYM")
        if it["k"] == "poly":
            pts = it["pts"]
            if it["fill"] and len(pts) >= 3:
                for i in range(1, len(pts) - 1):
                    solid(layer, pts[0], pts[i], pts[i + 1])
            g(0, "POLYLINE"); g(8, layer); g(6, "DASHED" if it.get("dash") else "CONTINUOUS")
            g(66, 1); g(70, 1 if it["closed"] else 0)
            for x, y in pts:
                g(0, "VERTEX"); g(8, layer); g(10, f"{x:.4f}"); g(20, f"{fy(y):.4f}")
            g(0, "SEQEND"); g(8, layer)
        elif it["k"] == "circle":
            cx, cy = it["c"]
            if it["fill"]:
                n = 16
                ring = [(cx + it["r"] * math.cos(2 * math.pi * i / n), cy + it["r"] * math.sin(2 * math.pi * i / n)) for i in range(n)]
                for i in range(1, n - 1):
                    solid(layer, ring[0], ring[i], ring[i + 1])
            g(0, "CIRCLE"); g(8, layer); g(10, f"{cx:.4f}"); g(20, f"{fy(cy):.4f}"); g(30, 0); g(40, f"{it['r']:.4f}")
        elif it["k"] == "text":
            x, y = it["p"]
            h = it["size"] * 0.72
            g(0, "TEXT"); g(8, layer); g(10, f"{x:.4f}"); g(20, f"{fy(y):.4f}"); g(30, 0)
            g(40, f"{h:.4f}"); g(1, _esc(it["s"]))
            g(72, {"start": 0, "middle": 1, "end": 2}[it["anchor"]]); g(73, 2)
            g(11, f"{x:.4f}"); g(21, f"{fy(y):.4f}"); g(31, 0)
    g(0, "ENDSEC"); g(0, "EOF")
    return "\n".join(out) + "\n"
