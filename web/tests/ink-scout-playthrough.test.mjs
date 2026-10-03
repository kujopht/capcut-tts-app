/*
 * INK SCOUT — CHƠI THỬ TOÀN CHƯƠNG bằng bot vòng kín (chậm phản ứng 15 khung) trên mô phỏng thật.
 * Chứng minh: chương hoàn thành được từ đầu đến cuối, không soft-lock, mọi cổng khả năng/ký ức/boss/kết thúc đều đi qua được, và cả ba đường kết thúc.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { loadModule } from "./helpers/loadGameCore.mjs";
import { playGame, FULL_GOALS, MIN_GOALS } from "./helpers/bot.mjs";

const core = await loadModule();
const { ENDINGS } = core;

function summary(r) {
  const g = r.game;
  return { ok: r.ok, reason: r.reason, seconds: +(g.save.playFrames / 60).toFixed(1), deaths: g.save.deaths, mem: g.save.memories, step: g.save.marginStep, ending: g.save.ending, stats: r.bot.stats };
}

test("toàn chương, đường đủ ba Ký Ức: hoàn thành với kết thúc KHÔI PHỤC, đúng thứ tự khả năng", () => {
  const r = playGame(core, { seed: 1, goals: FULL_GOALS, ending: "restore", reaction: 15, stuckLimit: 60 * 40 });
  const s = summary(r);
  console.log("full/restore:", JSON.stringify({ ...s, stats: undefined }));
  assert.equal(r.ok, true, JSON.stringify(s));
  assert.deepEqual(s.mem, [1, 2, 3]);
  assert.equal(s.step, true);
  assert.equal(s.ending, "restore");
  assert.ok(r.game.save.bossDefeated);
  assert.ok(s.deaths <= 3, `quá nhiều lần ngã: ${s.deaths}`);
  assert.ok(s.seconds > 90 && s.seconds < 600, `thời gian bot ${s.seconds}s`);
  // Thứ tự thiết kế: Ký Ức I (Pulse) TRƯỚC Margin Step; Ký Ức II và III SAU Margin Step (cần quay lại).
  const order = r.timeline.map((t) => t.e).filter((e) => e.startsWith("memory:") || e.startsWith("ability:") || e === "complete");
  const iStep = order.indexOf("ability:marginStep");
  assert.ok(order.indexOf("memory:1") < iStep, `thứ tự: ${order}`);
  assert.ok(order.indexOf("memory:2") > iStep && order.indexOf("memory:3") > iStep, `thứ tự: ${order}`);
  assert.equal(order[order.length - 1], "complete");
  const res = r.game.result();
  assert.equal(res.ending, "restore");
  assert.equal(res.memories.length, 3);
});

test("đường tối thiểu (không chủ động đi nhặt ký ức): vẫn hoàn thành, kết thúc cơ bản (0–1 ký ức), không có lựa chọn", () => {
  const r = playGame(core, { seed: 2, goals: MIN_GOALS, ending: "restore", reaction: 15, stuckLimit: 60 * 40 });
  const s = summary(r);
  console.log("min/basic:", JSON.stringify({ ...s, stats: undefined }));
  assert.equal(r.ok, true, JSON.stringify(s));
  assert.ok(s.mem.length <= 1, `đường tối thiểu chỉ có thể tình cờ nhặt ≤ 1 ký ức: ${s.mem}`);
  assert.equal(s.ending, "basic");
  assert.deepEqual(r.game.endingPages(), ENDINGS.basic.pages);
});

test("ba đường kết thúc: cơ bản (0–1), mở rộng (2 ký ức: thoại thêm), XOÁ và KHÔI PHỤC (3 ký ức, có lựa chọn)", () => {
  const finish = (memories, ending) => {
    const goals = [{ room: "arena", key: "bossTrigger" }, { room: "ending", key: "endingTrigger" }];
    return playGame(core, {
      seed: 5,
      goals,
      ending,
      reaction: 15,
      stuckLimit: 60 * 40,
      setup: (g) => {
        g.qaGrant({ marginStep: true, memories });
        g.save.checkpoint = "bookmark";
        g.qaGoto("arena", "left");
      },
    });
  };
  const two = finish([1, 2], "restore");
  assert.equal(two.ok, true);
  assert.equal(two.game.save.ending, "basic", "2 ký ức: vẫn là kết thúc cơ bản (không có lựa chọn)…");
  assert.deepEqual(two.game.endingPages(), ENDINGS.basic2.pages, "…nhưng có thêm đoạn sự thật của Redactor");
  const erase = finish([1, 2, 3], "erase");
  assert.equal(erase.ok, true);
  assert.equal(erase.game.save.ending, "erase");
  const restore = finish([1, 2, 3], "restore");
  assert.equal(restore.ok, true);
  assert.equal(restore.game.save.ending, "restore");
  assert.ok(ENDINGS.restore.pages.some((p) => p.includes("CURATOR")), "KHÔI PHỤC dẫn tới The Curator (móc cho chương sau)");
});

test("lưu giữa chừng rồi tải lại: ký ức/khả năng giữ nguyên, tiếp tục từ Dấu Trang và vẫn hoàn thành", () => {
  const first = playGame(core, {
    seed: 3,
    goals: FULL_GOALS,
    ending: "erase",
    reaction: 15,
    stuckLimit: 60 * 40,
    stop: (g) => g.save.memories.length === 2 && g.save.marginStep,
  });
  const snap = first.game.snapshot();
  assert.ok(snap.memories.length >= 2 && snap.marginStep);
  const resumed = playGame(core, { seed: 4, save: snap, goals: FULL_GOALS, ending: "erase", reaction: 15, stuckLimit: 60 * 40 });
  assert.equal(resumed.ok, true, JSON.stringify(summary(resumed)));
  assert.equal(resumed.game.save.ending, "erase");
});
