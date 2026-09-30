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

import { COMPANION_STATES, isOfflineError, mapCompanionState } from "../src/components/ai/companion/companionState.ts";
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

test("co: mac dinh TAT, AI tat -> companion tat, tat thi khong co chunk", () => {
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
  assert.match(c, /isDesktop && !onAssistantPage && available === true/);
  assert.match(c, /variant === "inline" && keyboardOpen/, "ban phim mo -> thu lai");
  assert.match(c, /setPaused\(!visible\)/, "an -> dung dong ho hoat anh");
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
