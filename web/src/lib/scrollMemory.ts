/**
 * NHO VI TRI CUON cua mot danh sach (Thu vien) qua mot lan mo truyen roi Back.
 *
 * Next.js tu khoi phuc cuon khi Back, NHUNG danh sach Thu vien tai du lieu SAU
 * khi trang ve: luc Next cuon, trang con ngan, nen nguoi doc bi dua ve dau
 * trang. Ta tu ghi `scrollY` theo DUNG URL (ke ca bo loc) truoc khi roi trang,
 * va chi cuon lai khi du lieu da ve.
 *
 * Tep thuan (kho luu truyen vao) — `tests/library-query.test.mjs`.
 */

export const KHOA_CUON = "fas.cuon.v1";
/** Qua lau thi thoi: nguoi doc da quen ho dang o dau. */
export const HET_HAN_CUON_MS = 30 * 60 * 1000;

export interface KhoPhien {
  getItem(k: string): string | null;
  setItem(k: string, v: string): void;
  removeItem(k: string): void;
}

interface BanGhi {
  url: string;
  y: number;
  t: number;
}

export function ghiViTri(kho: KhoPhien | null, url: string, y: number, bayGio: number): void {
  if (!kho || !Number.isFinite(y)) return;
  try {
    kho.setItem(KHOA_CUON, JSON.stringify({ url, y: Math.max(0, Math.round(y)), t: bayGio } satisfies BanGhi));
  } catch {
    /* Bi chan thi thoi. */
  }
}

/** Vi tri da nho cho DUNG `url` nay, con han; lay xong thi xoa (dung mot lan). */
export function layViTri(kho: KhoPhien | null, url: string, bayGio: number): number | null {
  if (!kho) return null;
  try {
    const tho = kho.getItem(KHOA_CUON);
    if (!tho) return null;
    const b = JSON.parse(tho) as Partial<BanGhi>;
    if (b.url !== url || typeof b.y !== "number" || typeof b.t !== "number") return null;
    if (bayGio - b.t > HET_HAN_CUON_MS) {
      kho.removeItem(KHOA_CUON);
      return null;
    }
    kho.removeItem(KHOA_CUON);
    return b.y;
  } catch {
    return null;
  }
}
