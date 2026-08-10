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

/** Ham bam dung chung cho ca mau lan dau an — cung mot truyen, cung ket qua. */
function bam(seed: string): number {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return hash;
}

export function paletteFor(seed: string): readonly [string, string] {
  return COVER_PALETTE[bam(seed) % COVER_PALETTE.length];
}

/**
 * Cac dau an cho bia du phong.
 *
 * KHONG dung chu cai dau cua ten truyen nua. Mot chu "V" to giua tam bia doc
 * ra la "cho nay chua lam xong" — no la mot cho trong duoc dan nhan, khong
 * phai mot thiet ke. Nam hinh duoi day la nhung hinh CO NGHIA trong the loai:
 * sao, sach, la ban, rune, mat trang.
 *
 * Van ON DINH theo `novel_id`: cung mot truyen luon ra cung mot dau an, de
 * nguoi doc nhan ra truyen quen o moi trang.
 */
export const COVER_SIGILS = ["sao", "sach", "laban", "rune", "trang"] as const;

export type CoverSigil = (typeof COVER_SIGILS)[number];

export function sigilFor(seed: string): CoverSigil {
  /*
    Ham bam RIENG, khong phai mot phep dich bit cua ham bam mau.

    Ban dau dung `bam(seed) >>> 3`. Voi sau truyen thuc te thi BA trong sau ra
    cung mot dau an — do duoc tren anh chup. Nguyen nhan: dich bit giu nguyen
    phan lon cau truc cua so goc, nen hai gia tri gan nhau van roi vao cung mot
    o sau khi chia lay du.

    So nhan khac va mot buoc tron bit o cuoi tra ket qua rai deu hon nhieu.
  */
  let h = 0x811c9dc5;
  for (let i = 0; i < seed.length; i += 1) {
    h = (h ^ seed.charCodeAt(i)) >>> 0;
    h = (h * 0x01000193) >>> 0;
  }
  h ^= h >>> 15;
  return COVER_SIGILS[(h >>> 0) % COVER_SIGILS.length];
}

/** Chu cai dau tien co nghia cua tieu de, dung cho anh du phong. */
export function coverInitial(title: string): string {
  const first = title.trim().charAt(0);
  return first ? first.toLocaleUpperCase("vi") : "?";
}
