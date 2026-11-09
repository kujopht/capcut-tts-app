/** Kiểu dùng chung của lõi mô phỏng (không DOM, không Canvas). */

/** Trạng thái nút ĐANG GIỮ ở một khung hình. Cạnh lên/xuống do mô phỏng tự tính (không tin nguồn nhập). */
export interface InputState {
  left: boolean;
  right: boolean;
  jump: boolean;
  attack: boolean;
  pulse: boolean;
  dash: boolean;
  /** Đóng hộp thoại / xác nhận. */
  confirm: boolean;
}

export const NO_INPUT: Readonly<InputState> = Object.freeze({
  left: false, right: false, jump: false, attack: false, pulse: false, dash: false, confirm: false,
});

/** Hộp trục song song: `x` = giữa, `y` = chân (đáy hộp). Dùng cho thực thể có chân. */
export interface FootBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Hộp trục song song kiểu góc trên-trái. */
export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export type Facing = 1 | -1;

export type RoomId =
  | "entrance"
  | "hall"
  | "echo"
  | "stacks"
  | "shrine"
  | "sealed"
  | "secret"
  | "redacted"
  | "bookmark"
  | "arena"
  | "ending";

export type MemoryId = 1 | 2 | 3;

export type EndingKind = "basic" | "erase" | "restore";

export type SfxName =
  | "jump" | "land" | "slash" | "hit" | "enemyDie" | "hurt" | "pulse" | "pickup" | "memory" | "dash" | "checkpoint"
  | "telegraph" | "bossHit" | "bossPhase" | "bossDie" | "door" | "glyph" | "death" | "ui";

export type FxName =
  | "spark" | "dust" | "inkSplash" | "dashTrail" | "pulseRing" | "memoryGlow" | "debris" | "deleteBurst" | "page";

/** Sự kiện mô phỏng phát ra cho lớp vẽ/âm thanh/giao diện (một chiều: lõi không đọc lại). */
export type GameEvent =
  | { t: "sfx"; name: SfxName; x?: number; y?: number }
  | { t: "fx"; name: FxName; x: number; y: number; dir?: number; n?: number; color?: string }
  | { t: "shake"; amount: number; frames: number }
  | { t: "caption"; id: string; ms?: number }
  | { t: "memory"; id: MemoryId }
  | { t: "ability"; id: "marginStep" }
  | { t: "checkpoint"; room: RoomId }
  | { t: "roomEnter"; room: RoomId; first: boolean }
  | { t: "bossPhase"; phase: 1 | 2 | "dying" }
  | { t: "ending"; kind: EndingKind | "choice" }
  | { t: "died" }
  | { t: "save" }
  | { t: "complete" };

export interface Vec2 {
  x: number;
  y: number;
}
