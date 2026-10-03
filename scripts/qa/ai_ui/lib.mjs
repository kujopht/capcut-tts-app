/**
 * Hạ tầng dùng chung của QA giao diện trợ lý AI bằng Chrome headless (CDP): máy chủ tĩnh, khởi chạy Chrome với hồ sơ tạm riêng,
 * kết nối CDP, trang + đo, ghi kết quả. Tách nguyên văn từ run.mjs (không đổi hành vi) để `run.mjs` (giao diện chat) và
 * `run_companion.mjs` (linh vật Ink Scout) dùng chung.
 */
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const args = process.argv.slice(2);
const opt = (name) => (args.includes(name) ? args[args.indexOf(name) + 1] : null);
export const ONLY = opt("--only") ? new RegExp(opt("--only")) : null;
export const SHOTS = opt("--shots");
export const JSON_OUT = opt("--json");
export const CHROME = process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";

export const results = [];
export function record(id, vp, status, detail = "") {
  results.push({ id, vp, status, detail });
  const tag = status === "PASS" ? "  ok  " : status === "FAIL" ? " FAIL " : " info ";
  console.log(`${tag} ${vp.padEnd(10)} ${id}${detail ? "  — " + detail : ""}`);
}
export const check = (id, vp, cond, detail = "") => record(id, vp, cond ? "PASS" : "FAIL", cond ? "" : detail);
export const info = (id, vp, detail) => record(id, vp, "INFO", detail);

// ----------------------------------------------------------------------------------------- hạ tầng: máy chủ tĩnh + Chrome + CDP
/**
 * Phục vụ `dir` ở gốc. `mounts` = { "/mascot/": "<thư mục>" } phục vụ thêm một cây tĩnh khác dưới tiền tố đó (asset linh vật
 * thật từ `web/public/mascot/`), và ghi lại mọi yêu cầu vào `server.hits` để kiểm "đã tải gì, bao nhiêu byte".
 */
export function serve(dir, mounts = {}) {
  const types = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".json": "application/json",
    ".webp": "image/webp", ".png": "image/png",
  };
  const hits = [];
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, "http://x");
    const p = decodeURIComponent(url.pathname);
    let root = dir;
    let rel = p === "/" ? "index.html" : p;
    for (const [prefix, folder] of Object.entries(mounts)) {
      if (p.startsWith(prefix)) { root = folder; rel = p.slice(prefix.length); break; }
    }
    const file = path.join(root, rel);
    if (!file.startsWith(root) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404).end();
      return;
    }
    const bytes = fs.statSync(file).size;
    hits.push({ path: p, search: url.search, bytes, t: Date.now() });
    res.writeHead(200, { "Content-Type": types[path.extname(file)] ?? "application/octet-stream", "Content-Length": bytes, "Cache-Control": "no-store" });
    fs.createReadStream(file).pipe(res);
  });
  server.hits = hits;
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve({ server, port: server.address().port })));
}

export async function launchChrome() {
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

export class Cdp {
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

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export class Page {
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
    const code = key === "Enter" ? 13 : key === "Escape" ? 27 : key === "Tab" ? 9 : 0;
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

/**
 * Ghi lại MỌI request của trang (`network: true` phải bật TRƯỚC khi điều hướng): url, loại tài nguyên, trạng thái, số byte trên đường
 * truyền (`encodedDataLength`: thân nén + header), thời điểm bắt đầu (ms epoch). `page.net.list()` trả bản sao.
 */
function trackNetwork(page) {
  const reqs = new Map();
  page.cdp.on((m) => {
    if (m.sessionId !== page.sid) return;
    const p = m.params;
    if (m.method === "Network.requestWillBeSent") reqs.set(p.requestId, { url: p.request.url, type: p.type, t: Date.now(), status: 0, bytes: 0, done: false });
    else if (m.method === "Network.responseReceived") {
      const r = reqs.get(p.requestId);
      if (r) { r.status = p.response.status; r.mime = p.response.mimeType; r.fromCache = !!p.response.fromDiskCache; }
    } else if (m.method === "Network.loadingFinished") {
      const r = reqs.get(p.requestId);
      if (r) { r.bytes = p.encodedDataLength; r.done = true; }
    } else if (m.method === "Network.loadingFailed") {
      const r = reqs.get(p.requestId);
      if (r) { r.failed = p.errorText; r.done = true; }
    }
  });
  page.net = { list: () => [...reqs.values()] };
}

export async function openPage(cdp, base, { width, height, mobile, hash, reducedMotion = false, preScript = null, storage = null, url = null, network = false }) {
  const { browserContextId } = await cdp.send("Target.createBrowserContext");
  const { targetId } = await cdp.send("Target.createTarget", { url: "about:blank", browserContextId });
  const { sessionId } = await cdp.send("Target.attachToTarget", { targetId, flatten: true });
  const p = new Page(cdp, sessionId, targetId, browserContextId);
  await p.s("Page.enable");
  await p.s("Runtime.enable");
  if (network) {
    await p.s("Network.enable");
    await p.s("Network.setCacheDisabled", { cacheDisabled: true }); // đo lần tải NGUỘI (không cache) — đúng với khách vào lần đầu
    trackNetwork(p);
  }
  await p.s("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: mobile ? 2 : 1, mobile });
  await p.s("Emulation.setTouchEmulationEnabled", { enabled: mobile, maxTouchPoints: mobile ? 5 : 1 });
  if (reducedMotion) await p.s("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
  // `preScript`: chạy TRƯỚC mã của trang ở mọi lần nạp (đo RAF/interval). `storage`: { khoá: giá trị } gieo vào localStorage trước khi
  // trang chạy (vị trí linh vật đã nhớ, tuỳ chọn Ẩn…) — chỉ gieo ở lần nạp đầu của MỖI context (không ghi đè lên giá trị đã lưu khi tải lại).
  if (preScript) await p.s("Page.addScriptToEvaluateOnNewDocument", { source: preScript });
  if (storage) {
    const seed = JSON.stringify(storage);
    await p.s("Page.addScriptToEvaluateOnNewDocument", {
      source: `try { if (!sessionStorage.getItem('__qa_seeded')) { const s = ${seed}; for (const k in s) localStorage.setItem(k, s[k]); sessionStorage.setItem('__qa_seeded', '1'); } } catch (e) {}`,
    });
  }
  // `url`: địa chỉ đầy đủ (bản dựng Next thật); mặc định là trang harness `index.html#<tuyến>`.
  await p.s("Page.navigate", { url: url ?? `${base}/index.html#${hash}` });
  try {
    await p.wait("window.__qa && document.readyState === 'complete'", 10000, "tải harness");
  } catch (e) {
    throw new Error(`${e.message}; lỗi trang: ${p.errors.slice(0, 3).join(" | ") || "(không có)"}; url=${await p.ev("location.href").catch(() => "?")}`);
  }
  return p;
}

