/**
 * QA giao diện Trợ lý AI bằng Chrome headless THẬT (CDP) trên harness (`harness/`): đo bố cục ở nhiều cỡ màn hình và chạy
 * các luồng người dùng (gửi, dừng, tạo lại, hết lượt, đổi tài khoản, focus, giảm chuyển động…) với máy chủ giả.
 *
 *   node scripts/qa/ai_ui/run.mjs [--only <regex>] [--shots <thư mục>] [--json <tệp>]
 *
 * Chrome chạy với --user-data-dir tạm RIÊNG (không đụng cửa sổ Chrome của người dùng), mỗi viewport một browser context mới.
 * Mã thoát 1 nếu có kiểm tra FAIL. Mức "INFO" chỉ để báo số đo, không làm hỏng lần chạy.
 */
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { buildHarness } from "./build.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const opt = (name) => (args.includes(name) ? args[args.indexOf(name) + 1] : null);
const ONLY = opt("--only") ? new RegExp(opt("--only")) : null;
const SHOTS = opt("--shots");
const JSON_OUT = opt("--json");
const CHROME = process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";

const results = [];
function record(id, vp, status, detail = "") {
  results.push({ id, vp, status, detail });
  const tag = status === "PASS" ? "  ok  " : status === "FAIL" ? " FAIL " : " info ";
  console.log(`${tag} ${vp.padEnd(10)} ${id}${detail ? "  — " + detail : ""}`);
}
const check = (id, vp, cond, detail = "") => record(id, vp, cond ? "PASS" : "FAIL", cond ? "" : detail);
const info = (id, vp, detail) => record(id, vp, "INFO", detail);

// ----------------------------------------------------------------------------------------- hạ tầng: máy chủ tĩnh + Chrome + CDP
function serve(dir) {
  const types = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css" };
  const server = http.createServer((req, res) => {
    const p = decodeURIComponent(new URL(req.url, "http://x").pathname);
    const file = path.join(dir, p === "/" ? "index.html" : p);
    if (!file.startsWith(dir) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404).end();
      return;
    }
    res.writeHead(200, { "Content-Type": types[path.extname(file)] ?? "application/octet-stream", "Cache-Control": "no-store" });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve({ server, port: server.address().port })));
}

async function launchChrome() {
  const userDir = fs.mkdtempSync(path.join(os.tmpdir(), "ai-ui-qa-"));
  const proc = spawn(CHROME, [
    "--headless=new", "--remote-debugging-port=0", `--user-data-dir=${userDir}`, "--no-first-run",
    "--no-default-browser-check", "--disable-gpu", "--disable-features=CalculateNativeWinOcclusion,Translate",
    "--disable-background-timer-throttling", "--disable-renderer-backgrounding", "--mute-audio",
    "--enable-precise-memory-info", "about:blank",
  ], { stdio: "ignore" });
  const portFile = path.join(userDir, "DevToolsActivePort");
  for (let i = 0; i < 150 && !fs.existsSync(portFile); i += 1) await new Promise((r) => setTimeout(r, 100));
  if (!fs.existsSync(portFile)) throw new Error("Chrome không mở cổng DevTools");
  const [port, wsPath] = fs.readFileSync(portFile, "utf8").trim().split("\n");
  return { proc, userDir, wsUrl: `ws://127.0.0.1:${port}${wsPath}` };
}

class Cdp {
  constructor(ws) {
    this.ws = ws;
    this.id = 0;
    this.pending = new Map();
    this.handlers = [];
    ws.addEventListener("message", (m) => {
      const msg = JSON.parse(m.data);
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.error) reject(new Error(`${msg.error.message} (${JSON.stringify(msg.error.data ?? "")})`));
        else resolve(msg.result);
      } else if (msg.method) {
        for (const h of this.handlers) h(msg);
      }
    });
  }
  static async connect(url) {
    const ws = new WebSocket(url);
    await new Promise((res, rej) => {
      ws.addEventListener("open", res);
      ws.addEventListener("error", rej);
    });
    return new Cdp(ws);
  }
  send(method, params = {}, sessionId) {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
    });
  }
  on(h) {
    this.handlers.push(h);
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

class Page {
  constructor(cdp, sessionId, targetId, ctxId) {
    this.cdp = cdp;
    this.sid = sessionId;
    this.targetId = targetId;
    this.ctxId = ctxId;
    this.errors = [];
    cdp.on((m) => {
      if (m.sessionId !== sessionId) return;
      if (m.method === "Runtime.exceptionThrown") this.errors.push(m.params.exceptionDetails?.exception?.description ?? m.params.exceptionDetails?.text);
      if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error") {
        this.errors.push(m.params.args.map((a) => a.value ?? a.description ?? "").join(" "));
      }
    });
  }
  s(method, params) {
    return this.cdp.send(method, params, this.sid);
  }
  async ev(expression) {
    const r = await this.s("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
    return r.result.value;
  }
  async wait(expression, timeout = 6000, label = expression) {
    const end = Date.now() + timeout;
    while (Date.now() < end) {
      if (await this.ev(`!!(${expression})`)) return true;
      await sleep(40);
    }
    throw new Error(`hết giờ chờ: ${label}`);
  }
  async click(selector) {
    await this.ev(`(() => { const el = [...document.querySelectorAll(${JSON.stringify(selector)})].find((e) => e.getBoundingClientRect().width > 0); if (!el) throw new Error(${JSON.stringify("không thấy " + selector)}); el.click(); })()`);
  }
  async focus(selector) {
    await this.ev(`document.querySelector(${JSON.stringify(selector)}).focus()`);
  }
  async type(text) {
    await this.s("Input.insertText", { text });
  }
  async key(key, { shift = false } = {}) {
    const code = key === "Enter" ? 13 : key === "Escape" ? 27 : 0;
    const base = { key, code: key, windowsVirtualKeyCode: code, modifiers: shift ? 8 : 0 };
    await this.s("Input.dispatchKeyEvent", { type: "keyDown", ...base, ...(key === "Enter" ? { text: "\r" } : {}) });
    await this.s("Input.dispatchKeyEvent", { type: "keyUp", ...base });
  }
  async shot(name) {
    if (!SHOTS) return;
    fs.mkdirSync(SHOTS, { recursive: true });
    const { data } = await this.s("Page.captureScreenshot", { format: "png" });
    fs.writeFileSync(path.join(SHOTS, `${name}.png`), Buffer.from(data, "base64"));
  }
  async close() {
    await this.cdp.send("Target.closeTarget", { targetId: this.targetId }).catch(() => {});
    await this.cdp.send("Target.disposeBrowserContext", { browserContextId: this.ctxId }).catch(() => {});
  }
}

async function openPage(cdp, base, { width, height, mobile, hash, reducedMotion = false }) {
  const { browserContextId } = await cdp.send("Target.createBrowserContext");
  const { targetId } = await cdp.send("Target.createTarget", { url: "about:blank", browserContextId });
  const { sessionId } = await cdp.send("Target.attachToTarget", { targetId, flatten: true });
  const p = new Page(cdp, sessionId, targetId, browserContextId);
  await p.s("Page.enable");
  await p.s("Runtime.enable");
  await p.s("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: mobile ? 2 : 1, mobile });
  await p.s("Emulation.setTouchEmulationEnabled", { enabled: mobile, maxTouchPoints: mobile ? 5 : 1 });
  if (reducedMotion) await p.s("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
  await p.s("Page.navigate", { url: `${base}/index.html#${hash}` });
  try {
    await p.wait("window.__qa && document.readyState === 'complete'", 10000, "tải harness");
  } catch (e) {
    throw new Error(`${e.message}; lỗi trang: ${p.errors.slice(0, 3).join(" | ") || "(không có)"}; url=${await p.ev("location.href").catch(() => "?")}`);
  }
  return p;
}

// ----------------------------------------------------------------------------------------- dữ liệu thử
const LONG_WORD = "Siêuthanhlịchsửvĩđạiphithườngkhôngthểchiara".repeat(4);
const URL_LONG = "https://example.com/rất/dài/" + "a".repeat(140);
const MD_BODY = [
  "**Tiêu đề đậm** và `mã_nội_tuyến_rất_dài_không_có_khoảng_trắng_nào_cả_" + "x".repeat(70) + "`",
  "- mục một\n- mục hai " + LONG_WORD,
  "1. bước một\n2. bước hai",
  "```js\nconst a = 1; // " + "dòng mã rất dài ".repeat(12) + "\n```",
  URL_LONG,
  "Một đoạn văn thường khá dài để kiểm tra việc xuống dòng tự nhiên của tiếng Việt có dấu trong một khung hẹp 320px.",
].join("\n\n");

const VIEWPORTS = [
  { name: "320", width: 320, height: 568, mobile: true },
  { name: "360", width: 360, height: 740, mobile: true },
  { name: "390", width: 390, height: 844, mobile: true },
  { name: "430", width: 430, height: 932, mobile: true },
  { name: "tablet", width: 768, height: 1024, mobile: true },
  { name: "desktop", width: 1280, height: 800, mobile: false },
  { name: "1024", width: 1024, height: 768, mobile: false },
];
const isPageView = (vp) => vp.width < 1024;

// ----------------------------------------------------------------------------------------- đo bố cục (chạy trong trang)
const MEASURE = `(() => {
  const root = document.querySelector('.ai-trang, .ai-panel');
  const vw = innerWidth, vh = innerHeight;
  const out = { vw, vh, docScrollW: document.documentElement.scrollWidth, hasRoot: !!root, overflow: [], controls: [] };
  if (!root) return out;
  const vis = (el) => { const cs = getComputedStyle(el); if (cs.display === 'none' || cs.visibility === 'hidden') return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const name = (el) => (el.getAttribute('aria-label') || (el.className && el.className.toString().split(' ')[0]) || el.tagName).slice(0, 36);
  for (const el of root.querySelectorAll('*')) {
    if (!vis(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.right > vw + 1 || r.left < -1) out.overflow.push(name(el) + ' [' + Math.round(r.left) + '..' + Math.round(r.right) + ']');
  }
  // Vùng chạm HIỆU DỤNG: kích thước phần tử + phần ::after mở rộng (inset âm), hoặc cả <label> bao ô tích.
  const eff = (el, r) => {
    let w = r.width, h = r.height;
    const a = getComputedStyle(el, '::after');
    if (a && a.content !== 'none' && a.position === 'absolute') {
      const l = parseFloat(a.left), rr = parseFloat(a.right), t = parseFloat(a.top), b = parseFloat(a.bottom);
      if (![l, rr, t, b].some(Number.isNaN)) { w = w - l - rr; h = h - t - b; }
    }
    if (el.matches('input[type=checkbox],input[type=radio]')) { const lab = el.closest('label'); if (lab) { const lr = lab.getBoundingClientRect(); w = Math.max(w, lr.width); h = Math.max(h, lr.height); } }
    return [Math.round(w), Math.round(h)];
  };
  for (const el of root.querySelectorAll('button, select, textarea, input, a[href], [role=menuitem]')) {
    if (!vis(el)) continue;
    const r = el.getBoundingClientRect();
    const [ew, eh] = eff(el, r);
    out.controls.push({ name: name(el), w: ew, h: eh, inView: r.left >= -1 && r.right <= vw + 1 && r.top >= -1 && r.bottom <= vh + 1 });
  }
  const ta = root.querySelector('textarea.ai-o');
  if (ta) { const cs = getComputedStyle(ta); out.textareaFont = parseFloat(cs.fontSize); const r = ta.getBoundingClientRect(); out.composer = { top: Math.round(r.top), bottom: Math.round(r.bottom), inView: r.top >= 0 && r.bottom <= vh + 1 }; }
  const sel = root.querySelector('select.ai-mode'); if (sel) out.selectFont = parseFloat(getComputedStyle(sel).fontSize);
  const list = root.querySelector('.ai-panel-tin'); if (list) out.list = { client: list.clientHeight, scroll: list.scrollHeight, top: Math.round(list.getBoundingClientRect().top) };
  return out;
})()`;

async function measure(page, vp, label, { strictTouch = false } = {}) {
  const m = await page.ev(MEASURE);
  check(`${label}: có khung AI`, vp.name, m.hasRoot, "không thấy .ai-trang/.ai-panel");
  if (!m.hasRoot) return m;
  check(`${label}: không tràn ngang (trang)`, vp.name, m.docScrollW <= m.vw, `scrollWidth=${m.docScrollW} > ${m.vw}`);
  check(`${label}: không phần tử nào vượt khung nhìn`, vp.name, m.overflow.length === 0, m.overflow.slice(0, 5).join("; "));
  const outside = m.controls.filter((c) => !c.inView);
  check(`${label}: mọi nút/ô nhập nằm trong khung nhìn`, vp.name, outside.length === 0, outside.map((c) => c.name).join(", "));
  if (m.composer) check(`${label}: ô soạn thấy được`, vp.name, m.composer.inView, JSON.stringify(m.composer));
  if (isPageView(vp)) {
    const small = m.controls.filter((c) => Math.min(c.w, c.h) < 44);
    const tiny = m.controls.filter((c) => Math.min(c.w, c.h) < 24);
    check(`${label}: không điều khiển nào nhỏ hơn 24px`, vp.name, tiny.length === 0, tiny.map((c) => `${c.name} ${c.w}x${c.h}`).join(", "));
    if (strictTouch) check(`${label}: điều khiển chạm >= 44px`, vp.name, small.length === 0, small.map((c) => `${c.name} ${c.w}x${c.h}`).join(", "));
    else if (small.length) info(`${label}: điều khiển < 44px`, vp.name, small.map((c) => `${c.name} ${c.w}x${c.h}`).join(", "));
    if (m.textareaFont !== undefined) check(`${label}: ô soạn >= 16px (iOS không tự phóng to)`, vp.name, m.textareaFont >= 16, `font=${m.textareaFont}px`);
    if (m.selectFont !== undefined) check(`${label}: ô chọn chế độ >= 16px`, vp.name, m.selectFont >= 16, `font=${m.selectFont}px`);
  }
  return m;
}

// ----------------------------------------------------------------------------------------- thao tác
async function login(page, user) {
  await page.ev(`__qa.setUser(${JSON.stringify(user)})`);
}
async function openDesktop(page) {
  await page.wait("document.querySelector('.ai-launcher')", 8000, "nút nổi");
  await page.click(".ai-launcher");
  await page.wait("document.querySelector('.ai-panel')", 4000, "panel");
}
async function ready(page, vp, user = "alice") {
  await login(page, user);
  if (isPageView(vp)) await page.wait("document.querySelector('.ai-trang textarea.ai-o')", 8000, "ô soạn");
  else {
    await openDesktop(page);
    await page.wait("document.querySelector('.ai-panel textarea.ai-o')", 8000, "ô soạn");
  }
}
async function send(page, text, { script, wait = "done" } = {}) {
  if (script) await page.ev(`__qa.script.push(${JSON.stringify(script)})`);
  const before = await page.ev(`__qa.count('/messages')`);
  await page.focus("textarea.ai-o");
  await page.type(text);
  await page.key("Enter");
  if (wait === "done") {
    await page.wait(`__qa.count('/messages') > ${before} && !document.querySelector('.ai-nut-dung')`, 15000, "xong lượt gửi");
    await sleep(60);
  }
}

// ----------------------------------------------------------------------------------------- các kịch bản
const SCENARIOS = [];
const scenario = (id, fn, { viewports = VIEWPORTS, reducedMotion = false } = {}) => SCENARIOS.push({ id, fn, viewports, reducedMotion });

scenario("layout", async (page, vp) => {
  await ready(page, vp);
  await page.wait("document.querySelector('.ai-trong')", 5000, "trạng thái rỗng");
  await measure(page, vp, "rỗng");
  await page.shot(`${vp.name}-01-empty`);

  await send(page, "Xin chào " + LONG_WORD + " " + URL_LONG, { script: { kind: "text", text: MD_BODY, chunk: 40, delay: 5 } });
  await measure(page, vp, "hội thoại dài (từ/URL/mã dài)");
  await page.shot(`${vp.name}-02-convo`);

  // hết lượt: dùng hết 5 lượt rồi xem khung báo
  await page.ev(`__qa.setUsed('alice', 4)`);
  await send(page, "lượt cuối", { script: { kind: "ok", words: 8, delay: 5 } });
  await page.wait("document.querySelector('textarea.ai-o').disabled", 4000, "ô soạn bị khoá khi hết lượt");
  await measure(page, vp, "hết lượt");
  await page.shot(`${vp.name}-03-exhausted`);
});

scenario("layout-states", async (page, vp) => {
  await ready(page, vp, "carol");
  const longTitle = "Một cuộc trò chuyện có tiêu đề rất rất dài " + LONG_WORD;
  await page.ev(`__qa.seed('carol', { title: ${JSON.stringify(longTitle)}, messages: [{ role: 'user', content: 'a' }, { role: 'assistant', content: 'b' }] })`);
  for (let i = 0; i < 6; i += 1) await page.ev(`__qa.seed('carol', { title: 'Hội thoại số ${i + 1}', messages: [] })`);
  await page.click("button[aria-label='Lịch sử hội thoại']");
  await page.wait("document.querySelector('.ai-lichsu')", 4000, "danh sách lịch sử");
  await sleep(150);
  await measure(page, vp, "lịch sử mở (tiêu đề dài)");
  await page.shot(`${vp.name}-04-history`);
  await page.click("button[aria-label='Lịch sử hội thoại']");

  await page.click("button[aria-label='Cài đặt ký ức']");
  await page.wait("document.querySelector('.ai-caidat')", 3000, "popover cài đặt");
  await measure(page, vp, "popover cài đặt");
  await page.shot(`${vp.name}-05-settings`);
  await page.click("button[aria-label='Cài đặt ký ức']");

  // lỗi: bị từ chối trước khi nhận => "Chưa gửi" + khung báo
  await send(page, "tin bị từ chối " + LONG_WORD, { script: { kind: "http", status: 503, body: { detail: { code: "ai_busy", message: "Máy chủ đang bận — vui lòng thử lại sau ít giây." } } } });
  await page.wait("document.querySelector('.ai-loi')", 4000, "khung báo lỗi");
  await measure(page, vp, "lỗi + 'Chưa gửi'");
  check("tin bị từ chối hiện 'Chưa gửi'", vp.name, await page.ev(`!!document.querySelector('.ai-bong-chua-gui-nhan')`));
  await page.shot(`${vp.name}-06-notsent`);

  // chế độ viết
  await page.ev(`(() => { const s = document.querySelector('select.ai-mode'); if (s && !s.disabled) { const set = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set; set.call(s, 'writer'); s.dispatchEvent(new Event('change', { bubbles: true })); } })()`);
  await sleep(150);
  await measure(page, vp, "chế độ viết");
  await page.shot(`${vp.name}-07-writer`);
});

scenario("behaviour-send-stop-regenerate", async (page, vp) => {
  await ready(page, vp, "dave");
  const calls0 = await page.ev(`__qa.count('/messages')`);
  await page.focus("textarea.ai-o");
  await page.key("Enter");
  await page.type("   ");
  await page.key("Enter");
  check("Enter với ô trống/khoảng trắng không gửi", vp.name, (await page.ev(`__qa.count('/messages')`)) === calls0);
  await page.ev(`(() => { const ta = document.querySelector('textarea.ai-o'); Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(ta, ''); ta.dispatchEvent(new Event('input', { bubbles: true })); ta.focus(); })()`);

  await page.type("dòng một");
  await page.key("Enter", { shift: true });
  await page.type("dòng hai");
  const draft = await page.ev(`document.querySelector('textarea.ai-o').value`);
  check("Shift+Enter xuống dòng, không gửi", vp.name, draft === "dòng một\ndòng hai" && (await page.ev(`__qa.count('/messages')`)) === calls0, JSON.stringify(draft));

  // IME: Enter khi đang gõ dấu (isComposing) KHÔNG được gửi
  await page.ev(`(() => { const ta = document.querySelector('textarea.ai-o'); ta.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true, isComposing: true })); })()`);
  await sleep(80);
  check("Enter trong lúc IME đang soạn (isComposing) không gửi", vp.name, (await page.ev(`__qa.count('/messages')`)) === calls0, "tin bị gửi giữa chừng khi đang gõ dấu");

  await page.key("Enter");
  await page.wait(`__qa.count('/messages') > ${calls0} && !document.querySelector('.ai-nut-dung')`, 12000, "gửi xong");
  check("gửi bằng Enter: ô soạn được xoá", vp.name, (await page.ev(`document.querySelector('textarea.ai-o').value`)) === "");
  const bubbles = await page.ev(`[...document.querySelectorAll('.ai-bong')].map((b) => b.className.includes('ai-bong-user') ? 'U' : 'A').join('')`);
  check("đúng một lượt user + một trả lời", vp.name, bubbles === "UA", bubbles);

  // Tạo lại
  await page.click(".ai-nut-tao-lai");
  await page.wait(`!document.querySelector('.ai-nut-dung') && document.querySelector('.ai-nut-tao-lai')`, 12000, "tạo lại xong");
  const assistants = await page.ev(`document.querySelectorAll('.ai-bong-assistant').length`);
  check("Tạo lại thay câu trả lời cũ (chỉ còn 1 bong bóng trợ lý)", vp.name, assistants === 1, `assistants=${assistants}`);

  // Dừng giữa chừng
  await page.ev(`__qa.script.push({ kind: 'ok', words: 400, delay: 30 })`);
  await page.focus("textarea.ai-o");
  await page.type("trả lời thật dài");
  await page.key("Enter");
  await page.wait("document.querySelector('.ai-nut-dung')", 4000, "nút Dừng");
  await page.wait("document.querySelectorAll('.ai-bong-assistant').length >= 1 && document.body.innerText.includes('xin chào')", 6000, "đã có chữ");
  await page.shot(`${vp.name}-08-streaming`);
  await page.click(".ai-nut-dung");
  await page.wait("!document.querySelector('.ai-nut-dung')", 4000, "dừng xong");
  check("Dừng: hiện 'Đã dừng' và ô soạn dùng lại được", vp.name, (await page.ev(`document.body.innerText.includes('Đã dừng')`)) && !(await page.ev(`document.querySelector('textarea.ai-o').disabled`)));
  const stillHasSend = await page.ev(`!!document.querySelector('.ai-nut-gui')`);
  check("Dừng: nút Gửi quay lại", vp.name, stillHasSend);
});

scenario("behaviour-quota-and-errors", async (page, vp) => {
  await ready(page, vp, "erin");
  // máy chủ từ chối (429 user) dù giao diện chưa biết: "Chưa gửi" + khung báo + KHÔNG có % toàn cục
  await page.ev(`__qa.setUsed('erin', 5)`);
  await send(page, "gửi khi đã hết", { wait: "none" });
  await page.wait("document.querySelector('.ai-loi')", 6000, "khung báo hết lượt");
  const banner = await page.ev(`document.querySelector('.ai-loi').innerText`);
  check("báo hết lượt của CHÍNH người dùng, kèm giờ làm mới", vp.name, /hết lượt/i.test(banner) && /làm mới|lúc/i.test(banner), banner);
  check("không có phần trăm/dung lượng toàn site trong giao diện", vp.name, !/\d+\s?%/.test(await page.ev(`document.querySelector('.ai-trang, .ai-panel').innerText`)));
  check("tin hiện 'Chưa gửi' (không trông như đã gửi)", vp.name, await page.ev(`!!document.querySelector('.ai-bong-chua-gui-nhan')`));
  check("ô soạn bị khoá, không còn mời 'Tạo lại'", vp.name, (await page.ev(`document.querySelector('textarea.ai-o').disabled`)) && !(await page.ev(`!!document.querySelector('.ai-nut-tao-lai')`)));

  // hết công suất chung (scope global) giữa chừng: nói rõ không phải lỗi của người dùng
  await page.ev(`__qa.setUsed('erin', 0)`);
  await page.click("button[aria-label='Hội thoại mới']");
  await sleep(200);
  await login(page, "frank");
  if (!isPageView(vp)) await openDesktop(page); // người mới đăng nhập: panel nổi bắt đầu ở trạng thái đóng
  await page.wait("document.querySelector('textarea.ai-o')", 5000, "ô soạn của frank");
  await send(page, "hỏi", { script: { kind: "sse_error", code: "ai_budget_exhausted", scope: "global" } });
  await page.wait("document.querySelector('.ai-loi')", 5000, "khung báo global");
  const g = await page.ev(`document.querySelector('.ai-loi').innerText`);
  check("hết công suất chung: không đổ lỗi cho người dùng", vp.name, /không phải|công suất|hệ thống|chung/i.test(g), g);
  await send(page, "hỏi nữa", { script: { kind: "sse_error", code: "ai_busy" } });
  const b = await page.ev(`document.querySelector('.ai-loi')?.innerText ?? ''`);
  check("ai_busy hiện 'đang bận'", vp.name, /bận/i.test(b), b);
});

scenario("behaviour-double-submit", async (page, vp) => {
  await ready(page, vp, "lan");
  // Hai lần Enter CÙNG MỘT nhịp (trước khi React kịp vẽ lại `streaming: true`): chỉ một request được gửi đi.
  const before = await page.ev(`__qa.count('/messages')`);
  await page.focus("textarea.ai-o");
  await page.type("gửi hai lần");
  await page.ev(`(() => { const ta = document.querySelector('textarea.ai-o'); for (let i = 0; i < 2; i += 1) ta.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true })); })()`);
  await page.wait(`__qa.count('/messages') > ${before} && !document.querySelector('.ai-nut-dung')`, 12000, "xong lượt gửi");
  await sleep(300);
  check("Enter hai lần cùng nhịp chỉ gửi MỘT lần", vp.name, (await page.ev(`__qa.count('/messages')`)) === before + 1, `requests=${(await page.ev(`__qa.count('/messages')`)) - before}`);
  const users = await page.ev(`document.querySelectorAll('.ai-bong-user').length`);
  check("không có bong bóng người dùng bị nhân đôi", vp.name, users === 1, `users=${users}`);
  // Hai lần bấm nút Gửi cùng nhịp.
  const b2 = await page.ev(`__qa.count('/messages')`);
  await page.focus("textarea.ai-o");
  await page.type("bấm hai lần");
  await page.ev(`(() => { const f = document.querySelector('form.ai-panel-soan'); const btn = f.querySelector('button[type=submit]'); btn.click(); btn.click(); })()`);
  await page.wait(`__qa.count('/messages') > ${b2} && !document.querySelector('.ai-nut-dung')`, 12000, "xong lượt thứ hai");
  await sleep(300);
  check("bấm Gửi hai lần cùng nhịp chỉ gửi MỘT lần", vp.name, (await page.ev(`__qa.count('/messages')`)) === b2 + 1, `requests=${(await page.ev(`__qa.count('/messages')`)) - b2}`);
}, { viewports: VIEWPORTS.filter((v) => ["390", "desktop"].includes(v.name)) });

scenario("behaviour-resilience", async (page, vp) => {
  // Gieo trước khi đăng nhập: danh sách lịch sử được nạp một lần lúc mở panel.
  await page.ev(`__qa.seed('kim', { title: 'Cuộc trò chuyện cũ', messages: [{ role: 'user', content: 'câu hỏi cũ' }, { role: 'assistant', content: 'trả lời cũ' }] })`);
  await ready(page, vp, "kim");
  // Luồng đóng SẠCH giữa chừng (không done/error): giao diện KHÔNG được kẹt ở "đang trả lời".
  await send(page, "hỏi rồi bị cắt", { script: { kind: "eof", partial: "một phần câu trả lời " }, wait: "none" });
  await page.wait("!document.querySelector('.ai-nut-dung') && document.body.innerText.includes('một phần câu trả lời')", 6000, "thoát khỏi trạng thái streaming");
  check("EOF giữa chừng: ô soạn dùng lại được, nút Gửi quay lại", vp.name, !(await page.ev(`document.querySelector('textarea.ai-o').disabled`)) && !!(await page.ev(`!!document.querySelector('.ai-nut-gui')`)));
  check("EOF giữa chừng: báo 'bị ngắt giữa chừng' + giữ phần đã nhận", vp.name, /ngắt giữa chừng/i.test(await page.ev(`document.querySelector('.ai-loi')?.innerText ?? ''`)));
  // "Tạo lại" sau khi mở một hội thoại cũ từ lịch sử (chưa gửi lượt nào trong phiên này) phải thật sự gửi.
  await page.click("button[aria-label='Lịch sử hội thoại']");
  await page.wait("document.querySelector('.ai-lichsu')", 4000, "lịch sử");
  await page.ev(`[...document.querySelectorAll('.ai-lichsu-mo')].find((b) => b.innerText.includes('Cuộc trò chuyện cũ')).click()`);
  await page.wait("document.body.innerText.includes('trả lời cũ')", 4000, "mở hội thoại cũ");
  const before = await page.ev(`__qa.count('/messages')`);
  await page.click(".ai-nut-tao-lai");
  await sleep(800);
  check("'Tạo lại' trên hội thoại vừa mở từ lịch sử gửi lại câu hỏi cũ", vp.name, (await page.ev(`__qa.count('/messages')`)) === before + 1, "bấm Tạo lại mà không có request nào");
  // Chống hồi quy (reviewer): trước đó trong PHIÊN này đã gửi "hỏi rồi bị cắt" ở một hội thoại KHÁC. "Tạo lại" ở hội thoại cũ
  // phải gửi câu hỏi CỦA hội thoại cũ vào ĐÚNG hội thoại cũ, không phải câu hỏi của hội thoại kia.
  const gui = await page.ev(`({ content: __qa.lastContent, conv: __qa.lastConv })`);
  check("'Tạo lại' gửi câu hỏi của hội thoại đang xem vào đúng hội thoại đó", vp.name, gui.content === "câu hỏi cũ" && String(gui.conv).startsWith("s"), JSON.stringify(gui));
});

scenario("behaviour-account-switch", async (page, vp) => {
  await ready(page, vp, "alice2");
  await send(page, "BÍ MẬT CỦA ALICE");
  await page.wait("document.body.innerText.includes('BÍ MẬT CỦA ALICE')", 3000, "tin của alice hiện");
  const aliceConv = await page.ev(`sessionStorage.getItem('fas.ai.conv')`);
  const callsBefore = await page.ev(`__qa.calls.length`);
  await login(page, "bob2");
  await sleep(700);
  if (!isPageView(vp)) {
    // panel nổi: bob có thể phải mở lại
    const open = await page.ev(`!!document.querySelector('.ai-panel')`);
    if (!open) await openDesktop(page).catch(() => {});
    await sleep(500);
  }
  const text = await page.ev(`document.body.innerText`);
  check("đổi tài khoản: không còn nội dung của người trước trên màn hình", vp.name, !text.includes("BÍ MẬT CỦA ALICE"), "nội dung của alice vẫn hiện cho bob");
  const bobCalls = await page.ev(`__qa.calls.slice(${callsBefore}).filter((c) => c.user === 'alice2').length`);
  check("sau khi đổi tài khoản không còn request nào mang token của người trước", vp.name, bobCalls === 0, `alice2 calls=${bobCalls}`);
  const forbidden = await page.ev(`__qa.calls.slice(${callsBefore}).filter((c) => c.user === 'bob2' && c.path.includes(${JSON.stringify(aliceConv ?? "zzz")})).length`);
  check("bob không cố mở hội thoại của alice (cờ phiên không bị thừa kế)", vp.name, forbidden === 0, `bob requested alice's conversation ${forbidden}x`);
  const errShown = await page.ev(`!!document.querySelector('.ai-loi')`);
  check("bob không thấy khung lỗi 'không thuộc về bạn'", vp.name, !errShown, await page.ev(`document.querySelector('.ai-loi')?.innerText ?? ''`));
  const quotaBob = await page.ev(`document.querySelector('.ai-usage')?.innerText ?? ''`);
  check("hạn mức hiển thị là của bob (chưa dùng), không phải của alice", vp.name, !quotaBob || /5\/5|còn 5/.test(quotaBob), quotaBob);
  // đăng xuất: không còn gì
  await login(page, null);
  await sleep(300);
  const after = await page.ev(`document.body.innerText`);
  check("đăng xuất: nội dung hội thoại biến mất", vp.name, !after.includes("BÍ MẬT CỦA ALICE") && !after.includes("xin chào"));
});

scenario("behaviour-focus", async (page, vp) => {
  await ready(page, vp, "gina");
  const inside = await page.ev(`!!document.activeElement && !!document.activeElement.closest('.ai-panel')`);
  check("mở panel: focus chuyển vào panel (ô soạn)", vp.name, inside, `activeElement=${await page.ev("document.activeElement?.tagName + '.' + document.activeElement?.className")}`);
  await page.click("button[aria-label='Đóng trợ lý AI']");
  await page.wait("!document.querySelector('.ai-panel')", 3000, "panel đóng");
  await sleep(100);
  const onLauncher = await page.ev(`document.activeElement?.classList?.contains('ai-launcher')`);
  check("đóng panel: focus trả về nút mở", vp.name, onLauncher, `activeElement=${await page.ev("document.activeElement?.tagName + '.' + document.activeElement?.className")}`);
}, { viewports: VIEWPORTS.filter((v) => !isPageView(v)) });

scenario("behaviour-scroll-follow", async (page, vp) => {
  // Hai điều mà bài kiểm "cuộn lên thì không bị giật xuống" KHÔNG phủ (reviewer): vẫn bám đáy khi người dùng không cuộn,
  // và mở một hội thoại dài từ lịch sử thì nhảy xuống đáy; cộng với khung cao lên giữa chừng thì không mất bám đáy.
  const msgs = Array.from({ length: 30 }, (_, i) => ({ role: i % 2 ? "assistant" : "user", content: `tin số ${i + 1} ` + "nội dung dài ".repeat(12) }));
  await page.ev(`__qa.seed('mai', { title: 'Hội thoại rất dài', messages: ${JSON.stringify(msgs)} })`);
  await ready(page, vp, "mai");
  const gan = `(() => { const el = document.querySelector('.ai-panel-tin'); return el.scrollHeight - el.scrollTop - el.clientHeight; })()`;
  await page.click("button[aria-label='Lịch sử hội thoại']");
  await page.wait("document.querySelector('.ai-lichsu')", 4000, "lịch sử");
  await page.ev(`[...document.querySelectorAll('.ai-lichsu-mo')].find((b) => b.innerText.includes('Hội thoại rất dài')).click()`);
  await page.wait("document.body.innerText.includes('tin số 30')", 4000, "mở hội thoại dài");
  await sleep(200);
  const khoang = await page.ev(gan);
  check("mở hội thoại dài từ lịch sử: nhảy xuống đáy", vp.name, khoang < 80, `còn cách đáy ${khoang}px`);
  await page.ev(`__qa.script.push({ kind: 'ok', words: 300, delay: 10 })`);
  await page.focus("textarea.ai-o");
  await page.type("viết dài đi");
  await page.key("Enter");
  await page.wait("document.querySelector('.ai-nut-dung')", 4000, "bắt đầu stream");
  await sleep(500);
  // Khung cao lên giữa chừng (như xoay màn hình): việc bám đáy KHÔNG được tắt.
  await page.s("Emulation.setDeviceMetricsOverride", { width: vp.width, height: vp.height + 120, deviceScaleFactor: vp.mobile ? 2 : 1, mobile: vp.mobile });
  await page.wait("!document.querySelector('.ai-nut-dung')", 20000, "stream xong");
  await sleep(150);
  const sau = await page.ev(gan);
  check("không cuộn gì + khung cao lên giữa chừng: vẫn ở đáy khi stream xong", vp.name, sau < 80, `còn cách đáy ${sau}px`);
}, { viewports: VIEWPORTS.filter((v) => ["390", "desktop"].includes(v.name)) });

scenario("behaviour-scroll-anchor", async (page, vp) => {
  await ready(page, vp, "hana");
  await page.ev(`__qa.script.push({ kind: 'ok', words: 500, delay: 12 })`);
  await page.focus("textarea.ai-o");
  await page.type("viết dài");
  await page.key("Enter");
  await page.wait("document.querySelector('.ai-panel-tin').scrollHeight > document.querySelector('.ai-panel-tin').clientHeight + 200", 8000, "đủ dài để cuộn");
  await page.ev(`document.querySelector('.ai-panel-tin').scrollTop = 0`);
  await sleep(500);
  const top = await page.ev(`document.querySelector('.ai-panel-tin').scrollTop`);
  check("người dùng cuộn lên đọc trong lúc stream: khung KHÔNG bị giật xuống đáy", vp.name, top < 80, `scrollTop=${top}`);
  await page.wait("!document.querySelector('.ai-nut-dung')", 20000, "stream xong");
}, { viewports: VIEWPORTS.filter((v) => ["390", "desktop"].includes(v.name)) });

scenario("behaviour-reduced-motion", async (page, vp) => {
  await ready(page, vp, "ivy");
  await page.ev(`__qa.script.push({ kind: 'hang' })`);
  await page.focus("textarea.ai-o");
  await page.type("đợi");
  await page.key("Enter");
  await page.wait("document.querySelector('.ai-dang-go')", 4000, "chấm đang gõ");
  // Hoạt ảnh THẬT SỰ chuyển động = thời lượng > 20ms (quy tắc giảm-chuyển-động toàn cục của site rút còn ~0,01ms).
  const anims = await page.ev(`document.getAnimations().filter((a) => a.playState === 'running' && a.effect?.target?.closest?.('.ai-trang, .ai-panel') && a.effect.getComputedTiming().duration > 20).map((a) => (a.animationName || a.transitionProperty || '?') + ':' + a.effect.getComputedTiming().duration)`);
  check("giảm chuyển động: không có hoạt ảnh nào đang chạy trong khung AI", vp.name, anims.length === 0, anims.slice(0, 6).join(", "));
  await page.click(".ai-nut-dung");
  if (!isPageView(vp)) {
    await page.click("button[aria-label='Đóng trợ lý AI']");
    await page.wait("document.querySelector('.ai-launcher')", 3000, "nút mở");
    const tr = await page.ev(`getComputedStyle(document.querySelector('.ai-launcher')).transitionDuration`);
    const worst = Math.max(...tr.split(",").map((x) => parseFloat(x) * (x.includes("ms") ? 0.001 : 1)));
    check("giảm chuyển động: nút mở không có transition đáng kể", vp.name, worst <= 0.02, tr);
  }
}, { viewports: VIEWPORTS.filter((v) => ["390", "desktop"].includes(v.name)), reducedMotion: true });

scenario("perf-idle-and-reopen", async (page, vp) => {
  await login(page, "jack");
  await sleep(600);
  const accessCalls = await page.ev(`__qa.count('/api/ai/access')`);
  check("khi đóng: chỉ 1 request /access, chưa gọi availability/lịch sử", vp.name, accessCalls === 1 && (await page.ev(`__qa.count('/availability')`)) === 0, `access=${accessCalls}`);
  await openDesktop(page);
  await sleep(800);
  const baseCalls = await page.ev(`__qa.calls.length`);
  await sleep(3000);
  check("panel mở nhưng rỗng: không có request nền nào trong 3 giây", vp.name, (await page.ev(`__qa.calls.length`)) === baseCalls, `+${(await page.ev(`__qa.calls.length`)) - baseCalls}`);
  await page.s("HeapProfiler.collectGarbage");
  const m0 = await page.ev(`performance.memory.usedJSHeapSize`);
  const n0 = await page.ev(`document.getElementsByTagName('*').length`);
  for (let i = 0; i < 40; i += 1) {
    await page.click("button[aria-label='Đóng trợ lý AI']");
    await page.wait("document.querySelector('.ai-launcher')", 3000, "nút mở");
    await page.click(".ai-launcher");
    await page.wait("document.querySelector('.ai-panel')", 3000, "panel");
  }
  await sleep(300);
  await page.s("HeapProfiler.collectGarbage");
  const m1 = await page.ev(`performance.memory.usedJSHeapSize`);
  const n1 = await page.ev(`document.getElementsByTagName('*').length`);
  check("mở/đóng 40 lần: số phần tử DOM không tăng", vp.name, n1 <= n0 + 2, `${n0} -> ${n1}`);
  check("mở/đóng 40 lần: heap JS tăng < 2 MB", vp.name, m1 - m0 < 2 * 1024 * 1024, `${((m1 - m0) / 1024).toFixed(0)} KB`);
  // luồng dài: không có long task đáng kể
  await page.ev(`window.__lt = []; new PerformanceObserver((l) => l.getEntries().forEach((e) => window.__lt.push(e.duration))).observe({ entryTypes: ['longtask'] }); __qa.script.push({ kind: 'ok', words: 600, delay: 8 })`);
  await page.focus("textarea.ai-o");
  await page.type("dài");
  await page.key("Enter");
  await page.wait("!document.querySelector('.ai-nut-dung') && document.body.innerText.includes('xin chào')", 20000, "stream dài xong");
  const lt = await page.ev(`window.__lt`);
  info("long task trong stream 600 từ", vp.name, `${lt.length} cái, lớn nhất ${Math.max(0, ...lt).toFixed(0)}ms`);
  check("stream 600 từ: không có long task > 200ms", vp.name, Math.max(0, ...lt) < 200, `${Math.max(0, ...lt).toFixed(0)}ms`);
}, { viewports: VIEWPORTS.filter((v) => v.name === "desktop") });

// ----------------------------------------------------------------------------------------- chạy
async function main() {
  const out = await buildHarness();
  const { server, port } = await serve(out);
  const base = `http://127.0.0.1:${port}`;
  const chrome = await launchChrome();
  let cdp;
  try {
    cdp = await Cdp.connect(chrome.wsUrl);
    for (const sc of SCENARIOS) {
      if (ONLY && !ONLY.test(sc.id)) continue;
      for (const vp of sc.viewports) {
        if (ONLY && ONLY.test(sc.id) === false) continue;
        const page = await openPage(cdp, base, {
          width: vp.width, height: vp.height, mobile: vp.mobile, hash: isPageView(vp) ? "/assistant" : "/", reducedMotion: sc.reducedMotion,
        });
        try {
          await sc.fn(page, vp);
          const errs = page.errors.filter((e) => !/Failed to load resource|favicon|net::ERR/.test(e ?? ""));
          check(`${sc.id}: không có lỗi console`, vp.name, errs.length === 0, errs.slice(0, 2).join(" | "));
        } catch (e) {
          record(`${sc.id}: ngoại lệ trong kịch bản`, vp.name, "FAIL", String(e.message ?? e).slice(0, 300));
          await page.shot(`${vp.name}-${sc.id}-ERROR`).catch(() => {});
        } finally {
          await page.close();
        }
      }
    }
  } finally {
    try { cdp?.ws.close(); } catch { /* bỏ qua */ }
    chrome.proc.kill();
    server.close();
    await sleep(300);
    try { fs.rmSync(chrome.userDir, { recursive: true, force: true }); } catch { /* Chrome còn giữ tệp: bỏ qua */ }
  }
  if (results.length === 0) {
    console.error(ONLY ? `Không kịch bản nào khớp --only ${ONLY}` : "Không chạy được kiểm tra nào");
    process.exit(2);
  }
  const fail = results.filter((r) => r.status === "FAIL");
  console.log(`\n${results.filter((r) => r.status === "PASS").length} PASS, ${fail.length} FAIL, ${results.filter((r) => r.status === "INFO").length} INFO`);
  if (JSON_OUT) fs.writeFileSync(JSON_OUT, JSON.stringify(results, null, 2));
  process.exit(fail.length ? 1 : 0);
}

main().catch((e) => {
  console.error(e);
  process.exit(2);
});
