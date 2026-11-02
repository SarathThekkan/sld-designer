"""Backend tests - no browser needed."""
import json
import math
import os
import re

import pytest

from sld_designer import config, project as prj
from sld_designer.dxf import export_dxf
from sld_designer.geometry import arc_points, seg_hit, transform_point
from sld_designer.library import SymbolError, UserLibrary, validate_symbol
from sld_designer.pdf import export_pdf
from sld_designer.render import build_display_list, junctions
from sld_designer.server import create_app
from sld_designer.symbols_builtin import BUILTIN

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = {"X-SLD-Client": "1"}


@pytest.fixture
def lib(tmp_path):
    return UserLibrary(str(tmp_path))


def sample_project():
    p = prj.new_project()
    p["elements"] = [
        {"id": "e1", "type": "sym", "sym": "cb", "x": 50, "y": 50, "rot": 0, "mirror": False, "tag": "CB1", "attrs": {"Rating": "630 A"}},
        {"id": "e2", "type": "bus", "x": 20, "y": 80, "len": 60, "rot": 0, "tag": "BUS1", "attrs": {}},
        {"id": "e3", "type": "text", "x": 100, "y": 30, "s": "Hi\nthere", "size": 4},
        {"id": "e4", "type": "rect", "x": 10, "y": 20, "w": 80, "h": 50, "dash": True},
        {"id": "e6", "type": "sym", "sym": "motor", "x": 50, "y": 120, "rot": 90, "mirror": True, "tag": "M1", "attrs": {}},
    ]
    p["wires"] = [{"id": "w5", "pts": [[50, 60], [50, 80]], "a": {"el": "e1", "t": 1}, "b": {"el": "e2", "s": 30}, "label": "cable"}]
    p["nextId"] = 7
    return prj.validate_project(p)


# ------------------------------------------------------------------ geometry
def test_transform_quarter_turns():
    assert transform_point(1, 0, 90, False, 0, 0) == (0, 1)          # right -> down (clockwise on screen)
    assert transform_point(1, 0, 180, False, 10, 10) == (9, 10)
    assert transform_point(1, 0, 270, False, 0, 0) == (0, -1)
    assert transform_point(1, 2, 0, True, 0, 0) == (-1, 2)           # mirror flips x first


def test_arc_and_seg():
    pts = arc_points(0, 0, 10, 0, 90, 10)
    assert pts[0] == (10, 0) and math.isclose(pts[-1][0], 0, abs_tol=1e-9) and math.isclose(pts[-1][1], 10)
    assert seg_hit((5, 5), (0, 0), (10, 10)) and not seg_hit((5, 6), (0, 0), (10, 10))


# ------------------------------------------------------------------- symbols
def test_builtin_symbols_valid_and_on_grid():
    assert len(BUILTIN) >= 90
    ids = set()
    for s in BUILTIN:
        assert s["id"] not in ids
        ids.add(s["id"])
        v = validate_symbol(s)
        assert v["prims"] and v["terminals"], s["id"]
        for t in v["terminals"]:      # wires must land on the 5 mm grid
            assert t["x"] % 5 == 0 and t["y"] % 5 == 0, (s["id"], t)


@pytest.mark.parametrize("bad", [
    {}, {"id": "Bad Id", "prims": [{"t": "line", "x1": 0, "y1": 0, "x2": 1, "y2": 1}]},
    {"id": "ok", "prims": []}, {"id": "ok", "prims": [{"t": "evil"}]},
    {"id": "ok", "prims": [{"t": "line", "x1": float("nan"), "y1": 0, "x2": 1, "y2": 1}]},
    {"id": "ok", "prims": [{"t": "circle", "cx": 0, "cy": 0, "r": 1e9}]},
])
def test_symbol_validation_rejects(bad):
    with pytest.raises(SymbolError):
        validate_symbol(bad)


# ------------------------------------------------------------------- project
def test_new_project_roundtrip(tmp_path):
    p = sample_project()
    f = tmp_path / "a.cad"
    prj.save(p, str(f))
    q = prj.load(str(f))
    assert q["elements"] == p["elements"] and q["wires"] == p["wires"]
    assert json.loads(f.read_text())["format"] == "SLD-CAD"


@pytest.mark.parametrize("mutate,msg", [
    (lambda d: d.update(format="nope"), "Not an SLD"),
    (lambda d: d.update(version=99), "newer version"),
    (lambda d: d["sheet"].update(size="A9"), "sheet size"),
    (lambda d: d["elements"].append({"id": "x", "type": "ufo"}), "unknown element"),
    (lambda d: d["elements"].append({"id": "e1", "type": "text", "x": 0, "y": 0}), "duplicate"),
    (lambda d: d["elements"][0].update(x=float("inf")), "invalid number"),
    (lambda d: d["wires"][0].update(pts=[[0, 0]]), "wire"),
    (lambda d: d["elements"][0].update(id="a b"), "invalid id"),
])
def test_project_validation_rejects(mutate, msg):
    d = json.loads(json.dumps(sample_project()))
    mutate(d)
    with pytest.raises(prj.ProjectError, match=msg):
        prj.validate_project(d)


def test_loads_garbage():
    with pytest.raises(prj.ProjectError):
        prj.loads("not json at all")


def test_sample_file_loads_and_renders(lib):
    p = prj.load(os.path.join(ROOT, "examples", "sample.cad"))
    items = build_display_list(p, lib.lookup())
    assert len(items) > 150
    assert export_pdf(p, lib.lookup())[:5] == b"%PDF-"


# ------------------------------------------------------------------- render
def test_display_list_basics(lib):
    items = build_display_list(sample_project(), lib.lookup())
    texts = [i["s"] for i in items if i["k"] == "text"]
    assert "CB1" in texts and "630 A" in texts and "BUS1" in texts and "cable" in texts and "there" in texts
    assert any(i["k"] == "poly" and i["w"] == config.STYLE["bus_w"] for i in items)


def test_junctions():
    w = lambda *pts: {"pts": [list(p) for p in pts]}
    # T junction: end of one wire on the middle of another
    assert len(junctions([w((0, 0), (0, 20)), w((0, 10), (10, 10))])) == 1
    # simple continuation: two ends meeting -> no dot
    assert junctions([w((0, 0), (0, 10)), w((0, 10), (0, 20))]) == []
    # three ends -> dot
    assert len(junctions([w((0, 0), (0, 10)), w((0, 10), (10, 10)), w((0, 10), (0, 20))])) == 1
    # crossing -> no dot
    assert junctions([w((0, 0), (0, 20)), w((-5, 10), (5, 10))]) == []


def test_missing_symbol_placeholder(lib):
    p = sample_project()
    p["elements"][0]["sym"] = "does-not-exist"
    items = build_display_list(p, lib.lookup())
    assert any(i["k"] == "text" and i["s"] == "?" for i in items)


def test_project_embedded_symbols_win(lib):
    p = sample_project()
    sym = {"id": "cb", "name": "X", "category": "c", "prefix": "", "prims": [{"t": "circle", "cx": 0, "cy": 0, "r": 3, "fill": False}], "terminals": [], "attrs": []}
    p["symbols"] = {"cb": validate_symbol(sym)}
    items = build_display_list(p, lib.lookup())
    assert any(i["k"] == "circle" and i["r"] == 3 for i in items)


# ---------------------------------------------------------------- pdf / dxf
def test_pdf_page_size_and_content(lib):
    p = sample_project()
    data = export_pdf(p, lib.lookup())
    assert data.startswith(b"%PDF-") and data.rstrip().endswith(b"%%EOF")
    m = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]", data)
    w_mm, h_mm = float(m.group(1)) / 72 * 25.4, float(m.group(2)) / 72 * 25.4
    assert abs(w_mm - 420) < 0.2 and abs(h_mm - 297) < 0.2          # A3 landscape
    p["sheet"].update(size="A4", orientation="portrait")
    m = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]", export_pdf(p, lib.lookup()))
    assert abs(float(m.group(1)) / 72 * 25.4 - 210) < 0.2 and abs(float(m.group(2)) / 72 * 25.4 - 297) < 0.2


def parse_dxf(text):
    lines = text.split("\n")
    pairs = [(int(lines[i]), lines[i + 1]) for i in range(0, len(lines) - 1, 2) if lines[i].strip() != ""]
    return pairs


def test_dxf_structure(lib):
    p = sample_project()
    p["title"]["title"] = "Ω test ° ²"
    text = export_dxf(p, lib.lookup())
    pairs = parse_dxf(text)
    assert pairs[-1] == (0, "EOF")
    ents = [v for c, v in pairs if c == 0]
    assert ents.count("SECTION") == ents.count("ENDSEC") == 3
    assert ents.count("POLYLINE") == ents.count("SEQEND") > 5
    assert "TEXT" in ents and "CIRCLE" in ents
    assert text.isascii() and "\\U+03A9" in text                      # non-ASCII is escaped
    layers = {v for c, v in pairs if c == 8}
    assert {"SYM", "BUS", "WIRE", "FRAME", "TEXT", "ANNOT"} <= layers


# ------------------------------------------------------------------ library
def test_library_put_delete_export_import(lib, tmp_path):
    base = {"name": "My thing", "id": "my-thing", "category": "Custom", "prefix": "MT",
            "prims": [{"t": "rect", "x": -5, "y": -5, "w": 10, "h": 10}],
            "terminals": [{"x": 0, "y": -5, "d": [0, -1], "n": "1"}], "attrs": [{"key": "Rating", "default": "5 A"}]}
    lib.put(base)
    assert "my-thing" in UserLibrary(str(tmp_path)).symbols                   # persisted
    with pytest.raises(SymbolError):
        lib.put(dict(base, id="cb"))                                          # built-in id is protected
    text = lib.export_text()
    data = json.loads(text)
    assert data["format"] == "SLD-LIB" and [s["id"] for s in data["symbols"]] == ["my-thing"]
    lib.delete("my-thing")
    with pytest.raises(SymbolError):
        lib.delete("cb")
    added, replaced, problems = lib.import_data(data)
    assert added == ["my-thing"] and not problems
    added, replaced, problems = lib.import_data(data)                         # identical -> not duplicated
    assert added == [] and lib.last_unchanged == ["my-thing"] and len(lib.symbols) == 1
    data["symbols"][0]["name"] = "Changed"
    added, _, _ = lib.import_data(data)                                       # same id, different content -> renamed
    assert added == ["my-thing-2"] and len(lib.symbols) == 2
    with pytest.raises(SymbolError):
        lib.import_data({"format": "other"})
    _, _, problems = lib.import_data({"format": "SLD-LIB", "symbols": [{"id": "bad id"}]})
    assert len(problems) == 1


# --------------------------------------------------------------------- API
@pytest.fixture
def client(tmp_path):
    return create_app(str(tmp_path)).test_client()


def test_api_basics(client):
    assert client.get("/").status_code == 200
    assert client.get("/static/core.js").status_code == 200
    assert client.get("/static/../server.py").status_code == 404
    assert client.get("/fonts/DejaVuSans.ttf").status_code == 200
    assert client.get("/fonts/LICENSE_DEJAVU").status_code == 404
    cfg = client.get("/api/config").get_json()
    assert cfg["sheets"]["A3"] == [420, 297]
    syms = client.get("/api/symbols").get_json()["symbols"]
    assert len(syms) >= 30 and all(s["builtin"] for s in syms)


def test_api_guards(client):
    assert client.post("/api/symbols", json={}).status_code == 403                      # no custom header
    assert client.get("/api/config", headers={"Host": "evil.example.com"}).status_code == 403
    assert client.get("/api/config", headers={"Host": "localhost:8765"}).status_code == 200
    assert client.post("/api/project/validate", data="x", headers=H).status_code == 400


def test_api_symbol_lifecycle_and_exports(client):
    sym = {"name": "Test Sym", "category": "Custom", "prefix": "TS", "prims": [{"t": "line", "x1": 0, "y1": -5, "x2": 0, "y2": 5}],
           "terminals": [{"x": 0, "y": -5, "d": [0, -1]}], "attrs": []}
    r = client.post("/api/symbols", json=sym, headers=H)
    assert r.status_code == 200 and r.get_json()["symbol"]["id"] == "u-test-sym"
    assert client.post("/api/symbols", json=dict(sym, prims=[]), headers=H).status_code == 400
    exp = client.get("/api/library/export")
    assert exp.status_code == 200 and "attachment" in exp.headers["Content-Disposition"]
    lib_data = json.loads(exp.data)
    assert client.delete("/api/symbols/u-test-sym", headers=H).status_code == 200
    r = client.post("/api/library/import", json={"data": lib_data}, headers=H).get_json()
    assert r["added"] == ["u-test-sym"]
    assert client.delete("/api/symbols/cb", headers=H).status_code == 400
    proj = sample_project()
    pdf = client.post("/api/export/pdf", json=proj, headers=H)
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF") and pdf.mimetype == "application/pdf"
    assert client.post("/api/export/dxf", json=proj, headers=H).data.startswith(b"0\nSECTION")
    assert client.post("/api/export/pdf", json={"format": "x"}, headers=H).status_code == 400


# ---------------------------------------------------------------------- CLI
def test_cli_export(tmp_path, monkeypatch):
    from sld_designer.__main__ import main
    monkeypatch.setenv("SLD_HOME", str(tmp_path / "home"))
    src = os.path.join(ROOT, "examples", "sample.cad")
    main(["export", src, str(tmp_path / "o.pdf")])
    main(["export", src, str(tmp_path / "o.dxf")])
    assert (tmp_path / "o.pdf").read_bytes().startswith(b"%PDF")
    assert (tmp_path / "o.dxf").read_text().startswith("0\nSECTION")
    with pytest.raises(SystemExit):
        main(["export", src, str(tmp_path / "o.png")])
    with pytest.raises(SystemExit):
        main(["export", str(tmp_path / "missing.cad"), str(tmp_path / "x.pdf")])
