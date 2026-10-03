import { TILE, VIEW_H, VIEW_W } from "../core/constants";
import type { Boss } from "../core/boss";
import { cycleState, type Game } from "../core/game";
import type { RoomDef } from "../core/rooms";
import { T, type TileMap } from "../core/tilemap";
import { hash, r } from "./actors";
import { C, type RoomStyle } from "./palette";

type Ctx = CanvasRenderingContext2D;

const BOOK_COLORS = ["#3b2f6e", "#6b2d3d", "#2d5a6b", "#7a6a45", "#4a3a5e", "#34406e", "#5c4a38", "#264f52"];

// ====================================================================== địa hình (vẽ sẵn một lần cho mỗi phòng)
export function buildTerrain(map: TileMap, def: RoomDef): HTMLCanvasElement {
  const cv = document.createElement("canvas");
  cv.width = map.pxW;
  cv.height = map.pxH;
  const c = cv.getContext("2d");
  if (!c) return cv;
  const w = map.w;
  for (let ty = 0; ty < map.h; ty += 1) {
    for (let tx = 0; tx < w; tx += 1) {
      const k = map.kind(tx, ty);
      const x = tx * TILE;
      const y = ty * TILE;
      if (k === T.SOLID) {
        const border = tx === 0 || tx === w - 1 || ty <= 1;
        if (border) shelfTile(c, x, y, tx, ty);
        else stoneTile(c, x, y, tx, ty, map);
      } else if (k === T.ONEWAY) {
        plankTile(c, x, y, tx);
      } else if (k === T.SPIKE) {
        spikeTile(c, x, y, tx);
      }
    }
  }
  void def;
  return cv;
}

function shelfTile(c: Ctx, x: number, y: number, tx: number, ty: number): void {
  r(c, C.wood0, x, y, TILE, TILE);
  for (let s = 0; s < 2; s += 1) {
    const sy = y + s * 8;
    r(c, C.wood1, x, sy + 7, TILE, 1);
    let bx = 0;
    let i = 0;
    while (bx < TILE) {
      const bw = 2 + Math.floor(hash(tx * 3 + i, ty * 2 + s) * 2);
      const bh = 4 + Math.floor(hash(tx + i, ty * 5 + s) * 3);
      const col = BOOK_COLORS[Math.floor(hash(i + tx, s + ty * 7) * BOOK_COLORS.length)];
      r(c, col, x + bx, sy + 7 - bh, bw, bh);
      r(c, "#00000033", x + bx + bw - 1, sy + 7 - bh, 1, bh);
      if (hash(i, tx + ty) < 0.25) r(c, C.parch0, x + bx, sy + 7 - bh + 1, bw, 1);
      bx += bw;
      i += 1;
    }
  }
  r(c, "#00000040", x, y, TILE, 1);
}

function stoneTile(c: Ctx, x: number, y: number, tx: number, ty: number, map: TileMap): void {
  const above = map.solid(tx, ty - 1);
  const below = map.solid(tx, ty + 1);
  r(c, C.slate1, x, y, TILE, TILE);
  // gạch: hai hàng 8px lệch nhau
  const off = (ty & 1) * 8;
  r(c, C.slate0, x, y + 7, TILE, 1);
  r(c, C.slate0, x, y + 15, TILE, 1);
  r(c, C.slate0, x + ((off + 4) % TILE), y, 1, 8);
  r(c, C.slate0, x + ((off + 12) % TILE), y + 8, 1, 8);
  // vân sáng nhẹ
  if (hash(tx, ty) < 0.4) r(c, C.slate2, x + 2 + Math.floor(hash(ty, tx) * 8), y + 2, 3, 1);
  if (hash(tx + 7, ty) < 0.2) r(c, C.slate0, x + 3, y + 10, 4, 1);
  if (!above) {
    r(c, C.slate3, x, y, TILE, 2);
    r(c, C.slate2, x, y + 2, TILE, 1);
    // mảnh giấy vụn / chữ trên sàn
    if (hash(tx, ty * 3) < 0.18) r(c, C.parch1, x + 3 + Math.floor(hash(ty, 2) * 8), y - 1, 3, 1);
  }
  if (!below) r(c, C.navy1, x, y + TILE - 2, TILE, 2);
}

function plankTile(c: Ctx, x: number, y: number, tx: number): void {
  r(c, C.wood1, x, y, TILE, 5);
  r(c, C.parch1, x, y, TILE, 1);
  r(c, C.wood0, x, y + 4, TILE, 1);
  r(c, C.goldDark, x + 1, y + 1, 1, 3);
  r(c, C.goldDark, x + TILE - 2, y + 1, 1, 3);
  if (hash(tx, 9) < 0.5) r(c, C.parch0, x + 5, y + 2, 4, 1);
}

function spikeTile(c: Ctx, x: number, y: number, tx: number): void {
  // Gai là những cây bút lông ngược mực đỏ.
  for (let i = 0; i < 3; i += 1) {
    const bx = x + 1 + i * 5;
    const h = 7 + Math.floor(hash(tx * 3 + i, 4) * 3);
    r(c, C.ink, bx + 1, y + TILE - h, 3, h);
    r(c, C.ink, bx + 2, y + TILE - h - 2, 1, 2);
    r(c, C.crimson, bx + 2, y + TILE - h - 1, 1, 2);
    r(c, C.crimsonDark, bx + 1, y + TILE - 3, 3, 1);
  }
  r(c, C.ink, x, y + TILE - 3, TILE, 3);
}

// ====================================================================== nền nhiều lớp
export interface Mote {
  x: number;
  y: number;
  vx: number;
  vy: number;
  s: number;
}

export function makeMotes(n: number): Mote[] {
  const out: Mote[] = [];
  for (let i = 0; i < n; i += 1) {
    out.push({ x: hash(i, 1) * VIEW_W, y: hash(i, 2) * VIEW_H, vx: (hash(i, 3) - 0.5) * 0.12, vy: -0.02 - hash(i, 4) * 0.08, s: hash(i, 5) < 0.2 ? 2 : 1 });
  }
  return out;
}

export function drawBackground(c: Ctx, grad: CanvasGradient, st: RoomStyle, camX: number, camY: number, tick: number, motes: Mote[]): void {
  c.fillStyle = grad;
  c.fillRect(0, 0, VIEW_W, VIEW_H);
  // lớp xa: các vòm cột
  const fx = Math.round(camX * 0.18);
  for (let i = -1; i < 6; i += 1) {
    const bx = i * 96 - (fx % 96);
    r(c, "#ffffff08", bx, 0, 14, VIEW_H);
    r(c, "#ffffff0b", bx + 14, 0, 2, VIEW_H);
    // vòm
    for (let k = 0; k < 8; k += 1) r(c, "#ffffff06", bx + 16 + k * 5, 18 + Math.round(Math.pow(Math.abs(k - 3.5), 2) * 1.6), 5, 3);
  }
  // lớp giữa: bóng kệ sách
  const mx = Math.round(camX * 0.42);
  const my = Math.round(camY * 0.12);
  for (let i = -1; i < 12; i += 1) {
    const bx = i * 40 - (mx % 40);
    const h = 70 + Math.floor(hash(i + Math.floor(mx / 40), 7) * 60);
    r(c, "#00000044", bx, VIEW_H - h + my, 34, h);
    for (let row = 0; row < 6; row += 1) {
      const yy = VIEW_H - h + 6 + row * 14 + my;
      r(c, "#00000033", bx, yy, 34, 1);
      if (hash(i + Math.floor(mx / 40), row) < 0.3) r(c, st.accent + "40", bx + 4 + Math.floor(hash(row, i) * 24), yy - 3, 2, 2);
    }
  }
  // tia sáng
  c.save();
  c.globalAlpha = 0.05 + Math.sin(tick * 0.01) * 0.01;
  for (let i = 0; i < 3; i += 1) {
    const sx = Math.round(60 + i * 130 - camX * 0.3);
    c.fillStyle = st.accent;
    c.beginPath();
    c.moveTo(sx, 0);
    c.lineTo(sx + 26, 0);
    c.lineTo(sx + 70, VIEW_H);
    c.lineTo(sx + 30, VIEW_H);
    c.closePath();
    c.fill();
  }
  c.restore();
  // thanh bôi đen trôi (tha hoá)
  if (st.corruption > 0) {
    c.save();
    c.globalAlpha = 0.18 * st.corruption + 0.05;
    const n = Math.round(4 + st.corruption * 8);
    for (let i = 0; i < n; i += 1) {
      const w = 30 + Math.floor(hash(i, 21) * 90);
      const y = Math.floor(hash(i, 22) * VIEW_H);
      const x = ((hash(i, 23) * (VIEW_W + 200) + tick * (0.1 + hash(i, 24) * 0.25) - Math.round(camX * 0.25)) % (VIEW_W + 200)) - 100;
      r(c, "#000000", Math.round(x), y, w, 4 + Math.floor(hash(i, 25) * 4));
      r(c, C.crimsonDark, Math.round(x), y + 1, Math.min(w, 8), 1);
    }
    c.restore();
  }
  // hạt bụi bay (vị trí là hàm của `tick` — không phụ thuộc tần số làm tươi màn hình)
  for (const m of motes) {
    const x = (((m.x + m.vx * tick) % VIEW_W) + VIEW_W) % VIEW_W;
    const y = (((m.y + m.vy * tick) % VIEW_H) + VIEW_H) % VIEW_H;
    c.globalAlpha = 0.35 + 0.25 * Math.sin(tick * 0.03 + m.x);
    r(c, st.accent, Math.round(x), Math.round(y), m.s, m.s);
  }
  c.globalAlpha = 1;
}

// ====================================================================== bệ glyph ẩn
export function drawGlyphs(c: Ctx, map: TileMap, glyphs: readonly { tx: number; ty: number }[], tick: number): void {
  for (const g of glyphs) {
    const rem = map.glyphUntil[g.ty * map.w + g.tx];
    const x = g.tx * TILE;
    const y = g.ty * TILE;
    if (rem > 0) {
      const fade = rem < 90 ? (Math.floor(tick / 5) & 1 ? 0.5 : 1) : 1;
      c.globalAlpha = fade;
      r(c, C.goldDark, x, y, TILE, TILE);
      r(c, C.gold, x, y, TILE, 3);
      r(c, C.white, x, y, TILE, 1);
      r(c, "#7a6a2d", x + 2, y + 6, 12, 1);
      // chữ rune
      r(c, C.parch2, x + 3, y + 8, 2, 4);
      r(c, C.parch2, x + 7, y + 8, 2, 2);
      r(c, C.parch2, x + 7, y + 11, 5, 1);
      r(c, C.parch2, x + 11, y + 8, 1, 3);
      c.globalAlpha = 1;
    } else {
      // dấu vết rất mờ: người chơi tinh ý sẽ nhận ra có "thứ gì đó" ở đây
      c.globalAlpha = 0.1 + 0.07 * (0.5 + 0.5 * Math.sin(tick * 0.04 + g.tx * 1.7 + g.ty));
      r(c, C.gold, x, y, TILE, 1);
      r(c, C.gold, x, y + TILE - 1, TILE, 1);
      r(c, C.gold, x, y, 1, TILE);
      r(c, C.gold, x + TILE - 1, y, 1, TILE);
      r(c, C.gold, x + 7, y + 5, 2, 6);
      c.globalAlpha = 1;
    }
  }
}

// ====================================================================== vật thể trong phòng
export function drawThings(c: Ctx, game: Game, tick: number, glow: ReadonlyMap<string, number>): void {
  const px = game.player.x;
  for (const th of game.def.things) {
    const cx = ("tx" in th ? th.tx : 0) * TILE + TILE / 2;
    const fy = ("ty" in th ? th.ty : 0) * TILE + TILE;
    switch (th.kind) {
      case "checkpoint": {
        const active = game.save.checkpoint === th.id;
        // bục đọc sách + cuốn sách + dải dấu trang
        r(c, C.slate1, cx - 4, fy - 7, 8, 7);
        r(c, C.slate2, cx - 5, fy - 8, 10, 2);
        r(c, C.violetDark, cx - 4, fy - 11, 8, 3);
        r(c, C.parch2, cx - 3, fy - 11, 6, 1);
        const bob = Math.round(Math.sin(tick * 0.06) * 1.5);
        const col = active ? C.gold : C.violet;
        r(c, col, cx + 1, fy - 17 + bob, 2, 7);
        r(c, col, cx + 1, fy - 10 + bob, 1, 2);
        r(c, col, cx + 2, fy - 10 + bob, 1, 1);
        if (active) glowOrb(c, cx, fy - 14, 14, "rgba(243,227,162,0.28)");
        break;
      }
      case "memory": {
        if (game.has(th.id)) break;
        const bob = Math.sin(tick * 0.05 + th.id) * 2.5;
        const y = fy - 12 + bob;
        glowOrb(c, cx, y, 22, "rgba(243,227,162,0.35)");
        r(c, C.gold, cx - 3, y - 4, 6, 8);
        r(c, C.gold, cx - 4, y - 3, 8, 6);
        r(c, C.white, cx - 2, y - 2, 4, 4);
        // trang giấy bay quanh
        for (let i = 0; i < 3; i += 1) {
          const a = tick * 0.05 + i * 2.1 + th.id;
          r(c, C.parch2, Math.round(cx + Math.cos(a) * 9) - 1, Math.round(y + Math.sin(a) * 5) - 1, 3, 2);
        }
        break;
      }
      case "marginStep": {
        if (game.save.marginStep) break;
        const bob = Math.sin(tick * 0.06) * 2.5;
        const y = fy - 14 + bob;
        glowOrb(c, cx, y, 26, "rgba(34,211,238,0.35)");
        // mũi tên kép
        for (let i = 0; i < 2; i += 1) {
          r(c, C.cyanLight, cx - 5 + i * 5, y - 1, 4, 2);
          r(c, C.cyanLight, cx - 2 + i * 5, y - 3, 2, 2);
          r(c, C.cyanLight, cx - 2 + i * 5, y + 1, 2, 2);
          r(c, C.cyan, cx - 3 + i * 5, y - 2, 1, 4);
        }
        break;
      }
      case "echo": {
        const bob = Math.sin(tick * 0.04) * 2;
        const near = Math.abs(px - cx) < (th.range ?? 40);
        c.globalAlpha = near ? 0.7 : 0.38;
        glowOrb(c, cx, fy - 14 + bob, 16, "rgba(127,231,255,0.25)");
        // bóng người ghi chép mờ ảo
        r(c, "#7fe7ff", cx - 4, fy - 22 + bob, 8, 8);
        r(c, "#9bd9f0", cx - 6, fy - 14 + bob, 12, 10);
        r(c, "#7fb6d0", cx - 5, fy - 4 + bob, 3, 4);
        r(c, "#7fb6d0", cx + 2, fy - 3 + bob, 3, 3);
        r(c, C.ink, cx - 2, fy - 19 + bob, 1, 2);
        r(c, C.ink, cx + 1, fy - 19 + bob, 1, 2);
        c.globalAlpha = 1;
        break;
      }
      case "sign": {
        r(c, C.wood1, cx - 1, fy - 10, 2, 10);
        r(c, C.parch1, cx - 5, fy - 17, 10, 8);
        r(c, C.parch2, cx - 5, fy - 17, 10, 1);
        r(c, C.parch0, cx - 3, fy - 14, 6, 1);
        r(c, C.parch0, cx - 3, fy - 12, 4, 1);
        break;
      }
      case "glyphLore": {
        const t = glow.get(th.id) ?? 0;
        const x = th.tx * TILE;
        const y = th.ty * TILE;
        if (t > 0) {
          c.globalAlpha = Math.min(1, t / 60);
          glowOrb(c, x + 8, y + 8, 22, "rgba(243,227,162,0.3)");
          for (let i = 0; i < 4; i += 1) r(c, C.gold, x + 1 + i * 4, y + 2 + (i & 1) * 3, 3, 1);
          r(c, C.gold, x + 2, y + 9, 12, 1);
          r(c, C.white, x + 4, y + 12, 8, 1);
          c.globalAlpha = 1;
        } else {
          c.globalAlpha = 0.14;
          r(c, C.parch1, x + 2, y + 4, 10, 1);
          r(c, C.parch1, x + 3, y + 8, 8, 1);
          c.globalAlpha = 1;
        }
        break;
      }
      case "endingTrigger": {
        const lit = game.save.bossDefeated;
        const x = th.tx * TILE + (th.tw * TILE) / 2;
        const y = (th.ty + th.th) * TILE - 12;
        glowOrb(c, x, y, lit ? 30 : 14, lit ? "rgba(246,248,255,0.35)" : "rgba(246,248,255,0.1)");
        if (lit) {
          // cây bút lơ lửng trên bệ
          const bob = Math.sin(tick * 0.05) * 2;
          r(c, C.white, x - 1, y - 16 + bob, 2, 12);
          r(c, C.cyanLight, x - 1, y - 6 + bob, 2, 4);
          r(c, C.gold, x - 2, y - 18 + bob, 4, 3);
        }
        break;
      }
      default:
        break;
    }
  }
}

function glowOrb(c: Ctx, x: number, y: number, rad: number, color: string): void {
  const g = c.createRadialGradient(x, y, 1, x, y, rad);
  g.addColorStop(0, color);
  g.addColorStop(1, "rgba(0,0,0,0)");
  c.fillStyle = g;
  c.fillRect(x - rad, y - rad, rad * 2, rad * 2);
}

export function drawExits(c: Ctx, game: Game, tick: number): void {
  for (const ex of game.def.exits) {
    const x = ex.tx * TILE;
    const y = ex.ty * TILE;
    const w = ex.tw * TILE;
    const h = ex.th * TILE;
    const horizontal = ex.tw > ex.th; // lối rơi xuống / trần
    c.globalAlpha = 0.14 + 0.05 * Math.sin(tick * 0.05);
    r(c, C.cyanLight, x, y, w, h);
    c.globalAlpha = 0.5;
    if (!horizontal) {
      const edge = ex.tx === 0 ? x : x + w - 2;
      r(c, C.cyanLight, edge, y, 2, h);
    }
    c.globalAlpha = 1;
  }
  // cửa đấu trường bị khoá
  if (game.roomId === "arena") {
    for (const side of ["left", "right"] as const) {
      if (!game.doorLocked(side)) continue;
      const x = side === "left" ? 0 : (game.def.tiles[0].length - 1) * TILE;
      r(c, C.ink, x, 8 * TILE, TILE, 3 * TILE);
      for (let i = 0; i < 3; i += 1) {
        r(c, C.crimsonDark, x + 2, 8 * TILE + i * TILE + 2, TILE - 4, 3);
        r(c, C.crimson, x + 2, 8 * TILE + i * TILE + 2, TILE - 4, 1);
      }
      r(c, C.crimsonLight, x + 6, 9 * TILE + 4, 4, 5);
    }
  }
}

export function drawCycles(c: Ctx, game: Game, tick: number): void {
  for (const cy of game.def.cycles) {
    const st = cycleState(cy, game.roomT);
    const x = cy.tx * TILE;
    const y = cy.ty * TILE;
    const w = cy.tw * TILE;
    const h = cy.th * TILE;
    if (st.phase === 0) {
      c.globalAlpha = 0.22;
      for (let i = 0; i < h; i += 6) r(c, C.crimsonDark, x + (w >> 1), y + i, 1, 3);
      c.globalAlpha = 1;
    } else if (st.phase === 1) {
      const blink = (tick >> 2) & 1;
      c.globalAlpha = blink ? 0.9 : 0.4;
      for (let i = 0; i < h; i += 4) r(c, C.crimson, x + 1, y + i, 1, 2);
      for (let i = 0; i < h; i += 4) r(c, C.crimson, x + w - 2, y + i, 1, 2);
      c.globalAlpha = 0.25;
      r(c, C.crimson, x, y, w, h);
      c.globalAlpha = 1;
    } else {
      r(c, C.ink, x, y, w, h);
      r(c, C.crimson, x, y, 1, h);
      r(c, C.crimson, x + w - 1, y, 1, h);
      for (let i = 0; i < h; i += 3) {
        if (hash(i, Math.floor(tick / 2)) < 0.4) r(c, C.parch1, x + 2 + Math.floor(hash(i, 3) * (w - 5)), y + i, 3, 1);
      }
    }
  }
}

// ====================================================================== vùng nguy hiểm của boss
export function drawBossHazards(c: Ctx, b: Boss, tick: number): void {
  const blink = (tick >> 2) & 1;
  for (const l of b.lines) {
    const r0 = l.rect;
    if (l.t < l.telegraph) {
      c.globalAlpha = blink ? 0.85 : 0.35;
      if (l.horizontal) {
        for (let x = 0; x < r0.w; x += 8) r(c, C.crimson, r0.x + x, r0.y + 3, 5, 2);
      } else {
        for (let y = 0; y < r0.h; y += 8) r(c, C.crimson, r0.x + (r0.w >> 1) - 1, r0.y + y, 2, 5);
        r(c, C.crimson, r0.x, r0.y, 1, r0.h);
        r(c, C.crimson, r0.x + r0.w - 1, r0.y, 1, r0.h);
      }
      c.globalAlpha = 0.18;
      r(c, C.crimson, r0.x, r0.y, r0.w, r0.h);
      c.globalAlpha = 1;
    } else if (l.t < l.telegraph + l.active) {
      r(c, C.ink, r0.x, r0.y, r0.w, r0.h);
      r(c, C.crimson, r0.x, r0.y, r0.w, 1);
      r(c, C.crimson, r0.x, r0.y + r0.h - 1, r0.w, 1);
      for (let i = 0; i < r0.w; i += 5) if (hash(i, Math.floor(tick / 2)) < 0.35) r(c, C.parch2, r0.x + i, r0.y + 3, 3, 1);
    }
  }
  for (const z of b.zones) {
    const x = Math.round(z.x - z.w / 2);
    const top = Math.round(b.floorY - 14 * 16);
    const h = 14 * 16;
    if (z.t < z.telegraph) {
      c.globalAlpha = blink ? 0.7 : 0.3;
      r(c, C.crimson, x, top, 1, h);
      r(c, C.crimson, x + z.w - 1, top, 1, h);
      for (let y = 0; y < h; y += 10) r(c, C.crimson, x + 1, top + y, z.w - 2, 1);
      c.globalAlpha = 0.14;
      r(c, C.crimson, x, top, z.w, h);
      c.globalAlpha = 1;
    } else if (z.t < z.telegraph + z.active) {
      r(c, C.ink, x, top, z.w, h);
      r(c, C.crimson, x, top, 1, h);
      r(c, C.crimson, x + z.w - 1, top, 1, h);
      for (let y = 0; y < h; y += 4) {
        if (hash(y, Math.floor(tick / 2) + z.x) < 0.5) r(c, C.parch1, x + 2 + Math.floor(hash(y, 2) * (z.w - 8)), top + y, 6, 1);
      }
    }
  }
  for (const w of b.waves) {
    r(c, C.ink, Math.round(w.x) - 7, Math.round(w.y) - 14, 14, 14);
    r(c, C.crimson, Math.round(w.x) - 7, Math.round(w.y) - 14, 14, 1);
    r(c, C.crimsonLight, Math.round(w.x) - 2, Math.round(w.y) - 16, 4, 2);
  }
  for (const s of b.shots) {
    const x = Math.round(s.x);
    const y = Math.round(s.y);
    r(c, C.ink, x - 4, y - 1, 8, 2);
    r(c, C.ink, x - 1, y - 4, 2, 8);
    r(c, C.ink, x - 3, y - 3, 6, 6);
    r(c, C.crimson, x - 2, y - 2, 4, 4);
    r(c, C.crimsonLight, x - 1, y - 1, 2, 2);
  }
  for (const f of b.fragments) {
    if (f.hp <= 0) continue;
    const x = Math.round(f.x);
    const y = Math.round(f.y);
    const flash = f.flash > 0;
    glowOrb(c, x, y, 12, "rgba(243,227,162,0.3)");
    r(c, flash ? C.white : C.gold, x - 4, y - 5, 8, 10);
    r(c, flash ? C.white : C.goldDark, x - 5, y - 3, 10, 6);
    r(c, C.white, x - 2, y - 3, 4, 3);
    if (f.cracked) {
      r(c, C.ink, x - 1, y - 5, 1, 4);
      r(c, C.ink, x, y - 1, 3, 1);
      r(c, C.ink, x + 2, y, 1, 4);
    }
  }
}

/** Dải cảnh báo trên mặt đất cho các đòn có đường đi (lao/chém), vẽ khi boss đang báo trước. */
export function drawBossTelegraph(c: Ctx, b: Boss, tick: number): void {
  if (b.state !== "telegraph" || !b.attack) return;
  const blink = (tick >> 2) & 1;
  const fy = b.floorY;
  c.globalAlpha = blink ? 0.7 : 0.3;
  if (b.attack === "revisionSlash" || b.attack === "revisionRush") {
    const dir = b.lockX >= b.x ? 1 : -1;
    const len = b.attack === "revisionSlash" ? 138 : 84;
    for (let i = 0; i < len; i += 10) r(c, C.crimson, Math.round(b.x + dir * (12 + i)), fy - 2, 6, 2);
    r(c, C.crimsonLight, Math.round(b.x + dir * (12 + len)), fy - 6, 2, 6);
  } else if (b.attack === "marginCut") {
    for (const dir of [-1, 1]) for (let i = 0; i < 80; i += 10) r(c, C.crimson, Math.round(b.x + dir * (10 + i)), fy - 2, 5, 2);
  } else if (b.attack === "rewrite") {
    c.globalAlpha = 0.5 * (1 - b.t / 30);
    r(c, C.parch2, Math.round(b.x) - 10, fy - 44, 20, 44);
  }
  c.globalAlpha = 1;
  // dấu "!" đỏ trên đầu boss
  if (blink) {
    r(c, C.crimsonLight, Math.round(b.x) - 1, fy - 78, 3, 8);
    r(c, C.crimsonLight, Math.round(b.x) - 1, fy - 68, 3, 3);
  }
}
