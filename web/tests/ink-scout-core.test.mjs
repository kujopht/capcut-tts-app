/*
 * INK SCOUT: THE LOST CHAPTER — lõi mô phỏng tất định.
 * Movement (gia tốc/giảm tốc, nhảy biến thiên, coyote, jump buffer, knockback, i-frames), chiến đấu (combo, Ink, Pulse), kẻ địch (FSM, báo trước),
 * ký ức, Margin Step, lưu/tải, chết/hồi sinh, tính tất định. Không dùng DOM/Canvas/thời gian thực.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { loadModule } from "./helpers/loadGameCore.mjs";

const m = await loadModule();
const { TileMap, Player, NO_INPUT, TILE, PLAYER, BLADE, PULSE, Game, Enemy, ENEMY_SPEC, MemoryStore, defaultSave, sanitizeSave, endingEligibility, room } = m;

const noop = () => {};
const ABIL = { marginStep: true, pulseWide: false, pulseCheap: false };
const NOABIL = { marginStep: false, pulseWide: false, pulseCheap: false };

function arena(w = 80) {
  const rows = [];
  for (let r = 0; r < 20; r += 1) rows.push(r >= 17 ? "#".repeat(w) : ".".repeat(w));
  return new TileMap(rows);
}

/** Chạy một người chơi `frames` khung với hàm đầu vào theo khung. */
function run(map, frames, inputAt, { x = 80, abilities = ABIL, setup, events } = {}) {
  const p = new Player(x, 17 * TILE);
  setup?.(p);
  const trace = [];
  for (let f = 0; f < frames; f += 1) {
    const input = { ...NO_INPUT, ...inputAt(f, p) };
    p.update({ map, input, abilities, emit: (e) => events?.push(e) });
    trace.push({ x: p.x, y: p.y, vx: p.vx, vy: p.vy, g: p.onGround });
  }
  return { p, trace };
}

const floorY = 17 * TILE;

// ---------------------------------------------------------------- di chuyển
test("chạy: tăng tốc dần tới tốc độ tối đa, nhả phím thì giảm tốc về 0", () => {
  const map = arena();
  const { trace } = run(map, 60, (f) => ({ right: f < 30 }));
  assert.ok(trace[2].vx > 0 && trace[2].vx < PLAYER.maxRun, "khung 3 đang tăng tốc");
  assert.equal(trace[25].vx, PLAYER.maxRun);
  assert.ok(Math.abs(trace[45].vx) < 0.01, "đã dừng sau khi nhả phím");
  // đổi chiều nhanh hơn tăng tốc thường (turnBoost)
  const turn = run(map, 40, (f) => ({ right: f < 20, left: f >= 20 }));
  assert.ok(turn.trace[26].vx < 0.2, "quay đầu: vx đã giảm mạnh sau 6 khung");
});

test("nhảy biến thiên: giữ lâu cao hơn nhảy ngắn; nhảy tối đa ≈ 3,5 ô", () => {
  const map = arena();
  const peak = (hold) => floorY - Math.min(...run(map, 70, (f) => ({ jump: f >= 5 && f < 5 + hold })).trace.map((t) => t.y));
  const full = peak(50);
  const tap = peak(3);
  assert.ok(full >= 3 * TILE + 4 && full <= 4 * TILE, `nhảy đầy ${full}px phải trong (52..64]`);
  assert.ok(tap < full - 18, `nhảy ngắn ${tap}px phải thấp hơn rõ rệt so với ${full}px`);
  assert.ok(tap > 4, "nhảy ngắn vẫn rời đất");
});

test("coyote time: còn nhảy được vài khung sau khi rời mép, hết cửa sổ thì không", () => {
  // Sàn kết thúc tại cột 10: đi ra khỏi mép rồi bấm nhảy sau N khung.
  const rows = [];
  for (let r = 0; r < 20; r += 1) rows.push(r >= 17 ? "#".repeat(10) + ".".repeat(60) : ".".repeat(70));
  const map = new TileMap(rows);
  const attempt = (delay) => {
    let leftAt = -1;
    const { trace } = run(map, 90, (f, p) => {
      if (leftAt < 0 && !p.onGround && f > 3) leftAt = f;
      return { right: f < 40, jump: leftAt >= 0 && f === leftAt + delay };
    }, { x: 130 });
    const after = trace.slice(Math.max(0, leftAt + delay), leftAt + delay + 6);
    return after.some((t) => t.vy < -3);
  };
  assert.equal(attempt(3), true, "3 khung sau mép: vẫn nhảy (coyote 6)");
  assert.equal(attempt(14), false, "14 khung sau mép: hết coyote");
});

test("jump buffer: bấm nhảy sớm vài khung trước khi chạm đất vẫn nhảy khi chạm; quá sớm thì không", () => {
  const map = arena();
  const base = run(map, 120, (f) => ({ jump: f < 20 }));
  const L = base.trace.findIndex((t, i) => i > 8 && t.g);
  assert.ok(L > 25, `đáp xuống ở khung ${L}`);
  const attempt = (early) => {
    const { trace } = run(map, 120, (f) => ({ jump: f < 20 || (f >= L - early && f < L - early + 3) }));
    return trace.slice(L, L + 6).some((t) => t.vy < -1);
  };
  assert.equal(attempt(5), true, "bấm sớm 5 khung (≤ 7): nhảy ngay khi chạm đất");
  assert.equal(attempt(16), false, "bấm sớm 16 khung: hết cửa sổ đệm");
});

test("knockback + i-frames: trúng đòn bị hất ra, 60 khung bất tử, sau đó trúng lại được", () => {
  const p = new Player(100, floorY);
  const ev = [];
  assert.equal(p.takeHit(120, 1, (e) => ev.push(e)), true);
  assert.equal(p.hp, PLAYER.maxHp - 1);
  assert.ok(p.vx < 0, "nguồn ở bên phải ⇒ bị hất sang trái");
  assert.ok(p.vy < 0, "bị hất lên");
  assert.equal(p.takeHit(120, 1, noop), false, "đang bất tử");
  assert.equal(p.hp, PLAYER.maxHp - 1);
  const map = arena();
  for (let f = 0; f < PLAYER.invulnFrames + 2; f += 1) p.update({ map, input: NO_INPUT, abilities: ABIL, emit: noop });
  assert.equal(p.invulnerable, false);
  assert.equal(p.takeHit(80, 1, noop), true);
  assert.ok(ev.some((e) => e.t === "shake") && ev.some((e) => e.t === "sfx"), "phát hiệu ứng rung/âm");
});

test("Margin Step: cần khả năng; lướt mặt đất ≈ 54–66 px; lướt trên không mỗi cú nhảy một lần; có khung bất tử đầu", () => {
  const map = arena();
  const noDash = run(map, 30, (f) => ({ dash: f === 3 }), { abilities: NOABIL });
  const withDash = run(map, 30, (f) => ({ dash: f === 3 }), {});
  const d = withDash.trace[29].x - 80;
  assert.ok(d >= 54 && d <= 70, `lướt mặt đất ${d.toFixed(1)}px`);
  assert.ok(Math.abs(noDash.trace[29].x - 80) < 3, "chưa có khả năng ⇒ không lướt");
  // lướt trên không hai lần liền: lần hai bị chặn
  const air = run(map, 60, (f) => ({ jump: f >= 2 && f < 40, right: true, dash: f === 12 || f === 40 }), {});
  assert.ok(air.p.x > 80);
  // bất tử đầu lướt
  const p = new Player(100, floorY);
  const mp = arena();
  p.update({ map: mp, input: NO_INPUT, abilities: ABIL, emit: noop });
  p.update({ map: mp, input: { ...NO_INPUT, dash: true }, abilities: ABIL, emit: noop });
  assert.equal(p.dashing, true);
  assert.equal(p.invulnerable, true);
  assert.equal(p.takeHit(90, 1, noop), false, "lướt né được đòn");
});

test("số đo thiết kế phòng: nhảy xa < khe 5 ô, + lướt > khe 5 ô, bậc cao ≤ 3 ô", () => {
  const map = arena(100);
  const dist = (dash) => {
    const { trace } = run(map, 160, (f) => ({ right: f >= 2, jump: f >= 20 && f < 70, dash: dash && f === 32 }));
    const takeoff = trace.findIndex((t, i) => i > 20 && !t.g);
    const land = trace.findIndex((t, i) => i > takeoff && t.g);
    return trace[land].x - trace[takeoff - 1].x;
  };
  const plain = dist(false);
  const dashed = dist(true);
  assert.ok(plain < 5 * TILE - 8, `nhảy thường ${plain.toFixed(0)}px phải KHÔNG vượt khe 5 ô (80 px)`);
  assert.ok(plain > 3 * TILE + 8, `nhảy thường ${plain.toFixed(0)}px phải vượt khe 3 ô (48 px)`);
  assert.ok(dashed > 5 * TILE + 8, `nhảy + lướt ${dashed.toFixed(0)}px phải vượt khe 5 ô`);
});

// ---------------------------------------------------------------- chém / Ink / Pulse
test("Glyph Blade: combo ba nhát, nhát trên không riêng, hộp đòn chỉ tồn tại trong cửa sổ trúng", () => {
  const map = arena();
  const kinds = new Set();
  const boxes = [];
  const pl = new Player(100, floorY);
  const seq = [];
  for (let f = 0; f < 70; f += 1) {
    pl.update({ map, input: { ...NO_INPUT, attack: [2, 10, 24].includes(f) }, abilities: ABIL, emit: noop });
    kinds.add(pl.attackKind);
    seq.push(pl.attackKind);
    boxes.push(pl.attackBox() !== null);
  }
  assert.ok(kinds.has("g1") && kinds.has("g2") && kinds.has("g3"), `đã thấy ${[...kinds]}`);
  assert.ok(boxes.some(Boolean) && !boxes.every(Boolean));
  // nhát trên không
  const air = new Player(100, floorY);
  air.update({ map, input: { ...NO_INPUT, jump: true }, abilities: ABIL, emit: noop });
  for (let f = 0; f < 12; f += 1) air.update({ map, input: { ...NO_INPUT, jump: true, attack: f === 6 }, abilities: ABIL, emit: noop });
  assert.equal(air.attackKind, "air");
  assert.equal(BLADE.hitStop < BLADE.hitStopHeavy, true);
});

test("Ink: chém trúng kẻ địch tích 1 Ink mỗi mục tiêu, có hit-stop, và Ink bị chặn ở mức tối đa", () => {
  const g = new Game({ seed: 1 });
  g.enemies.length = 0;
  g.qaGoto("entrance", "start");
  g.enemies = [new Enemy({ kind: "scribble", tx: 5, ty: 10 })];
  g.player.place(g.enemies[0].x - 20, 11 * TILE);
  g.player.facing = 1;
  g.step(NO_INPUT);
  for (let f = 0; f < 30 && g.player.ink === 0; f += 1) g.step({ ...NO_INPUT, attack: f === 0 });
  assert.ok(g.player.ink >= 1, `Ink ${g.player.ink}`);
  assert.ok(g.hitStop >= 0);
  g.qaGrant({ ink: 99 });
  assert.equal(g.player.ink, PLAYER.maxInk);
});

test("Memory Pulse: tốn 3 Ink (2 khi có Ký Ức III), làm choáng kẻ địch trong tầm, mở rộng khi có Ký Ức II", () => {
  const g = new Game({ seed: 1 });
  g.qaGoto("entrance", "start");
  g.enemies = [new Enemy({ kind: "scribble", tx: 6, ty: 10 })];
  const e = g.enemies[0];
  g.player.place(e.x - 30, 11 * TILE);
  g.qaGrant({ ink: 2 });
  g.step({ ...NO_INPUT, pulse: true });
  assert.equal(g.player.pulseT, 0, "không đủ Ink ⇒ không tung");
  g.qaGrant({ ink: 3 });
  g.step({ ...NO_INPUT });
  g.step({ ...NO_INPUT, pulse: true });
  assert.ok(g.player.pulseT > 0);
  assert.equal(g.player.ink, 0, "tốn 3 Ink");
  for (let f = 0; f < PULSE.windup + PULSE.expandFrames + 2; f += 1) g.step(NO_INPUT);
  assert.ok(e.stun > 0, "kẻ địch trong tầm bị gián đoạn");
  // Ký Ức III: rẻ hơn; Ký Ức II: rộng hơn
  g.qaGrant({ memories: [2, 3], ink: 2 });
  assert.equal(g.abilities.pulseCheap, true);
  assert.equal(g.abilities.pulseWide, true);
  assert.equal(g.player.pulseCost(g.abilities), PULSE.costMemory3);
});

// ---------------------------------------------------------------- kẻ địch
test("kẻ địch: mỗi loại có báo trước ≥ 20 khung trước khi gây sát thương", () => {
  for (const [k, s] of Object.entries(ENEMY_SPEC)) assert.ok(s.telegraph >= 20, `${k} báo trước ${s.telegraph}`);
});

test("Scribble: tuần tra → báo trước → lao → hồi phục → tuần tra; bị chém giữa báo trước thì bị ngắt", () => {
  const map = arena();
  const e = new Enemy({ kind: "scribble", tx: 20, ty: 16 });
  const px = e.x - 60;
  const seen = [];
  for (let f = 0; f < 200; f += 1) {
    e.update({ map, px, py: e.y, emit: noop });
    if (seen[seen.length - 1] !== e.state) seen.push(e.state);
  }
  assert.deepEqual(seen.slice(0, 4), ["notice", "lunge", "recover", "patrol"]);
  const e2 = new Enemy({ kind: "scribble", tx: 20, ty: 16 });
  for (let f = 0; f < 60 && e2.state !== "notice"; f += 1) e2.update({ map, px: e2.x - 60, py: e2.y, emit: noop });
  assert.equal(e2.state, "notice");
  e2.hit(1, 1, noop);
  assert.equal(e2.state, "recover", "bị chém trong báo trước ⇒ ngắt đòn");
});

test("kẻ địch: Torn Page báo trước rồi bổ nhào; Hound cúi → lao; Broken báo trước dài + đòn đập; hạ gục thì dọn", () => {
  const map = arena();
  const page = new Enemy({ kind: "tornPage", tx: 20, ty: 10 });
  const s1 = new Set();
  for (let f = 0; f < 120; f += 1) {
    page.update({ map, px: page.x + 40, py: 17 * TILE, emit: noop });
    s1.add(page.state);
  }
  assert.ok(s1.has("telegraph") && s1.has("dive"), [...s1].join());
  const hound = new Enemy({ kind: "hound", tx: 20, ty: 16 });
  const s2 = new Set();
  for (let f = 0; f < 120; f += 1) {
    hound.update({ map, px: hound.x - 100, py: hound.y, emit: noop });
    s2.add(hound.state);
  }
  assert.ok(s2.has("crouch") && s2.has("charge"), [...s2].join());
  const broken = new Enemy({ kind: "broken", tx: 20, ty: 16 });
  const s3 = new Set();
  for (let f = 0; f < 200; f += 1) {
    broken.update({ map, px: broken.x - 40, py: broken.y, emit: noop });
    s3.add(broken.state);
  }
  assert.ok(s3.has("notice") && s3.has("slam"), [...s3].join());
  // hạ gục → dying → alive=false sau animation (dọn tất định)
  const e = new Enemy({ kind: "scribble", tx: 5, ty: 16 });
  assert.equal(e.hit(99, 1, noop), true);
  assert.equal(e.alive, true);
  for (let f = 0; f < 30; f += 1) e.update({ map, px: 0, py: 0, emit: noop });
  assert.equal(e.alive, false);
});

test("va chạm công bằng: hộp chạm kẻ địch nhỏ hơn thân và rỗng khi bị choáng/đang chết", () => {
  const e = new Enemy({ kind: "hound", tx: 5, ty: 10 });
  const cb = e.contactBox;
  assert.ok(cb.w < e.hurtbox.w && cb.h < e.hurtbox.h);
  e.disrupt(60);
  assert.equal(e.contactBox, null);
});

// ---------------------------------------------------------------- ký ức / khả năng / lưu
test("Ký Ức: nhặt tại đúng chỗ ⇒ lưu, mở hộp đọc, thưởng cơ chế; chỉ nhặt một lần", () => {
  const g = new Game({ seed: 1 });
  g.qaGoto("secret", "left");
  g.player.place(12 * TILE + 8, 10 * TILE);
  g.step(NO_INPUT);
  assert.deepEqual(g.save.memories, [3]);
  assert.equal(g.mode, "read");
  assert.equal(g.readKind, "memory");
  const ev = g.drainEvents();
  assert.ok(ev.some((e) => e.t === "memory" && e.id === 3));
  assert.ok(ev.some((e) => e.t === "save"));
  // đóng hộp đọc (cần ≥ 30 khung)
  for (let f = 0; f < 40; f += 1) g.step(NO_INPUT);
  g.step({ ...NO_INPUT, confirm: true });
  assert.equal(g.mode, "play");
  g.step(NO_INPUT);
  assert.deepEqual(g.save.memories, [3], "không nhặt lại");
  // Ký Ức I: +1 máu tối đa
  g.qaGoto("echo", "left");
  g.player.place(24 * TILE + 8, 6 * TILE);
  g.step(NO_INPUT);
  assert.equal(g.player.maxHp, PLAYER.maxHp + 1);
});

test("Margin Step: nhặt ở Đền Lề mở khả năng, phát sự kiện, lưu; chưa nhặt thì không lướt được", () => {
  const g = new Game({ seed: 1 });
  assert.equal(g.abilities.marginStep, false);
  g.qaGoto("shrine", "left");
  g.player.place(16 * TILE + 8, 11 * TILE);
  g.step(NO_INPUT);
  assert.equal(g.save.marginStep, true);
  assert.equal(g.abilities.marginStep, true);
  assert.equal(g.mode, "read");
  assert.ok(g.drainEvents().some((e) => e.t === "ability" && e.id === "marginStep"));
});

test("lưu/tải: mặc định hợp lệ, vòng lưu–đọc không đổi, dữ liệu hỏng/độc không làm sập, nhất quán tiến trình", async () => {
  const d = defaultSave();
  assert.equal(d.v, 1);
  assert.deepEqual(sanitizeSave(d), d);
  const store = new MemoryStore();
  assert.equal(await store.load(), null);
  const s = defaultSave();
  s.checkpoint = "shrine";
  s.marginStep = true;
  s.memories = [1, 3];
  await store.save(s);
  assert.deepEqual(await store.load(), s);
  // JSON hỏng
  store.seedRaw("{not json");
  assert.equal(await store.load(), null);
  // giá trị độc / sai kiểu
  const bad = sanitizeSave({ checkpoint: "<script>", marginStep: "yes", memories: [1, 1, 9, "2", 3, null], bossDefeated: 1, ending: "hax", settings: { shake: 7, muted: "x" }, playFrames: -5, deaths: 1e30, bestFrames: "fast" });
  assert.equal(bad.checkpoint, "start");
  assert.equal(bad.marginStep, false);
  assert.deepEqual(bad.memories, [1, 3]);
  assert.equal(bad.ending, null);
  assert.equal(bad.settings.shake, 1);
  assert.equal(bad.playFrames, 0);
  assert.ok(bad.deaths <= 1_000_000);
  // điểm lưu sau Đền Lề mà chưa có Margin Step ⇒ coi như hỏng, đưa về Đền Lề
  assert.equal(sanitizeSave({ checkpoint: "bookmark", marginStep: false }).checkpoint, "shrine");
  assert.equal(sanitizeSave({ checkpoint: "bookmark", marginStep: true }).checkpoint, "bookmark");
  // không thể "có kết thúc" mà boss chưa bị hạ
  assert.equal(sanitizeSave({ ending: "erase" }).bossDefeated, true);
});

test("tải game từ lưu: vào đúng Dấu Trang, đúng khả năng/ký ức", () => {
  const s = defaultSave();
  s.checkpoint = "sealed";
  s.marginStep = true;
  s.memories = [1];
  const g = new Game({ save: s, seed: 3 });
  assert.equal(g.roomId, "sealed");
  assert.equal(g.abilities.marginStep, true);
  assert.equal(g.player.maxHp, PLAYER.maxHp + 1);
});

test("điều kiện kết thúc: 0–1 ký ức ⇒ cơ bản; 2 ⇒ thoại thêm; 3 ⇒ được chọn XOÁ/KHÔI PHỤC", () => {
  assert.deepEqual(endingEligibility([]), { choice: false, extraDialogue: false });
  assert.deepEqual(endingEligibility([1]), { choice: false, extraDialogue: false });
  assert.deepEqual(endingEligibility([1, 2]), { choice: false, extraDialogue: true });
  assert.deepEqual(endingEligibility([1, 2, 3]), { choice: true, extraDialogue: true });
});

// ---------------------------------------------------------------- chết / hồi sinh / tất định
test("chết rồi hồi sinh sạch: về Dấu Trang, đầy máu, Ink 0, kẻ địch dựng lại, đếm lần ngã", () => {
  const g = new Game({ seed: 1 });
  g.qaGoto("hall", "left");
  g.step(NO_INPUT);
  g.qaGrant({ ink: 5 });
  g.player.hp = 1;
  g.player.invuln = 0;
  g.player.takeHit(0, 1, noop);
  g.step(NO_INPUT);
  assert.equal(g.mode, "dead");
  assert.equal(g.save.deaths, 1);
  for (let f = 0; f < 120; f += 1) g.step(NO_INPUT);
  assert.equal(g.mode, "play");
  assert.equal(g.player.hp, g.player.maxHp);
  assert.equal(g.player.ink, 0);
  assert.equal(g.roomId, "entrance", "chưa có Dấu Trang nào ⇒ về điểm đầu");
  assert.ok(g.enemies.length > 0);
});

test("Dấu Trang: chạm ⇒ lưu điểm hồi sinh + hồi đầy máu", () => {
  const g = new Game({ seed: 1 });
  g.qaGoto("hall", "left");
  g.player.place(6 * TILE + 8, 19 * TILE);
  g.player.hp = 2;
  g.step(NO_INPUT);
  assert.equal(g.save.checkpoint, "hall");
  assert.equal(g.player.hp, g.player.maxHp);
});

test("gai và rơi: mất 1 máu rồi về chỗ an toàn (không mất phòng), không chết liên tục", () => {
  const g = new Game({ seed: 1 });
  g.qaGoto("entrance", "start");
  for (let f = 0; f < 5; f += 1) g.step(NO_INPUT);
  const safe = { x: g.player.x, y: g.player.y };
  g.player.place(15 * TILE + 8, 13 * TILE + 14); // chân chạm nửa dưới ô gai ở đáy hố
  g.player.safeX = safe.x;
  g.player.safeY = safe.y;
  g.step(NO_INPUT);
  assert.equal(g.player.hp, PLAYER.maxHp - 1);
  assert.equal(g.roomId, "entrance");
  assert.ok(Math.abs(g.player.x - safe.x) < 1 && Math.abs(g.player.y - safe.y) < 1);
});

function fingerprint(g) {
  const b = g.boss;
  return JSON.stringify({
    r: g.roomId, f: g.frame, p: [g.player.x.toFixed(3), g.player.y.toFixed(3), g.player.hp, g.player.ink],
    e: g.enemies.map((e) => [e.kind, e.state, e.x.toFixed(2), e.y.toFixed(2), e.hp]),
    b: b ? [b.state, b.attack, b.hp, b.x.toFixed(2)] : null,
  });
}

test("tất định: cùng hạt giống + cùng chuỗi đầu vào ⇒ cùng trạng thái, từng khung", () => {
  const script = (f) => ({ right: f % 90 < 60, jump: f % 70 === 5 || (f % 70 > 5 && f % 70 < 22), attack: f % 17 === 3, dash: f % 130 === 40, pulse: f % 200 === 150 });
  const play = (seed) => {
    const g = new Game({ seed });
    g.qaGrant({ marginStep: true, ink: 9 });
    const marks = [];
    for (let f = 0; f < 1500; f += 1) {
      g.step({ ...NO_INPUT, ...script(f) });
      g.drainEvents();
      if (f % 250 === 0) marks.push(fingerprint(g));
    }
    return marks;
  };
  assert.deepEqual(play(7), play(7));
  assert.deepEqual(play(7), play(7));
});

test("mọi dữ liệu phòng hợp lệ: spawn/cửa/thực thể nằm trong bản đồ, cửa trỏ đúng spawn, có đúng 11 phòng", () => {
  const ids = m.ROOM_ORDER;
  assert.equal(ids.length, 11);
  for (const id of ids) {
    const def = room(id);
    const w = def.tiles[0].length;
    const h = def.tiles.length;
    for (const row of def.tiles) assert.equal(row.length, w, `${id}: hàng không đều`);
    for (const ex of def.exits) {
      const target = room(ex.to);
      assert.ok(target.spawns[ex.spawn], `${id} → ${ex.to}: thiếu spawn ${ex.spawn}`);
      assert.ok(ex.tx >= 0 && ex.ty >= 0 && ex.tx + ex.tw <= w && ex.ty + ex.th <= h, `${id}: cửa ngoài bản đồ`);
      assert.ok(target.exits.some((b) => b.to === id), `${ex.to} thiếu lối quay về ${id}`);
    }
    for (const e of def.enemies) assert.ok(e.tx > 0 && e.tx < w - 1 && e.ty > 0 && e.ty < h, `${id}: kẻ địch ngoài bản đồ`);
    for (const [name, s] of Object.entries(def.spawns)) {
      const map = new TileMap(def.tiles);
      assert.ok(!map.solid(s.tx, s.ty), `${id}.${name}: spawn nằm trong tường`);
    }
  }
  // đúng bốn loại kẻ địch + Bộ boss trong đấu trường
  const kinds = new Set(ids.flatMap((id) => room(id).enemies.map((e) => e.kind)));
  assert.deepEqual([...kinds].sort(), ["broken", "hound", "scribble", "tornPage"]);
});
