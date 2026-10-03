import type { EndingKind, MemoryId } from "./types";

/**
 * Trạng thái lưu của Ink Scout: The Lost Chapter. CHỈ lưu cục bộ (không Appwrite, không mạng). Giao diện `SaveStore` bất đồng bộ để sau này
 * có thể thay bằng lưu đám mây mà lõi không đổi; bản `MemoryStore` dành cho test, `LocalStorageStore` (platform/storage.ts) cho trình duyệt.
 */
export type CheckpointId = "start" | "hall" | "shrine" | "redacted" | "bookmark";
export const CHECKPOINT_IDS: readonly CheckpointId[] = ["start", "hall", "shrine", "redacted", "bookmark"];

export interface SaveSettings {
  /** Hệ số rung màn hình: 0 = tắt, 0.5 = nhẹ, 1 = đủ. */
  shake: 0 | 0.5 | 1;
  muted: boolean;
}

export interface SaveData {
  v: 1;
  checkpoint: CheckpointId;
  marginStep: boolean;
  memories: MemoryId[];
  bossDefeated: boolean;
  ending: EndingKind | null;
  settings: SaveSettings;
  /** Tổng số khung hình đã chơi (60/giây) — thời gian hoàn thành. */
  playFrames: number;
  deaths: number;
  /** Thời gian nhanh nhất (khung hình) qua các lần hoàn thành. */
  bestFrames: number | null;
}

export const SAVE_VERSION = 1;
export const SAVE_KEY = "fanfic.inkscout.lostchapter.v1";

export function defaultSave(): SaveData {
  return {
    v: 1,
    checkpoint: "start",
    marginStep: false,
    memories: [],
    bossDefeated: false,
    ending: null,
    settings: { shake: 1, muted: false },
    playFrames: 0,
    deaths: 0,
    bestFrames: null,
  };
}

const ENDINGS: readonly EndingKind[] = ["basic", "erase", "restore"];
const MAX_FRAMES = 60 * 60 * 24 * 7; // một tuần chơi: trần chống số vô lý

function isObj(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}

function num(x: unknown, lo: number, hi: number, fallback: number): number {
  return typeof x === "number" && Number.isFinite(x) ? Math.min(hi, Math.max(lo, Math.floor(x))) : fallback;
}

/** Biến BẤT KỲ giá trị nào (kể cả JSON hỏng/bị sửa tay) thành `SaveData` hợp lệ. Không bao giờ ném lỗi. */
export function sanitizeSave(raw: unknown): SaveData {
  const d = defaultSave();
  if (!isObj(raw)) return d;
  if (typeof raw.checkpoint === "string" && (CHECKPOINT_IDS as readonly string[]).includes(raw.checkpoint)) d.checkpoint = raw.checkpoint as CheckpointId;
  d.marginStep = raw.marginStep === true;
  if (Array.isArray(raw.memories)) {
    const set = new Set<MemoryId>();
    for (const m of raw.memories) if (m === 1 || m === 2 || m === 3) set.add(m);
    d.memories = [...set].sort();
  }
  d.bossDefeated = raw.bossDefeated === true;
  if (typeof raw.ending === "string" && (ENDINGS as readonly string[]).includes(raw.ending)) d.ending = raw.ending as EndingKind;
  if (isObj(raw.settings)) {
    const s = raw.settings.shake;
    d.settings.shake = s === 0 || s === 0.5 || s === 1 ? s : 1;
    d.settings.muted = raw.settings.muted === true;
  }
  d.playFrames = num(raw.playFrames, 0, MAX_FRAMES, 0);
  d.deaths = num(raw.deaths, 0, 1_000_000, 0);
  d.bestFrames = raw.bestFrames === null || raw.bestFrames === undefined ? null : num(raw.bestFrames, 1, MAX_FRAMES, MAX_FRAMES);
  // Nhất quán: ghi nhận đã có kết thúc/boss thì không thể còn ở điểm lưu trước đền hay thiếu Margin Step.
  if (d.ending !== null) d.bossDefeated = true;
  if (d.checkpoint === "shrine" || d.checkpoint === "redacted" || d.checkpoint === "bookmark") {
    // Điểm lưu sau Đền Lề không đạt được nếu chưa có Margin Step (khe 5 ô) — coi như tiến trình hỏng → về điểm đầu của vùng hợp lệ.
    if (d.checkpoint !== "shrine" && !d.marginStep) d.checkpoint = "shrine";
  }
  return d;
}

export interface SaveStore {
  load(): Promise<SaveData | null>;
  save(data: SaveData): Promise<void>;
  clear(): Promise<void>;
}

export class MemoryStore implements SaveStore {
  private blob: string | null = null;

  async load(): Promise<SaveData | null> {
    if (this.blob === null) return null;
    try {
      return sanitizeSave(JSON.parse(this.blob));
    } catch {
      return null;
    }
  }

  async save(data: SaveData): Promise<void> {
    this.blob = JSON.stringify(data);
  }

  async clear(): Promise<void> {
    this.blob = null;
  }

  /** Gài dữ liệu thô (test hỏng/thiếu trường). */
  seedRaw(blob: string | null): void {
    this.blob = blob;
  }
}

/** Có đủ điều kiện "tiếp tục" không (đã có tiến trình đáng kể)? */
export function hasProgress(s: SaveData): boolean {
  return s.checkpoint !== "start" || s.marginStep || s.memories.length > 0 || s.bossDefeated || s.playFrames > 0;
}

export function endingEligibility(memories: readonly MemoryId[]): { choice: boolean; extraDialogue: boolean } {
  return { choice: memories.length >= 3, extraDialogue: memories.length >= 2 };
}
