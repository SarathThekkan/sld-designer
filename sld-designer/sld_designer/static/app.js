// app.js - application shell: menus, toolbar, file handling, status bar.
import { setConfig, ST, standaloneSvg, sheetSize, TB } from './core.js';
import { Editor, TOOL_HINTS } from './editor.js';
import { Panel } from './panel.js';
import { Palette } from './palette.js';
import { h, api, toast, askText, confirmBox, download, modal } from './ui.js';

const $ = (id) => document.getElementById(id);
const app = {};
window.sld = app;                      // handy for debugging / automated tests

const I = {
  select: 'M5 3l12 7-5 1.5L9.5 17z', pan: 'M12 3v18M3 12h18M12 3l-3 3M12 3l3 3M12 21l-3-3M12 21l3-3M3 12l3-3M3 12l3 3M21 12l-3-3M21 12l-3 3',
  wire: 'M4 19h6V6h10M4 19m-1.5 0a1.5 1.5 0 1 0 3 0a1.5 1.5 0 1 0-3 0M20 6m-1.5 0a1.5 1.5 0 1 0 3 0a1.5 1.5 0 1 0-3 0',
  bus: 'M3 12h18', rect: 'M4 6h16v12H4z', line: 'M4 20L20 4', text: 'M5 6h14M12 6v13',
  rotate: 'M20 12a8 8 0 1 1-3-6.2M20 4v5h-5', mirror: 'M12 3v18M8 7L3 12l5 5zM16 7l5 5-5 5z', trash: 'M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13',
  undo: 'M9 14L4 9l5-5M4 9h9a6 6 0 0 1 0 12h-3', redo: 'M15 14l5-5-5-5M20 9h-9a6 6 0 0 0 0 12h3',
  fit: 'M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5', zin: 'M11 11m-7 0a7 7 0 1 0 14 0a7 7 0 1 0-14 0M16 16l5 5M8 11h6M11 8v6', zout: 'M11 11m-7 0a7 7 0 1 0 14 0a7 7 0 1 0-14 0M16 16l5 5M8 11h6',
  grid: 'M4 4h16v16H4zM4 12h16M12 4v16', snap: 'M5 4v8a7 7 0 0 0 14 0V4h-4v8a3 3 0 0 1-6 0V4z',
  pdf: 'M6 3h8l4 4v14H6zM14 3v4h4', print: 'M7 9V3h10v6M7 17H4v-7h16v7h-3M7 14h10v7H7z',
};
const svgIcon = (k) => `<svg viewBox="0 0 24 24"><path d="${I[k]}"${k === 'bus' ? ' style="stroke-width:4"' : ''}${k === 'rect' ? ' stroke-dasharray="3 2"' : ''}/></svg>`;

// -------------------------------------------------------------------- project
function newProject() {
  const today = new Date().toISOString().slice(0, 10);
  return {
    format: 'SLD-CAD', version: 1, meta: { app: 'SLD Designer', modified: today },
    sheet: { size: 'A3', orientation: 'landscape', grid: 5, snap: true, showGrid: true },
    title: { project: '', title: 'Single Line Diagram', number: 'SLD-001', rev: 'A', date: today, company: '', drawn: '', checked: '', scale: 'NTS', sheet: '1 / 1' },
    symbols: {}, elements: [], wires: [], nextId: 1,
  };
}

app.fileHandle = null;
app.fileName = null;

app.updateDocName = () => {
  const ed = app.editor;
  const name = app.fileName || 'Untitled.cad';
  $('docname').innerHTML = `<b>${name.replace(/</g, '&lt;')}</b>${ed.dirty ? ' ●' : ''}`;
  document.title = `${ed.dirty ? '• ' : ''}${name} - SLD Designer`;
};

async function guardUnsaved(what) {
  if (!app.editor.dirty) return true;
  return confirmBox('Unsaved changes', `The current drawing has unsaved changes.\nDiscard them and ${what}?`, 'Discard', true);
}

async function fileNew() {
  if (!(await guardUnsaved('start a new drawing'))) return;
  app.editor.setProject(newProject());
  app.fileHandle = null; app.fileName = null;
  clearAutosave(); app.panel.render(); app.syncToggles(); app.updateDocName();
}

async function loadText(text, name, handle) {
  let json;
  try { json = JSON.parse(text); } catch { throw new Error('This file is not valid JSON, so it is not an SLD Designer .cad file.'); }
  const r = await api('/api/project/validate', { method: 'POST', body: json });
  const p = r.project;
  // offer to keep custom symbols that only exist inside the file
  const missing = Object.values(p.symbols).filter(s => !app.editor.library.has(s.id));
  app.editor.setProject(p);
  app.fileHandle = handle || null; app.fileName = name;
  app.panel.render(); app.syncToggles(); app.updateDocName();
  if (missing.length) {
    if (await confirmBox('Custom symbols found', `This drawing uses ${missing.length} custom symbol(s) that are not in your library:\n${missing.map(s => '• ' + s.name).join('\n')}\n\nAdd them to your library?`, 'Add to library')) {
      for (const s of missing) { try { await api('/api/symbols', { method: 'POST', body: s }); } catch (e) { toast(e.message, true); } }
      await app.palette.reload();
    }
  }
}

async function fileOpen() {
  if (!(await guardUnsaved('open another file'))) return;
  try {
    if (window.showOpenFilePicker) {
      const [handle] = await window.showOpenFilePicker({ types: [{ description: 'SLD Designer drawing', accept: { 'application/json': ['.cad'] } }] });
      const f = await handle.getFile();
      await loadText(await f.text(), f.name, handle);
    } else {
      const inp = h('input', { type: 'file', accept: '.cad,application/json' });
      inp.addEventListener('change', async () => {
        const f = inp.files[0];
        if (f) try { await loadText(await f.text(), f.name, null); } catch (e) { toast(e.message, true); }
      });
      inp.click();
    }
  } catch (e) { if (e.name !== 'AbortError') toast('Could not open file: ' + e.message, true); }
}
app.openText = loadText;   // used by tests / drag-and-drop

function baseName() {
  const t = app.editor.project.title;
  return (app.fileName ? app.fileName.replace(/\.cad$/i, '') : (t.number || t.title || 'drawing')).replace(/[^\w\-. ]+/g, '_');
}

async function fileSave(saveAs = false) {
  const ed = app.editor;
  const text = JSON.stringify({ ...ed.exportable(), meta: { app: 'SLD Designer 1.0.0', modified: new Date().toISOString() } }, null, 1);
  try {
    if (window.showSaveFilePicker) {
      let handle = saveAs ? null : app.fileHandle;
      if (!handle) handle = await window.showSaveFilePicker({ suggestedName: baseName() + '.cad', types: [{ description: 'SLD Designer drawing', accept: { 'application/json': ['.cad'] } }] });
      const w = await handle.createWritable(); await w.write(text); await w.close();
      app.fileHandle = handle; app.fileName = handle.name;
    } else {
      if (saveAs || !app.fileName) {
        const n = await askText('Save drawing', 'File name', baseName());
        if (!n) return;
        app.fileName = n.replace(/\.cad$/i, '') + '.cad';
      }
      download(text, app.fileName, 'application/json');
    }
    ed.setDirty(false); clearAutosave(); app.updateDocName();
    toast('Saved ' + app.fileName);
  } catch (e) { if (e.name !== 'AbortError') toast('Save failed: ' + e.message, true); }
}

async function serverExport(kind) {
  const r = await api('/api/export/' + kind, { method: 'POST', body: app.editor.exportable(), raw: true });
  return r.blob();
}
async function exportPdf() {
  try { const b = await serverExport('pdf'); download(b, baseName() + '.pdf', 'application/pdf'); toast('PDF exported.'); }
  catch (e) { toast('PDF export failed: ' + e.message, true); }
}
async function printPdf() {
  const w = window.open('', '_blank');           // open synchronously (inside the click) so pop-up blockers allow it
  try {
    const b = await serverExport('pdf');
    if (w) { w.location.href = URL.createObjectURL(b); }
    else { download(b, baseName() + '.pdf'); toast('Pop-up blocked - the PDF was downloaded instead. Open it and print.', true); }
  } catch (e) { if (w) w.close(); toast('Print failed: ' + e.message, true); }
}
async function exportDxf() {
  try { const b = await serverExport('dxf'); download(b, baseName() + '.dxf', 'application/dxf'); toast('DXF exported (open it in AutoCAD, LibreCAD, …).'); }
  catch (e) { toast('DXF export failed: ' + e.message, true); }
}
function exportSvg() {
  download(standaloneSvg(app.editor.exportable(), (id) => app.editor.exportable().symbols[id]), baseName() + '.svg', 'image/svg+xml');
}

// -------------------------------------------------------------------- autosave
const AS_KEY = 'sld-designer-autosave';
let asTimer = null;
function scheduleAutosave() {
  clearTimeout(asTimer);
  asTimer = setTimeout(() => {
    try { localStorage.setItem(AS_KEY, JSON.stringify({ t: Date.now(), name: app.fileName, p: app.editor.exportable() })); } catch { /* quota / private mode */ }
  }, 1500);
}
function clearAutosave() { clearTimeout(asTimer); try { localStorage.removeItem(AS_KEY); } catch { /* ignore */ } }
async function offerRestore() {
  let rec = null;
  try { rec = JSON.parse(localStorage.getItem(AS_KEY) || 'null'); } catch { /* ignore */ }
  if (!rec || !rec.p || !(rec.p.elements || []).length) return;
  if (await confirmBox('Recover unsaved drawing?', `An unsaved drawing from ${new Date(rec.t).toLocaleString()} was found in this browser.`, 'Recover')) {
    try { await loadText(JSON.stringify(rec.p), rec.name || null, null); app.editor.setDirty(true); app.updateDocName(); } catch (e) { toast(e.message, true); }
  } else clearAutosave();
}

// ---------------------------------------------------------------- menus/toolbar
function buildMenus() {
  const ed = () => app.editor;
  const defs = [
    ['File', [
      ['New', fileNew, 'Ctrl+Alt+N'], ['Open…', fileOpen, 'Ctrl+O'], ['Save', () => fileSave(false), 'Ctrl+S'], ['Save as…', () => fileSave(true), 'Ctrl+Shift+S'], '-',
      ['Export PDF…', exportPdf, 'Ctrl+E'], ['Print…', printPdf, 'Ctrl+P'], ['Export DXF (AutoCAD)…', exportDxf], ['Export SVG…', exportSvg], '-',
      ['Import symbol library (.sldlib)…', () => app.palette.importLib()], ['Export symbol library (.sldlib)…', () => app.palette.exportLib()],
    ]],
    ['Edit', [
      ['Undo', () => ed().undo(), 'Ctrl+Z'], ['Redo', () => ed().redo(), 'Ctrl+Y'], '-',
      ['Cut', () => { ed().copy(); ed().deleteSelection(); }, 'Ctrl+X'], ['Copy', () => ed().copy(), 'Ctrl+C'], ['Paste', () => ed().paste(), 'Ctrl+V'], ['Duplicate', () => { ed().copy(); ed().paste(); }, 'Ctrl+D'],
      ['Delete', () => ed().deleteSelection(), 'Del'], ['Select all', () => ed().setSelection([...ed().project.elements, ...ed().project.wires].map(x => x.id)), 'Ctrl+A'], '-',
      ['Rotate 90°', () => ed().rotateSelection(), 'R'], ['Mirror', () => ed().mirrorSelection(), 'M'], ['Auto-route selected wire', () => ed().autoRouteSelection()],
    ]],
    ['View', [
      ['Zoom to fit', () => ed().fit(), 'F'], ['Zoom in', () => ed().zoomAt(1.25), '+'], ['Zoom out', () => ed().zoomAt(0.8), '-'], '-',
      ['Toggle grid', () => toggle('showGrid'), 'G'], ['Toggle snap', () => toggle('snap'), 'F9'],
    ]],
    ['Symbols', [
      ['New symbol…', () => app.palette.newSymbol()], ['Import library…', () => app.palette.importLib()], ['Export library…', () => app.palette.exportLib()],
    ]],
    ['Help', [['Keyboard shortcuts & tips', showHelp], ['About', showAbout]]],
  ];
  const nav = $('menus');
  for (const [label, items] of defs) {
    const m = h('div', { class: 'menu' });
    const drop = h('div', { class: 'drop' });
    for (const it of items) {
      if (it === '-') { drop.append(h('hr')); continue; }
      drop.append(h('button', { type: 'button', onclick: () => { closeMenus(); it[1](); } }, h('span', {}, it[0]), it[2] ? h('kbd', {}, it[2]) : ''));
    }
    m.append(h('button', { type: 'button', onclick: (e) => { e.stopPropagation(); const o = m.classList.contains('open'); closeMenus(); if (!o) m.classList.add('open'); }, onmouseenter: () => { if (nav.querySelector('.open')) { closeMenus(); m.classList.add('open'); } } }, label), drop);
    nav.append(m);
  }
  document.addEventListener('click', closeMenus);
}
const closeMenus = () => document.querySelectorAll('.menu.open').forEach(m => m.classList.remove('open'));

function toggle(key) { const s = app.editor.project.sheet; s[key] = !s[key]; app.editor.render(); app.syncToggles(); app.editor.setDirty(true); if (!app.editor.sel.size) app.panel.render(); }

const toolButtons = {};
function buildToolbar() {
  const tb = $('toolbar');
  const btn = (id, key, label, title, fn, cls = '') => {
    const b = h('button', { class: 'tb ' + cls, type: 'button', title, 'aria-label': title, onclick: fn });
    b.innerHTML = svgIcon(key) + (label ? `<span class="lbl">${label}</span>` : '');
    tb.append(b); toolButtons[id] = b; return b;
  };
  const sep = () => tb.append(h('span', { class: 'sep' }));
  const ed = () => app.editor;
  btn('select', 'select', 'Select', 'Select (V)', () => ed().setTool('select'));
  btn('pan', 'pan', '', 'Pan (H)', () => ed().setTool('pan'));
  sep();
  btn('wire', 'wire', 'Wire', 'Draw wire (W)', () => ed().setTool('wire'));
  btn('bus', 'bus', 'Busbar', 'Draw busbar (B)', () => ed().setTool('bus'));
  btn('rect', 'rect', 'Enclosure', 'Dashed enclosure rectangle (X)', () => ed().setTool('rect'));
  btn('line', 'line', 'Line', 'Line (L)', () => ed().setTool('line'));
  btn('text', 'text', 'Text', 'Text (T)', () => ed().setTool('text'));
  sep();
  btn('rotate', 'rotate', '', 'Rotate 90° (R)', () => ed().rotateSelection());
  btn('mirror', 'mirror', '', 'Mirror (M)', () => ed().mirrorSelection());
  btn('delete', 'trash', '', 'Delete (Del)', () => ed().deleteSelection());
  sep();
  btn('undo', 'undo', '', 'Undo (Ctrl+Z)', () => ed().undo());
  btn('redo', 'redo', '', 'Redo (Ctrl+Y)', () => ed().redo());
  sep();
  btn('fit', 'fit', '', 'Zoom to fit (F)', () => ed().fit());
  btn('zin', 'zin', '', 'Zoom in (+)', () => ed().zoomAt(1.25));
  btn('zout', 'zout', '', 'Zoom out (-)', () => ed().zoomAt(0.8));
  sep();
  btn('grid', 'grid', 'Grid', 'Show grid (G)', () => toggle('showGrid'), 'toggle');
  btn('snap', 'snap', 'Snap', 'Snap to grid (F9)', () => toggle('snap'), 'toggle');
  tb.append(h('span', { style: 'flex:1' }));
  btn('print', 'print', 'Print', 'Print (Ctrl+P)', printPdf);
  const pdf = btn('pdf', 'pdf', 'Export PDF', 'Export to PDF (Ctrl+E)', exportPdf);
  pdf.classList.add('primary'); pdf.style.cssText = 'background:var(--accent);color:#fff;border-color:var(--accent)';
}

app.syncToggles = () => {
  const s = app.editor.project.sheet;
  toolButtons.grid.classList.toggle('active', !!s.showGrid);
  toolButtons.snap.classList.toggle('active', !!s.snap);
};

function syncToolbar() {
  const ed = app.editor;
  for (const t of ['select', 'pan', 'wire', 'bus', 'rect', 'line', 'text']) toolButtons[t].classList.toggle('active', ed.tool === t);
  toolButtons.undo.disabled = !ed.undoStack.length;
  toolButtons.redo.disabled = !ed.redoStack.length;
  const has = ed.sel.size > 0;
  for (const k of ['rotate', 'delete']) toolButtons[k].disabled = !has;
  toolButtons.mirror.disabled = ![...ed.sel].some(id => (ed.find(id) || {}).type === 'sym');
}

// ------------------------------------------------------------------------ help
function showHelp() {
  const rows = [['V / H', 'Select / Pan'], ['W', 'Wire (click corners; click a terminal or busbar to finish; Space flips the corner)'], ['B', 'Busbar (drag)'], ['X', 'Dashed enclosure'], ['L', 'Line'], ['T', 'Text'],
    ['R / M', 'Rotate / Mirror (selection or the symbol being placed)'], ['Del', 'Delete'], ['Ctrl+C / V / D', 'Copy / Paste / Duplicate'], ['Ctrl+Z / Y', 'Undo / Redo'], ['Arrow keys', 'Nudge selection by one grid step'],
    ['Wheel / middle-drag', 'Zoom / Pan (also Space+drag)'], ['F', 'Zoom to fit'], ['G / F9', 'Grid / Snap'], ['Ctrl+S / O / E / P', 'Save / Open / Export PDF / Print'],
    ['Box select', 'Left→right selects fully enclosed objects; right→left selects anything touched']];
  modal({ title: 'Shortcuts & tips', width: 560, buttons: [{ label: 'Close', value: true, primary: true }],
    build: (b) => { const t = h('table', { style: 'border-collapse:collapse;width:100%' }); for (const [k, v] of rows) t.append(h('tr', {}, h('td', { style: 'padding:3px 12px 3px 0;white-space:nowrap' }, h('span', { class: 'kbd' }, k)), h('td', { style: 'padding:3px 0' }, v))); b.append(t); } });
}
function showAbout() {
  modal({ title: 'SLD Designer', width: 460, buttons: [{ label: 'Close', value: true, primary: true }],
    build: (b) => b.append(h('p', { style: 'margin:0' }, 'A lightweight single-line-diagram editor for electrical systems. Native project files are .cad (JSON); symbol libraries are .sldlib; drawings export to vector PDF, DXF and SVG.')) });
}

// ------------------------------------------------------------------------ boot
async function boot() {
  buildMenus(); buildToolbar();
  const cfg = await api('/api/config');
  setConfig(cfg);
  app.cfg = cfg;
  const hooks = {
    onSelection: () => { app.panel.render(); syncToolbar(); },
    onHistory: () => { if (app.toolbarReady) syncToolbar(); },
    onDirty: () => { app.updateDocName(); if (app.editor.dirty) scheduleAutosave(); },
    onTool: (t, o) => { syncToolbar(); app.palette.setActive(t === 'place' ? o.sym : null); $('st-hint').textContent = TOOL_HINTS[t] || ''; },
    onStatus: (snap, raw) => {
      $('st-coord').textContent = `${raw[0].toFixed(1)}, ${raw[1].toFixed(1)} mm`;
      $('st-snap').textContent = snap.kind === 'term' ? '⌖ terminal' : snap.kind === 'bus' ? '⌖ busbar' : snap.kind === 'wire' ? '⌖ wire' : '';
    },
    onSheet: () => app.syncToggles(),
    onEdit: async (id) => {
      const el = app.editor.find(id);
      if (el && el.type === 'text') { const s = await askText('Edit text', 'Text', el.s, true); if (s !== null) app.editor.mutate(() => { el.s = s; }); }
      else document.querySelector('#props input')?.focus();
    },
    promptText: (title, v) => askText(title, 'Text', v, true),
  };
  app.editor = new Editor($('canvas'), hooks);
  app.panel = new Panel($('props'), app);
  app.palette = new Palette($('palette'), app);
  const { symbols } = await api('/api/symbols');
  app.palette.setSymbols(symbols);
  app.editor.setProject(newProject());
  app.toolbarReady = true;
  app.panel.render(); app.syncToggles(); syncToolbar(); app.updateDocName();
  $('st-hint').textContent = TOOL_HINTS.select;
  const z = () => { $('st-zoom').textContent = Math.round(app.editor.view.k / 3.7795 * 100) + '%'; };
  const origRender = app.editor.render.bind(app.editor);
  app.editor.render = () => { origRender(); z(); };
  app.editor.render();

  window.addEventListener('keydown', (e) => {
    const ctrl = e.ctrlKey || e.metaKey; const k = e.key.toLowerCase();
    if (!ctrl) return;
    const inField = /input|textarea|select/i.test(e.target.tagName);
    if (k === 's') { e.preventDefault(); fileSave(e.shiftKey); }
    else if (k === 'o') { e.preventDefault(); fileOpen(); }
    else if (k === 'e') { e.preventDefault(); exportPdf(); }
    else if (k === 'p') { e.preventDefault(); printPdf(); }
    else if (k === 'n' && e.altKey) { e.preventDefault(); fileNew(); }
    else if (inField) return;
  });
  window.addEventListener('beforeunload', (e) => { if (app.editor.dirty) { e.preventDefault(); e.returnValue = ''; } });
  // drag & drop a .cad file
  document.addEventListener('dragover', (e) => e.preventDefault());
  document.addEventListener('drop', async (e) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f && /\.cad$/i.test(f.name) && await guardUnsaved('open the dropped file')) try { await loadText(await f.text(), f.name, null); } catch (err) { toast(err.message, true); }
  });
  await offerRestore();
  app.ready = true;
}

boot().catch((e) => { console.error(e); toast('Failed to start: ' + e.message, true); });
