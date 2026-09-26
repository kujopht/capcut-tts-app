/**
 * Memory Runes — bảng rune (khóa → ký hiệu + tên tiếng Việt) và luật cho chế độ
 * LUYỆN TẬP (chạy hoàn toàn ở client, không tính điểm).
 *
 * Chế độ TÍNH ĐIỂM không dùng `xepBaiLuyenTap`: bố cục do máy chủ giữ kín, client
 * chỉ biết khóa của thẻ nào đã lật (`server/games_service.py`, `memory-v1`).
 *
 * Mỗi rune có HÌNH khác nhau VÀ tên đọc được — không phân biệt bằng màu.
 */

export interface Rune {
  key: string;
  ten: string;
}

/* Hình vẽ ở `components/games/RuneGlyph.tsx` (SVG nội tuyến — ký hiệu giả kim
   Unicode hiện thành ô trống trên nhiều máy Windows/Android). */
export const RUNES: Record<string, Rune> = {
  ignis: { key: "ignis", ten: "Lửa" },
  aqua: { key: "aqua", ten: "Nước" },
  terra: { key: "terra", ten: "Đất" },
  ventus: { key: "ventus", ten: "Gió" },
  lux: { key: "lux", ten: "Ánh sáng" },
  umbra: { key: "umbra", ten: "Bóng tối" },
  flora: { key: "flora", ten: "Cỏ cây" },
  ferrum: { key: "ferrum", ten: "Sắt" },
  astra: { key: "astra", ten: "Tinh tú" },
  glacies: { key: "glacies", ten: "Băng" },
  fulmen: { key: "fulmen", ten: "Sấm" },
  vita: { key: "vita", ten: "Sự sống" },
};

export const KHOA_RUNE = Object.keys(RUNES);

export type DoKho = "easy" | "normal" | "hard";

export const DO_KHO: Record<DoKho, { ten: string; rows: number; cols: number; pairs: number }> = {
  easy: { ten: "Dễ", rows: 3, cols: 4, pairs: 6 },
  normal: { ten: "Vừa", rows: 4, cols: 4, pairs: 8 },
  hard: { ten: "Khó", rows: 4, cols: 6, pairs: 12 },
};

export const runeCua = (key: string): Rune => RUNES[key] ?? { key, ten: key };

/** Bố cục ngẫu nhiên cho LUYỆN TẬP (Fisher–Yates). */
export function xepBaiLuyenTap(doKho: DoKho, ngauNhien: () => number = Math.random): string[] {
  const { pairs } = DO_KHO[doKho];
  const bai = KHOA_RUNE.slice(0, pairs).flatMap((k) => [k, k]);
  for (let i = bai.length - 1; i > 0; i--) {
    const j = Math.floor(ngauNhien() * (i + 1));
    [bai[i], bai[j]] = [bai[j], bai[i]];
  }
  return bai;
}

/** Điểm hiển thị — CÙNG công thức với máy chủ để luyện tập và tính điểm dễ so. */
export function diemMemory(pairs: number, moves: number, giay: number): number {
  return Math.max(0, pairs * 100 - (moves - pairs) * 15 - Math.floor(giay));
}

export function dongHoGiay(giay: number): string {
  const s = Math.max(0, Math.floor(giay));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
