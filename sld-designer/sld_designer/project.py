"""Project (.cad) model: creation, validation and (de)serialisation.

A .cad file is UTF-8 JSON:

    {"format": "SLD-CAD", "version": 1, "meta": {...},
     "sheet": {"size", "orientation", "grid", "snap", "showGrid"},
     "title": {...title block fields...},
     "symbols":  {id: symbol definition}       # every symbol used, so the file is self-contained
     "elements": [...], "wires": [...], "nextId": int}
"""

import datetime
import json
import math
import re

from . import config
from .library import validate_symbol

MAX_ELEMENTS = 20000
MAX_TEXT = 2000
TITLE_KEYS = [c[4] for c in config.TITLEBLOCK["cells"]]


class ProjectError(ValueError):
    pass


def new_project():
    today = datetime.date.today().isoformat()
    return {
        "format": config.PROJECT_FORMAT, "version": config.PROJECT_VERSION,
        "meta": {"app": f"{config.APP_NAME} {config.VERSION}", "modified": today},
        "sheet": {"size": "A3", "orientation": "landscape", "grid": 5, "snap": True, "showGrid": True},
        "title": {"project": "", "title": "Single Line Diagram", "number": "SLD-001", "rev": "A",
                  "date": today, "company": "", "drawn": "", "checked": "", "scale": "NTS",
                  "sheet": "1 / 1"},
        "symbols": {}, "elements": [], "wires": [], "nextId": 1,
    }


def _num(v, what, lo=-1e5, hi=1e5):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
        raise ProjectError(f"invalid number for {what}: {v!r}")
    return v


def _str(v, what="text", n=MAX_TEXT):
    if v is None:
        return ""
    if not isinstance(v, (str, int, float)):
        raise ProjectError(f"invalid {what}")
    return str(v)[:n]


def _id(v):
    if not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9_\-]{1,32}", v):
        raise ProjectError(f"invalid id: {v!r}")
    return v


def _pt(p, what="point"):
    if not isinstance(p, (list, tuple)) or len(p) != 2:
        raise ProjectError(f"invalid {what}")
    return [_num(p[0], what), _num(p[1], what)]


def _ref(r):
    if r is None:
        return None
    if not isinstance(r, dict):
        raise ProjectError("invalid wire connection")
    out = {"el": _id(r.get("el"))}
    if "t" in r:
        out["t"] = int(_num(r["t"], "terminal", 0, 1000))
    elif "s" in r:
        out["s"] = _num(r["s"], "bus offset", 0, 1e5)
    else:
        raise ProjectError("wire connection needs 't' or 's'")
    return out


def _element(e):
    if not isinstance(e, dict):
        raise ProjectError("element must be an object")
    t = e.get("type")
    if t not in config.ELEMENT_TYPES:
        raise ProjectError(f"unknown element type {t!r}")
    out = {"id": _id(e.get("id")), "type": t}
    if t in ("sym", "bus", "rect", "text"):
        out["x"] = _num(e.get("x"), "x")
        out["y"] = _num(e.get("y"), "y")
    if t in ("sym", "bus"):
        out["rot"] = int(_num(e.get("rot", 0), "rot")) % 360
        out["tag"] = _str(e.get("tag", ""), "tag", 64)
        attrs = e.get("attrs") or {}
        if not isinstance(attrs, dict) or len(attrs) > 64:
            raise ProjectError("invalid attrs")
        out["attrs"] = {_str(k, "attr key", 64): _str(v, "attr value", 200) for k, v in attrs.items()}
        lp = e.get("lp", "r" if t == "sym" else "l")
        out["lp"] = lp if lp in ("r", "l", "t", "b") else "r"
        if e.get("lo"):
            lo = e["lo"]
            if not isinstance(lo, (list, tuple)) or len(lo) != 2:
                raise ProjectError("invalid label offset")
            out["lo"] = [_num(lo[0], "label offset", -500, 500), _num(lo[1], "label offset", -500, 500)]
    if t == "sym":
        out["sym"] = _str(e.get("sym"), "symbol id", 64)
        out["mirror"] = bool(e.get("mirror", False))
    elif t == "bus":
        out["len"] = _num(e.get("len"), "len", 0, 1e5)
        if out["rot"] not in (0, 90):
            out["rot"] = 0
    elif t == "rect":
        out["w"] = _num(e.get("w"), "w", 0, 1e5)
        out["h"] = _num(e.get("h"), "h", 0, 1e5)
        out["dash"] = bool(e.get("dash", False))
        if "lw" in e:
            out["lw"] = _num(e["lw"], "lw", 0.05, 5)
    elif t == "line":
        pts = e.get("pts")
        if not isinstance(pts, list) or len(pts) < 2 or len(pts) > 500:
            raise ProjectError("invalid line")
        out["pts"] = [_pt(p) for p in pts]
        out["dash"] = bool(e.get("dash", False))
        if "lw" in e:
            out["lw"] = _num(e["lw"], "lw", 0.05, 5)
    elif t == "text":
        out["s"] = _str(e.get("s", ""))
        out["size"] = _num(e.get("size", config.STYLE["text_size"]), "size", 0.5, 100)
        out["bold"] = bool(e.get("bold", False))
        a = e.get("anchor", "start")
        out["anchor"] = a if a in ("start", "middle", "end") else "start"
    return out


def _wire(w):
    if not isinstance(w, dict):
        raise ProjectError("wire must be an object")
    pts = w.get("pts")
    if not isinstance(pts, list) or len(pts) < 2 or len(pts) > 500:
        raise ProjectError("invalid wire points")
    return {"id": _id(w.get("id")), "pts": [_pt(p) for p in pts],
            "a": _ref(w.get("a")), "b": _ref(w.get("b")), "label": _str(w.get("label", ""), "label", 400)}


def validate_project(data):
    """Return a sanitised copy of `data` or raise ProjectError."""
    if not isinstance(data, dict) or data.get("format") != config.PROJECT_FORMAT:
        raise ProjectError("Not an SLD Designer .cad file (missing format marker).")
    if int(data.get("version", 0) or 0) > config.PROJECT_VERSION:
        raise ProjectError("This file was written by a newer version of SLD Designer.")
    base = new_project()
    sheet = data.get("sheet") or {}
    size = sheet.get("size", "A3")
    if size not in config.SHEETS:
        raise ProjectError(f"unknown sheet size {size!r}")
    grid = _num(sheet.get("grid", 5), "grid", 0.5, 50)
    out = {
        "format": config.PROJECT_FORMAT, "version": config.PROJECT_VERSION,
        "meta": {"app": _str((data.get("meta") or {}).get("app", ""), "meta", 100),
                 "modified": _str((data.get("meta") or {}).get("modified", ""), "meta", 40)},
        "sheet": {"size": size,
                  "orientation": "portrait" if sheet.get("orientation") == "portrait" else "landscape",
                  "grid": grid, "snap": bool(sheet.get("snap", True)),
                  "showGrid": bool(sheet.get("showGrid", True))},
        "title": {k: _str((data.get("title") or {}).get(k, base["title"][k] if k in ("rev",) else ""),
                          "title field", 200) for k in TITLE_KEYS},
    }
    syms = data.get("symbols") or {}
    if not isinstance(syms, dict) or len(syms) > 1000:
        raise ProjectError("invalid symbols section")
    out["symbols"] = {}
    for sid, sdef in syms.items():
        s = validate_symbol(sdef, require_id=True)
        out["symbols"][s["id"]] = s
    els = data.get("elements") or []
    wires = data.get("wires") or []
    if not isinstance(els, list) or not isinstance(wires, list) or len(els) + len(wires) > MAX_ELEMENTS:
        raise ProjectError("invalid or too many elements")
    out["elements"] = [_element(e) for e in els]
    out["wires"] = [_wire(w) for w in wires]
    ids = [e["id"] for e in out["elements"]] + [w["id"] for w in out["wires"]]
    if len(set(ids)) != len(ids):
        raise ProjectError("duplicate element ids")
    out["nextId"] = int(_num(data.get("nextId", len(ids) + 1), "nextId", 1, 1e9))
    return out


def loads(text):
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as e:
        raise ProjectError(f"File is not valid JSON: {e}")
    return validate_project(data)


def load(path):
    with open(path, "r", encoding="utf-8") as fh:
        return loads(fh.read())


def dumps(project):
    return json.dumps(project, indent=1, ensure_ascii=False)


def save(project, path):
    p = validate_project(project)
    p["meta"]["modified"] = datetime.datetime.now().isoformat(timespec="seconds")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(dumps(p))
