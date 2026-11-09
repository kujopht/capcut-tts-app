/*
 * INK SCOUT — lớp đầu vào (bàn phím + nút chạm đa ngón) và gỡ sạch bộ nghe.
 * Dùng đích `window` giả (chỉ addEventListener/removeEventListener) nên chạy được trong Node.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { loadModule } from "./helpers/loadGameCore.mjs";

const { InputSource } = await loadModule("src/game/inkscout/platform/input.ts");

function fakeWindow() {
  const handlers = new Map();
  return {
    handlers,
    addEventListener(t, f) {
      if (!handlers.has(t)) handlers.set(t, new Set());
      handlers.get(t).add(f);
    },
    removeEventListener(t, f) {
      handlers.get(t)?.delete(f);
    },
    fire(t, ev) {
      for (const f of [...(handlers.get(t) ?? [])]) f(ev);
    },
    count() {
      let n = 0;
      for (const s of handlers.values()) n += s.size;
      return n;
    },
  };
}

const key = (code, extra = {}) => ({ code, key: code, ctrlKey: false, metaKey: false, altKey: false, repeat: false, target: { tagName: "DIV" }, preventDefault() { this.prevented = true; }, ...extra });

function setup() {
  const w = fakeWindow();
  const inp = new InputSource();
  const hooks = { pauses: 0, anyKey: 0 };
  inp.attach(w, { onPause: () => (hooks.pauses += 1), onAnyKey: () => (hooks.anyKey += 1) });
  inp.active = true;
  return { w, inp, hooks };
}

test("phím: ←/A đi trái, →/D đi phải, Space/↑/W nhảy, J/Z chém, K/X Pulse, Shift/L lướt, Enter/E xác nhận", () => {
  const { w, inp } = setup();
  const cases = [
    ["ArrowLeft", "left"], ["KeyA", "left"], ["ArrowRight", "right"], ["KeyD", "right"], ["Space", "jump"], ["ArrowUp", "jump"], ["KeyW", "jump"],
    ["KeyJ", "attack"], ["KeyZ", "attack"], ["KeyK", "pulse"], ["KeyX", "pulse"], ["ShiftLeft", "dash"], ["KeyL", "dash"], ["Enter", "confirm"], ["KeyE", "confirm"],
  ];
  for (const [code, btn] of cases) {
    w.fire("keydown", key(code));
    assert.equal(inp.read()[btn], true, `${code} ⇒ ${btn}`);
    w.fire("keyup", key(code));
    assert.equal(inp.read()[btn], false, `${code} nhả`);
  }
});

test("hai phím cùng nút: chỉ nhả khi cả hai nhả; trái+phải cùng giữ thì triệt tiêu", () => {
  const { w, inp } = setup();
  w.fire("keydown", key("ArrowLeft"));
  w.fire("keydown", key("KeyA"));
  w.fire("keyup", key("ArrowLeft"));
  assert.equal(inp.read().left, true, "A vẫn đang giữ");
  w.fire("keyup", key("KeyA"));
  assert.equal(inp.read().left, false);
  w.fire("keydown", key("ArrowLeft"));
  w.fire("keydown", key("ArrowRight"));
  assert.deepEqual([inp.read().left, inp.read().right], [false, false]);
});

test("chặn cuộn trang: Space/mũi tên bị preventDefault khi game đang nhận đầu vào; không chặn khi gõ vào ô nhập", () => {
  const { w, inp } = setup();
  const e1 = key("Space");
  w.fire("keydown", e1);
  assert.equal(e1.prevented, true);
  const e2 = key("Space", { target: { tagName: "INPUT" } });
  w.fire("keydown", e2);
  assert.notEqual(e2.prevented, true);
  inp.active = false;
  const e3 = key("ArrowDown");
  w.fire("keydown", e3);
  assert.notEqual(e3.prevented, true, "không hoạt động ⇒ không nuốt phím");
});

test("Esc/P gọi tạm dừng một lần (bỏ qua lặp phím); mất tiêu điểm nhả hết phím (không kẹt)", () => {
  const { w, inp, hooks } = setup();
  w.fire("keydown", key("Escape"));
  w.fire("keydown", key("Escape", { repeat: true }));
  assert.equal(hooks.pauses, 1);
  w.fire("keydown", key("ArrowRight"));
  w.fire("keydown", key("KeyJ"));
  assert.equal(inp.read().right && inp.read().attack, true);
  w.fire("blur", {});
  const r = inp.read();
  assert.equal(r.right || r.attack, false);
  assert.ok(hooks.anyKey >= 2);
});

test("nút chạm: nhiều ngón giữ cùng một nút, chỉ nhả khi ngón cuối nhả; ngón khác nút độc lập", () => {
  const { inp } = setup();
  inp.press("right", 1);
  inp.press("jump", 2);
  inp.press("right", 3);
  let r = inp.read();
  assert.equal(r.right && r.jump, true);
  inp.release("right", 1);
  assert.equal(inp.read().right, true, "ngón 3 vẫn giữ");
  inp.release("right", 3);
  assert.equal(inp.read().right, false);
  inp.releasePointer(2);
  assert.equal(inp.read().jump, false);
});

test("controller QA thay thế nguồn đầu vào; không hoạt động ⇒ đầu vào rỗng", () => {
  const { inp } = setup();
  inp.controller = () => ({ left: false, right: true, jump: false, attack: false, pulse: false, dash: false, confirm: false });
  assert.equal(inp.read().right, true);
  inp.controller = null;
  assert.equal(inp.read().right, false);
  inp.active = false;
  inp.press("jump", 1);
  assert.equal(inp.read().jump, false);
});

test("detach gỡ SẠCH mọi bộ nghe và nhả phím; attach lại không nhân đôi", () => {
  const { w, inp } = setup();
  assert.ok(w.count() >= 3);
  w.fire("keydown", key("ArrowRight"));
  inp.detach();
  assert.equal(w.count(), 0);
  assert.equal(inp.read().right, false);
  inp.attach(w, { onPause() {} });
  inp.attach(w, { onPause() {} });
  assert.equal(w.count(), 3, "attach hai lần vẫn chỉ ba bộ nghe (keydown, keyup, blur)");
  inp.detach();
  assert.equal(w.count(), 0);
});

test("Enter/Space trên một nút của hộp thoại DOM do trình duyệt kích hoạt: không bị nuốt, không thành hành động game (review độc lập #B1)", () => {
  const { w, inp } = setup();
  for (const code of ["Enter", "Space"]) {
    const e = key(code, { target: { tagName: "BUTTON", getAttribute: () => null } });
    w.fire("keydown", e);
    assert.notEqual(e.prevented, true, `${code} trên BUTTON không bị preventDefault`);
    assert.equal(inp.read().confirm || inp.read().jump, false, `${code} trên BUTTON không thành confirm/jump`);
  }
  const radio = key("Space", { target: { tagName: "DIV", getAttribute: (a) => (a === "role" ? "radio" : null) } });
  w.fire("keydown", radio);
  assert.notEqual(radio.prevented, true);
  // mũi tên vẫn là điều khiển game khi tiêu điểm ở nút
  w.fire("keydown", key("ArrowRight", { target: { tagName: "BUTTON", getAttribute: () => null } }));
  assert.equal(inp.read().right, true);
});

test("nút chạm cũng thử mở khoá âm thanh (cử chỉ người dùng) (review độc lập #B2)", () => {
  const { inp, hooks } = setup();
  const n = hooks.anyKey;
  inp.press("jump", 5);
  assert.equal(hooks.anyKey, n + 1);
});
