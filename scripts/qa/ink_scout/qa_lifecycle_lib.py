TRACK = r"""
(() => {
  const L = new Map(); const R = new Set(); const I = new Set(); let fid = 0; const ids = new WeakMap();
  const idOf = (f) => { if (!ids.has(f)) ids.set(f, ++fid); return ids.get(f); };
  const add = EventTarget.prototype.addEventListener, rem = EventTarget.prototype.removeEventListener;
  const tag = (t) => (t === window ? 'window' : t === document ? 'document' : null);
  EventTarget.prototype.addEventListener = function (type, fn, o) {
    const g = tag(this); if (g && fn) { const cap = typeof o === 'object' ? !!o.capture : !!o; L.set(`${g}:${type}:${cap}:${idOf(fn)}`, 1); }
    return add.call(this, type, fn, o);
  };
  EventTarget.prototype.removeEventListener = function (type, fn, o) {
    const g = tag(this); if (g && fn) { const cap = typeof o === 'object' ? !!o.capture : !!o; L.delete(`${g}:${type}:${cap}:${idOf(fn)}`); }
    return rem.call(this, type, fn, o);
  };
  const raf = window.requestAnimationFrame.bind(window), caf = window.cancelAnimationFrame.bind(window);
  window.requestAnimationFrame = (cb) => { const id = raf((t) => { R.delete(id); cb(t); }); R.add(id); return id; };
  window.cancelAnimationFrame = (id) => { R.delete(id); caf(id); };
  const si = window.setInterval.bind(window), ci = window.clearInterval.bind(window);
  window.setInterval = (f, ms, ...a) => { const id = si(f, ms, ...a); I.add(id); return id; };
  window.clearInterval = (id) => { I.delete(id); ci(id); };
  window.__trk = () => ({ listeners: L.size, byType: [...L.keys()].reduce((m, k) => { const t = k.split(':').slice(0, 2).join(':'); m[t] = (m[t] || 0) + 1; return m; }, {}), raf: R.size, intervals: I.size });
})();
"""
