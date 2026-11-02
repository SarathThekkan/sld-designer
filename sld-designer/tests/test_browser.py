"""Browser end-to-end tests (real mouse/keyboard events in headless Chromium).

Skipped automatically when Playwright / Chromium are not installed:
    pip install playwright && playwright install chromium
"""
import json
import os

import pytest

pw = pytest.importorskip("playwright.sync_api")

from e2e_helpers import UI, Server  # noqa: E402
from sld_designer.library import UserLibrary  # noqa: E402
from sld_designer.project import validate_project  # noqa: E402
from sld_designer.render import build_display_list  # noqa: E402


@pytest.fixture(scope="module")
def server():
    s = Server()
    yield s
    s.stop()


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # pragma: no cover
            pytest.skip(f"chromium not available: {e}")
        yield b
        b.close()


@pytest.fixture
def ui(browser, server):
    ctx = browser.new_context(viewport={"width": 1500, "height": 950}, accept_downloads=True)
    # force the portable download/upload code paths (native file pickers cannot be automated)
    ctx.add_init_script("delete window.showSaveFilePicker; delete window.showOpenFilePicker;")
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    u = UI(page)
    u.errors = errors
    u.server = server
    u.open(server.url)
    yield u
    ctx.close()
    assert not errors, errors


def orthogonal(pts):
    return all(a[0] == b[0] or a[1] == b[1] for a, b in zip(pts, pts[1:]))


def test_browser_and_python_draw_identically(ui):
    """The on-screen drawing list must equal what Python exports to PDF/DXF."""
    ui.pg.evaluate("""() => {
      const e = window.sld.editor; const syms = [...e.library.values()];
      syms.forEach((s, i) => e.project.elements.push({id: 'e' + (100 + i), type: 'sym', sym: s.id, x: 30 + (i % 8) * 45, y: 40 + Math.floor(i / 8) * 45,
        rot: (i % 4) * 90, mirror: i % 3 === 0, tag: s.prefix ? s.prefix + (i + 1) : '', attrs: Object.fromEntries((s.attrs || []).map(a => [a.key, a.default])), lp: ['r', 'l', 't', 'b'][i % 4]}));
      e.project.elements.push({id: 'e300', type: 'bus', x: 30, y: 250, len: 200, rot: 0, tag: 'BUS-A', attrs: {Voltage: '11 kV'}, lp: 'l'});
      e.project.elements.push({id: 'e302', type: 'rect', x: 20, y: 30, w: 100, h: 60, dash: true});
      e.project.elements.push({id: 'e303', type: 'line', pts: [[10, 10], [50, 10], [50, 30]], dash: false});
      e.project.elements.push({id: 'e304', type: 'text', x: 200, y: 200, s: 'Hello\\nWorld ° mm² Ω', size: 4, bold: true, anchor: 'middle'});
      e.project.wires.push({id: 'w400', pts: [[100, 200], [100, 220], [150, 220], [150, 240]], a: null, b: null, label: '3x240 mm² XLPE\\n100 m'});
      e.project.wires.push({id: 'w401', pts: [[150, 230], [190, 230]], a: null, b: null, label: 'x'});
      e.project.elements.push({id: 'e305', type: 'sym', sym: 'no-such-symbol', x: 300, y: 150, rot: 0, tag: 'X1', attrs: {}});
      e.project.nextId = 1000; e.render();
    }""")
    proj = ui.pg.evaluate("window.sld.editor.exportable()")
    js_items = ui.pg.evaluate("""async () => { const c = await import('/static/core.js'); const p = window.sld.editor.exportable();
                                  return c.buildDisplayList(p, (id) => p.symbols[id]); }""")
    py_items = build_display_list(validate_project(proj), UserLibrary(ui.server.home).lookup())

    def strip(items):
        return [{k: v for k, v in it.items() if k != "id"} for it in items]

    def same(a, b, path=""):
        if isinstance(a, dict):
            assert set(a) == set(b), path
            for k in a:
                same(a[k], b[k], path + "/" + k)
        elif isinstance(a, list):
            assert len(a) == len(b), f"{path}: {len(a)} != {len(b)}"
            for i, (x, y) in enumerate(zip(a, b)):
                same(x, y, f"{path}[{i}]")
        elif isinstance(a, float) or isinstance(b, float):
            assert abs(a - b) < 1e-3, f"{path}: {a} != {b}"
        else:
            assert a == b, f"{path}: {a!r} != {b!r}"

    assert len(py_items) > 200
    same(strip(js_items), strip(py_items))


def test_place_and_wire_connect_to_terminals_and_busbar(ui):
    ui.place("cb", 100, 60)
    ui.place("motor", 100, 100)
    ui.bus(60, 30, 160, 30)
    ui.wire((100, 70), (100, 90))
    ui.wire((100, 50), (100, 30))
    p = ui.proj()
    assert [e["tag"] for e in p["elements"]] == ["CB1", "M1", "BUS1"]
    w1, w2 = p["wires"]
    assert w1["a"] == {"el": "e1", "t": 1} and w1["b"] == {"el": "e2", "t": 0}
    assert w2["a"] == {"el": "e1", "t": 0} and w2["b"] == {"el": "e3", "s": 40}


def test_moving_a_symbol_drags_wire_and_keeps_it_orthogonal(ui):
    ui.place("cb", 60, 60)
    ui.place("cb", 120, 120)
    ui.wire((60, 70), (120, 110))
    w = ui.proj()["wires"][0]
    assert len(w["pts"]) == 4 and orthogonal(w["pts"])           # V-H-V route
    ui.pg.keyboard.press("v")
    ui.drag(120, 120, 150, 140)
    p = ui.proj()
    assert (p["elements"][1]["x"], p["elements"][1]["y"]) == (150, 140)
    assert p["wires"][0]["pts"][-1] == [150, 130] and orthogonal(p["wires"][0]["pts"])
    # rotate the first symbol: its wire end follows the terminal
    ui.click(60, 60)
    ui.pg.keyboard.press("r")
    p = ui.proj()
    assert p["elements"][0]["rot"] == 90 and p["wires"][0]["pts"][0] == [50, 60] and orthogonal(p["wires"][0]["pts"])


def test_drag_wire_segment_handle(ui):
    ui.place("cb", 60, 60)
    ui.place("cb", 120, 120)
    ui.wire((60, 70), (120, 110))
    ui.pg.keyboard.press("v")
    ui.click(60, 80)
    (hx, hy), = ui.pg.evaluate("window.sld.editor.handles().map(h => h.p)")
    ui.drag(hx, hy, hx, hy + 10)
    pts = ui.proj()["wires"][0]["pts"]
    assert pts == [[60, 70], [60, 100], [120, 100], [120, 110]]


def test_undo_redo_copy_paste_delete(ui):
    ui.place("cb", 60, 60)
    ui.place("motor", 100, 60)
    assert len(ui.proj()["elements"]) == 2
    ui.pg.keyboard.press("Control+z")
    assert len(ui.proj()["elements"]) == 1
    ui.pg.keyboard.press("Control+y")
    assert len(ui.proj()["elements"]) == 2
    ui.pg.keyboard.press("v")
    ui.click(60, 60)
    ui.pg.keyboard.press("Control+c")
    ui.pg.keyboard.press("Control+v")
    els = ui.proj()["elements"]
    assert len(els) == 3 and els[2]["tag"] == "CB2" and els[2]["x"] == 70
    ui.pg.keyboard.press("Delete")
    assert len(ui.proj()["elements"]) == 2


def test_group_rotate_and_box_select(ui):
    ui.place("cb", 60, 60)
    ui.place("motor", 60, 90)
    ui.wire((60, 70), (60, 80))
    ui.pg.keyboard.press("v")
    ui.drag(30, 30, 100, 120)                                     # left->right = window select
    assert len(ui.pg.evaluate("[...window.sld.editor.sel]")) == 3
    ui.pg.keyboard.press("r")
    p = ui.proj()
    assert all(e["rot"] == 90 for e in p["elements"]) and orthogonal(p["wires"][0]["pts"])


def test_properties_panel_edits_tag_and_data(ui):
    ui.place("trafo2", 100, 100)
    ui.pg.fill("#props input >> nth=0", "TR-MAIN")
    ui.pg.keyboard.press("Tab")
    ui.pg.fill("#props .attr input >> nth=0", "2500 kVA")
    ui.pg.keyboard.press("Tab")
    e = ui.proj()["elements"][0]
    assert e["tag"] == "TR-MAIN" and e["attrs"]["Rating"] == "2500 kVA"
    assert "2500 kVA" in ui.pg.text_content("#content")


def test_save_and_open_cad_file(ui, tmp_path):
    ui.place("generator", 100, 60)
    ui.wire((100, 70), (100, 90))
    path = str(tmp_path / "t.cad")
    with ui.pg.expect_download() as dl:
        ui.pg.keyboard.press("Control+s")
        ui.pg.wait_for_selector("dialog input")
        ui.pg.fill("dialog input", "t")
        ui.pg.click("dialog .btn.primary")
    dl.value.save_as(path)
    saved = json.load(open(path))
    assert saved["format"] == "SLD-CAD" and "generator" in saved["symbols"] and len(saved["elements"]) == 1
    # new drawing, then open the file back
    ui.pg.click(".menu >> text=File")
    ui.pg.click(".drop >> text=New")
    assert ui.proj()["elements"] == []
    with ui.pg.expect_file_chooser() as fc:
        ui.pg.click(".menu >> text=File")
        ui.pg.click(".drop >> text=Open")
    fc.value.set_files(path)
    ui.pg.wait_for_function("window.sld.editor.project.elements.length === 1")
    assert ui.pg.inner_text("#docname").startswith("t.cad")
    assert ui.proj()["wires"][0]["pts"] == [[100, 70], [100, 90]]


def test_open_invalid_file_is_rejected_with_message(ui, tmp_path):
    ui.place("cb", 60, 60)
    bad = tmp_path / "bad.cad"
    bad.write_text('{"format": "something-else"}')
    ui.pg.evaluate("window.sld.editor.setDirty(false)")
    with ui.pg.expect_file_chooser() as fc:
        ui.pg.click(".menu >> text=File")
        ui.pg.click(".drop >> text=Open")
    fc.value.set_files(str(bad))
    ui.pg.wait_for_selector(".toast.err")
    assert "Not an SLD Designer" in ui.pg.inner_text(".toast.err")
    assert len(ui.proj()["elements"]) == 1                         # drawing untouched
    ui.errors[:] = [e for e in ui.errors if "400" not in e]        # the expected 400 response


def test_unsaved_changes_prompt(ui):
    ui.place("cb", 60, 60)
    ui.pg.click(".menu >> text=File")
    ui.pg.click(".drop >> text=New")
    ui.pg.wait_for_selector("dialog >> text=Unsaved changes")
    ui.pg.click("dialog >> text=Cancel")
    assert len(ui.proj()["elements"]) == 1


def test_export_pdf_dxf_svg_through_ui(ui, tmp_path):
    ui.place("cb", 100, 100)
    with ui.pg.expect_download() as dl:
        ui.pg.click("button.tb >> text=Export PDF")
    f = tmp_path / "a.pdf"
    dl.value.save_as(str(f))
    assert f.read_bytes().startswith(b"%PDF-") and dl.value.suggested_filename.endswith(".pdf")
    with ui.pg.expect_download() as dl:
        ui.pg.click(".menu >> text=File")
        ui.pg.click(".drop >> text=Export DXF")
    f = tmp_path / "a.dxf"
    dl.value.save_as(str(f))
    assert f.read_text().startswith("0\nSECTION")
    with ui.pg.expect_download() as dl:
        ui.pg.click(".menu >> text=File")
        ui.pg.click(".drop >> text=Export SVG")
    f = tmp_path / "a.svg"
    dl.value.save_as(str(f))
    assert "<svg" in f.read_text() and "CB1" in f.read_text()


def test_sheet_properties_change_page_size_of_pdf(ui, tmp_path):
    ui.pg.select_option("#props select >> nth=0", "A4")
    ui.pg.select_option("#props select >> nth=1", "portrait")
    assert ui.proj()["sheet"]["size"] == "A4" and ui.proj()["sheet"]["orientation"] == "portrait"
    with ui.pg.expect_download() as dl:
        ui.pg.click("button.tb >> text=Export PDF")
    f = tmp_path / "p.pdf"
    dl.value.save_as(str(f))
    import re
    m = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)", f.read_bytes())
    assert abs(float(m.group(1)) / 72 * 25.4 - 210) < 0.3 and abs(float(m.group(2)) / 72 * 25.4 - 297) < 0.3


def test_symbol_editor_library_export_import(ui, tmp_path):
    ui.pg.click("#palette >> text=New symbol…")
    box = ui.pg.locator(".se-canvas").bounding_box()
    S = box["width"] / 80

    def sp(x, y):
        return box["x"] + box["width"] / 2 + x * S, box["y"] + box["height"] / 2 + y * S

    def tool(t):
        ui.pg.click(f'.se-tools button[data-tool="{t}"]')

    tool("rect"); ui.pg.mouse.click(*sp(-7.5, -5)); ui.pg.mouse.click(*sp(7.5, 5))
    tool("line"); ui.pg.mouse.click(*sp(0, -10)); ui.pg.mouse.click(*sp(0, -5))
    tool("circle"); ui.pg.mouse.click(*sp(0, 0)); ui.pg.mouse.click(*sp(2.5, 0))
    tool("term"); ui.pg.mouse.click(*sp(0, -10))
    ui.pg.fill(".se-form input >> nth=0", "Test widget")
    ui.pg.fill(".se-form input >> nth=2", "TW")
    ui.pg.fill(".se-form textarea", "Rating = 5 A")
    ui.pg.click("#se-save")
    ui.pg.wait_for_selector('.sym[data-id="u-test-widget"]')
    ui.place("u-test-widget", 100, 100)
    e = ui.proj()["elements"][0]
    assert e["tag"] == "TW1" and e["attrs"] == {"Rating": "5 A"}
    with ui.pg.expect_download() as dl:
        ui.pg.click("#palette >> text=Export…")
    f = tmp_path / "x.sldlib"
    dl.value.save_as(str(f))
    lib = json.load(open(f))
    assert lib["format"] == "SLD-LIB" and [s["id"] for s in lib["symbols"]] == ["u-test-widget"]
    ui.pg.hover('.sym[data-id="u-test-widget"]')
    ui.pg.click('.sym[data-id="u-test-widget"] .mini button[title="Delete symbol"]')
    ui.pg.click("dialog .btn.primary")
    ui.pg.wait_for_selector('.sym[data-id="u-test-widget"]', state="detached")
    ui.pg.set_input_files("#palette input[type=file]", str(f))
    ui.pg.wait_for_selector('.sym[data-id="u-test-widget"]')
    # a drawing saved with the symbol embeds it, so it opens even if the library lacks it
    saved = ui.pg.evaluate("window.sld.editor.exportable().symbols")
    assert "u-test-widget" in saved


def test_autosave_recovery(ui):
    ui.place("cb", 60, 60)
    ui.pg.wait_for_timeout(1900)
    ui.pg.evaluate("window.sld.editor.setDirty(false)")      # avoid the beforeunload prompt
    ui.pg.reload()
    ui.pg.wait_for_selector("dialog >> text=Recover unsaved drawing?")
    ui.pg.click("dialog .btn.primary")
    ui.pg.wait_for_function("window.sld.editor.project.elements.length === 1")
