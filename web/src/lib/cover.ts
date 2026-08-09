/**
 * Logic anh bia du phong — tach khoi JSX de kiem thu duoc truc tiep.
 *
 * Anh du phong phai ON DINH: cung mot truyen luon ra cung mau, de nguoi dung
 * nhan ra truyen quen o moi trang. Nen mau lay tu ham bam cua `novel_id` chu
 * khong phai tu thu tu render hay so ngau nhien.
 */

/**
 * Cac cap mau du phong — deu lay tu bang mau thuong hieu trong globals.css.
 *
 * Ban truoc dung mau ruc: vang `#fbbf24`, do `#f87171`, xanh la `#4ade80`. Tren
 * mot nen gan den, sau tam bia nhu vay trong nhu den neon, va chung hut mat
 * manh hon chinh ten truyen ngay ben duoi.
 *
 * Sau khi doi sang tim/lo, day la cac sac do TOI hon va deu nam trong ho tim →
 * lo → xanh bien. Van du khac nhau de nhan ra truyen quen, nhung khong con
 * tranh cho voi chu. `.cover-fallback` con phu them mot lop toi o duoi.
 */
export const COVER_PALETTE = [
  ["#6d4aef", "#22d3ee"],
  ["#22d3ee", "#3b82f6"],
  ["#3b82f6", "#8b6cff"],
  ["#a855f7", "#6d4aef"],
  ["#0ea5e9", "#6d4aef"],
  ["#14b8a6", "#3b82f6"],
] as const;

export function paletteFor(seed: string): readonly [string, string] {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return COVER_PALETTE[hash % COVER_PALETTE.length];
}

/** Chu cai dau tien co nghia cua tieu de, dung cho anh du phong. */
export function coverInitial(title: string): string {
  const first = title.trim().charAt(0);
  return first ? first.toLocaleUpperCase("vi") : "?";
}
