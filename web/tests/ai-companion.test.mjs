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
import {
  boundsFor, computeSeat, inlineBoundsFor, judgeLanding, mascotBody, panelSurfaces, rectsIntersect,
} from "../src/components/ai/companion/companionGeometry.ts";
import { HOME_X_MIN, sanitizeHomeX } from "../src/components/ai/companion/companionPrefs.ts";

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
  // Hết lượt hôm nay không phải một lỗi: linh vật nghỉ (sleepy) tới lúc đặt lại, không làm mặt bối rối. Quá nhanh vẫn là "error" (lượt
  // bị từ chối vì chính thao tác vừa rồi), còn lỗi thật (nhà cung cấp hết/ngắt) luôn là "error".
  assert.equal(st({ open: true, errorCode: "ai_budget_exhausted" }), "offline");
  assert.equal(st({ open: true, errorCode: "ai_provider_interrupted" }), "error");
  assert.ok(isOfflineError("ai_no_provider") && isOfflineError("ai_budget_exhausted") && !isOfflineError("ai_rate_limited"));
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

test("giam chuyen dong ap TRUOC khi hien; listener go khi huy; con tro CHI o host khi da san sang (Codex #3/#4/#5 + keo tha)", () => {
  const src = codeOnly(read(COMP + "AiCompanion.tsx"));
  assert.match(src, /if \(reducedRef\.current\) await rt\.setReducedMotion\(true\);[\s\S]{0,60}setReady\(true\)/);
  assert.match(src, /ai-companion-cho/);
  for (const ev of ["statechange", "animationcomplete", "pickup", "movementcomplete"]) {
    assert.match(src, new RegExp(`removeEventListener\\("${ev}"`), `go listener ${ev} khi huy`);
    assert.match(src, new RegExp(`addEventListener\\("${ev}"`), `co listener ${ev}`);
  }
  for (const ev of ["pointerenter", "pointerleave"]) {
    assert.match(src, new RegExp(`removeEventListener\\("${ev}"`), `go listener ${ev} khi huy`);
  }
  assert.ok(!/onPointer|onMouse|onTouch|onClick/.test(src), "khong gan su kien con tro qua JSX: moi listener deu duoc go bang tay");
  assert.match(src, /querySelector\("\.ai-launcher"\)/, "hover van lay tu nut mo tro ly");
  const css = codeOnly(read("../src/components/ai/ai.css"));
  // Moi `pointer-events: auto` cua linh vat phai nam duoi `.ai-companion-live` (physics da gan + dang hien) — truoc do 0 px bi chan.
  const autos = css.split("}").filter((b) => /ai-companion/.test(b) && /pointer-events:\s*auto/.test(b));
  assert.ok(autos.length >= 1, "host nhan con tro de keo tha");
  for (const b of autos) assert.match(b, /\.ai-companion-live \.ai-companion-host/, "pointer-events:auto CHI duoi .ai-companion-live");
  assert.match(css, /\.ai-companion \{ pointer-events: none; \}/, "khung bao khong bat con tro");
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
    // `!ketThuc`: luong dong SACH ma khong co khung done/error (mat ket noi giua chung) cung la loi that, khong phai gia.
    assert.ok(/ev\.type === "error"|catch \(e\)|!ketThuc/.test(truoc), "error chi dat khi may chu bao loi that");
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
    calls, position: { x: 0, y: 0 }, home: { x: 0, y: 0 }, destroyed: false,
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
  assert.equal(b.right, 0, "chi duoc di sang TRAI nha: khong bao gio chui xuong duoi nut mo tro ly / Chat Dock o goc phai");
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

test("co TAT = 0 byte linh vat trong JS ban dau: AiControls KHONG import tinh gi tu companion/ (muc cai dat nap luoi qua import())", () => {
  const controls = codeOnly(read("../src/components/ai/AiControls.tsx"));
  assert.ok(!/from "\.\/companion\//.test(controls), "import tinh keo companionPrefs vao chunk chung du co tat (do ~0,4 KB gzip tren MOI trang)");
  assert.match(controls, /AI_COMPANION_ENABLED\s*\?\s*\(\) => import\("\.\/companion\/CompanionSettings"\)/);
  assert.match(controls, /\{AI_COMPANION_ENABLED \? <CompanionSettingsSlot \/> : null\}/);
  // Khong file nao NGOAI companion/ (va layout/assistant gate) import gia tri tu companion/ — chi cong + loader lười.
  for (const rel of ["../src/components/ai/AiPanel.tsx", "../src/components/ai/AiLauncher.tsx", "../src/components/ai/AiComposer.tsx", "../src/components/ai/AiConversation.tsx", "../src/components/ai/AiProvider.tsx"]) {
    assert.ok(!/from "\.\/companion\//.test(codeOnly(read(rel))), `${rel} khong duoc import tinh tu companion/`);
  }
});

test("cong linh vat noi: chi tai chunk khi man hinh desktop >=1024px (dien thoai ngoai /assistant khong bao gio can no)", () => {
  const gate = codeOnly(read(COMP + "AiCompanionGate.tsx"));
  assert.match(gate, /\(min-width: 1024px\)/);
  assert.match(gate, /useSyncExternalStore\(subscribeDesktop, isDesktopNow, isDesktopServer\)/);
  assert.match(gate, /variant === "inline" \|\|\s*\(desktop && ai\.eligible/, "inline (/assistant) khong phu thuoc media; nổi thi co");
  // Cung moc voi CSS an nut mo/panel.
  assert.match(read("../src/components/ai/ai.css"), /@media \(max-width: 1023px\) \{ \.ai-launcher \{ display: none; \} \}/);
});

test("panel noi: Escape dong (khong khi popover cai dat mo / dang go IME), tra focus ve nut mo; mo bang fade chi opacity (khong doi hop → linh vat do cho ngoi dung)", () => {
  const panel = codeOnly(read("../src/components/ai/AiPanel.tsx"));
  assert.match(panel, /e\.key !== "Escape" \|\| e\.defaultPrevented \|\| e\.nativeEvent\.isComposing/);
  assert.match(panel, /querySelector\("\.ai-caidat"\)/);
  assert.match(panel, /focusNutMoAi/);
  const css = read("../src/components/ai/ai.css");
  const fade = css.match(/@keyframes ai-panel-hien \{([^}]*\}[^}]*)\}/);
  assert.ok(fade, "co keyframes ai-panel-hien");
  assert.ok(!/transform|scale|translate/.test(fade[1]), "fade chi opacity: transform lam hop panel doi trong luc hien → chỗ ngồi của linh vật sai vài px");
  assert.match(css, /@media \(prefers-reduced-motion: reduce\) \{ \.ai-panel \{ animation: none; \} \}/);
});

test("khong tu mo tro ly, khong am thanh, khong focus, khong lat nguoc nhan vat", () => {
  for (const [f, src] of companionFiles()) {
    const code = codeOnly(src);
    assert.ok(!/openAssistant|ensureReady|enterFullscreen/.test(code), `${f}: tu mo tro ly`);
    assert.ok(!/new Audio|AudioContext|\.play\(\)/.test(code), `${f}: am thanh`);
    assert.ok(!/tabIndex|\.focus\(/.test(code), `${f}: lay focus`);
    // physics tu dat tabindex=0 + aria-label len host: linh vat chi duoc co tabindex AM, khong tabindex duong va khong nhan doc man hinh.
    assert.ok(!/tabindex["'],\s*["']\d/.test(code) && !/tabindex["'],\s*["']0/.test(code), `${f}: tabindex duong`);
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
  assert.match(c, /setPaused\(!visible \|\| quiet\)/, "an hoac yen lang -> dung dong ho hoat anh");
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

const RUNTIME_FILES = ["ink-scout.js", "ink-scout-walk-rig.js", "ink-scout-physics.js", "ink-scout-presence.js"];

test("bo con web v1.3.0: chi WebP + 4 runtime + manifest + manh rig PNG cua pack, trong ngan sach, runtime nguyen ban", () => {
  const root = fileURLToPath(new URL("../public/mascot/ink-scout/", import.meta.url));
  const walk = (d) => readdirSync(d).flatMap((n) => {
    const p = d + "/" + n;
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
  const files = walk(root.replace(/[\\/]$/, "")).map((p) => p.slice(root.length - 1).replace(/\\/g, "/").replace(/^\//, ""));
  const allowed = (f) =>
    /\.webp$/.test(f) ||
    ["manifest.json", "SUBSET.json", ...RUNTIME_FILES.map((r) => "runtime/" + r)].includes(f) ||
    // Manh rig di bo: pack CHI xuat PNG (khong co WebP) — chep nguyen, khong ma hoa lai.
    /^animations\/walk-(left|right)\/rig\/(body|far-arm|far-boot|far-shin|far-thigh|near-arm|near-boot|near-shin|near-thigh)\.png$/.test(f);
  for (const f of files) assert.ok(allowed(f), `tep khong duoc phep: ${f}`);
  const inv = JSON.parse(read("../public/mascot/ink-scout/SUBSET.json"));
  assert.ok(inv.totalBytes <= inv.budgetBytes && inv.budgetBytes <= 4_100_000, "ngan sach bo con");
  assert.ok(inv.totalBytes < inv.packBytes * 0.05, "duoi 5% bo goc");
  for (const name of RUNTIME_FILES) {
    const rt = inv.files.find((x) => x.path === "runtime/" + name);
    assert.ok(rt, `SUBSET.json thieu runtime/${name}`);
    const sha = createHash("sha256").update(readFileSync(root + "runtime/" + name)).digest("hex");
    assert.equal(sha, rt.sha256, `runtime/${name} nguyen ban tung byte`);
  }
  const man = JSON.parse(read("../public/mascot/ink-scout/manifest.json"));
  assert.deepEqual(Object.keys(man.states).sort(), [...COMPANION_STATES].sort());
  for (const t of ["hop-left", "hop-right", "walk", "jump-onto-panel", "sit-down", "stand-up", "peek-out", "return-home", "walk-left", "walk-right"]) {
    assert.ok(man.transitions[t] && man.animations[man.transitions[t].animation], t);
  }
  const rigParts = ["walk-left", "walk-right"].flatMap((n) => Object.values(man.animations[n].rig.parts).map((p) => p.image));
  assert.equal(rigParts.length, 18, "2 huong x 9 manh");
  const refs = [...Object.values(man.states).flatMap((s) => [s.image, s.static]),
    ...Object.values(man.animations).flatMap((a) => [a.image, a.poster]), ...Object.values(man.poses).map((p) => p.webp),
    ...Object.values(man.physics.poses), ...rigParts];
  for (const r of refs) assert.ok(files.includes(r), `manifest tro toi tep khong co: ${r}`);
  assert.deepEqual(Object.keys(man.physics.poses).sort(), ["jump-airborne", "jump-anticipation", "jump-landing", "picked-up"]);
  assert.deepEqual(man.physics.walkCycles, { left: "walk-left", right: "walk-right" });
  // PNG chi duoc nhac toi DUY NHAT trong mo ta rig (mot tep cua pack khong co ban WebP).
  // (`dedupedAliases` chi la ghi chu khu trung, khong phai tham chieu tai.)
  const mt = JSON.stringify({ ...man, dedupedAliases: null, animations: { ...man.animations, "walk-left": { ...man.animations["walk-left"], rig: null }, "walk-right": { ...man.animations["walk-right"], rig: null } } });
  assert.ok(!mt.includes(".png"), "manifest web khong tro toi PNG ngoai manh rig");
  assert.ok(!/scaleX\(\s*-|scale\(\s*-1|rotateY\(\s*180/.test(RUNTIME_FILES.map((r) => read("../public/mascot/ink-scout/runtime/" + r)).join("\n")), "runtime khong lat");
});

test("bo nap: phien ban ?v= khop manifest + SUBSET; thu tu player -> rig -> physics; presence nap luoi; script khong chan", () => {
  const loader = codeOnly(read(COMP + "inkScoutLoader.ts"));
  const man = JSON.parse(read("../public/mascot/ink-scout/manifest.json"));
  const m = loader.match(/INK_SCOUT_VERSION = "([^"]+)"/);
  assert.ok(m, "co hang INK_SCOUT_VERSION");
  assert.equal(m[1], man.version, "runtime moi + manifest cu bi cam (HANDOFF §8): phien ban bo nap = manifest");
  assert.equal(m[1], "1.3.0");
  assert.match(loader, /el\.async = false/, "tai song song, THUC THI dung thu tu chen");
  const iPlayer = loader.indexOf('loadScript("ink-scout.js")');
  const iRig = loader.indexOf('loadScript("ink-scout-walk-rig.js")');
  const iPhysics = loader.indexOf('loadScript("ink-scout-physics.js")');
  assert.ok(iPlayer > 0 && iPlayer < iRig && iRig < iPhysics, "thu tu player -> walk-rig -> physics");
  assert.match(loader, /\.catch\(\(\) => null\)/, "thieu physics/rig -> van chay bang player co ban");
  assert.ok(!/ink-scout-presence\.js/.test(loader.slice(0, loader.indexOf("export function loadInkScoutPresence"))), "presence KHONG nap cung player");
  assert.match(loader, /manifest\.json\?v=/);
});

// ------------------------------------------------------------------ kéo thả, vị trí nhớ, phán xử nơi thả

test("vi tri nho: chi nhan so huu han <= 0 trong can; gia tri rac/cu luon ve null (khong bao gio dua linh vat ra ngoai man hinh)", () => {
  assert.equal(sanitizeHomeX(-120), -120);
  assert.equal(sanitizeHomeX(-120.4), -120);
  assert.equal(sanitizeHomeX(0), null, "0 = mac dinh");
  assert.equal(sanitizeHomeX(-0.2), null);
  for (const bad of [NaN, Infinity, -Infinity, 1, 80, HOME_X_MIN - 1, -1e9, "-120", null, undefined, {}, [], true]) {
    assert.equal(sanitizeHomeX(bad), null, String(bad));
  }
  assert.equal(sanitizeHomeX(HOME_X_MIN), HOME_X_MIN);
});

const panelBox = { left: 1204, top: 212, width: 380, height: 600 };
const seatTop = computeSeat({ home, panel: panelBox, navBottom: 72, viewportWidth: 1600, size: 96 });

test("mat phang dap: chi mep TREN panel (kieu top); toa do goc host; 'side'/khong co cho -> khong mat phang", () => {
  const s = panelSurfaces(seatTop, panelBox, home);
  assert.deepEqual(s, [{ left: panelBox.left - home.left, right: panelBox.left + panelBox.width - home.left, y: seatTop.y }]);
  assert.deepEqual(panelSurfaces({ ...seatTop, where: "side" }, panelBox, home), []);
  assert.deepEqual(panelSurfaces(null, panelBox, home), []);
  assert.deepEqual(panelSurfaces(seatTop, null, home), [], "panel dong -> khong co mat phang");
});

test("bien keo tha: floating chi sang TRAI nha, khong len tren navbar; inline trong dai noi dung cua no", () => {
  const b = boundsFor(home, 1600, 72);
  assert.equal(b.right, 0);
  assert.ok(home.left + b.left >= 0 && home.left + b.left <= 16, "khong ra ngoai mep trai man hinh");
  assert.ok(home.top + b.top >= 72, "khong len tren day thanh dieu huong");
  const i = inlineBoundsFor({ left: 0, top: 120, width: 390, height: 80 }, 72);
  assert.deepEqual(i, { left: -159, right: 159, top: -43, bottom: 0 });
  assert.deepEqual(inlineBoundsFor({ left: 0, top: 0, width: 50, height: 80 }, 72), { left: -0, right: 0, top: -43, bottom: 0 }, "dai hep hon linh vat -> khong am");
});

test("phan xu noi tha: dap dung mep panel -> cho ngoi; than chong vung cam -> cuu; san hop le -> nho", () => {
  const launcher = { left: 1532, top: 724, width: 52, height: 52 };
  const dock = { left: 1100, top: 560, width: 320, height: 380 };
  const common = { size: 96, home, seat: seatTop, protectedRects: [panelBox, launcher, dock] };
  // dap dung len mep tren panel (y = seat.y, x trong dai panel)
  assert.deepEqual(judgeLanding({ ...common, x: seatTop.x + 40, y: seatTop.y }), { kind: "seat" });
  assert.deepEqual(judgeLanding({ ...common, x: seatTop.x + 40, y: seatTop.y + 3 }), { kind: "seat" }, "sai so < 6 px van la ngoi");
  // tha vao long panel (roi xuong san nam duoi panel) -> cuu ve cho ngoi (panel dang mo, co cho)
  assert.deepEqual(judgeLanding({ ...common, x: -120, y: 0 }), { kind: "rescue", to: "seat" });
  // panel dong (khong co cho ngoi): chong Chat Dock -> ve nha
  assert.deepEqual(judgeLanding({ size: 96, home, seat: null, protectedRects: [launcher, dock], x: -330, y: 0 }), { kind: "rescue", to: "home" });
  // san hop le, xa moi vung cam -> nho lam nha (lam tron)
  assert.deepEqual(judgeLanding({ size: 96, home, seat: null, protectedRects: [launcher, dock], x: -600.4, y: 0 }), { kind: "floor", x: -600 });
  assert.deepEqual(judgeLanding({ size: 96, home, seat: null, protectedRects: [], x: 0, y: 0 }), { kind: "floor", x: 0 });
});

test("hinh hoc: than linh vat bo phan trong suot; giao hop co khoang dem", () => {
  const body = mascotBody(home, 0, 0, 96);
  assert.ok(body.width < 96 && body.height < 96 && body.left > home.left && body.top > home.top);
  assert.equal(rectsIntersect({ left: 0, top: 0, width: 10, height: 10 }, { left: 10, top: 0, width: 10, height: 10 }), false);
  assert.equal(rectsIntersect({ left: 0, top: 0, width: 10, height: 10 }, { left: 10, top: 0, width: 10, height: 10 }, 2), true);
});

test("director + nguoi dung dang cam: khong setState/transition (khong giat khoi tay); tha ra thi ap trang thai MOI NHAT mot lan", async () => {
  const rt = fakeRuntime();
  const d = new CompanionDirector(rt);
  d.setState("listening"); await tick(); await tick();
  const before = rt.calls.length;
  d.hold(true);
  d.setState("thinking"); d.setState("answering"); d.goSeat(-120, -300); d.goHome();
  await tick(); await tick();
  assert.equal(rt.calls.length, before, "dang cam: runtime khong nhan lenh nao");
  assert.equal(d.isHeld, true);
  d.hold(false);
  await tick(); await tick();
  const after = rt.calls.slice(before);
  assert.deepEqual(after.filter((c) => c[0] === "state").map((c) => c[1]), ["answering"], "chi trang thai CUOI");
  assert.equal(after.filter((c) => c[0] === "move").length, 0, "dich cuoi la nha va dang o nha -> khong di dau");
});

test("director: relocate khi dang bi cam chi ghi nhan dich moi, ap khi tha; settle 'free' lam moi dich deu di chuyen that", async () => {
  const rt = fakeRuntime();
  const d = new CompanionDirector(rt);
  d.goSeat(-100, -280); await tick(); rt.finishMove(); await tick(); await tick();
  const pos0 = { ...rt.position };
  d.hold(true);
  d.relocate(-160, -260);
  assert.deepEqual(rt.position, pos0, "khong dich truc tiep khi dang cam");
  d.hold(false); await tick(); await tick();
  assert.equal(rt.calls.filter((c) => c[0] === "move").at(-1)[1], "jump-onto-panel", "ap dich moi khi tha");
  rt.finishMove(); await tick(); await tick();
  // Nguoi dung tha vao vung cam: place khong xac dinh -> goSeat(cung toa do cu) van phai nhay that.
  d.settle({ kind: "free" });
  const moves = rt.calls.filter((c) => c[0] === "move").length;
  d.goSeat(-160, -260); await tick();
  assert.equal(rt.calls.filter((c) => c[0] === "move").length, moves + 1);
});

test("director.rehome: nha doi khi dang BAN ap trang thai dau tien -> van doi (khong bo qua), ngay khi ranh; khong hoat anh", async () => {
  // Loi that do o QA trinh duyet: vi tri da nho khong duoc ap luc tai trang vi director dang ban `setState('idle')`.
  const rt = fakeRuntime();
  const d = new CompanionDirector(rt);
  d.setState("idle");                    // pump bat dau, dang cho runtime.setState
  assert.equal(d.busy, true);
  rt.home = { x: -320, y: 0 };
  d.rehome();
  d.goHome();
  assert.deepEqual(rt.position, { x: 0, y: 0 }, "dang ban: chua dich");
  await tick(); await tick();
  assert.deepEqual(rt.position, { x: -320, y: 0 }, "ranh -> dang o nha thi doi ngay");
  assert.equal(rt.calls.filter((c) => c[0] === "move").length, 0, "khong phat hoat anh di chuyen");
  // Dang ranh: doi tuc thi.
  rt.home = { x: -100, y: 0 };
  d.rehome();
  assert.deepEqual(rt.position, { x: -100, y: 0 });
  // Dang ngoi o panel: KHONG keo linh vat khoi cho ngoi; lan ve nha ke tiep moi toi nha moi.
  d.goSeat(-90, -250); await tick(); rt.finishMove(); await tick(); await tick();
  const seatPos = { ...rt.position };
  rt.home = { x: -500, y: 0 };
  d.rehome();
  assert.deepEqual(rt.position, seatPos);
  // Dang bi cam: khong dich.
  d.settle({ kind: "home" });
  d.hold(true);
  rt.position = { x: -42, y: -10 };
  d.rehome();
  assert.deepEqual(rt.position, { x: -42, y: -10 });
  d.destroy();
  rt.home = { x: -9, y: 0 };
  d.rehome();
  assert.deepEqual(rt.position, { x: -42, y: -10 }, "da huy: khong dong den runtime");
});

test("director: giam chuyen dong ve 'nha' dung rt.home (vi tri nguoi dung da dat), khong ve 0,0", async () => {
  const rt = fakeRuntime({ reduced: true });
  rt.home = { x: -340, y: 0 };
  const d = new CompanionDirector(rt);
  d.goSeat(-90, -250); await tick(); await tick();
  d.goHome(); await tick(); await tick();
  assert.deepEqual(rt.position, { x: -340, y: 0 });
});

test("AiCompanion: vi tri chi duoc nho khi THA hop le; physics gan luoi; presence chi khi tuong tac; yen lang dung ve", () => {
  const src = codeOnly(read(COMP + "AiCompanion.tsx"));
  assert.ok((src.match(/writeCompanionPrefs\(/g) || []).length === 1, "chi MOT cho ghi vi tri: luc nguoi dung tha o san hop le");
  assert.match(src, /judgeLanding\(/);
  assert.match(src, /protectedRectsNow\(/);
  assert.match(src, /requestIdleCallback\(attachPhysics/, "physics gan khi trinh duyet ranh");
  assert.match(src, /\(pointer: coarse\)/, "man hinh cam ung gan ngay (khong co hover de bao truoc)");
  assert.match(src, /setAttribute\("tabindex", "-1"\)/);
  assert.match(src, /removeAttribute\("aria-label"\)/, "linh vat trang tri: khong nhan doc man hinh");
  assert.match(src, /loadInkScoutPresence\(\)/);
  assert.match(src, /addEventListener\("pointerenter", enter\)/, "presence nap khi con tro vao linh vat");
  assert.match(src, /p\.enabled = false;[\s\S]{0,80}p\.stop\(\);[\s\S]{0,40}p\.reset\(\)/, "roi linh vat -> dung vong ve lien tuc cua presence");
  assert.match(src, /IDLE_QUIET_MS = 6000/);
  assert.match(src, /const quiet = quietEligible && firedKey === quietKey/);
  assert.match(src, /clearInterval\(watchdog\)/, "luoi an toan khong ro ri hen gio");
  // Khong nghe `window`/`document` truc tiep ngoai cac hook co cleanup (resize/online/offline da co trong file goc).
  assert.ok(!/document\.addEventListener|window\.addEventListener\("(pointer|mouse|touch|key)/.test(src), "khong nghe con tro/ban phim toan trang");
});
