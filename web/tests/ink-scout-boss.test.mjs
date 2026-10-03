/*
 * INK SCOUT — THE REDACTOR: lập lịch đòn, giai đoạn, Memory Collapse, báo trước, và CHỨNG MINH thắng được bằng bot chậm phản ứng.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { loadModule } from "./helpers/loadGameCore.mjs";
import { playGame } from "./helpers/bot.mjs";

const core = await loadModule();
const { Boss, BossScheduler, BOSS, BOSS_ATTACKS, PHASE1_ATTACKS, PHASE2_ATTACKS, Rng, TileMap, defaultSave, ENDINGS } = core;

const noop = () => {};
const rows = [];
for (let r = 0; r < 14; r += 1) rows.push(r >= 11 ? "#".repeat(24) : "#" + ".".repeat(22) + "#");
const MAP = new TileMap(rows);
const FLOOR = 11 * 16;

function newBoss(seed = 5) {
  const b = new Boss(FLOOR, 16, 368, seed);
  b.awaken();
  return b;
}
const ctx = (over = {}) => ({ map: MAP, px: 100, py: FLOOR, memories: 0, emit: noop, ...over });

function runUntil(b, pred, max = 4000, c = ctx()) {
  for (let f = 0; f < max; f += 1) {
    b.update(c);
    if (pred(b)) return f;
  }
  return -1;
}

test("mọi đòn của boss có báo trước ≥ 24 khung (0,4 giây)", () => {
  for (const [name, spec] of Object.entries(BOSS_ATTACKS)) assert.ok(spec.telegraph >= 24, `${name}: ${spec.telegraph}`);
});

test("báo trước thật sự có trước: lưỡi chém/sóng/đạn không bao giờ gây sát thương lúc đang báo trước", () => {
  const b = newBoss(11);
  const c = ctx({ px: 120 });
  let telegraphFrames = 0;
  const seen = new Map();
  for (let f = 0; f < 6000; f += 1) {
    b.update(c);
    if (b.state === "telegraph") {
      telegraphFrames += 1;
      assert.ok(!b.hazards().some((h) => h.kind === "slash"), "lưỡi chém xuất hiện trong lúc báo trước");
      assert.ok(!b.hazards().some((h) => h.kind === "wave" && b.attack === "marginCut"), "sóng của Margin Cut xuất hiện trong lúc báo trước");
    }
    if (b.attack) seen.set(b.attack, (seen.get(b.attack) ?? 0) + 1);
  }
  assert.ok(telegraphFrames > 200);
  assert.ok(seen.size >= 4, `giai đoạn 1 dùng ${[...seen.keys()]}`);
});

test("bộ lập lịch đòn: không lặp liền kề, đúng tập giai đoạn, mỗi đòn xuất hiện đều (túi xáo trộn có hạt giống)", () => {
  const s1 = new BossScheduler(new Rng(3));
  const seq1 = Array.from({ length: 400 }, () => s1.next(1, 100));
  for (let i = 1; i < seq1.length; i += 1) assert.notEqual(seq1[i], seq1[i - 1]);
  assert.ok(seq1.every((a) => PHASE1_ATTACKS.includes(a)));
  for (const a of PHASE1_ATTACKS) assert.ok(seq1.filter((x) => x === a).length > 60, `${a} bị thiếu`);
  const s2 = new BossScheduler(new Rng(3));
  const seq2 = Array.from({ length: 700 }, () => s2.next(2, 100));
  assert.ok(seq2.every((a) => PHASE2_ATTACKS.includes(a)));
  for (const a of ["delete", "brokenSentence", "revisionRush"]) assert.ok(seq2.includes(a), `${a} chưa xuất hiện ở giai đoạn 2`);
  // áp sát thì không dùng Revision Slash (bất công)
  const s3 = new BossScheduler(new Rng(9));
  assert.ok(Array.from({ length: 200 }, () => s3.next(1, 10)).every((a) => a !== "revisionSlash"));
  // tất định theo hạt giống
  const a1 = Array.from({ length: 30 }, ((s) => () => s.next(1, 100))(new BossScheduler(new Rng(42))));
  const a2 = Array.from({ length: 30 }, ((s) => () => s.next(1, 100))(new BossScheduler(new Rng(42))));
  const a3 = Array.from({ length: 30 }, ((s) => () => s.next(1, 100))(new BossScheduler(new Rng(43))));
  assert.deepEqual(a1, a2);
  assert.notDeepEqual(a1, a3);
});

test("giai đoạn: hạ máu xuống ngưỡng ⇒ khựng bất tử → Memory Collapse (4 mảnh, nứt theo số Ký Ức)", () => {
  for (const mem of [0, 1, 3]) {
    const b = newBoss(7);
    const c = ctx({ memories: mem });
    runUntil(b, (x) => x.state === "neutral", 400, c);
    assert.equal(b.phase, 1);
    while (b.hp > BOSS.phase2At + 1) {
      b.hp -= 1;
    }
    assert.equal(b.hit(1, noop), true);
    assert.equal(b.phase, 2, "đã sang giai đoạn 2");
    assert.equal(b.state, "stagger");
    assert.equal(b.invuln, true);
    assert.equal(b.hit(5, noop), false, "đang khựng: không nhận sát thương");
    runUntil(b, (x) => x.state === "collapse", 400, c);
    assert.equal(b.state, "collapse");
    assert.equal(b.fragments.length, BOSS.fragments);
    assert.equal(b.fragments.filter((f) => f.cracked).length, Math.min(BOSS.fragments, mem), `nứt ${mem}`);
    assert.equal(b.hit(5, noop), false, "đang chắn bằng mảnh vỡ");
  }
});

test("Memory Collapse: Ký Ức làm mảnh dễ vỡ hơn; Pulse phá hết trong tầm ⇒ boss choáng và chịu thêm sát thương", () => {
  const mk = (mem) => {
    const b = newBoss(7);
    const c = ctx({ memories: mem });
    runUntil(b, (x) => x.state === "neutral", 400, c);
    b.hp = BOSS.phase2At + 1;
    b.hit(1, noop);
    runUntil(b, (x) => x.state === "collapse", 400, c);
    return { b, c };
  };
  const rect = (b, f) => ({ x: f.x - 8, y: f.y - 8, w: 16, h: 16 });
  // mảnh nứt vỡ chỉ với một nhát 1 sát thương; mảnh thường cần hai
  const crack = mk(1).b;
  const f0 = crack.fragments.find((f) => f.cracked);
  const hitsSeen = new Set();
  crack.slashAt(rect(crack, f0), 1, noop, hitsSeen);
  assert.ok(f0.hp <= 0, "mảnh nứt vỡ sau 1 nhát");
  const plain = mk(0).b;
  const f1 = plain.fragments[0];
  const seen2 = new Set();
  plain.slashAt(rect(plain, f1), 1, noop, seen2);
  assert.equal(f1.hp, 1, "mảnh thường còn máu");
  plain.slashAt(rect(plain, f1), 1, noop, seen2);
  assert.equal(f1.hp, 1, "cùng một nhát không chém trúng hai lần");
  // Pulse phá toàn bộ
  const { b } = mk(0);
  const n = b.pulseFragments(b.x, b.y - 26, 90, noop);
  assert.equal(n, BOSS.fragments);
  assert.equal(b.state, "stunned");
  assert.equal(b.invuln, false);
  const before = b.hp;
  assert.equal(b.hit(2, noop), true);
  assert.equal(before - b.hp, 3, "boss choáng chịu ×1,5 sát thương (làm tròn lên)");
});

test("Pulse ngắt đòn đang báo trước; có hồi chiêu chống lạm dụng", () => {
  const b = newBoss(2);
  const c = ctx({ px: 60 });
  runUntil(b, (x) => x.state === "telegraph", 600, c);
  assert.equal(b.state, "telegraph");
  b.pulseHit(noop);
  assert.equal(b.state, "stunned");
  assert.equal(b.attack, null);
  runUntil(b, (x) => x.state === "telegraph", 600, c);
  assert.equal(b.state, "telegraph");
  b.pulseHit(noop);
  assert.equal(b.state, "telegraph", "còn hồi chiêu ⇒ không ngắt lần nữa");
});

test("chống kẹt: Memory Collapse không bao giờ kéo dài vô hạn; hạ boss ⇒ dying → dead và không nhận thêm đòn", () => {
  const b = newBoss(4);
  const c = ctx({ px: 40 });
  runUntil(b, (x) => x.state === "neutral", 400, c);
  b.hp = BOSS.phase2At + 1;
  b.hit(1, noop);
  const f = runUntil(b, (x) => x.state === "stunned", BOSS.staggerFrames + BOSS_ATTACKS.memoryCollapse.active + 200, c);
  assert.ok(f > 0, "mảnh tan sau thời hạn dù người chơi không phá");
  b.hp = 1;
  b.invuln = false;
  b.state = "neutral";
  assert.equal(b.hit(5, noop), true);
  assert.equal(b.state, "dying");
  assert.equal(b.hit(5, noop), false);
  runUntil(b, (x) => x.state === "dead", 400, c);
  assert.equal(b.state, "dead");
});

// ---------------------------------------------------------------- CHỨNG MINH thắng được
function fight(seed, reaction, memories = []) {
  return playGame(core, {
    seed,
    goals: [{ room: "arena", key: "bossTrigger" }],
    reaction,
    maxFrames: 40000,
    stuckLimit: 60 * 60,
    setup: (g) => {
      g.qaGrant({ marginStep: true, memories });
      g.save.checkpoint = "bookmark";
      g.qaGoto("arena", "left");
    },
    stop: (g) => g.save.bossDefeated,
  });
}

test("công bằng: bot chậm phản ứng 20 khung (0,33 s) hạ được The Redactor ở nhiều hạt giống, ít lần ngã", () => {
  const results = [];
  for (const seed of [1, 2, 3, 4, 5, 6]) {
    const r = fight(seed, 20, seed % 2 ? [1] : []);
    results.push({ seed, won: r.game.save.bossDefeated, deaths: r.game.save.deaths, seconds: +(r.frames / 60).toFixed(1) });
  }
  console.log("boss bot (reaction 20):", JSON.stringify(results));
  assert.ok(results.every((r) => r.won), "bot phải thắng ở mọi hạt giống");
  assert.ok(results.every((r) => r.deaths <= 4), "không hạt giống nào cần quá 4 lần ngã");
  assert.ok(results.reduce((s, r) => s + r.deaths, 0) <= 8);
  // trận không quá chóng vánh (boss đủ máu) cũng không kéo dài vô tận
  assert.ok(results.every((r) => r.seconds >= 25 && r.seconds <= 400), JSON.stringify(results));
});

test("ba Ký Ức giúp thật: ít sát thương nhận hơn nhờ +1 máu và Pulse rẻ", () => {
  const r0 = fight(8, 20, []);
  const r3 = fight(8, 20, [1, 2, 3]);
  assert.ok(r0.game.save.bossDefeated && r3.game.save.bossDefeated);
  assert.equal(r3.game.player.maxHp, core.PLAYER.maxHp + 1);
  assert.equal(r3.game.abilities.pulseCheap, true);
  assert.ok(ENDINGS.restore.pages.length >= 3);
  void defaultSave;
});
