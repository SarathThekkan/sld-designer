"""Symbol validation and the persistent *user library*.

The user library lives in  ~/.sld_designer/user_symbols.json  (override with the
SLD_HOME environment variable).  It can be exported to / imported from
portable *.sldlib files so extra symbols can be shared between machines:

    {"format": "SLD-LIB", "version": 1, "symbols": [ {symbol}, ... ]}
"""

import json
import math
import os
import re
import tempfile

from . import config
from .symbols_builtin import BUILTIN, BUILTIN_BY_ID

ID_RE = re.compile(r"^[a-z0-9_\-]{1,48}$")
MAX_PRIMS = 400


class SymbolError(ValueError):
    pass


def _n(v, what, lo=-500, hi=500):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
        raise SymbolError(f"invalid number for {what}: {v!r}")
    return v


def _s(v, what, n=200):
    if not isinstance(v, str):
        raise SymbolError(f"{what} must be text")
    return v[:n]


def validate_prim(p):
    if not isinstance(p, dict) or p.get("t") not in config.PRIM_TYPES:
        raise SymbolError("unknown primitive")
    t = p["t"]
    out = {"t": t}
    if t == "line":
        for k in ("x1", "y1", "x2", "y2"):
            out[k] = _n(p.get(k), k)
    elif t == "poly":
        pts = p.get("pts")
        if not isinstance(pts, list) or not 2 <= len(pts) <= 200:
            raise SymbolError("poly needs 2..200 points")
        out["pts"] = [[_n(q[0], "x"), _n(q[1], "y")] for q in pts]
        out["closed"] = bool(p.get("closed"))
        out["fill"] = bool(p.get("fill"))
    elif t == "rect":
        for k in ("x", "y"):
            out[k] = _n(p.get(k), k)
        for k in ("w", "h"):
            out[k] = _n(p.get(k), k, 0, 1000)
        out["fill"] = bool(p.get("fill"))
    elif t == "circle":
        out["cx"], out["cy"] = _n(p.get("cx"), "cx"), _n(p.get("cy"), "cy")
        out["r"] = _n(p.get("r"), "r", 0, 500)
        out["fill"] = bool(p.get("fill"))
    elif t == "arc":
        out["cx"], out["cy"] = _n(p.get("cx"), "cx"), _n(p.get("cy"), "cy")
        out["r"] = _n(p.get("r"), "r", 0, 500)
        out["a0"], out["a1"] = _n(p.get("a0"), "a0", -3600, 3600), _n(p.get("a1"), "a1", -3600, 3600)
    elif t == "text":
        out["x"], out["y"] = _n(p.get("x"), "x"), _n(p.get("y"), "y")
        out["s"] = _s(p.get("s", ""), "text", 100)
        out["size"] = _n(p.get("size", 3.5), "size", 0.5, 50)
        out["bold"] = bool(p.get("bold"))
        a = p.get("anchor", "middle")
        out["anchor"] = a if a in ("start", "middle", "end") else "middle"
    if "lw" in p:
        out["lw"] = _n(p["lw"], "lw", 0.05, 5)
    if p.get("dash") and t != "circle":
        out["dash"] = True
    return out


def validate_symbol(d, require_id=True):
    """Return a sanitised symbol dict (without the 'builtin' flag) or raise SymbolError."""
    if not isinstance(d, dict):
        raise SymbolError("symbol must be an object")
    sid = d.get("id")
    if require_id or sid:
        if not isinstance(sid, str) or not ID_RE.match(sid):
            raise SymbolError("symbol id must be 1-48 chars of a-z 0-9 _ -")
    prims = d.get("prims")
    if not isinstance(prims, list) or not 1 <= len(prims) <= MAX_PRIMS:
        raise SymbolError("symbol needs 1..%d primitives" % MAX_PRIMS)
    terms = d.get("terminals", [])
    if not isinstance(terms, list) or len(terms) > 16:
        raise SymbolError("a symbol can have at most 16 terminals")
    out = {
        "id": sid,
        "name": _s(d.get("name") or sid, "name", 80),
        "category": _s(d.get("category") or "Custom", "category", 60),
        "prefix": re.sub(r"[^A-Za-z0-9]", "", str(d.get("prefix", "")))[:8],
        "keywords": str(d.get("keywords", ""))[:300],
        "prims": [validate_prim(p) for p in prims],
        "terminals": [],
        "attrs": [],
    }
    for t in terms:
        dx, dy = (t.get("d") or [0, 1])[:2]
        norm = math.hypot(_n(dx, "dir"), _n(dy, "dir")) or 1.0
        out["terminals"].append({"x": _n(t.get("x"), "terminal x"), "y": _n(t.get("y"), "terminal y"),
                                 "d": [round(dx / norm, 4), round(dy / norm, 4)],
                                 "n": _s(t.get("n", ""), "terminal name", 12)})
    for a in d.get("attrs", []) or []:
        out["attrs"].append({"key": _s(a.get("key", ""), "attr key", 40), "default": _s(a.get("default", ""), "attr default", 80)})
    return out


class UserLibrary:
    def __init__(self, home=None):
        self.home = home or os.environ.get("SLD_HOME") or os.path.join(os.path.expanduser("~"), ".sld_designer")
        self.path = os.path.join(self.home, "user_symbols.json")
        self.symbols = {}
        self.last_unchanged = []
        self.load()

    # -- persistence -------------------------------------------------------
    def load(self):
        self.symbols = {}
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            for s in data.get("symbols", []):
                try:
                    v = validate_symbol(s)
                    self.symbols[v["id"]] = v
                except SymbolError:
                    continue
        except (OSError, ValueError):
            pass

    def save(self):
        os.makedirs(self.home, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.home, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"format": config.LIBRARY_FORMAT, "version": config.LIBRARY_VERSION,
                       "symbols": list(self.symbols.values())}, fh, indent=1)
        os.replace(tmp, self.path)

    # -- queries -----------------------------------------------------------
    def all(self):
        out = [dict(s, builtin=True) for s in BUILTIN]
        out += [dict(s, builtin=False) for s in self.symbols.values()]
        return out

    def lookup(self):
        d = {s["id"]: s for s in BUILTIN}
        d.update(self.symbols)
        return d

    # -- edits -------------------------------------------------------------
    def put(self, sdef):
        s = validate_symbol(sdef)
        if s["id"] in BUILTIN_BY_ID:
            raise SymbolError("this id belongs to a built-in symbol; choose another name")
        self.symbols[s["id"]] = s
        self.save()
        return s

    def delete(self, sid):
        if sid in BUILTIN_BY_ID:
            raise SymbolError("built-in symbols cannot be deleted")
        if sid not in self.symbols:
            raise SymbolError("no such symbol")
        del self.symbols[sid]
        self.save()

    def unique_id(self, sid):
        base, i = sid, 2
        while sid in BUILTIN_BY_ID or sid in self.symbols:
            sid = f"{base}-{i}"
            i += 1
        return sid

    # -- import / export ---------------------------------------------------
    def export_text(self, ids=None):
        syms = [s for s in self.symbols.values() if ids is None or s["id"] in ids]
        return json.dumps({"format": config.LIBRARY_FORMAT, "version": config.LIBRARY_VERSION,
                           "symbols": syms}, indent=1)

    def import_data(self, data, overwrite=False):
        """Merge a parsed .sldlib. Returns (added, replaced, skipped_messages)."""
        if not isinstance(data, dict) or data.get("format") != config.LIBRARY_FORMAT:
            raise SymbolError("Not an SLD Designer symbol library (.sldlib).")
        added, replaced, problems = [], [], []
        self.last_unchanged = []
        for raw in data.get("symbols", []):
            try:
                s = validate_symbol(raw)
            except SymbolError as e:
                problems.append(str(e))
                continue
            if self.symbols.get(s["id"]) == s:      # identical symbol already in the library
                self.last_unchanged.append(s["id"])
                continue
            if s["id"] in self.symbols:
                if overwrite:
                    replaced.append(s["id"])
                else:
                    s["id"] = self.unique_id(s["id"])
                    added.append(s["id"])
            elif s["id"] in BUILTIN_BY_ID:
                s["id"] = self.unique_id(s["id"])
                added.append(s["id"])
            else:
                added.append(s["id"])
            self.symbols[s["id"]] = s
        self.save()
        return added, replaced, problems
