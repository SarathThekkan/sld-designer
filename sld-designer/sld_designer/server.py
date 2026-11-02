"""Local web server: serves the editor and the JSON/PDF/DXF API (bound to 127.0.0.1 only)."""

import json
import os
import re

from flask import Flask, Response, jsonify, request, send_from_directory

from . import config
from .dxf import export_dxf
from .library import SymbolError, UserLibrary, validate_symbol
from .pdf import export_pdf
from .project import ProjectError, validate_project

STATIC = os.path.join(os.path.dirname(__file__), "static")
FONTS = os.path.join(os.path.dirname(__file__), "fonts")
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}


def create_app(home=None):
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024
    lib = UserLibrary(home)
    app.sld_library = lib

    @app.before_request
    def guard():
        # Only answer requests addressed to localhost (blocks DNS-rebinding) and require a
        # custom header on every state-changing / data request (blocks cross-site form posts).
        host = (request.host or "").rsplit(":", 1)[0] if not request.host.startswith("[") else request.host.split("]")[0] + "]"
        if host not in LOCAL_HOSTS:
            return jsonify(error="forbidden host"), 403
        if request.method != "GET" and request.headers.get("X-SLD-Client") != "1":
            return jsonify(error="missing X-SLD-Client header"), 403

    @app.after_request
    def no_cache(resp):
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    @app.errorhandler(ProjectError)
    @app.errorhandler(SymbolError)
    def bad(e):
        return jsonify(error=str(e)), 400

    # ----------------------------------------------------------------- pages
    @app.get("/")
    def index():
        return send_from_directory(STATIC, "index.html")

    @app.get("/static/<path:name>")
    def static_files(name):
        return send_from_directory(STATIC, name)

    @app.get("/fonts/<path:name>")
    def font_files(name):
        if not name.endswith(".ttf"):
            return jsonify(error="not found"), 404
        return send_from_directory(FONTS, name)

    # ------------------------------------------------------------------- api
    @app.get("/api/config")
    def get_config():
        return jsonify(version=config.VERSION, app=config.APP_NAME, style=config.STYLE,
                       sheets=config.SHEETS, titleblock=config.TITLEBLOCK,
                       project_format=config.PROJECT_FORMAT, project_version=config.PROJECT_VERSION)

    @app.get("/api/symbols")
    def get_symbols():
        return jsonify(symbols=lib.all())

    @app.post("/api/symbols")
    def put_symbol():
        data = request.get_json(force=True, silent=True)
        if not isinstance(data, dict):
            raise SymbolError("expected a JSON object")
        if not data.get("id"):
            slug = re.sub(r"[^a-z0-9]+", "-", str(data.get("name", "symbol")).lower()).strip("-") or "symbol"
            data["id"] = lib.unique_id("u-" + slug)
        saved = lib.put(data)
        return jsonify(symbol=dict(saved, builtin=False))

    @app.delete("/api/symbols/<sid>")
    def del_symbol(sid):
        lib.delete(sid)
        return jsonify(ok=True)

    @app.post("/api/library/import")
    def import_lib():
        body = request.get_json(force=True, silent=True) or {}
        added, replaced, problems = lib.import_data(body.get("data"), bool(body.get("overwrite")))
        return jsonify(added=added, replaced=replaced, unchanged=lib.last_unchanged, problems=problems, symbols=lib.all())

    @app.get("/api/library/export")
    def export_lib():
        ids = request.args.get("ids")
        ids = set(ids.split(",")) if ids else None
        return Response(lib.export_text(ids), mimetype="application/json",
                        headers={"Content-Disposition": 'attachment; filename="symbols.sldlib"'})

    @app.post("/api/project/validate")
    def validate():
        return jsonify(project=validate_project(request.get_json(force=True, silent=True)))

    def _project_from_body():
        return validate_project(request.get_json(force=True, silent=True))

    @app.post("/api/export/pdf")
    def pdf():
        data = export_pdf(_project_from_body(), lib.lookup())
        return Response(data, mimetype="application/pdf")

    @app.post("/api/export/dxf")
    def dxf():
        text = export_dxf(_project_from_body(), lib.lookup())
        return Response(text, mimetype="application/dxf")

    return app
