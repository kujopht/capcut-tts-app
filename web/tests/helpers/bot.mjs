/**
 * Bot chơi thử (test/QA — không vào bundle game): điều khiển vòng kín qua `InputState`, đi theo đồ thị khả năng tiếp cận của `nav.mjs`,
 * đánh kẻ địch bằng phản xạ đơn giản, và đấu boss bằng bộ não CHẬM PHẢN ỨNG `reaction` khung hình (mặc định 15 ≈ 0,25 s): bot chỉ thấy trạng
 * thái boss của `reaction` khung hình trước rồi ngoại suy theo lịch báo trước — nghĩa là mọi đòn của boss phải né được chỉ với thông tin
 * một người chơi thật có từ lúc báo trước bắt đầu. Bot THUA ⇒ đòn đó báo trước chưa đủ; bot THẮNG ⇒ chứng minh có chiến lược khả thi.
 */
import { buildNav, macroInput } from "./nav.mjs";

const IDLE = Object.freeze({ left: false, right: false, jump: false, attack: false, pulse: false, dash: false, confirm: false });

export const FULL_GOALS = [
  { room: "echo", key: "memory:1" },
  { room: "shrine", key: "marginStep" },
  { room: "sealed", key: "memory:2" },
  { room: "secret", key: "memory:3" },
  { room: "bookmark", key: "checkpoint:bookmark" },
  { room: "arena", key: "bossTrigger" },
  { room: "ending", key: "endingTrigger" },
];

/** Đường nhanh nhất: bỏ mọi ký ức, chỉ lấy Margin Step (cần để qua khe 5 ô tới boss). */
export const MIN_GOALS = [
  { room: "shrine", key: "marginStep" },
  { room: "bookmark", key: "checkpoint:bookmark" },
  { room: "arena", key: "bossTrigger" },
  { room: "ending", key: "endingTrigger" },
];

export function createBot(core, game, opts = {}) {
  const { TILE, cycleState, rooms, BOSS_ATTACKS } = core;
  const goals = opts.goals ?? FULL_GOALS;
  const reaction = opts.reaction ?? 15;
  const wantEnding = opts.ending ?? "restore";
  let gi = 0;
  const navCache = new Map();
  let macro = null;
  let settle = 0;
  let toggle = 0;
  let stuckFrames = 0;
  let lastProgress = 0;
  let lastPos = "";
  const stats = { macros: 0, replans: 0, noPlan: 0, fights: 0, bossFrames: 0, bossStart: -1, bossEnd: -1, pulses: 0 };
  const hist = [];
  let sched = [];
  const planned = new Set();
  const shotPlanned = new Set();

  function getNav(rid) {
    const k = `${rid}:${game.save.marginStep ? 1 : 0}`;
    let n = navCache.get(k);
    if (!n) {
      n = buildNav(core, rid, { marginStep: game.save.marginStep, glyphs: true });
      navCache.set(k, n);
    }
    return n;
  }

  function goalDone(g) {
    const s = game.save;
    if (g.key.startsWith("memory:")) return game.has(Number(g.key.split(":")[1]));
    if (g.key === "marginStep") return s.marginStep;
    if (g.key.startsWith("checkpoint:")) return s.checkpoint === g.key.split(":")[1];
    if (g.key === "bossTrigger") return s.bossDefeated;
    if (g.key === "endingTrigger") return game.mode === "ending" || game.mode === "complete";
    return false;
  }

  function nextRoom(from, to) {
    if (from === to) return from;
    const all = rooms();
    const prev = new Map([[from, null]]);
    const q = [from];
    for (let i = 0; i < q.length; i += 1) {
      const u = q[i];
      for (const ex of all[u].exits) {
        if (prev.has(ex.to)) continue;
        prev.set(ex.to, u);
        q.push(ex.to);
      }
    }
    if (!prev.has(to)) return null;
    let cur = to;
    while (prev.get(cur) !== from) cur = prev.get(cur);
    return cur;
  }

  // ------------------------------------------------------------------ chiến đấu thường
  function aliveEnemies() {
    return game.enemies.filter((e) => e.state !== "dying");
  }

  function groundAhead(dir) {
    const p = game.player;
    return game.map.groundBelow({ x: p.x + dir * 10, y: p.y, w: 8, h: 16 }) && !game.map.hitsSpike({ x: p.x + dir * 10, y: p.y - 2, w: 8, h: 16 });
  }

  let evade = 0;
  const ignoreUntil = new Map();
  let engaged = null;

  /**
   * Chiến thuật người thật: đứng ngoài tầm khi kẻ địch báo trước, NHẢY QUA cú lao khi nó tới, rồi áp sát chém trong lúc nó hồi phục.
   * Torn Page: tránh ngang khi nó bổ nhào, chém khi nó bay thấp quay về.
   */
  function combat() {
    const p = game.player;
    const wantInk = needInk();
    let best = null;
    let bestD = 1e9;
    for (const e of aliveEnemies()) {
      if ((ignoreUntil.get(e.id) ?? 0) > game.frame) continue;
      const dx = e.x - p.x;
      const dy = e.y - p.y;
      const flying = e.spec.flying;
      const lim = wantInk ? 170 : flying ? 90 : 110;
      // Kẻ đi bộ ở KHÁC tầng sàn thì không tới chém được — đừng đứng vung gươm vào khoảng không.
      const yl = wantInk ? 60 : flying ? 90 : 14;
      if (Math.abs(dx) < lim && Math.abs(dy) < yl) {
        const d = Math.abs(dx) + Math.abs(dy) * 0.5;
        if (d < bestD) {
          bestD = d;
          best = e;
        }
      }
    }
    if (!best) {
      engaged = null;
      return null;
    }
    // Chống kẹt: giao chiến > 240 khung mà mục tiêu không mất máu ⇒ bỏ qua nó một lúc.
    if (!engaged || engaged.id !== best.id) engaged = { id: best.id, hp: best.hp, since: game.frame };
    else if (best.hp < engaged.hp) engaged = { id: best.id, hp: best.hp, since: game.frame };
    else if (game.frame - engaged.since > 240) {
      ignoreUntil.set(best.id, game.frame + 600);
      engaged = null;
      return null;
    }
    stats.fights += 1;
    // Memory Pulse làm choáng mọi kẻ địch quanh mình: dùng Ink dư để mở "cửa sổ chém miễn phí" (trừ ở Phòng Vọng, nơi Ink dành cho bệ glyph).
    if (p.pulseT === 0 && p.ink >= p.pulseCost(game.abilities) && (game.roomId !== "echo" || p.hp <= 2)) {
      const close = aliveEnemies().some((x) => x.stun === 0 && Math.hypot(x.x - p.x, x.y - x.spec.h / 2 - (p.y - 8)) < 44 + x.spec.w / 2);
      if (close) {
        stats.pulses += 1;
        return { ...IDLE, pulse: true };
      }
    }
    const e = best;
    const dx = e.x - p.x;
    const dir = dx >= 0 ? 1 : -1;
    const dist = Math.abs(dx);
    const input = { ...IDLE };
    const go = (d) => {
      if (d > 0) input.right = true;
      else input.left = true;
    };

    if (e.spec.flying) {
      if (e.state === "telegraph" || e.state === "dive") {
        const lockX = e.state === "dive" ? e.lockX : p.x;
        if (e.state === "dive" && Math.abs(p.x - lockX) < 26) {
          const away = p.x >= lockX ? 1 : -1;
          if (groundAhead(away)) go(away);
          else if (groundAhead(-away)) go(-away);
        }
        return input;
      }
      const lowAndNear = dist < 30 && Math.abs(e.y - e.spec.h / 2 - (p.y - 8)) < 22;
      if (lowAndNear) return swing(e, dir, input);
      return null;
    }

    const telegraphing = e.state === "notice" || e.state === "crouch";
    const lunging = e.state === "lunge" || e.state === "charge" || e.state === "slam";
    if (lunging && e.stun === 0) {
      if (dist < 42 && p.onGround) {
        evade = 8;
        return { ...IDLE, jump: true };
      }
      return input;
    }
    if (telegraphing && e.stun === 0) {
      const safe = e.kind === "broken" ? 56 : 52;
      if (dist < safe && groundAhead(-dir)) go(-dir);
      return input;
    }
    // patrol / recover / bị choáng / skid: áp sát và chém
    const reach = 26 + e.spec.w / 2 - 6;
    if (dist > reach) {
      if (groundAhead(dir)) go(dir);
      return input;
    }
    return swing(e, dir, input);
  }

  /** Quay mặt về kẻ địch (một khung riêng, vì đòn đang diễn ra không đổi hướng), rồi chém liên tục và nối combo. */
  function swing(e, dir, input) {
    const p = game.player;
    if (p.facing !== dir && p.attackKind === "none") {
      if (dir > 0) input.right = true;
      else input.left = true;
      return input;
    }
    input.attack = p.attackKind === "none" || (p.attackT >= 5 && p.attackT <= 12 && p.attackKind !== "air");
    return input;
  }

  function needInk() {
    const goal = goals[gi];
    if (!goal || game.roomId !== "echo" || game.has(1)) return false;
    const p = game.player;
    return p.ink < p.pulseCost(game.abilities);
  }

  let lastGlyphPulse = -1000;
  /** Echo: gọi Memory Pulse khi còn bệ glyph ẩn trong tầm Pulse (56 px). */
  function glyphPulse() {
    if (game.roomId !== "echo") return null;
    const p = game.player;
    if (p.pulseT > 0 || p.ink < p.pulseCost(game.abilities) || !p.onGround) return null;
    const m = game.map;
    let hidden = 0;
    let shown = 0;
    for (let ty = 0; ty < m.h; ty += 1) {
      for (let tx = 0; tx < m.w; tx += 1) {
        if (m.kind(tx, ty) !== 4) continue;
        const dx = tx * TILE + 8 - p.x;
        const dy = ty * TILE + 8 - (p.y - 8);
        if (Math.hypot(dx, dy) > 54) continue;
        if (m.glyphRevealed(tx, ty)) shown += 1;
        else hidden += 1;
      }
    }
    void shown;
    if (hidden > 0 && game.frame - lastGlyphPulse > 90) {
      lastGlyphPulse = game.frame;
      stats.pulses += 1;
      return { ...IDLE, pulse: true };
    }
    return null;
  }

  function cycleBlock(m) {
    const p = game.player;
    const dir = m.dir !== 0 ? m.dir : 0;
    for (const c of game.def.cycles) {
      const cx = c.tx * TILE + (c.tw * TILE) / 2;
      const ahead = dir === 0 ? Math.abs(cx - p.x) < 30 : (cx - p.x) * dir > -10 && (cx - p.x) * dir < 110;
      if (!ahead) continue;
      const st = cycleState(c, game.roomT);
      const remainIdle = c.period - c.telegraph - c.active; // tổng nghỉ
      void remainIdle;
      if (st.phase !== 0) return true;
      // đang nghỉ nhưng sắp báo trước (còn < 70 khung) → chờ cho xong chu kỳ kế
      const untilTele = c.period - ((game.roomT + c.offset) % c.period);
      if (untilTele < 90 && (cx - p.x) * dir < 110) return true;
    }
    return false;
  }

  // ------------------------------------------------------------------ boss
  function observeBoss() {
    const b = game.boss;
    hist.push({
      f: game.frame,
      state: b.state,
      attack: b.attack,
      t: b.t,
      step: b.step,
      x: b.x,
      facing: b.facing,
      phase: b.phase,
      lines: b.lines.map((l) => ({ x: l.rect.x, w: l.rect.w, horizontal: l.horizontal, t: l.t, telegraph: l.telegraph, active: l.active })),
      zones: b.zones.map((z) => ({ x: z.x, w: z.w, t: z.t, telegraph: z.telegraph, active: z.active })),
      shots: b.shots.map((s) => ({ id: s.id, x: s.x, y: s.y, vx: s.vx, vy: s.vy })),
    });
    if (hist.length > reaction + 1) hist.shift();
  }

  function addWin(from, to, patch) {
    sched.push({ from, to, ...patch });
  }

  function jumpWin(J) {
    const nf = game.frame + 1;
    const j = Math.max(nf, Math.round(J));
    addWin(j, j + 24, { jump: true });
  }

  function planFromObs(o) {
    const p = game.player;
    const nf = game.frame + 1;
    const key = `${o.attack}:${o.f - o.t}`;
    if (o.state === "telegraph" && o.attack) {
      const spec = BOSS_ATTACKS[o.attack];
      const A = o.f + (spec.telegraph - o.t);
      const d = Math.abs(p.x - o.x);
      if (o.attack === "revisionSlash" && !planned.has(key)) {
        planned.add(key);
        const C = A + Math.max(0, (d - 38) / 4.6);
        jumpWin(C - 8);
      } else if (o.attack === "marginCut" && !planned.has(key)) {
        planned.add(key);
        const C = A + Math.max(0, (d - 11) / 2.2);
        jumpWin(C - 8);
      } else if (o.attack === "rewrite" && !planned.has(key)) {
        planned.add(key);
        jumpWin(A + 24);
      } else if (o.attack === "blackLine" && !planned.has(key) && o.lines.length > 0) {
        planned.add(key);
        const ln = o.lines[0];
        if (ln.horizontal) {
          jumpWin(A - 4);
        } else if (p.x > ln.x - 8 && p.x < ln.x + ln.w + 8) {
          const out = p.x < ln.x + ln.w / 2 ? -1 : 1;
          const edge = out < 0 ? ln.x - 10 : ln.x + ln.w + 10;
          const frames = Math.ceil(Math.abs(edge - p.x) / 1.6) + 3;
          addWin(nf, nf + frames, out < 0 ? { left: true } : { right: true });
        }
      } else if (o.attack === "delete" && !planned.has(key) && o.zones.length > 0) {
        planned.add(key);
        const z = o.zones[0];
        const off = p.x - z.x;
        if (Math.abs(off) < z.w / 2 + 8) {
          const out = off < 0 ? -1 : 1;
          const edge = z.x + out * (z.w / 2 + 12);
          const frames = Math.ceil(Math.abs(edge - p.x) / 1.6) + 3;
          addWin(nf, nf + frames, out < 0 ? { left: true } : { right: true });
        }
      }
    }
    if (o.state === "active" && o.attack === "revisionRush") {
      const per = 56;
      const seg = Math.floor(o.t / per);
      const k2 = `rush:${o.f - o.t}:${seg}`;
      if (seg < 3 && !planned.has(k2)) {
        planned.add(k2);
        const segStart = o.f - o.t + seg * per;
        const dashStart = segStart + 30;
        const d = Math.abs(p.x - o.x);
        const C = dashStart + Math.max(0, (d - 36) / 5.2);
        jumpWin(C - 7);
      }
    }
  }

  function windowInput() {
    const nf = game.frame + 1;
    const input = { ...IDLE };
    sched = sched.filter((w) => w.to >= nf);
    for (const w of sched) {
      if (nf >= w.from && nf < w.to) {
        if (w.jump) input.jump = true;
        if (w.left) input.left = true;
        if (w.right) input.right = true;
        if (w.dash) input.dash = true;
      }
    }
    return input;
  }

  function nearestShotThreat() {
    const o = hist[0];
    if (!o) return null;
    const p = game.player;
    const age = game.frame - o.f;
    let best = null;
    for (const s of o.shots) {
      const px = s.x + s.vx * age;
      const py = s.y + s.vy * age;
      for (let k = 0; k <= 40; k += 1) {
        const x = px + s.vx * k;
        const y = py + s.vy * k;
        if (Math.abs(x - p.x) < 10 && y > p.y - 20 && y < p.y + 4) {
          if (!best || k < best.k) best = { k, x, y, dir: s.vx >= 0 ? -1 : 1, sx: px, sy: py };
          break;
        }
      }
    }
    return best;
  }

  function bossStep() {
    const b = game.boss;
    const p = game.player;
    observeBoss();
    const o = hist[0];
    planFromObs(o);
    const input = windowInput();
    const nf = game.frame + 1;
    const busyJump = sched.some((w) => w.jump && nf >= w.from - 6 && nf < w.to);
    const busyRun = sched.some((w) => (w.left || w.right) && nf >= w.from && nf < w.to);
    if (input.jump || input.left || input.right) return input;

    // Cột/vùng nguy hiểm đứng yên (Delete, Black Line dọc) đang hiện: không đứng trong, không bước vào (người chơi thấy chúng ngay).
    const cols = [];
    for (const z of o.zones) cols.push({ x0: z.x - z.w / 2, x1: z.x + z.w / 2 });
    for (const l of o.lines) if (!l.horizontal) cols.push({ x0: l.x, x1: l.x + l.w });
    for (const c of cols) {
      if (p.x > c.x0 - 6 && p.x < c.x1 + 6) {
        const out = p.x < (c.x0 + c.x1) / 2 ? -1 : 1;
        return { ...IDLE, left: out < 0, right: out > 0 };
      }
    }
    const blockedAhead = (dir) => cols.some((c) => p.x + dir * 10 > c.x0 - 8 && p.x + dir * 10 < c.x1 + 8 && !(p.x > c.x0 - 6 && p.x < c.x1 + 6));

    // Memory Collapse: gọi Pulse sát tâm boss, không có Ink thì chém mảnh.
    if (b.state === "collapse") {
      const dx = b.x - p.x;
      if (p.ink >= p.pulseCost(game.abilities) && p.pulseT === 0) {
        if (Math.abs(dx) > 10) {
          return { ...IDLE, left: dx < 0, right: dx > 0 };
        }
        stats.pulses += 1;
        return { ...IDLE, pulse: true };
      }
      const frag = b.fragments.filter((f) => f.hp > 0).sort((a, c) => Math.hypot(a.x - p.x, a.y - p.y) - Math.hypot(c.x - p.x, c.y - p.y))[0];
      if (frag) {
        const fx = frag.x - p.x;
        const close = Math.abs(fx) < 24 && Math.abs(frag.y - (p.y - 8)) < 22;
        const inp = { ...IDLE, left: fx < -22, right: fx > 22, jump: frag.y < p.y - 30 && Math.abs(fx) < 30 && p.onGround };
        if (close) return swing({ spec: { w: 0 } }, fx >= 0 ? 1 : -1, inp);
        return inp;
      }
      return { ...IDLE };
    }

    // Đạn: chém khi sắp tới (thưởng Ink), chỉ khi không bận nhảy né.
    const th = nearestShotThreat();
    if (th && th.k <= 16 && !busyJump && !busyRun) {
      const dirTo = th.dir === -1 ? 1 : -1;
      return swing({ spec: { w: 0 } }, dirTo, { ...IDLE });
    }

    if (b.state === "dormant" || b.state === "intro" || b.state === "stagger" || b.state === "dying" || b.invuln) {
      // chờ: lùi giữa phòng để có chỗ
      const mid = (b.left + b.right) / 2;
      const dx = mid - p.x;
      return Math.abs(dx) > 40 && b.state !== "dying" ? { ...IDLE, left: dx < 0, right: dx > 0 } : { ...IDLE };
    }

    // Pulse cắt đòn đang báo trước khi có Ink (hồi chiêu 600 khung giữ cho không lạm dụng).
    if (b.state === "telegraph" && b.pulseCooldown === 0 && p.ink >= p.pulseCost(game.abilities) && Math.abs(b.x - p.x) < 40 && p.pulseT === 0 && !busyJump && o.attack !== "rewrite" && opts.pulseInterrupt) {
      stats.pulses += 1;
      return { ...IDLE, pulse: true };
    }

    // Tấn công: áp sát, chém. Không tiến vào khi sắp phải nhảy né.
    const dx = b.x - p.x;
    const dist = Math.abs(dx);
    const reach = 24;
    if (dist > reach) {
      if (busyJump || blockedAhead(dx >= 0 ? 1 : -1)) return { ...IDLE };
      return { ...IDLE, left: dx < 0, right: dx > 0 };
    }
    if (busyJump) return { ...IDLE };
    return swing({ spec: { w: 0 } }, dx >= 0 ? 1 : -1, { ...IDLE });
  }

  // ------------------------------------------------------------------ vòng chính
  function settled() {
    const p = game.player;
    return p.onGround && !p.dashing && p.hurt === 0 && Math.abs(p.vx) < 0.06 && p.pulseT === 0;
  }

  function trackStuck() {
    const p = game.player;
    const pos = `${game.roomId}:${Math.round(p.x / 8)}:${Math.round(p.y / 8)}:${gi}:${game.save.memories.length}`;
    if (pos !== lastPos) {
      lastPos = pos;
      lastProgress = game.frame;
    }
    stuckFrames = game.frame - lastProgress;
  }

  let prevAtk = false;
  let prevPulse = false;

  /** Mọi nút "bấm" (chém, Pulse) phải có cạnh lên: nhả ít nhất một khung giữa hai lần bấm. */
  function next() {
    const input = nextInner();
    if (input.attack && prevAtk) input.attack = false;
    if (input.pulse && prevPulse) input.pulse = false;
    prevAtk = input.attack;
    prevPulse = input.pulse;
    return input;
  }

  function nextInner() {
    const g = game;
    if (g.mode === "read") {
      toggle += 1;
      return toggle > 36 ? { ...IDLE, confirm: toggle % 2 === 0 } : { ...IDLE };
    }
    if (g.mode === "dead" || g.mode === "complete") {
      macro = null;
      sched = [];
      toggle = 0;
      return { ...IDLE };
    }
    if (g.mode === "ending") {
      toggle += 1;
      if (g.endingStage === "choice") {
        const want = wantEnding === "erase" ? 0 : 1;
        if (g.endingChoice !== want) return { ...IDLE, left: want === 0 && toggle % 2 === 0, right: want === 1 && toggle % 2 === 0 };
        return toggle > 40 ? { ...IDLE, confirm: toggle % 2 === 0 } : { ...IDLE };
      }
      return toggle > 24 ? { ...IDLE, confirm: toggle % 2 === 0 } : { ...IDLE };
    }
    while (gi < goals.length && goalDone(goals[gi])) gi += 1;
    trackStuck();

    // boss
    const b = g.boss;
    if (b && b.active && g.roomId === "arena") {
      if (stats.bossStart < 0) stats.bossStart = g.frame;
      stats.bossFrames += 1;
      macro = null;
      return bossStep();
    }
    if (hist.length) {
      hist.length = 0;
      sched = [];
    }
    if (gi >= goals.length) return { ...IDLE };

    const p = g.player;
    if (p.hurt > 0 && macro) {
      macro = null;
      settle = 0;
    }
    if (macro) {
      const m = macro.m;
      const len = Math.max(m.hold, m.dirHold, (m.dash ?? -1) + 2);
      if (!p.onGround) macro.airborne = true;
      else if (macro.airborne) macro.cut = true;
      if (!macro.cut && macro.f < len) {
        const input = macroInput(m, macro.f);
        macro.f += 1;
        return input;
      }
      // sau macro: chờ đáp xuống và đứng yên
      if (settled()) {
        settle += 1;
        if (settle >= 3) {
          macro = null;
          settle = 0;
        }
      } else if (p.onGround === false && macro.f > 300) {
        macro = null;
      } else {
        settle = 0;
        macro.f += 1;
        if (macro.f > 340) macro = null;
      }
      return { ...IDLE };
    }
    if (evade > 0) {
      // giữ nút nhảy suốt cú nhảy né (kể cả khi đang ở trên không)
      evade -= 1;
      return p.hurt > 0 ? { ...IDLE } : { ...IDLE, jump: true };
    }
    if (!p.onGround || p.hurt > 0) return { ...IDLE };

    const gp = glyphPulse();
    if (gp) return gp;
    const fight = combat();
    if (fight) return fight;
    if (!settled()) return { ...IDLE };

    // lập kế hoạch
    const goal = goals[gi];
    const rid = g.roomId;
    let key;
    if (goal.room === rid) key = goal.key;
    else {
      const nx = nextRoom(rid, goal.room);
      if (!nx) return { ...IDLE };
      key = `exit:${nx}`;
    }
    const nav = getNav(rid);
    const start = nav.snap(p.x, p.y);
    stats.replans += 1;
    if (start < 0) {
      stats.noPlan += 1;
      return { ...IDLE };
    }
    const r = nav.reachable([start]);
    const hit = r.found.get(key);
    if (!hit) {
      stats.noPlan += 1;
      return { ...IDLE };
    }
    const path = nav.pathFrom(r.prev, hit.node);
    const mi = path.length ? path[0] : hit.mi;
    const m = nav.macros[mi];
    if (cycleBlock(m)) return { ...IDLE };
    stats.macros += 1;
    macro = { m, f: 0, airborne: false, cut: false };
    const input = macroInput(m, 0);
    macro.f = 1;
    return input;
  }

  return {
    next,
    stats,
    get goalIndex() {
      return gi;
    },
    get stuckFrames() {
      return stuckFrames;
    },
    get done() {
      return gi >= goals.length && game.mode === "complete";
    },
  };
}

export function playGame(core, opts = {}) {
  const game = new core.Game({ seed: opts.seed ?? 1, save: opts.save });
  if (opts.setup) opts.setup(game);
  const bot = createBot(core, game, opts);
  const max = opts.maxFrames ?? 60 * 60 * 40;
  const timeline = [];
  let f = 0;
  for (; f < max; f += 1) {
    const input = bot.next();
    game.step(input);
    for (const e of game.drainEvents()) {
      if (e.t === "memory" || e.t === "ability" || e.t === "checkpoint" || e.t === "died" || e.t === "bossPhase" || e.t === "complete" || e.t === "roomEnter") timeline.push({ f: game.save.playFrames, e: e.t === "roomEnter" ? `room:${e.room}` : e.t + (e.id ? `:${e.id}` : e.phase ? `:${e.phase}` : "") });
    }
    if (game.mode === "complete") break;
    if (bot.stuckFrames > (opts.stuckLimit ?? 60 * 25)) {
      return { ok: false, reason: "stuck", game, bot, frames: f, timeline };
    }
    if (opts.stop && opts.stop(game)) break;
  }
  return { ok: game.mode === "complete", reason: game.mode === "complete" ? "complete" : "timeout", game, bot, frames: f, timeline };
}

