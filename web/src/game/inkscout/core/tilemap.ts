import { TILE } from "./constants";
import type { FootBox, Rect } from "./types";

/**
 * Bản đồ ô + va chạm AABB quét theo trục. Lõi KHÔNG biết gì về vẽ; mọi truy vấn là hàm thuần trên mảng ô.
 *
 * Chú giải ASCII của phòng (`rooms.ts`):
 *   `#` đặc (kệ sách / đá)   `=` bệ một chiều (đi xuyên từ dưới lên, đứng được từ trên)
 *   `^` gai mực (sát thương + về chỗ an toàn)   `g` bệ glyph ẨN (chỉ đặc khi Memory Pulse đã lộ ra)
 *   `.` hoặc khoảng trắng = không khí
 */
export const T = { AIR: 0, SOLID: 1, ONEWAY: 2, SPIKE: 3, GLYPH: 4 } as const;
export type TileKind = (typeof T)[keyof typeof T];

const EPS = 0.001;

export class TileMap {
  readonly w: number;
  readonly h: number;
  readonly cells: Uint8Array;
  /** Số khung còn lại mà mỗi ô glyph đang LỘ (0 = ẩn). Chỉ có nghĩa với ô `T.GLYPH`. */
  readonly glyphUntil: Int16Array;

  constructor(rows: readonly string[]) {
    this.h = rows.length;
    this.w = rows.reduce((m, r) => Math.max(m, r.length), 0);
    this.cells = new Uint8Array(this.w * this.h);
    this.glyphUntil = new Int16Array(this.w * this.h);
    for (let ty = 0; ty < this.h; ty += 1) {
      const row = rows[ty];
      for (let tx = 0; tx < this.w; tx += 1) {
        const c = row[tx] ?? ".";
        this.cells[ty * this.w + tx] = c === "#" ? T.SOLID : c === "=" ? T.ONEWAY : c === "^" ? T.SPIKE : c === "g" ? T.GLYPH : T.AIR;
      }
    }
  }

  get pxW(): number {
    return this.w * TILE;
  }

  get pxH(): number {
    return this.h * TILE;
  }

  kind(tx: number, ty: number): TileKind {
    if (tx < 0 || tx >= this.w) return T.SOLID; // hai bên là tường: chỉ ra khỏi phòng qua cửa (exit)
    if (ty < 0 || ty >= this.h) return T.AIR; // trên = trời mở, dưới = hố (rơi → hồi sinh)
    return this.cells[ty * this.w + tx] as TileKind;
  }

  /** Ô đặc với va chạm (kể cả glyph đang lộ). */
  solid(tx: number, ty: number): boolean {
    const k = this.kind(tx, ty);
    if (k === T.SOLID) return true;
    if (k === T.GLYPH) return this.glyphUntil[ty * this.w + tx] > 0;
    return false;
  }

  /** Đổi một ô (khoá/mở cửa đấu trường). Không đổi kích thước bản đồ. */
  setCell(tx: number, ty: number, kind: TileKind): void {
    if (tx >= 0 && tx < this.w && ty >= 0 && ty < this.h) this.cells[ty * this.w + tx] = kind;
  }

  /** Nội dung ô cho lớp vẽ: glyph ẩn đã lộ trả về `true`. */
  glyphRevealed(tx: number, ty: number): boolean {
    return tx >= 0 && tx < this.w && ty >= 0 && ty < this.h && this.glyphUntil[ty * this.w + tx] > 0;
  }

  /** Lộ mọi ô glyph trong bán kính `r` (pixel) quanh (cx,cy). Trả số ô vừa được lộ/gia hạn. */
  revealGlyphs(cx: number, cy: number, r: number, frames: number): number {
    let n = 0;
    const tx0 = Math.max(0, Math.floor((cx - r) / TILE));
    const tx1 = Math.min(this.w - 1, Math.floor((cx + r) / TILE));
    const ty0 = Math.max(0, Math.floor((cy - r) / TILE));
    const ty1 = Math.min(this.h - 1, Math.floor((cy + r) / TILE));
    for (let ty = ty0; ty <= ty1; ty += 1) {
      for (let tx = tx0; tx <= tx1; tx += 1) {
        if (this.cells[ty * this.w + tx] !== T.GLYPH) continue;
        const dx = tx * TILE + TILE / 2 - cx;
        const dy = ty * TILE + TILE / 2 - cy;
        if (dx * dx + dy * dy <= r * r) {
          this.glyphUntil[ty * this.w + tx] = frames;
          n += 1;
        }
      }
    }
    return n;
  }

  /** Mỗi khung: các ô glyph đang lộ đếm lùi. */
  tick(): void {
    const g = this.glyphUntil;
    for (let i = 0; i < g.length; i += 1) if (g[i] > 0) g[i] -= 1;
  }

  /** Có ô đặc nào chồng lên hình chữ nhật (góc trên-trái, pixel)? */
  rectHitsSolid(r: Rect): boolean {
    const tx0 = Math.floor(r.x / TILE);
    const tx1 = Math.floor((r.x + r.w - EPS) / TILE);
    const ty0 = Math.floor(r.y / TILE);
    const ty1 = Math.floor((r.y + r.h - EPS) / TILE);
    for (let ty = ty0; ty <= ty1; ty += 1) for (let tx = tx0; tx <= tx1; tx += 1) if (this.solid(tx, ty)) return true;
    return false;
  }

  /** Chạm gai? Vùng sát thương = nửa dưới của ô gai. */
  hitsSpike(b: FootBox): boolean {
    const left = b.x - b.w / 2;
    const right = b.x + b.w / 2;
    const top = b.y - b.h;
    const bottom = b.y;
    const tx0 = Math.floor(left / TILE);
    const tx1 = Math.floor((right - EPS) / TILE);
    const ty0 = Math.floor(top / TILE);
    const ty1 = Math.floor((bottom - EPS) / TILE);
    for (let ty = ty0; ty <= ty1; ty += 1) {
      for (let tx = tx0; tx <= tx1; tx += 1) {
        if (this.kind(tx, ty) !== T.SPIKE) continue;
        const sy = ty * TILE + TILE / 2;
        if (bottom > sy && top < (ty + 1) * TILE) return true;
      }
    }
    return false;
  }

  /** Đứng trên mặt đất (đặc hoặc bệ một chiều ngay dưới chân)? */
  groundBelow(b: FootBox): boolean {
    const probe = b.y + 0.1;
    const row = Math.floor(probe / TILE);
    const left = b.x - b.w / 2;
    const right = b.x + b.w / 2;
    const tx0 = Math.floor(left / TILE);
    const tx1 = Math.floor((right - EPS) / TILE);
    for (let tx = tx0; tx <= tx1; tx += 1) {
      if (this.solid(tx, row)) return true;
      if (this.kind(tx, row) === T.ONEWAY && b.y <= row * TILE + 0.5) return true;
    }
    return false;
  }

  /** Đường ngắm không bị ô đặc chắn (lấy mẫu mỗi nửa ô). */
  lineClear(x0: number, y0: number, x1: number, y1: number): boolean {
    const dx = x1 - x0;
    const dy = y1 - y0;
    const steps = Math.max(1, Math.ceil(Math.hypot(dx, dy) / (TILE / 2)));
    for (let i = 1; i < steps; i += 1) {
      const x = x0 + (dx * i) / steps;
      const y = y0 + (dy * i) / steps;
      if (this.solid(Math.floor(x / TILE), Math.floor(y / TILE))) return false;
    }
    return true;
  }
}

export interface MoveResult {
  x: number;
  y: number;
  hitLeft: boolean;
  hitRight: boolean;
  hitFloor: boolean;
  hitCeil: boolean;
}

/**
 * Di chuyển hộp có chân theo (dx, dy): X trước rồi Y. `passOneWay` = bỏ qua bệ một chiều (đang rơi xuyên).
 * Mỗi trục tối đa < 1 ô/khung nên một lần kiểm cột/hàng ngoài cùng là đủ (tốc độ lớn nhất ~5,4 px/khung).
 */
export function moveFoot(map: TileMap, b: FootBox, dx: number, dy: number, passOneWay = false): MoveResult {
  const hw = b.w / 2;
  let x = b.x;
  let y = b.y;
  let hitLeft = false;
  let hitRight = false;
  let hitFloor = false;
  let hitCeil = false;

  if (dx !== 0) {
    x += dx;
    const top = y - b.h;
    const ty0 = Math.floor(top / TILE);
    const ty1 = Math.floor((y - EPS) / TILE);
    if (dx > 0) {
      const tx = Math.floor((x + hw - EPS) / TILE);
      for (let ty = ty0; ty <= ty1; ty += 1) {
        if (map.solid(tx, ty)) {
          x = tx * TILE - hw;
          hitRight = true;
          break;
        }
      }
    } else {
      const tx = Math.floor((x - hw) / TILE);
      for (let ty = ty0; ty <= ty1; ty += 1) {
        if (map.solid(tx, ty)) {
          x = (tx + 1) * TILE + hw;
          hitLeft = true;
          break;
        }
      }
    }
  }

  if (dy !== 0) {
    const prevBottom = y;
    y += dy;
    const left = x - hw;
    const right = x + hw;
    const tx0 = Math.floor(left / TILE);
    const tx1 = Math.floor((right - EPS) / TILE);
    if (dy > 0) {
      const row = Math.floor((y - EPS) / TILE);
      let landed = false;
      for (let tx = tx0; tx <= tx1 && !landed; tx += 1) {
        if (map.solid(tx, row)) landed = true;
        else if (!passOneWay && map.kind(tx, row) === T.ONEWAY && prevBottom <= row * TILE + EPS) landed = true;
      }
      if (landed) {
        y = row * TILE;
        hitFloor = true;
      }
    } else {
      const row = Math.floor((y - b.h) / TILE);
      for (let tx = tx0; tx <= tx1; tx += 1) {
        if (map.solid(tx, row)) {
          y = (row + 1) * TILE + b.h;
          hitCeil = true;
          break;
        }
      }
    }
  }

  return { x, y, hitLeft, hitRight, hitFloor, hitCeil };
}

/** Hai hình chữ nhật (góc trên-trái) giao nhau? */
export function rectsOverlap(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

export function footToRect(b: FootBox): Rect {
  return { x: b.x - b.w / 2, y: b.y - b.h, w: b.w, h: b.h };
}
