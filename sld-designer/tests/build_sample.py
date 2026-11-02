"""Builds examples/sample.cad by *driving the real editor UI* with mouse and keyboard events,
then exports sample.pdf / sample.dxf / a screenshot.  Doubles as an end-to-end test.

    python tests/build_sample.py            (needs: pip install playwright && playwright install chromium)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright  # noqa: E402

from e2e_helpers import ROOT, UI, Server  # noqa: E402

OUT = os.path.join(ROOT, "examples")


def build(pg):
    ui = UI(pg)
    # --- enclosures first (so they sit behind everything) -------------------------------
    ui.rect(30, 108, 268, 148)       # 11 kV switchgear
    ui.rect(30, 183, 270, 241)       # LV switchboard
    # --- 11 kV incomer ------------------------------------------------------------------
    ui.place("utility", 60, 30)
    ui.place("disconnector", 60, 60)
    ui.place("ct", 60, 80)
    ui.place("cb", 60, 100)
    ui.bus(50, 120, 260, 120)
    ui.wire((60, 45), (60, 50))
    ui.wire((60, 110), (60, 120))
    # --- transformer feeders ------------------------------------------------------------
    for x in (100, 180):
        ui.place("cb", x, 135)
        ui.place("trafo2", x, 165)
        ui.place("cb", x, 195)
        ui.wire((x, 120), (x, 125))
        ui.wire((x, 145), (x, 150))
        ui.wire((x, 180), (x, 185))
    ui.place("vt", 225, 135)
    ui.wire((225, 120), (225, 125))
    # --- LV board -----------------------------------------------------------------------
    ui.bus(50, 215, 260, 215)
    ui.wire((100, 205), (100, 215))
    ui.wire((180, 205), (180, 215))
    # standby generator
    ui.place("generator", 250, 170)
    ui.place("cb", 250, 195)
    ui.wire((250, 180), (250, 185))
    ui.wire((250, 205), (250, 215))
    # outgoing feeders
    for x, load in ((60, "motor"), (105, "load"), (160, "db"), (200, "capacitor")):
        ui.place("cb", x, 228)
        ui.place(load, x, 253)
        ui.wire((x, 215), (x, 218))
        ui.wire((x, 238), (x, 243))
    # --- annotations --------------------------------------------------------------------
    ui.text(210, 22, "SUBSTATION SS-01 - SINGLE LINE DIAGRAM", 6, True, "middle")
    ui.text(150, 113, "11 kV SWITCHGEAR", 3, True)
    ui.text(34, 188, "0.4 kV MAIN LV SWITCHBOARD", 3, True)
    ui.text(290, 40, "NOTES:\n1. Ratings are indicative only.\n2. All cables are XLPE/SWA unless noted.\n3. Standby generator interlocked with\n    incomer breakers CB4 and CB5.", 3.2)

    # --- naming & data (what the properties panel does) -------------------------------------
    els = ui.proj()["elements"]
    by = {}
    for e in els:
        by.setdefault(e.get("sym") or e["type"], []).append(e)
    names = {"utility": ["GRID"], "disconnector": ["DS1"], "ct": ["CT1"], "vt": ["VT1"], "generator": ["G1"], "db": ["DB-1"], "motor": ["M1"], "load": ["L1"], "capacitor": ["C1"], "trafo2": ["TR1", "TR2"]}
    for sym, tags in names.items():
        for e, t in zip(by[sym], tags):
            ui.edit(e["id"], tag=t)
    cb_tags = ["CB1", "CB2", "CB4", "CB3", "CB5", "CB6", "CB7", "CB8", "CB9", "CB10", "CB11"]
    ui.pg.evaluate("""(tags)=>{const e=window.sld.editor; const cbs=e.project.elements.filter(x=>x.sym==='cb'); cbs.forEach((c,i)=>{c.tag=tags[i]}); e.render();}""", cb_tags)
    buses = by["bus"]
    ui.edit(buses[0]["id"], tag="BUS-1", attrs={"Voltage": "11 kV", "Rating": "1250 A"})
    ui.edit(buses[1]["id"], tag="LV-BUS", attrs={"Voltage": "0.4 kV", "Rating": "3200 A"})
    ui.edit(by["trafo2"][0]["id"], attrs={"Rating": "1600 kVA", "Voltage": "11/0.4 kV"})
    ui.edit(by["trafo2"][1]["id"], attrs={"Rating": "1600 kVA", "Voltage": "11/0.4 kV"})
    ui.edit(by["load"][0]["id"], attrs={"Description": "Lights & small power", "Rating": "45 kW"})
    ui.edit(by["db"][0]["id"], attrs={"Rating": "250 A"})
    ui.edit(by["capacitor"][0]["id"], attrs={"Rating": "300 kvar"})
    ui.edit(by["generator"][0]["id"], attrs={"Rating": "1250 kVA", "Voltage": "0.4 kV"})
    # a cable label on the 11 kV incomer
    wid = [w for w in ui.proj()["wires"] if w["pts"][0] == [60, 110]][0]["id"]
    ui.edit(wid, label="3x(1C 300 mm2) XLPE")
    # drawing data
    ui.pg.evaluate("""()=>{const t=window.sld.editor.project.title; Object.assign(t,{project:'Demo Industrial Plant', title:'11/0.4 kV Substation SS-01', number:'E-SLD-001', rev:'B', company:'Acme Engineering', drawn:'SK', checked:'MJ', scale:'NTS', date:'2026-10-26'}); window.sld.editor.render()}""")
    return ui


def main():
    os.makedirs(OUT, exist_ok=True)
    srv = Server()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1600, "height": 950}, accept_downloads=True)
            ctx.add_init_script("delete window.showSaveFilePicker; delete window.showOpenFilePicker;")
            pg = ctx.new_page()
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            ui = UI(pg)
            ui.open(srv.url)
            build(pg)
            pg.keyboard.press("v")
            pg.keyboard.press("f")
            pg.keyboard.press("Escape")
            pg.screenshot(path=os.path.join(OUT, "screenshot.png"))
            # save through the real Save command
            with pg.expect_download() as dl:
                pg.keyboard.press("Control+s")
                pg.wait_for_selector("dialog input")
                pg.fill("dialog input", "sample")
                pg.click("dialog .btn.primary")
            dl.value.save_as(os.path.join(OUT, "sample.cad"))
            with pg.expect_download() as dl:
                pg.click("button.tb >> text=Export PDF")
            dl.value.save_as(os.path.join(OUT, "sample.pdf"))
            assert not errors, errors
            browser.close()
    finally:
        srv.stop()
    print("wrote", os.listdir(OUT))


if __name__ == "__main__":
    main()
