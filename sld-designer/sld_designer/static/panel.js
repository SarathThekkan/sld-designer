// panel.js - properties panel (right side).
import { h, askText } from './ui.js';
import { SHEETS, ST } from './core.js';

const CABLE_PRESETS = ['XVB 3G1,5 mm²', 'XVB 3G2,5 mm²', 'XVB 5G2,5 mm²', 'XVB 3G6 mm²', 'XVB 5G6 mm²',
  'XVB 4G10 mm²', 'XVB 5G10 mm²', 'XVB 5G16 mm²', 'VOB 2,5 mm² in buis', 'VOB 6 mm² in buis',
  'EXVB 4x1,5 mm²', 'EAXVB 4x16 mm²', 'EAXVB 4x25 mm²', 'XGB 5G2,5 mm²', 'Cu 16 mm² (aarding)'];

export class Panel {
  constructor(root, app) { this.root = root; this.app = app; }

  get ed() { return this.app.editor; }

  render() {
    const ed = this.ed;
    if (!ed || !ed.project) return;
    const ids = [...ed.sel];
    const root = this.root;
    root.replaceChildren();
    if (ids.length === 0) return root.append(...this.sheetPanel());
    if (ids.length > 1) return root.append(this.multiPanel(ids));
    const obj = ed.find(ids[0]);
    if (!obj) return root.append(...this.sheetPanel());
    if (obj.pts && obj.id.startsWith('w')) return root.append(...this.wirePanel(obj));
    const t = obj.type;
    if (t === 'sym' || t === 'bus') return root.append(...this.symPanel(obj));
    if (t === 'text') return root.append(...this.textPanel(obj));
    if (t === 'rect' || t === 'line') return root.append(...this.shapePanel(obj));
  }

  // helpers ---------------------------------------------------------------
  field(label, input) { return h('div', { class: 'field' }, h('label', {}, label), input); }
  text(label, obj, key, { apply, multiline = false, type = 'text', step } = {}) {
    const inp = multiline ? h('textarea', { rows: 3 }) : h('input', { type, step });
    inp.value = obj[key] ?? '';
    inp.addEventListener('change', () => {
      const v = type === 'number' ? parseFloat(inp.value) : inp.value;
      if (type === 'number' && !isFinite(v)) { inp.value = obj[key]; return; }
      this.ed.mutate(() => { if (apply) apply(v); else obj[key] = v; }, { quiet: true });
    });
    return this.field(label, inp);
  }
  numInput(value, apply) {
    const inp = h('input', { type: 'number', step: 1, value });
    inp.addEventListener('change', () => { const v = parseFloat(inp.value); if (isFinite(v)) this.ed.mutate(() => apply(v), { quiet: true }); });
    return inp;
  }
  select(label, value, options, onChange) {
    const s = h('select', {}, options.map(([v, l]) => h('option', { value: v, selected: String(v) === String(value) }, l)));
    s.addEventListener('change', () => onChange(s.value));
    return this.field(label, s);
  }
  check(label, value, onChange) {
    const c = h('input', { type: 'checkbox', checked: value });
    c.addEventListener('change', () => onChange(c.checked));
    return h('label', { class: 'check' }, c, label);
  }
  button(label, fn, cls = '') { return h('button', { class: 'btn ' + cls, type: 'button', onclick: fn }, label); }
  section(title, ...kids) { return h('section', {}, h('h3', {}, title), ...kids); }

  // panels ----------------------------------------------------------------
  sheetPanel() {
    const ed = this.ed, p = ed.project, sh = p.sheet;
    const upd = (fn) => { ed.checkpoint(); fn(); ed.setDirty(true); ed.render(); this.app.syncToggles(); };
    const out = [];
    out.push(this.section('Drawing sheet',
      this.select('Sheet size', sh.size, Object.keys(SHEETS).map(k => [k, `${k}  (${SHEETS[k][0]} × ${SHEETS[k][1]} mm)`]), (v) => { upd(() => { sh.size = v; }); ed.fit(); }),
      this.select('Orientation', sh.orientation, [['landscape', 'Landscape'], ['portrait', 'Portrait']], (v) => { upd(() => { sh.orientation = v; }); ed.fit(); }),
      this.select('Grid spacing', sh.grid, ST.grids.map(g => [g, g + ' mm']), (v) => upd(() => { sh.grid = parseFloat(v); })),
      this.check('Snap to grid', sh.snap, (v) => upd(() => { sh.snap = v; })),
      this.check('Show grid', sh.showGrid, (v) => upd(() => { sh.showGrid = v; })),
    ));
    const tb = h('div', {});
    const labels = { project: 'Project', title: 'Title', number: 'Drawing no.', rev: 'Revision', date: 'Date', company: 'Company', drawn: 'Drawn by', checked: 'Checked by', scale: 'Scale', sheet: 'Sheet' };
    for (const [k, l] of Object.entries(labels)) {
      const inp = h('input', { type: 'text', value: p.title[k] || '' });
      inp.addEventListener('change', () => { ed.checkpoint(); p.title[k] = inp.value; ed.setDirty(true); ed.render(); this.app.updateDocName(); });
      tb.append(this.field(l, inp));
    }
    out.push(this.section('Title block', tb));
    out.push(h('p', { class: 'muted' }, 'Select an object to edit its properties. Press ', h('span', { class: 'kbd' }, 'W'), ' to draw wires, ', h('span', { class: 'kbd' }, 'B'), ' for busbars.'));
    return out;
  }

  multiPanel(ids) {
    const ed = this.ed;
    return h('div', {}, this.section(`${ids.length} objects selected`,
      h('div', { class: 'row' }, this.button('Rotate', () => ed.rotateSelection()), this.button('Mirror', () => ed.mirrorSelection())),
      h('div', { class: 'row', style: 'margin-top:6px' }, this.button('Copy', () => { ed.copy(); }), this.button('Delete', () => ed.deleteSelection(), 'danger'))));
  }

  symPanel(el) {
    const ed = this.ed;
    const sym = el.type === 'sym' ? ed.symbols(el.sym) : null;
    const out = [];
    out.push(this.section(el.type === 'bus' ? 'Busbar' : (sym ? sym.name : 'Symbol (missing)'),
      this.text('Tag', el, 'tag'),
      this.select('Label position', el.lp || 'r', [['r', 'Right'], ['l', 'Left'], ['t', 'Above'], ['b', 'Below']], (v) => ed.mutate(() => { el.lp = v; }, { quiet: true })),
      h('div', { class: 'row' },
        this.field('Label shift X (mm)', this.numInput((el.lo || [0, 0])[0], (v) => { el.lo = [v, (el.lo || [0, 0])[1]]; })),
        this.field('Label shift Y (mm)', this.numInput((el.lo || [0, 0])[1], (v) => { el.lo = [(el.lo || [0, 0])[0], v]; })))));
    const attrs = h('div', {});
    for (const key of Object.keys(el.attrs || {})) {
      const inp = h('input', { type: 'text', value: el.attrs[key] });
      inp.addEventListener('change', () => ed.mutate(() => { el.attrs[key] = inp.value; }, { quiet: true }));
      const x = h('button', { class: 'x', type: 'button', title: 'Remove field', onclick: () => { ed.mutate(() => { delete el.attrs[key]; }); } }, '×');
      attrs.append(h('div', { class: 'attr' }, this.field(key, inp), x));
    }
    attrs.append(this.button('+ Add field', async () => {
      const k = await askText('New field', 'Field name (e.g. Cable, Length)');
      if (k && k.trim()) ed.mutate(() => { el.attrs = el.attrs || {}; el.attrs[k.trim()] = ''; });
    }, 'wide'));
    out.push(this.section('Data (shown in the label)', attrs));
    if (el.type === 'bus') {
      out.push(this.section('Geometry',
        h('div', { class: 'row' }, this.text('X (mm)', el, 'x', { type: 'number', step: ed.grid() }), this.text('Y (mm)', el, 'y', { type: 'number', step: ed.grid() })),
        this.text('Length (mm)', el, 'len', { type: 'number', step: ed.grid(), apply: (v) => { el.len = Math.max(5, v); } }),
        this.select('Orientation', el.rot || 0, [[0, 'Horizontal'], [90, 'Vertical']], (v) => ed.mutate(() => { el.rot = +v; }, { quiet: true }))));
    } else {
      out.push(this.section('Position',
        h('div', { class: 'row' }, this.text('X (mm)', el, 'x', { type: 'number', step: ed.grid() }), this.text('Y (mm)', el, 'y', { type: 'number', step: ed.grid() })),
        h('div', { class: 'row' }, this.button('Rotate  R', () => ed.rotateSelection()), this.button('Mirror  M', () => ed.mirrorSelection()))));
    }
    out.push(h('div', {}, this.button('Delete', () => ed.deleteSelection(), 'danger wide')));
    return out;
  }

  wirePanel(w) {
    const ed = this.ed;
    const conn = (r) => (r ? 'connected' : 'free end');
    return [
      this.section('Wire / cable',
        this.text('Label (cable, size, length…)', w, 'label', { multiline: true }),
        this.select('Preset (Belgian cables)', '', [['', '— choose —'], ...CABLE_PRESETS.map((c) => [c, c])], (v) => {
          if (v) ed.mutate(() => { w.label = v; });
        }),
        h('p', { class: 'muted' }, `Start: ${conn(w.a)} · End: ${conn(w.b)}`),
        h('div', { class: 'row' }, this.button('Auto-route', () => ed.autoRouteSelection()), this.button('Delete', () => ed.deleteSelection(), 'danger')),
        h('p', { class: 'muted', style: 'margin-top:10px' }, 'Drag the square handles to move a wire segment.')),
    ];
  }

  textPanel(el) {
    const ed = this.ed;
    return [
      this.section('Text',
        this.text('Text', el, 's', { multiline: true }),
        this.text('Size (mm)', el, 'size', { type: 'number', step: 0.5 }),
        this.select('Alignment', el.anchor || 'start', [['start', 'Left'], ['middle', 'Centre'], ['end', 'Right']], (v) => ed.mutate(() => { el.anchor = v; }, { quiet: true })),
        this.check('Bold', el.bold, (v) => ed.mutate(() => { el.bold = v; }, { quiet: true })),
        h('div', { class: 'row' }, this.text('X (mm)', el, 'x', { type: 'number' }), this.text('Y (mm)', el, 'y', { type: 'number' })),
        this.button('Delete', () => ed.deleteSelection(), 'danger wide')),
    ];
  }

  shapePanel(el) {
    const ed = this.ed;
    const out = [this.section(el.type === 'rect' ? 'Enclosure rectangle' : 'Line',
      this.check('Dashed', !!el.dash, (v) => ed.mutate(() => { el.dash = v; }, { quiet: true })))];
    if (el.type === 'rect') out.push(h('div', {},
      h('div', { class: 'row' }, this.text('X', el, 'x', { type: 'number' }), this.text('Y', el, 'y', { type: 'number' })),
      h('div', { class: 'row' }, this.text('Width', el, 'w', { type: 'number' }), this.text('Height', el, 'h', { type: 'number' }))));
    out.push(this.button('Delete', () => ed.deleteSelection(), 'danger wide'));
    return out;
  }
}
