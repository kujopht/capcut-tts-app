/*
 * INK SCOUT — VÒNG ĐỜI RUNTIME (không cần trình duyệt): bước cố định 60 Hz độc lập tần số màn hình, không xoáy ốc chết khi đứng hình,
 * tạm dừng khi tab ẩn/mất tiêu điểm, và `destroy()` gỡ SẠCH rAF + bộ nghe + QA hook, kể cả sau nhiều vòng tạo/huỷ.
 * Dùng window/document/canvas giả (canvas "null-object": mọi lệnh vẽ là no-op).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { loadModule } from "./helpers/loadGameCore.mjs";

const { createRuntime } = await loadModule("src/game/inkscout/platform/runtime.ts");
const { MemoryStore } = await loadModule("src/game/inkscout/core/index.ts");

// ---------------------------------------------------------------- môi trường giả
function nullCtx() {
  const fn = () => proxy;
  const proxy = new Proxy(fn, {
    get: (_t, k) => (k === "addColorStop" ? () => {} : k === Symbol.toPrimitive ? () => 0 : proxy),
    set: () => true,
    apply: () => proxy,
  });
  return proxy;
}
function fakeCanvas() {
  return { width: 0, height: 0, getContext: () => nullCtx() };
}

function installEnv() {
  const winHandlers = new Map();
  const docHandlers = new Map();
  const mk = (m) => ({
    addEventListener(t, f) {
      if (!m.has(t)) m.set(t, new Set());
      m.get(t).add(f);
    },
    removeEventListener(t, f) {
      m.get(t)?.delete(f);
    },
  });
  const count = (m) => [...m.values()].reduce((n, s) => n + s.size, 0);
  const win = { ...mk(winHandlers), localStorage: undefined };
  const doc = { ...mk(docHandlers), hidden: false, createElement: (t) => (t === "canvas" ? fakeCanvas() : {}) };
  let nextId = 0;
  const queue = new Map();
  let cancelled = 0;
  globalThis.window = win;
  globalThis.document = doc;
  globalThis.Image = class {
    constructor() {
      this.complete = false;
      this.naturalWidth = 0;
    }
  };
  globalThis.requestAnimationFrame = (cb) => {
    nextId += 1;
    queue.set(nextId, cb);
    return nextId;
  };
  globalThis.cancelAnimationFrame = (id) => {
    cancelled += 1;
    queue.delete(id);
  };
  let t = 1000;
  return {
    win, doc, winHandlers, docHandlers,
    listeners: () => count(winHandlers) + count(docHandlers),
    pending: () => queue.size,
    cancelled: () => cancelled,
    /** Chạy một "khung hiển thị" sau `ms` mili-giây. */
    pump(ms) {
      t += ms;
      const cbs = [...queue.entries()];
      queue.clear();
      for (const [, cb] of cbs) cb(t);
    },
    /** Gọi lại một callback đã bị huỷ (mô phỏng khung đã xếp hàng lúc destroy). */
    staleCallbacks: () => cbsSnapshot(queue),
  };
}
function cbsSnapshot(queue) {
  return [...queue.values()];
}

function make(env, extra = {}) {
  const ui = [];
  const store = new MemoryStore();
  return createRuntime({ canvas: fakeCanvas(), store, onUi: (s) => ui.push(s), seed: 7, ...extra }).then((rt) => ({ rt, ui, store }));
}

test("bước cố định 60 Hz: 60 Hz, 120 Hz và 144 Hz đều ra ≈ 60 bước mô phỏng mỗi giây", async () => {
  for (const hz of [60, 120, 144]) {
    const env = installEnv();
    const { rt } = await make(env);
    const s0 = rt.stats().steps;
    const dt = 1000 / hz;
    for (let i = 0; i < hz * 2; i += 1) env.pump(dt); // 2 giây
    const steps = rt.stats().steps - s0;
    assert.ok(Math.abs(steps - 120) <= 2, `${hz} Hz ⇒ ${steps} bước trong 2 s (mong 120)`);
    rt.destroy();
  }
});

test("đứng hình lâu (tab nền/CPU tắc) không gây xoáy ốc chết: mỗi khung tối đa 5 bước", async () => {
  const env = installEnv();
  const { rt } = await make(env);
  const s0 = rt.stats().steps;
  env.pump(5000);
  assert.ok(rt.stats().steps - s0 <= 5, `một khung 5 s chỉ được chạy ≤ 5 bước, thực tế ${rt.stats().steps - s0}`);
  rt.destroy();
});

test("tab ẩn / mất tiêu điểm ⇒ tự tạm dừng (không bước nữa, đã lưu); tiếp tục thì chạy lại, không dồn thời gian", async () => {
  const env = installEnv();
  const { rt, store } = await make(env);
  for (let i = 0; i < 30; i += 1) env.pump(16.7);
  env.doc.hidden = true;
  for (const f of env.docHandlers.get("visibilitychange")) f();
  const frozen = rt.stats().steps;
  for (let i = 0; i < 60; i += 1) env.pump(16.7);
  assert.equal(rt.stats().steps, frozen, "đang ẩn ⇒ đóng băng");
  assert.ok((await store.load()) !== null, "tạm dừng ⇒ đã lưu");
  env.doc.hidden = false;
  rt.resume();
  env.pump(16.7);
  const s1 = rt.stats().steps;
  env.pump(16.7);
  env.pump(16.7);
  assert.ok(rt.stats().steps > s1 && rt.stats().steps - frozen <= 8, "tiếp tục không xả lại thời gian đã ngừng");
  // mất tiêu điểm
  for (const f of env.winHandlers.get("blur")) f();
  const s2 = rt.stats().steps;
  env.pump(16.7);
  env.pump(16.7);
  assert.equal(rt.stats().steps, s2);
  rt.destroy();
});

test("destroy gỡ SẠCH: rAF đã huỷ, mọi bộ nghe window/document gỡ hết, khung xếp hàng dở không chạy thêm", async () => {
  const env = installEnv();
  const baseline = env.listeners();
  const { rt, store } = await make(env);
  assert.ok(env.listeners() > baseline, "có bộ nghe khi đang chạy");
  assert.equal(rt.stats().rafActive, true);
  assert.equal(rt.stats().instances, 1);
  for (let i = 0; i < 10; i += 1) env.pump(16.7);
  // giữ lại callback đang xếp hàng để thử "khung ma" sau khi huỷ
  const stale = env.staleCallbacks();
  rt.destroy();
  assert.equal(env.listeners(), baseline, "gỡ hết bộ nghe");
  assert.equal(rt.stats().rafActive, false);
  assert.equal(rt.stats().instances, 0);
  assert.ok(env.cancelled() >= 1);
  assert.equal(env.pending(), 0, "không còn rAF chờ");
  const steps = rt.stats().steps;
  for (const cb of stale) cb(99999); // khung ma
  assert.equal(rt.stats().steps, steps, "khung ma không chạy mô phỏng");
  assert.equal(env.pending(), 0, "khung ma không xếp thêm rAF");
  assert.ok((await store.load()) !== null, "destroy lưu lần cuối");
  rt.destroy(); // gọi lần hai an toàn
});

test("40 vòng tạo/huỷ: không tích luỹ bộ nghe, rAF, hay thể hiện", async () => {
  const env = installEnv();
  const baseline = env.listeners();
  for (let i = 0; i < 40; i += 1) {
    const { rt } = await make(env);
    assert.equal(rt.stats().instances, 1, `vòng ${i}: đúng một thể hiện`);
    for (let k = 0; k < 5; k += 1) env.pump(16.7);
    rt.destroy();
    assert.equal(env.listeners(), baseline, `vòng ${i}: còn bộ nghe`);
    assert.equal(env.pending(), 0, `vòng ${i}: còn rAF`);
  }
});

test("UI chỉ nhận cập nhật khi trạng thái rời rạc đổi (không theo từng khung)", async () => {
  const env = installEnv();
  const { rt, ui } = await make(env);
  const n0 = ui.length;
  for (let i = 0; i < 300; i += 1) env.pump(16.7);
  assert.ok(ui.length - n0 <= 3, `300 khung chơi bình thường chỉ phát ${ui.length - n0} cập nhật UI`);
  assert.equal(ui.at(-1).mode, "play");
  rt.pause();
  assert.equal(ui.at(-1).paused, true);
  rt.destroy();
});

test("móc QA chỉ có khi trang đặt window.__INK_QA__ trước khi tải, và bị gỡ khi destroy", async () => {
  const env = installEnv();
  const a = await make(env);
  assert.equal(env.win.__INK_QA_API__, undefined, "mặc định KHÔNG có móc QA");
  a.rt.destroy();
  env.win.__INK_QA__ = true;
  const b = await make(env);
  assert.ok(env.win.__INK_QA_API__ && env.win.__INK_QA_API__.game === b.rt.game);
  b.rt.destroy();
  assert.equal(env.win.__INK_QA_API__, undefined, "destroy gỡ móc");
});

test("mất tiêu điểm khi đang giữ phím: nhả hết (không kẹt phím); tiếp tục từ lưu cũ", async () => {
  const env = installEnv();
  const { rt } = await make(env);
  const kd = { code: "ArrowRight", key: "ArrowRight", ctrlKey: false, metaKey: false, altKey: false, repeat: false, target: { tagName: "DIV" }, preventDefault() {} };
  for (const f of env.winHandlers.get("keydown")) f(kd);
  assert.equal(rt.input.read().right, true);
  for (const f of env.winHandlers.get("blur")) f({});
  assert.equal(rt.input.read().right, false);
  rt.destroy();
});

test("lời thoại không hết hạn trong lúc tạm dừng: dừng lâu rồi tiếp tục vẫn còn đủ thời gian đọc (review vòng 2 #D1)", async () => {
  const env = installEnv();
  let fake = 1000;
  const realPerf = Object.getOwnPropertyDescriptor(globalThis, "performance");
  Object.defineProperty(globalThis, "performance", { value: { now: () => fake }, configurable: true });
  try {
    const { rt, ui } = await make(env);
    env.pump(16.7); // khung đầu chỉ đặt mốc thời gian
    rt.game.emit({ t: "caption", id: "tut.move" });
    env.pump(16.7);
    env.pump(16.7);
    assert.ok(ui.at(-1).caption, "lời thoại hiện");
    rt.pause();
    fake += 60_000; // dừng 60 giây
    env.pump(16.7);
    rt.resume();
    env.pump(16.7);
    env.pump(16.7);
    assert.ok(ui.at(-1).caption, "vẫn còn lời thoại sau khi tiếp tục");
    fake += 20_000;
    env.pump(16.7);
    env.pump(16.7);
    assert.equal(ui.at(-1).caption, null, "hết hạn sau thời gian đọc bình thường");
    rt.destroy();
  } finally {
    if (realPerf) Object.defineProperty(globalThis, "performance", realPerf);
  }
});
