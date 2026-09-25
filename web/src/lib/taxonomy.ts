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
  // Co pipeline / trang thai lap lai dang the (Sprint 2): "audio_novel" la co
  // nhap lieu, "completed"/"ongoing" da hien o nhan trang thai rieng.
  if (lower === "audio_novel" || lower === "completed" || lower === "ongoing" || lower === "hiatus") return true;
  return false;
}

/**
 * The qua chung chung de dung vi tri tren the: gan nhu moi truyen o day deu
 * la fanfic, nen "đồng nhân" khong giup chon truyen. Van hien neu khong con
 * the nao khac.
 */
const THE_CHUNG = new Set(["đồng nhân", "fanfic", "fanfiction", "fan fiction"]);

/**
 * The cho THE TRUYEN o Thu vien (Sprint 2): toi da `max` the, BO the trung voi
 * fandom da hien o goc anh (vd "naruto" khi fandom la "Naruto", "genshin
 * impact"), day the chung chung xuong cuoi, viet hoa chu dau.
 */
export function theChoThe(
  novel: { tags?: string[]; title?: string },
  max: number,
  boQua: readonly string[] = [],
): string[] {
  const bo = new Set(boQua.map((x) => x.toLowerCase().trim()).filter(Boolean));
  const tot: string[] = [];
  const chung: string[] = [];
  for (const t of getReaderTags(novel, 99)) {
    const k = t.toLowerCase();
    if (bo.has(k)) continue;
    (THE_CHUNG.has(k) ? chung : tot).push(t.charAt(0).toLocaleUpperCase("vi") + t.slice(1));
  }
  return [...tot, ...chung].slice(0, max);
}

/**
 * Fandom CO CAU TRUC (tu `fandom_ids` va the), KHONG suy tu tieu de.
 *
 * Dung cho CHIP loc fandom o Thu vien: bo loc `fandom` cua backend chi so
 * `fandom_ids` va `tags`, nen mot truyen chi nhan ra fandom qua TIEU DE (vd
 * truyen audio cu gan "fandom:Da Fandom Unresolved") se KHONG hien khi bam
 * chip do. Dem nhung truyen ay vao chip la hua mot ket qua may chu khong tra.
 * Chuoi rong = khong co fandom co cau truc.
 */
export function fandomCauTruc(novel: { tags?: string[]; fandom_ids?: string[] }): string {
  const cac = [...(novel.fandom_ids ?? []), ...(novel.tags ?? [])].map((x) => x.toLowerCase().trim());
  const co = (...k: string[]) => cac.some((x) => k.includes(x));
  if (co("fan_naruto", "naruto", "fandom:naruto")) return "Naruto";
  if (co("fan_onepiece", "one piece", "fandom:one piece")) return "One Piece";
  if (co("fan_conan", "conan", "fandom:detective conan")) return "Detective Conan";
  if (co("fan_genshin", "genshin", "genshin impact", "fandom:genshin impact")) return "Genshin Impact";
  if (co("fairy tail", "fandom:fairy tail")) return "Fairy Tail";
  const the = (novel.tags ?? []).find((x) => x.toLowerCase().startsWith("fandom:") && !isInternalTag(x));
  return the ? the.slice(7).trim() : "";
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
 * Suy luận fandom từ tiêu đề khi truyện CHƯA có thẻ fandom chuẩn hóa ở backend.
 *
 * NGUYÊN TẮC BẢO THỦ:
 * - Ưu tiên false negative (không gắn thẻ) hơn là gắn sai fandom (false positive).
 * - Tuyệt đối không dùng từ khóa quá rộng như "ninja", "gin", "hệ thống".
 * - Chỉ nhận diện tên tác phẩm chính thức hoặc cặp danh xưng đặc trưng không thể nhầm lẫn.
 */
export function inferFandomFromTitle(title?: string): string | null {
  if (!title) return null;
  const t = title.toLowerCase();

  // One Piece
  if (t.includes("one piece") || (t.includes("hải tặc") && (t.includes("mũ rơm") || t.includes("luffy")))) {
    return "One Piece";
  }

  // Naruto: không dùng từ "ninja" chung chung
  if (t.includes("naruto") || t.includes("hỏa ảnh") || (t.includes("làng lá") && t.includes("uchiha"))) {
    return "Naruto";
  }

  // Conan: không dùng từ "gin" hay "kisaki" đơn độc
  if (t.includes("conan") || t.includes("thám tử lừng danh") || t.includes("haibara ai") || t.includes("kudo shinichi")) {
    return "Conan";
  }

  // Fairy Tail
  if (t.includes("fairy tail")) {
    return "Fairy Tail";
  }

  // Bóng rổ (Slam Dunk / Kuroko no Basket)
  if (t.includes("slam dunk") || t.includes("kuroko no basket") || t.includes("kuroko") || t.includes("thế giới bóng rổ")) {
    return "Bóng rổ";
  }

  // Dragon Ball
  if (t.includes("dragon ball") || t.includes("7 viên ngọc rồng") || t.includes("bảy viên ngọc rồng") || t.includes("songoku")) {
    return "Dragon Ball";
  }

  // Jujutsu Kaisen
  if (t.includes("jujutsu kaisen") || t.includes("chú thuật hồi chiến")) {
    return "Jujutsu Kaisen";
  }

  // Bleach
  if (t.includes("bleach") && (t.includes("fanfic") || t.includes("shinigami") || t.includes("ichigo"))) {
    return "Bleach";
  }

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
