// editor.js - the drawing canvas: view, tools, snapping, selection, wire routing, undo/redo.
import {
  ST, SHEETS, r4, tfPoint, termWorld, termDir, busEnds, elementItems, elementBBox, symbolItems,
  buildDisplayList, itemsSvg, sheetSize, symbolLookup, distSeg, nearestOnSeg, simplify, route, axisOf,
  samePt, wireItems,
} from './core.js';

const SVGNS = 'http://www.w3.org/2000/svg';
const clone = (o) => JSON.parse(JSON.stringify(o));

export const TOOL_HINTS = {
  select: 'Click to select, drag to move, drag on empty space for a selection box. R rotate, M mirror, Del delete.',
  pan: 'Drag to pan the view. (Middle mouse button or Space+drag also pan in any tool.)',
  place: 'Click to place. R rotates, M mirrors, Esc stops placing.',
  wire: 'Click a terminal or grid point to start; click to add corners; click a terminal / busbar to finish. Enter or right-click ends. Space flips the corner.',
  bus: 'Click-drag (or click twice) to draw a busbar. Esc to stop.',
  rect: 'Click-drag (or click twice) to draw a dashed enclosure rectangle. Esc to stop.',
  line: 'Click points; double-click / Enter / right-click ends. Hold Shift for free angles.',
  text: 'Click where the text should go.',
};

export class Editor {
  constructor(svg, hooks = {}) {
    this.svg = svg;
    this.hooks = hooks;
    this.library = new Map();
    this.project = null;
    this.sel = new Set();
    this.tool = 'select';
    this.placing = null;
    this.view = { tx: 0, ty: 0, k: 2 };
    this.mouse = [0, 0];
    this.snap = { x: 0, y: 0, kind: 'grid' };
    this.drag = null;
    this.draft = null;
    this.undoStack = [];
    this.redoStack = [];
    this.dirty = false;
    this.clipboard = null;
    this.pasteCount = 0;
    this.spaceDown = false;
    this.flip = false;
    this._buildSvg();
    this._bind();
    this.symbols = (id) => symbolLookup(this.project, this.library)(id);
  }

  // ------------------------------------------------------------------ setup
  _buildSvg() {
    const s = this.svg;
    s.innerHTML = `<defs><pattern id="gridpat" patternUnits="userSpaceOnUse" width="5" height="5"><circle cx="0" cy="0" r="0.2"/></pattern></defs>
      <g id="view"><rect id="paper"/><rect id="gridrect" fill="url(#gridpat)" style="fill:url(#gridpat)"/>
      <g id="content"></g><g id="overlay"></g></g>`;
    this.gView = s.querySelector('#view');
    this.gContent = s.querySelector('#content');
    this.gOverlay = s.querySelector('#overlay');
    this.paper = s.querySelector('#paper');
    this.gridRect = s.querySelector('#gridrect');
    this.gridPat = s.querySelector('#gridpat');
  }

  setProject(p, { keepView = false } = {}) {
    this.project = p;
    this.sel = new Set();
    this.draft = null;
    this.drag = null;
    this.undoStack = [];
    this.redoStack = [];
    this.refreshWires();
    this.setDirty(false);
    if (!keepView) this.fit(); else this.render();
    this.hooks.onSelection?.();
    this.hooks.onHistory?.();
  }

  setDirty(v) { this.dirty = v; this.hooks.onDirty?.(v); }

  // ------------------------------------------------------------------- view
  size() { const r = this.svg.getBoundingClientRect(); return [r.width, r.height]; }
  toMM(ev) {
    const r = this.svg.getBoundingClientRect();
    return [(ev.clientX - r.left - this.view.tx) / this.view.k, (ev.clientY - r.top - this.view.ty) / this.view.k];
  }
  fit() {
    const [W, H] = sheetSize(this.project.sheet);
    const [vw, vh] = this.size();
    const k = Math.min((vw - 40) / W, (vh - 40) / H);
    this.view.k = Math.max(0.2, k);
    this.view.tx = (vw - W * this.view.k) / 2;
    this.view.ty = (vh - H * this.view.k) / 2;
    this.render();
  }
  zoomAt(factor, cx, cy) {
    const [vw, vh] = this.size();
    cx = cx ?? vw / 2; cy = cy ?? vh / 2;
    const k0 = this.view.k;
    const k1 = Math.min(80, Math.max(0.15, k0 * factor));
    this.view.tx = cx - (cx - this.view.tx) * (k1 / k0);
    this.view.ty = cy - (cy - this.view.ty) * (k1 / k0);
    this.view.k = k1;
    this.render();
  }
  applyView() { this.gView.setAttribute('transform', `translate(${this.view.tx} ${this.view.ty}) scale(${this.view.k})`); }

  // ----------------------------------------------------------------- tools
  setTool(t, opts = {}) {
    if (this.tool === 'line' && this.draft) this.finishLine();
    if (this.tool === 'wire' && this.draft) this.finishWire(null, true);
    this.tool = t;
    this.draft = null;
    this.drag = null;
    this.placing = t === 'place' ? { sym: opts.sym, rot: 0, mirror: false } : null;
    this.svg.dataset.tool = t;
    this.hooks.onTool?.(t, opts);
    this.renderOverlay();
  }
  cancelTool() {
    if (this.draft) { if (this.tool === 'wire') this.finishWire(null, true); else if (this.tool === 'line') this.finishLine(); else this.draft = null; this.renderOverlay(); return; }
    if (this.tool !== 'select') this.setTool('select');
    else { this.sel = new Set(); this.hooks.onSelection?.(); this.render(); }
  }

  // ------------------------------------------------------------ project ops
  uid(prefix) { return prefix + (this.project.nextId++); }
  grid() { return this.project.sheet.grid || 5; }
  snapVal(v) {
    if (!this.project.sheet.snap) return r4(v);
    const g = this.grid();
    return r4(Math.round(v / g) * g);
  }
  checkpoint() {
    this.undoStack.push(JSON.stringify(this.project));
    if (this.undoStack.length > 300) this.undoStack.shift();
    this.redoStack = [];
    this.hooks.onHistory?.();
  }
  _restore(str) {
    this.project = JSON.parse(str);
    const ids = new Set([...this.project.elements, ...this.project.wires].map(e => e.id));
    this.sel = new Set([...this.sel].filter(i => ids.has(i)));
    this.setDirty(true);
    this.render();
    this.hooks.onSelection?.();
    this.hooks.onHistory?.();
  }
  undo() { if (!this.undoStack.length) return; this.redoStack.push(JSON.stringify(this.project)); this._restore(this.undoStack.pop()); }
  redo() { if (!this.redoStack.length) return; this.undoStack.push(JSON.stringify(this.project)); this._restore(this.redoStack.pop()); }
  /** Run fn(project) as one undoable change. */
  mutate(fn, { noCheckpoint = false, quiet = false } = {}) {
    if (!noCheckpoint) this.checkpoint();
    fn(this.project);
    this.refreshWires();
    this.setDirty(true);
    this.render();
    if (!quiet) this.hooks.onSelection?.();
  }
  find(id) { return this.project.elements.find(e => e.id === id) || this.project.wires.find(w => w.id === id); }
  nextTag(prefix) {
    if (!prefix) return '';
    let max = 0;
    const re = new RegExp('^' + prefix.replace(/[^A-Za-z0-9]/g, '') + '(\\d+)$');
    for (const e of this.project.elements) { const m = re.exec(e.tag || ''); if (m) max = Math.max(max, +m[1]); }
    return prefix + (max + 1);
  }

  // ------------------------------------------------------- terminals & snap
  allTerminals() {
    const out = [];
    for (const el of this.project.elements) {
      if (el.type !== 'sym') continue;
      const sym = this.symbols(el.sym);
      if (!sym) continue;
      sym.terminals.forEach((t, i) => out.push({ el, i, p: termWorld(sym, el, i), d: termDir(sym, el, i) }));
    }
    return out;
  }
  resolveRef(ref) {
    if (!ref) return null;
    const el = this.project.elements.find(e => e.id === ref.el);
    if (!el) return null;
    if (el.type === 'sym') {
      const sym = this.symbols(el.sym);
      if (!sym || ref.t >= sym.terminals.length) return null;
      return termWorld(sym, el, ref.t);
    }
    if (el.type === 'bus') {
      const [a, b] = busEnds(el);
      const s = Math.min(Math.max(ref.s, 0), el.len);
      return (el.rot || 0) % 180 === 0 ? [a[0] + s, a[1]] : [a[0], a[1] + s];
    }
    return null;
  }
  refAxis(ref) {
    if (!ref) return null;
    const el = this.project.elements.find(e => e.id === ref.el);
    if (!el) return null;
    if (el.type === 'sym') { const sym = this.symbols(el.sym); return sym && ref.t < sym.terminals.length ? axisOf(termDir(sym, el, ref.t)) : null; }
    if (el.type === 'bus') return (el.rot || 0) % 180 === 0 ? 'v' : 'h';
    return null;
  }
  snapPoint(p, { wire = false, exclude = null } = {}) {
    const k = this.view.k;
    const tol = Math.max(2.5, 10 / k);
    let best = null, bd = tol;
    for (const t of this.allTerminals()) {
      const d = Math.hypot(t.p[0] - p[0], t.p[1] - p[1]);
      if (d < bd) { bd = d; best = { x: t.p[0], y: t.p[1], kind: 'term', ref: { el: t.el.id, t: t.i }, axis: axisOf(t.d) }; }
    }
    if (best) return best;
    for (const el of this.project.elements) {
      if (el.type !== 'bus') continue;
      const [a, b] = busEnds(el);
      const [qx, qy] = nearestOnSeg(p, a, b);
      if (Math.hypot(qx - p[0], qy - p[1]) <= Math.min(tol, 3)) {
        const horiz = (el.rot || 0) % 180 === 0;
        const along = horiz ? p[0] - a[0] : p[1] - a[1];
        // snap the absolute coordinate to the grid so the wire lands on a grid point
        const abs = horiz ? this.snapVal(a[0] + along) - a[0] : this.snapVal(a[1] + along) - a[1];
        const ss = Math.min(el.len, Math.max(0, abs));
        const pos = (el.rot || 0) % 180 === 0 ? [a[0] + ss, a[1]] : [a[0], a[1] + ss];
        return { x: pos[0], y: pos[1], kind: 'bus', ref: { el: el.id, s: r4(ss) }, axis: (el.rot || 0) % 180 === 0 ? 'v' : 'h' };
      }
    }
    if (wire) {
      for (const w of this.project.wires) {
        if (w === exclude) continue;
        for (let i = 0; i < w.pts.length - 1; i++) {
          const a = w.pts[i], b = w.pts[i + 1];
          if (distSeg(p, a, b) <= Math.min(tol, 2.5)) {
            const horiz = Math.abs(a[1] - b[1]) < 1e-6;
            const q = horiz ? [this.snapVal(p[0]), a[1]] : [a[0], this.snapVal(p[1])];
            if (distSeg(q, a, b) < 1e-6) return { x: q[0], y: q[1], kind: 'wire', ref: null, axis: horiz ? 'v' : 'h' };
          }
        }
      }
    }
    return { x: this.snapVal(p[0]), y: this.snapVal(p[1]), kind: 'grid', ref: null, axis: null };
  }

  // ---------------------------------------------------------- wire geometry
  setWireEnd(w, which, pos) {
    const pts = w.pts;
    const i = which === 'a' ? 0 : pts.length - 1;
    const j = which === 'a' ? 1 : pts.length - 2;
    const old = pts[i];
    if (samePt(old, pos)) return;
    if (pts.length === 2) {
      pts[i] = [pos[0], pos[1]];
      this.rerouteTwoPoint(w);
      return;
    }
    const nb = pts[j];
    const horiz = Math.abs(old[1] - nb[1]) < 1e-6;
    const vert = Math.abs(old[0] - nb[0]) < 1e-6;
    pts[i] = [pos[0], pos[1]];
    if (horiz && !vert) nb[1] = pos[1];
    else if (vert && !horiz) nb[0] = pos[0];
    w.pts = simplify(pts);
    if (w.pts.length === 2) this.rerouteTwoPoint(w);
  }
  rerouteTwoPoint(w) {
    const a = w.pts[0], b = w.pts[w.pts.length - 1];
    if (Math.abs(a[0] - b[0]) < 1e-6 || Math.abs(a[1] - b[1]) < 1e-6) { w.pts = [a, b]; return; }
    const g = this.grid();
    w.pts = [a, ...route(a, b, this.refAxis(w.a), this.refAxis(w.b), (v) => this.snapVal(v))];
    w.pts = simplify(w.pts);
  }
  autoRoute(w) {
    const a = this.resolveRef(w.a) || w.pts[0], b = this.resolveRef(w.b) || w.pts[w.pts.length - 1];
    w.pts = simplify([a, ...route(a, b, this.refAxis(w.a), this.refAxis(w.b), (v) => this.snapVal(v))]);
  }
  refreshWires() {
    for (const w of this.project.wires) {
      if (w.a) { const p = this.resolveRef(w.a); if (p) this.setWireEnd(w, 'a', p); else w.a = null; }
      if (w.b) { const p = this.resolveRef(w.b); if (p) this.setWireEnd(w, 'b', p); else w.b = null; }
    }
  }

  // ------------------------------------------------------------- hit testing
  tol() { return Math.max(1.0, 6 / this.view.k); }
  hitTest(p) {
    const tol = this.tol();
    const els = this.project.elements;
    for (let i = els.length - 1; i >= 0; i--) {
      const el = els[i];
      if (el.type === 'sym' || el.type === 'text') {
        const [x0, y0, x1, y1] = elementBBox(el, this.symbols);
        if (p[0] >= x0 - tol / 2 && p[0] <= x1 + tol / 2 && p[1] >= y0 - tol / 2 && p[1] <= y1 + tol / 2) return el.id;
      } else if (el.type === 'bus') {
        const [a, b] = busEnds(el);
        if (distSeg(p, a, b) <= Math.max(tol, 1.2)) return el.id;
      }
    }
    const ws = this.project.wires;
    for (let i = ws.length - 1; i >= 0; i--) {
      const w = ws[i];
      for (let j = 0; j < w.pts.length - 1; j++) if (distSeg(p, w.pts[j], w.pts[j + 1]) <= tol) return w.id;
    }
    for (let i = els.length - 1; i >= 0; i--) {
      const el = els[i];
      if (el.type === 'rect') {
        const { x, y, w, h } = el;
        const c = [[x, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y]];
        for (let j = 0; j < 4; j++) if (distSeg(p, c[j], c[j + 1]) <= tol) return el.id;
      } else if (el.type === 'line') {
        for (let j = 0; j < el.pts.length - 1; j++) if (distSeg(p, el.pts[j], el.pts[j + 1]) <= tol) return el.id;
      }
    }
    return null;
  }
  bboxOf(id) {
    const el = this.project.elements.find(e => e.id === id);
    if (el) return elementBBox(el, this.symbols);
    const w = this.project.wires.find(e => e.id === id);
    if (w) { const xs = w.pts.map(p => p[0]), ys = w.pts.map(p => p[1]); return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)]; }
    return null;
  }
  selectionBBox() {
    let b = null;
    for (const id of this.sel) {
      const bb = this.bboxOf(id);
      if (!bb) continue;
      b = b ? [Math.min(b[0], bb[0]), Math.min(b[1], bb[1]), Math.max(b[2], bb[2]), Math.max(b[3], bb[3])] : bb.slice();
    }
    return b;
  }
  setSelection(ids) { this.sel = new Set(ids); this.hooks.onSelection?.(); this.render(); }

  // -------------------------------------------------------------- selection handles
  handles() {
    if (this.sel.size !== 1 || this.tool !== 'select') return [];
    const id = [...this.sel][0];
    const w = this.project.wires.find(x => x.id === id);
    const out = [];
    if (w) {
      for (let i = 1; i < w.pts.length - 2; i++) {
        const a = w.pts[i], b = w.pts[i + 1];
        out.push({ type: 'seg', id, i, p: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], horiz: Math.abs(a[1] - b[1]) < 1e-6 });
      }
      return out;
    }
    const el = this.project.elements.find(x => x.id === id);
    if (el && el.type === 'bus') {
      const [a, b] = busEnds(el);
      out.push({ type: 'busA', id, p: a }, { type: 'busB', id, p: b });
    }
    return out;
  }

  // ------------------------------------------------------------------ events
  _bind() {
    const s = this.svg;
    s.addEventListener('pointerdown', (e) => this.onDown(e));
    s.addEventListener('pointermove', (e) => this.onMove(e));
    s.addEventListener('pointerup', (e) => this.onUp(e));
    s.addEventListener('dblclick', (e) => this.onDbl(e));
    s.addEventListener('contextmenu', (e) => { e.preventDefault(); this.onRight(); });
    s.addEventListener('wheel', (e) => {
      e.preventDefault();
      const r = s.getBoundingClientRect();
      this.zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - r.left, e.clientY - r.top);
    }, { passive: false });
    window.addEventListener('keydown', (e) => this.onKey(e));
    window.addEventListener('keyup', (e) => { if (e.code === 'Space') this.spaceDown = false; });
    new ResizeObserver(() => this.render()).observe(s);
  }

  onRight() {
    if (this.draft) { this.cancelTool(); return; }
    if (this.tool !== 'select') this.setTool('select');
  }

  onDown(e) {
    if (!this.project) return;
    this.svg.setPointerCapture(e.pointerId);
    const raw = this.toMM(e);
    const panning = e.button === 1 || this.spaceDown || this.tool === 'pan';
    if (e.button === 2) return;
    if (panning) { this.drag = { type: 'pan', sx: e.clientX, sy: e.clientY, tx: this.view.tx, ty: this.view.ty }; return; }
    if (e.button !== 0) return;
    const t = this.tool;
    if (t === 'select') return this.downSelect(e, raw);
    if (t === 'place') return this.placeAt(raw);
    if (t === 'wire') return this.downWire(raw);
    if (t === 'bus' || t === 'rect') return this.downBox(raw, t);
    if (t === 'line') return this.downLine(e, raw);
    if (t === 'text') return this.downText(raw);
  }

  onMove(e) {
    if (!this.project) return;
    const raw = this.toMM(e);
    this.mouse = raw;
    this.shiftDown = e.shiftKey;
    const d = this.drag;
    if (d && d.type === 'pan') {
      this.view.tx = d.tx + (e.clientX - d.sx); this.view.ty = d.ty + (e.clientY - d.sy);
      this.render();
      return;
    }
    const wireish = this.tool === 'wire';
    this.snap = this.snapPoint(raw, { wire: wireish });
    if (this.tool === 'select') this.moveSelect(e, raw);
    else if (this.tool === 'bus' || this.tool === 'rect') this.renderOverlay();
    else this.renderOverlay();
    this.hooks.onStatus?.(this.snap, raw);
  }

  onUp(e) {
    const d = this.drag;
    if (!d) return;
    if (d.type === 'pan') { this.drag = null; return; }
    if (d.type === 'move') {
      if (d.moved) { this.undoStack.push(d.base); this.redoStack = []; this.hooks.onHistory?.(); this.setDirty(true); }
      else if (this.sel.size > 1) this.sel = new Set([d.hit]);   // plain click inside a multi-selection narrows it
      this.drag = null; this.render(); this.hooks.onSelection?.();
    } else if (d.type === 'band') {
      this.finishBand(e);
    } else if (d.type === 'seg' || d.type === 'bushandle') {
      if (d.moved) { this.undoStack.push(d.base); this.redoStack = []; this.hooks.onHistory?.(); this.setDirty(true); }
      this.drag = null; this.render();
    } else if (d.type === 'box') {
      const raw = this.toMM(e);
      const moved = Math.hypot(raw[0] - d.start[0], raw[1] - d.start[1]) * this.view.k > 6;
      this.drag = null;
      if (moved) this.finishBox(d, this.snapPoint(raw));
      else this.draft = { type: 'box', tool: d.tool, start: d.start };
      this.renderOverlay();
    }
  }

  onDbl(e) {
    if (this.tool === 'line' && this.draft) { this.finishLine(); return; }
    if (this.tool === 'wire' && this.draft) { this.finishWire(null, true); return; }
    if (this.tool === 'select') {
      const id = this.hitTest(this.toMM(e));
      if (id) { this.setSelection([id]); this.hooks.onEdit?.(id); }
    }
  }

  onKey(e) {
    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select' || e.target.isContentEditable) return;
    if (document.querySelector('dialog[open]')) return;
    const ctrl = e.ctrlKey || e.metaKey;
    const k = e.key.toLowerCase();
    if (e.code === 'Space') { this.spaceDown = true; if (this.tool === 'wire' && this.draft) { this.flip = !this.flip; this.renderOverlay(); } e.preventDefault(); return; }
    if (ctrl) {
      if (k === 'z') { e.shiftKey ? this.redo() : this.undo(); e.preventDefault(); }
      else if (k === 'y') { this.redo(); e.preventDefault(); }
      else if (k === 'c') { this.copy(); e.preventDefault(); }
      else if (k === 'x') { this.copy(); this.deleteSelection(); e.preventDefault(); }
      else if (k === 'v') { this.paste(); e.preventDefault(); }
      else if (k === 'd') { this.copy(); this.paste(); e.preventDefault(); }
      else if (k === 'a') { this.setSelection([...this.project.elements, ...this.project.wires].map(x => x.id)); e.preventDefault(); }
      return;
    }
    if (e.key === 'Escape') { this.cancelTool(); return; }
    if (e.key === 'Enter') { if (this.draft && this.tool === 'wire') this.finishWire(null, true); else if (this.draft && this.tool === 'line') this.finishLine(); return; }
    if (e.key === 'Delete' || e.key === 'Backspace') { this.deleteSelection(); e.preventDefault(); return; }
    if (k === 'r') { this.placing ? (this.placing.rot = (this.placing.rot + 90) % 360, this.renderOverlay()) : this.rotateSelection(); return; }
    if (k === 'm') { this.placing ? (this.placing.mirror = !this.placing.mirror, this.renderOverlay()) : this.mirrorSelection(); return; }
    const tools = { v: 'select', h: 'pan', w: 'wire', b: 'bus', l: 'line', x: 'rect', t: 'text' };
    if (tools[k]) { this.setTool(tools[k]); return; }
    if (k === 'f' || e.key === 'Home') { this.fit(); return; }
    if (k === 'g') { this.project.sheet.showGrid = !this.project.sheet.showGrid; this.render(); this.hooks.onSheet?.(); return; }
    if (e.key === 'F9') { this.project.sheet.snap = !this.project.sheet.snap; this.hooks.onSheet?.(); return; }
    if (e.key === '+' || e.key === '=') { this.zoomAt(1.25); return; }
    if (e.key === '-') { this.zoomAt(0.8); return; }
    if (e.key.startsWith('Arrow') && this.sel.size) {
      const g = this.grid();
      const dx = e.key === 'ArrowLeft' ? -g : e.key === 'ArrowRight' ? g : 0;
      const dy = e.key === 'ArrowUp' ? -g : e.key === 'ArrowDown' ? g : 0;
      this.mutate(() => this.translateSelection(dx, dy, this.project));
      e.preventDefault();
    }
  }

  // ----------------------------------------------------------- select tool
  downSelect(e, raw) {
    // handles of a single selected wire / bus
    const hk = this.handles();
    const hr = 8 / this.view.k;
    for (const h of hk) {
      if (Math.hypot(h.p[0] - raw[0], h.p[1] - raw[1]) <= hr) {
        this.drag = { type: h.type === 'seg' ? 'seg' : 'bushandle', h, base: JSON.stringify(this.project), moved: false, orig: clone(this.project) };
        return;
      }
    }
    const id = this.hitTest(raw);
    if (id) {
      if (e.shiftKey) {
        if (this.sel.has(id)) this.sel.delete(id); else this.sel.add(id);
        this.hooks.onSelection?.(); this.render();
        return;
      }
      if (!this.sel.has(id)) { this.sel = new Set([id]); this.hooks.onSelection?.(); }
      this.drag = { type: 'move', hit: id, start: raw, sx: e.clientX, sy: e.clientY, base: JSON.stringify(this.project), moved: false, orig: clone(this.project) };
      this.render();
    } else {
      if (!e.shiftKey && this.sel.size) { this.sel = new Set(); this.hooks.onSelection?.(); }
      this.drag = { type: 'band', start: raw, cur: raw, shift: e.shiftKey, base: new Set(this.sel) };
      this.render();
    }
  }

  moveSelect(e, raw) {
    const d = this.drag;
    if (!d) { this.svg.style.cursor = ''; this.renderOverlayLight(raw); return; }
    if (d.type === 'band') { d.cur = raw; this.renderOverlay(); return; }
    if (d.type === 'move') {
      if (!d.moved && Math.hypot(e.clientX - d.sx, e.clientY - d.sy) < 4) return;
      d.moved = true;
      let dx = raw[0] - d.start[0], dy = raw[1] - d.start[1];
      if (this.project.sheet.snap) { const g = this.grid(); dx = Math.round(dx / g) * g; dy = Math.round(dy / g) * g; }
      this.project = clone(d.orig);
      this.translateSelection(dx, dy, this.project);
      this.refreshWires();
      this.render();
      return;
    }
    if (d.type === 'seg') {
      d.moved = true;
      this.project = clone(d.orig);
      const w = this.project.wires.find(x => x.id === d.h.id);
      const a = w.pts[d.h.i], b = w.pts[d.h.i + 1];
      if (d.h.horiz) { const y = this.snapVal(raw[1]); a[1] = y; b[1] = y; } else { const x = this.snapVal(raw[0]); a[0] = x; b[0] = x; }
      w.pts = simplify(w.pts);
      this.render();
      return;
    }
    if (d.type === 'bushandle') {
      d.moved = true;
      this.project = clone(d.orig);
      const el = this.project.elements.find(x => x.id === d.h.id);
      const horiz = (el.rot || 0) % 180 === 0;
      const v = horiz ? this.snapVal(raw[0]) : this.snapVal(raw[1]);
      const start = horiz ? el.x : el.y;
      if (d.h.type === 'busB') {
        el.len = Math.max(5, r4(v - start));
      } else {
        const end = start + el.len;
        const ns = Math.min(v, end - 5);
        const delta = ns - start;
        if (horiz) el.x = r4(ns); else el.y = r4(ns);
        el.len = r4(el.len - delta);
        for (const w of this.project.wires) for (const k of ['a', 'b']) if (w[k] && w[k].el === el.id && w[k].s !== undefined) w[k].s = r4(w[k].s - delta);
      }
      this.refreshWires();
      this.render();
    }
  }

  translateSelection(dx, dy, project) {
    const moving = new Set(this.sel);
    for (const el of project.elements) {
      if (!moving.has(el.id)) continue;
      if (el.type === 'line') el.pts = el.pts.map(p => [r4(p[0] + dx), r4(p[1] + dy)]);
      else { el.x = r4(el.x + dx); el.y = r4(el.y + dy); }
    }
    for (const w of project.wires) {
      const both = w.a && w.b && moving.has(w.a.el) && moving.has(w.b.el);
      if (moving.has(w.id) || both) w.pts = w.pts.map(p => [r4(p[0] + dx), r4(p[1] + dy)]);
    }
  }

  finishBand(e) {
    const d = this.drag; this.drag = null;
    const [x0, x1] = [Math.min(d.start[0], d.cur[0]), Math.max(d.start[0], d.cur[0])];
    const [y0, y1] = [Math.min(d.start[1], d.cur[1]), Math.max(d.start[1], d.cur[1])];
    const small = (x1 - x0) * this.view.k < 4 && (y1 - y0) * this.view.k < 4;
    const sel = new Set(d.shift ? d.base : []);
    if (!small) {
      const crossing = d.cur[0] < d.start[0];   // right-to-left = crossing, left-to-right = window
      for (const id of [...this.project.elements, ...this.project.wires].map(x => x.id)) {
        const bb = this.bboxOf(id);
        if (!bb) continue;
        const inside = bb[0] >= x0 && bb[2] <= x1 && bb[1] >= y0 && bb[3] <= y1;
        const touch = bb[2] >= x0 && bb[0] <= x1 && bb[3] >= y0 && bb[1] <= y1;
        if (crossing ? touch : inside) sel.add(id);
      }
    }
    this.sel = sel;
    this.hooks.onSelection?.();
    this.render();
  }

  // ------------------------------------------------------------ place tool
  placeAt(raw) {
    const pl = this.placing;
    const lib = this.symbols(pl.sym);
    if (!lib) return;
    const x = this.snapVal(raw[0]), y = this.snapVal(raw[1]);
    this.checkpoint();
    const el = {
      id: this.uid('e'), type: 'sym', sym: pl.sym, x, y, rot: pl.rot, mirror: pl.mirror,
      tag: this.nextTag(lib.prefix), attrs: Object.fromEntries((lib.attrs || []).map(a => [a.key, a.default])), lp: 'r',
    };
    this.project.elements.push(el);
    this.sel = new Set([el.id]);
    this.setDirty(true);
    this.render();
    this.hooks.onSelection?.();
  }

  // ------------------------------------------------------------- wire tool
  downWire(raw) {
    const sp = this.snapPoint(raw, { wire: true });
    if (!this.draft) {
      this.draft = { type: 'wire', pts: [[sp.x, sp.y]], a: sp.ref, axis: sp.axis };
      this.flip = false;
      this.renderOverlay();
      return;
    }
    const d = this.draft;
    const last = d.pts[d.pts.length - 1];
    if (samePt(last, [sp.x, sp.y])) { if (d.pts.length >= 2) this.finishWire(null, true); return; }
    const leg = route(last, [sp.x, sp.y], d.axis, (sp.kind === 'term' || sp.kind === 'bus') ? sp.axis : null, (v) => this.snapVal(v), this.flip);
    d.pts.push(...leg);
    d.pts = simplify(d.pts);
    if (sp.kind === 'term' || sp.kind === 'bus') { this.finishWire(sp.ref, false); return; }
    if (sp.kind === 'wire') { this.finishWire(null, false); return; }
    const n = d.pts.length;
    const orient = Math.abs(d.pts[n - 1][1] - d.pts[n - 2][1]) < 1e-6 ? 'h' : 'v';
    d.axis = orient === 'h' ? 'v' : 'h';
    this.flip = false;
    this.renderOverlay();
  }
  wirePreview() {
    const d = this.draft;
    const last = d.pts[d.pts.length - 1];
    const sp = this.snap;
    const leg = route(last, [sp.x, sp.y], d.axis, (sp.kind === 'term' || sp.kind === 'bus') ? sp.axis : null, (v) => this.snapVal(v), this.flip);
    return simplify([...d.pts, ...leg]);
  }
  finishWire(bref, fromUser) {
    const d = this.draft;
    this.draft = null;
    if (d && d.pts.length >= 2) {
      this.checkpoint();
      const w = { id: this.uid('w'), pts: d.pts.map(p => [r4(p[0]), r4(p[1])]), a: d.a || null, b: bref || null, label: '' };
      this.project.wires.push(w);
      this.refreshWires();
      this.setDirty(true);
      this.render();
    } else this.renderOverlay();
  }

  // ----------------------------------------------------- bus / rect (2-point)
  downBox(raw, tool) {
    const sp = { x: this.snapVal(raw[0]), y: this.snapVal(raw[1]) };
    if (this.draft && this.draft.type === 'box') {
      const d = this.draft; this.draft = null;
      this.finishBox(d, sp);
      return;
    }
    this.drag = { type: 'box', tool, start: [sp.x, sp.y] };
    this.draft = null;
    this.renderOverlay();
  }
  boxEnd(d, sp) {
    let [x, y] = [sp.x, sp.y];
    if (d.tool === 'bus') {
      if (Math.abs(x - d.start[0]) >= Math.abs(y - d.start[1])) y = d.start[1]; else x = d.start[0];
    }
    return [x, y];
  }
  finishBox(d, sp) {
    const [ex, ey] = this.boxEnd(d, sp);
    const [sx, sy] = d.start;
    if (d.tool === 'bus') {
      const horiz = Math.abs(ey - sy) < 1e-6;
      const len = horiz ? Math.abs(ex - sx) : Math.abs(ey - sy);
      if (len < 5) return;
      this.checkpoint();
      this.project.elements.push({
        id: this.uid('e'), type: 'bus', x: horiz ? Math.min(sx, ex) : sx, y: horiz ? sy : Math.min(sy, ey),
        len: r4(len), rot: horiz ? 0 : 90, tag: this.nextTag('BUS'), attrs: { Voltage: '0.4 kV', Rating: '1600 A' }, lp: 'l',
      });
    } else {
      const w = Math.abs(ex - sx), h = Math.abs(ey - sy);
      if (w < 5 || h < 5) return;
      this.checkpoint();
      this.project.elements.unshift({ id: this.uid('e'), type: 'rect', x: Math.min(sx, ex), y: Math.min(sy, ey), w: r4(w), h: r4(h), dash: true });
    }
    this.sel = new Set([this.project.elements[d.tool === 'rect' ? 0 : this.project.elements.length - 1].id]);
    this.setDirty(true);
    this.render();
    this.hooks.onSelection?.();
  }

  // --------------------------------------------------------------- line tool
  downLine(e, raw) {
    const sp = e.shiftKey ? [this.snapVal(raw[0]), this.snapVal(raw[1])] : null;
    const p = sp || this.orthoPoint(raw);
    if (!this.draft) { this.draft = { type: 'line', pts: [[p[0], p[1]]] }; this.renderOverlay(); return; }
    const last = this.draft.pts[this.draft.pts.length - 1];
    if (samePt(last, p)) return;
    this.draft.pts.push([p[0], p[1]]);
    this.renderOverlay();
  }
  orthoPoint(raw) {
    const x = this.snapVal(raw[0]), y = this.snapVal(raw[1]);
    if (!this.draft) return [x, y];
    const last = this.draft.pts[this.draft.pts.length - 1];
    return Math.abs(x - last[0]) >= Math.abs(y - last[1]) ? [x, last[1]] : [last[0], y];
  }
  finishLine() {
    const d = this.draft; this.draft = null;
    if (d && d.pts.length >= 2) {
      this.checkpoint();
      this.project.elements.push({ id: this.uid('e'), type: 'line', pts: d.pts, dash: false });
      this.setDirty(true);
      this.render();
    } else this.renderOverlay();
  }

  // --------------------------------------------------------------- text tool
  async downText(raw) {
    const x = this.snapVal(raw[0]), y = this.snapVal(raw[1]);
    const s = await this.hooks.promptText?.('Text', '');
    if (!s) return;
    this.checkpoint();
    const el = { id: this.uid('e'), type: 'text', x, y, s, size: ST.text_size, bold: false, anchor: 'start' };
    this.project.elements.push(el);
    this.sel = new Set([el.id]);
    this.setDirty(true);
    this.render();
    this.hooks.onSelection?.();
  }

  // ---------------------------------------------------------- edit commands
  deleteSelection() {
    if (!this.sel.size) return;
    this.checkpoint();
    const ids = this.sel;
    this.project.elements = this.project.elements.filter(e => !ids.has(e.id));
    this.project.wires = this.project.wires.filter(w => !ids.has(w.id));
    this.sel = new Set();
    this.refreshWires();
    this.setDirty(true);
    this.render();
    this.hooks.onSelection?.();
  }

  rotateSelection() {
    if (!this.sel.size) return;
    const p = this.project;
    const els = p.elements.filter(e => this.sel.has(e.id));
    let c;
    if (this.sel.size === 1 && els.length === 1 && els[0].type === 'sym') c = [els[0].x, els[0].y];
    else { const bb = this.selectionBBox(); c = [this.snapVal((bb[0] + bb[2]) / 2), this.snapVal((bb[1] + bb[3]) / 2)]; }
    const R = (x, y) => [r4(c[0] - (y - c[1])), r4(c[1] + (x - c[0]))];
    this.checkpoint();
    for (const el of els) {
      if (el.type === 'sym') { [el.x, el.y] = R(el.x, el.y); el.rot = ((el.rot || 0) + 90) % 360; }
      else if (el.type === 'text') { [el.x, el.y] = R(el.x, el.y); }
      else if (el.type === 'line') el.pts = el.pts.map(q => R(q[0], q[1]));
      else if (el.type === 'rect') {
        const a = R(el.x, el.y), b = R(el.x + el.w, el.y + el.h);
        el.x = Math.min(a[0], b[0]); el.y = Math.min(a[1], b[1]); el.w = Math.abs(a[0] - b[0]); el.h = Math.abs(a[1] - b[1]);
      } else if (el.type === 'bus') {
        const [s, e2] = busEnds(el);
        const s2 = R(s[0], s[1]), e3 = R(e2[0], e2[1]);
        if ((el.rot || 0) % 180 === 0) { el.x = s2[0]; el.y = s2[1]; el.rot = 90; }
        else {
          el.x = e3[0]; el.y = e3[1]; el.rot = 0;
          for (const w of p.wires) for (const k of ['a', 'b']) if (w[k] && w[k].el === el.id && w[k].s !== undefined) w[k].s = r4(el.len - w[k].s);
        }
      }
    }
    for (const w of p.wires) if (this.sel.has(w.id)) w.pts = w.pts.map(q => R(q[0], q[1]));
    this.refreshWires();
    this.setDirty(true);
    this.render();
    this.hooks.onSelection?.();
  }
  mirrorSelection() {
    const els = this.project.elements.filter(e => this.sel.has(e.id) && e.type === 'sym');
    if (!els.length) return;
    this.mutate(() => { for (const e of els) e.mirror = !e.mirror; });
  }
  autoRouteSelection() {
    const ws = this.project.wires.filter(w => this.sel.has(w.id));
    if (!ws.length) return;
    this.mutate(() => { for (const w of ws) this.autoRoute(w); });
  }

  copy() {
    if (!this.sel.size) return;
    const els = this.project.elements.filter(e => this.sel.has(e.id));
    const ids = new Set(els.map(e => e.id));
    const wires = this.project.wires.filter(w => this.sel.has(w.id) || (w.a && w.b && ids.has(w.a.el) && ids.has(w.b.el)));
    this.clipboard = clone({ els, wires });
    this.pasteCount = 0;
  }
  paste() {
    if (!this.clipboard) return;
    this.checkpoint();
    this.pasteCount++;
    const off = this.grid() * 2 * this.pasteCount;
    const map = new Map();
    const newSel = [];
    const data = clone(this.clipboard);
    for (const el of data.els) {
      const old = el.id; el.id = this.uid('e'); map.set(old, el.id);
      if (el.type === 'line') el.pts = el.pts.map(p => [p[0] + off, p[1] + off]); else { el.x += off; el.y += off; }
      if (el.type === 'sym' || el.type === 'bus') {
        const lib = el.type === 'sym' ? this.symbols(el.sym) : { prefix: 'BUS' };
        if (el.tag) el.tag = this.nextTag(lib ? lib.prefix : el.tag.replace(/\d+$/, ''));
      }
      this.project.elements.push(el); newSel.push(el.id);
    }
    for (const w of data.wires) {
      w.id = this.uid('w');
      w.pts = w.pts.map(p => [p[0] + off, p[1] + off]);
      for (const k of ['a', 'b']) { if (w[k]) { if (map.has(w[k].el)) w[k].el = map.get(w[k].el); else w[k] = null; } }
      this.project.wires.push(w); newSel.push(w.id);
    }
    this.sel = new Set(newSel);
    this.refreshWires();
    this.setDirty(true);
    this.render();
    this.hooks.onSelection?.();
  }

  // ------------------------------------------------------------- rendering
  render() {
    if (!this.project) return;
    this.applyView();
    const [W, H] = sheetSize(this.project.sheet);
    const k = this.view.k;
    this.paper.setAttribute('width', W); this.paper.setAttribute('height', H);
    // grid dots
    let g = this.grid();
    while (g * k < 7) g *= 2;
    this.gridPat.setAttribute('width', g); this.gridPat.setAttribute('height', g);
    this.gridPat.firstElementChild.setAttribute('r', 0.9 / k);
    this.gridRect.setAttribute('width', W); this.gridRect.setAttribute('height', H);
    this.gridRect.style.display = this.project.sheet.showGrid ? '' : 'none';
    const items = buildDisplayList(this.project, this.symbols);
    this.gContent.innerHTML = itemsSvg(items, 0.9 / k);
    this.lastItems = items;
    this.renderOverlay();
  }

  hl(ids) {
    const set = new Set(ids);
    return itemsSvg(this.lastItems.filter(it => set.has(it.id)), 0.9 / this.view.k);
  }

  renderOverlayLight() { /* hover feedback only needs the snap marker */ this.renderOverlay(); }

  renderOverlay() {
    if (!this.project) return;
    const k = this.view.k, px = 1 / k;
    let h = '';
    if (this.sel.size) {
      h += `<g class="hl">${this.hl(this.sel)}</g>`;
      for (const hd of this.handles()) {
        const r = 3 * px;
        h += `<rect class="handle" x="${hd.p[0] - r}" y="${hd.p[1] - r}" width="${2 * r}" height="${2 * r}" stroke-width="${px}"/>`;
      }
      if (this.sel.size === 1) {
        const w = this.project.wires.find(x => x.id === [...this.sel][0]);
        if (w) for (const [pt, ref] of [[w.pts[0], w.a], [w.pts[w.pts.length - 1], w.b]]) {
          h += `<circle class="${ref ? 'endbound' : 'endfree'}" cx="${pt[0]}" cy="${pt[1]}" r="${3 * px}" stroke-width="${px}"/>`;
        }
      }
    }
    if (this.tool === 'wire' || this.tool === 'place') {
      for (const t of this.allTerminals()) h += `<circle class="term" cx="${t.p[0]}" cy="${t.p[1]}" r="${2.6 * px}" stroke-width="${px}"/>`;
    }
    // previews
    const sp = this.snap;
    if (this.tool === 'place' && this.placing) {
      const sym = this.symbols(this.placing.sym);
      if (sym) {
        const el = { type: 'sym', sym: this.placing.sym, x: this.snapVal(this.mouse[0]), y: this.snapVal(this.mouse[1]), rot: this.placing.rot, mirror: this.placing.mirror, tag: this.nextTag(sym.prefix), attrs: {}, lp: 'r' };
        h += `<g class="ghost">${itemsSvg(elementItems(el, this.symbols), 0.9 / k)}</g>`;
      }
    }
    if (this.tool === 'wire') {
      if (this.draft) {
        const pts = this.wirePreview();
        h += `<polyline class="draft" points="${pts.map(p => p.join(',')).join(' ')}" stroke-width="${ST.line_w}"/>`;
      }
      if (sp.kind !== 'grid') h += `<circle class="snap ${sp.kind}" cx="${sp.x}" cy="${sp.y}" r="${5 * px}" stroke-width="${1.5 * px}"/>`;
      else h += `<path class="cross" d="M${sp.x - 3 * px} ${sp.y}H${sp.x + 3 * px}M${sp.x} ${sp.y - 3 * px}V${sp.y + 3 * px}" stroke-width="${px}"/>`;
    }
    const dr = this.drag && this.drag.type === 'box' ? this.drag : (this.draft && this.draft.type === 'box' ? this.draft : null);
    if (dr && (this.tool === 'bus' || this.tool === 'rect')) {
      const [ex, ey] = this.boxEnd(dr, { x: this.snapVal(this.mouse[0]), y: this.snapVal(this.mouse[1]) });
      if (this.tool === 'rect') h += `<rect class="draft" x="${Math.min(dr.start[0], ex)}" y="${Math.min(dr.start[1], ey)}" width="${Math.abs(ex - dr.start[0])}" height="${Math.abs(ey - dr.start[1])}" stroke-width="${ST.line_w}" stroke-dasharray="${ST.dash.join(' ')}"/>`;
      else h += `<line class="draft" x1="${dr.start[0]}" y1="${dr.start[1]}" x2="${ex}" y2="${ey}" stroke-width="${ST.bus_w}"/>`;
    } else if ((this.tool === 'bus' || this.tool === 'rect')) {
      h += `<path class="cross" d="M${this.snapVal(this.mouse[0]) - 3 * px} ${this.snapVal(this.mouse[1])}H${this.snapVal(this.mouse[0]) + 3 * px}M${this.snapVal(this.mouse[0])} ${this.snapVal(this.mouse[1]) - 3 * px}V${this.snapVal(this.mouse[1]) + 3 * px}" stroke-width="${px}"/>`;
    }
    if (this.tool === 'line' && this.draft) {
      const pts = [...this.draft.pts, this.orthoPointShift()];
      h += `<polyline class="draft" points="${pts.map(p => p.join(',')).join(' ')}" stroke-width="${ST.line_w}"/>`;
    }
    if (this.drag && this.drag.type === 'band') {
      const d = this.drag;
      const crossing = d.cur[0] < d.start[0];
      h += `<rect class="band ${crossing ? 'cross' : 'window'}" x="${Math.min(d.start[0], d.cur[0])}" y="${Math.min(d.start[1], d.cur[1])}" width="${Math.abs(d.cur[0] - d.start[0])}" height="${Math.abs(d.cur[1] - d.start[1])}" stroke-width="${px}" stroke-dasharray="${4 * px} ${3 * px}"/>`;
    }
    this.gOverlay.innerHTML = h;
  }
  orthoPointShift() {
    const m = this.mouse;
    return this.shiftDown ? [this.snapVal(m[0]), this.snapVal(m[1])] : this.orthoPoint(m);
  }

  // ----------------------------------------------------------------- export helpers
  /** Project with every used symbol embedded, ready to save or send to the server. */
  exportable() {
    const p = clone(this.project);
    const used = new Set(p.elements.filter(e => e.type === 'sym').map(e => e.sym));
    const syms = {};
    for (const id of used) { const s = this.symbols(id); if (s) { const c = clone(s); delete c.builtin; syms[id] = c; } }
    p.symbols = syms;
    return p;
  }
}
