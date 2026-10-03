/**
 * QA bản dựng Next THẬT (`next build` + `next start`) với Chrome headless: layout/header/footer/định tuyến/chunk lười/CSS thật của Fanfic
 * World, API thay bằng máy chủ giả chèn vào trang (`real/inject.ts`, `NEXT_PUBLIC_API_BASE=http://qa.local` — không có gì đi ra mạng).
 *
 *   # dựng trước (cờ chỉ là biến lúc BUILD), mỗi biến thể một thư mục kết quả:
 *   NEXT_PUBLIC_API_BASE=http://qa.local NEXT_PUBLIC_AI_ASSISTANT_ENABLED=1 NEXT_PUBLIC_AI_COMPANION_ENABLED=1 npm --prefix web run build
 *   mv web/.next web/.next-on        # biến thể "on"      : trợ lý BẬT + linh vật BẬT
 *   ... ASSISTANT=1 COMPANION=0  -> mv web/.next web/.next-asst   # "asst" : chỉ trợ lý
 *   ... ASSISTANT=0 COMPANION=0  -> mv web/.next web/.next-alloff # "alloff": mặc định production (mọi cờ tắt)
 *
 *   node scripts/qa/ai_ui/run_real.mjs [--only <regex theo id>] [--shots <thư mục>] [--json <tệp>]
 *
 * Mỗi kịch bản chạy trên đúng biến thể nó cần: runner đổi tên `.next-<biến thể>` → `.next`, chạy `next start`, rồi trả lại tên.
 * Không đụng `.next` của người khác: nếu `web/.next` đang tồn tại thì dừng.
 */
import fs from "node:fs";
import net from "node:net";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { buildInject } from "./build.mjs";
import { ONLY, JSON_OUT, results, record, check, info, sleep, launchChrome, Cdp, openPage } from "./lib.mjs";
import {
  DESKTOP, PREFS_KEY, PERF_PRE, centerOf, closePanel, dragMouse, geom, hostRect, mapped, noCollision, openPanel, prefs, q, seq, settled,
  turn, waitMascot, waitPhysics, mouse,
} from "./companion_lib.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
// `QA_WEB_DIR`: chạy cùng bộ đo trên một bản `web/` khác (vd. worktree của `main` để so sánh byte trước/sau).
const WEB = process.env.QA_WEB_DIR ? path.resolve(process.env.QA_WEB_DIR) : path.resolve(here, "../../../web");
const VARIANT_DIR = { on: ".next-on", asst: ".next-asst", alloff: ".next-alloff" }; // mv web/.next web/.next-<biến thể> sau mỗi lần build
const TOKEN = { "fas.token": "tok_alice" };

const SCENARIOS = [];
const scenario = (id, variant, fn, o = {}) => SCENARIOS.push({ id, variant, fn, viewports: o.viewports ?? [DESKTOP], path: o.path ?? "/", storage: { ...TOKEN, ...(o.storage ?? {}) }, pre: o.pre ?? null, reducedMotion: o.reducedMotion ?? false });

const MOBILE_390 = { name: "390", width: 390, height: 844, mobile: true };
const MOBILE_320 = { name: "320", width: 320, height: 568, mobile: true };
const DESKTOP_1024 = { name: "1024", width: 1024, height: 768, mobile: false };

/** Tóm tắt request: JS / mascot / tổng, từ `page.net`. */
function bytesOf(page, { since = 0 } = {}) {
  const list = page.net.list().filter((r) => r.t >= since && r.done && !r.failed && r.status > 0 && r.status < 400);
  const sum = (arr) => arr.reduce((s, r) => s + r.bytes, 0);
  // `js` = JS của TRANG (chunk Next); runtime của linh vật (`/mascot/.../runtime/*.js`) tính vào `mascot`, không tính hai lần.
  const js = list.filter((r) => r.type === "Script" && !r.url.includes("/mascot/"));
  const mascot = list.filter((r) => r.url.includes("/mascot/"));
  return { js, mascot, all: list, jsBytes: sum(js), mascotBytes: sum(mascot), allBytes: sum(list) };
}
const kb = (n) => `${(n / 1024).toFixed(1)} KB`;

// ----------------------------------------------------------------------------------------- 1. byte lúc nghỉ ở các biến thể (cờ tắt = 0 byte linh vật)
const IDLE = {};
for (const variant of ["alloff", "asst", "on"]) {
  scenario(`byte-idle-${variant}`, variant, async (page, vp) => {
    await sleep(9000); // đủ cho requestIdleCallback (≤4s) + tải lười + physics
    const b = bytesOf(page);
    IDLE[variant] = b;
    info(`${variant}: tải nguội "/" đăng nhập sau 9s`, vp.name, `JS ${b.js.length} tệp ${kb(b.jsBytes)} · linh vật ${b.mascot.length} tệp ${kb(b.mascotBytes)} · tổng ${kb(b.allBytes)}`);
    const hasUi = await page.ev(`!!document.querySelector('.ai-launcher')`);
    if (variant === "alloff") {
      check("mặc định production (mọi cờ tắt): KHÔNG nút nổi AI, KHÔNG linh vật", vp.name, !hasUi && !(await page.ev(`!!document.querySelector('[class*=ai-companion]')`)));
    } else check(`${variant}: nút mở trợ lý AI hiện ở desktop`, vp.name, hasUi);
    if (variant !== "on") {
      check(`${variant}: 0 request tới /mascot/ (0 byte linh vật)`, vp.name, b.mascot.length === 0, b.mascot.map((r) => r.url).join(","));
      // Không script nào ĐÃ TẢI chứa mã linh vật (tìm khoá localStorage + tên runtime trong thân từng script).
      const scan = await page.ev(`(async () => { const urls = performance.getEntriesByType('resource').filter((r) => r.initiatorType === 'script' || r.name.endsWith('.js')).map((r) => r.name); const hits = []; for (const u of urls) { try { const t = await (await fetch(u)).text(); if (t.includes('fas.aiCompanion.v1') || t.includes('InkScout') || t.includes('ink-scout')) hits.push(u.split('/').pop()); } catch {} } return { scanned: urls.length, hits }; })()`);
      check(`${variant}: không script đã tải nào chứa mã linh vật`, vp.name, scan.hits.length === 0, `${scan.hits.join(",")} (đã quét ${scan.scanned})`);
    } else {
      check("on: có tải linh vật lười SAU khi trang xong (manifest + runtime + sprite idle)", vp.name, b.mascot.length >= 3, `${b.mascot.length} tệp`);
      const loadEnd = await page.ev(`performance.timeOrigin + performance.getEntriesByType('navigation')[0].loadEventEnd`);
      const early = b.mascot.filter((r) => r.t < loadEnd);
      check("on: không request linh vật nào TRƯỚC khi trang tải xong", vp.name, early.length === 0, early.map((r) => r.url.split("/").pop()).join(","));
      const alloff = IDLE.alloff, asst = IDLE.asst;
      if (alloff && asst) {
        info("so sánh JS ban đầu: mọi cờ tắt → chỉ trợ lý → trợ lý + linh vật", vp.name, `${kb(alloff.jsBytes)} → ${kb(asst.jsBytes)} → ${kb(b.jsBytes)} (linh vật thêm ${kb(b.jsBytes - asst.jsBytes)} JS + ${kb(b.mascotBytes)} asset)`);
      }
    }
    await page.shot("idle");
  }, { path: "/" });
}

scenario("byte-mobile-on", "on", async (page, vp) => {
  await sleep(7000);
  const b = bytesOf(page);
  info("on: tải nguội '/' trên điện thoại 390×844, đăng nhập", vp.name, `JS ${b.js.length} tệp ${kb(b.jsBytes)} · linh vật ${b.mascot.length} tệp`);
  check("điện thoại ngoài /assistant: 0 request linh vật", vp.name, b.mascot.length === 0, b.mascot.map((r) => r.url).join(","));
  check("điện thoại: không nút nổi, không linh vật nổi", vp.name, !(await page.ev(`!!document.querySelector('.ai-launcher')`)) || (await page.ev(`getComputedStyle(document.querySelector('.ai-launcher')).display === 'none'`)));
  // chunk lười của linh vật KHÔNG được tải trên điện thoại (cổng kiểm media desktop trước khi import)
  const heavy = b.js.filter((r) => /AiCompanion|ink-scout/i.test(r.url));
  const chunkWithCode = await page.ev(`(async () => { const out = []; for (const r of performance.getEntriesByType('resource').filter((x) => x.name.endsWith('.js'))) { try { const t = await (await fetch(r.name)).text(); if (t.includes('fas.aiCompanion.v1')) out.push(r.name.split('/').pop()); } catch {} } return out; })()`);
  check("điện thoại ngoài /assistant: chunk mã linh vật KHÔNG được tải", vp.name, chunkWithCode.length === 0 && heavy.length === 0, chunkWithCode.join(","));
}, { viewports: [MOBILE_390] });

// ----------------------------------------------------------------------------------------- 2. desktop: trang chủ thật + va chạm với header/footer thật
scenario("desktop-thật", "on", async (page, vp) => {
  await page.wait("document.querySelector('.ai-launcher')", 15000, "nút nổi");
  await waitMascot(page);
  await waitPhysics(page);
  let g = await settled(page).then(() => geom(page));
  check("trang thật: linh vật hiện, đứng bên trái nút mở", vp.name, g.present && g.shown, JSON.stringify(g));
  noCollision("trang thật (nghỉ)", vp, g);
  const L = await q(page, ".ai-launcher");
  const header = await q(page, ".site-header");
  info("hộp thật", vp.name, `header ${JSON.stringify(header && { t: Math.round(header.t), b: Math.round(header.b) })} nút mở ${JSON.stringify({ l: Math.round(L.l), t: Math.round(L.t) })} linh vật ${JSON.stringify({ l: Math.round(g.h.l), t: Math.round(g.h.t) })}`);
  check("trang thật: linh vật sát bên trái nút mở", vp.name, g.h.r <= L.l + 2 && L.l - g.h.r < 140, `host.r=${g.h.r} launcher.l=${L.l}`);
  await page.shot("home");

  // cuộn trang: nút nổi + linh vật đứng yên theo viewport (fixed)
  await page.ev(`scrollTo(0, 600)`);
  await sleep(500);
  const g2 = await geom(page);
  check("cuộn trang 600px: linh vật không đổi chỗ trong khung nhìn (fixed)", vp.name, Math.abs(g2.h.t - g.h.t) <= 1 && Math.abs(g2.h.l - g.h.l) <= 1, `${g.h.t}→${g2.h.t}`);
  await page.ev(`scrollTo(0, 0)`);

  await page.ev(`__qa.setMini(true)`);
  await sleep(500);
  noCollision("thanh phát thật (.mini) mở", vp, await settled(page).then(() => geom(page)));
  await page.ev(`__qa.setDock(true)`);
  await sleep(500);
  noCollision("thanh phát + Chat Dock", vp, await settled(page).then(() => geom(page)));
  await page.shot("dock-mini");
  await page.ev(`__qa.setDock(false); __qa.setMini(false)`);
  await sleep(500);

  await openPanel(page);
  await sleep(300);
  g = await settled(page, { timeout: 12000 }).then(() => geom(page));
  info("panel mở: chỗ của linh vật", vp.name, g.shown ? `hiện (${Math.round(g.h.l)},${Math.round(g.h.t)})` : "ẨN");
  noCollision("panel thật mở", vp, g);
  if (g.shown) {
    const hd = await q(page, ".site-header");
    check("panel mở: linh vật không lên trên đáy header THẬT", vp.name, g.h.t + g.h.h * 0.1 >= hd.b - 1, `thân.t=${g.h.t + g.h.h * 0.1} header.b=${hd.b}`);
  }
  await page.shot("panel-open");
  await closePanel(page);
  await sleep(300);
  g = await settled(page, { timeout: 12000 }).then(() => geom(page));
  check("đóng panel: linh vật về nhà, không đè gì", vp.name, g.shown && g.hits.length === 0, JSON.stringify(g.hits));
});

// ----------------------------------------------------------------------------------------- 3. vòng đời THẬT trên ứng dụng thật
scenario("trạng-thái-thật", "on", async (page, vp) => {
  await page.wait("document.querySelector('.ai-launcher')", 15000, "nút nổi");
  await waitMascot(page);
  await openPanel(page);
  await settled(page, { timeout: 12000 });
  await page.ev(`__qa.cap = 1000`);
  let tr = await turn(page, "Xin chào", { kind: "ok", words: 24, pre: 1000, delay: 30 });
  let m = seq(tr, "mapped");
  check("thật: thinking → answering → success → listening", vp.name, m.join(">") === "listening>thinking>answering>success>listening", m.join(">"));
  tr = await turn(page, "failover", { kind: "ok", words: 10, pre: 2600, ping: true, delay: 30 });
  m = seq(tr, "mapped");
  check("thật: failover thành công (im lặng 2,6s + ping) KHÔNG nháy lỗi", vp.name, !m.includes("error") && !m.includes("offline") && m.join(">") === "listening>thinking>answering>success>listening", m.join(">"));
  tr = await turn(page, "lỗi", { kind: "sse_error", code: "ai_provider_unavailable" }, { settleMs: 2000 });
  m = seq(tr, "mapped");
  check("thật: lỗi cuối → error (giữ nguyên)", vp.name, m[m.length - 1] === "error" && (await mapped(page)) === "error", m.join(">"));
  await page.ev(`__qa.script.push({ kind: 'hang' })`);
  await page.focus("textarea.ai-o"); await page.type("sẽ bị dừng"); await page.key("Enter");
  await page.wait("document.querySelector('.ai-nut-dung')", 5000, "nút Dừng");
  await sleep(700);
  await page.click(".ai-nut-dung");
  await page.wait("!document.querySelector('.ai-nut-dung')", 5000, "đã dừng");
  await sleep(1200);
  check("thật: Dừng → listening (không success/error)", vp.name, (await mapped(page)) === "listening", String(await mapped(page)));
  await page.shot("states");
});

// ----------------------------------------------------------------------------------------- 4. /assistant thật (layout thật: header + 100dvh)
scenario("assistant-thật", "on", async (page, vp) => {
  await page.wait("document.querySelector('.ai-trang textarea.ai-o')", 15000, "ô soạn /assistant");
  await waitMascot(page);
  await sleep(1200);
  const L = await page.ev(`(() => { const r = (s) => { const e = document.querySelector(s); if (!e) return null; const b = e.getBoundingClientRect(); return { t: Math.round(b.top), b: Math.round(b.bottom), h: Math.round(b.height) }; };
    return { vh: innerHeight, docH: document.documentElement.scrollHeight, header: r('.site-header'), trang: r('.ai-trang'), composer: r('.ai-trang textarea.ai-o'), footer: r('.site-footer'), overflowX: document.documentElement.scrollWidth - innerWidth, scrollY }; })()`);
  info("/assistant thật: bố cục", vp.name, JSON.stringify(L));
  check("/assistant: không tràn ngang", vp.name, L.overflowX <= 0, String(L.overflowX));
  check("/assistant: ô soạn NẰM TRONG khung nhìn ngay khi vào (không phải cuộn trang mới thấy)", vp.name, L.composer && L.composer.b <= L.vh + 1, `ô soạn.bottom=${L.composer?.b} > viewport ${L.vh}`);
  const g = await geom(page);
  check("/assistant: linh vật inline hiện, trong khung nhìn", vp.name, g.present && g.shown && g.inViewport, JSON.stringify({ shown: g.shown, inViewport: g.inViewport }));
  noCollision("/assistant thật", vp, g);
  await page.shot("assistant");
}, { path: "/assistant", viewports: [DESKTOP, DESKTOP_1024, MOBILE_390, MOBILE_320] });

// ----------------------------------------------------------------------------------------- 5. điều hướng phía client: một linh vật duy nhất, không tải lại trang
scenario("điều-hướng-thật", "on", async (page, vp) => {
  await page.wait("document.querySelector('.ai-launcher')", 15000, "nút nổi");
  await waitMascot(page);
  await page.ev(`window.__noReload = 'ok'`); // còn sống = trang KHÔNG bị tải lại (điều hướng client-side thật)
  const count = () => page.ev(`({ wraps: document.querySelectorAll('.ai-companion').length, canvases: document.querySelectorAll('.ai-companion-host canvas').length, inline: !!document.querySelector('.ai-companion-inline'), floating: !!document.querySelector('.ai-companion-floating'), noReload: window.__noReload === 'ok' })`);
  let c = await count();
  check("khởi đầu: đúng 1 linh vật nổi, 1 canvas", vp.name, c.wraps === 1 && c.canvases === 1 && c.floating, JSON.stringify(c));
  // 1) footer → /library (Link thật)
  await page.click("a.footer-link[href='/library']");
  await page.wait("location.pathname === '/library'", 8000, "sang /library");
  await sleep(1200);
  c = await count();
  check("sang /library bằng Link thật: không tải lại trang, vẫn đúng 1 linh vật nổi", vp.name, c.noReload && c.wraps === 1 && c.canvases === 1 && c.floating, JSON.stringify(c));
  // 2) menu tài khoản → /assistant: linh vật nổi nhường chỗ cho bản inline
  await page.click("button.account-link");
  await page.wait("document.querySelector(\"a.menu-item[href='/assistant']\")", 5000, "mục Trợ lý AI trong menu").catch(async () => {
    throw new Error("không thấy mục Trợ lý AI; mục có: " + JSON.stringify(await page.ev("[...document.querySelectorAll('.menu-panel a, .menu-panel button')].map((e) => e.getAttribute('href') || e.innerText)")));
  });
  await page.click("a.menu-item[href='/assistant']");
  await page.wait("location.pathname === '/assistant'", 8000, "sang /assistant");
  await page.wait("document.querySelector('.ai-trang textarea.ai-o')", 10000, "trang trợ lý");
  await waitMascot(page);
  await sleep(800);
  c = await count();
  check("sang /assistant: bản inline thay bản nổi (đúng 1 linh vật, 1 canvas, không tải lại trang)", vp.name, c.noReload && c.wraps === 1 && c.canvases === 1 && c.inline && !c.floating, JSON.stringify(c));
  noCollision("/assistant sau điều hướng client-side", vp, await geom(page));
  await page.shot("assistant-via-menu");
  // 3) logo → trang chủ: bản nổi trở lại
  await page.click("a.brand");
  await page.wait("location.pathname === '/'", 8000, "về trang chủ");
  await page.wait("document.querySelector('.ai-launcher')", 8000, "nút nổi trở lại");
  await waitMascot(page);
  await sleep(800);
  c = await count();
  check("về trang chủ: bản nổi trở lại, đúng 1 linh vật, 1 canvas (không nhân bản qua 3 lần điều hướng)", vp.name, c.noReload && c.wraps === 1 && c.canvases === 1 && c.floating && !c.inline, JSON.stringify(c));
  const errs = page.errors.filter((e) => !/qa\.local|Failed to load resource|404|net::ERR/.test(e ?? ""));
  check("điều hướng: không lỗi console (ngoài API giả 404)", vp.name, errs.length === 0, errs.slice(0, 2).join(" | "));
});

// ----------------------------------------------------------------------------------------- 6. kéo thả + nhớ vị trí qua tải lại (hydration thật)
scenario("kéo-thả-thật", "on", async (page, vp) => {
  await page.wait("document.querySelector('.ai-launcher')", 15000, "nút nổi");
  await waitMascot(page);
  await waitPhysics(page);
  const R0 = await settled(page);
  await dragMouse(page, centerOf(R0), { x: centerOf(R0).x - 300, y: centerOf(R0).y });
  const R1 = await settled(page);
  check("kéo sang trái 300px: đứng đúng chỗ thả (±16px)", vp.name, Math.abs(R1.l - (R0.l - 300)) <= 16, `${R0.l} → ${R1.l}`);
  const p = await prefs(page);
  check("vị trí được nhớ", vp.name, p && typeof p.homeX === "number" && p.homeX < -250, JSON.stringify(p));
  await page.s("Page.reload");
  await page.wait("window.__qa && document.readyState === 'complete'", 15000, "tải lại");
  await page.wait("document.querySelector('.ai-launcher')", 15000, "nút nổi");
  await waitMascot(page);
  const R2 = await settled(page);
  check("tải lại (hydration thật): đứng đúng chỗ đã nhớ (±2px)", vp.name, Math.abs(R2.l - R1.l) <= 2 && Math.abs(R2.t - R1.t) <= 2, `${R1.l},${R1.t} → ${R2.l},${R2.t}`);
  await mouse(page, "mouseMoved", 5, 5);
  void PREFS_KEY; void PERF_PRE; void hostRect;
});

// ----------------------------------------------------------------------------------------- chạy
function freePort() {
  return new Promise((resolve, reject) => {
    const s = net.createServer();
    s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => resolve(port)); });
    s.on("error", reject);
  });
}

async function startNext(variant) {
  const from = path.join(WEB, VARIANT_DIR[variant]);
  const to = path.join(WEB, ".next");
  if (!fs.existsSync(from)) throw new Error(`thiếu bản dựng ${from} — dựng trước (xem đầu tệp)`);
  if (fs.existsSync(to)) throw new Error("web/.next đang tồn tại — đổi tên/dọn nó trước khi chạy QA thật");
  fs.renameSync(from, to);
  const port = await freePort();
  const proc = spawn(process.execPath, [path.join(WEB, "node_modules/next/dist/bin/next"), "start", "-p", String(port), "-H", "127.0.0.1"], {
    cwd: WEB, env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1" }, stdio: "ignore",
  });
  const base = `http://127.0.0.1:${port}`;
  let ok = false;
  for (let i = 0; i < 300 && !ok; i += 1) {
    try { ok = (await fetch(base + "/")).status < 500; } catch { await sleep(200); }
  }
  if (!ok) { proc.kill(); fs.renameSync(to, from); throw new Error(`next start (${variant}) không lên`); }
  return { base, stop: async () => { proc.kill(); await sleep(800); try { fs.renameSync(to, from); } catch (e) { console.error("không trả được tên .next:", e.message); } } };
}

async function main() {
  const inject = fs.readFileSync(await buildInject(), "utf8");
  const chrome = await launchChrome();
  let cdp;
  try {
    cdp = await Cdp.connect(chrome.wsUrl);
    for (const variant of ["alloff", "asst", "on"]) {
      const list = SCENARIOS.filter((s) => s.variant === variant && (!ONLY || ONLY.test(s.id)));
      if (!list.length) continue;
      const srv = await startNext(variant);
      try {
        for (const sc of list) {
          for (const vp of sc.viewports) {
            const page = await openPage(cdp, srv.base, {
              width: vp.width, height: vp.height, mobile: vp.mobile, hash: "", url: srv.base + sc.path, reducedMotion: sc.reducedMotion,
              preScript: inject + "\n" + (sc.pre ?? ""), storage: sc.storage, network: true,
            });
            const shotName = `${sc.id}-${vp.name}`;
            const origShot = page.shot.bind(page);
            page.shot = (n) => origShot(`${shotName}-${n}`);
            try {
              await sc.fn(page, vp);
              const errs = page.errors.filter((e) => !/qa\.local|Failed to load resource|favicon|net::ERR|404|artwork|fonts/.test(e ?? ""));
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
        await srv.stop();
      }
    }
  } finally {
    try { cdp?.ws.close(); } catch { /* bỏ qua */ }
    chrome.proc.kill();
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
