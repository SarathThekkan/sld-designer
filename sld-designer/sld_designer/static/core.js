// core.js - pure drawing logic shared by the editor. Mirrors sld_designer/render.py exactly
// (tests/test_parity.py compares both outputs), so the screen equals the exported PDF/DXF.

export const ST = {};
export const TB = {};
export const SHEETS = {};

export function setConfig(cfg) {
  Object.assign(ST, cfg.style);
  Object.assign(TB, cfg.titleblock);
  Object.assign(SHEETS, cfg.sheets);
}

export const r4 = (v) => { const x = Math.round(v * 1e4) / 1e4; return x === 0 ? 0 : x; };

// ----------------------------------------------------------------- geometry
export function tfVec(px, py, rot, mirror) {
  if (mirror) px = -px;
  const r = ((rot % 360) + 360) % 360;
  if (r === 0) return [px, py];
  if (r === 90) return [-py, px];
  if (r === 180) return [-px, -py];
  if (r === 270) return [py, -px];
  const a = r * Math.PI / 180;
  return [px * Math.cos(a) - py * Math.sin(a), px * Math.sin(a) + py * Math.cos(a)];
}
export function tfPoint(px, py, rot, mirror, ox, oy) {
  const [x, y] = tfVec(px, py, rot, mirror);
  return [x + ox, y + oy];
}
export function arcPoints(cx, cy, r, a0, a1, step) {
  const n = Math.max(2, Math.ceil(Math.abs(a1 - a0) / step));
  const pts = [];
  for (let i = 0; i <= n; i++) {
    const t = (a0 + (a1 - a0) * i / n) * Math.PI / 180;
    pts.push([cx + r * Math.cos(t), cy + r * Math.sin(t)]);
  }
  return pts;
}
export function segHit(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const L2 = dx * dx + dy * dy;
  if (L2 === 0) return Math.abs(p[0] - a[0]) < 1e-6 && Math.abs(p[1] - a[1]) < 1e-6;
  const t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2;
  if (t < -1e-9 || t > 1 + 1e-9) return false;
  const qx = a[0] + t * dx, qy = a[1] + t * dy;
  return (p[0] - qx) ** 2 + (p[1] - qy) ** 2 < 1e-10;
}
export function distSeg(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const L2 = dx * dx + dy * dy;
  let t = L2 === 0 ? 0 : ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
}
export function nearestOnSeg(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const L2 = dx * dx + dy * dy;
  let t = L2 === 0 ? 0 : ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2;
  t = Math.max(0, Math.min(1, t));
  return [a[0] + t * dx, a[1] + t * dy, t];
}

// -------------------------------------------------------------- primitives
const poly = (pts, closed = false, fill = false, w = null, dash = false, layer = 'SYM') => ({
  k: 'poly', pts: pts.map(([x, y]) => [r4(x), r4(y)]), closed: !!closed, fill: !!fill,
  w: r4(w === null || w === undefined ? ST.line_w : w), dash: !!dash, layer,
});
const circle = (cx, cy, r, fill = false, w = null, layer = 'SYM') => ({
  k: 'circle', c: [r4(cx), r4(cy)], r: r4(r), fill: !!fill,
  w: r4(w === null || w === undefined ? ST.line_w : w), layer,
});
const text = (x, y, s, size, bold = false, anchor = 'start', layer = 'TEXT') => ({
  k: 'text', p: [r4(x), r4(y)], s: String(s), size: r4(size), bold: !!bold, anchor, layer,
});

// ------------------------------------------------------------------ symbols
export function symbolItems(sym, el) {
  const rot = el.rot || 0, mir = !!el.mirror, ox = el.x, oy = el.y;
  const f = (x, y) => tfPoint(x, y, rot, mir, ox, oy);
  const out = [];
  for (const p of sym.prims) {
    const w = p.lw, dash = !!p.dash;
    switch (p.t) {
      case 'line': out.push(poly([f(p.x1, p.y1), f(p.x2, p.y2)], false, false, w, dash)); break;
      case 'poly': out.push(poly(p.pts.map(([x, y]) => f(x, y)), p.closed, p.fill, w, dash)); break;
      case 'rect': {
        const { x, y, w: ww, h: hh } = p;
        out.push(poly([f(x, y), f(x + ww, y), f(x + ww, y + hh), f(x, y + hh)], true, p.fill, w, dash));
        break;
      }
      case 'circle': { const [cx, cy] = f(p.cx, p.cy); out.push(circle(cx, cy, p.r, p.fill, w)); break; }
      case 'arc': {
        const pts = arcPoints(p.cx, p.cy, p.r, p.a0, p.a1, ST.arc_step);
        out.push(poly(pts.map(([x, y]) => f(x, y)), false, false, w, dash));
        break;
      }
      case 'text': {
        const [x, y] = f(p.x, p.y);
        out.push(text(x, y, p.s, p.size === undefined ? 3.5 : p.size, p.bold, p.anchor || 'middle', 'SYM'));
        break;
      }
    }
  }
  return out;
}

export function termWorld(sym, el, idx) {
  const t = sym.terminals[idx];
  return tfPoint(t.x, t.y, el.rot || 0, !!el.mirror, el.x, el.y);
}
export function termDir(sym, el, idx) {
  const t = sym.terminals[idx];
  const d = t.d || [0, 1];
  return tfVec(d[0], d[1], el.rot || 0, !!el.mirror);
}
export function busEnds(el) {
  return ((el.rot || 0) % 180 === 0)
    ? [[el.x, el.y], [el.x + el.len, el.y]] : [[el.x, el.y], [el.x, el.y + el.len]];
}
export function itemsBBox(items) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const it of items) {
    if (it.k === 'poly') for (const [x, y] of it.pts) { x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); }
    else if (it.k === 'circle') { x0 = Math.min(x0, it.c[0] - it.r); x1 = Math.max(x1, it.c[0] + it.r); y0 = Math.min(y0, it.c[1] - it.r); y1 = Math.max(y1, it.c[1] + it.r); }
  }
  return x0 === Infinity ? null : [x0, y0, x1, y1];
}

// ------------------------------------------------------------------- labels
export function labelItems(lines, bbox, lp, boldFirst = true, off = [0, 0]) {
  const n = lines.length;
  if (!n) return [];
  const [x0, y0, x1, y1] = bbox;
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
  const gap = ST.label_gap, pitch = ST.pitch;
  const [ox, oy] = off;
  const out = [];
  lines.forEach((s, i) => {
    const first = boldFirst && i === 0;
    const size = first ? ST.tag_size : ST.attr_size;
    if (lp === 'l') out.push(text(ox + x0 - gap, oy + cy - (n - 1) * pitch / 2 + i * pitch, s, size, first, 'end'));
    else if (lp === 't') out.push(text(ox + cx, oy + y0 - gap - 1.5 - (n - 1 - i) * pitch, s, size, first, 'middle'));
    else if (lp === 'b') out.push(text(ox + cx, oy + y1 + gap + 1.5 + i * pitch, s, size, first, 'middle'));
    else out.push(text(ox + x1 + gap, oy + cy - (n - 1) * pitch / 2 + i * pitch, s, size, first, 'start'));
  });
  return out;
}
export function elementLines(el) {
  const lines = [];
  if (el.tag) lines.push(el.tag);
  for (const v of Object.values(el.attrs || {})) if (String(v).trim()) lines.push(String(v));
  return lines;
}

// ----------------------------------------------------------------- elements
export function elementBBox(el, symbols) {
  if (el.type === 'sym') {
    const sym = symbols(el.sym);
    const bb = sym ? itemsBBox(symbolItems(sym, el)) : null;
    return bb || [el.x - 5, el.y - 5, el.x + 5, el.y + 5];
  }
  if (el.type === 'bus') { const [a, b] = busEnds(el); return [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])]; }
  if (el.type === 'rect') return [el.x, el.y, el.x + el.w, el.y + el.h];
  if (el.type === 'line') { const xs = el.pts.map(p => p[0]), ys = el.pts.map(p => p[1]); return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)]; }
  if (el.type === 'text') {
    const lines = String(el.s || '').split('\n');
    const size = el.size || ST.text_size;
    const w = Math.max(...lines.map(l => l.length)) * size * 0.62;
    const x0 = el.anchor === 'middle' ? el.x - w / 2 : el.anchor === 'end' ? el.x - w : el.x;
    return [x0, el.y - size * 0.6, x0 + w, el.y + (lines.length - 1) * size * 1.3 + size * 0.6];
  }
  return [el.x, el.y, el.x, el.y];
}

export function elementItems(el, symbols) {
  const t = el.type;
  if (t === 'sym') {
    const sym = symbols(el.sym);
    if (!sym) {      // symbol not available: visible placeholder so nothing silently disappears
      const { x, y } = el;
      return [poly([[x - 5, y - 5], [x + 5, y - 5], [x + 5, y + 5], [x - 5, y + 5]], true, false, null, true, 'SYM'),
        text(x, y, '?', 4, true, 'middle', 'SYM')].concat(labelItems([el.tag || 'missing symbol'], [x - 5, y - 5, x + 5, y + 5], el.lp || 'r'));
    }
    const items = symbolItems(sym, el);
    const bb = itemsBBox(items) || [el.x - 5, el.y - 5, el.x + 5, el.y + 5];
    return items.concat(labelItems(elementLines(el), bb, el.lp || 'r', true, el.lo || [0, 0]));
  }
  if (t === 'bus') {
    const [a, b] = busEnds(el);
    const items = [poly([a, b], false, false, ST.bus_w, false, 'BUS')];
    const bb = [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])];
    return items.concat(labelItems(elementLines(el), bb, el.lp || 'l', true, el.lo || [0, 0]));
  }
  if (t === 'rect') {
    const { x, y, w, h } = el;
    return [poly([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], true, false, el.lw, el.dash, 'ANNOT')];
  }
  if (t === 'line') return [poly(el.pts, false, false, el.lw, el.dash, 'ANNOT')];
  if (t === 'text') {
    const size = el.size === undefined ? ST.text_size : el.size;
    return String(el.s || '').split('\n').map((s, i) =>
      text(el.x, el.y + i * size * 1.3, s, size, el.bold, el.anchor || 'start', 'TEXT'));
  }
  return [];
}

// -------------------------------------------------------------------- wires
export function wireItems(w) {
  const pts = w.pts;
  const out = [poly(pts, false, false, null, false, 'WIRE')];
  const label = String(w.label || '').trim();
  if (label && pts.length >= 2) {
    let best = -1, bi = 0;
    for (let i = 0; i < pts.length - 1; i++) {
      const L = Math.abs(pts[i + 1][0] - pts[i][0]) + Math.abs(pts[i + 1][1] - pts[i][1]);
      if (L > best) { best = L; bi = i; }
    }
    const a = pts[bi], b = pts[bi + 1];
    const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
    const vertical = Math.abs(a[0] - b[0]) < Math.abs(a[1] - b[1]);
    out.push(...labelItems(label.split('\n'), [mx, my, mx, my], vertical ? 'r' : 't', false));
  }
  return out;
}

export function junctions(wires) {
  const key = (p) => r4(p[0]) + ',' + r4(p[1]);
  const ends = new Map();
  for (const w of wires) for (const p of [w.pts[0], w.pts[w.pts.length - 1]]) ends.set(key(p), (ends.get(key(p)) || 0) + 1);
  const dots = [];
  for (const [k, n] of ends) {
    const p = k.split(',').map(Number);
    let onOther = false;
    for (const w of wires) {
      const pts = w.pts;
      const isEnd = key(pts[0]) === k || key(pts[pts.length - 1]) === k;
      if (isEnd) continue;
      for (let i = 0; i < pts.length - 1; i++) if (segHit(p, pts[i], pts[i + 1])) { onOther = true; break; }
      if (onOther) break;
    }
    if (n >= 3 || onOther) dots.push(p);
  }
  return dots.map(([x, y]) => circle(x, y, ST.junction_r, true, 0.1, 'WIRE'));
}

// -------------------------------------------------------------- sheet frame
export function sheetSize(sheet) {
  let [w, h] = SHEETS[sheet.size || 'A3'];
  if ((sheet.orientation || 'landscape') === 'portrait') [w, h] = [h, w];
  return [w, h];
}
export function frameItems(project) {
  const [W, H] = sheetSize(project.sheet);
  const m = ST.margin;
  const rect = (x0, y0, x1, y1, w) => poly([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], true, false, w, false, 'FRAME');
  const out = [rect(m, m, W - m, H - m, ST.border_w)];
  const ox = W - m - TB.w, oy = H - m - TB.h;
  out.push(rect(ox, oy, ox + TB.w, oy + TB.h, ST.border_w));
  const title = project.title || {};
  for (const [x, y, w, h, key, cap] of TB.cells) {
    out.push(rect(ox + x, oy + y, ox + x + w, oy + y + h, ST.tb_w));
    out.push(text(ox + x + 1.5, oy + y + 2.4, cap, TB.caption_size, false, 'start', 'FRAME'));
    const val = String(title[key] === undefined ? '' : title[key]);
    if (val) out.push(text(ox + x + 1.5, oy + y + h - 4.2, val, TB.value_size, key === 'title' || key === 'project', 'start', 'FRAME'));
  }
  return out;
}

export function symbolLookup(project, library) {
  return (id) => (project.symbols && project.symbols[id]) || library.get(id);
}

// Each item gets `id` (owning element / wire id) so the editor can highlight it.
export function buildDisplayList(project, symbols) {
  const tag = (items, id) => { for (const it of items) it.id = id; return items; };
  let items = tag(frameItems(project), 'frame');
  for (const el of project.elements) items = items.concat(tag(elementItems(el, symbols), el.id));
  for (const w of project.wires) items = items.concat(tag(wireItems(w), w.id));
  items = items.concat(tag(junctions(project.wires), 'junction'));
  return items;
}

// ----------------------------------------------------------------- SVG output
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const n = (v) => +v.toFixed(3);

export function itemSvg(it, minW = 0) {
  const w = Math.max(it.w || 0, minW);
  if (it.k === 'poly') {
    const pts = it.pts.map(p => n(p[0]) + ',' + n(p[1])).join(' ');
    const dash = it.dash ? ` stroke-dasharray="${ST.dash.join(' ')}"` : '';
    const fill = it.fill ? 'fill="currentColor"' : 'fill="none"';
    return `<${it.closed ? 'polygon' : 'polyline'} points="${pts}" ${fill} stroke="currentColor" stroke-width="${n(w)}" stroke-linejoin="round"${dash}/>`;
  }
  if (it.k === 'circle') {
    return `<circle cx="${n(it.c[0])}" cy="${n(it.c[1])}" r="${n(it.r)}" fill="${it.fill ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="${n(w)}"/>`;
  }
  return `<text x="${n(it.p[0])}" y="${n(it.p[1])}" dy="0.35em" font-size="${n(it.size)}" text-anchor="${it.anchor}"${it.bold ? ' font-weight="700"' : ''}>${esc(it.s)}</text>`;
}
export function itemsSvg(items, minW = 0) { return items.map(it => itemSvg(it, minW)).join(''); }

export function standaloneSvg(project, symbols) {
  const [W, H] = sheetSize(project.sheet);
  const body = itemsSvg(buildDisplayList(project, symbols));
  return `<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" width="${W}mm" height="${H}mm" viewBox="0 0 ${W} ${H}" ` +
    `font-family="DejaVu Sans, Verdana, Arial, sans-serif" color="#000"><rect width="${W}" height="${H}" fill="#fff"/>${body}</svg>\n`;
}

// ------------------------------------------------------------- wire routing
export function samePt(a, b) { return Math.abs(a[0] - b[0]) < 1e-6 && Math.abs(a[1] - b[1]) < 1e-6; }

export function simplify(pts) {
  let out = [];
  for (const p of pts) if (!out.length || !samePt(out[out.length - 1], p)) out.push([p[0], p[1]]);
  let changed = true;
  while (changed && out.length > 2) {
    changed = false;
    for (let i = 1; i < out.length - 1; i++) {
      const a = out[i - 1], b = out[i], c = out[i + 1];
      const colX = Math.abs(a[0] - b[0]) < 1e-6 && Math.abs(b[0] - c[0]) < 1e-6;
      const colY = Math.abs(a[1] - b[1]) < 1e-6 && Math.abs(b[1] - c[1]) < 1e-6;
      if (colX || colY) { out.splice(i, 1); changed = true; break; }
    }
  }
  return out;
}

// Orthogonal route from a to b. axisA/axisB: 'v' | 'h' | null = direction the wire leaves a / arrives at b.
export function route(a, b, axisA, axisB, snapFn = (v) => v, flip = false) {
  if (Math.abs(a[0] - b[0]) < 1e-6 || Math.abs(a[1] - b[1]) < 1e-6) return [b];
  if (axisA && axisB && axisA === axisB) {
    if (axisA === 'v') { const my = snapFn((a[1] + b[1]) / 2); return [[a[0], my], [b[0], my], b]; }
    const mx = snapFn((a[0] + b[0]) / 2); return [[mx, a[1]], [mx, b[1]], b];
  }
  if (axisA) return [axisA === 'v' ? [a[0], b[1]] : [b[0], a[1]], b];
  if (axisB) return [axisB === 'v' ? [b[0], a[1]] : [a[0], b[1]], b];
  return [flip ? [b[0], a[1]] : [a[0], b[1]], b];
}
export const axisOf = (d) => (Math.abs(d[1]) >= Math.abs(d[0]) ? 'v' : 'h');
