/*
 * Ink Scout — linh vật đi cùng Trợ lý AI (docs/ai/INK_SCOUT_COMPANION.md).
 *
 * Hàm thuần (ánh xạ trạng thái, hình học chỗ ngồi) và bộ điều phối được import
 * TRỰC TIẾP (.ts qua strip-types) và chạy với runtime giả; phần React/CSS/bộ
 * asset được khoá bằng kiểm tĩnh như các bài admin/AI khác.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { COMPANION_STATES, isOfflineError, isOnceState, mapCompanionState } from "../src/components/ai/companion/companionState.ts";
import { CompanionDirector } from "../src/components/ai/companion/companionDirector.ts";
import { boundsFor, computeSeat } from "../src/components/ai/companion/companionGeometry.ts";

const read = (rel) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
const codeOnly = (src) => src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
const COMP = "../src/components/ai/companion/";
const companionFiles = () =>
  readdirSync(fileURLToPath(new URL(COMP, import.meta.url))).map((f) => [f, read(COMP + f)]);

const base = {
  available: true, networkOffline: false, open: false, streaming: false, hasStreamText: false,
  mode: "general", errorCode: null, hovering: false, flash: null,
};
const st = (patch) => mapCompanionState({ ...base, ...patch });

// ------------------------------------------------------------------ ánh xạ trạng thái

test("anh xa trang thai that cua tro ly -> Ink Scout (moi truong hop trong bang)", () => {
  assert.equal(st({}), "idle");
  assert.equal(st({ hovering: true }), "hover");
  assert.equal(st({ open: true }), "listening");
  assert.equal(st({ open: true, hovering: true }), "listening", "hover chi co nghia o vi tri nha");
  assert.equal(st({ open: true, streaming: true }), "thinking", "da gui, chua co token dau");
  assert.equal(st({ open: true, streaming: true, mode: "story" }), "searching", "Truyen: may chu dang truy chuong");
  assert.equal(st({ open: true, streaming: true, webSearch: true }), "searching");
  assert.equal(st({ open: true, streaming: true, hasStreamText: true }), "answering");
  assert.equal(st({ open: true, streaming: true, hasStreamText: true, mode: "writer" }), "writing");
  assert.equal(st({ open: true, flash: "success" }), "success");
  assert.equal(st({ open: true, errorCode: "ai_provider_unavailable" }), "error");
  assert.equal(st({ open: true, errorCode: "ai_rate_limited" }), "error");
  assert.equal(st({ open: true, errorCode: "network_error" }), "offline");
  assert.equal(st({ available: false }), "offline");
  assert.equal(st({ networkOffline: true, open: true, streaming: true }), "offline");
  assert.equal(st({ open: false, errorCode: "ai_provider_unavailable" }), "idle", "panel dong -> nghi");
  assert.equal(st({ available: null }), "idle", "chua biet availability -> khong ket luan offline");
  assert.ok(isOfflineError("ai_no_provider") && !isOfflineError("ai_budget_exhausted"));
  for (const s of new Set([st({}), st({ open: true }), st({ available: false })])) assert.ok(COMPANION_STATES.includes(s));
});

test("dung tao sinh: dung lai -> listening (khong flash thanh cong)", () => {
  assert.equal(st({ open: true, streaming: false, flash: null }), "listening");
  const src = codeOnly(read(COMP + "AiCompanion.tsx"));
  assert.match(src, /last\.status === "complete"/, "chi 'complete' moi bat success");
  assert.ok(!/status === "stopped"[^;]*setFlash\("success"\)/.test(src));
});

// ------------------------------------------------------------------ failover phía máy chủ

/** Chay DUNG bo tach SSE that (`lib/ai/sse.ts`) tren byte cua mot luot, roi ap cung luat
 *  `AiProvider` dung cho cac truong ma companion doc (streaming / streamingText / error /
 *  messages[-1].status). Tra ve chuoi trang thai Ink Scout theo tung su kien. */
async function songTrangThai(raw, { mode = "general" } = {}) {
  const { tachKhungSse, dienDichKhungAi } = await import("../src/lib/ai/sse.ts");
  let s = { streaming: true, text: "", error: null, last: null };
  const seq = [st({ open: true, streaming: true, mode })];
  const { khung } = tachKhungSse(raw);
  for (const k of khung) {
    const ev = dienDichKhungAi(k);
    if (!ev) continue;
    if (ev.type === "delta") s = { ...s, text: s.text + ev.text };
    else if (ev.type === "done") s = { ...s, streaming: false, last: ev.status };
    else if (ev.type === "error") s = { ...s, streaming: false, error: ev.code, last: "error" };
    seq.push(st({ open: true, mode, streaming: s.streaming, hasStreamText: !!s.text, errorCode: s.error,
                  flash: !s.streaming && s.last === "complete" ? "success" : null }));
  }
  return seq;
}

test("failover thanh cong phia may chu KHONG BAO GIO hien loi (byte giong luot that T4 canary)", async () => {
  // Slot dau tra 404/503 -> may chu chuyen slot TRUOC token dau; client chi thay meta/delta/usage/done
  // (+ nhip tim). Khong co su kien nao mang thong tin slot/loi trung gian.
  const raw = 'event: meta\ndata: {"message_id":"m1","conversation_id":"c1"}\n\n'
    + ": ping\n\n"
    + 'event: delta\ndata: {"text":"Xanh"}\n\n'
    + 'event: delta\ndata: {"text":" dương"}\n\n'
    + 'event: usage\ndata: {"input_tokens":245,"output_tokens":2,"used_today":900,"limit_today":30000}\n\n'
    + 'event: done\ndata: {"status":"complete"}\n\n';
  const seq = await songTrangThai(raw);
  assert.ok(!seq.includes("error") && !seq.includes("offline"), seq.join(" > "));
  assert.equal(seq[0], "thinking");
  assert.ok(seq.includes("answering"));
  assert.equal(seq.at(-1), "success");
});

test("searching CHI truoc `meta` o che do Truyen; sau meta (cho provider/failover) la thinking (Codex #1)", () => {
  assert.equal(st({ open: true, streaming: true, mode: "story" }), "searching", "may chu dang truy chuong");
  assert.equal(st({ open: true, streaming: true, mode: "story", responseStarted: true }), "thinking");
  assert.equal(st({ open: true, streaming: true, mode: "general", responseStarted: false }), "thinking");
  const src = codeOnly(read("../src/components/ai/AiProvider.tsx"));
  assert.match(src, /ev\.type === "meta"\)[\s\S]{0,200}responseStarted: true/, "meta that dat responseStarted");
  assert.match(src, /streaming: true, streamingText: "", responseStarted: false/, "luot moi dat lai");
});

test("mot-lan (success/hover) da phat xong thi KHONG phat lai khi React chua doi desired (Codex #2)", async () => {
  const rt = fakeRuntime();
  const d = new CompanionDirector(rt);
  d.setState("success");
  await tick(); await tick();
  d.notifyRuntimeState("idle"); // runtime tu ve `after` sau khi phat xong
  await tick(); await tick();
  assert.equal(rt.calls.filter((c) => c[0] === "state" && c[1] === "success").length, 1);
  d.setState("listening");
  await tick(); await tick();
  assert.equal(rt.calls.at(-1)[1], "listening");
  d.setState("success"); // luot moi xong -> duoc phat lai
  await tick(); await tick();
  assert.equal(rt.calls.filter((c) => c[0] === "state" && c[1] === "success").length, 2);
  const dirSrc = read(COMP + "companionDirector.ts");
  const once = COMPANION_STATES.filter((s) => isOnceState(s));
  assert.deepEqual(once, ["hover", "success"]);
  for (const s of once) assert.match(dirSrc, new RegExp(`ONCE_STATES[^;]*"${s}"`), `ONCE_STATES thieu ${s}`);
});

test("giam chuyen dong ap TRUOC khi hien; listener go khi huy; linh vat khong bat con tro (Codex #3/#4/#5)", () => {
  const src = codeOnly(read(COMP + "AiCompanion.tsx"));
  assert.match(src, /if \(reducedRef\.current\) await rt\.setReducedMotion\(true\);[\s\S]{0,60}setReady\(true\)/);
  assert.match(src, /ai-companion-cho/);
  assert.match(src, /removeEventListener\("statechange"/);
  assert.match(src, /removeEventListener\("animationcomplete"/);
  assert.ok(!/onPointerEnter/.test(src), "host khong bat con tro");
  assert.match(src, /querySelector\("\.ai-launcher"\)/, "hover lay tu nut mo tro ly");
  const css = codeOnly(read("../src/components/ai/ai.css"));
  assert.ok(!/ai-companion[^{]*\{[^}]*pointer-events:\s*auto/.test(css), "khong co vung chet bat con tro");
  assert.match(css, /\.ai-companion-cho \.ai-companion-host \{ visibility: hidden; \}/);
});

test("su kien la (vd 'fallback' tuong lai) va nhip tim bi bo qua, khong thanh loi", async () => {
  const raw = 'event: fallback\ndata: {"slot":"gemini-02"}\n\n: ping\n\n'
    + 'event: delta\ndata: {"text":"OK"}\n\nevent: done\ndata: {"status":"complete"}\n\n';
  const seq = await songTrangThai(raw);
  assert.deepEqual([...new Set(seq)], ["thinking", "answering", "success"]);
});

test("chi loi CUOI CUNG cua may chu (moi slot deu hong) moi hien error", async () => {
  const raw = 'event: meta\ndata: {"message_id":"m2","conversation_id":"c1"}\n\n'
    + 'event: usage\ndata: {"input_tokens":0,"output_tokens":0}\n\n'
    + 'event: error\ndata: {"code":"ai_provider_unavailable","message":"x"}\n\n';
  assert.equal((await songTrangThai(raw)).at(-1), "error");
  const off = 'event: error\ndata: {"code":"ai_no_provider","message":"x"}\n\n';
  assert.equal((await songTrangThai(off)).at(-1), "offline");
});

test("AiProvider chi dat `error` o nhanh su kien error / ngoai le, va xoa no khi gui luot moi", () => {
  const src = codeOnly(read("../src/components/ai/AiProvider.tsx"));
  const at = [...src.matchAll(/error: \{ code:/g)].map((m) => m.index);
  assert.ok(at.length >= 1);
  for (const i of at) {
    const truoc = src.slice(Math.max(0, i - 900), i);
    assert.ok(/ev\.type === "error"|catch \(e\)/.test(truoc), "error chi dat khi may chu bao loi that");
  }
  assert.match(src, /streaming: true, streamingText: "", responseStarted: false, error: null/, "luot moi xoa loi cu");
  for (const t of ["meta", "delta", "done", "citations"]) {
    const m = src.match(new RegExp(`ev\\.type === "${t}"\\)[\\s\\S]*?\\} else if`));
    assert.ok(m && !/error: \{/.test(m[0]), `nhanh ${t} khong duoc dat error`);
  }
});

// ------------------------------------------------------------------ bộ điều phối

function fakeRuntime({ reduced = false } = {}) {
  const calls = [];
  let pending = [];
  const rt = {
    calls, position: { x: 0, y: 0 }, destroyed: false,
    get reducedMotion() { return reduced; },
    setState: async (s) => { calls.push(["state", s]); await Promise.resolve(); return true; },
    transition: (name, opts) => new Promise((resolve) => { calls.push(["move", name, opts]); pending.push(resolve); }),
    setReducedMotion: async () => {},
    applyPosition() { calls.push(["pos", { ...this.position }]); },
    destroy() { this.destroyed = true; pending.forEach((r) => r({ cancelled: true })); pending = []; },
    finishMove() { const r = pending.shift(); r?.({ cancelled: false }); },
  };
  return rt;
}
const tick = () => new Promise((r) => setTimeout(r, 0));

test("trang thai moi nhat thang: doi don dap chi ap cai cuoi, khong cat ngang di chuyen", async () => {
  const rt = fakeRuntime();
  const d = new CompanionDirector(rt);
  d.goSeat(-120, -300);                 // bat dau nhay len panel (dang bay)
  d.setState("listening");
  d.setState("thinking");
  d.setState("answering");              // 3 trang thai trong luc dang bay
  await tick();
  assert.deepEqual(rt.calls.filter((c) => c[0] === "state"), [], "khong setState khi dang di chuyen");
  rt.finishMove();                      // nhay xong
  await tick(); await tick();
  assert.deepEqual(rt.calls.filter((c) => c[0] === "state").map((c) => c[1]), ["answering"], "chi trang thai CUOI");
});

test("dang ngoi tren panel + chi lang nghe -> ngoi (sit-down), lam viec -> dung day", async () => {
  const rt = fakeRuntime();
  const d = new CompanionDirector(rt);
  d.setState("listening");
  d.goSeat(-100, -280);
  await tick(); rt.finishMove();        // jump-onto-panel xong
  await tick(); await tick();
  assert.deepEqual(rt.calls.filter((c) => c[0] === "move").map((c) => c[1]), ["jump-onto-panel", "sit-down"]);
  rt.finishMove(); await tick();
  d.setState("thinking"); await tick(); await tick();
  assert.deepEqual(rt.calls.at(-1), ["state", "thinking"]);
  d.goHome(); await tick();
  assert.equal(rt.calls.at(-1)[1], "return-home", "dang dung (khong ngoi) -> ve nha thang");
});

test("mo/dong panel lien tuc: chi di toi DICH cuoi cung", async () => {
  const rt = fakeRuntime();
  const d = new CompanionDirector(rt);
  d.goSeat(-100, -280);
  d.goHome(); d.goSeat(-100, -280); d.goHome();   // bam mo/dong 4 lan trong luc dang nhay
  await tick(); rt.finishMove(); await tick(); await tick();
  const moves = rt.calls.filter((c) => c[0] === "move").map((c) => c[1]);
  assert.deepEqual(moves, ["jump-onto-panel", "return-home"], "khong phat lai tung lan bam");
});

test("giam chuyen dong: doi cho tuc thi, khong goi transition (khong tai poster)", async () => {
  const rt = fakeRuntime({ reduced: true });
  const d = new CompanionDirector(rt);
  d.setState("listening");
  d.goSeat(-90, -250);
  await tick(); await tick();
  assert.equal(rt.calls.filter((c) => c[0] === "move").length, 0);
  assert.deepEqual(rt.position, { x: -90, y: -250 });
  assert.deepEqual(rt.calls.at(-1), ["state", "listening"]);
});

test("don dep: destroy huy runtime va dung vong lap", async () => {
  const rt = fakeRuntime();
  const d = new CompanionDirector(rt);
  d.goSeat(-100, -280);
  d.destroy();
  await tick(); await tick();
  d.setState("answering"); await tick();
  assert.ok(rt.destroyed);
  assert.equal(rt.calls.filter((c) => c[0] === "state").length, 0);
});

test("relocate khi dang ngoi yen: doi vi tri ngay, khong phat hoat anh", async () => {
  const rt = fakeRuntime();
  const d = new CompanionDirector(rt);
  d.goSeat(-100, -280); await tick(); rt.finishMove(); await tick(); await tick();
  const moves = rt.calls.filter((c) => c[0] === "move").length;
  d.relocate(-160, -260);
  assert.equal(rt.calls.filter((c) => c[0] === "move").length, moves);
  assert.deepEqual(d.currentPlace, { kind: "seat", x: -160, y: -260 });
});

// ------------------------------------------------------------------ vị trí trên panel

const home = { left: 1430, top: 716, width: 96, height: 96 };
test("cho ngoi: mep TREN panel, ngoai panel, duoi navbar", () => {
  const panel = { left: 1204, top: 212, width: 380, height: 600 };
  const s = computeSeat({ home, panel, navBottom: 72, viewportWidth: 1600, size: 96 });
  assert.equal(s.where, "top");
  const top = home.top + s.y, left = home.left + s.x;
  assert.ok(top + 96 <= panel.top + 96 * 0.15, "chan cham mep, than ngoai panel (khong che chu/nut)");
  assert.ok(top >= 72, "khong len tren navbar");
  assert.ok(left >= panel.left && left + 96 <= panel.left + panel.width / 2, "phia trai, xa nut Dong goc phai");
});

test("man thap: dung canh trai panel; khong con cho an toan -> null (an di)", () => {
  const low = { left: 620, top: 80, width: 380, height: 600 };
  const s = computeSeat({ home: { ...home, left: 850, top: 584 }, panel: low, navBottom: 72, viewportWidth: 1024, size: 96 });
  assert.equal(s.where, "side");
  assert.ok(850 + s.x + 96 <= low.left, "ben trai panel, khong de len panel");
  const cramped = { left: 40, top: 80, width: 380, height: 600 };
  assert.equal(computeSeat({ home, panel: cramped, navBottom: 72, viewportWidth: 460, size: 96 }), null);
  const b = boundsFor(home, 1600, 72);
  assert.ok(b.top < 0 && b.left < 0 && b.bottom === 0);
});

// ------------------------------------------------------------------ cờ + tính năng

test("co: mac dinh TAT, AI tat -> companion tat, tat thi loader null (khong tai chunk)", () => {
  const f = read("../src/lib/features.ts");
  assert.match(f, /AI_COMPANION_ENABLED =\s*AI_ASSISTANT_ENABLED && process\.env\.NEXT_PUBLIC_AI_COMPANION_ENABLED === "1"/);
  const gate = codeOnly(read(COMP + "AiCompanionGate.tsx"));
  assert.match(gate, /AI_COMPANION_ENABLED\s*\?\s*\(\) => import\("\.\/AiCompanion"\)/);
  assert.match(gate, /:\s*null;/);
  assert.match(gate, /ai\?\.enabled/, "tro ly tat -> khong tai ma linh vat");
  assert.ok(!/next\/dynamic/.test(gate));
  assert.match(read("../src/app/layout.tsx"), /<AiCompanionGate variant="floating" \/>/);
  assert.match(read("../src/app/assistant/page.tsx"), /<AiCompanionGate variant="inline" \/>/);
});

test("khong tu mo tro ly, khong am thanh, khong focus, khong lat nguoc nhan vat", () => {
  for (const [f, src] of companionFiles()) {
    const code = codeOnly(src);
    assert.ok(!/openAssistant|ensureReady|enterFullscreen/.test(code), `${f}: tu mo tro ly`);
    assert.ok(!/new Audio|AudioContext|\.play\(\)/.test(code), `${f}: am thanh`);
    assert.ok(!/tabIndex|\.focus\(/.test(code), `${f}: lay focus`);
    assert.ok(!/scaleX\(\s*-|scale\(\s*-1|rotateY\(\s*180|matrix\(\s*-1/.test(code), `${f}: lat ngang`);
  }
  const css = read("../src/components/ai/ai.css");
  const khoi = css.slice(css.indexOf("Ink Scout (cờ NEXT_PUBLIC_AI_COMPANION_ENABLED)"));
  assert.ok(!/scaleX\(\s*-|scale\(\s*-1|rotateY\(\s*180/.test(khoi));
  const runtime = read("../public/mascot/ink-scout/runtime/ink-scout.js");
  assert.ok(!/scaleX\(\s*-|scale\(\s*-1|rotateY\(\s*180/.test(runtime), "runtime khong lat");
  assert.match(codeOnly(read(COMP + "AiCompanion.tsx")), /aria-hidden="true"/);
});

test("mobile: khong linh vat noi o <=1023px; /assistant dung ban inline trong luong noi dung", () => {
  const css = read("../src/components/ai/ai.css");
  assert.match(css, /@media \(max-width: 1023px\) \{ \.ai-companion-floating \{ display: none; \} \}/);
  const c = codeOnly(read(COMP + "AiCompanion.tsx"));
  assert.match(c, /isDesktop && !onAssistantPage && launcherVisible/);
  assert.match(c, /const launcherVisible = ai\.availability !== false && !\(ai\.availability && !ai\.availability\.enabled\)/,
    "cung dieu kien voi AiLauncher (availability null = chua hoi may chu, van hien)");
  assert.match(c, /variant === "inline" && keyboardOpen/, "ban phim mo -> thu lai");
  assert.match(c, /setPaused\(!visible\)/, "an -> dung dong ho hoat anh");
  assert.match(c, /const home: Rect = rectOf\(wrap\)/, "nha = khung bao co dinh");
  assert.ok(!/r\.left - rt\.position\.x/.test(c), "khong suy nha tu host - runtime.position (nhan doi cho ngoi)");
  assert.match(css, /z-index: 54;/, "duoi Chat Dock (55) va panel/nut AI (56)");
});

test("giam chuyen dong: prefers-reduced-motion luon thang + tuy chon nguoi dung duoc luu", () => {
  const prefs = codeOnly(read(COMP + "companionPrefs.ts"));
  assert.match(prefs, /prefers-reduced-motion: reduce/);
  assert.match(prefs, /localStorage/);
  assert.ok((prefs.match(/try \{/g) || []).length >= 3, "moi truy cap luu tru deu boc try/catch");
  const c = codeOnly(read(COMP + "AiCompanion.tsx"));
  assert.match(c, /const reduced = prefs\.reducedMotion \|\| systemReduced/);
  assert.match(read(COMP + "CompanionSettings.tsx"), /Ẩn Ink Scout/);
});

// ------------------------------------------------------------------ bộ asset web

test("bo con web: chi WebP + runtime + manifest, trong ngan sach, runtime nguyen ban", () => {
  const root = fileURLToPath(new URL("../public/mascot/ink-scout/", import.meta.url));
  const walk = (d) => readdirSync(d).flatMap((n) => {
    const p = d + "/" + n;
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
  const files = walk(root.replace(/[\\/]$/, "")).map((p) => p.slice(root.length - 1).replace(/\\/g, "/").replace(/^\//, ""));
  for (const f of files) {
    assert.ok(/\.webp$/.test(f) || ["manifest.json", "SUBSET.json", "runtime/ink-scout.js"].includes(f), `tep khong duoc phep: ${f}`);
  }
  const inv = JSON.parse(read("../public/mascot/ink-scout/SUBSET.json"));
  assert.ok(inv.totalBytes <= inv.budgetBytes && inv.budgetBytes <= 2_700_000);
  assert.ok(inv.totalBytes < inv.packBytes * 0.05, "duoi 5% bo goc");
  const rt = inv.files.find((x) => x.path === "runtime/ink-scout.js");
  const sha = createHash("sha256").update(readFileSync(root + "runtime/ink-scout.js")).digest("hex");
  assert.equal(sha, rt.sha256);
  const man = JSON.parse(read("../public/mascot/ink-scout/manifest.json"));
  assert.deepEqual(Object.keys(man.states).sort(), [...COMPANION_STATES].sort());
  for (const t of ["hop-left", "hop-right", "walk", "jump-onto-panel", "sit-down", "stand-up", "peek-out", "return-home"]) {
    assert.ok(man.transitions[t] && man.animations[man.transitions[t].animation], t);
  }
  const refs = [...Object.values(man.states).flatMap((s) => [s.image, s.static]),
    ...Object.values(man.animations).flatMap((a) => [a.image, a.poster]), ...Object.values(man.poses).map((p) => p.webp)];
  for (const r of refs) assert.ok(files.includes(r), `manifest tro toi tep khong co: ${r}`);
  assert.ok(!JSON.stringify(man).includes(".png"), "manifest web khong tro toi PNG");
});
