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

export type CheDoGame = "solo" | "phong" | "may-va-phong";

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
  /** XP phụ thuộc máy chủ: máy chủ tắt tính năng (`/api/games/config`) thì thẻ
      phải nói "Không tính XP", không hứa theo `xp`. */
  xpCanMayChu?: boolean;
}

export const GAMES: readonly GameInfo[] = [
  {
    id: "memory-runes",
    title: "Memory Runes",
    desc: "Lật thẻ tìm cặp rune giống nhau. Luyện tập tự do, hoặc đăng nhập để tính điểm — máy chủ giữ kín bố cục.",
    icon: "🔮",
    color: "#f5c46b",
    cheDo: "solo",
    nguoiChoi: "1",
    thoiLuong: "1–4 phút",
    xp: "+2 XP mỗi lượt hợp lệ (cần đăng nhập)",
    href: "/entertainment/memory",
    xpCanMayChu: true,
  },
  {
    id: "caro",
    title: "Caro 15×15",
    desc: "Năm quân liên tiếp là thắng. Luyện với máy, hoặc tạo phòng riêng mời một người bạn bằng mã.",
    icon: "⭕",
    color: "#7dd3fc",
    cheDo: "may-va-phong",
    nguoiChoi: "1 (với máy) hoặc 2",
    thoiLuong: "5–15 phút",
    xp: "Phòng 2 người: +2 XP, thắng thêm +3",
    href: "/entertainment/caro",
    xpCanMayChu: true,
  },
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

export function nhanCheDo(c: CheDoGame): string {
  if (c === "solo") return "Chơi đơn";
  if (c === "phong") return "Phòng 2 người";
  return "Với máy · Phòng 2 người";
}

/** Dòng "Phần thưởng" thật trên thẻ, theo cấu hình SỐNG của máy chủ. */
export function nhanXp(g: GameInfo, mayChuBat: boolean | null): string {
  if (!g.xp) return "Không tính XP";
  if (g.xpCanMayChu && mayChuBat === false) return "Không tính XP (máy chủ chưa bật)";
  return g.xp;
}
