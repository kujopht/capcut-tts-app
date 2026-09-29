/**
 * Logic THUAN cua bang tin Cong dong (Social & Play V1) — khong React, khong
 * fetch, nen kiem duoc bang `node --test` (`tests/community-feed.test.mjs`).
 *
 * Bon viec o day, moi viec la mot loi da gap o bang tin cu:
 *
 *   1. Tab + fandom song tren URL (`?tab=following&fandom=naruto`) — Back tra
 *      ve dung bo loc, va mot lien ket chia se mo dung bo loc.
 *   2. Gop trang KHONG TRUNG theo `post_id` — cursor cua may chu da tat dinh,
 *      nhung mot bai vua dang (them vao dau) khong duoc hien hai lan.
 *   3. "Co N bai moi" thay vi chen bai len dau va day nguoi dang doc di cho
 *      khac.
 *   4. ANH CHUP bang tin (bai da tai, cursor, binh luan dang mo, vi tri cuon)
 *      theo DUNG URL, de mo mot bai/ho so roi Back thay lai dung cho cu —
 *      danh sach tai SAU khi trang ve nen cuon tu dong cua Next khong du.
 */

export type FeedScope = "latest" | "following";

export interface FeedQuery {
  scope: FeedScope;
  /** Slug fandom trong `community_fandoms` cua may chu, "" = tat ca. */
  fandom: string;
}

export const MAC_DINH_FEED: FeedQuery = { scope: "latest", fandom: "" };

const SLUG = /^[a-z0-9][a-z0-9_-]{0,63}$/;

export function docTruyVanFeed(search: string | URLSearchParams): FeedQuery {
  const p = typeof search === "string" ? new URLSearchParams(search) : search;
  const scope: FeedScope = p.get("tab") === "following" ? "following" : "latest";
  const f = (p.get("fandom") || "").trim().toLowerCase();
  return { scope, fandom: SLUG.test(f) ? f : "" };
}

/** Chuoi truy van CHUAN (mac dinh bi bo) — cung la khoa cua anh chup. */
export function chuoiTruyVanFeed(q: FeedQuery): string {
  const p = new URLSearchParams();
  if (q.scope === "following") p.set("tab", "following");
  if (q.fandom) p.set("fandom", q.fandom);
  const s = p.toString();
  return s ? `?${s}` : "";
}

export function urlFeed(q: FeedQuery): string {
  return `/community${chuoiTruyVanFeed(q)}`;
}

/** Gop them mot trang vao cuoi, bo bai da co (theo `post_id`), giu thu tu. */
export function gopTrang<T extends { post_id: string }>(cu: readonly T[], moi: readonly T[]): T[] {
  const da = new Set(cu.map((x) => x.post_id));
  const ra = [...cu];
  for (const x of moi) {
    if (da.has(x.post_id)) continue;
    da.add(x.post_id);
    ra.push(x);
  }
  return ra;
}

/**
 * So bai MOI HON bai dau danh sach dang hien, trong trang dau vua hoi lai.
 * Chi dem bai co thoi diem tao LON HON bai dau (hoac bang nhau nhung chua co)
 * — mot bai cu bi day len vi binh luan moi khong phai "bai moi".
 */
export function demBaiMoi<T extends { post_id: string; created_at: string }>(
  dangHien: readonly T[],
  trangDauMoi: readonly T[],
): number {
  if (!dangHien.length) return 0;
  const da = new Set(dangHien.map((x) => x.post_id));
  const moc = dangHien[0].created_at;
  let n = 0;
  for (const x of trangDauMoi) {
    if (!da.has(x.post_id) && x.created_at >= moc) n += 1;
  }
  return n;
}

/** "Có 1 bài mới" / "Có 20+ bài mới" — tran bang so bai cua mot trang. */
export function nhanBaiMoi(n: number, tranTrang: number): string {
  if (n <= 0) return "";
  const so = n >= tranTrang ? `${tranTrang}+` : String(n);
  return `Có ${so} bài mới`;
}

// ------------------------------------------------------------------ anh chup

export interface KhoChuoi {
  getItem(k: string): string | null;
  setItem(k: string, v: string): void;
  removeItem(k: string): void;
}

export const KHOA_ANH_CHUP = "fas.congdong.v1";
export const HET_HAN_ANH_CHUP_MS = 30 * 60 * 1000;
/** Tran de sessionStorage (thuong 5 MB) khong bi mot bang tin dai lam day. */
export const TRAN_BAI_ANH_CHUP = 200;
export const TRAN_BYTE_ANH_CHUP = 1_500_000;

export interface AnhChupFeed<T> {
  khoa: string;
  items: T[];
  nextCursor: string | null;
  depthCapped: boolean;
  /** `post_id` dang mo khoi binh luan day du. */
  moBinhLuan: string[];
  y: number;
  t: number;
}

export function ghiAnhChup<T>(kho: KhoChuoi | null, a: AnhChupFeed<T>): boolean {
  if (!kho) return false;
  const gon: AnhChupFeed<T> = { ...a, items: a.items.slice(0, TRAN_BAI_ANH_CHUP) };
  if (gon.items.length < a.items.length) gon.nextCursor = null;
  let tho = JSON.stringify(gon);
  if (tho.length > TRAN_BYTE_ANH_CHUP) {
    // Qua to: chi nho vi tri + bo loc; danh sach se tai lai tu dau.
    tho = JSON.stringify({ ...gon, items: [], nextCursor: null });
  }
  try {
    kho.setItem(KHOA_ANH_CHUP, tho);
    return true;
  } catch {
    return false;
  }
}

/**
 * Anh chup cho DUNG khoa, con han.
 *
 * `xoa = true` (mac dinh): lay xong thi xoa (dung mot lan). Trang bang tin goi
 * voi `xoa = false` roi TU xoa (`xoaAnhChup`) SAU KHI da cuon ve cho cu — vi
 * effect co the chay hai lan (React StrictMode o dev, hoac phien dang nhap vua
 * ve lam effect chay lai): "doc la xoa" lam lan chay thu hai mat anh chup va
 * tai lai tu dau, nguoi doc bi day ve dau trang.
 */
export function layAnhChup<T>(
  kho: KhoChuoi | null,
  khoa: string,
  bayGio: number,
  xoa = true,
): AnhChupFeed<T> | null {
  if (!kho) return null;
  try {
    const tho = kho.getItem(KHOA_ANH_CHUP);
    if (!tho) return null;
    const a = JSON.parse(tho) as AnhChupFeed<T>;
    const conHan = a.khoa === khoa && typeof a.t === "number" && bayGio - a.t <= HET_HAN_ANH_CHUP_MS;
    if (xoa || !conHan) kho.removeItem(KHOA_ANH_CHUP);
    if (!conHan) return null;
    if (!Array.isArray(a.items) || !Array.isArray(a.moBinhLuan)) return null;
    return a;
  } catch {
    return null;
  }
}

export function xoaAnhChup(kho: KhoChuoi | null): void {
  try {
    kho?.removeItem(KHOA_ANH_CHUP);
  } catch {
    /* bo qua */
  }
}

// ------------------------------------------------------------ ban nhap + khoa

/**
 * Khoa idempotent cho MOT lan dang. Sinh mot lan khi bat dau soan va GIU qua
 * moi lan thu lai — neu yeu cau dau da toi may chu nhung tra loi bi mat, lan
 * thu lai mang cung khoa va may chu tra ve dung bai cu thay vi dang hai lan.
 */
export function taoKhoaGui(ngauNhien: () => string): string {
  const s = ngauNhien().replace(/[^A-Za-z0-9_-]/g, "");
  return (s.length >= 8 ? s : `${s}${Date.now().toString(36)}xxxxxxxx`).slice(0, 64);
}

export interface BanNhap {
  text: string;
  fandom: string;
  spoiler: boolean;
  novelId: string;
  khoaGui: string;
  t: number;
}

export const HET_HAN_BAN_NHAP_MS = 7 * 24 * 60 * 60 * 1000;

export function khoaBanNhap(userId: string): string {
  return `fas.nhap.v1.${userId}`;
}

/** Chi luu khi CO chu — mot ban nhap rong la mot o nho chiem cho vo ich. */
export function ghiBanNhap(kho: KhoChuoi | null, userId: string, b: BanNhap): void {
  if (!kho || !userId) return;
  try {
    if (!b.text.trim()) {
      kho.removeItem(khoaBanNhap(userId));
      return;
    }
    kho.setItem(khoaBanNhap(userId), JSON.stringify(b));
  } catch {
    /* bi chan / day thi thoi — ban nhap van con trong bo nho */
  }
}

export function docBanNhap(kho: KhoChuoi | null, userId: string, bayGio: number): BanNhap | null {
  if (!kho || !userId) return null;
  try {
    const tho = kho.getItem(khoaBanNhap(userId));
    if (!tho) return null;
    const b = JSON.parse(tho) as Partial<BanNhap>;
    if (typeof b.text !== "string" || typeof b.t !== "number") return null;
    if (bayGio - b.t > HET_HAN_BAN_NHAP_MS) {
      kho.removeItem(khoaBanNhap(userId));
      return null;
    }
    return {
      text: b.text,
      fandom: typeof b.fandom === "string" ? b.fandom : "",
      spoiler: Boolean(b.spoiler),
      novelId: typeof b.novelId === "string" ? b.novelId : "",
      khoaGui: typeof b.khoaGui === "string" ? b.khoaGui : "",
      t: b.t,
    };
  } catch {
    return null;
  }
}

export function xoaBanNhap(kho: KhoChuoi | null, userId: string): void {
  if (!kho || !userId) return;
  try {
    kho.removeItem(khoaBanNhap(userId));
  } catch {
    /* bo qua */
  }
}

/** Duong dan ho so cong khai: username neu co, khong thi user_id bat bien. */
export function hoSoHref(tacGia: { username?: string | null; user_id?: string } | null | undefined): string {
  if (!tacGia) return "";
  const h = tacGia.username || tacGia.user_id || "";
  return h ? `/u/${encodeURIComponent(h)}` : "";
}
