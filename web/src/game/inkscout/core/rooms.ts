import { TILE } from "./constants";
import type { EnemyDef } from "./enemies";
import type { Facing, MemoryId, RoomId } from "./types";

/**
 * 11 phòng của Chương 0 — Kho Lưu Trữ Bị Lãng Quên. Mỗi phòng được dựng bằng `RoomBuilder` (toạ độ ô) rồi chuyển sang chuỗi ASCII
 * (`TileMap` đọc). Số đo thiết kế bám theo mô phỏng người chơi (xem `ink-scout-core.test.mjs`):
 *   • nhảy cao tối đa ≈ 57 px (3 ô) ⇒ bậc thang ≤ 3 ô; nhảy xa ≈ 58 px ⇒ khe ≤ 3 ô tự nhảy được (4 ô sát giới hạn);
 *   • Margin Step cộng ≈ +40 px ⇒ khe 5 ô BẮT BUỘC lướt (đây là cổng tiến trình metroidvania của chương).
 * Toạ độ thực thể: `tx,ty` = ô mà thực thể ĐỨNG trong (chân ở đáy ô, ngay trên mặt sàn).
 */
export type ThemeId = RoomId;

export interface SpawnDef {
  tx: number;
  ty: number;
  facing?: Facing;
}

export interface ExitDef {
  tx: number;
  ty: number;
  tw: number;
  th: number;
  to: RoomId;
  spawn: string;
}

export type ThingDef =
  | { kind: "checkpoint"; id: string; tx: number; ty: number }
  | { kind: "memory"; id: MemoryId; tx: number; ty: number }
  | { kind: "marginStep"; tx: number; ty: number }
  /** Echo: bóng ma kể chuyện — nói khi người chơi lại gần (một lần mỗi lần vào phòng, có lưu "đã nghe"). */
  | { kind: "echo"; id: string; tx: number; ty: number; range?: number }
  /** Biển chỉ dẫn / bản thảo: hiện chú thích khi lại gần. */
  | { kind: "sign"; id: string; tx: number; ty: number; range?: number }
  /** Glyph chữ viết: chỉ hiện nội dung khi Memory Pulse quét qua. */
  | { kind: "glyphLore"; id: string; tx: number; ty: number }
  | { kind: "bossTrigger"; tx: number; ty: number; tw: number; th: number }
  | { kind: "endingTrigger"; tx: number; ty: number; tw: number; th: number };

/** Thanh Redaction: chu kỳ báo trước → nguy hiểm → nghỉ. Dùng đồng hồ phòng nên tất định. */
export interface CycleHazard {
  tx: number;
  ty: number;
  tw: number;
  th: number;
  period: number;
  offset: number;
  telegraph: number;
  active: number;
}

export interface RoomDef {
  id: RoomId;
  name: string;
  tiles: readonly string[];
  spawns: Readonly<Record<string, SpawnDef>>;
  exits: readonly ExitDef[];
  enemies: readonly EnemyDef[];
  things: readonly ThingDef[];
  cycles: readonly CycleHazard[];
}

class RoomBuilder {
  private readonly g: string[][];

  constructor(
    readonly w: number,
    readonly h: number,
  ) {
    this.g = Array.from({ length: h }, () => Array.from({ length: w }, () => "."));
    this.fill("#", 0, 0, w - 1, 1); // trần
    this.fill("#", 0, 0, 0, h - 1); // tường trái
    this.fill("#", w - 1, 0, w - 1, h - 1); // tường phải
  }

  fill(ch: string, x0: number, y0: number, x1: number, y1: number): this {
    for (let y = y0; y <= y1; y += 1) for (let x = x0; x <= x1; x += 1) if (this.g[y]?.[x] !== undefined) this.g[y][x] = ch;
    return this;
  }

  /** Sàn đặc từ hàng `top` xuống đáy. */
  floor(top: number, x0 = 1, x1 = this.w - 2): this {
    return this.fill("#", x0, top, x1, this.h - 1);
  }

  /** Bệ một chiều tại hàng `row` (mặt bệ = đỉnh hàng này). */
  platform(row: number, x0: number, x1: number): this {
    return this.fill("=", x0, row, x1, row);
  }

  /** Khối đặc (bệ/đài/tường). */
  block(x0: number, y0: number, x1: number, y1: number): this {
    return this.fill("#", x0, y0, x1, y1);
  }

  /** Khoét khoảng trống (hố, cửa, hốc). */
  hole(x0: number, y0: number, x1: number, y1: number): this {
    return this.fill(".", x0, y0, x1, y1);
  }

  spikes(x0: number, x1: number, row: number): this {
    return this.fill("^", x0, row, x1, row);
  }

  glyph(x0: number, x1: number, row: number): this {
    return this.fill("g", x0, row, x1, row);
  }

  rows(): string[] {
    return this.g.map((r) => r.join(""));
  }
}

export const ROOM_ORDER: readonly RoomId[] = ["entrance", "hall", "echo", "stacks", "shrine", "sealed", "secret", "redacted", "bookmark", "arena", "ending"];

function entrance(): RoomDef {
  const b = new RoomBuilder(30, 14).floor(11);
  b.hole(14, 11, 16, 13).spikes(14, 16, 13); // hố 3 ô (nhảy qua dễ), đáy gai
  b.block(20, 10, 21, 10); // bậc 1 ô
  b.hole(29, 8, 29, 10); // cửa phải
  return {
    id: "entrance",
    name: "Cửa Kho Lưu Trữ",
    tiles: b.rows(),
    spawns: { start: { tx: 3, ty: 10, facing: 1 }, fromHall: { tx: 27, ty: 10, facing: -1 } },
    exits: [{ tx: 29, ty: 8, tw: 1, th: 3, to: "hall", spawn: "left" }],
    enemies: [{ kind: "scribble", tx: 24, ty: 10, range: [22, 27] }],
    things: [
      { kind: "sign", id: "tut.move", tx: 6, ty: 10 },
      { kind: "sign", id: "tut.jump", tx: 11, ty: 10 },
      { kind: "sign", id: "tut.attack", tx: 18, ty: 10 },
      { kind: "sign", id: "tut.pulse", tx: 27, ty: 10 },
    ],
    cycles: [],
  };
}

function hall(): RoomDef {
  const b = new RoomBuilder(48, 22).floor(19);
  b.hole(0, 16, 0, 18); // cửa trái → Cửa Kho
  b.hole(39, 19, 41, 21); // hố xuống Dãy Kệ Dưới
  b.platform(16, 22, 26).platform(13, 28, 32).platform(10, 33, 37); // bậc thang lên
  b.block(43, 10, 46, 11); // gờ cao bên phải (cần Margin Step để tới — khe 5 ô)
  b.hole(47, 7, 47, 9); // cửa → Phòng Bí Mật
  b.hole(47, 16, 47, 18); // cửa → Phòng Vọng
  return {
    id: "hall",
    name: "Đại Sảnh Lưu Trữ",
    tiles: b.rows(),
    spawns: {
      left: { tx: 2, ty: 18, facing: 1 },
      hole: { tx: 37, ty: 18, facing: -1 },
      echoDoor: { tx: 45, ty: 18, facing: -1 },
      secretDoor: { tx: 45, ty: 9, facing: -1 },
    },
    exits: [
      { tx: 0, ty: 16, tw: 1, th: 3, to: "entrance", spawn: "fromHall" },
      { tx: 39, ty: 20, tw: 3, th: 2, to: "stacks", spawn: "top" },
      { tx: 47, ty: 16, tw: 1, th: 3, to: "echo", spawn: "left" },
      { tx: 47, ty: 7, tw: 1, th: 3, to: "secret", spawn: "left" },
    ],
    enemies: [
      { kind: "scribble", tx: 13, ty: 18, range: [9, 18] },
      { kind: "scribble", tx: 19, ty: 18, range: [16, 23] },
      { kind: "tornPage", tx: 15, ty: 13 },
      { kind: "tornPage", tx: 29, ty: 8 },
    ],
    things: [
      { kind: "checkpoint", id: "hall", tx: 6, ty: 18 },
      { kind: "sign", id: "hall.sign", tx: 9, ty: 18 },
      { kind: "sign", id: "hall.ledge", tx: 36, ty: 9, range: 40 },
    ],
    cycles: [],
  };
}

function echo(): RoomDef {
  const b = new RoomBuilder(28, 14).floor(11);
  b.hole(0, 8, 0, 10); // cửa trái → Đại Sảnh
  b.glyph(17, 18, 8).glyph(20, 21, 6); // bệ glyph ẨN dẫn lên hốc ký ức: Pulse lộ từng chặng (tầm 56 px) nên cần gọi lại khi đã bước lên bệ đầu
  b.block(22, 6, 26, 7); // hốc ký ức
  return {
    id: "echo",
    name: "Phòng Vọng",
    tiles: b.rows(),
    spawns: { left: { tx: 2, ty: 10, facing: 1 } },
    exits: [{ tx: 0, ty: 8, tw: 1, th: 3, to: "hall", spawn: "echoDoor" }],
    enemies: [
      { kind: "scribble", tx: 8, ty: 10, range: [6, 12] },
      { kind: "scribble", tx: 21, ty: 10, range: [19, 25] },
    ],
    things: [
      { kind: "echo", id: "echo.1", tx: 12, ty: 10, range: 52 },
      { kind: "glyphLore", id: "echo.glyph", tx: 15, ty: 10 },
      { kind: "memory", id: 1, tx: 24, ty: 5 },
    ],
    cycles: [],
  };
}

function stacks(): RoomDef {
  const b = new RoomBuilder(44, 22).floor(19);
  b.block(1, 6, 9, 7); // gờ đón người rơi từ Đại Sảnh
  b.hole(3, 0, 6, 1); // trần mở → quay lại Đại Sảnh
  b.platform(16, 14, 17).platform(13, 10, 13).platform(10, 14, 17).platform(8, 10, 13); // cầu thang một chiều lên gờ
  b.spikes(22, 23, 18).spikes(34, 35, 18); // gai mặt sàn rộng 2 ô (40 px với thân) — nhảy qua được; 3 ô thì KHÔNG (xem test khả năng tiếp cận)
  b.platform(15, 28, 31).platform(15, 38, 40);
  b.hole(43, 16, 43, 18); // cửa phải → Đền Lề
  return {
    id: "stacks",
    name: "Dãy Kệ Dưới",
    tiles: b.rows(),
    spawns: { top: { tx: 5, ty: 5, facing: 1 }, fromShrine: { tx: 41, ty: 18, facing: -1 } },
    exits: [
      { tx: 3, ty: 0, tw: 4, th: 3, to: "hall", spawn: "hole" },
      { tx: 43, ty: 16, tw: 1, th: 3, to: "shrine", spawn: "left" },
    ],
    enemies: [
      { kind: "hound", tx: 19, ty: 18, range: [14, 21] },
      { kind: "hound", tx: 30, ty: 18, range: [26, 33] },
      { kind: "tornPage", tx: 16, ty: 12 },
      { kind: "tornPage", tx: 38, ty: 12 },
      { kind: "scribble", tx: 29, ty: 14 },
    ],
    things: [{ kind: "sign", id: "stacks.sign", tx: 6, ty: 5 }],
    cycles: [],
  };
}

function shrine(): RoomDef {
  const b = new RoomBuilder(32, 16).floor(13);
  b.hole(0, 10, 0, 12); // cửa trái → Dãy Kệ Dưới
  b.block(14, 11, 17, 12); // bệ thờ
  b.hole(25, 13, 29, 15).spikes(25, 29, 15); // khe 5 ô, đáy gai — BẮT BUỘC Margin Step
  b.hole(31, 10, 31, 12); // cửa phải → Chồng Phong Ấn
  return {
    id: "shrine",
    name: "Đền Lề Trang",
    tiles: b.rows(),
    spawns: { left: { tx: 2, ty: 12, facing: 1 }, fromSealed: { tx: 29 + 1, ty: 12, facing: -1 } },
    exits: [
      { tx: 0, ty: 10, tw: 1, th: 3, to: "stacks", spawn: "fromShrine" },
      { tx: 31, ty: 10, tw: 1, th: 3, to: "sealed", spawn: "left" },
    ],
    enemies: [{ kind: "broken", tx: 11, ty: 12 }],
    things: [
      { kind: "checkpoint", id: "shrine", tx: 4, ty: 12 },
      { kind: "marginStep", tx: 16, ty: 10 },
      { kind: "echo", id: "shrine.echo", tx: 8, ty: 12, range: 36 },
    ],
    cycles: [],
  };
}

function sealed(): RoomDef {
  const b = new RoomBuilder(40, 14).floor(11);
  b.hole(9, 11, 13, 13).spikes(9, 13, 13); // khe 1
  b.hole(21, 11, 25, 13).spikes(21, 25, 13); // khe 2
  b.hole(33, 11, 37, 13).spikes(33, 37, 13); // khe 3 (sát cửa phải)
  b.hole(0, 8, 0, 10);
  b.hole(39, 8, 39, 10);
  return {
    id: "sealed",
    name: "Chồng Phong Ấn",
    tiles: b.rows(),
    spawns: { left: { tx: 2, ty: 10, facing: 1 }, fromRedacted: { tx: 38, ty: 10, facing: -1 } },
    exits: [
      { tx: 0, ty: 8, tw: 1, th: 3, to: "shrine", spawn: "fromSealed" },
      { tx: 39, ty: 8, tw: 1, th: 3, to: "redacted", spawn: "left" },
    ],
    enemies: [
      { kind: "hound", tx: 17, ty: 10, range: [14, 20] },
      { kind: "tornPage", tx: 23, ty: 6 },
    ],
    things: [
      { kind: "checkpoint", id: "sealed", tx: 27, ty: 10 },
      { kind: "memory", id: 2, tx: 30, ty: 10 },
    ],
    cycles: [],
  };
}

function secret(): RoomDef {
  const b = new RoomBuilder(26, 14).floor(11);
  b.hole(0, 8, 0, 10);
  b.block(10, 10, 15, 10); // đài ký ức
  return {
    id: "secret",
    name: "Phòng Ký Ức Bí Mật",
    tiles: b.rows(),
    spawns: { left: { tx: 2, ty: 10, facing: 1 } },
    exits: [{ tx: 0, ty: 8, tw: 1, th: 3, to: "hall", spawn: "secretDoor" }],
    enemies: [
      { kind: "tornPage", tx: 7, ty: 6 },
      { kind: "scribble", tx: 19, ty: 10, range: [17, 23] },
    ],
    things: [
      { kind: "echo", id: "secret.echo", tx: 5, ty: 10, range: 48 },
      { kind: "memory", id: 3, tx: 12, ty: 9 },
    ],
    cycles: [],
  };
}

function redacted(): RoomDef {
  const b = new RoomBuilder(52, 14).floor(11);
  b.hole(0, 8, 0, 10);
  b.hole(51, 8, 51, 10);
  b.hole(24, 11, 28, 13).spikes(24, 28, 13); // khe 5 ô thứ tư (cần lướt) — giữa phòng
  b.platform(8, 15, 18).platform(8, 36, 40);
  return {
    id: "redacted",
    name: "Sảnh Bị Biên Tập",
    tiles: b.rows(),
    spawns: { left: { tx: 2, ty: 10, facing: 1 }, fromBookmark: { tx: 49, ty: 10, facing: -1 } },
    exits: [
      { tx: 0, ty: 8, tw: 1, th: 3, to: "sealed", spawn: "fromRedacted" },
      { tx: 51, ty: 8, tw: 1, th: 3, to: "bookmark", spawn: "left" },
    ],
    enemies: [
      { kind: "hound", tx: 10, ty: 10, range: [6, 14] },
      { kind: "tornPage", tx: 17, ty: 5 },
      { kind: "broken", tx: 38, ty: 10 },
      { kind: "hound", tx: 44, ty: 10, range: [41, 48] },
    ],
    things: [{ kind: "checkpoint", id: "redacted", tx: 21, ty: 10 }],
    cycles: [
      // Ba thanh Redaction: cột dọc cắt sàn, đổi pha để tạo nhịp "qua – chờ – qua".
      { tx: 8, ty: 5, tw: 1, th: 6, period: 220, offset: 0, telegraph: 45, active: 30 },
      { tx: 33, ty: 5, tw: 1, th: 6, period: 220, offset: 70, telegraph: 45, active: 30 },
      { tx: 46, ty: 5, tw: 1, th: 6, period: 220, offset: 140, telegraph: 45, active: 30 },
    ],
  };
}

function bookmark(): RoomDef {
  const b = new RoomBuilder(20, 14).floor(11);
  b.hole(0, 8, 0, 10);
  b.hole(19, 8, 19, 10);
  return {
    id: "bookmark",
    name: "Phòng Dấu Trang",
    tiles: b.rows(),
    spawns: { left: { tx: 2, ty: 10, facing: 1 }, fromArena: { tx: 17, ty: 10, facing: -1 } },
    exits: [
      { tx: 0, ty: 8, tw: 1, th: 3, to: "redacted", spawn: "fromBookmark" },
      { tx: 19, ty: 8, tw: 1, th: 3, to: "arena", spawn: "left" },
    ],
    enemies: [],
    things: [
      { kind: "checkpoint", id: "bookmark", tx: 9, ty: 10 },
      { kind: "echo", id: "bookmark.echo", tx: 13, ty: 10, range: 56 },
    ],
    cycles: [],
  };
}

function arena(): RoomDef {
  const b = new RoomBuilder(24, 14).floor(11);
  b.hole(0, 8, 0, 10);
  b.hole(23, 8, 23, 10);
  b.platform(8, 4, 7).platform(8, 16, 19);
  return {
    id: "arena",
    name: "Đấu Trường Biên Tập",
    tiles: b.rows(),
    spawns: { left: { tx: 2, ty: 10, facing: 1 }, fromEnding: { tx: 21, ty: 10, facing: -1 } },
    exits: [
      { tx: 0, ty: 8, tw: 1, th: 3, to: "bookmark", spawn: "fromArena" },
      { tx: 23, ty: 8, tw: 1, th: 3, to: "ending", spawn: "left" },
    ],
    enemies: [],
    things: [{ kind: "bossTrigger", tx: 4, ty: 5, tw: 2, th: 6 }],
    cycles: [],
  };
}

function ending(): RoomDef {
  const b = new RoomBuilder(24, 14).floor(11);
  b.hole(0, 8, 0, 10);
  b.block(10, 10, 13, 10); // bệ bút
  return {
    id: "ending",
    name: "Phòng Kết Thúc",
    tiles: b.rows(),
    spawns: { left: { tx: 2, ty: 10, facing: 1 } },
    exits: [{ tx: 0, ty: 8, tw: 1, th: 3, to: "arena", spawn: "fromEnding" }],
    enemies: [],
    things: [{ kind: "endingTrigger", tx: 10, ty: 5, tw: 4, th: 5 }],
    cycles: [],
  };
}

const BUILDERS: Record<RoomId, () => RoomDef> = {
  entrance, hall, echo, stacks, shrine, sealed, secret, redacted, bookmark, arena, ending,
};

let cache: Record<RoomId, RoomDef> | null = null;

export function rooms(): Record<RoomId, RoomDef> {
  if (!cache) {
    cache = Object.fromEntries(ROOM_ORDER.map((id) => [id, BUILDERS[id]()])) as Record<RoomId, RoomDef>;
  }
  return cache;
}

export function room(id: RoomId): RoomDef {
  return rooms()[id];
}

/** Toạ độ pixel (giữa-chân) của một spawn. */
export function spawnPos(def: RoomDef, name: string): { x: number; y: number; facing: Facing } {
  const s = def.spawns[name] ?? Object.values(def.spawns)[0];
  return { x: s.tx * TILE + TILE / 2, y: (s.ty + 1) * TILE, facing: s.facing ?? 1 };
}

/** In phòng ra ASCII có ký hiệu thực thể (công cụ gỡ lỗi/test; không dùng khi chạy game). */
export function describeRoom(def: RoomDef): string {
  const g = def.tiles.map((r) => r.split(""));
  const put = (tx: number, ty: number, ch: string): void => {
    if (g[ty]?.[tx] !== undefined) g[ty][tx] = ch;
  };
  for (const e of def.enemies) put(e.tx, e.ty, e.kind === "scribble" ? "S" : e.kind === "tornPage" ? "T" : e.kind === "hound" ? "H" : "B");
  for (const t of def.things) {
    if ("tx" in t && t.kind !== "bossTrigger" && t.kind !== "endingTrigger") {
      put(t.tx, t.ty, t.kind === "memory" ? String(t.id) : t.kind === "marginStep" ? "X" : t.kind === "checkpoint" ? "C" : t.kind === "echo" ? "E" : t.kind === "sign" ? "?" : "L");
    }
  }
  for (const x of def.exits) for (let ty = x.ty; ty < x.ty + x.th; ty += 1) for (let tx = x.tx; tx < x.tx + x.tw; tx += 1) if (g[ty][tx] === ".") g[ty][tx] = "D";
  for (const [name, s] of Object.entries(def.spawns)) if (g[s.ty][s.tx] === ".") g[s.ty][s.tx] = name === "start" ? "P" : "p";
  return g.map((r) => r.join("")).join("\n");
}
