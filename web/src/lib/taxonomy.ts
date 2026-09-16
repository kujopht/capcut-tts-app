/**
 * Phân loại & Khám phá cho Fanfic World.
 *
 * Tách biệt phân loại cho người đọc (fandom, chủ đề, định dạng)
 * khỏi các cờ kỹ thuật nội bộ (work:*, imported, long_form_audio, Da Fandom Unresolved).
 */

export interface FandomOption {
  id: string;
  label: string;
  tag?: string;   // Thẻ backend nếu có trong cơ sở dữ liệu
  query?: string; // Từ khóa tìm kiếm nếu thẻ chưa chuẩn hóa
}

/**
 * Danh mục fandom chính quy cho độc giả.
 */
export const FANDOM_OPTIONS: FandomOption[] = [
  { id: "all", label: "Tất cả vũ trụ" },
  { id: "one-piece", label: "One Piece", tag: "fandom:One Piece" },
  { id: "naruto", label: "Naruto", tag: "fandom:Naruto" },
  { id: "conan", label: "Conan", query: "Conan" },
  { id: "fairy-tail", label: "Fairy Tail", query: "Fairy Tail" },
  { id: "bong-ro", label: "Bóng rổ", query: "Bóng Rổ" },
];

/**
 * Lọc bỏ hoàn toàn các thẻ kỹ thuật nội bộ khỏi giao diện người đọc:
 * - work:* (mã tác phẩm nội bộ e.g. work:CAT-*, work:OP-*)
 * - imported (cờ di trú dữ liệu)
 * - long_form_audio (cờ pipeline sinh âm thanh)
 * - Da Fandom Unresolved (trạng thái chờ phân loại của crawler)
 */
export function isInternalTag(tag: string): boolean {
  if (!tag) return true;
  const lower = tag.toLowerCase().trim();
  if (lower.startsWith("work:") || lower.startsWith("work-")) return true;
  if (lower === "imported") return true;
  if (lower === "long_form_audio") return true;
  if (lower.includes("unresolved")) return true;
  return false;
}

/**
 * Chuyển đổi một thẻ thô sang nhãn hiển thị thân thiện:
 * "fandom:One Piece" -> "One Piece"
 * "fandom:Naruto" -> "Naruto"
 */
export function formatReaderTag(tag: string): string | null {
  if (isInternalTag(tag)) return null;
  const trimmed = tag.trim();
  if (trimmed.toLowerCase().startsWith("fandom:")) {
    const rawFandom = trimmed.slice(7).trim();
    if (rawFandom.toLowerCase().includes("unresolved")) return null;
    return rawFandom;
  }
  return trimmed;
}

/**
 * Suy luận fandom từ tiêu đề nếu truyện chưa có thẻ fandom chính thức hoặc thẻ bị unresolved.
 */
export function inferFandomFromTitle(title?: string): string | null {
  if (!title) return null;
  const t = title.toLowerCase();
  if (t.includes("one piece") || t.includes("hải tặc")) return "One Piece";
  if (t.includes("naruto") || t.includes("làng lá") || t.includes("ninja") || t.includes("uchiha")) return "Naruto";
  if (t.includes("conan") || t.includes("gin") || t.includes("kisaki")) return "Conan";
  if (t.includes("fairy tail")) return "Fairy Tail";
  if (t.includes("bóng rổ") || t.includes("kuroko") || t.includes("slam dunk")) return "Bóng rổ";
  if (t.includes("dragon ball") || t.includes("7 viên ngọc rồng")) return "Dragon Ball";
  if (t.includes("jujutsu") || t.includes("kaisen")) return "Jujutsu Kaisen";
  if (t.includes("bleach")) return "Bleach";
  return null;
}

/**
 * Lấy danh sách thẻ sạch cho người đọc hiển thị trên StoryCard hoặc hàng truyện.
 * Tuyệt đối không để lộ các thẻ kỹ thuật (work:*, imported, long_form_audio).
 */
export function getReaderTags(
  novel: { tags?: string[]; title?: string },
  maxTags: number = 3
): string[] {
  const result: string[] = [];
  const seen = new Set<string>();

  // 1. Thẻ fandom hoặc thẻ chủ đề hợp lệ từ novel.tags
  if (Array.isArray(novel.tags)) {
    for (const raw of novel.tags) {
      const clean = formatReaderTag(raw);
      if (clean && !seen.has(clean.toLowerCase())) {
        seen.add(clean.toLowerCase());
        result.push(clean);
      }
    }
  }

  // 2. Nếu chưa có fandom rõ ràng, suy luận từ tiêu đề
  if (result.length === 0 && novel.title) {
    const inferred = inferFandomFromTitle(novel.title);
    if (inferred && !seen.has(inferred.toLowerCase())) {
      seen.add(inferred.toLowerCase());
      result.push(inferred);
    }
  }

  return result.slice(0, maxTags);
}
