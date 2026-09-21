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

export function novelFandom(novel: {
  title?: string;
  tags?: string[];
  fandom_ids?: string[];
}): string {
  const t = (novel.title ?? "").toLowerCase();
  const tags = (novel.tags ?? []).map((x) => x.toLowerCase());
  const fids = (novel.fandom_ids ?? []).map((x) => x.toLowerCase());

  if (t.includes("naruto") || tags.some((x) => x.includes("naruto") || x.includes("làng lá")) || fids.includes("fan_naruto")) {
    return "Naruto";
  }
  if (t.includes("one piece") || tags.some((x) => x.includes("one piece") || x.includes("hải tặc")) || fids.includes("fan_onepiece")) {
    return "One Piece";
  }
  if (t.includes("conan") || tags.some((x) => x.includes("conan") || x.includes("thám tử")) || fids.includes("fan_conan")) {
    return "Detective Conan";
  }
  if (t.includes("genshin") || tags.some((x) => x.includes("genshin")) || fids.includes("fan_genshin")) {
    return "Genshin Impact";
  }
  if (t.includes("fairy tail") || tags.some((x) => x.includes("fairy tail"))) {
    return "Fairy Tail";
  }
  if (t.includes("bóng rổ") || tags.some((x) => x.includes("bóng rổ") || x.includes("kuroko"))) {
    return "Thể thao / Bóng rổ";
  }
  if (t.includes("warhammer") || t.includes("sci-fi") || tags.some((x) => x.includes("warhammer") || x.includes("scifi"))) {
    return "Sci-Fi / Warhammer";
  }

  // Fallback to first non-generic tag
  const candidate = (novel.tags ?? []).find((tag) => !tag.startsWith("work:") && tag !== "imported" && tag !== "long_form_audio" && !tag.startsWith("fandom:Da Fandom"));
  if (candidate) {
    return candidate;
  }
  return "Fanfic";
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
