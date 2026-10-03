/**
 * Danh mục trò chơi của trang Giải trí (Social & Play V1).
 *
 * Mỗi thẻ PHẢI nói thật bốn điều người chơi cần biết trước khi bấm: chế độ,
 * số người chơi, thời lượng ước chừng, và lượt chơi có được tính XP hay không.
 * Không có "đang online", không có phòng "đang mở" nào nếu không đọc từ trạng
 * thái sống thật.
 *
 * Hai game 3D hiện có là trang HTML tĩnh chạy trong iframe, không nói chuyện
 * với máy chủ — nên KHÔNG tính XP và nói rõ như vậy.
 */

export type CheDoGame = "solo" | "phong";

export interface GameInfo {
  id: string;
  title: string;
  desc: string;
  icon: string;
  color: string;
  cheDo: CheDoGame;
  /** "1", "2", "1–2"… hiển thị nguyên văn. */
  nguoiChoi: string;
  /** Ước chừng, người đọc được: "3–5 phút", "tự do". */
  thoiLuong: string;
  /** `null` = không tính XP. Chuỗi = mô tả luật XP thật (máy chủ kiểm). */
  xp: string | null;
  /** Game tĩnh chạy trong iframe (tải CHỈ khi mở). */
  iframe?: string;
  /** Trang riêng của game (React, có máy chủ). */
  href?: string;
}

export const GAMES: readonly GameInfo[] = [
  {
    id: "cyber-snake",
    title: "Cyber Serpent 3D",
    desc: "Rắn săn mồi 3D trong không gian mạng neon — né tường, ăn năng lượng, giữ nhịp.",
    icon: "🐍",
    color: "#00f0ff",
    cheDo: "solo",
    nguoiChoi: "1",
    thoiLuong: "2–5 phút",
    xp: null,
    iframe: "/games/cyber_snake_3d/index.html",
  },
  {
    id: "cosmic-dragon",
    title: "Cosmic Dragon 3D",
    desc: "Điều khiển rồng vũ trụ bay giữa các vì sao, gom hạt sáng — chơi thư giãn, không có thua.",
    icon: "🐉",
    color: "#a855f7",
    cheDo: "solo",
    nguoiChoi: "1",
    thoiLuong: "tự do",
    xp: null,
    iframe: "/games/cosmic_dragon_3d/index.html",
  },
];

/**
 * Thẻ của "Ink Scout: The Lost Chapter" — chỉ là DỮ LIỆU; trang Giải trí chỉ nối nó vào danh sách khi `GAME_INK_SCOUT_ENABLED` bật (cờ ở
 * `lib/features.ts`). Game có trang riêng (`href`), chạy hoàn toàn trên trình duyệt, lưu cục bộ, không nói chuyện với máy chủ → không tính XP.
 */
export const INK_SCOUT_GAME: GameInfo = {
  id: "ink-scout-lost-chapter",
  title: "Ink Scout: The Lost Chapter",
  desc: "Hành động 2D kiểu metroidvania: xuống Kho Lưu Trữ bị lãng quên, gom ba Mảnh Ký Ức và đối mặt với The Redactor.",
  icon: "🗡️",
  color: "#8b6cff",
  cheDo: "solo",
  nguoiChoi: "1",
  thoiLuong: "20–35 phút",
  xp: null,
  href: "/entertainment/ink-scout",
};

export function nhanCheDo(c: CheDoGame): string {
  return c === "solo" ? "Chơi đơn" : "Phòng 2 người";
}
