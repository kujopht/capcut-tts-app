/**
 * Bộ giải khả năng tiếp cận (chỉ dùng trong test/QA — không đi vào bundle game).
 *
 * Ý tưởng: dựng các "nút đứng" trên mọi mặt sàn của một phòng (bước 2 px), rồi từ MỖI nút mô phỏng bằng chính `Player` + `TileMap` thật một bộ
 * macro (đi bộ / nhảy với thời gian giữ khác nhau / lướt ở các khung khác nhau). Kết quả là đồ thị cạnh → BFS chứng minh phòng nào, vật thể nào,
 * cửa nào ĐẠT ĐƯỢC với bộ khả năng cho trước, và cho ra chuỗi macro để bot đi lại trong game thật (replay tất định).
 */
const STEP = 2;

export function macroList() {
  const list = [];
  const holds = [4, 7, 11, 60];
  const dirHolds = [8, 16, 30, 90];
  const dashAts = [null, 0, 8, 16, 26];
  // đi bộ
  for (const dir of [-1, 1]) list.push({ kind: "walk", dir, hold: 0, dirHold: 4, dash: null });
  // nhảy tại chỗ
  for (const hold of holds) list.push({ kind: "jump", dir: 0, hold, dirHold: 0, dash: null });
  // lướt mặt đất (cần Margin Step)
  for (const dir of [-1, 1]) for (const at of [0]) list.push({ kind: "dash", dir, hold: 0, dirHold: 0, dash: at });
  // nhảy + hướng + lướt
  for (const dir of [-1, 1]) {
    for (const hold of holds) {
      for (const dh of dirHolds) {
        for (const dash of dashAts) {
          if (dash === 0 && hold !== 60) continue; // lướt khung 0 đã có macro riêng
          list.push({ kind: dash === null ? "jumpMove" : "jumpDash", dir, hold, dirHold: dh, dash });
        }
      }
    }
  }
  return list;
}

export function macroInput(m, f) {
  return {
    left: m.dir < 0 && f < m.dirHold,
    right: m.dir > 0 && f < m.dirHold,
    jump: f < m.hold,
    attack: false,
    pulse: false,
    dash: m.dash !== null && f >= m.dash && f < m.dash + 2,
    confirm: false,
  };
}

export function buildNav(core, roomId, opts = {}) {
  const { Player, TileMap, NO_INPUT, rectsOverlap, room, TILE, footToRect } = core;
  const abilities = { marginStep: !!opts.marginStep, pulseWide: false, pulseCheap: false };
  const def = room(roomId);
  const map = new TileMap(def.tiles);
  if (opts.glyphs) map.glyphUntil.fill(30000);
  const macros = macroList();

  // ---- nút đứng
  const nodes = [];
  const index = new Map();
  for (let ty = 1; ty < map.h; ty += 1) {
    for (let tx = 0; tx < map.w; tx += 1) {
      const k = map.kind(tx, ty);
      const ground = map.solid(tx, ty) || k === 2; // SOLID hoặc ONEWAY
      if (!ground) continue;
      if (map.solid(tx, ty - 1) || map.kind(tx, ty - 1) === 3) continue;
      for (let ox = 0; ox < TILE; ox += STEP) {
        const x = tx * TILE + ox + STEP / 2;
        const y = ty * TILE;
        const foot = { x, y, w: 8, h: 16 };
        if (map.rectHitsSolid({ x: x - 4, y: y - 16, w: 8, h: 16 })) continue;
        if (map.hitsSpike({ ...foot, y: y - 2 })) continue;
        if (!map.groundBelow(foot)) continue;
        const id = nodes.length;
        nodes.push({ id, x, y });
        index.set(`${Math.round(x / STEP)}:${y}`, id);
      }
    }
  }

  function snap(x, y) {
    const cx = Math.round((x - STEP / 2) / STEP) * STEP + STEP / 2;
    for (const dx of [0, -STEP, STEP, -2 * STEP, 2 * STEP]) {
      const id = index.get(`${Math.round((cx + dx) / STEP)}:${y}`);
      if (id !== undefined) return id;
    }
    return -1;
  }

  // ---- mục tiêu "chạm"
  const targets = [];
  for (const ex of def.exits) targets.push({ key: `exit:${ex.to}`, test: (b) => rectsOverlap({ x: ex.tx * TILE, y: ex.ty * TILE, w: ex.tw * TILE, h: ex.th * TILE }, b) });
  for (const t of def.things) {
    if (t.kind === "memory") targets.push({ key: `memory:${t.id}`, test: (b, p) => Math.abs(p.x - (t.tx * TILE + 8)) <= 14 && Math.abs(p.y - (t.ty + 1) * TILE) <= 28 });
    else if (t.kind === "marginStep") targets.push({ key: "marginStep", test: (b, p) => Math.abs(p.x - (t.tx * TILE + 8)) <= 14 && Math.abs(p.y - (t.ty + 1) * TILE) <= 28 });
    else if (t.kind === "checkpoint") targets.push({ key: `checkpoint:${t.id}`, test: (b, p) => Math.abs(p.x - (t.tx * TILE + 8)) <= 18 && Math.abs(p.y - (t.ty + 1) * TILE) <= 26 });
    else if (t.kind === "bossTrigger") targets.push({ key: "bossTrigger", test: (b) => rectsOverlap({ x: t.tx * TILE, y: t.ty * TILE, w: t.tw * TILE, h: t.th * TILE }, b) });
    else if (t.kind === "endingTrigger") targets.push({ key: "endingTrigger", test: (b) => rectsOverlap({ x: t.tx * TILE, y: t.ty * TILE, w: t.tw * TILE, h: t.th * TILE }, b) });
  }
  for (const [name, s] of Object.entries(def.spawns)) {
    void name;
    void s;
  }

  // ---- mô phỏng macro từ mỗi nút
  const edges = nodes.map(() => []);
  const touches = nodes.map(() => []); // [{key, mi, frame, x, y}]
  const noop = () => {};
  for (const n of nodes) {
    for (let mi = 0; mi < macros.length; mi += 1) {
      const m = macros[mi];
      if ((m.kind === "dash" || m.kind === "jumpDash") && !abilities.marginStep) continue;
      const p = new Player(n.x, n.y);
      for (let w = 0; w < 2; w += 1) p.update({ map, input: NO_INPUT, abilities, emit: noop });
      if (!p.onGround) continue;
      const seen = new Set();
      let dead = false;
      let settled = 0;
      const maxF = 260;
      let f = 0;
      for (; f < maxF; f += 1) {
        const input = f < Math.max(m.hold, m.dirHold, (m.dash ?? -1) + 2) ? macroInput(m, f) : NO_INPUT;
        p.update({ map, input, abilities, emit: noop });
        const foot = p.foot;
        const rect = footToRect(foot);
        if (map.hitsSpike(foot) || p.y > map.pxH + 40) {
          dead = true;
          for (const t of targets) if (!seen.has(t.key) && t.test(rect, p)) {
            seen.add(t.key);
            touches[n.id].push({ key: t.key, mi, frame: f });
          }
          break;
        }
        for (const t of targets) {
          if (seen.has(t.key)) continue;
          if (t.test(rect, p)) {
            seen.add(t.key);
            touches[n.id].push({ key: t.key, mi, frame: f });
          }
        }
        const past = f >= Math.max(m.hold, m.dirHold, (m.dash ?? -1) + 2);
        if (past && p.onGround && !p.dashing && Math.abs(p.vx) < 0.05) {
          settled += 1;
          if (settled >= 3) break;
        } else settled = 0;
      }
      if (dead || f >= maxF) continue;
      if (!p.onGround) continue;
      const to = snap(p.x, p.y);
      if (to < 0 || to === n.id) continue;
      edges[n.id].push({ to, mi, frames: f });
    }
  }

  function search(starts) {
    const dist = new Int32Array(nodes.length).fill(-1);
    const prev = new Array(nodes.length).fill(null);
    const q = [];
    for (const s of starts) {
      if (s >= 0 && dist[s] < 0) {
        dist[s] = 0;
        q.push(s);
      }
    }
    for (let qi = 0; qi < q.length; qi += 1) {
      const u = q[qi];
      for (const e of edges[u]) {
        if (dist[e.to] < 0) {
          dist[e.to] = dist[u] + 1;
          prev[e.to] = { from: u, mi: e.mi };
          q.push(e.to);
        }
      }
    }
    return { dist, prev };
  }

  /** Các khoá "chạm" đạt được từ tập nút bắt đầu, kèm nút + macro thực hiện. */
  function reachable(starts) {
    const { dist, prev } = search(starts);
    const found = new Map();
    for (const n of nodes) {
      if (dist[n.id] < 0) continue;
      for (const t of touches[n.id]) {
        const cost = dist[n.id] + 1;
        const cur = found.get(t.key);
        if (!cur || cost < cur.cost) found.set(t.key, { cost, node: n.id, mi: t.mi });
      }
    }
    return { found, dist, prev };
  }

  function pathFrom(prev, node) {
    const out = [];
    let cur = node;
    while (prev[cur]) {
      out.push(prev[cur].mi);
      cur = prev[cur].from;
    }
    return out.reverse();
  }

  return { def, map, nodes, edges, touches, macros, snap, search, reachable, pathFrom, abilities };
}
