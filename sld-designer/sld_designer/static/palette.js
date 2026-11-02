// palette.js - symbol library browser (left panel).
import { h, api, toast, confirmBox, download } from './ui.js';
import { symbolItems, itemsBBox, itemsSvg } from './core.js';
import { openSymbolEditor } from './symed.js';

export function thumbSvg(sym, px = 48) {
  const items = symbolItems(sym, { x: 0, y: 0, rot: 0, mirror: false });
  const bb = itemsBBox(items) || [-5, -5, 5, 5];
  const w = bb[2] - bb[0], hh = bb[3] - bb[1];
  const size = Math.max(w, hh, 10) + 4;
  const cx = (bb[0] + bb[2]) / 2, cy = (bb[1] + bb[3]) / 2;
  const minW = 1.3 / (px / size);
  return `<svg viewBox="${cx - size / 2} ${cy - size / 2} ${size} ${size}" width="${px}" height="${px}" color="currentColor">${itemsSvg(items, minW)}</svg>`;
}

export class Palette {
  constructor(root, app) {
    this.root = root; this.app = app; this.filter = ''; this.active = null; this.symbols = [];
    this.search = h('input', { type: 'search', placeholder: 'Search symbols…', 'aria-label': 'Search symbols' });
    this.search.addEventListener('input', () => { this.filter = this.search.value.trim().toLowerCase(); this.renderList(); });
    this.list = h('div', { id: 'pal-list' });
    root.append(
      h('div', { class: 'pal-head' }, h('h3', {}, 'Symbol library'), this.search),
      this.list,
      h('div', { class: 'pal-foot' },
        h('button', { class: 'btn wide', type: 'button', onclick: () => this.newSymbol() }, '＋ New symbol…'),
        h('button', { class: 'btn', type: 'button', onclick: () => this.importLib() }, 'Import…'),
        h('button', { class: 'btn', type: 'button', onclick: () => this.exportLib() }, 'Export…')),
    );
    this.fileInput = h('input', { type: 'file', accept: '.sldlib,application/json', hidden: true });
    this.fileInput.addEventListener('change', () => this.onFile());
    root.append(this.fileInput);
  }

  setSymbols(list) {
    this.symbols = list;
    this.app.editor.library = new Map(list.map(s => [s.id, s]));
    this.renderList();
  }
  setActive(id) { this.active = id; this.list.querySelectorAll('.sym').forEach(b => b.classList.toggle('active', b.dataset.id === id)); }

  renderList() {
    const f = this.filter;
    const cats = new Map();
    for (const s of this.symbols) {
      if (f && !(s.name + ' ' + s.category + ' ' + s.id + ' ' + s.prefix + ' ' + (s.keywords || '')).toLowerCase().includes(f)) continue;
      if (!cats.has(s.category)) cats.set(s.category, []);
      cats.get(s.category).push(s);
    }
    const open = new Set([...this.list.querySelectorAll('details[open]')].map(d => d.dataset.cat));
    const first = !this.list.children.length;
    this.list.replaceChildren();
    for (const [cat, syms] of cats) {
      const d = h('details', { class: 'cat', 'data-cat': cat });
      if (f || first || open.has(cat) || cat === 'Custom') d.open = true;
      d.append(h('summary', {}, `${cat} (${syms.length})`));
      const grid = h('div', { class: 'sym-grid' });
      for (const s of syms) grid.append(this.item(s));
      d.append(grid);
      this.list.append(d);
    }
    if (!cats.size) this.list.append(h('p', { class: 'muted' }, 'No symbols match.'));
    this.setActive(this.active);
  }

  item(s) {
    const b = h('div', { class: 'sym', role: 'button', tabindex: 0, 'data-id': s.id, title: `${s.name}${s.builtin ? '' : ' (custom)'}` });
    b.innerHTML = thumbSvg(s) + '';
    b.append(h('span', {}, s.name));
    if (!s.builtin) b.append(h('i', { class: 'badge' }, '★'));
    const mini = h('div', { class: 'mini' });
    if (s.builtin) mini.append(h('button', { title: 'Copy to a new custom symbol', onclick: (e) => { e.stopPropagation(); this.edit(s, true); } }, '⧉'));
    else {
      mini.append(h('button', { title: 'Edit symbol', onclick: (e) => { e.stopPropagation(); this.edit(s, false); } }, '✎'));
      mini.append(h('button', { title: 'Delete symbol', onclick: (e) => { e.stopPropagation(); this.remove(s); } }, '×'));
    }
    b.append(mini);
    const go = () => { this.app.editor.setTool('place', { sym: s.id }); this.setActive(s.id); };
    b.addEventListener('click', go);
    b.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
    return b;
  }

  async reload() { const { symbols } = await api('/api/symbols'); this.setSymbols(symbols); }

  async newSymbol() { await this.edit(null, false); }
  async edit(sym, copy) {
    const saved = await openSymbolEditor(this.app, sym, { copy });
    if (saved) {
      const ed = this.app.editor;
      if (ed.project.symbols && ed.project.symbols[saved.id]) delete ed.project.symbols[saved.id];  // follow the library again
      await this.reload();
      ed.render();
      toast(`Symbol "${saved.name}" saved to your library.`);
    }
  }
  async remove(s) {
    if (!(await confirmBox('Delete symbol', `Delete "${s.name}" from your library?\nDrawings that already use it keep their own copy.`, 'Delete', true))) return;
    try { await api('/api/symbols/' + encodeURIComponent(s.id), { method: 'DELETE' }); await this.reload(); } catch (e) { toast(e.message, true); }
  }

  importLib() { this.fileInput.value = ''; this.fileInput.click(); }
  async onFile() {
    const f = this.fileInput.files[0];
    if (!f) return;
    try {
      const data = JSON.parse(await f.text());
      const r = await api('/api/library/import', { method: 'POST', body: { data } });
      this.setSymbols(r.symbols);
      const n = r.added.length + r.replaced.length;
      toast(`Imported ${n} symbol(s)` + (r.unchanged.length ? `, ${r.unchanged.length} already in your library` : '') + (r.problems.length ? `, skipped ${r.problems.length} invalid` : '') + '.', r.problems.length > 0);
    } catch (e) { toast('Import failed: ' + e.message, true); }
  }
  async exportLib() {
    const custom = this.symbols.filter(s => !s.builtin);
    if (!custom.length) { toast('There are no custom symbols to export yet. Create one with “New symbol…”.', true); return; }
    try {
      const r = await api('/api/library/export', { raw: true });
      download(await r.blob(), 'my-symbols.sldlib', 'application/json');
      toast(`Exported ${custom.length} custom symbol(s).`);
    } catch (e) { toast(e.message, true); }
  }
}
