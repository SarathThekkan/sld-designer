"""Vector PDF export (reportlab) of a display list - 1:1 sheet size in mm."""

import io
import os

from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from . import config
from .render import build_display_list, sheet_size

_FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
_fonts_ready = False


def _fonts():
    global _fonts_ready
    if not _fonts_ready:
        pdfmetrics.registerFont(TTFont("SLD", os.path.join(_FONT_DIR, "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("SLD-Bold", os.path.join(_FONT_DIR, "DejaVuSans-Bold.ttf")))
        _fonts_ready = True


def draw_items(c, items, H):
    """Draw display-list items on a reportlab canvas; (0,0) is the sheet's top-left, y down."""
    dash = config.STYLE["dash"]
    c.setLineJoin(1)
    c.setLineCap(0)
    for it in items:
        k = it["k"]
        if k == "poly":
            pts = it["pts"]
            c.setLineWidth(it["w"] * mm)
            c.setDash([d * mm for d in dash] if it.get("dash") else [])
            p = c.beginPath()
            p.moveTo(pts[0][0] * mm, (H - pts[0][1]) * mm)
            for x, y in pts[1:]:
                p.lineTo(x * mm, (H - y) * mm)
            if it["closed"]:
                p.close()
            c.drawPath(p, stroke=1, fill=1 if it["fill"] else 0)
        elif k == "circle":
            c.setLineWidth(it["w"] * mm)
            c.setDash([])
            c.circle(it["c"][0] * mm, (H - it["c"][1]) * mm, it["r"] * mm, stroke=1, fill=1 if it["fill"] else 0)
        elif k == "text":
            size = it["size"]
            c.setFont("SLD-Bold" if it["bold"] else "SLD", size * mm)
            x, y = it["p"][0] * mm, (H - it["p"][1] - 0.35 * size) * mm
            if it["anchor"] == "middle":
                c.drawCentredString(x, y, it["s"])
            elif it["anchor"] == "end":
                c.drawRightString(x, y, it["s"])
            else:
                c.drawString(x, y, it["s"])


def export_pdf(project, library, path_or_none=None):
    """Return PDF bytes (and also write to path if given)."""
    _fonts()
    W, H = sheet_size(project["sheet"])
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W * mm, H * mm))
    t = project.get("title", {})
    c.setTitle(t.get("title") or "Single line diagram")
    c.setAuthor(t.get("drawn") or "")
    c.setSubject(t.get("project") or "")
    c.setCreator(f"{config.APP_NAME} {config.VERSION}")
    c.setStrokeColorRGB(0, 0, 0)
    c.setFillColorRGB(0, 0, 0)
    draw_items(c, build_display_list(project, library), H)
    c.showPage()
    c.save()
    data = buf.getvalue()
    if path_or_none:
        with open(path_or_none, "wb") as fh:
            fh.write(data)
    return data
