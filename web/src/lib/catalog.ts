/**
 * Catalog helper functions for Fanfic World works.
 *
 * Consistently resolves audio availability, chapter count, author name,
 * and fandom badges across Home, Library, and Novel detail views.
 */

import type { Novel } from "@/lib/api";

export function novelHasAudio(novel: {
  novel_id?: string;
  has_audio?: boolean;
  dub_audio_key?: string | null;
  tags?: string[];
}): boolean {
  if (novel.has_audio) return true;
  if (novel.dub_audio_key && novel.dub_audio_key.trim().length > 0) return true;
  if (novel.tags?.some((t) => t === "long_form_audio" || t.toLowerCase().includes("audio"))) return true;
  // Known canonical audio works
  if (novel.novel_id === "nov_rr_156206" || novel.novel_id === "nov_hatake_156690") return true;
  return false;
}

/**
 * Ten ngan hien tren badge cho cac truyen KHONG thuoc fandom nao (truyen
 * Trung / ngon tinh goc...). Key theo novel_id de khong doan mo tu title
 * (tieu de tieng Viet cua cac bo nay dai, cat ngan se xau).
 */
const TEN_GOC_NGAN: Record<string, string> = {
  nov_kho_do_danh: "Khó Dỗ Dành",
  nov_gao_wu_ji_yuan: "Cao Võ Kỷ Nguyên",
  nov_zombie_king: "Zombie King",
  nov_s01_laopo: "Trùng Sinh Từ Vợ Đảo Truy Tôi Bắt Đầu",
};

/**
 * Ten goc/fandom KHONG tien to "Fanfic" ("" khi khong xac dinh duoc) — dung
 * chung cho badge (`novelFandom`) VA chip loc fandom o Thu vien, de hai cho
 * khong bao gio lech nhau nua.
 */
export function novelFandomBase(novel: {
  novel_id?: string;
  title?: string;
  tags?: string[];
  fandom_ids?: string[];
}): string {
  const t = (novel.title ?? "").toLowerCase();
  const tags = (novel.tags ?? []).map((x) => x.toLowerCase());
  const fids = (novel.fandom_ids ?? []).map((x) => x.toLowerCase());
  const has = (...k: string[]) => tags.some((x) => k.some((y) => x.includes(y)));

  let base = "";
  if (t.includes("naruto") || has("naruto", "làng lá") || fids.includes("fan_naruto")) {
    base = "Naruto";
  } else if (t.includes("one piece") || has("one piece", "hải tặc") || fids.includes("fan_onepiece")) {
    base = "One Piece";
  } else if (t.includes("conan") || has("conan", "thám tử") || fids.includes("fan_conan")) {
    base = "Detective Conan";
  } else if (t.includes("genshin") || has("genshin") || fids.includes("fan_genshin")) {
    base = "Genshin Impact";
  } else if (t.includes("fairy tail") || has("fairy tail")) {
    base = "Fairy Tail";
  } else if (t.includes("bleach") || has("bleach") || fids.includes("fan_bleach")) {
    base = "Bleach";
  } else if (t.includes("harry potter") || has("harry potter") || fids.includes("fan_harrypotter")) {
    base = "Harry Potter";
  } else if (t.includes("re:zero") || has("re:zero") || fids.includes("fan_rezero")) {
    base = "Re:Zero";
  } else if (t.includes("avatar") || has("avatar") || fids.includes("fan_avatar")) {
    base = "Avatar";
  } else if (t.includes("bóng rổ") || has("bóng rổ", "kuroko")) {
    base = "Thể thao / Bóng rổ";
  } else if (t.includes("warhammer") || t.includes("sci-fi") || has("warhammer", "scifi")) {
    base = "Sci-Fi / Warhammer";
  } else if (novel.novel_id && TEN_GOC_NGAN[novel.novel_id]) {
    base = TEN_GOC_NGAN[novel.novel_id];
  } else {
    // Fallback: the co nghia dau tien (bo the ky thuat / trang thai / gate),
    // viet hoa chu dau; khong dung the chung chung ("fanfic", "dong nhan").
    const candidate = (novel.tags ?? []).find(
      (tag) =>
        !tag.startsWith("work:") &&
        tag !== "imported" &&
        tag !== "long_form_audio" &&
        !tag.startsWith("fandom:Da Fandom") &&
        !tag.startsWith("gate:") &&
        tag.toLowerCase() !== "fanfic" &&
        tag.toLowerCase() !== "đồng nhân" &&
        tag.toLowerCase() !== "ongoing" &&
        tag.toLowerCase() !== "completed" &&
        tag.toLowerCase() !== "complete" &&
        tag.toLowerCase() !== "hiatus" &&
        tag.toLowerCase() !== "audio_novel",
    );
    if (candidate) {
      base = candidate.charAt(0).toLocaleUpperCase("vi") + candidate.slice(1);
    }
  }

  return base;
}

/**
 * Badge goc trai tren anh bia: LUON dang "Fanfic <ten goc/fandom>" (vd
 * "Fanfic One Piece", "Fanfic Harry Potter", "Fanfic Cao Võ Kỷ Nguyên").
 * Tra ve "Fanfic" tran khi khong xac dinh duoc gi — khi do the an badge
 * (kieu cu, `fandom !== "Fanfic"`).
 */
export function novelFandom(novel: {
  novel_id?: string;
  title?: string;
  tags?: string[];
  fandom_ids?: string[];
}): string {
  const base = novelFandomBase(novel);
  return base ? `Fanfic ${base}` : "Fanfic";
}

export function formatAuthor(novel: {
  external_author_name?: string | null;
  author_name?: string | null;
}): string {
  if (novel.external_author_name && novel.external_author_name.trim().length > 0) {
    return novel.external_author_name.trim();
  }
  if (novel.author_name && novel.author_name.trim().length > 0) {
    return novel.author_name.trim();
  }
  return "Fanfic Studio";
}

export function formatChapterCount(count?: number | null): string {
  if (!count || count <= 0) {
    return "Trọn bộ audio";
  }
  return `${count} chương`;
}

export function novelPortraitUrl(novel: {
  cover_portrait_url?: string | null;
  cover_url?: string | null;
}): string | null {
  return novel.cover_portrait_url || novel.cover_url || null;
}

export function novelHeroUrl(novel: {
  hero_background_url?: string | null;
  cover_portrait_url?: string | null;
  cover_url?: string | null;
}): string | null {
  return novel.hero_background_url || novel.cover_portrait_url || novel.cover_url || null;
}

export function isLegacyAudioOnly(novel: {
  content_mode?: string | null;
  tags?: string[];
  external_chapter_count?: number;
}): boolean {
  if (novel.content_mode === "audio_only") return true;
  const tags = novel.tags ?? [];
  return tags.some(
    (t) => t === "long_form_audio" || t.startsWith("work:CAT-") || t.startsWith("work:OP-")
  );
}
