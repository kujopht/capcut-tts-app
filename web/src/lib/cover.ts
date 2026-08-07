/**
 * Logic anh bia du phong — tach khoi JSX de kiem thu duoc truc tiep.
 *
 * Anh du phong phai ON DINH: cung mot truyen luon ra cung mau, de nguoi dung
 * nhan ra truyen quen o moi trang. Nen mau lay tu ham bam cua `novel_id` chu
 * khong phai tu thu tu render hay so ngau nhien.
 */

/** Cac cap mau du phong — deu lay tu bang mau thuong hieu trong globals.css. */
export const COVER_PALETTE = [
  ["#7c8cff", "#4dd6c1"],
  ["#4dd6c1", "#60a5fa"],
  ["#60a5fa", "#7c8cff"],
  ["#fbbf24", "#f87171"],
  ["#f87171", "#7c8cff"],
  ["#4ade80", "#4dd6c1"],
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
