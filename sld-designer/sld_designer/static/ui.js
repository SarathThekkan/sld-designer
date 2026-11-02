// ui.js - tiny DOM + dialog helpers.

export function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'html') el.innerHTML = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'value') el.value = v;
    else if (k === 'checked' || k === 'disabled' || k === 'selected') el[k] = !!v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return el;
}

export function icon(path, extra = '') {
  return `<svg viewBox="0 0 24 24" ${extra}>${path}</svg>`;
}

export function toast(msg, isErr = false, ms = 3500) {
  const box = document.getElementById('toasts');
  const t = h('div', { class: 'toast' + (isErr ? ' err' : '') }, msg);
  box.append(t);
  setTimeout(() => t.remove(), isErr ? ms * 2 : ms);
}

export async function api(path, { method = 'GET', body, raw = false } = {}) {
  const opt = { method, headers: { 'X-SLD-Client': '1' } };
  if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
  const r = await fetch(path, opt);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).error || msg; } catch { /* not json */ }
    throw new Error(msg);
  }
  return raw ? r : r.json();
}

/** Modal dialog. buildBody(bodyEl) may return a function that produces the result for the primary button. */
export function modal({ title, build, buttons = [{ label: 'Cancel', value: null }, { label: 'OK', value: true, primary: true }], width }) {
  const dlg = h('dialog');
  document.body.append(dlg);
  return new Promise((resolve) => {
    const body = h('div', { class: 'dlg-b' });
    const getResult = build ? build(body, dlg) : null;
    const foot = h('div', { class: 'dlg-f' });
    let done = false;
    const close = (v) => { if (done) return; done = true; dlg.close(); dlg.remove(); resolve(v); };
    for (const b of buttons) {
      foot.append(h('button', { class: 'btn' + (b.primary ? ' primary' : '') + (b.danger ? ' danger' : ''), type: 'button',
        onclick: () => close(b.primary && getResult ? (getResult() ?? undefined) : b.value) }, b.label));
    }
    dlg.replaceChildren(h('div', { class: 'dlg-h' }, title), body, foot);
    dlg.style.width = width ? width + 'px' : '';
    dlg.oncancel = () => { if (!done) { done = true; resolve(null); } };
    dlg.onclose = () => { dlg.remove(); if (!done) { done = true; resolve(null); } };
    dlg.showModal();
    const first = body.querySelector('input,textarea,select');
    if (first) { first.focus(); first.select?.(); }
  });
}

export async function askText(title, label, value = '', multiline = false) {
  let inp;
  const r = await modal({
    title, width: 380,
    build: (body, dlg) => {
      inp = multiline ? h('textarea', { rows: 4 }) : h('input', { type: 'text' });
      inp.value = value;
      inp.addEventListener('keydown', (e) => { if (e.key === 'Enter' && (!multiline || e.ctrlKey)) { e.preventDefault(); dlg.querySelector('.btn.primary').click(); } });
      body.append(h('div', { class: 'field' }, h('label', {}, label + (multiline ? '  (Ctrl+Enter to confirm)' : '')), inp));
      return () => inp.value;
    },
  });
  return r === null || r === undefined ? null : r;
}

export async function confirmBox(title, message, okLabel = 'OK', danger = false) {
  const r = await modal({
    title, width: 420,
    build: (body) => { body.append(h('p', { style: 'margin:0;white-space:pre-wrap' }, message)); },
    buttons: [{ label: 'Cancel', value: false }, { label: okLabel, value: true, primary: true, danger }],
  });
  return r === true;
}

export function download(blobOrText, filename, type = 'application/octet-stream') {
  const blob = blobOrText instanceof Blob ? blobOrText : new Blob([blobOrText], { type });
  const url = URL.createObjectURL(blob);
  const a = h('a', { href: url, download: filename });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}
