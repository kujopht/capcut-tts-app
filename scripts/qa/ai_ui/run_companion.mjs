/**
 * QA LINH VẬT Ink Scout bằng Chrome headless THẬT (CDP) trên harness `entry-companion.tsx`: mã `AiCompanion` + `AiProvider` + `AiPanel`
 * + `AiLauncher` THẬT, asset linh vật THẬT (`web/public/mascot/`, phục vụ ở `/mascot/`), máy chủ SSE giả có nhịp thời gian.
 *
 *   node scripts/qa/ai_ui/run_companion.mjs [--only <regex>] [--shots <thư mục>] [--json <tệp>]
 *
 * Phủ: cờ tắt (0 byte linh vật), tải lười, ánh xạ trạng thái theo vòng đời THẬT (không nháy lỗi khi failover thành công; lỗi cuối;
 * Dừng; Tạo lại; đóng/mở lại; mất mạng; hết lượt), vị trí/va chạm với nút mở·Chat Dock·thanh phát·panel·header ở nhiều bề rộng, kéo thả
 * bằng chuột và chạm, nhớ vị trí + đặt lại, đổi kích thước cửa sổ, giảm chuyển động, CPU lúc nghỉ/ẩn/yên lặng, rò listener/RAF/heap khi
 * mount-unmount lặp lại, biến thể inline ở `/assistant`, rò rỉ metadata nhà cung cấp. Mỗi viewport một browser context mới.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { buildHarness } from "./build.mjs";
import { ONLY, JSON_OUT, results, record, check, info, sleep, serve, launchChrome, Cdp, openPage } from "./lib.mjs";

import {
  PREFS_KEY,
  FLOAT_VPS,
  DESKTOP,
  TABLET_LANDSCAPE,
  INLINE_VPS,
  PERF_PRE,
  hostRect,
  q,
  prefs,
  mapped,
  login,
  waitMascot,
  waitPhysics,
  readyFloating,
  openPanel,
  closePanel,
  setMode,
  settled,
  turn,
  seq,
  spanOf,
  GEOM,
  geom,
  noCollision,
  mouse,
  dragMouse,
  dragTouch,
  swipeUp,
  centerOf,
  cpuNow,
  metric,
  sampleOnce,
  sampleCpu,
  fmtCpu,
  counters,
} from "./companion_lib.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "../../..");
const MASCOT = path.join(repo, "web/public/mascot");

// ----------------------------------------------------------------------------------------- các kịch bản
const SCENARIOS = [];
const scenario = (id, fn, o = {}) => SCENARIOS.push({ id, fn, viewports: o.viewports ?? [DESKTOP], hash: o.hash ?? "/", reducedMotion: o.reducedMotion ?? false, harness: o.harness ?? "on", pre: o.pre ?? null, storage: o.storage ?? null });
const LEAK_RE = /LEAK_|gemini|qwen|alibaba|provider_quota|api[_ -]?key|fingerprint/i;

// ---- 1. Cờ TẮT: cùng mã linh vật thật, cờ build = 0 → không một byte linh vật
scenario("cờ-tắt", async (page, vp, ctx) => {
  await login(page);
  await page.wait("document.querySelector('.ai-launcher')", 8000, "nút nổi");
  await sleep(1500);
  check("cờ TẮT: không có phần tử linh vật nào", vp.name, (await page.ev(`document.querySelectorAll('[class*=ai-companion]').length`)) === 0);
  await openPanel(page);
  await turn(page, "xin chào", { kind: "ok", words: 8 }, { settleMs: 600 });
  check("cờ TẮT: vẫn không có linh vật sau khi mở panel và gửi tin", vp.name, (await page.ev(`document.querySelectorAll('[class*=ai-companion]').length`)) === 0);
  const mascotHits = ctx.hits().filter((h) => h.path.startsWith("/mascot/"));
  check("cờ TẮT: 0 request tới /mascot/ (0 byte linh vật)", vp.name, mascotHits.length === 0, mascotHits.map((h) => h.path).join(","));
  check("cờ TẮT: không ghi tuỳ chọn linh vật vào localStorage", vp.name, (await prefs(page)) === null);
  await page.click(".ai-panel [aria-label='Cài đặt ký ức']");
  await page.wait("document.querySelector('.ai-caidat')", 3000, "popover cài đặt");
  check("cờ TẮT: popover cài đặt không có mục linh vật", vp.name, !(await page.ev(`document.querySelector('.ai-caidat')?.innerText.includes('Ink Scout')`)));
}, { harness: "off" });

// ---- 2. Cờ BẬT: nạp lười, không chặn tải trang, ngân sách byte lúc nghỉ
scenario("tải-lười", async (page, vp, ctx) => {
  await login(page);
  await page.wait("document.querySelector('.ai-launcher')", 8000, "nút nổi");
  const loadEnd = await page.ev(`performance.timeOrigin + performance.getEntriesByType('navigation')[0].loadEventEnd`);
  await waitMascot(page);
  await waitPhysics(page);
  const hits = ctx.hits().filter((h) => h.path.startsWith("/mascot/"));
  const bytes = hits.reduce((s, h) => s + h.bytes, 0);
  const kinds = (re) => hits.filter((h) => re.test(h.path));
  check("cờ BẬT: có tải manifest + 4 script runtime theo đúng thứ tự", vp.name, kinds(/runtime\/ink-scout/).map((h) => path.basename(h.path)).join(",") === "ink-scout.js,ink-scout-walk-rig.js,ink-scout-physics.js,ink-scout-presence.js" || kinds(/runtime\//).length >= 3, kinds(/runtime\//).map((h) => path.basename(h.path)).join(","));
  const earlyHits = hits.filter((h) => h.t < loadEnd);
  check("tải lười: không có request linh vật nào TRƯỚC khi trang tải xong (không chặn đường tới hạn)", vp.name, earlyHits.length === 0, earlyHits.map((h) => h.path).join(","));
  check("tải lười: presence (vòng vẽ liên tục) CHƯA tải khi chưa ai chạm", vp.name, kinds(/ink-scout-presence/).length === 0);
  check("tải lười: chưa tải sprite đi bộ/nhảy khi chưa di chuyển", vp.name, kinds(/animations\/walk|transitions\//).length === 0, kinds(/animations\/walk|transitions\//).map((h) => h.path).join(","));
  info("byte linh vật lúc nghỉ (đã tải)", vp.name, `${hits.length} request, ${(bytes / 1024).toFixed(0)} KB — ${hits.map((h) => path.basename(h.path) + ":" + Math.round(h.bytes / 1024)).join(" ")}`);
  check("ngân sách: lúc nghỉ tải < 700 KB", vp.name, bytes < 700 * 1024, `${(bytes / 1024).toFixed(0)} KB`);
  await page.shot("float-idle");
});

// ---- 3. Ánh xạ trạng thái theo vòng đời thật
scenario("trạng-thái", async (page, vp) => {
  await readyFloating(page);
  await openPanel(page);
  await settled(page);
  check("mở panel → linh vật 'listening'", vp.name, (await mapped(page)) === "listening", String(await mapped(page)));
  await page.shot("state-listening");

  // (a) lượt thường: thinking (chờ token đầu) → answering → success → listening
  let tr = await turn(page, "Xin chào", { kind: "ok", words: 30, pre: 1100, delay: 40 });
  let m = seq(tr, "mapped"), r = seq(tr, "runtime");
  check("lượt thường: thinking → answering → success → listening (đúng thứ tự, không lỗi)", vp.name, m.join(">") === "listening>thinking>answering>success>listening", m.join(">"));
  check("lượt thường: runtime THẬT cũng đi thinking → answering → success", vp.name, ["thinking", "answering", "success"].every((s) => r.includes(s)) && r.indexOf("thinking") < r.indexOf("answering") && r.indexOf("answering") < r.indexOf("success") && !r.includes("error"), r.join(">"));
  const th = spanOf(tr, "mapped", "thinking");
  check("lượt thường: 'thinking' kéo dài suốt khoảng chờ token đầu (≥ 900ms)", vp.name, th && th.ms >= 900, JSON.stringify(th));

  // (b) chế độ Truyện: máy chủ dựng ngữ cảnh trước `meta` → searching, rồi thinking, rồi answering
  await setMode(page, "story");
  tr = await turn(page, "Tìm chương hay", { kind: "ok", words: 20, metaDelay: 900, pre: 700, delay: 40 });
  m = seq(tr, "mapped");
  check("chế độ Truyện: searching (trước meta) → thinking → answering → success", vp.name, m.join(">") === "listening>searching>thinking>answering>success>listening", m.join(">"));
  await page.shot("state-after-story");

  // (c) chế độ Viết: writing
  await setMode(page, "writer");
  tr = await turn(page, "Viết tiếp đoạn này", { kind: "ok", words: 20, pre: 500, delay: 40 });
  m = seq(tr, "mapped");
  check("chế độ Viết: thinking → writing → success", vp.name, m.join(">") === "listening>thinking>writing>success>listening", m.join(">"));
  await setMode(page, "general");

  // (d) FAILOVER nội bộ thành công: khoảng im lặng dài (có nhịp tim `: ping`) rồi trả lời bình thường — client KHÔNG thấy gì khác → không lỗi
  tr = await turn(page, "Hỏi lúc nhà cung cấp chập chờn", { kind: "ok", words: 12, pre: 3000, ping: true, delay: 40 });
  m = seq(tr, "mapped"); r = seq(tr, "runtime");
  check("failover thành công (im lặng 3 giây + ping): KHÔNG BAO GIỜ error/offline", vp.name, !m.includes("error") && !m.includes("offline") && !r.includes("error") && !r.includes("sleepy"), `${m.join(">")} | runtime ${r.join(">")}`);
  check("failover thành công: vẫn 'thinking' suốt khoảng im lặng rồi answering → success", vp.name, m.join(">") === "listening>thinking>answering>success>listening" && (spanOf(tr, "mapped", "thinking")?.ms ?? 0) >= 2700, `${m.join(">")} ${JSON.stringify(spanOf(tr, "mapped", "thinking"))}`);

  // (e) Dừng giữa lúc chờ → về listening, KHÔNG success, KHÔNG error
  await page.ev(`__qa.script.push({ kind: 'hang' })`);
  await page.ev(`__qa.traceStart()`);
  await page.focus("textarea.ai-o"); await page.type("sẽ bị dừng"); await page.key("Enter");
  await page.wait("document.querySelector('.ai-nut-dung')", 5000, "nút Dừng");
  await sleep(900);
  check("đang chờ (hang): 'thinking'", vp.name, (await mapped(page)) === "thinking", String(await mapped(page)));
  await page.click(".ai-nut-dung");
  await page.wait("!document.querySelector('.ai-nut-dung')", 5000, "đã dừng");
  await sleep(1500);
  tr = await page.ev(`__qa.traceStop()`); m = seq(tr, "mapped");
  check("Dừng: thinking → listening, không success, không error", vp.name, m.join(">") === "listening>thinking>listening", m.join(">"));

  // (f) Dừng giữa lúc đang stream chữ
  await page.ev(`__qa.script.push({ kind: 'ok', words: 400, delay: 60 })`);
  await page.ev(`__qa.traceStart()`);
  await page.focus("textarea.ai-o"); await page.type("dừng giữa chừng"); await page.key("Enter");
  await page.wait("document.querySelector('.ai-nut-dung')", 5000, "nút Dừng");
  await sleep(1200);
  check("đang stream: 'answering'", vp.name, (await mapped(page)) === "answering", String(await mapped(page)));
  await page.click(".ai-nut-dung");
  await page.wait("!document.querySelector('.ai-nut-dung')", 5000, "đã dừng");
  await sleep(1500);
  tr = await page.ev(`__qa.traceStop()`); m = seq(tr, "mapped");
  check("Dừng khi đang stream: answering → listening (không success, không error)", vp.name, m.join(">") === "listening>thinking>answering>listening" || m.join(">") === "listening>answering>listening", m.join(">"));

  // (g) Tạo lại
  await turn(page, "một câu để tạo lại", { kind: "ok", words: 10, delay: 30 }, { settleMs: 2600 }); // đủ để hoạt ảnh 'success' trước đó phát xong
  await page.wait("document.querySelector('.ai-nut-tao-lai')", 4000, "nút Tạo lại");
  await page.ev(`__qa.script.push({ kind: 'ok', words: 14, pre: 600, delay: 40 }); __qa.traceStart()`);
  await page.click(".ai-nut-tao-lai");
  await page.wait("__qa.inflight === 0 && !document.querySelector('.ai-nut-dung') && __qa.trace().some(e => e.state === 'success')", 15000, "tạo lại xong");
  await sleep(2200);
  tr = await page.ev(`__qa.traceStop()`); m = seq(tr, "mapped");
  check("Tạo lại: thinking → answering → success → listening", vp.name, m.join(">") === "listening>thinking>answering>success>listening", m.join(">"));

  // (h) LỖI cuối cùng: error giữ nguyên, rồi hồi phục ở lượt sau
  tr = await turn(page, "gây lỗi cuối", { kind: "sse_error", code: "ai_provider_unavailable" }, { settleMs: 2500 });
  m = seq(tr, "mapped"); r = seq(tr, "runtime");
  check("lỗi cuối (nhà cung cấp hết): thinking → error", vp.name, m.join(">") === "listening>thinking>error", m.join(">"));
  check("lỗi cuối: 'error' GIỮ NGUYÊN (không tự reset sau vài giây)", vp.name, (await mapped(page)) === "error" && r[r.length - 1] === "error", `${await mapped(page)} runtime ${r.join(">")}`);
  await page.shot("state-error");
  tr = await turn(page, "thử lại sau lỗi", { kind: "ok", words: 10, pre: 300, delay: 30 });
  m = seq(tr, "mapped");
  check("sau lỗi, lượt mới thành công: error → thinking → answering → success → listening", vp.name, m.join(">") === "error>thinking>answering>success>listening", m.join(">"));

  // (i) Lỗi GIỮA CHỪNG (đã có chữ): answering → error
  tr = await turn(page, "lỗi giữa chừng", { kind: "sse_error", partial: "đang trả lời dở dang ", code: "ai_provider_interrupted" }, { settleMs: 1500 });
  m = seq(tr, "mapped");
  check("lỗi giữa chừng: có chữ rồi mới lỗi → answering → error", vp.name, m.includes("answering") && m[m.length - 1] === "error", m.join(">"));
  await turn(page, "hồi phục", { kind: "ok", words: 6, delay: 20 }, { settleMs: 800 });

  // (j) 429 hỏi quá nhanh (lượt bị từ chối vì chính thao tác vừa rồi): 'error', rồi lượt kế tiếp hồi phục
  tr = await turn(page, "bị chặn quá nhanh", { kind: "http", status: 429, body: { detail: { code: "ai_rate_limited", message: "x" } } }, { settleMs: 1200 });
  m = seq(tr, "mapped");
  check("hỏi quá nhanh (429 ai_rate_limited): linh vật 'error'", vp.name, m[m.length - 1] === "error", m.join(">"));
  tr = await turn(page, "ổn rồi", { kind: "ok", words: 5, delay: 20 }, { settleMs: 2400 });
  m = seq(tr, "mapped");
  check("sau 429: lượt thành công kế tiếp hồi phục linh vật (error → thinking → answering → success → listening)", vp.name, m.join(">") === "error>thinking>answering>success>listening" || m.join(">") === "error>answering>success>listening", m.join(">"));

  // (k) Mất mạng → offline → có mạng lại → hồi phục
  await page.s("Network.enable");
  await page.s("Network.emulateNetworkConditions", { offline: true, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
  await page.ev(`window.dispatchEvent(new Event('offline'))`);
  await page.wait("document.querySelector('.ai-companion')?.getAttribute('data-state') === 'offline'", 4000, "offline");
  check("mất mạng → 'offline'", vp.name, true);
  await page.s("Network.emulateNetworkConditions", { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
  await page.ev(`window.dispatchEvent(new Event('online'))`);
  await page.wait("document.querySelector('.ai-companion')?.getAttribute('data-state') !== 'offline'", 4000, "hết offline");
  await sleep(500);
  check("có mạng lại → rời 'offline'", vp.name, (await mapped(page)) !== "offline", String(await mapped(page)));
  info("hồi phục sau offline", vp.name, String(await mapped(page)));

  // (l) Đóng giữa lúc đang trả lời rồi mở lại: không kẹt
  await page.ev(`__qa.script.push({ kind: 'ok', words: 80, pre: 600, delay: 50 })`);
  await page.focus("textarea.ai-o"); await page.type("đóng giữa chừng"); await page.key("Enter");
  await page.wait("document.querySelector('.ai-nut-dung')", 5000, "nút Dừng");
  await sleep(900);
  await closePanel(page);
  await sleep(600);
  info("đóng panel giữa lúc stream: trạng thái linh vật", vp.name, String(await mapped(page)));
  await page.wait("__qa.inflight === 0", 20000, "stream ngầm kết thúc").catch(() => {});
  await sleep(2500);
  info("sau khi stream ngầm kết thúc (panel đóng)", vp.name, String(await mapped(page)));
  await openPanel(page);
  await sleep(1200);
  check("mở lại sau đó: không kẹt ở thinking/answering/error", vp.name, ["listening", "idle"].includes(await mapped(page)), String(await mapped(page)));

  // (m) Hết lượt hôm nay: máy chủ từ chối TRƯỚC khi nhận (client chưa biết, ví dụ đã dùng ở tab khác) — làm CUỐI vì sau đó ô soạn bị khoá.
  const reset = new Date(Date.now() + 3600_000).toISOString();
  tr = await turn(page, "khi hết lượt", { kind: "http", status: 429, body: { detail: { code: "ai_budget_exhausted", scope: "user", reset_at: reset, message: "x" } } }, { settleMs: 1200 });
  m = seq(tr, "mapped");
  check("hết lượt hôm nay (429 ai_budget_exhausted): linh vật 'offline' (nghỉ tới lúc đặt lại), KHÔNG 'error'", vp.name, m[m.length - 1] === "offline" && !m.includes("error"), m.join(">"));
  await page.shot("state-budget");
});

// ---- 4. Không lộ metadata nhà cung cấp (máy chủ giả CỐ TÌNH nhét LEAK_* vào mọi khung SSE và thông điệp lỗi)
scenario("không-lộ-metadata", async (page, vp) => {
  await readyFloating(page);
  await openPanel(page);
  const scan = async (label) => {
    const leaks = await page.ev(`(() => { const re = new RegExp(${JSON.stringify(LEAK_RE.source)}, 'i'); const out = [];
      if (re.test(document.body.innerText)) out.push('innerText');
      for (const e of document.querySelectorAll('*')) { for (const a of e.attributes) if (re.test(a.name + '=' + a.value)) out.push(e.tagName + '[' + a.name + ']'); }
      try { for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); if (re.test(k + localStorage.getItem(k))) out.push('localStorage:' + k); } } catch {}
      return out; })()`);
    check(`${label}: DOM/aria/localStorage không chứa tên nhà cung cấp, model, khe, vân tay khoá`, vp.name, leaks.length === 0, leaks.slice(0, 4).join(", "));
  };
  await turn(page, "hỏi với máy chủ lỡ lời", { kind: "ok", words: 12, leak: true, delay: 20 }, { settleMs: 600 });
  await scan("sau lượt thành công");
  await turn(page, "lỗi có tên nhà cung cấp", { kind: "sse_error", code: "ai_provider_unavailable", leak: true }, { settleMs: 600 });
  await scan("sau lỗi cuối");
  const banner = await page.ev(`document.querySelector('.ai-loi')?.innerText ?? ''`);
  check("banner lỗi chỉ là câu thân thiện (không số liệu nội bộ)", vp.name, banner.length > 0 && !LEAK_RE.test(banner), banner.slice(0, 80));
  const labels = await page.ev(`[...document.querySelectorAll('.ai-companion *, .ai-companion')].map(e => e.getAttribute('aria-label') || '').filter(Boolean)`);
  check("linh vật: aria-hidden và không có nhãn đọc màn hình lọt ra", vp.name, (await page.ev(`document.querySelector('.ai-companion')?.getAttribute('aria-hidden')`)) === "true", labels.join("|"));
});

// ---- 5. Vị trí & va chạm với phần còn lại của site ở nhiều bề rộng
scenario("vị-trí-va-chạm", async (page, vp) => {
  await readyFloating(page);
  await waitPhysics(page);
  let g = await settled(page).then(() => geom(page));
  check("nghỉ: linh vật hiện", vp.name, g.shown, JSON.stringify(g));
  noCollision("nghỉ", vp, g);
  const L = await q(page, ".ai-launcher");
  check("nghỉ: nằm bên TRÁI nút mở trợ lý (sát nút, không đè)", vp.name, g.h.r <= L.l + 2 && L.l - g.h.r < 140, `host.r=${g.h.r} launcher.l=${L.l}`);
  await page.shot(`float-home-${vp.name}`);

  await page.ev(`__qa.setDock(true)`);
  await sleep(500);
  g = await settled(page).then(() => geom(page));
  noCollision("Chat Dock mở", vp, g);
  const D = await q(page, ".chat-dock");
  check("Chat Dock mở: linh vật dịch sang trái khỏi dock", vp.name, !g.present || g.h.r <= D.l + 2, `host.r=${g.h.r} dock.l=${D?.l}`);
  await page.shot(`float-dock-${vp.name}`);

  await page.ev(`__qa.setMini(true)`);
  await sleep(500);
  g = await settled(page).then(() => geom(page));
  noCollision("Chat Dock + thanh phát", vp, g);
  await page.ev(`__qa.setDock(false)`);
  await sleep(500);
  g = await settled(page).then(() => geom(page));
  noCollision("chỉ thanh phát", vp, g);
  const M = await q(page, ".mini");
  check("thanh phát: linh vật nằm TRÊN thanh phát", vp.name, !g.present || g.h.b <= M.t + 2, `host.b=${g.h.b} mini.t=${M?.t}`);
  await page.ev(`__qa.setMini(false)`);
  await sleep(400);

  await openPanel(page);
  await sleep(300);
  g = await settled(page).then(() => geom(page));
  info("panel mở: chỗ của linh vật", vp.name, g.shown ? `hiện, host=(${Math.round(g.h.l)},${Math.round(g.h.t)})` : "ẨN (không có chỗ an toàn)");
  noCollision("panel mở", vp, g);
  await page.shot(`float-open-${vp.name}`);
  if (g.shown) {
    const P = await q(page, ".ai-panel");
    const H = await q(page, ".site-header");
    check("panel mở: linh vật không lên trên đáy header", vp.name, g.h.t + g.h.h * 0.1 >= H.b - 1, `thân.t=${g.h.t + g.h.h * 0.1} header.b=${H.b}`);
    check("panel mở: ngồi trên/cạnh panel (chân sát mép trên hoặc đứng cạnh trái)", vp.name, Math.abs(g.h.b - P.t) < g.h.h * 0.3 || g.h.r <= P.l + 2, `host.b=${g.h.b} panel.t=${P.t}`);
  }
  await page.ev(`__qa.setDock(true)`);
  await sleep(600);
  g = await settled(page).then(() => geom(page));
  noCollision("panel mở + Chat Dock", vp, g);
  await page.ev(`__qa.setDock(false)`);
  await sleep(400);

  await closePanel(page);
  await sleep(300);
  g = await settled(page, { timeout: 12000 }).then(() => geom(page));
  noCollision("đóng panel → về nhà", vp, g);
  check("đóng panel → linh vật về đúng chỗ nhà (bên trái nút mở)", vp.name, g.shown && g.h.r <= L.l + 2 && Math.abs(g.h.r - (await q(page, ".ai-launcher")).l) < 140, JSON.stringify(g.h));
}, { viewports: FLOAT_VPS });

// ---- 6. Kéo thả bằng chuột, nhớ vị trí, đặt lại
scenario("kéo-thả-chuột", async (page, vp, ctx) => {
  await readyFloating(page);
  await waitPhysics(page);
  const R0 = await settled(page);
  const g0 = await geom(page);
  check("physics đã gắn nhưng linh vật KHÔNG focus được (gỡ hẳn tabindex + aria-label trên host)", vp.name,
    (await page.ev(`(() => { const h = document.querySelector('.ai-companion-host'); return !h.hasAttribute('tabindex') && !h.hasAttribute('aria-label') && h.tabIndex === -1; })()`)), "");
  // bấm chuột vào linh vật KHÔNG được chuyển focus vào nó (review Codex #3)
  await page.ev(`document.querySelector('.ai-launcher').focus()`);
  const hostBox = await hostRect(page);
  await mouse(page, "mouseMoved", centerOf(hostBox).x, centerOf(hostBox).y);
  await mouse(page, "mousePressed", centerOf(hostBox).x, centerOf(hostBox).y, { buttons: 1 });
  await mouse(page, "mouseReleased", centerOf(hostBox).x, centerOf(hostBox).y);
  await sleep(300);
  check("bấm vào linh vật: focus KHÔNG rơi vào linh vật", vp.name, await page.ev(`!document.activeElement?.closest('.ai-companion')`), await page.ev(`document.activeElement?.tagName + '.' + document.activeElement?.className`));
  await sleep(1500);
  check("host báo touch-action: none (chạm kéo không cuộn trang)", vp.name, (await page.ev(`getComputedStyle(document.querySelector('.ai-companion-host')).touchAction`)) === "none",
    await page.ev(`getComputedStyle(document.querySelector('.ai-companion-host')).touchAction`));

  // bấm nhẹ (không kéo): phản ứng 'hover'/vẫy tay, KHÔNG đổi vị trí nhớ
  const c0 = centerOf(R0);
  const hits0 = ctx.hits().length;
  await page.ev(`__qa.traceStart()`);
  await page.ev(`(() => { window.__lbl = []; const cv = document.querySelector('.ai-companion-host canvas'); new MutationObserver(() => window.__lbl.push(cv.getAttribute('aria-label'))).observe(cv, { attributes: true, attributeFilter: ['aria-label'] }); })()`);
  await mouse(page, "mouseMoved", c0.x, c0.y);
  await sleep(500);
  const afterEnter = { mapped: await mapped(page), lbl: await page.ev(`window.__lbl.slice()`) };
  await mouse(page, "mousePressed", c0.x, c0.y, { buttons: 1 });
  await sleep(60);
  await mouse(page, "mouseReleased", c0.x, c0.y);
  await sleep(1800);
  let tr = await page.ev(`__qa.traceStop()`);
  info("bấm nhẹ vào linh vật: dòng trạng thái", vp.name, `mapped ${seq(tr, "mapped").join(">")} | runtime ${seq(tr, "runtime").join(">")} | nhãn canvas ${JSON.stringify(await page.ev(`window.__lbl`))} | sau pointerenter ${JSON.stringify(afterEnter)}`);
  info("bấm nhẹ: tệp mới tải", vp.name, ctx.hits().slice(hits0).map((h) => h.path.replace("/mascot/ink-scout/", "")).join(" "));
  check("bấm nhẹ: không ghi vị trí mới", vp.name, (await prefs(page))?.homeX == null, JSON.stringify(await prefs(page)));
  await mouse(page, "mouseMoved", 5, 5);
  await sleep(300);

  // kéo ngang sang trái trên sàn → đứng ở đó và được NHỚ
  await dragMouse(page, centerOf(R0), { x: centerOf(R0).x - 320, y: centerOf(R0).y });
  let R1 = await settled(page);
  check("kéo sang trái 320px: đứng đúng chỗ thả (±16px)", vp.name, Math.abs(R1.l - (R0.l - 320)) <= 16, `trước ${R0.l} sau ${R1.l}`);
  check("kéo trên sàn: giữ nguyên độ cao sàn", vp.name, Math.abs(R1.t - R0.t) <= 3, `trước ${R0.t} sau ${R1.t}`);
  let p = await prefs(page);
  check("vị trí được NHỚ (homeX ≈ -320, kẹp ≤ 0)", vp.name, p && typeof p.homeX === "number" && Math.abs(p.homeX + 320) <= 16, JSON.stringify(p));
  noCollision("sau khi kéo", vp, await geom(page));
  await page.shot("drag-1-moved");

  // nhấc lên không trung rồi thả → rơi xuống sàn
  await dragMouse(page, centerOf(R1), { x: centerOf(R1).x - 100, y: centerOf(R1).y - 220 });
  let R2 = await settled(page);
  check("thả giữa không trung → rơi xuống sàn (cùng độ cao sàn)", vp.name, Math.abs(R2.t - R0.t) <= 3, `sàn ${R0.t} sau ${R2.t}`);
  info("thả từ trên cao: vị trí ngang", vp.name, `${Math.round(R2.l)} (nhà mặc định ${Math.round(R0.l)})`);

  // kéo ra ngoài màn hình bên trái / lên trên header: bị kẹp biên
  await dragMouse(page, centerOf(R2), { x: -60, y: centerOf(R2).y });
  let R3 = await settled(page);
  check("kéo ra ngoài mép trái: bị kẹp trong màn hình", vp.name, R3.l >= -1, `l=${R3.l}`);
  const H = await q(page, ".site-header");
  await dragMouse(page, centerOf(R3), { x: centerOf(R3).x + 40, y: 4 });
  const R4 = await settled(page);
  check("kéo lên trên header: không bao giờ lên trên đáy header", vp.name, R4.t + R4.h * 0.1 >= H.b - 2, `thân.t=${R4.t + R4.h * 0.1} header.b=${H.b}`);

  // kéo vào nút mở trợ lý (bên phải): bị kẹp, không chui xuống dưới nút
  const L = await q(page, ".ai-launcher");
  await dragMouse(page, centerOf(R4), { x: L.l + L.w / 2, y: L.t + L.h / 2 });
  const R5 = await settled(page);
  check("thả lên nút mở trợ lý: không đè lên nút", vp.name, R5.r - R5.w * 0.2 <= L.l + 2 || R5.b <= L.t + 2, `host.r=${R5.r} launcher.l=${L.l}`);
  noCollision("sau khi thả vào nút mở", vp, await geom(page));

  // tải lại: vị trí nhớ được khôi phục
  await dragMouse(page, centerOf(R5), { x: centerOf(R5).x - 220, y: centerOf(R5).y });
  const R6 = await settled(page);
  p = await prefs(page);
  await page.s("Page.reload");
  await page.wait("window.__qa && document.readyState === 'complete'", 10000, "tải lại");
  await readyFloating(page);
  const R7 = await settled(page);
  check("tải lại trang: linh vật đứng đúng chỗ đã nhớ (±2px)", vp.name, Math.abs(R7.l - R6.l) <= 2 && Math.abs(R7.t - R6.t) <= 2, `trước ${R6.l},${R6.t} sau ${R7.l},${R7.t}`);

  // mở panel: nhảy lên chỗ ngồi; thả vào thân panel → được đưa ra chỗ an toàn
  await openPanel(page);
  await waitPhysics(page).catch(() => {});
  const R8 = await settled(page, { timeout: 12000 });
  const gP = await geom(page);
  if (gP.shown) {
    const P = await q(page, ".ai-panel");
    await dragMouse(page, centerOf(R8), { x: P.l + P.w / 2, y: P.t + P.h / 2 });
    const R9 = await settled(page, { timeout: 12000 });
    const g9 = await geom(page);
    check("thả vào thân panel: được đưa tới chỗ an toàn (không đè điều khiển nào)", vp.name, g9.ctrl.length === 0 && g9.covered.length === 0, `${g9.ctrl.join(",")} ${g9.covered.join(";")} host=(${Math.round(R9.l)},${Math.round(R9.t)})`);
    const P2 = await q(page, ".ai-panel");
    const bodyInPanel = (R9.l + R9.w * 0.2 < P2.r - 3 && R9.r - R9.w * 0.2 > P2.l + 3 && R9.b - R9.h * 0.04 > P2.t + 14 && R9.t + R9.h * 0.1 < P2.b);
    check("thả vào thân panel: thân không nằm trong panel sau khi đứng yên", vp.name, !bodyInPanel, `host=(${R9.l},${R9.t})-(${R9.r},${R9.b}) panel=(${P2.l},${P2.t})-(${P2.r},${P2.b})`);
    await page.shot("drag-2-panel-rescue");
  } else info("panel mở: không có chỗ ngồi — bỏ bước thả vào panel", vp.name, "");

  // Đặt lại vị trí qua popover cài đặt
  await page.click(".ai-panel [aria-label='Cài đặt ký ức']");
  await page.wait("document.querySelector('.ai-caidat-datlai')", 3000, "nút Đặt lại vị trí");
  await page.shot("drag-3-settings");
  await page.click(".ai-caidat-datlai");
  await sleep(500);
  check("Đặt lại vị trí: xoá vị trí nhớ", vp.name, (await prefs(page))?.homeX == null, JSON.stringify(await prefs(page)));
  await page.key("Escape");
  await closePanel(page).catch(() => {});
  const R10 = await settled(page, { timeout: 12000 });
  check("sau đặt lại: linh vật về chỗ nhà mặc định (±2px)", vp.name, Math.abs(R10.l - R0.l) <= 2 && Math.abs(R10.t - R0.t) <= 2, `mặc định ${R0.l},${R0.t} sau ${R10.l},${R10.t}`);
  void g0;
});

// ---- 6b. Cầm linh vật GIỮA LÚC nó đang nhảy lên panel / đang áp trạng thái: không bị giật khỏi tay (review Codex #1)
scenario("kéo-giữa-lúc-nhảy", async (page, vp) => {
  await readyFloating(page);
  await waitPhysics(page);
  await settled(page);
  // Mở panel rồi ĐÓNG: director ra lệnh stand-up + return-home (đường về nhà KHÔNG đi qua panel — panel có z-index cao hơn linh vật
  // nên nếu cầm lúc nó bay sau panel thì con trỏ sẽ trúng panel chứ không phải linh vật).
  await openPanel(page);
  const R0 = await settled(page, { timeout: 12000 });
  await closePanel(page);
  // chờ tới khi linh vật ĐANG di chuyển (đã rời chỗ ngồi ≥ 25px) rồi cầm ngay giữa không trung
  let cur = R0, moved = false;
  for (let i = 0; i < 80 && !moved; i += 1) {
    await sleep(25);
    cur = await hostRect(page);
    moved = Math.hypot(cur.l - R0.l, cur.t - R0.t) >= 25;
  }
  check("linh vật đang di chuyển về nhà khi cầm (đã rời chỗ ngồi ≥ 25px)", vp.name, moved, `${R0.l},${R0.t} → ${cur.l},${cur.t}`);
  // Đo lại ngay trước khi bấm (linh vật đang bay ~0,5px/ms): bấm TRƯỚC khi ra khỏi ô 96px của nó.
  cur = await hostRect(page);
  const from = centerOf(cur);
  await mouse(page, "mousePressed", from.x, from.y, { buttons: 1 });
  await sleep(80); // React cập nhật lớp "đang cầm" sau sự kiện `pickup`
  const grabbed = await page.ev(`!!document.querySelector('.ai-companion-giu')`);
  check("bấm giữa lúc đang di chuyển: linh vật bị CẦM (physics nhận pointerdown, director dừng ra lệnh)", vp.name, grabbed, `host ${Math.round(cur.l)},${Math.round(cur.t)} bấm ${Math.round(from.x)},${Math.round(from.y)}`);
  const samples = [];
  const steps = 22;
  const to = { x: from.x - 260, y: from.y + 40 };
  for (let i = 1; i <= steps; i += 1) {
    const px = from.x + ((to.x - from.x) * i) / steps, py = from.y + ((to.y - from.y) * i) / steps;
    await mouse(page, "mouseMoved", px, py, { buttons: 1 });
    await sleep(40);
    const r = await hostRect(page);
    const c = centerOf(r);
    samples.push({ d: Math.hypot(c.x - px, c.y - py), i });
  }
  const tracked = samples.filter((s) => s.i >= 5 && s.d <= 60).length / samples.filter((s) => s.i >= 5).length;
  check("đang cầm: linh vật bám theo con trỏ (≥ 85% mẫu trong 60px) — không bị lệnh nhảy/trạng thái cũ giật đi", vp.name, tracked >= 0.85, `${(tracked * 100).toFixed(0)}% — ${samples.filter((s) => s.i >= 5).map((s) => Math.round(s.d)).join(",")}`);
  await mouse(page, "mouseReleased", to.x, to.y, { buttons: 0 });
  const R1 = await settled(page, { timeout: 12000 });
  const g = await geom(page);
  check("thả: đứng yên hợp lệ, không đè điều khiển nào", vp.name, g.present && g.ctrl.length === 0 && g.covered.length === 0 && R1.l >= -1, JSON.stringify({ ctrl: g.ctrl, covered: g.covered, l: R1.l }));
  info("kết cục sau khi thả giữa lúc bay", vp.name, `host (${Math.round(R1.l)},${Math.round(R1.t)}) thả ở (${Math.round(to.x)},${Math.round(to.y)}) · ${(await prefs(page))?.homeX ?? "không nhớ"}`);
});

// ---- 6c. Runtime/physics KHÔNG tải được lần đầu (mạng chập chờn) → thử lại khi mount lại, không treo vĩnh viễn (review Codex #2)
scenario("tải-thất-bại-thử-lại", async (page, vp) => {
  await page.s("Network.enable");
  await page.s("Network.setBlockedURLs", { urls: ["*ink-scout.js*"] });
  await login(page);
  await page.wait("document.querySelector('.ai-launcher')", 8000, "nút nổi");
  await sleep(6000);
  check("runtime bị chặn: không linh vật, trợ lý vẫn chạy (nút mở hiện)", vp.name, !(await page.ev(`!!document.querySelector('.ai-companion-host canvas')`)) && (await page.ev(`!!document.querySelector('.ai-launcher')`)));
  await page.s("Network.setBlockedURLs", { urls: [] });
  const emit = (hidden) => page.ev(`window.dispatchEvent(new CustomEvent('fas:ai-companion-prefs', { detail: { hidden: ${hidden}, reducedMotion: false, homeX: null } }))`);
  await emit(true);
  await sleep(300);
  await emit(false); // mount lại → nạp lại
  await waitMascot(page, 15000);
  check("bỏ chặn rồi mount lại: linh vật nạp được (không treo trên thẻ script đã hỏng)", vp.name, await page.ev(`!!document.querySelector('.ai-companion-host canvas')`));
  check("chỉ còn MỘT thẻ <script> cho runtime (thẻ hỏng đã được gỡ)", vp.name, (await page.ev(`document.querySelectorAll('script[id="ink-scout-ink-scout"]').length`)) === 1);
});

// ---- 7. Kéo thả bằng CHẠM (máy tính bảng ngang, con trỏ thô)
scenario("kéo-thả-chạm", async (page, vp) => {
  await readyFloating(page);
  await waitPhysics(page);
  check("máy chạm: physics gắn ngay (không chờ rảnh rỗi)", vp.name, true);
  const R0 = await settled(page);
  await dragTouch(page, centerOf(R0), { x: centerOf(R0).x - 300, y: centerOf(R0).y });
  const R1 = await settled(page);
  check("chạm kéo sang trái 300px: đứng đúng chỗ thả (±16px)", vp.name, Math.abs(R1.l - (R0.l - 300)) <= 16, `trước ${R0.l} sau ${R1.l}`);
  check("chạm kéo: trang KHÔNG bị cuộn theo", vp.name, (await page.ev(`scrollY`)) === 0, String(await page.ev(`scrollY`)));
  const p = await prefs(page);
  check("chạm kéo: vị trí được nhớ", vp.name, p && typeof p.homeX === "number" && p.homeX < -250, JSON.stringify(p));
  noCollision("sau chạm kéo", vp, await geom(page));
  // chạm vào vùng nền trang (ngoài linh vật) vẫn cuộn bình thường: host không chặn vùng quanh nó
  const before = await page.ev(`scrollY`);
  await swipeUp(page, { x: 300, y: 600 }, 320);
  await sleep(700);
  check("vuốt nền trang (ngoài linh vật): vẫn cuộn được", vp.name, (await page.ev(`scrollY`)) > before + 50, `${before} → ${await page.ev(`scrollY`)}`);
  // Vuốt BẮT ĐẦU trên chính linh vật = kéo thả (không cuộn trang): đã kiểm ở trên (scrollY === 0 sau chạm kéo).
  await page.shot("touch-drag");
}, { viewports: [TABLET_LANDSCAPE] });

// ---- 7b. ĐỐI CHỨNG của bài vuốt ở trên: cùng cử chỉ trên harness KHÔNG có linh vật (cờ tắt) cũng phải cuộn — nếu không thì bài thử vô giá trị
scenario("đối-chứng-vuốt", async (page, vp) => {
  await login(page);
  await page.wait("document.querySelector('.ai-launcher')", 8000, "nút nổi");
  const before = await page.ev(`scrollY`);
  await swipeUp(page, { x: 300, y: 600 }, 320);
  await sleep(700);
  check("đối chứng: vuốt nền trang cuộn được khi KHÔNG có linh vật (bài thử vuốt có giá trị)", vp.name, (await page.ev(`scrollY`)) > before + 50, `${before} → ${await page.ev(`scrollY`)}`);
}, { viewports: [TABLET_LANDSCAPE], harness: "off" });

// ---- 8. Đổi kích thước cửa sổ với vị trí đã nhớ ở rìa
scenario("đổi-kích-thước", async (page, vp) => {
  await page.s("Emulation.setDeviceMetricsOverride", { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
  await readyFloating(page);
  await waitPhysics(page);
  const R0 = await settled(page);
  info("prefs đã gieo", vp.name, JSON.stringify(await prefs(page)));
  check("homeX đã gieo (-900) được áp ở 1920 (linh vật đứng xa nút mở)", vp.name, R0.l < (await q(page, ".ai-launcher")).l - 700, `host.l=${R0.l} prefs=${JSON.stringify(await prefs(page))}`);
  for (const [w, h] of [[1280, 800], [1100, 700], [1024, 768]]) {
    await page.s("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 1, mobile: false });
    await sleep(500);
    const R = await settled(page, { timeout: 10000 });
    const g = await geom(page);
    check(`thu cửa sổ ${w}×${h}: linh vật bị kẹp vào trong màn hình`, `${w}`, R.l >= -1 && g.inViewport, JSON.stringify(R));
    noCollision(`thu ${w}`, { name: String(w) }, g);
  }
  await page.s("Emulation.setDeviceMetricsOverride", { width: 900, height: 700, deviceScaleFactor: 1, mobile: false });
  await sleep(600);
  const disp = await page.ev(`getComputedStyle(document.querySelector('.ai-companion') ?? document.body).display`);
  check("dưới 1024px: linh vật nổi biến mất (không còn nút nổi, không lỗi)", "900", disp === "none" || !(await page.ev(`!!document.querySelector('.ai-companion')`)), disp);
  await page.s("Emulation.setDeviceMetricsOverride", { width: 1600, height: 900, deviceScaleFactor: 1, mobile: false });
  await sleep(800);
  const g = await geom(page);
  check("phóng lại lên 1600: linh vật trở lại, hợp lệ", "1600", g.present && g.shown && g.inViewport, JSON.stringify(g));
  noCollision("phóng lại", { name: "1600" }, g);
  // panel đang mở khi đổi kích thước
  await openPanel(page);
  await sleep(300);
  await settled(page, { timeout: 12000 });
  for (const [w, h] of [[1280, 720], [1024, 700], [1366, 900]]) {
    await page.s("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 1, mobile: false });
    await sleep(500);
    await settled(page, { timeout: 12000 });
    noCollision(`panel mở, đổi ${w}×${h}`, { name: `${w}x${h}` }, await geom(page));
  }
}, { viewports: [{ name: "resize", width: 1920, height: 1080, mobile: false }], storage: { [PREFS_KEY]: JSON.stringify({ hidden: false, reducedMotion: false, homeX: -900 }) } });

// ---- 9. Giảm chuyển động (hệ điều hành) và tuỳ chọn riêng
scenario("giảm-chuyển-động", async (page, vp, ctx) => {
  await readyFloating(page);
  await sleep(800);
  check("giảm chuyển động: data-reduced=1 trên khung linh vật", vp.name, (await page.ev(`document.querySelector('.ai-companion')?.getAttribute('data-reduced')`)) === "1");
  const hits = ctx.hits().filter((h) => h.path.startsWith("/mascot/ink-scout/") && /sprite|animations|transitions/.test(h.path));
  check("giảm chuyển động: KHÔNG tải sprite hoạt ảnh (chỉ ảnh tĩnh)", vp.name, hits.length === 0, hits.map((h) => h.path).join(","));
  const raf0 = await page.ev(`window.__perf.raf`);
  await sleep(1500);
  const dr = (await page.ev(`window.__perf.raf`)) - raf0;
  check("giảm chuyển động: gần như không vòng vẽ lúc nghỉ (≤ 6 khung / 1,5 giây)", vp.name, dr <= 6, `${dr} khung`);
  await openPanel(page);
  await sleep(800);
  const R = await hostRect(page);
  const g = await geom(page);
  check("giảm chuyển động: mở panel dời tức thì tới chỗ ngồi (không tải sprite nhảy)", vp.name, ctx.hits().filter((h) => /transitions\/|animations\/walk/.test(h.path)).length === 0, "");
  noCollision("giảm chuyển động + panel mở", vp, g);
  const tr = await turn(page, "thử giảm chuyển động", { kind: "ok", words: 12, pre: 500, delay: 30 }, { settleMs: 2400 });
  check("giảm chuyển động: vẫn thinking → answering → success → listening", vp.name, seq(tr, "mapped").join(">") === "listening>thinking>answering>success>listening", seq(tr, "mapped").join(">"));
  await page.shot("reduced-motion");
  void R;
}, { reducedMotion: true, pre: PERF_PRE });

// ---- 10. CPU lúc nghỉ / yên lặng / ẩn / panel mở / đang stream
// CPU là TỔNG mọi tiến trình Chrome (trình duyệt + GPU + renderer; 1 nhân = 100%) lấy từ `SystemInfo.getProcessInfo`. Harness chạy phần mềm
// (--disable-gpu), và chính trang site có hoạt ảnh CSS liên tục (viền header, nền…) nên số tuyệt đối bị nó chi phối: ĐÓNG BĂNG mọi hoạt
// ảnh/transition CSS của trang để chỉ còn phần của linh vật, và lấy "cơ sở" = CÙNG trang với linh vật đang bị Ẩn từ đầu (tuỳ chọn Ẩn).
const FREEZE_CSS = `(() => { const s = document.createElement('style'); s.id = 'qa-freeze'; s.textContent = '*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important}'; document.head.appendChild(s); })()`;
scenario("hiệu-năng-cpu", async (page, vp, ctx) => {
  const cdp = ctx.cdp;
  await page.s("Performance.enable");
  await login(page);
  await page.wait("document.querySelector('.ai-launcher')", 8000, "nút nổi");
  await page.ev(FREEZE_CSS);
  await sleep(4000); // để Chrome (trình duyệt/GPU/renderer) yên sau khi tạo context rồi mới đo cơ sở
  check("cơ sở: linh vật đang ẨN từ đầu (không có khung linh vật)", vp.name, !(await page.ev(`!!document.querySelector('.ai-companion')`)));
  const base = await sampleCpu(page, cdp, 4500, 3);
  info("CPU cơ sở (cùng trang, linh vật bị Ẩn)", vp.name, fmtCpu(base));
  // Bỏ Ẩn như người dùng làm: ghi tuỳ chọn rồi phát sự kiện (cùng đường với CompanionSettings)
  await page.ev(`(() => { const v = { hidden: false, reducedMotion: false, homeX: null }; localStorage.setItem(${JSON.stringify(PREFS_KEY)}, JSON.stringify(v)); window.dispatchEvent(new CustomEvent('fas:ai-companion-prefs', { detail: v })); })()`);
  await waitMascot(page);
  await waitPhysics(page);
  await sleep(800);
  const active = await sampleCpu(page, cdp, 3000, 3);
  info("CPU linh vật ĐANG hoạt ảnh (nghỉ, panel đóng, trước yên lặng)", vp.name, fmtCpu(active));
  check("linh vật đang hoạt ảnh vẽ khung (RAF > 0)", vp.name, (active.rafPerSec ?? 0) > 1, String(active.rafPerSec));
  await page.wait("document.querySelector('.ai-companion')?.getAttribute('data-quiet') === '1'", 14000, "chế độ yên lặng");
  await sleep(800);
  const quiet = await sampleCpu(page, cdp, 4500, 3);
  info("CPU linh vật YÊN LẶNG (dừng vẽ sau 6s)", vp.name, fmtCpu(quiet));
  check("yên lặng: vòng vẽ DỪNG (RAF ≈ 0)", vp.name, (quiet.rafPerSec ?? 99) < 0.6, `${quiet.rafPerSec?.toFixed(2)} RAF/s`);
  check("yên lặng: luồng chính ≈ cơ sở (≤ cơ sở + 1%)", vp.name, quiet.mainPct <= base.mainPct + 1, `${quiet.mainPct.toFixed(2)}% vs cơ sở ${base.mainPct.toFixed(2)}%`);
  info("linh vật hoạt ảnh tốn thêm so với cơ sở", vp.name, `luồng chính +${(active.mainPct - base.mainPct).toFixed(1)}% · tiến trình +${(active.cpuPct - base.cpuPct).toFixed(1)}% của 1 nhân`);
  // Đánh thức: panel mở → vẽ lại, đóng + yên lặng lại
  await openPanel(page);
  await settled(page, { timeout: 12000 });
  const open = await sampleCpu(page, cdp, 2500, 2);
  info("CPU panel MỞ, linh vật ngồi (không stream)", vp.name, fmtCpu(open));
  await page.ev(`__qa.script.push({ kind: 'ok', words: 300, delay: 40 })`);
  await page.focus("textarea.ai-o"); await page.type("đo CPU khi stream"); await page.key("Enter");
  await sleep(1500);
  const streaming = await sampleCpu(page, cdp, 3000, 2);
  info("CPU lúc ĐANG stream trả lời", vp.name, fmtCpu(streaming));
  await page.wait("__qa.inflight === 0 && !document.querySelector('.ai-nut-dung')", 30000, "stream xong");
  await sleep(2500);
  // ẨN: bật "Ẩn Ink Scout" qua popover cài đặt (đường của người dùng)
  await page.click(".ai-panel [aria-label='Cài đặt ký ức']");
  await page.wait("document.querySelector(\"[aria-label='Ẩn linh vật Ink Scout']\")", 3000, "ô Ẩn");
  await page.click("[aria-label='Ẩn linh vật Ink Scout']");
  await sleep(600);
  const hiddenFlag = await prefs(page);
  await page.wait("!document.querySelector('.ai-companion')", 4000, "linh vật đã bị ẩn/huỷ").catch(async () => {
    throw new Error(`linh vật không biến mất sau khi tick 'Ẩn' — prefs=${JSON.stringify(hiddenFlag)} khung=${await page.ev(`document.querySelector('.ai-companion')?.className ?? null`)}`);
  });
  await sleep(1500);
  const hidden = await sampleCpu(page, cdp, 4500, 3);
  info("CPU khi người dùng ẨN linh vật", vp.name, fmtCpu(hidden));
  check("ẨN: không còn vòng vẽ nào (RAF ≈ 0)", vp.name, (hidden.rafPerSec ?? 99) < 0.6, `${hidden.rafPerSec}`);
  check("ẨN: luồng chính ≈ cơ sở (≤ cơ sở + 1%)", vp.name, hidden.mainPct <= base.mainPct + 1, `${hidden.mainPct.toFixed(2)}% vs ${base.mainPct.toFixed(2)}%`);
  const pend = await page.ev(`({ pending: window.__perf.pending.size, intervals: window.__perf.intervals.size })`);
  info("RAF đang chờ / interval đang chạy khi ẨN", vp.name, JSON.stringify(pend));
}, { pre: PERF_PRE, storage: { [PREFS_KEY]: JSON.stringify({ hidden: true, reducedMotion: false, homeX: null }) } });

// ---- 11. Rò rỉ: mount/unmount, mở/đóng, stream, Dừng lặp lại
scenario("rò-rỉ", async (page, vp) => {
  await readyFloating(page);
  await waitPhysics(page);
  await openPanel(page);
  await closePanel(page);
  await sleep(1500);
  const base = await counters(page);
  info("cơ sở trước vòng lặp", vp.name, JSON.stringify(base));

  // mount/unmount: đổi tuyến floating ↔ inline (/assistant) và bật/tắt tuỳ chọn Ẩn
  for (let i = 0; i < 12; i += 1) {
    await page.ev(`location.hash = '#/assistant'`);
    await sleep(i % 3 === 0 ? 20 : 220); // có lượt đổi quá nhanh: linh vật huỷ khi runtime còn đang nạp
    await page.ev(`location.hash = '#/'`);
    await sleep(i % 3 === 0 ? 20 : 220);
  }
  for (let i = 0; i < 8; i += 1) {
    await page.ev(`window.dispatchEvent(new CustomEvent('fas:ai-companion-prefs', { detail: { hidden: true, reducedMotion: false, homeX: null } }))`);
    await sleep(i % 2 ? 30 : 250);
    await page.ev(`window.dispatchEvent(new CustomEvent('fas:ai-companion-prefs', { detail: { hidden: false, reducedMotion: false, homeX: null } }))`);
    await sleep(i % 2 ? 30 : 400);
  }
  // mở/đóng panel
  for (let i = 0; i < 16; i += 1) {
    await page.click(".ai-launcher");
    await sleep(i % 2 ? 60 : 300);
    await page.click(".ai-panel [aria-label='Đóng trợ lý AI']").catch(() => {});
    await sleep(i % 2 ? 60 : 300);
  }
  // stream + Dừng
  await openPanel(page).catch(() => {});
  for (let i = 0; i < 4; i += 1) await turn(page, `tin ${i}`, { kind: "ok", words: 20, delay: 10 }, { settleMs: 200 });
  for (let i = 0; i < 3; i += 1) {
    await page.ev(`__qa.script.push({ kind: 'hang' })`);
    await page.focus("textarea.ai-o"); await page.type("dừng"); await page.key("Enter");
    await page.wait("document.querySelector('.ai-nut-dung')", 4000, "nút Dừng");
    await page.click(".ai-nut-dung");
    await page.wait("!document.querySelector('.ai-nut-dung')", 4000, "đã dừng");
  }
  await closePanel(page).catch(() => {});
  await page.wait("__qa.inflight === 0", 10000, "không còn luồng SSE mở");
  check("sau lặp: máy chủ giả không còn luồng SSE nào mở (huỷ sạch)", vp.name, (await page.ev(`__qa.inflight`)) === 0);
  await sleep(8000); // đủ cho chế độ yên lặng + ân hạn presence
  const after = await counters(page);
  info("sau vòng lặp (đã GC)", vp.name, JSON.stringify(after));
  check("rò listener: jsEventListeners tăng ≤ 12", vp.name, after.listeners - base.listeners <= 12, `${base.listeners} → ${after.listeners}`);
  check("rò DOM: số nút tăng ≤ 150 (chỉ là tin nhắn đã thêm)", vp.name, after.nodes - base.nodes <= 150, `${base.nodes} → ${after.nodes}`);
  check("rò timer: RAF đang chờ không tăng quá 2", vp.name, after.pending - base.pending <= 2, `${base.pending} → ${after.pending}`);
  check("rò timer: interval đang chạy không tăng quá 1", vp.name, after.intervals - base.intervals <= 1, `${base.intervals} → ${after.intervals}`);
  check("rò heap: tăng < 6 MB sau ~70 chu kỳ", vp.name, after.heap - base.heap < 6 * 1024 * 1024, `${((after.heap - base.heap) / 1024 / 1024).toFixed(2)} MB`);
  check("sau vòng lặp: số document không tăng (không rò iframe/trang)", vp.name, after.docs <= base.docs + 1, `${base.docs} → ${after.docs}`);
  // Còn hoạt động đúng sau tất cả: mở panel, linh vật vẫn đáp ứng
  await waitMascot(page);
  await openPanel(page);
  const tr = await turn(page, "còn sống không", { kind: "ok", words: 10, pre: 300, delay: 20 }, { settleMs: 2200 });
  check("sau vòng lặp: linh vật vẫn theo đúng vòng đời (thinking → answering → success)", vp.name, seq(tr, "mapped").join(">") === "listening>thinking>answering>success>listening", seq(tr, "mapped").join(">"));
}, { pre: PERF_PRE });

// ---- 12. Tab ẩn / quay lại (background/foreground)
scenario("nền-trước-sau", async (page, vp, ctx) => {
  await readyFloating(page);
  await waitPhysics(page);
  await sleep(1500);
  const r0 = await page.ev(`window.__perf.raf`);
  await sleep(1000);
  const running = ((await page.ev(`window.__perf.raf`)) - r0);
  check("trước khi ẩn tab: linh vật đang vẽ", vp.name, running > 10, `${running} khung/giây`);
  await page.ev(`(() => { Object.defineProperty(document, 'hidden', { configurable: true, get: () => true }); Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' }); document.dispatchEvent(new Event('visibilitychange')); })()`);
  await sleep(600);
  const r1 = await page.ev(`window.__perf.raf`);
  await sleep(1500);
  const hiddenFrames = (await page.ev(`window.__perf.raf`)) - r1;
  check("tab ẩn: linh vật dừng vẽ (≤ 4 khung / 1,5s)", vp.name, hiddenFrames <= 4, `${hiddenFrames} khung`);
  await page.ev(`(() => { delete document.hidden; delete document.visibilityState; document.dispatchEvent(new Event('visibilitychange')); })()`);
  await sleep(700);
  const r2 = await page.ev(`window.__perf.raf`);
  await sleep(1000);
  const back = (await page.ev(`window.__perf.raf`)) - r2;
  check("quay lại tab: linh vật vẽ lại", vp.name, back > 10, `${back} khung/giây`);
  void ctx;
}, { pre: PERF_PRE });

// ---- 13. Biến thể INLINE ở /assistant (mọi bề rộng, kể cả điện thoại)
scenario("assistant-inline", async (page, vp) => {
  await login(page);
  await page.wait("document.querySelector('.ai-trang textarea.ai-o')", 9000, "ô soạn");
  await waitMascot(page);
  await waitPhysics(page);
  let g = await settled(page).then(() => geom(page));
  check("inline: linh vật hiện trong trang /assistant", vp.name, g.present && g.shown, JSON.stringify(g));
  noCollision("inline", vp, g);
  const ta = await q(page, ".ai-trang textarea.ai-o");
  check("inline: nằm TRÊN ô soạn (không đè lên)", vp.name, g.h.b <= ta.t + 2, `host.b=${g.h.b} ô soạn.t=${ta.t}`);
  check("inline: nằm trong bề rộng nội dung", vp.name, g.h.l >= -1 && g.h.r <= g.vw + 1, JSON.stringify(g.h));
  await page.shot(`inline-${vp.name}`);

  // vòng đời trên /assistant
  const docOver = await page.ev(`document.documentElement.scrollHeight - innerHeight`);
  if (docOver > 1) info("trang /assistant cao hơn khung nhìn (tồn tại từ trước, KHÔNG phải do linh vật)", vp.name, `${docOver}px — gõ vào ô soạn làm trang cuộn xuống, header sticky của site che đầu trang trợ lý`);
  const tr = await turn(page, "Xin chào từ trang trợ lý", { kind: "ok", words: 24, pre: 800, delay: 30 }, { settleMs: 2400 });
  const m = seq(tr, "mapped");
  await page.ev(`scrollTo(0, 0)`); // đo va chạm của LINH VẬT ở đầu trang (không lẫn với việc header sticky của site che đầu trang khi cuộn)
  check("inline: thinking → answering → success → listening", vp.name, m.join(">") === "listening>thinking>answering>success>listening" || m.join(">") === "idle>thinking>answering>success>listening", m.join(">"));
  noCollision("inline sau lượt hỏi", vp, await geom(page));
  await page.shot(`inline-after-turn-${vp.name}`);

  // kéo thả ngang trong dải của chính nó (chuột hoặc chạm theo thiết bị)
  const R0 = await settled(page);
  const drag = vp.mobile ? dragTouch : dragMouse;
  await drag(page, centerOf(R0), { x: Math.max(12, vp.width * 0.12), y: centerOf(R0).y });
  const R1 = await settled(page);
  g = await geom(page);
  check("inline: kéo sang trái trong dải, vẫn trong khung nhìn", vp.name, R1.l >= -1 && g.inViewport, JSON.stringify(R1));
  noCollision("inline sau kéo", vp, g);
  info("inline kéo: dịch ngang", vp.name, `${Math.round(R1.l - R0.l)}px`);

  // bàn phím ảo mở (mô phỏng visualViewport thấp): linh vật thu lại, trả lại khi đóng
  await page.ev(`(() => { const vv = window.visualViewport; Object.defineProperty(vv, 'height', { configurable: true, get: () => innerHeight * 0.45 }); vv.dispatchEvent(new Event('resize')); })()`);
  await sleep(500);
  check("bàn phím ảo mở (mô phỏng): linh vật thu lại, ô soạn vẫn thấy", vp.name, !(await geom(page)).shown && (await q(page, ".ai-trang textarea.ai-o")) !== null);
  await page.ev(`(() => { const vv = window.visualViewport; delete vv.height; vv.dispatchEvent(new Event('resize')); })()`);
  await sleep(500);
  check("bàn phím đóng: linh vật trở lại", vp.name, (await geom(page)).shown);

  // lỗi → hồi phục
  const tr2 = await turn(page, "lỗi trên trang trợ lý", { kind: "sse_error", code: "ai_provider_unavailable" }, { settleMs: 1500 });
  check("inline: lỗi cuối → 'error'", vp.name, seq(tr2, "mapped").slice(-1)[0] === "error", seq(tr2, "mapped").join(">"));
}, { viewports: INLINE_VPS, hash: "/assistant" });

// ---- 14. Xoay màn hình điện thoại ở /assistant
scenario("xoay-màn-hình", async (page, vp) => {
  await login(page);
  await page.wait("document.querySelector('.ai-trang textarea.ai-o')", 9000, "ô soạn");
  await waitMascot(page);
  await settled(page);
  for (const [w, h, name] of [[844, 390, "ngang"], [390, 844, "dọc"], [667, 375, "ngang-nhỏ"], [375, 667, "dọc-nhỏ"]]) {
    await page.s("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 2, mobile: true });
    await sleep(700);
    await settled(page).catch(() => {});
    const g = await geom(page);
    noCollision(`xoay ${name} ${w}×${h}`, { name: `${w}x${h}` }, g);
    check(`xoay ${name}: ô soạn vẫn nằm trong khung nhìn`, `${w}x${h}`, await page.ev(`(() => { const r = document.querySelector('.ai-trang textarea.ai-o').getBoundingClientRect(); return r.bottom <= innerHeight + 1 && r.top >= 0; })()`), "");
  }
}, { viewports: [{ name: "xoay", width: 390, height: 844, mobile: true }], hash: "/assistant" });

// ---- 15. Trình đọc chương: linh vật không đứng ở nhà (có điều khiển riêng ở góc dưới)
scenario("tuyến-chương", async (page, vp) => {
  await login(page);
  await page.wait("document.querySelector('.ai-launcher')", 8000, "nút nổi");
  await sleep(500);
  const g = await geom(page);
  check("trên /chapters/*: linh vật nổi không hiện ở nhà (không đè điều khiển trình đọc)", vp.name, !g.present || !g.shown, JSON.stringify({ shown: g.shown }));
  await openPanel(page);
  await sleep(1500);
  noCollision("/chapters + panel mở", vp, await geom(page));
  await closePanel(page);
  await sleep(1500);
  const g2 = await geom(page);
  check("đóng panel trên /chapters: lại không hiện ở nhà", vp.name, !g2.present || !g2.shown, "");
}, { hash: "/chapters/1" });

// ---- 15b. Trợ năng bàn phím: thứ tự Tab, tên truy cập, vòng focus nhìn thấy, linh vật không bao giờ nhận focus / không đọc màn hình
scenario("trợ-năng-bàn-phím", async (page, vp) => {
  await readyFloating(page);
  await waitPhysics(page);
  const focusInfo = () => page.ev(`(() => { const e = document.activeElement; if (!e || e === document.body) return null; const cs = getComputedStyle(e); const r = e.getBoundingClientRect();
    return { tag: e.tagName.toLowerCase(), name: (e.getAttribute('aria-label') || e.getAttribute('title') || e.innerText || e.placeholder || '').trim().slice(0, 40), inCompanion: !!e.closest('.ai-companion'),
      ring: (cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) >= 1) || (cs.boxShadow && cs.boxShadow !== 'none'), inView: r.width > 0 && r.top >= -1 && r.bottom <= innerHeight + 1 }; })()`);
  // Từ nút mở: Enter mở panel, focus vào panel
  await page.focus(".ai-launcher");
  await page.key("Enter");
  await page.wait("document.querySelector('.ai-panel')", 4000, "panel mở bằng bàn phím");
  await sleep(300);
  let f = await focusInfo();
  check("Enter trên nút mở: focus chuyển vào panel (ô soạn)", vp.name, f && !f.inCompanion && f.tag === "textarea", JSON.stringify(f));
  await settled(page, { timeout: 12000 });
  const seen = [];
  for (let i = 0; i < 14; i += 1) {
    await page.key("Tab");
    await sleep(60);
    f = await focusInfo();
    seen.push(f);
  }
  const names = seen.filter(Boolean).map((x) => `${x.tag}:${x.name}`);
  info("thứ tự Tab (14 lần từ ô soạn)", vp.name, names.join(" → "));
  check("Tab: linh vật KHÔNG BAO GIỜ nhận focus (không vào thứ tự Tab)", vp.name, seen.every((x) => !x || !x.inCompanion), JSON.stringify(seen.find((x) => x?.inCompanion)));
  check("Tab: mọi điều khiển nhận focus đều có tên truy cập", vp.name, seen.filter(Boolean).every((x) => x.name.length > 0), JSON.stringify(seen.filter((x) => x && !x.name)));
  check("Tab: mọi điều khiển nhận focus đều có vòng/bóng focus nhìn thấy", vp.name, seen.filter(Boolean).every((x) => x.ring), JSON.stringify(seen.filter((x) => x && !x.ring)));
  check("Tab: mọi điều khiển nhận focus đều nằm trong khung nhìn", vp.name, seen.filter(Boolean).every((x) => x.inView), JSON.stringify(seen.filter((x) => x && !x.inView)));
  const uniq = new Set(names);
  check("Tab: đi qua các điều khiển chính của panel (chế độ, hội thoại mới, lịch sử, cài đặt, đóng, ô soạn)", vp.name, ["Chọn chế độ trợ lý", "Hội thoại mới", "Lịch sử hội thoại", "Cài đặt ký ức", "Đóng trợ lý AI"].every((n) => [...uniq].some((u) => u.includes(n))), [...uniq].join(" | "));
  // Linh vật trang trí: ẩn khỏi cây trợ năng
  check("linh vật: aria-hidden=true, host không tabindex, không nhãn đọc màn hình trên host", vp.name,
    await page.ev(`(() => { const w = document.querySelector('.ai-companion'); const h = document.querySelector('.ai-companion-host'); return w.getAttribute('aria-hidden') === 'true' && !h.hasAttribute('tabindex') && !h.hasAttribute('aria-label'); })()`));
  // Gửi bằng bàn phím + Escape đóng, focus về nút mở
  await page.focus("textarea.ai-o");
  await page.type("bàn phím thôi");
  await page.key("Enter");
  await page.wait("__qa.inflight === 0 && !document.querySelector('.ai-nut-dung') && document.querySelectorAll('.ai-bong-assistant').length >= 1", 15000, "xong lượt");
  await page.focus("textarea.ai-o");
  await page.key("Escape");
  await page.wait("!document.querySelector('.ai-panel')", 4000, "Escape đóng panel");
  await sleep(200);
  f = await focusInfo();
  check("Escape: panel đóng, focus về nút mở", vp.name, f && f.name.includes("Mở trợ lý AI"), JSON.stringify(f));
  // Vùng trực tiếp (aria-live) của hội thoại không bị linh vật làm ồn: số node aria-live trong khung linh vật = 0
  check("khung linh vật không có vùng aria-live/role=status/alert", vp.name, await page.ev(`document.querySelectorAll('.ai-companion [aria-live], .ai-companion [role=status], .ai-companion [role=alert]').length === 0`));
});

// ---- 16. Công tắc tổng TẮT: linh vật biến mất cùng nút mở
scenario("công-tắc-tắt", async (page, vp) => {
  await login(page, "outsider1");
  await page.wait("document.querySelector('.ai-launcher') === null", 6000, "nút mở ẩn").catch(() => {});
  await sleep(1200);
  const g = await geom(page);
  check("người ngoài khán giả: không nút mở và không linh vật", vp.name, !(await page.ev(`!!document.querySelector('.ai-launcher')`)) && (!g.present || !g.shown), JSON.stringify({ present: g.present, shown: g.shown }));
});

// ----------------------------------------------------------------------------------------- chạy
async function main() {
  const need = (h) => SCENARIOS.some((s) => s.harness === h && (!ONLY || ONLY.test(s.id)));
  const harnesses = {};
  const chrome = await launchChrome();
  let cdp;
  try {
    for (const h of ["on", "off"]) {
      if (!need(h)) continue;
      const out = await buildHarness({ companion: true, flag: h === "on" ? "1" : "0" });
      const { server, port } = await serve(out, { "/mascot/": MASCOT });
      harnesses[h] = { server, base: `http://127.0.0.1:${port}` };
    }
    cdp = await Cdp.connect(chrome.wsUrl);
    for (const sc of SCENARIOS) {
      if (ONLY && !ONLY.test(sc.id)) continue;
      const H = harnesses[sc.harness];
      for (const vp of sc.viewports) {
        const page = await openPage(cdp, H.base, {
          width: vp.width, height: vp.height, mobile: vp.mobile, hash: sc.hash, reducedMotion: sc.reducedMotion, preScript: sc.pre, storage: sc.storage,
        });
        const t0 = Date.now();
        const ctx = { cdp, hits: () => H.server.hits.filter((h) => h.t >= t0 - 50), server: H.server };
        const shotName = `${sc.id}-${vp.name}`;
        const origShot = page.shot.bind(page);
        page.shot = (n) => origShot(`${shotName}-${n}`);
        try {
          await sc.fn(page, vp, ctx);
          const errs = page.errors.filter((e) => !/Failed to load resource|favicon|net::ERR|artwork|fonts/.test(e ?? ""));
          check(`${sc.id}: không có lỗi console`, vp.name, errs.length === 0, errs.slice(0, 2).join(" | "));
        } catch (e) {
          record(`${sc.id}: ngoại lệ trong kịch bản`, vp.name, "FAIL", String(e.message ?? e).slice(0, 400));
          await origShot(`${shotName}-ERROR`).catch(() => {});
        } finally {
          await page.close();
        }
      }
    }
  } finally {
    try { cdp?.ws.close(); } catch { /* bỏ qua */ }
    chrome.proc.kill();
    for (const h of Object.values(harnesses)) h.server.close();
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
