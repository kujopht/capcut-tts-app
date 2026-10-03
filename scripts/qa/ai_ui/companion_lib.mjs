/**
 * Hạ tầng DÙNG CHUNG của QA linh vật Ink Scout: viewport, thao tác trang (đăng nhập, mở/đóng panel, chờ linh vật), đo hình học + va chạm,
 * kéo thả chuột/chạm, dòng thời gian trạng thái, lấy mẫu CPU/heap. Tách nguyên văn từ `run_companion.mjs` (harness) để
 * `run_real.mjs` (bản dựng Next THẬT) dùng đúng cùng một cách đo.
 */
import { check, info, sleep } from "./lib.mjs";

export const PREFS_KEY = "fas.aiCompanion.v1";

// ----------------------------------------------------------------------------------------- viewport
export const FLOAT_VPS = [
  { name: "1024", width: 1024, height: 768, mobile: false },
  { name: "desktop", width: 1280, height: 800, mobile: false },
  { name: "wide", width: 1920, height: 1080, mobile: false },
  { name: "ultrawide", width: 2560, height: 1080, mobile: false },
];
export const DESKTOP = FLOAT_VPS[1];
export const TABLET_LANDSCAPE = { name: "tablet-ngang", width: 1024, height: 768, mobile: true };
export const INLINE_VPS = [
  { name: "320", width: 320, height: 568, mobile: true },
  { name: "360", width: 360, height: 740, mobile: true },
  { name: "390", width: 390, height: 844, mobile: true },
  { name: "430", width: 430, height: 932, mobile: true },
  { name: "tablet", width: 768, height: 1024, mobile: true },
  { name: "desktop", width: 1280, height: 800, mobile: false },
  { name: "wide", width: 1920, height: 1080, mobile: false },
];

// Đếm RAF/interval đang chờ + số lần RAF chạy: để chứng minh "yên lặng = không vòng vẽ" và "không rò timer".
export const PERF_PRE = `(() => {
  const o = window.requestAnimationFrame.bind(window), c = window.cancelAnimationFrame.bind(window);
  const S = (window.__perf = { raf: 0, pending: new Set(), intervals: new Set() });
  window.requestAnimationFrame = (cb) => { let id; id = o((t) => { S.pending.delete(id); S.raf += 1; cb(t); }); S.pending.add(id); return id; };
  window.cancelAnimationFrame = (id) => { S.pending.delete(id); c(id); };
  const si = window.setInterval.bind(window), ci = window.clearInterval.bind(window);
  window.setInterval = (f, ms, ...a) => { const id = si(f, ms, ...a); S.intervals.add(id); return id; };
  window.clearInterval = (id) => { S.intervals.delete(id); ci(id); };
})();`;

// ----------------------------------------------------------------------------------------- thao tác trang
export const hostRect = (page) => page.ev(`(() => { const e = document.querySelector('.ai-companion-host'); if (!e) return null; const r = e.getBoundingClientRect(); return { l: r.left, t: r.top, r: r.right, b: r.bottom, w: r.width, h: r.height }; })()`);
export const q = (page, sel) => page.ev(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e) return null; const r = e.getBoundingClientRect(); return { l: r.left, t: r.top, r: r.right, b: r.bottom, w: r.width, h: r.height }; })()`);
export const prefs = (page) => page.ev(`(() => { try { return JSON.parse(localStorage.getItem(${JSON.stringify(PREFS_KEY)}) || 'null'); } catch { return 'bad'; } })()`);
export const mapped = (page) => page.ev(`document.querySelector('.ai-companion')?.getAttribute('data-state') ?? null`);

export async function login(page, user = "alice") {
  // Hạn mức giả mặc định là 5 lượt/ngày (như thật) — kịch bản nhiều lượt cần trần cao, trừ chỗ cố ý thử "hết lượt".
  // `__qa.setUser` chỉ có ở harness; ở bản dựng Next thật phiên đến từ token đặt trong localStorage trước khi trang chạy (`run_real.mjs`).
  await page.ev(`__qa.cap = 1000; if (__qa.setUser) __qa.setUser(${JSON.stringify(user)})`);
}
export async function waitMascot(page, timeout = 14000) {
  await page.wait("document.querySelector('.ai-companion-host canvas') && !document.querySelector('.ai-companion-cho')", timeout, "linh vật sẵn sàng");
}
export async function waitPhysics(page, timeout = 9000) {
  await page.wait("document.querySelector('.ai-companion-live')", timeout, "physics (kéo thả) đã gắn");
}
export async function readyFloating(page, user = "alice") {
  await login(page, user);
  await page.wait("document.querySelector('.ai-launcher')", 8000, "nút nổi");
  await waitMascot(page);
}
export async function openPanel(page) {
  await page.click(".ai-launcher");
  await page.wait("document.querySelector('.ai-panel textarea.ai-o')", 6000, "panel + ô soạn");
}
export async function closePanel(page) {
  await page.click(".ai-panel [aria-label='Đóng trợ lý AI']");
  await page.wait("!document.querySelector('.ai-panel')", 4000, "panel đóng");
}
export async function setMode(page, mode) {
  await page.ev(`(() => { const sel = document.querySelector('select.ai-mode'); const set = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set; set.call(sel, ${JSON.stringify(mode)}); sel.dispatchEvent(new Event('change', { bubbles: true })); })()`);
}

/** Chờ linh vật ĐỨNG YÊN (không bị cầm, hộp host không đổi trong `stableMs`). Trả hộp cuối. */
export async function settled(page, { timeout = 9000, stableMs = 600 } = {}) {
  const end = Date.now() + timeout;
  let last = null, since = Date.now();
  while (Date.now() < end) {
    const r = await hostRect(page);
    const held = await page.ev(`!!document.querySelector('.ai-companion-giu')`);
    const key = r ? `${Math.round(r.l)},${Math.round(r.t)}` : "x";
    if (!held && key === last) {
      if (Date.now() - since >= stableMs) return r;
    } else {
      last = key;
      since = Date.now();
    }
    await sleep(70);
  }
  throw new Error("linh vật không đứng yên trong " + timeout + "ms (cuối: " + last + ")");
}

/** Gửi một lượt, ghi DÒNG THỜI GIAN trạng thái linh vật, đợi xong + `settleMs` cho hoạt ảnh `success` → trở về nền. */
export async function turn(page, text, script, { settleMs = 2200, wait = "done" } = {}) {
  if (script) await page.ev(`__qa.script.push(${JSON.stringify(script)})`);
  const before = await page.ev(`__qa.count('/messages')`);
  await page.ev(`__qa.traceStart()`);
  await page.focus("textarea.ai-o");
  await page.type(text);
  await page.key("Enter");
  await page.wait(`__qa.count('/messages') > ${before}`, 6000, "đã gửi");
  if (wait === "done") {
    await page.wait(`__qa.inflight === 0 && !document.querySelector('.ai-nut-dung')`, 25000, "xong lượt");
    await sleep(settleMs);
    return page.ev(`__qa.traceStop()`);
  }
  return null;
}
export const seq = (tr, kind) => {
  const out = [];
  for (const e of tr) if (e.kind === kind && out[out.length - 1] !== e.state) out.push(e.state);
  return out;
};
/** Thời điểm (ms từ lúc bắt đầu ghi) trạng thái `state` xuất hiện lần đầu / lần đầu mà sau đó đổi sang trạng thái khác. */
export const spanOf = (tr, kind, state) => {
  const i = tr.findIndex((e) => e.kind === kind && e.state === state);
  if (i < 0) return null;
  const j = tr.findIndex((e, k) => k > i && e.kind === kind && e.state !== state);
  return { from: tr[i].t, to: j < 0 ? null : tr[j].t, ms: j < 0 ? null : tr[j].t - tr[i].t };
};

// ----------------------------------------------------------------------------------------- đo hình học / va chạm (chạy trong trang)
export const GEOM = `(() => {
  const q = (s) => document.querySelector(s);
  const R = (e) => { const r = e.getBoundingClientRect(); return { l: r.left, t: r.top, r: r.right, b: r.bottom, w: r.width, h: r.height }; };
  const wrap = q('.ai-companion'), host = q('.ai-companion-host');
  if (!wrap || !host) return { present: false };
  const cs = getComputedStyle(wrap);
  const shown = cs.display !== 'none' && cs.visibility !== 'hidden' && parseFloat(cs.opacity) > 0.01 && !wrap.className.includes('ai-companion-an');
  const h = R(host), size = h.w;
  // Hộp THÂN (cùng hệ số với companionGeometry.mascotBody): trừ phần trong suốt quanh nhân vật.
  const body = { l: h.l + size * 0.2, t: h.t + size * 0.1, r: h.l + size * 0.8, b: h.t + size * 0.96 };
  const inter = (a, b, pad) => a.l < b.r + pad && a.r > b.l - pad && a.t < b.b + pad && a.b > b.t - pad;
  const vis = (e) => { const c = getComputedStyle(e); if (c.display === 'none' || c.visibility === 'hidden') return false; const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const hits = [];
  for (const [name, sel] of [['launcher', '.ai-launcher'], ['dock', '.chat-dock'], ['mini', '.mini'], ['header', '.site-header']]) {
    const e = q(sel); if (!e || !vis(e)) continue;
    const rr = R(e);
    if (!inter(body, rr, 0)) continue;
    // Chồng HỘP chỉ tính khi phần tử đó thật sự nằm trên cùng tại điểm giao (hoặc linh vật nằm trên nó): trang /assistant toàn màn hình
    // (fixed, z-index 70) phủ lên header — không có chồng nhìn thấy nào.
    const cx = (Math.max(body.l, rr.l) + Math.min(body.r, rr.r)) / 2, cy = (Math.max(body.t, rr.t) + Math.min(body.b, rr.b)) / 2;
    // Phần tử NHÌN THẤY ngay dưới linh vật tại điểm giao: nếu đó là chính phần tử đang xét thì linh vật đang đè lên nó.
    const below = document.elementsFromPoint(cx, cy).find((x) => !x.closest('.ai-companion'));
    if (!below || e === below || e.contains(below)) hits.push(name);
  }
  const ctrl = [];
  const panel = q('.ai-panel');
  if (panel && vis(panel)) {
    for (const e of panel.querySelectorAll('button, select, textarea, input, a[href]')) {
      if (!vis(e)) continue;
      if (inter(body, R(e), 0)) ctrl.push((e.getAttribute('aria-label') || e.className || e.tagName).toString().slice(0, 30));
    }
  }
  // Mọi điều khiển quan trọng phải THẬT SỰ là đích của con trỏ (linh vật không được che): elementFromPoint tại tâm.
  const covered = [];
  for (const sel of ['.ai-launcher', ".ai-panel [aria-label='Đóng trợ lý AI']", ".ai-panel [aria-label='Lịch sử hội thoại']", ".ai-panel [aria-label='Hội thoại mới']", '.ai-panel select.ai-mode', '.ai-panel textarea.ai-o', '.ai-panel .ai-nut-gui', '.ai-panel .ai-nut-dung', '.ai-trang textarea.ai-o', '.ai-trang .ai-nut-gui', '.ai-trang .ai-nut-dung', '.ai-trang select.ai-mode', '.site-header a']) {
    const e = q(sel); if (!e || !vis(e)) continue;
    if (sel === '.site-header a' && q('.ai-trang')) continue; // /assistant là trang toàn màn hình: nó CHỦ ĐỊNH phủ lên header
    const r = R(e); const cx = r.l + r.w / 2, cy = r.t + r.h / 2;
    if (cx < 0 || cy < 0 || cx > innerWidth || cy > innerHeight) continue; // ngoài khung nhìn (cuộn đi): elementFromPoint trả null
    const el = document.elementFromPoint(cx, cy);
    if (!(el === e || e.contains(el))) covered.push(sel + ' <- ' + String(el ? (el.className || el.tagName) : 'null').slice(0, 40) + ' @' + Math.round(cx) + ',' + Math.round(cy) + ' rect ' + Math.round(r.l) + ',' + Math.round(r.t) + ' ' + Math.round(r.w) + 'x' + Math.round(r.h));
  }
  const vw = innerWidth, vh = innerHeight;
  return { present: true, shown, h, body, hits, ctrl, covered, inViewport: h.l >= -1 && h.r <= vw + 1 && h.t >= -1 && h.b <= vh + 1, docW: document.documentElement.scrollWidth, vw, vh,
    cls: wrap.className, state: wrap.getAttribute('data-state') };
})()`;
export const geom = (page) => page.ev(GEOM);

export function noCollision(label, vp, g, { allowPanel = false } = {}) {
  if (!g.present || !g.shown) return;
  check(`${label}: nằm trong khung nhìn`, vp.name, g.inViewport, JSON.stringify(g.h));
  check(`${label}: không đè nút mở/Chat Dock/thanh phát/header`, vp.name, g.hits.length === 0, g.hits.join(","));
  check(`${label}: không đè điều khiển nào của panel`, vp.name, g.ctrl.length === 0, g.ctrl.join(", "));
  check(`${label}: không che đích chạm của điều khiển nào`, vp.name, g.covered.length === 0, g.covered.join("; "));
  check(`${label}: không tràn ngang trang`, vp.name, g.docW <= g.vw, `scrollWidth=${g.docW} > ${g.vw}`);
  void allowPanel;
}

// ----------------------------------------------------------------------------------------- chuột / chạm
export async function mouse(page, type, x, y, extra = {}) {
  await page.s("Input.dispatchMouseEvent", { type, x, y, button: type === "mouseMoved" && !extra.buttons ? "none" : "left", buttons: extra.buttons ?? 0, clickCount: type === "mousePressed" || type === "mouseReleased" ? 1 : 0 });
}
export async function dragMouse(page, from, to, { steps = 14, hold = 70, endHold = 120 } = {}) {
  await mouse(page, "mouseMoved", from.x, from.y);
  await mouse(page, "mousePressed", from.x, from.y, { buttons: 1 });
  await sleep(hold);
  for (let i = 1; i <= steps; i += 1) {
    await mouse(page, "mouseMoved", from.x + ((to.x - from.x) * i) / steps, from.y + ((to.y - from.y) * i) / steps, { buttons: 1 });
    await sleep(16);
  }
  await sleep(endHold);
  await mouse(page, "mouseReleased", to.x, to.y, { buttons: 0 });
}
export async function dragTouch(page, from, to, { steps = 14, hold = 70, endHold = 120 } = {}) {
  const pt = (x, y) => [{ x, y, id: 1 }];
  await page.s("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: pt(from.x, from.y) });
  await sleep(hold);
  for (let i = 1; i <= steps; i += 1) {
    await page.s("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: pt(from.x + ((to.x - from.x) * i) / steps, from.y + ((to.y - from.y) * i) / steps) });
    await sleep(16);
  }
  await sleep(endHold);
  await page.s("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
}
/** Vuốt LÊN `dist` px bằng chuỗi sự kiện chạm thật (như ngón tay): cuộn trang xuống. */
export async function swipeUp(page, from, dist) {
  const pt = (x, y) => [{ x, y, id: 1 }];
  await page.s("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: pt(from.x, from.y) });
  for (let i = 1; i <= 16; i += 1) {
    await page.s("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: pt(from.x, from.y - (dist * i) / 16) });
    await sleep(14);
  }
  await page.s("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
}
export const centerOf = (r) => ({ x: r.l + r.w / 2, y: r.t + r.h / 2 });

// ----------------------------------------------------------------------------------------- CPU / bộ nhớ
export async function cpuNow(cdp) {
  const { processInfo } = await cdp.send("SystemInfo.getProcessInfo");
  return { t: Date.now(), total: processInfo.reduce((s, p) => s + p.cpuTime, 0), by: Object.fromEntries(processInfo.map((p) => [p.type + ":" + p.id, p.cpuTime])) };
}
export const metric = async (page, name) => (await page.s("Performance.getMetrics")).metrics.find((m) => m.name === name)?.value ?? 0;
/**
 * Một cửa sổ đo `ms`: `cpuPct` = % CPU TỔNG mọi tiến trình Chrome (trình duyệt + GPU + renderer; 1 nhân = 100%), `mainPct` = % thời gian
 * luồng chính của TRANG bận (TaskDuration — không bị nhiễu bởi tiến trình trình duyệt/GPU khởi động), `rafPerSec` = số khung RAF/giây.
 */
export async function sampleOnce(page, cdp, ms) {
  const a = await cpuNow(cdp);
  const t0 = await metric(page, "TaskDuration");
  const r0 = await page.ev(`window.__perf ? window.__perf.raf : -1`);
  await sleep(ms);
  const b = await cpuNow(cdp);
  const t1 = await metric(page, "TaskDuration");
  const r1 = await page.ev(`window.__perf ? window.__perf.raf : -1`);
  const wall = (b.t - a.t) / 1000;
  return { cpuPct: ((b.total - a.total) / wall) * 100, mainPct: ((t1 - t0) / wall) * 100, rafPerSec: r0 < 0 ? null : (r1 - r0) / wall, wall };
}
/** TRUNG VỊ của `n` cửa sổ (chống nhiễu nền của Chrome và sai số lấy mẫu `cpuTime` của tiến trình — có lúc ra số âm). */
export async function sampleCpu(page, cdp, ms, n = 3) {
  const per = Math.max(700, Math.round(ms / n));
  const all = [];
  for (let i = 0; i < n; i += 1) all.push(await sampleOnce(page, cdp, per));
  const med = (k) => all.map((s) => s[k]).sort((a, b) => a - b)[Math.floor(all.length / 2)];
  return { cpuPct: Math.max(0, med("cpuPct")), mainPct: med("mainPct"), rafPerSec: med("rafPerSec"), all: all.map((s) => `${s.cpuPct.toFixed(0)}/${s.mainPct.toFixed(1)}`).join(" ") };
}
export const fmtCpu = (s) => `tiến trình ${s.cpuPct.toFixed(1)}% · luồng chính ${s.mainPct.toFixed(1)}% · ${s.rafPerSec?.toFixed(1)} RAF/s [các cửa sổ: ${s.all}]`;
export async function counters(page) {
  await page.s("HeapProfiler.collectGarbage");
  await sleep(150);
  const d = await page.s("Memory.getDOMCounters");
  const h = await page.s("Runtime.getHeapUsage");
  const p = await page.ev(`window.__perf ? { pending: window.__perf.pending.size, intervals: window.__perf.intervals.size } : null`);
  return { nodes: d.nodes, listeners: d.jsEventListeners, docs: d.documents, heap: h.usedSize, ...(p ?? {}) };
}

