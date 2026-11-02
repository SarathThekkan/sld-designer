"""Helpers for driving the editor with real mouse/keyboard events through Playwright."""
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    """Runs `python -m sld_designer serve` with a throw-away library directory."""

    def __init__(self):
        self.home = tempfile.mkdtemp(prefix="sld_home_")
        self.port = free_port()
        env = dict(os.environ, SLD_HOME=self.home, PYTHONPATH=os.pathsep.join([ROOT] + [p for p in sys.path if p]))
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "sld_designer", "serve", "--no-browser", "--port", str(self.port)],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.url = f"http://127.0.0.1:{self.port}/"
        for _ in range(100):
            try:
                urllib.request.urlopen(self.url + "api/config", timeout=0.5).read()
                return
            except Exception:
                time.sleep(0.1)
        raise RuntimeError("server did not start")

    def stop(self):
        self.proc.terminate()
        self.proc.wait(5)


class UI:
    def __init__(self, page):
        self.pg = page

    def open(self, url):
        self.pg.goto(url)
        self.pg.wait_for_function("window.sld && window.sld.ready")

    def px(self, x, y):
        v = self.pg.evaluate("(()=>{const e=window.sld.editor;const r=e.svg.getBoundingClientRect();return [r.left+e.view.tx,r.top+e.view.ty,e.view.k]})()")
        return v[0] + x * v[2], v[1] + y * v[2]

    def click(self, x, y, **kw):
        self.pg.mouse.click(*self.px(x, y), **kw)

    def move(self, x, y):
        self.pg.mouse.move(*self.px(x, y))

    def drag(self, x1, y1, x2, y2, steps=8):
        self.pg.mouse.move(*self.px(x1, y1))
        self.pg.mouse.down()
        self.pg.mouse.move(*self.px(x2, y2), steps=steps)
        self.pg.mouse.up()

    def place(self, sym, x, y, rot=0, mirror=False):
        self.pg.click(f'.sym[data-id="{sym}"]')
        for _ in range(rot // 90):
            self.pg.keyboard.press("r")
        if mirror:
            self.pg.keyboard.press("m")
        self.move(x, y)
        self.click(x, y)
        self.pg.keyboard.press("Escape")

    def bus(self, x1, y1, x2, y2):
        self.pg.keyboard.press("b")
        self.drag(x1, y1, x2, y2)
        self.pg.keyboard.press("Escape")

    def wire(self, *pts):
        self.pg.keyboard.press("w")
        for x, y in pts:
            self.move(x, y)
            self.click(x, y)
        self.pg.keyboard.press("Escape")
        self.pg.keyboard.press("Escape")

    def rect(self, x1, y1, x2, y2):
        self.pg.keyboard.press("x")
        self.drag(x1, y1, x2, y2)
        self.pg.keyboard.press("Escape")

    def text(self, x, y, s, size=None, bold=False, anchor="start"):
        self.pg.keyboard.press("t")
        self.move(x, y)
        self.click(x, y)
        self.pg.wait_for_selector("dialog textarea")
        self.pg.fill("dialog textarea", s)
        self.pg.click("dialog .btn.primary")
        self.pg.keyboard.press("Escape")
        self.pg.evaluate("([s,b,a])=>{const e=window.sld.editor;const t=e.project.elements[e.project.elements.length-1];"
                         "if(s)t.size=s;t.bold=b;t.anchor=a;e.render()}", [size, bold, anchor])

    def proj(self):
        return self.pg.evaluate("JSON.parse(JSON.stringify(window.sld.editor.project))")

    def edit(self, el_id, **fields):
        """Programmatic property edit (as the properties panel would do)."""
        self.pg.evaluate("([i,f])=>{const e=window.sld.editor;const o=e.find(i);"
                         "for(const [k,v] of Object.entries(f)){ if(k==='attrs') Object.assign(o.attrs,v); else o[k]=v;} e.render()}", [el_id, fields])

    def last_id(self):
        return self.pg.evaluate("(()=>{const e=window.sld.editor;return e.project.elements[e.project.elements.length-1].id})()")
