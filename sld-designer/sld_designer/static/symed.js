// symed.js - symbol editor dialog: draw a symbol on a grid, mark terminals, save to the user library.
import { h, modal, api, toast, askText } from './ui.js';
import { symbolItems, itemsSvg, arcPoints, distSeg, ST } from './core.js';

const SCALE = 7, HALF = 40, PX = SCALE * HALF * 2;
const TOOLS = [
  ['select', 'Select / delete', 'M5 3l12 7-5 1.5L9.5 17z'],
  ['line', 'Line', 'M4 20L20 4'],
  ['poly', 'Polyline / polygon', 'M4 18l5-12 6 8 5-9'],
  ['rect', 'Rectangle', 'M4 6h16v12H4z'],
  ['circle', 'Circle', 'M12 4a8 8 0 1 0 0.01 0z'],
  ['arc', 'Arc (centre, start, end)', 'M5 18a9 9 0 0 1 14-10'],
  ['text', 'Text', 'M5 6h14M12 6v13'],
  ['term', 'Terminal', 'M12 8a4 4 0 1 0 0.01 0zM12 2v4'],
];

const clone = (o) => JSON.parse(JSON.stringify(o));

export async function openSymbolEditor(app, base, { copy = false } = {}) {
  const st = {
    prims: base ? clone(base.prims) : [], terms: base ? clone(base.terminals) : [],
    tool: 'line', draft: [], sel: null, hist: [], snap: 2.5, fill: false, dash: false, close: false, dir: [0, -1], mouse: [0, 0],
  };
  const isEdit = !!base && !copy && !base.builtin;
  let saved = null;
  const cats = [...new Set(app.palette.symbols.map(s => s.category))];

  const push = () => st.hist.push(JSON.stringify({ p: st.prims, t: st.terms }));
  const pop = () => { const s = st.hist.pop(); if (s) { const o = JSON.parse(s); st.prims = o.p; st.terms = o.t; st.sel = null; draw(); } };

  let svg, errEl, inputs = {};
  const sn = (v, g = st.snap) => Math.round(v / g) * g;
  const toMM = (e) => { const r = svg.getBoundingClientRect(); return [((e.clientX - r.left) * (PX / r.width) - PX / 2) / SCALE, ((e.clientY - r.top) * (PX / r.height) - PX / 2) / SCALE]; };
  const opts = () => ({ fill: st.fill, ...(st.dash ? { dash: true } : {}) });

  function draw() {
    const items = symbolItems({ prims: st.prims }, { x: 0, y: 0, rot: 0, mirror: false });
    let g = '';
    for (let i = -HALF; i <= HALF; i += 5) g += `<line x1="${i}" y1="${-HALF}" x2="${i}" y2="${HALF}" stroke="${i === 0 ? '#9aa3b5' : '#e3e6ee'}" stroke-width="${i === 0 ? 0.25 : 0.12}"/><line x1="${-HALF}" y1="${i}" x2="${HALF}" y2="${i}" stroke="${i === 0 ? '#9aa3b5' : '#e3e6ee'}" stroke-width="${i === 0 ? 0.25 : 0.12}"/>`;
    let ov = '';
    if (st.sel && st.sel.kind === 'p') {
      const one = symbolItems({ prims: [st.prims[st.sel.i]] }, { x: 0, y: 0, rot: 0, mirror: false });
      ov += `<g color="#1d6bff" style="--hl:1">${itemsSvg(one, 0.5)}</g>`;
    }
    st.terms.forEach((t, i) => {
      const sel = st.sel && st.sel.kind === 't' && st.sel.i === i;
      ov += `<g><circle cx="${t.x}" cy="${t.y}" r="1.4" fill="${sel ? '#1d6bff' : '#12b76a'}" fill-opacity=".35" stroke="${sel ? '#1d6bff' : '#12b76a'}" stroke-width=".4"/>` +
        `<line x1="${t.x}" y1="${t.y}" x2="${t.x + t.d[0] * 3.5}" y2="${t.y + t.d[1] * 3.5}" stroke="#12b76a" stroke-width=".4"/>` +
        `<text x="${t.x + 2}" y="${t.y - 1.5}" font-size="2.4" fill="#0a7d4b">${t.n || i + 1}</text></g>`;
    });
    // draft preview
    const m = st.mouse;
    const m2 = [sn(m[0]), sn(m[1])];
    if (st.draft.length) {
      const d = st.draft, a = d[0];
      let pv = '';
      if (st.tool === 'line') pv = `<line x1="${a[0]}" y1="${a[1]}" x2="${m2[0]}" y2="${m2[1]}"/>`;
      else if (st.tool === 'rect') pv = `<rect x="${Math.min(a[0], m2[0])}" y="${Math.min(a[1], m2[1])}" width="${Math.abs(m2[0] - a[0])}" height="${Math.abs(m2[1] - a[1])}"/>`;
      else if (st.tool === 'circle') pv = `<circle cx="${a[0]}" cy="${a[1]}" r="${Math.hypot(m2[0] - a[0], m2[1] - a[1])}"/>`;
      else if (st.tool === 'poly') pv = `<polyline points="${[...d, m2].map(p => p.join(',')).join(' ')}"/>`;
      else if (st.tool === 'arc') {
        pv = `<circle cx="${a[0]}" cy="${a[1]}" r="1"/>`;
        if (d.length === 1) pv += `<line x1="${a[0]}" y1="${a[1]}" x2="${m2[0]}" y2="${m2[1]}"/>`;
        else { const r = Math.hypot(d[1][0] - a[0], d[1][1] - a[1]); const a0 = Math.atan2(d[1][1] - a[1], d[1][0] - a[0]) * 180 / Math.PI; let a1 = Math.atan2(m2[1] - a[1], m2[0] - a[0]) * 180 / Math.PI; if (a1 <= a0) a1 += 360; pv = `<polyline points="${arcPoints(a[0], a[1], r, a0, a1, 10).map(p => p.join(',')).join(' ')}"/>`; }
      }
      ov += `<g fill="none" stroke="#1d6bff" stroke-width=".35" stroke-dasharray="1 .8">${pv}</g>`;
    } else if (['line', 'poly', 'rect', 'circle', 'arc', 'text', 'term'].includes(st.tool)) {
      const q = st.tool === 'term' ? [sn(m[0], 5), sn(m[1], 5)] : m2;
      ov += `<path d="M${q[0] - 1.2} ${q[1]}H${q[0] + 1.2}M${q[0]} ${q[1] - 1.2}V${q[1] + 1.2}" stroke="#1d6bff" stroke-width=".25"/>`;
    }
    svg.querySelector('#se-g').innerHTML = g + `<g color="#000">${itemsSvg(items, 0.3)}</g>` + ov;
    listEl.textContent = `${st.prims.length} shape(s), ${st.terms.length} terminal(s)` + (st.sel ? ' · selected: press Delete' : '');
  }

  function dist(p, pr) {
    const poly = (pts, closed) => { let best = 1e9; for (let i = 0; i < pts.length - (closed ? 0 : 1); i++) best = Math.min(best, distSeg(p, pts[i], pts[(i + 1) % pts.length])); return best; };
    switch (pr.t) {
      case 'line': return distSeg(p, [pr.x1, pr.y1], [pr.x2, pr.y2]);
      case 'poly': return poly(pr.pts, pr.closed);
      case 'rect': return poly([[pr.x, pr.y], [pr.x + pr.w, pr.y], [pr.x + pr.w, pr.y + pr.h], [pr.x, pr.y + pr.h]], true);
      case 'circle': return Math.abs(Math.hypot(p[0] - pr.cx, p[1] - pr.cy) - pr.r);
      case 'arc': return poly(arcPoints(pr.cx, pr.cy, pr.r, pr.a0, pr.a1, 10), false);
      case 'text': return Math.hypot(p[0] - pr.x, p[1] - pr.y) - 2;
    }
    return 1e9;
  }

  async function onClick(e) {
    const raw = toMM(e);
    const p = [sn(raw[0]), sn(raw[1])];
    const t = st.tool;
    if (t === 'select') {
      let best = null, bd = 2;
      st.terms.forEach((q, i) => { const d = Math.hypot(raw[0] - q.x, raw[1] - q.y); if (d < bd) { bd = d; best = { kind: 't', i }; } });
      st.prims.forEach((pr, i) => { const d = dist(raw, pr); if (d < bd) { bd = d; best = { kind: 'p', i }; } });
      st.sel = best; draw(); return;
    }
    if (t === 'term') { push(); const q = [sn(raw[0], 5), sn(raw[1], 5)]; st.terms.push({ x: q[0], y: q[1], d: st.dir.slice(), n: String(st.terms.length + 1) }); draw(); return; }
    if (t === 'text') {
      const s = await askText('Text', 'Text to place');
      if (s) { push(); st.prims.push({ t: 'text', x: p[0], y: p[1], s, size: 3.5, bold: false, anchor: 'middle' }); draw(); }
      return;
    }
    if (t === 'poly') { st.draft.push(p); draw(); return; }
    st.draft.push(p);
    const d = st.draft;
    if (t === 'line' && d.length === 2) { if (d[0][0] !== d[1][0] || d[0][1] !== d[1][1]) { push(); st.prims.push({ t: 'line', x1: d[0][0], y1: d[0][1], x2: d[1][0], y2: d[1][1], ...(st.dash ? { dash: true } : {}) }); } st.draft = []; }
    else if (t === 'rect' && d.length === 2) { const w = Math.abs(d[1][0] - d[0][0]), hh = Math.abs(d[1][1] - d[0][1]); if (w && hh) { push(); st.prims.push({ t: 'rect', x: Math.min(d[0][0], d[1][0]), y: Math.min(d[0][1], d[1][1]), w, h: hh, ...opts() }); } st.draft = []; }
    else if (t === 'circle' && d.length === 2) { const r = Math.hypot(d[1][0] - d[0][0], d[1][1] - d[0][1]); if (r > 0) { push(); st.prims.push({ t: 'circle', cx: d[0][0], cy: d[0][1], r: +r.toFixed(4), fill: st.fill }); } st.draft = []; }
    else if (t === 'arc' && d.length === 3) {
      const r = Math.hypot(d[1][0] - d[0][0], d[1][1] - d[0][1]);
      const a0 = Math.atan2(d[1][1] - d[0][1], d[1][0] - d[0][0]) * 180 / Math.PI;
      let a1 = Math.atan2(d[2][1] - d[0][1], d[2][0] - d[0][0]) * 180 / Math.PI;
      if (a1 <= a0) a1 += 360;
      if (r > 0) { push(); st.prims.push({ t: 'arc', cx: d[0][0], cy: d[0][1], r: +r.toFixed(4), a0: +a0.toFixed(2), a1: +a1.toFixed(2), ...(st.dash ? { dash: true } : {}) }); }
      st.draft = [];
    }
    draw();
  }
  function finishPoly() {
    if (st.tool === 'poly' && st.draft.length >= 2) { push(); st.prims.push({ t: 'poly', pts: st.draft, closed: st.close || st.fill, fill: st.fill, ...(st.dash ? { dash: true } : {}) }); }
    st.draft = []; draw();
  }
  function del() {
    if (!st.sel) return;
    push();
    if (st.sel.kind === 'p') st.prims.splice(st.sel.i, 1); else st.terms.splice(st.sel.i, 1);
    st.sel = null; draw();
  }

  let listEl;
  await modal({
    title: isEdit ? `Edit symbol: ${base.name}` : (copy ? `New custom symbol (copy of ${base.name})` : 'New symbol'),
    buttons: [], width: 940,
    build: (body, dlg) => {
      svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('class', 'se-canvas');
      svg.setAttribute('viewBox', `${-HALF} ${-HALF} ${HALF * 2} ${HALF * 2}`);
      svg.setAttribute('width', PX); svg.setAttribute('height', PX);
      svg.style.cssText = `width:${PX}px;height:${PX}px;max-width:100%`;
      svg.innerHTML = '<g id="se-g"></g>';
      svg.addEventListener('pointermove', (e) => { st.mouse = toMM(e); if (st.draft.length || st.tool !== 'select') draw(); });
      svg.addEventListener('click', onClick);
      svg.addEventListener('dblclick', () => { if (st.tool === 'poly') { st.draft.pop(); finishPoly(); } });
      svg.addEventListener('contextmenu', (e) => { e.preventDefault(); if (st.tool === 'poly') finishPoly(); else { st.draft = []; draw(); } });
      dlg.onkeydown = (e) => {
        if (e.target.matches('input,textarea,select')) return;
        if (e.key === 'Delete' || e.key === 'Backspace') { del(); e.preventDefault(); }
        else if (e.key === 'Enter') finishPoly();
        else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { pop(); e.preventDefault(); }
        else if (e.key === 'Escape' && st.draft.length) { st.draft = []; draw(); e.stopPropagation(); e.preventDefault(); }
      };
      const tools = h('div', { class: 'se-tools' });
      for (const [id, label, path] of TOOLS) {
        const b = h('button', { class: 'tb' + (id === st.tool ? ' active' : ''), type: 'button', 'data-tool': id, onclick: () => { st.tool = id; st.draft = []; tools.querySelectorAll('.tb').forEach(x => x.classList.toggle('active', x.dataset.tool === id)); draw(); } });
        b.innerHTML = `<svg viewBox="0 0 24 24"><path d="${path}"/></svg><span class="lbl">${label.split(' ')[0]}</span>`;
        b.title = label;
        tools.append(b);
      }
      const chk = (label, key) => { const c = h('input', { type: 'checkbox', onchange: () => { st[key] = c.checked; } }); return h('label', { class: 'check' }, c, label); };
      tools.append(h('hr'), chk('Filled', 'fill'), chk('Dashed', 'dash'), chk('Close poly', 'close'));
      const dir = h('select', { onchange: () => { st.dir = dir.value.split(',').map(Number); } },
        [['0,-1', 'Exits ↑'], ['0,1', 'Exits ↓'], ['-1,0', 'Exits ←'], ['1,0', 'Exits →']].map(([v, l]) => h('option', { value: v }, l)));
      tools.append(dir, h('hr'),
        h('button', { class: 'btn', type: 'button', onclick: pop }, '↶ Undo'),
        h('button', { class: 'btn danger', type: 'button', onclick: del }, 'Delete sel.'),
        h('button', { class: 'btn', type: 'button', onclick: () => { push(); st.prims = []; st.terms = []; st.sel = null; draw(); } }, 'Clear'));

      listEl = h('div', { class: 'muted', style: 'margin-top:6px;font-size:12px' });
      const attrText = base ? (base.attrs || []).map(a => `${a.key} = ${a.default}`).join('\n') : '';
      inputs.name = h('input', { type: 'text', value: base ? (copy ? base.name + ' (custom)' : base.name) : '', placeholder: 'e.g. Capacitor bank' });
      inputs.cat = h('input', { type: 'text', value: base && !base.builtin ? base.category : 'Custom', list: 'se-cats' });
      inputs.prefix = h('input', { type: 'text', value: base ? base.prefix : '', placeholder: 'tag prefix, e.g. CB', maxlength: 8 });
      inputs.attrs = h('textarea', { placeholder: 'One per line:\nRating = 630 A\nType = ACB' });
      inputs.attrs.value = attrText;
      errEl = h('div', { class: 'se-err' });
      const form = h('div', { class: 'se-form' },
        h('div', { class: 'field' }, h('label', {}, 'Name'), inputs.name),
        h('div', { class: 'field' }, h('label', {}, 'Category'), inputs.cat, h('datalist', { id: 'se-cats' }, cats.map(c => h('option', { value: c })))),
        h('div', { class: 'field' }, h('label', {}, 'Tag prefix'), inputs.prefix),
        h('div', { class: 'field' }, h('label', {}, 'Data fields (shown in the label)'), inputs.attrs),
        h('p', { class: 'muted', style: 'font-size:12px;margin:0 0 6px' }, 'Draw on the grid. Origin (0,0) is the insertion point. Terminals snap to 5 mm so wires land on the drawing grid. Right-click or Enter finishes a polyline.'),
        errEl,
        h('div', { style: 'display:flex;gap:8px;justify-content:flex-end;margin-top:auto' },
          h('button', { class: 'btn', type: 'button', onclick: () => dlg.close() }, 'Cancel'),
          h('button', { class: 'btn primary', id: 'se-save', type: 'button', onclick: async () => {
            errEl.textContent = '';
            const name = inputs.name.value.trim();
            if (!name) { errEl.textContent = 'Please enter a name.'; return; }
            if (!st.prims.length) { errEl.textContent = 'Draw at least one shape.'; return; }
            const attrs = inputs.attrs.value.split('\n').map(l => l.trim()).filter(Boolean).map(l => { const i = l.indexOf('='); return i < 0 ? { key: l, default: '' } : { key: l.slice(0, i).trim(), default: l.slice(i + 1).trim() }; });
            const payload = { name, category: inputs.cat.value.trim() || 'Custom', prefix: inputs.prefix.value.trim(), prims: st.prims, terminals: st.terms, attrs };
            if (isEdit) payload.id = base.id;
            try { const r = await api('/api/symbols', { method: 'POST', body: payload }); saved = r.symbol; dlg.close(); } catch (err) { errEl.textContent = err.message; }
          } }, 'Save to library')));
      body.append(h('div', { class: 'se' }, tools, h('div', {}, svg, listEl), form));
      draw();
      return null;
    },
  });
  return saved;
}
