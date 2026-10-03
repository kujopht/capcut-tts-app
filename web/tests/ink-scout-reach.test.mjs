/*
 * INK SCOUT — CHỨNG MINH KHẢ NĂNG TIẾP CẬN (không soft-lock, cổng khả năng, backtracking).
 *
 * Bộ giải (`helpers/nav.mjs`) dựng nút đứng trên mọi mặt sàn của từng phòng rồi mô phỏng BẰNG CHÍNH `Player` + `TileMap` thật hàng trăm macro
 * (đi/nhảy/lướt) từ mỗi nút; chỉ giữ cạnh BỀN (đáp xuống cùng chỗ khi lệch xuất phát ±1,5 px và lệch thời điểm lướt ±1 khung). Từ đó chứng minh:
 *   • mọi vật thể bắt buộc đều ĐẠT ĐƯỢC khi có đúng khả năng cần;
 *   • các cổng thiết kế (khe 5 ô, bệ glyph ẩn) THẬT SỰ chặn khi thiếu khả năng — Margin Step mở ra ≥ 1 lối trước đó không vào được;
 *   • không có chỗ nào mà người chơi bị kẹt vĩnh viễn (đồ thị trạng thái liên thông mạnh).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { loadModule } from "./helpers/loadGameCore.mjs";
import { buildNav } from "./helpers/nav.mjs";

const core = await loadModule();
const { room, spawnPos, ROOM_ORDER } = core;

const cache = new Map();
function nav(id, step, glyphs = true) {
  const k = `${id}:${step ? 1 : 0}:${glyphs ? 1 : 0}`;
  if (!cache.has(k)) cache.set(k, buildNav(core, id, { marginStep: step, glyphs }));
  return cache.get(k);
}

/** Tập khoá "chạm" đạt được từ một spawn. */
function reach(id, spawn, step, glyphs = true) {
  const n = nav(id, step, glyphs);
  const pos = spawnPos(room(id), spawn);
  const start = n.snap(pos.x, pos.y);
  assert.ok(start >= 0, `${id}.${spawn}: spawn không nằm trên nút đứng`);
  return new Set(n.reachable([start]).found.keys());
}

const has = (s, ...keys) => keys.every((k) => s.has(k));

test("vật thể bắt buộc đều đạt được khi có đúng khả năng", () => {
  assert.ok(has(reach("entrance", "start", false), "exit:hall"), "Cửa Kho → Đại Sảnh (không cần khả năng)");
  assert.ok(has(reach("hall", "left", false), "exit:entrance", "exit:echo", "exit:stacks", "checkpoint:hall"));
  assert.ok(has(reach("echo", "left", false, true), "memory:1"), "Ký Ức I: cần Pulse (glyph) nhưng KHÔNG cần Margin Step");
  assert.ok(has(reach("stacks", "top", false), "exit:shrine", "exit:hall"), "Dãy Kệ → Đền Lề: không cần khả năng");
  assert.ok(has(reach("shrine", "left", false), "marginStep", "checkpoint:shrine", "exit:stacks"), "Margin Step nằm TRƯỚC khe đầu tiên");
  assert.ok(has(reach("sealed", "left", true), "memory:2", "checkpoint:sealed", "exit:redacted", "exit:shrine"));
  assert.ok(has(reach("secret", "left", true), "memory:3", "exit:hall"));
  assert.ok(has(reach("redacted", "left", true), "checkpoint:redacted", "exit:bookmark", "exit:sealed"));
  assert.ok(has(reach("bookmark", "left", true), "checkpoint:bookmark", "exit:arena", "exit:redacted"));
  assert.ok(has(reach("arena", "left", true), "bossTrigger", "exit:ending"));
  assert.ok(has(reach("ending", "left", true), "endingTrigger", "exit:arena"));
});

test("cổng khả năng: thiếu Margin Step thì KHÔNG tới được; có thì tới được (backtracking thật)", () => {
  const gates = [
    ["hall", "left", "exit:secret", "Phòng Ký Ức Bí Mật chỉ vào được từ gờ cao của Đại Sảnh"],
    ["shrine", "left", "exit:sealed", "Đền Lề → Chồng Phong Ấn qua khe 5 ô"],
    ["sealed", "left", "memory:2", "Ký Ức II nằm sau khe 5 ô"],
    ["sealed", "left", "exit:redacted", "Chồng Phong Ấn → Sảnh Bị Biên Tập"],
    ["redacted", "left", "exit:bookmark", "khe 5 ô giữa Sảnh Bị Biên Tập"],
  ];
  for (const [id, spawn, key, why] of gates) {
    assert.equal(reach(id, spawn, false).has(key), false, `${key} phải bị chặn khi chưa có Margin Step (${why})`);
    assert.equal(reach(id, spawn, true).has(key), true, `${key} phải mở khi có Margin Step (${why})`);
  }
});

test("ký ức là TUỲ CHỌN: bỏ hẳn các bệ dẫn tới Ký Ức II thì vẫn qua được Chồng Phong Ấn; Ký Ức I/III nằm ngoài lối chính", () => {
  const n = buildNav(core, "sealed", { marginStep: true, glyphs: true, excludeNode: (p) => p.y <= 130 });
  const pos = spawnPos(room("sealed"), "left");
  const found = n.reachable([n.snap(pos.x, pos.y)]).found;
  assert.equal(found.has("exit:redacted"), true, "không cần lên bệ Ký Ức II để đi tiếp");
  assert.equal(found.has("memory:2"), false, "(và các bậc ván lên hốc đã bị loại ⇒ không nhặt được — xác nhận phép loại có tác dụng)");
  assert.ok(has(reach("echo", "left", false, false), "exit:hall"), "Phòng Vọng: đi qua không cần Ký Ức I");
  assert.equal(room("secret").exits.length, 1, "Phòng Bí Mật là ngõ cụt tuỳ chọn");
});

test("cổng Pulse: Ký Ức I chỉ lấy được khi các bệ glyph ẩn được lộ ra", () => {
  assert.equal(reach("echo", "left", false, false).has("memory:1"), false, "không lộ glyph ⇒ không tới");
  assert.equal(reach("echo", "left", true, true).has("memory:1"), true);
});

test("không soft-lock: trước Margin Step vẫn đi lại tự do khu đầu; có Margin Step thì cả 11 phòng liên thông mạnh", () => {
  /** Đồ thị trạng thái (phòng:spawn) với một bộ khả năng. */
  const edges = new Map();
  const key = (id, sp) => `${id}:${sp}`;
  function build(step) {
    edges.clear();
    for (const id of ROOM_ORDER) {
      const def = room(id);
      for (const sp of Object.keys(def.spawns)) {
        const r = reach(id, sp, step);
        const out = [];
        for (const ex of def.exits) if (r.has(`exit:${ex.to}`)) out.push(key(ex.to, ex.spawn));
        edges.set(key(id, sp), out);
      }
    }
  }
  const closure = (from) => {
    const seen = new Set([from]);
    const q = [from];
    for (let i = 0; i < q.length; i += 1) for (const v of edges.get(q[i]) ?? []) if (!seen.has(v)) (seen.add(v), q.push(v));
    return seen;
  };
  const roomsOf = (set) => new Set([...set].map((s) => s.split(":")[0]));

  // Trước Margin Step: từ điểm bắt đầu chỉ tới được khu đầu — và từ MỌI nơi trong khu đó đều quay lại được điểm hồi sinh (hall).
  build(false);
  const early = closure(key("entrance", "start"));
  const earlyRooms = roomsOf(early);
  assert.deepEqual([...earlyRooms].sort(), ["echo", "entrance", "hall", "shrine", "stacks"], `khu đầu: ${[...earlyRooms]}`);
  for (const node of early) {
    const back = closure(node);
    assert.ok([...back].some((n) => n.startsWith("hall:")), `${node}: không quay lại được Đại Sảnh khi chưa có Margin Step`);
    assert.ok(roomsOf(back).has("shrine"), `${node}: không quay lại được Đền Lề (nơi có Margin Step)`);
  }
  // Có Margin Step: cả 11 phòng, và từ mọi trạng thái đều về được Đại Sảnh/Đấu trường (liên thông mạnh theo phòng).
  build(true);
  const all = closure(key("entrance", "start"));
  assert.equal(roomsOf(all).size, 11, `đã tới ${[...roomsOf(all)]}`);
  for (const node of all) {
    const back = closure(node);
    assert.ok(roomsOf(back).has("hall") && roomsOf(back).has("entrance"), `${node}: không quay về được khu đầu`);
    assert.ok(roomsOf(back).has("arena"), `${node}: không tới được Đấu trường`);
  }
});

test("hố gai và khe rơi KHÔNG phải ngõ cụt: rơi xuống gai được đưa về chỗ an toàn nên không bao giờ kẹt", () => {
  // Gai nằm đáy mọi khe 5 ô; người chơi rơi vào sẽ về điểm an toàn gần nhất (kiểm bằng test lõi) — ở đây xác nhận mỗi khe có gai ở ĐÁY chứ không phải tường.
  for (const id of ["entrance", "shrine", "sealed", "redacted"]) {
    const rows = room(id).tiles;
    assert.ok(rows.some((r) => r.includes("^")), `${id} có gai đáy khe`);
    assert.ok(rows[rows.length - 1].includes("^"), `${id}: hàng đáy có gai`);
  }
});
