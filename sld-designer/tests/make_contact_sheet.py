"""Render every built-in symbol on A3 pages -> examples/symbol_library.pdf"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from collections import OrderedDict
from sld_designer.symbols_builtin import BUILTIN
from sld_designer.pdf import export_pdf

cats = OrderedDict()
for s in BUILTIN:
    cats.setdefault(s["category"], []).append(s)
els, y = [], 60
els.append({"id": "t0", "type": "text", "x": 20, "y": 30, "s": "SLD Designer - built-in symbol library", "size": 6, "bold": True})
for c, syms in cats.items():
    els.append({"id": f"c{y}", "type": "text", "x": 20, "y": y, "s": c, "size": 4.5, "bold": True})
    x = 40
    for s in syms:
        els.append({"id": f"s{len(els)}", "type": "sym", "sym": s["id"], "x": x, "y": y + 30, "rot": 0, "lp": "b", "tag": s["name"][:22]})
        x += 52
        if x > 780:
            x = 40; y += 55
    y += 60
proj = {"format": "SLD-CAD", "version": 1, "sheet": {"size": "A0", "orientation": "portrait"},
        "title": {}, "symbols": {}, "elements": els, "wires": [], "nextId": 9999}
out = sys.argv[1] if len(sys.argv) > 1 else "examples/symbol_library.pdf"
export_pdf(proj, {s["id"]: s for s in BUILTIN}, out)
