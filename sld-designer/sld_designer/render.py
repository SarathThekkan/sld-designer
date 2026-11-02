"""Turns a project into a flat *display list* (lines, circles, text in sheet mm).

The display list is the single source for PDF and DXF export.  static/core.js
builds the very same list in the browser for the live view (tests/test_parity.py
asserts they match), so what you see is what you print.

Items
    {"k": "poly",   "pts": [[x, y], ...], "closed": bool, "fill": bool, "w": mm, "dash": bool, "layer": str}
    {"k": "circle", "c": [x, y], "r": mm, "fill": bool, "w": mm, "layer": str}
    {"k": "text",   "p": [x, y], "s": str, "size": mm, "bold": bool, "anchor": "start|middle|end", "layer": str}
Text is vertically centred on p[1].
"""

from . import config
from .geometry import arc_points, r4, seg_hit, transform_point, transform_vec

ST = config.STYLE


# ----------------------------------------------------------------- primitives
def _poly(pts, closed=False, fill=False, w=None, dash=False, layer="SYM"):
    return {"k": "poly", "pts": [[r4(x), r4(y)] for x, y in pts], "closed": bool(closed),
            "fill": bool(fill), "w": r4(ST["line_w"] if w is None else w),
            "dash": bool(dash), "layer": layer}


def _circle(cx, cy, r, fill=False, w=None, layer="SYM"):
    return {"k": "circle", "c": [r4(cx), r4(cy)], "r": r4(r), "fill": bool(fill),
            "w": r4(ST["line_w"] if w is None else w), "layer": layer}


def _text(x, y, s, size, bold=False, anchor="start", layer="TEXT"):
    return {"k": "text", "p": [r4(x), r4(y)], "s": str(s), "size": r4(size),
            "bold": bool(bold), "anchor": anchor, "layer": layer}


# --------------------------------------------------------------------- symbols
def symbol_items(sym, el):
    """World-space items for one placed symbol (no label)."""
    rot, mir = el.get("rot", 0), bool(el.get("mirror", False))
    ox, oy = el["x"], el["y"]

    def f(x, y):
        return transform_point(x, y, rot, mir, ox, oy)

    out = []
    for p in sym["prims"]:
        t = p["t"]
        w = p.get("lw")
        dash = bool(p.get("dash"))
        if t == "line":
            out.append(_poly([f(p["x1"], p["y1"]), f(p["x2"], p["y2"])], w=w, dash=dash))
        elif t == "poly":
            out.append(_poly([f(x, y) for x, y in p["pts"]], p.get("closed", False),
                             p.get("fill", False), w, dash))
        elif t == "rect":
            x, y, ww, hh = p["x"], p["y"], p["w"], p["h"]
            out.append(_poly([f(x, y), f(x + ww, y), f(x + ww, y + hh), f(x, y + hh)],
                             True, p.get("fill", False), w, dash))
        elif t == "circle":
            cx, cy = f(p["cx"], p["cy"])
            out.append(_circle(cx, cy, p["r"], p.get("fill", False), w))
        elif t == "arc":
            pts = arc_points(p["cx"], p["cy"], p["r"], p["a0"], p["a1"], ST["arc_step"])
            out.append(_poly([f(x, y) for x, y in pts], w=w, dash=dash))
        elif t == "text":
            x, y = f(p["x"], p["y"])
            out.append(_text(x, y, p["s"], p.get("size", 3.5), p.get("bold", False),
                             p.get("anchor", "middle"), "SYM"))
    return out


def terminal_world(sym, el, idx):
    t = sym["terminals"][idx]
    x, y = transform_point(t["x"], t["y"], el.get("rot", 0), bool(el.get("mirror")), el["x"], el["y"])
    return x, y


def bus_ends(el):
    x, y, n = el["x"], el["y"], el["len"]
    return ((x, y), (x + n, y)) if int(el.get("rot", 0)) % 180 == 0 else ((x, y), (x, y + n))


def items_bbox(items):
    xs, ys = [], []
    for it in items:
        if it["k"] == "poly":
            for x, y in it["pts"]:
                xs.append(x)
                ys.append(y)
        elif it["k"] == "circle":
            cx, cy = it["c"]
            r = it["r"]
            xs += [cx - r, cx + r]
            ys += [cy - r, cy + r]
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


# ---------------------------------------------------------------------- labels
def label_items(lines, bbox, lp, bold_first=True, size_first=None, off=(0, 0)):
    """Stack text lines next to bbox=(x0,y0,x1,y1). lp: r|l|t|b; off = manual (dx, dy) offset."""
    n = len(lines)
    if n == 0:
        return []
    x0, y0, x1, y1 = bbox
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    gap, pitch = ST["label_gap"], ST["pitch"]
    ox, oy = off
    out = []
    for i, s in enumerate(lines):
        first = bold_first and i == 0
        size = ST["tag_size"] if first else ST["attr_size"]
        if size_first is not None and i == 0:
            size = size_first
        if lp == "l":
            out.append(_text(ox + x0 - gap, oy + cy - (n - 1) * pitch / 2 + i * pitch, s, size, first, "end"))
        elif lp == "t":
            out.append(_text(ox + cx, oy + y0 - gap - 1.5 - (n - 1 - i) * pitch, s, size, first, "middle"))
        elif lp == "b":
            out.append(_text(ox + cx, oy + y1 + gap + 1.5 + i * pitch, s, size, first, "middle"))
        else:
            out.append(_text(ox + x1 + gap, oy + cy - (n - 1) * pitch / 2 + i * pitch, s, size, first, "start"))
    return out


def element_lines(el):
    lines = []
    if el.get("tag"):
        lines.append(el["tag"])
    for v in (el.get("attrs") or {}).values():
        if str(v).strip():
            lines.append(str(v))
    return lines


# -------------------------------------------------------------------- elements
def element_items(el, symbols):
    t = el["type"]
    if t == "sym":
        sym = symbols.get(el["sym"])
        if not sym:      # symbol not available: visible placeholder so nothing silently disappears
            x, y = el["x"], el["y"]
            return [_poly([(x - 5, y - 5), (x + 5, y - 5), (x + 5, y + 5), (x - 5, y + 5)], True, False, None, True, "SYM"),
                    _text(x, y, "?", 4, True, "middle", "SYM")] + label_items(
                        [el.get("tag") or "missing symbol"], (x - 5, y - 5, x + 5, y + 5), el.get("lp", "r"))
        items = symbol_items(sym, el)
        bb = items_bbox(items) or (el["x"] - 5, el["y"] - 5, el["x"] + 5, el["y"] + 5)
        lines = element_lines(el)
        return items + label_items(lines, bb, el.get("lp", "r"), off=el.get("lo", (0, 0)))
    if t == "bus":
        a, b = bus_ends(el)
        items = [_poly([a, b], w=ST["bus_w"], layer="BUS")]
        bb = (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
        return items + label_items(element_lines(el), bb, el.get("lp", "l"), off=el.get("lo", (0, 0)))
    if t == "rect":
        x, y, w, h = el["x"], el["y"], el["w"], el["h"]
        return [_poly([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], True, False,
                      el.get("lw"), el.get("dash", False), "ANNOT")]
    if t == "line":
        return [_poly(el["pts"], False, False, el.get("lw"), el.get("dash", False), "ANNOT")]
    if t == "text":
        out = []
        size = el.get("size", ST["text_size"])
        for i, s in enumerate(str(el.get("s", "")).split("\n")):
            out.append(_text(el["x"], el["y"] + i * size * 1.3, s, size, el.get("bold", False),
                             el.get("anchor", "start"), "TEXT"))
        return out
    return []


# ----------------------------------------------------------------------- wires
def wire_items(w):
    pts = w["pts"]
    out = [_poly(pts, layer="WIRE")]
    label = str(w.get("label", "")).strip()
    if label and len(pts) >= 2:
        best, bi = -1, 0
        for i in range(len(pts) - 1):
            L = abs(pts[i + 1][0] - pts[i][0]) + abs(pts[i + 1][1] - pts[i][1])
            if L > best:
                best, bi = L, i
        a, b = pts[bi], pts[bi + 1]
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        vertical = abs(a[0] - b[0]) < abs(a[1] - b[1])
        items = label_items(label.split("\n"), (mx, my, mx, my), "r" if vertical else "t",
                            bold_first=False)
        out += items
    return out


def junctions(wires):
    """Dots where >=3 wire ends meet or where a wire ends on another wire."""
    ends = {}
    for w in wires:
        for p in (w["pts"][0], w["pts"][-1]):
            ends.setdefault((r4(p[0]), r4(p[1])), 0)
            ends[(r4(p[0]), r4(p[1]))] += 1
    dots = []
    for key, n in ends.items():
        on_other = False
        for w in wires:
            pts = w["pts"]
            for i in range(len(pts) - 1):
                if seg_hit(key, pts[i], pts[i + 1]) and key != (r4(pts[0][0]), r4(pts[0][1])) \
                        and key != (r4(pts[-1][0]), r4(pts[-1][1])):
                    on_other = True
                    break
            if on_other:
                break
        if n >= 3 or on_other:
            dots.append(key)
    return [_circle(x, y, ST["junction_r"], True, 0.1, "WIRE") for x, y in dots]


# ---------------------------------------------------------------- sheet frame
def sheet_size(sheet):
    w, h = config.SHEETS[sheet.get("size", "A3")]
    if sheet.get("orientation", "landscape") == "portrait":
        w, h = h, w
    return w, h


def frame_items(project):
    W, H = sheet_size(project["sheet"])
    m = ST["margin"]
    out = [_poly([(m, m), (W - m, m), (W - m, H - m), (m, H - m)], True, False, ST["border_w"], False, "FRAME")]
    tb = config.TITLEBLOCK
    ox, oy = W - m - tb["w"], H - m - tb["h"]
    out.append(_poly([(ox, oy), (ox + tb["w"], oy), (ox + tb["w"], oy + tb["h"]), (ox, oy + tb["h"])],
                     True, False, ST["border_w"], False, "FRAME"))
    title = project.get("title", {})
    for x, y, w, h, key, cap in tb["cells"]:
        out.append(_poly([(ox + x, oy + y), (ox + x + w, oy + y), (ox + x + w, oy + y + h), (ox + x, oy + y + h)],
                         True, False, ST["tb_w"], False, "FRAME"))
        out.append(_text(ox + x + 1.5, oy + y + 2.4, cap, tb["caption_size"], False, "start", "FRAME"))
        val = str(title.get(key, ""))
        if val:
            out.append(_text(ox + x + 1.5, oy + y + h - 4.2, val, tb["value_size"], key in ("title", "project"),
                             "start", "FRAME"))
    return out


# ------------------------------------------------------------------ everything
def symbol_lookup(project, library):
    """Symbols embedded in the project win over the library (reproducible files)."""
    d = dict(library)
    d.update(project.get("symbols", {}))
    return d


def build_display_list(project, library):
    symbols = symbol_lookup(project, library)
    items = frame_items(project)
    for el in project.get("elements", []):
        items += element_items(el, symbols)
    wires = project.get("wires", [])
    for w in wires:
        items += wire_items(w)
    items += junctions(wires)
    return items
