/**
 * "Gan day" + "Yeu thich" cua bo chon nhan dan — phan THUAN (test bang `node --test`). Luu `localStorage`
 * THEO NGUOI (khoa co `me`): tien ich cua RIENG trinh duyet nay, khong phai du lieu dong bo. Ma nao khong
 * con trong catalog cua nguoi xem thi giao dien tu bo qua khi hien.
 *
 * Giao dien san cho "yeu thich" dong bo may chu sau nay: chi can thay noi doc/ghi, hinh dang giu nguyen.
 */
export interface StickerPrefs {
  recent: string[];
  favorites: string[];
}

export const GAN_DAY_TOI_DA = 16;
export const YEU_THICH_TOI_DA = 32;
const MA_HOP_LE = /^[a-z0-9]+\.[a-z0-9-]+$/;

export const PREFS_RONG: StickerPrefs = { recent: [], favorites: [] };

export function khoaPrefs(me: string): string {
  return `fanfic.chat.stickers.${me}`;
}

function sach(ds: unknown, toiDa: number): string[] {
  if (!Array.isArray(ds)) return [];
  const ra: string[] = [];
  for (const x of ds) {
    if (typeof x === "string" && MA_HOP_LE.test(x) && !ra.includes(x)) ra.push(x);
    if (ra.length >= toiDa) break;
  }
  return ra;
}

export function docPrefs(raw: string | null | undefined): StickerPrefs {
  if (!raw) return PREFS_RONG;
  try {
    const d = JSON.parse(raw) as Partial<StickerPrefs>;
    return { recent: sach(d?.recent, GAN_DAY_TOI_DA), favorites: sach(d?.favorites, YEU_THICH_TOI_DA) };
  } catch {
    return PREFS_RONG;
  }
}

export function themGanDay(p: StickerPrefs, id: string): StickerPrefs {
  return { ...p, recent: [id, ...p.recent.filter((x) => x !== id)].slice(0, GAN_DAY_TOI_DA) };
}

export function doiYeuThich(p: StickerPrefs, id: string): StickerPrefs {
  const co = p.favorites.includes(id);
  return { ...p, favorites: co ? p.favorites.filter((x) => x !== id) : [id, ...p.favorites].slice(0, YEU_THICH_TOI_DA) };
}
