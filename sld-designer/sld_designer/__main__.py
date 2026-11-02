"""Command line:

    python -m sld_designer                      start the editor (opens your browser)
    python -m sld_designer export in.cad out.pdf    batch export (.pdf or .dxf)
    python -m sld_designer library --export my.sldlib | --import my.sldlib
"""

import argparse
import json
import os
import socket
import sys
import threading
import webbrowser

from . import config
from .dxf import export_dxf
from .library import SymbolError, UserLibrary
from .pdf import export_pdf
from .project import ProjectError, load


def _free_port(host, preferred):
    for port in range(preferred, preferred + 50):
        with socket.socket() as s:
            if s.connect_ex((host, port)) != 0:
                return port
    raise SystemExit("no free port found")


def cmd_serve(a):
    from .server import create_app
    host = "127.0.0.1"
    port = _free_port(host, a.port)
    app = create_app()
    url = f"http://{host}:{port}/"
    print(f"{config.APP_NAME} {config.VERSION} running at {url}  (Ctrl+C to quit)")
    if not a.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    app.run(host=host, port=port, threaded=True, debug=False)


def cmd_export(a):
    lib = UserLibrary()
    project = load(a.input)
    out = a.output
    if out.lower().endswith(".pdf"):
        export_pdf(project, lib.lookup(), out)
    elif out.lower().endswith(".dxf"):
        with open(out, "w", encoding="ascii") as fh:
            fh.write(export_dxf(project, lib.lookup()))
    else:
        raise SystemExit("output must end in .pdf or .dxf")
    print("written", out)


def cmd_library(a):
    lib = UserLibrary()
    if a.export:
        with open(a.export, "w", encoding="utf-8") as fh:
            fh.write(lib.export_text())
        print(f"exported {len(lib.symbols)} custom symbol(s) to {a.export}")
    if a.import_:
        with open(a.import_, "r", encoding="utf-8") as fh:
            added, replaced, problems = lib.import_data(json.load(fh), a.overwrite)
        print("added:", added, "replaced:", replaced, "problems:", problems)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="sld_designer", description=config.APP_NAME)
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("serve", help="start the editor (default)")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-browser", action="store_true")
    s.set_defaults(fn=cmd_serve)
    e = sub.add_parser("export", help="export a .cad file to .pdf or .dxf")
    e.add_argument("input")
    e.add_argument("output")
    e.set_defaults(fn=cmd_export)
    l = sub.add_parser("library", help="export / import custom symbol libraries (.sldlib)")
    l.add_argument("--export")
    l.add_argument("--import", dest="import_")
    l.add_argument("--overwrite", action="store_true")
    l.set_defaults(fn=cmd_library)
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv or (argv[0].startswith("-") and argv[0] not in ("-h", "--help")):
        argv = ["serve"] + argv                      # `python -m sld_designer --port 9000`
    a = ap.parse_args(argv)
    try:
        a.fn(a)
    except (ProjectError, SymbolError, OSError, ValueError) as ex:
        print("error:", ex, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
